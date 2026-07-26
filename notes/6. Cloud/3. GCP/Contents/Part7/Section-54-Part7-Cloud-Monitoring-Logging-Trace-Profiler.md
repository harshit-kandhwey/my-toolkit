# Section 54 (Part 7): Cloud Monitoring, Logging, Trace & Profiler

## 1. Definition

**Plain language:** Once something is deployed, you need to know whether it's actually working — is it up, is it fast, is it throwing errors, and if something breaks, can you figure out why fast enough to fix it? Cloud Monitoring answers "is it healthy" with numbers and alerts, Cloud Logging answers "what exactly happened" with detailed records, Cloud Trace answers "where did the time go" across a chain of service calls, and Cloud Profiler answers "which line of code is actually slow/expensive" inside a single running service.

**Precise:** **Cloud Monitoring** and **Cloud Logging** together form the **Google Cloud Observability** suite: Monitoring collects and visualizes time-series **metrics** (numeric measurements over time) via dashboards and evaluates **alerting policies** against them; Logging ingests structured/unstructured **log entries** from GCP services and applications, routes them via the **Log Router** to **sinks** (BigQuery, Cloud Storage, Pub/Sub, or retained in Cloud Logging's own storage for **Log Analytics**), and integrates with **Error Reporting** for automatic exception aggregation. **Cloud Trace** captures **distributed traces** — the latency breakdown of a single request as it crosses multiple services — while **Cloud Profiler** continuously samples a running application's CPU/memory/wall-time usage at the code-line level with negligible production overhead.

## 2. Why It Exists / Problem It Solves

Running services without observability tooling means outages are discovered by users before they're discovered by the team, and root-causing an incident means manually SSHing into machines to grep log files that may have already rotated away. Specific problems observability tooling solves:

- **No early warning.** Without metrics and alerting, degraded performance (rising latency, a slow error-rate climb) goes unnoticed until it becomes a full outage a customer reports.
- **No searchable, durable record of what happened.** Application logs written only to local disk vanish on VM restart/rescheduling; without centralized log routing, they can't be searched, correlated, or retained for compliance.
- **No visibility into where time goes across services.** In a microservices architecture, a slow user-facing request might spend its time in any of a dozen downstream calls — without distributed tracing, diagnosing this means guessing or adding ad hoc timing logs after the fact.
- **No visibility into code-level cost inside a single service.** Even a fast-looking service can be quietly burning CPU in an inefficient function; without a profiler, this stays invisible until it becomes a scaling/cost problem.

Cloud Monitoring, Logging, Trace, and Profiler together close all four gaps as managed, low-friction-to-adopt services, most of them auto-instrumented for GCP-native compute (GKE, Cloud Run, App Engine) with minimal configuration.

## 3. Cloud Monitoring

### 3.1 Metrics, Dashboards, and Alerting Policies

GCP services automatically emit **system metrics** (e.g., Cloud Run request count/latency, GKE pod CPU) with no setup; applications can also publish **custom metrics** for business-specific measurements (e.g., `orders_processed`). Metrics are visualized on **dashboards** (prebuilt per-service dashboards exist automatically; custom dashboards combine metrics across services) and evaluated by **alerting policies**:

```bash
gcloud alpha monitoring policies create \
  --notification-channels=projects/my-project/notificationChannels/1234567890 \
  --display-name="Cloud Run high error rate" \
  --condition-display-name="5xx rate > 5%" \
  --condition-filter='resource.type="cloud_run_revision" AND metric.type="run.googleapis.com/request_count" AND metric.label.response_code_class="5xx"' \
  --duration=300s \
  --if-value-mean-above=0.05
```

**Purpose:** Creates an alerting policy that fires when a Cloud Run service's 5xx error rate exceeds 5% over a sustained 5-minute window, notifying a preconfigured channel (email, Slack, PagerDuty).
**Expected output (abbreviated):**

```
Created alert policy [projects/my-project/alertPolicies/9876543210].
```

Alerting policies support multi-condition logic, notification channels (email, SMS, PagerDuty, Slack, webhook, Pub/Sub — the last enabling Eventarc/Workflows automation, Section 53), and **snoozing** to suppress known/planned noise without disabling the policy entirely.

### 3.2 Uptime Checks

**Uptime checks** are synthetic, black-box probes run from multiple global locations against a public (or internal) endpoint on a fixed interval, independent of whether the target service is even emitting its own metrics:

```bash
gcloud monitoring uptime create my-api-uptime-check \
  --resource-type=uptime-url \
  --host=api.example.com \
  --path=/healthz \
  --period=60
```

**Purpose:** Establishes an external, ground-truth health signal that doesn't depend on the target application's own instrumentation — useful for catching failures the service itself can't observe (e.g., a DNS misconfiguration or a load balancer outage in front of it).

## 4. Cloud Logging

### 4.1 The Log Router and Sinks

Every log entry written to Cloud Logging passes through the **Log Router**, which evaluates each entry against configured **sinks** — filtered export destinations:

| Sink Destination        | Typical Use                                                              |
| ----------------------- | ------------------------------------------------------------------------ |
| BigQuery                | SQL-queryable long-term log analytics, joins with other business data    |
| Cloud Storage           | Cheap, long-term archival for compliance retention                       |
| Pub/Sub                 | Real-time streaming of logs to external SIEMs or custom processors       |
| Cloud Logging (default) | Short-term (configurable) retention, searchable via the Logs Explorer UI |

```bash
gcloud logging sinks create security-audit-export \
  bigquery.googleapis.com/projects/my-project/datasets/audit_logs \
  --log-filter='logName:"cloudaudit.googleapis.com"'
```

**Purpose:** Continuously exports all Cloud Audit Log entries to a BigQuery dataset for long-term, SQL-queryable security and compliance analysis, independent of Cloud Logging's own default retention window.

### 4.2 Log Analytics

**Log Analytics** upgrades a log bucket to be directly SQL-queryable (via a generated BigQuery-linked dataset or the Logs Explorer's SQL mode), letting teams run analytical queries — error trends over weeks, top-N noisiest services — without first exporting to a separate BigQuery dataset via a sink.

### 4.3 Error Reporting

**Error Reporting** automatically detects and groups stack traces appearing in Cloud Logging output (no separate SDK required for supported languages/frameworks, though a dedicated client library gives richer context), presenting a deduplicated, trend-tracked view of distinct exception types rather than a flat, repetitive log stream — dramatically reducing the noise of triaging "how many _distinct_ things are actually broken" versus "how many log lines mention an error."

## 5. Cloud Trace

**Cloud Trace** captures **spans** — timed segments of work — stitched into a **trace** representing one end-to-end request as it crosses service boundaries, most commonly auto-instrumented via **OpenTelemetry** exporters on Cloud Run, GKE, and App Engine. A trace's waterfall view makes it possible to see, at a glance, that a 2-second user-facing request spent 1.8 seconds waiting on one specific downstream database call rather than guessing across a dozen candidate services.

```bash
gcloud trace list-traces --project=my-project \
  --filter="span:process-order" \
  --limit=5
```

**Purpose:** Lists recent traces containing a span named `process-order`, a starting point for investigating latency reported against that specific operation.

## 6. Cloud Profiler

**Cloud Profiler** continuously samples a running production service's CPU time, wall-clock time, heap, and memory allocation at the function/line level, using low-overhead statistical sampling (rather than always-on instrumentation) so it is safe to leave enabled in production continuously, unlike heavier profiling tools typically run only in isolated debugging sessions. Profiler is most valuable for identifying which specific function in a service is disproportionately consuming CPU or memory across real production traffic patterns — patterns that rarely reproduce faithfully in a local or synthetic benchmark.

## 7. Architecture Diagram

```
      Application / GCP Service
          │              │              │
    metrics         log entries      trace spans
          │              │              │
          ▼              ▼              ▼
  ┌─────────────┐ ┌──────────────┐ ┌─────────────┐      ┌──────────────┐
  │  Cloud      │ │  Log Router  │ │ Cloud Trace │      │ Cloud        │
  │  Monitoring │ │ ──► sinks:   │ │ (waterfall  │      │ Profiler     │
  │(dashboards, │ │ BigQuery,    │ │  latency    │      │ (CPU/memory  │
  │   alerts,   │ │ GCS,         │ │  breakdown) │      │  sampling)   │
  │   uptime)   │ │ Pub/Sub,     │ └─────────────┘      └──────────────┘
  └─────┬───────┘ │ Log Analytics│
        │         └────────┬─────┘
        │                  │
        ▼                  ▼
  Notification Channel   Error Reporting
  (email/Slack/PagerDuty/  (deduplicated
   Pub/Sub ► Eventarc,      exception
   Section 53)              grouping)
```

## 8. Comparison vs. AWS CloudWatch/X-Ray and Azure Monitor/Application Insights

| Concept                             | GCP                                      | AWS                                                               | Azure                                                                 |
| ----------------------------------- | ---------------------------------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------- |
| Metrics + dashboards + alerts       | Cloud Monitoring                         | CloudWatch (Metrics, Dashboards, Alarms)                          | Azure Monitor (Metrics, Workbooks, Alerts)                            |
| Centralized logging                 | Cloud Logging (Log Router + sinks)       | CloudWatch Logs (+ subscription filters)                          | Azure Monitor Logs (Log Analytics workspace)                          |
| SQL-queryable log analytics         | Log Analytics / BigQuery sink            | CloudWatch Logs Insights                                          | Kusto Query Language (KQL) over Log Analytics                         |
| Distributed tracing                 | Cloud Trace                              | X-Ray                                                             | Application Insights (distributed tracing)                            |
| Continuous code profiling           | Cloud Profiler                           | CodeGuru Profiler                                                 | Application Insights Profiler                                         |
| Automatic exception grouping        | Error Reporting                          | No direct equivalent (built via CloudWatch Logs Insights queries) | Application Insights Failures view                                    |
| Synthetic external health checks    | Uptime checks                            | Route 53 health checks / CloudWatch Synthetics                    | Application Insights Availability tests                               |
| Underlying instrumentation standard | OpenTelemetry-based auto-instrumentation | X-Ray SDK (OpenTelemetry increasingly supported)                  | OpenTelemetry-based auto-instrumentation via Application Insights SDK |

## 9. Production & Enterprise Usage

- **Alerting policy tiering:** Enterprises commonly separate **paging alerts** (SLO burn, sustained 5xx spikes — routed to PagerDuty/on-call) from **ticketing alerts** (soft capacity warnings — routed to a queue reviewed during business hours), avoiding alert fatigue that erodes trust in the on-call system (directly feeding Section 55's incident response practices).
- **Centralized log sinks with retention tiers:** A common pattern routes all Cloud Audit Logs and security-relevant logs to a dedicated, tightly IAM-scoped project's BigQuery dataset (Section 61's centralized logging pattern) with long retention for compliance, while routine application debug logs use Cloud Logging's shorter default retention to control storage cost.
- **Trace sampling at scale:** High-traffic services typically configure a fractional trace sampling rate (rather than 100%) to control Cloud Trace ingestion cost, while ensuring error traces are always captured regardless of the sampling rate, since the traces most valuable for debugging are disproportionately the failing ones.
- **Profiler left always-on:** Because Profiler's statistical sampling overhead is low enough to be production-safe, mature teams leave it continuously enabled on production services rather than only during ad hoc investigations, so historical profiling data is already available when an unexplained CPU/cost spike appears.

## 10. Common Misconceptions

- **Misconception:** "Cloud Logging's default retention keeps my logs forever." Cloud Logging's default (`_Default`) bucket has a finite retention window; logs needed for long-term compliance or historical analysis must be routed via a sink to BigQuery or Cloud Storage, or have the bucket's retention explicitly extended — assuming indefinite default retention is a common and costly surprise during an audit.
- **Misconception:** "Cloud Trace and Cloud Profiler do the same job." Trace shows latency _across_ service boundaries for a single request (where did the 2 seconds go, across which downstream calls); Profiler shows resource consumption _within_ one service's code over aggregate production traffic (which function is burning the CPU) — they answer different questions and are commonly used together, not as alternatives.

## 11. Interview Questions

**🎯 Beginner:** _What is the difference between Cloud Monitoring and Cloud Logging, and why are they usually discussed together?_
**Model answer:** Cloud Monitoring deals with numeric time-series metrics — counts, latencies, error rates — visualized on dashboards and evaluated by alerting policies to answer "is the system healthy right now." Cloud Logging deals with discrete, detailed log entries — the actual text/structured record of individual events — searchable to answer "what exactly happened." They're discussed together as the "Google Cloud Observability" suite because real investigations use both: an alert from Monitoring tells you something is wrong and roughly when, then Logging is where you dig into the specific entries explaining why.

**🎯 Intermediate:** _A service's average latency metric looks fine, but users are complaining about slow requests. How would you use Cloud Trace to investigate, and why might the average metric be misleading?_
**Model answer:** An average latency metric can look healthy even when a meaningful subset of requests are slow, because a large number of fast requests can mathematically absorb a smaller number of very slow ones — this is why percentile metrics (p95, p99) are generally more actionable than averages for user-experience investigations. I'd first switch to a percentile view in Cloud Monitoring to confirm a tail-latency problem exists, then pull specific slow traces from Cloud Trace filtered to that time window, examining the span waterfall to identify which specific downstream call (a slow database query, an external API) is consistently responsible for the tail latency, rather than guessing from the service's own code.

**🎯 Senior/Architect:** _Design an alerting strategy for a production service with a 99.9% availability SLO, avoiding both alert fatigue and missed incidents._
**Model answer:** I would define the SLO's error budget explicitly (Section 55) and build alerting policies around **burn rate** — how fast the service is consuming its error budget — rather than a single static error-rate threshold, using a multi-window approach: a fast-burn condition (e.g., consuming budget at a rate that would exhaust it in hours) pages immediately, while a slow-burn condition (a rate that would exhaust it over days) creates a lower-urgency ticket rather than paging, since an immediate page for a slow, sustainable-looking degradation trains on-call engineers to distrust pages. I would route the fast-burn alert's notification channel to a Pub/Sub topic in addition to PagerDuty, letting an Eventarc-triggered Workflows execution (Section 53) automatically gather initial diagnostic context (recent deploys, recent config changes) and attach it to the page, so the responding engineer starts triage with context already assembled rather than starting cold. Uptime checks would run in parallel as an independent, black-box confirmation that the outage is real and externally visible, not just an artifact of the service's own instrumentation being wrong.

## 12. Key Takeaways 🔑

- 🔑 Cloud Monitoring (metrics/dashboards/alerts/uptime checks) and Cloud Logging (Log Router/sinks/Log Analytics/Error Reporting) form the Google Cloud Observability suite, answering "is it healthy" and "what happened" respectively.
- 🔑 Cloud Trace shows cross-service latency breakdown for a single request; Cloud Profiler shows code-level resource consumption within one service across aggregate traffic — complementary, not overlapping.
- 🔑 Cloud Logging's default retention is finite; durable/compliance logging requires explicit sinks to BigQuery or Cloud Storage.
- 🔑 Alerting policy notification channels can target Pub/Sub, directly enabling Eventarc/Workflows-driven automated response (Section 53), a pattern central to modern incident response (Section 55).
- 🔑 Percentile-based metrics and burn-rate alerting generally outperform average-based, static-threshold alerting for both catching real degradation and avoiding alert fatigue.

## 13. Related Concepts

Eventarc and Workflows for alert-driven automation (Section 53), Cloud Audit Logs as a shared input to both Logging and Eventarc (Section 41), centralized logging project patterns in a landing zone (Section 61), SLIs/SLOs/error budgets and on-call practice built directly on this tooling (Section 55), and the GCP vs. AWS vs. Azure comparison (Section 82) all connect directly to the observability model introduced here.
