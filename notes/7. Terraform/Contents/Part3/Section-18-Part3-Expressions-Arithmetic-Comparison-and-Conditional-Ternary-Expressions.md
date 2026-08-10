# Section 18 (Part 3): Expressions: Arithmetic, Comparison, and Conditional (Ternary) Expressions

## 1. Definition

**Plain language:** An expression is anything on the right-hand side of an argument's `=` that produces a value — a literal, a reference to another value, a calculation, a comparison, or a choice between two values based on a condition. Terraform expressions look and behave a lot like expressions in mainstream programming languages, just without loops or statements — everything is a value-producing expression, evaluated once per plan.

**Precise definition:** HCL expressions are the constructs Terraform evaluates to produce the value assigned to an argument. They include: **arithmetic operators** (`+ - * / %`), **comparison operators** (`== != < > <= >=`), **logical operators** (`&& || !`), and the **conditional (ternary) expression** (`condition ? true_val : false_val`). Expressions can reference other values (variables, resource attributes, locals — via **reference expressions**), call functions ([§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md)), and combine arbitrarily via operator precedence rules matching standard mathematical convention. Every expression has exactly one evaluated type and value at plan time, computed from the current state of all values it depends on.

> 💡 **Tip:** There is no `if`/`else` statement in HCL — only the ternary expression `condition ? true_val : false_val`. If you find yourself wanting branching logic beyond a single condition, that's usually a sign you actually want a `for` expression with a filter ([§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md)) or a `lookup()`/map-based dispatch, not nested ternaries.

## 2. Why This Matters

- Nearly every non-trivial argument value in real Terraform code is an expression, not a bare literal — conditional resource sizing, computed tags, and environment-dependent defaults are all built from the operators covered here.
- The ternary expression is the _only_ branching construct in HCL; recognizing this early prevents wasted time hunting for an `if` block that doesn't exist.
- Comparison and logical operators are the backbone of variable validation conditions ([§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) and `for` expression filter clauses ([§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md)) — getting operator precedence and short-circuit behavior wrong produces subtly incorrect plans, not obvious syntax errors.
- Misreading `count = condition ? 1 : 0` (a near-universal conditional-resource-creation idiom, [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)) as unfamiliar syntax is a common beginner blocker that disappears the moment ternary syntax is internalized.

## 3. Prerequisites and Dependencies

Requires [§15](./Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md) (block/argument grammar — expressions are what appears after `=`) and [§17](./Section-17-Part3-Data-Types-Primitives-Collections-list-map-set-Structural-object-tuple.md) (the type system these operators produce and consume). This section is a direct prerequisite for [§19](./Section-19-Part3-String-Interpolation-and-Templating-heredoc-templatefile.md) (string interpolation embeds expressions), [§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md) (functions are called within expressions), [§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md) (`for` expressions use conditional filters built from these same comparison/logical operators), and [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) (the `count = condition ? 1 : 0` conditional-resource idiom).

## 4. Architecture / Conceptual Diagram

```hcl
# ── Arithmetic ─────────────────────────────────────────────
subnet_count = length(var.availability_zones) * 2      # multiplication
cidr_offset  = var.base_cidr_block + local.index_offset # addition

# ── Comparison ─────────────────────────────────────────────
is_large_env = var.instance_count > 10                 # bool: true/false

# ── Logical ───────────────────────────────────────────────
needs_ha = var.environment == "production" && var.instance_count > 1

# ── Conditional (ternary) ───────────────────────────────────
#        condition                 ?   true_value    :  false_value
instance_type = var.environment == "production" ? "m5.large" : "t3.micro"

#  Common production idiom: conditional resource creation
resource "aws_instance" "bastion" {
  count = var.enable_bastion ? 1 : 0     # 1 instance if true, 0 (none) if false
  # ...
}
```

```text
Operator precedence (highest to lowest), matching standard convention:
  1. !  -  (unary not, unary minus)
  2. *  /  %
  3. +  -
  4. >  >=  <  <=
  5. ==  !=
  6. &&
  7. ||
  8. ? :          (ternary, evaluated last)
```

## 5. Hands-On

### 5.1 Arithmetic Expressions

**Purpose:** Compute derived numeric values — counts, offsets, CIDR math — from variables and other references.

**Syntax:**

```hcl
<expression> ::= <expr> ("+" | "-" | "*" | "/" | "%") <expr>
```

**Example usage and expected output:**

```bash
$ terraform console
> 10 % 3
1
> length(["a","b","c"]) * 2
6
> 2 + 2 * 3
8
```

**Production usage example:** Subnet CIDR allocation commonly uses arithmetic combined with `cidrsubnet()` ([§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md)) — e.g., computing how many subnets fit a VPC block based on `var.subnet_count`, or deriving a numeric suffix for resource naming from `count.index + 1` so names start at 1 instead of 0.

**Common errors:** `Error: Unsuitable value type` when attempting arithmetic on a non-numeric value that can't implicitly convert (e.g., adding a number to a list) — arithmetic operators require both operands to be numbers (or convertible to numbers), not any type.

### 5.2 Comparison and Logical Expressions

**Purpose:** Produce boolean values used in conditionals, variable validation, and `for` expression filters.

**Syntax:**

```hcl
<expr> ("==" | "!=" | "<" | ">" | "<=" | ">=") <expr>
<expr> ("&&" | "||") <expr>
"!" <expr>
```

**Example usage and expected output:**

```bash
$ terraform console
> var.environment == "production"
true
> var.instance_count > 0 && var.instance_count <= 10
true
> !contains(["dev", "staging"], var.environment)
true
```

**Production usage example:** Variable validation blocks ([§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) rely entirely on expressions that evaluate to a boolean — e.g., `condition = var.instance_count > 0 && var.instance_count <= 100` enforces a bounded, positive instance count directly at plan time, before any resource is even considered for creation.

**Common errors:** Comparing values of different types (`var.count == "3"` where `var.count` is `number`) can succeed via implicit conversion in some cases but fails with `Error: Invalid template interpolation value` or a type mismatch in others — explicit `tostring()`/`tonumber()` conversion ([§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md)) removes the ambiguity entirely.

### 5.3 Conditional (Ternary) Expressions

**Purpose:** Choose between two values based on a single boolean condition — the only branching construct in HCL.

**Syntax:**

```hcl
<condition> ? <true_expr> : <false_expr>
```

**Example usage and expected output:**

```hcl
# variables.tf
variable "environment" {
  type = string
}

# main.tf
locals {
  instance_type = var.environment == "production" ? "m5.large" : "t3.micro"
  instance_count = var.environment == "production" ? 3 : 1
}

resource "aws_instance" "app" {
  count         = local.instance_count
  instance_type = local.instance_type
  ami           = "ami-0c55b159cbfafe1f0"
}
```

```bash
$ terraform plan -var="environment=production"
  # local.instance_type  = "m5.large"
  # local.instance_count = 3
Plan: 3 to add, 0 to change, 0 to destroy.
```

**Production usage example:** `count = var.enable_feature ? 1 : 0` is the single most common conditional-resource-creation idiom in real Terraform code — it's how a resource can be entirely present or entirely absent based on a boolean flag, since HCL has no `if` block to conditionally skip a resource declaration outright (full treatment of `count`-based conditional creation in [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)).

**Common errors:** Both branches of a ternary must produce **type-compatible** results — `condition ? "a" : 5` (string vs. number) can trigger `Error: Inconsistent conditional result types` in strict contexts, though Terraform will attempt unification where a sensible common type exists; when branches return structurally different collection/object types, this fails outright and the branches must be made consistent (e.g., both `object({...})` with the same attributes).

## 6. Production Usage Notes

- Ternary expressions nest, but nesting more than one level (`a ? b : c ? d : e`) is rarely worth the readability cost — a `lookup()` against a map keyed by the discriminating value is almost always clearer once there are more than two outcomes.
- `&&` and `||` **do not short-circuit the way some languages guarantee** in the presence of errors on the unevaluated branch — Terraform's expression evaluator generally evaluates both operands, so relying on short-circuiting to "avoid" an error-producing expression on one side (e.g., `var.list != null && var.list[0] == "x"` hoping the index avoids evaluation when null) is not a safe pattern; use `try()` or `coalesce()` ([§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md)) instead for that purpose.
- Conditional expressions are evaluated fresh on every `plan`, so a ternary driven by a data source's current value can change a plan's outcome run-to-run even with no configuration changes — a source of "drift-like" plan diffs worth understanding when a condition depends on external, mutable data.

## 7. Security Considerations

- Conditional logic that gates security-relevant resources (e.g., `count = var.enable_public_access ? 1 : 0` for a public-facing resource) puts real security posture behind a boolean variable — such variables deserve explicit, reviewed defaults (defaulting to `false`/restrictive) rather than defaulting to the permissive option "for convenience."
- Comparison-based validation conditions ([§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) are a cheap, plan-time security control — e.g., rejecting a CIDR block that isn't sufficiently restrictive before any network resource is ever created.

## 8. Common Troubleshooting Scenarios

| Symptom                                              | Likely Cause                                                                   | Resolution Path                                                                  |
| ---------------------------------------------------- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------- |
| `Error: Inconsistent conditional result types`       | Ternary's two branches produce incompatible types                              | Make both branches return the same type/shape explicitly; use `tostring()`/casts |
| `Error: Unsuitable value type` on arithmetic         | One operand isn't numeric and can't implicitly convert                         | Convert explicitly with `tonumber()`, or check the source value's actual type    |
| Ternary condition evaluates unexpectedly across runs | Condition depends on a data source or external value that changed between runs | Trace the condition's inputs; consider pinning or caching the driving value      |
| Boolean expression using `&&`/`                      |                                                                                | ` still errors on "unreached" side                                               | Assuming short-circuit evaluation avoids an error on the untaken branch | Use `try()` or restructure with `coalesce()`/`can()` instead of relying on short-circuiting |

## 9. Best Practices

- Use ternaries for genuinely binary choices; switch to `lookup()` against a map, or a `for` expression, once there are more than two outcomes.
- Keep both ternary branches the same declared type explicitly, even when Terraform could infer a common type, for clarity and to avoid `Inconsistent conditional result types` errors as the configuration evolves.
- Use `try()`/`can()` ([§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md)) rather than relying on `&&`/`||` short-circuit behavior to guard against errors from a potentially-null or potentially-invalid expression.
- Extract non-trivial conditional expressions into a named `local` value ([§43](../Part6/Section-43-Part6-Local-Values-Use-Cases-and-Best-Practices.md)) rather than inlining a long ternary directly into a resource argument — it documents intent and is reusable across multiple resources.

## 10. Common Anti-Patterns / Mistakes

- **Nesting multiple ternaries** (`a ? b : c ? d : e ? f : g`) to emulate a switch statement — technically valid but a significant readability regression; a map lookup expresses the same intent far more clearly.
- **Relying on `&&`/`||` short-circuiting to prevent an error** on an unevaluated branch — not a guaranteed pattern in HCL; use `try()` instead.
- **Comparing values across types without explicit conversion** and depending on implicit conversion succeeding — works until it doesn't, and the failure mode is a confusing type error far from the actual root cause.
- **Inlining a complex conditional directly in a resource argument** instead of naming it as a `local` — makes the resource block harder to read and the condition impossible to reuse across multiple resources.

## 11. Interview Questions

**🎯 Beginner:** _"How do you write conditional logic in Terraform, given that HCL has no `if` statement?"_
**Model answer:** Terraform provides the ternary conditional expression, `condition ? true_value : false_value`, which is the only branching construct in the language. It's most commonly used to conditionally set an argument's value, or combined with `count` (`count = condition ? 1 : 0`) to conditionally create or omit an entire resource.
_What the interviewer is probing for:_ Basic fluency with the language's one branching construct, and awareness that there's no block-level `if`.

**🎯 Intermediate:** _"What happens if the two branches of a ternary expression return different types?"_
**Model answer:** Terraform attempts to unify the branch types where a sensible common type exists (e.g., a number and a string may unify to string in some contexts), but when the branches are structurally incompatible — different object attribute sets, or a list vs. a map — it produces `Error: Inconsistent conditional result types` at plan time. The fix is to make both branches explicitly return the same type, often via explicit conversion functions.
_What the interviewer is probing for:_ Whether the candidate has actually hit and debugged this specific, very common error, not just used ternaries in the happy path.

**🎯 Senior:** _"Explain why `var.list != null && var.list[0] == "x"` is not a safe pattern in HCL, and what you'd use instead."_
**Model answer:** In many mainstream languages, `&&` guarantees left-to-right short-circuit evaluation, so if the first operand is false the second is never evaluated. HCL's evaluator does not reliably guarantee this in all contexts — both operands can be evaluated during graph evaluation, meaning `var.list[0]` can still error (index out of range on a null/empty list) even though the intent was to guard against exactly that. The safer pattern is `try(var.list[0], null) == "x"` or restructuring the check using `length(var.list) > 0 ? var.list[0] == "x" : false`, both of which avoid depending on evaluation order guarantees the language doesn't make.
_What the interviewer is probing for:_ Deep, battle-tested knowledge of an HCL-specific gotcha that trips up engineers coming from general-purpose languages with guaranteed short-circuit semantics.

**🎯 Architect:** _"You're reviewing a module with a five-level nested ternary controlling instance sizing across environments. What's your architectural recommendation, and why?"_
**Model answer:** Replace it with a lookup against a map keyed by environment: `local.instance_type = lookup(var.instance_type_map, var.environment, "t3.micro")`, with `instance_type_map` defined as a `local` or variable mapping each environment name to its instance type, plus a sensible default. This is strictly more maintainable — adding a new environment means adding one map entry instead of restructuring nested conditional logic, it's trivially testable/reviewable at a glance, and it eliminates the risk of a ternary branch-type mismatch entirely. Nested ternaries beyond one level are a code smell that almost always indicates the underlying problem is actually a discrete-value dispatch problem, which maps and lookups solve more naturally than chained conditionals.
_What the interviewer is probing for:_ Whether the candidate defaults to "more elegant HCL" over "objectively more maintainable structure" — recognizing when a language feature is being used past its comfortable complexity ceiling is a senior-level signal.

## 12. Common Misconceptions

1. **"HCL has an `if`/`else` block like other languages."** It doesn't — the ternary expression is the only conditional construct; there's no statement-level branching.
2. **"`&&` and `||` always short-circuit safely."** Not reliably guaranteed in HCL's evaluation model — use `try()` for expressions that might error on one branch.
3. **"Ternary branches can freely mix types."** They must resolve to a compatible/unifiable type, or the plan fails with `Inconsistent conditional result types`.
4. **"Arithmetic operators work on any value Terraform can display as a number-like thing."** They require genuinely numeric (or number-convertible) operands — a string that merely _looks_ numeric still needs explicit `tonumber()` in strict contexts.

## 13. 🔑 Key Takeaways

- HCL expressions cover arithmetic (`+ - * / %`), comparison (`== != < > <= >=`), logical (`&& || !`), and the single conditional construct: the ternary (`condition ? true : false`).
- The ternary is HCL's _only_ branching construct — there is no `if`/`else` block; more than one level of nested ternary is a strong signal to switch to a map lookup instead.
- `&&`/`||` are not a reliable substitute for null/error guarding — use `try()`/`can()` for that purpose instead of depending on short-circuit evaluation order.
- Both branches of a ternary must resolve to a compatible type, or the plan fails with a precise, catchable error.
- `count = condition ? 1 : 0` is the standard idiom for conditionally creating an entire resource, and is foundational to understanding [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)'s resource meta-argument coverage.

## 14. Related Concepts & What's Next

[§19](./Section-19-Part3-String-Interpolation-and-Templating-heredoc-templatefile.md) covers string interpolation, which embeds these same expressions inside string templates via `${...}`. [§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md) covers the built-in functions (`try`, `can`, `coalesce`, `lookup`) referenced here as safer alternatives to relying on operator short-circuiting. [§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md) covers `for` expressions, whose optional filter clause (`if <condition>`) uses exactly the comparison/logical operators introduced here. [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) and [§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md) apply ternary and boolean expressions respectively to conditional resource creation and variable validation in full production depth.

**Next Section:** [§19](./Section-19-Part3-String-Interpolation-and-Templating-heredoc-templatefile.md) — `Section-19-Part3-String-Interpolation-and-Templating-heredoc-templatefile.md`
