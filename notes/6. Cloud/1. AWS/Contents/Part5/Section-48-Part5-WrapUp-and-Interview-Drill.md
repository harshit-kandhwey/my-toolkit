# Part 5 - Section 10 - Part 5 Wrap-Up + Storage Interview Drill

AWS Zero-to-Enterprise Knowledge Base - Part 5: Storage (Final Section)

---

## 1. Part 5 Consolidated Knowledge Map

Storage (Part 5) breaks down into:

- S1 S3 Fundamentals: Object storage, flat namespace, durability vs availability
- S2 Storage Classes & Lifecycle: Hot->cold->delete, Intelligent-Tiering
- S3 S3 Security/Encryption: IAM+bucket policies, BPA, SSE-S3/KMS/C
- S4 S3 Advanced: Versioning/Replication/Performance
- S5 EBS Full Depth: Block storage, gp3/io2, snapshots, KMS gotcha
- S6 EFS: File storage, POSIX, elastic, Access Points
- S7 FSx Family: Windows/Lustre/ONTAP/OpenZFS, purpose-built compatibility
- S8 Storage Gateway: Hybrid, protocol compatibility
- S9 Backup Strategies: AWS Backup, RPO/RTO, 4 DR patterns

Throughline: S1-4 build S3 completely - fundamentals, cost optimization, security, advanced features. S5 builds EBS to the same depth. S6-7 cover file storage - EFS (general-purpose) and FSx (purpose-built compatibility). S8 bridges storage to on-premises via Storage Gateway. S9 unifies everything into backup policy and the business-driven DR-pattern framework giving all prior sections their purpose: protecting data against loss and enabling recovery.

---

## 2. Consolidated Key-Takeaways Checklist

- Explain S3's flat namespace, the "folder rename is a copy" implication, and durability vs availability precisely.
- Name all seven S3 storage classes, their minimum durations, and when each is appropriate.
- Explain the IAM-policy-vs-bucket-policy distinction and Block Public Access's role as an override.
- Explain SSE-S3 vs SSE-KMS vs SSE-C, and the KMS key-policy "must also align" gotcha.
- Explain versioning's delete-marker behavior and Object Lock's Governance vs Compliance modes.
- Explain gp3 vs gp2's IOPS model, and why st1/sc1 can't be boot volumes.
- Explain why an EBS snapshot chain remains independently restorable even if earlier snapshots are deleted.
- Explain what EFS solves that EBS doesn't, and how Access Points enable multi-tenant sharing.
- Map each FSx type to its specific existing-technology compatibility driver.
- Explain Storage Gateway's three types and the "protocol compatibility without rewrites" principle.
- Define RPO and RTO precisely and distinctly, and map all four DR patterns to their RPO/RTO/cost profile.

---

## 3. Progressive Hands-On Labs - Part 5

### Lab 1 (Beginner) - S3 Fundamentals and Lifecycle

1. Create a bucket; upload several objects with a deliberate key-prefix structure.
2. Enable versioning; overwrite an object, then delete it - observe the delete marker and confirm "undelete."
3. Add a lifecycle rule transitioning objects to Standard-IA after 30 days and expiring non-current versions after 90.

### Lab 2 (Beginner) - S3 Security in Practice

1. Confirm Block Public Access is enabled by default.
2. Write a bucket policy granting read access to a specific IAM role only; confirm access works for that role and is denied for another.
3. Enable SSE-KMS with a CMK; attempt access from a role with S3 permissions but no KMS key-policy grant - confirm AccessDenied, then fix the key policy and confirm success.

### Lab 3 (Intermediate) - EBS Snapshot Lifecycle

1. Attach a gp3 volume to an EC2 instance; write some data.
2. Take a snapshot; modify the data; take a second snapshot.
3. Delete the first snapshot; confirm you can still create a new volume from the second snapshot successfully.

### Lab 4 (Intermediate) - EFS Multi-AZ Mount

1. Create an EFS file system with mount targets in two AZs.
2. Launch one instance per AZ, mount on both, confirm a file written from one is immediately visible from the other.
3. Create two Access Points with different root directories; mount each from a different instance and confirm isolation.

### Lab 5 (Capstone) - DR Pattern Decision Document

1. For three hypothetical systems (public marketing site, core transactional order system, internal HR tool), assign RPO/RTO requirements and select the appropriate DR pattern, justifying against cost.
2. Extend the account-health document with a "storage & DR posture" section: current S3 lifecycle policies, EBS snapshot automation status, and which DR pattern (if any) is implemented for the most critical workload.

---

## 4. Cross-Section Interview Drill

**Compare S3, EBS, and EFS in one paragraph.**
S3 is object storage - flat, key-based, API-driven, no filesystem semantics, massive scale, ideal for unstructured data. EBS is block storage - persistent network-attached disk for a single instance (or narrow multi-attach cluster), formatted with whatever filesystem, ideal for databases/boot volumes. EFS is file storage - managed POSIX-compliant NFS mountable by many instances across many AZs simultaneously, no capacity planning, ideal for shared file access. Deciding question: does this need an API, a single instance's disk, or genuinely shared simultaneous file access?

**Why does the "KMS key policy must also align" gotcha appear in S3, EBS, and AMI sharing?**
All three rely on the same underlying KMS envelope-encryption mechanism, and KMS's own key policy is always the primary access gate, independent of the resource-level policy. One consistent KMS behavior, not three coincidences - understanding it once pays off repeatedly across every encrypted-resource-sharing scenario.

**A team has 18-month-old S3 versioning with no non-current-version lifecycle rule, plus an unencrypted EBS volume with sensitive data needing a compliance CMK - fixes?**
S3: add a lifecycle rule expiring non-current versions after an appropriate window - fixes accumulated storage cost going forward without touching current versions. EBS: since encryption can't be toggled in place, snapshot the volume, copy the snapshot with encryption enabled using the required CMK, create a new volume from that encrypted copy, swap it in - the same not-in-place pattern that also applies to EFS.

**Design storage/DR for: revenue-critical e-commerce (RTO under 5 min), marketing CMS (RTO under 4 hrs acceptable), and a 7-year immutable compliance archive (RPO/RTO largely irrelevant)?**
E-commerce: Warm Standby or Multi-Site Active-Active given the sub-5-min RTO - scaled-down/active environment running continuously in a second Region, data replicated via the tightest mechanism, Route 53 Failover routing driving redirection. Marketing CMS: cheaper Pilot Light given the looser 4-hour RTO - core data replication continuous, full infra scaled up only on failover. Compliance archive: S3 with Object Lock Compliance mode for 7-year immutability, transitioning to Glacier Deep Archive via lifecycle policy given rare access - the requirement is immutability/durability, not availability speed, so the cheapest class with the right retention guarantee is correct, not a DR pattern at all.

---

## 5. Related Technologies (forward links, consolidated)

- RDS/Aurora storage, backup, and Multi-AZ building directly on EBS and the DR patterns here -> Part 6
- VPC Gateway/Interface Endpoints for S3/EFS access -> Part 4 (already covered)
- SQS/EventBridge triggering S3 event-driven processing pipelines -> Part 7
- CloudWatch monitoring of storage metrics, CloudTrail logging of storage API activity -> Part 8
- Infrastructure as Code for backup plans, lifecycle policies, DR infrastructure -> Part 9
- Well-Architected Reliability pillar formalizing the DR pattern framework -> Part 10

---

## 6. Recommended Certification Alignment

- AWS Certified Solutions Architect - Associate/Professional weight S3, EBS, and DR pattern selection heavily.
- AWS Certified SysOps Administrator - Associate emphasizes operational depth (lifecycle policies, snapshot automation, Storage Gateway).

---

## Part 5 - Final Consolidated Key Takeaways

1. Three genuinely different storage paradigms for three genuinely different needs - S3 (object, API-driven, massive scale), EBS (block, single-instance filesystem semantics), EFS (file, shared multi-instance POSIX access) - with FSx providing purpose-built compatibility variants of the file paradigm.
2. Cost optimization across storage is about matching access-pattern assumptions to pricing tiers - S3, EBS, and EFS all follow the same principle: pay more for immediate/flexible access, less for infrequent/delayed access, with real minimum-duration trade-offs.
3. Encryption and access control are consistent, layered patterns repeated across every storage service - IAM + resource policies + KMS key policies, with the "KMS key policy must also align" gotcha appearing identically across S3, EBS, and AMI sharing.
4. Storage Gateway bridges on-premises reality to AWS storage without application rewrites - a protocol-translation and caching layer.
5. Backup and DR are business decisions expressed through technical patterns - RPO/RTO define the requirement, AWS Backup and the four DR patterns provide the implementation spectrum, and cost scales directly with requirement tightness.

---

## Part 5 Complete

All 10 sections of Storage are done. Next: Part 6 - Databases (RDS, Aurora, DynamoDB, ElastiCache, Redshift, DocumentDB, Neptune, migration).
