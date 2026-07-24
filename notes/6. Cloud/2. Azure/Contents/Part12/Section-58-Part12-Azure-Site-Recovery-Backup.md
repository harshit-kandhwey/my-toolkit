# Section 58 — Azure Site Recovery & Backup

**Part 12: High Availability, DR, Scaling & Cost | Section 58 of 70**
**Prerequisites:** Section 57 (HA/DR Patterns, RTO/RPO), Section 18.14/19.14 (Disk/Files snapshots), Section 28.15 (SQL Business Continuity), Section 37.5.2 (Velero for AKS)
**Leads into:** Section 59 (Autoscaling Strategies)

---

## 58.1 Introduction and Scope

This section covers the concrete Azure services implementing the DR pattern spectrum introduced in Section 57.6: **Azure Site Recovery (ASR)** for orchestrated compute/VM-level disaster recovery replication and failover, and **Azure Backup** for data protection and recovery. This section also consolidates and cross-references the resource-specific backup mechanisms already covered piecemeal throughout this roadmap (Section 18.14's disk snapshots, Section 19.14's Azure Files snapshots, Section 28.15's SQL backup/geo-replication, Section 37.5.2's Velero for AKS) into one coherent backup strategy framework, and precisely distinguishes ASR from Azure Backup — two frequently confused services addressing genuinely different problems.

🔑 **Key Takeaway:** Azure Site Recovery and Azure Backup answer different questions. **ASR answers "how do I keep an entire VM/application running and ready to fail over to a secondary region with minimal downtime"** (continuous replication for DR, addressing RTO primarily). **Azure Backup answers "how do I recover specific data to a point in time"** (periodic backup for data protection and recovery from data loss/corruption, addressing RPO and data-recovery scenarios primarily, including scenarios that have nothing to do with a regional disaster at all — like recovering from accidental deletion or ransomware). They are complementary, often used together, but solve genuinely different problems.

---

## 58.2 Azure Site Recovery (ASR)

### 58.2.1 Definition

**Plain language:** Azure Site Recovery continuously replicates the state of running VMs (Azure-to-Azure, on-premises-to-Azure, or between on-premises sites) to a secondary location, and orchestrates a coordinated failover of an entire multi-VM application to that secondary location during a disaster — implementing the "warm standby" and "pilot light" points on Section 57.6.1's DR pattern spectrum as an actual, concrete Azure service.

**Precise definition:** Azure Site Recovery is a disaster recovery orchestration service that continuously replicates VM disk state to a target region (or on-premises site), maintains a configurable recovery point history, and executes coordinated, ordered failover of grouped VMs (via **recovery plans**) to bring a multi-tier application online in the target location with minimal manual intervention.

### 58.2.2 Why It Exists — What It Solves Beyond Manual DR

- **Continuous replication vs. periodic backup:** unlike a backup (a periodic snapshot, 58.3), ASR maintains near-continuous, ongoing replication of VM disk changes to the target location — meaning the target location's replica is kept much more current than a backup taken on a schedule (hourly/daily), directly supporting a much lower RPO than backup-and-restore alone could achieve.
- **Orchestrated, multi-VM failover via Recovery Plans:** a real application is rarely a single VM — it's typically a multi-tier system (web tier, application tier, database tier) with startup-order dependencies. Manually failing over each VM individually, in the correct order, with correct post-failover configuration steps (updating connection strings, DNS records) is exactly the kind of error-prone, high-stress manual process ASR's **Recovery Plans** automate — defining the exact group/order/scripted-step sequence for bringing an entire application online in the target region with a single, orchestrated failover action, directly addressing RTO by removing manual, error-prone coordination from the critical path during an actual disaster.
- **Non-disruptive testing:** ASR supports **test failover** — validating that failover actually works correctly, in an isolated network environment that doesn't affect the actual production primary or the real target-region network, directly implementing Section 57.7.2's "DR procedures must actually be tested" guidance as a first-class, built-in ASR capability rather than requiring the customer to build their own separate testing mechanism.

### 58.2.3 Replication Mechanics

- ASR performs an initial full replication of the source VM's disks to the target location, then continuously replicates ongoing disk changes (a form of continuous/near-continuous data replication, distinct from periodic backup snapshots) — maintaining the target as a近-current, ready-to-activate (but not actively running/consuming full compute cost) replica.
- **Recovery points:** ASR maintains multiple recovery points over a retention window (not just the single most-current replicated state), allowing failover to a specific prior point in time if the most recent replicated state itself reflects a problem (e.g., replicating a corrupted or compromised state) — directly relevant to a ransomware-recovery scenario where failing over to the _most recent_ state would simply replicate the compromise; being able to select an earlier, pre-compromise recovery point is essential.

### 58.2.4 Recovery Plans

```
Recovery Plan: "E-Commerce Platform Failover"
  Group 1 (start first): Database tier VMs
  Group 2 (start after Group 1): Application tier VMs
  Group 3 (start after Group 2): Web tier VMs
  Scripted step (between Group 2 and 3): Update application config with new database connection endpoint
  Scripted step (after Group 3): Update DNS/Traffic Manager to point to failed-over region
```

- **Groups** define ordered startup sequencing — directly analogous in purpose to Section 46.2.3's environment-promotion pipeline structure and Section 42.4.3's `dependsOn` stage ordering, now applied to disaster-recovery failover sequencing specifically, the same "ensure dependencies come online before dependents" principle recurring in yet another context.
- **Scripted/manual action steps** embedded within a Recovery Plan can perform necessary post-failover configuration (updating connection strings to point at the now-active target-region database, updating DNS records via Azure Traffic Manager or Front Door, Section 25) as an integrated part of the automated failover sequence rather than a separate, easily-forgotten manual follow-up task.

### 58.2.5 ASR for AKS — A Notable Gap

⚠️ **Warning:** Azure Site Recovery, as covered in this section, is fundamentally a **VM-replication** service — it does not natively support AKS clusters as a first-class replication/failover target the way it does for VMs. AKS-specific DR (Section 37.5.3's original material) instead relies on GitOps-based cluster/manifest reconstruction in a secondary region (reconstructing the cluster's _configuration_ from source-controlled manifests, rather than replicating a running cluster's exact state) combined with the underlying database/storage layer's own geo-replication mechanisms (SQL failover groups, Section 28.15; Cosmos DB multi-region, Section 29) for the actual _data_ — a genuinely different DR architecture pattern from ASR's VM-replication model, worth being precise about rather than assuming ASR is a universal DR solution applicable identically to every compute type covered in this roadmap.

---

## 58.3 Azure Backup

### 58.3.1 Definition

**Plain language:** Azure Backup provides scheduled, retained, point-in-time backup and recovery for VMs, databases, file shares, and other data sources — the mechanism for recovering from data loss, corruption, accidental deletion, or ransomware, distinct from ASR's continuous-replication-for-regional-failover purpose.

**Precise definition:** Azure Backup is a backup-as-a-service platform providing application-consistent, scheduled backup of supported Azure and on-premises workloads to a **Recovery Services vault**, with configurable retention policies and point-in-time restore capability.

### 58.3.2 Recovery Services Vault

- The central storage/management resource for Azure Backup (and also used by ASR for its own configuration/orchestration data, though the two services' actual replicated/backed-up data serve different purposes as established in 58.2/58.3) — directly analogous in organizational role to a Log Analytics workspace (Section 47–48) or Key Vault (Section 53) as a central, RBAC-governed resource that specific backup policies target.

### 58.3.3 Backup Policies and Retention

- A **backup policy** defines schedule (how often backups are taken) and retention (how long each backup is kept, potentially with different retention tiers — e.g., daily backups retained 30 days, weekly backups retained a year, monthly backups retained 5 years) — directly connecting to Section 55.8.2's compliance-driven retention requirements, now understood as a concrete, configurable Azure Backup policy setting rather than an abstract requirement.
- **Application-consistent vs. crash-consistent backups:** a crash-consistent backup captures disk state as if the VM had simply lost power (potentially leaving an application, particularly a database, in an inconsistent state requiring its own crash-recovery process upon restore); an application-consistent backup coordinates with the application (e.g., via VSS — Volume Shadow Copy Service on Windows, or application-specific pre/post scripts on Linux) to ensure the backed-up state reflects a consistent, valid application state — a meaningful, commonly-tested distinction, with application-consistent backups being the generally preferred, safer option wherever supported for database/stateful workloads specifically.

### 58.3.4 Consolidating This Roadmap's Resource-Specific Backup References

🔑 **Key Takeaway, directly synthesizing prior sections:** several resource-specific backup mechanisms already covered throughout this roadmap are either implemented via, or conceptually parallel to, Azure Backup's general model:

| Prior Section  | Mechanism                                                                                        | Relationship to This Section                                                                                                                                                                                                                                                                                                                                                                                                                              |
| -------------- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Section 18.14  | Managed Disk snapshots/incremental snapshots                                                     | A disk-native snapshot capability, usable independently or orchestrated as part of a broader Azure Backup policy for VM backup specifically                                                                                                                                                                                                                                                                                                               |
| Section 19.14  | Azure Files soft delete and share snapshots                                                      | A Files-native protection mechanism, distinct from but complementary to Azure Backup's own Azure Files backup support                                                                                                                                                                                                                                                                                                                                     |
| Section 28.15  | SQL Database automated backups, PITR, Long-Term Retention (LTR), geo-replication/failover groups | SQL Database has its own fully-managed, built-in backup system (distinct from the general Azure Backup service, though conceptually following the same schedule/retention/point-in-time-restore model) — a specific, important distinction: not every Azure data service is backed up _via_ the general Azure Backup service; several PaaS data services (SQL Database prominent among them) have their own dedicated, built-in backup capability instead |
| Section 37.5.2 | Velero for AKS persistent volumes and Kubernetes object definitions                              | A third-party, Kubernetes-native backup tool (not Azure Backup itself), specifically because AKS's application/object-definition backup needs (Kubernetes manifests) fall outside Azure Backup's native scope, while the underlying persistent volume data (Azure Disks/Files) can still leverage Section 18.14/19.14's storage-layer mechanisms or Velero's own coordinated approach                                                                     |

⚠️ **Warning, precisely important for interviews:** **not every Azure data service backup mechanism is "Azure Backup"** — SQL Database's backup system (Section 28.15) is its own dedicated, PaaS-native capability, separate from the general Azure Backup service covered in this section, even though both follow a broadly similar schedule/retention/restore conceptual model. Precisely distinguishing "this resource type has its own dedicated backup system" from "this resource type is backed up via the general Azure Backup service" is a specific, valuable, commonly-tested distinction — conflating them (assuming Azure Backup is the single, universal mechanism for every Azure data service) is a real and common inaccuracy worth actively avoiding.

---

## 58.4 Azure Backup vs. Azure Site Recovery — The Direct, Commonly-Tested Comparison

| Aspect                     | Azure Site Recovery                                                                                | Azure Backup                                                                                                                                             |
| -------------------------- | -------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Primary purpose            | Regional disaster recovery — keep an application ready to fail over with minimal downtime          | Data protection and point-in-time recovery — recover from data loss, corruption, accidental deletion, ransomware                                         |
| Replication/backup model   | Near-continuous replication                                                                        | Scheduled, periodic backup (with configurable frequency)                                                                                                 |
| Typical RTO characteristic | Low (minutes, orchestrated via Recovery Plans)                                                     | Higher (time to restore from a backup and bring the restored resource online)                                                                            |
| Typical RPO characteristic | Low (near-continuous replication minimizes data loss)                                              | Determined by backup frequency (e.g., a daily backup policy has an inherent RPO of up to 24 hours for that specific backup's data)                       |
| Scope                      | Whole-VM (and orchestrated multi-VM application) replication and failover                          | Individual resource-type backup (VM, database, file share) and point-in-time restore, not necessarily whole-application orchestrated failover            |
| Typical use case           | "Our primary region just became unavailable; bring the application up in the secondary region now" | "Someone accidentally deleted a critical file/database three days ago; restore it" or "We were hit by ransomware; restore to a pre-attack point in time" |

🎯 **Interview Tip:** a precise answer to "when would you use ASR vs. Azure Backup" names the specific failure scenario each is actually designed for — ASR for regional unavailability requiring fast, orchestrated multi-VM failover; Azure Backup for data-level loss/corruption/malicious-deletion recovery, regardless of whether the primary region is even affected at all (a ransomware attack or accidental deletion doesn't require a regional outage to occur, making Azure Backup relevant even in scenarios entirely unrelated to Section 57's regional-DR framing) — and, critically, that mature production architectures typically use **both**, since they protect against genuinely different failure categories.

---

## 58.5 Production and Enterprise Usage

### 58.5.1 Backup as Ransomware/Malicious-Deletion Protection Specifically

- Directly extending 58.4's table: Azure Backup's retained, immutable (with soft-delete protection for backup data itself, directly paralleling Section 53.6's Key Vault soft-delete concept, now applied to backup data) point-in-time recovery points provide a specific, critical defense against ransomware — an attacker who encrypts/corrupts production data cannot also retroactively corrupt already-taken, retained backup recovery points, allowing restoration to a pre-attack point in time. This is a genuinely distinct value proposition from ASR, which — if the ransomware encryption were replicated to the ASR target before detection — would simply propagate the corrupted state to the secondary region as well, underscoring why backup's point-in-time retention (not just replication) is specifically valuable for this threat category.

### 58.5.2 Cross-Region Backup Storage

- Azure Backup's Recovery Services vault can be configured with **geo-redundant storage** (Section 20's redundancy concepts, applied directly here) for the backup data itself, ensuring the backups remain available even if the primary region storing the vault becomes unavailable — a specific, important detail ensuring the backup mechanism itself isn't a single point of failure correlated with the exact regional disaster it might otherwise be needed to recover from.

### 58.5.3 DR/Backup Testing Cadence (Direct Extension of Section 57.7.2)

- Regular test failovers (ASR, 58.2.2) and regular restore drills (Azure Backup) should both be scheduled, recurring operational practices — directly extending Section 57.7.2's "untested DR cannot be trusted" warning to both services covered in this section specifically, not merely a general principle stated once and left abstract.

---

## 58.6 Troubleshooting Reference

| Symptom                                                                                                              | Likely Cause                                                                                                                                                                       | Diagnostic Step                                                                                                                                                                             |
| -------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| ASR failover takes significantly longer than expected                                                                | Recovery Plan group/ordering misconfiguration, or scripted action steps failing/timing out during actual execution                                                                 | Review the specific Recovery Plan's group sequencing and script step logs from the failover operation; validate via test failover (58.2.2) before relying on the plan in an actual disaster |
| A restored backup is missing recent data                                                                             | Restore was performed from an older recovery point than intended, or the backup policy's schedule frequency inherently has a larger RPO gap than assumed                           | Verify the specific recovery point selected matches the intended point in time; review backup policy schedule frequency against actual RPO requirements                                     |
| SQL Database "backup" question in an interview/documentation context causes confusion about which service manages it | Conflating SQL Database's own dedicated backup system with the general Azure Backup service (58.3.4's specific warning)                                                            | Clarify which specific backup mechanism applies to the resource type in question — not every data service uses the general Azure Backup service                                             |
| Ransomware attack also corrupted the DR replica                                                                      | ASR's continuous replication propagated the corruption/encryption to the target region before detection, since ASR is a replication mechanism, not a point-in-time-retained backup | Restore from Azure Backup's retained recovery points instead (58.5.1), selecting a point in time before the attack occurred                                                                 |
| Backup/restore drill reveals missing dependencies or incorrect assumptions in the runbook                            | Untested procedure, exactly the gap Section 57.7.2 warns about                                                                                                                     | Update the runbook/Recovery Plan based on findings; schedule regular, recurring test cadence going forward                                                                                  |

---

## 58.7 Best Practices Checklist

- [ ] ASR and Azure Backup both deployed for production-critical workloads, understood as addressing genuinely different failure categories (regional DR vs. data-level recovery) rather than one substituting for the other.
- [ ] Recovery Plans (ASR) correctly sequenced by application-tier dependency order, with necessary post-failover configuration steps (DNS/connection-string updates) embedded as scripted actions.
- [ ] Test failovers (ASR) and restore drills (Azure Backup) conducted on a regular, recurring schedule, not left as untested, documentation-only procedures.
- [ ] Backup policy retention tiers aligned with actual compliance/business retention requirements (Section 55.8.2), not left at a default without review.
- [ ] Application-consistent backups used for database/stateful workloads wherever supported, rather than accepting crash-consistent backups by default.
- [ ] Awareness maintained of which specific resource types have their own dedicated PaaS-native backup system (e.g., SQL Database) versus which are backed up via the general Azure Backup service — not assumed uniformly the same mechanism.
- [ ] Recovery Services vault (and its backup data) configured with geo-redundant storage, ensuring the backup mechanism itself isn't correlated with the exact regional disaster it may be needed to recover from.

---

## 58.8 Common Misconceptions

- "Azure Site Recovery and Azure Backup are essentially the same service with different names." _Correction:_ ASR provides near-continuous replication for regional DR/fast failover; Azure Backup provides scheduled, retained, point-in-time backup for data-level recovery — genuinely different purposes, RTO/RPO characteristics, and threat-scenario applicability (58.4's full comparison).
- "Having Azure Site Recovery configured means ransomware-encrypted data can always be recovered by failing over." _Correction:_ ASR's continuous replication would propagate ransomware corruption to the target region if not caught before replication occurs — retained, point-in-time Azure Backup recovery points are the actually appropriate recovery mechanism for this specific threat (58.5.1).
- "Every Azure data service uses the same general Azure Backup service for its backup needs." _Correction:_ several PaaS data services (SQL Database prominently) have their own dedicated, built-in backup system, distinct from the general Azure Backup service covered in this section (58.3.4's specific, important warning).

---

## 58.9 Interview Questions (Consolidated)

**Beginner:** "What is the difference between Azure Site Recovery and Azure Backup?"
_Model answer:_ Azure Site Recovery provides near-continuous replication of VMs to a secondary location, with orchestrated, ordered multi-VM failover (via Recovery Plans) for regional disaster recovery, targeting low RTO/RPO for bringing an entire application online in a secondary region. Azure Backup provides scheduled, retained, point-in-time backup and restore for data protection — recovering from data loss, corruption, accidental deletion, or ransomware, which can be relevant even without any regional outage occurring at all. They address different failure categories and are commonly used together in a complete resilience strategy.

**Intermediate:** "Why is Azure Backup, rather than Azure Site Recovery, generally the appropriate recovery mechanism after a ransomware attack?"
_Model answer:_ Azure Site Recovery continuously replicates ongoing changes to a target location — if ransomware encryption occurred before detection, that corrupted/encrypted state would be replicated to the ASR target as well, since ASR's model is "keep the target current with the source," not "retain a history of past states." Azure Backup, by contrast, retains multiple distinct point-in-time recovery points over a retention window — allowing restoration to a specific point _before_ the attack occurred, which ASR's continuous-replication model doesn't provide in the same way (though ASR does maintain some recovery point history, 58.2.3, backup's retention-focused design is the more directly appropriate tool for this specific "recover to a known-good prior state" need).

**Senior:** "A team configured Azure Site Recovery for their production VMs and considers their disaster recovery complete, with no separate Azure Backup configuration. What gap would you flag, and why?"
_Model answer:_ ASR alone leaves the organization without protection against data-level loss/corruption/malicious-deletion scenarios that don't involve a regional disaster at all — an accidental deletion of a critical file, a database corruption bug, or a ransomware attack would either have no recovery mechanism at all, or (in the ransomware case specifically) risk the corrupted state being propagated to the ASR target via continuous replication before detection (58.5.1's specific risk). ASR addresses "the region became unavailable" specifically; it does not address "our data was corrupted or maliciously deleted while the region remains perfectly available" — a distinct, equally real failure category requiring Azure Backup's retained, point-in-time recovery capability specifically. The team's DR posture should be considered incomplete without both services deployed for genuinely production-critical workloads, addressing their respective, non-overlapping failure categories.
_What the interviewer is probing:_ precise recognition that ASR and Backup are not redundant or substitutable, and the ability to name a specific, realistic failure scenario (ransomware, accidental deletion) that ASR alone leaves entirely unprotected against — directly reinforcing 58.4's core comparison with a concrete, consequential example.

**Architect / Scenario:** "Design a complete backup and DR strategy for the revenue-critical checkout service (the recurring example from Sections 46/57), including protection against both regional disaster and ransomware/accidental data loss, with a defined RTO of 1 hour and RPO of 5 minutes."
_Model answer:_ deploy **Azure Site Recovery** for the checkout service's VM-tier components (if any VM-based components exist in the architecture; for an AKS-hosted service specifically, per 58.2.5's important gap, rely instead on GitOps-based cluster reconstruction combined with the database layer's own geo-replication rather than ASR directly) with a Recovery Plan sequencing database, application, and web tiers in correct dependency order and embedding DNS/connection-string update steps — targeting the stated 1-hour RTO, validated via regular test failovers (58.2.2/58.5.3) to confirm the actual achieved RTO meets the target, not merely assumed to. For the stated 5-minute RPO, ensure the underlying database layer (Section 28's SQL Database, per this recurring example) is configured with synchronous or near-synchronous geo-replication/failover groups (Section 28.15) capable of genuinely meeting a 5-minute RPO — since ASR's own replication cadence and the database's own replication mechanism both need to independently satisfy this tight RPO target, this is a case where the database-layer replication configuration (Section 28.15), not ASR alone, is the actual RPO-determining factor for the stateful component. Separately and additionally, configure **Azure Backup** with a policy providing frequent (e.g., hourly or more frequent, depending on what the database's own PITR capability from Section 28.15 already provides, potentially making a separate Azure Backup configuration redundant specifically for the SQL Database tier given its own dedicated backup system per 58.3.4) point-in-time recovery specifically as ransomware/accidental-deletion protection, independent of and complementary to the ASR-based regional-failover capability — ensuring that a ransomware attack or accidental deletion, which the stated 1-hour-RTO/5-minute-RPO DR target doesn't specifically address (since it's not a regional-availability failure), has its own appropriate recovery path via retained point-in-time backups. Schedule regular, recurring test failovers and restore drills for both mechanisms (58.5.3), since an untested strategy meeting these tight, business-critical RTO/RPO targets on paper provides no actual assurance without verified, repeated execution.
_What the interviewer is probing:_ the ability to design a complete, dual-mechanism strategy (ASR for regional DR, Backup for data-level recovery) addressing both named threat categories with specific, numeric RTO/RPO targets, while correctly identifying that a stateful component's actual RPO achievement depends on the database layer's own replication configuration (not ASR alone) and correctly flagging the AKS-specific ASR gap from 58.2.5 rather than assuming ASR applies uniformly to every possible compute type in the architecture.

---

## 58.10 Key Takeaways Summary

🔑 Azure Site Recovery (near-continuous replication, orchestrated multi-VM failover, addressing regional DR) and Azure Backup (scheduled, retained, point-in-time recovery, addressing data-level loss/corruption/ransomware) solve genuinely different problems and are typically used together, not as substitutes for one another.

🔑 Ransomware recovery specifically favors Azure Backup's retained point-in-time recovery points over ASR's continuous replication, since continuous replication would propagate an undetected attack's corruption to the secondary region.

🔑 Not every Azure data service is backed up via the general Azure Backup service — several PaaS services (SQL Database prominently) have their own dedicated, built-in backup system, a precise and commonly-tested distinction.

🔑 Azure Site Recovery is fundamentally VM-centric; AKS-specific DR (Section 37.5.3) relies on a genuinely different pattern (GitOps-based reconstruction plus database-layer geo-replication), not ASR directly — an important, specific gap to recognize rather than assuming universal ASR applicability.

🔑 Both ASR test failovers and Azure Backup restore drills must be conducted regularly and actually executed, directly extending Section 57.7.2's "untested DR cannot be trusted" principle to both concrete services covered in this section.

---

## 58.11 Related Concepts and What Comes Next

- **Section 57 (prerequisite, completed):** the RTO/RPO metrics and DR pattern spectrum this section's ASR/Backup material provides the concrete implementation mechanisms for.
- **Section 18.14/19.14/28.15/37.5.2 (prerequisite, completed):** the resource-specific backup mechanisms consolidated and precisely distinguished from the general Azure Backup service in 58.3.4.
- **Section 59 — Autoscaling Strategies (next):** shifts from resilience/recovery to elastic capacity management — a related but distinct operational concern completing this Part's HA/DR/Scaling/Cost coverage.
- **Section 25 (prerequisite, completed):** Azure Front Door/Traffic Manager, referenced in this section's Recovery Plan DNS-update scripted-action example (58.2.4).
- **Section 55.8.2 (prerequisite, completed):** compliance-driven retention requirements, directly connecting to this section's backup policy retention-tier configuration guidance.

---

_End of Section 58. Next: Section 59 — Autoscaling Strategies._
