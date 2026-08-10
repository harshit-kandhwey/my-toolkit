# Section 55 (Part 8): What Modules Are; Root Module vs. Child Modules

## 1. Definition

**Plain language:** A module is just a folder containing `.tf` files. Every Terraform configuration has at least one module — the **root module**, the directory you run `terraform apply` from. When that configuration calls another folder of `.tf` files using a `module` block, that called folder is a **child module** — a self-contained, reusable unit of configuration that the root (or another module) can instantiate, potentially many times, each time with different inputs.

**Precise definition:** A **module** in Terraform is any directory containing `.tf`/`.tf.json` configuration files. The **root module** is the module Terraform loads directly from the working directory when a command is run; it is always present, even in a single-file configuration with no `module` blocks at all. A **child module** is a module referenced from another module via a `module "<name>" { source = ... }` block; the module doing the referencing is that child's **caller**. Modules can be nested arbitrarily deep — a child module can itself call further child modules. Crucially, every `module` block instance creates its own **namespace in the state address space**: a resource `aws_instance.app` declared inside a module called from `module "web" { ... }` is addressed in state as `module.web.aws_instance.app`, not `aws_instance.app` — the module call is a state-addressing boundary, not just a file-organization convenience.

> 💡 **Tip:** "Module" does not mean "special file type" — there is no `module.tf` file and no syntactic marker inside a directory that makes it a module. Any directory of valid `.tf` files can be used as a root module (run directly) or as a child module (called via a `module` block) — the same directory can even serve both purposes on different occasions, which is exactly what makes the `examples/` convention ([§56](./Section-56-Part8-Module-Structure-and-Conventions.md)) work.

## 2. Why This Matters

- **Reuse without copy-paste.** A VPC-with-subnets pattern used across ten environments can be written once as a child module and instantiated ten times with different inputs, instead of ten near-identical copies of the same 200 lines of HCL silently drifting apart over time.
- **Encapsulation.** A well-designed child module exposes only its inputs and outputs ([§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)) — callers don't need to understand its internal resource names or provider quirks to consume it, the same way a function's caller doesn't need to read its implementation.
- **State organization follows module structure.** Because every module call gets its own `module.<name>.` prefix in state addressing, modules give you a natural, hierarchical way to reason about a `terraform state list` output on a large configuration instead of one flat list of hundreds of resources.
- **Blast-radius reasoning.** Understanding root vs. child modules is the prerequisite for understanding `-target=module.name` partial applies ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) and `terraform state mv` module refactors ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) — both operate on this same addressing boundary.
- **This is the foundation of everything else in Part 8.** Structure conventions ([§56](./Section-56-Part8-Module-Structure-and-Conventions.md)), inputs/outputs ([§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)), sourcing ([§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)), the public registry ([§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)), versioning ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)), composition ([§61](./Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md)), and design best practices ([§62](./Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md)) all build directly on the root/child distinction established here.

## 3. Prerequisites and Dependencies

This section assumes comfort with resource blocks and resource addressing ([§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md)), since module addressing is a direct extension of that idea, and with the state file's role in tracking resources ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)), since the state-namespace claim above is meaningless without understanding what state actually records. [§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)'s dependency graph concepts also apply inside and across module boundaries — Terraform builds one graph spanning the root module and every module it calls, not a separate graph per module.

## 4. Architecture / Conceptual Diagram

```text
                         ROOT MODULE
                    (the directory you `terraform apply` from)
                         main.tf, variables.tf, outputs.tf
                                    │
                    ┌───────────────┼───────────────┐
                    │               │               │
            module "network"  module "web"    module "web"
            { source = ... }  { source = ... } { source = ... }
            (1 instance)      (instance "a")   (instance "b")
                    │               │               │
                    ▼               ▼               ▼
          ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
          │ CHILD MODULE │ │ CHILD MODULE │ │ CHILD MODULE │
          │  (network/)  │ │   (web/)     │ │   (web/)     │
          │ resources... │ │ resources... │ │ resources... │
          └──────────────┘ └──────────────┘ └──────────────┘

STATE ADDRESSING (flat namespace, module-prefixed):
  aws_vpc.main                          <- root module resource (no prefix)
  module.network.aws_subnet.public      <- inside the "network" module call
  module.web["a"].aws_instance.app      <- inside the first "web" call
  module.web["b"].aws_instance.app      <- inside the second "web" call

Same source directory (web/), called twice with for_each -> two
completely independent resource instances, each with its own state address.
```

- The root module is not optional or special-cased syntactically — it is simply "whatever module Terraform was invoked against." Every configuration, even a single `main.tf` with three resources and no `module` blocks, has exactly one module: the root.
- A single child module **source directory** can be called multiple times (as shown with `web/` above), each call getting an independent name (`web["a"]`, `web["b"]`) if `for_each` or `count` is used on the `module` block itself — this is exactly analogous to `count`/`for_each` on a `resource` block ([§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)), just one level up.
- Nesting is unlimited: a child module can itself contain `module` blocks calling further child modules, and the state address just keeps extending (`module.web.module.logging.aws_iam_role.this`).

## 5. Hands-On

### 5.1 Recognizing the Root Module

**Purpose:** Show that "root module" is a positional concept, not a file marker.

**Syntax:**

```text
my-project/
├── main.tf          # this whole directory is the root module
├── variables.tf
└── outputs.tf
```

**Example usage and expected output:**

```bash
$ cd my-project
$ terraform apply
# Terraform loads main.tf/variables.tf/outputs.tf in this directory
# as the root module — no configuration marks it as "root" explicitly.
```

**Production usage example:** Every Terraform project has exactly one root module per `terraform init`/`apply` invocation — in a multi-environment layout ([§71](../Part10/Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md)), each environment directory (`environments/dev/`, `environments/prod/`) is its own separate root module, each typically calling the same shared child modules with different inputs.

**Common errors:** Running `terraform apply` from inside what was intended to be a child module's own directory (e.g., `cd modules/network && terraform apply`) technically works — Terraform will treat `modules/network` as a root module and create its own separate state file there — but this is almost always a mistake; it fragments state and bypasses the calling configuration's inputs.

### 5.2 Calling a Child Module and Inspecting Its State Address

**Purpose:** Demonstrate the `module.<name>.` state-addressing prefix in practice.

**Syntax:**

```hcl
# root module: main.tf
module "network" {
  source = "./modules/network"

  cidr_block = "10.0.0.0/16"
}

resource "aws_instance" "bastion" {
  # root-module resource — no module prefix
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"
  subnet_id     = module.network.public_subnet_id
}
```

```hcl
# modules/network/main.tf (the child module)
resource "aws_vpc" "this" {
  cidr_block = var.cidr_block
}

resource "aws_subnet" "public" {
  vpc_id     = aws_vpc.this.id
  cidr_block = "10.0.1.0/24"
}
```

**Example usage and expected output:**

```bash
$ terraform apply
Terraform will perform the following actions:
  # aws_instance.bastion will be created
  # module.network.aws_vpc.this will be created
  # module.network.aws_subnet.public will be created

$ terraform state list
aws_instance.bastion
module.network.aws_vpc.this
module.network.aws_subnet.public
```

**Production usage example:** This is the standard shape of nearly every non-trivial root module — a handful of child module calls for reusable, well-tested patterns (networking, IAM, a standard compute pattern), plus a small number of root-module-local resources that are specific to this one environment and not worth abstracting into a module.

**Common errors:** Referencing a child module's internal resource directly from the root (`module.network.aws_vpc.this.id`) fails — child module internals are not addressable from outside; only explicitly declared outputs ([§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)) are visible to the caller, which is the entire point of encapsulation.

## 6. Production Usage Notes

- **The root module is where provider configuration lives, by convention.** Child modules generally should not contain `provider` blocks of their own (except in specific multi-region/multi-account patterns using passed-in provider aliases, [§13](../Part2/Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md)) — provider configuration is inherited from the root, keeping child modules provider-agnostic and reusable across accounts/regions.
- **Module calls are graph nodes too.** Terraform's dependency graph ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) treats a `module` block as a unit for ordering purposes when other resources reference its outputs — `subnet_id = module.network.public_subnet_id` creates a dependency edge from `aws_instance.bastion` to every resource inside `module.network` that contributes to that output, not just to the module block itself.
- **`for_each`/`count` on module blocks multiply the state namespace exactly like on resources.** `module.web["a"]` and `module.web["b"]` are two fully independent sets of underlying resources — destroying the `for_each` key `"a"` from configuration correctly plans to destroy only that instance's resources, not `"b"`'s.

## 7. Security Considerations

- Because a child module's resources inherit whatever provider credentials the root module's provider configuration supplies, a compromised or malicious child module source (especially one pulled from an untrusted Git URL or registry namespace, [§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)/[§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)) has exactly the same blast radius as hand-written root-module resources — module trust boundaries deserve the same scrutiny as third-party code dependencies generally.
- Sensitive values passed as inputs into a child module ([§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)) still land in state under that module's `module.<name>.` prefix — module boundaries organize state, they do not protect against the state-file secrets exposure covered in [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md).
- Pin module sources to specific versions or commit SHAs ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) rather than tracking a mutable branch (`ref=main`) — an unpinned Git source means the next `terraform init` can silently pull in changed, unreviewed code with full provider credentials at apply time.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                                  | Likely Cause                                                                                                            | Resolution Path                                                                                                                                                                                 |
| -------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Error: Unsupported attribute` referencing `module.network.aws_vpc.this`                                 | Attempting to reach a child module's internal resource directly instead of a declared output                            | Add an explicit `output` block in the child module ([§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)) and reference `module.network.<output_name>`                                        |
| `terraform state list` shows resources with no `module.` prefix that were expected to be inside a module | Resources were declared directly in the root module instead of inside the intended child module's source directory      | Move the resource block into the child module's files, or use `terraform state mv` ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) if it already exists in state |
| Two calls to the same module source produce a "duplicate resource" plan error                            | Module called twice without `count`/`for_each` and without distinguishing `module` block names                          | Give each call a unique `module "<name>"` block name, or use `for_each`/`count` on a single call for near-identical instances                                                                   |
| `terraform apply` unexpectedly destroys and recreates every resource inside a module                     | The module's `source` argument changed (e.g., path typo, or a version bump that changes the underlying source location) | Run `terraform plan` and inspect carefully; verify `source`/`version` are unchanged if recreation was not intended                                                                              |

## 9. Best Practices

- Keep the root module thin: prefer composing well-defined child modules over writing large volumes of resources directly at the root, once a configuration passes a small handful of resources.
- Name `module` blocks for what they represent, not for their source directory (`module "app_network"` rather than `module "network_module_v2"`) — the name becomes a permanent part of every resource's state address inside it, and renaming later requires a `state mv`.
- Treat every module boundary as a place worth documenting inputs/outputs clearly ([§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)) — the whole value of the root/child split evaporates if callers still need to read the child's internals to use it correctly.

## 10. Common Anti-Patterns / Mistakes

- **Treating "module" as meaning "third-party/registry module" only.** Any local directory of `.tf` files is a module the moment something calls it with a `module` block — teams that reserve the word for registry sources often under-modularize their own repeated root-module code.
- **Renaming a `module` block casually.** Because the block's name (`module "network"`) is baked into every resource's state address beneath it, renaming it without a corresponding `terraform state mv` ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) causes Terraform to plan destroying and recreating every resource inside — a common cause of unplanned production outages during "just a cleanup" refactor.
- **Putting provider blocks inside reusable child modules.** This hardcodes the module to a specific account/region/alias and breaks the reuse case that modules exist for in the first place — provider configuration should flow in from the root ([§13](../Part2/Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md)).

## 11. Interview Questions

**🎯 Beginner:** _"What is the root module in Terraform?"_
**Model answer:** The root module is the module Terraform loads from whatever directory you run a command like `terraform apply` in. It's not a special file or block — every Terraform configuration has exactly one root module by definition, even a simple one with no `module` blocks at all. Any `module` blocks inside it call child modules.
_What the interviewer is probing for:_ Whether the candidate understands "module" as a directory-based, positional concept rather than something requiring special syntax.

**🎯 Intermediate:** _"If you call the same child module twice, how does Terraform tell the two sets of resources apart in state?"_
**Model answer:** Each `module` block has its own name (e.g., `module "web"`), and every resource inside that module call is addressed with a `module.<name>.` prefix, like `module.web.aws_instance.app`. If the module block itself uses `count` or `for_each`, each instance also gets an index or key, e.g., `module.web["a"].aws_instance.app` and `module.web["b"].aws_instance.app` — two fully independent resource sets in state despite sharing the same source code.
_What the interviewer is probing for:_ Concrete understanding of module state addressing, not just "modules are reusable."

**🎯 Senior:** _"A teammate renamed a `module` block from `module "net"` to `module "network"` purely for readability, then ran `terraform plan` and saw dozens of resources marked for destroy-and-recreate. Why, and how should this have been handled?"_
**Model answer:** The module block's name is part of every contained resource's state address (`module.net.aws_vpc.this` vs. `module.network.aws_vpc.this`). Terraform's plan is computed by diffing configuration against state by address — since `module.network.aws_vpc.this` doesn't exist in state (only `module.net.aws_vpc.this` does), Terraform sees a new resource to create and an old one, at the old address, with nothing in configuration pointing to it, to destroy. This should have been handled with `terraform state mv 'module.net' 'module.network'` ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) before or alongside the configuration rename, which updates the state addresses without touching real infrastructure at all.
_What the interviewer is probing for:_ Whether the candidate connects "renaming is a state-address change" to the concrete `state mv` remediation, showing they understand state as an addressed, not positional, record.

**🎯 Architect:** _"You're designing the module structure for a platform team that will own ~15 reusable child modules consumed by ~40 application teams' root modules. What governs whether something becomes a module boundary versus staying as root-module resources, and how does that decision interact with state?"_
**Model answer:** The primary criterion is the combination of (a) genuine reuse across multiple consumers with a stable, well-understood interface, and (b) a natural unit of ownership/change — a module boundary works best when the platform team can version and evolve it ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) somewhat independently of any one consumer's root module. Each module boundary is also a state-addressing boundary, which has operational consequences: consumers get natural `-target=module.name` scoping ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) for partial applies, `terraform state list` output stays organized by module rather than flat, and blast radius for a bad apply is easier to reason about per-module. The trade-off is that over-modularizing (turning every three-resource pattern into its own versioned module) adds indirection, extra `terraform init` provider/module resolution overhead, and version-pinning maintenance burden across 40 consumers for marginal reuse benefit — so the practical rule of thumb is: module it when at least two real consumers need the same pattern with genuinely different inputs, not preemptively.
_What the interviewer is probing for:_ Systems-level judgment about when abstraction earns its cost, tied concretely to the state-addressing and versioning mechanics rather than abstract "reusability" platitudes.

## 12. Common Misconceptions

1. **"A module is a special kind of file."** It's an ordinary directory of `.tf` files; nothing marks it as a module except being referenced by a `module` block (or being the directory you run Terraform from, making it the root).
2. **"Child modules have their own separate state file."** They don't — a module call's resources live inside the same state file as the root module (or the same remote backend state), just under a `module.<name>.` address prefix. Separate state files come from separate root module / backend configurations ([§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md)), not from module nesting.
3. **"You need the registry to use modules."** Local directory sources (`source = "./modules/network"`) are just as valid a module source as a registry or Git source ([§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)) — the registry is a distribution mechanism, not a requirement for modularity.
4. **"Renaming a module block is a harmless refactor."** As shown above, it changes every contained resource's state address and, without `state mv`, produces a destroy-and-recreate plan.

## 13. 🔑 Key Takeaways

- Every Terraform configuration has exactly one root module — the directory a command is invoked against — and zero or more child modules called from it via `module` blocks.
- A module is any directory of `.tf` files; there is no special syntax that marks a directory as a module.
- Every `module` block instance creates its own namespace in state addressing: `module.<name>.<resource_type>.<resource_name>`, extended further by `count`/`for_each` keys and by nesting.
- Module calls participate fully in Terraform's dependency graph — resources outside a module that reference its outputs correctly depend on everything inside the module that produces those outputs.
- Renaming a `module` block changes state addresses for everything inside it and requires `terraform state mv` to avoid a destroy/recreate plan.

## 14. Related Concepts & What's Next

[§56](./Section-56-Part8-Module-Structure-and-Conventions.md) covers the actual file-layout conventions used inside a well-structured module (`main.tf`, `variables.tf`, `outputs.tf`, `README.md`). [§57](./Section-57-Part8-Module-Inputs-and-Outputs.md) details how inputs and outputs form a child module's public interface. [§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md) covers the three ways to source a module (local, registry, Git). [§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md) and [§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md) return to the state-addressing mechanics introduced here for targeted applies and state refactors, respectively.

**Next Section:** [§56](./Section-56-Part8-Module-Structure-and-Conventions.md) — `Section-56-Part8-Module-Structure-and-Conventions.md`
