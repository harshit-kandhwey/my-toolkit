# Section 103 (Part 14): GitOps for Terraform: PR-Based Plan/Apply Workflows

## 1. Definition

**Plain language:** GitOps for Terraform means the Git repository — specifically its protected branch — is the single source of truth for what infrastructure should exist, and the only way to change real infrastructure is through a pull request against that repository. Nobody runs `terraform apply` from their laptop against production; the pipeline does it, and only after a PR containing the change has been reviewed and merged.

**Precise definition:** **GitOps for Terraform** is an operating model where infrastructure changes follow a strict sequence: a **feature branch** is created and modified, a **pull request** opens against the protected branch, a CI pipeline ([§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) automatically runs `terraform plan` against that PR and posts the resulting diff as a PR comment for **human review**, the PR requires approval and passing status checks before it can merge, and only **after merge to the protected branch** does a second, separate pipeline stage run `terraform apply` — applying the exact plan that was reviewed, never a freshly recomputed one. The defining constraint is that **apply never runs directly from a feature branch or an unreviewed/unmerged state** — the merge event to the protected branch is the only trigger for `apply`, making the Git history of that branch an accurate, auditable record of every change that was ever actually applied to real infrastructure.

> 💡 **Tip:** The single test for "is this actually GitOps, or just CI with extra steps" is: can `apply` run against production infrastructure without a corresponding merged commit on the protected branch existing first? If the answer is yes — someone can trigger an out-of-band apply, or apply runs on a feature branch push — it isn't GitOps, no matter how much Terraform automation surrounds it.

## 2. Why This Matters

- **Git history becomes an accurate infrastructure change log.** Because apply only ever runs from a merge to the protected branch, `git log` on that branch is not just "what the config says now" but a true record of every change that was ever actually applied, in order, with an associated PR and approver.
- **Review happens on the artifact that matters — the plan diff, not just the HCL diff.** As emphasized in [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md), a small HCL change can imply a large infrastructure blast radius; GitOps workflows post the actual `plan` output to the PR specifically so reviewers see the real consequence, not just the source diff.
- **Removes the single biggest source of untracked infrastructure drift: ad hoc local applies.** An engineer running `terraform apply` from their laptop against a shared workspace — even with good intentions — creates changes with no PR, no review, and no clean audit trail; GitOps structurally prevents this by making the pipeline the only path to `apply`.
- **Enables safe rollback via revert.** Because every applied change corresponds to a specific merged commit, rolling back is a normal `git revert` followed by the same plan/apply pipeline — no separate "how do we undo this" runbook is needed.
- **Scales review across a team without scaling risk.** Multiple engineers can propose changes concurrently via PRs; the merge-gated apply model ensures each change is independently reviewed and applied in a controlled, serialized way rather than colliding in an ad hoc shared apply process.

## 3. Prerequisites and Dependencies

This section is the direct synthesis of [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md) (plan-based review as the artifact GitOps reviews), [§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) (the CI mechanics — PR-triggered plan, merge-triggered apply — that implement GitOps), and state locking from [§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md) (which prevents concurrent applies from corrupting shared state even under a GitOps model with multiple merged PRs in flight). It also connects to Terraform Cloud's VCS-driven workflow ([§85](../Part12/Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md)), which is essentially a managed, opinionated implementation of the GitOps pattern described generically here.

## 4. Architecture / Conceptual Diagram

```text
   1. Feature branch created, .tf files changed
              │
              ▼
   2. PR opened/updated against `main`
              │
              ▼
   3. CI pipeline (PR trigger, §102):
        fmt -check → validate → plan -detailed-exitcode -out=tfplan
        → tests (§100) → policy check (§101)
              │
              ▼
   4. Plan diff posted as PR comment ──────► Human reviewer reads plan,
                                              not just HCL diff
              │
              ▼
   5. Required approvals + all status checks pass
              │
              ▼
   6. PR merged into `main`               ◄── Only trigger for step 7
              │
              ▼
   7. CI pipeline (merge trigger, §102):
        terraform apply <the exact tfplan from step 3>
              │
              ▼
   8. Apply result posted / logged; `main`'s history now accurately
      reflects every change ever applied to real infrastructure

   NEVER: apply triggered directly from a feature branch, a local
   machine, or any event other than merge to the protected branch.
```

- Step 3's plan is the artifact that must survive unchanged all the way to step 7 — this is why persisting the saved plan file as a build artifact ([§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) §5.2) is not an optional nicety but a structural requirement of correct GitOps.
- Step 4 is where GitOps earns its value over plain CI: the reviewer isn't reading source code and guessing at impact, they're reading the actual computed diff.
- The "never" at the bottom is the actual defining property — everything above it is implementation detail that varies by CI platform; that constraint is what makes it GitOps specifically.

## 5. Hands-On

### 5.1 Posting a Human-Readable Plan Diff as a PR Comment

**Purpose:** Turn raw `terraform plan` output into a reviewable PR comment automatically, the concrete mechanism that makes step 4 above possible.

**Syntax:**

```yaml
# excerpt from a GitHub Actions plan job
- name: Terraform plan
  id: plan
  run: |
    terraform plan -detailed-exitcode -out=tfplan
    terraform show -no-color tfplan > plan_output.txt
  continue-on-error: true

- name: Comment plan on PR
  uses: actions/github-script@v7
  with:
    script: |
      const fs = require('fs');
      const plan = fs.readFileSync('plan_output.txt', 'utf8').slice(0, 60000);
      github.rest.issues.createComment({
        issue_number: context.issue.number,
        owner: context.repo.owner,
        repo: context.repo.repo,
        body: `#### Terraform Plan\n\`\`\`\n${plan}\n\`\`\``
      });
```

**Example usage and expected output:**

```text
PR #128 — comment posted by github-actions[bot]:

#### Terraform Plan
```

# aws_db_instance.primary will be updated in-place

~ resource "aws_db_instance" "primary" {
~ allocated_storage = 100 -> 200
id = "db-prod-primary"
}

Plan: 0 to add, 1 to change, 0 to destroy.

```

```

**Production usage example:** Reviewers approve or request changes on the PR based on this exact comment — a storage increase is an easy approve, while a comment showing `1 to destroy` on a stateful resource prompts immediate scrutiny before any approval is given.

**Common errors:** Not truncating long plan output (as `.slice(0, 60000)` does above) can exceed the CI platform's comment size limit for very large plans, causing the comment step itself to fail silently or post a truncated, confusing result — always cap and, for genuinely huge plans, link to full CI logs instead of inlining everything.

### 5.2 Gating Merge on Approval and Plan Success

**Purpose:** Configure branch protection so merging is technically impossible without both a passing plan-based pipeline and human approval.

**Syntax:**

```bash
# via GitHub CLI, configuring branch protection on `main`
gh api repos/OWNER/REPO/branches/main/protection \
  --method PUT \
  --field required_status_checks='{"strict":true,"contexts":["Terraform Plan / plan"]}' \
  --field enforce_admins=true \
  --field required_pull_request_reviews='{"required_approving_review_count":1}' \
  --field restrictions=null
```

**Example usage and expected output:**

```text
$ gh pr merge 128
✓ Required status check "Terraform Plan / plan" has passed
✗ At least 1 approving review is required before merging
Merge blocked.
```

**Production usage example:** Any organization treating production infrastructure changes seriously configures this exact combination — required status checks plus required approvals plus `enforce_admins: true` (so even repository admins can't bypass the gate, a common and important detail) — as a baseline, non-negotiable repository setting.

**Common errors:** Leaving `enforce_admins` false (or unset, defaulting to false on most platforms) means administrators can merge around the required checks entirely, silently reintroducing the "someone can bypass review" risk GitOps is meant to eliminate — this is a frequently missed setting.

### 5.3 Merge-Triggered Apply Using the Reviewed Plan Artifact

**Purpose:** Ensure the apply stage, triggered strictly by merge to `main`, applies exactly what was reviewed rather than recomputing.

**Syntax:**

```yaml
# .github/workflows/terraform-apply.yml
name: Terraform Apply

on:
  push:
    branches: [main]
    paths:
      - "**.tf"

jobs:
  apply:
    runs-on: ubuntu-latest
    environment: production # requires a manual approver in GitHub Environments
    steps:
      - uses: actions/checkout@v4
      - uses: hashicorp/setup-terraform@v3
      - run: terraform init
      - run: terraform apply -auto-approve tfplan
```

**Example usage and expected output:**

```text
$ gh run watch
Terraform Apply / apply   waiting  ──► Review required by environment
                                        protection rule (production)
...approved by @platform-lead...
Terraform Apply / apply   pass   Apply complete! Resources: 0 added, 1 changed, 0 destroyed.
```

**Production usage example:** GitHub's `environment: production` protection rule adds a second, independent approval gate specifically on the apply step — distinct from the PR review — commonly required by organizations wanting a "four-eyes" separation between whoever approved the code change and whoever authorizes it touching production.

**Common errors:** This example assumes `tfplan` is available in the apply job's workspace — in practice this requires either re-fetching the artifact uploaded by the merged PR's plan job (matched by commit SHA) or, more commonly in real pipelines, storing the plan artifact keyed to the PR/commit so the apply job can retrieve the _exact_ file rather than any plan; skipping this step and letting `apply` implicitly re-plan reopens the plan/apply consistency gap discussed in [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md).

## 6. Production Usage Notes

- **Plan and apply are almost always separate CI jobs/pipelines with separate triggers**, not one long pipeline — this is what makes the "never apply without a merge" constraint enforceable at the trigger-configuration level rather than relying on in-pipeline logic to decide.
- **Terraform Cloud's VCS-driven workflow ([§85](../Part12/Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md)) implements this entire pattern natively** — a workspace connected to a VCS repo automatically runs a "speculative plan" on PRs and a real run on merge, with the plan-file consistency problem handled internally by Terraform Cloud rather than needing custom artifact-passing logic.
- **Environment promotion (dev → staging → prod, [§74](../Part10/Section-74-Part10-Environment-Promotion-Patterns-dev-staging-prod.md)) typically layers on top of GitOps rather than replacing it** — each environment might correspond to a separate workspace/directory with its own PR-gated pipeline, and promotion between environments is itself often a PR (e.g., merging a tag or branch that's already been proven in staging) rather than a manual step.

## 7. Security Considerations

- The merge-triggered apply job's credentials are the actual keys to production — restricting who can approve PRs and who can approve the separate environment-protection gate (§5.3) is a real access-control decision, not a formality, and ties directly to least-privilege execution role design ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)).
- A GitOps model is only as strong as branch protection configuration — `enforce_admins: false`, a missing required-approval count, or a misconfigured `CODEOWNERS` file all create bypass paths that undermine the entire "apply only happens via reviewed merge" guarantee.
- Fork-based PRs (common in open-source or loosely-permissioned internal repos) pose a specific risk: a PR-triggered plan job that runs with full cloud credentials against a PR from an untrusted fork can expose those credentials to attacker-controlled code — most CI platforms restrict secret access on fork PRs by default specifically because of this, and that restriction should not be casually disabled.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                          | Likely Cause                                                                                         | Resolution Path                                                                                                                                                       |
| -------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Infrastructure changed but no corresponding merged PR exists in `main`'s history | Someone applied directly (local machine, manual pipeline trigger) bypassing the GitOps flow entirely | Investigate access controls that allowed a non-pipeline apply; tighten execution-role scoping so only the CI identity can apply                                       |
| Repository admin merged a PR with failing checks                                 | `enforce_admins` was not set to `true` in branch protection                                          | Enable `enforce_admins` so even admins are subject to required checks                                                                                                 |
| Apply stage applies a different diff than what reviewers approved                | Apply job recomputed a fresh plan instead of applying the exact reviewed plan artifact               | Ensure the plan file is persisted and retrieved by exact commit/PR reference, not regenerated                                                                         |
| Fork-based PR plan job fails with missing credentials                            | CI platform correctly withheld secrets from an untrusted fork PR by default                          | This is expected/desired behavior; use a separate, restricted workflow (e.g., requiring maintainer approval to run) for fork PRs rather than disabling the protection |

## 9. Best Practices

- Enforce `enforce_admins: true` (or the equivalent on other platforms) so branch protection cannot be silently bypassed by anyone, including administrators.
- Persist and re-apply the exact reviewed plan artifact at merge time; never let the apply stage recompute a fresh plan.
- Use a separate approval gate on the apply step itself (e.g., GitHub Environments, GitLab's manual job gates) for production, distinct from PR code review, when a "four-eyes" separation between code approval and production authorization is required.

## 10. Common Anti-Patterns / Mistakes

- **Allowing `apply` to be triggered by any event other than merge to the protected branch** — a feature-branch push, a manual workflow dispatch without restriction, or a scheduled job that applies unreviewed state — each reintroduces the exact untracked-change risk GitOps exists to remove.
- **Treating "the pipeline ran `terraform apply`" as equivalent to "this went through GitOps."** Automation alone isn't the point; the review gate between plan and apply, enforced by branch protection, is what makes it GitOps rather than just automated scripting.
- **Granting broad, standing apply credentials to individual engineers "just in case," alongside the GitOps pipeline.** This creates a parallel, unaudited path to production that undermines the entire model even if it's rarely used — the guarantee GitOps provides is only as strong as the absence of alternate paths.

## 11. Interview Questions

**🎯 Beginner:** _"What does GitOps mean in the context of Terraform, in one sentence?"_
**Model answer:** GitOps for Terraform means the only way to change real infrastructure is through a pull request against a protected Git branch — a plan runs and is reviewed on the PR, and `apply` only ever runs automatically after that PR is merged, never from a feature branch or a local machine.
_What the interviewer is probing for:_ Whether the candidate can state the core constraint (merge-gated apply) precisely, not just "GitOps means Terraform in CI."

**🎯 Intermediate:** _"Why does the apply stage need to use the exact plan file from the PR's review, rather than just running `terraform plan && terraform apply` again after merge?"_
**Model answer:** If the apply stage recomputes a fresh plan, any drift that happened between when the PR's plan was reviewed and when it merges — real infrastructure changing outside the pipeline, or another PR merging first — silently gets folded into what's applied, without ever being shown to a reviewer. Applying the exact saved plan file guarantees what actually gets applied is precisely what was reviewed and approved, closing that gap; if the saved plan has gone stale relative to current state, `apply` should fail loudly rather than silently reconciling against new state.
_What the interviewer is probing for:_ Understanding this as a consistency/integrity problem, not just a performance optimization to avoid running plan twice.

**🎯 Senior:** _"A team using GitOps for Terraform reports that occasionally two merged PRs' applies seem to interleave unpredictably, producing confusing results. What's the likely cause, and how does GitOps interact with state locking here?"_
**Model answer:** This is a state-locking and serialization issue, not a GitOps-model flaw per se — if two PRs targeting the same workspace/state merge in quick succession, their respective merge-triggered apply jobs can both start close together. A correctly configured remote backend with state locking ([§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) will force the second apply to wait for the first to release the lock, not truly "interleave" at the state level, but the _plan_ each PR's apply is applying may have gone stale by the time it's the second one's turn to run — the second apply could then fail (if using the strict "apply the exact plan, error on staleness" approach) or, if the pipeline is misconfigured to silently re-plan on lock-acquisition, apply something subtly different from what was reviewed. The fix is ensuring the CI pipeline correctly serializes apply jobs per workspace (e.g., GitHub Actions `concurrency` groups scoped to the workspace) and treats a stale saved plan as a hard failure requiring a fresh PR/re-review rather than a silent recompute.
_What the interviewer is probing for:_ Whether the candidate connects GitOps process design to the underlying state-locking mechanics rather than treating them as unrelated topics — a common gap in surface-level GitOps understanding.

**🎯 Architect:** _"Design the GitOps workflow for an organization managing production infrastructure across 15 Terraform workspaces (one per service), where changes sometimes need to span multiple workspaces atomically (e.g., a new VPC in one workspace that a service's workspace depends on). How do you preserve GitOps guarantees without forcing everything into one giant monolithic state file?"_
**Model answer:** I'd keep each workspace's own plan/apply pipeline strictly GitOps (PR-triggered plan, merge-triggered apply, branch-protected) as the baseline — this is non-negotiable per workspace regardless of cross-workspace concerns. For genuinely cross-workspace changes, I'd avoid trying to force atomic multi-workspace applies (which fights against Terraform's per-workspace state model and is a common source of the "giant state file" anti-pattern discussed in [§108](../Part15/Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md)); instead, I'd sequence the dependency explicitly: the upstream workspace's PR (e.g., the new VPC) merges and applies first, exposing its outputs (VPC ID, subnet IDs) via a `data` source, remote state read, or a proper interface like Terraform Cloud's run triggers/workspace dependencies ([§88](../Part12/Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md)); only once that's confirmed applied does the downstream service's PR — referencing the now-real upstream values — get opened, reviewed, and merged through its own independent GitOps pipeline. This preserves per-workspace GitOps guarantees (each change is independently reviewable and auditable) while accepting that true cross-workspace atomicity isn't a goal — the trade-off is a brief window where the dependency graph across workspaces is applied in stages rather than instantaneously, which is an acceptable and normal characteristic of a well-decomposed multi-workspace architecture, not a bug to engineer away.
_What the interviewer is probing for:_ Whether the candidate resists the urge to force artificial atomicity across state boundaries and instead designs a sequenced, still fully GitOps-compliant flow — a sign of mature large-scale Terraform architecture thinking.

## 12. Common Misconceptions

1. **"GitOps just means Terraform runs in CI instead of locally."** Running in CI is necessary but not sufficient — the defining property is that `apply` is strictly gated behind a reviewed, merged PR, with no alternate path.
2. **"A GitOps pipeline is complete once `apply` is automated."** Automation without a review gate between plan and merge is just automated scripting, not GitOps — the human review step on the plan diff is central, not optional.
3. **"Repository admins should always be able to bypass required checks for emergencies."** This is exactly the kind of exception that undermines the guarantee; a documented, audited break-glass process (a fast-tracked but still-reviewed and still-logged PR) preserves the audit trail even for genuine emergencies, unlike a blanket admin bypass.
4. **"Once GitOps is set up for one workspace, cross-workspace dependencies just work the same way."** Multi-workspace dependencies require deliberate sequencing (run triggers, remote state reads) — GitOps guarantees are per-pipeline, not automatically composable across independently-applied workspaces.

## 13. 🔑 Key Takeaways

- GitOps for Terraform's defining constraint is that `apply` only ever runs as a result of a merge to a protected branch — never from a feature branch, local machine, or any other trigger.
- The plan diff posted to the PR, not the raw HCL diff, is the artifact human reviewers actually evaluate — this is why plan-based testing ([§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)) and clean plan output matter so much to GitOps specifically.
- The exact plan reviewed on the PR must be the exact plan applied after merge — recomputing at apply time reopens a consistency gap GitOps is meant to close.
- Branch protection settings (required checks, required approvals, `enforce_admins`) are the actual enforcement mechanism; without them correctly configured, "GitOps" is only a convention, not a guarantee.
- Cross-workspace dependencies require explicit sequencing (run triggers, remote state) rather than forcing artificial atomicity across separate state files.

## 14. Related Concepts & What's Next

[§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md) supplies the plan-diff artifact this section's review step depends on. [§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) supplies the concrete CI mechanics (separate PR-triggered and merge-triggered pipelines) this section's workflow is built from. [§85](../Part12/Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md) covers Terraform Cloud's native implementation of this same pattern via VCS-driven workflows. [§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md) covers the state locking that keeps concurrent GitOps-triggered applies against the same workspace safe. [§74](../Part10/Section-74-Part10-Environment-Promotion-Patterns-dev-staging-prod.md) covers environment promotion patterns that typically layer on top of a GitOps foundation.

**Next Section:** [§104](./Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md) — `Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md`
