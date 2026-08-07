# Part 6 - Section 6 - Amazon ElastiCache: Redis & Memcached

AWS Zero-to-Enterprise Knowledge Base - Part 6: Databases

---

## 1. Definition

Plain-language: ElastiCache lets you run a managed, in-memory data store - Redis or Memcached - that sits between your application and your database, storing frequently-accessed data in memory for extremely fast retrieval, reducing database load and speeding up your application.

Precise: Amazon ElastiCache is a managed, in-memory data store and cache service, supporting Redis (ElastiCache for Redis/Valkey) and Memcached, used to reduce database load and deliver sub-millisecond latency for frequently-accessed data, session state, and other cacheable workloads.

---

## 2. Why It Exists

- Disk-backed storage has a latency floor pure in-memory access doesn't - for latency-critical or extremely read-heavy workloads, even a well-tuned database query is slower than reading from RAM.
- ElastiCache inserts an in-memory layer between app and database, absorbing repeated reads (cache-aside pattern) so the database only serves the first request - extending the caching philosophy from CloudFront/Gateway Endpoints to the database-query layer.
- Session state is a second distinct use case - externalizing session state to a shared store (the correct fix for sticky-session anti-patterns) - ElastiCache is precisely that shared store, letting any instance retrieve any user's session data.

---

## 3. Redis vs Memcached

|                   | Redis                                                     | Memcached                                               |
| ----------------- | --------------------------------------------------------- | ------------------------------------------------------- |
| Data structures   | Rich (strings, hashes, lists, sets, sorted sets, streams) | Simple key-value only                                   |
| Persistence       | Optional disk persistence                                 | None - pure in-memory                                   |
| Replication       | Native (primary/replica)                                  | None natively                                           |
| High availability | Multi-AZ with automatic failover                          | None natively                                           |
| Multi-threading   | Primarily single-threaded per shard                       | Multi-threaded                                          |
| Use case fit      | Persistence/replication/HA/rich structures needed         | Simple ephemeral caching, raw multi-threaded throughput |

Key idea, the deciding question: need anything beyond simple key-value caching (persistence, replication, failover, pub/sub, rich structures)? Yes -> Redis. Purely simple, ephemeral, no persistence/HA need at all -> Memcached remains legitimate. In practice, Redis is the default for the large majority of modern use cases.

---

## 4. Common Caching Patterns

### 4.1 Cache-Aside (Lazy Loading)

App checks cache first; on a miss, queries the database, writes result into cache for next time - the most common pattern, resilient to cache failures (a cache-node failure just means more misses temporarily, database remains source of truth).
Trade-off: first request always pays full database latency (cache-miss penalty), and cached data can become stale if the database changes without corresponding cache invalidation.

### 4.2 Write-Through

App writes to cache and database simultaneously - cache never stale relative to a completed write, at the cost of added write latency and cache space consumed by potentially-never-read data.

### 4.3 The Trade-off

Interview tip: cache-aside optimizes for read performance/resilience, accepting miss-penalty and potential staleness. Write-through optimizes for freshness, accepting write latency and cache space cost. Most read-heavy apps default to cache-aside; write-through fits when read-after-write consistency through the cache genuinely matters and write volume is low.

---

## 5. Redis High Availability

- Cluster Mode Disabled - single primary with up to 5 read replicas, all data on one shard - simpler, limited by a single node's memory capacity.
- Cluster Mode Enabled - data sharded across multiple node groups (each with primary+replicas) - horizontal scaling of storage/throughput beyond one node's limits, parallel to DynamoDB partitioning but for an in-memory cache.
- Multi-AZ with automatic failover - replicas in different AZs, automatic promotion if primary fails - parallel to RDS Multi-AZ, for the cache layer.
- Memcached has none of this - no native replication, HA, or persistence - a fundamental limitation reinforcing Redis as the generally-recommended default.

---

## 6. Production & Enterprise Usage

- ElastiCache for Redis as a session store for stateless web tiers - implementing "externalize session state" concretely.
- ElastiCache in front of RDS/Aurora for read-heavy relational workloads - complementary to Read Replicas, not competing: Read Replicas scale reads at the database layer, ElastiCache absorbs the most frequently repeated reads at an even faster in-memory layer.
- Redis's rich data structures for specific features - sorted sets for leaderboards, pub/sub for real-time notifications, hyperloglog for approximate unique counts.
- Redis for rate limiting and distributed locking - infrastructure patterns built on Redis's atomic operations.

---

## 7. Security Considerations

- ElastiCache clusters belong in private subnets, following the same three-tier architecture as RDS - never directly internet-reachable, accessed only via app-tier-scoped security groups.
- Redis supports encryption in transit/at rest and Redis AUTH (password-based) or IAM authentication in VPC deployments - distinct mechanics from the IAM-policy model used elsewhere, worth knowing precisely.
- Memcached has more limited native security features than Redis (no encryption, no AUTH-equivalent) - another reason Redis is preferred beyond basic low-sensitivity caching.

---

## 8. Performance Considerations

- The cache-miss penalty is a genuine first-request cost - cache warming (proactively populating before real traffic) mitigates workloads where an unwarmed spike is unacceptable.
- Cluster Mode's sharding is the primary lever for scaling beyond one node - a decision to make proactively, since migrating from Disabled to Enabled is more involved than a simple resize.
- DAX vs ElastiCache - a frequently confused pair: DAX is purpose-built/API-compatible specifically for DynamoDB; ElastiCache is general-purpose, usable in front of any data source. Deciding question: DynamoDB-specific with zero code changes (DAX) vs flexible general-purpose in-memory layer with rich data structures (ElastiCache/Redis).

---

## 9. Troubleshooting

| Symptom                                            | Cause                                                                                      | Fix                                                                                                           |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| App shows stale data after a DB update             | Cache-aside without invalidating/updating on write                                         | Explicitly invalidate/update the relevant cache key on data change                                            |
| Cache node failure causes app-wide outage          | Not using Redis Multi-AZ failover, or using Memcached (no native HA)                       | Enable Redis Multi-AZ automatic failover for production                                                       |
| Cache running out of memory/evicting unexpectedly  | Single-shard dataset outgrew one node's capacity                                           | Migrate to Cluster Mode Enabled proactively before hitting this limit                                         |
| Confusion choosing DAX vs ElastiCache for DynamoDB | Not distinguishing DAX's DynamoDB-specific purpose from ElastiCache's general-purpose role | Use DAX for DynamoDB with zero code changes; ElastiCache if broader flexibility/non-DynamoDB sources involved |

---

## 10. Best Practices & Anti-Patterns

Best practices: default to Redis over Memcached unless genuinely simple/ephemeral; use cache-aside as default, write-through for genuine freshness needs; enable Multi-AZ failover for production Redis; plan Cluster Mode proactively; use ElastiCache to externalize session state for stateless tiers.

Anti-patterns: choosing Memcached by default without confirming its limitations are acceptable; using write-through universally; running production Redis without Multi-AZ; confusing DAX/ElastiCache's distinct purposes.

---

## 11. Common Misconceptions

- "Redis and Memcached are basically interchangeable." False - Redis offers persistence, replication, native HA, rich structures Memcached lacks.
- "A cache automatically stays in sync with the database." False - cache-aside requires the app to handle invalidation; staleness is a managed risk, not automatic.
- "ElastiCache and DAX are the same kind of thing for different databases." Partially false - DAX needs no code changes; ElastiCache requires explicit caching logic implementation.
- "Memcached and Redis have the same HA capabilities." False - Memcached has no native replication/failover; Redis does via Multi-AZ.

---

## 12. Interview Questions (with model answers)

Beginner - What problem does ElastiCache solve? Inserts an in-memory caching layer absorbing repeated reads so the database only serves the first request, with subsequent requests served from memory. Also serves as a shared externalized session store for stateless app tiers.

Beginner - When choose Memcached over Redis? Only for genuinely simple, purely ephemeral key-value caching with no persistence/replication/failover need - Memcached's simpler multi-threaded model fits there. Redis is the more broadly capable default for most production scenarios.

Intermediate - Trade-off between cache-aside and write-through? Cache-aside: check cache first, query DB only on miss, populate cache after - simple, resilient to cache failures, but first request pays full DB latency and data can go stale without invalidation. Write-through: writes to cache and DB together - never stale relative to a completed write, but adds write latency and cache space for potentially unread data. Cache-aside is the common default; write-through fits when read-after-write freshness matters.

Intermediate - How decide between DAX and ElastiCache for a DynamoDB-backed app? If DynamoDB is the only source needing caching and zero code changes are wanted (DAX is API-compatible), DAX is simpler/purpose-built. Reach for ElastiCache for more flexibility - multiple data sources, Redis's richer data structures (leaderboard, pub/sub), or existing custom caching logic not mapping to DAX's DynamoDB-specific model.

Senior - Design caching for high-traffic e-commerce: product catalog in RDS, user sessions, real-time trending-products feature? Catalog (read-heavy, tolerates brief staleness): ElastiCache Redis with cache-aside, reasonable TTL, explicit invalidation on updates. Sessions: same/separate Redis cluster as externalized session store, making the web tier stateless. Trending products: Redis sorted sets - increment score per view/purchase, query top N directly - a feature Memcached couldn't support natively and a plain DB query couldn't serve with the same real-time responsiveness. Enable Multi-AZ failover given the cache's now-central role across three features; plan Cluster Mode if catalog/session volume is expected to outgrow one node.

---

## Key Takeaways

1. ElastiCache is a general-purpose, managed in-memory data store - absorbing read load in front of any database and serving as the externalized session store making app tiers stateless.
2. Redis is the broadly-capable default; Memcached is a narrower, simpler fit - persistence, native replication, automatic Multi-AZ failover, and rich data structures are Redis-only.
3. Cache-aside (resilient, accepts staleness/miss-penalty) and write-through (fresh, higher write cost) are the two foundational patterns - cache-aside the common default.
4. Redis Cluster Mode enables horizontal sharding beyond one node's memory/throughput ceiling - a proactive architectural decision.
5. DAX and ElastiCache are genuinely different tools - DAX is DynamoDB-specific with no code changes; ElastiCache is general-purpose requiring explicit caching logic.

## Related Concepts (forward links)

- Amazon Redshift for analytical/data-warehouse workloads, a genuinely different paradigm -> [§55](./Section-55-Part6-Redshift-Data-Warehousing.md)
- DocumentDB and Neptune as further specialized database engines -> [§56](./Section-56-Part6-DocumentDB-Neptune.md)
- Choosing among all of Part 6's database services for a given workload -> [§57](./Section-57-Part6-DMS-Choosing-Right-Database.md)
