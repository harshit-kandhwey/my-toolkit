# Section 17 (Part 3): Data Types: Primitives, Collections (list, map, set), Structural (object, tuple)

## 1. Definition

**Plain language:** Every value in Terraform — a string, a number, a list of subnet IDs, a map of tags — has a type, and Terraform checks that types line up correctly wherever a value is used (an argument expecting a string will complain if you hand it a list). Understanding the type system means you can predict exactly what shape of value a variable, function, or resource argument expects, and read type-mismatch errors as precise diagnostics instead of noise.

**Precise definition:** Terraform's type system, defined by the underlying `cty` (Go) type system, has three categories: **primitive types** (`string`, `number`, `bool`), **collection types** (`list`, `map`, `set` — each parameterized by a single element type, e.g. `list(string)`), and **structural types** (`object`, `tuple` — each with a fixed, per-position or per-attribute type schema). A special value `null` represents the absence of a value and is valid for any type. Terraform performs automatic type conversion in many contexts (e.g., a number can convert to a string), but structural mismatches (assigning a `map` where a `list` is required) produce a type error at `plan` or `validate` time, not silently.

> 💡 **Tip:** Collections (`list`, `map`, `set`) hold **any number of elements, all the same type**. Structural types (`object`, `tuple`) hold a **fixed, known shape** where each position or attribute can have a _different_ type. That single distinction — homogeneous-and-unbounded vs. heterogeneous-and-fixed — is the entire type system's organizing principle.

## 2. Why This Matters

- Type errors are one of the most common `terraform plan`/`terraform validate` failures encountered by every Terraform user, at every skill level — being able to read `Inappropriate value for attribute` errors precisely and fix them fast is a daily-use skill.
- Variable type constraints ([§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)) are how a module author documents and enforces its expected inputs — getting the type system right is what makes a module's interface self-documenting and misuse-resistant.
- `for` expressions ([§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md)), dynamic blocks ([§22](./Section-22-Part3-Dynamic-Blocks.md)), and most built-in collection functions ([§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md)) all operate in terms of these types — you cannot reason correctly about a `for` expression's output without knowing whether the input is a `list`, `map`, or `set`, since each has different iteration semantics.
- Structural types (`object`) are the backbone of complex variable validation ([§45](../Part6/Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md), complex nested variable types) used heavily in production modules that accept rich configuration objects instead of dozens of flat scalar variables.

## 3. Prerequisites and Dependencies

Builds on the block/argument grammar from [§15](./Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md) (arguments are `identifier = expression`, and every expression evaluates to one of the types covered here) and file conventions from [§16](./Section-16-Part3-Terraform-File-Structure-and-Conventions.md). This section is a direct prerequisite for [§18](./Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md) (expressions operate over these types), [§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md) (built-in functions are type-specific), [§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md) (`for` expressions iterate collection/structural types), and [§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) (variable `type` constraints use this exact type-constraint syntax).

## 4. Architecture / Conceptual Diagram

```hcl
# ── Primitive types ──────────────────────────────────────────────
region        = "us-east-1"        # string
instance_count = 3                  # number
enable_backup  = true                 # bool

# ── Collection types: homogeneous, variable length ───────────────
availability_zones = ["us-east-1a", "us-east-1b", "us-east-1c"]  # list(string)
tags = {                                                          # map(string)
  Environment = "production"
  Team        = "platform"
}
allowed_ports = toset([22, 80, 443])                              # set(number)

# ── Structural types: heterogeneous, fixed shape ──────────────────
server_config = {                    # object({ name = string, cpu = number, tags = list(string) })
  name = "web-01"
  cpu  = 2
  tags = ["prod", "web"]
}

coordinates = ["us-east-1", 3, true]  # tuple([string, number, bool]) — fixed positions, mixed types
```

- **`list`** — ordered, allows duplicates, indexed by position (`var.azs[0]`).
- **`map`** — unordered key/value pairs, all values the same type, indexed by key (`var.tags["Team"]`).
- **`set`** — unordered, **no duplicates**, no indexing by position (use `for` or convert to `list` to index).
- **`object`** — fixed named attributes, each with its own declared type; think "a typed record."
- **`tuple`** — fixed-length, fixed per-position types; think "a typed, heterogeneous array."

## 5. Hands-On

### 5.1 Primitive Types and Implicit Conversion

**Purpose:** Understand `string`, `number`, `bool`, and how Terraform's implicit type conversion behaves between them.

**Syntax:**

```hcl
variable "port" {
  type = number
}
```

**Example usage and expected output:**

```bash
$ terraform console
> 5 + "3"
8
> "${5}"
"5"
> tostring(true)
"true"
> can(tonumber("abc"))
false
```

**Production usage example:** Implicit numeric/string conversion is convenient in interpolated strings (`"port-${var.port}"` works whether `var.port` is typed `number` or `string`) but production modules still declare explicit `type` constraints on every variable ([§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)) rather than relying on conversion, because conversion masks genuine caller mistakes (e.g., passing `"true"` instead of `true` for a `bool`-typed variable) until they surface as a confusing downstream error.

**Common errors:**

```text
Error: Invalid value for variable
  var.port is "eighty" — a number is required.
```

Passing a non-numeric string where `number` is declared fails at plan time with a precise message — this is the type system doing its job, not a bug.

### 5.2 Collection Types: `list`, `map`, `set`

**Purpose:** Choose the right collection type for ordered/indexed data (`list`), keyed data (`map`), and deduplicated unordered data (`set`).

**Syntax:**

```hcl
variable "subnet_ids" {
  type = list(string)
}

variable "tags" {
  type = map(string)
}

variable "allowed_cidrs" {
  type = set(string)
}
```

**Example usage and expected output:**

```bash
$ terraform console
> ["a", "b", "c"][1]
"b"
> { for k, v in {"a" = 1, "b" = 2} : k => v * 10 }
{
  "a" = 10
  "b" = 20
}
> toset(["x", "x", "y"])
[
  "x",
  "y",
]
```

**Production usage example:** Security group rule CIDR blocks are almost always typed as `set(string)` rather than `list(string)` specifically because duplicate CIDR entries are meaningless and a `set` makes accidental duplicates a non-issue rather than a silent redundant rule; ordered resources like `availability_zones` (where index order matters for zone-to-subnet mapping) use `list(string)` instead.

**Common errors:** Attempting to index a `set` by position (`var.allowed_cidrs[0]`) fails — `Error: Invalid index — this value does not have any indices` — because sets are unordered by design; convert to a `list` first (`tolist(var.allowed_cidrs)[0]`) if positional access is genuinely needed.

### 5.3 Structural Types: `object` and `tuple`

**Purpose:** Model fixed-shape, heterogeneous data — the type category used for rich variable inputs and nested configuration.

**Syntax:**

```hcl
variable "server" {
  type = object({
    name          = string
    instance_type = string
    cpu_count     = number
    is_production = bool
  })
}
```

**Example usage and expected output:**

```hcl
variable "server" {
  type = object({
    name          = string
    instance_type = string
    cpu_count     = number
    is_production = bool
  })
  default = {
    name          = "web-01"
    instance_type = "t3.micro"
    cpu_count     = 2
    is_production = false
  }
}
```

```bash
$ terraform console
> var.server.name
"web-01"
> var.server.cpu_count
2
```

**Production usage example:** Modules that accept complex, multi-field configuration (e.g., a single `server` object instead of four separate flat variables) use `object` types specifically because it groups logically related inputs into one self-documenting, independently-validatable unit — this pattern is covered fully in [§45](../Part6/Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md).

**Common errors:** Adding an attribute to a value that isn't declared in the `object` type constraint produces `Error: Unsupported attribute` if optional attributes aren't explicitly declared with `optional()` (available since Terraform 1.3) — object types are closed by default, not permissive like a loosely-typed map.

## 6. Production Usage Notes

- `set` types silently reorder and deduplicate on assignment — if a downstream tool or output genuinely depends on original insertion order, `list` is the correct type even if duplicates are impossible in practice.
- `object` type constraints support the `optional(type, default)` modifier (Terraform 1.3+) for attributes that callers may omit — this is now the standard way to give complex object-typed variables sensible per-field defaults without forcing every caller to specify every attribute.
- `terraform console` ([§28](../Part4/Section-28-Part4-terraform-console-and-terraform-graph.md)) is the fastest way to experimentally check a type or expression's evaluated result before committing it to a `.tf` file — reach for it constantly during type-related debugging.

## 7. Security Considerations

- Type constraints on variables are a lightweight but real security control: a `sensitive = true` attribute combined with a strict `type` constraint ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) prevents both accidental console/log exposure and accidental type confusion for values like credentials or connection strings.
- Overly loose typing (declaring a variable as `any` instead of a specific type) removes Terraform's ability to catch a caller passing an unexpected shape of data — in security-sensitive modules (IAM policy documents, network CIDR inputs), precise typing is itself a defense against misconfiguration.

## 8. Common Troubleshooting Scenarios

| Symptom                                                 | Likely Cause                                                                 | Resolution Path                                                                                              |
| ------------------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `Inappropriate value for attribute`                     | Value's actual type doesn't match the declared/expected type                 | Use `terraform console` to inspect the actual type; adjust the value or the type constraint                  |
| `Invalid index` on a set                                | Attempting positional indexing (`var.x[0]`) on a `set` value                 | Convert with `tolist()` first, or restructure to use `for` instead of indexing                               |
| `Unsupported attribute` on an object value              | Referencing an attribute not declared in the `object()` type constraint      | Add the attribute to the type constraint (with `optional()` if not always present)                           |
| Duplicate list entries unexpectedly vanish after a plan | The value was implicitly converted to/through a `set` somewhere in the chain | Trace the type through variable declarations and function calls; switch to `list` if order/duplicates matter |

## 9. Best Practices

- Always declare explicit `type` constraints on variables rather than defaulting to `any` — precise types are self-documentation and free validation.
- Use `set` for unordered, dedup-significant data (security group CIDRs, tag keys); use `list` when order or duplicates are meaningful (ordered AZ lists, ordered command arguments).
- Prefer `object` types with `optional()` attributes over many flat scalar variables once a module's configuration surface grows past a handful of related values.
- Reach for `terraform console` liberally to check a type or expression's evaluated shape before wiring it into a real resource argument.

## 10. Common Anti-Patterns / Mistakes

- **Typing every variable as `any`** to "avoid dealing with types" — this defeats the type system's entire purpose and pushes type-mismatch bugs from `plan` time (cheap to catch) to `apply` time or runtime (expensive to catch).
- **Using `list` where `set` is semantically correct** (e.g., a list of security group IDs where duplicates are meaningless) — works, but invites duplicate-entry bugs the type system could have prevented.
- **Deeply nesting `object` types many levels without validation blocks** ([§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) — the type constraint alone doesn't enforce semantic correctness (e.g., "cpu_count must be positive"), only shape correctness.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a `list` and a `set` in Terraform?"_
**Model answer:** Both hold multiple values of the same type, but a `list` is ordered and allows duplicates (accessed by index, e.g. `var.x[0]`), while a `set` is unordered, disallows duplicates, and cannot be indexed by position.
_What the interviewer is probing for:_ Basic type-system vocabulary and whether the candidate knows sets can't be positionally indexed — a very common early stumbling block.

**🎯 Intermediate:** _"When would you use an `object` type instead of a `map` for a variable?"_
**Model answer:** A `map` requires all values to share one type and is meant for an open-ended, dynamically-keyed collection (e.g., arbitrary tag key/value pairs). An `object` is for a fixed, known set of named attributes where each attribute can have its own distinct type (e.g., a server config with a `string` name, a `number` cpu_count, and a `bool` flag) — it's the right choice whenever the shape of the data is known in advance and attributes are conceptually different fields, not interchangeable entries.
_What the interviewer is probing for:_ Understanding that the map/object distinction is about known-fixed-heterogeneous-shape vs. open-ended-homogeneous-shape, not just "which one looks more like JSON."

**🎯 Senior:** _"A module variable is typed `list(string)` but a caller passes a value that Terraform silently reorders. What's actually going on?"_
**Model answer:** This is almost never the `list` type itself reordering — lists preserve order. More likely, the value passed in went through a `set` conversion somewhere in the chain (e.g., a function like `toset()` was applied, or the underlying data source naturally returns a set-like unordered structure), and converting back to `list(string)` afterward "sorts" or reorders based on the set's internal representation rather than restoring original insertion order. The fix is to trace the actual type through every transformation between the source of the data and the point it's consumed, since a `set` round-trip anywhere in the pipeline permanently loses original order.
_What the interviewer is probing for:_ Debugging instinct — tracing type transformations through a pipeline rather than assuming the symptom's location is the root cause.

**🎯 Architect:** _"You're designing the input variable interface for a widely-reused internal module. How do you decide between many flat scalar variables versus a smaller number of `object`-typed variables?"_
**Model answer:** Flat scalars are easier for a first-time caller to discover (autocomplete, simple `.tfvars` entries) but don't scale past roughly half a dozen related inputs without becoming unwieldy and losing the grouping relationship between related fields. Object-typed variables group related configuration into one coherent, independently-versionable unit, support `optional()` attributes for sensible per-field defaults, and make it easier to add a new optional field later without a breaking change to the variable list itself — but they're less discoverable and harder to override piecemeal from a `.tfvars` file (a caller must know the whole object shape to override one field, at least without `merge()` gymnastics). In practice, I default to flat scalars for genuinely independent top-level settings and switch to `object` types the moment a group of 3+ variables are always set together or represent one logical entity (e.g., "the database configuration").
_What the interviewer is probing for:_ Real interface-design judgment for module authorship, not just type-system trivia — this is a decision every senior Terraform module author makes repeatedly.

## 12. Common Misconceptions

1. **"Maps and objects are the same thing."** Maps require homogeneous value types and open-ended keys; objects have fixed, named, independently-typed attributes.
2. **"Sets preserve insertion order."** They don't — sets are unordered by definition, and Terraform may reorder/deduplicate elements on conversion.
3. **"`any` is a safe default type for a variable."** It disables Terraform's type checking for that variable entirely, deferring type errors from cheap `plan`-time detection to more expensive downstream failures.
4. **"Tuples and lists are interchangeable."** A `tuple` has a fixed length with independently-typed positions (heterogeneous); a `list` is unbounded and homogeneous — declaring `type = list(string)` when values are actually mixed-type will fail type checking.

## 13. 🔑 Key Takeaways

- Terraform's type system splits into primitives (`string`, `number`, `bool`), collections (`list`, `map`, `set` — homogeneous, variable-length), and structural types (`object`, `tuple` — heterogeneous, fixed shape).
- `set` is unordered and deduplicated; use it for data where duplicates are meaningless and order doesn't matter — use `list` otherwise.
- `object` types with `optional()` attributes are the standard pattern for rich, self-documenting module inputs, replacing large numbers of flat scalar variables.
- Precise typing (avoiding `any`) is both a correctness tool and a lightweight security control — it catches caller mistakes at `plan` time instead of letting them propagate.
- `terraform console` is the fastest tool for experimentally verifying a value's actual evaluated type.

## 14. Related Concepts & What's Next

[§18](./Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md) covers the expressions (arithmetic, comparison, conditional) that operate over these types. [§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md) covers built-in functions, many of which exist specifically to convert or manipulate these types (`tolist()`, `toset()`, `tomap()`, `keys()`, `values()`). [§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md) covers `for` expressions, whose output type (list vs. map) depends directly on the syntax used and the input collection's type. [§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) and [§45](../Part6/Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md) apply this type system fully to variable declarations, including nested object types and validation.

**Next Section:** [§18](./Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md) — `Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md`
