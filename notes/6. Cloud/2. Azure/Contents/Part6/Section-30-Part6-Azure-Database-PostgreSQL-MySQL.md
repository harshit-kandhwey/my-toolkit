# Section 30 — Azure Database for PostgreSQL/MySQL

## 30.1 Definition

**Plain language:** Azure Database for PostgreSQL and Azure Database for MySQL are fully managed versions of these popular open-source relational databases — Azure handles patching, backups, and high availability, the same operational relief PaaS provides for SQL Server (Section 28), but for applications built around PostgreSQL or MySQL specifically.

**Precise definition:** Azure Database for PostgreSQL and Azure Database for MySQL are fully managed Platform-as-a-Service offerings running the genuine, community-compatible PostgreSQL and MySQL database engines respectively, providing automated patching, backups, high availability, and elastic scaling, without requiring the customer to manage underlying VM or OS infrastructure.

## 30.2 Why It Exists / Problem It Solves

A substantial portion of the application ecosystem — particularly open-source, Linux-native, and many modern web-application stacks — is built around PostgreSQL or MySQL rather than SQL Server, often for licensing cost reasons, specific feature/extension ecosystems (PostgreSQL's rich extension ecosystem in particular), or simply pre-existing technical investment and team expertise. These applications need the same PaaS operational relief (no manual patching, automated backups, built-in HA) that Azure SQL Database provides for SQL Server-based applications, but running the actual PostgreSQL or MySQL engine for genuine compatibility with existing application code, drivers, and tooling built against those specific open-source database ecosystems — a proprietary reimplementation wouldn't provide the compatibility guarantee these migrations and new deployments require.

## 30.3 Core Concepts

### 30.3.1 Deployment Options

Both services have historically offered multiple deployment architectures, with the current primary recommended offering being the **Flexible Server** deployment model for both PostgreSQL and MySQL — ⚠️ Microsoft has, over time, retired or deprecated certain earlier deployment options (such as "Single Server") in favor of Flexible Server; current official documentation should always be checked to confirm which deployment options remain available/recommended before starting a new design, since this specific area has undergone meaningful change.

**Flexible Server characteristics:**

- **Zone-redundant high availability** — can be configured to deploy a standby replica in a different Availability Zone (Section 3.3.2), with automated failover if the primary becomes unavailable.
- **Burstable, General Purpose, and Memory Optimized compute tiers** — similar in spirit to VM sizing categories (Section 11.4), letting compute be matched to the actual workload's CPU/memory profile.
- **Custom maintenance windows** — allowing the customer to specify when Azure applies periodic patching, rather than having patching occur at an arbitrary, potentially business-inconvenient time.
- **Stop/Start capability** — Flexible Server instances can be stopped (halting billing for compute, though storage billing typically continues) and restarted, useful for dev/test environments that don't need to run continuously, a capability not typically available on the older Single Server model or on other fully continuous PaaS database offerings.

### 30.3.2 High Availability Configuration

Flexible Server high availability, when enabled, typically involves a synchronously-replicated standby instance (same-zone or zone-redundant, depending on configuration and region support) that can take over automatically if the primary instance becomes unavailable — this is an **optional, explicitly configured** feature (with associated additional cost) rather than always-on by default the way Azure SQL Database's built-in HA operates, an important distinction to verify when comparing the two services' baseline resilience posture.

⚠️ Exact HA architecture details, failover time expectations, and whether HA is zone-redundant or same-zone by default/configuration should be verified against current official documentation for the specific service (PostgreSQL vs. MySQL) and region, since these details can differ between the two database engines' respective Flexible Server implementations.

### 30.3.3 Extensions (PostgreSQL-Specific)

PostgreSQL is particularly known for its rich **extension** ecosystem — additional functionality that can be enabled on top of the core engine, such as **PostGIS** (geospatial data support) or **pg_stat_statements** (query performance statistics). Azure Database for PostgreSQL supports a defined, allow-listed set of extensions that can be enabled per server — not every community PostgreSQL extension is necessarily available in the managed service, since the managed nature of the offering requires Microsoft to vet and support each available extension. ⚠️ The specific list of currently supported extensions should always be verified against official documentation before assuming a particular extension an application depends on is available in the managed service, since this is a common and consequential compatibility check during migration planning.

### 30.3.4 Read Replicas

Both services support **read replicas** — additional, asynchronously-replicated copies of the database that can serve read-only query traffic, offloading read load from the primary instance and, when placed in different regions, providing lower-latency reads for geographically distributed read-heavy workloads — conceptually similar to RA-GRS's readable secondary for Storage Accounts (Section 20.3.4), but applied at the database engine level with its own replication lag characteristics that application logic must account for, similar to the eventual-consistency considerations already discussed for Cosmos DB (Section 29.3.3) and geo-redundant storage.

## 30.4 Architecture Diagram

```
Azure Database for PostgreSQL - Flexible Server "pg-myapp-prod"
 Region: East US
  ├── Primary Instance (Zone 1)
  │      Compute Tier: General Purpose
  │      Extensions enabled: postgis, pg_stat_statements
  │
  ├── (if HA enabled) Standby Instance (Zone 2) — synchronous replication,
  │      automated failover if primary becomes unavailable
  │
  └── Read Replica (West Europe) — asynchronous replication,
         serves read-only queries for European users with lower latency
         than querying the East US primary directly
```

## 30.5 Configuration & Hands-On Example

**Creating a PostgreSQL Flexible Server with zone-redundant HA:**

```bash
az postgres flexible-server create \
  --resource-group rg-myapp-prod \
  --name pg-myapp-prod \
  --location eastus \
  --admin-user pgadmin \
  --admin-password '<strong-password>' \
  --sku-name Standard_D2s_v3 \
  --tier GeneralPurpose \
  --high-availability ZoneRedundant \
  --version 16
```

- **Purpose:** Creates a General Purpose-tier Flexible Server with zone-redundant high availability, following the architecture shown in Section 30.4.
- **Important arguments explained individually:**
  - `--high-availability ZoneRedundant` — explicitly enables the optional HA configuration discussed in Section 30.3.2; omitting this parameter results in a single-instance deployment without automated failover, an important distinction from Azure SQL Database's always-on-by-default HA posture.
  - `--version` — specifies the PostgreSQL major version; supported versions and their end-of-support timelines should be verified against current documentation, since open-source database engines follow their own upstream version support lifecycles that Azure's managed service tracks.
- **Common error:** Attempting to enable an unsupported extension without first verifying it's on the currently-supported allow-list for the specific server version results in a configuration failure — always check the supported extension list for the specific engine version in use.

**Creating a read replica:**

```bash
az postgres flexible-server replica create \
  --resource-group rg-myapp-prod \
  --replica-name pg-myapp-replica-weu \
  --source-server pg-myapp-prod \
  --location westeurope
```

- **Purpose:** Creates an asynchronously-replicated, cross-region read replica, following the pattern shown in Section 30.4's diagram.
- **Application design note:** Read replica lag means replica reads may return slightly stale data relative to the primary; application logic must be designed to tolerate this (e.g., routing genuinely latency-tolerant analytical/reporting queries to the replica, while transactional reads requiring absolute freshness continue querying the primary).

## 30.6 Production & Enterprise Usage

Enterprises with existing PostgreSQL or MySQL application investments (open-source web application stacks, applications built by teams with specific PostgreSQL/MySQL expertise, or applications leveraging PostgreSQL-specific extensions like PostGIS) migrate to the corresponding Azure managed offering specifically to preserve engine compatibility while gaining PaaS operational benefits. HA configuration, backup retention policies, and read replica placement are deliberate, workload-specific decisions — not every workload justifies the additional cost of zone-redundant HA, and this should be a considered trade-off against the workload's actual availability requirements, mirroring the redundancy-selection discipline established for Storage Accounts in Section 20.7.

## 30.7 Security Considerations

- Both services support Entra ID-based authentication as an alternative/complement to native database authentication, extending the same centralized identity benefits established throughout Part 2.
- Private Link/VNet integration (Section 23.5) is recommended for production deployments holding sensitive data, avoiding public endpoint exposure.
- SSL/TLS enforcement for client connections should be verified as enabled (generally the default for Flexible Server), ensuring data in transit between application and database is encrypted.

## 30.8 Performance Considerations

Query performance tuning (appropriate indexing, query optimization) remains the customer's responsibility even in a managed PaaS offering — the managed service handles infrastructure-level concerns (patching, HA, backups) but doesn't eliminate the need for database-level performance engineering; both services provide query performance insights and logging integration with Azure Monitor (Part 10) to support this ongoing tuning work.

## 30.9 Monitoring

Standard Azure Monitor integration provides CPU, memory, storage, and connection-count metrics; PostgreSQL and MySQL-specific logs (query logs, slow query logs, when enabled) can be routed to Log Analytics for deeper query-level performance analysis, similar in spirit to Azure SQL Database's Query Performance Insight (Section 28.10) though implemented through more standard PostgreSQL/MySQL native logging mechanisms rather than an Azure SQL-specific proprietary feature.

## 30.10 Troubleshooting

| Symptom                                                                  | Likely Cause                                                                                     | Fix                                                                                                                                                                        |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Required PostgreSQL extension unavailable                                | Extension not on the currently supported allow-list for the managed service                      | Verify current supported extension list; consider an architectural alternative if the specific extension isn't and won't be supported                                      |
| Failover during an HA event takes longer than expected, or doesn't occur | HA wasn't actually enabled (defaults to non-HA single instance), or a genuine platform issue     | Verify `--high-availability` configuration was actually applied; review HA-specific SLA and failover time documentation for the specific configuration                     |
| Read replica queries return unexpectedly stale data                      | Normal asynchronous replication lag, potentially exacerbated by high write volume on the primary | Confirm application logic correctly tolerates expected replica lag for the specific query use case; monitor replication lag metrics to confirm it's within expected bounds |

## 30.11 Interview Questions — Section 30

### 🎯 Beginner

**Q: Why would an organization choose Azure Database for PostgreSQL over Azure SQL Database?**

_Model answer:_ The choice is primarily driven by which database engine the application is actually built for — an application written against PostgreSQL's SQL dialect, using PostgreSQL-specific features or extensions (like PostGIS for geospatial data), or maintained by a team with PostgreSQL-specific expertise, would use Azure Database for PostgreSQL to preserve genuine engine compatibility. Azure SQL Database runs the SQL Server engine specifically and wouldn't support PostgreSQL-specific SQL syntax or extensions; the decision is generally not about one service being "better" than the other in the abstract, but about matching the managed service to the actual database engine the application requires.

_What the interviewer is probing:_ basic understanding that engine choice, not a generic quality comparison, drives the decision between these differently-engined managed database offerings.

### 🎯 Senior

**Q: An application team wants to migrate their on-premises PostgreSQL database to Azure, needs high availability, and has read-heavy reporting workloads from users in a different region than the primary application. How would you configure the Azure Database for PostgreSQL deployment?**

_Model answer:_ I'd deploy a PostgreSQL Flexible Server in the primary application's region, explicitly enabling zone-redundant high availability given the stated requirement, since HA is an optional, explicitly-configured feature on Flexible Server rather than an always-on default. For the read-heavy reporting workload from a different region, I'd provision a cross-region read replica located near those reporting users, routing their reporting queries to the replica rather than the primary — reducing both latency for those users and read load on the primary instance. I'd explicitly validate with the reporting team whether the asynchronous replication lag inherent to read replicas is acceptable for their use case (reporting/analytics workloads are often naturally tolerant of some data staleness, unlike transactional operations), and would monitor replication lag metrics post-migration to confirm actual behavior matches this assumption. I'd also verify, before committing to the migration, that any PostgreSQL extensions the on-premises database currently relies on are present on the managed service's currently supported extension list, since this is a common and potentially migration-blocking compatibility gap that should be identified early in planning rather than discovered after cutover.

_What the interviewer is probing:_ whether the candidate can translate a description of application requirements (HA, cross-region reporting) into the specific corresponding Flexible Server features (zone-redundant HA, read replicas), while also proactively surfacing the extension-compatibility risk that's a genuinely common real-world migration blocker specific to PostgreSQL migrations.

## 30.12 Common Misconceptions

- **"Azure Database for PostgreSQL/MySQL has the same always-on HA as Azure SQL Database by default."** False — HA on Flexible Server is an optional, explicitly configured (and separately costed) feature, unlike Azure SQL Database's built-in HA that's part of the base service across tiers; this default-posture difference should be explicitly verified when comparing the two service families.
- **"Any PostgreSQL extension available in open-source PostgreSQL is available in the managed Azure service."** False — Azure Database for PostgreSQL supports a specific, vetted allow-list of extensions, not the full universe of community PostgreSQL extensions; this must be verified during migration planning, not assumed.

## 30.13 Key Takeaways

- 🔑 Azure Database for PostgreSQL and MySQL run the genuine, compatible open-source database engines as managed PaaS offerings, chosen specifically for engine compatibility with existing PostgreSQL/MySQL applications.
- 🔑 Flexible Server is the current primary deployment model for both, offering zone-redundant HA (as an optional, explicitly configured feature), flexible compute tiers, custom maintenance windows, and stop/start capability.
- 🔑 PostgreSQL's extension support is allow-listed and must be explicitly verified against application requirements during migration planning, not assumed to match full open-source PostgreSQL's extension ecosystem.
- 🔑 Read replicas provide asynchronously-replicated, cross-region read scaling, with the same replication-lag/staleness considerations that apply to any asynchronous replication mechanism covered elsewhere in this roadmap.

## 30.14 MySQL-Specific Considerations, and Backup/Restore/PITR for Both Engines

### 30.14.1 Why MySQL Needs Its Own Treatment

Sections 30.1–30.13 focused heavily on Flexible Server concepts illustrated primarily through PostgreSQL examples. While Azure Database for MySQL Flexible Server shares the same overall architecture (Flexible Server model, zone-redundant HA, burstable/General Purpose/Memory Optimized compute tiers, custom maintenance windows, stop/start capability — all as described in Section 30.3.1), MySQL has its own distinct compatibility surface, configuration mechanisms, and operational tooling that don't simply mirror PostgreSQL's — treating the two as interchangeable beyond the shared Flexible Server chassis is a real gap this subsection addresses.

### 30.14.2 MySQL-Specific Configuration

**Server parameters:** MySQL configuration (equivalent to PostgreSQL's configuration parameters, but using MySQL's own parameter/variable naming and semantics — e.g., `innodb_buffer_pool_size`, `max_connections`, `slow_query_log`) is managed through Azure's server parameters interface, analogous in mechanism to PostgreSQL's but with an entirely different parameter namespace reflecting MySQL's own engine internals (notably its InnoDB storage engine, MySQL's default and virtually universally-used transactional storage engine).

**Storage engine:** Unlike PostgreSQL (which has one primary storage layer), MySQL historically supports multiple **storage engines** (InnoDB, MyISAM, and others), though Azure Database for MySQL Flexible Server, like virtually all modern MySQL deployments, is built around **InnoDB** as the standard, transaction-safe engine — applications or legacy schemas relying on MyISAM-specific behavior (such as MyISAM's historically different full-text search implementation, or its lack of transaction support) should be assessed for InnoDB compatibility during migration planning, since MyISAM-specific features may not translate directly.

**Character sets and collation:** MySQL's character set and collation configuration (e.g., `utf8mb4` versus older `utf8`, which notably doesn't support the full Unicode range including many emoji and certain international characters) is a MySQL-specific compatibility area worth explicit verification during migration — a common real-world migration surprise when source data assumed a MySQL default that differs from the managed service's default configuration.

### 30.14.3 MySQL-Specific Compatibility Considerations

⚠️ Similar in spirit to PostgreSQL's extension allow-list (Section 30.3.3), Azure Database for MySQL supports a defined set of **plugins** and has specific version-by-version feature support — MySQL-specific features an application might depend on (such as specific replication configurations, certain MySQL-proprietary SQL extensions, or specific authentication plugins) should be verified against the current supported feature list for the target MySQL version before migration, exactly mirroring the PostgreSQL extension-verification discipline established in Section 30.3.3, but against MySQL's own distinct compatibility matrix.

### 30.14.4 Backup, Restore, and Point-in-Time Recovery (Both Engines)

**Automated backups:** Both Azure Database for PostgreSQL and MySQL Flexible Server perform automated backups by default — full backups plus transaction log backups (PostgreSQL's write-ahead log / WAL, and MySQL's binary log, respectively, each engine's own native mechanism for durability and replication that the managed backup system builds on) — requiring no customer configuration to enable at a baseline level, mirroring the automated-backup-by-default posture established for Azure SQL Database in Section 28.15.2.

**Point-in-Time Restore (PITR):** Both services support restoring to any specific point in time within a configurable retention window (commonly a default around 7 days, configurable up to 35 days — ⚠️ verify current default/maximum values against official documentation, matching the same verification discipline applied to Azure SQL's PITR in Section 28.15.2). As with Azure SQL's PITR, **restore creates a new server instance**, not an in-place rollback of the existing server — the same operational detail flagged for Azure SQL Database in Section 28.15.2 applies identically here, and should be reflected in incident-response runbooks for PostgreSQL/MySQL workloads exactly as for SQL Server-based ones.

**Long-term retention:** ⚠️ Unlike Azure SQL Database's dedicated, independently-configurable Long-Term Retention feature (Section 28.15.3), Azure Database for PostgreSQL/MySQL's native long-horizon backup retention capabilities should be verified against current documentation — if native LTR-equivalent functionality isn't available or doesn't meet a specific compliance retention requirement (e.g., a multi-year regulatory mandate), an application-level or infrastructure-level supplementary backup export strategy (e.g., periodic `pg_dump`/`mysqldump` exports to Blob Storage with its own lifecycle/immutability policy, connecting back to Section 17.14's Blob Storage data-protection capabilities) may be required to fully satisfy a long-term retention requirement — this is a genuine, worth-verifying gap-risk area rather than an assumed capability parity with Azure SQL Database.

**Geo-redundancy for DR:** Both PostgreSQL and MySQL Flexible Server support **geo-redundant backup** storage (backups replicated to the paired region, similar in principle to GRS, Section 20.3.3) and **read replicas** (Section 30.3.4) that can be promoted to a standalone writable server during a regional DR event — but this promotion is a **manual, customer-initiated** process for Flexible Server, distinct from Azure SQL Database's Auto-Failover Groups (Section 28.15.4), which support fully automatic failover with a stable connection endpoint. ⚠️ This is an important distinction to verify and communicate: PostgreSQL/MySQL Flexible Server's DR story generally requires more manual operational involvement during an actual regional failure than Azure SQL Database's most automated configuration — current documentation should be checked for whether this gap has narrowed, since managed-service DR automation capabilities are an actively developing area across Azure's database portfolio.

### 30.14.5 Interview Questions — Section 30.14

**🎯 Intermediate**
**Q: Are Azure Database for PostgreSQL and Azure Database for MySQL operationally identical aside from the underlying engine?**

_Model answer:_ No — while both share the same overall Flexible Server architecture (compute tiers, zone-redundant HA, maintenance windows, stop/start), each has its own distinct configuration surface (MySQL's server variables and InnoDB-specific settings versus PostgreSQL's configuration parameters and extension ecosystem), its own compatibility verification requirements (MySQL plugins and character-set/collation considerations versus PostgreSQL's extension allow-list), and, in some areas, different capability maturity — for example, PostgreSQL and MySQL Flexible Server's DR promotion process is more manual than Azure SQL Database's fully automated failover groups. Treating the two services as interchangeable beyond their shared PaaS operational model risks missing engine-specific migration or configuration issues.

_What the interviewer is probing:_ whether the candidate understands that "managed PaaS database" doesn't mean "identical operational characteristics regardless of engine" — genuine engine-specific knowledge versus a surface-level "it's just managed MySQL/PostgreSQL" assumption.

**🎯 Senior**
**Q: A team is deciding between PostgreSQL and MySQL Flexible Server for a new application with no strong existing engine preference, but with a hard requirement for fully automatic regional failover with zero application connection-string changes. What would you tell them?**

_Model answer:_ I'd flag that, as of current understanding, neither PostgreSQL nor MySQL Flexible Server offers the same fully automatic, stable-endpoint failover that Azure SQL Database's Auto-Failover Groups provide (Section 28.15.4) — their geo-redundant DR model generally requires manually promoting a read replica during an actual regional event, which doesn't meet a "zero application changes, fully automatic" requirement as stated. I'd recommend the team either verify this against the most current documentation in case this capability gap has narrowed, explicitly accept the manual-promotion operational model and build the necessary automation/runbook themselves (e.g., automation triggered by health monitoring that handles the promotion and connection-string update), or reconsider whether Azure SQL Database might be a better fit if the automatic-failover requirement is truly non-negotiable and outweighs any other engine preference — surfacing this trade-off explicitly before the team commits to an architecture, rather than discovering the gap during an actual incident.

_What the interviewer is probing:_ whether the candidate proactively surfaces a genuine, consequential service-capability gap relevant to the stated hard requirement, rather than assuming feature parity across Azure's different managed database offerings.

### 30.14.6 Key Takeaways — Section 30.14

- 🔑 MySQL Flexible Server shares Flexible Server's overall architecture with PostgreSQL but has its own distinct configuration (server variables, InnoDB), compatibility surface (plugins, character sets/collation), and migration verification requirements — the two engines are not interchangeable beyond the shared chassis.
- 🔑 Both PostgreSQL and MySQL Flexible Server provide automated backups and self-service Point-in-Time Restore (restoring to a new instance, not in place) within a configurable retention window, mirroring Azure SQL Database's PITR model.
- 🔑 Long-term, multi-year retention may require a supplementary application/infrastructure-level export strategy for PostgreSQL/MySQL, unlike Azure SQL Database's dedicated native Long-Term Retention feature — verify current capability before assuming parity.
- 🔑 Regional DR for PostgreSQL/MySQL Flexible Server generally requires manual read-replica promotion, a meaningfully less automated failover model than Azure SQL Database's Auto-Failover Groups — an important, easily-overlooked distinction when a hard automatic-failover requirement exists.

## 30.15 Related Concepts (Next Up)

Section 31 covers **Azure Cache for Redis** — a managed in-memory caching service commonly deployed alongside the relational and NoSQL database services covered in Sections 28-30, used to reduce database load and improve application latency for frequently-accessed data.
