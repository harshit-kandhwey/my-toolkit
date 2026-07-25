# Section 7 (Part 1): Cloud Run

## 7.1 Definition

**Plain language:** Cloud Run lets you take a containerized application — anything you can package into a Docker container — and run it without managing any servers at all. Google runs your container only when requests arrive, scales the number of running copies up and down automatically (including down to zero when there's no traffic), and you pay only for the compute time actually used while handling requests.

**Precise:** Cloud Run is a fully managed serverless compute platform for running stateless containers, invoked either as **services** (long-running, request-driven, HTTP/gRPC endpoints) or **jobs** (run-to-completion tasks not tied to serving requests), with automatic autoscaling — including scale-to-zero — based on concurrent request load, built on top of the open-source Knative API surface.

## 7.2 Why It Exists / Problem It Solves

App Engine Flexible (Section 6) already ran arbitrary containers, but always kept at least one instance warm and had slow deployment/scaling cycles. Cloud Functions (Section 8) scaled to zero but restricted you to a single function handler in a supported language, not an arbitrary container. Cloud Run exists to combine the best of both: the container flexibility of Flexible (bring any language, any dependency, any binary) with the fast, granular, scale-to-zero autoscaling of Cloud Functions — filling the gap between "PaaS with container support but no scale-to-zero" and "scale-to-zero but function-only," without requiring the operational complexity of running a full Kubernetes cluster (GKE, Section 30) just to get container-based serving.

## 7.3 Concurrency and Autoscaling

Cloud Run's defining architectural feature is **per-instance request concurrency**: each running container instance can serve multiple concurrent requests simultaneously (configurable, up to a maximum), rather than one request per instance as in the original Cloud Functions model. Cloud Run's autoscaler adds or removes container instances based on actual concurrent load against this configured concurrency target, and — critically — will scale a service down to **zero instances** entirely when there is no traffic, resuming with a cold start on the next incoming request.

- **Minimum instances:** Can be configured above zero to eliminate cold starts for latency-sensitive services, at the cost of paying for that guaranteed-warm capacity continuously.
- **Maximum instances:** Caps the autoscaler's ceiling, both as a cost-control mechanism and to avoid overwhelming downstream dependencies (e.g., a database with a limited connection pool).

## 7.4 Cloud Run Services vs. Jobs

| Aspect           | Cloud Run **Service**                                             | Cloud Run **Job**                                                                         |
| ---------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Invocation model | Responds to incoming HTTP/gRPC requests                           | Runs to completion, then exits — not request-driven                                       |
| Use case         | Web APIs, webhooks, microservices                                 | Batch processing, one-off scripts, scheduled data tasks                                   |
| Scaling          | Autoscaled by concurrent request load, can scale to zero          | Runs a specified number of parallel task executions, then stops entirely                  |
| Typical trigger  | Direct HTTP call, Load Balancer, Cloud Scheduler (as an HTTP hit) | `gcloud run jobs execute`, Cloud Scheduler, Workflows (Section 53), Eventarc (Section 53) |

## 7.5 Revisions and Traffic Splitting

Every deployment to a Cloud Run service creates an immutable **revision** — a specific, versioned combination of container image, configuration, and environment variables. Traffic can be split across multiple revisions by percentage, identical in purpose to App Engine's version traffic splitting (Section 6.6), enabling canary deployments and instant rollback by simply shifting the traffic percentage back to a previous revision, since old revisions remain deployed and addressable rather than being deleted on redeploy.

## 7.6 Architecture Diagram

```
                     Container Image
                (built via Cloud Build, Section 50)
                             │
                    gcloud run deploy
                             │
                             ▼
                Cloud Run Service "api-service"
        ┌────────────────────┴────────────────────┐
        │                                         │
   Revision "api-service-00042"          Revision "api-service-00043"
   (previous, stable)                    (new, canary)
        │  90% traffic                            │  10% traffic
        ▼                                         ▼
  ┌───────────┐ ┌───────────┐               ┌───────────┐
  │ Instance  │ │ Instance  │               │ Instance  │  ◄ scales 0►N based on
  │ (warm)    │ │ (warm)    │               │(cold-start│    concurrent request load
  └───────────┘ └───────────┘               │ on demand)│
                                            └───────────┘
        Idle service (no traffic) ► scales to ZERO instances
```

## 7.7 Hands-On Example

**Purpose:** Deploy a container image to Cloud Run as a service, allowing unauthenticated public access.

```bash
gcloud run deploy api-service \
  --image=gcr.io/payments-prod-01/api-service:v1.4 \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --min-instances=1 \
  --max-instances=20 \
  --concurrency=80
```

**Expected output:**

```
Deploying container to Cloud Run service [api-service] in project [payments-prod-01] region [us-central1]
✓ Deploying new service... Done.
Service [api-service] revision [api-service-00001-xyz] has been deployed
and is serving 100 percent of traffic.
Service URL: https://api-service-abcdef123-uc.a.run.app
```

**Purpose:** Run a Cloud Run Job (a batch task, not a request-serving service).

```bash
gcloud run jobs execute nightly-reconciliation \
  --region=us-central1 \
  --wait
```

**Expected output:**

```
Executing job [nightly-reconciliation]...
Execution [nightly-reconciliation-a1b2c] completed successfully.
```

## 7.8 Comparison: Cloud Run vs. App Engine Flexible vs. GKE

| Aspect                    | Cloud Run                                                        | App Engine Flexible                               | GKE (Section 30)                                                                           |
| ------------------------- | ---------------------------------------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------ |
| Scale-to-zero             | Yes                                                              | No                                                | No (nodes generally run continuously; workload-level scale-to-zero requires extra tooling) |
| Operational overhead      | Minimal — no cluster/node management                             | Minimal — no cluster/node management              | Higher — cluster upgrades, node pools, networking config                                   |
| Orchestration granularity | Single-container-per-revision service/job model                  | Single service per app.yaml                       | Full Kubernetes — pods, deployments, services, custom controllers                          |
| Best fit                  | Stateless containers, variable/bursty traffic, event-driven jobs | Legacy apps needing always-warm custom containers | Complex multi-service architectures needing full orchestration control                     |

## 7.9 Production & Enterprise Usage

- **Microservices backends:** Cloud Run is a common default for stateless microservices and internal APIs, given minimal operational overhead and pay-per-use billing that scales cleanly from near-zero to high-traffic without capacity planning.
- **Event-driven processing:** Cloud Run services are frequently invoked by Eventarc (Section 53) in response to Pub/Sub messages or Cloud Storage events, and Cloud Run Jobs are invoked by Cloud Scheduler for recurring batch tasks — a common alternative to Cloud Functions for anything needing more than a single lightweight handler.
- **Gradual migration path:** Organizations migrating off App Engine Flexible or self-managed container platforms commonly choose Cloud Run first before considering GKE, reserving GKE for cases genuinely requiring Kubernetes-level orchestration control (Section 10 covers this decision in full).

## 7.10 Common Misconceptions

- **Misconception:** "Cloud Run is only for simple, single-request-at-a-time workloads like Cloud Functions." Cloud Run supports configurable per-instance concurrency (multiple simultaneous requests per container instance) and runs arbitrary containers with any dependencies — it is materially more flexible than the original Cloud Functions model.
- **Misconception:** "Scale-to-zero means Cloud Run is always the cheapest option." For services with consistently high, steady traffic, the always-on cost of enough Cloud Run instances to handle that load can approach or exceed a comparably-sized always-on Compute Engine/GKE deployment — scale-to-zero's cost advantage is most pronounced for bursty or intermittent traffic, not steady peak load.

## 7.11 Interview Questions

**🎯 Beginner:** _What is the difference between a Cloud Run service and a Cloud Run job?_
**Model answer:** A Cloud Run service is a long-running, request-driven deployment that responds to HTTP/gRPC requests and autoscales — including to zero — based on incoming traffic. A Cloud Run job is a run-to-completion task, not tied to serving requests, used for batch processing or one-off scripts; it executes a specified number of task instances and then stops, rather than waiting indefinitely for requests.

**🎯 Intermediate:** _How does Cloud Run's concurrency setting affect both cost and cold-start behavior?_
**Model answer:** The concurrency setting controls how many simultaneous requests a single container instance will handle before Cloud Run spins up an additional instance. A higher concurrency value means fewer total instances are needed to absorb a given request volume, which reduces cost (fewer billed instance-seconds) but also means each instance needs enough CPU/memory to genuinely serve that many requests in parallel without degrading latency. Setting concurrency too high for a CPU-bound workload can cause requests to queue behind each other on an already-busy instance; setting it too low creates more frequent scaling events and, for a service scaled to zero, more frequent cold starts as new instances are provisioned.

**🎯 Senior/Architect:** _You're migrating a fleet of Cloud Functions handling Pub/Sub events, HTTP webhooks, and scheduled batch jobs into a more maintainable architecture. Where does Cloud Run fit, and where wouldn't you use it?_
**Model answer:** For the HTTP webhook handlers and any function whose logic has grown complex enough to need multiple files, custom dependencies, or shared code across handlers, I'd containerize them as Cloud Run services — this gives full control over the runtime environment and avoids the more constrained deployment model of individual functions, while keeping the same scale-to-zero cost profile. For the scheduled batch jobs, I'd use Cloud Run Jobs directly rather than services, since jobs are purpose-built for run-to-completion semantics without needing to fake a request-response cycle. For the Pub/Sub-triggered event handlers, I'd evaluate whether they're simple enough to remain as 2nd-gen Cloud Functions (Section 8), which are themselves built on Cloud Run and Eventarc under the hood — if the handlers are small, single-purpose, and rarely change, keeping them as Cloud Functions may be less operational overhead than maintaining container builds for each; if they're numerous, complex, or share significant logic, consolidating into Cloud Run services triggered by Eventarc reduces duplication and gives more deployment control (canary revisions, traffic splitting) than individual functions provide.

## 7.12 Key Takeaways

- 🔑 Cloud Run runs arbitrary containers with configurable per-instance request concurrency, autoscaling — including to zero — based on load.
- 🔑 Services are request-driven and long-running; Jobs are run-to-completion batch tasks — a clear split in invocation model.
- 🔑 Revisions are immutable per-deployment snapshots, enabling traffic splitting for canary rollouts and instant rollback, just like App Engine's version traffic splitting.
- 🔑 Cloud Run sits between App Engine Flexible (always-on containers) and GKE (full Kubernetes orchestration) in the control-vs-convenience spectrum explored fully in Section 10.

## 7.13 Related Concepts

App Engine as the PaaS predecessor (Section 6), Cloud Functions for lightweight single-purpose event handlers (Section 8), Eventarc and Workflows for event-driven orchestration (Section 53), GKE for full Kubernetes control (Section 30), and the full compute decision matrix (Section 10) all build on the serverless container model introduced here.
