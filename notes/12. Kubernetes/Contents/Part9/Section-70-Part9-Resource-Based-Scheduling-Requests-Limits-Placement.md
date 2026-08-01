# Section 70 (Part 9): Resource-Based Scheduling: How Requests/Limits Drive Placement

## 1. Definition

**Plain language:** When kube-scheduler decides where a new Pod goes, it isn't guessing at how "busy" a node looks — it's doing arithmetic. It adds up what every already-scheduled Pod on a node has _requested_, subtracts that from the node's total allocatable capacity, and only considers a node a candidate if what's left over covers the new Pod's own requests.

**Precise definition:** During the **filtering phase**, kube-scheduler's `NodeResourcesFit` plugin eliminates any node whose **allocatable capacity minus the sum of requests from all Pods already bound to it** is less than the new Pod's own resource requests, for every resource type declared (CPU, memory, ephemeral storage, and extended resources like GPUs). Limits play no role in this filtering arithmetic at all — only **requests** are counted, meaning a node can be scheduled to look "full" from a requests perspective while still having enormous slack under limits, or conversely appear to have room while every Pod is limit-capped far above what it requested. During the subsequent **scoring phase**, plugins such as `NodeResourcesBalancedAllocation` and `NodeResourcesFit`'s scoring strategy (`LeastAllocated` or `MostAllocated`, configurable) rank the surviving candidate nodes by how requests-relative utilization would look after placing the Pod, directly consuming the same QoS-class-adjacent request/limit model introduced in §46.

## 2. Why This Matters

- **Requests are the scheduler's only currency during filtering — limits are invisible to it.** A Pod requesting 100m CPU but limited to 4 CPUs is treated by the filtering phase as if it only needs 100m, meaning a node can accept far more Pods "on paper" than it can actually sustain if every Pod bursts to its limit simultaneously — the overcommitment risk flagged in §46 is fundamentally a scheduling-time blind spot, not a runtime one.
- **The scoring strategy (`LeastAllocated` vs. `MostAllocated`) changes cluster shape, not just individual placements.** `LeastAllocated` (the default) spreads Pods across nodes to keep headroom everywhere; `MostAllocated` deliberately packs nodes tightly to free up whole nodes for cluster-autoscaler scale-down — the same requests feed opposite strategic outcomes depending on this one scheduler configuration choice.
- **A Pod with no request at all is invisible to fit-based filtering in a meaningful sense.** It's treated as requesting zero of every resource, meaning it can schedule onto an already-tightly-packed node and then compete for whatever's actually left at runtime — tying directly back to the BestEffort QoS class's placement risk from §46.

🔑 **Key Takeaway:** Kube-scheduler's filtering phase does simple subtraction using only requests (never limits) to decide which nodes are candidates at all, and its scoring phase ranks those survivors by request-relative utilization under a configurable strategy — making the request values set in a Pod spec the literal input to where every Pod in the cluster ends up.

## 3. Prerequisites and Dependencies

Builds on §46 (Resource Requests, Limits, and QoS Classes, Part 6) for the request/limit vocabulary and QoS derivation, and on §69 (Manual Scheduling and Custom Schedulers), which established what the default scheduler's normal pipeline looks like when it isn't bypassed.

## 4. Architecture Diagram

```text
                    New Pod: requests { cpu: 500m, memory: 512Mi }
                                       │
                                       ▼
              ┌────────────────────────────────────────────────────┐
              │        FILTERING PHASE: NodeResourcesFit           │
              │  For each node:                                    │
              │    allocatable - Σ(requests of bound Pods)         │
              │      ≥ new Pod's requests ?  → candidate           │
              │      < new Pod's requests ?  → rejected            │
              │  LIMITS ARE NOT CONSULTED HERE AT ALL              │
              └───────────────────────┬────────────────────────────┘
                                      ▼
              ┌────────────────────────────────────────────────────┐
              │       SCORING PHASE: rank surviving nodes          │
              │  NodeResourcesFit scoring strategy:                │
              │    LeastAllocated (default) → prefer emptier nodes │
              │    MostAllocated            → prefer fuller nodes  │
              │  NodeResourcesBalancedAllocation:                  │
              │    prefer nodes where CPU % and memory % after     │
              │    placement are close to each other (balanced)    │
              └───────────────────────┬────────────────────────────┘
                                      ▼
                         Highest-scoring node selected; Binding
                         object written; kubelet on that node
                         starts the Pod

  Node capacity view (why limits are invisible to filtering):
  ┌─────────────────────────────────────────────────────────────────┐
  │ Node allocatable: 4 CPU                                         │
  │ Pod A: requests 500m, limits 2 CPU  ─┐                          │
  │ Pod B: requests 500m, limits 2 CPU  ─┤ Σ requests = 1 CPU       │
  │ Pod C: requests 500m, limits 2 CPU  ─┘ Σ limits = 6 CPU         │
  │ Scheduler sees 3 CPU "free" (4 - 1) and keeps scheduling more   │
  │ Pods — but if A, B, and C all burst to their limits at once,    │
  │ the node cannot actually supply 6 CPU worth of demand.          │
  └─────────────────────────────────────────────────────────────────┘
```

## 5. Hands-On

### 5.1 Observing How Requests Determine Schedulability

**Purpose:** See directly how a node's allocatable capacity and already-reserved requests determine whether a new Pod can land there at all.

**Syntax:**

```bash
kubectl describe node worker-node-1
```

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: heavy-requester
spec:
  containers:
    - name: app
      image: myregistry/app:1.0.0
      resources:
        requests:
          cpu: "3500m"
          memory: "6Gi"
```

**Example usage and expected output:**

```bash
$ kubectl describe node worker-node-1 | grep -A6 "Allocated resources"
Allocated resources:
  (Total limits may be over 100 percent, i.e., overcommitted.)
  Resource           Requests      Limits
  --------           --------      ------
  cpu                3200m (80%)   6400m (160%)
  memory             5Gi (62%)     12Gi (150%)

$ kubectl apply -f heavy-requester.yaml
pod/heavy-requester created

$ kubectl get pod heavy-requester
NAME              READY   STATUS    RESTARTS   AGE
heavy-requester   0/1     Pending   0          5s

$ kubectl describe pod heavy-requester | grep -A3 Events
Events:
  Type     Reason            Message
  Warning  FailedScheduling  0/3 nodes are available: 3 Insufficient cpu.
```

**Production usage example:** Capacity planners routinely run `kubectl describe node` across all nodes before onboarding a new heavy workload, comparing the Requests column (not Limits) against allocatable capacity to determine whether current infrastructure can actually absorb it — the Limits column tells you the theoretical worst case, but the Requests column tells you what the scheduler will actually enforce today.

**Common errors:** Reading the "Limits" percentage in `kubectl describe node` output as the real constraint and concluding a node is "full" at 160% limits — that number is informational only; the scheduler only ever filters against the Requests row, so a node showing 160% limit overcommitment can still schedule additional Pods as long as Requests has headroom.

### 5.2 Choosing a Scoring Strategy: LeastAllocated vs. MostAllocated

**Purpose:** Configure whether the scheduler spreads Pods thinly across many nodes (to preserve headroom) or packs them tightly onto fewer nodes (to enable cluster-autoscaler node scale-down).

**Syntax:**

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
profiles:
  - schedulerName: default-scheduler
    pluginConfig:
      - name: NodeResourcesFit
        args:
          scoringStrategy:
            type: MostAllocated
            resources:
              - name: cpu
                weight: 1
              - name: memory
                weight: 1
```

**Example usage and expected output:**

```bash
# Applied via kubeadm's ClusterConfiguration for kube-scheduler,
# or as a --config flag to the kube-scheduler binary
$ kubectl get pods -o wide --sort-by='.spec.nodeName'
# With MostAllocated: new Pods concentrate onto already-busier
# nodes until they're full, leaving other nodes empty and safe
# for cluster-autoscaler to remove
```

**Production usage example:** A cost-sensitive cluster running on cloud infrastructure with cluster-autoscaler enabled sets `MostAllocated` deliberately, so that as workloads scale down, whole nodes empty out completely rather than each node retaining a light, scattered residue of Pods that would otherwise block node removal — directly reducing infrastructure spend.

**Common errors:** Switching to `MostAllocated` without first verifying that Pods have accurate resource requests amplifies any existing under-requesting problem, since the scheduler now actively concentrates load onto fewer nodes based on those same (potentially wrong) numbers — a scoring strategy change should always follow a review of request accuracy, not precede it.

## 6. Production Usage Notes

- Extended resources (GPUs, or custom device-plugin-advertised resources) participate in the exact same filtering arithmetic as CPU/memory — a Pod requesting `nvidia.com/gpu: 1` is filtered against nodes' allocatable GPU count minus already-requested GPUs, with no fractional sharing unless the device plugin or a custom scheduler explicitly supports it.
- `kubectl top node` shows **actual runtime usage**, not scheduler-relevant allocatable/request numbers — conflating the two is a common mistake; only `kubectl describe node`'s "Allocated resources" section reflects what the scheduler actually reasons about.
- Nodes reserve some capacity for the kubelet and system daemons via `--system-reserved` and `--kube-reserved` kubelet flags, which reduces **allocatable** below the node's raw physical capacity — the scheduler always filters against allocatable, never raw capacity, so under-provisioned system reservations can make a node appear to have less room than expected.

## 7. Security Considerations

- Because filtering only counts requests, a namespace without a `ResourceQuota` (Part 16) can have its Pods request minimal CPU/memory while carrying enormous limits, letting it consume disproportionate actual capacity once running — this is a resource-based denial-of-service vector against co-tenants, not just a capacity-planning nuisance.
- Extended-resource filtering (GPUs, etc.) has no notion of confidentiality or isolation beyond count-based accounting — a compromised container that can request GPU resources arbitrarily could starve legitimate GPU workloads cluster-wide if RBAC on Pod creation isn't scoped tightly per namespace.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                          | Likely Cause                                                                                   | Resolution Path                                                                                       |
| ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Pod `Pending` with "Insufficient cpu/memory" despite `kubectl top node` showing low actual usage | Filtering uses requests, not real usage; requests across bound Pods already exceed allocatable | Compare `kubectl describe node`'s Requests row (not Limits, not `top`) against the new Pod's requests |
| Cluster feels "full" per scheduler but nodes show low real CPU/memory usage                      | Over-requesting relative to real usage has exhausted request-based headroom                    | Right-size requests based on observed usage (consider VPA, §38) rather than adding nodes              |
| Nodes never empty out for cluster-autoscaler to remove                                           | `LeastAllocated` (default) scoring spreads Pods evenly, leaving light residue everywhere       | Switch scoring strategy to `MostAllocated` if bin-packing for scale-down is the priority              |
| Pod schedules fine but is OOMKilled or throttled soon after                                      | Filtering only checked requests; actual usage exceeded limits at runtime                       | This is a runtime/limits issue (§46), not a scheduling issue — review limit sizing, not placement     |

## 9. Best Practices

- Set requests to reflect realistic sustained usage (not padding "just in case"), since every request value directly shapes both which nodes are schedulable and how the scoring phase ranks them.
- Periodically audit `kubectl describe node`'s Requests-vs-allocatable ratio cluster-wide to catch systemic under- or over-requesting before it manifests as either Pending Pods or wasted capacity.
- Choose `LeastAllocated` vs. `MostAllocated` deliberately based on whether the cluster's priority is headroom safety or infrastructure cost via autoscaler-driven bin-packing — don't leave it at the default without considering which fits the workload.

## 10. Common Anti-Patterns / Mistakes

- **Reading `kubectl describe node`'s Limits percentage as the scheduling constraint**, when the scheduler's filtering phase only ever consults the Requests row.
- **Confusing `kubectl top node` (live usage) with scheduler-relevant allocatable/request accounting**, leading to confusion about why a "lightly used" node still rejects new Pods.
- **Switching scoring strategy to `MostAllocated` without first validating that requests are accurate**, which concentrates and amplifies any existing request-sizing errors onto fewer nodes.

## 11. Interview Questions

**🎯 Beginner:** _"Does kube-scheduler consider a Pod's resource limits when deciding which node to place it on?"_
**Model answer:** No — the filtering phase only sums up **requests** from already-bound Pods and compares that against a node's allocatable capacity. Limits are enforced later, at runtime, by the kubelet via cgroups, but they play no role in the scheduler's placement decision at all.
_What the interviewer is probing for:_ The specific, commonly-missed fact that limits are invisible to scheduling — a foundational distinction for both CKA scheduling questions and real capacity-planning conversations.

**🎯 Intermediate:** _"A node shows 160% CPU allocated in `kubectl describe node` under the Limits column, but the scheduler keeps placing new Pods on it. Is this a bug?"_
**Model answer:** No — that percentage is purely informational. The scheduler filters exclusively against the Requests row, and it's entirely normal (and expected in most clusters) for aggregate limits to exceed 100% of allocatable capacity, since limits represent a worst-case ceiling that isn't expected to be hit by every Pod simultaneously. As long as the Requests row still has headroom, the scheduler will continue placing Pods there regardless of how high the Limits percentage climbs.
_What the interviewer is probing for:_ Whether the candidate can correctly interpret real `kubectl describe node` output rather than assuming any over-100% number indicates malfunction.

**🎯 Senior:** _"Your cluster-autoscaler almost never scales down, even though overall CPU/memory usage looks low. How would you investigate and what scheduler-level lever might help?"_
**Model answer:** I'd first check whether Pods are evenly spread across most nodes (consistent with the default `LeastAllocated` scoring strategy) rather than concentrated — if every node carries a light residue of Pods, none of them ever becomes fully empty, and cluster-autoscaler can only remove nodes with zero (or safely evictable) Pods. I'd consider switching the scoring strategy to `MostAllocated` so the scheduler actively bin-packs new Pods onto already-busier nodes, letting lightly-loaded nodes drain out naturally as their Pods complete or get rescheduled elsewhere — provided request values are already reasonably accurate, since `MostAllocated` amplifies whatever the current request numbers say.
_What the interviewer is probing for:_ Connecting a real operational symptom (autoscaler not scaling down) to a specific, correct scheduler configuration lever, rather than defaulting to "just add fewer nodes" reasoning.

**🎯 Architect:** _"Design the resource-request governance strategy for a platform where different teams' inaccurate self-reported requests are causing both Pending Pods and wasted capacity across the cluster."_
**Model answer:** I'd separate the two failure modes since they need different levers: Pending Pods from under-provisioned capacity relative to genuine demand need either more nodes or workload right-sizing, while wasted capacity from over-requesting needs enforcement, not just guidance. I'd deploy Vertical Pod Autoscaler in recommendation-only mode across the fleet to generate objective, usage-based request suggestions per workload, feed those into a CI-gate or admission policy that flags requests deviating significantly from VPA's recommendation, and pair that with `ResourceQuota` per namespace (Part 16) so no team can request more aggregate capacity than they're entitled to regardless of per-Pod accuracy. On the scheduler side, I'd default to `LeastAllocated` for safety margin across the general workload population, but carve out a `MostAllocated`-scored profile (via `schedulerName`, §69) for a batch/best-effort tier explicitly designed to backfill otherwise-wasted request headroom. The core principle is treating requests as a governed, audited number rather than a per-team guess, since every downstream scheduling and autoscaling decision is only as good as that input.
_What the interviewer is probing for:_ Ability to architect a full closed loop — measurement (VPA), enforcement (quota, admission), and scheduler-level configuration — rather than treating "set better requests" as a one-time instruction to teams.

## 12. Common Misconceptions

1. **"The scheduler avoids overloaded nodes based on real-time CPU/memory usage."** It never looks at live usage during filtering — only the sum of declared requests from already-bound Pods versus allocatable capacity.
2. **"A node showing over-100% in the Limits column is misconfigured."** Aggregate limits exceeding 100% of allocatable capacity is normal and expected; it only becomes a real problem if enough Pods burst simultaneously.
3. **"Higher limits improve a Pod's chance of getting scheduled."** Limits have zero influence on the filtering decision; only the Pod's own requests (and the node's remaining request-based headroom) matter.
4. **"LeastAllocated and MostAllocated only matter for edge-case clusters."** The choice materially affects whether cluster-autoscaler can ever free up whole nodes, making it directly relevant to infrastructure cost in any autoscaled cloud environment.

## 13. 🔑 Key Takeaways

- Kube-scheduler's filtering phase (`NodeResourcesFit`) sums only **requests** from bound Pods against node allocatable capacity — limits are never part of this arithmetic.
- `kubectl describe node`'s Requests row reflects the real scheduling constraint; its Limits row and `kubectl top node`'s live usage are both informational, not scheduler inputs.
- The scoring phase's strategy (`LeastAllocated` default vs. `MostAllocated`) determines whether Pods spread out for headroom or concentrate for autoscaler-friendly bin-packing — a configurable, workload-strategy-dependent choice.
- Under-requesting risks node overcommitment invisible to the scheduler at placement time; over-requesting wastes cluster capacity the scheduler will never offer to other Pods.
- This entire mechanism directly extends the request/limit/QoS model from §46 into the scheduler's actual placement algorithm.

## 14. Related Concepts & What's Next

§46 (Part 6) introduced requests, limits, and QoS classes conceptually; this section showed precisely how the scheduler consumes request values during filtering and scoring, while §69 established what the default scheduler pipeline looks like when it isn't bypassed by manual scheduling or a custom scheduler. §71 builds on this same foundation to cover Priority Classes and Preemption — what happens when the scheduler's normal filtering finds no room at all, and a higher-priority Pod needs to evict a lower-priority one to get placed.

**Next Section:** §71 — `Section-71-Part9-Priority-Classes-Preemption.md`
