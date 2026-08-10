# Section 86 (Part 12): Sentinel and OPA Policy-as-Code

## 1. Definition

**Plain language:** Policy-as-code means writing rules like "no S3 bucket may be public" or "every instance must be tagged with a cost center" as actual code that automatically checks every Terraform plan before it's allowed to apply — instead of relying on a human reviewer to remember and manually enforce those rules on every pull request.

**Precise definition:** **Policy-as-code** in the Terraform ecosystem is enforced primarily through two engines that inspect a generated plan (or its JSON representation) against a set of author-defined rules and either pass, soft-fail (warn), or hard-fail (block) the run before apply: **Sentinel**, HashiCorp's proprietary policy language, available only in Terraform Cloud (Team & Governance tier and above) and Terraform Enterprise; and **Open Policy Agent (OPA)**, an open-source, CNCF-hosted general-purpose policy engine using the **Rego** query language, usable both inside Terraform Cloud/Enterprise (as an alternative policy framework) and independently in any CI pipeline via the `conftest` tool or direct OPA evaluation against `terraform show -json` plan output. Both operate on the same underlying artifact — the plan's structured JSON — but differ in language, licensing, and portability.

> 💡 **Tip:** The deciding question when choosing between them isn't "which is more powerful" — both can express essentially the same checks — it's "does this policy need to run anywhere outside Terraform Cloud/Enterprise?" Sentinel is tightly coupled to HashiCorp's platform and cannot run standalone in a generic CI job; OPA/Rego is a general-purpose engine already used for Kubernetes admission control, API authorization, and CI gates elsewhere, so a team standardizing policy tooling across multiple systems (not just Terraform) usually gravitates to OPA specifically because it isn't Terraform-specific at all.

## 2. Why This Matters

- **Human review doesn't scale as a compliance control.** A reviewer can miss that a new subnet lacks a required tag; a policy check never does, because it evaluates the same rule against every single plan mechanically.
- **Governance can be enforced automatically, not just documented.** "All production databases must have encryption enabled" stops being a wiki page reviewers are supposed to remember and becomes a hard gate the run pipeline itself enforces.
- **Policy checks run inside the same pipeline as plan/apply**, giving them access to the actual computed diff — not just static configuration — so they can catch things static analysis ([§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md)) alone cannot, like "this specific apply would increase the security group's open port range."
- **Advisory vs. mandatory policies let organizations phase in governance.** Soft-mandatory (warn, can be overridden with justification) and hard-mandatory (block, no override) enforcement levels let a team introduce a new rule without immediately breaking every existing workspace.
- **Cost and security policy can be unified in one gate.** The same run pipeline stage that blocks an over-permissive security group can also block a plan that would exceed a cost threshold, tying into the cost estimation covered in [§90](./Section-90-Part12-Cost-Estimation-Features.md).

## 3. Prerequisites and Dependencies

Assumes the run pipeline model from [§84](./Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md) and [§85](./Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md) — policy checks are a stage inserted between plan and apply in that pipeline. No prior policy-as-code experience is assumed. [§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) revisits policy testing specifically in a CI context, and [§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md) covers a related but distinct discipline: static analysis of raw configuration (tfsec, Checkov) rather than policy checks against a computed plan.

## 4. Architecture / Conceptual Diagram

```text
   terraform plan (computed diff, as structured JSON: tfplan/v2)
              │
              ▼
   ┌──────────────────────────────────────────────────┐
   │           POLICY CHECK STAGE                     │
   │                                                  │
   │  Sentinel (TFC/TFE only)     OPA / Rego          │
   │  ┌─────────────────────┐    ┌──────────────────┐ │
   │  │ import "tfplan/v2"  │    │ input.resource_  │ │
   │  │   as tfplan         │    │  changes[_]      │ │
   │  │ main = rule { ... } │    │ deny[msg] { ... }│ │
   │  └─────────────────────┘    └──────────────────┘ │
   │                                                  │
   │  Result per policy: pass / soft-fail / hard-fail │
   └────────────────────┬─────────────────────────────┘
                        │
        ┌───────────────┴─────────────────┐
        ▼                                 ▼
  all policies pass              any hard-mandatory policy fails
  (or soft-fail overridden)      → run halted, apply blocked
        │
        ▼
   proceeds to apply stage (§84's run pipeline)
```

- Both engines receive the same input conceptually — the plan's resource changes — but Sentinel's `tfplan/v2` import is TFC/TFE-native, while OPA needs the plan exported as JSON (`terraform show -json plan.out`) to evaluate against.
- The policy-check stage sits strictly after plan and before apply, meaning a failing policy prevents the apply from ever running — the diff was computed, but never executed.
- Enforcement level (advisory / soft-mandatory / hard-mandatory) determines whether a failure merely warns or actually halts the pipeline.

## 5. Hands-On

### 5.1 A Sentinel Policy Restricting Instance Types

**Purpose:** Show real Sentinel syntax enforcing a governance rule against the plan.

**Syntax:**

```python
import "tfplan/v2" as tfplan

allowed_types = ["t3.micro", "t3.small", "t3.medium"]

instances = filter tfplan.resource_changes as _, rc {
  rc.type is "aws_instance" and
  (rc.change.actions contains "create" or rc.change.actions contains "update")
}

main = rule {
  all instances as _, instance {
    instance.change.after.instance_type in allowed_types
  }
}
```

**Example usage and expected output:**

```text
Sentinel Result: false

Policy "restrict-instance-types.sentinel":
  ✖ main = false

  instances["aws_instance.app"].change.after.instance_type is "m5.4xlarge",
  which is not in allowed_types ["t3.micro", "t3.small", "t3.medium"]

This plan did not pass a hard-mandatory policy check. Apply halted.
```

**Production usage example:** A platform team enforces this policy organization-wide as hard-mandatory so no workspace can accidentally provision an oversized (and expensive) instance type outside an approved list, catching the mistake at plan time rather than on the next month's bill.

**Common errors:** Forgetting `and (rc.change.actions contains "create" or ... "update")` means the policy also evaluates resources being destroyed, incorrectly flagging a plan that's only removing an oversized instance, not creating one.

### 5.2 The Same Check Expressed in OPA/Rego

**Purpose:** Show the open-source equivalent, runnable outside Terraform Cloud entirely via `conftest`.

**Syntax:**

```rego
package terraform.instance_types

allowed_types := {"t3.micro", "t3.small", "t3.medium"}

deny[msg] {
  rc := input.resource_changes[_]
  rc.type == "aws_instance"
  rc.change.actions[_] == "create"
  not allowed_types[rc.change.after.instance_type]
  msg := sprintf("aws_instance.%s uses disallowed instance_type %q", [rc.name, rc.change.after.instance_type])
}
```

**Example usage and expected output:**

```bash
$ terraform show -json tfplan.binary > plan.json
$ conftest test plan.json --policy instance_types.rego

FAIL - plan.json - terraform.instance_types - aws_instance.app uses disallowed instance_type "m5.4xlarge"

1 test, 0 passed, 1 failed
```

**Production usage example:** A team running Terraform entirely via plain CLI + GitHub Actions (no Terraform Cloud) adds this `conftest` check as a required CI job — enforcing the identical governance rule without any dependency on TFC/TFE's Team & Governance tier.

**Common errors:** Running `conftest` against the raw `.tf` files instead of the exported plan JSON only catches static misconfigurations, not computed values (e.g., an instance type set via a variable that only resolves at plan time) — OPA needs the plan JSON, same as Sentinel needs `tfplan/v2`, to see actual computed values.

## 6. Production Usage Notes

- **Sentinel policies are organized into policy sets** attached to workspaces (by VCS repo or directly), each with an enforcement level per policy — this lets a shared policy library apply differently across workspaces (hard-mandatory in production, advisory in dev).
- **OPA's portability is its main production advantage outside TFC/TFE.** The exact same `.rego` files can gate Terraform plans, Kubernetes manifests, and API authorization decisions, letting a security team maintain one policy engine and language across systems instead of a Terraform-specific one.
- **Policy checks add latency to every run**, proportional to the number and complexity of policies evaluated — a policy set with dozens of complex Sentinel/Rego rules measurably slows the plan-to-apply cycle, which matters for teams optimizing for fast iteration in lower environments.

## 7. Security Considerations

- Policy-as-code is a genuine security control, not just a linting nicety — a hard-mandatory policy blocking public S3 buckets or 0.0.0.0/0 ingress rules prevents that misconfiguration from ever reaching apply, closing a gap that code review alone reliably misses at scale.
- Policies themselves are code and need the same review rigor as the infrastructure they govern — a subtly wrong Rego/Sentinel rule that always evaluates to "pass" provides false assurance that's worse than no policy at all, since it looks like a control exists.
- Because policy checks see the fully computed plan (including resolved sensitive values in some cases), the policy execution environment itself needs to be trusted with the same sensitivity as the plan/apply execution environment — it isn't a lower-trust sandbox by default.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                 | Likely Cause                                                                                                                       | Resolution Path                                                                                                                        |
| --------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| Sentinel policy always passes even for resources that should fail                       | The `filter` expression's condition doesn't match the actual `resource_changes` shape (e.g., wrong `actions` check)                | Print/inspect `tfplan.resource_changes` structure directly in a test policy; verify the filter actually selects the intended resources |
| `conftest` reports zero results even though a violating resource exists                 | Plan JSON wasn't regenerated after the latest `terraform plan`, or `package` name in `.rego` doesn't match what `conftest` expects | Regenerate `terraform show -json` output fresh; confirm `--policy` path and package naming                                             |
| Run blocked by a policy that's supposed to be advisory                                  | Policy set's enforcement level was configured as soft-mandatory or hard-mandatory rather than advisory                             | Correct the enforcement level on the policy set attachment, not the policy code itself                                                 |
| Policy check passes locally with `conftest` but fails identically in CI (or vice versa) | Different plan JSON was generated (e.g., different variable values, different Terraform version between environments)              | Ensure CI and local runs use the same `.tfvars`/variable inputs and Terraform version when reproducing                                 |

## 9. Best Practices

- Start new policies as **advisory**, observe results across real runs for a period, then promote to soft- or hard-mandatory once false positives are ruled out.
- Keep policy code in its own version-controlled repository, reviewed with the same rigor as infrastructure code, since a broken policy either blocks all applies or silently lets everything through.
- Prefer OPA/Rego over Sentinel specifically when the same policies need to also govern non-Terraform systems, to avoid maintaining two policy languages for overlapping governance goals.

## 10. Common Anti-Patterns / Mistakes

- **Writing policies that only check static configuration instead of the computed plan.** This duplicates what static analysis tools ([§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md)) already do and misses issues only visible in resolved values — the whole point of plan-based policy is seeing actual computed state.
- **Setting every new policy to hard-mandatory immediately.** This risks blocking legitimate, unanticipated use cases the policy author didn't think of, without an advisory period to surface false positives first.
- **Treating Sentinel and OPA as interchangeable with zero migration cost.** Rewriting a policy library from one language to the other is real engineering work — the "just switch engines" decision should be made once, deliberately, not per-policy.

## 11. Interview Questions

**🎯 Beginner:** _"What problem does policy-as-code solve that code review alone doesn't?"_
**Model answer:** Policy-as-code enforces rules mechanically against every single plan, so a rule like "no public S3 buckets" is never missed due to reviewer fatigue or oversight — it's checked identically and automatically every time, unlike relying on a human to remember and catch every violation in review.
_What the interviewer is probing for:_ Understanding that policy-as-code is about consistency and scale of enforcement, not just "more rules."

**🎯 Intermediate:** _"What's the difference between Sentinel and OPA, and when would you choose one over the other?"_
**Model answer:** Sentinel is HashiCorp's proprietary policy language, available only within Terraform Cloud/Enterprise's governance tiers, and evaluates directly against the `tfplan/v2` import inside TFC's run pipeline. OPA is an open-source, general-purpose policy engine using the Rego language that can evaluate a Terraform plan's JSON output (via `conftest` or direct integration) both inside TFC/TFE and completely independently in any CI pipeline. Choose Sentinel if already committed to TFC/TFE's governance tier and want native integration; choose OPA if policy needs to be portable across systems beyond Terraform, or if the team isn't using Terraform Cloud/Enterprise at all.
_What the interviewer is probing for:_ Accurate understanding that these aren't just "two flavors of the same thing" — licensing and platform coupling are real, practical differentiators.

**🎯 Senior:** _"Your team wants to enforce 'every aws_db_instance must have `storage_encrypted = true`' before it ever applies. Walk through implementing this as a hard-mandatory policy and explain what could still go wrong."_
**Model answer:** Write a Sentinel or Rego rule that filters `resource_changes` for `type == "aws_db_instance"` with a create or update action, and asserts `change.after.storage_encrypted == true`, attaching it as hard-mandatory to the relevant policy set. What could still go wrong: the policy only catches this at plan/apply time through TFC/TFE (or CI, for OPA) — a resource created outside this pipeline (manual console change, a different CI path not wired to the policy check) bypasses it entirely, so policy-as-code needs to be paired with drift detection ([§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)) to catch out-of-band changes; also, if the attribute is set via a variable whose default silently changes, or if the policy's filter logic has a subtle bug (e.g., missing the "update" action, only checking "create"), an in-place modification that removes encryption could slip through undetected.
_What the interviewer is probing for:_ Whether the candidate understands policy-as-code's actual coverage boundary — it governs the pipeline it's attached to, not infrastructure reality as a whole.

**🎯 Architect:** _"You're standardizing policy enforcement across Terraform, Kubernetes, and internal API gateways for a security-conscious organization. Would you pick Sentinel, OPA, or both — and why?"_
**Model answer:** OPA, primarily — it's already the de facto standard for Kubernetes admission control (Gatekeeper) and is commonly used for API authorization, so standardizing on Rego across all three systems means one policy language, one team skill set, and potentially shared policy libraries for cross-cutting concerns (tagging standards, naming conventions) expressible similarly across systems. Sentinel would only be added if the organization is deeply committed to Terraform Cloud/Enterprise specifically and wants the tightest native integration with TFC's run pipeline (e.g., built-in cost-estimation-aware policies, [§90](./Section-90-Part12-Cost-Estimation-Features.md)) — but that's a narrower, Terraform-specific benefit that doesn't extend to the other two systems. The trade-off to flag explicitly: OPA's TFC/TFE integration, while supported, is generally considered less deeply native than Sentinel's, so there's a real integration-smoothness cost to the portability gain — worth surfacing to leadership as a deliberate trade-off, not glossing over.
_What the interviewer is probing for:_ Systems-level thinking about tooling standardization trade-offs across an organization, not just a Terraform-only answer.

## 12. Common Misconceptions

1. **"Sentinel and OPA can express fundamentally different kinds of policies."** Both are Turing-complete-enough for essentially any check expressible against structured plan data — the difference is licensing, platform coupling, and ecosystem, not raw capability.
2. **"Policy-as-code replaces static analysis tools like tfsec/Checkov."** They're complementary: static analysis ([§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md)) scans raw configuration before a plan even exists; policy-as-code evaluates the computed plan — different stages, different blind spots each covers.
3. **"OPA only works with Terraform Cloud."** OPA/Rego with `conftest` works entirely standalone against exported plan JSON in any CI pipeline, with zero dependency on Terraform Cloud or Enterprise.
4. **"A passing policy check means the infrastructure is compliant."** It means the plan that was checked complied at that moment — subsequent manual changes or drift outside the pipeline aren't covered by a one-time plan-stage check ([§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md) covers ongoing drift/compliance monitoring).

## 13. 🔑 Key Takeaways

- Policy-as-code inserts an automated check between plan and apply, evaluating the computed diff against author-defined rules rather than relying on manual review.
- Sentinel is proprietary and TFC/TFE-only; OPA/Rego is open-source and portable across Terraform and non-Terraform systems alike.
- Both operate on the plan's structured output (`tfplan/v2` for Sentinel, exported JSON for OPA) — not just static `.tf` configuration.
- Enforcement levels (advisory, soft-mandatory, hard-mandatory) let policies be phased in without immediately blocking every workspace.
- Policy-as-code governs the pipeline it's attached to; it doesn't catch changes made outside that pipeline, which is what drift detection ([§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)) is for.

## 14. Related Concepts & What's Next

[§87](./Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md) covers the private module and provider registries that often ship alongside policy-governed workspaces in an enterprise setup. [§90](./Section-90-Part12-Cost-Estimation-Features.md) covers cost estimation, another stage in the same run pipeline. [§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md) covers static analysis tools that check raw configuration rather than computed plans, and [§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) revisits policy testing specifically as a CI concern.

**Next Section:** [§87](./Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md) — `Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md`
