# Section 104 (Part 13): Cluster-Level Resource Exhaustion and Eviction

## 1. Definition

**Plain language:** §103 looked at a single container running out of its own memory or CPU allowance. This section zooms out to what happens when an entire node runs low on resources — not because one container misbehaved, but because the sum of everything scheduled onto that node exceeds what the node physically has. When that happens, the kubelet doesn't just let the node fall over; it starts actively killing Pods to protect itself, a process with its own specific ordering, triggers, and terminology that's easy to mistake for a routine crash.

**Precise definition:** **Cluster-level resource exhaustion** occurs when a node's actual resource consumption (memory, disk, PIDs) approaches or exceeds thresholds the kubelet monitors independently of any individual Pod's own `resources.limits`. When a monitored resource crosses its configured **eviction threshold**, the kubelet triggers **node-pressure eviction** — reported as node conditions (`MemoryPressure`, `DiskPressure`, `PIDPressure`) and Pod status `Evicted` — selecting victim Pods by **QoS class** (§46) in the order `BestEffort` → `Burstable` → `Guaranteed`, and within a class, by how far each Pod's usage exceeds its own requests. This is distinct from the Kubernetes **API-initiated eviction** (via the Eviction API, used by `kubectl drain` and voluntary disruption, §112 Part 14) and distinct from a single container's `OOMKilled` (§103), which is a per-container cgroup limit kill rather than a node-wide protective action.

## 2. Why This Matters

- **Node-pressure eviction is the kubelet actively protecting node stability, not a bug** — when it kills a `BestEffort` Pod under `MemoryPressure`, it is working exactly as designed; the actual problem to investigate is why the node reached that pressure threshold in the first place (undersized node, missing requests, a genuine leak somewhere on the node), not the eviction mechanism itself.
- **QoS class determines eviction order, and most teams under-provision it accidentally** — a critical workload left with no `resources.requests`/`limits` at all is `BestEffort` by default (§46) and is the _first_ class of Pod evicted under any node pressure, which is a serious and entirely avoidable production risk if nobody deliberately reviewed QoS classes for critical workloads.
- **`Evicted` and `OOMKilled` are frequently confused, but point at different fixes** — an `OOMKilled` container exceeded its own limit and the fix is usually per-container (§103); a node-pressure `Evicted` Pod may have been well within its own limits and simply lost a resource contest against other Pods on an overcommitted node, meaning the fix is node capacity, bin-packing, or requests/limits tuning across the whole node, not any single container's configuration.

🔑 **Key Takeaway:** Node-pressure eviction is the kubelet's last line of defense against a node running out of memory, disk, or PIDs entirely, it selects victims by QoS class (`BestEffort` first, `Guaranteed` last), and a Pod being `Evicted` is a fundamentally different event — with a different root cause and fix — than a single container being `OOMKilled`.

## 3. Prerequisites and Dependencies

Back-references §103 (application-level debugging, specifically `OOMKilled`, which this section distinguishes from node-pressure eviction) and §46 (resource requests/limits and QoS classes, Part 6, which directly determines eviction order). Builds on §100 (Part 13's structured troubleshooting methodology) and follows §103 in Part 13's sequence. Forwards into §105 (incident case studies, the Part 13 capstone) and previews concepts fully covered in §112 (Cluster Backup Strategies context) and §14x (node maintenance, Part 14) for the voluntary/API-initiated eviction path.

## 4. Architecture Diagram

```text
   Node-pressure eviction: from resource pressure to Pod termination

   Node resource usage climbs (memory, disk, or PID count)
                    │
                    ▼
   kubelet's eviction manager compares usage against configured
   eviction thresholds (e.g. memory.available < 100Mi)
                    │
        threshold crossed
                    ▼
   Node condition set:  MemoryPressure=True (or DiskPressure/PIDPressure)
                    │
                    ▼
   kubelet ranks all Pods on the node for eviction:
   ┌─────────────────────────────────────────────────────────┐
   │ 1st: BestEffort        (no requests/limits at all)      │
   │ 2nd: Burstable         (usage exceeds its own requests) │
   │ 3rd: Guaranteed        (evicted only in extreme cases)  │
   └─────────────────────────────────────────────────────────┘
                    │
                    ▼
   Selected Pod(s) terminated → kubectl get pods shows:
     STATUS: Evicted
   New Pods with matching nodeSelector/taints refused scheduling
   onto this node until pressure clears (node tainted accordingly)
```

- The kubelet's eviction manager is deliberately proactive — it acts on soft/hard thresholds _before_ the node fully runs out of a resource, aiming to fail gracefully (kill a Pod) rather than have the node itself become unresponsive.
- QoS-class ordering is the single most important fact for understanding _which_ Pod gets killed first — `BestEffort` Pods have no protection at all, `Burstable` Pods are protected only up to their requested amount, and `Guaranteed` Pods (requests == limits for both CPU and memory) are evicted only when there is no other option.
- Once pressure is detected, the kubelet also taints the node (e.g., `node.kubernetes.io/memory-pressure:NoSchedule`) so the scheduler stops placing new Pods there until the condition clears, compounding effects with cluster autoscaling behavior if enabled.

## 5. Hands-On

### 5.1 Confirming Node-Pressure Eviction Versus a Container-Level OOMKilled

**Purpose:** Establish, from Pod status alone, whether a Pod loss was a node-pressure eviction or a container-level `OOMKilled` (§103) — the two require entirely different remediation.

**Syntax:**

```bash
kubectl get pods --field-selector=status.phase=Failed -A
kubectl describe pod <pod-name> -n <namespace>
kubectl describe node <node-name> | grep -A5 Conditions
```

**Example usage:**

```bash
$ kubectl get pods --field-selector=status.phase=Failed -A
NAMESPACE   NAME                       READY   STATUS    RESTARTS   AGE
batch       report-gen-8f7c2-m9k1x     0/1     Evicted   0          12m

$ kubectl describe pod report-gen-8f7c2-m9k1x -n batch | grep -A3 "Status\|Message"
Status:       Failed
Reason:       Evicted
Message:      The node was low on resource: memory. Container app was using 340Ki, request is 0.

$ kubectl describe node node-4 | grep -A5 Conditions
Conditions:
  Type             Status  Reason
  MemoryPressure   True    KubeletHasInsufficientMemory
```

**Production usage example:** The Pod's `Message` field explicitly states the node was low on memory and quotes the container's request as `0` — this is the tell that the Pod was `BestEffort` (no `resources.requests` set at all), the lowest-protected QoS class, and was evicted to relieve genuine node-wide `MemoryPressure`, not because this specific container exceeded any limit of its own; the fix is adding proper `requests`/`limits` to this workload, not investigating the application's memory behavior in isolation.

**Common errors:** Treating an `Evicted` Pod the same as an `OOMKilled` one and looking for an application-level memory leak, when the actual root cause is that the Pod had no resource requests at all and lost a node-wide resource contest that had little to do with its own behavior.

### 5.2 Diagnosing Which QoS Class Is Driving Repeated Evictions on a Node

**Purpose:** Identify whether a node is repeatedly evicting Pods because of genuine undersizing, or because too many `BestEffort`/under-requested `Burstable` Pods are packed onto it.

**Syntax:**

```bash
kubectl describe node <node-name> | grep -A10 "Allocated resources"
kubectl get pods -A -o wide --field-selector spec.nodeName=<node-name>
kubectl get pod <pod-name> -o jsonpath='{.status.qosClass}'
```

**Example usage:**

```bash
$ kubectl describe node node-4 | grep -A8 "Allocated resources"
Allocated resources:
  Resource           Requests      Limits
  --------           --------      ------
  cpu                1200m (30%)   4000m (100%)
  memory             1200Mi (30%)  8000Mi (200%)

$ kubectl get pods -A -o wide --field-selector spec.nodeName=node-4 | wc -l
23

$ for p in $(kubectl get pods -A --field-selector spec.nodeName=node-4 -o name); do
    kubectl get $p -o jsonpath='{.status.qosClass}{"\n"}'
  done | sort | uniq -c
     14 BestEffort
      6 Burstable
      1 Guaranteed
```

**Production usage example:** Requests total only `30%` of the node's memory, but limits total `200%` — meaning the node is heavily overcommitted on limits, and with 14 of 23 Pods running as `BestEffort` (no requests set at all), any real memory spike from even a handful of them will trigger eviction well before the node's absolute capacity is reached; the actionable fix is mandating `resources.requests` on this namespace's workloads (potentially enforced via a LimitRange, §46) to move Pods out of the unprotected `BestEffort` tier.

**Common errors:** Concluding a node needs to be resized (more memory/CPU) purely from repeated eviction events, without first checking whether the actual issue is Pod-level under-requesting driving the node into `BestEffort`-heavy overcommitment — resizing the node without fixing requests just delays the same problem at a larger scale.

### 5.3 Reading Eviction Thresholds and Adjusting Kubelet Configuration

**Purpose:** Understand and, where appropriate, tune the specific thresholds the kubelet uses to decide when a node is under pressure.

**Syntax:**

```bash
kubectl get --raw /api/v1/nodes/<node-name>/proxy/configz | jq '.kubeletconfig.evictionHard'
```

**Example usage:**

```bash
$ kubectl get --raw /api/v1/nodes/node-4/proxy/configz | jq '.kubeletconfig.evictionHard'
{
  "memory.available": "100Mi",
  "nodefs.available": "10%",
  "imagefs.available": "15%",
  "pid.available": "10%"
}
```

**Production usage example:** A node running consistently at `memory.available` just above `100Mi` is a node that will start evicting Pods with essentially no warning margin — raising `evictionHard.memory.available` to a value proportional to the node's total memory (e.g., `5%` instead of a fixed `100Mi` on very large nodes) gives the kubelet more headroom to react before the node is genuinely critical, and is a standard kubeadm/kubelet config tuning exercise for large-memory nodes where a fixed absolute threshold is too tight.

**Common errors:** Treating `evictionHard` thresholds as fixed, universal defaults rather than values that should scale with node size — a `100Mi` hard threshold that's reasonable on a small node leaves almost no margin on a node with hundreds of gigabytes of memory, where a fast-moving memory spike can blow past it before anyone reacts.

## 6. Production Usage Notes

- **`resources.requests` should be treated as close to mandatory for any workload that must survive node pressure** — it is the single field that moves a Pod out of the unprotected `BestEffort` QoS tier, and a `LimitRange` (§46) enforcing a default request is a common and effective guardrail at the namespace level.
- **Eviction events and node conditions belong in the same monitoring and alerting pipeline as any other node-health signal** (§92, Part 12) — `MemoryPressure`/`DiskPressure`/`PIDPressure` conditions are a leading indicator that should page someone well before repeated evictions become a user-facing incident.
- **Node overcommitment on `limits` (as opposed to `requests`) is a deliberate bin-packing tradeoff, not automatically a misconfiguration** — but it should be a monitored, intentional choice (with headroom margins understood) rather than an accidental byproduct of teams setting generous limits without matching, realistic requests.

## 7. Security Considerations

- Eviction messages and node condition details are visible to anyone with `describe` access on Pods/Nodes and can reveal cluster capacity-planning information (how tightly nodes are packed) — treat this similarly to other capacity-related information disclosure concerns (§113, Part 15).
- A malicious or careless workload deliberately consuming unbounded memory without limits (a `BestEffort` "noisy neighbor") can trigger evictions of unrelated, legitimate Pods on the same node — this is a strong practical argument for enforcing `LimitRange`/`ResourceQuota` (§46, §16x Part 16) at the namespace level in multi-tenant clusters, not just a performance nicety.
- Node taints applied automatically during pressure (`memory-pressure:NoSchedule`) should never be manually removed to "force" scheduling onto a pressured node — doing so defeats the kubelet's own protective mechanism and risks node instability.

## 8. Common Troubleshooting Scenarios

| Symptom                                                        | Cause                                                                                     | Fix                                                                                                     |
| -------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Pod status `Evicted`, message cites node low on memory         | Node hit `MemoryPressure`; Pod was `BestEffort` or exceeded its `Burstable` requests      | Add proper `resources.requests`/`limits` (§46) to move the Pod out of the unprotected QoS tier          |
| Repeated evictions across many different Pods on the same node | Node overcommitted on limits with a high proportion of `BestEffort`/under-requested Pods  | Audit and correct requests cluster-wide, or right-size/scale-out the node pool                          |
| Node condition `DiskPressure=True`                             | Ephemeral storage or container image layers filling the node's disk                       | Check `kubectl describe node` for disk usage breakdown; clean up unused images, check log volume growth |
| Node condition `PIDPressure=True`                              | A workload spawning excessive processes/threads without a PID limit                       | Set container-level PID limits (`--pod-max-pids`) or fix the process-spawning behavior                  |
| Evictions happen with almost no warning on large-memory nodes  | Fixed `evictionHard.memory.available` threshold too small relative to node's total memory | Scale the eviction threshold (percentage-based) relative to node size, not a fixed absolute value       |

## 9. Best Practices

- Set `resources.requests` on every production workload as close to non-negotiable policy, enforced via `LimitRange` where feasible, since it is the deciding factor in eviction order under node pressure.
- Monitor node conditions (`MemoryPressure`, `DiskPressure`, `PIDPressure`) as first-class alerts, not just Pod-level restart counts, since they are the leading indicator that precedes evictions.
- Scale `evictionHard` thresholds proportionally to node size on large-memory node pools, rather than leaving small, fixed default thresholds that provide little real warning margin.

## 10. Common Anti-Patterns / Mistakes

- **Treating an `Evicted` Pod the same as an `OOMKilled` container** and investigating application-level memory behavior when the actual cause is node-wide resource contention driven by missing requests.
- **Leaving critical workloads with no `resources.requests`/`limits` at all**, making them `BestEffort` by default and first in line for eviction under any node pressure, entirely by accident.
- **Resizing nodes as a first response to repeated evictions** without first auditing whether under-requested workloads are the real driver of the overcommitment causing those evictions.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a Pod being `OOMKilled` and a Pod being `Evicted`?"_
**Model answer:** `OOMKilled` happens at the container level — the cgroup memory controller kills a specific container because it exceeded its own `resources.limits.memory`, reported with exit code `137`. `Evicted` happens at the node level — the kubelet proactively terminates Pods to relieve overall node pressure (memory, disk, or PIDs), and the victim Pod may well have been operating within its own limits; it simply lost out based on its QoS class when the node as a whole ran low on a resource. The fixes are different too — an `OOMKilled` container usually needs its own limit or code fixed, while an `Evicted` Pod usually points to node-wide overcommitment or missing `resources.requests`.
_What the interviewer is probing for:_ Clear separation between per-container and node-wide resource failure modes, since they're commonly conflated.

**🎯 Intermediate:** _"A Pod with no `resources.requests` or `limits` set keeps getting evicted whenever the node comes under memory pressure. Why, specifically, is this Pod always the first one killed?"_
**Model answer:** A Pod with no requests or limits at all is automatically classified `BestEffort`, the lowest-protected QoS class, and the kubelet's eviction manager always selects `BestEffort` Pods first when reclaiming resources under node pressure — it has essentially no guaranteed resource claim to fall back on. The fix is setting appropriate `resources.requests` (and ideally `limits`) on the Pod, which moves it into the `Burstable` or `Guaranteed` tier depending on whether requests equal limits, giving it meaningfully more protection the next time the node comes under pressure.
_What the interviewer is probing for:_ Understanding that QoS class is derived automatically from requests/limits and directly determines eviction priority.

**🎯 Senior:** _"You're seeing repeated node-pressure evictions across a node pool, but no single Pod appears to be misbehaving. How do you investigate?"_
**Model answer:** I'd start by checking `kubectl describe node` for each affected node's `Allocated resources` section, comparing total requests versus total limits versus actual node capacity — a large gap between requests and limits, combined with a high proportion of `BestEffort` or under-requested `Burstable` Pods on the node (checked via `status.qosClass` across all Pods on that node), points to systemic overcommitment rather than any one workload's fault. I'd resist the instinct to simply resize the node pool first, since that just raises the ceiling on the same underlying issue — teams under-requesting resources cluster-wide. Instead I'd push for a `LimitRange` default request policy at the namespace level and audit the highest-consuming workloads' actual usage against their declared requests, using that data to right-size requests before considering whether the node pool itself also needs to grow.
_What the interviewer is probing for:_ Diagnosing systemic overcommitment across a node pool rather than treating each eviction as an isolated Pod-level event, and resisting the reflexive "just add more nodes" fix.

**🎯 Architect:** _"Design a cluster-wide policy that prevents node-pressure eviction incidents from being discovered reactively, across a platform with many independent application teams."_
**Model answer:** I'd enforce `LimitRange` defaults at the namespace level cluster-wide, so any Pod deployed without explicit requests still receives a sane, non-`BestEffort` default rather than silently falling into the least-protected QoS tier — combined with a validating admission policy (§77, Part 10) that flags or blocks Pods requesting `Guaranteed`-tier resources far in excess of their historical usage, since over-requesting is its own form of node overcommitment risk in the other direction. I'd feed node condition metrics (`MemoryPressure`, `DiskPressure`, `PIDPressure`) and per-namespace requests-versus-actual-usage ratios into the same Grafana dashboards (§93, Part 12) app teams already use, so under-requesting shows up as a visible, attributable metric per team rather than only surfacing as a platform-wide incident. I'd also fold eviction events into the centralized logging/alerting pipeline (§94, Part 12) with alerting on the _node condition_ transitioning to pressure, not just on the eviction event itself, giving the platform team a chance to intervene (cordon, drain, scale) before Pods actually start getting killed. Finally, I'd periodically right-size cluster autoscaler node pool profiles based on aggregate requested-versus-actual usage trends, treating persistent overcommitment as a capacity-planning signal rather than a one-off firefight each time it manifests as an incident.
_What the interviewer is probing for:_ Building proactive, self-service-friendly guardrails (admission policy, default LimitRanges, per-team visibility) rather than relying on the platform team to manually catch overcommitment after the fact.

## 12. Common Misconceptions

1. **"`Evicted` and `OOMKilled` mean the same thing."** `OOMKilled` is a per-container cgroup limit kill; `Evicted` is a node-wide protective action by the kubelet, and the two have different causes and fixes.
2. **"A resized (bigger) node fixes repeated eviction problems."** It often just delays the same overcommitment at larger scale if the underlying issue is workloads without proper `resources.requests`, rather than genuine node undersizing.
3. **"Eviction thresholds are fixed defaults that don't need tuning."** `evictionHard` thresholds are frequently set as fixed absolute values that provide little warning margin on very large-memory nodes and should be scaled relative to node size.
4. **"Setting generous `limits` without matching `requests` has no downside."** It's a deliberate overcommitment tradeoff that should be monitored intentionally — left unmanaged, it silently increases how many Pods end up unprotected (`BestEffort`/low-request `Burstable`) during real pressure events.

## 13. 🔑 Key Takeaways

- Node-pressure eviction (`Evicted`) is a node-wide kubelet protective action, distinct from a per-container `OOMKilled` termination, and requires checking node conditions, not just container exit codes.
- QoS class — derived automatically from `resources.requests`/`limits` — directly determines eviction order: `BestEffort` first, `Burstable` next, `Guaranteed` last.
- Repeated evictions across many Pods on a node point toward systemic overcommitment (missing requests cluster-wide), not necessarily a node sizing problem — audit requests before resizing.
- `evictionHard` thresholds should scale with node size; a fixed absolute threshold reasonable on a small node can leave almost no warning margin on a large one.
- Node condition monitoring (`MemoryPressure`, `DiskPressure`, `PIDPressure`) should be a leading-indicator alert, not something discovered only after Pods start getting evicted.

## 14. Related Concepts & What's Next

This section extends §103's container-level resource debugging out to the node-wide level, directly applying §46's QoS class model to explain eviction ordering, and follows §103 as Part 13 moves from single-container failures to cluster-wide resource pressure. §105, next, is Part 13's capstone, synthesizing the networking (§101), storage (§102), application-level (§103), and cluster-level resource (§104) scenarios covered across this Part into complete, realistic incident narratives with runbook-style resolution steps.

**Next Section:** §105 — `Section-105-Part13-Incident-Case-Studies-Runbooks.md`
