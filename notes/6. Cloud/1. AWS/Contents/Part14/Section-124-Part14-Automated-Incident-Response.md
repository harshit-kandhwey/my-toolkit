# Part 14, Section 4: Automated Incident Response — EventBridge, Lambda, SSM Runbooks

## 1. Definition

**Plain language:** §121-123 covered discovering sensitive data (Macie), investigating suspicious activity (Detective), and centralizing security telemetry (Security Lake) — but discovery and investigation alone don't fix anything. This section is about closing the loop: automatically responding to security findings, from immediate, well-understood containment actions all the way through a structured, repeatable incident-response process.

**Precise definition:** Automated incident response on AWS is the practice of using **Amazon EventBridge** to route security findings (from GuardDuty, Macie, Security Hub, and other sources) to automated response mechanisms — commonly **AWS Lambda** functions for custom logic, and **AWS Systems Manager Automation runbooks** for structured, repeatable, multi-step remediation procedures — enabling immediate, consistent containment and remediation actions without requiring a human to manually execute every response step, while preserving human decision-making for genuinely judgment-requiring actions.

## 2. Why It Exists / Problem It Solves

- A security finding — from GuardDuty, Macie, or any other detection source covered in this Part — has real value only if something happens in response to it; §119 §4.2 already established this principle for compliance guardrail findings specifically ("a finding provides no value if it simply accumulates unreviewed"), and it applies with even greater urgency to active security incidents, where response speed genuinely matters.
- Manual response — a human seeing a finding, deciding what to do, and executing each remediation step by hand — is both slow (introducing a real window between detection and containment during which an active compromise can continue or spread) and inconsistent (different responders might handle the same finding type differently, or a tired/distracted responder might make an error under pressure).
- Automation directly addresses both problems for well-understood finding types: an EventBridge rule matching a specific finding pattern can trigger an immediate, consistent response — isolating a compromised instance, revoking a compromised credential's active sessions, or restricting an unexpectedly-public S3 bucket — within seconds of detection, far faster than any manual process could achieve, and identically every time regardless of who (or what, since it's automated) is "on call" at that moment.
- 🔑 **Key takeaway:** this section applies the exact same "automate the well-understood, keep humans in the loop for genuine judgment" principle established for Config Rule automatic remediation (§119 §4.2) and SageMaker Pipeline evaluation gates (§109 §4.5), here applied specifically to active security incident response — automation handles fast, unambiguous initial containment; human judgment remains essential for anything requiring genuine investigation or carrying meaningful risk of unintended impact.

## 3. Prerequisites and Dependencies

- **Amazon EventBridge** (§62): the routing mechanism connecting security findings to response actions — this section assumes fluency with EventBridge's event-pattern-matching and rule-based routing model.
- **AWS Lambda** (§25): the common mechanism for custom, code-based response logic.
- **AWS Systems Manager** (§75): Automation runbooks, covered in depth here, build on the Systems Manager foundation introduced in Part 8.
- **GuardDuty, Security Hub, Macie** (§16, §121): the common finding sources triggering automated response.

## 4. Internal Working / Architecture & Components

### 4.1 The Detection-to-Response Pipeline

```
Finding generated (GuardDuty / Macie / Security Hub / Config)
        |
        v
EventBridge rule matches the finding's event pattern
   (e.g., specific finding TYPE, specific SEVERITY threshold)
        |
        v
Target invoked:
   - Lambda function (custom logic, e.g., "tag and isolate this
     instance, notify the security team via SNS")
   - Systems Manager Automation runbook (structured, multi-step,
     often requiring approval for higher-risk steps)
        |
        v
Response executed -- immediate containment and/or notification,
with human investigation (Detective, §122) proceeding in
parallel or subsequently
```

- This is a direct, security-specific application of the EventBridge-driven, event-pattern-matched automation model established generally in §62, and specifically echoes §67 §5a's EventBridge Pipes pattern (a defined source triggering a defined, possibly-transformed action) — here, the source is a security finding, and the action is a containment/remediation response.

### 4.2 Lambda for Custom Response Logic

- A Lambda function triggered by an EventBridge rule can implement essentially any custom containment logic — common patterns include: isolating a suspected-compromised EC2 instance (modifying its security group to remove all inbound/outbound access except to a forensics subnet, following the network-isolation principles established in Part 4), revoking active IAM credentials/sessions for a principal implicated in a finding, or automatically applying a stricter S3 bucket policy in response to a Macie or GuardDuty finding indicating unexpected public exposure.
- ⚠️ **Warning:** Lambda-based automated response functions are themselves a genuinely powerful, potentially broad-reaching capability — following the exact same principle established for Bedrock Agent side-effectful actions (§112 §4.2), any automated response action with real, consequential impact (isolating a production instance, revoking credentials) should be carefully scoped, tested, and — for higher-risk actions specifically — potentially gated behind a confirmation step rather than executing fully unilaterally for every possible triggering finding.

### 4.3 Systems Manager Automation Runbooks

- A **Systems Manager Automation runbook** (§75's Systems Manager foundation, extended here) defines a structured, multi-step remediation procedure — a genuinely more formalized, auditable mechanism than an arbitrary Lambda function for well-defined, repeatable incident-response procedures, since a runbook's steps, parameters, and execution history are all natively tracked by Systems Manager.
- Runbooks support **approval steps** within an otherwise-automated sequence — meaning a runbook can automate the bulk of a response procedure (gathering forensic data, tagging affected resources, notifying stakeholders) while pausing at a specific, higher-risk step (actually terminating or modifying a production resource) for explicit human approval before proceeding — directly implementing §4.2's warning as a structural, built-in runbook capability rather than something a custom Lambda function would need to implement itself.
- 🔑 **Key takeaway:** runbooks versus custom Lambda functions represents roughly the same "structured, purpose-built tool versus general-purpose custom code" trade-off seen elsewhere in this course (e.g., Config's managed rules versus custom Lambda-backed Config rules, or built-in SageMaker algorithms versus custom training code, §108 §4.2) — runbooks are well-suited to well-defined, repeatable, auditable incident-response procedures; custom Lambda functions offer more flexibility for response logic that doesn't map cleanly to a runbook's structure.

### 4.4 Automated Response Tiers

| Tier                                   | Example                                                                                                                       | Human Involvement                                                                   |
| -------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| **Fully automated, immediate**         | Auto-remediate a publicly-exposed S3 bucket flagged by Macie/GuardDuty (restrict access immediately)                          | None required for execution; notification sent for awareness                        |
| **Automated with approval gate**       | Isolate a suspected-compromised production instance via a runbook that pauses for approval before the isolation step executes | Explicit approval required before the higher-risk action proceeds                   |
| **Notification only, manual response** | A finding requiring genuine investigative judgment (ambiguous, low-confidence, or affecting a highly sensitive resource)      | Full manual investigation (Detective, §122) and response, no automated action taken |

- 🔑 **Key takeaway:** this tiered model directly mirrors the automatic-remediation-versus-manual-triage distinction established in §119 §4.2 — the tier a given finding type falls into should be a deliberate design decision based on the finding's confidence level and the response action's potential impact, not a uniform default applied to every finding regardless of these factors.

## 5. Lifecycle / Workflow

1. A security finding is generated (GuardDuty, Macie, Security Hub, or Security Lake-correlated data, §121-123).
2. An EventBridge rule, matching the finding's specific type/severity pattern, routes it to the appropriate response tier (§4.4) — a Lambda function for fully-automated or lightly-gated response, or a Systems Manager Automation runbook for more structured, multi-step, potentially approval-gated procedures.
3. Immediate, well-understood containment actions execute automatically (or after approval, for gated tiers), reducing the window of exposure for a genuine active incident.
4. Security personnel are notified (commonly via SNS, §61) of the finding and any automated action already taken, and — for findings requiring deeper investigation — proceed to manual investigation via Detective (§122) and Security Lake-based querying (§123) in parallel with or following any immediate automated containment.
5. Once the incident is fully understood and resolved, the response is documented, and — following the same continuous-improvement principle established in Part 8's incident-response material and §119's guardrail-baseline reassessment — the automated response configuration itself is reviewed: was the automated tier assignment appropriate, did the response work as intended, and should any new finding pattern be added to automated response based on what was learned.

## 6. Configuration

| Setting                                        | Purpose                                                                                                                                                                                               |
| ---------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| EventBridge rule event patterns                | Which specific finding types/severities trigger which response target.                                                                                                                                |
| Lambda function IAM execution role             | The actual permission boundary for what a response function can do — scoped tightly following least-privilege, given the function's powerful, potentially broad-reaching capability (§4.2's warning). |
| Systems Manager Automation runbook definitions | The structured, multi-step response procedures, including approval-gate placement for higher-risk steps.                                                                                              |
| Notification configuration (SNS topics)        | Ensuring security personnel are informed of both findings and any automated actions taken.                                                                                                            |

## 7. Commands / API (Full Documentation)

### 7.1 Creating an EventBridge Rule for GuardDuty Findings

- **Purpose:** Route high-severity GuardDuty findings to an automated response Lambda function.
- **Syntax:**

```bash
aws events put-rule \
  --name high-severity-guardduty-response \
  --event-pattern '{"source":["aws.guardduty"],"detail-type":["GuardDuty Finding"],"detail":{"severity":[{"numeric":[">=", 7]}]}}'

aws events put-targets \
  --rule high-severity-guardduty-response \
  --targets '[{"Id":"1","Arn":"arn:aws:lambda:us-east-1:111122223333:function:isolate-compromised-instance"}]'
```

- **Important arguments:** the `event-pattern`'s severity filter (`>=7`, GuardDuty's high-severity threshold) ensures only genuinely high-confidence, high-severity findings trigger this specific automated response — directly implementing §4.4's tiered model, where lower-severity or lower-confidence findings would route to a different rule/target (or no automated action, only notification).
- **Common errors:** an overly broad event pattern triggering automated response for findings that don't actually warrant it, risking unintended disruption from an automated action applied too liberally; an overly narrow pattern missing genuine incidents that should have triggered automated response.

### 7.2 A Systems Manager Automation Runbook with an Approval Step

```json
{
  "schemaVersion": "0.3",
  "mainSteps": [
    {
      "name": "TagAffectedInstance",
      "action": "aws:createTags",
      "inputs": {
        "ResourceIds": ["{{InstanceId}}"],
        "Tags": [{ "Key": "IncidentStatus", "Value": "UnderInvestigation" }]
      }
    },
    {
      "name": "GatherForensicSnapshot",
      "action": "aws:executeAwsApi",
      "inputs": {
        "Service": "ec2",
        "Api": "CreateSnapshot",
        "VolumeId": "{{VolumeId}}"
      }
    },
    {
      "name": "ApprovalGate",
      "action": "aws:approve",
      "inputs": { "Approvers": ["security-team-lead"] }
    },
    {
      "name": "IsolateInstance",
      "action": "aws:executeAwsApi",
      "inputs": {
        "Service": "ec2",
        "Api": "ModifyInstanceAttribute",
        "InstanceId": "{{InstanceId}}",
        "Groups": ["{{IsolationSecurityGroupId}}"]
      }
    }
  ]
}
```

- **Production usage:** this runbook automates the low-risk, purely investigative early steps (tagging, forensic snapshot capture) without requiring approval, since these actions carry minimal risk of unintended impact, but explicitly pauses at an `ApprovalGate` step before the higher-risk `IsolateInstance` action — directly implementing §4.3's approval-gate capability, ensuring a human confirms the isolation is warranted before a potentially production-impacting action actually executes.

## 8. Hands-On Example — Full Response Flow

```text
1. GuardDuty finding: severity 8.5, "EC2 instance i-0abc123 is
   communicating with a known command-and-control IP address"

2. EventBridge rule matches (severity >= 7) --> triggers Systems
   Manager Automation runbook (§7.2)

3. Runbook executes automatically:
   - Tags instance "IncidentStatus: UnderInvestigation"
   - Captures a forensic EBS snapshot (§43's snapshot mechanism)
     BEFORE any further action, preserving evidence
   - PAUSES at approval gate, notifying security-team-lead via SNS

4. Security team lead reviews the finding and Detective's behavior
   graph (§122) for this instance within minutes, confirms
   this is a genuine compromise, and approves the next step

5. Runbook proceeds: modifies the instance's security group to the
   isolation group (no inbound/outbound except to a forensics subnet)

6. Total time from detection to containment: under 10 minutes,
   with a forensic snapshot preserved BEFORE isolation, and a human
   explicitly confirming the higher-risk isolation step rather than
   it executing fully unattended
```

This demonstrates the full tiered-automation model (§4.4) in practice: fast, automatic, low-risk initial steps; a deliberate approval gate before higher-risk action; and forensic evidence preservation built into the automated sequence itself, rather than being an afterthought a rushed manual response might have skipped under pressure.

## 9. Production and Enterprise Usage

- Mature security operations teams commonly maintain a library of Systems Manager Automation runbooks covering their most common, well-understood incident types — compromised credentials, compromised instances, unexpected public exposure — treating runbook development itself as an ongoing investment, similar to how a mature CI/CD practice maintains reusable pipeline templates (§86 §10).
- The tiered automation model (§4.4) is commonly calibrated based on actual operational experience over time — a finding type initially routed to manual-only response might graduate to automated-with-approval-gate, and eventually to fully automated, as the team gains confidence in the response pattern's reliability and low false-positive rate, mirroring the same "start conservative, calibrate as track record builds" discipline touched on for guardrail rollout (§119 §4.1).
- Automated forensic evidence preservation (§8's snapshot step) before any potentially-disruptive containment action is a widely recognized best practice, since containment actions (isolating, terminating) can otherwise destroy volatile evidence a subsequent investigation would need.

## 10. Security Considerations

- Response Lambda functions and Automation runbooks are themselves high-value, powerful automation and warrant the same least-privilege IAM scoping rigor as any other automated, side-effectful capability covered throughout this course (§112 §4.2's Agent-action principle, §119 §4.2's automatic-remediation principle) — a compromised or misconfigured response function could itself become an attack vector if overly broadly permissioned.
- Approval gates (§4.3, §7.2) for higher-risk response actions are a genuine security control, not merely a process formality — they prevent a false-positive or overly-aggressive automated rule from causing unintended, consequential impact (isolating or terminating a legitimate, non-compromised production resource) without any human check.
- Forensic evidence preservation (snapshot capture, log retention) before a containment action executes is itself a security/compliance consideration — many incident-response and regulatory frameworks expect evidence to be preserved, not just the threat to be contained.

## 11. Performance Considerations

- The primary "performance" metric for this section is response latency — how quickly a genuine finding results in actual containment action — where automation's fundamental value proposition is dramatically reducing this compared to a fully manual process, directly reducing an active incident's window of opportunity.
- Approval gates (§4.3) intentionally trade some of that speed advantage for genuine human judgment on higher-risk steps — a deliberate, calibrated trade-off (§4.4), not an oversight; the goal is minimizing response latency specifically for the well-understood, lower-risk portions of a response while preserving appropriate human oversight for the higher-stakes portions.

## 12. Monitoring

- Automated response execution (which rules fired, which runbooks/functions executed, with what outcome) should itself be logged and monitored — CloudTrail (§73) captures the underlying API activity, and Systems Manager provides its own runbook execution history — ensuring the automation itself is auditable, not a black box.
- False-positive rate for automated response actions (how often an automated action fires on a finding that, upon investigation, wasn't actually a genuine incident) is a critical metric to track — a high false-positive rate for a fully-automated (no approval gate) response tier is a strong signal that finding type should be moved to a more conservative tier (approval-gated, or manual-only) per §9's calibration discipline.

## 13. Troubleshooting

| Symptom                                                                  | Cause                                                                                                                                     | Fix                                                                                                                     |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Automated response didn't trigger for an apparent genuine incident       | EventBridge rule's event pattern didn't match the specific finding's actual attributes                                                    | Review and correct the event pattern; verify against the actual finding's structure                                     |
| Automated response caused unintended disruption to a legitimate resource | Response tier assignment (§4.4) was too aggressive for that finding type's actual false-positive rate, or response logic itself had a bug | Move the finding type to a more conservative tier (approval-gated or manual); review and test response logic thoroughly |
| Runbook execution stuck at an approval gate with no response             | Notification to the designated approver failed, or approver wasn't actually available/monitoring                                          | Verify SNS notification configuration; ensure appropriate on-call coverage for approval-gated response steps            |

## 14. Best Practices

- Calibrate automated response tiers (§4.4) deliberately based on each finding type's confidence level and the response action's potential impact, starting conservative and graduating to more automation as operational track record builds.
- Preserve forensic evidence (snapshots, logs) as an automated early step before any potentially-disruptive containment action executes.
- Use approval gates for genuinely higher-risk response actions, rather than either fully automating everything or requiring manual approval for everything uniformly.
- Maintain and periodically review a library of well-tested Systems Manager Automation runbooks for common, well-understood incident types.
- Monitor automated response false-positive rates and adjust tier assignments accordingly.

## 15. Anti-Patterns and Common Mistakes

- ❌ Fully automating high-impact response actions (terminating production resources, revoking broad access) without any approval gate, risking significant unintended disruption from a false positive.
- ❌ Requiring manual approval for every single finding regardless of confidence/severity, undermining automation's core speed advantage for genuinely well-understood, low-risk cases.
- ❌ Executing containment actions (isolation, termination) without first preserving forensic evidence, potentially destroying information a subsequent investigation needs.
- ❌ Never reviewing or calibrating automated response tier assignments based on actual operational experience, leaving an initially-conservative (or initially-too-aggressive) configuration static indefinitely.
- ❌ Granting response Lambda functions or runbooks broader IAM permissions than their specific response actions actually require.

## 16. Interview Questions with Model Answers

**🎯 Junior:** _"Why automate security incident response instead of always having a human review every finding first?"_
**Model answer:** Speed matters a lot during an active security incident — the longer it takes to contain a genuine compromise, the more damage it can potentially cause. A human manually reviewing and responding to every single finding introduces delay, and for well-understood, high-confidence finding types, that delay isn't buying much extra safety — the right response is usually clear. Automation lets those well-understood cases get contained immediately, in seconds rather than however long it takes a human to notice, review, and act, while still preserving human judgment for findings that are more ambiguous or where the response action carries higher risk.

**🎯 Intermediate:** _"Why would you put an approval gate in an incident-response runbook rather than fully automating the entire response, given that speed matters so much?"_
**Model answer:** Speed matters, but so does avoiding unintended damage from a false positive — an automated response that's wrong (isolating or terminating a legitimate, non-compromised production resource) can itself cause a real incident. An approval gate lets you automate the parts of the response that are low-risk and clearly beneficial regardless of whether the finding turns out to be a true or false positive — like tagging the resource and capturing a forensic snapshot — while pausing before the higher-risk, harder-to-reverse action, like actually isolating a production instance, until a human confirms it's genuinely warranted. It's a deliberate balance: you still get most of the speed benefit from automating the safe parts immediately, while keeping a human check specifically where a mistake would be most costly.

**🎯 Senior:** _"Your team's automated response for 'publicly exposed S3 bucket' findings has a 30% false-positive rate — a third of the time, the bucket was actually intentionally public (like static website hosting) and the automated remediation broke something. How would you address this?"_
**Model answer:** A 30% false-positive rate on a fully-automated response is too high — I'd first move this finding type from fully-automated to an approval-gated tier (§4.4), immediately stopping the unintended disruption while I investigate further, since continuing to auto-remediate at this false-positive rate is actively causing more harm than the genuine incidents it's preventing. Then I'd investigate why the false-positive rate is so high — likely the detection logic (the GuardDuty/Macie finding, or the EventBridge rule's pattern matching) isn't distinguishing between "unexpectedly public" and "intentionally, legitimately public" buckets, perhaps missing a check for a tag or naming convention the organization uses to mark intentional public-hosting buckets. I'd refine the detection/routing logic to incorporate that distinction — for example, excluding buckets tagged as intentionally public from this automated response path entirely — and only after validating the refined logic against historical findings (confirming it correctly distinguishes genuine issues from the known legitimate cases) would I consider returning this finding type to a fully-automated tier, now with a meaningfully lower expected false-positive rate.

**🎯 Architect:** _"Design the automated incident response program for a large enterprise handling several hundred security findings per day across 200+ accounts, where the current fully-manual process means most findings go uninvestigated due to sheer volume."_
**Model answer:** Start by using Security Lake (§123) and Security Hub to get a unified, correlated view of the actual finding volume and patterns — several hundred findings per day is unlikely to be several hundred genuinely distinct incidents; Detective's finding-group correlation (§122 §4.2) likely reveals that many are related or represent a smaller number of underlying patterns, directly informing where automation investment should be prioritized first. Build the tiered automation model (§4.4) starting with the highest-volume, most well-understood, lowest-risk finding types — likely things like publicly-exposed resources or unencrypted storage, following patterns already well-established in this course (§119's automatic remediation for well-understood Config findings) — moving these to fully-automated or lightly-gated response first, since they likely represent a large share of total volume with the least ambiguity about the correct response. For findings requiring genuine investigation, build Systems Manager Automation runbooks that automate the _investigative groundwork_ (gathering Detective behavior-graph context, pulling relevant Security Lake-correlated data, tagging and categorizing) even where the actual response decision still requires human judgment — this doesn't eliminate the need for human review, but it dramatically reduces the time each human-reviewed finding takes, since the analyst starts with pre-gathered context rather than beginning their investigation from scratch, directly addressing the volume problem even for findings that can't be safely fully automated. Track false-positive rates and analyst time-per-finding as explicit program metrics (mirroring §119's Architect answer's program-health-metric discipline), using them to continuously identify which additional finding types are ready to graduate to higher automation tiers as the program matures — treating this as an ongoing, data-driven calibration process rather than a one-time buildout, directly addressing the stated volume problem sustainably rather than through a single initial automation push that then goes stale as finding patterns evolve.

## 17. Common Misconceptions

- "Fully automated response is always better than a manual process, since it's faster." False — as the Senior interview answer demonstrates, an inappropriately-calibrated fully-automated response can cause real unintended harm; the right automation tier depends on the finding type's confidence level and the response action's risk, not a blanket preference for maximum automation.
- "An approval gate defeats the purpose of automation." False — as the Intermediate answer establishes, approval gates let the low-risk portions of a response still be automated immediately, while reserving human judgment specifically for the higher-risk decision point, capturing most of automation's speed benefit without its full risk.
- "Automated incident response replaces the need for tools like Detective and manual investigation." False — automation handles fast, well-understood initial containment; genuine investigation of ambiguous or complex findings (§122) remains essential and complementary, not replaced.

## 18. Key Takeaways

🔑 Automated incident response, via EventBridge routing to Lambda functions or Systems Manager Automation runbooks, dramatically reduces response latency for well-understood, high-confidence findings compared to a fully manual process.
🔑 A tiered automation model — fully automated, approval-gated, or manual-only — should be deliberately calibrated per finding type based on confidence level and response-action risk, not applied uniformly.
🔑 Approval gates within runbooks preserve human judgment specifically for higher-risk response steps while still automating the safe, low-risk portions of a response immediately.
🔑 Forensic evidence preservation (snapshots, tagging) should be an automated, built-in early step before any potentially-disruptive containment action executes.
🔑 Automated response tier calibration is an ongoing, data-driven process — tracking false-positive rates and adjusting tier assignments as operational track record builds, not a one-time configuration.

## 19. Related Concepts

- **Amazon EventBridge** (§62) — the routing mechanism connecting findings to automated response.
- **AWS Systems Manager** (§75) — the foundation for Automation runbooks covered in depth here.
- **Config Rule Automatic Remediation** (§119 §4.2) — the directly analogous automation-tiering principle, applied here to active security incidents specifically.
- **Amazon Detective** (§122) — the investigative tool commonly used alongside or following automated initial containment.
- **Security Operations Center (SOC) Patterns on AWS** (§125, next section) — the broader operational structure and practices this section's automated response capability operates within.
