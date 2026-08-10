# Section 37 (Part 5): Resource Targeting and Partial Applies

## 1. Definition

**Plain language:** Normally, `terraform plan` and `terraform apply` consider your entire configuration — every resource, every dependency. Sometimes you don't want that: you want to act on just one resource (or a small, specific set) while leaving everything else untouched for this run. `-target` lets you do that, narrowing Terraform's attention to a specific resource address and whatever it depends on. It's a scalpel for emergencies and edge cases — not a tool meant for routine, everyday use.

**Precise definition:** **Resource targeting** is invoked with the `-target=<resource_address>` CLI flag (repeatable for multiple targets) on `terraform plan`, `terraform apply`, or `terraform destroy`, restricting the operation to the specified resource address(es) plus any resources they transitively **depend on** (never resources that depend on them, unless those are also explicitly targeted). This produces a **partial apply**: a subset of the full configuration's changes is planned and applied, while the rest of the configuration is left as-is for this run, even if it also has pending changes. HashiCorp's official guidance frames `-target` as an exceptional-use tool for recovery scenarios and complex migrations, not routine workflow — because a targeted apply followed by a full apply can produce a different final result than a single full apply would have, due to the resource graph being evaluated in a truncated form.

> 💡 **Tip:** `-target` restricts _outward_ from the address you give it, following dependencies _inward_ (upstream) automatically, but never follows _outward_ (downstream) to things that depend on your target — meaning a targeted apply can silently leave downstream resources in a state inconsistent with what your target's change implies, until you run a full, untargeted apply afterward. Always follow a `-target` apply with a full `terraform plan` (no `-target`) to see what's still outstanding.

## 2. Why This Matters

- **`-target` is a legitimate emergency tool** — recovering from a broken apply, unblocking a single failing resource without touching hundreds of unrelated ones, or working around a provider bug affecting one resource type.
- **It is also one of the most misused CLI flags in Terraform**, frequently reached for as a routine workaround for slow applies or unfamiliarity with the full plan, which erodes the safety guarantees a full, complete plan otherwise provides.
- **A targeted apply can produce configuration drift relative to a full apply** — because Terraform's plan for a targeted subset is computed without full awareness of the rest of the graph's pending changes, repeated targeted applies over time can leave a codebase in a state a full apply from scratch would never have produced.
- **State operations (`terraform state mv`, `rm`, `import`) share the same addressing model as `-target`**, so understanding resource address syntax here directly transfers to state management workflows ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)–[§52](../Part7/Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md)).
- **Certification and interview relevance:** understanding _why_ `-target` is discouraged (not just that it exists) is a frequently tested distinction between candidates who've memorized the flag and those who understand Terraform's execution model.

## 3. Prerequisites and Dependencies

This section depends on [§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md) (resource addressing — `-target` takes exactly the address grammar introduced there) and [§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md) (the resource graph, since targeting's "depends on, but not depended on by" behavior is a graph traversal concept). [§31](../Part4/Section-31-Part4-Common-CLI-Flags-Automation-Friendly-Patterns.md) (Common CLI Flags and Automation-Friendly Patterns) previewed `-target` alongside `-auto-approve`, `-var-file`, and `-lock`; this section is the dedicated deep dive. [§25](../Part4/Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md)–[§26](../Part4/Section-26-Part4-terraform-apply-and-terraform-destroy.md) (terraform plan/apply/destroy) are assumed baseline CLI fluency.

## 4. Architecture / Conceptual Diagram

```text
  DEPENDENCY GRAPH (full)

       aws_vpc.main
             │
             ▼
       aws_subnet.public
             │
             ▼
       aws_instance.web ◄── you run: terraform plan -target=aws_instance.web
             │
             ▼
       aws_eip.web_ip


  WHAT GETS INCLUDED when targeting aws_instance.web:

       aws_vpc.main         ✅ included (target depends on this — upstream)
       aws_subnet.public    ✅ included (target depends on this — upstream)
       aws_instance.web     ✅ included (the target itself)
       aws_eip.web_ip       ❌ EXCLUDED (this depends on the target — downstream,
                                          never auto-included even though it needs
                                          web's ID and will show drift/be stale
                                          until a full apply runs)

  RESULT: a "partial apply" — only the target and its upstream dependencies
  are considered; downstream resources are left untouched, potentially
  now inconsistent with the target's new state until a full, untargeted
  apply is run afterward.
```

- Targeting always pulls in the **transitive closure of dependencies feeding into** the target — you never end up with a broken apply because an upstream prerequisite was silently skipped.
- Targeting **never** pulls in resources that depend on the target — this is deliberate (Terraform can't know if you want those touched too), but it means downstream resources are frequently left stale relative to the target's new state until a subsequent full apply.
- Multiple `-target` flags can be combined in a single invocation (`-target=A -target=B`), each expanding the included set with its own upstream dependency closure.

## 5. Hands-On

### 5.1 Basic `-target` on `plan`

**Purpose:** Preview changes restricted to a single resource address, useful for reviewing a specific, isolated change before committing to a broader apply.

**Syntax:**

```bash
terraform plan -target=<resource_address>
```

**Example usage and expected output:**

```bash
$ terraform plan -target=aws_instance.web

Warning: Resource targeting is in effect

You are planning a partial apply, which can produce an incomplete plan or
apply if other resources depend on the targeted resources. Resource
targeting is intended for exceptional use, such as recovering from errors
or mistakes.

  # aws_instance.web will be updated in-place
  ~ resource "aws_instance" "web" {
      ~ instance_type = "t3.micro" -> "t3.small"
    }

Plan: 0 to add, 1 to change, 0 to destroy.
```

**Production usage example:** Reviewing an isolated, high-confidence change (an instance size bump) in a large shared-state configuration without also re-evaluating (and potentially exposing unrelated pending drift on) every other resource in that state.

**Common errors:** Forgetting that other genuinely pending changes elsewhere in the configuration are simply not shown or applied in this run — a targeted plan showing "0 to add, 1 to change, 0 to destroy" does not mean the rest of the configuration has no pending changes; it means those changes weren't considered at all.

### 5.2 `-target` on `apply` — Partial Apply in an Emergency

**Purpose:** Apply a fix to one broken resource without touching the rest of a large, otherwise-unrelated configuration mid-incident.

**Syntax:**

```bash
terraform apply -target=<resource_address>
```

**Example usage and expected output:**

```bash
$ terraform apply -target=aws_security_group_rule.emergency_block

Warning: Resource targeting is in effect
...

  # aws_security_group_rule.emergency_block will be created
  + resource "aws_security_group_rule" "emergency_block" {
      + type        = "ingress"
      + cidr_blocks = ["203.0.113.0/24"]
    }

Plan: 1 to add, 0 to change, 0 to destroy.

Do you want to perform these actions?
  Terraform will perform the actions described above.
  Only 'yes' will be accepted to approve.

  Enter a value: yes

aws_security_group_rule.emergency_block: Creating...
aws_security_group_rule.emergency_block: Creation complete after 2s

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** A textbook legitimate use case — during an active incident, adding a single emergency-blocking security group rule via Terraform (to keep it under version control rather than clicking it into the console) without waiting for or risking a full, larger apply that might include unrelated, not-yet-reviewed changes.

**Common errors:** Treating this as "done" without a follow-up full plan — leaving the incident-response change unreconciled with the rest of configuration risks a future full apply reverting or conflicting with it if the corresponding permanent fix isn't also committed to the actual `.tf` files.

### 5.3 Multiple `-target` Flags Combined

**Purpose:** Restrict an apply to a specific, deliberately chosen small set of resources spanning more than one address.

**Syntax:**

```bash
terraform apply -target=<address_a> -target=<address_b>
```

**Example usage and expected output:**

```bash
$ terraform plan -target=module.database.aws_db_instance.primary -target=module.database.aws_db_parameter_group.custom

Warning: Resource targeting is in effect
...

  # module.database.aws_db_parameter_group.custom will be updated in-place
  # module.database.aws_db_instance.primary will be updated in-place

Plan: 0 to add, 2 to change, 0 to destroy.
```

**Production usage example:** Rolling out a parameter group change and the instance's reference to it together, deliberately excluding every other resource in a shared `database` module's state from this specific, reviewed change window.

**Common errors:** Each `-target` independently pulls in its own upstream dependency closure — combining unrelated targets from different parts of a large graph can still result in a surprisingly large included set, defeating the purpose of narrowing the operation; always verify with `plan` before `apply`.

### 5.4 The Required Follow-Up: Full Untargeted Plan

**Purpose:** Confirm the overall configuration is fully reconciled after any targeted apply, closing the gap `-target` deliberately leaves open.

**Syntax:**

```bash
terraform plan
```

**Example usage and expected output:**

```bash
$ terraform plan
  # aws_eip.web_ip will be updated in-place
  ~ resource "aws_eip" "web_ip" {
      ~ instance = "i-0oldinstance123" -> "i-0newinstance456"
        # this downstream resource wasn't touched by the earlier
        # -target=aws_instance.web apply, and is only now surfaced
    }

Plan: 0 to add, 1 to change, 0 to destroy.
```

**Production usage example:** This is the mandatory second step after any targeted apply in a disciplined workflow — running a full, untargeted `plan` immediately afterward to surface exactly what the targeted operation left unreconciled, and then deciding deliberately whether to apply that too or defer it.

**Common errors:** Skipping this step is the single most common way `-target` usage leads to accumulating, unnoticed drift between configuration and reality — teams that use `-target` routinely without this follow-up habit often discover months later that a full apply produces a large, surprising, and hard-to-review diff.

## 6. Production Usage Notes

- **`-target` should be the exception, documented and justified, not a routine habit** for working around slow plans or large state files — the correct fix for chronically slow full plans is usually state splitting or better module boundaries ([§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)), not perpetual targeting.
- **CI/CD pipelines should generally never use `-target` in their default automated path** ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)–[§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)) — automated pipelines are exactly the context where a full, complete, reviewed plan matters most; targeting is a manual, human-judgment tool for exceptional situations.
- **`-target` and `-destroy`-mode targeting are asymmetric in risk** — targeting a `destroy` operation is especially dangerous, since it can destroy a resource while leaving dependents that reference it (outside the targeted set) now pointing at nothing, a common cause of subsequent apply failures on the _next_, untargeted run.

## 7. Security Considerations

- Because `-target` restricts what's reviewed in a given plan, it can be (mis)used to slip a change through without full-configuration scrutiny in a workflow that otherwise relies on reviewing complete plan output — code review processes for Terraform changes should be wary of PRs whose stated verification is a targeted plan rather than a full one.
- A targeted apply that creates a resource but leaves its downstream security-relevant dependents (an IAM policy attachment, a security group rule referencing it) unapplied can leave infrastructure in a genuinely insecure intermediate state — e.g., a new resource created but not yet locked down by the security group rule that would normally accompany it in a full apply.
- Emergency `-target` usage during an incident is a legitimate, common pattern (§5.2) but should still go through the same credential/least-privilege execution role controls ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)) as any other apply — incident urgency is not a reason to bypass access controls, even if it sometimes shortens review cycles.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                            | Likely Cause                                                                                                                             | Resolution Path                                                                                                                                                                                                                                                             |
| ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A subsequent full `terraform plan` shows unexpected changes after a targeted apply | Downstream resources depending on the targeted resource weren't included and are now stale relative to it                                | Review and apply the full plan deliberately; this is expected `-target` behavior, not a bug                                                                                                                                                                                 |
| `Error: Resource address ... does not exist` when using `-target`                  | Wrong address syntax — missing module prefix, wrong instance key, or resource doesn't exist yet in state or config                       | Verify the exact address with `terraform state list` or by checking configuration first ([§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md))                                                                                                      |
| Targeted `apply` succeeds but the "real" fix never lands in `.tf` files            | A manual/emergency targeted change was applied to fix a symptom but the corresponding permanent configuration change was never committed | Always pair emergency targeted applies with an immediate follow-up PR updating the actual `.tf` source                                                                                                                                                                      |
| Team routinely uses `-target` to speed up applies on a large configuration         | Underlying issue is a state file/graph that's grown too large, not a workflow problem `-target` genuinely solves                         | Consider state splitting or module boundary redesign ([§53](../Part7/Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md), [§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) rather than routine targeting |

## 9. Best Practices

- Treat every `-target` usage as exceptional — require a brief, documented reason (an incident ticket, a migration plan) rather than using it as a default habit.
- Always run a full, untargeted `terraform plan` immediately after any targeted apply, to surface exactly what remains unreconciled before deciding the next step.
- Prefer fixing the root cause of "I need `-target` because plans are too slow/scary" (state splitting, module boundaries, better team ownership of state, [§106](../Part15/Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md), [§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) over normalizing routine targeting as a workaround.
- Never combine `-target` with `-auto-approve` in anything but a well-understood, already-reviewed emergency scenario — the combination removes both the safety of a full plan and the safety of a manual approval step.

## 10. Common Anti-Patterns / Mistakes

- **Using `-target` routinely to avoid dealing with a large or slow-to-plan configuration**, instead of addressing the actual root cause (state/module structure) — this normalizes partial applies as standard practice and gradually erodes confidence that a full `plan` reflects reality.
- **Targeting a `destroy` operation without considering what depends on the targeted resource**, potentially leaving dependents referencing a now-nonexistent object until the next full run surfaces the resulting breakage.
- **Never following up a targeted apply with a full, untargeted plan**, allowing drift between what's actually applied and what a complete run of the current configuration would produce to silently accumulate over time.

## 11. Interview Questions

**🎯 Beginner:** _"What does the `-target` flag do on `terraform plan` or `terraform apply`?"_
**Model answer:** `-target=<resource_address>` restricts the plan or apply operation to just that specific resource (plus whatever it depends on), instead of considering the entire configuration. It's used to narrow Terraform's focus to a single resource or a small, specific set of resources for one particular run.
_What the interviewer is probing for:_ Basic familiarity with the flag's existence and purpose, as a foundation for deeper "when should you use it" questions.

**🎯 Intermediate:** _"If you run `terraform apply -target=aws_instance.web`, and something else in your configuration depends on `aws_instance.web`'s output, does that dependent resource get updated too?"_
**Model answer:** No — targeting only pulls in resources the target _depends on_ (its upstream prerequisites, automatically included so the target itself can be created/updated correctly), never resources that _depend on_ the target (its downstream dependents). So if an Elastic IP resource references `aws_instance.web`'s ID, and `aws_instance.web` is replaced during a targeted apply, the Elastic IP resource is left untouched by that specific apply — it will only be reconciled on a subsequent, untargeted plan/apply that surfaces the now-stale relationship.
_What the interviewer is probing for:_ Accurate understanding of the directional, upstream-only inclusion behavior — a common point of confusion that leads to real production drift if misunderstood.

**🎯 Senior:** _"Why does HashiCorp specifically discourage routine use of `-target`, beyond it just being 'a partial apply'? What actually goes wrong?"_
**Model answer:** The core issue is that Terraform's plan is computed against a graph that's been artificially truncated to the targeted subset — this means the plan Terraform produces for a targeted run can genuinely differ from what a full, untargeted plan would have produced for the same resource, because the full plan considers interactions and pending changes elsewhere in the configuration that the targeted plan simply never evaluates. Repeated targeted applies over time, without regular full-plan reconciliation, can accumulate configuration drift where the deployed infrastructure diverges from what a clean, full `terraform apply` from the current configuration would actually produce — sometimes in ways that are only discovered much later when a full apply surfaces a large, confusing diff. It also removes the review benefit of seeing the complete picture in a single plan, which is one of Terraform's core safety properties. This is why it's positioned as an exceptional recovery/migration tool, not a routine performance or convenience shortcut.
_What the interviewer is probing for:_ Whether the candidate understands the actual mechanism behind the risk (graph truncation and accumulated drift), not just the rule "don't use -target often."

**🎯 Architect:** _"A team has normalized using `-target` in their day-to-day workflow because their monolithic state file has grown to thousands of resources and full plans take 20+ minutes. How would you address this at the root, and what would you tell them about their current `-target` habit in the meantime?"_
**Model answer:** The root cause is architectural, not a workflow inconvenience `-target` genuinely solves — a state file with thousands of resources managed as one unit is a scaling failure of state/module design, not something targeting should be used to routinely paper over. The real fix is decomposing the monolithic state into smaller, independently-planned units aligned with genuine ownership and change-frequency boundaries (separate state files per service, environment, or bounded context, using remote state and possibly Terraform Cloud workspace dependencies, [§53](../Part7/Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md), [§88](../Part12/Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md), [§106](../Part15/Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md), [§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) so that any individual team's routine plan only considers the resources relevant to them, without needing `-target` at all. In the meantime, I'd have the team keep using `-target` for genuinely time-sensitive changes, but require every targeted apply to be paired with a full, untargeted `plan` run at least daily (even if not applied immediately) specifically to catch accumulating drift before it becomes a large, surprising diff — treating the current habit as a stopgap under active remediation, not an accepted permanent workflow, with the state-splitting project tracked and resourced as the actual fix.
_What the interviewer is probing for:_ Whether the candidate can distinguish a workflow symptom from its architectural root cause and propose a real remediation path rather than either banning `-target` outright or accepting the status quo indefinitely.

## 12. Common Misconceptions

1. **"`-target` only applies the change to that one resource and nothing else is affected."** It also includes every resource the target transitively depends on (upstream) — the actually-applied set is often larger than just the named resource.
2. **"A targeted plan/apply tells you the complete, current state of pending changes."** It only reflects the targeted subset — other genuinely pending changes elsewhere in configuration are simply not evaluated or shown at all.
3. **"`-target` is fine to use routinely once a team gets comfortable with it."** HashiCorp's own guidance and the mechanism itself (graph truncation, accumulated drift risk) both argue against normalizing it as anything but an exceptional-use tool.
4. **"Resources depending on a targeted resource are automatically updated to stay consistent."** They are not — downstream dependents are never auto-included; they're left as-is until a subsequent, untargeted run reconciles them.

## 13. 🔑 Key Takeaways

- `-target=<resource_address>` restricts `plan`/`apply`/`destroy` to a specific resource plus its upstream dependencies — never its downstream dependents.
- HashiCorp positions `-target` as an exceptional-use recovery/migration tool, not routine workflow, because a targeted plan is computed against a truncated graph and can differ from what a full plan would produce.
- Always follow a targeted apply with a full, untargeted `terraform plan` to surface what remains unreconciled.
- Multiple `-target` flags can be combined in one invocation, each independently expanding the included set with its own dependency closure.
- Chronic reliance on `-target` to manage slow or unwieldy plans is a signal of an underlying state/module architecture problem, not something targeting itself should be used to solve long-term.

## 14. Related Concepts & What's Next

[§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md) established the resource addressing grammar `-target` consumes directly. [§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md) (the resource graph) explains the dependency-closure mechanics behind targeting's upstream-only inclusion behavior. [§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md) (state commands) and [§52](../Part7/Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md) (`terraform import`) share the same addressing model for different operations. [§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md) (performance at scale) covers the state-splitting alternative to chronic `-target` reliance discussed in this section's Architect-tier answer.

**Next Section:** [§38](./Section-38-Part5-Local-Only-Resources-null_resource-terraform_data-random-time.md) — `Section-38-Part5-Local-Only-Resources-null_resource-terraform_data-random-time.md`
