# Section 38 (Part 5): Local-Only Resources (null_resource, terraform_data, random and time Providers)

## 1. Definition

**Plain language:** Not every "resource" in Terraform represents a real cloud object. Some resources exist purely to help Terraform's own machinery — giving you a hook to run a script tied to a specific lifecycle event, generating a random password, or capturing a timestamp — without ever calling a cloud provider's API. These are **local-only resources**: they're managed entirely by the Terraform CLI itself or a minimal helper provider, and nothing about them exists outside your state file.

**Precise definition:** **Local-only resources** are resources whose provider does not manage any external infrastructure — the `null` provider's `null_resource`, its modern successor `terraform_data` (built into Terraform core since 1.4, no separate provider required), and the small utility providers `random` (generating pseudo-random values like IDs, passwords, and UUIDs, persisted in state so they stay stable across applies) and `time` (capturing and comparing timestamps, e.g., for time-based rotation triggers). These resources exist to solve two recurring problems declarative infrastructure otherwise struggles with: attaching arbitrary logic (via provisioners, [§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)–[§64](../Part9/Section-64-Part9-local-exec-and-remote-exec-Provisioners.md)) to a point in the dependency graph that has no natural resource of its own to attach to, and generating and persistently storing values Terraform itself computes rather than a cloud provider.

> 💡 **Tip:** `null_resource` is officially in maintenance mode — HashiCorp recommends `terraform_data` (built into Terraform core, no `required_providers` entry needed) for any new configuration on Terraform ≥ 1.4. They serve the same purpose and share the `triggers`/`triggers_replace` mechanism, but `terraform_data` also exposes an `input`/`output` pass-through attribute `null_resource` never had, useful for threading a computed value through a lifecycle hook.

## 2. Why This Matters

- **`null_resource`/`terraform_data` are the standard attachment point for provisioners** ([§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)–[§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) that don't naturally belong to any specific cloud resource — a script that needs to run once, or re-run when specific inputs change, without being tied to a VM's own lifecycle.
- **`random_*` resources solve a real, common problem**: needing a value (a password, a suffix for a globally-unique bucket name, a UUID) that Terraform itself generates once and then must remain **stable** across every subsequent plan/apply — a plain `random()`-style function call inside an expression, by contrast, would re-evaluate every run and constantly show drift.
- **`time_*` resources solve scheduling and rotation problems** that are otherwise awkward in a purely declarative model — capturing "when was this created," gating a change until a specific time, or triggering periodic rotation.
- **Overuse of these resources, especially `null_resource` with provisioners, is a well-known anti-pattern** ([§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)) — understanding when they're the right tool versus a workaround for a design that should be solved differently (cloud-init/`user_data`, [§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) is a meaningful production-judgment skill.
- **These resources still fully participate in the dependency graph, state, and addressing model** ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md), [§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md), [§47](../Part7/Section-47-Part7-The-State-File-Format-terraform-tfstate-Deep-Dive.md)) exactly like any "real" cloud resource — they aren't a special case syntactically, only in what they actually do (or rather, don't do) against an external API.

## 3. Prerequisites and Dependencies

This section builds on [§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md) (resource addressing — these are ordinary resource blocks, addressed identically) and [§35](./Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md) (dependencies — `triggers`/`triggers_replace` interact closely with the dependency graph). It previews [§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)–[§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) (Provisioners and Lifecycle Rules), where `null_resource`/`terraform_data` are covered in their most common real use case in much greater depth — this section focuses on what these resources _are_ and their non-provisioner uses (random value generation, time-based triggers), while Part 9 focuses specifically on attaching provisioner logic to them.

## 4. Architecture / Conceptual Diagram

```text
  WHY A "LOCAL-ONLY" RESOURCE EXISTS AT ALL

  Normal resource:                    Local-only resource:
  ┌──────────────────────┐            ┌──────────────────────────┐
  │ resource "aws_..."   │            │ resource "null_resource" │
  │  ...                 │            │  or "terraform_data"     │
  │        │             │            │  or "random_..."         │
  │        ▼             │            │  or "time_..."           │
  │  Terraform Core      │            │        │                 │
  │        │             │            │        ▼                 │
  │        ▼             │            │  Terraform Core          │
  │  Provider Plugin RPC │            │        │                 │
  │        │             │            │        ▼                 │
  │        ▼             │            │  Provider Plugin RPC     │
  │  Real Cloud API Call │            │  (null/random/time —     │
  │  (creates/reads/     │            │   NO external API call;  │
  │   updates/destroys   │            │   logic runs locally or  │
  │   a real object)     │            │   value is generated/    │
  └──────────────────────┘            │   stored purely in state)│
                                      └──────────────────────────┘

  TRIGGER-BASED REPLACEMENT (null_resource / terraform_data)

  resource "terraform_data" "rerun_trigger" {
    triggers_replace = [ <expression that changes when re-run is needed> ]

    provisioner "local-exec" { command = "..." }
  }

       triggers_replace value UNCHANGED across applies
              │
              ▼
       resource NOT replaced → provisioner does NOT re-run

       triggers_replace value CHANGED (e.g., an AMI ID, a file hash)
              │
              ▼
       resource IS replaced (destroy + create) → provisioner DOES re-run
```

- Local-only resources still get a **real state entry**, a **real address** (`null_resource.example`, `random_password.db.result`), and participate in `terraform plan`'s diffing exactly like any resource — the only thing that's "local" is that no external API is called to realize them.
- `random_*` resources compute their value **once**, on first creation, and then persist it in state — subsequent plans read the stored value rather than regenerating it, which is precisely what makes them usable for values that must stay stable (like a password already deployed to a real database).
- `triggers` (on `null_resource`) and `triggers_replace` (on `terraform_data`) are the mechanism controlling **when** the resource (and any attached provisioner) is destroyed and recreated — any change in the trigger expression's value forces replacement.

## 5. Hands-On

### 5.1 `terraform_data` as a Provisioner Attachment Point

**Purpose:** Run a script tied to a specific set of trigger inputs, with no corresponding real cloud resource to attach it to.

**Syntax:**

```hcl
resource "terraform_data" "<NAME>" {
  triggers_replace = [<expression>]

  provisioner "local-exec" {
    command = "<command>"
  }
}
```

**Example usage and expected output:**

```hcl
resource "terraform_data" "db_migration" {
  triggers_replace = [filemd5("${path.module}/migrations/schema.sql")]

  provisioner "local-exec" {
    command = "psql -f ${path.module}/migrations/schema.sql"
  }
}
```

```bash
$ terraform apply
  # terraform_data.db_migration will be created
  + resource "terraform_data" "db_migration" {
      + triggers_replace = "d41d8cd98f00b204e9800998ecf8427e"
    }

Plan: 1 to add, 0 to change, 0 to destroy.

terraform_data.db_migration: Creating...
terraform_data.db_migration: Provisioning with 'local-exec'...
terraform_data.db_migration (local-exec): Executing: psql -f ./migrations/schema.sql
terraform_data.db_migration: Creation complete after 1s

$ # schema.sql edited, hash changes; apply again
$ terraform apply
  # terraform_data.db_migration must be replaced
-/+ resource "terraform_data" "db_migration" {
      ~ triggers_replace = "d41d8cd98f00b204e9800998ecf8427e" -> "a1b2c3d4e5f6..." # forces replacement
    }

Plan: 1 to add, 0 to change, 1 to destroy.
```

**Production usage example:** A common (if provisioner-discouraged, [§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)) pattern for one-off, locally-run scripts triggered by a genuine file content change — the `filemd5()` trigger ensures the script only re-runs when the underlying migration file actually changes, not on every unrelated `apply`.

**Common errors:** Omitting `triggers_replace` (or `triggers` on the older `null_resource`) entirely means the resource is created exactly once and never reconsidered on subsequent applies, regardless of any real underlying change — a common source of "why didn't my script re-run" confusion.

### 5.2 `random_password` — Generating and Persisting a Stable Secret

**Purpose:** Generate a value that must be created once and then remain stable for the life of the resource it's used with.

**Syntax:**

```hcl
resource "random_password" "<NAME>" {
  length  = <number>
  special = <bool>
}
```

**Example usage and expected output:**

```hcl
resource "random_password" "db" {
  length  = 24
  special = true
}

resource "aws_db_instance" "primary" {
  identifier = "prod-db"
  password   = random_password.db.result
  # ...
}
```

```bash
$ terraform apply
  # random_password.db will be created
  + resource "random_password" "db" {
      + length  = 24
      + result  = (sensitive value)
      + special = true
    }
  # aws_db_instance.primary will be created

Plan: 2 to add, 0 to change, 0 to destroy.

$ # run apply again, nothing changed
$ terraform apply
No changes. Your infrastructure matches the configuration.
# random_password.db.result is READ FROM STATE, not regenerated —
# the database's actual password stays valid and unchanged.
```

**Production usage example:** Standard pattern for auto-generating database and service credentials that need to exist somewhere deterministic and version-controllable in configuration flow, though the _value itself_ is stored in state ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) and should be paired with `sensitive = true` on any output exposing it and, ideally, handed off to a secrets manager ([§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md)–[§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)) rather than left solely in Terraform state long-term.

**Common errors:** Assuming `random_password.db.result` changes on every apply — it doesn't, by design, as long as the resource itself isn't replaced; confusing this with a non-persisted random value (like calling a hypothetical "generate random every time" function) leads to incorrect assumptions about credential rotation behavior, which must instead be driven deliberately (e.g., via `keepers`/`triggers` or a scheduled `time_rotating` resource).

### 5.3 `random_id` for Unique Naming Suffixes

**Purpose:** Produce a stable, unique suffix for resources with globally-unique naming constraints (like S3 bucket names).

**Syntax:**

```hcl
resource "random_id" "<NAME>" {
  byte_length = <number>
}
```

**Example usage and expected output:**

```hcl
resource "random_id" "bucket_suffix" {
  byte_length = 4
}

resource "aws_s3_bucket" "logs" {
  bucket = "app-logs-${random_id.bucket_suffix.hex}"
}
```

```bash
$ terraform apply
  # random_id.bucket_suffix will be created
  + resource "random_id" "bucket_suffix" {
      + byte_length = 4
      + hex         = (known after apply)
    }
  # aws_s3_bucket.logs will be created
    + bucket = (known after apply)

Plan: 2 to add, 0 to change, 0 to destroy.

Apply complete! Resources: 2 added, 0 changed, 0 destroyed.

$ terraform state show random_id.bucket_suffix
# random_id.bucket_suffix:
resource "random_id" "bucket_suffix" {
    byte_length = 4
    hex         = "a1b2c3d4"
    id          = "obwjfk-..."
}
```

**Production usage example:** The standard workaround for globally-unique cloud resource naming requirements (S3 bucket names, some DNS-related resources) that must be deterministic per-deployment but not hardcoded, especially across multiple environments deployed from the same configuration.

**Common errors:** Regenerating this value unintentionally by changing `byte_length` or otherwise forcing replacement causes every dependent resource referencing `random_id.bucket_suffix.hex` (like the bucket name here) to also be replaced — for anything with a globally-unique name, replacement usually means an entirely new bucket, not a rename, which can be highly disruptive.

### 5.4 `time_sleep` and `time_static` — Handling Timing and Timestamps

**Purpose:** Introduce a deliberate delay for eventual-consistency issues, or capture an immutable creation timestamp.

**Syntax:**

```hcl
resource "time_sleep" "<NAME>" {
  create_duration = "<duration>"
  depends_on       = [<resource>]
}

resource "time_static" "<NAME>" {}
```

**Example usage and expected output:**

```hcl
resource "aws_iam_role_policy_attachment" "app" {
  role       = aws_iam_role.app.name
  policy_arn = aws_iam_policy.app.arn
}

resource "time_sleep" "iam_propagation" {
  depends_on       = [aws_iam_role_policy_attachment.app]
  create_duration  = "30s"
}

resource "aws_instance" "app" {
  depends_on = [time_sleep.iam_propagation]
  # ...
}

resource "time_static" "created_at" {}

output "provisioned_at" {
  value = time_static.created_at.rfc3339
}
```

```bash
$ terraform apply
aws_iam_role_policy_attachment.app: Creating...
aws_iam_role_policy_attachment.app: Creation complete after 1s
time_sleep.iam_propagation: Creating...
time_sleep.iam_propagation: Still creating... [10s elapsed]
time_sleep.iam_propagation: Still creating... [20s elapsed]
time_sleep.iam_propagation: Creation complete after 30s
aws_instance.app: Creating...
aws_instance.app: Creation complete after 32s
time_static.created_at: Creating...
time_static.created_at: Creation complete after 0s

Apply complete! Resources: 4 added, 0 changed, 0 destroyed.

Outputs:
provisioned_at = "2026-08-08T14:32:07Z"
```

**Production usage example:** `time_sleep` is a pragmatic (if blunt) workaround for IAM eventual-consistency issues ([§35](./Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md)'s `depends_on` alone guarantees ordering, but not that the change has fully propagated on the provider's side); `time_static` is commonly used to stamp resources with an immutable creation time for auditing, independent of when `terraform plan`/`apply` happens to run.

**Common errors:** Relying on `time_sleep` with a fixed, guessed duration as a permanent fix for a flaky eventual-consistency issue is fragile — the "correct" propagation delay can vary by region, load, and provider behavior over time; where a provider offers a dedicated "wait until ready" data source or resource, prefer that over a blind sleep.

## 6. Production Usage Notes

- **`random_*` values are stored in state in plaintext** exactly like any other resource attribute — a generated password is exactly as exposed to anyone with state read access as a hardcoded one would be; [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) (secrets in state) applies fully here, and pairing `random_password` with `sensitive = true` on any output is necessary but not sufficient for real secret protection.
- **`null_resource`/`terraform_data` used for provisioners should be treated as a last resort**, not a default — [§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md) covers HashiCorp's own stance that provisioners (and by extension, their common attachment point) are a "last resort" for anything a provider-native mechanism (`user_data`, cloud-init, [§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) could otherwise handle more reliably.
- **`time_sleep` durations should be treated as technical debt**, tracked and periodically reviewed — a hardcoded sleep masking a real eventual-consistency issue is a workaround, and provider updates sometimes introduce better native mechanisms (explicit "wait" resources or data sources) that should replace it when available.

## 7. Security Considerations

- Values generated by `random_password`/`random_string` land in the plaintext state file identically to any other sensitive attribute — treat every use of these resources as an automatic trigger to review your state encryption-at-rest and access-control posture ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md), [§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)), not as a security control in itself.
- `local-exec` provisioners attached to `null_resource`/`terraform_data` run arbitrary shell commands on whatever machine executes `terraform apply` (a laptop, a CI runner) — this is a meaningfully larger execution surface than a purely declarative resource block, and should be scoped and reviewed with the same rigor as any other code that runs with the apply identity's credentials ([§64](../Part9/Section-64-Part9-local-exec-and-remote-exec-Provisioners.md), [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)).
- Because `random_*` resources persist their generated values in state rather than regenerating them, an attacker who gains read access to state gains access to every credential ever generated this way for the life of that state file's history in any retained state backups/versions — state backend retention policy ([§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)) is directly relevant here.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                                            | Likely Cause                                                                                                                                 | Resolution Path                                                                                            |
| ------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| A `null_resource`/`terraform_data` provisioner never re-runs despite a real underlying change                      | No `triggers`/`triggers_replace` set, or the trigger expression doesn't actually reflect the change                                          | Add a `triggers_replace`/`triggers` value that changes precisely when the intended re-run condition occurs |
| `random_password.x.result` unexpectedly changes on an apply, rotating a live credential                            | The resource was forced to replace (a `keepers`/`triggers`-equivalent argument changed, or it was tainted/removed from state and reimported) | Review what changed about the resource's own arguments; if unintended, revert the triggering change        |
| Instance boot fails intermittently calling an API that needs a just-attached IAM policy                            | Provider-reported "created" doesn't guarantee full propagation; `depends_on` alone isn't sufficient for eventual consistency                 | Add a `time_sleep` (pragmatic) or a provider-native "wait until ready" mechanism if one exists             |
| `terraform plan` shows a `null_resource`/`terraform_data` resource with no obvious purpose during a codebase audit | Likely a provisioner-attachment resource whose logic isn't visible without reading the full block                                            | Read the full resource block including its `provisioner` sub-blocks and `triggers` to understand intent    |

## 9. Best Practices

- Prefer `terraform_data` over `null_resource` for any new configuration on Terraform ≥ 1.4 — it's the actively maintained, core-integrated successor with equivalent functionality plus input/output pass-through.
- Scope `random_*` resource usage to genuinely needing a Terraform-generated, state-persisted value — don't reach for `random_id` purely for cosmetic naming variety where a deterministic name (from a variable) would work just as well and be easier to reason about.
- Treat every `local-exec`/`remote-exec` provisioner attached to a local-only resource as a signal to ask "could this be a provider-native mechanism instead" (`user_data`, cloud-init, a purpose-built provider resource) before accepting it as the final design ([§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)).
- Document the _reason_ for any `time_sleep` duration in a comment, including what specific eventual-consistency behavior it's working around — this prevents future maintainers from either removing it prematurely or leaving it in place long after it's no longer necessary.

## 10. Common Anti-Patterns / Mistakes

- **Using `null_resource` with a `local-exec` provisioner to perform actual infrastructure provisioning logic** that a proper resource or provider-native mechanism should handle instead — this is one of the most common gateway anti-patterns leading a Terraform codebase toward unmaintainable, imperative-inside-declarative sprawl.
- **Assuming a `random_*` value regenerates on every apply**, and building logic (or expectations) around that assumption — it's stored in state and stable by design, and "rotation" requires a deliberate trigger.
- **Layering multiple `time_sleep` resources to work around a chain of eventual-consistency issues** instead of investigating whether a provider-native wait mechanism exists, or whether the underlying dependency chain itself is poorly designed — stacked sleeps are fragile and slow down every apply permanently.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `null_resource` and `terraform_data`?"_
**Model answer:** They serve the same purpose — a resource with no real cloud object behind it, most commonly used as an attachment point for provisioners — but `terraform_data` is the newer, core-built-in successor available since Terraform 1.4, while `null_resource` requires a separate `null` provider and is now in maintenance mode. `terraform_data` also adds an input/output pass-through capability `null_resource` never had. HashiCorp recommends `terraform_data` for new configurations.
_What the interviewer is probing for:_ Awareness that Terraform's ecosystem evolves and that "the way it's always been done" (`null_resource`) isn't necessarily the current best practice.

**🎯 Intermediate:** _"Why would you use a `random_password` resource instead of just calling a random-generation function directly inside a string expression?"_
**Model answer:** A function call inside an expression re-evaluates every time Terraform computes the configuration, which would produce a different value on every single plan — completely unusable for something like a database password that needs to stay the same as what's actually deployed. `random_password`, as a resource, computes its value once when created and then persists that value in the state file; subsequent plans read the stored value from state rather than regenerating it, so the password stays stable across every apply unless the resource is deliberately replaced. This state persistence is the entire reason it exists as a resource rather than a function.
_What the interviewer is probing for:_ Understanding _why_ the resource abstraction matters here specifically — state persistence — not just "it generates random values."

**🎯 Senior:** _"You find a `null_resource` in a codebase with a `local-exec` provisioner running a script that configures application settings on a VM after it boots. What's your assessment, and what would you recommend instead?"_
**Model answer:** This is a common but discouraged pattern — HashiCorp's own guidance treats provisioners as a last resort specifically because they're imperative logic bolted onto a declarative tool, they only run at creation time (by default) with no ongoing reconciliation, they depend on network reachability and credentials for whatever machine runs `terraform apply` to reach the target VM, and they have no idempotency guarantee the way resource attributes do. The stronger alternative, when configuring a VM at boot, is provider-native `user_data`/cloud-init ([§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) — passed directly as a resource argument, executed by the cloud provider itself at boot time without any dependency on the `apply` machine's network reachability to the instance, and naturally idempotent if written as a boot script that runs the same way every time. I'd recommend migrating this to `user_data` unless there's a specific, documented reason cloud-init genuinely can't express the same logic (e.g., a script that needs Terraform-side computed values not easily passed through user*data templating, which is rare in practice with `templatefile()`, [§19](../Part3/Section-19-Part3-String-Interpolation-and-Templating-heredoc-templatefile.md)).
\_What the interviewer is probing for:* Real production judgment about provisioners as an anti-pattern, and specific, concrete knowledge of the preferred alternative rather than a vague "provisioners are bad."

**🎯 Architect:** _"Your organization has several dozen `random_password` resources across different services' Terraform state, all storing database credentials directly in state with no secrets manager integration. How would you assess and prioritize remediation?"_
**Model answer:** I'd start by treating this as a state-security posture problem first, independent of whether `random_password` itself is used — every one of these credentials is sitting in plaintext in state files, so the immediate priority is auditing who and what has read access to those state backends ([§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)) and whether state is encrypted at rest, since that's the actual blast radius regardless of remediation timeline. For remediation, I wouldn't rip out `random_password` wholesale — the pattern of generating a credential once and needing it to stay stable is legitimate — but I'd migrate the actual credential storage and distribution to a dedicated secrets manager (Vault, AWS Secrets Manager, etc., [§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md)–[§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)): Terraform can still generate the password with `random_password`, but instead of applications reading it from Terraform outputs or state, it should be written into the secrets manager as part of the same apply, and applications should read credentials from the secrets manager directly, never from Terraform state or outputs. I'd prioritize services by data sensitivity and blast radius first (customer data, payment-adjacent systems before internal tooling), and treat this as an incremental, service-by-service migration with each service's state re-encrypted or rotated as part of its migration, not a single big-bang cutover across dozens of services simultaneously.
_What the interviewer is probing for:_ Whether the candidate can connect a specific resource pattern to a broader organizational secrets-management strategy, prioritize realistically, and avoid both under-reacting (ignoring the exposure) and over-reacting (a risky simultaneous mass migration).

## 12. Common Misconceptions

1. **"`null_resource` and `terraform_data` create something, even if it's abstract."** They create a state entry and participate in the graph, but there is no external object at all — "creation" here means Terraform runs whatever's attached (provisioners) and/or records trigger values, nothing more.
2. **"`random_*` resources regenerate their value on every `apply`."** They generate once and persist the value in state; regeneration only happens if the resource is replaced (typically via a `keepers` argument or trigger change).
3. **"Local-only resources are a special syntax category, different from normal resource blocks."** They use the exact same `resource "<TYPE>" "<NAME>" { ... }` syntax, addressing model, and graph participation as any cloud resource — the only difference is what happens (or doesn't) against an external API.
4. **"`time_sleep` guarantees a dependency is fully ready."** It only guarantees a fixed amount of wall-clock time has passed — it's a heuristic, not a guarantee, and the "correct" duration can vary by provider, region, and load.

## 13. 🔑 Key Takeaways

- Local-only resources (`null_resource`/`terraform_data`, `random_*`, `time_*`) participate fully in Terraform's addressing, state, and dependency graph exactly like real cloud resources, but call no external provisioning API.
- `terraform_data` (built into Terraform core since 1.4) is the recommended successor to the maintenance-mode `null_resource`, sharing the `triggers`/`triggers_replace` mechanism for controlling replacement (and thus provisioner re-execution).
- `random_*` resources generate a value once and persist it in state, which is precisely what makes them suitable for stable secrets and unique naming suffixes — unlike a function call, they don't regenerate on every plan.
- `time_sleep` and other `time_*` resources are pragmatic tools for eventual-consistency and timestamp-capture needs a purely declarative model handles awkwardly, but should be treated as documented technical debt, not a permanent fix.
- Provisioner-attached local-only resources are a well-known anti-pattern when a provider-native alternative (`user_data`, cloud-init) exists — Part 9 ([§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)–[§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) covers this trade-off in full depth.

## 14. Related Concepts & What's Next

[§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md) (resource addressing) and [§35](./Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md) (dependencies) apply identically to local-only resources. [§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)–[§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) cover provisioners — the most common reason `null_resource`/`terraform_data` appear in real configurations — in much greater depth, including `on_failure` behavior and provider-native alternatives. [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) (secrets in state) is directly relevant to any `random_*` credential-generation usage. This closes out Part 5 (Resources and Data Sources); Part 6 begins the companion topic of input variables, outputs, and locals — the mechanisms for parameterizing everything built in this Part.

**Next Section:** [§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) — `Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md`
