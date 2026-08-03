# 00 — Roadmap: Terraform (Complete Topic Roadmap)

## 0. Assumption Line

Terraform is treated in its most common **DevOps / Cloud / Infrastructure-as-Code** interpretation: HashiCorp Terraform as a provider-agnostic declarative provisioning tool (HCL, the provider plugin model, state, the resource graph, modules, workspaces, provisioners, and Terraform Cloud/Enterprise), covering everything from first principles through enterprise multi-cloud provisioning patterns and policy-as-code — with explicit, direct coverage of the **HashiCorp Certified: Terraform Associate** exam curriculum. Because this repo already carries full AWS, Azure, and GCP knowledge bases at [[../6. Cloud]], Terraform is taught here as a provider-agnostic core (HCL syntax, state, graph, modules, CLI workflow) with worked AWS/Azure/GCP examples layered on top for multi-cloud provisioning patterns, rather than duplicating any single cloud's service catalog. This roadmap runs **120 sections across 17 parts**, sized to the same standard of depth as this repo's other tracks (comparable to Linux's 125 and Ansible's 119 sections) rather than a shallow tool overview.

Because Terraform spans language mechanics, state semantics, multi-cloud provisioning, and enterprise governance, this project is split into **named Parts**, generated sequentially. Do not ask which part to start with — Part 1 begins immediately after this roadmap.

---

## 1. Complete Numbered Roadmap

### Part 1 — Foundations, IaC History, and Terraform's Place in the Ecosystem

1.1 What Infrastructure as Code Is; Declarative vs. Imperative Provisioning
1.2 History: Terraform's Origins, HashiCorp, and the IaC Tooling Landscape (CloudFormation, ARM/Bicep, Pulumi, CDK)
1.3 Terraform vs. Configuration Management (Ansible/Puppet/Chef) — Provisioning vs. Configuration
1.4 Terraform Architecture Overview: Core, Providers, State, Plugins
1.5 Installation and Setup (tfenv, package managers, version pinning)
1.6 Prerequisites Recap (Cloud Fundamentals, CLI Basics)
1.7 Terraform Associate Certification Landscape and How This Roadmap Maps to It

### Part 2 — Core Architecture: Providers, Plugins, and the Dependency Graph

2.1 The Terraform Core / Provider Plugin Model (RPC, Provider SDK)
2.2 Provider Configuration and Version Constraints
2.3 The Terraform Registry and Sourcing Providers
2.4 The Resource Graph: Dependency Resolution and DAG Construction
2.5 Terraform's Execution Model: Refresh, Plan, Apply Internals
2.6 Multiple Provider Instances and Provider Aliases
2.7 Provider Authentication Patterns (AWS/Azure/GCP)

### Part 3 — HCL Syntax Deep Dive

3.1 HCL Fundamentals: Blocks, Arguments, Identifiers
3.2 Terraform File Structure and Conventions (main.tf, variables.tf, outputs.tf, versions.tf)
3.3 Data Types: Primitives, Collections (list, map, set), Structural (object, tuple)
3.4 Expressions: Arithmetic, Comparison, and Conditional (Ternary) Expressions
3.5 String Interpolation and Templating (heredoc, templatefile)
3.6 Built-In Functions: Numeric, String, Collection, and Type Conversion Functions
3.7 for Expressions and Splat Expressions
3.8 Dynamic Blocks
3.9 Meta-Arguments Overview (count, for_each, depends_on, lifecycle, provider)

### Part 4 — The Terraform CLI Workflow

4.1 terraform init: Backend Init, Provider Install, Module Install
4.2 terraform plan: Reading Plan Output and Saved Plan Files
4.3 terraform apply and terraform destroy
4.4 terraform validate and terraform fmt
4.5 terraform console and terraform graph
4.6 CLI Configuration (.terraformrc, CLI Config Blocks, Credentials Helpers)
4.7 terraform show, terraform output, and Machine-Readable (-json) Output
4.8 Common CLI Flags and Automation-Friendly Patterns (-auto-approve, -var-file, -target, -lock)

### Part 5 — Resources and Data Sources

5.1 Resource Blocks: Anatomy and Resource Addressing
5.2 Data Sources: Reading External and Existing Infrastructure
5.3 Resource Meta-Arguments: count vs. for_each
5.4 Resource Dependencies: Implicit vs. Explicit (depends_on)
5.5 The lifecycle Block: create_before_destroy, prevent_destroy, ignore_changes
5.6 Resource Targeting and Partial Applies
5.7 Local-Only Resources (null_resource, terraform_data, random and time Providers)

### Part 6 — Variables, Outputs, and Locals

6.1 Input Variables: Declaration, Types, and Defaults
6.2 Variable Precedence and Assignment Methods (CLI Flags, .tfvars, Environment Variables)
6.3 Sensitive Variables and Sensitive Output Values
6.4 Output Values: Declaration, Dependencies, and Consumption
6.5 Local Values: Use Cases and Best Practices
6.6 Variable Validation Rules and Custom Error Messages
6.7 Complex Variable Types: Object and Nested Structures

### Part 7 — State Management and Remote Backends

7.1 What Terraform State Is and Why It Exists
7.2 The State File Format (terraform.tfstate) Deep Dive
7.3 Local State vs. Remote State
7.4 Remote Backends Overview (S3, Azure Storage, GCS, Terraform Cloud)
7.5 State Locking Mechanisms (DynamoDB, Blob Lease, and Equivalents)
7.6 State Commands: terraform state list/show/mv/rm/pull/push
7.7 terraform import: Bringing Existing Resources Under Management
7.8 State Migration and Backend Reconfiguration
7.9 Handling State Drift and terraform refresh

### Part 8 — Modules

8.1 What Modules Are; Root Module vs. Child Modules
8.2 Module Structure and Conventions
8.3 Module Inputs and Outputs
8.4 Calling Modules: Local Paths, Registry Sources, Git Sources
8.5 The Terraform Registry: Publishing and Consuming Public Modules
8.6 Module Versioning and Version Constraints
8.7 Module Composition Patterns and Nested Modules
8.8 Module Design Best Practices and Anti-Patterns

### Part 9 — Provisioners and Lifecycle Rules

9.1 Provisioners Overview and Why HashiCorp Discourages Them
9.2 local-exec and remote-exec Provisioners
9.3 Connection Blocks (SSH/WinRM)
9.4 Provisioner Failure Behavior (on_failure)
9.5 null_resource and Provisioner Triggers
9.6 Alternatives to Provisioners (cloud-init, user_data, Ansible Handoff)

### Part 10 — Workspaces and Environment Strategies

10.1 Terraform CLI Workspaces: Concepts and Commands
10.2 Workspace-Based vs. Directory-Based Environment Separation
10.3 File Layout Patterns for Multi-Environment Projects
10.4 terraform.workspace and Interpolation Patterns
10.5 When Workspaces Are the Wrong Tool
10.6 Environment Promotion Patterns (dev → staging → prod)

### Part 11 — Multi-Cloud Provisioning Patterns (AWS/Azure/GCP)

11.1 AWS Provider Deep Dive: VPC, EC2, S3, IAM Provisioning Patterns
11.2 Azure Provider (azurerm) Deep Dive: Resource Groups, VNets, VMs
11.3 GCP Provider (google) Deep Dive: Projects, VPCs, Compute Instances
11.4 Cross-Provider Patterns: Shared Modules Across Clouds
11.5 Networking as Code (VPC/VNet Peering, Subnets, Security Groups/NSGs)
11.6 IAM as Code Across Providers
11.7 Kubernetes Provisioning via Terraform (EKS/AKS/GKE)
11.8 Multi-Region and Multi-Account/Subscription/Project Patterns
11.9 Cost Awareness in Multi-Cloud Terraform Design

### Part 12 — Terraform Cloud and Enterprise

12.1 Terraform Cloud Overview: Organizations, Workspaces, and Runs
12.2 VCS-Driven Workflows and Remote Runs
12.3 Sentinel and OPA Policy-as-Code
12.4 Private Module Registry and Private Provider Registry
12.5 Terraform Cloud Run Triggers and Workspace Dependencies
12.6 Terraform Enterprise: On-Prem/Self-Hosted Considerations
12.7 Cost Estimation Features
12.8 Teams, RBAC, and SSO in Terraform Cloud/Enterprise

### Part 13 — Security and Secrets Management

13.1 Secrets in State: Risks and Mitigations
13.2 Integrating HashiCorp Vault with Terraform
13.3 Cloud-Native Secrets Managers (AWS Secrets Manager, Azure Key Vault, GCP Secret Manager)
13.4 Least-Privilege IAM for Terraform Execution Roles
13.5 Static Analysis and Security Scanning (tfsec, Checkov, Terrascan)
13.6 Drift Detection and Compliance Enforcement
13.7 Secure Backend Configuration (Encryption at Rest, Access Controls)

### Part 14 — Testing and CI/CD Integration

14.1 terraform validate and Plan-Based Testing Strategies
14.2 Terratest and the Native terraform test Framework
14.3 Policy Testing with Sentinel/OPA in CI
14.4 CI/CD Pipeline Integration (GitHub Actions, GitLab CI, Jenkins)
14.5 GitOps for Terraform: PR-Based Plan/Apply Workflows
14.6 Pre-Commit Hooks and Linting (tflint)
14.7 Automated Testing Pyramids for IaC

### Part 15 — Mastery: Best Practices, Anti-Patterns, and Comparisons

15.1 Project Structure Best Practices at Scale (Monorepo vs. Polyrepo)
15.2 Terraform vs. Pulumi vs. CDK vs. CloudFormation/Bicep — Detailed Comparison
15.3 Common Anti-Patterns (Giant State Files, Hardcoded Values, Provider Sprawl)
15.4 Performance at Scale: -parallelism, State Splitting, Large Graphs
15.5 Versioning Strategy: Terraform Core, Providers, and Modules
15.6 Terraform + Ansible + Kubernetes: Division of Labor in a Full Stack

### Part 16 — Interview and Exam Preparation (Terraform Associate)

16.1 Terraform Associate Exam Domain Breakdown and Time-Management Strategy
16.2 Common Exam-Style Scenario Questions (Worked Through Step by Step)
16.3 CLI Speed Techniques and Common Gotchas for Exam Conditions
16.4 General Terraform Interview Question Bank (Beginner to Architect)
16.5 Scenario-Based Infrastructure Design Questions

### Part 17 — Wrap-Up

17.1 Progressive Hands-On Labs (beginner → production-style, exam-simulation labs)
17.2 Consolidated Key-Takeaways Checklist
17.3 Common Misconceptions and Anti-Patterns Recap
17.4 Related Technologies and Recommended Next Topics

---

## 2. Prerequisites

| Prerequisite                                              | Needed For     | Introduced                             |
| --------------------------------------------------------- | -------------- | -------------------------------------- |
| Cloud fundamentals (accounts, regions, IAM, networking)   | Part 2, 11, 13 | Assumed baseline (see [[../6. Cloud]]) |
| Command-line comfort (shells, environment variables)      | Part 4 onward  | Assumed baseline                       |
| Basic understanding of declarative vs. imperative tooling | Part 1         | Introduced in 1.1                      |
| Version control (Git) basics                              | Part 12, 14    | Assumed baseline (see [[../1. GIT]])   |

No external topic must be studied before starting; this roadmap builds every Terraform-specific prerequisite in place, though cloud-provider and Git fundamentals are assumed baseline knowledge.

---

## 3. Learning Phases

| Phase                                   | Parts Covered | Goal                                                               |
| --------------------------------------- | ------------- | ------------------------------------------------------------------ |
| Phase 1 — Foundations                   | Part 1, 2     | Understand IaC concepts and Terraform's provider architecture      |
| Phase 2 — Language Mechanics            | Part 3        | Master HCL syntax, types, expressions, and meta-arguments          |
| Phase 3 — Core Workflow                 | Part 4        | Run the init/plan/apply/destroy CLI workflow confidently           |
| Phase 4 — Configuration Building Blocks | Part 5, 6     | Author resources, data sources, variables, outputs, and locals     |
| Phase 5 — State and Reuse               | Part 7, 8     | Manage state safely and package configuration into modules         |
| Phase 6 — Provisioning Control          | Part 9, 10    | Handle provisioners, lifecycle rules, and environment strategy     |
| Phase 7 — Multi-Cloud Application       | Part 11       | Apply Terraform against AWS, Azure, and GCP in worked patterns     |
| Phase 8 — Enterprise and Governance     | Part 12, 13   | Terraform Cloud/Enterprise, policy-as-code, and secrets management |
| Phase 9 — Quality and Delivery          | Part 14       | Testing, linting, and CI/CD integration                            |
| Phase 10 — Mastery and Certification    | Part 15, 16   | Best practices, comparisons, and Terraform Associate exam prep     |
| Phase 11 — Wrap-Up                      | Part 17       | Labs, checklists, next steps                                       |

---

## 4. Section-to-File Mapping

Each roadmap subsection (e.g., `1.1`, `7.5`) is authored as its own file, following the `Contents/PartN/Section-NN-PartN-Slug.md` convention shared with this repo's other knowledge bases (Linux, AWS, Azure, GCP, Kubernetes, Ansible, GIT). Section numbers (`§`) are continuous across the entire 17-part roadmap (1–120), not reset per part.

| Part                                                                      | Roadmap Range | Continuous § Range | Folder             |
| ------------------------------------------------------------------------- | ------------- | ------------------ | ------------------ |
| Part 1 — Foundations, IaC History, and Terraform's Place in the Ecosystem | 1.1–1.7       | §1–§7              | `Contents/Part1/`  |
| Part 2 — Core Architecture: Providers, Plugins, and the Dependency Graph  | 2.1–2.7       | §8–§14             | `Contents/Part2/`  |
| Part 3 — HCL Syntax Deep Dive                                             | 3.1–3.9       | §15–§23            | `Contents/Part3/`  |
| Part 4 — The Terraform CLI Workflow                                       | 4.1–4.8       | §24–§31            | `Contents/Part4/`  |
| Part 5 — Resources and Data Sources                                       | 5.1–5.7       | §32–§38            | `Contents/Part5/`  |
| Part 6 — Variables, Outputs, and Locals                                   | 6.1–6.7       | §39–§45            | `Contents/Part6/`  |
| Part 7 — State Management and Remote Backends                             | 7.1–7.9       | §46–§54            | `Contents/Part7/`  |
| Part 8 — Modules                                                          | 8.1–8.8       | §55–§62            | `Contents/Part8/`  |
| Part 9 — Provisioners and Lifecycle Rules                                 | 9.1–9.6       | §63–§68            | `Contents/Part9/`  |
| Part 10 — Workspaces and Environment Strategies                           | 10.1–10.6     | §69–§74            | `Contents/Part10/` |
| Part 11 — Multi-Cloud Provisioning Patterns (AWS/Azure/GCP)               | 11.1–11.9     | §75–§83            | `Contents/Part11/` |
| Part 12 — Terraform Cloud and Enterprise                                  | 12.1–12.8     | §84–§91            | `Contents/Part12/` |
| Part 13 — Security and Secrets Management                                 | 13.1–13.7     | §92–§98            | `Contents/Part13/` |
| Part 14 — Testing and CI/CD Integration                                   | 14.1–14.7     | §99–§105           | `Contents/Part14/` |
| Part 15 — Mastery: Best Practices, Anti-Patterns, and Comparisons         | 15.1–15.6     | §106–§111          | `Contents/Part15/` |
| Part 16 — Interview and Exam Preparation (Terraform Associate)            | 16.1–16.5     | §112–§116          | `Contents/Part16/` |
| Part 17 — Wrap-Up                                                         | 17.1–17.4     | §117–§120          | `Contents/Part17/` |

**Total: 120 sections across 17 parts.**

The Part breakdown above is deliberately shaped to align cleanly with the official HashiCorp Certified: Terraform Associate exam objective areas (IaC concepts → Part 1; Terraform's purpose vs. other IaC tools → Part 1, 15; Terraform basics → Part 2, 3; the core CLI workflow → Part 4; resources, variables, and outputs → Part 5, 6; state → Part 7; modules → Part 8; using Terraform outside the core workflow, including import and state manipulation → Part 7, 9; workspaces → Part 10; and Terraform Cloud capabilities → Part 12) so that a future README's Certification Domain Mapping table can reference these Parts directly.

---

## 5. Cross-Topic Dependency Graph

```text
Foundations, IaC History, and Terraform's Place in the Ecosystem (P1)
        │
        ▼
Core Architecture: Providers, Plugins, and the Dependency Graph (P2)
        │
        ▼
HCL Syntax Deep Dive (P3) ──► Types, expressions, functions, dynamic blocks
        │
        ▼
The Terraform CLI Workflow (P4) ──► init/plan/apply/destroy
        │
        ▼
Resources and Data Sources (P5) ──► Variables, Outputs, and Locals (P6)
        │
        ▼
State Management and Remote Backends (P7) ──► import, drift, locking
        │
        ▼
Modules (P8)
        │
        ├──► Provisioners and Lifecycle Rules (P9)
        │
        ▼
Workspaces and Environment Strategies (P10)
        │
        ▼
Multi-Cloud Provisioning Patterns: AWS/Azure/GCP (P11)
        │
        ▼
Terraform Cloud and Enterprise (P12) ──► Sentinel/OPA, private registries, run triggers
        │
        ▼
Security and Secrets Management (P13)
        │
        ▼
Testing and CI/CD Integration (P14)
        │
        ▼
Mastery: Best Practices, Anti-Patterns, and Comparisons (P15)
        │
        ▼
Interview and Exam Preparation: Terraform Associate (P16)
        │
        ▼
Wrap-Up: Labs & Next Steps (P17) ──► Recommended next topics: Ansible, CI/CD, Kubernetes
```

**Recommended technologies to learn alongside or after Terraform:** Ansible (configuration management vs. Terraform's provisioning role — see [[../8. Ansible/00-Roadmap]]), CI/CD pipelines (see [[../9. CI-CD]]), Kubernetes (see [[../12. Kubernetes/00-Roadmap]]), cloud-provider fundamentals (already covered — see [[../6. Cloud]]), Git (already covered — see [[../1. GIT]]).

---

## 6. Roadmap Expansion Backlog

_(Empty at project start. Populated when the user requests additions, gap coverage, or new parts.)_

| Item | Requested Reason / Gap | Placement | Status | Target Filename |
| ---- | ---------------------- | --------- | ------ | --------------- |
| —    | —                      | —         | —      | —               |

---

## 7. Current Roadmap State

| #   | Part                                                                      | Section   | Status         |
| --- | ------------------------------------------------------------------------- | --------- | -------------- |
| 01  | Part 1 — Foundations, IaC History, and Terraform's Place in the Ecosystem | 1.1–1.7   | ⬜ Not Started |
| 02  | Part 2 — Core Architecture: Providers, Plugins, and the Dependency Graph  | 2.1–2.7   | ⬜ Not Started |
| 03  | Part 3 — HCL Syntax Deep Dive                                             | 3.1–3.9   | ⬜ Not Started |
| 04  | Part 4 — The Terraform CLI Workflow                                       | 4.1–4.8   | ⬜ Not Started |
| 05  | Part 5 — Resources and Data Sources                                       | 5.1–5.7   | ⬜ Not Started |
| 06  | Part 6 — Variables, Outputs, and Locals                                   | 6.1–6.7   | ⬜ Not Started |
| 07  | Part 7 — State Management and Remote Backends                             | 7.1–7.9   | ⬜ Not Started |
| 08  | Part 8 — Modules                                                          | 8.1–8.8   | ⬜ Not Started |
| 09  | Part 9 — Provisioners and Lifecycle Rules                                 | 9.1–9.6   | ⬜ Not Started |
| 10  | Part 10 — Workspaces and Environment Strategies                           | 10.1–10.6 | ⬜ Not Started |
| 11  | Part 11 — Multi-Cloud Provisioning Patterns (AWS/Azure/GCP)               | 11.1–11.9 | ⬜ Not Started |
| 12  | Part 12 — Terraform Cloud and Enterprise                                  | 12.1–12.8 | ⬜ Not Started |
| 13  | Part 13 — Security and Secrets Management                                 | 13.1–13.7 | ⬜ Not Started |
| 14  | Part 14 — Testing and CI/CD Integration                                   | 14.1–14.7 | ⬜ Not Started |
| 15  | Part 15 — Mastery: Best Practices, Anti-Patterns, and Comparisons         | 15.1–15.6 | ⬜ Not Started |
| 16  | Part 16 — Interview and Exam Preparation (Terraform Associate)            | 16.1–16.5 | ⬜ Not Started |
| 17  | Part 17 — Wrap-Up                                                         | 17.1–17.4 | ⬜ Not Started |

**Next Section:** Part 1 — Foundations, IaC History, and Terraform's Place in the Ecosystem (§1–§7)
