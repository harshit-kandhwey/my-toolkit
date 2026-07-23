# Part 11, Section 3: Amazon Athena — Serverless SQL Query

## 1. Definition

**Plain language:** Sections 1 and 2 built a governed, cataloged data lake in S3 — but a catalog and governed access don't yet let anyone actually _ask questions_ of the data in familiar SQL. Amazon Athena is the service that lets you run standard SQL queries directly against data sitting in S3, using the Glue Data Catalog's table definitions, without ever loading the data into a database first.

**Precise definition:** Amazon Athena is a serverless, interactive query service that uses standard SQL (based on Presto/Trino under the hood) to query data directly in Amazon S3, resolving table schemas from the Glue Data Catalog, with no infrastructure to provision or manage, priced (in its default mode) by the amount of data scanned per query.

## 2. Why It Exists / Problem It Solves

- Before Athena, querying data sitting in S3 typically required either loading it into a traditional database first (an ETL step introducing latency and duplicated storage) or standing up and managing a query engine cluster (an EMR cluster, Part 11 §4) even for a single ad hoc question — meaningful operational overhead for what might be a one-off analytical query.
- Athena removes both requirements: point it at a Glue Catalog table (§1), write standard SQL, get results — no cluster to provision, size, or manage, and the data never leaves S3 or gets duplicated into a separate storage system.
- 🔑 **Key takeaway:** Athena is specifically optimized for the "ask a SQL question against data already sitting in S3, without standing up infrastructure" use case — this is precisely why partitioning and columnar formats (Part 11 §1 §11) matter so much for it specifically: since it's priced by data scanned, both directly determine the actual cost and speed of every query.

## 3. Prerequisites and Dependencies

- **Glue Data Catalog** (Part 11 §1): Athena queries reference Catalog databases/tables by name — without cataloged tables, Athena has no schema to resolve a SQL query against.
- **S3** (Part 5 §1): the actual data Athena scans.
- **Lake Formation** (Part 11 §2, optional but common): if a queried table is Lake Formation-governed, Athena transparently enforces those column/row-level restrictions as part of query execution.

## 4. Internal Working / Architecture & Components

### 4.1 Query Execution Model

- Athena is built on **Presto/Trino**, a distributed SQL query engine — when a query runs, Athena provisions the necessary compute transparently (invisible to the user), executes the query directly against the S3 data referenced by the Catalog table's location, and tears the compute back down after the query completes; there's no persistent cluster to manage or pay for between queries.
- Query results are written to a specified S3 location (the "query results location") as a side effect of every query — Athena itself doesn't store results anywhere else; this results bucket, and its own storage cost/lifecycle, is a real, sometimes overlooked operational detail (§11).

### 4.2 Pricing Model

- **On-demand (default):** priced per query, based on the amount of data actually scanned from S3 — this is precisely why partitioning and columnar formats (Part 11 §1 §11) directly and proportionally reduce cost, not just latency, for Athena specifically.
- **Athena provisioned capacity (Capacity Reservations):** an alternative pricing model reserving dedicated query-processing capacity for a predictable hourly cost, more cost-effective for organizations running a very high, sustained volume of queries where per-query on-demand pricing would exceed a reserved-capacity cost — verify current documentation for exact pricing thresholds, as this is a newer, evolving capability.

### 4.3 Workgroups

- A **Workgroup** is an Athena construct for separating and controlling groups of queries — different teams or use cases can be assigned different Workgroups, each with its own query results location, per-query or per-workgroup data-scan limits (a direct cost-control mechanism), and CloudWatch metrics isolation.
- Practical fit: separating an ad hoc analyst Workgroup (with a conservative per-query data-scan limit, preventing an accidentally unbounded query from generating a large surprise cost) from a scheduled production-reporting Workgroup (with different limits appropriate to known, expected query patterns).

## 5. Lifecycle / Workflow

1. A table exists in the Glue Data Catalog (Part 11 §1), pointing at S3 data.
2. A user or application submits a SQL query via the Athena console, CLI, JDBC/ODBC driver, or API, referencing the Catalog table by name.
3. Athena resolves the table's schema and location from the Catalog, transparently provisions the compute needed, and executes the query against the underlying S3 data — applying any Lake Formation column/row restrictions (Part 11 §2) if the table is governed.
4. Results are written to the configured query results S3 location and returned to the requester.
5. Compute is torn down; nothing persists except the results in S3 and Athena's own query-execution metadata/history.

## 6. Configuration

| Setting                                | Purpose                                                                                                                                                                                                                                |
| -------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Query results location (S3 path)       | Where every query's output is written — a required configuration, either at the Workgroup level or per-query.                                                                                                                          |
| Workgroup data-scan limits             | Per-query and/or per-workgroup caps on data scanned, a direct cost-control guardrail.                                                                                                                                                  |
| Encryption of query results            | SSE-S3, SSE-KMS, or client-side encryption (Part 5 §3 patterns) applied to the results written to S3 — configured per Workgroup.                                                                                                       |
| Federated Query data source connectors | Optional connectors letting Athena query non-S3 sources (RDS, DynamoDB, and others) through the same SQL interface — extends Athena's reach beyond pure data lake queries; verify current documentation for supported connector types. |

## 7. Commands (Full Documentation)

### 7.1 Running a Query

- **Purpose:** Execute a SQL query against a Catalog table and retrieve results.
- **Syntax:**

```bash
aws athena start-query-execution \
  --query-string "SELECT region, SUM(amount) FROM curated_zone_db.sales WHERE year=2026 AND month=07 GROUP BY region" \
  --query-execution-context Database=curated_zone_db \
  --result-configuration OutputLocation=s3://athena-results-bucket/queries/
```

- **Important arguments:** `--query-string` is standard SQL, referencing Catalog tables by database/table name. `--result-configuration` specifies where output lands — required unless a Workgroup default is configured. `start-query-execution` is asynchronous — it returns a `QueryExecutionId` immediately; use `get-query-execution` to poll status and `get-query-results` to retrieve the actual result rows once `Status.State` is `SUCCEEDED`.
- **Practical example / expected output:** the query above, run against a properly partitioned (`year`/`month`) and Parquet-formatted curated table (Part 11 §1), scans only the July 2026 partition's data — dramatically less than scanning the entire table's history — and returns one row per region with summed sales.
- **Common errors:** referencing a table/database name that doesn't exist in the Catalog (typo, or table not yet crawled); omitting a results location with no Workgroup default configured; a query that doesn't filter on the partition column, unintentionally scanning far more data (and costing far more) than the query's actual intent required.
- **Security impact:** Athena queries run under the calling principal's own IAM permissions (and any Lake Formation restrictions, Part 11 §2) — Athena itself doesn't grant additional access beyond what the principal already has to the underlying Catalog/S3/Lake Formation-governed data.
- **Performance impact:** query cost and latency are directly proportional to data scanned — see §11.
- **Troubleshooting tip:** `get-query-execution` returns not just success/failure but the exact data-scanned amount and execution time for a completed query — the first place to check when a query is slower or more expensive than expected.

### 7.2 CREATE TABLE AS SELECT (CTAS) — Curating Data in SQL

```sql
CREATE TABLE curated_zone_db.sales_parquet
WITH (format = 'PARQUET', partitioned_by = ARRAY['year', 'month'],
      external_location = 's3://data-lake-bucket/curated/sales/')
AS SELECT * FROM raw_zone_db.sales;
```

- **Purpose:** a CTAS query lets you perform the raw-to-curated transformation described in Part 11 §1 (converting row-based data to partitioned Parquet) directly in SQL via Athena, as an alternative to writing a Glue ETL Job (Part 11 §1) for simpler transformation needs.
- **Production usage:** a common, lightweight pattern for straightforward format/partition conversions where a full Spark-based Glue Job would be unnecessary overhead — reserve actual Glue ETL Jobs (Part 11 §1, Part 11 §4) for more complex transformation logic (multi-step cleaning, joins across many sources, custom business logic) that's awkward or impractical to express as a single SQL statement.

## 8. Hands-On Example

```text
Query: SELECT region, SUM(amount) FROM curated_zone_db.sales
       WHERE year=2026 AND month=07 GROUP BY region

Execution:
  1. Athena resolves curated_zone_db.sales from the Glue Catalog:
     format=Parquet, partitioned by year/month, location=s3://.../curated/sales/
  2. Partition pruning: only s3://.../curated/sales/year=2026/month=07/ is scanned
     (every other year/month partition is skipped entirely)
  3. Columnar read: only 'region' and 'amount' columns are read from the
     Parquet files in that partition (every other column is skipped)
  4. Result written to s3://athena-results-bucket/queries/<query-id>.csv
  5. Compute torn down; next query starts fresh
```

This demonstrates exactly why Part 11 §1's partitioning and columnar-format best practices matter so directly for Athena: partition pruning and columnar reads together mean this query scans a small fraction of the table's total data, directly reducing both latency and — since Athena is priced by data scanned — cost, without any change to the query itself.

## 9. Production and Enterprise Usage

- Athena is commonly the default first choice for ad hoc analytical querying against a data lake, given its zero-infrastructure operational model — analysts and data scientists can query immediately against any cataloged table without waiting for infrastructure provisioning.
- Scheduled production reporting queries (feeding a BI dashboard, Part 11 §6) are commonly run via Athena on a schedule (via a Lambda function or Step Functions workflow, Part 7, triggering `start-query-execution` periodically) rather than requiring a persistent, always-on query engine for what's ultimately periodic, not continuous, query load.
- Workgroups with data-scan limits are a standard enterprise cost-control practice, particularly for broadly-accessible ad hoc analyst Workgroups where an accidentally unbounded query (missing a partition filter, or an unintended cross join) could otherwise generate significant, unexpected cost.

## 10. Security Considerations

- Athena enforces IAM permissions and, where applicable, Lake Formation column/row restrictions (Part 11 §2) — it introduces no separate access-control model of its own beyond what governs the underlying Catalog/S3 resources.
- Query results written to S3 inherit whatever encryption/access-control configuration is applied to the results bucket (Part 5 §3 patterns) — the results bucket itself is a genuine, sometimes overlooked data-exposure surface, since query output can contain the same sensitive data as the source, and warrants the same access-control rigor as the source data itself.

## 11. Performance Considerations

- Cost and latency are both directly driven by **data scanned**, which is why partitioning and columnar formats (Part 11 §1 §11) matter so directly for Athena specifically — a query against a well-partitioned Parquet table can scan orders of magnitude less data than the equivalent query against unpartitioned CSV, at proportionally lower cost and latency.
- A very large number of small files (Part 11 §1 §11's "compaction" discussion) also directly hurts Athena performance, since Athena must open and process each file individually as part of query execution.
- Query result caching: Athena automatically reuses results for an identical, recently-run query against unchanged underlying data, avoiding a redundant re-scan and re-charge for a repeated query — verify current documentation for the exact reuse window and conditions.

## 12. Monitoring

- CloudWatch Metrics (Part 8 §1) for Athena include query execution time and data scanned per query/workgroup — the primary signals for both performance and cost tracking.
- `get-query-execution`'s returned statistics (data scanned, execution time, status) are the per-query-level detail underlying those aggregate CloudWatch metrics, useful for investigating one specific slow or expensive query.

## 13. Troubleshooting

| Symptom                                                                         | Cause                                                                                  | Fix                                                                                                                                     |
| ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| Query is much slower/more expensive than expected                               | Missing partition filter, or unpartitioned/non-columnar source table                   | Add an appropriate `WHERE` clause on the partition column; curate the source into partitioned Parquet (Part 11 §1)                      |
| `TABLE_NOT_FOUND` error                                                         | Table doesn't exist in the referenced Catalog database, or a typo in the name          | Verify via `aws glue get-tables`; confirm the Crawler (Part 11 §1) has run and registered the expected table                            |
| Query fails with an access-denied-style error despite a seemingly correct query | Underlying IAM or Lake Formation permission missing on the table/columns being queried | Verify both the IAM policy and, if applicable, the Lake Formation grant (Part 11 §2) permit the specific columns/rows the query touches |
| Results location error                                                          | No results S3 location configured at either the query or Workgroup level               | Specify `--result-configuration`, or configure a Workgroup default                                                                      |

## 14. Best Practices

- Always query partitioned, columnar (Parquet/ORC) curated tables for any repeated or production query pattern — reserve querying raw, unpartitioned data for genuine one-off, exploratory investigation.
- Use Workgroups with data-scan limits to bound accidental cost exposure, especially for broadly-accessible ad hoc query access.
- Use CTAS for straightforward SQL-expressible curation transformations, reserving full Glue ETL Jobs (Part 11 §1, §4) for more complex transformation logic.
- Secure the query results S3 location with the same rigor as the source data, since results can contain equally sensitive content.

## 15. Anti-Patterns and Common Mistakes

- ❌ Repeatedly running production reporting queries against raw, unpartitioned CSV/JSON data instead of curating it once into partitioned Parquet — every such query pays the avoidable full-scan cost that a one-time curation step would have eliminated for every subsequent query.
- ❌ Granting unrestricted, unlimited Athena access to a broad analyst population with no Workgroup data-scan limits — a single mistakenly unbounded query (e.g., a missing `WHERE` clause on a huge table) can generate significant unexpected cost with no guardrail in place.
- ❌ Treating the query results S3 bucket as an afterthought with weaker access control than the source data it's derived from.

## 16. Interview Questions with Model Answers

**🎯 Junior:** _"What makes Athena different from just running a query on a traditional database?"_
**Model answer:** Athena queries data directly where it already sits in S3, using the Glue Data Catalog's table definitions, without needing to load or copy the data into a separate database first. It's also serverless — there's no cluster or instance to provision or manage; Athena transparently handles the compute needed for each query and tears it down afterward. You're charged based on how much data the query actually scans, rather than paying for always-on database infrastructure.

**🎯 Intermediate:** _"Why does converting data to Parquet and partitioning it matter so specifically for Athena's cost, not just its speed?"_
**Model answer:** Athena's default pricing is based directly on the amount of data scanned per query, not on time or a fixed instance cost. Partitioning lets Athena skip entire sections of data that don't match a query's filter — if a query filters on `year=2026 AND month=07`, a well-partitioned table means Athena only reads that specific partition's files, ignoring every other date entirely. Parquet's columnar format means that even within the data that is scanned, Athena only reads the specific columns the query actually selects, rather than every column in every row. Both effects directly reduce the bytes scanned, which directly reduces the dollar cost of the query — it's not just a speed optimization, it's a cost optimization with a very direct, measurable relationship to the pricing model itself.

**🎯 Senior:** _"An analytics team's shared Athena Workgroup generated an unexpectedly large bill last month. How would you investigate and prevent recurrence?"_
**Model answer:** Start with CloudWatch metrics for that Workgroup, specifically data-scanned-per-query over the billing period, to identify whether the cost came from one or a few outlier queries (a missing partition filter, an accidental full-table scan) or from generally high query volume across many smaller queries. For an outlier-query root cause, `get-query-execution` on the specific expensive query IDs would show exactly what was scanned and how the query was structured, likely revealing an unpartitioned source table or a missing WHERE clause. To prevent recurrence, I'd configure a per-query data-scan limit on that Workgroup (a genuine, enforced guardrail, not just a monitoring signal) sized to catch genuinely anomalous queries without blocking legitimate expected usage, and separately, if the root cause traces back to querying an unpartitioned or non-columnar source table repeatedly, prioritize curating that specific dataset into partitioned Parquet (Part 11 §1) so future queries against it are inherently cheaper regardless of how carefully each individual query is written.

**🎯 Architect:** _"Design a cost-controlled, multi-team Athena setup for an organization with 15 analytics teams sharing one data lake, where finance needs predictable monthly cost and individual teams shouldn't be able to accidentally impact each other's budgets."_
**Model answer:** Create a separate Athena Workgroup per team (or per logical cost-center grouping, if 15 individual Workgroups is administratively excessive), each with its own dedicated query-results S3 location and its own per-query and/or per-workgroup data-scan limit sized to that team's expected legitimate usage — this directly prevents one team's misbehaving query from consuming budget or hitting limits that would affect a different team's Workgroup, since Workgroup-level limits are isolated from each other. For finance's predictable-cost requirement specifically, evaluate Athena provisioned capacity (Capacity Reservations, §4.2) if the organization's aggregate query volume across all 15 teams is high and sustained enough that a reserved, predictable hourly cost would be more cost-effective and more budget-predictable than aggregate on-demand per-query billing across every team — this converts a variable, harder-to-forecast on-demand cost into a fixed, plannable one, at the potential trade-off of paying for reserved capacity even during lower-usage periods. Tag each Workgroup (and the underlying Catalog resources each team primarily queries, potentially via LF-Tags, Part 11 §2) with a cost-center identifier, enabling AWS Cost Explorer / Cost and Usage Report-based chargeback reporting per team even under a shared reserved-capacity billing model, giving finance both predictable aggregate cost and per-team cost visibility simultaneously.

## 17. Common Misconceptions

- "Athena stores or hosts the data being queried." False — Athena is purely a query engine; the data lives entirely in S3, both before and after any Athena query, and Athena only writes query _results_ to S3 as output.
- "Athena is always the cheapest or fastest option for any data lake query." False as a blanket statement — for very high, sustained query volume, provisioned capacity or a persistent EMR cluster (Part 11 §4) can be more cost-effective than per-query on-demand Athena pricing; Athena's strength is specifically its zero-infrastructure, pay-per-query model for variable or ad hoc workloads.
- "Partitioning and Parquet are 'nice to have' optimizations for Athena." Understated — given Athena's data-scanned-based pricing, they have a direct, often order-of-magnitude effect on actual query cost, not just a marginal performance tweak.

## 18. Key Takeaways

🔑 Athena is a serverless SQL query engine reading Glue Catalog tables directly against S3 data, with no infrastructure to provision and pricing based on data scanned.
🔑 Partitioning and columnar (Parquet/ORC) formats have a direct, often dramatic effect on both Athena query cost and latency, since both are driven by data actually scanned.
🔑 Workgroups provide query isolation, separate results locations, and enforceable data-scan limits — a genuine cost-control guardrail, not just an organizational convenience.
🔑 CTAS queries let straightforward curation transformations (format/partition conversion) happen directly in SQL, reserving full Glue ETL Jobs for more complex transformation needs.
🔑 Athena enforces exactly the same IAM and Lake Formation restrictions as the underlying Catalog/S3 resources — it introduces no separate access-control model of its own.

## 19. Related Concepts

- **Glue Data Catalog** (Part 11 §1) — the schema/metadata source every Athena query resolves against.
- **AWS Lake Formation** (Part 11 §2) — column/row-level restrictions Athena transparently enforces for governed tables.
- **Amazon EMR** (Part 11 §4, next section) — the alternative, more heavyweight compute option for large-scale or complex processing beyond what a single SQL query comfortably expresses.
- **Redshift Spectrum** (Part 11 §5) — a related S3-querying capability accessed from within Redshift rather than standalone, useful for comparison of when to use which.
- **Amazon QuickSight** (Part 11 §6) — commonly connects to Athena as a data source for BI dashboards built on top of data lake queries.
