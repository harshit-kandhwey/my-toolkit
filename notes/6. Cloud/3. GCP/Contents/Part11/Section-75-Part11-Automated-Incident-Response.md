# Section 75 (Part 11): Automated Incident Response on GCP

## 75.1 Definition

**Plain language:** Detecting a threat (Sections 72–74) is only half the problem — someone still has to actually do something about it, like isolating a compromised VM or shutting off a leaked credential. If that response depends entirely on a human being awake, available, and fast enough to act within minutes, real damage happens in the gap. Automated incident response means writing code that reacts to a detection automatically, the moment it fires, taking a specific, predefined containment action without waiting for a person to click a button.

**Precise:** Automated incident response on GCP is the practice of triggering **Cloud Functions** or **Cloud Workflows** (Section 53) from Security Command Center (Section 39) findings or Chronicle detections (Sections 72–73), typically via **Eventarc** or Chronicle's SOAR playbook layer, to execute predefined remediation actions — quarantining a compromised Compute Engine instance, revoking exposed credentials, or disabling a compromised service account — without requiring manual analyst intervention for well-understood, high-confidence incident patterns.

## 75.2 Why It Exists / Problem It Solves

Chronicle's detection engineering (Section 73) and Security Command Center (Section 39) can identify a compromise with high confidence in seconds. The problem automated response solves is the gap between "we know something bad happened" and "the bad thing has been contained" — a gap that, left to manual process, is bounded by human response time, not detection time.

Two specific pressures make this gap costly enough to justify automation:

1. **Attacker dwell time compounds damage.** A compromised service account with valid credentials can exfiltrate data or pivot to further resources every minute it remains active. The difference between an analyst responding in 2 minutes versus 20 minutes during off-hours can be the difference between a contained incident and a significant breach.
2. **Well-understood incident patterns don't need human judgment for the first response.** Not every remediation decision requires nuanced human judgment — "this specific service account key was flagged as publicly exposed in a GitHub scan" has one correct immediate first action (revoke the key) regardless of who is on call. Automating exactly this class of high-confidence, low-ambiguity response frees human analysts to focus judgment on genuinely ambiguous cases, rather than spending scarce analyst time on mechanical first-response steps.

Automation here is deliberately scoped to _containment_, not full incident resolution — the automated action buys time and limits blast radius; root-cause investigation and recovery remain human-led (SOC Patterns, Section 76).

## 75.3 Core Concepts

### 75.3.1 The Trigger-Decide-Act Pattern

Every automated response pipeline on GCP follows the same three-stage structure:

1. **Trigger** — a Security Command Center finding or Chronicle detection fires and is published as an event, most commonly via **Eventarc** (Section 53), GCP's unified eventing service that routes events from a wide range of sources (including SCC findings) to a target like Cloud Functions or Cloud Workflows.
2. **Decide** — the receiving function or workflow evaluates whether the finding meets criteria for automated action: is confidence/severity high enough, is the affected resource in scope for automation (e.g., excluding certain production-critical resources from fully automatic action), and has this exact finding already been acted on (avoiding duplicate remediation).
3. **Act** — the remediation action itself executes via GCP APIs: stopping/isolating a VM, revoking IAM bindings, disabling a service account key.

### 75.3.2 Eventarc as the Trigger Layer

**Definition:** Eventarc (introduced in Section 53) is GCP's managed eventing service, routing events from sources — including Cloud Audit Logs, Pub/Sub, and directly-supported providers — to destinations like Cloud Functions, Cloud Run, or Workflows, without the destination needing to poll for new findings.

- SCC findings can be routed to Eventarc either via a Pub/Sub notification configuration on Security Command Center (SCC publishes findings to a specified Pub/Sub topic, which Eventarc or a direct Pub/Sub-triggered function subscribes to) or via Chronicle's own SOAR layer invoking a webhook/Cloud Function directly.
- Using Eventarc/Pub/Sub as the trigger layer rather than having a function poll SCC or Chronicle on a schedule matters for response latency — a polling-based design introduces a delay bounded by the poll interval, while an event-driven design reacts within seconds of the finding being published.

### 75.3.3 Example Remediation: Quarantining a Compromised VM

A common automated response pattern for a VM flagged with high-confidence malware or command-and-control activity:

1. Receive the SCC finding/Chronicle detection identifying the compromised instance.
2. Snapshot the instance's disk(s) first, preserving forensic evidence before any state-altering action — a step frequently skipped in naive automation designs, and one that matters because the next steps intentionally alter or remove network reachability.
3. Apply a **quarantine VPC firewall tag** or move the instance's network interface to an isolated quarantine subnet with no route to the rest of the VPC, cutting off further lateral movement or exfiltration while keeping the instance running (rather than stopping it outright) so live forensic analysis remains possible if needed.
4. Notify the SOC channel (Section 76) with the finding, the action taken, and a link to the snapshot — automation contains the incident, but a human is still informed and can take over investigation.

### 75.3.4 Example Remediation: Revoking Leaked Credentials

For a finding indicating an exposed service account key (e.g., detected in a public code repository scan feeding into SCC):

1. Identify the exact key ID associated with the finding (not just the service account — a service account may have multiple keys, and disabling the wrong one causes unnecessary disruption).
2. Call the IAM API to delete or disable that specific key.
3. If the finding indicates broader compromise beyond just the key (e.g., correlated Chronicle detections of anomalous activity from that service account, per Section 73.3.3's entity risk scoring), escalate to disabling the service account entirely rather than only the single key, since a sophisticated attacker with account-level access may have provisioned additional keys.
4. Log the action and notify the SOC channel, including which specific key/account was affected, for audit trail purposes required in most compliance frameworks.

### 75.3.5 Cloud Workflows vs. Cloud Functions for Response Logic

| Aspect                   | Cloud Functions                                                                          | Cloud Workflows                                                                                                        |
| ------------------------ | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Best fit                 | A single, self-contained remediation action (revoke one key, disable one account)        | Multi-step response sequences with branching logic (snapshot → quarantine → notify → conditionally escalate)           |
| Orchestration visibility | Limited — logic lives in code, harder to visualize the sequence at a glance              | Native step-by-step visual/YAML definition, making the response sequence auditable and reviewable without reading code |
| Error handling/retries   | Manual, coded per function                                                               | Built-in retry policies and error-handling steps per workflow step                                                     |
| Typical role             | The atomic "worker" invoked by a step (or invoked directly by Eventarc for simple cases) | The orchestrator calling multiple Cloud Functions or GCP API steps in sequence with conditional branches               |

> 💡 **Tip:** Production incident response pipelines with more than one or two sequential actions are usually better modeled as a Workflow calling individual Cloud Functions as steps, rather than one large Cloud Function containing all the branching logic — the workflow definition itself becomes reviewable documentation of exactly what automated response does, which matters for SOC audit and compliance review.

## 75.4 Automated Response Pipeline Diagram

```
   SCC Finding (Sec 39)          Chronicle Detection (Sec 72-73)
          │                                  │
          └───────────────┬──────────────────┘
                          ▼
              ┌────────────────────────┐
              │ Eventarc / Pub-Sub     │
              │ (event trigger layer)  │
              └───────────┬────────────┘
                          ▼
              ┌────────────────────────┐
              │   Cloud Workflows      │
              │ (orchestration logic)  │
              └────────────┬───────────┘
             ┌─────────────┼──────────────┐
             ▼             ▼              ▼
     Cloud Function    Cloud Function   Cloud Function
     (snapshot disk)   (quarantine VM)  (revoke key/
                                          disable SA)
             │             │               │
             └─────────────┼───────────────┘
                           ▼
                 Notify SOC Channel (Section 76)
                 + Audit Log Entry
```

## 75.5 Comparison: GCP Automated Response vs. AWS EventBridge/Lambda/SSM vs. Azure Sentinel Automation

| Aspect                      | GCP                                                                            | AWS                                                                                           | Azure                                                                                 |
| --------------------------- | ------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Event trigger layer         | Eventarc (unified eventing, including Pub/Sub-based SCC finding notifications) | EventBridge (rules matching event patterns from GuardDuty, Security Hub, etc.)                | Sentinel's built-in automation rules, triggered directly by analytics rule detections |
| Atomic action execution     | Cloud Functions                                                                | Lambda functions, or **SSM Automation runbooks** for infrastructure-level remediation actions | **Logic Apps** (low-code workflow/connector-based playbooks)                          |
| Multi-step orchestration    | Cloud Workflows                                                                | Step Functions (for complex orchestration) or a single Lambda with internal branching         | Logic Apps itself serves as both the trigger destination and the orchestrator         |
| Remediation authoring style | Code-first (Cloud Functions) with optional visual orchestration (Workflows)    | Code-first (Lambda) or declarative runbooks (SSM Automation documents, JSON/YAML)             | Low-code/visual-first (Logic Apps designer), though code steps are supported          |
| Closest conceptual analog   | Cloud Workflows ≈ Step Functions; Cloud Functions ≈ Lambda                     | —                                                                                             | Logic Apps combines what GCP splits across Eventarc trigger + Workflows orchestration |

> ⚠️ **Interview-relevant nuance:** Azure Sentinel's automation rules and Logic Apps are more tightly and natively integrated into the SIEM product itself than GCP's or AWS's equivalents — a Sentinel automation rule can be attached directly to an analytics rule with no separate eventing layer to configure. GCP and AWS both route through a general-purpose eventing service (Eventarc/EventBridge) that is not SIEM-specific, reflecting a more composable but more manually-wired architecture. This is a legitimate trade-off to discuss: tighter native integration and faster initial setup (Sentinel) versus a more general, reusable eventing substrate that also serves non-security use cases (Eventarc/EventBridge).

## 75.6 Hands-On Example: Eventarc Trigger Invoking a Remediation Cloud Function

**Purpose:** Create an Eventarc trigger that invokes a Cloud Function whenever a new Security Command Center finding matching a specific severity is published to a Pub/Sub topic, implementing the trigger stage of the pattern in 75.3.1.

```bash
gcloud eventarc triggers create scc-critical-finding-trigger \
  --location=us-central1 \
  --destination-run-service=quarantine-responder \
  --destination-run-region=us-central1 \
  --event-filters="type=google.cloud.pubsub.topic.v1.messagePublished" \
  --transport-topic=projects/prod-1/topics/scc-notifications \
  --service-account=incident-responder@prod-1.iam.gserviceaccount.com
```

**Expected output:**

```
Created trigger [scc-critical-finding-trigger].
```

- **Purpose of the dedicated service account:** the trigger invokes the responder function using `incident-responder@prod-1.iam.gserviceaccount.com` rather than a default or overly broad identity, so the responder function's own IAM permissions (compute admin actions for quarantine, IAM admin actions for key revocation) can be scoped tightly to exactly what automated remediation requires — a direct application of least privilege to the automation pipeline itself.
- **Common error:** granting the responder's service account broad project-level Editor/Owner permissions "to make the automation work" instead of the specific narrow permissions each remediation action needs (e.g., `compute.instances.setTags`, `iam.serviceAccountKeys.delete`) — an overly privileged remediation identity becomes itself a high-value target if the automation pipeline's own security is ever compromised.

> 💡 **Tip:** Before wiring a destructive remediation action (disabling a service account, stopping a VM) to fully automatic execution, most mature deployments run the pipeline in a "dry-run"/notify-only mode for a period — logging what action _would_ be taken without taking it — to validate the decision logic against real findings before trusting it to act autonomously, directly mirroring the preview-mode pattern used for Cloud Armor rules (Section 74.7).

## 75.7 Production & Enterprise Usage

- **Tiered automation confidence.** Mature deployments do not automate every possible response uniformly; they reserve full automatic action for high-confidence, low-ambiguity finding types (a confirmed leaked credential, a confirmed malware signature match) and route lower-confidence or higher-blast-radius findings to a human-approval step first (e.g., a Workflow step that pages an analyst for approval before executing the destructive action).
- **Idempotency and duplicate-suppression.** Because detections can fire more than once for the same underlying incident (e.g., a Chronicle rule re-evaluating and re-matching, or both SCC and Chronicle separately flagging the same compromised resource), production remediation logic checks whether an action has already been taken for a given resource/finding before re-executing it, avoiding redundant or conflicting actions.
- **Full audit trail as a compliance requirement.** Every automated action is logged with the triggering finding, the specific action taken, the identity/timestamp, and (for regulated environments) is retained and reportable, since auditors and compliance frameworks require demonstrating exactly what automated systems did and why, not just that "the system responded."

## 75.8 Common Misconceptions

- **Misconception:** "Automated response replaces the SOC analyst." Automation handles narrowly-scoped, high-confidence containment actions to buy time and limit blast radius; root-cause investigation, closing out the incident, and handling ambiguous or novel patterns remain human-led work covered in SOC Patterns (Section 76).
- **Misconception:** "The safest approach is to automate the most destructive response possible (e.g., always terminate a suspicious VM) to guarantee containment." Overly aggressive default automation (destroying rather than quarantining, deleting rather than disabling) destroys forensic evidence and can cause unnecessary production impact from false positives; the quarantine-first pattern (75.3.3) is preferred specifically because it is reversible and preserves evidence.
- **Misconception:** "Eventarc and Cloud Workflows are security-specific tools." Both are general-purpose GCP services — Eventarc is GCP's unified eventing layer and Workflows is a general orchestration service — applied here to a security use case, not dedicated SecOps products, which is precisely why GCP's automation architecture looks more "assembled from general-purpose parts" than Sentinel's natively integrated automation rules (75.5).

## 75.9 Interview Questions

**🎯 Beginner:** _What is the basic pattern behind automated incident response on GCP?_
**Model answer:** A finding from Security Command Center or a detection from Chronicle is published as an event, typically via Pub/Sub, and routed through Eventarc to a Cloud Function or Cloud Workflow. That function or workflow evaluates whether the finding meets criteria for automatic action and, if so, executes a predefined remediation step — such as quarantining a compromised VM or revoking a leaked credential — via GCP APIs, without waiting for manual analyst action.

**🎯 Intermediate:** _Why is quarantining a compromised VM generally preferred over immediately terminating it?_
**Model answer:** Terminating the instance destroys forensic evidence needed for root-cause investigation and destroys the ability to do live analysis of the compromise. Quarantining — isolating the instance's network access via firewall tags or an isolated subnet while keeping it running, after first snapshotting its disks — achieves the same immediate goal of stopping lateral movement and exfiltration, while preserving both the live instance and a disk snapshot for forensic investigation, and remains reversible if the finding turns out to be a false positive.

**🎯 Senior/Architect:** _You're designing an automated response pipeline and need to decide which finding types get fully automatic remediation versus which require human approval first. How would you make that determination, and how would you structure the pipeline to support both paths?_
**Model answer:** I'd base the determination on two axes: confidence of the finding and blast radius/reversibility of the response. High-confidence, low-ambiguity findings with a reversible response — a confirmed leaked credential where the action is disabling one specific key — are strong candidates for full automation, since the cost of a false positive is low (re-enabling a key is trivial) and the cost of delay is real (an active leak). Lower-confidence findings, or findings whose remediation is destructive or hard to reverse — terminating a production database instance, disabling a service account that many production workflows depend on — should route to a human-approval step even if detection confidence is reasonably high, because the asymmetry between the cost of a false positive and the cost of a short delay favors keeping a human in the loop. Structurally, I'd implement this as a single Cloud Workflow with a branching decision step early in the sequence: findings meeting the auto-remediate criteria proceed directly through the snapshot/quarantine/notify steps, while findings falling outside that criteria route to a step that pages an on-call analyst with the finding and a proposed action, waiting for explicit approval (e.g., via a callback into the same workflow) before executing the destructive step. I'd also build in an escape hatch: even auto-remediated actions get logged and surfaced to the SOC channel immediately after execution, not buried, so a human can catch and reverse an automated action quickly if it turns out to be wrong, and I'd periodically review which finding types are auto-remediated as detection confidence and false-positive rates evolve, since the right classification is not static.

## 75.10 Key Takeaways

- 🔑 Automated incident response follows a consistent trigger (Eventarc) → decide (Cloud Function/Workflow logic) → act (GCP API call) pattern, sourcing triggers from SCC findings (Section 39) and Chronicle detections (Sections 72–73).
- 🔑 Quarantine-then-investigate is the preferred pattern for compromised resources — isolate network access after snapshotting for forensics, rather than immediately terminating and destroying evidence.
- 🔑 Cloud Workflows suits multi-step, branching remediation sequences with built-in retry/error handling; Cloud Functions suit atomic single-action remediation steps invoked as workflow steps or directly.
- 🔑 Mature pipelines tier automation by confidence and blast radius — full automation for high-confidence, reversible actions; human-approval gates for lower-confidence or destructive/hard-to-reverse actions.
- 🔑 The remediation pipeline's own service account must be scoped to least privilege, since an overly privileged automation identity becomes a high-value target if the pipeline itself is compromised.
- 🔑 GCP's Eventarc + Workflows architecture is more composable/general-purpose than Azure Sentinel's natively integrated automation rules + Logic Apps, trading faster native setup for a more reusable eventing substrate.

## 75.11 Related Concepts

Security Command Center (Section 39), Eventarc and Cloud Workflows fundamentals (Section 53), Chronicle detection engineering that feeds these triggers (Section 73), Cloud Armor's Adaptive Protection alerts as an additional trigger source (Section 74), and SOC Patterns covering how human analysts work alongside this automation (Section 76) all connect directly to the material in this section.
