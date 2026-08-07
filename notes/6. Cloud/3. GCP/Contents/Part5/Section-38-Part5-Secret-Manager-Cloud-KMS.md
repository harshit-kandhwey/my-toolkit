# Section 38 (Part 5): Secret Manager & Cloud KMS

## 1. Definition

**Plain language:** Applications need two related but distinct things kept safe: sensitive pieces of text like API keys and database passwords (secrets), and the cryptographic keys used to encrypt data at rest (encryption keys). Secret Manager stores and versions the former; Cloud KMS creates and manages the latter.

**Precise:** **Secret Manager** is a fully managed service for storing, versioning, and controlling access to sensitive string/binary data ("secrets") such as API keys, passwords, and certificates, with each secret holding an immutable, access-controlled version history. **Cloud KMS (Key Management Service)** is a fully managed service for creating, managing, rotating, and using cryptographic keys — including symmetric encryption keys, asymmetric keys for signing/decryption, and keys backed by dedicated Hardware Security Modules (HSMs) — for encrypting data both directly (application-level encryption) and indirectly (Customer-Managed Encryption Keys, or CMEK, for other GCP services).

## 2. Why It Exists

Before Secret Manager, applications commonly stored secrets in configuration files, environment variables, or source code — all of which are easy to leak (a config file committed to Git, an environment variable dumped in a crash log) and impossible to version, rotate, or audit access to consistently. Secret Manager exists to centralize secret storage with IAM-governed access, automatic versioning, and audit logging, so a secret is never scattered across many places or embedded in code.

Separately, "encrypt data at rest" is a near-universal requirement, but organizations often need to control the _keys_ themselves — for compliance, for the ability to revoke access to encrypted data by disabling a key, or for HSM-level assurance that key material never exists unencrypted outside dedicated hardware. Cloud KMS exists to give organizations this level of control without requiring them to build and operate their own key management infrastructure.

## 3. Core Concepts: Secret Manager

### 3.1 Secrets and Versions

A **secret** is a named container; each time its value changes, a new immutable **version** is created (`v1`, `v2`, ...), and old versions remain retrievable (or can be explicitly destroyed) — this gives a full audit trail of what a credential's value was at any point in time, and lets an application pin to a specific version or always fetch "latest."

### 3.2 Access Control and Rotation

- Access to secrets is governed by IAM roles (`roles/secretmanager.secretAccessor` to read a value, `roles/secretmanager.admin` to manage), following the same principal/binding model as [Section 35](./Section-35-Part5-IAM-Fundamentals-Members-Roles-Policies.md) — a secret's access can be scoped as tightly as a single service account.
- Secret Manager supports **rotation notifications** — configuring a schedule that publishes a Pub/Sub message reminding an owner (or triggering an automation, e.g., a Cloud Function) to rotate the underlying credential; Secret Manager itself does not automatically regenerate arbitrary third-party credentials, since it has no way to know how to, e.g., change a specific database's password — rotation logic is application/service-specific.
- Every access to a secret version is recorded in Cloud Audit Logs' Data Access logs ([Section 40](./Section-40-Part5-Compliance-Governance.md)), letting security teams answer "who read this secret, and when?"

### 3.3 Replication

Secrets can be configured as **automatic** (Google chooses replica locations, simplest default) or **user-managed** (explicit list of regions), the latter used when data residency requirements dictate exactly where the secret's encrypted replicas may live.

## 4. Core Concepts: Cloud KMS

### 4.1 Key Hierarchy

Cloud KMS organizes keys as: **Key Ring** (a regional or global grouping/namespace for keys, existing purely for organization and IAM scoping) → **Key** (a named cryptographic key) → **Key Version** (the actual key material; a key can have multiple versions as it's rotated, with one marked "primary" for new encryption operations).

### 4.2 Key Types

| Key type                      | Use case                                                                                                                                                                                                                            |
| ----------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Symmetric encryption key**  | The default and most common type — same key encrypts and decrypts. Used for envelope encryption of application data and CMEK.                                                                                                       |
| **Asymmetric decryption key** | A public/private key pair where the public key encrypts and only the private key (which never leaves KMS) decrypts.                                                                                                                 |
| **Asymmetric signing key**    | A public/private key pair used to produce and verify digital signatures, e.g., for signed URLs or attestations (relevant to Binary Authorization, [Section 43](./Section-43-Part5-Binary-Authorization-Confidential-Computing.md)). |

### 4.3 Protection Levels

- **Software** — key material is protected by Google's software-based encryption within KMS, the default and most common tier.
- **HSM (Hardware Security Module)** — key material is generated and used inside a FIPS 140-2 Level 3 validated hardware module, and can never be exported even in encrypted form — required by some regulatory/compliance frameworks.
- **External / External-VPC** — key material is stored and the cryptographic operation actually performed outside Google's infrastructure entirely (an external key manager), for organizations requiring full custody of key material independent of the cloud provider.

### 4.4 CMEK (Customer-Managed Encryption Keys)

By default, GCP services encrypt data at rest with Google-managed keys, transparently and with no customer configuration. **CMEK** lets a customer instead supply their own Cloud KMS key for a given resource (a Cloud Storage bucket, a BigQuery dataset, a Compute Engine disk, etc.) — the service still performs encryption/decryption transparently, but now depends on that specific KMS key, meaning the customer can revoke access or disable/destroy the key to cryptographically deny all further access to the data, independent of any IAM change.

> ⚠️ **Interview-relevant nuance:** Disabling or destroying a CMEK key does not delete the underlying data — it makes the data cryptographically unrecoverable, since the encrypted bytes on disk can no longer be decrypted without that specific key. This is why KMS key deletion has a mandatory scheduled-destruction delay (minimum 24 hours, configurable up to 30 days) rather than being instantaneous — an accidental key deletion without this safety window could otherwise instantly and irrecoverably destroy access to everything encrypted under it.

## 5. Architecture Diagram

```
              APPLICATION                                    CLOUD KMS
                  │                                       ┌────────────────────┐
      1. Request secret value                             │  Key Ring: "prod"  │
                  ▼                                       │  ┌──────────────┐  │
        ┌───────────────────┐                             │  │ Key: cmek-gcs│  │
        │  SECRET MANAGER   │                             │  │  v1 (primary)│  │
        │  Secret: db-pass  │                             │  └──────────────┘  │
        │   v1 (destroyed)  │                             └──────────┬─────────┘
        │   v2 (active)  ◄──┼── IAM: secretAccessor role             │
        │   v3 (active)     │   scoped to app-sa@...                 │ CMEK reference
        └───────────────────┘                                        ▼
                                                          ┌──────────────────┐
                                                          │ Cloud Storage    │
                                                          │ bucket encrypted │
                                                          │ with cmek-gcs    │
                                                          └──────────────────┘

    Secret Manager: stores/versions sensitive VALUES (passwords, API keys)
    Cloud KMS: creates/manages KEYS used to encrypt other services' DATA
```

## 6. Comparison with AWS and Azure

| Concept                                     | GCP                                             | AWS                                                     | Azure                                           |
| ------------------------------------------- | ----------------------------------------------- | ------------------------------------------------------- | ----------------------------------------------- |
| Secret storage                              | Secret Manager                                  | Secrets Manager (native rotation for RDS/etc.)          | Key Vault (Secrets)                             |
| Key management                              | Cloud KMS                                       | KMS (Key Management Service)                            | Key Vault (Keys)                                |
| HSM-backed keys                             | Cloud HSM / KMS HSM protection level            | CloudHSM / KMS custom key store                         | Key Vault Managed HSM                           |
| CMEK equivalent                             | CMEK (Customer-Managed Encryption Keys)         | SSE-KMS with customer-managed CMK                       | Customer-managed keys (CMK) in Key Vault        |
| Automatic rotation of the credential itself | Notification-driven, app/service-specific logic | Native rotation for several AWS-managed data stores     | Native rotation for select first-party services |
| Grouping/namespace concept                  | Key Ring                                        | No direct equivalent (keys are flat per-region, tagged) | Vault (also groups secrets/keys/certs together) |

## 7. Hands-On Example: Storing a Secret and Creating a CMEK Key

**Purpose:** Create a secret with a new version, grant an application service account read access, and create a KMS key ring/key for CMEK-encrypting a storage bucket.

```bash
echo -n "SuperSecretDbPassword123" | gcloud secrets create db-password \
  --data-file=- --replication-policy=automatic

gcloud secrets add-iam-policy-binding db-password \
  --member="serviceAccount:app-sa@my-project.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud kms keyrings create prod-keyring --location=us-central1

gcloud kms keys create cmek-gcs-key \
  --keyring=prod-keyring --location=us-central1 \
  --purpose=encryption --protection-level=hsm
```

**Expected output (abbreviated):**

```
Created version [1] of the secret [db-password].
Updated IAM policy for secret [db-password].
Created key ring [prod-keyring].
Created key [cmek-gcs-key] (protection level: HSM).
```

**Accessing the secret at runtime (from the app service account):**

```bash
gcloud secrets versions access latest --secret=db-password
```

> 💡 **Tip:** Never bake a secret's value into a build artifact or environment variable at deploy time from a fetched value that's then logged — instead, have the running workload call `secretmanager.versions.access` at startup using its own attached identity ([Section 36](./Section-36-Part5-Service-Accounts.md)), so the plaintext value never touches CI/CD logs or version control.

## 8. Production & Enterprise Usage

- **CMEK as a compliance and "crypto-shredding" tool.** Enterprises with regulatory requirements to guarantee data destruction (e.g., a tenant offboarding in a multi-tenant SaaS product) use per-tenant CMEK keys, so destroying the key cryptographically erases that tenant's data without needing to hunt down every physical copy.
- **Separate key-admin and key-user roles.** A dedicated security/platform team holds `roles/cloudkms.admin` (can create/destroy keys) while application teams hold only `roles/cloudkms.cryptoKeyEncrypterDecrypter` (can use the key but not destroy or export it) — mirroring the same admin/user separation pattern used in AWS KMS key policies.
- **Secret Manager integrated into deployment pipelines.** Instead of injecting secrets as CI/CD pipeline variables (which often end up cached or logged), enterprises configure the deployed workload to fetch secrets directly from Secret Manager at runtime using its own service account, keeping the plaintext value out of the CI/CD system's blast radius entirely.

## 9. Common Misconceptions

- **Misconception:** "Secret Manager automatically rotates my database password." Secret Manager can notify you (via Pub/Sub) that rotation is due, but it does not know how to change an arbitrary third-party system's credential itself — the actual rotation logic (calling the database to set a new password, then storing the new value as a new secret version) must be implemented by the application or an automation.
- **Misconception:** "Deleting a CMEK key deletes the data it protects." It does not delete the data — it renders the ciphertext permanently undecryptable, which is why key destruction has a mandatory delay window and should be treated with the same caution as an irreversible data-deletion operation.
- **Misconception:** "CMEK means I'm managing the encryption algorithm/process myself." The service (e.g., Cloud Storage) still performs the actual encryption/decryption transparently — CMEK only changes _which key_ is used and who controls its lifecycle, not who implements the cryptography.

## 10. Interview Questions

**🎯 Beginner:** _What's the difference between Secret Manager and Cloud KMS?_
**Model answer:** Secret Manager stores and versions sensitive values themselves — passwords, API keys, certificates — with IAM-controlled access to retrieve them. Cloud KMS manages cryptographic keys used to encrypt and decrypt data, including CMEK keys that other GCP services use to encrypt data at rest. Secret Manager holds secret values; Cloud KMS holds the keys that protect data (and, under the hood, Secret Manager's own stored values are themselves encrypted using Google-managed KMS keys).

**🎯 Intermediate:** _What happens to data encrypted with a CMEK key if that key is disabled?_
**Model answer:** The data itself is not deleted or modified — it remains on disk as ciphertext — but it becomes immediately inaccessible, since the service can no longer perform the decryption operation without an enabled key. Re-enabling the key restores access instantly, since nothing about the underlying data changed; only fully destroying the key version (after its mandatory scheduled-destruction delay) makes the data permanently unrecoverable.

**🎯 Senior/Architect:** _Design a key management and secrets strategy for a multi-tenant SaaS platform that must be able to cryptographically guarantee complete data destruction for any tenant on offboarding, and must satisfy a customer requirement for HSM-backed keys._
**Model answer:** I'd provision one Cloud KMS key per tenant (or per tenant-tier, if per-tenant key sprawl becomes operationally heavy), created at the HSM protection level to satisfy the hardware-backing requirement, organized into key rings scoped by environment and region for data residency. Each tenant's data across relevant services (Cloud Storage, BigQuery, Cloud SQL) would be CMEK-encrypted using that tenant's dedicated key. On offboarding, I'd destroy that tenant's key (respecting the mandatory destruction delay, verified by an internal approval workflow before the delay begins, per Access Approval practices in [Section 40](./Section-40-Part5-Compliance-Governance.md)), which renders every copy of that tenant's data across every service permanently unrecoverable without needing to manually locate and delete each individual record — a strong, auditable "crypto-shredding" guarantee. Application secrets (database credentials, third-party API keys) would live in Secret Manager, scoped per-tenant or per-service via IAM, accessed only by each service's own dedicated service account ([Section 36](./Section-36-Part5-Service-Accounts.md)), with rotation notifications wired to an automation that regenerates credentials and stores new versions without human handling of plaintext.

## 🔑 Key Takeaways

- 🔑 Secret Manager stores and versions sensitive values with IAM-governed, audited access; Cloud KMS manages the cryptographic keys used to encrypt data, including CMEK keys for other GCP services.
- 🔑 Cloud KMS's hierarchy is Key Ring → Key → Key Version, supporting symmetric, asymmetric-decryption, and asymmetric-signing key types at Software, HSM, or External protection levels.
- 🔑 CMEK lets a customer control the key protecting a resource's data at rest, enabling key-based access revocation and "crypto-shredding" independent of IAM changes — but key destruction carries a mandatory delay precisely because it's irreversible.
- 🔑 Secret Manager does not itself rotate arbitrary third-party credentials — it notifies and versions, while rotation logic is application/service-specific.
- 🔑 GCP's Secret Manager/Cloud KMS split maps directly to AWS's Secrets Manager/KMS and Azure Key Vault's secrets/keys split, with GCP's Key Ring having no precise one-to-one AWS equivalent.

## Related Concepts

IAM Fundamentals ([Section 35](./Section-35-Part5-IAM-Fundamentals-Members-Roles-Policies.md)), Service Accounts ([Section 36](./Section-36-Part5-Service-Accounts.md)), Security Command Center ([Section 39](./Section-39-Part5-Security-Command-Center.md)), Compliance & Governance and Cloud Audit Logs ([Section 40](./Section-40-Part5-Compliance-Governance.md)), Binary Authorization & Confidential Computing ([Section 43](./Section-43-Part5-Binary-Authorization-Confidential-Computing.md)), and Cloud SQL/BigQuery/Cloud Storage encryption-at-rest options (Sections 11, 13, 44) all build directly on the secrets and key-management concepts introduced here.
