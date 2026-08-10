# Section 56 (Part 8): Module Structure and Conventions

## 1. Definition

**Plain language:** Terraform doesn't technically require any particular file layout inside a module — you could put every resource, variable, and output in one giant `everything.tf`. But the community and HashiCorp's own tooling (the registry, `terraform-docs`, module linters) have converged on a standard layout, and following it is what makes a module predictable to anyone who opens it for the first time.

**Precise definition:** The **standard module structure** is a set of conventional filenames and a directory layout that Terraform itself does not enforce (Terraform reads and merges every `.tf` file in a directory identically, regardless of name) but that the Terraform Registry ([§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)), `terraform-docs`, and virtually every published module follow: `main.tf` (primary resource definitions), `variables.tf` (input variable declarations, [§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)), `outputs.tf` (output value declarations, [§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)), `versions.tf` (`required_version` and `required_providers` constraints), `README.md` (usage documentation, often auto-generated), and an optional `examples/` directory containing one or more minimal root modules that demonstrate calling this module. Larger modules may add `locals.tf`, `data.tf`, or split `main.tf` into topic-named files (`network.tf`, `iam.tf`) — file names are cosmetic to Terraform, which simply concatenates all `.tf` files in a directory into one logical configuration.

> 💡 **Tip:** Because Terraform merges all `.tf` files in a directory before evaluating anything, you can never "forget to import" a file the way you might in a general-purpose programming language — every `.tf` file in the module's root directory (not subdirectories) is automatically part of the module. Subdirectories are never implicitly included; a subdirectory is only pulled in if something explicitly calls it as a nested child module ([§61](./Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md)).

## 2. Why This Matters

- **Predictability across a large module ecosystem.** When every module — whether written in-house or pulled from the public registry — puts inputs in `variables.tf` and outputs in `outputs.tf`, any engineer can open an unfamiliar module and immediately know where to look, without reading every line of `main.tf`.
- **Tooling depends on it.** `terraform-docs` generates README tables from `variables.tf`/`outputs.tf` structure; the Terraform Registry's auto-generated documentation pages ([§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)) parse the same conventional files; IDE extensions and linters (`tflint`, [§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)) assume this layout for navigation and autocomplete.
- **`versions.tf` isolation prevents version-constraint sprawl.** Keeping `required_providers`/`required_version` in one dedicated file makes it trivial to audit and bump version constraints across dozens of modules without hunting through `main.tf`.
- **`examples/` doubles as living documentation and a manual test harness.** A directory of runnable example root modules is both the fastest way for a new consumer to understand a module and (combined with `terraform test`, [§100](../Part14/Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)) a way to validate the module actually still works as changes are made.
- Getting this right up front avoids the much more painful retrofit of reorganizing a module's files after a dozen teams already depend on it and have their own tooling assumptions about its layout.

## 3. Prerequisites and Dependencies

This section builds directly on [§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)'s root/child module distinction and assumes familiarity with the general Terraform file structure conventions already introduced for root modules in [§16](../Part3/Section-16-Part3-Terraform-File-Structure-and-Conventions.md) (`main.tf`/`variables.tf`/`outputs.tf`/`versions.tf`) — the module conventions here are the same convention applied consistently to child modules as well, so [§16](../Part3/Section-16-Part3-Terraform-File-Structure-and-Conventions.md) is worth a quick review if the root-module version of this pattern is unfamiliar. [§57](./Section-57-Part8-Module-Inputs-and-Outputs.md) (immediately following) goes deeper into what actually belongs inside `variables.tf` and `outputs.tf`.

## 4. Architecture / Conceptual Diagram

```text
modules/network/                    <- module source directory
├── main.tf                <- primary resource definitions
├── variables.tf            <- input variable declarations (§57)
├── outputs.tf               <- output value declarations (§57)
├── versions.tf                <- required_version, required_providers
├── locals.tf                    <- (optional) computed local values
├── README.md                      <- usage docs (often terraform-docs generated)
└── examples/
    ├── basic/
    │   ├── main.tf         <- minimal root module calling ../../
    │   └── README.md
    └── complete/
        ├── main.tf         <- fuller example, more inputs exercised
        └── README.md

Terraform's actual parsing behavior:
  ┌─────────────────────────────────────────────┐
  │ All *.tf files directly in modules/network/ │
  │ are merged into ONE logical configuration.  │
  │ File names are a human/tooling convention   │
  │ only — Terraform itself does not care       │
  │ whether a resource lives in main.tf or      │
  │ some-other-name.tf.                         │
  └─────────────────────────────────────────────┘
  Subdirectories (examples/, tests/) are NEVER
  auto-included — they're only pulled in if
  something explicitly sources them.
```

- The `examples/` subdirectories are themselves complete root modules (each has its own `source = "../../"` call back to the parent module) — they are not automatically part of the `modules/network` module itself, which is exactly why they can safely contain a full `terraform { required_providers }` and provider configuration without polluting the reusable module's own provider-agnosticism ([§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)).
- Larger modules commonly split `main.tf` by topic (`network.tf`, `security_groups.tf`, `iam.tf`) once a single file grows unwieldy — this is purely organizational since Terraform concatenates them regardless.

## 5. Hands-On

### 5.1 Minimal Standard Module Layout

**Purpose:** Show the smallest reasonable standard-structured module.

**Syntax:**

```hcl
# modules/s3-bucket/versions.tf
terraform {
  required_version = ">= 1.5.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
```

```hcl
# modules/s3-bucket/variables.tf
variable "bucket_name" {
  description = "Name of the S3 bucket to create."
  type        = string
}

variable "versioning_enabled" {
  description = "Whether to enable S3 bucket versioning."
  type        = bool
  default     = false
}
```

```hcl
# modules/s3-bucket/main.tf
resource "aws_s3_bucket" "this" {
  bucket = var.bucket_name
}

resource "aws_s3_bucket_versioning" "this" {
  bucket = aws_s3_bucket.this.id
  versioning_configuration {
    status = var.versioning_enabled ? "Enabled" : "Suspended"
  }
}
```

```hcl
# modules/s3-bucket/outputs.tf
output "bucket_arn" {
  description = "ARN of the created S3 bucket."
  value       = aws_s3_bucket.this.arn
}
```

**Example usage and expected output:**

```bash
$ ls modules/s3-bucket/
main.tf  outputs.tf  variables.tf  versions.tf

$ terraform -chdir=modules/s3-bucket validate
Success! The configuration is valid.
```

**Production usage example:** This four-file layout (`main.tf`/`variables.tf`/`outputs.tf`/`versions.tf`) is the practical minimum for any module intended to be reused more than once — even an internal-only module benefits from the predictability, since the next engineer to touch it (possibly a future version of the same author) shouldn't have to re-derive the module's interface by reading every resource block.

**Common errors:** Declaring `required_providers` inside `main.tf` instead of a dedicated `versions.tf` works functionally (Terraform doesn't care) but breaks the convention that tooling and reviewers expect — during code review this is the kind of thing that gets flagged as "please move to versions.tf for consistency."

### 5.2 Adding an `examples/` Directory

**Purpose:** Demonstrate the self-referencing example pattern that doubles as documentation and manual verification.

**Syntax:**

```hcl
# modules/s3-bucket/examples/basic/main.tf
terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region = "us-east-1"
}

module "example_bucket" {
  source = "../../"

  bucket_name         = "my-example-bucket-12345"
  versioning_enabled  = true
}

output "bucket_arn" {
  value = module.example_bucket.bucket_arn
}
```

**Example usage and expected output:**

```bash
$ cd modules/s3-bucket/examples/basic
$ terraform init
$ terraform plan
Plan: 2 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Public registry modules ([§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)) are expected to ship at least one `examples/` directory — the registry's documentation UI renders these directly, and many teams' internal module review checklists require at least a `basic/` example before a module is approved for shared use.

**Common errors:** Forgetting that `examples/basic` needs its own `provider` and `required_providers` blocks (since it is itself a root module) is a common first mistake — the parent module deliberately omits provider configuration ([§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)) so the example must supply it.

## 6. Production Usage Notes

- **`terraform-docs` automates the README.** Rather than hand-maintaining a table of every variable's name, type, description, and default, most teams run `terraform-docs markdown . > README.md` (often as a pre-commit hook, [§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)) to keep documentation mechanically in sync with `variables.tf`/`outputs.tf` — hand-written module READMEs drift out of date almost immediately otherwise.
- **File-splitting by resource type scales better than by lifecycle stage.** For larger modules, splitting `main.tf` into `network.tf`, `compute.tf`, `iam.tf` (by what the resources represent) tends to age better than splitting by something like `create.tf`/`update.tf`, since Terraform's declarative model doesn't actually have separate create/update phases in configuration the way that split implies.
- **`locals.tf` is worth its own file once a module computes more than a couple of derived values** — mixing local value computation into `main.tf` alongside resource blocks makes it harder to scan a module for "what does this module actually create" versus "what is this module computing internally."

## 7. Security Considerations

- Module `README.md` files (especially `examples/`) frequently accumulate real-looking example values (account IDs, ARNs, bucket names) — reviewers should confirm these are clearly fake/placeholder rather than accidentally leaked real infrastructure identifiers.
- Because `versions.tf` pins provider version constraints, an out-of-date or overly loose constraint (`version = ">= 4.0"` with no upper bound) can silently pull in a newer provider version with different default behaviors or newly-required permissions at the next `terraform init` — see [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md) for the version-constraint operators that mitigate this.
- `examples/` directories that include real provider credentials or `.tfvars` files with populated secrets (rather than placeholders) risk those secrets being committed to a public registry module's Git repository ([§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)) — `.gitignore` discipline for `*.tfvars` applies here exactly as it does for root-module projects ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)).

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Likely Cause                                                                                     | Resolution Path                                                                                                                                                              |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A resource seems to be "missing" when reading only `main.tf`         | The module's files were split by topic (`network.tf`, `iam.tf`) and the resource lives elsewhere | Search the whole module directory, not just `main.tf` — Terraform merges all `.tf` files equally                                                                             |
| `terraform init` in an `examples/` folder fails to find the module   | The example's relative `source = "../../"` path is wrong for its actual nesting depth            | Verify the relative path matches the example's actual directory depth relative to the module root                                                                            |
| README documentation for variables is out of date                    | `variables.tf` was changed but `terraform-docs` was not re-run                                   | Add a `terraform-docs` pre-commit hook ([§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)) so the README regenerates automatically on every commit |
| New team member can't tell which variables are required vs. optional | Module lacks consistent `description`/`default` conventions, or a generated README table         | Standardize on `terraform-docs` output as the source of truth for the interface, not ad hoc comments                                                                         |

## 9. Best Practices

- Always include at minimum `main.tf`, `variables.tf`, `outputs.tf`, and `versions.tf`, even for small modules — the marginal cost is nearly zero and the consistency benefit compounds across an organization's module inventory.
- Generate (don't hand-write) `README.md` variable/output tables with `terraform-docs`, so documentation cannot silently drift from the actual interface.
- Ship at least one runnable example under `examples/` for any module with more than a couple of consumers — it is the fastest onboarding path and doubles as a smoke test.

## 10. Common Anti-Patterns / Mistakes

- **One giant `main.tf` with hundreds of lines mixing variables, resources, and outputs.** Nothing breaks technically, but every reviewer and downstream tool now has to parse the whole file to find what they need — the split convention exists precisely to avoid this.
- **Inconsistent naming across a module inventory** (`vars.tf` in one module, `variables.tf` in another; `output.tf` singular vs. `outputs.tf` plural) — small inconsistencies like this add friction every single time an engineer switches between modules.
- **Treating `examples/` as throwaway scratch space that goes stale.** An example that no longer applies cleanly against the current module version actively misleads new consumers and should be treated as a first-class artifact validated in CI, not an afterthought.

## 11. Interview Questions

**🎯 Beginner:** _"Does Terraform require a module's files to be named `main.tf`, `variables.tf`, and `outputs.tf`?"_
**Model answer:** No — Terraform reads and merges every `.tf` file in a directory identically regardless of its name; there's no functional difference between putting a resource block in `main.tf` versus a file called `whatever.tf`. Those names are a strong community and tooling convention, not a language requirement.
_What the interviewer is probing for:_ Whether the candidate can distinguish "convention that tooling expects" from "language-enforced rule" — a common point of confusion for newcomers.

**🎯 Intermediate:** _"What's the purpose of an `examples/` directory inside a module, and why does it need its own `provider` block when the module itself typically shouldn't have one?"_
**Model answer:** `examples/` directories are themselves complete, runnable root modules that call the parent module via a relative source path (typically `../../`), demonstrating realistic usage and doubling as documentation and a manual (or CI-driven) smoke test. They need their own `provider`/`required_providers` configuration because they are root modules in their own right — the parent module intentionally omits provider configuration so it stays reusable across accounts and regions ([§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)), so each example must supply the specific configuration it will actually run against.
_What the interviewer is probing for:_ Understanding that `examples/` are genuine root modules, not a special Terraform construct, tying back to the root/child module concept from [§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md).

**🎯 Senior:** _"Your team's `versions.tf` convention has drifted — some modules pin providers in `main.tf`, some in `versions.tf`, and a few have no version constraints at all. What's the actual risk, and how would you remediate at scale?"_
**Model answer:** The functional risk isn't file placement (Terraform doesn't care) — it's the missing or loose version constraints themselves: modules without `required_providers` version constraints can resolve to a newer provider version at the next `terraform init` with different resource schemas, default behaviors, or required permissions, causing unexpected plan diffs or apply failures across every consumer simultaneously. Remediation at scale means (1) auditing every module for a consistent, appropriately-bounded constraint (typically `~>` pessimistic constraints, [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) in a dedicated `versions.tf`, (2) enforcing this via a linter (`tflint`, [§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)) in CI rather than manual review, and (3) rolling out the fix incrementally with a deprecation window since tightening constraints on a widely-consumed module can itself break consumers relying on the previously-loose range.
_What the interviewer is probing for:_ Ability to separate cosmetic convention drift from the real underlying risk (unconstrained provider versions), and a practical, incremental remediation plan rather than "just fix it."

**🎯 Architect:** _"You're setting module authoring standards for an organization with 200+ internal modules written over several years with inconsistent structure. What's your practical enforcement strategy, and what do you deliberately not standardize?"_
**Model answer:** Enforce the file-layout convention (`main.tf`/`variables.tf`/`outputs.tf`/`versions.tf`, generated `README.md`, `examples/`) via automated linting and a module-scaffolding template/generator, not manual review — humans will not consistently catch structural drift across 200 modules, but a CI check absolutely can. I'd deliberately not standardize internal file-splitting beyond the four required files (whether `main.tf` stays monolithic or splits into `network.tf`/`iam.tf` is a module-author judgment call based on size, and mandating a specific split scheme adds bureaucracy without real benefit). I would also not force a big-bang migration of all 200 existing modules — instead require the new standard for any module touched going forward (new modules and any PR that modifies an existing one), letting the inventory converge organically, since a mass rewrite of working, versioned modules carries real regression risk for comparatively little benefit over incremental convergence.
_What the interviewer is probing for:_ Pragmatic standards-setting at scale — knowing what to automate versus enforce via review, and knowing when NOT to mandate a big migration for cosmetic consistency.

## 12. Common Misconceptions

1. **"`main.tf`/`variables.tf`/`outputs.tf` are Terraform keywords or special files."** They're plain file names; Terraform merges every `.tf` file in a directory identically. The names are convention only.
2. **"An `examples/` subdirectory is automatically included as part of the module."** It is not — subdirectories are never auto-included; `examples/` only works because each example explicitly sources the parent module itself (`../../`).
3. **"A well-structured module doesn't need a README because `variables.tf`/`outputs.tf` are self-documenting."** Type signatures alone don't convey intent, valid ranges, or usage guidance — a generated README (via `terraform-docs`) still adds real value even when variable/output declarations have good `description` fields.
4. **"Splitting a module's files differently than another module in the same repo is harmless."** It's harmless to Terraform's execution, but it measurably increases cognitive load for anyone working across multiple modules — consistency itself has value independent of any single module's internal correctness.

## 13. 🔑 Key Takeaways

- The standard module layout (`main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`, `README.md`, `examples/`) is a convention followed by the ecosystem and its tooling, not a Terraform language requirement.
- Terraform merges every `.tf` file directly inside a module's directory into one logical configuration regardless of file name; subdirectories are never implicitly included.
- `examples/` directories are themselves complete, independent root modules that reference the parent module via a relative `source` path, and therefore need their own provider configuration.
- `terraform-docs` is the standard way to keep a module's README interface documentation mechanically synchronized with its actual `variables.tf`/`outputs.tf`.
- Consistency of structure across an organization's module inventory has real value beyond any single module's correctness — it reduces the cognitive cost of moving between modules.

## 14. Related Concepts & What's Next

[§57](./Section-57-Part8-Module-Inputs-and-Outputs.md) goes deeper into exactly what belongs inside `variables.tf` and `outputs.tf` — the interface this section's file layout organizes. [§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md) covers how the standard structure interacts with the public Terraform Registry's auto-generated documentation. [§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md) covers wiring `terraform-docs` and `tflint` into CI as pre-commit hooks so this structure is enforced automatically rather than by manual review.

**Next Section:** [§57](./Section-57-Part8-Module-Inputs-and-Outputs.md) — `Section-57-Part8-Module-Inputs-and-Outputs.md`
