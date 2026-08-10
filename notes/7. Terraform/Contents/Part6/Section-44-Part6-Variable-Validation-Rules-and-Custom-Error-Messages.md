# Section 44 (Part 6): Variable Validation Rules and Custom Error Messages

## 1. Definition

**Plain language:** Type constraints ([§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)) catch a caller passing the wrong _kind_ of value — a number where a string was expected. Validation rules catch a caller passing the wrong _value_ of the right kind — a string that's type-correct but semantically invalid, like an AWS region name that doesn't exist, or a port number outside the valid range. A `validation` block lets a module author write that check directly into the variable declaration, with a custom error message that tells the caller exactly what went wrong.

**Precise definition:** A `validation` block, nested inside a `variable` block, contains a `condition` argument (a boolean expression, typically referencing the variable itself via `var.<name>`) and an `error_message` argument (a string shown to the caller when `condition` evaluates to `false`). A single `variable` block can contain multiple `validation` blocks, each checked independently; if any fails, `terraform plan`/`apply` halts with that block's specific `error_message`, before any resource is touched. Validation runs after type conversion but before the value is used anywhere else in the configuration, making it the earliest point at which a module author can enforce domain-specific correctness beyond what the type system alone expresses.

> 💡 **Tip:** Write the `error_message` as if you're the one who'll be paged when a caller gets it wrong at 2 a.m. — `"Invalid value"` tells them nothing; `"instance_type must be one of: t3.micro, t3.small, t3.medium (got: ${var.instance_type})"` tells them exactly what to fix without opening the module source.

## 2. Why This Matters

- **Failing fast with an actionable message, before any API call.** Without validation, a bad value (an out-of-range port, a malformed CIDR block) often isn't caught until the cloud provider's API rejects it mid-apply, producing a cryptic provider-level error and a partially-applied plan — validation catches it at plan time, before anything is touched.
- **Encoding domain knowledge the type system can't express.** `type = string` can't express "must be a valid AWS region name" or "must be between 1 and 65535" — validation is the mechanism for exactly this class of constraint.
- **Self-documenting, enforced module contracts.** A `validation` block with a clear `error_message` is simultaneously documentation (what values are acceptable) and enforcement (a caller literally cannot proceed with an invalid value) — a `description` alone is only documentation, easily ignored.
- **Reducing support burden for widely-used modules.** A module consumed by many teams benefits enormously from validation that catches common mistakes immediately with a clear message, rather than every team individually rediscovering the same constraint through a confusing downstream failure.
- **Cross-field consistency checks.** A `validation` block's `condition` can reference other variables, not just the one it's attached to, enabling checks like "if `enable_multi_az` is true, `instance_count` must be at least 2" that a single variable's type alone could never express.

## 3. Prerequisites and Dependencies

This section builds directly on [§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) (variable declaration, where `validation` is one of the arguments a `variable` block accepts) and assumes the expression vocabulary from [§18](../Part3/Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md) (comparison operators) and [§20](../Part3/Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md) (built-in functions, many of which — `contains()`, `can()`, `regex()` — are the actual building blocks of validation conditions). [§45](./Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md) (complex variable types) frequently combines with validation, since object-typed variables often need cross-attribute checks that only a `validation` block can express.

## 4. Architecture / Conceptual Diagram

```text
   VARIABLE RESOLUTION AND VALIDATION ORDER

   1. Value assigned (§40 precedence: -var > .tfvars > env > default)
              │
              ▼
   2. Type conversion / type-checking against declared `type` (§39)
              │  fails here → "Invalid value for input variable" (type mismatch)
              ▼
   3. validation { condition = ... } blocks evaluated, IN DECLARATION ORDER
              │  fails here → custom error_message shown, halts BEFORE
              │  the resource graph (§11) is even built — no API calls made
              ▼
   4. Value is now available as var.<name> to the rest of the configuration


   variable "port" {
     type = number
     validation {
       condition     = var.port > 0 && var.port <= 65535
       error_message = "port must be between 1 and 65535 (got: ${var.port})."
     }
   }
```

- Validation strictly follows type checking — a `validation` block never runs against a value that failed the `type` check, since that value never reaches this stage at all.
- Multiple `validation` blocks on one variable are all evaluated (not short-circuited on the first pass) so plan output can potentially surface more than one failing constraint per run, though the exact reporting behavior may show the first failure depending on Terraform version.

## 5. Hands-On

### 5.1 A Basic Range/Allowed-Value Validation

**Purpose:** Show the fundamental `validation` block syntax enforcing a numeric range.

**Syntax:**

```hcl
variable "port" {
  type        = number
  description = "Application listen port"

  validation {
    condition     = var.port > 0 && var.port <= 65535
    error_message = "port must be between 1 and 65535 (got: ${var.port})."
  }
}
```

**Example usage and expected output:**

```bash
$ terraform plan -var="port=99999"
Error: Invalid value for variable

  on variables.tf line 1:
   1: variable "port" {

port must be between 1 and 65535 (got: 99999).

This was checked by the validation rule at variables.tf:5,3-13.
```

**Production usage example:** Any variable representing a network port, a percentage, a count with meaningful upper/lower bounds, or a string from a known finite set of valid values is a strong candidate for a `validation` block enforcing that constraint explicitly, rather than relying on the provider API to reject bad input later.

**Common errors:** Writing `condition = var.port > 0` alone (forgetting the upper bound) technically validates but leaves a real gap — a `validation` block only enforces exactly what its `condition` expresses; it's easy to write a check that's correct but incomplete.

### 5.2 Allowed-Value Sets with `contains()`

**Purpose:** Show validating a string variable against a fixed, meaningful set of acceptable values.

**Syntax:**

```hcl
variable "environment" {
  type        = string
  description = "Deployment environment"

  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be one of: dev, staging, prod (got: \"${var.environment}\")."
  }
}
```

**Example usage and expected output:**

```bash
$ terraform plan -var="environment=production"
Error: Invalid value for variable

environment must be one of: dev, staging, prod (got: "production").

This was checked by the validation rule at variables.tf:6,3-13.
```

**Production usage example:** This is the single most common validation pattern in production modules — enforcing that an "environment," "tier," or "region" style variable can only take one of a known, finite set of values, catching typos like `"production"` instead of `"prod"` immediately.

**Common errors:** Hardcoding the allowed-values list separately in both a `validation` block and a `lookup()` map elsewhere in the module (as in [§43](./Section-43-Part6-Local-Values-Use-Cases-and-Best-Practices.md)'s `size_map` example) risks the two falling out of sync if one is updated and the other isn't — keeping such lists in one place (a `local`, [§43](./Section-43-Part6-Local-Values-Use-Cases-and-Best-Practices.md)) referenced by both is a more maintainable pattern for larger modules.

### 5.3 Format Validation with `regex()` and Cross-Variable Validation

**Purpose:** Show format validation via `can(regex(...))` and a validation condition referencing more than one variable.

**Syntax:**

```hcl
variable "cidr_block" {
  type        = string
  description = "CIDR block for the VPC"

  validation {
    condition     = can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/[0-9]{1,2}$", var.cidr_block))
    error_message = "cidr_block must be a valid CIDR notation, e.g. 10.0.0.0/16."
  }
}

variable "enable_multi_az" {
  type    = bool
  default = false
}

variable "instance_count" {
  type    = number
  default = 1

  validation {
    condition     = !var.enable_multi_az || var.instance_count >= 2
    error_message = "instance_count must be at least 2 when enable_multi_az is true."
  }
}
```

**Example usage and expected output:**

```bash
$ terraform plan -var="cidr_block=not-a-cidr"
Error: Invalid value for variable

cidr_block must be a valid CIDR notation, e.g. 10.0.0.0/16.

$ terraform plan -var="enable_multi_az=true" -var="instance_count=1"
Error: Invalid value for variable

instance_count must be at least 2 when enable_multi_az is true.
```

**Production usage example:** Modules provisioning networking resources routinely validate CIDR-format variables with `can(regex(...))` since a malformed CIDR block would otherwise fail deep inside a provider API call with a much less specific error; cross-variable validations like the multi-AZ example encode business rules that no single variable's type alone could express.

**Common errors:** Forgetting to wrap `regex()` in `can()` means a non-matching string causes `regex()` itself to raise an error rather than returning a value the `condition` can evaluate to `false` — `can()` converts that raised error into a clean `false`, which is exactly what a `validation` condition needs to handle gracefully.

## 6. Production Usage Notes

- **Validation blocks cannot reference resources or data sources** — only other variables and the variable's own value, plus built-in functions. This is a deliberate constraint: variable resolution happens before the resource graph exists, so nothing resource-derived is available yet.
- **`error_message` should always include the actual invalid value** where practical (via string interpolation) so the caller doesn't have to cross-reference the plan output separately to see what they passed — this is a small addition that meaningfully reduces back-and-forth during debugging.
- **Validation is not a substitute for provider-side constraints** — a `validation` block can check a CIDR block is syntactically well-formed, but it can't check whether that CIDR block actually conflicts with an existing VPC's address space; some correctness checks are only knowable by the provider at apply time.

## 7. Security Considerations

- Validation is a useful defense-in-depth layer for catching obviously wrong values before they reach a provider API, but it is not a security control by itself — a syntactically valid but maliciously chosen value (an overly permissive CIDR block that's still well-formed) passes format validation just fine; broader guardrails belong in policy-as-code (Sentinel/OPA, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) or static analysis (tfsec/Checkov, [§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md)).
- Validation `error_message` strings are plain, unredacted text — never interpolate a sensitive variable's raw value into an `error_message`, since the message is printed in full to the CLI/logs regardless of any `sensitive` marking on the variable itself ([§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)'s redaction applies to normal plan/apply output, not to validation error text, which is a distinct code path).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                       | Likely Cause                                                                                                       | Resolution Path                                                                                                                                                                     |
| ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Error: Invalid value for variable` with a generic, unhelpful message         | `error_message` wasn't written descriptively, or interpolation of the actual invalid value was omitted             | Rewrite `error_message` to state the exact rule and include the offending value via interpolation                                                                                   |
| A validation condition using `regex()` errors instead of failing cleanly      | `regex()` was used without wrapping in `can()`, so a non-matching input raises an error instead of returning false | Wrap the `regex()` call in `can(...)` so a non-match becomes a clean `false` the condition can evaluate                                                                             |
| A cross-variable validation on `var.a` doesn't seem to see the latest `var.b` | Both variables resolved correctly, but the condition logic itself has an error (inverted boolean, wrong operator)  | Use `terraform console` ([§28](../Part4/Section-28-Part4-terraform-console-and-terraform-graph.md)) to evaluate the exact `condition` expression interactively against known inputs |

## 9. Best Practices

- Add a `validation` block for any variable where an invalid but type-correct value would otherwise fail confusingly deep inside a provider API call — ports, CIDR blocks, enumerated string sets, and numeric ranges are the most common candidates.
- Write every `error_message` to state the rule explicitly and include the actual invalid value via interpolation, so a caller never has to guess what was wrong.
- Keep validation logic and any related lookup tables (like an allowed-values list also used elsewhere) in sync by centralizing shared lists in a `local` ([§43](./Section-43-Part6-Local-Values-Use-Cases-and-Best-Practices.md)) that both the validation condition and any dependent logic reference.

## 10. Common Anti-Patterns / Mistakes

- **Writing a vague `error_message` like `"Invalid input"` with no detail on what's actually required.** This defeats the entire point of validation over a plain type error — the caller still has to go read the module source to understand the rule.
- **Using `regex()` without `can()`, causing the validation itself to error out ungracefully** on non-matching input instead of surfacing the intended custom message.
- **Over-relying on validation for checks that genuinely require provider-side knowledge** (e.g., "does this AMI ID actually exist") — a `validation` block can check format and range, not live provider-side reality; conflating the two leads to false confidence that a passing plan guarantees apply-time success.

## 11. Interview Questions

**🎯 Beginner:** _"What does a `validation` block inside a `variable` declaration do?"_
**Model answer:** It lets a module author enforce a custom rule on the variable's value beyond what its declared `type` alone can express — for example, that a number falls within a specific range, or a string matches one of a fixed set of allowed values. It has a `condition` (a boolean expression) and an `error_message` shown to the caller if the condition evaluates to false; if it fails, `terraform plan`/`apply` halts immediately with that message, before any resource is touched.
_What the interviewer is probing for:_ Basic understanding that validation is a runtime check on the value, layered on top of (not replacing) type checking.

**🎯 Intermediate:** _"Why would you use `can(regex(...))` in a validation condition instead of just `regex(...)` directly?"_
**Model answer:** `regex()` raises an error when the input doesn't match the pattern, rather than returning a false-y value — if used directly as (or inside) a `condition` expression, a non-matching input would cause the validation evaluation itself to error out ungracefully instead of cleanly failing with the intended custom `error_message`. Wrapping it in `can()` catches that raised error and converts it into a plain `false`, which the `condition` boolean can then evaluate normally, letting the custom `error_message` actually surface as intended.
_What the interviewer is probing for:_ Practical familiarity with the `can()`/`try()` error-handling pattern in HCL, which comes up frequently beyond just validation blocks.

**🎯 Senior:** _"Design a validation strategy for a variable representing a list of CIDR blocks, where you need to ensure each one is individually valid and that none of them overlap with each other."_
**Model answer:** Two separate `validation` blocks address two separate concerns cleanly. The first checks each element's format individually — something like `condition = alltrue([for c in var.cidr_blocks : can(regex("^([0-9]{1,3}\\.){3}[0-9]{1,3}/[0-9]{1,2}$", c))])` using a `for` expression ([§21](../Part3/Section-21-Part3-for-Expressions-and-Splat-Expressions.md)) combined with `alltrue()` to apply the same per-element check across the whole list. The second checks for pairwise non-overlap, which is harder to express cleanly in HCL alone — a nested `for` expression comparing every pair, or, more practically, delegating true CIDR-overlap arithmetic to a purpose-built function if the provider ecosystem or a helper module offers `cidrsubnets`/`cidrhost`-style utilities, since raw prefix-length arithmetic in a validation condition can get unreadable fast. In practice, for genuinely complex cross-element consistency logic like this, some teams accept that format-only validation happens in Terraform and defer true overlap detection to a policy-as-code check (Sentinel/OPA, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) that can run more general logic, rather than pushing an over-complicated expression into a single `validation` block.
_What the interviewer is probing for:_ Whether the candidate can decompose a compound validation need into separate, individually-readable checks and recognizes the practical limits of HCL-expressible validation logic.

**🎯 Architect:** _"A widely-used internal module has been live for two years with minimal input validation. Teams keep hitting confusing mid-apply failures caused by bad input values. How do you approach retrofitting validation without breaking existing callers?"_
**Model answer:** Start by mining the module's actual failure history — provider-level errors, support tickets, incident postmortems — to identify which invalid inputs have actually caused real pain, rather than validating everything speculatively; this focuses effort on the highest-value checks first. Add `validation` blocks incrementally, and for each one, test it against every known existing caller's current `.tfvars`/values before merging, since a validation rule that's stricter than what's already in production use will break someone's next `plan` the moment the module version is bumped — this is a breaking change requiring the same versioning discipline as any other module interface change ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)), even though the variable's `type` itself hasn't changed. Favor permissive-but-informative rules initially (broad allowed ranges, clear messages) over maximally strict ones, and tighten over subsequent versions once callers have had a chance to adapt. Pair the Terraform-level validation with clear release notes and, where the organization has it, a policy-as-code layer (Sentinel/OPA, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) for checks that need to span multiple modules or reference live infrastructure state that variable-level validation alone can't see. Finally, treat the rollout itself as a communication problem as much as a technical one — validation failures are only an improvement over confusing provider errors if callers understand why the new failure appeared and how to fix it quickly.
_What the interviewer is probing for:_ Awareness that adding validation to an established, widely-consumed module is itself a versioned, potentially breaking interface change requiring careful rollout — not just a technical exercise in writing correct `condition` expressions.

## 12. Common Misconceptions

1. **"Validation blocks can check anything about the final infrastructure state."** They can only evaluate the variable's own value and other variables — no resource or data source access is available at variable-resolution time, so live infrastructure checks (e.g., "does this AMI exist") are out of scope.
2. **"A `type` constraint and a `validation` block do the same job."** Type constraints check the _shape_ of a value (string vs. number vs. list); validation checks the _content_ of a value within that shape (a string that's the right kind of string) — they're complementary, not redundant.
3. **"If `regex()` doesn't match, the validation just fails normally."** Without `can()`, a non-matching `regex()` call raises an error that short-circuits the whole condition evaluation ungracefully, rather than producing a clean `false` — `can()` is required for regex-based validations to behave as expected on non-matching input.
4. **"Adding a `validation` block to an existing module variable is always a safe, backwards-compatible change."** For any caller currently passing a value that happens to violate the new rule, it's a breaking change — the same caution applied to type or default changes applies here too.

## 13. 🔑 Key Takeaways

- A `validation` block enforces content-level correctness on a variable's value (range, format, allowed set, cross-variable consistency) beyond what its `type` alone can express.
- Validation runs after type checking and before the resource graph is built — a failing validation halts the run before any API call is made, with a custom, caller-facing `error_message`.
- `can(regex(...))` (or `can()` around any expression that might raise an error) is the standard pattern for format validation that fails cleanly instead of erroring ungracefully.
- Validation conditions can reference other variables, enabling cross-field consistency checks a single variable's type could never express.
- Adding or tightening validation on an already-consumed module variable is a breaking-change consideration, not a purely additive improvement — existing callers may already be passing values the new rule would reject.

## 14. Related Concepts & What's Next

[§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) introduced the `validation` argument briefly as part of the full `variable` block syntax; this section covers it in depth. [§18](../Part3/Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md) and [§20](../Part3/Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md) supply the comparison operators and built-in functions (`contains()`, `can()`, `regex()`, `alltrue()`) that validation conditions are built from. [§45](./Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md) covers complex `object`-typed variables, which frequently pair with cross-attribute validation blocks for the kind of structural consistency checks a flat type alone can't express. [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) covers Sentinel/OPA policy-as-code, the organization-wide analog to per-module validation for checks that need to span multiple configurations or reference live state.

**Next Section:** [§45](./Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md) — `Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md`
