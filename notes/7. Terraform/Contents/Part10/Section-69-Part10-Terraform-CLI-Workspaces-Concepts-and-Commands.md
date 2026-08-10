# Section 69 (Part 10): Terraform CLI Workspaces: Concepts and Commands

## 1. Definition

**Plain language:** A Terraform CLI workspace is a named "slot" that holds its own state file while reusing the exact same configuration files and backend connection. Switching workspaces is like swapping which save file you're pointed at in a game — the game (your `.tf` code) doesn't change, only which save (state) is currently active.

**Precise definition:** A **Terraform CLI workspace** is a mechanism, built into Terraform core and every backend, for maintaining multiple distinct **state files** for a single working directory's configuration. Each workspace has its own `terraform.tfstate` (or backend-specific equivalent), addressed internally by workspace name, but all workspaces share the same `.tf` configuration, the same backend block, the same provider credentials, and the same provider version constraints. Workspaces are managed with the `terraform workspace` family of subcommands (`new`, `select`, `list`, `show`, `delete`) and the currently selected workspace is exposed inside configuration via the `terraform.workspace` expression ([§72](./Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md)).

> 💡 **Tip:** The single fact that resolves almost every confusion about workspaces: **a workspace is a state file, not a configuration.** If you find yourself wanting different backend settings, different provider credentials, or different `.tf` files per environment, CLI workspaces cannot give you that — they only ever give you a different state file pointed at the same code ([§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) covers this limitation in depth).

## 2. Why This Matters

- **Parallel state without parallel directories.** Workspaces let one working directory manage several instances of the same infrastructure (e.g., a feature-branch sandbox and a shared dev environment) without checking out multiple copies of the repository.
- **Exam relevance.** Workspace commands and semantics are directly tested on the HashiCorp Certified: Terraform Associate exam ([§112](../Part16/Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md)) — candidates are frequently tripped up by the difference between what workspaces isolate (state) and what they don't (backend config, credentials).
- **Foundation for the environment-separation debate.** Understanding exactly what a workspace is and isn't is the prerequisite for the workspace-vs-directory comparison in [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md) and the "wrong tool" guidance in [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) — none of that discussion is meaningful without first knowing workspaces are purely a state-partitioning feature.
- **Default-workspace awareness.** Every Terraform working directory starts in a workspace named `default`, whether or not the user ever runs a `workspace` command — many engineers unknowingly operate entirely within it for years.
- **Prevents accidental cross-environment writes.** Without workspace discipline, a `terraform apply` intended for a sandbox can silently target the shared state of a different logical environment if the wrong workspace is selected — the `list`/`show` commands exist specifically to make the active workspace visible before a destructive operation.

## 3. Prerequisites and Dependencies

This section assumes comfort with the core CLI workflow (`init`, `plan`, `apply` — Part 4) and a working understanding of what the state file records and why it exists ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)). [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md) immediately follows to contrast this mechanism against directory-based separation; [§72](./Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md) builds on the `terraform.workspace` value introduced here to show interpolation patterns; [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) revisits this section's mechanics to explain HashiCorp's own guidance on when workspaces are inappropriate.

## 4. Architecture / Conceptual Diagram

```text
                  ONE CONFIGURATION, ONE BACKEND
        (same main.tf, variables.tf, backend block — never duplicated)

                    ┌───────────────────────────┐
                    │   Backend (e.g., S3 +     │
                    │   DynamoDB lock table)    │
                    └───────────────────────────┘
                                 │
        ┌────────────────────────┼────────────────────────┐
        ▼                        ▼                        ▼
 workspace: default      workspace: dev            workspace: staging
 state key:              state key:                state key:
 env:/default/           env:/dev/                 env:/staging/
 terraform.tfstate        terraform.tfstate          terraform.tfstate
        │                        │                         │
        ▼                        ▼                         ▼
 Resources tagged        Resources tagged           Resources tagged
 under default's         under dev's                under staging's
 recorded state          recorded state              recorded state

 All three workspaces:
   - read the SAME .tf files
   - use the SAME backend configuration (bucket, region, lock table)
   - authenticate with the SAME provider credentials
   - are subject to the SAME provider version constraints

 Only the STATE FILE differs per workspace — nothing else.
```

- With the default local backend, each workspace's state lives under `terraform.tfstate.d/<workspace-name>/terraform.tfstate`, while `default` itself stays at the top-level `terraform.tfstate` for backward compatibility.
- With remote backends (S3, GCS, Azure Storage — [§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)), most backends implement workspaces by prefixing the state object's key with the workspace name (S3's default pattern is `env:/<workspace>/<key>`), so each workspace's state is a distinct object in the same bucket.
- Critically, the diagram shows **one** backend block and **one** set of provider configuration reused across every branch — there is no per-workspace backend, no per-workspace provider block, and no per-workspace `.tf` file. That single shared column is exactly the constraint [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md) and [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) build on.

## 5. Hands-On

### 5.1 Creating, Listing, and Selecting Workspaces

**Purpose:** Establish the base commands for creating a new state partition and moving between existing ones.

**Syntax:**

```bash
terraform workspace new <name>      # create a new workspace and switch to it
terraform workspace select <name>   # switch to an existing workspace
terraform workspace list            # list all workspaces; * marks the active one
terraform workspace show            # print the name of the currently active workspace
terraform workspace delete <name>   # delete a workspace (must not be the active one, and by default must have no resources tracked)
```

**Example usage and expected output:**

```bash
$ terraform workspace list
* default

$ terraform workspace new dev
Created and switched to workspace "dev"!

You're now on a new, empty workspace. Workspaces isolate their state,
so if you run "terraform plan" Terraform will not see any existing state
for this configuration.

$ terraform workspace list
  default
* dev

$ terraform workspace show
dev

$ terraform workspace select default
Switched to workspace "default".
```

**Production usage example:** A platform team scripting ephemeral pull-request preview environments runs `terraform workspace new pr-4821` in CI as part of the pipeline, applies the shared configuration into that fresh, empty-state workspace, and runs `terraform workspace delete pr-4821` after `destroy` once the PR closes — reusing one root module for every PR without checking out separate directories.

**Common errors:** Running `terraform workspace new dev` when a workspace named `dev` already exists fails with `workspace "dev" already exists`; running `terraform apply` immediately after `workspace new` and being surprised that no resources show up in `plan` — the new workspace legitimately starts with empty state, it does not inherit anything from `default`.

### 5.2 Referencing the Active Workspace and Deleting Safely

**Purpose:** Show how configuration can react to the active workspace, and the guardrails around deletion.

**Syntax:**

```hcl
resource "aws_instance" "app" {
  instance_type = terraform.workspace == "prod" ? "m5.xlarge" : "t3.micro"
  tags = {
    Environment = terraform.workspace
  }
}
```

**Example usage and expected output:**

```bash
$ terraform workspace delete dev
Workspace "dev" is not empty.

Deleting "dev" can result in dangling resources: resources that
Terraform is no longer managing. Please make sure that this is what
you want to do. If you'd like to keep managing these resources, first
run `terraform destroy` in this workspace, or move the resources out
of state with `terraform state rm`, before deleting this workspace.

$ terraform destroy          # first empty the workspace's state
...
Destroy complete! Resources: 3 destroyed.

$ terraform workspace delete dev
Deleted workspace "dev"!
```

**Production usage example:** [§72](./Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md) extends the `terraform.workspace == "prod"` conditional above into full sizing/naming lookup maps, which is the most common legitimate production use of `terraform.workspace` — driving small, size/tag-level differences from one shared configuration rather than driving structural differences (different resources entirely), which workspaces are poorly suited for.

**Common errors:** Forgetting that `terraform workspace delete` refuses non-empty workspaces by default (without `-force`) is a deliberate safety rail, not a bug — bypassing it with `-force` orphans real cloud resources that Terraform no longer tracks, since deleting the workspace deletes its record of what exists, not the infrastructure itself.

## 6. Production Usage Notes

- `terraform init` must be run once per backend configuration, not per workspace — workspaces created after `init` are immediately usable without re-running `init`, because they share the already-initialized backend connection.
- The `default` workspace is special: it cannot be deleted, and on the local backend it is the only workspace whose state file lives at the legacy top-level `terraform.tfstate` path rather than under `terraform.tfstate.d/`.
- CI pipelines that use workspaces for ephemeral environments (PR previews, one-off test stacks) should always pair `workspace new` with a guaranteed teardown step (`destroy` then `workspace delete`) — orphaned workspaces silently accumulate empty or forgotten state entries in the backend over time.
- `terraform workspace list` output is not itself proof that a workspace has no drift — always run `plan` inside the selected workspace to see its true status; the list command only shows names.

## 7. Security Considerations

- Because every workspace shares the same backend configuration and the same provider credentials (as shown in the architecture diagram above), a credential scoped for one workspace's environment is, in practice, valid for every other workspace sharing that configuration — there is no CLI-workspace-native mechanism to scope an IAM role to only the `prod` workspace and not `dev`. This is the central security argument behind [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md)'s guidance against using workspaces for prod/dev isolation.
- An operator who runs `terraform apply` with the wrong workspace silently selected (having forgotten to `workspace select`) applies changes intended for one environment against a completely different environment's real resources, using the same broad credentials in both cases — the blast radius is not reduced by the workspace boundary the way it would be by genuinely separate backends and separate execution roles ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)).
- `terraform workspace show` in a CI job's pre-apply step is a cheap, high-value guardrail: printing (and ideally asserting against an expected value) the active workspace before every `apply` catches an entire class of "applied to the wrong environment" incidents before they happen.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                                             | Likely Cause                                                                                                                           | Resolution Path                                                                                                                                                                                           |
| ------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `terraform plan` shows every resource as "to be created" in a workspace you expected to already have infrastructure | Wrong workspace is active — you're looking at an empty state, not the one you meant                                                    | Run `terraform workspace show` to confirm, `terraform workspace select <correct-name>`                                                                                                                    |
| `terraform workspace delete dev` fails with "workspace is not empty"                                                | The workspace's state still tracks real resources                                                                                      | Run `terraform destroy` in that workspace first, or `terraform state rm` each resource, before deleting                                                                                                   |
| `terraform workspace new prod` fails with an error about an existing workspace or state conflict                    | A workspace of that name already exists in the backend from a prior run (possibly by another engineer)                                 | Run `terraform workspace list` to check existing names first; use `select` instead of `new` if it already exists                                                                                          |
| Two environments unexpectedly show identical resource values despite being in different workspaces                  | Configuration doesn't actually reference `terraform.workspace` anywhere — both workspaces are applying byte-identical hardcoded values | Audit `.tf` files for hardcoded environment-specific values and drive them from `terraform.workspace` ([§72](./Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md)) or variables instead |

## 9. Best Practices

- Always confirm the active workspace with `terraform workspace show` (or bake the check into CI) immediately before any `apply` or `destroy` against shared infrastructure.
- Name workspaces predictably and consistently (`dev`, `staging`, `prod`, or `pr-<number>` for ephemeral ones) so `terraform.workspace` can be used in lookup maps without special-casing.
- Treat workspace deletion as a two-step, deliberate operation (`destroy`, then `delete`) — never reach for `-force` on `workspace delete` as a shortcut.
- Reserve CLI workspaces for genuinely lightweight, same-account, same-credential state partitioning (parallel feature branches, ephemeral PR environments) rather than for isolating environments that need separate security boundaries — see [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) for the full argument.

## 10. Common Anti-Patterns / Mistakes

- **Assuming `workspace new` clones the current workspace's state.** It does not — every new workspace starts completely empty, which surprises engineers expecting `dev` to inherit anything from `default`.
- **Using workspace names as the only signal of environment identity in automation** without also asserting the expected name in the pipeline — a typo in a `workspace select` command silently targets the wrong state with no error, since `select` succeeds for any existing workspace name.
- **Treating `terraform workspace list` as a health check.** It only enumerates names; it says nothing about whether a given workspace's state is drifted, stale, or contains orphaned resources.

## 11. Interview Questions

**🎯 Beginner:** _"What does a Terraform CLI workspace actually change when you switch between two of them?"_
**Model answer:** Only the active state file. Switching workspaces points Terraform at a different `terraform.tfstate` (or backend-equivalent) partition tied to the same configuration, same backend, and same provider credentials — the `.tf` files themselves never change.
_What the interviewer is probing for:_ Whether the candidate has internalized that workspaces are a state mechanism, not an environment or configuration mechanism — the single most common point of confusion.

**🎯 Intermediate:** _"Walk through the commands needed to create a new workspace, verify you're in it, and then safely remove it once you're done."_
**Model answer:** `terraform workspace new <name>` creates and switches to it in one step; `terraform workspace show` (or `list`, looking for the `*`) confirms which workspace is active; before deletion, `terraform destroy` must be run in that workspace to empty its state, because `terraform workspace delete <name>` refuses to remove a workspace with tracked resources unless `-force` is passed, which is discouraged since it would orphan real infrastructure.
_What the interviewer is probing for:_ Practical command fluency and awareness of the safety rail around deletion, not just memorized syntax.

**🎯 Senior:** _"A teammate proposes using one workspace per developer for personal sandbox environments, all sharing one root module and one backend. What goes right and what goes wrong with this approach at scale?"_
**Model answer:** What goes right: it's genuinely lightweight — no directory duplication, one `init`, fast to spin up and tear down, and `terraform.workspace` can trivially namespace resource names per developer. What goes wrong at scale: every developer's sandbox shares the exact same backend credentials and provider configuration, so there's no way to give one developer's sandbox a narrower IAM role than another's; a shared lock table means concurrent applies across sandboxes queue behind each other's locks even though the environments are logically unrelated; and workspace sprawl (dozens of stale `dev-alice`, `dev-bob` workspaces) accumulates silently because `workspace list` gives no indication of staleness. It's a reasonable pattern for small teams or genuinely low-stakes sandboxes, but it doesn't hold up once sandboxes need distinct credentials or independent locking.
_What the interviewer is probing for:_ Ability to reason about workspace trade-offs concretely rather than reciting "workspaces are good/bad" — specifically the shared-backend and shared-lock implications.

**🎯 Architect:** _"Your organization currently uses one Terraform root module with CLI workspaces named `dev`, `staging`, and `prod`, all applied by the same CI service account. A security audit has flagged this. What exactly is the audit flagging, and what's the migration path?"_
**Model answer:** The audit is correctly flagging that `dev`, `staging`, and `prod` share one backend configuration and one CI service account's credentials — meaning a single compromised or over-permissioned credential can reach production state and, since `apply` in the wrong workspace uses that same credential, production resources, from a pipeline nominally scoped to "dev." There is no CLI-workspace-native way to scope IAM per workspace. The migration path (detailed further in [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md) and [§74](./Section-74-Part10-Environment-Promotion-Patterns-dev-staging-prod.md)) is to move to directory-per-environment (or Terraform Cloud workspaces with distinct variable sets and credentials, [§84](../Part12/Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md)), giving each environment its own backend key, its own execution role scoped to only that environment's resources, and — critically — separate approval gates in CI so a `prod` apply requires distinct authorization from a `dev` apply. The state-partitioning convenience of CLI workspaces is preserved conceptually but reimplemented with genuine credential and backend isolation.
_What the interviewer is probing for:_ Whether the candidate can connect the CLI-workspace shared-credential limitation to a concrete organizational security finding and propose the standard, HashiCorp-endorsed remediation rather than a workspace-only patch.

## 12. Common Misconceptions

1. **"A workspace is basically a lightweight environment."** It's a state partition sharing everything else (config, backend, credentials) with every other workspace — see [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md) for why that distinction matters for environment separation specifically.
2. **"`terraform workspace new` inherits the current workspace's resources."** New workspaces always start with empty state; nothing is copied or cloned.
3. **"Deleting a workspace deletes its cloud resources."** It deletes Terraform's state record of those resources — the underlying infrastructure keeps running, now completely unmanaged (an "orphaned" resource), unless it was destroyed first.
4. **"You need a separate `terraform init` for every new workspace."** `init` initializes the backend connection once; new workspaces created afterward reuse that same initialized backend immediately.

## 13. 🔑 Key Takeaways

- A CLI workspace is a named state-file partition; it changes nothing about configuration, backend settings, or provider credentials, which are shared identically across every workspace.
- `terraform workspace new/select/list/show/delete` are the full command surface; `new` both creates and switches, `delete` refuses non-empty state without `-force`.
- Every working directory starts in an implicit `default` workspace that cannot be deleted.
- The active workspace is exposed to configuration as `terraform.workspace`, letting one configuration produce slightly different output per workspace ([§72](./Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md)).
- Because credentials and backend config are shared across all workspaces, workspaces provide no credential or backend isolation — the security implication that directly motivates [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md)'s guidance.

## 14. Related Concepts & What's Next

[§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md) takes this exact mechanism and puts it head-to-head against directory-based environment separation, spelling out precisely what each approach isolates and what it doesn't. [§71](./Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md) shows concrete file layouts for both strategies. [§72](./Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md) goes deeper on `terraform.workspace` interpolation patterns only briefly demonstrated here. [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md) is the prerequisite state-file background this section assumes.

**Next Section:** [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md) — `Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md`
