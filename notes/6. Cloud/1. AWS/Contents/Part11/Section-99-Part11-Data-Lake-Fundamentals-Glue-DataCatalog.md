# Part 11, Section 1: Data Lake Fundamentals & AWS Glue / Data Catalog

## 1. Definition

**Plain language:** Everything in Parts 5 and 6 assumed data lives in a well-structured place — an S3 object with a known shape, or a database table with a fixed schema. Real organizations also accumulate enormous volumes of raw, differently-shaped data (logs, clickstreams, exported CSVs, JSON events, Parquet files from a dozen different systems) that nobody has fully modeled into a database yet. A **data lake** is where that raw data lives — cheaply, at scale, in its original format — and **AWS Glue Data Catalog** is the piece that makes a pile of files in S3 queryable as if it were a set of database tables, without actually moving or reshaping the data first.

**Precise definition:** A data lake is a centralized repository — on AWS, built on Amazon S3 — that stores structured, semi-structured, and unstructured data at any scale, in its native format, without requiring schema definition or transformation prior to storage ("schema-on-read" rather than the "schema-on-write" model relational databases like RDS require, Part 6 §1). The **AWS Glue Data Catalog** is a persistent, managed metadata repository — a Hive-metastore-compatible catalog of table definitions (schema, location, format, partitioning) that describes data sitting in S3 (or other sources) without duplicating the data itself, and which every AWS analytics service in this Part (Athena, Redshift Spectrum, EMR) reads from as a shared, central source of truth for "what tables exist and what do they look like."

## 2. Why It Exists / Problem It Solves

- Relational databases (Part 6) require a schema to be defined _before_ data is written — appropriate for well-understood, transactional workloads, but a poor fit for raw, high-volume, variably-structured data where defining a rigid schema upfront is either impossible (the data's shape isn't fully known yet) or would require expensive transformation before the data could even be stored.
- Object storage alone (S3, Part 5 §1) solves the "store cheaply at any scale, in any format" problem, but S3 by itself has no concept of "tables," "schemas," or "columns" — it just stores objects (files). Without something layered on top, querying "all the orders from Q3 where region = 'EU'" across a folder of JSON files would require every consuming application to independently know and hardcode that folder's structure.
- The Glue Data Catalog solves exactly this gap: it lets an organization define (or automatically infer, via Crawlers, §4.3) a table's schema — pointing at where the underlying files actually live in S3 — once, centrally, and have every analytics tool (Athena, Redshift Spectrum, EMR, and even some third-party tools) query that same table definition consistently, rather than every tool needing its own separate, potentially inconsistent understanding of the data's shape.
- 🔑 **Key takeaway:** the data lake pattern deliberately decouples _storage_ (cheap, schema-flexible, in S3) from _schema/metadata_ (centralized, in the Glue Data Catalog) from _compute_ (whichever query engine — Athena, Redshift Spectrum, EMR — is best suited to a given workload) — a fundamentally different architecture from a traditional database, where storage, schema enforcement, and compute are all bundled into one engine.

## 3. Prerequisites and Dependencies

- **Amazon S3** (Part 5 §1-4): the data lake's actual storage layer; Glue Data Catalog tables point at S3 locations, they don't replace S3 storage.
- **IAM** (Part 2 §1-3): Glue Crawlers and Jobs run under an IAM role/permissions, and the Data Catalog itself is subject to IAM-based access control (and, for finer-grained control, Lake Formation permissions — Part 11 §2).
- General familiarity with structured file formats (CSV, JSON, Parquet, ORC) — Glue and the rest of this Part assume comfort with the idea that data can be stored in different serialization formats with meaningfully different performance characteristics (§4.4).

## 4. Internal Working / Architecture & Components

### 4.1 The Data Lake Storage Layer

- Built on S3, typically organized into **zones** reflecting a data's processing maturity — a common pattern (not an AWS-enforced requirement) uses a **raw/bronze zone** (data exactly as ingested, untouched), a **cleaned/silver zone** (validated, deduplicated, standard formats), and a **curated/gold zone** (business-ready, aggregated, optimized for query performance) — each zone typically its own S3 prefix or bucket.
- Data lands in the raw zone via varied ingestion paths depending on source: batch exports, Kinesis Data Firehose (Part 7 §7) for streaming data, DMS (Part 6 §9) for database change-data-capture, or direct application writes.

### 4.2 The Glue Data Catalog

| Component                      | Explanation                                                                                                                                                                                                                                                                                                                |
| ------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Database** (Catalog concept) | A logical grouping of tables in the Data Catalog — a namespace, not a physical database engine; purely organizational.                                                                                                                                                                                                     |
| **Table**                      | A Data Catalog entry describing one dataset's schema (column names/types), the S3 location the data actually lives at, the file format (CSV, JSON, Parquet, ORC), and partitioning scheme — critically, the table definition is metadata only; creating a Catalog table does not move, copy, or transform any actual data. |
| **Partition**                  | A subdivision of a table's data, typically by a column like date or region, corresponding to a specific S3 prefix (e.g., `s3://bucket/sales/year=2026/month=07/`) — partitioning is what lets a query engine skip scanning irrelevant data entirely, a major performance and cost lever (§11).                             |
| **Connection**                 | Stored connectivity details (JDBC endpoint, credentials reference) letting Glue Crawlers and Jobs reach non-S3 data sources, such as an RDS database, for cataloging or ETL purposes.                                                                                                                                      |

### 4.3 Glue Crawlers — Automatic Schema Discovery

- A **Crawler** is a Glue component that scans a specified data source (an S3 path, or a connected database), infers the schema (column names, inferred data types) and file format, detects partitioning structure from folder naming conventions, and writes or updates the corresponding Data Catalog table definition automatically.
- Why this matters: without a Crawler, someone would need to manually write out every table's exact schema by hand — impractical at real data lake scale, and especially impractical when source data's shape evolves over time (new columns appearing, format changes). Crawlers can be scheduled to re-run periodically, keeping the Catalog's understanding of a dataset's schema current as the underlying data evolves.
- ⚠️ **Warning:** Crawler schema inference is a best-effort heuristic, not a guarantee — it can occasionally misinfer a column's data type (e.g., inferring a column that's usually numeric but occasionally contains a stray non-numeric value as a string type), or fail to correctly detect an intended partitioning scheme from an unconventional folder-naming pattern. Reviewing a Crawler's inferred schema after first run, especially for a new or unusually-structured dataset, is a standard practice, not an optional afterthought.

### 4.4 File Format Matters — A Cross-Cutting Concern for This Entire Part

- **Row-based formats** (CSV, JSON): human-readable, simple to produce, but a query engine reading a row-based file for one column still has to read the entire row — inefficient for analytical queries that typically touch a small subset of many columns across a huge number of rows.
- **Columnar formats** (**Parquet**, **ORC**): store data column-by-column rather than row-by-row, meaning a query touching only 3 of a table's 50 columns only needs to actually read those 3 columns' data from storage — dramatically reducing the data scanned (and, for services like Athena that charge by data scanned, §11, the actual cost) for typical analytical query patterns. Columnar formats also compress significantly better than row-based formats, since similar values are stored contiguously.
- 🔑 **Key takeaway:** converting raw, row-based ingested data (CSV/JSON) into a columnar format (Parquet) as part of a cleaning/curation ETL step is one of the single highest-leverage data lake optimizations available — smaller storage footprint, dramatically faster queries, and lower cost for every downstream service in this Part that queries the data.

## 5. Lifecycle / Workflow

1. Raw data lands in the data lake's raw zone in S3, in whatever format the source system produces (often CSV/JSON).
2. A Glue Crawler runs against the raw zone, inferring schema and creating/updating the corresponding Data Catalog table(s).
3. A Glue ETL Job (a Spark-based transformation, conceptually similar to what Part 11 §4 — EMR — runs, but managed and serverless) reads the raw data, cleans/validates/deduplicates it, converts it to a columnar format (Parquet), and writes the result to the cleaned/curated zone, partitioned appropriately.
4. A second Crawler (or the same Job, using the Glue ETL library's built-in Catalog-update capability) catalogs the newly-written curated table.
5. Downstream services — Athena (Part 11 §3), Redshift Spectrum (Part 11 §5), EMR (Part 11 §4), QuickSight (Part 11 §6) — query the curated table directly via the Data Catalog, without needing to know or care about the underlying raw data's original format or location.

## 6. Configuration

| Setting                                                   | Purpose                                                                                                                                                                                                                                                                                                                                                                                     |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Crawler schedule                                          | How frequently a Crawler re-scans its source and updates the Catalog — balancing catalog freshness against unnecessary re-crawls of unchanged data.                                                                                                                                                                                                                                         |
| Crawler exclude patterns                                  | Restricting which files/paths within a source a Crawler actually scans, avoiding accidentally cataloging temporary or unrelated files.                                                                                                                                                                                                                                                      |
| Table partition projection (Athena-specific optimization) | An alternative to Crawler-discovered partitions that computes expected partition values algorithmically (e.g., every date in a range) rather than requiring a Crawler scan to discover them — reduces Crawler run frequency/cost for very large, predictably-partitioned tables. Verify current documentation for exact configuration syntax, as this is a more advanced, evolving feature. |
| Glue Job worker type/count                                | For ETL Jobs specifically, the compute capacity (analogous to EMR's cluster sizing, Part 11 §4) allocated to a transformation job.                                                                                                                                                                                                                                                          |

## 7. Commands / API (Full Documentation)

### 7.1 Creating and Running a Crawler

- **Purpose:** Register a Crawler that will scan an S3 location and populate/update the Data Catalog.
- **Syntax:**

```bash
aws glue create-crawler \
  --name raw-sales-crawler \
  --role GlueCrawlerRole \
  --database-name raw_zone_db \
  --targets '{"S3Targets": [{"Path": "s3://data-lake-bucket/raw/sales/"}]}'

aws glue start-crawler --name raw-sales-crawler
```

- **Important arguments:** `--role` is the IAM role the Crawler assumes to read the S3 source and write to the Catalog — must have both S3 read permission on the target path and Glue Catalog write permission. `--database-name` is the logical Catalog database the discovered table(s) will be written into. `--targets` specifies what to scan — can be one or more S3 paths, or a configured Connection for a database source.
- **Practical example / expected output:** After `start-crawler` completes (asynchronous — check status via `get-crawler`), a new table appears in the `raw_zone_db` Catalog database, with inferred column names/types and, if the S3 path contains partition-like folder structure (e.g., `year=2026/month=07/`), automatically-detected partitions.
- **Common errors:** insufficient IAM permissions on the target S3 path (Crawler fails silently or with an access-denied error in its run history, not a synchronous CLI error); inconsistent file formats within the same target path causing schema-inference confusion (mixing CSV and JSON files in the same crawled folder is a common cause of unexpected/incorrect inferred schemas).
- **Security impact:** the Crawler's IAM role is a real, auditable permission boundary — scope it to exactly the S3 paths and Catalog databases it needs, following the same least-privilege principle applied throughout Part 2.
- **Troubleshooting tip:** Crawler run history (visible via `get-crawler-metrics` or the console) shows exactly what tables/partitions were added, updated, or deleted on each run — the first place to check when Catalog contents don't match expectations after a Crawler run.

### 7.2 Querying the Catalog Programmatically

```bash
# List tables in a Catalog database
aws glue get-tables --database-name raw_zone_db

# Get one table's schema/location detail
aws glue get-table --database-name raw_zone_db --name sales
```

- **Production usage:** downstream services rarely call these APIs directly in normal operation — Athena, Redshift Spectrum, and EMR all resolve table definitions from the Catalog transparently as part of running a SQL query against a Catalog-registered table name. These calls are primarily useful for programmatic inspection, automation, or troubleshooting a specific table's registered definition.

## 8. Hands-On Example — Raw-to-Curated Pipeline

```text
s3://data-lake-bucket/
  raw/sales/year=2026/month=07/day=15/sales_2026-07-15.csv   (row-based, uncompressed)
  curated/sales/year=2026/month=07/day=15/part-0001.parquet  (columnar, compressed)

Glue Data Catalog:
  Database: raw_zone_db
    Table: sales  --> points at s3://data-lake-bucket/raw/sales/, format=CSV
  Database: curated_zone_db
    Table: sales  --> points at s3://data-lake-bucket/curated/sales/, format=Parquet, partitioned by year/month/day

A Glue ETL Job reads raw_zone_db.sales, validates/deduplicates rows,
writes the result as Parquet to the curated path, and a second Crawler
(or the Job's own Catalog-update step) registers curated_zone_db.sales.

Athena (Part 11 §3) can now run: SELECT * FROM curated_zone_db.sales
WHERE year=2026 AND month=07  -- scans ONLY the July partition's Parquet files,
skipping every other date and reading only the needed columns.
```

This concrete example demonstrates the full pattern this section introduces: raw data lands cheaply and immediately usable; a Crawler catalogs it without manual schema definition; an ETL step both cleans and reformats it into a query-optimized layout; a second Catalog registration makes the curated version queryable by name — and every later section in this Part builds directly on top of this same raw→curated→cataloged pattern.

## 9. Production and Enterprise Usage

- Large organizations typically run dozens to hundreds of Crawlers and Glue ETL Jobs on schedules, forming a continuously-refreshing data lake where new raw data is regularly re-cataloged and re-curated without manual intervention.
- The Glue Data Catalog is frequently the **single shared metadata layer** across an organization's entire analytics stack — the same table definitions are queried by Athena for ad hoc analysis, by Redshift Spectrum for BI reporting (Part 11 §5), and by EMR for large-scale batch processing (Part 11 §4), avoiding the common enterprise anti-pattern of each tool maintaining its own separate, potentially inconsistent schema understanding of the same underlying data.
- Multi-account organizations commonly centralize the Data Catalog in one account (frequently paired with Lake Formation, Part 11 §2, for cross-account permission management) so that multiple teams' accounts can query a shared set of curated datasets without duplicating data or metadata per account.

## 10. Security Considerations

- IAM policies control who can create/modify Crawlers, Jobs, and Catalog tables/databases — standard least-privilege scoping applies (Part 2 §1-2).
- The Data Catalog itself contains only metadata (schema, location) — it does not contain the actual data, meaning access to _view a table's schema_ in the Catalog is a distinct permission from access to _read the underlying data_ in S3; both need to independently permit access for a query to actually succeed (the same "multiple layers must align" pattern seen throughout this course, e.g., Part 5 §3's S3/KMS interaction).
- For fine-grained, column-level and row-level access control on top of Catalog tables (beyond what IAM alone provides at the table/database level), see **AWS Lake Formation** (Part 11 §2) — the natural next section, purpose-built for exactly this deeper access-control requirement.

## 11. Performance Considerations

- **Partitioning** is the single most impactful performance lever for query engines reading Catalog tables — a well-partitioned table (e.g., by date, matching common query filter patterns) lets a query engine skip scanning irrelevant partitions entirely, often reducing both query latency and cost (for scan-based-pricing services like Athena) by an order of magnitude for selective queries.
- **File format** (§4.4) is the second major lever — columnar Parquet/ORC formats dramatically reduce data scanned for typical analytical queries compared to row-based CSV/JSON, independent of partitioning.
- **File size** matters too: a data lake with an extremely large number of very small files (a common byproduct of frequent, small streaming writes) creates real overhead for query engines, which must open and process each file individually — periodic **compaction** (an ETL job that merges many small files into fewer, larger ones) is a standard data lake maintenance practice specifically to address this.

## 12. Monitoring

- Crawler run history and Glue Job run history (both via CloudWatch Logs, Part 8 §2, and the Glue console) show success/failure status, rows processed, and duration for each run — the primary operational signal for whether the data lake's cataloging and curation pipeline is healthy.
- CloudWatch Alarms (Part 8 §3) on Crawler/Job failure is a standard practice, since a silently-failing nightly ETL job means downstream curated tables silently stop updating, which can go unnoticed for a surprising length of time without explicit alerting.

## 13. Troubleshooting

| Symptom                                                                     | Cause                                                                                                                                | Fix                                                                                                                              |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| Query against a Catalog table returns no rows, or errors                    | Catalog table's registered S3 location doesn't match where data is actually written, or the Crawler hasn't run since new data landed | Verify the table's registered location (`get-table`) matches actual data location; re-run the Crawler                            |
| Crawler infers an unexpected/incorrect schema                               | Mixed file formats or inconsistent data types within the crawled path                                                                | Separate differently-formatted data into distinct S3 paths/Crawlers; review and, if needed, manually correct the inferred schema |
| Queries against a large table are slow and scan far more data than expected | Table isn't partitioned, or the query's filter doesn't align with the partitioning scheme                                            | Add appropriate partitioning matching common query filter patterns; verify the query actually filters on the partition column    |
| Crawler run fails                                                           | IAM role lacks S3 read or Catalog write permission                                                                                   | Review and correct the Crawler's IAM role permissions                                                                            |

## 14. Best Practices

- Convert raw, row-based ingested data to a columnar format (Parquet) as part of a curation ETL step — the highest-leverage single optimization available for this entire Part's downstream query performance and cost.
- Partition curated tables by columns that match common query filter patterns (commonly date-based).
- Schedule Crawlers to run after new data lands, rather than continuously, to avoid unnecessary re-crawl overhead — trigger-based (e.g., Crawler run initiated by an S3 event via EventBridge, Part 7 §4) or schedule-based approaches are both common.
- Periodically compact small files in high-write-frequency areas of the data lake.
- Review Crawler-inferred schemas for new or unusually-structured datasets rather than assuming inference is always correct.

## 15. Anti-Patterns and Common Mistakes

- ❌ Treating the data lake as a place to dump data with no zone structure or curation discipline — without a raw→cleaned→curated progression, a data lake tends to degrade into what's commonly (and accurately) called a "data swamp": technically queryable, but poorly understood, inconsistent, and untrusted.
- ❌ Querying raw CSV/JSON data directly and repeatedly in production BI/reporting workloads instead of curating it into partitioned Parquet first — every such query pays the full cost of row-based, unpartitioned scanning that a one-time curation step would have avoided for every subsequent query.
- ❌ Never re-running Crawlers after a data source's schema changes, leading to a stale Catalog definition that no longer matches the actual underlying data.
- ❌ Allowing raw ingestion to accumulate as many small files without periodic compaction, degrading query performance for every engine reading that data over time.

## 16. Interview Questions with Model Answers

**🎯 Junior:** _"What's the difference between a data lake and a traditional relational database, at a high level?"_
**Model answer:** A relational database (like RDS) requires you to define a schema before writing data, and it tightly couples storage and query engine into one system. A data lake stores data in its raw, native format — you don't need to know or define the full schema upfront — and it deliberately separates storage (S3) from the schema/metadata layer (the Glue Data Catalog) from the actual query engine (Athena, Redshift Spectrum, EMR, depending on the workload), giving much more flexibility for large volumes of varied, evolving, or not-yet-fully-understood data, at the cost of the strong consistency and transactional guarantees a relational database provides.

**🎯 Intermediate:** _"A team's Athena queries against their data lake are slow and expensive even though the underlying dataset isn't that large. What would you check first?"_
**Model answer:** The two highest-impact things to check first are partitioning and file format. If the table isn't partitioned (or the query's filter doesn't align with how it is partitioned), every query is scanning the entire dataset regardless of how selective the actual filter is — adding appropriate partitioning, typically by date, is usually the single biggest fix. Second, if the underlying data is still in raw row-based format (CSV or JSON) rather than a columnar format like Parquet, every query is reading full rows even when it only needs a few columns, and missing out on Parquet's much better compression. Converting the data to partitioned Parquet as a one-time (or ongoing) curation ETL step typically produces a dramatic improvement in both query speed and — since Athena charges by data scanned — cost, without changing the query itself at all.

**🎯 Senior:** _"Design the raw-to-curated data pipeline for an organization ingesting clickstream events via Kinesis Data Firehose, needing the data queryable in Athena within about 15 minutes of generation, with a 7-year retention requirement for compliance."_
**Model answer:** Firehose delivers the clickstream events into a raw zone in S3, ideally already in a reasonably efficient format and partitioned by Firehose's built-in time-based prefixing (Part 7 §7) — this satisfies the low-latency requirement, since Firehose delivers on its own buffer interval, typically well under 15 minutes. Layer a Glue Crawler on the raw zone, scheduled frequently enough (e.g., every 10-15 minutes, or triggered by an S3-event via EventBridge on new file arrival) to keep the raw table's Catalog definition current as new partitions appear. For the actual "queryable and fast" requirement, don't rely on querying raw JSON directly for anything beyond ad hoc raw investigation — run a Glue ETL Job on a similarly short schedule that converts the recent raw data into partitioned Parquet in a curated zone, and have the organization's actual BI/reporting queries target the curated table, not the raw one, since raw JSON at clickstream volume would be prohibitively slow and expensive to query repeatedly. For the 7-year retention requirement, apply an S3 Lifecycle policy (Part 5 §2) on the raw zone specifically, transitioning older raw data to a lower-cost storage class (or even Glacier, Part 5 §2) after some active-query window has passed, while the curated zone — smaller, compressed, and the actual query target — can retain a more query-friendly storage class for longer, balancing the 7-year compliance retention requirement against ongoing storage cost.

**🎯 Architect:** _"A large enterprise has 40 teams, each producing data they want to share as part of a company-wide data lake, but leadership is worried about both data quality degrading into an unmanaged mess and inconsistent security/access control across teams. Design the governance approach, referencing specific AWS capabilities."_
**Model answer:** Establish an organization-wide zone convention (raw/cleaned/curated, or an equivalent standard) that every team's data follows, with the Glue Data Catalog centralized — likely in a dedicated, shared "data lake account" within the organization's AWS Organizations structure (Part 2 §5) — rather than each of the 40 teams maintaining an entirely separate, disconnected catalog; this directly addresses the "unmanaged mess" concern by giving the organization one place to see what data exists company-wide, with a consistent structural convention. For the security/access-control concern specifically, layer AWS Lake Formation (Part 11 §2, the natural next section) on top of this centralized Catalog — Lake Formation provides fine-grained, column-level and row-level permissions on Catalog tables and supports secure cross-account data sharing, which is exactly the capability needed for 40 different teams' accounts to each access an appropriately-scoped slice of the shared catalog without either over-provisioning broad access or having each team re-implement their own access control scheme independently. Require each team's data to pass through Crawler-based cataloging and, for data intended for company-wide curated use, a minimum data-quality/curation bar (validated, deduplicated, in Parquet, appropriately partitioned) before being registered in the shared "curated" zone/database — data that hasn't met that bar can still exist in a team-specific raw zone, but isn't promoted to the shared, company-wide curated layer other teams are expected to trust and query, directly preventing the specific "quality degrading into a mess" failure mode leadership is worried about.

## 17. Common Misconceptions

- "A data lake is just an S3 bucket." Incomplete — S3 provides the storage, but without a metadata/schema layer like the Glue Data Catalog on top, a bucket full of files isn't queryable as structured tables by SQL-based tools; the Catalog is what actually makes it a "lake" in the useful sense, not just a pile of objects.
- "Creating a Glue Data Catalog table copies or moves the underlying data." False — a Catalog table is pure metadata (schema and a pointer to an S3 location); the actual data never moves or duplicates as part of Catalog registration.
- "Crawlers always correctly infer the exact intended schema." False — Crawler inference is a genuinely useful heuristic, not a guarantee; reviewing inferred schemas, especially for new or irregularly-structured data, remains a real practice, not a formality.

## 18. Key Takeaways

🔑 A data lake deliberately separates storage (S3), schema/metadata (the Glue Data Catalog), and compute (Athena/Redshift Spectrum/EMR, chosen per-workload) — a fundamentally different architecture from a bundled relational database engine.
🔑 The Glue Data Catalog is metadata only — creating or updating a table definition never moves or copies the underlying data; it's a pointer plus a schema.
🔑 Glue Crawlers automate schema discovery and Catalog population/updates, removing the impractical burden of manually defining every table's schema by hand, though inferred schemas still warrant review.
🔑 Partitioning and columnar file format (Parquet/ORC) are the two highest-leverage performance and cost levers for every downstream service querying data lake tables in this Part — both are addressed once, during curation, and benefit every subsequent query.
🔑 A data lake without zone structure and curation discipline tends toward becoming an unmanaged, untrusted "data swamp" — the raw→cleaned→curated pattern exists specifically to prevent that outcome.

## 19. Related Concepts

- **Amazon S3** (Part 5 §1-4) — the data lake's physical storage layer.
- **AWS Lake Formation** (Part 11 §2, next section) — fine-grained, column/row-level permissions and cross-account sharing built on top of the Glue Data Catalog covered here.
- **Amazon Athena** (Part 11 §3) — the primary serverless SQL query engine reading Glue Catalog tables.
- **Amazon EMR** (Part 11 §4) — large-scale Spark/Hadoop processing, another major consumer (and producer) of Glue Catalog tables.
- **Redshift Spectrum** (Part 11 §5) — querying Glue Catalog tables directly from Redshift without loading data into the warehouse.
- **Kinesis Data Firehose** (Part 7 §7) — a common raw-zone ingestion path for streaming data feeding this Part's data lake pattern.
