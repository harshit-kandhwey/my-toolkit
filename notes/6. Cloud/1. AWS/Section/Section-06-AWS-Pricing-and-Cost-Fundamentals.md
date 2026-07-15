# Part 1 · Section 6 — AWS Pricing & Cost Fundamentals

> AWS Zero-to-Enterprise Knowledge Base · Part 1: Foundations & Global Infrastructure

---

## 1. Definition

**Plain-language:** AWS doesn't have one fixed price list. Almost everything is metered — charged based on how much you actually consume (time, storage, requests, data transferred); different services meter different things.

**Precise:** AWS pricing is fundamentally **consumption-based (pay-as-you-go)**, applied per service using service-specific **pricing dimensions**. Charges accrue continuously, billed monthly, with tools to forecast, monitor, and control spend.

> 💡 **Mental model:** Your bill is like a utility bill with many separate meters — compute-hours, GB stored, GB transferred out, API requests — all itemized and summed monthly.

---

## 2. Why It Exists

- Delivers Section 1's promise — trade capital expense for variable expense; never pay for idle unprovisioned capacity, never blocked by a purchase order.
- **Trade-off:** the flexibility that removes upfront cost also removes a natural spending ceiling. Without deliberate cost management, consumption-based billing can produce runaway costs — a real operational risk.

---

## 3. Fundamental Pricing Dimensions

1. **Compute time** — per instance-hour or per-second (EC2); Lambda = per request + per GB-second.
2. **Storage** — per GB-month, often tiered by access frequency (Part 5: S3 storage classes).
3. **Requests / API calls** — per thousand/million (S3, DynamoDB, SQS, API Gateway).
4. **Data transfer** — charged by direction/destination (see §4 — most misunderstood dimension).
5. **Provisioned capacity** — pre-allocated throughput (e.g., DynamoDB provisioned capacity), charged regardless of actual usage, vs. on-demand request pricing.

> 🔑 For any new service, ask: "what is its metering unit?" — time, storage-time, requests, or data transferred.

---

## 4. Data Transfer Pricing — The Most Misunderstood Rule

- **IN to AWS (from internet):** generally free.
- **OUT to the internet:** generally charged, per GB, often tiered (cheaper at higher volume).
- **BETWEEN Regions:** charged (crossing a Region boundary).
- **WITHIN same AZ:** often free/minimal; between AZs in same Region: typically a small charge.
- **Certain paths reduced/free:** e.g., VPC Gateway Endpoint traffic, CloudFront pricing structure (Parts 4/5).

> ⚠️ Exact rates change frequently and vary by Region — verify on the service's pricing page. Treat the **directional pattern** (in=free, out=charged, cross-Region=charged) as the durable mental model.

> 🎯 "Why is my bill higher than expected" answers should almost always mention data transfer out — the most common surprise-charge source at scale.

---

## 5. Major AWS Pricing Models

| Model | Commitment | Price | Best for |
|-------|-----------|-------|----------|
| On-Demand | None | Highest baseline | Unpredictable/short-term/first-time workloads |
| Reserved / Savings Plans | 1–3 years, optional upfront | Discounted 30–70%+ | Steady-state, predictable, long-running |
| Spot | None (AWS can reclaim with short notice) | Deepest discount 70–90%+ | Fault-tolerant, interruptible, flexible-timing |
| Free Tier | None | Free within allowances | Learning, prototyping, light usage |

> 🔑 **Trade-off pattern:** commitment and interruptibility are what you trade for discount. On-Demand = no trade, highest price; Reserved = time commitment for discount; Spot = availability guarantee for deepest discount. Generalizes far beyond EC2.

---

## 6. Free Tier — Cost-Management Context

- Three categories (Section 4): always-free, 12-months-free, short-term trials.
- It's an **allowance, not an enforced ceiling** — exceeding it bills normally, silently, unless guardrails (§7) are set.
- Practical: always clean up lab resources (terminate instances, delete unused volumes/snapshots) — a forgotten running resource is the most common unwanted-charge source for learners.

---

## 7. Cost Management & Governance Tools

### 7.1 AWS Cost Explorer
- Visual analytics of **historical** cost/usage, filterable by service, account, tag, Region, time; basic forecasting.
- Turns raw billing into filterable charts — "what drove last month's spike?"
- Use: monthly reviews, identifying top cost drivers, informing RI/Savings Plans decisions.

### 7.2 AWS Budgets
- Define a spending/usage **threshold**; get alerted (email/SNS) when actual or **forecasted** spend crosses it.
- Proactive vs Cost Explorer's reactive nature.
- Types: cost budgets, usage budgets, Reservation/Savings Plans utilization/coverage budgets.
- Best practice: set a low-dollar cost budget (e.g., $5–$10) with 80%/100% alerts on every new/learning account.

### 7.3 AWS Cost and Usage Report (CUR)
- Most detailed, line-item-level export, delivered to S3, for custom analysis/BI/data-warehouse integration and chargeback systems.

### 7.4 AWS Pricing Calculator
- **Pre-purchase** planning tool — describe a hypothetical architecture, get a monthly cost estimate before building.

### 7.5 AWS Trusted Advisor (preview, full detail Part 8)
- Cost-optimization checks: flags idle/underutilized resources (stopped instance still billing EBS, idle load balancer).

**Which tool answers which question:**

| Question | Tool |
|----------|------|
| What did I spend, on what, historically? | Cost Explorer |
| Alert me before/when I overspend | Budgets |
| Every line-item detail for custom analysis | Cost and Usage Report |
| What will this new architecture cost? | Pricing Calculator |
| Is anything idle and wasting money? | Trusted Advisor |

---

## 8. Billing & Payment Concepts

- **Billing cycle:** monthly, in arrears, based on metered usage.
- **Consolidated Billing:** under an Organization, all member accounts roll into one bill (management account pays), per-account attribution retained, unlocks volume discount tiers.
- **Cost allocation tags:** key-value labels (`team: payments`, `env: production`) flowing into Cost Explorer/CUR for breakdowns by team/project/environment — essential for chargeback/showback (Part 10).

---

## 9. Production & Enterprise Usage

- **FinOps:** cross-functional practice (finance + engineering + leadership) continuously optimizing spend vs. business value, using §7's tools as instrumentation (Part 10).
- **Showback/chargeback:** tags + Cost Explorer/CUR attribute spend to teams/products — for visibility or actual internal billing.
- **Reserved capacity planning:** analyze steady-state usage via Cost Explorer before committing to RIs/Savings Plans.
- **Guardrails:** Budgets alerts + SCPs (restrict expensive actions/Regions) + automated remediation (e.g., Lambda triggered by a Budget alert to stop non-prod resources).

---

## 10. Common Cost Mistakes & Troubleshooting

| Symptom/Mistake | Root cause | Fix |
|---|---|---|
| Bill much higher than expected mid-month | No alerting on uncapped billing | Set up Budgets on every account immediately |
| "Free Tier" account still charged | Exceeded allowance / non-covered service or Region | Check Cost Explorer; verify current Free Tier terms |
| Forgotten resources after a lab | No cleanup; e.g., EBS volume billing after instance termination | Explicitly delete/terminate everything; check Trusted Advisor |
| Large unexplained data-transfer charges | Cross-Region or internet-egress pattern not accounted for | Filter Cost Explorer by usage type; review architecture for unnecessary egress |
| Can't tell which team caused a spike | No tagging strategy | Implement/enforce cost allocation tags |

---

## 11. Best Practices & Anti-Patterns

**Best practices:** set an AWS Budget with alerts on every account from day one; tag resources consistently from the start; use Pricing Calculator during design; review Cost Explorer regularly; clean up lab/test resources immediately; evaluate RIs/Savings Plans using real historical usage.

**Anti-patterns:** treating pay-as-you-go as "no active management needed"; ignoring data transfer in multi-Region/high-egress designs; assuming Free Tier is a hard cap; committing to Reserved capacity without usage analysis; no tagging strategy.

---

## 12. Common Misconceptions

- "Free Tier means I can't be charged." → False — an allowance, not a cap.
- "Inbound and outbound data cost the same." → False — inbound generally free, outbound generally charged (often the biggest surprise line item).
- "Reserved capacity is always cheaper." → False — only if you actually use the committed capacity; unused reservations waste money.
- "Cost Explorer warns me automatically." → False — Cost Explorer is passive/historical; **Budgets** is the proactive alerting tool.

---

## 13. Interview Questions (with model answers)

**🟢 How does AWS pricing generally work?** Consumption-based, pay-as-you-go — charged for actual usage, metered per service (compute time, storage GB-month, requests, data transfer), no large upfront purchase, billed monthly; commitment-based discounts (Reserved/Savings Plans) also available for predictable workloads.

**🟡 Why might data transfer outweigh compute cost concerns?** Inbound is free but outbound to the internet is charged and has no natural cap the way compute does (can't "right-size" egress); cross-Region traffic adds more. Media-heavy or chatty cross-Region architectures can have data transfer dominate the bill even with modest compute.

**🟡 Cost Explorer vs Budgets?** Cost Explorer = retrospective/exploratory, visualizes historical cost/usage with some forecasting. Budgets = proactive, alerts when actual/forecasted spend crosses a set threshold. Use together: Explorer to understand what happened, Budgets to catch problems early.

**🔴 Cost governance for 100 AWS accounts?** Enforce tagging via SCPs/Config rules; use Organizations consolidated billing for volume discounts with per-account visibility; Budgets with escalating alerts org- and account-wide; CUR into a central warehouse for FinOps/chargeback; analyze real usage via Cost Explorer before RI/Savings Plans commitments; pair Budget alerts with automated guardrails (auto-stop non-prod resources, SCP blocking expensive instance types in dev).

**🔴 Bill tripled overnight, no deploy — investigate?** Cost Explorer filtered to recent days, grouped by service, to isolate the driver. Data-transfer spike → suspect traffic-pattern change, misconfigured cross-Region replication, newly-exposed resource. Compute spike → check runaway Auto Scaling, stuck retry loop, forgotten test workload (Trusted Advisor idle checks help). Cross-reference timing with CloudTrail — "no deploy" doesn't rule out a manual Console change, autoscaling event, traffic surge, or leaked-credential misuse. Check Budgets alert history to narrow the time window.

---

## 🔑 Key Takeaways

1. AWS pricing is consumption-based across service-specific dimensions — ask "what's the metering unit?" for any service.
2. Data transfer OUT to internet and across Regions is charged; IN is generally free — the most common surprise-bill source.
3. Purchasing models (On-Demand, Reserved/Savings Plans, Spot) trade commitment or interruptibility for discount — one trade-off axis generalizing beyond EC2.
4. Cost Explorer (retrospective), Budgets (proactive), CUR (granular), Pricing Calculator (pre-purchase), Trusted Advisor (idle detection) each answer a distinct question — use together.
5. Free Tier is an allowance, not a cap — combine with Budgets and disciplined cleanup.

## 🌐 Related Concepts (forward links)

- Reserved Instances, Savings Plans, Spot in depth → Part 3
- S3 storage classes and cost trade-offs → Part 5
- Cost allocation tags, SCP-based cost guardrails → Part 2
- FinOps, chargeback/showback, Well-Architected Cost Optimization pillar → Part 10
