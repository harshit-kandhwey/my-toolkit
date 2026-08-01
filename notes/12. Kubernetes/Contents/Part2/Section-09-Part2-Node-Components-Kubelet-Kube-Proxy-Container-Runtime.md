# Section 9 (Part 2): Node Components: kubelet, kube-proxy, container runtime

## 1. Definition

**Plain language:** If the control plane is the brain deciding what should happen, every worker node has its own small set of "hands" that actually make it happen — one that talks to the control plane and manages containers, one that manages network traffic rules, and one that actually starts and stops container processes.

**Precise definition:** Every Kubernetes worker node runs three components that together implement the data-plane half of the architecture introduced in §3: **kubelet** (the primary node agent that registers the node with the control plane, watches for Pods assigned to it, and ensures their containers are running as specified), **kube-proxy** (maintains network rules on the node that implement Kubernetes' Service abstraction, covered fully in §51), and a **container runtime** (the actual software — containerd or CRI-O — that creates and manages container processes, communicating with the kubelet via the **Container Runtime Interface**, covered in §11).

## 2. Why Understanding Each Component Individually Matters

- **The kubelet is the single point of contact between a node and the control plane.** If it crashes or loses connectivity, the node's existing Pods often keep running (their processes don't depend on continuous kubelet supervision to keep executing) but the node stops reporting status and can't accept new assignments — a specific, recognizable failure mode covered in §97 (Part 13).
- **kube-proxy is invisible until Service networking breaks.** Most engineers never think about kube-proxy directly, but "a Service isn't routing traffic correctly" almost always traces back to kube-proxy's rules on the relevant node(s) — understanding what it actually does removes a huge amount of networking mystery (§51, Part 7).
- **The container runtime split (kubelet talks CRI, not directly to Docker) explains the 2020s "dockershim removal" disruption** many teams experienced — understanding the CRI abstraction (§11) explains why that transition happened and what it actually changed operationally (mostly nothing, for workloads using standard container images).

🔑 **Key Takeaway:** Every node runs exactly three components — kubelet (control-plane liaison and container supervisor), kube-proxy (Service networking rules), and a container runtime (actual container execution) — and node-side troubleshooting almost always starts by identifying which of these three is implicated.

## 3. Prerequisites and Dependencies

Builds on §3 (control plane vs. data plane) and §8 (control-plane components this section's node components communicate with). No new external prerequisites.

## 4. Architecture Diagram

```text
                     kube-apiserver (control plane)
                              ▲  │
                    reports    │  │  assigns Pods,
                    status,    │  │  desired state
                    watches    │  ▼
                    for work ┌──────────────────────────────┐
                             │         kubelet              │
                             │  (per-node agent)            │
                             │  - registers node            │
                             │  - watches for assigned Pods │
                             │  - runs liveness/readiness   │
                             │    probes (§89, Part 12)     │
                             └──────────┬───────────────────┘
                                        │ CRI (gRPC API)
                                        ▼
                             ┌──────────────────────────────┐
                             │   Container Runtime          │
                             │   (containerd or CRI-O)      │
                             │  - pulls images              │
                             │  - creates/starts/stops      │
                             │    container processes       │
                             └──────────────────────────────┘

                             ┌──────────────────────────────┐
                             │        kube-proxy            │
                             │  (per-node, independent)     │
                             │  - watches Services/Endpoints│
                             │  - programs iptables/IPVS    │
                             │    rules for traffic routing │
                             └──────────────────────────────┘
```

- **kubelet does not run containers itself** — it delegates that to the container runtime via the CRI, a clean separation that lets Kubernetes support multiple runtimes without changing kubelet's own code.
- **kube-proxy operates independently of the kubelet** — it watches Service/Endpoint objects via the api-server directly and programs the node's networking rules accordingly; it has no direct relationship with which specific Pods the kubelet happens to be running.

## 5. Component-by-Component Deep Dive

### 5.1 kubelet — The Node Agent

**Purpose:** Registers the node with the cluster, continuously watches the api-server for Pods scheduled to run on this specific node, and ensures the containers described in each Pod's spec are actually running — restarting them per the Pod's restart policy if they exit unexpectedly, and executing liveness/readiness/startup probes against them.

**Key characteristics:**

- Reports node and Pod status back to the api-server, which is what populates `kubectl get nodes` and `kubectl get pods` output.
- Runs **static Pods** directly from local manifest files without going through the api-server for their initial definition (§46, Part 3) — this is how kubeadm-bootstrapped clusters run control-plane components as Pods even before a full api-server is available.

**Production usage example:** A `kubectl describe pod` showing recent events like "Pulling image," "Pulled," "Created," "Started" are all kubelet-reported events, generated as it walks through getting a Pod's containers running via the container runtime.

### 5.2 kube-proxy — The Service Networking Enforcer

**Purpose:** Watches the api-server for Service and Endpoint (or EndpointSlice) objects, and programs the local node's networking rules (via iptables or IPVS, §52) so that traffic sent to a Service's virtual IP gets correctly routed to one of the Pods backing it.

**Key characteristics:**

- Runs on every node as a DaemonSet (§34, Part 5 covers DaemonSets) — each node needs its own copy since networking rules are per-node.
- Does not carry traffic itself — it programs the kernel's networking rules (iptables/IPVS), which then handle the actual packet routing at the kernel level.

**Production usage example:** When a Service's backing Pods change (a new replica added, an old one removed), kube-proxy on every node updates its local rules accordingly — this is why Service load balancing continues correctly across rolling updates without any manual reconfiguration.

### 5.3 Container Runtime — The Actual Execution Layer

**Purpose:** Implements the mechanics of pulling images, creating containers, allocating their namespaces/cgroups (the Linux primitives covered in the Linux roadmap's §99), and starting/stopping the actual processes — all in response to instructions from the kubelet via the CRI.

**Key characteristics:**

- **containerd** and **CRI-O** are the two dominant CRI-compliant runtimes in modern Kubernetes; Docker Engine itself is no longer used directly (the "dockershim" compatibility shim was removed in Kubernetes 1.24 — §11 covers this transition and why it mattered far less than many teams feared).
- The CRI is a gRPC API — any runtime implementing it can be used interchangeably from the kubelet's perspective, which is what allows this pluggability.

**Production usage example:** `crictl` (a CLI tool analogous to `docker` but talking directly to a CRI runtime) is the standard debugging tool for inspecting containers at the node level when `kubectl` alone doesn't provide enough detail — used heavily in real troubleshooting scenarios (§99, Part 13).

## 6. Production Usage Notes: How These Three Interact During Normal Operation

- **Pod creation flow:** api-server accepts a new Pod spec → scheduler assigns it to a node → the kubelet _on that node_ notices (via its watch on the api-server) that a Pod has been assigned to it → kubelet instructs the container runtime (via CRI) to pull the image and start the container(s) → kubelet reports status back to the api-server → if the Pod backs a Service, kube-proxy on every node (not just this one) updates its rules once the api-server reflects the new Endpoint.
- **Node failure detection:** if a kubelet stops reporting to the api-server (network partition, crash, or node failure), the control plane's Node controller (part of kube-controller-manager, §8) eventually marks the node `NotReady` and, after a further grace period, begins evicting and rescheduling its Pods elsewhere — a process covered fully in §99 (Part 13).

## 7. Security Considerations

- The kubelet exposes an API of its own (the kubelet API, typically on port 10250) that, if left unauthenticated or overly permissive, allows direct container execution and log access on that node — a real, historically-exploited attack surface covered in cluster-hardening depth (§113, Part 15).
- The container runtime's configuration (e.g., whether privileged containers are permitted) is a primary lever for the "Minimize Microservice Vulnerabilities" CKS domain (§115).

## 8. Common Troubleshooting Scenarios

| Symptom                                                       | Likely Cause                                                           | Resolution Path                                                                 |
| ------------------------------------------------------------- | ---------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Node shows `NotReady` but existing Pods still respond briefly | kubelet lost contact with api-server (network issue or kubelet crash)  | Check kubelet process/logs on that specific node (§97, Part 13)                 |
| A Service's traffic isn't reaching any backing Pods           | kube-proxy rules stale or not programmed correctly on relevant node(s) | Check kube-proxy logs and current iptables/IPVS rules on the node (§51)         |
| Pod stuck `ContainerCreating` indefinitely                    | Container runtime failing to pull image or allocate resources          | Check container runtime logs (`crictl` on the node) and image pull status (§97) |

## 9. Best Practices

- When a Pod-level symptom appears, explicitly separate "is this a scheduling problem (control plane), a kubelet problem (this node's agent), or a container-runtime problem (actual execution)" before diagnosing further.
- Understand that kube-proxy issues are per-node — a Service reachability problem affecting only some clients may point to kube-proxy rules on specific nodes rather than a cluster-wide Service misconfiguration.
- Keep `crictl` available and familiar as a runtime-level debugging tool distinct from `kubectl`, for situations where Pod-level visibility isn't enough.

## 10. Common Anti-Patterns / Mistakes

- **Assuming a `NotReady` node means every Pod on it has stopped working immediately** — existing processes may continue running for a period even after the kubelet loses contact with the control plane, until eviction actually occurs.
- **Debugging Service networking issues purely at the Kubernetes object level** (checking Service/Endpoint definitions) without checking kube-proxy's actual node-level rule state when the object definitions look correct.
- **Conflating container-runtime-level failures with kubelet failures** — a stuck image pull is a runtime issue; a node failing to report status at all is a kubelet issue; they require different diagnostic commands.

## 11. Interview Questions

**🎯 Beginner:** _"What does the kubelet do?"_
**Model answer:** The kubelet is the agent running on every node that registers the node with the cluster, watches for Pods assigned to that node, and works with the container runtime to make sure those Pods' containers are actually running as specified — restarting them if they crash and reporting status back to the control plane.
_What the interviewer is probing for:_ Correct, specific understanding of the kubelet's role rather than vaguely conflating it with "Kubernetes on the node."

**🎯 Intermediate:** _"Explain the relationship between the kubelet and the container runtime, and why Kubernetes introduced the CRI."_
**Model answer:** The kubelet doesn't run containers directly — it delegates that to a container runtime (containerd, CRI-O) via the Container Runtime Interface, a standardized gRPC API. This exists so Kubernetes' core code doesn't need to be hardcoded against any one specific runtime; any CRI-compliant runtime can be swapped in. This is also why the "dockershim" removal in Kubernetes 1.24 mattered less operationally than many feared — Docker Engine was never CRI-compliant itself, so kubelet talked to it through a compatibility shim, and removing that shim just meant switching to a native CRI runtime (typically containerd, which Docker itself was already using under the hood).
_What the interviewer is probing for:_ Real understanding of the CRI abstraction and the dockershim transition, not just a memorized "Docker was removed" headline.

**🎯 Senior:** _"A specific node shows Pods stuck `ContainerCreating` for several minutes, while other nodes are fine. Walk through how you'd isolate whether this is a kubelet, container-runtime, or networking issue."_
**Model answer:** I'd start with `kubectl describe pod` on an affected Pod to read its recent Events — image pull failures, volume mount failures, or scheduling messages appear there first and often immediately narrow the cause. If events point to image pulling, I'd suspect the container runtime or registry connectivity specifically on that node, and use `crictl images`/`crictl pull` directly on the node to reproduce and isolate it from `kubectl`'s higher-level view. If kubelet itself seems unresponsive (node status stale, no new events appearing at all), I'd check kubelet's own process logs and its connectivity to the api-server rather than assuming a runtime-level problem. The key discipline is not guessing — the Pod's Events and the node-local `crictl`/kubelet logs, checked in that order, almost always pinpoint which of the three components is actually responsible before I change anything.
_What the interviewer is probing for:_ A structured, evidence-based troubleshooting approach that correctly separates the three node-level components rather than guessing or restarting things speculatively.

**🎯 Architect:** _"You're evaluating whether to standardize on containerd or CRI-O across a large, multi-team Kubernetes platform. What does understanding the kubelet/CRI/runtime separation tell you about how much this choice actually matters, and what would still differ between them?"_
**Model answer:** Because both are CRI-compliant, from the kubelet's perspective — and therefore from almost every workload's perspective — the choice is largely invisible: standard Pod specs, image pulls, and container lifecycle behavior work identically regardless of which runtime is underneath. What still differs is runtime-specific configuration surface (default security profiles, specific CRI extensions or plugins each supports, operational tooling and community/vendor support maturity, and in some cases performance characteristics under specific workload profiles). I'd frame the decision as "this choice doesn't change what application teams need to know or do," which lowers the switching cost and risk considerably, while still doing due diligence on the runtime-specific operational details (logging integration, security defaults, vendor support) that genuinely do vary and would affect the platform team specifically, not application teams.
_What the interviewer is probing for:_ Whether the candidate understands the CRI abstraction well enough to correctly scope which parts of a "big" infrastructure decision are actually low-risk versus which specific details genuinely warrant careful evaluation.

## 12. Common Misconceptions

1. **"The kubelet runs containers."** It delegates actual container execution to the container runtime via the CRI; the kubelet's job is supervision and reporting, not execution itself.
2. **"kube-proxy routes traffic itself, like a load balancer process."** It programs the node's kernel-level networking rules (iptables/IPVS); the kernel, not kube-proxy itself, actually handles packet routing.
3. **"Removing dockershim removed Docker support entirely, breaking most workloads."** It removed a compatibility shim for using Docker Engine specifically as the CRI runtime; standard container images built with any tool (including Docker) continue to run completely unaffected under containerd or CRI-O.
4. **"A `NotReady` node means all its Pods have already stopped."** Existing container processes may continue running for a period after the kubelet loses contact with the control plane, until formal eviction occurs.

## 13. 🔑 Key Takeaways

- Every worker node runs exactly three components: kubelet (node agent and container supervisor), kube-proxy (Service networking rule enforcement), and a container runtime (actual container execution via containerd or CRI-O).
- The kubelet delegates execution to the container runtime through the CRI, a clean abstraction that made the "dockershim removal" transition far less disruptive than it initially sounded.
- kube-proxy operates independently of the kubelet, watching Services/Endpoints directly and programming per-node networking rules.
- Node-level troubleshooting starts by identifying which of these three components a symptom actually implicates — Pod events, kubelet logs, and `crictl` output are the primary diagnostic tools, in that order.
- A `NotReady` node doesn't mean immediate Pod failure — there's a grace period before the control plane begins evicting and rescheduling that node's workloads.

## 14. Related Concepts & What's Next

§3 and §8 established the control-plane side this section's node components communicate with. §11 covers the Container Runtime Interface and the dockershim transition referenced here in full technical depth. §51 (Part 7) covers kube-proxy's Service-routing mechanics (iptables vs. IPVS modes) completely. §97–§101 (Part 13) build the full node-level troubleshooting methodology this section's scenarios only previewed. §113 (Part 15) returns to the kubelet API security concern noted in §7 with full CKS-level hardening guidance.

**Next Section:** §10 — `Section-10-Part2-etcd-Deep-Dive-Data-Model-Raft-Consensus.md`
