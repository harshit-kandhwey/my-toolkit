# Part 6 - Section 1 - Amazon RDS Fundamentals

AWS Zero-to-Enterprise Knowledge Base - Part 6: Databases

---

## 1. Definition

Plain-language: RDS lets you run a standard relational database - MySQL, PostgreSQL, and others - without managing the underlying server yourself. AWS handles patching, backups, and much of the operational burden, while you interact with it exactly like any relational database you already know.

Precise: Amazon Relational Database Service (RDS) is a managed relational database service supporting multiple database engines (MySQL, PostgreSQL, MariaDB, Oracle, SQL Server, and Aurora), where AWS manages the underlying EC2 instance, OS, and database engine patching, while the customer retains control over schema, queries, and data.

---

## 2. Why It Exists

- RDS sits at the managed-service point on the spectrum for relational databases - a real engine, but AWS manages the underlying OS and much of the engine-level operational burden (patching, backup automation, failover) that self-managing on EC2 would leave entirely to you.
- Core problem: running production relational databases yourself means OS patching, engine patching, backup configuration, building your own HA failover logic, and monitoring - complex, error-prone work unrelated to actual application business logic. RDS removes most of that burden while preserving the relational experience developers already know.

---

## 3. Supported Database Engines

- MySQL, PostgreSQL, MariaDB - open-source, no licensing cost beyond RDS usage-based pricing.
- Oracle, SQL Server - commercial/licensed - License Included (AWS handles licensing, bundled into cost) or Bring Your Own License (BYOL, connecting to Dedicated Host licensing scenarios).
- Amazon Aurora - AWS's own MySQL/PostgreSQL-compatible engine, architecturally distinct enough for its own full section (Section 3).

Key idea: RDS is not one database - it's a management layer applied consistently across six engine choices, automating operational burden around whichever engine you choose without changing its fundamental SQL/query behavior.

---

## 4. DB Instance Classes

- Uses the same instance-family taxonomy as EC2 (general purpose, memory-optimized, burstable), with RDS-specific class names (db.m6g.large, db.r6g.xlarge) - same decoding logic applies.
- Memory-optimized (db.r-family) especially common for RDS - databases are frequently memory-bound (buffer cache, query working sets), making memory-to-vCPU ratio a common bottleneck.

---

## 5. Storage for RDS - Built on EBS

- RDS storage is EBS underneath - provisioning an RDS instance indirectly chooses an EBS volume type/size, following the same gp2/gp3 vs Provisioned IOPS (io1/io2) trade-off, now for database storage specifically.
- Storage Auto Scaling - RDS can automatically increase allocated storage as capacity approaches its limit, without manual intervention - parallel to EBS Elastic Volumes, automated for the "database running out of space" scenario.
- IOPS provisioning matters more for RDS than many EC2 workloads - database performance is frequently I/O-bound, making Provisioned IOPS a common production choice, not a specialized edge case.

---

## 6. Parameter Groups and Option Groups

- A DB Parameter Group contains engine-configuration settings (equivalent to a config file like MySQL's my.cnf), applied at the RDS-instance level since RDS abstracts away OS access.
- An Option Group provides additional engine-specific features requiring more than a simple parameter change (e.g., Oracle enterprise features) - narrower, used only for specific engines/features needing it.
- Because RDS manages the underlying OS/instance, you cannot directly edit a config file - Parameter/Option Groups are the RDS-native mechanism for the same customization through the managed API.

---

## 7. RDS Networking

- DB Subnet Groups - a collection of subnets (typically private) across multiple AZs that RDS uses to place the instance and any standbys/replicas - requiring the multi-AZ private-subnet three-tier architecture.
- RDS instances should live in private subnets - never directly internet-reachable - access only from the application tier via security groups scoped to the app tier's own security group (the chained-security-group pattern).
- RDS Proxy - a fully managed database proxy between an application (frequently Lambda) and RDS, pooling/reusing connections - solves the problem of Lambda's rapid concurrent scaling opening more simultaneous connections than a database can handle.

---

## 8. RDS vs Self-Managed Database on EC2

|                       | RDS (Managed)                     | Self-Managed on EC2                                     |
| --------------------- | --------------------------------- | ------------------------------------------------------- |
| OS/engine patching    | AWS handles it                    | You handle it                                           |
| Backup automation     | Built-in (Section 2)              | You build it                                            |
| HA failover           | Built-in (Multi-AZ, Section 2)    | You build it                                            |
| Engine/version choice | Limited to RDS-supported          | Any engine/version/config                               |
| OS-level access       | None - fully abstracted           | Full control                                            |
| Best for              | Vast majority of relational needs | Unsupported engines, or specific OS-level customization |

Interview tip: RDS should be the default for relational databases on AWS - the operational burden removed is substantial. Self-managed EC2 databases are reserved for genuinely specific needs RDS doesn't support.

---

## 9. Production & Enterprise Usage

- RDS as the default relational choice for most new AWS-native applications, self-managed EC2 reserved for genuinely unmet needs.
- RDS Proxy paired with Lambda-based applications - increasingly standard to prevent connection exhaustion from serverless scaling.
- Provisioned IOPS storage for production, query-heavy RDS instances - extending Part 5's storage-type framework to database-specific I/O-bound reality.
- BYOL for Oracle/SQL Server when an enterprise already holds licenses - a real cost consideration.

---

## 10. Security Considerations

- RDS instances belong in private subnets, accessible only via app-tier-scoped security groups - the standard three-tier pattern.
- Encryption at rest uses KMS, same envelope-encryption mechanics - like EBS/EFS, CANNOT be enabled on an existing unencrypted instance in place; path is creating an encrypted snapshot/copy and restoring a new instance.
- Credentials should be managed via Secrets Manager, not hardcoded, with native RDS-Secrets-Manager rotation integration automating the four-step rotation process.

---

## 11. Performance Considerations

- Instance class (compute/memory) and storage type/IOPS are the two primary performance levers - genuinely independent decisions, mirroring EBS's instance-vs-volume-bandwidth consideration at the database layer.
- RDS Proxy's connection pooling is itself a performance/stability lever for high-concurrency connection-churning patterns like Lambda, not just a connection-limit workaround.

---

## 12. Troubleshooting

| Symptom                                               | Cause                                                                | Fix                                                       |
| ----------------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------- |
| App can't connect to RDS                              | Security group doesn't allow app-tier traffic, or wrong subnet group | Verify security group scoping and subnet group placement  |
| Need to change engine config, no file-system access   | Attempting to edit a config file directly                            | Use a DB Parameter Group instead                          |
| Lambda app intermittently fails connecting under load | Too many concurrent invocations opening too many direct connections  | Introduce RDS Proxy                                       |
| Need to encrypt an existing unencrypted RDS instance  | Cannot toggle encryption in place                                    | Create an encrypted snapshot copy, restore a new instance |

---

## 13. Best Practices & Anti-Patterns

Best practices: default to RDS for relational needs; place RDS in private subnets accessed only via app-tier-scoped security groups; use RDS Proxy for Lambda/high-concurrency patterns; manage credentials via Secrets Manager with rotation; choose storage type based on actual I/O demands.

Anti-patterns: placing RDS in a public subnet or granting broad inbound access; attempting to edit config files directly instead of using Parameter Groups; connecting high-concurrency Lambda directly to RDS without pooling; hardcoding credentials.

---

## 14. Common Misconceptions

- "RDS is a single database product." False - a management layer across six engine choices.
- "You can SSH into RDS to tune config files directly." False - no OS-level access; use Parameter/Option Groups.
- "RDS storage is separate from EBS." False - built on EBS, same volume-type trade-offs.
- "Lambda can connect directly to RDS at any scale without consideration." False - RDS Proxy exists specifically for this.

---

## 15. Interview Questions (with model answers)

Beginner - What does RDS manage for you compared to self-managed EC2? OS patching, engine patching, automated backups, and (with Multi-AZ) HA failover - none automatic on self-managed EC2. You still control schema/queries/data; AWS handles infrastructure currency and resilience.

Beginner - Why can't you directly edit a MySQL config file on RDS? RDS abstracts away OS-level access entirely - no file-system/shell access to the underlying instance. Configuration changes go through a DB Parameter Group instead, achieving the same customization via the RDS API.

Intermediate - Why would a serverless Lambda+RDS application need RDS Proxy? Lambda can scale to many concurrent executions quickly; each opening its own direct DB connection can exceed the database's connection limit, causing failures under load. RDS Proxy pools/reuses a smaller number of actual connections across many invocations so the database isn't overwhelmed.

Intermediate - How choose between gp3 and Provisioned IOPS for a new RDS instance? Same reasoning as general EBS: gp3 default/cost-effective for moderate I/O demands; Provisioned IOPS for genuinely I/O-intensive, query-heavy production databases needing consistent performance under load - the same gp3-vs-io2 decision, applied to a typically I/O-bound database workload.

Senior - Design networking/connection management for RDS PostgreSQL serving both an EC2 web app and a Lambda data-processing pipeline? RDS in a private subnet, DB subnet group across 2+ AZs for future Multi-AZ. Security group allowing inbound only from: the EC2 app's security group, and the Lambda function's security group (Lambda accessing a VPC resource needs its own ENI/SG) - chained least-privilege pattern. RDS Proxy specifically for the Lambda pipeline given its rapid concurrent-scaling risk; the EC2 app with a smaller stable connection pool might not need it depending on its concurrency profile. Manage both apps' credentials via Secrets Manager with rotation; encrypt with a CMK from creation to avoid a later snapshot-and-restore migration.

---

## Key Takeaways

1. RDS is a management layer, not a single database product - applied across six engine choices, removing OS/engine patching, backup, and failover burden.
2. RDS storage is built on EBS - the gp3-vs-Provisioned-IOPS trade-off applies directly, I/O performance frequently the actual bottleneck.
3. Parameter Groups and Option Groups replace direct configuration-file access given the complete absence of OS-level access.
4. RDS networking follows the standard three-tier pattern - private subnets, DB subnet groups across AZs, chained security groups scoped to the app tier.
5. RDS Proxy solves Lambda's connection-exhaustion problem specifically - pooling connections between high-concurrency serverless compute and a database that can't handle that many direct connections.

## Related Concepts (forward links)

- RDS High Availability (Multi-AZ), Read Replicas, and backup mechanics in full depth -> [§50](./Section-50-Part6-RDS-HA-ReadReplicas-Backup.md)
- Amazon Aurora as RDS's own architecturally distinct engine -> [§51](./Section-51-Part6-Aurora-Deep-Dive.md)
- DynamoDB as the genuinely different, non-relational alternative -> [§52](./Section-52-Part6-DynamoDB-Fundamentals-DataModeling.md)
