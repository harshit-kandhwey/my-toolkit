# Section 129 (Part 15): Capacity Planning and Baseline Establishment

## 1. Definition

**Plain language:** Every metric covered so far in this Part — latency, loss, throughput, interface counters, flow volumes — is only meaningful relative to "what normal looks like." Capacity planning is the discipline of knowing today's normal well enough to predict when it will stop being enough, and a baseline is the recorded, quantified version of that "normal" everything else gets compared against.

**Precise definition:** A **baseline** is a documented, statistically characterized record of a network's normal operating behavior for a given metric (utilization, latency, error rate, connection count) over a representative time period, capturing not just an average but the expected range and pattern of variation (time-of-day, day-of-week, seasonal cycles). **Capacity planning** is the ongoing practice of comparing current and projected demand against available capacity, using historical growth trends derived from baseline data to forecast when a given link, device, or path will approach a utilization threshold that risks performance degradation, and to plan upgrades or architectural changes proactively rather than reactively. The two are inseparable: capacity planning without a baseline is guesswork, and a baseline without an ongoing capacity-planning practice is just an unused historical record.

> 💡 **Tip:** A baseline is not a single number — "our web tier link runs at 40% utilization" is far less useful than "our web tier link runs at 25-45% utilization on weekdays with a predictable evening peak, and has grown roughly 8% quarter-over-quarter for the last year." The second version is what actually supports a capacity decision.

## 2. Why This Matters

- **Without a baseline, "is this normal?" has no answer** — every anomaly-detection and alerting effort ([§130](Section-130-Part15-Alerting-on-Network-Layer-Signals.md)) fundamentally depends on knowing what abnormal deviates from, making baseline establishment the prerequisite for essentially all proactive network operations.
- **Capacity planning converts reactive firefighting into proactive engineering** — discovering a link is saturated because users are complaining is strictly worse, in cost and reputation, than discovering the same link will saturate in six weeks based on trend projection and upgrading it before that happens.
- **Utilization percentages alone are misleading without understanding queuing behavior** — a link at 70% average utilization can already be experiencing meaningful queuing delay and occasional loss during peak intervals well before it appears "full" on an averaged dashboard, a nuance directly tied to [§124](Section-124-Part15-Network-Performance-Metrics-Latency-Jitter-Packet-Loss-Throughput.md)'s discussion of queuing delay.
- **Growth trends are rarely linear** — a data platform's network demand might grow steadily for months and then step-change sharply after a specific product launch or seasonal event; capacity plans that assume smooth linear growth are frequently caught off guard by real-world step changes.
- **This section closes the loop on everything measured in [§124](Section-124-Part15-Network-Performance-Metrics-Latency-Jitter-Packet-Loss-Throughput.md)-[§128](Section-128-Part15-Network-Observability-in-Cloud-and-Modern-Stacks-VPC-Flow-Logs-Metrics.md)** — those sections provide the raw data; this section is where that data becomes a decision-making tool rather than just a dashboard.

## 3. Prerequisites and Dependencies

This section depends directly on [§124](Section-124-Part15-Network-Performance-Metrics-Latency-Jitter-Packet-Loss-Throughput.md)'s metric definitions (baselines are built from exactly those metrics) and on the measurement tooling from [§125](Section-125-Part15-Bandwidth-Testing-Tools-iperf-and-Friends.md)-[§128](Section-128-Part15-Network-Observability-in-Cloud-and-Modern-Stacks-VPC-Flow-Logs-Metrics.md) (iperf, SNMP, flow data, cloud metrics) as the actual sources of baseline data. It assumes queuing-delay concepts introduced in [§124](Section-124-Part15-Network-Performance-Metrics-Latency-Jitter-Packet-Loss-Throughput.md)'s latency-decomposition discussion, since utilization thresholds for capacity action are set based on when queuing delay becomes material, not simply at 100% raw utilization. It sets up [§130](Section-130-Part15-Alerting-on-Network-Layer-Signals.md) directly — alerting rules are only meaningful when they're defined relative to an established baseline and deviation from it, rather than an arbitrary static threshold.

## 4. Architecture / Conceptual Diagram

```text
    UTILIZATION vs. LATENCY (why capacity action happens well before "100% full")

    Latency
      │                                                    ╱
      │                                                  ╱
      │                                               ╱
      │                                          ╱
      │                                  ╱ ◄── queuing delay begins
      │                          ╱            rising sharply here
      │            ╱ ╱ ╱ ╱ ╱ ╱
      └──────────────────────────────────────────────────────► Utilization %
         0%        50%        70%        85%        100%
                                 ▲
                      typical capacity-action threshold
                      (well before saturation, not at it)

    BASELINE + TREND PROJECTION (used for capacity forecasting)

    Utilization %
    100% ┤                                              ╭── projected saturation
     85% ┤ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─ ─╭─┴─  (action threshold)
     70% ┤                                    ╭───────╯
     55% ┤                          ╭─────────╯
     40% ┤ actual history ─────────╯
         └────────────────────────────────────────────────────► Time
           Q1        Q2        Q3        Q4        Q1 (next)   ◄── plan upgrade here
```

- The relationship between utilization and latency is non-linear (queuing theory) — latency stays relatively flat at low-to-moderate utilization and then rises sharply as a link approaches saturation, which is why capacity-action thresholds are typically set well below 100% (often 70-85% depending on traffic burstiness), not at the point of literal exhaustion.
- A baseline that only captures a single "current utilization" number cannot support trend projection; capacity planning specifically needs a *time series* of the baseline metric to compute a growth rate and extrapolate forward to a projected saturation date.
- Seasonal and cyclical patterns (daily peak hours, weekly patterns, end-of-quarter batch jobs, holiday traffic surges for customer-facing systems) must be captured in the baseline's characterization, not averaged away — a capacity plan based on an annual average utilization will badly underestimate the peak the network actually needs to sustain.

## 5. Hands-On

### 5.1 Establishing a Utilization Baseline From Existing Telemetry

**Purpose:** Convert raw SNMP/flow/cloud-metric time-series data (from [§126](Section-126-Part15-SNMP-and-Network-Device-Monitoring-Concepts.md)-[§128](Section-128-Part15-Network-Observability-in-Cloud-and-Modern-Stacks-VPC-Flow-Logs-Metrics.md)) into a characterized baseline with expected range and pattern.

**Syntax (conceptual query pattern against a time-series metrics store):**

```text
SELECT
  date_trunc('hour', timestamp) AS hour_bucket,
  extract(dow FROM timestamp) AS day_of_week,
  avg(utilization_pct) AS avg_util,
  percentile_cont(0.95) WITHIN GROUP (ORDER BY utilization_pct) AS p95_util
FROM interface_utilization
WHERE interface_id = 'core-uplink-1' AND timestamp > now() - interval '90 days'
GROUP BY hour_bucket, day_of_week
```

**Example usage and expected output:**

```text
day_of_week   hour   avg_util   p95_util
Mon           09:00     38%        52%
Mon           14:00     61%        79%
Mon           20:00     29%        41%
...
```

**Production usage example:** This pattern — a clear weekday afternoon peak reaching a p95 of 79%, versus a much quieter evening trough — becomes the documented baseline for `core-uplink-1`; any future alerting rule ([§130](Section-130-Part15-Alerting-on-Network-Layer-Signals.md)) for this link is set relative to this known pattern (e.g., "alert if 14:00 weekday utilization exceeds p95 baseline plus 15 percentage points for 3 consecutive samples") rather than a single static threshold that would either be too sensitive during the trough or too insensitive during the peak.

**Common errors:** Establishing a baseline from too short a window (a few days) and missing weekly or monthly cyclical patterns entirely — a baseline built only from a quiet week will flag every subsequent normal busy week as anomalous; at least several weeks, and ideally a full seasonal cycle relevant to the business, should inform the baseline.

### 5.2 Projecting a Capacity Exhaustion Date From Trend Data

**Purpose:** Turn historical utilization growth into an actionable forecast of when a link or device will reach its capacity-action threshold.

**Syntax (conceptual linear/trend projection over quarterly peak utilization data):**

```text
Quarter    Peak Utilization (p95, weekday afternoon)
Q1         55%
Q2         63%
Q3         71%
Q4         79%   ◄── most recent

Trend: ~+8 percentage points per quarter
Action threshold: 85%
Projected quarters to threshold: (85 - 79) / 8 ≈ 0.75 quarter (~2-3 months)
```

**Example usage and expected output:**

```text
Capacity Report: core-uplink-1
Current peak utilization (p95): 79%
Action threshold: 85%
Projected threshold breach: ~early Q1 (next), ~10-12 weeks from report date
Recommended action: initiate upgrade/expansion procurement now
```

**Production usage example:** This kind of quarterly capacity report, generated directly from the baseline established in 5.1, is what justifies a budget request or a change-management ticket for a link upgrade *before* the link becomes a production incident — the entire value of capacity planning lies in this lead time between forecast and actual exhaustion.

**Common errors:** Assuming a linear trend continues indefinitely without accounting for known future events (a planned product launch, a seasonal traffic event, an upcoming migration adding new traffic to the same link) — a purely statistical projection should always be sanity-checked against known business and infrastructure roadmap events that could accelerate or decelerate the trend.

### 5.3 Detecting Baseline Deviation as an Early Warning Signal

**Purpose:** Use the established baseline to flag a change in behavior that is unusual for the specific time/pattern context, not just in absolute terms.

**Syntax (conceptual comparison against baseline expectation, e.g., in a monitoring rule):**

```text
current_util = get_current_metric('core-uplink-1', 'utilization_pct')
baseline_p95 = get_baseline('core-uplink-1', day_of_week=today, hour=current_hour)

if current_util > baseline_p95 + 15:
    raise_warning("Utilization significantly above baseline for this time window")
```

**Example usage and expected output:**

```text
2026-09-14 14:05:00  core-uplink-1  current=94%  baseline_p95(Mon,14:00)=79%
  WARNING: utilization 15pp above established baseline for this time window
```

**Production usage example:** This warning fires specifically because 94% is abnormal *for a Monday at 14:00* even though it might be an entirely normal value during a known end-of-month batch-processing window on a different day — the baseline's time-aware granularity is what prevents both false alarms (flagging normal peak-hour traffic as anomalous) and missed detections (failing to flag an abnormal spike during an otherwise quiet period), setting up the alerting design covered fully in [§130](Section-130-Part15-Alerting-on-Network-Layer-Signals.md).

**Common errors:** Comparing current utilization only against a flat, time-independent baseline (e.g., "the 90-day average is 55%, so 79% is anomalous") — this produces constant false alarms during every normal daily/weekly peak; the comparison must be time-context-aware, as shown above.

## 6. Production Usage Notes

- Re-baseline periodically (quarterly is common) rather than treating a baseline as a permanent, one-time artifact — network traffic patterns shift as applications, user bases, and architectures evolve, and a stale baseline produces both false alarms and missed detections.
- Maintain baselines per logical grouping that actually matters for capacity decisions (per link, per region-pair, per device role) rather than one undifferentiated network-wide average, since different segments have genuinely different normal patterns and different capacity-action thresholds.
- Document the capacity-action threshold rationale (why 85% and not 95%) alongside the baseline itself, since this threshold should reflect the specific link's traffic burstiness and the queuing-delay sensitivity of the applications it carries, not an arbitrary organization-wide constant.

## 7. Security Considerations

- A sudden, unexplained deviation from an established baseline (a link at 3x its normal weekday-evening utilization, for instance) is frequently the earliest observable signal of a DDoS attack, a compromised host generating abnormal traffic, or a data-exfiltration event — baseline-deviation detection is a security control as much as a capacity-management one, directly complementing the flow-data anomaly detection discussed in [§127](Section-127-Part15-Flow-Data-NetFlow-sFlow-IPFIX-Concepts.md)-[§128](Section-128-Part15-Network-Observability-in-Cloud-and-Modern-Stacks-VPC-Flow-Logs-Metrics.md).
- Capacity-planning data itself (detailed traffic patterns, growth projections tied to business events) can be commercially sensitive; access to detailed baseline/capacity reports should be scoped appropriately rather than broadly shared.
- Capacity shortfalls that are allowed to reach genuine saturation can themselves become an availability risk indistinguishable in user impact from an actual denial-of-service event — proactive capacity planning is, in this sense, a preventive security control against self-inflicted availability incidents.

## 8. Common Troubleshooting Scenarios

| Symptom                                                     | Likely Cause                                                                 | Resolution Path                                                                                       |
| -------------------------------------------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Frequent false-positive utilization alerts during known peak hours | Baseline/alert threshold is time-independent (flat) rather than time-aware       | Rebuild the baseline with time-of-day/day-of-week granularity as shown in 5.1; set alerts relative to that pattern |
| Link saturation incident occurred with no advance warning     | No capacity-planning trend projection existed, or baseline was too stale       | Establish/refresh a trend-based projection (5.2) and set a proactive action threshold below saturation |
| Capacity report shows steady linear growth but an actual step-change surprise occurred | A known business/infrastructure event wasn't factored into the projection      | Cross-check trend projections against the infrastructure/product roadmap, not statistics alone         |
| Baseline no longer reflects current normal traffic patterns   | Baseline is stale relative to real architectural/traffic changes since it was built | Re-baseline on a regular cadence (e.g., quarterly) rather than treating the original baseline as permanent |

## 9. Best Practices

- Build baselines with time-of-day and day-of-week granularity, not flat averages, so anomaly detection and alerting can distinguish "unusual for now" from "unusual in general."
- Set capacity-action thresholds well below literal saturation (commonly 70-85%, tuned to the specific link's burstiness) based on the non-linear utilization-to-latency relationship, and document the rationale for the chosen threshold.
- Re-baseline on a regular cadence and explicitly cross-check statistical trend projections against known upcoming business or infrastructure events rather than trusting pure extrapolation.

## 10. Common Anti-Patterns / Mistakes

- **Treating a single "current utilization" number as a baseline.** A useful baseline is a characterized range and pattern over time, not a snapshot — a snapshot supports no trend projection and no time-aware anomaly detection.
- **Setting a flat, time-independent alert threshold across all times of day/week.** This produces false alarms during every normal peak and can miss real anomalies during normally-quiet periods.
- **Extrapolating capacity trends purely statistically without cross-checking against known business events.** Real-world step changes (product launches, seasonal surges, planned migrations) are common and often invisible to a pure historical-trend model.

## 11. Interview Questions

**🎯 Beginner:** _"What is a network baseline, and why is it useful?"_
**Model answer:** A baseline is a documented record of what normal network behavior looks like for a given metric — utilization, latency, error rate — including how it typically varies by time of day and day of week, not just a single average number. It's useful because it gives you something concrete to compare current behavior against: without knowing what's normal, you can't reliably tell whether a given measurement represents a real problem or just expected, everyday variation.
_What the interviewer is probing for:_ Basic understanding that a baseline is a characterized pattern, not a single value, and why that distinction matters.

**🎯 Intermediate:** _"Why would a network team set a capacity-action threshold at 80% utilization instead of waiting until a link is actually at or near 100%?"_
**Model answer:** The relationship between utilization and latency isn't linear — as a link's utilization climbs, queuing delay stays relatively flat at first but then rises sharply as the link approaches saturation, because buffers start filling faster than they can drain. By the time a link is visibly near 100% on a utilization graph, users may already be experiencing meaningful latency degradation or intermittent packet loss during peak intervals. Setting the action threshold at 80% (or wherever queuing delay for that specific link's traffic pattern starts becoming noticeable) provides lead time to upgrade or rebalance capacity before the degradation becomes user-visible, rather than reacting only once the link is already causing real problems.
_What the interviewer is probing for:_ Understanding of queuing theory's practical implication for setting capacity thresholds, not just a rule memorized without the underlying reasoning.

**🎯 Senior:** _"You're asked to build a quarterly capacity report for the network team's core uplinks. What data would you include, and how would you avoid it being misleading?"_
**Model answer:** I'd include, per uplink, the historical trend of peak (not average) utilization over time with clear time-of-day/day-of-week context, since averages hide the peaks that actually drive capacity risk. I'd project that trend forward to estimate when each link would reach its documented capacity-action threshold, and explicitly flag any known upcoming business or infrastructure events (a planned migration, a product launch, seasonal traffic patterns) that could accelerate or invalidate a purely statistical projection — presenting a pure linear extrapolation as if it were certain would be misleading given how often real growth is step-changed rather than smooth. I'd also include current baseline deviation status (is anything already trending abnormally versus its own historical pattern) so the report serves both a forward-looking capacity-planning purpose and a near-term operational-health purpose in the same document.
_What the interviewer is probing for:_ Ability to design a genuinely useful, non-misleading capacity report rather than a superficial utilization chart, with explicit awareness of statistical extrapolation's limitations.

**🎯 Architect:** _"How would you build an organization-wide capacity planning practice across hundreds of network segments spanning on-prem and multiple cloud providers?"_
**Model answer:** I'd centralize all the underlying telemetry — SNMP-derived on-prem interface data ([§126](Section-126-Part15-SNMP-and-Network-Device-Monitoring-Concepts.md)), flow data ([§127](Section-127-Part15-Flow-Data-NetFlow-sFlow-IPFIX-Concepts.md)), and cloud-native metrics ([§128](Section-128-Part15-Network-Observability-in-Cloud-and-Modern-Stacks-VPC-Flow-Logs-Metrics.md)) — into one unified time-series store, tagged consistently by logical role (core, distribution, cross-region, cross-cloud) rather than by raw device identity, so baselines and capacity reports can be generated consistently regardless of the underlying telemetry source. I'd automate baseline computation and re-baselining on a regular cadence (e.g., a rolling 90-day window recomputed monthly) rather than relying on manual, one-off baseline exercises that inevitably go stale. Capacity-action thresholds would be set per segment role, informed by that segment's specific traffic burstiness and the latency-sensitivity of the applications it carries, and documented centrally so they're auditable and consistent rather than ad hoc per team. I'd integrate known infrastructure and business-roadmap events into the projection process — ideally as a structured input a capacity-planning tool consumes, not just an analyst's manual sanity check — so trend projections are automatically flagged when a known event could invalidate them. Finally, I'd make the same baseline data the direct foundation for the alerting practice in [§130](Section-130-Part15-Alerting-on-Network-Layer-Signals.md), so capacity planning and operational alerting share one source of truth rather than maintaining separate, potentially inconsistent definitions of "normal."
_What the interviewer is probing for:_ Ability to scale capacity planning into a systematic, automated, organization-wide practice rather than a manual, per-team exercise, with explicit unification across heterogeneous telemetry sources.

## 12. Common Misconceptions

1. **"A baseline is just the average utilization over some period."** A useful baseline captures the expected range and time-based pattern of a metric, not a single averaged number, which is what enables meaningful anomaly detection.
2. **"Capacity planning means waiting until utilization is near 100% before acting."** Because of the non-linear utilization-to-latency relationship, action thresholds are set well below saturation to provide lead time before user-visible degradation occurs.
3. **"Once a baseline is established, it stays valid indefinitely."** Traffic patterns evolve as applications and usage change; baselines need periodic refresh to remain accurate.
4. **"Trend projections based on historical data are reliably accurate forecasts."** Real-world growth is often step-changed by specific business or infrastructure events; statistical extrapolation should always be cross-checked against known roadmap information.

## 13. 🔑 Key Takeaways

- A baseline is a characterized pattern of normal behavior (including time-based variation), not a single average number, and it is the prerequisite for meaningful anomaly detection and alerting.
- Capacity-action thresholds are set well below literal saturation because of the non-linear relationship between utilization and queuing-driven latency degradation.
- Effective capacity planning combines statistical trend projection with explicit cross-checking against known future business/infrastructure events.
- Baselines must be refreshed periodically and built with enough historical depth to capture real cyclical patterns, not just a short, potentially unrepresentative sample window.

## 14. Related Concepts & What's Next

This section is where the metrics defined in [§124](Section-124-Part15-Network-Performance-Metrics-Latency-Jitter-Packet-Loss-Throughput.md) and measured by the tools in [§125](Section-125-Part15-Bandwidth-Testing-Tools-iperf-and-Friends.md)-[§128](Section-128-Part15-Network-Observability-in-Cloud-and-Modern-Stacks-VPC-Flow-Logs-Metrics.md) become an actual decision-making practice. It depends on queuing-delay concepts from [§124](Section-124-Part15-Network-Performance-Metrics-Latency-Jitter-Packet-Loss-Throughput.md) to justify non-saturation capacity thresholds, and on the SNMP, flow, and cloud-metric data sources from [§126](Section-126-Part15-SNMP-and-Network-Device-Monitoring-Concepts.md)-[§128](Section-128-Part15-Network-Observability-in-Cloud-and-Modern-Stacks-VPC-Flow-Logs-Metrics.md) as its raw material. It leads directly into [§130](Section-130-Part15-Alerting-on-Network-Layer-Signals.md), where the same baseline concept becomes the foundation for defining meaningful, low-noise alerting rules rather than arbitrary static thresholds.

**Next Section:** [§130](Section-130-Part15-Alerting-on-Network-Layer-Signals.md) — `Section-130-Part15-Alerting-on-Network-Layer-Signals.md`
