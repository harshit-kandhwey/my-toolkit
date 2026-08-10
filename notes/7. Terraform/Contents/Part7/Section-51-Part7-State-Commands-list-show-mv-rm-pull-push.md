# Section 51 (Part 7): State Commands: terraform state list/show/mv/rm/pull/push

## 1. Definition

**Plain language:** `terraform state` is a family of subcommands for inspecting and directly editing what's recorded in state, without going through a normal `plan`/`apply` cycle. They're the supported way to answer "what does Terraform think it manages," look at one resource's recorded details, rename/move a resource's tracked identity, stop tracking a resource without destroying it, or pull/push the raw state file to and from the backend.

**Precise definition:** `terraform state` is a CLI subcommand group operating directly on the configured backend's state ([§48](./Section-48-Part7-Local-State-vs.-Remote-State.md), [§49](./Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)), each acquiring a lock ([§50](./Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) before any write operation. `list` prints every resource address currently tracked in state, optionally filtered by a partial address. `show <address>` prints the full recorded attributes for one resource instance. `mv <source> <destination>` renames or relocates a resource's entry in state — updating its tracked address without touching real infrastructure — used when refactoring configuration (renaming a resource, moving it into or out of a module) without wanting Terraform to destroy and recreate the underlying object. `rm <address>` removes a resource from state without destroying the real infrastructure object, leaving it unmanaged. `pull` prints the raw current state (from the backend) to stdout. `push` writes a local state file to the backend, overwriting what's there — the most dangerous of the group.

> 💡 **Tip:** Every one of these commands changes what Terraform believes exists, not what actually exists. `state rm` doesn't delete the S3 bucket, EC2 instance, or database it's applied to — it only makes Terraform forget about it. Conflating "remove from state" with "destroy" is the single most common mistake with this command family, and the two are opposites in terms of what happens to real infrastructure.

## 2. Why This Matters

- **These commands are how you fix state without touching real infrastructure.** A resource block gets renamed during a refactor, a resource needs to move into a new module, or a resource needs to stop being Terraform-managed entirely (handed off to another team or tool) — all of these are state-only operations that would otherwise, via a naive `plan`, show up as "destroy and recreate," which is often unacceptable for stateful resources like databases.
- **`state mv` is what prevents unnecessary destroy/recreate cycles during refactoring.** Terraform's diff engine identifies resources by their address; if you simply rename a resource block in `.tf` without also telling state about the rename, Terraform sees "the old address is gone, a new one with the same config appeared" and plans a destroy-then-create, not a no-op rename.
- **`state rm` is the correct way to hand off or decommission management without deleting real infrastructure**, which is a genuinely common operational need (a resource migrating to a different team's Terraform project, or being taken over by a different tool).
- **`state list`/`show` are the primary diagnostic tools** for answering "what does Terraform actually think exists and with what attributes" during any state-related debugging ([§46](./Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md), [§47](./Section-47-Part7-The-State-File-Format-terraform-tfstate-Deep-Dive.md)).
- **`pull`/`push` are the low-level primitives underlying migration workflows** ([§53](./Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md)) — understanding them directly demystifies what `init -migrate-state` and similar higher-level operations are actually doing underneath.

## 3. Prerequisites and Dependencies

Assumes the state file structure and resource-instance addressing from [§47](./Section-47-Part7-The-State-File-Format-terraform-tfstate-Deep-Dive.md) (particularly how `count`/`for_each` resources are addressed as `resource[0]`/`resource["key"]`), and the locking behavior from [§50](./Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md), since every state-writing subcommand here acquires a lock first. [§52](./Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md) (`import`) and [§53](./Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md) (migration) both build on the `mv`/`pull`/`push` mechanics introduced here.

## 4. Architecture / Conceptual Diagram

```text
                    terraform state SUBCOMMANDS — WHAT THEY TOUCH

  Configuration (.tf)        State (backend)              Real Infrastructure
  ──────────────────         ────────────────              ────────────────────
                              ┌──────────────┐
  state list           ──────►│ read-only    │
                              │ enumerate    │
                              └──────────────┘

                              ┌──────────────┐
  state show <addr>    ──────►│ read-only    │
                              │ one instance │
                              └──────────────┘

  (rename resource      ┌────►┌──────────────┐
   block in .tf, then)  │     │ WRITE: rename│        untouched
  state mv <src> <dst> ─┘     │ address only │───X───►(no API calls)
                              └──────────────┘

                              ┌────────────────┐
  state rm <addr>      ──────►│ WRITE: delete  │        untouched
                              │ entry entirely │───X───►(no API calls —
                              └────────────────┘         becomes unmanaged)

                              ┌──────────────┐
  state pull           ◄──────│ read raw JSON│
                              │ to stdout    │
                              └──────────────┘

                              ┌─────────────────┐
  state push           ──────►│ WRITE: overwrite│       untouched
                              │ entire state    │───X───►(no API calls)
                              └─────────────────┘

  Only `apply`/`destroy` (not the state subcommands above) ever make real
  provider API calls. Every `state` subcommand here operates purely on the
  recorded mapping — that's the entire point of this command family.
```

- The critical pattern across `mv` and `rm`: both are state-only writes with **zero** provider API calls — nothing happens to real infrastructure as a direct result of running them.
- `list` and `show` are pure reads and therefore safe to run at any time with no lock contention concerns beyond the read itself.
- `pull` and `push` operate on the entire state file as a unit, not a single resource — `push` in particular replaces everything the backend holds, which is why it's the most dangerous command in this family.

## 5. Hands-On

### 5.1 `list` and `show` — Inspecting State

**Purpose:** Enumerate what's tracked and inspect one resource's recorded details.

**Syntax:**

```bash
terraform state list [address_filter]
terraform state show <address>
```

**Example usage and expected output:**

```bash
$ terraform state list
aws_vpc.main
aws_subnet.public
aws_instance.web

$ terraform state show aws_instance.web
# aws_instance.web:
resource "aws_instance" "web" {
    ami           = "ami-0abcdef1234567890"
    id            = "i-0a1b2c3d4e5f6g7h8"
    instance_type = "t3.micro"
    subnet_id     = "subnet-0a1b2c3d"
}
```

**Production usage example:** `state list` piped through `grep` is the standard way to quickly confirm exactly which of possibly hundreds of resources a state file tracks before performing any riskier operation like `mv` or `rm` on it.

**Common errors:** Running `state show` with a partial or mistyped address (especially forgetting `[0]` or `["key"]` on an expanded resource) returns `No instance found for the given address!` — always confirm the exact address via `list` first.

### 5.2 `mv` — Renaming Without Destroy/Recreate

**Purpose:** Rename a resource in configuration without Terraform planning to destroy and recreate the underlying real object.

**Syntax:**

```bash
terraform state mv <source_address> <destination_address>
```

**Example usage and expected output:**

```bash
# main.tf renamed the resource block from "web" to "app_server"

$ terraform state mv aws_instance.web aws_instance.app_server
Move "aws_instance.web" to "aws_instance.app_server"
Successfully moved 1 object(s).

$ terraform plan
No changes. Your infrastructure matches the configuration.
```

**Production usage example:** This is the standard fix any time a resource block is renamed, or moved between the root module and a child module, during a refactor — running `mv` first, then `plan`, is how a team confirms the refactor is state-safe before merging it.

**Common errors:** Renaming a resource block in `.tf` and skipping `state mv` entirely results in `plan` proposing to destroy the old address and create the new one — for a stateful resource (a database, a persistent volume) this can mean real, possibly irreversible, data loss if `apply` is run without noticing.

### 5.3 `rm` — Removing From State Without Destroying

**Purpose:** Stop Terraform from managing a resource while leaving the real object completely untouched.

**Syntax:**

```bash
terraform state rm <address>
```

**Example usage and expected output:**

```bash
$ terraform state rm aws_instance.legacy
Removed aws_instance.legacy
Successfully removed 1 object(s).

$ terraform plan
Terraform will perform the following actions:
  # aws_instance.legacy will be created
Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Used when handing a resource off to another team's Terraform project or a different tool entirely — `rm` it from this project's state (leaving the real resource alone), then either delete its resource block from configuration or `import` ([§52](./Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md)) it into the new owner's state.

**Common errors:** Forgetting to also remove the corresponding resource block from `.tf` after `state rm` means the very next `plan` proposes recreating it — because as far as configuration is concerned, that resource should still exist, and state no longer says otherwise.

## 6. Production Usage Notes

- **Always run `terraform plan` immediately after any `state` write operation** (`mv`, `rm`) to confirm the result matches intent — "no changes" (for a rename) or "1 to add" with the expectation of a subsequent `import` (for a removal) are the expected signals that the operation did what you meant.
- **`state mv` across module boundaries requires matching the full module-qualified address on both sides** — e.g., moving `aws_instance.web` into a module means the destination is `module.app.aws_instance.web`, not just a bare resource name.
- **`push` should be treated as an emergency/migration-only tool**, not part of routine workflow — nearly every legitimate use is better served by `mv`/`rm`/`import`, which operate surgically on individual resources rather than replacing the entire state file.

## 7. Security Considerations

- **`state show` and `pull` both surface full recorded attributes, including plaintext secrets** ([§46](./Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md), [§47](./Section-47-Part7-The-State-File-Format-terraform-tfstate-Deep-Dive.md), [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) — piping their output to logs, tickets, or chat messages leaks whatever sensitive values that resource's state holds, exactly as with `terraform show` ([§30](../Part4/Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md)).
- **`push` bypasses the normal plan/apply review path entirely.** Because it writes a whole state file directly, it should be restricted to the same access tier as direct backend write access, and never scripted into routine automation without explicit human review of what's being pushed.
- **Access to run these commands should be scoped as tightly as `apply` access**, since `mv`/`rm`/`push` can all silently change what Terraform will do on the next `apply` without going through a reviewed `plan` first.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                  | Likely Cause                                                                                      | Resolution Path                                                                                                                                                                                                        |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `plan` proposes destroying and recreating a resource after a rename      | The `.tf` resource block was renamed but `terraform state mv` was never run                       | Run `terraform state mv <old_address> <new_address>` to update the tracked identity, then re-plan                                                                                                                      |
| `plan` proposes creating a resource that already exists and is unmanaged | Resource was removed via `state rm` (or was never imported) but still has a matching config block | Run `terraform import` ([§52](./Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md)) to bring it back under management, or remove the resource block if it's genuinely no longer wanted |
| `state show` returns "No instance found for the given address!"          | Address typo, or missing `[index]`/`["key"]` for an expanded resource                             | Run `terraform state list` first to get the exact address                                                                                                                                                              |
| `state push` succeeds but subsequent `plan` shows unexpected changes     | Pushed state file was stale, partial, or from a different lineage than the backend expected       | Verify the pushed file's source and correctness before pushing; restore from a known-good backend version if in doubt ([§49](./Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md))                 |

## 9. Best Practices

- Run `terraform state list` (optionally filtered) before any `mv`/`rm` operation to confirm the exact address you're about to change.
- Always follow a `state mv` or `state rm` with `terraform plan` to verify the outcome matches intent before moving on.
- Reserve `push` for genuine backend migration or disaster-recovery scenarios, never as a routine part of applying changes.

## 10. Common Anti-Patterns / Mistakes

- **Renaming resource blocks in `.tf` without a corresponding `state mv`.** This is the most common source of unintended destroy/recreate plans during refactors — always pair a rename with `state mv` before the next `plan`.
- **Using `state rm` when the intent was actually to destroy the resource.** `rm` only stops tracking it; the real object survives — use `terraform destroy -target` ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) or remove the resource block and `apply` if actual deletion is intended.
- **Treating `state push` as a quick fix for "state seems wrong."** Pushing a hand-edited or stale state file risks overwriting legitimate concurrent changes and losing the backend's more current data — investigate the root cause via `list`/`show`/`pull` first.

## 11. Interview Questions

**🎯 Beginner:** _"What does `terraform state rm` actually do to the real infrastructure resource it's applied to?"_
**Model answer:** Nothing at all — `terraform state rm` only removes the resource's entry from Terraform's state file, so Terraform stops tracking and managing it. The actual real-world object (the EC2 instance, the S3 bucket, whatever it is) is left completely untouched and keeps running exactly as it was; it simply becomes unmanaged by this Terraform configuration.
_What the interviewer is probing for:_ The core distinction between "remove from state" and "destroy," which is the most commonly confused pair in this command family.

**🎯 Intermediate:** _"Why would you use `terraform state mv` instead of just renaming a resource block and letting `apply` recreate it?"_
**Model answer:** Because for most stateful resources, destroy-then-create isn't a harmless no-op — it can mean real downtime, or in the worst case, real data loss (a database, a persistent disk, anything holding state of its own outside Terraform). Terraform identifies resources by address, so simply renaming the block in `.tf` without telling state about the rename makes Terraform see it as an entirely new resource replacing an entirely different old one, and plans accordingly. `state mv` updates the tracked address directly, with zero API calls, so the next `plan` correctly shows no changes — the rename is purely a Terraform-side bookkeeping update, not an infrastructure change at all.
_What the interviewer is probing for:_ Understanding of why address-based identity matters and the real operational cost of getting a refactor wrong for stateful resources.

**🎯 Senior:** _"A team needs to split a large monolithic Terraform state into two smaller state files — some resources need to move to a brand-new state entirely, not just a new address within the same state. Walk through how `state mv` supports this, and what its limits are."_
**Model answer:** `terraform state mv` supports a `-state-out` (or, in current versions, a combination of separate source/destination state files) flag that lets you move a resource from the source project's state directly into a different state file, not just to a new address within the same one — this is the standard low-risk way to split a state, because it moves the tracked resource with zero API calls, so the underlying infrastructure is untouched throughout. The limits: it moves state entries one at a time (or via address patterns), so splitting a large state into many resources still requires either scripting a series of `mv` calls or careful manual execution, and it needs to be done from both the source and destination configurations simultaneously — the destination configuration must already have matching resource blocks (or be updated immediately after) so its own subsequent `plan` doesn't try to recreate what was just moved in. It also does nothing to help split shared dependencies — if two resources being separated reference each other (e.g., a subnet ID from one going to an instance in the other), those references need to become data sources or remote state lookups (Part 10, Part 8) as part of the same refactor, which `state mv` itself has no awareness of.
_What the interviewer is probing for:_ Real hands-on familiarity with cross-state moves specifically (not just same-state renames), and awareness that the state operation is only part of a larger refactor that also needs config-level handling of cross-state dependencies.

**🎯 Architect:** _"Your organization wants to build internal tooling that automatically runs `terraform state mv` as part of a refactoring bot whenever engineers rename resources in a pull request. What are the risks of automating this, and how would you mitigate them?"_
**Model answer:** The core risk is that `state mv` operates on trust — it assumes the human (or bot) correctly identified that the old and new addresses genuinely refer to the same underlying resource, with no independent verification of that assumption. An automated bot inferring "this looks like a rename" from a diff heuristic could misidentify an actual resource replacement (different `ami`, different `engine_version` on a database — a case where destroy/recreate is correct) as a pure rename, and silently `mv` it in state — after which `plan` would show "no changes" even though the configuration diff represents a real, intended replacement the team no longer gets warned about. Mitigations: the bot should require the diff to be a pure address change with zero attribute changes before treating it as auto-`mv`-eligible, refuse to act on anything ambiguous (any change to arguments alongside the rename), always run and post `terraform plan` output after the `mv` for human review before merge (never fire-and-forget), and log every automated `mv` with enough detail (old address, new address, PR link) to audit later. Given the risk profile, many organizations land on the bot only _suggesting_ the `state mv` command for a human to run and review, rather than executing state-write operations unattended — the review-before-merge safety net that PR-based Terraform workflows ([§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)) are built around shouldn't be silently bypassed for state operations just because they're state-only and API-call-free.
_What the interviewer is probing for:_ Whether the candidate can reason about automation risk specific to a "looks safe because it's API-call-free" operation, and proposes concrete guardrails (strict eligibility criteria, mandatory human review, audit logging) rather than either blanket approval or blanket rejection of the idea.

## 12. Common Misconceptions

1. **"`terraform state rm` destroys the resource."** It does the opposite — it stops tracking it while leaving the real object completely untouched.
2. **"Renaming a resource block in `.tf` is a safe, cosmetic change."** Without a corresponding `state mv`, it causes Terraform to plan a destroy-then-create of the underlying resource.
3. **"`state push` is a normal part of applying state changes."** It's a full state-file overwrite meant for migration/recovery scenarios, not routine workflow — `mv`/`rm`/`import` are the surgical, resource-level tools for routine use.
4. **"State subcommands are read-only and safe to run anytime without caution."** `list` and `show` are read-only; `mv`, `rm`, and `push` are writes that acquire a lock and change what the next `plan`/`apply` will do — they deserve the same care as an `apply`.

## 13. 🔑 Key Takeaways

- `terraform state list`/`show` are read-only inspection tools; `mv`/`rm`/`push` are writes that change Terraform's tracked mapping without making any real provider API calls.
- `state mv` prevents unnecessary destroy/recreate cycles when a resource is renamed or relocated in configuration — always pair a resource rename with a corresponding `mv`.
- `state rm` stops tracking a resource without destroying it; `terraform destroy -target` is the correct command when actual deletion is intended.
- Always follow a state-write operation with `terraform plan` to confirm the outcome matches intent.
- These commands carry the same access-control and secrets-sensitivity concerns as `apply` itself, since state output includes plaintext attributes and writes bypass the normal reviewed plan/apply path.

## 14. Related Concepts & What's Next

[§52](./Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md) covers `terraform import`, the counterpart to `state rm` for bringing existing, previously-unmanaged infrastructure under Terraform's management. [§53](./Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md) builds directly on `pull`/`push` mechanics for full backend migrations.

**Next Section:** [§52](./Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md) — `Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md`
