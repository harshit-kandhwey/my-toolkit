# Section 46 (Part 6): Resource Requests and Limits; Quality-of-Service Classes (Guaranteed/Burstable/BestEffort)

## 1. Definition

**Plain language:** When you tell Kubernetes "this container needs at least this much CPU and memory, but should never be allowed to use more than this much," you're giving the scheduler and the kubelet the information they need to place your Pod sensibly and to decide who gets sacrificed first when a node runs out of resources.

**Precise definition:** A **resource request** is the amount of CPU and/or memory a container is guaranteed to receive and the value the **scheduler** uses to decide which node has room for a Pod; a **resource limit** is the hard ceiling a container is not allowed to exceed, enforced by the kubelet and container runtime via Linux cgroups. Based on the relationship between a Pod's aggregate requests and limits across all its containers, Kubernetes assigns one of three **Quality-of-Service (QoS) classes** — **Guaranteed** (requests equal limits for every container, for both CPU and memory), **Burstable** (at least one container has a request, but requests and limits don't match everywhere), or **BestEffort** (no requests or limits set anywhere in the Pod) — which directly determines eviction priority under node memory pressure.

## 2. Why This Matters

- **QoS class determines eviction order, not just performance.** Under node memory pressure, the kubelet evicts **BestEffort** Pods first, then **Burstable** Pods exceeding their requests, and only evicts **Guaranteed** Pods as an absolute last resort — a direct consequence of how you set requests/limits, tying this section to [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md)'s Pod spec anatomy and to real production incident behavior.
- **Requests are the scheduler's placement currency.** The scheduler's filtering phase (previewed in [§12](../Part2/Section-12-Part2-API-Server-Deep-Dive-Groups-Versioning-Admission-Chain.md), fully covered in [§65](../Part9/Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md)-[§72](../Part9/Section-72-Part9-Topology-Spread-Constraints.md)) rejects any node that doesn't have enough _unreserved_ request capacity for a new Pod — meaning under-requesting leads to overcommitted nodes and over-requesting wastes cluster capacity, a tension every capacity-planning decision in Part 9 has to resolve.
- **Autoscalers act on requests, not raw usage.** The Horizontal Pod Autoscaler ([§37](../Part5/Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md)) computes CPU/memory utilization as a percentage _of the request value_, not of any absolute number — a Pod with no CPU request cannot be targeted by a CPU-based HPA at all, a subtlety that trips up many first HPA configurations.

🔑 **Key Takeaway:** Requests and limits aren't just "sizing hints" — they're the literal inputs to scheduling placement, eviction ordering, and autoscaling math, so setting them incorrectly has concrete operational consequences well beyond the container's own performance.

## 3. Prerequisites and Dependencies

Builds on [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) (Pod spec anatomy, where `resources.requests`/`resources.limits` live in the container spec) and [§37](../Part5/Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md) (HPA, which consumes request values as its scaling denominator).

## 4. Architecture Diagram

```text
                     Pod Spec (per container)
   ┌───────────────────────────────────────────────────────────┐
   │  resources:                                               │
   │    requests: { cpu: 250m, memory: 256Mi }  ── scheduler   │
   │    limits:   { cpu: 500m, memory: 512Mi }  ── kubelet/    │
   │                                                cgroups    │
   └───────────────────────────────────────────────────────────┘
              │                              │
              ▼                              ▼
   ┌─────────────────────┐         ┌────────────────────────────┐
   │  kube-scheduler     │         │  kubelet + container       │
   │  sums requests      │         │  runtime enforce limits    │
   │  across Pods on a   │         │  via cgroup CPU/memory     │
   │  candidate node;    │         │  controllers               │
   │  only schedules if  │         │  - CPU limit → throttled   │
   │  unreserved capacity│         │  - Memory limit → OOMKilled│
   │  ≥ this Pod's       │         │    if exceeded             │
   │  requests           │         │                            │
   └─────────────────────┘         └────────────────────────────┘
              │
              ▼
   ┌────────────────────────────────────────────────────────────┐
   │           QoS class (computed from requests/limits)        │
   │  Guaranteed  : requests == limits, every resource, every   │
   │                container                                   │
   │  Burstable   : at least one request set, not all equal     │
   │  BestEffort  : no requests or limits set anywhere          │
   │  ──► eviction priority under node memory pressure:         │
   │      BestEffort first, then Burstable, Guaranteed last     │
   └────────────────────────────────────────────────────────────┘
```

- **CPU is compressible** — exceeding a CPU limit results in throttling (the process is slowed down, not killed).
- **Memory is not compressible** — exceeding a memory limit results in the container being **OOMKilled** immediately, because the kernel cannot simply "slow down" memory usage.

## 5. Hands-On: Setting Requests/Limits and Observing QoS Behavior

### 5.1 Defining Requests and Limits in a Pod Spec

**Purpose:** Declare both the guaranteed floor (request) and hard ceiling (limit) for CPU and memory on a container.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: web-app
spec:
  containers:
    - name: app
      image: myregistry/web-app:1.4.0
      resources:
        requests:
          cpu: "250m"
          memory: "256Mi"
        limits:
          cpu: "500m"
          memory: "512Mi"
```

**Production usage example:** A payments API team sets `requests.cpu: 250m` based on observed p50 CPU usage under normal load, and `limits.cpu: 500m` to allow headroom for traffic spikes without letting one container starve its node-mates — the 2x request-to-limit ratio is a common, defensible starting convention before tuning against real metrics.

**Common errors:** Setting `limits.memory` far above `requests.memory` (e.g., 128Mi request, 4Gi limit) creates a Burstable Pod that the scheduler under-reserves capacity for, but that can consume far more memory than planned once running — a frequent cause of unexpected node memory pressure and neighbor evictions.

### 5.2 Verifying the Assigned QoS Class

**Purpose:** Confirm which QoS class Kubernetes computed for a running Pod, since it isn't set directly — it's derived.

**Syntax:**

```bash
kubectl get pod web-app -o jsonpath='{.status.qosClass}'
```

**Example usage and expected output:**

```bash
$ kubectl get pod web-app -o jsonpath='{.status.qosClass}'
Burstable

$ kubectl describe pod web-app | grep -A2 "QoS Class"
QoS Class:                  Burstable
```

**Production usage example:** During a node memory-pressure incident, an SRE runs this across all Pods on the affected node (`kubectl get pods -o custom-columns=NAME:.metadata.name,QOS:.status.qosClass`) to predict which Pods the kubelet will evict first, before the eviction actually happens — turning a reactive incident into a partially predictable one.

### 5.3 Achieving the Guaranteed QoS Class

**Purpose:** Configure a Pod so every container's requests exactly equal its limits for both CPU and memory — the only way to reach the Guaranteed class.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: critical-cache
spec:
  containers:
    - name: redis
      image: redis:7.2
      resources:
        requests:
          cpu: "1"
          memory: "1Gi"
        limits:
          cpu: "1"
          memory: "1Gi"
```

**Production usage example:** A team running a self-hosted Redis cache used as a single point of failure for session state deliberately sets requests equal to limits, accepting the loss of "bursting" headroom in exchange for being the last Pod the kubelet would ever evict under memory pressure — an explicit reliability trade-off, not an accident.

**Common errors:** Setting requests equal to limits for CPU but not memory (or vice versa) still results in Burstable, not Guaranteed — the equality must hold for **every** resource type across **every** container in the Pod, including sidecars, which is a common oversight in multi-container Pods ([§25](../Part4/Section-25-Part4-Multi-Container-Pods-Sidecar-Ambassador-Adapter-Patterns.md)).

## 6. Production Usage Notes

- **Under-requesting to "fit more Pods per node" backfires** — it works until real usage exceeds what the node can actually supply across all its overcommitted Pods, at which point CPU throttling or OOMKills appear under load precisely when the application can least tolerate it.
- **Limits without requests are silently defaulted** by many clusters' `LimitRange` objects, or left as an unbounded request equal to zero, which can make a Pod schedule onto an already-busy node and then get starved — always set both explicitly rather than relying on defaults you haven't inspected.
- **Vertical Pod Autoscaler ([§38](../Part5/Section-38-Part5-Vertical-Pod-Autoscaler-Cluster-Autoscaler.md)) exists precisely because manually tuning requests/limits at scale is hard** — it observes actual usage over time and recommends (or automatically applies) revised request values, which is often more accurate than a static, guessed value.
- **Memory limits are the more dangerous of the two to under-provision** — a CPU limit breach only slows the process down, but a memory limit breach kills the container outright, so memory limits deserve more conservative headroom than CPU limits in most workloads.

## 7. Security Considerations

- **Pods without any resource limits are a denial-of-service vector** — a single misbehaving or compromised container can consume unbounded node CPU/memory, starving every other workload on that node; enforcing limits via `LimitRange` or admission policy is a baseline hardening measure.
- **ResourceQuota objects (Part 16, [§125](../Part16/Section-125-Part16-Multi-Cluster-Architectures-Federation-Cluster-API.md)) enforce requests/limits at the namespace level**, preventing a single team or tenant from being able to request more aggregate capacity than their namespace is entitled to — a multi-tenancy security and fairness boundary, not just a cost control.

## 8. Common Troubleshooting Scenarios

| Symptom                                                               | Likely Cause                                                                   | Resolution Path                                                                              |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------- |
| Pod stuck `Pending` with "Insufficient cpu/memory" event              | Requested resources exceed what any node has unreserved                        | Check `kubectl describe node` allocatable vs. requested; scale nodes or lower requests       |
| Container repeatedly `OOMKilled`                                      | Memory usage exceeds `limits.memory`                                           | Raise the memory limit or investigate a memory leak; check `kubectl describe pod` last state |
| Application intermittently slow under load despite low apparent CPU % | CPU usage hitting `limits.cpu` and being throttled by cgroups                  | Compare usage against the limit specifically (not just node-wide CPU); raise the CPU limit   |
| Pod evicted first during a node memory-pressure event                 | Pod is BestEffort or low-priority Burstable relative to other Pods on the node | Set explicit requests/limits, or move critical workloads toward Guaranteed QoS               |

## 9. Best Practices

- Set requests based on observed steady-state usage (from metrics, not guesses) and set limits with deliberate headroom for legitimate bursts, rather than copying arbitrary defaults across every workload.
- Reserve the Guaranteed QoS class for workloads whose eviction would be genuinely catastrophic (stateful caches, control-plane-adjacent components), since it trades away burst capacity for eviction priority.
- Always set both requests and limits explicitly per container rather than relying on namespace-wide `LimitRange` defaults you haven't reviewed recently.

## 10. Common Anti-Patterns / Mistakes

- **Leaving requests and limits unset entirely** ("BestEffort by accident"), which makes a Pod both hard for the scheduler to place well and the first evicted under any pressure.
- **Setting memory limits far above memory requests** ("just in case"), which under-reserves scheduling capacity while still permitting a single Pod to consume enough memory to destabilize its node.
- **Copy-pasting the same requests/limits values across every microservice** regardless of actual workload profile, producing systematic overcommitment for light services and starvation for heavy ones.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a resource request and a resource limit?"_
**Model answer:** A request is the amount of CPU/memory a container is guaranteed to get and what the scheduler uses to decide if a node has room for the Pod. A limit is the maximum the container is allowed to use — enforced by the kubelet via cgroups. Exceeding a CPU limit throttles the process; exceeding a memory limit gets the container OOMKilled.
_What the interviewer is probing for:_ Whether the candidate distinguishes the scheduling-time role (request) from the runtime-enforcement role (limit), rather than treating them as synonyms.

**🎯 Intermediate:** _"How does Kubernetes decide a Pod's QoS class, and why does it matter operationally?"_
**Model answer:** QoS class is derived, not set directly: Guaranteed requires every container's requests to equal its limits for both CPU and memory; Burstable means at least one request is set but they don't all match; BestEffort means no requests or limits anywhere. It matters because under node memory pressure the kubelet evicts BestEffort Pods first, then Burstable Pods exceeding their requests, and Guaranteed Pods last — so QoS class is effectively a self-selected eviction priority based on how carefully you configured resources.
_What the interviewer is probing for:_ Understanding that QoS is a derived property with real eviction consequences, not a label you set in the spec.

**🎯 Senior:** _"A namespace's Pods are experiencing intermittent CPU throttling under load even though node-level CPU utilization looks fine. How do you investigate, and what would you change?"_
**Model answer:** Node-wide CPU utilization being fine doesn't rule out a specific container hitting its own `limits.cpu` — cgroup CPU throttling is enforced per-container regardless of how much idle capacity the node has elsewhere. I'd check container-level throttling metrics (`container_cpu_cfs_throttled_seconds_total` from cAdvisor/Metrics pipeline, [§91](../Part12/Section-91-Part12-Metrics-Server-Kubernetes-Metrics-Pipeline.md)) rather than node CPU percentage, correlate throttling spikes with request traffic, and if confirmed, either raise the CPU limit for that container or, if the workload's usage pattern is genuinely bursty and unpredictable, consider whether a limit is appropriate at all for that specific container versus relying on requests plus namespace ResourceQuota for overall fairness.
_What the interviewer is probing for:_ Recognition that node-level metrics and container-level cgroup enforcement are different signals, and that fixing throttling requires per-container limit tuning, not node capacity changes.

**🎯 Architect:** _"You're designing resource governance for a shared cluster with dozens of teams. How do requests, limits, QoS classes, and quotas combine into an overall strategy, and what failure mode are you specifically trying to prevent?"_
**Model answer:** I'd treat requests as the primary fairness and scheduling-capacity lever — enforced in aggregate per namespace via ResourceQuota so no single team can reserve more of the cluster's real capacity than they're entitled to. I'd use `LimitRange` to set sane per-container defaults and caps so teams can't accidentally (or deliberately) launch unbounded BestEffort workloads that any co-tenant could be starved by. QoS class becomes the emergent property I'd audit rather than mandate directly — critical shared infrastructure (ingress controllers, DNS, monitoring) I'd push explicitly toward Guaranteed, while typical application workloads stay Burstable with tuned requests. The specific failure mode I'm preventing is the "noisy neighbor" problem: one team's under-governed workload degrading every other tenant's Pods on a shared node, which requests/limits/QoS/quota together are the complete toolset for preventing, but only if all four are actually enforced together rather than any one alone.
_What the interviewer is probing for:_ Whether the candidate can architect resource governance as a system of complementary controls rather than reaching for just one lever, and can name the concrete multi-tenant failure mode being defended against.

## 12. Common Misconceptions

1. **"Setting a higher limit always improves performance."** A limit is a ceiling, not a guarantee — actual performance is bounded by the node's real available capacity and by the request-driven scheduling decision, not by how generous the limit looks on paper.
2. **"QoS class is something you set directly in the Pod spec."** It's entirely derived from the relationship between requests and limits across all containers; there's no `qosClass` field to author.
3. **"A memory limit breach behaves like a CPU limit breach (slowdown)."** Memory is not compressible — exceeding a memory limit results in an immediate OOMKill, not throttling.
4. **"BestEffort Pods can't be scheduled."** They schedule freely (with no resource reservation at all) — the risk is entirely at runtime, where they're both unprotected from resource contention and first in line for eviction.

## 13. 🔑 Key Takeaways

- Requests drive scheduler placement; limits are enforced at runtime via cgroups, with CPU throttled and memory OOMKilled on breach.
- QoS class (Guaranteed/Burstable/BestEffort) is derived from requests-vs-limits equality and directly determines eviction order under node memory pressure.
- The Horizontal Pod Autoscaler ([§37](../Part5/Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md)) computes utilization as a percentage of the request value, so unset requests make CPU/memory-based autoscaling impossible.
- Under-requesting risks node overcommitment and throttling/OOMKills under real load; over-requesting wastes cluster capacity that other Pods can't use.
- Namespace-level `ResourceQuota` and `LimitRange` (Part 16) extend this same request/limit model to multi-tenant fairness enforcement.

## 14. Related Concepts & What's Next

[§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) introduced where requests and limits live in the Pod spec; [§37](../Part5/Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md)'s HPA consumes request values as its scaling denominator, and [§65](../Part9/Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md)-[§72](../Part9/Section-72-Part9-Topology-Spread-Constraints.md) cover in full depth how the scheduler's filtering and scoring phases actually use requests during placement, along with resource-based scheduling and priority/preemption built on the same QoS foundation. [§47](./Section-47-Part6-Multi-Environment-Configuration-Patterns.md) closes out Part 6 by looking at how requests/limits and other configuration vary across environments (dev/staging/prod) using Namespaces and a preview of Kustomize overlays.

**Next Section:** [§47](./Section-47-Part6-Multi-Environment-Configuration-Patterns.md) — `Section-47-Part6-Multi-Environment-Configuration-Patterns.md`
