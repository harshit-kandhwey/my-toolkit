# Section 49 (Part 6): Data Pipeline Architecture Patterns — Part 6 Wrap-Up & Interview Drill

## 1. Definition

**Plain language:** Sections 44–48 each covered one piece of GCP's data and analytics stack — a warehouse, a set of processing engines, an orchestrator, a governance layer, and a pair of BI tools. This closing section is about how those pieces actually get assembled into one coherent, production-grade pipeline: what "lakehouse" means concretely on GCP, when to transform data before loading it (ETL) versus after (ELT), and how the widely used **medallion architecture** (bronze/silver/gold) maps onto the specific GCP services already covered.

**Precise:** This section synthesizes Part 6's individual services into end-to-end architectural patterns — the **BigLake-based lakehouse pattern** unifying BigQuery, Cloud Storage, and Dataplex under one governed, engine-agnostic table layer; the **ELT vs. ETL** decision framework as it applies to Dataflow, Dataproc, and BigQuery SQL; and the **medallion (bronze/silver/gold) architecture**, commonly implemented on GCP using Dataflow/Dataproc for transformation and Cloud Composer for orchestration — closing with a tiered interview drill spanning Sections 44–48.

## 2. Why It Exists / Problem It Solves

None of Sections 44–48 individually answers "how do I actually build a production data platform" — each is one capability. Teams that pick services one at a time, without an overall pattern in mind, commonly end up with: BigQuery tables and GCS files that drift out of sync with each other, ETL logic duplicated across Dataflow jobs and BigQuery scheduled queries with no consistent rule for which does what, and a "lake" that is really just an ungoverned pile of files with no meaningful maturity tiers. The lakehouse pattern, the ELT/ETL framework, and the medallion architecture each exist to give teams a proven, repeatable shape to build toward, rather than re-deriving pipeline architecture from scratch on every project.

## 3. The Lakehouse Pattern on GCP — BigLake

### 3.1 The Problem BigLake Solves

Historically, "data lake" (cheap, flexible, engine-agnostic files in object storage) and "data warehouse" (fast, governed, SQL-optimized structured storage) were separate architectural choices with a real tradeoff: BigQuery-native tables are fast and fully governed by BigQuery's own access controls, but reading them from Dataproc/Spark or other engines is awkward; GCS files are cheap and open to any engine, but lack BigQuery-grade governance and performance without extra tooling.

### 3.2 How BigLake Ties BigQuery, GCS, and Dataplex Together

**BigLake** is GCP's answer: it lets you define **BigLake tables** over data still physically sitting in Cloud Storage (in open formats like Parquet, ORC, or Iceberg), while applying BigQuery's fine-grained row/column-level security and performance optimizations to that data as if it were a native BigQuery table — and critically, that same governed access applies whether the table is queried from BigQuery SQL, Dataproc/Spark, or other supported engines, rather than each engine needing its own separate access-control setup. Dataplex (Section 47) is the governance and cataloging layer that sits above this: lakes/zones/assets register and tag both native BigQuery datasets and BigLake-backed GCS data uniformly, so discovery, tagging, quality rules, and lineage apply consistently regardless of where a given table's bytes physically live.

```
                     Dataplex (Section 47)
        Unified catalog, tags, quality, lineage — across BOTH
   ┌────────────────────────────┬────────────────────────────────┐
   │                            │                                │
   ▼                            ▼                                ▼
BigQuery native tables    BigLake tables                   Dataproc/Spark
(fastest, BQ-managed      (governed BQ-grade access        reading the SAME
 storage)                 over GCS files in open           BigLake table with
                          formats — Parquet/Iceberg)       the SAME permissions
                                    │
                                    ▼
                          Cloud Storage (GCS)
                     (data physically lives here,
                      one copy, multi-engine access)
```

> ⚠️ **Interview-relevant nuance:** BigLake is not a new storage system — it is an access/governance layer over existing GCS data, conceptually similar to how Dataplex (Section 47) is a governance layer, not a storage system. The distinction matters: BigLake specifically solves _cross-engine governed access_ to the same physical data, whereas Dataplex solves _discovery, cataloging, quality, and lineage_ across both BigQuery-native and BigLake-backed data. They are complementary layers, not the same thing.

## 4. ELT vs. ETL Trends on GCP

- **ETL (Extract, Transform, Load):** Data is transformed _before_ it lands in its final destination — typically using Dataflow (Section 45) for streaming/batch transformation or Dataproc (Section 45) for Spark-based processing — with only cleaned, modeled data actually loaded into BigQuery. This suits complex transformations (custom code, ML feature engineering, joins against non-BigQuery sources) or cases where raw data should never be exposed to end consumers at all.
- **ELT (Extract, Load, Transform):** Raw data is loaded into BigQuery first (often with minimal processing), and transformation happens _afterward_, directly in BigQuery using SQL (scheduled queries, `dbt`-style modeling, or materialized views). This has become the dominant modern pattern specifically because BigQuery's serverless, highly scalable SQL engine (Section 44) makes SQL-based transformation fast and cheap enough that a separate processing cluster often isn't needed for transformations that are fundamentally expressible in SQL.
- **The practical decision rule:** if the transformation is SQL-expressible (joins, aggregations, filtering, window functions) and the data is already loaded or cheaply loadable into BigQuery, ELT via SQL is usually simpler to build and maintain than a dedicated Dataflow/Dataproc job. Reach for ETL (Dataflow/Dataproc) specifically when transformation logic needs custom code, non-SQL processing (streaming windowing, complex ML feature pipelines), or must complete _before_ data is allowed to land in a governed, queryable location at all.

## 5. Medallion Architecture on GCP

The **medallion architecture** organizes data into three progressively refined tiers — a pattern that maps directly onto Dataplex's raw/curated zone concept (Section 47.3.1), extended into three explicit tiers:

- **Bronze (raw):** Data landed as-is from source systems — untransformed, often schema-on-read, typically stored in GCS and/or loaded as-is into BigQuery. Preserves the original data exactly, so any downstream bug in transformation logic can always be corrected by reprocessing from bronze rather than needing to re-extract from the source system again.
- **Silver (cleaned/conformed):** Data with basic quality rules applied — deduplicated, type-corrected, joined with reference data, conforming to a consistent schema — typically produced via a Dataflow or Dataproc job (for complex logic) or a BigQuery scheduled query/ELT step (for SQL-expressible cleaning), with a Dataplex data quality rule (Section 47.3.3) commonly gating promotion from bronze to silver.
- **Gold (business-level, aggregated):** Data modeled specifically for consumption — pre-aggregated tables, star-schema-style models, or metrics tables — feeding BI tools directly (Looker/Looker Studio, Section 48) or serving as curated feature tables for ML.

```
  Source systems
       │
       ▼
  BRONZE (raw, as-landed) ── GCS / BigQuery raw tables
       │  Dataflow / Dataproc / BQ ELT job
       │  (cleaning, dedup, schema conformance)
       │  ── gated by Dataplex data quality rules (§47) ──
       ▼
  SILVER (cleaned, conformed)
       │  Dataflow / Dataproc / BQ SQL
       │  (aggregation, business modeling)
       ▼
  GOLD (business-level, aggregated) ── BigLake / BigQuery
       │
       ▼
  Looker / Looker Studio (§48) dashboards, ML feature tables

  Cloud Composer (§46) orchestrates every arrow above as a scheduled,
  retry-aware, dependency-tracked DAG — not run as disconnected ad hoc jobs.
```

Cloud Composer (Section 46) is the orchestration layer tying bronze→silver→gold promotion together as an explicit DAG — each tier's transformation is a task with defined dependencies, retries, and failure alerting, rather than a set of independently scheduled cron jobs with no visibility into whether an upstream tier actually succeeded before a downstream tier ran.

## 6. Part 6 Recap — What Was Covered

| §   | Section                             | Core Idea                                                                                                                                                                                     |
| --- | ----------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 44  | BigQuery Deep Dive                  | Serverless, SQL-first data warehouse; separates storage and compute; the default destination for both raw and modeled data on GCP.                                                            |
| 45  | Dataflow, Dataproc, Pub/Sub         | Dataflow (managed Apache Beam, unified batch/streaming) and Dataproc (managed Spark/Hadoop) for processing beyond SQL's reach; Pub/Sub as the messaging backbone feeding streaming pipelines. |
| 46  | Cloud Composer                      | Managed Apache Airflow; DAG-based orchestration tying individually capable services together into one coordinated, retry-aware, monitored pipeline.                                           |
| 47  | Dataplex                            | Unified governance layer — discovery, cataloging, data quality, lineage — across BigQuery and GCS data in place, without data movement.                                                       |
| 48  | Looker & Looker Studio              | Looker Studio (free, self-service, no shared semantic layer) vs. Looker (LookML-governed enterprise BI) as the "last mile" from curated data to business consumption.                         |
| 49  | Data Pipeline Architecture Patterns | BigLake-based lakehouse pattern, ELT vs. ETL, and the medallion (bronze/silver/gold) architecture as the synthesis tying Sections 44–48 into one coherent platform.                           |

## 7. Cross-Service Decision Framework

| Question                                                                                                        | Answer                                                 |
| --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------ |
| Need governed, cross-engine access to data still physically in GCS?                                             | BigLake (§49.3)                                        |
| Need discovery, cataloging, quality, or lineage across BigQuery/GCS data?                                       | Dataplex (§47)                                         |
| Transformation is SQL-expressible and data is already/cheaply in BigQuery?                                      | ELT via BigQuery SQL (§49.4)                           |
| Transformation needs custom code, complex streaming logic, or must happen before data lands anywhere queryable? | ETL via Dataflow or Dataproc (§45, §49.4)              |
| Need to coordinate multiple services/tiers with dependencies, retries, and alerting?                            | Cloud Composer (§46)                                   |
| Need fast, ad hoc reporting for one team?                                                                       | Looker Studio (§48)                                    |
| Need one governed metric definition reused across many dashboards/teams?                                        | Looker + LookML (§48)                                  |
| Structuring raw-to-consumption data maturity?                                                                   | Medallion architecture: bronze → silver → gold (§49.5) |

## 8. Common Mistakes Spanning Part 6

- Loading raw, ungoverned data directly into BigQuery gold-tier tables with no bronze/silver staging, making it impossible to safely reprocess or audit how a final number was derived (§49.5).
- Defaulting to Dataflow/Dataproc for every transformation regardless of whether the logic is genuinely SQL-inexpressible, when a BigQuery ELT step (§49.4) would be simpler to build and maintain.
- Treating Cloud Composer as optional glue rather than the actual coordination layer, leaving bronze→silver→gold promotion as disconnected, independently scheduled jobs with no dependency awareness (§46, §49.5).
- Skipping Dataplex data quality gating between tiers, allowing bad data to silently propagate from bronze all the way to gold and into a Looker/Looker Studio dashboard (§47.3.3, §49.5).
- Assuming Looker Studio and Looker are interchangeable, and discovering only at scale that ungoverned per-report metric definitions have produced inconsistent numbers across teams (§48).

## 9. Part 6 Interview Drill (Sections 44–48)

### 🎯 Beginner Tier

**Q1:** What is the core architectural difference between BigQuery and Dataproc?
**A:** BigQuery is a serverless, SQL-first data warehouse where you never manage compute infrastructure — you write SQL and BigQuery handles execution. Dataproc is managed Spark/Hadoop, giving direct control over cluster sizing and custom code, used when processing logic isn't naturally SQL-expressible (Section 45).

**Q2:** What does Cloud Composer actually orchestrate, and what open-source project is it built on?
**A:** Composer is managed Apache Airflow. It orchestrates DAGs (Directed Acyclic Graphs) of tasks — commonly including BigQuery jobs, Dataflow pipelines, and Dataproc jobs — handling scheduling, retries, and dependency ordering across services that would otherwise need to be coordinated with ad hoc scripts (Section 46).

**Q3:** What is the fundamental difference between Looker Studio and Looker?
**A:** Looker Studio is free and self-service with no shared semantic layer — each report defines its own calculated fields. Looker is built around LookML, a version-controlled semantic layer defining metrics once and reusing them consistently across every dashboard and consumer (Section 48).

### 🎯 Intermediate Tier

**Q4:** A team wants to query the same GCS-based Parquet dataset from both BigQuery SQL and a Dataproc Spark job, with consistent row-level security enforced in both places. What GCP feature enables this?
**A:** BigLake tables. BigLake lets you define a governed table over data physically stored in GCS, applying BigQuery-grade row/column-level security that's enforced consistently regardless of which supported engine (BigQuery SQL or Dataproc/Spark) queries it — avoiding the need to separately implement and maintain access control in each engine (Section 49.3).

**Q5:** When would you choose ELT over ETL for a new BigQuery-bound pipeline?
**A:** When the transformation logic is expressible in SQL (joins, aggregations, filtering) and the source data is already in or cheaply loadable into BigQuery — ELT lets BigQuery's serverless SQL engine do the transformation work directly, avoiding the added operational surface of a separate Dataflow or Dataproc job for logic that doesn't need one (Section 49.4).

**Q6:** How does Dataplex's data quality feature typically integrate with a medallion architecture's bronze-to-silver promotion step?
**A:** A Dataplex data quality rule check is commonly wired as a required, blocking step — often orchestrated as a Cloud Composer task — before data is promoted from the bronze (raw) tier to the silver (cleaned/conformed) tier, ensuring rows that fail quality rules (nulls in required fields, out-of-range values) don't silently propagate into the more trusted, business-facing tiers (Sections 46, 47, 49.5).

### 🎯 Senior Tier

**Q7:** Design a pipeline for a retail company ingesting raw point-of-sale events (via Pub/Sub), producing a daily executive revenue dashboard, with a requirement that every number on the dashboard be traceable back to its source transaction.
**A:** Pub/Sub (§45) delivers raw POS events into a Dataflow streaming pipeline that lands them, largely as-is, into a bronze-tier BigQuery/GCS location. A Cloud Composer DAG (§46) then orchestrates promotion: a cleaning/dedup step (Dataflow or BigQuery ELT, whichever is simpler for the specific logic, §49.4) produces the silver tier, gated by a Dataplex data quality check (§47.3.3) before promotion. A further BigQuery ELT aggregation step produces gold-tier, pre-aggregated revenue tables. Looker (§48), not Looker Studio, is the right choice specifically because this is an executive-facing, high-trust metric — LookML defines "revenue" once, governed and version-controlled. Dataplex lineage (§47.3.4) directly satisfies the traceability requirement, since it automatically captures which upstream bronze-tier events and which transformation jobs fed each gold-tier aggregate, letting anyone trace a dashboard number back to its originating transaction without manual documentation.

**Q8:** A team has been using Looker Studio reports for two years, and finance has recently flagged inconsistent quarterly figures across different teams' reports. Would you recommend migrating everything to Looker, and how would you sequence the change?
**A:** No — a full migration is unnecessary and disruptive; only the metrics genuinely causing cross-team inconsistency and business risk need governance. I'd sequence this by first identifying the specific metrics finance flagged (e.g., quarterly revenue), defining those in LookML with proper review, and pointing finance's and any exec-facing reports at the new governed Looker Explore first. Lower-stakes, team-local reporting can remain in Looker Studio, since forcing full governance onto every report would add cost and friction disproportionate to the actual risk those reports pose (Section 48.7).

**Q9:** Why might an organization adopt BigLake tables over GCS data instead of simply loading everything into native BigQuery storage?
**A:** Loading everything natively into BigQuery means giving up the ability for non-BigQuery engines (Dataproc/Spark, other analytics tools) to read that same data without a separate export or copy step, and it forfeits the cost/flexibility benefits of keeping large, less latency-sensitive datasets in cheaper GCS storage in open formats. BigLake preserves BigQuery-grade governance and query performance over that GCS data while keeping it genuinely multi-engine accessible from one physical copy — the right tradeoff when an organization has genuine multi-engine consumption needs (e.g., a data science team on Spark and an analytics team on BigQuery SQL both need the same governed table), rather than adopted reflexively for data with no such cross-engine requirement.

### 🎯 Architect Tier

**Q10:** Design a complete data platform for a healthcare company that must (a) ingest streaming device telemetry, (b) support ad hoc exploratory analysis by a small data science team using Spark, (c) provide a governed, audit-ready executive dashboard, and (d) demonstrate regulatory lineage for any reported figure. Walk through the full architecture.
**A:** Streaming device telemetry flows through Pub/Sub into a Dataflow pipeline landing bronze-tier data into GCS, registered as a Dataplex raw-zone asset (§47) immediately for discoverability and governance from day one. Because the data science team needs genuine Spark access, the bronze and silver tiers are defined as BigLake tables (§49.3) over that GCS data rather than loaded natively into BigQuery — giving Dataproc/Spark-based exploratory analysis (§45) direct, governed access to the same physical data BigQuery also queries, with consistent row/column-level security enforced regardless of entry point. Silver-tier cleaning (dedup, schema conformance, PII tagging via Dataplex tag templates, §47.3.2) is gated by Dataplex data quality rules before promotion, all orchestrated as a Cloud Composer DAG (§46) rather than disconnected jobs — critical for a regulated environment where "did the quality gate actually run before this data was used" needs to be provably true, not just assumed. Gold-tier, aggregated tables feed a Looker (§48) dashboard specifically — not Looker Studio — because the executive/audit-facing nature of this data demands LookML's version-controlled, single-definition governance rather than per-report calculated fields that could drift. For the regulatory lineage requirement, Dataplex's automatic lineage capture (§47.3.4) traces every gold-tier figure back through the silver transformation job and Composer DAG run to the specific bronze-tier records and originating Pub/Sub messages — directly satisfying the audit requirement without separate manual documentation. The overall shape end to end: Pub/Sub → Dataflow (bronze) → Composer-orchestrated, Dataplex-quality-gated promotion through BigLake-backed silver → BigQuery-native gold → Looker, with Dataplex providing the governance and lineage spine across every tier.

**Q11:** Your organization's data platform has grown to include dozens of BigQuery datasets, GCS buckets, several Dataflow and Dataproc pipelines, and ad hoc Looker Studio reports across 15 teams, with no consistent maturity-tiering and frequent "which number is correct" disputes. Propose a remediation plan and its sequencing.
**A:** Sequence this to minimize disruption, front-loading low-risk, high-visibility wins. First, register the existing (unmoved) BigQuery datasets and GCS buckets as Dataplex lakes/zones/assets (§47) — pure governance registration with zero data movement, immediately giving every team a unified catalog to search and establishing a measurable baseline of what actually exists. Second, formally define bronze/silver/gold tiers (§49.5) mapped onto Dataplex's raw/curated zone concept, and for the highest-impact pipelines specifically (prioritized by which feed the most disputed numbers), introduce Dataplex data quality gates between tiers, orchestrated via Cloud Composer (§46) rather than each team's independently scheduled jobs — again prioritized rather than attempted across all 15 teams simultaneously. Third, and specifically targeting the "which number is correct" disputes, identify the small set of metrics genuinely causing cross-team disagreement and move only those into governed Looker/LookML definitions (§48), leaving lower-stakes Looker Studio reporting in place elsewhere. This sequencing — catalog and register first (safest, immediate value), then tier and quality-gate the highest-impact pipelines (moderate risk, prioritized), then govern only the specific disputed metrics in Looker (targeted, not wholesale) — directly addresses the reported symptom (inconsistent numbers) without the disruption and cost of forcing full governance onto all 15 teams' entire data estate at once.

## 10. Key Takeaways — Part 6 Overall 🔑

- 🔑 BigLake is the lakehouse-enabling layer on GCP — governed, cross-engine (BigQuery + Dataproc/Spark) access to data that physically remains in GCS, complementing rather than duplicating Dataplex's cataloging/quality/lineage role.
- 🔑 ELT (via BigQuery SQL) has become the default modern pattern for SQL-expressible transformations, with ETL (Dataflow/Dataproc) reserved for custom-code or pre-load transformation needs.
- 🔑 The medallion (bronze/silver/gold) architecture gives raw-to-consumption data a maturity structure, with Cloud Composer orchestrating promotion between tiers and Dataplex data quality rules gating that promotion.
- 🔑 Looker Studio and Looker solve different problems at different organizational scales — self-service speed versus governed, version-controlled metric consistency — and are commonly run together rather than as competing choices.
- 🔑 Every service in Part 6 (BigQuery, Dataflow/Dataproc/Pub-Sub, Composer, Dataplex, Looker/Looker Studio) is one piece of a single coherent pipeline shape, not a menu of unrelated tools — Section 49's patterns are how those pieces are meant to be assembled together in production.

## 11. Related Concepts and What's Next

Part 6 (Sections 44–49) covered GCP's full data and analytics stack: warehousing (BigQuery, §44), processing and messaging (Dataflow/Dataproc/Pub-Sub, §45), orchestration (Cloud Composer, §46), governance (Dataplex, §47), BI/visualization (Looker & Looker Studio, §48), and this section's architectural synthesis (§49). BigQuery and GCS also connect directly to Part 2's storage and database foundations (Sections 11–18), and IAM/Org Policy (Part 5, Sections 35–43) underpins every access-control layer referenced throughout — from BigQuery's own permissions to Dataplex tags to BigLake's row/column security.

**Next: Part 7 — DevOps, IaC & Observability (Sections 50–55).** Having covered how data flows through GCP, Part 7 shifts to how GCP infrastructure and applications themselves are built, deployed, and operated reliably: Cloud Build and CI/CD pipelines (Section 50), Cloud Deploy for progressive delivery (Section 51), Terraform for infrastructure as code (Section 52), Eventarc and Workflows for event-driven automation (Section 53), Cloud Monitoring/Logging/Trace/Profiler for observability (Section 54), and incident response/SRE practices (Section 55) — the operational discipline that keeps everything built in Parts 1–6 running reliably in production.
