# Section 19 — Azure Files & File Sync

## 1. Definition

**Plain language:** Azure Files provides network file shares in the cloud that work like a traditional shared drive — multiple machines can connect to the same share at once over standard SMB or NFS protocols, unlike a Managed Disk which only attaches to one VM at a time.

**Precise definition:** Azure Files is a fully managed file-share service, hosted under a Storage Account ([Section 16](./Section-16-Part4-Azure-Storage-Account-Fundamentals.md)), providing SMB and NFS protocol access to shared file storage that can be mounted concurrently by multiple clients (VMs, on-premises servers, containers), with Azure File Sync extending this to cache and synchronize Azure file shares with on-premises Windows Servers.

## 2. Why It Exists / Problem It Solves

Many existing applications and workflows depend on a traditional, concurrently-shared network file system (a "shared drive") rather than object storage (Blob, [Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md)) or VM-attached block storage (Managed Disks, [Section 18](./Section-18-Part4-Azure-Managed-Disks.md)) — legacy applications expecting a mapped drive letter, multiple VMs needing simultaneous read/write access to the same configuration or data files, or on-premises file servers whose capacity or resilience needs to be extended into the cloud without a full re-architecture. Azure Files exists to support these traditional file-sharing patterns natively, and Azure File Sync exists specifically to bridge existing on-premises file servers with cloud storage, allowing organizations to extend on-premises file infrastructure into Azure incrementally rather than requiring an all-or-nothing migration.

## 3. Core Concepts

### 3.1 Protocol Support

- **SMB (Server Message Block)** — the standard Windows file-sharing protocol, also supported natively by macOS and Linux clients, making Azure File SMB shares broadly cross-platform accessible.
- **NFS (Network File System)** — the standard Linux/Unix file-sharing protocol, supported for scenarios requiring NFS-specific semantics or compatibility with Linux-native applications expecting NFS rather than SMB.

⚠️ Specific feature parity, performance characteristics, and supported tier combinations differ between SMB and NFS shares, and these details evolve — verify current protocol-specific capabilities against official documentation when choosing between them for a specific workload.

### 3.2 Performance Tiers

Similar in concept to Blob Storage's access tiers ([Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md).3.3) but distinct in mechanism, Azure Files offers tiers balancing cost against performance:

- **Transaction Optimized** — for workloads with high transaction volume relative to storage capacity.
- **Hot** — for actively used, general-purpose file share workloads.
- **Cool** — for infrequently accessed file data, lower storage cost.
- **Premium** — SSD-backed, for high-performance, low-latency requirements (e.g., databases requiring file-based storage, performance-sensitive application workloads).

⚠️ Exact tier names and their precise performance/cost characteristics change over time — verify current tier structure against official documentation before selecting one for a production workload.

### 3.3 Azure File Sync

**Definition:** Azure File Sync is a service that synchronizes files between an on-premises Windows Server and an Azure file share, using the Azure file share as a central, authoritative "cloud endpoint," with one or more on-premises servers acting as synchronized "server endpoints."

**Cloud Tiering:** A key Azure File Sync feature is **cloud tiering** — infrequently accessed files can have their content transparently moved to the cloud (Azure Files) while leaving a small placeholder ("stub") on the local on-premises server, so the local server's disk footprint doesn't need to hold the full data set, only what's actually being actively accessed locally, with the full file transparently retrieved from the cloud on-demand when accessed. This effectively lets an on-premises file server present far more data than its local disk capacity would otherwise allow, using Azure Files as an extended, transparent capacity tier.

**Why this matters:** Organizations with substantial existing on-premises file server infrastructure and workflows can adopt cloud storage benefits (centralized backup, disaster recovery, reduced on-premises capacity requirements) incrementally, without forcing every client application or user workflow to be immediately re-pointed at cloud storage directly — the on-premises server continues to present a normal, familiar file share to local users, with Azure File Sync handling the cloud integration transparently behind that familiar interface.

### 3.4 Identity-Based Access

Azure Files supports Entra ID-based (specifically, Entra Domain Services or on-premises Active Directory Domain Services integration, depending on configuration) authentication for SMB shares, allowing the same Active Directory identity and permission model organizations already use for on-premises file shares to be extended to Azure file shares, rather than relying solely on Storage Account key-based authentication for file access.

## 4. Architecture Diagram

```
Azure Storage Account "stmyappfiles"
 └── File Service
      └── File Share "companyshare" (Premium tier)
           ├── Mounted directly by: VM "vm-app-01" (SMB)
           ├── Mounted directly by: Linux VM "vm-app-02" (NFS)
           └── Synchronized via Azure File Sync with:
                 On-Premises Windows Server "fileserver01"
                  ├── Server Endpoint: local sync folder
                  ├── Cloud Tiering: enabled
                  │     — frequently accessed files: full copy stored locally
                  │     — infrequently accessed files: stub only, content in Azure
                  └── Local users/apps: see a normal file share, unaware
                        of the cloud tiering happening behind it
```

## 5. Configuration & Hands-On Example

**Creating a file share and mounting it on a Linux VM (SMB):**

```bash
az storage share-rm create \
  --resource-group rg-myapp-prod \
  --storage-account stmyappfiles \
  --name companyshare \
  --quota 1024 \
  --enabled-protocols SMB

# On the client machine (illustrative mount command):
sudo mount -t cifs //stmyappfiles.file.core.windows.net/companyshare /mnt/companyshare \
  -o username=stmyappfiles,password=<storage-account-key>,serverino
```

- **Purpose:** Creates a 1 TB (1024 GB) SMB file share, then demonstrates mounting it from a Linux client using the CIFS (SMB-compatible) mount mechanism.
- **Important arguments explained individually:**
  - `--quota` — the maximum size of the share in GB; unlike Blob Storage's effectively unlimited scale within a container, a file share has an explicit provisioned/maximum quota that should be sized deliberately.
  - `--enabled-protocols` — specifies SMB (or NFS, though a share is generally restricted to one protocol type depending on the underlying performance tier and configuration) — verify current protocol-selection constraints against documentation.
- **Security note:** The illustrative mount command uses a storage account key directly, which, per the security guidance in [Section 16](./Section-16-Part4-Azure-Storage-Account-Fundamentals.md).7, should be replaced with Entra ID-based/Active Directory-based authentication ([Section 19](./Section-19-Part4-Azure-Files-and-File-Sync.md).3.4) in production wherever feasible, rather than embedding a shared key in mount configuration.

## 6. Production & Enterprise Usage

Enterprises use Azure Files directly (mounted by cloud-hosted VMs or App Service, [Section 13](../Part3/Section-13-Part3-Azure-App-Service.md).3.5's VNet integration relevant here for private access) for scenarios genuinely requiring concurrent shared file access — shared configuration files across a VM Scale Set ([Section 12](../Part3/Section-12-Part3-VM-Scale-Sets.md)), for instance, or lift-and-shift of an application originally designed around a traditional network file share. Azure File Sync is used specifically as a bridging/hybrid strategy: organizations with substantial existing on-premises file server investment use it to extend capacity, gain cloud-based backup/DR for that data, and begin a gradual migration path, without requiring every consuming application or user to be immediately redirected to cloud-native access. This hybrid pattern connects directly to the hybrid cloud deployment model concepts introduced in [Section 2](../Part1/Section-02-Part1-Cloud-Service-and-Deployment-Models.md).8.

## 7. Security Considerations

- Identity-based (Active Directory/Entra ID) authentication should be preferred over Storage Account key-based access for SMB shares wherever feasible, allowing familiar, auditable, per-user/per-group permission models rather than a single shared secret granting full share access.
- Network access to file shares should be restricted (via Private Endpoints or Storage Account firewall rules, Part 5) rather than left open to the public internet, particularly for shares holding sensitive data.
- Azure File Sync's cloud tiering means sensitive data may reside in the cloud file share even when accessed primarily through an on-premises server — the same data-security and compliance considerations applying to any cloud-stored sensitive data (Part 11) apply here as well, and shouldn't be overlooked simply because the primary access pattern feels "on-premises."

## 8. Performance Considerations

File share performance (IOPS, throughput, latency) depends on the selected tier ([Section 19](./Section-19-Part4-Azure-Files-and-File-Sync.md).3.2), similar in principle to the disk performance tier considerations covered in [Section 18](./Section-18-Part4-Azure-Managed-Disks.md).8 — Premium tier is appropriate for genuinely performance-sensitive workloads, while Transaction Optimized, Hot, or Cool tiers suit progressively less performance-sensitive, more cost-sensitive use cases.

## 9. Monitoring

Azure Files metrics (available capacity/quota utilization, transaction counts, latency) integrate with Azure Monitor (Part 10); Azure File Sync additionally provides sync-health monitoring specific to each server endpoint, important for detecting sync failures or conflicts between on-premises and cloud data that could otherwise go unnoticed given the transparent nature of the tiering/sync process.

## 10. Troubleshooting

| Symptom                                                                     | Likely Cause                                                                                                          | Fix                                                                                                                                                                                |
| --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Client cannot mount an Azure file share over SMB                            | Port 445 (SMB) blocked by the client's network/ISP, a common restriction on some networks                             | Use a VPN/ExpressRoute connection (Part 5) to route SMB traffic through an allowed path, since some networks block outbound port 445 entirely                                      |
| On-premises users report a file appears "not yet available" or slow to open | Azure File Sync cloud tiering — the file's content is only a cloud-stored stub locally, requiring on-demand retrieval | Expected behavior for infrequently accessed tiered files; if unacceptable for specific frequently-needed files, adjust cloud tiering policy/thresholds to keep them cached locally |
| File share running out of provisioned quota                                 | Quota set too conservatively relative to actual data growth                                                           | Increase the share's quota (`az storage share-rm update --quota`) proactively based on monitored capacity trends                                                                   |

## 11. Interview Questions — [Section 19](./Section-19-Part4-Azure-Files-and-File-Sync.md)

### 🎯 Intermediate

**Q: When would you choose Azure Files over Blob Storage for a given workload?**

_Model answer:_ Azure Files is appropriate when the workload genuinely needs traditional network-file-share semantics — concurrent access from multiple clients via standard SMB or NFS protocols, a mounted drive letter or mount point that applications interact with as a normal file system, or lift-and-shift compatibility with an existing application built around file-share access patterns. Blob Storage is appropriate for unstructured object storage accessed via HTTP-based APIs — files, images, backups, data lake content — where traditional concurrent file-share semantics (like file locking behavior) aren't required. The deciding factor is usually whether the consuming application or workflow expects a traditional file share interface (Azure Files) or is designed to work with object storage APIs directly (Blob Storage).

_What the interviewer is probing:_ whether the candidate can correctly map a described access pattern to the appropriate storage service, rather than defaulting to Blob Storage for all unstructured-data scenarios.

### 🎯 Senior

**Q: An organization wants to modernize its on-premises file server infrastructure with minimal disruption to existing users and applications. How would Azure File Sync fit into that strategy?**

_Model answer:_ Azure File Sync lets the organization keep its existing on-premises file server(s) as the primary access point for local users and applications — nothing changes from their perspective — while the sync service transparently synchronizes data with an Azure file share behind the scenes, gaining cloud-based backup and disaster-recovery benefits, and potentially reducing required on-premises storage capacity through cloud tiering, where infrequently accessed files are stored as lightweight stubs locally with full content in Azure, retrieved on-demand. This is a genuinely incremental modernization path: it doesn't require immediately redirecting every application or user workflow to cloud-native access, avoids a disruptive all-or-nothing migration, and creates a natural on-ramp toward eventually moving more workloads to direct Azure Files (or other cloud-native) access as confidence and cloud-readiness grow over time. I'd pair this with clear communication to users about cloud tiering's on-demand retrieval behavior for infrequently accessed files, since the latency difference for tiered files (versus a fully local file) is a real, if usually minor, user-facing change worth setting expectations around.

_What the interviewer is probing:_ understanding of Azure File Sync specifically as a hybrid/bridging strategy, connecting the technical mechanism to a broader organizational modernization narrative — the kind of practical, change-management-aware thinking expected at senior level.

## 12. Common Misconceptions

- **"Azure Files and Managed Disks serve the same purpose."** False — Managed Disks attach to exactly one VM at a time (block storage); Azure Files supports concurrent access from multiple clients simultaneously (file storage) — fundamentally different access models suited to different needs.
- **"Azure File Sync fully replaces the on-premises file server."** Not necessarily — File Sync is commonly used to augment and extend an existing on-premises file server (via cloud tiering and cloud-based backup/DR) rather than immediately eliminating it; full replacement is a possible eventual outcome but not an inherent requirement of adopting File Sync.

## 13. Key Takeaways

- 🔑 Azure Files provides SMB/NFS-based network file shares supporting concurrent multi-client access, distinct from Managed Disks' single-VM-attached block storage model.
- 🔑 Azure File Sync bridges on-premises Windows Servers with Azure file shares, with cloud tiering allowing on-premises capacity to be transparently extended via cloud-stored content and local stubs.
- 🔑 Identity-based (AD/Entra ID) authentication should be preferred over Storage Account key-based access for production SMB share access.
- 🔑 Azure Files/File Sync represents a hybrid cloud pattern ([Section 2](../Part1/Section-02-Part1-Cloud-Service-and-Deployment-Models.md).8), enabling incremental, low-disruption modernization of existing on-premises file infrastructure.

## 14. File Share Data Protection: Soft Delete and Share Snapshots

### 14.1 Why This Extends Beyond What Blob Storage and Managed Disks Already Cover

[Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md).14 covered Blob Storage's data-protection mechanisms (versioning, soft delete, PITR, object replication), and [Section 18](./Section-18-Part4-Azure-Managed-Disks.md).14 covered Managed Disk snapshots. Azure Files, despite being hosted under the same Storage Account umbrella as Blob Storage ([Section 16](./Section-16-Part4-Azure-Storage-Account-Fundamentals.md)), has its **own distinct** data-protection mechanisms rather than directly inheriting Blob Storage's — this is a genuine, easy-to-assume-incorrectly gap: enabling Blob soft delete on a Storage Account does **not** automatically protect the File shares hosted in that same account.

### 14.2 Share-Level Soft Delete

**Definition:** **Share Soft Delete**, when enabled on a Storage Account, retains a deleted file share (and its full contents) in a recoverable state for a configured retention period (commonly configurable up to 365 days) before permanent removal — directly analogous in purpose to Blob Storage's Soft Delete ([Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md).14.3), but operating at the file-share level rather than the individual-blob level, and configured as its own distinct setting.

**Why it matters:** Protects against accidental deletion of an entire file share (a genuinely common mistake — deleting the wrong share, or a script targeting the wrong share name) — without it enabled, a deleted share and all its contents are immediately and permanently gone, with no recovery path.

⚠️ Share Soft Delete protects the **share itself** from deletion — it is a distinct setting from any individual-file-level protection within a still-existing share, which is where Share Snapshots ([Section 19](./Section-19-Part4-Azure-Files-and-File-Sync.md).14.3) come in.

### 14.3 Share Snapshots

**Definition:** A **Share Snapshot** is a read-only, point-in-time copy of an entire file share's contents at the moment the snapshot was taken, similar in concept to Managed Disk snapshots ([Section 18](./Section-18-Part4-Azure-Managed-Disks.md).14.2) but operating on a file share's full directory/file structure rather than a block-storage disk.

**Incremental nature:** Like Managed Disk incremental snapshots ([Section 18](./Section-18-Part4-Azure-Managed-Disks.md).14.3), share snapshots only store the data that has changed since the previous snapshot, making a recurring snapshot schedule (e.g., hourly or daily) practical and cost-effective rather than requiring a full copy of the share's entire contents on every snapshot.

**Common use cases:**

- **Recovering an individual accidentally-deleted or -modified file** — a user or application accidentally deletes or overwrites a specific file within an otherwise-intact share; a recent share snapshot allows browsing and restoring that specific file's prior content, without needing to restore the entire share.
- **Point-in-time recovery for the whole share** — reverting the entire share's contents to a prior snapshot if a broader issue (a faulty sync job, a ransomware-style event affecting many files) affected many files across the share simultaneously.
- **Azure File Sync integration** — for shares used with Azure File Sync ([Section 19](./Section-19-Part4-Azure-Files-and-File-Sync.md).3.3), share snapshots provide a recovery mechanism operating alongside the sync relationship, protecting the cloud-side authoritative copy that on-premises servers synchronize against.

### 14.4 Configuration Example

```bash
az storage account file-service-properties update \
  --resource-group rg-myapp-prod \
  --account-name stmyappfiles \
  --enable-delete-retention true \
  --delete-retention-days 30

az storage share snapshot \
  --account-name stmyappfiles \
  --name companyshare
```

- **Purpose:** Enables Share Soft Delete with a 30-day retention window on the Storage Account (protecting against whole-share deletion), then takes a manual share snapshot of the specific share created in [Section 19](./Section-19-Part4-Azure-Files-and-File-Sync.md).5's example (protecting against individual file-level loss or corruption within the share).
- **Production usage note:** For a recurring protection strategy rather than one-off manual snapshots, share snapshots are typically scheduled via Azure Backup's file share backup capability (which manages the snapshot schedule and retention policy centrally, similar in spirit to how Azure Backup manages VM disk backups, [Section 11](../Part3/Section-11-Part3-Azure-Virtual-Machines.md).15.2) rather than relying on manually-triggered ad hoc snapshots for ongoing production protection.

### 14.5 Interview Questions — [Section 19](./Section-19-Part4-Azure-Files-and-File-Sync.md).14

**🎯 Intermediate**
**Q: If Blob Storage Soft Delete is already enabled on a Storage Account, are the Azure File shares in that same account also protected against accidental deletion?**

_Model answer:_ No — Blob Storage Soft Delete and Azure Files Share Soft Delete are distinct, independently configured settings, even though both live under the same Storage Account. Enabling one does not enable the other; a Storage Account holding both Blob containers and File shares that needs deletion protection for both must explicitly enable both Blob Soft Delete and Share Soft Delete separately.

_What the interviewer is probing:_ awareness of this specific, easy-to-assume-incorrectly gap — a real-world configuration mistake where a team assumes account-wide protection when the actual settings are service-specific.

**🎯 Senior**
**Q: A user reports that a critical file was accidentally deleted from a production file share this morning, but the share itself still exists with all its other files intact. Walk through your recovery approach.**

_Model answer:_ Since the share itself wasn't deleted (only one file within it), Share Soft Delete (which protects the share as a whole) isn't the relevant recovery mechanism here — I'd instead look for a Share Snapshot taken before the file was deleted, browsing into that snapshot's point-in-time view of the share to locate and restore the specific file, without needing to touch or revert the rest of the share's current contents. If no recent snapshot exists covering the time before the deletion, this underscores the value of a regular, scheduled snapshot cadence (via Azure Backup's file share backup capability) rather than relying solely on ad hoc manual snapshots — I'd use this incident as the basis for recommending a scheduled snapshot policy going forward if one isn't already in place, to ensure future single-file recovery scenarios like this one have a recent, close-to-current recovery point available.

_What the interviewer is probing:_ whether the candidate correctly distinguishes when Share Soft Delete (whole-share deletion) is the relevant tool versus when Share Snapshots (individual file recovery within an intact share) are the relevant tool — a specific, scenario-driven test of understanding rather than just naming both features abstractly.

### 14.6 Key Takeaways — [Section 19](./Section-19-Part4-Azure-Files-and-File-Sync.md).14

- 🔑 Azure Files has its own distinct data-protection mechanisms (Share Soft Delete, Share Snapshots) — these are separate settings from Blob Storage's equivalent features, even within the same Storage Account, and must be configured independently.
- 🔑 Share Soft Delete protects against accidental deletion of an entire share; Share Snapshots protect against loss or corruption of individual files within an otherwise-intact share — choosing the right recovery tool depends on which of these two scenarios actually occurred.
- 🔑 Share Snapshots are incremental (like Managed Disk snapshots, [Section 18](./Section-18-Part4-Azure-Managed-Disks.md).14.3), making a recurring snapshot schedule practical; production shares should generally use Azure Backup's file share backup capability for centrally-managed, scheduled protection rather than relying only on manual ad hoc snapshots.

## 15. Related Concepts / Part 4 Wrap-Up

This completes the core file-and-block storage services within Part 4. [Section 20](./Section-20-Part4-Data-Redundancy-and-Replication.md) covers **Data Redundancy & Replication (LRS/ZRS/GRS/RA-GRS)** — the redundancy configuration referenced by name throughout this Part (Sections 16, 17, 18) but not yet explained in depth, determining how many copies of data across Blob, File, and Disk storage are kept and where, directly connecting back to the Availability Zone and Region Pair concepts from [Section 3](../Part1/Section-03-Part1-Azure-Global-Infrastructure.md).
