# Section 93 — Microsoft Sentinel Deep Dive: Analytics Rules, Hunting, and SOAR Playbooks

**Part 17: Security Operations & Incident Response | Section 93 of 100**
**Prerequisites:** Section 92 (Sentinel SIEM Fundamentals — workspace foundation, data connectors), Section 51 (Log Analytics & KQL), Section 42 (Logic Apps — the automation engine SOAR playbooks are built on), Section 55 (Defender for Cloud alerts as a data source)
**Leads into:** Section 94 (Automated Incident Response — automation rules, playbook design patterns, containment)

---

## 1. Definition

**Plain language:** Section 92 established that Sentinel ingests security signal from everywhere into one Log Analytics workspace. This section covers what actually turns that raw, ingested log data into something a security analyst acts on: rules that continuously watch the data for known-bad patterns and generate prioritized incidents, dashboards and hunting tools for an analyst to proactively go looking for something a rule hasn't been written for yet, and the automated playbooks that can respond the moment something is found.

**Precise definition:** Microsoft Sentinel's detection and response layer consists of **analytics rules** (scheduled, near-real-time, and Fusion correlation logic that generates **incidents** from matching log data), **hunting queries** and **workbooks** (interactive tools for proactive, analyst-driven investigation), **entity behavior analytics** (baseline-deviation detection for users and other entities), and **SOAR playbooks** (Logic Apps workflows, Section 42, triggered automatically or manually in response to alerts/incidents).

## 2. Why It Exists / Problem It Solves

A Log Analytics workspace full of correlated data (Section 92.4) is necessary but not sufficient — without something actively watching that data and turning matches into actionable, prioritized work items, a SOC analyst would need to manually run ad hoc KQL queries around the clock to notice anything, which doesn't scale past a trivially small environment. Analytics rules solve the "continuously and automatically watch for known-bad patterns" problem. But not every threat is a pattern someone has already written a rule for — genuinely novel or slow, low-and-slow attacks are often only found by an experienced analyst proactively exploring the data with hypotheses of their own, which is what hunting queries, workbooks, and entity behavior analytics exist to support. And detection alone — even excellent detection — leaves the actual response (containing the threat, gathering more context, notifying the right people) as manual work unless it's automated via SOAR playbooks, built on the exact same Logic Apps engine already covered in Section 42 for general workflow automation, now applied specifically to security response.

---

## 3. Analytics Rules

### 3.1 Scheduled Analytics Rules

**Definition:** the most common analytics rule type — a KQL query run on a defined schedule (e.g., every 5 minutes, looking back over a defined lookback period) against the Sentinel workspace's data; any results returned by the query generate an **incident** (or are grouped into an existing one, 93.3.5).

**How it works conceptually:** the rule author writes a KQL query expressing the specific detection logic (e.g., "more than N failed sign-ins from a single IP in the lookback window," directly extending the illustrative query from Section 92.8), sets a query frequency and lookback period, and configures how matching results should be grouped into incidents, their severity, and which entities (accounts, IP addresses, hosts) should be extracted from the results for downstream investigation and correlation.

### 3.2 Near-Real-Time (NRT) Analytics Rules

**Definition:** a rule variant evaluated continuously (effectively per-event, rather than on a fixed polling schedule) against a constrained set of supported data sources — trading some of the flexibility of a full scheduled-rule KQL query for materially lower detection latency, appropriate for scenarios where even a five-minute scheduled-rule delay is unacceptable.

⚠️ NRT rules support a narrower, evolving subset of KQL operators and data sources than full scheduled rules — verify current NRT capability and supported source coverage against documentation before assuming any scheduled-rule query can be trivially converted to an NRT rule.

### 3.3 Fusion Rules

**Definition:** a built-in, Microsoft-maintained correlation capability using machine learning to combine multiple, individually low-fidelity signals (each potentially unremarkable in isolation) across different data sources into a single, higher-confidence incident representing a probable multi-stage attack — directly addressing the scenario introduced in Section 92.2 (individually low-signal events that only become meaningful when correlated together).

**Why it matters:** Fusion rules are not something an analyst authors — they're pre-built correlation logic Microsoft maintains and updates, providing out-of-the-box detection for known multi-stage attack patterns (e.g., a specific sequence of reconnaissance-then-lateral-movement-then-exfiltration behavior) without requiring every organization to independently discover and author that correlation logic themselves.

### 3.4 Microsoft Security Rule Templates

Sentinel ships with a large, continuously updated library of **rule templates** — pre-authored analytics rules for common attack patterns against specific connected data sources (e.g., a template detecting a specific Entra ID sign-in risk pattern, or a template for a specific known attack technique against a connected firewall's logs) — that can be enabled directly or customized, substantially reducing the effort of building detection coverage from a blank slate. ⚠️ The specific template catalog and its coverage evolves continuously — periodically reviewing newly available templates against connected data sources is a genuine, recurring SOC maintenance task, not a one-time setup step.

### 3.5 Incidents — Grouping Alerts Into Actionable Work Items

**Definition:** an **incident** is Sentinel's unit of analyst work — one or more related **alerts** (individual rule matches) grouped together (by shared entities, time proximity, or explicit rule configuration) into a single item with a status (New/Active/Closed), severity, and assigned owner, so an analyst investigates one coherent incident rather than a disconnected pile of individual alerts that may actually represent the same underlying attack.

---

## 4. KQL-Based Detection Queries — Worked Example

```kql
let riskyIPs = SigninLogs
| where TimeGenerated > ago(1h)
| where ResultType != "0"
| summarize FailedCount = count() by IPAddress
| where FailedCount > 20;
SigninLogs
| where TimeGenerated > ago(1h)
| where ResultType == "0"
| join kind=inner riskyIPs on IPAddress
| project TimeGenerated, UserPrincipalName, IPAddress, FailedCount
```

**Purpose:** a two-stage detection — first identifying IP addresses responsible for a high volume of failed sign-ins (a likely brute-force source, `riskyIPs`), then finding any _successful_ sign-in from one of those same IP addresses within the same window — a materially higher-confidence "possible successful brute-force compromise" pattern than either failed-attempt volume or a single successful sign-in would indicate alone. This kind of two-stage, entity-joined query is a common, realistic shape for a genuinely useful analytics rule, well beyond a single flat `where` filter.

## 5. Threat Hunting

### 5.1 Hunting Queries

**Definition:** KQL queries authored (by Microsoft, as templates, or by an organization's own analysts) specifically for **proactive, hypothesis-driven investigation** rather than continuous automated alerting — an analyst runs a hunting query manually when investigating a specific hypothesis ("did anyone in the last 30 days access this specific sensitive dataset from an unusual location") that isn't (yet) codified as a standing analytics rule.

### 5.2 Bookmarks

**Definition:** a saved reference to a specific, interesting result found during hunting — allowing an analyst to mark and return to a specific finding, and to promote a bookmark directly into a new incident if the finding turns out to be genuinely actionable, connecting ad hoc hunting work back into the same incident-management workflow as automated rule detections.

### 5.3 Notebooks

Sentinel supports Jupyter notebook-based hunting for more complex, code-driven investigation (using Python libraries for data analysis directly against workspace data) — appropriate for genuinely sophisticated investigative work (e.g., statistical anomaly detection an analyst is building themselves) beyond what a single KQL query comfortably expresses.

### 5.4 Workbooks

**Definition:** interactive, dashboard-style visualizations built on the same underlying visualization capability referenced in Section 92.12 — Sentinel ships built-in workbooks for common scenarios (e.g., an overview of sign-in activity, or a MITRE ATT&CK coverage workbook referenced further in Section 95.5) and supports fully custom workbooks tailored to an organization's specific monitoring needs.

## 6. Entity Behavior Analytics (UEBA)

**Definition:** User and Entity Behavior Analytics establishes a learned behavioral baseline for entities (primarily user accounts, but also hosts and IP addresses) — typical sign-in times, typical locations, typical resource-access patterns — and flags activity deviating meaningfully from that baseline, surfacing an **anomaly** that may not match any specific authored analytics rule pattern but is nonetheless behaviorally unusual for that specific entity.

**Why it matters:** UEBA catches the class of threat that pattern-based analytics rules structurally cannot — a legitimate credential being used in a way that doesn't match any known "bad" signature (e.g., a correctly-authenticated user account, using its normal, valid credentials, but at 3 AM from a country the account has never been used from before) — directly complementing rule-based detection rather than replacing it.

---

## 7. SOAR Playbooks — Built on Logic Apps (Section 42)

### 7.1 Definition

**Definition:** a Sentinel **playbook** is a Logic App (Section 42) with a Sentinel-specific trigger (an alert being created, an incident being created or updated) that can be invoked automatically (via an automation rule, Section 94.3) or manually by an analyst, performing enrichment, containment, or notification actions using the same Logic Apps connector ecosystem and workflow-designer concepts already established in Section 42.

### 7.2 Why Logic Apps, Specifically

🔑 **Key Takeaway:** Sentinel deliberately reuses Logic Apps as its SOAR automation engine rather than providing a separate, security-specific workflow builder — meaning everything already covered in Section 42 (the visual designer, the connector ecosystem spanning hundreds of services, managed identity-based authentication for connector actions) applies directly to authoring a security playbook; a team already comfortable building general business-process Logic Apps has almost all the skill needed to author a Sentinel playbook, with the only genuinely new concept being the Sentinel-specific trigger types and the alert/incident schema those triggers expose.

---

## 8. Comparison — Analytics Rule Types

| Rule Type                    | Latency                            | Flexibility                                                      | Typical Use                                                                    |
| ---------------------------- | ---------------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Scheduled                    | Minutes (per configured frequency) | Full KQL expressiveness                                          | The general-purpose default for most custom detection logic                    |
| Near-Real-Time (NRT)         | Near-immediate                     | Constrained KQL subset, limited source coverage                  | High-urgency detections where scheduled-rule latency is unacceptable           |
| Fusion                       | Near-immediate, ML-driven          | Not author-configurable — Microsoft-maintained correlation logic | Multi-stage attack patterns spanning several individually low-fidelity signals |
| Microsoft Security templates | Varies by template                 | Enable-as-is or customize                                        | Fast, low-effort baseline detection coverage for well-known attack patterns    |

🎯 **Interview Tip:** a frequently tested nuance is that **Fusion rules are not something you author** — candidates who describe Fusion as "a rule type you write like any other" are missing the point; its value is specifically that Microsoft has pre-built the multi-signal correlation logic for known attack chains, something individual organizations would otherwise have to discover and encode themselves, one at a time, through hard-won incident experience.

---

## 9. Architecture Diagram

```
Log Analytics Workspace (Sentinel-enabled, Section 92.4)
        │
        ├── Scheduled Analytics Rules ──┐
        ├── NRT Analytics Rules ────────┤
        └── Fusion (ML correlation) ────┤
                                        ▼
                                   Alerts ──► grouped into ──► Incidents
                                                                    │
                        ┌───────────────────────────────────────────┤
                        ▼                                           ▼
              Manual Analyst Review                     Automation Rule (Section 94)
              (Hunting queries, Workbooks,                          │
               Bookmarks, UEBA — 93.5-93.6)                         ▼
                                                          SOAR Playbook (Logic App,
                                                          Section 42) — enrichment,
                                                          containment, notification
```

## 10. Configuration & Hands-On Example

**Creating a scheduled analytics rule via Azure CLI:**

```bash
az sentinel alert-rule scheduled create \
  --resource-group rg-security \
  --workspace-name law-sentinel-prod \
  --rule-id "brute-force-success-rule" \
  --display-name "Successful Sign-in From Brute-Force Source IP" \
  --severity High \
  --enabled true \
  --query "$(cat brute_force_query.kql)" \
  --query-frequency PT5M \
  --query-period PT1H \
  --trigger-operator GreaterThan \
  --trigger-threshold 0 \
  --tactics CredentialAccess InitialAccess
```

- **Purpose:** deploys the two-stage detection query from Section 93.4 as a standing, automatically-run scheduled analytics rule, generating an incident whenever it matches.
- **Important arguments explained individually:**
  - `--query-frequency PT5M` / `--query-period PT1H` — ISO 8601 duration values controlling how often the rule runs (every 5 minutes) and how far back each run looks (a rolling 1-hour window) — these two values together determine both detection latency and the risk of missing events near a window boundary; a period shorter than the frequency risks gaps, while an excessively long period relative to frequency increases query cost from repeatedly re-scanning overlapping data.
  - `--tactics CredentialAccess InitialAccess` — tags the rule with MITRE ATT&CK tactic categories (directly feeding Section 95.5's ATT&CK coverage-mapping material), letting a SOC later assess detection coverage across the ATT&CK framework rather than only per individual rule.
  - `--trigger-threshold 0` combined with `GreaterThan` — creates an incident on any non-empty query result; a higher threshold could instead require, e.g., multiple matching rows before triggering, appropriate for noisier detection logic prone to occasional benign matches.
- **Common error:** setting `--query-frequency` and `--query-period` to the same or nearly-identical values without accounting for query execution and ingestion latency — data arriving slightly late relative to the rule's run time can fall just outside the lookback window and be silently missed on that run (though often still caught on the next), a subtle timing gap worth explicitly accounting for rather than assuming perfectly synchronized real-time evaluation.

## 11. Production & Enterprise Usage

Mature Sentinel deployments maintain analytics rule coverage deliberately mapped against the MITRE ATT&CK framework (Section 95.5), reviewed periodically against the evolving Microsoft Security rule template catalog (93.3.4) rather than treating initial rule deployment as a one-time setup task — new templates and Fusion correlation coverage are added by Microsoft on an ongoing basis, and a SOC that never revisits its enabled-rule set drifts toward stale coverage relative to current known attack techniques.

## 12. Security Considerations

- Analytics rules and hunting queries themselves can reveal sensitive operational detail about how an organization detects threats — access to rule logic and hunting-query history should be scoped via the same workspace RBAC principles established in Section 92.10, since an attacker with visibility into detection logic could deliberately evade it.
- UEBA baselines take time to establish meaningfully (an entity's "normal" behavior needs a representative observation period) — newly onboarded entities or recently changed roles/responsibilities can produce a period of elevated false-positive anomaly flags until the baseline catches up; this is expected behavior, not a UEBA malfunction, and should be accounted for when triaging anomaly alerts for genuinely new users or systems.

## 13. Performance Considerations

Scheduled rules with a short query frequency against a very high-volume, unfiltered table can themselves become a meaningful driver of workspace query cost/load at scale — rule authors should apply the same KQL performance discipline from Section 51 (filtering early, avoiding unnecessarily broad time ranges) when writing detection logic, not only when writing ad hoc investigative queries.

## 14. Monitoring

Sentinel's own analytics-rule health and incident-volume workbooks (93.5.4) should themselves be monitored — a rule silently failing to run (due to a query syntax issue introduced by an edit, or an underlying data-connector outage upstream, Section 92.13) produces a dangerous, invisible detection gap that looks identical to "everything is fine, nothing bad is happening" from an analyst's perspective, unless rule execution health is itself actively tracked.

## 15. Troubleshooting

| Symptom                                                                                   | Likely Cause                                                                                                                                       | Fix                                                                                                                                                                |
| ----------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| A scheduled rule that previously fired regularly stops generating incidents               | Underlying data connector or source stopped forwarding data (Section 92.13), or a rule edit introduced a query logic error                         | Verify source data is still arriving in the workspace via a direct KQL query against the underlying table; review recent rule edit history                         |
| Analysts report alert fatigue from an excessive volume of low-value incidents             | Rule threshold set too low/sensitive, or incident-grouping logic not consolidating related alerts effectively                                      | Tune rule threshold and grouping/entity-mapping configuration; consider suppressing or tuning down rules with a poor true-positive rate                            |
| UEBA flags a large volume of anomalies for a specific team shortly after a reorganization | Baseline behavior genuinely changed (new roles, new resource access patterns) faster than UEBA's learned baseline has adapted                      | Expected transient behavior; allow the baseline observation period to re-establish, and communicate the expected temporary noise to analysts triaging these alerts |
| A playbook configured on an analytics rule never actually runs                            | Playbook not correctly linked via an automation rule (Section 94.3), or the playbook's managed identity lacks required permissions for its actions | Verify the automation rule linking the analytics rule/incident trigger to the specific playbook; verify playbook managed identity permissions                      |

## 16. Interview Questions — Section 93

### 🎯 Intermediate

**Q: What's the difference between a Sentinel analytics rule and a hunting query, and when would you use each?**

_Model answer:_ An analytics rule runs automatically on a schedule (or near-real-time) and generates incidents whenever its query matches — it's the standing, always-on detection mechanism for known patterns. A hunting query is run manually by an analyst investigating a specific hypothesis that isn't (yet) codified as a standing rule — it's proactive, exploratory investigation rather than continuous automated alerting. You'd use an analytics rule for well-understood, recurring threat patterns you want detected automatically at all times, and hunting queries when investigating something novel, or validating whether a specific hypothesis-driven pattern is worth eventually promoting into a standing analytics rule.

_What the interviewer is probing:_ clear understanding of the automated-detection vs. proactive-investigation distinction, and the natural workflow of a good hunting finding eventually becoming a codified rule.

### 🎯 Senior/Architect

**Q: Your SOC is being overwhelmed with low-value incident volume from one particular scheduled analytics rule, but the security team is nervous about simply raising its threshold or disabling it, worried about missing a genuine detection. How do you approach this?**

_Model answer:_ First, I'd quantify the actual true-positive rate of the rule over a representative historical period — reviewing closed incidents generated by that specific rule to establish what fraction were genuinely actionable versus benign noise, rather than making a threshold change based on gut feel alone. If the true-positive rate is genuinely low, I'd look at whether the underlying detection logic itself needs refinement (e.g., adding an additional join or filter condition to the KQL, similar in spirit to the two-stage brute-force-plus-successful-sign-in pattern from Section 93.4, which is meaningfully higher-confidence than either signal alone) before simply raising a numeric threshold, since a logic refinement can reduce noise without proportionally reducing genuine detection coverage the way a blunt threshold increase risks doing. I'd also check whether this rule overlaps meaningfully with a Fusion rule's correlation coverage (93.3.3) or a Microsoft Security template's more refined version of similar logic (93.3.4) — it's possible a better-maintained, Microsoft-authored alternative already exists and should replace a noisier, custom-authored rule doing roughly the same job less precisely. Finally, I'd treat any threshold or logic change as something to validate against recent known-genuine incidents (if any exist in history) to confirm the change wouldn't have caused a real detection to be missed, before rolling it out, and I'd document the tuning decision and its rationale for future reference, since alert-fatigue tuning decisions made without documented reasoning tend to get silently re-litigated (or worse, silently reverted) by a future analyst unaware of why the current configuration exists.

_What the interviewer is probing:_ a data-driven, non-reckless approach to alert tuning — measuring before changing, preferring logic refinement over blunt threshold changes where possible, checking for better-maintained alternatives, and validating against historical ground truth rather than guessing.

## 17. Common Misconceptions

- **"Fusion rules are just another rule type you write yourself, like a scheduled rule."** False — Fusion is Microsoft-maintained, ML-driven multi-signal correlation logic that isn't author-configurable in the same way as a scheduled or NRT rule; its value is specifically that this correlation logic doesn't need to be independently built by each organization.
- **"UEBA anomaly flags are always meaningful security findings."** False — UEBA baselines take time to establish, and legitimate changes (a reorganization, a role change, a new work pattern) can produce a temporary burst of anomaly flags that reflect a genuinely changed baseline, not an actual threat; this is expected, not a system malfunction.
- **"A Sentinel playbook is a fundamentally different technology from a general-purpose Logic App."** False — a Sentinel playbook is precisely a Logic App (Section 42) with a Sentinel-specific trigger; the underlying designer, connector ecosystem, and authoring skill are identical to any other Logic App.

## 18. Key Takeaways

- 🔑 Scheduled analytics rules (author-written KQL on a timer), NRT rules (lower-latency, constrained), and Fusion rules (Microsoft-maintained ML correlation of multiple low-fidelity signals) are three structurally distinct detection mechanisms, each with different trade-offs in latency, flexibility, and authoring effort.
- 🔑 Alerts are grouped into incidents — the actual unit of analyst work — so related detections are investigated together rather than as a disconnected pile of individual alerts.
- 🔑 Hunting queries, bookmarks, workbooks, and notebooks support proactive, analyst-driven investigation for threats without a standing rule, complementing rather than replacing automated detection.
- 🔑 Entity Behavior Analytics detects baseline deviation for legitimately-authenticated entities, catching a class of threat (misuse of valid credentials) that pattern-based rules structurally cannot.
- 🔑 SOAR playbooks are Logic Apps (Section 42) with a Sentinel-specific trigger — the entire Logic Apps connector ecosystem and authoring skillset transfers directly, with only the trigger type and alert/incident schema being genuinely new.

## 19. Related Concepts (Next Up)

Section 94 completes the SOAR story by covering exactly how playbooks are wired to actually run automatically — **automation rules**, the specific containment/enrichment/notification playbook design patterns a mature SOC relies on, and how this automated-response layer integrates with the Defender for Cloud alert-routing material already covered in Section 55.7.
