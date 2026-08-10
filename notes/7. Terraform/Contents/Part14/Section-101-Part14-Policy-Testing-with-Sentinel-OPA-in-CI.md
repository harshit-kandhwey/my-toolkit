# Section 101 (Part 14): Policy Testing with Sentinel/OPA in CI

## 1. Definition

**Plain language:** Plan-based tests ([§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)) and integration tests ([§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)) check that a specific configuration does what its author intended. Policy testing checks something different: does this change comply with rules the _organization_ sets, regardless of what any individual author intended — no public S3 buckets, no unencrypted databases, no instances outside approved regions. Sentinel and OPA are the two dominant engines for writing those organizational rules as code and enforcing them automatically in CI, rather than relying on a human reviewer to remember and manually check every rule on every PR.

**Precise definition:** **Sentinel** is HashiCorp's proprietary policy-as-code framework, natively integrated into Terraform Cloud/Enterprise ([§84](../Part12/Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md), [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)), that evaluates policies written in the Sentinel language against a Terraform plan's structured data, enforcing one of three outcomes per policy: **advisory** (logs a violation but doesn't block), **soft-mandatory** (blocks unless an authorized user explicitly overrides), or **hard-mandatory** (blocks unconditionally, no override possible). **OPA (Open Policy Agent)**, evaluated via its Rego policy language, is a general-purpose, CNCF-hosted policy engine not tied to any single vendor — for Terraform specifically, it's most commonly run via **Conftest**, a CLI wrapper around OPA purpose-built for testing structured configuration files (including a `terraform show -json` plan) against Rego policies, making it usable in any CI system, not just Terraform Cloud/Enterprise.

> 💡 **Tip:** The practical decision between the two is largely about where you run Terraform. If the organization is on Terraform Cloud/Enterprise, Sentinel is natively wired into the run pipeline with zero extra plumbing — plans are automatically evaluated before apply. If Terraform runs anywhere else (self-hosted CI, open-source Terraform with a non-HashiCorp backend), OPA/Conftest is the tool that works regardless of where or how `plan` is invoked, because it's just consuming a JSON file, not a proprietary run pipeline.

## 2. Why This Matters

- **Policy testing scales governance past what human review can reliably enforce.** A reviewer manually checking "does this PR create a public S3 bucket" across dozens of PRs a week eventually misses one; a policy engine checking the same rule against the plan JSON never gets tired or distracted.
- **Policies are testable and versionable, like any other code.** Because Sentinel/Rego policies live in files under version control, they get code review, changelogs, and their own test suites — a governance rule change is auditable in exactly the way a verbal "team standard" never is.
- **Different enforcement levels map to real organizational risk tolerance.** Sentinel's advisory/soft-mandatory/hard-mandatory tiers (and OPA's equivalent pattern of warn-vs-deny rules) let an organization roll out a new rule as advisory first (measure impact, avoid breaking existing pipelines) before promoting it to a hard block — which matters enormously for adopting new policy without a "big bang" cutover.
- **Policy checks operate on exactly the same plan JSON that plan-based testing ([§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)) produces**, meaning the investment in getting clean, structured plan data pays off across both testing strategies rather than being duplicated.
- **Cost and compliance policies belong here, not in code review.** Rules like "no `t3.2xlarge` or larger without a cost-center tag" or "database resources must have `deletion_protection = true`" are exactly the kind of numeric/structural check a policy engine enforces reliably and a human reviewer often forgets under review-fatigue.

## 3. Prerequisites and Dependencies

This section depends directly on [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)'s JSON plan output, which is the data both Sentinel and OPA/Conftest evaluate against — the ad hoc `jq` assertions shown there are, conceptually, a manual precursor to what a real policy engine formalizes. It also builds on [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)'s introduction to Sentinel and OPA within Terraform Cloud specifically; this section focuses on running policy checks in a general CI pipeline ([§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) rather than exclusively inside Terraform Cloud's run pipeline. Familiarity with the security-scanning tools from [§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md) (tfsec, Checkov, Terrascan) is useful context — those tools scan _static configuration_ for known-bad patterns, whereas Sentinel/OPA here evaluate the _actual plan_ (what would really happen, including computed values), a meaningfully different and complementary layer.

## 4. Architecture / Conceptual Diagram

```text
   terraform plan -out=tfplan
            │
            ▼
   terraform show -json tfplan > plan.json
            │
            ├──────────────────────────────┬───────────────────────────────
            ▼                              ▼
   SENTINEL (Terraform Cloud/Enterprise)   OPA / CONFTEST (any CI)
            │                              │
   Policy set attached to workspace        conftest test plan.json
   Evaluated automatically as part            --policy policies/
   of the TFC run pipeline, before apply           │
            │                                      ▼
            ▼                              policies/*.rego evaluated
   enforcement_level per policy:           against plan.json
   - advisory   → log only, never blocks            │
   - soft-mandatory → blocks, overridable           ▼
     by an authorized user                  deny[msg] rules → pipeline
   - hard-mandatory → blocks, no override    exit code != 0 → CI fails
            │                                       │
            ▼                                       ▼
   Run halted or proceeds to apply         Merge blocked via CI status check
   based on policy result                  (branch protection rule)
```

- Both engines converge on the same input (the structured plan) but diverge on _where_ they run: Sentinel is a run-pipeline-native step inside Terraform Cloud/Enterprise; OPA/Conftest is a CLI step that fits into any CI system's job graph.
- Sentinel's three-tier enforcement model (advisory/soft-mandatory/hard-mandatory) has no single built-in OPA equivalent — teams using OPA typically approximate the same distinction by convention (`warn` vs. `deny` rules in Rego, with CI treating `deny` as a hard failure and `warn` as a logged-but-passing check).
- Neither tool replaces the other layers in this Part: policy testing checks organizational rules against a specific proposed change; it doesn't replace plan-based testing's correctness checks ([§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)) or integration testing's real-behavior checks ([§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)).

## 5. Hands-On

### 5.1 A Sentinel Policy: Enforcing Mandatory Tags

**Purpose:** Block any plan that creates an AWS resource missing a required `cost_center` tag, using Terraform Cloud's native Sentinel integration.

**Syntax:**

```python
# require-cost-center-tag.sentinel
import "tfplan/v2" as tfplan

mandatory_tag = "cost_center"

taggable_resources = filter tfplan.resource_changes as _, rc {
    rc.type matches "^aws_" and
    rc.mode is "managed" and
    (rc.change.actions contains "create" or rc.change.actions contains "update")
}

violating_resources = filter taggable_resources as _, rc {
    rc.change.after.tags is null or
    rc.change.after.tags[mandatory_tag] is undefined
}

main = rule {
    length(violating_resources) is 0
}
```

**Example usage and expected output:**

```text
# In Terraform Cloud, attached as a policy set with enforcement_level = "soft-mandatory"

Policy check "require-cost-center-tag": Failed (soft-mandatory)

  aws_instance.app: missing required tag "cost_center"

An authorized user can override this policy check to proceed with apply.
```

**Production usage example:** A FinOps-driven Sentinel policy set is attached to every production workspace, initially deployed as `advisory` for two weeks to measure how many existing configurations would fail, then promoted to `soft-mandatory` once teams have had time to remediate, and finally to `hard-mandatory` for new workspaces created after a cutoff date.

**Common errors:** Writing `rc.change.after.tags[mandatory_tag] is undefined` without first null-checking `rc.change.after.tags` itself throws a runtime error (rather than evaluating to `false`) when a resource has no `tags` attribute at all — Sentinel policies need explicit null-safety exactly like defensive code in any other language.

### 5.2 An OPA/Rego Policy: Denying Public S3 Buckets, Run via Conftest

**Purpose:** Block any plan that creates an S3 bucket with public-read ACLs, runnable from any CI system via the Conftest CLI wrapper around OPA.

**Syntax:**

```rego
# policies/no_public_buckets.rego
package main

deny[msg] {
    resource := input.resource_changes[_]
    resource.type == "aws_s3_bucket_acl"
    acl := resource.change.after.acl
    acl == "public-read"
    msg := sprintf(
        "S3 bucket ACL %q on %q must not be public-read",
        [acl, resource.address],
    )
}
```

**Example usage and expected output:**

```bash
$ terraform show -json tfplan > plan.json
$ conftest test plan.json --policy policies/

FAIL - plan.json - main - S3 bucket ACL "public-read" on "aws_s3_bucket_acl.assets" must not be public-read

1 test, 0 passed, 1 failure, 0 warnings
$ echo $?
1
```

**Production usage example:** A GitHub Actions job runs `conftest test plan.json --policy policies/` as a required status check on every PR, using the same `deny[msg]`-style Rego rules to enforce a shared, versioned policy library across dozens of repositories via a Conftest-compatible policy bundle, rather than reimplementing checks per-repo.

**Common errors:** Forgetting that Conftest's exit code is the actual CI signal — a Rego syntax error produces output that looks superficially like a passing run in some terminal configurations, so pipelines should check the exit code explicitly rather than grepping for "FAIL" in output text.

### 5.3 Writing a Unit Test for a Rego Policy

**Purpose:** Verify a policy itself behaves correctly against known-good and known-bad fixture plans, before trusting it to gate real PRs.

**Syntax:**

```rego
# policies/no_public_buckets_test.rego
package main

test_denies_public_read_acl {
    deny[_] with input as {
        "resource_changes": [{
            "type": "aws_s3_bucket_acl",
            "address": "aws_s3_bucket_acl.test",
            "change": {"after": {"acl": "public-read"}},
        }]
    }
}

test_allows_private_acl {
    count(deny) == 0 with input as {
        "resource_changes": [{
            "type": "aws_s3_bucket_acl",
            "address": "aws_s3_bucket_acl.test",
            "change": {"after": {"acl": "private"}},
        }]
    }
}
```

**Example usage and expected output:**

```bash
$ conftest verify --policy policies/
PASS - data.main.test_denies_public_read_acl
PASS - data.main.test_allows_private_acl

2 tests, 2 passed, 0 failures
```

**Production usage example:** A shared platform-engineering repository holding the organization's full Rego policy library runs `conftest verify` in its own CI on every policy change, ensuring a policy edit can't silently stop enforcing what it used to (or start blocking things it shouldn't) before it's rolled out to every consuming repository.

**Common errors:** Testing only the "should deny" case and never the "should allow" case is a common gap — a policy with an overly broad match condition can pass its one deny test while also incorrectly denying legitimate configurations it was never meant to block.

## 6. Production Usage Notes

- **Policy evaluation happens after `plan`, before `apply`** in both models — neither Sentinel nor OPA/Conftest modifies the plan; they only decide whether the pipeline is allowed to proceed to apply based on the plan's contents.
- **Sentinel's override mechanism (`soft-mandatory`) requires a real audit trail.** Terraform Cloud/Enterprise records who overrode a policy check and when — this is the actual governance value: not "no exceptions ever," but "every exception is attributable to a specific accountable person," which most compliance frameworks specifically require.
- **OPA/Conftest policies are just files and can be shared as a versioned bundle** across many repositories (via a Conftest policy bundle registry, a Git submodule, or a package), the same way modules ([§59](../Part8/Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)) are shared — treating the policy library itself as a versioned artifact avoids drift between repos enforcing "the same" rule slightly differently.

## 7. Security Considerations

- Both engines evaluate the plan JSON, which — as noted in [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md) — can contain sensitive values unless marked `sensitive`; policy evaluation logs and CI output should be treated with the same sensitivity as raw plan output.
- A policy engine is only as strong as its coverage — a Rego/Sentinel policy library that hasn't kept pace with new resource types or new attack patterns provides false confidence; policy libraries need their own maintenance and review cadence, not a "write once" mentality.
- Hard-mandatory Sentinel policies and `deny`-blocking Rego rules are a genuine control against a compromised or careless CI credential attempting a destructive or non-compliant change — but only if the policy check itself cannot be bypassed by someone with direct `apply` access outside the pipeline, tying back to the least-privilege execution role concerns from [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                     | Likely Cause                                                                                                                                               | Resolution Path                                                                                           |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| Sentinel policy throws a runtime error instead of failing cleanly           | Missing null-check before indexing into a possibly-absent plan attribute (e.g., `tags` on a resource with none)                                            | Add explicit null/undefined checks before attribute access, as shown in §5.1                              |
| Conftest reports "0 tests" or silently passes when it shouldn't             | Rego `package` name in the policy file doesn't match what Conftest expects (`main` by default), or the policy file wasn't picked up by the `--policy` path | Confirm package naming and that the policy directory path is correct and included                         |
| A soft-mandatory Sentinel policy is overridden far more often than expected | The policy is miscalibrated — either too strict for legitimate cases, or teams weren't given advisory-mode lead time to remediate before promotion         | Review override audit logs for patterns; consider loosening the policy or extending advisory-mode rollout |
| New Rego policy accidentally blocks unrelated, compliant PRs                | Overly broad match condition in the `deny` rule (matching on resource `type` alone instead of the specific attribute in violation)                         | Add unit tests (§5.3) covering both should-deny and should-allow cases before merging any policy change   |

## 9. Best Practices

- Roll out any new policy as advisory first, measure real-world impact against existing configurations, and only promote to (soft- or hard-)mandatory once the blast radius is understood.
- Write unit tests for policies themselves (Conftest's `verify`, or Sentinel's own test framework) before trusting them to gate real PRs — a policy bug that over-blocks is its own kind of outage.
- Keep the policy library as a separately versioned, reviewed artifact shared across repositories rather than copy-pasted per-repo, so a rule change or fix propagates consistently.

## 10. Common Anti-Patterns / Mistakes

- **Writing policies against raw HCL source instead of the plan JSON.** Static-source scanning ([§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md) tools like tfsec/Checkov do exactly this) catches known-bad _patterns_, but only plan-based policy evaluation sees computed, real values — e.g., a `for_each`-generated resource's actual final attributes, which don't exist as literal text anywhere in the source.
- **Making every policy hard-mandatory from day one.** This produces an immediate wave of blocked, unrelated PRs and breeds resentment toward the policy system itself — advisory-first rollout exists specifically to avoid this.
- **Letting the policy library grow without its own tests or ownership.** A policy repository that nobody owns or tests degrades exactly like any other unmaintained codebase — false positives accumulate, and teams start reflexively overriding rather than reading violations.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between Sentinel and OPA for Terraform policy enforcement?"_
**Model answer:** Sentinel is HashiCorp's proprietary policy-as-code language, natively built into Terraform Cloud/Enterprise's run pipeline — policies are evaluated automatically as part of every run with no extra setup. OPA (Open Policy Agent) is a general-purpose, vendor-neutral policy engine using the Rego language; for Terraform it's typically run via Conftest against a `terraform show -json` plan file, and it works in any CI system regardless of whether Terraform Cloud is involved at all.
_What the interviewer is probing for:_ Basic awareness of the vendor-lock-in distinction between the two, not just that "both do policy checks."

**🎯 Intermediate:** _"Explain Sentinel's three enforcement levels and why an organization would use all three rather than just hard-blocking everything."_
**Model answer:** Advisory logs a violation without blocking anything — used to measure a new policy's real-world impact before enforcing it. Soft-mandatory blocks the run but allows an authorized user to explicitly override, creating an audited exception path for legitimate edge cases. Hard-mandatory blocks unconditionally with no override. Using all three lets an organization roll out governance incrementally — start advisory to avoid breaking unrelated work, promote to soft-mandatory once most configurations comply, and reserve hard-mandatory for the smallest set of non-negotiable rules (e.g., a rule preventing public database endpoints) where no legitimate exception should exist.
_What the interviewer is probing for:_ Understanding policy enforcement as a rollout and risk-tolerance problem, not a binary block/allow decision.

**🎯 Senior:** _"Your team has both tfsec/Checkov static scanning ([§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md)) and Conftest-based OPA policy checks running in CI. Isn't that redundant? How do you explain the difference to a skeptical engineer?"_
**Model answer:** They operate on fundamentally different inputs. Static scanners like tfsec/Checkov analyze the raw HCL source for known-bad _patterns_ — they can flag "this resource block sets `acl = \"public-read\"` literally in the file" without ever running Terraform at all, which makes them extremely fast and usable even on a single file with no provider credentials. OPA/Conftest policy checks evaluate the actual computed plan — the real, final attribute values after all variables, `for_each` expansion, and module composition are resolved — which is the only place you can catch a violation that only exists because of _how values compute_, not because of any literal string in the source (e.g., a `for_each`-generated bucket whose ACL is set indirectly through a variable that happens to resolve to `public-read` in one specific environment). The two are complementary layers, not redundant: static scanning is a fast, cheap first pass; plan-based policy is the more expensive but more accurate final gate.
_What the interviewer is probing for:_ Whether the candidate actually understands the source-vs-plan distinction, not just "more scanning is more secure."

**🎯 Architect:** _"Design a policy governance rollout for an organization migrating 200 Terraform Cloud workspaces from 'no policy enforcement at all' to a fully enforced Sentinel policy set, without causing a wave of blocked teams and lost trust in the system."_
**Model answer:** I'd start by writing the full intended policy set but attaching it to all 200 workspaces at `advisory` enforcement level first, running for a fixed measurement window (e.g., 2-4 weeks) to collect violation data without blocking anyone. I'd triage violations by policy and by team — some policies will have near-zero violations (safe to promote quickly) while others will reveal that a large fraction of existing workspaces genuinely can't comply yet (needs either a remediation project or the policy itself needs adjusting for a legitimate use case I hadn't considered). I'd promote policies to soft-mandatory in waves, prioritizing the highest-risk/lowest-friction ones first, giving each wave's affected teams a clear remediation deadline and a documented override path for genuine exceptions in the interim. Only a small, carefully chosen subset of truly non-negotiable rules (public database exposure, disabling encryption) would ever reach hard-mandatory, and only after the soft-mandatory override log shows near-zero legitimate use of the override for that specific rule. Throughout, I'd keep policy definitions themselves under version control with their own unit tests (§5.3) and require review on any policy change, so governance itself is auditable and doesn't silently drift.
_What the interviewer is probing for:_ Whether the candidate can design a staged, low-friction rollout for an org-wide control change, balancing governance rigor against not breaking 200 teams' workflows overnight — a realistic large-scale platform-engineering scenario.

## 12. Common Misconceptions

1. **"Policy-as-code and static security scanning (tfsec/Checkov) are the same thing."** Static scanners check raw source for known-bad patterns; policy engines like Sentinel/OPA evaluate the actual computed plan — different inputs, different blind spots, genuinely complementary.
2. **"Sentinel only works if you're on Terraform Cloud/Enterprise."** True for Sentinel specifically (it's tied to HashiCorp's run pipeline) — but that's exactly why OPA/Conftest exists as the equivalent for any other CI setup.
3. **"A hard-mandatory policy can never be a mistake."** A hard-mandatory policy with a bug or an overly broad condition blocks legitimate work with zero recourse — this is precisely why advisory-first rollout and policy unit testing both exist.
4. **"Policy checks replace the need for a human reviewer on infrastructure PRs."** They enforce specific, codified rules reliably, but a human reviewer still catches design-level and intent-level issues no policy engine is written to check.

## 13. 🔑 Key Takeaways

- Sentinel (Terraform Cloud/Enterprise-native) and OPA/Conftest (vendor-neutral, any CI) both evaluate the structured plan JSON to enforce organizational rules beyond what any individual PR author controls.
- Sentinel's advisory/soft-mandatory/hard-mandatory tiers exist to support incremental, low-friction policy rollout rather than immediate hard blocking.
- Policy engines evaluate computed plan values, catching violations that only exist because of how values resolve — something static source scanning ([§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md)) structurally cannot see.
- Policies themselves should be version-controlled, reviewed, and unit-tested before being trusted to gate real PRs.
- Policy-as-code is a distinct testing layer from plan-based correctness testing ([§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)) and integration testing ([§100](./Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)) — it enforces organizational rules, not authorial intent.

## 14. Related Concepts & What's Next

[§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md) produces the JSON plan data both engines here consume. [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) introduced Sentinel and OPA within the Terraform Cloud context specifically; this section generalized policy testing to any CI pipeline. [§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md) covers the complementary static-source scanning layer. [§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) shows how a policy-check step like Conftest fits into a complete CI pipeline alongside validate, plan, and test stages.

**Next Section:** [§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) — `Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md`
