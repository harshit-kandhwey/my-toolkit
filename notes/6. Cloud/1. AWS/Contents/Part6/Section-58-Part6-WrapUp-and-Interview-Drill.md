# Part 6 - Section 10 - Part 6 Wrap-Up + Database Interview Drill

AWS Zero-to-Enterprise Knowledge Base - Part 6: Databases (Final Section)

---

## 1. Part 6 Consolidated Knowledge Map

Databases (Part 6) breaks down into:

- S1 RDS Fundamentals: Managed engines, 6 engines, parameter groups
- S2 RDS HA/Read Replicas/Backup: Multi-AZ vs Read Replica, PITR
- S3 Aurora Deep Dive: Shared storage, 6-way replicated, fast failover, Global Database
- S4 DynamoDB Fundamentals: Access-pattern-first design, Query vs Scan
- S5 DynamoDB Advanced: GSI/LSI, Streams, Global Tables, DAX
- S6 ElastiCache: Redis/Memcached, cache-aside/write-through, session store
- S7 Redshift: OLAP, columnar, MPP, Spectrum
- S8 DocumentDB & Neptune: Document/graph paradigms
- S9 DMS & Choosing the Right Database: Migration mechanics, full decision framework

Throughline: S1-3 build relational databases (RDS, its HA mechanics, then Aurora's architecturally distinct evolution) to full depth. S4-5 pivot to DynamoDB's genuinely different NoSQL paradigm. S6 adds a caching layer usable in front of anything. S7-8 cover analytical (Redshift) and specialized (DocumentDB, Neptune) data models. S9 ties everything together: moving data between engines, and choosing correctly.

---

## 2. Consolidated Key-Takeaways Checklist

- Explain what RDS manages for you and why Parameter/Option Groups replace direct config-file access.
- Distinguish Multi-AZ (synchronous, non-readable, automatic failover) from Read Replicas (asynchronous, readable, manual promotion) precisely.
- Explain Aurora's shared-storage architecture and why it produces faster failover and lower-lag replicas than standard RDS.
- Explain DynamoDB's access-pattern-first design principle and the Query-vs-Scan distinction.
- Distinguish GSI (different partition key, addable anytime, eventually consistent) from LSI (same partition key, creation-time-only, optionally strongly consistent).
- Explain cache-aside vs write-through, and when Redis is preferred over Memcached.
- Explain OLTP vs OLAP and why columnar storage suits analytical aggregation.
- Explain when DocumentDB or Neptune is the right fit versus a general-purpose database.
- Explain how DMS minimizes migration downtime, and walk the complete data-shape decision framework from memory.

---

## 3. Progressive Hands-On Labs - Part 6

### Lab 1 (Beginner) - RDS Multi-AZ and Failover

1. Launch an RDS MySQL/PostgreSQL instance with Multi-AZ enabled, in private subnets.
2. Connect an application/script and confirm connectivity via the instance endpoint.
3. Manually trigger a failover (Console's "Reboot with failover") and observe the brief interruption and automatic reconnection.

### Lab 2 (Beginner) - DynamoDB Access Patterns

1. Create a table with CustomerID as partition key, OrderDate as sort key.
2. Insert items; run a Query for one customer's orders.
3. Attempt "all orders over $500 across all customers" - observe this requires a Scan - add a GSI keyed appropriately and re-run as an efficient Query.

### Lab 3 (Intermediate) - ElastiCache Cache-Aside

1. Deploy ElastiCache for Redis in a private subnet, Multi-AZ enabled.
2. Implement cache-aside: check Redis first, fall back to RDS on miss, populate Redis after.
3. Demonstrate hit-vs-miss latency difference; manually invalidate a key after a simulated update.

### Lab 4 (Intermediate) - Aurora vs Standard RDS Comparison

1. Provision a small Aurora MySQL cluster alongside standard RDS MySQL with a Read Replica.
2. Compare observed replica lag and failover time between the two.
3. Document differences against Section 3's claimed architectural advantages.

### Lab 5 (Capstone) - Polyglot Architecture Decision Document

1. For a hypothetical app (ride-sharing: trip records, driver-location caching, historical trip analytics, "drivers who know this route" relationship feature), map each component to the correct database service using the Section 9 framework.
2. Write a justification for each choice, noting where DMS would be used migrating from an existing single-database system.

---

## 4. Cross-Section Interview Drill

**Why doesn't DynamoDB's "know your access patterns first" principle apply to RDS/Aurora the same way?**
Relational databases use SQL, expressing arbitrary joins/filters after the fact - the query language provides flexibility so you don't predict every query at design time. DynamoDB's efficiency depends entirely on exact partition-key matches with no equivalent query-time flexibility, so the key structure must be chosen upfront based on actual queries, or you're stuck with inefficient Scans.

**How do Aurora Replicas and DynamoDB Global Tables both achieve fast cross-node consistency, using genuinely different mechanisms?**
Aurora Replicas achieve low lag by reading from the same shared storage the primary writes to - no data to replay. DynamoDB Global Tables use Streams-based multi-active replication across Regions - genuinely different, since Global Tables handle simultaneous multi-Region writes with conflict resolution, which read-only Aurora Replicas never face.

**A team's ElastiCache Redis cluster caches DynamoDB data - would DAX be better, and why or why not?**
Depends on whether ElastiCache is purely a DynamoDB read cache with custom cache-aside logic, or used for something DAX doesn't offer. If purely caching DynamoDB reads with standard logic, DAX is simpler - API-compatible with DynamoDB, no custom logic needed. If using Redis-specific features (sorted sets, pub/sub) or caching other sources too, ElastiCache's flexibility is the better fit - DAX wouldn't cover those.

**Design a database architecture for a global e-commerce platform: catalog, order processing, sessions, sales analytics, fraud detection on account relationships - with sub-minute cross-Region failover on order processing.**
Order processing: Aurora with Aurora Global Database given the sub-minute RTO requirement - purpose-built cross-Region replication and fast promotion, more reliable than standard RDS Read Replicas for this. Product catalog: DynamoDB if access patterns are well-understood; DocumentDB if attributes are highly variable per product line - a genuine trade-off. Session management: ElastiCache for Redis with Multi-AZ, stateless web tier. Sales analytics: Redshift, fed via ongoing DMS replication or ETL/ELT from Aurora, keeping analytical load off the transactional database; Spectrum for older infrequent historical data via S3. Fraud detection on account relationships: Neptune, a genuinely multi-hop relationship-traversal problem. If migrating from a single existing database, DMS (with Schema Conversion Tool for heterogeneous pieces) moves each dataset incrementally with minimal downtime.

---

## 5. Related Technologies (forward links, consolidated)

- SQS/SNS/EventBridge/Kinesis for event-driven integration with databases (DynamoDB Streams triggers, ETL pipelines) -> Part 7
- CloudWatch monitoring of database metrics, CloudTrail logging of database API activity -> Part 8
- Infrastructure as Code for provisioning RDS/Aurora/DynamoDB and replication configuration -> Part 9
- Migration strategies (the 6 Rs) at the full-application level, building on DMS -> Part 10
- Well-Architected Reliability and Performance Efficiency pillars formalizing database HA/DR and scaling choices -> Part 10

---

## 6. Recommended Certification Alignment

- AWS Certified Database - Specialty is almost entirely a formalized, deep test of this Part's content.
- AWS Certified Solutions Architect - Associate/Professional both weight RDS, Aurora, and DynamoDB heavily, with growing emphasis on the broader specialized-database decision framework.

---

## Part 6 - Final Consolidated Key Takeaways

1. Every database in this Part exists because a specific data shape/query pattern is genuinely awkward in a general-purpose relational database - RDS/Aurora for transactional relational, DynamoDB for access-pattern-known key-value at scale, Redshift for analytical aggregation, DocumentDB for flexible documents, Neptune for relationship traversal.
2. Aurora's shared-storage architecture and DynamoDB's access-pattern-first design are the two most conceptually important architectural insights in this Part - genuine departures from "traditional database plus automation."
3. High availability and read scaling are always two distinct concerns - RDS Multi-AZ vs Read Replicas, or Aurora's unified but distinguishable mechanics - conflating them is a frequently-tested mistake.
4. ElastiCache is a universal caching layer, not tied to any one database - cache-aside vs write-through is decided per use case, independent of the database behind the cache.
5. Choosing a database is a data-shape-and-query-pattern decision, and DMS is the tool that moves data once decided - polyglot persistence is the expected, standard outcome of applying this framework to any complex real-world system.

---

## Part 6 Complete

All 10 sections of Databases are done. Next: Part 7 - Application Integration & Streaming (SQS, SNS, EventBridge, Step Functions, Kinesis, MSK).
