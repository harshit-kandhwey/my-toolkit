# Section 39 (Part 6): Input Variables: Declaration, Types, and Defaults

## 1. Definition

**Plain language:** Input variables are Terraform's parameters — the knobs a configuration exposes so the same `.tf` files can produce different results without editing the files themselves. Instead of hardcoding `"t3.micro"` into a resource block, you declare a variable, reference it where the value belongs, and supply the actual value from outside the configuration (a command-line flag, a `.tfvars` file, an environment variable, or a default).

**Precise definition:** An **input variable** is declared with a `variable` block containing a label (the variable's name) and, optionally, `type`, `default`, `description`, `sensitive`, `nullable`, and `validation` arguments. Declaring a variable does not assign it a value — it defines a named slot with constraints (a `type` restricts what values are acceptable; a `default` supplies a value when none is assigned externally) that the rest of the configuration can reference via `var.<name>`. If a variable has no `default` and no value is supplied through any assignment method, Terraform prompts interactively (in a TTY) or errors (in non-interactive contexts such as CI).

> 💡 **Tip:** `type` is not optional documentation — Terraform actively enforces it. `type = number` on a variable rejects `"three"` at plan time with a clear type-mismatch error instead of letting a stringly-typed value silently propagate into a resource argument that expects a number, where it might fail confusingly three layers deeper.

## 2. Why This Matters

- **Reusability across environments.** The same root module or child module can provision a small dev environment and a large production environment purely by varying input values — no duplicated `.tf` files, no copy-paste drift between environments.
- **Separation of configuration logic from configuration data.** `variables.tf` (declarations) stays stable while `.tfvars` files (values) change per environment — this maps directly onto standard software engineering practice of separating code from config.
- **Self-documenting interfaces.** A well-declared variable (with `type`, `description`, and a sensible `default`) tells the next engineer exactly what a module or root configuration expects without reading every resource block to reverse-engineer it.
- **Type safety at plan time.** Declaring `type = list(string)` catches a caller passing a single string or a map long before that mistake reaches a cloud API and produces a cryptic provider-level error.
- **Foundation for modules.** Every reusable module ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)) is, at its boundary, nothing more than a set of input variables and output values — mastering variable declaration here is a direct prerequisite for module authoring.

## 3. Prerequisites and Dependencies

This section builds on HCL fundamentals ([§15](../Part3/Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md) — block/argument syntax) and Terraform's data types ([§17](../Part3/Section-17-Part3-Data-Types-Primitives-Collections-list-map-set-Structural-object-tuple.md) — primitives, collections, and structural types, which are exactly the vocabulary the `type` argument uses). It also assumes familiarity with the standard file layout ([§16](../Part3/Section-16-Part3-Terraform-File-Structure-and-Conventions.md)), where variable declarations conventionally live in `variables.tf`. [§40](./Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md) (immediately following) covers how a declared variable actually gets its value at runtime — precedence and assignment methods — which this section deliberately defers. [§44](./Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md) goes deeper on the `validation` block only introduced briefly here.

## 4. Architecture / Conceptual Diagram

```text
  DECLARATION (variables.tf)              REFERENCE (main.tf)           VALUE (external)

  variable "instance_type" {               resource "aws_instance" "app" {   -var="instance_type=t3.large"
    type        = string                     instance_type = var.instance_type    or
    default     = "t3.micro"                 ...                              terraform.tfvars:
    description = "EC2 instance size"      }                                    instance_type = "t3.large"
  }
        │                                         │                                     │
        │ defines a named, typed slot             │ resolves var.instance_type          │
        └────────────────────► Terraform's variable resolution (§40) ◄──────────────────┘
                                          │
                                          ▼
                              Final value used in plan/apply
                              (type-checked against declared `type`
                               before any resource is touched)
```

- Declaration and assignment are separate concerns by design: a `variable` block never contains the actual value used in a specific run (a `default` is a fallback, not "the value") — this separation is what makes the same configuration portable across environments.
- Type checking happens during variable resolution, before the resource graph ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) is even built — a type mismatch on a variable fails fast, before Terraform attempts to construct a plan.

## 5. Hands-On

### 5.1 Declaring Variables with Types and Defaults

**Purpose:** Show the core `variable` block syntax across primitive and collection types.

**Syntax:**

```hcl
variable "environment" {
  type        = string
  description = "Deployment environment name"
  default     = "dev"
}

variable "instance_count" {
  type        = number
  description = "Number of instances to launch"
  default     = 2
}

variable "enable_monitoring" {
  type        = bool
  description = "Whether to enable detailed monitoring"
  default     = true
}

variable "availability_zones" {
  type        = list(string)
  description = "AZs to distribute resources across"
  default     = ["us-east-1a", "us-east-1b"]
}

variable "tags" {
  type        = map(string)
  description = "Common resource tags"
  default     = {}
}
```

**Example usage and expected output:**

```bash
$ terraform plan
# var.environment uses its default ("dev") since nothing overrides it
# var.instance_count uses its default (2)

  # aws_instance.app[0] will be created
  # aws_instance.app[1] will be created

Plan: 2 to add, 0 to change, 0 to destroy.
```

**Production usage example:** A root module declares `environment`, `instance_count`, and `tags` with sane dev-friendly defaults; CI pipelines override them per environment via `-var-file` ([§40](./Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)) so the same configuration deploys three different environment sizes without any edits to `variables.tf` or `main.tf`.

**Common errors:** Declaring `default = "2"` (a string) on a variable typed `number` — Terraform's type conversion is permissive for literal-convertible values, but passing a genuinely non-numeric string default (`default = "two"`) fails with `Invalid default value for variable` at parse time.

### 5.2 Referencing Variables in Resource Blocks

**Purpose:** Demonstrate consuming a declared variable inside a resource argument.

**Syntax:**

```hcl
resource "aws_instance" "app" {
  count         = var.instance_count
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"

  tags = merge(var.tags, {
    Environment = var.environment
  })
}
```

**Example usage and expected output:**

```bash
$ terraform plan
  # aws_instance.app[0] will be created
      + tags = {
          + "Environment" = "dev"
        }
  # aws_instance.app[1] will be created
      + tags = {
          + "Environment" = "dev"
        }

Plan: 2 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Nearly every non-trivial resource argument in a production configuration is a `var.*` reference rather than a literal — literals in resource blocks are a smell that usually indicates a value should have been parameterized instead.

**Common errors:** Referencing `var.instance_cnt` (a typo) produces `Reference to undeclared input variable` — Terraform requires every referenced variable to have a matching `variable` block; there is no implicit declaration from use.

### 5.3 Undeclared Defaults and Interactive Prompts

**Purpose:** Show what happens when a variable has no default and no assigned value.

**Example usage and expected output:**

```bash
$ terraform plan
var.instance_type
  EC2 instance size to launch

  Enter a value:
```

In a non-interactive context (CI/CD, [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)):

```bash
$ terraform plan
Error: No value for required variable

  on variables.tf line 10:
  10: variable "instance_type" {

The root module input variable "instance_type" is not set, and has no
default value. Use a -var or -var-file command line argument to provide
a value for this variable.
```

**Production usage example:** Required variables with no default (e.g., an AWS account ID that must never silently default to the wrong account) are used deliberately to force every pipeline invocation to supply an explicit value — the absence of a default is itself a safety mechanism.

**Common errors:** A CI pipeline hanging indefinitely on a variable prompt is a classic symptom of a required variable that a `.tfvars` file update forgot to populate — non-interactive runs should always fail loudly instead, which is exactly what happens outside a TTY.

## 6. Production Usage Notes

- **Prefer explicit `type` on every variable.** Omitting `type` implicitly defaults to `any`, which defeats the type-checking benefit entirely and pushes type errors downstream into confusing provider-level failures instead of a clean Terraform-level error.
- **Defaults should represent the safest or most common case, not a placeholder.** A `default` of `"CHANGEME"` on a database password variable is worse than no default — it produces infrastructure that looks correctly configured but silently uses a throwaway value; [§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md) covers marking such variables `sensitive` and [§44](./Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md) covers rejecting placeholder values via `validation`.
- **`description` is not decorative.** `terraform plan` and `terraform console` ([§28](../Part4/Section-28-Part4-terraform-console-and-terraform-graph.md)) surface it in interactive prompts, and `terraform-docs`-style tooling generates module documentation directly from it — an undocumented variable is a support burden on every future caller of the module.

## 7. Security Considerations

- Variables are the most common entry point for secrets into a Terraform run — a database password, API token, or private key is almost always supplied as a variable value rather than hardcoded. [§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md) covers the `sensitive` argument that redacts these from plan/apply CLI output, but redaction is a display-layer protection only; the resolved value is still written to state in plaintext ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) covers the deeper mitigation: keeping secrets out of Terraform's control plane entirely via Vault or a cloud secrets manager, [§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md)/[§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)).
- Default values checked into version control are inherently non-secret — never put a real credential in a `default` argument, since anyone with read access to the repository can read it directly from `variables.tf` without ever running Terraform.
- Variables typed loosely as `any` or `string` when they should be a constrained `object` ([§45](./Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md)) or validated ([§44](./Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) create an unreviewed surface where a caller can pass unexpected values that a later resource block trusts without question.

## 8. Common Troubleshooting Scenarios

| Symptom                                                | Likely Cause                                                                                          | Resolution Path                                                                                                 |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `terraform plan` hangs waiting for input in a CI job   | A required variable (no default) was never supplied via `-var`/`-var-file`/env                        | Supply the value explicitly in the pipeline, or add a sensible `default` if one genuinely exists                |
| `Error: Invalid value for input variable` at plan time | A supplied value doesn't match the declared `type` (e.g., a string where `type = number` is declared) | Fix the supplied value's shape, or loosen/adjust the declared `type` if it was too strict for the real use case |
| `Reference to undeclared input variable`               | A `var.name` reference in a resource/output has no matching `variable "name" {}` block, often a typo  | Correct the reference or add the missing `variable` declaration                                                 |

## 9. Best Practices

- Declare every variable with `type`, `description`, and (where genuinely appropriate) a safe `default` — treat an undocumented, untyped variable as incomplete work, not a shortcut.
- Group all variable declarations in `variables.tf`, separate from resource logic in `main.tf` — this convention ([§16](../Part3/Section-16-Part3-Terraform-File-Structure-and-Conventions.md)) makes a module's entire input surface reviewable in one file.
- Use the narrowest type that's actually correct (`list(string)` rather than `any` for a list of AZ names) so Terraform's type checker catches mistakes for you instead of a provider API rejecting them later.

## 10. Common Anti-Patterns / Mistakes

- **Typing everything as `any`.** This silences the type checker entirely and pushes every mistake downstream to the provider, which produces far less actionable error messages than Terraform's own type validation.
- **Using a placeholder default like `"changeme"` or `"TODO"`.** This looks like a working configuration but silently ships an unintended value if a caller forgets to override it — a required variable with no default forces the override explicitly instead.
- **Declaring dozens of loosely related flat variables instead of one structured `object` type.** A resource that needs a name, size, and tier is better served by one `object({ name = string, size = string, tier = string })` variable ([§45](./Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md)) than three independently-passed, easy-to-mismatch string variables.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between declaring a variable and assigning it a value?"_
**Model answer:** Declaring a variable (a `variable` block in `variables.tf`) creates a named, typed slot that the rest of the configuration can reference via `var.<name>` — it does not by itself supply the value used in a run. Assignment happens separately, through one of several methods (CLI flags, `.tfvars` files, environment variables, or the variable's own `default` as a fallback). The same declared variable can receive a different assigned value on every run without changing the declaration.
_What the interviewer is probing for:_ Whether the candidate understands the separation between a variable's interface (declaration) and its runtime value (assignment), which is foundational to everything module-related later.

**🎯 Intermediate:** _"Why declare an explicit `type` on a variable instead of leaving it untyped?"_
**Model answer:** An untyped variable implicitly defaults to `type = any`, which disables Terraform's plan-time type checking entirely. With an explicit type (`string`, `number`, `list(string)`, `object({...})`, etc.), Terraform validates any supplied value against that type before building a plan, failing fast with a clear error if a caller passes the wrong shape. Without it, a type mismatch propagates further into the run and typically surfaces as a much less clear provider-level API error, or worse, silently coerces into something unintended.
_What the interviewer is probing for:_ Practical understanding of why type constraints matter operationally, not just as documentation.

**🎯 Senior:** _"A module has 15 loosely related string and number variables for configuring a single database resource. What's wrong with this design, and how would you fix it?"_
**Model answer:** Flat, individually-declared variables for a cohesive concept ("a database's configuration") make the module's call site verbose, make it easy to pass values in a way that's individually type-valid but logically inconsistent (e.g., a `disk_size` that doesn't match a `tier`), and make evolving the interface painful — adding one new related field means adding one more top-level variable and updating every caller. The fix is consolidating related fields into a single `object` type ([§45](./Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md)), optionally with `optional()` attributes for fields that have sensible defaults, plus a `validation` block ([§44](./Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) enforcing cross-field consistency (e.g., disk size must be large enough for the chosen tier) that flat variables can't express at all.
_What the interviewer is probing for:_ Whether the candidate designs variable interfaces for maintainability at scale, not just correctness for a single call.

**🎯 Architect:** _"You're designing the variable interface for a module that will be consumed by 20+ teams with varying levels of Terraform experience. What principles guide how you declare its variables?"_
**Model answer:** Minimize the required (no-default) variable surface to only what genuinely cannot have a safe default, since every required variable is friction for every caller. Give every variable a `description` precise enough that a caller never needs to read the module's internals to understand what to pass. Use `validation` blocks ([§44](./Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) to fail fast with an actionable message rather than letting a bad value surface as a cryptic provider error three resources deep. Group related fields into `object` types ([§45](./Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md)) rather than exploding them into many flat variables, both for interface clarity and to allow atomic evolution of the schema. Mark genuinely sensitive fields `sensitive` ([§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) so accidental CI log exposure isn't a silent risk for less experienced callers. Finally, treat the variable interface itself as a versioned contract — changing a required variable's type or removing a variable is a breaking change that needs a major version bump ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) for the module.
_What the interviewer is probing for:_ Systems thinking about variables as a public API surface with real usability and compatibility consequences at organizational scale, not just correct HCL syntax.

## 12. Common Misconceptions

1. **"A `default` value is what gets used if I don't explicitly need to override it."** More precisely: a default is used only when _no_ higher-precedence assignment method ([§40](./Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)) supplies a value — it's the lowest-priority fallback, not a "usual" value that's easy to accidentally override unintentionally.
2. **"Leaving `type` off a variable just means Terraform infers it from the default."** It doesn't infer per-variable; omitting `type` sets it to `any`, disabling type checking for every value that variable could ever receive, default or not.
3. **"Variables are only useful for values that genuinely differ between environments."** They're also the correct mechanism for values a module's caller should control even within one environment (e.g., a feature flag), and for keeping any provider-facing literal out of resource blocks so it's reviewable and reusable in one place.

## 13. 🔑 Key Takeaways

- A `variable` block declares a named, typed slot; it does not by itself assign the value used at runtime — assignment is a separate concern covered in [§40](./Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md).
- Explicit `type` gives Terraform real plan-time validation; omitting it silently defaults to `any` and defeats that protection.
- `default` is a fallback used only when no higher-precedence source supplies a value — never a placeholder for a secret or a value that genuinely must be reviewed per run.
- `description` is functional documentation surfaced by interactive prompts and doc-generation tooling, not just a comment.
- Related fields belong in a structured `object` type ([§45](./Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md)) rather than as many independently-passed flat variables.

## 14. Related Concepts & What's Next

[§40](./Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md) covers how a declared variable actually resolves to a value at runtime — the full precedence order across CLI flags, `.tfvars` files, environment variables, and defaults. [§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md) covers marking a variable `sensitive` and the resulting redaction behavior (and its limits). [§44](./Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md) goes deeper into the `validation` block only sketched here. [§45](./Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md) covers `object` and other structural types for variables that represent more than a single scalar value. [§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md) revisits variables specifically in the context of module input interfaces.

**Next Section:** [§40](./Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md) — `Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md`
