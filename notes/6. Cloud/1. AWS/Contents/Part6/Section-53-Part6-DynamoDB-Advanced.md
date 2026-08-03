# Part 6 - Section 5 - DynamoDB Advanced: Indexes, Streams, Capacity & Performance

AWS Zero-to-Enterprise Knowledge Base - Part 6: Databases

---

## 1. Definition

Plain-language: Secondary indexes let you efficiently query a DynamoDB table using a different key than its primary key, without a Scan. Streams give a real-time feed of every change to a table, so other services can react automatically. Capacity/performance tuning covers the practical levers for keeping DynamoDB fast and cost-effective at real production scale.

Precise: DynamoDB secondary indexes (Global and Local) provide alternative query paths beyond the base table's primary key. DynamoDB Streams provide an ordered, near-real-time record of item-level changes, consumable by Lambda or other processors. DAX and adaptive capacity address specific production performance and hot-partition challenges.

---

## 2. Why This Category Exists

- One primary key structure efficiently serves one access pattern (or closely related family) - a genuine, immediate constraint since real applications almost always have multiple distinct query needs.
- Secondary indexes solve this without duplicating data into separate tables or resorting to Scans - one table serving multiple access patterns via automatically-synchronized additional key structures.
- Streams solve reacting to data changes in real time - triggering downstream processing, maintaining derived views, replicating changes - extending event-driven Lambda triggers to DynamoDB as an event source.

---

## 3. Global Secondary Indexes (GSI)

### 3.1 Definition and Mechanics

- Has its OWN partition key (and optionally sort key), genuinely different from the base table's - serving an entirely different access pattern.
- "Global" means the index spans all partitions of the base table - its own independent partitioning based on its own key structure.
- Asynchronously updated - GSI updates propagate with a brief delay after base-table changes, meaning a GSI query might briefly reflect slightly stale data.
- Has its own separate provisioned capacity (Provisioned mode) - under-provisioning a GSI can throttle queries against it even with ample base-table capacity.

### 3.2 Can Be Added After Table Creation

Unlike the base table's primary key (fixed at creation), GSIs can be added to an existing table anytime - practical for new access patterns emerging after production launch.

---

## 4. Local Secondary Indexes (LSI)

### 4.1 Definition and Mechanics

- Shares the SAME partition key as the base table, but a different sort key - alternative sort/range orderings within the same partition grouping.
- "Local" means scoped to the same partition - a query still specifies the same partition key value; only the within-partition sorting/filtering changes.
- Strongly consistent reads available for LSIs (unlike GSIs, always eventually consistent) - since an LSI lives on the same partition, it updates synchronously with the base table.

### 4.2 Must Be Created at Table Creation Time

Unlike GSIs, LSIs CANNOT be added after table creation - must be defined upfront, a significant operational constraint.

### 4.3 GSI vs LSI

|                 | GSI                                                  | LSI                                                   |
| --------------- | ---------------------------------------------------- | ----------------------------------------------------- |
| Partition key   | Different from base table                            | Same as base table                                    |
| Sort key        | Different (optional)                                 | Different (required)                                  |
| Consistency     | Eventually consistent only                           | Strongly or eventually consistent                     |
| Creation timing | Anytime                                              | Only at table creation                                |
| Capacity        | Own separate capacity                                | Shares base table's capacity                          |
| Best for        | An entirely different access pattern/entity grouping | Alternative sort order within same partition grouping |

Interview tip: use a GSI for a genuinely different key than the base table's partition key - flexible, addable anytime, always eventually consistent. Use an LSI for an alternative sort order within the same partition needing strong consistency - but must decide at creation time.

---

## 5. DynamoDB Streams

### 5.1 Definition and Mechanics

- Captures a time-ordered sequence of item-level changes (inserts/updates/deletes), retained 24 hours, consumable by Lambda (event source mapping) or Kinesis Data Streams integration (longer retention/broader fan-out).
- Stream records can include item state before, after, or both the change - useful for logic needing to know what changed FROM, not just what changed.

### 5.2 Common Use Cases

- Triggering downstream processing - Lambda reacting to a new item, sending notifications, updating aggregates.
- Cross-Region replication (DynamoDB Global Tables) - use Streams internally for multi-Region, MULTI-ACTIVE tables (writes accepted in any participating Region) - a genuinely different DR model from primary/standby patterns.
- Maintaining derived/materialized views - keeping a differently-keyed table or search index (OpenSearch) in sync via event-driven synchronization, when a GSI alone isn't structurally different enough.

---

## 6. DynamoDB Accelerator (DAX)

- Fully managed, in-memory caching layer specifically for DynamoDB, providing microsecond read latency for read-heavy workloads - purpose-built and API-compatible for DynamoDB specifically (unlike general-purpose ElastiCache, Section 6).
- Useful when even DynamoDB's native latency isn't fast enough, or when reducing read-capacity consumption on the underlying table is valuable (cache hits don't consume base-table capacity) - parallel to CDN/Gateway-Endpoint "avoid hitting the origin" philosophy, for database reads.

---

## 7. Adaptive Capacity and Hot Partitions

- Adaptive capacity is DynamoDB's built-in automatic mechanism shifting throughput toward partitions receiving disproportionate traffic - no customer configuration needed, mitigating minor hot-partition issues transparently.
- For genuinely extreme hot-partition scenarios (a "viral" item, a global shared counter), adaptive capacity alone may not suffice - write-sharding (a calculated suffix spreading a logical key across multiple physical values) remains a manual intervention for these extreme cases.

---

## 8. Production & Enterprise Usage

- GSIs as the standard solution for multi-access-pattern applications - nearly every production table with more than one query need uses at least one GSI.
- Streams + Lambda for event-driven architectures - a common serverless pattern keeping downstream systems synchronized without polling.
- Global Tables for genuinely global, multi-active applications - gaming, IoT, global SaaS needing writes accepted in multiple Regions with automatic conflict resolution (last-writer-wins by default).
- DAX for read-heavy, latency-critical production workloads - gaming leaderboards, ad-tech bidding.

---

## 9. Security Considerations

- GSIs/LSIs inherit the base table's encryption - no separate configuration needed, though IAM can still scope index-specific access if needed.
- Streams should be treated as a genuine data-access path requiring its own IAM scoping - a stream-consuming Lambda has read access to every table change, scoped as tightly as any other data-access permission.

---

## 10. Performance Considerations

- GSI capacity under-provisioning is a common, easy-to-miss throttling cause - monitor both base table and every GSI's capacity separately.
- DAX trades a small amount of consistency (briefly stale cached reads) for substantial latency improvement - an explicit trade-off to evaluate against staleness tolerance.

---

## 11. Troubleshooting

| Symptom                                                                  | Cause                                                                        | Fix                                                                                             |
| ------------------------------------------------------------------------ | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| Base table has capacity but a specific query is throttled                | The queried GSI has insufficient capacity of its own                         | Increase or enable Auto Scaling on that specific GSI                                            |
| Need an LSI for a new pattern on an existing production table            | LSIs only creatable at table creation                                        | Cannot retrofit; consider a GSI instead, or plan a migration if strong consistency is essential |
| Lambda not receiving expected DynamoDB change events                     | Streams not enabled, or event source mapping misconfigured                   | Verify Streams enabled with correct view type and correct event source mapping                  |
| One item/key receives disproportionate traffic despite adaptive capacity | Extreme hot-partition scenario beyond adaptive capacity's automatic handling | Consider write-sharding with a calculated suffix                                                |

---

## 12. Best Practices & Anti-Patterns

Best practices: use GSIs for genuinely different access patterns, planning for separate capacity; use LSIs only when strong consistency on an alternate sort order is required, decided at creation; use Streams+Lambda for event-driven sync over polling; evaluate DAX for read-heavy latency-critical workloads specifically; rely on adaptive capacity for moderate unevenness, write-sharding only for extreme cases.

Anti-patterns: forgetting GSIs have separate capacity and under-provisioning; assuming LSIs can be added after the fact; building custom polling instead of using Streams; reaching for write-sharding prematurely before confirming adaptive capacity is insufficient.

---

## 13. Common Misconceptions

- "A GSI and the base table are always perfectly in sync." False - asynchronous updates create a genuine eventual-consistency gap.
- "You can add an LSI to a table anytime like a GSI." False - LSIs must be defined at creation.
- "DynamoDB automatically handles every hot-partition scenario." False - adaptive capacity handles moderate unevenness; extreme cases need manual write-sharding.
- "DAX is a general-purpose cache for any database." False - purpose-built and API-compatible specifically for DynamoDB.

---

## 14. Interview Questions (with model answers)

Beginner - Main difference between a GSI and an LSI? GSI: own partition key, different from base table, asynchronously updated, addable anytime. LSI: shares the base table's partition key with a different sort key, supports strongly consistent reads, but must be defined at table creation and can't be added later.

Beginner - What are DynamoDB Streams used for? Time-ordered record of item-level changes (insert/update/delete), retained 24 hours, processed by Lambda or other consumers in near real time. Uses: triggering downstream processing, keeping a derived/differently-structured view in sync, powering Global Tables' cross-Region replication internally.

Intermediate - Why might a GSI query return slightly stale data? GSIs update asynchronously relative to the base table - an update propagates with a brief delay, similar in spirit to Read Replica lag. A GSI query could miss a very recent write briefly. LSIs differ - can offer strong consistency since they're on the same partition, updated synchronously.

Intermediate - Table throttled on a specific query despite base table having unused capacity - what to check? If the query runs against a GSI, it has its own separate provisioned capacity independent of the base table - entirely possible for the base table to have ample capacity while a specific GSI is under-provisioned. Check that GSI's capacity metrics specifically, increase or enable Auto Scaling on it.

Senior - Design DynamoDB for a global multiplayer game: real-time leaderboard, low-latency multi-Region reads, auto-synced search-optimized player view? Global Tables for multi-active writes accepted in each Region with Streams-based cross-Region replication - a genuinely different model from primary/standby, appropriate for low-latency local writes across Regions. Leaderboard: a GSI keyed by score/rank within a game/season, since the base table's primary pattern is likely per-player data with a different key structure. DAX in front of leaderboard reads specifically given their read-heavy latency-critical nature, avoiding base-table read-capacity consumption. Search-optimized view: Streams triggering a Lambda keeping an external search index (OpenSearch) synchronized in near real time, since a search structure is different enough that a GSI alone wouldn't suffice - exactly what Streams are built for.

---

## Key Takeaways

1. GSIs (different partition key, addable anytime, eventually consistent, own capacity) and LSIs (same partition key, creation-time-only, optionally strongly consistent, shared capacity) solve the multi-access-pattern problem differently - a frequently-tested decision.
2. DynamoDB Streams provide a time-ordered change feed - the mechanism behind event-driven Lambda triggers, Global Tables replication, and derived-view synchronization.
3. DynamoDB Global Tables provide a genuinely multi-active (not primary/standby) cross-Region model - distinct from RDS/Aurora's DR approach.
4. DAX provides microsecond-latency caching purpose-built for DynamoDB - not a general-purpose cache, a genuine consistency-for-latency trade-off.
5. Adaptive capacity handles moderate traffic unevenness automatically; write-sharding remains necessary for genuinely extreme hot-partition scenarios.

## Related Concepts (forward links)

- ElastiCache - general-purpose caching for RDS/Aurora and other workloads -> §54
- Kinesis Data Streams for broader-scale stream processing beyond native DynamoDB Streams -> Part 7
- Choosing between RDS/Aurora and DynamoDB, and DMS for migration -> §57
