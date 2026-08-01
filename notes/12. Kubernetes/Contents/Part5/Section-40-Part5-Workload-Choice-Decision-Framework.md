# Section 40 (Part 5): Workload Choice Decision Framework (Deployment vs. StatefulSet vs. DaemonSet vs. Job vs. CronJob)

## 1. Definition

**Plain language:** Part 5 has now introduced every major workload controller Kubernetes offers, plus the autoscaling and disruption mechanisms that layer on top of them. In practice, the first real decision on any new application isn't "how do I scale this" or "how do I protect it during maintenance" — it's simply "which controller do I even use to run this in the first place?" Picking wrong doesn't usually cause an immediate failure; it causes a slow accumulation of workarounds as a team fights the wrong object's assumptions for months.

**Precise definition:** Kubernetes provides five core workload controllers, each built around a distinct assumption about **identity**, **completion semantics**, and **placement**: **Deployment** (§28) assumes interchangeable, stateless replicas with no individual identity, run indefinitely; **StatefulSet** (§33) assumes each replica needs a **stable, sticky identity** (network name, ordinal index, and often dedicated per-replica storage) and ordered lifecycle operations; **DaemonSet** (§34) assumes exactly **one Pod per matching node** with no replica count to declare at all — placement is driven by cluster topology, not a desired count; **Job** (§35) assumes a **run-to-completion** workload where success is defined by the container(s) exiting `0`, not by staying running; and **CronJob** (§36) is a Job template invoked on a **recurring schedule**. Choosing among them is a matter of matching the workload's actual identity, completion, and placement requirements to the controller built for exactly that combination — not a matter of feature-richness or personal preference.

## 2. Why This Matters

- **Using the wrong controller doesn't fail loudly — it fails as accumulating operational friction.** Running a workload that actually needs stable per-replica identity (session-sticky caches, clustered databases) on a plain Deployment (§27/§28) works fine in a demo and quietly breaks the moment a Pod is rescheduled and loses its old identity/storage association — exactly the gap StatefulSet (§33) closes.
- **The five controllers are not layered in sophistication — they're orthogonal to different problems.** DaemonSet (§34) isn't "a simpler Deployment"; it solves a placement problem (one-per-node) that Deployment's replica-count model cannot express at all, no matter how it's tuned. Recognizing which axis (identity, completion, placement) a requirement actually falls on is the entire skill this section builds.
- **This decision compounds with everything else in Part 5** — the autoscaling mechanism that fits (§37 HPA fits Deployments and StatefulSets naturally; DaemonSets have no meaningful replica count to scale; Jobs/CronJobs are typically scaled by parallelism, not HPA) and disruption protection (§39 PDBs) both depend on having chosen the right base controller first.

🔑 **Key Takeaway:** Deployment, StatefulSet, DaemonSet, Job, and CronJob each encode a different, non-overlapping assumption about identity, completion semantics, and placement — the right choice is found by identifying which of those three axes the workload's actual requirement sits on, not by ranking the controllers from simple to advanced.

## 3. Prerequisites and Dependencies

Synthesizes §27/§28 (ReplicaSet/Deployment), §33 (StatefulSet), §34 (DaemonSet), §35/§36 (Job/CronJob), §37 (HPA), §38 (VPA/Cluster Autoscaler), and §39 (PodDisruptionBudgets) — every workload and scaling/disruption concept introduced across Part 5.

## 4. Architecture Diagram: The Decision Flow

```text
                          Start: "What kind of workload is this?"
                                        │
                    ┌───────────────────┼────────────────────────┐
                    ▼                   ▼                        ▼
       "Runs indefinitely,   "Runs to completion,      "Must run on every
        never 'finishes'"     then stops"                (or every matching)
                    │                   │                  node, one copy each"
                    ▼                   ▼                        ▼
       Does each replica need    Does it need to run         ┌─────────────────┐
       a STABLE IDENTITY          on a SCHEDULE, or          │  DaemonSet §34  │
       (name/storage tied         just once/on demand?       │  (log/metrics   │
       to ordinal, survives                                  │  agents, CNI,   │
       rescheduling)?                 │             │        │  node monitors) │
        │             │               ▼             ▼        └─────────────────┘
        ▼             ▼           Once/on-demand  Recurring
       YES            NO              │             │
        │             │               ▼             ▼
        ▼             ▼          ┌────────────┐ ┌─────────────┐
┌────────────────┐ ┌──────────┐  │ Job §35    │ │ CronJob §36 │
│ StatefulSet §33│ │Deployment│  │ (batch,    │ │ (scheduled  │
│ (DBs, brokers, │ │   §28    │  │ migrations,│ │  backups,   │
│ clustered      │ │(stateless│  │ one-off    │ │  reports)   │
│ caches)        │ │   web/   │  │ processing)│ │             │
└────────────────┘ │API tiers)|  └────────────┘ └─────────────┘
                   └──────────┘

Layered on top of whichever base controller is chosen:
  HPA (§37)   → fits Deployment & StatefulSet naturally; rarely meaningful on DaemonSet
                (no replica count to scale) or Job/CronJob (parallelism, not HPA, controls concurrency)
  VPA (§38)   → applicable to any controller's Pod template, same disruption caveats apply
  PDB (§39)   → meaningful for Deployment/StatefulSet/DaemonSet (ongoing availability);
                not applicable to Job/CronJob (no "availability" concept for a completed Pod)
```

- **The three questions in order — identity, then completion, then placement — resolve the large majority of real workload-choice decisions** without needing to consult a longer feature checklist; most genuine ambiguity in practice is between Deployment and StatefulSet, specifically around whether "identity" is really required or just habitually assumed.
- **DaemonSet is the one controller with no `replicas` field at all** — its Pod count is entirely a function of matching node count, which is precisely why it sits outside the HPA/replica-count conversation entirely.

## 5. Hands-On: Applying the Framework to Real Scenarios

### 5.1 Working Through a Genuine Deployment-vs-StatefulSet Ambiguity

**Purpose:** Show the reasoning process on the single most common point of real confusion — a Redis cache cluster.

**Syntax:** No new command syntax — this is a reasoning exercise using the decision flow above.

```text
Scenario: "3-node Redis cluster, each node needs to know its peers,
           and losing a node's data on reschedule is unacceptable."

Question 1 (identity): Does each replica need a stable identity?
  → YES: each Redis node needs a predictable hostname (redis-0, redis-1,
    redis-2) that peers can address, and each node's data volume must
    follow that specific ordinal if it's rescheduled — a Deployment's
    Pods get random hashes and no persistent per-replica identity link.

Decision: StatefulSet (§33), using volumeClaimTemplates so redis-0
always reattaches to the same PersistentVolumeClaim, and a headless
Service providing the stable DNS names (redis-0.redis, redis-1.redis, ...).
```

```bash
$ kubectl get statefulset redis
NAME    READY   AGE
redis   3/3     10m

$ kubectl get pods -l app=redis -o wide
NAME      READY   STATUS    NODE
redis-0   1/1     Running   node-a
redis-1   1/1     Running   node-b
redis-2   1/1     Running   node-c
```

**Production usage example:** Teams that mistakenly run a clustered stateful workload on a Deployment typically discover the gap only during an incident — a rescheduled Pod comes up with a fresh, empty PersistentVolumeClaim and no stable name, breaking cluster membership at exactly the moment resilience mattered most.

### 5.2 Working Through a Job-vs-Deployment Ambiguity

**Purpose:** Distinguish "restarts because it crashed" from "restarts because it's designed to always be running."

```text
Scenario: "A container runs a one-time database schema migration,
           then exits 0 when done."

Question 1 (identity): No stable identity needed — rules out StatefulSet.
Question 2 (completion): Does it run to completion and stop, or run forever?
  → RUNS TO COMPLETION: success is "exited 0," not "still running."
    A Deployment would treat that clean exit as a crash and restart it
    indefinitely (subject to its restart policy), which is exactly wrong
    for a migration that must run exactly once (or a bounded retry count).

Decision: Job (§35), with backoffLimit bounding retries on genuine failure.
```

```bash
$ kubectl get job schema-migration
NAME                COMPLETIONS   DURATION   AGE
schema-migration    1/1           14s        1m
```

**Common errors:** Running a run-to-completion task as a Deployment is the most common miscategorization in this framework — the telltale symptom is a Pod stuck in an endless `Completed → CrashLoopBackOff`-adjacent restart cycle, because the Deployment's controller interprets the container's successful exit as something to restart rather than a finished task.

### 5.3 Working Through a DaemonSet-vs-Deployment Ambiguity

**Purpose:** Recognize a placement-driven requirement that no replica count can express.

```text
Scenario: "Every node needs a log-shipping agent running locally,
           reading that node's container logs from disk."

Question 1 (identity): Not relevant — no stable per-replica identity needed.
Question 2 (completion): Runs indefinitely — rules out Job/CronJob.
Question 3 (placement): Must it run on every node specifically,
  regardless of how many nodes exist or when they join/leave?
  → YES: a Deployment's replica count would need constant manual
    adjustment to match node count, and provides no guarantee that
    Pods land one-per-node rather than clustering on a subset.

Decision: DaemonSet (§34) — Pod count is automatically tied to node
count, including nodes that join later.
```

**Production usage example:** DaemonSets are the standard pattern for CNI plugins, node-level monitoring agents, and log shippers precisely because "one instance per node, automatically adjusting as nodes are added or removed" is a placement guarantee no `replicas` value on a Deployment can express, regardless of how it's tuned.

## 6. Production Usage Notes

- **The Deployment-vs-StatefulSet line is blurrier in practice than the diagram suggests for workloads with soft, not hard, identity needs** — some teams run lightly-stateful caches on Deployments with external, shared storage precisely to avoid StatefulSet's operational overhead (ordered rollout, per-replica PVCs) when true per-replica identity isn't actually required; the deciding question is always "does losing this replica's specific identity/data break correctness," not "does this workload happen to have some state."
- **CronJob's schedule is evaluated in the kube-controller-manager's timezone-aware `schedule` field (post-v1.24-ish clusters)** — teams migrating older CronJobs should verify whether an implicit UTC assumption is baked into existing schedules before relying on the newer explicit timezone field.
- **HPA (§37) on a Job or CronJob is a category error, not merely uncommon** — Jobs express concurrency through `parallelism`/`completions`, an entirely different mechanism than HPA's continuous replica-count reconciliation against a live metric, since a Job's Pods are expected to eventually all reach `Completed`, not stay running indefinitely at a target count.

## 7. Security Considerations

- DaemonSets frequently run with elevated privileges (hostPath mounts, `hostNetwork`, or privileged SecurityContexts) because their job is often node-level introspection — this makes DaemonSet manifests a disproportionately high-value target for security review relative to their small size, and Pod Security Admission (§80, Part 10) policy should treat DaemonSet namespaces as a distinct, more carefully reviewed tier.
- Jobs and CronJobs that pull and run images on a schedule (e.g., a nightly backup Job) are a common vector for stale, unpatched image drift if the image tag isn't pinned and periodically reviewed — a scheduled workload that "just works" for months can silently be running an image with known, unpatched CVEs the whole time.

## 8. Common Troubleshooting Scenarios

| Symptom                                                        | Likely Cause                                                                     | Resolution Path                                                                  |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Rescheduled replica loses data/identity peers can't rejoin     | Stateful workload running on a Deployment instead of a StatefulSet               | Migrate to StatefulSet (§33) with volumeClaimTemplates and a headless Service    |
| Run-to-completion task restarts endlessly instead of finishing | Task running as a Deployment/bare Pod instead of a Job                           | Migrate to Job (§35) with an appropriate `backoffLimit` and restart policy       |
| A node-level agent is missing on newly-added nodes             | Agent deployed as a Deployment with a fixed replica count instead of a DaemonSet | Migrate to DaemonSet (§34) so Pod count tracks node count automatically          |
| HPA applied to a Job/CronJob has no visible effect             | HPA is a category error for run-to-completion workloads                          | Use `parallelism`/`completions` on the Job spec instead; HPA does not apply here |

## 9. Best Practices

- Run the three-question framework (identity → completion → placement) explicitly during design review for every new workload rather than defaulting to Deployment out of habit — Deployment is the most common controller but not a safe universal default.
- Reassess an existing workload's controller choice when its actual requirements change — a Deployment that quietly grew a real identity requirement (e.g., through ad hoc per-Pod configuration) is a signal to migrate to StatefulSet before an incident forces the issue.
- Document _why_ a non-obvious controller choice was made (e.g., "DaemonSet, not Deployment, because this must run per-node") directly in the manifest or adjacent documentation, since the reasoning is rarely self-evident to the next engineer months later.

## 10. Common Anti-Patterns / Mistakes

- **Defaulting every workload to Deployment regardless of actual identity or completion requirements**, discovering the mismatch only during an incident involving rescheduling, data loss, or endless restart loops.
- **Treating DaemonSet as "a Deployment with extra steps" rather than recognizing it solves a placement problem Deployment's replica-count model cannot express at all.**
- **Applying HPA to Job/CronJob workloads**, or expecting PodDisruptionBudgets (§39) to mean anything for a completed Job Pod — both are category errors stemming from treating all five controllers as points on a single spectrum rather than orthogonal tools.

## 11. Interview Questions

**🎯 Beginner:** _"How do you decide between a Deployment and a Job for a new workload?"_
**Model answer:** The deciding question is whether the workload is meant to run indefinitely or run to completion and stop. A Deployment expects its Pods to keep running — a container exiting is treated as something to restart. A Job expects its Pod(s) to eventually exit `0` as the definition of success, and stops managing them once that happens (subject to `completions`/`backoffLimit`). Using a Deployment for a one-time task causes it to restart the task endlessly since a clean exit looks like a crash to a Deployment's controller.
_What the interviewer is probing for:_ Correct grasp of the completion-semantics axis, the most common real miscategorization.

**🎯 Intermediate:** _"A team is running a clustered message broker (3 nodes, each needs a stable peer address) on a Deployment with a shared PersistentVolumeClaim. What's wrong, and what should it be?"_
**Model answer:** A Deployment's Pods have no stable identity — names are randomly suffixed and any Pod can be rescheduled to any node with a fresh identity, and a single shared PVC across all replicas typically can't be safely written by multiple broker instances simultaneously without corruption (most storage access modes don't support concurrent read-write from many Pods safely for this use case). This workload actually needs StatefulSet: each broker replica gets a stable, ordinal-based name and DNS entry (via a headless Service) that peers can address consistently even after rescheduling, and `volumeClaimTemplates` give each replica its own dedicated PVC that follows that specific ordinal, not a shared one.
_What the interviewer is probing for:_ Ability to recognize a real identity requirement being worked around with a mismatched controller, and to name the specific StatefulSet mechanisms (headless Service, volumeClaimTemplates) that solve it.

**🎯 Senior:** _"Why doesn't it make sense to apply a Horizontal Pod Autoscaler to a DaemonSet, and how would you actually scale DaemonSet-style workloads?"_
**Model answer:** HPA's entire model is adjusting a `replicas` field toward a target based on a metric — but a DaemonSet has no `replicas` field at all; its Pod count is a direct, automatic function of how many nodes currently match its node selector/affinity rules, not a value anyone declares or an autoscaler could sensibly override. "Scaling" a DaemonSet-style workload really means changing the node count itself (Cluster Autoscaler, §38) or adjusting the DaemonSet's node-selection criteria to cover more or fewer nodes — the underlying capacity question is answered at the node-fleet level, not at the per-workload replica level, which is why HPA simply has no meaningful role here.
_What the interviewer is probing for:_ Precise understanding of why DaemonSet sits outside the replica-count autoscaling conversation entirely, not just that "HPA doesn't apply."

**🎯 Architect:** _"Design a workload-classification policy for a platform team that reviews every new service request before it's onboarded, ensuring the right controller is chosen up front."_
**Model answer:** I'd formalize the three-question framework as a mandatory onboarding checklist rather than leaving it to individual engineer judgment: does this workload require per-replica stable identity or dedicated per-replica storage (route to StatefulSet, §33, with an explicit note on quorum/replica-count rationale); does it run to completion rather than indefinitely, and if so, is it scheduled or on-demand (route to Job or CronJob, §35/§36, with backoffLimit and concurrency policy reviewed); does it need exactly one instance per node regardless of fleet size (route to DaemonSet, §34, flagged for extra security review given its typical elevated privileges); otherwise it defaults to Deployment (§28). I'd pair that classification with a corresponding autoscaling/disruption checklist — Deployment/StatefulSet workloads get an HPA suitability review (§37) and a mandatory PodDisruptionBudget (§39) above a criticality threshold; DaemonSets get a Cluster-Autoscaler-awareness note instead of HPA; Job/CronJob workloads get an explicit statement that HPA and PDB don't apply and that concurrency is governed by `parallelism`/`completions`/`concurrencyPolicy` instead. The goal is making the classification decision a five-minute, front-loaded design conversation instead of a multi-month accumulation of workarounds discovered during an incident.
_What the interviewer is probing for:_ Ability to operationalize the workload-choice framework as an actual governance process for a platform team, not just apply it ad hoc to one workload at a time.

## 12. Common Misconceptions

1. **"The five controllers form a difficulty ladder from simple (Deployment) to advanced (StatefulSet)."** They solve orthogonal problems on different axes (identity, completion, placement) — StatefulSet isn't "harder Deployment," it's the answer to a requirement Deployment cannot express at all.
2. **"Any stateful-looking workload needs a StatefulSet."** Some lightly-stateful workloads (e.g., a cache backed by shared external storage with no per-replica identity requirement) are correctly run on a Deployment — the deciding factor is whether losing a specific replica's identity/data breaks correctness, not merely whether the workload has state.
3. **"DaemonSet is just a Deployment with `replicas` set automatically."** DaemonSet has no `replicas` field at all — its Pod count is structurally tied to matching node count, a placement guarantee no replica-count-based controller can express regardless of tuning.
4. **"HPA and PodDisruptionBudgets are relevant to every workload controller equally."** HPA fits Deployment/StatefulSet naturally but is a category error for Job/CronJob (which use `parallelism`/`completions`) and largely irrelevant to DaemonSet (no replica count); PDBs are meaningful for ongoing-availability controllers but not for completed Job Pods.

## 13. 🔑 Key Takeaways

- Deployment, StatefulSet, DaemonSet, Job, and CronJob each answer a different question — identity (StatefulSet), completion semantics (Job/CronJob), or placement (DaemonSet) — rather than ranking from basic to advanced.
- The fastest triage sequence is: does it need stable per-replica identity (→ StatefulSet, §33)? Does it run to completion (→ Job/CronJob, §35/§36)? Must it run one-per-node (→ DaemonSet, §34)? Otherwise, Deployment (§28).
- HPA (§37) fits Deployment and StatefulSet naturally, is a category error for Job/CronJob, and is largely inapplicable to DaemonSet, which has no `replicas` field to scale.
- PodDisruptionBudgets (§39) matter for controllers with an ongoing-availability concept (Deployment, StatefulSet, DaemonSet) but have no meaning for a Job/CronJob's already-completed Pods.
- Mismatched controller choices rarely fail immediately — they surface later as data loss on reschedule, endless restart loops, or missing per-node coverage, making this decision worth making deliberately at design time rather than defaulting to Deployment out of habit.

## 14. Related Concepts & What's Next

This section closes Part 5 by synthesizing §27/§28 (Deployment), §33 (StatefulSet), §34 (DaemonSet), §35/§36 (Job/CronJob), §37 (HPA), §38 (VPA/Cluster Autoscaler), and §39 (PodDisruptionBudgets) into a single decision framework. Part 6 shifts focus from workload identity to application configuration and environment — starting with ConfigMaps, the mechanism for injecting non-secret configuration data into any of the workload types this section just covered.

**Next Section:** §41 — `Section-41-Part6-ConfigMaps-Creation-Consumption.md`
