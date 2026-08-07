# Section 35 (Part 5): Jobs: Run-to-Completion Workloads

## 1. Definition

**Plain language:** Not every workload is meant to run forever — a database migration, a batch report, a one-off data-processing task needs to run exactly until it finishes successfully, and then stop, with the system remembering whether it actually succeeded. A Job is the object built for exactly that "run until done, then stop" shape, which a Deployment fundamentally cannot express.

**Precise definition:** A **Job** is a controller that creates one or more Pods and ensures a specified number of them **terminate successfully** (exit code `0`), rather than running indefinitely. Unlike a Deployment's `restartPolicy: Always` assumption ([§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md)), a Job's Pod template must specify `restartPolicy: OnFailure` or `restartPolicy: Never`, since "the container is supposed to eventually exit" is the entire premise. A Job tracks **completions** (how many Pods must succeed in total), **parallelism** (how many Pods may run concurrently while working toward that count), and a **backoffLimit** (how many Pod failures are tolerated, with exponential backoff between retries, before the Job itself is marked `Failed`). Once the required number of successful completions is reached, the Job is marked `Complete` and no further Pods are created.

## 2. Why This Matters

- **A Deployment cannot express "run once and stop" without fighting its own reconciliation loop.** [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) established `restartPolicy: Always` as the default Pod assumption for long-running services; a Job is the object that formalizes the opposite assumption — the container is expected to exit, and that exit code determines whether the work is considered done or must be retried, not treated as a crash to restart forever.
- **`backoffLimit` and exponential backoff turn transient failures into a bounded, safe retry policy** instead of either giving up after one failure or retrying forever — this is precisely the operational gap a bare `kubectl run` one-off Pod leaves open, since a single Pod with no controller has no retry logic at all.
- **`completions` and `parallelism` together model real batch-processing patterns directly** — a fixed work queue processed by several worker Pods concurrently, or a precise number of sequential validation runs — without needing external orchestration tooling for the common case.

🔑 **Key Takeaway:** Use a Job whenever the workload's success is defined by "this ran to completion successfully N times," not "this should always be running" — the defining Pod-spec signal is `restartPolicy` being `OnFailure`/`Never` instead of `Always`, and the defining controller fields are `completions`, `parallelism`, and `backoffLimit`.

## 3. Prerequisites and Dependencies

Builds directly on [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) (Pod spec anatomy, specifically `restartPolicy` and its allowed values) and assumes familiarity with the general controller/reconciliation pattern from [§1](../Part1/Section-01-Part1-What-Kubernetes-Is-Container-Orchestration-Problem.md) and [§13](../Part2/Section-13-Part2-Controller-Manager-Controller-Pattern-Reconciliation-Loops.md).

## 4. Architecture Diagram

```text
                          Job "data-migration"
                 completions: 5   parallelism: 2   backoffLimit: 3
                                    │
                     tracks: succeeded Pod count vs. completions
                                    │
        ┌───────────────────────────┼────────────────────────────┐
        │                                                        │
   Pod #1 (running)                                       Pod #2 (running)
   restartPolicy: OnFailure                                restartPolicy: OnFailure
        │                                                        │
   exits 0 (success)                                     exits 1 (failure)
        │                                                        │
   succeeded: 1/5                                    retry Pod #2 created
        │                                             (backoff: 10s, 20s, 40s...)
        ▼                                                        │
   Pod #3 created (parallelism slot freed)             exits 0 eventually
        │                                                        │
        └───────────────────────────┬────────────────────────────┘
                                    ▼
                    ... repeats until succeeded == 5
                                    │
                                    ▼
                       Job status: Complete
                (no further Pods created; failed Pod
                 objects retained for log inspection
                 until manually cleaned up or TTL expires)
```

- **Failed Pods are not deleted automatically by default** — they remain visible via `kubectl get pods` for post-mortem log inspection, unless `ttlSecondsAfterFinished` is set on the Job to auto-clean up finished Job objects (and their Pods) after a delay.
- **`backoffLimit` counts Job-level retries, not per-Pod restarts** — each failed Pod counts against the limit; once exceeded, the Job transitions to `Failed` and stops creating new Pods entirely, requiring manual intervention.
- **`parallelism` bounds concurrency, not total work** — `completions` is the actual target; `parallelism` only controls how many Pods may be in flight at once while working toward that target.

## 5. Hands-On: Defining and Running Jobs

### 5.1 A Simple Single-Run Job

**Purpose:** The simplest Job shape — run one Pod to completion, retry on failure up to a bound.

```yaml
# db-migration-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: db-migration
spec:
  backoffLimit: 3
  activeDeadlineSeconds: 300
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: migrate
          image: myregistry/db-migrator:1.8
          command: ["./migrate.sh", "--target=latest"]
```

```bash
$ kubectl apply -f db-migration-job.yaml
job.batch/db-migration created

$ kubectl get jobs
NAME            COMPLETIONS   DURATION   AGE
db-migration    0/1           14s        14s

$ kubectl get pods -l job-name=db-migration
NAME                  READY   STATUS      RESTARTS   AGE
db-migration-9kvqz    0/1     Completed   0          22s

$ kubectl get jobs
NAME            COMPLETIONS   DURATION   AGE
db-migration    1/1           25s        30s

$ kubectl logs job/db-migration
Applying migration 0042_add_index... done
Applying migration 0043_backfill_column... done
Migration complete.
```

**Common errors:** Omitting `restartPolicy: OnFailure`/`Never` and leaving the Pod-level default (`Always`) causes the api-server to reject the Job manifest outright — a Job's Pod template is required to declare one of the two Job-compatible restart policies.

### 5.2 Parallel Jobs with Fixed Completion Count

**Purpose:** Process a fixed amount of batch work using multiple concurrent worker Pods — the standard "worker queue" Job pattern.

```yaml
# batch-worker-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: report-batch
spec:
  completions: 6
  parallelism: 3
  backoffLimit: 4
  template:
    spec:
      restartPolicy: OnFailure
      containers:
        - name: worker
          image: myregistry/report-worker:2.1
          command: ["./process-batch.sh"]
```

```bash
$ kubectl apply -f batch-worker-job.yaml
job.batch/report-batch created

$ kubectl get pods -l job-name=report-batch
NAME                  READY   STATUS      RESTARTS   AGE
report-batch-2f8kq    1/1     Running     0          5s
report-batch-6n3wp    1/1     Running     0          5s
report-batch-x9jdt    1/1     Running     0          5s

$ kubectl get jobs report-batch
NAME           COMPLETIONS   DURATION   AGE
report-batch   3/6           41s        41s
```

**Production usage example:** This is the standard shape for parallelizable batch work — image-thumbnail generation across a fixed set of files, or bulk record reprocessing — where `parallelism` is tuned to the resource budget available and `completions` matches the exact known unit of work.

**Common errors:** A worker image that isn't idempotent on retry (e.g., it doesn't tolerate reprocessing the same unit of work twice) can cause data corruption if a Pod is retried after partially completing work before failing — Job retries assume the work unit is safely re-runnable from scratch.

### 5.3 Bounding Job Runtime and Cleaning Up Finished Jobs

**Purpose:** Prevent a stuck Job from running indefinitely, and automatically clean up completed Job objects.

```yaml
# bounded-job.yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: nightly-cleanup
spec:
  activeDeadlineSeconds: 600
  ttlSecondsAfterFinished: 3600
  backoffLimit: 2
  template:
    spec:
      restartPolicy: Never
      containers:
        - name: cleanup
          image: myregistry/cleanup-tool:1.0
```

```bash
$ kubectl apply -f bounded-job.yaml
job.batch/nightly-cleanup created

$ kubectl get job nightly-cleanup -o jsonpath='{.status.conditions[*].type}'
Complete

# 1 hour later, the Job and its Pods are garbage-collected automatically
$ kubectl get job nightly-cleanup
Error from server (NotFound): jobs.batch "nightly-cleanup" not found
```

**Common errors:** `activeDeadlineSeconds` measures wall-clock time since the Job started, across all retries combined — if it's set too aggressively relative to `backoffLimit`'s retry/backoff timing, the Job can be killed for exceeding the deadline before it's genuinely had a fair chance to retry and succeed.

## 6. Production Usage Notes

- **`ttlSecondsAfterFinished` is worth setting on most batch Jobs** to avoid accumulating a long tail of completed Job objects (and their terminal Pods) cluttering `kubectl get jobs`/`get pods` output and consuming etcd storage indefinitely.
- **Non-idempotent workloads need explicit idempotency handling in application logic**, not just relying on Kubernetes — a retried Pod re-executes the entire container command from the start, so partial-completion side effects (partial writes, sent notifications) must be safe to repeat or explicitly guarded against.
- **CronJobs ([§36](./Section-36-Part5-CronJobs-Scheduled-Job-Execution.md)) are built directly on top of Jobs** — every scheduled run a CronJob triggers is, underneath, exactly the Job object covered in this section, created and retired on a schedule.

## 7. Security Considerations

- A Job's Pod template inherits the same SecurityContext, ServiceAccount, and image-pull considerations as any Pod ([§45](../Part6/Section-45-Part6-SecurityContext-Pod-Container-Level.md)) — batch/migration Jobs are frequently granted elevated database or infrastructure credentials, making their ServiceAccount scope and Secret usage a priority review target, not an afterthought because "it's just a one-off job."
- `activeDeadlineSeconds` doubles as a safety control against a runaway or hung Job consuming cluster resources indefinitely — omitting it on Jobs with untrusted or unpredictable workloads is a real operational risk, not just a tidiness concern.

## 8. Common Troubleshooting Scenarios

| Symptom                                                           | Likely Cause                                                       | Resolution Path                                                                               |
| ----------------------------------------------------------------- | ------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- |
| Job manifest rejected at `kubectl apply`                          | `restartPolicy` left as default `Always` in the Pod template       | Set `restartPolicy` to `OnFailure` or `Never` explicitly                                      |
| Job stuck retrying indefinitely, never `Complete` or `Failed`     | `backoffLimit` set very high or work unit genuinely never succeeds | Check Pod logs for the actual failure cause; lower `backoffLimit` for faster fail-fast signal |
| Job marked `Failed` before work seemingly finished                | `activeDeadlineSeconds` exceeded across all retries combined       | Increase the deadline, or investigate why individual attempts are taking longer than expected |
| Completed Job Pods accumulating and cluttering `kubectl get pods` | No `ttlSecondsAfterFinished` set                                   | Add `ttlSecondsAfterFinished` to newly created Jobs; manually clean up existing ones          |

## 9. Best Practices

- Always set `restartPolicy: OnFailure` deliberately (not `Never`) when retries are meaningful for the workload, reserving `Never` for cases where a failed Pod's logs should be preserved untouched for inspection rather than replaced by a fresh retry attempt.
- Set both `backoffLimit` and `activeDeadlineSeconds` intentionally rather than leaving defaults unexamined, so a broken Job fails fast and visibly instead of retrying silently for a long time.
- Design the work unit each Pod performs to be idempotent wherever possible, since Job semantics assume a retried Pod safely repeats the entire unit of work from scratch.

## 10. Common Anti-Patterns / Mistakes

- **Using a bare, unmanaged Pod (`kubectl run --restart=Never`) for batch work** instead of a Job, losing retry/backoff semantics and completion tracking entirely.
- **Writing worker containers that aren't safely re-runnable**, causing data corruption or duplicate side effects the first time a Job retry actually fires.
- **Leaving `ttlSecondsAfterFinished` unset on high-frequency Jobs**, allowing completed Job/Pod objects to accumulate indefinitely and degrade `kubectl get`/etcd performance over time.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a Job and a Deployment?"_
**Model answer:** A Deployment manages Pods that are meant to run indefinitely (`restartPolicy: Always`), restarting or replacing them forever to maintain a steady-state replica count. A Job manages Pods meant to run to completion and then stop — it requires `restartPolicy: OnFailure` or `Never`, tracks successful completions against a target, and marks itself `Complete` once that target is reached, creating no further Pods afterward.
_What the interviewer is probing for:_ Clear grasp of the fundamental "run forever" vs. "run until done" distinction driving the two object types.

**🎯 Intermediate:** _"Explain `completions`, `parallelism`, and `backoffLimit` and how they interact."_
**Model answer:** `completions` is the total number of Pods that must succeed for the Job to be considered done. `parallelism` caps how many Pods may be running concurrently while working toward that total — it controls concurrency, not the target itself. `backoffLimit` bounds how many Pod failures the Job tolerates in total (with exponential backoff between retries) before giving up and marking the whole Job `Failed`; it's a Job-level failure budget, not a per-Pod restart count.
_What the interviewer is probing for:_ Precise understanding of three fields that are easy to conflate, especially `parallelism` vs. `completions`.

**🎯 Senior:** _"A batch Job processing 20 units of work with `parallelism: 5` fails partway through with some units processed twice. What likely went wrong, and how do you fix it?"_
**Model answer:** This points to a non-idempotent worker: a Pod failure and subsequent retry re-executed a unit of work that had already partially or fully completed before failing, causing duplicate processing. The Job mechanism itself worked exactly as designed — retries are expected to re-run the entire Pod's command from scratch — so the actual fix is application-level: making each unit of work idempotent (e.g., checking for already-processed markers before acting, or using upserts instead of inserts) rather than trying to prevent Kubernetes from retrying at all, since removing retries would just trade duplicate-processing risk for unrecovered-failure risk.
_What the interviewer is probing for:_ Recognition that Job retry semantics are a feature, not a bug, and that safe retry behavior is the workload's responsibility to guarantee.

**🎯 Architect:** _"How would you design a large-scale batch processing pipeline using Jobs, balancing throughput, cost, and failure isolation?"_
**Model answer:** I'd split the total work into a `completions`/`parallelism` ratio tuned against both the cluster's available capacity and the cost of over-provisioning worker Pods that finish early and sit idle — usually keeping `parallelism` well below `completions` so a slow node or transient failure doesn't stall the entire batch. I'd set a `backoffLimit` and `activeDeadlineSeconds` tuned to the expected per-unit processing time so genuine failures surface quickly rather than retrying for hours, and I'd insist on idempotent work-unit design up front so retries are always safe. For very large or long-running batches I'd also consider whether the work should be partitioned across multiple smaller Jobs rather than one giant Job, both for failure-blast-radius reasons (one bad unit doesn't block unrelated units in a separate Job) and for clearer progress observability via `kubectl get jobs` per partition, plus `ttlSecondsAfterFinished` to keep the resulting object count manageable at scale.
_What the interviewer is probing for:_ Systems-level batch-pipeline design thinking, not just recitation of individual Job fields.

## 12. Common Misconceptions

1. **"A Job with a failing Pod just restarts it forever like a Deployment would."** Retries are bounded by `backoffLimit`; once exceeded, the Job is marked `Failed` and stops creating new Pods entirely.
2. **"`parallelism` is the total amount of work the Job will do."** `completions` is the actual target; `parallelism` only bounds how many Pods run concurrently while reaching it.
3. **"Job Pods and their logs disappear immediately once the Job completes."** They're retained by default for inspection unless `ttlSecondsAfterFinished` is configured to clean them up after a delay.
4. **"Any container that eventually exits should be run as a Job."** A container that's expected to run indefinitely but occasionally exits due to a crash still belongs in a Deployment with `restartPolicy: Always` — a Job is specifically for workloads whose success is defined by successful completion, not for long-running services that merely restart on crash.

## 13. 🔑 Key Takeaways

- A Job runs Pods to completion rather than indefinitely, requiring `restartPolicy: OnFailure` or `Never` instead of the Deployment-style `Always`.
- `completions`, `parallelism`, and `backoffLimit` together define how much work must succeed, how much concurrency is allowed, and how many failures are tolerated before giving up.
- Failed and completed Pods are retained by default for log inspection; `ttlSecondsAfterFinished` automates cleanup.
- `activeDeadlineSeconds` bounds total Job runtime across all retries combined, acting as a safety net against runaway or hung work.
- Job retry semantics assume the underlying work unit is idempotent — that responsibility belongs to the application, not Kubernetes.

## 14. Related Concepts & What's Next

[§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md)'s Pod spec anatomy, particularly `restartPolicy`, is the direct foundation this section built on to explain why Jobs require a different restart contract than ordinary workloads. [§36](./Section-36-Part5-CronJobs-Scheduled-Job-Execution.md) builds immediately on top of everything covered here: a CronJob is, mechanically, a controller that creates Job objects (exactly as defined in this section) on a recurring schedule.

**Next Section:** [§36](./Section-36-Part5-CronJobs-Scheduled-Job-Execution.md) — `Section-36-Part5-CronJobs-Scheduled-Job-Execution.md`
