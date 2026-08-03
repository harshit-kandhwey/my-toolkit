# Section 105 (Part 14): High Availability Architectures (Pacemaker/Corosync Overview, Load-Balanced Fleets)

## 1. What "High Availability" Actually Means

**High availability (HA)** has a precise operational meaning, not just a vague "the system doesn't go down" aspiration: it is the property of a system continuing to serve traffic despite the failure of some individual component — a node, a disk, a network link — without that failure becoming a user-visible outage. HA is a design goal achieved through redundancy and failure detection, and it is conventionally measured in **uptime percentage**, expressed as a number of "nines."

The nines convention is worth internalizing precisely, because the jump between adjacent tiers is far larger in practice than the percentages suggest:

| Availability | Nickname      | Annual downtime | Monthly downtime |
| ------------ | ------------- | --------------- | ---------------- |
| 99%          | "two nines"   | ~3.65 days      | ~7.3 hours       |
| 99.9%        | "three nines" | ~8.76 hours     | ~43.8 minutes    |
| 99.99%       | "four nines"  | ~52.6 minutes   | ~4.4 minutes     |
| 99.999%      | "five nines"  | ~5.26 minutes   | ~26 seconds      |

Going from three nines to four nines doesn't mean "a bit less downtime" — it means shrinking acceptable annual downtime from most of a working day to under an hour, and going to five nines means single-digit minutes for an entire year. Each additional nine typically costs disproportionately more in architectural complexity, redundant infrastructure, and operational discipline than the one before it — which is exactly why choosing a target should be a deliberate business decision tied to what an outage actually costs, not an automatic reach for "as many nines as possible."

> 💡 **Tip:** When someone states an SLA target, translate it into actual minutes of annual downtime before agreeing to it. "99.95%" sounds close to "99.99%," but the former allows roughly 4.4 hours of annual downtime against the latter's 52 minutes — a nearly 5x difference that materially changes what architecture is required to meet it.

## 2. Two Broad HA Architecture Patterns

Almost every HA design on Linux falls into one of two broad patterns. They solve the same underlying problem — surviving a component failure — with fundamentally different mechanisms, trade-offs, and failure modes.

## 3. Pattern One: Active-Passive Clustering

In **active-passive clustering**, one node (the active node) actively serves traffic while one or more standby nodes sit idle, ready to take over if the active node fails. Only one node is "live" at any given moment; the standby's entire job is readiness, not throughput. This is the classic on-prem/traditional Linux HA pattern, and the reference stack for implementing it is **Pacemaker** paired with **Corosync**.

### 3.1 Corosync: Cluster Membership and Communication

**Corosync** is the underlying communication and membership layer the cluster depends on. Its job, stated as plainly as possible, is answering one question continuously: **"who's alive, and can talk to whom?"** It maintains a heartbeat between cluster nodes over the network, detects when a node stops responding, and provides the messaging substrate that higher-level cluster software (Pacemaker) builds on. Corosync itself has no concept of "services" or "what should be running" — it only knows cluster membership and connectivity.

### 3.2 Pacemaker: The Cluster Resource Manager

**Pacemaker** is the **cluster resource manager** sitting on top of Corosync. Given Corosync's answer to "who's alive," Pacemaker answers the second question: **"given that, what should be running where?"** Pacemaker tracks **resources** (a resource being anything the cluster manages — a database service, a filesystem mount, a virtual IP) and their placement rules, monitors resource health independently of node health (a node can be "alive" per Corosync while the actual service on it has crashed), and triggers failover — stopping a resource on a failed node and starting it on a healthy one — according to configured policy.

The division of labor is worth stating as cleanly as possible, since conflating the two is a common source of confusion: **Corosync = membership and communication; Pacemaker = resource placement and failure response.** Pacemaker cannot function without Corosync's membership view, and Corosync alone has no orchestration logic at all.

### 3.3 The Virtual IP (VIP)

A **VIP (Virtual IP)** is a single IP address that clients connect to, which Pacemaker moves — fails over — between physical nodes as part of a failover event. Clients never need to know which physical node is currently active; they always target the VIP, and Pacemaker's job during failover includes reassigning that address to whichever node is now serving traffic (typically via gratuitous ARP on the same subnet). The VIP is what makes failover transparent to the outside world rather than requiring every client to be reconfigured mid-incident.

### 3.4 Split-Brain and Fencing (STONITH)

**Split-brain** is the single most important failure mode to understand in active-passive clustering, and it is a frequent interview topic precisely because it is subtle and genuinely dangerous. It occurs when a network partition prevents nodes from communicating with each other, and **each node concludes the other is dead** — both believe they are now the sole active node. If both nodes then act on that belief (both claim the VIP, both mount the same shared storage, both write to the same database files), the result is data corruption, not just a service disruption: two independent processes writing to shared state that assumes single-writer semantics.

The real mechanism that prevents this is **fencing**, most commonly implemented as **STONITH — "Shoot The Other Node In The Head."** Rather than trusting a suspected-dead node to gracefully stop on its own (which it can't do if it's the one that's partitioned and doesn't know it), the surviving node forcibly powers off, reboots, or fences the other node at the hardware or infrastructure level — via an IPMI/BMC out-of-band management interface, a cloud provider API call, or a network switch port disable — before proceeding with failover. STONITH guarantees the old active node is genuinely, verifiably dead before the standby takes over the VIP and shared resources, closing the window where both nodes could otherwise act simultaneously.

⚠️ **Warning:** A Pacemaker cluster configured without working fencing is not a safe HA cluster — it is a cluster that will eventually suffer a split-brain data-corruption incident during a real network partition. Fencing is not an optional hardening step layered on top of a working cluster; it is the mechanism that makes failover safe at all. Any Pacemaker deployment review should verify STONITH is configured and actually tested, not merely present in configuration.

## 4. Pattern Two: Load-Balanced Active-Active Fleets

The second pattern is **load-balanced active-active fleets**: multiple genuinely identical nodes all actively serving traffic simultaneously, sitting behind a load balancer that distributes requests across them. There is no "standby" concept at all — every node is doing real work all the time.

When a node in this pattern becomes unhealthy, nothing resembling Pacemaker-style failover happens. The load balancer's health checks simply detect the failing node and **remove it from rotation** — traffic stops being routed to it, and the remaining healthy nodes absorb the load. No VIP is reassigned between two specific nodes, no resource is "moved," and no fencing decision needs to be made, because no node ever assumed it was the sole authority over shared state in the first place.

### 4.1 Why This Pattern Dominates Modern Architectures

Load-balanced active-active fleets have become the dominant HA pattern in modern, cloud-native architectures, for reasons directly traceable to the split-brain problem described above:

- **Simpler failure model.** "Remove an unhealthy node from a load-balancer pool" is a far simpler, lower-risk operation than "coordinate which of two nodes should now own shared state," with fewer edge cases and no fencing infrastructure to build and test.
- **No split-brain risk.** Because nodes aren't coordinating exclusive ownership of shared state the same way an active-passive cluster's active node does, there is no scenario where two nodes each believe they're uniquely authoritative and act on it destructively.
- **Horizontal scalability as a side effect.** A fleet built to tolerate any single node's failure is, by construction, also a fleet that can be scaled by adding more nodes — the same load-balancer/health-check mechanism that provides HA also provides capacity growth (§107 covers this scaling relationship in depth).

## 5. When Each Pattern Actually Applies

Neither pattern is universally "better" — they solve different problems, and the honest guidance is to match the pattern to what the service actually is:

- **Active-passive clustering (Pacemaker/Corosync) still matters for genuinely stateful services** that cannot trivially run active-active — a relational database with a single writable primary is the canonical example. Running two database primaries simultaneously against the same underlying storage without a true multi-master design is exactly the split-brain scenario described above; clustering with fencing is how such services achieve HA safely.
- **Load-balanced active-active fleets are the default choice for stateless application tiers** — web/API servers, stateless workers, anything that doesn't hold authoritative state that must remain single-writer. For these, the simpler failure model and horizontal scalability of the load-balanced pattern described above make it the clearly preferable default in essentially all modern deployments.

A well-designed fleet commonly uses both patterns at once, layered by tier: a load-balanced active-active pool of stateless application servers in front of an active-passive (or genuinely multi-master, where the technology supports it) database cluster behind them — each tier using the HA pattern appropriate to whether it holds exclusive state.

## 6. Contrast With Single-Host Redundancy

It's worth explicitly distinguishing this section's scope from §75's RAID coverage (Part 10). RAID is a **single-host redundancy** concept — surviving the failure of an individual disk within one machine, transparent to everything above the storage layer. The patterns in this section are the **multi-host equivalent**: surviving the failure of an entire node, not just a component within it. A host with a perfectly redundant RAID array can still be a single point of failure at the fleet level if it's the only node serving a given role — RAID and HA clustering/load-balancing operate at different layers of the same broader redundancy goal and are not substitutes for each other.

## 7. Cloud-Native Context

§104's coverage of cloud images and cloud-init (Part 14, prior) is worth recalling here: cloud-native HA often looks structurally different from the on-prem Pacemaker/Corosync stack described above. Cloud load balancers (managed services, not self-hosted software) combined with auto-scaling groups built from a shared golden image frequently implement the load-balanced active-active pattern described above with far less manual cluster configuration than a traditional on-prem Pacemaker deployment requires — the underlying concepts (health checks, removing unhealthy nodes from rotation) are identical, but the implementation shifts from self-managed cluster software to managed cloud infrastructure.

## 8. Common Misconceptions

1. **"HA means the system never goes down."** HA reduces the probability and duration of a user-visible outage from a component failure; it does not make outages impossible. The nines convention described above exists precisely because "always up" isn't a real target — every HA design accepts some nonzero acceptable downtime.
2. **"Pacemaker and Corosync do the same job, just redundantly."** They are distinct, complementary layers, not redundant ones — Corosync answers "who's alive and reachable," Pacemaker answers "what should be running where" given that membership view. Removing either one breaks the stack; they are not interchangeable.
3. **"Fencing is an optional extra hardening step."** As the fencing warning above states, a cluster without working, tested fencing is not a safe cluster — it is one that will eventually experience split-brain during a real network partition, not a hardened version of an already-safe design.
4. **"Load-balanced fleets don't need any failure-handling logic."** They still require health checks, timeout tuning, and a load balancer correctly configured to remove and re-add nodes — the pattern is simpler than Pacemaker-style failover, not automatic or configuration-free.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between active-passive clustering and a load-balanced active-active fleet?"_
**Model answer:** Active-passive clustering has one node actively serving traffic while one or more standby nodes wait idle, ready to take over via failover if the active node fails — Pacemaker/Corosync is the classic Linux implementation. A load-balanced active-active fleet has multiple identical nodes all serving traffic simultaneously behind a load balancer; an unhealthy node is simply removed from rotation rather than anything "failing over." The first pattern suits stateful services with a single-writer requirement; the second suits stateless application tiers.
_What the interviewer is probing for:_ Basic recognition that these are two distinct patterns with different mechanisms, not two names for the same idea.

**🎯 Intermediate:** _"Explain the specific roles of Corosync and Pacemaker — why do you need both?"_
**Model answer:** Corosync is the cluster membership and communication layer — it maintains heartbeats between nodes and answers "who's alive and reachable." Pacemaker is the cluster resource manager built on top of it — given Corosync's membership view, Pacemaker decides what resources (services, VIPs, mounts) should be running where, monitors their health, and triggers failover according to policy. Corosync has no concept of services or placement; Pacemaker has no way to determine cluster membership on its own. Neither is a substitute for the other — they're stacked layers, not alternatives.
_What the interviewer is probing for:_ Precise separation of the two tools' responsibilities rather than treating "Pacemaker/Corosync" as one undifferentiated blob.

**🎯 Senior:** _"Walk me through exactly how split-brain happens and how STONITH prevents it."_
**Model answer:** In an active-passive cluster, a network partition can cause the active and standby nodes to lose contact with each other while both remain independently alive. Each node's failure-detection logic then concludes the other node is dead — from the partitioned active node's perspective, the standby is unreachable and therefore presumed down; from the standby's perspective, the active node is unreachable and therefore presumed down, triggering its own failover logic. Without fencing, both nodes can end up believing they're the sole active node, both claiming the VIP and both writing to shared storage — which causes real data corruption, not just a service blip. STONITH prevents this by having the surviving node forcibly power off or fence the other node at the hardware/infrastructure level — IPMI, a cloud API call, a switch port disable — before proceeding with failover, guaranteeing the old node is genuinely dead rather than just unreachable over one link, so it's structurally impossible for both to act as active simultaneously.
_What the interviewer is probing for:_ Understanding split-brain as a partition-induced dual-belief problem specifically, and STONITH as a hard guarantee (verified death) rather than a soft heuristic.

**🎯 Architect:** _"You're designing HA for a three-tier application: stateless API servers, a caching layer, and a primary-replica relational database. How do you assign HA patterns across the tiers, and why?"_
**Model answer:** The API tier is stateless and gets a load-balanced active-active fleet, as described above — identical nodes behind a load balancer, unhealthy ones removed from rotation, with horizontal scaling as a natural side benefit (tied into §107's capacity planning). The caching layer depends on what it's backing — if it's a pure cache where a cold miss just falls through to the database, active-active with client-side or proxy-based sharding is usually fine, since losing a cache node degrades performance rather than causing data loss or corruption. The database tier is the one case that genuinely needs active-passive-style clustering with real fencing, because it holds authoritative, single-writer state — I'd use Pacemaker/Corosync with STONITH (or a managed database service's equivalent built-in failover, in cloud contexts, which implements the same fencing guarantee under a different name) precisely because running two writable primaries against the same storage without true multi-master support is the split-brain scenario in its most damaging form. I'd also make sure the database's fencing is actually tested under simulated partition conditions, not just configured, since untested fencing is functionally no better than no fencing at all.
_What the interviewer is probing for:_ Correctly differentiating HA pattern choice by statefulness per tier rather than applying one pattern uniformly, and insisting on tested (not just configured) fencing for the stateful tier.

## 10. Key Takeaways

- High availability is precisely defined as surviving a component failure without a user-visible outage, and "nines" of availability translate to dramatically different actual annual downtime — three nines (~8.76 hours/year) versus five nines (~5.26 minutes/year) is not a small gap.
- Active-passive clustering (Pacemaker/Corosync) keeps one active node and one or more idle standbys, using a VIP so clients don't need to know the current active node.
- Corosync handles cluster membership/communication ("who's alive"); Pacemaker handles resource placement and failover decisions ("what runs where") — distinct, complementary layers, not redundant ones.
- Split-brain — both nodes believing they're active after a network partition — is a serious data-corruption risk; STONITH/fencing forcibly guarantees the old node is dead before failover proceeds, and is not optional hardening.
- Load-balanced active-active fleets remove unhealthy nodes from rotation rather than failing over, avoiding split-brain risk entirely since nodes don't coordinate exclusive ownership of shared state — this is why the pattern dominates modern stateless-tier architectures.
- Match the pattern to statefulness: active-passive clustering for genuinely stateful, single-writer services; load-balanced active-active fleets as the default for stateless tiers.

## 11. Related Concepts & What's Next

This section is the multi-host equivalent of §75's single-host RAID redundancy (Part 10) — both address surviving a failure, at different layers, and are not substitutes for each other. It also contrasts with §104's cloud images/cloud-init coverage (Part 14, prior): cloud-native HA frequently achieves the load-balanced active-active pattern through managed infrastructure rather than self-hosted Pacemaker/Corosync. §106, next, moves from surviving a component failure to recovering from a much larger-scale disaster — an entire site or region becoming unavailable — a related but distinct discipline worth keeping clearly separated from this section's HA scope.

**Next Section:** §106 — `Section-106-Part14-Disaster-Recovery-Backup-Restore-At-Scale.md`
