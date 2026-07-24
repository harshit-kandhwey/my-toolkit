# Section 33 — Data Migration & Azure Database Migration Service

## 33.1 Definition

**Plain language:** Moving an existing database — whether from on-premises, another cloud, or one Azure database type to another — into one of the Azure database services covered in this Part is its own specialized task, with its own tools and challenges around minimizing downtime and ensuring data integrity. Azure Database Migration Service (DMS) is Microsoft's purpose-built tool for this.

**Precise definition:** Azure Database Migration Service (DMS) is a fully managed service that facilitates database migrations from various source database engines (SQL Server, PostgreSQL, MySQL, MongoDB, Oracle, and others) to corresponding Azure database targets, supporting both one-time (offline) migrations and continuous, minimal-downtime (online) migrations that keep the source and target synchronized until a final cutover.

## 33.2 Why It Exists / Problem It Solves

Every database service covered in this Part (Azure SQL Database/Managed Instance, Cosmos DB, PostgreSQL/MySQL) is only useful to an organization with existing data if that data can actually be moved there reliably — and database migration is genuinely difficult to do well: naive approaches (a simple backup/restore, or a bulk export/import) typically require significant application downtime while the migration completes, risk data loss or corruption if not handled carefully, and don't easily handle the reality that source data often continues changing during the migration window itself. DMS exists specifically to address these challenges in a managed, purpose-built way — particularly by supporting online migrations that keep a continuously-updated target in sync with the still-active source database, allowing the actual cutover (the moment the application switches from the old database to the new one) to happen with minimal downtime, rather than requiring the source to be taken fully offline for the entire migration duration.

## 33.3 Core Concepts

### 33.3.1 Offline vs. Online Migration

- **Offline Migration** — the source database is taken offline (or at minimum, write access is stopped) for the duration of the migration; data is copied once, and the application cuts over to the new target only after the migration completes. Simpler to execute and reason about, but requires a maintenance window sized to the full migration duration, which can be substantial for large databases.
- **Online Migration** — the source database remains fully operational and continues accepting writes throughout the migration; DMS performs an initial full data copy, then continuously applies ongoing changes from the source to the target (via change-data-capture-style mechanisms specific to the source engine) until the target is caught up and closely synchronized, at which point a brief, final cutover (stopping the source, applying any last remaining changes, and redirecting the application to the new target) completes the migration with dramatically less downtime than an offline approach.

💡 **Tip:** Online migration is generally preferred for any production database where extended downtime isn't acceptable, but it requires more careful planning (the source engine must support the specific change-tracking mechanism DMS relies on for continuous sync) and a more involved cutover procedure than offline migration's comparatively simple "stop, copy, restart" approach.

### 33.3.2 Migration Assessment

Before migrating, DMS (and related Microsoft tooling like the **Azure Migrate** and specific engine-focused assessment tools) can perform a **compatibility assessment** against the source database, identifying features, syntax, or configurations used by the source that aren't supported (or behave differently) in the target Azure service — surfacing potential migration blockers or required application changes **before** the migration is attempted, rather than discovering them mid-migration or, worse, after cutover when the application unexpectedly breaks.

**Why this connects directly to earlier sections:** This assessment step is precisely what would surface issues like the PostgreSQL extension compatibility gap discussed in Section 31.3.3, or the instance-level feature dependency (cross-database queries, SQL Agent) discussed in Section 29.4.3 that would push a SQL Server migration toward Managed Instance rather than Azure SQL Database — a thorough upfront assessment is what makes an informed target-service decision possible, rather than choosing a target first and discovering incompatibilities later.

### 33.3.3 Source and Target Combinations

DMS supports a range of source-to-target combinations aligned with the database services covered throughout this Part, including (illustrative, not exhaustive): SQL Server (on-premises or another cloud) to Azure SQL Database or Managed Instance; PostgreSQL/MySQL (on-premises, another cloud, or a different managed provider) to the corresponding Azure Database for PostgreSQL/MySQL service; and MongoDB to Cosmos DB's MongoDB API (Section 30.3.1). ⚠️ The exact current list of supported source engines, versions, and corresponding target combinations should always be verified against official documentation before planning a specific migration, since this compatibility matrix is actively maintained and expanded over time.

### 33.3.4 Schema and Data Migration Phases

A typical migration project, whether using DMS directly or in combination with complementary tools, generally proceeds through distinguishable phases: **schema migration** (recreating the source database's table structures, indexes, constraints, and other schema objects on the target — sometimes requiring translation/adaptation if migrating between different database engines, such as SQL Server to PostgreSQL, which is a meaningfully more complex "heterogeneous" migration than a same-engine "homogeneous" migration like SQL Server to Azure SQL Database), **initial data load** (the bulk copy of existing data), and, for online migrations, **continuous synchronization** until cutover.

⚠️ **Heterogeneous migrations** (migrating between fundamentally different database engines, e.g., Oracle to Azure SQL Database, or SQL Server to PostgreSQL) are meaningfully more complex than **homogeneous migrations** (same engine, e.g., on-premises SQL Server to Azure SQL Managed Instance) — schema and even query/stored-procedure logic often require substantial translation and testing when engines differ, and this added complexity should be planned for explicitly rather than assumed to be a comparably simple undertaking to a same-engine migration.

## 33.4 Architecture Diagram — Online Migration Flow

```
Source Database (on-premises SQL Server, still actively serving the application)
   │
   ▼
Azure Database Migration Service
   │
   ├── Phase 1: Schema Migration
   │      — recreate tables, indexes, constraints on the target
   │
   ├── Phase 2: Initial Data Load
   │      — bulk copy existing data to the target
   │
   ├── Phase 3: Continuous Synchronization (Online Migration only)
   │      — ongoing changes on the source are continuously replicated
   │        to the target, keeping it closely in sync while the
   │        source remains live and actively serving the application
   │
   ▼
Cutover (brief, planned downtime window)
   — stop writes to source, apply final remaining changes to target,
     redirect application connection strings to the new target,
     resume application traffic against Azure SQL Database/Managed Instance

Target Database (Azure SQL Database / Managed Instance)
```

## 33.5 Configuration & Hands-On Example

**High-level DMS project setup (conceptual — full setup involves substantial prerequisite configuration):**

```bash
az dms create \
  --resource-group rg-migration \
  --name dms-sqlmigration \
  --location eastus \
  --sku-name Premium_4vCores

az dms project create \
  --resource-group rg-migration \
  --service-name dms-sqlmigration \
  --name proj-onprem-to-azuresql \
  --source-platform SQL \
  --target-platform SQLDB \
  --location eastus
```

- **Purpose:** Creates a DMS instance (the underlying compute resource performing the migration work) and a migration project targeting an on-premises SQL Server source and Azure SQL Database target — the first infrastructure steps in what's typically a substantially larger, multi-step migration project.
- ⚠️ A real DMS migration additionally requires network connectivity configuration (DMS typically needs network access to both the source database and the target, often via VPN Gateway or ExpressRoute, Section 26, if the source is on-premises), source database prerequisite configuration (such as enabling specific change-tracking mechanisms for online migration), and a defined cutover plan — this illustrative command sequence represents only the initial resource-creation step, not a complete migration runbook; always follow current official migration guides for the specific source/target combination in use.
- **Production usage note:** Given the complexity and risk involved, production database migrations are typically preceded by one or more test migrations against non-production copies of the source data, validating both the migration process itself and the target application's correct functioning against the migrated schema/data before ever attempting the production cutover.

## 33.6 Production & Enterprise Usage

Enterprises undertaking database migrations as part of a broader cloud adoption or modernization initiative typically begin with the compatibility assessment phase (Section 33.3.2) across their full database estate, using the findings to inform not just migration feasibility but the actual target-service decision itself (e.g., discovering an application's heavy reliance on SQL Server Agent jobs during assessment might redirect the target choice from Azure SQL Database to Managed Instance, connecting directly back to the decision framework established in Section 29.4.3). Large-scale enterprise migrations commonly run many individual database migrations in parallel or in planned waves, prioritized by business criticality, complexity, and risk tolerance — often migrating lower-risk, less-critical databases first to build organizational confidence and refine the migration process before tackling the most business-critical systems.

## 33.7 Security Considerations

- Migration projects necessarily involve data flowing between source and target, often across a network boundary (on-premises to Azure) — this traffic should be secured appropriately (via the hybrid connectivity mechanisms covered in Section 26, and encryption in transit), particularly for migrations involving sensitive or regulated data.
- Credentials used by DMS to access both source and target databases should follow least-privilege principles, scoped specifically to what the migration process requires, and should be securely managed (ideally via Key Vault, Section 56) rather than embedded directly in migration configuration.
- Post-migration, a formal decommissioning plan for the source database (once the target is validated and confirmed stable) should account for any data-retention or compliance requirements that might require the source's data (or the source system itself) to remain available or recoverable for some defined period, rather than being immediately and permanently deleted upon cutover.

## 33.8 Performance Considerations

Migration duration — particularly for the initial data load phase — depends heavily on database size, available network bandwidth between source and target (making a high-bandwidth connectivity option like ExpressRoute, Section 26, valuable for large on-premises-to-Azure migrations), and the DMS instance's own provisioned compute tier; migration timelines should be estimated based on realistic bandwidth and data-volume calculations rather than optimistic assumptions, since underestimating migration duration can create significant project-planning and stakeholder-expectation problems.

## 33.9 Monitoring

DMS provides migration progress tracking (schema migration status, initial load progress, ongoing synchronization latency for online migrations) throughout the process, essential both for project management visibility and, specifically for online migrations, for determining when the target has caught up closely enough with the source to safely proceed with cutover — cutting over while the target is still meaningfully behind the source risks data loss or inconsistency.

## 33.10 Troubleshooting

| Symptom                                                                               | Likely Cause                                                                                                             | Fix                                                                                                                                                                                      |
| ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Migration compatibility assessment reveals unsupported source features                | Application relies on features/syntax not supported by the chosen target service                                         | Reconsider target service choice (e.g., Managed Instance instead of Azure SQL Database) or plan required application changes before proceeding                                           |
| Online migration's continuous synchronization never seems to catch up with the source | Source database write volume exceeds the rate DMS can replicate changes to the target, or a network bandwidth constraint | Review network bandwidth between source and target; consider a higher DMS compute tier; investigate whether source write volume could be temporarily reduced during the migration window |
| Post-cutover application errors reveal missed schema objects or data                  | Incomplete schema migration, or a heterogeneous migration's translation gaps not caught during pre-migration testing     | This underscores the importance of thorough test migrations and validation against non-production data before production cutover, rather than skipping this step under time pressure     |

## 33.11 Interview Questions — Section 33

### 🎯 Intermediate

**Q: What's the key advantage of an online migration over an offline migration, and what added complexity does it introduce?**

_Model answer:_ An online migration keeps the source database fully operational throughout most of the migration process, continuously synchronizing ongoing changes to the target, so the actual application downtime is limited to a brief final cutover window rather than the full migration duration required by an offline approach. This is a significant advantage for production databases where extended downtime isn't acceptable. The added complexity is that online migration requires the source engine to support an appropriate change-tracking/replication mechanism DMS can use for continuous synchronization, requires more careful cutover planning (ensuring the target has sufficiently caught up before cutover), and is generally a more involved process to set up and monitor correctly compared to offline migration's simpler stop-copy-restart approach.

_What the interviewer is probing:_ understanding of the fundamental downtime-versus-complexity trade-off between the two migration approaches, and awareness that online migration isn't simply "strictly better" without any added considerations.

### 🎯 Senior/Architect

**Q: How would you plan a large-scale enterprise migration involving dozens of databases across SQL Server, PostgreSQL, and MongoDB, migrating to their respective Azure equivalents?**

_Model answer:_ I'd begin with a comprehensive compatibility assessment across the full database estate, identifying for each database any instance-level feature dependencies, unsupported extensions, or engine-specific behaviors that would influence the target service choice (e.g., SQL Server databases relying on cross-database queries pointing toward Managed Instance rather than Azure SQL Database, per the decision framework from Section 29.4.3) — this assessment phase directly informs which specific target each database should migrate to, rather than assuming a single target choice applies uniformly across the whole estate. I'd then group databases into migration waves based on business criticality, complexity, and risk — starting with lower-risk, less business-critical databases to validate and refine the migration process and tooling before tackling the most critical, highest-risk systems, building organizational confidence and surfacing process gaps early when the consequences of a mistake are lower. For each wave, I'd favor online migration wherever the source engine and network connectivity support it, minimizing downtime for production systems, while reserving offline migration for genuinely lower-criticality databases where a planned downtime window is acceptable and the reduced setup complexity is worth the trade-off. Throughout, I'd insist on test migrations against non-production data and full application validation against the migrated target before any production cutover, and would ensure adequate network bandwidth (potentially via ExpressRoute for substantial on-premises data volumes) is provisioned given how directly migration duration depends on available bandwidth for the initial data load phase.

_What the interviewer is probing:_ whether the candidate can design a genuinely large-scale, multi-database, multi-engine migration program — sequencing by risk, matching target services to actual per-database compatibility findings rather than a one-size-fits-all decision, and building in validation discipline — rather than describing migration only at the level of a single database's mechanics.

## 33.12 Common Misconceptions

- **"Migration is purely a data-copying exercise."** False — schema compatibility, especially for heterogeneous (cross-engine) migrations, and application-level validation against the target are equally critical and often more time-consuming and risk-laden than the raw data transfer itself.
- **"Online migration eliminates downtime entirely."** Not quite accurate — online migration dramatically _reduces_ downtime compared to offline migration by keeping the source live during most of the process, but a final cutover step, however brief, is still required to safely transition the application to the new target.

## 33.13 Key Takeaways

- 🔑 Azure Database Migration Service supports both offline (simpler, requires a full migration-duration downtime window) and online (continuous synchronization, minimal-downtime cutover) migration approaches, chosen based on the source database's acceptable downtime tolerance.
- 🔑 Pre-migration compatibility assessment is essential and should directly inform target service selection (e.g., Managed Instance vs. Azure SQL Database) rather than being treated as a formality after the target has already been chosen.
- 🔑 Heterogeneous (cross-engine) migrations carry meaningfully more schema/logic translation complexity than homogeneous (same-engine) migrations and should be planned and resourced accordingly.
- 🔑 Large-scale enterprise migrations benefit from wave-based sequencing (lower-risk databases first) and rigorous test-migration validation before any production cutover.

## 33.14 Data Validation, Rollback, and Application Cutover Planning

### 33.14.1 Why This Extends Beyond Section 33.3's Migration Mechanics

Sections 33.3–33.5 covered how DMS actually moves schema and data. This subsection addresses the equally critical, often under-planned questions that determine whether a migration is _safe_ to execute in production: how do you confirm the migrated data is actually correct, what do you do if it isn't, and how does the application itself transition to the new database without an uncontrolled outage or silent data loss.

### 33.14.2 Data Validation

**Definition:** **Data validation** is the process of confirming that data in the target database genuinely and completely matches the source, beyond simply trusting that the migration tool reported success — since a migration tool reporting "completed" reflects that the _process_ ran without error, not necessarily that every row, relationship, and constraint landed correctly and completely.

**Common validation approaches:**

- **Row count reconciliation** — comparing row counts per table between source and target, a fast, low-effort first-pass check that catches gross data-loss issues (a table that's missing rows entirely) but doesn't catch subtler problems (correct row count but incorrect values).
- **Checksum/hash-based comparison** — computing a checksum or hash over each table's data (or samples of it) on both source and target and comparing them, catching value-level discrepancies that row counts alone would miss.
- **Business-rule/application-level validation** — running the actual application (or a representative subset of its critical queries/workflows) against the migrated target in a non-production test pass, confirming not just that raw data matches but that the application _functions correctly_ against it — this is what would catch a heterogeneous-migration schema-translation issue (Section 33.3.4) that technically preserved data but subtly changed its meaning or queryability.
- **Reconciliation of ongoing changes (online migrations specifically)** — for an online migration (Section 33.3.1), validation must also confirm the continuous synchronization phase is genuinely keeping the target current, not just that the initial load was correct — checking replication lag metrics (Section 33.9) and performing a final validation pass immediately before cutover, since data continues changing on the source throughout the migration window.

⚠️ Validation should be performed against a **non-production test migration** first (as already emphasized in Section 33.5's production usage note), refining the validation approach itself before it's relied upon to gate an actual production cutover decision — treating the validation process as something that itself needs testing and confidence-building, not just the migration mechanics alone.

### 33.14.3 Rollback Planning

**Definition:** A **rollback plan** defines the specific, pre-determined steps to revert the application back to the original source database if validation fails post-cutover, or if unexpected problems emerge after the application has already started using the new target — this must be planned and, ideally, tested _before_ cutover, not improvised during an actual incident under time pressure.

**Key rollback planning considerations:**

- **Source database retention** — the source database should remain intact, unmodified, and available for a defined window after cutover specifically to support rollback, rather than being decommissioned immediately upon a seemingly-successful cutover; the length of this retention window should reflect how long the organization needs to have confidence the migration was fully successful before it's safe to consider the source expendable.
- **Data drift during the post-cutover window** — if the application has already started writing to the new target after cutover, and a rollback becomes necessary, those new writes exist only on the target, not the source — rollback planning must explicitly address how to handle this (e.g., a brief read-only or fully-paused window immediately after cutover before declaring success, during which rollback would still be clean, versus a longer window where rollback would need a data-reconciliation step to carry forward any new target-only writes back to the source).
- **Rollback testing** — for high-stakes migrations, actually rehearsing the rollback procedure (not just the forward migration) against a test environment builds genuine confidence and surfaces gaps in the plan (missing steps, incorrect assumptions about source database state) before they matter in production.

🎯 **Interview Tip:** "What's your rollback plan?" is one of the most common questions in a migration design review, and a candidate who hasn't considered it — treating the migration as a one-way, can't-fail operation — is a significant red flag to an experienced interviewer. A credible answer always addresses source retention, data-drift handling, and ideally rollback rehearsal.

### 33.14.4 Application Connection Cutover Planning

**Definition:** **Cutover** is the actual moment the application stops using the source database and starts using the target — this requires the application's connection configuration (connection strings, DNS names, or a configuration-driven endpoint) to change, and how that change is executed materially affects both downtime and rollback simplicity.

**Common cutover mechanisms:**

- **Direct connection string change** — updating the application's configuration to point directly at the new target's connection string, requiring an application restart/redeployment to take effect — simple, but ties cutover timing to a deployment event and makes rollback require a second deployment.
- **DNS-based cutover (CNAME repointing)** — if the application connects via a DNS name rather than a hardcoded endpoint, repointing that DNS record to resolve to the new target allows cutover without an application redeployment — but is subject to DNS caching/TTL delays (echoing the TTL considerations from Section 28.4 and Section 25.4.2), meaning cutover isn't instantaneous across all clients, and rollback via DNS is similarly subject to the same propagation delay.
- **Abstraction-layer cutover** — if the application already uses a connection-string abstraction (e.g., a feature-flag-driven or configuration-service-driven database endpoint, rather than a hardcoded value), cutover can be as simple as flipping a centrally-managed flag, often the fastest and most easily reversible mechanism, but requires this abstraction to have been built into the application in advance rather than retrofitted urgently as part of the migration itself.

**Coordinating cutover with online migration's synchronization state (connecting to Section 33.3.1):** For an online migration specifically, cutover should only be executed once the continuous synchronization phase has confirmed the target is caught up (minimal replication lag) — cutting over prematurely, while the target is still meaningfully behind the source, risks the application reading and writing against incomplete or stale data immediately after cutover, undermining much of the point of using online migration's minimal-downtime approach in the first place.

### 33.14.5 Configuration Example — Illustrative Cutover Checklist

```text
Pre-Cutover Validation Gate (all must pass before proceeding):
  [ ] Row count reconciliation: source vs. target — match
  [ ] Checksum/hash comparison on critical tables — match
  [ ] Application smoke tests against target (non-production) — pass
  [ ] Online migration replication lag < defined threshold (e.g., < 5 seconds)
  [ ] Rollback plan reviewed and (for high-stakes migrations) rehearsed

Cutover Execution:
  [ ] Brief application-level pause or read-only mode enabled (if required by rollback plan)
  [ ] Final synchronization catch-up confirmed (online migration)
  [ ] Connection endpoint repointed (DNS / config flag / direct connection string, per chosen mechanism)
  [ ] Application resumed against target
  [ ] Post-cutover smoke tests against live target — pass

Post-Cutover:
  [ ] Source database retained, unmodified, for defined rollback window
  [ ] Monitoring in place for target database (Section 29/29/30's respective monitoring capabilities)
  [ ] Rollback window expiration and formal migration sign-off scheduled
```

- **Purpose:** Illustrates how the validation, rollback, and cutover concepts from this subsection combine into a concrete, checklist-driven cutover runbook — the kind of artifact that should exist and be reviewed _before_ a production migration cutover is attempted, not improvised in the moment.

### 33.14.6 Interview Questions — Section 33.14

**🎯 Senior/Architect**
**Q: Walk through how you'd validate a completed database migration and plan for cutover, for a production system that cannot tolerate silent data loss.**

_Model answer:_ I'd start with row count reconciliation as a fast first-pass sanity check across all migrated tables, followed by checksum or hash-based comparison on critical tables to catch value-level discrepancies row counts alone would miss. Beyond raw data comparison, I'd run the application's actual critical workflows against the migrated target in a non-production test pass, since a heterogeneous migration in particular (Section 33.3.4) can technically preserve data while subtly changing its meaning or queryability in ways a pure data comparison wouldn't catch. For an online migration specifically, I'd also confirm replication lag is within an acceptable threshold immediately before cutover, since the target continues receiving synchronized changes up until that point. For cutover itself, I'd prefer an abstraction-layer mechanism (a configuration flag or service pointing at the current database endpoint) over a hardcoded connection string if the application architecture supports it, since it allows both cutover and rollback without requiring a full redeployment, minimizing both downtime and the time-to-rollback if a problem is discovered. I'd retain the source database, fully intact and unmodified, for a defined post-cutover window, and would explicitly plan for how any target-only writes that occur after cutover would be handled if a rollback becomes necessary during that window — accepting either a brief read-only pause immediately after cutover to keep rollback clean, or building a data-reconciliation capability if a longer window is required. For a genuinely can't-tolerate-silent-data-loss system, I'd also rehearse this full rollback procedure against a test environment before the actual production cutover, rather than trusting an untested plan.

_What the interviewer is probing:_ whether the candidate treats migration validation and rollback as first-class, deliberately-planned concerns with specific concrete techniques, rather than assuming a successful-looking migration tool run is sufficient evidence the migration is actually safe to finalize.

### 33.14.7 Key Takeaways — Section 33.14

- 🔑 A migration tool reporting success reflects the process completing without error, not proof the data is correct — explicit validation (row counts, checksums, application-level smoke tests) is a separate, necessary step.
- 🔑 Rollback plans must be defined (and ideally rehearsed) before cutover, explicitly addressing source-database retention and how any target-only writes during the post-cutover window would be handled if rollback becomes necessary.
- 🔑 Cutover mechanism choice (direct connection string, DNS repointing, or an abstraction-layer flag) directly affects both achievable downtime and how easily rollback can be executed — an abstraction layer generally offers the fastest, cleanest cutover and rollback if the application architecture supports it.
- 🔑 For online migrations, cutover should only proceed once synchronization lag is confirmed within an acceptable threshold — premature cutover undermines the minimal-downtime benefit online migration is meant to provide.

## 33.15 Related Concepts / Part 6 Wrap-Up

This completes **Part 6 — Databases & Data Services**, covering Azure SQL Database/Managed Instance, Cosmos DB, PostgreSQL/MySQL, Azure Cache for Redis, and database migration strategy and tooling. **Part 7 — Containers & Orchestration** begins next with Section 34, covering Docker fundamentals on Azure, building toward Azure Kubernetes Service (AKS) — revisiting and building substantially on the container concepts first introduced with Azure Container Instances in Section 15, now moving into full container orchestration at production scale.
