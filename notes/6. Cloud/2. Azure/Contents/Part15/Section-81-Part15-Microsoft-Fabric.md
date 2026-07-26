# Section 81 — Microsoft Fabric

## 1. Definition

**Plain language:** Microsoft Fabric is Microsoft's newer, unified, all-in-one SaaS data platform — an attempt to take everything covered so far in this Part (data lake storage, data warehousing, big-data Spark processing, pipeline orchestration, and BI reporting) and offer it as one product, with one underlying storage layer, one set of workspaces, and one licensing/capacity model, rather than as the collection of separately-provisioned services (Synapse, Data Factory, Power BI) this Part has covered individually so far.

**Precise definition:** Microsoft Fabric is a Software-as-a-Service analytics platform built around **OneLake** (a single, tenant-wide, ADLS Gen2-compatible logical data lake underlying every Fabric workload) and a set of converged **experiences** — **Data Factory** (pipeline orchestration, functionally descended from Section 77's standalone Data Factory), **Synapse Data Engineering** (Spark-based processing, descended from Section 76's Spark pools), **Synapse Data Warehouse** (SQL-based warehousing, descended from Section 76's dedicated SQL pools), **Lakehouse** (a converged storage/compute construct combining data-lake file storage with SQL-queryable table structure over the same underlying data), and **Power BI** (reporting, the same product covered in Section 79, now natively integrated as a first-class Fabric experience) — all reading and writing against the shared OneLake, provisioned and billed through a single **Fabric capacity**.

## 2. Why It Exists / Problem It Solves

Sections 75–80 of this Part described a real, common architectural pattern: an ADLS Gen2 data lake, a Synapse workspace for warehousing/Spark, a standalone (or Synapse-embedded) Data Factory-style orchestration layer, and Power BI for reporting, all wired together as genuinely separate resources — each independently provisioned, each with its own billing/capacity model, and each requiring explicit configuration to talk to the others (linked services, connection strings, separately-configured network boundaries). This works, and remains a fully valid, widely deployed architecture, but it does require a data platform team to provision, secure, and operate several genuinely distinct Azure resources as one coherent system. Microsoft Fabric exists to offer an alternative: rather than assembling this same set of capabilities from separately-provisioned services, Fabric bundles equivalent capabilities into one SaaS product with one shared storage layer (OneLake) that every experience reads/writes natively, one workspace model, and one capacity-based billing unit — the same underlying problem-solving capability this Part has built up piece by piece, offered instead as a single, pre-integrated product.

This is explicitly a consolidation and simplification play, not a wholesale replacement of the underlying technology: Fabric's Data Factory experience is directly descended from Data Factory/Synapse Pipelines (Section 77), its Data Engineering experience is directly descended from Synapse Spark pools (Section 76.5), its Data Warehouse experience is directly descended from Synapse dedicated SQL pools (Section 76.3), and Power BI is the same product covered in Section 79 — meaning everything learned about these individual capabilities in Sections 76–79 transfers directly to understanding what Fabric's corresponding experience actually does under the hood.

## 3. OneLake

### 3.1 Definition

**Plain language:** OneLake is Fabric's answer to "which data lake do all these different tools actually read from" — instead of every workspace or project provisioning its own separate ADLS Gen2 account (as Sections 75–80's architecture would), OneLake provides a single, logical, tenant-wide data lake that every Fabric workspace and item (Lakehouses, Warehouses, and other Fabric artifacts) stores its data within, organized hierarchically by workspace and item rather than by separately-provisioned storage accounts.

**Precise definition:** OneLake is a single, ADLS Gen2-API-compatible logical data lake automatically provisioned once per Fabric tenant, structured as a hierarchy of workspaces and the items (Lakehouses, Warehouses, KQL databases) within them, each of which stores its underlying data as files (typically Delta Lake-formatted Parquet, directly reusing the Delta Lake concepts introduced in Section 78.4) within this shared logical lake — meaning any tool capable of speaking the ADLS Gen2 API can, in principle, read and write OneLake data directly, the same way it would against a standalone ADLS Gen2 account.

### 3.2 Shortcuts — Referencing External Data Without Copying It

**Definition:** a **Shortcut** is a OneLake feature creating a reference to data stored elsewhere — another location within OneLake, an external ADLS Gen2 account, or (per current documentation) certain other cloud providers' storage — that makes the referenced data appear and behave as if it were natively stored within OneLake, without physically copying it. This directly addresses one of the most common practical objections to a "one big unified lake" model: an organization with substantial existing data already in a standalone ADLS Gen2 account (Section 75) isn't forced to duplicate that data into OneLake before Fabric's tools can use it — a Shortcut lets Fabric experiences query it in place.

⚠️ Exact Shortcut source-type support (which external systems/clouds can be referenced) and any performance or consistency caveats versus natively-stored OneLake data evolve quickly — verify current capability against official documentation before relying on Shortcuts for a production architecture decision.

## 4. Lakehouse and Warehouse

### 4.1 Lakehouse

**Definition:** a Fabric **Lakehouse** is an item combining data-lake-style file storage (Delta Lake-formatted files, directly queryable by Spark notebooks, mirroring the Databricks/Synapse Spark pattern from Sections 76.5/78) with an automatically-maintained **SQL analytics endpoint** exposing the same underlying Delta tables for T-SQL querying — meaning the same physical data is simultaneously accessible as Spark DataFrames for engineering/ML workloads and as SQL tables for analyst/BI workloads, without requiring an explicit ETL step to move data between a "lake" representation and a "warehouse" representation.

### 4.2 Warehouse

**Definition:** a Fabric **Warehouse** is a full T-SQL data warehouse item, more directly analogous to a Synapse dedicated SQL pool (Section 76.3) — supporting full transactional T-SQL (including multi-table transactions Lakehouse's SQL endpoint doesn't support), with its data also stored as Delta Lake tables within OneLake, meaning Warehouse data is likewise directly readable by Spark or other OneLake-aware tools without an export step.

### 4.3 The Blurred Line

🎯 **Interview Tip:** a frequently tested nuance in Fabric-specific interview questions — the Lakehouse-vs-Warehouse choice in Fabric is a genuinely different decision from the dedicated-vs-serverless SQL pool decision in classic Synapse (Section 76.8), because both Fabric items store data in the same Delta Lake format within the same OneLake, and both are simultaneously Spark- and SQL-queryable to varying degrees — the real distinguishing factor is whether the workload needs full multi-table transactional T-SQL semantics (favoring Warehouse) versus primarily Spark-engineering-driven work with secondary SQL querying needs (favoring Lakehouse), not a storage-format or fundamental data-location difference the way choosing between Synapse's genuinely separate dedicated and serverless pool storage models was.

## 5. How Fabric Relates to Synapse, Data Factory, and Power BI

| Classic Azure Service (Sections 76–79) | Corresponding Fabric Experience                                     |
| -------------------------------------- | ------------------------------------------------------------------- |
| Synapse dedicated SQL pool             | Fabric Data Warehouse                                               |
| Synapse serverless SQL pool            | Lakehouse SQL analytics endpoint                                    |
| Synapse Spark pools                    | Data Engineering (Fabric Spark notebooks)                           |
| Azure Data Factory / Synapse Pipelines | Fabric Data Factory                                                 |
| ADLS Gen2 (standalone account)         | OneLake (with Shortcuts referencing existing ADLS Gen2 data)        |
| Power BI                               | Power BI (same product, natively integrated as a Fabric experience) |

🔑 **Key framing:** Fabric is not a sixth, unrelated service added on top of Sections 76–80 — it is Microsoft's current effort to converge those same underlying capabilities under one SaaS product and one shared storage layer. Understanding Sections 76–79 in depth is directly transferable to understanding what each Fabric experience does; the genuinely new material is OneLake as a shared storage layer and the unified capacity/licensing model.

## 6. Maturity Caveats

⚠️ **This is an actively, rapidly evolving product.** Microsoft Fabric was a comparatively recent addition to Azure's data platform lineup relative to Synapse, Data Factory, and Power BI (all long-established, mature services), and both its feature set and its guidance on when to choose Fabric versus the classic Synapse/ADF/Power BI architecture continue to change quickly. Specific claims that should be independently verified against current official documentation before being relied on for an architectural decision or an interview answer include: exact feature parity (or gaps) between Fabric's Warehouse/Lakehouse items and classic Synapse dedicated/serverless SQL pools; Shortcut support for external and multi-cloud sources; Fabric capacity SKU sizing and pricing; and Microsoft's current official positioning on whether new data platform projects should default to Fabric or to the classic Synapse-based architecture. Treat any specific numeric or feature-availability claim about Fabric in this section as illustrative of the concepts rather than a currently-guaranteed fact.

## 7. Architecture Diagram

```
Microsoft Fabric Tenant
┌───────────────────────────────────────────────────────┐
│                        OneLake                           │
│   (single logical data lake, Delta Lake-formatted)        │
│                                                            │
│   Workspace: "Sales Analytics"                             │
│   ├── Lakehouse (Spark + SQL endpoint, Delta tables)        │
│   ├── Warehouse (full T-SQL, Delta tables)                  │
│   ├── Data Factory pipeline (orchestration)                 │
│   └── Power BI report/dataset (DirectQuery to Lakehouse/     │
│        Warehouse, or Import)                                 │
│                                                            │
│   Shortcut ──▶ external ADLS Gen2 account (Section 75)      │
│               (referenced, not copied)                       │
└───────────────────────────────────────────────────────────┘
                All billed through one Fabric Capacity
```

## 8. Configuration & Hands-On Example

Fabric workspace and item creation is primarily driven through the Fabric portal (app.fabric.microsoft.com) and its REST APIs rather than the classic `az` CLI, reflecting its SaaS-first delivery model distinct from most other services covered in this roadmap:

```bash
# Fabric capacity is provisioned as an Azure resource (billing/scaling unit)
az resource create \
  --resource-group rg-data-platform \
  --name fabriccap-analytics-prod \
  --resource-type "Microsoft.Fabric/capacities" \
  --properties '{"sku": {"name": "F64"}, "administration": {"members": ["admin@contoso.com"]}}'
```

- **Purpose:** provisions the underlying Fabric capacity — the billing and compute-scaling unit that Fabric workspaces are assigned to — as an Azure resource, even though the workspaces, Lakehouses, and pipelines built on top of it are created through the Fabric portal/API rather than `az`.
- **Important arguments explained individually:**
  - `sku.name` — Fabric capacity SKUs (e.g., `F64`) determine available compute capacity shared across every workspace assigned to it; ⚠️ exact SKU sizing, naming, and pricing should be verified against current official documentation given this is one of the fastest-changing aspects of the product.
- **Common error:** assuming Fabric items (Lakehouses, Warehouses, pipelines) can be fully provisioned via the same `az` CLI patterns used for Synapse/Data Factory in Sections 76–77 — Fabric's item-level authoring is portal/API-driven as a SaaS product, with `az`/ARM scope limited primarily to the underlying capacity resource itself; teams expecting full IaC parity with classic Synapse should verify current Fabric API/Terraform-provider support before committing to that operational model.

## 9. Production & Enterprise Usage

Organizations already deeply invested in Synapse, standalone Data Factory, and Power BI (Sections 76–79) as separately-provisioned services generally evaluate Fabric as a forward-looking consolidation option rather than an urgent migration — given the classic architecture remains fully supported and is the more mature, better-documented, and more IaC-friendly option as of any given point in this product's fast-evolving lifecycle. Organizations starting a genuinely new data platform from scratch, particularly smaller teams wanting to minimize the number of separately-provisioned and separately-secured Azure resources, are a more natural fit for evaluating Fabric first, given its single-capacity billing and OneLake's elimination of needing to separately provision and network-secure an ADLS Gen2 account, a Synapse workspace, and a Data Factory instance as distinct resources.

## 10. Security Considerations

- Fabric workspace access and item-level permissions are managed through the Fabric portal's own workspace-role model (broadly analogous to Power BI's workspace roles, Section 79.3.2, now extended across all Fabric item types), layered on top of Entra ID identity — the same identity foundation (Part 2) underlying every other service in this roadmap.
- OneLake data governance increasingly relies on Microsoft Purview integration for tenant-wide data discovery, classification, and lineage across Fabric items — directly extending the compliance/classification concerns from Section 58 to a unified data estate.
- Because OneLake is tenant-wide by default, workspace-level and item-level access boundaries are the primary control for keeping different business units' or teams' data appropriately separated within what is architecturally a single shared logical lake — a materially different default posture from provisioning entirely separate ADLS Gen2 accounts per team (Section 75.9), requiring deliberate attention to workspace/item permission boundaries specifically because the underlying storage is unified rather than physically separated.

## 11. Performance Considerations

Because Lakehouse and Warehouse items both store data as Delta Lake tables within OneLake, the same file-size/compaction and data-layout guidance already established for Delta Lake generally (Section 78.4.3, `OPTIMIZE`/`ZORDER`) applies directly to Fabric Lakehouse and Warehouse performance tuning — this is a direct, practical benefit of Fabric's underlying format consolidation, since a data engineer's Delta Lake tuning knowledge from working with Synapse or Databricks transfers without needing to learn a separate Fabric-specific optimization model.

## 12. Monitoring

Fabric provides a **Capacity Metrics** app (a Power BI-based monitoring app specifically for Fabric capacity utilization) tracking compute consumption across every workspace and item assigned to a capacity, plus integration with Azure Monitor for capacity-level Azure resource metrics — essential given Fabric's shared-capacity billing model means one workspace's heavy usage can affect the performance available to every other workspace sharing that same capacity, a materially different monitoring concern from classic Synapse/Data Factory's per-resource, independently-scaled billing model.

## 13. Troubleshooting

| Symptom                                                                                                                       | Likely Cause                                                                                                                                                                       | Fix                                                                                                                                                                                                                                |
| ----------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| One workspace's heavy query load is degrading performance for other workspaces on the same Fabric capacity                    | Shared capacity model means all assigned workspaces draw from the same compute pool                                                                                                | Review the Capacity Metrics app for the actual consuming workload; consider a separate/larger capacity for heavy workloads                                                                                                         |
| Data referenced via a Shortcut appears stale or inconsistent                                                                  | Shortcut-referenced external source updated in a way not yet reflected, or the specific source type has documented consistency caveats                                             | Verify current Shortcut consistency/refresh behavior for the specific source type against official documentation                                                                                                                   |
| Team expected to provision Fabric items (Lakehouses, pipelines) via Bicep/Terraform the same way as classic Synapse resources | Fabric's item-level authoring is primarily portal/API-driven; IaC support for Fabric items specifically is comparatively newer and narrower than for classic Synapse/ADF resources | Verify current Fabric REST API/Terraform provider coverage for the specific item types needed; provision the underlying capacity via IaC and items via the Fabric API/portal in the interim if full IaC parity isn't yet available |

## 14. Interview Questions — Section 81

### 🎯 Intermediate

**Q: What is OneLake, and how does it change the relationship between storage and compute compared to the classic Synapse/ADLS Gen2 architecture?**

_Model answer:_ OneLake is a single, tenant-wide, ADLS Gen2-compatible logical data lake automatically provisioned once per Fabric tenant, that every Fabric workspace and item (Lakehouses, Warehouses) stores its data within, rather than each workspace or project provisioning its own separate ADLS Gen2 account the way the classic Synapse architecture requires. This means Fabric's various experiences — Data Engineering, Data Warehouse, Power BI — all read and write against one shared logical storage layer by default, with Shortcuts available to reference existing external data (including standalone ADLS Gen2 accounts) without physically copying it in, whereas the classic architecture requires explicitly wiring together a separately-provisioned ADLS Gen2 account, Synapse workspace, and Data Factory instance via linked services.

_What the interviewer is probing:_ understanding that OneLake's core value is storage consolidation and simplified integration between tools, not a fundamentally new storage technology — and that Shortcuts specifically address the "we already have data elsewhere" concern.

### 🎯 Senior/Architect

**Q: A company already has a mature Synapse workspace, standalone Data Factory, and Power BI reporting in production. A director asks whether they should migrate to Microsoft Fabric. How do you advise them?**

_Model answer:_ I'd frame this as a consolidation and simplification opportunity rather than an urgent necessity, since the existing Synapse/Data Factory/Power BI architecture remains fully supported and, being more established, is currently better documented and has broader IaC tooling support than Fabric's newer item types. I'd recommend against a wholesale, disruptive migration purely to be on the newer platform, and instead suggest evaluating Fabric specifically for net-new projects or workloads first, to build genuine team familiarity with OneLake, Lakehouses, and Fabric's capacity model at lower risk before considering migrating the existing production estate. If the underlying motivation is reducing the operational overhead of managing several separately-provisioned resources (a standalone ADLS Gen2 account, a Synapse workspace, a Data Factory instance, each independently secured and network-configured), I'd note that's a legitimate and real benefit Fabric's OneLake and single-capacity model directly addresses — but I'd also flag, given how quickly this product area evolves, that any specific migration plan needs its feature-parity assumptions (particularly around Warehouse's transactional T-SQL completeness versus their existing dedicated SQL pool workloads, and current IaC/Terraform support for Fabric items) explicitly re-verified against current documentation immediately before committing to a timeline, rather than planned against this section's or any other historical reference's specific claims.

_What the interviewer is probing:_ balanced, non-hype-driven judgment about adopting a genuinely still-maturing platform for an already-working production system, and the specific discipline of flagging fast-changing product claims for re-verification rather than treating any point-in-time description of Fabric as a stable, durable fact — directly reinforcing the ⚠️ verification theme this roadmap applies throughout to fast-evolving Azure services.

## 15. Common Misconceptions

- **"Microsoft Fabric is an entirely new technology unrelated to Synapse, Data Factory, and Power BI."** False — Fabric's experiences are directly descended from and functionally correspond to those existing services (81.5); understanding those services transfers directly to understanding Fabric.
- **"OneLake requires migrating/copying all existing ADLS Gen2 data into it before Fabric tools can use it."** False — Shortcuts let Fabric experiences reference existing external data (including standalone ADLS Gen2 accounts) in place, without physical copying.
- **"Fabric is now the mandatory, universally-recommended replacement for classic Synapse."** False (as of any point-in-time assessment) — the classic Synapse/Data Factory/Power BI architecture remains fully supported and viable; Fabric adoption is a deliberate architectural choice to evaluate, not an assumed migration path, and current Microsoft guidance on this specific point should always be independently verified.

## 16. Key Takeaways

- 🔑 Microsoft Fabric converges Synapse (SQL pools, Spark pools), Data Factory, and Power BI into one SaaS product built around OneLake, a single tenant-wide logical data lake, and one capacity-based billing/scaling unit.
- 🔑 Fabric's Data Factory, Data Engineering, Data Warehouse, and Power BI experiences functionally correspond to Sections 76–79's classic services — existing knowledge of those services transfers directly.
- 🔑 Lakehouse and Warehouse both store data as Delta Lake tables in OneLake; the choice between them hinges on whether full multi-table transactional T-SQL is required (Warehouse) versus primarily Spark-engineering work with secondary SQL access (Lakehouse).
- 🔑 Shortcuts let OneLake reference external data (including existing ADLS Gen2 accounts) without physically copying it, directly addressing migration/adoption friction.
- 🔑 Fabric is a fast-evolving product — specific feature-parity, pricing, and IaC-support claims should always be re-verified against current official documentation before an architectural decision, more so than for this roadmap's longer-established services.

## 17. Related Concepts (Next Up)

Section 82 steps back from individual services to cover **Data Architecture Patterns** directly — the lakehouse architecture, the medallion (bronze/silver/gold) pattern introduced in Section 75.5 and deepened via Section 78.4's Delta Lake material, and batch-vs-streaming ETL/ELT trade-offs — providing the decision framework for choosing among every service this Part has covered (ADLS Gen2, Synapse, Data Factory, Databricks, Power BI, Azure AI Search, and Fabric) for a given real-world workload.
