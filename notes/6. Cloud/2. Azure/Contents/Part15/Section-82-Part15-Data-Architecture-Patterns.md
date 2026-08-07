# Section 82 — Data Engineering Architecture Patterns

## 1. Definition

**Plain language:** this section steps back from individual Azure services and asks the architectural question every data platform team eventually faces: given the raw material — ADLS Gen2, Synapse, Data Factory, Databricks, Power BI, Azure AI Search, Fabric — how do you actually put them together for a specific real workload? This section covers the recurring architectural patterns (lakehouse architecture, the medallion/bronze-silver-gold layering, batch vs. streaming processing) that answer that question, and provides a decision framework for choosing among this Part's services rather than treating each one in isolation.

**Precise definition:** a data architecture pattern is a reusable, named structural approach to organizing data ingestion, storage, transformation, and serving — this section covers the **lakehouse architecture** (unifying data-lake flexibility with warehouse-style structure and performance), the **medallion architecture** (progressive, staged data refinement across bronze/silver/gold layers), and **batch vs. streaming** processing models, synthesizing how Sections 75–81's individual services combine to implement each pattern in practice.

## 2. Why It Exists / Problem It Solves

Sections 75 through 81 each introduced one service or product at a time — but a real data platform is never "just ADLS Gen2" or "just Synapse": it's a specific combination of several of these services, arranged according to a deliberate architectural pattern, chosen because it solves a specific set of trade-offs (cost, latency, data-freshness requirement, query pattern) for a specific organization's workload. Without an explicit architectural framework, a team risks either reinventing ad hoc versions of well-established patterns (and rediscovering their pitfalls the hard way) or defaulting to whichever service they're most familiar with regardless of fit — the same "deliberate trade-off, not a default choice" theme this roadmap has applied to compute service selection ([Section 74](../Part14/Section-74-Part14-Key-Takeaways-Checklist-Next-Topics.md).2, Part 3's key takeaway) applies equally to data architecture. This section exists to make that decision framework explicit, directly ahead of [Section 83](./Section-83-Part15-WrapUp-Interview-Drill.md)'s synthesis and interview drill for the whole Part.

## 3. The Lakehouse Architecture

### 3.1 Definition

**Plain language:** for years, organizations had to choose between a **data lake** (cheap, flexible, handles any data shape, but historically lacking the reliability guarantees and fast structured-query performance of a warehouse) and a **data warehouse** (fast, reliable, well-structured, but expensive and rigid about what data shapes it can hold). The lakehouse architecture is the attempt to get both: warehouse-like reliability and query performance, built directly on top of data-lake-cheap storage, rather than requiring a separate, duplicated warehouse system alongside the lake.

**Precise definition:** a lakehouse architecture stores all data — raw, semi-structured, and fully modeled — in low-cost data lake storage (ADLS Gen2, [Section 75](./Section-75-Part15-Data-Lake-Fundamentals-ADLS-Gen2.md)) using a table format providing ACID transactions and schema enforcement on top of the lake's plain files (Delta Lake, [Section 78](./Section-78-Part15-Azure-Databricks.md).4, being the dominant such format in the Azure ecosystem), such that the same underlying storage simultaneously supports big-data/ML processing (via Spark, Sections 76.5/78) and fast, reliable SQL-based warehouse-style querying (via a serverless SQL pool, [Section 76](./Section-76-Part15-Azure-Synapse-Analytics.md).4, or a Fabric Lakehouse's SQL endpoint, [Section 81](./Section-81-Part15-Microsoft-Fabric.md).4.1) without needing to physically copy data into a separate, differently-formatted warehouse system.

### 3.2 Why This Matters — Eliminating a Historical Trade-off

Before Delta Lake and similar table formats existed, an organization genuinely had to choose: keep data cheap and flexible in a lake but accept weaker consistency guarantees and slower structured query performance, or load a curated subset into an expensive, rigid warehouse to get fast, reliable SQL queries — and maintain both, with all the duplication, latency, and consistency-management overhead that dual-system approach implies. The lakehouse pattern, enabled specifically by Delta Lake's ACID transaction layer ([Section 78](./Section-78-Part15-Azure-Databricks.md).4.1), collapses this into one system: the lake **is** the warehouse's storage layer, with SQL query performance coming from the query engine (Synapse serverless SQL, Databricks SQL Warehouse, Fabric's Lakehouse SQL endpoint) reading directly against Delta-formatted lake files, rather than a genuinely separate storage system.

## 4. Medallion Architecture (Bronze / Silver / Gold)

### 4.1 Definition, Formalized

**Definition:** the medallion architecture organizes data processing into three progressively-refined layers — **bronze** (raw, as-received data, immutable, retained for reprocessing/auditability), **silver** (validated, deduplicated, conformed data — typically in Delta Lake/Parquet format, joined and cleaned but not yet business-modeled), and **gold** (business-level, aggregated, dimensionally-modeled data optimized for the specific consumption pattern — reporting, ML feature serving, or operational dashboards) — this formalizes the raw/enriched/curated zone convention already introduced in [Section 75](./Section-75-Part15-Data-Lake-Fundamentals-ADLS-Gen2.md).5.

### 4.2 Why Each Layer Exists — Not Just "More Processing Steps"

- **Bronze exists** so that any downstream processing bug or requirements change can be corrected by reprocessing from the original, unmodified source data, rather than needing to re-extract from the (possibly no-longer-available, or since-changed) original source system — bronze is the disaster-recovery and reprocessing safety net for the entire pipeline.
- **Silver exists** as the layer where data quality problems (duplicates, malformed records, type mismatches) are resolved once, centrally — rather than every downstream consumer (each report, each ML model) needing to independently re-implement the same cleaning logic against bronze data directly.
- **Gold exists** because different consumption patterns (a finance dashboard's aggregated monthly revenue vs. a fraud-detection model's row-level feature set) need genuinely different shapes of the same underlying silver data — gold tables are deliberately narrow, purpose-built outputs rather than one universal "final" table trying to serve every consumer's needs simultaneously.

### 4.3 Medallion Architecture Mapped to This Part's Services

```
Bronze (raw)         →  ADLS Gen2 raw/ container (Section 75.5)
                         Ingested by: Data Factory / Synapse Pipelines (Section 77)

Silver (validated,   →  ADLS Gen2 enriched/ container, Delta Lake format
enriched)                Processed by: Databricks or Synapse Spark pools (Sections 76.5/78)
                         (MERGE/upsert, dedup, schema enforcement — Section 78.4.3)

Gold (curated,        →  ADLS Gen2 curated/ container, Delta Lake / dedicated SQL pool tables
business-modeled)         Served by: Synapse dedicated/serverless SQL pool (Section 76),
                          Fabric Warehouse/Lakehouse (Section 81.4)
                          Consumed by: Power BI (Section 79), Azure AI Search (Section 80)
```

🎯 **Interview Tip:** a frequently tested nuance — the medallion architecture is a **logical/organizational pattern**, not a specific Azure feature or service; the same three-layer structure can be implemented with Synapse alone, Databricks alone, Fabric alone, or any combination of them, and interviewers often probe whether a candidate can correctly place a specific Azure service's role within this pattern (e.g., "which layer would a Synapse serverless SQL pool typically query against?" — usually gold, sometimes silver for ad hoc validation, essentially never bronze directly for business-facing queries) rather than only being able to recite the bronze/silver/gold names.

## 5. Batch vs. Streaming ETL/ELT

### 5.1 Batch Processing

**Definition:** batch processing runs on a scheduled or triggered basis over a bounded set of accumulated data (e.g., "process yesterday's orders every night at 2 AM"), the model underlying most of what Sections 76–78 describe by default — Data Factory's schedule/tumbling-window triggers ([Section 77](./Section-77-Part15-Azure-Data-Factory.md).3.3), scheduled Databricks Job Clusters ([Section 78](./Section-78-Part15-Azure-Databricks.md).3.2), and nightly Synapse pipeline runs all follow this pattern, appropriate whenever the business use case tolerates data being no fresher than the last completed batch run.

### 5.2 Streaming Processing

**Definition:** streaming processing continuously ingests and processes data as it arrives, with results available within seconds or a small number of minutes rather than waiting for a scheduled batch window — implemented in the Azure ecosystem primarily via **Spark Structured Streaming** running on Databricks or Synapse Spark pools reading from a continuously-arriving source (Event Hubs or Kafka, [Section 43](../Part8/Section-43-Part8-Event-Grid-Event-Hubs-Service-Bus.md), being the typical upstream source for a streaming ETL pipeline), writing incrementally into Delta Lake tables (whose ACID transaction support, [Section 78](./Section-78-Part15-Azure-Databricks.md).4, makes safe incremental/concurrent writes from a continuously-running streaming job practical).

### 5.3 Choosing Between Them

| Factor                 | Favors Batch                                                                             | Favors Streaming                                                                                            |
| ---------------------- | ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| Freshness requirement  | Hourly/daily is acceptable                                                               | Near-real-time (seconds/minutes) genuinely required by the business use case                                |
| Operational complexity | Lower — simpler to reason about, debug, and recover from failure (rerun the batch)       | Higher — a continuously-running job requires its own monitoring, checkpointing, and failure-recovery design |
| Cost                   | Generally lower — compute runs only for the batch window, then stops (or scales to zero) | Generally higher — compute typically runs continuously to process the stream in near-real-time              |
| Typical use case       | Nightly financial reporting, daily customer analytics refresh                            | Fraud detection, real-time operational dashboards, IoT telemetry processing                                 |

🎯 **Interview Tip:** a commonly tested trap — candidates sometimes default to recommending streaming because it "sounds more modern," when the actual business requirement (e.g., a monthly finance report) has no genuine real-time need at all; the correct, defensible answer is almost always to justify the choice against the **actual stated freshness requirement and its associated cost/complexity trade-off**, exactly the same "deliberate trade-off, not a default" discipline this roadmap applies to every other architectural decision.

## 6. Lambda and Kappa Architectures (Brief Survey)

- **Lambda architecture** — runs both a batch layer (processing the full historical dataset periodically, for accuracy/completeness) and a speed/streaming layer (processing only recent data, for low latency) in parallel, merging both layers' outputs at query/serving time — historically popular when streaming engines alone couldn't be fully trusted for both correctness and low latency simultaneously.
- **Kappa architecture** — runs everything through a single streaming pipeline, treating batch reprocessing as simply "replaying the stream from an earlier point" rather than maintaining a genuinely separate batch codepath — increasingly favored as streaming engines (including Spark Structured Streaming) have matured to handle both low-latency and reprocessing/correctness concerns within one unified pipeline, reducing the dual-codebase maintenance burden Lambda architecture's two separate layers impose.

⚠️ Whether Lambda or Kappa is the "currently recommended default" continues to shift as streaming engine capabilities mature — verify current best-practice guidance rather than treating either as a permanently settled recommendation.

## 7. A Decision Framework — Choosing Among This Part's Services

| Requirement                                                                                | Recommended Starting Point                                                                                                                     |
| ------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| Need a foundational, hierarchical data lake with fine-grained access control               | ADLS Gen2 ([Section 75](./Section-75-Part15-Data-Lake-Fundamentals-ADLS-Gen2.md)) — the storage foundation underlying nearly everything else   |
| Need heavy, frequent SQL queries over a modeled, curated schema                            | Synapse dedicated SQL pool, or Fabric Warehouse (Sections 76.3/81.4.2)                                                                         |
| Need ad hoc/occasional querying directly over lake files, minimizing idle cost             | Synapse serverless SQL pool, or Fabric Lakehouse SQL endpoint (Sections 76.4/81.4.1)                                                           |
| Need heavy Spark/ML processing, mature ML tooling                                          | Azure Databricks ([Section 78](./Section-78-Part15-Azure-Databricks.md)), or Synapse Spark pools if staying fully within one Synapse workspace |
| Need to orchestrate ingestion across many sources, possibly including on-premises systems  | Azure Data Factory, or Synapse Pipelines if fully embedded in one Synapse workspace ([Section 77](./Section-77-Part15-Azure-Data-Factory.md))  |
| Need self-service business reporting/dashboards                                            | Power BI ([Section 79](./Section-79-Part15-Power-BI.md))                                                                                       |
| Need full-text or semantic/vector search over documents                                    | Azure AI Search ([Section 80](./Section-80-Part15-Azure-Cognitive-Search.md))                                                                  |
| Need to minimize the number of separately-provisioned/secured resources for a new platform | Evaluate Microsoft Fabric ([Section 81](./Section-81-Part15-Microsoft-Fabric.md)), with appropriate maturity caveats                           |
| Freshness requirement is hourly/daily                                                      | Batch processing (82.5.1)                                                                                                                      |
| Freshness requirement is genuinely seconds/minutes, business-justified                     | Streaming via Spark Structured Streaming over Event Hubs (82.5.2)                                                                              |

## 8. Architecture Diagram — A Complete Medallion Pipeline

```
Source Systems (on-prem DB, SaaS API, Event Hubs stream)
        │
        ▼  Data Factory / Synapse Pipelines (batch) or Spark Structured Streaming (streaming)
┌─────────────────────────────────────────────────────────┐
│  BRONZE  — ADLS Gen2 raw/  (immutable, as-received)        │
└─────────────────────────────────────────────────────────┘
        │  Databricks / Synapse Spark: validate, dedupe, MERGE
        ▼
┌─────────────────────────────────────────────────────────┐
│  SILVER  — ADLS Gen2 enriched/  (Delta Lake, conformed)     │
└─────────────────────────────────────────────────────────┘
        │  Aggregate, dimensional model
        ▼
┌─────────────────────────────────────────────────────────┐
│  GOLD    — ADLS Gen2 curated/  (Delta Lake / dedicated SQL) │
└─────────────────────────────────────────────────────────┘
        │                              │
        ▼                              ▼
   Power BI (Section 79)      Azure AI Search (Section 80)
   business reporting          document/vector search
```

## 9. Configuration & Hands-On Example

**A representative Spark Structured Streaming job implementing the bronze-to-silver step in near-real-time, reading from Event Hubs and writing to a Delta silver table:**

```python
raw_stream = (spark.readStream
    .format("eventhubs")
    .options(**eventhub_conf)
    .load())

(raw_stream
    .selectExpr("CAST(body AS STRING) as json_payload")
    .writeStream
    .format("delta")
    .option("checkpointLocation", "/mnt/silver/_checkpoints/orders")
    .trigger(processingTime="1 minute")
    .start("/mnt/silver/orders"))
```

- **Purpose:** continuously ingests order events from Event Hubs ([Section 43](../Part8/Section-43-Part8-Event-Grid-Event-Hubs-Service-Bus.md)) and writes them as a streaming Delta Lake table in the silver zone, processing in micro-batches every minute — an illustrative streaming implementation of the bronze-to-silver medallion step (82.4.3).
- **Important arguments explained individually:**
  - `checkpointLocation` — a required Structured Streaming setting recording processing progress, so the job can resume correctly from where it left off after a restart or failure, without either reprocessing already-handled events or silently dropping unprocessed ones.
  - `trigger(processingTime="1 minute")` — configures a micro-batch interval rather than true per-event processing, a common and pragmatic middle ground balancing near-real-time freshness against the operational simplicity and cost-efficiency of processing in small batches rather than one event at a time.
- **Common error:** omitting or misconfiguring `checkpointLocation` — without correct checkpointing, a restarted streaming job may reprocess already-handled data (producing duplicates, without idempotent write logic) or, worse, silently skip data that arrived during the restart window; checkpointing is not optional infrastructure for a production streaming pipeline.

## 10. Production & Enterprise Usage

Mature enterprise data platforms typically implement the full bronze/silver/gold medallion pattern with batch processing as the default for most workloads, layering in streaming specifically for the subset of use cases (fraud detection, real-time operational dashboards) with a genuine, business-justified low-latency requirement — rather than defaulting the entire platform to streaming, given streaming's materially higher operational complexity and cost per [Section 82](./Section-82-Part15-Data-Architecture-Patterns.md).5.3. Lakehouse-pattern adoption (storing gold-layer data as Delta Lake tables queried directly via serverless SQL or a Fabric Lakehouse, rather than physically loading into a separate dedicated warehouse) is increasingly the default starting point for new platforms specifically because it avoids the dual-system duplication historically required to get both lake flexibility and warehouse-style query performance (82.3.2).

## 11. Security Considerations

Security for a medallion-architecture pipeline is the composite of every individual service's own security guidance already covered in this Part — ACLs/RBAC on ADLS Gen2 zones ([Section 75](./Section-75-Part15-Data-Lake-Fundamentals-ADLS-Gen2.md).4), Managed Identity authentication for every pipeline/compute component reaching the lake (Sections 76.12/77.10/78.10), and appropriately scoped access to gold-layer consumption tools (Row-Level Security in Power BI, [Section 79](./Section-79-Part15-Power-BI.md).7; security filters in Azure AI Search, [Section 80](./Section-80-Part15-Azure-Cognitive-Search.md).10) — the architectural pattern itself doesn't introduce a new security model, but does introduce the discipline of applying each layer's appropriate controls consistently at every stage of the bronze-silver-gold pipeline, rather than only securing the final gold-layer output and treating bronze/silver as internal, lower-scrutiny data.

## 12. Performance Considerations

Performance across a medallion pipeline compounds across layers — a poorly-partitioned or uncompacted bronze layer ([Section 75](./Section-75-Part15-Data-Lake-Fundamentals-ADLS-Gen2.md).11) slows every downstream silver-layer Spark job reading from it, and a poorly-designed silver-layer schema or missing `OPTIMIZE`/`ZORDER` compaction ([Section 78](./Section-78-Part15-Azure-Databricks.md).4.3) slows every downstream gold-layer aggregation — meaning performance tuning should generally start upstream (bronze/silver file layout and compaction) rather than only tuning the final gold-layer query engine, since a well-tuned Synapse dedicated SQL pool distribution strategy ([Section 76](./Section-76-Part15-Azure-Synapse-Analytics.md).3.2) can't fully compensate for a poorly-organized upstream silver layer feeding it.

## 13. Monitoring

A medallion pipeline's monitoring needs span every stage — ingestion pipeline success/failure (Data Factory/Synapse Pipelines monitoring, [Section 77](./Section-77-Part15-Azure-Data-Factory.md).12), Spark job execution health ([Section 78](./Section-78-Part15-Azure-Databricks.md).12), and end-consumption freshness (a Power BI dataset refresh failure, [Section 79](./Section-79-Part15-Power-BI.md).13, or a stale Azure AI Search index, [Section 80](./Section-80-Part15-Azure-Cognitive-Search.md).12) — production platforms typically implement end-to-end pipeline observability (often via Log Analytics workbooks or Application Insights, Part 10) correlating a downstream freshness problem back to its actual upstream root cause (a failed bronze ingestion, a broken silver transformation) rather than monitoring each layer's tools in isolation.

## 14. Troubleshooting

| Symptom                                                                                                                                       | Likely Cause                                                                                                                                    | Fix                                                                                                                                                           |
| --------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Gold-layer reports show stale or missing data despite the overall pipeline "running"                                                          | A silent failure in an intermediate stage (silver transformation job, streaming checkpoint issue) that didn't halt the overall pipeline visibly | Implement end-to-end pipeline monitoring correlating each stage's success/failure, not just the final consumption layer's apparent status                     |
| Streaming pipeline reprocesses duplicate data after a restart                                                                                 | Missing or misconfigured checkpointing                                                                                                          | Verify `checkpointLocation` is correctly configured and durable; ensure downstream writes are idempotent (e.g., via Delta Lake `MERGE`) as a defense in depth |
| Team defaulted to a streaming architecture for a workload with no genuine real-time requirement, and now faces high operational/cost overhead | Streaming chosen by default rather than justified against the actual business freshness requirement                                             | Reassess the actual freshness requirement; migrate to simpler, cheaper batch processing if a scheduled/periodic refresh genuinely meets business needs        |

## 15. Interview Questions — [Section 82](./Section-82-Part15-Data-Architecture-Patterns.md)

### 🎯 Intermediate

**Q: Why does the medallion architecture use three layers (bronze/silver/gold) instead of just cleaning and modeling data in one step?**

_Model answer:_ Each layer serves a distinct purpose: bronze retains the original, unmodified data so any downstream processing bug or requirements change can be corrected by reprocessing from source, rather than needing to re-extract from a source system that may no longer have the same historical data available. Silver is where data-quality problems (duplicates, malformed records, type mismatches) get resolved once, centrally, rather than every downstream report or model re-implementing the same cleaning logic against raw data independently. Gold holds business-modeled, purpose-built outputs, because different consumers (a finance dashboard vs. an ML model) genuinely need different shapes of the same underlying silver data, and trying to serve every consumer from one universal "final" table doesn't fit either well.

_What the interviewer is probing:_ whether the candidate can justify each layer's existence functionally, rather than just reciting the bronze/silver/gold names without understanding why the staged separation actually matters.

### 🎯 Senior/Architect

**Q: A retail company wants real-time fraud detection on transactions, but also needs traditional nightly financial reporting from the same underlying transaction data. Design the data architecture, and justify your batch/streaming choices.**

_Model answer:_ I'd split this into two paths sharing the same bronze ingestion, rather than forcing the entire platform into one processing model. Transaction events would land in the bronze zone (ADLS Gen2 raw/) via both a Data Factory batch pipeline for bulk/historical loads and Event Hubs for real-time event capture, since both consumption paths ultimately need the same raw data available. For fraud detection, I'd use Spark Structured Streaming (Databricks or Synapse Spark) reading directly from Event Hubs, applying fraud-detection logic in near-real-time and writing flagged transactions to a silver-layer Delta table with sub-minute micro-batch triggers, since this use case has a genuine, business-justified low-latency requirement — a fraud alert arriving hours later provides little value. For the nightly financial reporting, I'd use a much simpler nightly batch pipeline (Data Factory or a scheduled Databricks Job Cluster) processing the same bronze data into a separate gold-layer, dimensionally-modeled reporting schema, served via a Synapse dedicated SQL pool and consumed by Power BI — deliberately choosing batch here rather than reusing the streaming pipeline's output, since financial reporting has no genuine real-time requirement and batch is materially simpler and cheaper to operate and recover. I'd explicitly justify this split against each use case's actual freshness requirement rather than defaulting the whole platform to streaming just because one part of it needs it, directly avoiding the common mistake of over-applying streaming's added complexity and cost to a workload that doesn't need it.

_What the interviewer is probing:_ the ability to correctly segment a mixed workload by its genuinely different freshness requirements rather than picking one processing model for the entire platform, and explicit justification of the batch/streaming choice against the stated business need rather than defaulting to whichever sounds more sophisticated.

## 16. Common Misconceptions

- **"The medallion architecture is an Azure-specific feature you enable somewhere."** False — it's a logical, engine-agnostic organizational pattern implementable with Synapse, Databricks, Fabric, or any combination; there is no single "medallion" toggle or resource.
- **"Streaming is strictly better than batch because it's more real-time."** False — streaming carries materially higher operational complexity and cost; batch remains the correct choice whenever the actual business freshness requirement doesn't need sub-hour latency.
- **"A lakehouse architecture means giving up warehouse-style query performance."** False — the entire point of the lakehouse pattern, enabled by Delta Lake's ACID guarantees, is achieving warehouse-like reliability and query performance directly on lake storage, without a separate, duplicated warehouse system.

## 17. Key Takeaways

- 🔑 The lakehouse architecture unifies lake-storage economics with warehouse-style reliability and query performance, enabled specifically by Delta Lake's ACID transaction layer on top of plain Parquet files.
- 🔑 The medallion (bronze/silver/gold) pattern is a logical, engine-agnostic organizational convention, not an Azure-specific feature — each layer exists for a distinct, justifiable reason (reprocessing safety net, centralized cleaning, purpose-built consumption shapes).
- 🔑 Batch processing should remain the default; streaming should be adopted only for the specific subset of workloads with a genuine, business-justified low-latency requirement, given its materially higher operational complexity and cost.
- 🔑 A mixed workload (e.g., real-time fraud detection alongside nightly reporting) can and often should split into parallel batch and streaming paths sharing the same bronze ingestion, rather than forcing the entire platform into one processing model.
- 🔑 Performance and security in a medallion pipeline compound across layers — tuning and securing only the final gold-layer output without attention to bronze/silver leaves the overall pipeline both slower and less secure than the sum of its individually-tuned parts would suggest.

## 18. Related Concepts (Next Up)

[Section 83](./Section-83-Part15-WrapUp-Interview-Drill.md) closes Part 15 with a synthesis of every section covered — Data Lake Fundamentals/ADLS Gen2, Synapse, Data Factory, Databricks, Power BI, Azure AI Search, Microsoft Fabric, and this section's architecture patterns — plus a rapid-fire interview drill spanning the whole Part, before transitioning to Part 16's coverage of AI/ML and Generative AI on Azure, which builds directly on this Part's data foundation (particularly Azure AI Search's vector search capability, [Section 80](./Section-80-Part15-Azure-Cognitive-Search.md).5) as the data layer underlying Azure's AI/ML services.
