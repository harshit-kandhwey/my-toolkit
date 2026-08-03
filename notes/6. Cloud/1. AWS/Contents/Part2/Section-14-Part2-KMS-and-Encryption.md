# Part 2 · Section 6 — Data Protection: KMS & Encryption

> AWS Zero-to-Enterprise Knowledge Base · Part 2: Identity, Security & Governance

---

## 1. Definition

**Plain-language:** AWS KMS creates and controls the cryptographic keys that scramble/unscramble your data, so a copy of raw storage is unreadable without permission to use the right key.

**Precise:** **AWS Key Management Service (KMS)** is a managed service for **creating, storing, controlling, and auditing cryptographic keys** used to encrypt/decrypt data across AWS services, backed by **FIPS 140-2 validated HSMs**, governed by IAM-style key policies and logged via CloudTrail.

> 💡 **Mental model:** KMS is a secure locksmith's vault — you bring data to be locked/unlocked using a key that never leaves the vault; every request is checked against a permission list and logged.

---

## 2. Why It Exists

- **Defense in depth:** IAM/SCPs (Sections 1–5) control access, but access controls can be misconfigured or bypassed. Encryption protects data even if access control fails — exfiltrated ciphertext is useless without the key.
- **The hard part is key management**, not cryptography itself — safely generating, storing, rotating, and controlling access to keys at scale. KMS solves key management, not new crypto.
- **Compliance:** HIPAA, PCI DSS, etc. mandate encryption at rest/in transit — KMS is the AWS-native mechanism to satisfy and evidence these requirements.

---

## 3. Encryption Fundamentals

- **Encryption at rest** — protects stored data.
- **Encryption in transit** — protects data moving over a network (TLS/HTTPS).
- **Symmetric encryption** — same key encrypts and decrypts; faster, default for most AWS features.
- **Asymmetric encryption** — key pair (public/private); used for signing or when the encrypting party shouldn't decrypt.
- **Envelope encryption** — the KMS-at-scale pattern (§5): encrypt data with a fast local key, encrypt that key with a KMS master key.
- **Plaintext vs ciphertext** — readable vs encrypted/unreadable.

---

## 4. KMS Keys — Types and Structure

### 4.1 KMS Keys

- Core KMS resource. Typically used via envelope encryption rather than directly encrypting large data.
- **Never leaves KMS in plaintext** — key material stays inside the HSM boundary.

### 4.2 Key Types by Origin

| Key type                                | Who manages material                           | Use case                                                     |
| --------------------------------------- | ---------------------------------------------- | ------------------------------------------------------------ |
| AWS owned keys                          | AWS (invisible to you)                         | Default encryption, zero setup, no visibility/control        |
| AWS managed keys                        | AWS (auto, per service/account, e.g. `aws/s3`) | Free, automatic default encryption                           |
| Customer managed keys (CMKs)            | You (policy, rotation, deletion)               | Fine-grained access control, custom rotation, detailed audit |
| Customer-provided/imported key material | You supply it                                  | Regulatory requirements mandating external key generation    |

> 🎯 AWS owned/managed = convenient, free, minimal control. CMKs = small monthly fee, full control over policy/rotation/deletion — choose CMKs for fine-grained control or audit trail needs.

### 4.3 Symmetric vs Asymmetric KMS Keys

- **Symmetric** — default, most common (S3, EBS, RDS integrations).
- **Asymmetric** — digital signing/verification, or encryption where the public key must be distributed outside AWS.

---

## 5. Envelope Encryption — Core Mechanism

### 5.1 Why It Exists

Sending large data through KMS for every operation would be slow and load-heavy. Envelope encryption uses KMS only to protect a small key, not the data itself.

### 5.2 The Process

1. App calls KMS `GenerateDataKey`, referencing a KMS key.
2. KMS returns a **plaintext data key** + an **encrypted copy** of that same data key.
3. App uses the plaintext data key to encrypt actual data **locally** (fast, no further KMS calls).
4. App discards the plaintext data key; stores only the encrypted data key + encrypted data.
5. **To decrypt:** app sends the encrypted data key to KMS `Decrypt`, gets back the plaintext data key, decrypts data locally.

```
ENCRYPT: App→KMS: GenerateDataKey → KMS→App: [Plaintext DK] + [Encrypted DK]
         App: Encrypt(Data, Plaintext DK) locally → store [Encrypted Data]+[Encrypted DK]; discard plaintext DK

DECRYPT: App→KMS: Decrypt(Encrypted DK) → KMS→App: [Plaintext DK]
         App: Decrypt(Encrypted Data, Plaintext DK) locally
```

> 🔑 Only the small data key touches KMS directly; the (potentially huge) data is encrypted/decrypted entirely locally. The KMS key never leaves KMS; the plaintext data key exists only transiently in memory. This is how S3/EBS/RDS encryption stays fast at scale.

---

## 6. Key Policies

- Every KMS key has a **key policy** — a resource-based policy governing who can manage/use it.
- **Critical default:** unlike most resources, an IAM policy alone is typically **not sufficient** to grant KMS access — the key policy is the primary gate (commonly delegated to IAM via an account-root statement).
- **Key administrators vs key users** — key policies commonly separate who can manage (rotate, delete, modify policy) from who can merely use (encrypt/decrypt) the key.

> ⚠️ A correct IAM policy granting `kms:Decrypt` can still yield AccessDenied if the key policy doesn't also permit it — KMS's most common real troubleshooting scenario.

---

## 7. Key Rotation

- **AWS managed keys:** automatic rotation on AWS's fixed schedule, no configuration.
- **Customer managed keys:** optional automatic **annual** rotation — old key material versions are retained, so previously encrypted data stays decryptable; no re-encryption needed.
- **Manual rotation** — create a new key and re-encrypt data, used to fully retire old material or for keys (like asymmetric) that generally require manual handling.

---

## 8. Encryption Context

- Optional key-value pairs supplied with encrypt/decrypt requests, acting as **additional authenticated data (AAD)** — must match exactly on both sides; included unencrypted in ciphertext metadata and CloudTrail logs.
- Cryptographically binds ciphertext to its context (e.g., `{"table":"customers","purpose":"PII"}`) — decryption fails with wrong context; adds useful audit detail.

---

## 9. Where Encryption Applies

- **At rest, service-integrated** — S3, EBS, RDS, DynamoDB etc. offer built-in server-side encryption via KMS, envelope encryption happening transparently.
- **In transit** — TLS/HTTPS, a separate mechanism from KMS (certificate-based key exchange), often discussed together as a complete data-protection story.
- **Client-side encryption** — app encrypts data before sending to AWS (AWS Encryption SDK, often using KMS underneath) — strongest model, AWS never sees plaintext, more implementation complexity.

> 🔑 Recall §5 (Shared Responsibility Model): encryption **enablement** is always a customer responsibility across every service tier — AWS provides the tooling, you must turn it on and configure it.

---

## 10. Production & Enterprise Usage

- **Encryption-by-default enforcement via SCPs/Config:** deny creation of unencrypted resources (e.g., S3 buckets without default encryption, unencrypted EBS volumes) — turns policy into an unbypassable technical control.
- **Multi-region keys:** shared key material across Regions, enabling encrypted data replication (DR, Part 10) without decrypt-and-re-encrypt.
- **Separation of duties:** key administrators (security team) separate from key users (application teams) via key policy admin/user distinction.
- **Cross-account key sharing:** a key policy can grant usage to principals in another account (e.g., centralized logging account decrypting data from many source accounts) without duplicating keys.

---

## 11. Security Considerations

- **Key deletion is deliberately hard to do accidentally** — irreversible, destroys decrypt ability for everything under it; KMS enforces a mandatory 7–30 day waiting period, cancellable during that window.
- **Least privilege on key policies** matters as much as IAM policies — an overly permissive key policy undermines the point of encrypting.
- **CloudTrail logs every KMS usage** — every Encrypt/Decrypt/GenerateDataKey call with the calling principal (Part 8 full depth).

---

## 12. Performance Considerations

- Envelope encryption is exactly what keeps KMS-integrated services fast even for large data — actual data never transits KMS.
- **KMS API request quotas exist** (varying by action/Region) — high-throughput direct KMS callers should consider brief in-memory data-key caching rather than calling GenerateDataKey per small operation.

---

## 13. Troubleshooting

| Symptom                                                | Cause                                                                              | Fix                                                                                |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| AccessDenied on kms:Decrypt despite correct IAM policy | Key policy doesn't grant this principal — IAM alone isn't automatically sufficient | Review/update the key policy itself                                                |
| Can't decrypt data from before a rotation              | Misconception — shouldn't happen                                                   | KMS retains old key versions; investigate other causes (e.g., accidental deletion) |
| Accidentally scheduled key deletion                    | Delete action run without realizing consequences                                   | Cancel deletion during the mandatory waiting window                                |
| Encrypt/decrypt fails with encryption context mismatch | Context must match exactly on both sides                                           | Ensure identical context key-value pairs on both operations                        |

---

## 14. Best Practices & Anti-Patterns

**Best practices:** use CMKs when fine-grained control/audit is needed; enable automatic annual rotation on CMKs; separate key admins from key users; enforce encryption via SCPs/Config; use encryption context for sensitive data.

**Anti-patterns:** assuming IAM alone suffices for KMS access; deleting a key without understanding irreversible consequences; relying solely on AWS managed keys when fine-grained control is genuinely needed; calling GenerateDataKey per-record at extreme throughput without caching considerations.

---

## 15. Common Misconceptions

- "IAM policy granting kms:Decrypt is enough." → False — key policy must also permit it.
- "KMS sends all my data through the service." → False — envelope encryption keeps data local; only the small data key touches KMS.
- "Key rotation breaks previously encrypted data." → False — old key material is retained indefinitely.
- "Deleting a KMS key is quick and immediate." → False — mandatory waiting period specifically because it's irreversible.

---

## 16. Interview Questions (with model answers)

**🟢 What is KMS, and why does it matter even with IAM already controlling access?** Manages cryptographic keys for encrypting/decrypting data. Matters as a separate defense-in-depth layer — even if access controls fail, encrypted data stays unreadable without the key, which KMS tightly controls and audits independently.

**🟢 AWS managed key vs customer managed key?** AWS managed: automatic, free, no config, minimal control — good default. Customer managed: you control policy/rotation/deletion, small monthly cost — choose when you need fine-grained access control or a detailed usage audit trail.

**🟡 Explain envelope encryption and why AWS uses it.** GenerateDataKey returns a plaintext data key + encrypted copy; app encrypts data locally with the plaintext key, discards it, stores only the encrypted key + encrypted data; decrypt sends the encrypted key back to KMS to get the plaintext key back, then decrypts locally. Only a small key ever transits KMS — keeps large-object encryption (S3, EBS) fast.

**🟡 IAM policy grants kms:Decrypt but still AccessDenied — why?** IAM alone usually isn't sufficient for KMS — the key's own resource-based key policy is the primary gate and must also permit the principal (or delegate to IAM via an account-root statement). Fix the key policy, not just IAM.

**🔴 Design encryption strategy for a multi-account org handling regulated healthcare data?** Use customer managed keys for audit trail/control. Centralize key administration in a dedicated Security account; app-account roles get only encrypt/decrypt usage rights (separation of duties). Grant cross-account decrypt needs (e.g., centralized logging) via the key policy rather than duplicating keys. Enable automatic annual rotation; use encryption context to bind ciphertext to data classification. Enforce encryption-required via SCP. Centralize CloudTrail capture of all key usage.

**🔴 Team accidentally scheduled deletion of a production KMS key used by an active RDS database — response?** Cancel the scheduled deletion immediately within the mandatory 7–30 day window — key material isn't destroyed yet, so no backup/data-recovery needed if caught in time. Afterward, review why deletion was possible (tighten key policy to a small admin set), and add a CloudTrail alert on ScheduleKeyDeletion events in production going forward.

---

## 🔑 Key Takeaways

1. KMS protects data as a layer independent of access control — a defense that holds even if IAM/SCP controls fail.
2. AWS owned/managed/customer managed keys trade convenience/cost against control/audit — use CMKs for fine-grained needs.
3. Envelope encryption is the core mechanism — only a small data key transits KMS; data is encrypted/decrypted locally, keeping things fast.
4. A KMS key's resource-based key policy is the primary access gate — IAM alone is typically insufficient; both must align.
5. Key deletion is deliberately hard to do accidentally (7–30 day wait); key rotation is deliberately safe (old material always retained).

## 🌐 Related Concepts (forward links)

- Secrets Manager and Parameter Store (use KMS under the hood) → §15
- Service-specific encryption (S3 SSE, EBS, RDS) → Parts 5 and 6
- TLS/certificate management via AWS Certificate Manager → Part 4
