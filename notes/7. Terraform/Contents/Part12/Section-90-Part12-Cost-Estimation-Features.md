# Section 90 (Part 12): Cost Estimation Features

## 1. Definition

**Plain language:** Cost estimation in Terraform Cloud/Enterprise shows you the projected monthly cost impact of a plan — "this apply will add roughly $340/month" — right alongside the plan diff, before anyone clicks apply, so cost surprises are caught during review instead of discovered on next month's cloud bill.

**Precise definition:** **Cost estimation** is a run-pipeline stage in Terraform Cloud/Enterprise that, after a plan completes, analyzes the plan's resource changes against provider pricing data and computes an estimated monthly cost delta — broken down by resource, and categorized as cost added, cost removed, or net change — displayed in the run's UI and available via the API. It supports the major cloud providers' primary resource types (AWS, Azure, GCP) with continuously updated pricing data, and can optionally be wired into policy-as-code ([§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) so a Sentinel or OPA policy can inspect the estimated cost and block a run that exceeds an organization-defined threshold, not just review it passively.

> 💡 **Tip:** Cost estimation is an **estimate**, not a bill — it prices the resource configuration itself (instance type, storage size, provisioned throughput) using published list pricing, but it cannot account for actual usage-based costs that depend on runtime behavior (data transfer volume, API call counts, autoscaling behavior under real load) or negotiated/reserved pricing discounts. Treat the number as directional — "is this plan roughly what I expect, or has something gotten dramatically more expensive" — not as a precise forecast of the next invoice.

## 2. Why This Matters

- **Cost review happens at the same point as technical review**, in the same PR/plan artifact reviewers already look at — rather than being a separate, after-the-fact FinOps process disconnected from the change itself.
- **Catches expensive mistakes before they're expensive.** A variable default accidentally left at `db.r5.24xlarge` instead of `db.t3.micro` shows up as a glaring cost delta in the plan review, not as a shocking line item weeks later.
- **Makes cost governance enforceable, not just visible.** Paired with policy-as-code ([§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)), an organization can hard-block any plan projected to exceed a defined monthly cost threshold, the same way it can block a public S3 bucket.
- **Gives non-cost-specialist reviewers a cost signal they wouldn't otherwise have.** Most engineers reviewing a Terraform plan aren't fluent in every instance type's pricing — a computed estimate surfaces that information without requiring the reviewer to look it up manually.
- **Supports incremental cost accountability per team/workspace.** Because estimates are computed per run and workspace, cost impact can be tracked and attributed to the team or component responsible for a given workspace over time.

## 3. Prerequisites and Dependencies

Builds on the run pipeline model ([§84](./Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md), [§85](./Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md)) and the policy-as-code stage it can integrate with ([§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)). Some familiarity with the general cost-awareness concepts introduced in [§83](../Part11/Section-83-Part11-Cost-Awareness-in-Multi-Cloud-Terraform-Design.md) (Cost Awareness in Multi-Cloud Terraform Design) is useful context — this section covers the automated, run-pipeline-integrated mechanism specifically, where [§83](../Part11/Section-83-Part11-Cost-Awareness-in-Multi-Cloud-Terraform-Design.md) covers broader design-level cost thinking.

## 4. Architecture / Conceptual Diagram

```text
   terraform plan (computed diff)
              │
              ▼
   ┌─────────────────────────────────────────────────┐
   │            COST ESTIMATION STAGE                │
   │                                                 │
   │  For each resource_change:                      │
   │   - match resource type + attributes            │
   │     against provider pricing data               │
   │   - compute estimated monthly cost delta        │
   │     (added / removed / net change)              │
   │                                                 │
   │  Result: "$0.00/mo → $340.12/mo (+$340.12/mo)"  │
   └────────────────────┬────────────────────────────┘
                        │
        ┌───────────────┴─────────────────┐
        ▼                                 ▼
  displayed in run UI/API           (optional) fed into policy check
  for human review                  e.g. Sentinel rule:
                                     "reject if delta > $500/mo"
                        │
                        ▼
              proceeds to policy-check stage (§86)
              and then apply, as in the normal pipeline
```

- Cost estimation runs after plan and can feed directly into the policy-check stage as an input a Sentinel/OPA policy can inspect — it isn't only a passive display.
- The estimate reflects the plan's proposed resource configuration, not observed runtime usage — it has no visibility into what happens after apply.
- Per-resource breakdown lets a reviewer see which specific resource in a multi-resource plan is driving the cost delta, not just an aggregate number.

## 5. Hands-On

### 5.1 Reading a Cost Estimate in Run Output

**Purpose:** Show what the cost estimation stage produces alongside a normal plan.

**Example usage and expected output:**

```text
Terraform Cloud — Run #run-8pQd3RtY9kLmNx2A

Plan: 2 to add, 0 to change, 0 to destroy.

Cost Estimate:
  Resource                         Monthly Cost   Delta
  aws_db_instance.replica          $187.20        +$187.20
  aws_instance.worker (x3)         $152.64        +$152.64
  ─────────────────────────────────────────────────────
  Total estimated monthly cost delta:              +$339.84

  Prior estimated monthly cost:  $1,204.55
  New estimated monthly cost:    $1,544.39
```

**Production usage example:** A reviewer approving a PR that adds a read replica sees this breakdown directly in the TFC run view, confirms the ~$340/month increase is expected and budgeted, and approves the apply — the cost conversation happens in the same review, not in a separate spreadsheet afterward.

**Common errors:** Expecting the estimate to reflect data-transfer or request-volume costs (common with services like S3 or API Gateway) leads to underestimating real cost, since usage-based pricing components generally aren't — and often can't be — captured by a static plan-time estimate.

### 5.2 Gating a Run on Cost via Sentinel

**Purpose:** Show cost estimation feeding directly into a policy check, not just passive display, tying together [§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) and this section.

**Syntax:**

```python
import "tfrun"

max_monthly_delta = 500.0

main = rule {
  tfrun.cost_estimate.delta_monthly_cost as float(tfrun.cost_estimate.delta_monthly_cost) <= max_monthly_delta
}
```

**Example usage and expected output:**

```text
Sentinel Result: false

Policy "cost-threshold.sentinel":
  ✖ main = false

  tfrun.cost_estimate.delta_monthly_cost is 780.40, which exceeds
  max_monthly_delta of 500.0

This plan did not pass a hard-mandatory policy check. Apply halted.
```

**Production usage example:** A workspace representing a shared staging environment enforces this policy as hard-mandatory so any single change proposing more than $500/month in added cost requires explicit approval to raise the threshold or route through a separate budget-approval process, rather than applying silently.

**Common errors:** Setting the threshold too low for a legitimately large but expected change (a planned capacity increase) causes routine, budgeted work to be blocked — thresholds need periodic review against actual expected spend, not a single "set once" value.

## 6. Production Usage Notes

- **Cost estimation coverage varies by resource type.** Well-established, widely used resource types (EC2 instances, RDS, common Azure/GCP compute and storage) have solid pricing coverage; niche or newly released resource types may not yet be priced, and the estimate silently omits them rather than erroring — worth knowing so a "$0 estimated delta" isn't mistaken for "definitely no cost impact."
- **Estimates use list pricing, not negotiated discounts.** An organization with Reserved Instances, Savings Plans, or negotiated enterprise discounts will see estimates that overstate real cost relative to their actual bill — useful for relative comparison between plans, less useful as an absolute number without adjustment.
- **The feature typically requires a specific TFC/TFE plan tier** (generally bundled with the same tiers that include Sentinel/governance features) — teams on lower tiers may not have cost estimation available at all, which is worth confirming before designing a workflow around it.

## 7. Security Considerations

- Cost estimation itself has minimal direct security surface, but a cost-threshold policy tied into the apply-gating pipeline (as in §5.2) becomes a governance control worth protecting the same way any other hard-mandatory policy is protected — a broken or bypassed cost policy silently removes a real spend control, not just a display feature.
- No cloud credentials or additional API calls to the target cloud provider are needed to compute the estimate — it's derived entirely from the plan's resource attributes matched against static pricing data, so the estimation stage doesn't itself expand the workspace's credential exposure.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                     | Likely Cause                                                                                                | Resolution Path                                                                                                               |
| ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Cost estimate shows $0 for a resource that clearly costs money                              | The specific resource type/attribute combination isn't covered by the pricing data yet                      | Treat as "not estimated," not "confirmed free"; verify actual pricing manually for uncovered resource types                   |
| Estimated cost is significantly higher than the team's actual bill for equivalent resources | Estimate uses list pricing; the organization has Reserved Instances, Savings Plans, or negotiated discounts | Treat the estimate as directional/relative rather than an absolute forecast; adjust expectations accordingly, not the tooling |
| Cost estimation stage doesn't appear in run output at all                                   | Feature not enabled or not included in the organization's TFC/TFE plan tier                                 | Verify the organization's subscription tier includes cost estimation; enable it in workspace settings if available but off    |
| A Sentinel cost-threshold policy blocks a run unexpectedly                                  | Threshold value is stale relative to current, legitimately higher expected spend patterns                   | Review and adjust the threshold periodically as part of normal policy maintenance, not just when it becomes a blocker         |

## 9. Best Practices

- Treat cost estimates as a relative signal for review, not an authoritative forecast — pair with actual billing/cost-management tooling (cloud-native cost explorers) for precise accounting.
- Where thresholds are used for policy gating, review and adjust them on a regular cadence tied to actual budget cycles, not as a one-time setup step.
- Surface per-resource cost breakdowns in review culture explicitly — a reviewer glancing only at the aggregate delta can miss that one specific, avoidable resource is driving most of the cost.

## 10. Common Anti-Patterns / Mistakes

- **Treating the cost estimate as the actual bill.** It's list-price-based and blind to usage-driven costs and discounts — using it as a precise budget number rather than a review signal leads to real forecasting errors.
- **Setting a single global cost threshold policy across wildly different workspace types.** A dev-sandbox workspace and a production database workspace have very different legitimate cost profiles; one threshold rarely fits both sensibly.
- **Ignoring "$0 estimated" for uncovered resource types as confirmation of no cost.** This silently misses real spend from resource types the estimation engine simply doesn't price yet.

## 11. Interview Questions

**🎯 Beginner:** _"What does Terraform Cloud's cost estimation feature show you?"_
**Model answer:** After a plan completes, it shows an estimated monthly cost delta for the proposed changes — broken down per resource — computed against provider pricing data, so reviewers can see the projected cost impact of a change alongside the technical diff before approving an apply.
_What the interviewer is probing for:_ Basic understanding of what the feature actually displays and when in the pipeline it runs.

**🎯 Intermediate:** _"What are the limitations of Terraform Cloud's cost estimate, and why shouldn't a team treat it as their actual forecasted bill?"_
**Model answer:** It's based on static list pricing matched against the plan's resource configuration — it can't account for usage-based costs that depend on runtime behavior (data transfer, request volume, autoscaling under real load), and it doesn't reflect negotiated discounts, Reserved Instances, or Savings Plans the organization may have. It's most useful as a relative, directional signal during review ("does this look roughly right, or has something gotten unexpectedly expensive") rather than a precise forecast of the next invoice.
_What the interviewer is probing for:_ Whether the candidate understands the estimate's actual scope and limitations, not just that the feature exists.

**🎯 Senior:** _"How would you use cost estimation together with policy-as-code to actually enforce a budget, rather than just displaying numbers for review?"_
**Model answer:** Write a Sentinel (or OPA, if applicable) policy that reads the run's computed cost-estimate delta — via Sentinel's `tfrun` import exposing `cost_estimate.delta_monthly_cost`, for example — and compares it against an organization- or workspace-appropriate threshold, failing hard-mandatory if exceeded. This converts cost estimation from a passive display into an actual gate in the run pipeline, the same mechanism used for security policies ([§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)). The key design decision is threshold granularity: a single org-wide threshold rarely fits every workspace's legitimate cost profile, so thresholds are usually set per workspace or per workspace category (dev vs. prod, by team budget) rather than globally.
_What the interviewer is probing for:_ Practical knowledge of wiring cost estimation into the same policy engine covered earlier, not treating it as an isolated, display-only feature.

**🎯 Architect:** _"A finance team wants Terraform Cloud's cost estimation to be the authoritative source for infrastructure budget forecasting across the organization. What would you tell them about relying on it that way?"_
**Model answer:** Explain clearly that plan-time cost estimation is structurally unable to serve as an authoritative forecast: it prices resource configuration at list rates, blind to negotiated discounts/reservations and entirely blind to usage-driven costs that often dominate real cloud bills (data transfer, request volume, storage growth over time). It's a valuable point-in-time review signal for catching gross misconfigurations before they're expensive, and useful for relative trend tracking (is this quarter's infrastructure additions trending more expensive than last quarter's), but actual budget forecasting needs to be grounded in the cloud provider's own cost-management tooling (AWS Cost Explorer, Azure Cost Management, GCP's Billing reports) reconciled against actual usage, ideally cross-referenced with — not replaced by — Terraform's plan-time estimates. Positioning it correctly to finance avoids a credibility gap when actual bills diverge from Terraform's estimates for reasons that were never within the estimate's scope to capture.
_What the interviewer is probing for:_ Ability to set accurate expectations with a non-technical stakeholder about a tool's actual scope, rather than overselling a feature's capability.

## 12. Common Misconceptions

1. **"Cost estimation shows the actual bill Terraform's changes will produce."** It's a list-price estimate of the resource configuration, blind to usage-based costs and negotiated discounts — directional, not authoritative.
2. **"Every resource type is covered by cost estimation."** Coverage is strongest for common, well-established resource types; niche or newly released types may not be priced at all, silently showing as no cost impact.
3. **"Cost estimation is purely a display feature with no enforcement capability."** It can be wired directly into policy-as-code (Sentinel/OPA) to actually block runs exceeding a defined cost threshold, not just show numbers for manual review.
4. **"Cost estimation requires cloud credentials to compute."** It's computed entirely from the plan's resource attributes against static pricing data — no additional calls to the target cloud provider are needed.

## 13. 🔑 Key Takeaways

- Cost estimation runs after plan and before apply, showing a per-resource and aggregate estimated monthly cost delta directly in the run pipeline.
- It's based on static list pricing matched to the plan's resource configuration — blind to usage-based costs and negotiated discounts, so treat it as directional, not authoritative.
- Coverage varies by resource type; uncovered types show no cost impact, which is easy to mistake for "confirmed free."
- Cost estimates can feed directly into policy-as-code to enforce hard cost thresholds, not just display numbers passively.
- Real budget forecasting still needs cloud-provider cost-management tooling reconciled against actual usage — cost estimation is a review aid, not a replacement for that.

## 14. Related Concepts & What's Next

[§91](./Section-91-Part12-Teams-RBAC-and-SSO-in-Terraform-Cloud-Enterprise.md) covers the team/RBAC/SSO model that governs who can approve runs carrying a given cost estimate. [§83](../Part11/Section-83-Part11-Cost-Awareness-in-Multi-Cloud-Terraform-Design.md) covers broader cost-awareness design principles this section's automated mechanism supports. [§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) covers the policy-as-code engine cost thresholds are implemented through.

**Next Section:** [§91](./Section-91-Part12-Teams-RBAC-and-SSO-in-Terraform-Cloud-Enterprise.md) — `Section-91-Part12-Teams-RBAC-and-SSO-in-Terraform-Cloud-Enterprise.md`
