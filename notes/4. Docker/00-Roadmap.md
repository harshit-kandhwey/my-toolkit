# 00 — Roadmap: Docker (Complete Topic Roadmap)

## 0. Assumption Line

Docker is treated in its most common **DevOps / Cloud / SRE** interpretation: Docker as a production container runtime and image-build tool — container fundamentals, Docker Engine architecture, image and Dockerfile authoring, Docker Compose for multi-container applications, networking, storage/volumes, security hardening, registries and image distribution, build optimization, CI/CD integration, and production operations. This roadmap runs **109 sections across 15 parts**, sized to the same standard of depth as this repo's other tracks (comparable to Linux's 125 and Ansible's 119 sections) rather than a shallow tool overview.

This roadmap deliberately runs right up to, but does **not** include, container **orchestration**. Docker Swarm is covered only briefly as native/legacy context in Part 12, and Kubernetes is intentionally excluded entirely — it is already covered in this repo as its own separate, fully authored 141-section knowledge base (see [[../12. Kubernetes/00-Roadmap]]). Once this roadmap is complete, Kubernetes is the natural next topic for orchestrating the images and containers built here.

Because Docker touches OS-level primitives, networking, storage, security, and CI/CD in addition to core image/container mechanics, this project is split into **named Parts**, generated sequentially. Do not ask which part to start with — Part 1 begins immediately after this roadmap.

---

## 1. Complete Numbered Roadmap

### Part 1 — Foundations and History

1.1 What Docker Is; the Container Model vs. Virtual Machines
1.2 History: dotCloud → Docker Inc. → OCI Standardization
1.3 Docker vs. Podman/LXC/rkt/containerd Standalone — Positioning
1.4 Installation and Setup (Docker Desktop, Docker Engine, Rootless Mode)
1.5 Prerequisites Recap (Linux Namespaces/cgroups, Basic Networking)
1.6 Docker Editions and Licensing Changes (Docker Desktop Licensing History)
1.7 Docker Certified Associate (DCA) Landscape Overview

### Part 2 — Architecture and the Container Runtime

2.1 Docker Engine Architecture: dockerd, containerd, runc
2.2 Client-Server Model: Docker CLI and the REST API
2.3 OCI Specifications: Image Spec and Runtime Spec
2.4 Linux Namespaces Deep Dive (pid, net, mnt, uts, ipc, user)
2.5 Control Groups (cgroups) Deep Dive: v1 vs. v2
2.6 Union Filesystems and Layered Storage (overlay2 Internals)
2.7 containerd and the CRI's Relationship to Kubernetes
2.8 Docker Daemon Configuration (daemon.json, Socket Permissions)

### Part 3 — Images and Dockerfile Authoring

3.1 Image Anatomy: Layers, Manifest, and Config
3.2 Dockerfile Fundamentals: FROM, RUN, COPY, ADD
3.3 CMD vs. ENTRYPOINT — Semantics and Interactions
3.4 WORKDIR, ENV, ARG, and LABEL
3.5 EXPOSE, VOLUME, and USER Instructions
3.6 .dockerignore and Build Context Mechanics
3.7 Base Image Selection (distroless, alpine, slim, scratch)
3.8 Image Tagging Conventions and Semantic Versioning
3.9 Building Images: docker build and BuildKit Basics
3.10 Inspecting Images: docker inspect, history, and dive

### Part 4 — Container Lifecycle and CLI

4.1 docker run Deep Dive: Flags and Common Patterns
4.2 Container Lifecycle: create, start, stop, restart, pause, kill
4.3 Executing Commands in Running Containers: exec and attach
4.4 Container Logs and Log Drivers
4.5 Copying Files: docker cp and Data Exchange Patterns
4.6 Resource Constraints: --memory, --cpus, --pids-limit
4.7 Restart Policies and Health Checks (HEALTHCHECK Instruction)
4.8 Cleaning Up: prune Commands and Disk Usage Management

### Part 5 — Docker Compose and Multi-Container Apps

5.1 Compose File Format: Compose v2 and the Compose Specification
5.2 Services, Networks, and Volumes in docker-compose.yml
5.3 Environment Variables and .env Files
5.4 Dependency Ordering: depends_on, Health Checks, Wait Strategies
5.5 Compose Profiles and Multi-Environment Overrides
5.6 Scaling Services with Compose
5.7 Compose CLI Deep Dive: up, down, logs, exec
5.8 Compose in Local Development Workflows (Hot Reload, Bind Mounts)

### Part 6 — Networking

6.1 Docker Network Drivers Overview: bridge, host, none, overlay, macvlan
6.2 The Default Bridge Network and Custom Bridge Networks
6.3 Container DNS and Service Discovery
6.4 Port Publishing and iptables/nftables Under the Hood
6.5 Overlay Networks and Multi-Host Networking Concepts
6.6 Network Troubleshooting Tools and Techniques
6.7 Container-to-Host and Container-to-Container Communication Patterns
6.8 Network Security: Isolation and Segmentation Patterns

### Part 7 — Storage and Volumes

7.1 Storage Drivers: overlay2 Internals Revisited
7.2 Volumes vs. Bind Mounts vs. tmpfs — When Each Applies
7.3 Named Volumes: Lifecycle and Management
7.4 Volume Drivers and Plugins (NFS, Cloud-Backed Storage)
7.5 Data Persistence Patterns for Stateful Containers
7.6 Backup and Restore Strategies for Volumes
7.7 Storage Performance Considerations

### Part 8 — Security and Hardening

8.1 Container Security Model: What Isolation Does and Doesn't Provide
8.2 Running as Non-Root: USER Instruction and User Namespaces
8.3 Capabilities: --cap-add/--cap-drop and Least Privilege
8.4 Seccomp Profiles
8.5 AppArmor and SELinux with Docker
8.6 Read-Only Filesystems and Immutable Containers
8.7 Image Vulnerability Scanning (Trivy, Docker Scout, Snyk)
8.8 Secrets Management (Docker Secrets, Avoiding ENV-Based Secrets)
8.9 Supply Chain Security: Image Signing, SBOM, Content Trust

### Part 9 — Registries and Image Distribution

9.1 Docker Hub Fundamentals: Public/Private Repos, Rate Limits
9.2 Private Registries: Self-Hosted Registry and Harbor
9.3 Cloud Registries: ECR, ACR, GCR/Artifact Registry
9.4 Authentication: docker login and Credential Helpers
9.5 Image Push/Pull Workflows and Tagging Strategies
9.6 Image Retention Policies and Garbage Collection
9.7 Multi-Architecture Images (buildx, Manifest Lists)

### Part 10 — Build Optimization and Multi-Stage Builds

10.1 Multi-Stage Builds: Pattern and Motivation
10.2 Layer Caching Strategies and Build Cache Invalidation
10.3 BuildKit Deep Dive: Features and Syntax
10.4 Build Secrets and SSH Forwarding During Build
10.5 Minimizing Image Size: Techniques and Trade-offs
10.6 Reproducible Builds and Build Args Best Practices
10.7 docker buildx: Multi-Platform Build Pipelines

### Part 11 — CI/CD Integration

11.1 Docker in CI/CD Pipelines (GitHub Actions, GitLab CI, Jenkins)
11.2 Docker-in-Docker vs. Docker Socket Mounting — Trade-offs
11.3 Automated Image Build-and-Push Pipelines
11.4 Integration Testing with Ephemeral Containers
11.5 GitOps Patterns for Container Image Promotion
11.6 Build Caching Strategies in CI for Faster Pipelines

### Part 12 — Production Operations and Monitoring

12.1 Logging Architectures for Containerized Applications
12.2 Monitoring: cAdvisor, Prometheus, and Container Metrics
12.3 Health Checks and Self-Healing Patterns
12.4 Resource Management at Scale
12.5 Docker Swarm as a Native Orchestrator (Brief, Pre-Kubernetes Context)
12.6 Zero-Downtime Deployment Patterns with Docker
12.7 Disaster Recovery and Rollback Strategies
12.8 Troubleshooting Production Container Issues

### Part 13 — Mastery: Best Practices, Anti-Patterns, and Comparisons

13.1 Dockerfile Best Practices Checklist
13.2 Common Anti-Patterns and Why They Hurt
13.3 Docker vs. Podman vs. Standalone containerd — Detailed Comparison
13.4 When Docker Is the Wrong Tool
13.5 Performance Tuning Recap
13.6 The Path from Docker to Orchestration (Swarm vs. Kubernetes)

### Part 14 — Interview Preparation

14.1 Docker Certified Associate (DCA) Domain Breakdown
14.2 Common Docker Interview Questions (Beginner to Advanced)
14.3 Scenario-Based Troubleshooting Questions
14.4 Dockerfile Code-Review Style Questions
14.5 System Design Questions Involving Containers
14.6 Hands-On Whiteboard/Live-Coding Exercise Bank

### Part 15 — Wrap-Up

15.1 Progressive Hands-On Labs (Beginner → Production-Style)
15.2 Consolidated Key-Takeaways Checklist
15.3 Common Misconceptions and Anti-Patterns Recap
15.4 Related Technologies and Recommended Next Topics

---

## 2. Prerequisites

| Prerequisite                                            | Needed For    | Introduced                                             |
| ------------------------------------------------------- | ------------- | ------------------------------------------------------ |
| Linux fundamentals (processes, filesystem, permissions) | Throughout    | Assumed baseline (see [[../2. Linux/00-Roadmap]])      |
| Linux namespaces and cgroups (conceptual)               | Part 2        | Deep dive in 2.4–2.5, but a passing familiarity helps  |
| Basic networking (IP, DNS, ports)                       | Part 6 onward | Assumed baseline (see [[../3. Networking/00-Roadmap]]) |
| Command-line comfort (shell basics)                     | Throughout    | Assumed baseline                                       |
| YAML syntax                                             | Part 5        | Used directly in Compose files, no deep dive repeated  |

No external topic must be studied before starting; this roadmap builds every Docker-specific prerequisite in place, though Linux and basic networking fundamentals are assumed baseline knowledge.

---

## 3. Learning Phases

| Phase                                           | Parts Covered | Goal                                                          |
| ----------------------------------------------- | ------------- | ------------------------------------------------------------- |
| Phase 1 — Foundations                           | Part 1, 2     | Understand the container model and Docker Engine architecture |
| Phase 2 — Image and Container Mechanics         | Part 3, 4     | Author Dockerfiles and operate the container lifecycle        |
| Phase 3 — Multi-Container Applications          | Part 5        | Compose-based local and multi-service application design      |
| Phase 4 — Platform Fundamentals                 | Part 6, 7     | Networking models and persistent storage                      |
| Phase 5 — Security                              | Part 8        | Hardening containers and the supply chain                     |
| Phase 6 — Distribution and Build Pipeline       | Part 9, 10    | Registries, multi-arch images, and build optimization         |
| Phase 7 — Delivery and Operations               | Part 11, 12   | CI/CD integration and production operations                   |
| Phase 8 — Mastery                               | Part 13       | Best practices, anti-patterns, and tool comparisons           |
| Phase 9 — Certification and Interview Readiness | Part 14       | DCA-style domain review and interview question banks          |
| Phase 10 — Wrap-Up                              | Part 15       | Labs, checklists, and next steps toward orchestration         |

---

## 4. Section-to-File Mapping

Each roadmap subsection (e.g., `1.1`, `4.5`) is authored as its own file, following the `Contents/PartN/Section-NN-PartN-Slug.md` convention shared with this repo's other knowledge bases (Linux, AWS, Azure, GCP, Kubernetes, Ansible, GIT). Section numbers (`§`) are continuous across the entire 15-part roadmap (1–109), not reset per part.

| Part                                                              | Roadmap Range | Continuous § Range | Folder             |
| ----------------------------------------------------------------- | ------------- | ------------------ | ------------------ |
| Part 1 — Foundations and History                                  | 1.1–1.7       | §1–§7              | `Contents/Part1/`  |
| Part 2 — Architecture and the Container Runtime                   | 2.1–2.8       | §8–§15             | `Contents/Part2/`  |
| Part 3 — Images and Dockerfile Authoring                          | 3.1–3.10      | §16–§25            | `Contents/Part3/`  |
| Part 4 — Container Lifecycle and CLI                              | 4.1–4.8       | §26–§33            | `Contents/Part4/`  |
| Part 5 — Docker Compose and Multi-Container Apps                  | 5.1–5.8       | §34–§41            | `Contents/Part5/`  |
| Part 6 — Networking                                               | 6.1–6.8       | §42–§49            | `Contents/Part6/`  |
| Part 7 — Storage and Volumes                                      | 7.1–7.7       | §50–§56            | `Contents/Part7/`  |
| Part 8 — Security and Hardening                                   | 8.1–8.9       | §57–§65            | `Contents/Part8/`  |
| Part 9 — Registries and Image Distribution                        | 9.1–9.7       | §66–§72            | `Contents/Part9/`  |
| Part 10 — Build Optimization and Multi-Stage Builds               | 10.1–10.7     | §73–§79            | `Contents/Part10/` |
| Part 11 — CI/CD Integration                                       | 11.1–11.6     | §80–§85            | `Contents/Part11/` |
| Part 12 — Production Operations and Monitoring                    | 12.1–12.8     | §86–§93            | `Contents/Part12/` |
| Part 13 — Mastery: Best Practices, Anti-Patterns, and Comparisons | 13.1–13.6     | §94–§99            | `Contents/Part13/` |
| Part 14 — Interview Preparation                                   | 14.1–14.6     | §100–§105          | `Contents/Part14/` |
| Part 15 — Wrap-Up                                                 | 15.1–15.4     | §106–§109          | `Contents/Part15/` |

**Total: 109 sections across 15 parts.**

---

## 5. Certification Domain Mapping (Docker Certified Associate — DCA, Historical Reference)

The Docker Certified Associate (DCA) exam has since been retired by Docker/Mirantis, but its domain breakdown remains a useful, widely-referenced framework for structuring practical Docker competence, and many job postings and interview loops still implicitly test against it. Treat the mapping below as orientation, not a live exam blueprint.

| Representative DCA Domain            | Covered By                                 |
| ------------------------------------ | ------------------------------------------ |
| Orchestration (Swarm-era)            | Part 12 (§86–§93, briefly, pre-Kubernetes) |
| Image Creation, Management, Registry | Part 3, Part 9, Part 10                    |
| Installation and Configuration       | Part 1, Part 2                             |
| Networking                           | Part 6                                     |
| Security                             | Part 8                                     |
| Storage and Volumes                  | Part 7                                     |

Part 14 (§100–105) additionally provides a dedicated interview-question bank and hands-on scenario exercises modeled on how Docker competence is actually assessed in modern SRE/DevOps interview loops, since DCA itself is no longer offered as a live certification path.

---

## 6. Cross-Topic Dependency Graph

```text
Foundations and History (P1)
        │
        ▼
Architecture and the Container Runtime (P2) ──────► Namespaces, cgroups, containerd, runc
        │
        ▼
Images and Dockerfile Authoring (P3)
        │
        ▼
Container Lifecycle and CLI (P4)
        │
        ▼
Docker Compose and Multi-Container Apps (P5)
        │
        ├──► Networking (P6)
        ├──► Storage and Volumes (P7)
        │
        ▼
Security and Hardening (P8)
        │
        ▼
Registries and Image Distribution (P9)
        │
        ▼
Build Optimization and Multi-Stage Builds (P10)
        │
        ▼
CI/CD Integration (P11)
        │
        ▼
Production Operations and Monitoring (P12) ──► Swarm as native orchestrator (brief, pre-K8s)
        │
        ▼
Mastery: Best Practices, Anti-Patterns, and Comparisons (P13)
        │
        ▼
Interview Preparation (P14)
        │
        ▼
Wrap-Up: Labs & Next Steps (P15) ──► Recommended next topics: Kubernetes, CI/CD deep dive
```

**Recommended technologies to learn alongside or after Docker:** Kubernetes (orchestration built directly on the images and container model authored here — already fully covered in this repo as a 141-section knowledge base, see [[../12. Kubernetes/00-Roadmap]]), CI/CD pipelines (see [[../9. CI-CD]]), Ansible (configuration management around containerized fleets, see [[../8. Ansible/00-Roadmap]]), Linux fundamentals (already covered — see [[../2. Linux/00-Roadmap]]), Networking fundamentals (see [[../3. Networking]]).

---

## 7. Roadmap Expansion Backlog

_(Empty at project start. Populated when the user requests additions, gap coverage, or new parts.)_

| Item | Requested Reason / Gap | Placement | Status | Target Filename |
| ---- | ---------------------- | --------- | ------ | --------------- |
| —    | —                      | —         | —      | —               |

---

## 8. Current Roadmap State

| #   | Part                                                              | Section   | Status         |
| --- | ----------------------------------------------------------------- | --------- | -------------- |
| 01  | Part 1 — Foundations and History                                  | 1.1–1.7   | ✅ Done        |
| 02  | Part 2 — Architecture and the Container Runtime                   | 2.1–2.8   | ✅ Done        |
| 03  | Part 3 — Images and Dockerfile Authoring                          | 3.1–3.10  | ✅ Done        |
| 04  | Part 4 — Container Lifecycle and CLI                              | 4.1–4.8   | ✅ Done        |
| 05  | Part 5 — Docker Compose and Multi-Container Apps                  | 5.1–5.8   | ✅ Done        |
| 06  | Part 6 — Networking                                               | 6.1–6.8   | ✅ Done        |
| 07  | Part 7 — Storage and Volumes                                      | 7.1–7.7   | ✅ Done        |
| 08  | Part 8 — Security and Hardening                                   | 8.1–8.9   | ✅ Done        |
| 09  | Part 9 — Registries and Image Distribution                        | 9.1–9.7   | ✅ Done        |
| 10  | Part 10 — Build Optimization and Multi-Stage Builds               | 10.1–10.7 | ✅ Done        |
| 11  | Part 11 — CI/CD Integration                                       | 11.1–11.6 | ✅ Done        |
| 12  | Part 12 — Production Operations and Monitoring                    | 12.1–12.8 | ✅ Done        |
| 13  | Part 13 — Mastery: Best Practices, Anti-Patterns, and Comparisons | 13.1–13.6 | ✅ Done        |
| 14  | Part 14 — Interview Preparation                                   | 14.1–14.6 | ✅ Done        |
| 15  | Part 15 — Wrap-Up                                                 | 15.1–15.4 | ✅ Done        |

**Next Section:** None. All 109 sections (§1–§109) are authored. Remaining: README.md, INDEX.md, Certification-Map update.
