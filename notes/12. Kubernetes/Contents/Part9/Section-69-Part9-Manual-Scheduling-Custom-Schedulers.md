# Section 69 (Part 9): Manual Scheduling and Custom Schedulers

## 1. Definition

**Plain language:** Every Pod normally gets placed onto a node by kube-scheduler running its filtering and scoring pipeline behind the scenes. But the scheduler is not magic and not mandatory — you can bypass it entirely by telling Kubernetes exactly which node to use, or you can replace it with your own scheduling program that makes placement decisions using whatever logic your organization needs.

**Precise definition:** **Manual scheduling** means setting a Pod's `spec.nodeName` field directly at creation time, which causes the kubelet on the named node to bind and run the Pod without kube-scheduler ever being consulted — no filtering, no scoring, no admission through the scheduling pipeline at all. A **custom scheduler** is an alternative binary (or additional scheduler process) that watches for unscheduled Pods carrying a specific `spec.schedulerName`, applies its own placement algorithm, and writes a `Binding` object to the API server exactly as kube-scheduler would. Kubernetes supports running multiple schedulers simultaneously in the same cluster, each responsible for a distinct subset of Pods identified by `schedulerName`, coexisting without conflict because they don't compete for the same Pods.

## 2. Why This Matters

- **Manual scheduling is the escape hatch when the default scheduler's algorithm doesn't fit an edge case.** Understanding `nodeName` clarifies what the scheduler actually does — bind a Pod to a node — which makes the entire filtering/scoring pipeline and its taint/toleration rules ([§68](./Section-68-Part9-Taints-Tolerations.md)) easier to reason about by contrast.
- **Custom schedulers are a real production pattern, not just a CKA exam trick.** Batch scheduling systems (Volcano, YuniKorn) and GPU-aware schedulers run as separate `schedulerName`-scoped binaries precisely because kube-scheduler's default algorithm doesn't model gang scheduling or fractional GPU allocation well.
- **Multiple schedulers running concurrently is a foundational concept for everything else in Part 9.** Resource-based scheduling ([§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)), priority/preemption ([§71](./Section-71-Part9-Priority-Classes-Preemption.md)), and topology spread ([§72](./Section-72-Part9-Topology-Spread-Constraints.md)) are all behaviors of the _default_ scheduler — knowing that they can, in principle, be replaced or supplemented clarifies what's a Kubernetes primitive versus a default-scheduler-specific behavior.

🔑 **Key Takeaway:** Setting `nodeName` bypasses kube-scheduler entirely; setting `schedulerName` routes a Pod to an alternative scheduler process — both are legitimate mechanisms for cases where the default filtering/scoring pipeline ([§68](./Section-68-Part9-Taints-Tolerations.md) and earlier) isn't the right tool.

## 3. Prerequisites and Dependencies

Builds directly on [§68](./Section-68-Part9-Taints-Tolerations.md) (Taints and Tolerations), the last of the default scheduler's placement-constraint mechanisms covered in this Part, and assumes familiarity with the scheduler's filtering/scoring pipeline introduced earlier in Part 9.

## 4. Architecture Diagram

```text
                    New Pod created (spec.nodeName empty)
                                  │
                 ┌────────────────┴─────────────────┐
                 │                                  │
      spec.nodeName SET manually        spec.nodeName EMPTY
                 │                                  │
                 ▼                                  ▼
      kubelet on that node sees            kube-scheduler (or custom
      a Pod already bound to it            scheduler matching
      via nodeName — binds and             spec.schedulerName) watches
      runs it directly.                    for unbound Pods.
      NO filtering, NO scoring,                        │
      NO scheduler involvement               ┌─────────┴─────────┐
      at all.                                │                   │
                                    schedulerName:          schedulerName:
                                    default-scheduler        my-custom-scheduler
                                             │                   │
                                             ▼                   ▼
                                     kube-scheduler runs   custom scheduler binary
                                     filter/score/bind     runs its own algorithm,
                                     (§65-§68)              writes Binding object
                                             │                   │
                                             └─────────┬─────────┘
                                                       ▼
                                            Pod bound to a node; kubelet
                                            on that node runs it
```

- Multiple scheduler processes can run in the same cluster simultaneously, each watching only Pods whose `schedulerName` matches its own identity.
- A Pod with `nodeName` set at creation is never visible to any scheduler's "unscheduled Pods" watch — it skips the entire pipeline.

## 5. Hands-On

### 5.1 Manual Scheduling via `spec.nodeName`

**Purpose:** Force a Pod onto a specific node without involving kube-scheduler at all — useful for emergency placement, debugging scheduler behavior, or isolating whether a Pending Pod's problem is scheduling logic versus something the kubelet itself rejects.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: manually-placed
spec:
  nodeName: worker-node-3
  containers:
    - name: app
      image: myregistry/app:2.0.0
```

```bash
# Rescheduling an already-Pending Pod by binding it manually
# (nodeName is immutable once set at creation, so this must be
# a fresh Pod, not an edit of an existing one)
kubectl get nodes
kubectl apply -f manually-placed.yaml
```

**Production usage example:** During an incident where kube-scheduler itself is crash-looping ([§104](../Part13/Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md), control-plane failure scenarios), an SRE can keep critical workloads deployable by setting `nodeName` directly on a handful of manifests, sidestepping the broken scheduler entirely until the control plane is restored — a break-glass procedure, not a routine practice.

**Common errors:** Setting `nodeName` to a node that doesn't exist or is `NotReady` leaves the Pod stuck, because there is no scheduler retry logic in this path at all — kubelet on the named node simply never picks it up, and `kubectl describe pod` shows no scheduling events whatsoever since the scheduler was never involved.

### 5.2 Writing and Deploying a Custom Scheduler

**Purpose:** Run a second scheduler in the cluster that handles a specific subset of Pods using custom logic, while kube-scheduler continues handling everything else.

**Syntax:**

```yaml
# Deployment running a custom scheduler binary alongside kube-scheduler
apiVersion: apps/v1
kind: Deployment
metadata:
  name: my-custom-scheduler
  namespace: kube-system
spec:
  replicas: 1
  selector:
    matchLabels:
      component: my-custom-scheduler
  template:
    metadata:
      labels:
        component: my-custom-scheduler
    spec:
      serviceAccountName: my-custom-scheduler
      containers:
        - name: scheduler
          image: myregistry/custom-scheduler:1.0.0
          command:
            - /custom-scheduler
            - --scheduler-name=my-custom-scheduler
            - --leader-elect=true
---
apiVersion: v1
kind: Pod
metadata:
  name: gpu-batch-job
spec:
  schedulerName: my-custom-scheduler
  containers:
    - name: worker
      image: myregistry/gpu-worker:3.1.0
```

**Example usage and expected output:**

```bash
$ kubectl get pods -n kube-system -l component=my-custom-scheduler
NAME                                    READY   STATUS    RESTARTS   AGE
my-custom-scheduler-6d9f8c9b7f-x2k9p    1/1     Running   0          4m

$ kubectl describe pod gpu-batch-job | grep -A2 Events
Events:
  Type    Reason     Age   From                  Message
  Normal  Scheduled  30s   my-custom-scheduler   Successfully assigned default/gpu-batch-job to worker-node-5
```

**Production usage example:** Volcano and Apache YuniKorn are production-grade custom schedulers deployed exactly this way — they register as `schedulerName: volcano` or `schedulerName: yunikorn`, and only Pods that explicitly opt in via that field are managed by them, while every other Pod in the cluster continues to use the default `default-scheduler` untouched.

**Common errors:** Forgetting `--leader-elect` (or an equivalent HA mechanism) when running more than one replica of a custom scheduler causes two instances to both try binding the same Pod, resulting in a race and a `Binding` conflict error surfaced in the scheduler's logs — custom schedulers must implement the same single-writer discipline kube-scheduler relies on via its own leader election.

## 6. Production Usage Notes

- Custom schedulers are almost always deployed for **specialized workload classes** — batch/HPC job scheduling with gang semantics, GPU-fraction allocation, or cost-aware bin-packing — not as a general replacement for kube-scheduler, since reimplementing its full filtering/scoring feature set is substantial engineering effort.
- A more common production pattern than a fully custom scheduler is **scheduler configuration profiles** (`KubeSchedulerConfiguration` with multiple named profiles, each with its own plugin set), which lets a single kube-scheduler process act like several logical schedulers distinguished by `schedulerName` without running separate binaries.
- Manual scheduling via `nodeName` shows up in automated tooling too — some CI-driven test frameworks pin ephemeral test Pods to specific nodes with known hardware (e.g., a GPU-equipped node) rather than relying on affinity rules, when the workload is short-lived enough that scheduler correctness isn't worth the added spec complexity.

## 7. Security Considerations

- Manually setting `nodeName` bypasses any admission-time scheduling constraints that would otherwise be enforced through the scheduler's filtering phase (such as taints that reject workloads from sensitive nodes) — RBAC alone must be relied on to prevent unauthorized users from creating Pods with `nodeName` pointed at nodes they shouldn't be able to target.
- A custom scheduler's ServiceAccount typically needs `create` permission on `bindings` and broad `get`/`list`/`watch` on Pods and Nodes — over-scoping this ServiceAccount's RBAC ([§74](../Part10/Section-74-Part10-Authorization-Modes-RBAC-ABAC-Node-Webhook.md)) turns a scheduling component into a high-value target, since it can effectively place workloads anywhere in the cluster.
- Running an unreviewed third-party custom scheduler introduces a new, highly privileged control-plane-adjacent component into the cluster's trust boundary; treat its image provenance and RBAC footprint with the same scrutiny given to kube-scheduler itself.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                  | Likely Cause                                                                                          | Resolution Path                                                                                     |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Pod stuck `Pending` forever with zero scheduling events                  | `spec.schedulerName` references a scheduler that isn't running or doesn't exist                       | `kubectl get pods -n kube-system` to confirm the named scheduler is deployed and healthy            |
| Pod with `nodeName` set never starts                                     | Target node doesn't exist, is `NotReady`, or lacks capacity                                           | `kubectl get nodes -o wide`; verify node name spelling and node health                              |
| Two Pods land on the same node unexpectedly, ignoring resource pressure  | `nodeName` set manually, bypassing the filtering phase that would have rejected an over-capacity node | Avoid manual scheduling for workloads that need resource-aware placement; use the default scheduler |
| Custom scheduler binds Pods intermittently or with conflicting decisions | Multiple custom scheduler replicas running without leader election                                    | Enable leader election or run exactly one active replica                                            |

## 9. Best Practices

- Reserve manual scheduling (`nodeName`) for break-glass operational scenarios or narrow, well-understood test tooling — never as a routine placement mechanism for production workloads, since it forfeits every safety check the scheduler provides.
- When a specialized workload class genuinely needs custom placement logic, evaluate a mature existing custom scheduler (Volcano, YuniKorn) before building one from scratch — reimplementing filtering/scoring correctness is a substantial undertaking.
- If only a different _set of plugins or weights_ is needed rather than fundamentally different logic, prefer `KubeSchedulerConfiguration` profiles over a fully separate custom scheduler binary — it's far less operational overhead.

## 10. Common Anti-Patterns / Mistakes

- **Using `nodeName` as a substitute for node affinity or taints/tolerations** in production manifests, which silently disables all scheduler safety checks (resource fit, taints, affinity) for that Pod.
- **Running a custom scheduler without leader election** when scaled beyond one replica, producing binding races that are difficult to diagnose because both instances appear healthy individually.
- **Building a fully custom scheduler for a problem that scheduler profiles or extenders could solve**, incurring unnecessary long-term maintenance burden for logic that a configuration change could have achieved.

## 11. Interview Questions

**🎯 Beginner:** _"What happens if you set `spec.nodeName` on a Pod manifest before creating it?"_
**Model answer:** The Pod is bound directly to the named node without kube-scheduler ever being involved. The kubelet on that node sees the Pod already assigned to it and starts running it immediately, skipping the filtering and scoring phases entirely, including any resource-fit or taint checks.
_What the interviewer is probing for:_ Basic understanding that `nodeName` is a bypass mechanism, not a scheduling _hint_.

**🎯 Intermediate:** _"How can multiple schedulers coexist in the same cluster without conflicting?"_
**Model answer:** Each scheduler process watches only Pods whose `spec.schedulerName` matches its own configured identity. Kube-scheduler defaults to handling Pods with `schedulerName: default-scheduler` (or an empty field, which is treated the same way), while a custom scheduler is deployed with a distinct name and only acts on Pods explicitly assigned to it. Because the two never contend over the same Pod, there's no conflict as long as every Pod's `schedulerName` maps to exactly one running scheduler.
_What the interviewer is probing for:_ Understanding `schedulerName` as the actual coexistence mechanism, not vague awareness that "you can have custom schedulers."

**🎯 Senior:** _"A team wants GPU-fractional bin-packing that the default scheduler doesn't support well. Walk through your options before recommending a fully custom scheduler."_
**Model answer:** I'd first check whether device plugins plus existing scheduler extenders or a `KubeSchedulerConfiguration` profile with a custom scoring plugin could express the bin-packing preference — that's far less engineering and operational burden than a standalone scheduler. If the requirement genuinely needs semantics the plugin framework can't express (e.g., gang scheduling across multiple Pods as an atomic unit), I'd evaluate an existing mature project like Volcano or YuniKorn rather than writing one from scratch, since correctness in the filtering/scoring pipeline is deceptively hard to replicate. Only if neither option fits would I build a bespoke scheduler, and even then I'd keep its scope narrow — handling only the Pods that genuinely need the special logic via `schedulerName`, leaving the default scheduler responsible for everything else.
_What the interviewer is probing for:_ Whether the candidate escalates to "build a custom scheduler" only after ruling out lower-effort native mechanisms, and understands the real engineering cost of scheduler correctness.

**🎯 Architect:** _"You're designing a platform where several workload classes (interactive services, batch jobs, GPU training) coexist in one cluster. How do you decide what each uses for placement?"_
**Model answer:** I'd keep the default scheduler as the placement engine for interactive services, since its filtering/scoring pipeline (resource fit, affinity, taints, topology spread) already covers their needs well. For batch jobs needing gang scheduling and queue-based fairness, I'd route them via `schedulerName` to a dedicated batch scheduler like Volcano, isolating its blast radius to only the Pods that opt in. GPU training workloads I'd evaluate against whatever the GPU vendor's device plugin and any accompanying scheduler extension recommend, since GPU topology-aware placement (NVLink adjacency, for instance) is a solved problem in that ecosystem I wouldn't want to reinvent. The unifying principle is that `schedulerName` gives me a clean per-workload-class boundary — I never want a single scheduler binary trying to be everything to every workload type, and I never want to build custom scheduling logic where a mature, purpose-built project already exists.
_What the interviewer is probing for:_ Systems-level thinking about workload segmentation and appropriate build-vs-adopt judgment for a genuinely platform-scale decision.

## 12. Common Misconceptions

1. **"`nodeName` is just another form of node affinity."** Node affinity still goes through the scheduler's filtering/scoring pipeline and can fail gracefully (Pod stays Pending with an explanatory event); `nodeName` bypasses the scheduler entirely with no such safety net.
2. **"A cluster can only ever have one scheduler."** Kubernetes explicitly supports multiple concurrent schedulers distinguished by `schedulerName`, and this is a documented, supported pattern used by real production tooling.
3. **"Writing a custom scheduler is a common, low-effort customization."** In practice it requires reimplementing meaningful parts of the filtering/scoring contract correctly (including edge cases around resource accounting and race conditions), which is why most teams reach for scheduler profiles or existing projects like Volcano/YuniKorn instead.

## 13. 🔑 Key Takeaways

- Setting `spec.nodeName` binds a Pod directly to a node, bypassing kube-scheduler's filtering/scoring pipeline entirely — including taint and resource-fit checks covered in [§68](./Section-68-Part9-Taints-Tolerations.md) and earlier sections.
- `spec.schedulerName` routes a Pod to a specific scheduler process, and Kubernetes natively supports multiple schedulers coexisting without conflict as long as each Pod maps to exactly one.
- Custom schedulers are a legitimate production tool for specialized workload classes (batch/GPU scheduling) but carry substantial engineering cost — mature existing projects or scheduler configuration profiles are usually preferable to building one from scratch.
- Manual scheduling should be reserved for break-glass operational scenarios, never routine production placement, since it forfeits every scheduler safety check.

## 14. Related Concepts & What's Next

This section closes out the placement-mechanism tour that began with node/Pod affinity and taints/tolerations ([§68](./Section-68-Part9-Taints-Tolerations.md)) by showing what happens when the scheduler is bypassed or replaced outright. [§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md) turns to how the _default_ scheduler actually uses resource requests and limits during its filtering and scoring phases — the mechanism manual scheduling and custom schedulers both sidestep or must reimplement themselves.

**Next Section:** [§70](./Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md) — `Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md`
