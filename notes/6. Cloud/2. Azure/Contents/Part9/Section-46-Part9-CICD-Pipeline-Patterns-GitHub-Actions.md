# Section 46 — CI/CD Pipeline Patterns, GitHub Actions with Azure

**Part 9: DevOps & Infrastructure as Code | Section 46 of 70 (Final Section of Part 9)**
**Prerequisites:** Section 42 (Azure DevOps Pipelines), Section 43–45 (ARM/Bicep/Terraform), Section 33–34 (Docker/ACR)
**Leads into:** Part 10 — Monitoring & Observability (Section 47, Azure Monitor fundamentals)

---

## 46.1 Introduction and Scope

This final section of Part 9 covers two things: (1) CI/CD pipeline **patterns** that generalize across whichever specific tool implements them (Azure Pipelines, GitHub Actions, or others) — environment promotion strategies, deployment strategies (blue-green, canary, rolling), and GitOps; and (2) **GitHub Actions** specifically as Azure's other first-class-supported CI/CD platform, with a direct, concrete comparison against Azure Pipelines (Section 42) and coverage of its Azure-specific authentication and deployment integration.

🔑 **Key Takeaway:** the deployment _patterns_ covered in this section (blue-green, canary, GitOps, environment promotion) are tool-agnostic architectural concepts — they apply identically whether implemented in Azure Pipelines, GitHub Actions, or any other CI/CD platform. Understanding them at this level, decoupled from any specific tool's syntax, is what actually transfers across jobs, teams, and technology changes over a career — the tool-specific YAML syntax is comparatively replaceable knowledge.

---

## 46.2 Environment Promotion Strategies

### 46.2.1 The Core Pattern: Build Once, Promote Unchanged

Directly extending the "build once, deploy the same artifact to every environment" principle established repeatedly across this roadmap (Section 33.12, Section 34.10, Section 43.3.2's parameter-file pattern), a mature CI/CD pipeline builds exactly one artifact (a container image with a specific digest, a compiled package, a Bicep-compiled ARM deployment) and **promotes that same, unmodified artifact** through a sequence of environments (dev → staging → production), rather than rebuilding for each environment.

### 46.2.2 Why Rebuilding Per Environment Is an Anti-Pattern

⚠️ **Warning:** rebuilding the deployment artifact separately for each environment — even from the identical source commit — reintroduces exactly the "it works in the environment it was built for" risk containers and immutable artifacts exist to eliminate (Section 33.2.2): a different base image patch version pulled at a different build time, a different dependency resolution outcome, or any other build-time non-determinism means the artifact actually tested in staging is not guaranteed to be byte-identical to the artifact deployed to production, undermining the entire premise of "what we tested is what we're shipping." Environment-specific _configuration_ (connection strings, feature flags, scaling parameters) should vary between environments — the artifact itself should not.

### 46.2.3 Promotion Pipeline Structure

```
[Build Stage]
   → produces one artifact (image digest / package version), pushed once to ACR/Artifacts
        │
        ▼
[Deploy to Dev]  (automatic, no approval gate)
        │
        ▼
[Automated Tests against Dev]
        │
        ▼
[Deploy to Staging]  (automatic, or lightweight approval)
        │
        ▼
[Automated/Manual Validation against Staging]
        │
        ▼
[Deploy to Production]  (manual approval gate, Section 42.4.4)
   — deploys the EXACT SAME artifact digest/version validated in every prior stage
```

- This structure directly reuses the multi-stage pipeline and environment-approval-gate mechanics from Section 42.4.3–42.4.4, with the specific added discipline of parameterizing _only_ configuration (via parameter files, Section 43.3.2, or environment-specific variable groups) between stages, never rebuilding the underlying artifact.

---

## 46.3 Deployment Strategies

### 46.3.1 Why Deployment Strategy Is a Distinct Concern From Environment Promotion

Environment promotion (46.2) answers "in what order do environments receive a new version"; **deployment strategy** answers a different question: "within a single environment, how does traffic transition from the old version to the new version" — a genuinely separate axis of the overall release process, both of which a mature pipeline must address.

### 46.3.2 Rolling Deployment

- **Definition:** gradually replaces instances of the old version with the new version, a subset at a time, until the new version fully replaces the old — this is the default behavior of a Kubernetes Deployment's `RollingUpdate` strategy (Section 35.5.2), and conceptually applies equally to App Service deployment slots swapping gradually, or VM Scale Set instance-by-instance upgrades.
- **Trade-off:** simple, requires no additional infrastructure beyond what's already running the application, but both old and new versions serve live traffic simultaneously during the rollout window — requiring the application to tolerate this (e.g., a database schema change must remain compatible with both the old and new application version for the duration of the rollout, a real constraint worth naming explicitly rather than assuming rolling deployments are always trivially safe).

### 46.3.3 Blue-Green Deployment

- **Definition:** two complete, independent environments ("blue" = currently live, "green" = the new version) run simultaneously; the new version is fully deployed and validated in the green environment while blue continues serving all live traffic, and cutover happens by switching traffic (e.g., via a load balancer, Application Gateway, or DNS change) from blue to green essentially instantaneously, rather than gradually.
- **Why it exists:** eliminates the "old and new versions serving simultaneously" concern from rolling deployment (46.3.2) — the cutover is a single, near-instantaneous switch, and if a problem is discovered post-cutover, traffic can be switched back to blue immediately, providing a very fast, low-risk rollback mechanism (as long as blue remains available/un-decommissioned for a period after cutover).
- **Trade-off:** requires running two complete environments simultaneously (at least briefly, during the validation-and-cutover window), a real cost/infrastructure consideration compared to rolling deployment's incremental-replacement approach — Azure App Service's deployment slots feature (Section 13) is a direct, built-in implementation of this pattern at the PaaS level, and AKS can implement it via two parallel Deployments/Services with a traffic-switching mechanism (an Ingress or Service selector change, Section 36.3).

### 46.3.4 Canary Deployment

- **Definition:** the new version is deployed to a small subset of production infrastructure/traffic first (e.g., 5% of requests), monitored closely for errors/performance regressions, and — only if that canary subset performs acceptably — gradually expanded to serve an increasing percentage of traffic until it fully replaces the old version; if a problem is detected at any stage, the rollout halts and the canary traffic is reverted.
- **Why it exists:** provides real production traffic validation (something staging environments, however well-configured, cannot perfectly replicate) while limiting the blast radius of a genuinely bad release to a small, bounded fraction of actual users — a materially different risk profile from both rolling deployment (100% eventual exposure with no explicit small-scale validation gate) and blue-green (100% exposure immediately upon cutover, validated pre-cutover but not against live production traffic specifically).
- **Implementation mechanisms on Azure:** Azure Front Door and Application Gateway (Section 24–25) support weighted traffic splitting across backend pools, directly enabling percentage-based canary routing; in AKS specifically, a service mesh (not yet covered in this roadmap, a candidate future topic) or Ingress-level traffic-splitting annotations provide finer-grained canary control than a plain Kubernetes Service alone offers.

### 46.3.5 Comparison Table

| Strategy   | Traffic Cutover                                   | Rollback Speed                         | Infrastructure Cost                     | Production-Traffic Validation                                                 |
| ---------- | ------------------------------------------------- | -------------------------------------- | --------------------------------------- | ----------------------------------------------------------------------------- |
| Rolling    | Gradual, instance-by-instance                     | Moderate (must roll back the same way) | Low (no duplicate environment)          | Indirect (partial exposure during rollout, not a deliberate small-scale gate) |
| Blue-Green | Instantaneous, at cutover                         | Very fast (switch back to blue)        | Higher (two full environments briefly)  | None before cutover; full exposure immediately after                          |
| Canary     | Gradual, percentage-based, deliberately monitored | Fast (halt/revert canary traffic)      | Moderate (canary subset infrastructure) | Explicit, deliberate, bounded-risk real production traffic validation         |

🎯 **Interview Tip:** the strongest deployment-strategy answer names the specific risk tolerance and infrastructure-cost trade-off driving the choice for a given scenario, rather than asserting one strategy as universally best — e.g., "a low-traffic internal tool" may reasonably accept rolling deployment's simplicity, while "a high-traffic, revenue-critical consumer service" more often justifies canary's deliberate, monitored, bounded-exposure validation despite its added complexity.

---

## 46.4 GitOps

### 46.4.1 Definition

**Plain language:** GitOps is a pattern where a Git repository is the single source of truth for a system's desired state (application manifests, infrastructure configuration), and an automated agent continuously reconciles the actual running system to match what's declared in that repository — rather than a pipeline pushing changes imperatively to the target environment.

**Precise definition:** GitOps is an operational model applying Git as the single source of truth for declarative infrastructure and application configuration, combined with an automated, continuously reconciling agent (running inside or with access to the target environment) that pulls and applies the desired state from the repository, rather than a CI/CD pipeline directly pushing changes to the target.

### 46.4.2 Push-Based vs. Pull-Based Deployment: The Key Distinction

- **Traditional (push-based) pipeline deployment:** a CI/CD pipeline (Section 42.4, or GitHub Actions, 46.6) authenticates directly to the target environment (AKS, Azure resources) and pushes the change — the pipeline holds credentials with write access to production, and the deployment happens as a discrete pipeline-run event.
- **GitOps (pull-based) deployment:** an agent running _inside_ the target environment (e.g., Flux or Argo CD running as a controller inside an AKS cluster, Section 35–37) continuously polls or watches the Git repository, and pulls/applies any detected changes itself — no external pipeline holds direct write credentials to the cluster; the only "credential" flowing outward is the repository being readable by the in-cluster agent, and deployment happens via continuous reconciliation rather than a discrete push event.
- 🔑 **Key Takeaway — the security implication:** GitOps' pull-based model means the production environment's write credentials never need to leave the environment itself (no external CI/CD system holds a credential capable of directly modifying production) — a meaningfully different, and for many organizations preferable, security posture compared to a traditional pipeline that must be granted (and carefully scoped/secured, per Section 42.7.2's least-privilege guidance) direct write access to production from outside the cluster.

### 46.4.3 GitOps and Kubernetes/AKS Specifically

- GitOps is particularly well-suited to Kubernetes because Kubernetes' own object model is already fully declarative (Section 35.5) — a GitOps agent's job is simply "ensure the cluster's actual objects match what's declared in the repository," directly reusing Kubernetes' own reconciliation-loop philosophy (Section 35.3.2) at the level of "which manifests exist" rather than only "how many replicas of an already-deployed manifest exist."
- **Flux and Argo CD** are the two most widely used GitOps agents/controllers for Kubernetes, both available as AKS add-ons or self-installed into a cluster — continuously reconciling cluster state against a configured Git repository, with drift (a manual `kubectl` change made outside the Git-declared configuration) detected and reverted, directly analogous in philosophy (though implemented at a different layer) to Terraform's drift-reconciliation behavior covered in Section 45.3.4.

### 46.4.4 GitOps Trade-offs

- **Advantage:** stronger security posture (no external push credentials), a genuinely complete audit trail (every change is a Git commit, inherently reviewed via the same PR process as any other code change, Section 42.3.3), and automatic self-healing against drift.
- **Trade-off:** deployment is no longer a discrete, immediately-observable pipeline-run event — it happens on the agent's reconciliation cadence (near-immediate for a well-configured agent, but genuinely a different operational model to reason about and monitor than "watch the pipeline run finish"), and adopting GitOps requires running and maintaining the reconciliation agent itself as additional in-cluster infrastructure, a real operational cost to weigh against the security/audit benefits.

---

## 46.5 GitHub Actions: Core Concepts

### 46.5.1 Definition

**Plain language:** GitHub Actions is GitHub's native CI/CD automation platform — workflows defined as YAML files stored directly in the repository (`.github/workflows/`), triggered by repository events (a push, a pull request, a schedule, or a manual dispatch), executing a sequence of steps on GitHub-hosted or self-hosted runners.

### 46.5.2 Core Concepts (Direct Comparison to Azure Pipelines' Equivalents)

| GitHub Actions Term | Azure Pipelines Equivalent (Section 42.4.2) | Notes                                                                                                                                                                                                                                                                             |
| ------------------- | ------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Workflow**        | Pipeline                                    | The overall YAML-defined automation, triggered by repository events.                                                                                                                                                                                                              |
| **Job**             | Job                                         | A unit of work executing on a single runner; multiple jobs can run in parallel or with explicit dependency ordering (`needs:`).                                                                                                                                                   |
| **Step**            | Step/Task                                   | An individual action within a job — running a shell command, or invoking a reusable **Action**.                                                                                                                                                                                   |
| **Action**          | Task                                        | A reusable, shareable unit of workflow functionality, published to the GitHub Marketplace or referenced directly from a repository — directly analogous to an Azure Pipelines task, with a similarly large ecosystem of both Microsoft-published and community-published actions. |
| **Runner**          | Agent                                       | The compute executing a job — GitHub-hosted (ephemeral, various OS images) or self-hosted, directly analogous to Azure Pipelines' hosted vs. self-hosted agent distinction (Section 42.4.2).                                                                                      |
| **Environment**     | Environment                                 | A named deployment target supporting required reviewers/approval gates before a job targeting it executes — directly analogous to Azure Pipelines' environment approval gates (Section 42.4.4).                                                                                   |
| **Secret**          | Variable group / Key Vault-linked variable  | Encrypted, repository- or organization-scoped configuration values referenced in workflows without being exposed in logs.                                                                                                                                                         |

### 46.5.3 Example Workflow: Build and Push to ACR, Deploy to AKS

```yaml
name: Build and Deploy

on:
  push:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - name: Azure Login (OIDC federation)
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}

      - name: Build and push image
        run: |
          az acr build --registry myregistry --image webapp:${{ github.sha }} .

  deploy:
    needs: build
    runs-on: ubuntu-latest
    environment: production
    steps:
      - uses: actions/checkout@v4
      - name: Azure Login (OIDC federation)
        uses: azure/login@v2
        with:
          client-id: ${{ secrets.AZURE_CLIENT_ID }}
          tenant-id: ${{ secrets.AZURE_TENANT_ID }}
          subscription-id: ${{ secrets.AZURE_SUBSCRIPTION_ID }}
      - name: Set AKS context
        uses: azure/aks-set-context@v4
        with:
          resource-group: myResourceGroup
          cluster-name: myAKSCluster
      - name: Deploy to AKS
        uses: azure/k8s-deploy@v5
        with:
          images: "myregistry.azurecr.io/webapp:${{ github.sha }}"
          manifests: "k8s/deployment.yaml"
```

- **`needs: build`:** the GitHub Actions equivalent of Azure Pipelines' `dependsOn` (Section 42.4.3) — explicit job-dependency ordering, not assumed from file position.
- **`environment: production`:** triggers any configured required-reviewer approval gate for the `production` environment before this job executes — directly equivalent to Section 42.4.4's environment approval gate pattern, just expressed in GitHub Actions' own syntax.
- **`azure/login@v2` with `client-id`/`tenant-id`/`subscription-id` (no client secret):** this is **OIDC federation** — GitHub Actions' workflow identity federates directly with Microsoft Entra ID via a trust relationship configured on an app registration, issuing short-lived tokens per workflow run with **no stored Azure credential/secret in GitHub at all** — the GitHub Actions-specific implementation of the same Workload Identity Federation pattern already established as the preferred approach for Azure DevOps service connections (Section 42.7.2) and referenced generally in Section 34.4.2.
- **`${{ github.sha }}`:** the GitHub Actions equivalent of Azure Pipelines' `$(Build.BuildId)` (Section 42.4.3) — a unique, traceable identifier used for image tagging, directly implementing the same digest/tag traceability principle from Section 33.5.6.

---

## 46.6 GitHub Actions vs. Azure Pipelines: Decision Framework

### 46.6.1 When the Choice Is Already Made For You

- If source code already lives in GitHub, GitHub Actions is the natural, lowest-friction CI/CD choice (no separate platform/login/permission model to manage), and vice versa for Azure Repos and Azure Pipelines — for many organizations, this single factor (where does the code already live) settles the decision without further analysis being necessary.

### 46.6.2 When a Genuine Choice Exists

| Factor                                                                                                                                    | Favors Azure Pipelines                                                                                                                    | Favors GitHub Actions                                                                                                                      |
| ----------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| Existing Azure DevOps investment (Boards, established pipeline templates, Section 42.8)                                                   | ✓                                                                                                                                         |                                                                                                                                            |
| Need for integrated Agile work-item tracking (Boards) tightly linked to pipeline runs                                                     | ✓                                                                                                                                         |                                                                                                                                            |
| Open-source project / broad external contributor community                                                                                |                                                                                                                                           | ✓ (GitHub's broader community/marketplace ecosystem, and native fork-PR workflow familiarity for external contributors)                    |
| Organization-wide preference for GitHub as the primary developer platform (increasingly common given Microsoft's own strategic direction) |                                                                                                                                           | ✓                                                                                                                                          |
| Very large marketplace of community-maintained, narrowly specific integrations/actions                                                    |                                                                                                                                           | ✓ (generally the larger, more actively growing ecosystem at present — verify current relative ecosystem size, as this continues to evolve) |
| Enterprise governance/compliance tooling maturity specific to on-premises/self-hosted Azure DevOps Server scenarios                       | ✓ (Azure DevOps Server, the self-hosted variant, has no direct GitHub Actions equivalent in the same self-hosted-enterprise-server sense) |                                                                                                                                            |

🎯 **Interview Tip:** as with the Terraform-vs-Bicep decision (Section 45.6.2), the strongest answer avoids declaring one platform universally better and instead names the specific organizational factors (where code already lives, existing tooling investment, community/contribution model, self-hosted enterprise requirements) that would actually drive the decision for a given organization.

---

## 46.7 Security Considerations Specific to CI/CD Pipeline Patterns

### 46.7.1 Recap and Extension of Section 42.7.3's Fork-PR Risk

The fork-originated/untrusted-PR pipeline execution risk covered for Azure Pipelines in Section 42.7.3 applies equally, and is if anything more prominently discussed, in the GitHub Actions ecosystem specifically — GitHub Actions provides explicit workflow permission settings (`pull_request` vs. `pull_request_target` triggers carry meaningfully different, easily-misunderstood security implications regarding whether secrets are exposed to a fork-originated workflow run) that require deliberate, informed configuration, following the same "untrusted-origin pipeline runs should have minimal blast radius" principle established in Section 42.7.3, now with GitHub Actions' own specific trigger-type nuances to understand correctly.

### 46.7.2 OIDC Federation as the Now-Standard Pattern Across Both Platforms

🔑 **Key Takeaway:** by this point in the roadmap, the "eliminate stored long-lived secrets in favor of federated/Managed Identity-based authentication" pattern has now been established identically across every relevant integration point covered: ACR authentication (Section 34.4.2), AKS Workload Identity (Section 36.5.4), Functions-to-Azure-service authentication (Section 38.7.2), Logic Apps connector authentication (Section 39.7), Event Grid/Hubs/Service Bus authentication (Section 40.8), APIM-to-backend authentication (Section 41.7.2), Azure DevOps service connections (Section 42.7.2), and now GitHub Actions' OIDC federation (46.5.3) — this is not a collection of unrelated tips but one consistent, cross-cutting architectural principle applied identically at every layer of the Azure ecosystem, and being able to articulate it as a single unifying pattern (rather than a list of disconnected facts) is a strong signal of genuinely internalized, rather than memorized, understanding.

---

## 46.8 Production and Enterprise Usage

- **Combining patterns:** a mature production pipeline (in either Azure Pipelines or GitHub Actions) typically combines environment promotion (46.2), a chosen deployment strategy (46.3, often canary or blue-green specifically for production given its lower risk-exposure profile), and — for AKS-hosted workloads specifically — increasingly a GitOps model (46.4) for the actual cluster-facing deployment step, with the CI pipeline responsible only for building/testing/pushing the artifact and updating the GitOps repository's manifest reference, while the in-cluster GitOps agent handles the actual pull-based deployment.
- **Multi-tool, multi-platform reality:** many real organizations use a genuinely mixed toolchain — GitHub for source control and CI, Azure Pipelines for certain deployment stages requiring Azure DevOps-specific integration, Terraform for multi-cloud infrastructure and Bicep for Azure-only infrastructure, Flux/Argo CD for GitOps-based Kubernetes deployment — and the ability to reason about how these pieces fit together (rather than assuming any single organization uses one tool exclusively for everything) reflects realistic production practice more accurately than a single idealized toolchain.

---

## 46.9 Troubleshooting Reference

| Symptom                                                                                           | Likely Cause                                                                                                                                                                                     | Diagnostic Step                                                                                                                                                                                             |
| ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| GitHub Actions workflow fails to authenticate to Azure despite correct-looking OIDC configuration | Federated credential's subject claim configuration on the Entra ID app registration doesn't match the actual workflow's repository/branch/environment context                                    | Review the federated credential's configured subject against the exact workflow trigger context (branch, environment, or PR) that produced the failing run                                                  |
| A canary deployment shows no clear signal to promote or roll back                                 | Insufficient or improperly scoped monitoring/alerting on the canary traffic subset specifically (as opposed to aggregate metrics across old and new versions combined)                           | Ensure metrics/alerting are split by version/deployment specifically, not only aggregated cluster-wide (directly connecting to Part 10's upcoming Azure Monitor/Application Insights material)              |
| GitOps agent shows persistent drift/reconciliation loop, repeatedly reverting a change            | A manual `kubectl` change is being made outside the Git-declared configuration and conflicting with the agent's reconciliation (directly analogous to Section 45.3.4's Terraform drift behavior) | Make the intended change in the Git repository itself, not directly against the cluster, and let the GitOps agent apply it through the normal reconciliation path                                           |
| Blue-green cutover causes a brief service disruption despite being described as "instantaneous"   | Connection draining/in-flight-request handling not correctly configured on the traffic-switching mechanism (Load Balancer/Application Gateway/DNS TTL)                                           | Review the specific cutover mechanism's connection-draining and TTL configuration; a DNS-based cutover in particular can have real propagation delay depending on client-side and resolver caching behavior |

---

## 46.10 Best Practices Checklist

- [ ] Exactly one artifact built and promoted unchanged through every environment, with only configuration varying per environment.
- [ ] Deployment strategy (rolling, blue-green, canary) chosen deliberately based on the specific workload's risk tolerance and infrastructure-cost trade-off, not left at a tool's default without consideration.
- [ ] GitOps considered specifically for AKS-hosted production workloads, weighing its security/audit-trail benefits against its additional operational surface area.
- [ ] OIDC/federated credential authentication used for both Azure Pipelines and GitHub Actions Azure integration, consistent with the roadmap-wide Managed Identity/federation preference.
- [ ] Fork-originated/untrusted-branch pipeline execution risk explicitly reviewed and restricted in whichever platform (Azure Pipelines or GitHub Actions) is in use.
- [ ] Canary/blue-green deployments backed by version-specific (not only aggregate) monitoring, enabling a genuine promote-or-rollback signal.
- [ ] Manual changes to GitOps-managed or Terraform-managed environments avoided, given both tools' drift-reconciliation behavior reverting them.

---

## 46.11 Common Misconceptions

- "Blue-green deployment eliminates all deployment risk since the cutover is instantaneous." _Correction:_ it eliminates the "old and new versions serving simultaneously" concern specifically, but the cutover itself can still surface issues only visible under real cutover conditions (connection draining, DNS propagation, 46.9), and running two full environments has a real infrastructure cost — it reduces certain risks, not all risk universally.
- "GitOps means you no longer need a CI pipeline at all." _Correction:_ GitOps replaces the _deployment push_ step specifically with pull-based reconciliation; a CI pipeline (build, test, push the artifact, update the GitOps repository's manifest reference) is still needed — GitOps changes how the final deployment step happens, not whether CI is needed at all (46.8).
- "Canary deployment is strictly better than blue-green or rolling, so it should always be used." _Correction:_ canary's monitoring/traffic-splitting infrastructure requirements are genuinely more complex to set up and operate correctly than rolling or blue-green; the right choice depends on the workload's actual risk profile and the organization's operational maturity to support canary's requirements correctly (46.3.5's trade-off table applies).

---

## 46.12 Interview Questions (Consolidated)

**Beginner:** "What is the difference between rolling, blue-green, and canary deployment strategies?"
_Model answer:_ rolling deployment gradually replaces old-version instances with new-version instances, with both versions serving traffic simultaneously during the transition. Blue-green runs two complete environments and switches traffic between them nearly instantaneously at cutover, with no gradual mixed-traffic period. Canary deploys the new version to a small percentage of production traffic first, closely monitors it, and gradually expands only if it performs acceptably, providing the most deliberate, bounded-risk real-production-traffic validation of the three.

**Intermediate:** "Explain the fundamental difference between a traditional push-based deployment pipeline and a GitOps pull-based model, and why this distinction matters for security."
_Model answer:_ in a push-based pipeline, the CI/CD system itself authenticates directly to the target environment and pushes changes, meaning it must hold credentials with write access to that environment. In GitOps' pull-based model, an agent running inside the target environment continuously watches a Git repository and pulls/applies changes itself — no external CI/CD system needs direct write credentials to the environment at all. This matters for security because it meaningfully reduces the blast radius of a compromised CI/CD system: in the push model, compromising the pipeline's credentials grants direct write access to production; in the GitOps model, compromising the pipeline (which now only needs to push to a Git repository, not the production environment itself) does not directly grant infrastructure access, since the actual write action is performed by the in-cluster agent based on what it reads from Git, itself subject to normal PR review before merge.

**Senior:** "A team's canary deployment process rolled out a new version to 5% of traffic, showed no alerts for 30 minutes, and was then promoted to 100% — after which a serious bug affecting a specific, less common user workflow was discovered. What likely went wrong with the canary process itself, not just the code?"
_Model answer:_ this points to either insufficient canary traffic volume/duration to statistically capture the specific less-common workflow (if that workflow only occurs for a small fraction of overall traffic, a 5% canary sample for 30 minutes may simply not have included enough instances of that specific workflow to surface the bug at all — a real statistical-coverage limitation of canary deployments that scales with how rare the affected pattern is relative to overall traffic), or insufficient monitoring granularity (aggregate error-rate alerting across the canary population may not have been broken down by specific user workflow/feature area, meaning even if the bug did occur within the canary window, it may not have been visible in the specific metrics being watched, connecting to the general monitoring-granularity point in 46.9's troubleshooting table). The recommended fix going forward is not necessarily abandoning canary deployment, but rather explicitly identifying which specific workflows/features carry disproportionate risk and ensuring the canary process either runs long enough / at sufficient volume to reasonably capture rare-but-critical workflows, or is supplemented with targeted automated testing specifically covering those workflows before promotion, rather than relying on canary's general traffic sampling alone to catch every category of regression.
_What the interviewer is probing:_ the ability to reason precisely about canary deployment's actual statistical/coverage limitations rather than treating it as an infallible safety net — recognizing that "no alerts during canary" is a probabilistic signal bounded by sample size and monitoring granularity, not an absolute guarantee, is a meaningfully senior-level distinction.

**Architect / Scenario:** "Design a complete CI/CD and deployment strategy for a revenue-critical, high-traffic e-commerce checkout service running on AKS, addressing artifact promotion, deployment strategy, and the push-vs-GitOps decision."
_Model answer:_ build the container image exactly once per source commit, tagged/pinned by digest (Section 33.5.6/46.2.1), and promote that identical artifact through dev → staging → production environments (46.2.3) with only configuration varying. Given the "revenue-critical, high-traffic" characterization, use a **canary deployment strategy** (46.3.4) for production specifically — the deliberate, bounded-risk, real-traffic validation is well justified by the cost of a bad release reaching 100% of checkout traffic immediately, and the organization's presumed scale/traffic volume mitigates canary's statistical-coverage limitation discussed in the prior answer (higher absolute traffic volume means even a modest canary percentage captures a meaningful, statistically useful sample more quickly than for a lower-traffic service). For the actual deployment mechanism, adopt **GitOps** (46.4) with a controller such as Argo CD or Flux running in the AKS cluster, reconciling against a Git repository whose manifests are updated by the CI pipeline after a successful build — providing the security benefit of no external CI system holding direct production-write credentials (46.4.2), a fully auditable change history via Git/PR review for every deployment change to this revenue-critical system, and the canary rollout itself can be expressed and progressively adjusted through Git-committed configuration changes (e.g., adjusting a traffic-split percentage in the GitOps-managed manifests) rather than an imperative pipeline-driven traffic shift, keeping the entire rollout process within the same auditable, reviewed Git-based change trail. Production deployment progression (canary percentage increases) should be gated by explicit, version-specific monitoring (46.9) rather than a fixed timer alone, given the coverage limitations discussed above.
_What the interviewer is probing:_ the ability to synthesize artifact promotion, deployment strategy, and the push-vs-GitOps architectural decision into one coherent design justified by the specific business characteristics named in the prompt (revenue-critical, high-traffic), rather than defaulting to a generic "best practices" checklist disconnected from the actual scenario's risk profile.

---

## 46.13 Key Takeaways Summary

🔑 Deployment patterns (environment promotion, rolling/blue-green/canary strategies, GitOps) are tool-agnostic architectural concepts that transfer across Azure Pipelines, GitHub Actions, or any other CI/CD platform — understanding them at this level is more durable knowledge than any single tool's specific YAML syntax.

🔑 "Build once, promote the same artifact unchanged through every environment" is a foundational discipline this section directly extends from Sections 33.12/34.10/43.3.2, with only configuration (never the artifact itself) varying per environment.

🔑 GitOps' pull-based model fundamentally changes the security posture of deployment by removing the need for any external CI/CD system to hold direct production-write credentials — a meaningfully different architecture from traditional push-based pipelines, not merely a stylistic preference.

🔑 OIDC/federated credential authentication is now established as a single, consistent, cross-cutting pattern applied identically across every Azure integration point covered in this entire roadmap (46.7.2) — recognizing it as one unifying principle, rather than a list of disconnected tool-specific tips, reflects genuine architectural understanding.

🔑 Canary deployment's safety guarantee is probabilistic and bounded by traffic volume/duration and monitoring granularity, not an infallible safety net — a nuance worth understanding precisely for both real incident analysis and interview-level reasoning.

---

## 46.14 Part 9 Wrap-Up: Consolidated Dependency Recap

```
Section 42 (Azure DevOps: Boards, Repos, Pipelines, Artifacts)
        │  Git workflow, branch policies, pipeline stages/environments/approvals
        ▼
Section 43 (ARM Templates)
        │  native IaC execution format; what-if preview
        ▼
Section 44 (Bicep)
        │  modern authoring layer compiling to ARM JSON
        ▼
Section 45 (Terraform on Azure)
        │  alternative, multi-cloud-capable IaC with its own state model
        ▼
Section 46 (CI/CD Pipeline Patterns, GitHub Actions)  ← this section
   tool-agnostic deployment patterns; GitHub Actions as an alternative/complementary CI/CD platform
```

Part 9 is now complete. Every deployment of every Azure resource type covered across Parts 1–8 of this roadmap — VMs, App Service, Functions, AKS, databases, networking — is, in a mature production environment, provisioned via the IaC tools from Sections 43–45 and deployed via the CI/CD patterns and platforms from Sections 42 and 46, rather than manual Portal-driven changes.

---

## 46.15 Related Concepts and What Comes Next

- **Section 47 — Azure Monitor Fundamentals (Part 10, next):** the observability foundation that makes deployment-strategy monitoring gates (46.3.4's canary promotion signal, 46.9's version-specific monitoring requirement) actually implementable in practice — this section's monitoring references throughout (canary alerting, GitOps drift detection) are fully realized once Part 10's observability material is covered.
- **Section 42 (prerequisite, completed):** Azure Pipelines' stage/environment/approval-gate mechanics this section's patterns were expressed against directly.
- **Section 35–37 (prerequisite, completed):** AKS Deployment rolling-update mechanics (46.3.2) and the GitOps-in-AKS pattern (46.4.3) built directly on that Part's foundation.
- **Section 33.5.6/34.10 (prerequisite, completed):** the digest-pinning and artifact-promotion principles this section's environment-promotion pattern (46.2) directly extends.
- **A future "service mesh" topic** (candidate for this knowledge base series, referenced in 46.3.4): fine-grained traffic-splitting for canary deployments in AKS beyond basic Ingress-level capability was noted as outside this roadmap's current scope, and remains a natural related-topic extension.

---

_End of Section 46. End of Part 9 — DevOps & Infrastructure as Code. Next: Section 47 — Azure Monitor Fundamentals (Part 10 — Monitoring & Observability)._
