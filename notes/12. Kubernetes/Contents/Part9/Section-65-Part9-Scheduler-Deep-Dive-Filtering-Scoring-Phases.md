# Section 65 (Part 9): Scheduler Deep Dive: Filtering and Scoring Phases in Full

## 1. Definition

**Plain language:** [§14](../Part2/Section-14-Part2-Scheduler-Internals-Preview-Filtering-Scoring.md) introduced the scheduler's two-phase pipeline at a level sufficient to triage a `Pending` Pod. This section goes the rest of the way: every built-in filter and score plugin kube-scheduler actually ships with, how the scheduling framework's extension points fit together, how weights combine into a final score, and where a custom scheduling profile can hook in.

**Precise definition:** kube-scheduler is built on the **Scheduling Framework**, a pluggable architecture in which each scheduling attempt runs through an ordered sequence of **extension points** — `PreFilter`, `Filter`, `PostFilter`, `PreScore`, `Score`, `NormalizeScore`, `Reserve`, `Permit`, `PreBind`, `Bind`, `PostBind` — with each point implemented by one or more **plugins**. `Filter` plugins (`NodeResourcesFit`, `NodeAffinity`, `TaintToleration`, `NodeName`, `NodePorts`, `VolumeBinding`, `PodTopologySpread`, `InterPodAffinity`, and others) each independently answer yes/no per node, and a single "no" from any plugin eliminates that node. `Score` plugins (`NodeResourcesBalancedAllocation`, `NodeAffinity`, `InterPodAffinity`, `ImageLocality`, `PodTopologySpread`, `TaintToleration`) each return 0–100 per surviving node; scores are normalized and multiplied by a configurable per-plugin **weight**, then summed into a final ranking. This entire pipeline is configurable via a **KubeSchedulerConfiguration** object defining one or more named **scheduling profiles**, which is also the mechanism that underlies custom and multi-scheduler deployments ([§69](./Section-69-Part9-Manual-Scheduling-Custom-Schedulers.md)).

## 2. Why This Matters

- **Exam-relevant `Pending` diagnosis frequently requires naming the specific plugin at fault** — CKA's hardest scheduling questions go beyond "filtering eliminated all nodes" and expect recognition of which named filter (`NodeResourcesFit` vs. `TaintToleration` vs. `PodTopologySpread`) produced a given `FailedScheduling` message.
- **Scoring weights are the actual lever behind bin-packing and spread behavior** — teams tuning cluster-wide density or resilience are configuring `pluginConfig` weights in a scheduling profile, not adjusting some vague "scheduler setting"; understanding the plugin list is a prerequisite to that tuning.
- **Every later Part 9 section is a special case of this framework** — node affinity ([§66](./Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md)) and Pod affinity ([§67](./Section-67-Part9-Pod-Affinity-Anti-Affinity.md)) are `Filter`/`Score` plugin behavior, taints/tolerations ([§68](./Section-68-Part9-Taints-Tolerations.md)) are the `TaintToleration` plugin, and priority/preemption run through the same `PostFilter` extension point — this section is the shared foundation all of them build on.

🔑 **Key Takeaway:** The scheduler is not a monolithic algorithm but a configurable pipeline of independent plugins, each owning one extension point; every scheduling feature covered in the rest of Part 9 is implemented as a specific plugin (or pair of plugins) inside this same framework.

## 3. Prerequisites and Dependencies

Builds directly on [§14](../Part2/Section-14-Part2-Scheduler-Internals-Preview-Filtering-Scoring.md), which previewed the two-phase filtering/scoring model at a conceptual level sufficient for early troubleshooting. This section assumes that preview and delivers the full plugin catalog and framework mechanics. [§66](./Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md) (node affinity), [§67](./Section-67-Part9-Pod-Affinity-Anti-Affinity.md) (Pod affinity), and [§68](./Section-68-Part9-Taints-Tolerations.md) (taints/tolerations) each drill into one specific plugin family introduced here; [§69](./Section-69-Part9-Manual-Scheduling-Custom-Schedulers.md) covers custom schedulers built on the same profile mechanism; [§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md) covers resource-based scheduling built on `NodeResourcesFit`; [§71](./Section-71-Part9-Priority-Classes-Preemption.md) covers priority/preemption's use of `PostFilter`.

## 4. Architecture Diagram: The Scheduling Framework Extension Points

```text
   Unscheduled Pod (nodeName empty) ──► scheduling queue (priority-ordered)
                                                  │
                                                  ▼
        ┌───────────────────────────────────────────────────────────────┐
        │  PreFilter   — compute reusable state once per Pod            │
        │               (e.g., precompute Pod's affinity terms)         │
        └───────────────────────────────┬───────────────────────────────┘
                                          ▼
        ┌───────────────────────────────────────────────────────────────┐
        │  Filter (runs per node, short-circuits on first "no")         │
        │   - NodeResourcesFit     - TaintToleration                    │
        │   - NodeAffinity         - NodePorts / NodeName               │
        │   - VolumeBinding        - PodTopologySpread                  │
        │   - InterPodAffinity     - (+ any registered custom plugin)   │
        └───────────────────────────────┬───────────────────────────────┘
                              feasible nodes (0..N)
                                          │
                       ┌──────────────────┴─────────────────────┐
                       │ 0 feasible?                            │
                       ▼                                        ▼
        ┌───────────────────────────────┐      ┌───────────────────────────────┐
        │  PostFilter (only if 0)       │      │  PreScore / Score / Normalize │
        │  - DefaultPreemption:         │      │   each Score plugin returns   │
        │    can preempting a lower-    │      │   0-100 per feasible node;    │
        │    priority Pod free a node?  │      │   NormalizeScore rescales;    │
        │    (§71)                      │      │   final = Σ(score × weight)   │
        └───────────────────────────────┘      └──────────────────┬────────────┘
                                                                  ▼
                                                     ┌──────────────────────────┐
                                                     │  Reserve → Permit        │
                                                     │  (reserve resources on   │
                                                     │   the winning node before│
                                                     │   binding is finalized)  │
                                                     └────────────┬─────────────┘
                                                                  ▼
                                                     ┌────────────────────────────┐
                                                     │  PreBind → Bind → PostBind │
                                                     │  writes the Binding object │
                                                     │  via kube-apiserver (§8)   │
                                                     └────────────────────────────┘
```

- **`PostFilter` only runs when zero nodes survive filtering** — its default implementation is preemption ([§71](./Section-71-Part9-Priority-Classes-Preemption.md)): can evicting a lower-priority Pod make room? If not, the Pod stays `Pending`.
- **Reserve/Permit exist to prevent race conditions** between concurrent scheduling decisions targeting overlapping resources (notably for `VolumeBinding` and gang-scheduling-style admission webhooks) — the framework reserves the outcome before the irreversible `Bind` call.

## 5. Hands-On: Working With the Scheduling Framework

### 5.1 Listing the Effective Filter/Score Plugins via Scheduler Logs

**Purpose:** Confirm which plugins are actually active for a given scheduling profile, since the default set can be customized or disabled.

**Syntax:** `kubectl logs -n kube-system <scheduler-pod> --v=<verbosity>` (verbosity ≥ 4 surfaces per-plugin decisions)

```bash
$ kubectl logs -n kube-system kube-scheduler-controlplane-1 | grep -i "plugin" | head -5
I0714 09:12:03.114521       1 schedule_one.go:89] "Attempting to schedule pod" pod="default/web-7d9f"
I0714 09:12:03.114902       1 framework.go:355] "Plugin Filter" pod="default/web-7d9f" node="worker-2" plugin="NodeResourcesFit" status="Success"
I0714 09:12:03.115011       1 framework.go:355] "Plugin Filter" pod="default/web-7d9f" node="worker-2" plugin="TaintToleration" status="Success"
I0714 09:12:03.115320       1 framework.go:410] "Plugin Score" pod="default/web-7d9f" node="worker-2" plugin="NodeResourcesBalancedAllocation" score=72
```

**Production usage example:** When a Pod lands on an unexpected node and the team suspects a scoring-weight issue rather than a filtering bug, raising scheduler log verbosity temporarily (via the kubelet-managed static Pod manifest's `--v` flag) is the fastest way to see the actual per-plugin scores that drove the decision, without guessing.

**Common errors:** Leaving verbose scheduler logging enabled permanently in production — at `--v=4` or higher the scheduler logs every plugin evaluation for every Pod against every node, which is prohibitively noisy and CPU-costly on any cluster of meaningful size; use it as a temporary diagnostic, not a standing configuration.

### 5.2 Defining a Custom Scheduling Profile with Plugin Weights

**Purpose:** Show how `KubeSchedulerConfiguration` exposes per-plugin enable/disable and weight tuning, the mechanism behind every "tune the scheduler" production request.

**Syntax:**

```yaml
apiVersion: kubescheduler.config.k8s.io/v1
kind: KubeSchedulerConfiguration
profiles:
  - schedulerName: default-scheduler
    plugins:
      score:
        enabled:
          - name: NodeResourcesBalancedAllocation
            weight: 3
          - name: InterPodAffinity
            weight: 2
        disabled:
          - name: ImageLocality
```

**Production usage example:** A platform team running a bin-packing-sensitive cost-optimization initiative raises `NodeResourcesBalancedAllocation`'s weight relative to the defaults so the scheduler more aggressively favors nodes that balance CPU and memory utilization, directly reducing wasted allocatable capacity across the fleet without touching any application manifest.

**Common errors:** Editing `KubeSchedulerConfiguration` without restarting/reloading kube-scheduler's static Pod — since kube-scheduler is itself typically a static Pod ([§17](../Part3/Section-17-Part3-Static-Pods-Kubelet-Configuration.md)), a config change requires the kubelet to detect the manifest change and restart the container; a config file edit with no corresponding Pod restart silently has no effect.

### 5.3 Forcing a PostFilter/Preemption Path

**Purpose:** Demonstrate that a `Pending` Pod with matching priority-driven preemption eligibility takes a different path than a plain filtering failure.

```bash
$ kubectl get pod high-priority-job -o jsonpath='{.spec.priorityClassName}'
high-priority

$ kubectl describe pod high-priority-job | grep -A3 Events
Events:
  Type     Reason     Age   From               Message
  ----     ------     ----  ----               -------
  Normal   Preempted  10s   default-scheduler   Preempted pod default/low-priority-batch on node worker-3 to accommodate this pod
```

**Production usage example:** Seeing a `Preempted` Event confirms the `PostFilter` extension point's default `DefaultPreemption` plugin activated because zero nodes were feasible without evicting something — a materially different diagnostic path than a `FailedScheduling` Event, and one that requires checking `PriorityClass` values ([§71](./Section-71-Part9-Priority-Classes-Preemption.md)) rather than resource requests.

**Common errors:** Assuming any evicted Pod was OOM-evicted (a kubelet-driven node-pressure eviction) rather than scheduler-driven preemption — the two mechanisms look superficially similar in `kubectl get events` output but have entirely different root causes and remediation paths.

## 6. Production Usage Notes

- **Most clusters never need a custom `KubeSchedulerConfiguration`** — the default plugin set and weights handle the overwhelming majority of workloads; reach for profile customization only when a measured, specific bin-packing or spread problem exists, not preemptively.
- **Multiple scheduling profiles can coexist in one `KubeSchedulerConfiguration`**, each with its own `schedulerName`, letting a single kube-scheduler process serve several distinct scheduling policies without deploying separate scheduler binaries — a lighter-weight alternative to a fully custom scheduler ([§69](./Section-69-Part9-Manual-Scheduling-Custom-Schedulers.md)) for many use cases.
- **Scheduler throughput at scale is dominated by the `Filter` phase's short-circuit behavior** — plugins ordered to fail fast (cheap checks like `NodeName`/`NodePorts` before expensive ones like `InterPodAffinity`) materially reduce per-Pod scheduling latency on large clusters.

## 7. Security Considerations

- The scheduling framework itself has no authentication/authorization surface distinct from kube-apiserver's — kube-scheduler authenticates to the API server like any other control-plane client and its RBAC permissions (`pods/binding` write access chiefly) should be scoped to exactly that, per [§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)'s ServiceAccount hardening guidance.
- Because `KubeSchedulerConfiguration` can register out-of-tree custom plugins, any cluster accepting third-party scheduler plugin binaries introduces a supply-chain trust boundary — treat custom scheduler plugin code with the same image-provenance scrutiny as any other cluster component ([§117](../Part15/Section-117-Part15-Static-Analysis-Manifests-kube-linter-Kubesec.md)).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                | Likely Cause                                                                                            | Fix                                                                                                                                                                  |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FailedScheduling` names a specific plugin (e.g., `PodTopologySpread`) | That plugin's Filter check failed on every node                                                         | Inspect the specific constraint that plugin enforces (spread constraints, affinity terms, taints) rather than assuming a generic resource shortage                   |
| Pod consistently loses a scoring tie to a different node than expected | A scoring plugin's weight favors a different node characteristic than assumed                           | Enable verbose scheduler logging to see per-plugin scores; adjust `pluginConfig` weights if the default balance is wrong for the workload                            |
| Custom `KubeSchedulerConfiguration` change has no effect               | Static Pod manifest wasn't actually reloaded                                                            | Confirm the kubelet detected the manifest change and restarted the kube-scheduler static Pod ([§17](../Part3/Section-17-Part3-Static-Pods-Kubelet-Configuration.md)) |
| Pod shows a `Preempted` Event instead of `FailedScheduling`            | Zero nodes were feasible, but the Pod's priority allowed evicting a lower-priority Pod via `PostFilter` | Review `PriorityClass` assignments ([§71](./Section-71-Part9-Priority-Classes-Preemption.md)) rather than treating this as a resource-shortage bug                   |

## 9. Best Practices

- Treat the default plugin set and weights as the correct starting point for virtually every cluster, and only customize after observing a specific, measured placement problem.
- Use scheduler log verbosity as a temporary diagnostic tool, never a permanent production setting, given its cost at scale.
- When defining custom scheduling profiles, name them distinctly from `default-scheduler` and document which workloads opt into them via `spec.schedulerName`, so the profile's purpose stays discoverable months later.

## 10. Common Anti-Patterns / Mistakes

- **Reaching for a fully custom scheduler ([§69](./Section-69-Part9-Manual-Scheduling-Custom-Schedulers.md)) when a `KubeSchedulerConfiguration` profile with adjusted weights would have solved the problem** — profiles are far lower operational overhead than running and maintaining a second scheduler binary.
- **Diagnosing scoring-phase surprises by guesswork** instead of enabling verbose logging to see the actual per-plugin scores driving the decision.
- **Confusing scheduler-driven preemption with kubelet-driven node-pressure eviction** because both produce a Pod disappearing from a node — the root cause and remediation paths for each are entirely different.

## 11. Interview Questions

**🎯 Beginner:** _"What is the Kubernetes Scheduling Framework, in one sentence?"_
**Model answer:** It's the pluggable pipeline kube-scheduler runs every scheduling attempt through — a sequence of extension points like Filter and Score, each implemented by one or more independently swappable plugins, rather than one monolithic scheduling algorithm.
_What the interviewer is probing for:_ Basic recognition that the scheduler is plugin-based rather than a fixed black box.

**🎯 Intermediate:** _"Name three built-in Filter plugins and explain what each one checks."_
**Model answer:** `NodeResourcesFit` checks whether a node has enough unreserved allocatable CPU/memory for the Pod's requests. `TaintToleration` checks whether the Pod's tolerations match every taint on the node. `NodeAffinity` checks whether the node's labels satisfy the Pod's `requiredDuringSchedulingIgnoredDuringExecution` node affinity terms. Any one of these returning "no" eliminates that node from consideration entirely, regardless of how the others would have scored it.
_What the interviewer is probing for:_ Concrete plugin-level knowledge rather than only the abstract two-phase model.

**🎯 Senior:** _"How would you diagnose a Pod that schedules successfully but consistently lands on a smaller subset of nodes than expected, in a cluster with a custom `KubeSchedulerConfiguration`?"_
**Model answer:** I'd first confirm whether this is a filtering or scoring question — if the Pod could theoretically run anywhere but keeps landing on the same nodes, filtering has already ruled out the others (check taints, affinity, resource fit on the excluded nodes) or scoring weights are heavily favoring those nodes. I'd inspect the active `KubeSchedulerConfiguration` for that profile to see which Score plugins are enabled and their weights — a heavily weighted `NodeResourcesBalancedAllocation` or `ImageLocality` plugin, for instance, could systematically favor nodes that already run similar images or have a particular resource balance. Verbose scheduler logs showing per-plugin scores for a representative Pod would confirm which specific plugin is driving the concentration, rather than guessing from the outcome alone.
_What the interviewer is probing for:_ Ability to move from a fleet-wide symptom to a specific plugin/weight root cause using the framework's actual diagnostic surface, not just re-stating the two-phase model.

**🎯 Architect:** _"You're asked to support two distinct scheduling policies in one cluster — a bin-packing-optimized policy for batch workloads and a spread-optimized policy for customer-facing services — without running two separate scheduler deployments. How do you design this?"_
**Model answer:** I'd define two named profiles inside a single `KubeSchedulerConfiguration` served by one kube-scheduler process: one profile weighting `NodeResourcesBalancedAllocation` and `NodeResourcesFit` heavily for density, and a second profile weighting `PodTopologySpread` and `InterPodAffinity` (anti-affinity) heavily for spread, each with a distinct `schedulerName`. Batch workloads would set `spec.schedulerName` to the bin-packing profile and customer-facing Deployments to the spread profile, letting a single scheduler binary serve genuinely different placement philosophies without the operational cost of maintaining a fully custom scheduler ([§69](./Section-69-Part9-Manual-Scheduling-Custom-Schedulers.md)) or running redundant scheduler processes. I'd document the profile-to-workload mapping explicitly, since an undocumented multi-profile setup is a common source of "why did this Pod schedule differently than that one" confusion months later.
_What the interviewer is probing for:_ Awareness that multi-profile configuration inside the stock scheduler is usually the right-sized solution before reaching for custom scheduler binaries, and the ability to map business requirements onto concrete plugin weight choices.

## 12. Common Misconceptions

1. **"The scheduler runs one fixed algorithm."** It runs a configurable pipeline of independently swappable plugins across defined extension points; the "algorithm" is really the sum of whichever plugins are enabled and how they're weighted.
2. **"PostFilter always means the Pod failed permanently."** `PostFilter`'s default behavior is to attempt preemption — it can still result in a successful placement after evicting a lower-priority Pod, not just a dead end.
3. **"Any custom scheduling need requires writing a custom scheduler."** A large share of customization needs are satisfiable by adjusting plugin weights or enabling/disabling plugins within a `KubeSchedulerConfiguration` profile, which is far less operational overhead than a bespoke scheduler binary ([§69](./Section-69-Part9-Manual-Scheduling-Custom-Schedulers.md)).
4. **"Scoring plugin weights are fixed and not configurable."** Every built-in Score plugin's weight is configurable per profile via `pluginConfig`, and disabling plugins entirely is also supported.

## 13. 🔑 Key Takeaways

- kube-scheduler's behavior is the sum of plugins registered at each Scheduling Framework extension point (`PreFilter`, `Filter`, `PostFilter`, `PreScore`, `Score`, `Reserve`, `Permit`, `Bind`), not one monolithic algorithm.
- Filter plugins each independently veto a node; any single "no" is final and short-circuits further evaluation for that node.
- Score plugins return normalized 0–100 values that are multiplied by configurable weights and summed; `KubeSchedulerConfiguration` profiles are the supported way to tune this without writing custom code.
- `PostFilter`'s default implementation is preemption, giving a Pending Pod with sufficient priority a second path to scheduling by evicting lower-priority Pods ([§71](./Section-71-Part9-Priority-Classes-Preemption.md)).
- Every subsequent Part 9 topic — node affinity, Pod affinity, taints/tolerations, custom schedulers, resource-based scheduling, priority/preemption, topology spread — is a specific instance of this same plugin framework.

## 14. Related Concepts & What's Next

[§14](../Part2/Section-14-Part2-Scheduler-Internals-Preview-Filtering-Scoring.md) previewed the two-phase model this section completes. [§17](../Part3/Section-17-Part3-Static-Pods-Kubelet-Configuration.md) covers static Pods, relevant since kube-scheduler itself typically runs as one. [§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md) covers the RBAC scoping appropriate for kube-scheduler's own ServiceAccount. [§66](./Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md) next covers node affinity/anti-affinity as a deep dive into the `NodeAffinity` Filter/Score plugin pair introduced here, followed by [§67](./Section-67-Part9-Pod-Affinity-Anti-Affinity.md) (Pod affinity), [§68](./Section-68-Part9-Taints-Tolerations.md) (taints/tolerations), [§69](./Section-69-Part9-Manual-Scheduling-Custom-Schedulers.md) (custom schedulers), [§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md) (resource-based scheduling), [§71](./Section-71-Part9-Priority-Classes-Preemption.md) (priority/preemption), and [§72](./Section-72-Part9-Topology-Spread-Constraints.md) (topology spread) — each drilling into one plugin family from this section's catalog.

**Next Section:** [§66](./Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md) — `Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md`
