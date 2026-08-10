# Section 16 (Part 3): Terraform File Structure and Conventions (main.tf, variables.tf, outputs.tf, versions.tf)

## 1. Definition

**Plain language:** Terraform doesn't actually require you to split configuration into separate files — it loads and merges _every_ `.tf` file in a directory as if it were one giant file. But the community has converged on a standard set of file names (`main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`) that group related blocks together, purely for human readability, and following that convention is what makes any Terraform project instantly navigable to anyone who already knows Terraform.

**Precise definition:** A **Terraform module** — including the root module of a project — is defined by the set of all `.tf` (and `.tf.json`) files in a single directory (non-recursively; subdirectories are separate modules, [§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)). Terraform's parser concatenates every file's top-level blocks into one logical configuration; file boundaries have zero effect on evaluation order, dependency resolution, or the resource graph ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)). File naming is therefore a **pure convention**, not a language rule, but it is such a strongly established convention that deviating from it without reason is treated as a code-quality issue in review, not a style preference.

> 💡 **Tip:** File names are for humans; the resource graph is for Terraform. You can put every block in one `main.tf` and it will work identically — but nobody, including future-you, will thank you for it once the file passes a few hundred lines.

## 2. Why This Matters

- Every Terraform module a team touches — internal or from the public Registry ([§59](../Part8/Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)) — follows this same file-naming convention, so learning it once means being able to navigate _any_ module's source in seconds instead of reading every file to find where variables are declared.
- `terraform fmt` and most linters (`tflint`, [§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)) assume this file layout implicitly in their default configuration and reporting, and generated documentation tools (`terraform-docs`) parse `variables.tf`/`outputs.tf` specifically by convention, not by scanning every file.
- Code review is faster and safer when reviewers know exactly where to look for a given kind of change (a new input goes in `variables.tf`, a new exposed value in `outputs.tf`) rather than hunting through an undifferentiated file.
- Getting this wrong at small scale (a single `main.tf` with everything) becomes a real refactor cost once a module or root configuration grows — establishing the convention early avoids a painful split-up later.

## 3. Prerequisites and Dependencies

Requires the block/argument grammar from [§15](./Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md). This section previews the `variable`, `output`, and `terraform` block types by _placement convention_ only — their full syntax and semantics are covered later: input variables in [§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md), output values in [§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md), and the `terraform`/`required_providers` block in [§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md). Module directory structure at large is covered in [§56](../Part8/Section-56-Part8-Module-Structure-and-Conventions.md).

## 4. Architecture / Conceptual Diagram

```text
my-terraform-project/
├── main.tf          # primary resource/data-source declarations — the "what gets built"
├── variables.tf      # input variable declarations — the module's configurable surface
├── outputs.tf         # output value declarations — what the module exposes to callers
├── versions.tf         # terraform{} block: core version + required_providers constraints
├── providers.tf         # (optional, larger projects) provider "aws" {} configuration blocks
├── locals.tf              # (optional) local value declarations, split out once numerous
├── terraform.tfvars        # (optional, often gitignored if sensitive) variable value assignments
└── .terraform/               # (generated, gitignored) provider plugins, module cache — never hand-edited
```

- **All files at the same directory level are merged into one configuration** — there is no `import` or `include` statement in HCL; splitting files is organizational, not functional.
- **`main.tf`** conventionally holds `resource` and `data` blocks — the actual infrastructure declarations — though in larger projects these are often further split by service or component (`network.tf`, `compute.tf`).
- **`variables.tf` / `outputs.tf`** are almost universally kept as their own files even in small projects, because they define a module's _interface_ — the parts a caller needs to read without reading implementation details.
- **`versions.tf`** isolates version-pinning concerns (`required_version`, `required_providers`) so they're trivially auditable in one place, separate from resource logic.

## 5. Hands-On

### 5.1 A Minimal, Conventionally Structured Root Module

**Purpose:** See the four canonical files working together as a single logical configuration.

**Syntax:**

```text
project/
├── main.tf
├── variables.tf
├── outputs.tf
└── versions.tf
```

**Example usage and expected output:**

```hcl
# versions.tf
terraform {
  required_version = ">= 1.7.0"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
```

```hcl
# variables.tf
variable "instance_type" {
  description = "EC2 instance type for the web server"
  type        = string
  default     = "t3.micro"
}
```

```hcl
# main.tf
resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = var.instance_type
}
```

```hcl
# outputs.tf
output "instance_id" {
  description = "ID of the created EC2 instance"
  value       = aws_instance.web.id
}
```

```bash
$ terraform init && terraform plan
Terraform will perform the following actions:
  # aws_instance.web will be created
  + resource "aws_instance" "web" {
      + ami           = "ami-0c55b159cbfafe1f0"
      + instance_type = "t3.micro"
      ...
    }
Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Even though these four files could be concatenated into one `main.tf` with identical plan output, real teams split them this way specifically so a reviewer approving a change to an input's default value only needs to open `variables.tf`, not scroll through resource logic to find it.

**Common errors:** Declaring a `variable` block inside `main.tf` instead of `variables.tf` produces no error at all — Terraform doesn't care — but it fails silently against the _convention_, and a linter or reviewer following the standard layout will flag it as a readability defect, not a functional one.

### 5.2 Splitting `main.tf` as a Project Grows

**Purpose:** Understand when and how to break the single `main.tf` convention down further as resource count grows.

**Syntax:**

```text
project/
├── network.tf     # VPC, subnets, route tables
├── compute.tf      # EC2 instances, autoscaling groups
├── security.tf       # security groups, IAM roles
├── variables.tf
├── outputs.tf
└── versions.tf
```

**Example usage and expected output:**

```bash
$ terraform plan
# identical plan output regardless of whether resources live in main.tf
# or are split across network.tf / compute.tf / security.tf —
# Terraform builds one merged configuration either way.
```

**Production usage example:** Once a root module exceeds roughly 150–300 lines in a single file, teams commonly split `main.tf` by logical component (network, compute, security) to keep diffs in pull requests small and reviewable — a PR that only touches security groups should only show changes in `security.tf`, not an unrelated diff noise across an undifferentiated `main.tf`.

**Common errors:** Splitting files by _resource type_ instead of by _logical component_ (e.g., one file per Terraform resource type) tends to scale poorly — it optimizes for "where is this resource type" at the cost of "what depends on what," which matters more for reviewability.

### 5.3 `providers.tf` and `locals.tf` as Optional Extensions

**Purpose:** Know when to introduce further conventional files beyond the core four.

**Syntax:**

```hcl
# providers.tf
provider "aws" {
  region = var.aws_region
}

provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}
```

**Example usage and expected output:**

```bash
$ terraform validate
Success! The configuration is valid.
```

**Production usage example:** Provider _configuration_ blocks (as opposed to the `required_providers` version constraint in `versions.tf`) are commonly split into their own `providers.tf` once a project uses [provider aliases](../Part2/Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md) ([§13](../Part2/Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md)) for multi-region or multi-account setups, so the full list of configured provider instances is visible in one place.

**Common errors:** Confusing `versions.tf`'s `required_providers` block (a version _constraint_, resolved at `terraform init`) with `providers.tf`'s `provider` block (runtime _configuration_, like region and credentials) is a common early mix-up — both mention the same provider name but serve entirely different purposes.

## 6. Production Usage Notes

- File structure conventions are enforced by team discipline and code review, not by the Terraform binary — `terraform fmt` normalizes formatting _within_ a file but has no opinion on which file a block lives in.
- `terraform-docs`, a widely used third-party tool, generates a module's README table of inputs/outputs by parsing `variable`/`output` blocks wherever they are — but its examples and most real-world usage assume the standard `variables.tf`/`outputs.tf` split, and deviating makes generated docs harder for contributors to cross-reference against source.
- Root modules (the top-level configuration `terraform apply` is run against) and child modules ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)) both follow this same file convention — there is no structural difference between them beyond how they're invoked.

## 7. Security Considerations

- `terraform.tfvars` files frequently contain environment-specific values; if any of them contain secrets, they must be excluded from version control via `.gitignore` — committing a `.tfvars` file with a literal credential is one of the most common real-world secret-leak vectors in Terraform projects.
- The generated `.terraform/` directory (provider plugin binaries, module cache) should always be gitignored — besides being disposable and regenerable via `terraform init`, committing it can accidentally commit large binaries or stale provider versions into history.
- `versions.tf`'s provider version constraints are a security control, not just a compatibility one: pinning to a known-good provider version range prevents an automatic upgrade to a compromised or buggy provider release from silently reaching production.

## 8. Common Troubleshooting Scenarios

| Symptom                                                   | Likely Cause                                                                     | Resolution Path                                                                                         |
| --------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| "Duplicate variable declaration" error                    | Same variable name declared in two different `.tf` files in the same directory   | Search the whole directory (not just `variables.tf`) for the duplicate `variable` block                 |
| A block seems "missing" when reading a module             | Terraform merges all files; the block may simply live in an unexpected file      | Search across all `.tf` files in the directory, not just the conventionally-named one                   |
| Generated docs (`terraform-docs`) missing an input/output | The `variable`/`output` block was declared outside the conventional file         | Not a functional bug — move the block to `variables.tf`/`outputs.tf` to align with tooling expectations |
| Secrets found in Git history via a `.tfvars` file         | `.tfvars` file with real credentials was committed before `.gitignore` was added | Rotate the leaked credential immediately; add `.gitignore` entry; scrub history if required             |

## 9. Best Practices

- Default to the four-file convention (`main.tf`, `variables.tf`, `outputs.tf`, `versions.tf`) for every new project or module, even a small one — consistency across a team's repositories matters more than optimizing any single small project's layout.
- Split `main.tf` by logical component, not by resource type, once it grows past a few hundred lines.
- Always gitignore `.terraform/` and any `.tfvars` file that may contain environment-specific secrets; commit a `.tfvars.example` template instead so the expected variable shape is still documented in version control.
- Keep `versions.tf` minimal and dedicated purely to version constraints — resist the temptation to add unrelated blocks to it just because it's a small, easy-to-find file.

## 10. Common Anti-Patterns / Mistakes

- **One giant `main.tf` with everything** (resources, variables, outputs, provider config) — technically valid, but actively hostile to code review and onboarding once a project has more than a handful of resources.
- **Splitting so aggressively that navigating requires opening ten files to understand one resource's full context** — the opposite failure mode; component-based splitting should aid navigation, not fragment it.
- **Committing `.tfvars` files with real secrets** because "it's just a config file, not code" — from Terraform's parser's perspective and from Git's perspective, it's exactly as committed and exactly as permanent as any other file.
- **Relying on file name alone to guess a block's meaning without opening it** — file names are a convention for organization, not a substitute for reading `description` fields and actual arguments.

## 11. Interview Questions

**🎯 Beginner:** _"Does Terraform require configuration to be split into `main.tf`, `variables.tf`, and `outputs.tf`?"_
**Model answer:** No — Terraform loads and merges every `.tf` file in a directory as one logical configuration regardless of file name. The four-file convention is a community and tooling convention for human readability, not a language requirement.
_What the interviewer is probing for:_ Whether the candidate understands the distinction between language requirements and team/tooling convention — a distinction that comes up constantly in code review discussions.

**🎯 Intermediate:** _"Two files, `network.tf` and `compute.tf`, both live in the same module directory and one resource in `compute.tf` references a subnet ID from a resource in `network.tf`. Does file order or naming affect whether this works?"_
**Model answer:** No. Terraform builds a single resource dependency graph ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) from all blocks in the directory, regardless of which file they're declared in or the order files are processed — the reference itself (`aws_subnet.main.id`) is what establishes the dependency, not file placement. File organization is purely cosmetic to the evaluation engine.
_What the interviewer is probing for:_ Confirming the candidate hasn't confused file-based organization with the actual dependency-resolution mechanism, which is graph-based and reference-driven ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)).

**🎯 Senior:** _"Your team's module has grown to 40 resources in a single `main.tf`. What's your process for splitting it, and what risks do you need to manage during the split?"_
**Model answer:** Split by logical component (e.g., networking, compute, security) rather than by resource type, since that aligns file boundaries with how changes and reviews actually happen. The critical risk during the split is state: moving a `resource` block to a different file has zero effect on its state address (state addresses are `<type>.<name>`, not file-qualified), so a pure file reorganization with no name/type changes requires no `terraform state mv` and no plan diff — but it's worth running `terraform plan` immediately after the split to confirm zero planned changes, since any unintended renaming during the refactor would otherwise show as a destroy/create in the plan.
_What the interviewer is probing for:_ Real operational awareness that file reorganization is state-safe only if resource addresses are untouched — a distinction that matters a lot once state is involved ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)).

**🎯 Architect:** _"You're setting engineering standards for how every Terraform repository in your organization should be laid out. What do you standardize on, and what do you deliberately leave flexible?"_
**Model answer:** Standardize the things that affect cross-repo navigability and tooling: the four-core-file convention at the root of every module, consistent `versions.tf` provider pinning strategy, mandatory `.gitignore` entries for `.terraform/` and sensitive `.tfvars`, and a documented policy for when `main.tf` should be split by component. Leave flexible: how aggressively a specific module splits `main.tf` into sub-files (a 20-resource module and a 200-resource module have legitimately different needs), and naming beyond the core four files, since forcing an identical file tree onto every module regardless of size produces its own readability problems. The goal is a standard that removes "where do I look" friction across dozens of repositories without micromanaging every module's internal organization.
_What the interviewer is probing for:_ Judgment about which conventions genuinely need organization-wide enforcement versus which are better left as team-level or module-level decisions — over-standardizing has real costs too.

## 12. Common Misconceptions

1. **"Terraform reads files in a specific order that matters."** It doesn't — all `.tf` files in a directory are merged into one configuration and evaluated according to the dependency graph, not file order or alphabetical order.
2. **"variables.tf and outputs.tf are required file names."** They're conventions; a variable block works identically no matter which `.tf` file it's declared in.
3. **"Splitting files affects performance."** It doesn't meaningfully — parsing and graph construction operate on the merged configuration regardless of how many files it came from.
4. **"Moving a resource to a different file requires a state operation."** It doesn't, as long as the resource's type and local name are unchanged — only renaming or moving a resource's _address_ (type/name) requires `terraform state mv` ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)).

## 13. 🔑 Key Takeaways

- Terraform merges every `.tf` file in a directory into one logical configuration; file names and boundaries have zero effect on parsing, dependency resolution, or the resource graph.
- The `main.tf` / `variables.tf` / `outputs.tf` / `versions.tf` convention exists purely for human and tooling readability, and following it is close to universal in real-world Terraform code.
- Split `main.tf` by logical component once it grows large, not by resource type.
- `.terraform/` and any secret-bearing `.tfvars` file must be gitignored — file-structure hygiene is also a security control, not just an organizational one.
- Reorganizing files (without renaming resource addresses) is always state-safe; renaming a resource's type/local name is not, and requires `terraform state mv`.

## 14. Related Concepts & What's Next

[§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) and [§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md) give the full syntax and semantics of the `variable` and `output` blocks only previewed here by placement. [§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md) covers the `terraform`/`required_providers` block's version-constraint syntax in depth. [§56](../Part8/Section-56-Part8-Module-Structure-and-Conventions.md) extends this same file-layout convention to child modules specifically, including the standard `examples/` and `README.md` structure expected of publishable modules. [§106](../Part15/Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md) scales this discussion up to whole-repository structure across many modules.

**Next Section:** [§17](./Section-17-Part3-Data-Types-Primitives-Collections-list-map-set-Structural-object-tuple.md) — `Section-17-Part3-Data-Types-Primitives-Collections-list-map-set-Structural-object-tuple.md`
