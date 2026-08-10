# Section 102 (Part 14): CI/CD Pipeline Integration (GitHub Actions, GitLab CI, Jenkins)

## 1. Definition

**Plain language:** Every technique covered so far in this Part — validate, plan-based checks, Terratest/`terraform test`, Sentinel/OPA policy checks — only becomes a real safeguard once it runs automatically, on every change, without depending on someone remembering to run it locally. CI/CD pipeline integration is the work of wiring those individual checks into an actual pipeline definition in whichever CI system a team uses, so that a PR simply cannot merge, or a change simply cannot reach production, without passing them.

**Precise definition:** **CI/CD pipeline integration for Terraform** is the configuration of a continuous integration/continuous delivery system — commonly **GitHub Actions**, **GitLab CI**, or **Jenkins** — to automatically execute the Terraform workflow (`fmt -check`, `validate`, `plan`, tests, policy checks, and ultimately `apply`) in response to repository events (pull request opened/updated, merge to a protected branch), using ephemeral runners with scoped cloud credentials, and surfacing results (plan diffs, test outcomes, policy violations) as pipeline status checks that can gate merges via branch protection rules. The specific mechanics differ by platform — GitHub Actions uses YAML workflow files and the official `hashicorp/setup-terraform` action; GitLab CI uses `.gitlab-ci.yml` with stages and a similar Terraform-specific job template; Jenkins uses either a declarative `Jenkinsfile` or the dedicated HashiCorp Terraform plugin — but the underlying pipeline shape (fmt/validate → plan → test/policy → apply-on-merge) is consistent across all three.

> 💡 **Tip:** The single most important design decision in any Terraform CI pipeline isn't which platform you use — it's _where the `apply` step runs and what triggers it_. A pipeline that runs `apply` on the same trigger as `plan` (e.g., every push to a feature branch) has no review gate at all; a correctly designed pipeline runs `plan` on PR events and `apply` only after merge to the protected branch, which is the GitOps pattern formalized in [§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md).

## 3. Prerequisites and Dependencies

This section is the practical integration point for everything else in Part 14: it assumes the CLI workflow fundamentals from Part 4 (`init`, `plan`, `apply`), the plan-based testing from [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md), the test frameworks from [§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md), and the policy checks from [§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) — all of which appear as individual steps in the pipelines built here. It also depends on remote backend and state locking concepts from [§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)–[§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md), since CI runners are ephemeral and require a remote backend to share state across runs, and on least-privilege execution role design from [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md), since CI credentials are the actual blast radius of a compromised pipeline.

## 2. Why This Matters

- **Consistency across every change.** A pipeline runs the exact same `fmt`/`validate`/`plan`/test/policy sequence on every single PR, eliminating the "did anyone actually run this locally before merging" uncertainty inherent in manual workflows.
- **Ephemeral, auditable execution.** CI runners don't retain state between runs and every execution is logged with exactly what ran, by what trigger, using what credentials — a meaningfully stronger audit trail than infrastructure changes applied from an individual's laptop.
- **Enables branch protection as a real enforcement mechanism.** Once pipeline checks post as GitHub/GitLab status checks, branch protection rules can require them to pass before merge is even _possible_ — turning "please run terraform plan before merging" from a social convention into a technical control.
- **Credential scoping becomes centralized and auditable.** Cloud credentials live in the CI system's secret store, scoped to specific pipelines and environments, rather than scattered across individual engineers' local AWS/Azure/GCP profiles.
- **Foundation for the GitOps pattern.** Everything in [§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) (PR-triggered plan, merge-triggered apply) depends on the pipeline mechanics built in this section actually working correctly first.

## 4. Architecture / Conceptual Diagram

```text
   PULL REQUEST OPENED/UPDATED                  MERGE TO main
            │                                          │
            ▼                                          ▼
   ┌─────────────────────────┐            ┌─────────────────────────┐
   │ CI Pipeline (PR trigger)│            │ CI Pipeline (merge      │
   │                         │            │ trigger)                │
   │ 1. terraform fmt -check │            │ 1. terraform init       │
   │ 2. terraform init       │            │ 2. terraform apply      │
   │ 3. terraform validate   │            │    tfplan  (saved from  │
   │ 4. terraform plan       │            │    the merged PR's plan)│
   │    -detailed-exitcode   │            │ 3. Post apply result    │
   │    -out=tfplan          │            └─────────────────────────┘
   │ 5. terraform test /     |        Only reachable after
   │    Terratest suite      |            step 6 passed AND a human
   │ 6. Policy check         |            approved the PR
   │    (Conftest/Sentinel)  |
   │ 7. Post plan diff as    |
   │    PR comment           |
   └─────────────────────────┘
            │
            ▼
   Branch protection: all steps above
   must pass as required status checks
   before merge button is enabled
```

- The PR-triggered pipeline never runs `apply` — it stops at producing and posting a reviewable plan, gated by every check in this Part.
- The merge-triggered pipeline is deliberately minimal: its job is to apply the _exact_ plan that was already reviewed, not to recompute a fresh one, closing the review/apply gap discussed in [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md).
- Branch protection rules are the actual enforcement mechanism — a pipeline that runs all these checks but doesn't gate the merge button on their results is only informational, not a real control.

## 5. Hands-On

### 5.1 GitHub Actions: PR-Triggered Plan Workflow

**Purpose:** Run fmt, validate, and plan on every PR touching Terraform files, posting the plan as a PR comment, using the official HashiCorp setup action.

**Syntax:**

```yaml
# .github/workflows/terraform-plan.yml
name: Terraform Plan

on:
  pull_request:
    paths:
      - "**.tf"

permissions:
  contents: read
  pull-requests: write
  id-token: write # for OIDC-based cloud auth

jobs:
  plan:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: hashicorp/setup-terraform@v3
        with:
          terraform_version: "1.9.0"

      - name: Terraform fmt
        run: terraform fmt -check -recursive

      - name: Terraform init
        run: terraform init

      - name: Terraform validate
        run: terraform validate

      - name: Terraform plan
        id: plan
        run: terraform plan -detailed-exitcode -out=tfplan
        continue-on-error: true

      - name: Post plan to PR
        uses: actions/github-script@v7
        with:
          script: |
            github.rest.issues.createComment({
              issue_number: context.issue.number,
              owner: context.repo.owner,
              repo: context.repo.repo,
              body: "Terraform plan exit code: ${{ steps.plan.outcome }}"
            })

      - name: Fail on plan error
        if: steps.plan.outcome == 'failure'
        run: exit 1
```

**Example usage and expected output:**

```text
$ gh pr checks 42
Terraform Plan / plan   pass   1m52s
```

**Production usage example:** This workflow, extended with the policy-check and test steps from [§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)–[§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md), is the standard PR gate at organizations using GitHub — its result becomes a required status check in branch protection, preventing merge until it passes.

**Common errors:** Forgetting `permissions: id-token: write` when using OIDC-based cloud authentication (the recommended, credential-free pattern for GitHub Actions against AWS/Azure/GCP) causes the cloud provider login step to fail with an opaque permissions error — this permission must be explicitly declared, it's not on by default.

### 5.2 GitLab CI: Staged Pipeline with a Terraform Template

**Purpose:** Show the equivalent staged pipeline in GitLab CI, using merge-request pipelines for the plan stage.

**Syntax:**

```yaml
# .gitlab-ci.yml
image:
  name: hashicorp/terraform:1.9
  entrypoint: [""]

stages:
  - validate
  - plan
  - apply

validate:
  stage: validate
  script:
    - terraform fmt -check -recursive
    - terraform init -backend=false
    - terraform validate
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"

plan:
  stage: plan
  script:
    - terraform init
    - terraform plan -detailed-exitcode -out=tfplan
  artifacts:
    paths:
      - tfplan
    expire_in: 1 week
  rules:
    - if: $CI_PIPELINE_SOURCE == "merge_request_event"

apply:
  stage: apply
  script:
    - terraform init
    - terraform apply tfplan
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
  when: manual
```

**Example usage and expected output:**

```text
$ glab ci status
validate   ✓ passed
plan       ✓ passed
apply      manual (awaiting trigger on main)
```

**Production usage example:** The `apply` job's `when: manual` on `main` is a deliberate human-in-the-loop gate — even after merge, a designated approver clicks to trigger the actual apply, common in organizations not yet ready for fully automatic apply-on-merge.

**Common errors:** Omitting `artifacts:` on the `plan` job means the saved `tfplan` file doesn't survive between pipeline stages (each GitLab CI job runs in a fresh container) — the `apply` job would then have no plan file to apply and either fail outright or, worse, silently fall back to an implicit fresh plan.

### 5.3 Jenkins: Declarative Pipeline with the HashiCorp Terraform Plugin

**Purpose:** Show the same plan/apply staging in a Jenkins declarative pipeline, common in organizations with existing Jenkins infrastructure.

**Syntax:**

```groovy
// Jenkinsfile
pipeline {
    agent any

    stages {
        stage('Validate') {
            steps {
                sh 'terraform fmt -check -recursive'
                sh 'terraform init -backend=false'
                sh 'terraform validate'
            }
        }
        stage('Plan') {
            steps {
                sh 'terraform init'
                script {
                    def planExit = sh(
                        script: 'terraform plan -detailed-exitcode -out=tfplan',
                        returnStatus: true
                    )
                    if (planExit == 1) { error("Terraform plan failed") }
                    env.HAS_CHANGES = (planExit == 2) ? "true" : "false"
                }
            }
        }
        stage('Apply') {
            when {
                allOf {
                    branch 'main'
                    environment name: 'HAS_CHANGES', value: 'true'
                }
            }
            steps {
                input message: 'Apply this plan to production?'
                sh 'terraform apply tfplan'
            }
        }
    }
}
```

**Example usage and expected output:**

```text
Stage "Plan" — terraform plan -detailed-exitcode -out=tfplan
Plan: 2 to add, 1 to change, 0 to destroy.
[Pipeline] // exit code 2, HAS_CHANGES=true

Stage "Apply" — waiting for input
Apply this plan to production? (Proceed / Abort)
```

**Production usage example:** The explicit `input` step gives Jenkins pipelines a manual approval gate directly in the pipeline UI, commonly used by teams migrating from a fully manual `terraform apply` habit toward automation incrementally, without removing human sign-off immediately.

**Common errors:** Using `sh 'terraform plan -detailed-exitcode'` without `returnStatus: true` causes Jenkins's default `sh` step behavior (treating any non-zero exit as a failed step) to mark exit code `2` — a legitimate "changes present" result — as a pipeline failure, the same `-detailed-exitcode` misuse flagged in [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md).

## 6. Production Usage Notes

- **Prefer OIDC-based short-lived credentials over long-lived static cloud access keys stored as CI secrets.** All three platforms support federated identity (GitHub Actions OIDC, GitLab CI's `id_tokens`, Jenkins with an OIDC plugin) issuing short-lived tokens scoped to a specific role — this removes an entire class of "leaked static credential" risk that long-lived secrets carry.
- **Pin the Terraform CLI version explicitly in every pipeline** (as shown via `terraform_version` in the GitHub Actions example) — an unpinned "latest" version can silently change plan/apply behavior between runs, undermining reproducibility.
- **Cache provider plugin downloads between pipeline runs** where the CI platform supports it (GitHub Actions cache, GitLab CI cache keys) — `terraform init` re-downloading providers on every run adds meaningful, avoidable pipeline latency at scale.

## 7. Security Considerations

- CI runners executing `apply` hold real, often broad, cloud credentials for the run's duration — scope them to the minimum permissions the specific workspace/environment needs ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)), and never share one broad credential across every environment's pipeline.
- Pipeline definitions themselves (the YAML/Groovy files) are part of the attack surface — a malicious PR that modifies `.github/workflows/*.yml` to add a step that exfiltrates secrets is a real, documented attack pattern; requiring separate review/approval for changes to workflow files themselves (most platforms support this) closes that gap.
- Secrets used by the pipeline (cloud credentials, if not using OIDC) must be stored in the CI platform's dedicated secret store, never in plaintext in the pipeline YAML or repository — this connects directly to the state-and-secrets concerns from [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                  | Likely Cause                                                                                                                                                  | Resolution Path                                                                                                        |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Pipeline fails on `terraform plan` with exit code 2 treated as failure   | `-detailed-exitcode`'s three-way exit code not correctly handled by the CI step (GitHub `continue-on-error`, GitLab job rules, or Jenkins `returnStatus`)     | Explicitly branch on the exit code as shown in each platform's example rather than relying on default failure handling |
| `apply` stage applies different changes than what was reviewed in the PR | Saved plan file (`tfplan`) wasn't passed between pipeline stages/jobs (missing artifact upload in GitLab, or plan re-run instead of reused in GitHub/Jenkins) | Persist the plan file as a build artifact and apply that exact file, never a freshly recomputed plan                   |
| OIDC-based cloud login step fails with a permissions error               | Missing `id-token: write` permission (GitHub Actions) or equivalent `id_tokens` config (GitLab), which isn't granted by default                               | Explicitly declare the OIDC token permission in the workflow/pipeline definition                                       |
| Pipeline is slow, mostly spent in `terraform init`                       | Provider plugins re-downloaded from scratch on every run with no caching configured                                                                           | Enable the CI platform's caching for the `.terraform` provider plugin directory between runs                           |

## 9. Best Practices

- Trigger `plan` on pull request events and `apply` only on merge to the protected branch, applying the exact saved plan file from the reviewed PR — never recompute a fresh plan at apply time.
- Require the full check sequence (fmt, validate, plan, tests, policy) as required status checks in branch protection, not just as pipeline steps that run but don't gate merging.
- Use OIDC/federated identity for cloud authentication in CI wherever the platform and cloud provider support it, eliminating long-lived static credentials from CI secret stores entirely.

## 10. Common Anti-Patterns / Mistakes

- **Running `apply` automatically on every push to a feature branch.** This removes the entire review gate the pipeline exists to provide — any commit to any branch could apply to real infrastructure with no human review whatsoever.
- **Storing long-lived cloud access keys as CI secrets when the platform supports OIDC.** This carries indefinite credential-leak risk for no operational benefit once OIDC is available.
- **Treating pipeline YAML/Groovy files as lower-scrutiny than application code.** A pipeline definition change can grant itself broader permissions or exfiltrate secrets just as easily as application code can introduce a vulnerability — it deserves the same review rigor.

## 11. Interview Questions

**🎯 Beginner:** _"What are the typical stages of a Terraform CI pipeline?"_
**Model answer:** A typical pipeline runs `terraform fmt -check` and `terraform validate` first as fast, cheap static checks, then `terraform plan` to compute what would change, often followed by automated tests and policy checks against that plan, and finally `terraform apply` — but the apply stage is usually gated separately, triggered only after a PR merges to the protected branch rather than on every push.
_What the interviewer is probing for:_ Basic sequencing knowledge and awareness that plan and apply are typically triggered by different events, not run back-to-back on every commit.

**🎯 Intermediate:** _"Why is `-detailed-exitcode` handling a common source of CI misconfiguration, and how do you fix it on GitHub Actions vs. Jenkins?"_
**Model answer:** By default, most CI systems treat any non-zero shell exit code as a failed step, but `-detailed-exitcode` uses exit code `2` to mean "changes present" — a normal, expected outcome, not an error. On GitHub Actions, this is handled with `continue-on-error: true` on the plan step plus explicit checking of `steps.<id>.outcome` afterward. On Jenkins, it's handled by capturing the exit code with `returnStatus: true` in the `sh` step instead of letting the default `sh` behavior fail the stage automatically. Both require the pipeline author to explicitly branch on the exit code rather than relying on default pass/fail semantics.
_What the interviewer is probing for:_ Concrete, platform-specific knowledge of how to correctly implement a pattern introduced conceptually in [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md).

**🎯 Senior:** _"A team's GitLab CI pipeline applies successfully on `main`, but engineers report the applied changes sometimes don't match what was shown in the merge request's plan output. What's the likely root cause and fix?"_
**Model answer:** This is almost certainly a missing or misconfigured `artifacts:` declaration on the plan job — without persisting the saved `tfplan` file as a build artifact, the apply job (running in a fresh container, since GitLab CI jobs don't share filesystem state by default) either fails to find the plan file or, if scripted carelessly, falls back to running a fresh `terraform plan` implicitly before apply. That fresh plan can differ from the reviewed one if any drift occurred between merge-request review and the apply job running — a different problem than the artifact issue but with the same symptom. The fix is to explicitly declare `artifacts: paths: [tfplan]` on the plan job and have the apply job consume that exact artifact, never recomputing.
_What the interviewer is probing for:_ Whether the candidate understands CI job isolation (fresh containers per job) as the root mechanical cause, not just "something's wrong with the pipeline."

**🎯 Architect:** _"You're standardizing Terraform CI across an organization that uses GitHub Actions, GitLab CI, and Jenkins in different business units, with no near-term plan to consolidate onto one platform. How do you achieve consistent governance (same checks, same gating logic) across all three without maintaining three divergent, hand-written pipeline definitions?"_
**Model answer:** I'd separate the actual Terraform logic (which checks run, in what order, what constitutes pass/fail) from the platform-specific orchestration syntax. Concretely: package the shared logic as platform-agnostic scripts or a small CLI wrapper (a `Makefile` or a dedicated shell script performing fmt-check/validate/plan/policy-check/test in sequence with consistent exit codes) that each platform's pipeline definition simply invokes — GitHub Actions calls `make ci-plan`, GitLab CI calls the same target, Jenkins shells out to it too. This means the actual governance logic (which policies run, what tests are required) lives in one place, versioned and reviewed like any other code, while each platform's YAML/Groovy file is reduced to thin, mostly-boilerplate orchestration (checkout, auth, invoke the shared script, upload artifacts) that's far cheaper to keep in sync across three ecosystems. I'd also centralize the Sentinel/OPA policy library ([§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)) as its own versioned bundle consumed identically regardless of which CI platform triggers the check, and standardize branch protection / merge-gating semantics as an organizational policy document, even though the exact mechanism (required status checks vs. Jenkins approval gates) differs by platform.
_What the interviewer is probing for:_ Whether the candidate thinks about CI portability and governance consistency as a genuine platform-engineering design problem, not just familiarity with three separate YAML dialects.

## 12. Common Misconceptions

1. **"CI/CD for Terraform just means running `terraform apply` in a pipeline instead of locally."** The value is in the full gated sequence (fmt/validate/plan/test/policy) and the review gate between plan and apply, not merely relocating where `apply` executes.
2. **"Any CI platform's default `sh`/`run` step behavior handles Terraform's exit codes correctly."** `-detailed-exitcode`'s three-way semantics require explicit handling on every platform; default non-zero-means-failure behavior actively fights against it.
3. **"Storing cloud credentials as CI secrets is inherently secure since they're encrypted at rest."** Encryption at rest doesn't address the risk of a long-lived credential being exposed through a misconfigured pipeline step, a compromised dependency, or a malicious PR modifying the pipeline itself — OIDC's short-lived, scoped tokens meaningfully reduce this blast radius in a way static secrets cannot.
4. **"Pipeline YAML files don't need the same code review scrutiny as application code."** A pipeline definition change can alter what credentials are used or what steps run with just as much impact as an application code vulnerability.

## 13. 🔑 Key Takeaways

- All three major CI platforms (GitHub Actions, GitLab CI, Jenkins) can express the same core Terraform pipeline shape: fmt/validate → plan → test/policy → gated apply, differing only in syntax.
- `terraform plan -detailed-exitcode`'s three-way exit code (0/1/2) requires explicit, platform-specific handling to avoid CI systems misreporting "changes present" as a failure.
- The saved plan file must be persisted and applied exactly as reviewed — never recomputed — across pipeline stages/jobs, which requires explicit artifact handling on most platforms.
- OIDC/federated identity is the preferred cloud authentication pattern for CI, replacing long-lived static credentials with short-lived, scoped tokens.
- Pipeline definitions and policy libraries deserve the same review rigor and version control discipline as the Terraform configuration they gate.

## 14. Related Concepts & What's Next

[§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)–[§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) supply the individual checks (validate/plan, tests, policy) that populate the pipeline stages built in this section. [§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)–[§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md) cover the remote backend and locking mechanics that make shared CI execution against a single workspace safe. [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) covers the least-privilege execution role design that scopes what CI credentials, however authenticated, are actually allowed to do. [§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) formalizes the PR-triggered-plan/merge-triggered-apply pattern shown here into the complete GitOps model for Terraform.

**Next Section:** [§103](./Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) — `Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md`
