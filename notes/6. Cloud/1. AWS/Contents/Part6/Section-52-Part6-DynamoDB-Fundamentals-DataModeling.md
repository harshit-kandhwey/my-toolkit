# Part 6 - Section 4 - Amazon DynamoDB: Fundamentals & Data Modeling

AWS Zero-to-Enterprise Knowledge Base - Part 6: Databases

---

## 1. Definition

Plain-language: DynamoDB is a fully managed NoSQL database that stores data as items identified by a key, rather than rows in tables with fixed columns and relationships. Designed for consistent, single-digit-millisecond performance at effectively unlimited scale, but requires designing your data model around how you'll actually query it.

Precise: Amazon DynamoDB is a fully managed, serverless NoSQL key-value and document database, providing consistent single-digit-millisecond latency at any scale, with data organized into tables, items, and attributes rather than relational rows/columns/joins, and access governed by a primary key design chosen upfront based on anticipated query patterns.

---

## 2. Why It Exists

- Relational databases have genuine scaling limits - vertical scaling hits a ceiling, horizontal sharding is genuinely difficult for complex joins.
- DynamoDB's core bet: give up arbitrary query flexibility (no joins, no ad hoc WHERE clauses without additional infrastructure) for near-infinite horizontal scalability and consistently fast performance - parallel to S3's trade-off, now for structured data.
- The inverted mental model: relational databases model structure first, query later. DynamoDB requires knowing access patterns (actual queries) BEFORE designing the table, since the primary key structure determines query efficiency. The central conceptual shift this section teaches.

---

## 3. Core DynamoDB Concepts

### 3.1 Tables, Items, Attributes
- A table is a collection of items (roughly rows, but genuinely schemaless beyond the key structure).
- An item is a collection of attributes (roughly columns) - different items in the same table can have completely different attribute sets, no fixed schema.
- Attributes can be simple (string, number, boolean) or complex (list, map, set).

### 3.2 Primary Keys - The Central Design Decision
- Simple primary key (Partition Key only) - a single attribute uniquely identifying each item; DynamoDB hashes this to determine physical partition placement.
- Composite primary key (Partition Key + Sort Key) - partition key groups items, sort key orders/uniquely identifies items within that group, enabling range queries and multiple items sharing a partition key.
- The partition key determines physical data distribution; query efficiency is built around exact partition key match (optionally with sort key range) - querying by any other attribute is inefficient (a full scan) unless a secondary index is added (Section 5).

### 3.3 Access-Pattern-First Design Principle
- Central, most heavily-tested concept: because efficient queries need an exact partition key match, table design must be based on how the application will actually query data - not on inherent data structure.
- Example: "get all orders for a customer, most recent first" -> partition key CustomerID, sort key OrderDate - makes that query extremely efficient but makes "find all orders over $1000 across all customers" inefficient without extra infrastructure.
- Practical consequence: DynamoDB modeling starts with listing required queries, then designs keys/indexes to make each efficient - inverted from relational normalization.

### 3.4 Query vs Scan
- Query - exact partition key match (optional sort key condition) - efficient, targeted, performance doesn't degrade with table size.
- Scan - examines every item, optionally filtering after - inefficient at scale, cost/latency grow with table size regardless of match count.
- Needing a Scan for a routine access pattern signals the key design needs reconsidering or a secondary index (Section 5) is needed.

---

## 4. DynamoDB's Consistency Model

- Eventually consistent reads (default) - might not reflect the very latest write, in exchange for higher throughput/lower cost - genuinely different from S3's move to strong consistency; DynamoDB's default is the older eventual-consistency model.
- Strongly consistent reads (optional, explicit) - guarantees reflecting all prior writes, at roughly double read capacity cost and potentially slightly higher latency.
- Use strongly consistent reads specifically when correctness genuinely depends on the absolute latest data (e.g., immediately after a write in the same operation), not as a universal default.

---

## 5. DynamoDB Capacity Modes

### 5.1 On-Demand Capacity
Pay per request, no capacity planning, auto-scales to actual traffic - parallel to Lambda's "pay for what you use," applied to database throughput. Best for unpredictable/new/highly variable workloads.

### 5.2 Provisioned Capacity
Specify Read Capacity Units (RCUs) and Write Capacity Units (WCUs) upfront - cheaper per-unit for predictable steady traffic, requires capacity planning, can throttle if exceeded (mitigated by Auto Scaling for provisioned capacity). Mirrors the On-Demand-vs-Reserved EC2 framework: On-Demand for unpredictable/new workloads, Provisioned (with Auto Scaling) once traffic patterns are established.

---

## 6. Production & Enterprise Usage

- DynamoDB as standard choice for high-scale, latency-sensitive, access-pattern-known applications - session storage, shopping carts, user profiles, leaderboards, IoT device state.
- "Single-table design" - an advanced technique storing multiple entity types in one table using carefully designed partition/sort key patterns to support multiple access patterns - a DynamoDB-specific technique with no relational equivalent (deepened Section 5).
- DynamoDB behind Lambda/API Gateway - an extremely common fully serverless application backend pattern, both scaling automatically together.

---

## 7. Security Considerations

- Encryption at rest enabled by default for all tables (AWS owned/managed KMS keys, customer-managed options available) - "secure by default" theme continues.
- IAM policies control access at table, item, and even attribute level - fine-grained access control via IAM condition keys referencing the requesting principal (e.g., restricting a user to only items where the partition key matches their own user ID) - a powerful DynamoDB-specific least-privilege pattern.

---

## 8. Performance Considerations

- Query performance doesn't degrade with table size - the central performance promise, entirely dependent on using Query rather than Scan for real access patterns.
- Hot partitions - disproportionate traffic to one partition key value can bottleneck that partition despite overall horizontal scalability - a genuine modeling consideration, sometimes requiring write-sharding (adding a random/calculated suffix to the partition key) to spread load.

---

## 9. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Query pattern slow, gets slower as table grows | Using Scan instead of Query, access pattern doesn't match primary key | Redesign primary key, or add a secondary index (Section 5) |
| Reads don't reflect a very recent write | Default eventually consistent reads | Request a strongly consistent read where genuinely needed |
| Requests throttled under load | Provisioned capacity too low, no Auto Scaling | Enable Auto Scaling, or switch to On-Demand |
| One partition key value is a bottleneck | Hot partition - disproportionate traffic | Consider write-sharding (calculated suffix on partition key) |

---

## 10. Best Practices & Anti-Patterns

Best practices: list actual required access patterns before designing keys; use Query not Scan for production patterns; request strongly consistent reads only where genuinely needed; start On-Demand for new/unpredictable workloads, move to Provisioned+Auto Scaling once patterns are established; watch for hot-partition risk.

Anti-patterns: designing DynamoDB like a relational schema (entities/relationships first); relying on Scan for routine production patterns; defaulting to strongly consistent reads universally; provisioning fixed capacity without Auto Scaling for variable traffic.

---

## 11. Common Misconceptions

- "DynamoDB tables have a fixed schema like relational tables." False - schemaless beyond the key structure.
- "You design a DynamoDB table the same way as a relational schema." False - access-pattern-first, inverted design philosophy.
- "DynamoDB reads are always perfectly up to date." False - default is eventually consistent; strong consistency must be explicitly requested at extra cost.
- "Scan and Query are the same operation." False - Query is targeted/efficient; Scan is full-table with cost/latency growing with size.

---

## 12. Interview Questions (with model answers)

Beginner - Fundamental difference in designing a DynamoDB table vs a relational table? Relational: model structure/relationships first, SQL flexibility handles queries afterward. DynamoDB: must know actual access patterns before designing the table, since the primary key structure determines query efficiency - design keys around queries, not the reverse.

Beginner - Difference between Query and Scan? Query: exact partition key match (optional sort key condition), targeted/efficient, performance doesn't degrade with size. Scan: examines every item, filters after, cost/latency grow with table size regardless of match count. Needing Scan for a routine pattern signals a key-design/indexing gap.

Intermediate - When use a strongly consistent read instead of the default? When correctness genuinely depends on seeing the absolute latest data - e.g., reading immediately after writing within the same operation. Costs roughly double read capacity and slightly more latency - request explicitly per-read for operations where it matters, not as a default.

Senior - Table has UserID as partition key for "get all orders for a user," now also needs "get all orders on a specific date across all users" - how to address? Date-across-all-users doesn't match the partition key - would require an inefficient, growing Scan. Add a Global Secondary Index with OrderDate as its partition key, making that pattern an efficient Query against the index instead of the base table. Exactly why DynamoDB modeling enumerates every required access pattern upfront - a single primary key typically can't serve every pattern; secondary indexes add support without redesigning the base table.

---

## Key Takeaways

1. DynamoDB trades relational query flexibility for near-infinite horizontal scale and consistent low-latency performance - the NoSQL parallel to S3's trade-off, for structured data.
2. Access-pattern-first design is the central, inverted principle - know your queries before designing the primary key.
3. Query (efficient, exact-key-match) vs Scan (inefficient, full-table) is a critical distinction - needing Scan for routine patterns signals a design gap.
4. DynamoDB defaults to eventually consistent reads, with strongly consistent reads available at a cost/latency premium for operations needing absolute currency.
5. On-Demand and Provisioned (with Auto Scaling) capacity modes mirror the broader EC2 On-Demand-vs-Reserved framework - observe first, commit once patterns are established.

## Related Concepts (forward links)

- DynamoDB secondary indexes, streams, and advanced capacity/performance tuning -> Part 6, Section 5
- ElastiCache as a caching layer sometimes paired with DynamoDB -> Part 6, Section 6
- Choosing between RDS/Aurora and DynamoDB for a given workload -> Part 6, Section 9
