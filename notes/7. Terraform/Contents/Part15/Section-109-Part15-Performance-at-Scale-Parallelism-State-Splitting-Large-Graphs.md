# Section 109 (Part 15): Performance at Scale: -parallelism, State Splitting, Large Graphs

## 1. Definition

**Plain language:** Once a Terraform configuration manages hundreds of resources, `plan` and `apply` can start taking minutes instead of seconds, and the risk of one apply touching something it shouldn't goes up. This section is about the specific, real mechanisms for keeping Terraform fast and safe at that scale — how much work it does concurrently, how to split state so each apply's dependency graph stays small, and why reaching for `-target` as a routine fix is the wrong lever.

**Precise definition:** Terraform's `-parallelism=N` flag controls the maximum number of concurrent resource operations (create/update/delete, and provider API calls) the graph walker will execute at once during `apply` (default 10). **State splitting** is the practice of dividing what would otherwise be one large state into multiple independently-applied root modules, each with a smaller, more tractable dependency graph and a narrower blast radius (extending the blast-radius argument from [§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md)'s giant-state anti-pattern into the concrete mechanics of how to fix it). **Large dependency graphs** refers to the DAG Terraform builds from resource references ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) — its size and shape directly determine both the theoretical maximum concurrency `-parallelism` can exploit and how much of the graph a single apply necessarily touches.

> 💡 **Tip:** `-parallelism` controls throughput _within_ a single state's apply; state splitting controls how much work — and how much risk — exists inside any single apply in the first place. They solve different problems. Raising `-parallelism` on a giant, tangled state makes a slow apply somewhat faster; it does nothing about that apply's blast radius. Splitting state makes both the apply faster (smaller graph) and safer (narrower blast radius) — which is why it's the structural fix and `-parallelism` tuning is a secondary lever, not a substitute.

## 2. Why This Matters

- **Apply latency directly affects delivery velocity.** A `plan`/`apply` cycle that takes 15 minutes instead of 90 seconds materially slows every PR's feedback loop, especially in CI/CD pipelines ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) run on every change.
- **Graph size is the real ceiling on parallelism's benefit.** `-parallelism` only helps for operations the dependency graph says can run concurrently — a long, narrow chain of dependent resources (A depends on B depends on C...) gets no benefit from raising it no matter how high the value, because the graph itself is the bottleneck, not the concurrency setting.
- **Provider API rate limits interact directly with parallelism.** Cranking `-parallelism` up on a provider with aggressive rate limiting (some cloud APIs throttle aggressively under bursts) can make an apply slower or cause failures, not faster — this is a common, non-obvious trap.
- **State splitting is the mechanism that actually enforces blast-radius boundaries** discussed abstractly in [§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md) and structurally in [§106](./Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md) — it's not just a performance optimization, it's the primary safety mechanism against a giant state's worst failure mode.
- **`-target` is tempting but dangerous as a routine large-graph workaround** — understanding exactly why it's an anti-pattern for anything but genuine emergency use ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) prevents a team from normalizing a practice that quietly produces inconsistent state.

## 3. Prerequisites and Dependencies

This section assumes solid understanding of the resource graph and DAG construction ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)), Terraform's execution model ([§12](../Part2/Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md)), remote state and backends ([§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md)–[§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)), and resource targeting ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) — it synthesizes all of these into a coherent scaling strategy. [§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md)'s giant-state-file anti-pattern is the problem this section provides the concrete fix for.

## 4. Architecture / Conceptual Diagram

```text
BEFORE: ONE GIANT STATE, ONE GIANT GRAPH

┌───────────────────────────────────────────────────────────┐
│  root module state (single backend key)                   │
│                                                           │
│  networking (40) ──► platform (60) ──► app-a (30)         │
│                                    └──► app-b (35)        │
│                                    └──► app-c (28)        │
│                                                           │
│  terraform apply walks the ENTIRE graph (193 resources)   │
│  every time, even for a one-line app-c change.            │
│  -parallelism=10 helps within this walk, but the walk     │
│  itself is unavoidably large.                             │
└───────────────────────────────────────────────────────────┘

AFTER: SPLIT STATE, SMALLER INDEPENDENT GRAPHS

┌──────────────┐    outputs consumed via     ┌──────────────┐
│  networking  │    remote_state data        │   platform   │
│  state (40)  │ ───────────────────────►    │   state (60) │
└──────────────┘    source (§42, §33)        └──────────────┘
                                                      │
                                      remote_state outputs
                                                      ▼
                          ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
                          │   app-a      │  │   app-b      │  │   app-c      │
                          │   state (30) │  │   state (35) │  │   state (28) │
                          └──────────────┘  └──────────────┘  └──────────────┘

A change to app-c only ever walks app-c's own 28-resource graph.
`terraform_remote_state` (or a data source reading platform's
outputs) is a ONE-WAY read dependency, not a shared graph —
app-c's apply cannot touch platform's or networking's resources.
```

- The critical shift from "before" to "after": cross-root-module dependencies become **data reads** of another state's outputs (`terraform_remote_state` data source, or an equivalent output published to a shared parameter store), not shared graph edges within one Terraform run — this is what actually shrinks both graph size and blast radius simultaneously.
- `-parallelism` operates entirely within a single graph walk; it has no effect on the number of separate `apply` runs needed across split states, each of which is invoked independently (often in a CI pipeline stage per root module, [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)).

## 5. Hands-On

### 5.1 Tuning `-parallelism`

**Purpose:** Show correct, deliberate use of `-parallelism` and the tradeoffs of raising or lowering it.

**Syntax:**

```bash
terraform apply -parallelism=N
```

**Example usage and expected output:**

```bash
$ terraform apply -parallelism=30
Plan: 84 to add, 0 to change, 0 to destroy.
# more operations proceed concurrently — faster wall-clock time
# IF the graph has enough independent (non-dependent) resources
# AND the provider API doesn't start throttling

$ terraform apply -parallelism=2
# apply against a provider known to hard rate-limit bursts
Plan: 84 to add, 0 to change, 0 to destroy.
# fewer concurrent API calls — slower wall-clock, but avoids
# 429 Too Many Requests errors mid-apply
```

**Production usage example:** Teams provisioning against providers with known aggressive rate limits (some SaaS provider APIs, certain cloud APIs during specific operations like IAM propagation) deliberately lower `-parallelism` in CI for those specific root modules, while leaving the default (10) or raising it for root modules against providers that handle bursts well and have large graphs of genuinely independent resources (e.g., creating 50 near-identical S3 buckets via `for_each`).

**Common errors:** Assuming raising `-parallelism` always makes `apply` faster — for a graph that's mostly a long dependency chain (each resource waits on the previous), most of the 84 "to add" resources in the example above may not actually be eligible to run concurrently regardless of the flag, because the graph's edges — not the flag — determine what can run in parallel.

### 5.2 Splitting State with `terraform state mv` and `moved` Blocks

**Purpose:** Show the actual mechanics of splitting an oversized state into independent root modules without destroying and recreating resources.

**Syntax:**

```bash
# Step 1: in the OLD root module, move resources destined for a new state
terraform state mv 'module.app_c' '../app-c-root/module.app_c' \
  -state-out=../app-c-root/terraform.tfstate
```

```hcl
# Step 2: in the NEW root module (app-c-root), reference platform's outputs
# instead of relying on being in the same graph
data "terraform_remote_state" "platform" {
  backend = "s3"
  config = {
    bucket = "org-tfstate"
    key    = "platform/terraform.tfstate"
    region = "us-east-1"
  }
}

resource "aws_ecs_service" "app_c" {
  cluster = data.terraform_remote_state.platform.outputs.ecs_cluster_id
  # ...
}
```

**Example usage and expected output:**

```bash
$ terraform state mv 'module.app_c' '../app-c-root/module.app_c' \
    -state-out=../app-c-root/terraform.tfstate
Move "module.app_c" to "module.app_c"
Successfully moved 1 object(s).

# In the OLD root module afterward:
$ terraform plan
Plan: 0 to add, 0 to change, 0 to destroy.   # app_c resources cleanly gone from this state

# In the NEW app-c-root:
$ terraform plan
Plan: 0 to add, 0 to change, 0 to destroy.   # matches real infra — nothing recreated
```

**Production usage example:** State-splitting projects are almost always done incrementally, one bounded subsystem at a time, verified with a diff-free `plan` immediately before and after each move — this is real, careful surgery on production state, and teams typically start with the lowest-risk, most clearly-bounded subsystem to validate the process before touching anything business-critical ([§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md)'s Architect interview answer describes this sequencing).

**Common errors:** Forgetting to update the _consuming_ configuration's references (still pointing at `module.app_c.some_output` from within the old root module) after moving resources out — the old root module will error on plan with a reference to a module that no longer exists in its state, which is expected and resolved by removing the stale reference along with the move.

## 6. Production Usage Notes

- **`-parallelism` tuning is a secondary optimization, applied after state is already reasonably scoped.** Raising it on an already-giant, tangled state buys marginal wall-clock improvement while leaving the actual structural problem (blast radius, review difficulty) fully intact — teams sometimes reach for it first because it's a one-flag change, when state splitting is the change that actually matters.
- **`terraform_remote_state` is a read-only, one-time-per-plan dependency, not a live link.** A downstream root module reading an upstream state's outputs sees whatever those outputs were at the _downstream_ module's last `plan`/`apply` — if the upstream state changes, the downstream module doesn't automatically know until its own next plan, which is the correct and expected behavior for deliberately decoupled state, but worth being explicit about with teams new to the pattern.
- **Large graphs slow down `plan` and `refresh` too, not just `apply`.** Every `plan` (including read-only ones in CI) walks the graph and, by default, refreshes resource state from the provider API — a large state means slow `plan`s even when nothing is being changed, which is often the more painful, more frequent cost compared to occasional slow applies.

## 7. Security Considerations

- Splitting state along ownership boundaries lets execution-role permissions ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)) be scoped per state — the CI role that applies `app-c`'s root module needs no permissions over `networking` or `platform`'s resources at all, which a giant shared state cannot offer regardless of how careful the pipeline logic is.
- `terraform_remote_state` data sources reading another team's state require read access to that state's backend (e.g., an S3 bucket) — this is a real cross-boundary permission grant and should be scoped narrowly (read-only, specific state key) rather than broad bucket-wide access, to avoid one team's misconfigured root module being able to read unrelated states' potentially sensitive outputs.
- Raising `-parallelism` significantly increases the number of concurrent credentialed API calls a CI runner makes — this is rarely a direct security issue but can trip anomaly-detection systems (a burst of API calls from one CI identity) that are tuned to flag exactly that pattern as suspicious; worth coordinating with a security team before large increases in shared CI environments.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                       | Likely Cause                                                                                    | Resolution Path                                                                                                                |
| --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `apply` fails intermittently with `429 Too Many Requests` from the cloud provider             | `-parallelism` set too high for a rate-limited provider/account                                 | Lower `-parallelism` for that root module's CI job; check provider-specific rate-limit documentation                           |
| Raising `-parallelism` produces little to no wall-clock improvement                           | The dependency graph is a long chain with few genuinely independent resources                   | Inspect with `terraform graph`; consider restructuring resource dependencies or splitting state rather than tuning parallelism |
| `terraform plan` in a downstream root module shows stale values after an upstream change      | `terraform_remote_state` read the upstream state before the upstream's latest `apply` completed | Re-run downstream `plan` after confirming upstream `apply` finished; this is expected decoupled behavior, not a bug            |
| A `terraform state mv` during a splitting project leaves the old root module erroring on plan | A reference to the moved module/resource still exists in the old root module's configuration    | Remove the stale reference from the old configuration; re-run `plan` to confirm a clean, empty diff                            |

## 9. Best Practices

- Treat state splitting as the primary lever for both performance and blast-radius control at scale; treat `-parallelism` tuning as a secondary, provider-aware optimization applied after state is already well-scoped.
- Split along real ownership and dependency boundaries (team, system, environment) — mirroring the structural boundaries discussed in [§106](./Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md) and [§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md) — not arbitrarily by resource count alone.
- Verify every state-splitting `state mv` operation with a diff-free `plan` immediately before and after, on both the source and destination root modules, before considering the move complete.
- Benchmark `-parallelism` empirically per root module/provider combination rather than assuming one global value is optimal everywhere — a value that's ideal for one provider's rate limits may cause failures against another.

## 10. Common Anti-Patterns / Mistakes

- **Using `-target` as a routine substitute for state splitting.** `-target` narrows a single apply's scope without addressing the state's actual blast radius for every other apply against it, and repeated use risks the applied state diverging from what a full plan would show — reserve it for genuine emergency/recovery scenarios ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)), never as standard operating procedure for a large graph.
- **Raising `-parallelism` as a first response to slow applies without checking whether the graph even has parallelizable structure** — wasted tuning effort on a chain-shaped graph where the flag can't help.
- **Splitting state without replacing the removed graph edges with explicit `terraform_remote_state` (or equivalent) reads** — silently relying on "it happened to apply in the right order when they were one state" and then being surprised when independent applies of the split states run in an unexpected order relative to each other.
- **Treating a large `plan`/`apply` time as purely a tooling problem to tune away** rather than recognizing it as a signal that the underlying state/graph structure needs to change ([§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md)'s connection between anti-patterns and their root causes applies directly here).

## 11. Interview Questions

**🎯 Beginner:** _"What does the `-parallelism` flag control in Terraform?"_
**Model answer:** It sets the maximum number of resource operations (creates, updates, deletes, and related provider API calls) Terraform will execute concurrently during `apply`, defaulting to 10. It doesn't change what gets applied, only how much of the independent, non-dependent work happens at the same time.
_What the interviewer is probing for:_ Basic accuracy about what the flag actually does, as opposed to vague "makes it faster" answers.

**🎯 Intermediate:** _"You raise `-parallelism` from 10 to 50 and see no improvement in apply time. Why might that be?"_
**Model answer:** Parallelism can only help for graph nodes that are independent of each other — if the resource graph is mostly a long dependency chain (each resource references the previous one's output), there's little or nothing eligible to run concurrently regardless of how high the flag is set, since Terraform still has to walk the graph in dependency order. The bottleneck in that case is the graph's shape, not the concurrency ceiling.
_What the interviewer is probing for:_ Understanding that `-parallelism` is bounded by actual graph structure, not a universal throughput dial.

**🎯 Senior:** _"Walk me through how you'd split an oversized shared state into two independent root modules without downtime or resource recreation."_
**Model answer:** Identify a clean boundary in the existing graph — ideally an already-modularized subtree with minimal cross-references to the rest of the state. Use `terraform state mv` (with `-state-out` pointing at a new state file/backend, or `moved` blocks for the newer declarative approach) to relocate the target resources into the new root module's state without touching real infrastructure. Immediately verify both the old and new root modules produce a diff-free `plan` — confirming no resource was accidentally left behind, duplicated, or marked for recreation. Update the new root module's configuration to reference anything it needs from the old one via `terraform_remote_state` (reading the old module's published outputs) instead of relying on shared-graph resource references, since those no longer exist across the split. Update the old root module to remove references to what moved out. Only after both plan cleanly do CI pipelines get updated to apply them as separate stages/jobs.
_What the interviewer is probing for:_ Concrete, correct command-level knowledge of the splitting mechanism, not just the conceptual justification for doing it.

**🎯 Architect:** _"Your organization's single 'platform' state has grown to 800 resources and takes 25 minutes to plan. Leadership wants this fixed in the next sprint without risking an outage. How do you approach it?"_
**Model answer:** Reject the sprint-timeline framing directly but constructively — a full remediation of an 800-resource shared state is not safely compressible into one sprint without meaningfully raising outage risk, and committing to that timeline would itself be the anti-pattern. Instead, propose an incremental plan with a first-sprint deliverable that's real progress without being the whole fix: audit `terraform state list` to identify the two or three most clearly-bounded, lowest-risk subsystems (something with few cross-references to the rest of the graph, ideally already its own module), and split just those first, each individually verified with diff-free plans before and after. That alone measurably shrinks the shared state and reduces its plan time and blast radius, proves the splitting process safely on lower-stakes systems, and establishes the `terraform_remote_state` pattern the remaining splits will reuse. Communicate to leadership that this is a multi-sprint program with each increment independently valuable and independently low-risk, rather than a single big-bang cutover — and that attempting the full 800-resource split in one sprint is the choice that actually introduces outage risk, not the incremental one.
_What the interviewer is probing for:_ Willingness to push back on an unrealistic timeline with a credible, lower-risk incremental alternative, rather than either refusing outright or agreeing to an unsafe compressed plan.

## 12. Common Misconceptions

1. **"Higher `-parallelism` always means faster applies."** Only for graphs with genuinely independent resources; a chain-shaped graph gets no benefit, and too-high values can trigger provider rate limiting, making things slower or causing failures.
2. **"`-target` is a fine everyday tool for speeding up large-state applies."** It narrows scope for one apply without fixing the state's actual blast radius, and repeated use risks producing state inconsistent with a full plan — it's an emergency tool ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)), not a routine performance lever.
3. **"State splitting is purely a performance optimization."** It's equally, arguably primarily, a blast-radius/safety mechanism — smaller graphs are faster, but the bigger win is that one team's apply becomes structurally unable to touch another team's resources.
4. **"`terraform_remote_state` keeps split states automatically in sync."** It's a read at plan time, not a live link — downstream modules see upstream outputs as of their own last plan, not continuously.

## 13. 🔑 Key Takeaways

- `-parallelism` controls concurrency within one graph walk (default 10); its benefit is bounded by how much of the graph is actually independent, and by provider rate limits.
- State splitting is the structural fix for both slow applies and large blast radius — it shrinks the graph any single apply touches and removes cross-team resource access entirely.
- `terraform state mv` (or `moved` blocks) lets state be split without destroying and recreating resources, verified by diff-free plans on both sides before and after.
- `terraform_remote_state` replaces shared-graph edges with explicit, read-only, one-time-per-plan cross-state references after a split.
- `-target` is an emergency/recovery tool ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)), never a substitute for actually splitting an oversized state.

## 14. Related Concepts & What's Next

[§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md) named the giant-state anti-pattern this section provides the concrete remediation for. [§106](./Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md) covers the project-structure decisions that should mirror the same state boundaries. [§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md) and [§12](../Part2/Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md) cover the graph and execution model this section's mechanics build directly on. [§110](./Section-110-Part15-Versioning-Strategy-Terraform-Core-Providers-and-Modules.md) turns to versioning strategy — a related but distinct scaling concern.

**Next Section:** [§110](./Section-110-Part15-Versioning-Strategy-Terraform-Core-Providers-and-Modules.md) — `Section-110-Part15-Versioning-Strategy-Terraform-Core-Providers-and-Modules.md`
