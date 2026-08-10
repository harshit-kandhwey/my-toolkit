# Section 83 (Part 11): Cost Awareness in Multi-Cloud Terraform Design

## 1. Definition

**Plain language:** Cost awareness in Terraform design means writing configuration that makes the financial impact of infrastructure decisions visible and reviewable before `apply` — not treating cost as something only discovered on next month's bill. Because Terraform's `plan` output already shows exactly what will be created, changed, or destroyed, it's a natural (if underused) checkpoint for catching expensive mistakes before they happen.

**Precise definition:** **Cost awareness** in Terraform practice spans three layers: (1) **structural choices** in resource arguments that directly determine cost — instance/VM/machine size, storage tier, data transfer patterns, reserved vs. on-demand pricing models — which differ in both mechanism and vocabulary across AWS, Azure, and GCP; (2) **tooling** that estimates cost from a `plan` before `apply` (Terraform Cloud's built-in cost estimation, covered in depth in [§90](../Part12/Section-90-Part12-Cost-Estimation-Features.md), and third-party tools like Infracost) so cost review happens at the same review checkpoint as the infrastructure change itself; and (3) **organizational patterns** — tagging for cost allocation, budget alerts tied to provisioned infrastructure, and policy-as-code guardrails ([§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) that can reject a `plan` exceeding a cost threshold before it ever reaches `apply`. None of these require a different Terraform core mechanism than what's already been covered in this roadmap — cost awareness is a discipline layered on top of ordinary `plan`/`apply`/tagging/policy mechanics, not a separate feature.

> 💡 **Tip:** The most expensive Terraform mistakes are rarely "wrong resource type" — they're usually **forgotten teardown** (a `count`/`for_each` loop left scaled up after a load test, a dev environment nobody remembered to `destroy`) and **replication multiplied silently across a loop** (a `for_each` typo that creates 50 expensive resources instead of 5). Both are visible in `terraform plan`'s resource count _before_ `apply`, which is exactly why reading plan output carefully is a cost control, not just a correctness control.

## 2. Why This Matters

- **Multi-cloud environments multiply the surface area for cost mistakes** — three different pricing models, three different reserved/committed-use discount mechanisms, and three different sets of "cheap by default vs. expensive by default" resource defaults to learn.
- **Terraform's plan-before-apply model is a structural cost-control advantage over manual provisioning** that's frequently underutilized — teams that review `plan` output only for correctness, never for cost, are leaving a genuinely useful checkpoint on the table.
- **Cost incidents from infrastructure-as-code mistakes are common and are almost always preventable in hindsight** — a `for_each` over the wrong list, a forgotten dev environment, a wildcard `count` — making this a practical, not theoretical, section of the roadmap.

## 3. Prerequisites and Dependencies

Builds on the resource provisioning patterns across [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md)-[§82](./Section-82-Part11-Multi-Region-and-Multi-Account-Subscription-Project-Patterns.md) as the concrete resource types being reasoned about cost-wise, and on `count`/`for_each` ([§23](../Part3/Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md)/[§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)) as the mechanism most responsible for cost multiplying silently. [§90](../Part12/Section-90-Part12-Cost-Estimation-Features.md) (Terraform Cloud cost estimation) and [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) (Sentinel/OPA policy-as-code) are referenced here as the deeper, tooling-specific follow-ups this section previews at a conceptual level only.

## 4. Architecture / Conceptual Diagram

```text
   Developer writes/changes .tf
              │
              ▼
   terraform plan
              │
              ├──► Read for CORRECTNESS (does this do what I meant?)
              │
              └──► Read for COST (what will this actually cost?)
                          │
              ┌───────────┴────────────┐
              ▼                        ▼
     Manual review:             Automated tooling:
     - resource count in plan   - Infracost / TFC cost estimation
       (for_each/count sanity)    diffs plan against pricing APIs
     - instance/VM/machine       - Policy-as-code (Sentinel/OPA,
       size vs. workload need      §86) can HARD-BLOCK an apply
     - storage tier appropriate   exceeding a cost delta threshold
       for access pattern
              │                        │
              └────────────┬───────────┘
                           ▼
                  terraform apply (only after both checks pass)
```

## 5. Hands-On

### 5.1 Right-Sizing via Variables Instead of Hardcoded Tiers

**Purpose:** Show a pattern that makes cost-relevant sizing an explicit, reviewable input rather than a value buried inside a resource block.

**Syntax:**

```hcl
variable "environment" {
  type = string
}

locals {
  # Explicit, reviewable mapping — cost-relevant sizing decisions
  # live in one place, not scattered across resource blocks.
  instance_size = {
    dev     = "t3.micro"
    staging = "t3.small"
    prod    = "m5.large"
  }
}

resource "aws_instance" "app" {
  ami           = "ami-0abcdef1234567890"
  instance_type = local.instance_size[var.environment]
}
```

**Example usage and expected output:**

```bash
$ terraform plan -var environment=dev
  # aws_instance.app will be created
  + instance_type = "t3.micro"

$ terraform plan -var environment=prod
  # aws_instance.app will be created
  + instance_type = "m5.large"
```

**Production usage example:** Centralizing the environment-to-size mapping in one `locals` block means a cost review only needs to check one place to understand every environment's compute spend tier, instead of auditing every individual resource block for a hardcoded size.

**Common errors:** A common mistake is defaulting `var.environment` to `"prod"` (or omitting a default entirely with no validation) — an accidental `terraform apply` without `-var environment=dev` in a dev context can provision production-tier (and production-cost) infrastructure by mistake; a `validation` block restricting the variable to known environment names, combined with no default, forces the value to always be explicit.

### 5.2 Reading Plan Output for Cost-Relevant Resource Count

**Purpose:** Demonstrate the specific plan-reading discipline that catches the most common real-world cost mistake — a loop that creates far more resources than intended.

**Syntax:**

```hcl
variable "worker_count" {
  type    = number
  default = 5
}

resource "aws_instance" "worker" {
  count         = var.worker_count
  ami           = "ami-0abcdef1234567890"
  instance_type = "m5.xlarge"
}
```

**Example usage and expected output:**

```bash
$ terraform plan -var worker_count=50    # typo: meant 5
  # aws_instance.worker[0] will be created
  # aws_instance.worker[1] will be created
  ... (48 more) ...

Plan: 50 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Reading "`Plan: 50 to add`" against an expectation of 5 is the single cheapest cost control available — it costs nothing beyond attention, catches the mistake before any API call is made, and is why `plan` review discipline ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)'s original framing, applied here specifically to cost) matters as much for cost as for correctness.

**Common errors:** `-auto-approve` in a CI pipeline without a preceding human or automated plan-count sanity check removes exactly this safety net — a `worker_count=50` typo applies immediately with no review checkpoint at all.

## 6. Production Usage Notes

- Terraform Cloud's native cost estimation ([§90](../Part12/Section-90-Part12-Cost-Estimation-Features.md)) and third-party tools like Infracost integrate directly into the `plan` step, annotating each resource in the plan output with an estimated monthly cost delta — this automates the manual "does this size/count look right" review from 5.1/5.2 into a number a reviewer can act on directly in a pull request.
- Reserved/committed-use discount models (AWS Reserved Instances/Savings Plans, Azure Reserved VM Instances, GCP Committed Use Discounts) are purchasing decisions layered on top of, not expressed by, the Terraform resource type itself — a `t3.micro` costs the same to declare in HCL whether it's on-demand or covered by a savings plan; the discount is an account-level commitment tracked outside Terraform's state entirely, though tagging resources consistently (as in [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md)-[§77](./Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md)) makes reconciling actual spend against these commitments easier.
- Ephemeral environments (feature-branch previews, load-test environments) are a common cost leak specifically because they're easy to create and easy to forget — pairing their creation with an automated expiry (a scheduled `terraform destroy` job, or a Terraform Cloud workspace auto-destroy policy) closes the "forgotten teardown" gap named in this section's opening tip.

## 7. Security Considerations

- Cost anomalies are frequently the first visible signal of a security incident — cryptocurrency-mining payloads deployed via a compromised CI/CD pipeline typically show up as an unexplained compute cost spike before they show up in any security tool — so cost monitoring functions as a secondary security control, not purely a financial one.
- Policy-as-code guardrails that block a `plan` exceeding a cost threshold ([§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) double as a security control against a compromised pipeline provisioning large amounts of unauthorized infrastructure (e.g., for cryptomining), not just a budget-discipline tool.

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Likely Cause                                                                        | Resolution Path                                                                                    |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Unexpectedly large monthly bill traced to Terraform-managed infra    | A `count`/`for_each` value was larger than intended, undetected at `plan` time      | Add plan-count sanity checks (manual review or automated cost-estimation tooling) before `apply`   |
| Dev/staging environment costs approach production levels             | Environment-to-size mapping missing, defaulted to a larger tier, or absent entirely | Centralize sizing in a reviewable `locals` map (5.1) keyed by environment, with no unsafe default  |
| Old environments still incurring cost long after their intended life | No automated expiry/destroy mechanism for ephemeral environments                    | Add scheduled `destroy` automation or workspace auto-destroy policies for short-lived environments |
| Sudden, unexplained compute cost spike                               | Possible compromised pipeline provisioning unauthorized infrastructure              | Treat as a security incident first; audit recent `apply` runs and rotate pipeline credentials      |

## 9. Best Practices

- Centralize cost-relevant sizing decisions (instance/VM/machine type, storage tier) in explicit, reviewable `locals` or variable mappings rather than scattering hardcoded values across resource blocks.
- Read `terraform plan`'s resource-count summary as a cost checkpoint, not just a correctness checkpoint, especially for any `count`/`for_each`-driven resource.
- Pair ephemeral environments with automated expiry so "forgotten teardown" cannot silently accumulate cost indefinitely.

## 10. Common Anti-Patterns / Mistakes

- **Treating cost as a finance-team concern discovered only on the monthly bill**, rather than a `plan`-time review checkpoint available before any money is spent.
- **Using `-auto-approve` in CI without any automated cost or resource-count sanity check**, removing the cheapest and most effective cost control available.
- **Letting ephemeral environments accumulate with no expiry mechanism**, so cost grows monotonically as more short-lived environments are created than are ever cleaned up.

## 11. Interview Questions

**🎯 Beginner:** _"How can `terraform plan` output help catch a cost mistake before it happens?"_
**Model answer:** `plan` shows exactly what will be created, changed, or destroyed, including the resource count for any `count`/`for_each`-driven resource, before any API call is made. Reading that output carefully — checking that the number of resources and their sizes match what was intended — catches mistakes like a loop-count typo before they cost anything, since nothing has been provisioned yet at plan time.
_What the interviewer is probing for:_ Basic recognition that `plan`'s pre-apply visibility is directly useful for cost, not just for correctness review.

**🎯 Intermediate:** _"What's the difference between a resource's on-demand cost and a reserved/committed-use discount, in terms of how each is represented in Terraform?"_
**Model answer:** The resource type and its arguments in HCL (e.g., `instance_type = "m5.large"`) determine what gets provisioned and its on-demand cost — Terraform has no native concept of a discount plan. Reserved Instances, Savings Plans, and Committed Use Discounts are purchasing commitments made at the account/billing level, tracked outside Terraform's state entirely; the same `m5.large` declared in HCL costs the same to provision whether or not it happens to be covered by a reservation. Consistent tagging (environment, team, workload) helps reconcile actual usage against these commitments after the fact, but Terraform doesn't manage the commitment itself.
_What the interviewer is probing for:_ Correct understanding of the boundary between what Terraform controls (what gets provisioned) and what it doesn't (billing/discount commitments).

**🎯 Senior:** _"A `for_each` loop meant to create resources for 5 named clients created 50 due to a data-source bug returning stale results. What plan-review or tooling changes would have caught this before `apply`?"_
**Model answer:** Several layers, ideally combined: first, basic `plan` output discipline — a reviewer expecting "5 to add" seeing "50 to add" should stop and investigate regardless of tooling; this alone would likely have caught it. Second, automated cost-estimation tooling (Infracost or Terraform Cloud's built-in estimator, [§90](../Part12/Section-90-Part12-Cost-Estimation-Features.md)) attached to the CI pipeline would surface the cost delta explicitly as a number in the PR, making the anomaly harder to overlook than a raw resource count buried in verbose plan output. Third, a policy-as-code check (Sentinel/OPA, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) with a hard ceiling on resource count or cost delta per `apply` would have blocked the run outright rather than relying on a human catching it in review. The deeper fix, once the incident is understood, is auditing why the data source returned stale/incorrect results in the first place — the `for_each` itself behaved correctly given its input; the actual bug was upstream in whatever produced the client list.
_What the interviewer is probing for:_ A layered answer (manual review, automated cost tooling, policy enforcement) rather than a single fix, plus recognizing that the `for_each` mechanism itself wasn't the root cause — its input was.

**🎯 Architect:** _"Design a cost-governance strategy for a Terraform-managed multi-cloud estate spanning AWS, Azure, and GCP with dozens of teams applying infrastructure independently."_
**Model answer:** Layer the controls rather than relying on any single one. At the PR level, require automated cost-estimation output (Infracost or equivalent, integrated per-cloud since each has its own pricing API) attached to every plan, so cost delta is visible at the same review checkpoint as the infrastructure diff itself. At the policy layer, enforce hard guardrails via Sentinel/OPA ([§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) — a per-`apply` cost-delta ceiling requiring explicit additional approval above it, and mandatory cost-allocation tags (team, environment, cost-center) on every resource type that supports tagging across all three providers, rejecting untagged resources outright. At the account/subscription/project layer ([§82](./Section-82-Part11-Multi-Region-and-Multi-Account-Subscription-Project-Patterns.md)), set budget alerts scoped to each team's boundary so cost visibility exists independently of whether the Terraform-level controls catch everything, providing defense in depth. At the organizational layer, pair every ephemeral-environment pattern with automated expiry (scheduled destroy or workspace auto-destroy) so forgotten teardown cannot silently accumulate, and schedule a recurring (not one-time) audit correlating actual cloud spend against Terraform state to catch anything that drifted outside these controls entirely — resources created manually outside Terraform, or reservations/discounts that were purchased but never reconciled against what's actually running. The key design principle across all of this is that no single layer is trusted alone — plan-time review, policy enforcement, platform-level budget alerts, and periodic reconciliation each catch different failure modes the others miss.
_What the interviewer is probing for:_ Ability to design defense-in-depth cost governance across a genuinely large, multi-team, multi-cloud organization, connecting concretely back to policy-as-code ([§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)), tagging, account boundaries ([§82](./Section-82-Part11-Multi-Region-and-Multi-Account-Subscription-Project-Patterns.md)), and recurring reconciliation rather than proposing a single silver-bullet control.

## 12. Common Misconceptions

1. **"Cost is a finance/billing concern, not something Terraform configuration itself affects."** Structural choices in HCL — sizing, count, storage tier — directly determine cost, and `plan` output is a genuine pre-spend review checkpoint.
2. **"Terraform tracks and applies reserved-instance/committed-use discounts automatically."** It doesn't — those are account-level purchasing commitments tracked outside Terraform's state; the HCL declares what gets provisioned, not which billing plan covers it.
3. **"A `for_each`/`count` mistake will be obvious from the resource names in `plan`."** It's often only visible as a resource-count summary number (`Plan: 50 to add`) unless the reviewer actually reads that line — verbose per-resource diffs can bury the anomaly.
4. **"Automated cost-estimation tooling replaces the need to read `plan` output for correctness."** It supplements, not replaces — cost tooling estimates the financial delta of whatever the plan describes; it doesn't validate that the plan describes the intended infrastructure in the first place.

## 13. 🔑 Key Takeaways

- Cost awareness is a discipline layered on existing Terraform mechanics (`plan` review, tagging, `count`/`for_each` scrutiny, policy-as-code), not a separate Terraform feature.
- The most expensive real-world mistakes are typically forgotten teardown and silently multiplied resource counts — both are visible in `plan` output before any cost is incurred.
- Reserved/committed-use discounts are account-level billing commitments outside Terraform's state; HCL determines what's provisioned, not which discount plan covers it.
- Layered controls — manual plan review, automated cost-estimation tooling, policy-as-code cost ceilings, and platform-level budget alerts — catch different failure modes and are more effective combined than any single layer alone.
- Cost anomalies can be an early signal of security incidents (e.g., unauthorized cryptomining infrastructure), making cost monitoring a secondary security control as well as a financial one.

## 14. Related Concepts & What's Next

[§90](../Part12/Section-90-Part12-Cost-Estimation-Features.md) covers Terraform Cloud's native cost-estimation feature in full mechanical depth, building directly on the conceptual framing established here. [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) covers Sentinel/OPA policy-as-code, the enforcement mechanism referenced throughout this section's cost-ceiling and tagging-requirement discussions. [§82](./Section-82-Part11-Multi-Region-and-Multi-Account-Subscription-Project-Patterns.md)'s account/subscription/project boundaries are the natural scope for the budget-alert layer described in the architect answer above. This section closes Part 11's application of Terraform fundamentals against real AWS/Azure/GCP provisioning; Part 12 now shifts to Terraform Cloud and Enterprise as a platform layer, beginning with organizations, workspaces, and runs.

**Next Section:** [§84](../Part12/Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md) — `Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md`
