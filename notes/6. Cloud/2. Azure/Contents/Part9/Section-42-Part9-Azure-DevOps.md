# Section 42 — Azure DevOps (Boards, Repos, Pipelines, Artifacts)

**Part 9: DevOps & Infrastructure as Code | Section 42 of 70 (First Section of Part 9)**
**Prerequisites:** Section 33–34 (Docker, ACR — build artifacts), Section 9 (Managed Identities/Service Principals), Section 8 (RBAC)
**Leads into:** Section 43 (ARM Templates), Section 44 (Bicep), Section 45 (Terraform on Azure), Section 46 (CI/CD Pipeline Patterns, GitHub Actions with Azure)

---

## 42.1 Introduction and Scope

This section covers Azure DevOps as an integrated suite of five services — Boards, Repos, Pipelines, Artifacts, and Test Plans — with primary emphasis on Repos, Pipelines, and Artifacts, since these are the components most directly relevant to the infrastructure/deployment automation focus of this roadmap's Part 9. Boards and Test Plans are covered at an appropriate but lighter depth, since they address project-management and testing-process concerns adjacent to, rather than central to, the DevOps engineering focus of this material.

🔑 **Key Takeaway:** Azure DevOps is a _toolchain_, not a single monolithic product — each of its five services can be adopted independently (many organizations use Azure Pipelines with GitHub Repos, for example, rather than the full integrated suite), and understanding the boundary and integration points between the services is as important as understanding any one service in isolation.

---

## 42.2 What Is Azure DevOps

### 42.2.1 Definition

**Plain language:** Azure DevOps is a suite of development collaboration tools covering the full software delivery lifecycle — planning and tracking work (Boards), storing and versioning code (Repos), automating build/test/deployment (Pipelines), managing package/binary artifacts (Artifacts), and managing test plans/execution (Test Plans) — usable together as an integrated platform or adopted piecemeal alongside other tools.

**Precise definition:** Azure DevOps is Microsoft's cloud-hosted (Azure DevOps Services) or self-hosted (Azure DevOps Server) suite of five integrated services supporting Agile planning, source control, continuous integration/continuous delivery, package management, and manual/automated testing.

### 42.2.2 The Five Services

| Service        | Purpose                                                                                                                                                                              |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Boards**     | Agile work tracking — work items (epics, features, user stories, tasks, bugs), Kanban boards, sprint planning, backlogs, and dashboards.                                             |
| **Repos**      | Git (and legacy Team Foundation Version Control, largely superseded by Git for new projects) source code repositories with pull request workflows, branch policies, and code review. |
| **Pipelines**  | CI/CD automation — build, test, and deployment pipelines, defined as YAML (or via a classic visual designer), supporting both Azure and non-Azure/multi-cloud deployment targets.    |
| **Artifacts**  | Package management — hosts NuGet, npm, Maven, Python, and universal package feeds, for sharing internally built packages/dependencies across projects and teams.                     |
| **Test Plans** | Manual and exploratory test case management, plus integration with automated test results from Pipelines.                                                                            |

### 42.2.3 Azure DevOps vs. GitHub (Both Microsoft-Owned)

⚠️ **Warning:** since Microsoft owns both Azure DevOps and GitHub, a frequent point of confusion (and a legitimate architecture decision point) is choosing between them. They are not the same product: GitHub emphasizes open-source-friendly social coding, GitHub Actions for CI/CD, and broader developer-community features; Azure DevOps emphasizes integrated enterprise Agile planning (Boards) alongside its own CI/CD (Pipelines) and is often preferred in enterprises with established Microsoft-ecosystem tooling investment and specific Agile process/reporting needs Boards addresses natively. Many organizations use a hybrid: GitHub for source control (Repos) combined with Azure Pipelines for CI/CD, or vice versa — this section's CI/CD material (Pipelines) applies conceptually to either combination, and Section 46 covers GitHub Actions as a direct alternative/complement.

---

## 42.3 Azure Repos

### 42.3.1 Git Fundamentals Applied (Brief — Full Git Coverage Is a Separate Topic)

Azure Repos hosts standard Git repositories; this roadmap assumes no dedicated prior Git-specific section exists yet, so this subsection notes the concepts specifically relevant to enterprise Azure DevOps usage without re-teaching Git from first principles (a natural candidate for a future "Git" topic roadmap in this same knowledge base series, referenced as a related topic in 42.14).

### 42.3.2 Branch Policies

- **Definition:** rules enforced on a specific branch (typically the main/release branch) requiring certain conditions before changes can be merged — a minimum number of reviewer approvals, successful build validation (a Pipeline run triggered automatically on the pull request), linked work items, and comment resolution.
- **Why they exist:** without enforced policies, code quality and review discipline depend entirely on individual developer/team discipline; branch policies make specific quality gates mandatory and unbypassable (for non-administrator users) at the platform level — directly parallel in philosophy to Pod Security Admission (Section 36.6.3) enforcing hardening as cluster policy rather than developer discretion, now applied to source control.
- **Build validation policy specifically:** requires a specified Pipeline to run and succeed against the proposed merge before it can complete — this is the mechanism connecting Repos to Pipelines, ensuring code cannot reach the protected branch without passing automated checks.

### 42.3.3 Pull Request Workflow

- A pull request (PR) proposes merging changes from a source branch into a target branch, triggering configured branch policies, enabling threaded code review comments, and (once approved and passing policies) completing the merge — the standard collaborative code-review mechanism, with Azure Repos' specific implementation supporting features like squash merge options, automatic work-item linking (connecting a PR to its originating Boards work item), and PR templates.

---

## 42.4 Azure Pipelines

### 42.4.1 Definition

**Plain language:** Azure Pipelines automates the process of building, testing, and deploying code — triggered automatically by a code change (or on a schedule, or manually), running a defined sequence of steps on managed or self-hosted compute, producing artifacts and/or deploying to target environments.

**Precise definition:** Azure Pipelines is a cloud-based CI/CD service that automates build, test, and deployment workflows, defined declaratively in YAML (the modern, recommended approach) or via the legacy classic visual designer, executing on Microsoft-hosted or self-hosted **agents**.

### 42.4.2 Core Concepts

| Term                   | Definition                                                                                                                                                                                                                                                                                                                                                                                                      |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Pipeline**           | The overall automated workflow definition, typically stored as a YAML file (`azure-pipelines.yml`) alongside the source code it builds — directly applying the "infrastructure/configuration as version-controlled code" principle already established for Kubernetes manifests (Section 35.5.3) and Logic Apps definitions (Section 39.4.1).                                                                   |
| **Stage**              | A major logical division of a pipeline (e.g., Build, Test, Deploy-to-Dev, Deploy-to-Prod), which can have dependencies on other stages and approval gates between them.                                                                                                                                                                                                                                         |
| **Job**                | A unit of work within a stage, executing on a single agent; multiple jobs within a stage can run in parallel across multiple agents.                                                                                                                                                                                                                                                                            |
| **Step / Task**        | An individual action within a job — running a script, or invoking a prebuilt **task** (a reusable, parameterized unit of pipeline functionality, e.g., `AzureCLI@2`, `Docker@2`, `PublishBuildArtifacts@1`).                                                                                                                                                                                                    |
| **Agent**              | The compute (VM or container) that actually executes a pipeline job — either Microsoft-hosted (ephemeral, maintained by Microsoft, offered in various OS images) or **self-hosted** (a customer-managed and -maintained VM or on-premises machine registered as an agent, needed for scenarios requiring specific software, network access to private resources, or cost optimization at high pipeline volume). |
| **Trigger**            | The condition causing a pipeline to run — a push to a specific branch (CI trigger), a pull request (PR trigger), a schedule, or a manual/API-invoked run.                                                                                                                                                                                                                                                       |
| **Service connection** | A stored, reusable authentication configuration (e.g., to an Azure subscription via a Service Principal or Workload Identity Federation, to ACR, Section 34) that pipeline tasks reference to authenticate to external systems without embedding credentials directly in the pipeline YAML.                                                                                                                     |

### 42.4.3 Example Pipeline: Build and Push a Container Image to ACR

```yaml
trigger:
  branches:
    include: [main]

pool:
  vmImage: "ubuntu-latest"

stages:
  - stage: Build
    jobs:
      - job: BuildAndPush
        steps:
          - task: Docker@2
            inputs:
              containerRegistry: "my-acr-service-connection"
              repository: "webapp"
              command: "buildAndPush"
              Dockerfile: "**/Dockerfile"
              tags: |
                $(Build.BuildId)
                latest

  - stage: DeployToAKS
    dependsOn: Build
    jobs:
      - deployment: DeployWebapp
        environment: "production"
        strategy:
          runOnce:
            deploy:
              steps:
                - task: KubernetesManifest@1
                  inputs:
                    action: "deploy"
                    manifests: "k8s/deployment.yaml"
                    containers: "myregistry.azurecr.io/webapp:$(Build.BuildId)"
```

- **Line-by-line, non-obvious points:**
  - `containerRegistry: 'my-acr-service-connection'` references a pre-configured service connection rather than embedding ACR credentials directly — connecting straight back to Section 34.4.2's Managed Identity/Service Principal-based authentication guidance, now applied at the pipeline level.
  - Tagging with `$(Build.BuildId)` (a unique, auto-incrementing pipeline run identifier) alongside `latest` directly implements the digest/immutable-tag-adjacent traceability guidance from Section 33.5.6 — every build produces a uniquely identifiable, traceable image tag, not just a mutable `latest` overwrite.
  - The `DeployToAKS` stage's `environment: 'production'` reference enables **environment-level approval gates** (42.4.4) — this stage will not execute until any configured approval for the `production` environment is satisfied, regardless of the prior stage's success.
  - `dependsOn: Build` makes the deployment stage's execution explicitly conditional on the build stage succeeding — stages execute in dependency order, not simply top-to-bottom by default (a common point of confusion, worth being precise about).

### 42.4.4 Environments and Approval Gates

- **Environments** are a Pipelines construct representing a logical deployment target (e.g., `dev`, `staging`, `production`), against which deployment history and approval requirements can be configured, independent of the pipeline YAML itself.
- **Approval gates:** a required manual approval (by a specified individual or group) before a deployment to a given environment proceeds — the standard mechanism for enforcing human sign-off before production deployment specifically, while allowing lower environments (dev, staging) to deploy fully automatically without gating.
- 💡 **Tip:** this pattern — full CI automation through build/test, automatic deployment to non-production environments, and a manual approval gate specifically before production — is a widely adopted, sensible default balancing deployment velocity against production change-management risk, though the specific gating requirements (who approves, whether additional automated checks like a canary analysis also gate production) should be tailored to an organization's actual risk tolerance and regulatory requirements rather than treated as one-size-fits-all.

### 42.4.5 Templates and Pipeline Reuse

- Pipeline YAML supports **templates** — reusable, parameterized YAML fragments referenced from multiple pipelines — addressing the real-world problem of near-duplicate pipeline definitions proliferating across many repositories/teams as an organization's pipeline count grows, allowing common patterns (e.g., a standard build-and-scan sequence) to be defined once and referenced everywhere, with organization-specific mandatory steps (e.g., a required security scan) centrally maintainable rather than needing to be manually replicated and kept in sync across every team's individual pipeline.

---

## 42.5 Azure Artifacts

### 42.5.1 Definition

**Plain language:** Azure Artifacts is a package repository service — a place to publish and consume internally built packages (NuGet, npm, Maven, Python packages, or arbitrary "universal packages") within an organization, functioning as a private equivalent to public package registries like npm's registry or NuGet.org.

### 42.5.2 Why It Exists

- **Sharing internal code as versioned dependencies:** rather than copy-pasting shared code across repositories, or vendoring it via Git submodules (both error-prone at scale), teams publish shared internal libraries as versioned packages consumed via standard package-manager tooling (`npm install`, `dotnet add package`), exactly as they would consume any public package — but from a private, organization-controlled feed.
- **Upstream sources / proxying public registries:** Artifacts feeds can be configured with an "upstream source" pointing to a public registry (npmjs.org, NuGet.org), caching packages the organization actually consumes — providing resilience against public registry outages, a single governed point for scanning/vetting which external package versions are actually in use, and reduced external bandwidth, directly parallel in purpose to `az acr import`'s pattern of mirroring approved public container images into a controlled private registry (Section 34.10).
- **Universal Packages:** a feed type for arbitrary binary artifacts not fitting a language-specific package format (e.g., a build's compiled output, ML model files) — providing versioned artifact storage for scenarios beyond the standard language package managers.

### 42.5.3 Relationship to ACR (Section 34)

🔑 **Key Takeaway:** Azure Artifacts and Azure Container Registry serve analogous purposes for different artifact types — Artifacts for language-ecosystem packages (NuGet, npm, Maven, etc.) and general binary artifacts, ACR specifically for OCI container images. A mature CI/CD pipeline commonly publishes to both: application dependencies/shared libraries to Artifacts, and the final container image to ACR — understanding this division (rather than conflating "package registry" as a single undifferentiated concept) is relevant both practically and for precise interview answers.

---

## 42.6 Azure Boards (Brief Coverage)

### 42.6.1 Core Concepts

- **Work item types:** hierarchical Agile planning artifacts — typically Epic → Feature → User Story/Product Backlog Item → Task, plus Bug as a parallel type — configurable per the specific process template (Basic, Agile, Scrum, CMMI) an Azure DevOps project uses.
- **Boards (Kanban) and Sprints:** visual, drag-and-drop work tracking (Kanban board for continuous flow, Sprint/Scrum board for time-boxed iterations), with configurable columns/swimlanes reflecting a team's actual workflow states.
- **Traceability to code:** work items can be linked to commits, pull requests, and pipeline builds — providing an audit trail from a planned unit of work through to the actual code change and deployment that implemented it, valuable both for project visibility and for compliance/audit requirements in regulated environments.

### 42.6.2 Why This Is Covered Lightly in This Roadmap

Boards addresses Agile project-management process, a discipline with its own substantial depth (estimation techniques, Scrum/Kanban methodology specifics, portfolio management) that is adjacent to, rather than core to, this roadmap's DevOps/infrastructure/cloud-engineering focus — covered here at the level needed to understand its role in the Azure DevOps suite and its integration points with Repos/Pipelines (work-item-linked commits and PRs), without duplicating a full Agile-methodology curriculum.

---

## 42.7 Security and Access Control

### 42.7.1 Azure DevOps Permissions Model

- Azure DevOps has its own permissions system (organization, project, and object-level — e.g., specific repository or pipeline permissions), layered similarly in spirit to the Kubernetes-RBAC-vs-Azure-RBAC distinction from Section 36.5.1: Azure DevOps access is managed within Azure DevOps' own permission model (often synchronized with Entra ID group membership for identity, but the actual permission grants are Azure-DevOps-native), and is a **separate system** from Azure RBAC governing the Azure resources a pipeline might ultimately deploy to.

### 42.7.2 Service Connections and Least Privilege

- Service connections (42.4.2) authenticating a pipeline to an Azure subscription should be scoped to the minimum necessary permission — a pipeline that only needs to deploy to a specific resource group should use a Service Principal/Workload Identity scoped to that resource group (Section 8's RBAC scoping concepts), not a subscription-wide `Owner` or `Contributor` role, following the same least-privilege discipline established throughout this roadmap.
- **Workload Identity Federation for service connections:** modern Azure DevOps supports federated credentials for Azure service connections (directly parallel to the GitHub Actions OIDC federation pattern noted in Section 34.4.2), avoiding a stored Service Principal secret entirely — the currently preferred pattern over classic secret-based Service Principal connections, consistent with the Managed-Identity-and-federation preference established repeatedly across this roadmap.

### 42.7.3 Pipeline Security: Preventing Unreviewed Code From Running With Elevated Permissions

⚠️ **Warning:** a pipeline triggered by a pull request from a fork or an untrusted branch, if allowed to run with the same service connection permissions as a trusted main-branch pipeline, creates a supply-chain risk: an attacker submitting a malicious PR could potentially exfiltrate secrets or abuse the pipeline's Azure permissions before any human review occurs. Azure Pipelines provides settings to restrict this (e.g., requiring approval before a fork-originated PR's pipeline run executes, or restricting which branches/triggers can access sensitive service connections) — a genuine, actively exploited real-world CI/CD attack pattern across the industry (not unique to Azure DevOps), worth explicit awareness and deliberate configuration rather than assuming default settings are automatically safe.

---

## 42.8 Production and Enterprise Usage Patterns

- **Multi-stage pipelines as the standard, not classic release pipelines:** modern Azure DevOps guidance favors YAML-based multi-stage pipelines (as shown in 42.4.3) over the legacy classic (UI-designer-based) release pipeline model, for the version-control/reviewability benefits of pipeline-as-code — directly paralleling this roadmap's recurring "manage it as version-controlled configuration, not manual UI edits" principle (Sections 35.5.3, 39.4.1).
- **Pipeline templates enforcing organizational standards (42.4.5):** enterprises commonly mandate that all pipelines extend from a centrally maintained template enforcing required steps (security scanning, required approvals, tagging conventions) — providing governance without requiring every individual team to manually replicate compliance logic.
- **Integration with the container/registry ecosystem (Sections 33–34):** the vast majority of Azure DevOps pipelines in a modern Azure-centric organization exist specifically to build, test, and push container images to ACR and deploy them to AKS/App Service/Container Apps — making Sections 33–34's material and this section's Pipelines material two halves of one practical, frequently-interview-tested workflow.

---

## 42.9 Troubleshooting Reference

| Symptom                                                                          | Likely Cause                                                                                                                                                  | Diagnostic Step                                                                                                                     |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Pipeline fails at a service connection-authenticated step                        | Service connection credentials expired (classic Service Principal secret) or insufficient RBAC scope                                                          | Verify service connection validity; consider migrating to Workload Identity Federation (42.7.2) to eliminate secret expiry entirely |
| PR cannot be completed despite passing all visible checks                        | A branch policy requirement not yet satisfied (e.g., a required reviewer group, work-item linking requirement) not obviously visible in the PR UI at a glance | Review the target branch's full policy configuration in Repos settings                                                              |
| Deployment stage never starts despite the build stage succeeding                 | An environment approval gate (42.4.4) is pending, or a `dependsOn` misconfiguration                                                                           | Check the environment's pending approvals; review stage dependency configuration                                                    |
| A malicious or unexpected pipeline run occurred from an external contribution    | Insufficient fork/untrusted-branch pipeline restrictions (42.7.3)                                                                                             | Review and tighten fork PR build settings and service connection access restrictions                                                |
| Package consumed from an Artifacts feed is an unexpectedly old/different version | Upstream source caching behavior, or feed view/scope misconfiguration                                                                                         | Review the feed's upstream source configuration and the specific feed view being consumed from                                      |

---

## 42.10 Best Practices Checklist

- [ ] Pipelines defined as YAML, version-controlled alongside source code, not managed solely via the classic visual designer.
- [ ] Branch policies enforced on protected branches, including mandatory build validation.
- [ ] Service connections scoped to least privilege and, where supported, using Workload Identity Federation rather than stored secrets.
- [ ] Production deployment stages gated behind explicit environment approvals, distinct from fully automated lower-environment deployment.
- [ ] Fork/untrusted-branch pipeline execution explicitly reviewed and restricted to prevent unreviewed-code supply-chain risk.
- [ ] Shared pipeline logic centralized via templates rather than duplicated across many individual pipeline files.
- [ ] Container images pushed to ACR (Section 34) and internal language packages published to Artifacts, with the distinction between the two artifact types understood and applied correctly.

---

## 42.11 Common Misconceptions

- "Azure DevOps and GitHub are essentially the same product since Microsoft owns both." _Correction:_ they have genuinely distinct strengths and typical usage patterns (42.2.3), and are frequently combined rather than treated as strict alternatives.
- "A service connection with broad subscription-level permissions is simpler and therefore fine for most pipelines." _Correction:_ this directly violates least-privilege (42.7.2) and expands the blast radius of any pipeline compromise; scoping to the minimum necessary resource group/permission is the correct default, not an optional hardening step.
- "If my main branch has protection policies, my pipelines are safe from malicious code execution." _Correction:_ fork-originated or untrusted-branch PR pipeline runs can execute _before_ a PR is merged/reviewed if not explicitly restricted (42.7.3) — branch protection on the target branch does not by itself prevent this distinct risk.

---

## 42.12 Interview Questions (Consolidated)

**Beginner:** "What are the five services that make up Azure DevOps, and what does each do?"
_Model answer:_ Boards for Agile work tracking; Repos for Git source control with pull requests and branch policies; Pipelines for CI/CD build/test/deployment automation; Artifacts for hosting internal package feeds (NuGet, npm, Maven, etc.); and Test Plans for manual/exploratory test case management. They can be adopted together as an integrated suite or independently alongside other tools.

**Intermediate:** "Explain the difference between a Pipeline stage and a job, and why does the distinction matter?"
_Model answer:_ a stage is a major logical division of a pipeline (e.g., Build, Deploy-to-Dev, Deploy-to-Prod), which can depend on other stages and be gated by environment approvals; a job is a unit of work within a stage that executes on a single agent, with multiple jobs in a stage able to run in parallel across multiple agents. The distinction matters for both execution behavior (jobs within a stage can parallelize; stages execute according to their dependency graph, not simply top-to-bottom) and for where approval gates and environment-level governance actually apply — gates attach to stage-to-environment deployments, not to individual jobs.

**Senior:** "A team's Azure Pipelines service connection uses a classic Service Principal with a client secret. Explain the operational and security risks of this configuration, and what you would recommend instead."
_Model answer:_ operationally, a client secret has an expiration date and must be manually rotated before it expires — a common source of pipeline failures when rotation is forgotten or mismanaged, and the secret itself, if scoped too broadly (a frequent accompanying issue, 42.7.2), represents a standing credential that, if leaked (e.g., accidentally logged, or exfiltrated via a compromised pipeline step), grants an attacker Azure access for as long as it remains valid and unrevoked. The recommended fix is migrating to Workload Identity Federation for the service connection, which eliminates the stored secret entirely — Azure DevOps and Azure Entra ID establish trust via a federated credential configuration, and short-lived tokens are issued per pipeline run without any long-lived secret ever being stored or capable of leaking in the first place — directly analogous to the same Managed Identity/federation preference established for AKS-to-ACR authentication (Section 34.4.2) and AKS Workload Identity (Section 36.5.4), now applied to the CI/CD platform's own authentication to Azure.
_What the interviewer is probing:_ recognizing this as the same recurring "eliminate stored secrets in favor of federated/managed identity" pattern that spans the entire roadmap, correctly applied to the Azure DevOps-specific mechanism, rather than treating it as an isolated fact.

**Architect / Scenario:** "Design a CI/CD pipeline security posture for an organization that accepts external contributions via pull requests from forked repositories, given the real risk of malicious PR-triggered pipeline runs."
_Model answer:_ configure Azure Pipelines to require explicit approval before a fork-originated PR's pipeline build runs at all (42.7.3), ensuring a human reviews the proposed code changes before any pipeline execution occurs, rather than allowing automatic execution on every PR regardless of origin. Ensure the pipeline used for fork/external PR validation is scoped with no access to sensitive service connections (or a heavily restricted, read-only/build-only service connection) — a build-and-test-only pipeline for external contributions should have no legitimate need for a service connection capable of deploying to production Azure resources at all, following least-privilege scoping (42.7.2) specifically calibrated to what an untrusted-origin pipeline run should be capable of doing even in a worst-case compromise scenario. Separately, the trusted main-branch pipeline (running only after a PR has been reviewed, approved, and merged) can retain the broader service-connection permissions needed for actual deployment, since by that point the code has passed human review. This two-tier trust model — untrusted/external pipeline runs with minimal blast radius, trusted post-merge pipeline runs with the permissions actually needed for deployment — directly addresses the specific risk named in the scenario.
_What the interviewer is probing:_ the ability to design a concrete, two-tier trust architecture addressing a named, real supply-chain risk, rather than a generic "enable security settings" answer — this is a genuinely current, actively relevant industry concern (open-source and external-contribution supply-chain attacks), and interviewers value candidates who have internalized it as a design principle rather than an isolated checkbox.

---

## 42.13 Key Takeaways Summary

🔑 Azure DevOps is a toolchain of five independently adoptable services (Boards, Repos, Pipelines, Artifacts, Test Plans) — not a monolithic single product, and frequently combined with non-Microsoft tools (e.g., GitHub Repos with Azure Pipelines).

🔑 Modern Azure Pipelines guidance favors YAML-based, version-controlled multi-stage pipelines over the legacy classic visual-designer release pipeline model — a specific instance of this roadmap's recurring "configuration as version-controlled code" principle.

🔑 Service connections should use least-privilege scoping and, where supported, Workload Identity Federation rather than stored Service Principal secrets — the same Managed-Identity-and-federation pattern established repeatedly across Sections 34, 36, and now 42.

🔑 Azure Artifacts (language packages/binaries) and Azure Container Registry (Section 34, OCI images) serve analogous but distinct artifact-management roles within a complete CI/CD pipeline.

🔑 Fork-originated/untrusted-branch pipeline execution is a genuine, actively exploited supply-chain risk requiring deliberate restriction — not a theoretical concern, and a strong signal of security maturity when correctly designed around.

---

## 42.14 Related Concepts and What Comes Next

- **Section 43 — ARM Templates (next):** the native Azure Infrastructure-as-Code format that Azure Pipelines (and Azure DevOps generally) commonly deploys as part of a pipeline's infrastructure-provisioning stage.
- **Section 44 — Bicep:** the modern, more ergonomic authoring layer over ARM Templates, also commonly deployed via Azure Pipelines tasks.
- **Section 45 — Terraform on Azure:** an alternative, multi-cloud-capable IaC tool, also integrable with Azure Pipelines.
- **Section 46 — CI/CD Pipeline Patterns, GitHub Actions with Azure:** directly extends this section's CI/CD material with broader pattern coverage and GitHub Actions as a specific alternative/complementary tool, revisiting 42.2.3's Azure DevOps vs. GitHub comparison in more depth.
- **Section 34 (prerequisite, completed):** ACR, the container registry target for the majority of production Azure Pipelines container-build workflows (42.4.3, 42.8).
- **A future "Git Fundamentals" topic (candidate for a separate roadmap in this knowledge base series):** full Git-specific depth (branching strategies, rebasing, merge conflict resolution) was intentionally not duplicated here per 42.3.1, and remains a natural standalone topic outside this Azure-focused roadmap's current scope.

---

_End of Section 42. Next: Section 43 — ARM Templates._
