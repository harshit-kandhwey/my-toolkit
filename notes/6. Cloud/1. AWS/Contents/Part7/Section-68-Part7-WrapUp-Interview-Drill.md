# Part 7, Section 10: Part 7 Wrap-Up + Integration Interview Drill

## 1. Part 7 Recap — What Was Covered

Part 7, Application Integration & Streaming, covered nine core services/topics across two governing paradigms — **messaging** (data moved once, consumed, and gone) and **streaming** (data retained in an ordered log, read by many independent consumers) — plus the orchestration layer that coordinates work across them:

1. **SQS Fundamentals** (§1) — point-to-point queuing, visibility timeout, receipt handles, at-least-once delivery.
2. **SQS Advanced** (§2) — DLQs/redrive policies, FIFO ordering and deduplication, heartbeat pattern for long jobs.
3. **SNS** (§3) — publish/subscribe fan-out, filter policies, the SNS→SQS fan-out pattern.
4. **EventBridge** (§4) — content-based event routing, native AWS service event integration, archive/replay.
5. **Step Functions** (§5) — declarative workflow orchestration, Standard vs. Express, task tokens for human-in-the-loop.
6. **Kinesis Data Streams** (§6) — durable, ordered, replayable, multi-consumer log; partition keys and shards.
7. **Kinesis Data Firehose** (§7) — managed, no-code delivery of streaming data into S3/Redshift/OpenSearch, with format conversion.
8. **Amazon MSK** (§8) — managed Apache Kafka, for genuine Kafka-ecosystem compatibility and migration scenarios.
9. **Choosing the Right Integration Pattern** (§9) — the decision framework tying all eight services together.

## 2. Progressive Hands-On Labs (Beginner → Production-Style)

**Lab 1 (Beginner): Basic SQS Queue with DLQ**
Create a standard SQS queue and a DLQ, set `maxReceiveCount` to 3, write a simple producer/consumer in Python using boto3, deliberately raise an exception in the consumer for one message and observe it move to the DLQ after 3 receive attempts. _Validates: §59-60 core mechanics._

**Lab 2 (Beginner-Intermediate): SNS Fan-Out to Two SQS Queues**
Create an SNS topic and two SQS queues; subscribe both queues to the topic with correct queue policies; publish one message and confirm both queues independently receive a copy; add a filter policy to one subscription and confirm selective delivery. _Validates: §61._

**Lab 3 (Intermediate): EventBridge Content-Based Routing**
Create two EventBridge rules on a custom event bus — one matching a numeric threshold on a nested field, one matching all events of a given type — targeting different Lambda functions; publish events that satisfy each pattern combination and confirm correct routing. _Validates: §62._

**Lab 4 (Intermediate): Step Functions Order-Processing Workflow**
Build the order-processing state machine from §63 (retry, catch, parallel, choice), trigger it via `start-execution`, deliberately fail the payment validation Lambda to confirm the Catch path fires, and inspect the execution history to trace exactly what happened. _Validates: §63._

**Lab 5 (Intermediate-Advanced): Kinesis Multi-Consumer Stream**
Create a Kinesis stream with 2 shards, write records with a deliberately low-cardinality partition key and observe the resulting hot-shard throttling via CloudWatch, then redesign with a high-cardinality key and confirm even distribution; attach two independent consumers (a Lambda via event source mapping, and a Firehose delivery to S3) and confirm both receive the full stream independently. _Validates: §64-65._

**Lab 6 (Production-Style, Capstone): Full E-Commerce Event Architecture**
Build the complete architecture from §67's senior-level interview scenario: order placement → SNS fan-out to inventory/email/fraud-screening SQS queues → EventBridge risk-score routing → Step Functions orchestrating the full sequence with retry/catch → full execution history reviewed for audit purposes. This lab deliberately combines every service from this Part into one coherent, defensible architecture. _Validates: §59-67 in combination._

## 3. Consolidated Key-Takeaways Checklist

- [ ] I can explain why SQS guarantees at-least-once, not exactly-once, delivery, and why that requires idempotent consumers.
- [ ] I can explain the visibility timeout + receipt handle mechanism precisely, including what happens on consumer crash.
- [ ] I can explain FIFO's ordering scope (`MessageGroupId`) and deduplication scope (5-minute window), and why they're precisely bounded, not absolute.
- [ ] I can explain why a DLQ must match its source queue's type, and why `RedriveAllowPolicy` matters.
- [ ] I can explain the structural difference between SNS's push-without-retention model and SQS's durable, delete-on-read model.
- [ ] I can explain why SNS filter policies control routing, not data-level access.
- [ ] I can explain why EventBridge's content-based pattern matching is more expressive than SNS's flat attribute filtering, with a concrete example.
- [ ] I can explain the difference between Step Functions Standard (durable, exactly-once, full history) and Express (at-least-once, cheaper at volume) and when to choose each.
- [ ] I can explain the task-token pattern and why it doesn't tie up compute resources during a long wait.
- [ ] I can explain why Kinesis partition key cardinality directly determines both ordering scope and shard-load distribution.
- [ ] I can explain why Kinesis retains data regardless of consumption, and what `IteratorAgeMilliseconds` signals.
- [ ] I can explain what Firehose adds on top of Kinesis Data Streams (managed delivery, no consumer code) and what it gives up (no replay, no multi-consumer model).
- [ ] I can explain when MSK is the right choice over Kinesis, and specifically why "already using Kafka" is the deciding factor, not general preference.
- [ ] I can walk through the five-service decision tree (§67) from a cold requirement statement without prompting.
- [ ] I can name at least three real production architectures that combine multiple of these services rather than using one in isolation.

## 4. Related Technologies (Beyond This Roadmap's Current Scope)

- **Amazon MQ** — a managed message broker service supporting ActiveMQ and RabbitMQ protocols specifically, for migrating existing applications that depend on those specific protocols rather than SQS/SNS's AWS-native APIs; a natural extension for anyone with an existing ActiveMQ/RabbitMQ investment analogous to MSK's role for Kafka.
- **AWS AppSync** — managed GraphQL with built-in real-time subscriptions, a different (API-layer, not infrastructure-layer) approach to real-time data delivery, relevant for teams building client-facing real-time features rather than backend service integration.
- **Amazon Managed Service for Apache Flink** — for complex stream processing (windowed aggregations, joins across streams) beyond what Lambda-based Kinesis/Firehose consumers typically handle, a natural next step after Kinesis Data Streams for teams needing genuine stream-processing (not just stream-delivery) capability.
- **AWS Glue** — the ETL and Data Catalog service underlying Firehose's format-conversion feature (§65), worth its own dedicated exploration for teams building broader data lake pipelines.
- **Amazon Athena / Redshift Spectrum** — the query layer typically sitting on top of Firehose-delivered S3 data, completing the "ingest → store → query" data lake picture only partially covered here.

## 5. Recommended Next Topics (Learning Path)

Given Part 7's content, the roadmap's upcoming parts build directly on this foundation:

- **Part 8 — Observability & Monitoring** (CloudWatch, X-Ray, CloudTrail) is the natural and immediate next step, since nearly every section in Part 7 referenced CloudWatch metrics, alarms, and monitoring patterns (DLQ depth, `IteratorAgeMilliseconds`, consumer group lag, execution history) without yet covering CloudWatch itself in depth — Part 8 will make those forward references concrete.
- **Part 9 — Infrastructure as Code** (CloudFormation, CDK, Terraform) is the second natural next step, since nearly every "production usage" note in Part 7 stated that real deployments define these resources declaratively rather than via CLI commands — Part 9 will cover exactly how.
- Beyond this roadmap: **AWS Glue, Athena, and Redshift Spectrum** (the analytics/query layer completing Firehose's data lake story) and **Amazon Managed Service for Apache Flink** (genuine stream processing beyond delivery) are natural extensions for anyone specializing further in data engineering on AWS.
