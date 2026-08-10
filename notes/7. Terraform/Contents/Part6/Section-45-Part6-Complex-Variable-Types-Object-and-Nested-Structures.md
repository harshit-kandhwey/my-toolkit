# Section 45 (Part 6): Complex Variable Types: Object and Nested Structures

## 1. Definition

**Plain language:** Sometimes a single scalar variable (a string, a number) isn't enough to represent what a caller needs to configure — a database needs a name, a size, a tier, and a flag for whether it's multi-AZ, all as one cohesive unit. Instead of declaring four separate flat variables that a caller could pass in an inconsistent combination, you declare one `object`-typed variable that bundles them together, with each field individually typed, and some fields allowed to be optional with their own defaults.

**Precise definition:** Terraform's **structural types** — `object({ ... })`, `tuple([ ... ])` — describe values with a fixed, named (object) or positional (tuple) internal shape, as opposed to **collection types** (`list`, `map`, `set`) which hold an arbitrary number of elements all of the _same_ type. An `object` type constraint is written as `object({ attribute_name = type, ... })`, where each attribute can itself be any type, including another nested `object` or a collection of objects — allowing arbitrarily deep structured variables. Since Terraform 1.3, individual object attributes can be marked `optional(type, default_value)`, meaning a caller may omit that attribute entirely and Terraform substitutes the given default, rather than requiring every attribute to be explicitly supplied on every call.

> 💡 **Tip:** `object` types shine when a set of fields is conceptually one thing (a "database configuration," a "network configuration") that should be validated and passed around as a unit. If fields are genuinely independent and a caller might set some without the others in no particular combination, separate flat variables are still often the clearer design — object types are a tool for cohesion, not a default for every multi-field input.

## 2. Why This Matters

- **Modeling real-world configuration cohesively.** Cloud resources routinely have config that's naturally grouped — a database's engine, version, size, and backup window belong together conceptually, and an `object` type lets the variable declaration reflect that grouping directly instead of scattering it across unrelated flat variables.
- **Reducing call-site verbosity and mismatch risk.** Passing one structured object with named fields to a module call is clearer and less error-prone than passing five positional or loosely related flat arguments where it's easy to mix up which value goes where.
- **Optional attributes with sane defaults.** `optional()` lets a module ship a rich configuration schema while still letting most callers specify only the two or three fields they actually care about, with everything else defaulting sensibly — without `optional()`, every caller would be forced to specify every single attribute on every single call.
- **Enabling structural validation.** A `validation` block ([§44](./Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) on an object-typed variable can check cross-attribute consistency (a `size` and `tier` combination that doesn't make sense together) that would be impossible to express across several independently-declared flat variables.
- **Foundation for `for_each` over structured data.** A `map(object({...}))` variable — a map of structured configurations keyed by name — is one of the most common patterns for driving `for_each` ([§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)) over a set of similarly-shaped-but-distinct resources (e.g., provisioning several differently-sized subnets from one variable).

## 3. Prerequisites and Dependencies

This section assumes the full data-type vocabulary from [§17](../Part3/Section-17-Part3-Data-Types-Primitives-Collections-list-map-set-Structural-object-tuple.md) (primitives, collections, and a first introduction to structural types), and builds directly on [§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) (variable declaration mechanics) and [§44](./Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md) (validation, frequently paired with object types for cross-attribute checks). It also connects forward to [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) (`count` vs. `for_each`), since structured map-of-object variables are a common `for_each` driver, and to [§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md) (module inputs/outputs), where object types are the standard way a well-designed module exposes a rich, cohesive configuration surface.

## 4. Architecture / Conceptual Diagram

```text
   FLAT VARIABLES (loosely related, error-prone at call site)

   variable "db_name" { type = string }
   variable "db_size" { type = string }
   variable "db_tier" { type = string }
   variable "db_multi_az" { type = bool }
        │
        │  caller must pass all four correctly, in no enforced relationship
        ▼
   module "db" {
     db_name     = "app"
     db_size     = "large"    ◄── nothing stops an inconsistent
     db_tier     = "basic"    ◄── size/tier combination from being passed
     db_multi_az = true
   }

   ────────────────────────────────────────────────────────────────

   OBJECT-TYPED VARIABLE (cohesive, individually typed, partially optional)

   variable "database" {
     type = object({
       name      = string
       size      = string
       tier      = optional(string, "standard")   ◄── optional, defaults if omitted
       multi_az  = optional(bool, false)           ◄── optional, defaults if omitted
     })

     validation {                                   ◄── cross-attribute check,
       condition     = !var.database.multi_az || var.database.tier != "basic"  #     impossible with flat vars
       error_message = "multi_az requires a tier other than 'basic'."
     }
   }
        │
        ▼
   module "db" {
     database = {
       name = "app"
       size = "large"
       # tier and multi_az omitted — use their optional() defaults
     }
   }
```

- Structural types are checked recursively — every nested attribute's type constraint is enforced just as strictly as a top-level scalar variable's `type` would be, including nested `object`s within `object`s.
- `optional()` only applies inside an `object({...})` type constraint; it has no meaning on a top-level variable's own `type` argument — a whole variable is either required (no `default`) or has a `default`, per [§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md), while individual object _attributes_ use `optional()` for the same effect at a finer grain.

## 5. Hands-On

### 5.1 Declaring a Basic Object-Typed Variable

**Purpose:** Show the core `object({...})` syntax with mixed required and typed attributes.

**Syntax:**

```hcl
variable "database" {
  type = object({
    name    = string
    engine  = string
    version = string
    size    = string
  })
  description = "Core database configuration"
}
```

**Example usage and expected output:**

```bash
$ cat terraform.tfvars
database = {
  name    = "app-db"
  engine  = "postgres"
  version = "15.4"
  size    = "db.t3.medium"
}

$ terraform plan
  # aws_db_instance.main will be created
      + identifier     = "app-db"
      + engine         = "postgres"
      + engine_version = "15.4"
      + instance_class = "db.t3.medium"

Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Any module provisioning a resource with more than three or four related configuration fields typically groups them into exactly this kind of `object`-typed variable rather than exposing each field as its own top-level variable.

**Common errors:** Omitting a required (non-`optional()`) attribute in the supplied value — e.g., leaving out `version` — produces `Error: Invalid value for variable` with `attribute "version" is required`, since every non-optional attribute must be present in every supplied object value.

### 5.2 Optional Attributes with Defaults

**Purpose:** Show `optional(type, default)` letting callers omit attributes that have sensible fallbacks.

**Syntax:**

```hcl
variable "database" {
  type = object({
    name           = string
    engine         = string
    version        = string
    size           = optional(string, "db.t3.micro")
    multi_az       = optional(bool, false)
    backup_days    = optional(number, 7)
  })
}
```

**Example usage and expected output:**

```bash
$ cat terraform.tfvars
database = {
  name    = "app-db"
  engine  = "postgres"
  version = "15.4"
  # size, multi_az, backup_days all omitted — optional() defaults apply
}

$ terraform console
> var.database
{
  "backup_days" = 7
  "engine" = "postgres"
  "multi_az" = false
  "name" = "app-db"
  "size" = "db.t3.micro"
  "version" = "15.4"
}
```

**Production usage example:** A shared internal module used by many teams typically makes only the truly essential fields required (`name`, `engine`, `version`) and gives every operational-tuning field (`size`, `multi_az`, `backup_days`) an `optional()` default, so a minimal caller can adopt the module with a three-line object while power users can still override anything.

**Common errors:** Forgetting that `optional()` requires Terraform 1.3+ — using it against an older `required_version` constraint ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)) fails during `terraform init`/`validate` with an unsupported-syntax error, a common gotcha when a module is meant to support older Terraform versions.

### 5.3 Nested Objects and `map(object({...}))` for `for_each`

**Purpose:** Show a nested object and the common map-of-objects pattern used to drive `for_each` over structurally similar resources.

**Syntax:**

```hcl
variable "subnets" {
  type = map(object({
    cidr_block        = string
    availability_zone = string
    public            = optional(bool, false)
    tags              = optional(map(string), {})
  }))
  description = "Subnets keyed by logical name"
}

resource "aws_subnet" "this" {
  for_each = var.subnets

  vpc_id            = aws_vpc.main.id
  cidr_block        = each.value.cidr_block
  availability_zone = each.value.availability_zone
  map_public_ip_on_launch = each.value.public
  tags              = merge(each.value.tags, { Name = each.key })
}
```

**Example usage and expected output:**

```bash
$ cat terraform.tfvars
subnets = {
  public-a = {
    cidr_block        = "10.0.1.0/24"
    availability_zone = "us-east-1a"
    public             = true
  }
  private-a = {
    cidr_block        = "10.0.2.0/24"
    availability_zone = "us-east-1a"
  }
}

$ terraform plan
  # aws_subnet.this["private-a"] will be created
  # aws_subnet.this["public-a"] will be created

Plan: 2 to add, 0 to change, 0 to destroy.
```

**Production usage example:** This `map(object({...}))` plus `for_each` pattern is the standard way production modules provision a variable-length set of structurally similar-but-individually-configured resources (subnets, IAM roles, S3 buckets) from a single input variable, addressed stably by the map key rather than a positional index ([§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)).

**Common errors:** Using `list(object({...}))` with `for_each` instead of `map(object({...}))` requires converting the list to a map first (commonly via a `for` expression keyed by some unique attribute) since `for_each` needs stable string keys, not positional indices — passing a list directly to `for_each` either fails or, if coerced, reintroduces the same reordering instability that `count` has ([§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)).

## 6. Production Usage Notes

- **`optional()` defaults are resolved once, at the point the object value is first evaluated** — they behave consistently with how top-level variable defaults work ([§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)), just at the per-attribute granularity instead.
- **Deeply nested object types (three or more levels) become hard to read and validate.** Beyond a certain nesting depth, consider whether the structure should be flattened, split into multiple separate variables, or restructured into a `map(object({...}))` keyed collection instead of ever-deeper nesting.
- **Structural type mismatches produce precise, attribute-level error messages** (e.g., `.database.size: number required`) — this precision is one of the strongest arguments for using `object` types over a loosely-typed `map(any)` or `any` for structured configuration, since the latter defers all such errors to wherever the value is eventually consumed.

## 7. Security Considerations

- A `sensitive`-marked object-typed variable marks the _entire_ object sensitive for CLI redaction purposes ([§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) — there is no way to mark only one nested attribute of an object sensitive while leaving sibling attributes visible; if only one field is genuinely sensitive (a password nested alongside a non-sensitive database name), consider splitting it into a separate, individually `sensitive`-marked variable instead.
- Overly permissive object types (using `any` for a nested attribute that should itself be constrained) reintroduce the same unreviewed-input risk described in [§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) at the nested level — apply the same "narrowest correct type" discipline recursively, not just at the top level of the variable.

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Likely Cause                                                                                                                                                                                                 | Resolution Path                                                                                                                                                             |
| -------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `attribute "x" is required` even though a value seems to be supplied | The attribute is misspelled in the supplied object value, or nested one level too shallow/deep relative to the type constraint                                                                               | Compare the supplied `.tfvars` object shape field-by-field against the `object({...})` type declaration                                                                     |
| `optional()` syntax rejected during `terraform init`/`validate`      | The module's `required_version` constraint ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)) allows a Terraform version older than 1.3, which doesn't support `optional()` | Raise the minimum required Terraform version, or restructure the type without `optional()` for broader compatibility                                                        |
| `for_each` argument must be a map or set of strings, got object      | A `list(object({...}))` or a bare nested collection was passed directly to `for_each` without conversion to a stable-keyed map                                                                               | Convert to `map(object({...}))`, keyed by a unique attribute, before passing to `for_each` ([§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)) |

## 9. Best Practices

- Reach for `object({...})` when a set of fields is conceptually one cohesive configuration unit, not merely because a module has "several variables" — cohesion, not count, is the right criterion.
- Mark genuinely optional fields with `optional(type, default)` so callers only need to specify what they actually want to customize, keeping the common case concise.
- Prefer `map(object({...}))` over `list(object({...}))` whenever the values will drive `for_each`, since it gives every element a stable, meaningful key instead of a fragile positional index.

## 10. Common Anti-Patterns / Mistakes

- **Over-nesting structured types three or four levels deep "for completeness."** Beyond a shallow nesting depth, readability and validation both suffer — flatten or split before nesting becomes unmanageable.
- **Using `any` inside a nested attribute instead of a real constraint**, silently reintroducing the exact type-safety gap `object` types exist to close.
- **Building a `list(object({...}))` variable that's immediately converted to a map inside every consuming module** — if the value is always going to be keyed, declaring it as `map(object({...}))` at the variable boundary avoids the repeated conversion logic entirely.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `map(string)` and `object({...})` as a variable type?"_
**Model answer:** `map(string)` holds an arbitrary number of key-value pairs where every value must be the same type (a string) — the keys aren't individually declared or constrained. `object({...})` declares a fixed, named set of attributes where each attribute can have its own distinct type — it's for representing a single structured "thing" with known fields, not an open-ended collection of same-typed values.
_What the interviewer is probing for:_ Basic grasp of the distinction between collection types (uniform, arbitrary size) and structural types (fixed shape, per-attribute typing).

**🎯 Intermediate:** _"What does `optional()` do inside an `object({...})` type constraint, and what version of Terraform introduced it?"_
**Model answer:** `optional(type, default_value)` marks a specific attribute of an object type as not required — a caller can omit it entirely from the supplied value, and Terraform substitutes the given default for that attribute. Without it, every attribute declared in the `object({...})` type must be explicitly present in every value assigned to that variable. `optional()` was introduced in Terraform 1.3; using it in a module with a `required_version` constraint that allows older Terraform versions will fail for those older versions.
_What the interviewer is probing for:_ Both the functional behavior and the practical compatibility gotcha (version requirement), which is a common real-world trip-up.

**🎯 Senior:** _"You have a `map(object({cidr_block = string, az = string}))` variable driving `for_each` for subnet creation. A teammate wants to switch it to `list(object({...}))` because 'lists are simpler.' What's your response?"_
**Model answer:** I'd push back — a list loses the stable, meaningful key that `for_each` needs to track resource identity across plans. With `map(object({...}))`, each subnet is addressed by its map key (e.g., `"public-a"`), so adding or removing an unrelated entry doesn't disturb any other subnet's resource address in state. With `list(object({...}))`, `for_each` would need the list converted to a map anyway (since it requires string keys), and if that conversion uses positional index as the key, it reintroduces exactly the reordering instability `for_each` was meant to solve over `count` ([§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)) — inserting an element in the middle of the list would shift every subsequent index-derived key, causing Terraform to plan to destroy and recreate every subnet after the insertion point. Keeping the variable as `map(object({...}))` from the start avoids this failure mode entirely and is a better fit for the resource's stable-identity requirements.
_What the interviewer is probing for:_ Connecting the type-choice decision to `for_each`'s stable-key requirement and the concrete operational consequence (unnecessary destroy/recreate) of getting it wrong — not just a stylistic preference.

**🎯 Architect:** _"You're designing the variable interface for a module provisioning a fleet of microservices, each needing a name, image, replica count, resource limits, and optional environment-specific overrides. How do you structure the variable types?"_
**Model answer:** I'd model each microservice as a nested `object` capturing its cohesive configuration — name, image, replicas (with an `optional()` default for a sensible baseline replica count), and a nested `resources` object for CPU/memory limits (itself with `optional()` defaults so most services don't need to specify limits explicitly). The fleet as a whole becomes a `map(object({...}))` keyed by service name, driving `for_each` over the actual deployment resources so each service has a stable identity independent of the others. For environment-specific overrides, I'd resist nesting environment logic directly into the object type itself — that couples the module's core schema to a concern (environment) that's better handled by the caller supplying a different variable value per environment via `.tfvars` ([§40](./Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)), keeping the object type focused purely on "what a microservice looks like," not "how it differs across environments." I'd add `validation` blocks ([§44](./Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) for cross-attribute consistency the type alone can't express — for instance, a memory limit that must be at least proportional to a requested CPU limit — and keep nesting to at most two levels (fleet map → service object → resources object) since deeper nesting starts to hurt both readability and the clarity of validation error messages. Finally, I'd document the full schema with clear `description`s at every level, since a nested structural type is otherwise opaque to a new caller without reading the module source.
_What the interviewer is probing for:_ Whether the candidate can design a multi-level structural type that balances cohesion, `for_each` stability, and readability, and correctly separates schema concerns (what a service is) from deployment concerns (how it varies by environment).

## 12. Common Misconceptions

1. **"`object` types must have every field explicitly typed as a primitive."** A field inside an `object({...})` can itself be a collection (`list(string)`), another `object`, or any other valid type — nesting is fully supported, not limited to scalars.
2. **"`optional()` works on any variable, not just inside `object` types."** `optional()` is specifically an `object`-type-constraint construct for marking individual attributes optional; a top-level variable's own optionality is controlled by whether it has a `default` ([§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)), a different mechanism entirely.
3. **"Marking an object-typed variable `sensitive` only hides the sensitive-looking fields."** `sensitive = true` on an object-typed variable redacts the entire object from CLI output, not just the fields that are conceptually secret — if only one nested field is truly sensitive, it may need to be split out as its own separately-marked variable.
4. **"A `list(object({...}))` and a `map(object({...}))` are interchangeable for `for_each`."** They are not directly interchangeable — `for_each` requires a map or set of strings as its key source; a list requires an explicit, deliberate conversion to a stably-keyed map first, or it reintroduces the positional-index instability `for_each` exists to avoid.

## 13. 🔑 Key Takeaways

- `object({...})` declares a fixed, named-attribute structural type for representing a cohesive configuration unit, distinct from collection types (`list`, `map`, `set`) which hold an arbitrary number of same-typed elements.
- `optional(type, default)`, available since Terraform 1.3, lets individual object attributes be omitted by the caller with a substituted default, keeping the common call case concise without sacrificing a rich full schema.
- Nested `object`s within `object`s are supported to arbitrary depth, but readability and validation clarity degrade past roughly two levels — flatten or split before that point.
- `map(object({...}))` is the standard, stable-keyed pattern for driving `for_each` over a variable-length set of structurally similar resources; `list(object({...}))` requires explicit conversion first and risks reintroducing index-based instability if done carelessly.
- Sensitivity marking on an object-typed variable applies to the whole object, not selectively to individual nested attributes — split out genuinely secret fields into their own variable if partial redaction is needed.

## 14. Related Concepts & What's Next

This section closes out Part 6 (Variables, Outputs, and Locals) by extending [§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)'s type vocabulary into full structural types. [§44](./Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)'s validation patterns apply directly to object-typed variables for cross-attribute checks. [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) (`count` vs. `for_each`) is the direct consumer of the `map(object({...}))` pattern demonstrated here. [§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md) revisits complex types specifically in the context of designing a module's full input interface. Part 7 shifts focus entirely to state — what Terraform actually records about the resources these variables help configure, and why that record exists at all.

**Next Section:** [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md) — `Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md`
