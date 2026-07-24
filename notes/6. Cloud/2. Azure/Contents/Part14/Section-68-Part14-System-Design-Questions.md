# Section 68 — System Design Questions (Azure-Based)

**Part 14: Interview Preparation & Wrap-Up | Section 68 of 70**
**Prerequisites:** Section 66 (Real-World Enterprise Case Studies), Section 67 (Consolidated Interview Question Bank)
**Leads into:** Section 69 (Hands-On Labs & Mini-Projects)

---

## 68.1 Introduction and Purpose

This section provides five complete, dedicated system-design interview scenarios — the format most commonly used in senior/staff/principal-level cloud engineering and architecture interviews — with a structured approach for tackling any Azure system-design question, full walkthrough solutions, and explicit likely-follow-up-question preparation. Unlike Section 66's case studies (illustrative, narrative-driven), this section is structured specifically around the interview *format*: a prompt, a time-boxed reasoning approach, a structured answer, and anticipated probing follow-ups.

🔑 **Key Takeaway:** system design interviews evaluate the *process* of arriving at an architecture at least as much as the final answer — explicitly stating assumptions, asking clarifying questions where genuinely ambiguous, walking through trade-offs out loud, and being able to defend/adjust the design under follow-up pressure are all part of what's being assessed, not merely whether the final diagram is "correct." This section's structured approach directly trains that process.

---

## 68.2 A Structured Approach to Any Azure System Design Question

### 68.2.1 The Five-Step Framework

1. **Clarify requirements and constraints** — ask about scale (users, requests/sec, data volume), latency requirements, consistency requirements, budget constraints, compliance/regulatory requirements, and team/organizational constraints (existing tooling, skill investment per Section 65.5.2) — never assume; state explicitly what you're assuming if the interviewer doesn't specify.
2. **Identify the core architectural decisions** — compute model (Section 33.11.1's comparison), data storage/consistency model, networking/security posture, and the HA/DR tier appropriate to stated criticality (Section 57.7.1's differentiated-investment principle).
3. **Design the happy path first, then layer in resilience/security/observability** — get a working baseline architecture established before adding HA/DR, security hardening, and monitoring, then explicitly walk through adding each layer with its specific justification.
4. **State trade-offs explicitly, out loud** — for every non-obvious decision, name the alternative(s) considered and why the chosen option won given the stated requirements — this is the single most important habit distinguishing strong from weak system-design performance.
5. **Anticipate and prepare for follow-ups** — scaling beyond initial assumptions, a specific failure-mode walkthrough, and a cost-estimate sanity check are the three most common follow-up categories across virtually every Azure system-design interview.

---

## 68.3 Scenario 1: Design a URL Shortener Service

### 68.3.1 Prompt

"Design a URL shortening service (like bit.ly) on Azure, expected to handle 100 million shortened URLs with a 100:1 read-to-write ratio, requiring sub-100ms redirect latency globally."

### 68.3.2 Clarifying Questions (Step 1)

- Do shortened URLs expire, or persist indefinitely? (Affects storage/retention strategy.)
- Is analytics (click tracking) required? (Affects whether this is a pure redirect service or needs an event-ingestion pipeline.)
- Global user base, or specific regions? (Directly affects the multi-region/Front-Door decision.)

### 68.3.3 Structured Solution

- **Compute:** Azure Functions (Section 38) with HTTP triggers — the redirect operation is a simple, stateless, high-read-volume operation ideally suited to Consumption-plan's automatic scaling (Section 38.3.2), though Premium plan (Section 38.3.3) is justified here specifically given the stated sub-100ms latency requirement, since Consumption's cold start (Section 38.4) risks violating that SLA for infrequently-hit shortened URLs.
- **Data store:** Cosmos DB (Section 29) chosen over SQL Database specifically because the access pattern (simple key lookup by short-code, extremely high read volume, no complex relational queries needed) is an ideal fit for Cosmos DB's key-value access pattern and native multi-region distribution — directly connecting to the stated global-latency requirement via Cosmos DB's multi-region read replica capability, avoiding the cross-region latency a single-region SQL Database would introduce for globally distributed users.
- **Global distribution:** Azure Front Door (Section 25) in front of regional Function App deployments, providing both the CDN-level caching benefit (a redirect response can be cached at the edge for a given short-code) and global routing to the nearest healthy region.
- **Write path:** short-code generation (a counter-based or hash-based approach) writes to Cosmos DB, with the specific generation algorithm choice (a system-design detail beyond this roadmap's Azure-service-selection focus) noted as a distinct algorithmic decision separate from the Azure architecture itself.

### 68.3.4 Explicit Trade-offs Stated

- Cosmos DB over SQL Database: chosen for global distribution and simple key-value access pattern fit, at the cost of Cosmos DB's different consistency model considerations (Section 29) compared to SQL's familiar relational guarantees — acceptable here since the access pattern doesn't require relational query capability.
- Functions over App Service: chosen for the stated 100:1 read-skewed, potentially bursty traffic pattern's fit with consumption-based elastic scaling (Section 38.2.2), accepting Premium-plan cost over Consumption specifically to satisfy the stated latency SLA.

### 68.3.5 Anticipated Follow-Ups

- **"How would you add click analytics without impacting redirect latency?"** — Event Hubs (Section 40.4) ingesting a fire-and-forget click event asynchronously from the redirect Function, decoupling analytics ingestion from the latency-critical redirect path — directly applying Section 40.2.2's "why three services" reasoning (Event Hubs specifically for this high-volume streaming-ingestion pattern, not Service Bus or Event Grid).
- **"What happens if Cosmos DB becomes unavailable in one region?"** — Cosmos DB's multi-region configuration with automatic failover (Section 29) handles this; the Function App's connection configuration must correctly implement retry/failover logic against Cosmos DB's SDK-provided region-failover capability.

---

## 68.4 Scenario 2: Design a Real-Time Chat Application Backend

### 68.4.1 Prompt

"Design the backend for a real-time chat application supporting 1 million concurrent users, requiring message delivery within 200ms and message history persistence."

### 68.4.2 Clarifying Questions

- Group chats or only 1:1? (Affects fan-out complexity.)
- Message ordering guarantees required? (Directly connects to Section 40.5.4's Service Bus Sessions material.)
- Is this greenfield, or integrating with an existing user/auth system? (Affects Entra ID/B2C decision.)

### 68.4.3 Structured Solution

- **Real-time connection layer:** Azure Web PubSub (a real-time messaging service not yet explicitly covered elsewhere in this roadmap, functioning conceptually as a managed WebSocket/real-time-connection service) or, alternatively, SignalR Service — providing the persistent, low-latency connection layer to connected clients, a genuinely different requirement from this roadmap's HTTP-request/response-focused compute services (Sections 13, 38), worth explicitly naming as requiring a specifically real-time-connection-oriented service rather than forcing a standard HTTP API to serve this role.
- **Message routing/fan-out:** Service Bus Topics (Section 40.5.3) for group-chat message fan-out to multiple subscribers, with **Sessions** (Section 40.5.4) enabled specifically to guarantee per-conversation message ordering — directly applying Section 40.6.2's exact "Service Bus for reliable, ordered business messaging" decision-tree outcome, since chat message ordering is precisely the kind of requirement that rules out Event Grid's lighter-weight, non-ordering-guaranteed model.
- **Message persistence:** Cosmos DB (Section 29) for message history, chosen for its horizontal write scalability matching the stated 1-million-concurrent-user write volume, with a partition key design (conversation ID) directly informed by Section 29's data-modeling material.
- **Presence/connection state:** Azure Cache for Redis (Section 31) for tracking which users are currently connected/online, given Redis's low-latency key-value access pattern fit for this specific, frequently-read-and-updated state.

### 68.4.4 Explicit Trade-offs Stated

- Service Bus over Event Grid for message routing: chosen specifically for ordering guarantees (Sessions) and reliable delivery semantics chat messages require, accepting Service Bus's somewhat higher operational complexity over Event Grid's lighter-weight model, directly justified by the stated ordering requirement.
- Redis over Cosmos DB for presence state: chosen for Redis's lower-latency access pattern specifically suited to frequently-changing, ephemeral state, versus Cosmos DB's stronger fit for durable, persisted message history — two different data stores for two genuinely different access patterns within the same system, rather than forcing one store to serve both roles suboptimally.

### 68.4.5 Anticipated Follow-Ups

- **"How would you handle a user connected to a different region than their conversation partner?"** — directly connects to Section 40.4.2's consumer-group model and Section 29's multi-region Cosmos DB material — the real-time connection layer's regional presence must be reconciled with the message-routing layer's cross-region delivery capability, a genuine, non-trivial distributed-systems challenge worth acknowledging explicitly rather than hand-waving.
- **"What's your strategy if Service Bus experiences a regional outage?"** — directly applies Section 57.2.4's HA-vs-DR distinction: Service Bus's own zone-redundancy (within-region HA) handles routine failures, while a genuine regional outage requires the DR pattern spectrum (Section 57.6.1) applied to this specific messaging-layer component.

---

## 68.5 Scenario 3: Design a Video Streaming Platform's Upload/Encoding Pipeline

### 68.5.1 Prompt

"Design the backend pipeline for a video-streaming platform's upload and encoding process: users upload raw video files, which must be encoded into multiple resolutions/bitrates and made available for streaming, at a scale of 10,000 uploads per day, with encoding typically taking several minutes per video."

### 68.5.2 Structured Solution

- **Upload target:** Blob Storage (Section 17) directly, using a client-side direct-to-Blob-Storage upload pattern (via a SAS token, avoiding routing large file uploads through an application server as an unnecessary bottleneck) — a specific, standard Blob Storage usage pattern worth naming explicitly for a large-file-upload scenario.
- **Encoding trigger:** an Event Grid-based Blob-created event (Section 40.3.3, directly reusing the exact "near-real-time Blob trigger" pattern established in Section 38.5.4/40.3.3) triggers the encoding workflow the moment an upload completes.
- **Encoding orchestration:** given the stated "several minutes per video" processing duration, this is a genuinely long-running, multi-step workflow (encode to multiple resolutions, potentially in parallel) — directly matching **Durable Functions'** fan-out/fan-in pattern (Section 38.6.3) exactly: an orchestrator function triggered by the upload event fans out to parallel activity functions each handling one target resolution/bitrate encoding, fanning back in once all complete to finalize the video's availability.
- **Actual encoding compute:** the encoding activity functions themselves likely delegate to a specialized media-encoding service (outside this roadmap's specific coverage, as Azure Media Services-equivalent capability is a specialized area) or to a containerized encoding job — if containerized, Azure Container Instances (Section 15) is a strong fit specifically because encoding jobs are short-lived (compared to a long-running service), bursty (matching ACI's per-invocation billing), and don't need Kubernetes' orchestration overhead for this specific batch-style workload.
- **Output storage:** encoded outputs written to a separate Blob Storage container/tier, with lifecycle management (Section 17) potentially moving older, less-frequently-streamed content to Cool tier over time.

### 68.5.3 Explicit Trade-offs Stated

- Durable Functions over Logic Apps for orchestration: chosen specifically because the encoding workflow, while it has a clear fan-out/fan-in shape (which either service could express), likely also requires the kind of custom, algorithmic logic (Section 39.6.3's decision framework) that fits Functions' code-first model better than Logic Apps' connector-driven model, particularly for any custom encoding-parameter logic.
- ACI over AKS for encoding compute: chosen specifically because encoding jobs are bursty, short-lived, and don't require Kubernetes' orchestration capability for what is fundamentally a batch job pattern (Section 33.11.1's comparison table), avoiding AKS's higher baseline operational complexity for a workload that doesn't need it.

### 68.5.4 Anticipated Follow-Ups

- **"How would you handle an encoding job that fails partway through?"** — directly applies Section 38.6.4's orchestrator-determinism and exception-handling material, and Section 40.5.4's dead-lettering concept if a queue-based retry mechanism is layered in for encoding job failures specifically.
- **"How would you estimate and control the cost of this pipeline at scale?"** — directly connects to Section 60's cost-optimization material: ACI's per-invocation billing model fits this bursty workload's cost profile well, and Section 61.2.4's capacity-forecasting practice would inform whether the 10,000-uploads/day figure justifies evaluating a Reserved-capacity alternative for encoding compute specifically, if that volume proves large and steady enough.

---

## 68.6 Scenario 4: Design a Multi-Region, Highly Available E-Commerce Order Processing System

### 68.6.1 Prompt

"Design the order-processing backend for a multi-region e-commerce platform requiring each order to be processed exactly once, in the order received per customer, with a defined RTO of 15 minutes and RPO of 1 minute."

### 68.6.2 Structured Solution — Direct, Explicit Reuse of This Roadmap's Recurring Example

🔑 This prompt is directly, deliberately structured as this roadmap's own recurring revenue-critical checkout-service example (Sections 46, 57, 58, 59) — the strongest possible answer explicitly recognizes and states this, then applies the accumulated reasoning from those sections directly:

- **Message ordering/exactly-once processing:** Service Bus Queue with **Sessions** (grouping all events for a given order/customer ID) and **Transactions** (Section 40.5.4), directly reusing the exact decision from Section 40.6.2's decision-framework table for this precise scenario shape.
- **Compute:** AKS (Section 35–37), chosen for the multi-tier order-processing application's orchestration needs, with the Deployment/replica-count and Pod Disruption Budget configuration (Section 36.4.4) specifically tuned to support the stated 15-minute RTO's upgrade/failover-tolerance requirements (Section 37.2.3).
- **Data layer:** SQL Database with **geo-replication/failover groups** (Section 28.15) — the specific RPO of 1 minute requires verifying the failover group's actual achievable replication lag against this target, directly applying Section 58.6.1's architect-scenario reasoning that database-layer replication configuration, not the DR orchestration layer alone, is what actually determines achieved RPO.
- **DR orchestration:** given the 15-minute RTO and AKS-hosted architecture, GitOps-based cluster reconstruction (Section 46.4, Section 58.2.5's specific AKS-ASR-gap guidance) in the secondary region, combined with the SQL failover group above — with **capacity/quota pre-verified** in the secondary region (Section 61.5.1's explicitly-named gap) as a prerequisite to actually achieving the stated RTO under a genuine failover.
- **Deployment strategy:** canary (Section 46.3.4), directly reusing the established justification for this exact revenue-critical profile.

### 68.6.3 Explicit Trade-offs Stated

- This solution explicitly reuses and cites the prior reasoning from Sections 46/57/58/59/61 rather than re-deriving it from scratch — in an actual interview, explicitly saying "this matches a pattern I've reasoned through before: [specific justification]" is a legitimate, strong signal of genuine understanding, not a weakness, provided the underlying reasoning is actually sound and correctly applied to the specific stated numbers (15-minute RTO, 1-minute RPO) rather than generically asserted.

### 68.6.4 Anticipated Follow-Ups

- **"What if the RTO requirement were 30 seconds instead of 15 minutes?"** — this would push the design toward **active-active** (Section 57.6.1's spectrum, Section 66.3.3's Case Study 2 example) rather than the warm-standby-style GitOps reconstruction approach, since 15 minutes' worth of reconstruction/scale-out time would violate a 30-second target — a genuine, correct escalation up the DR pattern spectrum in response to a tightened requirement, worth being able to articulate precisely.
- **"How do you validate the 1-minute RPO is actually being met on an ongoing basis?"** — directly connects to Section 58.5.3's testing-cadence material and Section 47's monitoring material: the SQL failover group's actual replication lag should itself be monitored (a metric, Section 47.3.1) with an alert (Section 50) if it exceeds the 1-minute target, providing continuous validation rather than only point-in-time DR-test validation.

---

## 68.7 Scenario 5: Design a Data Analytics Platform for IoT Sensor Data

### 68.7.1 Prompt

"Design a platform ingesting telemetry from 1 million IoT sensors, each reporting every 10 seconds, requiring real-time dashboards, historical trend analysis, and anomaly alerting."

### 68.7.2 Structured Solution

- **Ingestion:** Event Hubs (Section 40.4) — this is the textbook Event Hubs use case directly named in Section 40.6.2's decision framework: massive-volume streaming telemetry requiring multiple independent downstream consumers (real-time dashboard vs. historical analytics) reading the same stream at their own pace via separate **consumer groups** (Section 40.4.2).
- **Partition count planning:** given 1 million sensors reporting every 10 seconds (100,000 events/sec aggregate), partition count must be sized deliberately per Section 40.4.4's specific capacity-planning warning, since this is exactly the kind of high-throughput scenario where under-provisioning partition count becomes a real, hard-to-fix-later bottleneck.
- **Real-time dashboard consumer:** a consumer group feeding Azure Monitor/a custom real-time visualization (or, if within this roadmap's explicit scope, Application Insights-adjacent Live Metrics-style near-real-time visualization, Section 49.7.2) reading near the current stream tip.
- **Historical analytics consumer:** a separate consumer group feeding into long-term storage (Blob Storage, Section 17, potentially with lifecycle tiering) for historical trend analysis, queryable via a data-analytics service — this specific requirement (large-scale historical analytical querying) points toward a dedicated data-warehouse-style service (noted, per Section 65.2's comparison table, as an area — Synapse Analytics — not yet covered in explicit depth in this roadmap, flagged honestly rather than glossed over).
- **Anomaly alerting:** an Azure Function (Section 38.5.3's Event Hub trigger) or Stream Analytics-style processing (also noted as outside this roadmap's current explicit-depth scope) consuming the stream and applying anomaly-detection logic, feeding into Azure Monitor alert rules (Section 50) with a dynamic-threshold or KQL-based anomaly-detection approach (Section 48.5.3's `series_decompose_anomalies()`) for the alerting logic itself.

### 68.7.3 Explicit Trade-offs Stated and Honest Scope Acknowledgment

- This scenario deliberately surfaces a genuine roadmap-scope boundary: real-time stream-processing services (Azure Stream Analytics) and dedicated data-warehouse services (Synapse Analytics) were noted in Section 65.2's comparison table but not covered in their own dedicated roadmap sections — the honest, correct interview approach here is explicitly naming this gap ("this would typically involve Stream Analytics or Synapse Analytics for this specific piece, which I'd want to research the current specifics of") rather than fabricating confident-sounding but unverified details about services outside this roadmap's actual covered depth — directly modeling Section 15's anti-hallucination principle in an interview-simulation context specifically.

### 68.7.4 Anticipated Follow-Ups

- **"How would you handle a sudden 10x increase in sensor count?"** — directly connects to Section 40.4.4's partition-count scaling limitation and Section 59's autoscaling material — Event Hubs partition count is a genuine, harder-to-scale-reactively bottleneck than most other components in this design, worth flagging explicitly as the component requiring the most proactive capacity planning (Section 61.2.4) for this specific growth scenario.

---

## 68.8 Key Takeaways Summary

🔑 System design interviews evaluate reasoning process (clarifying questions, explicit trade-off articulation, structured escalation from happy-path to full resilience/security) at least as much as the final architecture.

🔑 Explicitly recognizing when a prompt matches a previously-reasoned-through pattern (as in Scenario 4's direct reuse of this roadmap's recurring checkout-service example) is a legitimate strength, not a weakness, provided the reasoning is genuinely, correctly applied to the specific new numbers/constraints given.

🔑 Honestly acknowledging a scope boundary (Scenario 5's Stream Analytics/Synapse gap) is stronger interview practice than fabricating confident but unverified detail — directly modeling this roadmap's own anti-hallucination discipline under interview pressure specifically.

🔑 Every scenario in this section drew on multiple, different Parts of this roadmap simultaneously (compute + data + networking + resilience + cost), reinforcing Section 66.5.1's "no genuine architectural exercise is single-topic" principle one final time in interview-specific format.

---

## 68.9 Related Concepts and What Comes Next

- **Section 66 (prerequisite, completed):** the case-study format this section's structured scenarios directly extend into interview-specific practice.
- **Section 67 (prerequisite, completed):** the consolidated question bank this section's five scenarios draw their component reasoning from.
- **Section 69 — Hands-On Labs & Mini-Projects (next):** provides practical, hands-on exercises for building toward genuine implementation fluency with the services this section's scenarios reasoned about architecturally.
- **Section 70 — Key Takeaways Checklist & Recommended Next Topics (final section):** the roadmap's concluding wrap-up.

---

*End of Section 68. Next: Section 69 — Hands-On Labs & Mini-Projects.*
