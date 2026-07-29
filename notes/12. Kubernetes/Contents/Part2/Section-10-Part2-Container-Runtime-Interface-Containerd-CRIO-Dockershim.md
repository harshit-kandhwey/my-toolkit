# Section 10 (Part 2): Container Runtime Interface (CRI): containerd, CRI-O, and the Dockershim Removal

## 1. Definition

**Plain language:** Kubernetes doesn't hardcode itself to work with one specific container tool. Instead, it defines a standard "plug" (an interface) that any compliant container runtime can be plugged into — which is exactly why Kubernetes could stop supporting Docker directly without breaking the vast majority of workloads running on it.

**Precise definition:** The **Container Runtime Interface (CRI)** is a gRPC-based API that decouples the kubelet from any specific container runtime implementation. Any runtime that implements the CRI's `RuntimeService` and `ImageService` interfaces — most notably **containerd** and **CRI-O** — can serve as a node's container runtime, interchangeably from the kubelet's perspective. Docker Engine predates the CRI and never natively implemented it; Kubernetes used a compatibility shim called **dockershim** to let kubelet talk to Docker via CRI-shaped calls, which was removed in Kubernetes 1.24 (2022) in favor of requiring a native CRI runtime directly.

## 2. Why the CRI Matters

- **It's the reason multiple container runtimes can coexist in the Kubernetes ecosystem at all.** Before the CRI existed, kubelet had runtime-specific code baked in; the CRI abstraction let the Kubernetes project stop maintaining that runtime-specific code directly and let the runtime ecosystem evolve independently.
- **It's the reason the dockershim removal was far less disruptive than headlines suggested.** Since dockershim only ever existed to let kubelet call Docker _as if_ it were CRI-compliant, removing it didn't remove the ability to run Docker-built container images — it removed the ability to use the Docker Engine daemon specifically as the runtime doing the running. Any image built with `docker build` runs identically under containerd or CRI-O, because container images are a standardized OCI format, not a Docker-specific concept.
- **It's directly, frequently tested exam content.** Understanding exactly what changed (and, just as importantly, what didn't) in the dockershim removal is a common CKA-style question, since it's an area rich with easy-to-hold misconceptions.

🔑 **Key Takeaway:** The CRI is the abstraction layer that decouples kubelet from any specific runtime; the 2022 dockershim removal ended Docker Engine's use _as the runtime_, but changed essentially nothing for workloads themselves, since Docker-built images are standard OCI images that run identically under containerd or CRI-O.

## 3. Prerequisites and Dependencies

Builds directly on §9's introduction of the container runtime as one of the three node components. No new external prerequisites.

## 4. Architecture Diagram

```text
                          kubelet
                             │
                             │  CRI (gRPC): RuntimeService, ImageService
                             ▼
              ┌────────────────────────────────┐
              │   Any CRI-compliant runtime:   │
              │                                │
              │   containerd  ── or ──  CRI-O  │
              └──────────────┬─────────────────┘
                             │  OCI Runtime Spec
                             ▼
              ┌────────────────────────────────┐
              │   Low-level runtime (runc,     │
              │   crun) — actually creates     │
              │   namespaces/cgroups, starts   │
              │   the container process        │
              └────────────────────────────────┘

  BEFORE Kubernetes 1.24:              AFTER Kubernetes 1.24:
  kubelet → dockershim → Docker        kubelet → containerd/CRI-O directly
            Engine → containerd
            (extra translation hop)    (dockershim hop removed; Docker
                                         Engine itself no longer usable
                                         as the Kubernetes runtime)
```

- **The CRI sits between kubelet and the runtime**, not between the runtime and the actual OS-level container creation — that lower-level work is handled by an OCI-compliant runtime like `runc` (used by both containerd and CRI-O under the hood in most configurations).
- **Docker Engine itself always used containerd internally** (Docker adopted containerd as its own runtime component years before Kubernetes' dockershim removal) — which is part of why the practical impact of the removal was smaller than expected: many "Docker" clusters were already running on top of containerd one layer down.

## 5. Hands-On: Inspecting the Runtime a Node Actually Uses

### 5.1 `kubectl get nodes -o wide` — Check the Runtime Column

**Purpose:** The node's reported runtime and version are visible directly from `kubectl`.

**Syntax:**

```bash
kubectl get nodes -o wide
```

**Example usage and expected output:**

```bash
$ kubectl get nodes -o wide
NAME       STATUS   ROLES    AGE   VERSION   CONTAINER-RUNTIME
worker-1   Ready    <none>   30d   v1.30.2   containerd://1.7.13
worker-2   Ready    <none>   30d   v1.30.2   containerd://1.7.13
```

**Production usage example:** This is the fastest way to confirm whether a cluster has already migrated off dockershim (any modern cluster on a supported Kubernetes version will show `containerd://` or `cri-o://` here, never `docker://`) — a common first check when inheriting an unfamiliar or older cluster.

### 5.2 `crictl` — Runtime-Level Debugging Beneath kubectl

**Purpose:** `crictl` is a CLI tool that talks directly to a CRI runtime, analogous to how the `docker` CLI talks to the Docker daemon — used when `kubectl`'s Pod-level view isn't enough detail.

**Syntax:**

```bash
crictl ps
crictl images
crictl logs <container-id>
```

**Example usage and expected output:**

```bash
$ crictl ps
CONTAINER ID   IMAGE               STATE      NAME    POD ID
a1b2c3d4e5f6   nginx:1.25          Running    web     f6e5d4c3b2a1
```

**Production usage example:** When a Pod is stuck in a confusing state and `kubectl describe pod`'s Events aren't detailed enough, SSHing onto the affected node and running `crictl ps`/`crictl inspect` gives direct runtime-level visibility that `kubectl` doesn't expose — a standard escalation step in real incident response (§99, Part 13).

**Common errors:** Running `crictl` without specifying the correct runtime endpoint socket (e.g., `/run/containerd/containerd.sock`) results in a connection error — `crictl` needs to know which runtime's socket to talk to, configurable via `/etc/crictl.yaml` or the `--runtime-endpoint` flag.

## 6. Production Usage Notes: What the Dockershim Removal Actually Changed

- **What did NOT change:** Container images built with `docker build` are standard OCI-format images and run identically under containerd or CRI-O. `Dockerfile`-based build workflows are entirely unaffected — the removal was about the _runtime_ executing containers on nodes, not the _build tooling_ developers use locally.
- **What DID change:** Clusters that explicitly configured Docker Engine as their Kubernetes container runtime needed to migrate their node configuration to containerd or CRI-O directly before upgrading past Kubernetes 1.24 — a real, one-time migration for teams that hadn't already moved, but a node-configuration change, not an application-level one.
- **Common source of unnecessary panic in 2022:** Many teams initially worried "Docker is being removed from Kubernetes" in a way that implied their applications or Dockerfile-based CI pipelines would break — in practice, almost no application-facing behavior changed, and the actual work was a node-runtime-configuration migration handled once by whoever managed the cluster infrastructure.

## 7. Security Considerations

- containerd and CRI-O have different default security postures and configuration surfaces (e.g., CRI-O is often chosen in security-conscious OpenShift-style environments for its minimal, Kubernetes-specific design) — a platform team's runtime choice is a genuine, if usually secondary, security consideration (§113, Part 15).
- Runtime-level access (via `crictl` or direct socket access) on a node is equivalent to significant control over that node's containers — securing access to the container runtime's socket is part of node-level hardening.

## 8. Common Troubleshooting Scenarios

| Symptom                                                     | Likely Cause                                                               | Resolution Path                                                                                                            |
| ----------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Cluster upgrade to a recent Kubernetes version fails/blocks | Still configured with Docker Engine as the runtime on unsupported versions | Migrate node container runtime to containerd or CRI-O before upgrading (§106, Part 14)                                     |
| `crictl` commands fail with a connection error              | Wrong or unspecified runtime endpoint socket                               | Check `/etc/crictl.yaml` or pass `--runtime-endpoint` explicitly matching the node's actual runtime                        |
| Confusion about whether "Docker" images still work          | Misunderstanding of what the dockershim removal actually changed           | Clarify: OCI images built by any tool run identically; only the Docker Engine daemon as the Kubernetes runtime was removed |

## 9. Best Practices

- Verify the container runtime column in `kubectl get nodes -o wide` when inheriting or auditing an unfamiliar cluster, especially one that might predate Kubernetes 1.24.
- Keep `crictl` configured and available on nodes for runtime-level debugging that goes beneath what `kubectl` alone can show.
- When explaining the dockershim removal to a team, separate "build tooling" (unaffected) from "cluster runtime configuration" (the actual, one-time migration) to avoid unnecessary alarm.

## 10. Common Anti-Patterns / Mistakes

- **Believing the dockershim removal meant "Docker images no longer work on Kubernetes."** OCI-format images work identically regardless of runtime; only Docker Engine specifically as the node-level runtime was affected.
- **Running an old, unsupported Kubernetes version indefinitely to avoid a runtime migration**, missing security patches in the process rather than completing what is typically a well-documented, one-time infrastructure change.
- **Not knowing `crictl` exists**, and being stuck with only `kubectl`'s Pod-level abstraction during a node-level incident that genuinely requires runtime-level visibility.

## 11. Interview Questions

**🎯 Beginner:** _"What is the Container Runtime Interface, and why does it exist?"_
**Model answer:** The CRI is a standardized API that lets kubelet talk to any compliant container runtime the same way, rather than having runtime-specific code built into kubelet itself. This is why Kubernetes can support multiple runtimes (containerd, CRI-O) interchangeably — any runtime implementing the CRI's interface works without kubelet needing runtime-specific logic.
_What the interviewer is probing for:_ Basic understanding of why the CRI abstraction exists, not just that "Docker was removed."

**🎯 Intermediate:** _"Explain what actually changed when dockershim was removed in Kubernetes 1.24, and what a team needed to do about it."_
**Model answer:** Dockershim was a compatibility layer letting kubelet call Docker Engine as if it were CRI-compliant, since Docker predates the CRI and never natively implemented it. Removing it meant Docker Engine could no longer be used directly as the Kubernetes container runtime — clusters still configured that way needed to migrate node configuration to a native CRI runtime, typically containerd, before upgrading past 1.24. It did not affect container images themselves; anything built with `docker build` is a standard OCI image that runs identically under containerd or CRI-O, so application teams and CI pipelines were generally unaffected — this was a node-infrastructure migration, not an application-level change.
_What the interviewer is probing for:_ Accurate, specific knowledge of the actual scope of the change, correcting the common overreaction many teams had in 2022.

**🎯 Senior:** _"A team is worried that migrating from Docker Engine to containerd as their Kubernetes runtime will require changes to their CI/CD pipelines and Dockerfiles. How would you address this concern?"_
**Model answer:** I'd clarify the distinction between build-time tooling and runtime execution: `docker build` produces a standard OCI-format image regardless of what will eventually run it, so CI pipelines building images with Docker (or any OCI-compliant builder) require zero changes. The migration is purely a node-level infrastructure change — reconfiguring the kubelet's CRI socket to point at containerd instead of going through dockershim to Docker Engine — which is typically handled by the platform/infrastructure team during a node OS image or kubeadm configuration update, invisible to application developers. I'd validate this concretely by testing a sample deployment against a containerd-based node before the full migration, but the underlying architectural reason (OCI image standardization) is why this concern, while understandable, doesn't hold up in practice.
_What the interviewer is probing for:_ Ability to reassure a team with accurate technical reasoning (OCI standardization) rather than just asserting "it'll be fine."

**🎯 Architect:** _"You're choosing between containerd and CRI-O as the standard runtime for a new large-scale Kubernetes platform. Given that both are CRI-compliant, what actually differentiates them, and how do you decide?"_
**Model answer:** Since both fully satisfy the CRI, the choice doesn't affect application-facing behavior at all — it comes down to secondary factors: containerd has the broadest ecosystem adoption and is the default in most managed offerings (EKS, GKE) and distributions, generally meaning more community familiarity and tooling; CRI-O was purpose-built specifically for Kubernetes (no extra features beyond what Kubernetes needs) and is common in security-conscious, minimal-footprint environments like OpenShift. I'd weigh ecosystem familiarity and operational tooling maturity (favoring containerd for most general-purpose platforms) against a specifically minimal, Kubernetes-only footprint requirement (favoring CRI-O) — and I'd be explicit with stakeholders that this is a lower-stakes decision than it might sound, precisely because CRI compliance means workloads are portable between them if the choice needs to change later.
_What the interviewer is probing for:_ Whether the candidate correctly scopes this as a secondary, largely operational decision rather than treating it as a major architectural fork, while still being able to name genuine differentiators.

## 12. Common Misconceptions

1. **"The dockershim removal means Docker-built images don't work on Kubernetes anymore."** OCI-format images are runtime-agnostic; only using Docker Engine itself as the node's runtime was affected.
2. **"containerd and CRI-O are Docker's competitors doing something totally different."** Both are CRI-compliant container runtimes serving the same fundamental role Docker Engine used to (via dockershim) — and Docker Engine itself has used containerd internally for years.
3. **"CRI is Kubernetes-specific low-level container creation."** The CRI itself doesn't create containers — it's the API contract between kubelet and a runtime; the actual namespace/cgroup-level work happens one layer further down via an OCI runtime like `runc`.

## 13. 🔑 Key Takeaways

- The CRI is a gRPC API decoupling kubelet from any specific container runtime implementation, enabling containerd and CRI-O to serve interchangeably as a node's runtime.
- Docker Engine predates the CRI and never natively implemented it; dockershim was a compatibility layer, removed in Kubernetes 1.24.
- The dockershim removal changed node-level runtime configuration, not application images — OCI-format images built by any tool run identically regardless of runtime.
- `crictl` provides runtime-level debugging visibility beneath what `kubectl` exposes, a standard escalation tool in real node-level incidents.
- Choosing between containerd and CRI-O is a secondary, largely operational decision given both are CRI-compliant and interchangeable from the workload's perspective.

## 14. Related Concepts & What's Next

§9 introduced the container runtime as one of three node components this section covers in full technical depth. §46 (Part 3) covers static Pods, which is how kubelet runs control-plane components directly from local manifests before a full api-server is available. §106 (Part 14) covers cluster upgrade mechanics, including scenarios where a lingering Docker Engine runtime configuration must be migrated first. §97–§101 (Part 13) build the full node-level troubleshooting methodology this section's `crictl` introduction supports directly.

**Next Section:** §11 — `Section-11-Part2-API-Server-Deep-Dive-Groups-Versioning-Admission-Chain.md`
