# Section 41 (Part 6): Sensitive Variables and Sensitive Output Values

## 1. Definition

**Plain language:** When a variable or output holds something like a password or API key, marking it `sensitive` tells Terraform to hide its value from the normal CLI output — `plan` and `apply` show `(sensitive value)` instead of the actual string. This stops secrets from accidentally showing up in a terminal screen-share or a CI log, but it is a display-layer redaction, not encryption — the real value is still written to the state file in plain text.

**Precise definition:** Setting `sensitive = true` on a `variable` block or an `output` block instructs Terraform's CLI output formatter to redact that value wherever it would otherwise be printed — in `terraform plan`/`apply` diffs, in `terraform output` (unless the specific sensitive output is requested by name), and in error messages that would otherwise interpolate the value. This redaction is enforced by Terraform core itself, and it **propagates**: any other value derived from a sensitive value (through an expression, a `local`, or another resource argument) is treated as sensitive too, and referencing a sensitive value in a non-sensitive output produces a hard error unless that output is also marked `sensitive`. Critically, sensitive marking does **not** affect what's written to the state file ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)) — sensitive values are stored there in plaintext exactly like any other value, which is why state file access control ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md), [§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)) is the real security boundary, not the `sensitive` flag.

> 💡 **Tip:** Think of `sensitive = true` as "don't print this to a screen or log," not "encrypt this." If someone can read your `terraform.tfstate`, `sensitive` marking provides zero protection — the value is sitting there in plaintext regardless of how it was marked in configuration.

## 2. Why This Matters

- **Preventing accidental secret exposure in CI logs.** A `terraform apply` running in a CI pipeline that prints a plan diff to a shared build log is a common, avoidable leak vector — `sensitive` marking on the relevant variable or output closes it for the CLI-output surface specifically.
- **Preventing shoulder-surfing and screen-share leaks.** An engineer running `terraform plan` during a pair-programming session or a recorded demo won't accidentally reveal a database password on screen if it's properly marked sensitive.
- **Forcing deliberate, explicit exposure.** Because referencing a sensitive value in a non-sensitive output is a hard error, a developer can't accidentally "leak" a secret into a visible output just by wiring up a reference carelessly — they have to explicitly mark the consuming output sensitive too, which is a deliberate, reviewable choice.
- **Setting accurate security expectations.** Understanding that `sensitive` doesn't protect the state file is essential for correctly reasoning about where the _actual_ security boundary is — state storage access control, encryption at rest, and secrets manager integration ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md), [§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md), [§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md), [§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)), not the `sensitive` attribute.
- **Compliance and audit requirements.** Many security review processes explicitly check for `sensitive = true` on known-sensitive variable/output names as a baseline hygiene signal, even though it's necessary but not sufficient for full secret protection.

## 3. Prerequisites and Dependencies

This section builds directly on [§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) (variable declaration, where `sensitive` is one of the arguments a `variable` block can take) and previews [§42](./Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md) (output values), since `sensitive` applies symmetrically to both variables and outputs. It assumes the precedence and assignment concepts from [§40](./Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md). The deeper implications for state security are covered fully in [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) (Secrets in State: Risks and Mitigations) and [§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md) (Secure Backend Configuration) — this section establishes the mechanic and its limits; those sections cover the broader mitigation strategy.

## 4. Architecture / Conceptual Diagram

```text
   SENSITIVE VALUE PROPAGATION PATH

   variable "db_password" {                    -var="db_password=s3cr3t"
     type      = string                        or terraform.tfvars
     sensitive = true                           or TF_VAR_db_password
   }
          │
          │ referenced by
          ▼
   resource "aws_db_instance" "main" {
     password = var.db_password
   }
          │
   ┌──────┴──────────────────────────────────────────────────────────┐
   │                                                                 │
   ▼                                                                 ▼
  CLI OUTPUT (plan/apply)                                    STATE FILE (terraform.tfstate)
  password = (sensitive value)   ◄── REDACTED                password = "s3cr3t"  ◄── PLAINTEXT
  (protects terminal, CI logs,                                (protects nothing by itself —
   screen shares)                                              state access control, §92/§98,
                                                                 is the real boundary here)

  output "db_password" {
    value     = var.db_password
    sensitive = true       ◄── required if the output exposes a sensitive value,
  }                             otherwise Terraform errors at plan/apply time
```

- Redaction happens at the CLI presentation layer only — it's implemented in Terraform core's output formatting, not in the state serialization format, which is why the two behave so differently.
- Sensitivity is contagious through the dependency graph: any expression that incorporates a sensitive value (string interpolation, a `local` built from it, a resource attribute derived from it) inherits the sensitive marking automatically for output/display purposes.

## 5. Hands-On

### 5.1 Marking a Variable Sensitive

**Purpose:** Show the `sensitive` argument on a `variable` block and its effect on plan output.

**Syntax:**

```hcl
variable "db_password" {
  type        = string
  description = "Master password for the RDS instance"
  sensitive   = true
}

resource "aws_db_instance" "main" {
  identifier = "app-db"
  password   = var.db_password
  # ... other required arguments
}
```

**Example usage and expected output:**

```bash
$ terraform apply -var="db_password=s3cr3t-value"
  # aws_db_instance.main will be created
      + password = (sensitive value)
      + identifier = "app-db"

Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Every variable representing a credential, private key, connection string, or token in a production configuration should be marked `sensitive = true` — this is a near-universal baseline practice, not a case-by-case judgment call.

**Common errors:** Marking a variable `sensitive` does not retroactively redact it from a state file created before the marking was added — an already-applied resource's state entry remains plaintext regardless of when `sensitive` was added to the declaration; the marking only affects future CLI output formatting from that point on.

### 5.2 Marking an Output Sensitive

**Purpose:** Show the equivalent mechanism for outputs, and the enforced propagation when a sensitive value feeds a non-sensitive output.

**Syntax:**

```hcl
output "db_endpoint" {
  value = aws_db_instance.main.endpoint
}

output "db_password" {
  value     = var.db_password
  sensitive = true
}
```

**Example usage and expected output:**

```bash
$ terraform apply
Outputs:

db_endpoint = "app-db.abc123xyz.us-east-1.rds.amazonaws.com"
db_password = <sensitive>

$ terraform output db_password
"s3cr3t-value"
# Requesting a sensitive output BY NAME still prints the real value —
# sensitive marking hides it from the general summary, not from an
# operator who explicitly asks for that specific output.
```

If `sensitive = true` is omitted on an output whose value derives from a sensitive source:

```bash
$ terraform plan
Error: Output refers to sensitive values

  on outputs.tf line 5:
   5: output "db_password" {

To reduce the risk of accidentally exposing sensitive data referenced
by an output value, access to Output.Value returned by a sensitive
value is not allowed. Add `sensitive = true` to the output declaration.
```

**Production usage example:** Modules commonly expose a generated password or connection string as a `sensitive` output specifically so a calling root module can wire it into another resource (e.g., an application's environment variable) without ever having generated or typed the value itself.

**Common errors:** Assuming `terraform output` (with no argument, listing everything) hides sensitive values permanently — it hides them from the summary listing, but `terraform output <name>` for that specific sensitive output, and `terraform output -json`, both still reveal the real value; access to the CLI itself is the actual control, not the `sensitive` flag.

### 5.3 What Sensitive Marking Does Not Protect

**Purpose:** Demonstrate that state remains plaintext regardless of `sensitive` marking, reinforcing the core nuance of this section.

**Example usage and expected output:**

```bash
$ terraform show -json terraform.tfstate | grep -A2 '"password"'
"password": "s3cr3t-value",
# Plaintext in state despite sensitive = true on the variable and
# the resource attribute deriving from it — sensitive marking is a
# CLI/output-layer control, not a state-encryption control.
```

**Production usage example:** Organizations handling regulated data treat the state backend itself (encrypted S3 bucket with restrictive IAM, or Terraform Cloud with its own encryption-at-rest, [§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)) as the actual security boundary for secrets that end up in state — `sensitive = true` is a complementary hygiene practice on top of that, never a substitute for it.

**Common errors:** A security review that stops at "are sensitive variables marked `sensitive`?" without also checking state backend access controls and encryption gives a false sense of assurance — both layers are required.

## 6. Production Usage Notes

- **`sensitive` marking is viral through references but not through indirect side effects.** A `local` computed from a sensitive variable is itself sensitive; but if a sensitive value influences _which_ resource gets created (e.g., via a `count` conditional) without directly appearing in an output, that structural fact isn't redacted — only literal value exposure is covered.
- **`-json` output modes (`terraform show -json`, `terraform output -json`) still include sensitive values in full**, specifically because machine consumers (a CI step piping a password into another tool) often need the real value — redaction is aimed at human-facing terminal/log output, not programmatic consumption.
- **For genuinely high-sensitivity secrets, prefer not putting them in Terraform state at all** — generate them out-of-band in a secrets manager and have Terraform reference them (via a `data` source, [§33](../Part5/Section-33-Part5-Data-Sources-Reading-External-and-Existing-Infrastructure.md)) rather than create and store them, wherever the provider ecosystem supports that pattern; [§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md)/[§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md) cover this in depth.

## 7. Security Considerations

- `sensitive` marking is necessary-but-not-sufficient: pair it with state backend encryption and access controls ([§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)), least-privilege access to the state backend, and — for the highest-sensitivity secrets — avoiding storing the raw value in Terraform-managed state entirely by delegating to a secrets manager ([§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md)/[§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)).
- CI/CD systems that echo the full command line into build logs (`terraform apply -var="db_password=..."`) leak the secret regardless of `sensitive` marking on the variable, since the leak happens before Terraform even runs — this is why environment-variable injection (`TF_VAR_*`, [§40](./Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)) is safer than `-var` for secrets independent of `sensitive` marking.
- Third-party tools that consume `terraform show -json` or `terraform output -json` for automation (dashboards, drift detectors) receive sensitive values in full — any pipeline piping that JSON somewhere less trusted than the Terraform run itself reintroduces the exposure `sensitive` was meant to prevent.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                | Likely Cause                                                                                                                                    | Resolution Path                                                                                                                                                                                                                    |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Error: Output refers to sensitive values`                             | An output's `value` derives from a `sensitive`-marked variable/resource attribute but lacks `sensitive = true` itself                           | Add `sensitive = true` to the output block, or restructure to avoid exposing the sensitive value at that boundary                                                                                                                  |
| Secret still visible in `terraform.tfstate` despite `sensitive = true` | Misunderstanding `sensitive` scope — it redacts CLI output only, never state serialization                                                      | Treat state backend access control and encryption ([§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)) as the actual protection; rotate any secret exposed in an unprotected state file |
| A secret appears in CI build logs despite being marked `sensitive`     | The secret was passed via a literal `-var` flag or interpolated into a log line the pipeline itself prints, bypassing Terraform's own redaction | Use `TF_VAR_*` environment variable injection ([§40](./Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)) instead of `-var`, and audit pipeline steps for values echoed outside Terraform's own CLI output           |

## 9. Best Practices

- Mark every variable and output that represents a credential, token, private key, or connection string containing credentials as `sensitive = true` without exception, as a baseline hygiene practice.
- Never rely on `sensitive` marking alone for genuinely high-value secrets — combine it with a secrets manager integration ([§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md)/[§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)) and restrictive state backend access ([§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)).
- Audit CI/CD pipeline definitions for places that might echo a full command line, an environment dump, or unredacted JSON output to a log — these bypass Terraform's own redaction entirely.

## 10. Common Anti-Patterns / Mistakes

- **Treating `sensitive = true` as equivalent to encryption.** It's a display-layer redaction; the value sits in plaintext in state regardless.
- **Passing secrets via `-var` on the command line "because it's marked sensitive anyway."** The `sensitive` flag doesn't prevent the shell-history and process-listing exposure that comes from using `-var` in the first place — the marking and the assignment-method choice are independent concerns.
- **Assuming `terraform output` with no arguments fully hides a sensitive value forever.** `terraform output <name>` and `-json` variants both still reveal it — `sensitive` narrows visibility in the default summary, it doesn't lock the value away entirely from the CLI.

## 11. Interview Questions

**🎯 Beginner:** _"What does marking a Terraform variable `sensitive = true` actually do?"_
**Model answer:** It tells Terraform's CLI to redact that value — printing `(sensitive value)` instead of the real string — anywhere it would otherwise appear in `plan`/`apply` output, preventing accidental exposure in a terminal, screen share, or CI log. It does not encrypt the value or change how it's stored anywhere else.
_What the interviewer is probing for:_ Whether the candidate knows this is a display-layer control, the most fundamental fact about this feature.

**🎯 Intermediate:** _"If a variable is marked `sensitive`, is the resulting value protected in the state file?"_
**Model answer:** No — sensitive marking has no effect on state serialization. The value is written to `terraform.tfstate` in plaintext exactly as it would be without the marking. The actual protection for state-stored secrets comes from controlling who can read the state backend (IAM policies on an S3 bucket, Terraform Cloud's access controls) and encrypting it at rest — `sensitive` only controls what's printed to the terminal or logs during a run.
_What the interviewer is probing for:_ The single most commonly tested nuance of this topic — candidates who assume `sensitive` protects state reveal a real security gap in their mental model.

**🎯 Senior:** _"A junior engineer marks a database password variable `sensitive`, then passes it on the command line with `-var="db_password=..."` in a CI script that echoes each command before running it. Is the secret protected?"_
**Model answer:** No. The `sensitive` marking only redacts Terraform's own CLI output (plan diffs, output listings) — it has no effect on what the CI system itself chooses to log before invoking Terraform. If the pipeline echoes the full command line (a common default in many CI systems' verbose/debug modes), the secret leaks at that layer entirely independent of the `sensitive` flag. The fix is to change the assignment method, not the sensitivity marking: inject the secret via a `TF_VAR_db_password` environment variable set from a secrets manager, and ensure the CI system doesn't log environment variable contents either.
_What the interviewer is probing for:_ Whether the candidate can reason about the full pipeline surface, not just the Terraform-internal redaction, and correctly separates "sensitive marking" from "assignment method choice" as two independent controls.

**🎯 Architect:** _"You're designing secrets handling for an organization where several modules generate secrets (e.g., randomly generated database passwords via the `random_password` resource) and pass them between modules as outputs. What's your end-to-end approach to keeping these actually secure, not just `sensitive`-marked?"_
**Model answer:** First, minimize how many secrets Terraform generates and stores at all — where the target service/provider supports it, prefer having Terraform reference a secret created and rotated in a dedicated secrets manager (Vault, AWS Secrets Manager, [§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md)/[§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)) via a data source rather than generating and storing the raw value in its own state. Where Terraform must generate a secret (e.g., an initial database master password), mark every variable and output carrying it `sensitive = true` end-to-end through every module boundary it crosses, since the propagation requirement forces this to be explicit rather than accidentally dropped at some intermediate output. Treat the state backend as the primary security boundary: encryption at rest, tightly scoped IAM/access-control policies limiting who can read state ([§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)), and ideally a backend that supports fine-grained audit logging of state reads. Restrict CI/CD execution roles to only the state and secrets they need ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)), and audit pipeline logging configuration so that verbose/debug modes never echo full command lines or environment dumps. Finally, treat any secret that transited an unprotected state file (e.g., discovered during an incident review) as compromised and rotate it — `sensitive` marking is a hygiene practice that reduces _accidental_ exposure surface, not a guarantee against a determined reader of state.
_What the interviewer is probing for:_ Whether the candidate designs defense-in-depth around secrets rather than treating one flag as sufficient, and understands the specific limits of each individual control.

## 12. Common Misconceptions

1. **"`sensitive = true` encrypts the value."** It only affects CLI/log display formatting — state storage is unaffected and remains plaintext.
2. **"`terraform output` with no arguments hides a sensitive value permanently."** Requesting that specific output by name, or using `-json` output modes, still reveals the real value — it's hidden from the default summary listing only.
3. **"Marking a variable sensitive retroactively redacts it from state written before the marking existed."** Sensitivity marking only affects behavior going forward from when it's added to configuration; prior state entries for that value remain exactly as they were written.
4. **"If I mark my variable sensitive, I don't need to worry about how I assign it a value."** The assignment method ([§40](./Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)) is an independent concern — `-var` on the command line exposes a secret via shell history regardless of `sensitive` marking on the variable.

## 13. 🔑 Key Takeaways

- `sensitive = true` on a `variable` or `output` block redacts that value from Terraform's own CLI output (plan/apply diffs, default `terraform output` listing) — it is a display-layer control.
- Sensitive values are still stored in plaintext in the state file regardless of marking; state backend access control and encryption at rest are the actual protection layer ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md), [§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)).
- Sensitivity propagates automatically through references — any output deriving from a sensitive value must itself be marked `sensitive` or Terraform errors at plan time.
- `terraform output <name>` and `-json` output modes still reveal the real value even when the summary listing redacts it — human-facing default output is what's protected, not every CLI surface.
- For genuinely high-sensitivity secrets, prefer sourcing them from a dedicated secrets manager rather than generating and storing them directly in Terraform state.

## 14. Related Concepts & What's Next

[§42](./Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md) covers output values in full generality — declaration, dependency ordering, and consumption patterns — of which `sensitive` outputs are one variant. [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) goes deep on the broader risk of secrets in state and mitigation strategies beyond `sensitive` marking. [§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md) and [§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md) cover integrating Vault and cloud-native secrets managers as the preferred alternative to generating secrets directly in Terraform. [§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md) covers securing the backend itself, the actual protection boundary this section repeatedly points to.

**Next Section:** [§42](./Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md) — `Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md`
