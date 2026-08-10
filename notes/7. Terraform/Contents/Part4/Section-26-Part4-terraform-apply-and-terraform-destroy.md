# Section 26 (Part 4): terraform apply and terraform destroy

## 1. Definition

**Plain language:** `terraform apply` is the command that actually makes the changes `terraform plan` ([§25](./Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md)) previewed — it creates, updates, and destroys real infrastructure to match your configuration. `terraform destroy` is its counterpart: it tears down every resource Terraform manages in the current state, the reverse of building things up.

**Precise definition:** `terraform apply` executes an **execution plan** against real infrastructure by calling provider APIs to create, update, or destroy resources, then writes the resulting real-world state back into the **state file** ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)) so it stays an accurate record of what Terraform manages. Run with no arguments, it internally computes a fresh plan and prompts for interactive confirmation before executing; run against a **saved plan file** (`terraform apply <planfile>`, [§25](./Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md)), it skips re-planning and confirmation, executing exactly the frozen actions. `terraform destroy` is functionally equivalent to `terraform apply -destroy` — it computes a plan whose only proposed action, for every resource in state, is destruction, then executes it the same way.

> 💡 **Tip:** `terraform destroy` does not "undo" `apply` — it destroys **everything currently tracked in state**, regardless of how it got there. If a resource was created outside Terraform and later `import`ed ([§52](../Part7/Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md)), `destroy` will tear it down just like anything else, with no distinction for its provenance.

## 2. Why This Matters

- **This is the command that has real, often irreversible, consequences.** Everything before it — `init`, `plan`, `validate` — is either read-only or purely local; `apply` and `destroy` are where infrastructure actually changes, including data loss on a destroyed database.
- **The interactive confirmation prompt is the last human checkpoint** in an unscripted workflow — understanding exactly what triggers `-auto-approve` bypassing it ([§31](./Section-31-Part4-Common-CLI-Flags-Automation-Friendly-Patterns.md)) is essential to using automation safely.
- **`apply` updates the state file as a side effect of execution**, not just infrastructure — if `apply` is interrupted partway through, state and reality can diverge in ways that need careful reconciliation.
- **`destroy` is used far more often than "delete everything forever" implies** — ephemeral environments (per-PR preview environments, short-lived test infrastructure) are routinely created and destroyed as a normal part of the workflow, not just as a last resort.
- **Partial failure during `apply` is a real, common scenario** (one resource fails to create after three others succeeded) — knowing how Terraform handles this (it records what succeeded, reports what failed, and a re-run picks up from there) is core operational knowledge.

## 3. Prerequisites and Dependencies

Requires the plan-reading fluency built in [§25](./Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md) — this section assumes you can already read `+`/`-`/`~`/`-/+` diff output. State fundamentals ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)) explain what `apply` writes back after execution. The `lifecycle` block's `prevent_destroy` ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) is the primary guardrail against accidental destruction and is referenced here. Workspaces ([§69](../Part10/Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md)) and environment separation ([§70](../Part10/Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)) are relevant to understanding blast radius when running `apply`/`destroy` against the wrong target.

## 4. Architecture / Conceptual Diagram

```text
terraform apply (no saved plan)              terraform apply <planfile>
        │                                              │
        ▼                                              ▼
 1. Compute fresh plan                        1. Load frozen plan from file
        │                                      2. Verify state hasn't changed
        ▼                                         since plan was saved
 2. Print plan + prompt:                             │
    "Do you want to perform                          ▼
     these actions?                          3. Execute immediately
     Enter a value: yes"                         (no confirmation prompt)
        │
        ▼ (yes)
 3. Execute actions in dependency-graph order
    (creates/updates/destroys, parallelized
     where the graph allows, §11)
        │
        ▼
 4. Write results to state file (§46)
        │
        ▼
 5. Print Apply complete! summary +
    any declared outputs (§42)

terraform destroy
        │
        ▼
 1. Compute plan: destroy every resource in state
        │
        ▼
 2. Print destroy plan + prompt:
    "Do you really want to destroy all resources?
     Enter a value: yes"
        │
        ▼ (yes)
 3. Destroy in REVERSE dependency order
    (dependents destroyed before dependencies)
        │
        ▼
 4. Empty (or reduced) state file written
```

- **Dependency-respecting execution order** — `apply` creates/updates in an order that respects the resource graph (dependencies before dependents); `destroy` reverses this, removing dependents before the resources they depend on, to avoid leaving broken references.
- **Confirmation prompt** — The literal text `Enter a value:` requiring `yes` (not `y`) — bypassed only by `-auto-approve` or by applying a saved plan file.

## 5. Hands-On

### 5.1 Interactive Apply

**Purpose:** Execute proposed changes with a final human confirmation step.

**Syntax:**

```bash
terraform apply [options]
```

**Example usage and expected output:**

```bash
$ terraform apply

  # aws_instance.web will be created
  + resource "aws_instance" "web" {
      + ami           = "ami-0c55b159cbfafe1f0"
      + instance_type = "t3.micro"
      + id            = (known after apply)
    }

Plan: 1 to add, 0 to change, 0 to destroy.

Do you want to perform these actions?
  Terraform will perform the actions described above.
  Only 'yes' will be accepted to approve.

  Enter a value: yes

aws_instance.web: Creating...
aws_instance.web: Still creating... [10s elapsed]
aws_instance.web: Creation complete after 14s [id=i-0abc123def456]

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

Outputs:

instance_public_ip = "54.183.10.22"
```

**Production usage example:** The standard local developer loop while iterating on a module in a personal sandbox account — `plan`, review, `apply`, confirm, repeat — before ever pushing changes toward a shared or production environment.

**Common errors:**

```text
Error: creating EC2 Instance: UnauthorizedOperation: You are not authorized
to perform this operation.
```

An IAM/authorization failure mid-apply — Terraform stops, reports exactly which resource failed, and leaves already-created resources correctly recorded in state; re-running `apply` after fixing permissions resumes from where it left off rather than starting over.

### 5.2 Applying a Saved Plan File

**Purpose:** Execute exactly the actions reviewed and approved earlier, with no re-planning and no interactive prompt.

**Syntax:**

```bash
terraform apply <PLANFILE>
```

**Example usage and expected output:**

```bash
$ terraform apply tfplan

aws_instance.api: Modifying... [id=i-0def456abc789]
aws_instance.api: Modifications complete after 3s [id=i-0def456abc789]
aws_db_instance.main: Destroying... [id=db-mydb]
aws_db_instance.main: Destruction complete after 1m20s
aws_db_instance.main: Creating...
aws_db_instance.main: Still creating... [30s elapsed]
aws_db_instance.main: Creation complete after 4m2s [id=db-mydb-new]

Apply complete! Resources: 1 added, 1 changed, 1 destroyed.
```

**Production usage example:** The exact mechanism a CI/CD "apply" stage uses after a merged, approved PR ([§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)) — the plan artifact produced during PR review is what gets applied, with no possibility of the actual change diverging from what was reviewed.

**Common errors:** `Error: Saved plan is stale` — covered in [§25](./Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md) — if state changed after the plan was saved, Terraform refuses to apply it; the fix is to discard it and re-plan, never to force it through.

### 5.3 terraform destroy

**Purpose:** Tear down every resource Terraform currently manages in state.

**Syntax:**

```bash
terraform destroy [options]
```

**Example usage and expected output:**

```bash
$ terraform destroy

  # aws_instance.web will be destroyed
  - resource "aws_instance" "web" {
      - id            = "i-0abc123def456" -> null
      - instance_type = "t3.micro" -> null
    }

  # aws_db_instance.main will be destroyed
  - resource "aws_db_instance" "main" {
      - id         = "db-mydb-new" -> null
      - identifier = "mydb" -> null
    }

Plan: 0 to add, 0 to change, 2 to destroy.

Do you really want to destroy all resources?
  Terraform will destroy all your managed infrastructure, as shown above.
  There is no undo. Only 'yes' will be accepted to confirm.

  Enter a value: yes

aws_instance.web: Destroying... [id=i-0abc123def456]
aws_instance.web: Destruction complete after 5s
aws_db_instance.main: Destroying... [id=db-mydb-new]
aws_db_instance.main: Destruction complete after 1m32s

Destroy complete! Resources: 2 destroyed.
```

**Production usage example:** Nightly teardown of ephemeral per-PR preview environments, or teardown of an entire disposable test/staging environment provisioned earlier the same day as part of an automated test pyramid ([§105](../Part14/Section-105-Part14-Automated-Testing-Pyramids-for-IaC.md)) — `destroy` is a normal, expected part of these workflows, not an emergency action.

**Common errors:**

```text
Error: Instance cannot be destroyed

  on main.tf line 8, in resource "aws_db_instance" "main":
   8: resource "aws_db_instance" "main" {

Resource aws_db_instance.main has lifecycle.prevent_destroy set, but the
plan calls for this resource to be destroyed.
```

This is `prevent_destroy` ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) doing exactly its job — protecting a resource from accidental or scripted destruction; the fix, if destruction is genuinely intended, is to remove or override that lifecycle setting deliberately, not to work around it.

### 5.4 Destroying a Single Resource

**Purpose:** Tear down one specific resource without destroying the entire managed infrastructure.

**Syntax:**

```bash
terraform destroy -target=<RESOURCE_ADDRESS>
```

**Example usage and expected output:**

```bash
$ terraform destroy -target=aws_instance.old

Warning: Resource targeting is in effect

  # aws_instance.old will be destroyed
  - resource "aws_instance" "old" { ... }

Plan: 0 to add, 0 to change, 1 to destroy.

Do you really want to destroy all resources?
  Enter a value: yes

aws_instance.old: Destroying... [id=i-0999888777aaa]
aws_instance.old: Destruction complete after 6s

Destroy complete! Resources: 1 destroyed.
```

**Production usage example:** Removing a single misprovisioned or genuinely obsolete resource during cleanup, without regenerating a full plan across an entire large configuration — same targeted-use caveats as `-target` on `plan` ([§25](./Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md), [§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)).

**Common errors:** Forgetting that `-target` only scopes what's destroyed, not what's _evaluated_ — dependent resources referencing the targeted one may still show up in the plan as needing an update, which can surprise operators expecting a fully isolated single-resource operation.

## 6. Production Usage Notes

- **`apply` is not atomic across multiple resources.** If it fails partway through a multi-resource change, some resources are left created/updated and others are not — this is recorded accurately in state, and the correct recovery is almost always to fix the underlying error and re-run `apply`, letting it resume.
- **Destroy order is the reverse of create order** specifically to respect dependencies — e.g., a subnet is not destroyed while an instance still depends on it being present, preventing certain classes of provider-level errors.
- **`prevent_destroy` ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) is the primary guardrail for protecting specific critical resources** (production databases, KMS keys) from any destroy path, whether interactive, scripted, or accidental via `-target`.
- **`-auto-approve` ([§31](./Section-31-Part4-Common-CLI-Flags-Automation-Friendly-Patterns.md)) removes the interactive confirmation entirely** and is standard in CI pipelines applying a pre-reviewed saved plan file — it should almost never be used with a bare, unsaved `plan`+`apply` in an unattended context.

## 7. Security Considerations

- The credentials `apply` runs with need write access to everything the configuration touches — this is the highest-privilege step in the Terraform workflow and should use the most tightly scoped, least-privilege execution role available ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)), separate from broader human credentials where possible.
- `terraform destroy` run with the wrong workspace, wrong `-var-file`, or against the wrong backend can destroy production infrastructure while an operator believes they're targeting a disposable environment — verify `terraform workspace show` ([§69](../Part10/Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md)) and the active backend before ever running `destroy` outside of fully automated, well-tested ephemeral-environment pipelines.
- Outputs printed after `apply` ([§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md)) can include sensitive values if not marked `sensitive` ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) — CI logs capturing apply output are a common accidental secrets-leak vector.

## 8. Common Troubleshooting Scenarios

| Symptom                                                           | Likely Cause                                                                               | Resolution Path                                                                                                                                                                                               |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `apply` fails partway through with some resources created         | A downstream resource failed (API error, quota, invalid config)                            | Fix the root cause, re-run `apply` — Terraform resumes from current (partially-applied) state                                                                                                                 |
| `Error: Instance cannot be destroyed`                             | `lifecycle.prevent_destroy = true` set on the resource                                     | Confirm destruction is truly intended, then deliberately remove/override the lifecycle setting ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) |
| `apply` hangs waiting for confirmation in CI                      | No `-auto-approve` and no saved plan file passed in a non-interactive context              | Use a saved plan file with `-auto-approve`, or pass `-auto-approve` only against a reviewed plan                                                                                                              |
| `destroy` removes fewer resources than expected                   | Some resources live in a different workspace or state file than assumed                    | Verify `terraform workspace show` and backend configuration before destroying ([§69](../Part10/Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md))                                          |
| Apply succeeds but real infrastructure doesn't reflect the change | Provider-side eventual consistency, or the change was to an attribute the provider ignores | Re-run `terraform plan` to confirm state matches config; check provider-specific known issues                                                                                                                 |

## 9. Best Practices

- Always apply a saved plan file in any automated or team-reviewed workflow; reserve bare `terraform apply` for genuinely interactive, single-operator sessions.
- Protect stateful, hard-to-recreate resources with `lifecycle { prevent_destroy = true }` as a default posture, not an afterthought added after a near-miss.
- Double-check the active workspace and backend before running `destroy` — make this an explicit habit, not a trust exercise.
- Treat partial-apply failures calmly: read the error, fix the actual cause, and re-run `apply` rather than manually editing state to "fix" the discrepancy.

## 10. Common Anti-Patterns / Mistakes

- **Using `-auto-approve` on an unsaved, freshly-computed plan in unattended automation.** This removes the human review step entirely with no saved-plan guarantee of what's actually being executed — a materially higher-risk combination than `-auto-approve` on a pre-reviewed saved plan file.
- **Manually editing the state file to "fix" a partial-apply failure** instead of fixing the underlying cause and re-running `apply` — this is one of the most common ways teams corrupt their state.
- **Treating `destroy` as scary and avoiding using it for legitimate ephemeral-environment teardown**, leading to orphaned, forgotten, cost-accumulating test infrastructure.
- **Not verifying workspace/backend context before `destroy`** — the single most common cause of "we destroyed the wrong environment" incidents.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `terraform plan` and `terraform apply`?"_
**Model answer:** `plan` computes and displays proposed changes without touching any real infrastructure; `apply` actually executes those changes against real infrastructure (after confirmation, unless auto-approved or applying a saved plan) and updates the state file to reflect the result.
_What the interviewer is probing for:_ Basic grasp of the dry-run/execute split that underlies Terraform's entire safety model.

**🎯 Intermediate:** _"What happens if `terraform apply` fails after successfully creating 2 of 5 planned resources?"_
**Model answer:** Terraform stops on the failure, reports which resource failed and why, and — critically — the 2 successfully created resources are already recorded in the state file, since state is updated incrementally as each resource completes, not only at the very end. Re-running `apply` after fixing the underlying error picks up from that state and only attempts the remaining 3 resources (plus re-verifying the first 2 are still correct), rather than starting over or duplicating the already-created resources.
_What the interviewer is probing for:_ Understanding that state updates happen incrementally during apply, which is why partial failures are recoverable rather than catastrophic.

**🎯 Senior:** _"Your team has `lifecycle { prevent_destroy = true }` on a production database resource. A `terraform destroy` is run against that environment by mistake. What happens, and why is this an example of good defense-in-depth?"_
**Model answer:** The destroy plan will include the database as a resource marked for destruction, but before executing, Terraform checks the `prevent_destroy` lifecycle setting and refuses with an explicit error (`Instance cannot be destroyed`), halting before any destructive API call is made against that resource. Other, unprotected resources in the same destroy plan may still be destroyed unless the whole operation is aborted — so `prevent_destroy` protects the specific resource it's set on, not the whole configuration. This is defense-in-depth because it doesn't rely on the operator remembering to be careful or on process/review catching the mistake beforehand — the safeguard is encoded directly in configuration and enforced by the tool itself at execution time, independent of who's running the command or how.
_What the interviewer is probing for:_ Whether the candidate understands `prevent_destroy` at a mechanical level (per-resource, enforced at apply/destroy time) and appreciates layered safety design rather than relying purely on process discipline.

**🎯 Architect:** _"Design the safety controls around who can run `terraform destroy` against production, and under what conditions it's allowed to run unattended (e.g., in CI)."_
**Model answer:** Unattended `destroy` against long-lived production environments should essentially never be automated with `-auto-approve` — it should require an interactive human confirmation, or at minimum a separate, explicitly-invoked pipeline stage gated by a second human approval distinct from the one that approves normal applies (asymmetric approval — creating is lower risk than destroying). `prevent_destroy` should be set on all genuinely critical stateful resources as a hard technical backstop independent of process. Workspace/backend context should be verified programmatically before any destroy pipeline proceeds (e.g., a CI job that refuses to run if the target workspace name doesn't match an explicit allowlist for "destroyable" environments). For legitimately ephemeral environments (per-PR preview, nightly test infra), automated `destroy` with `-auto-approve` is appropriate and should be the default, scoped tightly by naming convention or separate state/workspace so it's structurally impossible for that automation to reach a production state file. The overall design principle: make the blast radius of an automated destroy pipeline provably limited to disposable infrastructure by construction, not by operator discipline alone.
_What the interviewer is probing for:_ Systems-level thinking about destructive-operation safety — layered technical controls plus process, scoped by environment criticality, not a single uniform policy applied everywhere.

## 12. Common Misconceptions

1. **"`terraform destroy` only undoes what the last `apply` did."** It destroys everything currently in state, regardless of when or how each resource entered state — including imported resources that predate Terraform entirely.
2. **"A failed `apply` leaves infrastructure and state in a consistent, matching pair."** State is updated incrementally as resources complete — a partial failure can leave state accurately reflecting a partially-changed real world, which is actually the correct and recoverable outcome, not corruption.
3. **"`-auto-approve` is inherently dangerous and should never be used."** It's safe and standard practice when applying a saved, reviewed plan file in CI; the danger is specifically pairing it with an unsaved, unreviewed plan in unattended automation.
4. **"`prevent_destroy` protects a resource from all forms of removal."** It blocks `destroy`-path removal via Terraform, but doesn't protect against the resource being removed from configuration and having Terraform propose to destroy it as a side effect of a normal `apply` — that's a distinct scenario also covered by `prevent_destroy`, but worth knowing it applies broadly to any Terraform-driven destroy action, not just the `destroy` command specifically.

## 13. 🔑 Key Takeaways

- `terraform apply` executes proposed changes against real infrastructure and updates state as it goes; `terraform destroy` is the special case of applying a plan whose only actions are destroying everything in state.
- Applying a saved plan file ([§25](./Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md)) skips re-planning and confirmation, executing exactly what was reviewed — the safe pattern for automation.
- Partial `apply` failures are recoverable by design: state reflects real progress, and re-running `apply` resumes rather than restarts.
- `lifecycle { prevent_destroy = true }` ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) is a hard, tool-enforced backstop against accidental destruction of critical resources, independent of process discipline.
- Always confirm workspace and backend context before running `destroy` — misdirected destroys against the wrong environment are a leading cause of real incidents.

## 14. Related Concepts & What's Next

[§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md) covers the full `lifecycle` block including `prevent_destroy`, `create_before_destroy`, and `ignore_changes` referenced here. [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md) covers exactly how state is written during and after `apply`. [§69](../Part10/Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md)–[§70](../Part10/Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md) cover workspaces and environment separation, directly relevant to avoiding misdirected destroys. [§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) covers the full CI/CD apply pipeline pattern this section previewed. Next, [§27](./Section-27-Part4-terraform-validate-and-terraform-fmt.md) covers `terraform validate` and `terraform fmt` — the lightweight, purely local checks that should run before any `plan`/`apply` cycle begins.

**Next Section:** [§27](./Section-27-Part4-terraform-validate-and-terraform-fmt.md) — `Section-27-Part4-terraform-validate-and-terraform-fmt.md`
