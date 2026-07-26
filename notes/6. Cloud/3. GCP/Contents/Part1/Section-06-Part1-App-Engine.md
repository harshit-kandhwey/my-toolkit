# Section 6 (Part 1): App Engine

## 1. Definition

**Plain language:** App Engine is GCP's original "just deploy your code" platform — you push your application, and Google handles provisioning servers, scaling them up and down with traffic, and load balancing between them, without you ever touching a VM directly.

**Precise:** App Engine is a fully managed Platform-as-a-Service (PaaS) for deploying web applications and APIs, offered in two distinct environments — **Standard** and **Flexible** — each with different scaling models, runtime constraints, and underlying infrastructure, configured declaratively via an `app.yaml` file.

## 2. Why It Exists / Problem It Solves

App Engine was GCP's first public product (2008, Section 1.4), built to solve the problem of deploying a web application without provisioning, patching, or scaling any servers at all — the developer supplies code, App Engine supplies everything else: load balancing, autoscaling, versioning, and traffic management. It predates both containers-as-a-service (Cloud Run, Section 7) and function-as-a-service (Cloud Functions, Section 8) on GCP, and remains relevant today for teams wanting a PaaS with more built-in application-platform features (e.g., built-in task queues, memcache, traffic splitting across full application versions) than Cloud Run natively provides for arbitrary containers.

## 3. Standard vs. Flexible Environment

| Aspect                          | App Engine Standard                                                                                   | App Engine Flexible                                                              |
| ------------------------------- | ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- |
| Underlying infrastructure       | Lightweight sandboxed runtime (per-language, not full VMs)                                            | Compute Engine VMs running Docker containers, managed by App Engine              |
| Runtime flexibility             | Limited to supported language runtimes/versions Google provides                                       | Any custom Docker container, any language/library/binary dependency              |
| Scale-to-zero                   | Yes — supports scaling down to zero instances during idle periods                                     | No — always keeps at least one instance running per version                      |
| Cold start                      | Fast (lightweight sandbox startup)                                                                    | Slower (full VM/container boot)                                                  |
| Startup time                    | Seconds                                                                                               | Minutes (for new deployments/instance boot)                                      |
| Local disk / background threads | Historically restricted (older Standard generations); modern (2nd-gen) Standard relaxes many of these | Full VM-level access, no special restrictions                                    |
| Best fit                        | Stateless web apps/APIs in a supported language, cost-sensitive with bursty/idle traffic              | Apps needing custom system dependencies, background processes, or full VM access |

## 4. `app.yaml` Configuration

Every App Engine service is configured via an `app.yaml` file at the root of the deployed code, declaring the runtime, scaling type, and environment variables.

```yaml
runtime: python312
instance_class: F2

env_variables:
  ENVIRONMENT: "production"

handlers:
  - url: /.*
    script: auto
```

## 5. Scaling Types

- **Automatic scaling:** App Engine adjusts the number of running instances based on incoming request rate, latency, and CPU utilization, including scaling down to zero instances (Standard only) when idle — the default choice for most stateless web workloads.
- **Basic scaling:** Instances are created only when requests arrive and shut down when idle for a configured duration, targeted at workloads with bursty, infrequent traffic where automatic scaling's constant background instance isn't needed.
- **Manual scaling:** A fixed number of instances run continuously regardless of load, used for workloads requiring persistent in-memory state or a guaranteed-warm instance pool (e.g., avoiding any cold start for latency-sensitive paths).

## 6. Traffic Splitting

App Engine can split incoming traffic across multiple **deployed versions** of a service by percentage or by IP/cookie-based affinity — used for canary releases (send 5% of traffic to a new version, monitor, then ramp up) or A/B testing, all managed declaratively without needing a separate load balancer configuration.

## 7. Hands-On Example

**Purpose:** Deploy an application to App Engine from the directory containing `app.yaml`.

```bash
gcloud app deploy app.yaml --version=v2 --project=payments-prod-01
```

**Expected output:**

```
Services to deploy:
descriptor:      [./app.yaml]
source:          [/home/user/payments-app]
target project:  [payments-prod-01]
target service:  [default]
target version:  [v2]
target url:      [https://payments-prod-01.uc.r.appspot.com]

Deploying...done.
Setting traffic split for service [default]...done.
Deployed service [default] to [https://payments-prod-01.uc.r.appspot.com]
```

**Purpose:** Split traffic between two versions for a gradual rollout.

```bash
gcloud app services set-traffic default \
  --splits=v1=90,v2=10
```

**Expected output:**

```
Setting traffic split for service [default]...done.
```

## 8. When App Engine Still Makes Sense

Despite newer serverless compute options (Cloud Run, Section 7; Cloud Functions, Section 8), App Engine remains a reasonable choice when:

- The team wants an opinionated, batteries-included PaaS with built-in versioning, traffic splitting, and task queue integration (Cloud Tasks) without assembling these from separate services.
- The application is a traditional multi-page web app in a directly-supported language runtime, where Standard's fast scale-to-zero and simple deployment model outweighs the flexibility of managing a container image.
- An existing App Engine application already works well and there's no compelling business reason to migrate purely for the sake of using a newer service — "if it isn't broken" is a legitimate operational stance here, not a red flag.

For net-new projects needing custom system dependencies, arbitrary language runtimes, or a more container-native operational model, Cloud Run (Section 7) has become the more commonly recommended default.

## 9. Production & Enterprise Usage

- **Standard for cost-sensitive, bursty APIs:** Enterprises running internal tools or bursty-traffic APIs favor Standard's scale-to-zero to avoid paying for idle capacity.
- **Flexible for legacy app migration:** Applications with native system dependencies (custom binaries, specific OS libraries) that can't run in Standard's sandboxed runtime are migrated to Flexible rather than rewritten, since Flexible accepts arbitrary Docker containers.
- **Traffic splitting for safe rollout:** Production deployments commonly use App Engine's built-in traffic splitting for canary releases rather than deploying a new version to 100% of traffic immediately.

## 10. Common Misconceptions

- **Misconception:** "App Engine Flexible is just a newer version of Standard, so it's strictly better." Flexible sacrifices scale-to-zero and fast cold starts in exchange for full VM/container flexibility — it is a different trade-off, not a strict upgrade, and Standard remains the better fit for bursty, cost-sensitive, sandbox-compatible workloads.
- **Misconception:** "App Engine is deprecated in favor of Cloud Run." App Engine is still fully supported and actively used in production by many organizations; Cloud Run is simply the more commonly recommended default for new projects due to its container-native, more granular model — this is a "recommended for new work" distinction, not a deprecation.

## 11. Interview Questions

**🎯 Beginner:** _What's the key trade-off between App Engine Standard and Flexible?_
**Model answer:** Standard runs in a lightweight sandboxed runtime limited to Google-supported language runtimes, but supports fast cold starts and true scale-to-zero. Flexible runs arbitrary Docker containers on managed Compute Engine VMs, giving full system-level flexibility, but always keeps at least one instance running (no scale-to-zero) and has slower cold/boot times. Standard suits stateless, cost-sensitive, sandbox-compatible apps; Flexible suits apps needing custom dependencies or full VM access.

**🎯 Intermediate:** _How would you perform a safe canary rollout of a new App Engine version?_
**Model answer:** Deploy the new code as a new version (not overwriting the existing one) using `gcloud app deploy --version=vNew --no-promote` so it doesn't immediately receive 100% of traffic, then use `gcloud app services set-traffic` to split a small percentage (e.g., 5%) to the new version while the rest stays on the stable version. Monitor error rates and latency on the new version via Cloud Monitoring/Logging, and gradually increase its traffic share, rolling back instantly by shifting the split back to 0% if problems appear — all without needing a separate load balancer or blue/green infrastructure, since traffic splitting is native to App Engine.

**🎯 Senior/Architect:** _A team has a legacy monolith running on App Engine Flexible with a custom system dependency, and leadership wants to modernize toward serverless containers without a full rewrite. What's your approach?_
**Model answer:** Since App Engine Flexible already runs the application as a Docker container on managed VMs, the container image itself is very likely portable to Cloud Run (Section 7) largely unchanged, since Cloud Run also runs arbitrary containers — the main differences to validate are Cloud Run's stricter startup-time and request-concurrency expectations, statelessness assumptions (Cloud Run instances can scale to zero and are not guaranteed session affinity across requests the way a Flexible instance might implicitly provide), and how any custom system dependency behaves in Cloud Run's container runtime sandbox. I'd start by deploying the existing container image as-is to Cloud Run in a non-production project, run integration tests, and specifically probe any implicit assumptions about long-lived local state or background threads that Flexible's always-on VM model tolerated but Cloud Run's scale-to-zero model would not. If that validates cleanly, I'd migrate incrementally by splitting traffic at the load balancer level between the App Engine and Cloud Run deployments, rather than a hard cutover, giving a safe rollback path throughout the migration.

## 12. Key Takeaways

- 🔑 App Engine Standard uses a lightweight sandboxed runtime with fast scale-to-zero; Flexible runs arbitrary Docker containers on managed VMs with no scale-to-zero — a genuine trade-off, not a strict hierarchy.
- 🔑 `app.yaml` declaratively configures runtime, scaling type (automatic/basic/manual), and environment variables.
- 🔑 Built-in traffic splitting across deployed versions enables canary releases and A/B testing without separate load-balancer configuration.
- 🔑 App Engine remains a valid choice for opinionated PaaS needs and existing stable applications, even as Cloud Run has become the more commonly recommended default for new serverless container projects.

## 13. Related Concepts

Cloud Run as the more modern serverless-container alternative (Section 7), Cloud Functions for event-driven single-purpose code (Section 8), and the full compute decision matrix comparing all of GCP's compute options (Section 10) build directly on the PaaS model introduced here.
