# Section 73 (Part 11): Chronicle Deep Dive & Detection Engineering

## 1. Definition

**Plain language:** [Section 72](./Section-72-Part11-Chronicle-SIEM-Fundamentals.md) introduced Chronicle as the place where all your security logs land and get normalized. This section is about what you actually _do_ with that normalized data day to day: writing rules that automatically flag suspicious activity, using Google's pre-built detection content instead of writing everything from scratch, ranking which alerts deserve attention first, and pulling in outside threat intelligence about known-bad actors so your detections are informed by more than just your own logs.

**Precise:** Chronicle detection engineering covers writing and tuning **YARA-L** rules against the Unified Data Model (UDM), subscribing to Google-maintained **curated detections** (pre-built, continuously updated rule packs), using **entity risk scoring** to prioritize which users/hosts/IPs need investigation first, enriching detections with **Mandiant threat intelligence**, and feeding Security Command Center ([Section 39](../Part5/Section-39-Part5-Security-Command-Center.md)) findings into Chronicle as an additional detection input.

## 2. Why It Exists / Problem It Solves

A SIEM that only ingests and normalizes logs ([Section 72](./Section-72-Part11-Chronicle-SIEM-Fundamentals.md)) is a very expensive, very fast search engine — useful for investigation, but not proactive. The problem detection engineering solves is turning that normalized data into automatic, prioritized alerts _before_ an analyst goes looking. Three specific gaps drive the features in this section:

1. **Every organization writing every rule from scratch doesn't scale.** Techniques like credential-stuffing patterns or common malware command-and-control beaconing are common across nearly all organizations. Requiring every Chronicle customer's security team to independently research and author a detection for each of these is wasteful duplication — curated detections exist so Google's own detection engineers author and continuously tune this baseline content once, centrally.
2. **A flood of true-but-low-value alerts is as bad as no alerts.** A rule firing correctly on a real anomaly is still a problem if it fires 500 times a day with no way to tell which of the 500 matters most. Entity risk scoring exists to rank alerts and entities by aggregate risk, not just surface a flat, equally-weighted list.
3. **Your own logs don't know what a known-bad IP or malware hash looks like.** A firewall log showing a connection to `203.0.113.45` is unremarkable in isolation. Mandiant threat intelligence exists to tell Chronicle that IP is a known command-and-control server, turning an unremarkable log line into a high-confidence detection.

## 3. Core Concepts

### 3.1 Writing Multi-Event YARA-L Rules

[Section 72](./Section-72-Part11-Chronicle-SIEM-Fundamentals.md).3.4 showed a minimal two-event YARA-L rule. Real detection engineering typically chains more conditions and uses **placeholders** and **outcome variables** to enrich the alert itself:

```yara-l
rule impossible_travel_login {
  meta:
    author = "detection-eng"
    severity = "Medium"
    description = "Same user authenticates from two geographically distant IPs within 30 minutes"
    mitre_technique = "T1078 - Valid Accounts"

  events:
    $login1.metadata.event_type = "USER_LOGIN"
    $login1.security_result.action = "ALLOW"
    $login2.metadata.event_type = "USER_LOGIN"
    $login2.security_result.action = "ALLOW"
    $login1.principal.user.userid = $login2.principal.user.userid
    $login1.principal.ip != $login2.principal.ip
    $login1.metadata.event_timestamp.seconds < $login2.metadata.event_timestamp.seconds

  match:
    $login1.principal.user.userid over 30m

  outcome:
    $risk_score = max(65)
    $source_ips = array_distinct($login1.principal.ip, $login2.principal.ip)

  condition:
    $login1 and $login2
}
```

- **`outcome`** is the section that did not appear in the [Section 72](./Section-72-Part11-Chronicle-SIEM-Fundamentals.md) minimal example — it lets a rule compute and attach values (a risk contribution, a deduplicated list of IPs involved) directly onto the generated detection, so an analyst opening the alert sees enriched context immediately rather than re-deriving it from raw events.
- **MITRE ATT&CK tagging** in `meta` (shown here as `mitre_technique`) is a strong production convention — it lets SOC dashboards ([Section 76](./Section-76-Part11-SOC-Patterns.md)) and reporting roll detections up by adversary technique rather than by rule name alone.

### 3.2 Curated Detections

**Definition:** curated detections are pre-built, Google-authored and Google-maintained YARA-L rule packs covering common attacker techniques, mapped to MITRE ATT&CK, that a Chronicle customer subscribes to and enables rather than authoring independently.

- Organized into **rule sets** by theme (e.g., a rule set for Windows-based lateral movement, one for cloud identity abuse), each independently enabled or disabled.
- Google continuously tunes and updates curated detection logic as attacker techniques evolve, so the rule content improves without the customer's own detection team having to track every new technique themselves.
- The standard production pattern is: **enable relevant curated detection rule sets first**, then author custom YARA-L rules only for organization-specific logic that curated content cannot know about (internal naming conventions, org-specific expected admin behavior, custom application logs).

> ⚠️ **Common mistake:** Treating curated detections and custom rules as mutually exclusive. Mature deployments run both — curated detections provide broad, continuously updated baseline coverage; custom rules cover the organization-specific context Google cannot know in advance (e.g., "this service account normally only ever touches project X, alert if it touches anything else").

### 3.3 Entity Risk Scoring

**Definition:** entity risk scoring is Chronicle's mechanism for aggregating signal across multiple detections, alerts, and context sources into a single, continuously updated risk score per entity (a user, host, or IP address), so analysts can triage by "which entities are riskiest right now" rather than working a flat, unranked alert queue.

- A single detection firing once on an otherwise-quiet user contributes modestly to that user's risk score. The same user triggering several distinct detections in a short window compounds the score — reflecting that a pattern of multiple suspicious events on one entity is a stronger signal than any single event alone.
- Risk scores decay over time absent new signal, so an entity's score reflects _recent_ behavior rather than accumulating indefinitely from stale, long-resolved incidents.
- This is the mechanism SOC tiered triage ([Section 76](./Section-76-Part11-SOC-Patterns.md)) is built on top of: Tier 1 analysts typically start from the highest-risk-scored entities rather than scanning every individual detection chronologically.

### 3.4 Mandiant Threat Intelligence Integration

**Definition:** Mandiant is Google's threat intelligence and incident response organization; its intelligence feeds — indicators of compromise (IOCs), threat actor profiles, and campaign tracking — are natively integrated into Chronicle so that raw UDM events are automatically enriched and matched against known-bad indicators.

- **IOC matching** happens automatically: when a UDM event contains an IP, domain, or file hash that matches a Mandiant-tracked indicator, Chronicle surfaces that match without requiring a custom YARA-L rule to look it up.
- **Threat actor and campaign context** is attached to matches — a detection is not just "this IP is bad," it can be "this IP is associated with threat actor group X's known campaign Y," giving analysts far more actionable context for prioritization and response than a bare indicator match.
- This integration is the direct analog to how the entity risk scoring in 73.3.3 gets some of its highest-confidence signal: a confirmed Mandiant IOC match is a strong, well-attributed contributor to an entity's risk score, distinct from a heuristic pattern match from a custom rule.

### 3.5 Security Command Center as a Chronicle Input

Security Command Center ([Section 39](../Part5/Section-39-Part5-Security-Command-Center.md)) findings — misconfigurations, vulnerabilities, and GCP-resource-scoped threat detections — can themselves be routed into Chronicle as an additional UDM event source. This closes the loop described in [Section 72](./Section-72-Part11-Chronicle-SIEM-Fundamentals.md).8: SCC and Chronicle are not redundant, they are layered. SCC's GCP-resource-scoped findings become one more correlatable signal inside Chronicle's broader cross-source view — a SCC finding that a service account key was exposed, correlated inside Chronicle against subsequent anomalous API activity from that same service account logged elsewhere, is a stronger combined signal than either finding alone.

## 4. Detection Pipeline Diagram

```
   Raw UDM Events (Section 72)
              │
              ▼
   ┌───────────────────────────────────────────────────────┐
   │              Detection Evaluation Layer               │
   │                                                       │
   │  Custom YARA-L Rules   Curated Detections   IOC Match │
   │  (org-specific logic)  (Google-maintained)  (Mandiant)│
   │            │                  │                  │    │
   └────────────┼──────────────────┼──────────────────┼────┘
                │                  │                  │
                └──────────────────┴──────────────────┘
                                   ▼
                     ┌───────────────────────────┐
                     │  Entity Risk Scoring      │
                     │  (aggregates per entity)  │
                     └────────────┬──────────────┘
                                  ▼
                     ┌───────────────────────────┐
                     │  Prioritized Alert Queue  │
                     └────────────┬──────────────┘
                     ┌────────────┴──────────────┐
                     ▼                            ▼
        Automated Response (Section 75)   SOC Triage (Section 76)

   SCC Findings (Section 39) ──────► feed in as additional UDM events
```

## 5. Comparison: Chronicle Detection Engineering vs. Azure Sentinel

| Aspect                      | Chronicle (GCP)                                                             | Microsoft Sentinel (Azure)                                                                                            |
| --------------------------- | --------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Custom rule language        | YARA-L — event/match/condition/outcome structure, extended from YARA syntax | KQL-based **analytics rules** — a scheduled or near-real-time KQL query against Log Analytics tables                  |
| Pre-built detection content | **Curated detections** — Google-authored, continuously maintained rule sets | **Analytics rule templates** and **Content Hub solutions** — Microsoft- and partner-authored, installed per workspace |
| Investigation visualization | UDM-based search and entity graphs                                          | **Workbooks** — customizable dashboards, plus investigation graph views                                               |
| Risk prioritization         | Native entity risk scoring, aggregating across detections automatically     | **UEBA (User and Entity Behavior Analytics)** module provides comparable entity risk insights, with some setup        |
| Threat intel source         | Native Mandiant integration                                                 | Microsoft threat intelligence feeds plus partner/community feeds via Content Hub                                      |
| Closest conceptual mapping  | Curated detections ≈ analytics rule templates; entity risk scoring ≈ UEBA   | —                                                                                                                     |

> 💡 **Interview-relevant nuance:** Both platforms converge on the same underlying idea — ship pre-built detection content instead of expecting every customer to author everything, and provide entity-level risk aggregation on top of individual alerts. The differentiator worth naming in an interview is _provenance_: Chronicle's curated detections and Mandiant intel come from a single, tightly integrated vendor pipeline (Google/Mandiant), whereas Sentinel's Content Hub is a more open marketplace model spanning Microsoft and many third-party publishers — a trade-off between curated consistency and broader ecosystem breadth.

## 6. Hands-On Example: Enabling a Curated Detection Rule Set via `gcloud`

**Purpose:** Chronicle's curated detections and rule management are primarily configured via the Chronicle console or its dedicated API, but organizations that manage detection-as-code often drive Chronicle configuration through automation. This example shows retrieving Chronicle-forwarded findings via the Security Command Center API surface, illustrating how SCC findings (73.3.5) are queried before being routed toward Chronicle correlation.

```bash
gcloud scc findings list organizations/123456789012 \
  --filter='category="MANDIANT_IOC_MATCH" AND state="ACTIVE"' \
  --format='table(finding.resourceName, finding.category, finding.severity)'
```

**Expected output:**

```
RESOURCE_NAME                                          CATEGORY            SEVERITY
//compute.googleapis.com/projects/prod-1/instances/...  MANDIANT_IOC_MATCH  HIGH
//compute.googleapis.com/projects/prod-1/instances/...  MANDIANT_IOC_MATCH  MEDIUM
```

- **Purpose of the filter:** narrows the SCC findings list specifically to findings that originated from a Mandiant IOC match surfaced through the SCC/Chronicle integration, rather than the full unfiltered findings stream — useful for verifying threat-intel-driven detections are actually reaching SCC as expected.
- **Common error:** assuming YARA-L rule authoring itself can be done via `gcloud` — rule creation, curated detection enablement, and risk scoring configuration are managed through the Chronicle console/API, not the `gcloud` CLI; `gcloud` is relevant here only for the GCP-side SCC finding correlation shown above.

> 💡 **Tip:** Detection-as-code workflows for YARA-L rules (version-controlling rule text, deploying via the Chronicle API in CI/CD) are a common maturity marker in production SOCs — treating detection rules with the same rigor as application code (code review, testing against sample UDM events, staged rollout) rather than editing them ad hoc in a console.

## 7. Production & Enterprise Usage

- **Curated-first, custom-second rule strategy.** Mature deployments enable relevant curated detection rule sets as the baseline and reserve custom YARA-L authoring effort for genuinely organization-specific logic, avoiding duplicated effort re-inventing detections Google already maintains.
- **Regular tuning against false-positive rate.** New custom rules are typically deployed in a "test"/silent mode first, observed against real traffic to measure false-positive rate, and only promoted to actively alerting once tuned — deploying straight to production alerting is a common source of analyst alert fatigue.
- **Risk score thresholds drive automation triggers.** Organizations with automated response ([Section 75](./Section-75-Part11-Automated-Incident-Response.md)) commonly gate automation on entity risk score crossing a threshold, not on any single detection firing alone — reducing the chance a single noisy rule triggers an aggressive automated action.

## 8. Common Misconceptions

- **Misconception:** "Curated detections replace the need for custom rules entirely." Curated content covers common, broadly applicable techniques; it cannot know an organization's specific expected behavior (which service accounts normally touch which resources, internal naming conventions), which is exactly the gap custom rules fill.
- **Misconception:** "Entity risk scoring is just a fancier way of counting alerts per entity." It aggregates across multiple signal types (rule detections, Mandiant IOC matches, SCC findings) with decay over time, producing a materially different and more current signal than a raw alert count would.
- **Misconception:** "Mandiant integration means Chronicle does threat hunting for you automatically." IOC matching is automatic, but proactive threat hunting ([Section 76](./Section-76-Part11-SOC-Patterns.md)) — analysts actively querying UDM data for patterns not yet covered by any existing rule or known indicator — remains a distinct, human-driven activity Mandiant intelligence supports but does not replace.

## 9. Interview Questions

**🎯 Beginner:** _What is the difference between a curated detection and a custom YARA-L rule?_
**Model answer:** A curated detection is a pre-built, Google-authored and continuously maintained rule that a customer enables, covering common attacker techniques broadly applicable across organizations. A custom YARA-L rule is authored by the organization's own detection engineers to cover logic specific to that organization — internal naming conventions, expected service account behavior, or custom application logs — that generic curated content cannot anticipate.

**🎯 Intermediate:** _Why does entity risk scoring matter for SOC operations, beyond just having a list of alerts?_
**Model answer:** A flat alert list treats every detection as equally worth investigating first, which does not reflect reality — a user with one low-severity anomaly is a lower priority than a user with several correlated detections plus a confirmed Mandiant IOC match. Entity risk scoring aggregates signal across detections, IOC matches, and other context per entity with decay over time, giving analysts a prioritized, continuously current view of which entities most warrant investigation right now, which is the foundation tiered SOC triage ([Section 76](./Section-76-Part11-SOC-Patterns.md)) is built on.

**🎯 Senior/Architect:** _Your detection engineering team wants to reduce alert fatigue without silently missing real incidents. Walk through how you'd use Chronicle's features to do this._
**Model answer:** I would first separate the two failure modes: too many low-value alerts, and risk of missing real ones, because they pull in opposite directions if handled carelessly. For volume reduction, I'd audit custom rules for ones deployed straight to active alerting without a tuning period, move new rules through a silent/test phase to measure false-positive rate before promotion, and lean more heavily on curated detections, which Google continuously tunes, rather than maintaining marginal custom rules with high false-positive rates. Rather than deleting noisy rules outright — which risks the missed-incident failure mode — I would use entity risk scoring as the triage layer: keep the rules firing, but ensure Tier 1 analysts ([Section 76](./Section-76-Part11-SOC-Patterns.md)) work from the risk-ranked entity view rather than a flat rule-firing log, so noisy-but-low-severity rules contribute proportionally to risk score without individually demanding investigation. I'd also confirm Mandiant IOC matches and SCC findings are correctly feeding into the same risk aggregation, since high-confidence external signal should outrank a purely heuristic pattern match, and periodically validate against known incident scenarios (red team exercises or past incident replay) that reducing noise has not caused any real technique to fall below the triage threshold.

## 10. Key Takeaways

- 🔑 YARA-L rules can use `outcome` blocks to attach computed context (risk contribution, deduplicated fields) directly to a generated detection, beyond the minimal `events`/`match`/`condition` structure introduced in [Section 72](./Section-72-Part11-Chronicle-SIEM-Fundamentals.md).
- 🔑 Curated detections are Google-maintained, continuously updated rule content that should form the baseline of detection coverage, with custom rules reserved for organization-specific logic.
- 🔑 Entity risk scoring aggregates detections, Mandiant IOC matches, and other signal per entity with time decay, enabling risk-ranked triage instead of a flat alert queue — the foundation of SOC tiered triage in [Section 76](./Section-76-Part11-SOC-Patterns.md).
- 🔑 Mandiant threat intelligence provides native, automatic IOC matching and threat-actor/campaign context, distinct from and complementary to custom heuristic rule logic.
- 🔑 Security Command Center findings ([Section 39](../Part5/Section-39-Part5-Security-Command-Center.md)) can feed into Chronicle as an additional correlatable event source, making SCC and Chronicle complementary layers rather than redundant tools.
- 🔑 Chronicle's curated detections/Mandiant pairing is architecturally closest to Sentinel's analytics rule templates/Content Hub plus UEBA, differing mainly in vendor provenance (tightly integrated vs. open marketplace).

## 11. Related Concepts

Chronicle SIEM Fundamentals and the UDM ([Section 72](./Section-72-Part11-Chronicle-SIEM-Fundamentals.md)), Security Command Center ([Section 39](../Part5/Section-39-Part5-Security-Command-Center.md)), automated incident response acting on these detections ([Section 75](./Section-75-Part11-Automated-Incident-Response.md)), and SOC triage workflows built on entity risk scoring ([Section 76](./Section-76-Part11-SOC-Patterns.md)) all connect directly to the detection engineering practices covered here.
