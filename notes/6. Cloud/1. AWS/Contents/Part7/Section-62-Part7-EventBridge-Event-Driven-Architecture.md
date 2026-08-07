# Part 7, Section 4: Amazon EventBridge — Event-Driven Architecture

## 1. Definition

**Plain language:** EventBridge is a serverless event router. Instead of one topic broadcasting to whoever subscribed (SNS's model), EventBridge lets you write rules that say "when an event matching this exact pattern happens, send it to this target" — across dozens of AWS services, SaaS applications, and your own custom applications, all flowing through named "event buses."

**Precise definition:** Amazon EventBridge is a serverless event bus service that ingests events from AWS services, custom applications, and third-party SaaS partners, matches them against declarative content-based rules (matching on the actual event structure and field values, not just a fixed set of message attributes), and routes matching events to one or more of 20+ target types, while also providing a schema registry, event replay, and archival.

## 2. Why It Exists / Problem It Solves

SNS ([§61](./Section-61-Part7-SNS-PubSub-Messaging.md)) fans out to subscribers based on **message attributes** you explicitly attach when publishing — the publisher has to know to set those attributes for filtering to work, and filtering is comparatively shallow (attribute matching, not deep event-content matching). It also doesn't natively understand events already flowing out of AWS services (e.g., "an EC2 instance changed state," "a CodePipeline deployment failed") — someone has to explicitly wire those into SNS.

EventBridge solves a broader problem: it is AWS's answer to **"give me a central nervous system for events across my entire AWS environment and beyond, with rich, content-aware routing, and no need to modify the producer to add new consumers or new filtering logic."** Its rules match on the actual JSON structure of the event itself (nested fields, ranges, prefixes, "exists" checks), not just a small set of hand-picked attributes — a materially more expressive filtering model. It also comes pre-wired to receive events automatically from ~200 AWS services without any producer-side integration work, and supports ingesting from external SaaS vendors (Datadog, PagerDuty, Zendesk, and others) via **partner event sources**.

**What existed before it:** CloudWatch Events (EventBridge's direct predecessor and still visible in some documentation/APIs) provided a simpler version of this for AWS-service-generated events only; EventBridge is a superset adding custom event buses, the schema registry, and SaaS partner integration.

## 3. Prerequisites and Dependencies

- **SNS** ([§61](./Section-61-Part7-SNS-PubSub-Messaging.md)): EventBridge and SNS overlap significantly in purpose; the choice between them is a common architecture decision revisited fully in [§67](./Section-67-Part7-Choosing-Integration-Pattern.md).
- **Lambda** ([§25](../Part3/Section-25-Part3-AWS-Lambda-Serverless-Compute.md)) and **Step Functions** (next section, [§63](./Section-63-Part7-StepFunctions-Orchestration.md)): the two most common EventBridge targets for actually doing something with a routed event.
- **IAM** ([§9](../Part2/Section-09-Part2-IAM-Core-Concepts.md)-[§11](../Part2/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md)): rules need permission to invoke their targets, and event buses have resource policies analogous to SNS/SQS.

## 4. Internal Working

- An **event bus** is the channel events flow through. Every account has a **default event bus** that automatically and passively receives events from most AWS services in that account (no configuration required for many service-generated events — this is different from SNS, where you must explicitly wire a service to publish to your topic). You can also create **custom event buses** for your own application-generated events, and **partner event buses**, one per subscribed SaaS integration.
- Every event is a JSON object with a standardized envelope (`source`, `detail-type`, `time`, `region`, `account`, and a `detail` object holding the event-specific payload).
- A **rule** is a pattern (an "event pattern," itself JSON) matched against incoming events on a bus. If an event's fields match the rule's pattern, EventBridge invokes every **target** configured on that rule — up to 5 targets per rule by default (soft limit, raisable).
- Matching is **structural and content-aware**: patterns can match exact values, arrays of allowed values, numeric ranges, prefixes, existence checks, and more, against arbitrarily nested fields inside the `detail` object — not just top-level message attributes as with SNS.
- **Scheduled rules** are a special rule type using either a `rate()` expression (e.g., every 5 minutes) or a `cron()` expression, letting EventBridge function as a serverless, managed cron/scheduler in addition to its event-routing role (this overlaps with, and in some respects has been superseded by, the newer dedicated **EventBridge Scheduler** feature — verify current guidance in AWS docs, as this area has evolved).

```
                          +---------------------+
   AWS Service Events --->|                     |
   (auto, no wiring)      |   Event Bus         |--> Rule 1 (pattern match) --> Lambda
                          |  (default/custom/   |
   Custom App events  --->|   partner)          |--> Rule 2 (pattern match) --> Step Functions
   (PutEvents API)        |                     |
                          |                     |--> Rule 3 (pattern match) --> SQS / SNS / Firehose / API destination
                          +---------------------+
```

## 5. Architecture & Components

| Component            | Explanation                                                                                                                                                                                                 |
| -------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Event Bus**        | The channel: default (per account, auto-receives most AWS service events), custom (your own application events), or partner (one per SaaS integration).                                                     |
| **Event**            | JSON envelope: `source`, `detail-type`, `time`, `region`, `account`, `resources`, and `detail` (the actual payload).                                                                                        |
| **Rule**             | An event pattern plus one or more targets; evaluated against every event on the bus it's attached to.                                                                                                       |
| **Event Pattern**    | JSON matching logic — supports exact match, arrays ("any of"), numeric comparisons, prefix matching, `exists`, and more.                                                                                    |
| **Target**           | What the rule invokes on a match: Lambda, Step Functions, SQS, SNS, Kinesis, Firehose, ECS task, API Gateway, API destination (arbitrary HTTPS endpoint outside AWS), and more — over 20 target types.      |
| **Schema Registry**  | Automatically infers and stores the JSON schema of events flowing through a bus, letting developers generate strongly-typed code bindings for event `detail` payloads.                                      |
| **Archive & Replay** | EventBridge can archive all (or a filtered subset of) events on a bus and later replay them against current rules — valuable for reprocessing after a bug fix or for reconstructing historical event flows. |
| **API Destinations** | A target type that lets a rule invoke an arbitrary external HTTPS API (with connection/auth management built in), extending EventBridge's routing outside AWS entirely.                                     |

## 6. Lifecycle / Workflow

1. An event occurs — either generated automatically by an AWS service, or explicitly published by your application via `PutEvents`.
2. The event lands on the relevant event bus (default, custom, or partner).
3. EventBridge evaluates every rule attached to that bus against the event.
4. For every rule whose event pattern matches, EventBridge invokes all of that rule's configured targets, in parallel, each independently.
5. Each target processes the event using its own semantics (Lambda: invoked; SQS: message enqueued; Step Functions: execution started).
6. Optionally, the event is also written to a configured archive for later replay.

## 7. Configuration

| Setting                         | Purpose                                                                                                                                                                       |
| ------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Event Pattern (on a rule)       | The JSON match criteria — the heart of EventBridge's routing logic                                                                                                            |
| `EventBusName`                  | Which bus a rule is attached to                                                                                                                                               |
| Target `RetryPolicy`            | Per-target retry attempts and max event age before giving up                                                                                                                  |
| Target `DeadLetterConfig`       | Per-target DLQ (an SQS queue) for events that exhaust retries — directly analogous to SNS subscription DLQs                                                                   |
| Resource Policy (on a bus)      | Controls cross-account `PutEvents` permission — who else can publish onto this bus                                                                                            |
| Input Transformer (on a target) | Reshapes the event before it's delivered to a target (e.g., extracting only certain fields, or restructuring the JSON) so the target doesn't have to parse the full raw event |

⚠️ **Warning:** just like SNS, EventBridge targets should have a `DeadLetterConfig` configured — without one, an event that a target repeatedly fails to process (e.g., a throttled Lambda) can be silently dropped after retries are exhausted.

## 8. Commands (Full Documentation)

### `aws events put-rule`

- **Purpose:** Creates or updates a rule — the pattern that decides which events get routed where.
- **Syntax:**
  ```
  aws events put-rule --name <rule-name> --event-pattern <JSON> [--event-bus-name <bus>] [--schedule-expression <expr>]
  ```
- **Practical example (content-based pattern):**
  ```
  aws events put-rule --name HighValueOrderRule \
    --event-pattern '{
      "source": ["custom.orders"],
      "detail-type": ["OrderPlaced"],
      "detail": {
        "amount": [{"numeric": [">", 1000]}]
      }
    }'
  ```
  **Expected output:**
  ```json
  { "RuleArn": "arn:aws:events:us-east-1:123456789012:rule/HighValueOrderRule" }
  ```
- **Important arguments:**
  - `--event-pattern`: the matching JSON — note the `numeric` operator here, matching any order amount greater than 1000, something SNS's simpler attribute filtering cannot directly express.
  - `--schedule-expression`: alternative to an event pattern, for time-based (cron/rate) rules.
- **Production usage:** rules are almost always defined via CloudFormation/Terraform/CDK for version control and review, especially as the number of rules on shared buses grows into the dozens across a large organization.
- **Common errors:** malformed event pattern JSON (a very common source of "my rule never matches" bugs) — EventBridge validates pattern syntax at creation time but logical mismatches (e.g., matching on a field name that doesn't actually exist in the real event) fail silently at match time, not at creation time.
- **Security impact:** requires `events:PutRule`; separately, each target added to the rule needs its own resource-based permission granting EventBridge invoke rights (e.g., a Lambda resource policy statement allowing `events.amazonaws.com`).
- **Troubleshooting tip:** use the EventBridge console's built-in "test pattern" / sandbox feature (paste a sample event, paste the pattern, see whether it matches) before deploying — logical pattern mismatches are otherwise very difficult to debug from CloudWatch logs alone.

### `aws events put-targets`

- **Purpose:** Attaches one or more targets to an existing rule.
- **Syntax:**
  ```
  aws events put-targets --rule <rule-name> --targets '[{"Id":"1","Arn":"<target-arn>"}]' [--event-bus-name <bus>]
  ```
- **Practical example:**
  ```
  aws events put-targets --rule HighValueOrderRule --targets '[
    {
      "Id": "FraudCheckLambda",
      "Arn": "arn:aws:lambda:us-east-1:123456789012:function:FraudCheck",
      "DeadLetterConfig": {"Arn": "arn:aws:sqs:us-east-1:123456789012:eventbridge-dlq"},
      "RetryPolicy": {"MaximumRetryAttempts": 3, "MaximumEventAgeInSeconds": 3600}
    }
  ]'
  ```
  **Expected output:**
  ```json
  { "FailedEntryCount": 0, "FailedEntries": [] }
  ```
- **Common errors:** `FailedEntryCount > 0` in the response with details in `FailedEntries` — commonly caused by the target ARN not existing, or EventBridge lacking invoke permission on that target's resource policy.
- **Security impact:** requires `events:PutTargets` on the rule; for Lambda targets specifically, the Lambda function's own resource policy must separately grant `lambda:InvokeFunction` to the `events.amazonaws.com` principal, scoped to this specific rule ARN.
- **Production usage:** input transformers are frequently attached here in production to reduce the payload a target actually receives to only what it needs, both for cost (smaller Lambda payloads) and for decoupling target code from the full raw event shape.

### `aws events put-events`

- **Purpose:** Publishes one or more custom events (up to 10 per call) onto an event bus from your own application.
- **Syntax:**
  ```
  aws events put-events --entries '[{"Source":"...","DetailType":"...","Detail":"...","EventBusName":"..."}]'
  ```
- **Practical example:**
  ```
  aws events put-events --entries '[
    {
      "Source": "custom.orders",
      "DetailType": "OrderPlaced",
      "Detail": "{\"orderId\":\"A5001\",\"amount\":1500}",
      "EventBusName": "default"
    }
  ]'
  ```
  **Expected output:**
  ```json
  {
    "FailedEntryCount": 0,
    "Entries": [{ "EventId": "8f14e45f-1234-..." }]
  }
  ```
- **Common errors:** `Detail` must be a JSON **string** (escaped), not a nested object — the same "stringified JSON" pitfall seen with SQS redrive policies.
- **Security impact:** requires `events:PutEvents` on the target bus; cross-account publishing additionally requires the target bus's resource policy to allow the publishing account.
- **Performance impact:** batching up to 10 entries per call reduces API overhead for high-volume custom event producers, mirroring SQS/SNS batching best practices.

## 9. Hands-On Example — Content-Based Routing Beyond SNS's Capability

```bash
# Rule: route only orders over $1000 to a fraud-check Lambda,
# and separately route ALL orders (regardless of amount) to an analytics queue.

aws events put-rule --name HighValueOrders --event-pattern '{
  "source": ["custom.orders"],
  "detail-type": ["OrderPlaced"],
  "detail": {"amount": [{"numeric": [">", 1000]}]}
}'
aws events put-targets --rule HighValueOrders --targets '[
  {"Id": "1", "Arn": "arn:aws:lambda:us-east-1:123456789012:function:FraudCheck"}
]'

aws events put-rule --name AllOrders --event-pattern '{
  "source": ["custom.orders"],
  "detail-type": ["OrderPlaced"]
}'
aws events put-targets --rule AllOrders --targets '[
  {"Id": "1", "Arn": "arn:aws:sqs:us-east-1:123456789012:analytics-queue"}
]'

# A single put-events call now triggers BOTH rules independently if it matches both patterns:
aws events put-events --entries '[{
  "Source": "custom.orders",
  "DetailType": "OrderPlaced",
  "Detail": "{\"orderId\":\"A5002\",\"amount\":2500}"
}]'
```

This numeric-range matching (`amount > 1000`) directly on the nested event payload is something SNS's flat message-attribute filtering cannot express without the publisher manually computing and attaching a separate `"highValue": "true"` attribute — EventBridge evaluates the actual business data in the event itself.

**Native AWS service integration example (no custom publishing code at all):**

```bash
# Automatically react to any EC2 instance entering the "stopped" state,
# using events EC2 already emits to the default bus with zero producer wiring.
aws events put-rule --name EC2StoppedAlert --event-pattern '{
  "source": ["aws.ec2"],
  "detail-type": ["EC2 Instance State-change Notification"],
  "detail": {"state": ["stopped"]}
}'
aws events put-targets --rule EC2StoppedAlert --targets '[
  {"Id": "1", "Arn": "arn:aws:sns:us-east-1:123456789012:ops-alerts"}
]'
```

## 10. Production & Enterprise Usage

- **Startups** commonly use EventBridge's scheduled rules as a lightweight, serverless cron replacement (e.g., "run this Lambda nightly") and a handful of rules reacting to core AWS service events (S3 uploads, CodePipeline state changes).
- **Enterprises** build entire event-driven architectures (EDA) around EventBridge as the central nervous system: custom event buses per business domain, dozens to hundreds of rules owned by different teams, SaaS partner integrations feeding third-party tool events (e.g., a support-ticket system) directly into internal automation, and the schema registry providing a de facto contract/documentation layer between event producers and consumers across team boundaries.
- **Cross-account event routing**: a common enterprise pattern is a central "hub" account's event bus receiving events from many "spoke" account buses (via resource policies granting cross-account `PutEvents`), enabling centralized security/compliance event monitoring across an entire AWS Organization (cross-reference [§13](../Part2/Section-13-Part2-AWS-Organizations-and-SCPs.md)).
- **Archive & Replay** is used operationally for incident recovery: if a downstream consumer had a bug that silently mishandled events for a period, the archived events can be replayed against the fixed consumer logic without needing the original producers to resend anything.

## 11. Security Considerations

- Event bus resource policies control cross-account `PutEvents` — the same two-sided permission model as SNS/SQS applies for cross-account and cross-service routing.
- Each target requires its own resource-based permission granting EventBridge invoke rights, scoped ideally to the specific rule ARN via `aws:SourceArn` — broad, unscoped grants of "any EventBridge rule may invoke this Lambda" are an avoidable over-permission.
- Sensitive data flowing through `detail` payloads should be minimized or referenced by pointer (similar to the S3-pointer pattern for oversized SQS messages) rather than embedded directly, particularly since the schema registry may surface field structures broadly within an organization.

## 12. Performance Considerations

- EventBridge's per-rule target limit (default 5, raisable) means a very "busy" rule matching many event types may need to be split into multiple more specific rules rather than accumulating targets on one.
- Input transformers reduce per-target payload size, which can meaningfully reduce Lambda cold-start/parsing overhead and cost at scale for high-volume event flows.
- Rule evaluation happens per-event against every rule on a bus; while AWS manages this scaling internally, an extremely large number of broad, overlapping rules increases operational complexity and debugging difficulty more than it typically causes a hard performance ceiling.

## 13. Monitoring

| Metric                             | What it tells you                                                                                                                          |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `Invocations` (per rule)           | How many times a rule's targets were triggered — confirms rules are actually matching as expected.                                         |
| `FailedInvocations`                | Target invocation failures — the primary signal to check DLQ configuration and target health.                                              |
| `TriggeredRules` / `MatchedEvents` | Confirms pattern-matching behavior in production, useful for validating a newly deployed rule actually fires as intended.                  |
| `ThrottledRules`                   | Indicates a rule is being throttled, often due to a downstream target's own throttling (e.g., Lambda concurrency limits) propagating back. |

## 14. Troubleshooting

| Symptom                                                     | Likely Root Cause                                                                                                                     | Fix                                                                                                         |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Rule never fires despite matching events appearing to occur | Event pattern syntax matches AWS's validation but doesn't actually match the real event's field names/values/nesting                  | Use the console's test-pattern sandbox with a real sample event; check for a typo in a nested field path    |
| Target never invoked despite rule showing as matched        | Target's resource policy doesn't grant EventBridge invoke permission                                                                  | Add the required resource-based policy statement (e.g., Lambda `add-permission` for `events.amazonaws.com`) |
| Cross-account events never arrive on the hub bus            | Spoke account's rule/bus lacks permission to `PutEvents` onto the hub bus, or hub bus resource policy doesn't allow the spoke account | Verify both sides of the cross-account resource policy                                                      |
| Some events silently missing from a downstream system       | No DLQ configured on the target; events exhausted retries and were dropped                                                            | Configure `DeadLetterConfig` on every target; consider enabling archive for the bus to allow later replay   |

## 15. Best Practices

- Always test event patterns against real sample events before deploying to production — logical mismatches fail silently, not loudly.
- Configure a DLQ on every rule target, mirroring the same discipline applied to SNS subscriptions.
- Use input transformers to shrink target payloads to only what's needed.
- Use custom event buses to logically separate domains (e.g., one bus per major business area) rather than routing everything through the single default bus in large organizations.
- Enable archiving on buses carrying business-critical events, to support replay after downstream bugs.

## 16. Anti-Patterns & Common Mistakes

- ❌ Assuming a rule "must be working" because it was created without error — pattern syntax validation at creation time does not guarantee the pattern logically matches real events; always verify against actual event samples.
- ❌ Omitting target DLQs — the exact same silent-data-loss risk as an unconfigured SNS subscription applies here.
- ❌ Routing everything through the single default event bus in a large multi-team organization, making ownership, permissions, and debugging unnecessarily tangled — custom buses per domain scale better organizationally.
- **Common misconception:** "EventBridge and SNS are redundant; pick one and standardize." In practice, many enterprise architectures use both for different purposes — SNS for simple fan-out and human-facing alerting, EventBridge for rich content-based routing and native AWS-service-event reactions — full comparison in [§67](./Section-67-Part7-Choosing-Integration-Pattern.md).

## 17. Interview Questions with Model Answers

**🎯 Junior:** _"What is EventBridge and how is it different from SNS at a high level?"_
**Model answer:** EventBridge is a serverless event bus that routes events based on rich, content-based pattern matching against the actual structure of the event, including nested fields and numeric ranges, and it automatically receives events from most AWS services with no producer-side wiring needed. SNS is simpler publish/subscribe: a producer explicitly publishes to a topic and attaches flat message attributes, and subscribers filter on those attributes. EventBridge's routing logic is generally more expressive and it has native, pre-built awareness of AWS service events that SNS doesn't have out of the box.

**🎯 Intermediate:** _"Explain how EventBridge's event pattern matching lets it express something SNS's filter policies cannot."_
**Model answer:** SNS filter policies match against message attributes that the publisher must explicitly set alongside the message — flat key-value pairs, essentially. EventBridge's event pattern matches directly against the nested structure of the event's `detail` payload itself, and supports operators like numeric comparisons (greater-than, ranges), prefix matching, and existence checks on deeply nested fields, without requiring the publisher to precompute and attach separate summary attributes. For example, routing only orders where `detail.amount > 1000` is directly expressible as an EventBridge pattern, whereas SNS would require the publisher to compute a boolean "isHighValue" attribute themselves and attach it at publish time.

**🎯 Senior:** _"You're building a system where multiple teams across a large AWS Organization need centralized visibility into security-relevant events (IAM changes, GuardDuty findings, Config rule violations) generated across many separate AWS accounts. How would you use EventBridge?"_
**Model answer:** Set up a central "security hub" account with its own custom EventBridge bus, and configure a resource policy on that bus permitting `PutEvents` from every account in the Organization (often scoped via an AWS Organizations condition rather than listing every account ID individually). In each spoke account, create a rule on the default bus (which automatically receives the relevant native AWS service events like IAM changes and GuardDuty findings with no extra wiring) with a target that forwards matching events to the central hub bus. The hub account then owns the actual response logic — rules matching on event type routing to different Lambda functions, Step Functions workflows, or a ticketing system — giving a single, centrally-managed point of security-event response logic while each spoke account only needs a lightweight forwarding rule, not full duplicated response logic per account.

**🎯 Architect:** _"A previously deployed EventBridge target had a bug that silently dropped a category of business-critical events for two weeks before being caught. How do you both detect this class of failure earlier next time, and recover the lost two weeks of events?"_
**Model answer:** For detection: ensure every rule target has a DeadLetterConfig, and alarm actively on the DLQ's depth metric and on the rule's own FailedInvocations CloudWatch metric — a silent drop with no DLQ and no alarm is exactly the failure mode described, so the fix going forward is making failures loud rather than silent. For recovery: this depends on whether bus-level archiving was enabled during that window; if it was, EventBridge's native replay feature can resend the exact archived events from that two-week window against the now-fixed target logic without requiring the original producers to regenerate anything. If archiving wasn't enabled, recovery is only possible if the original producing systems retain enough state to reconstruct and republish equivalent events — which argues strongly for enabling archiving proactively on any bus carrying business-critical events specifically to cover this exact recovery scenario.

## 18. Common Misconceptions

- "EventBridge rules fail loudly if a pattern doesn't match anything." False — a syntactically valid pattern that simply never matches real events produces no error at all; it just silently never fires, which is why sandbox-testing patterns against real samples before deployment is a real best practice, not a formality.
- "The default event bus is the only bus you need." False for larger organizations — custom buses provide domain separation, ownership clarity, and independent resource policies that the single default bus can't cleanly provide at scale.

## 19. Key Takeaways

🔑 EventBridge routes based on rich, content-aware pattern matching against the actual event structure — a materially more expressive model than SNS's flat attribute filtering.
🔑 The default event bus automatically receives most AWS service events with zero producer-side wiring — a key differentiator from SNS, where every publisher relationship must be explicitly established.
🔑 Every rule target should have a DLQ configured, exactly as with SNS subscriptions — EventBridge is not a durable store either.
🔑 Archive and replay provide a recovery mechanism SNS and SQS don't natively offer — valuable for reprocessing after downstream bugs.
🔑 EventBridge and SNS are not strictly redundant; many production architectures use both, and the choice is a recurring interview topic covered fully in [§67](./Section-67-Part7-Choosing-Integration-Pattern.md).

## 20. Related Concepts

- **Step Functions** (a very common EventBridge target for triggering multi-step workflows) → next section, [§63](./Section-63-Part7-StepFunctions-Orchestration.md).
- **SNS** (compared and contrasted directly) → [§61](./Section-61-Part7-SNS-PubSub-Messaging.md); full head-to-head comparison → [§67](./Section-67-Part7-Choosing-Integration-Pattern.md).
- **Lambda** (the most common single-action EventBridge target) → [§25](../Part3/Section-25-Part3-AWS-Lambda-Serverless-Compute.md).
- **CloudWatch Events** (EventBridge's predecessor; still referenced in some legacy contexts) → conceptually superseded, will be noted briefly where relevant in Part 8.
