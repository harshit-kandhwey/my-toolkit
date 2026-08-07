# Part 9, Section 7: Deployment Strategies — Blue/Green, Canary, Rolling

## 1. Definition

**Plain language:** Once you have a built artifact ([§83](./Section-83-Part9-CodePipeline-CodeBuild.md)) and a mechanism to deploy it (CodeDeploy, [§84](./Section-84-Part9-CodeDeploy.md)), there's still a genuine design decision left: exactly _how_ does traffic move from the old version to the new one? This section covers the actual patterns — all-at-once, rolling, blue/green, and canary — as conceptual strategies, independent of which specific AWS service implements them, since the same underlying trade-offs apply whether you're deploying via CodeDeploy, a Kubernetes rollout, or a hand-rolled script.

**Precise definition:** A deployment strategy defines how traffic or workload transitions from an existing application version to a new one during a release, with the major patterns — all-at-once, rolling, blue/green, and canary — differing in their trade-offs between deployment speed, resource cost during the transition, blast radius of a bad release, and rollback speed, each appropriate for different combinations of risk tolerance, traffic volume, and infrastructure cost sensitivity.

## 2. Why It Exists / Problem It Solves

Deploying a new version of an application is inherently risky — even with thorough testing ([§83](./Section-83-Part9-CodePipeline-CodeBuild.md)'s build/test stages), a new version can still fail in production in ways tests didn't catch (a configuration difference, a scale-dependent bug, an unexpected interaction with production data). The question every deployment strategy answers differently is: **how much of your traffic is exposed to that risk, for how long, before you're confident enough to commit fully** — and each strategy makes a different, explicit trade-off between minimizing that exposure and minimizing deployment complexity/cost.

## 3. Prerequisites and Dependencies

- **AWS CodeDeploy** ([§84](./Section-84-Part9-CodeDeploy.md)): the AWS-native mechanism most directly implementing these patterns for EC2/Lambda/ECS deployments.
- **Elastic Load Balancing and Auto Scaling** (Part 3): the underlying traffic-routing and capacity mechanisms several of these strategies depend on.
- **CloudWatch Alarms** ([§71](../Part8/Section-71-Part8-CloudWatch-Alarms-Dashboards.md)): the health-signal mechanism that makes any of these strategies' automated rollback meaningful.

## 4. The Deployment Strategies, In Depth

### All-at-Once

- Every instance/task is updated simultaneously to the new version.
- **Fastest** deployment, **zero additional infrastructure cost** during the transition (no parallel environment), but **highest risk** — if the new version has a problem, 100% of traffic is immediately affected, and there's no "old version still running" fallback to immediately serve traffic from during rollback (rollback requires redeploying the old version, which takes time).
- Appropriate for: low-stakes internal tools, environments where brief full downtime is acceptable, or situations where deployment speed is prioritized over risk minimization (e.g., a critical hotfix where the bug being fixed is worse than the deployment risk).

### Rolling

- Instances/tasks are updated in **batches** (e.g., 25% at a time, or one at a time), with each batch verified healthy before the next batch proceeds.
- **Moderate risk** — a bad deployment is caught after the first batch (assuming reasonable health checking) and only affects that batch's portion of traffic, not the whole fleet, though the affected batch's users do experience the issue.
- **No additional infrastructure cost** (no parallel environment; the existing fleet is updated in place, batch by batch), but the fleet runs at **reduced capacity** during the rollout, since some fraction of instances are always mid-update, unless additional temporary capacity is provisioned.
- Directly corresponds to CodeDeploy's in-place `HalfAtATime`/`OneAtATime`/custom deployment configurations ([§84](./Section-84-Part9-CodeDeploy.md)).

### Blue/Green

- A completely separate, parallel **"green" environment** is provisioned running the new version, validated for health, and traffic is then **cut over** from "blue" (current) to "green" — either instantly (all at once) or gradually.
- **Near-zero downtime**, and critically, **extremely fast rollback** — since "blue" is still fully running and available, reverting is simply routing traffic back to it, not redeploying anything.
- **Requires double the compute capacity** during the transition window (both environments running simultaneously), a direct, real cost trade-off for the availability/rollback-speed benefit.
- Directly corresponds to CodeDeploy's blue/green deployment type ([§84](./Section-84-Part9-CodeDeploy.md)).

### Canary

- A **small percentage** of traffic (e.g., 5%) is routed to the new version first, monitored closely, and — if healthy — the percentage is gradually increased (either in defined steps, or linearly over time) until 100% of traffic is on the new version.
- **Lowest blast radius** of any strategy if something is wrong — only the small canary percentage of users are ever exposed to a bad release before it's caught and rolled back.
- Requires genuinely meaningful health monitoring at each traffic-percentage step, since the strategy's entire safety value depends on actually detecting a problem in the canary population before expanding further — a canary strategy with no real health checking provides false confidence, not actual risk reduction.
- Often implemented as a specific _mode_ of blue/green traffic-shifting (CodeDeploy's canary and linear traffic-shifting configurations for Lambda/ECS, [§84](./Section-84-Part9-CodeDeploy.md)) rather than a wholly separate mechanism.

## 5. Comparison Table

| Strategy    | Downtime                | Rollback Speed                      | Infra Cost During Deploy         | Blast Radius of a Bad Release                                  | Complexity   |
| ----------- | ----------------------- | ----------------------------------- | -------------------------------- | -------------------------------------------------------------- | ------------ |
| All-at-Once | Possible brief downtime | Slow (requires redeploy)            | None                             | 100% immediately                                               | Lowest       |
| Rolling     | None (reduced capacity) | Moderate (revert remaining batches) | None (or requires temp capacity) | Partial, batch-limited                                         | Low-Moderate |
| Blue/Green  | Near-zero               | Fastest (route back to blue)        | Double, during transition        | Depends on cutover style (0% if canary-style, 100% if instant) | Moderate     |
| Canary      | Near-zero               | Fast (stop shift, revert canary %)  | Slight (canary instances)        | Smallest — limited to canary %                                 | Highest      |

## 6. Interview Questions with Model Answers

**🎯 Junior:** _"What's the fundamental difference between a rolling deployment and a blue/green deployment?"_
**Model answer:** A rolling deployment updates the existing fleet of instances in place, batch by batch — there's only ever one environment, gradually transitioning. A blue/green deployment provisions a completely separate, parallel environment running the new version, validates it, and then cuts traffic over — so there are briefly two full environments running simultaneously. The practical difference is that blue/green needs double the infrastructure capacity during the transition but gives you near-instant rollback by just routing traffic back to the still-running old environment, while rolling deployment doesn't need extra capacity but rollback means reverting the batches you've already updated, which takes more time.

**🎯 Intermediate:** _"Why is a canary deployment's safety value dependent on genuinely meaningful health checks, and what happens if the health checks are too shallow?"_
**Model answer:** The entire point of a canary deployment is exposing only a small percentage of traffic to the new version first, specifically so a problem can be caught and the rollout stopped before it reaches the full user base. That safety mechanism only works if whatever's monitoring the canary population can actually detect a real problem — if the health check is shallow, like just confirming the service responds to any request rather than checking that responses are actually correct, a genuinely broken new version could sail through the canary stage with an artificially clean bill of health, and the rollout would proceed to 100% traffic on a broken release, completely defeating the purpose of using canary in the first place. The strategy provides a structural opportunity to catch problems early, but it doesn't automatically provide the detection itself — that still has to be built deliberately.

**🎯 Senior:** _"A team wants to switch their critical payment-processing service from all-at-once to canary deployments, but is concerned about the added complexity and cost. How would you help them decide if it's worth it?"_
**Model answer:** I'd frame this as an explicit cost-benefit comparison specific to their actual risk profile, rather than assuming canary is automatically the right answer just because it's the most sophisticated option. For a payment-processing service specifically, the cost of a bad all-at-once deployment — every single transaction potentially affected simultaneously, with slow rollback while the old version is redeployed — is genuinely severe, both financially and in terms of customer trust, which is exactly the kind of high-stakes, asymmetric-risk scenario canary deployment is designed for. The added operational complexity (building genuinely meaningful health checks at each traffic-percentage step, the engineering time to set up the canary infrastructure) is a real, one-time cost, but it's being weighed against a recurring risk that exists on every single deployment going forward. Given the described criticality, I'd recommend the switch, but I'd emphasize that the value only materializes if they invest genuinely in the health-check quality — adopting canary with weak health checks would add complexity without adding real safety, which is a trap worth calling out explicitly before they commit to the change.

**🎯 Architect:** _"Design a tiered deployment-strategy policy for an organization with services ranging from internal admin tools to customer-facing payment APIs, avoiding a one-size-fits-all mandate that would either over-engineer low-stakes services or under-protect high-stakes ones."_
**Model answer:** I'd define deployment-strategy tiers explicitly tied to business criticality and blast-radius tolerance, rather than mandating one strategy organization-wide. For internal, low-traffic admin tools with a small user base and easy manual recovery, all-at-once or simple rolling deployment is entirely appropriate — the operational overhead of blue/green or canary infrastructure isn't justified by the actual risk. For moderate-traffic customer-facing services where downtime is undesirable but a brief partial-impact window is tolerable, rolling deployment with reasonable batch sizing and solid health checks is a good default. For the highest-stakes services — payment APIs, authentication, anything where a bad release has severe, hard-to-reverse consequences — I'd mandate canary deployment with genuinely rigorous, business-logic-aware health validation at each step, accepting the added infrastructure cost and engineering complexity as a direct, justified trade-off against the severity of the risk being managed. I'd document this tiering explicitly as organizational policy, including the specific criteria (customer-facing, transaction-processing, blast-radius severity) that place a service in each tier, so teams have clear, defensible guidance rather than needing to independently re-derive the right strategy for every new service from scratch.

## 7. Common Misconceptions

- "Canary is strictly better than blue/green, which is strictly better than rolling." False — each strategy is a different point on the same speed/cost/risk trade-off curve, and the "best" one is the one appropriate for the specific service's actual risk profile and cost tolerance, not a fixed ranking.
- "Blue/green deployments eliminate deployment risk entirely." False — blue/green minimizes rollback _time_ and downtime, but if the cutover to green is instant (all traffic at once) rather than gradual, 100% of traffic is still exposed to a bad release the moment cutover happens; blue/green and canary are complementary, not mutually exclusive (many blue/green implementations use canary-style gradual traffic shifting during the cutover itself).

## 8. Key Takeaways

🔑 Every deployment strategy trades off deployment speed, infrastructure cost during transition, rollback speed, and blast radius of a bad release — there's no universally "best" strategy independent of context.
🔑 All-at-once is fastest and cheapest but riskiest; rolling reduces blast radius without extra infrastructure cost but with slower rollback; blue/green gives near-instant rollback at double the transition-time infrastructure cost; canary minimizes blast radius most but requires the most sophisticated health-monitoring investment.
🔑 A strategy's safety value is only as real as the health checks backing it — canary and blue/green's risk-reduction benefits require genuinely meaningful health validation, not superficial checks.
🔑 Blue/green and canary are complementary, not mutually exclusive — a blue/green cutover can itself use gradual, canary-style traffic shifting rather than an instant switch.
🔑 A mature organization typically applies different strategies to different services based on actual business criticality, rather than mandating one strategy uniformly.

## 9. Related Concepts

- **AWS CodeDeploy** (the AWS-native mechanism implementing these patterns) → [§84](./Section-84-Part9-CodeDeploy.md).
- **AWS CodePipeline & CodeBuild** (the pipeline stages preceding a strategy-driven deployment) → [§83](./Section-83-Part9-CodePipeline-CodeBuild.md).
- **CloudWatch Alarms** (the health-signal foundation every strategy's safety depends on) → [§71](../Part8/Section-71-Part8-CloudWatch-Alarms-Dashboards.md).
- **Well-Architected Framework** (the Reliability/Cost trade-off language directly applicable to strategy selection) → [§89](../Part10/Section-89-Part10-WellArchitected-Framework.md).
