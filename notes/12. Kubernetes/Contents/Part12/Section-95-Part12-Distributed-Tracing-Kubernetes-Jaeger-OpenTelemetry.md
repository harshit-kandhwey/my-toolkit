# Section 95 (Part 12): Distributed Tracing in Kubernetes (Jaeger/OpenTelemetry Overview)

## 1. Definition

**Plain language:** A single user-facing request in a microservices architecture might touch a dozen services before returning a response — metrics ([§92](./Section-92-Part12-Prometheus-Kubernetes-ServiceMonitors-Node-Exporter-kube-state-metrics.md)) tell you a service is slow, and logs ([§94](./Section-94-Part12-Centralized-Logging-Patterns-Fluentd-FluentBit-Loki-EFK.md)) tell you what each service logged individually, but neither one tells you which specific hop in that chain of a dozen services actually added the latency. Distributed tracing follows one request's entire journey across every service it touched, showing exactly where time was spent.

**Precise definition:** **Distributed tracing** captures a single request's full execution path across multiple services as a **trace** — a tree of **spans**, where each span represents one unit of work (an HTTP call, a database query, a function execution) with a start time, duration, and a set of key-value **attributes**. Spans are causally linked via a shared **trace ID** propagated through request headers, and a **parent span ID** establishing the tree structure (which span called which). **OpenTelemetry (OTel)** is the vendor-neutral instrumentation standard — a set of APIs, SDKs, and a **Collector** component — for generating and exporting this trace data in a consistent format, regardless of which backend ultimately stores and visualizes it. **Jaeger** is one such backend: an open-source distributed tracing system (originally built at Uber) that stores traces and provides a UI for visualizing the resulting span trees, timeline views, and cross-service latency breakdowns.

## 2. Why This Matters

- **Tracing answers a question neither metrics nor logs can answer alone: "which specific hop in this request's path caused the latency?"** — a metrics dashboard might show the checkout service's p99 latency spiked, and logs might show each service's individual log lines, but only a trace shows the actual causal chain of calls and exactly how much time each one consumed, in context.
- **OpenTelemetry's vendor-neutral instrumentation is precisely why an application team can add tracing once and switch backends (Jaeger, Tempo, a commercial APM tool) later without re-instrumenting code** — this decoupling of "how do I generate trace data" from "where does it get stored and visualized" is the entire reason OTel exists as a standard, rather than each vendor requiring its own proprietary SDK.
- **This section completes the three-pillar observability picture (metrics [§92](./Section-92-Part12-Prometheus-Kubernetes-ServiceMonitors-Node-Exporter-kube-state-metrics.md)–[§93](./Section-93-Part12-Grafana-Dashboards-Kubernetes.md), logs [§94](./Section-94-Part12-Centralized-Logging-Patterns-Fluentd-FluentBit-Loki-EFK.md), traces here) that [§96](./Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md)'s capstone synthesizes** — understanding what each signal type uniquely provides, and where they overlap, is what lets a practitioner reach for the _right_ tool during an actual incident rather than defaulting to whichever one they know best.

🔑 **Key Takeaway:** Distributed tracing follows a single request's causal path across every microservice it touches as a tree of spans linked by a shared trace ID, with OpenTelemetry as the vendor-neutral instrumentation standard for generating that data and Jaeger as a common open-source backend for storing and visualizing it — the one observability signal that shows exactly where time was spent across a multi-service call chain.

## 3. Prerequisites and Dependencies

Builds on [§94](./Section-94-Part12-Centralized-Logging-Patterns-Fluentd-FluentBit-Loki-EFK.md) (Centralized Logging), whose collection-agent DaemonSet pattern and Grafana/Kibana query-surface concepts parallel the Collector/backend split covered here, and assumes familiarity with basic Service-to-Service communication ([§50](../Part7/Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md)) as the actual traffic being traced. Sets up [§96](./Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md), the Part 12 capstone synthesizing all three observability signal types.

## 4. Architecture Diagram

```text
   Request: user → API Gateway → checkout-svc → payment-svc → inventory-svc

┌──────────────┐  trace-id: abc123, span: root
│ API Gateway  │──────────────────────────────────────────────► span duration: 420ms
└──────┬───────┘
       │ propagates trace-id via HTTP header (traceparent)
       ▼
┌──────────────┐  span: checkout-svc (child of root)
│ checkout-svc │─────────────────────────────────► span duration: 380ms
└──────┬───────┘
       │ propagates trace-id further
       ├───────────────────────┐
       ▼                       ▼
┌─────────────┐        ┌──────────────┐
│ payment-svc │        │ inventory-svc│
│ span: 90ms  │        │ span: 260ms  │  ← the actual bottleneck
└─────────────┘        └──────────────┘

   Instrumentation & Collection Path:

┌─────────────┐  OTel SDK emits spans    ┌────────────────────────┐
│ Each Pod's  │─────────────────────────►│  OpenTelemetry         │
│ app (OTel   │                          │  Collector (Deployment │
│ SDK/agent)  │                          │  or DaemonSet)         │
└─────────────┘                          └───────────┬────────────┘
                                                     │ exports (OTLP protocol)
                                                     ▼
                                          ┌───────────────────────┐
                                          │        Jaeger         │
                                          │  (storage + query UI) │
                                          └───────────────────────┘
```

- **The trace ID propagating through every HTTP header hop (typically the W3C `traceparent` header) is what lets otherwise-independent spans, emitted by entirely separate services, be reassembled into one coherent tree** after the fact — without this propagation, each service's spans would be disconnected, isolated fragments.
- **The OpenTelemetry Collector sits between instrumented applications and the storage backend**, decoupling "how spans get generated" from "where they end up" — a Collector can batch, filter, or even fan-out the same trace data to multiple backends simultaneously (Jaeger for one team, a commercial tool for another).
- **The span-duration breakdown (root: 420ms, checkout-svc: 380ms, payment-svc: 90ms, inventory-svc: 260ms) directly localizes the bottleneck** — here, inventory-svc's 260ms span is clearly the dominant contributor to overall latency, a conclusion neither a per-service metrics dashboard nor isolated logs could establish this precisely on their own.

## 5. Hands-On: Instrumenting and Querying Traces

### 5.1 Deploying the OpenTelemetry Collector and Jaeger

**Purpose:** Stand up the collection and storage/query layers before any application instrumentation is added.

**Syntax:**

```bash
helm repo add jaegertracing https://jaegertracing.github.io/helm-charts
helm install jaeger jaegertracing/jaeger -n observability --create-namespace

helm repo add open-telemetry https://open-telemetry.github.io/opentelemetry-helm-charts
helm install otel-collector open-telemetry/opentelemetry-collector -n observability \
  --set mode=deployment
```

```yaml
# OpenTelemetry Collector config excerpt — receive OTLP, export to Jaeger
receivers:
  otlp:
    protocols:
      grpc:
      http:
exporters:
  otlp/jaeger:
    endpoint: jaeger-collector.observability.svc.cluster.local:4317
    tls:
      insecure: true
service:
  pipelines:
    traces:
      receivers: [otlp]
      exporters: [otlp/jaeger]
```

**Example usage and expected output:**

```bash
$ kubectl get pods -n observability
NAME                              READY   STATUS    RESTARTS   AGE
jaeger-query-6f8d9c-x2k1            1/1     Running   0          3m
jaeger-collector-7d9f8-m9p2         1/1     Running   0          3m
otel-collector-5c7b6-p4q8            1/1     Running   0          2m

$ kubectl port-forward -n observability svc/jaeger-query 16686:16686
Forwarding from 127.0.0.1:16686 -> 16686
```

**Production usage example:** Routing all application trace exports through the Collector rather than directly to Jaeger means the storage backend can later be swapped (e.g., migrating to Grafana Tempo) by changing only the Collector's exporter configuration — application Pods and their instrumentation never need to know or care where traces ultimately land.

**Common errors:** Pointing application SDKs directly at Jaeger's ingestion endpoint instead of the Collector "to save a hop" — this works initially but eliminates the Collector's batching, sampling, and backend-portability benefits, and becomes a real migration cost later if the backend ever needs to change.

### 5.2 Instrumenting an Application with the OpenTelemetry SDK

**Purpose:** Show the minimal application-side change required to emit spans, and how trace context propagates automatically across an HTTP call.

**Syntax:**

```yaml
# Deployment env vars — auto-instrumentation via OTel SDK config, no code changes
env:
  - name: OTEL_EXPORTER_OTLP_ENDPOINT
    value: "http://otel-collector.observability.svc.cluster.local:4317"
  - name: OTEL_SERVICE_NAME
    value: "checkout-svc"
  - name: OTEL_TRACES_SAMPLER
    value: "parentbased_traceidratio"
  - name: OTEL_TRACES_SAMPLER_ARG
    value: "0.1" # sample 10% of traces
```

**Example usage and expected output:**

```bash
$ kubectl logs -n production deploy/checkout-svc | grep -i "trace"
INFO otel: exporting span trace_id=abc123def456 span_id=789ghi duration_ms=380 service=checkout-svc
```

**Production usage example:** Many teams adopt OpenTelemetry's **auto-instrumentation agents** (available for Java, Python, Node.js, .NET) that inject span creation and trace-context propagation into common HTTP/database client libraries via bytecode manipulation or monkey-patching, without any application code changes at all — meaningful trace coverage from day one, with manual span instrumentation reserved for genuinely custom business logic later.

**Common errors:** Setting `OTEL_TRACES_SAMPLER_ARG` to `1.0` (100% sampling) in a high-throughput production service without considering the storage and Collector throughput cost — full sampling on a busy service can overwhelm both the Collector and the backend, which is why a fractional sampling rate (commonly 1-10%) is the standard production default outside of active incident debugging.

### 5.3 Investigating a Latency Regression via the Jaeger UI

**Purpose:** Use a trace's span breakdown to localize a latency bottleneck to one specific downstream service, directly answering the question metrics alone left open.

**Syntax:**

```text
Jaeger UI → Search → Service: checkout-svc → Min Duration: 400ms
```

**Example usage and expected output:**

```text
Trace abc123def456 — total duration: 720ms
├── checkout-svc (root span)          380ms
│   ├── payment-svc                     90ms
│   └── inventory-svc                  260ms  ← 65% of checkout-svc's own span time
│       └── inventory-db query          240ms  ← nearly all of inventory-svc's time
```

**Production usage example:** This breakdown pinpoints the actual regression to a single slow database query inside `inventory-svc`, not a general "checkout is slow" symptom — the team investigating can go directly to that query (checking for a missing index, a lock contention issue, or a recent schema change) rather than broadly profiling every service in the call chain.

**Common errors:** Concluding a service is slow based on its own span duration alone without expanding its children — `checkout-svc`'s 380ms span looks like the problem in isolation, but the actual root cause is nested two levels deeper, inside `inventory-svc`'s database query span.

## 6. Production Usage Notes

- **Sampling strategy is the central operational tradeoff in distributed tracing at scale** — 100% trace capture gives complete visibility but at real storage and Collector throughput cost, while a low fixed-percentage or adaptive/tail-based sampling strategy (capturing more of the traces that end in errors or high latency) balances cost against catching the traces that actually matter.
- **The OpenTelemetry Collector can run as either a Deployment (centralized, receiving from all Pods over the network) or a DaemonSet (one per node, similar to the logging agents in [§94](./Section-94-Part12-Centralized-Logging-Patterns-Fluentd-FluentBit-Loki-EFK.md))** — the DaemonSet pattern reduces network hops and is common when Collector-side processing needs node-local context.
- **Trace context propagation depends on every hop in the call chain actually forwarding the trace headers** — a service mesh (Istio, Linkerd) or a consistently-applied HTTP client library convention is what typically guarantees this in practice; a single unintentionally "context-blind" proxy or gateway in the chain breaks the trace into disconnected fragments.

## 7. Security Considerations

- **Span attributes can inadvertently capture sensitive data** (full request URLs with embedded tokens, request/response bodies if overly verbose instrumentation is enabled) — the same data-exposure discipline that applies to logs ([§94](./Section-94-Part12-Centralized-Logging-Patterns-Fluentd-FluentBit-Loki-EFK.md)) applies equally to trace attributes, and needs deliberate scrubbing/redaction rules in the Collector pipeline.
- **The Jaeger UI, like Grafana ([§93](./Section-93-Part12-Grafana-Dashboards-Kubernetes.md)) and Kibana, needs its own access control** — trace data reveals internal service topology and call patterns, which is genuinely sensitive architectural information in the wrong hands.
- **The OpenTelemetry Collector's OTLP receiver endpoint should not be exposed outside the cluster without authentication**, since an unauthenticated ingestion endpoint could be abused to inject fabricated trace data or, in some configurations, act as an unintended data-exfiltration path.

## 8. Common Troubleshooting Scenarios

| Symptom                                                       | Cause                                                                                                | Fix                                                                                                                |
| ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Trace shows only one service's spans, chain looks broken      | An intermediate hop (proxy, gateway, or uninstrumented service) isn't propagating trace headers      | Verify every hop forwards `traceparent`/`tracestate` headers; check for a service mesh or library gap              |
| No traces appear in Jaeger at all                             | Application SDK misconfigured (wrong Collector endpoint) or sampling rate effectively zero           | Verify `OTEL_EXPORTER_OTLP_ENDPOINT` and check `OTEL_TRACES_SAMPLER_ARG` isn't set too low                         |
| Collector reports dropped/refused spans                       | Collector throughput exceeded, often from too-high a sampling rate for cluster scale                 | Lower the sampling rate or scale the Collector Deployment horizontally                                             |
| Trace duration looks correct but a child span is missing      | Async/background work (queue-based processing) not instrumented to continue the parent trace context | Explicitly propagate trace context into async job payloads via manual span linking                                 |
| High cardinality span attributes overwhelming backend storage | Attributes include unbounded values (raw user IDs, full URLs with query params) as indexed fields    | Restrict indexed attributes to genuinely low-cardinality fields; keep high-cardinality data as unindexed span logs |

## 9. Best Practices

- Route all application trace exports through the OpenTelemetry Collector rather than directly at a backend, preserving the ability to change backends without re-instrumenting applications.
- Use a fractional or tail-based sampling strategy in production rather than 100% capture, reserving full sampling for active incident investigation windows.
- Prefer OpenTelemetry auto-instrumentation agents for baseline coverage, reserving manual span instrumentation for genuinely custom business logic the auto-instrumentation can't see.

## 10. Common Anti-Patterns / Mistakes

- **Instrumenting application code to export traces directly to Jaeger (or any specific backend) rather than through the OpenTelemetry Collector**, locking in a backend migration cost that OTel's whole design exists to avoid.
- **Setting 100% trace sampling in a high-throughput production service without considering Collector/backend throughput**, risking dropped spans or an overwhelmed backend precisely when trace data matters most.
- **Concluding a bottleneck from a span's own duration without expanding its children**, missing that the actual root cause is nested deeper in the call tree.

## 11. Interview Questions

**🎯 Beginner:** _"What problem does distributed tracing solve that metrics and logs don't?"_
**Model answer:** Metrics tell you a service's aggregate behavior changed (latency went up, error rate spiked), and logs tell you what each service individually recorded, but neither shows the actual causal chain of calls a single request made across multiple microservices, or how much time each hop in that chain consumed. Distributed tracing follows one specific request end-to-end as a tree of spans linked by a shared trace ID, so you can see exactly which service in a multi-hop call chain added the latency, rather than inferring it indirectly from separate metrics and logs.
_What the interviewer is probing for:_ Clear grasp of tracing's unique value versus metrics and logs, not vague familiarity with "Jaeger" as a name.

**🎯 Intermediate:** _"Explain the relationship between OpenTelemetry and Jaeger."_
**Model answer:** OpenTelemetry is the vendor-neutral instrumentation standard — APIs, SDKs, and a Collector component — for generating and exporting trace (and metric/log) data in a consistent format. Jaeger is one specific backend that stores trace data and provides a UI for visualizing it. They're complementary, not competing: an application instrumented with the OpenTelemetry SDK exports spans to an OpenTelemetry Collector, which then forwards them on to whichever backend is configured, Jaeger being one common choice. Because the instrumentation layer (OTel) is decoupled from the backend (Jaeger), a team can switch backends later by reconfiguring the Collector's exporter, without touching any application code.
_What the interviewer is probing for:_ Correctly distinguishing the standard/instrumentation layer from the storage/visualization backend, a distinction people frequently blur.

**🎯 Senior:** _"A trace shows a request's root span at 720ms, but the on-call engineer can't find where the time actually went. What would you check?"_
**Model answer:** First, I'd expand every child span in the tree, not just look at the root span's own duration — the actual bottleneck is very often nested two or three levels deep (as in the example where `checkout-svc` looked slow, but the real cause was a database query span inside `inventory-svc`). If a meaningful gap in total duration isn't accounted for by any visible child span, I'd suspect a missing propagation hop — an uninstrumented service, an async/queue-based step that didn't carry trace context forward, or a proxy/gateway not forwarding `traceparent` headers — meaning part of the actual work is happening completely outside the visible trace. I'd also check the sampling configuration; if this specific trace was captured via a low fixed sampling rate, related but unsampled traces for the same request pattern might tell a fuller story, which is part of the argument for tail-based sampling that specifically captures high-latency and error traces more consistently.
_What the interviewer is probing for:_ Practical trace-analysis skill — checking child spans before concluding root-cause, and recognizing propagation gaps and sampling configuration as separate, real causes of an incomplete picture.

**🎯 Architect:** _"Design the tracing rollout strategy for an organization with 150 services across multiple languages, migrating from no tracing at all."_
**Model answer:** I'd standardize on OpenTelemetry as the single instrumentation layer across all 150 services regardless of language, specifically because its multi-language SDK support and auto-instrumentation agents let teams get baseline trace coverage (HTTP calls, database queries) without hand-writing span logic per service, deferring manual instrumentation to genuinely custom business-critical code paths. I'd deploy the OpenTelemetry Collector centrally (likely as a Deployment behind a Service, scaled independently of application Pods) as the single ingestion point, and pick a backend — Jaeger for a lighter operational footprint, or a commercial/managed option if the organization doesn't want to operate trace storage itself — configured purely at the Collector's exporter layer, so the backend choice is reversible later without touching any of the 150 services' code. Given the scale, I'd adopt tail-based sampling rather than a flat percentage — capturing all error and high-latency traces in full while sampling normal-latency traces at a low rate — to keep storage and Collector costs proportional to genuinely interesting traffic rather than raw volume. I'd mandate that every service, regardless of team or language, correctly propagates `traceparent` headers through any proxy or gateway it owns, since a single non-propagating hop anywhere in a 150-service mesh silently fragments traces for every request passing through it — likely enforced via a shared service-mesh sidecar (Istio) rather than trusting each team's individual HTTP client configuration. Finally, I'd integrate trace data into the same Grafana instance serving metrics ([§93](./Section-93-Part12-Grafana-Dashboards-Kubernetes.md)) and logs ([§94](./Section-94-Part12-Centralized-Logging-Patterns-Fluentd-FluentBit-Loki-EFK.md)) via trace-to-logs and trace-to-metrics correlation (exemplar linking), so an engineer investigating a metric spike can jump directly into a representative trace without manually correlating timestamps across three separate tools.
_What the interviewer is probing for:_ Ability to design tracing adoption at genuine multi-team, multi-language scale — auto-instrumentation for coverage, sampling strategy for cost control, propagation consistency as an organizational (not just technical) challenge, and cross-signal correlation as the ultimate observability goal.

## 12. Common Misconceptions

1. **"Jaeger and OpenTelemetry are competing or redundant tools."** OpenTelemetry is the instrumentation standard for generating trace data; Jaeger is one backend for storing and visualizing it — they're complementary layers, not alternatives to each other.
2. **"100% trace sampling is always the safest choice."** At real production scale, full sampling risks overwhelming the Collector and backend, which is why fractional or tail-based sampling is the standard production default.
3. **"A slow-looking root span means that service is the bottleneck."** The actual cause is very often nested in a child span several levels deeper; the root span's own duration includes all of its children's time.
4. **"Distributed tracing requires rewriting application code from scratch."** OpenTelemetry auto-instrumentation agents cover common HTTP/database client libraries without code changes for most languages, with manual instrumentation reserved for custom logic.

## 13. 🔑 Key Takeaways

- Distributed tracing follows a single request's causal path across microservices as a tree of spans linked by a shared trace ID, answering "where did the time go" in a way metrics and logs alone cannot.
- OpenTelemetry is the vendor-neutral instrumentation standard (SDKs plus a Collector); Jaeger is one common backend for storage and visualization — keep application code exporting to the Collector, never directly to a specific backend.
- Sampling strategy (fractional or tail-based) is the central cost-versus-completeness tradeoff at production scale; 100% sampling is rarely sustainable.
- Trace context propagation depends on every hop forwarding the relevant headers — a single non-propagating proxy or uninstrumented service fragments the trace.
- Always expand a span's children before concluding it's the bottleneck — the actual root cause is frequently nested deeper in the call tree.

## 14. Related Concepts & What's Next

This section completed the three-pillar observability picture alongside [§92](./Section-92-Part12-Prometheus-Kubernetes-ServiceMonitors-Node-Exporter-kube-state-metrics.md)–[§93](./Section-93-Part12-Grafana-Dashboards-Kubernetes.md) (metrics) and [§94](./Section-94-Part12-Centralized-Logging-Patterns-Fluentd-FluentBit-Loki-EFK.md) (centralized logging), showing how distributed tracing uniquely reveals cross-service latency causation that neither of the other two signals can establish alone. [§96](./Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md), next, is the Part 12 capstone — synthesizing probes ([§89](./Section-89-Part12-Liveness-Readiness-Startup-Probes.md)), `kubectl debug` ([§90](./Section-90-Part12-kubectl-logs-exec-debug-Ephemeral-Containers.md)), Metrics Server and Prometheus ([§91](./Section-91-Part12-Metrics-Server-Kubernetes-Metrics-Pipeline.md)–[§92](./Section-92-Part12-Prometheus-Kubernetes-ServiceMonitors-Node-Exporter-kube-state-metrics.md)), Grafana ([§93](./Section-93-Part12-Grafana-Dashboards-Kubernetes.md)), centralized logging ([§94](./Section-94-Part12-Centralized-Logging-Patterns-Fluentd-FluentBit-Loki-EFK.md)), and distributed tracing ([§95](./Section-95-Part12-Distributed-Tracing-Kubernetes-Jaeger-OpenTelemetry.md)) into a unified events-and-audit-log deep dive, and handing off to Part 13's structured troubleshooting methodology.

**Next Section:** [§96](./Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md) — `Section-96-Part12-Events-Audit-Logs-kubectl-describe-Deep-Dive.md`
