# Section 43 (Part 6): Local Values: Use Cases and Best Practices

## 1. Definition

**Plain language:** Local values (`locals`) are named expressions you compute once inside a configuration and reuse elsewhere by name, instead of repeating the same calculation or string-building logic in every resource block that needs it. They're not an input (nobody assigns them from outside) and not an output (they're not automatically exposed) — they're purely an internal convenience for keeping a configuration DRY and readable.

**Precise definition:** A **local value** is declared inside a `locals` block, which can contain any number of named expressions, each referencing variables, resource attributes, data source attributes, other locals, or literal values. Once declared, a local is referenced elsewhere in the configuration as `local.<name>`. Unlike variables, locals have no `type`, `default`, or `description` argument — they are always fully computed from an expression, always internal to the module (never externally assignable, never automatically exposed as a module interface the way a variable or output is), and can reference each other freely as long as there's no circular reference.

> 💡 **Tip:** A good rule of thumb: if a value needs to come from outside the module, it's a variable ([§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)). If a value needs to go outside the module, it's an output ([§42](./Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md)). If a value is purely computed for internal reuse and neither of those applies, it's a local.

## 2. Why This Matters

- **Eliminating repeated expressions.** A naming convention like `"${var.environment}-${var.project}-app"` used in a dozen resource blocks is a maintenance hazard if it's typed out a dozen times — a single `local.name_prefix` computed once and referenced everywhere means changing the convention is a one-line edit.
- **Readability of complex expressions.** A nested `for` expression ([§21](../Part3/Section-21-Part3-for-Expressions-and-Splat-Expressions.md)) or conditional ([§18](../Part3/Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md)) computing a merged tag map is far more readable referenced as `local.common_tags` in twenty resource blocks than inlined twenty times.
- **A clean seam for computed defaults and derived logic.** Locals are the natural place to compute a value that depends on conditional logic over one or more variables — for instance, deriving an instance size from an `environment` variable via a lookup map, without cluttering every consuming resource block with that logic.
- **Avoiding accidental drift between resource blocks.** If the same computed value is needed in five places and it's inlined five times, a future edit to the logic can easily update four of the five and silently miss one — a single local referenced five times cannot drift internally.
- **A staging point before exposing a value as an output.** Locals are frequently the last computation step before a value is handed to an `output` block ([§42](./Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md)), keeping the output declaration itself simple.

## 3. Prerequisites and Dependencies

This section assumes the expression and function vocabulary from [§18](../Part3/Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md) (arithmetic/comparison/conditional expressions), [§19](../Part3/Section-19-Part3-String-Interpolation-and-Templating-heredoc-templatefile.md) (string interpolation), [§20](../Part3/Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md) (built-in functions), and [§21](../Part3/Section-21-Part3-for-Expressions-and-Splat-Expressions.md) (`for` expressions) — locals are frequently where those expressions actually get used in practice. It also builds on [§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) (input variables) and [§42](./Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md) (output values), since locals typically sit between the two: computed from variables, consumed by resources or exposed via outputs.

## 4. Architecture / Conceptual Diagram

```text
   VARIABLES (external input) ──┐
                                  │
   DATA SOURCES (external read) ─┼──►  locals { ... }  ──►  resource blocks
                                  │      (internal,              (consume
   OTHER LOCALS ───────────────┘      computed once,           local.* freely)
                                       referenced by name)
                                          │
                                          ▼
                                    output blocks (§42)
                                    (locals are a common
                                     staging point before
                                     exposing a final value)

   locals {
     name_prefix = "${var.environment}-${var.project}"      # from variables
     common_tags = merge(var.tags, { ManagedBy = "terraform" })
     instance_size = lookup(local.size_map, var.environment, "t3.micro")
     size_map = {                                            # locals referencing
       dev  = "t3.micro"                                     # other locals is fine,
       prod = "t3.large"                                     # as long as it's not
     }                                                        # circular
   }
```

- Locals are purely a lexical convenience layer inside a module — they never cross a module boundary in either direction; a caller cannot set a local, and a local is never automatically visible outside the module the way an output is.
- A `locals` block can reference other locals freely (in any declaration order — Terraform resolves the dependency graph, not file order), but a circular reference (local A defined in terms of local B which is defined in terms of local A) is a hard error.

## 5. Hands-On

### 5.1 Basic Local Values for Naming and Tagging

**Purpose:** Show the most common real-world use case: a shared naming prefix and a common tag map.

**Syntax:**

```hcl
locals {
  name_prefix = "${var.environment}-${var.project}"

  common_tags = merge(var.tags, {
    Environment = var.environment
    ManagedBy   = "terraform"
  })
}

resource "aws_instance" "app" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"
  tags          = merge(local.common_tags, { Name = "${local.name_prefix}-app" })
}

resource "aws_security_group" "app" {
  name = "${local.name_prefix}-sg"
  tags = local.common_tags
}
```

**Example usage and expected output:**

```bash
$ terraform plan
  # aws_instance.app will be created
      + tags = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
          + "Name"        = "dev-payments-app"
        }
  # aws_security_group.app will be created
      + name = "dev-payments-sg"
      + tags = {
          + "Environment" = "dev"
          + "ManagedBy"   = "terraform"
        }

Plan: 2 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Nearly every production module declares a `locals` block with a `name_prefix`-style value and a `common_tags` map right at the top of `main.tf`, referenced by every subsequent resource — this is one of the most universal Terraform idioms in practice.

**Common errors:** Defining `local.name_prefix` in terms of `local.common_tags` and `local.common_tags` in terms of `local.name_prefix` simultaneously produces `Error: Circular reference` — Terraform builds a dependency graph over locals just like resources, and a cycle is unresolvable.

### 5.2 Conditional and Lookup-Based Locals

**Purpose:** Show locals used to compute a derived value via conditional logic, keeping that logic out of resource blocks.

**Syntax:**

```hcl
locals {
  size_map = {
    dev     = "t3.micro"
    staging = "t3.medium"
    prod    = "t3.large"
  }

  instance_type = lookup(local.size_map, var.environment, "t3.micro")
  is_production = var.environment == "prod"
}

resource "aws_instance" "app" {
  instance_type         = local.instance_type
  monitoring            = local.is_production
  disable_api_termination = local.is_production
}
```

**Example usage and expected output:**

```bash
$ terraform plan -var="environment=prod"
  # aws_instance.app will be created
      + instance_type            = "t3.large"
      + monitoring               = true
      + disable_api_termination  = true

Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** A shared module used across dev/staging/prod computes environment-tier-dependent settings (instance size, backup retention, deletion protection) once via `locals`, keeping every resource block free of environment-conditional logic scattered throughout.

**Common errors:** Using `local.size_map[var.environment]` (direct index) instead of `lookup(local.size_map, var.environment, default)` fails with an unhandled-key error if `var.environment` doesn't match any map key exactly — `lookup()` with a default argument is the safer pattern for maps that might not cover every possible input.

### 5.3 Locals as a Staging Point Before Outputs

**Purpose:** Show a `locals` block computing a value that's then exposed via an `output`, keeping the output declaration itself simple.

**Syntax:**

```hcl
locals {
  connection_string = "postgresql://${aws_db_instance.main.username}@${aws_db_instance.main.endpoint}/${aws_db_instance.main.db_name}"
}

output "db_connection_string" {
  description = "Non-credential connection string for the app database"
  value       = local.connection_string
}
```

**Example usage and expected output:**

```bash
$ terraform apply
Outputs:

db_connection_string = "postgresql://app_user@app-db.abc123.us-east-1.rds.amazonaws.com/appdb"
```

**Production usage example:** Modules that need to compose a value from several resource attributes (a full URL, a formatted ARN, a combined identifier) almost always do that composition in a `locals` block first, then reference the finished local in a single-line `output` — separating "how it's computed" from "what's exposed."

**Common errors:** Inlining a long, multi-attribute string interpolation directly into an `output` block's `value` argument works functionally but makes the output declaration hard to read and hides the computation from anyone just skimming `outputs.tf` — extracting it to a named local is a readability best practice, not a functional requirement.

## 6. Production Usage Notes

- **Locals are file-location-agnostic but conventionally centralized.** They can be declared in any `.tf` file in the module (there's no requirement they live in one place), but most teams converge on a single `locals.tf` (or a `locals` block at the top of `main.tf`) for discoverability, mirroring the `variables.tf`/`outputs.tf` convention from [§16](../Part3/Section-16-Part3-Terraform-File-Structure-and-Conventions.md).
- **Locals aren't a substitute for variables when a value genuinely needs to be caller-configurable.** A common mistake is hardcoding a value in a local that should have been a variable with a default — the test is always "could a caller reasonably need to override this?"; if yes, it belongs in `variables.tf`, not `locals.tf`.
- **Overusing locals for values only ever referenced once provides no benefit** and adds a layer of indirection a reader has to trace — reserve locals for values that are either reused in multiple places or that meaningfully improve readability by being named, not for single-use trivial expressions.

## 7. Security Considerations

- Locals computed from sensitive variables inherit sensitivity for CLI-output purposes exactly like any other derived expression ([§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) — a `local.connection_string` built from a sensitive password is itself treated as sensitive by Terraform's redaction logic, and any output exposing it must be marked `sensitive` accordingly.
- Because locals are purely internal to a module, they're not a mechanism for restricting or exposing access to anything — they don't add or remove any security boundary by themselves; the security posture of the values they compute is inherited entirely from their inputs.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                     | Likely Cause                                                                                                                        | Resolution Path                                                                                                                                                                  |
| --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Error: Circular reference` involving one or more `local` names             | Two or more locals reference each other, directly or transitively, forming a cycle                                                  | Break the cycle by extracting the shared logic into a third local both can reference, or restructure the expressions                                                             |
| A local's computed value is wrong but the referenced variables look correct | The local's expression logic itself has a bug (wrong lookup key, wrong conditional), not the inputs                                 | Use `terraform console` ([§28](../Part4/Section-28-Part4-terraform-console-and-terraform-graph.md)) to evaluate the local's expression interactively and isolate the faulty step |
| Changing a local's expression unexpectedly changes many resources at once   | The local is widely referenced by design (e.g., `common_tags`), so a definition change legitimately propagates everywhere it's used | Expected behavior for a shared local — review the blast radius with `terraform plan` before applying, this is the intended trade-off of centralizing the value                   |

## 9. Best Practices

- Centralize locals in a dedicated `locals.tf` (or a clearly delimited block at the top of `main.tf`) so the module's computed-value layer is easy to find in one place.
- Use locals for any expression referenced more than once, or any expression complex enough that naming it improves readability, even if only referenced once.
- Keep the distinction between variables, locals, and outputs sharp: input from outside → variable; internal computation → local; output to outside → output — resist blurring these roles for convenience.

## 10. Common Anti-Patterns / Mistakes

- **Hardcoding a value in a local that should really be a variable.** If a caller might reasonably need to override it, it belongs in `variables.tf` with a `default`, not baked into `locals.tf` as a fixed computation.
- **Building deeply nested, hard-to-read local expressions without breaking them into smaller named intermediate locals.** A single local computed through five chained function calls and three ternaries is harder to debug than the same logic split across three or four smaller, individually named locals.
- **Duplicating the same computed expression across multiple resource blocks instead of extracting a local.** This is precisely the maintenance hazard locals exist to prevent, and it's a common code-review finding in Terraform configurations.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a local value and a variable in Terraform?"_
**Model answer:** A variable ([§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)) is an input — its value comes from outside the configuration, via a default, a CLI flag, a `.tfvars` file, or an environment variable. A local value is purely internal — it's always fully computed from an expression inside the configuration itself, never assigned externally, and it's not automatically exposed to anything outside the module. Locals exist to avoid repeating the same computed expression in multiple places.
_What the interviewer is probing for:_ Basic clarity on the three-way distinction between variables (input), locals (internal computation), and outputs (external exposure).

**🎯 Intermediate:** _"When would you extract an expression into a local value rather than just repeating it inline in each resource block that needs it?"_
**Model answer:** Whenever the same expression is used in more than one place, extracting it to a local ensures every consumer stays in sync if the logic ever changes — inlining it repeatedly risks one occurrence getting updated while another is missed. It's also worth extracting even a single-use expression into a named local if doing so meaningfully improves readability — for example, naming a complex conditional or lookup so a resource block reads as `local.instance_type` instead of a multi-line inline expression.
_What the interviewer is probing for:_ Whether the candidate applies locals for both reuse and readability, not just mechanical deduplication.

**🎯 Senior:** _"A module has a `locals` block where `local.a` references `local.b`, `local.b` references `local.c`, and `local.c` references `local.a`. What happens, and how would you resolve it?"_
**Model answer:** Terraform builds a dependency graph over local values the same way it does for resources, and a cycle like this is a hard error (`Circular reference`) — it can't determine an evaluation order since each depends transitively on itself. Resolving it requires breaking the cycle structurally: identifying the piece of logic that's genuinely shared and extracting it into a fourth local (or a variable) that the other three can each depend on without depending on each other, or reconsidering whether the three values should really be mutually dependent at all — in practice, a genuine three-way circular dependency usually indicates the computation should be restructured rather than patched.
_What the interviewer is probing for:_ Understanding that locals participate in the same dependency-graph model as resources, and the ability to reason about breaking a cycle rather than just naming the error.

**🎯 Architect:** _"You're reviewing a large module where `locals.tf` has grown to 200 lines of deeply chained computed values, several of which are only referenced once. How do you approach cleaning this up?"_
**Model answer:** First, distinguish genuinely reused locals (referenced by multiple resource blocks — these earn their place) from single-use locals that exist only because someone defaulted to "always name intermediate values" — the latter can often be inlined back into their sole consumer without losing meaningful readability, trimming the file significantly. Second, look for locals that are actually acting as configuration rather than computation — a hardcoded lookup map or a value that never changes based on any variable is a signal it might belong as a variable default instead, giving future callers the ability to override it that a local silently forecloses. Third, break deeply chained computations into logically grouped sub-blocks (naming intermediate locals meaningfully rather than as `temp1`, `temp2`) so the dependency chain reads top-to-bottom as a narrative rather than requiring the reader to trace references backward. Finally, if the module genuinely has 200 lines of distinct computed concerns, that's often itself a signal the module is doing too much and could be decomposed into smaller, more focused modules ([§62](../Part8/Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md)) each with a much shorter local computation surface.
_What the interviewer is probing for:_ Whether the candidate can distinguish genuine reuse from habitual over-abstraction, and connects excessive local complexity to a broader module-design smell rather than treating it as purely a style issue.

## 12. Common Misconceptions

1. **"Locals can be set from the command line like variables."** They cannot — locals have no external assignment mechanism whatsoever; they are always fully computed from their declared expression.
2. **"Locals are automatically exposed as part of a module's interface."** They are not — only explicitly declared `output` blocks ([§42](./Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md)) cross a module boundary; a local, no matter how important internally, is invisible to a calling module unless separately surfaced via an output.
3. **"Using a local is always strictly better than inlining an expression."** For a truly single-use, simple expression, extracting a local can add indirection without a readability benefit — the decision should weigh actual reuse and clarity, not apply as a blanket rule.
4. **"Locals must all be declared in one single `locals` block."** A module can have multiple `locals` blocks across multiple files (or even the same file); Terraform merges them into one namespace — the single-`locals.tf`-file convention is a team convention for discoverability, not a language requirement.

## 13. 🔑 Key Takeaways

- Local values are internal, always-computed expressions referenced as `local.<name>` — never externally assignable and never automatically exposed outside the module.
- The clean mental model: variables are input, locals are internal computation, outputs are external exposure — keeping these roles distinct avoids confusing a module's design.
- Locals build their own dependency graph exactly like resources; circular references between locals are a hard error requiring restructuring.
- Extract a local for any expression that's reused in multiple places, or complex enough that naming it improves readability, even if only used once.
- A sprawling, deeply chained `locals` block is often a signal the module itself is trying to do too much and could benefit from decomposition.

## 14. Related Concepts & What's Next

[§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) and [§42](./Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md) cover the two boundary-crossing counterparts to locals — variables (input) and outputs (output) — that this section is deliberately framed against. [§18](../Part3/Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md)–[§21](../Part3/Section-21-Part3-for-Expressions-and-Splat-Expressions.md) cover the expression, interpolation, function, and `for`-expression vocabulary locals most commonly compute with. [§44](./Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md) shifts focus to variable validation — a different mechanism for enforcing correctness at the input boundary, complementary to the internal computation locals provide.

**Next Section:** [§44](./Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md) — `Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md`
