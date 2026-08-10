# Section 11 (Part 2): The Resource Graph: Dependency Resolution and DAG Construction

## 1. Definition

**Plain language:** Terraform doesn't run through your configuration file top to bottom. Instead, it first figures out which resources depend on which other resources — a subnet needs a VPC to exist first, an EC2 instance needs the subnet — and builds a map of those dependencies. Then it processes that map, creating everything that has no unmet dependencies first, and things that depend on those results only after they're done. Independent resources with no relationship to each other get created at the same time, in parallel.

**Precise definition:** Terraform models every configuration as a **Directed Acyclic Graph (DAG)** — a set of **vertices** (resources, data sources, providers, variables, outputs, and internal meta-nodes) connected by **directed edges** representing dependency relationships, with the guarantee that the graph contains no cycles. Terraform Core builds this graph during the earliest phase of both `plan` and `apply` by statically analyzing configuration for two kinds of dependency: **implicit dependencies**, inferred automatically whenever one resource's argument references another resource's attribute (e.g., `subnet_id = aws_subnet.main.id`), and **explicit dependencies**, declared via the `depends_on` meta-argument ([§35](../Part5/Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md)) when no attribute reference exists but an ordering constraint is still required. Once built, Terraform performs a **topological sort** on the graph to determine a valid execution order — an ordering where every vertex appears only after all vertices it depends on — and then walks the graph using a **worker pool**, executing all currently-unblocked (dependency-satisfied) nodes **concurrently**, up to the concurrency limit set by `-parallelism` (default 10), before unblocking and executing their dependents.

> 💡 **Tip:** The graph is built **separately and independently for create/update operations versus destroy operations** — Terraform actually walks the _reverse_ of the dependency graph for destroys, tearing things down in the opposite order they were created in (dependents destroyed before their dependencies) — which is why deleting a VPC that still has an attached subnet in the graph fails safely rather than orphaning resources, and why `terraform destroy` order is not simply "apply order in reverse of the file," it's reverse of the _dependency_ order, which is a different thing when your file isn't already dependency-ordered.

## 2. Why This Matters

- **The graph — not file order, not declaration order — is what determines execution sequence.** A resource declared at the top of a `.tf` file with no dependencies on anything below it may still be created _after_ resources declared later, if those later resources happen to have no dependencies and the graph scheduler picks them up first; relying on file order to reason about behavior is a category error.
- **Parallelism is a direct, deliberate consequence of the graph model, not an incidental optimization.** Provisioning 50 independent S3 buckets takes roughly the time of provisioning one (up to the parallelism limit), because the graph correctly identifies they have no relationship to each other — this is why Terraform scales well operationally compared to naive sequential scripting.
- **Dependency cycles are structurally impossible to apply, and Terraform catches them before touching any infrastructure.** A configuration where resource A implicitly depends on B and B implicitly (or explicitly) depends on A fails at the graph-construction/validation stage with a clear cycle error — before any API calls are made — rather than partially applying and leaving infrastructure in an inconsistent state.
- **Understanding the graph is the single highest-leverage skill for diagnosing "why did Terraform do X before Y" incidents**, especially unexpected destroy-then-create orderings, unexpected parallel API rate-limiting, and `-target` ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) behavior, all of which are graph phenomena.

## 3. Prerequisites and Dependencies

Builds on [§8](./Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md) (provider RPC boundary — the graph is what decides _when_ to make each RPC call) and [§9](./Section-09-Part2-Provider-Configuration-and-Version-Constraints.md) (provider configuration — provider nodes are themselves vertices in the graph, covered further in [§13](./Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md)). Assumes basic familiarity with resource block syntax as a concept (full syntax in [§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md)) — attribute-reference dependency detection is explained here at the mechanism level even though full resource block anatomy comes later. [§12](./Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md) (next section) builds directly on this section's DAG to explain the full refresh/plan/apply execution sequence that walks it. [§28](../Part4/Section-28-Part4-terraform-console-and-terraform-graph.md) (`terraform graph`) is the CLI command that visualizes exactly what this section describes conceptually.

## 4. Architecture / Conceptual Diagram

```text
Configuration:
  resource "aws_vpc" "main" { ... }
  resource "aws_subnet" "a"  { vpc_id = aws_vpc.main.id }
  resource "aws_subnet" "b"  { vpc_id = aws_vpc.main.id }
  resource "aws_instance" "web" { subnet_id = aws_subnet.a.id }
  resource "aws_s3_bucket" "logs" { }   # no dependency on anything above

Dependency Graph (edges point FROM dependent TO dependency):

        ┌─────────────────────┐
        │   aws_vpc.main      │
        └──────────┬──────────┘
             ┌─────┴─────┐
             ▼           ▼
   ┌──────────────┐ ┌─────────────┐        ┌────────────────────┐
   │aws_subnet.a  │ │aws_subnet.b │        │ aws_s3_bucket.logs │  ◄── independent
   └──────┬───────┘ └─────────────┘        │  (no edges in/out) │
          │                                └────────────────────┘
          ▼
   ┌───────────────────┐
   │ aws_instance.web  │
   └───────────────────┘

Topological sort → valid execution order (one of possibly several):

  Wave 1 (parallel): aws_vpc.main, aws_s3_bucket.logs
  Wave 2 (parallel): aws_subnet.a, aws_subnet.b   (both unblocked once VPC exists)
  Wave 3:            aws_instance.web              (unblocked once subnet.a exists)

  -parallelism=10 (default) means up to 10 unblocked nodes execute
  concurrently within any wave; aws_s3_bucket.logs has no dependency
  at all, so it can run concurrently with wave 1, 2, or 3 equally.
```

- Terraform doesn't literally execute in rigid "waves" — it's a continuous worker-pool model where any node becomes eligible the instant its dependencies complete, but the wave framing is a useful mental simplification.
- Destroy operations walk the **transpose (reversed edges)** of this same graph: `aws_instance.web` is destroyed before `aws_subnet.a`, which is destroyed before `aws_vpc.main`.

## 5. Hands-On

### 5.1 Visualizing the Actual Graph with `terraform graph`

**Purpose:** See the real dependency graph Terraform built for your configuration, rather than inferring it manually.

**Syntax:**

```bash
terraform graph
terraform graph | dot -Tsvg > graph.svg   # requires Graphviz's `dot`
```

**Example usage and expected output:**

```bash
$ terraform graph
digraph {
    compound = "true"
    newrank = "true"
    subgraph "root" {
        "[root] aws_instance.web" -> "[root] aws_subnet.a"
        "[root] aws_subnet.a" -> "[root] aws_vpc.main"
        "[root] aws_subnet.b" -> "[root] aws_vpc.main"
        "[root] aws_s3_bucket.logs"
        "[root] provider[\"registry.terraform.io/hashicorp/aws\"]"
    }
}
```

**Production usage example:** When onboarding a large, unfamiliar Terraform codebase, rendering `terraform graph | dot -Tsvg` gives a genuine architectural map of resource relationships that's often more accurate and more current than any hand-maintained diagram, since it's generated directly from the live configuration.

**Common errors:** `terraform graph` requires an initialized working directory (`terraform init` first) — running it beforehand fails with a provider-schema-related error, since Core needs provider schemas loaded to fully resolve some dependency edges.

### 5.2 Implicit Dependencies via Attribute References

**Purpose:** The default, preferred way to create a dependency edge — simply reference another resource's attribute.

**Syntax:**

```hcl
resource "<type>" "<name>" {
  <argument> = <other_resource_type>.<other_resource_name>.<attribute>
}
```

**Example usage and expected output:**

```hcl
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "a" {
  vpc_id     = aws_vpc.main.id   # creates an implicit dependency edge
  cidr_block = "10.0.1.0/24"
}
```

```bash
$ terraform apply
aws_vpc.main: Creating...
aws_vpc.main: Creation complete after 2s [id=vpc-0a1b2c3d]
aws_subnet.a: Creating...
aws_subnet.a: Creation complete after 1s [id=subnet-0e5f6g7h]
```

**Production usage example:** The overwhelming majority of real-world dependency relationships in Terraform configurations are expressed this way — attribute references are the idiomatic mechanism, and configurations that instead rely heavily on `depends_on` for relationships that could be expressed via attribute reference are a common review flag ([§35](../Part5/Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md) covers this trade-off in depth).

**Common errors:** Referencing an attribute that isn't actually known until after apply (e.g., a computed ID) inside a context that requires a known value _before_ apply, such as a `count` or `for_each` expression, produces `The "count" value depends on resource attributes that cannot be determined until apply` — this is the graph's dependency-ordering constraint surfacing as a plan-time error.

### 5.3 Explicit Dependencies via `depends_on`

**Purpose:** Force an ordering constraint when no attribute reference exists to make the dependency implicit — typically for side effects not visible in resource arguments (e.g., IAM policy propagation, or provisioner ordering).

**Syntax:**

```hcl
resource "<type>" "<name>" {
  # ...
  depends_on = [<other_resource_type>.<other_resource_name>]
}
```

**Example usage and expected output:**

```hcl
resource "aws_iam_role_policy" "app" {
  role   = aws_iam_role.app.id
  policy = data.aws_iam_policy_document.app.json
}

resource "aws_instance" "app" {
  # No attribute of aws_instance references the policy directly,
  # but the instance's IAM role needs the policy attached before boot.
  depends_on = [aws_iam_role_policy.app]
}
```

```bash
$ terraform plan
  # aws_iam_role_policy.app will be created
  # aws_instance.app will be created (after aws_iam_role_policy.app)
```

**Production usage example:** Explicit `depends_on` is a legitimate, common pattern for ensuring an IAM policy or security group rule is fully attached before a compute resource that relies on those permissions at boot time starts up, when Terraform's own attribute-tracking can't see that runtime dependency.

**Common errors:** Overusing `depends_on` for relationships attribute references would already capture creates redundant graph edges that make the graph harder to reason about and can mask a design that should instead pass data through outputs/attributes; also, `depends_on` accepts only resource/module references, not arbitrary expressions — attempting `depends_on = [var.some_flag]` is a syntax error.

## 6. Production Usage Notes

- **The graph is rebuilt on every single `plan` and `apply` invocation** — it is never cached or persisted between runs, which is part of why large configurations with thousands of resources can have a noticeably slow graph-construction phase at the start of every `plan`, independent of how many resources actually change.
- **`-parallelism=<n>`** (default 10) bounds how many graph nodes execute concurrently — lowering it (e.g., `-parallelism=4`) is a common mitigation for cloud API rate-limiting errors during large applies, while raising it can speed up applies with many independent, low-cost resources on providers with generous rate limits ([§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md) covers this trade-off at scale in depth).
- **Modules do not create a separate graph** — a child module's resources are flattened into the same single overall graph as the root module and every other module; there is one graph per Terraform run, not one graph per module, which is why cross-module implicit dependencies (via module outputs consumed as inputs elsewhere) work seamlessly.

## 7. Security Considerations

- Because independent resources can be created in parallel, a misconfigured `-parallelism` combined with a security-sensitive ordering requirement (e.g., a security group must exist before an instance that should never be briefly exposed without it) needs an explicit dependency, not an assumption that "it'll probably be fine" — the graph only guarantees the orderings you've actually declared, implicitly or explicitly.
- Cycle detection failures are a safety feature, not an inconvenience — a configuration that would create infrastructure in an ambiguous or contradictory order is rejected before any API call is made, preventing partially-applied, inconsistent infrastructure states that would be harder to reason about and clean up than an upfront validation error.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                  | Likely Cause                                                                                                                        | Resolution Path                                                                                                                      |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `Error: Cycle: ...` during plan                                                          | Two or more resources form a circular dependency (implicit, explicit, or a mix)                                                     | Run `terraform graph` to visualize the cycle; break it by removing an unnecessary `depends_on` or restructuring attribute references |
| Resource created before something it "obviously" needs (per file order)                  | File order does not equal graph order; no actual dependency edge exists between them                                                | Add an implicit reference or explicit `depends_on` if a real ordering constraint exists                                              |
| Apply fails with cloud API throttling on large configurations                            | Default parallelism (10) exceeds what the target API's rate limits tolerate for bulk creates                                        | Lower `-parallelism` (e.g., `-parallelism=4`)                                                                                        |
| `The "count" value depends on resource attributes that cannot be determined until apply` | `count`/`for_each` expression references a value only known after apply, violating the graph's need to size itself before execution | Restructure to avoid computed values in `count`/`for_each`, or use `-target` to apply the dependency first in a separate step        |

## 9. Best Practices

- Prefer implicit dependencies (attribute references) over `depends_on` whenever an attribute reference is available — it keeps the graph accurate and self-documenting from the configuration itself.
- Use `terraform graph` (piped through Graphviz) periodically on large or unfamiliar configurations to validate that the actual dependency structure matches your mental model.
- Tune `-parallelism` deliberately based on the target API's known rate limits rather than leaving the default unexamined on very large applies.
- Reserve `depends_on` for genuine side-effect dependencies invisible to attribute tracking (IAM propagation, ordering constraints without a data dependency) — not as a general-purpose ordering hammer.

## 10. Common Anti-Patterns / Mistakes

- **Reasoning about execution order by reading the `.tf` file top to bottom.** File order is irrelevant to execution order; only the graph matters, and assuming otherwise leads to genuinely wrong mental models of what a configuration will do.
- **Sprinkling `depends_on` everywhere "just to be safe."** Creates artificial serialization that destroys the parallelism the graph model is designed to provide, slowing down applies for no real benefit when the underlying resources have no actual relationship.
- **Not investigating a `Cycle` error's root cause and instead removing dependencies arbitrarily until the error disappears.** This can silently remove a _necessary_ ordering constraint rather than the _redundant_ one actually causing the cycle — always trace the specific cycle with `terraform graph` before editing.

## 11. Interview Questions

**🎯 Beginner:** _"Does Terraform create resources in the order they appear in the configuration file?"_
**Model answer:** No. Terraform builds a dependency graph from the configuration and determines execution order based on that graph — which resources reference which other resources' attributes — not file order. Resources with no dependency relationship to each other can even be created in parallel, regardless of where they appear in the file.
_What the interviewer is probing for:_ Whether the candidate has internalized the graph-based execution model rather than assuming sequential, file-order execution.

**🎯 Intermediate:** _"What's the difference between an implicit and an explicit dependency, and when would you use `depends_on`?"_
**Model answer:** An implicit dependency is automatically inferred when one resource's argument references another resource's attribute (e.g., `subnet_id = aws_subnet.main.id`) — this is the preferred, idiomatic mechanism. An explicit dependency, declared via `depends_on`, is needed when an ordering requirement exists that isn't visible through any attribute reference — for example, an IAM policy that needs to finish propagating before a dependent compute resource boots, even though the compute resource's arguments don't reference the policy directly. `depends_on` should be reserved for these genuine side-effect cases, not used as a general substitute for attribute references.
_What the interviewer is probing for:_ Practical understanding of when the graph needs help versus when it infers correctly on its own.

**🎯 Senior:** _"Explain what happens, graph-wise, when you run `terraform destroy` on a configuration with a VPC and several dependent subnets and instances."_
**Model answer:** Terraform builds the same dependency graph it would for an apply, then walks it in reverse — the transpose of the graph, following edges backward. Since instances depend on subnets and subnets depend on the VPC in the create direction, the destroy direction reverses that: instances are destroyed first, then subnets, then the VPC last. This ordering is what prevents a destroy from ever attempting to delete a VPC while dependent subnets still reference it, which would otherwise fail at the API level or, worse on some providers, silently orphan resources. It's not "apply order reversed by file position" — it's genuinely the dependency graph's edges reversed and re-topologically-sorted.
_What the interviewer is probing for:_ Real understanding that destroy uses the same graph machinery, not a separately reasoned-about process, and that this is precisely why destroys are generally safe with respect to ordering.

**🎯 Architect:** _"A very large Terraform configuration (thousands of resources) has slow `plan` times even when almost nothing has changed. How much of that is graph construction, and what would you actually do about it?"_
**Model answer:** Graph construction (parsing configuration, building vertices and edges, topological sorting) happens on every single `plan` regardless of how much has actually changed, and its cost scales with configuration size, not with the size of the diff — so on a genuinely large single-state configuration, a nontrivial fraction of `plan` time can be graph-related bookkeeping plus the refresh phase's read calls to every resource ([§12](./Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md)), not just the diff computation itself. The actual fix is rarely "make the graph faster" (there's limited control over that) — it's **state/configuration decomposition**: splitting an overly large single state into multiple independently-planned states (per service, per environment, per bounded context) via [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)–[§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md)'s state management patterns, so each `plan` only has to build and walk a graph sized to its own bounded scope. `-parallelism` tuning and `-target` help at the margins but don't address root-cause graph size; [§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md) covers this scaling problem and its mitigations in full depth.
_What the interviewer is probing for:_ Whether the candidate connects graph mechanics to a real, common production scaling problem and reaches for the correct architectural fix (state splitting) rather than only tuning flags.

## 12. Common Misconceptions

1. **"Resources run in the order they're written in the file."** Execution order is entirely graph-derived; file order has no bearing on it whatsoever.
2. **"`depends_on` is required whenever one resource logically relates to another."** Attribute references already create the dependency edge automatically in the vast majority of cases; `depends_on` is only needed for relationships invisible to attribute tracking.
3. **"Everything in a `plan`/`apply` runs strictly sequentially, one resource at a time."** Independent, unblocked graph nodes run concurrently by default (up to `-parallelism`, default 10) — sequential execution only happens along an actual dependency chain.
4. **"Modules create isolated sub-graphs."** All resources across the root module and every child module are flattened into one single graph per run; modules are an organizational/namespacing construct, not a graph-partitioning one.

## 13. 🔑 Key Takeaways

- Terraform builds a Directed Acyclic Graph from configuration, using implicit (attribute-reference) and explicit (`depends_on`) dependency edges, and executes it via topological sort — not file order.
- Independent, unblocked nodes execute in parallel up to `-parallelism` (default 10), which is why Terraform scales well operationally across large numbers of independent resources.
- Destroys walk the same graph in reverse (dependents destroyed before dependencies), which is what makes `terraform destroy` ordering-safe by default.
- Cycle detection happens before any API call, preventing partially-applied, contradictory infrastructure states.
- The graph is rebuilt fresh on every single `plan`/`apply` and spans the entire configuration across all modules as one unified graph.

## 14. Related Concepts & What's Next

[§9](./Section-09-Part2-Provider-Configuration-and-Version-Constraints.md) covered provider configuration; provider nodes are themselves part of this graph, expanded on in [§13](./Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md)'s alias discussion. [§12](./Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md) (next) walks the full refresh/plan/apply sequence that actually traverses this graph step by step. [§28](../Part4/Section-28-Part4-terraform-console-and-terraform-graph.md) covers the `terraform graph` command's CLI usage in more operational depth. [§35](../Part5/Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md) returns to `depends_on` specifically within the broader resource dependency discussion in Part 5. [§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md) covers graph size and parallelism as a performance-at-scale concern for very large configurations.

**Next Section:** [§12](./Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md) — `Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md`
