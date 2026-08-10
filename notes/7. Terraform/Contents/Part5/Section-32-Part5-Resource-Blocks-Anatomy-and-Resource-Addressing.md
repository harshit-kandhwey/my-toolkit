# Section 32 (Part 5): Resource Blocks: Anatomy and Resource Addressing

## 1. Definition

**Plain language:** A resource block is where you actually tell Terraform "I want this specific piece of infrastructure to exist" — a virtual machine, a storage bucket, a DNS record. Everything before this point in the roadmap (providers, HCL syntax, the CLI workflow) exists to support this one moment: declaring a resource. Every resource you declare gets a unique "address" — a name Terraform (and you) use to refer to it anywhere else in configuration, in `plan` output, in state, and on the CLI.

**Precise definition:** A **resource block** is the fundamental unit of infrastructure declaration in Terraform, with the syntax `resource "<PROVIDER_TYPE>" "<LOCAL_NAME>" { ... }`. The first label is the **resource type** (e.g., `aws_instance`), which determines what kind of object is managed and which provider handles it (the prefix before the first underscore, by convention, maps to a provider — `aws_instance` → the `aws` provider). The second label is the **local name**, an identifier scoped to the current module, used only within configuration to reference this resource — it is never sent to the provider API. Together, `<TYPE>.<LOCAL_NAME>` (optionally suffixed with an instance key for `count`/`for_each`, and prefixed with `module.<name>.` when inside a child module) forms a **resource address** — a globally unique path Terraform uses internally in its dependency graph and state file, and that you use explicitly with `terraform state`, `terraform plan -target`, and `terraform import`.

> 💡 **Tip:** A resource's local name (the second label) is cosmetic to the provider but load-bearing to Terraform — renaming it in configuration does not rename the underlying cloud object, it makes Terraform think the old address was deleted and a new one should be created. Renaming a resource safely requires either a `moved` block or `terraform state mv` ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)), never just editing the label in place.

## 2. Why This Matters

- **Resource addresses are the vocabulary of the entire CLI workflow.** `terraform state show`, `terraform plan -target`, `terraform import`, and `terraform state mv` ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md), [§37](./Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) all operate on resource addresses — getting the addressing model wrong makes every one of those commands error-prone.
- **The dependency graph ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) is built from resource addresses.** Terraform infers what must be created, updated, or destroyed before what, based on which addresses reference which other addresses inside `${}`-style expressions.
- **State is keyed by resource address.** The state file ([§47](../Part7/Section-47-Part7-The-State-File-Format-terraform-tfstate-Deep-Dive.md)) is fundamentally a map from resource address to the last-known real-world object; a mismatch between configuration addresses and state addresses is the single most common cause of "Terraform wants to destroy and recreate something that didn't actually change."
- **Multi-instance resources (`count`/`for_each`, [§34](./Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)) extend the address with an instance key** — `aws_instance.web[0]` or `aws_instance.web["primary"]` — and getting this distinction wrong is a frequent source of unwanted resource replacement during refactors.
- **Module-qualified addresses (`module.network.aws_vpc.main`) are how targeting and state operations reach into child modules ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)–[§62](../Part8/Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md))** — without understanding the address grammar, operating on a resource nested three modules deep is guesswork.

## 3. Prerequisites and Dependencies

This section assumes HCL block/argument syntax ([§15](../Part3/Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md)), file organization conventions ([§16](../Part3/Section-16-Part3-Terraform-File-Structure-and-Conventions.md)), and the provider plugin model ([§8](../Part2/Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md)–[§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)) already covered in Part 2 and Part 3 — a resource block cannot be understood in isolation from the provider that implements it. [§4](../Part1/Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md) (Terraform architecture overview) previewed resources as one of Terraform's core concepts; this section is the deep dive. [§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md) (the resource graph) depends directly on the addressing model introduced here, and [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)–[§47](../Part7/Section-47-Part7-The-State-File-Format-terraform-tfstate-Deep-Dive.md) (state) store data keyed by exactly these addresses.

## 4. Architecture / Conceptual Diagram

```text
                     RESOURCE ADDRESS GRAMMAR

  [module.<module_name>.[module.<nested_name>.]]<resource_type>.<local_name>[<instance_key>]

  Examples, least to most complex:

  aws_instance.web
      └─ root module, single instance (no count/for_each)

  aws_instance.web[0]
      └─ root module, count-based instance, index 0

  aws_instance.web["primary"]
      └─ root module, for_each-based instance, key "primary"

  module.network.aws_vpc.main
      └─ resource "main" inside a child module called "network"

  module.network.module.subnets.aws_subnet.this["us-east-1a"]
      └─ resource nested two modules deep, itself for_each-keyed

  ┌─────────────────────────────────────────────────────────┐
  │  resource "aws_instance" "web" {                        │
  │            └──┬──────┘   └┬┘                            │
  │          resource type   local name                     │
  │          (picks provider  (scoped to this module;       │
  │           + schema)        never sent to the API)       │
  │    ami           = "ami-0abcdef1234567890"              │
  │    instance_type = "t3.micro"                           │
  │  }                                                      │
  └─────────────────────────────────────────────────────────┘
```

- The **resource type prefix** (`aws_`, `azurerm_`, `google_`, `random_`, `null_`) is a naming convention, not a hard rule enforced by Terraform core — it maps to whichever provider is configured to handle that type in `required_providers` ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)), but the mapping itself is defined by the provider's schema, not the string prefix.
- **Instance keys only exist on resources using `count` or `for_each`** ([§34](./Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)); a resource with neither has exactly one instance and its address never has a trailing `[...]`.
- **Module prefixes stack** for arbitrarily nested child modules ([§61](../Part8/Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md)) — the address is always read left-to-right as a literal path through the module tree down to the resource.

## 5. Hands-On

### 5.1 Declaring a Basic Resource Block

**Purpose:** Establish the minimal, complete anatomy of a resource block — type, name, and arguments.

**Syntax:**

```hcl
resource "<TYPE>" "<LOCAL_NAME>" {
  <argument> = <value>
  # ...
}
```

**Example usage and expected output:**

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"

  tags = {
    Name = "web-server"
  }
}
```

```bash
$ terraform plan
  # aws_instance.web will be created
  + resource "aws_instance" "web" {
      + ami                          = "ami-0abcdef1234567890"
      + instance_type                = "t3.micro"
      + id                           = (known after apply)
      + arn                          = (known after apply)
      + private_ip                   = (known after apply)
      + tags                         = {
          + "Name" = "web-server"
        }
    }

Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Nearly every resource block in a real codebase follows this exact shape — required arguments the provider schema demands (`ami`, `instance_type` here), plus optional arguments like `tags` that most organizations mandate via policy ([§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md), [§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md)) for cost allocation and ownership tracking.

**Common errors:** `Error: Missing required argument` means the provider's schema for that resource type requires an argument you omitted — check the provider's registry documentation ([§10](../Part2/Section-10-Part2-The-Terraform-Registry-and-Sourcing-Providers.md)) for the exact required-vs-optional argument list, since it differs per resource type and is not something Terraform core enforces generically.

### 5.2 Reading Resource Addresses via the CLI

**Purpose:** Confirm how Terraform names a declared resource internally, and how to query that address from the state.

**Syntax:**

```bash
terraform state list
terraform state show <resource_address>
```

**Example usage and expected output:**

```bash
$ terraform state list
aws_instance.web
aws_vpc.main
aws_subnet.public["us-east-1a"]

$ terraform state show aws_instance.web
# aws_instance.web:
resource "aws_instance" "web" {
    ami                    = "ami-0abcdef1234567890"
    id                     = "i-0a1b2c3d4e5f6g7h8"
    instance_type          = "t3.micro"
    tags                   = {
        "Name" = "web-server"
    }
}
```

**Production usage example:** During an incident, `terraform state list | grep aws_instance` is often the fastest way to enumerate every managed instance address before targeting one specifically with `terraform plan -target` ([§37](./Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) or `terraform state show` for a detailed attribute dump.

**Common errors:** `No instance found for the given address` from `terraform state show` almost always means the address string doesn't match exactly — instance keys must be quoted precisely (`["us-east-1a"]`, not `[us-east-1a]`) and are case-sensitive against what's actually in state.

### 5.3 Referencing a Resource's Attributes Elsewhere in Configuration

**Purpose:** Demonstrate that a resource's address is also the expression syntax used to reference its computed attributes from other resources.

**Syntax:**

```hcl
<resource_type>.<local_name>.<attribute>
```

**Example usage and expected output:**

```hcl
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "public" {
  vpc_id     = aws_vpc.main.id       # address used as a value expression
  cidr_block = "10.0.1.0/24"
}
```

```bash
$ terraform plan
  # aws_vpc.main will be created
  # aws_subnet.public will be created
    (depends on aws_vpc.main.id being known after apply)

Plan: 2 to add, 0 to change, 0 to destroy.
```

**Production usage example:** This attribute-reference pattern is how implicit dependencies ([§35](./Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md)) are created — Terraform parses `aws_vpc.main.id` inside `aws_subnet.public`, records that `aws_subnet.public` depends on `aws_vpc.main`, and orders `apply` accordingly, with zero explicit ordering logic written by the author.

**Common errors:** Referencing an attribute that doesn't exist on that resource type (`aws_vpc.main.arn` when the AWS provider's `aws_vpc` schema doesn't expose `arn` in older provider versions) produces `Error: Unsupported attribute` at `plan` time — always check the actual exported attributes in the provider's registry docs rather than assuming AWS console field names map 1:1.

### 5.4 Module-Qualified Resource Addressing

**Purpose:** Show how a resource address extends when the resource lives inside a child module, which matters for `-target`, `state mv`, and reading `plan` output on any non-trivial codebase.

**Syntax:**

```bash
terraform state show module.<module_name>.<resource_type>.<local_name>
terraform plan -target=module.<module_name>.<resource_type>.<local_name>
```

**Example usage and expected output:**

```bash
$ terraform state list
module.network.aws_vpc.main
module.network.aws_subnet.public["us-east-1a"]
module.compute.aws_instance.web[0]
module.compute.aws_instance.web[1]

$ terraform state show module.network.aws_vpc.main
# module.network.aws_vpc.main:
resource "aws_vpc" "main" {
    cidr_block = "10.0.0.0/16"
    id         = "vpc-0a1b2c3d4e5f6g7h8"
}
```

**Production usage example:** In a codebase built from modules (Part 8), essentially every resource address an operator types on the CLI is module-qualified — recognizing this prefix is a prerequisite to using `-target` or `import` correctly against anything beyond the smallest root-module-only project.

**Common errors:** Forgetting the `module.` prefix when targeting a resource that lives inside a child module produces `Error: Resource address ... does not exist` — the resource type and local name alone are not sufficient once module nesting is involved.

## 6. Production Usage Notes

- **Resource addresses are a contract with the state file, not just a config convenience.** Renaming `resource "aws_instance" "web"` to `resource "aws_instance" "app"` without a `moved` block or `terraform state mv` ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) produces a plan showing `aws_instance.web` destroyed and `aws_instance.app` created — Terraform has no way to know these labels refer to the "same" logical resource unless told explicitly.
- **Local names should describe role, not the resource type.** `aws_instance.web` is more useful long-term than `aws_instance.instance_1`, since the type is already encoded in the first label — a redundant local name adds noise without adding information, and a role-based name survives resource-type migrations (e.g., moving from `aws_instance` to `aws_launch_template`-backed autoscaling) better.
- **Address stability matters more as team size grows.** In solo projects, renaming a resource and re-applying is low-stakes. In shared state with CI/CD ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)–[§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)), an unplanned destroy/recreate triggered by a casual rename can take down production — code review of `plan` output specifically for unexpected `# resource will be destroyed` / `# resource will be created` pairs on what should be a no-op rename is a standard safeguard.

## 7. Security Considerations

- Resource attributes are frequently sensitive (database passwords set via an argument, generated private keys) — attributes are stored in plaintext in the state file by default regardless of resource address, so addressing a resource for inspection (`terraform state show`) can expose secrets to anyone with state read access; [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) covers state-level secret risk in depth.
- Because `-target` ([§37](./Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) and `import` ([§52](../Part7/Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md)) operate on precise addresses, an attacker or careless operator with CLI access and state write permission can use `terraform state rm` on a specific address to make Terraform "forget" a resource — the underlying cloud object still exists but is no longer governed by policy checks (Sentinel/OPA, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) on the next apply, a subtle way to bypass governance if state write access isn't tightly scoped.
- Least-privilege IAM for the identity actually running `terraform apply` ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)) matters independently of addressing, but addressing precision is what makes scoped `-target` applies (deliberately touching only one resource) a viable alternative to broad, blast-radius-maximizing full applies in sensitive environments.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                         | Likely Cause                                                                                            | Resolution Path                                                                                                                                                                                                          |
| ------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Plan shows a resource being destroyed and an identically-configured one created | Local name (or module path) was changed in configuration, so the address no longer matches state        | Use `terraform state mv` or a `moved` block ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) to repoint the existing state entry to the new address instead of letting it destroy/recreate |
| `terraform state show <address>` returns "No instance found"                    | Address string doesn't exactly match what's recorded — wrong instance key syntax, missing module prefix | Run `terraform state list` first and copy the exact address string rather than hand-typing it                                                                                                                            |
| `-target` flag errors with "Resource address ... does not exist"                | Targeting a resource inside a child module without the `module.<name>.` prefix                          | Prefix the address with every module level between root and the resource, in order ([§37](./Section-37-Part5-Resource-Targeting-and-Partial-Applies.md))                                                                 |
| Two resources appear to collide on the same address after a copy-paste refactor | Local name was duplicated across two `resource` blocks of the same type in the same module              | Rename one block's local name — local names must be unique per resource type within a module                                                                                                                             |

## 9. Best Practices

- Choose local names that describe the resource's **role** in the architecture (`web`, `primary`, `replica`), not its type or a generic counter — this keeps addresses meaningful in `plan` output and state listings years into a project's life.
- Treat any resource rename as a state operation, not just a text edit — pair every local-name or module-path change with `terraform state mv` or a `moved` block, and verify with `terraform plan` that the diff shows no unintended destroy/create.
- Run `terraform state list` early when picking up an unfamiliar codebase — it is the fastest way to learn the real resource inventory and addressing conventions actually in use, faster than reading every `.tf` file.
- Keep resource type prefixes and provider configuration ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md), [§13](../Part2/Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md)) consistent — mixing aliased and default provider instances on similarly-named resources makes addresses harder to reason about during incident response.

## 10. Common Anti-Patterns / Mistakes

- **Renaming a resource's local name "for readability" without a state operation**, causing an unplanned destroy/recreate that can be catastrophic on stateful resources (databases, persistent volumes) — this is one of the most common causes of unintended production data loss in Terraform-managed environments.
- **Overloading a single resource block to represent multiple logical things** (e.g., one `aws_instance` resource block manually duplicated three times with copy-pasted, slightly-varied arguments) instead of using `count`/`for_each` ([§34](./Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)) — this produces addresses like `aws_instance.web`, `aws_instance.web2`, `aws_instance.web_three` with no consistent addressing pattern, making later automation and targeting error-prone.
- **Hardcoding a resource's expected ID or ARN as a string literal** instead of referencing its address's exported attribute (`aws_vpc.main.id`) — this breaks the implicit dependency graph ([§35](./Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md)) and means Terraform can't guarantee correct ordering or detect drift on that specific linkage.

## 11. Interview Questions

**🎯 Beginner:** _"What are the two labels on a `resource` block, and what does each one do?"_
**Model answer:** The first label is the resource type (e.g., `aws_instance`), which tells Terraform which provider and which schema to use — it determines what kind of infrastructure object is being managed. The second label is the local name, an identifier scoped to the current module that's used only within Terraform configuration and CLI commands to refer to that specific resource — it's never sent to the provider's API and has no effect on the real-world object's name unless a `name`-type argument is separately set inside the block.
_What the interviewer is probing for:_ Basic fluency with the most fundamental syntax construct in Terraform, and specifically not conflating the local name with the cloud resource's actual name/tag.

**🎯 Intermediate:** _"What happens if you rename a resource's local name in configuration and run `terraform apply` without doing anything else?"_
**Model answer:** Terraform has no way to know the renamed block refers to the same logical resource as before — the resource address in state no longer matches any address in configuration, so Terraform plans to destroy the resource at the old address and create a new one at the new address. For anything stateful (a database, a persistent disk) this is potentially destructive. The correct approach is to either add a `moved` block declaring the old and new addresses, or run `terraform state mv` to repoint the existing state entry to the new address before applying, so Terraform recognizes it as the same object.
_What the interviewer is probing for:_ Whether the candidate understands that resource addresses are load-bearing against state, not just cosmetic configuration text.

**🎯 Senior:** _"How does a resource's address change when it's declared with `count` versus `for_each`, and why does that distinction matter during a refactor?"_
**Model answer:** With `count`, the address gets a numeric instance key based on list index — `aws_instance.web[0]`, `[1]`, etc. With `for_each`, the address gets a string key from the map or set — `aws_instance.web["primary"]`. The critical difference during refactors is stability: if a `count`-based list's order changes (an item removed from the middle), every subsequent index shifts, and Terraform sees this as many resources being destroyed and recreated even though most of them are logically unchanged. `for_each` keys are tied to the map/set key itself, not position, so removing one entry only affects that one resource's instance — everything else stays stable. This is the primary reason `for_each` is generally preferred over `count` when list order isn't guaranteed to stay fixed ([§34](./Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) covers this trade-off in full).
_What the interviewer is probing for:_ Real operational understanding of instance-key semantics, not just syntax memorization — this is a frequent source of production incidents when teams migrate from `count` to `for_each` carelessly.

**🎯 Architect:** _"You inherit a 400-resource root module with no child modules, all resources declared with generic local names like `instance_1` through `instance_47`. What's the actual risk here, and how would you approach fixing it without causing an outage?"_
**Model answer:** The immediate risk isn't functional — the infrastructure works — but operational: addresses carry no semantic meaning, so `plan` output, `state list`, and incident-response targeting are all guesswork requiring cross-referencing against a separate spreadsheet or memory of "which instance is which." The deeper risk is that any future refactor (splitting into modules, converting to `for_each`) is far more dangerous when addresses aren't already meaningful, because there's no way to distinguish an intentional address change from an accidental one in review. The fix is incremental, not a single risky rewrite: introduce `moved` blocks (or `state mv` in a controlled maintenance window) resource-by-resource or in small batches, renaming to role-based local names, verifying after each batch that `terraform plan` shows zero destroy/create actions — purely address remapping. This should happen over multiple PRs with `plan` review as the safety gate, never as one giant apply.
_What the interviewer is probing for:_ Whether the candidate can reason about large-scale technical debt remediation with production safety as the primary constraint, not just "the right end state."

## 12. Common Misconceptions

1. **"The resource's local name becomes the resource's name in the cloud provider."** It does not automatically — the local name is Terraform-internal only; the actual cloud object's name/tag is whatever you explicitly set via a `name` or `tags` argument inside the block.
2. **"Resource addresses in state and in configuration are always kept in sync automatically."** They are not — Terraform only updates state to match configuration when you explicitly reconcile a rename via `moved` blocks or `state mv`; otherwise a config rename is read as delete-then-create.
3. **"`count` and `for_each` produce equivalent, interchangeable addressing."** They don't — `count` addresses are positional (`[0]`, `[1]`) and shift when list contents change, while `for_each` addresses are keyed (`["primary"]`) and stay stable regardless of other entries changing ([§34](./Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)).
4. **"A resource address uniquely identifies the cloud object across all of Terraform, permanently."** It only uniquely identifies the object within one state file's addressing scheme — the same real-world object could, in principle, be imported under a completely different address in a different state file, since the address is Terraform's bookkeeping construct, not an inherent property of the cloud resource.

## 13. 🔑 Key Takeaways

- A resource block's syntax is `resource "<TYPE>" "<LOCAL_NAME>" { ... }`; the type picks the provider/schema, the local name is a Terraform-only identifier.
- The full resource address (`[module.path.]TYPE.NAME[instance_key]`) is the vocabulary used across state, CLI targeting, `import`, and the dependency graph — it is not just documentation convenience.
- Renaming a resource's address in configuration without a corresponding state operation (`moved` block or `state mv`) causes Terraform to destroy the old address and create the new one, which is dangerous for stateful resources.
- `count` produces positional, order-sensitive instance keys; `for_each` produces stable, key-based instance keys — this distinction has real consequences during refactors ([§34](./Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) goes deeper).
- Module nesting prepends `module.<name>.` segments to the address for every level of nesting, and every level must be included when targeting or querying state.

## 14. Related Concepts & What's Next

[§33](./Section-33-Part5-Data-Sources-Reading-External-and-Existing-Infrastructure.md) introduces data sources, which use a parallel but distinct address grammar (`data.<TYPE>.<NAME>`) for read-only lookups. [§34](./Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) dives into the `count`/`for_each` instance-key mechanics only previewed here. [§35](./Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md) covers how resource addresses referenced inside expressions create the implicit dependency graph. [§37](./Section-37-Part5-Resource-Targeting-and-Partial-Applies.md) returns to addressing specifically for `-target` and partial-apply workflows. [§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md) covers the full `terraform state` command suite (`list`, `show`, `mv`, `rm`) referenced throughout this section.

**Next Section:** [§33](./Section-33-Part5-Data-Sources-Reading-External-and-Existing-Infrastructure.md) — `Section-33-Part5-Data-Sources-Reading-External-and-Existing-Infrastructure.md`
