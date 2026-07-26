# Section 8 (Part 1): Cloud Functions

## 1. Definition

**Plain language:** Cloud Functions lets you deploy a single small piece of code — a function — that Google runs automatically whenever a specific event happens: an HTTP request arrives, a file is uploaded to Cloud Storage, a message is published to Pub/Sub, or a document changes in Firestore. You never provision a server, never manage a container, and pay only for the function's actual execution time.

**Precise:** Cloud Functions is GCP's Function-as-a-Service (FaaS) offering, deploying single-purpose functions triggered by HTTP requests or asynchronous events, available in two generations — **1st gen** (the original, more limited implementation) and **2nd gen** (rebuilt on top of Cloud Run and Eventarc, Section 7 and Section 53, offering longer execution times, larger instance sizes, and a broader set of event sources).

## 2. Why It Exists / Problem It Solves

Cloud Functions exists for the narrowest, most granular slice of the serverless spectrum: a single unit of logic reacting to a single event, with zero infrastructure concerns — no container to build, no `app.yaml` to maintain, just a function signature and a deployment command. It solves the "I just need this one small thing to run when X happens" problem more simply than Cloud Run (which requires a container image and Dockerfile) or App Engine (which requires a full application structure), at the cost of being restricted to Google's supported language runtimes and a single-handler deployment unit rather than an arbitrary multi-file container.

## 3. 1st Gen vs. 2nd Gen

| Aspect                    | Cloud Functions 1st Gen                                   | Cloud Functions 2nd Gen                                                                                            |
| ------------------------- | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Underlying infrastructure | Google's original proprietary FaaS runtime                | Built on Cloud Run (execution) + Eventarc (eventing)                                                               |
| Max execution timeout     | Shorter (historically up to 9 minutes for HTTP functions) | Longer (up to 60 minutes for HTTP-triggered functions)                                                             |
| Max instance size         | Smaller CPU/memory ceiling                                | Larger CPU/memory ceiling, aligned with Cloud Run limits                                                           |
| Concurrency per instance  | One request per instance                                  | Configurable concurrency per instance (inherited from Cloud Run)                                                   |
| Event sources             | Narrower, fixed set of direct triggers                    | Broader — any event source Eventarc supports, including third-party sources via Eventarc's CloudEvents-based model |
| Traffic splitting         | Not supported                                             | Supported (inherited from Cloud Run's revision model)                                                              |

> ⚠️ **Interview-relevant nuance:** Since 2nd gen functions are literally deployed as Cloud Run services under the hood, a common architect-level question is "why not just use Cloud Run directly?" — the answer is developer ergonomics: Cloud Functions abstracts away the container build step entirely, letting a developer deploy a single source file directly, whereas Cloud Run requires (or auto-generates via buildpacks) a container image first. For simple single-purpose handlers, that reduced ceremony is the entire value proposition of Cloud Functions over hand-building a Cloud Run service.

## 4. Triggers

- **HTTP trigger:** Invoked directly via an HTTPS endpoint, for lightweight APIs or webhooks.
- **Pub/Sub trigger:** Invoked when a message is published to a specified Pub/Sub topic (Section 45) — the standard pattern for decoupled, asynchronous event processing.
- **Cloud Storage trigger:** Invoked when an object is created, updated, or deleted in a specified bucket (Section 11) — commonly used for triggering processing pipelines on file upload (e.g., resizing an uploaded image).
- **Firestore trigger:** Invoked on document create/update/delete events in a Firestore database (Section 15).
- **Eventarc trigger (2nd gen only):** A generalized eventing layer (Section 53) supporting a much broader range of event sources — including many Google Cloud audit log events and, in some configurations, third-party event sources — routed via a standardized CloudEvents format.

## 5. Cold Starts

Like all scale-to-zero serverless compute, an idle Cloud Function incurs a **cold start** on its next invocation — the time needed to provision a fresh execution environment before the function code actually runs. Cold starts are influenced by runtime choice (some language runtimes initialize faster than others), package/dependency size, and whether a **minimum instance count** above zero is configured to keep a warm pool ready (trading cost for latency, identical in principle to Cloud Run's `--min-instances` setting).

## 6. Hands-On Example

**Purpose:** Deploy a 2nd-gen Cloud Function triggered by a Cloud Storage object-finalize event (e.g., a file upload).

```bash
gcloud functions deploy process-upload \
  --gen2 \
  --runtime=python312 \
  --region=us-central1 \
  --source=. \
  --entry-point=process_upload \
  --trigger-bucket=uploads-prod-01 \
  --memory=512MiB \
  --timeout=120s
```

**Expected output:**

```
Deploying function (may take a while - up to 2 minutes)...done.
availableMemoryMb: 512
entryPoint: process_upload
eventTrigger:
  eventType: google.cloud.storage.object.v1.finalized
  resource: projects/_/buckets/uploads-prod-01
name: projects/payments-prod-01/locations/us-central1/functions/process-upload
runtime: python312
status: ACTIVE
```

**Purpose:** Deploy an HTTP-triggered function allowing unauthenticated invocation for a public webhook endpoint.

```bash
gcloud functions deploy webhook-handler \
  --gen2 \
  --runtime=nodejs20 \
  --region=us-central1 \
  --source=. \
  --entry-point=handleWebhook \
  --trigger-http \
  --allow-unauthenticated
```

**Expected output:**

```
Deploying function (may take a while - up to 2 minutes)...done.
httpsTrigger:
  url: https://us-central1-payments-prod-01.cloudfunctions.net/webhook-handler
status: ACTIVE
```

## 7. Comparison: Cloud Functions vs. Cloud Run

| Aspect                         | Cloud Functions                                                     | Cloud Run                                                            |
| ------------------------------ | ------------------------------------------------------------------- | -------------------------------------------------------------------- |
| Deployment unit                | Single function (source code directly, no Dockerfile needed)        | Full container image (Dockerfile or buildpack-generated)             |
| Language flexibility           | Limited to supported managed runtimes                               | Any language/dependency that fits in a container                     |
| Multi-file / complex logic     | Awkward beyond a certain complexity — a single-handler mental model | Naturally suited — a full application structure                      |
| Event-source breadth (2nd gen) | Broad, via Eventarc                                                 | Also broad, via Eventarc (2nd-gen functions run on Cloud Run anyway) |
| Best fit                       | Small, single-purpose event reactions with minimal ceremony         | Multi-endpoint services, complex logic, custom system dependencies   |

## 8. Production & Enterprise Usage

- **Pub/Sub fan-out processing:** A common enterprise pattern is a Pub/Sub topic feeding multiple independent Cloud Functions, each performing a distinct piece of downstream processing (e.g., one function updates a database, another sends a notification, a third writes an audit log) — decoupled via the topic rather than one monolithic handler doing everything.
- **Storage-triggered pipelines:** Image/document processing pipelines commonly trigger a Cloud Function on file upload to a Cloud Storage bucket, which then hands off to further processing (potentially Cloud Run or Dataflow, Section 45, for heavier transformation).
- **Migration to 2nd gen:** Organizations still running 1st-gen functions are commonly encouraged to migrate to 2nd gen for the longer timeout, larger instance sizes, and broader Eventarc-based triggers, though 1st gen remains supported for existing deployments.

## 9. Common Misconceptions

- **Misconception:** "Cloud Functions and Cloud Run are competing, unrelated products." 2nd-gen Cloud Functions are built directly on top of Cloud Run and Eventarc — Cloud Functions is better understood as a more ergonomic deployment experience layered over the same underlying execution platform, not a separate competing runtime.
- **Misconception:** "Cold starts make Cloud Functions unsuitable for any latency-sensitive workload." Configuring a minimum instance count above zero (identical in principle to Cloud Run) eliminates cold starts for a given function at the cost of continuous billing for that warm capacity — cold starts are a configurable trade-off, not an immovable constraint.

## 10. Interview Questions

**🎯 Beginner:** _Name three common trigger types for a Cloud Function._
**Model answer:** HTTP triggers (invoked via a direct HTTPS endpoint), Pub/Sub triggers (invoked when a message is published to a topic), and Cloud Storage triggers (invoked when an object is created/updated/deleted in a bucket). 2nd-gen functions can also use the broader Eventarc trigger mechanism for a wider range of event sources, including many Google Cloud audit log events.

**🎯 Intermediate:** _Why would you choose Cloud Functions 2nd gen over 1st gen for a new deployment?_
**Model answer:** 2nd gen is built on Cloud Run and Eventarc, giving longer execution timeouts (up to 60 minutes for HTTP functions versus a much shorter ceiling on 1st gen), larger available instance sizes, configurable per-instance concurrency, and a broader range of event sources via Eventarc's CloudEvents-based model. It also supports traffic splitting across revisions, inherited from the underlying Cloud Run deployment — a capability 1st gen doesn't have at all. Unless there's a specific compatibility reason to stay on 1st gen, 2nd gen is the generally recommended choice for new functions.

**🎯 Senior/Architect:** _A team has 40 separate Cloud Functions, many sharing near-identical dependency code, each triggered by different Pub/Sub topics for a data-processing pipeline. Lint and deployment overhead has become a maintenance burden. How would you address this?_
**Model answer:** I'd evaluate consolidating the functions that share substantial logic into a smaller number of Cloud Run services, since 2nd-gen Cloud Functions already run on Cloud Run under the hood — the real limitation causing the current maintenance burden is Cloud Functions' single-handler-per-deployment model forcing duplicated shared code across 40 separate deployment units. Migrating to Cloud Run lets me package shared dependency code into one container image and expose multiple internal handlers or routes for the different event types, all triggered via Eventarc pointing at the same or different Pub/Sub topics, cutting duplicated build/deploy pipelines drastically. I'd keep any of the 40 that are genuinely simple, rarely-changing, single-purpose reactions as standalone Cloud Functions rather than force-migrating everything, since the consolidation benefit is proportional to how much shared logic and how much lint/deploy overhead a given function actually carries — not every function benefits equally from consolidation.

## 11. Key Takeaways

- 🔑 Cloud Functions is GCP's FaaS offering for single-purpose, event-triggered code, deployed as source directly (no Dockerfile needed).
- 🔑 2nd gen is built on Cloud Run and Eventarc, offering longer timeouts, larger instances, configurable concurrency, and broader event sources than 1st gen.
- 🔑 Common triggers: HTTP, Pub/Sub, Cloud Storage, Firestore, and (2nd gen) the generalized Eventarc trigger.
- 🔑 Cold starts are a configurable trade-off (minimum instance count) rather than an unavoidable constraint, identical in principle to Cloud Run.
- 🔑 Cloud Functions and Cloud Run share the same underlying execution model in 2nd gen — the choice is about deployment ergonomics and logic complexity, not fundamentally different infrastructure.

## 12. Related Concepts

Cloud Run as the underlying execution platform for 2nd-gen functions (Section 7), Eventarc and Workflows for the broader eventing model (Section 53), Cloud Storage and Firestore as common event sources (Sections 11 and 15), Pub/Sub as a messaging backbone (Section 45), and the full compute decision matrix (Section 10) all build on the FaaS model introduced here.
