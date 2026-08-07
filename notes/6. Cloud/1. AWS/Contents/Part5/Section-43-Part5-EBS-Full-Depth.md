# Part 5 - Section 5 - Amazon EBS: Elastic Block Store, Full Depth

AWS Zero-to-Enterprise Knowledge Base - Part 5: Storage

---

## 1. Definition

Plain-language: EBS gives your EC2 instances persistent, network-attached disks that behave just like a local hard drive from the OS's perspective, but can be detached, reattached, resized, and backed up independently of any specific instance.

Precise: Amazon Elastic Block Store (EBS) provides persistent, network-attached block storage volumes for EC2 instances, offering multiple volume types optimized for different performance profiles, snapshot-based backup to S3, and encryption integrated with KMS.

---

## 2. Why It Exists

- EBS gives EC2 persistence independent of the physical host, enabling stop/start lifecycle, resizing, and cross-instance reattachment that instance store cannot provide.
- Block storage is a genuinely different paradigm from S3's object storage - addressed in fixed-size blocks, mountable as a filesystem, supporting in-place edits and random byte/block-level access - exactly the POSIX-like semantics S3 gave up for scale. EBS is for workloads genuinely needing that filesystem behavior - databases, boot volumes, low-latency random read/write.

---

## 3. EBS Volume Types

### 3.1 SSD-Backed - IOPS-Intensive

| Type                                           | Use case                                                              | Key characteristic                                                                     |
| ---------------------------------------------- | --------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| gp3 (General Purpose SSD)                      | Default for most workloads - boot volumes, dev/test, small-medium DBs | IOPS and throughput independently configurable, decoupled from size                    |
| gp2 (older generation)                         | Legacy, superseded by gp3                                             | IOPS scales WITH volume size (3 IOPS/GB, burst capability) - less flexible             |
| io2 / io2 Block Express (Provisioned IOPS SSD) | I/O-intensive databases (large relational, SAP HANA)                  | Highest durability (99.999%); IOPS provisioned independently, up to very high ceilings |

Key idea: gp2's IOPS derives from size (like T-family CPU credits in spirit); gp3 decouples IOPS/throughput from size entirely - provision a small volume with high IOPS without over-provisioning capacity, generally at lower cost than equivalent gp2. This is why gp3 is the current default.

### 3.2 HDD-Backed - Throughput-Intensive, Sequential

| Type                           | Use case                               | Key characteristic                                    |
| ------------------------------ | -------------------------------------- | ----------------------------------------------------- |
| st1 (Throughput Optimized HDD) | Big data, warehouses, log processing   | Cannot be a boot volume; optimized for MB/s not IOPS  |
| sc1 (Cold HDD)                 | Infrequently accessed, lowest-cost EBS | Lowest cost/performance; also cannot be a boot volume |

Frequently tested: st1 and sc1 CANNOT be boot volumes - only SSD-backed types can boot an instance. A hard constraint, not a recommendation.

---

## 4. EBS Snapshots - Full Mechanics

### 4.1 What a Snapshot Is

- Point-in-time, incremental backup stored durably in S3 (not directly browsable) - the mechanism behind AMI creation.
- First snapshot copies all used blocks; every subsequent snapshot copies only changed blocks since the previous one - but each snapshot remains a complete, independently restorable point-in-time view. EBS tracks block references across the full history internally; deleting an earlier snapshot doesn't break later ones.

### 4.2 Snapshot Consistency

- A snapshot of an actively-written volume captures whatever was on disk at that instant - can be crash-consistent but not application-consistent if data was in memory buffers not yet flushed (like pulling power on a running system).
- For genuinely application-consistent backups, briefly pause writes/flush buffers, or use a database-native backup mechanism, rather than assuming a snapshot of a live database is automatically clean.

### 4.3 Cross-Region and Cross-Account Snapshot Copying

- Snapshots can be copied to other Regions (DR patterns, similar to S3 CRR but for block storage) and shared with other accounts (same permission pattern as AMIs).
- Identical KMS cross-account gotcha applies: if encrypted with a CMK, sharing also requires sharing key-usage permission via the KMS key policy.

### 4.4 Fast Snapshot Restore

- By default, a newly restored volume may have a brief warm-up period (lazy-load from S3 on first block access). Fast Snapshot Restore (extra cost) pre-warms so restored volumes deliver full performance immediately - relevant for DR failover where restore-time performance matters.

---

## 5. EBS Encryption

- Uses the same KMS/envelope-encryption mechanics as Part 2 - an encrypted volume's data, snapshots, and any volume created from those snapshots are all automatically encrypted, propagating through the entire volume-to-snapshot-to-new-volume lineage.
- Encryption by default - account/Region-level setting automatically encrypting every new volume/snapshot, removing the need to remember per-resource.
- You CANNOT encrypt an existing unencrypted volume in place - the only path: snapshot it, copy the snapshot WITH encryption enabled, create a new volume from the encrypted copy, swap it in.

---

## 6. EBS Multi-Attach

- Certain io1/io2 volumes support Multi-Attach - simultaneous attachment to multiple instances in the same AZ - but EBS provides NO file-locking/write-coordination. The application (a clustered filesystem/database designed for this) must manage concurrent writes itself, or corruption results.
- A narrow, specialized capability for cluster-aware applications explicitly designed for shared block-storage access - not a general "share a disk" feature.

---

## 7. EBS Elastic Volumes - Live Resizing

- Volumes can be modified live - size increase, type change (gp2->gp3), IOPS/throughput adjustment - without detaching or stopping the instance.
- Caveat: the volume can grow live, but the FILESYSTEM on top typically needs separate extension (an OS-level operation, e.g., resize2fs on Linux) to actually use the new space.

---

## 8. Production & Enterprise Usage

- gp3 as default recommendation for general-purpose workloads; io2/io2 Block Express reserved for demanding, consistent-IOPS databases.
- Automated snapshot lifecycle via Amazon Data Lifecycle Manager (DLM) - automates scheduled creation and retention/deletion, extending S3's lifecycle-policy philosophy to EBS snapshots.
- Cross-Region snapshot copying as a foundational DR building block, paired with Route 53 Failover and standby-infrastructure patterns.
- Encryption by default enabled account-wide, often enforced via SCP or Config rule denying unencrypted volume creation.

---

## 9. Security Considerations

- The KMS key-policy cross-account sharing gotcha is the single most common practical EBS/KMS troubleshooting scenario - identical to the AMI and S3 patterns.
- Snapshots are only as secure as their sharing configuration - a mistakenly-public snapshot exposes the entire volume's data.
- Multi-Attach's lack of built-in coordination is a data-integrity risk, not just a performance consideration, when used without a genuinely cluster-aware application.

---

## 10. Performance Considerations

- gp3's decoupled IOPS/throughput configuration is the primary modern performance-tuning lever.
- Instance-side EBS bandwidth limits remain the actual bottleneck even with a well-provisioned volume - check both sides.
- Fast Snapshot Restore matters for performance-sensitive restore scenarios (tight RTO DR) where lazy-load latency is unacceptable.

---

## 11. Troubleshooting

| Symptom                                                         | Cause                                                                                | Fix                                                                                 |
| --------------------------------------------------------------- | ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------- |
| Restored volume shows degraded performance briefly              | Default lazy-loading from S3 on first block access                                   | Expected; use Fast Snapshot Restore if immediate full performance is required       |
| Cross-account snapshot sharing fails despite permission granted | Underlying KMS key policy doesn't permit the target account                          | Update the KMS key policy, not just the snapshot-sharing permission                 |
| Increased volume size, OS still shows old capacity              | Filesystem wasn't extended after volume resize                                       | Run the appropriate OS-level filesystem-extension command                           |
| DB performance degrades after a "successful" snapshot backup    | Snapshot taken without pausing writes - crash-consistent, not application-consistent | Use a DB-native backup mechanism or coordinate write-pausing around snapshot timing |
| Multi-Attach volume shows data corruption                       | App isn't genuinely cluster-aware                                                    | Only use Multi-Attach with software designed for shared block-storage coordination  |

---

## 12. Best Practices & Anti-Patterns

Best practices: default to gp3 for general-purpose workloads, reserve io2/io2 Block Express for demanding databases; enable encryption by default account/Region-wide; automate snapshot lifecycle via DLM; copy snapshots cross-Region for DR; extend the filesystem after resizing a volume.

Anti-patterns: using st1/sc1 as a boot volume; assuming a live DB snapshot is automatically application-consistent; using Multi-Attach without a cluster-aware app; forgetting the KMS key-policy sharing requirement for cross-account encrypted snapshots.

---

## 13. Common Misconceptions

- "gp2 and gp3 are basically the same." False - gp3 decouples IOPS/throughput from size entirely, a real architectural difference.
- "Any EBS volume type can be a boot volume." False - st1/sc1 cannot; only SSD-backed types can.
- "Deleting an earlier snapshot breaks later ones' restorability." False - each snapshot is independently restorable via internal block-reference tracking.
- "You can just enable encryption on an existing unencrypted volume." False - requires snapshot-copy-with-encryption then a new volume from that copy.

---

## 14. Interview Questions (with model answers)

Beginner - Difference between gp2 and gp3? gp2's IOPS derives from size (~3 IOPS/GB, burst credits). gp3 decouples IOPS/throughput from size entirely - provision a small volume with high IOPS without over-provisioning capacity, generally cheaper than equivalent gp2. Why gp3 is the current default.

Beginner - Can st1 or sc1 be a boot volume? No - HDD-backed throughput-optimized types, neither can boot an instance; only SSD-backed types (gp2/gp3/io1/io2) can. A hard architectural constraint.

Intermediate - Deleting an early snapshot in an incremental chain - can you still restore from a later one? Yes - despite being incremental, EBS tracks which blocks are still referenced across the entire snapshot history. Each snapshot remains complete and independently restorable regardless of earlier snapshots' existence; deleting one just lets AWS clean up blocks only referenced by that snapshot.

Intermediate - Why might a snapshot backup of a running database not be sufficient? Captures whatever was physically on disk at that instant - crash-consistent but not necessarily application-consistent if data was in unflushed memory buffers. For reliable transactionally-clean restore, use the DB's native backup mechanism or coordinate pausing writes/flushing buffers around snapshot timing.

Senior - Design EBS strategy for an I/O-intensive self-managed relational DB needing high sustained IOPS, cross-Region DR, and compliance encryption? io2 Block Express for high consistent IOPS beyond gp3's ceiling, provisioned independently of size to match demonstrated workload needs. Enable encryption with a customer-managed KMS key (not AWS-managed default) for independent access control/audit trail matching compliance. Automate snapshot creation via DLM matching required RPO, copy cross-Region with matching encryption and destination-Region KMS key policy granting the DR-restore principal decrypt permissions (a commonly missed step). Coordinate snapshot timing with DB quiescing or native backup tooling for application-consistent backups. Evaluate Fast Snapshot Restore on DR-region snapshots if RTO requires avoiding the lazy-load warm-up.

---

## Key Takeaways

1. EBS is block storage for filesystem-semantics workloads - the paradigm counterpart to S3's object storage.
2. gp3 decouples IOPS/throughput from volume size, the modern default over gp2; io2/io2 Block Express for the most demanding databases; st1/sc1 for sequential throughput workloads that cannot be boot volumes.
3. Snapshots are incremental but each independently restorable - deleting an early one doesn't break later ones.
4. Encryption propagates through the volume-to-snapshot-to-new-volume lineage but cannot be applied in-place to an existing unencrypted volume.
5. The KMS key-policy cross-account sharing gotcha is identical across EBS snapshots, AMIs, and S3 - one pattern tested repeatedly across this course.

## Related Concepts (forward links)

- Amazon EFS - shared, POSIX-compliant file storage, the third storage paradigm -> [§44](./Section-44-Part5-EFS-Elastic-File-System.md)
- AWS Backup unifying EBS/EFS/RDS backup management -> [§47](./Section-47-Part5-Backup-Strategies-DR-Patterns.md)
- RDS's own storage/backup mechanics building on EBS underneath -> Part 6
