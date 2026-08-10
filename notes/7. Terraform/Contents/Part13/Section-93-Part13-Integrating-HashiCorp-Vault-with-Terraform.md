# Section 93 (Part 13): Integrating HashiCorp Vault with Terraform

## 1. Definition

**Plain language:** HashiCorp Vault is a dedicated secrets-management system: instead of a database password living as a static string somewhere in your configuration, Vault can hand out a freshly generated, time-limited credential each time Terraform (or anything else) asks for one. Terraform talks to Vault through the `vault` provider, reading secrets at plan/apply time rather than storing static secret values in your `.tf` files or `.tfvars`.

**Precise definition:** The **`vault` provider** is a Terraform provider that authenticates to a HashiCorp Vault server and exposes Vault-managed secret data to Terraform configuration via data sources, most commonly `data "vault_generic_secret"` for static key-value secrets stored in Vault's KV secrets engine. Beyond static secrets, Vault supports **dynamic secrets**: credentials generated on-demand by a Vault secrets engine (e.g., the database secrets engine creating a scoped, time-limited database user) with an associated **lease** — a time-to-live after which Vault automatically revokes the credential. Terraform data sources backed by dynamic secrets engines (e.g., `vault_database_secret_backend_static_role`, or reading a dynamic credential path) receive a freshly minted, short-lived credential on each `apply` rather than a long-lived static one, fundamentally changing the risk profile of a leaked value: a leaked dynamic credential expires on its own.

> 💡 **Tip:** The Vault integration's value isn't just "one more place to store a password" — it's that Vault can eliminate long-lived credentials from your infrastructure lifecycle entirely. A static secret leaked from state ([§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) is a permanent liability until manually rotated; a dynamic Vault-issued credential leaked from state expires on a lease timer whether or not anyone notices the leak.

## 2. Why This Matters

- **Directly mitigates [§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)'s core problem for a subset of secrets**: if a credential is dynamically generated and short-lived, its presence in Terraform state (still plaintext, still a risk) is a far smaller liability than a static, indefinitely valid password would be.
- **Centralizes secret lifecycle management** outside of Terraform configuration entirely — rotation, access policy, and audit logging live in Vault, a system purpose-built for that job, rather than being reinvented per-provider or per-team in Terraform.
- **Enables fine-grained, auditable access policies** — Vault's policy engine can restrict which Terraform run (identified by its auth method — AppRole, Kubernetes auth, AWS auth) can read which secret paths, independent of cloud IAM.
- **Widely adopted in regulated and security-conscious organizations** as the standard secrets backend for infrastructure automation, making Vault fluency a common interview and real-world expectation for Terraform practitioners working at scale.
- **Decouples secret storage from cloud provider** — a multi-cloud or hybrid organization can use one Vault instance as a single secrets source of truth across AWS, Azure, and GCP Terraform configurations, rather than three separate cloud-native secret stores.

## 3. Prerequisites and Dependencies

This section builds directly on [§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)'s finding that secrets referenced by Terraform end up in state regardless of source — understanding that risk motivates why teams reach for Vault's dynamic secrets specifically. Provider configuration mechanics generally were covered in [§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md); this section is a provider-specific deep dive following that same pattern. Familiarity with a running Vault server (installation, unsealing, secrets engine enablement) is assumed as out of scope here — this section covers the Terraform-side integration only, not standing up Vault itself. [§94](./Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md) covers the cloud-native secrets manager alternative to Vault, useful for contrast.

## 4. Architecture / Conceptual Diagram

```text
   VAULT DYNAMIC SECRET LEASE LIFECYCLE (via Terraform)

   terraform apply
        │
        ▼
   ┌─────────────────────┐   authenticate (AppRole/    ┌────────────────────┐
   │  Terraform vault    │──  Kubernetes/AWS auth) ───►│   Vault Server     │
   │  provider           │                             │   (unsealed)       │
   └─────────────────────┘◄── short-lived Vault token ─└────────────────────┘
        │
        │ data "vault_generic_secret" / dynamic secret read
        ▼
   ┌───────────────────────┐
   │  Vault Secrets Engine │  e.g. database secrets engine
   │  generates a NEW      │  creates a scoped DB user:
   │  credential + LEASE   │  username=v-approle-xyz123
   └───────────────────────┘  password=<random>, TTL=1h
        │
        ▼
   Credential flows into Terraform resource config
   (e.g. passed to an app's environment, or used to
   configure a resource) — value IS still written into
   Terraform state (§92 risk still applies)
        │
        ▼
   Lease TTL expires (e.g. 1h) ──► Vault auto-revokes the
   credential server-side. Even if the state file leaked,
   the credential in it is now invalid.

   Contrast: a STATIC secret (data "vault_generic_secret"
   reading a KV path) has no lease — it's valid until
   manually rotated in Vault, same exposure profile as any
   other static secret once it's in Terraform state.
```

- Authentication to Vault from Terraform is itself a credential-management problem — commonly solved with **AppRole auth** (a role ID + secret ID pair, often injected via CI/CD secret store) or **cloud-native auth methods** (AWS/Azure/GCP auth backends that let Vault trust the CI runner's cloud identity without a separate Vault credential at all).
- **Static secrets** (KV engine) behave like any other secret once read into Terraform — still subject to the full [§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) state-exposure risk.
- **Dynamic secrets** are the differentiator: the credential materializes only at apply time, has a bounded lifetime, and Vault — not Terraform — owns revocation.

## 5. Hands-On

### 5.1 Configuring the `vault` Provider

**Purpose:** Establish an authenticated connection from Terraform to a Vault server.

**Syntax:**

```hcl
provider "vault" {
  address = "https://vault.internal.example.com:8200"
  # Auth typically supplied via VAULT_TOKEN env var, or an auth_login block
  # for AppRole/Kubernetes/AWS auth rather than a hardcoded token.
  auth_login {
    path = "auth/approle/login"
    parameters = {
      role_id   = var.vault_role_id
      secret_id = var.vault_secret_id
    }
  }
}
```

**Example usage and expected output:**

```bash
$ terraform plan
data.vault_generic_secret.db: Reading...
data.vault_generic_secret.db: Read complete after 0s
```

**Production usage example:** CI/CD runners typically authenticate via AppRole, with the `role_id` baked into pipeline config (non-secret) and the `secret_id` injected as a masked CI variable or fetched via the CI platform's own OIDC trust with Vault — avoiding a long-lived Vault token ever being stored anywhere.

**Common errors:** `Error: missing client token` — the provider has no valid Vault auth; check that `VAULT_TOKEN` is set or the `auth_login` block's credentials are valid and the AppRole is not expired/revoked.

### 5.2 Reading a Static Secret with `data "vault_generic_secret"`

**Purpose:** Fetch a KV-stored secret from Vault for use in resource configuration, avoiding a static secret ever living in `.tfvars`.

**Syntax:**

```hcl
data "vault_generic_secret" "db" {
  path = "secret/data/app/database"
}

resource "aws_db_instance" "main" {
  identifier = "app-db"
  username   = data.vault_generic_secret.db.data["username"]
  password   = data.vault_generic_secret.db.data["password"]
  # ...
}
```

**Example usage and expected output:**

```bash
$ terraform apply
data.vault_generic_secret.db: Reading...
data.vault_generic_secret.db: Read complete after 0s

  # aws_db_instance.main will be created
  + password = (sensitive value)
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** Teams migrating off hardcoded `.tfvars` secrets typically start here — swapping `var.db_password` for a `vault_generic_secret` read is a low-effort first step, even before adopting dynamic secrets, since it removes the secret from Terraform's own variable inputs and version-controlled `.tfvars` files.

**Common errors:** Forgetting the KV v2 path prefix — Vault's KV version 2 engine requires paths of the form `secret/data/<path>` (not `secret/<path>`) for reads via the generic API, a frequent source of a `no data returned` result that looks like a permissions error but is actually a path-format mistake.

### 5.3 Consuming a Dynamic Database Credential

**Purpose:** Obtain a short-lived, Vault-generated database credential rather than a static one.

**Syntax:**

```hcl
data "vault_generic_secret" "db_creds" {
  path = "database/creds/app-role"
}

output "db_username" {
  value     = data.vault_generic_secret.db_creds.data["username"]
  sensitive = true
}
```

**Example usage and expected output:**

```bash
$ terraform apply
data.vault_generic_secret.db_creds: Reading...
data.vault_generic_secret.db_creds: Read complete after 0s
# username = v-approle-app-role-a1b2c3
# TTL: 1h — Vault will auto-revoke after expiry
Apply complete! Resources: 0 added, 0 changed, 0 destroyed.
```

**Production usage example:** Every `terraform apply` against this data source triggers Vault to mint a brand-new database credential — appropriate for infrastructure that's re-applied on a schedule or as part of a pipeline, less suitable for a value an application needs to keep using long after `apply` finishes (in which case the application itself should request its own lease directly from Vault, not receive one that passed through Terraform state).

**Common errors:** Credential works during `apply` but the downstream application fails to authenticate later — the dynamic credential's lease expired because it was generated at Terraform-apply time and consumed hours or days later; dynamic secrets with short TTLs are a poor fit for values an application reads long after the `apply` that generated them.

## 6. Production Usage Notes

- **Dynamic secrets are not automatically leak-proof once in Terraform state** — the credential value is still written into state plaintext just like a static secret ([§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) still applies); the mitigation is that the leaked value expires quickly, not that it's absent from state.
- **Lease renewal is Vault's responsibility, not Terraform's** — Terraform is not a long-running process that keeps leases alive; if a resource needs an active lease beyond a single apply's lifetime, that resource (or the application it configures) must manage its own renewal against Vault directly.
- **Vault auth method choice for the Terraform run matters as much as the secrets engine choice** — CI/CD runners should authenticate via a workload-identity-based method (Kubernetes auth, AWS/Azure/GCP auth) where possible, avoiding a static AppRole `secret_id` or root token stored as a CI secret.
- **The `vault` provider itself needs a valid, unexpired auth session for the full `plan`/`apply` duration** — long-running applies against Vault-backed data can fail mid-run if the Vault token's own TTL expires before the apply completes.

## 7. Security Considerations

- **Dynamic secrets meaningfully reduce blast radius but do not eliminate the state-exposure problem from [§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)** — a leaked state file still exposes whatever credential was live at the time of the last apply; the difference is that credential's usefulness has a clock on it.
- **Vault policies scoping what a given AppRole/auth identity can read are the actual access-control boundary** — a Terraform run authenticated with an overly broad Vault policy can read secrets far beyond what that specific configuration needs, which is the same least-privilege principle covered for cloud IAM in [§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md), applied to Vault.
- **Static Vault secrets (KV) still require the same backend encryption/access-control discipline as any other secret once they land in Terraform state** — Vault protects the secret at rest in Vault itself, but does nothing to protect the copy that ends up in `terraform.tfstate`.
- **Audit logging in Vault provides a strong forensic trail** — every secret read (including Terraform's) is logged, which is valuable for incident response but only if Vault audit devices are actually enabled and monitored.
- **A compromised Vault auth credential (AppRole `secret_id`, Vault token) used by Terraform is itself a high-value target** — protect it with the same rigor as any execution-role credential ([§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)); it is, in effect, the credential to the credential store.

## 8. Common Troubleshooting Scenarios

| Symptom                                                   | Likely Cause                                                                           | Resolution Path                                                                                                          |
| --------------------------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `Error: missing client token`                             | Vault provider has no valid auth (token expired, AppRole login failed)                 | Verify `VAULT_TOKEN`/`auth_login` credentials; check AppRole hasn't been revoked or secret_id expired                    |
| `data "vault_generic_secret"` returns empty/no data       | Wrong path — commonly missing the `data/` segment required for KV v2 engine reads      | Confirm KV engine version; use `secret/data/<path>` for KV v2, `secret/<path>` for KV v1                                 |
| Dynamic credential works in `apply` but fails hours later | Lease TTL expired before the credential was actually used by the consuming application | Shorten the gap between generation and use, increase TTL where policy allows, or have the consumer request its own lease |
| `permission denied` reading a Vault path                  | The authenticated identity's Vault policy doesn't grant read on that path              | Review and update the Vault policy attached to the AppRole/auth method used by the Terraform run                         |

## 9. Best Practices

- Prefer dynamic secrets engines (database, cloud provider engines) over static KV secrets wherever the target system supports them — the automatic expiry is a meaningful security improvement over any static credential.
- Authenticate the `vault` provider using a workload-identity method (Kubernetes, AWS/Azure/GCP auth) in CI/CD rather than a long-lived static token or hardcoded AppRole `secret_id`.
- Scope Vault policies per Terraform workspace/pipeline as narrowly as the specific secret paths that configuration actually needs — mirror the least-privilege principle from [§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) inside Vault's own policy model.
- Enable Vault audit logging and monitor it for anomalous secret reads, particularly from automation identities.
- Combine Vault with the state-encryption/access-control practices from [§98](./Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md) — Vault reduces risk, it doesn't remove the need for a properly secured backend.

## 10. Common Anti-Patterns / Mistakes

- **Using a Vault root token for Terraform automation.** Root tokens bypass all policy scoping — a compromised CI pipeline using one has unrestricted Vault access, the opposite of least privilege.
- **Treating dynamic secrets as a full replacement for backend security.** They reduce the value of a leaked state file; they don't make the state file safe to leave unencrypted or publicly readable.
- **Hardcoding Vault AppRole `secret_id` values in `.tfvars` or CI YAML.** This just relocates the "static secret in a config file" problem from the target application to Vault's own auth credential.
- **Requesting dynamic credentials far in advance of when they're actually used**, causing TTL expiry before consumption — dynamic secrets need generation timed close to actual use.

## 11. Interview Questions

**🎯 Beginner:** _"What does the `vault` provider let Terraform do?"_
**Model answer:** It lets Terraform authenticate to a HashiCorp Vault server and read secrets stored or generated there — most commonly via `data "vault_generic_secret"` — for use in resource configuration, instead of hardcoding secret values into Terraform variables or `.tfvars` files.
_What the interviewer is probing for:_ Basic familiarity with the provider's purpose and the specific data source name.

**🎯 Intermediate:** _"What's the difference between a static secret and a dynamic secret in Vault, and why does that distinction matter for Terraform?"_
**Model answer:** A static secret is a fixed value stored in Vault's KV engine and read back unchanged — it behaves like any other secret once Terraform reads it, including being written plaintext into state. A dynamic secret is generated on-demand by a Vault secrets engine (e.g., the database engine creating a scoped user) with an associated lease/TTL, after which Vault automatically revokes it. It matters for Terraform because state files retain whatever secret value was current at last apply ([§92](./Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) — a dynamic secret's short lifetime limits how long that retained copy remains useful if the state ever leaks, whereas a static secret in state is valid indefinitely until manually rotated.
_What the interviewer is probing for:_ Understanding of the practical security benefit, tied back to the state-exposure problem, not just a rote definition.

**🎯 Senior:** _"A team says using Vault dynamic secrets means they no longer need to worry about state file security. Do you agree?"_
**Model answer:** No — dynamic secrets reduce the _severity_ of a state leak for those specific credentials by bounding their useful lifetime, but the credential is still written into state plaintext at apply time exactly like a static one, and if the leak is discovered before the lease expires, it's fully exploitable. There are also often static secrets, non-credential sensitive values, or other resources' attributes coexisting in the same state file that dynamic secrets do nothing for. Backend encryption and access control ([§98](./Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)) remain necessary regardless of whether the secrets inside are static or dynamic.
_What the interviewer is probing for:_ Whether the candidate treats dynamic secrets as a risk-reduction layer rather than a substitute for actual state security controls — a common overclaim.

**🎯 Architect:** _"Design the Vault authentication approach for a fleet of CI/CD pipelines running Terraform across dozens of teams, minimizing standing credentials."_
**Model answer:** Avoid any long-lived static Vault token or shared AppRole secret*id distributed across teams. Instead, use a workload-identity federation approach: if pipelines run in a cloud CI platform with OIDC support, configure Vault's JWT/OIDC auth method to trust the CI platform's OIDC tokens directly, scoped per-repository or per-pipeline, so no Vault credential is provisioned or stored at all — trust is established dynamically per run. Where OIDC federation isn't available, use per-team AppRole with tightly scoped policies (each team's role can only read its own secret paths) and short `secret_id` TTLs, rotated automatically rather than manually distributed. Layer Vault namespaces or path prefixes per team to keep policy management tractable at scale, and require audit logging on all reads. This mirrors the least-privilege execution-role design in [§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) but applied to the secrets-store authentication boundary specifically, and treats "which team's pipeline can read which secrets" as an access-control problem to be solved structurally, not by convention.
\_What the interviewer is probing for:* Architectural thinking about credential sprawl at organizational scale, awareness of workload-identity/OIDC patterns as the modern best practice over static credentials, and connecting back to least-privilege principles established elsewhere in the Part.

## 12. Common Misconceptions

1. **"Vault secrets never end up in Terraform state."** They do — whatever value a `vault_generic_secret` or dynamic secret data source returns and is used in a resource argument is written into state exactly like any other value; Vault does not intercept or exempt Terraform's state serialization.
2. **"Dynamic secrets are inherently safer to leave in an insecure backend."** They're less _permanently_ damaging if leaked, but an active lease credential exposed before expiry is fully usable — TTL is a mitigation, not an exemption from backend security.
3. **"The `vault` provider requires a static Vault token."** A token is one option, but `auth_login` blocks support AppRole, Kubernetes, cloud IAM, and other auth methods that avoid a long-lived static token entirely.
4. **"KV v1 and KV v2 paths work the same way."** KV v2 requires an extra `data/` path segment for reads (`secret/data/<path>`) that KV v1 does not — a very common source of "empty secret" errors when migrating or misconfiguring the engine version.

## 13. 🔑 Key Takeaways

- The `vault` provider reads secrets from HashiCorp Vault into Terraform via data sources, most commonly `data "vault_generic_secret"`, instead of hardcoding secret values in configuration.
- Vault's dynamic secrets (with leases/TTLs) meaningfully reduce the risk of a leaked credential compared to static secrets, because Vault auto-revokes them — but the credential is still written into Terraform state plaintext just like any other value.
- Authentication to Vault from Terraform should use workload-identity-based auth methods (AppRole with rotated secret_id, Kubernetes/cloud auth, or OIDC federation) rather than long-lived static tokens.
- Vault policy scoping applied to the Terraform run's auth identity is a least-privilege control analogous to the execution-role scoping covered in [§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md), but for the secrets store itself.
- Vault integration is a risk-reduction layer on top of, not a replacement for, the backend encryption and access-control practices covered in [§98](./Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md).

## 14. Related Concepts & What's Next

[§94](./Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md) covers the cloud-native alternative to Vault — AWS Secrets Manager, Azure Key Vault, and GCP Secret Manager — useful where a dedicated Vault deployment isn't justified or where staying within a single cloud's native tooling is preferred. [§95](./Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) applies the same least-privilege thinking demonstrated here for Vault policies to the Terraform execution role's cloud IAM permissions. [§98](./Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md) covers the backend-level encryption and access control that remains necessary regardless of whether secrets originate from Vault or elsewhere.

**Next Section:** [§94](./Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md) — `Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md`
