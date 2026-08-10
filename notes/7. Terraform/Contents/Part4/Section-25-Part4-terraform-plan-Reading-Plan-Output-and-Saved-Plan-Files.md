# Section 25 (Part 4): terraform plan — Reading Plan Output and Saved Plan Files

## 1. Definition

**Plain language:** `terraform plan` is Terraform's "dry run." It compares what your configuration says should exist against what Terraform's state file says currently exists, checks in with the real infrastructure to see if anything drifted, and prints a detailed, human-readable list of exactly what it would create, change, or destroy — without actually touching anything. Nothing is modified until a separate `apply` step confirms it.

**Precise definition:** `terraform plan` computes an **execution plan**: it (1) refreshes its understanding of real-world resource state by querying providers (unless refresh is disabled), (2) walks the resource dependency graph ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) evaluating the configuration against current state and any inputs (variables, data sources), and (3) produces a diff of proposed actions — `create`, `update`, `destroy`, or `no-op` — per resource, annotated with `+`, `-`, `~`, and `-/+` symbols, plus a summary count line. The plan can optionally be written to a **saved plan file** with `-out`, which freezes the exact set of proposed actions so a later `terraform apply <planfile>` executes precisely what was reviewed — with no possibility of drift between plan-time and apply-time changing the outcome.

> 💡 **Tip:** A plan without `-out` is **never guaranteed to match** a later `apply` — anything else that changes the real infrastructure or the configuration between the two commands can change the outcome. Any workflow that requires a human to review a plan before approving an apply (which should be nearly all production workflows) must use a saved plan file, not two independent commands.

## 2. Why This Matters

- **It's the single most important safety mechanism in Terraform's workflow.** Reading plan output carefully — especially spotting an unexpected `-/+` (destroy and recreate) on a stateful resource like a database — is what prevents accidental data loss in production.
- **The diff symbols encode real operational risk, not just cosmetic change.** A `~` (in-place update) is usually low-risk; a `-/+` (replace) means the existing resource is destroyed and a new one created, which for anything holding data is a very different risk profile.
- **Saved plan files make `apply` deterministic and reviewable.** Nearly every mature CI/CD pipeline for Terraform ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md), [§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)) is built around "plan on PR, save the plan artifact, apply that exact artifact after approval" rather than re-planning at apply time.
- **The refresh step means `plan` itself makes API calls to your cloud provider** — it is not a purely local, offline operation, and can be slow or rate-limited against large infrastructures.
- **Misreading plan output (skimming past a destroy) is one of the most common causes of real production incidents** with Terraform — this section exists specifically to build the habit of reading it correctly.

## 3. Prerequisites and Dependencies

Requires a successfully initialized working directory — see [§24](./Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md). Understanding of the resource graph and Terraform's refresh/plan/apply execution model ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md), [§12](../Part2/Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md)) explains _why_ plan output looks the way it does. Resource addressing ([§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md)) is needed to fully read resource identifiers in plan output. State fundamentals ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)) and drift/refresh ([§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md)) are directly relevant since `plan` is the primary tool for detecting drift.

## 4. Architecture / Conceptual Diagram

```text
                     terraform plan
                           │
   ┌───────────────────────┼───────────────────────┐
   ▼                       ▼                       ▼
Configuration          State File            Real Infrastructure
(.tf files —          (terraform.tfstate —    (queried live via
 desired state)        last-known state)       provider APIs)
   │                       │                       │
   │                       └──────────┬────────────┘
   │                                  ▼
   │                      1. Refresh: reconcile state
   │                         with real infra (detect drift)
   │                                  │
   └──────────────┬───────────────────┘
                  ▼
        2. Diff: desired (config) vs.
           refreshed actual (state)
                   │
                   ▼
        3. Execution Plan
   ┌──────────────────────────────────┐
   │  + aws_instance.web (create)     │
   │  ~ aws_instance.api (update)     │
   │  - aws_instance.old (destroy)    │
   │ -/+ aws_db_instance.x (replace)  │
   └──────────────────────────────────┘
                   │
          -out=tfplan (optional)
                   ▼
         Saved, frozen plan file
       (binary; input to `apply`)
```

- **Refresh** — Querying providers for the current real state of every resource already in state, before diffing ([§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md)). Can be skipped with `-refresh=false` for speed at the cost of accuracy.
- **Diff engine** — Compares desired (config) against refreshed actual (state), per resource attribute, determining the minimal action needed.
- **Saved plan file** — A binary artifact (not human-editable) capturing the exact proposed actions; `terraform show -json <planfile>` ([§30](./Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md)) renders it as machine-readable JSON.

## 5. Hands-On

### 5.1 Basic Plan — Reading Diff Symbols

**Purpose:** Preview proposed changes before applying anything.

**Syntax:**

```bash
terraform plan [options]
```

**Example usage and expected output:**

```bash
$ terraform plan

aws_instance.web: Refreshing state... [id=i-0abc123def456]
aws_db_instance.main: Refreshing state... [id=db-mydb]

Terraform used the selected providers to generate the following execution
plan. Resource actions are indicated with the following symbols:
  + create
  ~ update in-place
  - destroy
-/+ destroy and then create replacement

Terraform will perform the following actions:

  # aws_instance.api will be updated in-place
  ~ resource "aws_instance" "api" {
        id            = "i-0def456abc789"
      ~ instance_type = "t3.small" -> "t3.medium"
        tags          = {
            "Name" = "api-server"
        }
        # (8 unchanged attributes hidden)
    }

  # aws_instance.web will be created
  + resource "aws_instance" "web" {
      + ami                    = "ami-0c55b159cbfafe1f0"
      + id                     = (known after apply)
      + instance_type          = "t3.micro"
      + private_ip             = (known after apply)
      + public_ip              = (known after apply)
      + subnet_id              = "subnet-0a1b2c3d"
      + tags                   = {
          + "Name" = "web-server"
        }
    }

  # aws_db_instance.main must be replaced
-/+ resource "aws_db_instance" "main" {
      ~ engine_version      = "14.6" -> "16.1" # forces replacement
      ~ id                  = "db-mydb" -> (known after apply)
        identifier          = "mydb"
    }

  # aws_instance.old will be destroyed
  - resource "aws_instance" "old" {
      - ami           = "ami-0c55b159cbfafe1f0" -> null
      - id            = "i-0999888777aaa" -> null
      - instance_type = "t2.micro" -> null
    }

Plan: 1 to add, 1 to change, 1 to destroy, 1 to replace.
```

**Production usage example:** This exact output format is what reviewers read on every pull request in a plan-gated GitOps workflow ([§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)) — the `-/+` on `aws_db_instance.main` is the kind of line that must stop a merge and trigger a discussion (e.g., can `engine_version` be upgraded in-place via a different approach, or does this genuinely require a maintenance window and a new instance).

**Common errors:**

```text
Error: Reference to undeclared input variable

  on main.tf line 12, in resource "aws_instance" "web":
  12:   instance_type = var.instance_type

An input variable with the name "instance_type" has not been declared.
```

This is a configuration error caught at plan time — plan fails fast rather than partially computing a plan, which is exactly the behavior you want before anything touches real infrastructure.

### 5.2 Saving a Plan File

**Purpose:** Freeze an exact execution plan to a file so a later `apply` executes precisely what was reviewed, with no risk of drift or config changes altering the outcome between review and execution.

**Syntax:**

```bash
terraform plan -out=<PATH>
```

**Example usage and expected output:**

```bash
$ terraform plan -out=tfplan
...
Plan: 1 to add, 1 to change, 1 to destroy, 1 to replace.

Saved the plan to: tfplan

To perform exactly these actions, run the following command to apply:
    terraform apply "tfplan"
```

**Production usage example:** The standard pattern in a CI pipeline: a `plan` job runs on every pull request, saves `tfplan` as a build artifact and posts the human-readable diff as a PR comment; after human approval, a separate `apply` job downloads that exact artifact and runs `terraform apply tfplan` — guaranteeing the applied changes are byte-for-byte what was reviewed, not a fresh re-plan that could differ if the target environment changed in the meantime.

**Common errors:** Applying a saved plan file against a working directory whose state has since changed (e.g., someone else applied a different change in between) fails with an explicit error rather than silently applying a stale plan:

```text
Error: Saved plan is stale

The given plan file can no longer be applied because the state was changed
by another operation after the plan was created.
```

This is a safety feature, not a bug — the fix is to discard the stale plan and re-plan.

### 5.3 Scoping a Plan: Targeting and Variable Files

**Purpose:** Narrow the scope of a plan to specific resources, or supply variable values explicitly rather than relying on defaults/environment.

**Syntax:**

```bash
terraform plan -target=<RESOURCE_ADDRESS>
terraform plan -var-file="prod.tfvars"
terraform plan -var="instance_type=t3.large"
```

**Example usage and expected output:**

```bash
$ terraform plan -target=aws_instance.web -var-file="prod.tfvars"

Warning: Resource targeting is in effect

You are creating a plan with the -target option, which means that the
result of this plan may not represent all of the changes present in your
configuration.
...
Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** `-target` is reached for during incident response — e.g., recreating one broken resource without touching the rest of a large configuration — but is deliberately noisy about it (the warning above) because HashiCorp considers routine use an anti-pattern; full targeting semantics and trade-offs are covered in [§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md).

**Common errors:** Repeated, routine use of `-target` in normal workflows tends to produce configurations whose full, untargeted plan later surprises the team with a large batch of unrelated accumulated changes — `-target` should be an exception-handling tool, not a habit.

### 5.4 Detecting Drift Without a Full Plan

**Purpose:** Check whether real infrastructure has drifted from state, using `plan`'s refresh step as a read-only detection tool.

**Syntax:**

```bash
terraform plan -refresh-only
```

**Example usage and expected output:**

```bash
$ terraform plan -refresh-only

aws_instance.web: Refreshing state... [id=i-0abc123def456]

Note: Objects have changed outside of Terraform

Terraform detected the following changes made outside of Terraform since the
last "terraform apply":

  # aws_instance.web has changed
  ~ resource "aws_instance" "web" {
        id            = "i-0abc123def456"
      ~ instance_type = "t3.micro" -> "t3.small"
    }

This is a refresh-only plan, so Terraform will not take any actions to undo
these changes.
```

**Production usage example:** Scheduled, off-hours drift-detection jobs ([§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)) run `plan -refresh-only` on a cron schedule and alert if any drift is found, without risking an unattended `apply` making unreviewed changes to production.

**Common errors:** Confusing `-refresh-only` with a normal plan and being surprised that it never proposes to "fix" drift by re-applying the configuration — that's by design; `-refresh-only` updates Terraform's recorded state to match reality, it does not reconcile reality back to the configuration (full drift handling is covered in [§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md)).

## 6. Production Usage Notes

- **Plan output order is not guaranteed to match resource declaration order** — Terraform orders actions per the dependency graph ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)), which is why unrelated resources can appear interleaved.
- **`(known after apply)` is normal and expected** for any attribute whose value the provider only determines once the resource actually exists (e.g., a generated ID or an IP address) — it is not an error or a sign of a broken plan.
- **A completely empty plan (`No changes.`) is a valid and common outcome** — it confirms configuration, state, and real infrastructure are all in agreement, and is the expected steady-state result of running `plan` repeatedly against unchanged infrastructure.
- **Large plans against large state files can be slow**, dominated by the refresh step making one API call per resource; `-refresh=false` trades accuracy for speed and should be used deliberately, not as a default habit.

## 7. Security Considerations

- Plan output routinely includes resource attribute values — including ones marked `sensitive` in the configuration ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)), which are redacted in the CLI's human-readable output but **not** redacted in `-json` plan output by default unless properly marked, meaning CI logs and stored plan artifacts must be treated as potentially containing sensitive data.
- A saved plan file (`-out`) contains a complete rendering of proposed resource state, which can include secrets — treat plan file artifacts in CI with the same access controls as the state file itself, not as harmless build output.
- Because `plan` executes provider read calls against real infrastructure, the credentials used to run `plan` need at least read access across everything the configuration touches — scope this deliberately rather than reusing full `apply`-level credentials for a review-only step where avoidable ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                   | Likely Cause                                                                                  | Resolution Path                                                                                                                                                                                              |
| ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Plan shows changes to a resource nobody touched                                           | Drift — someone or something changed the resource outside Terraform                           | Investigate via `terraform plan -refresh-only` ([§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md)), reconcile config or accept drift deliberately                               |
| `Error: Saved plan is stale`                                                              | State changed after the plan file was created (concurrent apply, drift)                       | Discard the saved plan, re-run `terraform plan` fresh                                                                                                                                                        |
| Plan proposes `-/+` (replace) on an attribute expected to update in-place                 | The changed attribute is one the provider marks as `ForceNew`/requires replacement            | Check provider docs for that attribute; consider `lifecycle { create_before_destroy = true }` ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) |
| Plan is extremely slow                                                                    | Large state file, many resources refreshed serially, or slow provider APIs                    | Consider `-refresh=false` for a quick look, increase `-parallelism` ([§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)), or split state (Part 15)        |
| Plan output shows attributes as `(known after apply)` unexpectedly on unrelated resources | An upstream dependency in the graph is itself changing, propagating unknown values downstream | Trace the dependency chain ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)); this is expected graph behavior, not an error                                |

## 9. Best Practices

- Always read plan output fully, resource by resource — never skim straight to the summary count line, especially watching for `-/+` on stateful resources (databases, storage).
- Use `-out` to save plans in any workflow with a human approval gate, and apply the saved file — never re-plan at apply time in a reviewed pipeline.
- Treat `-target` as an incident-response escape hatch, not a routine planning flag.
- Run `-refresh-only` on a schedule against production to catch drift proactively rather than discovering it during the next routine change.

## 10. Common Anti-Patterns / Mistakes

- **Approving a plan by reading only the summary line ("Plan: 3 to add, 1 to change, 0 to destroy").** The summary hides _which_ resources are affected and whether a "change" is actually a destructive replace.
- **Running `plan` and `apply` as two separate, un-linked commands in CI** and assuming the apply will do exactly what the plan showed — without `-out`, it might not.
- **Routine, habitual use of `-target`** to "speed up" plans, accumulating an ever-larger set of untested, unreviewed pending changes in the full configuration.
- **Ignoring `-refresh-only` drift reports** because "nothing broke yet" — unaddressed drift compounds and eventually causes a confusing, large forced change during a routine `apply`.

## 11. Interview Questions

**🎯 Beginner:** _"What do the `+`, `-`, and `~` symbols mean in `terraform plan` output?"_
**Model answer:** `+` means the resource will be created, `-` means it will be destroyed, `~` means it will be updated in place, and `-/+` together means it will be destroyed and then recreated as a replacement rather than updated in place.
_What the interviewer is probing for:_ Basic fluency reading the most common Terraform output a candidate will see daily.

**🎯 Intermediate:** _"Why would Terraform propose to destroy and recreate a resource instead of updating it in place?"_
**Model answer:** Some resource attributes are immutable at the provider/API level — the cloud provider simply doesn't support changing them on an existing resource (e.g., certain database engine version jumps, or an EC2 instance's AMI). The provider schema marks such attributes as forcing replacement, so any change to them makes Terraform propose destroy-then-create instead of an in-place update. This is a real operational event, not a modeling choice Terraform makes arbitrarily.
_What the interviewer is probing for:_ Understanding that plan behavior reflects real provider/API constraints, and awareness that replacement is a higher-risk action for stateful resources.

**🎯 Senior:** _"Why is `terraform plan -out=tfplan` followed by `terraform apply tfplan` considered safer than running `plan` and `apply` as separate, unlinked commands?"_
**Model answer:** Without a saved plan file, `apply` performs its own fresh plan internally right before executing — if anything changed in the real infrastructure, the state, or the configuration between the reviewed `plan` and the `apply`, the actions actually executed can differ from what was reviewed and approved. A saved plan file freezes the exact proposed actions at plan time; `apply <planfile>` executes precisely that, and Terraform explicitly refuses to apply a stale plan file if the state has changed underneath it. This makes human review of a plan a meaningful safety gate rather than a best-effort preview.
_What the interviewer is probing for:_ Whether the candidate understands plan/apply as a security- and correctness-relevant workflow decision, not just two commands run back to back.

**🎯 Architect:** _"Design the plan/apply stage of a CI/CD pipeline for a team that requires human approval before any infrastructure change reaches production. What specifically would you build in, and what failure modes would you defend against?"_
**Model answer:** A `plan` job runs on every PR, produces a saved plan file, uploads it as a build artifact, and posts the human-readable diff (or `-json` output rendered nicely, [§30](./Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md)) as a PR comment for review. Merge or an explicit approval gate triggers an `apply` job that downloads that exact plan artifact and runs `terraform apply <planfile>` — never a fresh plan. Defenses: reject the apply if the plan artifact is stale (Terraform does this natively); enforce state locking ([§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) so no concurrent run can apply a conflicting change between plan and apply; scope plan-stage credentials to read-only where the provider supports it, reserving full read/write credentials for the apply stage only; retain plan artifacts and their JSON rendering as an audit trail tied to the approving human, satisfying compliance requirements for who-approved-what. Also schedule independent drift-detection (`-refresh-only`) outside the deploy pipeline, since drift can occur between deploys and a plan-only PR-triggered pipeline won't catch it on its own.
_What the interviewer is probing for:_ End-to-end pipeline design thinking — safety, auditability, and the specific mechanics of saved plan files, not just "we run plan then apply."

## 12. Common Misconceptions

1. **"`terraform plan` is read-only and makes no external calls."** It performs a refresh against real infrastructure via provider APIs by default — it's read-only with respect to _making changes_, but it does perform live network calls unless `-refresh=false` is set.
2. **"An unsaved plan and its later `apply` will always do the same thing."** Only true if nothing changes state, config, or real infrastructure in between — which is exactly what `-out` and applying the saved file guarantees, and a bare `plan` followed by a bare `apply` does not.
3. **"`-target` is a normal, everyday flag for narrowing scope."** HashiCorp explicitly discourages routine use — it's an escape hatch for specific situations (like incident response), and habitual use accumulates unreviewed configuration drift.
4. **"`-refresh-only` fixes drift."** It only updates Terraform's state to reflect reality; it does not change real infrastructure to match the configuration — that still requires a normal `apply` after the drift is addressed in configuration or accepted.

## 13. 🔑 Key Takeaways

- `terraform plan` diffs desired configuration against refreshed real-world state and prints a precise, symbol-annotated list of proposed actions — it changes nothing by itself.
- Reading plan output means reading every resource line, not just the summary count — `-/+` on a stateful resource is the single most important thing to catch before approving.
- `-out` produces a saved plan file that `apply` can execute exactly, closing the gap between what was reviewed and what actually happens — essential for any approval-gated workflow.
- `-target` and `-refresh-only` are targeted diagnostic/incident tools, not everyday planning habits.
- Plan performs live provider API calls during refresh by default, meaning it's neither instantaneous nor entirely free of external side effects like rate-limit consumption.

## 14. Related Concepts & What's Next

[§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)–[§12](../Part2/Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md) cover the resource graph and execution model that determine plan ordering and diffing internals in more depth. [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md) and [§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) cover state and drift/refresh fully. [§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md) covers resource targeting semantics in depth beyond this section's brief introduction. [§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) covers the full PR-based plan/apply GitOps pattern this section previewed. Next, [§26](./Section-26-Part4-terraform-apply-and-terraform-destroy.md) covers `terraform apply` and `terraform destroy` — the commands that actually execute (or reverse) the plan this section teaches you to read.

**Next Section:** [§26](./Section-26-Part4-terraform-apply-and-terraform-destroy.md) — `Section-26-Part4-terraform-apply-and-terraform-destroy.md`
