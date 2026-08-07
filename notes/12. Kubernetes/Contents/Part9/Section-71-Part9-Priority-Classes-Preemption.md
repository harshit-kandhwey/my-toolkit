# Section 71 (Part 9): Priority Classes and Preemption

## 1. Definition

**Plain language:** When a cluster genuinely has no room for a new Pod, Kubernetes doesn't have to just leave it Pending forever. If that Pod is important enough, the scheduler can evict a less important, already-running Pod to make space — but only if you've told Kubernetes which Pods count as "more important" in the first place.

**Precise definition:** A **PriorityClass** is a non-namespaced Kubernetes API object that defines a named integer `value` (higher means higher priority), which Pods reference via `spec.priorityClassName`. When a Pod cannot be scheduled because no node passes the filtering phase, kube-scheduler's **preemption** logic (the `DefaultPreemption` plugin) searches for a node where evicting one or more lower-priority Pods would free up enough resources for the pending higher-priority Pod, then deletes those victim Pods (which are given their configured `terminationGracePeriodSeconds` to shut down) so the higher-priority Pod can eventually be bound there. Preemption is a **last-resort mechanism** invoked only after normal filtering fails to find room anywhere — it never runs simply because a higher-priority Pod exists; it runs specifically when that Pod would otherwise stay Pending.

## 2. Why This Matters

- **Priority determines both scheduling order and eviction survivability.** Pods are dequeued from the scheduling queue in priority order, and separately, priority governs preemption eviction targeting — a single `priorityClassName` field influences both "when do I get considered" and "am I at risk of being evicted for someone else."
- **Preemption interacts directly with the resource-based filtering covered in [§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md).** Preemption only activates when normal filtering (based on requests, as established in [§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)) finds zero viable nodes — it's the fallback when the request/allocatable arithmetic comes up short everywhere, not an independent scheduling path.
- **Misconfigured priority is a production incident waiting to happen.** Giving every workload the same high priority defeats the entire mechanism (nothing is preemptible relative to anything else), while giving a genuinely critical workload low priority means it can be evicted by anything, including workloads that matter far less.

🔑 **Key Takeaway:** PriorityClass assigns an integer importance value to Pods, and preemption is the scheduler's last-resort mechanism — triggered only when a Pod can't be placed any other way — for evicting lower-priority Pods to make room, making thoughtful priority assignment as operationally significant as resource requests themselves.

## 3. Prerequisites and Dependencies

Builds directly on [§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md) (Resource-Based Scheduling), since preemption is specifically the scheduler's response to a filtering-phase failure driven by the same requests-vs-allocatable arithmetic, and assumes the general filtering/scoring pipeline vocabulary established across Part 9.

## 4. Architecture Diagram

```text
                New high-priority Pod submitted
                (priorityClassName: critical-app, value: 1000000)
                                │
                                ▼
              ┌───────────────────────────────────────────┐
              │   Normal filtering phase (§70) runs       │
              │   across all nodes                        │
              └─────────────────┬─────────────────────────┘
                                │
                 ┌──────────────┴───────────────┐
                 ▼                              ▼
        A node passes filtering        NO node passes filtering
        normally                       (cluster genuinely full)
                 │                               │
                 ▼                               ▼
        Pod scheduled normally,        ┌────────────────────────────────┐
        NO preemption involved         │   PREEMPTION LOGIC RUNS        │
                                       │   (DefaultPreemption)          │
                                       │                                │
                                       │  For each node, simulate:      │
                                       │   "if I evict Pods with        │
                                       │    priority < 1000000, does    │
                                       │    the pending Pod then fit?"  │
                                       └─────────────┬──────────────────┘
                                                     ▼
                                       ┌────────────────────────────────┐
                                       │  Node found where eviction     │
                                       │  would make room               │
                                       │  → victim Pod(s) DELETED       │
                                       │    (graceful termination)      │
                                       │  → pending Pod nominated to    │
                                       │    that node, scheduled once   │
                                       │    victims actually terminate  │
                                       └────────────────────────────────┘

  Priority ordering example:
  system-cluster-critical  (2000000000+)  ── never preempted in practice
  system-node-critical     (2000001000)   ── kubelet/kube-proxy tier
  critical-app             (1000000)      ── custom, business-critical
  default-priority          (0, implicit)  ── unset priorityClassName
  batch-low                (-1000)         ── explicitly de-prioritized
```

## 5. Hands-On

### 5.1 Defining and Assigning PriorityClasses

**Purpose:** Create a named priority tier and attach it to a Pod so both scheduling order and preemption eligibility reflect its real importance.

**Syntax:**

```yaml
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: critical-app
value: 1000000
globalDefault: false
description: "Business-critical services that may preempt lower-priority workloads"
---
apiVersion: scheduling.k8s.io/v1
kind: PriorityClass
metadata:
  name: batch-low
value: -1000
globalDefault: false
description: "Best-effort batch workloads, first to be preempted"
---
apiVersion: v1
kind: Pod
metadata:
  name: payments-api
spec:
  priorityClassName: critical-app
  containers:
    - name: app
      image: myregistry/payments-api:4.2.0
      resources:
        requests:
          cpu: "1"
          memory: "2Gi"
```

**Example usage and expected output:**

```bash
$ kubectl get priorityclass
NAME                      VALUE        GLOBAL-DEFAULT   AGE
system-cluster-critical   2000000000   false            40d
system-node-critical      2000001000   false            40d
critical-app              1000000      false            2m
batch-low                 -1000        false            2m

$ kubectl get pod payments-api -o jsonpath='{.spec.priority}'
1000000
```

**Production usage example:** A payments platform assigns `critical-app` (high positive value) to its core transaction-processing Deployments and `batch-low` (negative value) to its nightly reconciliation Jobs, ensuring that if the cluster ever runs genuinely short on capacity, the reconciliation batch Pods are evicted first, well before any transaction-serving Pod is touched.

**Common errors:** Setting `globalDefault: true` on more than one PriorityClass is rejected by the API server (only one PriorityClass cluster-wide may carry `globalDefault: true`), and forgetting to set `globalDefault` on any PriorityClass at all means Pods without an explicit `priorityClassName` silently default to priority `0` — often not what teams intend for their "normal" workloads relative to an explicitly low-priority batch tier.

### 5.2 Observing Preemption in Action

**Purpose:** Confirm that a lower-priority Pod is actually evicted to make room for a pending higher-priority one, and understand the events that show this happened.

**Syntax:**

```bash
kubectl get pods -o custom-columns=NAME:.metadata.name,PRIORITY:.spec.priority,STATUS:.status.phase
kubectl describe pod <pending-high-priority-pod>
```

**Example usage and expected output:**

```bash
$ kubectl describe pod payments-api-new | grep -A5 Events
Events:
  Type    Reason            Message
  Normal  Preempted         Preempted by default/payments-api-new on node worker-node-2
  Normal  Scheduled         Successfully assigned default/payments-api-new to worker-node-2

$ kubectl get events --field-selector reason=Preempting
LAST SEEN   TYPE     REASON       OBJECT                    MESSAGE
30s         Normal   Preempting   pod/batch-reconcile-7x2p  Preempted by pod payments-api-new
```

**Production usage example:** During a capacity crunch caused by an unplanned traffic spike, an SRE watching `kubectl get events --field-selector reason=Preempting` in real time can immediately identify which lower-priority workloads are being sacrificed, confirming the priority hierarchy is behaving as designed rather than evicting something unexpected.

**Common errors:** Assuming preemption is instantaneous — the victim Pod is deleted but still consumes its `terminationGracePeriodSeconds` window to shut down, meaning the pending Pod remains unscheduled (though "nominated" to the target node via `.status.nominatedNodeName`) for that entire grace period, which is easy to mistake for preemption having failed.

## 6. Production Usage Notes

- Kubernetes ships two built-in PriorityClasses for system components — `system-cluster-critical` and `system-node-critical` — with extremely high values; custom application PriorityClasses should always use values well below these to avoid ever contending with or accidentally preempting core cluster infrastructure Pods.
- `PodDisruptionBudget` ([§37](../Part5/Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md)) is **not** consulted by the preemption path the same way it is for voluntary evictions like node drains — preemption is considered involuntary disruption and can violate a PDB's minimum availability, which is a deliberate design trade-off (a higher-priority Pod's need to run outweighs a PDB), worth explicitly accounting for in capacity planning.
- Preemption is disabled per-Pod via `preemptionPolicy: Never` on the PriorityClass or Pod spec — useful for high-priority Pods that should win scheduling order but should never cause disruption to others, common for priority values used purely for queue-ordering purposes rather than eviction rights.

## 7. Security Considerations

- Any user able to create Pods with an arbitrary `priorityClassName` could assign themselves artificially high priority to preempt other tenants' workloads — RBAC should restrict which ServiceAccounts/users may reference high-value PriorityClasses using the `scheduling.k8s.io` API group's resource-name-scoped permissions, not left open by default.
- A namespace-level `ResourceQuota` (Part 16) can be scoped to specific PriorityClasses, which is a meaningful multi-tenancy control — without it, a single tenant with access to a high-priority class could preempt across the entire cluster regardless of namespace boundaries.
- Because preemption deletes Pods (a real, observable disruption), audit logging ([§96](../Part12/Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md)) of Pod deletions attributable to preemption is worth retaining distinctly from user-initiated deletions when investigating unexpected workload terminations.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                         | Likely Cause                                                                                                                 | Resolution Path                                                                                                                    |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| High-priority Pod stays `Pending` despite lower-priority Pods running elsewhere | No single node has enough evictable lower-priority capacity to fit it, or victims are protected by `preemptionPolicy: Never` | `kubectl describe pod`; check for preemption-related events and PriorityClass `preemptionPolicy` settings                          |
| Lower-priority Pod unexpectedly terminated with no direct action taken          | It was preempted to make room for a higher-priority pending Pod                                                              | `kubectl get events --field-selector reason=Preempting` to confirm and identify the preempting Pod                                 |
| Every Pod in the namespace seems to preempt every other Pod unpredictably       | Multiple PriorityClasses accidentally assigned similar or ambiguous values across unrelated workloads                        | Audit and consolidate PriorityClass values into a clear, intentional tier hierarchy                                                |
| Preemption evicts Pods that violate their PodDisruptionBudget                   | Preemption doesn't honor PDBs the way voluntary evictions do                                                                 | Account for this in PDB design; consider `preemptionPolicy: Never` for the higher-priority class if this trade-off is unacceptable |

## 9. Best Practices

- Design a small, deliberate number of priority tiers (e.g., system-critical, business-critical, standard, batch/best-effort) rather than a large number of finely-graded values that are hard to reason about during an incident.
- Reserve genuinely high priority values only for workloads whose preemption rights are actually justified — treat priority as a scarce, carefully governed resource, not a default "make it higher just in case" setting.
- Combine priority with `ResourceQuota` scoped per PriorityClass (Part 16) in multi-tenant clusters so priority assignment itself is subject to governance, not solely to individual teams' self-declaration.

## 10. Common Anti-Patterns / Mistakes

- **Assigning every workload the same high-priority class** "to be safe," which defeats preemption entirely since there's nothing left to preempt relative to anything else.
- **Leaving priority unset (defaulting to 0) for workloads that are actually critical**, making them just as preemptible as anything else with no explicit assignment.
- **Ignoring the PodDisruptionBudget interaction**, assuming a PDB fully protects a workload from disruption when preemption specifically is not bound by PDB guarantees.

## 11. Interview Questions

**🎯 Beginner:** _"What is a PriorityClass, and when does preemption actually happen?"_
**Model answer:** A PriorityClass is a named integer value that Pods reference to declare their relative importance. Preemption is not continuous or proactive — it's a last-resort action the scheduler takes only when a Pod can't be scheduled anywhere through normal filtering, at which point it looks for lower-priority Pods it could evict to free up room for the pending higher-priority one.
_What the interviewer is probing for:_ Correcting the common assumption that higher priority means "runs sooner" in some general sense, rather than the precise trigger condition for preemption.

**🎯 Intermediate:** _"Does a PodDisruptionBudget protect a Pod from being preempted?"_
**Model answer:** Not in the way it protects against voluntary disruptions like node drains. Preemption is treated as a different category of disruption specifically because a higher-priority Pod's scheduling need is considered to outweigh a lower-priority Pod's PDB guarantee — the scheduler can and will violate a PDB's minimum availability if that's what it takes to place the pending Pod. This is a deliberate design choice, not an oversight, and it's important to account for it explicitly when relying on PDBs for availability guarantees.
_What the interviewer is probing for:_ Awareness of a specific, often-surprising interaction between two distinct scheduling mechanisms, rather than assuming all disruption-protection mechanisms compose cleanly.

**🎯 Senior:** _"A pending high-priority Pod remains unscheduled for several minutes even though `kubectl get events` shows a preemption occurred. Is something broken?"_
**Model answer:** Not necessarily — preemption deletes the victim Pod, but that Pod still runs through its full `terminationGracePeriodSeconds` before actually terminating, and the pending Pod is only "nominated" to that node (visible via `.status.nominatedNodeName`) until the victim is actually gone and the node's resources are truly free. If the victim has a long grace period (or a `preStop` hook that takes a while), the apparent delay is expected behavior, not a malfunction. I'd check the victim Pod's grace period and any `preStop` hook duration before assuming anything is wrong.
_What the interviewer is probing for:_ Understanding that preemption's effects aren't instantaneous and correctly distinguishing expected grace-period delay from actual scheduler malfunction.

**🎯 Architect:** _"Design a priority and preemption strategy for a multi-tenant cluster hosting both revenue-critical services and internal batch analytics, where tenants shouldn't be able to game the system."_
**Model answer:** I'd define a small, fixed set of PriorityClasses — reserving the built-in `system-*` tiers for cluster infrastructure only, a `business-critical` tier for revenue-facing services, a `standard` default tier, and a `batch-low` tier with negative priority for analytics — and lock down which ServiceAccounts/namespaces may reference each via RBAC on the `scheduling.k8s.io` API resources, so no tenant can self-assign into a higher tier than they're entitled to. I'd pair this with namespace-scoped `ResourceQuota` objects scoped by PriorityClass (Part 16) so a tenant can't simply flood the cluster with high-priority Pod requests to dominate preemption outcomes even within their allowed tier. For the batch-analytics tier specifically, I'd set `preemptionPolicy: Never` if I only want it to lose the _scheduling queue_ race gracefully without ever contributing eviction risk to workloads even lower than it — versus allowing it full preemption rights if genuinely being ahead of best-effort workloads matters. I'd also explicitly document the PDB-vs-preemption interaction for business-critical services' on-call runbooks, since it's the interaction most likely to surprise someone during a real incident.
_What the interviewer is probing for:_ Ability to combine priority, RBAC, quota, and preemption-policy controls into a coherent multi-tenant governance model, and awareness of the specific PDB interaction as an operational risk worth documenting proactively.

## 12. Common Misconceptions

1. **"Higher priority means the Pod runs with more resources or performs better."** Priority affects scheduling order and preemption eligibility only — it has no bearing on the Pod's actual runtime resource allocation, which is entirely governed by requests/limits ([§46](../Part6/Section-46-Part6-Resource-Requests-Limits-QoS-Classes.md), [§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)).
2. **"Preemption happens continuously to optimize cluster utilization."** It only triggers when a specific pending Pod cannot be scheduled through normal filtering — it's reactive to a scheduling failure, not a proactive rebalancing mechanism.
3. **"PodDisruptionBudgets fully protect a workload from any kind of eviction."** They protect against voluntary disruptions (drains, descheduling); preemption is explicitly allowed to violate them.
4. **"Unset priority means neutral, mid-tier priority."** It defaults to `0`, which in a cluster with explicitly negative-priority tiers (like batch workloads) is actually higher than intended relative to those tiers — always assign priority explicitly rather than relying on the default.

## 13. 🔑 Key Takeaways

- A PriorityClass assigns an integer value Pods reference via `priorityClassName`, governing both scheduling queue order and preemption eviction eligibility.
- Preemption is a last-resort scheduler action triggered only when normal filtering ([§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)) finds zero viable nodes for a pending Pod — never a proactive or continuous process.
- Victim Pod deletion during preemption respects `terminationGracePeriodSeconds`, so the pending Pod's actual scheduling is delayed until the victim fully terminates, not instantaneous.
- Preemption is not bound by PodDisruptionBudget guarantees — a deliberate design trade-off worth explicitly accounting for in availability planning.
- Multi-tenant clusters should govern PriorityClass access via RBAC and PriorityClass-scoped `ResourceQuota` to prevent tenants from self-assigning disproportionate eviction power.

## 14. Related Concepts & What's Next

[§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md) established how the scheduler's filtering phase uses requests to determine node candidacy; this section covered what happens when that filtering fails everywhere and a higher-priority Pod needs room made for it via preemption. [§72](./Section-72-Part9-Topology-Spread-Constraints.md) covers Topology Spread Constraints — the mechanism for controlling _how_ Pods distribute across failure domains once they are scheduled, completing Part 9's tour of placement controls.

**Next Section:** [§72](./Section-72-Part9-Topology-Spread-Constraints.md) — `Section-72-Part9-Topology-Spread-Constraints.md`
