# Section 99 (Part 14): terraform validate and Plan-Based Testing Strategies

## 1. Definition

**Plain language:** Before you trust a Terraform change enough to run it against real infrastructure, you can catch two very different classes of problems automatically: is the configuration even well-formed HCL that refers to things consistently (`terraform validate`), and, separately, what would actually change if you applied it right now (`terraform plan`)? Neither of these requires you to touch real infrastructure to run, which is exactly what makes them the foundation of testing Terraform in CI.

**Precise definition:** **`terraform validate`** performs a static, offline check of a configuration: it verifies HCL syntax is well-formed, that argument names and types match each resource/provider schema, that internal references (`aws_vpc.main.id`) resolve to something that actually exists in the configuration, and that required arguments are present — all without contacting any provider API or reading real infrastructure state. **Plan-based testing** is the complementary technique of running `terraform plan` (optionally with `-detailed-exitcode`) in an automated pipeline and inspecting its output — either the exit code, the human-readable summary, or the structured `-json`/`show -json` plan ([§30](../Part4/Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md)) — to assert things about what a change _would do_: does it propose to destroy a resource it shouldn't, does it add the expected number of resources, does it touch a forbidden resource type. `-detailed-exitcode` turns `plan`'s otherwise informational exit code into a three-way signal a CI pipeline can branch on: `0` = no changes, `1` = error, `2` = changes present.

> 💡 **Tip:** `terraform validate` cannot catch a huge category of real-world failures: a syntactically perfect configuration that references a nonexistent AMI ID, a CIDR block that collides with an existing subnet, or an IAM policy the target account will reject — because validate never calls the provider API or reads real infrastructure. Only `plan` (which does refresh against real state and, depending on provider, real APIs) and `apply` can surface those. Treat `validate` as a fast pre-filter, not a substitute for plan-based or integration testing.

## 2. Why This Matters

- **Fast, cheap feedback loop.** `terraform validate` runs in milliseconds to low seconds with no network calls beyond what's already cached locally, making it viable as a pre-commit hook ([§104](./Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)) or the very first CI step, long before slower plan/apply stages run.
- **Catches an entire class of PR mistakes before review.** A malformed reference, a typo'd argument name, or a missing required field fails loudly and immediately instead of surfacing as a confusing `plan` error minutes later, or worse, mid-`apply`.
- **Plan output is the actual "diff" reviewers and CI gates should reason about.** Unlike application code, where a diff of source lines tells you most of what changed, a Terraform diff of HCL lines can be misleading — a one-line change to a `for_each` key can implicitly destroy and recreate dozens of resources. `terraform plan` is the only reliable way to see the _real_ blast radius.
- **`-detailed-exitcode` enables branching automation.** A pipeline can programmatically distinguish "nothing to do, safe to skip apply" from "changes proposed, needs human review" from "plan itself failed" — the basis of most GitOps plan/apply gating ([§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)).
- **Structured JSON plan output enables assertion-based testing.** Piping `terraform show -json tfplan` ([§30](../Part4/Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md)) into `jq` or a policy engine ([§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)) lets CI assert specific properties of a change — e.g., "no `aws_db_instance` resource may have `deletion_protection = false`" — as a hard gate, not a manual review step.

## 3. Prerequisites and Dependencies

This section assumes familiarity with `terraform plan` mechanics from [§25](../Part4/Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md) and the exit-code and `-json` output conventions covered in [§30](../Part4/Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md). It also depends on the CLI workflow fundamentals (`init`, `plan`, `apply`) established across Part 4, and specifically builds on [§27](../Part4/Section-27-Part4-terraform-validate-and-terraform-fmt.md)'s coverage of `terraform validate` and `terraform fmt` as standalone commands — this section goes deeper into using `validate` and `plan` together as an automated testing strategy rather than manual CLI habits. [§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md) builds on this section by introducing frameworks (Terratest, native `terraform test`) that go beyond plan inspection into actual apply-and-assert integration testing.

## 4. Architecture / Conceptual Diagram

```text
   STATIC / OFFLINE                    DYNAMIC / PLAN-BASED
   (no provider API calls)             (reads real state, calls provider APIs)

   terraform fmt -check                terraform plan -detailed-exitcode -out=tfplan
        │                                       │
        ▼                                       ▼
   Is HCL canonically                  Exit 0: no changes (safe, no-op)
   formatted?                          Exit 1: error (config/provider/auth failure)
        │                              Exit 2: changes present (needs review)
        ▼                                       │
   terraform validate                           ▼
        │                              terraform show -json tfplan > plan.json
        ▼                                       │
   - HCL syntax valid?                          ▼
   - Argument names/types match          Assertions against plan.json:
     provider schema?                    - resource_changes[].change.actions
   - Internal references resolve?        - no unexpected "delete" actions
   - Required arguments present?         - no forbidden resource types touched
        │                                - count of adds/changes/deletes within
        ▼                                  expected bounds
   Exit 0: valid                                 │
   Exit 1: invalid                               ▼
                                        Feed into policy engine (§101) or
                                        CI gate: block merge/apply if violated
```

- `fmt -check` and `validate` form the fast, zero-cost-of-execution layer — they run before any provider credentials are even needed in some setups, since `validate` needs providers installed (via `init`) but not authenticated against real infrastructure for most providers.
- `plan -detailed-exitcode` is the first stage that requires real credentials and produces a result that depends on the actual state of real infrastructure — it's a fundamentally different kind of test than `validate`, testing "what would happen" rather than "is this well-formed."
- The JSON plan output is the hinge point between plan-based testing done with ad hoc scripting (`jq` assertions) and formal policy-as-code testing ([§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)), which consumes the same structured plan representation.

## 5. Hands-On

### 5.1 `terraform validate` in Isolation

**Purpose:** Confirm a configuration is internally consistent before any plan is attempted.

**Syntax:**

```bash
terraform init -backend=false   # providers/modules only, no remote state needed
terraform validate
terraform validate -json        # machine-readable output for CI parsing
```

**Example usage and expected output:**

```bash
$ terraform validate
Error: Unsupported argument

  on main.tf line 12, in resource "aws_instance" "app":
  12:   instance_typ = "t3.micro"

An argument named "instance_typ" is not expected here. Did you mean "instance_type"?
```

```bash
$ terraform validate -json
{
  "format_version": "1.0",
  "valid": false,
  "error_count": 1,
  "warning_count": 0,
  "diagnostics": [
    {
      "severity": "error",
      "summary": "Unsupported argument",
      "detail": "An argument named \"instance_typ\" is not expected here. Did you mean \"instance_type\"?"
    }
  ]
}
```

**Production usage example:** A GitHub Actions job runs `terraform init -backend=false && terraform validate` as the very first step of every PR pipeline, failing fast on typos before any slower plan step (which requires real cloud credentials) even starts — see [§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) for the full workflow.

**Common errors:** Running `terraform validate` before `terraform init` fails immediately because providers and modules aren't installed yet — `validate` needs the provider schemas to check argument names against, even though it never calls the provider's API.

### 5.2 Plan-Based Testing with `-detailed-exitcode`

**Purpose:** Turn `terraform plan`'s result into a branchable signal for automation, distinguishing "no-op," "changes pending," and "failed."

**Syntax:**

```bash
terraform plan -detailed-exitcode -out=tfplan
echo "Exit code: $?"
```

**Example usage and expected output:**

```bash
$ terraform plan -detailed-exitcode -out=tfplan
No changes. Your infrastructure matches the configuration.
$ echo $?
0

$ terraform plan -detailed-exitcode -out=tfplan
Plan: 1 to add, 0 to change, 0 to destroy.
$ echo $?
2
```

```bash
# In a CI shell step:
terraform plan -detailed-exitcode -out=tfplan
case $? in
  0) echo "No changes — skipping apply, nothing to review." ;;
  1) echo "Plan failed — blocking pipeline." && exit 1 ;;
  2) echo "Changes detected — posting plan for review." ;;
esac
```

**Production usage example:** GitOps pipelines ([§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)) use exactly this pattern to decide whether to post a "no changes" comment on a PR versus a full plan diff requiring reviewer sign-off, avoiding noisy no-op comments on every commit.

**Common errors:** Treating exit code `2` as a failure (some naive CI configurations mark any non-zero exit as a build failure) is the single most common mistake — it turns every legitimate proposed change into a red build, defeating the purpose of `-detailed-exitcode`. The CI step must explicitly branch on `2` as success-with-changes.

### 5.3 Asserting Against the JSON Plan

**Purpose:** Extract structured facts from a plan to enforce rules programmatically, without a full policy engine.

**Syntax:**

```bash
terraform show -json tfplan > plan.json
jq '.resource_changes[] | select(.change.actions[] == "delete")' plan.json
```

**Example usage and expected output:**

```bash
$ jq '.resource_changes[] | select(.change.actions[] == "delete") | .address' plan.json
"aws_db_instance.primary"

$ echo "BLOCKED: plan proposes deleting a database resource" && exit 1
```

**Production usage example:** A "no destructive changes on `main`" guardrail script runs this `jq` filter against every plan targeting the production workspace and fails the pipeline if any `aws_db_instance`, `aws_s3_bucket`, or similarly stateful resource type appears with a `delete` action — a cheap, dependency-free precursor to formal Sentinel/OPA policy checks ([§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)).

**Common errors:** Forgetting that `change.actions` is an array (e.g. `["delete", "create"]` for a replace) rather than a single string — filtering on `.change.actions == "delete"` instead of `.change.actions[] == "delete"` silently matches nothing and gives false confidence that no destructive changes exist.

## 6. Production Usage Notes

- **`validate` should run before `init -backend=true` where possible** (using `-backend=false`) to avoid needing remote state credentials just to catch a syntax typo — many teams run `validate` as a pre-commit hook ([§104](./Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)) precisely because it's this cheap.
- **`plan` is not free and is not side-effect-free with a remote backend.** It refreshes state (contacting real provider APIs to read current resource attributes) and, with most remote backends, acquires a state lock ([§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) for the duration — running `plan` concurrently across many parallel CI jobs against the same workspace will serialize on that lock or fail outright.
- **A saved plan file (`-out=tfplan`) is the only way to guarantee `apply` executes exactly what was reviewed.** Re-running `terraform plan` implicitly before `apply` (the default when no plan file is given) reopens a window where infrastructure could have drifted between review and apply — GitOps pipelines ([§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)) apply the saved plan file specifically to close this gap.

## 7. Security Considerations

- The JSON plan output can contain sensitive values (database passwords passed as resource arguments, for example) unless those arguments are marked `sensitive` ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) — CI logs that dump `terraform show -json` output verbatim risk leaking secrets into build logs, which are often more widely readable than the infrastructure itself.
- `terraform plan` requires live credentials with read (and for accurate diffing, sometimes broader) permissions against real infrastructure — a PR-triggered plan job effectively grants a CI runner processing untrusted PR branches access to production-adjacent read credentials; scoping those credentials to least privilege ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)) matters even for "just a plan."
- Because `plan` calls provider APIs, a malicious or careless configuration change in a PR (e.g., a `data` source pointed at an attacker-controlled endpoint via a crafted variable) can exfiltrate information or trigger side effects during a supposedly "read-only" plan step — validating and reviewing PR-sourced variable inputs before they reach a plan job is a real, if often overlooked, concern.

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Likely Cause                                                                                                                                                       | Resolution Path                                                                                                     |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- |
| `terraform validate` fails with "Could not load plugin"              | `terraform init` was never run, or was run with `-backend=false` but providers weren't installed                                                                   | Run `terraform init` (or `init -backend=false` at minimum) before `validate`                                        |
| CI marks every plan run as "failed" even when changes are legitimate | Pipeline treats any non-zero exit code as failure instead of branching on `-detailed-exitcode`'s 0/1/2 semantics                                                   | Update the CI step to explicitly handle exit code `2` as "changes present," not an error                            |
| `terraform plan` hangs or times out in CI                            | State lock ([§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) held by a concurrent or crashed prior run against the same workspace | Check backend lock status; use `terraform force-unlock` only after confirming no other run is genuinely in progress |
| `jq` assertion against plan JSON silently passes when it shouldn't   | Filtering against `.change.actions` as a scalar instead of iterating the array with `.change.actions[]`                                                            | Correct the `jq` filter to iterate the actions array                                                                |

## 9. Best Practices

- Run `terraform fmt -check` and `terraform validate` as the earliest, fastest CI stage — fail the pipeline before spending time or provider API quota on a `plan` that's guaranteed to be irrelevant because the config won't even parse correctly.
- Always save the plan with `-out` and apply that exact saved plan file, never a fresh implicit plan, in any pipeline where review happens between plan and apply ([§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)).
- Use `-detailed-exitcode` explicitly in any automation branching on "were there changes" rather than parsing human-readable plan text, which is not a stable interface across Terraform versions.

## 10. Common Anti-Patterns / Mistakes

- **Treating `terraform validate` passing as proof the configuration is safe to apply.** Validate never contacts a provider or reads real infrastructure — a config can validate cleanly and still fail catastrophically at `plan` or `apply` time against real state.
- **Parsing human-readable `plan` text output with regex/grep for CI assertions.** The human-readable format is explicitly not a stable contract across Terraform versions; the JSON plan format ([§30](../Part4/Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md)) is the only interface meant for machine consumption.
- **Skipping `plan` review entirely because `validate` passed and the diff "looks small."** A one-line HCL change (e.g., altering a `for_each` expression) can produce an enormous, non-obvious blast radius that only `plan` output reveals — this is precisely why plan-based testing exists as a distinct layer from static validation.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `terraform validate` and `terraform plan`?"_
**Model answer:** `terraform validate` is a static, offline check — it confirms the HCL is syntactically correct, argument names and types match provider schemas, and internal references resolve, all without calling any provider API. `terraform plan` actually contacts providers, refreshes state against real infrastructure, and computes what changes would be made if applied — it can catch problems `validate` cannot, like an invalid AMI ID or a naming collision with existing infrastructure, but it requires real credentials and network access, unlike `validate`.
_What the interviewer is probing for:_ Whether the candidate understands these as two genuinely different classes of check, not "validate is a lightweight version of plan."

**🎯 Intermediate:** _"How would you use `terraform plan` in a CI pipeline to programmatically decide whether changes exist, without parsing plan text?"_
**Model answer:** Run `terraform plan -detailed-exitcode -out=tfplan` and branch on the exit code: `0` means no changes (safe no-op), `1` means the plan itself errored, and `2` means changes are proposed and need review. For anything beyond that binary signal — like asserting specific resource types weren't touched — pipe `terraform show -json tfplan` into `jq` or a policy engine, since the JSON plan format is the stable, machine-readable interface, unlike the human-readable summary text.
_What the interviewer is probing for:_ Practical CI fluency — knowing the specific flag and exit code contract, not just "check if plan says something changed."

**🎯 Senior:** _"A team's pipeline runs `terraform plan` on every PR, but sometimes the plan on `main` after merge shows unexpected changes that weren't in the PR's reviewed plan. What's happening, and how do you fix it?"_
**Model answer:** This is almost always a gap between the plan that was reviewed and the plan that's actually applied. If the pipeline re-runs `terraform plan` implicitly at apply time (instead of applying a saved `-out` plan file from the PR), any drift that occurred between PR review and merge — someone else's apply landing first, or real infrastructure changing outside Terraform — gets silently folded into the "apply" step instead of being caught and re-reviewed. The fix is to always save the plan (`-out=tfplan`) at PR time, pass that exact plan artifact through to the apply stage after merge, and have `apply` fail loudly (rather than silently re-plan) if the saved plan is stale relative to current state.
_What the interviewer is probing for:_ Understanding that plan/apply consistency is an artifact-passing problem, not just a two-command sequence — this is core to correct GitOps design ([§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)).

**🎯 Architect:** _"Your organization wants a hard gate that no PR can ever merge if its plan proposes deleting an RDS instance, without relying on human reviewers remembering to check. How would you design that, and what are its limits?"_
**Model answer:** Generate the plan as JSON (`terraform show -json`) in the PR pipeline, and run an automated assertion — either a simple `jq`/script-based check or, more robustly, a Sentinel or OPA policy ([§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)) — against `resource_changes[]`, blocking the pipeline (and thus the merge, if branch protection requires the check) whenever any `aws_db_instance` resource change includes a `delete` action. The limits: this only catches _plan-visible_ deletions — it won't catch a resource silently removed from state via `terraform state rm` outside the normal flow, won't catch destroys that happen via `-target` in an ad hoc manual run bypassing CI entirely, and won't catch replace-in-place operations where a destroy is masked as part of a create*before_destroy/replace cycle unless the policy specifically checks for "delete" appearing anywhere in the actions array, including replace operations. A complete design pairs this CI gate with restricting who/what can run `terraform apply` outside the pipeline at all ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)), since a policy check only has teeth if it's the only path to production.
\_What the interviewer is probing for:* Whether the candidate sees plan-based gates as one layer of defense that depends on process controls (restricted apply paths) to actually be enforceable, not a complete solution on its own.

## 12. Common Misconceptions

1. **"If `terraform validate` passes, the plan will succeed."** Validate is purely static; a valid configuration can still fail at plan time due to real infrastructure state, provider-side constraints, or authentication issues validate never checks.
2. **"`terraform plan` is read-only and therefore always completely safe to run."** Plan calls provider APIs (which can have side effects for certain data sources or exotic providers) and, against a remote backend, acquires a state lock — it isn't a no-op against the outside world, even though it never modifies managed infrastructure.
3. **"Exit code 2 from `-detailed-exitcode` means something went wrong."** It specifically means "changes are proposed" — a normal, often-desired outcome — while exit code `1` is the actual error signal; conflating the two is a common CI misconfiguration.
4. **"Plan output is a stable format safe to `grep`."** Only the `-json` output is a documented, stable machine-readable contract; the human-readable plan text can and does change format across Terraform versions.

## 13. 🔑 Key Takeaways

- `terraform validate` is a fast, offline, static check — no provider API calls, no real infrastructure awareness — and should be the earliest CI stage.
- `terraform plan -detailed-exitcode` turns plan results into a three-way branchable signal (0/1/2) that automation can act on without parsing text output.
- The JSON plan format (via `terraform show -json`) is the only stable interface for programmatic assertions about proposed changes; human-readable plan text is not.
- Saving and applying an exact plan file (`-out`) closes the gap between "what was reviewed" and "what gets applied," which is central to correct GitOps pipeline design.
- Plan-based testing catches "what would this change do" — it is complementary to, not a replacement for, apply-and-assert integration testing ([§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)).

## 14. Related Concepts & What's Next

[§27](../Part4/Section-27-Part4-terraform-validate-and-terraform-fmt.md) introduced `terraform validate` and `terraform fmt` as standalone CLI commands; this section built on that into automated testing strategy. [§30](../Part4/Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md) covers the `-json` output formats this section's JSON-plan techniques depend on. [§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md) goes further than plan inspection into frameworks that actually apply and destroy real infrastructure to assert on live behavior. [§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) formalizes the `jq`-style plan assertions shown here into real policy-as-code engines. [§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) shows how saved plan files flow through a full PR-based GitOps pipeline.

**Next Section:** [§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md) — `Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md`
