# Part 3 · Section 3 — EC2 Purchasing Options: On-Demand, Reserved, Spot, Savings Plans, Dedicated

> AWS Zero-to-Enterprise Knowledge Base · Part 3: Compute

---

## 1. Definition

**Plain-language:** AWS offers several ways to "buy" the same EC2 compute — pay full price with zero commitment, commit to steady usage for a discount, or bid for spare capacity at a deep discount but risk losing it on short notice.

**Precise:** EC2 purchasing options are distinct pricing/commitment models — **On-Demand**, **Reserved Instances**, **Savings Plans**, **Spot Instances**, **Dedicated** options — applied to the same compute capacity, each trading commitment length/flexibility/interruptibility for a discount level.

---

## 2. On-Demand Instances — Baseline

- Pay per second (60s minimum for most types), no upfront payment, no commitment — highest rate, maximum flexibility.
- Best for: unpredictable workloads, short-term tasks, first-time/dev-test workloads, anything without a proven usage pattern.
- Almost always the starting point — observe usage, then layer in commitments.

---

## 3. Reserved Instances (RIs)

### 3.1 Definition

A billing discount on On-Demand usage for a 1- or 3-year commitment — not a separate physical resource in most modern forms; a pricing construct discounting matching usage.

### 3.2 Payment Options

| Option          | Upfront                                     | Discount                                |
| --------------- | ------------------------------------------- | --------------------------------------- |
| All Upfront     | Full term paid at purchase                  | Highest                                 |
| Partial Upfront | Partial + monthly remainder                 | Middle                                  |
| No Upfront      | Nothing upfront, monthly at discounted rate | Lowest (of the three), zero cash outlay |

> 🔑 More upfront cash = deeper discount — a direct cash-flow-vs-savings trade-off.

### 3.3 Standard vs Convertible RIs

- **Standard** — can't change family/OS/tenancy (can modify AZ/scope/size within family in some cases); deepest discount.
- **Convertible** — can exchange for different family/config (equal or greater value) during the term; smaller discount, more flexibility.

### 3.4 Regional vs Zonal Scope

- **Regional** — flexible across the Region/AZs, no capacity reservation — more flexible.
- **Zonal** — tied to one AZ, **also provides an actual capacity reservation** there — less flexible but guarantees launch capability during an AZ capacity crunch.

### 3.5 RI Marketplace

- Standard RIs (not Convertible) sellable on the AWS Reserved Instance Marketplace if needs change.

---

## 4. Savings Plans — Modern, Flexible Alternative

### 4.1 Definition

Commit to a consistent **$/hour** of compute usage for 1 or 3 years — RI-like discounts applied automatically/flexibly across a broader usage range.

### 4.2 Two Types

- **Compute Savings Plans** — most flexible: any instance family/size/OS/tenancy/Region, plus **Fargate and Lambda** — broadest scope.
- **EC2 Instance Savings Plans** — narrower: specific instance family within a specific Region, flexible across size/OS/tenancy within that — deeper discount for the narrower scope.

> 🎯 Compute SP trades discount depth for max flexibility (incl. serverless); EC2 Instance SP trades flexibility for deeper discount on a known family/Region.

### 4.3 Savings Plans vs RIs

|                       | RIs                                                | Savings Plans                                      |
| --------------------- | -------------------------------------------------- | -------------------------------------------------- |
| Commitment unit       | Specific config (Standard) or family (Convertible) | Dollar/hour                                        |
| Flexibility           | Lower (esp. Standard)                              | Higher, auto-applies                               |
| Covers Fargate/Lambda | No                                                 | Yes (Compute SP only)                              |
| Secondary market      | Yes (Standard RIs)                                 | No                                                 |
| Current guidance      | Valid, esp. Zonal for capacity                     | Generally the more common default for cost savings |

> 🔑 AWS's guidance favors Savings Plans for pure cost optimization due to flexibility. The main remaining reason for an RI (specifically Zonal) is the capacity reservation guarantee — Savings Plans never provide one (pure billing discount).

---

## 5. Spot Instances

### 5.1 Definition

Spare unused EC2 capacity at a steep discount (often 70-90% off), with AWS able to reclaim it with short notice (~2-minute interruption notice).

### 5.2 Spot Price Mechanics

- Price fluctuates with supply/demand for spare capacity; modern model: pay the current Spot price directly, no traditional bidding war (older material may still describe the deprecated bid mechanic).
- Interruption reasons: AWS needs the capacity back, or the specific pool for your instance type/AZ is constrained.

### 5.3 Best Use Cases

- Batch jobs that checkpoint/resume.
- Stateless horizontally-scaled web tiers (LB routes around losses, ASG replaces).
- CI/CD build agents.
- Big data/analytics (Spark) designed for node failure tolerance.
- **Wrong for:** stateful workloads without replication, strict-SLA workloads, anything that can't handle a 2-minute-notice shutdown.

### 5.4 Spot Fleet / Mixed Instances Policies

- Request Spot across multiple instance types/AZs simultaneously (Spot Fleet, or modern practice: ASG mixed instances policy) — diversification reduces interruption impact.
- Mixing On-Demand + Spot in one ASG — baseline guaranteed capacity + cost-effective Spot scale.

---

## 6. Dedicated Instances and Dedicated Hosts (revisited)

- **Dedicated Instances** — hardware dedicated to your account, premium over shared-tenancy On-Demand, still AWS-managed at host level.
- **Dedicated Hosts** — entire physical server allocated to you, visibility into sockets/cores — only option satisfying per-socket/per-core licensing, or strictest physical-isolation compliance.
- Premium options chosen for compliance/licensing, not cost optimization — opposite end of the spectrum from Spot.

---

## 7. On-Demand Capacity Reservations (ODCR)

- Reserve EC2 capacity in a specific AZ for a specific instance type, **no 1-/3-year term required** — pay On-Demand rates whether used or not, but capacity is guaranteed.
- **Decouples capacity guarantee from billing discount** — combine an ODCR (capacity) with a Savings Plan (discount) for both benefits, more flexible than a bundled Zonal RI.
- Best for: guaranteeing capacity for a planned time-bound event (launch, DR failover test) without a multi-year commitment.

---

## 8. Decision Framework

```
Is the workload interruption-tolerant?
  Yes -> Consider SPOT (deepest discount)
  No -> Is usage predictable/steady?
        No -> Use ON-DEMAND (observe pattern first)
        Yes -> Need a capacity guarantee in a specific AZ?
              Yes -> Zonal RI, or ODCR + Savings Plan combo
              No -> Savings Plan (Compute SP for max flexibility,
                    EC2 Instance SP for deeper discount on known family/Region)
```

> 🔑 A genuinely common system-design/cost interview exercise — walk through it live, reasoning why each branch leads where it does.

---

## 9. Production & Enterprise Usage

- **Layered purchasing strategy at scale:** Savings-Plans-covered baseline + On-Demand for spikes + Spot for fault-tolerant/batch — three models simultaneously across one fleet.
- **Savings Plans decisions driven by Cost Explorer analysis** of actual historical steady-state usage (Part 1 §6).
- **RI/Savings Plans utilization tracked via Budgets** — alerts on under-utilization of a commitment, just as important as overspend alerts.
- **Spot for CI/CD and batch** — widely-cited case study, often 60-90% cost reduction for interruption-tolerant workloads.

---

## 10. Cost Considerations

- **Unused RI/Savings Plans commitment is wasted money** — "reserved is always cheaper" is false if unused (Part 1 §6 misconception, applies with full force here).
- **Spot's savings are real but variable** — architecting for interruption tolerance is what makes savings reliably capturable, not the discount percentage alone.

---

## 11. Security Considerations

- **Dedicated Hosts and licensing compliance** — some enterprise license compliance is a customer responsibility (Part 1 §3) that Dedicated Host purchasing satisfies.
- **Spot interruption handling should be graceful** — an app not properly draining in-flight requests on the 2-minute notice (Section 6 load balancer deregistration) causes real user-facing errors, not just a cost issue.

---

## 12. Troubleshooting

| Symptom                                                   | Cause                                                                            | Fix                                                                                     |
| --------------------------------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| RI/Savings Plan not reducing bill as expected             | Commitment doesn't match actual usage (Standard RI too narrow, or usage shifted) | Review Cost Explorer RI/SP utilization; consider Convertible RI or Compute Savings Plan |
| Spot Instances frequently interrupted                     | Single high-demand instance type/AZ combo                                        | Diversify via mixed instances policy or Spot Fleet                                      |
| Can't launch a type during capacity crunch despite budget | On-Demand has no capacity guarantee                                              | Use Zonal RI or ODCR                                                                    |
| Savings Plan not discounting Fargate/Lambda               | Purchased EC2 Instance Savings Plan, not Compute Savings Plan                    | Only Compute Savings Plans cover Fargate/Lambda                                         |

---

## 13. Best Practices & Anti-Patterns

**Best practices:** start On-Demand, observe via Cost Explorer, then commit; default to Savings Plans over RIs for pure cost optimization, reserve RIs (Zonal) for capacity-guarantee needs; diversify Spot requests; architect for graceful Spot interruption; layer purchasing options across the fleet.

**Anti-patterns:** committing to large RI/SP purchases before a proven usage pattern; Spot for stateful workloads without replication; assuming Savings Plans provide capacity guarantees; single Spot instance type/AZ; defaulting to Dedicated Instances/Hosts without a genuine licensing/compliance need.

---

## 14. Common Misconceptions

- "RIs reserve actual capacity." → Only true for Zonal RIs — Regional RIs are pure billing discount.
- "Savings Plans and RIs are basically the same." → False — dollar-amount vs specific-configuration commitment; AWS favors Savings Plans for flexibility.
- "Spot still works via a bidding war." → False in the modern model — pay the current Spot price directly.
- "Spot is too risky for production." → False as a blanket statement — appropriately architected fault-tolerant workloads run on Spot in production widely.

---

## 15. Interview Questions (with model answers)

**🟢 RI vs Savings Plan?** RI commits to a specific configuration (or family for Convertible) for 1-3 years. Savings Plan commits to a $/hour amount, applying flexibly — Compute SP even covers Fargate/Lambda. Savings Plans generally more flexible; AWS favors them for cost optimization; Zonal RIs remain relevant for capacity guarantees.

**🟢 When would you use Spot?** Fault-tolerant, flexible-timing workloads tolerating ~2-minute interruption — batch, stateless scaled web tiers behind an LB, CI/CD agents, big-data processing designed for node failure. Not for stateful workloads without replication or strict-SLA workloads.

**🟡 Regional vs Zonal RI, and when does it matter?** Regional: flexible across the Region/AZs, no capacity reservation, pure billing construct. Zonal: tied to one AZ, also provides an actual capacity reservation, guaranteeing launch capability during a crunch. Matters when capacity availability, not just cost, is a real concern.

**🟡 Reduce Spot interruption risk for production batch processing?** Diversify across instance types/AZs via ASG mixed instances policy rather than a single type/AZ — more pools reduce simultaneous-loss odds. Ensure checkpointing/graceful 2-minute-notice handling. Mix in an On-Demand/Savings-Plans baseline alongside Spot for guaranteed minimum capacity.

**🔴 Design purchasing strategy for steady web app + nightly batch analytics + periodic launches needing guaranteed capacity?** Web app: Compute Savings Plan sized to Cost Explorer-analyzed steady-state baseline (covers flexibility, extends to Fargate/Lambda), On-Demand above baseline for spikes. Nightly batch: Spot, diversified via mixed instances policy, since fault-tolerant and time-bound. Launches: On-Demand Capacity Reservation scoped to the launch window/AZ, no multi-year commitment; evaluate a Zonal RI if the need recurs regularly.

**🔴 A 3-year All Upfront RI is now on the wrong instance family after a migration — options and prevention?** If Convertible: exchange for the new family (equal/greater value) — exactly its designed flexibility. If Standard: sell remaining term on the RI Marketplace, or accept as sunk cost while running the new workload elsewhere. Forward-looking: shift default guidance to Savings Plans (dollar commitment, not configuration) to prevent this stranding; reserve Standard RIs only for very high-confidence unchanging configs, leaning Convertible over Standard given how often "won't change" proves wrong over 3 years.

---

## 🔑 Key Takeaways

1. On-Demand is the flexible, no-commitment baseline — the correct starting point before a usage pattern is proven.
2. RIs commit to a specific configuration for 1-3 years; only Zonal RIs provide an actual capacity guarantee — Regional RIs and all Savings Plans are pure billing discounts.
3. Savings Plans commit to a dollar amount, applying more flexibly — Compute SP (max flexibility, incl. Fargate/Lambda) vs EC2 Instance SP (deeper discount, narrower scope). AWS generally favors Savings Plans for pure cost optimization.
4. Spot offers the deepest discount (70-90%) for possible ~2-minute-notice interruption — for fault-tolerant, flexible-timing workloads, mitigated by diversification.
5. Capacity guarantees and billing discounts are separable — ODCR + Savings Plan combines both without a multi-year commitment purely for the guarantee.

## 🌐 Related Concepts (forward links)

- Auto Scaling Groups and mixed instances policies → Part 3, Section 5
- EC2 storage/networking details → Part 3, Section 4
- Fargate/Lambda pricing and Compute Savings Plans → Part 3, Sections 7-8
- Cost Explorer/Budgets workflow for RI/SP decisions in full depth → Part 10 FinOps
