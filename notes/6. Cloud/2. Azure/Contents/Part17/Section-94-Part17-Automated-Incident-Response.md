# Section 94 — Automated Incident Response

**Part 17: Security Operations & Incident Response | [Section 94](./Section-94-Part17-Automated-Incident-Response.md) of 100**
**Prerequisites:** [Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md) (Sentinel Deep Dive — analytics rules, incidents, playbook basics), [Section 42](../Part8/Section-42-Part8-Logic-Apps.md) (Logic Apps), [Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md).7 (Defender for Cloud alerts and action-group integration), [Section 8](../Part2/Section-08-Part2-Role-Based-Access-Control.md)-[Section 9](../Part2/Section-09-Part2-Managed-Identities-and-Service-Principals.md) (RBAC, Managed Identities)
**Leads into:** [Section 95](./Section-95-Part17-SOC-Patterns-on-Azure.md) (SOC Patterns on Azure — the organizational and tiered-analyst context this automation operates within)

---

## 1. Definition

**Plain language:** [Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md) introduced playbooks as Logic Apps that can respond to a security alert or incident. This section covers the actual mechanics of wiring detection to automated response — the rules that decide _which_ playbook runs for _which_ incident, and the concrete design patterns (enrichment, containment, notification) a real SOC uses to build playbooks that do genuinely useful, safe automated work rather than either doing nothing useful or doing something too aggressive without a human in the loop.

**Precise definition:** Automated incident response in Sentinel is implemented through **automation rules** (conditions and actions — assigning, tagging, suppressing, or triggering a playbook — evaluated automatically whenever a matching incident is created or updated) that invoke **playbooks** (Logic Apps, [Section 42](../Part8/Section-42-Part8-Logic-Apps.md), with a Sentinel-specific trigger) performing **enrichment** (gathering additional context), **containment** (taking a corrective action, e.g., disabling an account or isolating a resource), and **notification** (alerting a human or opening a tracking ticket) actions, designed according to runbook principles of idempotency, least-privilege execution, and appropriate human-approval gates for destructive actions.

## 2. Why It Exists / Problem It Solves

[Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md) established detection: analytics rules, Fusion correlation, and UEBA all produce incidents. But an incident sitting in a queue, however well-detected, still requires a human analyst to manually gather context, decide on a response, and execute it — for high-incident-volume environments, or for time-critical containment actions where minutes matter (e.g., a compromised account actively being used for lateral movement), pure manual response doesn't scale and is often too slow. [Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md).7.2 already established that Defender for Cloud alerts can be routed through [Section 53](../Part10/Section-53-Part10-Alerts-Action-Groups-Dashboards.md)'s action-group infrastructure for basic notification — but a genuinely mature response needs more than notification: it needs the ability to automatically enrich an incident with additional context (so an analyst reviewing it starts with more information, not less), and, for well-understood, high-confidence scenarios, to automatically execute a containment action without waiting for a human to be available. Automation rules and playbooks exist specifically to close this gap between "we detected something" and "something meaningful was actually done about it," while automation-rule design and runbook principles (94.6) exist specifically to make sure that automation is safe, not merely fast.

---

## 3. Automation Rules

### 3.1 Definition

**Definition:** an automation rule is a condition-and-action configuration evaluated automatically whenever a new (or updated) incident matches its trigger conditions (e.g., "incident created by analytics rule X," or "incident has severity High and contains a specific entity type") — its actions can include changing incident status, assigning an owner, adding a tag, suppressing/closing (for known-benign, high-confidence-false-positive patterns), or running one or more playbooks.

### 3.2 Automation Rules vs. Playbooks — Precise Distinction

| Aspect               | Automation Rule                                                                                               | Playbook                                                                                                 |
| -------------------- | ------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| What it is           | Lightweight condition-and-action configuration, native to Sentinel                                            | A full Logic App ([Section 42](../Part8/Section-42-Part8-Logic-Apps.md)) workflow                        |
| What it can do       | Assign, tag, change status, suppress, or invoke a playbook                                                    | Arbitrary workflow logic — API calls, conditionals, loops, connector actions across hundreds of services |
| Authoring complexity | Simple, built-in condition/action builder                                                                     | Full Logic Apps designer, same skillset as [Section 42](../Part8/Section-42-Part8-Logic-Apps.md)         |
| Typical role         | The "dispatcher" — decides which playbook runs for which incident, and handles simple triage actions directly | The "worker" — does the actual enrichment/containment/notification work                                  |

🎯 **Interview Tip:** a common point of confusion is treating automation rules and playbooks as interchangeable — they are not. The automation rule is the lightweight trigger/dispatch logic; the playbook is where genuinely complex, multi-step response work happens. A well-designed Sentinel deployment typically has relatively few, focused, well-tested playbooks, invoked by potentially many automation rules with different trigger conditions — reusing the same playbook (e.g., "enrich this IP address with threat-intelligence context") across multiple different analytics rules' incidents, rather than duplicating similar logic across many one-off playbooks.

---

## 4. Playbook Design Patterns

### 4.1 Enrichment Playbooks

**Definition:** a playbook that gathers additional context about an incident's entities (an IP address, a user account, a file hash) from external or internal sources — e.g., querying a threat-intelligence API for an IP's reputation, or querying Entra ID (Part 2) for an account's recent sign-in history and group memberships — and writes that context back onto the incident (as a comment or custom detail) for the analyst reviewing it.

**Why it matters:** enrichment playbooks don't take any corrective action at all — they're specifically about reducing analyst investigation time by having the answer to "what do we already know about this entity" waiting on the incident before a human even opens it, a low-risk, high-value automation pattern appropriate to run broadly and automatically on nearly every incident, since there's no destructive action to worry about approving.

### 4.2 Containment Playbooks

**Definition:** a playbook that takes an actual corrective action in response to a high-confidence incident — common examples include disabling a compromised Entra ID user account (via the Microsoft Graph connector), isolating a VM by applying a restrictive NSG rule ([Section 22](../Part5/Section-22-Part5-NSGs-and-Route-Tables.md)) or Defender for Servers' isolation capability, revoking a specific active session/token, or blocking an IP address at a firewall/WAF ([Section 44](../Part8/Section-44-Part8-API-Management.md).7-adjacent material).

**Why containment demands more care than enrichment:** unlike enrichment, a containment action has a real, potentially disruptive effect on a legitimate user or system if the underlying detection turns out to be a false positive — disabling the account of a legitimate user who genuinely was just traveling and signing in from an unusual location, for instance, has a real business-disruption cost. This is precisely why containment playbooks are the ones that most often warrant the human-approval-gate pattern (94.6.3) rather than being fully automatic end-to-end.

### 4.3 Notification/Ticketing Playbooks

**Definition:** a playbook that posts incident details to a Teams channel, sends an email, or opens/updates a ticket in an external ITSM system (e.g., ServiceNow) via its Logic Apps connector — ensuring the right humans and the right system-of-record are updated the moment an incident reaches a relevant status, directly extending the notification role [Section 53](../Part10/Section-53-Part10-Alerts-Action-Groups-Dashboards.md)'s action groups play for general operational alerting (and [Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md).7.2's reuse of that same infrastructure for Defender for Cloud alerts specifically), now implemented as a Sentinel-native playbook rather than an action group.

---

## 5. Trigger Types

### 5.1 Alert-Triggered Playbooks

Run in response to an individual alert being created — appropriate for enrichment or notification actions that make sense at the level of a single detection, before that alert has necessarily been grouped into a broader incident.

### 5.2 Incident-Triggered Playbooks

Run in response to an incident being created or updated (including changes to its status, severity, or assigned owner) — the more commonly used trigger type for containment and notification playbooks, since an incident represents the analyst-facing unit of work and its full, correlated context (potentially multiple related alerts and entities) rather than a single, possibly-partial alert.

### 5.3 Entity-Triggered Playbooks

Run against a specific entity (an account, host, IP address, or file hash) on demand — typically invoked manually by an analyst during investigation ("run this enrichment playbook against this specific IP address right now"), rather than automatically via an automation rule, useful for ad hoc investigative enrichment beyond what's already been automatically gathered.

---

## 6. Runbook Design Principles

### 6.1 Idempotency

**Definition:** a playbook should produce the same end state (and not error, duplicate work, or cause harm) if it's accidentally triggered more than once for the same incident/entity — e.g., a "disable this account" containment action should check the account's current state first and handle the case where it's already disabled gracefully, rather than assuming it always starts from an enabled state.

**Why it matters:** automation rules and Sentinel's own alert/incident lifecycle can, in some circumstances, result in a playbook being invoked more than once for what is conceptually "the same" underlying incident (e.g., an incident being updated multiple times as new related alerts are grouped into it) — a playbook that isn't idempotent can produce confusing, duplicated, or actively harmful side effects (e.g., attempting to re-isolate an already-isolated VM in a way that errors or has an unexpected side effect) under exactly this common, realistic condition.

### 6.2 Least-Privilege Execution

Playbooks authenticate to the services they act against (Entra ID, a VM's NSG, a firewall API) via a managed identity ([Section 9](../Part2/Section-09-Part2-Managed-Identities-and-Service-Principals.md)) — directly reusing the same managed-identity-over-embedded-credentials principle established throughout this roadmap's secrets-avoidance guidance — and that identity should be scoped to the absolute minimum permission the playbook's specific actions require (e.g., a playbook that only ever disables user accounts needs Entra ID user-management permission, not full Global Administrator), so that a playbook's own compromise or a logic bug in its workflow has the smallest possible blast radius.

### 6.3 Human-Approval Gates for Destructive Actions

**Definition:** for containment actions with a meaningful business-disruption cost if wrong (94.4.2), a playbook can pause and wait for explicit analyst approval (e.g., via a Teams Adaptive Card approval prompt, or an approval step in the Logic Apps workflow itself) before executing the actual destructive action, rather than running fully end-to-end without any human checkpoint.

🔑 **Key Takeaway:** the decision of which containment actions should run fully automatically versus require an approval gate is a genuine, incident-type-specific risk judgment — a very high-confidence, low-business-impact action (e.g., automatically blocking a single IP address at a firewall, easily and quickly reversed if wrong) is a reasonable candidate for full automation; a lower-confidence or higher-business-impact action (e.g., disabling a senior executive's account) is a reasonable candidate for requiring human approval first, and treating every containment action identically (either always fully automatic, or always requiring approval, regardless of confidence/impact) is a less mature design than making this trade-off deliberately per scenario.

### 6.4 Logging and Auditability

Every playbook execution (its trigger, the actions taken, and their outcome) should itself be logged in a way that's reviewable after the fact — both for troubleshooting a misbehaving playbook and, for containment actions specifically, as an auditable record of what automated action was taken against which resource/account and why, directly relevant to [Section 58](../Part11/Section-58-Part11-Compliance-Encryption.md)'s compliance and audit material.

---

## 7. Integration With Defender for Cloud Alerts (Extending [Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md).7)

[Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md).7.2 established that Defender for Cloud security alerts reuse [Section 53](../Part10/Section-53-Part10-Alerts-Action-Groups-Dashboards.md)'s action-group infrastructure for basic notification. Once Defender for Cloud is connected into Sentinel as a data connector ([Section 92](./Section-92-Part17-Microsoft-Sentinel-SIEM-Fundamentals.md).5.2), those same alerts additionally become full Sentinel incidents, eligible for the entire automation-rule and playbook machinery covered in this section — meaning a Defender for Cloud-originated alert (e.g., "suspicious process execution detected on this VM" from Defender for Servers, [Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md).4.1) can trigger an enrichment playbook gathering additional VM/process context, then a containment playbook isolating the VM pending investigation, entirely automatically, going well beyond what action-group-based notification alone provides.

---

## 8. Architecture Diagram

```
Incident Created/Updated (Section 93.3.5)
        │
        ▼
 Automation Rule (94.3) — condition match:
   "severity = High AND analytics rule = Brute-Force-Success"
        │
        ├──► Auto-assign to Tier-1 analyst, tag "brute-force"
        │
        └──► Invoke Playbook (Logic App, Section 42)
                    │
                    ├── Step 1: Enrichment (94.4.1)
                    │     Query threat-intel API for IPAddress reputation
                    │     Query Entra ID for account's recent sign-in history
                    │
                    ├── Step 2: Approval Gate (94.6.3)
                    │     Post Teams Adaptive Card: "Disable this account?"
                    │     Wait for analyst approval
                    │
                    ├── Step 3: Containment (94.4.2) — on approval
                    │     Disable Entra ID account via Graph connector
                    │     (playbook's managed identity, least-privilege scoped, 94.6.2)
                    │
                    └── Step 4: Notification (94.4.3)
                          Post outcome to Teams channel / update ServiceNow ticket
```

## 9. Configuration & Hands-On Example

**Creating an automation rule that invokes a playbook on high-severity incidents (Azure CLI):**

```bash
az sentinel automation-rule create \
  --resource-group rg-security \
  --workspace-name law-sentinel-prod \
  --automation-rule-id "auto-contain-brute-force" \
  --display-name "Auto-Contain: Brute-Force Success Incidents" \
  --order 1 \
  --triggering-logic '{
      "isEnabled": true,
      "triggersOn": "Incidents",
      "triggersWhen": "Created",
      "conditions": [
        { "conditionType": "Property",
          "conditionProperties": {
            "propertyName": "IncidentSeverity",
            "operator": "Equals",
            "propertyValues": ["High"]
          } }
      ]
    }' \
  --actions '[
      { "order": 1,
        "actionType": "RunPlaybook",
        "actionConfiguration": { "logicAppResourceId": "/subscriptions/.../resourceGroups/rg-security/providers/Microsoft.Logic/workflows/pb-contain-brute-force" }
      }
    ]'
```

- **Purpose:** wires the enrichment/approval/containment/notification playbook from [Section 94](./Section-94-Part17-Automated-Incident-Response.md).8's diagram to automatically run whenever a new High-severity incident is created, closing the loop between the [Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md).10 analytics rule's detection and this section's automated response.
- **Important arguments explained individually:**
  - `--order` — automation rules are evaluated in a defined order against each incident; explicit ordering matters when multiple rules could match the same incident (e.g., a general "tag all High-severity incidents" rule and a specific "auto-contain brute-force incidents" rule both potentially applying), since a later rule's actions can depend on or conflict with an earlier rule's.
  - `--triggering-logic` — the JSON condition block defining exactly which incidents this rule applies to; matching on `IncidentSeverity` here, but conditions can also match on the originating analytics rule, specific entity types present, or custom tags.
  - `--actions` — the `RunPlaybook` action references the playbook's full Logic App resource ID; the playbook itself (its enrichment/approval/containment steps) is authored separately in the Logic Apps designer ([Section 42](../Part8/Section-42-Part8-Logic-Apps.md)), with this automation rule purely responsible for deciding _when_ to invoke it.
- **Common error:** granting the playbook's managed identity broader permissions than its actual actions require (e.g., granting full Entra ID Global Administrator rights to a playbook that only ever needs to disable a single user account) "to avoid permission errors during testing," then never revisiting that over-broad grant once the playbook is confirmed working — directly violating the least-privilege principle from [Section 94](./Section-94-Part17-Automated-Incident-Response.md).6.2 and leaving a significantly larger blast radius than the playbook's actual function requires if the playbook's own logic or credentials were ever compromised.

## 10. Production & Enterprise Usage

Mature SOCs maintain a curated, relatively small library of well-tested, reusable playbooks (enrichment, common containment actions, standard notification patterns) invoked by many different automation rules across different analytics rules, rather than authoring a new bespoke playbook per analytics rule — directly mirroring the "few, well-tested, reusable modules" principle already established for Bicep/Terraform modules ([Section 47](../Part9/Section-47-Part9-Bicep.md).11, [Section 48](../Part9/Section-48-Part9-Terraform-on-Azure.md).8) and applied here to security-response automation specifically. Playbooks handling containment actions are typically version-controlled and code-reviewed with the same rigor as any other production automation, given their real-world blast radius.

## 11. Security Considerations

- A playbook's managed identity is, in effect, a standing credential with real permission to take corrective action against production systems and accounts — it should be scoped to least privilege (94.6.2), monitored for unexpected/anomalous invocation patterns, and treated as a genuinely sensitive component of the security estate rather than an implementation detail.
- Approval-gate steps (94.6.3) themselves need to route to genuinely available, appropriately-authorized approvers — an approval gate that pages an approver who's unreachable (out of office, wrong on-call rotation) effectively stalls containment indefinitely for what may be a time-critical incident, undermining the entire point of near-real-time automated response.

## 12. Performance Considerations

Playbooks invoking external APIs (a threat-intelligence lookup, a ticketing-system call) inherit those external dependencies' latency and reliability characteristics — a slow or occasionally-unavailable external enrichment source can meaningfully delay end-to-end incident processing time if the playbook doesn't handle timeouts/retries gracefully, directly analogous to any other Logic Apps integration reliability consideration already covered in [Section 42](../Part8/Section-42-Part8-Logic-Apps.md).

## 13. Monitoring

Logic Apps run history ([Section 42](../Part8/Section-42-Part8-Logic-Apps.md)) provides the execution-level detail (success/failure, per-step duration, error messages) for every playbook invocation; this should be actively monitored — a containment playbook silently failing partway through (e.g., successfully disabling an account but failing to post the expected notification) can leave a SOC with a false sense that containment occurred, and without run-history monitoring, that gap can go unnoticed for a meaningful period.

## 14. Troubleshooting

| Symptom                                                                                                                    | Likely Cause                                                                                                                                                       | Fix                                                                                                                                      |
| -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- |
| An automation rule appears configured correctly, but its playbook never actually runs                                      | Automation rule's trigger conditions don't actually match the incidents in question, or rule ordering causes an earlier rule to intercept/close the incident first | Review actual incident properties against the rule's condition logic; review automation-rule execution order (94.9)                      |
| Playbook fails with an authorization error against a target system (e.g., Entra ID, a firewall API)                        | Playbook's managed identity lacks the specific permission its action requires                                                                                      | Grant the minimum additional permission required (94.6.2), verified against the specific failing action, not a broad catch-all grant     |
| A containment action was executed twice for what appears to be the same incident, with a confusing/erroring second attempt | Playbook not designed idempotently (94.6.1) — doesn't check current state before acting                                                                            | Add a current-state check at the start of the containment step, and handle the "already in the desired state" case gracefully            |
| Approval-gate step never receives a response, stalling the incident indefinitely                                           | Approval routed to an unavailable/incorrect approver or channel                                                                                                    | Verify approval routing logic and on-call/approver availability; consider a timeout-and-escalate fallback rather than an indefinite wait |

## 15. Interview Questions — [Section 94](./Section-94-Part17-Automated-Incident-Response.md)

### 🎯 Intermediate

**Q: What is the difference between an automation rule and a playbook in Microsoft Sentinel, and why does Sentinel separate these into two distinct concepts rather than one?**

_Model answer:_ An automation rule is lightweight condition-and-action configuration native to Sentinel, deciding _when_ and _for which incidents_ something should happen — it can perform simple actions itself (assign, tag, suppress) or invoke a playbook. A playbook is a full Logic App workflow doing the actual, potentially complex, multi-step work (enrichment API calls, approval gates, containment actions, notifications). Separating these lets a small number of well-tested, reusable playbooks be invoked by many different automation rules with different trigger conditions, rather than needing a bespoke, duplicated workflow authored per analytics rule — the same "enrich this IP address" playbook, for example, can be triggered by many different detection rules that all produce IP-address entities.

_What the interviewer is probing:_ clear understanding of the dispatcher-vs-worker separation of concerns, and the practical reuse benefit it enables.

### 🎯 Senior/Architect

**Q: Design an automated incident-response workflow for a "compromised account" scenario in Sentinel, balancing response speed against the risk of a false positive disabling a legitimate user's access.**

_Model answer:_ I'd design a multi-stage playbook rather than a single all-or-nothing automated action. Stage one is enrichment (94.4.1), fully automatic and safe to run on every matching incident: querying threat-intelligence context for any involved IP address, and querying Entra ID for the account's recent sign-in history, typical locations, and group memberships, all attached to the incident before any human or further action occurs. Stage two is a confidence-based branch: if the incident's signal is extremely high-confidence and low-business-impact to act on wrongly (for example, a successful sign-in immediately following an IP address independently flagged as a known-malicious brute-force source within the same short window, per the [Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md).4 detection pattern), I'd allow a narrow, specific containment action — such as forcing re-authentication or revoking the specific session token, which is disruptive but readily reversible — to run fully automatically. For a full account disablement, which has a real business-disruption cost if the underlying detection is wrong, I'd insert a human-approval gate (94.6.3) via a Teams Adaptive Card routed to the on-call Tier 2 analyst, with a defined timeout-and-escalate path if no response arrives within a set window, rather than either fully automating account disablement end-to-end or requiring manual triage for every single occurrence. Throughout, the playbook's managed identity would be scoped to exactly the Entra ID permissions its specific actions require (session revocation, account disablement) and nothing broader (94.6.2), every step's outcome logged for audit (94.6.4), and the containment step built idempotently (94.6.1) so a duplicate trigger for the same incident doesn't error or cause an unexpected side effect on an already-contained account.

_What the interviewer is probing:_ the ability to design a genuinely risk-calibrated automation — not "automate everything" or "automate nothing," but a deliberate confidence/impact-based split between fully automatic and approval-gated actions, plus the supporting runbook discipline (idempotency, least privilege, auditability) that makes the automation trustworthy at scale.

## 16. Common Misconceptions

- **"Automation rules and playbooks are basically the same thing, just different names."** False — automation rules are lightweight trigger/dispatch configuration; playbooks are full Logic Apps workflows doing the actual work. One automation rule invokes one (or more) playbooks; a single well-designed playbook is typically reused across many automation rules.
- **"Fully automated containment is always the goal — the more automation, the better."** False — containment actions with meaningful false-positive business-disruption cost warrant a human-approval gate; treating every containment action as safe to fully automate regardless of confidence/impact is a less mature, riskier design than a deliberate, scenario-specific split.
- **"A playbook's managed identity just needs 'enough' permission to avoid errors, and can be tightened later."** False in practice, if not in principle — over-broad permissions granted during testing are routinely never revisited once things work, leaving a permanently oversized blast radius; least-privilege scoping should be treated as a day-one requirement, not deferred cleanup.

## 17. Key Takeaways

- 🔑 Automation rules are Sentinel-native condition/dispatch logic; playbooks are full Logic Apps ([Section 42](../Part8/Section-42-Part8-Logic-Apps.md)) workflows doing enrichment, containment, and notification work — the separation enables a small library of reusable playbooks invoked by many different rules.
- 🔑 Enrichment playbooks (gathering context, no destructive action) are low-risk and appropriate to run broadly automatically; containment playbooks (taking corrective action with real business-disruption risk if wrong) warrant more deliberate design, often including a human-approval gate.
- 🔑 Idempotency, least-privilege managed-identity scoping, and logged auditability are non-negotiable runbook design principles for any playbook capable of taking a real corrective action against production systems.
- 🔑 The decision of which containment actions run fully automatically versus require human approval is a genuine, per-scenario confidence/impact trade-off, not a single blanket policy applied identically to every action.
- 🔑 Connecting Defender for Cloud alerts ([Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md).7) into Sentinel unlocks this entire automation-rule/playbook machinery for those alerts, going well beyond the basic action-group notification [Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md).7.2 originally described.

## 18. Related Concepts (Next Up)

[Section 95](./Section-95-Part17-SOC-Patterns-on-Azure.md) zooms out from individual rules and playbooks to the organizational and operational context they run within — **SOC patterns on Azure**: centralized Sentinel workspace strategy across a multi-subscription/multi-tenant estate (building directly on [Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md)), tiered analyst workflows, MITRE ATT&CK coverage mapping, and the metrics a SOC uses to measure whether all of this detection and automation is actually working.
