# Part 10, Section 4: Disaster Recovery Strategy — Capstone

## 1. Definition

**Plain language:** This is the Reliability-pillar counterpart to §3's Cost capstone — not a new AWS service, but a synthesis of how the durability, redundancy, and automation patterns taught throughout this entire roadmap (multi-AZ architecture, backups, IaC, automated failover) come together into an actual, defensible disaster recovery strategy, chosen deliberately based on two numbers every DR conversation ultimately comes down to: how much data can you afford to lose, and how long can you afford to be down.

**Precise definition:** A disaster recovery (DR) strategy defines how an organization recovers system availability and data after a significant failure (an AZ outage, a regional outage, data corruption, or a catastrophic operational error), characterized by two target metrics — **Recovery Point Objective (RPO)**, the maximum acceptable data loss measured in time, and **Recovery Time Objective (RTO)**, the maximum acceptable downtime — with AWS's four standard DR strategy patterns (Backup & Restore, Pilot Light, Warm Standby, Multi-Site Active/Active) offering different RPO/RTO/cost trade-off points along the same spectrum.

## 2. Why It Exists / Problem It Solves

Every service covered in this roadmap has its own individual durability story — S3's eleven-nines durability, RDS Multi-AZ failover, DynamoDB's multi-AZ replication by default. But **DR strategy is a system-level concern**, not a per-service one: even if every individual component is internally durable, an entire region becoming unavailable, a catastrophic operational mistake deleting production data, or a security incident requiring full environment reconstruction all require a coordinated, tested, organization-level recovery plan — not just trusting that each service's own internal redundancy will somehow add up to genuine system-level recoverability.

This capstone exists to synthesize the individual durability/backup/automation patterns from across this roadmap into the specific, named DR strategies AWS itself defines, and to make explicit the RPO/RTO/cost trade-off that should drive the choice between them — directly extending the Well-Architected Reliability pillar (§89) and the cost-trade-off thinking from §90-91 into a concrete, interview-common architecture topic.

## 3. Prerequisites and Dependencies

- **Well-Architected Framework** (§89): DR strategy selection is a direct, concrete application of the Reliability-vs-Cost pillar trade-off.
- **Multi-AZ/Multi-Region architecture concepts** (Part 3, Part 4, Part 6): the underlying redundancy mechanisms every DR strategy builds on.
- **Backup services and Route 53** (Part 5, Part 4): the specific mechanisms (AWS Backup, DNS failover) commonly implementing DR strategies in practice.
- **CloudFormation/CDK/Terraform** (§79-82): DR strategies at the Pilot Light/Warm Standby/Active-Active end of the spectrum depend on IaC to reliably and quickly stand up or scale a secondary environment.

## 4. RPO and RTO — The Two Numbers That Drive Everything

- **RPO (Recovery Point Objective)** answers: "how much data can we afford to lose?" — measured backward in time from the moment of failure. An RPO of 1 hour means, in the worst case, up to one hour of data created since the last successful backup/replication point could be lost.
- **RTO (Recovery Time Objective)** answers: "how long can we afford to be down?" — measured as the maximum acceptable time between failure and full recovery.
- These two numbers are **business decisions**, not technical ones — they should come from actual business-impact analysis (what does an hour of downtime cost this specific business, what does losing an hour of data mean for this specific data), and the DR _architecture_ is then selected to actually achieve the RPO/RTO the business has determined it needs, at a cost the business is willing to pay for that level of protection.

## 5. The Four AWS DR Strategies, In Depth

### 1. Backup & Restore

- Data is regularly backed up (AWS Backup, Part 5, or service-native snapshots) to a separate location (often a different region); in a disaster, infrastructure is provisioned from scratch (ideally via IaC, §79-82) and data restored from backup.
- **Highest RPO/RTO** (slowest recovery, most potential data loss since the last backup) but **lowest cost** — no standby infrastructure running at all between backups.
- Appropriate for: lower-criticality workloads where hours-to-a-day of downtime and data loss up to the last backup interval are genuinely tolerable.

### 2. Pilot Light

- Core, hard-to-quickly-recreate components (typically the database) are kept continuously running and replicated in the secondary region at minimal scale; the rest of the application stack (compute) exists only as IaC templates, ready to be rapidly provisioned and scaled up when needed.
- **Lower RTO than Backup & Restore** (the data tier is already warm; only compute needs to be stood up), **moderate cost** (a small, continuously-running secondary database).
- Appropriate for: workloads where the database is the slowest, hardest thing to recover, but compute can be provisioned quickly via IaC when actually needed.

### 3. Warm Standby

- A **scaled-down but fully functional** version of the complete application stack runs continuously in the secondary region — not just the database, but application servers too, just running at lower capacity than production.
- **Lower RTO than Pilot Light** (everything is already running; failover means scaling up and redirecting traffic, not provisioning from scratch), **higher cost** (a continuously-running, if smaller, full secondary environment).
- Appropriate for: workloads with meaningful availability requirements where the additional continuous cost is justified by faster recovery than Pilot Light provides.

### 4. Multi-Site Active/Active

- The **full-scale application runs simultaneously in multiple regions**, actively serving production traffic in all of them (not standby at all) — a regional failure simply means traffic routes away from the failed region to the others, which were already handling live traffic.
- **Lowest RTO** (near-zero — no failover "activation" step at all, since the other region(s) are already fully live), **highest cost** (full production-scale infrastructure running redundantly, continuously, in every region).
- Appropriate for: the highest-criticality workloads where even minutes of downtime carry severe, unacceptable business cost, and the organization can justify the substantial ongoing cost of true multi-region active capacity.

## 6. Comparison Table

| Strategy                 | RPO                         | RTO                        | Relative Cost | Underlying Mechanism                                           |
| ------------------------ | --------------------------- | -------------------------- | ------------- | -------------------------------------------------------------- |
| Backup & Restore         | Highest (since last backup) | Highest (hours+)           | Lowest        | AWS Backup/snapshots + IaC-driven rebuild                      |
| Pilot Light              | Moderate                    | Moderate (tens of minutes) | Low-Moderate  | Continuously replicated data tier + IaC-driven compute standup |
| Warm Standby             | Low                         | Low (minutes)              | Moderate-High | Continuously running, scaled-down full stack                   |
| Multi-Site Active/Active | Near-zero                   | Near-zero                  | Highest       | Full-scale, simultaneously active multi-region deployment      |

## 7. Interview Questions with Model Answers

**🎯 Junior:** _"What do RPO and RTO mean, and why are they described as business decisions rather than technical ones?"_
**Model answer:** RPO is how much data you can afford to lose, measured in time — if your last backup was an hour ago and disaster strikes now, an RPO of one hour means losing up to that hour of data is acceptable. RTO is how long you can afford to be down before recovery is complete. They're business decisions because the right answer depends on what downtime or data loss actually costs this specific business — a one-hour outage might be a minor inconvenience for an internal reporting tool but a severe financial and reputational event for a payments platform, so the acceptable RPO/RTO, and therefore the DR architecture that's actually justified, is different for each, and that determination has to come from understanding the real business impact, not from a technical default.

**🎯 Intermediate:** _"Explain the difference between Pilot Light and Warm Standby, and what specifically improves as you move from one to the other."_
**Model answer:** In Pilot Light, only the data tier — typically the database — is kept continuously running and replicated in the secondary region; the application/compute layer exists only as infrastructure-as-code templates that get provisioned and scaled up when an actual disaster occurs. In Warm Standby, the entire application stack, not just the database, is already running continuously in the secondary region, just at reduced scale. What improves moving from Pilot Light to Warm Standby is RTO specifically — Warm Standby's recovery is largely just scaling up already-running infrastructure and redirecting traffic, whereas Pilot Light still requires actually provisioning and starting the compute layer from templates during the disaster itself, which takes meaningfully longer even with good IaC automation. The trade-off is that Warm Standby costs more continuously, since you're paying for a running (if smaller) full stack all the time, not just a database.

**🎯 Senior:** _"A team says they want 'the best possible DR strategy' for a new service without specifying an actual RPO/RTO requirement. How do you respond?"_
**Model answer:** I'd push back on "the best possible" as the framing, since Multi-Site Active/Active — the strategy with the best RPO/RTO — also carries the highest ongoing cost, running full-scale infrastructure redundantly in multiple regions continuously, and that cost is very unlikely to be justified for every service in an organization's portfolio. Instead of "best possible," I'd ask them to actually quantify what an outage or data loss would cost this specific service's business — how much revenue or trust is lost per hour of downtime, what happens if the last hour of data is gone — since that's what should actually drive the RPO/RTO target, and therefore which of the four strategies is genuinely appropriate, rather than defaulting to the most expensive option without evidence it's needed, or defaulting to the cheapest option without checking whether it's actually sufficient for this specific service's real risk profile.

**🎯 Architect:** _"Design a DR strategy portfolio for an organization running 50 services with meaningfully different criticality levels, and explain how you'd avoid either over-spending on low-criticality services or under-protecting high-criticality ones."_
**Model answer:** I'd start by working with each service's business owner to establish an actual RPO/RTO requirement grounded in real business-impact analysis, rather than assuming a uniform DR posture across all 50 services — this alone typically reveals a natural tiering, since not every service genuinely needs the same level of protection. I'd then map each service to the most cost-appropriate of the four standard strategies given its actual RPO/RTO requirement — likely the majority of lower-criticality internal services land on Backup & Restore or Pilot Light, a smaller set of genuinely important customer-facing services land on Warm Standby, and only the handful of truly mission-critical, revenue-direct services (payments, core authentication) justify Multi-Site Active/Active's substantial ongoing cost. Critically, I'd also insist on **actually testing** each service's DR plan periodically — a documented Pilot Light strategy that's never been exercised in practice is a strategy on paper, not a proven capability, and DR testing (a full or partial failover drill) is itself a genuine, deliberate exercise worth budgeting time and effort for, not a one-time setup step. I'd track this portfolio explicitly — which service is on which strategy, with what actual tested RTO, reviewed periodically as business criticality naturally shifts over time (a service that started as internal-only might become customer-facing and need its DR tier upgraded, for example).

## 8. Common Misconceptions

- "Multi-AZ within a single region is the same thing as a disaster recovery strategy." False — Multi-AZ protects against an Availability Zone failure, which is valuable and often sufficient, but a genuine DR strategy specifically addresses broader failure modes (a full regional outage, catastrophic data corruption, a destructive operational error affecting the primary region entirely) that Multi-AZ alone doesn't cover.
- "You should always pick the DR strategy with the fastest RTO." False — the fastest-RTO strategy (Multi-Site Active/Active) is also the most expensive; the right strategy is the one matching the actual, business-determined RPO/RTO requirement at the lowest cost that achieves it, not unconditionally the most protective option available.

## 9. Key Takeaways

🔑 RPO (acceptable data loss) and RTO (acceptable downtime) are business-determined numbers that should drive DR architecture selection, not the other way around.
🔑 The four AWS DR strategies — Backup & Restore, Pilot Light, Warm Standby, Multi-Site Active/Active — represent increasing RPO/RTO improvement at increasing ongoing cost, a direct Reliability-vs-Cost Well-Architected trade-off (§89).
🔑 Pilot Light keeps only the data tier warm; Warm Standby keeps the full stack running at reduced scale — the key RTO improvement comes from not needing to provision compute from scratch during the actual disaster.
🔑 A DR strategy that's never been tested is unproven — periodic failover drills are a genuine, necessary part of any real DR practice, not an optional afterthought.
🔑 Different services within one organization legitimately warrant different DR strategies based on their actual criticality — a uniform, one-size-fits-all DR posture either overspends on low-stakes services or underprotects high-stakes ones.

## 10. Related Concepts

- **Well-Architected Framework** (the Reliability-vs-Cost trade-off this entire capstone directly applies) → §89.
- **AWS Backup and backup strategies** (the mechanism underlying Backup & Restore and the data-tier replication in Pilot Light) → Part 5.
- **Route 53 DNS failover** (the traffic-redirection mechanism commonly implementing failover across all four strategies) → Part 4.
- **CloudFormation/CDK/Terraform** (the IaC foundation Pilot Light and Warm Standby depend on for rapid, reliable secondary-environment provisioning) → §79-82.
- **Migration Strategies** (the next section — a different kind of organization-wide, workload-by-workload AWS strategy framework) → next section, §93.
