# Section 47 (Part 6): Dataplex — Data Governance & Catalog

## 1. Definition

**Plain language:** As organizations spread data across BigQuery, Cloud Storage, and other systems, it becomes hard to know what data even exists, who owns it, whether it's trustworthy, and where a given number in a report actually came from. Dataplex is Google's answer: a single layer that discovers, catalogs, tags, quality-checks, and traces data across all of these systems without requiring you to physically move or copy the data.

**Precise:** Dataplex is an intelligent data fabric service that provides unified data management — discovery, metadata cataloging, data quality, and data lineage — across distributed data in Cloud Storage, BigQuery, and other sources, organized through a logical structure of **lakes**, **zones**, and **assets**, without requiring data movement or duplication.

## 2. Why It Exists / Problem It Solves

As data platforms grow, data ends up scattered: raw files in Cloud Storage buckets, curated tables in BigQuery, streaming outputs from Dataflow, and Spark output from Dataproc — often owned by different teams with inconsistent naming, undocumented schemas, and no visibility into whether a given dataset is trustworthy, fresh, or even still in use. This creates several concrete problems:

- **Discovery failure:** Analysts and data scientists can't find data that already exists, leading to duplicated effort and re-collection of data the organization already has.
- **Trust failure:** Without visible data quality metrics or lineage, consumers of a dashboard or report can't answer "is this number correct, and where did it come from?" — a critical gap for regulated industries and any high-stakes decision-making.
- **Governance failure:** Applying consistent access policies and classification (e.g., tagging PII columns) across many separately-managed storage systems and BigQuery datasets, by hand, doesn't scale past a small number of teams.

Dataplex solves this by layering a unified governance and discovery plane over existing data _in place_ — it does not require centralizing all data into one storage system first, which is a deliberate architectural difference from approaches that require full data migration before governance can be applied.

## 3. Core Concepts

### 3.1 Lakes, Zones, and Assets

Dataplex organizes data using a three-level logical hierarchy that sits _on top of_ existing storage, without moving the underlying data:

- **Lake:** A logical grouping representing a business unit or domain (e.g., a "Marketing Lake" or "Finance Lake"), the top-level organizational construct.
- **Zone:** A sub-grouping within a lake representing a data maturity or governance tier — commonly a **raw zone** (unprocessed, ingested-as-is data) and a **curated zone** (cleaned, validated, ready-for-consumption data), each with its own governance rules (e.g., stricter schema enforcement in the curated zone).
- **Asset:** A reference to an actual underlying resource — a Cloud Storage bucket or a BigQuery dataset — attached to a zone. The asset is a pointer/registration, not a copy; the data remains exactly where it physically lives.

### 3.2 Data Discovery and Metadata Management

Dataplex automatically scans registered assets to discover new or changed data (similar in spirit to Glue Crawlers on AWS), inferring schema for structured/semi-structured files and keeping BigQuery table metadata in sync, then surfaces all of this through a searchable catalog — **Dataplex Catalog** (previously Data Catalog) — where users can search across every lake/zone/asset by table name, column name, or attached business tags, rather than needing to already know which specific system a dataset lives in.

- **Tags and tag templates** let organizations attach structured, custom metadata to tables and columns (e.g., a `data_classification` tag with values like `public`, `internal`, `restricted`) beyond Dataplex's automatically inferred schema metadata — used both for discovery and as an input to governance policy.

### 3.3 Data Quality

Dataplex lets teams define **data quality rules** (e.g., "column `email` must never be null," "column `order_total` must be non-negative," "row count should not drop more than 20% day-over-day") that run automatically as scheduled checks against registered assets, surfacing pass/fail results and trends over time — turning "is this dataset trustworthy?" from a manual, ad hoc investigation into an automated, continuously monitored signal.

### 3.4 Data Lineage

Dataplex automatically captures **lineage** — which upstream tables/files fed into a given table's creation, via which job (a BigQuery query, a Dataflow pipeline, a Dataproc job) — letting users trace "where did this specific number in this report actually come from" all the way back through the pipeline, and conversely, assess downstream impact before changing or deprecating a source table.

## 4. Architecture Diagram

```
                     ┌────────────────────────────────────────┐
                     │              Dataplex                  │
                     │                                        │
                     │   Lake: "Sales"                        │
                     │   ┌──────────────┐   ┌──────────────┐  │
                     │   │  Raw Zone    │   │ Curated Zone │  │
                     │   │  (asset: GCS │   │ (asset: BQ   │  │
                     │   │   bucket)    │   │  dataset)    │  │
                     │   └──────────────┘   └──────────────┘  │
                     │           │                    │       │
                     │  Discovery, Catalog, Tags,     │       │
                     │ Data Quality Rules, Lineage ───┘       │
                     └────────────────────────────────────────┘
                            │                        │
                            ▼                        ▼
                  Cloud Storage bucket        BigQuery dataset
                 (data stays in place —      (data stays in place —
                  Dataplex only registers      Dataplex only registers
                  and governs it)              and governs it)
```

## 5. Comparison: Dataplex vs. AWS Glue Data Catalog / Lake Formation vs. Azure Purview

| Capability                         | Dataplex (GCP)                                                   | Glue Data Catalog / Lake Formation (AWS)                                           | Microsoft Purview (Azure)                                                                       |
| ---------------------------------- | ---------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| **Metadata catalog**               | Dataplex Catalog (unified, cross-source)                         | Glue Data Catalog (primarily S3/Athena/Redshift-oriented)                          | Purview Data Map/Catalog (cross-source, including non-Azure)                                    |
| **Fine-grained access control**    | Integrates with BigQuery/IAM policies; governance layered on top | Lake Formation (column/row/cell-level permissions) — a separate, dedicated service | Purview access policies (increasingly integrated, historically newer than AWS's Lake Formation) |
| **Data quality checks**            | Native, built-in rule-based data quality                         | Requires separate tooling (e.g., AWS Glue DataBrew, or third-party)                | Native data quality features (newer addition)                                                   |
| **Data lineage**                   | Native, automatic, cross-service (BigQuery, Dataflow, Dataproc)  | Requires separate tooling or manual tracking historically; improving               | Native, automatic lineage across scanned Azure and non-Azure sources                            |
| **Logical organization construct** | Lakes / Zones / Assets                                           | Databases / Tables (flatter, less zone-tiered by default)                          | Collections / Assets                                                                            |
| **Scope**                          | Primarily GCP-native sources, with some external connectivity    | Primarily AWS-native (S3-centric)                                                  | Broadest multi-cloud/on-prem scanning scope among the three                                     |

> ⚠️ **Interview-relevant nuance:** AWS splits catalog (Glue Data Catalog) and fine-grained governance (Lake Formation) into two distinct services, whereas Dataplex bundles discovery, cataloging, quality, and lineage into one unified service with a zone-based organizational model — a genuinely different product shape, not just a renaming, and a common point of confusion for engineers moving between the two clouds.

## 6. Hands-On Example

**Purpose:** Create a Dataplex lake and register a raw zone backed by an existing Cloud Storage bucket as an asset.

```bash
gcloud dataplex lakes create sales-lake \
  --location=us-central1 --display-name="Sales Lake"

gcloud dataplex zones create raw-zone \
  --lake=sales-lake --location=us-central1 \
  --resource-location-type=SINGLE_REGION --type=RAW \
  --discovery-enabled

gcloud dataplex assets create raw-orders-bucket \
  --lake=sales-lake --zone=raw-zone --location=us-central1 \
  --resource-type=STORAGE_BUCKET \
  --resource-name=projects/my-project/buckets/raw-orders-bucket
```

**Expected output (abbreviated):**

```
Created lake [sales-lake].
Created zone [raw-zone].
Created asset [raw-orders-bucket]. Discovery scan scheduled.
```

**Purpose:** Search the Dataplex Catalog for tables/columns matching a keyword.

```bash
gcloud data-catalog entries search --query="orders" --scope-project=my-project
```

**Expected output (abbreviated):**

```
NAME                                    DISPLAY_NAME    TYPE
projects/my-project/.../orders_raw      orders_raw      TABLE
projects/my-project/.../orders_curated  orders_curated  TABLE
```

> 💡 **Tip:** Enabling `--discovery-enabled` on a zone is what triggers Dataplex's automatic, scheduled schema-inference scans of newly arriving files — without it, new files land in the bucket but never get registered as discoverable, schema-inferred data in the catalog.

## 7. Production & Enterprise Usage

- **Cross-team data discovery portal:** Large enterprises use Dataplex Catalog as the single, organization-wide search entry point for "does this data already exist," reducing duplicated data collection/ingestion efforts across teams that would otherwise not know about each other's datasets.
- **Automated data quality gating:** Production pipelines commonly wire a Dataplex data quality check as a required, blocking step (often via a Cloud Composer task, Section 46) before promoting data from a raw zone to a curated zone, ensuring bad data can't silently propagate downstream to dashboards or ML training sets.
- **Compliance-driven lineage audits:** Regulated industries (finance, healthcare) use Dataplex lineage to answer regulator or auditor questions about exactly which source systems and transformations fed into a specific reported figure, satisfying traceability requirements that manual documentation struggles to keep reliably up to date.

## 8. Common Misconceptions

- **Misconception:** "Dataplex moves or copies my data into a new storage system." Dataplex is a governance and metadata layer — lakes, zones, and assets are logical registrations pointing at data that continues to live exactly where it already does (Cloud Storage, BigQuery), with zero data duplication as a deliberate design choice.
- **Misconception:** "Data quality rules and lineage are separate manual processes I still need to maintain elsewhere." Dataplex is specifically designed to automate both as native, ongoing capabilities tied to the same registered assets used for discovery, rather than requiring separate bolt-on tooling.

## 9. Interview Questions

**🎯 Beginner:** _What is the difference between a Dataplex lake, zone, and asset?_
**Model answer:** A lake is the top-level logical grouping, typically representing a business domain (e.g., "Sales"). A zone is a sub-grouping within a lake representing a data maturity tier, most commonly raw (unprocessed) versus curated (validated, consumption-ready), each with its own governance expectations. An asset is a registered pointer to an actual underlying resource — a specific Cloud Storage bucket or BigQuery dataset — attached to a zone; the data itself never moves, Dataplex just registers and governs it in place.

**🎯 Intermediate:** _How does Dataplex's approach to data quality change the reliability of a reporting pipeline compared to having no automated checks at all?_
**Model answer:** Without automated checks, bad data (nulls in a required field, an unexpected drop in row count, an out-of-range value) can silently flow from a raw ingestion point all the way to a dashboard, and the first anyone learns about it is when a business stakeholder notices a wrong number. Dataplex data quality rules run as scheduled, automated checks against registered assets, so a violated rule (e.g., a null spike in an `email` column) is caught and can block downstream promotion or trigger an alert before the bad data ever reaches a report — moving quality assurance from reactive (caught after the fact) to proactive (caught at the source).

**🎯 Senior/Architect:** _A financial services company has data spread across dozens of BigQuery datasets and GCS buckets, owned by different teams with no consistent tagging or documented lineage, and is facing a regulatory audit requiring full traceability of every number in their quarterly reports. How would you use Dataplex to address this?_
**Model answer:** First, organize the existing datasets into Dataplex lakes per business domain (e.g., separate lakes for "Trading," "Retail Banking," "Risk"), with raw and curated zones per lake, registering existing BigQuery datasets and GCS buckets as assets without moving any data — this alone gives the organization its first unified, searchable view of what data exists and who logically owns it. Second, apply tag templates for classification (e.g., `regulatory_scope`, `data_owner`) across discovered tables, prioritizing the tables that actually feed the quarterly reports first, since full-organization tagging is a large undertaking better done in priority order than all at once. Third, rely on Dataplex's automatic lineage capture across BigQuery/Dataflow/Dataproc jobs to reconstruct the actual transformation chain feeding each reported figure, using this directly as the audit trail evidence, and layer in data quality rules on the specific source tables feeding regulatory reports so the audit can also demonstrate ongoing, automated data trustworthiness, not just after-the-fact lineage tracing.

## 10. Key Takeaways 🔑

- 🔑 Dataplex unifies discovery, cataloging, quality, and lineage across Cloud Storage and BigQuery data in place, without requiring data movement or duplication.
- 🔑 The lake/zone/asset hierarchy is a logical governance structure layered over existing storage, not a new storage system itself.
- 🔑 Dataplex bundles capabilities AWS splits across Glue Data Catalog and Lake Formation, and that Azure Purview offers with the broadest multi-cloud scanning scope among the three.
- 🔑 Automated data quality rules and native lineage turn "is this data trustworthy and where did it come from" from manual investigation into continuously monitored, auditable signals.

## 11. Related Concepts

BigQuery and Cloud Storage as the primary governed data stores (Section 44, Part 2 Section 11), Dataflow/Dataproc/Composer jobs as the lineage-tracked transformation steps (Sections 45–46), and IAM/Org Policy governance layers that Dataplex complements at the metadata level (Part 5).
