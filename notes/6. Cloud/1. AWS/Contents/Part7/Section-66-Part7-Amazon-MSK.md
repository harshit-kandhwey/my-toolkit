# Part 7, Section 8: Amazon MSK (Managed Streaming for Kafka)

## 1. Definition

**Plain language:** Amazon MSK (Managed Streaming for Apache Kafka) is AWS running and operating Apache Kafka — the widely-used open-source distributed streaming platform — for you. If your organization already uses Kafka, is migrating from a self-hosted Kafka cluster, or specifically wants Kafka's ecosystem and semantics (rather than Kinesis's AWS-native equivalent), MSK gives you that without having to run the brokers, handle patching, or manage ZooKeeper/KRaft consensus yourself.

**Precise definition:** Amazon MSK is a fully managed service for building and running applications on Apache Kafka, provisioning and maintaining Kafka brokers (and, in the newer KRaft mode, the metadata/consensus layer, replacing the older separate ZooKeeper dependency), handling patching, broker replacement, and scaling operations, while exposing the standard, unmodified Kafka APIs and protocol — meaning existing Kafka client libraries, tools, and application code work against MSK largely unchanged.

## 2. Why It Exists / Problem It Solves

Apache Kafka is the dominant open-source, self-hostable equivalent of what Kinesis Data Streams (Part 7 §6) provides — a durable, ordered, partitioned, replayable log supporting multiple independent consumers. Many organizations already run substantial Kafka-based infrastructure, have deep existing Kafka operational expertise, use Kafka-ecosystem tools (Kafka Connect, Kafka Streams, ksqlDB, Schema Registry) that assume genuine Kafka compatibility, or need to migrate an existing on-premises Kafka deployment to AWS with minimal application-code changes.

Self-hosting Kafka is operationally demanding: managing broker instances, handling ZooKeeper (or newer KRaft) consensus, capacity planning partitions and replication, patching for security vulnerabilities, and handling broker failure/replacement — all significant, ongoing operational burden, directly analogous to the burden SQS eliminated for point-to-point queuing (Part 7 §1) and Kinesis eliminated for AWS-native streaming.

MSK solves this specifically for organizations that need **genuine Kafka protocol compatibility** — not just "a similar streaming service," but the actual Kafka wire protocol and ecosystem — while removing the operational burden of running the cluster yourself. This is a different value proposition from Kinesis: Kinesis is AWS's own native streaming primitive with deep native integration into other AWS services (Lambda event source mappings, Firehose, etc.); MSK is "Kafka, but AWS runs it for you."

**What existed before it:** self-managed Kafka clusters on EC2, requiring the organization to handle all broker provisioning, scaling, patching, and failure recovery themselves.

## 3. Prerequisites and Dependencies

- **Kinesis Data Streams** (Part 7 §6): the direct conceptual analogue and most common point of comparison; understanding KDS's shard/partition model transfers directly to understanding Kafka's partition model.
- General **networking/VPC** knowledge (Part 4 §1): MSK clusters run within your VPC, requiring subnet, security group, and connectivity planning distinct from Kinesis's fully serverless, no-VPC-footprint model.
- Basic familiarity that Kafka itself (independent of MSK) is a pre-existing, widely adopted open-source technology, assumed here as background context rather than taught from scratch.

## 4. Internal Working

- An MSK **cluster** consists of a set of **broker** nodes (EC2-based, though the underlying instances are managed by AWS on your behalf) distributed across the Availability Zones you specify, each broker handling reads/writes for a subset of the cluster's data.
- Data is organized into **topics**, each split into **partitions** — Kafka's direct equivalent of a Kinesis shard. Each partition is an ordered, append-only log; producers can specify a key that determines which partition a record is routed to (via a hash, exactly analogous to Kinesis's partition-key-to-shard hashing), giving per-key ordering.
- Each partition is **replicated** across multiple brokers (a configurable replication factor, commonly 3) for durability — one broker holds the "leader" replica handling reads/writes for that partition, others hold "follower" replicas kept in sync, providing automatic failover if the leader broker fails.
- **Consumer groups** are Kafka's mechanism for coordinating multiple consumer instances that together process a topic's partitions — partitions are automatically divided among the active members of a consumer group, so adding more consumer instances (up to the partition count) increases parallel processing throughput, and Kafka automatically rebalances partition assignment if a consumer instance joins or leaves the group.
- **MSK Serverless** is a deployment mode that removes broker/capacity management entirely (auto-scaling partitions and throughput), trading some configuration control for Kinesis-like operational simplicity, positioned between traditional (Provisioned) MSK and the fully serverless Kinesis model.
- **KRaft mode** (the modern Kafka consensus mechanism, replacing the historical dependency on a separate ZooKeeper ensemble) is increasingly the default/recommended metadata management approach for newer Kafka and MSK deployments — verify current MSK guidance on ZooKeeper vs. KRaft mode against AWS docs, as this is an area that has evolved and default recommendations may have shifted.

```
MSK Cluster (within your VPC, across multiple AZs)

Topic: "orders" (3 partitions, replication factor 3)

Partition 0 [Leader: Broker A, Followers: B, C] --- key hash range 1
Partition 1 [Leader: Broker B, Followers: A, C] --- key hash range 2
Partition 2 [Leader: Broker C, Followers: A, B] --- key hash range 3

Consumer Group "order-processors":
  Consumer 1 --> assigned Partition 0
  Consumer 2 --> assigned Partition 1
  Consumer 3 --> assigned Partition 2
  (adding Consumer 4 would sit idle -- max useful parallelism = partition count)
```

## 5. Architecture & Components

| Component              | Explanation                                                                                                                                                                                |
| ---------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Cluster**            | The set of managed broker nodes, spanning your chosen Availability Zones within a VPC.                                                                                                     |
| **Broker**             | A single Kafka server node handling a subset of partitions; MSK manages provisioning, patching, and replacement.                                                                           |
| **Topic**              | A named category of records, divided into partitions.                                                                                                                                      |
| **Partition**          | The unit of parallelism and ordering — directly analogous to a Kinesis shard.                                                                                                              |
| **Replication Factor** | How many broker copies of each partition are maintained for durability/failover (commonly 3).                                                                                              |
| **Consumer Group**     | A set of coordinated consumer instances sharing the work of consuming a topic's partitions, with automatic rebalancing.                                                                    |
| **MSK Connect**        | A managed Kafka Connect offering for streaming data between MSK and external systems (databases, S3, etc.) using standard Kafka Connect connectors, without self-managing Connect workers. |
| **MSK Serverless**     | The auto-scaling, no-broker-capacity-management deployment mode.                                                                                                                           |

## 6. Lifecycle / Workflow

1. **Provision** the MSK cluster (Provisioned mode: specify broker instance type, count, and storage; or Serverless mode: minimal capacity configuration), within a chosen VPC/subnets.
2. **Create topics** (via standard Kafka CLI tools or client libraries pointed at the cluster's bootstrap brokers), specifying partition count and replication factor.
3. **Producers** write records to topics, using standard Kafka client libraries (Java, Python via `kafka-python`/`confluent-kafka`, etc.) — genuinely the same client code that would work against any Kafka cluster, self-hosted or otherwise.
4. **Consumers**, organized into consumer groups, read from topic partitions, with Kafka automatically balancing partition assignment across active group members.
5. **Offsets** (Kafka's term for a consumer's read position within a partition, directly analogous to a Kinesis sequence number) are committed periodically, either automatically or explicitly by the consumer application, tracking progress durably (in Kafka's own internal `__consumer_offsets` topic).
6. AWS handles ongoing broker health monitoring, automatic replacement of failed broker instances, and (for Provisioned mode) supports both manual and auto-scaling of broker storage/count as load grows.

## 7. Configuration

| Setting                                      | Purpose                                                                                                           |
| -------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Broker instance type & count                 | Provisioned-mode capacity planning — directly affects cost and throughput ceiling                                 |
| Number of partitions (per topic)             | The primary throughput/parallelism lever, exactly as shard count is for Kinesis                                   |
| Replication factor                           | Durability vs. storage cost trade-off                                                                             |
| `min.insync.replicas` (topic/broker config)  | How many replicas must acknowledge a write before it's considered committed — a durability/latency trade-off knob |
| VPC/subnet/security group placement          | MSK clusters live inside your VPC, unlike Kinesis's fully AWS-managed, no-VPC-footprint model                     |
| Authentication (IAM, SASL/SCRAM, mutual TLS) | MSK supports IAM-based access control as an AWS-native addition on top of standard Kafka auth mechanisms          |
| Encryption (in-transit TLS, at-rest KMS)     | Standard security configuration, layered onto Kafka's native capabilities                                         |

⚠️ **Warning:** partition count, once increased, cannot be decreased for a Kafka topic — and increasing partition count after topic creation can disrupt existing key-to-partition ordering guarantees for any existing consumers relying on the original partition assignment, since the hash-to-partition mapping changes when the partition count changes. Planning partition count thoughtfully upfront matters more for Kafka/MSK than it does for Kinesis, where resharding has more built-in tooling support.

## 8. Commands (Full Documentation)

Because MSK exposes the standard Kafka protocol, most day-to-day interaction uses standard Kafka CLI tools (`kafka-topics.sh`, `kafka-console-producer.sh`, etc.) pointed at the cluster's bootstrap broker addresses, rather than AWS-specific CLI commands. The AWS CLI (`aws kafka ...`) is used primarily for cluster lifecycle management.

### `aws kafka create-cluster`

- **Purpose:** Provisions a new MSK cluster (Provisioned mode).
- **Syntax:**
  ```
  aws kafka create-cluster --cluster-name <name> --kafka-version <version> \
    --number-of-broker-nodes <n> --broker-node-group-info <JSON>
  ```
- **Practical example:**
  ```
  aws kafka create-cluster --cluster-name orders-cluster \
    --kafka-version "3.6.0" \
    --number-of-broker-nodes 3 \
    --broker-node-group-info '{
      "InstanceType": "kafka.m5.large",
      "ClientSubnets": ["subnet-abc123", "subnet-def456", "subnet-ghi789"],
      "SecurityGroups": ["sg-0123456789"]
    }'
  ```
  **Expected output:**
  ```json
  {
    "ClusterArn": "arn:aws:kafka:us-east-1:123456789012:cluster/orders-cluster/...",
    "State": "CREATING"
  }
  ```
- **Production usage:** deployed via CloudFormation/Terraform in production, given the significant number of interrelated networking, security, and capacity settings that benefit from being versioned as code.
- **Common errors:** subnet/security-group misconfiguration is a common source of cluster creation failure or subsequent client connectivity issues, since (unlike Kinesis) MSK clusters have real VPC networking to get right.
- **Security impact:** the `SecurityGroups` and subnet placement directly determine network-level access to the cluster — least-privilege network design (only allowing the specific producer/consumer application security groups) applies here exactly as with any other VPC-resident resource (Part 4).

### Standard Kafka CLI — `kafka-topics.sh` (topic creation, run against the cluster, not an AWS CLI command)

- **Purpose:** Creates a topic on the cluster — a genuinely standard Kafka operation, not an AWS-specific API.
- **Syntax:**
  ```
  kafka-topics.sh --create --topic <name> --partitions <n> --replication-factor <n> \
    --bootstrap-server <broker-endpoints>
  ```
- **Practical example:**
  ```
  kafka-topics.sh --create --topic orders --partitions 6 --replication-factor 3 \
    --bootstrap-server b-1.orders-cluster.xxxxx.kafka.us-east-1.amazonaws.com:9092
  ```
  **Expected output:**
  ```
  Created topic orders.
  ```
- **Production usage:** this exact command (and the exact underlying Kafka protocol behavior) is identical to what would be run against a self-hosted Kafka cluster — a genuinely important point about MSK's value proposition: existing Kafka operational knowledge, tooling, and scripts transfer directly, unlike a service with a proprietary API.
- **Common errors:** connectivity failures here almost always trace back to VPC/security-group/subnet configuration rather than the Kafka command itself, given MSK's real network presence inside your VPC.
- **Security impact:** if IAM-based authentication is enabled on the cluster, client tooling needs to be configured with the appropriate SASL/IAM mechanism rather than connecting unauthenticated — a meaningfully different setup step than Kinesis's pure IAM-API-call model.

## 9. Hands-On Example — Producer/Consumer Using Standard Kafka Client Libraries

```python
# Producer -- using confluent-kafka, genuinely the same code pattern as for self-hosted Kafka
from confluent_kafka import Producer

conf = {
    'bootstrap.servers': 'b-1.orders-cluster.xxxxx.kafka.us-east-1.amazonaws.com:9092',
    'security.protocol': 'SASL_SSL',       # if using IAM auth
    'sasl.mechanism': 'AWS_MSK_IAM',
}
producer = Producer(conf)
producer.produce('orders', key='customer-789', value='{"orderId":"A7001","action":"created"}')
producer.flush()

# Consumer -- consumer group coordination is automatic
from confluent_kafka import Consumer

consumer = Consumer({
    'bootstrap.servers': 'b-1.orders-cluster.xxxxx.kafka.us-east-1.amazonaws.com:9092',
    'group.id': 'order-processors',
    'auto.offset.reset': 'earliest',
    'security.protocol': 'SASL_SSL',
    'sasl.mechanism': 'AWS_MSK_IAM',
})
consumer.subscribe(['orders'])

while True:
    msg = consumer.poll(1.0)
    if msg is not None and not msg.error():
        print(f"Received: {msg.value()} from partition {msg.partition()}")
        consumer.commit(msg)  # explicit offset commit after successful processing
```

This is deliberately, meaningfully identical in structure to code that would run against any Kafka cluster anywhere — the entire value proposition of MSK over a fundamentally different service like Kinesis is exactly this: your Kafka expertise, client libraries, and operational tooling transfer directly, with AWS only removing the broker-operations burden underneath.

## 10. Production & Enterprise Usage

- **Startups** rarely reach for MSK as a first choice unless the team already has specific Kafka expertise or existing Kafka-dependent tooling — Kinesis or SQS/SNS are typically the lower-friction starting point for greenfield AWS-native applications.
- **Enterprises** commonly choose MSK specifically in **migration scenarios** (an existing on-premises or self-hosted-on-EC2 Kafka deployment moving to a managed AWS offering with minimal application code changes) or when **genuine Kafka-ecosystem compatibility** is a hard requirement — using Kafka Streams for stream processing, ksqlDB for streaming SQL, Kafka Connect for a broad ecosystem of existing connectors, or Confluent Schema Registry-compatible tooling that expects true Kafka wire-protocol compatibility.
- **MSK Connect** lets enterprises use the large existing ecosystem of open-source and commercial Kafka Connect connectors (database CDC connectors, S3 sink connectors, and many others) without self-hosting Connect workers.
- Large enterprises with substantial pre-existing Kafka operational investment (monitoring, tooling, runbooks, trained staff) often find migrating to MSK preserves that investment far better than a wholesale rewrite to a different streaming paradigm like Kinesis would.

## 11. Security Considerations

- MSK supports **IAM-based authentication and authorization** as an AWS-native addition to Kafka's standard security mechanisms (mutual TLS, SASL/SCRAM), letting IAM policies control topic-level access exactly as they control access to other AWS resources — a meaningful convenience over self-hosted Kafka's typically separate credential/ACL management.
- Because MSK clusters run within your VPC, standard VPC security controls (security groups, network ACLs, private subnet placement, VPC endpoints) apply directly — a materially different security surface area than the fully AWS-managed, no-VPC-footprint model of Kinesis or SQS/SNS.
- Encryption in transit (TLS) and at rest (KMS) are configurable, layered onto Kafka's native transport, matching the equivalent guarantees available in Kinesis.

## 12. Performance Considerations

- Partition count is the primary throughput/parallelism lever, and — as with Kinesis shard/partition-key design — an evenly distributed record key is essential to avoid a "hot partition" bottlenecking a topic regardless of total partition count.
- Consumer group parallelism is capped by partition count (one partition can only be actively consumed by one consumer within a given group at a time) — exactly the same structural constraint as Kinesis's per-shard consumption model.
- `min.insync.replicas` and related durability settings trade off write latency against durability guarantees — a lower requirement is faster but risks data loss on broker failure before full replication; a higher requirement is safer but slower.

## 13. Monitoring

| Metric                                                                                           | What it tells you                                                                                                                                                                                                        |
| ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `UnderReplicatedPartitions`                                                                      | Broker/replication health — a nonzero value signals a durability risk requiring investigation.                                                                                                                           |
| `BytesInPerSec` / `BytesOutPerSec`                                                               | Cluster-level throughput, useful for capacity planning.                                                                                                                                                                  |
| Consumer group lag (`kafka-consumer-groups.sh --describe`, or CloudWatch-integrated equivalents) | How far behind a consumer group is from the latest offset — directly analogous to Kinesis's `IteratorAgeMilliseconds` and SQS's age-of-oldest-message metrics; the primary "is my pipeline keeping up" signal for Kafka. |
| `ActiveControllerCount`                                                                          | Cluster-level health signal specific to Kafka's controller/consensus mechanism (relevant to both ZooKeeper-based and KRaft-based clusters).                                                                              |

## 14. Troubleshooting

| Symptom                                 | Likely Root Cause                                                                                          | Fix                                                                                                                                                                                           |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Clients can't connect to the cluster    | VPC/security-group/subnet misconfiguration                                                                 | Verify security group rules allow the client's source, and subnet routing is correct — the most common MSK-specific (vs. plain-Kafka) troubleshooting category, given MSK's real VPC presence |
| Consumer group lag growing steadily     | Consumer processing slower than production rate, or too few consumer instances relative to partition count | Scale out consumer instances (up to partition count) or optimize per-record processing time                                                                                                   |
| Uneven partition load ("hot partition") | Low-cardinality or poorly distributed record key                                                           | Redesign the key for better distribution, exactly as with Kinesis partition-key design                                                                                                        |
| `UnderReplicatedPartitions` nonzero     | A broker is down, slow, or struggling to keep replicas in sync                                             | Investigate broker health; AWS handles automatic broker replacement, but sustained replication issues may indicate a capacity or configuration problem                                        |

## 15. Best Practices

- Plan partition count deliberately upfront — increasing later is possible but can disrupt existing key-to-partition ordering assumptions for consumers relying on it.
- Use IAM-based authentication where it fits the organization's existing AWS access-control model, rather than defaulting to separately managed SASL/SCRAM credentials, for operational consistency with the rest of the AWS environment.
- Monitor consumer group lag as the primary pipeline-health signal, exactly as with Kinesis's iterator age or SQS's oldest-message age.
- Scope security groups and subnet placement tightly, treating the MSK cluster's VPC presence with the same network-security rigor as any other VPC-resident resource.
- Choose MSK deliberately for genuine Kafka-ecosystem or migration needs — don't default to it over Kinesis without a concrete reason tied to Kafka-specific compatibility requirements.

## 16. Anti-Patterns & Common Mistakes

- ❌ Choosing MSK by default for a new, greenfield AWS-native application with no existing Kafka investment or ecosystem requirement — Kinesis is typically the lower-operational-friction, more natively-integrated choice absent a specific reason to need genuine Kafka compatibility.
- ❌ Under-provisioning partition count at topic creation, then being surprised at the ordering implications of increasing it later.
- ❌ Treating MSK's VPC-networked nature as equivalent to Kinesis's fully-managed, no-VPC-footprint model — MSK genuinely requires real subnet/security-group/connectivity planning that Kinesis does not.
- **Common misconception:** "MSK and Kinesis are basically the same service with different names." False in an operationally important way — MSK requires VPC networking design and Kafka-specific operational knowledge (even though AWS manages the brokers), while Kinesis is fully serverless with zero VPC footprint and deep native AWS service integration (Lambda event source mappings, Firehose) that MSK approximates via its own separate integrations (MSK Connect, Lambda-Kafka event source mapping) but doesn't share identically.

## 17. Interview Questions with Model Answers

**🎯 Junior:** _"What is Amazon MSK, and why would an organization choose it over Kinesis?"_
**Model answer:** MSK is AWS's managed version of Apache Kafka — it runs the actual Kafka brokers and protocol for you, so existing Kafka client code, tools, and ecosystem components work against it largely unchanged. An organization would choose it over Kinesis specifically when they already have Kafka expertise, existing Kafka-dependent applications or tooling they're migrating to AWS, or a hard requirement for genuine Kafka-ecosystem compatibility, like using Kafka Streams or ksqlDB — Kinesis is AWS's own separate, natively-integrated streaming service, not a Kafka-compatible one.

**🎯 Intermediate:** _"Compare Kafka partitions and Kinesis shards — how similar are they conceptually, and where do the operational differences show up?"_
**Model answer:** Conceptually they're very similar — both are the fundamental unit of ordering and parallelism within a stream/topic, both use a key hashed to deterministically assign records to a partition/shard, and both cap consumer parallelism at the partition/shard count for a single consumer group or application. The operational differences show up mainly around how each is managed: Kinesis shard count is directly configurable per stream with resharding operations Kinesis manages, and Kinesis has no VPC footprint at all, while Kafka partition count for MSK requires more upfront planning since increasing it later can disrupt existing key-to-partition ordering assumptions, and MSK clusters live inside your VPC requiring real subnet and security group configuration that Kinesis simply doesn't need.

**🎯 Senior:** _"Your organization is migrating an on-premises Kafka-based data pipeline, including several Kafka Connect connectors and a ksqlDB deployment, to AWS. Would you recommend MSK or Kinesis, and why?"_
**Model answer:** MSK, fairly clearly, given the stated dependency on genuine Kafka-ecosystem components — Kafka Connect connectors and ksqlDB both assume real Kafka wire-protocol compatibility and won't work against Kinesis without a substantial compatibility-shim or rewrite effort. MSK's entire value proposition is preserving exactly this kind of existing Kafka investment while removing the broker-operations burden, so the existing Connect connectors and ksqlDB deployment should largely continue working with configuration changes (endpoints, authentication) rather than a full re-architecture. Plan the VPC networking and security group design carefully as part of the migration, since that's a genuinely new operational concern MSK introduces that the on-premises deployment presumably already had its own equivalent of, but which needs deliberate translation into AWS's networking model.

**🎯 Architect:** _"Design the topic/partition strategy for an MSK-based order-processing pipeline that must support at least 50 concurrent consumer instances for parallel processing, with per-customer ordering, and must gracefully accommodate future growth without breaking existing ordering guarantees."_
**Model answer:** Partition count needs to be at least 50 to allow up to 50 concurrent consumer instances within a single consumer group to each get their own partition (Kafka's parallelism ceiling is the partition count) — provision meaningfully above that, perhaps 100-200 partitions, to leave headroom for future consumer-instance growth without needing a partition-count change later, since increasing partition count after the fact changes the key-to-partition hash mapping and can silently break the ordering assumptions any downstream consumer logic has come to rely on. Use customer ID as the partition key to guarantee all of one customer's events land on the same partition in order, and explicitly document the initial partition count decision and its headroom rationale so that if partition count does eventually need to increase, the team makes that decision deliberately, understanding it resets the key-to-partition mapping, rather than discovering the ordering implications after the fact during an unrelated capacity-driven change.

## 18. Common Misconceptions

- "MSK is a proprietary AWS streaming API, similar to Kinesis." False — MSK exposes the genuine, standard Kafka protocol; this is precisely its differentiator and value proposition versus Kinesis.
- "MSK requires zero operational awareness since AWS manages it." Partially false — AWS manages broker provisioning, patching, and replacement, but partition/topic design, VPC networking, consumer group management, and Kafka-specific tuning remain the operator's responsibility, unlike Kinesis's more fully abstracted, serverless model.

## 19. Key Takeaways

🔑 MSK is genuine, standard Apache Kafka, managed by AWS — existing Kafka client code, tooling, and ecosystem components (Connect, Streams, ksqlDB) work against it largely unchanged.
🔑 Kafka partitions and Kinesis shards are conceptually near-identical (ordering + parallelism unit, key-hashed assignment), but MSK's VPC-networked nature and more manual partition-count planning are real operational differences from Kinesis's fully serverless model.
🔑 Choose MSK specifically for genuine Kafka-ecosystem compatibility or migration needs; choose Kinesis for greenfield AWS-native streaming with deeper native service integration and zero VPC footprint.
🔑 Consumer group lag is Kafka's primary pipeline-health metric, directly analogous to Kinesis's iterator age and SQS's oldest-message age.
🔑 Partition count planning matters more upfront for Kafka/MSK than for Kinesis, since increasing it later can disrupt existing consumer ordering assumptions.

## 20. Related Concepts

- **Kinesis Data Streams** (the direct AWS-native conceptual analogue, compared throughout this section) → Part 7 §6; full head-to-head decision framework → next section, Part 7 §9.
- **VPC networking** (required background for MSK's real network presence) → Part 4 §1.
- **IAM** (for MSK's IAM-based authentication option) → Part 2 §1-3.
- **MSK Connect / Kafka Connect ecosystem** — a natural extension topic beyond this roadmap for anyone building substantial MSK-based data integration pipelines.
