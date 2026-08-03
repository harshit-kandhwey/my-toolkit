# Part 14, Section 2: Amazon Detective — Security Investigation

## 1. Definition

**Plain language:** §77's worked incident-investigation example showed an analyst manually chaining together CloudWatch, X-Ray, Config, and CloudTrail to piece together a root cause — a genuinely valuable but manually-intensive process. Security investigations specifically (was this account compromised, what did the attacker actually do) involve an even more complex web of relationships — which IAM principal called which API, from which IP, affecting which resources, over what time period — that's tedious and error-prone to reconstruct by hand from raw logs alone. Amazon Detective exists specifically to make this kind of security investigation faster, by automatically building and visualizing these relationships.

**Precise definition:** Amazon Detective is a security investigation service that automatically collects log data from CloudTrail, VPC Flow Logs, GuardDuty findings, and other sources, then uses machine learning and graph analysis to build a unified, interactive model of an account's behavior over time — resource relationships, API call patterns, network traffic patterns — letting a security analyst visually explore and query these relationships to investigate a potential security issue far faster than manually correlating raw logs across multiple services.

## 2. Why It Exists / Problem It Solves

- GuardDuty (§16) is excellent at _detecting_ a specific suspicious event — an anomalous API call, unusual network traffic — but a single detected finding is often just the entry point into a much larger investigation question: is this an isolated event, or part of a broader pattern; what else did this same IAM principal or IP address do around the same time; has this resource been involved in other flagged activity before?
- Answering those follow-up questions by manually querying raw CloudTrail logs, VPC Flow Logs, and GuardDuty history separately — the manual correlation approach described in §77's worked example — is genuinely time-consuming and requires the analyst to already have a good hypothesis about what to look for, since raw log querying doesn't inherently surface non-obvious relationships.
- Detective exists specifically to remove much of that manual correlation burden: it pre-builds the relationship graph (which principals interacted with which resources, over what time periods, at what volume) continuously in the background, so when an investigation begins, an analyst can immediately visually explore actual behavioral relationships rather than starting from raw logs and building that picture themselves from scratch.
- 🔑 **Key takeaway:** Detective doesn't detect new security issues the way GuardDuty does — it accelerates the _investigation_ of an issue once suspected (from GuardDuty, Macie, §121, or any other trigger), directly analogous to how §72's X-Ray accelerates the investigation of a _performance_ issue once an alarm has already indicated something is wrong — both are investigation-acceleration tools, not initial-detection tools, applied to different problem domains.

## 3. Prerequisites and Dependencies

- **CloudTrail** (§73) and **VPC Flow Logs** (§37): Detective's underlying data sources, ingested and correlated automatically once enabled.
- **GuardDuty** (§16): commonly the trigger prompting a Detective investigation — a GuardDuty finding is frequently where an investigation _starts_, with Detective used to explore _around_ that finding.
- **Amazon Macie** (§121): a Macie finding (unexpected sensitive data exposure) can similarly trigger a Detective investigation into how that exposure came to be and what else might be related.

## 4. Internal Working / Architecture & Components

### 4.1 The Behavior Graph

- Detective continuously ingests and processes CloudTrail, VPC Flow Log, and GuardDuty data, constructing a **behavior graph** — a graph-structured model where entities (IAM principals, EC2 instances, IP addresses, S3 buckets, and others) are nodes, and their observed interactions (API calls, network connections) are edges, weighted and timestamped based on actual observed activity.
- This graph is built continuously, in the background, independent of any specific active investigation — meaning when an analyst begins investigating a specific finding, the relevant relationship data has typically already been processed and is immediately explorable, rather than needing to be computed on-demand at investigation time (a meaningful difference from, for example, an ad hoc Athena query against raw CloudTrail data, §101, which computes its result fresh each time).
- 🔑 **Key takeaway:** this pre-computation is Detective's core value proposition — trading continuous background processing cost for dramatically faster investigation-time exploration, the same general "precompute for faster query-time performance" trade-off pattern seen in QuickSight's SPICE caching (§104 §4.1), here applied to security relationship data specifically.

### 4.2 Investigation Workflow — Starting From a Finding

- An investigation commonly begins from a specific trigger — a GuardDuty finding, a Macie finding, or a manually-identified entity of interest (a specific IAM principal, IP address, or resource) — and Detective provides a visual, interactive view of that entity's behavior graph neighborhood: what else did this principal do, what other resources did this IP address interact with, over what time range.
- An analyst can pivot from any entity to its related entities interactively — starting from a flagged API call, pivoting to the IAM principal that made it, then to every other resource that principal touched in the surrounding time window, then to whether any of those resources show their own separate suspicious activity — a fluid, exploratory investigation pattern that would require many separate, manually-constructed queries against raw logs to replicate.
- **Finding groups**: Detective can also identify and group related GuardDuty findings that appear connected (based on shared entities or behavior graph proximity) — surfacing that several seemingly-separate findings may actually represent one broader, coordinated pattern of activity, rather than requiring an analyst to manually notice that connection themselves.

### 4.3 Detective vs. Direct Log Querying (Athena)

- 🔑 **Key takeaway:** Detective and directly querying centralized logs via Athena (§101, against the Log Archive account's data, §117 §8) are complementary, not competing, investigation approaches — Detective excels at fast, visual, relationship-driven exploration when the investigation's shape isn't yet fully known ("what else is connected to this"), while direct Athena querying excels at precise, specific questions where the analyst already knows exactly what they're looking for ("show me every API call this specific principal made between these two exact timestamps") — a real investigation commonly uses both, starting broad and exploratory in Detective, then narrowing to precise verification via direct log queries.

## 5. Lifecycle / Workflow

1. Detective is enabled across an account or organization (commonly via delegated administration, §118, alongside GuardDuty and Macie), continuously building its behavior graph from CloudTrail, VPC Flow Log, and GuardDuty data in the background.
2. A trigger occurs — a GuardDuty finding, a Macie finding, or a manually-flagged concern — prompting an investigation.
3. An analyst opens Detective, starting from the triggering entity (a principal, resource, or IP address), and explores its behavior graph neighborhood — what else is connected, over what time range, at what pattern of activity.
4. The analyst pivots through related entities as the investigation's shape emerges, identifying the actual scope of the issue — isolated event, or broader pattern (potentially surfaced directly via finding groups, §4.2).
5. Once the investigation's findings are clear, the analyst moves to remediation and response (§124-125), informed by Detective's now-established picture of exactly what happened and what was affected.

## 6. Configuration

| Setting                                                        | Purpose                                                                                                                    |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Detective enablement scope (account/organization)              | Which accounts' data feeds the behavior graph — organization-wide enablement gives cross-account investigation visibility. |
| Data source integration (CloudTrail, VPC Flow Logs, GuardDuty) | Which underlying telemetry sources feed Detective's graph construction.                                                    |
| Delegated administrator account                                | The account from which Detective is operated organization-wide, following §118's delegation pattern.                       |

## 7. Commands / API (Full Documentation)

### 7.1 Enabling Detective

- **Purpose:** Begin building the behavior graph for an account/organization.
- **Syntax:**

```bash
aws detective create-graph
```

- **Practical example / expected output:** returns a graph ARN — the behavior graph begins ingesting available CloudTrail/VPC Flow Log/GuardDuty history and continues processing new activity going forward. Detective commonly requires some initial processing period before a full, richly-populated graph is available for investigation — verify current documentation for expected timelines.
- **Common errors:** enabling Detective without also having GuardDuty enabled (Detective's investigation value is significantly enhanced when GuardDuty findings are available as investigation entry points and for finding-group correlation, §4.2) — while Detective can operate on CloudTrail/VPC Flow Log data alone, its full intended value depends on the broader security-service ecosystem being in place.

### 7.2 Exploring an Entity (Conceptual — Primarily a Console/Visual Experience)

- Detective's core investigative experience is fundamentally visual and interactive (graph exploration, pivoting between related entities) rather than a typical scripted API workflow — the API surface primarily supports enablement, configuration, and programmatic retrieval of specific summary data, while the actual exploratory investigation work happens through Detective's console interface.
- **Production usage:** an analyst starting from a GuardDuty finding can navigate directly into Detective's console view of the specific IAM principal or resource involved, immediately seeing that entity's broader behavior graph neighborhood without constructing any queries manually — this direct GuardDuty-to-Detective pivot is one of the most common real investigation entry points.

## 8. Hands-On Example — From Finding to Full Picture

```text
1. GuardDuty finding: "IAM principal payments-app-role made an unusual
   API call pattern from an unfamiliar IP address"

2. Analyst pivots directly into Detective, starting from
   payments-app-role

3. Detective's behavior graph immediately shows:
   - Every API call this role made in the surrounding 48 hours
   - Every resource it interacted with (not just the one flagged call)
   - The specific IP address's OTHER activity across the account --
     revealing it also touched TWO OTHER IAM roles in the same window

4. Analyst pivots to those two other roles, discovering one of them
   made an unusual S3 GetObject call against a sensitive bucket
   shortly after -- a connection GuardDuty's ORIGINAL finding never
   flagged on its own, since it only flagged the FIRST role's activity

5. What started as "investigate one flagged API call" becomes,
   within minutes of graph exploration, "this appears to be a broader
   compromise touching three IAM roles and a sensitive S3 access" --
   informing a much more accurately-scoped incident response (§124)
   than the original single finding alone would have suggested
```

This demonstrates Detective's core value directly: the _original_ GuardDuty finding only flagged one specific event, but graph exploration surfaced a materially broader picture within minutes — exactly the kind of discovery that manual, raw-log correlation (§77's approach, applied to security investigation) would have taken considerably longer to uncover, if the analyst even thought to look in the right places at all.

## 9. Production and Enterprise Usage

- Detective is commonly enabled organization-wide alongside GuardDuty and Macie, administered from the same security delegated administrator account (§118), reflecting these three services' natural operational pairing as a security operations team's core toolset.
- Security operations teams commonly treat "pivot into Detective" as the standard next step immediately following any GuardDuty or Macie finding warranting deeper investigation, rather than defaulting to manual raw-log querying as the first investigative step — reserving direct Athena/CloudTrail querying (§4.3) for precise verification once Detective's exploration has narrowed the investigation's actual scope.
- Finding groups (§4.2) are particularly valuable at organizational scale, where a security team monitoring findings across hundreds of accounts might otherwise miss that several individually-unremarkable findings actually represent one coordinated pattern.

## 10. Security Considerations

- Detective's own access — who can explore an organization's full behavior graph — is itself a meaningful security/privacy consideration, since the graph inherently contains detailed activity patterns across the organization; access should be restricted to appropriately authorized security personnel, following the same least-privilege discipline applied throughout this course.
- Detective is a read-only investigation tool — it doesn't take remediation action itself; any response based on a Detective investigation's findings still requires the explicit remediation/response mechanisms covered in §124, maintaining the same human-in-the-loop principle for consequential security actions established throughout this course.

## 11. Performance Considerations

- The behavior graph's continuous background construction (§4.1) means investigation-time exploration is fast — this is the entire point of the pre-computation trade-off — but the graph's completeness depends on how long Detective has been enabled and ingesting data; a newly-enabled Detective instance has a shorter historical window available than one that's been running for months.
- Organization-wide enablement provides cross-account investigation visibility but means the graph spans a proportionally larger volume of activity — generally not a practical concern for investigation speed given Detective's purpose-built graph architecture, but worth being aware of as a scale dimension when evaluating enablement scope.

## 12. Monitoring

- Detective itself is primarily an investigation tool used reactively (triggered by a finding) rather than something continuously monitored the way a CloudWatch dashboard is — but ensuring Detective remains enabled and correctly ingesting data across all intended accounts is itself worth periodic verification, similar to confirming an organization trail's continued coverage (§117 §12).
- Investigation outcomes (what was actually found, how long investigations take, how often Detective surfaces broader patterns beyond the original triggering finding) are worth tracking as a security operations program health metric, mirroring the "track whether the program is actually working" discipline established in §119's Architect answer.

## 13. Troubleshooting

| Symptom                                                                       | Cause                                                                                                                                | Fix                                                                                                                                                                                          |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Behavior graph shows limited/incomplete history for an investigation          | Detective was only recently enabled, hasn't yet accumulated sufficient historical data                                               | Understand this as an inherent limitation of recent enablement; consider whether raw CloudTrail data (if retained longer, per §117) can supplement for periods before Detective's enablement |
| An account's activity doesn't appear in the organization-wide graph           | Account wasn't included in Detective's organization-wide enablement scope                                                            | Verify the account is properly enrolled in the organization-wide Detective configuration                                                                                                     |
| Investigation seems to be missing an expected connection between two entities | The specific interaction type may not be captured by Detective's current data sources, or falls outside the graph's retention window | Verify current documentation for exactly which interaction types/data sources feed the graph; supplement with direct CloudTrail/VPC Flow Log querying if needed                              |

## 14. Best Practices

- Enable Detective organization-wide alongside GuardDuty, administered from the same security delegated administrator account.
- Treat Detective as the default first investigative step following a GuardDuty or Macie finding, reserving direct raw-log querying for precise verification once the investigation's scope is better understood.
- Use finding groups to catch broader, coordinated patterns that might otherwise appear as several unrelated, individually-lower-priority findings.
- Enable Detective proactively, well before an incident occurs — its value depends on having accumulated sufficient historical behavior graph data, which recent enablement can't provide.

## 15. Anti-Patterns and Common Mistakes

- ❌ Relying entirely on manual, raw-log correlation (§77's approach) for security investigations when Detective's pre-built behavior graph would substantially accelerate the same investigation.
- ❌ Only enabling Detective reactively, after a significant incident has already occurred, missing the accumulated historical graph data that would have made that investigation faster and more complete.
- ❌ Treating a single GuardDuty finding as the complete picture without pivoting into Detective to check for broader, connected activity that the original finding alone didn't surface.
- ❌ Granting broad Detective access to personnel without a genuine security-investigation need, given the sensitive, detailed activity picture the behavior graph contains.

## 16. Interview Questions with Model Answers

**🎯 Junior:** _"How is Amazon Detective different from GuardDuty?"_
**Model answer:** GuardDuty detects specific suspicious events — an anomalous API call, unusual network traffic — and generates findings. Detective doesn't detect new issues itself; instead, it helps investigate an issue once you suspect one, by automatically building a visual map of relationships between IAM principals, resources, and network activity over time, so you can quickly explore what else is connected to a specific finding rather than manually piecing that picture together from raw logs.

**🎯 Intermediate:** _"Why would a security analyst use both Detective and direct Athena queries against CloudTrail logs during the same investigation, rather than just one or the other?"_
**Model answer:** They're suited to different stages of an investigation. Detective is best when you don't yet know the full shape of what you're investigating — starting from one flagged entity and exploring its behavior graph to discover connected activity you might not have thought to look for. Direct Athena queries against centralized CloudTrail data are best once you have a precise, specific question — for example, confirming the exact timestamp and parameters of a specific API call Detective's exploration surfaced as suspicious. A real investigation commonly starts broad and exploratory in Detective, then narrows to precise verification via direct log queries once the investigation's actual scope becomes clearer.

**🎯 Senior:** _"Your security team investigates GuardDuty findings by manually querying CloudTrail via Athena for each one, and investigations typically take several hours. How would introducing Detective change this, and what would you expect to improve?"_
**Model answer:** Detective's pre-built behavior graph removes the most time-consuming part of the current manual process — constructing the relationship picture (what else did this principal do, what other resources were touched) from scratch via individual queries. With Detective, an analyst starting from the same GuardDuty finding can immediately explore that entity's full behavior graph neighborhood visually, rather than formulating and running a series of separate Athena queries to build the same picture manually. I'd expect investigation time to drop substantially for the exploratory phase specifically, and I'd also expect Detective to surface connections the team's current manual process might be missing entirely — since a manual investigator only queries for what they think to look for, while Detective's graph exploration surfaces actual observed relationships regardless of whether the analyst thought to check for them, similar to how §8's example surfaced a second compromised role the original finding never flagged.

**🎯 Architect:** _"Design the security investigation tooling and process for an organization with 200+ accounts, where the security team is small (5 people) and currently struggles to investigate the volume of GuardDuty findings generated across the whole environment."_
**Model answer:** Enable GuardDuty, Macie, and Detective organization-wide, administered from a single security delegated administrator account (§118), giving the 5-person team one unified environment rather than needing to work across many individual accounts. Given the team's small size relative to 200+ accounts' finding volume, prioritize triage using Detective's finding-group capability (§4.2) specifically — grouping related findings automatically means the team investigates coordinated patterns as single, consolidated investigations rather than working through what might otherwise appear as dozens of separate, unrelated findings requiring dozens of separate manual investigations, directly addressing the stated volume-versus-team-size challenge. Configure automated response (§124) for the highest-confidence, well-understood finding types — mirroring §119 §4.2's automatic-remediation principle, here applied to initial containment actions (e.g., automatically isolating a resource showing very high-confidence compromise indicators) for the clearest cases, freeing the team's limited investigative time for genuinely ambiguous or complex findings that actually require human judgment via Detective's exploratory investigation. Establish Detective as the mandatory first investigative step for any finding requiring deeper analysis (rather than defaulting to slower manual CloudTrail querying), directly targeting investigation-time reduction per finding, which — combined with finding-group consolidation reducing the effective number of separate investigations needed — together address both dimensions (speed per investigation, and total investigation count) of the team's stated volume challenge.

## 17. Common Misconceptions

- "Detective detects security threats the way GuardDuty does." False — Detective accelerates investigation of a suspected issue; it doesn't independently generate new detection findings the way GuardDuty's anomaly-detection does.
- "Detective and direct log querying (Athena) are competing, redundant approaches." False — as §4.3 establishes, they're complementary, suited to different investigation stages (exploratory versus precise verification).
- "Detective is only useful reactively, after an incident is already suspected." Partially false — while investigation is inherently reactive to a trigger, Detective's value depends on proactive, early enablement, since a richer historical behavior graph (built up over time before any incident) makes any future investigation more complete than one starting from a freshly-enabled instance with minimal history.

## 18. Key Takeaways

🔑 Detective automatically builds a continuous behavior graph from CloudTrail, VPC Flow Logs, and GuardDuty data, accelerating security investigation by letting analysts visually explore relationships rather than manually correlating raw logs.
🔑 Detective is an investigation-acceleration tool, not a detection tool — it complements GuardDuty (which detects) and Macie (which discovers sensitive data), typically serving as the next step once one of those services generates a finding warranting deeper investigation.
🔑 Detective and direct Athena/CloudTrail querying are complementary — exploratory graph investigation for discovering unknown connections, precise log querying for verifying specific, already-identified questions.
🔑 Finding groups surface coordinated patterns across multiple individually-flagged findings, valuable especially at scale where a small security team can't manually cross-reference every finding against every other.
🔑 Detective's value depends on proactive, early enablement — a longer-running instance has a richer historical graph available for any future investigation than one enabled only reactively after an incident is already suspected.

## 19. Related Concepts

- **GuardDuty and Security Hub** (§16) — the detection services whose findings commonly trigger a Detective investigation.
- **Amazon Macie** (§121) — sensitive-data-discovery findings that can similarly trigger Detective investigation.
- **CloudTrail and VPC Flow Logs** (§73, §37) — Detective's underlying data sources.
- **Observability Architecture — Putting It All Together** (§77) — the directly analogous manual multi-pillar investigation approach Detective substantially accelerates for the security-specific investigation domain.
- **AWS Security Lake** (§123, next section) — a broader, centralized security data lake capability, complementary to Detective's purpose-built behavior graph approach.
