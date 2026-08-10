# Section 52 (Part 7): terraform import: Bringing Existing Resources Under Management

## 1. Definition

**Plain language:** `terraform import` takes a real, already-existing piece of infrastructure — something created by hand in the console, by a different tool, or by a script — and adds an entry for it into Terraform's state, so that going forward Terraform manages it instead of treating it as something to create from scratch. It doesn't touch the real object at all; it only teaches Terraform's state about something that was already there.

**Precise definition:** **`terraform import <address> <id>`** associates an existing real-world infrastructure object, identified by a provider-specific ID, with a resource address in state. It requires that a matching resource block already exist in configuration before the command is run — import populates the _state_ side of the mapping ([§46](./Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)) but does not generate configuration for you (with the caveat that newer Terraform versions offer `import` blocks with `-generate-config-out` to scaffold a starting-point config, which still requires review). After import succeeds, the resource is present in state with its full set of provider-reported attributes, and the next `terraform plan` should be run immediately to confirm the written configuration actually matches what was imported — a mismatch surfaces as a proposed "change" on next plan, since import copies attributes into state exactly as the provider reports them, with no verification against your `.tf` file's arguments.

> 💡 **Tip:** Import is a two-sided operation and only automates one side. You must always write (or generate and then review) the resource block yourself — import only ever populates state, never configuration — and a common beginner mistake is running `import` against an address with no matching resource block at all, which fails immediately.

## 2. Why This Matters

- **Manually-created infrastructure is extremely common in real organizations**, especially in older accounts or ones with a history of console-driven operations — import is the standard, supported path to bring that infrastructure under Terraform management without destroying and recreating it (which for stateful resources can mean real data loss or downtime).
- **Import is the direct fix for the "Terraform wants to recreate something that already exists" failure mode** flagged all the way back in [§1](../Part1/Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md)'s troubleshooting table — instead of letting a mistaken `apply` destroy and recreate a resource that was already fine, import teaches state about it first.
- **Migrating resources between Terraform projects or from other IaC tools relies on import.** A resource being handed off from a CloudFormation stack, a Pulumi program, or another team's Terraform state (after a `state rm`, [§51](./Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) needs to be imported into its new home before it can be managed there.
- **Import is inherently error-prone if the config doesn't already match reality closely**, because Terraform doesn't verify your written arguments against the imported attributes at import time — only the following `plan` reveals any mismatch — making the immediate post-import `plan` step non-optional.
- **At scale, import of many resources (an entire pre-existing environment) is a genuinely significant undertaking**, often needing either careful manual sequencing or tooling (community tools that generate both config and import commands from a live environment) — understanding the single-resource mechanics here is the foundation for reasoning about that larger effort.

## 3. Prerequisites and Dependencies

Builds on [§46](./Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md) (why state exists as the config-to-reality mapping) and [§51](./Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md) (`state rm`, the operation import is often paired with when migrating a resource's ownership). Assumes resource block syntax and addressing from [§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md).

## 4. Architecture / Conceptual Diagram

```text
                        THE IMPORT WORKFLOW

  STEP 1: Resource exists in reality, NOT in Terraform's state or config

  Real Infrastructure                Configuration (.tf)      State
  ────────────────────                ──────────────────       ─────
  S3 bucket "legacy-assets"           (nothing written yet)     (no entry)
  created via console

  STEP 2: Write a matching resource block FIRST (required before import)

  resource "aws_s3_bucket" "legacy" {
    bucket = "legacy-assets"
  }
                    │
                    ▼
  STEP 3: terraform import aws_s3_bucket.legacy legacy-assets

  Real Infrastructure                Configuration (.tf)      State
  ────────────────────                ──────────────────       ─────
  S3 bucket "legacy-assets"    ◄────  resource block exists ──► NEW entry:
  (untouched — import makes            aws_s3_bucket.legacy      full attributes
   ZERO API calls that modify it)                                 as reported by
                                                                     the provider

                    │
                    ▼
  STEP 4: terraform plan  ── MANDATORY next step

  ┌──────────────────────────────────────────────────────────────┐
  │  Compares:  config arguments  vs.  imported state attributes │
  │                                                              │
  │  "No changes" → config already matches reality — done.       │
  │  Any diff     → config is INCOMPLETE/WRONG relative to       │
  │                 reality; refine the resource block until     │
  │                 plan shows no changes, WITHOUT applying      │
  │                 destructive changes to the real resource.    │
  └──────────────────────────────────────────────────────────────┘
```

- Step 2 is not optional — running `import` against a resource address with no matching block in configuration fails outright; import only ever writes to state, never to `.tf` files (outside the newer, still-review-required `-generate-config-out` flow).
- Step 4 exists because import copies the provider's reported attributes into state verbatim, with no cross-check against what you wrote — any gap between your resource block's arguments and reality only becomes visible on the next `plan`, which is why running it immediately after import, before any other change, is essential.
- Zero API calls are made against the real object at any point in this flow — import is purely a state-and-configuration-side operation, which is exactly why it's safe to use on production resources.

## 5. Hands-On

### 5.1 Basic Import Workflow

**Purpose:** Bring a manually-created S3 bucket under Terraform management.

**Syntax:**

```bash
terraform import <resource_address> <provider_specific_id>
```

**Example usage and expected output:**

```hcl
# main.tf — written FIRST, before running import
resource "aws_s3_bucket" "legacy" {
  bucket = "legacy-assets"
}
```

```bash
$ terraform import aws_s3_bucket.legacy legacy-assets
aws_s3_bucket.legacy: Importing from ID "legacy-assets"...
aws_s3_bucket.legacy: Import prepared!
  Prepared aws_s3_bucket for import
aws_s3_bucket.legacy: Refreshing state... [id=legacy-assets]

Import successful!

The resources that were imported are shown above. These resources are now in
your Terraform state and will henceforth be managed by Terraform.

$ terraform plan
aws_s3_bucket.legacy: Refreshing state... [id=legacy-assets]
No changes. Your infrastructure matches the configuration.
```

**Production usage example:** This exact sequence — write the block, import, then plan until clean — is the standard runbook step any time a team discovers a manually-created resource that needs to come under Terraform management, whether found via an audit, drift detection tooling ([§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)), or simply "someone remembers this exists but it's not in any `.tf` file."

**Common errors:** Running `import` without a matching resource block first fails with `resource address "aws_s3_bucket.legacy" does not exist in the configuration` — the block must exist, even with minimal/incomplete arguments, before import will proceed.

### 5.2 Resolving a Post-Import Plan Diff

**Purpose:** Show the expected follow-up work when the written configuration doesn't fully match the imported resource's real attributes.

**Syntax:**

```bash
terraform plan
# then edit the resource block to match, repeat until clean
```

**Example usage and expected output:**

```bash
$ terraform plan
  # aws_s3_bucket.legacy will be updated in-place
  ~ resource "aws_s3_bucket" "legacy" {
        id     = "legacy-assets"
      ~ tags   = {
          + "Environment" = "production"
        }
    }
Plan: 0 to add, 1 to change, 0 to destroy.
```

```hcl
# Fix: add the missing argument the real bucket already has
resource "aws_s3_bucket" "legacy" {
  bucket = "legacy-assets"
  tags = {
    Environment = "production"
  }
}
```

```bash
$ terraform plan
No changes. Your infrastructure matches the configuration.
```

**Production usage example:** This iterative "plan, diff, edit config, re-plan" loop after import is the normal and expected workflow for any resource with more than a handful of attributes — treating the first post-import `plan` diff as an error rather than a normal step is a common source of confusion for teams new to import.

**Common errors:** Applying a post-import plan diff without understanding why it's there risks accidentally _changing_ the real resource to match an incorrect assumption in configuration, rather than fixing the configuration to match reality — always read the diff carefully to determine which side (config or reality) needs to change before applying anything.

## 6. Production Usage Notes

- **Import is single-resource by default; large-scale imports need tooling or careful scripting.** Bringing an entire pre-existing environment under management typically means either writing/generating one resource block and one `import` command per resource, or using community tooling designed to scan a live account and emit both — either way, treat it as a project, not a one-liner, for anything beyond a handful of resources.
- **`-generate-config-out` (newer Terraform versions) reduces but doesn't eliminate the manual-config-writing step.** It generates a starting-point resource block from the real object's attributes, which still needs human review — provider-generated config commonly needs cleanup (hardcoded values that should become variables, attributes that shouldn't be tracked) before it's genuinely production-quality.
- **Post-import review should include checking `lifecycle` and `ignore_changes` needs**, since imported resources sometimes have attributes managed by another process that shouldn't be fought over by Terraform going forward — this is a good moment to add `ignore_changes` ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) deliberately rather than reactively after a surprising future plan.

## 7. Security Considerations

- **Import surfaces the full attribute set immediately, including secrets.** If the imported resource has attributes like a generated password or key, they land in state in plaintext the moment import completes, exactly as with any resource ([§46](./Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md), [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) — this is not a new risk import introduces, but it does mean the moment of import is when that risk starts to apply to a previously-unmanaged resource.
- **Getting import wrong (importing the wrong ID, or a resource with different intended ownership) can incorrectly place a sensitive resource under a project/team's management that shouldn't have visibility into it**, since state read access typically follows project/backend boundaries — verify the ID and target project carefully before importing anything sensitive.
- **The identity used for `terraform import` needs read (and refresh) access to the resource**, which for cross-account or cross-project imports may require a temporary credential/role grant that should be scoped narrowly and removed after the import is complete.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Likely Cause                                                                                                  | Resolution Path                                                                                                                   |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `import` fails with "resource address does not exist in the configuration" | No matching resource block was written before running `import`                                                | Write the resource block (even minimally) first, then re-run `import`                                                             |
| `plan` shows changes immediately after a successful import                 | Written configuration's arguments don't fully match the real resource's attributes                            | Iteratively update the resource block to match reality until `plan` shows no changes; do not apply blindly                        |
| Import succeeds but the resource's ID format is rejected/wrong             | Provider-specific ID format not used correctly (e.g., composite IDs with a separator for some resource types) | Check the specific provider/resource's documentation for its expected import ID format                                            |
| Team discovers dozens of manually-created resources needing import         | History of console-driven operations before Terraform adoption, no earlier audit                              | Treat as a structured project: inventory first, then script or tool-assist config generation + import, verifying each with `plan` |

## 9. Best Practices

- Always write the resource block before running `import`, and always run `plan` immediately after — never treat "import succeeded" alone as "done."
- Resolve any post-import plan diff by editing configuration to match reality, not by blindly applying — understand which side is actually wrong before changing anything.
- For anything beyond a handful of resources, plan the import effort as a deliberate, sequenced project (inventory, prioritize, generate/write config, import, verify) rather than ad hoc one-off imports discovered reactively.

## 10. Common Anti-Patterns / Mistakes

- **Running `import` without first writing a resource block, expecting Terraform to generate one automatically.** Import only writes to state; configuration must already exist (or be generated via `-generate-config-out` and reviewed) separately.
- **Treating a post-import `plan` diff as confirmation something is broken, and applying it without investigation.** The diff is expected and normal; understanding and resolving it in the correct direction (usually fixing config to match reality) is the actual next step, not blind `apply`.
- **Importing resources into a shared production state without any review process**, the same way you would never `apply` to production without review — import changes what the next `apply` will do just as much as any other state-write operation ([§51](./Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)).

## 11. Interview Questions

**🎯 Beginner:** _"What does `terraform import` require you to do before you run it?"_
**Model answer:** You must first write a resource block in configuration that matches the resource you intend to import — `terraform import` only populates Terraform's state with the mapping between that resource address and the real object's provider-specific ID; it does not create or generate the configuration for you (aside from the newer, still-review-required config-generation flag).
_What the interviewer is probing for:_ Basic understanding that import is state-only and requires a pre-existing config block, a common early stumbling block.

**🎯 Intermediate:** _"After a successful `terraform import`, `terraform plan` shows several proposed changes. Is this a sign something went wrong with the import?"_
**Model answer:** No, this is expected and normal, not an error. Import copies the provider's reported attributes directly into state without checking them against what you wrote in the resource block — any gap between your configuration's arguments and the real resource's actual settings only becomes visible on the following `plan`. The correct response is to review the diff, determine whether configuration needs to be updated to match reality (the far more common case) or whether the diff reveals something about the real resource that genuinely needs to change, and iterate until `plan` shows no changes before considering the import complete.
_What the interviewer is probing for:_ Whether the candidate understands the two-sided nature of import (state versus config) and treats the post-import plan step as mandatory, not optional.

**🎯 Senior:** _"You need to import roughly 200 manually-created resources across a legacy AWS account into a new Terraform project. What's your approach, and what are the biggest risks at that scale?"_
**Model answer:** At that scale, resource-by-resource manual `import` commands with hand-written config are impractical — the approach should use tooling that can enumerate the account's existing resources and generate both a starting-point resource block and the corresponding import command per resource (community tools exist for this, and newer Terraform's `-generate-config-out` can assist per-resource once you already know what to import), then treat the output as a first draft requiring systematic review rather than a finished result. Sequencing matters: import resources with few or no dependencies first, verify each with `plan` before moving to dependent resources, and group the effort into batches (by service, by environment) rather than attempting all 200 in one pass, so a mistake in batch three doesn't put the previous two batches' verified state at risk. The biggest risks at this scale: generated configuration is rarely production-quality as-is (hardcoded values needing to become variables, attributes that shouldn't be tracked at all, missing `lifecycle`/`ignore_changes` for attributes managed elsewhere) and reviewing 200 resources' worth of generated config for correctness is itself a substantial effort that shouldn't be underestimated or rushed; and any resource genuinely still relied upon by manual processes or other tooling that gets imported without that being understood risks Terraform "fighting" that other process on every subsequent `apply` once it starts trying to reconcile config against attributes something else keeps changing.
_What the interviewer is probing for:_ Realistic understanding that large-scale import is a structured project with sequencing, tooling, and review overhead — not simply "run import 200 times" — and awareness of the specific new risks (bad generated config, conflicting external management) that appear only at scale.

**🎯 Architect:** _"A newly-acquired subsidiary has years of manually-managed AWS infrastructure with no IaC at all. Leadership wants it fully under Terraform management within a quarter. Design the approach, and identify what could make this timeline unrealistic."_
**Model answer:** Approach: start with a full inventory/discovery pass (using account-wide resource enumeration, potentially combined with cost/usage data to identify what's actually load-bearing versus abandoned) before writing a single line of Terraform, since importing genuinely dead resources wastes effort and importing resources still under active manual change without recognizing that sets up a fight on every future apply. Prioritize by risk and value: foundational networking (VPCs, subnets) and stateful, hard-to-recreate resources (databases, resources holding data) go first and get the most careful manual review of generated configuration, since a mistake there is costly; large numbers of near-identical, low-risk resources (individual security group rules, tags) are strong candidates for tooling-assisted bulk import with lighter review. Structure the effort in state-file-sized increments per logical environment/component (Part 15's state-splitting concerns apply directly here) rather than one giant import into one giant state, both to limit blast radius of any single mistake and to let teams work on different components in parallel. What makes the quarter timeline unrealistic: the review burden of generated configuration is almost always underestimated — turning raw imported attributes into genuinely maintainable, variable-driven, reviewed Terraform code for years of undocumented manual infrastructure is a substantially larger effort than the import command itself, which is nearly instantaneous per resource; undiscovered dependencies and undocumented "tribal knowledge" resources surface throughout the process, not all up front, which means the inventory phase alone can run long; and any resource still actively managed by a process the acquiring team doesn't yet understand (another team's script, a legacy deployment tool) risks real incidents if imported and then fought over by Terraform before that's identified — discovering and de-conflicting those cases takes calendar time that doesn't compress well under schedule pressure. The honest answer to leadership is usually: full inventory and a risk-tiered rollout plan within the quarter is realistic; full completion of import for a genuinely multi-year, undocumented estate within one quarter typically is not, and committing to it invites corner-cutting on review that creates exactly the kind of incidents this effort is meant to prevent.
_What the interviewer is probing for:_ Whether the candidate can push back credibly on an unrealistic timeline with concrete reasoning (review burden, undiscovered dependencies, conflicting external management) rather than either agreeing uncritically or refusing to engage with the scoping question at all.

## 12. Common Misconceptions

1. **"`terraform import` writes the resource block for me."** It writes only to state; the resource block must already exist (or be generated separately via `-generate-config-out` and then reviewed) before import will succeed.
2. **"A clean `import successful!` message means the job is done."** It only means the state entry was created — a clean `terraform plan` afterward, confirming configuration matches reality, is the actual completion signal.
3. **"Import makes API calls that modify the real resource."** It makes only read calls to fetch the resource's current attributes for state — nothing about the real object changes as a result of import itself.
4. **"Import is only for one-off, rare situations."** It's a routine, expected part of Terraform adoption in any organization with pre-existing infrastructure, and at scale is a structured effort with its own tooling and process, not a rare edge case.

## 13. 🔑 Key Takeaways

- `terraform import <address> <id>` associates a real, already-existing object with a resource address in state — it requires a matching resource block to already exist in configuration.
- Import only ever writes to state, never to `.tf` files (aside from the newer, still-review-required config-generation flag) — it makes no modifying API calls against the real resource.
- A `terraform plan` immediately after import is mandatory, not optional, since import doesn't verify written configuration against the imported attributes — any mismatch only surfaces there.
- At scale, importing many resources is a structured project requiring sequencing, tooling assistance, and substantial configuration review, not a simple repeated one-liner.
- Import is the standard, safe path for bringing manually-created or externally-managed infrastructure under Terraform without destroying and recreating it.

## 14. Related Concepts & What's Next

[§53](./Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md) covers moving entire state files between backends, a distinct but related operation from moving individual resources into state via import. [§54](./Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) covers the ongoing problem of drift — what happens after a resource is already Terraform-managed and something changes it outside Terraform again.

**Next Section:** [§53](./Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md) — `Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md`
