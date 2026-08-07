# Section 17 (Part 2): Memorystore

## 1. Definition

**Plain language:** Memorystore is Google's fully managed in-memory caching service — it runs Redis or Memcached for you so applications can read and write data in microseconds instead of the milliseconds a disk-backed database needs, typically sitting in front of a "real" database to absorb repeated reads or hold short-lived, fast-moving data like sessions.

**Precise:** Memorystore is a fully managed, in-memory data store service offering two engines — **Memorystore for Redis** (including a **Cluster** tier for horizontal scaling) and **Memorystore for Memcached** — that handles provisioning, patching, failover, and monitoring of the underlying instances, exposing the same wire protocol as open-source Redis/Memcached so existing client libraries work unmodified.

## 2. Why It Exists / Problem It Solves

Relational and even NoSQL databases are disk-backed (or at least disk-durable), which means every read ultimately competes with I/O latency and query-planning overhead measured in single-digit milliseconds at best. Many application patterns — caching expensive query results, storing ephemeral session state, rate-limiting counters, leaderboards, pub/sub messaging — don't need durability guarantees at all, but do need sub-millisecond latency at very high request rates. Running Redis or Memcached yourself on Compute Engine means owning failover, patching, memory-eviction tuning, and version upgrades. Memorystore exists to remove that operational burden while preserving 100% client-library compatibility, since it speaks the actual Redis/Memcached protocol rather than a proprietary API.

## 3. Core Concepts

### 3.1 Two Engines, Two Purposes

- **Memorystore for Memcached** is a simple, multi-threaded, pure cache — no persistence, no complex data structures, data can be evicted at any time. It excels at raw key-value caching with the highest possible throughput per node and horizontal scaling via a flat pool of nodes.
- **Memorystore for Redis** supports rich data structures (lists, sets, sorted sets, hashes, streams), optional persistence (RDB snapshots/AOF), pub/sub messaging, and Lua scripting — making it suitable for use cases beyond pure caching, such as leaderboards, rate limiters, and session stores that benefit from atomic operations.

### 3.2 Tiers: Basic, Standard (HA), and Cluster

Memorystore for Redis offers a **Basic tier** (single node, no replication — data loss on maintenance/failure) and a **Standard tier** (primary + replica in different zones, automatic failover, an SLA-backed uptime commitment). For workloads needing more throughput or memory than a single node can provide, the **Redis Cluster** tier shards data across multiple shards (each with its own primary/replica set), similar in spirit to Bigtable's node-based horizontal scaling but for an in-memory Redis-protocol workload.

### 3.3 Caching Patterns

- **Cache-aside (lazy loading):** The application checks the cache first; on a miss, it reads from the source database and writes the result into the cache before returning it. This is the most common pattern and keeps the cache populated only with actually-requested data.
- **Write-through:** The application writes to the cache and the source database together, keeping them always in sync at the cost of extra write latency.

> ⚠️ **Interview-relevant nuance:** Memorystore is not a database of record — even the Standard (HA) tier's failover can lose a small window of recently written data, and the Basic tier can lose everything on a single node failure or maintenance event. Any data that must never be lost belongs in Cloud SQL, Spanner, Firestore, or Bigtable, with Memorystore only ever caching or holding derivable/ephemeral data in front of it.

## 4. Architecture Diagram

```
        Application (cache-aside pattern)
                    │
        1) GET key  ▼
              ┌────────────────┐   miss    ┌──────────────────────┐
              │  Memorystore   │──────────►│  Cloud SQL / Spanner │
              │  (Redis)       │◄──────────│  (source of truth)   │
              └────────────────┘  2) SET   └──────────────────────┘
                    ▲                 (populate cache with result)
                    │ hit (sub-ms)
              Application returns cached value directly, skipping the DB
```

## 5. Hands-On Examples

**Create a Standard-tier (HA) Redis instance (Beginner):**

```bash
gcloud redis instances create session-cache \
  --region=us-central1 --tier=STANDARD_HA \
  --size=5 --redis-version=redis_7_0
```

**Purpose:** Provisions a 5 GB Redis instance with an automatic-failover replica in a second zone, suitable for session storage where brief unavailability is acceptable but data loss on a single-node failure is not.

**Expected output (abbreviated):**

```
Creating instance...done.
createTime: '2026-07-25T09:00:00Z'
host: 10.0.0.5
port: 6379
state: READY
tier: STANDARD_HA
```

**Connect and test with `redis-cli` from a VM in the same VPC (Intermediate):**

```bash
redis-cli -h 10.0.0.5 -p 6379 SET session:abc123 '{"user":"alice"}'
redis-cli -h 10.0.0.5 -p 6379 GET session:abc123
```

**Expected output:**

```
OK
"{\"user\":\"alice\"}"
```

**Create a Memcached instance (Beginner):**

```bash
gcloud memcache instances create web-cache \
  --region=us-central1 --node-count=3 --node-cpu=2 --node-memory=4GB
```

**Purpose:** Provisions a 3-node Memcached cluster for straightforward, high-throughput page/fragment caching where persistence and rich data structures aren't needed.

## 6. Comparison vs. AWS ElastiCache / Azure Cache for Redis

| Concept                | Memorystore                                                             | AWS ElastiCache                                                             | Azure Cache for Redis                                                        |
| ---------------------- | ----------------------------------------------------------------------- | --------------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Engines offered        | Redis (with Cluster tier), Memcached                                    | Redis (with Cluster mode), Memcached, Valkey                                | Redis (Basic/Standard/Premium/Enterprise tiers)                              |
| HA model               | Standard tier: primary + replica across zones, automatic failover       | Multi-AZ with automatic failover (Redis); no built-in HA for Memcached      | Standard/Premium tiers: primary + replica, zone redundancy on Premium+       |
| Horizontal scaling     | Redis Cluster tier (sharded); Memcached scales by adding nodes          | Redis Cluster mode (sharded); Memcached scales by adding nodes              | Premium/Enterprise tiers support clustering                                  |
| Protocol compatibility | Native Redis/Memcached wire protocol — existing clients work unmodified | Native Redis/Memcached wire protocol                                        | Native Redis wire protocol                                                   |
| Ideal use case         | GCP-native workloads wanting minimal operational overhead for caching   | AWS-native workloads; broadest engine/version selection among the big three | Azure-native workloads; Enterprise tier adds Redis modules (RedisJSON, etc.) |

## 7. Production & Enterprise Usage

- **Session stores:** Web and mobile backends store user session state in Redis with a TTL, keeping stateless application servers behind a load balancer while session data survives individual server restarts.
- **Database query result caching:** Cache-aside in front of Cloud SQL or Spanner absorbs read-heavy traffic (e.g., product catalog lookups), cutting database load and p99 latency dramatically for repeated queries.
- **Rate limiting and counters:** Redis's atomic `INCR`/`EXPIRE` operations implement API rate limiters and leaderboards without race conditions, something a disk-backed database would struggle to do at the same throughput.
- **Pub/sub for real-time features:** Redis pub/sub backs lightweight real-time notifications (e.g., "user is typing" indicators) where Cloud Pub/Sub's durability guarantees are unnecessary overhead.

## 8. Common Misconceptions

- **Misconception:** "Memorystore is a database and can be my only data store." Even the HA tier's replication window can lose recent writes on failover, and the Basic tier offers no durability at all — Memorystore should always sit in front of a durable source of truth, never replace one.
- **Misconception:** "Redis and Memcached are interchangeable — just pick whichever." Memcached is simpler and multi-threaded (often higher raw throughput for pure key-value gets/sets), but Redis supports rich data structures, persistence options, and pub/sub — the choice depends on whether the workload needs more than plain caching.

## 9. Interview Questions

**🎯 Beginner:** _What is the difference between Memorystore's Basic and Standard tiers?_
**Model answer:** The Basic tier runs a single Redis node with no replication, so a node failure, maintenance event, or restart can lose all cached data with some downtime — acceptable for pure, easily-repopulated caches. The Standard (HA) tier runs a primary plus a replica in a different zone with automatic failover and a service-level uptime commitment, at higher cost, appropriate for workloads like session storage where availability matters more, even though even Standard tier isn't a durability guarantee for critical data.

**🎯 Intermediate:** _Explain the cache-aside pattern and one risk it introduces._
**Model answer:** In cache-aside, the application checks Memorystore first; on a cache miss, it reads from the source database, then writes that value into the cache before returning it, so subsequent identical requests are served from cache. The main risk is stale data: if the underlying database row changes but the cache isn't invalidated or given a short-enough TTL, reads can keep returning outdated values — mitigations include setting appropriate TTLs, explicitly invalidating/updating the cache key on writes, or accepting eventual consistency where the use case tolerates it.

**🎯 Senior/Architect:** _Design a caching layer for a global e-commerce product catalog served from Cloud Spanner, where read traffic is 50x write traffic and p99 latency must stay under 5ms._
**Model answer:** I'd place a Memorystore for Redis Standard-tier (or Cluster tier if the working set exceeds a single node's memory) instance in each region serving traffic, using the cache-aside pattern: application reads check Redis first, fall back to Spanner on a miss, and populate Redis with a TTL tuned to the catalog's actual update frequency (e.g., a few minutes) rather than caching indefinitely. Given the 50:1 read:write ratio, I'd also consider a short write-through step on product updates (invalidate or proactively refresh the specific product's cache key) to reduce the miss-driven latency spike right after a price/inventory change, rather than relying purely on TTL expiry. I'd size the Redis instance's memory to comfortably hold the "hot" catalog subset (not necessarily the entire catalog) based on observed access patterns, monitor cache hit rate as the primary health signal, and keep Spanner as the unambiguous source of truth so a total Redis outage degrades latency rather than causing incorrect data — the application must still function (slower) with Redis unavailable.

## 10. Key Takeaways

- 🔑 Memorystore is a fully managed cache, not a database of record — it must always sit in front of a durable store like Cloud SQL, Spanner, Firestore, or Bigtable.
- 🔑 Memcached is simpler and pure-cache; Redis adds rich data structures, optional persistence, and pub/sub, making the engine choice depend on whether the workload needs more than plain key-value caching.
- 🔑 The Standard (HA) tier adds automatic cross-zone failover over the Basic tier, but even it is not a durability guarantee — brief data loss on failover is possible.
- 🔑 Cache-aside is the dominant pattern; correct TTL/invalidation design is what prevents stale-data bugs, not the caching layer itself.

## 11. Related Concepts

Cloud SQL ([Section 13](./Section-13-Part2-Cloud-SQL.md)) and Cloud Spanner ([Section 14](./Section-14-Part2-Cloud-Spanner.md)) as the durable sources of truth Memorystore typically caches in front of, Firestore's own built-in real-time sync as an alternative to a manual cache for client-facing apps ([Section 15](./Section-15-Part2-Firestore-Datastore.md)), the storage/database decision matrix that places Memorystore in context against every other Part 2 service ([Section 18](./Section-18-Part2-Storage-DB-Decision-Matrix.md)), and the AWS ElastiCache/Azure Cache for Redis comparison here and in [Section 82](../Part13/Section-82-Part13-GCP-vs-AWS-vs-Azure-Comparison.md).
