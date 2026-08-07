# Section 36 (Part 5): CronJobs: Scheduled Job Execution

## 1. Definition

**Plain language:** A lot of batch work isn't triggered on demand — it needs to happen on a recurring schedule: a nightly backup, an hourly report, a weekly cleanup pass. A CronJob is the object that takes the "run to completion" Job pattern and adds the missing piece: a schedule that fires it automatically, over and over, using familiar cron syntax.

**Precise definition:** A **CronJob** is a controller that creates a new **Job** ([§35](./Section-35-Part5-Jobs-Run-To-Completion-Workloads.md)) at each tick of a schedule expressed in standard **cron syntax** (`minute hour day-of-month month day-of-week`), evaluated in the timezone configured on the CronJob (or the kube-controller-manager's default, historically UTC, unless `spec.timeZone` is set explicitly). Each scheduled firing produces an entirely new Job object — and therefore new Pods — following exactly the completions/parallelism/backoffLimit mechanics already covered in [§35](./Section-35-Part5-Jobs-Run-To-Completion-Workloads.md); the CronJob itself owns and tracks these generated Jobs, retaining a bounded history of both successful and failed ones via `successfulJobsHistoryLimit`/`failedJobsHistoryLimit`. A **concurrencyPolicy** governs what happens if a previous scheduled run is still in progress when the next scheduled time arrives, and **`startingDeadlineSeconds`** bounds how late a missed schedule tick may still be started before Kubernetes gives up on that particular firing.

## 2. Why This Matters

- **Everything about Job semantics from [§35](./Section-35-Part5-Jobs-Run-To-Completion-Workloads.md) applies unchanged to each individual run** — a CronJob doesn't reinvent retry, completion tracking, or parallelism; it's purely the scheduling layer sitting on top of the exact same Job object, which is why understanding [§35](./Section-35-Part5-Jobs-Run-To-Completion-Workloads.md) thoroughly first is what actually makes CronJob behavior predictable rather than mysterious.
- **`concurrencyPolicy` is the single most consequential and most commonly misconfigured field**, because the default (`Allow`) lets overlapping runs pile up if a job occasionally runs longer than the interval between schedule ticks — a nightly job that starts taking 25 hours under `Allow` silently starts stacking concurrent executions rather than skipping or replacing the overrunning one.
- **`startingDeadlineSeconds` determines what happens after real-world outages**, like a control-plane downtime spanning several missed schedule ticks — without it, or with it set too generously, a cluster recovering from an outage can suddenly fire off a burst of "catch-up" Jobs for every tick that was missed, which is rarely the intended behavior for time-sensitive scheduled work.

🔑 **Key Takeaway:** A CronJob is Job scheduling, not a distinct execution model — master the completions/parallelism/backoffLimit mechanics in [§35](./Section-35-Part5-Jobs-Run-To-Completion-Workloads.md) first, then layer on `schedule`, `concurrencyPolicy`, and `startingDeadlineSeconds` as the scheduling-specific decisions that determine how the cluster behaves around overlapping runs and missed ticks.

## 3. Prerequisites and Dependencies

Builds directly on [§35](./Section-35-Part5-Jobs-Run-To-Completion-Workloads.md) (Job completions/parallelism/backoffLimit mechanics, which every CronJob-generated run follows unchanged) and assumes the general controller/reconciliation model from [§1](../Part1/Section-01-Part1-What-Kubernetes-Is-Container-Orchestration-Problem.md).

## 4. Architecture Diagram

```text
                    CronJob "nightly-backup"
                schedule: "0 2 * * *"  (02:00 daily)
                concurrencyPolicy: Forbid
                startingDeadlineSeconds: 300
                                │
                  cron scheduler ticks at 02:00
                                │
                ┌───────────────┴───────────────┐
                │  Is a previous Job from this  │
                │  CronJob still Active?        │
                └───────────────┬───────────────┘
                     yes ◄──────┼──────► no
                      │                    │
           concurrencyPolicy decides:      ▼
           Allow  → start anyway    Job "nightly-backup-28394710" created
           Forbid → skip this tick         │
           Replace→ kill old, start new    ▼
                                    Pods run to completion (§35 mechanics:
                                    completions, parallelism, backoffLimit)
                                            │
                                            ▼
                              Job marked Complete or Failed
                                            │
                                            ▼
                        retained per successfulJobsHistoryLimit /
                        failedJobsHistoryLimit (older Jobs garbage-collected)

  Missed-tick handling:
  control plane down 02:00–03:15 → tick at 02:00 missed
  startingDeadlineSeconds: 300 (5 min) → too late, tick is skipped entirely
  (a larger startingDeadlineSeconds would instead fire a late catch-up run)
```

- **Each firing is a completely independent Job object**, named `<cronjob-name>-<unix-timestamp-ish-suffix>`, fully visible via `kubectl get jobs` alongside any manually created Jobs.
- **`concurrencyPolicy: Forbid` and `Replace` both require the controller to know whether a previous Job is still `Active`**, which is why a CronJob's own status (`kubectl get cronjob` shows an `ACTIVE` column) is meaningful, unlike a plain Job.
- **History limits apply independently to successful and failed Jobs** — a CronJob can retain, say, 3 successful and 1 failed Job by default, garbage-collecting older ones beyond those bounds automatically.

## 5. Hands-On: Defining and Operating CronJobs

### 5.1 A Basic Scheduled Job with Explicit Concurrency Policy

**Purpose:** Define a nightly backup CronJob with clear, deliberate overlap and history behavior.

```yaml
# nightly-backup-cronjob.yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: nightly-backup
spec:
  schedule: "0 2 * * *"
  timeZone: "America/New_York"
  concurrencyPolicy: Forbid
  startingDeadlineSeconds: 300
  successfulJobsHistoryLimit: 3
  failedJobsHistoryLimit: 1
  jobTemplate:
    spec:
      backoffLimit: 2
      activeDeadlineSeconds: 3600
      template:
        spec:
          restartPolicy: OnFailure
          containers:
            - name: backup
              image: myregistry/db-backup:1.3
              command: ["./backup.sh", "--target=s3"]
```

```bash
$ kubectl apply -f nightly-backup-cronjob.yaml
cronjob.batch/nightly-backup created

$ kubectl get cronjob nightly-backup
NAME              SCHEDULE      TIMEZONE           SUSPEND   ACTIVE   LAST SCHEDULE   AGE
nightly-backup    0 2 * * *     America/New_York   False     0        <none>          9s

# after 02:00 fires
$ kubectl get jobs
NAME                          COMPLETIONS   DURATION   AGE
nightly-backup-28394710       1/1           4m12s      4m20s

$ kubectl get cronjob nightly-backup
NAME              SCHEDULE      TIMEZONE           SUSPEND   ACTIVE   LAST SCHEDULE   AGE
nightly-backup    0 2 * * *     America/New_York   False     0        4m20s ago       6h
```

**Common errors:** Omitting `spec.timeZone` historically defaulted the schedule to the kube-controller-manager process's local time (commonly UTC in most clusters) — teams that assumed their local timezone without setting this field explicitly have shipped backup jobs firing at unexpected wall-clock hours; setting `timeZone` explicitly removes the ambiguity entirely.

### 5.2 Testing concurrencyPolicy Behavior

**Purpose:** Demonstrate the practical difference between `Allow`, `Forbid`, and `Replace` when a run overlaps the next scheduled tick.

```bash
# schedule fires every minute for demonstration; job intentionally takes 90s
$ kubectl get cronjob slow-job
NAME       SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
slow-job   * * * * *     False     1        45s ago         3m

# with concurrencyPolicy: Forbid — next tick at the 1-minute mark is skipped
$ kubectl get events --field-selector reason=JobAlreadyActive
LAST SEEN   TYPE      REASON             OBJECT               MESSAGE
5s          Warning   JobAlreadyActive   cronjob/slow-job      Not starting job because prior execution is still running

# with concurrencyPolicy: Replace — the in-flight Job is terminated, a new one starts
$ kubectl get jobs -l job-name -o wide
NAME                  COMPLETIONS   DURATION   AGE
slow-job-28394822     0/1           12s        12s    # previous run, terminated early
slow-job-28394881     0/1           2s         2s     # replacement run just started
```

**Production usage example:** `Forbid` is the correct choice for most backup/migration-style CronJobs where overlapping runs could corrupt shared state; `Replace` suits idempotent polling-style jobs where only the freshest run's result actually matters and a stale in-flight run should be abandoned outright.

### 5.3 Suspending a CronJob and Interpreting Missed-Schedule Behavior

**Purpose:** Temporarily pause scheduled execution (e.g., during a maintenance window) without deleting the CronJob object.

```bash
$ kubectl patch cronjob nightly-backup -p '{"spec":{"suspend":true}}'
cronjob.batch/nightly-backup patched

$ kubectl get cronjob nightly-backup
NAME              SCHEDULE      SUSPEND   ACTIVE   LAST SCHEDULE   AGE
nightly-backup    0 2 * * *     True      0        1d ago          3d

# resume later
$ kubectl patch cronjob nightly-backup -p '{"spec":{"suspend":false}}'
cronjob.batch/nightly-backup patched
```

**Common errors:** Setting `startingDeadlineSeconds` too small relative to how long the controller-manager might occasionally lag (e.g., during a cluster upgrade) causes legitimate ticks to be silently skipped rather than caught up — worth setting deliberately based on how tolerant the specific workload is of a late, catch-up-style run versus simply skipping a missed slot entirely.

## 6. Production Usage Notes

- **`concurrencyPolicy: Forbid` is the safest default for anything touching shared, non-idempotent state** (backups, migrations, financial reconciliation jobs); `Allow` should be a deliberate choice made only when overlapping runs are genuinely harmless.
- **History limits should be set high enough to support real incident investigation** — the default of retaining only a few Jobs can mean the specific failed run from three days ago that a teammate wants to inspect has already been garbage-collected; raise `failedJobsHistoryLimit` for critical scheduled jobs accordingly.
- **CronJob schedule strings are easy to get subtly wrong** (`0 2 * * *` vs. `0 2 * * 0`, daily vs. weekly-on-Sunday) — validating a new or edited schedule against a cron expression explainer before applying is cheap insurance against a very quiet, very wrong production mistake.

## 7. Security Considerations

- Every field from [§35](./Section-35-Part5-Jobs-Run-To-Completion-Workloads.md)'s Job security guidance applies unchanged to a CronJob's `jobTemplate` — ServiceAccount scope, SecurityContext, and Secret usage on the underlying Job deserve the same review, since a CronJob is simply a Job created repeatedly on a timer.
- A CronJob with `concurrencyPolicy: Allow` and no `activeDeadlineSeconds` on its `jobTemplate` can, under sustained failure, accumulate an unbounded number of concurrently running Pods over time — a resource-exhaustion risk worth explicitly guarding against on any CronJob with elevated privileges or access to sensitive systems.

## 8. Common Troubleshooting Scenarios

| Symptom                                                      | Likely Cause                                                                                                  | Resolution Path                                                                                                         |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Scheduled runs firing at the wrong wall-clock time           | `spec.timeZone` unset, defaulting to the controller-manager's local/UTC time instead of the intended timezone | Set `spec.timeZone` explicitly to the intended IANA timezone                                                            |
| Runs silently skipped after a cluster outage                 | `startingDeadlineSeconds` too small to cover the outage window                                                | Increase the deadline if catch-up runs are desired; otherwise this is expected behavior                                 |
| Overlapping runs of the same CronJob observed simultaneously | `concurrencyPolicy: Allow` (the default) combined with a job that occasionally overruns the schedule interval | Switch to `Forbid` or `Replace` depending on whether overlap or staleness is the bigger risk                            |
| Can't find a failed run from several days ago                | `failedJobsHistoryLimit` too low, and the Job/Pod objects were already garbage-collected                      | Raise the history limit going forward; ship Job logs to external log storage (Part 12) so history isn't the only record |

## 9. Best Practices

- Always set `timeZone` explicitly rather than relying on the cluster's default, since that default has historically varied and is easy to get wrong silently.
- Choose `concurrencyPolicy` deliberately per workload rather than leaving the `Allow` default unexamined — `Forbid` for anything touching shared or non-idempotent state.
- Set both `startingDeadlineSeconds` and the underlying Job's `activeDeadlineSeconds`/`backoffLimit` intentionally, so both "how late is too late to start" and "how long is too long to keep retrying" are explicit decisions rather than defaults nobody reviewed.

## 10. Common Anti-Patterns / Mistakes

- **Leaving `concurrencyPolicy` at the default `Allow` for a job with side effects on shared state**, allowing silent overlapping executions the first time the job runs longer than expected.
- **Assuming a missed schedule tick is always retried** — depending on `startingDeadlineSeconds`, a missed tick may simply be skipped entirely, which is easy to misunderstand as a bug rather than configured behavior.
- **Treating CronJob history retention as a substitute for real log aggregation**, then losing the ability to investigate a failure once the relevant Job object has been garbage-collected past the history limit.

## 11. Interview Questions

**🎯 Beginner:** _"What's the relationship between a CronJob and a Job?"_
**Model answer:** A CronJob doesn't run workloads itself — it creates a new Job object at each tick of its configured cron schedule, and that Job then behaves exactly as any other Job would: tracking completions, parallelism, and retries via backoffLimit, following the same mechanics as a manually created Job.
_What the interviewer is probing for:_ Understanding that CronJob is purely a scheduling wrapper, not a separate execution model.

**🎯 Intermediate:** _"What does `concurrencyPolicy: Forbid` do, and when would you choose it over `Allow`?"_
**Model answer:** `Forbid` skips creating a new Job at the next scheduled tick if a previous Job from the same CronJob is still `Active`, rather than letting them run concurrently. I'd choose it for any workload where overlapping runs could cause harm — a backup or database migration job that isn't safe to run twice at once — reserving `Allow` (the default) for genuinely independent, side-effect-free runs where overlap causes no real problem.
_What the interviewer is probing for:_ Practical judgment about when overlap is actually dangerous versus harmless, not just definition recall.

**🎯 Senior:** _"A nightly CronJob didn't run after the cluster was down for three hours overlapping its scheduled time. Is that a bug?"_
**Model answer:** Not necessarily — it depends on `startingDeadlineSeconds`. If it's unset or set to a value smaller than the outage duration, Kubernetes considers that missed tick too far in the past to still be worth starting and simply skips it, which is expected, documented behavior, not a controller malfunction. If catch-up execution after an outage is actually desired, the fix is raising `startingDeadlineSeconds` to comfortably exceed realistic outage windows; if a missed run genuinely needs a guaranteed catch-up mechanism regardless of any deadline, a CronJob's tick-based model isn't the right guarantee to build on, and an alternative (an idempotent, externally triggered re-run) might be more appropriate.
_What the interviewer is probing for:_ Correctly attributing a "missed run" to configuration rather than assuming it's a bug, and knowing the actual field responsible.

**🎯 Architect:** _"How would you design scheduling for a fleet of dozens of CronJobs with varying criticality, from best-effort cleanup tasks to revenue-critical nightly reconciliation jobs?"_
**Model answer:** I'd tier them explicitly rather than applying one config across the board: critical jobs get `concurrencyPolicy: Forbid`, a generous but bounded `startingDeadlineSeconds` tuned to realistic outage windows, high `failedJobsHistoryLimit` for post-incident forensics, and alerting wired to Job failure events (via the underlying Job's status, surfaced through the observability stack in Part 12) rather than relying on someone noticing a missing report. Best-effort jobs can run with looser settings and shorter history retention. I'd also push hard for idempotency in every job's implementation regardless of tier, since that's what makes `Replace` or manual re-runs after an incident safe rather than risky, and I'd centralize Job logs into external log storage rather than depending on CronJob history limits as the system of record for what actually happened on any given night.
_What the interviewer is probing for:_ Whether the candidate treats CronJob configuration as a risk-tiered design decision across a fleet, not a one-size-fits-all default applied uniformly.

## 12. Common Misconceptions

1. **"A CronJob runs the container directly on its own schedule."** It creates a new Job object at each tick, and that Job creates the actual Pods — the CronJob itself never runs a container.
2. **"Missed schedule ticks are always caught up later."** Whether a late tick is started at all depends entirely on `startingDeadlineSeconds`; without a generous enough value, missed ticks are simply skipped.
3. **"`concurrencyPolicy: Allow` is a safe default for any recurring job."** It silently permits overlapping runs, which is only safe for workloads with no harmful interaction between concurrent executions — a real risk for anything touching shared, non-idempotent state.
4. **"CronJob failure history is a reliable long-term audit log."** History is bounded by `successfulJobsHistoryLimit`/`failedJobsHistoryLimit` and garbage-collected beyond that — genuine audit needs require shipping logs to external storage (Part 12), not relying on retained Job objects.

## 13. 🔑 Key Takeaways

- A CronJob is purely a scheduling layer over Jobs ([§35](./Section-35-Part5-Jobs-Run-To-Completion-Workloads.md)) — every completions/parallelism/backoffLimit mechanic from that section applies unchanged to each scheduled run.
- `concurrencyPolicy` (`Allow`/`Forbid`/`Replace`) determines what happens when a run is still active at the next scheduled tick, and should be chosen deliberately per workload's tolerance for overlap.
- `startingDeadlineSeconds` determines whether a missed schedule tick (e.g., during a cluster outage) is still started late or simply skipped.
- `successfulJobsHistoryLimit`/`failedJobsHistoryLimit` bound retained Job history independently for successes and failures — not a substitute for real log aggregation.
- Setting `spec.timeZone` explicitly removes a historically common source of "the job ran at the wrong hour" incidents.

## 14. Related Concepts & What's Next

[§35](./Section-35-Part5-Jobs-Run-To-Completion-Workloads.md) supplied the Job mechanics (completions, parallelism, backoffLimit) that every CronJob-generated run follows unchanged; this section added only the scheduling layer on top — `schedule`, `concurrencyPolicy`, and `startingDeadlineSeconds`. Together, [§33](./Section-33-Part5-Statefulsets-Stable-Network-Identity-Ordered-Deployment.md)–[§36](./Section-36-Part5-CronJobs-Scheduled-Job-Execution.md) complete the "advanced workload shapes" beyond plain Deployments: stable-identity stateful workloads, node-level daemons, run-to-completion batch work, and its scheduled variant. [§37](./Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md) shifts from workload shape to automatic capacity response — scaling Pod replica count dynamically based on observed load.

**Next Section:** [§37](./Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md) — `Section-37-Part5-Horizontal-Pod-Autoscaler-HPA.md`
