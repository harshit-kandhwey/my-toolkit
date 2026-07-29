# 00 — Roadmap: Kubernetes (Complete Topic Roadmap)

## 0. Assumption Line

Kubernetes is treated in its most common **DevOps / Cloud / Platform Engineering / SRE** interpretation: Kubernetes as a production container-orchestration system (control plane + node components, workload objects, networking, storage, security, and operations), covering everything from first principles through cluster administration, application delivery, and enterprise/multi-cluster patterns — with explicit, direct coverage of the three Linux Foundation certification curricula: **CKA (Certified Kubernetes Administrator)**, **CKAD (Certified Kubernetes Application Developer)**, and **CKS (Certified Kubernetes Security Specialist)**. Depth matches or exceeds this repo's other tracks (Linux: 125 sections/17 parts; AWS: 131 sections/15 parts) — this roadmap runs **141 sections across 18 parts**.

Because Kubernetes is an extremely broad subject, this project is split into **named Parts**, generated sequentially. Do not ask which part to start with — Part 1 begins immediately after this roadmap.

---

## 1. Complete Numbered Roadmap

### Part 1 — Foundations, Container Orchestration, and History

1.1 What Kubernetes Is; the Container Orchestration Problem It Solves
1.2 History: Google's Borg → Omega → Kubernetes; CNCF Governance and Release Cadence
1.3 Kubernetes Architecture Overview (control plane vs. data plane, high-level mental model)
1.4 The Declarative Model: Desired State, Reconciliation, and Level-Triggered vs. Edge-Triggered Systems
1.5 Kubernetes Distributions and Managed Offerings (EKS, AKS, GKE, kubeadm, k3s, MicroK8s, minikube, kind)
1.6 Prerequisites Recap (Linux, containers/Docker, YAML, core networking) and How This Roadmap Is Organized
1.7 CKA/CKAD/CKS Certification Landscape and How This Roadmap Maps to Each Exam

### Part 2 — Cluster Architecture

2.1 Control Plane Components: kube-apiserver, etcd, kube-scheduler, kube-controller-manager, cloud-controller-manager
2.2 Node Components: kubelet, kube-proxy, container runtime
2.3 etcd Deep Dive: Data Model, Raft Consensus, Consistency Guarantees
2.4 Container Runtime Interface (CRI): containerd, CRI-O, and the Dockershim Removal
2.5 API Server Deep Dive: API Groups, Versioning, the Request Lifecycle and Admission Chain
2.6 Controller Manager and the Controller Pattern (Reconciliation Loops)
2.7 Scheduler Internals Preview: Filtering and Scoring Phases (full depth in Part 9)
2.8 High-Availability Control Plane Architectures (stacked vs. external etcd topologies)

### Part 3 — Installation and Cluster Bootstrapping

3.1 kubeadm: Cluster Bootstrapping Step by Step
3.2 Static Pods and the Kubelet Configuration
3.3 Certificates and PKI in Kubernetes (kubeadm certificate management)
3.4 Joining Nodes and Bootstrap Tokens
3.5 kubeconfig Files, Contexts, and Multi-Cluster Switching
3.6 Managed Kubernetes Bootstrap Differences: EKS, AKS, GKE
3.7 Lightweight Distributions and Local Dev Clusters: k3s, MicroK8s, kind, minikube
3.8 Cluster Networking Prerequisites and CNI Plugin Selection at Install Time

### Part 4 — Core Workload Objects: Pods and Controllers

4.1 The Pod: Smallest Deployable Unit, Full Pod Spec Anatomy
4.2 Multi-Container Pods: Sidecar, Ambassador, and Adapter Patterns
4.3 Init Containers
4.4 ReplicaSets: Purpose and Relationship to Deployments
4.5 Deployments: Rolling Updates, Rollbacks, and Revision History
4.6 Deployment Strategies: RollingUpdate vs. Recreate; Blue/Green and Canary Patterns
4.7 Labels, Selectors, and Annotations
4.8 kubectl Fundamentals: Imperative Commands, Generators, --dry-run, kubectl diff
4.9 YAML Manifest Authoring and the kubectl apply Workflow

### Part 5 — Advanced Workloads

5.1 StatefulSets: Stable Network Identity, Ordered Deployment, Per-Replica Storage
5.2 DaemonSets: Node-Level Agent Workloads
5.3 Jobs: Run-to-Completion Workloads
5.4 CronJobs: Scheduled Job Execution
5.5 Horizontal Pod Autoscaler (HPA)
5.6 Vertical Pod Autoscaler (VPA) and Cluster Autoscaler (concept-level)
5.7 Pod Disruption Budgets
5.8 Workload Choice Decision Framework (Deployment vs. StatefulSet vs. DaemonSet vs. Job vs. CronJob)

### Part 6 — Configuration and Application Environment

6.1 ConfigMaps: Creation and Consumption (env vars, volume mounts, command-line args)
6.2 Secrets: Types, Encoding vs. Encryption, and Consumption Patterns
6.3 Encrypting Secrets at Rest (EncryptionConfiguration)
6.4 Environment Variable Injection and Precedence Rules
6.5 SecurityContext at Pod and Container Level
6.6 Resource Requests and Limits; Quality-of-Service Classes (Guaranteed/Burstable/BestEffort)
6.7 Multi-Environment Configuration Patterns (Namespaces as an isolation boundary; preview of Kustomize overlays)

### Part 7 — Networking

7.1 Kubernetes Networking Model: the Flat Network and Pod-to-Pod Communication Rules
7.2 CNI Plugins Compared: Calico, Flannel, Cilium, Weave
7.3 Services: ClusterIP, NodePort, LoadBalancer, ExternalName
7.4 kube-proxy Modes: iptables vs. IPVS
7.5 DNS in Kubernetes: CoreDNS, Service Discovery, and DNS Record Types
7.6 Ingress and Ingress Controllers (NGINX Ingress and alternatives)
7.7 Gateway API: the Modern Successor to Ingress
7.8 NetworkPolicies: Default-Deny Posture, Ingress/Egress Rule Design
7.9 In-Cluster Network Troubleshooting Toolkit (dig, nslookup, netshoot, tcpdump)

### Part 8 — Storage

8.1 Volumes: emptyDir, hostPath, and Ephemeral Storage
8.2 PersistentVolumes and PersistentVolumeClaims
8.3 StorageClasses and Dynamic Provisioning
8.4 Container Storage Interface (CSI) Architecture
8.5 Access Modes (RWO/ROX/RWX) and Reclaim Policies
8.6 StatefulSet Storage Patterns (volumeClaimTemplates)
8.7 Volume Snapshots and Cloning
8.8 Storage Troubleshooting (stuck PVCs, mount failures, node affinity conflicts)

### Part 9 — Scheduling

9.1 Scheduler Deep Dive: Filtering and Scoring Phases in Full
9.2 Node Selectors and Node Affinity/Anti-Affinity
9.3 Pod Affinity and Anti-Affinity
9.4 Taints and Tolerations
9.5 Manual Scheduling and Custom Schedulers
9.6 Resource-Based Scheduling: How Requests/Limits Drive Placement
9.7 Priority Classes and Preemption
9.8 Topology Spread Constraints

### Part 10 — Security and RBAC

10.1 Authentication in Kubernetes: Users, ServiceAccounts, X.509 Certs, OIDC
10.2 Authorization Modes: RBAC, ABAC, Node, Webhook
10.3 RBAC Deep Dive: Roles, ClusterRoles, RoleBindings, ClusterRoleBindings
10.4 ServiceAccounts: Tokens, Auto-Mounting, and Bound Service Account Tokens
10.5 Admission Controllers: Validating and Mutating Webhooks
10.6 Pod Security Standards (Privileged/Baseline/Restricted) and Pod Security Admission
10.7 NetworkPolicies as a Security Boundary (cross-reference to Part 7)
10.8 Secrets Management Integration (Vault, External Secrets Operator, Sealed Secrets)
10.9 Kubernetes Security Best Practices Checklist

### Part 11 — Package Management and Application Delivery

11.1 Helm Fundamentals: Charts, Releases, Repositories
11.2 Writing Helm Charts: Templates, Values, Helpers
11.3 Kustomize: Bases, Overlays, Patches
11.4 Helm vs. Kustomize vs. Raw Manifests — Decision Framework
11.5 Operators and the Operator Pattern; Custom Resource Definitions (CRDs)
11.6 Custom Controllers (conceptual overview, controller-runtime)
11.7 GitOps Fundamentals: ArgoCD and Flux

### Part 12 — Observability

12.1 Liveness, Readiness, and Startup Probes
12.2 kubectl logs, exec, debug, and Ephemeral Containers
12.3 Metrics Server and the Kubernetes Metrics Pipeline
12.4 Prometheus on Kubernetes: ServiceMonitors, Node Exporter, kube-state-metrics
12.5 Grafana Dashboards for Kubernetes
12.6 Centralized Logging Patterns (Fluentd/Fluent Bit, Loki, EFK Stack)
12.7 Distributed Tracing in Kubernetes (Jaeger/OpenTelemetry overview)
12.8 Events, Audit Logs, and kubectl describe Deep Dive

### Part 13 — Troubleshooting

13.1 Structured Troubleshooting Methodology for Kubernetes
13.2 Pod Failure States: CrashLoopBackOff, ImagePullBackOff, Pending, Evicted
13.3 Debugging Node Issues: NotReady Nodes, kubelet Failures
13.4 Debugging Control Plane Failures (API server, etcd, scheduler down)
13.5 Networking Troubleshooting Scenarios (unreachable Services, DNS failures)
13.6 Storage Troubleshooting Scenarios (PVC Pending, mount errors)
13.7 Application-Level Debugging (misconfigured probes, resource starvation, OOMKilled)
13.8 Cluster-Level Resource Exhaustion and Eviction
13.9 Incident Case Studies and Runbooks

### Part 14 — Cluster Maintenance and Lifecycle

14.1 Cluster Upgrades with kubeadm (control plane and node upgrade ordering)
14.2 etcd Backup and Restore Procedures
14.3 Node Maintenance: cordon, drain, uncordon
14.4 Certificate Rotation and Renewal
14.5 Cluster Backup Strategies (Velero)
14.6 Version Skew Policy and Deprecation Handling
14.7 Disaster Recovery Planning for Kubernetes Clusters

### Part 15 — Advanced Security (CKS Deep Dive)

15.1 CKS Curriculum Overview and Cluster Setup Hardening (CIS Benchmarks, kube-bench)
15.2 System Hardening: Minimizing Host OS Attack Surface, seccomp, AppArmor
15.3 Minimizing Microservice Vulnerabilities: SecurityContext Hardening, gVisor/Kata Containers
15.4 Supply Chain Security: Image Scanning (Trivy), Signing (Cosign/Sigstore), SBOM
15.5 Static Analysis of Manifests (kube-linter, Kubesec)
15.6 Runtime Security and Threat Detection (Falco)
15.7 Network Security Deep Dive: mTLS and Service Mesh Security
15.8 Secrets Encryption and External Secret Stores (deep dive beyond Part 10)
15.9 Monitoring, Logging, and Runtime Threat Detection for the CKS Exam

### Part 16 — Service Mesh, Multi-Cluster, and Enterprise Patterns

16.1 Service Mesh Concepts: the Sidecar Proxy Pattern
16.2 Istio Fundamentals: Traffic Management, mTLS, Observability
16.3 Linkerd as a Lightweight Alternative
16.4 Multi-Cluster Architectures: Federation, Cluster API
16.5 Multi-Tenancy Patterns in Kubernetes
16.6 Cost Optimization and Resource Governance (ResourceQuotas, LimitRanges)
16.7 Kubernetes on AWS/Azure/GCP: EKS/AKS/GKE-Specific Considerations
16.8 Enterprise Landing-Zone Patterns for Kubernetes Platforms

### Part 17 — Interview and Exam Preparation (CKA/CKAD/CKS)

17.1 CKA Exam Domain Breakdown and Time-Management Strategy
17.2 CKAD Exam Domain Breakdown and Time-Management Strategy
17.3 CKS Exam Domain Breakdown and Time-Management Strategy
17.4 kubectl Speed Techniques: Aliases, Vim/Editor Config, Imperative One-Liners for Exam Conditions
17.5 CKA-Style Scenario Question Bank
17.6 CKAD-Style Scenario Question Bank
17.7 CKS-Style Scenario Question Bank
17.8 Architect-Level and Behavioral-Technical Crossover Questions

### Part 18 — Wrap-Up

18.1 Progressive Hands-On Labs (beginner → production-style, including exam-simulation labs)
18.2 Consolidated Key-Takeaways Checklist
18.3 Common Misconceptions and Anti-Patterns Recap
18.4 Related Technologies and Recommended Next Topics

---

## 2. Prerequisites

| Prerequisite                                    | Needed For     | Introduced                    |
| ------------------------------------------------ | -------------- | ------------------------------ |
| Linux fundamentals (processes, filesystem, users) | Throughout      | Assumed baseline (see [[../2. Linux/00-Roadmap]]) |
| Container/Docker fundamentals (images, layers, runtime) | Part 1, 2, 4  | Briefly recapped in 1.6         |
| YAML syntax                                       | Part 4 onward   | Assumed baseline                |
| Core networking (IP, DNS, TCP/UDP)                | Part 7          | Briefly recapped in 7.1         |

No external topic must be studied before starting; this roadmap builds every Kubernetes-specific prerequisite in place, though Linux and container fundamentals are assumed baseline knowledge.

---

## 3. Learning Phases

| Phase                               | Parts Covered      | Goal                                                  |
| ------------------------------------ | ------------------ | ------------------------------------------------------ |
| Phase 1 — Foundations                | Part 1, 2          | Understand what Kubernetes is and how it's architected |
| Phase 2 — Cluster Bring-Up            | Part 3             | Bootstrap and configure a working cluster               |
| Phase 3 — Core Workloads              | Part 4, 5, 6       | Pods, controllers, advanced workloads, configuration     |
| Phase 4 — Connectivity & Data          | Part 7, 8          | Networking and storage                                   |
| Phase 5 — Scheduling & Access Control | Part 9, 10         | Scheduling internals, RBAC, security fundamentals        |
| Phase 6 — Delivery & Operations        | Part 11, 12, 13    | Packaging, observability, troubleshooting (CKA's largest domain) |
| Phase 7 — Lifecycle & Advanced Security | Part 14, 15      | Cluster maintenance, CKS-level security depth            |
| Phase 8 — Enterprise Scale             | Part 16            | Service mesh, multi-cluster, cloud-provider specifics    |
| Phase 9 — Certification Readiness      | Part 17            | Full CKA/CKAD/CKS exam-style question banks              |
| Phase 10 — Wrap-Up                     | Part 18            | Labs, checklists, next steps                             |

---

## 4. Section-to-File Mapping

Each roadmap subsection (e.g., `1.1`, `2.4`) is authored as its own file, following the `Contents/PartN/Section-NN-PartN-Slug.md` convention shared with this repo's other knowledge bases (Linux, AWS, Azure, GCP, GIT). Section numbers (`§`) are continuous across the entire 18-part roadmap (1–141), not reset per part.

| Part                                                  | Roadmap Range | Continuous § Range | Folder             |
| ------------------------------------------------------ | -------------- | ------------------- | ------------------- |
| Part 1 — Foundations, Orchestration, History            | 1.1–1.7        | §1–§7                | `Contents/Part1/`   |
| Part 2 — Cluster Architecture                           | 2.1–2.8        | §8–§15               | `Contents/Part2/`   |
| Part 3 — Installation and Cluster Bootstrapping         | 3.1–3.8        | §16–§23              | `Contents/Part3/`   |
| Part 4 — Core Workload Objects: Pods and Controllers    | 4.1–4.9        | §24–§32              | `Contents/Part4/`   |
| Part 5 — Advanced Workloads                             | 5.1–5.8        | §33–§40              | `Contents/Part5/`   |
| Part 6 — Configuration and Application Environment      | 6.1–6.7        | §41–§47              | `Contents/Part6/`   |
| Part 7 — Networking                                     | 7.1–7.9        | §48–§56              | `Contents/Part7/`   |
| Part 8 — Storage                                        | 8.1–8.8        | §57–§64              | `Contents/Part8/`   |
| Part 9 — Scheduling                                     | 9.1–9.8        | §65–§72              | `Contents/Part9/`   |
| Part 10 — Security and RBAC                             | 10.1–10.9      | §73–§81              | `Contents/Part10/`  |
| Part 11 — Package Management and Application Delivery   | 11.1–11.7      | §82–§88              | `Contents/Part11/`  |
| Part 12 — Observability                                 | 12.1–12.8      | §89–§96              | `Contents/Part12/`  |
| Part 13 — Troubleshooting                               | 13.1–13.9      | §97–§105             | `Contents/Part13/`  |
| Part 14 — Cluster Maintenance and Lifecycle             | 14.1–14.7      | §106–§112            | `Contents/Part14/`  |
| Part 15 — Advanced Security (CKS Deep Dive)             | 15.1–15.9      | §113–§121            | `Contents/Part15/`  |
| Part 16 — Service Mesh, Multi-Cluster, Enterprise        | 16.1–16.8      | §122–§129            | `Contents/Part16/`  |
| Part 17 — Interview and Exam Preparation (CKA/CKAD/CKS) | 17.1–17.8      | §130–§137            | `Contents/Part17/`  |
| Part 18 — Wrap-Up                                       | 18.1–18.4      | §138–§141            | `Contents/Part18/`  |

**Total: 141 sections across 18 parts.**

---

## 5. Certification Domain Mapping (CKA / CKAD / CKS)

This roadmap is built to directly cover all three Linux Foundation Kubernetes certifications. The mapping below ties each exam's official curriculum domains to the Parts/sections that cover them.

### 5.1 CKA (Certified Kubernetes Administrator)

| Official CKA Domain               | Weight | Covered By                                  |
| ----------------------------------- | ------ | --------------------------------------------- |
| Cluster Architecture, Installation & Configuration | 25%    | Part 2, Part 3, Part 14                        |
| Workloads & Scheduling               | 15%    | Part 4, Part 5, Part 9                         |
| Services & Networking                | 20%    | Part 7                                         |
| Storage                               | 10%    | Part 8                                         |
| Troubleshooting                       | 30%    | Part 13 (plus troubleshooting subsections embedded in Parts 7, 8, 14) |

### 5.2 CKAD (Certified Kubernetes Application Developer)

| Official CKAD Domain                          | Weight | Covered By                        |
| ----------------------------------------------- | ------ | ------------------------------------ |
| Application Design and Build                    | 20%    | Part 4, Part 11 (Helm/Kustomize)     |
| Application Deployment                          | 20%    | Part 4, Part 5                       |
| Application Observability and Maintenance       | 15%    | Part 12                              |
| Application Environment, Configuration and Security | 25% | Part 6, Part 10                      |
| Services and Networking                         | 20%    | Part 7                               |

### 5.3 CKS (Certified Kubernetes Security Specialist — requires active CKA)

| Official CKS Domain                     | Weight | Covered By     |
| ------------------------------------------ | ------ | ---------------- |
| Cluster Setup                              | 10%    | Part 15 (15.1)    |
| Cluster Hardening                          | 15%    | Part 10, Part 15 (15.1) |
| System Hardening                           | 15%    | Part 15 (15.2)    |
| Minimize Microservice Vulnerabilities       | 20%    | Part 15 (15.3, 15.7, 15.8) |
| Supply Chain Security                      | 20%    | Part 15 (15.4, 15.5) |
| Monitoring, Logging and Runtime Security   | 20%    | Part 15 (15.6, 15.9), Part 12 |

Part 17 (§130–137) additionally provides dedicated exam-day strategy and scenario-style question banks for all three certifications.

---

## 6. Cross-Topic Dependency Graph

```text
Foundations, Orchestration & History (P1)
        │
        ▼
Cluster Architecture (P2) ──────────────► Control plane, etcd, CRI
        │
        ▼
Installation & Bootstrapping (P3) ──► kubeadm, managed K8s, local dev clusters
        │
        ▼
Core Workload Objects: Pods & Controllers (P4)
        │
        ├──► Advanced Workloads (P5) ──► StatefulSets, DaemonSets, Jobs, HPA
        │
        ▼
Configuration & Application Environment (P6)
        │
        ▼
Networking (P7) ──► Services, Ingress, NetworkPolicy, CNI
        │
        ├──► Storage (P8) ──► PV/PVC, CSI, StorageClasses
        │
        ▼
Scheduling (P9) ──► Affinity, taints/tolerations, priority
        │
        ▼
Security & RBAC (P10) ──► AuthN/AuthZ, admission control, Pod Security
        │
        ├──► Package Management & Delivery (P11) ──► Helm, Kustomize, GitOps
        │
        ▼
Observability (P12) ──► Probes, metrics, logging, tracing
        │
        ▼
Troubleshooting (P13) ──► CKA's largest domain; synthesizes P2–P12
        │
        ▼
Cluster Maintenance & Lifecycle (P14) ──► Upgrades, backup/restore, DR
        │
        ▼
Advanced Security: CKS Deep Dive (P15) ──► Supply chain, runtime security, hardening
        │
        ▼
Service Mesh, Multi-Cluster, Enterprise (P16) ──► Istio, multi-tenancy, cloud-specific EKS/AKS/GKE
        │
        ▼
Interview & Exam Preparation: CKA/CKAD/CKS (P17)
        │
        ▼
Wrap-Up: Labs & Next Steps (P18) ──► Recommended next topics: Terraform, Ansible, CI/CD, Prometheus/Grafana (deep dive), Service Mesh depth, Docker (if not already known)
```

**Recommended technologies to learn alongside or after Kubernetes:** Docker (if not already known), Helm/Kustomize (built into this roadmap), Terraform, Ansible, CI/CD pipelines, Prometheus/Grafana, Istio/Linkerd, cloud-provider Kubernetes services (EKS/AKS/GKE — see [[../6. Cloud]]).

---

## 7. Roadmap Expansion Backlog

_(Empty at project start. Populated when the user requests additions, gap coverage, or new parts.)_

| Item | Requested Reason / Gap | Placement | Status | Target Filename |
| ---- | ----------------------- | --------- | ------ | ----------------- |
| —    | —                       | —         | —      | —                  |

---

## 8. Current Roadmap State

| #   | Part                                                    | Section    | Status       |
| --- | -------------------------------------------------------- | ----------- | ------------ |
| 01  | Part 1 — Foundations, Orchestration, History              | 1.1–1.7     | ✅ Completed |
| 02  | Part 2 — Cluster Architecture                              | 2.1–2.8     | ⏳ Remaining |
| 03  | Part 3 — Installation and Cluster Bootstrapping            | 3.1–3.8     | ⏳ Remaining |
| 04  | Part 4 — Core Workload Objects: Pods and Controllers       | 4.1–4.9     | ⏳ Remaining |
| 05  | Part 5 — Advanced Workloads                                | 5.1–5.8     | ⏳ Remaining |
| 06  | Part 6 — Configuration and Application Environment         | 6.1–6.7     | ⏳ Remaining |
| 07  | Part 7 — Networking                                        | 7.1–7.9     | ⏳ Remaining |
| 08  | Part 8 — Storage                                           | 8.1–8.8     | ⏳ Remaining |
| 09  | Part 9 — Scheduling                                        | 9.1–9.8     | ⏳ Remaining |
| 10  | Part 10 — Security and RBAC                                | 10.1–10.9   | ⏳ Remaining |
| 11  | Part 11 — Package Management and Application Delivery      | 11.1–11.7   | ⏳ Remaining |
| 12  | Part 12 — Observability                                    | 12.1–12.8   | ⏳ Remaining |
| 13  | Part 13 — Troubleshooting                                  | 13.1–13.9   | ⏳ Remaining |
| 14  | Part 14 — Cluster Maintenance and Lifecycle                | 14.1–14.7   | ⏳ Remaining |
| 15  | Part 15 — Advanced Security (CKS Deep Dive)                | 15.1–15.9   | ⏳ Remaining |
| 16  | Part 16 — Service Mesh, Multi-Cluster, Enterprise Patterns | 16.1–16.8   | ⏳ Remaining |
| 17  | Part 17 — Interview and Exam Preparation (CKA/CKAD/CKS)    | 17.1–17.8   | ⏳ Remaining |
| 18  | Part 18 — Wrap-Up                                          | 18.1–18.4   | ⏳ Remaining |

**Next Section:** Part 2 — Cluster Architecture (§8–§15)
