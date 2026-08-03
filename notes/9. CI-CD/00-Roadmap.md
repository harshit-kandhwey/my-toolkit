# 00 — Roadmap: CI/CD (Complete Topic Roadmap)

## 0. Assumption Line

CI/CD is treated in its most common **DevOps / Platform Engineering / SRE** interpretation: continuous integration, continuous delivery, and continuous deployment as a discipline — the philosophy, pipeline-as-code design patterns, and hands-on platform depth needed to build, test, secure, and ship software automatically and reliably. This roadmap covers the concepts and history behind CI/CD, pipeline design fundamentals, and practical, in-depth coverage of the three dominant pipeline platforms (**GitHub Actions**, **GitLab CI/CD**, **Jenkins**), plus build/artifact management, testing strategy inside pipelines, deployment strategies, secrets handling, containerized pipelines, pipeline security (SAST/DAST/SCA/supply chain), pipeline observability, and enough **GitOps / ArgoCD** depth to bridge cleanly into continuous deployment on Kubernetes — cross-referencing this repo's existing Kubernetes GitOps coverage (`notes/12. Kubernetes/Contents/Part11/Section-88-Part11-GitOps-Fundamentals-ArgoCD-Flux.md`) rather than re-deriving it. This roadmap runs **130 sections across 16 parts**, sized to the same standard of depth as this repo's other tracks (comparable to Linux's 125, Ansible's 119, and Kubernetes' 141 sections) rather than a shallow tool overview.

Git fluency is assumed as a hard prerequisite — this repo already has a full 36-section Git knowledge base at `notes/1. GIT`, including a dedicated section on Git in CI/CD pipelines (`Contents/Part6/Section-25-Part6-Git-in-CICD-Pipelines.md`), so this roadmap does not re-teach branching, commits, or Git internals; it assumes the reader already thinks in terms of commits, branches, and pull/merge requests and focuses entirely on what happens to that code once a pipeline picks it up. Basic Linux/shell literacy (`notes/2. Linux`) is also assumed, since every pipeline platform ultimately runs shell commands inside a runner.

Because CI/CD spans philosophy, three genuinely different platforms with their own YAML dialects and execution models, and adjacent disciplines (testing, security scanning, deployment strategy, GitOps), this project is split into **named Parts**, generated sequentially. Do not ask which part to start with — Part 1 begins immediately after this roadmap.

---

## 1. Complete Numbered Roadmap

### Part 1 — Foundations, Philosophy, and History

1.1 What CI/CD Is: Continuous Integration vs. Continuous Delivery vs. Continuous Deployment
1.2 History: From Nightly Builds and CruiseControl to Jenkins, Cloud CI, and Pipeline-as-Code
1.3 The Business Case: Why CI/CD Exists (Lead Time, Deployment Frequency, MTTR, Change Failure Rate — DORA Metrics)
1.4 The CI/CD Feedback Loop and "Shift Left" Thinking
1.5 Trunk-Based Development vs. GitFlow vs. GitHub Flow — How Branching Strategy Shapes Pipeline Design
1.6 Anatomy of a Pipeline: Triggers, Stages, Jobs, Steps, Artifacts, Environments
1.7 The CI/CD Platform Landscape: GitHub Actions vs. GitLab CI vs. Jenkins vs. CircleCI/Travis/Others — Positioning
1.8 Prerequisites Recap (Git Fluency, Shell Basics, YAML Literacy)

### Part 2 — Pipeline Concepts and Pipeline-as-Code

2.1 Pipeline-as-Code Philosophy: Why Config Lives in the Repository
2.2 YAML Fundamentals for Pipeline Authors (Anchors, Aliases, Multi-Document Files)
2.3 Triggers and Events: Push, Pull Request, Schedule, Manual, Webhook
2.4 Stages vs. Jobs vs. Steps — Universal Vocabulary Across Platforms
2.5 Runners/Agents/Executors: Hosted vs. Self-Hosted Compute Models
2.6 Parallelism, Fan-Out/Fan-In, and Job Dependencies (DAG-Based Pipelines)
2.7 Caching Strategies: Dependency Caches vs. Build Caches vs. Layer Caches
2.8 Artifacts and Workspace Passing Between Jobs
2.9 Environment Variables, Contexts, and Variable Precedence
2.10 Pipeline Design Anti-Patterns: Monolithic Pipelines, Flaky Steps, Hidden State

### Part 3 — GitHub Actions Deep Dive I: Core Mechanics

3.1 GitHub Actions Architecture: Workflows, Jobs, Steps, Runners
3.2 Workflow Syntax: `on`, `jobs`, `steps`, `runs-on`
3.3 GitHub-Hosted Runners vs. Self-Hosted Runners (Sizing, OS Images, Runner Groups)
3.4 The Actions Marketplace: Using and Pinning Third-Party Actions
3.5 Writing Custom Actions (Composite, JavaScript, Docker Container Actions)
3.6 Matrix Builds and Strategy Blocks
3.7 Secrets and Environments in GitHub Actions (Repository, Environment, Organization Secrets)

### Part 4 — GitHub Actions Deep Dive II: Advanced Patterns

4.1 Reusable Workflows (`workflow_call`) vs. Composite Actions — When to Use Each
4.2 Concurrency Groups and Cancellation
4.3 Conditional Execution: `if`, `needs`, Job Outputs
4.4 GITHUB_TOKEN Permissions and the Principle of Least Privilege
4.5 Caching in GitHub Actions (`actions/cache`) and Dependency-Specific Caching Patterns
4.6 Artifacts, Job Summaries, and the Checks API
4.7 Self-Hosted Runner Security Considerations (Fork PRs, Untrusted Code)
4.8 GitHub Actions for Monorepos: Path Filters and Targeted Workflows
4.9 Debugging GitHub Actions: Re-Run, `tmate`/SSH Debugging, Step-Level Logs

### Part 5 — GitLab CI/CD Deep Dive I: Core Mechanics

5.1 GitLab CI/CD Architecture: `.gitlab-ci.yml`, Pipelines, Stages, Jobs
5.2 GitLab Runners: Shared, Group, and Project Runners; Executors (Shell, Docker, Kubernetes)
5.3 Pipeline Triggers: Push, Merge Request, Schedule, API, Pipeline Triggers
5.4 Rules vs. `only`/`except` — Modern Conditional Job Execution
5.5 Stages, `needs`, and DAG Pipelines in GitLab
5.6 CI/CD Variables and Variable Precedence in GitLab
5.7 Caching and Artifacts in GitLab CI

### Part 6 — GitLab CI/CD Deep Dive II: Advanced Patterns

6.1 `include` and Templates: Reusable Pipeline Configuration
6.2 Parent-Child Pipelines and Multi-Project Pipelines
6.3 Merge Request Pipelines vs. Merge Trains
6.4 GitLab Environments, Deployments, and the Deploy Board
6.5 GitLab Auto DevOps: What It Automates and Its Limits
6.6 Protected Branches, Protected Variables, and Protected Environments
6.7 GitLab CI Component Repository and Reusable Components
6.8 Debugging GitLab Pipelines: Job Logs, Pipeline Editor, Lint Tool

### Part 7 — Jenkins Deep Dive I: Core Mechanics

7.1 Jenkins Architecture: Controller, Agents, Executors
7.2 Freestyle Jobs vs. Pipeline Jobs — Why Pipeline-as-Code Won
7.3 Jenkinsfile Fundamentals: Declarative vs. Scripted Pipeline Syntax
7.4 Declarative Pipeline Structure: `agent`, `stages`, `steps`, `post`
7.5 Plugins Ecosystem: Essential Plugins and Plugin Management Risk
7.6 Distributed Builds: Configuring and Scaling Agents (Static, Docker, Kubernetes)
7.7 Credentials Management in Jenkins

### Part 8 — Jenkins Deep Dive II: Advanced Patterns

8.1 Scripted Pipeline: Groovy Fundamentals for Pipeline Authors
8.2 Shared Libraries: Centralizing Reusable Pipeline Logic
8.3 Multibranch Pipelines and Organization Folders
8.4 Parallel Stages and Matrix Builds in Jenkins
8.5 Blue Ocean and Modern Jenkins UI Considerations
8.6 Jenkins as Code: Configuration-as-Code (JCasC) Plugin
8.7 Jenkins in Kubernetes: The Kubernetes Plugin and Dynamic Agent Pods
8.8 Jenkins Security Hardening and Common CVE Classes
8.9 Migrating Off Jenkins: When and Why Teams Move to Cloud-Native CI

### Part 9 — Build and Artifact Management

9.1 Build Systems Overview: Language-Specific Build Tools in a CI Context (Maven/Gradle, npm/yarn, pip/poetry, Go modules)
9.2 Reproducible Builds: Pinning Dependencies and Lockfiles
9.3 Artifact Repositories: Nexus, Artifactory, GitHub Packages, GitLab Package Registry
9.4 Semantic Versioning and Automated Version Bumping in Pipelines
9.5 Build Caching Strategies at Scale (Remote Caches, Distributed Build Caches)
9.6 Multi-Language Monorepo Build Orchestration (Bazel, Nx, Turborepo — Conceptual Overview)
9.7 Release Artifacts: Tagging, Changelogs, and Release Notes Automation

### Part 10 — Testing Strategies in Pipelines

10.1 The Testing Pyramid Applied to Pipeline Design
10.2 Unit Tests in CI: Fast Feedback and Fail-Fast Principles
10.3 Integration Tests: Ephemeral Dependencies (Test Containers, Service Containers)
10.4 End-to-End Tests in Pipelines: Trade-Offs of Speed vs. Coverage
10.5 Test Parallelization and Splitting Strategies
10.6 Flaky Test Management: Quarantine, Retry, and Detection Strategies
10.7 Code Coverage Gates and Quality Gates (SonarQube and Similar Tools)
10.8 Contract Testing and Consumer-Driven Contracts in a CI Context

### Part 11 — Deployment Strategies

11.1 Deployment Strategy Overview: Recreate, Rolling, Blue-Green, Canary, A/B
11.2 Blue-Green Deployments: Implementation Patterns Across Platforms
11.3 Canary Releases: Progressive Traffic Shifting and Automated Rollback Triggers
11.4 Feature Flags as a Deployment Decoupling Mechanism
11.5 Rollback Strategies: Automated vs. Manual, Artifact-Based vs. Git-Revert-Based
11.6 Environment Promotion Models: Dev → Staging → Production Pipelines
11.7 Deployment Approval Gates and Manual Intervention Steps
11.8 Zero-Downtime Deployment Considerations at the Application Layer

### Part 12 — Secrets and Credentials Management in Pipelines

12.1 Why Pipeline Secrets Are a Distinct Threat Model (Log Leakage, Fork PRs, Third-Party Actions)
12.2 Native Secret Stores: GitHub Encrypted Secrets, GitLab CI/CD Variables, Jenkins Credentials
12.3 External Secret Managers in Pipelines: HashiCorp Vault, AWS Secrets Manager, Azure Key Vault
12.4 OIDC and Short-Lived Credentials: Eliminating Long-Lived Cloud Keys in CI
12.5 Secret Scanning and Pre-Commit/Pre-Push Prevention
12.6 Least-Privilege Service Accounts and Scoped Tokens for CI Runners
12.7 Secrets Rotation Strategies in Automated Pipelines

### Part 13 — Containerized Pipelines and Docker-in-CI

13.1 Why Containers and CI/CD Are Symbiotic: Reproducible Build Environments
13.2 Building Docker Images in CI: Docker-in-Docker vs. Kaniko vs. Buildah vs. Podman
13.3 Multi-Stage Builds for Smaller, Faster CI Images
13.4 Image Tagging Strategies and Immutable Artifact Promotion
13.5 Container Registries in the Pipeline: Push/Pull Auth Patterns (ECR, GCR/Artifact Registry, ACR, Docker Hub, Harbor)
13.6 Running Pipeline Jobs as Containers: Job Isolation and Ephemeral Runners
13.7 Layer Caching and Build Speed Optimization for Containerized Builds

### Part 14 — GitOps and Continuous Deployment to Kubernetes

14.1 GitOps Principles: Declarative State, Git as Source of Truth, Reconciliation Loops
14.2 Push-Based CD vs. Pull-Based GitOps — Why the Distinction Matters for Security
14.3 ArgoCD Fundamentals: Applications, Sync Policies, and the Reconciliation Loop
14.4 Flux as an Alternative GitOps Controller: Conceptual Comparison to ArgoCD
14.5 Structuring a GitOps Repository: App-of-Apps, Environment Branches vs. Directories
14.6 CI/CD Pipeline Responsibilities vs. GitOps Controller Responsibilities — Where the Handoff Happens
14.7 Progressive Delivery on Kubernetes: Argo Rollouts and Flagger for Canary/Blue-Green
14.8 Cross-Reference: This Repo's Kubernetes GitOps Coverage (`notes/12. Kubernetes/Contents/Part11/Section-88-Part11-GitOps-Fundamentals-ArgoCD-Flux.md`) and How It Extends This Part

### Part 15 — Security in the Pipeline

15.1 The Software Supply Chain Threat Model and Recent High-Profile Pipeline Attacks
15.2 SAST (Static Application Security Testing) Tools and CI Integration Patterns
15.3 SCA (Software Composition Analysis) and Dependency Vulnerability Scanning
15.4 DAST (Dynamic Application Security Testing) in Late-Stage Pipeline Gates
15.5 Container Image Scanning in CI (Trivy, Grype, and Registry-Native Scanners)
15.6 SBOM Generation and Consumption in Pipelines
15.7 Artifact Signing and Provenance: Sigstore/Cosign, SLSA Framework Levels
15.8 Policy-as-Code Gates in Pipelines (OPA/Conftest, Admission-Time Checks)
15.9 Pipeline Permission Hardening: Third-Party Action/Plugin Risk and Supply-Chain Pinning

### Part 16 — Monitoring, Mastery, Interview Prep, and Wrap-Up

16.1 Pipeline Observability: Build Metrics, Duration Trends, and Failure-Rate Dashboards
16.2 DORA Metrics in Practice: Instrumenting Pipelines to Measure Them
16.3 Alerting on Pipeline Health (Flaky Stages, Queue Times, Runner Saturation)
16.4 Platform Comparison Matrix Revisited: GitHub Actions vs. GitLab CI vs. Jenkins — Choosing for a Real Org
16.5 CI/CD Anti-Patterns and Common Failure Modes Recap
16.6 Cost Optimization for CI/CD at Scale (Runner Sizing, Caching ROI, Self-Hosted vs. Hosted Trade-Offs)
16.7 General CI/CD Interview Question Bank (Beginner to Architect)
16.8 Scenario-Based Pipeline Design Interview Questions
16.9 Progressive Hands-On Labs (Simple Workflow → Multi-Stage Secure GitOps Pipeline)
16.10 Consolidated Key-Takeaways Checklist
16.11 Related Technologies and Recommended Next Topics

---

## 2. Prerequisites

| Prerequisite                                                       | Needed For    | Introduced                                                                                                         |
| ------------------------------------------------------------------ | ------------- | ------------------------------------------------------------------------------------------------------------------ |
| Git fluency (branches, commits, pull/merge requests)               | Throughout    | Assumed baseline (see [[../1. GIT/README]], especially `Contents/Part6/Section-25-Part6-Git-in-CICD-Pipelines.md`) |
| Basic Linux/shell comfort (running commands, exit codes, env vars) | Throughout    | Assumed baseline (see [[../2. Linux/README]])                                                                      |
| YAML syntax                                                        | Part 2 onward | Recapped in 2.2                                                                                                    |
| Basic Docker/container literacy                                    | Part 13       | Recapped in 13.1                                                                                                   |
| Basic Kubernetes literacy                                          | Part 14       | Recapped in 14.1; deep dive lives in [[../12. Kubernetes/00-Roadmap]]                                              |

No external topic must be studied before starting beyond Git and basic Linux/shell fluency; every CI/CD-specific prerequisite is built in place.

---

## 3. Learning Phases

| Phase                                      | Parts Covered | Goal                                                                    |
| ------------------------------------------ | ------------- | ----------------------------------------------------------------------- |
| Phase 1 — Foundations                      | Part 1, 2     | Understand CI/CD philosophy, history, and universal pipeline vocabulary |
| Phase 2 — Platform Mastery: GitHub Actions | Part 3, 4     | Full working fluency in GitHub Actions, core and advanced               |
| Phase 3 — Platform Mastery: GitLab CI/CD   | Part 5, 6     | Full working fluency in GitLab CI/CD, core and advanced                 |
| Phase 4 — Platform Mastery: Jenkins        | Part 7, 8     | Full working fluency in Jenkins, core and advanced                      |
| Phase 5 — Build and Quality                | Part 9, 10    | Artifact management and testing strategy inside pipelines               |
| Phase 6 — Delivery and Trust               | Part 11, 12   | Deployment strategies and secrets management                            |
| Phase 7 — Cloud-Native Pipelines           | Part 13, 14   | Containerized pipelines and GitOps-based continuous deployment          |
| Phase 8 — Security                         | Part 15       | SAST/DAST/SCA and supply-chain hardening                                |
| Phase 9 — Operations and Mastery           | Part 16       | Observability, comparisons, interview prep, labs, wrap-up               |

---

## 4. Section-to-File Mapping

Each roadmap subsection (e.g., `1.1`, `9.4`) is authored as its own file, following the `Contents/PartN/Section-NN-PartN-Slug.md` convention shared with this repo's other knowledge bases (Linux, GIT, Ansible, Kubernetes). Section numbers (`§`) are continuous across the entire 16-part roadmap (1–128), not reset per part.

| Part                                                       | Roadmap Range | Continuous § Range | Folder             |
| ---------------------------------------------------------- | ------------- | ------------------ | ------------------ |
| Part 1 — Foundations, Philosophy, and History              | 1.1–1.8       | §1–§8              | `Contents/Part1/`  |
| Part 2 — Pipeline Concepts and Pipeline-as-Code            | 2.1–2.10      | §9–§18             | `Contents/Part2/`  |
| Part 3 — GitHub Actions Deep Dive I: Core Mechanics        | 3.1–3.7       | §19–§25            | `Contents/Part3/`  |
| Part 4 — GitHub Actions Deep Dive II: Advanced Patterns    | 4.1–4.9       | §26–§34            | `Contents/Part4/`  |
| Part 5 — GitLab CI/CD Deep Dive I: Core Mechanics          | 5.1–5.7       | §35–§41            | `Contents/Part5/`  |
| Part 6 — GitLab CI/CD Deep Dive II: Advanced Patterns      | 6.1–6.8       | §42–§49            | `Contents/Part6/`  |
| Part 7 — Jenkins Deep Dive I: Core Mechanics               | 7.1–7.7       | §50–§56            | `Contents/Part7/`  |
| Part 8 — Jenkins Deep Dive II: Advanced Patterns           | 8.1–8.9       | §57–§65            | `Contents/Part8/`  |
| Part 9 — Build and Artifact Management                     | 9.1–9.7       | §66–§72            | `Contents/Part9/`  |
| Part 10 — Testing Strategies in Pipelines                  | 10.1–10.8     | §73–§80            | `Contents/Part10/` |
| Part 11 — Deployment Strategies                            | 11.1–11.8     | §81–§88            | `Contents/Part11/` |
| Part 12 — Secrets and Credentials Management in Pipelines  | 12.1–12.7     | §89–§95            | `Contents/Part12/` |
| Part 13 — Containerized Pipelines and Docker-in-CI         | 13.1–13.7     | §96–§102           | `Contents/Part13/` |
| Part 14 — GitOps and Continuous Deployment to Kubernetes   | 14.1–14.8     | §103–§110          | `Contents/Part14/` |
| Part 15 — Security in the Pipeline                         | 15.1–15.9     | §111–§119          | `Contents/Part15/` |
| Part 16 — Monitoring, Mastery, Interview Prep, and Wrap-Up | 16.1–16.11    | §120–§130          | `Contents/Part16/` |

**Total: 130 sections across 16 parts.**

---

## 5. Cross-Topic Dependency Graph

```text
Foundations, Philosophy, and History (P1)
        │
        ▼
Pipeline Concepts and Pipeline-as-Code (P2) ──────────► Universal vocabulary: triggers, stages, jobs, caching, artifacts
        │
        ├──► GitHub Actions Deep Dive I (P3) ──► GitHub Actions Deep Dive II (P4)
        │
        ├──► GitLab CI/CD Deep Dive I (P5) ──► GitLab CI/CD Deep Dive II (P6)
        │
        └──► Jenkins Deep Dive I (P7) ──► Jenkins Deep Dive II (P8)
                        │
                        ▼
        Build and Artifact Management (P9)
                        │
                        ▼
        Testing Strategies in Pipelines (P10)
                        │
                        ▼
        Deployment Strategies (P11)
                        │
                        ▼
        Secrets and Credentials Management (P12)
                        │
                        ▼
        Containerized Pipelines and Docker-in-CI (P13)
                        │
                        ▼
        GitOps and Continuous Deployment to Kubernetes (P14) ──► Bridges into [[../12. Kubernetes/00-Roadmap]] Part 11 (GitOps/ArgoCD/Flux)
                        │
                        ▼
        Security in the Pipeline (P15) ──► SAST/DAST/SCA, supply-chain, SBOM, signing
                        │
                        ▼
        Monitoring, Mastery, Interview Prep, Wrap-Up (P16) ──► Recommended next topics: Kubernetes GitOps depth, Terraform, Prometheus/Grafana
```

**Recommended technologies to learn alongside or after CI/CD:** Kubernetes GitOps deep dive (see [[../12. Kubernetes/00-Roadmap]], Part 11), Terraform for infrastructure provisioning inside pipelines (see [[../7. Terraform]]), Prometheus/Grafana for pipeline and deployment observability (see [[../12. Kubernetes/00-Roadmap]], Part 12), Ansible for post-deployment configuration management (see [[../8. Ansible/00-Roadmap]]), Git internals and hosting-platform specifics already covered in full (see [[../1. GIT]]).

---

## 6. Roadmap Expansion Backlog

_(Empty at project start. Populated when the user requests additions, gap coverage, or new parts.)_

| Item | Requested Reason / Gap | Placement | Status | Target Filename |
| ---- | ---------------------- | --------- | ------ | --------------- |
| —    | —                      | —         | —      | —               |

---

## 7. Current Roadmap State

| #   | Part                                                       | Section    | Status         |
| --- | ---------------------------------------------------------- | ---------- | -------------- |
| 01  | Part 1 — Foundations, Philosophy, and History              | 1.1–1.8    | ⬜ Not Started |
| 02  | Part 2 — Pipeline Concepts and Pipeline-as-Code            | 2.1–2.10   | ⬜ Not Started |
| 03  | Part 3 — GitHub Actions Deep Dive I: Core Mechanics        | 3.1–3.7    | ⬜ Not Started |
| 04  | Part 4 — GitHub Actions Deep Dive II: Advanced Patterns    | 4.1–4.9    | ⬜ Not Started |
| 05  | Part 5 — GitLab CI/CD Deep Dive I: Core Mechanics          | 5.1–5.7    | ⬜ Not Started |
| 06  | Part 6 — GitLab CI/CD Deep Dive II: Advanced Patterns      | 6.1–6.8    | ⬜ Not Started |
| 07  | Part 7 — Jenkins Deep Dive I: Core Mechanics               | 7.1–7.7    | ⬜ Not Started |
| 08  | Part 8 — Jenkins Deep Dive II: Advanced Patterns           | 8.1–8.9    | ⬜ Not Started |
| 09  | Part 9 — Build and Artifact Management                     | 9.1–9.7    | ⬜ Not Started |
| 10  | Part 10 — Testing Strategies in Pipelines                  | 10.1–10.8  | ⬜ Not Started |
| 11  | Part 11 — Deployment Strategies                            | 11.1–11.8  | ⬜ Not Started |
| 12  | Part 12 — Secrets and Credentials Management in Pipelines  | 12.1–12.7  | ⬜ Not Started |
| 13  | Part 13 — Containerized Pipelines and Docker-in-CI         | 13.1–13.7  | ⬜ Not Started |
| 14  | Part 14 — GitOps and Continuous Deployment to Kubernetes   | 14.1–14.8  | ⬜ Not Started |
| 15  | Part 15 — Security in the Pipeline                         | 15.1–15.9  | ⬜ Not Started |
| 16  | Part 16 — Monitoring, Mastery, Interview Prep, and Wrap-Up | 16.1–16.11 | ⬜ Not Started |

**Next Section:** Part 1 — Foundations, Philosophy, and History (§1–§8)
