# Section 77 — Azure Data Factory

## 1. Definition

**Plain language:** Azure Data Factory (ADF) is Azure's dedicated cloud ETL/ELT orchestration service — a tool for building, scheduling, and monitoring data pipelines that move data from one place to another (a database to a data lake, an on-premises file share to Blob Storage, a SaaS API to a warehouse) and optionally transform it along the way, without writing and hosting custom integration code yourself.

**Precise definition:** Azure Data Factory is a managed orchestration service built around **pipelines** (containers of ordered activities), **activities** (individual units of work — copy data, run a stored procedure, invoke a Databricks notebook, run a mapping data flow), **datasets** (named references to specific data within a linked service), **linked services** (connection definitions to source/destination systems), and **triggers** (what causes a pipeline to run — a schedule, an event, or a manual invocation), all orchestrated via **integration runtimes** that provide the actual compute executing data movement and transformation.

## 2. Why It Exists / Problem It Solves

Every analytics platform covered so far in this Part — the ADLS Gen2 data lake (Section 75), Synapse's SQL and Spark pools (Section 76) — needs data to actually arrive from somewhere before any of it can be queried or processed: an on-premises SQL Server, a SaaS application's REST API, files dropped by a partner into an FTP server, a stream of application events. Data Factory exists to solve this "getting data reliably from A to B, on a schedule or in response to an event, with retry/monitoring/dependency logic" problem as a managed service, rather than requiring a team to write, host, and operate custom scripts or scheduled jobs for what is fundamentally a repeated, operational concern across nearly every data platform. It's also intentionally decoupled from any single compute engine — a Data Factory pipeline can invoke Synapse Spark pools, Databricks notebooks, Azure Functions, or its own built-in copy and mapping-dataflow activities, making it the connective tissue between disparate source systems and whichever processing engine (Synapse, Databricks, or ADF's own transformation capability) actually does the heavy lifting, rather than a processing engine itself.

This is also precisely why Synapse Pipelines (Section 76.6) exists as essentially the same technology embedded inside a Synapse workspace: Microsoft recognized that most Synapse customers also needed exactly this orchestration capability, and rather than requiring a separate standalone Data Factory resource for every Synapse deployment, embedded the same underlying orchestration engine directly into the Synapse workspace. Section 77.6 covers when a standalone ADF resource is still the better choice despite this overlap.

## 3. Pipelines, Activities, Datasets, Linked Services

### 3.1 The Core Object Model

**Definition:** a **pipeline** is a logical grouping of **activities** executed together, with configurable dependencies between them (activity B runs only on activity A's success, failure, or completion regardless of outcome); each activity operates against **datasets** (named, reusable pointers to a specific table, file, or folder) which in turn reference a **linked service** (the connection string/credential/endpoint definition for the underlying system — a specific Azure SQL Database, an ADLS Gen2 account, an on-premises file share).

### 3.2 Common Activity Types

- **Copy Activity** — moves data from a source dataset to a sink dataset, with built-in support for a large number of connector types and automatic schema mapping, retry, and fault tolerance.
- **Mapping Data Flow Activity** — invokes a visually-designed, Spark-executed transformation graph (77.5) directly within the pipeline.
- **Databricks Notebook / Synapse Notebook Activity** — invokes a Databricks (Section 78) or Synapse Spark notebook as a pipeline step, letting ADF orchestrate compute-heavy transformation logic that lives elsewhere.
- **Stored Procedure / Lookup / Web / Execute Pipeline** — activities for invoking database logic, reading small control-flow-relevant values, calling external HTTP endpoints, or invoking another pipeline as a nested sub-pipeline.

### 3.3 Triggers

- **Schedule trigger** — runs a pipeline on a defined recurring schedule (e.g., nightly at 2 AM).
- **Tumbling window trigger** — runs a pipeline repeatedly over fixed, sequential, non-overlapping time windows, with built-in support for dependency chaining between windows and automatic retry/backfill of a specific missed window — the appropriate trigger type when a pipeline logically processes "the data for period X" and windows must be processed in order or with awareness of prior-window completion.
- **Event-based trigger** — runs a pipeline in response to a blob being created or deleted in a storage account, enabling event-driven ("process this file as soon as it lands") pipelines rather than only time-based scheduling.

## 4. Integration Runtimes

### 4.1 Definition

**Definition:** an integration runtime (IR) is the actual compute infrastructure that executes an ADF pipeline's data movement and transformation — every linked service specifies which IR it uses, and the choice of IR type determines where that connection's traffic originates from and what kind of source/destination it can reach.

### 4.2 Three Integration Runtime Types

- **Azure Integration Runtime** — fully managed, serverless compute hosted by Microsoft in Azure, used for connecting to cloud-based data stores and for running cloud-hosted transformation (mapping data flows); requires no infrastructure management, and is the default choice whenever both source and destination are cloud-accessible.
- **Self-Hosted Integration Runtime (SHIR)** — software installed on a VM or on-premises machine that the customer provisions and manages, required whenever a pipeline needs to reach a data source that isn't reachable from Azure's managed network directly — most commonly an on-premises database or file share behind a corporate firewall, reached by the SHIR acting as a secure bridge that initiates outbound-only connections back to the Data Factory service, avoiding the need to open inbound firewall ports.
- **Azure-SSIS Integration Runtime** — a managed cluster of Azure VMs specifically provisioned to execute existing SQL Server Integration Services (SSIS) packages, aimed at organizations migrating existing on-premises SSIS-based ETL workloads to Azure without needing to fully rewrite them as native ADF pipelines first.

⚠️ Exact SHIR sizing recommendations, supported connector lists per IR type, and Azure-SSIS IR node-count/pricing options evolve over time — verify current guidance against official documentation when planning a production hybrid ingestion architecture.

🎯 **Interview Tip:** a frequently tested point — the Self-Hosted Integration Runtime is the specific mechanism enabling hybrid connectivity for Data Factory without requiring a full VPN Gateway/ExpressRoute connection (Section 26) between Azure and on-premises; the SHIR software itself makes only outbound connections from the on-premises network to the Data Factory service, meaning no inbound firewall rule needs to be opened on the on-premises side — a materially different (and often preferred, for this specific narrow use case) connectivity model from the always-on network-level hybrid connectivity Section 26 covers.

## 5. Mapping Data Flows

**Definition:** Mapping Data Flows are visually-designed data transformation graphs — built via a drag-and-drop canvas defining sources, transformation steps (join, aggregate, filter, pivot, and dozens of others), and sinks — that ADF compiles and executes as Spark jobs under the hood, without requiring the pipeline author to write any Spark code directly.

**Why this matters:** mapping data flows let a data engineer comfortable with ETL logic but not with writing PySpark/Scala directly still leverage Spark's distributed processing power, since ADF handles translating the visual graph into an executed Spark job — this is a deliberate accessibility trade-off: less flexibility and lower-level control than hand-written Spark code (as used in Synapse or Databricks notebooks, Sections 76.5/78), in exchange for a substantially lower barrier to entry for common transformation patterns.

## 6. Azure Data Factory vs. Synapse Pipelines

| Aspect                      | Azure Data Factory                                                                                                                                         | Synapse Pipelines                                                                                                                                                               |
| --------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Deployment                  | Standalone resource                                                                                                                                        | Embedded within a Synapse workspace                                                                                                                                             |
| Underlying technology       | Same core orchestration engine                                                                                                                             | Same core orchestration engine                                                                                                                                                  |
| Best fit                    | Organizations needing orchestration decoupled from any single analytics workspace, or orchestrating across multiple Synapse workspaces/non-Synapse targets | Organizations already standardized on a single Synapse workspace as their analytics platform, wanting orchestration in the same authoring/monitoring surface as SQL/Spark pools |
| Data flow / Spark execution | Own mapping data flows, invokes external Databricks/Synapse Spark                                                                                          | Own mapping data flows, invokes the same workspace's Spark pools directly                                                                                                       |
| Governance                  | Independent Azure resource, its own RBAC scope                                                                                                             | Inherits the Synapse workspace's access model                                                                                                                                   |

🎯 **Interview Tip:** this comparison is one of the most commonly asked Azure data-engineering interview questions precisely because the two are built on the same technology — the correct answer isn't "they're different products with different capabilities," but rather "the same orchestration engine, offered as either a standalone resource or embedded in a Synapse workspace," with the actual decision driven by organizational structure (single unified Synapse platform vs. orchestration spanning multiple targets) rather than a capability gap.

## 7. Architecture Diagram

```
On-Premises SQL Server ──▶ Self-Hosted Integration Runtime ──▶┐
                              (outbound-only connection)        │
SaaS API / FTP Partner Feed ──▶ Azure Integration Runtime ────┤
                                                                 ▼
                                            Azure Data Factory Pipeline
                                            ┌─────────────────────────┐
                                            │ Copy Activity             │
                                            │   ↓                       │
                                            │ Mapping Data Flow          │
                                            │ (Spark, transform)         │
                                            │   ↓                       │
                                            │ Databricks Notebook        │
                                            │ Activity (ML/heavy compute)│
                                            └─────────────────────────┘
                                                     │
                                                     ▼
                                    ADLS Gen2 (raw → enriched → curated)
                                                     │
                                                     ▼
                                        Synapse dedicated SQL pool / Power BI
```

## 8. Configuration & Hands-On Example

**Creating a Data Factory and a linked service to ADLS Gen2:**

```bash
az datafactory create \
  --name adf-ingestion-prod \
  --resource-group rg-data-platform \
  --location eastus

az datafactory linked-service create \
  --factory-name adf-ingestion-prod \
  --resource-group rg-data-platform \
  --name ls-adls-raw \
  --properties '{
    "type": "AzureBlobFS",
    "typeProperties": {
      "url": "https://stdatalakeprod.dfs.core.windows.net"
    }
  }'
```

- **Purpose:** provisions a Data Factory instance and defines a linked service connecting it to the ADLS Gen2 account created in Section 75.8, establishing the connection that datasets and copy activities will reference.
- **Important arguments explained individually:**
  - `--properties` — a JSON payload defining the linked service's type (`AzureBlobFS` specifically for ADLS Gen2, distinct from the plain `AzureBlobStorage` type used for flat-namespace Blob Storage) and its connection details.
  - The `.dfs.core.windows.net` endpoint — the ADLS Gen2-specific data-plane endpoint (distinct from the `.blob.core.windows.net` endpoint used for flat-namespace blob access), reflecting the hierarchical-namespace-aware API surface described in Section 75.3.
- **Common error:** authenticating the linked service with an embedded storage account key/connection string rather than the Data Factory's **Managed Identity** — a stored-credential anti-pattern this roadmap has flagged repeatedly (most recently in Section 75.10); production linked services should assign the Data Factory's system-assigned managed identity the appropriate RBAC role (e.g., Storage Blob Data Contributor) on the target storage account instead.

## 9. Production & Enterprise Usage

Enterprise Data Factory deployments typically separate pipelines by environment (dev/test/prod Data Factory instances, or a single instance with environment-specific parameterized linked services) and integrate with Azure DevOps or GitHub-based CI/CD (Part 9) for promoting pipeline definitions between environments as version-controlled JSON artifacts, following the same "build once, promote the same artifact, vary only configuration" discipline established generally in Section 45. Self-Hosted Integration Runtimes reaching on-premises systems are typically deployed redundantly (multiple SHIR nodes registered to the same logical IR) for high availability, so a single on-premises gateway VM's failure doesn't halt hybrid ingestion pipelines.

## 10. Security Considerations

- Use the Data Factory's **Managed Identity** (Section 9) for authenticating to linked services wherever the target supports it (ADLS Gen2, Azure SQL, Key Vault), rather than storing connection strings or keys directly in linked service definitions.
- Store any credentials that genuinely can't be replaced by managed identity (e.g., a third-party SaaS API key) in **Key Vault** (Section 56) and reference them from the linked service via Key Vault integration, rather than embedding secrets directly in pipeline JSON.
- For hybrid pipelines, the **Self-Hosted Integration Runtime** should be deployed on a hardened, patched VM with network access scoped tightly to only the specific on-premises systems it needs to reach — since a compromised SHIR host would have a network path into those on-premises systems.

## 11. Performance Considerations

Copy Activity performance scales with the configured **Data Integration Units (DIUs)** and the degree of parallelism/partitioning configured for the copy — for very large table or file-set copies, explicitly partitioning the copy (e.g., by date range) allows parallel execution across multiple concurrent sub-copies rather than a single serial stream. Mapping Data Flows, being Spark-executed under the hood, benefit from the same columnar-format and partition-pruning considerations already established in Section 75.11/76.13 — reading Parquet from a well-partitioned lake directory is materially faster than reading unpartitioned CSV.

## 12. Monitoring

Data Factory provides built-in pipeline **monitoring views** in the ADF Studio (run history, activity-level duration and status, failure error detail) and integrates with Azure Monitor (Part 10) for metrics and diagnostic logs sent to Log Analytics (Section 51) — enabling alerting (Section 53) on pipeline failure, unusually long run duration, or SHIR node health, so that a broken nightly ingestion pipeline surfaces as an actionable alert rather than being discovered only when downstream reports are found to be stale.

## 13. Troubleshooting

| Symptom                                                                        | Likely Cause                                                                                                                                 | Fix                                                                                                                                                              |
| ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Pipeline fails connecting to an on-premises data source                        | Self-Hosted Integration Runtime not running, not registered correctly, or blocked by an on-premises outbound firewall rule                   | Verify SHIR service status on the host VM; confirm outbound connectivity to the required Data Factory service endpoints                                          |
| Copy Activity performance is far below expected throughput for a large dataset | Copy not partitioned/parallelized; low configured DIUs; source or sink format not optimized (unpartitioned CSV)                              | Enable partition-based parallel copy; increase DIU allocation; convert source data to a partitioned, columnar format                                             |
| Pipeline works correctly in dev but fails after CI/CD promotion to production  | Environment-specific linked service parameters (connection endpoints, credentials) not correctly parameterized/substituted during deployment | Review ARM/Bicep template parameterization for the Data Factory's linked services; ensure environment-specific values are injected at deploy time, not hardcoded |

## 14. Interview Questions — Section 77

### 🎯 Intermediate

**Q: Your organization needs to ingest data from an on-premises SQL Server that isn't reachable directly from Azure. How does Data Factory handle this, and what's the underlying connectivity mechanism?**

_Model answer:_ Data Factory handles this via a Self-Hosted Integration Runtime (SHIR) — software installed on a VM or machine within the on-premises network that acts as a secure bridge back to the Data Factory service. The SHIR makes only outbound connections from the on-premises side to Data Factory, so no inbound firewall port needs to be opened on the on-premises network specifically for this — this is a materially lighter-weight connectivity model than establishing a full VPN Gateway or ExpressRoute connection, and is often sufficient purely for scheduled data-movement scenarios where full always-on network-level hybrid connectivity isn't otherwise required.

_What the interviewer is probing:_ whether the candidate knows the specific SHIR mechanism by name and understands its outbound-only connectivity model, rather than assuming any hybrid Data Factory scenario automatically requires full VPN Gateway/ExpressRoute connectivity.

### 🎯 Senior/Architect

**Q: A retail company runs both a Synapse workspace and a standalone Azure Data Factory instance, and a new data engineer asks why both exist given that Synapse Pipelines can do the same thing. How do you explain the decision, and under what circumstances would you consolidate onto one or the other?**

_Model answer:_ I'd explain that Synapse Pipelines and standalone Data Factory are built on the same underlying orchestration engine, so the choice isn't about one having capabilities the other lacks — it's about organizational and architectural fit. If this company's standalone Data Factory instance exists because it orchestrates ingestion into multiple downstream targets beyond just the one Synapse workspace (for example, feeding both the Synapse data lake and a separate Databricks-based platform, or serving as a shared, company-wide ingestion layer used by multiple business units each with their own analytics workspace), keeping it standalone makes sense, since embedding equivalent logic inside one specific Synapse workspace would awkwardly couple company-wide ingestion to a single workspace's lifecycle and access model. If, on investigation, the standalone Data Factory instance in practice only ever feeds this one Synapse workspace and nothing else, I'd recommend consolidating that orchestration logic into Synapse Pipelines directly, since that removes an entire separate resource, its own RBAC surface, and its own monitoring configuration to maintain, in favor of everything living in one workspace with one access model and one monitoring surface — directly reducing operational overhead without losing any actual capability, since the underlying engine is identical.

_What the interviewer is probing:_ recognition that the ADF-vs-Synapse-Pipelines question is an architectural/organizational decision rather than a capability comparison, and the ability to reason concretely about when consolidation genuinely reduces overhead versus when a standalone orchestration layer is still architecturally justified.

## 15. Common Misconceptions

- **"Data Factory is a data transformation/processing engine like Spark."** False — ADF is primarily an orchestration service; actual heavy transformation is delegated to Mapping Data Flows (itself Spark under the hood), Databricks, or Synapse Spark pools, rather than ADF processing data with its own compute engine directly (aside from the lightweight Copy Activity).
- **"Reaching an on-premises data source with Data Factory always requires a VPN Gateway or ExpressRoute connection."** False — the Self-Hosted Integration Runtime provides hybrid connectivity via outbound-only connections specifically for Data Factory's use, without requiring full network-level hybrid connectivity for this purpose alone.
- **"Synapse Pipelines and Azure Data Factory are competing, differently-capable products."** False — they're the same underlying orchestration engine; the choice between a standalone ADF resource and Synapse's embedded pipelines is architectural/organizational, not a capability trade-off.

## 16. Key Takeaways

- 🔑 Data Factory orchestrates data movement and transformation via pipelines, activities, datasets, and linked services, executed by one of three integration runtime types (Azure, Self-Hosted, Azure-SSIS).
- 🔑 The Self-Hosted Integration Runtime enables hybrid, on-premises connectivity via outbound-only connections, a lighter-weight mechanism than full VPN Gateway/ExpressRoute connectivity for this specific data-movement use case.
- 🔑 Mapping Data Flows let engineers build Spark-executed transformations visually, without writing PySpark/Scala directly, trading flexibility for accessibility.
- 🔑 Synapse Pipelines (Section 76.6) is the same underlying engine as standalone Data Factory, embedded in a Synapse workspace — the choice between them is architectural (single-workspace vs. cross-workspace/organization-wide orchestration), not a capability gap.
- 🔑 Managed Identity should authenticate every linked service that supports it, avoiding stored credentials — the same pattern established throughout this roadmap since Part 2.

## 17. Related Concepts (Next Up)

Section 78 introduces **Azure Databricks**, the other major Spark-based processing platform on Azure alongside Synapse Spark pools, covering its workspace/cluster model, Delta Lake, and notebook-driven development — including the detailed Databricks-vs-Synapse-Spark-pools comparison this section deferred (77.6/76.5.2) and how Data Factory's Databricks Notebook Activity fits together with the orchestration model just covered here.
