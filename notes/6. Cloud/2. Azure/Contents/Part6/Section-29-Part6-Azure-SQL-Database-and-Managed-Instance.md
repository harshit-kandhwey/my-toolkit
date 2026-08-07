# Section 29 — Azure SQL Database & Managed Instance

## 1. Definition

**Plain language:** Azure SQL Database and Azure SQL Managed Instance are both ways to run Microsoft SQL Server-compatible databases in Azure without managing the underlying VM or OS yourself — Azure SQL Database is the more streamlined, fully PaaS option, while Managed Instance offers closer compatibility with a traditional on-premises SQL Server for easier migration of existing applications.

**Precise definition:** **Azure SQL Database** is a fully managed Platform-as-a-Service relational database offering, built on the SQL Server engine, providing built-in high availability, automated backups, patching, and elastic scaling, at the individual database (or elastic pool) level. **Azure SQL Managed Instance** is a PaaS offering providing near-complete SQL Server engine compatibility (including instance-level features like cross-database queries and SQL Agent) within a fully managed, isolated environment, designed specifically to ease lift-and-shift migration of existing on-premises SQL Server workloads.

## 2. Why It Exists / Problem It Solves

Running SQL Server on an IaaS VM ([Section 11](../Part3/Section-11-Part3-Azure-Virtual-Machines.md)) still requires the customer to handle OS patching, SQL Server engine patching, backup configuration and execution, and high-availability configuration (like Always On Availability Groups) manually — substantial, specialized database-administration overhead for a workload pattern (relational database hosting) common enough to warrant a fully managed PaaS alternative. Azure SQL Database and Managed Instance exist to remove this operational burden, with Microsoft handling patching, backups, and built-in high availability automatically — but they exist as two distinct offerings specifically because migration compatibility and fully-optimized-for-cloud database design pull in somewhat different directions: an existing, complex on-premises SQL Server deployment with cross-database dependencies and SQL Agent jobs needs different compatibility guarantees than a newly-designed, cloud-native application that can be built around Azure SQL Database's more streamlined, single-database-scoped model from the start.

## 3. Azure SQL Database — Core Concepts

### 3.1 Deployment Models

- **Single Database** — each database is an independent resource with its own dedicated compute and storage resources, isolated from other databases; the simplest model, appropriate when databases have independent, unpredictable, or differently-sized resource needs.
- **Elastic Pool** — multiple databases share a pool of compute resources, appropriate when you have many databases with variable, non-simultaneous peak usage patterns (a common SaaS multi-tenant pattern, where each customer's database is unlikely to peak in resource usage at exactly the same moment as every other customer's), allowing more cost-efficient resource sharing than provisioning each database independently for its own peak capacity.

### 3.2 Purchasing Models

- **DTU-based (Database Transaction Unit)** — a simplified, bundled measure combining CPU, memory, and I/O into a single blended metric/tier, easier to reason about for straightforward scenarios but less granular.
- **vCore-based** — allows independently choosing compute (vCores) and storage, offering more granular control and generally considered the more flexible, modern approach, also enabling **Azure Hybrid Benefit** (applying existing on-premises SQL Server licenses toward Azure SQL costs, a cost-optimization mechanism covered further in Part 12).

⚠️ Exact purchasing model names, tier structures, and Microsoft's current default/recommended model should be verified against official documentation, as pricing model details are actively maintained and periodically revised.

### 3.3 Service Tiers

Within the vCore model, service tiers include **General Purpose** (balanced compute/storage, standard production workloads), **Business Critical** (higher performance, built-in local SSD storage with faster failover, for the most demanding, latency-sensitive production workloads), and **Hyperscale** (a highly scalable storage architecture supporting very large databases with fast backup/restore and scaling operations, designed for databases that may grow substantially beyond what General Purpose/Business Critical comfortably support). ⚠️ Verify current tier names, specific capabilities, and applicable use-case guidance against official documentation, since tier evolution (particularly around Hyperscale's capabilities) has been an active area of the platform's development.

### 3.4 Built-In High Availability

Azure SQL Database provides high availability automatically as part of the managed service — the specific underlying architecture (which varies by service tier) generally involves multiple replicas and automated failover without requiring the customer to configure Always On Availability Groups or similar mechanisms manually, unlike a self-managed SQL Server on a VM. ⚠️ The exact HA architecture details differ meaningfully across service tiers (e.g., Business Critical's built-in local replica architecture versus General Purpose's separated compute/storage architecture) — verify current tier-specific HA architecture details against official documentation for precise SLA and failover-behavior expectations.

## 4. Azure SQL Managed Instance — Core Concepts

### 4.1 Instance-Level Compatibility

Unlike Azure SQL Database's single-database-scoped model, Managed Instance provides a full **SQL Server instance**, supporting instance-level features that Azure SQL Database's model doesn't natively support in the same way — including **cross-database queries** (querying across multiple databases within the same instance directly), **SQL Server Agent** (for scheduled jobs), **Service Broker**, and **CLR (Common Language Runtime) integration** — features commonly relied upon by existing, more complex on-premises SQL Server applications that Managed Instance is specifically designed to accommodate during a lift-and-shift migration.

### 4.2 Network Isolation

Managed Instance is deployed **directly into a customer's VNet** (specifically, a dedicated subnet), unlike Azure SQL Database's default connectivity model, providing a network isolation posture closer to what an on-premises SQL Server or a SQL Server-on-VM deployment would have — this VNet-native deployment is a deliberate design choice supporting migration scenarios with strict network isolation requirements matching existing on-premises network architecture expectations.

### 4.3 Choosing Between Azure SQL Database and Managed Instance

| Factor                    | Favors Azure SQL Database                                      | Favors Managed Instance                                                                             |
| ------------------------- | -------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Application design        | New, cloud-native application design                           | Existing application relying on instance-level features (cross-DB queries, SQL Agent, CLR)          |
| Migration goal            | Willing to re-architect for a more cloud-native database model | Lift-and-shift with minimal application changes                                                     |
| Network requirements      | Standard public/private endpoint connectivity sufficient       | Requires deployment directly within a specific VNet/subnet                                          |
| Multi-database management | Managing many independent or pooled databases                  | Managing what was previously a single SQL Server instance hosting multiple interdependent databases |

## 5. Architecture Diagram

```
Azure SQL Database (Single Database model)
 └── Logical Server "sql-myapp-server"  (a logical management/connectivity construct)
      ├── Database "db-orders"    (General Purpose tier, independent compute/storage)
      └── Database "db-inventory" (Business Critical tier, independent compute/storage)

Azure SQL Database (Elastic Pool model)
 └── Logical Server "sql-saas-server"
      └── Elastic Pool "pool-tenant-dbs" (shared compute/storage budget)
           ├── Database "tenant-001-db"
           ├── Database "tenant-002-db"
           └── Database "tenant-003-db"  (all sharing the pool's resources)

Azure SQL Managed Instance
 └── Deployed into VNet "vnet-data", Subnet "snet-sql-mi" (dedicated subnet)
      └── Instance "sqlmi-legacyapp"
           ├── Database "db-orders"     ┐
           ├── Database "db-customers"  ├─ cross-database queries supported within the instance
           └── SQL Agent Jobs configured for scheduled maintenance/ETL tasks
```

## 6. Configuration & Hands-On Example

**Creating an Azure SQL Database (Single Database, vCore model):**

```bash
az sql server create \
  --resource-group rg-myapp-prod \
  --name sql-myapp-server \
  --admin-user sqladmin \
  --admin-password '<strong-password>'

az sql db create \
  --resource-group rg-myapp-prod \
  --server sql-myapp-server \
  --name db-orders \
  --edition GeneralPurpose \
  --family Gen5 \
  --capacity 2
```

- **Purpose:** Creates a logical SQL Server (the connectivity/management endpoint, not a VM) and a General Purpose-tier database with 2 vCores, following the Single Database deployment model.
- **Important arguments explained individually:**
  - `--edition` — the service tier (General Purpose in this example); `--family` and `--capacity` further specify the hardware generation and vCore count within the vCore purchasing model.
  - The admin password should never be hardcoded in scripts committed to source control; production automation should retrieve this from Azure Key Vault ([Section 56](../Part11/Section-56-Part11-Key-Vault.md)) instead.
- **Security note:** By default, newly created SQL Servers deny all inbound connections; a firewall rule (or Private Endpoint, [Section 23](../Part5/Section-23-Part5-VNet-Peering-Service-Endpoints-Private-Link.md).5, for full network isolation) must be explicitly configured to allow the intended client connectivity — a deliberate secure-by-default posture.

**Configuring a firewall rule to allow a specific client IP range:**

```bash
az sql server firewall-rule create \
  --resource-group rg-myapp-prod \
  --server sql-myapp-server \
  --name allow-app-service-outbound \
  --start-ip-address 20.185.xx.xx \
  --end-ip-address 20.185.xx.xx
```

- **Purpose:** Explicitly allows a specific IP (or range) to connect, following least-privilege network access principles rather than allowing all IPs; for production, Private Endpoint-based connectivity ([Section 23](../Part5/Section-23-Part5-VNet-Peering-Service-Endpoints-Private-Link.md).5) is generally preferred over IP-based firewall rules for stronger network isolation, particularly for connections originating from within Azure itself.

## 7. Production & Enterprise Usage

Enterprises building new, cloud-native applications generally default to Azure SQL Database (Single Database or Elastic Pool, depending on the multi-tenancy pattern), favoring its more streamlined operational model and its natural fit with modern application architecture patterns. Enterprises migrating substantial existing SQL Server estates — particularly those with complex, interdependent multi-database applications relying on instance-level features — favor Managed Instance specifically to minimize required application changes during migration, planning a potential future re-architecture toward Azure SQL Database's model only if and when it becomes worthwhile, rather than as a migration prerequisite. Both offerings integrate with Azure Active Directory/Entra ID authentication ([Section 6](../Part2/Section-06-Part2-Microsoft-Entra-ID-Fundamentals.md)-[Section 9](../Part2/Section-09-Part2-Managed-Identities-and-Service-Principals.md)) as an alternative to SQL-native authentication, and both support Transparent Data Encryption (encryption at rest) by default, connecting to the broader security/compliance discussion in Part 11.

## 8. Security Considerations

- Both Azure SQL Database and Managed Instance deny public network access by default in many configurations, or at minimum require explicit firewall rule configuration — always verify the actual default network posture for the specific deployment configuration chosen, rather than assuming a permissive default.
- Entra ID-based authentication (rather than SQL-native username/password authentication) is the recommended approach wherever feasible, extending the same RBAC and Conditional Access (Sections 8, 10) benefits already established for other Azure resources to database access as well.
- **Auditing** and **Advanced Threat Protection** (part of Microsoft Defender for Cloud's database-specific capabilities, Part 11) provide detection for anomalous database access patterns and potential SQL injection attempts, an important layer beyond network-level access control alone.

## 9. Performance Considerations

Service tier and vCore/DTU allocation directly determine available compute, memory, and I/O throughput — performance troubleshooting should start with Azure SQL's built-in query performance insights and DTU/vCore utilization metrics ([Section 29](./Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md).10) before assuming a tier upgrade is necessary, similar in principle to the disk-performance troubleshooting discipline established in [Section 18](../Part4/Section-18-Part4-Azure-Managed-Disks.md).11 (verify the actual bottleneck via metrics before scaling).

## 10. Monitoring

Azure SQL Database and Managed Instance both provide built-in **Query Performance Insight** and integration with Azure Monitor (Part 10) for resource utilization metrics (DTU/vCore percentage, storage utilization, connection counts) and **Intelligent Insights**, which can automatically detect certain performance degradation patterns (like a regressed query plan) and suggest remediation — reducing the manual database-performance-tuning expertise required compared to fully self-managed SQL Server.

## 11. Troubleshooting

| Symptom                                                                                 | Likely Cause                                                                                                                         | Fix                                                                                                         |
| --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------- |
| Application cannot connect to Azure SQL Database at all                                 | No firewall rule or Private Endpoint allowing the client's network path                                                              | Add an appropriate firewall rule or configure Private Endpoint connectivity                                 |
| Existing on-premises SQL Server application fails after migrating to Azure SQL Database | Application relies on instance-level features (cross-database queries, SQL Agent, CLR) not supported in the Azure SQL Database model | Consider migrating to Managed Instance instead, which supports these instance-level features                |
| Database performance degrades under load despite adequate-seeming tier                  | Actual bottleneck may be query-level (missing indexes, inefficient query plans) rather than raw compute/storage capacity             | Review Query Performance Insight and Intelligent Insights before assuming a tier upgrade is the correct fix |

## 12. Interview Questions — [Section 29](./Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md)

### 🎯 Intermediate

**Q: When would you choose Azure SQL Managed Instance over Azure SQL Database?**

_Model answer:_ Managed Instance is the better choice when migrating an existing SQL Server application that relies on instance-level features not natively supported by Azure SQL Database's single-database-scoped model — cross-database queries, SQL Server Agent jobs, Service Broker, or CLR integration — since Managed Instance provides much closer compatibility with a traditional on-premises SQL Server instance, minimizing required application changes during migration. Azure SQL Database is generally preferred for new, cloud-native application development, or for existing applications that don't depend on those instance-level features, since it offers a more streamlined, typically more cost-efficient operational model.

_What the interviewer is probing:_ whether the candidate understands the specific, concrete compatibility gap (instance-level features) that drives the choice, rather than a vague sense that "Managed Instance is for bigger/more complex needs."

### 🎯 Senior

**Q: An enterprise has 40 SQL Server databases on-premises, used by different internal applications with varying and largely non-overlapping usage peaks. How would you approach their Azure SQL migration to optimize cost while maintaining adequate performance?**

_Model answer:_ I'd first assess which of the 40 databases depend on instance-level features (cross-database queries, SQL Agent jobs, CLR) requiring Managed Instance for compatibility, migrating those as a group (since Managed Instance is provisioned at the instance level, grouping compatible/interdependent databases together makes sense) while evaluating whether the remaining databases could move to Azure SQL Database instead. For the Azure SQL Database-eligible group, given the described pattern of many databases with non-overlapping peak usage times, I'd strongly consider an Elastic Pool rather than provisioning each database as an independent Single Database resource — an Elastic Pool lets these databases share a compute/storage budget, and since their peaks don't overlap, the pool's total provisioned capacity can be meaningfully smaller than the sum of what each database would need individually, directly reducing cost without sacrificing the performance each application needs during its own actual peak periods. I'd validate this approach using actual historical usage telemetry from the on-premises databases (rather than assuming the non-overlapping pattern holds without evidence) to correctly size the elastic pool's total capacity, and would monitor actual pooled utilization post-migration to confirm the assumption held and adjust pool sizing if needed.

_What the interviewer is probing:_ whether the candidate recognizes Elastic Pools as the specific, purpose-built solution for exactly this "many databases, non-overlapping peaks" cost-optimization scenario, and whether they ground the design in actual usage data rather than an untested assumption.

## 13. Common Misconceptions

- **"Azure SQL Database and Managed Instance are just different pricing tiers of the same product."** False — they're architecturally distinct offerings with meaningfully different compatibility scopes (single-database vs. instance-level features) and deployment models (default connectivity vs. VNet-native), not simply different price points of an identical product.
- **"Migrating to Azure SQL Database always requires an application rewrite."** Not necessarily true for applications that don't depend on instance-level features — many applications migrate to Azure SQL Database with minimal changes; the instance-level-feature dependency is specifically what necessitates considering Managed Instance instead.

## 14. Key Takeaways

- 🔑 Azure SQL Database is a single-database (or elastic-pool)-scoped, fully managed PaaS relational database; Managed Instance provides near-complete SQL Server instance-level compatibility for easier lift-and-shift migration.
- 🔑 The key decision driver between the two is dependency on instance-level features (cross-database queries, SQL Agent, CLR) — present in the existing application favors Managed Instance; absent favors Azure SQL Database's more streamlined model.
- 🔑 Elastic Pools are the purpose-built cost-optimization mechanism for scenarios with many databases exhibiting non-overlapping peak usage patterns.
- 🔑 Managed Instance deploys directly into a customer VNet/subnet, providing network isolation closer to an on-premises or VM-hosted SQL Server than Azure SQL Database's default connectivity model.

## 15. Business Continuity: Backups, Point-in-Time Restore, Long-Term Retention, Geo-Replication/Failover Groups, and Migration Approaches

### 15.1 Why This Extends Beyond the Built-In HA Already Covered

[Section 29](./Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md).3.4 covered Azure SQL Database's built-in high availability — automatic failover within a region against infrastructure failure. This subsection covers the distinct, complementary concerns of recovering from _data-level_ mistakes (accidental deletes, bad deployments) and surviving a _full regional_ outage, mirroring the same three-layer resilience model (HA / Backup / DR) established for VMs in [Section 11](../Part3/Section-11-Part3-Azure-Virtual-Machines.md).15 — the same principle applies here: infrastructure-level HA does not substitute for data-recovery or cross-region DR capability.

### 15.2 Automated Backups and Point-in-Time Restore (PITR)

**Definition:** Azure SQL Database and Managed Instance both perform **automated backups** by default — full backups, differential backups, and transaction log backups, taken automatically on a Microsoft-managed schedule, requiring no customer configuration to enable at a baseline level.

**Point-in-Time Restore (PITR):** These automated backups enable restoring a database to any specific point in time within the configured retention window (commonly a default such as 7 days, configurable up to 35 days depending on tier — ⚠️ verify current default and maximum retention values against official documentation) — recovering from scenarios like an accidental bulk delete or a bad application deployment that corrupted data, by restoring to the moment just before the mistake occurred.

⚠️ **PITR restores to a new database, not in place.** Restoring doesn't overwrite the existing (problematic) database directly — it creates a new database at the restored point in time, which the application must then be redirected to (or the old database renamed/replaced) — this operational detail matters for incident-response runbooks, since "restore" isn't a single-click in-place rollback.

### 15.3 Long-Term Retention (LTR)

**Definition:** Beyond the standard PITR backup retention window (days to a few weeks), **Long-Term Retention** allows configuring backup retention for up to 10 years, on a defined schedule (e.g., retain one backup per week for 1 year, one per month for 5 years, one per year for 10 years), stored independently of the standard automated backup chain.

**Why it's distinct from PITR backups:** PITR backups are optimized for fine-grained, recent recovery (restore to any minute within the last few weeks); LTR backups are optimized for compliance and long-horizon retention requirements (e.g., "financial records must be retrievable for 7 years") where fine-grained recency isn't the goal — the two serve genuinely different recovery objectives and are configured and billed separately.

### 15.4 Geo-Replication and Failover Groups

**Active Geo-Replication:** Creates up to four readable secondary replicas of a database in different regions, asynchronously replicated from the primary, allowing manual failover to a secondary region if the primary becomes unavailable, and allowing the secondary replicas to serve read-only query traffic in the meantime (conceptually similar to RA-GRS's readable secondary for Storage Accounts, [Section 20](../Part4/Section-20-Part4-Data-Redundancy-and-Replication.md).3.4, and Cosmos DB's read regions, [Section 30](./Section-30-Part6-Cosmos-DB.md).3.5, applied here at the SQL database level).

**Auto-Failover Groups:** Builds on Active Geo-Replication by adding **automatic failover** (rather than requiring a manual failover trigger) and providing a **stable, abstracted connection endpoint** that automatically redirects to whichever region is currently primary — meaning the application's connection string doesn't need to change during a failover event, since it always points at the failover group's endpoint rather than a specific region's server directly.

⚠️ Like GRS ([Section 20](../Part4/Section-20-Part4-Data-Redundancy-and-Replication.md).3.3), geo-replication here is **asynchronous** — a true regional disaster can result in loss of the most recent, not-yet-replicated transactions, the same fundamental Recovery Point Objective limitation established for Storage Account redundancy. This should be explicitly communicated to stakeholders rather than assumed away, exactly as emphasized in [Section 20](../Part4/Section-20-Part4-Data-Redundancy-and-Replication.md).10's senior interview answer.

**Managed Instance note:** Managed Instance supports its own equivalent failover group mechanism for instance-level (rather than single-database-level) geo-replication and failover, consistent with its broader instance-scoped model ([Section 29](./Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md).4.1).

### 15.5 The Three-Layer SQL Resilience Model

1. **Built-in HA ([Section 29](./Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md).3.4)** — automatic, intra-region protection against infrastructure failure; always active as part of the base service.
2. **Backups: PITR + Long-Term Retention (this subsection)** — recover from data-level mistakes, at either short-term fine-grained (PITR) or long-term compliance-driven (LTR) recovery horizons.
3. **Geo-Replication / Auto-Failover Groups (this subsection)** — survive a full regional outage, with an explicit, asynchronous-replication-driven Recovery Point Objective trade-off.

### 15.6 Migration Approaches (Consolidating and Extending [Section 33](./Section-33-Part6-Data-Migration-and-DMS.md))

For SQL Server-to-Azure-SQL migrations specifically, Azure Database Migration Service ([Section 33](./Section-33-Part6-Data-Migration-and-DMS.md)) is the primary purpose-built tool, but several SQL-specific approaches and tools exist depending on scenario:

- **Azure Data Migration Assistant (DMA)** — a free, standalone assessment tool (distinct from DMS itself) specifically for SQL Server, identifying compatibility issues and recommending performance/reliability improvements before migration — commonly used as the assessment step ([Section 33](./Section-33-Part6-Data-Migration-and-DMS.md).3.2) feeding into a subsequent DMS-driven migration.
- **Native backup/restore** — for simpler, offline ([Section 33](./Section-33-Part6-Data-Migration-and-DMS.md).3.1) SQL Server-to-Managed-Instance migrations, a native SQL Server backup (`.bak` file) can sometimes be directly restored to a Managed Instance, a lighter-weight alternative to a full DMS project for straightforward, downtime-tolerant scenarios.
- **Transactional replication** — for specific scenarios needing continuous, ongoing synchronization beyond a one-time migration cutover (e.g., a genuinely long-running hybrid state, not just a migration transition window), SQL Server transactional replication can target Azure SQL Database directly, distinct from DMS's migration-focused (finite-duration, cutover-oriented) online synchronization.

⚠️ Tool availability and specific compatibility (particularly `.bak` restore support, which has specific version and configuration prerequisites) should be verified against current official documentation before committing to a specific migration approach.

### 15.7 Configuration Example

**Configuring an Auto-Failover Group:**

```bash
az sql failover-group create \
  --resource-group rg-myapp-prod \
  --server sql-myapp-server \
  --name fg-myapp-orders \
  --partner-server sql-myapp-server-secondary \
  --partner-resource-group rg-myapp-dr \
  --add-db db-orders \
  --failover-policy Automatic \
  --grace-period 1
```

- **Purpose:** Creates a failover group between the primary server (from [Section 29](./Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md).6's example) and a secondary server in a different region, adding the `db-orders` database, with automatic failover enabled after a 1-hour grace period (avoiding failover on a very brief, transient outage).
- **Important arguments explained individually:**
  - `--grace-period` — the number of hours the primary must be unavailable before automatic failover triggers; this deliberately avoids failing over (with its associated RPO/RTO implications) in response to a short-lived blip that would resolve on its own.
  - `--failover-policy Automatic` — as opposed to `Manual`, which would require an administrator to explicitly trigger failover rather than having it occur automatically after the grace period.

### 15.8 Interview Questions — [Section 29](./Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md).15

**🎯 Intermediate**
**Q: What's the difference between Point-in-Time Restore and Long-Term Retention backups?**

_Model answer:_ Point-in-Time Restore uses the standard automated backup chain (full, differential, transaction log backups) to restore a database to any specific minute within a relatively short retention window (commonly up to 35 days), suited to recovering from a recent mistake like an accidental delete or bad deployment. Long-Term Retention is a separate, independently configured mechanism retaining backups on a defined schedule for up to 10 years, suited to compliance and long-horizon retention requirements rather than fine-grained recent recovery. They serve different recovery objectives and are configured, scheduled, and billed separately.

_What the interviewer is probing:_ whether the candidate understands these as two distinct mechanisms serving different recovery time horizons, rather than treating "backup" as a single undifferentiated Azure SQL capability.

**🎯 Senior/Architect**
**Q: Design the business-continuity strategy for a mission-critical Azure SQL Database, addressing infrastructure failure, accidental data loss, regional disaster, and a 7-year regulatory retention requirement.**

_Model answer:_ Built-in HA ([Section 29](./Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md).3.4) is active by default and handles intra-region infrastructure failure automatically, requiring no additional configuration beyond appropriate service-tier selection. For accidental data loss, I'd rely on the default PITR backup chain, configuring an appropriate retention window based on the business's realistic detection-and-response time for data-corruption incidents. For the 7-year regulatory retention requirement, I'd configure Long-Term Retention with a schedule matching the specific regulatory requirement (for example, retaining one backup per year for 7 years, or whatever cadence the actual regulation specifies), explicitly separate from the PITR configuration since they serve different purposes. For regional disaster resilience, I'd configure an Auto-Failover Group to a secondary region, with automatic failover and an appropriate grace period tuned to avoid triggering on brief transient issues, and would explicitly document and communicate to stakeholders that the asynchronous replication underlying this means a true regional disaster could still result in loss of the very most recent transactions — if the business has a genuine zero-data-loss requirement, I'd flag that storage/database-level geo-replication alone doesn't satisfy that and would need to be paired with an application-level synchronous write strategy or a revised RPO expectation agreed with the business. I'd test failover (both for the failover group and for PITR restore) periodically rather than assuming untested configuration will work correctly during an actual incident.

_What the interviewer is probing:_ whether the candidate can address all four distinct requirements (infrastructure HA, data-loss recovery, regional DR, long-term compliance retention) with the four correspondingly distinct mechanisms, while being honest about the asynchronous-replication RPO limitation rather than presenting geo-replication as a complete, zero-data-loss solution — genuinely comprehensive, honest architectural reasoning.

### 15.9 Key Takeaways — [Section 29](./Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md).15

- 🔑 Automated PITR backups (default, days-to-weeks retention) and Long-Term Retention (up to 10 years, independently scheduled) serve different recovery time horizons and are configured separately.
- 🔑 PITR restores create a new database rather than restoring in place — this operational detail should be reflected in incident-response runbooks.
- 🔑 Auto-Failover Groups add automatic failover and a stable connection endpoint on top of Active Geo-Replication, but replication remains asynchronous, carrying the same non-zero data-loss-window limitation as Storage Account GRS ([Section 20](../Part4/Section-20-Part4-Data-Redundancy-and-Replication.md)).
- 🔑 SQL-specific migration tooling (Data Migration Assistant for assessment, native backup/restore, transactional replication) complements the general-purpose DMS covered in [Section 33](./Section-33-Part6-Data-Migration-and-DMS.md), each suited to different migration scenarios and downtime tolerances.
- 🔑 A complete Azure SQL resilience strategy layers built-in HA, backups (PITR + LTR), and geo-replication/failover groups — the same three-layer model (HA / Backup / DR) established for VMs in [Section 11](../Part3/Section-11-Part3-Azure-Virtual-Machines.md).15, applied here at the managed-database level.

## 16. Related Concepts (Next Up)

[Section 30](./Section-30-Part6-Cosmos-DB.md) covers **Cosmos DB** — Azure's globally-distributed, multi-model NoSQL database service, offering a fundamentally different data model and consistency/distribution approach than the relational SQL Database/Managed Instance offerings just covered, directly relevant to the global multi-region architecture patterns introduced in [Section 25](../Part5/Section-25-Part5-Azure-Front-Door-and-CDN.md)'s Front Door discussion.
