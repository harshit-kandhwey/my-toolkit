# Section 79 — Power BI

## 79.1 Definition

**Plain language:** Power BI is Microsoft's business intelligence and data visualization tool — it takes data from wherever it lives (a database, a data warehouse, a spreadsheet, a data lake) and turns it into interactive charts, dashboards, and reports that business users can explore themselves, without needing to write queries or understand the underlying data platform.

**Precise definition:** Power BI is a suite consisting of **Power BI Desktop** (a Windows authoring application for building data models and reports), the **Power BI Service** (the cloud platform, app.powerbi.com, for publishing, sharing, and collaborating on reports and dashboards), and **Power BI Mobile** apps, built around **datasets** (a data model — tables, relationships, and calculated measures defined in DAX) that **reports** (multi-page, interactive visualizations built against a dataset) and **dashboards** (single-page collections of pinned visuals, often pulled from multiple reports) are built on top of.

## 79.2 Why It Exists / Problem It Solves

Every service covered so far in this Part — ADLS Gen2 (Section 75), Synapse (Section 76), Data Factory (Section 77), Databricks (Section 78) — exists to get raw data ingested, processed, and modeled into a curated, business-ready form. None of them, on their own, put that data in front of the actual business stakeholders who need to make decisions from it: a sales director doesn't want to write a T-SQL query against a Synapse dedicated SQL pool, they want an interactive chart showing regional sales trends they can filter and drill into themselves. Power BI exists to close this "last mile" gap — connecting to the curated data this Part's other services produce and turning it into self-service, interactive reporting that business users consume directly, without needing any of the underlying data-engineering skill set. This is also why Power BI's positioning in this Part is deliberately the final consumption-layer step: it's the payoff that makes all the preceding ingestion, processing, and modeling work actually visible and useful to the organization.

## 79.3 Power BI Desktop vs. Power BI Service

### 79.3.1 The Division of Labor

**Definition:** Power BI Desktop is the authoring tool — where a report developer connects to data sources, builds the data model (tables, relationships, calculated columns and measures using DAX), and designs report visuals; the resulting `.pbix` file is then **published** to the Power BI Service, where it becomes a shared, centrally-managed asset that other users can view, interact with, and (with appropriate permissions) further build on.

### 79.3.2 Workspaces and the App Model

The Power BI Service organizes published content into **workspaces** — collaborative spaces where a team's datasets, reports, and dashboards live, with role-based access (Admin/Member/Contributor/Viewer) controlling who can edit vs. only view content. Content from one or more workspaces can be packaged and distributed to a broader audience as a **Power BI App** — a curated, read-optimized bundle of reports/dashboards distributed to end users who don't need workspace-editing access, directly separating the "people building reports" access tier from the much larger "people just consuming reports" audience.

## 79.4 DirectQuery vs. Import Mode

### 79.4.1 Import Mode

**Definition:** in Import mode, Power BI loads a copy of the source data directly into its own highly-compressed, in-memory analytical engine (the **VertiPaq** engine) at the time of data refresh — reports then query this in-memory copy, giving very fast query performance regardless of how the original data source is structured or performing, at the cost of data being only as fresh as the last scheduled refresh.

### 79.4.2 DirectQuery Mode

**Definition:** in DirectQuery mode, Power BI does not import or cache the data at all — every visual interaction (applying a filter, changing a chart's grouping) generates a live query sent directly to the underlying source system (a Synapse dedicated SQL pool, an Azure SQL Database, a Databricks SQL Warehouse) in real time, meaning report data is always current as of the moment it's viewed, at the cost of query performance being bounded by the underlying source system's own query performance and by network latency to it.

### 79.4.3 Choosing Between Them

| Factor                          | Favors Import                                                     | Favors DirectQuery                                                                     |
| ------------------------------- | ----------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Data freshness requirement      | Periodic refresh (hourly/daily) is acceptable                     | Genuinely real-time/near-real-time data is required                                    |
| Data volume                     | Fits comfortably in Power BI's in-memory capacity limits          | Very large datasets exceeding practical import size                                    |
| Source system query performance | Source is slow or not well-optimized for ad hoc BI query patterns | Source (e.g., a well-tuned Synapse dedicated SQL pool) can handle live query load well |
| Report interactivity            | Needs to feel instantaneous under heavy filtering/slicing         | Some latency on interaction is acceptable given the real-time trade-off                |

⚠️ Power BI also supports a **Composite model**, mixing Import and DirectQuery across different tables within the same report (e.g., importing a small, slowly-changing dimension table while DirectQuery-ing a huge, frequently-updated fact table) — exact capability boundaries and performance characteristics of composite models have evolved over time and should be verified against current documentation before relying on this pattern for a production report.

🎯 **Interview Tip:** a frequently tested nuance — DirectQuery's real-time-ness is not free: report interaction performance in DirectQuery mode is fundamentally bounded by the underlying source's query performance, meaning a poorly-tuned Synapse dedicated SQL pool distribution strategy (Section 76.3.2) or an under-provisioned Databricks SQL Warehouse (Section 78.3.2) will directly translate into a sluggish Power BI report experience — DirectQuery doesn't insulate report performance from the source system's own performance characteristics the way Import mode's cached, in-memory copy does.

## 79.5 DAX (Data Analysis Expressions)

**Definition:** DAX is Power BI's formula language for defining **calculated columns** (computed row-by-row and materialized into the data model) and **measures** (aggregations computed dynamically at query time, in the context of whatever filters/groupings are currently applied in a report) — measures are the more commonly used and more powerful construct for genuine BI reporting, since their calculation context automatically adapts to however a user is currently slicing the report, rather than being fixed at data-refresh time the way a calculated column is.

```dax
Total Sales YTD =
TOTALYTD(SUM(Sales[Amount]), 'Date'[Date])
```

This measure computes year-to-date total sales, automatically recalculating correctly whether a report visual is currently filtered to a specific region, product category, or time period — the defining characteristic of a measure versus a calculated column.

## 79.6 Integration with This Part's Other Services

### 79.6.1 Connecting to Synapse and Databricks

Power BI connects natively to Synapse dedicated SQL pools, Synapse serverless SQL pools, and Databricks SQL Warehouses as first-class data sources, supporting either Import (pulling a snapshot at refresh time) or DirectQuery (live querying) against any of them — this is the direct mechanism by which the curated/gold-zone data produced by Sections 76–78's processing engines actually reaches business users.

### 79.6.2 Connecting Directly to ADLS Gen2

Power BI can also connect directly to files in ADLS Gen2 (Section 75) — useful for smaller datasets or scenarios where standing up a full Synapse/Databricks query layer purely to expose data to Power BI isn't justified — though for larger, more complex curated datasets, querying through Synapse serverless SQL pools (Section 76.4) as an intermediate layer is generally preferable, since it provides SQL-based transformation/filtering capability before the data reaches Power BI, rather than requiring all of that logic to live inside the Power BI data model itself.

## 79.7 Row-Level Security (RLS)

**Definition:** Row-Level Security restricts which rows of data a given user sees within the same shared report, based on rules defined in the data model (e.g., a "Regional Manager" role defined to see only rows matching their assigned region) and the identity of the user viewing the report in the Power BI Service — allowing one report to be published once and shared broadly, while each viewer sees only the subset of data their role/identity permits, directly extending the least-privilege principle established for RBAC generally (Section 8) to the level of individual data rows within a shared BI asset.

## 79.8 Architecture Diagram

```
Power BI Desktop (authoring)
   │  build data model (DAX measures), design reports
   │  publish .pbix
   ▼
Power BI Service — Workspace
   ├── Dataset ──DirectQuery──▶ Synapse dedicated SQL pool (curated/gold)
   │         └──Import────────▶ Databricks SQL Warehouse (scheduled refresh)
   ├── Report (interactive visuals, RLS applied per viewer)
   └── Dashboard (pinned visuals across reports)
        │
        ▼
   Power BI App ──▶ distributed to broad business-user audience (view-only)
```

## 79.9 Configuration & Hands-On Example

Power BI report/dataset authoring is primarily a Desktop-application and Service-portal workflow rather than an `az` CLI-driven process, but workspace and capacity administration is scriptable via the Power BI REST API and PowerShell module:

```powershell
Connect-PowerBIServiceAccount

New-PowerBIWorkspace -Name "Sales Analytics Prod"

Add-PowerBIWorkspaceUser `
  -Id "<workspace-id>" `
  -UserEmailAddress "regional-manager@contoso.com" `
  -AccessRight Viewer
```

- **Purpose:** provisions a dedicated Power BI workspace for the sales analytics reporting content described in this section, and grants a business user Viewer access — the read-only role appropriate for report consumers rather than report authors.
- **Important arguments explained individually:**
  - `New-PowerBIWorkspace` — creates a "workspace v2" (the modern, Microsoft 365 group-backed workspace type); ⚠️ verify current cmdlet/API naming against official documentation, as Power BI's administrative surface has evolved over time.
  - `-AccessRight Viewer` — the workspace role granting read-only report/dashboard consumption without edit or dataset-modification rights, appropriate for the "much larger consuming audience" tier described in Section 79.3.2.
- **Common error:** granting broad Contributor/Member access to end users who only need to consume reports, rather than the more restrictive Viewer role or, more appropriately for a large consuming audience, distributing content via a Power BI App (79.3.2) instead of direct workspace access entirely — over-provisioned workspace access is a common and avoidable governance gap.

## 79.10 Production & Enterprise Usage

Enterprise Power BI deployments typically license **Power BI Premium** capacity (dedicated compute reserved for the organization, rather than shared/per-user licensing) once report volume, dataset size, or the number of consuming users grows large enough to justify it, enabling larger dataset sizes, more frequent scheduled refreshes, and features like paginated reports and deployment pipelines (a dev/test/prod content-promotion workflow directly analogous to the CI/CD promotion discipline established in Part 9). Content governance typically separates workspaces by business unit or reporting domain, with Row-Level Security (79.7) applied to any report containing data multiple business units share but shouldn't fully see across each other's boundaries, and Power BI Apps used to distribute finished reporting to broad audiences without granting workspace-editing access.

## 79.11 Security Considerations

- Use **Row-Level Security** (79.7) whenever a single shared dataset/report legitimately needs to restrict which rows different viewers see, rather than either publishing separate reports per audience (a maintenance burden) or granting everyone full visibility regardless of appropriate need-to-know.
- Grant the minimum necessary workspace role (Viewer for consumption, Contributor/Member only for those actually building reports) and prefer distributing finished content via **Power BI Apps** to broad audiences rather than direct workspace membership — directly applying least-privilege (Section 8.4) to BI content access.
- For DirectQuery connections to Synapse or Databricks, use **Entra ID single sign-on** so that the underlying source system's own row-level/column-level security and audit logging (where configured) apply consistently to the identity actually viewing the report, rather than all DirectQuery traffic appearing to originate from one shared service account.

## 79.12 Performance Considerations

Import-mode dataset refresh performance and report interactivity both benefit from **query folding** — ensuring transformation steps defined in Power Query (the data-preparation layer within Power BI) are pushed down and executed by the source system itself (e.g., a Synapse SQL pool) rather than pulled into Power BI and processed row-by-row locally, which is dramatically slower for large datasets. DirectQuery report performance, as noted in Section 79.4.3's Interview Tip, is fundamentally bounded by the underlying source system's own query performance — meaning DirectQuery report tuning is often really Synapse distribution-strategy tuning (Section 76.3.2) or Databricks SQL Warehouse sizing (Section 78.3.2) in disguise, not a Power-BI-side optimization at all.

## 79.13 Monitoring

The Power BI Service provides built-in **usage metrics** reports (views, unique viewers, refresh success/failure history per dataset) and, for Premium capacity, integrates with Azure Monitor (Part 10) for capacity-level metrics (memory/CPU utilization, query duration) — essential for identifying an over-subscribed Premium capacity before users start experiencing slow report load times, and for catching a silently-failing scheduled dataset refresh before a business user notices a report showing stale data.

## 79.14 Troubleshooting

| Symptom                                                            | Likely Cause                                                                                                                    | Fix                                                                                                                                                                             |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| DirectQuery report feels sluggish when users apply filters         | Underlying source system (Synapse SQL pool, Databricks SQL Warehouse) is slow to execute the live queries DirectQuery generates | Tune the source system directly (distribution strategy, cluster sizing) rather than only Power-BI-side settings, since DirectQuery performance is bounded by source performance |
| A regional manager can see other regions' data in a shared report  | Row-Level Security not configured, or RLS role/filter rule incorrectly defined                                                  | Review and correctly configure RLS roles and their DAX filter expressions; test using "View As Role" in Power BI Desktop before publishing                                      |
| Scheduled dataset refresh silently fails, and users see stale data | Source system credentials expired/rotated, gateway (for on-premises sources) offline, or refresh exceeding a time/size limit    | Review refresh history and failure details in the Service; verify gateway status and credentials; consider DirectQuery or incremental refresh for very large datasets           |

## 79.15 Interview Questions — Section 79

### 🎯 Intermediate

**Q: What's the fundamental trade-off between Import mode and DirectQuery mode in Power BI?**

_Model answer:_ Import mode loads a copy of the source data into Power BI's own in-memory engine at refresh time, giving very fast report interactivity regardless of the source system's own performance, at the cost of data only being as fresh as the last scheduled refresh. DirectQuery sends a live query to the underlying source system for every report interaction, so data is always current, but report performance is directly bounded by how fast the underlying source system can execute those queries — a poorly-tuned source system will make a DirectQuery report feel sluggish regardless of anything configured on the Power BI side.

_What the interviewer is probing:_ whether the candidate understands DirectQuery isn't a free "always fast and always fresh" option — it's a genuine trade-off, with performance dependent on the source system, not something Power BI insulates the user from.

### 🎯 Senior/Architect

**Q: A finance team wants a single shared Power BI report giving regional managers visibility into their own region's numbers only, while the VP of Finance sees all regions, sourced from a Synapse dedicated SQL pool with data refreshed nightly. Design the reporting setup.**

_Model answer:_ Given nightly refresh is acceptable and no real-time requirement is stated, I'd use Import mode rather than DirectQuery, since Import gives faster, more consistent report interactivity for the many regional managers likely querying it during business hours, and a nightly scheduled refresh comfortably meets the stated freshness requirement without needing to bound performance to the Synapse dedicated SQL pool's live query capacity. I'd implement Row-Level Security in the data model, defining a role tied to each region (or a dynamic RLS pattern mapping each viewer's Entra ID identity to their assigned region via a mapping table) so that regional managers only see their own region's rows, while the VP of Finance is assigned an "all regions" role or excluded from RLS filtering entirely — all from a single published report and dataset, rather than maintaining separate per-region report copies. I'd publish this to a dedicated Finance workspace, distribute it to the regional managers and the VP via a Power BI App (rather than direct workspace membership, since none of them need to edit the report), and grant only the report-authoring team actual Contributor access to the workspace itself. If the organization's report/dataset volume or user count is large enough, I'd also recommend Premium capacity to support the nightly refresh reliably at scale and enable deployment pipelines for promoting report changes through dev/test/prod, consistent with this roadmap's general IaC/CI-CD promotion discipline.

_What the interviewer is probing:_ the ability to design a complete, realistic BI access-control scenario combining the correct storage-mode choice (justified by the stated freshness requirement), Row-Level Security for the differentiated-visibility requirement, and appropriate workspace/App distribution governance — rather than treating "just build the report" as sufficient without addressing the differentiated-access requirement explicitly stated in the scenario.

## 79.16 Common Misconceptions

- **"DirectQuery is always the better choice since it's always real-time."** False — DirectQuery report performance is bounded by the underlying source system's own query performance; Import mode is often the better choice when periodic refresh is acceptable, for both performance and cost reasons.
- **"Row-Level Security requires publishing separate reports per audience."** False — RLS lets a single shared report and dataset restrict visible rows per viewer based on role/identity, avoiding the maintenance burden of separate report copies per audience.
- **"Power BI is only a Desktop application for building reports."** False — Power BI Desktop is the authoring tool, but the Power BI Service (workspaces, Apps, scheduled refresh, RLS enforcement, Premium capacity) is where published content is actually managed, shared, and governed for an organization.

## 79.17 Key Takeaways

- 🔑 Power BI is the consumption-layer BI tool that turns this Part's curated data (from Synapse, Databricks, ADLS Gen2) into interactive reports and dashboards for business users, via Power BI Desktop (authoring) and the Power BI Service (publishing/sharing/governance).
- 🔑 Import mode caches data in-memory for fast, consistent report performance at the cost of refresh-interval freshness; DirectQuery queries the source live for real-time freshness at the cost of performance being bounded by the source system.
- 🔑 Row-Level Security lets one shared report/dataset restrict visible rows per viewer's role/identity, avoiding the need for separate per-audience report copies.
- 🔑 DAX measures (not calculated columns) are the primary tool for context-aware aggregations that correctly adapt to however a report is currently filtered/sliced.
- 🔑 Power BI Apps are the appropriate distribution mechanism for a broad, view-only consuming audience, keeping workspace-editing access restricted to actual report authors.

## 79.18 Related Concepts (Next Up)

Section 80 covers **Azure Cognitive Search (Azure AI Search)**, which complements the reporting/BI consumption pattern just covered with a different consumption shape entirely — full-text and vector search over data, rather than aggregated visual reporting — including how it indexes data from Cosmos DB, ADLS Gen2, and other sources this Part has already covered.
