# Part 6 - Section 2 - RDS High Availability, Read Replicas & Backup

AWS Zero-to-Enterprise Knowledge Base - Part 6: Databases

---

## 1. Definition

Plain-language: RDS Multi-AZ keeps a synchronized standby copy of your database in a different AZ, ready to take over automatically if the primary fails. Read Replicas are additional, separate copies that serve read-only queries, spreading out read traffic. Automated backups and snapshots protect against data loss and let you restore to any point in time.

Precise: RDS Multi-AZ provides synchronous replication to a standby instance in a different AZ, with automatic failover on primary failure. RDS Read Replicas provide asynchronous replication to separate, independently-queryable instances, primarily for read scaling. RDS automated backups provide point-in-time recovery via daily snapshots plus continuous transaction log capture.

---

## 2. Why This Category Exists

- A single RDS instance, however well-managed, is a single point of failure without Multi-AZ, and cannot absorb large read traffic without Read Replicas.
- Two different problems, two different mechanisms: availability (surviving an AZ failure without data loss/extended downtime) is Multi-AZ's job; read scalability (handling more reads than one instance can serve) is Read Replicas' job - commonly conflated since both involve "another copy," but solving different problems with different replication mechanics.

---

## 3. RDS Multi-AZ - Full Mechanics

### 3.1 How It Works

- Maintains a synchronous, physical-replication standby in a different AZ, same Region - every write synchronously replicated to the standby before being considered committed, ensuring zero data loss (RPO ~0) on failover.
- The standby is NOT readable (classic RDS Multi-AZ, distinct from Aurora) - exists purely for failover readiness.

### 3.2 Automatic Failover

- On primary failure (health-check detected), RDS automatically promotes the standby - the connection endpoint (DNS name) doesn't change, so the application simply reconnects, now resolving to the promoted standby.
- Failover typically 60-120 seconds - non-zero RTO but far faster than Backup and Restore. Architecturally closer to a "Warm Standby" pattern for the database tier.

### 3.3 Multi-AZ and Backups

Automated backups are taken from the standby, not the primary, in Multi-AZ - avoiding I/O contention on the production-serving primary.

---

## 4. RDS Read Replicas - Full Mechanics

### 4.1 How It Works

A Read Replica is a separate, independently-addressable instance kept in sync via asynchronous replication - genuine measurable replication lag exists, unlike Multi-AZ's synchronous model.
Read Replicas ARE readable - their entire purpose: offload read-only queries from the primary, a horizontal read-scaling mechanism.

### 4.2 Cross-Region Read Replicas

Unlike Multi-AZ (same-Region only), Read Replicas can be cross-Region - enabling multi-Region read scaling for lower-latency local reads AND serving as a DR building block. A cross-Region replica can be manually promoted to a standalone writable instance during a disaster.

### 4.3 Read Replicas vs Multi-AZ

|                  | Multi-AZ Standby           | Read Replica                              |
| ---------------- | -------------------------- | ----------------------------------------- |
| Replication type | Synchronous                | Asynchronous                              |
| Readable?        | No (classic Multi-AZ)      | Yes                                       |
| Purpose          | High availability/failover | Read scaling (+ optional cross-Region DR) |
| Failover         | Automatic                  | Manual promotion required                 |
| Region           | Same Region only           | Same Region or cross-Region               |
| Data currency    | Always current (zero lag)  | Potentially lagging                       |

Interview tip: Multi-AZ = availability, synchronous non-readable standby with automatic failover, zero data loss. Read Replicas = read scaling, asynchronous readable copies requiring manual promotion. Different problems, frequently used together.

### 4.4 Can You Have Both?

Yes - the standard production pattern: Multi-AZ primary (availability) with Read Replicas attached (read scaling); Read Replicas can themselves be Multi-AZ for a fully resilient read tier.

---

## 5. RDS Backup Mechanics

### 5.1 Automated Backups

Daily full snapshot during a configurable window, plus continuous transaction log capture - the combination enables point-in-time recovery. Retention configurable up to 35 days.

### 5.2 Point-in-Time Recovery (PITR)

Continuous transaction log capture lets you restore to any specific point within the retention window, not just the last snapshot moment - e.g., restore to one minute before a bad deployment corrupted data.
Restoring always creates a NEW instance - never in-place - requiring the application to cut over (connection string or DNS update).

### 5.3 Manual Snapshots

User-initiated, persist beyond automated retention (even if the instance is deleted), can be shared cross-account - same cross-account-sharing/KMS-key-policy pattern as EBS snapshots and AMIs.
Automated backups ARE deleted if you delete the instance (unless a final snapshot is retained) - manual snapshots exist for backups that must survive independent of the source instance's lifecycle.

---

## 6. Production & Enterprise Usage

- Multi-AZ + Read Replicas together is the standard production architecture - Multi-AZ as the availability floor, Read Replicas layered for genuine read-heavy workloads.
- Cross-Region Read Replicas as a DR building block - kept warm via replication, promoted during a real disaster, similar in spirit to Pilot Light/Warm Standby for the database tier.
- PITR as the standard response to application-level data corruption (bad deployment, erroneous bulk update) - distinct from Multi-AZ/Read Replicas, which replicate corrupted data everywhere too; PITR is specifically for "data as it was before the mistake."

---

## 7. Security Considerations

- Manual snapshot cross-account sharing carries the identical KMS key-policy gotcha as every other encrypted-resource-sharing scenario in this course.
- Automated backups deleted alongside the instance is itself a security consideration - an attacker or accident deleting an instance without a retained final snapshot destroys backup history too; manual cross-account-shared snapshots are the mitigation.

---

## 8. Performance Considerations

- Read Replica lag is a genuine application-design consideration - reading from a replica immediately after writing to the primary might not show the write yet (read-your-writes challenge).
- Multi-AZ's synchronous replication can add a small write-latency overhead vs non-Multi-AZ, since every write must be confirmed on the standby first - a genuine, usually small, availability-vs-latency trade-off.

---

## 9. Troubleshooting

| Symptom                                                    | Cause                                                                           | Fix                                                                                          |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| App reads stale data right after a write                   | Reading from an asynchronously-lagging Read Replica                             | Read from the primary for read-your-writes-sensitive ops, or design for eventual consistency |
| Attempted to query Multi-AZ standby directly, inaccessible | Classic Multi-AZ standbys are not readable                                      | Expected; use a Read Replica for secondary-copy read access                                  |
| Restored a backup but app still points at old instance     | Restore creates a new instance, app config wasn't updated                       | Update the app's connection string/DNS                                                       |
| Automated backup history gone after deleting an instance   | No final snapshot retained; automated backups don't survive deletion by default | Always retain a final snapshot on production deletion                                        |

---

## 10. Best Practices & Anti-Patterns

Best practices: enable Multi-AZ for any production instance as the availability floor; layer Read Replicas for genuine read-heavy workloads; use cross-Region Read Replicas as a DR building block; always retain a final snapshot on deletion; use manual cross-account-shared snapshots for independently-surviving backups.

Anti-patterns: running production RDS without Multi-AZ; assuming a Read Replica is synchronous/non-readable like Multi-AZ or vice versa; directing read-your-writes-sensitive queries to a replica without accounting for lag; deleting production without a final snapshot.

---

## 11. Common Misconceptions

- "Multi-AZ standbys can offload read traffic." False - not readable; that's what Read Replicas are for.
- "Read Replicas provide automatic failover like Multi-AZ." False - promotion is manual.
- "Restoring an RDS backup restores in place." False - always creates a new instance.
- "Deleting an RDS instance automatically preserves backup history." False unless a final snapshot is explicitly retained.

---

## 12. Interview Questions (with model answers)

Beginner - Difference between a Multi-AZ standby and a Read Replica? Multi-AZ standby: synchronous, not readable, purely for automatic zero-data-loss failover. Read Replica: asynchronous (can lag), readable, offloads read queries. Multi-AZ = availability; Read Replicas = read scaling - often used together.

Beginner - If the RDS primary fails, does a Read Replica automatically take over? No - that's Multi-AZ's job. A Read Replica must be manually promoted to a standalone writable instance - not automatic, which is why Read Replicas aren't a substitute for Multi-AZ's automatic failover.

Intermediate - How does RDS point-in-time recovery work, and why is it useful beyond a daily snapshot restore? Daily full snapshot plus continuous transaction log capture combine to let you restore to any specific point within the retention window, not just the last snapshot moment. Useful for restoring to just before a bad deployment/bulk-update mistake, rather than losing an entire day's legitimate changes between the last snapshot and the incident.

Intermediate - Why might an app hit a read-your-writes problem using Read Replicas? Asynchronous replication means a genuine lag between a primary write completing and it appearing on a replica. Writing to the primary then immediately reading from a replica might miss that write. Apps with this requirement should read from the primary for those cases or design for eventual consistency.

Senior - Design RDS architecture for read-heavy reporting, automatic failover requirement, and cross-Region DR need? Multi-AZ primary for automatic failover (synchronous, zero data loss, fast AZ-level recovery). Same-Region Read Replica(s) specifically for reporting queries, kept off the primary so they don't compete with transactional workload - async lag acceptable for reporting. Cross-Region Read Replica kept warm via replication for DR; manually promoted during an actual disaster as part of a DR runbook, paired with Route 53 Failover routing once the promoted instance and surrounding infra are ready. Appropriate automated backup retention plus a final-snapshot policy on any instance replacement, with manual snapshots for backups needing to survive independent of any single instance's lifecycle.

---

## Key Takeaways

1. Multi-AZ (synchronous, non-readable, automatic failover) and Read Replicas (asynchronous, readable, manual promotion) solve genuinely different problems - availability vs read scaling - frequently used together.
2. Read Replicas can be cross-Region, serving both latency-driven read scaling and as a DR building block requiring manual promotion.
3. RDS automated backups combine daily snapshots with continuous transaction log capture for point-in-time recovery - restore always creates a new instance.
4. Manual snapshots persist independent of the source instance's lifecycle and support cross-account sharing - the tool for backups that must survive instance/account compromise or deletion, with the same KMS key-policy gotcha.
5. The standard production pattern is Multi-AZ plus Read Replicas together - Multi-AZ as the non-negotiable availability floor, Read Replicas for genuine read-scaling/DR needs.

## Related Concepts (forward links)

- Amazon Aurora's architecturally distinct HA/replication approach (shared storage, faster replicas) -> §51
- DynamoDB's fundamentally different consistency and replication model -> §52
- Database Migration Service for moving into/between RDS deployments -> §57
