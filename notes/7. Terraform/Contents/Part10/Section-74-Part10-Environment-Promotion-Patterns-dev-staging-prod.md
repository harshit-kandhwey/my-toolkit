# Section 74 (Part 10): Environment Promotion Patterns (dev → staging → prod)

## 1. Definition

**Plain language:** Environment promotion is the disciplined practice of proving a Terraform change works in a low-risk environment first, then rolling the exact same change forward through progressively higher-stakes environments, rather than applying an untested change directly to production. It's the infrastructure equivalent of a software deployment pipeline that gates a release through dev, then staging, then prod.

**Precise definition:** **Environment promotion** is the process of applying an identical (or minimally, deliberately parameterized) Terraform configuration change sequentially across a series of environments — typically dev, then staging, then production — using each earlier environment's successful `plan`/`apply` as evidence of readiness before the change is permitted to reach the next. Built on directory-based separation ([§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md), [§71](./Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md)) or Terraform Cloud workspaces ([§84](../Part12/Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md)) rather than CLI workspaces ([§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md)'s guidance directly informs this), promotion pipelines pair each environment directory with its own backend, its own variable values, and — critically — progressively stricter approval gates, so that a change reaching prod has already been validated (structurally, and often via automated tests, [§100](../Part14/Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)) in every environment before it.

> 💡 **Tip:** The single property that makes promotion meaningful is that the _same module version_ moves through every environment — only the input values (and approval strictness) change per environment. If dev, staging, and prod are calling different versions of a module, or different modules entirely, there's no real promotion happening; each environment is effectively an independent, untested deployment that merely shares a name with the others.

## 2. Why This Matters

- **This is the payoff of every decision Part 10 has built toward.** [§69](./Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md) established what workspaces are, [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)–[§71](./Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md) established directory-based separation as the appropriate foundation for real isolation, [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) explained why CLI workspaces can't provide it — promotion patterns are what that foundation is _for_.
- **It's the concrete mechanism that turns "prod is separate from dev" into "prod is safer than dev because dev already caught the mistake."** Isolation alone ([§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)) prevents a bad change in dev from touching prod; promotion additionally reduces the odds a bad change reaches prod at all.
- **Module versioning discipline becomes non-optional.** Promotion only works if there's a clear, trackable notion of "this exact version of the configuration passed in dev and staging" — which ties directly into module version constraints ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) and, later, CI/CD pipeline design (Part 14).
- **This is where Terraform-specific practice meets general software-delivery practice.** Anyone with CI/CD experience for application code will recognize this pattern immediately — Part 10 closes by showing how that familiar discipline applies to infrastructure changes specifically.
- **Sets up Part 11's transition.** Part 11 moves from environment-strategy theory into worked multi-cloud provisioning — the environment-directory layout and promotion discipline established here is the structure those upcoming AWS/Azure/GCP examples ([§75](../Part11/Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md) onward) are implicitly built on.

## 3. Prerequisites and Dependencies

This section assumes [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)'s directory-based separation, [§71](./Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md)'s concrete environment-directory file layout (the promotion pipeline below is built directly on Pattern 2 from that section), and [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md)'s reasoning for why CLI workspaces are unsuitable as the underlying mechanism. It references module versioning ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) and previews CI/CD pipeline integration ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) and native testing ([§99](../Part14/Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)–[§100](../Part14/Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)), which are covered in full later but are worth knowing exist as this section's natural next steps.

## 4. Architecture / Conceptual Diagram

```text
   Change lands in modules/app/ (or environments/dev/terraform.tfvars)
                          │
                          ▼
   ┌─────────────────────────────────────────────────────────┐
   │  environments/dev/                                      │
   │  - own backend, own (low-risk) credential               │
   │  - CI applies automatically on merge to main            │
   │  - terraform plan / apply                               │
   └─────────────────────────────────────────────────────────┘
                          │  plan clean, apply succeeds,
                          │  smoke tests pass
                          ▼
   ┌─────────────────────────────────────────────────────────┐
   │  environments/staging/                                  │
   │  - own backend, own credential                          │
   │  - CI applies automatically OR requires 1 reviewer      │
   │  - terraform plan / apply — SAME module version as dev  │
   └─────────────────────────────────────────────────────────┘
                          │  plan clean, apply succeeds,
                          │  integration tests pass
                          ▼
   ┌─────────────────────────────────────────────────────────┐
   │  environments/prod/                                     │
   │  - own backend, own SCOPED credential, separate account │
   │  - CI requires manual approval from a named approver    │
   │  - terraform plan reviewed by a human before apply      │
   │  - terraform plan / apply — SAME module version as      │
   │    dev and staging (never a newer, untested one)        │
   └─────────────────────────────────────────────────────────┘

   At every arrow: if plan/apply fails or a test fails,
   the change STOPS — it does not proceed to the next environment.
```

- The diagram is the direct, applied continuation of [§71](./Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md)'s Pattern 2 layout: promotion is not a separate mechanism bolted on top of environment directories, it's the sequencing discipline applied to running `plan`/`apply` across them in a fixed order.
- The approval-gate strictness increasing left to right (auto-apply in dev, human approval in prod) is what [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) argued CLI workspaces cannot express — this diagram only works because each environment is a genuinely separate CI target with its own pipeline configuration.

## 5. Hands-On

### 5.1 Promoting a Module Change Through a Pinned Version

**Purpose:** Show how a module version constraint ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) is used to guarantee the same tested code reaches every environment, one environment at a time.

**Syntax:**

```hcl
# environments/dev/main.tf
module "app" {
  source  = "git::https://github.com/acme/tf-modules.git//app"
  ref     = "v1.4.0"          # bumped first, here, in dev
}

# environments/staging/main.tf   (still on the prior version until dev is verified)
module "app" {
  source  = "git::https://github.com/acme/tf-modules.git//app"
  ref     = "v1.3.2"
}

# environments/prod/main.tf      (still on the prior version until staging is verified)
module "app" {
  source  = "git::https://github.com/acme/tf-modules.git//app"
  ref     = "v1.3.2"
}
```

**Example usage and expected output:**

```bash
$ cd environments/dev
$ terraform init -upgrade      # pull v1.4.0
$ terraform plan
# Plan reviewed: changes match expectations for v1.4.0
$ terraform apply
Apply complete! Resources: 2 changed, 0 destroyed.

# ... verification passes in dev ...
# staging's main.tf is now edited to ref = "v1.4.0" and applied next,
# then prod's main.tf last, once staging is verified.
```

**Production usage example:** This is the standard way module changes are rolled out in organizations with a versioned internal module registry ([§59](../Part8/Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)) — a module's Git tag or registry version number is the unit of promotion, bumped in one environment directory's `main.tf` at a time, verified, then bumped in the next.

**Common errors:** Bumping the module version reference in `prod/main.tf` before it has actually been verified in `staging/` — this defeats the entire purpose of promotion and is exactly the mistake a required-review process on environment directory changes is meant to catch.

### 5.2 A CI Pipeline Enforcing Promotion Order

**Purpose:** Show, at a conceptual level, how a CI pipeline encodes the promotion sequence and gating described in the architecture diagram.

**Syntax:**

```yaml
# Simplified CI pipeline stages (illustrative, not tied to one CI vendor)
stages:
  - plan-dev
  - apply-dev # auto-applies on merge to main
  - test-dev # smoke tests against dev
  - plan-staging
  - apply-staging # requires: test-dev passed
  - test-staging # integration tests against staging
  - plan-prod
  - approve-prod # manual gate: named human approver required
  - apply-prod # requires: approve-prod
```

**Example usage and expected output:**

```bash
$ git merge feature/bump-app-module   # merges into main
# Pipeline runs plan-dev -> apply-dev -> test-dev automatically
# On success, plan-staging -> apply-staging -> test-staging run automatically
# plan-prod runs and posts the diff for review
# Pipeline PAUSES at approve-prod, waiting for a named approver
$ # approver reviews terraform plan output for prod, clicks "approve"
# apply-prod runs only after that explicit approval
```

**Production usage example:** This staged-pipeline structure is exactly what [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) (CI/CD pipeline integration) and [§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) (GitOps for Terraform) cover in depth — this section previews the environment-promotion shape those later sections implement with concrete tooling (GitHub Actions, GitLab CI).

**Common errors:** Configuring `apply-prod` to trigger on the same merge event as `apply-dev` (rather than gating on `test-staging` succeeding and `approve-prod` being granted) collapses the promotion pipeline into a single simultaneous deploy — indistinguishable from applying directly to prod with no promotion at all.

## 6. Production Usage Notes

- The unit of promotion doesn't have to be a module version — for smaller projects without a separate module registry, the unit can simply be a Git commit SHA of the whole environment-directories repository, promoted by merging (or cherry-picking) the same commit's changes into each environment's applied state in sequence.
- Automated tests at each stage ([§99](../Part14/Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)–[§100](../Part14/Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)) meaningfully strengthen promotion — a `plan` with no unexpected diff is necessary but not sufficient evidence a change is safe; a smoke test hitting a real endpoint after `apply` in dev catches classes of problems a plan diff cannot.
- Rollback under a promotion model is symmetric to promotion itself: reverting a bad change means reverting the module version reference (or commit) in the affected environment's directory and re-applying, the same mechanism used to promote forward, just in reverse.
- Promotion speed should be allowed to vary by change risk — a one-line tag update might reasonably promote through all three environments within an hour with automated gates, while a networking topology change might deliberately sit in staging for days under closer observation before a human approves the prod promotion.

## 7. Security Considerations

- Prod's approval gate should require a named human approver distinct from whoever authored the change — this is standard separation-of-duties practice and is straightforward to enforce in directory-based separation (a CI rule tied to the `prod` environment directory) but has no clean equivalent in a CLI-workspace setup where there's no separate CI target per environment to attach the gate to.
- Because prod's directory uses its own scoped credential (per [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md)'s guidance), the promotion pipeline's final stage is also the pipeline's highest-privilege stage — access to trigger or approve the `apply-prod` step should itself be tightly restricted and audited, since it's functionally equivalent to granting prod deployment authority.
- Promotion pipelines that skip stages under pressure ("just apply directly to prod, we're behind schedule") reintroduce exactly the risk the pipeline exists to prevent — an emergency hotfix process should still require at minimum a `plan` review and an explicit approval, even if the full dev/staging soak time is compressed.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                              | Likely Cause                                                                                                                                                | Resolution Path                                                                                                                             |
| ------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| A change that worked in dev broke in prod despite passing staging                    | Prod's inputs (`.tfvars`) or scale (replica counts, instance sizes) differ meaningfully from staging, exposing a scale-dependent bug staging didn't surface | Make staging's configuration closer to prod's scale/shape where feasible, or add prod-scale testing earlier in the pipeline                 |
| Prod and staging are running different module versions despite "following" promotion | Someone manually bumped one environment's `main.tf` out of sequence, or a merge conflict left directories inconsistent                                      | Audit `environments/*/main.tf` module version references for consistency; add a CI check that fails if prod's version is ahead of staging's |
| Promotion pipeline stalls indefinitely at the prod approval gate                     | No approver has reviewed the pending `plan-prod` output, or the named approver is unavailable                                                               | Ensure more than one person is authorized to approve prod promotions; add pipeline visibility/alerting for pending approvals                |
| A hotfix needed to reach prod urgently, bypassing normal promotion timing            | Standard promotion soak time doesn't fit incident-response timelines                                                                                        | Maintain a documented, still-gated emergency path (plan review + approval still required, but expedited) rather than an ungated bypass      |

## 9. Best Practices

- Promote a single, identifiable unit of change (a module version, a commit SHA) through every environment in the same order every time — never let environments diverge on which version of the configuration they're running.
- Gate each promotion step on the previous environment's success (`plan` clean, `apply` succeeded, tests passed) rather than promoting on a fixed schedule regardless of outcome.
- Require a named human approval step before any prod apply, distinct from the change's author, even when every earlier stage is fully automated.
- Keep a documented, still-gated emergency/hotfix path so incident response doesn't create pressure to bypass promotion discipline entirely under time pressure.

## 10. Common Anti-Patterns / Mistakes

- **Applying directly to prod "just this once" to save time**, which both bypasses the safety value promotion provides and normalizes future bypasses.
- **Letting environment directories drift to different module versions without a clear, intentional reason** — the entire discipline collapses once "dev, staging, and prod run whatever version they happen to have" becomes the norm.
- **Treating a clean `terraform plan` as sufficient promotion evidence on its own**, without any functional or integration testing — a plan diff confirms the _intended_ infrastructure change, not that the resulting infrastructure actually behaves correctly.
- **Building the promotion pipeline on top of CLI workspaces** instead of directory-based separation, reintroducing exactly the shared-credential, no-independent-gating problem [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) warns against, just with an added layer of pipeline automation on top of an already-weak foundation.

## 11. Interview Questions

**🎯 Beginner:** _"What does 'environment promotion' mean in the context of Terraform?"_
**Model answer:** It means rolling out a configuration change through a fixed sequence of environments — typically dev, then staging, then production — applying and verifying it in each earlier environment before it's allowed to reach the next, rather than applying an untested change directly to production.
_What the interviewer is probing for:_ Basic conceptual grasp of the sequencing and gating idea, independent of any specific tooling.

**🎯 Intermediate:** _"What's the 'unit of promotion' in a typical dev-to-prod Terraform pipeline, and why does it matter that it stays the same across environments?"_
**Model answer:** It's typically a module version (a Git tag or registry version) or a commit SHA of the environment-directories repository. It matters because promotion is only meaningful evidence of safety if the exact same code that was verified in dev and staging is what actually reaches prod — if prod runs a different version than what was tested, the earlier environments' successful plans and tests say nothing about what prod is actually running.
_What the interviewer is probing for:_ Understanding that promotion's value depends on version consistency, not just the existence of multiple environments.

**🎯 Senior:** _"Your team's promotion pipeline auto-applies to dev and staging on every merge to main, with a manual approval gate only before prod. A recent incident showed a bad change broke staging for two hours before anyone noticed, delaying the next planned prod promotion. How would you improve the pipeline?"_
**Model answer:** The gap is that a broken staging environment went undetected — auto-apply without automated verification just moves the "did this actually work" question to a human eventually noticing, which is slow. I'd add automated smoke/integration tests ([§99](../Part14/Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)–[§100](../Part14/Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)) that run immediately after each `apply-dev` and `apply-staging` stage and gate progression to the next stage on those tests passing, not just on the `apply` command exiting successfully. I'd also add alerting tied to those test failures so the team is notified within minutes, not hours, and consider whether staging needs its own rollback automation (reverting to the last known-good module version) triggered automatically on repeated test failure, rather than waiting for a human to diagnose and manually revert.
_What the interviewer is probing for:_ Ability to diagnose that "apply succeeded" is a weak signal on its own and to design concrete automated verification and alerting improvements, not just process/documentation fixes.

**🎯 Architect:** _"Design an environment promotion strategy for a platform with 20 microservices, each with its own Terraform-managed infrastructure, where changes to a shared networking module need to propagate to all 20 without each team manually coordinating a simultaneous rollout."_
**Model answer:** Treat the shared networking module as an independently versioned artifact ([§59](../Part8/Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)'s registry pattern) with its own semantic version and changelog. Each microservice's environment directories pin to a specific version of that module, exactly as in this section's single-service example. When the networking module changes, publish a new version but don't force immediate adoption — instead, promote the version bump through one pilot microservice's dev → staging → prod pipeline first as a canary, catching any issues the change introduces in a single, contained blast radius. Once the pilot's prod promotion succeeds and soaks for an agreed period, open coordinated, automated pull requests (a "renovate/dependabot for Terraform modules" pattern) against the remaining 19 microservices' `environments/dev/main.tf` files bumping the version reference, letting each team's own dev → staging → prod pipeline carry the change through independently and on its own schedule, rather than one team forcing a synchronized org-wide rollout. Track adoption centrally (a dashboard showing which microservices are on which networking-module version) so stragglers are visible, and set an internal deprecation timeline for the old version to prevent indefinite lag. This avoids both extremes — a risky simultaneous 20-service rollout, and an uncoordinated free-for-all where some services never update.
_What the interviewer is probing for:_ Ability to scale the single-pipeline promotion concept into a cross-team, cross-repository coordination problem, balancing safety (canary-first) against practicality (not forcing synchronized rollouts) at real organizational scale.

## 12. Common Misconceptions

1. **"Promotion means literally copying the state file from dev into prod."** It does not — state files remain entirely separate per environment (per directory-based separation, [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)); what's promoted is the _configuration/module version_, applied independently against each environment's own state.
2. **"A clean `terraform plan` at every stage is sufficient proof a promotion is safe."** A plan confirms the intended infrastructure change matches expectations; it says nothing about runtime behavior, which is why automated testing at each stage matters.
3. **"Promotion pipelines require Terraform Cloud or a specific CI vendor."** The pattern is tooling-agnostic — it's fundamentally a discipline about ordering, gating, and version consistency across directory-based environments, implementable with any CI system ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) covers several concretely).
4. **"Faster promotion is always better."** Promotion speed should track change risk — compressing a genuinely risky change's soak time to move faster reintroduces the exact risk the staged pipeline exists to catch.

## 13. 🔑 Key Takeaways

- Environment promotion is the disciplined, gated rollout of the same configuration/module version through dev, then staging, then prod — built on directory-based separation, not CLI workspaces.
- The "unit of promotion" (a module version or commit SHA) must stay consistent as it moves through environments — divergence defeats the purpose.
- Gating each stage on the previous stage's actual verification (tests, not just a successful `apply`) is what makes promotion meaningfully safer than independent per-environment applies.
- Prod's promotion step should require a distinct, named human approval, separate from the change's author, even in an otherwise fully automated pipeline.
- This pattern is the practical payoff of choosing directory-based separation ([§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)) over CLI workspaces ([§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md)) — the independent CI targets and credentials that separation provides are what make differentiated gating possible at all.

## 14. Related Concepts & What's Next

This section closes Part 10's environment-strategy arc, which began with CLI workspace mechanics ([§69](./Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md)) and built through directory-based separation ([§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)), file layouts ([§71](./Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md)), workspace interpolation ([§72](./Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md)), and the explicit case against workspaces for isolation ([§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md)) to arrive at this promotion discipline. Part 11 now shifts from environment strategy to applying Terraform against real cloud providers — [§75](../Part11/Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md) opens with a deep dive into the AWS provider (VPC, EC2, S3, IAM provisioning patterns), the first of several provider-specific parts building worked examples on top of the environment-directory foundation established here. [§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md) (module versioning) and [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)/[§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md) (CI/CD and GitOps) are the natural deeper follow-ups for the mechanics only previewed in this section's hands-on examples.

**Next Section:** [§75](../Part11/Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md) — `Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md`
