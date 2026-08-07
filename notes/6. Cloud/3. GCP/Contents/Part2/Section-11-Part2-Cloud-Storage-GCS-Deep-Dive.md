# Section 11 (Part 2): Cloud Storage (GCS) — Deep Dive

## 1. Definition

**Plain language:** Cloud Storage (GCS) is Google's object storage service — a place to durably store any amount of unstructured data (files, images, backups, logs, video) as discrete "objects," accessed over HTTP(S) rather than through a filesystem.

**Precise:** Cloud Storage is a globally available, strongly consistent, RESTful object storage service organized into **buckets** (flat namespaces of objects addressed by key), offering multiple **storage classes** for cost/access-frequency trade-offs, fine-grained access control via IAM and (optionally) ACLs, and built-in redundancy/durability (11 nines annual durability) without any server provisioning.

## 2. Why It Exists / Problem It Solves

Traditional filesystems and block storage don't scale well to billions of arbitrarily sized files accessed by many clients concurrently over the internet, and they require you to manage servers, capacity, and redundancy yourself. Cloud Storage exists to give applications a place to put and retrieve arbitrary binary data at effectively unlimited scale, with:

- No capacity planning — a bucket can hold a single file or exabytes without any provisioning step.
- No server management — Google operates the storage backend; you only interact via API/CLI/console.
- Built-in geo-redundancy options and a uniform HTTP(S) API usable from any language or client, including directly from a browser (with signed URLs).

## 3. Core Concepts

### 3.1 Buckets and Objects

A **bucket** is a top-level container with a globally unique name, created in a specific **location** (a region, dual-region, or multi-region). An **object** is an immutable blob of data (up to 5 TiB) plus metadata, addressed by a key (object name) within the bucket. There is no true nested "folder" structure — object names containing `/` are just strings, and the console/CLI simulate folder-like browsing.

> ⚠️ **Interview-relevant nuance:** Because there's no real directory hierarchy, "renaming a folder" is actually a copy-then-delete of every object under that prefix — the same behavior as AWS S3 — and can be slow/costly for large prefixes.

### 3.2 Storage Classes and Autoclass

| Storage Class | Minimum Storage Duration | Typical Use Case                                                          | Relative Cost (storage / retrieval)    |
| ------------- | ------------------------ | ------------------------------------------------------------------------- | -------------------------------------- |
| **Standard**  | None                     | Frequently accessed ("hot") data, website content, active data processing | High storage / no retrieval fee        |
| **Nearline**  | 30 days                  | Accessed roughly once a month (backups, long-tail media)                  | Lower storage / small retrieval fee    |
| **Coldline**  | 90 days                  | Accessed roughly once a quarter (disaster recovery data)                  | Lower still / higher retrieval fee     |
| **Archive**   | 365 days                 | Accessed less than once a year (compliance archives, cold backups)        | Lowest storage / highest retrieval fee |

**Autoclass** is a bucket-level feature that automatically moves objects between Standard, Nearline, Coldline, and Archive based on actual access patterns, removing the need to hand-write lifecycle rules. It trades a small monitoring fee per object for guaranteed-optimal storage cost without manual tuning — ideal when access patterns are unpredictable.

### 3.3 Object Versioning

When enabled on a bucket, **object versioning** keeps prior versions of an object whenever it is overwritten or deleted (a "soft delete" via a **noncurrent version**, distinct from an actual permanent delete). This protects against accidental overwrites/deletions but increases storage cost, since every version is billed until explicitly cleaned up — typically via a lifecycle rule.

### 3.4 Lifecycle Rules

**Lifecycle rules** are bucket-level policies that automatically transition objects between storage classes or delete them once conditions are met (e.g., age, number of newer versions, whether the object is the "live" version). Common pattern: transition to Nearline after 30 days, Coldline after 90, Archive after 365, and delete noncurrent versions after 180 days.

### 3.5 IAM vs. ACLs

- **IAM (recommended, default with Uniform Bucket-Level Access):** Roles (e.g., `roles/storage.objectViewer`, `roles/storage.objectAdmin`) are granted at the project, bucket, or (rarely, for managed folders) sub-path level. Consistent with IAM everywhere else in GCP.
- **ACLs (legacy, fine-grained mode):** Per-object and per-bucket access control lists, allowing permissions on individual objects — powerful but hard to audit at scale, and cannot be combined with Uniform Bucket-Level Access.

### 3.6 Uniform Bucket-Level Access

**Uniform bucket-level access (UBLA)** disables per-object ACLs entirely and enforces that all access is governed solely through IAM at the bucket level. Google recommends UBLA for all new buckets because it dramatically simplifies auditing ("who can access this bucket" is answerable purely from IAM policy) and closes off the common misconfiguration where a single object's ACL accidentally grants public access despite restrictive bucket-level IAM.

### 3.7 Signed URLs

A **signed URL** is a time-limited URL that grants temporary read/write access to a specific object without requiring the requester to have a Google Cloud identity or credentials. It is generated by signing a URL with a service account's private key (or via IAM's `signBlob` API), commonly used to let end users upload/download files directly to/from GCS without proxying traffic through your application servers.

## 4. Architecture Diagram

```
        ┌───────────────────────────────────────────────────────────┐
        │                   Cloud Storage Bucket                    │
        │  Location: us-central1 (regional) or "US" (multi-region)  │
        │                                                           │
        │   ┌───────────────┐  ┌───────────────┐  ┌──────────────┐  │
        │   │ Object: a.jpg │  │Object: b/c.log│  │ Object: d.zip│  │
        │   │class: Standard│  │class: Nearline│  │class: Archive│  |
        │   └───────────────┘  └───────────────┘  └──────────────┘  │
        │                                                           │
        │   IAM Policy (bucket-level, UBLA enforced)                │
        │   - roles/storage.objectViewer -> group:analysts@         │
        │   - roles/storage.admin -> serviceAccount:app-sa@         │
        └───────────────────────────────────────────────────────────┘
              ▲                                    ▲
              │ gsutil / gcloud storage / API      │ Signed URL (temporary,
              │ (authenticated GCP identity)       │ no GCP identity needed)
        ┌────────────────┐                      ┌──────────────────────┐
        │Internal service│                      │ End-user browser/app │
        └────────────────┘                      └──────────────────────┘
```

## 5. Comparison vs. AWS S3 / Azure Blob Storage

| Concept              | GCP Cloud Storage                       | AWS S3                                | Azure Blob Storage                                              |
| -------------------- | --------------------------------------- | ------------------------------------- | --------------------------------------------------------------- |
| Container name       | Bucket                                  | Bucket                                | Storage Account -> Container                                    |
| Hot tier             | Standard                                | S3 Standard                           | Hot                                                             |
| Infrequent tier      | Nearline (30-day min)                   | Standard-IA (30-day min)              | Cool (30-day min)                                               |
| Cold/rare tier       | Coldline (90-day min)                   | Glacier variants                      | Cold (90-day min)                                               |
| Archive tier         | Archive (365-day min)                   | Glacier Deep Archive                  | Archive (180-day min)                                           |
| Automatic tiering    | Autoclass                               | Intelligent-Tiering                   | Lifecycle management policies (rule-based, not fully automatic) |
| Access control model | IAM (bucket-level, UBLA) or legacy ACLs | IAM policies + bucket policies + ACLs | Azure RBAC + Shared Access Signatures (SAS)                     |
| Temporary access URL | Signed URL                              | Presigned URL                         | SAS token                                                       |
| Global unique naming | Bucket names globally unique            | Bucket names globally unique          | Only storage account names globally unique, not containers      |

## 6. Hands-On Examples

**Create a bucket (Beginner):**

```bash
gcloud storage buckets create gs://my-toolkit-demo-bucket --location=us-central1 --uniform-bucket-level-access
```

**Purpose:** Creates a new regional bucket with Uniform Bucket-Level Access enforced from creation.
**Expected output:**

```
Creating gs://my-toolkit-demo-bucket/...
```

**Upload and set storage class (Beginner):**

```bash
gcloud storage cp ./report.pdf gs://my-toolkit-demo-bucket/reports/report.pdf --storage-class=NEARLINE
```

**Set a lifecycle rule (Intermediate):**

```bash
gcloud storage buckets update gs://my-toolkit-demo-bucket --lifecycle-file=lifecycle.json
```

Where `lifecycle.json` transitions objects to Coldline after 90 days:

```json
{
  "rule": [
    {
      "action": { "type": "SetStorageClass", "storageClass": "COLDLINE" },
      "condition": { "age": 90 }
    }
  ]
}
```

**Generate a signed URL (Intermediate):**

```bash
gcloud storage sign-url gs://my-toolkit-demo-bucket/reports/report.pdf --duration=15m --private-key-file=sa-key.json
```

**Expected output (abbreviated):** a full HTTPS URL with query-string signature parameters, valid for 15 minutes.

## 7. Production & Enterprise Usage

- **Static website / CDN origin:** Buckets frequently serve as the origin for Cloud CDN or third-party CDNs, fronting static assets globally.
- **Data lake landing zone:** Raw ingestion data lands in GCS before being processed by Dataflow/Dataproc and loaded into BigQuery (Part 6).
- **Terraform-managed lifecycle policies:** Enterprises manage bucket configuration (storage class, lifecycle, IAM bindings) as code, never via manual console changes, for auditability ([Section 52](../Part7/Section-52-Part7-Terraform-on-GCP-Deployment-Manager.md)).
- **Retention policies and Bucket Lock:** Compliance-heavy organizations (finance, healthcare) use retention policies combined with Bucket Lock to make retention periods legally immutable, similar in spirit to WORM (write-once-read-many) storage.

## 8. Common Misconceptions

- **Misconception:** "Cloud Storage buckets are like folders in a filesystem." In reality, a bucket is a flat namespace; apparent "folders" are just common prefixes in object names with no real directory structure or atomic rename operation.
- **Misconception:** "Nearline/Coldline/Archive are just slower storage." They are identical in latency to Standard for reads — the difference is entirely in _price structure_ (lower storage cost, added retrieval cost and minimum storage duration charges), not access speed.

## 9. Interview Questions

**🎯 Beginner:** _What is the difference between Cloud Storage's Standard and Archive storage classes?_
**Model answer:** Both offer the same millisecond-level read latency; the difference is cost structure. Standard has no minimum storage duration and no retrieval fee, suited for frequently accessed data. Archive has the lowest per-GB storage cost but the highest retrieval fee and a 365-day minimum storage duration, suited for data accessed less than once a year, such as long-term compliance archives.

**🎯 Intermediate:** _Why does Google recommend Uniform Bucket-Level Access over fine-grained ACLs for new buckets?_
**Model answer:** Fine-grained ACLs allow permissions to be set per-object, which means a bucket's effective access surface can only be fully understood by inspecting every object's ACL individually — an unauditable, error-prone model at scale. UBLA disables object-level ACLs entirely and routes all access decisions through IAM at the bucket level, so "who can access this data" is always answerable from one place, and it eliminates the specific misconfiguration class where an object accidentally has a public-read ACL despite restrictive bucket policy.

**🎯 Senior/Architect:** _Design a cost-optimized storage strategy for a data pipeline that ingests raw logs continuously, processes them within a week, and must retain them for 7 years for compliance, with occasional legal-hold audits._
**Model answer:** I would land raw logs in a Standard-class bucket for the active processing window (fast access while Dataflow/Dataproc jobs consume them), with a lifecycle rule transitioning objects to Nearline after 30 days once processing is confirmed complete, then to Coldline at 90 days, and Archive at 365 days, matching the declining access frequency over the 7-year retention window. I'd enable object versioning during the processing week only if in-place overwrites are possible, then rely on a retention policy plus Bucket Lock to make the 7-year retention legally immutable and audit-proof, since Bucket Lock prevents even project owners from shortening or removing the retention policy once locked. For legal-hold audits, I'd use per-object holds (independent of the retention policy) so any specific object involved in litigation is exempted from lifecycle deletion regardless of the age-based rule, without disrupting the retention/lifecycle policy for all other unrelated objects.

## 10. Key Takeaways

- 🔑 Buckets are flat namespaces with globally unique names; there is no real directory hierarchy, only prefix conventions.
- 🔑 Storage classes (Standard/Nearline/Coldline/Archive) trade lower storage cost for higher retrieval cost and longer minimum storage durations — read latency is identical across all classes.
- 🔑 Autoclass automates storage class transitions based on real access patterns, removing the need for hand-tuned lifecycle rules.
- 🔑 Uniform Bucket-Level Access + IAM is the recommended access model; legacy ACLs are fine-grained but unauditable at scale.
- 🔑 Signed URLs grant temporary, credential-free access to specific objects — essential for direct client uploads/downloads.

## 11. Related Concepts

Persistent Disks and Filestore for block/file storage ([Section 12](./Section-12-Part2-Persistent-Disks-and-Filestore.md)), BigQuery loading data from GCS ([Section 44](../Part6/Section-44-Part6-BigQuery-Deep-Dive.md)), Dataflow/Dataproc pipelines reading/writing GCS ([Section 45](../Part6/Section-45-Part6-Dataflow-Dataproc-PubSub.md)), IAM fundamentals ([Section 35](../Part5/Section-35-Part5-IAM-Fundamentals-Members-Roles-Policies.md)), and the GCP vs. AWS vs. Azure storage comparison ([Section 82](../Part13/Section-82-Part13-GCP-vs-AWS-vs-Azure-Comparison.md)) all build on the object storage model introduced here.
