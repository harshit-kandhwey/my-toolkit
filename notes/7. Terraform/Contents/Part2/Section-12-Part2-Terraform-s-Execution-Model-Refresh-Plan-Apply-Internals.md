# Section 12 (Part 2): Terraform's Execution Model: Refresh, Plan, Apply Internals

## 1. Definition

**Plain language:** "Terraform plan" and "terraform apply" sound like single actions, but each one is actually a multi-step internal process: read what's really out there right now, compare it against what your configuration says should exist, work out a set of changes, and (for apply) actually make those changes by walking the dependency graph. Understanding these steps individually — rather than treating `plan`/`apply` as opaque black boxes — is what lets you correctly predict and debug what Terraform will do.

**Precise definition:** Terraform's core execution model runs three conceptually distinct phases, though not always as three separate CLI invocations. **Refresh** reconciles Terraform's in-memory (and ultimately on-disk) state with the real-world status of every managed resource, by calling each resource's provider `ReadResource` RPC and updating state to reflect actual observed values — as of Terraform 0.15+, refresh is folded automatically into `plan` and `apply` rather than requiring a separate `terraform refresh` invocation ([§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) covers the standalone command and its remaining use cases). **Plan** builds the dependency graph ([§11](./Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)), walks it to compute a **diff** for every resource — comparing desired configuration against refreshed state via each provider's `PlanResourceChange` RPC, producing a set of proposed actions (create, update in-place, destroy, replace, or no-op) — and presents this diff to the operator without touching real infrastructure. **Apply** re-walks the same graph (re-validating that state hasn't drifted since the plan was computed, unless applying a saved plan file), and for each graph node in dependency order, calls the provider's `ApplyResourceChange` RPC to actually perform the create/update/destroy, persisting each result into state incrementally as it completes — not in one batch at the end.

> 💡 **Tip:** Apply does not simply "replay" the plan blindly. Unless you run `terraform apply <saved-plan-file>` against a plan produced with `terraform plan -out=<file>`, a bare `terraform apply` **recomputes the plan from scratch** immediately before executing it — meaning state or real infrastructure that changed between when you last looked at a plan and when you hit "yes" can silently produce a _different_ apply than what you reviewed. This is precisely why CI/CD pipelines that separate a review step from an apply step ([§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)) always pass an explicit saved plan file between the two steps, never re-running a fresh `plan` at apply time.

## 2. Why This Matters

- **Refresh being automatic (not a separate manual step) is one of the most consequential behavior changes in Terraform's history (0.15+) — and misunderstanding it causes real incidents.** A `plan` today reflects live infrastructure state at the moment you ran it, not stale state from the last apply; assuming otherwise (e.g., "state hasn't been touched since yesterday, so plan output is safe to trust today") is a common, avoidable mistake.
- **The diff computation in `plan` happens entirely client-side plus per-resource provider RPC calls — no infrastructure is ever mutated during `plan`.** This is what makes `plan` safe to run liberally, including in CI on every pull request, without fear of side effects (barring provider bugs).
- **Apply persists state incrementally, per-resource, not atomically at the end of the whole run.** This is why a failed apply midway through a large change leaves a valid, up-to-date state file for everything that _did_ complete — understanding this correctly shapes recovery behavior after a partial failure instead of assuming the whole apply is "rolled back" (Terraform has no automatic rollback).
- **A saved plan file (`-out`) is the only way to guarantee what gets applied is exactly what was reviewed.** Teams that skip this in CI/CD pipelines are exposed to a real "plan-apply drift" risk where the applied change differs from the reviewed change.

## 3. Prerequisites and Dependencies

Builds directly on [§11](./Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)'s dependency graph — this section explains what actually happens as Terraform walks that graph during each phase. [§8](./Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md)'s provider RPC model underlies every `ReadResource`/`PlanResourceChange`/`ApplyResourceChange` call described here. [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md) (What Terraform State Is) is referenced throughout for how state is read and written at each phase, though full state mechanics are covered there, not here. [§25](../Part4/Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md) and [§26](../Part4/Section-26-Part4-terraform-apply-and-terraform-destroy.md) (the `terraform plan` and `terraform apply` CLI commands) are the command-level companions to this section's internals-level treatment. [§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) (Handling State Drift and `terraform refresh`) covers the standalone refresh command and drift-handling strategies this section only introduces.

## 4. Architecture / Conceptual Diagram

```text
┌───────────────────────────────────────────────────────────────────────┐
│                          terraform plan                               │
│                                                                       │
│  1. REFRESH (implicit, unless -refresh=false)                         │
│     For every resource in state:                                      │
│       provider.ReadResource() ──► real API GET call                   │
│       state updated in-memory with actual observed values             │
│                                                                       │
│  2. GRAPH CONSTRUCTION                                                │
│     Parse config, build DAG (§11), topological sort                   │
│                                                                       │
│  3. DIFF / PLAN COMPUTATION                                           │
│     For every graph node:                                             │
│       provider.PlanResourceChange(desired_config, refreshed_state)    │
│       ──► proposed action: no-op | create | update | destroy | replace│
│                                                                       │
│  4. PRESENT PLAN                                                      │
│     "Plan: X to add, Y to change, Z to destroy."                      │
│     (nothing in real infrastructure has been touched)                 │
│     optionally: -out=tfplan  (binary saved plan file)                 │
└──────────────────────────┬────────────────────────────────────────────┘
                           │
                           ▼  terraform apply [tfplan]
┌───────────────────────────────────────────────────────────────────────┐
│                          terraform apply                              │
│                                                                       │
│  0. If given a saved plan file: skip re-planning, use it as-is.       │
│     If given no plan file: re-run steps 1-3 above FRESH, right now.   │
│                                                                       │
│  5. GRAPH WALK / EXECUTION                                            │
│     Worker pool executes unblocked nodes (up to -parallelism):        │
│       provider.ApplyResourceChange() ──► real API POST/PUT/DELETE     │
│       ┌────────────┐                                                  │
│       │ per node:   │  on success: write result to state IMMEDIATELY  │
│       │ apply →     │  on failure: mark node failed, dependents       │
│       │ persist state│  in that branch are skipped, OTHER branches    │
│       └────────────┘  continue independently                          │
│                                                                       │
│  6. FINAL STATE PERSISTED (to backend, §48-§49) + summary printed     │
└───────────────────────────────────────────────────────────────────────┘
```

## 5. Hands-On

### 5.1 Observing Automatic Refresh Behavior

**Purpose:** See refresh happening implicitly as part of `plan`, and control it explicitly when needed.

**Syntax:**

```bash
terraform plan                  # refresh happens automatically
terraform plan -refresh=false   # skip refresh, plan against last-known state only
terraform plan -refresh-only    # ONLY refresh + show drift, propose no config changes
```

**Example usage and expected output:**

```bash
$ terraform plan -refresh-only
aws_instance.web: Refreshing state... [id=i-0abc123]

Note: Objects have changed outside of Terraform

  # aws_instance.web has changed
  ~ resource "aws_instance" "web" {
      ~ instance_type = "t3.micro" -> "t3.small"
        id            = "i-0abc123"
    }

This is a refresh-only plan, so Terraform will not take any actions
to undo these changes.
```

**Production usage example:** `-refresh-only` plans, often run on a schedule in CI, are a standard way to detect infrastructure drift (manual console changes, out-of-band automation) without risking an accidental corrective apply — teams review the drift report and decide manually whether to reconcile via `apply` (accepting the drift into config) or revert it (re-applying the declared configuration).

**Common errors:** Running `-refresh=false` on a `plan` and being confused when the plan doesn't reflect a manual change made in the cloud console minutes earlier — `-refresh=false` deliberately trusts the last-known state file over live reality, trading accuracy for speed (useful on very large configurations where refresh's read calls dominate plan time).

### 5.2 Saved Plan Files: Guaranteeing Plan-Apply Consistency

**Purpose:** Ensure the exact reviewed plan is what actually gets applied, with no re-computation gap.

**Syntax:**

```bash
terraform plan -out=<plan_file>
terraform apply <plan_file>
```

**Example usage and expected output:**

```bash
$ terraform plan -out=tfplan
Plan: 2 to add, 1 to change, 0 to destroy.
Saved the plan to: tfplan

$ terraform apply tfplan
aws_instance.web: Modifying... [id=i-0abc123]
aws_instance.web: Modifications complete after 12s
aws_s3_bucket.logs: Creating...
aws_s3_bucket.logs: Creation complete after 1s
Apply complete! Resources: 2 added, 1 changed, 0 destroyed.
```

**Production usage example:** This is the standard CI/CD pattern ([§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)): a pull request triggers `terraform plan -out=tfplan`, which is posted as a PR comment for human review; on merge/approval, a separate pipeline stage runs `terraform apply tfplan` against the _exact same_ binary plan file — never a fresh `plan` — so what was reviewed is provably what gets applied.

**Common errors:** `Error: Saved plan is stale` fires if real infrastructure or state changed between saving the plan and applying it (e.g., someone else applied a different change in the interim) — Terraform detects this via a state-serial/fingerprint check and refuses to apply a plan computed against now-outdated state, forcing a fresh `plan` rather than silently applying against a mismatched baseline.

### 5.3 Observing Incremental State Persistence During a Partial Apply Failure

**Purpose:** Understand exactly what state looks like after an apply fails partway through, since Terraform has no automatic rollback.

**Syntax:**

```bash
terraform apply
# (simulate/observe a mid-apply failure)
terraform state list
terraform plan   # re-plan to see what's actually still needed
```

**Example usage and expected output:**

```bash
$ terraform apply
aws_vpc.main: Creating...
aws_vpc.main: Creation complete after 2s [id=vpc-0a1b2c3d]
aws_subnet.a: Creating...
aws_subnet.a: Creation complete after 1s [id=subnet-0e5f6g7h]
aws_instance.web: Creating...
Error: Error launching source instance: InsufficientInstanceCapacity

Apply failed after 3 resources.

$ terraform state list
aws_vpc.main
aws_subnet.a
```

**Production usage example:** Understanding that `aws_vpc.main` and `aws_subnet.a` are now genuinely, correctly tracked in state (not rolled back) after this partial failure is what tells an operator the safe next step is simply re-running `terraform apply` (which will skip the already-created resources and retry only `aws_instance.web`), not manually cleaning up "orphaned" resources that were never orphaned to begin with.

**Common errors:** Assuming a failed apply means "nothing happened" and manually re-creating resources via the console or a separate script — this creates duplicate/conflicting infrastructure that then conflicts with what Terraform already correctly has in state; the correct response to a partial failure is almost always simply re-running `apply`.

## 6. Production Usage Notes

- **`plan` performance is often dominated by the refresh phase's real API read calls on large configurations**, not by diff computation itself — thousands of resources each requiring a `ReadResource` RPC round trip to a cloud API adds up; `-refresh=false` and state-splitting ([§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) are the two standard mitigations.
- **Apply is not transactional across the whole run — each resource's success/failure is independent, scoped to its own graph branch.** A failure in one dependency chain doesn't halt unrelated, already-unblocked branches elsewhere in the graph; they continue executing (and their results get persisted) even while a sibling branch has failed, so a single apply's final summary can show a mix of successes and one specific failure.
- **`terraform apply -auto-approve`**, common in CI, skips the interactive confirmation prompt but does **not** skip refresh, graph construction, or diff computation — it only removes the "do you want to perform these actions?" pause; this distinction matters when explaining CI apply behavior to teams new to automation.

## 7. Security Considerations

- Refresh's `ReadResource` calls, and plan/apply's `PlanResourceChange`/`ApplyResourceChange` calls, all execute with whatever credentials the running provider process has ([§8](./Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md), [§14](./Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md)) — a `plan` run in CI with read-only credentials will correctly refresh and diff but fail cleanly at `apply` time if apply-level permissions are absent, which is a legitimate and common least-privilege pattern ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)): grant plan-time identities read-only access, apply-time identities write access.
- Saved plan files (`-out`) can contain sensitive values in plaintext within the binary file (including values marked `sensitive` in configuration, depending on Terraform version and context) — treat saved plan files with the same access controls as state files, never commit them to version control, and ensure CI artifact storage for plan files is appropriately access-restricted ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md), [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) cover sensitive value handling in full).

## 8. Common Troubleshooting Scenarios

| Symptom                                                             | Likely Cause                                                                       | Resolution Path                                                                                                                                                                           |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Error: Saved plan is stale`                                        | Real infrastructure or state changed between `plan -out` and `apply`               | Re-run `terraform plan -out=` fresh and re-review before applying                                                                                                                         |
| Apply fails partway; unsure what actually exists now                | Normal partial-apply behavior — completed resources are already persisted to state | `terraform state list` to see what's tracked, then simply re-run `apply`                                                                                                                  |
| `plan` takes far longer than expected on an unchanged configuration | Refresh phase reading every resource via real API calls dominates runtime          | Consider `-refresh=false` for a quick check, or state splitting ([§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) for a lasting fix |
| Drift detected but team unsure whether to accept or revert it       | Manual out-of-band change made outside Terraform                                   | Run `-refresh-only` plan to review drift explicitly before deciding to `apply` (accept) or fix the resource externally (revert)                                                           |

## 9. Best Practices

- Always use `-out` to save plans in any pipeline that separates review from apply, and apply that exact saved file — never re-plan between review and apply.
- Run scheduled `-refresh-only` plans against production state to catch drift proactively rather than discovering it during the next unrelated change's `plan`.
- Treat a partial apply failure as an expected, recoverable state, not an emergency requiring manual state surgery — re-running `apply` is almost always the correct first response.
- Grant plan-time and apply-time identities different permission levels (read-only vs. write) where CI workflow structure allows it, as a genuine least-privilege control enabled directly by this execution model.

## 10. Common Anti-Patterns / Mistakes

- **Re-running `terraform plan` immediately before `apply` in CI "just to double check," discarding the originally reviewed saved plan.** Defeats the entire purpose of plan-apply consistency and reintroduces the exact drift risk saved plan files exist to eliminate.
- **Manually "fixing" resources after a partial apply failure instead of simply re-running `apply`.** Almost always creates more inconsistency than it resolves, since Terraform's own state already accurately reflects what completed.
- **Disabling refresh (`-refresh=false`) as a default habit rather than a deliberate, occasional performance trade-off.** Silently trusts a potentially stale state file over live infrastructure reality, risking a plan (and subsequent apply) computed against inaccurate assumptions.
- **Assuming `apply` has automatic rollback on failure.** Terraform has no transaction/rollback semantics across a whole apply — every completed resource stays applied even if a later resource in the same run fails.

## 11. Interview Questions

**🎯 Beginner:** _"What are the three phases inside a `terraform apply` run, conceptually?"_
**Model answer:** Refresh (checking real infrastructure's current state against what Terraform's state file records), plan/diff (comparing refreshed state against desired configuration to compute proposed changes), and apply/execution (actually performing creates, updates, and destroys by walking the dependency graph and calling each provider's API). As of modern Terraform versions, refresh happens automatically as part of both `plan` and `apply` rather than as a separate manual step.
_What the interviewer is probing for:_ Basic understanding that "apply" isn't one atomic action but a sequence of distinct internal steps.

**🎯 Intermediate:** _"Why does HashiCorp recommend using `terraform plan -out=tfplan` followed by `terraform apply tfplan` in automated pipelines, instead of just running `terraform apply` directly?"_
**Model answer:** A bare `terraform apply` (with no saved plan file) recomputes the plan from scratch immediately before executing it. If real infrastructure or state changed between when a human reviewed a plan's output and when the pipeline actually applies, a fresh re-plan at apply time could produce a different set of changes than what was reviewed and approved — a plan-apply consistency gap. Saving the plan to a binary file with `-out` and then applying that exact file guarantees the applied changes are precisely what was reviewed, with no re-computation window for drift to sneak in.
_What the interviewer is probing for:_ Understanding of a specific, common CI/CD correctness requirement, not just command syntax.

**🎯 Senior:** _"An `apply` on a large configuration fails on resource 40 of 100 due to a transient cloud API error. What is the actual state of the system afterward, and what's the correct recovery procedure?"_
**Model answer:** Every resource that successfully completed its `ApplyResourceChange` call before the failure — potentially most of the other 99, since unrelated graph branches continue independently of the one that failed — is already correctly persisted to state; nothing is rolled back, because Terraform has no cross-resource transaction semantics. The failed resource and anything downstream of it in its specific dependency branch are left unapplied. The correct recovery is simply re-running `terraform apply`: it recomputes the graph, sees the already-completed resources need no action, and retries only the failed resource and its blocked dependents. Manual intervention (state surgery, manual resource creation) is not needed and is actively risky, since it can desync state from reality in ways a simple retry would not.
_What the interviewer is probing for:_ Correct, confident understanding of Terraform's non-transactional, incrementally-persisted apply model — a common source of unnecessary panic in real incidents if misunderstood.

**🎯 Architect:** _"Design the plan/apply stage split for a CI/CD pipeline serving dozens of teams, addressing both plan-apply consistency and least-privilege credential scoping."_
**Model answer:** The pipeline should have a distinct plan stage, triggered on every pull request, using a read-only (or plan-scoped) cloud identity — since `plan`'s refresh and diff computation only require read access to real infrastructure, never write access — producing a saved plan file (`-out`) posted for human review (e.g., as a PR comment or Terraform Cloud run). A separate apply stage, triggered only on merge/approval, consumes that exact saved plan file (never re-planning) using a distinct, more privileged apply-scoped identity with write access, satisfying least privilege by ensuring the broader set of engineers who can trigger/review plans never directly hold apply-capable credentials. Plan files should be treated as sensitive artifacts (encrypted at rest, access-controlled, short retention) given they can contain resource attribute values. This design directly leverages the phase separation covered in this section — refresh/plan being read-only and side-effect-free is what makes the read/write credential split possible at all.
_What the interviewer is probing for:_ Ability to translate execution-model internals into a concrete, secure, real-world pipeline design — connecting mechanism to architecture.

## 12. Common Misconceptions

1. **"`terraform refresh` is a required manual step before every plan."** It was in older Terraform versions; modern Terraform folds refresh automatically into both `plan` and `apply` — the standalone `terraform refresh` command still exists but is rarely needed directly ([§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md)).
2. **"`plan` can modify infrastructure if something unexpected happens."** `plan` (including its refresh phase) only performs read operations against provider APIs; it is deliberately side-effect-free by design — only `apply` performs writes.
3. **"A failed apply rolls back everything that already succeeded in that run."** There is no rollback; completed resources remain applied and correctly tracked in state, and re-running `apply` is the standard recovery path.
4. **"Applying a saved plan file re-validates and re-plans against current state before executing."** It deliberately does not (beyond a staleness/fingerprint check) — that's the entire point of saved plan files: guaranteeing exactly what was reviewed is what executes, not a fresh recomputation.

## 13. 🔑 Key Takeaways

- Refresh, plan, and apply are three distinct phases involving real provider RPC calls (`ReadResource`, `PlanResourceChange`, `ApplyResourceChange`); refresh is automatic in modern Terraform, not a separate manual command.
- `plan` (including refresh) is entirely read-only and side-effect-free against real infrastructure; only `apply` performs writes.
- Apply persists each resource's result to state incrementally as it completes, not atomically at the end — there is no automatic rollback on partial failure.
- Saved plan files (`-out` + `apply <file>`) are the only mechanism guaranteeing plan-apply consistency; a bare `apply` re-plans fresh and can diverge from a previously reviewed plan.
- Recovery from a partial apply failure is almost always a simple re-run of `apply`, not manual state surgery.

## 14. Related Concepts & What's Next

[§11](./Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md) covered the dependency graph this section's execution phases actually walk. [§8](./Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md) covered the RPC mechanics underlying every `ReadResource`/`PlanResourceChange`/`ApplyResourceChange` call described here. [§25](../Part4/Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md) and [§26](../Part4/Section-26-Part4-terraform-apply-and-terraform-destroy.md) cover the `terraform plan` and `terraform apply` commands themselves at the CLI-usage level. [§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) returns to drift handling and the standalone `terraform refresh` command in full depth. [§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) applies this section's plan-apply consistency discussion directly to a full GitOps pipeline design. Part 3 ([§15](../Part3/Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md) onward) shifts from execution internals to HCL language mechanics — the syntax that produces the configuration this execution model consumes.

**Next Section:** [§13](./Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md) — `Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md`
