# Section 12 (Part 2): Persistent Disks & Filestore

## 12.1 Definition

**Plain language:** Persistent Disks are the virtual hard drives you attach to Compute Engine VMs (block storage), and Filestore is a managed network file share (like a shared folder mounted by many machines at once).

**Precise:** **Persistent Disks (PDs)** are network-attached block storage volumes that can be attached to Compute Engine instances, offered in multiple performance tiers and either zonal (single-zone) or regional (synchronously replicated across two zones). **Filestore** is a fully managed NFS (Network File System) service providing POSIX-compliant shared file storage mountable simultaneously by many VMs or GKE pods.

## 12.2 Why It Exists / Problem It Solves

Object storage (Section 11) is not suitable for workloads needing a real filesystem with low-latency random reads/writes, POSIX semantics, or the ability to serve as a VM's boot disk. Persistent Disks solve this for single-VM (or narrowly shared) block-level access — databases, boot volumes, application data directories. Filestore solves the separate problem of **multiple compute nodes needing simultaneous, consistent, low-latency access to the same file tree** — a need block storage cannot meet, since a Persistent Disk is fundamentally designed around a small number of attaching VMs, not broad concurrent multi-writer access patterns.

## 12.3 Core Concepts

### 12.3.1 Persistent Disk Types

| Type            | Backing Media          | Performance Profile                                   | Typical Use                                                                                 |
| --------------- | ---------------------- | ----------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| **pd-standard** | HDD                    | Lowest cost, lowest IOPS, throughput scales with size | Large sequential-access data, cold storage attached to a VM                                 |
| **pd-balanced** | SSD                    | Balanced cost/performance, good default choice        | General-purpose boot disks and application volumes                                          |
| **pd-ssd**      | SSD                    | Higher, more consistent IOPS than balanced            | Databases, latency-sensitive workloads                                                      |
| **pd-extreme**  | SSD (provisioned IOPS) | IOPS provisioned independently of disk size           | Highest-performance databases (e.g., SAP HANA), demanding a specific guaranteed IOPS figure |

### 12.3.2 Zonal vs. Regional Persistent Disks

- **Zonal PD:** Lives in a single zone; if that zone fails, the disk is unavailable until the zone recovers. Lower cost, simpler, sufficient when the application layer handles redundancy (e.g., a database cluster spanning multiple VMs/zones with its own replication).
- **Regional PD:** Synchronously replicates data across two zones within the same region. If the primary zone fails, a VM in the paired zone can attach the same regional PD and continue with no data loss, since writes are acknowledged only after being durably written to both zones. This trades slightly higher write latency for zone-failure resilience at the storage layer itself, without requiring application-level replication.

> 💡 **Tip:** Regional PDs provide storage-layer HA, but the compute layer (the VM itself) still needs a strategy — e.g., a standby VM in the second zone ready to attach the regional PD on failover — to achieve full application availability.

### 12.3.3 Snapshots

A **snapshot** is an incremental, point-in-time backup of a Persistent Disk stored in Cloud Storage internally (not user-visible as a bucket). Snapshots are incremental after the first one — only changed blocks since the last snapshot are stored — making repeated snapshots storage-efficient. Snapshots can be scheduled automatically via **snapshot schedules** attached to a disk, and can be used to create new disks (including in a different region, enabling cross-region disaster recovery) or new custom images.

### 12.3.4 Filestore Tiers

| Tier                       | Capacity Range                  | Typical Use                                                                                |
| -------------------------- | ------------------------------- | ------------------------------------------------------------------------------------------ |
| **Basic HDD**              | 1 TiB – 63.9 TiB                | Cost-sensitive general file sharing, low-throughput needs                                  |
| **Basic SSD**              | 2.5 TiB – 63.9 TiB              | Higher-performance general file sharing                                                    |
| **Zonal (High Scale SSD)** | Up to hundreds of TiB           | High-performance computing, media rendering, ML training data                              |
| **Enterprise**             | Regional, multi-zone replicated | Mission-critical workloads needing regional HA and lower RPO/RTO for the file share itself |

Filestore instances are mounted over NFSv3 (or NFSv4.1 for some tiers) by Compute Engine VMs or GKE pods (via the Filestore CSI driver), giving many clients simultaneous read/write access to the same directory tree with standard POSIX file locking semantics.

## 12.4 Architecture Diagram

```
   ┌───────────────────────┐        ┌───────────────────────┐
   │  Compute Engine VM A  │        │  Compute Engine VM B  │
   │  ┌─────────────────┐  │        │  ┌─────────────────┐  │
   │  │ Zonal PD (boot) │  │        │  │ Zonal PD (boot) │  │
   │  └─────────────────┘  │        │  └─────────────────┘  │
   └───────────┬───────────┘        └───────────┬───────────┘
               │NFS mount (shared, concurrent)  │
               ▼                                ▼
        ┌─────────────────────────────────────────────┐
        │           Filestore instance                │
        │ (POSIX file tree, mounted by many clients)  │
        └─────────────────────────────────────────────┘

   ┌────────────────────────────┐
   │ Regional PD (zone A + B)   │◄── synchronous replication
   │ attached to active VM in   │
   │ zone A; standby VM in zone │
   │ B can attach on failover   │
   └────────────────────────────┘
```

## 12.5 Comparison vs. AWS EBS/EFS and Azure Managed Disks/Files

| Concept                              | GCP                                                  | AWS                                                 | Azure                                                     |
| ------------------------------------ | ---------------------------------------------------- | --------------------------------------------------- | --------------------------------------------------------- |
| Block storage                        | Persistent Disk (pd-standard/balanced/ssd/extreme)   | EBS (gp3/io2/st1/sc1)                               | Managed Disks (Standard HDD/SSD, Premium SSD, Ultra Disk) |
| Cross-zone block redundancy          | Regional Persistent Disk (sync replication, 2 zones) | No native equivalent (Multi-Attach is same-AZ only) | Zone-Redundant Storage (ZRS) for Managed Disks            |
| Provisioned IOPS independent of size | pd-extreme                                           | io2 Block Express                                   | Ultra Disk / Premium SSD v2                               |
| Managed shared file storage          | Filestore (NFS)                                      | EFS (NFS)                                           | Azure Files (SMB and NFS)                                 |
| File storage scaling model           | Provisioned capacity tiers (Basic/Zonal/Enterprise)  | Elastic, pay-per-use, no provisioning               | Provisioned or pay-as-you-go tiers                        |
| Point-in-time backup                 | Snapshots (incremental, cross-region capable)        | EBS Snapshots (incremental, cross-region copy)      | Managed Disk Snapshots / Azure Backup                     |

## 12.6 Hands-On Examples

**Create a balanced Persistent Disk (Beginner):**

```bash
gcloud compute disks create app-data-disk --size=100GB --type=pd-balanced --zone=us-central1-a
```

**Create a regional Persistent Disk (Intermediate):**

```bash
gcloud compute disks create ha-db-disk --size=200GB --type=pd-ssd \
  --region=us-central1 --replica-zones=us-central1-a,us-central1-b
```

**Purpose:** Provisions a disk synchronously replicated across two zones for storage-layer high availability.

**Create a snapshot (Beginner):**

```bash
gcloud compute snapshots create app-data-snap-1 --source-disk=app-data-disk --source-disk-zone=us-central1-a
```

**Create a Filestore instance (Intermediate):**

```bash
gcloud filestore instances create shared-nfs \
  --zone=us-central1-a --tier=BASIC_SSD --file-share=name="share1",capacity=2560GB \
  --network=name="default"
```

**Expected output (abbreviated):**

```
Waiting for [operation-...] to finish...done.
Created instance [shared-nfs].
```

## 12.7 Production & Enterprise Usage

- **Database VMs:** Self-managed databases on Compute Engine typically use pd-ssd or pd-extreme for the data directory and a separate smaller pd-balanced boot disk, following the principle of separating OS and data lifecycles.
- **Render farms / HPC / ML training:** Filestore's Zonal (High Scale SSD) tier is commonly used where hundreds of worker VMs need simultaneous, high-throughput access to the same shared dataset or scratch space.
- **DR via snapshots:** Automated snapshot schedules combined with cross-region snapshot copies underpin many Compute Engine disaster recovery designs (Section 58), letting a disk be reconstructed in a secondary region within minutes.
- **GKE persistent volumes:** Both Persistent Disks (via the Compute Engine persistent disk CSI driver) and Filestore (via the Filestore CSI driver) back PersistentVolumeClaims in GKE, covered in Section 31.

## 12.8 Common Misconceptions

- **Misconception:** "A Persistent Disk can be attached read-write to multiple VMs simultaneously by default." In reality, standard PDs are single-writer (with a narrow multi-writer mode for specific SSD types in read-only or clustered-filesystem scenarios) — genuine concurrent multi-writer access at the file level requires Filestore, not PD.
- **Misconception:** "Regional Persistent Disks alone give an application high availability." A regional PD only protects the _data_; you still need compute-layer failover logic (a standby VM ready to attach the disk in the second zone) to achieve full service availability.

## 12.9 Interview Questions

**🎯 Beginner:** _When would you choose Filestore over a Persistent Disk?_
**Model answer:** Persistent Disk is block storage attached to a single VM (or a narrow multi-attach scenario); Filestore is a managed NFS file share mountable simultaneously by many VMs or GKE pods with full POSIX semantics. Choose Filestore whenever multiple compute nodes need genuinely concurrent read-write access to the same directory tree, such as a shared content repository, render farm scratch space, or home directories across a fleet of VMs.

**🎯 Intermediate:** _What's the practical difference between pd-balanced and pd-extreme, and when do you need pd-extreme specifically?_
**Model answer:** pd-balanced offers a fixed cost/performance ratio tied to disk size, which is fine for general-purpose workloads and most databases. pd-extreme lets you provision IOPS independently of the disk's capacity, giving predictable, very high performance for demanding workloads like SAP HANA or large transactional databases where the required IOPS figure is much higher than what capacity-linked tiers would provide at a reasonable size — you only reach for pd-extreme when you have a specific, measured IOPS requirement that balanced/SSD tiers can't meet at your target disk size.

**🎯 Senior/Architect:** _Design a storage strategy for a self-managed PostgreSQL cluster requiring both storage-layer resilience and fast disaster recovery to a secondary region._
**Model answer:** I'd use a regional Persistent Disk (pd-ssd or pd-extreme depending on IOPS needs) for the primary database VM so a single zone failure doesn't cause data loss, with a standby VM in the paired zone ready to attach the same disk on failover — handling storage-layer HA. For cross-region DR, I'd rely on PostgreSQL's own streaming replication to a standby instance in the secondary region (since regional PDs don't span regions), combined with a scheduled snapshot policy on the primary disk copied to the DR region as a secondary safety net for point-in-time recovery beyond what streaming replication protects against (e.g., a logical corruption that replicates before being caught). This layers three independent protections — regional PD for zone failure, cross-region streaming replication for region failure, and cross-region snapshots for logical-corruption recovery — each addressing a different failure mode rather than relying on one mechanism to cover all of them.

## 12.10 Key Takeaways

- 🔑 Persistent Disks are block storage for VMs (pd-standard/balanced/ssd/extreme); Filestore is managed NFS for concurrent multi-client file access.
- 🔑 Regional Persistent Disks synchronously replicate across two zones for storage-layer HA, but still require a compute-layer failover strategy.
- 🔑 Snapshots are incremental, can seed disks in other regions, and underpin most Compute Engine DR strategies.
- 🔑 Filestore tiers (Basic HDD/SSD, Zonal, Enterprise) scale from cost-sensitive general sharing to HPC/ML-grade throughput and regional HA.

## 12.11 Related Concepts

Cloud Storage for object data (Section 11), Compute Engine (Section 5), GKE persistent storage via CSI drivers (Section 31), disaster recovery and multi-region architecture (Section 58), and the AWS/Azure storage comparison (Section 82) all connect directly to the block/file storage concepts here.
