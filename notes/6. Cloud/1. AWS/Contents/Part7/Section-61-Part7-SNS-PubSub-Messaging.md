# Part 7, Section 3: Amazon SNS — Pub/Sub Messaging

## 1. Definition

**Plain language:** Amazon Simple Notification Service (SNS) lets one event trigger many different destinations at once. You publish a single message to a "topic," and SNS instantly pushes a copy of it out to every subscriber of that topic — email addresses, SQS queues, Lambda functions, HTTP endpoints, mobile push notifications, SMS — without the publisher needing to know or care who's listening.

**Precise definition:** SNS is a fully managed publish/subscribe (pub/sub) messaging service that decouples message producers from an arbitrary, dynamically configurable set of consumers by pushing each published message to every currently active subscription on a topic, supporting fan-out to multiple heterogeneous protocol types (SQS, Lambda, HTTP/S, email, SMS, mobile push, Firehose) with optional filtering per subscriber.

## 2. Why It Exists / Problem It Solves

SQS ([§59](./Section-59-Part7-SQS-Fundamentals.md)-[§60](./Section-60-Part7-SQS-Advanced-DLQ-FIFO-VisibilityTimeout.md)) is fundamentally **point-to-point**: one message is consumed by exactly one consumer of that queue (even with multiple consumer instances polling the same queue, each individual message goes to only one of them). This is the wrong model when the same event needs to trigger multiple, independent, unrelated downstream actions — for example, "an order was placed" might need to simultaneously: (a) update inventory, (b) send a confirmation email, (c) notify the fulfillment system, and (d) feed an analytics pipeline. Building this with SQS alone would require the producer to know about and explicitly send to four separate queues — tightly coupling the producer to every consumer that might ever exist, and requiring producer code changes every time a new consumer is added.

SNS solves this with the **publish/subscribe pattern**: the producer publishes once, to one topic, with zero knowledge of who (or how many subscribers) will receive it. New consumers can subscribe to the topic at any time without any change to the producer whatsoever — this is a materially different, more scalable form of decoupling than SQS alone provides.

**What existed before it:** self-hosted pub/sub brokers (RabbitMQ exchanges, Kafka topics before MSK existed as a managed option, custom webhook-fan-out services) requiring the same operational burden SQS eliminated for point-to-point queuing.

## 3. Prerequisites and Dependencies

- **SQS** ([§59](./Section-59-Part7-SQS-Fundamentals.md)-[§60](./Section-60-Part7-SQS-Advanced-DLQ-FIFO-VisibilityTimeout.md)): the most common SNS subscriber type is an SQS queue; the "fan-out" pattern (SNS -> multiple SQS queues) is one of the most frequently tested architecture patterns in interviews and is covered fully below.
- **IAM** ([§9](../Part2/Section-09-Part2-IAM-Core-Concepts.md)-[§11](../Part2/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md)): topic access policies follow the same resource-policy model as SQS queue policies and S3 bucket policies.
- **Lambda** ([§25](../Part3/Section-25-Part3-AWS-Lambda-Serverless-Compute.md)): a common direct SNS subscriber type.

## 4. Internal Working

- A **topic** is a named, logical access point — not a physical message store the way a queue is. SNS does not hold undelivered messages indefinitely the way SQS does; delivery is attempted immediately (near real-time, typically sub-second) to every current subscriber.
- On `Publish`, SNS internally fans the single published message out to every **confirmed** subscription on that topic, in parallel, using each subscription's specific protocol adapter (SQS adapter enqueues a message; Lambda adapter invokes the function; HTTP adapter POSTs to the URL; email adapter sends via SES-like delivery; etc.).
- **Delivery retries:** for subscribers that don't immediately succeed (e.g., an HTTP endpoint temporarily returns an error, or a Lambda throttles), SNS applies a retry policy with exponential backoff, configurable per subscription — but if a subscriber never comes back up within SNS's retry window, and no DLQ is configured for that subscription, the message for that destination is lost. This is a critical distinction from SQS's default durability and is a frequent point of confusion.
- **Message filtering:** each individual subscription can specify a **filter policy** — a JSON pattern matched against message attributes (not the body) — so that a subscriber only receives the subset of messages on the topic that matches its filter, rather than every message published. This lets one topic serve many different consumer interests without each consumer having to receive-and-discard irrelevant messages.

```
                         +--------------+
                         |  SNS Topic   |
        Publish -------->| "OrderEvents"|
                         +------+-------+
                    (fan-out, parallel, near-real-time)
             +--------------------+--------------------+
             v                    v                    v
     +----------------+   +----------------+   +----------------+
     | SQS: Inventory |   | Lambda: Email  |   | SQS: Analytics |
     | (filter: none) |   |(filter:"paid") |   | (filter: none) |
     +----------------+   +----------------+   +----------------+
```

## 5. Architecture & Components

| Component                     | Explanation                                                                                                                                                                                                                                                                                                                              |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Topic**                     | The named pub/sub channel; identified by an ARN, e.g. `arn:aws:sns:us-east-1:123456789012:OrderEvents`.                                                                                                                                                                                                                                  |
| **Publisher**                 | Any caller with `sns:Publish` permission — an application, or an AWS service integration (S3 event notifications, CloudWatch Alarms, EventBridge).                                                                                                                                                                                       |
| **Subscription**              | A binding of one topic to one destination + protocol (`sqs`, `lambda`, `http`/`https`, `email`, `email-json`, `sms`, `application` for mobile push, `firehose`).                                                                                                                                                                         |
| **Subscription Confirmation** | For most protocols (notably email and HTTP/S), a subscriber must explicitly confirm the subscription (click a confirmation link, or the endpoint must respond to a confirmation handshake) before messages are actually delivered — SQS and Lambda subscriptions via the console/CLI/SDK with proper IAM permissions are auto-confirmed. |
| **Filter Policy**             | Per-subscription JSON matched against message attributes, restricting which published messages that subscriber actually receives.                                                                                                                                                                                                        |
| **Topic Policy**              | Resource-based policy on the topic controlling who can `Publish` or `Subscribe` — same model as SQS queue policies.                                                                                                                                                                                                                      |
| **FIFO Topic**                | An SNS topic variant (name ends `.fifo`) offering strict ordering and deduplication analogous to FIFO SQS queues, for use cases needing ordered fan-out.                                                                                                                                                                                 |

## 6. Lifecycle / Workflow

1. **Create** the topic (Standard or FIFO).
2. **Subscribe** one or more endpoints (SQS queue ARNs, Lambda function ARNs, HTTPS URLs, email addresses, etc.) to the topic.
3. **Confirm** subscriptions where required (email/HTTP) — SNS sends a confirmation request; the endpoint must respond/click before it starts receiving actual messages.
4. **Publish** a message to the topic, optionally with message attributes used for filtering and/or a subject (used by email subscriptions).
5. SNS **fans out** the message in parallel to every confirmed, filter-matching subscription.
6. Each subscriber processes the message using its own protocol-appropriate mechanism (SQS: the message lands in the queue and is later received/deleted per [§59](./Section-59-Part7-SQS-Fundamentals.md); Lambda: the function is invoked directly; HTTP: SNS POSTs to the endpoint and expects a 200-series response).

## 7. Configuration

| Setting                                  | Purpose                                                                                                                                                                            |
| ---------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `FilterPolicy` (subscription attribute)  | JSON pattern matched against `MessageAttributes` to scope which messages a subscriber receives                                                                                     |
| `FilterPolicyScope`                      | `MessageAttributes` (default) or `MessageBody` — the latter allows filtering on the JSON body itself rather than requiring separate attributes                                     |
| `RedrivePolicy` (subscription attribute) | Configures a DLQ for messages this specific subscription fails to deliver after retries — critical for non-SQS/Lambda subscription types that don't have SQS's inherent durability |
| `DeliveryPolicy`                         | Per-subscription retry behavior (backoff, max retries) for HTTP/S endpoints                                                                                                        |
| `Policy` (topic attribute)               | Resource-based access policy for the topic                                                                                                                                         |
| `FifoTopic`                              | Set at creation, immutable — marks the topic as FIFO                                                                                                                               |

⚠️ **Warning:** SNS subscriptions to **HTTP/HTTPS endpoints and other non-durable-by-default protocols** should always have a DLQ configured — unlike an SQS subscriber (which has its own inherent durability as a queue), a failing HTTP endpoint with no DLQ silently loses messages once SNS's retry window is exhausted.

## 8. Commands (Full Documentation)

### `aws sns create-topic`

- **Purpose:** Creates a new SNS topic.
- **Syntax:**
  ```
  aws sns create-topic --name <topic-name> [--attributes <JSON>]
  ```
- **Practical example:**
  ```
  aws sns create-topic --name OrderEvents
  ```
  **Expected output:**
  ```json
  { "TopicArn": "arn:aws:sns:us-east-1:123456789012:OrderEvents" }
  ```
- **Production usage:** typically defined in CloudFormation/Terraform alongside its subscriptions, so the full fan-out topology is versioned as code.
- **Common errors:** `InvalidParameter` for names with disallowed characters; FIFO topics require `.fifo` suffix and `FifoTopic: "true"` attribute at creation, immutable afterward.
- **Security impact:** default topic policy allows only the owning account to publish/subscribe; broader access requires an explicit topic policy.

### `aws sns subscribe`

- **Purpose:** Binds an endpoint (queue, function, URL, email, etc.) to a topic.
- **Syntax:**
  ```
  aws sns subscribe --topic-arn <arn> --protocol <protocol> --notification-endpoint <endpoint>
  ```
- **Important arguments:**
  - `--protocol`: one of `sqs`, `lambda`, `http`, `https`, `email`, `email-json`, `sms`, `application`, `firehose`.
  - `--notification-endpoint`: the ARN (for sqs/lambda/firehose), URL (for http/https), email address, or phone number, depending on protocol.
- **Practical example:**
  ```
  aws sns subscribe --topic-arn arn:aws:sns:us-east-1:123456789012:OrderEvents \
    --protocol sqs \
    --notification-endpoint arn:aws:sqs:us-east-1:123456789012:inventory-queue
  ```
  **Expected output:**
  ```json
  {
    "SubscriptionArn": "arn:aws:sns:us-east-1:123456789012:OrderEvents:8f14e45f-1234-..."
  }
  ```
  (For SQS/Lambda subscriptions with correct permissions, the subscription is auto-confirmed and the ARN is returned immediately; for email/HTTP, the response instead contains `"SubscriptionArn": "pending confirmation"` until the endpoint confirms.)
- **Production usage:** SQS-queue and Lambda-function subscriptions are by far the most common in production fan-out architectures; email/SMS subscriptions are typically reserved for human-facing alerting (often paired with CloudWatch alarms — full depth Part 8).
- **Common errors:** subscribing an SQS queue without granting that queue's policy permission for the SNS topic to send to it results in messages appearing to "vanish" — SNS reports the publish as accepted, but the queue never actually receives the message, because the queue-side resource policy denied SNS's `sqs:SendMessage` call.
- **Security impact:** cross-service permission is required on **both** sides — the topic must allow subscribing that endpoint, and (for SQS specifically) the queue's own resource policy must explicitly trust the SNS service principal, typically scoped via `aws:SourceArn` to this specific topic.
- **Troubleshooting tip:** if a subscribed SQS queue isn't receiving messages, check the queue's access policy for an explicit `sns.amazonaws.com` principal allow statement scoped to the topic ARN — this is the single most common SNS-to-SQS fan-out misconfiguration.

### `aws sns publish`

- **Purpose:** Publishes a message to a topic, triggering fan-out to all matching subscribers.
- **Syntax:**
  ```
  aws sns publish --topic-arn <arn> --message <text> [--message-attributes <JSON>] [--subject <text>]
  ```
- **Practical example:**
  ```
  aws sns publish --topic-arn arn:aws:sns:us-east-1:123456789012:OrderEvents \
    --message '{"orderId":"A4001","status":"paid"}' \
    --message-attributes '{"status":{"DataType":"String","StringValue":"paid"}}'
  ```
  **Expected output:**
  ```json
  { "MessageId": "8f14e45f-1234-4c1e-9a2b-abcde1234567" }
  ```
- **Production usage:** application code typically uses the SDK; the `--subject` parameter is specifically used (and only meaningfully rendered) by email subscriptions as the email subject line.
- **Common errors:** `--message-attributes` type mismatches (`DataType` must exactly match the value type, e.g., `String`, `Number`, `String.Array`) cause filter policies to silently not match, which looks like "my subscriber isn't getting messages" but is actually a filter/attribute mismatch, not a delivery failure.
- **Security impact:** requires `sns:Publish` on the topic; the topic policy may further restrict which principals/services can publish.
- **Performance impact:** publish is a single logical operation regardless of subscriber count — SNS handles the fan-out internally in parallel, so publisher-side latency does not scale with the number of subscribers.

## 9. Hands-On Example — Fan-Out Pattern (SNS → Multiple SQS Queues)

```bash
# Create the topic
aws sns create-topic --name OrderEvents

# Create two independent SQS queues, each for a different downstream concern
aws sqs create-queue --queue-name inventory-queue
aws sqs create-queue --queue-name analytics-queue

# Grant each queue's policy permission for SNS to send to it (queue policy, attached via set-queue-attributes)
# Example policy statement granted on inventory-queue:
# {
#   "Effect": "Allow",
#   "Principal": {"Service": "sns.amazonaws.com"},
#   "Action": "sqs:SendMessage",
#   "Resource": "<inventory-queue ARN>",
#   "Condition": {"ArnEquals": {"aws:SourceArn": "<OrderEvents topic ARN>"}}
# }

# Subscribe both queues to the topic
aws sns subscribe --topic-arn <OrderEvents-arn> --protocol sqs \
  --notification-endpoint <inventory-queue-arn>
aws sns subscribe --topic-arn <OrderEvents-arn> --protocol sqs \
  --notification-endpoint <analytics-queue-arn>

# Publish once — both queues receive an independent copy
aws sns publish --topic-arn <OrderEvents-arn> \
  --message '{"orderId":"A4002","status":"created"}'
```

This single publish results in one message landing in `inventory-queue` and an independent copy landing in `analytics-queue` — each queue's consumers process their own copy completely independently, with their own visibility timeouts, DLQs, and retry behavior (per [§59](./Section-59-Part7-SQS-Fundamentals.md)-[§60](./Section-60-Part7-SQS-Advanced-DLQ-FIFO-VisibilityTimeout.md)), fully decoupled from each other despite originating from the same event.

**Filtering example — only "paid" events go to the email-notification Lambda:**

```bash
aws sns subscribe --topic-arn <OrderEvents-arn> --protocol lambda \
  --notification-endpoint <SendConfirmationEmail-lambda-arn>

aws sns set-subscription-attributes \
  --subscription-arn <the-subscription-arn-returned-above> \
  --attribute-name FilterPolicy \
  --attribute-value '{"status": ["paid"]}'
```

Now, publishing a message with `status: "created"` does not invoke this Lambda at all; only messages carrying the `status` attribute value `"paid"` do — reducing unnecessary invocations and letting one topic serve multiple, differently-scoped consumers cleanly.

## 10. Production & Enterprise Usage

- **Startups** commonly use a single SNS topic to fan out to a small number of Lambda functions for lightweight event-driven glue (e.g., "user signed up" → welcome email Lambda + analytics Lambda).
- **Enterprises** build large fan-out topologies where one topic serves dozens of subscribers across many teams and even multiple AWS accounts (cross-account SNS subscriptions are supported and common in large orgs using AWS Organizations, [§13](../Part2/Section-13-Part2-AWS-Organizations-and-SCPs.md)), each team subscribing independently to the events relevant to them without any coordination with or code change from the publishing team — a genuine organizational decoupling benefit, not just a technical one.
- SNS is the standard mechanism behind many AWS-native **operational alerting** patterns: CloudWatch Alarms publish to an SNS topic, which fans out to email, SMS, and a Lambda that posts to Slack/PagerDuty simultaneously (full CloudWatch depth in Part 8).
- **Mobile push** subscriptions (protocol `application`) integrate with Apple APNs, Google FCM, and other platform-specific push services, letting SNS serve as the backend fan-out layer for mobile notification systems in consumer apps.

## 11. Security Considerations

- Same two-layer model as SQS/S3: the publisher's IAM policy must allow `sns:Publish`, and the topic's resource policy must not deny it; for cross-account or cross-service publishing, an explicit topic policy statement is required.
- **Message attribute-based filtering happens after fan-out routing decisions but does not encrypt or restrict message _content_ from a subscriber** — filtering controls which subscribers receive a message at all, not what part of the message body they can see; this is a common point of confusion when teams assume filter policies provide data-level access control (they don't).
- SNS supports server-side encryption of a topic using KMS (cross-reference [§14](../Part2/Section-14-Part2-KMS-and-Encryption.md)), protecting message content at rest within SNS's transient storage during delivery.

## 12. Performance Considerations

- Fan-out is parallel and near-real-time; publisher latency for `Publish` does not meaningfully increase with subscriber count.
- Because SNS attempts near-immediate delivery rather than durable queuing, a **burst of publishes to a subscriber that can't keep up (e.g., an under-provisioned Lambda with concurrency limits, or a slow HTTP endpoint) can cause throttling and retries** — pairing SNS with an SQS subscriber (rather than direct Lambda) adds a buffering layer that absorbs bursts, a common production reason to route SNS → SQS → Lambda rather than SNS → Lambda directly even when a queue isn't otherwise "needed."

## 13. Monitoring

| Metric                             | What it tells you                                                                                                                                                                    |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `NumberOfMessagesPublished`        | Publish-side throughput.                                                                                                                                                             |
| `NumberOfNotificationsDelivered`   | Successful deliveries across all subscriptions.                                                                                                                                      |
| `NumberOfNotificationsFailed`      | Failed deliveries — the primary alerting signal for a broken or unreachable subscriber.                                                                                              |
| `NumberOfNotificationsFilteredOut` | Messages correctly filtered out by a subscription's filter policy — high values here are expected/healthy, not necessarily a problem, but worth distinguishing from actual failures. |

## 14. Troubleshooting

| Symptom                                                                          | Likely Root Cause                                                                                                                 | Fix                                                                                                                                                        |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Subscribed SQS queue never receives messages                                     | Queue's resource policy doesn't grant `sns.amazonaws.com` permission scoped to the topic                                          | Add the required statement to the queue policy (see [§9](../Part2/Section-09-Part2-IAM-Core-Concepts.md) example)                                          |
| Lambda subscriber never invoked despite matching events                          | Filter policy attribute-type mismatch (e.g., `Number` vs `String`), or Lambda resource-based policy missing SNS invoke permission | Verify `MessageAttributes` `DataType` exactly matches filter policy expectations; check Lambda's resource policy for `sns.amazonaws.com` invoke permission |
| HTTP/S subscription "confirmed" but messages stop arriving after initial success | Endpoint intermittently failing, no DLQ configured, retries exhausted silently                                                    | Configure a `RedrivePolicy` DLQ on the subscription; monitor `NumberOfNotificationsFailed`                                                                 |
| Email subscription never receives anything                                       | Subscription never confirmed (recipient never clicked the confirmation link)                                                      | Resend confirmation or verify the email wasn't filtered/junked                                                                                             |

## 15. Best Practices

- Always configure a DLQ on subscriptions to protocols that lack inherent durability (HTTP/S especially; Lambda also benefits from one for after-retry failures).
- Prefer SNS → SQS → consumer over direct SNS → Lambda/HTTP where burst absorption or independent per-subscriber retry/backoff control matters.
- Use filter policies to let one topic serve many differently-scoped consumers rather than creating many near-duplicate topics.
- Scope topic and queue resource policies tightly with `aws:SourceArn` conditions rather than broad service-principal trust.

## 16. Anti-Patterns & Common Mistakes

- ❌ Subscribing an SQS queue to an SNS topic without updating the queue's own resource policy — the single most common SNS/SQS integration bug, producing "messages vanish with no error" symptoms.
- ❌ Relying on SNS alone as if it were a durable queue — for any protocol without its own storage layer (HTTP/S in particular), messages actually can be permanently lost if the endpoint is down long enough and no DLQ is configured; this is a materially different reliability profile than SQS.
- ❌ Assuming filter-policy scoping is a security control — it filters _routing_, not data visibility; anyone with access to the subscription and its resulting messages sees the full body.
- **Common misconception:** "SNS retries forever until delivery succeeds." False — retries are bounded and configurable, not infinite; beyond the retry window, delivery to that subscriber fails permanently unless a DLQ is attached.

## 17. Interview Questions with Model Answers

**🎯 Junior:** _"What's the difference between SQS and SNS?"_
**Model answer:** SQS is point-to-point — a single message is consumed by one consumer of that queue. SNS is publish/subscribe — a single published message is fanned out to every current subscriber of a topic simultaneously, and subscribers can be many different types (SQS queues, Lambda functions, HTTP endpoints, email, SMS). SQS is for buffering and decoupling one producer from one logical consumer group; SNS is for broadcasting one event to many independent, unrelated consumers at once.

**🎯 Intermediate:** _"Describe the SNS fan-out pattern and why you'd use it instead of having your application publish directly to multiple SQS queues."_
**Model answer:** In the fan-out pattern, a producer publishes once to a single SNS topic, and that topic is subscribed to by multiple SQS queues (or other endpoints), each serving a different downstream concern. The alternative — having the application code publish to each queue directly — tightly couples the producer to every consumer that currently exists, and requires a code change and redeploy of the producer every time a new consumer needs to be added. With SNS fan-out, a new team can subscribe their own queue to the existing topic with zero changes to the publisher, which is a significant decoupling win at the organizational level, not just the technical one.

**🎯 Senior:** _"A directly-subscribed HTTP endpoint under an SNS topic has been down for several hours. What happens to messages published during that window, and how would you have architected this differently to avoid data loss?"_
**Model answer:** SNS will retry delivery to that endpoint according to its configured retry/backoff policy, but that retry window is bounded, not infinite; once exhausted, any message SNS couldn't deliver to that specific subscriber is lost for that subscriber unless a DLQ was configured on the subscription — the topic itself doesn't durably retain undelivered messages the way a queue does. To avoid this, insert an SQS queue between the topic and the ultimate consumer (SNS -> SQS -> whatever processes the HTTP call), so the queue absorbs and durably holds messages during the downstream outage, and normal SQS visibility-timeout/retry/DLQ semantics apply once the consumer recovers — converting an unbounded-loss risk into a bounded, recoverable backlog.

**🎯 Architect:** _"Design a cross-account event distribution system where Team A's service publishes order events, and five other teams in five separate AWS accounts each need their own independent, durable copy of every event, with the ability to add or remove teams without ever touching Team A's code."_
**Model answer:** Team A publishes to a single SNS topic in their own account. Each of the five consuming teams creates an SQS queue in their own account and subscribes it cross-account to Team A's topic; Team A's topic policy explicitly allows `sns:Subscribe` from those specific account principals (or is more permissively opened within an AWS Organizations boundary with tighter per-queue conditions), and each consuming team's own queue resource policy grants the SNS service principal, scoped via `aws:SourceArn` to Team A's specific topic ARN, permission to send messages. Because it's SNS fan-out to SQS rather than direct HTTP subscriptions, every team gets independent durability, their own visibility timeout tuning, their own DLQ, and their own retry behavior, fully isolated from every other subscribing team. Adding a sixth team means only that team creates a queue and subscribes it — zero changes required to Team A's publishing code, topic definition, or existing subscriptions, satisfying the "never touch Team A's code" requirement directly.

## 18. Common Misconceptions

- "SNS is just SQS with more subscribers." False — the delivery model is fundamentally different: SNS pushes near-immediately with bounded retries and no default durable retention, while SQS durably holds messages until explicitly deleted or retention-expired. Combining them (SNS -> SQS) gets the benefits of both.
- "A filter policy restricts what data a subscriber can see in the message." False — filter policies control whether a message is delivered to a subscriber at all, based on message attributes; the full message body is still visible to any subscriber that does receive it.

## 19. Key Takeaways

🔑 SNS is publish/subscribe: one publish, many independent subscribers, zero producer awareness of who's listening.
🔑 SNS itself is not durable storage — protocols without their own persistence (HTTP/S especially) can lose messages after SNS's bounded retry window expires unless a DLQ is configured.
🔑 The fan-out pattern (SNS → multiple SQS queues) is the standard way to combine SNS's broadcast model with SQS's durability, and is one of the most interview-tested AWS architecture patterns.
🔑 Filter policies control message _routing_, not data-level access — they are not a security mechanism.
🔑 Cross-account SNS subscriptions require permission on both the topic side (subscribe) and, for SQS subscribers, the queue side (send message), scoped ideally via `aws:SourceArn`.

## 20. Related Concepts

- **EventBridge** (a more advanced event-routing service with richer filtering and a schema registry, often compared directly against SNS) → next section, [§62](./Section-62-Part7-EventBridge-Event-Driven-Architecture.md).
- **SQS** (the most common SNS subscriber type, and the basis of the fan-out pattern) → [§59](./Section-59-Part7-SQS-Fundamentals.md)-[§60](./Section-60-Part7-SQS-Advanced-DLQ-FIFO-VisibilityTimeout.md).
- **CloudWatch Alarms → SNS** (the standard AWS-native alerting pipeline) → previewed here, full depth Part 8.
- **KMS encryption for SNS topics** → [§14](../Part2/Section-14-Part2-KMS-and-Encryption.md).
