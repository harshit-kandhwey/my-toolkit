# Section 35 (Part 5): Resource Dependencies: Implicit vs. Explicit (depends_on)

## 1. Definition

**Plain language:** Terraform needs to know what order to create (or destroy) things in — you can't attach a subnet to a VPC that doesn't exist yet. Most of the time, Terraform figures this out on its own just by looking at which resources reference which other resources' values. But sometimes two resources genuinely depend on each other in a way that isn't visible through any attribute reference — a database must finish initializing before an application can safely connect to it, even though the application's configuration doesn't literally reference any database attribute. For those cases, you tell Terraform the dependency explicitly.

**Precise definition:** Terraform builds a directed acyclic graph (DAG, [§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) of every resource, data source, and module in a configuration. **Implicit dependencies** are inferred automatically whenever one block's arguments reference another block's address or attribute (e.g., `vpc_id = aws_vpc.main.id`) — Terraform parses these references at graph-construction time and orders operations accordingly, with no extra syntax required. **Explicit dependencies**, declared with the `depends_on` meta-argument (a list of resource/module addresses), force an ordering relationship between blocks that share no attribute reference at all — used when a dependency exists at the level of "this must happen after that for the infrastructure to function correctly" but isn't expressible as a data reference.

> 💡 **Tip:** `depends_on` is a deliberate escape hatch, not a default tool. If you find yourself reaching for `depends_on` frequently across a codebase, it is usually a signal that the underlying dependency actually _should_ be expressed as a data reference (even a value you don't otherwise need, just to make the relationship explicit to Terraform) — implicit dependencies are self-documenting and automatically stay correct as configuration evolves; `depends_on` lists must be manually maintained and can silently go stale.

## 2. Why This Matters

- **Incorrect ordering causes real apply failures** — attempting to create a resource that references another not-yet-created resource's ID produces an API error from the provider, not a graceful Terraform-side wait, if the dependency isn't captured at all.
- **The dependency graph is what makes parallelism safe** ([§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) — Terraform can create unrelated resources concurrently precisely because it knows, from the graph, which pairs of resources have no ordering constraint between them; missing dependencies risk race conditions, and unnecessary explicit dependencies needlessly serialize applies that could otherwise run in parallel.
- **Destroy order is the reverse of create order**, derived from the same graph — a dependency Terraform doesn't know about can cause a resource to be destroyed while something still depends on it still exists, causing destroy failures or, worse, orphaned resources.
- **`depends_on` is a common source of both over-use and under-use bugs** — under-use causes flaky applies that "usually work" until parallelism or timing changes expose a missing ordering constraint; over-use causes unnecessarily serialized, slower applies and graphs that are harder to reason about.
- **This directly feeds into module design ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)–[§62](../Part8/Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md))**: `depends_on` can be applied to an entire `module` block, forcing every resource inside a child module to wait on something outside it — a pattern with real performance and correctness trade-offs at scale.

## 3. Prerequisites and Dependencies

This section assumes [§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md) (resource addressing, since `depends_on` takes a list of resource addresses) and [§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md) (the resource graph / DAG construction) as direct prerequisites — depends_on cannot be understood without first understanding what the graph it's modifying actually is. [§33](./Section-33-Part5-Data-Sources-Reading-External-and-Existing-Infrastructure.md) (data sources) is relevant since data sources can both have and be targets of dependencies. [§23](../Part3/Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md) previewed `depends_on` alongside the other meta-arguments; this section is its dedicated deep dive.

## 4. Architecture / Conceptual Diagram

```text
  IMPLICIT DEPENDENCY (inferred from attribute reference)

  resource "aws_vpc" "main" { ... }
  resource "aws_subnet" "public" {
    vpc_id = aws_vpc.main.id     ◄── Terraform parses this reference,
  }                                  automatically adds an edge:
                                     aws_subnet.public → depends on → aws_vpc.main

           aws_vpc.main
                │
                ▼  (implicit edge, inferred)
           aws_subnet.public


  EXPLICIT DEPENDENCY (no attribute reference exists, but ordering still required)

  resource "aws_db_instance" "primary" { ... }
  resource "aws_instance" "app" {
    depends_on = [aws_db_instance.primary]   ◄── manually declared edge;
    # app's config never actually references                              no attribute of
    # any attribute of aws_db_instance.primary                            aws_db_instance.primary
  }                                                                       is used by app

           aws_db_instance.primary
                │
                ▼  (explicit edge, manually declared)
           aws_instance.app


  GRAPH CONSTRUCTION AND EXECUTION ORDER

  terraform plan/apply builds one DAG from ALL implicit + explicit edges
        │
        ▼
  Resources with no dependency between them → can run CONCURRENTLY
        (bounded by -parallelism, default 10, §109)
  Resources with a dependency edge → strictly ordered
        (dependency must complete before dependent starts, on apply;
         reverse order on destroy)
```

- Implicit dependencies are discovered by Terraform's HCL parser scanning for expressions of the form `<resource_address>.<attribute>` inside any argument value — this happens automatically, with zero explicit author effort, as a direct consequence of writing `aws_subnet.public.vpc_id = aws_vpc.main.id`.
- Explicit dependencies via `depends_on` add graph edges with no corresponding data flow — the dependent resource's configuration is unaffected by the dependency's values; only ordering is affected.
- **Destroy order is the graph traversed in reverse** — whatever created after whatever it depended on, is destroyed before what it depended on, preserving referential safety in both directions.

## 5. Hands-On

### 5.1 Implicit Dependency via Attribute Reference

**Purpose:** Show the default, no-extra-syntax mechanism Terraform uses for nearly all dependency ordering.

**Syntax:**

```hcl
resource "<TYPE_A>" "<NAME_A>" { ... }
resource "<TYPE_B>" "<NAME_B>" {
  <arg> = <TYPE_A>.<NAME_A>.<attribute>
}
```

**Example usage and expected output:**

```hcl
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "public" {
  vpc_id     = aws_vpc.main.id
  cidr_block = "10.0.1.0/24"
}
```

```bash
$ terraform graph
digraph {
  "aws_vpc.main" -> "aws_subnet.public" [style=dashed]  # order simplified for readability
}

$ terraform apply
aws_vpc.main: Creating...
aws_vpc.main: Creation complete after 2s [id=vpc-0a1b2c3d4e5f6g7h8]
aws_subnet.public: Creating...
aws_subnet.public: Creation complete after 1s [id=subnet-0a1b2c3d]

Apply complete! Resources: 2 added, 0 changed, 0 destroyed.
```

**Production usage example:** This is the mechanism behind essentially every correctly-ordered multi-resource configuration in production Terraform — VPCs before subnets, subnets before instances, IAM roles before role attachments — all inferred purely from reference chains, with no author ever writing an explicit ordering statement.

**Common errors:** Reversing intent — writing `aws_vpc.main.cidr_block = aws_subnet.public.cidr_block` (a parent referencing a child) — creates a cyclical or backwards dependency that either produces `Error: Cycle` or silently orders things in an unintended direction; the direction of the reference _is_ the direction of the dependency.

### 5.2 Explicit Dependency with `depends_on` — No Attribute Link Exists

**Purpose:** Force an ordering relationship between resources that don't reference each other's attributes but still require one to complete before the other starts.

**Syntax:**

```hcl
resource "<TYPE_B>" "<NAME_B>" {
  depends_on = [<TYPE_A>.<NAME_A>]
}
```

**Example usage and expected output:**

```hcl
resource "aws_iam_role_policy" "app_policy" {
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.app.json
}

resource "aws_instance" "app" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t3.micro"
  iam_instance_profile = aws_iam_instance_profile.app.name

  # The instance's user_data script calls AWS APIs on first boot using this
  # role's permissions, but no argument here literally references
  # aws_iam_role_policy.app_policy's attributes — the dependency is
  # behavioral (the policy must be attached before boot), not data-driven.
  depends_on = [aws_iam_role_policy.app_policy]
}
```

```bash
$ terraform apply
aws_iam_role_policy.app_policy: Creating...
aws_iam_role_policy.app_policy: Creation complete after 1s
aws_instance.app: Creating...
aws_instance.app: Creation complete after 32s

Apply complete! Resources: 2 added, 0 changed, 0 destroyed.
```

**Production usage example:** IAM eventual-consistency and boot-time API calls are one of the most common real-world reasons for explicit `depends_on` — an instance's `user_data` ([§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) may call AWS APIs immediately on boot that require a policy attachment which has no attribute the instance resource itself would ever reference.

**Common errors:** Forgetting `depends_on` here produces intermittent, hard-to-reproduce failures — sometimes the policy attachment finishes first anyway (Terraform's default parallelism doesn't guarantee ordering absent a graph edge) and the apply succeeds; other times the instance boots and fails its first API call before the policy is attached. This class of bug is notoriously hard to diagnose precisely because it isn't consistently reproducible.

### 5.3 `depends_on` on a Data Source

**Purpose:** Force a data source's read to wait until after a specific resource is created, when the data source's own arguments don't naturally reference that resource.

**Syntax:**

```hcl
data "<TYPE>" "<NAME>" {
  depends_on = [<resource_type>.<resource_name>]
}
```

**Example usage and expected output:**

```hcl
resource "aws_s3_bucket_policy" "logs" {
  bucket = aws_s3_bucket.logs.id
  policy = data.aws_iam_policy_document.logs_policy.json
}

data "aws_s3_bucket_object" "readme" {
  bucket = aws_s3_bucket.logs.id
  key    = "README.md"

  # Ensures the bucket policy (which may restrict access) is fully applied
  # before this read is attempted, even though this data source's own
  # arguments don't reference the policy resource directly.
  depends_on = [aws_s3_bucket_policy.logs]
}
```

```bash
$ terraform plan
  # aws_s3_bucket_policy.logs will be created
  # data.aws_s3_bucket_object.readme will be read during apply
    (config refers to values not yet known, or depends_on forces deferral)
```

**Production usage example:** Less common than resource-to-resource `depends_on`, but relevant whenever a data source reads something whose availability or correctness depends on a resource's side effects (a policy, an attachment) that the data source's own query arguments don't reference.

**Common errors:** Overusing `depends_on` on data sources unnecessarily defers their read from plan time to apply time ([§33](./Section-33-Part5-Data-Sources-Reading-External-and-Existing-Infrastructure.md) [§4](../Part1/Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md)), which reduces plan-time visibility — the data source's resolved value no longer shows concretely in `terraform plan` output, only after `apply` actually runs.

### 5.4 `depends_on` on an Entire Module

**Purpose:** Force every resource inside a child module to wait on a resource (or another module) outside it, when no individual output/input passes the dependency through naturally.

**Syntax:**

```hcl
module "<NAME>" {
  source     = "..."
  depends_on = [<resource_or_module_address>]
}
```

**Example usage and expected output:**

```hcl
module "vpc" {
  source     = "./modules/vpc"
  cidr_block = "10.0.0.0/16"
}

module "compute" {
  source     = "./modules/compute"
  vpc_id     = module.vpc.vpc_id   # normally sufficient as an implicit dependency
  depends_on = [module.vpc]         # rarely needed in addition, shown for illustration
}
```

**Production usage example:** Module-level `depends_on` is most often needed when a module's inputs don't fully capture every real dependency — for example, a module that provisions DNS records that another, seemingly-unrelated module's resources implicitly assume already exist for health checks to pass, with no actual variable passed between them.

**Common errors:** Module-level `depends_on` forces **every** resource inside the dependent module to wait on **every** resource inside the depended-on module, even where only a small subset actually has a real ordering requirement — this is a common cause of unnecessarily slow, over-serialized applies at scale ([§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)), and is usually a sign the module boundary or inputs should be redesigned instead.

## 6. Production Usage Notes

- **Implicit dependencies should be preferred wherever a genuine attribute value can be threaded through** — even referencing a value that isn't strictly needed by the dependent resource's actual configuration (sometimes assigned to an unused local, though this is a minor anti-pattern in itself) is often cleaner and more maintainable than an explicit `depends_on` list that must be kept in sync by hand.
- **`depends_on` does not eliminate the _need_ for the dependency to actually be correct at the API level** — it only orders Terraform's own operations; if the underlying cloud API has its own eventual-consistency delays even after a resource is reported "created," `depends_on` alone won't fix that (some providers expose explicit "wait for ready" resources or data sources for exactly this reason).
- **Module-level `depends_on` is a blunt instrument** — for large modules with many independent internal resources, it's usually better to expose a specific output from the "depended-on" module and thread it into the "dependent" module's input, creating a precise implicit dependency instead of an all-or-nothing module-level explicit one.

## 7. Security Considerations

- Missing an explicit dependency between an IAM policy attachment and a resource that relies on it at boot time (§5.2) is a common source of a specific security-adjacent failure mode: the resource might boot with **no** permissions at all during a race, causing it to either fail (safe but broken) or, in worse designs, fall back to overly permissive default credentials — reviewing IAM-adjacent ordering carefully during code review is worthwhile.
- `depends_on` lists, being manually maintained, can silently go stale when refactoring — a resource removed from a `depends_on` list during a refactor with no test coverage can silently reintroduce a race condition that previously "happened to work," a category of regression that's hard to catch without deliberately re-testing ordering-sensitive paths.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                             | Likely Cause                                                                                                  | Resolution Path                                                                                                                                                                                                 |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Apply intermittently fails referencing a resource/policy "not found" or "not ready" | A real dependency exists but isn't captured as either an attribute reference or `depends_on`                  | Add an explicit `depends_on` (or thread a real attribute reference) between the two resources                                                                                                                   |
| `Error: Cycle: ...` during plan or apply                                            | Two or more resources reference each other, directly or transitively, forming a circular dependency           | Break the cycle by removing one direction of the reference, often by introducing an intermediate resource or restructuring                                                                                      |
| Apply is much slower than expected for a large, mostly-independent set of resources | Overuse of module-level or blanket `depends_on`, serializing resources that don't actually need ordering      | Replace broad `depends_on` with precise implicit references, or remove unnecessary ordering constraints ([§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) |
| Destroy fails with a dependency-violation error from the provider                   | Terraform's destroy order (reverse of create) doesn't match a real-world constraint not captured in the graph | Add the missing dependency (implicit or explicit) so destroy order also respects it correctly                                                                                                                   |

## 9. Best Practices

- Exhaust implicit dependency options (referencing a real attribute, even a superficially unused one, purely to establish the graph edge) before reaching for `depends_on`.
- Keep `depends_on` lists as small and precise as possible — depend on the specific resource that has the real ordering requirement, not a whole module, whenever the module's outputs can express the same precision.
- Comment every `depends_on` usage explaining _why_ the dependency exists, since — unlike implicit dependencies — the reasoning isn't visible from any data flow in the code; future readers (including yourself) will not be able to infer it otherwise.
- Periodically audit `depends_on` usage during refactors — a stale or now-unnecessary explicit dependency is easy to leave behind and can obscure genuine parallelism opportunities.

## 10. Common Anti-Patterns / Mistakes

- **Reaching for `depends_on` by default instead of first checking whether a real attribute reference could express the same dependency implicitly** — this produces harder-to-maintain code with dependency lists that must be manually kept correct.
- **Adding `depends_on` at the module level when only a small subset of resources inside actually require ordering**, needlessly serializing an entire module's apply and hiding the real, narrower dependency.
- **Omitting a genuinely required dependency because "it usually works anyway"** — Terraform's default parallelism means missing dependencies often don't fail every single run, which makes this class of bug particularly dangerous: it passes code review and testing intermittently before failing in production under different timing or load.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between an implicit and an explicit dependency in Terraform?"_
**Model answer:** An implicit dependency is automatically inferred by Terraform when one resource's configuration references another resource's address or attribute — no extra syntax is needed. An explicit dependency is manually declared using the `depends_on` meta-argument, used when two resources have a real ordering requirement but no attribute reference connects them, so Terraform has no other way to know the ordering matters.
_What the interviewer is probing for:_ Basic understanding that dependency ordering is primarily automatic, and `depends_on` is the deliberate exception, not the default mechanism.

**🎯 Intermediate:** _"Give a concrete example of a situation where you'd need `depends_on` because an implicit dependency can't capture the relationship."_
**Model answer:** A common example is an EC2 instance whose `user_data` script calls AWS APIs on first boot that require an IAM policy to already be attached to its role. The instance resource's configuration doesn't reference any attribute of the `aws_iam_role_policy` resource — it only references the IAM role/instance profile, not the policy attachment itself — so there's no data flow Terraform can use to infer that the policy must exist before the instance boots. Without an explicit `depends_on = [aws_iam_role_policy.app_policy]`, Terraform's default parallelism might create both resources concurrently, and the instance could boot and attempt its API calls before the policy is actually attached, causing an intermittent failure.
_What the interviewer is probing for:_ Whether the candidate has hit this in practice or can reason concretely about behavioral (not data) dependencies, rather than giving only an abstract definition.

**🎯 Senior:** _"Your team has a module-level `depends_on` between two large modules, and applies have gotten noticeably slower over the last year as both modules grew. How would you diagnose and fix this?"_
**Model answer:** First, confirm the slowdown is actually caused by unnecessary serialization rather than just more total resources — `terraform graph` or `-json` plan output ([§30](../Part4/Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md)) can show which resources are actually gated behind the module-level `depends_on` edge versus which would run in parallel anyway. If the module-level dependency was added because only a handful of specific resources in the dependent module genuinely need something from the depended-on module, the fix is to remove the blanket module-level `depends_on` and instead expose a precise output from the depended-on module, threading it as an input into only the specific resources inside the dependent module that actually need the ordering — converting one all-or-nothing explicit edge into several precise implicit edges. This restores parallelism for every resource in the dependent module that never actually needed to wait, while preserving correctness for the ones that do.
_What the interviewer is probing for:_ Practical performance-diagnosis skill connecting a graph-level cause (over-broad dependency) to a concrete, testable fix, not just "use depends_on less."

**🎯 Architect:** _"How would you establish a team-wide policy on when `depends_on` is and isn't acceptable, for an organization with dozens of Terraform modules maintained by different teams?"_
**Model answer:** I'd frame the policy around a default-deny posture: `depends_on` requires an inline comment explaining the specific real-world reason no attribute reference could express the dependency, and code review should treat an uncommented or module-level `depends_on` as a request for change, not an automatic approval. I'd also push module authors toward exposing more granular outputs specifically so that consuming teams can express dependencies implicitly rather than reaching for `depends_on` out of convenience when a module's interface is too coarse. Practically, this could be partially enforced with a linter ([§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md), tflint or a custom rule) flagging module-level `depends_on` and any `depends_on` usage lacking an adjacent comment, backed by periodic audits during larger refactors to catch dependencies that have gone stale. The underlying principle is that dependency information should live as close as possible to the data that actually creates it — implicit references self-document and stay correct as code changes, while manually-maintained `depends_on` lists are exactly the kind of thing that silently rots across dozens of modules owned by different teams over time.
_What the interviewer is probing for:_ Organizational and process-design thinking — whether the candidate can turn a technical best practice into an enforceable, scalable team policy, not just restate the best practice itself.

## 12. Common Misconceptions

1. **"`depends_on` is needed whenever two resources are related."** Most relationships are already captured implicitly via attribute references; `depends_on` is only for the narrower case where no such reference exists but ordering is still required.
2. **"Terraform applies resources in the order they're written in the file."** It does not — execution order is entirely determined by the dependency graph, not file position; resources with no dependency relationship may apply in any order, including concurrently.
3. **"`depends_on` guarantees the depended-on resource is fully functional, not just 'created,' before the dependent resource starts."** It only guarantees Terraform's own "creation complete" signal has been received from the provider API — some cloud resources report as created before they're actually ready to serve requests (a separate eventual-consistency concern some providers address with dedicated "wait" resources).
4. **"Adding more `depends_on` relationships is always safer."** Excess dependencies serialize applies unnecessarily and obscure the graph's real structure, without adding any correctness benefit for relationships that don't actually require ordering.

## 13. 🔑 Key Takeaways

- Implicit dependencies, inferred automatically from attribute references, handle the overwhelming majority of ordering requirements in Terraform with zero extra syntax.
- `depends_on` is a deliberate, manually-maintained escape hatch for ordering requirements that exist at the infrastructure/behavioral level but have no corresponding attribute reference — most commonly IAM/permission timing issues.
- Destroy order is the dependency graph traversed in reverse; a missing dependency can cause failures on both create and destroy.
- `depends_on` can target resources, data sources, and entire modules — module-level usage is the bluntest and should be a last resort compared to precise, per-resource implicit or explicit dependencies.
- Overusing `depends_on` needlessly serializes applies and hides the graph's real structure; underusing it causes intermittent, timing-dependent failures that are notoriously hard to reproduce and debug.

## 14. Related Concepts & What's Next

[§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md) (the resource graph) is the foundational structure this section's dependency mechanics operate on. [§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md) established the resource addressing grammar `depends_on` lists reference. [§36](./Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md) covers the `lifecycle` block, whose `create_before_destroy` argument interacts closely with dependency ordering during resource replacement. [§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md) covers `-parallelism` and performance implications of graph shape at scale, directly relevant to the over-serialization anti-pattern discussed here.

**Next Section:** [§36](./Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md) — `Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md`
