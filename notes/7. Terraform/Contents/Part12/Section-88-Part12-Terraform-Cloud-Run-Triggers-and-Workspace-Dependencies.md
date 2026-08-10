# Section 88 (Part 12): Terraform Cloud Run Triggers and Workspace Dependencies

## 1. Definition

**Plain language:** A run trigger lets one Terraform Cloud workspace automatically queue a new run whenever another workspace it depends on finishes applying — so if a "networking" workspace successfully applies a new subnet, a downstream "app" workspace can automatically re-plan against that change, without anyone manually re-running it or a human remembering that the dependency changed.

**Precise definition:** A **run trigger** is a workspace-level configuration in Terraform Cloud/Enterprise that subscribes one workspace (the "downstream" workspace) to the successful applies of one or more other workspaces (the "source" workspaces). When a source workspace's run reaches an applied state, TFC automatically queues a new run in every downstream workspace configured to trigger on it. This is the primary mechanism for expressing **workspace dependencies** — situations where one workspace's configuration reads outputs from another via `terraform_remote_state` data sources or (more commonly in TFC) direct workspace output references — without requiring the two workspaces to be combined into a single monolithic root module or manually re-run in sequence by an operator.

> 💡 **Tip:** A run trigger only queues a _plan_ (and, if configured, apply) in the downstream workspace — it does not pass data directly. The actual data flow between workspaces still happens through the mechanism that already exists for cross-workspace references: reading the source workspace's state outputs (via `terraform_remote_state` pointed at a TFC-backed state, or the newer output-sharing configuration). The run trigger's only job is timing — "re-run me whenever this other workspace changes" — not payload delivery.

## 2. Why This Matters

- **Encodes real infrastructure dependencies without collapsing them into one workspace.** A networking layer and an application layer can stay in separate, independently owned workspaces (matching [§84](./Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md)'s guidance to keep workspace boundaries aligned with deployable units) while still staying automatically in sync.
- **Removes a manual re-run step that's easy to forget.** Without run triggers, an engineer changing the networking workspace has to remember to also go re-run every downstream workspace that depends on it — a run trigger makes that propagation automatic and visible in run history.
- **Keeps blast radius contained while preserving correctness.** Each workspace still applies independently (with its own plan review/policy checks), rather than one giant apply touching everything at once — dependencies propagate through the pipeline stage by stage.
- **Makes cross-team ownership boundaries practical.** A platform team owns and applies the networking workspace; an application team's workspace automatically reacts to that team's changes without either team needing direct write access to the other's workspace.
- **Surfaces dependency chains in the UI/API.** TFC shows a workspace's configured run triggers and the workspaces that depend on it, giving visibility into the dependency graph that would otherwise live only in institutional knowledge.

## 3. Prerequisites and Dependencies

Builds on the workspace model ([§84](./Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md)) and the VCS-driven run pipeline ([§85](./Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md)). Assumes familiarity with cross-configuration state references (`terraform_remote_state`, related to state fundamentals in [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)–[§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md)) and multi-environment/component layout patterns ([§71](../Part10/Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md), [§82](../Part11/Section-82-Part11-Multi-Region-and-Multi-Account-Subscription-Project-Patterns.md)).

## 4. Architecture / Conceptual Diagram

```text
   Workspace: "infra-network"                Workspace: "app-api-prod"
   (source)                                   (downstream)

   push/merge ──► plan ──► apply ──► APPLIED   run trigger configured:
                                        │        "watch infra-network"
                                        │                │
                                        └───────────────►│
                                                         ▼
                                            new run automatically QUEUED
                                                          │
                                                          ▼
                                              plan reads infra-network's
                                              outputs (vpc_id, subnet_ids)
                                              via terraform_remote_state
                                              or output sharing
                                                          │
                                                          ▼
                                                 plan → policy check →
                                                 apply (auto or manual)
```

- Multiple downstream workspaces can subscribe to the same source workspace; a single source apply can fan out to several dependent runs.
- A downstream workspace can itself have run triggers pointing at it, forming a multi-level dependency chain (network → shared-services → app), each stage independently reviewable.
- The trigger only fires on a successfully **applied** run in the source — a failed or discarded run in the source does not propagate.

## 5. Hands-On

### 5.1 Configuring a Run Trigger

**Purpose:** Show the `tfe` provider representation of a run trigger, consistent with managing TFC itself as code ([§85](./Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md)'s pattern).

**Syntax:**

```hcl
resource "tfe_run_trigger" "app_depends_on_network" {
  workspace_id    = tfe_workspace.app_api_prod.id
  sourceable_id   = tfe_workspace.infra_network.id
}
```

**Example usage and expected output:**

```bash
$ terraform apply
tfe_run_trigger.app_depends_on_network: Creating...
tfe_run_trigger.app_depends_on_network: Creation complete after 1s [id=rt-8pQd3RtY9kLmNx2A]

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** A platform team wires `app-api-prod`, `app-worker-prod`, and `app-scheduler-prod` all to run-trigger off `infra-network`, so a single networking change automatically re-validates every downstream application workspace in one pass, each with its own independent plan review.

**Common errors:** Configuring the run trigger in the wrong direction (source and downstream reversed) causes the networking workspace to queue runs whenever an application workspace applies — usually harmless but confusing, and a sign the dependency direction was misunderstood.

### 5.2 Consuming a Source Workspace's Outputs Downstream

**Purpose:** Show the actual data-flow mechanism a run trigger's timing pairs with.

**Syntax:**

```hcl
data "terraform_remote_state" "network" {
  backend = "remote"

  config = {
    organization = "acme-corp"
    workspaces = {
      name = "infra-network"
    }
  }
}

resource "aws_instance" "app" {
  subnet_id = data.terraform_remote_state.network.outputs.subnet_id
}
```

**Example usage and expected output:**

```bash
$ terraform plan
data.terraform_remote_state.network: Reading...
data.terraform_remote_state.network: Read complete after 1s

Terraform will perform the following actions:
  # aws_instance.app will be created
    + subnet_id = "subnet-0a1b2c3d"   # value read from infra-network's outputs

Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** This is the standard way TFC-hosted, separately owned workspaces share values without direct write coupling — the downstream workspace only needs read access to the source workspace's state outputs, not write access to its configuration.

**Common errors:** Forgetting that `terraform_remote_state` reads whatever the source workspace's **last applied** state contains — if the source workspace's apply hasn't run yet after a config change, downstream reads stale values, which is exactly the staleness window run triggers are designed to close automatically.

## 6. Production Usage Notes

- **Run triggers propagate one level per apply-cycle, not instantaneously through an entire chain in one pass.** A three-level chain (network → shared-services → app) takes three successive apply cycles to fully propagate a network-layer change end to end — this is expected sequencing, not a delay bug.
- **A downstream workspace's queued run still goes through its own full pipeline** — policy checks ([§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)), cost estimation ([§90](./Section-90-Part12-Cost-Estimation-Features.md)), and (if not auto-apply) a manual confirmation step — a run trigger only affects _when_ a run is queued, not whether it bypasses any governance already configured on that workspace.
- **Run triggers are commonly combined with output sharing rather than raw `terraform_remote_state`** in more recent TFC usage, since output sharing can be scoped more precisely (specific outputs, specific consuming workspaces) than a full remote-state data source read.

## 7. Security Considerations

- A downstream workspace configured to read a source workspace's state outputs needs read access to that state — if the source state contains sensitive values not marked as such ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)'s sensitive-output guidance), those values become readable to anyone with access to the downstream workspace's plan output too, effectively widening exposure.
- Run triggers themselves don't grant any new access between workspaces — they only affect run timing — but teams sometimes mistakenly assume configuring a run trigger also grants the downstream workspace read access to the source's state, when that access must be configured separately via output sharing or backend configuration permissions.
- A malicious or compromised source workspace that applies unexpected changes propagates that impact automatically and immediately to every downstream workspace subscribed to it — chained run triggers are a real attack-propagation path worth considering in a threat model for a heavily interconnected workspace graph.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                | Likely Cause                                                                                                    | Resolution Path                                                                                                               |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Downstream workspace doesn't queue a run after source applies          | Run trigger not configured, or configured in the wrong direction                                                | Verify the trigger's source/downstream relationship in the workspace's run-triggers settings                                  |
| Downstream plan shows stale values from the source workspace           | Source workspace's most recent config change hasn't actually been applied yet (only planned)                    | Confirm the source workspace's apply completed; remember `terraform_remote_state` reads last-applied state, not last-planned  |
| Chained dependency (A → B → C) doesn't fully propagate in one go       | Each hop requires its own apply cycle; this is expected sequential behavior, not a single instantaneous cascade | Track propagation across the expected number of apply cycles; don't assume a single trigger firing completes the whole chain  |
| Downstream workspace's read of source state fails with an access error | Downstream lacks read permission on the source workspace's state, separate from the run-trigger configuration   | Grant read access on the source workspace's state (via team permissions or output sharing) independently of the trigger setup |

## 9. Best Practices

- Keep dependency chains shallow and explicit (rarely more than two or three levels) — deeply chained run triggers become hard to reason about and slow to fully propagate.
- Prefer output sharing over broad `terraform_remote_state` reads where available, to limit exactly which values cross the workspace boundary.
- Document the dependency graph somewhere visible (README, architecture diagram) even though TFC's UI shows configured triggers, since the "why" behind a dependency is rarely self-evident from the trigger configuration alone.

## 10. Common Anti-Patterns / Mistakes

- **Using run triggers to simulate what should actually be one workspace.** If two "workspaces" apply in lockstep on every single change with no independent lifecycle, they may not have been meaningfully separate in the first place — over-splitting adds run-trigger complexity without a real isolation benefit.
- **Assuming run triggers grant data access.** Configuring a trigger without also configuring state-read permissions leaves the downstream workspace correctly re-triggered but unable to actually read the values it needs.
- **Building deep, tangled trigger graphs (many-to-many) without documentation.** A dependency web that only exists in TFC's configuration UI, with no external record of intent, becomes a maintenance hazard once the original author moves on.

## 11. Interview Questions

**🎯 Beginner:** _"What does a Terraform Cloud run trigger do?"_
**Model answer:** It automatically queues a new run in a downstream workspace whenever a source workspace it depends on successfully applies — so dependent workspaces stay in sync without a human manually re-running them.
_What the interviewer is probing for:_ Basic grasp of the trigger's purpose as a timing/propagation mechanism.

**🎯 Intermediate:** _"Does a run trigger transfer data between workspaces?"_
**Model answer:** No — a run trigger only affects timing, queuing a new run in the downstream workspace. Actual data flow between workspaces happens separately, typically via a `terraform_remote_state` data source reading the source workspace's applied outputs, or via TFC's output-sharing feature. The trigger and the data-read are two separate, complementary mechanisms.
_What the interviewer is probing for:_ Whether the candidate understands the trigger/data-flow distinction rather than assuming one mechanism does both.

**🎯 Senior:** _"You have a three-level dependency chain: network → shared-services → application. A network change is applied. How long until the application workspace reflects it, and what does that imply for how you'd communicate expected timing to a team asking 'why hasn't my change shown up yet'?"_
**Model answer:** It takes as many apply cycles as there are hops — network's apply triggers shared-services' run, and only once _that_ run itself applies does it trigger application's run; the change doesn't propagate through all three levels in a single pass. Practically, this means a team should expect a multi-stage delay proportional to chain depth, each stage subject to its own plan review/policy check/possible manual-apply gate, not an instantaneous cascade. Communicating this clearly matters because teams unfamiliar with the mechanism often expect one trigger to mean "everything downstream updates now," and the real behavior — sequential, gated propagation — is actually a feature (each stage stays independently reviewable) rather than a limitation to work around.
_What the interviewer is probing for:_ Accurate mental model of sequential propagation versus a naive "instant cascade" assumption, and the ability to explain the trade-off as intentional.

**🎯 Architect:** _"When would you choose run triggers and separate workspaces over just combining everything into one larger root module?"_
**Model answer:** Separate workspaces with run triggers are justified when the components have genuinely different ownership, change cadence, or blast-radius tolerance — a shared networking layer that changes rarely and needs tight review shouldn't share a state file (and thus a single all-or-nothing apply) with an application layer that changes daily. Combining into one root module is simpler operationally (no trigger configuration, no cross-workspace state reads to manage) and is the right choice when the components are always deployed together, owned by the same team, and don't benefit from independent review gates. The deciding factor is whether independent lifecycle and ownership are real requirements or just theoretical — over-splitting into many run-trigger-linked workspaces purely for the sake of modularity, without a genuine independence need, adds real operational complexity (dependency graphs to maintain, multi-stage propagation delay) for no corresponding benefit.
_What the interviewer is probing for:_ Judgment about when workspace/state splitting is actually warranted versus premature decomposition, tying back to state-splitting trade-offs covered more generally in [§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md).

## 12. Common Misconceptions

1. **"Run triggers pass values between workspaces."** They only affect run timing; actual value passing requires a separate state-read mechanism.
2. **"A chained dependency propagates through all levels in one pass."** Each hop requires its own successful apply before the next trigger fires — propagation is sequential, not instantaneous.
3. **"Configuring a run trigger automatically grants state-read access."** Access to a source workspace's state outputs must be configured separately (permissions/output sharing); the trigger alone doesn't grant it.
4. **"Run triggers bypass a downstream workspace's normal governance."** The triggered run still goes through the downstream workspace's own policy checks, cost estimation, and apply-confirmation settings exactly as any other run would.

## 13. 🔑 Key Takeaways

- Run triggers subscribe a downstream workspace to a source workspace's successful applies, automatically queuing a new run when the source changes.
- They control timing only — actual cross-workspace data flow still happens via `terraform_remote_state` or output sharing, configured separately.
- Chained dependencies propagate sequentially, one apply cycle per hop, not instantaneously through the whole chain.
- Triggered runs still pass through the downstream workspace's full governance pipeline (policy checks, cost estimation, apply gating).
- Deep or tangled trigger graphs without documentation become a real maintenance hazard — keep dependency chains shallow and explicit.

## 14. Related Concepts & What's Next

[§89](./Section-89-Part12-Terraform-Enterprise-On-Prem-Self-Hosted-Considerations.md) shifts from TFC-specific SaaS mechanics to the self-hosted Terraform Enterprise deployment model. [§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md) revisits the broader question of when splitting state/workspaces is justified, which underlies the decision to use run triggers at all. [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)–[§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md) cover the state fundamentals that `terraform_remote_state` reads depend on.

**Next Section:** [§89](./Section-89-Part12-Terraform-Enterprise-On-Prem-Self-Hosted-Considerations.md) — `Section-89-Part12-Terraform-Enterprise-On-Prem-Self-Hosted-Considerations.md`
