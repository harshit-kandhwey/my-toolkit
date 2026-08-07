# Section 14 (Part 2): Scheduler Internals Preview: Filtering and Scoring Phases

## 1. Definition

**Plain language:** When a new Pod needs a home, kube-scheduler doesn't just pick any node with free capacity — it runs a two-round contest. Round one throws out every node that flatly can't work. Round two ranks the survivors and picks the best of what's left. This section previews that two-round contest at a level sufficient for CKA-style reasoning; the exhaustive mechanics (every built-in predicate and priority function, extension points, scheduling profiles) are reserved for [§65](../Part9/Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md) in Part 9.

**Precise definition:** kube-scheduler assigns each unscheduled Pod to a node through two sequential phases: **filtering** (also historically called predicates), which produces the set of **feasible nodes** by eliminating any node that cannot satisfy the Pod's hard requirements (insufficient resources, unsatisfied node selectors, taints without matching tolerations, port conflicts, volume topology constraints), and **scoring** (historically called priorities), which ranks the remaining feasible nodes against a weighted set of criteria (resource balance, affinity preferences, spread) and selects the highest-scoring node — with ties broken pseudo-randomly to avoid the same node always winning.

## 2. Why This Preview Matters Now

- **It completes the control-plane component picture from [§8](./Section-08-Part2-Control-Plane-Components.md).** [§8](./Section-08-Part2-Control-Plane-Components.md) named kube-scheduler as "the placement decision-maker" without explaining the decision mechanism itself — this section supplies just enough of that mechanism to reason correctly about scheduling-related symptoms before Part 9's full treatment.
- **A huge share of "Pod stuck Pending" incidents are filtering-phase failures.** Recognizing that filtering eliminates nodes outright (an all-or-nothing gate) versus scoring merely ranking already-eligible nodes (a preference, never a hard block) is the single fastest way to triage a `Pending` Pod, and directly supports the reconciliation-loop mental model built in [§13](./Section-13-Part2-Controller-Manager-Controller-Pattern-Reconciliation-Loops.md).
- **CKA and CKAD both test scheduling behavior without expecting exam-day recall of every priority function's exact formula** — a solid conceptual grasp of "filter first, score second, ties broken randomly" answers the large majority of exam-relevant scheduling questions; the exhaustive algorithm detail in [§65](../Part9/Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md) is reserved for candidates going deeper into custom scheduler design or CKA's hardest edge cases.

🔑 **Key Takeaway:** Scheduling is always two distinct phases — filtering (hard elimination, all-or-nothing) then scoring (soft ranking of what survives) — and confusing the two is the most common source of misdiagnosed `Pending` Pods.

## 3. Prerequisites and Dependencies

Builds directly on [§8](./Section-08-Part2-Control-Plane-Components.md) (kube-scheduler's role among the five control-plane components) and [§13](./Section-13-Part2-Controller-Manager-Controller-Pattern-Reconciliation-Loops.md) (the generic controller/watch pattern, since the scheduler itself operates as a watch-driven loop over unscheduled Pods). Full mechanical depth resumes in [§65](../Part9/Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md), and priority-class-driven preemption specifically is covered in [§71](../Part9/Section-71-Part9-Priority-Classes-Preemption.md).

## 4. Architecture Diagram: The Two-Phase Scheduling Pipeline

```text
   New Pod created (nodeName empty) ──► visible to kube-scheduler via watch
                                                  │
                                                  ▼
                          ┌───────────────────────────────────────────┐
                          │              PHASE 1: FILTERING           │
                          │  (a.k.a. "predicates" — hard pass/fail)   │
                          │                                           │
                          │  For every node in the cluster, ask:      │
                          │   - Enough CPU/memory to satisfy requests?│
                          │   - nodeSelector / nodeAffinity satisfied?│
                          │   - Any taint without a matching          │
                          │     toleration on this Pod?               │
                          │   - Requested hostPort already taken?     │
                          │   - Volume topology / zone constraints    │
                          │     satisfiable from this node?           │
                          │                                           │
                          │  Any "no" ELIMINATES the node entirely.   │
                          └───────────────────┬───────────────────────┘
                                              │  feasible nodes
                                              │  (could be 0, 1, or many)
                                              ▼
                          ┌───────────────────────────────────────────┐
                          │              PHASE 2: SCORING             │
                          │  (a.k.a. "priorities" — weighted ranking) │
                          │                                           │
                          │  Each feasible node scored 0–100 on:      │
                          │   - Resource balance (avoid overpacking)  │
                          │   - Pod anti-affinity/affinity preference │
                          │   - Spread across zones/nodes             │
                          │   - Image-already-present locality, etc.  │
                          │                                           │
                          │  Weighted sum → highest score wins        │
                          │  (ties broken pseudo-randomly)            │
                          └───────────────────┬───────────────────────┘
                                              │
                                              ▼
                             Scheduler writes the binding decision
                             back via kube-apiserver (§8) — it never
                             starts the Pod itself; the kubelet on the
                             chosen node does that (§9).
```

- **Zero feasible nodes after filtering means the Pod stays `Pending` indefinitely** — this is not an error state the scheduler retries into success; it will keep re-evaluating on a watch trigger (e.g., a node's resources freeing up), but nothing changes until the cluster's actual state changes.
- **Scoring only ever operates on the survivors of filtering** — a node can score poorly and still be selected if it's the only feasible node left; scoring never overrides a hard filtering failure.

## 5. Hands-On: Observing Scheduling Decisions

### 5.1 Forcing and Observing a Filtering-Phase Failure

**Purpose:** Make the filtering phase's all-or-nothing behavior concrete by deliberately requesting more resources than any node can satisfy.

**Syntax:** `kubectl run <name> --image=<image> --requests=cpu=<amount>,memory=<amount>`

```bash
$ kubectl run oversized --image=nginx:1.25 \
    --requests='cpu=64,memory=256Gi' --restart=Never
pod/oversized created

$ kubectl get pod oversized
NAME        READY   STATUS    RESTARTS   AGE
oversized   0/1     Pending   0          12s

$ kubectl describe pod oversized | grep -A5 Events
Events:
  Type     Reason            Age   From               Message
  ----     ------            ----  ----               -------
  Warning  FailedScheduling  15s   default-scheduler   0/3 nodes are available:
  3 Insufficient cpu, 3 Insufficient memory.
```

**Production usage example:** This exact `FailedScheduling` Event message — "0/N nodes are available" followed by the specific reasons — is the fastest diagnostic signal that a Pod's resource requests exceed what any single node can offer, distinguishable at a glance from a taint/toleration mismatch or an affinity conflict, both of which produce differently worded reasons in the same Event.

**Common errors:** Reading `Pending` alone and assuming the scheduler itself has crashed — always check `kubectl describe pod` for the actual `FailedScheduling` reason before investigating the scheduler process; most `Pending` Pods reflect a correctly functioning scheduler correctly reporting zero feasible nodes.

### 5.2 Using `nodeSelector` to Watch Filtering Eliminate Nodes by Label

**Purpose:** Demonstrate a filtering constraint driven by a hard label match rather than resource pressure.

**Syntax:** `spec.nodeSelector: { <label-key>: <label-value> }`

```bash
$ kubectl label nodes worker-1 disktype=ssd
node/worker-1 labeled

$ cat <<'EOF' | kubectl apply -f -
apiVersion: v1
kind: Pod
metadata:
  name: ssd-only
spec:
  nodeSelector:
    disktype: ssd
  containers:
  - name: app
    image: nginx:1.25
EOF
pod/ssd-only created

$ kubectl get pod ssd-only -o wide
NAME       READY   STATUS    RESTARTS   AGE   NODE
ssd-only   1/1     Running   0          8s    worker-1
```

**Production usage example:** `nodeSelector` is the simplest possible filtering constraint — every node lacking the exact label is eliminated outright in the filtering phase, with no scoring-phase nuance possible; teams needing softer, weighted preferences instead of hard elimination reach for node affinity's `preferredDuringSchedulingIgnoredDuringExecution` form, covered in full in Part 9 ([§66](../Part9/Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md)).

### 5.3 Reading Scheduler Events to Distinguish Filtering vs. Scoring Outcomes

**Purpose:** Show that once a Pod is `Running`, its placement was the product of both phases, and `kubectl describe` still records which node won and (at higher log verbosity on the scheduler itself) why.

```bash
$ kubectl get events --field-selector reason=Scheduled --sort-by=.lastTimestamp
LAST SEEN   TYPE     REASON      OBJECT           MESSAGE
45s         Normal   Scheduled   pod/ssd-only     Successfully assigned default/ssd-only to worker-1
```

**Production usage example:** In clusters running multiple feasible nodes, correlating the `Scheduled` Event's target node against expectations (e.g., "why did it pick worker-2 over worker-3 when both looked equally eligible?") is exactly the kind of question that requires the scoring-phase detail deferred to [§65](../Part9/Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md) — this section's job is only to establish that such a ranking step exists and runs after filtering, not to compute it by hand.

## 6. Production Usage Notes

- **A cluster with only one control-plane-tainted node and no worker nodes will schedule nothing** by design — the default `NoSchedule` taint on control-plane nodes is a filtering-phase mechanism, not a scoring preference, and is a frequent cause of confusion on freshly bootstrapped single-node test clusters ([§16](../Part3/Section-16-Part3-Kubeadm-Cluster-Bootstrapping-Step-By-Step.md) covers this exact scenario during kubeadm bring-up).
- **Scoring behavior can shift cluster-wide bin-packing patterns** even when every Pod successfully schedules — teams tuning for cost efficiency (denser packing) versus resilience (spread across failure domains) are really tuning scoring-phase weights, a topic developed fully with topology spread constraints in [§72](../Part9/Section-72-Part9-Topology-Spread-Constraints.md).
- **The scheduler re-evaluates unscheduled Pods on relevant watch events, not on a fixed timer** — a Pod stuck `Pending` due to insufficient resources will schedule automatically the moment capacity frees up elsewhere, with no manual re-trigger needed.

## 7. Security Considerations

- Scheduling decisions are not a security boundary by themselves — taints/tolerations and node affinity control _where_ a Pod can run, but do not restrict _what_ a Pod can do once running there; that enforcement is SecurityContext and Pod Security Admission's job ([§45](../Part6/Section-45-Part6-SecurityContext-Pod-Container-Level.md); [§80](../Part10/Section-80-Part10-Secrets-Management-Integration-Vault-External-Secrets-Sealed-Secrets.md)), not the scheduler's.
- A compromised or maliciously configured custom scheduler ([§69](../Part9/Section-69-Part9-Manual-Scheduling-Custom-Schedulers.md)) could deliberately place sensitive workloads on under-hardened or attacker-controlled nodes — restricting who can specify `schedulerName` or deploy alternate schedulers is a relevant cluster-hardening concern covered at full depth in [§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md).

## 8. Common Troubleshooting Scenarios

| Symptom                                                           | Likely Cause                                                           | Resolution Path                                                                                                                                                  |
| ----------------------------------------------------------------- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pod `Pending`, Event says "Insufficient cpu/memory"               | Filtering phase eliminated every node on resource requests             | Reduce requests, add node capacity, or check for resource fragmentation across nodes                                                                             |
| Pod `Pending`, Event mentions taints                              | No node's tolerations match; filtering phase hard-eliminated all nodes | Add a matching toleration or remove/adjust the blocking taint ([§9](./Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md))                 |
| Pod schedules but consistently lands on the same handful of nodes | Scoring-phase weighting favoring those nodes (e.g., resource balance)  | Review affinity/anti-affinity and topology spread configuration ([§72](../Part9/Section-72-Part9-Topology-Spread-Constraints.md))                                |
| Pod `Pending` with zero Events at all                             | kube-scheduler itself is down or not receiving watches                 | Check scheduler process/Pod health and its api-server connectivity ([§99](../Part13/Section-99-Part13-Debugging-Node-Issues-NotReady-Nodes-kubelet-Failures.md)) |

## 9. Best Practices

- Always read the actual `FailedScheduling` Event message before assuming a scheduler outage — the overwhelming majority of `Pending` Pods reflect a healthy scheduler correctly reporting zero feasible nodes.
- Treat filtering and scoring as conceptually separate diagnostic questions: "is any node even eligible?" versus "why was this specific eligible node chosen over others?" — conflating them wastes investigation time.
- When designing workload placement rules, prefer hard filtering constraints (`nodeSelector`, required affinity, taints/tolerations) only for genuine hard requirements, and reserve scoring-phase preferences (preferred affinity) for soft, tunable preferences — full guidance in [§66](../Part9/Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md).

## 10. Common Anti-Patterns / Mistakes

- **Assuming `Pending` always means the scheduler is broken**, rather than checking whether it's correctly reporting that no node currently qualifies.
- **Using hard `nodeSelector`/required-affinity constraints for preferences that should be soft**, creating brittle scheduling that fails outright rather than degrading gracefully when the "ideal" node is temporarily unavailable.
- **Ignoring scoring-phase effects entirely** and being surprised by uneven bin-packing across nodes, when the scoring weights (resource balance, spread) were driving that distribution all along and are tunable.

## 11. Interview Questions

**🎯 Beginner:** _"What are the two phases kube-scheduler uses to place a Pod?"_
**Model answer:** Filtering, which eliminates every node that can't satisfy the Pod's hard requirements (resources, taints, node selectors, port conflicts), and scoring, which ranks the nodes that survive filtering against weighted criteria like resource balance and affinity preferences, picking the highest-scoring node. Filtering is all-or-nothing per node; scoring is a preference ranking among whatever remains.
_What the interviewer is probing for:_ Basic recall of the two-phase model without conflating hard elimination with soft preference.

**🎯 Intermediate:** _"A Pod is stuck Pending. How do filtering and scoring help you narrow down the cause?"_
**Model answer:** I'd start by checking `kubectl describe pod` for the `FailedScheduling` Event, since `Pending` with a populated Event almost always means filtering eliminated every node — the message itself (insufficient resources, taint mismatch, affinity conflict) tells me exactly which filtering criterion failed everywhere. If instead the Pod is `Running` but on a node I didn't expect, that's a scoring-phase question instead — filtering succeeded on multiple nodes, and I'd need to look at resource balance, affinity weights, or topology spread configuration to understand why scoring favored that particular node.
_What the interviewer is probing for:_ Ability to map an observed symptom to the correct phase, since the diagnostic path differs substantially between "nothing was eligible" and "something was eligible but not what I expected."

**🎯 Senior:** _"Why does Kubernetes separate filtering and scoring into two distinct phases instead of a single combined scoring pass that also excludes infeasible nodes?"_
**Model answer:** Separating them keeps the semantics of "hard requirement" and "soft preference" unambiguous and independently extensible. Filtering is a fast, all-or-nothing pass that can short-circuit — a node failing even one hard predicate is immediately discarded and never needs scoring computed at all, which matters for scheduler performance at scale, since scoring is comparatively expensive to compute across every remaining criterion. It also keeps the mental model and the extension points clean: scheduler plugins ([§65](../Part9/Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md)) can implement a `Filter` extension point without needing to reason about scoring weights, and vice versa, and cluster operators can reason about "will this Pod ever schedule at all" (a filtering question) completely separately from "which of the eligible nodes will it land on" (a scoring question) — collapsing them would make both harder to reason about and slower to compute.
_What the interviewer is probing for:_ Understanding of why the architectural separation exists, not just that it exists — genuine grasp of the design tradeoff versus memorized phase names.

**🎯 Architect:** _"You're designing a platform where certain workloads must never share a node with certain other workloads for compliance reasons, while other workloads should merely prefer spreading out for resilience but can double up under resource pressure. How does the filtering/scoring distinction shape your design?"_
**Model answer:** The compliance requirement is a hard, non-negotiable constraint, so it belongs in the filtering phase — implemented as required Pod anti-affinity (or, for stronger isolation, dedicated node pools with taints/tolerations), guaranteeing the scheduler will simply refuse to place those Pods together under any circumstances, producing a clear `Pending` failure rather than a silent compliance violation if no compliant placement exists. The resilience-oriented spreading preference, in contrast, belongs in the scoring phase — implemented as preferred anti-affinity or topology spread constraints with `whenUnsatisfiable: ScheduleAnyway`, letting the scheduler favor spreading when capacity allows but still schedule successfully (just less ideally distributed) under real resource pressure rather than leaving Pods unschedulable over a soft preference. Getting this distinction backwards in either direction is a real production risk: encoding a compliance boundary as a mere preference could silently place regulated workloads together under load, while encoding a resilience preference as a hard requirement could leave a fleet unschedulable during a legitimate capacity crunch when soft degradation would have been the safer failure mode.
_What the interviewer is probing for:_ Ability to translate business/compliance requirements into the correct scheduling mechanism (hard filter vs. soft score) and awareness of the real production failure modes of getting that mapping wrong.

## 12. Common Misconceptions

1. **"Scoring can override a filtering failure if a node scores well enough."** It cannot — scoring only ever ranks nodes that already survived filtering; a node eliminated in filtering is never reconsidered regardless of hypothetical score.
2. **"A `Pending` Pod always means the scheduler process has failed."** Far more often it means the scheduler is functioning correctly and reporting that literally no node currently qualifies — the Event message distinguishes these cases.
3. **"nodeSelector and node affinity are the same mechanism with different syntax."** `nodeSelector` is exclusively a hard filtering constraint; node affinity supports both a hard (`required...`) and soft (`preferred...`) form, with the soft form operating in the scoring phase instead ([§66](../Part9/Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md)).
4. **"The highest-scoring node is always chosen deterministically."** Ties among top-scoring feasible nodes are broken pseudo-randomly by design, specifically to avoid systematically overloading whichever node happens to be listed first.

## 13. 🔑 Key Takeaways

- Scheduling is strictly two sequential phases: filtering (hard, all-or-nothing elimination) then scoring (soft, weighted ranking of survivors) — never the reverse, and scoring never rescues a filtering failure.
- The large majority of `Pending` Pod incidents are filtering-phase outcomes, diagnosable directly from the `FailedScheduling` Event message without needing scoring-phase detail.
- `nodeSelector`, required affinity, and taints/tolerations are filtering-phase (hard) mechanisms; preferred affinity and topology spread weighting are scoring-phase (soft) mechanisms — mapping a requirement to the wrong mechanism is a common and consequential design mistake.
- The scheduler only decides placement and writes that decision via kube-apiserver ([§8](./Section-08-Part2-Control-Plane-Components.md)) — it never starts a Pod itself, and it re-evaluates unscheduled Pods on relevant watch events rather than a fixed timer.
- This section is intentionally a preview; [§65](../Part9/Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md) delivers the full predicate/priority-function catalog, extension points, and custom scheduler mechanics.

## 14. Related Concepts & What's Next

[§8](./Section-08-Part2-Control-Plane-Components.md) introduced kube-scheduler's role among the five control-plane components; this section supplied the mechanism behind that role. [§13](./Section-13-Part2-Controller-Manager-Controller-Pattern-Reconciliation-Loops.md)'s controller/watch pattern underlies how the scheduler itself observes unscheduled Pods. [§9](./Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md) covers the kubelet, the data-plane component that acts on the scheduler's decision. [§65](../Part9/Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md) delivers the full filtering/scoring depth this section previewed, and [§66](../Part9/Section-66-Part9-Node-Selectors-Node-Affinity-Anti-Affinity.md)–[§72](../Part9/Section-72-Part9-Topology-Spread-Constraints.md) cover affinity, taints/tolerations, priority/preemption, and topology spread in full. [§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md) covers cluster-hardening concerns touching custom schedulers. [§15](./Section-15-Part2-High-Availability-Control-Plane-Architectures.md) (next) closes out Part 2 with high-availability control-plane topologies.

**Next Section:** [§15](./Section-15-Part2-High-Availability-Control-Plane-Architectures.md) — `Section-15-Part2-High-Availability-Control-Plane-Architectures.md`
