# Part 7, Section 9: Choosing the Right Integration Pattern (SQS vs SNS vs EventBridge vs Kinesis vs MSK)

## 1. Definition

**Plain language:** This section directly answers the question every one of the last eight sections has been building toward: given a real requirement, which of these five services — SQS, SNS, EventBridge, Kinesis Data Streams, or MSK — should you actually use? This is one of the single most frequently asked AWS architecture interview questions, precisely because getting it right requires synthesizing the delivery model, ordering guarantees, consumer model, and operational trade-offs of each service.

**Precise definition:** This section provides a structured decision framework comparing SQS, SNS, EventBridge, Kinesis Data Streams, and MSK across their core dimensions — consumption model (point-to-point vs. pub/sub vs. replayable log), ordering guarantees, durability/retention model, throughput characteristics, and operational overhead — to support a defensible, criteria-driven architecture decision rather than a default or habitual choice.

## 2. Why This Framework Exists / Problem It Solves

Across Part 7 §1-8, five services that superficially all "move data from one place to another" turned out to have meaningfully different underlying models: SQS deletes on consumption (Part 7 §1-2), SNS pushes without retention (Part 7 §3), EventBridge routes on content (Part 7 §4), Kinesis retains an ordered, replayable, multi-consumer log (Part 7 §6), and MSK provides the same replayable-log model via genuine Kafka compatibility (Part 7 §8). Engineers who don't internalize these differences tend to default to whichever service they used last, or whichever is most familiar — which frequently produces architectures that technically work but fight the chosen service's actual model (e.g., building ordering logic on top of SNS, or building multi-consumer replay on top of SQS, both of which are the wrong tool for that specific job).

This framework exists to make the decision criteria explicit and repeatable, rather than intuition-based.

## 3. Prerequisites and Dependencies

- All of Part 7 §1-8 — this section is a synthesis, not new material, and assumes fluency with every service compared here.

## 4. The Core Decision Dimensions

| Dimension | SQS | SNS | EventBridge | Kinesis Data Streams | MSK |
|---|---|---|---|---|---|
| **Consumption model** | Point-to-point (one message → one consumer) | Push fan-out (one message → all confirmed subscribers) | Content-based routing (one event → matching rule targets) | Multi-consumer replayable log | Multi-consumer replayable log (Kafka) |
| **Message removed after consumption?** | Yes (explicit delete) | N/A — not retained after delivery attempts | N/A — not retained after delivery attempts | No — retained per retention window regardless of reads | No — retained per retention window regardless of reads |
| **Ordering guarantee** | None (standard) / per-`MessageGroupId` (FIFO) | None (topic-wide) | None (rule-based routing, not inherently ordered) | Per-partition-key (per shard) | Per-key (per partition) |
| **Multiple independent consumers reading the same data?** | No (one message, one consumer) | Yes, but each gets a push, not a replayable read | Yes, via multiple rules/targets, but not a replay model | Yes, natively, with independent positions | Yes, natively, via consumer groups |
| **Replay historical data?** | No | No (no storage) | Only if archiving is explicitly enabled | Yes, within the retention window | Yes, within the retention window (via offset reset) |
| **Throughput ceiling** | Near-unlimited (standard) / high but bounded (FIFO) | High, near-real-time push | High; per-rule/target dependent | Very high, scales with shard count | Very high, scales with partition count |
| **Operational overhead** | None (fully serverless) | None (fully serverless) | None (fully serverless) | Low (serverless, but shard/partition-key design matters) | Higher (VPC networking, partition planning, though brokers are managed) |
| **Native AWS service event awareness** | No (must be explicitly wired) | No (must be explicitly wired) | Yes — ~200 AWS services emit to the default bus automatically | No | No |
| **Primary use case fit** | Decouple producer/consumer, buffer load, work queues | Broadcast one event to many independent unrelated consumers | Content-rich routing, reacting to AWS service events, SaaS integration | Real-time analytics, multi-team shared event streams, strict per-key ordering at scale | Kafka-ecosystem compatibility, migration from existing Kafka |

## 5. Decision Tree (Walkthrough Logic)

1. **Does the same data need to be read by multiple independent applications, each potentially replaying historical data?**
   - Yes → Kinesis Data Streams or MSK (proceed to step 2 to choose between them).
   - No → proceed to step 3.
2. **Do you need genuine Kafka protocol/ecosystem compatibility (Kafka Connect, Kafka Streams, ksqlDB, or migrating an existing Kafka deployment)?**
   - Yes → MSK.
   - No → Kinesis Data Streams (simpler operationally, deeper native AWS integration, no VPC requirement).
3. **Does exactly one consumer need to process each unit of work, with durable buffering if the consumer is temporarily unavailable?**
   - Yes → SQS (add FIFO if strict ordering/exactly-once-within-window matters; add a DLQ regardless).
   - No → proceed to step 4.
4. **Does one event need to trigger multiple, independent, potentially heterogeneous downstream actions (multiple different consumer types) with minimal producer awareness of who's listening?**
   - Yes → proceed to step 5.
   - No → reconsider whether this is genuinely an integration/messaging problem at all.
5. **Does the routing decision need to inspect the actual structure/content of the event (nested fields, numeric ranges), or do you need automatic ingestion of native AWS service events with zero producer wiring?**
   - Yes → EventBridge.
   - No, simple flat-attribute filtering (or no filtering) is sufficient → SNS (commonly paired with SQS subscribers for the fan-out pattern, Part 7 §3).

## 6. Common Combined Architectures (Not Either/Or)

In real production systems, these services are frequently **combined**, not chosen exclusively:

- **SNS fan-out to SQS**: one event, multiple durable, independently-retryable queues (Part 7 §3) — combines SNS's broadcast model with SQS's durability.
- **EventBridge → Step Functions / Lambda / SQS**: EventBridge's rich content-based routing decides *what* should happen; the target does the actual work, often itself an SQS queue for durability or a Step Functions workflow for multi-step orchestration.
- **Kinesis Data Streams → Firehose (one consumer) + Lambda (another consumer) + KCL app (a third consumer)**: the same durable stream feeding a low-latency real-time path, a batch analytics-lake delivery path, and a custom processing application, all independently, all from one source of truth (Part 7 §7).
- **EventBridge → Kinesis / Firehose**: EventBridge can itself target Kinesis or Firehose, letting content-based routing decide which events even enter a streaming pipeline in the first place.

## 7. Common Mistakes in This Decision

- ❌ Using SNS where SQS's durability and single-consumer buffering was actually needed — messages get lost during a subscriber outage because SNS isn't a durable store by default (Part 7 §3).
- ❌ Using SQS where Kinesis's multi-consumer replay was actually needed — engineers awkwardly duplicate a message into several queues instead of using a naturally multi-consumer service.
- ❌ Defaulting to EventBridge for everything because of its rich filtering, when a simpler SNS fan-out would have been sufficient and lower-overhead for a use case that doesn't need content-based routing.
- ❌ Choosing MSK for a greenfield project with no Kafka-ecosystem requirement, taking on VPC networking and partition-planning overhead Kinesis would have avoided entirely.
- ❌ Treating "we already use X elsewhere in this system" as sufficient justification, rather than evaluating the current requirement's actual consumption-model needs against the decision tree above.

## 8. Interview Questions with Model Answers

**🎯 Junior:** *"In one sentence each, when would you reach for SQS versus SNS?"*
**Model answer:** SQS is for when exactly one consumer needs to process each piece of work, with durable buffering if that consumer is temporarily unavailable — think a work queue. SNS is for when one event needs to be broadcast to multiple independent subscribers simultaneously, with the producer having no need to know who's listening — think a notification fan-out.

**🎯 Intermediate:** *"A junior engineer proposes building a real-time leaderboard that three separate teams each need to independently consume and reprocess at their own pace, including replaying the last few hours after a bug fix, using SQS with three separate queues fed by the same producer. What would you push back on, and what would you suggest instead?"*
**Model answer:** The core problem is that SQS's model is fundamentally single-consumer-per-message and offers no replay — duplicating the write across three queues technically works for the "three independent consumers" part, but completely fails the "replay the last few hours after a bug fix" requirement, since a message deleted from a queue is simply gone; there's no way to rewind. Suggest Kinesis Data Streams instead, since its entire model is built around exactly this scenario: a durable, retained log that multiple independent consumers can each read at their own pace and position, including replaying from any point within the retention window, without the producer needing to know about or write to multiple destinations at all — a single stream, multiple independent readers, one of them replaying, natively supported rather than worked around.

**🎯 Senior:** *"Design the event architecture for an e-commerce order pipeline: order placement needs to trigger inventory update, email confirmation, and fraud screening (all independent, all must happen), fraud screening result needs to route to either an auto-approve or manual-review path based on a risk score threshold, and the whole multi-step process needs full auditability."*
**Model answer:** Order placement publishes to an SNS topic (or an EventBridge custom bus, discussed below) subscribed by three SQS queues — inventory, email, fraud-screening — using the fan-out pattern, so each of the three independent actions gets its own durable, independently-retryable queue rather than the producer needing to know about or coordinate three separate downstream systems. For the fraud-screening result's risk-score-based branching, route that decision through EventBridge rather than SNS, since "route based on a numeric risk-score field in the event" is exactly the content-based, numeric-comparison pattern SNS's flat attribute filtering can't cleanly express but EventBridge's event pattern matching can. For the "full auditability of the whole multi-step process" requirement specifically, wrap the actual sequencing — validate, fan out, wait for fraud result, branch, fulfill — in a Step Functions Standard workflow, since that's precisely what gives full step-by-step execution history and audit visibility that a scattered collection of independent SNS/SQS/EventBridge triggers wouldn't provide on its own; the messaging services handle the individual event distribution, and Step Functions owns the overall process visibility and correctness.

**🎯 Architect:** *"A financial services company needs a system where trade events must be processed in strict order per trading account, support multiple downstream consumers (real-time risk engine, end-of-day settlement batch, long-term regulatory archive), and the regulatory archive consumer needs the ability to replay any historical period going back up to 7 years for audit purposes. The company has no existing Kafka investment. Design this and justify every major choice."*
**Model answer:** Kinesis Data Streams is the right foundation, not SQS or SNS, because the requirement for multiple independent consumers plus historical replay is exactly Kinesis's core model, and — critically — since there's no existing Kafka investment stated, MSK's additional VPC-networking and Kafka-operational overhead isn't justified by any ecosystem-compatibility requirement; Kinesis gives the same replayable multi-consumer model with less operational surface area. Use trading account ID as the partition key, guaranteeing strict per-account ordering (a hard regulatory-adjacent requirement) while distributing load across accounts. For the three consumers: the real-time risk engine would be a low-latency KCL/Lambda consumer with Enhanced Fan-Out registered, given its latency sensitivity and need for dedicated throughput independent of the other two; the end-of-day settlement batch would be a separate, independent KCL consumer reading at its own pace, unaffected by the real-time consumer's read pattern. The 7-year regulatory archive requirement, though, exceeds Kinesis's maximum 365-day retention — so pair Kinesis with a Firehose delivery stream (a third independent consumer of the same source stream) landing every record durably into S3 in Parquet format with date-based partitioning, and the regulatory archive/replay use case would actually be served from that S3-based long-term store via Athena queries rather than from Kinesis's own retention window directly, since Kinesis was never designed to be a 7-year archive — this combination (Kinesis for real-time multi-consumer needs, Firehose-to-S3 for durable long-term archive and replay) is exactly the kind of combined-services architecture this section's §6 describes, and each piece is doing the specific job it's actually built for.

## 9. Common Misconceptions

- "There's one universally 'best' AWS messaging/streaming service." False — each of the five services optimizes for a genuinely different consumption model, and the right choice is entirely requirement-dependent, not a matter of picking the most modern or most powerful-sounding option.
- "You should pick one service and standardize on it everywhere for consistency." False as a blanket rule — real production architectures very commonly and correctly combine several of these services, each handling the specific part of the problem it's actually suited for (§6 above).

## 10. Key Takeaways

🔑 The single most important question is: does the same data need to be read by multiple independent applications with replay capability? If yes, you're in Kinesis/MSK territory; if no, you're in SQS/SNS/EventBridge territory.
🔑 SQS: single consumer, durable, delete-on-read. SNS: broadcast push, not retained. EventBridge: content-aware routing, native AWS service event integration.
🔑 Kinesis: AWS-native replayable multi-consumer log, no VPC footprint, simpler operationally. MSK: genuine Kafka compatibility, VPC-networked, chosen for ecosystem/migration needs specifically.
🔑 Production architectures routinely combine multiple of these services — SNS fan-out to SQS, EventBridge routing to Step Functions, Kinesis feeding both a real-time consumer and a Firehose-to-S3 archive — rather than forcing one service to do everything.
🔑 This decision is one of the most heavily interview-tested AWS architecture topics precisely because it requires synthesizing every service's actual underlying model, not just its marketing description.

## 11. Related Concepts

- Every service compared here: **SQS** (Part 7 §1-2), **SNS** (Part 7 §3), **EventBridge** (Part 7 §4), **Step Functions** (Part 7 §5, often the orchestration layer sitting on top of these messaging choices), **Kinesis Data Streams** (Part 7 §6), **Kinesis Data Firehose** (Part 7 §7), **MSK** (Part 7 §8).
- **Part 7 §10** (next, and final section of this Part) will close out Application Integration & Streaming with a wrap-up and integration interview drill synthesizing all nine preceding sections.
