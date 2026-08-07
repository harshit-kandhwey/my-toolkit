# Section 38 (Part 5): Vertical Pod Autoscaler (VPA) and Cluster Autoscaler (Concept-Level)

## 1. Definition

**Plain language:** [§37](./Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md) covered making more (or fewer) copies of a Pod in response to load. But two other, entirely separate questions remain: what if each individual Pod is simply requesting the wrong amount of CPU/memory in the first place — too much, wasting cluster capacity, or too little, getting OOMKilled? And what happens when there's genuinely nowhere left to schedule more Pods because every node is full? Neither question is HPA's job. The first is answered by the Vertical Pod Autoscaler; the second by the Cluster Autoscaler.

**Precise definition:** The **Vertical Pod Autoscaler (VPA)** is a **separate, non-core Kubernetes project** (not shipped as part of `kubernetes/kubernetes`, installed independently) that observes a workload's actual historical CPU/memory usage and recommends — or, in `Auto`/`Recreate` update mode, actively applies by evicting and recreating Pods — revised `resources.requests` (and optionally `limits`) values, right-sizing each individual Pod rather than changing how many exist. The **Cluster Autoscaler** is a separate control-loop component (cloud-provider-integrated, often installed as an in-cluster Deployment that calls out to cloud APIs) that watches for Pods stuck `Pending` due to insufficient cluster capacity and adds nodes to a node group/pool to accommodate them, and conversely removes underutilized nodes when their Pods can be safely rescheduled elsewhere — changing the number of **nodes**, not Pods or their resource requests.

## 2. Why This Matters

- **These are three genuinely distinct scaling axes, and conflating them is one of the most common Kubernetes autoscaling misunderstandings.** HPA ([§37](./Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md)) changes replica count; VPA changes per-Pod resource requests; Cluster Autoscaler changes node count. A workload can legitimately need all three simultaneously — right-sized Pods (VPA), the correct number of replicas for load (HPA), and enough nodes to actually host them (Cluster Autoscaler) — and each is configured, installed, and reasoned about completely independently.
- **VPA is explicitly not a built-in Kubernetes feature**, unlike HPA, which ships as a core API object. Treating VPA as "the vertical equivalent of the HPA object you get for free" leads to real surprises — it must be separately installed (typically via the `kubernetes/autoscaler` project's VPA components), and its default recommendation-only mode makes no changes at all unless explicitly configured to act.
- **VPA and HPA cannot safely target the same metric on the same workload simultaneously** — if both are configured to scale on CPU, they can fight each other (VPA changing the request that HPA's utilization percentage is computed against, while HPA changes replica count based on that same shifting baseline), a documented incompatibility that shapes real production configuration choices, connecting back to the replica-vs-resource distinction first drawn in [§27](../Part4/Section-27-Part4-ReplicaSets-Purpose-Relationship-To-Deployments.md)/[§28](../Part4/Section-28-Part4-Deployments-Rolling-Updates-Rollbacks-Revision-History.md).

🔑 **Key Takeaway:** HPA ([§37](./Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md)) scales replica count, VPA resizes each Pod's resource requests, and Cluster Autoscaler scales node count — three independent mechanisms, only one of which (HPA) is a built-in core Kubernetes API object; VPA and Cluster Autoscaler are separate projects installed on top of a cluster.

## 3. Prerequisites and Dependencies

Builds directly on [§37](./Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md) (HPA, to establish the contrast this section depends on) and [§27](../Part4/Section-27-Part4-ReplicaSets-Purpose-Relationship-To-Deployments.md)/[§28](../Part4/Section-28-Part4-Deployments-Rolling-Updates-Rollbacks-Revision-History.md) (ReplicaSets/Deployments, since VPA acts on the Pods those objects create and Cluster Autoscaler reacts to Pods those objects leave `Pending`).

## 4. Architecture Diagram

```text
Three independent autoscaling axes:

┌─────────────────────┐   ┌─────────────────────┐   ┌─────────────────────┐
│   HPA (§37, CORE)   │   │   VPA (SEPARATE     │   │  Cluster Autoscaler │
│                     │   │   PROJECT)          │   │  (SEPARATE PROJECT, │
│  Watches: metric vs.│   │  Watches: historical│   │   cloud-integrated) │
│  target             │   │  usage vs. request  │   │  Watches: Pending   │
│                     │   │                     │   │  Pods / idle nodes  │
│  Changes: REPLICA   │   │  Changes: RESOURCE  │   │  Changes: NODE      │
│  COUNT              │   │  REQUESTS per Pod   │   │  COUNT              │
│                     │   │                     │   │                     │
│  spec.replicas:     │   │  container.resources│   │  node group size:   │
│    3 → 7            │   │  .requests.cpu:     │   │    5 → 8 nodes      │
│                     │   │    250m → 500m      │   │  (cloud API call)   │
└─────────────────────┘   └─────────────────────┘   └─────────────────────┘
          │                          │                          ▲
          │  more Pods, same size    │  same Pods, resized      │
          ▼                          ▼                          │
  ┌──────────────────────────────────────────────────┐          │
  │   Scheduler (§14) attempts to place all Pods     │──────────┘
  │   If no node has room → Pod stays Pending        │  triggers
  │                                                  │  scale-out
  └──────────────────────────────────────────────────┘

VPA operating modes:
  Off        → recommendations only, visible via `kubectl describe vpa`, nothing applied
  Initial    → applied only at Pod creation time, never touches running Pods
  Recreate   → evicts and recreates running Pods with revised requests (brief disruption)
  Auto       → currently behaves like Recreate (in-place resize is an evolving feature)
```

- **VPA's `Recreate`/`Auto` modes cause Pod restarts** — because Kubernetes historically had no way to change a running container's resource requests without recreating the Pod, applying a VPA recommendation is inherently disruptive, a materially different operational cost than HPA's non-disruptive replica changes.
- **Cluster Autoscaler's scale-down path is conservative by design** — it only removes a node once it has confirmed every Pod on it can be safely rescheduled elsewhere (respecting PodDisruptionBudgets, [§39](./Section-39-Part5-Pod-Disruption-Budgets.md)), and it will not touch nodes running Pods it cannot safely evict.

## 5. Hands-On: Installing and Observing VPA and Cluster Autoscaler

### 5.1 Installing VPA and Reading Recommendations (`Off` Mode)

**Purpose:** Get right-sizing recommendations without any automatic Pod disruption — the safe first step before enabling active modes.

**Syntax:** VPA is installed separately (commonly cloned from `kubernetes/autoscaler`'s `vertical-pod-autoscaler` component); the `VerticalPodAutoscaler` CRD is then used per workload.

```yaml
# app-vpa.yaml
apiVersion: autoscaling.k8s.io/v1
kind: VerticalPodAutoscaler
metadata:
  name: app-vpa
spec:
  targetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: app
  updatePolicy:
    updateMode: "Off" # recommendation-only; nothing is applied
```

```bash
$ kubectl apply -f app-vpa.yaml
verticalpodautoscaler.autoscaling.k8s.io/app-vpa created

$ kubectl describe vpa app-vpa
...
Recommendation:
  Container Recommendations:
    Container Name:  app
    Lower Bound:
      Cpu:     180m
      Memory:  256Mi
    Target:
      Cpu:     310m
      Memory:  380Mi
    Upper Bound:
      Cpu:     520m
      Memory:  512Mi
```

**Production usage example:** `updateMode: "Off"` is the standard first deployment of VPA on any workload — teams review the `Target` recommendation against the currently configured request over one to two weeks of real traffic before ever enabling an active mode, since a bad recommendation applied automatically (e.g., during an unrepresentative low-traffic period) can under-provision a workload right before its next real spike.

**Common errors:** Running VPA in an active mode (`Recreate`/`Auto`) on the same metric HPA is also scaling on for the same workload — the two controllers can enter a feedback loop, since VPA changing the CPU request changes the denominator HPA's utilization percentage is computed against.

### 5.2 Observing Cluster Autoscaler React to a Pending Pod

**Purpose:** Show the trigger condition and cloud-provider interaction Cluster Autoscaler responds to.

```bash
$ kubectl get pods -l app=big-batch-job
NAME                 READY   STATUS    RESTARTS   AGE
big-batch-job-x7f2   0/1     Pending   0          45s

$ kubectl describe pod big-batch-job-x7f2 | grep -A3 Events
Events:
  Warning  FailedScheduling  50s  default-scheduler  0/5 nodes are available: 5 Insufficient cpu.
  Normal   TriggeredScaleUp  40s  cluster-autoscaler  pod triggered scale-up: [{node-group-a 5->8 (max: 10)}]

$ kubectl get nodes -w
NAME       STATUS     ROLES    AGE
node-a-6   NotReady   <none>   8s     # new node joining
...
node-a-6   Ready      <none>   65s

$ kubectl get pods -l app=big-batch-job
NAME                 READY   STATUS    RESTARTS   AGE
big-batch-job-x7f2   1/1     Running   0          2m
```

**Production usage example:** The `TriggeredScaleUp` Event referencing a specific node group and its bounds (`5->8 (max: 10)`) is the standard diagnostic signal that Cluster Autoscaler — not the scheduler and not HPA — is the component responding to this exact `Pending` scenario; the node-group `max` ceiling is a hard stop that Cluster Autoscaler will not exceed regardless of how many Pods remain Pending.

**Common errors:** Confusing a Cluster-Autoscaler-driven `Pending` (capacity genuinely exhausted, new nodes incoming) with a filtering-phase `Pending` from [§14](../Part2/Section-14-Part2-Scheduler-Internals-Preview-Filtering-Scoring.md) that no amount of new capacity will fix (e.g., an unsatisfiable node selector) — always check whether the `FailedScheduling` reason is resource-based before assuming Cluster Autoscaler will resolve it.

### 5.3 Configuring Cluster Autoscaler's Node Group Bounds

**Purpose:** Show the concept-level configuration surface without cloud-specific installation detail (which varies by EKS/AKS/GKE, covered in Part 16).

```yaml
# excerpt: cluster-autoscaler Deployment args (cloud-provider-specific flags vary)
containers:
  - name: cluster-autoscaler
    command:
      - ./cluster-autoscaler
      - --nodes=3:10:node-group-a
      - --scale-down-delay-after-add=10m
      - --scale-down-unneeded-time=10m
```

**Production usage example:** `--nodes=3:10:node-group-a` sets a floor of 3 and a ceiling of 10 nodes for that group — the floor guarantees baseline capacity even during a lull (avoiding a cold-start scale-up delay for the next traffic spike), and the ceiling caps runaway cost from a misbehaving workload or metric.

## 6. Production Usage Notes

- **VPA's `Recreate`/`Auto` modes are frequently avoided for latency-sensitive, low-replica-count services** specifically because the eviction-and-recreate cycle causes real disruption; teams commonly run VPA in `Off` mode indefinitely and apply its recommendations to manifests through a reviewed, deliberate process instead of letting VPA act automatically.
- **Cluster Autoscaler's scale-up latency (often 30–90 seconds for a new cloud instance to join and become `Ready`) means Pods triggering a scale-up sit `Pending` for that entire window** — workloads with strict low-latency scheduling requirements sometimes maintain a small buffer of intentionally over-provisioned capacity rather than relying purely on reactive scale-up.
- **Never run VPA in an active mode and HPA on the identical resource metric for the same workload** — this is explicitly called out as unsupported/risky in VPA's own documentation; a common safe pattern is VPA managing memory (which HPA rarely targets) while HPA scales on CPU or a custom metric.

## 7. Security Considerations

- Cluster Autoscaler requires cloud-provider IAM/credential access to create and destroy compute instances — that credential is a high-value target, since abuse could provision large amounts of billable infrastructure or destroy running capacity, and it should be scoped as narrowly as the cloud provider's IAM model allows.
- VPA's eviction-driven Pod recreation on `Recreate`/`Auto` mode interacts with PodDisruptionBudgets ([§39](./Section-39-Part5-Pod-Disruption-Budgets.md)) exactly like a voluntary disruption — a workload without a PDB has no guaranteed floor of availability during a VPA-triggered resize, which matters for security-relevant availability SLAs as much as for ordinary reliability.

## 8. Common Troubleshooting Scenarios

| Symptom                                                               | Likely Cause                                                                   | Resolution Path                                                                                                    |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| VPA recommendation exists but requests never change                   | `updateMode` is `"Off"` (recommendation-only by design)                        | Confirm this is intentional; switch to `Initial`/`Recreate`/`Auto` if active management is desired                 |
| Pods restarting unexpectedly with different resource requests         | VPA in `Recreate`/`Auto` mode applying a new recommendation                    | Expected behavior; review recommendation history and consider `Initial` mode if disruption is unacceptable         |
| Cluster stuck at max node count with Pods still Pending               | Node group `max` bound reached (Cluster Autoscaler will not exceed it)         | Raise the node group ceiling deliberately, or reduce demand (fewer replicas, smaller requests)                     |
| HPA replica count and VPA resource requests both changing erratically | VPA and HPA configured on the same metric for the same workload, feedback loop | Split responsibility — VPA on one resource dimension (e.g., memory), HPA on another (e.g., CPU or a custom metric) |

## 9. Best Practices

- Start every VPA rollout in `updateMode: "Off"` and review recommendations over a representative traffic window before enabling any active mode.
- Set Cluster Autoscaler node-group floors high enough to absorb ordinary traffic variance without a cold-start scale-up delay, and ceilings low enough to cap worst-case cost from a runaway workload.
- Never target the same resource metric with both an active-mode VPA and an HPA on the same workload — split responsibility across different dimensions or choose one mechanism per resource.

## 10. Common Anti-Patterns / Mistakes

- **Assuming VPA ships as a core Kubernetes API object the way HPA does** — it must be separately installed from the `kubernetes/autoscaler` project and is not present by default on any cluster.
- **Running VPA in `Auto`/`Recreate` mode on a low-replica, latency-sensitive service without a PodDisruptionBudget ([§39](./Section-39-Part5-Pod-Disruption-Budgets.md))**, risking a real availability dip every time VPA applies a resize.
- **Relying purely on Cluster Autoscaler's reactive scale-up for strict low-latency scheduling needs**, ignoring the real 30–90+ second window a new Pod spends `Pending` while a new node boots and joins.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between HPA, VPA, and Cluster Autoscaler in one sentence each?"_
**Model answer:** HPA changes how many replicas of a Pod exist based on a metric; VPA changes how much CPU/memory each individual Pod requests based on its observed usage; Cluster Autoscaler changes how many nodes the cluster has based on whether Pods are stuck Pending for lack of capacity or nodes are sitting underutilized.
_What the interviewer is probing for:_ Basic, correct separation of the three axes without conflating any pair of them.

**🎯 Intermediate:** _"Is VPA a built-in Kubernetes feature? What has to happen before it works?"_
**Model answer:** No — unlike HPA, which is a core API object shipped with every cluster, VPA is a separate project (part of `kubernetes/autoscaler`) that must be explicitly installed, deploying its own controller components and the `VerticalPodAutoscaler` CRD. Before it can do anything meaningful, it also needs a period of observed resource usage to build recommendations from, and — critically — its default and safest starting mode is `Off`, meaning even after installation it produces recommendations only and applies nothing until an active update mode is explicitly configured.
_What the interviewer is probing for:_ Awareness that VPA is not "free" the way HPA is, and correct understanding of its staged, opt-in operating modes.

**🎯 Senior:** _"A service has both an HPA and an active-mode VPA configured, both watching CPU. What goes wrong, and how would you fix it?"_
**Model answer:** VPA resizing the CPU request changes the denominator HPA's utilization percentage is computed against (utilization = usage / request), so as VPA adjusts the request up or down, HPA's computed utilization shifts independent of any real change in load, and HPA reacts by changing replica count in response to what is actually a VPA-driven artifact rather than genuine demand — the two controllers can end up chasing each other's changes. The fix is to split responsibility: keep HPA scaling on CPU (or ideally a custom/external metric less entangled with request sizing) for replica count, and either run VPA in `Off` mode as a periodic manual right-sizing input, or have VPA manage a different resource dimension (commonly memory) that HPA isn't scaling on at all.
_What the interviewer is probing for:_ Concrete understanding of the actual mechanical interaction that causes the conflict, not just "they can conflict," plus a workable mitigation.

**🎯 Architect:** _"Design an autoscaling strategy for a platform with hundreds of services of varying traffic shape and criticality, using all three mechanisms together without them undermining each other."_
**Model answer:** I'd treat the three mechanisms as answering three separate questions and assign clear default ownership: VPA in `Off` mode runs universally as a right-sizing advisory layer, feeding periodic, reviewed pull requests that adjust `resources.requests` baselines — not applied automatically in production for anything customer-facing, to avoid disruptive Recreate cycles on critical paths. HPA owns replica count for every service with variable load, scaling on CPU by default and on custom/external metrics (queue depth, request rate) for services where CPU is a poor proxy, with `behavior` policies tuned per criticality tier — fast scale-up/slow scale-down for user-facing tiers, more symmetric policies for cost-sensitive batch tiers. Cluster Autoscaler runs cluster-wide with node-group floors sized to absorb known daily/weekly traffic patterns without cold-start delay, and ceilings tied to a real budget review process, with PodDisruptionBudgets ([§39](./Section-39-Part5-Pod-Disruption-Budgets.md)) mandatory on every service so Cluster Autoscaler's scale-down path and any VPA-driven eviction both remain drain-safe. Finally, I'd bake a platform-level lint rule forbidding active-mode VPA and HPA on the same resource dimension for the same workload, since that specific conflict is well-understood and preventable at review time rather than needing to be debugged in production.
_What the interviewer is probing for:_ Ability to design a coherent, governed multi-mechanism autoscaling strategy at platform scale, with explicit guardrails against the known VPA/HPA conflict and disruption-safety via PDBs.

## 12. Common Misconceptions

1. **"VPA is the vertical counterpart to HPA and ships the same way."** HPA is a core, built-in Kubernetes API object; VPA is a separate project that must be installed independently and is not present on a cluster by default.
2. **"VPA and HPA can both freely scale the same metric on the same workload with no issue."** They can enter a feedback loop when both target the same resource dimension, since VPA changes the request that HPA's utilization percentage is computed against — documented as an unsupported/risky combination.
3. **"Cluster Autoscaler and HPA are the same mechanism at different levels."** HPA changes replica count within existing capacity; Cluster Autoscaler changes the amount of capacity (nodes) available in the first place — a Pod can be correctly scaled by HPA and still sit Pending if Cluster Autoscaler hasn't (yet) added enough nodes.
4. **"VPA in `Auto` mode resizes running Pods in place with zero disruption."** Until in-place resize matures as a stable feature, `Auto`/`Recreate` modes work by evicting and recreating the Pod with new resource requests — a real, if brief, disruption subject to PodDisruptionBudget protection ([§39](./Section-39-Part5-Pod-Disruption-Budgets.md)).

## 13. 🔑 Key Takeaways

- HPA ([§37](./Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md)) changes replica count, VPA changes per-Pod resource requests, and Cluster Autoscaler changes node count — three independent mechanisms answering three different questions.
- VPA is not a core Kubernetes component; it is a separately installed project (`kubernetes/autoscaler`) with its own CRD and controller, defaulting safely to recommendation-only (`Off`) mode.
- Cluster Autoscaler reacts to Pods stuck `Pending` for lack of capacity by adding nodes (bounded by node-group min/max), and conservatively removes underutilized nodes only when their Pods can be safely rescheduled elsewhere.
- Running an active-mode VPA and an HPA on the same resource metric for the same workload is a documented, risky combination that can produce a feedback loop — split responsibility across different resource dimensions instead.
- VPA's `Recreate`/`Auto` modes cause real Pod disruption (eviction and recreation), making PodDisruptionBudgets ([§39](./Section-39-Part5-Pod-Disruption-Budgets.md)) directly relevant to safe VPA operation.

## 14. Related Concepts & What's Next

[§37](./Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md) established HPA as the replica-count axis of autoscaling; this section completed the picture with the per-Pod-resource axis (VPA) and the node-count axis (Cluster Autoscaler), making explicit that only HPA is a core, built-in API object. [§27](../Part4/Section-27-Part4-ReplicaSets-Purpose-Relationship-To-Deployments.md)/[§28](../Part4/Section-28-Part4-Deployments-Rolling-Updates-Rollbacks-Revision-History.md) remain the foundation all three mechanisms ultimately act upon or around. [§39](./Section-39-Part5-Pod-Disruption-Budgets.md) (next) covers Pod Disruption Budgets, directly relevant to both VPA's eviction-driven resize and Cluster Autoscaler's scale-down path, since both are voluntary-disruption scenarios a PDB can bound.

**Next Section:** [§39](./Section-39-Part5-Pod-Disruption-Budgets.md) — `Section-39-Part5-Pod-Disruption-Budgets.md`
