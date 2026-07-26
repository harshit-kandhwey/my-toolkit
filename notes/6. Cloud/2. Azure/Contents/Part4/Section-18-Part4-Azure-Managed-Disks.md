# Section 18 — Azure Disks (Managed Disks, Types)

## 1. Definition

**Plain language:** A Managed Disk is the virtual hard drive attached to an Azure VM — Azure handles the underlying storage infrastructure for it entirely, so you just choose a size and performance level, rather than having to create and manage the storage account details yourself.

**Precise definition:** Azure Managed Disks are block-storage resources, managed as first-class ARM resources independent of any Storage Account the customer must directly configure, providing persistent OS and data storage for Virtual Machines (Section 11), with Azure handling underlying storage account management, placement, and availability-set/zone alignment automatically.

## 2. Why It Exists / Problem It Solves

Before Managed Disks (an evolution of the platform), VM disks were "unmanaged" — backed directly by Page Blobs (Section 17.3.2) in a Storage Account that the customer had to create and manage themselves, including tracking which VMs' disks lived in which Storage Accounts to avoid hitting per-account scalability limits (Section 16.8) when running many VMs, and manually ensuring disks for VMs in the same Availability Set were spread across different underlying storage infrastructure for actual fault tolerance. This was operationally burdensome and error-prone at any real scale. Managed Disks solve this by making the disk itself a fully independent, directly-manageable ARM resource — Azure handles the underlying storage placement, scalability, and fault-domain alignment automatically, removing an entire category of manual capacity-planning and configuration work from the customer.

## 3. Core Concepts

### 3.1 Disk Roles

- **OS Disk** — the disk containing the VM's operating system, created automatically from the chosen image (Section 11.5) when the VM is provisioned; every VM has exactly one OS disk.
- **Data Disk** — additional disks attached to a VM for application data, separate from the OS disk; a VM can have zero or many data disks (up to a size-dependent maximum), and adding/removing data disks doesn't require recreating the VM.
- **Temporary Disk** — a disk physically local to the VM's specific underlying host, providing very low-latency scratch storage (e.g., for OS page files or application temp files), but **not durable** — its contents are lost on certain events (VM deallocation, migration to different host hardware) and it should never be used for data requiring persistence.

⚠️ The Temporary Disk's non-durability is a frequent source of real-world data-loss incidents when misunderstood — any data that must survive a VM restart, deallocation, or host migration must be placed on an OS or Data Disk (or external storage like Blob Storage), never the Temporary Disk.

### 3.2 Disk Performance Tiers

| Disk Type                       | Underlying Hardware        | Performance Characteristics                                                                    | Typical Use                                                                                                  |
| ------------------------------- | -------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| **Standard HDD**                | Magnetic/HDD-class         | Lowest cost, lowest and least consistent performance                                           | Backup/infrequent-access data, dev/test, cost-sensitive non-critical workloads                               |
| **Standard SSD**                | SSD-class                  | Better consistency and latency than Standard HDD, moderate cost                                | Web servers, lightly-used application servers, dev/test needing better consistency than HDD                  |
| **Premium SSD**                 | High-performance SSD-class | High, consistent IOPS and throughput, low latency                                              | Production databases, I/O-intensive production workloads                                                     |
| **Ultra Disk / Premium SSD v2** | Highest-performance tier   | Independently configurable IOPS and throughput (not fixed purely by disk size), lowest latency | The most demanding, latency-sensitive production workloads (large-scale databases, SAP HANA-class workloads) |

⚠️ Exact tier names (particularly around newer "v2"/"Ultra" style offerings), their precise performance characteristics, and independent IOPS/throughput configurability details evolve over time — verify current tier names and specifications against official documentation before making disk-type decisions for a specific production workload.

💡 **Tip:** A common and important nuance: for several standard disk tiers, disk performance (maximum IOPS and throughput) scales with disk **size**, not purely with an independently-chosen performance parameter — meaning a small disk with a light capacity requirement might still need to be provisioned larger than strictly necessary purely to unlock the IOPS/throughput a workload actually needs, an important and sometimes counterintuitive sizing consideration. The newer Ultra Disk/Premium SSD v2 tiers specifically address this by allowing IOPS and throughput to be configured independently of disk size.

### 3.3 Disk Caching

Managed Disks support configurable **host caching** (ReadOnly, ReadWrite, or None), which uses the VM host's own cache to improve read (and optionally write) performance for the disk — appropriate caching mode depends on the workload's actual access pattern (e.g., ReadOnly caching benefits read-heavy workloads but can be inappropriate for certain database workloads that manage their own caching and consistency guarantees at the application layer, where the disk-level cache could interfere with expected write-durability semantics) — the specific correct caching configuration for a given database or application workload should be verified against that specific software's own official guidance rather than assumed generically.

### 3.4 Disk Encryption

Managed Disks are encrypted at rest by default using **Server-Side Encryption (SSE)** with Microsoft-managed keys, with the option to instead use **customer-managed keys** (stored in Azure Key Vault, Section 56) for organizations requiring direct control over the encryption key lifecycle — this encryption-at-rest topic connects to the broader security/compliance discussion in Part 11.

## 4. Architecture Diagram

```
Virtual Machine "vm-web-01"
 ├── OS Disk (Premium SSD, 128 GB)
 │      — created from image at VM provisioning, contains the guest OS
 │
 ├── Data Disk 1 (Premium SSD, 512 GB)
 │      — application data, attached/detachable independently of VM lifecycle
 │
 ├── Data Disk 2 (Standard SSD, 256 GB)
 │      — secondary/less-critical data, different performance tier than Data Disk 1
 │
 └── Temporary Disk (local, non-durable)
        — scratch space only; NOT for data requiring persistence
```

## 5. Configuration & Hands-On Example

**Creating and attaching a new data disk to an existing VM:**

```bash
az disk create \
  --resource-group rg-myapp-prod \
  --name disk-webapp-data-01 \
  --size-gb 512 \
  --sku Premium_LRS

az vm disk attach \
  --resource-group rg-myapp-prod \
  --vm-name vm-web-01 \
  --name disk-webapp-data-01
```

- **Purpose:** Creates an independent Managed Disk resource (Premium SSD performance, locally redundant), then attaches it to an existing running VM as an additional data disk — demonstrating that data disks can be added without recreating the VM.
- **Important arguments explained individually:**
  - `--sku` — combines the performance tier and redundancy option (`Premium_LRS` = Premium SSD, Locally Redundant Storage — disk-level redundancy options are conceptually related to, but configured independently from, the Storage Account-level redundancy options covered in Section 20).
  - `--size-gb` — as discussed in Section 18.3.2, this size can implicitly affect available IOPS/throughput on certain disk tiers, not just storage capacity — chosen deliberately with performance requirements in mind, not purely capacity requirements.
- **Common error:** Attaching a disk to a VM that has already reached its maximum data disk count (a limit determined by the VM's specific size/series, Section 11.4) fails — resolved by choosing a larger VM size supporting more attached disks, or consolidating data onto fewer, larger disks.

**Resizing an existing disk (requires VM deallocation for most disk types):**

```bash
az vm deallocate --resource-group rg-myapp-prod --name vm-web-01
az disk update --resource-group rg-myapp-prod --name disk-webapp-data-01 --size-gb 1024
az vm start --resource-group rg-myapp-prod --name vm-web-01
```

- **Purpose:** Demonstrates the standard disk-resize workflow — most disk resizing operations require the VM to be deallocated first, meaning brief planned downtime is a real operational consideration when resizing production disks (⚠️ verify current documentation for whether specific scenarios support online resize without deallocation, since platform capabilities in this area have evolved and may continue to).

## 6. Production & Enterprise Usage

Enterprises separate OS disks from data disks deliberately (rather than storing application data on the OS disk) to allow independent lifecycle management — an OS disk might be replaced entirely as part of an image update, while data disks persist independently across that kind of change — and to allow choosing different performance tiers appropriate to each disk's actual access pattern (e.g., a lower-cost tier for the OS disk, a high-performance tier specifically for a database's data disk). Production database workloads on IaaS VMs (rather than PaaS database services like Azure SQL Database, Section 29) typically require Premium SSD or Ultra Disk tiers with carefully-tuned caching configuration specific to the database engine's own documented best practices, since database performance is frequently disk-I/O-bound in practice.

## 7. Security Considerations

- Encryption at rest (Section 18.3.4) is enabled by default; customer-managed keys should be considered for workloads with specific compliance requirements mandating direct control over encryption key lifecycle and rotation.
- Managed Disks can be configured with network access restrictions (Private Endpoints for disk access operations, relevant primarily to disk import/export/snapshot scenarios) to limit exposure beyond the attached VM's own access.

## 8. Performance Considerations

As emphasized in Section 18.3.2 and 18.3.3, disk performance is a function of tier, size (for certain tiers), and caching configuration together — a common troubleshooting mistake is addressing perceived "slow disk" performance purely by choosing a higher-cost tier without first verifying whether size-driven IOPS/throughput limits or an inappropriate caching configuration were the actual bottleneck, potentially spending more than necessary without addressing the real constraint.

## 9. Monitoring

Disk-level metrics (IOPS consumed vs. provisioned limit, throughput consumed vs. provisioned limit, queue depth) are available through Azure Monitor (Part 10) and are the correct diagnostic starting point for any suspected disk-performance issue, before assuming a tier or size change is necessary.

## 10. Troubleshooting

| Symptom                                                                           | Likely Cause                                                                                                                               | Fix                                                                                                                                                                     |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Application data lost after a VM deallocation/restart                             | Data was written to the Temporary Disk rather than an OS or Data Disk                                                                      | Reconfigure the application to write persistent data only to OS/Data Disks; treat Temporary Disk as non-durable scratch space only                                      |
| Disk performance plateaus well below expectations despite a "fast" tier selection | Disk size too small to unlock the tier's higher IOPS/throughput limits (size-dependent scaling), or caching misconfigured for the workload | Review documented IOPS/throughput limits for the specific size and tier combination in use; verify caching configuration matches the workload's documented requirements |
| Cannot attach an additional data disk to a VM                                     | VM has reached the maximum data disk count for its current size                                                                            | Choose a larger VM size supporting more disks, or consolidate existing data onto fewer, larger disks                                                                    |

## 11. Interview Questions — Section 18

### 🎯 Beginner

**Q: What is the difference between a Data Disk and a Temporary Disk on an Azure VM?**

_Model answer:_ A Data Disk is a persistent Managed Disk resource, independent of the VM's lifecycle, used for application data that must survive VM restarts, deallocation, or host migration. A Temporary Disk is local, non-durable scratch storage physically tied to the VM's specific underlying host — its contents can be lost on events like deallocation or host migration, so it should only be used for genuinely disposable scratch data like page files or temp files, never for data requiring persistence.

_What the interviewer is probing:_ awareness of the Temporary Disk's non-durability, since misunderstanding this is a real and consequential real-world mistake that leads to unexpected data loss.

### 🎯 Senior

**Q: A production database VM is experiencing disk performance issues under load. Walk through how you'd diagnose and address this.**

_Model answer:_ I'd start by checking Azure Monitor disk metrics for the data disk specifically — comparing actual consumed IOPS and throughput against the disk's provisioned limits for its current size and tier, to determine whether the disk is genuinely being throttled at its configured ceiling, rather than assuming a tier upgrade is needed without evidence. If the disk is indeed hitting its provisioned limits, I'd consider whether the current tier's size-dependent IOPS/throughput scaling means a larger disk (even with excess capacity beyond what's strictly needed) would unlock sufficient performance more cost-effectively than jumping to Ultra Disk, or whether the workload's demands genuinely warrant Ultra Disk/Premium SSD v2 for independently configurable IOPS and throughput. I'd also verify the disk's caching configuration matches the database engine's own documented best practices, since an inappropriate caching mode can itself be a meaningful bottleneck independent of the underlying disk tier. Finally, I'd confirm the data disk is properly separated from the OS disk (not sharing I/O contention with OS-level activity), and would check whether the VM size itself imposes a disk throughput ceiling independent of the disk's own provisioned limits, since VM-level and disk-level limits both apply and the lower of the two governs actual achievable performance.

_What the interviewer is probing:_ a methodical, metrics-driven diagnostic approach rather than jumping straight to "upgrade the tier" — and awareness that VM-level and disk-level throughput limits are both real, independent constraints that must each be checked.

## 12. Common Misconceptions

- **"The Temporary Disk is just a smaller, cheaper regular disk."** False and risky — it's fundamentally non-durable, a categorically different guarantee than any Managed Disk tier, regardless of cost or size.
- **"A higher-cost disk tier always fixes performance problems."** Not necessarily — size-dependent IOPS/throughput scaling, caching misconfiguration, or VM-level throughput ceilings can all be the actual bottleneck independent of the disk tier chosen; diagnosing the actual constraint (Section 18.11) should precede a tier upgrade decision.

## 13. Key Takeaways

- 🔑 Managed Disks are independent ARM resources abstracting away underlying storage account management, distinguishing OS Disks, Data Disks, and non-durable Temporary Disks.
- 🔑 Never store data requiring persistence on the Temporary Disk — it can be lost on deallocation or host migration events.
- 🔑 Disk performance depends on tier, and for several tiers, also on size — smaller disks on size-scaling tiers may not unlock the IOPS/throughput a workload needs even at a "fast" tier.
- 🔑 Ultra Disk/Premium SSD v2 tiers allow independently configurable IOPS and throughput, decoupled from disk size, for the most demanding workloads.
- 🔑 Disk-performance troubleshooting should start with actual consumed-vs-provisioned metrics, checking both disk-level and VM-level throughput ceilings, before assuming a tier upgrade is the correct fix.

## 14. Disk Snapshots and Incremental Snapshots

### 14.1 Why This Extends Beyond Backup (Section 11.15.2)

Section 11.15.2 covered **Azure Backup** — scheduled, policy-driven, application-consistent VM backups. This subsection covers a related but distinct, disk-level mechanism: **manually or ad hoc-triggered point-in-time copies of an individual Managed Disk**, useful for scenarios narrower than a full VM backup — such as capturing a disk's state immediately before a risky change, or efficiently creating new disks from a known-good state — without necessarily invoking the full VM Backup policy/vault machinery.

### 14.2 Disk Snapshots

**Definition:** A **Snapshot** is a full, point-in-time, read-only copy of a Managed Disk, itself stored as a new (billable) disk-like resource, independent of the source disk's own lifecycle — deleting or modifying the source disk afterward does not affect a previously taken snapshot.

**Common use cases:**

- **Pre-change safety copy** — taking a snapshot immediately before a risky operation (an OS upgrade, a major application deployment, a schema migration on a VM-hosted database) provides a fast, disk-level rollback point distinct from a full VM backup/restore cycle.
- **Disk cloning / environment replication** — creating a new disk from a snapshot is a fast way to stand up an identical copy of a disk's content — for example, cloning a production disk's data into a new disk attached to a troubleshooting or staging VM, without disturbing the original.
- **Cross-region disk copy** — snapshots can be copied to a different region, providing a disk-level mechanism to seed disaster-recovery infrastructure or migrate a disk's content, complementary to (and more granular/manual than) the VM-level Azure Site Recovery replication introduced in Section 11.15.3 and covered fully in Section 62.

### 14.3 Incremental Snapshots

**Definition:** An **Incremental Snapshot** captures only the data that has changed since the _previous_ snapshot of the same disk, rather than a full copy each time — subsequent snapshots in an incremental chain are therefore significantly smaller and faster to create and cheaper to store than repeated full snapshots, while each incremental snapshot still represents a complete, independently restorable point-in-time state (the platform manages the underlying chain transparently — restoring from any single incremental snapshot doesn't require the customer to manually reconstruct it from the chain).

**Why this matters operationally:** For workloads needing frequent, recurring disk-level point-in-time copies (rather than a one-off pre-change safety snapshot), incremental snapshots make a regular snapshot cadence (e.g., daily) practical and cost-effective — a full-snapshot-every-day approach for a large disk would be both slow and expensive at scale, while incremental snapshots scale with the _rate of change_, not the disk's total size, after the initial full snapshot in the chain.

⚠️ Exact incremental snapshot billing mechanics, chain-management details, and current default behavior (whether incremental is now the standard/default snapshot type rather than an opt-in choice) should be verified against current official documentation, since Azure has evolved snapshot defaults and cost models over time.

### 14.4 Snapshots vs. Azure Backup vs. Azure Site Recovery — Choosing the Right Tool

| Mechanism                                             | Scope                                                            | Trigger                                                                 | Best Fit                                                                                                                                   |
| ----------------------------------------------------- | ---------------------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **Disk Snapshot / Incremental Snapshot**              | Single disk                                                      | Manual/ad hoc, or scripted on a custom schedule                         | Pre-change safety copies, disk cloning, lightweight custom recovery-point strategies outside the formal Azure Backup policy framework      |
| **Azure Backup (Section 11.15.2)**                    | Whole VM (OS disk + data disks together, application-consistent) | Policy-driven, scheduled, centrally managed via Recovery Services Vault | Standard production VM data-protection baseline — the default recommended mechanism for routine, policy-governed recovery point management |
| **Azure Site Recovery (Section 11.15.3, Section 62)** | Whole VM, replicated continuously to a different region          | Continuous replication                                                  | Regional disaster recovery — recovering the entire workload in a different region, not disk-level point-in-time recovery within a region   |

💡 **Tip:** Snapshots are a _complementary_, more granular/manual tool alongside Azure Backup, not a replacement for it — production VMs should still have an Azure Backup policy as their baseline data-protection mechanism (Section 11.15.2), with ad hoc snapshots used for the specific, narrower scenarios (pre-change safety, cloning) snapshots are particularly well suited to.

### 14.5 Configuration Example

```bash
az snapshot create \
  --resource-group rg-myapp-prod \
  --name snap-disk-webapp-data-pre-upgrade \
  --source disk-webapp-data-01 \
  --incremental true
```

- **Purpose:** Creates an incremental snapshot of the data disk from Section 18.5's example, immediately before a planned risky change (per the pre-change safety pattern, Section 18.14.2), following the general incremental-snapshot cost/performance benefit described in Section 18.14.3.
- **Important arguments explained individually:**
  - `--incremental true` — explicitly requests an incremental snapshot rather than a full snapshot; ⚠️ verify current default behavior, since this may already be the platform default depending on current documentation.
- **Common error:** Attempting to create a disk from a snapshot without sufficient quota/capacity in the target resource group or region — snapshots and disks created from them still consume standard disk-resource quota.

### 14.6 Interview Questions — Section 18.14

**🎯 Intermediate**
**Q: What's the advantage of an incremental snapshot over a full snapshot for a disk that needs frequent point-in-time copies?**

_Model answer:_ An incremental snapshot only captures the data changed since the previous snapshot in the chain, rather than copying the entire disk again each time, making subsequent snapshots significantly faster and cheaper to create and store, while each one still represents a complete, independently restorable point-in-time state. For a disk needing a recurring snapshot cadence (e.g., daily), this makes the ongoing cost and time scale with the rate of change rather than the disk's total size, which is what makes a frequent snapshot schedule practical at scale.

_What the interviewer is probing:_ understanding of the specific cost/performance mechanism that makes incremental snapshots viable for recurring use, versus assuming all snapshots are equally expensive full copies.

**🎯 Senior**
**Q: A team wants to take a snapshot before every production deployment as a safety net, in addition to their existing Azure Backup policy. Is this redundant?**

_Model answer:_ Not necessarily redundant — Azure Backup provides the standard, policy-driven, application-consistent baseline protection for the whole VM on a regular schedule, but a pre-deployment snapshot serves a different, complementary purpose: an immediate, deployment-triggered recovery point precisely aligned with a specific risky change, which a fixed backup schedule (e.g., nightly) might not align with as tightly — if a deployment happens mid-day and something goes wrong, the most recent Azure Backup recovery point could be many hours stale, whereas a pre-deployment snapshot captures the exact moment just before the change. I'd recommend keeping both: Azure Backup as the durable, policy-governed baseline, and pre-deployment snapshots as a lightweight, deployment-triggered supplementary safety net for the specific higher-risk moments around production changes — the two aren't redundant, they cover different recovery-point timing needs.

_What the interviewer is probing:_ whether the candidate can articulate the genuine complementary value of a more granular, event-triggered mechanism alongside a broader scheduled one, rather than assuming any two data-protection mechanisms covering "the same disk" must be redundant.

### 14.7 Key Takeaways — Section 18.14

- 🔑 Disk Snapshots provide manual/ad hoc, single-disk point-in-time copies, complementary to (not a replacement for) Azure Backup's policy-driven, whole-VM protection.
- 🔑 Incremental Snapshots capture only changed data since the prior snapshot, making frequent recurring snapshot schedules practical and cost-effective at scale.
- 🔑 Snapshots are well suited to pre-change safety copies and disk cloning; Azure Backup remains the recommended baseline for routine production VM data protection; Azure Site Recovery addresses full regional DR — the three are complementary layers, not competing alternatives.

## 15. Related Concepts (Next Up)

Section 19 covers **Azure Files and File Sync** — the traditional network file share service (introduced by name in Section 16.3.2) that, unlike Managed Disks (attached to one VM at a time), supports concurrent access from multiple clients simultaneously via SMB/NFS protocols, filling a genuinely different storage need than the block-storage-per-VM model just covered.
