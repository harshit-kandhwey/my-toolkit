# Section 57 (Part 8): Cost Optimization & FinOps on GCP

## 1. Definition

**Plain language:** Cost optimization is the ongoing practice of paying only for the cloud capacity you actually need, and no more — spotting waste, buying discounts where you have predictable usage, and giving finance and engineering teams shared visibility into spend so nobody is surprised by the bill.

**Precise:** Cost optimization on GCP combines pricing mechanisms (Committed Use Discounts, Sustained Use Discounts, Spot VMs), automated recommendations (Recommender), and financial operations tooling (Cloud Billing budgets, exports to BigQuery) to minimize cost per unit of value delivered while maintaining required performance and reliability. **FinOps** is the broader organizational discipline — bringing engineering, finance, and business teams into a shared, iterative accountability loop over cloud spend.

## 2. Why It Exists / Problem It Solves

Cloud's pay-as-you-go model is exactly what makes it cost-_efficient_ in theory, but it also makes it easy to overspend in practice:

- Resources provisioned for a temporary test are forgotten and left running indefinitely, accumulating cost with zero value delivered.
- Engineers, optimizing for "it works," commonly over-provision (bigger machine types, more replicas than needed) because oversizing is safe and undersizing causes visible incidents — this asymmetry biases everyone toward waste.
- Without shared visibility, finance discovers overspend only when the invoice arrives, long after the decisions that caused it were made, making corrective action slow and reactive rather than proactive.
- On-demand pricing is the most flexible but also the most expensive; without deliberate optimization, teams simply pay full on-demand rates even for perfectly predictable, always-on workloads that could receive a substantial discount.

GCP's discount mechanisms, recommendation tooling, and billing export/budget features exist to close this gap — reducing waste and giving organizations the cost visibility and levers needed to control spend proactively rather than after the fact.

## 3. Committed Use Discounts (CUDs)

A **Committed Use Discount** is a contractual commitment to use a minimum amount of compute (vCPU/memory) or spend for a **1-year or 3-year term**, in exchange for a significant discount (up to roughly 55–70% off on-demand pricing depending on resource type and term length) versus on-demand pricing.

- **Resource-based CUDs:** Commit to a specific amount of vCPU and memory in a specific region, applied automatically to matching running instances.
- **Spend-based CUDs:** Commit to a minimum hourly spend across a broader set of eligible services (useful when workload composition varies but overall spend is predictable), rather than committing to a specific machine shape.
- **Flexible CUDs:** Apply automatically to any qualifying machine family/region combination, giving more flexibility than resource-based CUDs at a slightly different discount rate.

> ⚠️ **Key trade-off:** CUDs are a financial commitment, not a technical reservation — they do not guarantee capacity availability the way a reservation does. If you need both a guaranteed discount **and** guaranteed capacity, you must combine a CUD with a separate Compute Engine **reservation**.

## 4. Sustained Use Discounts (SUDs)

**Sustained Use Discounts** are automatic, no-commitment discounts applied when a VM runs for a significant portion of a billing month — GCP automatically applies an increasing discount the longer a given VM (of certain machine types) runs continuously within the month, with no upfront commitment or contract required.

- Applies automatically — there is nothing to configure or purchase.
- Only applies to certain machine types/families (check current eligibility, since Google has narrowed SUD eligibility over time as CUDs and other discount mechanisms have expanded).
- Complements, rather than replaces, CUDs: a workload that runs continuously all month gets SUD automatically, and can _additionally_ apply a CUD for a deeper committed discount.

| Discount type                               | Commitment required                                        | Applies to                                 | Discount mechanism                                                        |
| ------------------------------------------- | ---------------------------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------- |
| **Sustained Use Discount**                  | None — automatic                                           | Certain machine types running continuously | Increases automatically the longer the instance runs in the billing month |
| **Committed Use Discount (resource-based)** | 1 or 3 year commitment to specific vCPU/memory in a region | Matching running instances                 | Fixed discount rate for the term, regardless of actual usage pattern      |
| **Committed Use Discount (spend-based)**    | 1 or 3 year commitment to minimum hourly spend             | Broader set of eligible services           | Fixed discount rate applied against qualifying spend                      |

## 5. Spot VMs

**Spot VMs** (the evolution of what GCP previously called "Preemptible VMs") are spare Compute Engine capacity offered at a steep discount (up to ~60–91% off on-demand, depending on machine type and region), with the trade-off that Google can reclaim the VM at any time with short notice (a termination notice, typically giving the workload a brief window to gracefully shut down).

- **Best suited for:** fault-tolerant, stateless, interruptible batch workloads — CI/CD build agents, batch data processing ([Section 9](../Part1/Section-09-Part1-Cloud-Batch.md)'s Cloud Batch is a natural fit), rendering jobs, or GKE node pools running workloads that tolerate pod eviction and rescheduling.
- **Not suited for:** stateful databases, long-running interactive services, or anything without a checkpoint/retry mechanism to resume after preemption.
- No commitment or term required — pay only for what runs, at the discounted spot rate, for as long as capacity is available.

> 💡 **Tip:** Spot VMs and CUDs solve different problems and are often combined in the same architecture: steady-state, always-on workloads get CUDs; bursty, interruptible batch workloads get Spot VMs — using either mechanism for the wrong workload type either wastes money (CUD on a workload that could tolerate interruption) or wastes reliability (Spot on a workload that can't tolerate interruption).

## 6. Rightsizing Recommendations (Recommender)

**Recommender** is GCP's built-in service that analyzes actual historical usage (CPU, memory, disk utilization patterns) and surfaces actionable recommendations, including:

- **VM rightsizing:** Flags Compute Engine instances that are consistently over-provisioned (e.g., a machine type with 4x the CPU actually used) and recommends a smaller machine type.
- **Idle resource detection:** Flags idle VMs, unattached persistent disks, and unused IP addresses that are accumulating cost with no traffic/usage.
- **Committed Use Discount recommendations:** Analyzes historical usage patterns to recommend how much CUD to purchase, based on demonstrated steady-state usage, reducing the guesswork in committing to a 1- or 3-year term.

**Hands-on example — listing rightsizing recommendations:**

```bash
gcloud recommender recommendations list \
  --project=my-project \
  --location=us-central1-a \
  --recommender=google.compute.instance.MachineTypeRecommender
```

**Purpose:** Surfaces machine-type downsizing recommendations for Compute Engine instances in the specified zone, based on actual observed CPU/memory utilization over the recommender's analysis window.

**Expected output (abbreviated):**

```
NAME: projects/my-project/locations/us-central1-a/recommenders/google.compute.instance.MachineTypeRecommender/recommendations/abcd-1234
DESCRIPTION: Save cost by changing machine type from n2-standard-8 to n2-standard-4.
STATE: ACTIVE
PRIMARY_IMPACT: Cost (estimated monthly savings)
```

## 7. Cloud Billing Budgets and BigQuery Export

- **Budgets and alerts:** Cloud Billing lets you define a budget amount (e.g., monthly project spend) and configure threshold alerts (e.g., notify at 50%, 90%, 100% of budget) via email or Pub/Sub — Pub/Sub notifications can trigger automated responses (e.g., a Cloud Function that disables billing on a sandbox project when a hard cap is hit).
- **Billing export to BigQuery:** Detailed, line-item billing data (resource-level, SKU-level, with labels) can be exported continuously to a BigQuery dataset, enabling arbitrary SQL analysis — cost per team (via resource labels), cost per environment, trend analysis over time, and anomaly detection, none of which is possible from the billing console's summary views alone.

**Hands-on example — querying exported billing data:**

```sql
SELECT
  service.description AS service,
  SUM(cost) AS total_cost,
  currency
FROM `my-project.billing_export.gcp_billing_export_v1_XXXXXX`
WHERE _PARTITIONTIME BETWEEN TIMESTAMP('2026-06-01') AND TIMESTAMP('2026-06-30')
GROUP BY service, currency
ORDER BY total_cost DESC;
```

**Purpose:** Breaks down last month's spend by service, giving finance/engineering a shared, queryable source of truth for cost attribution instead of relying on manual export from the console.

## 8. FinOps Principles

FinOps (a term popularized by the FinOps Foundation, applicable across all major clouds) is the operating model that ties these mechanisms together into an organizational practice, generally built around three iterative phases:

1. **Inform:** Give engineering teams real-time visibility into what their workloads cost (via labels/tags, BigQuery export, dashboards), so cost becomes a normal engineering signal rather than an opaque finance-only number.
2. **Optimize:** Act on that visibility — rightsizing via Recommender, purchasing CUDs for steady-state workloads, migrating interruptible workloads to Spot VMs, and eliminating idle resources.
3. **Operate:** Continuously govern the process — budgets and alerts catch drift early, and cost reviews become a recurring part of engineering operations rather than a one-time cleanup exercise.

A core FinOps principle is that cost accountability is shared — engineers make the technical decisions (machine type, architecture pattern) that determine cost, so they need the same visibility finance has, rather than cost being purely a finance-team concern discovered after the fact.

## 9. Comparison: GCP vs AWS vs Azure Cost Mechanisms

| Mechanism                            | GCP                                                               | AWS                                                                                                 | Azure                                                                                        |
| ------------------------------------ | ----------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| **Automatic no-commitment discount** | Sustained Use Discounts (automatic, certain machine types)        | No direct equivalent — AWS relies on Savings Plans/Reserved Instances for discounts                 | No direct equivalent — Azure relies on Reservations                                          |
| **Committed-term discount**          | Committed Use Discounts (resource-based or spend-based, 1/3-year) | Savings Plans (compute/EC2 instance, spend-based commitment) or Reserved Instances (resource-based) | Reservations (resource-based, 1/3-year)                                                      |
| **Interruptible discounted compute** | Spot VMs                                                          | Spot Instances                                                                                      | Spot Virtual Machines                                                                        |
| **License portability discount**     | N/A (GCP's licensing model differs)                               | N/A in the same form                                                                                | Azure Hybrid Benefit (reuse on-prem Windows Server/SQL Server licenses toward Azure VM cost) |
| **Rightsizing recommendations**      | Recommender                                                       | Compute Optimizer                                                                                   | Azure Advisor cost recommendations                                                           |
| **Billing data warehouse export**    | Billing export to BigQuery                                        | Cost and Usage Reports (CUR) to S3 (queryable via Athena)                                           | Cost Management exports to storage (queryable via Synapse/Power BI)                          |

> ⚠️ **Nuance:** Azure Hybrid Benefit has no direct GCP or AWS analog because it specifically monetizes existing on-premises Microsoft licensing investments — this reflects Microsoft's unique position as both an OS/software vendor and a cloud provider, a discount lever that is structurally unavailable to GCP or AWS.

## 10. Production & Enterprise Usage

- Enterprises typically purchase CUDs for baseline, steady-state capacity (e.g., the always-on production fleet) sized conservatively below actual historical minimum usage, then let Sustained Use Discounts and on-demand pricing absorb variable/peak load above that baseline.
- FinOps teams commonly build internal cost dashboards on top of the BigQuery billing export, sliced by team/project labels, and review them in a recurring (often monthly) cadence with engineering leads — treating cost review as a standing operational practice, not a one-off audit.
- Batch and CI/CD workloads at scale are migrated to Spot VMs as a default cost-reduction lever, with retry/checkpoint logic built into the job runner so preemption is a normal, handled event rather than an incident.

## 11. Common Misconceptions

- **Misconception:** "Sustained Use Discounts and Committed Use Discounts are the same thing." SUDs are automatic and require no commitment, applying only to certain machine types based on how long they run within the month; CUDs require a contractual 1- or 3-year commitment in exchange for a deeper discount rate, and the two can stack on the same workload.
- **Misconception:** "Spot VMs are simply a cheaper version of regular VMs, always safe to use." Spot VMs can be reclaimed by Google at any time with short notice — using them for stateful or non-interruptible workloads without a retry/checkpoint strategy risks unplanned data loss or downtime, not just a cost trade-off.

## 12. Interview Questions

**🎯 Beginner:** _What is the difference between a Sustained Use Discount and a Committed Use Discount?_
**Model answer:** A Sustained Use Discount is automatic and requires no commitment — GCP applies an increasing discount the longer certain eligible machine types run continuously within a billing month, with nothing to purchase or configure. A Committed Use Discount requires committing to a 1- or 3-year term of usage (either a specific resource shape or a minimum spend level) in exchange for a deeper, fixed discount rate for that term, regardless of whether usage fluctuates within it.

**🎯 Intermediate:** _When would you use Spot VMs, and what must the workload be able to tolerate?_
**Model answer:** Spot VMs are appropriate for fault-tolerant, interruptible workloads — batch processing, CI/CD build agents, rendering jobs, or GKE node pools running workloads that can be rescheduled — where the steep discount (often 60-91% off on-demand) justifies the risk that Google can reclaim the instance at any time with short notice. The workload must be designed to checkpoint progress and retry/resume after preemption; using Spot VMs for stateful databases or long-running interactive services without that resilience would trade cost savings for unacceptable reliability risk.

**🎯 Senior/Architect:** _An enterprise's monthly GCP bill has grown 40% with no corresponding growth in traffic. How would you diagnose and address this using GCP's FinOps tooling?_
**Model answer:** I'd start with the Cloud Billing export to BigQuery to break down the cost growth by service, project, and resource label over time, identifying which specific services or teams drove the increase rather than guessing. In parallel, I'd review Recommender's active recommendations across the affected projects for idle resources (unattached disks, unused IPs, idle VMs) and machine-type rightsizing opportunities, since a 40% cost increase with flat traffic strongly suggests waste rather than legitimate scale. I'd check whether steady-state workloads are running on-demand without CUD coverage — if historical usage shows a stable baseline, purchasing CUDs against that baseline would immediately reduce cost without any application change. I'd also set or tighten Cloud Billing budget alerts with Pub/Sub-triggered notifications so this kind of drift is caught within days next time, rather than discovered a full billing cycle later, and establish a recurring FinOps review cadence with engineering leads so cost visibility becomes routine.

## 13. Key Takeaways

- 🔑 Sustained Use Discounts are automatic and commitment-free; Committed Use Discounts require a 1- or 3-year term for a deeper, fixed discount — the two can stack.
- 🔑 Spot VMs offer the steepest discounts but require workloads tolerant of short-notice preemption — use for interruptible batch/CI workloads, not stateful or latency-sensitive services.
- 🔑 Recommender surfaces rightsizing, idle-resource, and CUD-purchase recommendations automatically from observed usage, closing the gap between "provisioned" and "actually needed."
- 🔑 Billing export to BigQuery turns opaque invoice totals into a queryable dataset, enabling per-team/per-environment cost attribution that the billing console summary view can't provide alone.
- 🔑 FinOps is the organizational discipline (Inform → Optimize → Operate) that makes these mechanisms a continuous practice rather than a one-time cost-cutting exercise.

## 14. Related Concepts

Compute Engine and machine types ([Section 5](../Part1/Section-05-Part1-Compute-Engine-Deep-Dive.md)), Cloud Batch for interruptible batch workloads ([Section 9](../Part1/Section-09-Part1-Cloud-Batch.md)), BigQuery for billing data analysis ([Section 44](../Part6/Section-44-Part6-BigQuery-Deep-Dive.md)), the cost optimization pillar of the Architecture Framework ([Section 56](./Section-56-Part8-Enterprise-Architecture-Patterns.md)), and disaster recovery cost trade-offs across standby strategies ([Section 58](./Section-58-Part8-Disaster-Recovery-Multi-Region-Architecture.md)) all connect directly to the cost mechanisms covered here.
