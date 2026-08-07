# Section 95 — Security Operations Center (SOC) Patterns on Azure

**Part 17: Security Operations & Incident Response | [Section 95](./Section-95-Part17-SOC-Patterns-on-Azure.md) of 100**
**Prerequisites:** [Section 94](./Section-94-Part17-Automated-Incident-Response.md) (Automated Incident Response), [Section 92](./Section-92-Part17-Microsoft-Sentinel-SIEM-Fundamentals.md)-[Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md) (Sentinel fundamentals and deep dive), [Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md) (Multi-Subscription/Multi-Tenant Architecture), [Section 68](../Part13/Section-68-Part13-Hybrid-Multi-Cloud-Azure-Arc.md) (Hybrid & Multi-Cloud, Azure Arc)
**Leads into:** [Section 96](./Section-96-Part17-WrapUp-Interview-Drill.md) (Part 17 Wrap-Up + Security Operations Interview Drill)

---

## 1. Definition

**Plain language:** the previous four sections in this Part covered the individual tools — Purview for data classification, Sentinel for detection/hunting, and automation rules/playbooks for response. This section covers how those tools actually get organized into a functioning team and process across a real enterprise — how many Sentinel workspaces you run and where, how work is divided among analysts of different experience levels, how you know your detection coverage actually maps to real-world attack techniques, and how you measure whether the whole operation is actually working.

**Precise definition:** a Security Operations Center (SOC) pattern on Azure is the organizational and architectural design governing how Sentinel workspace(s) are deployed and scoped across an enterprise's subscriptions and tenants, how incident-handling work is divided across tiered analyst roles, how detection coverage is deliberately mapped against a standard attack-technique taxonomy (MITRE ATT&CK), and how the SOC's own effectiveness is measured via defined operational metrics.

## 2. Why It Exists / Problem It Solves

Every tool covered in Sections 91-94 works at the level of a single detection, a single incident, a single playbook. None of them answer organizational-scale questions: should a 40-subscription enterprise (the recurring scenario from [Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md)) run one Sentinel workspace or several? Should every analyst handle every incident from initial triage through deep forensic investigation, or should work be divided by experience level and incident severity? How does a security leader know whether the analytics rules deployed in [Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md) actually provide meaningful coverage against real-world attacker behavior, rather than a scattered, ad hoc set of rules with unknown gaps? And ultimately, how does anyone — a CISO, an auditor, a board — know whether the SOC is actually effective, rather than merely busy? SOC patterns exist to answer these organizational-design questions, applying the same kind of centralization-vs-isolation trade-off reasoning already established repeatedly throughout this roadmap ([Section 50](../Part10/Section-50-Part10-Azure-Monitor-Fundamentals.md).8 for Log Analytics workspaces, [Section 56](../Part11/Section-56-Part11-Key-Vault.md).9.1 for Key Vaults, [Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md).3.4 for subscriptions generally) to the specific domain of running security operations at genuine enterprise scale.

---

## 3. Centralized vs. Federated Sentinel Workspace Models

### 3.1 The Centralization Argument (Recap and Application of [Section 92](./Section-92-Part17-Microsoft-Sentinel-SIEM-Fundamentals.md).9)

[Section 92](./Section-92-Part17-Microsoft-Sentinel-SIEM-Fundamentals.md).9 already established the core principle: Sentinel's value is cross-source correlation, which is undermined by fragmenting security signal across many isolated workspaces. For a genuinely large, multi-subscription enterprise, this argues for a **single, centrally-owned Sentinel workspace** ingesting data connectors from across every subscription (and, per [Section 68](../Part13/Section-68-Part13-Hybrid-Multi-Cloud-Azure-Arc.md)'s Azure Arc material, from on-premises and other-cloud sources as well), rather than one Sentinel deployment per subscription or business unit.

### 3.2 Cross-Subscription and Cross-Tenant Data Collection

Data from resources in other subscriptions (even other Entra ID tenants, in an MSSP or holding-company scenario) can be ingested into one centralized Sentinel workspace via appropriately configured data connectors and diagnostic settings pointing at the central workspace, rather than requiring the workspace itself to live in every subscription — directly extending [Section 50](../Part10/Section-50-Part10-Azure-Monitor-Fundamentals.md).4.2's diagnostic-settings export pattern, now applied at genuinely cross-subscription and cross-tenant scale.

### 3.3 Azure Lighthouse for Cross-Tenant SOC Operations

**Definition:** Azure Lighthouse enables a service provider (or a central corporate SOC) to be delegated access to resources and Sentinel workspaces in a **different Entra ID tenant**, without requiring guest-user access in each managed tenant individually — the common mechanism behind Managed Security Service Provider (MSSP) SOC models, and behind a parent-company SOC monitoring an acquired subsidiary's still-separate tenant (directly connecting to [Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md).2.2's "genuinely distinct organizational entities" framing for when a second tenant is actually warranted).

🔑 **Key Takeaway:** the choice between "one workspace serving multiple subscriptions within a single tenant" (95.3.2, the common case) and "cross-tenant delegated access via Azure Lighthouse" (95.3.3, the rarer, genuinely-separate-organization case) directly mirrors [Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md).2's subscription-vs-tenant distinction — most enterprise SOC centralization scenarios are solved within a single tenant using multi-subscription data collection, with Lighthouse reserved specifically for cases where a genuinely separate tenant boundary (an acquired company, an external MSSP relationship) is actually in play.

### 3.4 When Federation Is Still Appropriate

Despite the strong default toward centralization, a small number of scenarios still justify separate Sentinel workspaces — a strict data-residency or regulatory boundary requiring security log data to remain within a specific geographic/legal jurisdiction, or a genuinely separate organizational entity (post-acquisition, prior to full integration) not yet ready for shared workspace access — but these are deliberate exceptions to the centralization default, not the default itself, and should be treated as such in any architectural design.

---

## 4. Tiered Analyst Workflows

### 4.1 Tier 1 — Triage

**Definition:** the first line of incident handling — reviewing newly created incidents ([Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md).3.5), applying initial triage using the enrichment context already attached by automation ([Section 94](./Section-94-Part17-Automated-Incident-Response.md).4.1), and either resolving straightforward, well-understood incidents directly or escalating genuinely uncertain/complex incidents to Tier 2.

### 4.2 Tier 2 — Investigation

**Definition:** deeper investigation of escalated incidents — correlating across multiple data sources, using hunting queries ([Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md).5.1) to explore beyond the original incident's scope, and making the actual containment decision (including approving human-approval-gated playbook actions, [Section 94](./Section-94-Part17-Automated-Incident-Response.md).6.3) for incidents requiring judgment beyond Tier 1's initial triage.

### 4.3 Tier 3 — Threat Hunting and Advanced Response

**Definition:** the most experienced analysts, typically spending a meaningful portion of their time on proactive threat hunting ([Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md).5) rather than only reactive incident handling — developing new hunting hypotheses, authoring new analytics rules/playbooks based on patterns discovered through hunting, and handling the most complex, novel, or high-stakes incidents Tier 2 escalates further.

### 4.4 Why Tiering Matters Architecturally, Not Just Organizationally

🎯 **Interview Tip:** tiering isn't merely an HR/staffing decision — it directly shapes Sentinel RBAC design (workspace-level and even table-level access can be scoped so Tier 1 analysts see incident-level detail without necessarily needing the same broad hunting-query/raw-log access granted to Tier 3) and playbook design (an automation rule's initial routing/assignment logic, [Section 94](./Section-94-Part17-Automated-Incident-Response.md).3.1, typically routes based on incident severity/type directly to the appropriate tier, rather than every incident landing in one undifferentiated queue for a human to manually re-route).

---

## 5. MITRE ATT&CK Mapping

### 5.1 Definition

**Definition:** MITRE ATT&CK is a publicly maintained, industry-standard taxonomy of adversary tactics (the "why" — e.g., Credential Access, Lateral Movement) and techniques (the specific "how" within each tactic) observed in real-world attacks; Sentinel analytics rules can be tagged with the specific ATT&CK tactics/techniques they detect (as shown in the `--tactics` argument in [Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md).10's CLI example), and Sentinel provides a built-in MITRE ATT&CK workbook visualizing detection coverage across the full framework.

### 5.2 Why It Matters for Coverage Assessment

Without a standard taxonomy, "do we have good detection coverage" is an unanswerable, subjective question. With ATT&CK mapping, it becomes a concrete, visualizable gap analysis: which tactics/techniques have zero, one, or several tagged analytics rules covering them, directly informing where a SOC should prioritize authoring new detection logic (93.3.1) or reviewing newly available Microsoft Security rule templates ([Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md).3.4) — turning "improve our detection coverage" from a vague aspiration into a specific, trackable, technique-by-technique backlog.

### 5.3 Limitations

⚠️ ATT&CK-tagged rule _existence_ is not the same as _effective_ detection — a rule tagged against a specific technique but poorly tuned (excessive false positives leading analysts to routinely dismiss it, or a threshold set so high it rarely fires even against real activity) provides a misleading sense of coverage; the coverage workbook should be read alongside actual true-positive-rate data (the same rule-effectiveness measurement introduced in [Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md).16's senior interview scenario), not as a standalone measure of genuine protection.

---

## 6. SOC Effectiveness Metrics

| Metric                                    | Definition                                                                                          | Why It Matters                                                                                                                                                                                                                                   |
| ----------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **MTTD (Mean Time to Detect)**            | Average time between an attacker's initial action and the SOC's detection of it                     | Shorter MTTD limits an attacker's dwell time and opportunity to cause damage before being noticed                                                                                                                                                |
| **MTTR (Mean Time to Respond/Remediate)** | Average time between detection and effective containment/remediation                                | Directly reflects the value of the automation-rule/playbook investment from [Section 94](./Section-94-Part17-Automated-Incident-Response.md) — a well-automated containment pipeline should materially reduce MTTR versus a fully manual process |
| **Alert-to-incident ratio**               | How many raw alerts collapse into how many actual analyst-facing incidents                          | A very high ratio can indicate under-tuned grouping/correlation logic ([Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md).15) producing excessive alert noise rather than well-consolidated, actionable incidents                           |
| **False-positive rate**                   | Proportion of incidents closed as benign/non-actionable                                             | Directly informs the alert-fatigue tuning discussion from [Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md).16; persistently high false-positive rates on a specific rule justify tuning or retiring that rule                             |
| **ATT&CK coverage**                       | Proportion of relevant ATT&CK tactics/techniques with at least one tagged, effective analytics rule | Turns detection-coverage improvement into a concrete, trackable backlog (95.5.2), rather than a subjective assessment                                                                                                                            |

🔑 **Key Takeaway:** these metrics should be tracked together, not in isolation — a SOC with excellent MTTD/MTTR but a very high false-positive rate may simply be over-triggering on low-confidence rules (fast to "detect" noise, not necessarily fast to detect genuine threats); a SOC with low false-positive rate but poor ATT&CK coverage may be well-tuned but genuinely blind to entire categories of attack technique. A mature SOC dashboard presents all of these together specifically to avoid a misleadingly rosy picture from any single metric viewed alone.

---

## 7. Comparison — Centralized vs. Federated SOC Models

| Aspect                   | Centralized (single workspace, one tenant)                                                                                                                              | Federated (multiple workspaces / cross-tenant via Lighthouse)                                                                                                                                                |
| ------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Cross-source correlation | Strong — all signal in one place                                                                                                                                        | Weaker — correlation across workspace boundaries requires cross-workspace query or manual correlation                                                                                                        |
| Typical driver           | Default recommendation for a single-tenant, multi-subscription enterprise ([Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md).3) | Strict data-residency/regulatory boundary, or genuinely separate tenant (post-acquisition, MSSP relationship, [Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md).2.2) |
| Operational overhead     | Lower — one workspace, one rule set, one analyst team to maintain                                                                                                       | Higher — coverage, rules, and metrics must be maintained and reconciled across multiple workspaces                                                                                                           |
| RBAC granularity         | Achieved via table-level and workspace-level RBAC within the single workspace (95.4.4)                                                                                  | Achieved more coarsely, by the workspace/tenant boundary itself                                                                                                                                              |

---

## 8. Architecture Diagram

```
                     Corporate Entra ID Tenant
                     ┌───────────────────────────────────────┐
                     │  Management Group Hierarchy (Section 4) │
                     │   ├── Sub 1 ── diagnostic settings ────┐│
                     │   ├── Sub 2 ── diagnostic settings ────┤│
                     │   ├── ...  (up to 40+, Section 67)     ││
                     │   └── Sub N ── diagnostic settings ────┘│
                     └───────────────────┬─────────────────────┘
                                         ▼
                     Centralized Sentinel Workspace
                     (single workspace, cross-subscription, 95.3.2)
                                         │
        ┌────────────────────────────────┼────────────────────────────┐
        ▼                                ▼                            ▼
   Tier 1 Analysts                Tier 2 Analysts               Tier 3 Analysts
   (triage incidents,             (deep investigation,          (threat hunting,
    Section 95.4.1)                approve containment,          new rule/playbook
                                    Section 95.4.2)                authoring, 95.4.3)

   Azure Lighthouse (95.3.3) ──► Delegated cross-tenant access
                                  for an acquired subsidiary's
                                  still-separate tenant, or an
                                  external MSSP relationship

   MITRE ATT&CK Workbook (95.5) — coverage gap analysis feeding
   Tier 3's new-rule-authoring backlog
```

## 9. Configuration & Hands-On Example

**A KQL query surfacing ATT&CK tactic coverage gaps — which enabled analytics rules map to which tactics, and by extension, which don't have coverage at all:**

```kql
SecurityAlert
| where TimeGenerated > ago(90d)
| mv-expand Tactic = todynamic(Tactics)
| summarize AlertCount = count(), Rules = make_set(AlertName) by tostring(Tactic)
| order by AlertCount asc
```

- **Purpose:** aggregates alert volume by MITRE ATT&CK tactic over the last 90 days, sorted ascending — tactics near the top of the result (very low or zero alert volume) are candidates for a genuine coverage gap (no effective rule generating alerts for that tactic) rather than simply "that tactic hasn't been attempted against us," directly supporting the coverage-gap-analysis workflow described in [Section 95](./Section-95-Part17-SOC-Patterns-on-Azure.md).5.2.
- **Important arguments explained individually:**
  - `mv-expand Tactic = todynamic(Tactics)` — `Tactics` is stored as a multi-value field (an alert can map to more than one tactic); `mv-expand` flattens this so each tactic is counted independently, a KQL pattern directly extending the operators covered in [Section 51](../Part10/Section-51-Part10-Log-Analytics-KQL.md).6 to a genuinely multi-valued security field.
  - `make_set(AlertName)` — collects the distinct set of alert/rule names contributing to each tactic's count, letting an analyst immediately see _which_ rules (if any) cover a given tactic, not just how many alerts fired.
- **Common error:** interpreting a tactic with low alert volume as automatically meaning "we have no coverage" without checking whether a rule tagged for that tactic exists but simply hasn't fired (a genuinely different, better situation than no rule existing at all) — the `make_set(AlertName)` output specifically distinguishes "no rule exists for this tactic" from "a rule exists but hasn't matched anything in the window," and conflating these two very different situations is a common analysis mistake.

## 10. Production & Enterprise Usage

Enterprises at genuine multi-subscription scale ([Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md)'s 40-subscription scenario) typically operate exactly one centralized Sentinel workspace, with Azure Policy ([Section 57](../Part11/Section-57-Part11-Azure-Policy-Blueprints.md)) enforcing that every new subscription's relevant diagnostic settings/data connectors are automatically wired to feed that central workspace — directly extending the same management-group-scoped auto-enforcement pattern already established for Defender for Cloud ([Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md).8.1) and Purview ([Section 91](./Section-91-Part17-Microsoft-Purview.md).8), now applied to the SOC's central data-collection requirement specifically, ensuring no new subscription is ever silently invisible to the SOC by omission.

## 11. Security Considerations

- Centralizing security-relevant log data from across an entire enterprise into one workspace makes that workspace an exceptionally high-value target — its own access controls, monitoring, and (where relevant) Lighthouse delegation scoping deserve security scrutiny at least as rigorous as the systems it's monitoring.
- Tiered RBAC (95.4.4) should be genuinely enforced, not merely aspirational — granting every analyst, regardless of tier, full workspace access "for convenience" defeats the access-control benefit tiering is meant to provide.

## 12. Performance Considerations

A single, large centralized workspace ingesting from dozens of subscriptions can encounter genuinely large query volumes across many concurrent analysts and automation rules — the same KQL performance discipline from [Section 51](../Part10/Section-51-Part10-Log-Analytics-KQL.md) and [Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md).13 applies at magnified scale here, and query performance/cost monitoring ([Section 95](./Section-95-Part17-SOC-Patterns-on-Azure.md).14) becomes proportionally more important as workspace scale grows.

## 13. Monitoring

Beyond the individual rule/playbook health monitoring already covered in Sections 92-94, a SOC-level operations dashboard tracking the effectiveness metrics from [Section 95](./Section-95-Part17-SOC-Patterns-on-Azure.md).6 (MTTD, MTTR, false-positive rate, ATT&CK coverage) over time is itself the primary monitoring artifact at this organizational layer — reviewed regularly by SOC leadership, not only by individual analysts investigating individual incidents.

## 14. Troubleshooting

| Symptom                                                                                                                                 | Likely Cause                                                                                                                                                                      | Fix                                                                                                                                                                                              |
| --------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| A newly onboarded subscription's resources never appear in the central Sentinel workspace                                               | Diagnostic settings/data connector wiring not yet configured for the new subscription, or Azure Policy enforcement (95.10) not covering that scope                                | Verify Policy assignment scope includes the new subscription; manually wire diagnostic settings in the interim                                                                                   |
| MTTR is high despite substantial automation-rule/playbook investment ([Section 94](./Section-94-Part17-Automated-Incident-Response.md)) | Approval-gate steps ([Section 94](./Section-94-Part17-Automated-Incident-Response.md).6.3) routinely stalling on unavailable approvers, or containment playbooks failing silently | Review playbook run history ([Section 94](./Section-94-Part17-Automated-Incident-Response.md).13) for stalled/failed executions specifically, not just overall incident-closure time             |
| ATT&CK coverage workbook shows strong coverage, but a real incident post-mortem reveals the relevant technique wasn't actually detected | A rule was tagged for the technique but poorly tuned/ineffective (95.5.3) — tag existence without effective detection                                                             | Review the specific rule's true-positive history for that technique; treat ATT&CK-tag presence as necessary but not sufficient evidence of real coverage                                         |
| Tier 1 analysts routinely escalate nearly every incident to Tier 2, overloading the higher tier                                         | Tier 1 lacks sufficient enrichment context or defined triage criteria to resolve straightforward incidents independently                                                          | Review and expand automated enrichment ([Section 94](./Section-94-Part17-Automated-Incident-Response.md).4.1) attached to incidents before they reach Tier 1; clarify triage/escalation criteria |

## 15. Interview Questions — [Section 95](./Section-95-Part17-SOC-Patterns-on-Azure.md)

### 🎯 Intermediate

**Q: Why does MITRE ATT&CK mapping matter for a Sentinel deployment, and what's a common mistake in relying on it?**

_Model answer:_ ATT&CK mapping turns "do we have good detection coverage" from a subjective, unanswerable question into a concrete gap analysis — tagging analytics rules with the specific tactics/techniques they detect, and using the built-in coverage workbook to see which parts of the framework have zero, weak, or strong rule coverage, directly prioritizing where to author new detection logic. The common mistake is treating the presence of an ATT&CK-tagged rule as proof of effective detection — a rule can be tagged for a technique but be so poorly tuned (excessive false positives, or a threshold too high to ever fire on real activity) that it provides no genuine protection despite showing "covered" on the workbook; coverage-workbook data should always be read alongside actual rule-effectiveness/true-positive data, not as a standalone measure.

_What the interviewer is probing:_ understanding that ATT&CK mapping is a coverage-planning tool, not itself a guarantee of detection quality — a subtlety that distinguishes genuine SOC operational maturity from box-checking.

### 🎯 Senior/Architect

**Q: A holding company acquires a subsidiary that operates its own, entirely separate Entra ID tenant, and wants its central SOC to gain visibility into the subsidiary's security posture as quickly as possible, without waiting for a lengthy, disruptive tenant-consolidation project. How would you architect this?**

_Model answer:_ Since this is a genuinely separate Entra ID tenant (not merely additional subscriptions within the parent's existing tenant), this is squarely the scenario [Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md).2.2 flags as warranting cross-tenant tooling rather than the default single-tenant, multi-subscription centralization pattern (95.3.2) — I would not attempt to force the subsidiary into the parent's tenant purely to gain SOC visibility, since that kind of full tenant consolidation is a much larger, slower, more disruptive undertaking than the immediate visibility goal requires. Instead, I'd use **Azure Lighthouse** (95.3.3) to establish delegated access from the subsidiary's tenant to the parent's central security team, scoped specifically to what the SOC needs (read access to the subsidiary's relevant resource logs and its own Sentinel workspace, if it has one, or delegated rights to configure data connectors feeding the subsidiary's data into the parent's central workspace) — giving the central SOC genuine, near-immediate visibility and correlation capability without requiring identity-boundary consolidation as a prerequisite. I'd track this as an explicit, deliberate exception to the centralization default (95.3.4), clearly scoped and time-bounded if a full tenant consolidation is eventually planned, and I'd extend the parent SOC's ATT&CK coverage assessment (95.5) and effectiveness metrics (95.6) to include the subsidiary's now-visible data, so it's measured with the same rigor as the rest of the estate rather than being treated as a second-class, loosely monitored addition.

_What the interviewer is probing:_ recognizing this as a tenant-boundary problem (not merely a subscription-scaling problem), correctly reaching for Azure Lighthouse rather than either full tenant migration or building entirely separate, disconnected tooling, and understanding that cross-tenant visibility is a deliberate architectural exception with its own tracked scope, not simply "turn on Sentinel there too."

## 16. Common Misconceptions

- **"Every subsidiary or subscription should get its own dedicated Sentinel workspace for isolation."** False — the strong architectural default is centralization within a single tenant (95.3.1), since correlation value is lost by fragmenting workspaces; federation is a deliberate exception for specific regulatory or genuine-tenant-boundary reasons (95.3.4), not the default posture.
- **"MITRE ATT&CK coverage percentage alone tells you how good your detection is."** False — tag presence is necessary but not sufficient; a poorly tuned rule tagged against a technique can provide a false sense of coverage (95.5.3) that only a true-positive-rate review would reveal.
- **"Tiered analyst structure is purely an HR/staffing concern, unrelated to the technical Sentinel design."** False — tiering directly shapes RBAC scoping and automation-rule routing/assignment logic (95.4.4), making it a genuine architectural consideration, not only an organizational-chart decision.

## 17. Key Takeaways

- 🔑 The strong default for Sentinel workspace strategy at enterprise scale is centralization — one workspace per tenant (or major regulatory boundary), collecting data across all subscriptions — with federation reserved for deliberate exceptions like genuine tenant boundaries or strict data-residency requirements.
- 🔑 Azure Lighthouse extends SOC visibility across genuinely separate Entra ID tenants (post-acquisition subsidiaries, MSSP relationships) without requiring full tenant consolidation, directly mirroring [Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md).2's subscription-vs-tenant distinction.
- 🔑 Tiered analyst workflows (Tier 1 triage, Tier 2 investigation, Tier 3 hunting) directly shape RBAC and automation-routing design, not just staffing structure.
- 🔑 MITRE ATT&CK mapping turns detection-coverage assessment into a concrete, trackable gap analysis, but tag presence alone doesn't guarantee effective detection — it must be paired with true-positive-rate data.
- 🔑 SOC effectiveness should be measured across multiple metrics together (MTTD, MTTR, false-positive rate, ATT&CK coverage) rather than any single metric in isolation, since each metric alone can present a misleadingly favorable picture.

## 18. Related Concepts (Next Up)

[Section 96](./Section-96-Part17-WrapUp-Interview-Drill.md) closes out Part 17 with a synthesis of Sections 91-95 and a rapid-fire interview drill spanning the entire Security Operations & Incident Response part, before transitioning to **Part 18 — Resilience Testing & Chaos Engineering**, beginning at [Section 97](../Part18/Section-97-Part18-Azure-Chaos-Studio-Fundamentals.md).
