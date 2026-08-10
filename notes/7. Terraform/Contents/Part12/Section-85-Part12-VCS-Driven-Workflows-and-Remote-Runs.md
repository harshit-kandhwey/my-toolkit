# Section 85 (Part 12): VCS-Driven Workflows and Remote Runs

## 1. Definition

**Plain language:** A VCS-driven Terraform Cloud workspace watches a Git repository the way a CI pipeline does: when someone opens a pull request that touches the workspace's configuration, TFC automatically runs a `plan` and posts the result as a PR check; when the PR merges to the configured branch, TFC automatically runs the corresponding `apply` — all without anyone manually triggering `terraform plan` or `terraform apply` from a laptop or CI script.

**Precise definition:** A **VCS-connected workspace** links a Terraform Cloud workspace to a specific repository, branch, and working directory in a supported version control system (GitHub, GitLab, Bitbucket, Azure DevOps, or a generic webhook-based connection). TFC registers a webhook on the repository; on a push or pull-request event matching the workspace's configured branch and file-path filters, TFC automatically queues a **speculative plan** (on a PR, for review, never applied) or a **plan-and-apply run** (on a push/merge to the tracked branch, subject to the workspace's apply method — auto-apply or manual confirmation). This is one of three run "sources" TFC supports — the others being **CLI-driven remote runs** (`terraform plan`/`apply` executed locally but run remotely via the `cloud` block, as in [§84](./Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md)) and **API-driven runs** (triggered by direct API calls, which underlies CI-integrated and run-trigger workflows, [§88](./Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md)).

> 💡 **Tip:** A pull-request plan in a VCS-driven workspace is a **speculative plan** — it computes and displays the diff for review but can never be applied; there's no "apply" button attached to it. Only a run created by a push to the tracked branch (or a manually queued run) can actually apply. This distinction matters when explaining to a team why they can't click "apply" on the plan they see in a PR — that's by design, not a bug.

## 2. Why This Matters

- **Pull requests become the change-approval mechanism for infrastructure**, not a side channel — the plan diff appears directly on the PR, so reviewers see exactly what will change before approving, closing the loop that [§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)'s GitOps pattern formalizes further.
- **No separate CI pipeline is required just to run Terraform.** Where a CLI-only setup needs a GitHub Actions/GitLab CI job wired up to authenticate, run `plan`, and post a comment ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)), VCS-driven TFC workspaces do this natively via the webhook integration.
- **Branch-based promotion becomes straightforward.** Different workspaces can track different branches (or the same branch with different working directories) to implement environment promotion ([§74](../Part10/Section-74-Part10-Environment-Promotion-Patterns-dev-staging-prod.md)) without hand-rolled pipeline logic.
- **Speculative plans catch problems before merge**, not after — a broken plan on a PR is visible to reviewers immediately, rather than discovered when someone later runs `apply` against merged code.
- **Consistent execution environment for every run.** Every plan, whether from a PR or a merge, runs in the same TFC execution environment with the same Terraform version — removing "the CI runner had a different provider cache" class of bugs.

## 3. Prerequisites and Dependencies

Builds directly on the organization/workspace/run model from [§84](./Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md). Assumes familiarity with pull-request-based Git workflows (see the Git knowledge base, `../../../2. GIT`) and with the CLI plan/apply cycle ([§25](../Part4/Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md), [§26](../Part4/Section-26-Part4-terraform-apply-and-terraform-destroy.md)). [§88](./Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md) extends this section by covering run triggers that chain workspaces together, and [§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) covers the broader GitOps pattern this section is a specific implementation of.

## 4. Architecture / Conceptual Diagram

```text
   Developer                 GitHub/GitLab/etc.              Terraform Cloud

   git push (PR branch) ───► webhook fires ───────────────► speculative PLAN queued
                                                                       │
                                                                       ▼
                                                             plan output posted as
                                                             a PR status check / comment
                                                             (cannot be applied)

   PR reviewed & merged  ───► webhook fires ───────────────► PLAN + APPLY run queued
   to tracked branch (main)                                            │
                                                                       ▼
                                                             plan computed against
                                                             current state
                                                                       │
                                                    ┌──────────────────┴───────────────────┐
                                                    ▼                                      ▼
                                          auto-apply enabled                    manual apply required
                                          → apply runs immediately              → run pauses, waits for
                                            after successful plan                 confirmation in UI/API
```

- The webhook is registered by TFC on the VCS provider when the workspace is connected — no separate CI YAML file defines this trigger logic.
- Working-directory and branch filters on the workspace determine which pushes actually queue a run, letting a monorepo host multiple workspaces each watching a different subdirectory.
- The apply step's gating (auto vs. manual) is a workspace-level setting, independent of the VCS trigger itself.

## 5. Hands-On

### 5.1 Connecting a Workspace to a VCS Repository

**Purpose:** Show the configuration shape of a VCS-backed workspace (conceptually — this is typically done via UI/API, but the resulting behavior is what matters here).

**Syntax (Terraform Cloud's own `tfe` provider, managing TFC itself as code):**

```hcl
resource "tfe_workspace" "app_api_prod" {
  name              = "app-api-prod"
  organization      = "acme-corp"
  working_directory = "environments/prod"
  vcs_repo {
    identifier     = "acme-corp/app-api-infra"
    branch         = "main"
    oauth_token_id = var.github_oauth_token_id
  }
  auto_apply = false
}
```

**Example usage and expected output:**

```bash
$ terraform apply   # applying the tfe_workspace resource itself, against TFC's own API
tfe_workspace.app_api_prod: Creating...
tfe_workspace.app_api_prod: Creation complete after 2s [id=ws-8pQd3RtY9kLmNx2A]

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** Platform teams manage the TFC organization itself (workspaces, teams, VCS connections) as Terraform configuration using the `tfe` provider — a "Terraform managing Terraform Cloud" pattern that keeps workspace definitions reviewable and version-controlled rather than click-configured in the UI.

**Common errors:** Forgetting to scope `working_directory` in a monorepo means TFC queues a plan for every push to the branch regardless of which subdirectory changed, producing no-op plans (or worse, unrelated ones) on unrelated commits.

### 5.2 Reading a Speculative Plan on a Pull Request

**Purpose:** Demonstrate what a reviewer sees when a PR triggers a speculative plan, and why it differs from a normal `terraform plan` run.

**Example usage and expected output:**

```text
GitHub PR #142 — "Add read-replica to app database"

✔ terraform-cloud/app-api-prod — Plan: 1 to add, 1 to change, 0 to destroy
  View plan in Terraform Cloud →

Plan output (in TFC UI):
  # aws_db_instance.replica will be created
  # aws_db_instance.primary will be updated in-place
    ~ backup_retention_period = 7 -> 14

Plan: 1 to add, 1 to change, 0 to destroy.

  [ Apply ]  <- disabled/absent; this is a speculative plan tied to a PR, not a merge
```

**Production usage example:** A database change gets flagged in review because the speculative plan shows an unexpected in-place modification to the primary instance alongside the intended new replica — caught before merge instead of surfacing as a surprise diff after the fact.

**Common errors:** A reviewer trying to "just apply from here" on a PR-triggered speculative plan finds no apply action available — this is expected; only a run against the tracked branch (post-merge) can apply.

## 6. Production Usage Notes

- **Auto-apply is a deliberate, workspace-level risk decision.** Enabling it means every merge to the tracked branch applies without a human confirmation step — appropriate for well-tested, low-risk workspaces (e.g., ephemeral dev environments) but generally avoided for production workspaces, where manual apply confirmation is the norm.
- **Branch and path filters keep monorepos manageable.** A single repository can back many workspaces, each with its own `working_directory` and branch filter, so a change to `modules/networking` doesn't spuriously trigger a run in a workspace scoped to `environments/staging/app`.
- **VCS-driven runs and CLI-driven runs can coexist on the same workspace**, but doing so regularly makes the run history harder to reason about — most teams pick one primary trigger source per workspace and treat the other as an exception path (e.g., a manual `terraform plan` for debugging).

## 7. Security Considerations

- The OAuth token or VCS App connection TFC uses to read the repository and register webhooks is itself a sensitive credential at the organization level — scoping it to only the repositories that genuinely need TFC integration (rather than an org-wide token) limits blast radius if TFC's connection is ever compromised.
- Because a merge to the tracked branch can trigger an apply against real infrastructure, branch protection rules on that branch (required reviews, status checks) become part of the infrastructure change-control process, not just a code-quality nicety — merging without review effectively means applying without review.
- Speculative plans on PRs from forks (in open-source-style repos) may need restricting, since a PR plan can reveal information about the target infrastructure (resource names, existing values) to anyone who can open a PR, depending on repository visibility settings.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                      | Likely Cause                                                                                                               | Resolution Path                                                                                                                         |
| ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| PR shows no Terraform Cloud check at all                                     | Webhook not registered, or the changed files fall outside the workspace's working-directory/path filter                    | Verify VCS connection status in TFC; check working-directory and trigger-path settings against the changed files                        |
| Merge to `main` doesn't trigger an apply                                     | Workspace's branch filter doesn't match `main`, or auto-apply is off and the run is simply waiting for manual confirmation | Check the workspace's tracked branch setting; check the run queue for a run awaiting confirmation rather than assuming nothing happened |
| Speculative plan on a PR shows unexpected changes unrelated to the PR's diff | The tracked branch has diverged from what the PR is based on (state or config drift since the PR was opened)               | Rebase/update the PR branch; re-trigger the plan to get a diff against current `main`                                                   |
| Apply on merge fails with a stale plan error                                 | Another run applied to the same workspace between plan and apply (rare race, or a manually queued run in between)          | Re-run plan against current state before applying; treat this as expected concurrency protection, not a bug                             |

## 9. Best Practices

- Require passing status checks (including the TFC speculative plan) before allowing a PR to merge, so a broken or unreviewed plan can't reach the tracked branch.
- Reserve auto-apply for genuinely low-risk workspaces (throwaway/dev); require manual apply confirmation for anything touching shared or production infrastructure.
- Scope `working_directory` and trigger patterns tightly in monorepos so each workspace only reacts to changes that actually affect it.

## 10. Common Anti-Patterns / Mistakes

- **Enabling auto-apply broadly "to save clicks."** This collapses the plan-review safety net ([§25](../Part4/Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md)'s core value) into a single merge action with no final human checkpoint before real infrastructure changes.
- **Connecting one workspace to an entire monorepo with no path filtering.** Every unrelated commit anywhere in the repo queues a no-op plan, drowning the run history in noise and making genuine changes harder to spot.
- **Relying on VCS-driven runs while also routinely running `terraform apply` locally against the same workspace.** This produces a confusing, interleaved run history and defeats the purpose of a single source of truth for how changes reach the workspace.

## 11. Interview Questions

**🎯 Beginner:** _"What happens in a VCS-connected Terraform Cloud workspace when someone opens a pull request?"_
**Model answer:** TFC automatically queues a speculative plan showing what would change, and posts the result as a status check/comment on the PR — reviewers see the diff before merging, but this plan cannot itself be applied.
_What the interviewer is probing for:_ Basic understanding of the PR-triggered speculative plan behavior.

**🎯 Intermediate:** _"What's the difference between a speculative plan and a plan that can be applied?"_
**Model answer:** A speculative plan is triggered by events like a pull request and exists purely for review — it computes the diff against current state but has no associated apply action, so it can never modify infrastructure. A plan eligible for apply is created by a run against the workspace's tracked branch (via merge/push) or a manually queued run, and — depending on the workspace's auto-apply setting — either applies automatically after a successful plan or waits for a human to confirm.
_What the interviewer is probing for:_ Whether the candidate understands this isn't just "two plan types" cosmetically, but a genuine safety boundary in the run pipeline.

**🎯 Senior:** _"You have a monorepo with a dozen Terraform root modules, one per microservice, all connected to a single Terraform Cloud organization. How do you structure the VCS connections so a change to one service doesn't trigger runs in the other eleven?"_
**Model answer:** Create one TFC workspace per root module/service, each pointed at the same repository but with its `working_directory` set to that service's specific subdirectory, and (where the VCS integration supports it) trigger paths/patterns restricting which file changes queue a run for that workspace. This way a push touching only `services/billing/` only triggers the `billing` workspace's run, not the other eleven. It also means each workspace's run history stays meaningful and its state stays isolated per service, consistent with keeping workspace boundaries aligned to deployable units ([§84](./Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md)).
_What the interviewer is probing for:_ Practical monorepo-to-multi-workspace mapping skill, since this is an extremely common real-world layout question.

**🎯 Architect:** _"A team wants every merge to `main` to auto-apply to production with zero manual steps, for 'true continuous deployment' of infrastructure. What's your position?"_
**Model answer:** It's technically supported (auto-apply) but the trade-off needs to be explicit: infrastructure changes, unlike most application deploys, are frequently harder to roll back cleanly (a destroyed database, a replaced load balancer) and the human review that would otherwise happen at apply-confirmation time gets pushed entirely onto the PR review — which is fine only if PR review is genuinely rigorous, branch protection is enforced, and the workspace's blast radius is well understood and small. A middle ground many teams land on: auto-apply for lower-risk/highly-tested workspaces (e.g., stateless compute, ephemeral environments), manual confirmation retained for stateful or wide-blast-radius workspaces (databases, shared networking, IAM), rather than a single organization-wide policy. Policy-as-code checks ([§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) can also serve as an automated gate that substitutes for some of what manual apply confirmation provides, if the team wants speed without losing a safety mechanism entirely.
_What the interviewer is probing for:_ Whether the candidate can reason about risk-appropriate automation rather than treating "more automation" as unconditionally better.

## 12. Common Misconceptions

1. **"A PR's speculative plan can be applied directly from the PR."** It cannot — speculative plans have no apply action; only a run against the tracked branch can apply.
2. **"VCS-driven workspaces replace the need for a CI/CD pipeline entirely."** They replace the Terraform-execution portion of a pipeline, but application build/test/deploy steps unrelated to Terraform still need their own CI, and complex pre/post-plan automation ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) may still need external CI integration via the API.
3. **"Auto-apply is the default and expected setting."** It's an explicit opt-in; manual apply confirmation is the safer default most production workspaces use.
4. **"Every push to any branch triggers a run."** Only pushes matching the workspace's configured tracked branch (and, in a monorepo, matching path filters) trigger runs — pushes to unrelated branches or paths are ignored.

## 13. 🔑 Key Takeaways

- VCS-connected workspaces automatically queue a speculative plan on PRs (review-only, non-appliable) and a plan-and-apply run on pushes/merges to the tracked branch.
- Speculative plans and appliable runs are structurally different — this is a deliberate safety boundary, not a UI limitation.
- Auto-apply vs. manual apply confirmation is a per-workspace risk decision that should track the actual blast radius of that workspace.
- Monorepos need careful working-directory and path-filter scoping so one workspace's run isn't triggered by unrelated changes.
- Branch protection on the tracked branch effectively becomes part of the infrastructure change-control process once merges can trigger applies.

## 14. Related Concepts & What's Next

[§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) covers the policy-check stage that inserts itself into this same run pipeline between plan and apply. [§88](./Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md) covers run triggers, which let one workspace's successful apply automatically queue a run in a dependent workspace. [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) and [§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) revisit CI/CD integration and GitOps patterns for teams not using VCS-driven TFC workspaces directly.

**Next Section:** [§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) — `Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md`
