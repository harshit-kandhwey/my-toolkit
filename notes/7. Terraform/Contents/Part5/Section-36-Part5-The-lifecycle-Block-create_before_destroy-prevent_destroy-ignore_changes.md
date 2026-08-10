# Section 36 (Part 5): The lifecycle Block: create_before_destroy, prevent_destroy, ignore_changes

## 1. Definition

**Plain language:** By default, when Terraform needs to replace a resource (some change requires destroying the old one and creating a new one), it destroys first, then creates — meaning there's a window where the resource doesn't exist at all. The `lifecycle` block lets you override that and other default behaviors: flip the order so the new one is created before the old one is destroyed (avoiding downtime), refuse to ever destroy a resource no matter what the plan says (protecting something critical from accidental deletion), or tell Terraform to stop caring about changes to specific attributes (useful when something outside Terraform, like an autoscaler, legitimately changes a value Terraform would otherwise try to "fix" back).

**Precise definition:** The **`lifecycle` block** is a nested block (not itself a meta-argument, but a container for lifecycle-related meta-arguments) that can appear inside any `resource` block, controlling how Terraform manages that resource's create/update/destroy behavior independent of the provider's own semantics. Its three primary arguments are: **`create_before_destroy`** (boolean) — when a change requires replacement, create the new instance first and only destroy the old instance after the new one succeeds, instead of the default destroy-then-create order; **`prevent_destroy`** (boolean) — causes `terraform apply`/`terraform destroy` to error out before performing any destroy operation on this resource, regardless of what triggered it; and **`ignore_changes`** (a list of attribute names, or the literal keyword `all`) — tells Terraform to exclude the listed attributes from its diff calculation entirely, so drift on those specific attributes never appears in `plan` output and never triggers an update.

> 💡 **Tip:** `prevent_destroy` does not protect against everything — it blocks Terraform-initiated destroys triggered by `terraform destroy` or a plan that would replace/remove the resource, but it does **not** protect against someone deleting the resource manually outside Terraform, nor does it survive the resource being removed from configuration entirely combined with `terraform state rm` first. Treat it as a safety rail against accidental Terraform-driven deletion, not a comprehensive deletion-proof guarantee.

## 2. Why This Matters

- **`create_before_destroy` is frequently the difference between a zero-downtime replacement and an outage** — the default destroy-then-create order means any resource replacement (a changed AMI, a renamed launch configuration, an immutable attribute change) briefly removes the resource from existence before recreating it.
- **`prevent_destroy` is a critical guardrail against the single most catastrophic class of Terraform mistake**: an unintended plan that destroys a production database, a stateful volume, or any resource whose loss is not easily reversible.
- **`ignore_changes` is essential for interoperating with anything outside Terraform's control that legitimately mutates a resource** — autoscaling groups whose `desired_capacity` is managed by a scaling policy, resources tagged by a separate compliance automation tool, or attributes populated by a provisioner after creation.
- **Misusing any of the three has real production consequences**: `create_before_destroy` can fail outright on resources with unique-name constraints if not paired with correctly parameterized naming; `prevent_destroy` can block a legitimate, intentional decommission and require manual intervention to override; `ignore_changes` can mask genuine, unwanted drift if scoped too broadly (or the value `all`).
- **This is one of the most heavily tested areas of the Terraform Associate exam** ([§112](../Part16/Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md)–[§116](../Part16/Section-116-Part16-Scenario-Based-Infrastructure-Design-Questions.md)) precisely because getting these three arguments' exact names, scopes, and edge-case behaviors right is a common practical stumbling block.

## 3. Prerequisites and Dependencies

This section depends on [§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md) (resource addressing and the general shape of a resource block), [§34](./Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) (`count`/`for_each`, since `create_before_destroy` frequently pairs with `for_each`-driven resources during safe migrations), and [§35](./Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md) (dependency ordering, since `create_before_destroy` interacts with the dependency graph during replacement). [§23](../Part3/Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md) previewed the `lifecycle` block alongside other meta-arguments; this section is its dedicated deep dive. [§12](../Part2/Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md) (execution model: refresh/plan/apply internals) is useful background for understanding exactly when in the apply sequence these arguments take effect.

## 4. Architecture / Conceptual Diagram

```text
  DEFAULT REPLACEMENT ORDER (destroy-before-create)

  time ──────────────────────────────────────────►

  [ resource exists ]───X destroy───┆ gap: resource        ┆───create───[ resource exists ]
                                     ┆ does NOT exist here  ┆
                                     └──────────────────────┘
                                        DOWNTIME WINDOW


  create_before_destroy = true

  time ──────────────────────────────────────────►

  [ old resource exists ]──create new──[ both exist briefly ]──X destroy old──[ new resource exists ]
                                          │
                                          └─ traffic can shift to new before old is removed
                                             NO GAP where zero instances exist


  prevent_destroy = true

  terraform apply / destroy attempts to remove this resource
        │
        ▼
  ┌─────────────────────────────────────────────────────────────┐
  │ Error: Instance cannot be destroyed                         │
  │ Resource <address> has lifecycle.prevent_destroy set,       │
  │ but the plan calls for this resource to be destroyed.       │
  │ To avoid this error, either remove the resource from the    │
  │ configuration, or explicitly disable prevent_destroy first. │
  └─────────────────────────────────────────────────────────────┘
        Apply HALTS before any destroy occurs — safety-first behavior.


  ignore_changes = [tags, desired_capacity]

  Real infrastructure's "tags" and "desired_capacity" attributes
  drift away from what's declared in configuration (e.g. an
  autoscaler changes desired_capacity, a tagging tool adds tags)
        │
        ▼
  terraform plan
        │
        ▼
  Diff calculation SKIPS these two attributes entirely —
  no "will be updated in-place" shown for them, ever,
  regardless of how far they've drifted.
```

- `create_before_destroy` changes **ordering**, not the fact that a replacement happens — it still destroys the old resource eventually, just after the new one is confirmed created.
- `prevent_destroy` is evaluated **before** any destroy API call is made, causing `apply` to fail fast with a clear error rather than partially destroying anything.
- `ignore_changes` operates purely at the **diff/plan** level — the attribute's real-world value is never reverted, updated, or even reported as different, regardless of how much it has drifted from the configured value.

## 5. Hands-On

### 5.1 `create_before_destroy` — Zero-Downtime Replacement

**Purpose:** Avoid a destroy-then-create gap when a resource must be replaced due to an immutable attribute change.

**Syntax:**

```hcl
resource "<TYPE>" "<NAME>" {
  lifecycle {
    create_before_destroy = true
  }
}
```

**Example usage and expected output:**

```hcl
resource "aws_launch_template" "app" {
  name_prefix   = "app-lt-"   # name_prefix, not name — required for create_before_destroy
  image_id      = var.ami_id
  instance_type = "t3.micro"

  lifecycle {
    create_before_destroy = true
  }
}
```

```bash
$ terraform plan
  # aws_launch_template.app must be replaced
-/+ resource "aws_launch_template" "app" {
      ~ image_id = "ami-old12345" -> "ami-new67890" # forces replacement
    }

Plan: 1 to add, 0 to change, 1 to destroy.

$ terraform apply
aws_launch_template.app: Creating...
aws_launch_template.app: Creation complete after 1s [id=lt-0new1234]
aws_launch_template.app (deposed object abc123): Destroying...
aws_launch_template.app (deposed object abc123): Destruction complete after 1s

Apply complete! Resources: 1 added, 0 changed, 1 destroyed.
```

**Production usage example:** This is the standard pattern for launch templates/configurations feeding autoscaling groups, and for any resource with a uniquely-named-conflict constraint where the old and new versions must briefly coexist — `name_prefix` (which appends a random suffix) instead of a fixed `name` is required here, since a fixed name would collide between the still-existing old resource and the about-to-be-created new one.

**Common errors:** `Error: ... already exists` during a `create_before_destroy` replacement almost always means a fixed `name` argument (not `name_prefix`) is being used, causing the new resource's creation to collide with the still-existing old one — switch to a naming scheme that tolerates temporary coexistence, or accept the default destroy-before-create ordering if brief downtime is acceptable.

### 5.2 `prevent_destroy` — Blocking Accidental Deletion

**Purpose:** Guard a critical, hard-to-recover resource against any Terraform-initiated destroy.

**Syntax:**

```hcl
resource "<TYPE>" "<NAME>" {
  lifecycle {
    prevent_destroy = true
  }
}
```

**Example usage and expected output:**

```hcl
resource "aws_db_instance" "primary" {
  identifier     = "prod-primary-db"
  engine         = "postgres"
  instance_class = "db.r6g.xlarge"

  lifecycle {
    prevent_destroy = true
  }
}
```

```bash
$ terraform destroy
Terraform will perform the following actions:
  # aws_db_instance.primary will be destroyed

Error: Instance cannot be destroyed

  on main.tf line 12, in resource "aws_db_instance" "primary":
  12: resource "aws_db_instance" "primary" {

Resource aws_db_instance.primary has lifecycle.prevent_destroy set, but the
plan calls for this resource to be destroyed. To avoid this error and
continue with the plan, either disable lifecycle.prevent_destroy or reduce
the scope of the plan using the -target option.
```

**Production usage example:** Standard on production databases, KMS keys with long-lived encrypted data, and any stateful storage where destruction is effectively irreversible — the error is deliberately unrecoverable within the same apply, forcing a conscious, separate configuration change (removing or flipping the flag) before an intentional deletion can proceed.

**Common errors:** Believing `prevent_destroy` prevents _all_ forms of deletion — it does not stop a manual deletion via the cloud console/API, nor does it stop `terraform state rm` followed by manual deletion, since `state rm` only removes Terraform's record without touching the real object or triggering the lifecycle check at all.

### 5.3 `ignore_changes` — Tolerating Externally-Managed Attributes

**Purpose:** Prevent Terraform from fighting with an external process (an autoscaler, a separate tagging automation) over an attribute both parties touch.

**Syntax:**

```hcl
resource "<TYPE>" "<NAME>" {
  lifecycle {
    ignore_changes = [<attribute>, <attribute>, ...]
  }
}
```

**Example usage and expected output:**

```hcl
resource "aws_autoscaling_group" "app" {
  desired_capacity = 3   # only used at initial creation
  min_size          = 2
  max_size          = 10

  lifecycle {
    ignore_changes = [desired_capacity]
  }
}
```

```bash
$ # A scaling policy external to this configuration changes desired_capacity to 7
$ terraform plan
No changes. Your infrastructure matches the configuration.
# desired_capacity's real value (7) differs from configured value (3),
# but the diff is suppressed entirely because it's in ignore_changes.
```

**Production usage example:** This is the standard pattern for any autoscaling-managed attribute, and equally common for tags applied by a separate compliance/cost-tagging Lambda or policy engine that runs independently of the Terraform-managed lifecycle — without `ignore_changes`, every `plan` would show a perpetual, noisy diff trying to revert the externally-set value back to what's hardcoded in configuration.

**Common errors:** Using `ignore_changes = all` broadly "to make the noisy plans stop" instead of scoping to the specific attributes that are genuinely externally managed — this silences drift detection for the _entire_ resource, including attributes that should legitimately be caught and flagged, defeating one of Terraform's core value propositions ([§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md), drift detection).

### 5.4 Combining `create_before_destroy` with `ignore_changes`

**Purpose:** Show a realistic production pattern combining multiple `lifecycle` arguments on the same resource.

**Syntax:**

```hcl
resource "<TYPE>" "<NAME>" {
  lifecycle {
    create_before_destroy = true
    ignore_changes        = [<attribute>]
  }
}
```

**Example usage and expected output:**

```hcl
resource "aws_instance" "bastion" {
  ami           = var.bastion_ami
  instance_type = "t3.micro"

  lifecycle {
    create_before_destroy = true
    ignore_changes        = [ami]   # AMI updates handled via a separate, deliberate rotation process
  }
}
```

```bash
$ terraform plan
No changes. Your infrastructure matches the configuration.
# Even if var.bastion_ami changes, ignore_changes suppresses the diff for
# this specific attribute; create_before_destroy would only matter if some
# OTHER attribute forced replacement.
```

**Production usage example:** Deliberately decoupling a resource's replacement trigger from a specific attribute (rotating AMIs on a separate, controlled schedule rather than automatically on every Terraform apply) while still keeping zero-downtime replacement behavior available for any other attribute change that does force replacement.

**Common errors:** Assuming `ignore_changes` on an attribute also disables `create_before_destroy`'s relevance to that attribute — the two arguments operate independently; `ignore_changes` prevents the attribute from ever being seen as changed at all, so it can never trigger a replacement in the first place, regardless of the ordering strategy configured.

## 6. Production Usage Notes

- **`create_before_destroy` has a real cost: temporary duplicate resource existence**, which means quota limits, unique-name constraints, and cost (briefly running two of something) must all be accounted for — it isn't free zero-downtime, it's traded for those constraints.
- **`prevent_destroy` should be paired with a documented, explicit override procedure** (removing the flag in a reviewed PR, applying, then re-adding it if the resource persists) so that legitimate decommissions aren't blocked indefinitely by a forgotten safety flag.
- **`ignore_changes` should be re-audited periodically**, especially `ignore_changes = all` usage — attributes that were externally managed at one point in a project's life sometimes become Terraform-managed again after a refactor, and a stale `ignore_changes` entry silently prevents Terraform from ever correcting drift on that attribute again.

## 7. Security Considerations

- `prevent_destroy` is a meaningful, though partial, control against accidental or malicious destruction via Terraform — but since it lives in configuration (which is itself subject to change and review), a compromised or careless PR that simply removes the `lifecycle` block bypasses it entirely; genuine defense-in-depth also requires cloud-provider-level deletion protection (e.g., RDS deletion protection, S3 bucket policies) independent of Terraform.
- `ignore_changes` used broadly can mask genuinely security-relevant drift — for instance, ignoring changes to a security group's `ingress` rules means Terraform will never flag or alert on an unauthorized manual rule addition, silently defeating drift-based compliance enforcement ([§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)) for that resource.
- Because `create_before_destroy` briefly runs two instances of a resource concurrently, any resource-specific security configuration (network exposure, IAM role scope) must be correct on the **new** instance from the moment it's created, not gradually converged — there is no "grace period" during which reduced security posture is acceptable.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                         | Likely Cause                                                                                            | Resolution Path                                                                                                  |
| ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `Error: ... already exists` during a replacement                                                | `create_before_destroy = true` combined with a fixed (non-unique) `name` argument colliding on creation | Switch to `name_prefix` or another naming scheme tolerant of temporary duplicate existence                       |
| `terraform destroy`/`apply` errors with "Instance cannot be destroyed"                          | `prevent_destroy = true` is set and the plan calls for destroying that resource                         | Confirm intent; if destruction is deliberate, remove or set `prevent_destroy = false` in a reviewed change first |
| `plan` never shows drift on an attribute that has clearly changed in the real world             | `ignore_changes` includes that attribute (or is set to `all`)                                           | Remove the attribute (or narrow `all` to a specific list) from `ignore_changes` if drift detection should resume |
| `plan` is noisy every run, constantly trying to "fix" an attribute an external process controls | No `ignore_changes` set for an attribute genuinely managed outside Terraform                            | Add the specific attribute to `ignore_changes` rather than fighting the external process                         |

## 9. Best Practices

- Use `create_before_destroy` deliberately on resources where replacement is expected to happen regularly (launch templates/configurations, immutable-infrastructure patterns) and pair it with `name_prefix`-style naming from the start.
- Reserve `prevent_destroy` for resources whose loss would be genuinely catastrophic or hard to recover from (production databases, encryption keys, irreplaceable state backends) — applying it everywhere dilutes its signal and makes legitimate cleanup unnecessarily painful.
- Scope `ignore_changes` to the narrowest list of attributes actually managed externally; avoid `all` except as a deliberate, documented, and rare exception.
- Document _why_ each `lifecycle` argument is set, directly as a comment above the block — like `depends_on`, the reasoning isn't otherwise visible in the code and is easy to forget or misjudge during future refactors.

## 10. Common Anti-Patterns / Mistakes

- **Setting `ignore_changes = all` as a blanket fix for noisy plans** instead of diagnosing which specific attributes are genuinely externally managed — this silently disables drift detection for the entire resource, undermining one of Terraform's core guarantees.
- **Assuming `prevent_destroy` is a complete safety net** and skipping additional cloud-provider-native deletion protections, when `prevent_destroy` only blocks Terraform-initiated destroys, not manual console/API deletions or a careless removal of the lifecycle block itself.
- **Using `create_before_destroy` on resources with fixed, non-unique names**, causing every replacement to fail on a naming collision — a very common, easily-avoidable mistake for teams adopting the pattern for the first time.

## 11. Interview Questions

**🎯 Beginner:** _"What does `create_before_destroy = true` change about how Terraform replaces a resource?"_
**Model answer:** By default, when Terraform must replace a resource (because a change requires destroying and recreating it), it destroys the old instance first and then creates the new one — meaning there's a gap where the resource doesn't exist at all. Setting `create_before_destroy = true` inside the resource's `lifecycle` block reverses that order: Terraform creates the new instance first, and only destroys the old instance after the new one is successfully created, avoiding that gap.
_What the interviewer is probing for:_ Basic understanding of the ordering change and, ideally, why it matters (avoiding downtime).

**🎯 Intermediate:** _"You set `create_before_destroy = true` on a resource with a fixed `name` argument, and applying a change that forces replacement fails with an 'already exists' error. Why, and how do you fix it?"_
**Model answer:** With `create_before_destroy`, Terraform tries to create the new instance while the old one still exists — if both use the same fixed name, the provider's API rejects the new creation because a resource with that name is already there. The fix is to use a naming scheme that tolerates temporary coexistence, most commonly `name_prefix` instead of `name`, which lets the provider append a unique random suffix so the old and new instances have different actual names during the brief overlap window.
_What the interviewer is probing for:_ Hands-on familiarity with the most common practical gotcha of this specific lifecycle argument, not just its abstract definition.

**🎯 Senior:** _"Explain exactly what `prevent_destroy` does and does not protect against, and what additional controls you'd recommend for a genuinely critical resource like a production database."_
**Model answer:** `prevent_destroy = true` causes `terraform apply` or `terraform destroy` to fail with an error before performing any destroy operation on that resource, if the plan calls for destroying it — this blocks Terraform-initiated deletions, whether from an intentional `destroy` or an unintended replacement caused by a forces-replacement attribute change. It does **not** protect against: someone manually deleting the resource through the cloud console or API directly; someone running `terraform state rm` on the resource (which removes Terraform's record without any destroy check, since the lifecycle rule is only evaluated during a destroy plan) followed by a manual delete; or someone simply editing the configuration to remove the `lifecycle` block itself in a future change. For a production database, I'd combine `prevent_destroy` with cloud-provider-native deletion protection (e.g., RDS's own deletion protection flag, S3 MFA-delete or object lock where applicable), restrict who has IAM permission to disable those protections independently of Terraform, and require a documented, reviewed change (not just a routine PR) to ever remove `prevent_destroy` from configuration.
_What the interviewer is probing for:_ Whether the candidate understands `prevent_destroy`'s actual scope precisely enough to know it's a partial control, and can reason about defense-in-depth rather than treating one Terraform flag as sufficient.

**🎯 Architect:** _"Your organization has widespread `ignore_changes = all` usage across dozens of modules, originally added years ago to silence noisy plans. What's the risk, and how would you drive a safe remediation across a large codebase you don't fully control?"_
**Model answer:** The risk is that drift detection ([§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)) is effectively disabled on every resource with `ignore_changes = all` — any unauthorized or unintended manual change to those resources, security-relevant or not, will never surface in a `plan`, which undermines both compliance auditing and the basic premise that Terraform configuration reflects real infrastructure state. The remediation needs to be incremental and low-risk, not a single sweeping change, because blindly removing `ignore_changes = all` everywhere will surface a large backlog of real drift simultaneously, likely including changes that would now force unwanted replacements or updates. I'd start with an inventory pass — for each occurrence, determine what's actually externally managed on that resource (interview the module owner, check the resource's change history if available) — then replace the blanket `all` with a precise, narrow attribute list reflecting only what's genuinely externally managed, one module at a time, reviewing the resulting `plan` output carefully before applying (since some resources may show substantial newly-surfaced drift that needs its own remediation plan before the `ignore_changes` narrowing can safely land). This should be tracked as its own workstream with module owners accountable for their own resources, not centralized into one giant, risky change.
_What the interviewer is probing for:_ Large-scale, risk-aware remediation planning — recognizing that a technically-correct fix applied all at once to a large codebase can itself cause an incident, and designing a safer incremental path.

## 12. Common Misconceptions

1. **"`prevent_destroy` stops all forms of deletion, including manual ones."** It only blocks Terraform-initiated destroy operations; it has no effect on manual console/API deletion or on `state rm` followed by manual deletion.
2. **"`ignore_changes` reverts the real-world value back to what's in configuration."** It does the opposite — it stops Terraform from noticing or acting on the difference at all; the real-world value is left exactly as it is, and configuration is never "enforced" for ignored attributes.
3. **"`create_before_destroy` avoids downtime for every kind of resource automatically."** It requires the resource to tolerate temporary coexistence (unique naming, no exclusive-lock constraints) — resources with fixed unique-name requirements need explicit accommodation (`name_prefix`) or the pattern fails outright.
4. **"Setting `ignore_changes = [attribute]` also prevents that attribute from being set on initial creation."** It doesn't — the attribute is still applied normally when the resource is first created; `ignore_changes` only suppresses diffs on _subsequent_ plans comparing against the already-created resource.

## 13. 🔑 Key Takeaways

- `create_before_destroy` reverses the default destroy-then-create replacement order to create-then-destroy, enabling zero-downtime replacement at the cost of requiring temporary coexistence (often needing `name_prefix` over fixed `name`).
- `prevent_destroy` causes Terraform to error out before any Terraform-initiated destroy of that resource, but does not protect against manual deletion or configuration changes that remove the safeguard itself.
- `ignore_changes` (a list of attribute names, or `all`) excludes specified attributes from diff calculation entirely — used for attributes legitimately managed outside Terraform, but overuse (especially `all`) silently disables meaningful drift detection.
- All three arguments live inside a nested `lifecycle { ... }` block within a `resource` block, and can be combined on the same resource.
- These three arguments are among the most exam- and interview-relevant specifics in Terraform because their exact scope and edge-case behavior (what they do and, critically, do _not_ do) is easy to get subtly wrong.

## 14. Related Concepts & What's Next

[§34](./Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) (`count`/`for_each`) frequently pairs with `create_before_destroy` when migrating resources safely. [§35](./Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md) (`depends_on`) covers dependency ordering, which interacts with `create_before_destroy`'s create-then-destroy sequencing. [§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md) (drift detection and compliance enforcement) is directly undermined by overly broad `ignore_changes` usage, as discussed here. [§52](../Part7/Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md) (`terraform import`) and [§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) (state drift and `terraform refresh`) are the mechanisms for reconciling state with reality when `ignore_changes` isn't the right tool.

**Next Section:** [§37](./Section-37-Part5-Resource-Targeting-and-Partial-Applies.md) — `Section-37-Part5-Resource-Targeting-and-Partial-Applies.md`
