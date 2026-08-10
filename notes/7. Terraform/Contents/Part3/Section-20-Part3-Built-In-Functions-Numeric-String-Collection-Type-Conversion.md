# Section 20 (Part 3): Built-In Functions: Numeric, String, Collection, and Type Conversion Functions

## 1. Definition

**Plain language:** Terraform ships with a large standard library of built-in functions — for doing math, manipulating strings, transforming lists and maps, and converting between types — that you call the same way in every expression: `function_name(arg1, arg2, ...)`. There is no way to define your own custom function in HCL itself; every transformation you need must be built from this fixed library (composed together, or via `for` expressions), which makes knowing the library well a genuine productivity multiplier.

**Precise definition:** Terraform's built-in functions are a fixed, versioned set of pure functions (no side effects, deterministic given the same inputs) exposed by Terraform core, organized by category: **numeric** (`min`, `max`, `abs`, `ceil`, `floor`), **string** (`format`, `join`, `split`, `replace`, `trimspace`, `lower`, `upper`, `substr`), **collection** (`length`, `keys`, `values`, `merge`, `concat`, `contains`, `flatten`, `distinct`, `sort`, `lookup`, `element`, `zipmap`), **type conversion** (`tostring`, `tonumber`, `tolist`, `toset`, `tomap`, `try`, `can`), plus encoding, filesystem, date/time, hash/crypto, and IP-network categories. Functions cannot be user-defined; the full list is fixed per Terraform version and documented in HashiCorp's function reference. `terraform console` ([§28](../Part4/Section-28-Part4-terraform-console-and-terraform-graph.md)) is the standard tool for experimenting with function calls before committing them to configuration.

> 💡 **Tip:** You cannot write your own function in HCL — every transformation must be composed from this fixed standard library (or delegated to a `for` expression, [§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md)). When stuck, the question to ask is "what's the built-in function for this," not "how do I write a function for this."

## 2. Why This Matters

- Real-world Terraform configuration leans heavily on function composition for anything beyond the most trivial value assignment — computed names, merged tag maps, sanitized inputs, safe defaults — and knowing the standard library well directly translates into writing shorter, clearer, less error-prone HCL.
- `merge()` and `lookup()` are the two most common functions for combining default and override configuration (e.g., merging a module's default tags with caller-supplied tags) — a pattern that appears in nearly every production module.
- `try()` and `can()` are the idiomatic way to handle potentially-missing or potentially-invalid values gracefully, replacing the unsafe short-circuit patterns flagged in [§18](./Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md).
- Because functions can't be user-defined, misunderstanding what's available (and reinventing it clumsily with nested `for` expressions and ternaries) is a common source of unnecessarily complex configuration that a single built-in function would have solved directly.

## 3. Prerequisites and Dependencies

Requires [§17](./Section-17-Part3-Data-Types-Primitives-Collections-list-map-set-Structural-object-tuple.md) (types — functions are strictly typed on input/output) and [§18](./Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md) (expressions — function calls are themselves expressions). Builds directly on [§19](./Section-19-Part3-String-Interpolation-and-Templating-heredoc-templatefile.md) (templating functions like `format()` are often combined with `templatefile()`). Prerequisite for [§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md) (`for` expressions frequently wrap function calls) and [§22](./Section-22-Part3-Dynamic-Blocks.md) (dynamic blocks often iterate over function-transformed collections, e.g. the output of `merge()` or `flatten()`).

## 4. Architecture / Conceptual Diagram

```hcl
# ── Numeric ──────────────────────────────────────────────
max(1, 5, 3)                        # 5
min(var.desired_count, var.max_count)
ceil(4.2)                           # 5
abs(-7)                             # 7

# ── String ───────────────────────────────────────────────
format("%s-%s-%03d", var.project, var.env, count.index + 1)  # "app-prod-001"
join(",", ["a", "b", "c"])          # "a,b,c"
split(",", "a,b,c")                 # ["a", "b", "c"]
trimspace("  hello  ")              # "hello"
lower("PROD")                       # "prod"
replace("hello-world", "-", "_")    # "hello_world"

# ── Collection ───────────────────────────────────────────
length(var.subnet_ids)              # element count
keys({a = 1, b = 2})                # ["a", "b"]
values({a = 1, b = 2})              # [1, 2]
merge({a = 1}, {b = 2}, {a = 3})    # {a = 3, b = 2}  (later args win on key conflict)
concat(["a"], ["b", "c"])           # ["a", "b", "c"]
contains(["a", "b"], "a")           # true
flatten([["a", "b"], ["c"]])        # ["a", "b", "c"]
lookup({a = 1}, "a", 0)             # 1  (key, default-if-missing)

# ── Type conversion / error-safety ─────────────────────────
tostring(42)                        # "42"
tonumber("42")                      # 42
toset(["x", "x", "y"])              # deduplicated set
try(var.optional_map["missing"], "default")  # "default" instead of an error
can(tonumber(var.input))            # true/false instead of an error
```

## 5. Hands-On

### 5.1 Numeric and String Functions

**Purpose:** Compute derived numbers and build formatted, consistent strings (especially resource names).

**Syntax:**

```hcl
format(format_string, args...)
max(numbers...)
```

**Example usage and expected output:**

```bash
$ terraform console
> format("%s-%02d", "web", 3)
"web-03"
> max(var.min_size, 2)
2
> join("-", [var.project, var.environment, "sg"])
"payments-prod-sg"
```

**Production usage example:** `format()` with zero-padded numeric specifiers (`%02d`, `%03d`) is the standard way to generate consistent, sortable resource names across `count`/`for_each`-created resources (e.g., `"subnet-%02d"` producing `subnet-01`, `subnet-02`, ... rather than `subnet-1`, `subnet-2`, ..., `subnet-10` which sorts incorrectly as plain strings).

**Common errors:** `format()` argument count/type mismatches (`format("%d", "not-a-number")`) produce `Error: Invalid function argument — Cannot convert "not-a-number" to number`; the format verb (`%d` vs `%s`) must match the actual argument's convertible type.

### 5.2 Collection Functions

**Purpose:** Transform, combine, filter, and inspect lists, maps, and sets without writing manual loops.

**Syntax:**

```hcl
merge(maps...)
lookup(map, key, default)
flatten(list_of_lists)
```

**Example usage and expected output:**

```hcl
locals {
  default_tags = {
    ManagedBy   = "terraform"
    Environment = var.environment
  }
  final_tags = merge(local.default_tags, var.extra_tags)
}
```

```bash
$ terraform console
> merge({ManagedBy = "terraform"}, {Team = "platform", ManagedBy = "manual-override"})
{
  "ManagedBy" = "manual-override"
  "Team"      = "platform"
}
```

**Production usage example:** `merge(local.default_tags, var.extra_tags)` is the near-universal pattern for letting a module apply organization-standard default tags while still allowing callers to add or override specific tags — later arguments to `merge()` win on key conflicts, which is why defaults are always passed first and overrides last.

**Common errors:** `merge()` requires all arguments to be maps (or objects with compatible attribute sets) — passing a `list` accidentally (`merge(local.tags, ["a", "b"])`) produces `Error: Invalid function argument — argument must be a map`.

### 5.3 Type Conversion and Error-Safety Functions: `try()` and `can()`

**Purpose:** Handle values that might be missing, null, or invalid without the configuration failing outright — the idiomatic replacement for relying on `&&`/`||` short-circuiting ([§18](./Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md)).

**Syntax:**

```hcl
try(expression_1, expression_2, ..., fallback)
can(expression)
```

**Example usage and expected output:**

```hcl
locals {
  # falls back to "t3.micro" if var.instance_config or its "type" key is missing/null
  instance_type = try(var.instance_config.type, "t3.micro")

  # boolean check: does this expression evaluate without error?
  is_valid_cidr = can(cidrhost(var.cidr_block, 0))
}
```

```bash
$ terraform console
> try(var.missing_var.some_attr, "fallback")
"fallback"
> can(tonumber("not-a-number"))
false
```

**Production usage example:** `try()` is the standard pattern for consuming optional nested attributes from data sources or complex object variables without needing an explicit null-check ternary for every access — e.g., safely reading an optional tag from a data source result that may or may not have that tag set. `can()` is the standard building block for custom variable validation rules ([§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)), where a validation condition needs to check "is this value even the right shape" before checking its content.

**Common errors:** `try()` evaluates its arguments **in order** and returns the first one that doesn't produce an error — a common mistake is putting a fallback literal _before_ a real expression, causing the real expression to never be attempted; the fallback must always be last.

## 6. Production Usage Notes

- Function calls are pure and side-effect-free by design — no built-in function can, for example, write a file or make a network call as a side effect (functions like `file()` _read_ local files at plan time but don't mutate anything); this determinism is what keeps `plan` safely re-runnable and idempotent.
- Some functions (`timestamp()`, `uuid()`) are explicitly **non-deterministic** across runs and Terraform intentionally restricts where they can be used (they can't be used in a way that would require a resource to be recreated purely due to their changing value on every plan) — a documented exception to the "pure function" mental model worth knowing.
- `terraform console` ([§28](../Part4/Section-28-Part4-terraform-console-and-terraform-graph.md)) should be the default way to prototype any non-trivial function composition before pasting it into a `.tf` file — catching a function's exact argument order/type expectations interactively is far faster than a `plan`/`apply` cycle.

## 7. Security Considerations

- `file()` and `filebase64()` read local files at plan time and embed their content directly into the plan/state — never point these at files containing secrets outside of an already-secured secrets pipeline, since that content then lives in state exactly like any other resource attribute ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md), secrets in state).
- `sensitive()` (a function, distinct from the `sensitive = true` variable/output attribute) can be used to mark an arbitrary expression's result as sensitive for display purposes — useful when composing a sensitive value from function calls that wouldn't otherwise inherit sensitivity automatically.
- Hash and crypto functions (`sha256`, `md5`, `bcrypt`) are available for computing checksums (e.g., triggering resource replacement when file content changes via `filesha256()`) but are not a substitute for a real secrets management pipeline ([§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md)–[§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)) when it comes to actually protecting credential material.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                      | Likely Cause                                                                                                      | Resolution Path                                                                                                                   |
| ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `Error: Invalid function argument`                                           | Argument's actual type doesn't match the function's expected type                                                 | Check the function's documented signature; convert explicitly with `tostring()`/`tonumber()`/etc.                                 |
| `merge()` produces unexpected values for a key                               | Multiple maps share a key; a later argument silently overrode an earlier one                                      | Check argument order — `merge()` resolves conflicts left-to-right, later wins                                                     |
| `try()` always returns the fallback, even when the "real" value should exist | Real expression's error is happening for a reason other than the assumed one (e.g., a typo in the attribute path) | Test the real expression alone in `terraform console` to see its actual error                                                     |
| Function call errors only during `apply`, not `plan`                         | Function depends on a value only known after a resource is created (e.g., a computed attribute)                   | This is expected for "known after apply" values; re-run `plan` after the dependent resource exists, or restructure the dependency |

## 9. Best Practices

- Prototype non-trivial function compositions in `terraform console` before writing them into `.tf` files.
- Use `merge()` with defaults first, overrides last, as the standard pattern for tag/config merging.
- Use `try()`/`can()` instead of relying on `&&`/`||` short-circuiting for any expression that might legitimately fail on missing/invalid input.
- Reach for a built-in function before reaching for a hand-rolled `for` expression — the standard library covers the overwhelming majority of common transformations more concisely and more readably.

## 10. Common Anti-Patterns / Mistakes

- **Reinventing a built-in function with a manual `for` expression** (e.g., manually looping to deduplicate a list instead of calling `distinct()`) — more code, more room for bugs, no benefit.
- **Putting the fallback value first in a `try()` call** — this causes the intended primary expression to never actually be attempted, silently masking real errors.
- **Using `file()`/`filebase64()` on files containing raw secrets** without routing them through a proper secrets pipeline first — the content ends up embedded in state exactly like any other value.
- **Overusing `can()` to silently swallow every possible error** rather than validating inputs meaningfully — `can()` used everywhere turns real configuration bugs into silent, hard-to-diagnose fallbacks.

## 11. Interview Questions

**🎯 Beginner:** _"Can you write a custom function in Terraform's language?"_
**Model answer:** No — HCL has a fixed, built-in standard library of functions defined by Terraform core; there's no way to define a new function within the language itself. Any transformation not covered by a built-in function must be built by composing existing functions and expressions, often with a `for` expression.
_What the interviewer is probing for:_ A very common assumption from engineers coming from general-purpose languages — confirming the candidate knows this limitation exists and plans around it.

**🎯 Intermediate:** _"Explain what `merge({a=1, b=2}, {b=3, c=4})` returns and why."_
**Model answer:** It returns `{a=1, b=3, c=4}`. `merge()` combines all given maps into one; when the same key appears in multiple arguments, the value from the **later** argument in the call wins. This is why the conventional pattern is `merge(defaults, overrides)` — defaults first, so any caller-supplied override naturally takes precedence.
_What the interviewer is probing for:_ Concrete, correct understanding of conflict-resolution order in `merge()`, since getting the argument order backwards silently produces the opposite of the intended behavior.

**🎯 Senior:** _"When would you use `try()` versus a ternary with an explicit null check, and what's the practical difference?"_
**Model answer:** A ternary with a null check (`var.x != null ? var.x.attr : "default"`) still requires the accessed expression to be structurally safe to evaluate _given_ the null check passed — it doesn't protect against a deeper structural issue like a missing map key or an out-of-range index, and as covered in [§18](./Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md), relying on `&&`/short-circuit-adjacent patterns for safety isn't reliably guaranteed in HCL's evaluation model. `try()` instead attempts the real expression and catches _any_ error during its evaluation, falling through to the next argument — it's a more general and more robust guard, especially for deeply nested or dynamically-shaped data (e.g., attributes from a data source that may or may not be present depending on the underlying resource's actual configuration). I default to `try()` for anything beyond a simple, single-level null check.
_What the interviewer is probing for:_ Nuanced understanding that `try()` catches structural/type errors generally, not just null values, and knowing when the extra generality is worth reaching for.

**🎯 Architect:** _"A module you're reviewing has a 40-line nested `for` expression that manually replicates what `flatten()` + `distinct()` + `merge()` would do in three lines. How do you approach the review, and what's the underlying principle?"_
**Model answer:** I'd flag it directly and propose the built-in composition as a replacement, explaining the underlying principle: Terraform's standard library functions are tested, documented, and instantly recognizable to any Terraform engineer reading the code — a hand-rolled equivalent is a maintenance liability (it needs its own comments to explain what a one-line function call would communicate for free) and a higher-risk-of-bugs surface, since it's new code instead of a well-exercised built-in. The broader principle for code review is: any time custom logic is reimplementing something in the standard library, that's almost always a sign to check the function reference first — and if I don't recognize the pattern immediately, that's itself useful signal that a built-in probably exists and the author didn't know to look for it.
_What the interviewer is probing for:_ Whether the candidate treats "know the standard library well" as a real code-quality lever in review, not just a personal productivity trick — this is a common real-world review comment in mature Terraform codebases.

## 12. Common Misconceptions

1. **"You can write custom functions in Terraform."** You cannot — the function library is fixed and built into Terraform core; all transformations must compose existing functions.
2. **"`merge()`'s argument order doesn't matter."** It does — later arguments override earlier ones on key conflicts; getting the order backwards silently inverts intended precedence.
3. **"Functions can have side effects."** They're pure by design (with narrow, documented exceptions like `timestamp()`/`uuid()` being non-deterministic, not side-effecting) — no built-in function writes files or makes mutating calls as a side effect.
4. **"`try()` only helps with null values."** It catches any evaluation error on its arguments, including type mismatches, out-of-range indices, and missing map keys — not just nulls.

## 13. 🔑 Key Takeaways

- Terraform's function library is fixed and built-in; there is no way to define custom functions, so fluency with the standard library directly determines how concisely and safely configuration can be written.
- `merge()` resolves key conflicts with later arguments winning — always pass defaults first, overrides last.
- `try()` and `can()` are the idiomatic, reliable way to handle potentially-missing or potentially-invalid values, replacing unsafe reliance on `&&`/`||` short-circuiting.
- Functions are pure and side-effect-free by design, with a narrow set of documented non-deterministic exceptions (`timestamp()`, `uuid()`) that Terraform restricts from driving resource replacement.
- `terraform console` is the fastest feedback loop for prototyping function calls before committing them to configuration.

## 14. Related Concepts & What's Next

[§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md) covers `for` expressions and splat expressions, the general-purpose iteration construct that's frequently combined with the functions covered here (e.g., `[for x in var.list : upper(x)]`). [§19](./Section-19-Part3-String-Interpolation-and-Templating-heredoc-templatefile.md) covered templating functions like `format()` in the specific context of string generation. [§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md) builds heavily on `can()` for validation conditions. [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) expands on the `file()`/`sensitive()` security notes above in full depth.

**Next Section:** [§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md) — `Section-21-Part3-for-Expressions-and-Splat-Expressions.md`
