# Section 30 (Part 4): terraform show, terraform output, and Machine-Readable (-json) Output

## 1. Definition

**Plain language:** `terraform show` displays the contents of a state file or a saved plan file in a readable format — either the same human-readable style `plan`/`apply` print, or a fully structured JSON document. `terraform output` prints the values of a configuration's declared `output` blocks — the specific values a module or root configuration was designed to expose, like a load balancer's DNS name or a generated database password.

**Precise definition:** `terraform show [PATH]` renders either the **current state** (no argument) or a **saved plan file** (path argument) — human-readable by default, or as a structured JSON document with `-json`, following Terraform's documented, versioned JSON output schema. `terraform output [NAME]` reads only the **outputs section of state**, printing either every declared output or one named output; it supports `-json` for structured consumption and `-raw` for a single string value with no quoting, ideal for direct use in shell scripts. Both commands are **read-only** against state — neither modifies anything — and both are the primary mechanism for **programmatic consumption** of Terraform's results by external tooling (CI systems, scripts, dashboards).

> 💡 **Tip:** `terraform output -raw <name>` is the single most useful command for shell scripting — it prints a bare, unquoted string value (no JSON, no trailing newline complications from quoting) ready to be captured directly into a shell variable, e.g. `IP=$(terraform output -raw instance_ip)`.

## 2. Why This Matters

- **These are the commands that let other systems consume Terraform's results.** A CI pipeline that needs to feed a newly-created load balancer's address into a subsequent deployment step reads it via `terraform output`, not by parsing `apply` log text.
- **`-json` output is a stable, versioned, documented schema** — unlike scraping human-readable CLI text (which can change format between releases with no notice), tooling built against `-json` output has an actual contract to depend on.
- **`terraform show` on a saved plan file is how PR-comment bots and policy engines inspect proposed changes programmatically** — turning the plan diff into something a bot can parse and comment on, or a policy tool (Sentinel/OPA, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md), [§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)) can evaluate against rules before allowing an apply.
- **Sensitive output handling has real consequences here** — `-json` output does include values marked `sensitive` ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) in the underlying data (with a `sensitive` flag alongside them), meaning any pipeline capturing `-json` output must handle it as securely as the state file itself.
- **`terraform output` is often the very last step of a deployment pipeline** — the thing that hands off a concrete, usable result (a URL, an IP, a connection string) to whatever comes next in a larger automation chain.

## 3. Prerequisites and Dependencies

Requires an existing state file with at least one `apply` having run ([§26](./Section-26-Part4-terraform-apply-and-terraform-destroy.md)) — `output` and `show` on state have nothing to display against a never-applied configuration. Output value declaration ([§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md)) and sensitive outputs ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) are directly relevant — this section covers _reading_ outputs the CLI-consumption way; [§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md) covers _declaring_ them. Saved plan files ([§25](./Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md)) are what `show` renders when given a plan path rather than defaulting to state.

## 4. Architecture / Conceptual Diagram

```text
                    ┌──────────────────────────┐
                    │   terraform.tfstate      │
                    │  (or saved plan file)    │
                    └──────────────────────────┘
                          │              │
        ┌─────────────────┘              └───────────────────┐
        ▼                                                    ▼
terraform show                                    terraform output
(entire state OR plan,                            (ONLY the outputs
 full resource detail)                             section of state)
        │                                                    │
   ┌────┴────┐                                          ┌────┴────┐
   ▼         ▼                                          ▼         ▼
human-      -json                                   human-      -json / -raw
readable   (versioned                                readable    (structured or
 (default)  schema, stable                            (default)   bare string)
            contract)
        │         │                                        │         │
        ▼         ▼                                        ▼         ▼
  terminal   CI tooling,                              terminal   shell scripts,
  reading    policy engines                           reading     downstream
             (Sentinel/OPA,                                       automation
              PR bots)                                            (IP=$(... -raw))
```

- **`show` with no argument** reads current state. **`show <planfile>`** reads a saved plan. Same command, different input, same dual human/JSON output modes.
- **`output` is scoped strictly to declared outputs** — it cannot show arbitrary resource attributes not explicitly exposed via an `output` block; that's what `show` (or `console`, [§28](./Section-28-Part4-terraform-console-and-terraform-graph.md)) is for.

## 5. Hands-On

### 5.1 terraform show — Human-Readable State Inspection

**Purpose:** Review the full current state in the same readable format `plan`/`apply` use, without needing to run a new plan.

**Syntax:**

```bash
terraform show [options] [PATH]
```

**Example usage and expected output:**

```bash
$ terraform show

# aws_instance.web:
resource "aws_instance" "web" {
    ami                    = "ami-0c55b159cbfafe1f0"
    id                     = "i-0abc123def456"
    instance_type          = "t3.micro"
    private_ip             = "10.0.1.15"
    public_ip              = "54.183.10.22"
    tags                   = {
        "Name" = "web-server"
    }
}

# aws_db_instance.main:
resource "aws_db_instance" "main" {
    id                = "db-mydb-new"
    engine            = "postgres"
    engine_version     = "16.1"
    identifier        = "mydb"
}
```

**Production usage example:** A quick way to audit exactly what Terraform currently believes is deployed — e.g., confirming a specific resource's attribute value without writing a temporary output or opening `console` — often the fastest path to answering "what does state actually say right now" during an incident.

**Common errors:**

```text
$ terraform show
No state.
```

Expected output for a working directory that's been `init`-ed but never `apply`-ed — not an error, just an accurate report of empty state.

### 5.2 terraform show -json — Machine-Readable State or Plan

**Purpose:** Emit a structured, versioned JSON representation of state or a saved plan for programmatic consumption.

**Syntax:**

```bash
terraform show -json [PATH]
```

**Example usage and expected output:**

```bash
$ terraform show -json tfplan | jq '.resource_changes[] | {address, actions: .change.actions}'
{
  "address": "aws_instance.web",
  "actions": ["create"]
}
{
  "address": "aws_db_instance.main",
  "actions": ["delete", "create"]
}
{
  "address": "aws_instance.api",
  "actions": ["update"]
}
```

**Production usage example:** CI pipelines pipe `terraform show -json <planfile>` into `jq` (or a dedicated parsing library) to build custom PR-comment summaries, feed a policy-as-code check outside of Terraform Cloud/Enterprise's built-in Sentinel/OPA integration ([§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)), or drive automated approval logic (e.g., "auto-approve if the plan contains zero `delete` actions").

**Common errors:** Treating the `-json` schema as stable across major Terraform version boundaries without checking the `format_version` field — HashiCorp does version this schema and can introduce breaking changes between major versions; well-built tooling checks `format_version` rather than assuming a fixed shape forever.

### 5.3 terraform output — Reading Declared Outputs

**Purpose:** Retrieve the values of a configuration's `output` blocks after a successful apply.

**Syntax:**

```bash
terraform output [options] [NAME]
```

**Example usage and expected output:**

```bash
$ terraform output
db_endpoint = "mydb-new.abc123xyz.us-east-1.rds.amazonaws.com:5432"
instance_public_ip = "54.183.10.22"
db_password = <sensitive>

$ terraform output instance_public_ip
"54.183.10.22"
```

**Production usage example:** A deployment script that provisions infrastructure with Terraform and then needs to hand off a connection endpoint to an application deployment step — `terraform output db_endpoint` is the standard way that value crosses from the infrastructure layer into the application layer of a pipeline.

**Common errors:**

```text
$ terraform output nonexistent_output

Warning: Output not found

The output variable requested could not be found in the state file. If you
recently added this to your configuration, be sure to run `terraform apply`,
since the state won't be updated with new output variables until that command
is run.
```

A very common early-learning error: adding an `output` block to configuration doesn't populate it in state until an `apply` actually runs.

### 5.4 terraform output -raw and -json for Scripting

**Purpose:** Consume output values programmatically — `-raw` for a single bare string in shell scripts, `-json` for structured consumption of multiple/complex outputs.

**Syntax:**

```bash
terraform output -raw <NAME>
terraform output -json
```

**Example usage and expected output:**

```bash
$ IP=$(terraform output -raw instance_public_ip)
$ echo "Deployed instance reachable at: $IP"
Deployed instance reachable at: 54.183.10.22

$ terraform output -json
{
  "db_endpoint": {
    "sensitive": false,
    "type": "string",
    "value": "mydb-new.abc123xyz.us-east-1.rds.amazonaws.com:5432"
  },
  "db_password": {
    "sensitive": true,
    "type": "string",
    "value": "S3cr3tP@ss!"
  },
  "instance_public_ip": {
    "sensitive": false,
    "type": "string",
    "value": "54.183.10.22"
  }
}
```

Note that `-json` **includes the real value even for sensitive outputs**, only flagging them with `"sensitive": true` — the human-readable default output masks sensitive values as `<sensitive>`, but `-json` deliberately does not, since structured consumers need the actual value to function.

**Production usage example:** A CI job exports `terraform output -json` to a file consumed by a later pipeline stage (e.g., feeding connection details into a Kubernetes secret or an application's environment configuration) — `-raw` is used for single scalar values passed directly as shell variables or CLI arguments to a next command.

**Common errors:** Using `-raw` on an output whose value is a list, map, or object fails — `-raw` only supports single string, number, or boolean values; complex types require `-json` and downstream parsing (e.g., with `jq`).

## 6. Production Usage Notes

- **`-json` output from `show` on state or plan and from `output` do include real sensitive values.** Any pipeline capturing this output to a log, artifact, or file must treat that artifact with the same access control rigor as the state file itself — this is a frequent, underappreciated leak vector.
- **`terraform output` only reflects the last successful `apply`.** It does not refresh or re-plan; if real infrastructure changed outside Terraform since the last apply, `output` still reports the stale, last-known value.
- **The `-json` schema for `show` (state/plan) and for `output` are documented and versioned independently** by HashiCorp — check the `format_version` field when building tooling that must remain stable across Terraform CLI upgrades.
- **`show` on a plan file requires the exact same working directory/state context** the plan was generated against — it can't be inspected meaningfully in total isolation from the project it came from.

## 7. Security Considerations

- Because `-json` includes real sensitive values, **CI logs that dump `-json` output to stdout for debugging are a common accidental secrets leak** — redact or avoid printing raw `-json` output in shared/persisted logs; write it to a securely-handled artifact instead if needed downstream.
- The default human-readable `terraform output` correctly masks values marked `sensitive` as `<sensitive>` — but this protection is purely a CLI display convenience, not an access control; anyone with read access to state or the ability to run `-json`/`-raw` against a sensitive output can retrieve the real value.
- Treat any script or pipeline stage capturing `terraform output -raw` on a credential-like value (a generated password, an API key) as itself now holding that credential in whatever it does next (an environment variable, a temp file) — apply the same handling discipline downstream as to the source value.

## 8. Common Troubleshooting Scenarios

| Symptom                                                           | Likely Cause                                                                              | Resolution Path                                                                                        |
| ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `terraform output` shows nothing / empty                          | No `output` blocks declared, or state has never been successfully applied                 | Confirm `output` blocks exist in configuration and that `apply` has run since they were added          |
| `Warning: Output not found` for a recently-added output           | Configuration was updated with a new `output` block, but `apply` hasn't run yet           | Run `terraform apply` — outputs only populate in state after a successful apply                        |
| `-raw` fails on an output that looks like a simple value          | The output's actual type is a list/map/object, not a plain string/number/bool             | Use `-json` instead and parse the structured result (e.g., with `jq`)                                  |
| `-json` output shows stale values relative to real infrastructure | `output`/`show` read state only, without refreshing against real infrastructure           | Run `terraform plan -refresh-only` or `terraform apply` first if current real values are needed        |
| Sensitive value unexpectedly appears in a CI log                  | `-json` output (or a script using `-raw` on a sensitive value) was printed to stdout/logs | Redact pipeline output, avoid printing `-json`/`-raw` of sensitive values in shared logs going forward |

## 9. Best Practices

- Use `-raw` for single scalar values consumed directly in shell scripts; use `-json` for anything structured or when passing results to another program that parses JSON.
- Never print raw `-json` output (of `show` or `output`) directly into CI logs that are broadly readable — capture it to a securely-scoped artifact or variable instead.
- Check `format_version` in `-json` output when building tooling meant to survive Terraform CLI upgrades, rather than assuming schema stability forever.
- Prefer `terraform output <specific-name>` over parsing the full `terraform output` (or `-json`) blob when a script only needs one value — narrower, less brittle to unrelated output changes.

## 10. Common Anti-Patterns / Mistakes

- **Scraping human-readable `plan`/`apply`/`show` text output with regex** instead of using `-json` — human-readable formatting is not a stable contract and can change between Terraform releases without notice.
- **Printing `-json` output of `show` or `output` directly into shared CI logs** for debugging convenience, leaking sensitive values in the process.
- **Assuming `terraform output` reflects live, current infrastructure state** rather than the last-applied state — a common source of confusion after out-of-band changes.
- **Using `-raw` on non-scalar outputs and being surprised by the error**, rather than reaching for `-json` from the start for anything beyond a single simple value.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `terraform show` and `terraform output`?"_
**Model answer:** `terraform show` displays the full contents of state (or a saved plan) — every resource and every attribute Terraform is tracking. `terraform output` shows only the values explicitly declared in `output` blocks — a curated, intentional subset of information a module or configuration author chose to expose, like a specific endpoint or ID other systems need.
_What the interviewer is probing for:_ Basic distinction between "everything Terraform knows" versus "the specific values meant to be consumed externally."

**🎯 Intermediate:** _"Why would a CI pipeline use `terraform show -json` instead of parsing the normal human-readable `terraform plan` output?"_
**Model answer:** Human-readable output is formatted for people to read and isn't a guaranteed stable contract — its exact text and layout can change between Terraform versions without being treated as a breaking change. `-json` output follows a documented, versioned schema (with a `format_version` field) specifically intended for programmatic consumption, making it the reliable choice for any tooling — PR bots, policy engines, custom dashboards — that needs to parse plan or state data automatically rather than scrape text.
_What the interviewer is probing for:_ Understanding of why structured output exists as a distinct, deliberate interface rather than just "another way to print the same thing."

**🎯 Senior:** _"A teammate's CI pipeline prints `terraform output -json` to the build log for debugging. What's the risk, and how would you fix the pipeline?"_
**Model answer:** `-json` output includes the real value of every output, including ones marked `sensitive` in configuration — the `sensitive` flag in the JSON is metadata for consumers to act on, not a redaction Terraform performs itself. So any output holding a password, API key, or similar, gets printed in plaintext into the build log, which is often broadly readable and long-retained — a real credential leak. The fix: never print raw `-json` output of `output`/`show` directly to a shared log; if the values are needed for debugging, log only non-sensitive fields explicitly, or write the full `-json` result to a properly access-controlled artifact instead of stdout, and ensure any downstream consumption of that artifact treats it with the same handling rigor as the state file.
_What the interviewer is probing for:_ Awareness that `-sensitive` masking in `output`'s human-readable default is a display convenience only, and that `-json` deliberately breaks that masking for functional reasons — plus practical remediation instinct.

**🎯 Architect:** _"You're designing a system where a policy engine automatically evaluates every Terraform plan before allowing apply — e.g., blocking any plan that deletes a resource tagged `critical`. How would `terraform show -json` fit into this, and what would you build around it?"_
**Model answer:** `terraform plan -out=tfplan` produces a saved plan file; `terraform show -json tfplan` renders it as a structured document whose `resource_changes` array lists every proposed action (`create`/`update`/`delete`/`no-op`) per resource address, along with the resource's planned attribute values — including tags. A policy engine (custom script, or a proper tool like OPA/Sentinel, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)/[§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)) consumes that JSON, filters `resource_changes` for any entry where `actions` includes `"delete"` and the resource's `tags` (in `change.before` or `change.after`) include `critical = true`, and fails the pipeline if any match is found — blocking the apply stage from ever running against that plan file. Around this, I'd build: a pinned `format_version` check so a Terraform upgrade doesn't silently break the policy parser; the policy check as its own explicit, auditable CI stage (not inlined ad hoc) with clear pass/fail output and a human override path for legitimate exceptions; and, ideally, migrate to Terraform Cloud/Enterprise's native Sentinel or OPA integration ([§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) once the organization's scale justifies the operational overhead of a managed policy engine over a bespoke script.
_What the interviewer is probing for:_ Whether the candidate can design a real policy-as-code gate using `-json` output as the actual data contract, including forward-compatibility and auditability concerns, not just "parse the JSON and check for deletes."

## 12. Common Misconceptions

1. **"`terraform output`'s `<sensitive>` masking is a real security control."** It's a display convenience in the human-readable CLI output only — `-json` includes the real value, and anyone with read access to state can retrieve it regardless.
2. **"`terraform show` and `terraform output` reflect live, current infrastructure."** Both read only from state (or a saved plan) — neither refreshes against real infrastructure; stale state means stale output.
3. **"Human-readable plan/apply text output is a stable format safe to parse with scripts."** It's meant for humans and can change between releases; `-json` is the actual stable, documented contract for programmatic consumption.
4. **"`-raw` works on any output value."** It only supports single scalar values (string/number/bool) — lists, maps, and objects require `-json`.

## 13. 🔑 Key Takeaways

- `terraform show` displays full state or a saved plan; `terraform output` displays only explicitly declared output values — different scopes for different purposes.
- `-json` output follows a documented, versioned schema intended for programmatic consumption; human-readable text output is not a stable contract for scripting against.
- `-json` output includes real sensitive values (flagged, not redacted) — treat any pipeline capturing it with the same access control as the state file itself.
- `-raw` is ideal for single scalar values in shell scripts; `-json` is required for structured/complex output values.
- Both commands are read-only against the last-applied state — neither refreshes against real infrastructure automatically.

## 14. Related Concepts & What's Next

[§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)–[§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md) cover output value declaration and sensitive outputs in full depth — this section covers reading them via CLI, those sections cover authoring them correctly. [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) and [§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) cover Sentinel/OPA policy-as-code, the natural evolution of the custom `-json`-parsing policy patterns previewed here. [§47](../Part7/Section-47-Part7-The-State-File-Format-terraform-tfstate-Deep-Dive.md) covers the state file format that `show` renders directly. Next, and closing out Part 4, [§31](./Section-31-Part4-Common-CLI-Flags-Automation-Friendly-Patterns.md) covers common CLI flags and automation-friendly patterns (`-auto-approve`, `-var-file`, `-target`, `-lock`) that tie together everything covered across this Part into cohesive, automation-ready workflows.

**Next Section:** [§31](./Section-31-Part4-Common-CLI-Flags-Automation-Friendly-Patterns.md) — `Section-31-Part4-Common-CLI-Flags-Automation-Friendly-Patterns.md`
