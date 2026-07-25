# Section 52 (Part 7): Terraform on GCP / Deployment Manager

## 52.1 Definition

**Plain language:** Instead of clicking through the console or typing individual `gcloud` commands to create resources, Infrastructure as Code (IaC) means writing a text file that _describes_ the infrastructure you want, then running a tool that reads the file and makes the real cloud environment match it — repeatably, reviewably, and version-controlled like any other code.

**Precise:** On GCP, infrastructure is most commonly declared using **Terraform** (an open-source, multi-cloud IaC tool from HashiCorp/OpenTofu) via its **Google provider**, which translates HashiCorp Configuration Language (HCL) resource blocks into GCP API calls, tracking real-world resource state in a **state file** (commonly stored in a GCS backend for team use). **Deployment Manager** is GCP's own native, YAML/Python/Jinja2-based IaC service, offered directly by Google but now considered largely legacy in favor of Terraform.

## 52.2 Why It Exists / Problem It Solves

Manually clicking through the console or running one-off `gcloud` commands to build infrastructure has serious, compounding problems at any real scale:

- **No repeatability.** Recreating an identical environment (a new region, a disaster-recovery copy, a second customer's isolated stack) means either remembering every manual step or writing brittle imperative scripts that don't handle "this resource already exists" gracefully.
- **No review process.** Console clicks leave no diff to review before they happen — a mistaken firewall rule or IAM grant goes live immediately, with no peer-review gate analogous to a code pull request.
- **No source of truth.** Without a declarative file describing intended state, "what does our infrastructure actually look like right now, and why" becomes tribal knowledge or requires manually reconciling the console against memory.

IaC tools solve this by making infrastructure _declarative and versioned_: the desired end-state lives in a file, checked into the same version control as application code, reviewed via pull request, and applied idempotently — running the same configuration twice produces no unwanted changes if nothing changed.

## 52.3 Core Concepts

### 52.3.1 Terraform Google Provider Fundamentals

The **Google provider** (`hashicorp/google`, and `hashicorp/google-beta` for preview features) is a plugin that translates Terraform resource blocks into GCP API calls:

```hcl
terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = "my-project-id"
  region  = "us-central1"
}

resource "google_storage_bucket" "demo" {
  name          = "my-toolkit-tf-demo-bucket"
  location      = "US-CENTRAL1"
  force_destroy = false

  uniform_bucket_level_access = true
}
```

The core Terraform workflow is **write → `terraform plan` (preview the diff) → `terraform apply` (make reality match the config)**. Terraform compares its **state** against the actual GCP resources and the desired configuration on every run, computing the minimal set of create/update/destroy operations needed.

### 52.3.2 State Management (GCS Backend)

Terraform's **state file** (`terraform.tfstate`) is the record mapping configuration resource names to real-world resource IDs, and is the single most operationally sensitive artifact in a Terraform workflow — losing it means Terraform no longer knows what it manages. On GCP, teams almost universally configure a **GCS backend**:

```hcl
terraform {
  backend "gcs" {
    bucket = "my-org-terraform-state"
    prefix = "envs/prod"
  }
}
```

A GCS backend provides:

- **Remote, shared state** — every team member and CI pipeline reads/writes the same state, rather than each engineer holding a local, divergent copy.
- **State locking** — GCS backend uses object generation preconditions to prevent two concurrent `apply` operations from corrupting state simultaneously.
- **Versioning** — enabling object versioning (Section 11) on the state bucket lets a corrupted or bad state be rolled back to a prior version.

> ⚠️ **Interview-relevant nuance:** The state file contains resource attribute values in plaintext, which can include sensitive data (e.g., a generated database password set via a resource argument). State buckets should always have restrictive IAM, and sensitive values should ideally come from Secret Manager (Section 38) referenced at apply time rather than stored as literal Terraform variables.

### 52.3.3 Modules and Workspaces

- **Modules** are reusable, parameterized bundles of resources (e.g., a "standard VPC" module used identically across every project) — GCP's own `terraform-google-modules` GitHub organization publishes Google-maintained modules for common patterns (network, project-factory, GKE).
- **Workspaces** (or, more commonly at scale, entirely separate state files per environment/directory) isolate state between environments (dev/staging/prod) so applying to one never risks touching another.

### 52.3.4 Deployment Manager (Native, Largely Legacy)

**Deployment Manager** is GCP's own first-party IaC service, predating widespread Terraform adoption on GCP. Configurations are written in YAML, optionally templated with Python or Jinja2 for reusable logic:

```yaml
resources:
  - name: demo-bucket
    type: storage.v1.bucket
    properties:
      location: US-CENTRAL1
```

Deployment Manager is GCP-only (no multi-cloud support), has a smaller ecosystem of reusable templates than Terraform's module registry, and Google itself now generally steers customers toward Terraform for new work — Deployment Manager is mostly encountered maintaining older deployments rather than chosen for new ones.

## 52.4 Architecture Diagram

```
   Engineer writes .tf files  ──►  git commit / pull request (peer review)
                                         │
                                         ▼
                              CI pipeline (Cloud Build, Section 50)
                                         │
                          ┌──────────────┴───────────────┐
                          ▼                              ▼
                  terraform plan                  terraform apply
                  (preview diff, no changes)       (on merge / approval)
                          │                              │
                          ▼                              ▼
              ┌───────────────────────┐          ┌─────────────────────┐
              │  GCS Backend          │◄────────►│  Real GCP Resources │
              │  (state file, locked, │  reads/  │  (VPCs, GKE, IAM,   │
              │   versioned)          │  writes  │   buckets, ...)     │
              └───────────────────────┘          └─────────────────────┘
```

## 52.5 Comparison vs. AWS CloudFormation/CDK and Azure ARM/Bicep

| Concept                    | GCP (Terraform Google Provider)                  | GCP Deployment Manager               | AWS CloudFormation / CDK                                                                                              | Azure ARM / Bicep                                                              |
| -------------------------- | ------------------------------------------------ | ------------------------------------ | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Native/multi-cloud         | Multi-cloud (third-party, HashiCorp/OpenTofu)    | GCP-native only                      | AWS-native only (CloudFormation); CDK compiles to CloudFormation                                                      | Azure-native only                                                              |
| Config language            | HCL (declarative)                                | YAML + Jinja2/Python templates       | JSON/YAML (CloudFormation); TypeScript/Python/Java/C# (CDK, imperative-feeling but synthesizes declarative templates) | JSON (ARM) or Bicep (declarative DSL that compiles to ARM JSON)                |
| State tracking             | Explicit state file (GCS/other backend)          | Managed by the service itself        | Managed by the service itself (CloudFormation stack)                                                                  | Managed by the service itself (ARM deployment history)                         |
| Vendor status for new work | Google's generally recommended path for new IaC  | Legacy, not recommended for new work | Actively developed, first-party recommended                                                                           | Actively developed, first-party recommended (Bicep now preferred over raw ARM) |
| Reusable component model   | Modules (community + `terraform-google-modules`) | Templates (smaller ecosystem)        | Nested stacks / CDK constructs                                                                                        | Bicep modules / ARM linked templates                                           |
| Drift detection            | `terraform plan` shows drift vs. state           | Limited                              | CloudFormation drift detection                                                                                        | ARM "what-if"                                                                  |

## 52.6 Hands-On Examples

**Initialize a Terraform project with a GCS backend (Beginner):**

```bash
terraform init
```

**Purpose:** Downloads the Google provider plugin and configures the GCS backend for remote state.
**Expected output (abbreviated):**

```
Initializing the backend...
Successfully configured the backend "gcs"!
Initializing provider plugins...
Terraform has been successfully initialized!
```

**Preview changes (Beginner):**

```bash
terraform plan -out=tfplan
```

**Expected output (abbreviated):**

```
Terraform will perform the following actions:

  # google_storage_bucket.demo will be created
  + resource "google_storage_bucket" "demo" {
      + name     = "my-toolkit-tf-demo-bucket"
      ...
    }

Plan: 1 to add, 0 to change, 0 to destroy.
```

**Apply the reviewed plan (Intermediate):**

```bash
terraform apply tfplan
```

**Purpose:** Applies exactly the previously reviewed plan — a common CI/CD safeguard, since applying a _stored_ plan (rather than re-planning at apply time) guarantees no drift snuck in between review and apply.

**Import an existing resource into Terraform management (Intermediate-Advanced):**

```bash
terraform import google_storage_bucket.demo my-toolkit-tf-demo-bucket
```

**Purpose:** Brings a bucket created manually (console or `gcloud`) under Terraform's management without recreating it, a common step when adopting IaC for a previously manually managed environment.

## 52.7 Production & Enterprise Usage

- **CI/CD-driven apply, never local apply against prod:** Enterprises route all `terraform plan`/`apply` for shared environments through Cloud Build (Section 50) or another CI system, with `apply` gated behind PR approval, so no engineer's laptop ever runs `terraform apply` directly against production state.
- **State bucket hardening:** The GCS state bucket for production is typically its own tightly IAM-scoped bucket with versioning and, often, a retention policy, since it is one of the highest-value targets for both accidental deletion and credential exposure.
- **Landing-zone modules:** Large organizations standardize on internal Terraform modules (often based on `terraform-google-modules`) for repeated patterns — project creation, Shared VPC attachment, standard IAM bindings — so every new project starts from an approved, consistent baseline (foreshadowing Part 9's landing zone content, Section 59).
- **Separate state per environment/blast-radius boundary:** Production, staging, and dev almost always use entirely separate state files (and often separate GCP projects) rather than Terraform workspaces sharing one state, so a mistake in one environment's plan cannot touch another's real resources.

## 52.8 Common Misconceptions

- **Misconception:** "Terraform is a GCP product." Terraform is a third-party, open-source, multi-cloud tool (HashiCorp, now also forked as OpenTofu); Google contributes to and endorses the Google provider but does not own or operate Terraform itself — this is a meaningful distinction from Deployment Manager, which genuinely is a native Google service.
- **Misconception:** "Running `terraform apply` twice with no config changes is always a no-op." It is a no-op _only_ if nothing about the real infrastructure has drifted and no data source outputs have changed; Terraform recalculates the plan from current real state and current config every time, so out-of-band manual changes (a console edit) will surface as an unexpected diff on the next plan.

## 52.9 Interview Questions

**🎯 Beginner:** _Why does Terraform need a remote state backend like GCS instead of just a local state file?_
**Model answer:** A local state file only exists on one engineer's machine, so no one else and no CI pipeline can see or safely modify the same infrastructure without state getting out of sync or corrupted by concurrent edits. A GCS backend provides shared, remotely accessible state that every team member and automation reads and writes consistently, plus locking to prevent two simultaneous applies from corrupting the state, and versioning to allow recovery if the state is accidentally corrupted.

**🎯 Intermediate:** _When would you still encounter Deployment Manager instead of Terraform on a GCP project, and how would you approach it?_
**Model answer:** Deployment Manager predates widespread Terraform adoption on GCP, so it typically appears maintaining older deployments created before a team standardized on Terraform, not as a deliberate choice for new work — Google itself now generally steers new IaC work toward Terraform. My approach would be to avoid extending the legacy Deployment Manager configuration further; instead, I'd plan an incremental migration, importing existing resources into Terraform state (via `terraform import`) service by service, validating each import produces no unwanted diff on the next plan, rather than attempting a risky big-bang rewrite of the entire environment at once.

**🎯 Senior/Architect:** _Design a Terraform workflow for an enterprise with dozens of teams provisioning GCP infrastructure, where you need both team autonomy and central governance over things like IAM and network baselines._
**Model answer:** I would publish a set of internal, versioned Terraform modules (network, project baseline, standard IAM bindings) maintained by a central platform team, analogous to Google's own `terraform-google-modules`, so individual product teams consume approved modules rather than writing raw provider resources for foundational infrastructure — this keeps governance centralized without blocking team autonomy for their application-specific resources. Each team's environment would have its own GCS-backed state, scoped to a narrow blast radius (their own project or project set), with `plan`/`apply` running exclusively through Cloud Build pipelines gated by pull-request review, never local applies. State buckets would be centrally provisioned with strict IAM and versioning as part of the platform team's own bootstrap Terraform (itself following the same PR-gated apply pattern), and I'd enforce module version pinning so a breaking change to a shared module rolls out to consuming teams deliberately via a version bump and PR, rather than silently propagating to every environment on the next apply.

## 52.10 Key Takeaways

- 🔑 Terraform (via the Google provider) is GCP's de facto standard IaC tool, tracking desired state in HCL and real-world state in a state file, most commonly backed by GCS for team use.
- 🔑 The `plan` → review → `apply` workflow, run through CI/CD rather than locally, is the production-safe pattern; applying a previously stored plan avoids drift between review and execution.
- 🔑 Deployment Manager is GCP's native IaC service but is GCP-only and now largely legacy — Google steers new work toward Terraform.
- 🔑 State file security (restrictive IAM, versioning on the backend bucket) matters because state can contain sensitive resource attribute values in plaintext.

## 52.11 Related Concepts

Cloud Build as the CI/CD execution layer for `plan`/`apply` (Section 50), Cloud Storage as the state backend (Section 11), IAM fundamentals for provider/service-account permissions (Section 35), landing zone architecture built from standardized modules (Section 59), and the GCP vs. AWS vs. Azure IaC comparison (Section 82) all connect directly to the IaC model introduced here.
