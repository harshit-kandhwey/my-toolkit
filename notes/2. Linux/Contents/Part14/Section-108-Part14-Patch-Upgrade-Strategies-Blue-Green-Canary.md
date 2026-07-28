# Section 108 (Part 14): Patch and Upgrade Strategies (Blue/Green, Canary, In-Place vs. Reimage)

## 1. The Fundamental Decision: In-Place vs. Reimage

Every patch or upgrade to a running fleet ultimately reduces to one of two mechanical approaches, and every strategy in this section is built on top of that choice.

**In-place patching** modifies a running system directly — `apt upgrade`, `dnf update`, or a targeted package install applied to a host that continues existing as the same host before and after. §94's vulnerability and patch management coverage was about the _why_ and _when_ of applying a given patch; this section is about the _how_ at fleet scale, and in-place patching is the direct mechanical continuation of §94's patch mechanisms applied to a live system.

**Reimage-based patching** takes the opposite approach: rather than modifying a running host, a new **golden image** (§102) is built with the patch already baked in, and existing instances are replaced entirely with fresh instances launched from that new image. This is the immutable-infrastructure philosophy from §102 applied specifically to the patching problem — instead of asking "how do I safely mutate this running system," the question becomes "how do I safely replace it with a known-good, already-patched one."

The trade-offs are genuinely different in kind, not just degree:

| Dimension                             | In-Place                                                                                     | Reimage                                                            |
| ------------------------------------- | -------------------------------------------------------------------------------------------- | ------------------------------------------------------------------ |
| Speed for a single host               | Fast — apply the patch, restart the service                                                  | Slower — build/validate image, launch replacement, cut over        |
| Configuration drift risk              | Higher — repeated in-place changes accumulate untracked state over time                      | Lower — every instance traces back to a known, versioned image     |
| Rollback                              | Often awkward — uninstalling a patch cleanly isn't always well-supported                     | Clean — relaunch from the prior image version                      |
| Fleet-scale consistency               | Depends entirely on automation discipline; drift between hosts is easy to introduce silently | Structurally consistent — every replaced instance starts identical |
| Infrastructure cost during the change | None extra — same hosts, modified in place                                                   | Temporary duplication — old and new instances coexist briefly      |

Neither is universally correct. A single long-lived database host with complex local state is a poor reimage candidate; a stateless web-tier node behind a load balancer (§105) is often a better reimage candidate than an in-place one, precisely because replacing it is cheap and its state lives elsewhere.

> 💡 **Tip:** "In-place vs. reimage" is a decision about _mechanism_ — it doesn't by itself tell you _how_ to roll the change out across the fleet without an outage. Blue/green, canary, and rolling upgrades (2–4) are rollout patterns that sit on top of this decision, and reimage-based patching in particular is what makes blue/green practical at scale, since standing up a whole parallel "green" environment is far more tractable when it's built from a golden image than when it requires re-running a long, imperative in-place patch script on every new host.

## 2. Blue/Green Deployment in Depth

**Blue/green deployment** maintains two complete, parallel environments — conventionally labeled **blue** (currently live, serving production traffic) and **green** (currently idle). To roll out a patch or upgrade:

1. Deploy and fully validate the change on the idle environment (green) — with zero customer traffic hitting it yet, so nothing is at risk during this phase.
2. Once green is verified healthy, **switch traffic over atomically** — typically by repointing a load balancer or DNS record from blue to green.
3. Keep the old environment (blue) running, idle but intact, for a defined window after the cutover.

**The real value proposition here is not the deployment mechanism — it's the instant-rollback property.** Because blue is kept running rather than torn down immediately, if something goes wrong post-cutover, rolling back means flipping the traffic switch back to blue — an operation that takes seconds, not a re-deploy, a re-patch, or a restore-from-backup. This is fundamentally different from "deploy the fix and hope it works": blue/green explicitly buys back the ability to undo the change near-instantly, at the cost of running double the infrastructure for the overlap window. That cost-for-safety trade is the entire point of the pattern, not an unfortunate side effect of it.

Blue/green works cleanly for stateless services; it gets substantially harder when the environments share a stateful backing store (a database schema change made for green may not be backward-compatible with blue still running against it), which is a real limitation worth naming rather than glossing over.

## 3. Canary Deployment in Depth

**Canary deployment** rolls a change out to a small subset of the fleet first — the "canary" (named for the historical coal-mine practice of an early-warning indicator) — and monitors it closely for errors, latency regressions, or other signals before proceeding further. If the canary looks healthy after an observation window, the change progressively expands to larger slices of the fleet (e.g., 5% → 25% → 100%) rather than jumping straight to full rollout.

**The genuinely important distinction from blue/green is the risk model each one is solving, not just the mechanics:**

- **Blue/green** is about an **instant, atomic cutover** with an **instant rollback path** — the whole fleet moves to the new version at once (from the traffic-routing perspective), and the safety net is "flip back instantly if needed."
- **Canary** is about **gradual, monitored exposure** to reduce **blast radius** — only a small fraction of real traffic ever touches the new version until it's been proven safe, so if something is wrong, the damage is deliberately contained to that small slice rather than affecting the whole fleet at once.

These solve related but distinct problems: blue/green minimizes _how long it takes to undo_ a bad change once discovered; canary minimizes _how much of the fleet is affected_ before it's discovered. A change can go wrong in ways canary catches that blue/green's instant switch never would have caught in time (a bug that only manifests under a specific slice of real production traffic patterns, for instance) — and the two patterns are genuinely **combinable**: a canary phase to validate against a small slice of real traffic, followed by a blue/green-style atomic cutover for the remainder, gets both gradual validation and an instant rollback path for the bulk of the fleet.

⚠️ **Warning:** A canary phase is only as good as what's actually being monitored during it. A canary rolled out for five minutes with no meaningful error-rate, latency, or business-metric monitoring attached provides false confidence, not real risk reduction — the entire value of the pattern depends on genuinely observing the canary (§80–§88's monitoring toolset) before deciding to proceed, not just waiting a fixed amount of time and assuming silence means success.

## 4. Rolling Upgrades: The Pragmatic Middle Ground

**Rolling upgrades** update fleet nodes a few at a time, in sequence, rather than maintaining a second full environment (blue/green) or carefully monitoring a small subset before proceeding (canary). The typical mechanic, directly dependent on §105's load-balanced fleet architecture: remove a node from the load balancer's rotation, patch or upgrade it in place, run a health check, return it to rotation, then repeat for the next node — continuing until the whole fleet is updated.

Rolling upgrades are simpler to implement than blue/green (no second environment to provision and tear down) and don't require canary's careful staged-percentage traffic shaping — but the trade-offs are real:

- **Longer exposure window.** The fleet spends an extended period running a mix of old and new versions simultaneously, which needs to be a safe state for the application (backward/forward compatibility between versions matters more here than in an atomic blue/green cutover).
- **No single "flip a switch" rollback.** If a problem is discovered partway through, rolling back means rolling the change back out node by node, the same way it went in — there's no equivalent to blue/green's instant traffic-switch reversal.

This makes rolling upgrades the right default for **routine, low-risk patching** where the extra infrastructure cost of blue/green or the operational overhead of a carefully staged canary isn't justified by the risk level of the change.

## 5. Decision Framework

Putting 1–4 together into a practical choice:

- **Choose blue/green** when instant rollback matters most — high-stakes changes where minimizing time-to-undo is the priority — and the organization can absorb the temporary cost of running double infrastructure during the cutover window.
- **Choose canary** when gradual, monitored real-world validation matters most — changes where the failure mode is hard to predict in advance and catching it against a small slice of genuine production traffic before full exposure is worth the added rollout time and monitoring discipline.
- **Choose rolling upgrades** as the pragmatic default for routine, well-understood patching (regular OS security patches, routine minor-version bumps) where extreme rollback speed isn't critical and the operational simplicity of "a few nodes at a time" is the better trade.
- **Combine canary + blue/green** for the highest-stakes changes, where both gradual validation against real traffic and an instant full-fleet rollback path are warranted.

None of these three patterns is a strict upgrade over the others — they solve different risk problems, and the right choice depends on the specific change's blast-radius risk, rollback-speed requirement, and how much extra infrastructure cost is tolerable during the rollout window.

## 6. Common Misconceptions

1. **"Blue/green and canary are the same idea with different names."** They solve different problems: blue/green is about instant, atomic cutover with instant rollback; canary is about gradual, monitored exposure to limit blast radius. They can be combined, but conflating them obscures why each exists (3).
2. **"Reimage-based patching is always safer than in-place."** It's more consistent and structurally cleaner for stateless workloads, but it isn't free — it costs temporary double infrastructure and doesn't fit long-lived, complex stateful hosts well (1).
3. **"Rolling upgrades are just a cheaper version of blue/green."** They're a different pattern with a different exposure profile — a mixed-version fleet running for an extended period, and no single instant-rollback switch — not simply blue/green without the second environment (4).
4. **"A canary phase with no real monitoring attached still counts as a canary deployment."** Without genuine observation of the canary's health signals, the pattern provides no actual risk reduction — it's just a delayed full rollout (3's Warning).

## 7. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between in-place patching and reimaging?"_
**Model answer:** In-place patching modifies a running system directly — applying a package update to a host that continues to exist as the same host. Reimaging builds a new golden image with the patch already baked in and replaces the running instance entirely with a fresh one launched from that image. In-place is faster for a single host but risks configuration drift over repeated changes; reimaging is more consistent and cleanly rollback-able but costs temporary double infrastructure during the swap (1).
_What the interviewer is probing for:_ Whether the candidate understands this as a mechanism choice distinct from rollout-pattern choice (blue/green, canary, rolling), not the same decision.

**🎯 Intermediate:** _"Explain the actual difference between blue/green and canary deployment — not just the definitions, but why you'd choose one over the other."_
**Model answer:** Blue/green keeps two full parallel environments and switches all traffic atomically from the old to the new one, with the old environment kept briefly as an instant rollback path — its value is minimizing how long it takes to undo a bad change. Canary rolls a change out to a small slice of the fleet first and monitors it before expanding — its value is minimizing how much of the fleet is affected before a problem is caught. I'd choose blue/green when instant rollback speed is the priority and I can afford brief double infrastructure cost; I'd choose canary when I'm less certain how the change will behave under real traffic and want to limit exposure while validating it live.
_What the interviewer is probing for:_ Correctly separating "how fast can I undo this" from "how much of the fleet is exposed before I know," rather than treating the two patterns as interchangeable.

**🎯 Senior:** _"When would you choose rolling upgrades over blue/green for a load-balanced fleet, and what risk are you accepting by doing so?"_
**Model answer:** I'd default to rolling upgrades for routine, well-understood patches — regular OS security updates, minor version bumps with a known-good track record — where the operational simplicity of pulling a node from rotation, patching it, and returning it (§105's fleet architecture makes this mechanically easy) outweighs the benefit of a second full environment. The risk I'm accepting is a longer exposure window running a mix of old and new versions simultaneously, which requires the application to tolerate version skew across the fleet during the rollout, and the absence of a single instant-rollback switch — if something's wrong partway through, I have to roll the change back out node by node rather than flipping a traffic switch. I'd reserve blue/green for changes where that rollback speed is worth the extra infrastructure cost, and I'd add a canary phase in front of either pattern if I were less confident about how the change behaves under real traffic.
_What the interviewer is probing for:_ Real cost-benefit reasoning about when the simpler pattern is the right engineering choice, not just knowledge that "blue/green is safer" as an unconditional statement.

**🎯 Architect:** _"Design a patch rollout strategy for a fleet that includes both a stateless web tier and a stateful database tier. How do the strategies from this section apply differently to each?"_
**Model answer:** For the stateless web tier, I'd lean toward reimage-based patching (§102's golden images) combined with either blue/green or rolling upgrades depending on the risk profile of the specific change — the tier is naturally load-balanced (§105) and disposable, so replacing instances wholesale is cheap and clean, and a canary phase in front of either pattern gives real-traffic validation before wider rollout. For the database tier, reimage-and-replace is far riskier because of the state involved — I'd favor in-place patching with careful pre-validation, and I'd treat any blue/green-style approach here as needing an explicit data-migration/replication strategy rather than a simple traffic switch, since blue and green can't share a live, mutating dataset the way two stateless web fleets can share nothing. I'd also flag that a schema change coupling the two tiers (an application change deployed via blue/green against a database patched in-place) needs explicit backward/forward-compatibility validation between the tiers during any window where old and new versions coexist — which is the same version-skew concern rolling upgrades raise, just introduced here by the tiers being patched on different schedules rather than by a single tier's rollout being incremental.
_What the interviewer is probing for:_ Recognizing that these strategies aren't one-size-fits-all across a heterogeneous fleet, and specifically that statefulness is the dividing line between where reimage/blue-green cleanly applies and where it needs real adaptation.

## 8. Key Takeaways

- In-place vs. reimage is a mechanism decision (modify a running host vs. replace it from a golden image, §102) that sits underneath, not instead of, the rollout-pattern decision (2–4).
- Blue/green's real value is instant rollback via keeping the old environment briefly alive after an atomic traffic-switch cutover — not the deployment mechanism itself (2).
- Canary is about gradual, monitored exposure to reduce blast radius, which is a genuinely different risk problem from blue/green's instant-cutover-with-instant-rollback — the two are combinable, not interchangeable (3).
- Rolling upgrades, dependent on §105's load-balanced fleet architecture, are the pragmatic default for routine patching — simpler than blue/green but with a longer exposure window and no single-switch rollback (4).
- Choose based on which risk matters most for the specific change: rollback speed (blue/green), blast-radius reduction via real-world validation (canary), or routine operational simplicity (rolling) (5).

## 9. Related Concepts & What's Next

This section is the direct fleet-scale application of §94's patch management (the _why/when_, this section's _how_) and §102's golden images/immutable infrastructure (the reimage half of 1's core decision), and several of its rollout patterns depend structurally on §105's HA/load-balanced fleet architecture already existing. §109, next, moves to cost optimization for Linux infrastructure — including how the double-infrastructure cost of blue/green and the routine-vs-emergency trade-offs covered here connect to fleet-wide cost decisions.

**Next Section:** §109 — `Section-109-Part14-Cost-Optimization-For-Linux-Infrastructure.md`
