# Part 5 - Section 9 - Backup Strategies: AWS Backup & DR Patterns

AWS Zero-to-Enterprise Knowledge Base - Part 5: Storage

---

## 1. Definition

Plain-language: AWS Backup lets you define one centralized backup policy - how often to back up, how long to keep backups, whether to copy them to another Region - and apply it consistently across EBS, EFS, RDS, DynamoDB, FSx, and other services, instead of configuring backup separately for each.

Precise: AWS Backup is a centralized, policy-based backup management service across supported AWS resources, unifying scheduling, retention, cross-Region/cross-account copying, and compliance reporting into a single management plane.

---

## 2. Why It Exists

- Each service (EBS, EFS, FSx) has its own backup mechanism. Managing each separately - different schedules, retention rules, tools - across many accounts/resource types is error-prone and hard to audit.
- AWS Backup unifies this - one policy (backup plan) applied consistently across every supported resource type, extending Organizations-wide governance philosophy and IaC philosophy to backup management specifically.

---

## 3. Core AWS Backup Concepts

### 3.1 Backup Plans

Defines when backups happen (schedule), how long retained (lifecycle), and where copies go (cross-Region, cross-account) - a declarative policy, parallel to S3 lifecycle policies but generalized across resource types.

### 3.2 Resource Assignment via Tags

Backup plans assign via tags (reusing the cost-allocation-tag concept for a different purpose) - e.g., every resource tagged backup:daily automatically falls under that plan, so newly created resources with the right tag are automatically covered.

### 3.3 Backup Vaults

Backups stored in backup vaults - logical containers with their own access policies and encryption settings (KMS) - fine-grained control over backup access/deletion independent of the source resource's own permissions.

- Vault Lock - WORM protection for an entire vault, parallel to S3 Object Lock Compliance mode - "even root cannot override" immutability, generalized across resource types.

### 3.4 Cross-Region and Cross-Account Backup Copying

Backup plans can copy to another Region (DR) or another account (ransomware/compromise protection - an attacker who compromises your primary account can't also delete a backup in a separate account) - unifying the S3 CRR and EBS cross-Region snapshot patterns into one mechanism.

---

## 4. Disaster Recovery - RPO and RTO

### 4.1 Recovery Point Objective (RPO)

Answers "how much data can we afford to lose?" - a time duration. Directly determined by backup/replication frequency - CRR's asynchronous delay is a real RPO gap; nightly backups mean up to 24hr RPO; Replication Time Control's 15-min SLA tightens RPO to that bound.

### 4.2 Recovery Time Objective (RTO)

Answers "how long can we be down?" - a time duration from disaster to full recovery. Directly determined by the DR pattern chosen (Section 5) - Backup and Restore has a long RTO (provisioning + restore time); Active-Active has near-zero RTO (secondary already running).

Interview tip: RPO = data loss tolerance; RTO = downtime tolerance. Independent dimensions - you could have tight RPO/loose RTO or vice versa. Both typically trade off against cost in the same direction - tighter requirements cost more.

---

## 5. The Four DR Patterns

| Pattern                  | RPO                | RTO                  | Cost          | Description                                                                                     |
| ------------------------ | ------------------ | -------------------- | ------------- | ----------------------------------------------------------------------------------------------- |
| Backup and Restore       | Hours              | Hours to days        | Lowest        | Data backed up; infrastructure provisioned only after disaster declared                         |
| Pilot Light              | Minutes to hours   | Tens of min to hours | Low-moderate  | Minimal core infra (often just replication) runs continuously; full infra scaled up when needed |
| Warm Standby             | Seconds to minutes | Minutes              | Moderate-high | Scaled-down but fully functional environment runs continuously, scaled up on failover           |
| Multi-Site Active-Active | Near-zero          | Near-zero            | Highest       | Full production runs simultaneously in multiple Regions; failover is just routing traffic away  |

Key idea: RPO/RTO and cost move together in the same direction - tighter requirements need more continuous infrastructure, which costs more. Choosing a DR pattern is fundamentally a business decision about acceptable downtime/data-loss risk vs cost, not a purely technical choice.

---

## 6. Mapping This Course's Content to the DR Framework

- Route 53 Failover routing - the traffic-redirection mechanism for Pilot Light, Warm Standby, Active-Active once the DR Region is ready.
- S3 CRR and EBS snapshot cross-Region copying - the data-availability mechanism every pattern above Backup and Restore depends on.
- Auto Scaling Groups scaling from zero/minimal footprint - the mechanism behind Pilot Light's "scale up only when needed."
- AWS Backup itself - serves Backup and Restore most directly, though its cross-Region copying also supports the other patterns' data-availability needs.

This synthesis is exactly what a "design a DR strategy" interview question asks: select a point on the RPO/RTO/cost spectrum, then correctly assemble the specific services delivering it.

---

## 7. Production & Enterprise Usage

- AWS Backup as default for Backup-and-Restore-tier workloads, and as compliance reporting layer even for orgs using other patterns elsewhere - AWS Backup Audit Manager verifies backup plans meet compliance requirements across the estate.
- Cross-account backup copying as ransomware protection - a compromised credential deleting production AND reachable backups provides no real protection; a genuinely separate account closes that gap.
- Tiered DR strategy across a portfolio - Backup and Restore for low-priority tools, Pilot Light/Warm Standby for important-but-not-critical systems, Active-Active only for genuinely revenue-critical zero-downtime systems.

---

## 8. Security Considerations

- Vault Lock's WORM guarantee is the backup-specific parallel to S3 Object Lock Compliance mode - protects against accidental deletion and malicious/compromised-credential destruction.
- Cross-account backup copying directly mitigates "attacker with account-wide access deletes everything including backups" - a backup only as protected as the primary account isn't a genuine independent safety net.
- Backup vault access policies should follow least privilege - not every identity with source-resource access needs backup-deletion access.

---

## 9. Performance Considerations

- Backup operations can impact source resource performance during the backup window - schedule during lower-traffic periods where relevant.
- RTO is fundamentally about DR Region readiness, not just data-copy speed - Pilot Light's longer RTO reflects genuine infrastructure-provisioning time that Warm Standby/Active-Active eliminate by staying already-running.

---

## 10. Troubleshooting

| Symptom                                                          | Cause                                                                         | Fix                                                             |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------- |
| New resource not backed up despite existing plan                 | Resource not tagged to match plan's assignment criteria                       | Verify correct tags matching the plan's rules                   |
| Backups deleted along with production during an incident         | Backups in same account/credential scope as production, no cross-account copy | Implement cross-account backup copying                          |
| DR failover took much longer than expected                       | Backup and Restore chosen for a workload needing tighter RTO                  | Reassess actual business RTO; consider Pilot Light/Warm Standby |
| Compliance audit can't confirm backup policies followed org-wide | No centralized backup governance/reporting                                    | Use AWS Backup Audit Manager                                    |

---

## 11. Best Practices & Anti-Patterns

Best practices: use tag-based resource assignment for automatic coverage of new resources; copy backups cross-account for ransomware protection; use Vault Lock for compliance-critical immutability; match DR pattern to actual business RPO/RTO/criticality; use Audit Manager for centralized compliance reporting.

Anti-patterns: configuring backup separately/inconsistently per service instead of centralizing; storing all backups in the production account with no cross-account copy; applying Backup and Restore uniformly to genuinely critical systems; treating DR pattern selection as purely technical without business cost/risk input.

---

## 12. Common Misconceptions

- "A backup automatically protects against ransomware." False if in the same account/credential scope - genuine protection needs cross-account isolation.
- "RPO and RTO measure the same thing." False - data loss tolerance vs downtime tolerance, independent dimensions.
- "The most expensive DR pattern (Active-Active) is always right." False - should match actual business criticality; over-engineering wastes money.
- "AWS Backup replaces each service's native backup mechanism." Not quite - it's a unifying management/orchestration layer over those mechanisms, not a wholesale replacement.

---

## 13. Interview Questions (with model answers)

Beginner - What problem does AWS Backup solve? Without it, backup is configured separately per service with different schedules/retention/tools - hard to manage/audit consistently at scale. AWS Backup centralizes into one policy-based service across every supported resource type.

Beginner - Difference between RPO and RTO? RPO: how much data you can afford to lose, a time duration determined by backup/replication frequency. RTO: how long you can be down, time from disaster to full recovery. Independent - tight RPO with loose RTO or vice versa is possible; a complete DR strategy addresses both.

Intermediate - Why copy backups to a separate account rather than just a different Region in the same account? Same-account backups share the security boundary with production - a compromised credential could delete both. A genuinely separate account with separate credentials means an attacker compromising the primary account still can't reach the backup copy - specifically ransomware protection, distinct from cross-Region's DR purpose.

Intermediate - Why does Pilot Light have a longer RTO than Warm Standby despite both running some continuous DR infrastructure? Pilot Light keeps only minimal infrastructure running (often just replication/small core) - the rest must be provisioned/scaled from near-nothing on disaster, taking real time. Warm Standby keeps a scaled-down but fully functional environment running continuously - failover is mostly scaling up an already-running environment. Warm Standby's larger continuous footprint buys faster RTO at higher continuous cost.

Senior - Leadership wants "the best possible DR" for all systems - how do you respond? Reframe as a business decision, not purely technical - "best possible" (near-zero RPO/RTO via Active-Active everywhere) is also the most expensive option; applying it to non-critical internal tools wastes budget without benefit. Work with leadership to classify systems by actual business criticality (revenue-generating, contractual/regulatory uptime commitments, internal-only tolerating hours of downtime) and map each tier to the DR pattern matching its cost-of-downtime against DR infrastructure cost. Active-Active/Warm Standby for the most critical revenue systems; Backup and Restore adequate for internal tools. Turns an open-ended expensive mandate into a deliberately tiered, cost-justified strategy.

---

## Key Takeaways

1. AWS Backup unifies backup management across resource types - one policy-based plan applied via tags, rather than separate inconsistent native mechanisms.
2. RPO (data loss tolerance) and RTO (downtime tolerance) are independent dimensions, both shaped by how much infrastructure/replication runs continuously vs only after a disaster.
3. The four DR patterns (Backup and Restore, Pilot Light, Warm Standby, Active-Active) form a spectrum where RPO/RTO tightness and cost move together - a business decision about acceptable risk vs cost.
4. Cross-account backup copying is distinct protection from cross-Region copying - guards against compromised-account backup destruction vs Region-wide disaster.
5. Nearly every DR-adjacent mechanism from Parts 1-5 (Route 53 Failover, CRR/snapshot copying, Auto Scaling, AWS Backup) assembles into this framework - the chosen pattern determines which combination is needed.

## Related Concepts (forward links)

- Part 5 Wrap-Up and comprehensive Storage interview drill -> §48 (final section)
- RDS's own backup/Multi-AZ mechanics building directly on these DR pattern concepts -> Part 6
- The Well-Architected Framework's Reliability pillar, formalizing DR strategy selection -> Part 10
