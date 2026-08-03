# Part 15, Section 3: AWS Fault Injection Service (FIS) — Chaos Engineering

## 1. Definition

**Plain language:** §128 flagged the gap between "architecturally designed to be resilient" and "verified, through actual testing, to genuinely be resilient" — and named chaos engineering as the way to close it. AWS Fault Injection Service (FIS) is AWS's managed tooling for chaos engineering: deliberately, safely injecting real faults into a running system — terminating an instance, adding network latency, exhausting CPU — to verify the system actually responds and recovers the way its architecture claims it should, rather than just assuming it would.

**Precise definition:** AWS Fault Injection Service (FIS) is a managed chaos engineering service that lets an organization run controlled **experiments** — deliberately injecting real faults (instance termination, network disruption, resource exhaustion, API throttling simulation, and others) into a running AWS environment, scoped by defined targets and safety guardrails, and monitored via defined **stop conditions** — to empirically validate that a system's resilience mechanisms (auto-scaling, failover, retry logic) actually work as intended under real, injected failure conditions.

## 2. Why It Exists / Problem It Solves

- §128's Resilience Hub assessment analyzes architecture and produces a score — but a passing score confirms the _design_ includes appropriate redundancy; it doesn't confirm that redundancy actually _functions correctly_ when a real failure occurs, since a subtle misconfiguration, an untested failover path, or an incorrect assumption about how a dependency behaves under stress can all remain invisible until an actual failure — ideally a controlled, intentional one, not a genuine production incident — reveals it.
- Traditional testing (unit tests, integration tests, Part 9's testing-adjacent material) validates that code behaves correctly under expected conditions — it rarely, by design, validates behavior under genuinely adverse, failure-mode conditions (a dependency suddenly unavailable, a network partition, a resource exhausted) since those conditions are inherently harder to simulate realistically in a standard test environment.
- Chaos engineering directly addresses this gap: by deliberately, safely injecting real faults into a system (ideally, eventually, in production or a production-like environment, under carefully controlled and bounded conditions), an organization can empirically verify — not just assume — that their resilience mechanisms actually work, discovering gaps through controlled experimentation rather than through an actual, uncontrolled production incident.
- 🔑 **Key takeaway:** FIS is specifically what closes the gap §128 §4.2 identified between architectural analysis and verified operational reality — Resilience Hub tells you what _should_ work based on design; FIS tells you what _actually_ works based on real, injected failure, directly completing this Part's overall resilience-validation narrative.

## 3. Prerequisites and Dependencies

- **AWS Resilience Hub** (§128): FIS experiments are commonly designed specifically to validate the resilience mechanisms Resilience Hub's architectural assessment identified as present — this section builds directly on that foundation.
- **Auto Scaling Groups, Multi-AZ architectures** (§23, §50): the specific resilience mechanisms FIS experiments most commonly target for validation.
- **CloudWatch Alarms** (§71): FIS's stop-condition mechanism (§4.2) integrates directly with CloudWatch Alarms as a safety control.

## 4. Internal Working / Architecture & Components

### 4.1 Experiments, Actions, and Targets

- An FIS **experiment template** defines one or more **actions** (the specific fault being injected — terminating an EC2 instance, injecting network latency, throttling API calls, exhausting CPU) applied to specific **targets** (which resources the action applies to, selected via tags, resource IDs, or other filtering criteria) — a deliberately scoped, precise specification of exactly what fault happens to exactly what resources, not a vague or overly broad disruption.
- FIS provides pre-built actions for common, well-understood fault categories (EC2 instance termination/stop, EBS volume I/O impairment, network latency/packet-loss injection, RDS failover triggering, and others), removing the need for an organization to build their own custom fault-injection tooling from scratch, echoing the same "use managed tooling instead of self-building the equivalent capability" pattern established throughout this course.
- Practical example: an experiment targeting "50% of EC2 instances tagged `Environment: staging` and `Tier: application`" with the action "terminate" — precisely scoped to a specific, bounded subset of resources, not an unbounded or accidentally-broad blast radius.

### 4.2 Stop Conditions — The Critical Safety Mechanism

- A **stop condition** is a CloudWatch Alarm (§71) that FIS monitors throughout an experiment's execution — if the alarm enters an alarm state (indicating the injected fault is causing worse-than-expected impact, beyond what the experiment intended to safely validate), FIS automatically halts the experiment immediately, stopping further fault injection and, where applicable, reverting already-injected faults.
- ⚠️ **Warning:** stop conditions are not optional safety theater — they are the specific mechanism that makes chaos engineering a _controlled_, bounded experiment rather than simply causing an uncontrolled outage deliberately; every FIS experiment should have a carefully considered stop condition tied to a meaningful business/application health metric, not run without this safety guardrail even in a lower-stakes testing environment, since the entire discipline of chaos engineering depends on faults being injected safely, with a defined, automatic circuit-breaker if things go worse than expected.
- 🔑 **Key takeaway:** this stop-condition mechanism directly parallels the approval-gate discipline established for automated incident response (§124 §4.3) and CI/CD deployment gates (§85-86) — a defined, automatic safety check that halts a potentially-risky automated action if a monitored signal indicates it's causing more harm than intended, applied here specifically to deliberately-injected chaos experiments.

### 4.3 The Chaos Engineering Maturity Progression

- Organizations new to chaos engineering typically progress through a deliberate maturity curve: starting with experiments in a **non-production environment** (staging, a dedicated test environment) to build confidence in both the experiment design and the target system's actual resilience, before progressing to increasingly production-representative or eventually genuine **production experiments**, always with carefully scoped blast radius (a small percentage of resources, not "everything at once") and robust stop conditions.
- 🔑 **Key takeaway:** this progression directly mirrors §85's deployment-strategy maturity (canary, gradual rollout, before full production deployment) and §127 §4.2's drill-before-real-disaster progression — controlled, incremental exposure to risk, building validated confidence at each stage before increasing scope, rather than jumping directly to the highest-risk, broadest-scope experiment first.

## 5. Lifecycle / Workflow

1. Based on Resilience Hub's assessment (§128) or general architectural understanding, a specific resilience mechanism is identified for validation — for example, "does the Auto Scaling Group correctly replace a terminated instance within our target RTO."
2. An FIS experiment template is defined: the specific action (instance termination), the precisely-scoped target (a specific tagged subset of instances), and a stop condition (a CloudWatch Alarm monitoring overall application health/error rate).
3. The experiment runs first in a non-production environment, validating both that the experiment itself is correctly configured and that the target system's actual behavior matches architectural expectations.
4. Findings from the experiment — did the Auto Scaling Group actually replace the instance within target RTO, did the stop condition correctly halt the experiment if something went wrong — feed back into either confirming the architecture genuinely works as designed, or identifying a gap requiring remediation (feeding back into §128's assess-remediate-reassess cycle).
5. As confidence builds through repeated, successful non-production experiments, the same experiment (or a scoped-down version) may progress to a production environment, following the maturity progression in §4.3, continuing to validate genuine, real-world resilience on an ongoing basis.

## 6. Configuration

| Setting                                 | Purpose                                                                                                                                                                                                                     |
| --------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Experiment template (actions + targets) | The specific fault(s) injected and precisely which resources they apply to.                                                                                                                                                 |
| Stop conditions (CloudWatch Alarms)     | The safety mechanism halting the experiment if injected faults cause worse-than-intended impact.                                                                                                                            |
| IAM execution role                      | Scopes exactly what FIS is permitted to do — a genuinely powerful capability (deliberately causing failures) warranting the same least-privilege rigor as any other automated, consequential action covered in this course. |
| Experiment scheduling                   | Whether experiments run on-demand, or on a recurring schedule as part of ongoing, continuous resilience validation.                                                                                                         |

## 7. Commands / API (Full Documentation)

### 7.1 Creating an Experiment Template

- **Purpose:** Define a specific, scoped chaos experiment with safety guardrails.
- **Syntax:**

```bash
aws fis create-experiment-template \
  --description "Validate ASG replaces terminated instance within RTO" \
  --targets '{"application-instances":{"resourceType":"aws:ec2:instance","resourceTags":{"Environment":"staging","Tier":"application"},"selectionMode":"PERCENT(50)"}}' \
  --actions '{"terminate-instances":{"actionId":"aws:ec2:terminate-instances","targets":{"Instances":"application-instances"}}}' \
  --stop-conditions '[{"source":"aws:cloudwatch:alarm","value":"arn:aws:cloudwatch:us-east-1:111122223333:alarm:application-error-rate-high"}]' \
  --role-arn arn:aws:iam::111122223333:role/FISExperimentRole
```

- **Important arguments:** `selectionMode: PERCENT(50)` scopes the blast radius to half of matching instances, not all of them — a deliberate, bounded scope rather than an all-at-once disruption. `stop-conditions` ties the experiment to a specific CloudWatch Alarm monitoring application error rate — if that alarm fires during the experiment, FIS halts immediately, directly implementing §4.2's critical safety mechanism.
- **Common errors:** omitting a meaningful stop condition (§4.2's warning), or defining a stop condition tied to a metric that wouldn't actually catch genuine, worse-than-expected impact; scoping targets too broadly for an organization's actual chaos-engineering maturity level (§4.3), running a 100%-of-production-instances experiment before validating the same experiment safely at smaller scale first.
- **Security impact:** the FIS execution role has genuinely powerful, deliberately-destructive capability (terminating instances, injecting failures) — scope it tightly to exactly the actions/resources the specific experiment program requires, following least-privilege as rigorously as anywhere else in this course, arguably more so given the deliberately consequential nature of what this role is designed to do.

## 8. Hands-On Example — Validating an Architectural Assumption

```text
Resilience Hub assessment (§128) confirmed: "payments-app" scores
well on AZ-disruption resilience, with compute spread across 3 AZs via
an Auto Scaling Group, target RTO for AZ disruption: 5 minutes.

FIS experiment designed to VALIDATE this assumption:
  Action: terminate-instances
  Target: 33% of instances (approximating one AZ's worth)
  Stop condition: CloudWatch Alarm on application error rate > 5%

Experiment runs in staging first:
  RESULT: ASG detected terminated instances and launched replacements
  within 3 minutes 40 seconds -- WITHIN the 5-minute target RTO,
  confirming the architecture genuinely performs as Resilience Hub's
  assessment suggested it should

Experiment later scoped down and run in PRODUCTION during a planned,
low-traffic maintenance window, with tight monitoring and a
conservative stop condition:
  RESULT: consistent with staging findings -- 5-minute RTO target
  genuinely validated under real production conditions, not just
  architectural analysis or a staging approximation
```

This demonstrates the complete Resilience Hub-to-FIS validation chain directly: an architectural assessment identified a resilience claim, and FIS empirically verified that claim actually holds under real, injected failure — closing exactly the "designed to be resilient" versus "verified to be resilient" gap this Part has built toward across §127-129.

## 9. Production and Enterprise Usage

- Mature organizations run chaos experiments on a recurring, scheduled basis (not just ad hoc, one-time validation) for their most critical systems, treating continuous chaos engineering as an ongoing practice analogous to the continuous DR validation this Part's final section (§4) formalizes — resilience mechanisms can silently regress as a system evolves (a new dependency added without appropriate failover handling, a configuration change inadvertently weakening redundancy), and only ongoing, repeated validation catches this drift.
- "Game days" — planned, scheduled events where a team deliberately runs chaos experiments (often FIS-orchestrated) against a system, sometimes even without full advance notice to the responding on-call team, to genuinely test both the system's resilience and the human response process together — are a common, valuable practice, directly connecting this section's tooling to the broader operational-readiness themes established in §125's SOC patterns (drills, on-call, playbooks) and this Part's own DRS drill discipline (§127 §4.2).
- Organizations commonly start their chaos engineering practice narrowly — a small number of well-understood, low-risk experiments against non-critical systems — before expanding scope and criticality as both tooling confidence and organizational chaos-engineering maturity grow, following §4.3's progression discipline in actual practice.

## 10. Security Considerations

- The FIS execution role's genuinely powerful, deliberately-disruptive capability (§7.1's security-impact note) makes its own protection a meaningful security consideration — unauthorized or accidental use of this capability could cause a genuine, unintended outage, so access to create/run FIS experiments should be restricted to specifically authorized personnel, following least-privilege as rigorously as any other consequential, automated capability covered in this course.
- Stop conditions (§4.2) are as much a security/safety control as a testing-methodology detail — they're what prevents a chaos experiment from becoming an actual, uncontrolled incident, and should be reviewed with the same rigor this course applies to any other safety-critical automated control (§124's approval gates, §119's guardrail design).

## 11. Performance Considerations

- FIS experiments are, by design, intended to have some impact on the target system (that's the entire point — validating behavior under real, injected stress) — the key performance consideration is ensuring that impact stays within the intentionally bounded, controlled scope defined by targets and stop conditions, rather than the experiment itself becoming an unintended, broader performance/availability problem.
- Running experiments during lower-traffic periods (§8's "planned, low-traffic maintenance window" example) is a common practical mitigation for production experiments specifically, minimizing the real-world impact of the intentional, bounded disruption even as it validates genuine production behavior.

## 12. Monitoring

- Experiment execution should be closely monitored in real time via the same CloudWatch dashboards/alarms used for the stop conditions themselves (§4.2) — an experiment isn't a "set it and walk away" operation, particularly for early-maturity or production experiments, but an actively observed, controlled test.
- Experiment outcomes (did the system behave as expected, did any stop condition trigger, what was the actual measured recovery time) should be documented and tracked over time, feeding back into Resilience Hub's assessment cycle (§128 §5) and the organization's broader resilience-posture metrics, mirroring the "track whether it's actually working" discipline established throughout this course.

## 13. Troubleshooting

| Symptom                                                          | Cause                                                                                                                                                       | Fix                                                                                                                                                                           |
| ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Experiment's stop condition triggers immediately/unexpectedly    | Alarm threshold too sensitive relative to the experiment's actual intended impact, or the injected fault is causing genuinely worse impact than anticipated | Review whether the stop condition threshold is appropriately calibrated, or whether the underlying resilience mechanism genuinely has a gap the experiment correctly surfaced |
| System doesn't recover within expected time during an experiment | A genuine resilience gap — the architecture doesn't actually perform as Resilience Hub's assessment (or general design assumption) suggested                | Treat this as a valid, valuable finding — investigate root cause and remediate, following §128's assess-remediate-reassess cycle                                              |
| Experiment execution fails to start                              | IAM permission gap on the FIS execution role, or a misconfigured target/action specification                                                                | Review and correct the execution role's permissions and experiment template configuration                                                                                     |

## 14. Best Practices

- Always define a meaningful, well-calibrated stop condition tied to a genuine application health signal — never run an experiment without this safety mechanism.
- Follow the maturity progression (§4.3) — validate in non-production first, start with small, well-scoped blast radius, and expand scope/criticality only as confidence builds.
- Run chaos experiments on a recurring, scheduled basis for critical systems, not only as a one-time validation exercise.
- Treat experiment findings — whether confirming resilience or revealing a gap — as genuinely valuable, feeding directly back into Resilience Hub's assessment cycle.
- Document and track experiment outcomes over time as part of the organization's broader resilience-posture metrics.

## 15. Anti-Patterns and Common Mistakes

- ❌ Running a chaos experiment without a meaningful, well-calibrated stop condition, turning a controlled experiment into an uncontrolled risk.
- ❌ Jumping directly to broad-scope, production chaos experiments before validating the same experiment safely at smaller scale in non-production first.
- ❌ Treating architectural resilience assessment (Resilience Hub, §128) as sufficient on its own, without empirical validation via actual fault injection.
- ❌ Running chaos experiments once as a one-time exercise, rather than as an ongoing, recurring practice that catches resilience regression as systems evolve.
- ❌ Granting broad FIS execution permissions without appropriately restricting who can create/run experiments, given the genuinely consequential, deliberately-disruptive capability involved.

## 16. Interview Questions with Model Answers

**🎯 Junior:** _"What is chaos engineering, and what does AWS Fault Injection Service do?"_
**Model answer:** Chaos engineering is the practice of deliberately, safely injecting real faults into a system to verify it actually behaves resiliently under real failure conditions, rather than just assuming it does based on architectural design. AWS Fault Injection Service, or FIS, is AWS's managed tooling for this — it lets you define controlled experiments that inject specific faults, like terminating an instance or adding network latency, to a precisely-scoped set of target resources, with safety mechanisms called stop conditions that automatically halt the experiment if something goes worse than expected.

**🎯 Intermediate:** _"Why is a stop condition considered a critical, non-optional part of every FIS experiment, rather than just a nice-to-have safety feature?"_
**Model answer:** A stop condition is what actually makes chaos engineering a _controlled_ experiment rather than just deliberately causing an outage and hoping for the best. It's a CloudWatch Alarm that FIS continuously monitors during the experiment — if the alarm indicates the injected fault is causing worse impact than the experiment intended to safely validate, FIS automatically halts further fault injection immediately. Without this, an experiment that reveals a genuine, unexpected resilience gap could turn into a real, uncontrolled production incident instead of a safely-contained, valuable finding — the entire premise of chaos engineering as a safe discipline depends on this automatic circuit-breaker being in place.

**🎯 Senior:** _"Your organization has a Resilience Hub assessment showing a high score for a critical application, but has never run any FIS experiments against it. How would you evaluate whether that score can actually be trusted, and how would you begin introducing chaos experiments safely?"_
**Model answer:** A high Resilience Hub score confirms the _architecture_ is designed with appropriate redundancy, but without any empirical validation, I wouldn't treat that as proof the redundancy actually works correctly in practice — there could be a subtle misconfiguration or an untested failover path that architectural analysis alone wouldn't catch. I'd begin by identifying the specific resilience claims the Resilience Hub assessment is making (for example, "Auto Scaling replaces a failed instance within 5 minutes") and design a small number of narrowly-scoped FIS experiments specifically to validate those exact claims, starting in a staging or non-production environment first, following the maturity progression rather than jumping straight to production. Each experiment would have a carefully calibrated stop condition tied to genuine application health metrics. Only after these non-production experiments consistently confirm the architecture behaves as expected — and any gaps discovered are remediated and re-validated — would I consider progressing the same, still carefully-scoped experiments into production, giving genuine, empirically-verified confidence in the original high score rather than continuing to rely on architectural analysis alone.

**🎯 Architect:** _"Design a chaos engineering program for a large enterprise's most critical systems, integrating with the resilience assessment and DR capabilities covered elsewhere in this Part, and addressing both technical validation and organizational/human readiness."_
**Model answer:** Structure the program around the maturity progression (§4.3), starting with a small number of well-understood, high-value experiments against the organization's Mission-Critical tier applications (per §128's tiered Resiliency Policy model), each experiment directly designed to validate a specific claim from that application's Resilience Hub assessment — closing the architectural-analysis-to-empirical-validation gap systematically, application by application, rather than an unfocused, broad chaos-engineering initiative with no clear connection to what's actually being validated. Establish a recurring cadence (mirroring §127's DRS drill cadence and §119's periodic review discipline) — not one-time validation, but ongoing, scheduled experiments that catch resilience regression as these critical systems continue to evolve. For organizational/human readiness specifically, introduce periodic "game days" (§9) — scheduled events combining FIS-orchestrated technical fault injection with genuine on-call/incident-response process testing (directly connecting to §125's SOC on-call and escalation practices), validating not just "does the system recover" but "does our team correctly detect, escalate, and respond" — since a technically resilient system operated by a team unprepared to recognize and respond to a real disruption still represents a genuine organizational readiness gap that pure architectural or even automated technical validation alone wouldn't catch. Track experiment outcomes, Resiliency Score trends (§128), and DRS drill results (§127) together as one integrated resilience-posture reporting package to leadership, giving a genuinely complete picture — architectural design, empirical technical validation, and human/organizational readiness — rather than any single dimension in isolation, directly synthesizing every capability this Part has covered into one coherent, ongoing program.

## 17. Common Misconceptions

- "Chaos engineering means causing random, uncontrolled failures to see what happens." False — as this entire section establishes, genuine chaos engineering (and specifically FIS) is precisely scoped (targets), safety-gated (stop conditions), and follows a deliberate maturity progression — the opposite of random or uncontrolled.
- "A passing chaos experiment result means the system is now fully validated forever." False — as §9 and the Architect answer establish, resilience mechanisms can regress as systems evolve; chaos engineering is an ongoing, recurring practice, not a one-time certification.
- "Chaos engineering is only for AWS-experts-level, very large organizations." Understated as a barrier — starting small, in non-production, with a narrow, well-understood experiment scope (§4.3) is accessible to organizations of varying maturity levels; the discipline scales with organizational readiness, not requiring maximum sophistication from day one.

## 18. Key Takeaways

🔑 FIS enables controlled chaos engineering experiments — deliberately injecting real faults into precisely-scoped targets — to empirically validate resilience mechanisms, closing the gap Resilience Hub's architectural analysis alone leaves open.
🔑 Stop conditions (CloudWatch Alarms monitored throughout an experiment) are the critical safety mechanism distinguishing controlled chaos engineering from deliberately causing an uncontrolled outage — never optional.
🔑 A deliberate maturity progression — non-production first, narrow scope, expanding as confidence builds — mirrors the same incremental-risk-exposure discipline established for deployment strategies (§85) and DR drills (§127) throughout this course.
🔑 Chaos engineering should be an ongoing, recurring practice (not one-time validation), since resilience mechanisms can silently regress as systems evolve.
🔑 "Game days" combining technical fault injection with genuine human/process response testing address organizational readiness alongside pure technical validation — a system's resilience depends on both.

## 19. Related Concepts

- **AWS Resilience Hub** (§128) — the architectural assessment FIS experiments are commonly designed to empirically validate.
- **AWS Elastic Disaster Recovery drills** (§127 §4.2) — a directly analogous controlled-testing discipline, applied to server-level disaster recovery specifically.
- **CloudWatch Alarms** (§71) — the underlying mechanism implementing FIS's critical stop-condition safety control.
- **Security Operations Center Patterns** (§125) — the on-call/escalation/readiness themes directly connected to "game day" organizational testing.
- **Continuous DR Validation & Game Days** (§130, next section) — synthesizes this Part's entire resilience-validation narrative (DRS, Resilience Hub, FIS) into one ongoing operational practice.
