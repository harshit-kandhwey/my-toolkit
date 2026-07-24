# Section 30 — Cosmos DB

## 30.1 Definition

**Plain language:** Cosmos DB is Azure's globally distributed database — you can spread a single database across multiple regions worldwide, with each region able to read (and optionally write) data, and choose exactly how strictly "up to date" every region's copy needs to be, trading consistency for speed as your application requires.

**Precise definition:** Azure Cosmos DB is a fully managed, globally distributed, multi-model NoSQL database service, providing turnkey multi-region replication (including optional multi-region writes), guaranteed low single-digit-millisecond latency at defined percentiles, elastic and independent scaling of throughput and storage, and a choice of five well-defined consistency levels balancing consistency against latency and availability.

## 30.2 Why It Exists / Problem It Solves

Azure SQL Database and Managed Instance (Section 29), while capable of some geo-replication, are fundamentally relational databases designed around a traditional single-primary-region model with a defined schema. Many modern application patterns — globally distributed user bases needing low-latency access from anywhere, rapidly evolving or inherently non-relational data shapes (documents, key-value pairs, graphs), and massive horizontal scale requirements — don't fit this model well. Cosmos DB exists specifically to serve these patterns: true multi-region active distribution designed in from the ground up (not retrofitted onto a relational engine), flexible schema-less or semi-structured data models suited to rapidly evolving application needs, and elastic, independently-scalable throughput designed for unpredictable or massive-scale workloads.

## 30.3 Core Concepts

### 30.3.1 Multi-Model APIs

Cosmos DB supports multiple data-access APIs on top of the same underlying globally-distributed engine, letting developers work with the data model and API most natural to their application:

- **NoSQL API (formerly SQL API)** — a JSON document model queried using a SQL-like query language, the native and most fully-featured Cosmos DB API.
- **MongoDB API** — wire-protocol compatible with MongoDB, allowing existing MongoDB applications/drivers to work against Cosmos DB with minimal changes.
- **Cassandra API** — compatible with Apache Cassandra's wire protocol, for applications built around Cassandra's wide-column data model.
- **Table API** — provides Azure Table Storage-compatible access (referenced back in Section 16.3.2) but with Cosmos DB's global distribution and richer throughput/scaling capabilities layered on top.
- **Gremlin API** — for graph data models, supporting graph traversal queries.

⚠️ Exact API names (particularly the "NoSQL API" naming, which has itself evolved from "SQL API") and their specific current feature-parity levels relative to their native counterparts (e.g., how closely the MongoDB API tracks current MongoDB versions) should be verified against official documentation, since this is an actively evolving area of the service.

💡 **Tip:** A common point of confusion: choosing the MongoDB or Cassandra API doesn't mean you're running actual MongoDB or Cassandra software — it means Cosmos DB's own engine is speaking that protocol/wire format, allowing compatible client drivers and tools to connect, while the underlying storage, distribution, and scaling engine is entirely Cosmos DB's own.

### 30.3.2 Partitioning

**Definition:** Cosmos DB achieves horizontal scalability by **partitioning** data across multiple underlying physical partitions based on a **partition key** — a property chosen from your data that determines which logical/physical partition a given item is stored in.

**Why partition key choice matters critically:** A well-chosen partition key distributes data (and the read/write traffic against it) evenly across partitions, allowing the database to scale smoothly; a poorly-chosen partition key (one with low cardinality, or one where a small number of key values receive disproportionate traffic — a "hot partition") can create a scalability and performance bottleneck that no amount of provisioned throughput can fully resolve, since all the traffic funneling to that hot partition is still constrained by that single partition's own throughput ceiling regardless of how much total throughput is provisioned across the container as a whole.

⚠️ Partition key selection is effectively a foundational, difficult-to-change-later design decision (changing a partition key typically requires migrating data into a new container) — this makes upfront partition key design one of the most consequential Cosmos DB architectural decisions, deserving careful analysis of actual query and write patterns before committing to a specific property.

### 30.3.3 Consistency Levels

Cosmos DB offers five consistency levels, forming a spectrum trading data consistency (how "fresh" and ordered reads are guaranteed to be relative to writes) against latency, availability, and throughput:

| Consistency Level     | Guarantee                                                                                                                     | Trade-off                                                                                                                                           |
| --------------------- | ----------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Strong**            | Reads always return the most recent committed write, with linearizability guarantees                                          | Highest latency, most restrictive availability during network partitions                                                                            |
| **Bounded Staleness** | Reads lag behind writes by at most a configurable time window or number of versions                                           | Strong-like guarantees within a bounded, tunable staleness window                                                                                   |
| **Session**           | Within a single client "session," reads are guaranteed consistent with that session's own prior writes (read-your-own-writes) | The most commonly used default — strong guarantees for the writing client itself, more relaxed for other clients, with good latency characteristics |
| **Consistent Prefix** | Reads never see out-of-order writes (they may be behind, but never see writes applied "out of sequence")                      | Weaker than Session, but stronger ordering guarantee than Eventual                                                                                  |
| **Eventual**          | Reads may return any previously written value, with no ordering guarantee, but will eventually converge to the latest value   | Lowest latency, highest availability, weakest consistency guarantee                                                                                 |

⚠️ Exact SLA guarantees, precise staleness-window configurability, and current default consistency level should be verified against official documentation — this is a precise, contractually-relevant part of the service (backed by formal SLAs) where exact current details matter significantly for production design decisions.

🎯 **Interview Tip:** Being able to explain this five-level consistency spectrum — and specifically why **Session** consistency is the most commonly chosen default (balancing intuitive "read your own writes" behavior against strong latency/availability characteristics) — is one of the most distinctive and frequently tested pieces of Cosmos DB-specific knowledge, differentiating candidates who've genuinely worked with the service from those with only surface familiarity.

### 30.3.4 Throughput Provisioning (Request Units)

**Definition:** Cosmos DB throughput is measured and provisioned in **Request Units (RUs)** — a normalized measure abstracting away the actual CPU, memory, and I/O cost of a given database operation, allowing throughput to be reasoned about and provisioned in a single, consistent unit regardless of the specific mix of operations (reads, writes, queries) an application performs.

**Provisioning modes:**

- **Provisioned throughput** — a fixed number of RUs per second is reserved and billed for, whether fully utilized or not, appropriate for predictable, sustained workloads.
- **Serverless** — billed purely per-request based on actual RU consumption, with no pre-provisioned capacity, appropriate for intermittent, unpredictable, or low-average-with-occasional-burst workloads (conceptually similar to the Consumption plan trade-off discussed for Azure Functions, Section 14.3.2).
- **Autoscale** — automatically scales provisioned RUs between a defined minimum and maximum based on actual usage, billed based on the highest RU tier actually used within each hour, balancing the predictability of provisioned throughput against the elasticity of serverless.

### 30.3.5 Global Distribution and Multi-Region Writes

Cosmos DB supports adding read regions to a database with a few clicks/commands, with data automatically replicated to each added region; additionally, **multi-region writes** (sometimes called multi-master) can be enabled, allowing writes to be accepted in multiple regions simultaneously rather than requiring all writes to funnel through a single primary region — this comes with important consistency implications (write conflicts across regions must be resolved via a conflict resolution policy) and is a meaningfully more complex architectural pattern than single-write-region-with-multiple-read-regions, appropriate specifically for applications genuinely requiring low-latency writes from multiple geographically distant locations simultaneously.

## 30.4 Architecture Diagram

```
Cosmos DB Account "cosmos-globalapp"
 Consistency Level: Session
 API: NoSQL

 ├── Region: East US    (Write + Read) ┐
 ├── Region: West Europe (Write + Read) ├─ Multi-region writes enabled
 └── Region: Southeast Asia (Read only) ┘   (conflict resolution policy configured
                                              for the write regions)

 Database "orders-db"
  └── Container "orders"
       Partition Key: /customerId
       ├── Partition A: customerId hash range 1 — items for these customers
       ├── Partition B: customerId hash range 2
       └── Partition C: customerId hash range 3
             (data and RU throughput distributed across partitions
              based on partition key value)
```

## 30.5 Configuration & Hands-On Example

**Creating a Cosmos DB account, database, and container with a specified partition key:**

```bash
az cosmosdb create \
  --resource-group rg-myapp-prod \
  --name cosmos-globalapp \
  --default-consistency-level Session \
  --locations regionName=eastus failoverPriority=0 isZoneRedundant=false \
  --locations regionName=westeurope failoverPriority=1 isZoneRedundant=false

az cosmosdb sql database create \
  --resource-group rg-myapp-prod \
  --account-name cosmos-globalapp \
  --name orders-db

az cosmosdb sql container create \
  --resource-group rg-myapp-prod \
  --account-name cosmos-globalapp \
  --database-name orders-db \
  --name orders \
  --partition-key-path "/customerId" \
  --throughput 400
```

- **Purpose:** Creates a Cosmos DB account with Session consistency and two regions (East US as primary/failoverPriority=0, West Europe as secondary), then a database and a container explicitly partitioned by `/customerId`, with a baseline provisioned throughput of 400 RU/s.
- **Important arguments explained individually:**
  - `--default-consistency-level` — sets the account-wide default consistency level (Section 30.3.3); individual requests can often request a weaker consistency level than the account default on a per-request basis, but never a stronger one than the account default allows.
  - `--partition-key-path` — this decision, per Section 30.3.2, should be made deliberately based on actual analyzed access patterns (here, `/customerId` assumes queries and writes are predominantly scoped per-customer, spreading load evenly assuming a reasonably large and evenly-active customer base) rather than an arbitrary or convenient-seeming field.
- **Common error:** Choosing a low-cardinality partition key (e.g., partitioning by `/status` with only a few possible values like "pending"/"completed") concentrates most data and traffic onto very few partitions, creating the hot-partition problem described in Section 30.3.2 — this is a design-time mistake, not something easily fixed via configuration after significant data has accumulated.

## 30.6 Production & Enterprise Usage

Enterprises use Cosmos DB for genuinely globally-distributed, low-latency-critical applications (e-commerce catalogs, IoT telemetry ingestion, gaming leaderboards, globally-used SaaS applications) where the relational model and single/limited-region-write pattern of Azure SQL Database wouldn't meet latency or scale requirements. Partition key design is treated as a formal upfront architectural exercise, typically informed by actual or projected query and write patterns rather than convenience, given how costly a wrong choice is to correct later. Consistency level selection is a deliberate, documented trade-off decision per application (or even per specific operation, given Cosmos DB's support for per-request consistency overrides within the account's maximum), balancing the specific correctness requirements of each operation against latency and cost.

## 30.7 Security Considerations

- Cosmos DB supports both key-based authentication (account keys, similar in risk profile to Storage Account shared keys, Section 16.7) and Entra ID-based (RBAC) authentication — Entra ID-based access is generally preferred for the same least-privilege, auditability, and credential-lifecycle reasons established throughout Part 2.
- Network isolation via Private Link (Section 23.5) is supported and recommended for production Cosmos DB accounts holding sensitive data, following the same pattern established for other PaaS services.
- Data is encrypted at rest by default, with the option for customer-managed keys for organizations requiring direct encryption key control, mirroring the pattern already established for Managed Disks (Section 18.3.4) and Storage Accounts.

## 30.8 Performance Considerations

RU consumption should be monitored per operation type (a poorly-designed query, or one lacking an appropriate index, can consume disproportionately more RUs than necessary) — Cosmos DB's automatic indexing of all properties by default is convenient but can be tuned (via a custom indexing policy) to exclude properties that don't need to be queried, reducing both storage and write RU cost; this indexing-policy tuning is a genuine, non-obvious performance and cost optimization lever specific to Cosmos DB's architecture.

## 30.9 Monitoring

Cosmos DB integrates with Azure Monitor (Part 10), providing RU consumption metrics (critical for right-sizing provisioned throughput or evaluating whether Serverless/Autoscale would be more cost-effective), partition-level metrics (useful for detecting a hot-partition problem before it becomes a significant production issue), and replication-latency metrics across configured regions.

## 30.10 Troubleshooting

| Symptom                                                                                  | Likely Cause                                                                                                                                                | Fix                                                                                                                                            |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Requests failing with "429 Too Many Requests" errors                                     | Provisioned RU throughput exceeded for the current traffic level                                                                                            | Increase provisioned RUs, switch to Autoscale, or optimize queries/indexing policy to reduce RU consumption per operation                      |
| One specific partition consistently shows much higher RU consumption/latency than others | Hot partition — poorly distributed partition key values                                                                                                     | Requires redesigning the partition key strategy and migrating data to a new container, since partition keys aren't easily changed in place     |
| Application reads stale data unexpectedly                                                | Consistency level weaker than the application actually requires for that specific read (e.g., Eventual consistency used where Session or Strong was needed) | Review and adjust consistency level (account default or per-request override) to match the actual correctness requirement of the specific read |

## 30.11 Interview Questions — Section 30

### 🎯 Intermediate

**Q: Why is partition key selection considered one of the most important upfront design decisions in Cosmos DB?**

_Model answer:_ The partition key determines how data and the associated read/write traffic are distributed across Cosmos DB's underlying physical partitions. A well-chosen partition key with high cardinality and evenly-distributed access patterns allows the database to scale smoothly, since load spreads evenly across partitions. A poorly-chosen partition key can create a "hot partition" — a disproportionate share of traffic concentrated on a small number of partition key values — creating a bottleneck that can't be resolved simply by provisioning more total throughput, since that hot partition's own individual throughput ceiling still constrains it regardless of overall account capacity. Because changing a partition key typically requires migrating all data into a new container, this is a decision that's very costly to get wrong and correct later, making it a critical upfront design exercise rather than an easily-adjustable configuration setting.

_What the interviewer is probing:_ understanding of Cosmos DB's underlying partitioning architecture and why this specific design decision carries outsized long-term consequences compared to more easily reversible configuration choices.

### 🎯 Senior/Architect

**Q: Design the data architecture for a globally distributed e-commerce application needing low-latency reads and writes from users in North America, Europe, and Asia, with shopping cart data that must never show a customer stale/lost items.**

_Model answer:_ I'd use Cosmos DB with regions in each of the three geographies, and would evaluate whether multi-region writes are genuinely necessary — if shopping cart writes for a given customer can reasonably be routed to their nearest region consistently (e.g., via application-level routing informed by the user's location, similar to Front Door's latency-based routing concept from Section 25), a single-write-region-per-customer-affinity pattern with multiple read regions might avoid the added complexity of true multi-region writes and their conflict-resolution requirements. If genuinely simultaneous multi-region writes for the same data are unavoidable (e.g., a customer actively shopping from multiple devices/locations), I'd enable multi-region writes with a carefully considered conflict resolution policy. For consistency, given the explicit requirement that shopping cart items must never appear stale or lost to the customer, I'd lean toward Session consistency at minimum for cart-related operations specifically — ensuring a customer always sees their own most recent writes — while potentially using a more relaxed consistency level (like Eventual) for less consistency-sensitive data like a product catalog, where slightly stale data (e.g., a product description) is an acceptable trade-off for better latency and cost. I'd design the partition key for the cart container based on `/customerId` or a similar customer-scoped property, ensuring cart operations for a given customer are efficiently co-located within a partition, and would validate this choice against projected customer distribution to avoid a hot-partition risk for any unusually high-activity customer segment.

_What the interviewer is probing:_ whether the candidate can make differentiated, requirement-driven decisions about consistency level per data type (not applying one blanket consistency level to the entire application), and whether they understand the genuine complexity trade-off of multi-region writes versus simpler alternatives that might satisfy the actual stated requirement with less architectural complexity.

## 30.12 Common Misconceptions

- **"Choosing the MongoDB API means you're running actual MongoDB."** False — Cosmos DB's own engine speaks the MongoDB wire protocol, allowing compatible drivers/tools to connect, but the underlying storage and distribution engine is entirely Cosmos DB's own, not MongoDB software.
- **"Strong consistency is always the safest default choice."** Not necessarily — Strong consistency carries meaningful latency and availability trade-offs; Session consistency is the most commonly appropriate default for many applications, and the correct choice should be driven by the actual correctness requirements of each specific data/operation type, not a blanket assumption that "stronger is always better."

## 30.13 Key Takeaways

- 🔑 Cosmos DB provides globally-distributed, multi-model NoSQL database capabilities with five tunable consistency levels trading consistency against latency/availability, unlike Azure SQL Database's traditional relational, more limited-region-write model.
- 🔑 Partition key selection is a critical, difficult-to-change-later design decision directly determining scalability — poor choices create hot partitions that provisioned throughput alone cannot fix.
- 🔑 Session consistency is the most commonly used default, balancing read-your-own-writes guarantees against strong latency/availability characteristics.
- 🔑 Throughput is measured in Request Units (RUs), provisionable as fixed Provisioned throughput, pure pay-per-use Serverless, or auto-adjusting Autoscale, chosen based on workload predictability.
- 🔑 Multi-region writes enable true multi-master global distribution but introduce meaningful conflict-resolution complexity, and should only be adopted when genuinely required by the application's latency needs.

## 30.14 Change Feed, Transactional Scope, and Backup/Restore

### 30.14.1 Change Feed

**Definition:** The **Change Feed** is a persistent, ordered log of changes (inserts and updates — by default not deletes, though a "soft delete" application pattern using a flag can make deletes observable too) made to a Cosmos DB container, which client applications can read incrementally to react to data changes as they happen, without needing to repeatedly poll or query the container for what changed.

**Why it matters:** Change Feed is the foundation for a wide range of event-driven architectural patterns built on top of Cosmos DB — triggering an Azure Function (Section 14) whenever a new order document is inserted, maintaining a secondary materialized view or search index in sync with the primary container, replicating changes to another data store, or feeding a downstream event-processing pipeline (connecting directly to the eventing services covered in Part 8: Event Grid, Event Hubs, Service Bus). Change Feed is read per-partition-key-range and guarantees changes are delivered in the order they occurred _within_ a partition key range, though ordering **across** different partition key ranges isn't guaranteed — an important nuance when designing a consumer that needs to reason about global event ordering.

⚠️ Change Feed is a read-only, append-log-style mechanism, not a general-purpose query interface — consumers process it sequentially (typically tracking their own read position/checkpoint) rather than issuing ad hoc queries against it; exact current consumption models (e.g., push-model via Azure Functions trigger vs. pull-model via SDK) and their specific capabilities should be verified against current documentation.

### 30.14.2 Transactional Batch and Stored Procedures

**Transactional Batch:** Cosmos DB supports **Transactional Batch** operations — grouping multiple point operations (creates, updates, deletes, reads) against items that **share the same partition key** into a single atomic unit, where either all operations succeed or none do. This is Cosmos DB's mechanism for multi-item ACID transactions, but it comes with a fundamental scope limitation.

⚠️ **The critical constraint: Transactional Batch only works within a single partition key.** Cosmos DB does not support multi-document ACID transactions spanning _different_ partition key values — this is a direct consequence of the partitioning architecture covered in Section 30.3.2, since different partition keys may live on entirely different physical partitions, and Cosmos DB's transaction guarantee is scoped to what can be coordinated within one partition. This has significant data-modeling implications: if an application's business logic requires atomically updating multiple related documents together, those documents must share a partition key, or the application must handle cross-partition consistency itself at the application level (e.g., via a saga pattern or compensating-transaction approach) — this is a frequently underestimated design constraint when teams accustomed to relational databases' broader transactional guarantees first design for Cosmos DB.

**Stored Procedures:** Cosmos DB supports **stored procedures** (written in JavaScript), which execute server-side and, like Transactional Batch, are scoped to a single partition key/logical partition — allowing multiple operations to be bundled into one atomic, server-executed unit. Stored procedures are commonly used for exactly the kind of multi-document-within-one-partition atomic operation Transactional Batch also addresses, and for encapsulating reusable server-side logic, though newer applications often prefer Transactional Batch (via the SDK, without needing to write and deploy JavaScript) where its capabilities suffice.

### 30.14.3 Backup and Restore

**Definition:** Cosmos DB performs **automatic backups** by default, with two backup modes available:

- **Periodic backup mode** — backups are taken on a configurable interval (with a configurable retention period), and restoring requires **opening a support request** with Microsoft to perform the restore into a new account — a notably different, more manual operational model than the self-service restore available for Azure SQL Database (Section 29.15.2).
- **Continuous backup mode** — provides continuous, self-service point-in-time restore (similar in spirit to Azure SQL's PITR, Section 29.15.2) to any point within a retention window (commonly up to 30 days, or a longer window depending on the specific tier — ⚠️ verify current retention options against documentation), restorable by the customer directly without needing a Microsoft support request.

**Choosing between them:** Continuous backup mode is generally preferable for production workloads needing fast, self-service, fine-grained recovery from an accidental write or deletion, while periodic backup mode's support-request-dependent restore process introduces meaningfully longer recovery time — an important factor when defining a Recovery Time Objective (RTO) for a Cosmos DB-backed production workload.

⚠️ Exact backup mode names, retention limits, and restore mechanics continue to evolve — verify current details against official documentation, and note that backup mode is generally an account-level setting chosen at account creation time (or with specific migration paths between modes), not a casually reversible per-request choice.

### 30.14.4 Interview Questions — Section 30.14

**🎯 Senior**
**Q: An application needs to atomically update a customer's order document and their account balance document together. How does this work in Cosmos DB, and what design implication does it carry?**

_Model answer:_ Cosmos DB's Transactional Batch (or a stored procedure) can perform this atomically only if both documents share the same partition key — if the order document is partitioned by `/orderId` and the account balance document is partitioned by `/customerId`, they likely live on different physical partitions and cannot be included in the same atomic transaction. This means the data model needs to be deliberately designed so documents requiring atomic multi-document updates together share a partition key — for example, partitioning both order and account documents by `/customerId` if that atomicity requirement is a hard business rule — or, if that's not feasible given other access-pattern requirements, the application needs to implement its own compensating-transaction or saga-style logic to handle the cross-partition consistency requirement at the application layer, since Cosmos DB itself provides no native mechanism for that.

_What the interviewer is probing:_ whether the candidate understands that Cosmos DB's transactional guarantees are fundamentally partition-scoped, a direct and consequential extension of the partitioning architecture, rather than assuming database-wide ACID transactions are available the way they would be in a traditional relational database.

### 30.14.5 Key Takeaways — Section 30.14

- 🔑 Change Feed provides an ordered, incremental log of container changes, foundational to event-driven patterns (triggering Functions, materialized views, downstream event pipelines) — ordering is guaranteed within a partition key range, not globally across the container.
- 🔑 Transactional Batch and stored procedures provide atomic multi-operation transactions, but strictly scoped to a single partition key — cross-partition atomicity isn't natively supported and must be handled at the application level if required.
- 🔑 Periodic backup mode requires a Microsoft support request to restore; Continuous backup mode provides self-service point-in-time restore — the choice materially affects achievable Recovery Time Objective for a production workload.

## 30.15 Related Concepts (Next Up)

Section 31 covers **Azure Database for PostgreSQL/MySQL** — Azure's managed offerings for these popular open-source relational database engines, rounding out the relational database options (alongside Azure SQL Database/Managed Instance, Section 29) available for workloads specifically built around PostgreSQL or MySQL rather than SQL Server or Cosmos DB's NoSQL model.
