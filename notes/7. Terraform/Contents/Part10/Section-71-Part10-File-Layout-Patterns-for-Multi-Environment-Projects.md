# Section 71 (Part 10): File Layout Patterns for Multi-Environment Projects

## 1. Definition

**Plain language:** Once a team decides how it wants to separate environments ([§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)), that decision has to become an actual directory tree that engineers navigate every day. This section catalogs the concrete file layouts teams use in practice — where the shared logic lives, where environment-specific values live, and how the two connect.

**Precise definition:** A **multi-environment file layout** is the concrete arrangement of directories, `.tf` files, and `.tfvars` files that implements either workspace-based or directory-based environment separation (or a hybrid). The three dominant patterns are: (1) **single-directory-plus-workspaces**, one root module with per-workspace `.tfvars` files selected via `-var-file`; (2) **environment-directories-plus-shared-modules**, a top-level `modules/` directory holding reusable resource logic and an `environments/<env>/` directory per environment that calls those modules with environment-specific arguments; and (3) **Terragrunt-style DRY layering** (mentioned here for completeness, detailed tooling out of this roadmap's scope), which generates per-environment Terraform invocations from a smaller set of DRY configuration files using a wrapper tool rather than native Terraform alone.

> 💡 **Tip:** The file layout is not the isolation mechanism — it's the packaging around whichever mechanism [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md) already chose. A beautifully organized `environments/` directory tree still shares one backend and one credential if every subdirectory's `backend.tf` points at the same bucket; the layout only pays off once it's paired with genuinely distinct backend/variable configuration per environment.

## 2. Why This Matters

- **Layout is what new engineers see first.** A confusing or inconsistent file layout is often the actual source of "I don't understand how environments work here" complaints, even when the underlying separation strategy ([§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)) is sound.
- **Layout determines the blast radius of a typo.** A layout where `prod.tfvars` and `dev.tfvars` sit as sibling files in one directory, both usable with any `-var-file` flag, makes it trivially easy to fat-finger the wrong flag; a layout where `prod/` is a physically separate directory makes that mistake require a deliberate `cd`.
- **Layout affects how shared logic gets reused.** A flat, per-environment copy-paste layout (no `modules/`) means every improvement or bug fix has to be applied N times, once per environment directory — the module-based layouts in this section exist specifically to avoid that.
- **Terraform Associate exam relevance.** The exam expects familiarity with standard file naming conventions ([§16](../Part3/Section-16-Part3-Terraform-File-Structure-and-Conventions.md)) extended across environments, including recognizing `-var-file` and per-environment `.tfvars` usage in CLI-flag questions.
- **Sets up [§74](./Section-74-Part10-Environment-Promotion-Patterns-dev-staging-prod.md)'s promotion pipeline.** Environment promotion (dev → staging → prod) is only mechanically clean when the underlying layout makes "the same module, different inputs, different environment" an explicit, visible pattern rather than something inferred from scattered files.

## 3. Prerequisites and Dependencies

This section assumes [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)'s conceptual comparison of workspace-based vs. directory-based separation, plus module fundamentals ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)–[§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md)) for the shared-module layouts, and `.tfvars`/`-var-file` mechanics ([§40](../Part6/Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)) for variable-file-driven layouts. [§72](./Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md) follows with `terraform.workspace` interpolation patterns that specifically apply to the single-directory-plus-workspaces layout shown here; [§74](./Section-74-Part10-Environment-Promotion-Patterns-dev-staging-prod.md) builds directly on the environment-directory layout to describe promotion pipelines.

## 4. Architecture / Conceptual Diagram

```text
 PATTERN 1: Single directory + workspaces + per-workspace .tfvars

 project/
   main.tf, variables.tf, backend.tf     (one copy, shared)
   dev.tfvars
   staging.tfvars
   prod.tfvars
 $ terraform workspace select prod && terraform apply -var-file=prod.tfvars


 PATTERN 2: Environment directories + shared modules   (most common at scale)

 modules/
   network/           (reusable, no backend, no state of its own)
     main.tf  variables.tf  outputs.tf
   app/
     main.tf  variables.tf  outputs.tf

 environments/
   dev/
     main.tf          ──► module "network" { source = "../../modules/network" ... }
     backend.tf        (dev's own bucket/key)
     terraform.tfvars   (dev's own values)
   staging/
     main.tf  backend.tf  terraform.tfvars   (staging's own copies)
   prod/
     main.tf  backend.tf  terraform.tfvars   (prod's own copies)


 PATTERN 3: DRY wrapper-generated layout (Terragrunt-style — noted, not covered in depth)

 live/
   dev/terragrunt.hcl       ──► includes root config, sets dev-only inputs
   staging/terragrunt.hcl   ──► includes root config, sets staging-only inputs
   prod/terragrunt.hcl      ──► includes root config, sets prod-only inputs
 terraform/modules/...       (plain Terraform modules, wrapper-agnostic)
```

- Pattern 1 maps directly onto [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)'s workspace-based separation; Pattern 2 maps directly onto directory-based separation; Pattern 3 is an ecosystem tool built on top of native Terraform to reduce the boilerplate Pattern 2 introduces, included here only for situational awareness since native Terraform tooling is this roadmap's scope.
- In Pattern 2, `modules/` never contains a backend block and is never applied directly — it's only ever called from an `environments/<env>/main.tf`, which is where the actual state-bearing root modules live.

## 5. Hands-On

### 5.1 Pattern 1 — Single Directory with Per-Workspace Variable Files

**Purpose:** Show the minimal file set for workspace-based separation, including how environment-specific values are supplied without hardcoding them into the shared configuration.

**Syntax:**

```text
project/
├── backend.tf
├── main.tf
├── variables.tf
├── dev.tfvars
├── staging.tfvars
└── prod.tfvars
```

```hcl
# variables.tf
variable "instance_type" {
  type = string
}

# prod.tfvars
instance_type = "m5.xlarge"

# dev.tfvars
instance_type = "t3.micro"
```

**Example usage and expected output:**

```bash
$ terraform workspace select prod
Switched to workspace "prod".

$ terraform apply -var-file=prod.tfvars
# aws_instance.app will be created
  + instance_type = "m5.xlarge"
Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** A small internal-tools team with a single low-privilege AWS account and no regulatory need for environment-level credential separation uses exactly this layout — three `.tfvars` files, one workspace switch plus one `-var-file` flag per deploy, with a wiki page reminding engineers both must match (workspace `prod` with `prod.tfvars`, never mixed).

**Common errors:** Selecting workspace `prod` but passing `-var-file=dev.tfvars` by copy-paste mistake — nothing in the CLI enforces that the workspace name and the `.tfvars` filename correspond, so this combination applies dev-sized values into prod's state without any warning.

### 5.2 Pattern 2 — Environment Directories Calling Shared Modules

**Purpose:** Show the standard directory-based layout, including how a shared module is called with different inputs per environment.

**Syntax:**

```text
modules/app/main.tf
  resource "aws_instance" "app" {
    instance_type = var.instance_type
  }
  variable "instance_type" { type = string }

environments/prod/main.tf
  module "app" {
    source        = "../../modules/app"
    instance_type = var.instance_type
  }
  variable "instance_type" { type = string }

environments/prod/terraform.tfvars
  instance_type = "m5.xlarge"

environments/prod/backend.tf
  terraform {
    backend "s3" {
      bucket = "acme-tfstate-prod"
      key    = "app/terraform.tfstate"
      region = "us-east-1"
    }
  }
```

**Example usage and expected output:**

```bash
$ cd environments/prod
$ terraform init
$ terraform apply
# module.app.aws_instance.app will be created
  + instance_type = "m5.xlarge"
Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** This is the standard enterprise layout referenced throughout [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md) — `modules/app` is versioned and reviewed once, and a change to it (say, adding a new required tag) is validated in `environments/dev/` first, then promoted through `staging/` and `prod/` per [§74](./Section-74-Part10-Environment-Promotion-Patterns-dev-staging-prod.md)'s promotion workflow, with each directory's `terraform.tfvars` supplying only what genuinely differs (instance size, replica count, region).

**Common errors:** Letting `environments/prod/main.tf` drift out of sync with `environments/dev/main.tf` (someone adds a resource block directly in `prod/main.tf` instead of the shared module) silently reintroduces the duplication problem this layout exists to avoid — code review should specifically check that environment directories only ever _call_ modules with different inputs, never define diverging resource logic inline.

## 6. Production Usage Notes

- Naming the environment-specific variable file `terraform.tfvars` (rather than `dev.tfvars`) inside each `environments/<env>/` directory lets `terraform apply` pick it up automatically without an explicit `-var-file` flag, since Terraform auto-loads any file literally named `terraform.tfvars` or matching `*.auto.tfvars` in the working directory — this removes one manual step compared to Pattern 1.
- Keep `modules/` genuinely backend-free and stateless — a module should never contain a `backend` block or be applied directly; if a "module" needs its own backend, it's actually functioning as another root module and the layout should reflect that.
- Large organizations sometimes split further: a `global/` directory for account-wide resources (IAM roles, shared VPC peering) applied once, separate from any single environment directory, to avoid a false per-environment framing for resources that genuinely aren't per-environment.
- Consistent internal naming (`environments/` vs. `envs/` vs. `stacks/`) matters less than picking one and enforcing it repo-wide — mixed naming across repositories in the same organization is a recurring source of onboarding friction.

## 7. Security Considerations

- Pattern 1's shared directory means any engineer with filesystem/repo access can, in principle, run `-var-file=prod.tfvars` locally against whatever credentials their shell currently has configured — there's no structural barrier stopping a `prod.tfvars` apply from a laptop, only process/discipline (branch protection requiring CI-only applies, [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)).
- Pattern 2's separate `backend.tf` per environment directory is what allows genuinely different credentials per environment ([§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)) — but only if each `backend.tf` is actually configured to assume a different role or point at a different account; auditing that these files genuinely diverge (not just their bucket name, but their access-control boundary) is a worthwhile periodic check.
- `.tfvars` files containing secrets should never be committed regardless of layout — this applies identically to `dev.tfvars`/`prod.tfvars` in Pattern 1 and to each `environments/<env>/terraform.tfvars` in Pattern 2; `.gitignore` rules and dedicated secrets managers ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)–[§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)) are the standard mitigation either way.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                              | Likely Cause                                                                                      | Resolution Path                                                                                                                                                                                           |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `terraform apply` in Pattern 1 uses unexpected variable values                       | Workspace and `-var-file` flag don't correspond (e.g., workspace `prod` with `dev.tfvars`)        | Standardize a wrapper script or Makefile target that always pairs the correct workspace with the correct `-var-file`, removing manual pairing                                                             |
| Two environment directories in Pattern 2 have quietly diverged in resource logic     | An engineer edited one environment's `main.tf` directly instead of the shared module              | Diff `environments/*/main.tf` files periodically; move any diverging logic back into `modules/` with a variable to express the difference                                                                 |
| `terraform init` in a fresh `environments/staging/` checkout fails to find a backend | `backend.tf` wasn't copied/created for the new environment directory, or has a typo in bucket/key | Verify `backend.tf` exists and is correctly scoped per environment; re-run `terraform init` after fixing                                                                                                  |
| A module change breaks `prod` but was never caught in `dev`                          | Module was edited without being applied and verified in `dev`/`staging` first                     | Enforce the promotion order from [§74](./Section-74-Part10-Environment-Promotion-Patterns-dev-staging-prod.md) — every module change must pass through `dev` and `staging` applies before touching `prod` |

## 9. Best Practices

- Prefer Pattern 2 (environment directories plus shared modules) for anything beyond a small, single-credential project — it's the layout that actually supports the credential/backend isolation argued for in [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md).
- Keep `modules/` free of environment-specific values entirely — every environment-specific value should flow in as a variable from the calling `environments/<env>/main.tf`, never hardcoded inside the module.
- Auto-load environment `.tfvars` via the `terraform.tfvars`/`*.auto.tfvars` naming convention inside each environment directory rather than relying on engineers to remember explicit `-var-file` flags.
- Keep a single `global/` (or equivalent) directory for genuinely account-wide, non-per-environment resources rather than arbitrarily assigning them to one environment's directory.

## 10. Common Anti-Patterns / Mistakes

- **Copy-pasting entire resource blocks into each environment directory instead of extracting a shared module.** This is the single most common layout mistake — it works initially, then rots as environments silently diverge.
- **Relying on `-var-file` flag discipline alone (Pattern 1) for environments that actually need credential isolation.** If the isolation requirement is real, the layout needs to change to Pattern 2, not just get better documentation.
- **Naming environment `.tfvars` files inconsistently across projects** (`prod.tfvars` in one repo, `production.tfvars` in another) — small inconsistency, but it compounds across a large organization's Terraform estate into real onboarding cost.

## 11. Interview Questions

**🎯 Beginner:** _"What are the two main file-layout patterns for a multi-environment Terraform project?"_
**Model answer:** One is a single directory with one shared configuration, using CLI workspaces plus per-environment `.tfvars` files (or `-var-file` flags) to vary values. The other is a separate directory per environment, each with its own backend and variables, calling shared modules for the actual resource logic.
_What the interviewer is probing for:_ Basic familiarity with both patterns and their correspondence to [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)'s workspace-vs-directory distinction.

**🎯 Intermediate:** _"In an environment-directories-plus-modules layout, what should never live inside the `modules/` directory, and why?"_
**Model answer:** A backend block, hardcoded environment-specific values, or a `terraform.tfvars` file. Modules should be stateless and reusable — no backend of their own, since they're never applied directly, only called from a root module (an environment directory). Any value that differs between dev and prod should be passed in as a variable from the calling environment directory, not hardcoded in the module.
_What the interviewer is probing for:_ Understanding of the module/root-module boundary and why keeping modules environment-agnostic is what makes the shared-module pattern actually reusable.

**🎯 Senior:** _"A team's Pattern 1 (single directory, workspaces, per-workspace .tfvars) layout has caused two incidents where the wrong .tfvars file was applied to the wrong workspace. What layout-level changes would you recommend, short of a full migration to directory-based separation?"_
**Model answer:** Before jumping to a full Pattern 2 migration, layout-level mitigations exist: wrap `apply` in a script or Makefile target (`make apply ENV=prod`) that derives both the workspace selection and the `-var-file` from a single input, eliminating the chance of mismatching them manually; add a pre-apply check (a small script or CI step) that asserts `terraform workspace show` matches the environment name embedded in the `.tfvars` filename before allowing `apply` to proceed; and require all applies to run through CI rather than locally, with the environment selected by pipeline parameter rather than free-form flags. If incidents continue despite these guardrails, that's a signal the underlying shared-backend/shared-credential model is the real problem, not just tooling discipline — at that point, migrating to Pattern 2 for at least the highest-risk environment (prod) is the appropriate next step, per [§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)'s guidance.
_What the interviewer is probing for:_ Pragmatic, incremental problem-solving rather than reaching immediately for the most drastic fix, while still recognizing when the underlying model (not just discipline) is genuinely the issue.

**🎯 Architect:** _"You're standardizing file layout conventions across 40 Terraform repositories in a large organization, currently a mix of all three patterns with inconsistent naming. What conventions would you mandate, and how would you enforce them?"_
**Model answer:** Mandate Pattern 2 (environment directories plus shared modules) as the default for any repository managing an environment with distinct security requirements, reserving Pattern 1 explicitly for genuinely low-risk, single-credential utility projects — documented as an exception, not a free choice. Standardize directory naming (`environments/<name>/`), variable file naming (`terraform.tfvars` per directory, auto-loaded), and require every environment directory to contain only a backend block, a `terraform.tfvars`, and a `main.tf` that exclusively calls modules — no inline resource blocks. Enforcement: a linting step in CI (using `tflint`, [§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md), or a custom script) that fails the pipeline if an `environments/<env>/main.tf` contains a `resource` block directly, or if `modules/` contains a `backend` block. Roll this out incrementally, starting with new repositories mandated to comply and existing repositories migrated during their next significant change, rather than a forced big-bang migration across all 40 at once — the migration cost (state moves, backend reconfiguration) is real and shouldn't be paid all at once organization-wide.
_What the interviewer is probing for:_ Organizational-scale thinking — standardization plus enforceable, automatable rules plus a realistic incremental rollout plan, not just picking "the right pattern" in the abstract.

## 12. Common Misconceptions

1. **"The file layout is the isolation mechanism."** It isn't — the layout packages whichever separation strategy ([§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)) was already chosen; a well-organized `environments/` tree with identical backend blocks in every subdirectory still provides no credential isolation.
2. **"Modules and environment directories are interchangeable terms."** They're distinct roles — modules are reusable, stateless, called-not-applied; environment directories are root modules that are actually applied and hold state.
3. **"Terragrunt (or similar wrappers) is required for multi-environment Terraform."** Native Terraform's Pattern 1 and Pattern 2 fully support multi-environment projects without any additional tooling; wrapper tools reduce boilerplate but are not a prerequisite.
4. **"Auto-loaded `.tfvars` filenames are a Terraform-wide standard everyone follows."** Only `terraform.tfvars` and `*.auto.tfvars` are auto-loaded by Terraform itself; any other naming convention (`prod.tfvars`) must be passed explicitly via `-var-file`.

## 13. 🔑 Key Takeaways

- Pattern 1 (single directory, workspaces, per-workspace `.tfvars`) mirrors workspace-based separation; Pattern 2 (environment directories, shared modules) mirrors directory-based separation.
- `modules/` should stay stateless, backend-free, and environment-agnostic — all environment-specific values flow in as variables from the calling root module.
- `terraform.tfvars` and `*.auto.tfvars` auto-load without a flag; any other filename needs an explicit `-var-file`.
- Layout choice doesn't create isolation by itself — it only enables the isolation that the underlying separation strategy ([§70](./Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)) is actually configured to provide.
- Wrapper-generated DRY layouts (Terragrunt-style) exist to reduce Pattern 2's boilerplate but sit outside native Terraform and this roadmap's scope.

## 14. Related Concepts & What's Next

[§72](./Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md) builds directly on Pattern 1's workspace-driven values by going deeper into `terraform.workspace` interpolation. [§74](./Section-74-Part10-Environment-Promotion-Patterns-dev-staging-prod.md) extends Pattern 2's environment-directory layout into a full dev-to-prod promotion pipeline. [§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)–[§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md) cover the module fundamentals this section assumes. [§40](../Part6/Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md) covers `.tfvars`/`-var-file` precedence in full.

**Next Section:** [§72](./Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md) — `Section-72-Part10-terraform.workspace-and-Interpolation-Patterns.md`
