# Part 7, Section 2: SQS Advanced — DLQs, FIFO, Visibility Timeout, at Scale

## 1. Definition

**Plain language:** This section covers the mechanisms that turn basic SQS ([§59](./Section-59-Part7-SQS-Fundamentals.md)) into a production-grade messaging layer: dead-letter queues (a safety net for messages that keep failing), FIFO queues (strict ordering and exactly-once processing when you need them), and the deeper mechanics of visibility timeout and scaling behavior under real load.

**Precise definition:** These are advanced SQS features layered on the base queue primitive — Dead-Letter Queues (DLQs) via redrive policies, FIFO queue semantics (ordering, message groups, deduplication), and operational patterns for tuning visibility timeout and throughput at production scale, including redrive-to-source and high-throughput FIFO mode.

## 2. Why It Exists / Problem It Solves

Basic SQS ([§1](../Part1/Section-01-Part1-What-is-AWS-and-Cloud-Computing-Fundamentals.md)) guarantees at-least-once delivery on a best-effort, unordered basis. Two real production problems remain unsolved by the basic primitive:

1. **The poison message problem:** a malformed or unprocessable message will fail every single time a consumer tries it, cycle back into the queue after visibility timeout expires, get retried, fail again — forever. Without intervention, this message consumes consumer capacity indefinitely and never surfaces as an alert; it just silently degrades throughput. DLQs solve this by giving failing messages a maximum number of attempts, after which they're moved somewhere a human can inspect them.
2. **The ordering and duplication problem:** many real workflows (financial transactions, state-machine transitions, "create order" must precede "cancel order" for the same order) cannot tolerate out-of-order or duplicate processing. FIFO queues solve this with strict per-group ordering and built-in deduplication — at the cost of throughput ceilings that don't exist on standard queues.

## 3. Prerequisites and Dependencies

- **[§59](./Section-59-Part7-SQS-Fundamentals.md)** (SQS Fundamentals) — visibility timeout, receipt handles, and the send/receive/delete lifecycle are assumed knowledge here.
- **Lambda** ([§25](../Part3/Section-25-Part3-AWS-Lambda-Serverless-Compute.md)) — Lambda has its own DLQ-adjacent concept (on-failure destinations) that is related but distinct from SQS DLQs; distinguished below.

## 4. Internal Working

### Dead-Letter Queues (DLQs)

A DLQ is not a special queue type — it's an ordinary SQS queue (standard or FIFO, matching its source queue's type) that a **redrive policy** on the source queue points to. Internally:

- Every message has a hidden **receive count**, incremented each time `ReceiveMessage` returns it.
- On each receive, SQS checks: has `receiveCount` now exceeded the `maxReceiveCount` configured in the source queue's redrive policy?
- If yes, instead of making the message visible again in the source queue after the visibility timeout, SQS moves it to the configured DLQ and preserves the body, message attributes, and original message ID, allowing correlation.
- The DLQ then behaves like any other queue: it needs its own consumer (often a human via console, or an automated alerting/reprocessing tool) or it will simply retain messages until its own retention period expires.

### FIFO Queues

FIFO (First-In-First-Out) queues add two guarantees standard queues don't have, at the cost of throughput:

- **Strict ordering** — but only _within_ the same **Message Group ID**. Messages in different groups have no ordering guarantee relative to each other; this is a deliberate design allowing parallelism (many groups can be processed by many consumers concurrently) while preserving order where it matters (within one group, e.g., all messages for one customer or one order).
- **Exactly-once processing** — achieved via **deduplication**. Every message needs a `MessageDeduplicationId` (or, if `ContentBasedDeduplication` is enabled, SQS computes a SHA-256 hash of the message body automatically). If a message with the same deduplication ID is sent again within the **5-minute deduplication interval**, SQS silently discards the duplicate rather than enqueueing it a second time. This is why "exactly-once" is precisely scoped — it is deduplication of _sends_ within a 5-minute window, not an unconditional system-wide exactly-once guarantee across all time.

```
FIFO Queue internal grouping:

MessageGroupId="customer-A"  ->  [msg1] -> [msg2] -> [msg3]   (strict order within group)
MessageGroupId="customer-B"  ->  [msg1] -> [msg2]             (strict order within group)
                                    ^
                    No ordering guarantee between customer-A's and customer-B's messages
```

- **Throughput ceiling:** standard FIFO throughput is 300 messages/second (send, receive, or delete, combined) per API action type without batching, or 3,000 messages/second with batching (10 messages per API call). **High-throughput FIFO mode** removes the per-queue ceiling by partitioning message groups internally, raising throughput further — verify exact current numeric limits against AWS docs, as these have been revised across service updates.

### Visibility Timeout at Scale

- Visibility timeout is per-message, per-receive, not per-queue-global in effect — each `ReceiveMessage` call can override the queue default via the `--visibility-timeout` parameter, and `ChangeMessageVisibility` can extend or shorten it mid-flight for a specific received message.
- **Heartbeat pattern:** for long-running jobs (e.g., a 10-minute video transcode triggered by a queue message), instead of setting a single static visibility timeout of 10+ minutes (which delays retry if the consumer genuinely crashes early), production systems periodically call `ChangeMessageVisibility` to extend the timeout in smaller increments while the job is still alive — a heartbeat. If the heartbeat stops (consumer crashed), the timeout expires at its last-extended value and the message becomes available for retry much sooner than a single giant static timeout would allow.

## 5. Architecture & Components

| Component                     | Explanation                                                                                                                                                                    |
| ----------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Redrive Policy**            | JSON config on the source queue: `{"deadLetterTargetArn": "<DLQ ARN>", "maxReceiveCount": N}`.                                                                                 |
| **Redrive Allow Policy**      | A policy _on the DLQ_ restricting which source queues are permitted to redrive into it — a safety control preventing arbitrary queues from dumping messages into a shared DLQ. |
| **MessageGroupId**            | FIFO-only, required field — defines the ordering partition.                                                                                                                    |
| **MessageDeduplicationId**    | FIFO-only — explicit dedup key; can be omitted if `ContentBasedDeduplication` is enabled on the queue.                                                                         |
| **Sequence Number**           | FIFO-only — returned with each send, reflects the message's position for ordering verification.                                                                                |
| **High-Throughput FIFO Mode** | A queue-level setting (`DeduplicationScope` and `FifoThroughputLimit` attributes) that enables per-message-group throughput scaling rather than per-queue.                     |

## 6. Lifecycle / Workflow (DLQ Redrive Cycle)

1. Message sent to source queue.
2. Consumer receives it — `receiveCount` becomes 1.
3. Processing fails (exception thrown, or consumer times out without deleting).
4. Visibility timeout expires; message becomes visible again.
5. Steps 2-4 repeat, incrementing `receiveCount` each time.
6. Once `receiveCount > maxReceiveCount`, the next visibility-timeout expiry moves the message to the DLQ instead of back to the source queue.
7. A separate DLQ consumer (or human operator via console "Start DLQ redrive" feature) inspects, fixes, and optionally **redrives** the message back to the source queue for reprocessing using the built-in DLQ redrive feature, or discards it after root-causing the failure.

## 7. Configuration

| Setting                     | Where                                       | Purpose                                                                                                                         |
| --------------------------- | ------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `RedrivePolicy`             | Source queue attribute                      | Points to DLQ ARN + sets `maxReceiveCount`                                                                                      |
| `RedriveAllowPolicy`        | DLQ attribute                               | Restricts which source queue ARNs may target this DLQ (`allowAll`, `denyAll`, or `byQueue` with an explicit ARN list)           |
| `FifoQueue`                 | Queue attribute, set at creation, immutable | `"true"` marks the queue as FIFO (name must end `.fifo`)                                                                        |
| `ContentBasedDeduplication` | FIFO queue attribute                        | If `true`, SQS auto-generates the dedup ID from a body hash; if `false`, caller must supply `MessageDeduplicationId` explicitly |
| `DeduplicationScope`        | FIFO queue attribute                        | `queue` (default) or `messageGroup` — required set to `messageGroup` for high-throughput mode                                   |
| `FifoThroughputLimit`       | FIFO queue attribute                        | `perQueue` (default) or `perMessageGroupId` — the latter enables high-throughput FIFO                                           |

⚠️ **Warning:** a DLQ must be the **same queue type** as its source (standard DLQ for a standard source, FIFO DLQ for a FIFO source) — SQS enforces this and creation of a mismatched redrive policy fails validation.

## 8. Commands (Full Documentation)

### `aws sqs set-queue-attributes` (configuring a redrive policy)

- **Purpose:** Attaches or updates a queue's attributes post-creation — most commonly used to wire up a DLQ redrive policy on an existing queue.
- **Syntax:**
  ```
  aws sqs set-queue-attributes --queue-url <source-queue-url> --attributes file://redrive.json
  ```
  where `redrive.json` contains:
  ```json
  {
    "RedrivePolicy": "{\"deadLetterTargetArn\":\"arn:aws:sqs:us-east-1:123456789012:order-processing-dlq\",\"maxReceiveCount\":\"5\"}"
  }
  ```
- **Important arguments:** `RedrivePolicy` value must be a **JSON string** (escaped), not a nested JSON object — a common source of malformed-request errors.
- **Practical example output:** empty JSON `{}` on success.
- **Production usage:** almost always defined declaratively in CloudFormation/Terraform (Part 9) rather than run ad hoc, so the DLQ wiring is versioned and reviewable alongside the rest of the infrastructure.
- **Common errors:** `InvalidAttributeValue` if the DLQ ARN doesn't exist or is in a different region than the source queue (SQS DLQs must be in the _same region_ as their source queue — cross-region DLQs are not supported).
- **Security impact:** the caller needs `sqs:SetQueueAttributes` on the source queue; separately, the DLQ's own `RedriveAllowPolicy` (if restrictive) must permit this source queue ARN.
- **Troubleshooting tip:** if messages aren't appearing in the DLQ despite repeated failures, verify `maxReceiveCount` is actually being exceeded (check the queue's `ApproximateReceiveCount` message attribute in a received message body) and confirm the DLQ ARN in the policy is exactly correct.

### `aws sqs send-message` (FIFO-specific parameters)

- **Purpose:** Same core send operation as [§59](./Section-59-Part7-SQS-Fundamentals.md), but with FIFO-required parameters.
- **Syntax:**
  ```
  aws sqs send-message --queue-url <fifo-queue-url> --message-body <text> \
    --message-group-id <group> --message-deduplication-id <dedup-id>
  ```
- **Important arguments:**
  - `--message-group-id`: **required** for FIFO queues; determines the ordering partition.
  - `--message-deduplication-id`: required unless `ContentBasedDeduplication` is enabled on the queue.
- **Practical example:**
  ```
  aws sqs send-message --queue-url https://sqs.us-east-1.amazonaws.com/123456789012/orders.fifo \
    --message-body '{"orderId":"A2001","action":"create"}' \
    --message-group-id "customer-789" \
    --message-deduplication-id "A2001-create"
  ```
  **Expected output:**
  ```json
  {
    "MD5OfMessageBody": "a1b2c3...",
    "MessageId": "8f14e45f-1234-...",
    "SequenceNumber": "18849496460467756032"
  }
  ```
- **Common errors:** omitting `--message-group-id` on a FIFO queue -> `MissingParameter`; sending a duplicate `MessageDeduplicationId` within the 5-minute window silently succeeds (returns success) but the second message is discarded — this "silent" behavior surprises many engineers seeing it for the first time.
- **Production usage:** `MessageGroupId` is commonly set to a natural partition key already used elsewhere in the system (e.g., customer ID, order ID, account ID) so ordering aligns with the actual business entity that needs sequential processing.
- **Performance impact:** more message groups = more parallelism (different consumers can process different groups concurrently); a single group ID for all messages forces fully serial processing regardless of consumer count — a frequent, costly mistake (see [§16](../Part2/Section-16-Part2-GuardDuty-SecurityHub-Config-Inspector.md)).

### `aws sqs start-message-move-task` (DLQ redrive — moving messages back)

- **Purpose:** Initiates a managed redrive of messages from a DLQ back to their source queue (or another destination), without writing custom code to drain and re-publish manually.
- **Syntax:**
  ```
  aws sqs start-message-move-task --source-arn <dlq-arn> [--destination-arn <target-queue-arn>] [--max-number-of-messages-per-second <n>]
  ```
- **Practical example:**
  ```
  aws sqs start-message-move-task --source-arn arn:aws:sqs:us-east-1:123456789012:order-processing-dlq \
    --max-number-of-messages-per-second 10
  ```
  **Expected output:**
  ```json
  { "TaskHandle": "AQEB...==" }
  ```
- **Production usage:** used after a root cause is identified and fixed (e.g., a downstream dependency outage that has since recovered) to safely reprocess the backlog of failed messages at a controlled rate, rather than dumping them all back at once and re-overwhelming the same downstream dependency that originally caused the failures.
- **Security impact:** requires `sqs:StartMessageMoveTask` on the DLQ.
- **Troubleshooting tip:** use `--max-number-of-messages-per-second` deliberately conservatively when redriving after an incident — an unthrottled redrive is a common cause of "second wave" incidents.

## 9. Hands-On Example

**FIFO queue creation and use, end to end:**

```bash
# Create FIFO queue with content-based dedup
aws sqs create-queue --queue-name orders.fifo \
  --attributes '{
    "FifoQueue": "true",
    "ContentBasedDeduplication": "true",
    "VisibilityTimeout": "60"
  }'

# Create its DLQ (also must be FIFO)
aws sqs create-queue --queue-name orders-dlq.fifo \
  --attributes '{"FifoQueue": "true"}'

# Wire the redrive policy onto the source queue
aws sqs set-queue-attributes --queue-url <orders.fifo-url> --attributes '{
  "RedrivePolicy": "{\"deadLetterTargetArn\":\"<orders-dlq.fifo ARN>\",\"maxReceiveCount\":\"3\"}"
}'

# Send an ordered pair of messages for the same order
aws sqs send-message --queue-url <orders.fifo-url> \
  --message-body '{"orderId":"A3001","action":"created"}' \
  --message-group-id "A3001"

aws sqs send-message --queue-url <orders.fifo-url> \
  --message-body '{"orderId":"A3001","action":"shipped"}' \
  --message-group-id "A3001"
# Because both share MessageGroupId "A3001", "created" is guaranteed
# to be received before "shipped" by any consumer.
```

**Heartbeat pattern for long-running jobs (Python):**

```python
import boto3, time, threading

sqs = boto3.client('sqs')
queue_url = "https://sqs.us-east-1.amazonaws.com/123456789012/video-transcode-queue"

def heartbeat(receipt_handle, stop_event, extension_seconds=120):
    while not stop_event.is_set():
        sqs.change_message_visibility(
            QueueUrl=queue_url,
            ReceiptHandle=receipt_handle,
            VisibilityTimeout=extension_seconds
        )
        stop_event.wait(60)  # renew every 60s, well before the 120s extension expires

response = sqs.receive_message(QueueUrl=queue_url, MaxNumberOfMessages=1, WaitTimeSeconds=20)
for message in response.get('Messages', []):
    stop_event = threading.Event()
    hb_thread = threading.Thread(target=heartbeat, args=(message['ReceiptHandle'], stop_event))
    hb_thread.start()
    try:
        # ... long-running transcode job ...
        sqs.delete_message(QueueUrl=queue_url, ReceiptHandle=message['ReceiptHandle'])
    finally:
        stop_event.set()
        hb_thread.join()
```

## 10. Production & Enterprise Usage

- **Startups** commonly add a DLQ only after their first poison-message incident — a reactive rather than proactive pattern (see anti-patterns, [§16](../Part2/Section-16-Part2-GuardDuty-SecurityHub-Config-Inspector.md)).
- **Enterprises** treat DLQ depth as a first-class operational metric with automated alerting (CloudWatch alarm -> SNS -> PagerDuty/Slack, previewed here, full CloudWatch depth in Part 8) and a documented runbook for triage: inspect message, check for a known transient cause, decide redrive vs. manual fix vs. discard-with-audit-log.
- FIFO queues are heavily used in **financial services** (payment state machines), **e-commerce** (order lifecycle events per order ID as the group key), and **logistics/telecom** (per-device or per-shipment ordered event streams).
- **Multi-region/DR consideration:** SQS queues are regional resources; there is no built-in cross-region replication. Enterprises needing DR-level resilience for critical queues typically replicate at the application layer (dual-write to a queue in a secondary region) or rely on the broader multi-region architecture pattern rather than any native SQS cross-region feature.

## 11. Security Considerations

- `RedriveAllowPolicy` on a DLQ is a security control, not just an operational one — without it, a compromised or misconfigured queue elsewhere in the account (or, if permissions are too broad, another account) could redirect large volumes of unrelated traffic into a shared DLQ, potentially as a cost-inflation or noise-injection vector; set it to `byQueue` with an explicit allow-list in security-sensitive environments.
- DLQ messages often contain the same sensitive payload as the original message — encryption-at-rest and access-control requirements from [§59](./Section-59-Part7-SQS-Fundamentals.md) apply equally, and DLQ access should be scoped separately (often more restrictively, since DLQ inspection is typically a human/ops activity rather than an automated service).

## 12. Performance Considerations

- FIFO's throughput ceiling (verify exact current limits against AWS docs) is a hard architectural constraint — if projected order volume for a single, unavoidably-serial group (e.g., all events for one massive enterprise customer) exceeds it, FIFO alone cannot scale further for that group; reconsider whether strict ordering is truly required at that granularity, or introduce sub-partitioning.
- Using a highly granular `MessageGroupId` (e.g., per-order rather than per-customer, if orders themselves have no cross-order ordering requirement) maximizes achievable parallelism under FIFO's per-group serialization.

## 13. Monitoring

Additional metrics beyond [§59](./Section-59-Part7-SQS-Fundamentals.md)'s base set, specific to this section's features:

| Metric                                              | What it tells you                                                                                                                                                     |
| --------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `ApproximateNumberOfMessagesVisible` (on the DLQ)   | Direct signal of failure volume — the primary DLQ health alarm.                                                                                                       |
| `NumberOfMessagesMoved` (message-move-task related) | Progress of an in-flight redrive operation.                                                                                                                           |
| Per-message `ApproximateReceiveCount` attribute     | Available in the message body when received — lets a consumer log/alert on messages nearing `maxReceiveCount` before they hit the DLQ, enabling earlier intervention. |

🎯 **Interview tip:** a strong answer distinguishes "queue depth" (backlog size) from "DLQ depth" (failure rate) — conflating the two in an answer is a common signal of shallow understanding.

## 14. Troubleshooting

| Symptom                                                   | Likely Root Cause                                                                 | Fix                                                                                                                                         |
| --------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| Messages never reach DLQ despite failures                 | `maxReceiveCount` not actually exceeded, or redrive policy misconfigured/missing  | Check `ApproximateReceiveCount` on received messages; verify `RedrivePolicy` JSON is correctly escaped and DLQ ARN is exact and same-region |
| Redrive policy update rejected                            | DLQ and source queue type mismatch (standard vs FIFO)                             | Ensure both are the same type                                                                                                               |
| Duplicate message sends "vanish" silently on a FIFO queue | Expected behavior — `MessageDeduplicationId` collision within the 5-minute window | Not a bug; if unintended, verify your dedup ID generation logic is actually unique per distinct message                                     |
| FIFO queue throughput bottlenecked                        | Too few distinct `MessageGroupId` values, forcing serialization                   | Increase group granularity or enable high-throughput FIFO mode if ordering only needs to hold within smaller natural partitions             |
| DLQ redrive re-triggers the same failure immediately      | Root cause not actually fixed before redrive                                      | Confirm the underlying issue (e.g., downstream dependency) is resolved before redriving; throttle redrive rate                              |

## 15. Best Practices

- Always set a DLQ with a deliberately chosen `maxReceiveCount` — 3-5 is a common starting point, tuned based on how many transient-failure retries are reasonable for your workload.
- Set a `RedriveAllowPolicy` on every DLQ in security-conscious environments.
- Choose `MessageGroupId` granularity based on actual business ordering requirements — don't default to a single group "just in case," as it silently serializes your entire pipeline.
- Use the heartbeat pattern (`ChangeMessageVisibility`) for any job whose duration is variable or potentially long, rather than one large static visibility timeout guess.
- Throttle DLQ redrives (`--max-number-of-messages-per-second`) after an incident to avoid re-triggering the same downstream failure at full volume.

## 16. Anti-Patterns & Common Mistakes

- ❌ Using a single `MessageGroupId` for all messages on a FIFO queue "to be safe" — this collapses all parallelism and can make a FIFO queue perform like a single-threaded pipeline regardless of consumer count.
- ❌ Adding a DLQ only reactively, after a poison-message incident already happened in production — DLQs should be part of initial queue design, not an afterthought.
- ❌ Redriving a DLQ's full backlog at unthrottled speed immediately after "fixing" the root cause, without first validating the fix at small scale — a frequent cause of secondary incidents.
- **Common misconception:** "FIFO queues guarantee exactly-once delivery no matter what." In truth, the exactly-once guarantee is scoped to deduplication of identical `MessageDeduplicationId` values within a rolling 5-minute window — messages sent more than 5 minutes apart with the same content and no explicit dedup ID (under `ContentBasedDeduplication`) are _not_ deduplicated against each other.

## 17. Interview Questions with Model Answers

**🎯 Junior:** _"What is a dead-letter queue and why would you use one?"_
**Model answer:** A dead-letter queue is a regular SQS queue configured as the destination for messages that have failed processing too many times, based on a maxReceiveCount threshold set in the source queue's redrive policy. It exists so that a single malformed or unprocessable message doesn't cycle forever, consuming consumer capacity and hiding real backlog problems — instead it gets pulled aside after a set number of attempts so a human or an automated process can investigate it separately.

**🎯 Intermediate:** _"Explain the difference in ordering guarantees between a standard queue and a FIFO queue, and why that difference exists."_
**Model answer:** Standard queues store messages redundantly across multiple servers in multiple Availability Zones for durability and near-unlimited throughput, and that distributed storage model makes strict cross-copy ordering prohibitively expensive to guarantee at scale — so standard queues make no ordering promise at all. FIFO queues trade away some of that throughput ceiling specifically to guarantee strict ordering, but only within the same MessageGroupId; different groups can still be processed in parallel with no relative ordering guarantee between them, which is what lets FIFO scale better than a single fully-serial queue while still being strictly ordered where the business actually needs it.

**🎯 Senior:** _"A FIFO queue's consumers are falling behind under load. Diagnose possible causes and propose fixes."_
**Model answer:** First check how many distinct MessageGroupId values are actually in use — if most traffic funnels through one or a small number of groups, throughput is capped by that group's strict serialization regardless of how many consumers exist, since only one message per group can be in flight at a time. If that's the bottleneck, look at whether the ordering requirement is genuinely per-customer or could be relaxed to a finer partition without violating business correctness, or enable high-throughput FIFO mode if the queue is otherwise near its per-queue ceiling with already-fine-grained groups. Also verify the visibility timeout isn't set too conservatively long, artificially slowing effective throughput by delaying retries longer than necessary on the (hopefully rare) failure case.

**🎯 Architect:** _"Design a redrive strategy for a payments DLQ after a 2-hour downstream outage that has now been resolved, where you cannot afford duplicate charges."_
**Model answer:** Before redriving anything, verify the consumer's idempotency mechanism is solid — since the DLQ messages will represent the exact same at-least-once-delivery events replayed a second time, and correctness for payments depends on that idempotency layer, not on the queue. Redrive using start-message-move-task with a conservative max-messages-per-second, monitoring the source queue's error rate and the downstream dependency's health in real time, ready to pause the redrive if errors reappear. Also cross-check the DLQ message count against the outage window's expected order volume to confirm the redrive covers the full backlog and nothing was separately lost, and keep an audit log entry for every DLQ message processed, both redriven and manually resolved, given the regulatory sensitivity of payment data.

## 18. Common Misconceptions

- "DLQs automatically retry messages back into the source queue." False — moving a message _into_ a DLQ is automatic; moving it _back out_ (redrive) is a separate, deliberate action (via `start-message-move-task` or manual reprocessing).
- "FIFO queues can't scale." Partially false — high-throughput FIFO mode and fine-grained MessageGroupId partitioning both meaningfully raise achievable throughput; the real constraint is how much genuine ordering your business logic actually requires within one partition.

## 19. Key Takeaways

🔑 A DLQ is just a normal queue targeted by a source queue's redrive policy once `maxReceiveCount` is exceeded.
🔑 FIFO ordering is guaranteed only within a `MessageGroupId` — group granularity is the main lever for FIFO throughput.
🔑 FIFO "exactly-once" means deduplication within a 5-minute window, not an unconditional lifetime guarantee.
🔑 The heartbeat pattern (`ChangeMessageVisibility`) is the production-grade answer to "how long should visibility timeout be?" for variable-duration jobs.
🔑 Throttled, validated redrives prevent DLQ recovery from becoming a second incident.

## 20. Related Concepts

- **SNS** (pub/sub, often paired with SQS to fan out one event to multiple queues) → next section, [§61](./Section-61-Part7-SNS-PubSub-Messaging.md).
- **Lambda on-failure destinations** (a related but distinct DLQ-like concept specific to async Lambda invocations) → previously touched in [§25](../Part3/Section-25-Part3-AWS-Lambda-Serverless-Compute.md); worth contrasting explicitly with SQS DLQs.
- **CloudWatch alarms on queue metrics** → full depth in Part 8.
