# Part 7, Section 6: Amazon Kinesis Data Streams

## 1. Definition

**Plain language:** Kinesis Data Streams is a service for capturing and processing continuous, high-volume streams of data in near real-time — think clickstreams, IoT sensor readings, application logs, or financial transaction feeds — where many different consumers might each need to read through the same stream of events independently, and where the order events arrived in often matters.

**Precise definition:** Amazon Kinesis Data Streams (KDS) is a scalable, durable, real-time data streaming service that ingests and stores records in an ordered, replayable log partitioned into shards, allowing multiple independent consumer applications to read the same stream concurrently, each maintaining its own position, with configurable retention from 24 hours up to 365 days.

## 2. Why It Exists / Problem It Solves

SQS and SNS (§59-61) both fundamentally **remove** a message once it's been meaningfully processed/delivered — a message is either consumed once (SQS) or pushed once per subscriber and not retained afterward (SNS). Neither is designed for a scenario where:

- The **same data needs to be read multiple times by multiple, independent applications**, each processing it differently and each needing to track its own read position, potentially replaying from an earlier point.
- **Strict, stream-wide ordering** matters, at very high throughput (millions of events per second), not just within a small partition group as with FIFO SQS.
- Analytics or ML systems need to **re-read historical data** (e.g., reprocess the last 24 hours of clickstream data after fixing an aggregation bug) — something neither SQS (messages gone after deletion) nor SNS (no storage at all) supports.

Kinesis solves this with a **log-based** model (conceptually similar to Apache Kafka) rather than a queue-based model: records are appended to a durable, ordered log and _retained_ for a configurable window, and consumers read from the log using their own tracked position (a sequence number / iterator), rather than the log "forgetting" a record once read. Multiple consumer applications can independently read the entire stream from whatever position each wants, without affecting each other — a structurally different consumption model from SQS's single-consumer-per-message semantics.

**What existed before it:** self-managed Kafka clusters (still common, and covered directly in §66 as Amazon MSK, the managed Kafka alternative) requiring significant operational overhead for cluster management, partition rebalancing, and scaling.

## 3. Prerequisites and Dependencies

- **SQS/SNS** (§59-61): understanding the queue and pub/sub models makes the log-based streaming model's differences clearer by contrast.
- **Lambda** (§25): a very common Kinesis consumer via event source mappings, similar to SQS's Lambda integration.
- Basic familiarity with the concept of **partitioning** for horizontal scale (introduced from scratch below).

## 4. Internal Working

- A Kinesis stream is divided into one or more **shards** — the fundamental unit of throughput and parallelism. Each shard supports up to 1 MB/second or 1,000 records/second of write throughput, and up to 2 MB/second of read throughput (shared across all consumers in the classic "shared throughput" model, though **Enhanced Fan-Out**, covered below, changes this).
- Every record written to the stream includes a **partition key**, supplied by the producer. Kinesis hashes this partition key to deterministically assign the record to a specific shard — meaning **all records with the same partition key always land on the same shard, in the order they were written**, giving per-key ordering guarantees analogous conceptually to FIFO SQS's per-`MessageGroupId` ordering, but at a fundamentally higher and more horizontally scalable throughput ceiling (you can add shards to add capacity).
- Records are retained in the stream for a configurable period (default 24 hours, extendable up to 365 days with extended retention enabled) regardless of whether any consumer has read them — this is the core structural difference from SQS, where a message vanishes once deleted.
- Consumers track their own **position** in the stream using a **sequence number** and don't affect any other consumer's position — many independent applications can read the identical stream of records concurrently, each starting from wherever it wants (the very beginning of the retention window, the current tip, or a specific timestamp/sequence number).
- **Enhanced Fan-Out (EFO)** consumers get a dedicated 2 MB/second read throughput pipe per consumer per shard (rather than sharing the shard's total 2 MB/second read capacity across all consumers using the classic polling model), at additional cost — critical for scenarios with many concurrent consumer applications needing full-speed independent reads.

```
Producer A (partition key: "user-123") --+
Producer B (partition key: "user-456") --+--> Kinesis Stream (Shard 1: keys hashing to it, Shard 2: others...)
Producer C (partition key: "user-123") --+         |
                                                     |  (durable, ordered, retained log)
                          +--------------------------+--------------------------+
                          v                          v                          v
                 Consumer App 1              Consumer App 2              Consumer App 3
                 (real-time dashboard,       (analytics pipeline,        (fraud detection,
                  reads from tip)             reads from tip)             replays last 6 hrs)
```

## 5. Architecture & Components

| Component                            | Explanation                                                                                                                                                                                                                                                                                                     |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Stream**                           | The named, durable, ordered log; composed of one or more shards.                                                                                                                                                                                                                                                |
| **Shard**                            | The unit of throughput/parallelism — 1 MB/s or 1,000 records/s write, 2 MB/s read (shared model).                                                                                                                                                                                                               |
| **Record**                           | A data blob (up to 1 MB) plus a partition key and a system-assigned sequence number.                                                                                                                                                                                                                            |
| **Partition Key**                    | Producer-supplied string determining shard assignment via hashing — the mechanism behind per-key ordering.                                                                                                                                                                                                      |
| **Shard Iterator / Sequence Number** | How a consumer tracks and resumes its read position within a shard.                                                                                                                                                                                                                                             |
| **Kinesis Client Library (KCL)**     | An AWS-provided library that handles the complexity of coordinating multiple worker instances reading from multiple shards of the same stream, tracking checkpoints, and handling shard splits/merges — the standard way production consumers are built, rather than calling the raw `GetRecords` API directly. |
| **Enhanced Fan-Out (EFO) Consumer**  | A registered consumer with a dedicated throughput pipe per shard, pushed to via HTTP/2, rather than sharing the shard's default polling-based read throughput.                                                                                                                                                  |

## 6. Lifecycle / Workflow

1. **Create** the stream, specifying the initial shard count (or use **On-Demand mode**, which auto-scales shard count without manual capacity planning).
2. **Producers** write records via `PutRecord` (single) or `PutRecords` (batch, up to 500 records/call), each tagged with a partition key.
3. Kinesis **durably stores** records in shard order, retained per the configured retention period.
4. **Consumers** (using KCL, the raw SDK, or a Lambda event source mapping) read records from one or more shards, tracking their own position via checkpoints.
5. Consumers **checkpoint** their progress (typically via KCL, which persists checkpoints to a DynamoDB table it manages) so that if a consumer worker restarts, it resumes from its last checkpoint rather than reprocessing the entire stream or losing its place.
6. Records eventually **age out** of the retention window and are removed, whether or not every consumer has read them — so consumers must keep up within the retention period or explicitly plan for reprocessing via the stream's data being additionally landed elsewhere (e.g., via Kinesis Data Firehose to S3, §65).

## 7. Configuration

| Setting                                              | Purpose                                                                                                                         |
| ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Shard count / capacity mode                          | `PROVISIONED` (manual shard count, manual scaling) or `ON_DEMAND` (auto-scales, simpler operationally, different pricing model) |
| `RetentionPeriodHours`                               | 24 hours default, up to 8760 hours (365 days) with extended retention                                                           |
| Partition Key strategy (producer-side design choice) | Determines both ordering scope and load distribution across shards — a poor choice can create a "hot shard"                     |
| Enhanced Fan-Out registration                        | Per-consumer opt-in for dedicated throughput, at additional cost                                                                |
| Server-side encryption (KMS)                         | Encrypts records at rest within the stream                                                                                      |

⚠️ **Warning:** choosing a **low-cardinality partition key** (e.g., a fixed constant, or a key with very few distinct values relative to record volume) concentrates most or all records onto a small number of shards — a "hot shard" — bottlenecking throughput regardless of how many total shards the stream has. Partition key selection is one of the most consequential Kinesis design decisions and a frequent interview topic.

## 8. Commands (Full Documentation)

### `aws kinesis create-stream`

- **Purpose:** Creates a new Kinesis data stream.
- **Syntax:**
  ```
  aws kinesis create-stream --stream-name <name> --shard-count <n>
  ```
  or, for On-Demand mode:
  ```
  aws kinesis create-stream --stream-name <name> --stream-mode-details StreamMode=ON_DEMAND
  ```
- **Practical example:**
  ```
  aws kinesis create-stream --stream-name clickstream-events --shard-count 4
  ```
  **Expected output:** (empty on success; use `describe-stream-summary` to confirm status)
- **Production usage:** On-Demand mode is increasingly the default choice for new streams with unpredictable or evolving traffic patterns, trading some cost efficiency at very high, stable volume for operational simplicity (no manual shard-count capacity planning).
- **Common errors:** `LimitExceededException` if the account's shard limit for the region is exceeded (a soft, raisable limit).
- **Security impact:** requires `kinesis:CreateStream`; server-side encryption should typically be enabled at creation for sensitive data streams.

### `aws kinesis put-record` / `put-records`

- **Purpose:** Writes one (or, batched, up to 500) records to a stream.
- **Syntax:**
  ```
  aws kinesis put-record --stream-name <name> --partition-key <key> --data <base64-or-text>
  ```
- **Practical example:**
  ```
  aws kinesis put-record --stream-name clickstream-events \
    --partition-key "user-123" \
    --data "eyJldmVudCI6ImNsaWNrIn0="
  ```
  **Expected output:**
  ```json
  {
    "ShardId": "shardId-000000000001",
    "SequenceNumber": "49546986683135544286507457936321625675700192471156785154"
  }
  ```
- **Important arguments:** `--partition-key` is the critical design decision (§7 warning above); `--data` must be base64-encoded when using the CLI directly (SDKs typically handle this encoding transparently).
- **Production usage:** high-throughput producers use `PutRecords` (batched) rather than looping individual `PutRecord` calls, both for throughput efficiency and to reduce per-call overhead costs.
- **Common errors:** `ProvisionedThroughputExceededException` when a shard's write capacity is exceeded — commonly caused by a hot-shard partition-key problem rather than genuinely needing more total shards.
- **Performance impact:** batching via `PutRecords` is materially more throughput-efficient than individual `PutRecord` calls at any meaningful volume.

### `aws kinesis get-shard-iterator` / `get-records`

- **Purpose:** The raw, low-level consumer read path — obtain a starting position in a shard, then read records from it. (Production consumers typically use KCL instead of calling these directly, but understanding the raw mechanics is foundational.)
- **Syntax:**
  ```
  aws kinesis get-shard-iterator --stream-name <name> --shard-id <shard-id> --shard-iterator-type <type>
  aws kinesis get-records --shard-iterator <iterator-value>
  ```
- **Important arguments:**
  - `--shard-iterator-type`: `TRIM_HORIZON` (start from the oldest available record), `LATEST` (start from the current tip, ignoring history), `AT_SEQUENCE_NUMBER` / `AFTER_SEQUENCE_NUMBER` (resume from a specific point), or `AT_TIMESTAMP`.
- **Practical example:**
  ```
  aws kinesis get-shard-iterator --stream-name clickstream-events \
    --shard-id shardId-000000000001 --shard-iterator-type LATEST
  ```
  **Expected output:**
  ```json
  { "ShardIterator": "AAAAAAAAAAFXn8..." }
  ```
  Then:
  ```
  aws kinesis get-records --shard-iterator "AAAAAAAAAAFXn8..."
  ```
  **Expected output:**
  ```json
  {
    "Records": [
      {
        "SequenceNumber": "...",
        "Data": "eyJldmVudCI6ImNsaWNrIn0=",
        "PartitionKey": "user-123"
      }
    ],
    "NextShardIterator": "AAAAAAAAAAHy..."
  }
  ```
- **Production usage:** each `get-records` response includes a `NextShardIterator` for the next poll — consumers loop this, but the raw API's per-shard, manual-looping nature is exactly why KCL exists to abstract this complexity away across many shards and many worker instances in production.
- **Common errors:** `ProvisionedThroughputExceededException` on the read side if consumers are polling too aggressively for a shard's read capacity, or if too many consumers (beyond EFO) are sharing the same shard's default 2 MB/s read throughput.

## 9. Hands-On Example — Lambda Consumer via Event Source Mapping

```yaml
# SAM/CloudFormation excerpt (full IaC depth in Part 9)
Resources:
  ClickstreamProcessor:
    Type: AWS::Serverless::Function
    Properties:
      Handler: index.handler
      Runtime: python3.12
      Events:
        KinesisTrigger:
          Type: Kinesis
          Properties:
            Stream: !GetAtt ClickstreamEvents.Arn
            StartingPosition: LATEST
            BatchSize: 100
            ParallelizationFactor: 2 # allows up to 2 concurrent Lambda invocations per shard
```

Similar to SQS's Lambda event source mapping (§59), AWS manages the polling and checkpointing for you — `StartingPosition: LATEST` means the Lambda only processes new records from deployment onward; `TRIM_HORIZON` would instead process the entire retained history first. `ParallelizationFactor` is Kinesis-specific — it allows multiple concurrent Lambda invocations to process different batches from the _same_ shard (up to 10), which is not something SQS offers per-queue in the same way, since Kinesis's per-shard ordering is a producer-side partition-key concern rather than something a single serial consumer must strictly preserve end-to-end unless the application specifically requires it.

**Partition key design comparison:**

```python
# BAD: low-cardinality key concentrates traffic onto one shard
producer.put_record(StreamName="events", Data=data, PartitionKey="click-event")

# GOOD: high-cardinality key (e.g., user ID) spreads load across shards
# while still guaranteeing all of one user's events stay in order on the same shard
producer.put_record(StreamName="events", Data=data, PartitionKey=str(user_id))
```

## 10. Production & Enterprise Usage

- **Startups** commonly start with a small number of shards or On-Demand mode for a single analytics or logging pipeline, often feeding a Lambda consumer or a Kinesis Data Firehose delivery (§65) to S3.
- **Enterprises** use Kinesis Data Streams as the backbone of large-scale **real-time analytics**, **clickstream processing**, **IoT telemetry ingestion**, and **change-data-capture (CDC) pipelines** (e.g., streaming database changes for downstream consumption by multiple teams), often with many independent consumer applications reading the same stream — fraud detection, real-time dashboards, and long-term storage pipelines all reading from one shared, durable stream concurrently, each with EFO consumers to guarantee dedicated throughput.
- **Multi-consumer replay** is a genuinely enterprise-scale pattern: a new team can start consuming an existing high-volume stream from the beginning of the current retention window without any coordination with, or impact on, existing consumers — a capability neither SQS nor SNS provides.
- Kinesis is frequently compared directly against **Amazon MSK** (managed Kafka, §66) for streaming workloads — the choice between them is a common architecture decision covered fully in §67.

## 11. Security Considerations

- Server-side encryption via KMS protects records at rest within the stream (cross-reference §14).
- IAM policies scope `kinesis:PutRecord`/`PutRecords` (producer) and `kinesis:GetRecords`/`GetShardIterator`/`SubscribeToShard` (consumer, the latter for EFO) separately — least privilege applies exactly as with SQS/SNS.
- Because Kinesis retains data for potentially up to a year, data classification and retention-period decisions have direct compliance implications (e.g., PII in a stream retained for 365 days is a materially different compliance posture than the same data in an SQS queue's default 4-day retention).

## 12. Performance Considerations

- Shard count is the primary throughput lever — more shards linearly increase both write and (classic, shared-model) read capacity, but only if partition keys distribute records evenly across them; a poor key choice bottlenecks throughput regardless of shard count.
- Enhanced Fan-Out trades additional cost for eliminating the shared 2 MB/s read-throughput contention across multiple concurrent consumer applications — essential once more than roughly 2 consumer applications need full-speed independent reads of the same shard.
- On-Demand mode removes manual shard-capacity planning but has its own scaling limits and cost model — high, sustained, predictable throughput often favors Provisioned mode for cost efficiency, while spiky or unpredictable traffic favors On-Demand.

## 13. Monitoring

| Metric                               | What it tells you                                                                                                                                                                                   |
| ------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `IncomingBytes` / `IncomingRecords`  | Producer-side ingestion volume, per stream/shard.                                                                                                                                                   |
| `WriteProvisionedThroughputExceeded` | Producer-side throttling — often a hot-shard/partition-key symptom.                                                                                                                                 |
| `ReadProvisionedThroughputExceeded`  | Consumer-side throttling — often too many consumers sharing classic (non-EFO) read throughput.                                                                                                      |
| `GetRecords.IteratorAgeMilliseconds` | How far behind (in time) a consumer's current read position is from the stream's tip — the primary "is my consumer keeping up" signal, directly analogous to SQS's `ApproximateAgeOfOldestMessage`. |

🔑 **Key takeaway:** `IteratorAgeMilliseconds` climbing toward the retention period's duration is a critical alarm — it means a consumer is at risk of records aging out of the stream before that consumer ever reads them, an unrecoverable data-loss scenario for that consumer specific to the log-based, time-bounded-retention model.

## 14. Troubleshooting

| Symptom                                                                        | Likely Root Cause                                                                                                            | Fix                                                                                                                     |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Frequent `ProvisionedThroughputExceededException` on writes                    | Low-cardinality partition key concentrating traffic on few shards ("hot shard"), or genuinely insufficient total shard count | Redesign partition key for higher cardinality/even distribution; add shards (resharding) if genuinely under-provisioned |
| Consumer falling further behind over time (`IteratorAgeMilliseconds` climbing) | Consumer processing slower than incoming write rate, or too many consumers contending for shared (non-EFO) read throughput   | Scale consumer parallelism (more KCL workers, or Lambda `ParallelizationFactor`); consider Enhanced Fan-Out             |
| New consumer needs historical data but records already aged out                | Retention period too short for the required replay window                                                                    | Extend `RetentionPeriodHours` proactively for streams that may need longer replay windows                               |
| Multiple consumer apps interfering with each other's throughput                | All sharing the classic 2 MB/s per-shard read pool                                                                           | Register affected consumers for Enhanced Fan-Out                                                                        |

## 15. Best Practices

- Choose a high-cardinality, evenly-distributed partition key deliberately — this is the single most consequential Kinesis design decision.
- Use `PutRecords` batching for producer throughput efficiency.
- Use KCL (or a managed integration like the Lambda event source mapping) rather than hand-rolling raw shard-iterator polling loops in production.
- Alarm on `IteratorAgeMilliseconds` as the primary "is my pipeline keeping up" signal.
- Extend retention proactively for streams that may need historical replay, rather than reactively after data has already aged out.
- Use Enhanced Fan-Out once more than a couple of independent consumer applications need full-speed reads of the same stream.

## 16. Anti-Patterns & Common Mistakes

- ❌ Using a low-cardinality or constant partition key "because it's simple" — creates a hot shard that bottlenecks throughput no matter how many shards the stream has.
- ❌ Building custom raw polling loops against `GetRecords`/`GetShardIterator` instead of using KCL or a managed consumer integration — reinventing checkpoint management, shard-split/merge handling, and worker coordination that KCL already solves.
- ❌ Treating Kinesis retention as unlimited or "good enough by default" — the default 24-hour window is easy to exceed for consumers that fall behind or for teams that need longer historical replay, without proactively extending it.
- **Common misconception:** "Kinesis and SQS are interchangeable, just pick whichever." False — SQS is single-consumer-per-message, ephemeral once processed; Kinesis is multi-consumer, replayable, ordered-by-partition-key, and retention-windowed. The choice depends on whether multiple independent readers need their own view of the same ordered data over time.

## 17. Interview Questions with Model Answers

**🎯 Junior:** _"What's the fundamental difference between how SQS and Kinesis handle a message/record once it's been read?"_
**Model answer:** In SQS, once a message is successfully processed, the consumer deletes it and it's gone — the queue held it only until one consumer finished with it. In Kinesis, a record stays in the stream for its full retention period regardless of whether it's been read, and multiple independent consumer applications can each read through the same stream at their own pace, tracking their own position — reading a record in Kinesis doesn't remove it or affect any other consumer's ability to read it too.

**🎯 Intermediate:** _"Explain what a partition key does in Kinesis and why choosing a bad one causes throughput problems."_
**Model answer:** The partition key, supplied by the producer on every record, is hashed by Kinesis to deterministically decide which shard the record goes to, and it also guarantees that all records sharing the same key land on the same shard in write order — giving per-key ordering. If the chosen key has very low cardinality — say, a constant value, or just a handful of distinct values across a high-volume stream — most or all records get routed to the same one or two shards no matter how many total shards the stream has, creating a hot shard that throttles at that shard's fixed throughput ceiling while the rest of the stream's shards sit idle. The fix is choosing a key with high cardinality relative to volume, like a user ID or device ID, that both distributes load evenly and still gives meaningful per-entity ordering.

**🎯 Senior:** _"Three separate teams each need to independently consume the same real-time order-event stream — one for fraud detection, one for a live dashboard, one for a nightly-batch-style analytics pipeline that periodically needs to replay the last several hours. How does Kinesis's model support this, and what would you configure?"_
**Model answer:** Kinesis's log-based, multi-consumer model is exactly suited to this — since reading doesn't remove records, all three teams can independently subscribe to the same stream, each tracking their own position, with zero coordination or interference between them, which SQS's single-consumer-per-message model couldn't support without either duplicating the data into three separate queues or building custom fan-out. Set the stream's retention period generously enough to cover the analytics team's replay window (several hours, so probably fine at the 24-hour default, but I'd confirm their actual worst-case replay need and extend retention if it exceeds that). Also register each of the three consumer applications for Enhanced Fan-Out, since three genuinely independent, presumably latency-sensitive consumers sharing the default 2 MB/s per-shard read pool risks them throttling each other, especially the real-time dashboard and fraud-detection use cases.

**🎯 Architect:** _"Design a Kinesis-based pipeline that guarantees per-customer event ordering at very high aggregate throughput (millions of events/second across all customers), while remaining resilient to a single customer suddenly generating a disproportionate burst of traffic."_
**Model answer:** Use the customer ID as the partition key, which guarantees all of one customer's events land on the same shard in write order, satisfying per-customer ordering, while distributing the overall high aggregate volume across many shards since there are presumably many customers (high key cardinality relative to volume). For the burst-resilience concern specifically — a single customer's traffic spiking disproportionately would concentrate onto that one customer's assigned shard and could throttle it even though the rest of the stream has capacity — consider whether strict single-shard ordering per customer is truly required at the individual-event level, or whether it's acceptable to sub-partition a very high-volume customer's key (e.g., appending a bounded random or hash-based suffix to spread across a few shards) at the cost of only guaranteeing ordering within each sub-partition rather than globally per customer; this is a genuine trade-off to surface explicitly to the business rather than silently deciding, since it changes the ordering guarantee. Also favor On-Demand mode or proactively provisioned shard headroom given the described unpredictable burst pattern, and alarm on `WriteProvisionedThroughputExceeded` specifically scoped per-shard (via detailed shard-level metrics) to catch this exact hot-customer scenario early.

## 18. Common Misconceptions

- "More shards always means better performance." False if partition keys are low-cardinality — additional shards only help if the key distribution actually spreads records across them; otherwise a hot shard remains the bottleneck regardless of total shard count.
- "Kinesis guarantees stream-wide strict ordering." False — ordering is guaranteed only _per partition key_ (per shard), not across the entire stream globally, directly analogous to FIFO SQS's per-`MessageGroupId` (not stream-wide) ordering guarantee.

## 19. Key Takeaways

🔑 Kinesis is a durable, ordered, retained log supporting many independent concurrent consumers — structurally different from SQS's single-consumer-per-message, delete-on-read model.
🔑 Partition key design is the single most consequential Kinesis decision, determining both ordering scope and load distribution across shards.
🔑 Records are retained for a configurable window regardless of consumption — `IteratorAgeMilliseconds` is the critical metric for detecting a consumer at risk of losing data to retention expiry.
🔑 Enhanced Fan-Out gives each registered consumer dedicated per-shard read throughput, essential once multiple independent applications read the same stream at full speed.
🔑 KCL abstracts away the complexity of multi-shard, multi-worker checkpoint coordination that raw `GetRecords`/`GetShardIterator` calls would otherwise require you to build yourself.

## 20. Related Concepts

- **Kinesis Data Firehose** (a simpler, delivery-focused Kinesis variant for landing streaming data into S3/Redshift/OpenSearch without custom consumer code) → next section, §65.
- **Amazon MSK** (managed Kafka, a direct alternative to Kinesis Data Streams for similar use cases) → §66; full comparison → §67.
- **Lambda event source mappings** (a common managed Kinesis consumer pattern) → §25, and SQS's analogous integration, §59.
- **SQS FIFO's per-`MessageGroupId` ordering** (a smaller-scale conceptual analogue to Kinesis's per-partition-key ordering) → §60.
