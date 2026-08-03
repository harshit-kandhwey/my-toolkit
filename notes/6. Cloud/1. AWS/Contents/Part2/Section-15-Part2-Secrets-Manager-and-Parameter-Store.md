# Part 2 · Section 7 — Secrets Management: Secrets Manager & Parameter Store

> AWS Zero-to-Enterprise Knowledge Base · Part 2: Identity, Security & Governance

---

## 1. Definition

**Plain-language:** Instead of writing a database password into code, store it in a dedicated, access-controlled, encrypted vault; the application asks for it at runtime. Nobody reading source code sees the actual secret.

**Precise:** AWS offers two complementary services: **AWS Secrets Manager**, purpose-built for secrets requiring **automatic rotation** and fine-grained lifecycle management, and **AWS Systems Manager Parameter Store**, a general-purpose **hierarchical configuration and secrets store**. Both use **KMS** for encryption and **IAM** for access control.

---

## 2. Why It Exists

- Hardcoded credentials remain one of the most common real-world breach vectors (leaked repos, logs, container images).
- Secrets have a lifecycle problem beyond hardcoding: rotation is operationally painful to coordinate manually across multiple consumers, so in practice many orgs simply don't rotate — a standing risk analogous to long-lived IAM keys.
- Secrets Manager and Parameter Store centralize secrets outside code, control access via IAM, encrypt via KMS, and (Secrets Manager specifically) **automate rotation** so it reliably happens.

---

## 3. AWS Secrets Manager

### 3.1 Definition

Managed service for storing, retrieving, and **automatically rotating** secrets — database credentials, API keys, tokens — with built-in database integrations and a custom-rotation framework.

### 3.2 Core Capabilities

- **Encrypted storage** via KMS (CMK or `aws/secretsmanager` AWS managed key).
- **Fine-grained IAM access control** — identity-based/resource-based policy model (Section 1) governs which principals can retrieve which secret.
- **Automatic rotation** — invokes a Lambda on a schedule to rotate the value, no downtime if implemented correctly (§3.4).
- **Native database integration** — built-in rotation templates for RDS, Aurora, DocumentDB, Redshift.
- **Versioning** — `AWSCURRENT`, `AWSPENDING`, `AWSPREVIOUS` staged versions supporting safe rotation.

### 3.3 Retrieving a Secret

Apps retrieve via SDK (`GetSecretValue`), authenticated using the compute resource's attached IAM role (Section 3) — never a hardcoded credential to access the store itself. Key point: **you still need an AWS credential to retrieve the secret, but it's a temporary auto-rotating role credential, not the sensitive secret itself.**

### 3.4 Automatic Rotation Mechanics (Zero-Downtime)

1. **`createSecret`** — rotation Lambda generates a new credential, stores as `AWSPENDING`, without touching the live system yet.
2. **`setSecret`** — Lambda applies the new credential to the actual target service (e.g., changes the DB password).
3. **`testSecret`** — Lambda verifies the new credential actually works.
4. **`finishSecret`** — promotes `AWSPENDING` to `AWSCURRENT` (old current becomes `AWSPREVIOUS`).

> 🔑 The new credential is created, applied, and verified **before** promotion — a failure at any step is caught before applications ever get a broken credential. Apps mid-rotation keep using the still-valid `AWSCURRENT` version throughout.

---

## 4. AWS Systems Manager Parameter Store

### 4.1 Definition

Part of Systems Manager (full depth Part 8) — a hierarchical, general-purpose store for configuration data and secrets, organized under path-like names (`/myapp/production/db-host`).

### 4.2 Parameter Types

| Type         | Encrypted?    | Use                                                            |
| ------------ | ------------- | -------------------------------------------------------------- |
| String       | No            | Non-sensitive config (feature flag, non-secret hostname)       |
| StringList   | No            | Comma-separated non-sensitive list                             |
| SecureString | **Yes (KMS)** | Sensitive values — Parameter Store's actual secrets capability |

### 4.3 Standard vs Advanced Parameters

- **Standard** — free, moderate parameter count/value size, sufficient for most use.
- **Advanced** — small per-parameter charge, larger count/size limits, parameter policies (e.g., expiration notifications).

### 4.4 Hierarchical Organization

- Path-structured names (`/myapp/production/database/password`) let you retrieve a group at once (`GetParametersByPath`) and scope IAM to a **path prefix** — e.g., a production role limited to `/myapp/production/*`, cleanly separated from staging.

---

## 5. Secrets Manager vs Parameter Store — Decision Framework

|                       | Secrets Manager                                               | Parameter Store (SecureString)                                              |
| --------------------- | ------------------------------------------------------------- | --------------------------------------------------------------------------- |
| Cost                  | Per-secret monthly + API call charges                         | Free (Standard); small charge (Advanced)                                    |
| Automatic rotation    | **Built-in**, native DB integrations                          | **No built-in rotation** — you'd rebuild it yourself via EventBridge+Lambda |
| Best for              | Database credentials, API keys needing rotation               | General config, non-rotating secrets                                        |
| Cross-account sharing | Native resource-based policy support                          | More limited, more manual setup                                             |
| Versioning            | Staged (`AWSCURRENT`/`AWSPENDING`/`AWSPREVIOUS`) for rotation | Simpler linear history, no rotation-staging                                 |

> 🎯 **Clean summary:** needs automatic rotation (most DB credentials) → Secrets Manager. General config or non-rotating secret → Parameter Store SecureString (more cost-effective).

---

## 6. Access Control for Secrets

- Governed by standard IAM identity-based policies — e.g., `secretsmanager:GetSecretValue` scoped to a specific ARN, or `ssm:GetParameter` scoped to a path.
- Secrets Manager also supports **resource-based policies** directly on a secret — enables cross-account sharing without duplicating the secret, same pattern as S3 bucket policies/KMS key policies.
- Least privilege applies fully — scope to the exact secret/path, never broad `secretsmanager:*` or `"Resource": "*"`.

---

## 7. Production & Enterprise Usage

- **CI/CD integration:** pipelines using OIDC federation (Section 3 §10) retrieve deployment secrets from Secrets Manager/Parameter Store instead of static CI/CD secrets — fully credential-hardcoding-free deployment.
- **Multi-environment configuration:** Parameter Store hierarchical paths per environment (`/myapp/dev/`, `/myapp/staging/`, `/myapp/production/`), IAM scoped per environment role to its own path.
- **Database credential rotation at scale:** enterprises with many databases rely on Secrets Manager's native rotation templates because manual rotation doesn't scale — worth the cost for the operational risk removed.
- **Secrets replication:** Secrets Manager supports multi-region secret replication (mirrors KMS multi-region keys) for DR requirements (Part 10).

---

## 8. Security Considerations

- **Never log secret values** — a common real-world leak: an app logging a retrieved secret in debug/error output.
- **CloudTrail logs every secret retrieval** (`GetSecretValue`, `GetParameter`) — audit trail of exactly who accessed what, when.
- **Rotation doesn't replace least-privilege access control** — both are needed together; complementary, not substitutes.

---

## 9. Cost Considerations

- Secrets Manager charges **per secret/month + per API call** — relevant for apps calling it very frequently rather than briefly caching a retrieved secret.
- Parameter Store Standard tier is **free** — the more cost-effective default for the large volume of non-rotating config, reserving Secrets Manager for values that genuinely need rotation.

---

## 10. Troubleshooting

| Symptom                                          | Cause                                                               | Fix                                                                                   |
| ------------------------------------------------ | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| App can't retrieve secret — AccessDenied         | IAM policy doesn't grant the specific action/ARN                    | Verify identity-based (and resource-based, for Secrets Manager) policy scoping        |
| Rotation Lambda fails partway                    | A stage failed (often testSecret — new credential doesn't work yet) | Review rotation Lambda logs for the failing stage; apps unaffected until finishSecret |
| App briefly fails auth right after rotation      | App cached an old credential, didn't re-fetch                       | Re-retrieve the secret rather than caching indefinitely                               |
| SecureString parameter returns encrypted/garbled | Called GetParameter without `--with-decryption`                     | Include the decryption flag                                                           |

---

## 11. Best Practices & Anti-Patterns

**Best practices:** use Secrets Manager for anything needing rotation, Parameter Store SecureString otherwise; never hardcode secrets anywhere; scope IAM to the specific secret/path; enable native rotation templates for supported databases; never log secret values.

**Anti-patterns:** storing a rotation-needing secret in Parameter Store to save cost, then never rotating manually; broad `secretsmanager:*` access "just in case"; retrieving secrets on every request without caching; treating rotation as a substitute for access control or vice versa.

---

## 12. Common Misconceptions

- "Secrets Manager and Parameter Store are interchangeable." → False — rotation need is the deciding factor.
- "Parameter Store SecureString is 'less encrypted' since it's cheaper." → False — genuinely uses KMS; difference is rotation capability and pricing, not encryption strength.
- "Automatic rotation causes downtime." → False with the staged process — apps use AWSCURRENT until the new version is verified and promoted.
- "An IAM role that can retrieve a secret 'is' the credential." → False — the role's STS credentials authenticate the retrieval request; the secret value is a separate returned piece of data.

---

## 13. Interview Questions (with model answers)

**🟢 Why not store a DB password in application code?** Hardcoded credentials are a common real-world breach vector (public repos, logs, container images, hard to fully purge from history). A secrets service means the app retrieves it at runtime via its own IAM permissions; the secret never appears in source code.

**🟢 Secrets Manager vs Parameter Store?** Secrets Manager: purpose-built for automatic rotation, native DB integrations. Parameter Store SecureString: more cost-effective general-purpose sensitive config without rotation. Rotation need decides which.

**🟡 How does Secrets Manager achieve zero-downtime rotation?** Four-step Lambda: createSecret (generate new value, pending, live system untouched), setSecret (apply new credential to target), testSecret (verify it works), finishSecret (promote pending to current). Failure caught before promotion — apps keep using still-valid current version throughout.

**🟡 Share a secret with another account without duplicating it?** Resource-based policy directly on the secret (like S3/KMS pattern) granting the specific principal in the other account retrieval permission — one source of truth instead of two to keep in sync.

**🔴 Design secrets strategy for multi-environment, multi-database app + CI/CD?** Secrets Manager with native rotation templates per RDS/Aurora instance. Parameter Store hierarchical paths per environment (/myapp/dev/, /staging/, /production/), IAM scoped per role to its own path prefix. CI/CD uses OIDC federation to assume a deployment role, retrieving deployment secrets directly rather than static pipeline secrets — no hardcoded credentials anywhere. Production secrets get tighter scoping/rotation permissions than dev.

**🔴 Rotation Lambda fails at testSecret at 2am for a critical prod DB — what happens and what's the on-call process?** Nothing happens to the running app — AWSCURRENT is untouched; only AWSPENDING has an unverified, unpromoted credential. App keeps authenticating successfully with the still-valid current credential. The real issue is rotation didn't complete (investigate why testSecret failed — connectivity, Lambda permissions, DB-side constraint). Treat as next-business-day investigation, not a page-worthy emergency, since zero-downtime design means no live impact — but monitor for repeated failures as a slow-building risk.

---

## 🔑 Key Takeaways

1. Secrets Manager and Parameter Store both solve "don't hardcode credentials," but the deciding factor is **automatic rotation need** — Secrets Manager if yes, Parameter Store SecureString if no.
2. Secrets Manager's rotation is a staged four-step Lambda process (createSecret → setSecret → testSecret → finishSecret) designed for zero downtime.
3. Both use KMS for encryption and IAM for access control — same least-privilege/resource-based-policy/cross-account patterns as Sections 1, 2, 6.
4. Applications still need an AWS credential (role's STS credentials) to retrieve a secret — the secrets service and the AWS-access credential are distinct, complementary layers.
5. Rotation and access control are complementary, not substitutes — both are needed together.

## 🌐 Related Concepts (forward links)

- Systems Manager's broader capabilities (Session Manager, Automation, Patch Manager) → Part 8
- RDS/Aurora-specific rotation integration → Part 6
- Threat detection against everything built so far → §16 (next)
