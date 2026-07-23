# Part 9, Section 8: CI/CD for Infrastructure — Pipelines, GitOps, and Safe Deployment Patterns

## 1. Definition

**Plain language:** This section covers how the tools from Part 9 §1-4 (CloudFormation, CDK, Terraform) actually get run in a real organization — not manually from someone's laptop, but through an automated pipeline that validates, plans, requires review, and only then applies infrastructure changes, exactly like how application code goes through CI/CD before reaching production.

**Precise definition:** CI/CD for Infrastructure applies continuous integration and continuous delivery practices to infrastructure-as-code changes — automated pipelines that validate/lint IaC templates, compute and surface a plan/change-set for human review, require approval gates for sensitive environments, and execute the approved deployment — often following a **GitOps** model where the version-controlled repository state is the single source of truth driving automated, reconciled deployment, rather than deployment being triggered by manual, ad hoc commands.

## 2. Why It Exists / Problem It Solves

Every one of Part 9 §1-4's tools provides the _mechanism_ for deploying infrastructure changes safely (change sets, `cdk diff`, `terraform plan`) — but mechanism alone doesn't guarantee the _process_ around using it is safe. If any engineer can run `terraform apply` or `aws cloudformation deploy` directly against production from their own laptop, with their own credentials, whenever they want, the organization has no consistent, enforced practice of change review, no reliable audit trail of who approved what, and no structural prevention of a mistake or malicious action reaching production unreviewed — undermining much of what IaC was supposed to provide in the first place (Part 9 §1's original motivation).

CI/CD for infrastructure solves this the same way CI/CD solves it for application code: route every change through a **pipeline** — automated validation, a computed plan for review, an explicit approval gate for sensitive environments, and only then an automated (not manual) apply step — using a dedicated, appropriately-scoped service identity rather than individual engineer credentials, with every step logged and auditable.

## 3. Prerequisites and Dependencies

- **CloudFormation, CDK, and Terraform** (Part 9 §1-4): this section is about how to safely _operate_ these tools, not new tooling itself.
- **AWS CodePipeline & CodeBuild, AWS CodeDeploy, Deployment Strategies** (Part 9 §5-7): this section's validate/plan/review/approve/apply pattern is the _infrastructure-specific_ application of the same general pipeline discipline covered generically for application deployment in those sections — CodePipeline/CodeBuild can equally well orchestrate the stages described here.
- **CloudTrail** (Part 8 §5): pipeline-executed infrastructure changes are still recorded there, providing the audit trail of what the pipeline's service identity actually did.
- **IAM** (Part 2 §1-3): the pipeline's deployment role/credentials are a genuinely high-value, carefully-scoped security asset, directly building on IAM's least-privilege principles.

## 4. Internal Working

- A typical infrastructure pipeline has distinct **stages**: (1) **validate/lint** — syntax and static-analysis checks (`cloudformation validate-template`, `cdk synth`, `terraform validate`/`fmt`) catching basic errors cheaply and early; (2) **plan** — computing the change set/diff/execution plan and surfacing it somewhere reviewable (a pull request comment, a pipeline artifact); (3) **review/approval** — a human (or, for lower-risk environments, potentially an automated policy check) explicitly approves the plan before proceeding; (4) **apply** — the actual deployment, executed by the pipeline's own service identity, not a human's.
- **GitOps** is a specific philosophy/pattern where the **version-controlled repository is the single source of truth** — a pull request merge (not a manual `terraform apply` command typed by a human) is what triggers deployment, and the pipeline's job is to continuously (or on every merge) reconcile the actual deployed infrastructure to match whatever's currently in the repository's main branch — meaning "what's deployed" and "what's in the repo" should never meaningfully diverge, by construction of the workflow itself.
- **Environment promotion** typically flows a change through progressively more sensitive environments — dev → staging → production — with the plan/apply pipeline re-run (often against the identical, already-reviewed template/configuration) at each stage, and increasingly strict approval requirements at each step (e.g., dev might auto-apply on merge; production requires an explicit named approver).
- **Separation of duties** — the person who authored/reviewed the code change is often required to be different from the person who approves the production deployment gate, a common compliance-driven control preventing a single individual from unilaterally pushing an unreviewed change to production.
- Pipeline **service identities** (the IAM role/credentials the pipeline itself runs under) should be scoped to exactly what the specific pipeline's templates/configurations need — different pipelines (or different stages within one pipeline) often warrant different, appropriately narrower roles rather than one broad, all-powerful deployment identity used everywhere.

```
Pull Request opened (infrastructure change)
        |
        v
  Validate/Lint (fast, cheap, catches basic errors)
        |
        v
  Plan/Diff computed --> posted as PR comment for human review
        |
        v
  Human review + approval (code review AND infrastructure-change review)
        |
        v
  Merge to main branch
        |
        v
  Pipeline triggers: Apply to dev (auto) -> staging (auto or light approval) -> production (explicit approval gate)
        |
        v
  CloudTrail records exactly what the pipeline's service identity did, when
```

## 5. Architecture & Components

| Component                     | Explanation                                                                                                                                  |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| **Validate/Lint Stage**       | Fast, early syntax/static-analysis checks before any real planning or deployment is attempted.                                               |
| **Plan Stage**                | Computes the reviewable diff (change set, `cdk diff`, `terraform plan`) without applying anything.                                           |
| **Approval Gate**             | An explicit human (or policy-based) approval step, required before proceeding to apply, especially for production.                           |
| **Apply Stage**               | The actual deployment, executed by the pipeline's own service identity.                                                                      |
| **GitOps Reconciliation**     | The pattern where deployed state is continuously/automatically reconciled to match the version-controlled repository's current state.        |
| **Environment Promotion**     | The staged flow of a change through progressively more sensitive environments, each with its own review/approval requirements.               |
| **Pipeline Service Identity** | The IAM role/credentials the pipeline itself uses to make actual deployment API calls — distinct from any individual engineer's credentials. |

## 6. Lifecycle / Workflow

1. An engineer **opens a pull request** with an infrastructure change (a modified CloudFormation template, CDK code, or Terraform configuration).
2. The pipeline automatically **validates/lints** the change.
3. The pipeline **computes and posts a plan** (change set/diff/execution plan) as a PR comment or artifact, giving reviewers concrete visibility into exactly what will change, not just the code diff.
4. **Human reviewers** review both the code change and the computed plan, approving (or requesting changes).
5. On **merge**, the pipeline **deploys to the first environment** (commonly dev), often automatically.
6. The change **promotes through further environments** (staging, then production), with production typically requiring an **explicit, separate approval gate** before the pipeline proceeds to apply.
7. **CloudTrail** and pipeline logs together provide the full audit trail of what changed, who approved it, and what the pipeline's service identity actually did.

## 7. Configuration

| Setting                                                   | Purpose                                                                                                                                               |
| --------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pipeline stage definitions                                | The validate → plan → approve → apply sequence, and which environments/branches trigger which stages                                                  |
| Approval gate configuration (per environment)             | Who can approve, how many approvers required, whether approval is mandatory or optional per environment                                               |
| Pipeline service role/credentials (per stage/environment) | Scoped IAM permissions specific to what that stage's deployment actually needs                                                                        |
| Branch protection rules (in the source repository)        | Preventing direct pushes to main/production branches, requiring PR review before merge — the GitOps enforcement mechanism at the source-control layer |

⚠️ **Warning:** a pipeline that computes and displays a plan for review, but then applies a **freshly recomputed plan** at apply time (rather than the exact plan file that was actually reviewed) introduces a subtle but real gap — if the underlying live infrastructure changed between the review and the apply (someone else's concurrent change, or drift), the plan that's actually executed may not be identical to what was reviewed and approved. Using a saved plan file (`terraform apply <planfile>`, or equivalent change-set-execution patterns) closes this gap by guaranteeing the exact reviewed plan is what's applied.

## 8. Commands (Full Documentation)

Since this section is about pipeline _process_ rather than new tool-specific commands, the relevant "commands" are how Part 9 §1-4's existing commands are sequenced within a pipeline definition (e.g., a GitHub Actions workflow, an AWS CodePipeline/CodeBuild definition, or similar).

### Example CI Pipeline Stage Sequencing (Terraform, conceptual)

- **Purpose:** Illustrates how `terraform` commands (Part 9 §4) are sequenced across pipeline stages, rather than run individually and manually.
- **Practical example (pipeline YAML, illustrative):**

  ```yaml
  stages:
    - name: validate
      run: terraform fmt -check && terraform validate

    - name: plan
      run: terraform plan -out=tfplan
      artifacts: [tfplan]

    - name: post-plan-for-review
      run: post-plan-comment-to-pr.sh tfplan

    - name: approval-gate
      environment: production
      requires_manual_approval: true

    - name: apply
      run: terraform apply tfplan # applies the EXACT reviewed plan, not a freshly computed one
  ```

- **Production usage:** this stage structure — validate, plan, review, gated approval, apply-the-reviewed-plan — is the general pattern applicable across CloudFormation, CDK, and Terraform pipelines alike, with the tool-specific commands from Part 9 §1-4 slotted into each stage.
- **Common errors:** skipping the "apply the exact saved plan file" step (§7 warning) in favor of re-running `plan` immediately before `apply` reintroduces the review/apply consistency gap this pattern exists to close.
- **Security impact:** the `apply` stage's execution identity is the pipeline's own scoped service role — never an individual engineer's personal credentials — making this the highest-privilege, most carefully protected step in the entire pipeline.

### AWS CodePipeline / CodeBuild (AWS-native CI/CD option)

- **Purpose:** AWS's own native CI/CD service, an alternative to third-party options (GitHub Actions, GitLab CI, Jenkins) for building infrastructure pipelines, with native integration for CloudFormation deployment actions specifically.
- **Production usage:** CodePipeline has a built-in CloudFormation deployment action type that natively understands change sets (creating one, then requiring an explicit separate approval action before executing it) — directly implementing the plan-then-approve-then-apply pattern as native pipeline stages without custom scripting.
- **Common errors/considerations:** verify current CodePipeline/CodeBuild capabilities and integration patterns against AWS documentation, as this is a service that continues to evolve; the general pipeline _pattern_ described in this section (validate → plan → review → approve → apply) applies regardless of which specific CI/CD tool implements it.

## 8a. Artifact Management & Supply Chain Security — CodeArtifact

### 8a.1 Definition and the Problem It Solves

This section's pipeline (validate → plan → review → approve → apply) governs how _infrastructure definitions_ move safely to production. A closely related, often-overlooked question is how the **software packages and dependencies** those definitions and the applications they deploy actually pull in — npm packages, Python packages, Maven artifacts — are sourced, stored, and verified. Pulling directly from public package registries (npmjs.com, PyPI, Maven Central) on every build introduces two real risks: **availability risk** (a public registry outage blocks every build depending on it) and **supply-chain risk** (a compromised or maliciously-published public package, or a dependency silently changed after initial review, can be pulled into a build without anyone noticing).

**AWS CodeArtifact** is a managed artifact repository service that sits between build pipelines and public package registries, addressing both risks.

### 8a.2 How CodeArtifact Works

- CodeArtifact hosts private package repositories (npm, PyPI, Maven, NuGet, and others) that pipelines pull from, instead of pulling directly from the public internet on every build.
- **Upstream repositories**: a CodeArtifact repository can be configured to transparently proxy a public registry (e.g., npmjs.com) — the first time a specific package version is requested, CodeArtifact fetches and caches it; subsequent requests for that same version are served from CodeArtifact's own cache, without depending on the public registry's availability.
- This gives an organization one controlled point where package versions are pinned and can be audited or scanned, rather than every individual build pulling directly and independently from the public internet.

```bash
# Point npm at a CodeArtifact repository as its registry
aws codeartifact login --tool npm --repository my-repo --domain my-domain --domain-owner 111122223333

# Publish an internally-built package to a private CodeArtifact repository
aws codeartifact publish-package-version \
  --domain my-domain --repository my-repo \
  --format npm --package my-internal-package --package-version 1.2.0 \
  --asset-content ./my-internal-package-1.2.0.tgz --asset-name package.tgz
```

- **Common error:** treating CodeArtifact purely as a caching layer without also integrating dependency scanning — caching a compromised package just as readily as a legitimate one; caching alone provides availability benefits but not, on its own, the security benefit.

### 8a.3 Supply Chain Security Practices

- **Dependency scanning integrated into the validate stage** (§7): scanning package dependencies for known vulnerabilities (CVEs) or license-compliance issues before a build proceeds, the same "shift security left" principle §11 applies to IaC template scanning, applied here to third-party dependencies specifically.
- **Artifact signing**: cryptographically signing build artifacts (container images, packages) at build time, and verifying that signature before deployment, so a downstream deployment step can confirm an artifact genuinely came from the organization's own trusted build pipeline and hasn't been tampered with or substituted after the fact — conceptually similar to how this section's "apply the exact reviewed plan artifact" principle (§7 warning) protects the IaC review/apply gap, applied here to software artifacts and their build/deploy gap.
- **Version pinning through CodeArtifact's cache**: since CodeArtifact caches the specific package versions actually requested, an organization gets a natural, auditable record of exactly which upstream package versions were ever pulled into any build — useful both for vulnerability-response ("which of our builds actually used the affected version") and for general build reproducibility.

### 8a.4 Production and Enterprise Usage

- Regulated organizations (financial services, healthcare) commonly mandate that no build pipeline pulls packages directly from the public internet — every dependency must route through an internally-controlled artifact repository like CodeArtifact, both for availability and for the auditability of exactly what entered a build.
- Artifact signing and verification is an increasingly common requirement in supply-chain-security-conscious organizations, often driven by the same compliance frameworks (SOC 2, and similar) that drive this section's separation-of-duties and approval-gate requirements (§10, §16) — supply chain integrity is treated as part of the same overall change-management control set as infrastructure deployment safety.

### 8a.5 Key Takeaways

1. CodeArtifact centralizes and caches package dependencies behind one controlled, organization-owned repository, reducing both public-registry availability risk and uncontrolled supply-chain exposure.
2. Caching alone isn't a security control — dependency vulnerability scanning must be explicitly integrated (typically into the pipeline's validate stage) to get the actual security benefit, not just availability.
3. Artifact signing at build time, verified before deployment, closes a supply-chain-specific version of the same "what's deployed should exactly match what was reviewed" principle this section already applies to infrastructure plans.

---

## 9. Hands-On Example — GitOps-Style Environment Promotion

```
Repository structure (illustrative):
  /infrastructure
    /environments
      /dev/main.tf        (references shared modules, dev-specific variables)
      /staging/main.tf     (references shared modules, staging-specific variables)
      /production/main.tf  (references shared modules, production-specific variables)
    /modules
      /order-queue/        (shared, reusable module used by all three environments)

Pipeline behavior on PR merge to main:
  1. Deploy to dev automatically (low risk, fast iteration)
  2. Deploy to staging automatically, but run integration tests after
  3. Deploy to production ONLY after:
     a. Staging integration tests pass
     b. An explicit, named human approver approves the production gate
     c. The approval references the EXACT plan that was computed and reviewed
```

This structure directly embodies GitOps: the repository's `main` branch is the single source of truth, and the pipeline's job is purely to reconcile each environment's actual deployed state to match what's in the repository — nobody manually runs `terraform apply` against any environment directly; the pipeline is the only path to deployment, and every deployment traces back to a specific, reviewed, merged commit.

## 10. Production & Enterprise Usage

- **Startups** often begin with a simple two-stage pipeline (validate + apply, perhaps with informal manual review) and add formal approval gates and environment promotion as the team and the stakes of a production mistake both grow.
- **Enterprises** build extensive, standardized pipeline templates used consistently across many teams' infrastructure repositories, often with mandatory security scanning stages (checking IaC templates for known misconfiguration patterns — e.g., detecting an S3 bucket being created without encryption, before it's ever deployed) integrated directly into the validate stage, catching security issues before deployment rather than relying solely on Part 8 §6's Config Rules to catch them after the fact.
- **Separation of duties** and formal approval-gate requirements are frequently driven directly by compliance requirements (SOC 2, PCI-DSS, and similar frameworks explicitly require change-management controls that a well-designed infrastructure pipeline directly satisfies) — infrastructure pipeline design is a genuine, common compliance-audit discussion point.
- Large organizations with many independent teams often centralize the _pipeline pattern/tooling_ (a shared, reusable pipeline template) while allowing each team to own their own specific infrastructure repository/configuration — balancing organizational consistency with team autonomy.

## 11. Security Considerations

- The pipeline's deployment service identity is one of the highest-value targets in the entire organization's AWS footprint, since it typically has broad infrastructure-provisioning permissions — protecting the CI/CD system itself (its own access controls, secret management, and the security of the pipeline configuration/scripts themselves) is as important as protecting the AWS credentials directly.
- Pre-deployment security scanning of IaC templates (checking for known misconfiguration anti-patterns before deployment) shifts security left, catching issues cheaper and earlier than post-deployment detection (Config Rules, Part 8 §6) alone.
- GitOps' "repository as source of truth" model means source-repository access control and branch protection rules are themselves a critical security boundary — someone who can merge to the main branch of an infrastructure repository effectively has significant deployment power, even without direct AWS credentials.

## 12. Performance Considerations

- Running full plan/apply cycles across multiple environments (dev, staging, production) sequentially adds real pipeline execution time — parallelizing independent stages where safe (e.g., validation and unrelated tests) while keeping genuinely sequential stages (staging must succeed before production) sequential is a common pipeline-design optimization.
- Very large infrastructure changes (affecting many resources) naturally take longer to plan and apply regardless of pipeline design — this is the underlying tool's characteristic (Part 9 §1-4), not something pipeline design alone can eliminate, though splitting into smaller, more frequent changes is a common mitigation.

## 13. Monitoring

- Pipeline execution history/logs are the primary "did this deployment succeed, and what exactly happened" signal, complementing (not replacing) the underlying tool's own signals — CloudFormation stack events, Terraform apply output.
- CloudTrail (Part 8 §5) records what the pipeline's service identity actually did at the AWS API level, providing an independent, tamper-resistant cross-check against the pipeline's own self-reported logs.
- Failed pipeline runs (especially at the approval-gate or apply stage) are worth alerting on, following the same CloudWatch Alarms → SNS pattern (Part 8 §3, Part 7 §3) used throughout this roadmap for other operational failure signals.

## 14. Troubleshooting

| Symptom                                                                       | Likely Root Cause                                                                                                                  | Fix                                                                                                                                                            |
| ----------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pipeline plan/apply behaves differently than expected from local testing      | Pipeline service identity has different (often more restricted) permissions than the engineer's local credentials used for testing | Ensure the pipeline's service role has exactly the permissions the deployment genuinely needs, tested end-to-end through the actual pipeline, not just locally |
| Applied change doesn't match what was reviewed in the PR                      | Plan was recomputed fresh at apply time rather than applying the exact saved/reviewed plan file                                    | Fix the pipeline to save and apply the exact plan artifact from the review stage (§7 warning)                                                                  |
| Approval gate bypassed or approved by the same person who authored the change | Separation-of-duties enforcement not actually configured in the pipeline/repository settings                                       | Configure branch protection / pipeline approval rules to require a different approver than the change author                                                   |
| Deployment succeeded in staging but fails identically-configured production   | Environment-specific configuration difference (account, region, resource limits) not accounted for                                 | Compare environment-specific variables/parameters carefully; verify account-level resource limits/quotas in the production account specifically                |

## 15. Best Practices

- Apply the exact reviewed plan artifact, not a freshly recomputed one, to guarantee review/apply consistency.
- Use a dedicated, scoped pipeline service identity for deployment — never individual engineer credentials for production applies.
- Require explicit, separate approval gates for production, ideally with separation of duties from the change author.
- Integrate pre-deployment security scanning into the validate stage, shifting security checks earlier and cheaper than post-deployment detection alone.
- Treat the source repository's branch protection and merge-approval rules as a genuine security boundary, not just a code-quality practice.

## 16. Anti-Patterns & Common Mistakes

- ❌ Allowing direct `terraform apply`/`cloudformation deploy`/`cdk deploy` from individual engineers' local machines against production, bypassing the entire pipeline review/approval structure.
- ❌ Recomputing the plan fresh at apply time instead of applying the exact plan artifact that was actually reviewed, reintroducing a review/apply consistency gap.
- ❌ Using one broad, all-powerful pipeline service identity across every environment and every team's pipelines, rather than scoping identities appropriately per pipeline/stage.
- **Common misconception:** "Having a CI/CD pipeline for infrastructure automatically means changes are safe." False — a pipeline that skips meaningful review (rubber-stamp approvals), applies freshly recomputed plans instead of reviewed ones, or uses an overly broad service identity provides much less real safety than its existence might suggest; the _quality and rigor_ of the pipeline's stages matters as much as having a pipeline at all.

## 17. Interview Questions with Model Answers

**🎯 Junior:** _"Why shouldn't engineers just run `terraform apply` or deploy CloudFormation changes directly from their own laptops against production?"_
**Model answer:** Doing that bypasses any consistent review process — there's no guarantee anyone else looked at the planned change before it happened, no reliable record of who approved it and why, and it relies entirely on that individual engineer's personal judgment and care in the moment, with no structural safety net. Routing changes through a pipeline instead means every production change goes through the same validate-plan-review-approve-apply sequence regardless of who's making it, with the actual deployment executed by a dedicated, appropriately scoped service identity rather than a person's own broad credentials, and with the review and approval steps creating both a genuine safety check and an audit trail.

**🎯 Intermediate:** _"Explain the 'apply the exact reviewed plan' best practice and what could go wrong without it."_
**Model answer:** When a plan is computed and reviewed — say, in a pull request — but the actual apply step recomputes a fresh plan at deployment time instead of using the saved plan artifact from review, there's a window where the two could differ. If someone else made a concurrent change to the same infrastructure, or if there's been any drift, the freshly recomputed plan at apply time might not be identical to what a human actually reviewed and approved. That means the deployment could execute something subtly different from what was signed off on. Saving the plan as an artifact during the review stage and then applying that exact saved plan file at apply time closes this gap, guaranteeing what gets approved is exactly what gets deployed.

**🎯 Senior:** _"Your organization's infrastructure pipeline has a production approval gate, but you discover the same engineer who writes most infrastructure changes is also the one who approves them. How would you address this, and why does it matter?"_
**Model answer:** This defeats the actual purpose of an approval gate, which is to have a second, independent set of eyes catch mistakes or issues the original author might have missed or been too close to the change to notice — self-approval provides essentially no additional safety beyond the original authoring, even though it looks like a gate exists on paper. Configure the pipeline or repository's branch protection rules to technically enforce separation of duties — requiring an approver who is not the PR's author — rather than relying on informal team norms, since informal norms are exactly what led to this gap in the first place. Also use this as an opportunity to check whether this pattern exists elsewhere in the organization's other pipelines, since a single-person infrastructure-change bottleneck like this is often symptomatic of a broader team-scaling or on-call coverage issue worth addressing directly, not just a pipeline configuration bug.

**🎯 Architect:** _"Design a CI/CD architecture for infrastructure changes across a 50-team organization, balancing organizational consistency (shared security standards, audit requirements) with each team's need for autonomy and fast iteration on their own infrastructure."_
**Model answer:** Build and centrally maintain a shared, reusable pipeline template — encoding the organization's mandatory stages (validate, security-scan, plan, review, gated production approval) and using appropriately scoped, per-team service identities — that every team's infrastructure repository consumes rather than each team building their own pipeline from scratch. This gives organizational consistency on the things that matter for audit and security (every team's production changes go through the same rigor, using the same underlying pipeline logic, so a compliance audit can point to one well-understood, centrally-owned pipeline definition rather than 50 different bespoke implementations) while still letting each team own their own actual infrastructure code, their own dev/staging environment iteration speed, and their own team-specific approvers for their own production gate, preserving genuine autonomy over their own domain. Version the shared pipeline template itself, so improvements (a new security scan, a process refinement) roll out to all 50 teams through a controlled update to the shared template rather than requiring 50 separate manual updates, and track a small set of central compliance metrics (approval-gate enforcement, service-identity scoping) across all teams' pipelines to catch drift from the intended standard, similar in spirit to the drift-detection and Conformance Pack governance patterns covered in Part 9 §2 and Part 8 §6.

## 18. Common Misconceptions

- "GitOps just means using Git for version control." False — GitOps specifically means the repository is the _deployment trigger and source of truth_, with automated reconciliation, not merely that configuration files happen to be stored in a Git repository somewhere.
- "A pipeline with an approval gate is automatically safe." False — the gate's actual effectiveness depends on genuine separation of duties, meaningful review (not rubber-stamping), and applying the exact reviewed plan; a poorly configured gate provides much less real safety than it appears to.

## 19. Key Takeaways

🔑 Infrastructure changes should flow through the same validate → plan → review → approve → apply pipeline discipline already applied to application code, using a dedicated, scoped service identity rather than individual credentials.
🔑 GitOps means the version-controlled repository is the actual deployment trigger and source of truth, with the pipeline reconciling deployed state to match it — not merely "we use Git."
🔑 Applying the exact reviewed plan artifact (not a freshly recomputed one) closes a real, subtle review/apply consistency gap.
🔑 Separation of duties (author ≠ approver) is a genuine, often compliance-driven control that must be technically enforced, not left to informal team norms.
🔑 Pre-deployment security scanning integrated into the pipeline shifts security checks earlier and cheaper than relying solely on post-deployment detection (Config Rules).

## 20. Related Concepts

- **CloudFormation, CDK, Terraform** (the tools whose commands are sequenced within these pipelines) → Part 9 §1-4.
- **AWS CodeArtifact & supply chain security** (§8a) — the closely related question of how build pipelines source and verify software package dependencies, alongside how they deploy infrastructure.
- **CloudTrail** (the independent audit trail of what the pipeline's service identity actually did) → Part 8 §5.
- **AWS Config** (post-deployment compliance detection, complementary to pre-deployment pipeline security scanning) → Part 8 §6.
- **Choosing the Right IaC Tool** (the final synthesis comparison, informed by everything in Part 9 §1-8) → next section, Part 9 §9.
