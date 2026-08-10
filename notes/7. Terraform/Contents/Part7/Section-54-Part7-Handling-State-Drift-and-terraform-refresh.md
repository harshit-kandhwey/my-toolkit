# Section 54 (Part 7): Handling State Drift and terraform refresh

## 1. Definition

**Plain language:** Drift happens when real infrastructure changes outside Terraform — someone edits a setting in the console, another script or tool modifies something, or the cloud provider itself changes an attribute — so what's actually deployed no longer matches what Terraform's state (and by extension, plan) believes is deployed. Terraform can detect this and show you the gap, but only when it actually looks; it doesn't watch continuously.

**Precise definition:** **Drift** is any divergence between a resource's real-world state and its last-recorded state in Terraform's state file, caused by a change made outside Terraform's own `apply`/`destroy` cycle. Terraform detects drift by **refreshing** — re-querying the provider API for each managed resource's current attributes and comparing them against what's recorded in state — which happens implicitly as the first phase of every `terraform plan`/`apply` (unless explicitly disabled with `-refresh=false`), and can be run in isolation via `terraform apply -refresh-only` (which updates state to match reality without changing any actual infrastructure) or the older, now-largely-superseded standalone `terraform refresh` command. Refresh only updates Terraform's _recorded_ state to match observed reality — it never modifies real infrastructure; a subsequent `plan`/`apply` is what would reconcile configuration against that now-current state, potentially changing real infrastructure back to match what's declared.

> 💡 **Tip:** Refresh and drift are opposite directions of the same comparison. Refresh pulls real infrastructure's current attributes _into_ state ("update my records to match reality"). A normal `apply` pushes configuration's declared values _onto_ real infrastructure ("make reality match my records"). Confusing these two directions is the single most consequential mistake in this area: running `apply` on drifted infrastructure without first understanding the drift can silently overwrite an intentional out-of-band change nobody meant to lose.

## 2. Why This Matters

- **Terraform's declarative model is state-driven, not continuously reconciling** ([§1](../Part1/Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md)) — drift can persist completely invisibly for however long it takes until someone next runs `plan`/`apply`, which is a meaningfully different guarantee than a continuously-reconciling system like Kubernetes provides.
- **Drift is one of the most common sources of confusing, unexpected plan output** — a `plan` that proposes changing an attribute nobody touched in `.tf` is very often explained by someone else having changed the real resource directly, not by a bug in Terraform.
- **Blindly applying against drifted infrastructure can silently discard a deliberate, valid out-of-band change** — an emergency console fix during an incident, or a change made by another authorized process — if configuration is simply reapplied without first understanding what changed and why.
- **`plan -refresh-only` gives teams a safe way to see drift without risking any change to real infrastructure**, which is the correct first step whenever drift is suspected, before deciding whether to update configuration to match reality or let the next `apply` revert it.
- **Systematic drift detection (scheduled `plan -refresh-only` runs) is a real operational practice**, not just a manual troubleshooting step, and is the foundation of the compliance/drift-enforcement patterns covered later in Part 13.

## 3. Prerequisites and Dependencies

Builds directly on [§46](./Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md) (state as a snapshot, not a live mirror) and closes the loop on [§1](../Part1/Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md)'s Senior interview question about Terraform being state-driven rather than continuously reconciling. Assumes `plan`/`apply` mechanics from [§25](../Part4/Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md)/[§26](../Part4/Section-26-Part4-terraform-apply-and-terraform-destroy.md) and the resource attribute structure in state from [§47](./Section-47-Part7-The-State-File-Format-terraform-tfstate-Deep-Dive.md).

## 4. Architecture / Conceptual Diagram

```text
                DRIFT: WHAT DIVERGES, AND WHICH DIRECTION FIXES IT

  Configuration (.tf)         State (recorded)          Real Infrastructure
  ────────────────────         ────────────────           ────────────────────
  instance_type = "t3.micro"   instance_type: t3.micro    instance_type: t3.large
                                (as of last refresh)        (someone resized it
                                                              in the console)
              ▲                          ▲                            │
              │                          │                            │
              │      ┌───────────────────┴────────────────────────────┘
              │      │  REFRESH (implicit in plan/apply, or explicit
              │      │  via `apply -refresh-only`)
              │      │  Pulls REAL attributes INTO state.
              │      │  Real infra: UNCHANGED.
              │      ▼
              │  State updated: instance_type: t3.large  ◄── now matches reality
              │
              │  Next `plan` compares:  config (t3.micro)  vs.  refreshed state (t3.large)
              │  → proposes changing instance_type back to t3.micro
              │
              └──── APPLY (normal terraform apply)
                    Pushes CONFIG's declared values ONTO real infrastructure.
                    Real infra: CHANGED — resized back to t3.micro.

  Two entirely different, non-interchangeable operations:
    refresh → state learns from reality           (config unchanged, infra unchanged)
    apply   → reality is forced to match config    (config unchanged, infra changed)
```

- The critical asymmetry: refresh only ever writes to _state_; apply is what actually writes to _real infrastructure_. Drift-handling decisions hinge entirely on knowing which of these two operations you're about to run.
- `plan` itself, by default, performs an implicit refresh first — this is why a routine `plan` can surface drift even when nobody explicitly asked to check for it, and also why disabling refresh (`-refresh=false`) means `plan` may be working from stale information.
- `plan -refresh-only` is the "look but don't touch" version: it shows exactly what refresh would update in state, without performing the refresh's write or proceeding to any config-vs-reality apply-side comparison — it's specifically designed for safe drift inspection.

## 5. Hands-On

### 5.1 Detecting Drift with `plan -refresh-only`

**Purpose:** Safely check for drift without risking any change to real infrastructure or state.

**Syntax:**

```bash
terraform plan -refresh-only
```

**Example usage and expected output:**

```bash
$ terraform plan -refresh-only
aws_instance.web: Refreshing state... [id=i-0a1b2c3d4e5f6g7h8]

Note: Objects have changed outside of Terraform

Terraform detected the following changes made outside of Terraform since the
last "terraform apply":

  # aws_instance.web has changed
  ~ resource "aws_instance" "web" {
        id            = "i-0a1b2c3d4e5f6g7h8"
      ~ instance_type = "t3.micro" -> "t3.large"
    }

This is a refresh-only plan, so Terraform will not take any actions to undo
these changes.
```

**Production usage example:** This is the standard, safe first step whenever drift is suspected — running it in a scheduled CI job across production environments ([§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)) turns drift detection into a routine, low-risk operational check rather than something only discovered reactively during an incident.

**Common errors:** Interpreting `-refresh-only`'s output as "Terraform is about to fix this" is a common misreading — it explicitly does not change anything; a separate, deliberate decision (update config to accept the drift, or apply to revert it) is still required afterward.

### 5.2 Committing to Accept Drift by Updating State

**Purpose:** Once drift is confirmed and the team decides the real-world value should become the new source of truth, formally accept it into state (and update configuration to match).

**Syntax:**

```bash
terraform apply -refresh-only
# then update the .tf file to match, so config and state agree going forward
```

**Example usage and expected output:**

```bash
$ terraform apply -refresh-only
  ~ resource "aws_instance" "web" {
      ~ instance_type = "t3.micro" -> "t3.large"
    }

Would you like to update the Terraform state to reflect these detected changes?
  Terraform will write these changes to the state without modifying any real
  infrastructure.

  Enter a value: yes

Apply complete! Resources: 0 added, 0 changed, 0 destroyed.
```

```hcl
# main.tf — updated to match, so future plans don't propose reverting it
resource "aws_instance" "web" {
  instance_type = "t3.large"   # was "t3.micro"
}
```

**Production usage example:** This is the correct path when an out-of-band change turns out to be legitimate and intended to stick — e.g., an emergency capacity increase made directly in the console during an incident that the team decides should become the new permanent baseline, rather than being silently reverted by the next routine `apply`.

**Common errors:** Accepting the refresh into state without also updating the `.tf` file leaves configuration and state agreeing only until the next `plan`, which will still eventually diff against whatever the `.tf` file says if it's later touched for an unrelated reason — the config update is what makes the acceptance durable.

## 6. Production Usage Notes

- **Never run a bare `apply` on infrastructure with unexamined suspected drift.** Always check with `plan`/`plan -refresh-only` first and make a deliberate choice — accept the drift into config, or let apply revert it — rather than letting an ordinary apply silently overwrite an out-of-band change nobody's reviewed.
- **Standalone `terraform refresh` is largely superseded by `apply -refresh-only`**, which offers the same state-update capability with the same safety review (`plan` output, confirmation prompt) that any other `apply` gets, rather than refresh's older behavior of updating state immediately with less visibility into what changed.
- **Scheduled drift-detection runs (`plan -refresh-only` on a cron/pipeline schedule) are a standard practice for production environments** — they surface out-of-band changes on a predictable cadence rather than relying on someone noticing a confusing `plan` diff by chance.

## 7. Security Considerations

- **Drift is sometimes a security signal, not just an operational inconvenience.** An unexpected change to a security group rule, an IAM policy, or a resource's public accessibility setting discovered via drift detection can indicate an unauthorized or malicious change, not just a well-intentioned manual fix — drift detection is one input into a broader compliance/security monitoring posture ([§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)).
- **Refresh itself requires read access to every managed resource**, which is generally already implied by the credentials Terraform runs with, but is worth remembering when scoping least-privilege execution roles ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)) — refresh needs read, `apply` needs write, and a role scoped only for one won't support the other.
- **Accepting drift into state via `-refresh-only` should go through the same review as any other state-affecting change**, especially for security-relevant attributes — silently "accepting" an unauthorized change into the new baseline without investigation defeats the purpose of having detected it at all.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                               | Likely Cause                                                                                        | Resolution Path                                                                                                                                                                                                                                                                 |
| ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `plan` proposes changing an attribute nobody edited in `.tf`                          | Real infrastructure was modified outside Terraform (console, another tool/process) since last apply | Run `plan -refresh-only` to confirm and isolate the drift; decide to accept (update config) or revert (apply)                                                                                                                                                                   |
| A deliberate emergency console change gets silently reverted by the next pipeline run | Team ran a normal `apply` without first checking for and consciously deciding on recent drift       | Establish a norm/gate: check `plan -refresh-only` (or review recent drift-detection output) before any apply following a known manual intervention                                                                                                                              |
| `plan` seems to be working from stale information, missing recent real-world changes  | `-refresh=false` was used, skipping the implicit refresh                                            | Re-run without `-refresh=false` to get an up-to-date comparison, or use `plan -refresh-only` explicitly first                                                                                                                                                                   |
| Drift keeps recurring on the same attribute after every apply                         | Another process or team continues to modify that attribute outside Terraform on an ongoing basis    | Add `ignore_changes` ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) for that specific attribute if the external management is intentional and expected to continue, or address the conflicting process directly |

## 9. Best Practices

- Run `plan -refresh-only` (or review scheduled drift-detection output) before applying to any environment where an out-of-band change is suspected or recently known to have happened.
- Treat every detected drift as a deliberate decision point — accept it (update config to match) or revert it (let a normal apply push config back onto reality) — never let it pass through unexamined via a routine apply.
- Set up scheduled, automated drift-detection (`plan -refresh-only` on a cadence) for production environments rather than relying on drift being noticed reactively.

## 10. Common Anti-Patterns / Mistakes

- **Running `apply` reflexively without considering that recent out-of-band changes might exist**, silently reverting a deliberate emergency fix or another team's legitimate change with no review.
- **Treating every instance of drift as something to immediately "fix" by reverting to configuration**, without first understanding why the drift happened — sometimes the real world is right and configuration is what's stale.
- **Using `ignore_changes` broadly as a way to stop seeing drift noise, rather than narrowly on the specific attributes genuinely managed elsewhere** — this can mask real, unwanted drift on other attributes of the same resource that should still be caught and addressed.

## 11. Interview Questions

**🎯 Beginner:** _"What is infrastructure drift, in Terraform terms?"_
**Model answer:** Drift is when the real, deployed infrastructure no longer matches what Terraform's state file has recorded, because something changed it outside of Terraform's own apply process — for example, someone manually resizing an EC2 instance in the AWS console. Terraform doesn't notice this automatically or continuously; it only detects it the next time it refreshes, which happens as part of `plan`/`apply` or explicitly via `plan -refresh-only`.
_What the interviewer is probing for:_ Basic understanding that drift is an out-of-band change and that detection is on-demand, not continuous.

**🎯 Intermediate:** _"What's the difference between what `terraform refresh` (or `apply -refresh-only`) does and what a normal `terraform apply` does, in terms of which direction data flows?"_
**Model answer:** They flow in opposite directions. Refresh (standalone, or via `apply -refresh-only`) pulls real infrastructure's current attributes into Terraform's state — it updates Terraform's records to match reality, and makes zero changes to the actual infrastructure. A normal `apply` does the opposite: it pushes configuration's declared values onto real infrastructure, potentially changing the real world to match what's written in `.tf`. Confusing these two is dangerous — running a normal apply when you actually needed to just refresh state can overwrite a legitimate real-world change; refreshing when you actually needed to fix a drifted resource does nothing to the resource, since it doesn't push anything back.
_What the interviewer is probing for:_ Clear understanding of the directionality — this is the single most important distinction in this topic, and confusing it in an interview answer is a strong negative signal.

**🎯 Senior:** _"During an incident, an on-call engineer manually increases a database's storage allocation directly in the console to resolve an immediate outage, bypassing Terraform entirely. Two days later, the next routine `terraform apply` for that project runs. What happens, and what should the team have done differently in between?"_
**Model answer:** Unless something intervened, the routine `apply` will refresh state (seeing the increased storage), then diff that against configuration (which still declares the old, smaller allocation), and propose reverting the storage size back down to match `.tf` — and unless someone notices and stops it during review, applying that plan would silently undo the incident fix, potentially causing the same outage to recur. What the team should have done in the two-day gap: as soon as the manual fix was made, someone should have either updated the `.tf` configuration to reflect the new storage size (accepting the change as the new intended baseline) and run a normal apply to reconcile state and config together, or at minimum flagged the drift explicitly (via `plan -refresh-only`, and a note in the incident follow-up) so whoever ran the next routine apply would know to check before proceeding rather than being surprised by an unexplained "reduce storage" diff. The core lesson: any manual out-of-band change made during an incident needs a deliberate, tracked follow-up to reconcile it with Terraform before the next apply, not an assumption that it'll just be noticed.
_What the interviewer is probing for:_ Whether the candidate connects the abstract drift/refresh mechanics to a realistic incident-response scenario, and specifically identifies the process gap (no follow-up to reconcile the manual fix) rather than just describing what Terraform would technically do.

**🎯 Architect:** _"Design an organization-wide drift management strategy for a company running hundreds of Terraform-managed environments, where manual out-of-band changes happen periodically (incidents, exceptions, other tooling) and are not going to stop entirely no matter what policy is written."_
**Model answer:** Accept as a starting premise that some out-of-band change will keep happening — the strategy should be about fast, reliable detection and disciplined reconciliation, not an unrealistic zero-drift mandate that gets silently ignored under real operational pressure. First, scheduled automated drift detection (`plan -refresh-only`, or a purpose-built drift-detection tool, [§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)) across every managed environment on a regular cadence, with results surfaced to a dashboard or alerting channel rather than requiring anyone to manually check — this ensures drift is found within a bounded window (hours or a day) rather than discovered by chance at the next unrelated apply. Second, a lightweight, fast reconciliation process for legitimate drift: whoever makes an authorized out-of-band change (documented as part of incident response or an approved exception) is responsible for a same-week follow-up PR updating configuration to match, reviewed and merged like any other change — this keeps the "config is source of truth" property true in practice, not just in policy, without blocking the emergency action itself. Third, for attributes genuinely and durably managed outside Terraform by design (not incidents, but ongoing operational reality — e.g., autoscaling continuously adjusting a desired instance count), use `ignore_changes` ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) deliberately and narrowly, scoped to exactly those attributes, so routine drift detection doesn't generate constant false-positive noise that trains engineers to ignore its output. Fourth, treat repeated, unexplained drift on the same resource/attribute as an escalation trigger — if the same thing keeps drifting without a tracked reconciliation, that's a signal of either a process gap (people bypassing Terraform routinely for something that should go through it) or a legitimate case for `ignore_changes` that hasn't been formalized yet, and either way needs a decision, not indefinite recurring alerts. The organizational risk this strategy manages is less "drift happens" (unavoidable) and more "drift accumulates silently and reconciliation debt builds up until a routine apply causes an unexpected, poorly-understood change" — the strategy's real job is keeping that debt visible and small.
_What the interviewer is probing for:_ Realistic, non-idealistic organizational design — acknowledging drift is inevitable at scale rather than proposing an unenforceable zero-drift policy, and building both fast detection and a lightweight reconciliation loop rather than either ignoring drift or over-blocking legitimate emergency actions.

## 12. Common Misconceptions

1. **"Terraform continuously monitors infrastructure for drift."** It only checks when a refresh happens — as part of `plan`/`apply`, or explicitly via `plan -refresh-only` — not continuously or in the background.
2. **"`terraform refresh`/`apply -refresh-only` fixes drift."** It only updates Terraform's _state_ to match reality; it never changes real infrastructure. Reverting drift (making reality match configuration) requires a normal `apply`.
3. **"Drift is always a mistake that needs to be reverted."** Sometimes the real-world change is legitimate and should become the new intended baseline — the correct response depends on the specific situation, not a default assumption either way.
4. **"A clean `plan` guarantees infrastructure matches configuration right now."** It guarantees state matched configuration as of the last refresh — real-world changes made after that refresh are invisible until the next one.

## 13. 🔑 Key Takeaways

- Drift is any divergence between real infrastructure and Terraform's recorded state, caused by changes made outside Terraform's own apply/destroy cycle.
- Refresh (implicit in `plan`/`apply`, or explicit via `plan`/`apply -refresh-only`) pulls real infrastructure's current attributes into state; it never modifies real infrastructure.
- A normal `apply` pushes configuration's declared values onto real infrastructure — the opposite direction from refresh — which is why blindly applying against unexamined drift risks silently reverting a legitimate out-of-band change.
- `plan -refresh-only` is the safe way to inspect drift without risking any change; deciding to accept it (update config) or revert it (apply) is always a deliberate, separate step.
- At organizational scale, drift is best managed with scheduled automated detection plus a fast, lightweight reconciliation process, not a zero-drift policy that's unrealistic under real operational pressure.

## 14. Related Concepts & What's Next

This section closes out Part 7's state management coverage — [§46](./Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md) through [§54](./Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) together cover what state is, its literal format, where it lives, how it's locked, how it's manipulated, how existing resources join it, how it migrates between backends, and how it's kept honest against reality. Part 8 begins immediately with modules, which package configuration (and interact with state through module-qualified addresses, as seen in [§51](./Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)'s `state mv` examples) for reuse across projects. [§97](../Part13/Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md) later returns to drift detection specifically in the context of organizational compliance enforcement.

**Next Section:** [§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md) — `Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md`
