# Section 109 (Part 15): Related Technologies and Recommended Next Topics

## 1. Definition

**Plain language:** Docker is one piece of a larger ecosystem. This section maps the technologies that sit below it (runtimes and the kernel), beside it (alternative engines and builders), above it (orchestrators, service meshes, platforms) and around it (CI/CD, infrastructure as code, observability, security). It then proposes a study order for what to learn next.

**Precise definition:** The container ecosystem is layered around the OCI standards ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)). Because the image format, runtime contract and distribution API are standardized, tools at each layer are replaceable: runc can be swapped for crun, gVisor or Kata; Docker Engine for Podman or standalone containerd; Compose for Kubernetes manifests; Docker Hub for ECR. Knowing the boundaries tells you which skills transfer and which are Docker-specific.

> 💡 **Tip:** Skills transfer along the standard. Dockerfiles, OCI images, registries and the namespace/cgroup model carry over almost unchanged; `docker` CLI flags, Compose syntax and Swarm do not.

## 2. Why This Matters

- Roles ask for containers plus Kubernetes, CI/CD, cloud and observability; the container layer underpins all of them.
- Picking the right neighbor tool avoids forcing Docker into jobs it is bad at ([§97](../Part13/Section-97-Part13-When-Docker-Is-the-Wrong-Tool.md)).
- A clear map prevents the common career stall of knowing commands without knowing where each fits in a production platform.
- Certifications form a ladder: DCA first (Docker-specific), then CKA/CKAD/CKS (Kubernetes), then cloud-provider certificates ([§7](../Part1/Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview.md), [§100](../Part14/Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md)).

## 3. Prerequisites and Dependencies

You should be comfortable with the core of this knowledge base: images and Dockerfiles (Part 3), running containers (Part 4), Compose (Part 5), networking and storage (Parts 6 and 7), security (Part 8), registries (Part 9), builds and CI (Parts 10 and 11) and operations (Part 12). Several neighbors build directly on earlier sections: the engine stack ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)), Kubernetes' container runtime interface ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)), the comparison with Podman ([§96](../Part13/Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison.md)) and the orchestration decision ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)). The consolidated checklist ([§107](Section-107-Part15-Consolidated-Key-Takeaways-Checklist.md)) and the misconceptions recap ([§108](Section-108-Part15-Common-Misconceptions-and-Anti-Patterns-Recap.md)) are the best self-assessment before moving on.

## 4. Architecture / Conceptual Diagram

```text
                       THE CONTAINER ECOSYSTEM AROUND DOCKER

  ┌────────────────────────────────────────────────────────────────────────┐
  │ PLATFORM / ORCHESTRATION    Kubernetes ► (EKS AKS GKE, OpenShift, k3s) │
  │                             Nomad, Docker Swarm, ECS, Cloud Run        │
  │ SERVICE LAYER               Ingress, service mesh (Istio, Linkerd),    │
  │                             Helm, Kustomize, operators                 │
  ├────────────────────────────────────────────────────────────────────────┤
  │ DELIVERY                    CI/CD (Actions, GitLab CI, Jenkins),       │
  │                             GitOps (Argo CD, Flux), IaC (Terraform,    │
  │                             Ansible), artifact registries              │
  ├────────────────────────────────────────────────────────────────────────┤
  │ OBSERVE + SECURE            Prometheus, Grafana, Loki, OpenTelemetry   │
  │                             Trivy, Cosign, Falco, OPA/Kyverno          │
  ├──────────────────────────────  THE DOCKER KB  ────────────────────────┤
  │ BUILD / DEVELOP             Docker CLI, BuildKit/buildx, Compose,      │
  │                             Docker Desktop, devcontainers, Testcontainers│
  │ ENGINE                      dockerd ► containerd ► runc                │
  │ ALTERNATIVES                Podman, Buildah, Kaniko, nerdctl, CRI-O    │
  ├────────────────────────────────────────────────────────────────────────┤
  │ STANDARDS                   OCI image spec, runtime spec, distribution │
  ├────────────────────────────────────────────────────────────────────────┤
  │ ISOLATION                   namespaces, cgroups v2, seccomp, LSMs;     │
  │                             gVisor, Kata, Firecracker for stronger     │
  │                             boundaries                                 │
  ├────────────────────────────────────────────────────────────────────────┤
  │ KERNEL + HOST               Linux (VM on Mac/Windows), eBPF, iptables  │
  └────────────────────────────────────────────────────────────────────────┘

   Study direction: stay in the Docker band until it feels boring, then go
   UP (orchestration) for compute scale or SIDE (delivery, observe) for
   production maturity.
```

- **Below Docker** you meet the Linux primitives; **beside it** the alternative implementations of the same standard; **above it** the systems that schedule many containers across many hosts.
- The OCI line is the portability contract: anything above it consumes images; anything below it runs them.
- Delivery and observability are orthogonal to orchestration; you need them even on a single host.

## 5. Hands-On

A short tour that demonstrates how standards make neighbors interchangeable. Run these in a disposable environment.

### 5.1 Same image, different engines

```bash
docker save alpine:3.20 -o alpine.tar
podman load -i alpine.tar                  # if Podman is installed
podman run --rm alpine:3.20 cat /etc/os-release | head -2
nerdctl --namespace demo load -i alpine.tar   # if containerd + nerdctl installed
```

```text
NAME="Alpine Linux"
ID=alpine
```

The OCI/Docker image tarball is engine-neutral ([§10](../Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md), [§96](../Part13/Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison.md)).

### 5.2 See the runtime stack your host actually uses

```bash
docker info --format 'Runtime: {{.DefaultRuntime}}  Runtimes: {{json .Runtimes}}  CgroupVersion: {{.CgroupVersion}}'
docker info --format 'Driver: {{.Driver}}  Containerd: {{.ContainerdCommit.ID}}'
```

```text
Runtime: runc  Runtimes: {"io.containerd.runc.v2":{"path":"runc"},"runc":{"path":"runc"}}  CgroupVersion: 2
Driver: overlayfs  Containerd: 7e3c...
```

Newer engines using the containerd image store report `overlayfs`; the classic store reports `overlay2` ([§13](../Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)). Alternative runtimes (gVisor `runsc`, Kata) register in this same `Runtimes` map via `daemon.json` and are selected per container with `--runtime` ([§15](../Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md)).

## 6. Production Usage Notes

Technologies by relationship, with a recommendation for when each matters.

### 6.1 Below and beside Docker

| Technology | Relationship | When to learn it |
|---|---|---|
| containerd, runc | Engine internals; Kubernetes' default runtime stack | Early; needed to debug nodes ([§8](../Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md), [§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)) |
| Podman, Buildah, Skopeo | Daemonless, rootless-first alternatives with compatible CLI | RHEL/Fedora fleets, rootless policy, registry copy tooling |
| nerdctl, Lima, Colima, Rancher Desktop | Docker-compatible CLI or Desktop replacements | Desktop licensing concerns ([§6](../Part1/Section-06-Part1-Docker-Editions-and-Licensing-Changes.md)) |
| gVisor, Kata Containers, Firecracker | Stronger isolation (user-space kernel or micro-VM) behind the same OCI interface | Multi-tenant or untrusted code ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)) |
| Linux kernel features: eBPF, cgroups v2, user namespaces | The substance beneath every container | Deep debugging and security work ([§11](../Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md), [§12](../Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)) |

### 6.2 Above Docker: orchestration and platforms

| Technology | Role | Guidance |
|---|---|---|
| Kubernetes | De facto standard scheduler: self-healing, rollouts, scaling, service discovery | The primary next topic; see section 6.5 |
| Managed Kubernetes (EKS, AKS, GKE) | Hosted control plane | Preferred over self-managed control planes for most teams |
| Docker Swarm | Native, simple orchestration | Small, stable estates; limited ecosystem ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md)) |
| AWS ECS/Fargate, Azure Container Apps, Google Cloud Run | Serverless or provider-native container platforms | When you want containers without running a cluster |
| Helm, Kustomize | Package and template Kubernetes manifests | First tools after core Kubernetes objects |

### 6.3 Around Docker

CI/CD and GitOps ([§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md), [§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)); Terraform/OpenTofu and Ansible for infrastructure; registries ([§66](../Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md)); Prometheus, Grafana and OpenTelemetry for observability ([§87](../Part12/Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)); Trivy, Syft and Cosign for supply chain ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)); Falco, OPA and Kyverno for runtime policy; Vault and External Secrets for secrets.

### 6.4 Recommended learning paths

Pick the path that matches your role. Each starts from where this knowledge base ends.

1. **Platform / SRE track:** Kubernetes core objects ► networking and storage in Kubernetes ► Helm and GitOps ► observability stack ► cluster operations and security. Target: CKA, then CKS.
2. **Application developer track:** Kubernetes workloads and configuration ► Skaffold or Tilt inner loop ► Testcontainers ► CI/CD pipelines ► CKAD.
3. **Security track:** supply chain (SBOM, signing) ► runtime security (Falco, seccomp, AppArmor) ► Kubernetes policy and RBAC ► sandboxed runtimes ► CKS.
4. **Cloud / infrastructure track:** Terraform for registries, clusters and networks ► managed Kubernetes ► IAM and workload identity ► cost control (right-sizing, image pulls, node pools).
### 6.5 The default next step: Kubernetes

Kubernetes is the next knowledge base in this repository: [Kubernetes, Part 1 first section](../../../12.%20Kubernetes/Contents/Part1/Section-01-Part1-What-Kubernetes-Is-Container-Orchestration-Problem.md). What carries over and what is new:

| Carries over from Docker | New in Kubernetes |
|---|---|
| OCI images, registries, tags and digests | Pods as the scheduling unit (one or more containers sharing network and volumes) |
| Dockerfile, entrypoint/CMD semantics ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)) | Declarative desired state and reconciliation controllers |
| Namespaces/cgroups as the isolation model | Control plane (API server, etcd, scheduler, controller manager) and kubelet |
| Resource limits (`--memory`, `--cpus`) | Requests, limits, QoS classes, quotas, autoscaling |

## 7. Security Considerations

- Every new layer adds attack surface (Kubernetes API and RBAC, pipeline credentials, registry publish rights); learn each layer's security model as you adopt it ([§57](../Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md)).
- Podman's rootless default and Docker's rootful default differ in blast radius; hardening guides do not transfer automatically.
- Pin and verify third-party controllers, charts and scanners as supply chain inputs ([§65](../Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)); prefer workload identity to long-lived keys ([§64](../Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)).
- Match isolation to trust: runc for first-party services, gVisor, Kata or Firecracker for customer code. The rules in [§107](Section-107-Part15-Consolidated-Key-Takeaways-Checklist.md) apply unchanged inside a cluster.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely cause | Fix |
|---|---|---|
| `CrashLoopBackOff` for an image that works in Docker | `command`/`args` mismatch or read-only root | Compare with ENTRYPOINT/CMD ([§18](../Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)); add `emptyDir` |
| `ImagePullBackOff` | Auth, rate limit or wrong arch | Pull secret, mirror, multi-arch ([§72](../Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)) |
| No `docker` on nodes | Nodes use containerd | Use `crictl` or `nerdctl` ([§14](../Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)) |
| `depends_on` ordering lost | No start-order primitive | Readiness probes, retries ([§37](../Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)) |
| Rootless Podman cannot bind port 80 | Unprivileged port floor | Lower `ip_unprivileged_port_start` or use a high port |

## 9. Best Practices

- Reproduce one workload on Docker, Podman and a local Kubernetes (kind or k3s) to learn the boundaries.
- Stay on the standards: OCI images, standard registries, the Compose Specification.
- Add one layer at a time; master Kubernetes basics before Helm, a mesh and operators.
- Automate the path to production and practice rollback ([§82](../Part11/Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md), [§92](../Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)).
- Document why you chose Swarm, ECS or Kubernetes ([§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)).

## 10. Common Anti-Patterns / Mistakes

- Jumping to Kubernetes before understanding images, networking and storage.
- Adopting a mesh, operators and GitOps for three services.
- Treating Compose-to-Kubernetes converters as a finished migration.
- Collecting certifications without hands-on practice.
- Self-managing a control plane when a managed one fits.
- Running stateful databases on an orchestrator with no restore plan ([§54](../Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)).

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between Docker, containerd, runc and Kubernetes?"_
**Model answer:** runc is the low-level runtime that sets up namespaces, cgroups and the root filesystem and starts the container process. containerd is a daemon that manages images, snapshots and container lifecycles and calls runc. Docker Engine (dockerd) adds the developer experience on top: CLI, REST API, build, networking, volumes and Compose integration, and delegates execution to containerd. Kubernetes is a different layer entirely: an orchestrator that schedules containers across many machines, using a CRI-compatible runtime (usually containerd or CRI-O) on each node. All of them rely on the OCI image and runtime specifications, which is why an image built with Docker runs under Kubernetes.
_What the interviewer is probing for:_ A correct layered picture of the stack and awareness of OCI as the contract.

**🎯 Intermediate:** _"When would you choose Podman over Docker, and what do you give up?"_
**Model answer:** Podman is daemonless and rootless-first, integrates well with systemd and SELinux, and runs pods natively, so it suits locked-down Linux hosts, RHEL-based fleets, and environments where a root-owned daemon is unacceptable. It accepts the same Dockerfile and OCI images, and its CLI is largely compatible. What you give up is some Docker-specific ecosystem polish: Docker Desktop features and extensions, certain Compose edge cases, Swarm, and the large body of tooling and tutorials that assume the Docker socket (though Podman provides a compatible socket). I would validate networking, rootless port binding, volume ownership and CI integrations before committing.
_What the interviewer is probing for:_ Balanced judgment grounded in architecture (daemon, root) rather than brand preference.

**🎯 Senior:** _"A team has a ten-service Compose application on one VM and wants Kubernetes. How do you decide, and how do you migrate?"_
**Model answer:** First test the need: do they require multi-host scheduling, rolling updates with automated rollback, autoscaling, self-healing across node failure, or multi-team multi-tenancy? If a single VM with good backups and a CI deploy script meets the availability target, Compose (or a managed container service such as ECS/Cloud Run) may be cheaper. If the need is real, migrate incrementally: harden images first (non-root, health endpoints, graceful shutdown, 12-factor configuration), move to a managed cluster, translate services to Deployments, Services and Ingress, replace `depends_on` with readiness probes and retries, move data stores to managed databases or well-operated StatefulSets, externalize secrets, and add observability before cutover. Run both in parallel with traffic shifting, keep rollback to the VM until confidence is built, and measure with SLOs rather than gut feel.
_What the interviewer is probing for:_ Need-driven migration decision, incremental plan, and stateful and operational awareness.

**🎯 Architect:** _"Design the container platform strategy for a 200-engineer company that currently has scattered Docker hosts. What are the layers, build-versus-buy choices and a 24-month roadmap?"_
**Model answer:** Define layers: standards (OCI images, one Dockerfile and base-image policy), supply chain (central registry with replication, scanning, SBOM, signing and admission verification), compute (managed Kubernetes per environment and region, plus a serverless container option for simple services), delivery (paved-road CI templates and GitOps promotion by digest), observability (metrics, logs, traces with shared conventions) and governance (policy as code, cost allocation, identity via workload identity). Buy managed control planes, registries and observability backends unless there is a strong reason to build; build thin internal developer tooling and templates that encode your standards. Roadmap: first six months consolidate images and CI, centralize the registry and scanning, and stand up one production cluster with two pilot teams; months 6 to 12 migrate stateless services, add GitOps and policy enforcement, and publish SLOs; months 12 to 24 migrate remaining workloads, add multi-region and sandboxed runtimes for untrusted code, and retire legacy hosts. Track adoption and risk with measurable indicators and keep an exit path from every vendor-specific component.
_What the interviewer is probing for:_ Layered thinking, build-versus-buy reasoning, phased delivery and governance.

## 12. Common Misconceptions

- "Kubernetes dropped dockershim, so Docker is obsolete." OCI images and Dockerfiles are unaffected.
- "Kubernetes replaces Docker." It orchestrates containers that a runtime runs.
- "Podman and Docker images are incompatible." Both use OCI images.
- "A mesh or GitOps is required." Both are optional layers.

## 13. 🔑 Key Takeaways

- The OCI standards make images, runtimes and registries interchangeable across Docker, Podman, containerd, CRI-O and Kubernetes.
- Docker skills transfer: Dockerfiles, image practices, registries, security hygiene and isolation concepts carry straight into any orchestrator.
- Kubernetes is the natural next step for multi-host scheduling, rollouts, self-healing and scaling; Swarm, Nomad and managed container services fit smaller or simpler needs.
- Delivery (CI/CD, GitOps), infrastructure as code, observability and supply chain security are the surrounding disciplines that make containers production-ready.
- Choose neighbors by need: Podman for rootless and daemonless hosts, gVisor or Kata for untrusted code, Testcontainers for test fixtures.
- Add one layer at a time and keep the security checklist from this KB intact at every layer.
- Recommended continuation: the Kubernetes knowledge base in this repository.

## 14. Related Concepts & What's Next

Related: alternative engines and comparison ([§3](../Part1/Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md), [§96](../Part13/Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison.md)), orchestration decision ([§90](../Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md), [§99](../Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)), CI/CD and GitOps ([§80](../Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md), [§84](../Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)), the consolidated checklist ([§107](Section-107-Part15-Consolidated-Key-Takeaways-Checklist.md)) and the misconceptions recap ([§108](Section-108-Part15-Common-Misconceptions-and-Anti-Patterns-Recap.md)). Related notes in this repository cover Terraform, Ansible, CI/CD, Prometheus, Grafana and Linux, which map to the delivery, infrastructure, observability and kernel layers in the diagram above.

This is the last section of the Docker knowledge base; the Docker knowledge base is complete. The recommended continuation is the Kubernetes knowledge base at `notes/12. Kubernetes`, beginning with [What Kubernetes Is and the Container Orchestration Problem](../../../12.%20Kubernetes/Contents/Part1/Section-01-Part1-What-Kubernetes-Is-Container-Orchestration-Problem.md).

**Next Section:** None. The Docker knowledge base is complete. Continue with the Kubernetes knowledge base: [Kubernetes §1](../../../12.%20Kubernetes/Contents/Part1/Section-01-Part1-What-Kubernetes-Is-Container-Orchestration-Problem.md) — `notes/12. Kubernetes/Contents/Part1/Section-01-Part1-What-Kubernetes-Is-Container-Orchestration-Problem.md`
