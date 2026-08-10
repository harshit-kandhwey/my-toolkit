# Section 61 (Part 8): Module Composition Patterns and Nested Modules

## 1. Definition

**Plain language:** Once you have several modules, the real design work is how they fit together — which module's outputs feed which other module's inputs, whether a module should call other modules internally, and how deep that nesting should go before it becomes more confusing than helpful.

**Precise definition:** **Module composition** is the practice of building larger infrastructure configurations by wiring together multiple modules' inputs and outputs ([§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)) — most commonly, the root module calling several sibling child modules and passing one module's output as another's input argument. **Nested modules** occur when a child module itself contains `module` blocks calling further child modules — Terraform supports unlimited nesting depth, and each level extends the state address accordingly (`module.parent.module.child.aws_instance.this`, per [§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)). Two common named composition patterns are the **wrapper module** (a thin module whose entire purpose is calling one other module — often a public registry module — with an organization's standardized defaults pre-filled, narrowing its interface) and **facade/orchestration modules** (a higher-level module that composes several lower-level modules into one cohesive unit representing a larger logical component, like an "application stack" module that internally calls network, compute, and database child modules).

> 💡 **Tip:** Nesting depth is not free. Every level of nesting adds a `module.` prefix to every state address beneath it, makes `-target` ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) more verbose to write correctly, and makes it harder to trace "where did this resource actually come from" when debugging a plan. A good rule of thumb: nest only when the nested module is a genuine, independently meaningful unit (not just a way to split files for tidiness) — most well-designed Terraform codebases rarely nest more than two levels deep in practice.

## 2. Why This Matters

- **Composition is how modules deliver on the reuse promise from [§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md) at scale** — a handful of well-designed, composable modules (network, compute, database, IAM) can be recombined in different arrangements across many root modules, rather than needing one giant module per application.
- **Wrapper modules are the standard way organizations apply governance to public registry modules** — instead of every team independently configuring `terraform-aws-modules/vpc/aws` with their own tagging and CIDR conventions, a wrapper module standardizes those defaults once and exposes a narrower, safer interface.
- **Understanding output-to-input wiring across modules is the practical mechanism behind almost every non-trivial Terraform dependency graph** — knowing how `module.network.vpc_id` flows into `module.database.vpc_id` is what makes the DAG ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) spanning multiple modules comprehensible rather than mysterious.
- **Nesting depth directly affects debuggability and state address verbosity** — architects who understand this trade-off design shallower, more composable module trees rather than deep hierarchies that are technically valid but operationally painful.
- This section is the natural capstone before [§62](./Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md)'s best practices, since composition decisions are where most real module design mistakes actually happen.

## 3. Prerequisites and Dependencies

This section assumes [§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)'s state-addressing model (`module.<name>.` prefixing, extended by nesting), [§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)'s input/output mechanics (the actual wiring mechanism composition relies on), and [§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)'s source syntax (since composed modules can mix local, registry, and Git sources freely within the same configuration). [§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)'s dependency graph concepts are directly relevant to understanding how composition affects apply ordering across module boundaries.

## 4. Architecture / Conceptual Diagram

```text
PATTERN 1: Sibling composition (root module wires outputs -> inputs)
┌─────────────────────────────────────────────────────────────────────┐
│ ROOT MODULE                                                         │
│                                                                     │
│  module "network" { source = "./modules/network" }                  │
│           │ outputs: vpc_id, subnet_ids                             │
│           ▼                                                         │
│  module "database" {                                                │
│    source = "./modules/database"                                    │
│    vpc_id     = module.network.vpc_id        ◄── output feeds input │
│    subnet_ids = module.network.subnet_ids                           │
│  }                                                                  │
│           │ outputs: db_endpoint                                    │
│           ▼                                                         │
│  module "app" {                                                     │
│    source   = "./modules/app"                                       │
│    db_endpoint = module.database.db_endpoint  ◄── output feeds input│
│  }                                                                  │
└─────────────────────────────────────────────────────────────────────┘

PATTERN 2: Nested modules (module calling module internally)
┌─────────────────────────────────────────────────────────────────────┐
│ ROOT MODULE                                                         │
│   module "app_stack" { source = "./modules/app-stack" }             │
└───────────────────────┬─────────────────────────────────────────────┘
                        ▼
        ┌───────────────────────────────┐
        │ modules/app-stack/ (child of root)│
        │   module "network" { ... }          │  <- nested (grandchild of root)
        │   module "database" { ... }           │  <- nested (grandchild of root)
        │   resource "aws_ecs_service" "app" {   │
        │     ... references module.network.*,     │
        │     module.database.* internally ...        │
        │   }                                             │
        └───────────────────────────────┘
State address: module.app_stack.module.network.aws_vpc.this
                └────┬────┘ └───┬───┘
                (root's call)  (app-stack's internal call)

PATTERN 3: Wrapper module (narrows a public module's interface)
  module "vpc" {                        <- inside org-internal wrapper module
    source  = "terraform-aws-modules/vpc/aws"
    version = "~> 5.8"
    # org-standard defaults pre-filled here, not exposed to wrapper's caller:
    enable_nat_gateway = true
    tags = local.org_standard_tags
    # only cidr and name are exposed as the wrapper's own variables
    cidr = var.cidr
    name = var.name
  }
```

- Sibling composition (Pattern 1) keeps every module at the same nesting depth, one level below root — this is the most common and generally most maintainable arrangement.
- Nested modules (Pattern 2) are appropriate when the inner modules genuinely only make sense as part of the outer module's larger unit (e.g., a reusable "full application stack" module that always needs its own network and database, never called independently) — if the inner modules also need to be called standalone elsewhere, sibling composition at the root is usually the better design.

## 5. Hands-On

### 5.1 Sibling Composition: Wiring Outputs Across Modules

**Purpose:** Show the standard root-module composition pattern with real output-to-input wiring.

**Syntax:**

```hcl
module "network" {
  source = "./modules/network"

  cidr_block = "10.0.0.0/16"
}

module "database" {
  source = "./modules/database"

  vpc_id            = module.network.vpc_id
  subnet_ids        = module.network.private_subnet_ids
  instance_class    = "db.t3.medium"
  allocated_storage = 100
}

module "app" {
  source = "./modules/app"

  vpc_id      = module.network.vpc_id
  subnet_ids  = module.network.public_subnet_ids
  db_endpoint = module.database.endpoint
}
```

**Example usage and expected output:**

```bash
$ terraform graph | grep module
# shows module.database depends on module.network,
# module.app depends on both module.network and module.database

$ terraform apply
Terraform will perform the following actions:
  # module.network.* resources created first
  # module.database.* resources created after (depends on network outputs)
  # module.app.* resources created last (depends on both)
```

**Production usage example:** This three-tier composition (network → database → app) is one of the most common shapes in real Terraform codebases — Terraform's dependency graph ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) automatically sequences the applies correctly purely from the output references, with no explicit ordering ever written by hand.

**Common errors:** Introducing a circular reference (module A's input depends on module B's output, and module B's input depends on module A's output) produces a graph cycle error at plan time — Terraform cannot resolve an ordering and will report exactly which reference creates the cycle.

### 5.2 A Wrapper Module Narrowing a Public Module's Interface

**Purpose:** Show a governance-oriented wrapper module pattern.

**Syntax:**

```hcl
# modules/org-vpc/variables.tf (the org's own wrapper module)
variable "name" {
  type = string
}

variable "cidr" {
  type = string
}
```

```hcl
# modules/org-vpc/main.tf
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.8"

  name = var.name
  cidr = var.cidr

  # org-wide standardized defaults, NOT exposed as wrapper inputs:
  enable_nat_gateway   = true
  single_nat_gateway   = true
  enable_dns_hostnames = true
  tags = {
    ManagedBy   = "terraform"
    Environment = "shared"
  }
}
```

```hcl
# modules/org-vpc/outputs.tf
output "vpc_id" {
  value = module.vpc.vpc_id
}
```

**Example usage and expected output:**

```bash
$ terraform plan
# Consumers of modules/org-vpc only ever set `name` and `cidr` —
# NAT gateway strategy, DNS settings, and tagging are enforced
# organization-wide by the wrapper, not left to each caller's discretion.
```

**Production usage example:** Wrapper modules are the standard mechanism platform teams use to let application teams consume a well-vetted public module ([§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)) without needing to independently rediscover and correctly set the same dozen governance-relevant arguments every single team would otherwise need to know about.

**Common errors:** Over-narrowing a wrapper's interface (exposing only 2 of the underlying module's 40 inputs) can force consumers who genuinely need an unexposed option to either fork the wrapper or petition the platform team for an addition — a wrapper module's interface design deserves the same care as [§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)'s guidance on input surface for any other module.

## 6. Production Usage Notes

- **Nested modules increase the verbosity of `-target` ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) and `state mv` ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) operations** — targeting a single resource two levels deep requires the full `module.parent.module.child.resource_type.name` address, which is more error-prone to type correctly than a shallower structure.
- **Wrapper modules should re-export only the outputs consumers actually need**, not blindly proxy every output of the wrapped module — this keeps the wrapper's own interface as deliberate and curated as any other module's, per [§57](./Section-57-Part8-Module-Inputs-and-Outputs.md).
- **A facade/orchestration module (composing several lower-level modules into one higher-level module) trades composability for convenience** — it's easier for a consumer to call one `module "app_stack"` block than five separate module blocks, but it's harder to reuse the network module independently if it's only ever nested inside `app_stack` and never exposed as a sibling-composable option.

## 7. Security Considerations

- Composition chains that wire a sensitive output ([§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)) from one module into another module's input still carry that value through the state file at every level of the chain — a database password output flowing from `module.database` into `module.app`'s input is present in state at both addresses, which is relevant when reasoning about state-file exposure ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) across a composed configuration.
- Wrapper modules that centralize security-relevant defaults (network egress rules, encryption settings) are a genuine security control when done well — they prevent every individual team from having to correctly configure the same security-sensitive arguments independently, reducing the chance any one team gets it wrong.
- Deeply nested compositions make security review harder in practice — reviewing a root module's plan output for a security-relevant change requires understanding what's happening several `module.` levels deep, which is a real (if often underweighted) argument for favoring shallower composition where feasible.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                          | Likely Cause                                                                                                                                                                                                      | Resolution Path                                                                                                                                                                                                  |
| -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Error: Cycle` during `terraform plan`                                           | Two or more modules' inputs/outputs reference each other, forming a circular dependency                                                                                                                           | Trace the reported cycle; restructure so dependencies flow one direction (often by extracting a shared value to a third module or root-level local)                                                              |
| Extremely long, error-prone `-target` addresses needed to plan a single resource | Module nesting is deeper than necessary for the actual reuse requirement                                                                                                                                          | Reconsider whether the inner module truly needs to be nested versus called as a sibling at the root ([§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md))                                |
| A wrapper module doesn't expose an option a consumer actually needs              | Wrapper's interface was deliberately (or accidentally) narrowed below what some legitimate use cases require                                                                                                      | Add the missing pass-through variable/output to the wrapper, or reconsider whether that use case belongs in a different, less-restrictive module                                                                 |
| Plan shows unexpected changes rippling through several composed modules          | An upstream module's output changed (e.g., a new default in an updated version, [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) and propagated through every module consuming that output | Trace the change to its source module via the dependency graph ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)); evaluate whether the propagation is intended |

## 9. Best Practices

- Prefer sibling composition (root module wiring several same-depth child modules) over deep nesting unless the inner modules genuinely have no independent existence outside the outer module.
- Use wrapper modules deliberately for governance over widely-consumed public modules, keeping the wrapper's own interface as curated as any other module's per [§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)'s guidance.
- Keep composition chains readable by naming `module` blocks after what they represent in the composition (`module "network"`, `module "database"`), so the wiring between them (`module.network.vpc_id` → `module.database.vpc_id`) reads clearly without needing to open every module's source.

## 10. Common Anti-Patterns / Mistakes

- **Nesting purely to organize files rather than to represent a genuine reusable unit.** If the "inner module" is never intended to be called independently and exists only to split a large module's file into smaller pieces, plain file-splitting within one module ([§56](./Section-56-Part8-Module-Structure-and-Conventions.md)) is usually the better tool than introducing a real nested `module` block and its associated state-address overhead.
- **Wrapper modules that just proxy every single argument and output with no actual defaults or governance applied.** If a wrapper adds zero value beyond renaming, it's pure indirection — the point of a wrapper is to standardize/narrow, not to exist as a pass-through shim.
- **Circular composition attempts, discovered only at plan time.** Designing module interfaces without first sketching the intended data flow (which outputs feed which inputs) is a common cause of accidentally circular designs that could have been caught on a whiteboard before implementation.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between two modules being 'sibling' modules versus one being 'nested' inside the other?"_
**Model answer:** Sibling modules are both called directly from the same parent (typically the root module) — each gets a `module.<name>.` state address at the same depth, and they can pass outputs to each other's inputs. A nested module is called from inside another child module, not directly from the root — its state address extends further, like `module.parent.module.child.resource_type.name`, reflecting that it's one level deeper in the module tree.
_What the interviewer is probing for:_ Basic grasp of module tree structure and how it maps to state addressing depth.

**🎯 Intermediate:** _"What is a 'wrapper module' and why would an organization build one around a public registry module instead of just consuming the public module directly everywhere?"_
**Model answer:** A wrapper module is a thin, organization-owned module whose main job is calling another module (often a public registry module) with standardized defaults pre-filled, exposing a narrower interface to its own callers. Organizations build these for governance: instead of every team independently configuring a dozen security- or cost-relevant arguments on a public VPC module, the wrapper centralizes those defaults once, so individual teams only set the few things that legitimately vary (like `name` and `cidr`) and can't accidentally misconfigure the standardized parts.
_What the interviewer is probing for:_ Understanding wrapper modules as a governance pattern with a real organizational motivation, not just "a module that calls another module."

**🎯 Senior:** _"You're reviewing a module that nests four levels deep — root calls app_stack, which calls compute_group, which calls instance_pool, which calls launch_template. What concerns would you raise, and what would you ask the author?"_
**Model answer:** Four levels of nesting means every resource's state address carries four `module.` prefixes, `-target` operations become unwieldy, and tracing a specific plan diff back to its actual source module requires mentally unwinding the whole chain — real operational cost. I'd ask the author whether each inner module genuinely needs independent existence as a module boundary versus being flattened into its parent's own files ([§56](./Section-56-Part8-Module-Structure-and-Conventions.md)) — specifically, is `launch_template` ever called from anywhere other than `instance_pool`, and is `instance_pool` ever called from anywhere other than `compute_group`? If the answer to both is "no, never independently," that's a strong signal at least two of those four levels should collapse into their parent as plain resource blocks rather than separate nested module calls, since nesting only pays for itself when the inner unit has genuine independent reuse value.
_What the interviewer is probing for:_ Practical judgment about when nesting is earning its complexity cost versus when it's accidental over-engineering — a real code review skill, not abstract module theory.

**🎯 Architect:** _"Design the module composition strategy for a platform supporting ~60 application teams, where each team needs a network, a compute layer, and a database, but with meaningfully different requirements per team (some need multi-AZ databases, some don't; some need public-facing compute, some don't). Sibling composition at each root, a single deeply composed 'app_stack' module, or something else?"_
**Model answer:** I'd favor sibling composition of well-designed, independently versioned child modules (network, database, compute) called directly from each team's root module, rather than one monolithic nested `app_stack` module — the stated requirement variance across 60 teams (multi-AZ vs. not, public vs. private compute) is exactly the signal that a single rigid composed unit will accumulate an ever-growing pile of conditional flags trying to serve every team's variant, becoming harder to version and reason about over time ([§62](./Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md)'s anti-patterns cover this "one module trying to do everything" failure mode directly). Sibling composition lets each team's root module opt into exactly the combination of child module inputs it needs, each child module stays independently versioned and testable ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)), and platform-team governance is still achievable via wrapper modules (this section) around the most security/cost-sensitive pieces (typically network and database) without forcing uniformity on compute, which is where teams' requirements diverge most. I'd reserve a genuinely nested "starter" composition module as an opt-in convenience for teams with straightforward, default-shaped needs, while keeping the underlying network/database/compute modules independently callable for teams that need to deviate.
_What the interviewer is probing for:_ Whether the candidate can weigh composition strategies against real requirement heterogeneity across many consumers, rather than defaulting to "always compose deeply" or "always keep flat" as a one-size-fits-all answer.

## 12. Common Misconceptions

1. **"Nested modules and sibling modules are functionally identical, just organized differently."** They differ meaningfully in state address depth, `-target` verbosity, and independent reusability — a nested module cannot easily be called standalone elsewhere the way a sibling module can.
2. **"A wrapper module is redundant if it doesn't add new resources of its own."** Its value is in narrowing/standardizing the interface and centralizing defaults, not in adding resources — a wrapper with zero resources of its own that only calls one other module with fixed defaults is still doing real governance work.
3. **"Deep nesting is always a sign of good modular design."** Nesting depth should track genuine reuse boundaries, not be maximized for its own sake — unnecessary nesting adds real operational cost (state address verbosity, harder tracing) without a corresponding benefit.
4. **"Circular module dependencies are just a Terraform limitation to work around with `depends_on`."** They're a design smell, not a syntax problem — `depends_on` cannot fix an actual circular data dependency between two modules' inputs and outputs; the composition needs to be restructured.

## 13. 🔑 Key Takeaways

- Composition is the practice of wiring modules' outputs into other modules' inputs; nesting is a child module calling further child modules internally, extending the state address depth accordingly.
- Sibling composition (all child modules called directly from root) is generally more maintainable than deep nesting, and is the more common real-world pattern.
- Wrapper modules narrow and standardize a widely-consumed module's (often a public registry module's) interface for organizational governance, without necessarily adding resources of their own.
- Nesting should reflect genuine independent-reuse boundaries, not just a desire to organize files — unnecessary nesting adds real operational cost with `-target`/`state mv` verbosity and debugging difficulty.
- Circular composition dependencies are a design problem to restructure around, not something `depends_on` can resolve.

## 14. Related Concepts & What's Next

[§62](./Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md) closes out Part 8 with module design best practices and anti-patterns, building directly on the composition trade-offs introduced here. [§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)'s resource targeting and [§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)'s state commands both become more complex to use correctly as nesting depth increases, exactly as discussed above. [§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)'s dependency graph construction underlies how Terraform sequences applies across composed and nested modules automatically.

**Next Section:** [§62](./Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md) — `Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md`
