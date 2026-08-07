# Section 13 (Part 2): Cloud SQL

## 1. Definition

**Plain language:** Cloud SQL is Google's managed relational database service — you get a working MySQL, PostgreSQL, or SQL Server database without having to install, patch, or babysit the database server yourself.

**Precise:** Cloud SQL is a fully managed relational database service supporting MySQL, PostgreSQL, and SQL Server engines, handling provisioning, storage scaling, patching, automated backups, and optional high-availability failover, while exposing the same wire protocol and SQL dialect as the underlying open-source/commercial engine, so existing applications and tools work largely unmodified.

## 2. Why It Exists / Problem It Solves

Running a relational database yourself on a VM means you own patching, backup scheduling and testing, failover orchestration, storage growth, and replication setup — all operational toil unrelated to building your application. Cloud SQL exists to remove that operational burden for the most common relational engines while preserving full SQL compatibility, so teams keep the familiar tooling and query language they already know, rather than being forced into a proprietary API like they would with some NoSQL migrations.

## 3. Core Concepts

### 3.1 Supported Engines

Cloud SQL supports **MySQL**, **PostgreSQL**, and **SQL Server**, each available across multiple major versions. The engine choice is typically driven by existing application compatibility rather than GCP-specific features, since Cloud SQL does not alter the SQL dialect or client protocol of the underlying engine.

### 3.2 High Availability (Regional Configuration)

Cloud SQL's HA configuration provisions a **primary instance** in one zone and a **standby instance** in a different zone within the same region, with data synchronously replicated to the standby's disk. If the primary or its zone fails, Cloud SQL automatically fails over to the standby, updating the instance's connection endpoint transparently, typically completing within under a minute. This is a regional (not global) HA model — it protects against zone failure, not regional failure.

### 3.3 Read Replicas

**Read replicas** are additional instances that asynchronously replicate from the primary, used to horizontally scale read-heavy workloads (offloading reporting/analytics queries from the primary) or to serve reads from a geographically closer region (**cross-region read replicas**). Unlike the HA standby, read replicas are usable for live traffic (read-only) at all times, not just during failover, but replication is asynchronous, so replicas can lag behind the primary.

> ⚠️ **Interview-relevant nuance:** The HA standby is not the same thing as a read replica — the standby is not queryable directly during normal operation and exists purely for failover, while a read replica is queryable but is not automatically promoted on primary failure without a manual (or scripted) promotion step.

### 3.4 Backups and Point-in-Time Recovery

Cloud SQL supports **automated daily backups** (retained per a configurable window) plus **transaction log retention**, enabling **point-in-time recovery (PITR)** — restoring the database to any specific timestamp within the log retention window, not just to the moment of the last daily backup. This is essential for recovering from application-level mistakes (e.g., an accidental `DELETE` without a `WHERE` clause) where you need to roll back to seconds before the error, not to last night's snapshot.

### 3.5 Cloud SQL Auth Proxy

The **Cloud SQL Auth Proxy** is a lightweight client-side process/sidecar that handles authentication and encryption between an application and its Cloud SQL instance without requiring the application to manage TLS certificates or manually authorize IP ranges. It authenticates using IAM credentials, establishes an encrypted tunnel to the instance, and lets the application connect to a local socket as if the database were local — removing the need for static IP allowlisting and manual certificate rotation.

## 4. Architecture Diagram

```
                     Region: us-central1
        ┌───────────────────────────────────────────────┐
        │    Zone -a                     Zone -b        │
        │ ┌──────────────┐   sync    ┌─────────────┐    │
        │ │  PRIMARY     │◄─────────►│  STANDBY    │    │
        │ │  instance    │replication│ (failover)  │    │
        │ └──────┬───────┘           └─────────────┘    │
        └────────┼──────────────────────────────────────┘
                 │ async replication
                 ▼
        ┌─────────────────────┐
        │   Read Replica      │  (same region or cross-region)
        │ (serves read-only   │
        │  query traffic)     │
        └─────────────────────┘

        Application ──(Cloud SQL Auth Proxy)──► Primary/Replica endpoint
        (IAM-authenticated, encrypted tunnel, no static IP allowlist needed)
```

## 5. Hands-On Examples

**Create an HA PostgreSQL instance (Beginner):**

```bash
gcloud sql instances create prod-db --database-version=POSTGRES_15 \
  --tier=db-custom-2-8192 --region=us-central1 --availability-type=REGIONAL
```

**Purpose:** Provisions a regional (HA) PostgreSQL 15 instance with a synchronously replicated standby.

**Create a read replica (Intermediate):**

```bash
gcloud sql instances create prod-db-replica-1 --master-instance-name=prod-db --region=us-east1
```

**Enable point-in-time recovery (Intermediate):**

```bash
gcloud sql instances patch prod-db --enable-point-in-time-recovery --retained-transaction-log-days=7
```

**Restore to a specific timestamp (Intermediate):**

```bash
gcloud sql instances clone prod-db prod-db-restored --point-in-time="2026-07-20T03:15:00Z"
```

**Expected output (abbreviated):**

```
Cloning Cloud SQL instance...done.
Created instance [prod-db-restored].
```

**Run the Cloud SQL Auth Proxy locally (Beginner):**

```bash
./cloud-sql-proxy my-project:us-central1:prod-db
```

## 6. Comparison vs. AWS RDS / Azure SQL Database

| Concept                                     | GCP Cloud SQL                                             | AWS RDS                                                                 | Azure SQL Database                                                                                     |
| ------------------------------------------- | --------------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| Supported engines                           | MySQL, PostgreSQL, SQL Server                             | MySQL, PostgreSQL, MariaDB, Oracle, SQL Server (plus Aurora separately) | SQL Server-compatible only (Azure SQL Database); other engines via Azure Database for MySQL/PostgreSQL |
| HA model                                    | Regional: sync standby in second zone, automatic failover | Multi-AZ: sync standby in second AZ, automatic failover                 | Zone-redundant configuration / auto-failover groups                                                    |
| Read scaling                                | Read replicas (same-region or cross-region, async)        | Read Replicas (async, cross-region supported)                           | Read replicas (geo-replication)                                                                        |
| Secure connectivity without IP allowlisting | Cloud SQL Auth Proxy (IAM-authenticated tunnel)           | RDS Proxy (connection pooling, IAM auth optional)                       | Azure AD authentication + private endpoints                                                            |
| PITR                                        | Yes, via transaction log retention                        | Yes, via automated backups + transaction logs                           | Yes, via automated backups                                                                             |

## 7. Production & Enterprise Usage

- **Private IP + VPC peering:** Production Cloud SQL instances are typically configured with private IP only (no public IP), reachable via VPC peering or Private Service Connect, minimizing internet exposure.
- **Connection pooling at scale:** High-connection-count applications pair Cloud SQL with a pooler (e.g., PgBouncer for PostgreSQL) since Cloud SQL instances have finite max-connection limits tied to instance size.
- **Automated maintenance windows:** Enterprises pin maintenance windows to low-traffic periods and use maintenance update tracks (stable vs. canary) to control when engine patches are applied.
- **Terraform-managed instances:** Instance tier, HA configuration, backup windows, and IAM database authentication are typically defined as code for repeatability across environments ([Section 52](../Part7/Section-52-Part7-Terraform-on-GCP-Deployment-Manager.md)).

## 8. Common Misconceptions

- **Misconception:** "A read replica can be promoted automatically on primary failure, just like the HA standby." Read replica promotion to become a new primary is a manual (or separately scripted) action — only the dedicated HA standby fails over automatically.
- **Misconception:** "Cloud SQL scales horizontally like a NoSQL database." Cloud SQL scales vertically (larger instance tiers) and via read replicas for read traffic, but write throughput is still bound to a single primary instance — genuine horizontal write scaling requires Cloud Spanner ([Section 14](./Section-14-Part2-Cloud-Spanner.md)) instead.

## 9. Interview Questions

**🎯 Beginner:** _What does the Cloud SQL Auth Proxy actually do?_
**Model answer:** It's a local process that sits between your application and the Cloud SQL instance, authenticating using IAM credentials and establishing an encrypted connection automatically. This means the application never needs to manage TLS certificates directly or rely on static IP allowlisting for network access — you connect to a local socket, and the proxy handles secure connectivity to the instance transparently.

**🎯 Intermediate:** _What's the difference between the HA standby and a read replica in Cloud SQL, and why does the distinction matter operationally?_
**Model answer:** The HA standby is a synchronously replicated instance in a second zone, purely for automatic failover — it isn't queryable for normal traffic. A read replica is asynchronously replicated and can serve live read-only query traffic at any time, but isn't automatically promoted on primary failure. The distinction matters because teams sometimes mistakenly assume a read replica provides failover protection; in reality, achieving both read scaling and automatic failover requires configuring HA and provisioning read replicas as two separate, complementary features.

**🎯 Senior/Architect:** _An application experiences an accidental bulk delete in production at 3:12 AM. Backups run nightly at 2 AM. How do you recover, and what should have been configured in advance?_
**Model answer:** If point-in-time recovery was enabled with sufficient transaction log retention, I'd clone the instance to a new instance targeting the timestamp just before 3:12 AM, verify the data there, then either redirect the application to the restored instance or selectively copy the affected rows back into production, minimizing data loss to seconds rather than losing everything since the prior night's backup. What should have been configured in advance: PITR enabled with a log retention window comfortably longer than the expected detection time for this class of incident, and ideally a defense-in-depth control at the application layer (e.g., requiring explicit confirmation or a soft-delete pattern for destructive bulk operations) so this class of incident is prevented rather than merely recoverable.

## 10. Key Takeaways

- 🔑 Cloud SQL manages MySQL, PostgreSQL, and SQL Server without altering the SQL dialect or wire protocol, preserving compatibility with existing tools.
- 🔑 HA (regional) uses a synchronous standby in a second zone for automatic failover; read replicas are a separate, asynchronous, always-queryable mechanism for read scaling.
- 🔑 Point-in-time recovery relies on transaction log retention, enabling restoration to any specific second within the retention window, not just to the last backup.
- 🔑 The Cloud SQL Auth Proxy removes the need for static IP allowlisting by authenticating via IAM and tunneling the connection.
- 🔑 Cloud SQL scales vertically and via read replicas; genuine horizontal write scaling requires Cloud Spanner ([Section 14](./Section-14-Part2-Cloud-Spanner.md)).

## 11. Related Concepts

Cloud Spanner for horizontally scalable relational needs ([Section 14](./Section-14-Part2-Cloud-Spanner.md)), Persistent Disks underlying Cloud SQL storage ([Section 12](./Section-12-Part2-Persistent-Disks-and-Filestore.md)), Cloud SQL Auth Proxy's reliance on IAM ([Section 35](../Part5/Section-35-Part5-IAM-Fundamentals-Members-Roles-Policies.md)/36), disaster recovery patterns ([Section 58](../Part8/Section-58-Part8-Disaster-Recovery-Multi-Region-Architecture.md)), and the AWS RDS/Azure SQL Database comparison in this section and [Section 82](../Part13/Section-82-Part13-GCP-vs-AWS-vs-Azure-Comparison.md).
