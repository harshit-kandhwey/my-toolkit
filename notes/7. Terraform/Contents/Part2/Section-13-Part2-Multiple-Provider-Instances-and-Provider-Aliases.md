# Section 13 (Part 2): Multiple Provider Instances and Provider Aliases

## 1. Definition

**Plain language:** Sometimes one `provider "aws" {}` block isn't enough — you need to provision resources in two different AWS regions in the same configuration, or across two different AWS accounts, or against both AWS and a second, differently-configured AWS provider for a disaster-recovery setup. Terraform lets you declare multiple, separately-configured instances of the _same_ provider type, and you pick which instance a given resource uses with an alias.

**Precise definition:** By default, every resource of a given provider type implicitly binds to that provider's single **default (unaliased) configuration** — the `provider "aws" {}` block with no `alias` argument. To configure additional, independent instances of the same provider (different regions, accounts, credentials, or any other provider-specific setting), you declare additional `provider {}` blocks with a unique `alias = "<name>"` argument. A resource then explicitly selects a non-default provider instance via the `provider = <type>.<alias>` meta-argument (note: no quotes, and it references the provider **local name**, not the resource type string). Each aliased provider instance is a **fully independent vertex in the dependency graph** ([§11](./Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) — plugin process, RPC calls, and all — meaning resources bound to different provider aliases can be created in parallel with no implicit ordering relationship between them unless one explicitly depends on the other.

> 💡 **Tip:** Provider aliasing is the mechanism, but the most common real trigger for needing it is one of exactly three scenarios: **multi-region** (same account, two regions), **multi-account** (different credentials/role entirely), or **disaster-recovery/failover pairs** (a primary and a standby configuration). If you find yourself reaching for an alias for a reason outside those three, pause and ask whether the actual need is better served by **separate root modules/workspaces** ([§69](../Part10/Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md)–[§74](../Part10/Section-74-Part10-Environment-Promotion-Patterns-dev-staging-prod.md)) instead — aliasing everything into one giant configuration with many provider instances is a common source of the "provider sprawl" anti-pattern covered in [§108](../Part15/Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md).

## 2. Why This Matters

- **Multi-region and multi-account provisioning is a routine production requirement, and aliases are the only in-configuration mechanism for it.** Without aliases, a single Terraform configuration is architecturally limited to one configured instance per provider type, forcing artificial workarounds (duplicate configurations, external orchestration) for genuinely common needs like "replicate this S3 bucket to a second region."
- **Modules need explicit provider-passing to work correctly with aliases.** A child module doesn't automatically inherit which aliased provider instance to use — this has to be passed explicitly via a `providers = {}` map ([§58](../Part8/Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)), and getting this wrong is one of the most common real-world module composition bugs teams hit.
- **Provider aliases directly interact with the dependency graph ([§11](./Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) and execution model ([§12](./Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md)).** Because each aliased instance is its own graph vertex, understanding aliasing correctly is necessary to reason about which resources can run in parallel versus which have an implicit relationship through shared configuration.
- **Getting default vs. aliased provider selection wrong silently provisions into the wrong region or account** — one of the more consequential classes of Terraform misconfiguration, since it's not a syntax error, just a resource quietly using the default provider when the author intended the aliased one.

## 3. Prerequisites and Dependencies

Builds directly on [§9](./Section-09-Part2-Provider-Configuration-and-Version-Constraints.md) (Provider Configuration and Version Constraints), which introduced the single-instance `provider {}` block this section extends to multiple instances. Assumes the graph model from [§11](./Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md) (each provider instance is an independent graph vertex). [§14](./Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md) (next section) applies aliasing concretely to AWS/Azure/GCP authentication scenarios. [§58](../Part8/Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md) (Calling Modules) is referenced for how aliased providers are passed into child modules — full module syntax comes later, but the `providers = {}` map concept is previewed here since it's inseparable from aliasing in practice.

## 4. Architecture / Conceptual Diagram

```text
terraform {
  required_providers { aws = { source = "hashicorp/aws", version = "~> 5.60" } }
}

provider "aws" {                    ◄── DEFAULT instance (no alias)
  region = "us-east-1"
}

provider "aws" {
  alias  = "west"                   ◄── ALIASED instance
  region = "us-west-2"
}

provider "aws" {
  alias  = "dr_account"             ◄── ALIASED instance, different account entirely
  region = "us-east-1"
  assume_role { role_arn = "arn:aws:iam::999999999999:role/terraform-dr" }
}

Graph (each provider instance = independent vertex):

┌───────────────────────┐   ┌───────────────────────┐   ┌─────────────────────────┐
│ provider.aws          │   │ provider.aws.west     │   │ provider.aws.dr_account │
│ (default, us-east-1)  │   │ (alias, us-west-2)    │   │ (alias, DR account)     │
└──────────┬────────────┘   └──────────┬────────────┘   └──────────┬──────────────┘
           │                           │                           │
           ▼                           ▼                           ▼
┌─────────────────────────┐   ┌────────────────────────┐   ┌───────────────────────────┐
│resource "aws_instance"  │   │resource "aws_instance" │   │resource "aws_s3_bucket"   │
│  "primary" { ... }      │   │  "secondary" {         │   │  "dr_backup" {            │
│  # implicit default     │   │  provider = aws.west   │   │  provider = aws.dr_account│
└─────────────────────────┘   │  ... }                 │   │  ... }                    │
                              └────────────────────────┘   └───────────────────────────┘

No implicit edge between these three branches — they execute
in parallel (up to -parallelism) unless an explicit depends_on
or attribute reference connects them.
```

## 5. Hands-On

### 5.1 Declaring and Using an Aliased Provider

**Purpose:** Provision the same resource type in two independent configurations of the same provider — the canonical multi-region case.

**Syntax:**

```hcl
provider "<name>" {
  alias  = "<alias_name>"
  <configuration_argument> = <value>
}

resource "<type>" "<name>" {
  provider = <name>.<alias_name>
  # ...
}
```

**Example usage and expected output:**

```hcl
provider "aws" {
  region = "us-east-1"
}

provider "aws" {
  alias  = "west"
  region = "us-west-2"
}

resource "aws_s3_bucket" "primary" {
  bucket = "my-app-primary-bucket"
  # no `provider` argument -> uses the default (us-east-1) instance
}

resource "aws_s3_bucket" "replica" {
  provider = aws.west
  bucket   = "my-app-replica-bucket"
}
```

```bash
$ terraform apply
aws_s3_bucket.primary: Creating...
aws_s3_bucket.replica: Creating...
aws_s3_bucket.primary: Creation complete after 1s [id=my-app-primary-bucket]
aws_s3_bucket.replica: Creation complete after 1s [id=my-app-replica-bucket]
```

**Production usage example:** A standard pattern for S3 Cross-Region Replication setups: the primary bucket resource uses the default provider, the destination bucket resource explicitly uses an aliased provider pointed at the replica region, and the replication configuration resource ties the two together via attribute references — all three provisioned from one configuration, one `apply`.

**Common errors:** `Error: Missing resource instance key` or, more commonly, a resource silently landing in the wrong region because the `provider` argument was simply omitted where it was needed — Terraform does not warn about this; the resource just quietly uses the default provider instance, which is why explicit code review attention to `provider =` arguments matters on multi-region configurations.

### 5.2 Passing Aliased Providers into Child Modules

**Purpose:** Give a child module access to a specific aliased provider instance from the calling (parent) module, since aliasing does not propagate automatically.

**Syntax:**

```hcl
module "<name>" {
  source = "<path>"
  providers = {
    <local_name_in_module> = <name>.<alias_name>
  }
}
```

**Example usage and expected output:**

```hcl
# root module
provider "aws" {
  alias  = "west"
  region = "us-west-2"
}

module "west_bucket" {
  source = "./modules/s3-bucket"
  providers = {
    aws = aws.west   # module's internal "aws" provider local name maps to root's aliased instance
  }
}
```

```hcl
# modules/s3-bucket/main.tf
terraform {
  required_providers {
    aws = { source = "hashicorp/aws" }
  }
}

resource "aws_s3_bucket" "this" {
  # uses whichever "aws" provider instance the caller passed in
  bucket = var.bucket_name
}
```

**Production usage example:** A shared "s3-bucket" module reused across a multi-region deployment is called once per region from the root module, each call passing a different aliased provider instance via `providers = {}` — the module code itself stays region-agnostic and is never duplicated.

**Common errors:** `Error: Module does not support provider configuration` or `Error: Provider configuration not present` — happens when a child module declares its own `provider {}` block internally (modules generally should not, per [§9](./Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)'s production notes) while the caller is also trying to pass one in via `providers = {}`; the two mechanisms conflict, and the fix is removing the module's internal `provider {}` block so it relies entirely on what's passed down.

### 5.3 `for_each` Across Multiple Provider Aliases

**Purpose:** Combine aliasing with meta-arguments to provision a resource across several configured regions/accounts without duplicating resource blocks manually.

**Syntax:**

```hcl
resource "<type>" "<name>" {
  for_each = <map_or_set>
  provider = <name>.<alias_expr>
  # ...
}
```

**Example usage and expected output:**

```hcl
provider "aws" { region = "us-east-1" }
provider "aws" { alias = "west"; region = "us-west-2" }
provider "aws" { alias = "eu";   region = "eu-west-1" }

# NOTE: `provider =` cannot itself be dynamically computed from for_each in
# a single resource block -- each aliased provider still needs its own
# explicit resource block (or module call, per 5.2) referencing it directly.
resource "aws_s3_bucket" "east" { bucket = "app-east" }
resource "aws_s3_bucket" "west" { provider = aws.west; bucket = "app-west" }
resource "aws_s3_bucket" "eu"   { provider = aws.eu;   bucket = "app-eu" }
```

**Production usage example:** Because `provider =` must be a static reference (not a computed expression), teams needing true "loop across N regions" behavior wrap the per-region resource in a module (5.2) and use `for_each` at the **module call** level with one aliased provider passed per module instance — this is the standard, supported pattern for scaling aliasing beyond a handful of hardcoded blocks.

**Common errors:** Attempting `provider = aws[each.key]` or similar dynamic provider selection directly on a resource — this is explicitly unsupported; the `provider` meta-argument must resolve statically, which is precisely why the module + `providers = {}` + `for_each`-on-the-module-call pattern exists as the correct workaround.

## 6. Production Usage Notes

- **Each aliased provider instance is a fully independent plugin process boundary conceptually** (per [§8](./Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md)'s RPC model) even though, in practice, aliased instances of the _same_ provider type reuse the same underlying provider _binary_ process — only the configuration (region, credentials) differs per instance, not the executable.
- **There is no limit on the number of aliases**, but practically, configurations with many aliases (5+) are a strong signal worth revisiting against [§108](../Part15/Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md)'s provider-sprawl anti-pattern — often the better design is separate root configurations orchestrated by a higher-level tool (a CI pipeline matrix, Terragrunt, or Terraform Cloud workspace-per-region) rather than one configuration aliasing across many regions/accounts.
- **The default (unaliased) provider instance is mandatory if any resource of that provider type doesn't specify `provider =`.** Even in a heavily-aliased configuration, Terraform still requires an unaliased `provider {}` block to exist if any resource omits the explicit alias reference — omitting it produces a `Missing required provider configuration` error at plan time.

## 7. Security Considerations

- Aliased providers pointed at different AWS accounts/Azure subscriptions/GCP projects are a common, legitimate pattern for cross-account provisioning (e.g., a central CI role that assumes into per-environment roles) — but this means a single Terraform run, with a single set of top-level credentials, can hold the combined blast radius of every account it's aliased into; scope the base credentials and each aliased `assume_role`/impersonation target with least privilege ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)) rather than granting the base identity broad standing access.
- Because aliasing makes multi-account/multi-region provisioning easy to add incrementally, configurations can accumulate unreviewed account access over time — periodically audit which accounts/subscriptions/projects a configuration's provider blocks actually touch, especially in shared/central infrastructure repositories.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                                     | Likely Cause                                                                                         | Resolution Path                                                                                    |
| ----------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| Resource created in the wrong region/account                                                                | `provider =` argument omitted, silently falling back to the default provider instance                | Audit resource blocks for missing `provider =` on any resource intended to use a non-default alias |
| `Error: Missing required provider configuration`                                                            | No unaliased default `provider {}` block exists, but some resource doesn't specify an explicit alias | Add a default (unaliased) `provider {}` block, even if minimal                                     |
| `Error: Module does not support provider configuration`                                                     | Child module has its own internal `provider {}` block while the caller also passes `providers = {}`  | Remove the module's internal `provider {}` block; rely solely on the caller's `providers` map      |
| Attempting to loop a resource across regions with a dynamic `provider =` expression fails to parse/validate | `provider` meta-argument must be a static reference, not computed                                    | Refactor into a module called once per alias via `for_each` at the module-call level (5.2/5.3)     |

## 9. Best Practices

- Always name aliases descriptively (`alias = "west"`, `alias = "dr_account"`) rather than generically (`alias = "b"`) — the alias name is the only thing distinguishing provider instances in resource code and review.
- Prefer passing aliased providers into modules explicitly (`providers = {}`) over duplicating resource blocks per region/account manually.
- Treat a configuration accumulating many aliases as a signal to reconsider whether separate root configurations, workspaces ([§69](../Part10/Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md)), or an orchestration layer would be a cleaner architecture than continued aliasing.
- Never let a child module declare its own hardcoded `provider {}` block if it's meant to be reusable across regions/accounts — let the caller control provider configuration entirely.

## 10. Common Anti-Patterns / Mistakes

- **Provider sprawl: a single configuration accumulating a dozen+ aliases for every region/account combination a team has ever needed.** Becomes unreviewable and tightly couples unrelated environments into one blast radius ([§108](../Part15/Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md) covers this pattern in depth as a mastery-level anti-pattern).
- **Omitting `provider =` and assuming Terraform will "figure out" which instance was intended based on resource naming or comments.** Terraform always falls back silently to the default instance; there is no inference based on naming.
- **Hardcoding a `provider {}` block inside a reusable child module "for convenience."** Breaks the module's reusability across any region/account other than the one hardcoded, and conflicts with callers trying to pass their own provider configuration.
- **Trying to dynamically select a provider alias per loop iteration directly on a resource's `provider =` argument.** Unsupported; requires restructuring into a module call looped with `for_each` instead.

## 11. Interview Questions

**🎯 Beginner:** _"How do you configure Terraform to create resources in two different AWS regions in the same configuration?"_
**Model answer:** Declare a second `provider "aws" {}` block with a unique `alias` argument set to the second region, alongside the default (unaliased) provider block for the first region. Resources intended for the second region reference it explicitly via the `provider = aws.<alias_name>` meta-argument; any resource that omits `provider =` uses the default instance.
_What the interviewer is probing for:_ Basic familiarity with the alias mechanism as the standard multi-region solution.

**🎯 Intermediate:** _"Why doesn't a child module automatically use whichever aliased provider instance the calling module happens to have configured?"_
**Model answer:** Provider configuration is explicitly not inherited implicitly by child modules in Terraform's design — a module must either declare its own provider configuration (generally discouraged for reusable modules) or receive one passed explicitly from the caller via the `providers = {}` map, mapping the module's internal provider local name to a specific instance (default or aliased) in the caller. This explicitness is deliberate: it makes it clear, at the module call site, exactly which account/region/credentials a given module invocation will use, rather than relying on implicit, easy-to-misjudge inheritance.
_What the interviewer is probing for:_ Understanding that provider passing to modules is an explicit, deliberate design choice, not an oversight or a gap to work around.

**🎯 Senior:** _"A team wants to provision an identical set of resources across five AWS regions using one Terraform configuration. What's the correct pattern, and what doesn't work?"_
**Model answer:** What doesn't work: trying to use `for_each` directly on a resource with a dynamically computed `provider =` expression — the `provider` meta-argument must be statically resolvable, so this fails to plan. The correct pattern is wrapping the resource(s) in a child module, declaring one `provider "aws" { alias = "<region>" }` block per region in the root module, and calling the module once per region (either five explicit module blocks, or a `for_each`-driven module call using Terraform 1.x's dynamic provider-passing improvements where supported), each call passing its region's aliased provider instance via `providers = {}`. This keeps the module itself region-agnostic while the root module explicitly enumerates and wires up each region's provider instance.
_What the interviewer is probing for:_ Practical knowledge of a real, common scaling limitation of aliasing and its correct, supported workaround.

**🎯 Architect:** _"A configuration has grown to alias the AWS provider across 8 regions and 3 accounts (24 total instances) to support a global rollout. What are the risks of this design, and what would you recommend instead?"_
**Model answer:** The risks are architectural, not just cosmetic: all 24 provider instances' credentials/blast radius are held by a single Terraform run's identity, meaning a single misconfigured resource or compromised pipeline credential has combined reach across every region and account; the state file for this one configuration becomes enormous and slow to plan/refresh ([§12](./Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md)'s refresh-cost discussion, [§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)'s scale concerns); and any change anywhere in the configuration risks an accidental `plan` touching resources across unrelated regions/accounts if graph dependencies aren't carefully isolated. The better design is decomposing into per-region and/or per-account root configurations (or Terraform Cloud/Enterprise workspaces, one per region/account) with a thin, higher-level orchestration layer (a CI pipeline matrix, or a tool like Terragrunt) driving consistent application of the same module across each independently-stated target — trading one large aliased configuration for many small, independently blast-radius-limited ones sharing common module code.
_What the interviewer is probing for:_ Whether the candidate recognizes that aliasing has a real architectural ceiling and can design the state/blast-radius decomposition that replaces it at scale — not just describe more aliasing.

## 12. Common Misconceptions

1. **"You need a separate Terraform installation or configuration file per region/account."** A single configuration can hold multiple provider instances of the same type via aliasing — no separate installation is needed for multi-region/account support at a small-to-medium scale.
2. **"Aliased providers automatically pass down into every child module."** They do not — provider configuration must be explicitly passed via `providers = {}`, or the module must declare and configure its own (generally discouraged for reusable modules).
3. **"You can dynamically compute which provider alias a resource uses per loop iteration."** The `provider =` meta-argument must resolve statically; true per-iteration alias selection requires wrapping the resource in a module called with `for_each`.
4. **"An aliased provider instance is a separate plugin binary process from the default instance."** Aliased instances of the same provider type typically share the same underlying provider binary process; only the configuration (credentials, region) differs per instance, not the executable itself.

## 13. 🔑 Key Takeaways

- Multiple, independently configured instances of the same provider type are declared via additional `provider {}` blocks with a unique `alias` argument; resources opt in via `provider = <type>.<alias>`.
- Omitting `provider =` on a resource silently falls back to the default (unaliased) instance — this is a common, hard-to-spot source of resources landing in the wrong region/account.
- Aliased providers do not automatically propagate into child modules; they must be explicitly passed via a `providers = {}` map.
- The `provider =` meta-argument must be statically resolvable — looping across provider aliases requires wrapping resources in a module and looping the module call, not the resource directly.
- Heavy aliasing (many regions/accounts in one configuration) is a scaling and blast-radius risk worth weighing against decomposing into separate root configurations or workspaces.

## 14. Related Concepts & What's Next

[§9](./Section-09-Part2-Provider-Configuration-and-Version-Constraints.md) introduced the single-instance `provider {}` block this section extends. [§11](./Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)'s graph model explains why aliased provider instances execute independently and in parallel by default. [§14](./Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md) (next) applies aliasing directly to concrete AWS, Azure, and GCP multi-account/multi-region authentication patterns. [§58](../Part8/Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md) covers the full `providers = {}` module-calling syntax previewed here. [§108](../Part15/Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md) revisits provider sprawl as a named anti-pattern in the mastery-level Part 15 material.

**Next Section:** [§14](./Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md) — `Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md`
