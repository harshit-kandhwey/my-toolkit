# Part 10, Section 8: AWS System Design — End-to-End Architecture Walkthroughs

## 1. Definition

**Plain language:** This section is where every prior Part comes together. Rather than teaching a new service or framework, it walks through two complete, realistic system designs from a cold requirement statement to a full architecture — the exact exercise a FAANG-style "design a system for X" interview actually looks like — explicitly narrating which service from which Part solves which requirement, and why.

**Precise definition:** This section demonstrates applied AWS system design methodology: gathering and clarifying requirements, identifying the core architectural challenges, selecting specific services from across this roadmap to address each challenge, and explicitly justifying trade-offs using the Well-Architected Framework (Part 10 §1) — modeling the reasoning process a system design interview is actually evaluating, not just the final diagram.

## 2. Why This Exercise Exists / Problem It Solves

Every prior section taught services and patterns largely in isolation or in small, focused combinations (an SQS+Lambda pipeline, a CloudWatch alarm on a specific metric). Real system design — and real system design interviews — require synthesizing dozens of these individual pieces of knowledge into one coherent, end-to-end architecture under time pressure, while explicitly articulating trade-offs. This is a genuinely different skill than knowing each piece individually, and it's the skill most senior/staff-level interviews are actually testing. This section exists to model that synthesis explicitly, rather than leaving the reader to independently figure out how to combine 80+ sections of prior material into one coherent design.

## 3. A General System Design Methodology

1. **Clarify requirements** — functional (what must the system do), non-functional (scale, latency, availability, consistency requirements), and constraints (budget, team size, compliance).
2. **Identify the core architectural challenges** — usually 2-4 genuinely hard problems specific to this system (e.g., "how do we guarantee exactly-once payment processing," not generic "how do we use AWS").
3. **Sketch the high-level data/request flow** before diving into specific services.
4. **Select specific services per component**, explicitly justifying each choice against alternatives (this is where Part 7 §9's and Part 9 §9's decision frameworks directly apply).
5. **Address cross-cutting concerns**: security (Part 2, Part 8 §5-6), observability (Part 8 §1-4), deployment (Part 9), and cost (Part 10 §2).
6. **Explicitly state trade-offs** using Well-Architected pillar language (Part 10 §1).

## 4. Worked Example 1 — Real-Time Order Processing Platform

**Requirement statement:** "Design an order processing system for an e-commerce platform. Orders must never be lost. Inventory and fraud checks must happen for every order. The system must handle Black Friday-level traffic spikes (50x normal volume) without falling over, and the team needs full visibility into what happens to every order."

**Step 1 — Clarify:** Functional: accept orders, check inventory, screen for fraud, fulfill or reject. Non-functional: no order loss (durability), massive traffic elasticity, full auditability. Assume moderate consistency tolerance (eventual consistency across inventory/fraud checks is acceptable; the _order itself_ must never be lost).

**Step 2 — Core challenges:** (a) absorbing a 50x traffic spike without dropping orders, (b) coordinating multiple independent checks (inventory, fraud) reliably, (c) end-to-end visibility for debugging and audit.

**Step 3-4 — Architecture and service selection:**

- **Ingestion**: API Gateway → Lambda (Part 3) accepting the order request, immediately publishing to an **SQS queue** (Part 7 §1) rather than processing synchronously — this is the direct answer to the traffic-spike requirement: SQS absorbs the 50x burst by buffering, decoupling the _rate orders arrive_ from the _rate they're processed_, so a traffic spike becomes a temporarily deeper queue rather than a cascading failure.
- **Fan-out**: the queue's messages trigger an **SNS→SQS fan-out** (Part 7 §3) to separate inventory-check and fraud-check queues, each with its own DLQ (Part 7 §2) — each check is independent, durably buffered, and independently retryable, directly addressing challenge (b).
- **Orchestration**: a **Step Functions Standard workflow** (Part 7 §5) coordinates the overall sequence — wait for both checks, branch on the combined result, fulfill or reject — chosen specifically for its full execution history, directly serving the auditability requirement (challenge (c)) far better than a scattered collection of independent Lambda triggers would.
- **Observability**: every Lambda has **X-Ray Active Tracing** enabled (Part 8 §4) with a consistent order-ID annotation, letting any specific order be traced end-to-end across every hop; **CloudWatch alarms** (Part 8 §3) on `ApproximateAgeOfOldestMessage` for every queue, composited (Part 8 §3) so a genuinely correlated multi-signal problem pages on-call urgently while a single noisy signal doesn't.
- **Durability**: every queue has a DLQ; the Step Functions Standard workflow's exactly-once execution semantics plus idempotent Lambda logic (using the order ID as an idempotency key) directly addresses the "orders must never be lost" requirement even under SQS's at-least-once delivery model (Part 7 §1).
- **Deployment**: the entire stack defined in **CDK** (Part 9 §3), chosen over raw CloudFormation for the team's ability to unit-test the Step Functions definition logic, deployed via a **CI/CD pipeline** (Part 9 §8) with a production approval gate.

**Step 5 — Trade-offs (Well-Architected framing):** This design trades some **latency** (an order isn't processed the instant it arrives — it's queued) for **Reliability** and **Performance Efficiency** under burst load — a deliberate, justified choice given the explicit 50x-spike requirement. It also trades some **initial complexity** (multiple queues, a Step Functions workflow) for **Operational Excellence** (auditability) — again justified by the explicit visibility requirement in the prompt. If the interviewer relaxed the "50x spike" requirement, a simpler direct-synchronous-processing design might be more appropriate — the architecture should be explicitly justified against the _stated_ requirements, not applied as a generic default.

## 5. Worked Example 2 — Multi-Tenant SaaS Analytics Platform

**Requirement statement:** "Design a platform where thousands of customer organizations each upload clickstream data, and each customer needs their own real-time dashboard plus the ability to query up to 90 days of historical data. New customers should onboard without any manual infrastructure provisioning."

**Step 1 — Clarify:** Functional: multi-tenant data ingestion, real-time dashboards, historical query capability. Non-functional: must scale to "thousands" of tenants, 90-day query window, zero-touch tenant onboarding. Assume per-tenant data isolation is required (a common unstated-but-implied SaaS requirement worth surfacing explicitly).

**Step 2 — Core challenges:** (a) ingesting clickstream data at scale from many independent tenants, (b) serving both real-time (dashboard) and historical (90-day query) access patterns from the same data, (c) achieving zero-touch onboarding for new tenants specifically.

**Step 3-4 — Architecture and service selection:**

- **Ingestion**: a **Kinesis Data Stream** (Part 7 §6), not SQS — this is the direct architectural answer to challenge (b): Kinesis's multi-consumer, replayable model lets the _same_ ingested stream simultaneously feed a real-time dashboard consumer and a separate historical-archive consumer, which SQS's single-consumer-per-message model structurally cannot do without duplicating writes. **Tenant ID is the Kinesis partition key**, directly reusing Part 7 §6's partition-key-cardinality lesson — with "thousands" of tenants, this is a naturally high-cardinality key giving good load distribution.
- **Real-time path**: a **Lambda consumer** (via Kinesis event source mapping, Part 7 §6) processes records as they arrive, updating a per-tenant real-time aggregate (e.g., in DynamoDB, chosen for its low-latency, high-throughput key-value access pattern well suited to "give me this one tenant's current dashboard numbers").
- **Historical path**: a **Kinesis Data Firehose** delivery stream (Part 7 §7), reading from the same Kinesis stream independently, converts records to Parquet and delivers to S3 with tenant-ID-based date-partitioned prefixes — directly enabling the 90-day historical query requirement via **Athena** queries against this partitioned data (a natural extension beyond this roadmap's core Part 7 depth, but directly buildable from Firehose's format-conversion capability).
- **Zero-touch tenant onboarding**: rather than manually provisioning per-tenant infrastructure, tenant isolation is achieved at the **data-partitioning level** (tenant ID as Kinesis partition key and S3 prefix, not separate AWS resources per tenant) — directly addressing challenge (c), since a new tenant simply starts sending data with their tenant ID and immediately participates in the existing shared infrastructure, with no new AWS resource ever needing to be provisioned per tenant.
- **Deployment and governance**: the shared infrastructure (Kinesis stream, Firehose, Lambda consumers) defined via **Terraform** (Part 9 §4) — a deliberate choice if this platform's organization also manages infrastructure on another cloud or significant non-AWS SaaS tooling elsewhere (per Part 9 §9's decision tree); otherwise CDK/CloudFormation would be equally valid.

**Step 5 — Trade-offs (Well-Architected framing):** This design trades **per-tenant infrastructure isolation** (each tenant does _not_ get their own dedicated queue/stream) for **Cost Optimization and Operational Excellence at scale** — provisioning genuinely separate infrastructure per tenant for "thousands" of tenants would be operationally unmanageable and needlessly expensive; shared infrastructure with logical (partition-key/prefix-based) isolation is the appropriate trade-off given the explicit scale requirement. If the requirement instead specified a small number of very large, security-sensitive enterprise tenants each requiring strict physical infrastructure isolation, this trade-off would flip toward per-tenant resources — again, the "right" answer is requirement-dependent, not universal.

## 6. Interview Questions — Meta-Level (About the Design Process Itself)

**🎯 Junior:** _"When given a system design question, what's the first thing you should do?"_
**Model answer:** Clarify the requirements before designing anything — both functional requirements (what must the system actually do) and non-functional requirements (expected scale, latency needs, consistency requirements, budget or team constraints). Jumping straight to naming AWS services without first understanding what's actually being asked for is a common mistake — the right architecture depends entirely on the specific requirements, and different reasonable-sounding requirement assumptions can lead to very different correct answers.

**🎯 Intermediate:** _"How do you decide how much detail to go into for any one component during a time-limited system design interview?"_
**Model answer:** Prioritize depth on the 2-3 components that represent the genuinely hard, distinguishing problems in this specific system — for an order-processing system, that's the traffic-burst-absorption and multi-check-coordination pieces, not the basic API Gateway front door, which is fairly standard regardless of the specific system. Deliberately keep the more standard, less differentiating pieces brief, mentioning the service and moving on, so there's time to go deep on the parts that actually demonstrate real architectural judgment — an interviewer generally cares far more about how you reason through the hard, specific problem than about correctly naming every service in a diagram.

**🎯 Senior:** _"An interviewer pushes back on your design and asks 'what would you do differently if this needed to handle 100x more scale?' How do you approach that follow-up?"_
**Model answer:** Identify which specific component of the current design would actually break first at that scale, rather than redesigning everything — for example, if the dashboard's real-time aggregate store was a single DynamoDB table with reasonable but not extreme provisioned capacity, that might need a partition-key redesign or a move to on-demand capacity mode at 100x scale, while the Kinesis ingestion layer might just need more shards, a much smaller architectural change. Walk through the design component by component, explicitly reasoning about where the actual bottleneck would first appear, rather than assuming everything needs to change — this demonstrates understanding of the actual scaling characteristics of each piece chosen, not just naming a generically "more scalable" alternative.

**🎯 Architect:** _"How do you handle a system design interview where the interviewer deliberately gives you an ambiguous or underspecified requirement?"_
**Model answer:** Treat the ambiguity as a genuine signal to ask a clarifying question rather than silently picking an assumption and hoping it's right, especially if the ambiguity affects a major architectural decision — for example, if "handle high traffic" doesn't specify actual numbers, ask for a rough order of magnitude, since the right architecture for 1,000 requests/second and 1,000,000 requests/second can be genuinely different, not just a scaled-up version of the same design. If the interviewer declines to give a specific number (sometimes deliberately, to see how ambiguity is handled), explicitly state the assumption out loud, explain why that assumption was chosen, and note how the design would change under a different assumption — this demonstrates the same underlying skill either way: recognizing that requirements drive architecture, and being explicit about the requirement-to-design linkage rather than presenting one design as if it were the only possible correct answer.

## 7. Key Takeaways

🔑 System design synthesis is a genuinely different skill from knowing individual services — it requires combining many pieces of prior knowledge into one coherent, requirement-justified architecture.
🔑 Always clarify functional and non-functional requirements before designing — the "right" architecture is requirement-dependent, and different reasonable assumptions lead to different correct designs.
🔑 Identify and prioritize depth on the 2-3 genuinely hard, distinguishing challenges in any given system, rather than spreading equal attention across every component.
🔑 Every major service choice should be explicitly justified against the specific requirement it addresses and against alternatives, using Well-Architected pillar language for trade-offs.
🔑 When pushed on scale/requirement changes, reason component-by-component about what would actually break first, rather than assuming a wholesale redesign is always needed.

## 8. Related Concepts

- Every prior Part in this roadmap supplies the concrete services combined in these worked examples.
- **Well-Architected Framework** (the trade-off language used throughout) → Part 10 §1.
- **Choosing the Right Integration Pattern / IaC Tool** (the decision frameworks directly applied in service-selection reasoning) → Part 7 §9, Part 9 §9.
- **Final Interview Preparation** (applying this methodology under realistic interview conditions, plus behavioral and rapid-fire technical prep) → next section, Part 10 §9.
