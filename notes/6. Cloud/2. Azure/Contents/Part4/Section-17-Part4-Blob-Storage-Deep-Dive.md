# Section 17 — Blob Storage Deep Dive (Tiers, Lifecycle Management, Configuration)

## 1. Definition

**Plain language:** Blob Storage is Azure's service for storing large amounts of unstructured data — files of essentially any kind and size, from tiny config files to massive video archives — organized into containers, with pricing that can automatically adjust based on how frequently the data is actually accessed.

**Precise definition:** Azure Blob Storage is an object storage service, one of the four core services hosted under a Storage Account ([Section 16](./Section-16-Part4-Azure-Storage-Account-Fundamentals.md)), providing scalable storage for unstructured binary data organized into a two-level hierarchy of Containers and Blobs, with configurable access tiers, lifecycle management, and multiple blob types suited to different access patterns.

## 2. Why It Exists / Problem It Solves

Unstructured data — images, videos, documents, log files, backups, application binaries, data lake content — doesn't fit naturally into a relational database's row/column structure, and the sheer scale of such data (potentially petabytes) makes traditional file-system-style storage on individual servers impractical. Blob Storage solves this by providing effectively unlimited, durable, highly available object storage accessible via a simple HTTP-based API, with a cost model that includes cheaper tiers for infrequently accessed data — directly addressing the reality that not all stored data is accessed with the same frequency, and paying the same premium rate for rarely-touched archival data as for actively-used data would be wasteful.

## 3. Core Concepts

### 3.1 Containers and Blobs

A **Container** is a logical grouping of blobs within a Storage Account (roughly analogous to a top-level folder, though Blob Storage's structure is technically flat with folder-like paths simulated via naming conventions using `/` delimiters, rather than true nested directories in the traditional file-system sense). A **Blob** is the actual stored object — the file itself, along with associated metadata.

### 3.2 Blob Types

- **Block Blobs** — the standard, most common blob type, optimized for storing and efficiently uploading/downloading discrete files (documents, images, videos, backups) as a set of independently-manageable blocks, allowing efficient partial updates and parallel upload of large files.
- **Append Blobs** — optimized specifically for append-only operations, such as continuously writing log data, where new data is always added to the end of the blob rather than modifying existing content.
- **Page Blobs** — optimized for random read/write access patterns, historically the underlying blob type for Azure VM disk storage ([Section 18](./Section-18-Part4-Azure-Managed-Disks.md)) before Managed Disks abstracted this detail away; still relevant for certain specialized random-access storage scenarios.

💡 **Tip:** For the significant majority of general application use cases (storing files, images, backups, static website assets), Block Blobs are the correct default choice; Append and Page Blobs serve genuinely specialized access patterns and shouldn't be reached for by default.

### 3.3 Access Tiers

Blob Storage supports multiple **access tiers**, each with a different balance of storage cost versus access (retrieval) cost, allowing cost optimization based on actual data access patterns:

| Tier        | Storage Cost    | Access Cost      | Typical Retrieval Latency                                           | Use Case                                                                                                                      |
| ----------- | --------------- | ---------------- | ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| **Hot**     | Highest         | Lowest           | Immediate                                                           | Frequently accessed, actively used data                                                                                       |
| **Cool**    | Lower than Hot  | Higher than Hot  | Immediate                                                           | Infrequently accessed data, retained for at least a defined minimum duration (e.g., 30 days) before it's cost-effective       |
| **Cold**    | Lower than Cool | Higher than Cool | Immediate                                                           | Rarely accessed data retained for a longer minimum duration than Cool                                                         |
| **Archive** | Lowest          | Highest          | Hours (requires explicit "rehydration" before the blob can be read) | Long-term retention/compliance data essentially never expected to be accessed, where retrieval latency of hours is acceptable |

⚠️ Exact tier names (the "Cold" tier is a more recently introduced addition alongside the long-standing Hot/Cool/Archive tiers), specific minimum retention periods, and precise pricing differentials change over time and should be verified against current official documentation before designing a tiering strategy around specific numeric assumptions.

**The core trade-off:** Colder tiers cost less to store data in but cost more (and, for Archive, take dramatically longer) to actually read that data back out — choosing a tier is fundamentally a bet about how frequently that specific data will actually be accessed, and getting this wrong (e.g., storing frequently-accessed data in Cool tier) results in higher total cost than simply using Hot tier would have, due to the higher per-access charges outweighing the storage savings.

### 3.4 Archive Tier Rehydration

Data in the Archive tier cannot be read directly — it must first be **rehydrated** (moved back to Hot or Cool tier), a process that can take several hours depending on the rehydration priority selected (standard vs. high priority, with high priority costing more but completing faster) — this multi-hour latency is a fundamental, unavoidable characteristic of Archive tier and must be planned for explicitly in any workflow that might need to retrieve archived data (e.g., a compliance audit request for old records should account for this rehydration delay in its response-time expectations).

### 3.5 Lifecycle Management Policies

**Definition:** A **Lifecycle Management Policy** is a set of rules, defined declaratively, that automatically transitions blobs between access tiers (or deletes them entirely) based on age or last-access-time conditions, without requiring manual intervention or custom scripting.

**Example policy logic (conceptual):** "Move blobs to Cool tier after 30 days without access; move to Archive tier after 90 days without access; delete entirely after 7 years" — a common pattern implementing a data-retention and cost-optimization strategy purely through declarative configuration rather than custom application logic having to track and manage blob age itself.

**Why this matters for cost optimization:** Without lifecycle management, data tends to accumulate indefinitely in the (more expensive) Hot tier by default, since nothing automatically moves it to cheaper tiers as it ages and becomes less frequently accessed — lifecycle policies are one of the most impactful and easiest-to-implement Blob Storage cost-optimization levers available, addressed further in the cost management discussion in Part 12.

## 4. Architecture Diagram

```
Storage Account "stmyappdata"
 └── Blob Service
      └── Container "backups"
           ├── Blob "backup-2026-01.zip"   [Tier: Hot]     — recent, actively restorable
           ├── Blob "backup-2025-06.zip"   [Tier: Cool]    — older, infrequent access
           └── Blob "backup-2023-01.zip"   [Tier: Archive] — long-term retention, rehydration required to read

Lifecycle Policy:
  IF age > 30 days AND tier == Hot   → move to Cool
  IF age > 90 days AND tier == Cool  → move to Archive
  IF age > 7 years                    → delete
```

## 5. Configuration & Hands-On Example

**Creating a container and uploading a blob with an explicit tier:**

```bash
az storage container create \
  --account-name stmyappdata \
  --name backups \
  --auth-mode login

az storage blob upload \
  --account-name stmyappdata \
  --container-name backups \
  --name "backup-2026-01.zip" \
  --file ./backup-2026-01.zip \
  --tier Hot \
  --auth-mode login
```

- **Purpose:** Creates a container, then uploads a file as a blob, explicitly setting its access tier to Hot.
- **Important arguments explained individually:**
  - `--auth-mode login` — authenticates using the caller's own Entra ID identity (RBAC-based, [Section 8](../Part2/Section-08-Part2-Role-Based-Access-Control.md)) rather than a shared account key, following the security best practice discussed in [Section 16](./Section-16-Part4-Azure-Storage-Account-Fundamentals.md).7.
  - `--tier` — explicitly sets the access tier at upload time; omitting this uses the Storage Account's configured default tier.
- **Common error:** `AuthorizationPermissionMismatch` when using `--auth-mode login` without an appropriate RBAC role (such as Storage Blob Data Contributor) assigned — a good illustration that Storage data-plane operations (reading/writing actual blob content) require specific data-plane RBAC roles, distinct from the management-plane roles (like Contributor) that only control the Storage Account resource itself, not its data.

**Applying a lifecycle management policy (JSON policy definition, illustrative):**

```json
{
  "rules": [
    {
      "name": "move-old-backups-to-cool-then-archive",
      "enabled": true,
      "type": "Lifecycle",
      "definition": {
        "filters": {
          "blobTypes": ["blockBlob"],
          "prefixMatch": ["backups/"]
        },
        "actions": {
          "baseBlob": {
            "tierToCool": { "daysAfterModificationGreaterThan": 30 },
            "tierToArchive": { "daysAfterModificationGreaterThan": 90 },
            "delete": { "daysAfterModificationGreaterThan": 2555 }
          }
        }
      }
    }
  ]
}
```

```bash
az storage account management-policy create \
  --account-name stmyappdata \
  --resource-group rg-myapp-prod \
  --policy @lifecycle-policy.json
```

- **Purpose:** Applies the JSON-defined lifecycle rule to the Storage Account, automating the tier-transition and eventual deletion strategy described conceptually in [Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md).3.5.
- ⚠️ Exact JSON schema field names should be verified against current documentation before use in production, as lifecycle policy schema details are a specific, precise contract that must match exactly.

## 6. Production & Enterprise Usage

Enterprises apply lifecycle management policies systematically across Storage Accounts holding backup, log, and compliance-retention data, tuning tier-transition thresholds based on actual observed access patterns (informed by Storage Account access logs and metrics, [Section 16](./Section-16-Part4-Azure-Storage-Account-Fundamentals.md).9) rather than guessed defaults, since an incorrectly aggressive policy (moving actively-needed data to Archive too early) can create operational friction (multi-hour retrieval delays for data still occasionally needed) while an overly conservative policy leaves cost-optimization value unrealized. Blob Storage is also foundational to many higher-level enterprise data patterns: as the storage layer underneath data lakes (often paired with Azure Data Lake Storage capabilities, a Blob Storage feature set enabling hierarchical namespace support for big-data analytics workloads), as the backing store for static website hosting, and as the target for Azure Backup and Azure Site Recovery data (Part 12).

## 7. Security Considerations

- **Public access** to containers/blobs should be disabled by default at the Storage Account level unless a specific container genuinely needs to serve public content (like static website assets); accidentally public blob containers holding sensitive data are a well-documented real-world data-breach pattern.
- **Immutability policies** (WORM — Write Once, Read Many) can be applied to blobs for compliance scenarios requiring data to be provably unmodifiable for a defined retention period, relevant for certain regulated industries' record-retention requirements.
- Data-plane access ([Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md).5's `AuthorizationPermissionMismatch` note) should use Entra ID-based RBAC roles scoped narrowly (e.g., Storage Blob Data Reader for read-only needs) rather than defaulting to broader access or shared account keys.

## 8. Performance Considerations

Very large blob uploads/downloads benefit from Block Blob's block-based parallel transfer capability (uploading/downloading multiple blocks of a large file concurrently rather than as one single serial stream), which most modern SDK/CLI tooling handles automatically; for extremely high-throughput scenarios, Storage Account-level scalability limits ([Section 16](./Section-16-Part4-Azure-Storage-Account-Fundamentals.md).8) still apply and may necessitate spreading load across multiple accounts.

## 9. Monitoring

Blob-level access patterns (which blobs are actually being read, and how often) should inform lifecycle policy tuning — Storage Account diagnostic logs and metrics ([Section 16](./Section-16-Part4-Azure-Storage-Account-Fundamentals.md).9, Part 10) provide this visibility, allowing a data-driven rather than purely assumption-based tiering strategy.

## 10. Troubleshooting

| Symptom                                                                                  | Likely Cause                                                                                      | Fix                                                                                                                                            |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Blob read request fails or hangs for a very long time                                    | Blob is in Archive tier and hasn't been rehydrated                                                | Initiate rehydration to Hot/Cool tier first and wait for the (potentially multi-hour) rehydration process to complete before retrying the read |
| `AuthorizationPermissionMismatch` despite having Contributor role on the Storage Account | Contributor is a management-plane role; blob data access requires a separate data-plane RBAC role | Assign an appropriate data-plane role (e.g., Storage Blob Data Contributor) in addition to or instead of Contributor                           |
| Storage costs unexpectedly high despite data being rarely accessed                       | Data sitting in Hot tier without a lifecycle policy moving it to cheaper tiers as it ages         | Implement and tune a lifecycle management policy based on actual access patterns                                                               |

## 11. Interview Questions — [Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md)

### 🎯 Intermediate

**Q: Explain the trade-off between the Hot, Cool, and Archive access tiers, and how you'd decide which to use for a given dataset.**

_Model answer:_ The tiers trade storage cost against access cost and retrieval latency: Hot has the highest storage cost but the lowest (immediate, cheapest) access cost, ideal for frequently accessed data. Cool and Cold have progressively lower storage costs but higher per-access costs, appropriate for data accessed infrequently enough that the storage savings outweigh the higher access charges. Archive has the lowest storage cost but requires a multi-hour rehydration process before data can be read at all, appropriate only for data that's essentially never expected to be accessed except in rare circumstances (like long-term compliance retention) where that retrieval delay is acceptable. The decision should be based on actual or reasonably expected access frequency for that specific data — choosing a colder tier than the actual access pattern warrants can increase total cost due to per-access charges, despite the lower storage rate.

_What the interviewer is probing:_ understanding that tier selection is a genuine cost-optimization trade-off requiring actual access-pattern knowledge, not simply "always pick the cheapest storage cost tier."

### 🎯 Senior

**Q: How would you design an automated, cost-effective data retention strategy for an application generating large volumes of log data with a 7-year compliance retention requirement, but where logs are rarely accessed after the first 30 days?**

_Model answer:_ I'd implement a Lifecycle Management Policy on the Storage Account holding the logs, defining rules that automatically transition blobs to Cool tier after roughly 30 days (matching the described drop-off in access frequency), further transition to Archive tier after some longer threshold (e.g., 90-180 days, tuned based on actual observed access data rather than a guessed default) once the likelihood of needing to read that data becomes very low, and automatically delete blobs once they exceed the 7-year compliance retention requirement — removing all of this from manual or custom-application-code management entirely. I'd pair this with an immutability policy for the compliance-retention period specifically, ensuring the data can't be modified or prematurely deleted before the retention requirement is satisfied, addressing the compliance angle alongside the cost-optimization angle. I'd also make sure any legitimate business process that might occasionally need to retrieve older logs (e.g., a compliance audit) is designed with awareness of Archive tier's multi-hour rehydration delay, so that expectation is set correctly rather than assuming instant retrieval will always be available.

_What the interviewer is probing:_ whether the candidate can design an end-to-end automated strategy combining lifecycle management, immutability/compliance requirements, and awareness of the operational implications (rehydration delay) of the chosen approach — genuine architectural thinking rather than just naming the relevant features.

## 12. Common Misconceptions

- **"Archive tier data can be read immediately, just at a lower storage cost."** False and operationally significant — Archive tier requires an explicit, multi-hour rehydration process before any read is possible; this is a hard architectural constraint, not a minor inconvenience.
- **"Choosing the cheapest storage tier always minimizes total cost."** False — total cost depends on both storage cost and access-frequency-driven access cost; frequently-accessed data in a colder tier can cost more overall than the same data in Hot tier, due to higher per-access charges.

## 13. Key Takeaways

- 🔑 Block Blobs are the default, general-purpose blob type; Append and Page Blobs serve specialized append-only and random-access scenarios respectively.
- 🔑 Access tiers (Hot/Cool/Cold/Archive) trade storage cost against access cost and retrieval latency — tier selection should be driven by actual or expected access frequency, not simply minimizing storage cost.
- 🔑 Archive tier requires an explicit, potentially multi-hour rehydration process before data can be read — a hard constraint that must be planned for in any workflow touching archived data.
- 🔑 Lifecycle Management Policies automate tier transitions and eventual deletion declaratively, one of the highest-impact and easiest-to-implement Blob Storage cost-optimization mechanisms available.
- 🔑 Blob data-plane access requires data-plane RBAC roles (e.g., Storage Blob Data Contributor), distinct from management-plane roles like Contributor that only control the Storage Account resource itself.

## 14. Data Protection & Recovery (Versioning, Soft Delete, Point-in-Time Restore, Legal Holds, Object Replication)

### 14.1 Why This Is a Distinct Concern

Access tiers ([Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md).3.3) and lifecycle policies ([Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md).3.5) manage _cost_ over a blob's life; they do nothing to protect against _accidental or malicious data loss_ — an application bug overwriting a blob, a user accidentally deleting a container, or a ransomware-style attack encrypting/corrupting blob content. The features in this subsection specifically address that separate concern: recovering from unwanted change or deletion, and, for regulated data, provably preventing deletion/modification entirely for a defined period.

### 14.2 Blob Versioning

**Definition:** When enabled on a Storage Account, **Blob Versioning** automatically preserves every prior version of a blob whenever it's overwritten or deleted, each with its own immutable version ID — rather than an overwrite or delete destroying the previous content outright, the prior version remains retrievable.

**Why it matters:** Versioning provides protection against accidental overwrites (an application bug that corrupts a file's content) and gives a straightforward way to retrieve or promote a specific prior version back to current — but it does add storage cost, since every version is retained (subject to any lifecycle policy rules specifically targeting older versions for cleanup) rather than only the latest content.

### 14.3 Soft Delete

**Definition:** **Soft Delete** (available for both blobs/containers and, separately, for Storage Accounts overall in some configurations) retains deleted blobs or containers in a recoverable state for a configured retention period (e.g., 7–365 days) before permanent removal, rather than deleting them immediately and irrecoverably.

**Why it matters:** This is the direct mitigation for accidental deletion (a script or user deleting the wrong container) and is one of the most impactful, low-effort protections available — enabling it costs comparatively little (retained deleted data is billed, but typically represents a small fraction of active data volume) relative to the protection it provides against what is otherwise an unrecoverable mistake.

💡 **Tip:** Soft Delete and Versioning are complementary, not redundant — Soft Delete protects against deletion, Versioning protects against overwrites; a blob that's overwritten (not deleted) is unaffected by Soft Delete but is protected by Versioning, and vice versa for a deleted-but-never-overwritten blob. Production Storage Accounts holding meaningful data should generally enable both together.

### 14.4 Point-in-Time Restore

**Definition:** **Point-in-Time Restore** (for block blobs, requiring Versioning and Soft Delete to both be enabled as prerequisites) allows restoring an entire container — or a specified set of blobs — to their state at a specific previous point in time, in a single operation, rather than requiring individual blob-by-blob version recovery.

**Why it matters:** For a scenario like a bulk accidental overwrite or corruption event affecting many blobs at once (e.g., a faulty batch job that incorrectly modified thousands of files), Point-in-Time Restore allows recovering the entire affected set back to a known-good state in one operation, rather than manually identifying and reverting each individual blob's version — a substantial operational time-savings during an actual incident.

### 14.5 Legal Holds and Immutability Policies

**Definition:** Referenced briefly in [Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md).7, **immutability policies** enforce Write-Once-Read-Many (WORM) semantics on blobs — once written, a blob under an immutability policy cannot be modified or deleted until the policy's conditions are satisfied. Two distinct immutability mechanisms exist:

- **Time-based retention policies** — data cannot be deleted or modified until a specified retention period elapses, suited to fixed-duration compliance retention requirements (e.g., "financial records must be retained for 7 years").
- **Legal Holds** — data is protected indefinitely, with no fixed expiration, until the hold is explicitly and deliberately removed by an authorized administrator — suited to open-ended scenarios like active litigation or a regulatory investigation, where the required retention duration isn't known in advance.

⚠️ Immutability policies, once applied in their "locked" state (as opposed to an initial "unlocked" testing state some configurations support), generally cannot be shortened or removed before their condition is met, even by an Owner-level administrator — this is an intentional, compliance-driven design (the policy would be meaningless if trivially reversible), but it means immutability configuration should be tested carefully in an unlocked state before being locked against production data.

### 14.6 Object Replication

**Definition:** **Object Replication** asynchronously copies block blobs from a source container to a destination container, which can be in a different Storage Account and a different region, based on a configured replication policy (optionally scoped to specific blob prefixes or filters) — distinct from the account-wide GRS/RA-GRS redundancy mechanisms covered in [Section 20](./Section-20-Part4-Data-Redundancy-and-Replication.md), since Object Replication operates at the container/blob level with more granular control and, notably, allows the destination to be actively used (read from and even written to independently, depending on configuration) rather than serving purely as a passive redundancy target.

**When to use Object Replication vs. GRS/RA-GRS:** GRS/RA-GRS ([Section 20](./Section-20-Part4-Data-Redundancy-and-Replication.md).3.3–20.3.4) provide whole-account disaster-recovery-oriented replication with Microsoft managing the mechanism transparently. Object Replication is chosen when more granular, container/prefix-scoped replication is needed — for example, replicating only specific data to a region close to a particular set of users for lower-latency read access, or maintaining an independently-writable secondary copy for a distinct application need — rather than a blanket whole-account DR copy.

### 14.7 Configuration Example

```bash
az storage account blob-service-properties update \
  --resource-group rg-myapp-prod \
  --account-name stmyappdata \
  --enable-versioning true \
  --enable-delete-retention true \
  --delete-retention-days 30 \
  --enable-restore-policy true \
  --restore-days 29
```

- **Purpose:** Enables Blob Versioning, Soft Delete (30-day retention), and Point-in-Time Restore (restore window must be shorter than the delete-retention window, hence 29 days here) on the Storage Account in a single configuration pass — implementing the layered protection strategy described above.
- ⚠️ Exact parameter names and interdependency rules (e.g., the restore-days-must-be-less-than-delete-retention-days constraint) should be verified against current CLI/documentation before applying to a production account, since these prerequisite relationships are specific and enforced by the platform.

### 14.8 Interview Questions — [Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md).14

**🎯 Intermediate**
**Q: What's the difference between Blob Versioning and Soft Delete, and why would you enable both?**

_Model answer:_ Versioning preserves every prior version of a blob whenever it's overwritten, allowing recovery of previous content after an unwanted overwrite. Soft Delete preserves a deleted blob or container in a recoverable state for a configured retention window, protecting against accidental deletion specifically. They address different failure modes — an overwrite isn't a deletion, and a deletion isn't an overwrite — so enabling only one leaves a real gap; production data benefiting from recovery protection should generally have both enabled together, since together they cover the two most common accidental-data-loss scenarios.

_What the interviewer is probing:_ precise understanding that these are complementary, not overlapping, protections — a common point of confusion for those newer to Blob Storage's data-protection feature set.

**🎯 Senior**
**Q: A compliance team requires that financial transaction records be provably unmodifiable for exactly 7 years, while a separate ongoing legal matter requires certain specific records be preserved indefinitely until the legal team says otherwise. How would you configure Blob Storage to satisfy both requirements?**

_Model answer:_ For the 7-year financial record requirement, I'd apply a time-based immutability retention policy set to a 7-year duration on the relevant container, and lock the policy once validated in an unlocked/testing state, ensuring the data genuinely cannot be deleted or modified before the 7-year period elapses, satisfying the "provably unmodifiable" requirement in a way that even an Owner-level administrator can't accidentally or improperly override. For the specific records under legal hold, I'd apply a Legal Hold to those specific blobs (or the container holding them, depending on how precisely the affected records can be scoped) rather than a time-based policy, since the required retention duration isn't known in advance — Legal Hold's indefinite, explicitly-removed-only nature matches that requirement precisely, whereas a time-based policy would require guessing an end date that might not align with when the legal matter actually concludes. I'd document both configurations clearly and would coordinate directly with the compliance and legal teams before removing either protection, given the deliberately difficult-to-reverse nature of these controls.

_What the interviewer is probing:_ whether the candidate can map two similar-sounding but functionally distinct compliance requirements (fixed-duration vs. open-ended) to the two correspondingly distinct immutability mechanisms, rather than treating "immutability" as a single undifferentiated feature.

### 14.9 Key Takeaways — [Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md).14

- 🔑 Versioning (protects against overwrites) and Soft Delete (protects against deletion) are complementary data-protection mechanisms, distinct from access tiers and lifecycle management, which manage cost rather than protect against loss.
- 🔑 Point-in-Time Restore (requiring Versioning + Soft Delete) enables bulk container-level recovery to a prior state in one operation, valuable for recovering from wide-impact accidental changes.
- 🔑 Time-based immutability policies suit fixed-duration compliance retention; Legal Holds suit open-ended, indefinite retention needs — choosing the wrong one either under- or over-commits to a retention duration that doesn't match the actual requirement.
- 🔑 Object Replication provides granular, container/prefix-scoped, actively-usable cross-account/cross-region replication, distinct from GRS/RA-GRS's whole-account, passive-by-default DR replication ([Section 20](./Section-20-Part4-Data-Redundancy-and-Replication.md)).

## 15. Related Concepts (Next Up)

[Section 18](./Section-18-Part4-Azure-Managed-Disks.md) covers **Azure Managed Disks** — VM-attached block storage (referenced back in [Section 11](../Part3/Section-11-Part3-Azure-Virtual-Machines.md).3 as the OS/data disk mechanism for VMs), including disk types, performance tiers, and how Managed Disks relate to (and abstract away) the underlying Page Blob storage mechanism mentioned in [Section 17](./Section-17-Part4-Blob-Storage-Deep-Dive.md).3.2.
