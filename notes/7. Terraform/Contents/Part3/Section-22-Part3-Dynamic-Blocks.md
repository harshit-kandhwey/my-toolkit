# Section 22 (Part 3): Dynamic Blocks

## 1. Definition

**Plain language:** Some resources need a variable number of repeated nested blocks — a security group might need anywhere from zero to a dozen ingress rules, and you don't want to hand-write a separate block for every possible count. A `dynamic` block lets you generate those repeated nested blocks programmatically from a list or map, the same way a `for` expression generates a list of values, except it generates _blocks_ instead.

**Precise definition:** A `dynamic` block is a special Terraform-only construct (not part of core HCL itself, but a Terraform-specific language feature) that generates zero or more instances of a given nested block type at plan time, by iterating over a collection. Its syntax is `dynamic "<block_name>" { for_each = <collection>  content { ... } }`, where `<block_name>` is the actual nested block type being generated (e.g., `ingress` inside `aws_security_group`), `for_each` supplies the iteration source (a list, set, or map), and the `content` block body defines what each generated instance looks like, referencing the current iteration item via the special `<block_name>.value` (and `.key`, when iterating a map) object — by default named after the block, or renamed via the optional `iterator` argument.

> 💡 **Tip:** `dynamic` blocks generate _nested blocks_, not top-level resources — that's what `for_each` on a `resource` block already does ([§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md)). Reach for `dynamic` specifically when a single resource needs a variable number of a specific nested block type inside it (ingress rules, tags-as-blocks, lifecycle hooks) — never for creating multiple separate resource instances.

## 2. Why This Matters

- Any provider resource with repeatable nested blocks (security group `ingress`/`egress` rules, load balancer listener rules, IAM policy statements expressed as blocks) needs `dynamic` the moment the number of those blocks isn't fixed at authoring time — this is one of the most common "advanced HCL" needs in real infrastructure code.
- Overusing `dynamic` blocks where a simpler resource-level `for_each`/`count` would do is a common and well-documented anti-pattern that makes modules harder to read — knowing precisely when `dynamic` is the _right_ tool (vs. when it's over-engineering a fixed set of blocks) is a real production skill.
- `dynamic` blocks interact with all the type/collection/`for`-expression mechanics from [§17](./Section-17-Part3-Data-Types-Primitives-Collections-list-map-set-Structural-object-tuple.md)–[§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md) simultaneously — they're a natural capstone that tests whether those concepts are genuinely understood together, not just individually.
- Misconfiguring a `dynamic` block's `for_each` source (passing a `list` where element order matters when a `map`/`set` was expected, or vice versa) can produce subtly wrong generated blocks that only surface in `terraform plan` diffs, not obvious errors.

## 3. Prerequisites and Dependencies

Hard prerequisite: [§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md) (`for` expressions) — `dynamic` blocks' `for_each` iteration and `content` templating are a direct extension of `for`-expression mechanics applied to blocks instead of values. Also builds on [§15](./Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md) (block/argument grammar — a `dynamic` block's `content {}` is itself an ordinary nested block). Directly related to [§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md) (resource-level `for_each` meta-argument) — the two are easily confused but operate at different levels (whole resource vs. nested block within one resource). Prerequisite understanding for [§79](../Part11/Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md) (networking-as-code patterns rely heavily on dynamic ingress/egress blocks).

## 4. Architecture / Conceptual Diagram

```hcl
variable "ingress_rules" {
  type = list(object({
    description = string
    from_port   = number
    to_port     = number
    protocol    = string
    cidr_blocks = list(string)
  }))
}

resource "aws_security_group" "web" {
  name = "web-sg"

  dynamic "ingress" {                    # generates N "ingress" nested blocks
    for_each = var.ingress_rules          # ← iteration source (list here)

    content {                            # ← template for EACH generated block
      description = ingress.value.description   # "ingress" = default iterator name
      from_port   = ingress.value.from_port      #   (matches the dynamic block's label)
      to_port     = ingress.value.to_port
      protocol    = ingress.value.protocol
      cidr_blocks = ingress.value.cidr_blocks
    }
  }
}
```

```text
                      ┌──────────────────────────────────────────┐
 var.ingress_rules ──►│  dynamic "ingress" { for_each = ... }    │
  (list of 3 objects) │        │                                 │
                      │        ▼  one content{} instance PER     │
                      │   element of for_each, in order          │
                      └──────────────────────────────────────────┘
                               │
                               ▼
        resulting aws_security_group.web ends up with THREE
        actual "ingress { ... }" nested blocks, indistinguishable
        at the provider level from hand-written ones.
```

## 5. Hands-On

### 5.1 A Basic Dynamic Block from a List

**Purpose:** Generate a variable number of identically-shaped nested blocks from a list variable.

**Syntax:**

```hcl
dynamic "<block_name>" {
  for_each = <collection>
  content {
    <argument> = <block_name>.value.<attribute>
  }
}
```

**Example usage and expected output:**

```hcl
variable "ingress_rules" {
  type = list(object({
    from_port = number
    to_port   = number
    protocol  = string
  }))
  default = [
    { from_port = 22, to_port = 22, protocol = "tcp" },
    { from_port = 443, to_port = 443, protocol = "tcp" },
  ]
}

resource "aws_security_group" "web" {
  name = "web-sg"

  dynamic "ingress" {
    for_each = var.ingress_rules
    content {
      from_port   = ingress.value.from_port
      to_port     = ingress.value.to_port
      protocol    = ingress.value.protocol
      cidr_blocks = ["0.0.0.0/0"]
    }
  }
}
```

```bash
$ terraform plan
  # aws_security_group.web will be created
  + resource "aws_security_group" "web" {
      + ingress {
          + from_port = 22
          + to_port   = 22
          + protocol  = "tcp"
        }
      + ingress {
          + from_port = 443
          + to_port   = 443
          + protocol  = "tcp"
        }
    }
```

**Production usage example:** This is the standard pattern for security group modules where callers supply a variable-length list of desired ingress rules — the module author never needs to hand-write a fixed number of `ingress` blocks, and the resource correctly grows or shrinks its rule set as the input list changes.

**Common errors:** Referencing `ingress.value` when the `dynamic` block's label is actually something else (e.g., `dynamic "egress"` but still writing `ingress.value` inside its `content`) produces `Error: Reference to undeclared resource` or similar — the implicit iterator variable name always matches the `dynamic` block's own label unless overridden with `iterator`.

### 5.2 Dynamic Blocks from a Map, and the `iterator` Argument

**Purpose:** Iterate a map (accessing both key and value) and use a custom iterator name for clarity in nested/multiple `dynamic` blocks.

**Syntax:**

```hcl
dynamic "<block_name>" {
  for_each = <map_collection>
  iterator = <custom_name>
  content {
    <argument> = <custom_name>.key
    <argument> = <custom_name>.value
  }
}
```

**Example usage and expected output:**

```hcl
variable "environment_tags" {
  type = map(string)
  default = {
    Owner = "platform-team"
    Tier  = "backend"
  }
}

resource "aws_autoscaling_group" "app" {
  # ...
  dynamic "tag" {
    for_each = var.environment_tags
    iterator = t
    content {
      key                 = t.key
      value               = t.value
      propagate_at_launch = true
    }
  }
}
```

```bash
$ terraform console
> [for k, v in {Owner = "platform-team", Tier = "backend"} : {key = k, value = v}]
[
  {
    "key"   = "Owner"
    "value" = "platform-team"
  },
  {
    "key"   = "Tier"
    "value" = "backend"
  },
]
```

**Production usage example:** `aws_autoscaling_group`'s `tag` block, which requires each tag as a separate nested block (unlike most resources' simple `tags = {}` map argument), is a canonical real-world reason `dynamic` blocks exist at all — this specific resource cannot accept a plain tags map for autoscaling-propagated tags, only repeated `tag { }` blocks, making `dynamic` the only clean way to drive it from a map variable.

**Common errors:** Omitting `iterator` when nesting two `dynamic` blocks of different types that both default to a same-shaped implicit variable name is rarely an actual naming collision (each `dynamic` block's default iterator is scoped to its own label), but explicit `iterator` naming is still strongly recommended once `dynamic` blocks are nested inside each other, since the default name becomes genuinely ambiguous to a human reader at that point.

### 5.3 Conditionally Omitting a Dynamic Block Entirely

**Purpose:** Generate zero instances of a nested block when a feature is disabled, without a separate resource or ternary gymnastics.

**Syntax:**

```hcl
dynamic "<block_name>" {
  for_each = <condition> ? <collection> : []
  content { ... }
}
```

**Example usage and expected output:**

```hcl
variable "enable_logging" {
  type    = bool
  default = false
}

resource "aws_s3_bucket" "data" {
  bucket = "my-app-data"

  dynamic "logging" {
    for_each = var.enable_logging ? [1] : []   # 1-element list "turns on" the block; empty list "turns it off"
    content {
      target_bucket = "my-app-logs"
      target_prefix = "log/"
    }
  }
}
```

```bash
$ terraform plan -var="enable_logging=false"
  # aws_s3_bucket.data will be created
  + resource "aws_s3_bucket" "data" {
      # (no "logging" block appears at all — zero instances generated)
    }
```

**Production usage example:** This `condition ? [single_item] : []` idiom is the standard way to make an entire optional nested block conditional on a boolean flag — much cleaner than duplicating the whole resource block behind a ternary, and the resulting resource has genuinely zero instances of that nested block type when disabled, not an empty/default one.

**Common errors:** Using `for_each = var.enable_logging ? {} : {}` (empty maps on both branches, a copy-paste mistake) silently produces zero blocks in both cases — always double-check both branches of the conditional actually differ.

## 6. Production Usage Notes

- `dynamic` blocks should generate their `for_each` source from a variable or local that's already the right shape (typically prepared with a `for` expression, [§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md)) — inlining a complex `for` expression directly as the `for_each` value makes the `dynamic` block itself much harder to read; extract it to a named `local` first.
- Terraform's own documentation explicitly recommends against using `dynamic` blocks purely for visual compactness when a resource's nested blocks are actually fixed and known in advance — hand-written repeated blocks are more readable and more directly diffable in `plan` output than a `dynamic` block whose generated content isn't visible in the source.
- `dynamic` blocks cannot be used to generate meta-argument-bearing constructs like `lifecycle {}` — `dynamic "lifecycle"` is not valid, since `lifecycle` is a meta-argument block interpreted by Terraform core itself ([§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md)), not an ordinary provider-schema nested block.

## 7. Security Considerations

- A `dynamic "ingress"` block driven by an unvalidated/unbounded caller-supplied list is a real security surface — without a variable validation rule ([§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) constraining CIDR ranges or port ranges, a module caller could accidentally (or maliciously) generate an overly permissive security group; validate the `for_each` source collection's contents, not just its shape.
- Because generated blocks are indistinguishable from hand-written ones in the actual provider API calls, `terraform plan` review is the only practical way to catch a `dynamic`-block-generated misconfiguration before `apply` — reviewers should expand and read generated block diffs in plan output with the same scrutiny as hand-written blocks, not less.

## 8. Common Troubleshooting Scenarios

| Symptom                                                            | Likely Cause                                                                           | Resolution Path                                                                                            |
| ------------------------------------------------------------------ | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| No nested blocks generated at all                                  | `for_each` source evaluated to an empty collection                                     | Check the source variable/local's actual value with `terraform console`                                    |
| `Error: Unsupported argument` inside a `dynamic` block's `content` | Argument name inside `content{}` doesn't match the actual nested block's schema        | Check the resource's provider documentation for the real nested block's argument names                     |
| Iterator reference (`ingress.value.x`) fails                       | Wrong implicit iterator name used, or `iterator` was set but old name still referenced | Match the reference to the `dynamic` block's label, or the explicit `iterator` name                        |
| Generated blocks appear in a different order than expected         | `for_each` source's element order isn't stable (e.g., iterating an unordered map/set)  | Use a `list` for order-sensitive generation, or accept that block order is cosmetic for most provider APIs |

## 9. Best Practices

- Reserve `dynamic` blocks for genuinely variable-count nested blocks; never use them to "avoid writing a few lines of HCL" for a fixed, known set of nested blocks.
- Prepare the `for_each` source as a named `local` using a `for` expression, rather than inlining complex transformation logic directly in the `dynamic` block's `for_each` argument.
- Set `iterator` explicitly whenever `dynamic` blocks are nested inside each other, even though it isn't strictly required for the outer/inner default names to avoid colliding.
- Validate the contents of any variable feeding a security-relevant `dynamic` block (ingress rules, IAM statements) with variable validation rules ([§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)), not just its type shape.

## 10. Common Anti-Patterns / Mistakes

- **Using `dynamic` for a small, fixed number of nested blocks known at authoring time** — pure over-engineering; hand-written blocks are more readable and directly reviewable in `plan` output.
- **Inlining a complex `for` expression directly as the `for_each` value** instead of extracting it to a named local — makes the `dynamic` block itself hard to audit at a glance.
- **Forgetting that `dynamic` generates nested blocks, not resource instances**, and reaching for `dynamic` when what's actually needed is resource-level `for_each`/`count` ([§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md)) to create multiple separate resources.
- **Not validating the `for_each` source's actual content** for security-relevant dynamic blocks (ingress/egress rules, IAM policy statements), only its type shape.

## 11. Interview Questions

**🎯 Beginner:** _"What problem does a `dynamic` block solve that a regular nested block can't?"_
**Model answer:** A regular nested block is fixed at authoring time — you hand-write exactly the blocks you want. A `dynamic` block generates a variable number of nested blocks of a given type at plan time, by iterating over a list or map, which is necessary when the number of nested blocks (like security group ingress rules) isn't known until the caller supplies their configuration.
_What the interviewer is probing for:_ Basic understanding of _why_ `dynamic` exists, not just its syntax.

**🎯 Intermediate:** _"What's the difference between a resource's `for_each` meta-argument and a `dynamic` block's `for_each` argument?"_
**Model answer:** Resource-level `for_each` ([§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md), [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)) creates multiple separate instances of an entire resource, each independently addressed and tracked in state. A `dynamic` block's `for_each` operates entirely _within_ a single resource instance, generating multiple copies of one specific nested block type inside that one resource — it has no effect on how many resources exist or how they're addressed in state; it only shapes the internal structure of one resource's configuration.
_What the interviewer is probing for:_ Whether the candidate can clearly distinguish resource-level replication from block-level replication — these are easily conflated by name (`for_each` appears in both) but operate at entirely different levels.

**🎯 Senior:** _"A teammate has converted every nested block in a module — including three fixed, never-changing `ingress` rules — into `dynamic` blocks for 'consistency.' How do you respond in review?"_
**Model answer:** I'd push back on that specific change. `dynamic` blocks exist to handle genuinely variable-count nested blocks; using them for a fixed, known set of blocks doesn't add consistency — it adds indirection. A reviewer (or future maintainer) now has to mentally "run" the `for_each` and `content` template to understand what blocks actually get generated, instead of just reading three plain `ingress { }` blocks directly. HashiCorp's own guidance is explicit about this: use `dynamic` only when the block set truly needs to vary based on input, not as a blanket style choice. I'd recommend reverting the fixed blocks back to hand-written form and reserving `dynamic` for the genuinely variable cases elsewhere in the module.
_What the interviewer is probing for:_ Judgment about appropriate tool usage and willingness to push back on "clever but unnecessary" abstraction in code review — a real, common review scenario.

**🎯 Architect:** _"You're designing a reusable security-group module that needs to support ingress rules, egress rules, and optionally VPC flow log configuration, all driven by caller input. How do you structure the `dynamic` block usage, and what do you validate?"_
**Model answer:** Structure: separate `dynamic "ingress"` and `dynamic "egress"` blocks, each driven by their own list-typed, `object`-shaped variable ([§17](./Section-17-Part3-Data-Types-Primitives-Collections-list-map-set-Structural-object-tuple.md), [§45](../Part6/Section-45-Part6-Complex-Variable-Types-Object-and-Nested-Structures.md)) prepared via `for` expressions into the exact shape the nested block schema expects, kept in named locals rather than inlined for auditability. The optional flow-log configuration uses the `condition ? [single_item] : []` idiom (§5.3 above) rather than a separate boolean-gated resource, keeping the module's interface to a single resource with conditional internal structure. On validation: every list-typed variable feeding a `dynamic` block gets explicit variable validation ([§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) — CIDR blocks checked with `can(cidrhost(...))`, port ranges bounded to 1–65535, protocol values restricted to an allowed set — because unlike a resource-level mistake (which at least shows up as an unexpected _resource_ in plan output), a bad value inside a `dynamic`-block-generated nested block can slip through as an unexpected but still "valid-looking" ingress rule that's easy to miss in a large plan diff. I'd also document the exact expected object shape for each list variable directly in its `description`, since the `dynamic` block's `content` template is the only place that shape is otherwise discoverable.
_What the interviewer is probing for:_ End-to-end module design thinking that connects `dynamic` blocks to variable typing, validation, and plan-reviewability — showing the candidate designs for the reviewer's and caller's experience, not just for correctness in the happy path.

## 12. Common Misconceptions

1. **"`dynamic` blocks create multiple resources."** They don't — they generate multiple instances of one _nested block type_ within a single resource; multiple resource instances come from resource-level `count`/`for_each` ([§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md)).
2. **"`dynamic` should be used for every nested block for consistency."** It should be reserved for genuinely variable-count blocks; using it for fixed, known blocks adds indirection without benefit.
3. **"The iterator variable name is always literally `each`."** It defaults to the `dynamic` block's own label (e.g., `ingress` for `dynamic "ingress"`), not a universal fixed name — `each` is the resource-level `for_each` iterator ([§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md)), a different construct entirely.
4. **"`dynamic` blocks can generate any kind of Terraform block, including meta-argument blocks like `lifecycle`."** They can't — `dynamic` only generates ordinary provider-schema nested blocks, not Terraform-core meta-argument blocks.

## 13. 🔑 Key Takeaways

- `dynamic "<block_name>" { for_each = ...  content { ... } }` generates a variable number of nested blocks of a specific type within a single resource — it operates at the nested-block level, not the resource level.
- The implicit iterator variable defaults to the `dynamic` block's own label; use the `iterator` argument to rename it, especially when nesting `dynamic` blocks.
- `condition ? [item] : []` is the standard idiom for conditionally generating zero or one instance of an entire optional nested block.
- Reserve `dynamic` for genuinely variable-count block sets — using it for fixed, known blocks is a documented anti-pattern that trades readability for unnecessary indirection.
- Because generated blocks are indistinguishable from hand-written ones at the provider level, `terraform plan` review remains the primary safety net for catching `dynamic`-block-driven misconfiguration.

## 14. Related Concepts & What's Next

[§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md) covers resource-level meta-arguments including `for_each`, the block-level counterpart's easily-confused-but-distinct sibling. [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) expands the `count` vs. `for_each` trade-off at the resource level in full depth. [§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md) covers the validation techniques recommended above for securing `dynamic`-block-driving variables. [§79](../Part11/Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md) applies `dynamic` blocks to real-world security group and networking modules across AWS/Azure/GCP.

**Next Section:** [§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md) — `Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md`
