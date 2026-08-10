# Section 94 (Part 13): Cloud-Native Secrets Managers (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager)

## 1. Definition

**Plain language:** Every major cloud provider has its own built-in secrets storage service — AWS Secrets Manager, Azure Key Vault, and GCP Secret Manager — that stores secret values encrypted at rest, controls who can read them via the cloud's native IAM, and can rotate credentials automatically. Terraform can read secrets from these services at plan/apply time using provider-specific data sources, without needing a separate Vault deployment.

**Precise definition:** A **cloud-native secrets manager** is a managed service provided by a cloud vendor for storing, versioning, encrypting, and controlling access to secret values, integrated natively with that cloud's IAM system. Terraform integrates with these services via read-only **data sources** — `data "aws_secretsmanager_secret_version"`, `data "azurerm_key_vault_secret"`, and `data "google_secret_manager_secret_version"` — that fetch a secret's current (or a specific) version at plan/apply time, and via corresponding **resource** types (`aws_secretsmanager_secret_version`, `azurerm_key_vault_secret`, `google_secret_manager_secret_version`) when Terraform is responsible for _writing_ a secret into the manager (as seen in [§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)'s `random_password` example). As with Vault, reading a secret through a data source into a resource argument still writes that secret's value into Terraform state ([§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) — the cloud-native manager protects the secret's storage at its own source, not the copy that ends up in state.

> 💡 **Tip:** The three providers' data sources are structurally similar (fetch-secret-by-name-or-ARN, return current or pinned version) but each cloud's rotation, versioning, and access-control model differs enough that "just swap the data source name" migrations between clouds routinely miss version-pinning or rotation-timing edge cases specific to each service.

## 2. Why This Matters

- **Avoids standing up and operating a separate Vault cluster** for organizations already committed to a single cloud, trading some of Vault's cross-cloud flexibility and dynamic-secrets sophistication for lower operational overhead.
- **Access control is native to the cloud's existing IAM system** — the same policies, roles, and audit trail (CloudTrail, Azure Activity Log, Cloud Audit Logs) already used for every other resource extend naturally to secrets, rather than requiring a parallel policy system.
- **Built-in automatic rotation** (particularly AWS Secrets Manager's native RDS/Redshift/DocumentDB rotation, and Azure Key Vault's rotation policies) reduces the operational burden of manually rotating credentials that Vault's dynamic secrets solve differently.
- **Most Terraform configurations already authenticate to a single cloud provider** — reusing that same cloud's secrets manager means no additional authentication mechanism (a separate Vault auth method) needs to be designed and secured.
- **A very common real-world default**: teams not already invested in Vault overwhelmingly reach for their cloud's native secrets manager first, making these data sources some of the most frequently used secret-handling patterns in production Terraform.

## 3. Prerequisites and Dependencies

This section assumes the same [§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) foundation as [§93](./Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md) — that any secret value read into a Terraform resource argument, regardless of source, ends up in state plaintext. It's a direct sibling to [§93](./Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md) (Vault integration), covering the alternative, single-cloud approach to the same underlying problem. Provider authentication basics ([§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md)) are a prerequisite, since these data sources authenticate using the same cloud provider credentials already configured for the `aws`/`azurerm`/`google` providers generally — there is no separate secrets-manager-specific authentication layer.

## 4. Architecture / Conceptual Diagram

```text
   LAYERED SECRET-PROTECTION MODEL (cloud-native managers in context)

   ┌────────────────────────────────────────────────────────────────┐
   │  Layer 4: Static Analysis / Scanning (§96)                     │
   │  Catches hardcoded secrets and misconfigurations BEFORE apply  │
   └────────────────────────────────────────────────────────────────┘
   ┌──────────────────────────────────────────────────────────────────┐
   │  Layer 3: Secret Source of Truth                                 │
   │  Vault (§93)  OR  AWS Secrets Manager / Azure Key Vault /        │
   │  GCP Secret Manager (this section) — encrypted at rest,          │
   │  IAM-controlled, versioned, some support rotation                │
   └──────────────────────────────────────────────────────────────────┘
                │  data source read at plan/apply
                ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  Layer 2: Least-Privilege Execution IAM (§95)                    │
   │  The Terraform execution role's OWN permission to read the       │
   │  secrets manager must itself be narrowly scoped                  │
   └──────────────────────────────────────────────────────────────────┘
                │  secret value now flows into resource config
                ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │  Layer 1: Encrypted, Access-Controlled Backend (§98)             │
   │  The value is now ALSO in terraform.tfstate — this layer is      │
   │  what actually protects that copy (§92's core risk)              │
   └──────────────────────────────────────────────────────────────────┘

   No single layer is sufficient alone — a cloud-native secrets
   manager protects the SOURCE; it does nothing for the COPY that
   lands in state the moment a data source reads it into a resource.
```

- Cloud-native secrets managers occupy the same conceptual position as Vault in this layered model — they're the "Layer 3" source of truth, interchangeable in role but differing in operational model.
- Reading from any of these sources still requires the Terraform execution role to have IAM permission to do so — which is itself a least-privilege concern ([§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)), independent of the secrets manager's own access controls.
- The layered diagram makes explicit what [§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) established: no layer here removes the need for Layer 1 (encrypted backend) — they're additive, not substitutive.

## 5. Hands-On

### 5.1 AWS Secrets Manager — `data "aws_secretsmanager_secret_version"`

**Purpose:** Fetch a secret's current value from AWS Secrets Manager for use in a resource argument.

**Syntax:**

```hcl
data "aws_secretsmanager_secret_version" "db" {
  secret_id = "app/db-credentials"
}

locals {
  db_creds = jsondecode(data.aws_secretsmanager_secret_version.db.secret_string)
}

resource "aws_db_instance" "main" {
  identifier = "app-db"
  username   = local.db_creds["username"]
  password   = local.db_creds["password"]
  # ...
}
```

**Example usage and expected output:**

```bash
$ terraform apply
data.aws_secretsmanager_secret_version.db: Reading...
data.aws_secretsmanager_secret_version.db: Read complete after 0s

  # aws_db_instance.main will be created
  + password = (sensitive value)
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** Common in AWS-only shops storing application secrets that were provisioned once (perhaps by a bootstrap process or manually) and are consumed, not managed, by Terraform — Terraform reads but does not own the secret's lifecycle.

**Common errors:** `AccessDeniedException: User is not authorized to perform: secretsmanager:GetSecretValue` — the Terraform execution role's IAM policy lacks the `secretsmanager:GetSecretValue` action on that secret's ARN; a least-privilege policy scoped too narrowly (or not updated for a new secret) is the usual cause.

### 5.2 Azure Key Vault — `data "azurerm_key_vault_secret"`

**Purpose:** Fetch a secret from Azure Key Vault.

**Syntax:**

```hcl
data "azurerm_key_vault" "main" {
  name                = "app-kv"
  resource_group_name = "app-rg"
}

data "azurerm_key_vault_secret" "db_password" {
  name         = "db-password"
  key_vault_id = data.azurerm_key_vault.main.id
}

resource "azurerm_postgresql_flexible_server" "main" {
  name                = "app-db"
  administrator_login = "appadmin"
  administrator_password = data.azurerm_key_vault_secret.db_password.value
  # ...
}
```

**Example usage and expected output:**

```bash
$ terraform apply
data.azurerm_key_vault.main: Reading...
data.azurerm_key_vault_secret.db_password: Reading...
data.azurerm_key_vault_secret.db_password: Read complete after 1s

  # azurerm_postgresql_flexible_server.main will be created
  + administrator_password = (sensitive value)
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** Azure Key Vault access policies or RBAC role assignments (`Key Vault Secrets User`) must grant the Terraform execution identity (often an Azure AD service principal or managed identity) explicit access — Key Vault's own access model is a second gate independent of the general `azurerm` provider authentication.

**Common errors:** `Error: checking for presence of existing Secret` with a 403 — the service principal running Terraform has network/Azure AD authentication working but lacks a Key Vault access policy or RBAC role granting `Get` on secrets; distinct from a general auth failure and easy to misdiagnose as one.

### 5.3 GCP Secret Manager — `data "google_secret_manager_secret_version"`

**Purpose:** Fetch a secret version from GCP Secret Manager.

**Syntax:**

```hcl
data "google_secret_manager_secret_version" "db_password" {
  secret  = "db-password"
  project = "my-project-id"
}

resource "google_sql_user" "app" {
  name     = "app"
  instance = google_sql_database_instance.main.name
  password = data.google_secret_manager_secret_version.db_password.secret_data
}
```

**Example usage and expected output:**

```bash
$ terraform apply
data.google_secret_manager_secret_version.db_password: Reading...
data.google_secret_manager_secret_version.db_password: Read complete after 0s

  # google_sql_user.app will be created
  + password = (sensitive value)
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** By default this data source reads the `latest` version unless a `version` argument pins a specific one — teams requiring reproducible applies (avoiding a secret rotation silently changing what the next `apply` reads) explicitly pin `version` rather than tracking `latest`.

**Common errors:** `Error: Secret Version "latest" not found` — the referenced secret exists but has no enabled version (e.g., all versions were disabled/destroyed), or the service account lacks `secretmanager.versions.access` IAM permission on the secret.

## 6. Production Usage Notes

- **Version pinning behavior differs by provider** — GCP's `latest` alias and AWS's default "current" stage retrieval both mean a data source's read result can silently change between applies if the underlying secret is rotated externally; pin explicit versions where reproducibility matters more than always-fresh values.
- **Each service's IAM/access-policy model is a genuinely separate gate from general provider authentication** — having valid AWS/Azure/GCP credentials does not imply access to a specific secret; that requires an explicit grant (`secretsmanager:GetSecretValue`, Key Vault access policy/RBAC, `secretmanager.versions.access`) scoped to that secret.
- **Automatic rotation (particularly AWS Secrets Manager's native rotation for supported databases) happens outside Terraform's control** — a rotated secret means the _next_ `terraform apply`'s data source read returns a new value, which can trigger unexpected resource updates if that value flows into an argument that isn't itself idempotent to reapply.
- **These data sources make a read-only dependency on infrastructure Terraform doesn't manage** — the secret itself is often created and rotated by a separate process (application team, security team), and Terraform is only a consumer; this separation of ownership is often intentional and should be preserved rather than having Terraform also manage the secret's lifecycle.

## 7. Security Considerations

- **As with Vault, reading a cloud-native secret into a resource argument still writes that value into Terraform state plaintext** — none of AWS Secrets Manager, Azure Key Vault, or GCP Secret Manager change [§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)'s core fact; they protect the source, not the state copy.
- **The Terraform execution role's own IAM permission to read secrets is a distinct least-privilege surface ([§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md))** — granting broad `secretsmanager:GetSecretValue` on `*` (all secrets) to a CI pipeline's execution role means a compromised pipeline can read every secret in the account, not just the ones its configuration actually needs; scope to specific ARNs/paths/vault names.
- **Cross-account/cross-subscription/cross-project secret access introduces additional trust boundaries** — a Terraform run in one AWS account reading a secret from another account's Secrets Manager (via resource policies) needs that trust relationship reviewed with the same scrutiny as any cross-account IAM grant.
- **Encryption at rest is generally automatic and vendor-managed for these services** (AWS Secrets Manager uses KMS, Azure Key Vault has its own HSM-backed encryption, GCP Secret Manager encrypts by default) — the meaningfully configurable security surface is access control (who/what can read a given secret), not whether encryption happens at all.
- **Logging/audit trail (CloudTrail `GetSecretValue` events, Azure Activity Log, GCP Cloud Audit Logs) should be monitored for secret reads by the Terraform execution identity**, both as a detective control and because unexpected read volume/timing can indicate a compromised pipeline.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                   | Likely Cause                                                                                                                 | Resolution Path                                                                                                                                                                                     |
| ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AccessDeniedException` / 403 reading a secret despite valid provider auth                | Execution role/service principal/service account lacks the specific secret-read permission, distinct from general cloud auth | Add the narrowly-scoped IAM policy/access-policy/RBAC grant for that specific secret ARN/vault/project ([§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) principles) |
| Secret value unexpectedly changes on a re-apply with no config change                     | Underlying secret was rotated externally and the data source tracks `latest`/current version                                 | Pin an explicit version if reproducibility is required; otherwise treat this as expected behavior                                                                                                   |
| `Error: Secret Version "latest" not found`                                                | All versions of the secret are disabled/destroyed, or the secret was deleted                                                 | Verify the secret has at least one enabled version; check for accidental deletion/disable by another process                                                                                        |
| Terraform plan shows an unexpected resource replacement tied to a secret-derived argument | A rotated secret value fed into an argument that forces resource replacement (e.g., certain immutable arguments)             | Review whether that argument should source from a stable reference rather than a rotating secret value, or use `ignore_changes` deliberately if appropriate                                         |

## 9. Best Practices

- Scope IAM/access-policy grants to specific secret ARNs/vault-and-secret-names/projects, never wildcard access to "all secrets," for the Terraform execution identity.
- Pin explicit secret versions when an apply's reproducibility matters more than always reading the newest value; use `latest`/current only when always-fresh reads are actually desired.
- Keep secret _ownership_ (creation, rotation policy) separate from Terraform where a dedicated security/platform team already manages it — Terraform as a read-only consumer via data sources is often the right boundary, not full lifecycle management.
- Enable and monitor audit logging for secret access events tied to the Terraform execution identity specifically.
- Prefer the cloud's native automatic-rotation features (AWS Secrets Manager rotation Lambdas, Key Vault rotation policies) over manual rotation processes where the target resource type supports it.

## 10. Common Anti-Patterns / Mistakes

- **Granting the Terraform execution role wildcard read access to an entire secrets manager namespace** ("just give it `secretsmanager:GetSecretValue` on `*`") instead of scoping to the specific secrets that configuration needs.
- **Having Terraform both create and continuously read-back the same secret** in ways that create update loops if the secret manager's stored value and Terraform's expected value drift for reasons outside Terraform's control (e.g., an external rotation Lambda).
- **Assuming a cloud-native secrets manager makes the state file safe.** Exactly the same misconception as with Vault ([§93](./Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md)) — the manager protects its own storage, not the plaintext copy in state.
- **Using `latest`/current-version reads where an immutable, auditable, pinned version was actually required** for compliance or reproducibility reasons.

## 11. Interview Questions

**🎯 Beginner:** _"Name the Terraform data source used to read a secret from AWS Secrets Manager."_
**Model answer:** `data "aws_secretsmanager_secret_version"`, typically referencing the secret by `secret_id` (name or ARN), with the resulting `secret_string` often JSON-decoded via `jsondecode()` if the secret stores multiple key-value fields.
_What the interviewer is probing for:_ Basic hands-on familiarity with the exact resource/data source name, not just conceptual awareness.

**🎯 Intermediate:** _"What's the difference between the access control model for Azure Key Vault secrets and general `azurerm` provider authentication?"_
**Model answer:** General `azurerm` provider authentication establishes that a given service principal or managed identity can authenticate to Azure at all (via Azure AD). Key Vault has its own separate access-control layer on top of that — either legacy access policies or Azure RBAC role assignments (e.g., `Key Vault Secrets User`) — that must explicitly grant that same identity permission to read secrets from a specific vault. Valid Azure authentication alone does not imply Key Vault access; both gates must be satisfied.
_What the interviewer is probing for:_ Understanding that cloud-native secrets managers layer their own access control on top of, not instead of, the base provider authentication — a frequent source of confusing 403 errors.

**🎯 Senior:** _"Your team wants to migrate from a self-managed HashiCorp Vault cluster to AWS Secrets Manager to reduce operational overhead. What capability would they most likely give up, and does it matter for their use case?"_
**Model answer:** The main capability gap is Vault's dynamic secrets model — Vault can generate short-lived, on-demand credentials via secrets engines (e.g., database engine) with automatic revocation on lease expiry, providing a materially different risk profile than a static secret. AWS Secrets Manager primarily stores and optionally rotates static secrets on a schedule (native rotation for supported databases) rather than minting per-request, leased credentials. Whether this matters depends on the use case: if the team's actual pattern is "static secret, rotated periodically," Secrets Manager's native rotation covers it adequately with far less operational burden than running Vault. If the team relies on Vault's broader capabilities — cross-cloud secret abstraction, PKI issuance, dynamic per-request credentials with fine-grained leases — those would need to be re-architected or accepted as lost.
_What the interviewer is probing for:_ Ability to reason about a real trade-off rather than treating the two options as interchangeable, and connecting the choice back to the specific secret-usage pattern in play.

**🎯 Architect:** _"Design a multi-cloud Terraform estate's secrets strategy: some workloads are AWS-only, some are Azure-only, and a shared platform team needs a single audit view of all secret access across both."_
**Model answer:** Two viable shapes: (1) keep each cloud's native secrets manager for its own workloads (Secrets Manager for AWS resources, Key Vault for Azure resources) to minimize operational surface and keep IAM boundaries native to each cloud, then centralize _audit_ rather than _storage_ — ship CloudTrail `GetSecretValue` events and Azure Activity Log Key Vault events into a shared SIEM/log-aggregation platform so the platform team gets one unified access view without unifying the storage layer; or (2) adopt a central Vault deployment as the single secrets source of truth across both clouds, using Vault's AWS and Azure secrets engines/auth methods to still integrate natively with each cloud's IAM at the edges, trading the operational cost of running Vault for a genuinely single audit and policy plane instead of a log-aggregation approximation of one. The right choice depends on whether the org already has Vault operational expertise and whether "single policy plane" (not just single audit view) is a hard requirement — if only unified visibility is needed, option 1 is materially cheaper; if unified _policy enforcement_ across clouds is required, Vault is the more direct answer.
_What the interviewer is probing for:_ Systems-level architectural reasoning about centralization trade-offs across multiple clouds, and recognizing that "unified audit visibility" and "unified secrets storage" are different problems with different solutions.

## 12. Common Misconceptions

1. **"A cloud-native secrets manager protects the secret everywhere it's used in Terraform."** It protects the secret at its own storage location; once a data source reads it into a resource argument, the value is written into Terraform state plaintext exactly as described in [§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md).
2. **"General cloud provider authentication is sufficient to read any secret."** Each service (Secrets Manager, Key Vault, Secret Manager) layers its own access control (IAM policy, access policy/RBAC, IAM binding) on top of base authentication — both must be satisfied.
3. **"Reading `latest` always gives reproducible plans."** If the underlying secret rotates between plan and apply, or between two applies, the value read can change even with zero configuration changes — pin versions for reproducibility.
4. **"These services are functionally identical to Vault."** They cover static secret storage and (for some) scheduled rotation well, but generally lack Vault's dynamic, per-request leased-credential model and cross-cloud abstraction — a real capability difference, not just a naming difference.

## 13. 🔑 Key Takeaways

- AWS Secrets Manager, Azure Key Vault, and GCP Secret Manager integrate with Terraform via `data "aws_secretsmanager_secret_version"`, `data "azurerm_key_vault_secret"`, and `data "google_secret_manager_secret_version"` respectively.
- Each service layers its own access control on top of the base cloud provider authentication — valid provider credentials do not automatically grant secret read access.
- Reading a secret from any of these services into a resource argument still writes the value into Terraform state plaintext — this is the same [§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) exposure regardless of secret source.
- Version pinning matters for reproducibility since `latest`/current-version reads can silently change between applies if the secret rotates externally.
- These services trade some of Vault's dynamic-secrets sophistication for lower operational overhead and native integration with each cloud's existing IAM and audit tooling — a legitimate choice, not a downgrade, for single-cloud or rotation-sufficient use cases.

## 14. Related Concepts & What's Next

[§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md), next, addresses the IAM permissions the Terraform execution role itself needs to read these secrets — a distinct least-privilege concern from the secrets manager's own access policy. [§96](./Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md) covers static analysis tooling that can catch hardcoded secrets or overly permissive secrets-manager IAM grants before they're ever applied. [§98](./Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md) closes the loop on protecting the state file copy that these data sources' reads inevitably create, regardless of how well the source secret itself is protected.

**Next Section:** [§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) — `Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md`
