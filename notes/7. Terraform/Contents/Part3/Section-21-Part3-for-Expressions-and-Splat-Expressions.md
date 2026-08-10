# Section 21 (Part 3): for Expressions and Splat Expressions

## 1. Definition

**Plain language:** A `for` expression is HCL's way of transforming one collection into another — "take this list of subnets and give me back a list of just their IDs" — without a `for` loop statement, since HCL has none. A splat expression (`[*]`) is a compact shortcut for the single most common case of that pattern: pulling one attribute out of every element of a list.

**Precise definition:** A **`for` expression** has the general form `[for <item> in <collection> : <expr>]` (producing a `list` or `tuple`) or `{for <key>, <val> in <collection> : <key_expr> => <val_expr>}` (producing a `map` or `object`), with an optional trailing `if <condition>` filter clause. It iterates every element of the source collection, applies the output expression to each, and optionally skips elements that fail the filter condition. A **splat expression**, `<list>[*].<attribute>`, is syntactic sugar equivalent to `[for item in <list> : item.<attribute>]` — it extracts one attribute from every element of a list in a single compact expression, and also has a **legacy single-value splat form** (`resource.attr.*.id`, historically used before `count`/`for_each` unification) that modern Terraform mostly supersedes with the `[*]` form working uniformly.

> 💡 **Tip:** If you're extracting one attribute from every item in a list, reach for splat (`list[*].id`) — it's shorter and immediately recognizable. The moment you need a _filter_, a _key transformation_, or output shaped as a _map_ instead of a list, you need the full `for` expression — splat can't do any of those.

## 2. Why This Matters

- `for_each` ([§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md), [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)) almost always consumes the output of a `for` expression to reshape a list into the map/set structure `for_each` requires — you cannot use `for_each` effectively at scale without fluency in `for` expressions.
- Splat expressions are the standard idiom for referencing "all the IDs from this `count`-created set of resources" (`aws_instance.web[*].id`) — an extremely common pattern anywhere `count` creates multiple resource instances.
- The `for` expression's map-producing form (`{for k, v in ... : k => v}`) is how most `for_each`-ready maps get built from raw lists in practice — this single syntax pattern shows up constantly in real modules.
- Getting the filter clause (`if condition`) or key-collision behavior wrong in a map-producing `for` expression is a common source of `Error: Duplicate object key` or silently-dropped elements — understanding the mechanics precisely prevents both.

## 3. Prerequisites and Dependencies

Directly builds on [§17](./Section-17-Part3-Data-Types-Primitives-Collections-list-map-set-Structural-object-tuple.md) (types — `for` expressions' output shape depends on list/map/set input types and the syntax used) and [§18](./Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md) (the `if` filter clause uses the same comparison/logical operators). Builds on [§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md) (function calls are commonly the output expression inside a `for`). This section is a hard prerequisite for [§22](./Section-22-Part3-Dynamic-Blocks.md) (dynamic blocks iterate via the same `for`-expression mental model) and [§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md)/[§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) (`for_each` almost always consumes a `for`-expression-shaped map or set).

## 4. Architecture / Conceptual Diagram

```hcl
# ── List-producing for expression ─────────────────────────
[for s in var.subnet_ids : upper(s)]
#   ^        ^                ^
#   |        |                └── output expression, applied per element
#   |        └── source collection
#   └── item variable name (yours to choose)

# ── With a filter clause ────────────────────────────────────
[for n in var.instance_counts : n if n > 0]     # skips elements where n <= 0

# ── Map-producing for expression (note the { } and =>) ───────
{for name, cfg in var.servers : name => cfg.instance_type}
#      ^      ^                    ^          ^
#      |      |                    |          └── value expression
#      |      |                    └── key expression
#      |      └── value variable (when iterating a map)
#      └── key variable (when iterating a map)

# ── Splat expression: shortcut for one-attribute extraction ──
aws_instance.web[*].id
# equivalent to:
[for instance in aws_instance.web : instance.id]
```

```text
Input type  →  for expression form           →  Output type
list/set    →  [for x in list : expr]         →  list/tuple
list/set    →  [for x in list : expr if cond] →  list/tuple (filtered)
map         →  [for k, v in map : expr]        →  list/tuple (over values, discarding keys unless used)
map         →  {for k, v in map : k => v}       →  map/object
list        →  {for i, x in list : x => i}       →  map/object (from a list, using index/value as key)
```

## 5. Hands-On

### 5.1 List-Producing `for` Expressions

**Purpose:** Transform every element of a collection into a new list, optionally filtering.

**Syntax:**

```hcl
[for <item> in <collection> : <expression>]
[for <item> in <collection> : <expression> if <condition>]
```

**Example usage and expected output:**

```bash
$ terraform console
> [for s in ["a", "b", "c"] : upper(s)]
[
  "A",
  "B",
  "C",
]
> [for n in [1, 2, 3, 4, 5] : n * 10 if n % 2 == 0]
[
  20,
  40,
]
```

**Production usage example:** Deriving a list of formatted names for `count`-created resources (`[for i in range(var.instance_count) : "web-${format("%02d", i + 1)}"]`) is a common pattern for generating deterministic, sortable instance names before those names are consumed by `for_each` ([§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md)) after conversion to a set.

**Common errors:** Forgetting the `if` filter is a boolean expression, not a value transformer — writing `[for n in list : n if n]` filters out falsy/zero values as a side effect of treating `n` as the condition, which is rarely the intended behavior; be explicit (`if n != 0`).

### 5.2 Map-Producing `for` Expressions

**Purpose:** Build a map (often specifically to feed `for_each`, [§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md)) from a list or another map, choosing both key and value expressions explicitly.

**Syntax:**

```hcl
{for <key>, <val> in <collection> : <key_expr> => <val_expr>}
{for <item> in <list> : <key_expr> => <val_expr>}
```

**Example usage and expected output:**

```hcl
variable "servers" {
  type = list(object({
    name          = string
    instance_type = string
  }))
}

locals {
  # turn a list of objects into a map keyed by name — for_each-ready
  servers_by_name = { for s in var.servers : s.name => s }
}
```

```bash
$ terraform console
> [for s in [{name = "web-01", instance_type = "t3.micro"}, {name = "web-02", instance_type = "t3.small"}] : s.name => s.instance_type]
# (map form requires { } braces, not [ ])
> {for s in [{name = "web-01", instance_type = "t3.micro"}] : s.name => s.instance_type}
{
  "web-01" = "t3.micro"
}
```

**Production usage example:** Converting a list-typed variable into a name-keyed map is the single most common `for` expression pattern preceding a `for_each` meta-argument ([§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md), [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)), because `for_each` requires a map or set of strings, not a list — this pattern (`{for x in var.list : x.name => x}`) appears in essentially every module that replaced `count` with `for_each` for stable per-instance addressing.

**Common errors:** `Error: Duplicate object key` occurs when the key expression produces the same value for two different source elements (e.g., two servers accidentally sharing the same `name`) — the map form requires unique keys, unlike the list form which has no such constraint.

### 5.3 Splat Expressions

**Purpose:** Compactly extract one attribute from every element of a list — the shorthand for the single most common `for` expression pattern.

**Syntax:**

```hcl
<list_expression>[*].<attribute>
```

**Example usage and expected output:**

```hcl
resource "aws_instance" "web" {
  count = 3
  ami   = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.micro"
}

output "all_instance_ids" {
  value = aws_instance.web[*].id
}
```

```bash
$ terraform apply
...
Outputs:
all_instance_ids = [
  "i-0abc123",
  "i-0def456",
  "i-0ghi789",
]
```

**Production usage example:** `aws_instance.web[*].id` (or `aws_instance.web[*].private_ip`) is the standard way to feed the IDs of every `count`-created instance into a downstream resource that needs the full list — e.g., registering every instance ID with a load balancer target group in one expression, without writing a full `for` expression for such a common case.

**Common errors:** Splat only works on values that are genuinely lists (or convertible to lists) — applying `[*]` to a single (non-`count`/`for_each`) resource reference is a common confusion; a resource without `count` or `for_each` is a single object, not a list, and doesn't need (or support) splat syntax at all.

## 6. Production Usage Notes

- `for` expressions inside `dynamic` blocks ([§22](./Section-22-Part3-Dynamic-Blocks.md)) reuse this exact same syntax to iterate the source collection that generates repeated nested blocks — mastering `for` here transfers directly.
- The map-producing form's key uniqueness requirement is a genuine design feature, not just a limitation — it's what guarantees the resulting map is safe to hand directly to `for_each`, since `for_each` itself requires unique keys for stable resource addressing.
- Nested `for` expressions (`[for outer in x : [for inner in outer.y : inner.z]]`) are valid but produce a list of lists — combine with `flatten()` ([§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md)) when a single flat list is actually wanted.

## 7. Security Considerations

- `for` expressions with filter clauses are commonly used to build allowlists/denylists dynamically (e.g., `[for cidr in var.all_cidrs : cidr if !contains(var.blocked_cidrs, cidr)]`) — as with any filtering logic, review the condition carefully since an inverted or incorrect condition can silently produce an overly permissive result rather than an error.
- Splat expressions on sensitive-attribute-bearing resources (e.g., extracting connection strings or generated passwords across a `count`-created set) inherit the same sensitivity-marking considerations as any other reference — verify sensitivity propagation rather than assuming it.

## 8. Common Troubleshooting Scenarios

| Symptom                                                 | Likely Cause                                                                                                                  | Resolution Path                                                                    |
| ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `Error: Duplicate object key`                           | Map-producing `for` expression's key expression isn't unique per element                                                      | Choose a genuinely unique key field, or dedupe the source data first               |
| `for` expression output is a list of lists unexpectedly | Nested `for` expressions without `flatten()`                                                                                  | Wrap the result in `flatten()` if a single flat list is intended                   |
| Splat expression returns an empty list                  | The underlying resource has `count = 0` (or an empty `for_each`)                                                              | Confirm the resource's count/for_each actually produced instances before splatting |
| `if` filter clause removes unintended elements          | Filter condition evaluates unexpected values as falsy (e.g., filtering on the item itself rather than an explicit comparison) | Write explicit boolean conditions (`if x != 0`, not `if x`)                        |

## 9. Best Practices

- Default to splat (`list[*].attr`) for simple single-attribute extraction; switch to a full `for` expression the moment filtering, key transformation, or map output is needed.
- Always give `for` expression item/key variables descriptive names (`for server in var.servers`, not `for x in var.servers`) — this matters more here than in most languages because `for` expressions are frequently nested and nameless single-letter variables become genuinely ambiguous.
- Use the map-producing `for` form as the standard way to prepare data for `for_each`, keeping the key expression obviously unique (a name, an ID) rather than a derived/computed value prone to collision.
- Combine `for` with `flatten()` explicitly whenever nesting, rather than relying on implicit flattening (which HCL doesn't do).

## 10. Common Anti-Patterns / Mistakes

- **Using `count` where the underlying data is naturally list-of-objects and a `for` expression could produce a clean `for_each`-ready map** — leads to fragile, index-based addressing instead of stable, name-based addressing (fully explored in [§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md)/[§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)'s `count` vs. `for_each` comparison).
- **Deeply nested `for` expressions (3+ levels) inline in a resource argument** — extract intermediate results into named `locals` ([§43](../Part6/Section-43-Part6-Local-Values-Use-Cases-and-Best-Practices.md)) so each transformation step is independently readable and testable via `terraform console`.
- **Using splat syntax on a resource without `count`/`for_each`** — unnecessary and confusing; a single resource reference doesn't need list-extraction syntax at all.
- **Relying on `if x` as a truthiness filter** instead of an explicit boolean comparison — HCL's implicit truthiness rules for non-boolean filter conditions are a frequent source of subtly wrong filtered results.

## 11. Interview Questions

**🎯 Beginner:** _"What does the splat expression `aws_instance.web[*].id` do?"_
**Model answer:** It extracts the `id` attribute from every element of `aws_instance.web` (which is a list of instances created via `count`), returning a list of all their IDs. It's shorthand for `[for instance in aws_instance.web : instance.id]`.
_What the interviewer is probing for:_ Basic recognition of one of the most common HCL idioms and its equivalence to the underlying `for` expression.

**🎯 Intermediate:** _"How do you convert a list of objects into a map suitable for `for_each`, and why is this necessary?"_
**Model answer:** Using a map-producing `for` expression: `{for item in var.list : item.unique_key => item}`. It's necessary because `for_each` requires a map or a set of strings — it cannot accept a bare list — so any list-shaped input data needs to be reshaped into a uniquely-keyed map first, typically keyed by a stable identifier like a name, before it can drive `for_each`-based resource creation.
_What the interviewer is probing for:_ Practical, hands-on fluency with the single most common `for`-expression-into-`for_each` pipeline pattern used throughout real Terraform code.

**🎯 Senior:** _"A map-producing `for` expression throws `Error: Duplicate object key`. Walk through how you'd debug it."_
**Model answer:** The key expression in the `for` is producing the same value for two or more elements of the source collection. I'd first inspect the source data directly in `terraform console` (e.g., print the list before the `for` expression) to find which elements share the offending key value, since the error itself doesn't name the colliding elements. Common root causes: the "unique" field chosen as the key isn't actually guaranteed unique by the data source or upstream system (e.g., using a display name instead of an ID), or the source list itself contains genuine duplicate entries that should have been deduplicated earlier in the pipeline with `distinct()`. The fix is either choosing a field that's truly unique, or explicitly deduplicating/validating the source data before the `for` expression runs.
_What the interviewer is probing for:_ Systematic debugging approach — using `terraform console` to isolate the actual colliding data rather than guessing from the error message alone, plus understanding the difference between "field looks unique" and "field is guaranteed unique."

**🎯 Architect:** _"You're reviewing a module that converts a `count`-based resource block to `for_each`, using a `for` expression to build the keyed map from a list variable. What do you check for in the review beyond syntax correctness?"_
**Model answer:** Beyond confirming the `for` expression compiles and the key expression is genuinely unique, the critical review point is state impact: switching from `count` (index-addressed, `resource[0]`, `resource[1]`) to `for_each` (key-addressed, `resource["name"]`) changes every resource instance's address in state, which Terraform will interpret as destroying the old indexed instances and creating new keyed ones unless the migration is handled explicitly with `moved` blocks or `terraform state mv` ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) for each instance. I'd also check that the chosen map key is stable across applies — if the key expression derives from something that can change value between runs (like a list index used as a key, defeating the whole purpose), the migration to `for_each` doesn't actually deliver its main benefit of stable per-instance addressing. Getting the `for` expression syntactically right is the easy part; getting the state transition safe is where real risk lives.
_What the interviewer is probing for:_ Whether the candidate connects language-mechanics fluency (`for` expressions) to its actual operational consequence (state addressing, safe migration) — a hallmark of senior-level Terraform review, tying Part 3 mechanics to Part 7 state concerns.

## 12. Common Misconceptions

1. **"Splat and `for` expressions are entirely different tools."** Splat is literally syntactic sugar for the single-attribute-extraction case of a `for` expression — they're the same underlying mechanism at different levels of compactness.
2. **"`for` expressions can use `if` as an arbitrary value transformer."** The `if` clause is strictly a boolean filter that skips elements — it cannot alter the output value, only decide whether an element is included.
3. **"Nested `for` expressions automatically flatten."** They don't — nesting produces a list of lists (or similar nested structure); `flatten()` must be called explicitly.
4. **"Any list can be used with `for_each` directly."** It cannot — `for_each` requires a map or a set of strings; a list must first be transformed via a map-producing `for` expression (or converted to a set, with the caveats that implies).

## 13. 🔑 Key Takeaways

- `for` expressions come in two output forms: `[for x in y : expr]` (list) and `{for k, v in y : k_expr => v_expr}` (map), with an optional `if` filter clause in either form.
- Splat (`list[*].attr`) is shorthand for the single-attribute-extraction `for` expression — reach for it when that's all that's needed, and the full `for` form when filtering, key transformation, or map output is required.
- Map-producing `for` expressions require unique key expressions or Terraform raises `Duplicate object key` — this is exactly the constraint that makes their output safe to feed directly into `for_each`.
- Nested `for` expressions don't auto-flatten; pair with `flatten()` explicitly when needed.
- Converting `count`-indexed resources to `for_each`-keyed ones via a `for` expression is a language-mechanics change with real state-addressing consequences — always verify the migration plan, not just the syntax.

## 14. Related Concepts & What's Next

[§22](./Section-22-Part3-Dynamic-Blocks.md) (Dynamic Blocks) reuses this exact `for`-expression mental model to generate repeated nested blocks instead of repeated top-level resources. [§23](./Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md) introduces `for_each` as a resource meta-argument, the primary consumer of map-producing `for` expressions covered here. [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) covers the `count` vs. `for_each` trade-off, including the state-addressing migration concern raised in the Architect interview question above, in full depth. [§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md) covers `terraform state mv`, the tool used to safely migrate resource addresses during a `count`-to-`for_each` conversion.

**Next Section:** [§22](./Section-22-Part3-Dynamic-Blocks.md) — `Section-22-Part3-Dynamic-Blocks.md`
