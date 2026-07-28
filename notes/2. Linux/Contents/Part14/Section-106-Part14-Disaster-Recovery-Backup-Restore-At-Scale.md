# Section 106 (Part 14): Disaster Recovery and Backup/Restore at Scale

## 1. HA vs. DR: A Distinction Commonly Conflated

**High availability (§105)** and **disaster recovery (DR)** are frequently used interchangeably in casual conversation, and that conflation is worth correcting explicitly before going further, because the two disciplines have genuinely different scope, mechanisms, and success criteria.

**HA** (§105) handles a **component failure** — a node, a disk, a process — while the overall system keeps running throughout, ideally with no user-visible interruption at all. Its mechanisms (Pacemaker/Corosync failover, load-balanced fleets removing unhealthy nodes) operate in seconds, are largely automatic, and assume the rest of the infrastructure — the datacenter, the region, the network backbone — remains intact.

**Disaster recovery** handles a much larger-scale failure: an entire **site, region, or datacenter** becoming unavailable — a natural disaster, a regional cloud provider outage, a catastrophic data-center failure, or a large-scale security incident that takes down the primary environment entirely. DR is fundamentally about **recovery after an outage has already happened**, not about preventing the outage from being user-visible in the first place. Where HA's success looks like "the user never noticed," DR's success looks like "we got back up within an acceptable window, with an acceptable amount of data loss" — the outage itself is treated as a given, not something DR mechanisms directly prevent.

> 💡 **Tip:** A useful one-line test for which discipline you're actually discussing: if the failure scenario is "one thing broke while everything else kept working," you're talking about HA. If the scenario is "the entire environment/region is gone and we need to stand up somewhere else," you're talking about DR. Many real incident postmortems blur this line by describing a DR-scale event in HA terms, which leads to under-provisioned recovery plans.

## 2. RTO and RPO: The Two Defining DR Metrics

Every DR architecture decision should be driven by two precisely defined metrics, not decided ad hoc after the fact:

### 2.1 RTO — Recovery Time Objective

**RTO** is **how long the system can be down before that downtime becomes unacceptable to the business.** An RTO of 4 hours means: after a disaster is declared, the organization has committed to having the system back up and serving traffic within 4 hours. RTO answers the question "how fast do we need to recover?"

### 2.2 RPO — Recovery Point Objective

**RPO** is **how much data loss, measured in time, is acceptable.** An RPO of 1 hour means the organization accepts losing up to the last hour of data — whatever was written between the last successful backup/replication point and the moment of the disaster is gone, and that is considered an acceptable trade-off, not a failure of the DR plan. RPO answers the question "how much data can we afford to lose?"

These two numbers are not interchangeable and do not move together automatically — a system can have a very short RTO (back up in minutes) with a longer RPO (an hour of data loss is fine), or vice versa, depending entirely on what the business actually needs. Critically, **RTO and RPO should be defined up front and drive every subsequent architecture decision** — which DR strategy tier (3) is affordable and appropriate, how frequently backups run, whether synchronous or asynchronous replication is needed — rather than being treated as an afterthought discovered only when an actual disaster reveals what the existing setup can and can't deliver.

## 3. The DR Strategy Spectrum

DR strategies exist on a spectrum from cheapest-and-slowest to most-expensive-and-fastest. There is no universally "correct" tier — the right choice is whichever tier's RTO/RPO characteristics actually match the business's stated tolerance from 2, at a cost the business is willing to pay for that tolerance.

| Tier                     | Description                                                                                                                             | Typical RTO              | Typical RPO               | Relative cost |
| ------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- | ------------------------ | ------------------------- | ------------- |
| Backup and restore       | Restore from backups onto newly provisioned infrastructure after a disaster is declared                                                 | Hours to days            | Hours (since last backup) | Lowest        |
| Pilot light              | A minimal, always-on skeleton of critical infrastructure (e.g., a database kept in sync) in a second region, scaled up only when needed | Tens of minutes to hours | Minutes to an hour        | Low-moderate  |
| Warm standby             | A scaled-down but fully functional duplicate environment running continuously in a second region                                        | Minutes                  | Seconds to minutes        | Moderate-high |
| Multi-site active-active | Full production capacity running simultaneously in multiple locations, serving live traffic in normal operation                         | Near-zero to seconds     | Near-zero                 | Highest       |

- **Backup and restore** is the cheapest and slowest tier: backups (tapes, snapshots, object storage) exist, but recovering means provisioning new infrastructure from scratch and restoring data onto it after the disaster is already underway — acceptable only when the business can genuinely tolerate hours-to-days of downtime.
- **Pilot light** keeps the smallest possible footprint of genuinely critical infrastructure running continuously in a second region — commonly just a replicated database — with the rest of the stack (application servers, load balancers) provisioned and scaled up only when a disaster is declared, trading some recovery speed for substantially lower steady-state cost than a full duplicate environment.
- **Warm standby** runs a complete, functional, but deliberately scaled-down duplicate of the production environment continuously — every component exists and works, just at lower capacity — so recovery is largely a matter of scaling up the standby environment rather than building it from nothing.
- **Multi-site active-active** runs full production capacity simultaneously across multiple locations at all times, with live traffic already being served from more than one site — this is the same active-active concept §105 introduced for individual node fleets, extended to the scale of entire sites/regions, and it delivers the fastest possible RTO/RPO because there is effectively no "recovery" step at all, only redirecting traffic away from the affected site.

## 4. Testing the DR Plan: The Discipline That Actually Matters

Choosing a DR tier and configuring backups is necessary but not sufficient — the operational discipline that separates a DR plan that works from one that only looks like it works on paper is **actually testing it**.

⚠️ **Warning:** A backup that has never been test-restored is not a verified backup — it is an unverified assumption sitting on a disk or in object storage. This is one of the most common and most costly real-world DR failures: an organization discovers, only during an actual disaster, that its backups were corrupted, incomplete, silently failing for weeks before anyone noticed, or simply restorable into a configuration that doesn't actually work — at precisely the moment when there is no time left to fix it and no fallback remaining. The failure mode isn't rare or exotic; it is one of the single most repeated root causes in real DR postmortems.

A genuine DR testing discipline means periodically executing an actual restore — not just confirming a backup job "completed successfully" in a log, which only proves the backup process ran, not that the resulting data is usable — into an environment that resembles production closely enough to validate the RTO/RPO the plan claims to deliver. For warm-standby and multi-site tiers, testing also means periodically exercising an actual failover (a "game day" or DR drill), since a standby environment that has never taken live traffic can hide configuration drift, missing dependencies, or capacity gaps that only surface under real load.

## 5. Geographic and Regional Considerations in Cloud Environments

§104 (Part 14, prior) covered cloud images and cloud-init for provisioning individual instances. DR planning extends that concern to **geography**: genuine disaster-level resilience requires replicating golden images, backups, and (for the higher DR tiers) live infrastructure across **regions**, not merely across **availability zones** within a single region.

Availability zones within one region are already isolated from many individual-datacenter-level failures — power, individual building issues, isolated hardware failures — and that isolation is exactly what makes AZ-level replication a reasonable basis for the HA patterns in §105. But a genuinely disaster-scale event — a large-scale regional outage, a natural disaster affecting an entire geographic area, or a cloud provider's region-wide incident — can affect every availability zone within a region simultaneously, since they typically share the same underlying regional control plane and often nearby physical geography. A DR plan that only replicates across AZs within one region has addressed HA-scale risk (§105), not DR-scale risk as defined in 1 — genuine DR requires the golden images, backup repositories, and (for warm-standby or active-active tiers) actual running infrastructure to exist in a **separate region entirely**, ideally one with independent underlying infrastructure and geographic distance from the primary.

## 6. Choosing a Tier: Tying It Back to RTO/RPO

The practical workflow is to define RTO/RPO (2) for each system honestly and separately — not every system in an environment needs the same tier — and then select the cheapest tier from 3 that actually meets those numbers. A batch-reporting system that can tolerate a day of downtime and an hour of data loss has no business paying for multi-site active-active; a payments-processing system with a five-minute RTO and near-zero RPO has no honest way to meet that target on backup-and-restore alone. Treating DR tier selection as a cost-vs-risk trade-off explicitly, rather than defaulting to either extreme, is the core of doing this well.

## 7. Common Misconceptions

1. **"HA and DR are the same thing, just different names."** They address different failure scales with different mechanisms — HA keeps a system running through a component failure (§105); DR recovers after a much larger site/region-scale outage has already happened (1). A system can be highly available and still have no real disaster recovery plan, and vice versa.
2. **"A completed backup job means the backup is good."** A backup job reporting success only confirms the process ran — it says nothing about whether the resulting data is actually restorable into a working system. Only a genuine test restore verifies that (4's Warning).
3. **"Lower RTO/RPO is always better, so aim for the fastest tier available."** Every tier in 3 has a real cost, and multi-site active-active is dramatically more expensive than backup-and-restore. The correct target is whatever RTO/RPO the business has actually decided is necessary for that specific system (2, 6) — not the fastest tier achievable regardless of cost.
4. **"Replicating across availability zones is sufficient for disaster recovery."** AZ replication addresses component/datacenter-level HA risk (§105) but not region-scale disaster risk, since a genuinely disaster-level event can affect an entire region's AZs simultaneously — true DR requires cross-region replication (5).

## 8. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between RTO and RPO?"_
**Model answer:** RTO (Recovery Time Objective) is how long the system can be down before that downtime is unacceptable — it's a measure of acceptable outage duration. RPO (Recovery Point Objective) is how much data loss, measured in time, is acceptable — an RPO of one hour means losing up to the last hour of data is tolerable. RTO is about recovery speed; RPO is about acceptable data loss. Both need to be defined explicitly, and they don't automatically move together.
_What the interviewer is probing for:_ Precise, non-confused definitions of both terms — mixing them up is a common and telling mistake.

**🎯 Intermediate:** _"Explain the DR strategy spectrum from backup-and-restore to multi-site active-active, and what drives the choice between them."_
**Model answer:** The spectrum runs from backup-and-restore (cheapest, slowest — restore from backups onto new infrastructure after the disaster hits, hours-to-days RTO), to pilot light (a minimal always-on skeleton, commonly just a replicated database, scaled up on demand), to warm standby (a full but scaled-down duplicate environment running continuously), to multi-site active-active (full production capacity live in multiple locations simultaneously, near-zero RTO/RPO but highest cost). The choice should be driven by the specific system's defined RTO and RPO — pick the cheapest tier that actually meets those numbers, rather than defaulting to either extreme.
_What the interviewer is probing for:_ Correct ordering and characterization of all four tiers, plus tying tier selection back to RTO/RPO rather than treating it as an arbitrary preference.

**🎯 Senior:** _"Your organization has a documented DR plan with backups running nightly, but it's never been tested with an actual restore. How do you evaluate the real risk here, and what do you do about it?"_
**Model answer:** I'd treat this as an unverified DR plan, not a working one, regardless of how long the backup jobs have been "succeeding" — a completed backup job only confirms the process ran, not that the resulting data is restorable into a functioning system. The real risk is discovering corruption, incompleteness, or a broken restore procedure during an actual disaster, when there's no time left to react — which is one of the most common root causes in real DR postmortems. I'd schedule a genuine test restore into an isolated environment that resembles production, verify the restored system actually comes up and functions (not just that files land on disk), and measure how long that took against the stated RTO — if it's slower than the target, that's the real finding, not an assumption I'd want the org discovering during a live incident. I'd push to make this a recurring exercise, not a one-time check, since backup/restore tooling, data volume, and infrastructure all drift over time.
_What the interviewer is probing for:_ Recognizing that an untested backup is functionally unverified, and proposing a concrete, recurring testing discipline rather than a one-off check.

**🎯 Architect:** _"You're designing DR for a multi-region cloud deployment. Walk me through how you'd decide what tier different systems need, and how region-level replication factors in."_
**Model answer:** I'd start by getting honest, system-by-system RTO/RPO numbers from the actual business owners rather than assuming uniform requirements across the whole environment — a batch analytics pipeline and a customer-facing payments system have very different tolerances, and treating them identically means either wildly overspending on the former or dangerously underprovisioning the latter. For each system, I'd select the cheapest tier from the spectrum that genuinely meets its numbers: backup-and-restore for tolerant internal tools, pilot light or warm standby for systems that need faster recovery but can tolerate some data loss, multi-site active-active reserved for the systems where the business has explicitly justified that cost against the cost of an outage. Separately from tier selection, I'd insist that whatever tier is chosen actually replicates across regions, not just availability zones within one region — AZ-level redundancy addresses HA-scale risk (§105) but a genuinely disaster-scale event can take out an entire region's AZs together, so golden images, backup repositories, and any standby infrastructure need to exist in a distinct region with independent underlying infrastructure. Finally, I'd build recurring DR drills into the operational calendar for every tier above backup-and-restore, since an untested standby environment is exactly as unverified as an untested backup.
_What the interviewer is probing for:_ System-by-system tier differentiation driven by real RTO/RPO rather than a one-size-fits-all plan, correct distinction between AZ-level and region-level replication, and building in recurring verification rather than treating the plan as done once configured.

## 9. Key Takeaways

- HA (§105) keeps a system running through a component failure; DR recovers after a much larger site/region-scale outage has already occurred — related but distinct disciplines, not interchangeable terms (1).
- RTO (acceptable downtime duration) and RPO (acceptable data loss, in time) are the two metrics that should drive every DR architecture decision, defined up front rather than discovered during an incident (2).
- The DR strategy spectrum runs backup-and-restore → pilot light → warm standby → multi-site active-active, trading increasing cost for decreasing RTO/RPO — choose the cheapest tier that actually meets a system's defined targets (3, 6).
- An untested backup is an unverified assumption, not a proven recovery path — a completed backup job only proves the process ran, not that the data is restorable; genuine DR discipline requires actual periodic test restores and, for higher tiers, real failover drills (4).
- Cloud DR requires replicating golden images and backups across regions, not just availability zones within one region, since a genuinely disaster-scale event can affect an entire region's AZs simultaneously (5).

## 10. Related Concepts & What's Next

This section is the fleet/organizational-scale continuation of §79's single-host backup tooling (tar, rsync, dd — Part 10): the mechanics of taking a backup are the same underlying idea, but DR planning adds RTO/RPO-driven strategy selection, cross-region geography, and testing discipline that single-host backup commands alone don't address. It's also deliberately contrasted against §105's HA architectures (Part 14, prior) — HA and DR solve related but distinct scale-of-failure problems and should be planned as separate, complementary line items rather than one substituting for the other. §107, next, covers capacity planning — the forward-looking discipline that determines, among other things, how much standby/duplicate capacity a chosen DR tier actually requires to provision.

**Next Section:** §107 — `Section-107-Part14-Capacity-Planning-For-Linux-Fleets.md`
