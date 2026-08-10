# Section 34 (Part 5): Resource Meta-Arguments: count vs. for_each

## 1. Definition

**Plain language:** `count` and `for_each` are both ways to tell Terraform "create more than one of this resource" from a single `resource` block, instead of copy-pasting the block multiple times. The difference is how each instance gets identified: `count` numbers them (0, 1, 2...) based on position in a list; `for_each` names them using a key from a map or set. That naming difference sounds small but has large practical consequences when the list of things you're provisioning changes over time.

**Precise definition:** **`count`** and **`for_each`** are **meta-arguments** — special arguments recognized by Terraform core itself (not by any provider schema) that can be attached to any `resource`, `data`, or `module` block to produce multiple instances from one block. `count = <number>` produces instances addressed by integer index (`resource_type.name[0]`, `[1]`, ...), and exposes `count.index` inside the block for per-instance customization. `for_each = <map_or_set>` produces instances addressed by string key (`resource_type.name["key"]`), and exposes `each.key` and `each.value` inside the block. `for_each` accepts a `map(any)` or a `set(string)` — never a `list`, though a list can be converted with `toset()`. A resource block may use `count` or `for_each`, never both.

> 💡 **Tip:** The rule of thumb that resolves nearly every "which one should I use" question: if the members of your collection are truly interchangeable and only their _count_ matters (three identical worker nodes), `count` is fine. If each member has a distinct identity that should survive the _other_ members changing (per-environment configs, per-user IAM roles, named subnets), use `for_each` — because `for_each`'s key-based addressing means removing one member doesn't reshuffle and force-replace every other member.

## 2. Why This Matters

- **Instance-key stability directly determines blast radius during a change.** A `count`-based list where an item is removed from the middle shifts every subsequent index, causing Terraform to plan a destroy/recreate for resources that didn't logically change at all — this has caused real production outages when teams didn't anticipate it.
- **`for_each` is now the generally recommended default for anything beyond a small, truly-anonymous, fixed-size collection**, precisely because key-based addressing avoids the reshuffling problem structurally.
- **Both meta-arguments fundamentally change a resource's address** ([§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md)) from a single `type.name` to an indexed or keyed family of addresses — every downstream reference, `-target` ([§37](./Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)), and `state mv` operation must account for this.
- **Migrating between `count` and `for_each` on an existing resource is itself a state operation**, not a free syntax swap — getting this wrong on a live production resource can trigger unwanted destroys.
- **Certification and interview relevance:** the `count`/`for_each` trade-off is one of the most consistently tested and asked-about topics in Terraform Associate prep ([§112](../Part16/Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md)–[§116](../Part16/Section-116-Part16-Scenario-Based-Infrastructure-Design-Questions.md)) and real interviews, because it's where "syntax knowledge" and "production judgment" most visibly diverge.

## 3. Prerequisites and Dependencies

This section depends on [§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md) (resource addressing — instance keys extend that grammar) and on [§17](../Part3/Section-17-Part3-Data-Types-Primitives-Collections-list-map-set-Structural-object-tuple.md) (data types: list, map, set) and [§21](../Part3/Section-21-Part3-for-Expressions-and-Splat-Expressions.md) (`for` expressions and splat expressions) from Part 3, since `for_each` collections are frequently built with `for` expressions. [§23](../Part3/Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md) (Meta-Arguments Overview) previewed `count`/`for_each` alongside `depends_on`, `lifecycle`, and `provider`; this section is their dedicated deep dive.

## 4. Architecture / Conceptual Diagram

```text
  count = 3                              for_each = {
                                            "primary"   = "10.0.1.0/24"
  aws_subnet.this[0]                       "secondary" = "10.0.2.0/24"
  aws_subnet.this[1]                     }
  aws_subnet.this[2]
                                          aws_subnet.this["primary"]
  count.index available inside            aws_subnet.this["secondary"]
  the block: 0, 1, 2
                                          each.key   available: "primary", "secondary"
                                          each.value available: "10.0.1.0/24", "10.0.2.0/24"


  REMOVING THE MIDDLE ELEMENT — WHY IT MATTERS

  count-based list  ["a", "b", "c"]  →  ["a", "c"]     (removed "b")

       BEFORE                 AFTER                    RESULT
    this[0] = a            this[0] = a                 unchanged
    this[1] = b            this[1] = c   ◄─ was [2]!    DESTROYED + RECREATED
    this[2] = c            (index 2 no longer exists)   DESTROYED

  for_each-based map { a = .., b = .., c = .. }  →  { a = .., c = .. }  (removed "b")

       BEFORE                 AFTER                    RESULT
    this["a"] = ..         this["a"] = ..               unchanged
    this["b"] = ..         (key "b" no longer exists)    DESTROYED (only "b")
    this["c"] = ..         this["c"] = ..               unchanged
```

- With `count`, Terraform has no concept of "identity" beyond position — instance `[1]` after a removal is treated as a completely different resource from what used to be at `[1]`, even if its configured values are unchanged.
- With `for_each`, each key is an independent identity — removing one key only affects that one instance; every other key's instance is left alone by the plan.
- Both mechanisms still build one dependency graph node per instance ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) — `count`/`for_each` don't collapse instances into a single graph node, so they can still be independently created, updated, or destroyed in parallel up to `-parallelism` limits ([§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)).

## 5. Hands-On

### 5.1 `count` — Fixed-Size, Interchangeable Instances

**Purpose:** Provision a known, fixed number of near-identical resources.

**Syntax:**

```hcl
resource "<TYPE>" "<NAME>" {
  count = <number>
  # count.index available inside the block
}
```

**Example usage and expected output:**

```hcl
resource "aws_instance" "worker" {
  count         = 3
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t3.micro"

  tags = {
    Name = "worker-${count.index}"
  }
}
```

```bash
$ terraform plan
  # aws_instance.worker[0] will be created
  # aws_instance.worker[1] will be created
  # aws_instance.worker[2] will be created

Plan: 3 to add, 0 to change, 0 to destroy.
```

**Production usage example:** `count` remains a reasonable fit for genuinely anonymous, interchangeable capacity — e.g., a fixed pool of stateless worker nodes behind a load balancer where individual identity truly doesn't matter and the pool size is set by a variable ([§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)) rarely changed mid-list.

**Common errors:** `Error: Invalid count argument` appears when the `count` expression itself depends on a value not known until apply (e.g., a data source result deferred to apply, §5.3 of [§33](./Section-33-Part5-Data-Sources-Reading-External-and-Existing-Infrastructure.md)) — count/for_each expressions must be resolvable at plan time.

### 5.2 `for_each` with a Map — Distinct, Named Instances

**Purpose:** Provision instances with stable, meaningful identity that survives other instances being added or removed.

**Syntax:**

```hcl
resource "<TYPE>" "<NAME>" {
  for_each = <map(any)>
  # each.key / each.value available inside the block
}
```

**Example usage and expected output:**

```hcl
resource "aws_subnet" "this" {
  for_each = {
    primary   = "10.0.1.0/24"
    secondary = "10.0.2.0/24"
  }

  vpc_id     = aws_vpc.main.id
  cidr_block = each.value

  tags = {
    Name = "subnet-${each.key}"
  }
}
```

```bash
$ terraform plan
  # aws_subnet.this["primary"] will be created
  # aws_subnet.this["secondary"] will be created

Plan: 2 to add, 0 to change, 0 to destroy.

$ # later, "secondary" removed from the map, "tertiary" added
$ terraform plan
  # aws_subnet.this["secondary"] will be destroyed
  # aws_subnet.this["tertiary"] will be created
  # aws_subnet.this["primary"] — no changes

Plan: 1 to add, 1 to destroy, 0 to change.
```

**Production usage example:** This is the standard shape for anything with meaningful per-instance identity — per-availability-zone subnets, per-environment resources, per-team IAM roles — where each key maps directly to something a human would name, and adding/removing one entry should never disturb the others.

**Common errors:** `Error: Invalid for_each argument — the given "for_each" argument value is unsuitable` appears when passing a `list` directly (lists aren't accepted) — wrap it with `toset(list_value)` if the values are already unique strings, or restructure into a map.

### 5.3 `for_each` with a Set — Simple Uniqueness Without Meaningful Values

**Purpose:** Handle the case where you have a unique list of strings (not key-value pairs) but still want stable, key-based addressing.

**Syntax:**

```hcl
resource "<TYPE>" "<NAME>" {
  for_each = toset(<list_of_strings>)
}
```

**Example usage and expected output:**

```hcl
variable "availability_zones" {
  type    = set(string)
  default = ["us-east-1a", "us-east-1b", "us-east-1c"]
}

resource "aws_subnet" "az" {
  for_each          = var.availability_zones
  vpc_id            = aws_vpc.main.id
  availability_zone = each.key
  cidr_block        = cidrsubnet(var.vpc_cidr, 8, index(tolist(var.availability_zones), each.key))
}
```

```bash
$ terraform plan
  # aws_subnet.az["us-east-1a"] will be created
  # aws_subnet.az["us-east-1b"] will be created
  # aws_subnet.az["us-east-1c"] will be created

Plan: 3 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Common for per-availability-zone resources where the "value" and the "key" are effectively the same string — `each.key` and `each.value` are identical when iterating a set, so only `each.key` is typically used for clarity.

**Common errors:** Using `each.value` where a map's _value_ was expected, but the collection is actually a set (where `each.key == each.value` always) — harmless but a sign the author may not have intended a set and meant to build a map instead.

### 5.4 Migrating an Existing Resource from `count` to `for_each`

**Purpose:** Show the state-safe way to convert an already-deployed `count`-based resource to `for_each`, since it is not a drop-in syntax swap.

**Syntax:**

```hcl
moved {
  from = <type>.<name>[<old_index>]
  to   = <type>.<name>["<new_key>"]
}
```

**Example usage and expected output:**

```hcl
# Before: count-based
# resource "aws_subnet" "this" {
#   count      = 2
#   cidr_block = ["10.0.1.0/24", "10.0.2.0/24"][count.index]
# }

# After: for_each-based, with moved blocks to preserve state mapping
resource "aws_subnet" "this" {
  for_each   = { primary = "10.0.1.0/24", secondary = "10.0.2.0/24" }
  cidr_block = each.value
}

moved {
  from = aws_subnet.this[0]
  to   = aws_subnet.this["primary"]
}

moved {
  from = aws_subnet.this[1]
  to   = aws_subnet.this["secondary"]
}
```

```bash
$ terraform plan
Terraform will perform the following actions:

  # aws_subnet.this[0] has moved to aws_subnet.this["primary"]
    resource "aws_subnet" "this" {
        id = "subnet-0a1b2c3d"
    }
  # aws_subnet.this[1] has moved to aws_subnet.this["secondary"]
    resource "aws_subnet" "this" {
        id = "subnet-0e5f6g7h"
    }

Plan: 0 to add, 0 to change, 0 to destroy.
```

**Production usage example:** This exact pattern — `moved` blocks pairing every old index to its correct new key — is the required, safe procedure whenever a team decides mid-project that `count` was the wrong choice; skipping it produces a destroy-then-recreate plan for every instance instead of a zero-downtime address remap.

**Common errors:** Mismatching an old index to the wrong new key in a `moved` block silently repoints state to the _wrong_ resource identity — always verify with `terraform plan` showing `0 to add, 0 to change, 0 to destroy` (pure moves) before applying, never assume the mapping is correct without checking plan output.

## 6. Production Usage Notes

- **`for_each` is the safer default for anything provisioned from a variable-driven collection** (environments, teams, regions) specifically because collection membership changes are the normal case over a project's life, not the exception.
- **`count` is still appropriate, and often clearer, for genuinely fixed, small, interchangeable counts** — e.g., `count = var.enable_feature ? 1 : 0` is a common and idiomatic pattern for conditionally creating a single resource, which `for_each` can also express but less readably.
- **Neither meta-argument can be combined with the other on the same block, and neither can be combined with an explicit single-instance declaration** — a block has exactly one of: no meta-argument (single instance), `count`, or `for_each`.
- **`count.index`, `each.key`, and `each.value` are only valid inside the block they're declared on** — they cannot be referenced from sibling resources directly; sibling resources reference the _resulting_ addressed instances (`aws_instance.worker[0].id`) instead.

## 7. Security Considerations

- A `for_each` map or set frequently comes from a variable ([§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)) or, worse, a data source result — if that collection's source is externally influenced (e.g., a data source reading tags an attacker could modify) without validation, count/for_each-driven resource creation could scale unexpectedly, a potential denial-of-service/cost-blowup vector worth guarding with variable validation ([§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)).
- Because instance keys become part of resource ARNs/names in many providers' default naming schemes, sensitive information should never be used as a `for_each` key or `count.index`-derived name — keys often surface in plan output, state, and cloud console names/logs.
- `moved` block migrations (§5.4) touch state directly; running them requires the same state-write access controls ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md), [§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)) as any other state-modifying operation, since an incorrect mapping can misattribute a resource's identity.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                              | Likely Cause                                                                                                                    | Resolution Path                                                                                                         |
| ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| Removing one item from a `count`-based list destroys/recreates unrelated instances   | Index-based addressing shifted because a middle element was removed                                                             | Migrate to `for_each` with `moved` blocks (§5.4); avoid `count` for collections expected to shrink/grow from the middle |
| `Error: Invalid for_each argument` on a list value                                   | `for_each` does not accept `list` directly                                                                                      | Convert with `toset(list_value)` if elements are unique strings, or restructure into a `map`                            |
| `Error: Invalid count argument` — value depends on resource attributes not yet known | `count`/`for_each` expressions must be known at plan time; a data source or resource attribute deferred to apply cannot be used | Restructure so the count/for_each source is a variable, local, or plan-time-known value                                 |
| `each.key` and `each.value` referenced outside the resource block they belong to     | Misunderstanding scope — these objects only exist inside the block using `for_each`                                             | Reference the resulting resource's specific keyed instance (`type.name["key"].attribute`) from elsewhere instead        |

## 9. Best Practices

- Default to `for_each` for any collection sourced from a variable, unless there's a specific, deliberate reason the collection is a fixed-size, position-agnostic count.
- When using `count` for conditional single-resource creation (`count = var.flag ? 1 : 0`), keep the pattern isolated and well-commented — it's idiomatic but easy for future readers to misread as a genuine multi-instance loop.
- Always verify a `count`-to-`for_each` migration's `plan` output shows only "moved" actions (`0 to add, 0 to change, 0 to destroy`) before applying — never trust the migration logic without confirming against real plan output.
- Keep `for_each` map/set values simple and stable — deriving keys from something that can change independently of actual intent (a hash of a mutable object) reintroduces the same instability `for_each` is meant to avoid.

## 10. Common Anti-Patterns / Mistakes

- **Using `count` for a collection whose membership genuinely changes over the project's life** (per-environment or per-team resources) purely out of habit or unfamiliarity with `for_each` — this sets up the exact reshuffling failure mode described in [§4](../Part1/Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md).
- **Using `for_each` with a data source result that isn't guaranteed to be stable or known at plan time**, causing `Invalid for_each argument` errors that appear inconsistent because the data source's timing varies by dependency shape.
- **Building `for_each` keys from computed expressions instead of stable, deliberate names** — e.g., `for_each = toset([for i in range(3) : "instance-${i}"])`, which just reintroduces `count`'s positional instability while looking like it avoided it.

## 11. Interview Questions

**🎯 Beginner:** _"What's the basic syntax difference between `count` and `for_each`, and what do they each expose inside the resource block?"_
**Model answer:** `count = <number>` produces that many instances, addressed by integer index (`resource.name[0]`), and exposes `count.index` inside the block. `for_each = <map or set>` produces one instance per entry, addressed by the map/set key as a string (`resource.name["key"]`), and exposes `each.key` and `each.value` inside the block (for a set, `each.key` and `each.value` are the same).
_What the interviewer is probing for:_ Basic syntax fluency as a baseline before deeper trade-off questions.

**🎯 Intermediate:** _"Why is removing an item from the middle of a `count`-based list dangerous, and how does `for_each` avoid that problem?"_
**Model answer:** `count` addresses instances purely by position — index 0, 1, 2. If you remove the item that was at index 1 from a 3-item list, everything that used to be at index 2 shifts down to index 1. Terraform compares state (which still has the old index-1 object) against the new plan (which now has a different object at index 1) and concludes the object at index 1 changed, planning a destroy-and-recreate — even though the actual object that was previously at index 2 didn't logically change at all. `for_each` avoids this because each instance's identity is tied to its map/set key, not its position — removing one key only affects that specific instance; every other key's instance is compared correctly against its own unchanged identity and shows no diff.
_What the interviewer is probing for:_ Real understanding of _why_ the instability happens mechanically, not just "for_each is better," which signals memorized advice without comprehension.

**🎯 Senior:** _"How would you safely migrate a production resource block from `count` to `for_each` without any downtime or unwanted resource recreation?"_
**Model answer:** Never just swap the meta-argument and re-run apply — that produces a full destroy/recreate for every instance since the resource addresses change entirely (`[0]` → `["key"]`). The safe path is: rewrite the resource block to use `for_each` with a map/set that produces the same real-world configuration per instance, then add explicit `moved` blocks pairing every old count-based address (`type.name[0]`) to its correct new for_each-based address (`type.name["key"]`) — one `moved` block per instance. Run `terraform plan` and confirm the output shows only "has moved to" notices with `0 to add, 0 to change, 0 to destroy` — a pure state remap, no infrastructure changes. Only apply once that's confirmed; if the plan shows any create/destroy actions, the mapping or the new for_each values don't line up with what's already deployed, and it needs to be fixed before applying.
_What the interviewer is probing for:_ Practical, safety-first migration procedure — many candidates know `for_each` is "better" but haven't thought through how to migrate an already-live resource without an outage.

**🎯 Architect:** _"Your team has a module that provisions one IAM role per application team using `count` over a list variable, ordered alphabetically by team name. A new team is being onboarded, and their name alphabetically sorts into the middle of the existing list. What's the actual risk in this design, and how would you redesign it?"_
**Model answer:** The risk is exactly the reshuffling problem: inserting a new team's name into an alphabetically-sorted list shifts every subsequent team's index, and Terraform will plan a destroy-and-recreate for every IAM role from that insertion point onward — even though only one _new_ role should actually be created. For IAM roles, destroy-then-recreate is genuinely dangerous: any resource, policy attachment, or trust relationship referencing the old role's ARN breaks the moment it's destroyed, potentially mid-recreation, causing an availability or access incident for every affected team, not just the new one. The redesign is straightforward: convert the module to `for_each` keyed by team name (a map or set), so team identity is tied to the team's name itself rather than list position — onboarding a new team, regardless of where it alphabetically falls, only ever adds one new keyed instance and never touches any existing team's role. This migration should itself use `moved` blocks (§5.4) to avoid a one-time destructive migration while fixing the design.
_What the interviewer is probing for:_ Whether the candidate can connect the abstract count/for_each trade-off to a concrete, high-stakes production scenario (IAM, in this case) and reason about both the immediate fix and the safe migration path.

## 12. Common Misconceptions

1. **"`count` and `for_each` are interchangeable, just different syntax for the same thing."** They produce structurally different addressing (positional vs. keyed) with materially different stability properties under list/map membership changes — they are not equivalent in practice.
2. **"`for_each` can accept a list directly."** It cannot — only `map` or `set(string)`; a list must be converted via `toset()` (losing any duplicate values and inherent ordering) or restructured into a map.
3. **"Switching a live resource from `count` to `for_each` is just a text edit."** Without `moved` blocks (or manual `state mv` operations), it produces a full destroy/recreate of every instance because the resource addresses change entirely.
4. **"`each.value` is always different from `each.key`."** Only true for maps; for a `set(string)`, `each.key` and `each.value` are always identical, since a set has no separate key/value distinction beyond the element itself.

## 13. 🔑 Key Takeaways

- `count` addresses instances by integer index; `for_each` addresses instances by map/set key — this is the core mechanical difference behind every practical trade-off between them.
- Removing an item from the middle of a `count`-based collection shifts every subsequent index, causing Terraform to plan unwanted destroy/recreate actions on unrelated resources.
- `for_each` accepts only `map` or `set(string)`, never `list` directly — convert with `toset()` when needed.
- `for_each` is the generally preferred default for collections whose membership can change over a project's life; `count` remains reasonable for fixed-size, position-agnostic, or single-conditional-instance use cases.
- Migrating an existing resource between `count` and `for_each` requires `moved` blocks (or `terraform state mv`) to avoid an unwanted destroy/recreate — it is a state operation, not a free syntax change.

## 14. Related Concepts & What's Next

[§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md) covers the resource addressing grammar that `count`/`for_each` instance keys extend. [§35](./Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md) covers `depends_on`, the other major meta-argument affecting resource ordering. [§36](./Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md) covers the `lifecycle` block, whose `create_before_destroy` argument is frequently paired with `for_each`-driven resources during safe replacements. [§21](../Part3/Section-21-Part3-for-Expressions-and-Splat-Expressions.md) (`for` expressions and splat expressions) and [§17](../Part3/Section-17-Part3-Data-Types-Primitives-Collections-list-map-set-Structural-object-tuple.md) (collection types) from Part 3 are the HCL mechanics most commonly used to build `for_each` maps and sets from other data.

**Next Section:** [§35](./Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md) — `Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md`
