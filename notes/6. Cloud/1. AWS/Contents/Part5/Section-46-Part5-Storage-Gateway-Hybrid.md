# Part 5 - Section 8 - AWS Storage Gateway & Hybrid Storage

AWS Zero-to-Enterprise Knowledge Base - Part 5: Storage

---

## 1. Definition

Plain-language: Storage Gateway is a virtual appliance you run on-premises (or on EC2) that makes AWS storage - S3, EBS snapshots, or tape-compatible interfaces - accessible using standard on-premises storage protocols, so existing applications can use AWS storage without knowing anything changed.

Precise: AWS Storage Gateway is a hybrid cloud storage service providing on-premises applications with local, low-latency access to AWS storage, presented through familiar on-premises protocols (NFS/SMB, iSCSI, or Virtual Tape Library), while the actual data is stored durably in AWS.

---

## 2. Why It Exists

- Part 4's hybrid connectivity (VPN/Direct Connect) makes a hybrid architecture possible; Storage Gateway makes that connectivity useful for storage specifically, without requiring apps to be rewritten to call S3's API directly.
- Core problem: countless enterprise applications assume a traditional file share, block device, or tape backup system. Rewriting them to speak S3 natively is often impractical (legacy/vendor software). Storage Gateway lets them keep using the protocol they understand while data quietly lives in AWS.

---

## 3. The Three Storage Gateway Types

### 3.1 S3 File Gateway

- Presents a file share (NFS or SMB) while storing actual files as objects in S3 - genuinely accessible via the normal S3 API too, not a proprietary format, letting the same data serve both traditional clients and modern S3-native tools.
- Local caching - frequently accessed data cached on the appliance for low latency, full dataset lives durably in S3 - parallel to CloudFront caching, for on-premises access to cloud-stored files.

### 3.2 Volume Gateway

- Presents iSCSI block storage volumes for applications expecting a block device.
- Cached volumes - primary data in S3, only frequently accessed data cached locally - for datasets larger than practical on-premises storage.
- Stored volumes - entire dataset lives locally for full-speed access, with asynchronous backup to S3 as EBS snapshots - for apps needing the complete dataset locally, using AWS purely for durable backup/DR.

### 3.3 Tape Gateway

- Presents a Virtual Tape Library (VTL) interface compatible with existing tape backup software, storing virtual tapes durably in S3 (transitionable to Glacier for long-term retention).
- Lets existing tape software/workflows continue unchanged while eliminating physical tape media and off-site logistics, replaced by S3/Glacier durability.

---

## 4. Common Thread

Key idea: Storage Gateway's entire value proposition is presenting a familiar existing protocol on-premises while data durably lives in S3 (or S3-backed EBS snapshots) in AWS - enabling hybrid storage without application-level changes, purely a protocol translation and caching layer.

---

## 4a. Data Migration & Transfer Services - AWS DataSync, AWS Transfer Family, AWS Snow Family

### 4a.1 The Problem Category

- Storage Gateway (Sections 1-4) solves ongoing, ongoing-access hybrid storage - ongoing production access to data that lives in AWS but is consumed on-premises via a familiar protocol. A related but distinct problem is moving data into (or out of) AWS as a one-time or recurring transfer job, not for ongoing protocol-level access - migrations, recurring sync jobs, and managed file-transfer workflows. DataSync, Transfer Family, and Snow Family are AWS's purpose-built services for that transfer-specific problem category.

### 4a.2 AWS DataSync

- DataSync automates and accelerates online (network-based) data transfer between on-premises storage (NFS/SMB shares, or a Storage Gateway File Gateway) and AWS storage (S3, EFS, FSx), or between two AWS storage services.
- Core value beyond a manual copy: DataSync manages the transfer using a purpose-built protocol optimized for throughput over standard network copy tools, automatically handles retries and validates data integrity after transfer, and can run on a recurring schedule - not just a one-time migration tool, but also a genuine ongoing sync mechanism (for example, keeping an on-premises file share and an S3-based copy continuously in sync for a hybrid workload).
- Distinct from Storage Gateway: DataSync moves data in transfer jobs, appropriate when the destination or source doesn't need continuous, transparent protocol-level access the way Storage Gateway provides - if the actual requirement is "on-premises apps need ongoing access to AWS-backed storage using a familiar protocol," that is Storage Gateway's job (Sections 3-4); if the requirement is "get this data from A to B, once or on a schedule," that is DataSync's job.

### 4a.3 AWS Transfer Family

- Transfer Family provides fully managed support for file transfers into and out of S3 (and EFS) using standard transfer protocols - SFTP, FTPS, and FTP - letting an organization support existing partner/customer file-transfer workflows built around those protocols without operating and patching their own SFTP/FTP server infrastructure.
- Core use case: many B2B and legacy data-exchange workflows are built around SFTP specifically (a trading partner's system, a legacy vendor integration) and cannot easily be changed to call the S3 API directly - Transfer Family lets that unchanged external workflow continue operating, with the actual files landing directly in S3 as the durable backing store, the same "meet existing protocol expectations, S3 underneath" philosophy Storage Gateway's S3 File Gateway applies to NFS/SMB, here applied to SFTP/FTPS/FTP specifically for managed, often externally-facing file exchange.
- Distinct from DataSync and Storage Gateway: Transfer Family is specifically for externally-facing, protocol-standard managed file transfer (frequently with external partners/customers as the other party), whereas DataSync is for internal, typically higher-throughput bulk data movement, and Storage Gateway (File Gateway) is for internal, ongoing NFS/SMB access.

### 4a.4 AWS Snow Family

- The Snow Family (Snowcone, Snowball Edge, Snowmobile) provides physical, offline data transfer devices for moving very large data volumes where network-based transfer (DataSync, or any online method) would be impractically slow or costly given available bandwidth - AWS ships a physical device, the data is loaded onto it on-premises, and the device is shipped back to AWS for ingestion.
- The decision driver is fundamentally a bandwidth-versus-data-volume calculation: transferring a large dataset (many terabytes to petabytes) over a constrained network connection can genuinely take weeks to months at the available bandwidth, while physically shipping a device can complete the same transfer in days, a calculation worth making explicitly for any sufficiently large one-time migration rather than assuming online transfer is always the right default.
- Snowcone is the smallest, portable option for edge locations with limited space/power; Snowball Edge adds significantly more capacity and, notably, onboard compute (allowing some processing to happen at the edge before/during transfer); Snowmobile is AWS's largest-scale option (an actual shipping-container-based solution) for truly massive, exabyte-scale migrations - a range of options for genuinely different data-volume scales, not one-size-fits-all.
- Snow Family devices are also used for the reverse and for disconnected/edge use cases beyond pure migration - some models support running compute and storage locally in disconnected or intermittently-connected environments, distinct from their migration-specific role covered here.

### 4a.5 Choosing Among These Options

- Ongoing, protocol-transparent hybrid access to AWS-backed storage from on-premises applications -> Storage Gateway (Sections 1-4).
- Online, network-based bulk transfer or recurring sync between on-premises/AWS storage, where available bandwidth is adequate -> DataSync.
- Managed, externally-facing SFTP/FTPS/FTP file exchange landing directly in S3 -> Transfer Family.
- One-time (or infrequent) transfer of very large data volumes where available network bandwidth makes online transfer impractically slow -> Snow Family, sized to the actual data volume (Snowcone/Snowball Edge/Snowmobile).

### 4a.6 Key Takeaways

1. DataSync, Transfer Family, and Snow Family address data movement (one-time or recurring transfer jobs), distinct from Storage Gateway's ongoing, protocol-transparent access problem.
2. DataSync is for online, network-based bulk transfer and recurring sync; Transfer Family is for managed, externally-facing SFTP/FTPS/FTP exchange landing in S3; Snow Family is for offline, physical transfer when data volume exceeds what available bandwidth can move in a reasonable time.
3. The choice between online (DataSync) and offline (Snow Family) transfer for a large migration is fundamentally a bandwidth-versus-data-volume calculation, not a default preference for one over the other.

## 5. Production & Enterprise Usage

- S3 File Gateway for gradual migration - point existing file-share apps at it today, gain S3 durability and eventual cloud-native processing (analytics, Lambda triggers) without first rewriting apps - a staged migration pattern.
- Volume Gateway (stored mode) for DR - keep primary data on-premises for latency/compliance, use stored-mode purely for automatic durable off-site EBS-snapshot backup.
- Tape Gateway for compliance-driven long-term retention - eliminate physical tape logistics while keeping existing backup software/audit processes unchanged, Glacier handling cost optimization underneath.

---

## 6. Security Considerations

- Data in transit between the on-prem gateway and AWS is TLS-encrypted by default.
- Data at rest in S3/EBS snapshots follows the same KMS/envelope-encryption mechanics as elsewhere - Storage Gateway inherits the underlying service's model, doesn't introduce a new one.
- IAM controls what the gateway itself can do in your AWS account - same least-privilege principle applied throughout.

---

## 7. Performance Considerations

- Local caching (File Gateway, cached-mode Volume Gateway) is the primary latency mitigation - frequent data stays local, bulk lives cheaply in AWS - a bandwidth/cost/latency trade-off parallel to CDN caching.
- Stored-mode Volume Gateway avoids latency trade-off for primary access (full dataset local) at the cost of not benefiting from S3's elastic capacity for the primary copy - a genuine choice, not strictly better either way.

---

## 8. Troubleshooting

| Symptom                                                                | Cause                                                                       | Fix                                                                                                                        |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Wrong gateway type for the workload's protocol                         | App expects a file share but Volume Gateway deployed, or vice versa         | Match gateway type to actual protocol expected (NFS/SMB->File Gateway, iSCSI->Volume Gateway, tape software->Tape Gateway) |
| Poor local access performance for large infrequently-changing datasets | Cached-mode Volume Gateway used when working set doesn't fit in local cache | Evaluate stored-mode if full local access is required, or review cache sizing                                              |
| Uncertain if existing tape software works unchanged with Tape Gateway  | Assuming new backup software is needed                                      | Tape Gateway is designed to work with existing tape-compatible software via VTL - verify compatibility                     |

---

## 9. Best Practices & Anti-Patterns

Best practices: match Storage Gateway type to the app's actual expected protocol; use S3 File Gateway for staged migrations; use stored-mode Volume Gateway only when full local access is a genuine requirement; use Tape Gateway to eliminate physical tape logistics while preserving compliance workflows.

Anti-patterns: choosing a gateway type without confirming protocol match; assuming cached-mode always suffices without checking working-set fit; assuming Storage Gateway requires application rewrites.

---

## 10. Common Misconceptions

- "Storage Gateway requires rewriting on-prem apps to use S3's API." False - its purpose is presenting familiar protocols so apps work unchanged.
- "All Storage Gateway types work the same way." False - File, Volume (cached/stored), and Tape Gateway are genuinely different, purpose-built for different protocols.
- "Cached-mode Volume Gateway keeps a full local copy." False - that's stored-mode; cached-mode keeps only frequently accessed data locally.
- "Files via S3 File Gateway aren't real S3 objects." False - genuine S3 objects, accessible via the standard API too.

---

## 11. Interview Questions (with model answers)

Beginner - What problem does Storage Gateway solve? Lets on-premises applications expecting traditional storage protocols (file share, block device, tape) use AWS storage as the backing store without rewriting - a virtual appliance presents the familiar protocol while data lives durably in S3/EBS snapshots.

Beginner - Cached vs stored Volume Gateway modes? Cached: primary data in S3, frequently accessed data cached locally - for datasets larger than practical locally. Stored: entire dataset local for full-speed access always, async backup to S3 as EBS snapshots - for apps needing the complete dataset locally, AWS as pure backup.

Intermediate - Why choose S3 File Gateway in a migration strategy rather than migrating directly to S3? Lets an existing file-share app keep working completely unchanged (still sees NFS/SMB) while data becomes genuine S3 objects underneath - gains S3 durability and cloud-native processing potential immediately, without first rewriting the app. A staged approach: get data into S3 now, modernize app access later if worthwhile.

Senior - Design hybrid storage for: legacy tape-based compliance backup, a large file server needing gradual migration, and a database needing full local block performance with cloud DR? Tape Gateway for compliance backup - existing software unchanged via VTL, tapes stored in S3/Glacier for long-term retention, eliminating physical tape logistics. S3 File Gateway for the file server - existing NFS/SMB clients unchanged, data becomes genuine S3 objects, setting up future cloud-native processing without immediate rewrite. Volume Gateway stored mode for the database - full local performance requirement keeps the entire dataset on-premises, with async EBS-snapshot backup to AWS providing DR without compromising local performance.

---

## Key Takeaways

1. Storage Gateway's entire value proposition is protocol compatibility without application rewrites - familiar on-premises protocols while data lives durably in AWS.
2. Three distinct types serve three distinct protocol dependencies - S3 File Gateway (NFS/SMB -> genuine S3 objects), Volume Gateway (iSCSI, cached or stored), Tape Gateway (VTL -> S3/Glacier).
3. Cached vs stored Volume Gateway modes are a genuine architectural choice depending on whether full local access is a real requirement.
4. S3 File Gateway enables staged migration - apps keep working unchanged while data becomes S3-native underneath.
5. Storage Gateway inherits the underlying AWS service's security model (KMS at rest, TLS in transit, IAM for gateway permissions) - no separate security paradigm.

## Related Concepts (forward links)

- AWS DataSync, AWS Transfer Family, and AWS Snow Family - the transfer-job-oriented complements to Storage Gateway's ongoing hybrid access model (see Section 4a above)
- AWS Backup - unifying backup management across EBS, EFS, FSx, RDS -> §47 (next, final content section)
- Migration strategies (the 7 Rs) building on Storage Gateway's and DataSync's staged-migration capability -> §93
- VPN/Direct Connect as the underlying hybrid connectivity Storage Gateway depends on -> §33
