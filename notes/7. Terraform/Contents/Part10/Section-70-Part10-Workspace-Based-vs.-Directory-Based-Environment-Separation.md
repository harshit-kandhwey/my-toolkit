# Section 70 (Part 10): Workspace-Based vs. Directory-Based Environment Separation

## 1. Definition

**Plain language:** There are two common ways to manage "dev, staging, and prod all built from the same Terraform code": switch between CLI workspaces that share one configuration and one backend, or maintain a separate directory per environment, each with its own backend, variables, and (often) its own credentials. The first is lighter but shares more than most teams realize; the second duplicates more but genuinely isolates each environment.

**Precise definition:** **Workspace-based separation** uses Terraform CLI workspaces ([§69](./Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md)) — one root module, one backend configuration, one set of provider credentials — with per-workspace state files distinguishing environments, and `terraform.workspace` ([§72](./Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md)) used inside the configuration to vary environment-specific values. **Directory-based separation** uses physically distinct directories (e.g., `environments/dev/`, `environments/staging/`, `environments/prod/`), each containing its own backend block (or backend config file), its own `.tfvars`, and typically its own provider credentials/execution role, with a shared module ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)) factored out and called from each directory to avoid duplicating resource logic. The two strategies isolate different things: workspaces isolate **state only**; directories isolate **state, backend configuration, variables, and — critically — credentials and approval gates**.

> 💡 **Tip:** Ask one question to pick between them: "If someone compromised or fat-fingered this environment's Terraform run, could it touch another environment?" With CLI workspaces, sharing one backend and one credential, the honest answer is often yes. With directory-based separation done correctly, the honest answer is no — each directory can have its own state, its own backend, and its own scoped credentials.

## 2. Why This Matters

- **This is the exact decision every team using Terraform across multiple environments has to make**, usually early, and reversing it later means either migrating state between directories ([§53](../Part7/Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md)) or collapsing separate directories back into workspaces — neither is trivial.
- **HashiCorp's own published guidance favors directories for this specific use case** (elaborated fully in [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md)) — understanding the mechanical reasons why (shared backend, shared credentials) is what makes that guidance make sense rather than feeling like an arbitrary rule.
- **Blast-radius reasoning depends entirely on which model is chosen.** A misconfigured `apply` in the wrong CLI workspace still uses the same credential as every other workspace; a misconfigured `apply` in the wrong directory at least has a chance of failing outright if that directory's backend or credentials genuinely differ.
- **Certification relevance.** The Terraform Associate exam ([§112](../Part16/Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md)) tests workspace mechanics directly and expects candidates to know HashiCorp's stated position that workspaces alone are not a recommended environment-isolation strategy.
- **Cost and duplication trade-offs are real, not hypothetical.** Directory-based separation multiplies the number of `.tf`/`.tfvars` files an engineer edits for cross-cutting changes (a new required tag added to every environment means editing N directories, or N calls to a shared module) — this is the honest cost side of the comparison, not a reason to dismiss it.

## 3. Prerequisites and Dependencies

This section assumes [§69](./Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md)'s workspace mechanics are already understood — everything here is a direct comparison built on that foundation, plus baseline familiarity with modules ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)–[§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md)) and remote backends ([§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md)–[§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)) since directory-based separation leans on both. [§71](./Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md) immediately follows with concrete file layouts implementing both patterns shown conceptually here; [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) revisits this comparison to state HashiCorp's guidance explicitly.

## 4. Architecture / Conceptual Diagram

```text
 WORKSPACE-BASED SEPARATION                DIRECTORY-BASED SEPARATION

 One directory, one backend block:         Three directories, three backend configs:

 project/                                   environments/
   main.tf         (shared by all envs)       dev/
   variables.tf                                  main.tf ──► calls modules/app
   backend.tf       (ONE backend)                backend.tf   (dev's own bucket/key)
                                                  dev.tfvars
   workspace: dev ──┐                          staging/
   workspace: staging├─► same backend,            main.tf ──► calls modules/app
   workspace: prod ──┘   same credentials,         backend.tf   (staging's own bucket/key)
                          different state key       staging.tfvars
                                                  prod/
                                                    main.tf ──► calls modules/app
                                                    backend.tf   (prod's own bucket/key)
                                                    prod.tfvars

                                             modules/app/          (shared logic, no state)
                                               main.tf
                                               variables.tf

 Isolation:  STATE ONLY                     Isolation:  STATE + BACKEND + VARIABLES
             (credentials, backend,                     + CREDENTIALS (if configured per-dir)
              provider versions all shared              + independent apply/approval gates
              across dev/staging/prod)                  Cost: duplicated backend/tfvars files,
                                                          module call boilerplate per directory
```

- In the workspace model, the three branches converge on one backend block — that convergence is the entire limitation [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) is built around.
- In the directory model, each environment directory is free to point at a completely different backend (different S3 bucket, different AWS account, different subscription), assume a different execution role, and be gated by a different CI approval step — none of which CLI workspaces can express, because backend configuration is fixed at `init` time for the whole working directory regardless of which workspace is later selected.
- The shared `modules/app/` in the directory model is what keeps the resource logic itself from being copy-pasted three times — directories duplicate the _environment shell_ (backend, vars, approvals), not the _resource definitions_, when done well.

## 5. Hands-On

### 5.1 The Same Environment Variance, Implemented as a Workspace

**Purpose:** Show how instance sizing per environment looks when driven entirely by `terraform.workspace` in one shared configuration.

**Syntax:**

```hcl
# One backend.tf, shared by every workspace
terraform {
  backend "s3" {
    bucket = "acme-tfstate"
    key    = "app/terraform.tfstate"   # workspace name is prefixed automatically
    region = "us-east-1"
  }
}

locals {
  instance_size = {
    dev     = "t3.micro"
    staging = "t3.small"
    prod    = "m5.xlarge"
  }
}

resource "aws_instance" "app" {
  instance_type = local.instance_size[terraform.workspace]
}
```

**Example usage and expected output:**

```bash
$ terraform workspace select prod
Switched to workspace "prod".

$ terraform apply
# aws_instance.app will be created
  + instance_type = "m5.xlarge"
Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Small teams or genuinely low-risk internal tools (an internal dashboard with a dev and prod instance, both deployed with the same low-privilege credential) reasonably use exactly this pattern — the shared-credential limitation matters far less when there's nothing catastrophic reachable from either environment.

**Common errors:** Forgetting `terraform workspace select prod` before `apply` and instead applying `m5.xlarge`-shaped changes intended for prod into whatever workspace happened to be active — this is the exact failure mode directory-based separation structurally prevents, since there is no shared "current selection" to forget to switch.

### 5.2 The Same Environment Variance, Implemented as Directories

**Purpose:** Show the equivalent outcome using genuinely separate directories, backends, and variable files.

**Syntax:**

```hcl
# environments/prod/backend.tf
terraform {
  backend "s3" {
    bucket = "acme-tfstate-prod"        # a DIFFERENT bucket than dev/staging
    key    = "app/terraform.tfstate"
    region = "us-east-1"
    # role_arn can also differ here, scoping this backend's access separately
  }
}

# environments/prod/main.tf
module "app" {
  source        = "../../modules/app"
  instance_type = "m5.xlarge"
}
```

**Example usage and expected output:**

```bash
$ cd environments/prod
$ terraform init          # connects to prod's OWN backend/bucket — separate lock, separate state
$ terraform apply
# module.app.aws_instance.app will be created
  + instance_type = "m5.xlarge"
Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** This is the standard pattern for any organization where dev and prod must have genuinely distinct AWS accounts or IAM roles (a common security baseline) — `environments/prod/backend.tf` can point at a bucket only the prod CI role can reach, so even a misconfigured pipeline running against the `dev` directory has no credential path to touch prod state at all.

**Common errors:** Forgetting to `cd` into (or otherwise target) the correct directory before running `terraform apply` is the directory-model's analog of forgetting to `workspace select` — the failure mode doesn't disappear, but with genuinely separate credentials per directory it typically fails loudly (access denied) rather than silently succeeding against the wrong environment.

## 6. Production Usage Notes

- Directory-based separation is what makes environment-specific CI approval gates (manual approval required before `prod/` applies, automatic for `dev/`) straightforward to express, because each directory is a distinct pipeline target — workspaces, sharing one directory, make it harder to gate one workspace's apply differently from another's within the same pipeline stage.
- A shared module (`modules/app/`) under directory-based separation is what keeps resource-definition duplication low — the duplication that remains (backend blocks, `.tfvars`, module call boilerplate) is intentional and comparatively cheap; the module itself is authored once.
- Some teams adopt a hybrid: directory-per-environment for `prod` (which needs full isolation) and CLI workspaces for numerous short-lived `dev`/`pr-*` sandboxes (where the shared-credential limitation is acceptable) — this is a legitimate middle ground, not a compromise to avoid.
- Migrating from workspace-based to directory-based separation later requires moving each workspace's state into its own new backend ([§53](../Part7/Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md)'s state migration mechanics) — plan for this cost if starting with workspaces on infrastructure that might later need real isolation.

## 7. Security Considerations

- The single biggest security differentiator is credential scope: directory-based separation lets each environment's backend use a distinct execution role (`role_arn` in an S3 backend, a distinct service principal for Azure) enforced at `init` time, while CLI workspaces cannot vary credentials per workspace at all — every workspace inherits the process's ambient provider credentials identically.
- Directory-based separation also allows genuinely separate state-locking scopes ([§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) per environment — a stuck lock in `dev/`'s DynamoDB table has zero effect on `prod/`'s lock table if they're configured to use different tables, whereas workspaces sharing one backend typically share one lock table (locks are usually scoped per state-file key, so concurrent workspace operations rarely block each other directly, but the underlying table, its permissions, and its blast radius are still shared infrastructure).
- Neither model is automatically secure — directory-based separation only delivers its isolation benefit if the backend/credentials are actually configured differently per directory; copy-pasting the same backend block and same credentials into three directories recreates the exact same shared-credential problem workspaces have, just with more files.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                            | Likely Cause                                                                                                                                                | Resolution Path                                                                                                                                      |
| -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| A CI pipeline scoped to "dev only" was still able to modify prod resources                         | Workspace-based separation with one shared credential across all workspaces — the pipeline's role was never actually restricted to dev                      | Migrate to directory-based separation with a distinct, narrowly-scoped execution role per environment directory                                      |
| Same `apply` produces different results locally vs. in CI for the "same" environment               | Local session has a different active workspace selected than CI's pipeline expects (workspace model), or the wrong directory was targeted (directory model) | Assert the expected workspace/directory explicitly in both local docs and CI scripts before every apply                                              |
| Adding one new tag to every environment requires touching many files                               | Directory-based separation's duplication cost — each environment directory calls the module independently                                                   | Push the change into the shared module (`modules/app/`) instead of each environment's call site where possible                                       |
| Team can't tell which AWS account a given `terraform apply` will affect until it's already running | Backend/credential selection isn't visible up front (common in under-documented workspace setups)                                                           | Adopt directory-based separation where the directory itself signals the target account, or add explicit pre-apply account/workspace assertions in CI |

## 9. Best Practices

- Default to directory-based separation for any environment boundary that also needs a security boundary (dev vs. prod, in particular) — reserve CLI workspaces for same-credential, same-risk-tier variants (parallel dev sandboxes, PR previews).
- Factor common resource logic into a shared module regardless of which separation strategy is chosen, so the "duplication cost" of directories is confined to backend/variable boilerplate, not resource definitions.
- Make the active environment visible at a glance in both models: directory-based separation gets this for free from the working directory path; workspace-based separation needs an explicit `terraform workspace show` check baked into tooling.
- Document the choice explicitly in the repository (a root `README` stating "this project uses directory-based separation; do not introduce CLI workspaces") — silently mixing both strategies in one repository is a common source of confusion.

## 10. Common Anti-Patterns / Mistakes

- **Using CLI workspaces for prod/dev isolation and assuming the security boundary is equivalent to separate directories.** It isn't — see [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) for HashiCorp's explicit guidance on this exact mistake.
- **Adopting directory-based separation but pointing every directory's backend at the same bucket, same credentials.** This recreates the workspace model's shared-credential limitation with strictly more files to maintain and no compensating benefit.
- **Mixing both models in one repository** (some environments as workspaces, others as directories) without clear documentation — this multiplies the mental model an engineer needs to hold and increases the odds of applying to the wrong target.

## 11. Interview Questions

**🎯 Beginner:** _"In one sentence, what's the practical difference between workspace-based and directory-based environment separation?"_
**Model answer:** Workspace-based separation reuses one configuration, one backend, and one set of credentials with only the state file varying per environment, while directory-based separation gives each environment its own directory with its own backend, variables, and typically its own credentials — trading some file duplication for genuine isolation.
_What the interviewer is probing for:_ A clean, accurate one-line summary that correctly identifies state as the only thing workspaces vary.

**🎯 Intermediate:** _"Why would a team choose directory-based separation over the simpler workspace model, given it means more files to maintain?"_
**Model answer:** The main reason is isolation of things workspaces cannot vary: backend configuration, provider credentials, and state-locking scope. If dev and prod need different AWS accounts or IAM roles — a common security requirement — only directory-based separation can express that, because CLI workspaces share one backend block fixed at `init` time. The extra files (backend.tf, .tfvars per directory) are the accepted cost of that isolation.
_What the interviewer is probing for:_ Whether the candidate connects the file-duplication cost to a specific, concrete capability gained (credential/backend isolation), not just "directories are more standard."

**🎯 Senior:** _"Your team currently uses CLI workspaces for dev/staging/prod, all sharing one CI service account with broad permissions across all three. Leadership wants tighter security without a full rewrite. What's the minimum viable next step?"_
**Model answer:** The minimum viable step is migrating to directory-based separation at least for the environments that need real isolation — typically prod first. Concretely: create an `environments/prod/` directory with its own backend block pointed at a separate state location, migrate `prod`'s existing state into it ([§53](../Part7/Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md)'s backend reconfiguration and state migration commands), provision a narrowly-scoped execution role specific to prod, and update the CI pipeline so prod applies use that role and require a distinct approval gate. dev and staging can remain as CLI workspaces initially if their shared-credential risk is judged acceptable, with the same migration applied to them later if warranted. This gets the highest-risk environment genuinely isolated without requiring the whole repository to be restructured in one pass.
_What the interviewer is probing for:_ Pragmatic, risk-prioritized migration thinking rather than an all-or-nothing rewrite, plus correct recall of the state-migration mechanics involved.

**🎯 Architect:** _"Design the environment-separation strategy for a multi-region, multi-account SaaS platform with dev, staging, and three regional prod deployments. Justify workspace usage anywhere in the design, if at all."_
**Model answer:** Use directory-based separation as the top-level structure — `environments/dev/`, `environments/staging/`, `environments/prod-us/`, `environments/prod-eu/`, `environments/prod-apac/` — each with its own backend pointed at a region- and account-scoped bucket, its own execution role scoped to only that account/region, and prod directories gated by mandatory approval in CI while dev/staging apply automatically on merge. All resource logic lives in shared modules (`modules/`) called identically from each environment directory, varying only by `.tfvars`. CLI workspaces still earn a legitimate, narrow role within this design: inside `environments/dev/` specifically, use workspaces for ephemeral per-engineer or per-PR sandboxes (`dev-alice`, `pr-4821`) where sharing dev's already-lower-stakes credential is an acceptable trade for the convenience of not creating a new directory per sandbox. The architectural principle is that workspaces are reserved for variance _within_ a single security/credential boundary, never used to _create_ that boundary between environments that must be genuinely isolated (regions with data-residency requirements, or prod vs. everything else).
_What the interviewer is probing for:_ Ability to combine both strategies correctly at scale — using directories for real isolation boundaries and workspaces only where their shared-everything nature is actually harmless, rather than picking one strategy dogmatically for the entire system.

## 12. Common Misconceptions

1. **"Workspaces and directories are just two equally valid styles with no functional difference."** They differ in exactly what's isolated — state only, versus state plus backend plus credentials — which is a functional, not stylistic, difference.
2. **"Directory-based separation always means fully separate AWS accounts."** It means the _option_ is available (different backend, different credentials); a team can still point every directory's backend at the same account if that's an intentional choice — directories create the capability for isolation, they don't force it.
3. **"Workspaces are the officially deprecated approach."** They're not deprecated — they remain a fully supported, useful feature for their appropriate use case (same-credential state partitioning); they're simply not recommended specifically for isolating environments with different security requirements ([§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md)).
4. **"Shared modules only work with directory-based separation."** Modules work identically regardless of separation strategy — a workspace-based configuration can and often should also be built from shared modules.

## 13. 🔑 Key Takeaways

- Workspace-based separation isolates only the state file; backend configuration, provider credentials, and provider versions are shared identically across every workspace.
- Directory-based separation isolates state, backend configuration, variables, and — when configured deliberately — credentials and CI approval gates, at the cost of some duplicated boilerplate per environment.
- The deciding question is whether the environment boundary is also meant to be a security boundary; if yes, directory-based separation is the appropriate tool.
- Shared modules keep resource-definition duplication low under either strategy — the duplication directories introduce is confined to backend/variable/boilerplate files, not resource logic.
- Hybrid approaches (directories for true isolation boundaries, workspaces for same-credential variance within one boundary) are legitimate and common in mature setups.

## 14. Related Concepts & What's Next

[§71](./Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md) turns this conceptual comparison into concrete file-tree layouts for both strategies. [§72](./Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md) goes deeper into the `terraform.workspace` interpolation pattern used in the workspace-based example above. [§73](./Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) states HashiCorp's explicit guidance against using workspaces for prod/dev isolation, building directly on the credential-sharing limitation described here. [§53](../Part7/Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md) covers the state migration mechanics referenced in the senior interview answer above.

**Next Section:** [§71](./Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md) — `Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md`
