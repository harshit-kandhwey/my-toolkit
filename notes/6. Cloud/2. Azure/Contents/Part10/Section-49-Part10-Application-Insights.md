# Section 49 — Application Insights

**Part 10: Monitoring & Observability | Section 49 of 70**
**Prerequisites:** Section 47 (Azure Monitor Fundamentals), Section 48 (Log Analytics & KQL), Section 38 (Azure Functions — referenced integration), Section 13 (App Service), Section 35–37 (AKS)
**Leads into:** Section 50 (Alerts, Action Groups, Dashboards)

---

## 49.1 Introduction and Scope

This section covers Application Insights: Azure Monitor's application-performance-monitoring (APM) layer, providing the request/dependency/exception-level telemetry referenced throughout Sections 38.7.3, 48's KQL examples, and implicitly needed by every application-hosting service covered in Parts 3, 7, and 8 of this roadmap. This section covers the telemetry types Application Insights collects, distributed tracing and the correlation model, instrumentation approaches (auto-instrumentation vs. manual SDK usage), sampling, and the Application Map visualization.

🔑 **Key Takeaway:** Application Insights answers questions Azure Monitor's generic infrastructure metrics/logs (Section 47) cannot: not just "is the VM/container healthy" but "why did this specific user's request fail, and which downstream dependency call caused it." This application-code-level, request-scoped visibility is what distinguishes APM from infrastructure monitoring — and understanding this distinction precisely is what separates genuine observability competence from infrastructure-monitoring-only familiarity.

---

## 49.2 What Is Application Insights and Why It Exists

### 49.2.1 Definition

**Plain language:** Application Insights is Azure's application-performance-monitoring service — it instruments your application code (automatically or with minimal manual code) to capture every incoming request, every outgoing call to a dependency (a database, an external API, another microservice), every exception, and custom application events, then correlates all of this into a coherent picture of exactly what happened during any individual request, end to end.

**Precise definition:** Application Insights is Azure Monitor's application-performance-monitoring (APM) feature, collecting request, dependency, exception, trace, and custom telemetry from instrumented application code, storing it in a Log Analytics workspace (in the modern workspace-based configuration) queried via KQL (Section 48), with distributed tracing correlation linking related telemetry across a request's full execution path, including across service boundaries.

### 49.2.2 Why It Exists — The Gap It Fills Beyond Section 47's Infrastructure Monitoring

- **Infrastructure health does not equal application health:** a VM or AKS pod (Section 47's metrics) can show perfectly healthy CPU/memory while the application running on it is nonetheless failing a significant fraction of user requests due to a bug, a slow downstream dependency, or an unhandled exception — infrastructure-level metrics simply don't have visibility into this application-code-level behavior at all.
- **Distributed systems need distributed tracing:** a single user-facing request in a microservices architecture (Section 35's AKS-hosted services, or a mix of App Service/Functions/AKS) may traverse multiple independent services before completing — understanding why that request was slow or failed requires correlating telemetry _across_ those service boundaries, something no single service's own isolated logs can provide in isolation; this is specifically what Application Insights' correlation model (49.4) solves.
- **Directly closing the gap flagged in Section 47.6's Container Insights discussion:** Container Insights (Section 47.6.2) provides node/pod/container-level infrastructure telemetry for AKS; Application Insights provides the complementary application-code-level telemetry for whatever is actually running _inside_ those containers — the two are complementary layers, not overlapping or redundant, directly reinforcing the "infrastructure health ≠ application health" distinction from the point above.

### 49.2.3 Terminology

| Term                      | Definition                                                                                                                                                                                                                                                                               |
| ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Telemetry**             | Any data point Application Insights collects — a request, a dependency call, an exception, a trace/log message, a custom event or metric.                                                                                                                                                |
| **Request telemetry**     | A record of an incoming request to the instrumented application (an HTTP request to a web app/API, a Functions trigger invocation) — duration, success/failure, response code.                                                                                                           |
| **Dependency telemetry**  | A record of an _outgoing_ call the application makes to another system (a SQL query, an HTTP call to another service, a call to Cosmos DB) — duration, success/failure, the target being called.                                                                                         |
| **Exception telemetry**   | A record of an unhandled (or explicitly tracked) exception, including stack trace.                                                                                                                                                                                                       |
| **Trace telemetry**       | Free-form log messages emitted by application code (the equivalent of a traditional application log line), captured alongside the other, more structured telemetry types.                                                                                                                |
| **Custom events/metrics** | Application-defined telemetry beyond the built-in types — business-relevant events (e.g., "checkout completed") or custom numeric measurements the standard telemetry types don't capture.                                                                                               |
| **Operation ID**          | A correlation identifier linking every piece of telemetry generated during the processing of a single logical operation (e.g., one incoming request and every dependency call/exception/trace that occurred while handling it) — directly referenced in Section 48.4.2's `join` example. |
| **Application Map**       | A visual, auto-generated topology diagram showing the discovered services and their call relationships, derived from correlated dependency telemetry across instrumented components.                                                                                                     |
| **Sampling**              | A mechanism reducing the volume of telemetry actually collected/stored (and therefore cost) by capturing only a representative subset of telemetry, while preserving statistically meaningful aggregate metrics (49.6).                                                                  |
| **Auto-instrumentation**  | Automatic telemetry collection requiring little to no application code changes, typically enabled via a platform-level configuration setting (e.g., an App Service/Function App setting) rather than SDK code changes.                                                                   |

---

## 49.3 Instrumentation Approaches

### 49.3.1 Auto-Instrumentation

- **Definition:** Application Insights telemetry collection enabled at the platform/hosting level (an App Service configuration setting, an AKS auto-instrumentation add-on/annotation) without requiring the application's own source code to reference the Application Insights SDK directly.
- **What it captures automatically:** incoming request telemetry, and — for many common frameworks/languages — automatically-detected dependency calls to well-known target types (SQL, HTTP, common Azure SDKs) without any manual code changes.
- **Trade-off:** minimal effort to enable, but limited to what the auto-instrumentation agent can automatically detect and correlate — custom business events, custom metrics, and fine-grained control over what gets tracked as a "dependency" for less common/custom integration types generally still require manual SDK usage (49.3.2).

### 49.3.2 Manual SDK Instrumentation

- **Definition:** explicit use of the Application Insights SDK within application code to track custom telemetry — custom events, custom metrics, explicit dependency tracking for integrations auto-instrumentation doesn't recognize, and fine-grained control over what gets captured.
- **Example (conceptual, language-agnostic pattern):**
  ```
  telemetryClient.TrackEvent("CheckoutCompleted", properties: { "OrderValue": "129.99", "PaymentMethod": "CreditCard" })
  telemetryClient.TrackDependency("CustomCache", "GetUserProfile", startTime, duration, success: true)
  ```
- **When manual instrumentation is necessary:** business-relevant custom events (which auto-instrumentation has no way to know are meaningful without being told), custom metrics beyond standard request/dependency timing, and any integration/protocol auto-instrumentation doesn't natively recognize.

### 49.3.3 Which Approach for Which Azure Service (Direct Application of Prior Roadmap Sections)

| Hosting Service                              | Instrumentation Pattern                                                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **App Service (Section 13)**                 | Auto-instrumentation available as a simple portal/configuration toggle ("Application Insights" blade), requiring no code changes for baseline request/dependency telemetry.                                                                                                                                                                                                                                                                                                                 |
| **Azure Functions (Section 38.7.3)**         | Native, built-in Application Insights integration — enabled by default in most Function App templates, automatically capturing invocation-level telemetry and, for Durable Functions specifically, the full orchestration execution history referenced in Section 38.7.3.                                                                                                                                                                                                                   |
| **AKS-hosted applications (Sections 35–37)** | Auto-instrumentation available via specific language-runtime agents/sidecar patterns (verify current AKS-specific auto-instrumentation mechanism against documentation, as this capability has evolved), or, very commonly in practice, manual SDK instrumentation within the application's own code — since AKS-hosted applications are typically custom code under full developer control, manual instrumentation is often the more natural fit compared to a PaaS platform-level toggle. |

---

## 49.4 Distributed Tracing and Correlation

### 49.4.1 The Correlation Problem

In a request spanning multiple services (a user request hits an App Service front-end, which calls an AKS-hosted API, which calls a Function, which queries Cosmos DB), each individual component's own telemetry, viewed in isolation, tells only part of the story — understanding the _end-to-end_ path, and specifically identifying which single component in that chain caused an observed slowdown or failure, requires linking all of these individually-generated telemetry records together as belonging to one logical operation.

### 49.4.2 Operation ID and the W3C Trace Context Standard

- **Operation ID (49.2.3):** a unique identifier generated for the initial incoming request, propagated forward through every subsequent dependency call the handling of that request makes — including across service boundaries, via HTTP headers automatically added and read by Application Insights' instrumentation.
- **W3C Trace Context:** the modern, standardized HTTP header format (`traceparent`, `tracestate`) Application Insights uses for this propagation, ensuring interoperability with other, non-Application-Insights-instrumented services that also implement the same open W3C standard (relevant for genuinely heterogeneous, multi-vendor-tooling architectures) — a meaningful improvement over Application Insights' own earlier, proprietary correlation header format, now aligned with a broader industry-standard distributed-tracing convention.
- **Practical consequence:** as long as every component in a request's path is Application-Insights-instrumented (or otherwise W3C-Trace-Context-compliant), the Operation ID correlates telemetry across every one of those components automatically, enabling the exact `join ... on OperationId` KQL pattern demonstrated in Section 48.4.2 to reconstruct a full end-to-end request trace from otherwise separately-generated telemetry records.

### 49.4.3 The Application Map

- **Definition:** an automatically-generated, visual topology diagram derived from correlated dependency telemetry across every instrumented component sharing the same underlying Application Insights resource (or a resource group of related resources) — showing discovered services as nodes and their observed call relationships as edges, annotated with aggregate health/performance data per edge (call volume, average duration, failure rate).
- **Why it matters operationally:** provides an immediately actionable, visual "where is the problem" starting point during an incident — a node/edge showing an elevated failure rate or latency spike visually highlights which specific service-to-service call path warrants deeper investigation, before any KQL query is even written, directly complementing the deep KQL investigative capability from Section 48 with a faster, visual first-pass triage tool.

---

## 49.5 Availability Tests

### 49.5.1 Definition

**Availability tests** (also called web tests) are synthetic, externally-originated HTTP requests Application Insights periodically sends to a specified URL (from multiple global points of presence) to verify the endpoint is reachable and responding correctly — distinct from all the telemetry types covered so far, which are generated by _real_ traffic passing through instrumented application code.

### 49.5.2 Why Synthetic Testing Matters Beyond Real-Traffic Telemetry

🔑 **Key Takeaway:** request/dependency telemetry (49.2.3) can only report on traffic that actually occurred — if an application has genuinely gone completely unreachable (a DNS failure, a networking misconfiguration, the application crashed entirely with no requests reaching it at all), there is no real traffic to generate telemetry about the outage in the first place. Availability tests solve this specific gap by originating requests _independently_ of real user traffic, providing an outside-in health signal that remains functional even when the application itself is completely down — directly enabling the alerting scenario "notify us the moment the site becomes unreachable" (Section 50), which real-traffic-dependent telemetry alone structurally cannot provide.

---

## 49.6 Sampling

### 49.6.1 Why Sampling Exists

At high request volume, capturing and storing _every single_ telemetry item (every request, every dependency call, every trace line) becomes both extremely costly (Log Analytics ingestion cost scales with data volume, Section 47.8) and, in many cases, unnecessary for the actual analytical/alerting need — most of the statistically meaningful insight (aggregate request rates, average/percentile durations, overall failure rates) can be preserved with only a representative sample of the full telemetry volume.

### 49.6.2 Sampling Types

| Type                                                                                                 | Mechanism                                                                                                                                                                                                                                | Trade-off                                                                                                                                                                                                                                                                             |
| ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Fixed-rate sampling**                                                                              | Captures a fixed percentage of all telemetry (e.g., 10%), applied at the SDK level                                                                                                                                                       | Simple, predictable cost reduction; aggregate metrics remain statistically representative, but any single specific request/exception has only a 10% chance of being captured, potentially missing the exact instance needed to diagnose a rare, specific issue                        |
| **Adaptive sampling**                                                                                | Automatically adjusts the sampling rate to target a configured telemetry volume, increasing the rate during low-traffic periods and decreasing it during high-traffic bursts                                                             | The generally recommended default for most production applications — balances cost control against not over-suppressing telemetry during genuinely low-volume periods where full capture would be cheap and valuable anyway                                                           |
| **Ingestion sampling (at the Application Insights resource level, distinct from SDK-side sampling)** | Applied at the ingestion endpoint rather than within the application's own SDK, reducing the _volume actually processed and billed_, but after the application has already generated and sent the full telemetry volume over the network | Useful when SDK-level sampling configuration isn't feasible/available, but doesn't reduce the network/CPU cost of the application generating and sending the un-sampled volume in the first place — a real, specific distinction from SDK-side sampling worth understanding precisely |

⚠️ **Warning:** because correlated telemetry (49.4) must be sampled _consistently_ for an entire operation to remain meaningfully correlate-able (sampling a request's telemetry in but its corresponding exception telemetry out would break the correlation), Application Insights' sampling algorithms are specifically designed to sample entire correlated operations together (all-or-nothing per Operation ID) rather than sampling individual telemetry items independently — a subtle but important correctness detail distinguishing Application Insights' sampling from a naive "randomly drop X% of telemetry items" approach that would otherwise silently corrupt the very distributed-tracing correlation capability (49.4) that is Application Insights' core value proposition.

---

## 49.7 Production and Enterprise Usage

### 49.7.1 Workspace-Based vs. Classic Application Insights

- Modern Application Insights resources are **workspace-based** — storing their telemetry directly within a Log Analytics workspace (Section 47–48), rather than the legacy "classic" model's separate, dedicated storage — directly unifying Application Insights data with the rest of an organization's Azure Monitor log data for combined querying (e.g., correlating application-level exception telemetry with infrastructure-level resource logs from the same workspace, in a single KQL query) and consistent RBAC/retention management, superseding the older classic model (verify exact current migration/deprecation status of classic Application Insights against documentation, as Microsoft has been actively transitioning customers toward the workspace-based model).

### 49.7.2 Live Metrics

- **Live Metrics** provides a near-real-time (sub-second latency, in contrast to the several-minutes-typical ingestion latency of standard telemetry queried via KQL) streaming view of key metrics (request rate, failure rate, CPU/memory) — specifically valuable during an active deployment (validating a canary/blue-green rollout's immediate health, Section 46.3) or an active incident, where even a few minutes of standard telemetry latency is operationally significant.

### 49.7.3 Cost Management

- Directly extending Section 47.8's Log Analytics cost discussion: Application Insights telemetry volume, especially trace-level logging at high verbosity across a high-traffic application, can become a very substantial fraction of an organization's total Log Analytics ingestion cost — sampling (49.6) is the primary lever for managing this, and a deliberate, reviewed sampling configuration (rather than an unconsidered default) is a genuine, recurring cost-optimization practice specific to APM telemetry.

---

## 49.8 Troubleshooting Reference

| Symptom                                                                                                                  | Likely Cause                                                                                                                                                                                                                                                           | Diagnostic Step                                                                                                                                                  |
| ------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A specific failed request has no corresponding exception telemetry despite the application clearly throwing an exception | Sampling excluded that specific operation (49.6.2), or the exception was caught/swallowed by application code without being explicitly tracked via `TrackException`                                                                                                    | Review sampling configuration/rate; verify application code explicitly tracks caught exceptions if silent handling is intentional but visibility is still needed |
| Application Map shows a service as disconnected/missing from the expected topology                                       | That service isn't instrumented, or is instrumented but not propagating/receiving W3C Trace Context correlation headers correctly (e.g., a non-Application-Insights-aware intermediary stripping headers)                                                              | Verify instrumentation is enabled on the missing service; check whether any intermediary (a gateway, proxy) might be stripping correlation headers in transit    |
| Availability test reports failures but real user traffic and request telemetry look healthy                              | A genuine environment-specific issue affecting the synthetic test's specific originating locations/network path but not real user traffic's path, or an availability test configuration issue (wrong URL, expired test credential if the test requires authentication) | Review which specific test locations are failing; verify the tested URL/configuration is current and correct                                                     |
| Telemetry volume/cost far higher than expected                                                                           | No sampling configured, or sampling configured at a higher rate than actually needed for the application's analytical/alerting requirements                                                                                                                            | Review current sampling configuration (49.6.2); consider adaptive sampling if not already in use                                                                 |
| Correlated `join` query (Section 48.4.2 pattern) returns fewer matches than expected between requests and exceptions     | Sampling excluded one side of the correlated pair inconsistently (should not normally happen given 49.6's all-or-nothing-per-operation sampling design, but worth verifying), or the exception genuinely wasn't tracked at all for that operation                      | Confirm sampling is functioning as designed (consistent per-operation); check whether the specific exception path is actually being tracked by application code  |

---

## 49.9 Best Practices Checklist

- [ ] Auto-instrumentation enabled as a baseline for every supported hosting service (App Service, Functions), with manual SDK instrumentation added specifically for custom business events/metrics.
- [ ] Distributed tracing correlation verified end-to-end across every service in a multi-service request path, confirmed via the Application Map showing the expected full topology.
- [ ] Availability tests configured for any externally-facing, business-critical endpoint, providing outside-in health signal independent of real traffic.
- [ ] Adaptive sampling configured deliberately (rather than left at an unconsidered default) for high-traffic production applications, balancing cost against retained diagnostic detail.
- [ ] Workspace-based Application Insights configuration used for new resources, unifying APM data with the rest of the organization's Azure Monitor log data.
- [ ] Live Metrics used during active deployments/incidents specifically, where standard telemetry's typical multi-minute ingestion latency is operationally significant.
- [ ] Application code explicitly tracks caught/handled exceptions where visibility is still operationally needed, not relying solely on unhandled-exception auto-capture.

---

## 49.10 Common Misconceptions

- "Healthy infrastructure metrics (Section 47) mean the application is healthy." _Correction:_ this is the core distinction motivating Application Insights' existence (49.2.2) — infrastructure health and application-code-level health are genuinely separate concerns, and an application can be failing user requests while its underlying infrastructure metrics look entirely normal.
- "Sampling means some requests are silently, inconsistently missing pieces of their telemetry (a request captured but its exception dropped, or vice versa)." _Correction:_ Application Insights' sampling is specifically designed to sample entire correlated operations together, preserving correlation integrity — a request and its associated exception/dependency telemetry are sampled in or out together as a unit, not independently (49.6's warning).
- "Real user request/dependency telemetry is sufficient to detect a complete application outage." _Correction:_ if the application is entirely unreachable, there is no real traffic generating telemetry about that fact — availability tests (49.5) exist specifically to provide an independent, outside-in signal for exactly this scenario.

---

## 49.11 Interview Questions (Consolidated)

**Beginner:** "What is the difference between request telemetry and dependency telemetry in Application Insights?"
_Model answer:_ request telemetry records incoming requests _to_ the instrumented application (e.g., an HTTP request a web API receives), including its duration and success/failure. Dependency telemetry records outgoing calls the application makes _to_ other systems while handling that request (a database query, an HTTP call to another service) — the two together provide both sides of the picture: what came in, and what the application did in response while processing it.

**Intermediate:** "Explain how Application Insights correlates telemetry across multiple services in a distributed request path."
_Model answer:_ every incoming request is assigned an Operation ID, propagated forward through every subsequent dependency call the handling of that request triggers — including across service boundaries — via standardized W3C Trace Context HTTP headers (`traceparent`/`tracestate`) that Application Insights' instrumentation automatically adds to outgoing calls and reads from incoming calls. As long as every service in the request's path is instrumented (or otherwise W3C-Trace-Context-compliant), all the telemetry generated across every one of those services during the handling of that one logical request shares the same Operation ID, enabling it to be correlated together — for example via a KQL `join ... on OperationId` query — to reconstruct the full end-to-end path.

**Senior:** "A team reports that during a recent incident, they could see in their App Service metrics (Section 47) that request latency spiked, but had no visibility into which specific downstream call was actually responsible for the slowdown. What was missing, and how would you fix it?"
_Model answer:_ Section 47's infrastructure-level metrics can show _that_ something was slow (aggregate request latency) but have no visibility into application-code-level detail like which specific dependency call within request handling was the actual bottleneck — this is exactly the gap Application Insights' dependency telemetry (49.2.3) exists to close. The fix is ensuring Application Insights is properly instrumented (auto-instrumentation at minimum, manual SDK instrumentation for any dependency types auto-instrumentation doesn't recognize, per 49.3.3's App Service guidance) so that dependency telemetry captures the duration of every outgoing call the application makes, allowing a query correlating slow requests with their corresponding dependency telemetry (the Section 48.4.2 `join ... on OperationId` pattern) to precisely identify which specific downstream dependency call was actually responsible for the observed latency spike, rather than only knowing that the request as a whole was slow.
_What the interviewer is probing:_ precise recognition of the infrastructure-monitoring-vs-APM gap (49.2.2) as the actual root cause of the described visibility gap, and the ability to name the specific fix (dependency telemetry plus correlation) rather than a vague "add more monitoring."

**Architect / Scenario:** "Design an observability instrumentation strategy for a system spanning an App Service front-end, an AKS-hosted API layer, and Azure Functions for background processing, with a requirement to trace a single user checkout operation end-to-end across all three, while managing telemetry cost at scale."
_Model answer:_ enable Application Insights auto-instrumentation on the App Service front-end (49.3.3, minimal-effort baseline coverage) and rely on Functions' native, built-in Application Insights integration (49.3.3) for the background-processing layer. For the AKS-hosted API layer, use manual SDK instrumentation within the application code (49.3.3's noted AKS pattern), ensuring the SDK is configured to correctly propagate and honor W3C Trace Context headers (49.4.2) so that telemetry generated in AKS correctly correlates via Operation ID with the telemetry from the App Service front-end that called into it and any Function the AKS service subsequently triggers — verifying this end-to-end correlation is actually working correctly via the Application Map (49.4.3), which should show all three layers connected as one coherent topology for a genuinely working configuration. For cost management at scale, configure adaptive sampling (49.6.2) rather than fixed-rate or no sampling, since adaptive sampling's traffic-responsive behavior avoids over-suppressing telemetry during lower-traffic periods while still controlling cost during traffic spikes — and rely on 49.6's all-or-nothing-per-operation sampling design to ensure that even with sampling active, any given checkout operation that _is_ sampled in still has its complete, correlated cross-service trace preserved intact (rather than sampling introducing gaps within an individual traced operation), directly satisfying the "trace a single checkout operation end-to-end" requirement even under active sampling.
_What the interviewer is probing:_ the ability to design a coherent, multi-service instrumentation strategy correctly matching instrumentation approach to each specific hosting service (49.3.3), while simultaneously addressing the stated cost-management requirement using the correct mechanism (adaptive sampling) and correctly explaining why sampling doesn't compromise the specific end-to-end tracing requirement given Application Insights' per-operation sampling design.

---

## 49.12 Key Takeaways Summary

🔑 Application Insights closes the specific gap infrastructure-level Azure Monitor metrics/logs (Section 47) cannot: application-code-level, request-scoped visibility into what actually happened during individual requests, including across distributed service boundaries.

🔑 Operation ID and W3C Trace Context propagation are the mechanism enabling distributed tracing correlation — telemetry generated across multiple, independently-instrumented services during one logical request shares a common correlation identifier, enabling reconstruction of the full end-to-end path.

🔑 Availability tests provide an outside-in health signal independent of real traffic, specifically covering the scenario (complete application unreachability) that real-traffic-dependent telemetry structurally cannot detect.

🔑 Application Insights' sampling is specifically designed to preserve per-operation correlation integrity (sampling entire correlated operations together, not individual telemetry items independently) — a critical, non-obvious design detail distinguishing it from naive random sampling.

🔑 Instrumentation approach (auto vs. manual SDK) should be matched deliberately to each specific hosting service's actual capabilities and the application's custom-telemetry needs, not treated as a single one-size-fits-all choice across a heterogeneous, multi-service architecture.

---

## 49.13 Related Concepts and What Comes Next

- **Section 47–48 (prerequisite, completed):** the Azure Monitor data model and KQL query capability this section's telemetry types and correlation model are stored in and queried through directly.
- **Section 50 — Alerts, Action Groups, Dashboards (next):** where this section's telemetry (and Section 48's KQL queries against it) becomes the actual trigger condition for automated alerting, and where the Application Map and Live Metrics (49.4.3, 49.7.2) connect to persistent Dashboards.
- **Section 38.7.3 (prerequisite, completed):** Azure Functions' native Application Insights integration, referenced directly in 49.3.3.
- **Section 46.3.4/46.9 (prerequisite, completed):** canary deployment's version-specific monitoring requirement, directly satisfiable using Application Insights' request/dependency telemetry split by deployment version/release annotation.
- **Section 51 — Azure Advisor (upcoming):** provides platform-level recommendations that can include Application Insights configuration/cost-optimization suggestions, connecting this section's material to that upcoming, broader recommendations-engine topic.

---

_End of Section 49. Next: Section 50 — Alerts, Action Groups, Dashboards._
