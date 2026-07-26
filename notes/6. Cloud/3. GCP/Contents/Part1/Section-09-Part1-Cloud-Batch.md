# Section 9 (Part 1): Cloud Batch

## 1. Definition

**Plain language:** Cloud Batch is Google's managed service for running batch-computing jobs — workloads that process a large amount of work in bulk and then finish, rather than serving live requests. You describe the work (what to run, how many times, on what kind of machine), and Google handles provisioning the compute, running every task to completion, retrying failures, and tearing everything down when the job is done.

**Precise:** Cloud Batch is a fully managed batch job scheduling and execution service that provisions and manages the underlying Compute Engine (Section 2) virtual machines required to run a **job**, composed of one or more **task groups**, each executing a specified number of parallel **tasks**, with built-in retry policies, scheduling, and automatic resource cleanup on completion.

## 2. Why It Exists / Problem It Solves

Before Cloud Batch, running a large batch workload on GCP meant hand-building the orchestration yourself: creating a Managed Instance Group (MIG) sized for the workload, writing startup scripts to pull and execute the work, tracking which VM had processed which chunk of work, handling partial failures and retries manually, and remembering to tear the MIG down when the job finished (or paying for idle capacity that was never scaled back). Cloud Batch exists to remove that undifferentiated heavy lifting: it is purpose-built for the "run this executable or container N times, in parallel, across as many VMs as needed, then clean up" pattern, letting a batch workload be described declaratively rather than orchestrated by hand.

## 3. Core Concepts

- **Job:** The top-level unit submitted to Cloud Batch — a complete unit of batch work with its own scheduling, priority, and lifecycle.
- **Task group:** A job is composed of one or more task groups, each defining a runnable (a script or container image), a task count, and the resource requirements (machine type, CPU, memory, GPUs if needed) for that group's tasks.
- **Task:** A single execution of a task group's runnable. If a task group specifies a task count of 100, Cloud Batch runs that runnable 100 times, distributing the tasks across as many VMs as the job's parallelism setting allows.
- **Parallelism:** Controls how many tasks run concurrently across the provisioned VMs, independent of the total task count — for example, 1,000 total tasks with a parallelism of 50 means at most 50 tasks execute at once.
- **Retry policy:** Cloud Batch can automatically retry failed tasks up to a configured maximum, without the job author having to implement retry logic themselves.
- **Provisioning model:** Cloud Batch provisions Compute Engine VMs on demand for the job's duration (optionally using Spot VMs for cost savings on interruptible work, Section 2) and deletes them automatically once all tasks complete — no lingering infrastructure to clean up.

## 4. Cloud Batch vs. Hand-Orchestrated MIGs

| Aspect                 | Cloud Batch                                                           | Manually Orchestrated MIG for Batch Work                                           |
| ---------------------- | --------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| Job/task modeling      | Native — job, task group, task, parallelism, retries all built in     | None — you invent your own convention for tracking work units                      |
| Provisioning           | Automatic — VMs created and deleted for the job's lifetime            | Manual — you create the MIG, size it, and remember to delete/scale it down         |
| Failure handling       | Built-in retry policy per task                                        | You write and maintain your own retry logic (often in the startup script)          |
| Work distribution      | Cloud Batch schedules tasks across VMs based on parallelism           | You build your own queue/dispatch mechanism (e.g., a Pub/Sub work queue)           |
| Cleanup                | Automatic on job completion                                           | Manual, or a separate scheduled process to detect idle MIGs and scale to zero      |
| Spot/cost optimization | Native Spot VM support at the job level                               | Possible, but requires configuring the MIG's provisioning model yourself           |
| Best fit               | Any bulk run-to-completion workload without existing pipeline tooling | Only worth building by hand when requirements fall genuinely outside Batch's model |

> ⚠️ **Interview-relevant nuance:** A common architect-level trap is reaching for a hand-rolled MIG-plus-Pub/Sub-queue pattern for batch work "because that's how compute scaling is normally done" — Cloud Batch exists precisely to remove the need for that pattern in the common case, and reinventing it duplicates functionality Cloud Batch already provides for free.

## 5. Architecture Diagram

```
                     gcloud batch jobs submit
                                │
                                ▼
                        Cloud Batch Job "render-job"
                                │
              ┌─────────────────┴─────────────────┐
              │                                   │
      Task Group 0                          Task Group 1
   (render frames 1-500)                (encode final output)
   task count: 500                        task count: 1
   parallelism: 50                        parallelism: 1
              │                                   │
   ┌──────────┼──────────┐                        │
   ▼          ▼          ▼                        ▼
┌──────┐  ┌──────┐  ┌──────┐                  ┌──────┐
│ VM 1 │  │ VM 2 │  │ VM.. │  ◄ auto-created  │ VM N │
│tasks │  │tasks │  │tasks │    Spot VMs      │ task │
│1-10  │  │11-20 │  │...   │                  │      │
└──────┘  └──────┘  └──────┘                  └──────┘
   │          │          │                        │
   └──────────┴──────────┴────────────────────────┘
                All VMs deleted automatically
                    on job completion
```

## 6. Hands-On Example

**Purpose:** Submit a Cloud Batch job that runs a script across 200 parallel tasks on Spot VMs.

```bash
gcloud batch jobs submit render-job \
  --location=us-central1 \
  --config=render-job.json
```

`render-job.json`:

```json
{
  "taskGroups": [
    {
      "taskSpec": {
        "runnables": [
          { "script": { "text": "bash render_frame.sh ${BATCH_TASK_INDEX}" } }
        ],
        "computeResource": { "cpuMilli": 2000, "memoryMib": 4096 },
        "maxRetryCount": 2
      },
      "taskCount": 200,
      "parallelism": 50
    }
  ],
  "allocationPolicy": {
    "instances": [
      {
        "policy": {
          "machineType": "n2-standard-2",
          "provisioningModel": "SPOT"
        }
      }
    ]
  },
  "logsPolicy": { "destination": "CLOUD_LOGGING" }
}
```

**Expected output:**

```
Job render-job was successfully submitted.
name: projects/payments-prod-01/locations/us-central1/jobs/render-job
status:
  state: SCHEDULED
```

**Purpose:** Check job status once tasks are underway.

```bash
gcloud batch jobs describe render-job --location=us-central1 --format="value(status.state)"
```

**Expected output:**

```
RUNNING
```

## 7. Cloud Batch vs. Dataflow / Dataproc for Data-Processing Batch Jobs

A frequent point of confusion is when to reach for Cloud Batch versus GCP's dedicated data-processing services, Dataflow and Dataproc (both covered fully in Section 45). The distinction is about what kind of "batch" work is involved:

| Aspect                   | Cloud Batch                                                                   | Dataflow / Dataproc (Section 45)                                                                    |
| ------------------------ | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Workload shape           | Arbitrary executables/containers — rendering, simulations, scripted pipelines | Data-parallel transformations over large datasets (ETL, streaming, Spark/Hadoop jobs)               |
| Programming model        | You bring your own script/binary, no imposed data-processing framework        | Apache Beam (Dataflow) or Spark/Hadoop (Dataproc) — a structured, data-aware execution model        |
| Built-in data primitives | None — no windowing, joins, or distributed data shuffling                     | Native — windowing, joins, aggregations, autoscaling tuned to data volume                           |
| Best fit                 | General-purpose compute-bound batch work not shaped like a data pipeline      | Genuine data-processing pipelines, especially ones needing streaming or a mature big-data framework |

The practical rule: if the workload is fundamentally "run this program N times over a list of inputs" (rendering, simulation, scientific compute, log post-processing scripts), Cloud Batch is the simpler, more direct fit. If the workload is fundamentally "transform, join, and aggregate large structured/semi-structured datasets," Dataflow or Dataproc's data-aware execution engines do meaningfully more work for you than Cloud Batch would, and reimplementing that logic on top of Cloud Batch would mean rebuilding data-processing primitives Dataflow/Dataproc already provide.

## 8. Production & Enterprise Usage

- **Rendering and simulation farms:** Media, scientific, and engineering workloads that need to run the same executable across thousands of input variations (frames, parameter sweeps) are a natural fit, especially combined with Spot VMs for cost efficiency on interruptible work.
- **Scheduled maintenance/reconciliation jobs:** Nightly or periodic bulk-processing scripts (data reconciliation, report generation, bulk file transformation) that don't warrant a persistent data-pipeline framework.
- **Genomics and scientific computing:** High-throughput scientific workloads with large parameter sweeps commonly use Cloud Batch's task-group model to fan out thousands of independent computations.

## 9. Common Misconceptions

- **Misconception:** "Cloud Batch is a data-processing service like Dataflow." Cloud Batch is a general-purpose job/VM orchestrator with no data-aware primitives — it runs whatever script or container you give it, without understanding the structure of any data involved. For genuine data-processing pipelines, Dataflow or Dataproc (Section 45) provide substantially more built-in capability.
- **Misconception:** "You still need to build your own MIG and cleanup logic for large-scale batch work on GCP." Cloud Batch already provisions, schedules, retries, and tears down the underlying VMs automatically — hand-building that orchestration is now rarely necessary outside of highly custom requirements.

## 10. Interview Questions

**🎯 Beginner:** _What are the three core building blocks of a Cloud Batch job?_
**Model answer:** A job is the top-level submitted unit, composed of one or more task groups; each task group defines a runnable (script or container) plus resource requirements and a task count; each task is a single execution of that task group's runnable. A job with a task count of 200 and a parallelism of 50 runs that runnable 200 times total, at most 50 concurrently.

**🎯 Intermediate:** _Why would a team building a nightly batch script pipeline choose Cloud Batch over manually orchestrating a Managed Instance Group?_
**Model answer:** Cloud Batch provides job/task modeling, automatic VM provisioning and teardown, built-in per-task retry policies, and native Spot VM support out of the box — all of which a hand-built MIG approach would require the team to implement and maintain themselves (a custom work-queue mechanism, manual retry logic in the startup script, and a separate process to scale the MIG back down after the work completes). Unless the team has a requirement that genuinely falls outside Cloud Batch's model, building the MIG-based version duplicates functionality Cloud Batch already provides for free.

**🎯 Senior/Architect:** _A team wants to run a large ETL pipeline that joins and aggregates several terabytes of structured data nightly, and is considering Cloud Batch because "it's just a batch job." How would you advise them?_
**Model answer:** I'd steer them toward Dataflow or Dataproc (Section 45) instead. Cloud Batch is a general-purpose compute orchestrator — it has no concept of a dataset, a join, a windowed aggregation, or distributed shuffling; implementing a terabyte-scale join-and-aggregate pipeline on top of Cloud Batch would mean hand-building the data-processing engine that Dataflow (Apache Beam) or Dataproc (Spark/Hadoop) already provide, including partitioning the data correctly across tasks, handling skew, and managing intermediate shuffle state. Cloud Batch is the right tool when the workload is "run this program N times" without an inherent data-processing structure; a genuine ETL join-and-aggregate workload has exactly that structure, so a data-aware framework does materially more of the hard work for the team than Cloud Batch would.

## 11. Key Takeaways

- 🔑 Cloud Batch is GCP's managed batch-computing service — job, task group, and task are the core building blocks, with parallelism controlling concurrent execution.
- 🔑 It automatically provisions and tears down the underlying Compute Engine VMs, including native Spot VM support, removing the need to hand-orchestrate a MIG for batch work.
- 🔑 Built-in retry policies handle task-level failures without custom retry logic.
- 🔑 Cloud Batch is for general-purpose "run this program N times" workloads — genuine data-processing pipelines (ETL, joins, aggregations, streaming) belong on Dataflow or Dataproc (Section 45), which provide data-aware execution engines Cloud Batch does not.

## 12. Related Concepts

Compute Engine and Managed Instance Groups as the underlying provisioned infrastructure and the manual alternative (Section 2), Spot VMs for cost-optimized interruptible work (Section 2), Dataflow and Dataproc for data-aware batch/streaming processing (Section 45), Cloud Scheduler for triggering recurring batch jobs, and the full compute decision matrix (Section 10) all relate to the batch-computing model introduced here.
