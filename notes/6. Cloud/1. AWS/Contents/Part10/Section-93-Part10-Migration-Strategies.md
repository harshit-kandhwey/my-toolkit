# Part 10, Section 5: Migration Strategies — The 7 Rs and Real-World Migration Patterns

## 1. Definition

**Plain language:** Not every system in this roadmap was born on AWS — most enterprise interviews eventually touch on migration: how do you move an existing, working, on-premises (or other-cloud) system onto AWS without breaking it. The "7 Rs" is AWS's own framework for categorizing the different strategies for migrating any given workload, ranging from "just move it as-is" to "throw it away and build something new."

**Precise definition:** AWS migration strategy is the practice of assessing existing (on-premises or other-cloud) workloads and selecting an appropriate migration approach per workload from the "7 Rs" framework — Retire, Retain, Rehost, Relocate, Repurchase, Replatform, and Refactor/Re-architect — balancing migration speed, cost, and the degree of modernization achieved, typically applied workload-by-workload across a large migration portfolio rather than uniformly across an entire estate.

## 2. Why It Exists / Problem It Solves

A large organization migrating to AWS typically has dozens, hundreds, or thousands of individual applications/workloads, each with different technical characteristics, business criticality, and modernization potential — treating "migrate to AWS" as one single strategy applied uniformly to everything is both impractical (some workloads genuinely can't be easily modernized in the migration's timeframe) and wasteful (some workloads would benefit enormously from real re-architecture, and simply lifting-and-shifting them as-is squanders that opportunity). The 7 Rs framework exists to make this workload-by-workload decision structured and comparable, rather than ad hoc.

## 3. Prerequisites and Dependencies

- **Well-Architected Framework** (Part 10 §1): migration decisions are themselves evaluated against the same six pillars — a migration that achieves speed at the cost of security or reliability is a poor migration.
- General familiarity with the AWS services covered across this roadmap, since migration strategy selection often depends on which AWS-native services a given workload could realistically adopt.

## 4. The 7 Rs, In Depth

1. **Retire** — the workload is no longer needed at all; decommission it rather than migrating it. A genuinely common outcome of a proper migration assessment — many organizations discover unused or redundant systems during migration planning that simply shouldn't be moved anywhere.
2. **Retain** — deliberately keep the workload where it currently is (on-premises or elsewhere), at least for now — appropriate for systems with a pending replacement already planned, systems with migration blockers (specific compliance/data-residency requirements, deep hardware dependencies) not yet resolved, or simply lower business priority relative to the migration effort's current focus.
3. **Rehost** ("lift and shift") — move the workload to AWS with minimal or no changes, typically moving VMs to EC2 essentially as-is. Fastest migration approach, lowest initial modernization benefit, often used as a first step to get out of a data center quickly (e.g., an expiring lease) with modernization deferred to later.
4. **Relocate** — a specific, narrower form of rehosting for virtualized workloads, moving entire VMware-based environments to AWS (via VMware Cloud on AWS) with even less change than typical rehosting — a narrower, more specialized "R" worth knowing exists distinctly from general Rehost.
5. **Repurchase** ("drop and shop") — replace the existing system with a different product entirely, commonly a SaaS alternative (e.g., migrating a self-hosted CRM to Salesforce, or a self-hosted email server to a hosted email service) rather than migrating the existing system's technology at all.
6. **Replatform** ("lift, tinker, and shift") — move to AWS with some cloud-optimization applied, without a full architectural rewrite — e.g., migrating a self-managed on-premises database to Amazon RDS (a managed service handling the same relational database engine) rather than continuing to self-manage it on an EC2 instance. A middle ground between Rehost's speed and Refactor's full modernization.
7. **Refactor / Re-architect** — substantially redesign the application to take full advantage of cloud-native capabilities (serverless, managed services, microservices decomposition) — highest modernization benefit and highest effort/risk/time investment, typically reserved for business-critical applications where the long-term benefit clearly justifies the larger investment.

## 5. Architecture & Components

| Component                          | Explanation                                                                                                                                                                                                                                     |
| ---------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Migration Portfolio Assessment** | The upfront analysis categorizing every workload in scope, typically using discovery tooling (e.g., AWS Application Discovery Service) to understand actual dependencies and characteristics before assigning an R.                             |
| **Migration Wave**                 | A grouped batch of workloads migrated together, typically sequenced by dependency order and risk level (lower-risk, less-interdependent workloads often migrated in earlier waves to build organizational confidence and process maturity).     |
| **AWS Migration Hub**              | A centralized service for tracking migration progress across many workloads and tools.                                                                                                                                                          |
| **6-R Predecessor Note**           | The framework historically had 6 Rs (without Relocate); Relocate was added later as VMware Cloud on AWS matured — worth being aware this framework has evolved, and current AWS materials should be checked for the authoritative current list. |

## 6. Decision Framework — Choosing an R Per Workload

- **Is the workload still needed at all?** → If not, Retire.
- **Is there a blocker or lower priority preventing migration right now?** → Retain.
- **Is speed the primary driver (e.g., data center lease expiring soon), with modernization deferred?** → Rehost (or Relocate for VMware-heavy environments specifically).
- **Is there an existing SaaS product that could replace this system's function entirely?** → Repurchase.
- **Would moderate cloud-optimization (e.g., managed database service) provide meaningful benefit without a full rewrite?** → Replatform.
- **Is this a business-critical, long-lived application where full cloud-native modernization would provide substantial, durable benefit justifying real investment?** → Refactor/Re-architect.

## 7. Interview Questions with Model Answers

**🎯 Junior:** _"What are the 7 Rs of migration, briefly?"_
**Model answer:** They're the seven strategies for migrating a workload to AWS: Retire (decommission it, it's not needed), Retain (keep it where it is for now), Rehost (move it as-is, "lift and shift"), Relocate (a VMware-specific variant of rehosting), Repurchase (replace it with a different product, often SaaS), Replatform (move it with some cloud optimization, like using a managed database instead of self-hosting), and Refactor/Re-architect (redesign it to be cloud-native). Each workload in a migration gets assessed and assigned whichever of these fits best, rather than applying one strategy to everything.

**🎯 Intermediate:** _"Why might an organization deliberately choose Rehost for a workload that would clearly benefit from Refactor, if they know Rehost leaves that benefit on the table?"_
**Model answer:** Rehost is dramatically faster and lower-risk than Refactor, and sometimes speed itself is the actual business driver — a common real scenario is an expiring data center lease or contract forcing an exit by a hard deadline, where there simply isn't time to fully re-architect every workload before that deadline. In that situation, the pragmatic choice is often to rehost quickly to get out of the data center on time, and then revisit specific high-value workloads for refactoring later, once the immediate time pressure is resolved — deferring the modernization benefit rather than abandoning it entirely. It's also reasonable for lower-business-value workloads where the refactor investment simply isn't justified by the expected benefit, even without a hard deadline forcing the decision.

**🎯 Senior:** _"An organization has migrated 200 workloads over 18 months, all via Rehost, and is now unhappy that they're not seeing the cost savings and agility benefits they expected from 'moving to the cloud.' What's happening, and how would you advise them?"_
**Model answer:** This is a very common and predictable outcome — Rehost, by design, moves the workload with minimal changes, which means it also largely preserves the on-premises-style architecture's inefficiencies: statically-sized, always-on servers instead of elastic, usage-aligned resources, self-managed databases instead of managed services with their operational and often cost benefits, and no adoption of the managed/serverless services that provide much of AWS's actual efficiency advantage. Rehosting alone gets you out of a data center, but it doesn't inherently get you the cost and agility benefits that come specifically from actually using cloud-native patterns. Advise treating this as expected and by-design, not a failure, and now beginning a deliberate second phase — going back through those 200 rehosted workloads and identifying which specific ones would most benefit from Replatform or Refactor, prioritized by expected benefit versus effort, essentially applying the migration assessment discipline that was likely skipped or compressed during the original speed-focused rehost push, but now with the pressure of an imminent deadline removed.

**🎯 Architect:** _"Design a migration strategy for an organization with 500 applications, ranging from a critical customer-facing e-commerce platform to internal tools nobody has touched in years, under a business mandate to exit their data center within 12 months."_
**Model answer:** Start with a genuine discovery and assessment phase — using tooling like AWS Application Discovery Service to understand actual dependencies, usage patterns, and business criticality across all 500 applications, since a 12-month hard deadline means there's no time to make this decision app-by-app through manual investigation alone. Expect this assessment to immediately reveal a meaningful number of Retire candidates (genuinely unused or redundant systems, common in any 500-application estate that's accumulated over years) — removing those from the migration workload entirely is often the single highest-leverage early action. For the remaining applications, given the hard 12-month deadline, bias heavily toward Rehost/Relocate for the majority, specifically to guarantee the data center exit deadline is met, reserving Replatform for a smaller set of applications where a moderate optimization (like moving to RDS) is low-risk and fits comfortably within the timeline, and reserving Refactor only for the single most business-critical application — likely the customer-facing e-commerce platform — where the business impact of getting it right justifies dedicated, focused investment even under time pressure, while everything else takes the faster path. Sequence this into migration waves, starting with lower-risk, less-interdependent internal tools to build organizational process and confidence before tackling the more complex, higher-stakes e-commerce platform migration, and explicitly plan a second, post-deadline phase for revisiting rehosted workloads for further optimization once the immediate data-center-exit pressure is resolved — directly avoiding the Part 10 §5 senior-level scenario above, where an all-Rehost approach later disappoints on cost/agility expectations, by being explicit upfront that Rehost is phase one of two, not the final state.

## 8. Common Misconceptions

- "Migration means picking one strategy and applying it to everything." False — the entire point of the 7 Rs framework is workload-by-workload assessment; a large migration portfolio typically uses several different Rs simultaneously across different applications.
- "Rehost is a 'wrong' or inferior choice compared to Refactor." False as a blanket statement — Rehost is the _right_ choice for many real scenarios (time pressure, lower-value workloads, deferred modernization strategy) even though it leaves cloud-native benefits on the table; the framework exists precisely because different workloads genuinely warrant different strategies.

## 9. Key Takeaways

🔑 The 7 Rs — Retire, Retain, Rehost, Relocate, Repurchase, Replatform, Refactor — provide a structured, per-workload decision framework rather than a single, uniform migration strategy.
🔑 Retire and Retain are legitimate, often underused outcomes — not every workload should be migrated, and migration assessment frequently reveals genuinely unneeded systems.
🔑 Rehost is fast and low-risk but preserves on-premises-style inefficiencies; it's frequently phase one of a two-phase strategy (rehost first, optimize later), not a final destination.
🔑 The choice of R per workload should balance migration speed/deadline pressure against modernization benefit and business criticality — there's no universally correct choice independent of context.
🔑 A large migration should be sequenced into waves, generally starting with lower-risk, less-interdependent workloads to build process and confidence before tackling the most complex or critical systems.

## 10. Related Concepts

- **Well-Architected Framework** (the six-pillar lens migration decisions should also be evaluated against) → Part 10 §1.
- **Cost Optimization** (migration business cases are frequently built around expected cost savings, which Rehost alone often doesn't fully deliver) → Part 10 §2.
- **Amazon Cognito** and **Neptune & Graph ML** (application-identity and specialized-database tie-ins, rounding out this Part's technical breadth) → Part 10 §6-7.
- **AWS System Design** (applying everything from this roadmap to end-to-end architecture, including migrated/refactored systems) → Part 10 §8.
