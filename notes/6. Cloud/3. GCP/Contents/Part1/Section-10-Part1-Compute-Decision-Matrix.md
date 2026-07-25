# Section 10 (Part 1): Compute Decision Matrix & Part 1 Wrap-Up

## 10.1 Definition

**Plain language:** This section doesn't introduce a new service — it steps back and puts every compute option covered so far (plus GKE and Cloud Batch) side by side, so choosing between them becomes a structured decision rather than a guess. It closes out Part 1 with a comprehensive interview drill covering everything from Section 1 through Section 9.

**Precise:** This is the Part 1 synthesis section: a consolidated decision matrix across GCP's compute execution models — Compute Engine, App Engine, Cloud Run, Cloud Functions, GKE, and Cloud Batch — evaluated along the axes that actually drive real-world architecture decisions (control vs. convenience, cold-start behavior, scaling model, pricing model, and ideal use case), followed by a Part 1 comprehensive interview drill and the transition into Part 2.

## 10.2 Why It Exists / Problem It Solves

Each individual compute section (2, 6, 7, 8, 9, and the forward-referenced 30) explains one service in isolation, but the real skill an architect or interviewer is testing for is: given a workload's actual requirements, which compute service is the right fit, and why not the others? Without a single consolidated comparison, that judgment has to be reconstructed from six separate sections every time the question comes up. This section exists to make that judgment call reusable — one table, one mental model, applicable to nearly any "which compute service should I use for X" question.

## 10.3 The Control-vs-Convenience Spectrum

Every GCP compute option sits somewhere on a single spectrum: the more control you take over the underlying infrastructure, the more operational responsibility you accept — and the more convenience a service offers, the less control you retain over exactly how your workload runs.

```
MORE CONTROL ─────────────────────────────────────────────► MORE CONVENIENCE

Compute Engine    GKE          App Engine       Cloud Run      Cloud Functions
(full VM,        (full         Standard        (containers,    (single function,
 you patch OS,    Kubernetes,  (managed         scale-to-zero,  no container,
 you scale)       you manage   runtime,         no cluster)     narrowest scope)
                  the cluster) auto-scaling)

                              Cloud Batch sits alongside this spectrum, not on it —
                              it isn't a "keep something running" model at all;
                              it's a "run this to completion, then disappear" model.
```

## 10.4 Full Compute Decision Matrix

| Aspect                  | Compute Engine (§2)                                                                          | App Engine (§6)                                                                                                    | Cloud Run (§7)                                                                            | Cloud Functions (§8)                                        | GKE (§30, preview)                                                              | Cloud Batch (§9)                                                                          |
| ----------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Control vs. convenience | Maximum control — you manage the OS, patching, scaling                                       | High convenience — managed runtime, minimal ops (Standard env)                                                     | High convenience — no cluster, just a container                                           | Highest convenience — no container, just a function         | Maximum control among managed options — full Kubernetes API surface             | High convenience — no VM lifecycle management at all                                      |
| Cold start              | N/A — instances persist unless explicitly stopped                                            | Standard: brief; Flexible: none (always-on)                                                                        | Configurable — scale-to-zero incurs cold start; `--min-instances` avoids it               | Present unless minimum instances configured                 | N/A for running pods; node-level scaling has its own latency                    | N/A — jobs are provisioned fresh per run by design                                        |
| Scaling model           | Manual or Managed Instance Group autoscaling                                                 | Automatic, request-based (Standard); manual/auto (Flexible)                                                        | Automatic, concurrent-request-based, including to zero                                    | Automatic, per-invocation, including to zero                | Horizontal Pod Autoscaler + Cluster Autoscaler — most granular, most complex    | Task-parallelism based — scales to the job's task count, then to zero                     |
| Pricing model           | Per-second billing for running instances, sustained-use discounts                            | Standard: per-request/instance-hour; Flexible: per-instance-hour                                                   | Per-request/CPU-second while handling traffic, scale-to-zero when idle                    | Per-invocation + execution time, scale-to-zero when idle    | Per-node compute cost (control plane free on Autopilot's underlying nodes vary) | Per-second billing on provisioned VMs, only for job duration; Spot VM discounts available |
| Ideal use case          | Custom OS/kernel needs, licensing constraints, lift-and-shift, persistent stateful workloads | Simple web apps wanting zero infra management (Standard) or legacy containerized apps needing always-on (Flexible) | Stateless containerized services and event-driven jobs needing full container flexibility | Small, single-purpose event reactions with minimal ceremony | Complex multi-service architectures needing fine-grained orchestration control  | Bulk run-to-completion workloads — rendering, simulation, scripted batch processing       |

> 💡 **Tip:** When faced with an unfamiliar "which compute service" question, first ask two things: (1) Is this a long-running service responding to requests, or a one-shot/batch task? (2) How much of the underlying runtime does the workload need to control (custom OS, custom kernel modules, arbitrary long-lived processes) versus how much can be abstracted away? Those two questions alone eliminate most of the six options immediately.

## 10.5 Decision Flow

```
                    New workload — which compute service?
                                    │
                 ┌──────────────────┴──────────────────┐
                 ▼                                     ▼
        Run-to-completion,                      Long-running / request-serving
        bulk/batch task?                                  │
                 │                          ┌─────────────┴───────────────┐
                YES                         ▼                             ▼
                 │                  Single event-triggered          Full application
                 ▼                  handler, minimal logic?         or multi-service system?
         Data-aware pipeline               │                                │
         (ETL/joins/streaming)?           YES                              NO ► keep going
              │        │                   │                                │
             YES       NO                  ▼                    Needs custom OS/kernel/
              │        │            Cloud Functions (§8)         licensing/persistent state?
              ▼        ▼                                              │
     Dataflow/     Cloud Batch                              YES ──────┴────── NO
     Dataproc      (§9)                                      │                 │
     (§45)                                                   ▼                 ▼
                                                       Compute Engine    Needs arbitrary container
                                                       (§2)              flexibility, no cluster mgmt?
                                                                              │
                                                                    YES ──────┴────── NO
                                                                     │                 │
                                                                     ▼                 ▼
                                                              Cloud Run (§7)   Needs full Kubernetes
                                                                               orchestration control?
                                                                               ► GKE (§30)
```

## 10.6 Production & Enterprise Usage

- **Layered adoption in real organizations:** Most enterprises running on GCP use several of these services simultaneously — Compute Engine for legacy/lift-and-shift workloads, Cloud Run for new stateless services, Cloud Functions for lightweight event glue, GKE for complex platform-team-owned systems, and Cloud Batch for periodic bulk-processing jobs — rather than standardizing on a single compute model.
- **Migration trajectories:** A common enterprise pattern is a gradual migration from Compute Engine (initial lift-and-shift) toward Cloud Run or GKE as applications are modernized, since Compute Engine's operational burden (patching, scaling configuration, OS management) is the highest of the six options.
- **Cost governance:** FinOps teams commonly review compute spend service-by-service, since the pricing models differ enough (always-on instance-hours vs. per-request billing vs. per-task-second billing) that the same workload can have a very different cost profile depending on which service runs it.

## 10.7 Common Misconceptions

- **Misconception:** "The most 'serverless' option is always the best choice." Convenience trades away control — a workload needing custom kernel modules, specific licensing, or persistent local state genuinely cannot run on Cloud Functions or Cloud Run regardless of how attractive the operational simplicity looks; matching the workload's actual requirements to the right point on the spectrum matters more than defaulting to the most abstracted option.
- **Misconception:** "GKE is just a more complicated version of Cloud Run." GKE and Cloud Run solve different problems — Cloud Run is a serverless container-execution model with an opinionated request/job structure, while GKE exposes the full Kubernetes API surface (custom controllers, StatefulSets, DaemonSets, arbitrary networking policies) for workloads whose orchestration needs genuinely exceed what Cloud Run's simpler model supports.

## 10.8 Part 1 Comprehensive Interview Drill

**🟢 What's the fundamental trade-off across all of GCP's compute options?**
Control versus convenience: the more a service manages on your behalf (patching, scaling, cluster operations), the less direct control you retain over exactly how the workload runs. Compute Engine sits at maximum control; Cloud Functions sits at maximum convenience; App Engine, Cloud Run, and GKE occupy points in between, with Cloud Batch off to the side as a purpose-built run-to-completion model rather than a "keep something running" model.

**🟢 A team needs to run a Python script against 5,000 input files, once, tonight, then never again until next month. Which compute service, and why?**
Cloud Batch (Section 9) — it's a run-to-completion, bulk-parallel workload with no ongoing serving requirement. Provisioning a persistent Compute Engine fleet or a Cloud Run service for a workload that runs once a month would leave infrastructure decisions (sizing, cleanup) to be managed by hand; Cloud Batch handles provisioning, parallel task distribution, retries, and teardown natively.

**🟡 Why might a 2nd-gen Cloud Function and a Cloud Run service end up being functionally almost identical under the hood, and when would you still pick the function?**
2nd-gen Cloud Functions are literally deployed on top of Cloud Run and Eventarc (Section 8.3), so the runtime behavior converges. The reason to still pick Cloud Functions is deployment ergonomics: for a small, single-purpose handler with minimal dependencies, deploying source directly (no Dockerfile) is less ceremony than building and pushing a container image, even though Cloud Run could do the same job.

**🟡 What's the risk of choosing Cloud Functions/Cloud Run's scale-to-zero for a latency-sensitive production API, and how is it mitigated?**
Scale-to-zero introduces a cold start on the first request after an idle period, which can violate a strict latency SLA. It's mitigated by configuring a minimum instance count above zero, which keeps warm capacity ready at the cost of paying for that capacity continuously — a configurable trade-off between latency and idle-cost, not an unavoidable constraint of serverless compute.

**🟡 An architect proposes running a data ETL join-and-aggregate job as a Cloud Batch job "since it's just batch work." What's the concern?**
Cloud Batch has no data-aware primitives — no windowing, joins, or distributed shuffle logic. A genuine data-processing pipeline belongs on Dataflow or Dataproc (Section 45), which provide a purpose-built execution engine for exactly that kind of work; using Cloud Batch would mean re-implementing data-processing infrastructure that already exists elsewhere in GCP.

**🔴 Walk through choosing a compute service for a growing startup: an MVP web app today, expected to scale to a complex multi-service platform within two years.**
Start with the highest-convenience option that fits the MVP's actual needs — likely Cloud Run for a containerized app (or App Engine Standard if it's a simple web app in a supported language with no custom container requirements) — since minimizing operational overhead early matters more than anticipating future orchestration needs prematurely. As the system decomposes into multiple services with more complex inter-service networking, scaling, and deployment coordination needs, evaluate GKE only once those needs are concrete rather than speculative, since GKE's operational overhead (cluster upgrades, node pools) is only worth taking on when Cloud Run's simpler service/job model genuinely can't express what's needed. Compute Engine only re-enters the picture if a specific component needs custom OS-level control the managed options can't provide; Cloud Batch only enters if a genuine bulk/batch processing need emerges (e.g., nightly reporting) alongside the serving workload.

**🔴 How would you explain, in one paragraph, why GCP offers six different compute execution models instead of just one flexible one?**
Because "flexible enough for every case" and "convenient enough to require no thought" are in direct tension — a single model would either force every simple workload to carry unnecessary operational overhead (if optimized for maximum control) or make certain legitimate workloads impossible to run (if optimized for maximum convenience). Offering a spectrum — Compute Engine, App Engine, Cloud Run, Cloud Functions, GKE, and the separately-shaped Cloud Batch — lets each workload's actual requirements (state, custom runtime needs, request-driven vs. batch shape, team's orchestration appetite) determine which point on that spectrum fits, rather than forcing every workload through one compromise model.

## 10.9 Key Takeaways

- 🔑 Every GCP compute option sits on a control-vs-convenience spectrum: Compute Engine (maximum control) → GKE → App Engine → Cloud Run → Cloud Functions (maximum convenience), with Cloud Batch as a separate run-to-completion model.
- 🔑 The two fastest questions to narrow the field: is this request-serving or run-to-completion, and how much runtime control does it actually need?
- 🔑 Cold starts, scaling model, and pricing model differ meaningfully across all six services — matching them to a workload's real traffic pattern (steady vs. bursty vs. batch) drives both cost and latency outcomes.
- 🔑 Cloud Batch is for compute-bound "run this program N times" work; Dataflow/Dataproc (Section 45) are for genuine data-aware pipelines — conflating the two means reimplementing infrastructure that already exists.
- 🔑 Real organizations run several of these services simultaneously rather than standardizing on one; the skill being tested is matching workload to service, not picking a single "best" option.

## 10.10 Related Concepts

Compute Engine (Section 2), App Engine (Section 6), Cloud Run (Section 7), Cloud Functions (Section 8), Cloud Batch (Section 9) all feed into this synthesis; GKE (Section 30) and Dataflow/Dataproc (Section 45) are forward-referenced as the remaining pieces of the full compute and data-processing picture, completed later in this knowledge base.

---

## ✅ Part 1 Complete

All 10 sections of **GCP Foundations & Compute** are done — from what GCP is and how it evolved, through global infrastructure, resource hierarchy, and tooling, to every major compute execution model and the decision framework for choosing between them. Next: **Part 2 — Storage & Databases** (Section 11: Cloud Storage, Section 12: Persistent Disks & Filestore, Section 13: Cloud SQL, Section 14: Cloud Spanner, Section 15: Firestore/Datastore, Section 16: Bigtable, Section 17: Memorystore, Section 18: Storage/Database Decision Matrix), where the same control-vs-convenience judgment developed here for compute gets applied to choosing how and where data actually lives.
