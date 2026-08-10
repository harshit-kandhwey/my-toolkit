# Section 57 (Part 8): Module Inputs and Outputs

## 1. Definition

**Plain language:** Inputs and outputs are how a module talks to the outside world. Inputs (`variable` blocks) are the knobs a caller sets when it uses the module; outputs (`output` blocks) are the values the module hands back once it's done, so the caller can wire them into other resources or other modules. Together, they're the entire public interface of a module — everything else inside it is private implementation detail the caller never sees.

**Precise definition:** A child module's **input variables** are `variable` blocks declared inside the module, populated by the calling `module` block's arguments (every argument in a `module "name" { ... }` block other than `source`, `version`, `providers`, `count`, `for_each`, and `depends_on` must correspond to a declared `variable` in that module). A child module's **output values** are `output` blocks declared inside the module, referenced from the caller as `module.<name>.<output_name>`. Variables and outputs are mechanically identical to root-module variables and outputs ([§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md), [§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md)) in syntax — `type`, `default`, `description`, `sensitive`, `validation` all apply the same way — the difference is purely structural: at the module boundary, these blocks form the contract between caller and module, whereas at the root they interface with the CLI/`.tfvars`/environment ([§40](../Part6/Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)).

> 💡 **Tip:** A variable with no `default` is a **required** input — the caller's `module` block must supply it or `terraform plan` fails immediately with a clear "Missing required argument" error. A variable with a `default` is optional for the caller to override. Deciding what's required versus defaulted is the single biggest design decision in a module's interface: too many required inputs makes the module tedious to call; too many silent defaults makes its behavior opaque to a caller who didn't read the source.

## 2. Why This Matters

- **Inputs and outputs are the entire encapsulation boundary from [§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md).** A caller cannot reach into a module's internal resources directly (`module.network.aws_vpc.this.id` is invalid) — only what's explicitly exposed as an output is visible, which is what makes modules safely refactorable internally without breaking callers, as long as the interface stays stable.
- **Type constraints on inputs catch caller mistakes early.** A `variable "subnet_count" { type = number }` rejects a string at `terraform plan` time with a specific error, rather than the module's internal resource logic failing confusingly deep inside `main.tf`.
- **Outputs are how modules compose.** [§61](./Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md)'s composition patterns are only possible because one module's outputs can feed directly into another module's inputs (`module.network.vpc_id` passed as `vpc_id = module.network.vpc_id` into a second module) — without outputs, modules would be dead-ends that can't participate in a larger configuration.
- **`sensitive = true` on module outputs prevents accidental secret exposure in plan/apply output**, the same protection root-module sensitive outputs ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) provide, but specifically relevant here because modules often generate secrets internally (e.g., a randomly generated database password) that must not leak into CI logs.
- Getting the input/output surface right is the practical difference between a module other teams actually adopt and one everyone works around because it's too rigid or too opaque.

## 3. Prerequisites and Dependencies

This section assumes the input variable mechanics from [§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) (declaration, types, defaults) and output value mechanics from [§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md) (declaration, dependencies, consumption) at the root-module level — everything here is the same mechanism applied at a module boundary rather than at the CLI/root boundary. [§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)'s coverage of `sensitive` variables and outputs applies identically inside modules and is directly relevant to this section's security considerations. [§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)'s variable validation rules are especially valuable at module boundaries, since a module's inputs are its main defense against being called incorrectly.

## 4. Architecture / Conceptual Diagram

```text
CALLER (root module or another module)
┌───────────────────────────────────────────────────────┐
│ module "database" {                                   │
│   source          = "./modules/database"              │
│   instance_class   = "db.t3.medium"   ───────┐        │
│   allocated_storage = 100             ───────┼──┐     │
│ }                                            │  │     │
│                                              │  │     │
│ resource "aws_security_group_rule" "db" {    │  │     │
│   ...                                        │  │     │
│   security_group_id = module.database.sg_id ◄─────────┼── OUTPUT flows back
│ }                                                     │
└──────────────────────────────────────────────┼────────┘
                                               │  │
                    module boundary ───────────┼──┼───────────
                                               ▼  ▼
CHILD MODULE (modules/database/)
┌───────────────────────────────────────────────────────────────────┐
│ variable "instance_class" { type = string }             ◄── INPUT (required)
│ variable "allocated_storage" { type = number }          ◄── INPUT (required)
│ variable "multi_az" {                                             │
│   type    = bool                                                  │
│   default = false                                       ◄── INPUT (optional, defaulted)
│ }                                                                 │
│                                                                   │
│ resource "aws_db_instance" "this" { ... }                         │
│ resource "aws_security_group" "db" { ... }                        │
│                                                                   │
│ output "sg_id" {                                                  │
│   value = aws_security_group.db.id                      ◄── OUTPUT (public)
│ }                                                                 │
│ output "db_password" {                                            │
│   value     = random_password.this.result                         │
│   sensitive = true                                      ◄── OUTPUT (sensitive)
│ }                                                                 │
│ # aws_db_instance.this, random_password.this internals:           │
│ # NOT visible outside this module — only declared outputs are     │
└───────────────────────────────────────────────────────────────────┘
```

- Every argument in a `module` block that isn't one of Terraform's reserved meta-arguments (`source`, `version`, `providers`, `count`, `for_each`, `depends_on`) must match a declared `variable` name inside the module — passing an argument the module hasn't declared is a validation error, and omitting a required (no-default) variable is also a validation error.
- Outputs are the only channel back out — internal resource attributes not surfaced as outputs are simply invisible to the caller, by design.

## 5. Hands-On

### 5.1 Declaring Module Inputs with Types, Defaults, and Validation

**Purpose:** Show a realistic input interface mixing required, optional, and validated variables.

**Syntax:**

```hcl
# modules/database/variables.tf
variable "instance_class" {
  description = "RDS instance class, e.g. db.t3.medium."
  type        = string
}

variable "allocated_storage" {
  description = "Allocated storage in GB."
  type        = number

  validation {
    condition     = var.allocated_storage >= 20
    error_message = "allocated_storage must be at least 20 GB."
  }
}

variable "multi_az" {
  description = "Whether to deploy a Multi-AZ standby replica."
  type        = bool
  default     = false
}
```

**Example usage and expected output:**

```bash
$ terraform plan
# Caller omitted instance_class entirely:
Error: Missing required argument

  on main.tf line 12, in module "database":
  12: module "database" {

The argument "instance_class" is required, but no definition was found.
```

**Production usage example:** Required variables (no `default`) are appropriate for inputs where there is no sensible organization-wide default (an instance class genuinely varies per environment); optional variables with defaults are appropriate for inputs most callers want left alone (`multi_az = false` for dev, only overridden explicitly for production).

**Common errors:** Passing a string like `"100"` for `allocated_storage` (declared as `type = number`) triggers a type-conversion error at plan time if it can't be coerced — Terraform will attempt automatic type conversion where unambiguous, but relying on that instead of matching the declared type is a common source of confusing plan-time errors.

### 5.2 Declaring and Consuming Module Outputs

**Purpose:** Show output declaration including a sensitive output, and consumption from the caller.

**Syntax:**

```hcl
# modules/database/outputs.tf
output "sg_id" {
  description = "Security group ID attached to the database."
  value       = aws_security_group.db.id
}

output "db_password" {
  description = "Generated database master password."
  value       = random_password.this.result
  sensitive   = true
}
```

```hcl
# root module main.tf
module "database" {
  source            = "./modules/database"
  instance_class    = "db.t3.medium"
  allocated_storage = 100
}

resource "aws_security_group_rule" "app_to_db" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = module.database.sg_id
  source_security_group_id = aws_security_group.app.id
}
```

**Example usage and expected output:**

```bash
$ terraform apply
Terraform will perform the following actions:
  # module.database.aws_db_instance.this will be created
  # module.database.aws_security_group.db will be created
  # aws_security_group_rule.app_to_db will be created

Apply complete! Resources: 3 added, 0 changed, 0 destroyed.

Outputs:
db_password = <sensitive>
```

**Production usage example:** Consuming one module's output as another resource's (or another module's) input argument is the standard way configuration is wired together across module boundaries in any non-trivial Terraform codebase — this is exactly the mechanism [§61](./Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md)'s composition patterns build on.

**Common errors:** Forgetting `sensitive = true` on an output that surfaces a secret (like `db_password` above) means that value prints in plain text in `terraform plan`/`apply` output and CI logs — a common and serious mistake; [§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md) and [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) cover the deeper implications for state file exposure as well.

## 6. Production Usage Notes

- **Keep the input surface minimal and cohesive.** Every additional optional variable is a permanent piece of interface surface area consumers may come to depend on — modules that expose 40 loosely related optional variables "just in case" become hard to reason about and hard to evolve without breaking someone's edge-case usage.
- **Outputs should expose IDs/ARNs/attributes that are genuinely useful to compose with, not just "everything the module happens to create."** A thoughtful output surface (the security group ID, the endpoint, the ARN) is more valuable than mechanically exposing every resource attribute.
- **`validation` blocks on module inputs are the module author's first line of defense against misuse** — catching an invalid `allocated_storage` at plan time with a clear message is far better for a consumer than an opaque provider API error deep into `apply`.

## 7. Security Considerations

- Always mark outputs `sensitive = true` when they surface secrets, tokens, or credentials generated or retrieved inside the module — this suppresses the value from CLI output and plan/apply logs (though it still lands in the state file in plaintext, per [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)'s broader coverage of secrets-in-state).
- A required input variable with `sensitive = true` similarly prevents that value from appearing in plan output when a caller passes it in — relevant for modules accepting things like API keys or connection strings as inputs.
- Validation rules ([§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) on inputs are a security control as much as a usability one — for example, validating that a CIDR block input doesn't overlap `0.0.0.0/0` for a security-group-related variable can prevent a misconfigured caller from accidentally opening a resource to the entire internet.

## 8. Common Troubleshooting Scenarios

| Symptom                                                            | Likely Cause                                                                                | Resolution Path                                                                                     |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| `Error: Missing required argument` on a `module` block             | The module declares a variable with no `default`, and the caller didn't supply it           | Supply the argument in the `module` block, or add a sensible `default` in the module if appropriate |
| `Error: Unsupported argument` on a `module` block                  | The caller passed an argument name that doesn't match any declared `variable` in the module | Check the module's `variables.tf` for the exact expected name (typos are the most common cause)     |
| A secret value appears in plain text in `terraform plan` output    | The module's output exposing that value is missing `sensitive = true`                       | Add `sensitive = true` to the relevant `output` block; rotate the exposed secret if already leaked  |
| Caller can't access an internal resource's attribute from a module | The module doesn't expose that attribute as a declared output                               | Add the needed `output` block inside the module; internal resources are never directly reachable    |

## 9. Best Practices

- Document every variable and output with a clear `description` — this is what populates the generated README table ([§56](./Section-56-Part8-Module-Structure-and-Conventions.md)) and is often the only documentation a future caller reads.
- Prefer a small number of well-chosen required inputs plus sensible defaults for everything else, rather than either extreme (all-required is tedious to call; all-defaulted hides important behavior).
- Add `validation` blocks for any input where an invalid value would fail confusingly deep inside `apply` rather than clearly at `plan` time.

## 10. Common Anti-Patterns / Mistakes

- **Exposing raw internal resource objects as outputs "for flexibility"** (e.g., an output that dumps an entire resource's attribute map) — this defeats encapsulation by re-coupling every caller to the module's internal resource structure, exactly what outputs are supposed to prevent.
- **Forgetting `sensitive = true` on outputs that surface generated credentials** — a frequent, serious mistake that leaks secrets into logs and terminal history even though the underlying resource (e.g., `random_password`) was itself correctly configured.
- **Adding a new required variable to a widely-used module without a default**, silently breaking every existing caller's next `terraform plan` — new inputs on a module already in production use should almost always ship with a backward-compatible default.

## 11. Interview Questions

**🎯 Beginner:** _"How does a caller pass a value into a child module, and how does it get a value back out?"_
**Model answer:** Values go in as arguments on the `module` block matching declared `variable` names inside the module (e.g., `module "db" { instance_class = "db.t3.medium" }` maps to `variable "instance_class"` inside the module). Values come back out via `output` blocks declared inside the module, referenced from the caller as `module.<name>.<output_name>`, e.g., `module.db.endpoint`.
_What the interviewer is probing for:_ Basic mechanical understanding of the `module` block argument-to-variable mapping and the `module.<name>.<output>` reference syntax.

**🎯 Intermediate:** _"What happens if a `module` block supplies an argument that doesn't match any declared variable in that module, and what happens if it omits one that has no default?"_
**Model answer:** An unrecognized argument produces an "Unsupported argument" error at plan/validate time — Terraform validates the `module` block's arguments against the module's declared variables. Omitting a required variable (no `default`) produces a "Missing required argument" error, also caught before any resources are touched. Both are plan-time validation failures, not runtime surprises.
_What the interviewer is probing for:_ Understanding that the module interface is validated structurally, and where in the workflow (plan/validate, not apply) that validation happens.

**🎯 Senior:** _"Your team's shared `database` module needs a new `backup_retention_days` input to support a new use case. How do you add it without breaking the 15 existing callers already using this module in production?"_
**Model answer:** Add the new variable with a `default` value matching the module's previous hardcoded behavior (whatever `backup_retention_days` effectively was before this variable existed), so every existing caller's next plan shows zero changes unless they explicitly opt into the new variable. This is the module-boundary equivalent of a backward-compatible API change — a new required (no-default) input on an existing module is a breaking change that forces every one of the 15 callers to update simultaneously, which should be reserved for genuinely mandatory new behavior communicated and coordinated in advance, not routine feature additions.
_What the interviewer is probing for:_ Practical module-versioning discipline and backward-compatibility thinking, connecting variable defaults to real operational impact across many consumers.

**🎯 Architect:** _"You're reviewing a proposed module whose `outputs.tf` exposes 30 outputs, many of which mirror entire resource attribute blocks. What's the actual problem with this design, and what would you push the author toward instead?"_
**Model answer:** The problem is that exposing raw resource attributes (or worse, whole attribute maps) as outputs effectively republishes the module's internal implementation as its public interface — callers start depending on internal resource shapes, which means the module author can no longer refactor internals (swap a resource type, restructure how a value is computed) without it being a breaking change for consumers, defeating the entire purpose of the root/child encapsulation boundary from [§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md). I'd push the author toward a deliberately curated output surface: expose the handful of values callers actually need to compose with (an ID here, an ARN there, a computed endpoint), each with a clear description of what it represents and why it's exposed — and treat any request for "just expose everything" as a signal that either the module is trying to do too much, or the requesting use case might be better served by a different, more specific output than a blanket attribute dump.
_What the interviewer is probing for:_ Interface design judgment — recognizing that outputs are a versioned public contract, not a convenience dump, and connecting that back to why encapsulation exists in the first place.

## 12. Common Misconceptions

1. **"Module inputs and outputs are a different mechanism from root-module variables/outputs."** They're the exact same `variable`/`output` block syntax — the only difference is what's on the other side of the boundary (a calling `module` block vs. the CLI/`.tfvars`/environment).
2. **"A variable with a default is basically optional and doesn't matter much."** Defaults are load-bearing design decisions — a wrong default silently shapes every caller who doesn't override it, often without them realizing a choice was even made.
3. **"Outputs marked `sensitive` are fully protected."** They're hidden from CLI/plan output, but the underlying value still lands in the state file in plaintext — sensitive outputs mitigate log/terminal exposure, not state-file exposure ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)).
4. **"You can reach any internal module resource attribute if you know its name."** You cannot — only explicitly declared outputs are visible outside a module; internal resource addressing is invisible to callers by construction.

## 13. 🔑 Key Takeaways

- Module inputs (`variable` blocks) and outputs (`output` blocks) are syntactically identical to root-module variables/outputs — the difference is purely which boundary they interface with.
- Every `module` block argument other than reserved meta-arguments must match a declared variable in that module; missing required variables and unrecognized arguments are both caught at plan/validate time.
- Outputs are the only channel for a caller to observe anything inside a child module — internal resources are otherwise fully encapsulated.
- `sensitive = true` on outputs and variables suppresses CLI/log exposure but does not prevent the value from being stored in plaintext in the state file.
- A module's input/output surface is a versioned public contract — new required inputs and removed/renamed outputs are breaking changes for every existing caller.

## 14. Related Concepts & What's Next

[§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md) covers how a `module` block's `source` argument determines where the module's code is actually fetched from — local paths, registry sources, and Git sources. [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md) covers how version constraints let callers pin to a known-compatible interface version of a module, directly relevant to the backward-compatibility discussion above. [§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)'s validation rules and [§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)'s sensitive-value handling both apply identically at the module-boundary variables covered here.

**Next Section:** [§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md) — `Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md`
