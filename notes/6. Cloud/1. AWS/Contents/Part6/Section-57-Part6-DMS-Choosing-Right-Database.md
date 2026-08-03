# Part 6 - Section 9 - Database Migration Service & Choosing the Right Database

AWS Zero-to-Enterprise Knowledge Base - Part 6: Databases

---

## 1. Definition

Plain-language: AWS Database Migration Service moves data from one database to another - including between genuinely different engines - with minimal downtime, while your application keeps running against the source until ready to cut over. Choosing the right database means matching data's actual shape and query patterns to the purpose-built service for that pattern, not defaulting to familiarity.

Precise: AWS Database Migration Service (DMS) is a managed service for migrating databases to AWS (or between AWS databases), supporting homogeneous (same engine) and heterogeneous (different engines, via AWS Schema Conversion Tool) migrations, with minimal downtime via continuous replication during the migration window.

---

## 2. AWS Database Migration Service (DMS)

### 2.1 Why It Exists

- Migrating a live production database is risky - can't just copy once and cut over, since the source keeps changing during migration, and cutover downtime is business-impacting.
- DMS performs an initial full load, then continuously replicates ongoing changes from source to target throughout the migration - target stays synchronized with the live source until actual cutover, minimizing downtime to just that final moment.

### 2.2 Homogeneous vs Heterogeneous Migrations

- Homogeneous - same engine on both sides (on-prem PostgreSQL to RDS PostgreSQL, RDS MySQL to Aurora MySQL) - simpler, schema/types transfer directly.
- Heterogeneous - different engines (Oracle to Aurora PostgreSQL, relational to DynamoDB) - requires schema/data-type conversion via AWS Schema Conversion Tool (SCT), which analyzes source schema and generates an equivalent target schema, flagging items needing manual attention.

### 2.3 Connection to Section 8's Framework

A heterogeneous migration is frequently the actual mechanism for adopting a specialized database - realizing relationship-heavy queries would fit Neptune better, or access-pattern-known key-value work would scale better on DynamoDB - DMS/SCT moves existing data into that better-fitting engine rather than starting from scratch.

---

## 3. Complete Database Decision Framework

Question: what is the data's shape, and what's the dominant query pattern?

- Relational, transactional (joins, ACID) -> RDS or Aurora (Aurora if faster failover/replicas/Global DB matter)
- Key-value, known access patterns, massive scale -> DynamoDB (+DAX if read-heavy at extreme scale)
- Analytical, aggregate-heavy (OLAP) -> Redshift (+Spectrum for cold data via S3)
- Nested, flexible-schema documents -> DocumentDB (or DynamoDB if access-pattern-first fits better)
- Relationship-heavy, multi-hop traversal -> Neptune (graph-specific query languages)

- Layer ElastiCache in front of any of these for read-heavy caching or session-state needs - complementary, not a competing choice at the same decision point.
- Layer DMS whenever moving existing data into whichever engine the framework points to - the framework answers "which database," DMS answers "how do I get my data there."

---

## 4. Applying the Framework - Worked Reasoning

### 4.1 "It's relational, but which one?"

Standard RDS: specific engine required (Oracle/SQL Server), cost-driven, or 100% native compatibility matters. Aurora: faster failover, lower-lag replicas, Global Database DR, or Serverless economics genuinely valuable.

### 4.2 "It's key-value at scale, but do I need more than DynamoDB?"

DynamoDB: access patterns well-known, designable upfront. DocumentDB: genuinely document-shaped variable structure, or MongoDB compatibility matters.

### 4.3 "It's analytical, but how much data, how often queried?"

Redshift-loaded storage: frequently-queried, performance-critical data. Redshift Spectrum + S3: infrequently-queried historical data where storage savings outweigh query-latency trade-off.

### 4.4 "There are relationships in my data - do I need Neptune?"

No, if relationships are simple/shallow and well-served by normal joins. Yes, specifically when the pattern requires genuinely deep multi-hop traversal expensive/complex as a join chain.

---

## 5. Production & Enterprise Usage

- DMS as the standard migration mechanism for both cloud migrations (on-prem to AWS) and in-AWS modernization (legacy engine to better-fitting one).
- Polyglot persistence - mature architectures frequently use multiple database types simultaneously for different parts of one application - the standard pattern for complex real-world systems, not an edge case.
- DMS for ongoing continuous replication (not just one-time migration) - maintaining an ongoing feed from an OLTP source into an analytical target (e.g., continuously feeding Redshift from RDS) - one concrete ETL/ELT mechanism.

---

## 6. Security Considerations

- DMS replication instances/endpoints follow the same VPC-isolation and encryption patterns as every database in this Part - DMS needs appropriately scoped IAM permissions and network access to both source and target.
- Migrating sensitive data heterogeneously means verifying the target engine's security model is configured correctly before cutover - a migration shouldn't silently downgrade the source's security posture.

---

## 7. Troubleshooting

| Symptom                                                                | Cause                                                                     | Fix                                                                                          |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| Migration to a different engine has unexpected schema/data-type issues | Heterogeneous schema/type differences not fully addressed                 | Use Schema Conversion Tool to properly convert schema, address flagged issues before cutover |
| Application needs extended downtime during migration                   | Not using DMS's continuous replication; treating it as one-time bulk copy | Use DMS continuous replication, minimizing downtime to the final cutover                     |
| Team defaulted to a familiar engine despite poor fit                   | Choosing by familiarity rather than the framework                         | Revisit the decision framework against actual data shape/query pattern                       |
| Application ends up needing several database types                     | Assuming one database type should serve an entire complex application     | Expected for complex applications (polyglot persistence); not itself a problem               |

---

## 8. Best Practices & Anti-Patterns

Best practices: use DMS with continuous replication for live migrations; use SCT proactively, addressing issues before cutover; apply the data-shape/query-pattern framework explicitly; embrace polyglot persistence for complex applications.

Anti-patterns: live migration without continuous replication (unnecessary downtime); skipping schema-conversion validation; choosing an engine by familiarity alone; forcing an entire complex application onto one database type.

---

## 9. Common Misconceptions

- "Migrating a database always requires significant downtime." False - DMS continuous replication minimizes downtime to the final cutover.
- "DMS only works for same-engine migrations." False - heterogeneous migrations are explicitly supported via SCT.
- "A well-architected application uses exactly one database type." False - polyglot persistence is the standard pattern for complex systems.
- "Choosing a database is mostly about team familiarity." False - the primary technical criterion should be data shape and dominant query pattern.

---

## 10. Interview Questions (with model answers)

Beginner - How does DMS minimize downtime during migration? Full load of existing data, then continuous replication of ongoing changes throughout the migration, keeping the target synchronized with the live source. Downtime limited to the final cutover, not the entire migration duration.

Beginner - Homogeneous vs heterogeneous migration? Homogeneous: same engine both sides (on-prem PostgreSQL to RDS PostgreSQL), schema/types transfer directly. Heterogeneous: different engines (Oracle to Aurora PostgreSQL), requires schema/data-type conversion via the Schema Conversion Tool.

Intermediate - Team wants to move fraud detection from SQL joins on RDS to a purpose-built solution - how does this connect to Section 8 and this section? Heterogeneous migration - moving relationship-heavy fraud data to Neptune, since graph databases are purpose-built for deep multi-hop relationship traversal relational joins handle poorly. Use DMS + SCT to migrate the relevant relationship data into Neptune with continuous replication, minimizing downtime, while the rest of the application stays on RDS - a concrete polyglot persistence example, a targeted migration not an all-or-nothing switch.

Senior - Company has all data in one RDS instance (orders, sessions, historical analytics, purchase-relationship recommendations) hitting a bottleneck - design target architecture and migration approach? Apply the framework to each workload separately. Orders: stay relational, move to Aurora for better replica/failover as scale grows, via DMS continuous replication (homogeneous, both PostgreSQL-compatible). Session data: move to ElastiCache for Redis, externalizing state, removing unsuited load from the primary database. Historical analytics: move to Redshift, fed via ongoing DMS replication or scheduled ETL/ELT from the Aurora source - the OLTP/OLAP separation from Section 7. Recommendation feature: migrate relationship data into Neptune via DMS+SCT, since purchase-relationship recommendations are a multi-hop graph problem. End state: a polyglot architecture (Aurora, ElastiCache, Redshift, Neptune) each handling its suited workload, migrated incrementally via DMS rather than one disruptive cutover.

---

## Key Takeaways

1. AWS DMS minimizes migration downtime via full-load-plus-continuous-replication, not a one-time bulk copy.
2. Homogeneous migrations (same engine) are simpler than heterogeneous ones (different engines), which need the Schema Conversion Tool.
3. DMS is frequently the actual mechanism for adopting a specialized database from Sections 4-8 once the data-shape framework identifies a better fit.
4. The complete database decision framework is data-shape-and-query-pattern-first, never default-preference-first.
5. Polyglot persistence - multiple database types serving different parts of one application - is the standard, expected pattern for complex real-world systems.

## Related Concepts (forward links)

- Part 6 Wrap-Up and comprehensive Database interview drill -> §58 (final section)
- ETL/ELT pipelines and Kinesis for data movement patterns beyond DMS -> Part 7
- Migration strategies (the 6 Rs) at the full-application level -> Part 10
