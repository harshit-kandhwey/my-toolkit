# Section 68 (Part 9): Taints and Tolerations

## 1. Definition

**Plain language:** Affinity ([§66](./Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md), [§67](./Section-67-Part9-Pod-Affinity-Anti-Affinity.md)) is opt-in: a Pod chooses which nodes it wants. Taints flip the direction entirely — a node repels every Pod by default, and a Pod must explicitly declare it can tolerate that repulsion to be allowed on. Where affinity is a Pod reaching toward a node, a taint is a node pushing Pods away unless they carry the right key.

**Precise definition:** A **taint** is applied to a node (`key=value:effect`) and repels any Pod lacking a matching **toleration**, enforced by the `TaintToleration` Filter plugin ([§65](./Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md)). Three **effects** exist: `NoSchedule` (a Pod without a matching toleration will not be scheduled onto the node, but existing Pods already running there are unaffected), `PreferNoSchedule` (a soft form — the scheduler tries to avoid the node but will use it if no better option exists, evaluated in the Score phase), and `NoExecute` (the strictest — a Pod without a matching toleration is not scheduled onto the node, and any already-running Pod without a matching toleration is actively **evicted** from the node). A **toleration** on a Pod (`key`, `operator`, `value`, `effect`, and optionally `tolerationSeconds` for `NoExecute`) declares that the Pod can withstand a specific taint; tolerating a taint does not attract a Pod to that node — it merely permits scheduling there, which is precisely why taints/tolerations and affinity are complementary, not redundant, mechanisms.

## 2. Why This Matters

- **Taints are the mechanism behind the most common single-node cluster confusion** — a freshly `kubeadm init`'d control-plane node carries a `node-role.kubernetes.io/control-plane:NoSchedule` taint by default, which is why workloads refuse to schedule until that taint is removed or tolerated, a scenario CKA candidates encounter directly during cluster bring-up labs.
- **`NoExecute` is the only affinity-adjacent mechanism that can actively evict already-running Pods**, not merely block new placement — this makes it the correct tool for node-condition-driven eviction (e.g., `node.kubernetes.io/not-ready`, `node.kubernetes.io/unreachable`), and understanding `tolerationSeconds` is essential to reasoning about how long a Pod survives on a node that just went unhealthy.
- **Taints/tolerations are what actually enforces workload isolation that affinity alone cannot** — affinity only controls what a given Pod is willing to select; it does nothing to stop an unrelated Pod without any affinity rule from landing on a "reserved" node, which is exactly the gap taints close.

🔑 **Key Takeaway:** Affinity is Pod-side opt-in preference; taints/tolerations are node-side repulsion that Pods must explicitly opt out of — genuine workload isolation (compliance zones, GPU nodes, dedicated pools) requires taints, not affinity alone, because only a taint actually excludes Pods that never asked to be excluded.

## 3. Prerequisites and Dependencies

Builds on [§65](./Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md) (the `TaintToleration` Filter/Score plugin operating within the Scheduling Framework) and directly complements [§66](./Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md)/[§67](./Section-67-Part9-Pod-Affinity-Anti-Affinity.md) (node and Pod affinity), which this section repeatedly contrasts against for the isolation-vs-preference distinction. Also assumes familiarity with node lifecycle and condition reporting from Part 2 and kubeadm bring-up behavior (Part 3).

## 4. Architecture Diagram: Taint Effects and Toleration Matching

```text
   Node has taint:  dedicated=gpu:NoSchedule

                     New Pod (no toleration)
                              │
                              ▼
              ┌─────────────────────────────────┐
              │  TaintToleration Filter plugin  │
              │  Pod's tolerations checked      │
              │  against every node taint       │
              └───────────────┬─────────────────┘
                              │  no match found
                              ▼
                     Node ELIMINATED from
                     feasible set (Filter phase)


   Node has taint:  dedicated=gpu:NoSchedule
   Pod has toleration: { key: dedicated, operator: Equal,
                          value: gpu, effect: NoSchedule }
                              │
                              ▼
                     Toleration MATCHES taint
                     Node remains feasible
                     (does NOT attract the Pod —
                      merely permits it; an
                      unrelated Pod with no
                      toleration is still repelled)


   ── Effect comparison ──

   NoSchedule        : blocks NEW scheduling only; running Pods
                        already on the node are unaffected even
                        if the taint is added after they landed
   PreferNoSchedule  : soft — Score phase deprioritizes the node;
                        used only if no better feasible node exists
   NoExecute         : blocks NEW scheduling AND evicts any
                        ALREADY-RUNNING Pod lacking a matching
                        toleration; tolerationSeconds controls how
                        long a tolerating-but-time-limited Pod
                        survives before eviction anyway
```

- **A node can carry multiple taints simultaneously**, and a Pod must tolerate every one of them to be scheduled there — taints are ANDed, unlike affinity's OR-across-terms flexibility.
- **`kubectl taint nodes` is the imperative command**; taints can also be applied automatically by the control plane itself (e.g., `node.kubernetes.io/not-ready`, `node.kubernetes.io/memory-pressure`) as node condition signals, not only by an operator's manual action.

## 5. Hands-On: Applying and Tolerating Taints

### 5.1 Applying a NoSchedule Taint for Dedicated Node Pools

**Purpose:** Reserve a set of nodes for a specific workload class, repelling every other Pod by default.

**Syntax:** `kubectl taint nodes <node> <key>=<value>:<effect>`

```bash
$ kubectl taint nodes gpu-node-1 dedicated=gpu:NoSchedule
node/gpu-node-1 tainted

$ kubectl describe node gpu-node-1 | grep Taints
Taints:             dedicated=gpu:NoSchedule
```

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: ml-training
spec:
  tolerations:
    - key: dedicated
      operator: Equal
      value: gpu
      effect: NoSchedule
  containers:
    - name: trainer
      image: myregistry/ml-trainer:2.0.0
```

**Production usage example:** A platform team dedicates a pool of GPU-equipped nodes exclusively to ML training workloads by tainting every GPU node with `dedicated=gpu:NoSchedule`; only Pods explicitly carrying the matching toleration (typically paired with node affinity toward a `hardware=gpu` label, per [§66](./Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md)'s complementary-mechanism guidance) can land there, while every ordinary workload is automatically repelled with zero additional configuration on the general-purpose side.

**Common errors:** Tainting a node but forgetting that tolerating a taint does not cause a Pod to prefer that node — teams sometimes add only a toleration and are surprised the intended workload doesn't actually land on the GPU nodes; a toleration alone permits scheduling there, it does not attract it, so pairing with node affinity ([§66](./Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md)) is required to actually steer the Pod onto the tainted nodes rather than merely allowing it.

### 5.2 Removing the Default Control-Plane Taint

**Purpose:** Demonstrate the exact taint responsible for workloads refusing to schedule on a freshly bootstrapped single-node cluster.

**Syntax:** `kubectl taint nodes <node> <key>=<value>:<effect>-` (trailing `-` removes)

```bash
$ kubectl describe node controlplane-1 | grep Taints
Taints:             node-role.kubernetes.io/control-plane:NoSchedule

$ kubectl taint nodes controlplane-1 node-role.kubernetes.io/control-plane:NoSchedule-
node/controlplane-1 untainted
```

**Production usage example:** Single-node development clusters (kind, minikube, a lab `kubeadm` bring-up) commonly remove this taint entirely so ordinary workloads can schedule on the only node available — a step that should never be replicated on a genuine multi-node production cluster, where control-plane nodes remaining untainted for general workloads increases control-plane blast radius under resource pressure.

**Common errors:** Removing the control-plane taint on a production HA cluster "to free up capacity," inadvertently allowing arbitrary application workloads to compete for CPU/memory with kube-apiserver, etcd, and kube-scheduler on the same node — a resilience regression rather than a capacity win.

### 5.3 NoExecute with tolerationSeconds for Graceful Node-Failure Handling

**Purpose:** Control how long a Pod is permitted to keep running on a node that has just been marked unhealthy, before being forcibly evicted.

**Syntax:** `tolerations[].{key, operator, effect: NoExecute, tolerationSeconds}`

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: stateful-worker
spec:
  tolerations:
    - key: node.kubernetes.io/not-ready
      operator: Exists
      effect: NoExecute
      tolerationSeconds: 60
    - key: node.kubernetes.io/unreachable
      operator: Exists
      effect: NoExecute
      tolerationSeconds: 60
  containers:
    - name: worker
      image: myregistry/worker:1.5.0
```

**Production usage example:** A stateful worker Pod tolerates the automatically-applied `not-ready`/`unreachable` `NoExecute` taints for 60 seconds instead of the cluster default (typically 300 seconds), trading a longer window for a brief network blip to self-resolve against a faster failover to a healthy node — a deliberate tuning decision for workloads where fast recovery matters more than tolerating transient flakiness.

**Common errors:** Setting `tolerationSeconds` far too high on latency-sensitive workloads, causing user-facing Pods to sit unresponsive on a genuinely dead node for minutes before eviction finally triggers, when a shorter tolerance would have failed over far sooner.

## 6. Production Usage Notes

- **The control plane automatically applies several built-in `NoExecute` taints as node condition signals fire** — `node.kubernetes.io/not-ready`, `node.kubernetes.io/unreachable`, `node.kubernetes.io/memory-pressure`, `node.kubernetes.io/disk-pressure`, and others — meaning most Pods experience `NoExecute`-driven eviction without any operator ever running `kubectl taint` manually.
- **Every Pod gets default tolerations for `not-ready` and `unreachable` with a 300-second `tolerationSeconds`** unless overridden, which is why a Pod doesn't disappear the instant a node blips `NotReady` — this default grace period is frequently misunderstood as a bug rather than intentional tolerance for transient node flakiness.
- **Taints combined with node affinity is the standard pattern for genuine dedicated node pools** — the taint repels everyone by default, and affinity (not merely a toleration) is what actually steers the intended workload onto those nodes, since a toleration alone only removes the repulsion without adding attraction.
- **Resource-based scheduling considerations ([§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)) still apply on tainted nodes** — a Pod with a matching toleration for a GPU node's taint must still satisfy that node's actual resource fit; tolerating a taint says nothing about whether the node has capacity.

## 7. Security Considerations

- Taints are the practical enforcement mechanism behind genuine multi-tenant node isolation — a compliance-sensitive node pool should be both taint-protected (so unrelated Pods can never land there even accidentally) and access-controlled via RBAC restricting who can add the matching toleration to a PodSpec, since anyone able to add a toleration and pass admission can bypass the isolation.
- Removing or misconfiguring the control-plane's default `NoSchedule` taint on a production cluster expands the attack surface reachable by arbitrary workload Pods sharing a node with sensitive control-plane components — treat any deliberate control-plane taint removal as a hardening regression requiring explicit sign-off.
- A malicious or compromised actor with node-taint RBAC permissions (`nodes` update/patch) could strip protective taints from a dedicated pool, silently reopening an isolation boundary — restricting that RBAC verb is a relevant Part 10/Part 15 hardening control.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                     | Cause                                                                                                               | Fix                                                                                                                                                                                                                                                                             |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pods refuse to schedule on a fresh single-node cluster                      | Default `node-role.kubernetes.io/control-plane:NoSchedule` taint present                                            | Remove the taint for dev/lab clusters only, or add matching tolerations to intended workloads                                                                                                                                                                                   |
| A running Pod suddenly disappears from a node that just went `NotReady`     | Automatic `node.kubernetes.io/not-ready:NoExecute` taint fired after the default `tolerationSeconds` (300s) elapsed | Expected behavior; adjust `tolerationSeconds` if the grace period is wrong for that workload's tolerance                                                                                                                                                                        |
| Toleration added but Pod still doesn't land on the intended dedicated nodes | Toleration only removes repulsion; it doesn't attract — no node affinity steering the Pod there                     | Pair the toleration with node affinity ([§66](./Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md)) matching a label on the dedicated nodes                                                                                                                        |
| Pod scheduled onto a tainted node still fails to actually run there         | Toleration satisfied the `TaintToleration` Filter, but the node still lacks sufficient resources                    | Check resource requests/limits and `NodeResourcesFit` separately ([§65](./Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md), [§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)) — tolerating a taint says nothing about capacity |

## 9. Best Practices

- Always pair a dedicated-node-pool taint with node affinity on the intended workload, not merely a toleration — a toleration alone permits but does not steer placement.
- Tune `tolerationSeconds` deliberately per workload class rather than relying on the 300-second cluster default everywhere; latency-sensitive services often warrant a shorter window, while stateful workloads recovering slowly may warrant longer.
- Treat control-plane taint removal as a one-way hardening regression reserved for genuinely single-node dev/lab clusters, never production HA topologies.

## 10. Common Anti-Patterns / Mistakes

- **Adding a toleration and assuming it also attracts the Pod to the tainted node** — without accompanying affinity, the Pod may just as easily land on any other untainted node instead.
- **Removing the default control-plane taint on a production multi-node cluster** to "free up capacity," inadvertently allowing arbitrary workloads to compete with control-plane components for resources.
- **Leaving `tolerationSeconds` at its default for every workload uniformly**, rather than tuning it against each workload's actual tolerance for running on a node that has just gone unhealthy.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a taint and a toleration?"_
**Model answer:** A taint is applied to a node and repels Pods by default; a toleration is applied to a Pod and declares that it can withstand a specific taint, permitting it to be scheduled there. They work as a matched pair — the taint defines the repulsion, the toleration defines the exception — and a toleration only removes the repulsion, it doesn't make the scheduler prefer that node.
_What the interviewer is probing for:_ Correctly identifying which object (node vs. Pod) each mechanism lives on, and that tolerating is passive permission, not active attraction.

**🎯 Intermediate:** _"Explain the three taint effects and what happens to an already-running Pod in each case."_
**Model answer:** `NoSchedule` blocks new scheduling of non-tolerating Pods but has no effect on Pods already running on the node when the taint is added. `PreferNoSchedule` is the soft version — the scheduler tries to avoid the node in the Score phase but will still use it if no better feasible node exists, and again has no effect on already-running Pods. `NoExecute` is the only one of the three that actively evicts already-running Pods lacking a matching toleration, in addition to blocking new scheduling — and even a Pod with a matching toleration can still be evicted later if `tolerationSeconds` is set and that duration elapses.
_What the interviewer is probing for:_ Precise recall that only `NoExecute` touches already-running Pods, since this is the detail most often glossed over.

**🎯 Senior:** _"A Pod tolerates a GPU node's taint but never actually lands on a GPU node in practice. Why, and how do you fix it?"_
**Model answer:** Tolerating a taint only removes that node from the Pod's "forbidden" list — it does nothing to make the scheduler prefer or select that node over any other feasible one, so without any pull toward the GPU nodes specifically, the Pod is just as likely to land anywhere else that's also feasible. The fix is to add node affinity ([§66](./Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md)), typically required affinity matching a `hardware=gpu` label on the same nodes, so the Pod is both permitted (via toleration) and steered (via affinity) onto the intended pool. This taint-plus-affinity pairing is the standard pattern for dedicated node pools precisely because taints alone only ever repel, never attract.
_What the interviewer is probing for:_ Deep understanding that taints/tolerations and affinity solve two different halves of the dedicated-node-pool problem, and that using only one half is a common, fixable misconfiguration.

**🎯 Architect:** _"Design a strategy so that a batch analytics tier is resource-scheduled correctly ([§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)) onto high-memory nodes, isolated from a compliance-sensitive tier that must never share hardware with it, while both tolerate transient node failures gracefully."_
**Model answer:** I'd taint the compliance-sensitive node pool distinctly (e.g., `compliance=pci:NoSchedule`) and grant the matching toleration only to the compliance workloads, paired with required node affinity toward a `compliance-zone` label so those Pods are both permitted and steered there specifically — and I'd restrict RBAC on node taint/label mutation so only a controlled process can grant that toleration or apply that label, since either one alone bypasses the isolation if handed out loosely. The batch analytics tier gets its own separate taint on the high-memory pool (e.g., `workload=analytics:NoSchedule`) with matching toleration plus affinity toward that pool's memory-class label, and its actual placement within that pool is then governed by request/limit-driven resource-based scheduling ([§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)) rather than the taint itself, since tolerating a taint says nothing about whether a specific node has room. For transient failure tolerance, I'd set a moderate `tolerationSeconds` on the `not-ready`/`unreachable` `NoExecute` taints for both tiers — long enough to ride out brief network blips, short enough that a genuinely dead node's Pods fail over promptly — tuned per tier based on how quickly each can acceptably recover. The key architectural point is that taints enforce the isolation boundary, affinity provides the steering within it, resource-based scheduling governs fine-grained placement inside the permitted pool, and none of the three mechanisms substitutes for another.
_What the interviewer is probing for:_ Ability to compose taints/tolerations, affinity, and resource-based scheduling as three distinct, complementary layers rather than conflating them, plus awareness of the RBAC angle protecting the isolation boundary itself.

## 12. Common Misconceptions

1. **"A toleration makes the scheduler prefer that node."** It only removes that node from the Pod's forbidden list; actual steering toward the node requires node affinity as a separate, complementary mechanism.
2. **"NoSchedule affects already-running Pods too."** It only blocks new scheduling; Pods already running when a `NoSchedule` taint is added are entirely unaffected. Only `NoExecute` evicts running Pods.
3. **"Every Pod eviction from an unhealthy node is instantaneous."** Default tolerations for `not-ready`/`unreachable` give a 300-second grace period unless a Pod's own `tolerationSeconds` overrides it — eviction is delayed by design, not a malfunction.
4. **"Tolerating a taint guarantees the Pod has enough resources on that node."** Tolerating a taint only satisfies the `TaintToleration` Filter check; resource fit is evaluated entirely separately ([§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)), and a tolerated but resource-starved node will still eliminate the Pod on that basis.

## 13. 🔑 Key Takeaways

- Taints repel Pods from a node by default; tolerations are the Pod-side exception permitting scheduling there — tolerating never equals attracting.
- `NoSchedule` and `PreferNoSchedule` only affect new scheduling (hard and soft respectively); `NoExecute` is the only effect that also evicts already-running Pods, subject to `tolerationSeconds`.
- The control plane applies several `NoExecute` taints automatically based on node conditions (`not-ready`, `unreachable`, `memory-pressure`, `disk-pressure`), and every Pod carries default 300-second tolerations for the first two unless overridden.
- Genuine dedicated-node-pool isolation requires taints paired with node affinity — the taint excludes everyone else, affinity steers the intended workload in; neither alone accomplishes both halves.
- Tolerating a taint says nothing about resource fit on that node — resource-based scheduling ([§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)) governs placement within a tainted pool independently.

## 14. Related Concepts & What's Next

[§67](./Section-67-Part9-Pod-Affinity-Anti-Affinity.md) covered Pod affinity/anti-affinity as the complementary Pod-side mechanism to this section's node-side repulsion. [§65](./Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md) established the `TaintToleration` plugin within the Scheduling Framework. [§66](./Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md) covers the node affinity pairing referenced throughout for genuine dedicated-node-pool designs. [§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md) (resource-based scheduling) governs placement within a tainted, tolerated node pool independently of the taint itself. [§69](./Section-69-Part9-Manual-Scheduling-Custom-Schedulers.md) picks up next with manual scheduling and custom schedulers, covering how `nodeName` and alternate `schedulerName` values bypass or extend the default pipeline this Part has built up across [§65](./Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md)–[§68](./Section-68-Part9-Taints-Tolerations.md).

**Next Section:** [§69](./Section-69-Part9-Manual-Scheduling-Custom-Schedulers.md) — `Section-69-Part9-Manual-Scheduling-Custom-Schedulers.md`
