# Part 5 - Section 6 - Amazon EFS: Elastic File System

AWS Zero-to-Enterprise Knowledge Base - Part 5: Storage

---

## 1. Definition

Plain-language: EFS is a shared network drive that many EC2 instances (or other compute) can mount and use at the same time, all seeing the same files, growing and shrinking automatically - like a traditional network file share, but fully managed.

Precise: Amazon Elastic File System (EFS) is a fully managed, elastic, POSIX-compliant network file system (NFS) that can be mounted simultaneously by multiple EC2 instances, containers, or Lambda functions, growing/shrinking automatically without pre-provisioned capacity.

---

## 2. Why It Exists

- EBS's Multi-Attach is narrow (io1/io2 only, single-AZ, requires application-level write coordination). Most workloads needing genuinely shared file access across many instances need something EBS wasn't designed for.
- S3 gives up POSIX semantics for scale; some applications genuinely require real filesystem behavior (legacy apps, CMS, shared config) and can't be rewritten for an object API.
- EFS fills this gap: multi-instance, multi-AZ, simultaneous, POSIX-compliant, fully managed - a distinct third paradigm alongside S3 (object) and EBS (block).

---

## 3. Core EFS Concepts

### 3.1 File System and Mount Targets

- An EFS file system is the top-level resource, accessible via mount targets - one per AZ, living in a specific subnet with an IP in that AZ.
- Instances in multiple AZs can mount the same file system simultaneously, each connecting to their own AZ's mount target - the fundamental capability neither S3 nor standard EBS provides.

### 3.2 Elastic, Pay-for-What-You-Use

No pre-provisioned capacity - EFS automatically grows/shrinks as files are added/removed, billed for actual data stored, not a provisioned allocation - a genuine contrast to EBS's provisioned-capacity model.

### 3.3 Performance Modes

- General Purpose - default, lowest-latency, for the majority of workloads.
- Max I/O - slightly higher latency, but scales to higher aggregate throughput/operations across many instances - for highly parallelized workloads (big data, media processing).

### 3.4 Throughput Modes

- Bursting Throughput - scales with amount of data stored (like gp2's size-tied model), burst credits for spikes.
- Provisioned Throughput - specified independently of data stored - for high throughput on relatively small datasets.
- Elastic Throughput - automatically scales based on actual activity, no provisioning needed - the most hands-off option, parallel to gp3's decoupling philosophy taken further.

---

## 4. EFS Storage Classes - Lifecycle Management

- EFS Standard - default, immediate-access tier.
- EFS Standard-IA and EFS One Zone/One Zone-IA - parallel to S3's classes: IA trades a retrieval fee for lower storage cost; One Zone stores in only one AZ (cheaper, vulnerable to that AZ's loss).
- EFS Lifecycle Management - automatically transitions files based on actual observed last-access time (more like S3 Intelligent-Tiering's behavioral approach than a fixed-day rule) - e.g., "move to IA after 30 days without access," handled automatically per-file.

---

## 5. EFS Access Points

- An Access Point provides an application-specific entry point with an enforced POSIX user/group identity and a specific root directory within the file system - different applications/tenants can share one file system while each seeing only their own portion, with their own enforced permissions.
- Rather than a separate file system per app/tenant, or trusting apps to self-scope, Access Points let EFS itself enforce the boundary - least-privilege at the filesystem-mount level.

---

## 6. EFS Security

- Encryption at rest uses KMS, same envelope-encryption mechanics - like EBS, CANNOT be enabled on an existing unencrypted file system in place; requires creating a new encrypted file system and migrating data (e.g., via AWS DataSync).
- Encryption in transit uses TLS for the NFS connection, configurable at mount time - important, sometimes-overlooked setting.
- Multi-layered access control: POSIX file permissions (within the filesystem), IAM policies (mount/access at the AWS API level), security groups (network-level access to mount targets) - genuine defense-in-depth for file storage.

---

## 7. EFS vs EBS vs S3 - Decision Framework

|                      | S3                                         | EBS                                              | EFS                                          |
| -------------------- | ------------------------------------------ | ------------------------------------------------ | -------------------------------------------- |
| Paradigm             | Object storage                             | Block storage                                    | File storage (NFS)                           |
| Access               | API (HTTP), no mounting                    | Mounted by one instance (or narrow Multi-Attach) | Mounted by many instances/AZs simultaneously |
| Filesystem semantics | None (flat key-value)                      | Full (whatever you format it with)               | Full (POSIX NFS)                             |
| Capacity planning    | None needed                                | Provisioned size upfront (resizable)             | Fully elastic, no provisioning               |
| Best for             | Massive-scale API-driven unstructured data | Single-instance databases, boot volumes          | Shared file access across many instances/AZs |

Clean summary: S3 for API-driven object access at scale with no filesystem semantics. EBS for a single instance's (or narrow multi-attach cluster's) block storage. EFS for genuine multi-instance, multi-AZ, simultaneous POSIX file sharing with zero capacity planning. Deciding question: does this need to be mounted, and by how many instances at once?

---

## 8. Production & Enterprise Usage

- Shared content/configuration across a web-tier ASG - every instance mounting the same EFS for shared static content/uploads/config without custom sync mechanisms - common for legacy/lift-and-shift apps.
- Lambda functions mounting EFS - for workloads needing a large shared dataset that wouldn't fit in /tmp, or genuinely persistent shared state across invocations.
- AWS DataSync for migration/synchronization between on-prem file servers and EFS, or between EFS file systems.
- EFS Lifecycle Management as the default cost-optimization setting for most production deployments.

---

## 9. Security Considerations

- Multi-layered access model means a misconfiguration at any one layer (overly permissive POSIX perms, broad SG, broad IAM policy) can independently create unintended access - the recurring "check every layer" discipline, now with POSIX permissions as a file-storage-specific consideration.
- Access Points as a genuine security boundary for multi-tenant sharing - enforcing scoping at the mount level rather than trusting apps to self-restrict.

---

## 10. Performance Considerations

- Performance mode and throughput mode are independent decisions - combine General Purpose/Max I/O with Bursting/Provisioned/Elastic based on actual workload needs.
- Elastic Throughput removes the need to predict/provision a specific level - the "automate the decision instead of guessing" pattern seen throughout Part 5.

---

## 11. Troubleshooting

| Symptom                                                  | Cause                                             | Fix                                                                               |
| -------------------------------------------------------- | ------------------------------------------------- | --------------------------------------------------------------------------------- |
| Instance in one AZ can mount, another AZ cannot          | No mount target in that AZ                        | Create a mount target in every AZ needing to mount                                |
| Multiple apps sharing one EFS see each other's files     | No Access Points configured                       | Configure Access Points scoping each app to its own root directory/POSIX identity |
| Need encryption on an existing unencrypted file system   | Cannot toggle encryption on existing file systems | Create a new encrypted file system, migrate data via DataSync                     |
| Expected throughput not achieved despite low data volume | Using Bursting Throughput, tied to data stored    | Switch to Provisioned or Elastic Throughput                                       |

---

## 12. Best Practices & Anti-Patterns

Best practices: create a mount target in every AZ needing access; use Access Points for multi-tenant sharing; enable Lifecycle Management for cost optimization; enable encryption at creation time; choose performance/throughput modes based on actual workload needs.

Anti-patterns: deploying only one AZ's mount target for a multi-AZ workload; sharing one file system across tenants without Access Points; assuming Bursting Throughput suffices for high-throughput/low-storage workloads; creating unencrypted with a "encrypt it later" plan.

---

## 13. Common Misconceptions

- "EFS is just EBS that can attach to multiple instances." False - a genuinely different paradigm (managed NFS, POSIX-compliant, elastic), not "EBS Multi-Attach without restrictions."
- "You need to provision EFS capacity like EBS." False - fully elastic, no upfront size.
- "EFS encryption can be enabled on an existing file system anytime." False - requires a new file system and migration.
- "One EFS mounted by multiple apps automatically isolates their data." False without Access Points - a shared mount gives full visibility by default.

---

## 14. Interview Questions (with model answers)

Beginner - What problem does EFS solve that EBS doesn't? Genuine simultaneous multi-instance, multi-AZ file access with POSIX semantics and no capacity planning. EBS is fundamentally single-instance, with only narrow Multi-Attach (certain types, single AZ, app-coordinated writes). EFS is right when many instances need genuinely shared file access without building coordination themselves.

Beginner - Do you specify a size when creating EFS? No - fully elastic, grows/shrinks automatically, billed for actual data stored - a contrast to EBS's upfront-size (though resizable) model.

Intermediate - How would you let three apps share one EFS file system while keeping data isolated? Use EFS Access Points - one per app, each enforcing a specific root directory and POSIX identity. Each app mounts via its own access point, seeing only its portion, with EFS itself enforcing the boundary rather than relying on app self-restriction.

Intermediate - Workload needs high predictable throughput on a small dataset - which throughput mode? Not Bursting (ties baseline throughput to data stored - low for small datasets). Provisioned Throughput, specifying required throughput independently of data stored. Elastic Throughput also worth considering if demand varies and manual provisioning isn't wanted.

Senior - Design shared storage for a legacy CMS lifted-and-shifted onto a 3-AZ ASG, needing all instances to see uploads immediately, with required encryption? EFS is the right paradigm given multi-AZ immediate visibility and legacy filesystem expectations. Create with encryption at creation time (can't add later). Mount target in each of the three AZs; include mount config in the Launch Template so every ASG-launched instance auto-mounts. General Purpose performance mode + Elastic Throughput to start (latency-sensitive individual file ops, avoid predicting throughput). Enable Lifecycle Management for infrequent-access media cost savings. Security groups on mount targets scoped to the ASG's own security group.

---

## Key Takeaways

1. EFS is the third storage paradigm - file storage - genuinely shared, POSIX-compliant, multi-instance, multi-AZ simultaneous access.
2. EFS is fully elastic with no capacity planning - grows/shrinks with actual data, billed for what's stored.
3. Performance mode (General Purpose vs Max I/O) and throughput mode (Bursting vs Provisioned vs Elastic) are independent decisions.
4. Access Points enforce per-application/tenant isolation at the filesystem-mount level.
5. EFS encryption, like EBS, cannot be toggled on an existing file system - must be enabled at creation, with DataSync migration as the path for existing unencrypted systems.

## Related Concepts (forward links)

- AWS FSx family - purpose-built file systems for Windows/Lustre/NetApp/OpenZFS workloads -> §45
- AWS DataSync for migration between on-premises and EFS/S3 -> §46
- AWS Backup unifying EFS backup alongside EBS/RDS -> §47
