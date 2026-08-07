# Section 63 (Part 9): Folder/Project Vending Automation

## 1. Definition

**Plain language:** By the time an enterprise's landing zone ([Section 59](./Section-59-Part9-Landing-Zone-Architecture-Blueprints.md)) is live, the org structure, network, logging, and security foundations exist — but every new team that wants a project still needs one created correctly: right folder, right IAM, right network attachment, right budget alert, right logging sink inheritance. Doing that by hand, once, for the first project is fine. Doing it by hand for the two-hundredth project, consistently, under time pressure, from a different requester every time, is where landing zones quietly rot. "Project vending" is the automation that makes creating a correctly configured new project a repeatable, self-service, few-minutes operation instead of a manual checklist someone might skip a step on.

**Precise:** **Project vending** (also called a **project factory** pattern) is the practice of automating GCP project creation — via Terraform modules, Config Connector, or a CI/CD pipeline triggered by a lightweight request (a pull request, a form submission, an API call) — such that every new project is created with a consistent, codified set of baseline resources and configuration applied automatically, rather than each project being manually provisioned and configured one setting at a time.

## 2. Why It Exists / Problem It Solves

- [Section 59](./Section-59-Part9-Landing-Zone-Architecture-Blueprints.md).3 listed the CI/CD/automation project as the mechanism "behind project vending" without detailing how it actually works; this section is that detail.
- Manual project creation has two failure modes at scale: **drift** (project #150, created by a different engineer under deadline pressure, is missing the log sink, the budget alert, or a required IAM binding that project #1 had) and **latency** (a new team waits days for a platform team to manually work through a project-creation checklist, becoming a bottleneck exactly like the Shared VPC bottleneck project vending is designed to avoid — [Section 62](./Section-62-Part9-Shared-VPC-at-Scale.md).4.1 already assumes vending exists to pre-grant network access).
- Automating project creation solves both: the exact same Terraform module (or Config Connector manifest) runs for every project, so baseline configuration cannot drift between projects, and because it's a pipeline rather than a person, turnaround is minutes rather than days once the request is submitted.

## 3. Two Automation Mechanisms

### 3.1 Terraform Project-Factory Modules

- The dominant pattern: a reusable Terraform module (commonly based on, or directly using, Google's published `terraform-google-project-factory` module or an organization's own fork of it) takes a small set of inputs — project name, parent folder, environment, business unit, budget amount — and outputs a fully configured project.
- New projects are requested by adding a small block of configuration (often just a few lines referencing the shared module) to a Terraform repository, submitted as a pull request that the platform team reviews for the _inputs_ (is this the right folder, the right budget) rather than re-reviewing the entire baseline configuration every time, since the module itself already encodes the approved baseline.
- CI/CD (Cloud Build, [Section 50](../Part7/Section-50-Part7-Cloud-Build-CICD.md)) applies the Terraform on merge, so the new project exists and is fully baselined within minutes of the pull request being approved.

### 3.2 Config Connector

- **Config Connector** is a GKE-based Kubernetes add-on that lets GCP resources — including projects, IAM bindings, and log sinks — be represented and managed as Kubernetes Custom Resources, applied via `kubectl apply` or GitOps tooling (Flux, Argo CD) rather than a Terraform `apply` step.
- This is chosen over Terraform by organizations that are already Kubernetes-native in their platform tooling and want project provisioning to live in the same GitOps workflow, reconciliation loop, and drift-detection model as their application deployments, rather than introducing a second, separate Terraform-based control plane.
- Functionally the two approaches vend the same outcome (a correctly baselined project); the choice is about which control plane and workflow an organization's platform team already standardizes on, not a difference in what gets provisioned.

## 4. Standard Baseline Resources Applied to Every New Project

| Baseline Resource                         | Purpose                                                                                                                                                                                                                                                        | Related Section                                                                                      |
| ----------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Correct folder placement**              | Project lands under the right environment/business-unit folder, inheriting that folder's Organization Policy tier                                                                                                                                              | [Section 3](../Part1/Section-03-Part1-Resource-Hierarchy.md), 60                                     |
| **Default networking decision**           | Either explicitly attached to the correct Shared VPC host project's subnet with the correct `compute.networkUser` binding, or explicitly left network-less if the project doesn't need compute networking — never left with an unmanaged default auto-mode VPC | [Section 62](./Section-62-Part9-Shared-VPC-at-Scale.md), 60.4 (`compute.skipDefaultNetworkCreation`) |
| **Logging sink inheritance confirmation** | Verifies the project correctly inherits the organization-level aggregated log sink ([Section 61](./Section-61-Part9-Centralized-Logging-Security-Projects.md)) rather than needing a per-project sink                                                          | [Section 61](./Section-61-Part9-Centralized-Logging-Security-Projects.md)                            |
| **Baseline IAM bindings**                 | Standard groups (e.g., the requesting team's engineers as `roles/editor` scoped narrowly, a platform admin group, a break-glass emergency-access group) bound automatically, consistent across every project                                                   | [Section 35](../Part5/Section-35-Part5-IAM-Fundamentals-Members-Roles-Policies.md), 36               |
| **Budget alert**                          | A Cloud Billing budget with alert thresholds (e.g., 50%/90%/100% of a monthly cap) created automatically, so no project goes live without any cost visibility                                                                                                  | [Section 57](../Part8/Section-57-Part8-Cost-Optimization-FinOps.md)                                  |
| **Required APIs enabled**                 | The standard set of APIs every project needs (Cloud Resource Manager, IAM, Logging, Monitoring) enabled at creation, rather than each team discovering and enabling them individually the first time they hit a permission error                               | —                                                                                                    |
| **Labels/tags**                           | Standard labels (cost center, environment, business unit, owner) applied at creation, so cost reporting and asset inventory queries work correctly from day one                                                                                                | [Section 57](../Part8/Section-57-Part8-Cost-Optimization-FinOps.md)                                  |

> 💡 **Tip:** The budget alert and required baseline IAM bindings are the two items most commonly forgotten in manual project creation, precisely because neither blocks a project from _working_ — a project with no budget alert functions identically to one with a budget alert, until the month a cost anomaly goes unnoticed for weeks because nobody was watching. Automation is what guarantees these "silent until they matter" items are never skipped.

## 5. Architecture Diagram: Project Vending Flow

```
  Requesting team submits:
  a Terraform PR (or GitOps manifest) referencing the shared
  project-factory module, specifying: name, parent folder, env, budget
                    │
                    ▼
        Platform team reviews PR
        (reviews INPUTS only -- module already encodes
         the approved baseline, so review is fast)
                    │
                    ▼  merge
         CI/CD pipeline (Cloud Build) applies Terraform
         using the automation project's CI/CD service account
                    │
       ┌────────────┼─────────────────────────────┐
       ▼            ▼                             ▼
  New project    Baseline resources applied:      Attached to Shared VPC
  created in     - required APIs enabled          host project's correct
  correct        - baseline IAM bindings          subnet with scoped
  folder         - budget alert                   networkUser (Sec 62)
                 - confirmed log sink inheritance
                    │
                    ▼
       New project ready for team use
       (minutes after PR merge, fully baselined,
        no manual checklist step skipped)
```

## 6. Hands-On Example: Vending a New Project via Terraform Module

**Purpose:** Illustrate the minimal input a requesting team provides — the shared module handles every baseline resource internally.

```hcl
module "svc_orders_prod" {
  source           = "git::https://source.example.com/platform/project-factory.git//modules/service-project"
  project_id       = "svc-orders-prod-7c1e"
  folder_id        = "folders/333333333333"        # production folder
  billing_account  = "012345-6789AB-CDEF01"
  budget_amount    = 5000
  shared_vpc_host  = "host-prod"
  shared_vpc_subnet = "subnet-b"                    # team-orders subnet, Section 62
  labels = {
    team        = "orders"
    cost_center = "cc-4471"
    environment = "production"
  }
}
```

**Purpose:** Apply the module via CI/CD (illustrating what the pipeline runs after PR merge).

```bash
terraform apply -target=module.svc_orders_prod
```

**Expected output:**

```
module.svc_orders_prod.google_project.this: Creating...
module.svc_orders_prod.google_project_service.apis["logging.googleapis.com"]: Creating...
module.svc_orders_prod.google_billing_budget.this: Creating...
module.svc_orders_prod.google_compute_subnetwork_iam_member.network_user: Creating...
...
Apply complete! Resources: 14 added, 0 changed, 0 destroyed.
```

> 💡 **Tip:** Notice how little the requesting team's input block ([Section 63](./Section-63-Part9-Folder-Project-Vending-Automation.md).6's first example) needs to specify — a project ID, a folder, a budget, and a subnet reference. Every other baseline resource (API enablement, IAM bindings, log sink inheritance verification) is encoded inside the module itself, which is the entire point: the requester cannot forget a step that the module handles unconditionally.

## 7. Production & Enterprise Usage

- Mature project-vending setups include automated **drift detection** — a scheduled job comparing every existing project's actual configuration against what the factory module would currently produce, flagging projects that have drifted from baseline (e.g., a budget alert manually deleted, an IAM binding manually added outside the pipeline) for remediation.
- Module versioning matters as much as it does for the Enterprise Foundations Blueprint itself ([Section 59](./Section-59-Part9-Landing-Zone-Architecture-Blueprints.md).8) — enterprises pin the project-factory module to a specific released version per environment and roll out module updates deliberately (often nonproduction first) rather than having every new project automatically pick up an unreviewed change to the shared module.
- Self-service is bounded, not unlimited: the factory module typically enforces its own guardrails (e.g., refusing to create a project outside an approved folder, or capping the maximum budget a team can self-request without additional approval), so "self-service" means fast within approved bounds, not unrestricted project creation authority handed to every engineer.

## 8. Common Misconceptions

- **Misconception:** "Project vending means anyone can create a project with no oversight." False — the platform team still reviews every request's _inputs_ (folder, budget, network attachment), and the factory module itself enforces guardrails; what's automated is the _consistent application of baseline configuration_, not the removal of all review.
- **Misconception:** "Config Connector and Terraform are competing, mutually exclusive standards for project vending." They are alternative control planes producing the same outcome; the choice depends on whether an organization's platform tooling is already Kubernetes/GitOps-native or Terraform/CI-native, not on one being objectively superior for this use case.
- **Misconception:** "Once a project is vended correctly, it stays correct forever." False — manual out-of-band changes (someone deleting a budget alert, adding an ungoverned IAM binding directly in the console) can still drift a project from its vended baseline after creation, which is why drift detection is a standard companion practice, not an optional extra.

## 9. Comparison: GCP Project Vending vs. AWS Account Factory vs. Azure Subscription Vending

| Aspect                    | GCP                                                                                       | AWS                                                                                                                                          | Azure                                                                                                                                           |
| ------------------------- | ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| **Primary mechanism**     | Terraform project-factory module or Config Connector, self-hosted CI/CD pipeline          | **Account Factory for Terraform (AFT)** — an AWS-published Terraform framework integrating with Control Tower                                | **Subscription vending** — a Terraform/Bicep pattern (often via Azure landing zone accelerators) creating subscriptions under Management Groups |
| **Unit being vended**     | Project (under a folder)                                                                  | Full AWS account (under an OU)                                                                                                               | Subscription (under a Management Group)                                                                                                         |
| **Ownership model**       | You own and operate the factory pipeline entirely yourself                                | AFT is AWS-published and Control-Tower-integrated but still self-hosted/operated by the customer                                             | Vending templates are Microsoft-published patterns, self-hosted/operated by the customer                                                        |
| **Baseline enforcement**  | Whatever the organization's own module encodes (no enforced standard beyond what's built) | AFT provides a structured customization framework (account-customizations, global-customizations) with a more opinionated built-in structure | Landing zone accelerator provides Bicep/Terraform starting templates; enforcement is however the organization wires policy assignment           |
| **Isolation granularity** | Project-level (narrower than a full account)                                              | Full account-level (broadest isolation of the three)                                                                                         | Subscription-level (comparable granularity to an AWS account)                                                                                   |

> ⚠️ **Interview-relevant nuance:** All three clouds converge on the same underlying idea — codify a "new environment" as a reusable, automated Terraform pattern rather than a manual checklist — but the _unit_ being vended differs in isolation strength: a GCP project is a narrower isolation boundary than a full AWS account or Azure subscription, so a precise comparison should note this rather than treating "project vending," "Account Factory," and "subscription vending" as interchangeable in what they actually isolate.

## 10. Interview Questions

**🎯 Beginner:** _Why is manual project creation a problem at enterprise scale even if the first few projects were created correctly?_
**Model answer:** Manual creation depends on a person correctly following every step of a checklist every single time, and at scale — dozens or hundreds of projects, created by different people under different amounts of time pressure — it's realistic that some steps get skipped: a missing budget alert, a missing IAM binding, an inconsistent network attachment. This "drift" between projects is exactly what automated project vending prevents, since the same Terraform module or Config Connector manifest applies identically every time, and it also removes the latency of waiting for a platform team member to manually work through the checklist.

**🎯 Intermediate:** _What baseline resources should a project-factory module apply automatically, and why are budget alerts and IAM bindings specifically called out as easy to forget?_
**Model answer:** A well-designed module applies correct folder placement, required API enablement, baseline IAM bindings, a budget alert, Shared VPC subnet attachment with scoped `networkUser`, confirmation of log sink inheritance, and standard labels for cost/asset tracking. Budget alerts and baseline IAM bindings are specifically easy to forget in manual creation because neither one blocks the project from functioning day-to-day — a project without a budget alert works exactly the same as one with an alert, until a cost anomaly goes unnoticed for weeks because nobody was watching. Automation guarantees these "silent until they matter" items are never skipped, which is precisely the category of mistake manual checklists are worst at catching.

**🎯 Senior/Architect:** _How would you design drift detection for a fleet of vended projects, and what would you do when drift is found?_
**Model answer:** I would run a scheduled job (e.g., a nightly Cloud Build trigger) that performs a `terraform plan` (or a Config Connector reconciliation dry-run) against every existing vended project's known configuration compared to what the current factory module version would produce, surfacing any project where the plan shows a difference — a manually deleted budget alert, an IAM binding added outside the pipeline, a subnet attachment changed by hand. I would not auto-apply corrections blindly, since some "drift" might be a deliberate, approved exception ([Section 60](./Section-60-Part9-Organization-Policy-Hierarchy-Deep-Dive.md).3.3) rather than a mistake; instead I'd route detected drift to the platform team for triage, distinguishing legitimate documented exceptions from genuine configuration decay, and only auto-remediate categories of drift the organization has explicitly pre-approved for automatic correction (e.g., re-adding an accidentally deleted budget alert is usually safe to auto-fix; a changed IAM binding usually is not, since it might reflect a legitimate access change made through a different approved process). I'd also version-pin the factory module per environment so drift detection compares against the version a project was actually vended with, not whatever the module's latest `main` branch currently looks like, avoiding false-positive drift on every module update.

## 11. Key Takeaways

- 🔑 Project vending automates project creation via a Terraform project-factory module or Config Connector, applying a consistent baseline (folder, IAM, network, budget alert, logging inheritance, labels) to every new project rather than relying on a manual checklist.
- 🔑 The platform team's review shifts from re-verifying an entire baseline every time to reviewing just the request's inputs (folder, budget, subnet) — the module itself guarantees the baseline.
- 🔑 Terraform-based and Config Connector-based vending produce the same outcome; the choice depends on whether the organization's platform tooling is Terraform/CI-native or Kubernetes/GitOps-native.
- 🔑 Drift detection is the necessary companion to vending — a project vended correctly can still drift from baseline via out-of-band manual changes after creation.
- 🔑 GCP's project is a narrower isolation unit than AWS's Account Factory-vended account or Azure's vended subscription, even though all three automate the same underlying "new environment" pattern.

## 12. Related Concepts

Resource hierarchy and folder structure ([Section 3](../Part1/Section-03-Part1-Resource-Hierarchy.md)), Organization Policy tiers new projects inherit ([Section 60](./Section-60-Part9-Organization-Policy-Hierarchy-Deep-Dive.md)), Shared VPC subnet attachment automated at vending time ([Section 62](./Section-62-Part9-Shared-VPC-at-Scale.md)), centralized logging sink inheritance ([Section 61](./Section-61-Part9-Centralized-Logging-Security-Projects.md)), cost/budget alerting ([Section 57](../Part8/Section-57-Part8-Cost-Optimization-FinOps.md)), and the landing zone's CI/CD automation project this pipeline runs from ([Section 59](./Section-59-Part9-Landing-Zone-Architecture-Blueprints.md).3, [Section 50](../Part7/Section-50-Part7-Cloud-Build-CICD.md)) all connect directly to project vending.
