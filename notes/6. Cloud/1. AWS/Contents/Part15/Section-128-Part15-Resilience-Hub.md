# Part 15, Section 2: AWS Resilience Hub

## 1. Definition

**Plain language:** [§127](./Section-127-Part15-Elastic-Disaster-Recovery.md) covered DRS's ability to recover a server-level failure — but a real application's resilience depends on far more than "can this one server come back after a disaster." Does the application have redundancy across Availability Zones? Are its dependencies (databases, queues) also resilient? Does its actual measured recovery time match what the business actually needs? AWS Resilience Hub is a service specifically designed to assess an application's overall resilience posture against defined targets, systematically, rather than relying on an ad hoc, informal sense of "this should probably be fine."

**Precise definition:** AWS Resilience Hub is a managed service that assesses an application's resilience against explicitly-defined **Resiliency Policies** (target RTO and RPO for different disruption types — infrastructure failure, Availability Zone disruption, Region disruption, application-level failure), analyzing the application's actual AWS architecture to identify specific gaps and providing prioritized, actionable recommendations for closing them, giving an organization a **Resiliency Score** and structured way to track resilience improvement over time.

## 2. Why It Exists / Problem It Solves

- [§92](../Part10/Section-92-Part10-DR-Strategy-Capstone.md)'s DR capstone and [§127](./Section-127-Part15-Elastic-Disaster-Recovery.md)'s DRS coverage addressed disaster recovery — but resilience is a broader concept encompassing an application's ability to withstand _any_ disruption, not only a full-scale declared disaster: a single Availability Zone failure, a dependent service's outage, a database failover — many of which this course's earlier material (multi-AZ architectures, [§23](../Part3/Section-23-Part3-Auto-Scaling-Groups.md); RDS Multi-AZ, [§50](../Part6/Section-50-Part6-RDS-HA-ReadReplicas-Backup.md)) already addressed piecemeal, but without a systematic way to verify an entire application's actual, current resilience posture against explicit targets.
- Without a structured assessment tool, an organization's confidence in an application's resilience is often based on architectural intent ("we designed this to be multi-AZ") rather than verified, current reality ("we've confirmed every component actually is multi-AZ, and recovery from an AZ failure genuinely meets our target RTO") — a gap between intended and actual resilience that often only becomes visible during a real disruption, precisely the wrong time to discover it.
- Resilience Hub exists to close that gap systematically: it analyzes an application's actual deployed architecture (commonly discovered via CloudFormation stacks, [§79](../Part9/Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md), or other supported resource-discovery mechanisms) against explicitly-stated resilience targets, and identifies specific, concrete gaps — this database has no read replica, this compute tier isn't spread across multiple AZs, this dependency has no defined failover behavior — rather than leaving resilience as an informal, unverified assumption.
- 🔑 **Key takeaway:** Resilience Hub applies the same "systematically verify against explicit targets rather than relying on informal confidence" principle established for AWS Config's compliance checking ([§74](../Part8/Section-74-Part8-AWS-Config.md)) and Well-Architected Framework reviews ([§89](../Part10/Section-89-Part10-WellArchitected-Framework.md)), here specifically focused on resilience posture.

## 3. Prerequisites and Dependencies

- **Well-Architected Framework** ([§89](../Part10/Section-89-Part10-WellArchitected-Framework.md)): resilience is a core dimension of the Reliability pillar specifically — Resilience Hub can be understood as purpose-built tooling for systematically assessing that one pillar in depth.
- **Multi-AZ architecture patterns** ([§23](../Part3/Section-23-Part3-Auto-Scaling-Groups.md), [§30](../Part4/Section-30-Part4-Subnets-RouteTables-IGW-NAT.md), [§50](../Part6/Section-50-Part6-RDS-HA-ReadReplicas-Backup.md)): this section assumes familiarity with the underlying redundancy patterns Resilience Hub assesses applications against.
- **Infrastructure as Code** ([§79](../Part9/Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)-[§82](../Part9/Section-82-Part9-Terraform-on-AWS.md)): Resilience Hub commonly discovers an application's architecture via its CloudFormation (or other IaC) definition, directly connecting to Part 9's IaC material.

## 4. Internal Working / Architecture & Components

### 4.1 Resiliency Policies — Defining the Target

- A **Resiliency Policy** explicitly defines target RTO and RPO ([§92](../Part10/Section-92-Part10-DR-Strategy-Capstone.md)'s framework) for four distinct disruption categories: **Infrastructure** (a single component failure), **Availability Zone** (an entire AZ becoming unavailable), **Region** (an entire AWS Region becoming unavailable), and **Application** (a software-level failure, distinct from underlying infrastructure issues).
- Defining separate targets per disruption type is a meaningful design choice — an application might reasonably tolerate a longer RTO for a full Regional disruption (a rare, extreme event) than for a single infrastructure component failure (a more common, lower-severity event that better architecture should handle almost transparently) — Resiliency Policies let an organization express these genuinely different tolerance levels explicitly, rather than a single blanket RTO/RPO target applied uniformly regardless of disruption severity.

### 4.2 Assessment — Analyzing Actual Architecture Against the Policy

- Resilience Hub imports an application's actual architecture (from a CloudFormation stack, Terraform state, or other supported source, [§79](../Part9/Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)-[§82](../Part9/Section-82-Part9-Terraform-on-AWS.md)) and runs an **assessment**, analyzing each component against resilience best practices relevant to its type — is a database Multi-AZ, is compute spread across multiple AZs, are there single points of failure in the dependency chain — comparing the architecture's actual, current capability against the Resiliency Policy's stated targets.
- The assessment produces a **Resiliency Score** — a quantified measure of how well the current architecture meets the defined policy — alongside specific, itemized recommendations for closing identified gaps, each typically annotated with its expected impact on the overall score, letting a team prioritize remediation effort toward the highest-impact gaps first.
- ⚠️ **Warning:** Resilience Hub's assessment is based on architectural analysis (does the _design_ include appropriate redundancy) — it's a complementary, not identical, capability to Chaos Engineering/Fault Injection Service ([§129](./Section-129-Part15-FIS-Chaos-Engineering.md)), which validates resilience through actual, real-world fault injection rather than architectural analysis alone; a component can be architecturally well-designed on paper while still having an operational gap (a misconfigured failover mechanism, for example) that only genuine fault injection testing would reveal.

### 4.3 Operational Recommendations Beyond Architecture

- Resilience Hub's recommendations extend beyond pure infrastructure architecture to include operational readiness — recommending appropriate CloudWatch Alarms ([§71](../Part8/Section-71-Part8-CloudWatch-Alarms-Dashboards.md)) for detecting the specific failure modes relevant to the application, and highlighting whether adequate testing (drills, [§127](./Section-127-Part15-Elastic-Disaster-Recovery.md) §4.2; chaos experiments, [§129](./Section-129-Part15-FIS-Chaos-Engineering.md)) has actually been performed to validate the assessed architecture's resilience claims in practice, not just on paper.
- 🔑 **Key takeaway:** this connects Resilience Hub directly to the broader theme established throughout this Part and this course generally — architectural design alone (what Resilience Hub primarily assesses) is necessary but not sufficient for genuine resilience; operational validation (drills, chaos experiments, [§127](./Section-127-Part15-Elastic-Disaster-Recovery.md), [§3](../Part1/Section-03-Part1-Shared-Responsibility-Model.md)) closes the gap between "designed to be resilient" and "verified to actually be resilient," the same "measure whether it's actually working, not just whether it's technically present" discipline this course has repeatedly emphasized ([§119](../Part13/Section-119-Part13-Guardrails-Operations.md), [§125](../Part14/Section-125-Part14-SOC-Patterns.md)).

## 5. Lifecycle / Workflow

1. An application's architecture is defined via Infrastructure as Code ([§79](../Part9/Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md)-[§82](../Part9/Section-82-Part9-Terraform-on-AWS.md)) and imported into Resilience Hub.
2. A Resiliency Policy is defined, stating target RTO/RPO for each disruption category (§4.1), reflecting the application's actual business criticality.
3. An assessment runs, comparing the application's actual architecture against the policy, producing a Resiliency Score and prioritized, itemized recommendations.
4. The team remediates identified gaps — following the recommendations (adding a read replica, spreading compute across additional AZs, adding recommended alarms) — and re-runs the assessment to confirm the score has improved as expected.
5. Ongoing, the assessment is re-run periodically (especially after any significant architectural change) to confirm resilience posture hasn't silently regressed, and operational validation (drills, chaos experiments, [§127](./Section-127-Part15-Elastic-Disaster-Recovery.md), [§3](../Part1/Section-03-Part1-Shared-Responsibility-Model.md)) is performed to verify the assessed architecture's resilience claims hold up in actual practice.

## 6. Configuration

| Setting                                                                        | Purpose                                                                                   |
| ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| Resiliency Policy (RTO/RPO per disruption type)                                | The explicit resilience target the application's architecture is assessed against.        |
| Application source (CloudFormation stack, Terraform state, resource discovery) | How Resilience Hub discovers the actual architecture being assessed.                      |
| Assessment schedule                                                            | How frequently assessments are re-run, particularly relevant after architectural changes. |

## 7. Commands / API (Full Documentation)

### 7.1 Defining a Resiliency Policy

- **Purpose:** Establish explicit RTO/RPO targets per disruption type.
- **Syntax:**

```bash
aws resiliencehub create-resiliency-policy \
  --policy-name payments-app-policy \
  --tier MissionCritical \
  --policy '{"AZ":{"rtoInSecs":300,"rpoInSecs":60},"Region":{"rtoInSecs":3600,"rpoInSecs":300},"Software":{"rtoInSecs":60,"rpoInSecs":0},"Hardware":{"rtoInSecs":60,"rpoInSecs":0}}'
```

- **Important arguments:** distinct RTO/RPO targets per disruption type (`AZ`, `Region`, `Software`, `Hardware`) directly implement §4.1's principle — this example reflects an appropriately tighter target for AZ disruption (5-minute RTO) than for a full Regional disruption (1-hour RTO), matching the different likelihood/severity of each disruption category. `--tier MissionCritical` reflects the application's business-criticality classification, informing default expectations.
- **Common errors:** setting uniformly aggressive RTO/RPO targets across every disruption type regardless of actual business need, potentially driving unnecessarily expensive architectural recommendations disproportionate to the application's genuine criticality — mirroring the same over-investment risk flagged in [§127](./Section-127-Part15-Elastic-Disaster-Recovery.md)'s Architect answer regarding DR tooling choice.

### 7.2 Running an Assessment

```bash
aws resiliencehub create-app-assessment \
  --app-arn arn:aws:resiliencehub:us-east-1:111122223333:app/payments-app \
  --assessment-name quarterly-assessment
```

- **Practical example / expected output:** returns a detailed assessment report including the overall Resiliency Score, per-disruption-type compliance status against the policy, and a prioritized list of specific recommendations (e.g., "enable Multi-AZ on RDS instance X" or "add a CloudWatch Alarm for Y metric") with each recommendation's estimated impact on the overall score.

## 8. Hands-On Example — Assessment-Driven Improvement

```text
Initial assessment of "payments-app":
  Resiliency Score: 62/100
  AZ disruption target: RTO 5min / RPO 1min --> CURRENT: FAILS
    (RDS instance is single-AZ, no automatic failover -- §50's
     Multi-AZ pattern was never actually applied to this specific
     database, despite being architecturally well-understood elsewhere
     in the organization)
  Recommendation: Enable RDS Multi-AZ (estimated score impact: +18)

Team implements the recommendation, re-runs assessment:
  Resiliency Score: 80/100
  AZ disruption target: PASSES

Remaining gap identified: no alarms configured for RDS failover events
  Recommendation: Add CloudWatch Alarm for RDS failover
  (operational readiness gap, per §4.3, not purely architectural)
```

This demonstrates Resilience Hub's core value directly: a specific, previously-unverified architectural gap (a single-AZ database in an application otherwise assumed resilient) is surfaced concretely, with a prioritized, quantified recommendation — turning "we think this is resilient" into "we've verified this specific gap and closed it, with a measurable score improvement confirming the fix," exactly the kind of systematic verification [§2](../Part1/Section-02-Part1-AWS-Global-Infrastructure.md) establishes as this service's core purpose.

## 9. Production and Enterprise Usage

- Organizations increasingly incorporate Resilience Hub assessments into their CI/CD pipeline ([§86](../Part9/Section-86-Part9-CICD-Infrastructure-GitOps.md)) — running an assessment as part of the deployment pipeline for any application architecture change, catching resilience regressions before they reach production, directly extending the "shift left" principle established for security scanning ([§86](../Part9/Section-86-Part9-CICD-Infrastructure-GitOps.md) [§11](../Part2/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md)) to resilience posture specifically.
- Resiliency Score tracking over time is commonly reported to leadership as a concrete, quantified measure of an organization's overall resilience posture and improvement trajectory — directly analogous to the program-health-metrics discipline established in [§119](../Part13/Section-119-Part13-Guardrails-Operations.md) and [§125](../Part14/Section-125-Part14-SOC-Patterns.md), here applied to resilience specifically.
- Resilience Hub's recommendations frequently surface genuine architectural debt — components that were understood, at the time they were built, to have a resilience gap that was deliberately deferred, or components where resilience simply wasn't a design consideration at the time — giving organizations a structured, prioritized way to address this debt systematically rather than only reactively after an actual disruption reveals it.

## 10. Security Considerations

- Resilience Hub's access to an application's architecture and assessment results is itself a meaningful access-control consideration — assessment results can reveal specific security-adjacent architectural weaknesses (a lack of redundancy that could be exploited to cause a denial-of-service-style impact), warranting appropriately scoped access following least-privilege, similar to how Macie/Detective findings ([§121](../Part14/Section-121-Part14-Macie.md)-[§122](../Part14/Section-122-Part14-Detective.md)) warrant restricted access given their own sensitivity.
- Resilience and security are related but distinct concerns — a highly resilient architecture (redundant, quick to recover) isn't automatically a secure one, and vice versa; this section's material complements, rather than substitutes for, Part 14's security operations coverage.

## 11. Performance Considerations

- Resilience Hub's assessment itself is an analysis operation (not a workload-performance-affecting one) — the "performance" consideration relevant here is really about how quickly and efficiently an organization can iterate through the assess-remediate-reassess cycle ([§5](../Part1/Section-05-Part1-Ways-to-Interact-with-AWS.md)), which directly determines how quickly overall resilience posture actually improves.
- Recommendations with the highest score impact (§7.2) should generally be prioritized first, maximizing resilience improvement per unit of engineering effort invested — a straightforward but important prioritization principle for teams with limited remediation capacity relative to the total identified gap list.

## 12. Monitoring

- Resiliency Score trends over time (via periodic re-assessment, [§5](../Part1/Section-05-Part1-Ways-to-Interact-with-AWS.md)) are the primary tracked signal — is the score improving as remediation work proceeds, or regressing as new architectural changes introduce new gaps without corresponding assessment/remediation.
- Resilience Hub's recommended alarms (§4.3) should themselves be implemented and monitored as part of the application's standard observability stack (Part 8), closing the loop between "Resilience Hub identified this operational monitoring gap" and "this gap is now actually addressed and being watched."

## 13. Troubleshooting

| Symptom                                                                 | Cause                                                                                                                                                      | Fix                                                                                                                                                                                                      |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Assessment can't fully analyze the application's architecture           | Application source (CloudFormation/Terraform) doesn't fully capture all relevant resources, or uses a pattern Resilience Hub's discovery doesn't recognize | Review current documentation for supported architecture-discovery patterns; ensure IaC definitions are complete and current                                                                              |
| Resiliency Score doesn't improve despite implementing a recommended fix | Fix wasn't fully or correctly implemented, or the re-assessment wasn't run against updated architecture                                                    | Verify the fix was actually deployed and reflected in the architecture Resilience Hub analyzes; re-run assessment                                                                                        |
| Score regresses unexpectedly between assessments                        | An architectural change (possibly unrelated to resilience) inadvertently removed or weakened existing redundancy                                           | Investigate recent architectural changes for unintended resilience regressions — a good candidate for the CI/CD-integrated assessment practice from [§9](../Part2/Section-09-Part2-IAM-Core-Concepts.md) |

## 14. Best Practices

- Define distinct RTO/RPO targets per disruption type (AZ, Region, Software, Hardware), reflecting genuinely different likelihood/severity rather than one uniform target.
- Integrate resilience assessment into CI/CD pipelines, catching regressions before they reach production.
- Prioritize remediation by score impact, maximizing resilience improvement per unit of engineering effort.
- Complement architectural assessment (Resilience Hub) with operational validation (drills, chaos experiments, [§127](./Section-127-Part15-Elastic-Disaster-Recovery.md), [§3](../Part1/Section-03-Part1-Shared-Responsibility-Model.md)) — architecture-on-paper and verified-in-practice are related but distinct.
- Track Resiliency Score trends over time as a genuine organizational metric, not a one-time assessment.

## 15. Anti-Patterns and Common Mistakes

- ❌ Treating a single, one-time Resilience Hub assessment as sufficient, without re-assessing after subsequent architectural changes that could introduce new gaps.
- ❌ Setting uniformly aggressive RTO/RPO targets across every disruption type regardless of actual business criticality, driving disproportionately expensive remediation relative to genuine need.
- ❌ Treating a passing Resiliency Score as complete proof of resilience without also performing operational validation (drills, chaos experiments) — architectural analysis and real-world fault injection are complementary, not substitutes (§4.2's warning).
- ❌ Never implementing Resilience Hub's operational recommendations (alarms, monitoring) even after addressing the architectural gaps, leaving genuine visibility gaps even in an architecturally-improved system.

## 16. Interview Questions with Model Answers

**🎯 Junior:** _"What does AWS Resilience Hub actually do?"_
**Model answer:** It assesses an application's actual AWS architecture against explicitly-defined resilience targets — target recovery time and recovery point objectives for different types of disruption, like a single component failure, an Availability Zone outage, or a full Region outage. It identifies specific gaps, like a database that isn't Multi-AZ, gives a quantified Resiliency Score, and provides prioritized recommendations for closing those gaps, so an organization has a concrete, verified picture of resilience rather than just an assumption that the architecture is probably fine.

**🎯 Intermediate:** _"Why does Resilience Hub define separate RTO/RPO targets for AZ disruption versus Region disruption, rather than one single target?"_
**Model answer:** These are genuinely different disruption categories with different likelihood and severity — a single AZ becoming unavailable is a more common, lower-severity event that well-architected applications should handle quickly and often close to transparently, while an entire Region becoming unavailable is much rarer and more severe, and might reasonably justify a longer acceptable recovery time given the scale of what's actually being recovered from. Defining separate targets lets an organization express these genuinely different tolerance levels explicitly, rather than forcing one blanket target that would either be unnecessarily strict (and expensive) for the more common AZ scenario, or insufficiently strict for the rarer Region scenario if a single compromise value were chosen instead.

**🎯 Senior:** _"A team's Resilience Hub assessment shows a high Resiliency Score, but a recent actual AZ disruption still caused a meaningful outage. How do you explain this gap, and what would you investigate?"_
**Model answer:** This is exactly the gap between architectural analysis and operational reality that §4.2's warning describes — a high score confirms the _architecture_ includes appropriate redundancy on paper, but doesn't guarantee that redundancy actually functions correctly in a real disruption. I'd investigate whether the failure was in the architecture itself (perhaps a component Resilience Hub's discovery didn't fully capture, or a dependency outside the assessed application boundary that also failed) or in the operational execution of failover (a database configured for Multi-AZ that, for some reason, didn't actually fail over as expected — a misconfiguration or an edge case the architectural analysis alone couldn't have surfaced). This is a strong argument for pairing Resilience Hub's architectural assessment with actual chaos engineering / Fault Injection Service testing ([§129](./Section-129-Part15-FIS-Chaos-Engineering.md)), which would have tested the _actual_ failover behavior under real, injected AZ-level disruption before a genuine outage did — closing exactly the gap this incident revealed.

**🎯 Architect:** _"Design a resilience governance program for a large organization with hundreds of applications, ensuring resilience posture is systematically tracked, improved over time, and appropriately proportionate to each application's actual business criticality."_
**Model answer:** Establish a tiered Resiliency Policy model, mirroring the risk-proportionate investment principle established throughout this course ([§115](../Part13/Section-115-Part13-ControlTower.md)'s guardrail-strictness-by-OU, [§124](../Part14/Section-124-Part14-Automated-Incident-Response.md)'s automated-response tiers) — a small number of standard Resiliency Policy templates (Mission-Critical, Important, Standard) with appropriately differentiated RTO/RPO targets per tier, applied to applications based on genuine business-criticality classification rather than every application receiving identical, maximally-aggressive targets regardless of actual need. Integrate Resilience Hub assessment into the organization's standard CI/CD pipeline templates (echoing [§86](../Part9/Section-86-Part9-CICD-Infrastructure-GitOps.md)'s shared-pipeline-template pattern), so every application automatically gets assessed on significant architectural changes without requiring each team to independently remember to run assessments manually. Track Resiliency Score trends at both the individual-application and organization-wide aggregate level, reporting the aggregate trend to leadership as a concrete resilience-posture metric — directly following the program-health-metrics discipline established in [§119](../Part13/Section-119-Part13-Guardrails-Operations.md) and [§125](../Part14/Section-125-Part14-SOC-Patterns.md) — while giving individual application teams their own specific, prioritized remediation backlogs. Critically, pair this architectural-assessment program with a complementary, regularly-scheduled chaos engineering practice ([§129](./Section-129-Part15-FIS-Chaos-Engineering.md)) specifically for Mission-Critical tier applications, given §4.2's established gap between architectural analysis and operational reality — a high Resiliency Score alone shouldn't be treated as sufficient proof of resilience for the organization's most critical systems without also validating that resilience through actual, real-world fault injection testing.

## 17. Common Misconceptions

- "A high Resiliency Score guarantees an application will actually survive a real disruption without issue." False — as the Senior interview answer establishes, Resilience Hub assesses architectural design; actual operational behavior under a real disruption can still reveal gaps architectural analysis alone doesn't catch, which is why chaos engineering ([§129](./Section-129-Part15-FIS-Chaos-Engineering.md)) remains a necessary complement.
- "Every application should target the same aggressive RTO/RPO regardless of actual criticality." False — as §4.1 and the Architect answer establish, resilience targets should be proportionate to genuine business need, not uniformly maximized regardless of cost/complexity trade-offs.
- "Resilience Hub is the same thing as disaster recovery tooling like DRS." False — Resilience Hub assesses architecture against resilience targets and provides recommendations; DRS ([§127](./Section-127-Part15-Elastic-Disaster-Recovery.md)) is a specific recovery mechanism. They're complementary — Resilience Hub might recommend DRS as part of closing an identified DR-related gap.

## 18. Key Takeaways

🔑 Resilience Hub systematically assesses an application's actual architecture against explicitly-defined RTO/RPO targets per disruption type, replacing informal confidence with a verified, quantified Resiliency Score.
🔑 Distinct targets per disruption type (AZ, Region, Software, Hardware) let an organization express genuinely different tolerance levels, rather than one uniform target regardless of disruption severity/likelihood.
🔑 Architectural assessment (Resilience Hub) and operational validation (drills, chaos experiments) are complementary — a high score confirms good design, not necessarily verified real-world behavior.
🔑 Resiliency Score tracking over time, integrated into CI/CD, catches resilience regressions before they reach production and provides a concrete organizational resilience metric.
🔑 Resilience targets and remediation investment should be proportionate to actual application business criticality, following the same risk-proportionate investment principle established throughout this course.

## 19. Related Concepts

- **AWS Well-Architected Framework** ([§89](../Part10/Section-89-Part10-WellArchitected-Framework.md)) — the Reliability pillar Resilience Hub provides purpose-built, systematic assessment tooling for.
- **AWS Elastic Disaster Recovery** ([§127](./Section-127-Part15-Elastic-Disaster-Recovery.md)) — a specific recovery mechanism Resilience Hub might recommend as part of closing an identified gap.
- **CI/CD for Infrastructure** ([§86](../Part9/Section-86-Part9-CICD-Infrastructure-GitOps.md)) — the pipeline integration pattern for automated, ongoing resilience assessment.
- **AWS Fault Injection Service** ([§129](./Section-129-Part15-FIS-Chaos-Engineering.md), next section) — the complementary chaos engineering capability validating resilience through actual fault injection, closing the gap architectural analysis alone leaves open.
