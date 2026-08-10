# Section 31 (Part 4): Common CLI Flags and Automation-Friendly Patterns (-auto-approve, -var-file, -target, -lock)

## 1. Definition

**Plain language:** Beyond the core commands themselves, Terraform's CLI has a set of flags that show up constantly in real automated pipelines — flags that skip interactive prompts, supply variable values from files, narrow scope to specific resources, and control state locking behavior. Knowing these well is the difference between a fragile, hand-run Terraform workflow and one that runs reliably, unattended, in CI.

**Precise definition:** This section consolidates the CLI flags that recur across `plan`, `apply`, and `destroy` and that specifically enable **non-interactive, automation-friendly execution**: `-auto-approve` (skip the interactive confirmation prompt), `-var-file` / `-var` (supply input variable values from a file or inline, [§40](../Part6/Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)), `-target` (scope an operation to a specific resource address and its dependencies, [§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)), `-lock` / `-lock-timeout` (control whether and how long to wait for the state lock, [§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)), `-input=false` (disable all interactive prompts, failing instead of hanging), `-parallelism=n` (control how many resource operations run concurrently, [§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)), and `-compact-warnings` / `-no-color` (output formatting suited to log-capturing CI systems rather than interactive terminals).

> 💡 **Tip:** The single most important automation pattern in Terraform is **never combining `-auto-approve` with an unsaved, freshly-computed plan** in unattended automation. `-auto-approve` is safe when applying a saved, previously-reviewed plan file ([§25](./Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md)); it is comparatively risky when it causes an unreviewed plan to execute immediately with zero human checkpoint.

## 2. Why This Matters

- **These flags are what turn Terraform from an interactive tool into a pipeline component.** Every CI/CD system running Terraform ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) is built almost entirely out of combinations of the flags covered in this section.
- **Getting `-lock-timeout` wrong causes real pipeline reliability problems** — a pipeline with no timeout can hang indefinitely on a stuck lock; one with too aggressive a timeout fails spuriously during normal, brief lock contention between concurrent runs.
- **`-var-file` is the standard mechanism for environment-specific configuration** (dev vs. staging vs. prod variable values) without duplicating `.tf` files — understanding its precedence relative to other variable sources ([§40](../Part6/Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)) prevents a very common class of "wrong environment got the wrong values" mistake.
- **`-target` is powerful and genuinely useful in the right narrow circumstances**, but its overuse is one of the most cited Terraform anti-patterns ([§108](../Part15/Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md)) — this section reinforces when it's appropriate versus when it signals a deeper configuration problem.
- **CI-oriented output flags (`-no-color`, `-compact-warnings`) directly affect whether pipeline logs are actually readable** — a small detail with outsized day-to-day impact on debugging failed CI runs.

## 3. Prerequisites and Dependencies

This section assumes familiarity with `plan` ([§25](./Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md)), `apply`/`destroy` ([§26](./Section-26-Part4-terraform-apply-and-terraform-destroy.md)), and `init` ([§24](./Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md)) — it consolidates flags used across all three rather than introducing new commands. Variable precedence and `.tfvars` files ([§40](../Part6/Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)) cover `-var-file` semantics in full depth; state locking ([§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) covers what `-lock`/`-lock-timeout` actually protect against; resource targeting ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) covers `-target` in full depth. This section is deliberately a capstone, synthesis-oriented section for Part 4.

## 4. Architecture / Conceptual Diagram

```text
Interactive, local developer workflow           Automated CI/CD pipeline workflow
┌───────────────────────────────┐                ┌─────────────────────────────────────┐
│ terraform plan                │                │ terraform init -input=false         │
│   (review interactively)      │                │   -lock-timeout=5m                  │
│                               │                │                                     │
│ terraform apply               │                │ terraform plan -input=false         │
│   Enter a value: yes          │                │   -var-file="prod.tfvars"           │
│   (human types "yes")         │                │   -lock-timeout=5m                  │
│                               │                │   -out=tfplan                       │
└───────────────────────────────┘                │                                     │
                                                 │ [ HUMAN APPROVAL GATE IN CI ]       │
                                                 │                                     │
                                                 │ terraform apply -input=false        │
                                                 │   -auto-approve                     │
                                                 │   -lock-timeout=5m                  │
                                                 │   tfplan          ◄─ saved plan,    │
                                                 │                      not re-planned │
                                                 └─────────────────────────────────────┘

    -target: narrow scope, exception-handling tool, used in EITHER workflow
             sparingly, never as a routine habit
```

- **The core automation pattern**: `-input=false` everywhere (fail fast, never hang), `-lock-timeout` set deliberately (bounded wait, not infinite or zero), `-var-file` for environment-specific values, `-out` to save a plan, a human/policy approval gate, then `-auto-approve` applying that exact saved plan.

## 5. Hands-On

### 5.1 -auto-approve — Skipping the Confirmation Prompt

**Purpose:** Execute `apply` or `destroy` without the interactive `Enter a value: yes` prompt, required for any unattended pipeline stage.

**Syntax:**

```bash
terraform apply -auto-approve [PLANFILE]
terraform destroy -auto-approve
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve tfplan

aws_instance.web: Creating...
aws_instance.web: Creation complete after 14s [id=i-0abc123def456]

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** The apply stage of any CI/CD pipeline, applied against a saved, already-approved plan file — this is the intended, safe use of `-auto-approve`.

**Common errors:** Pairing `-auto-approve` with a bare `terraform apply` (no saved plan file) in unattended automation means whatever the freshly-computed plan happens to be at that moment executes immediately with zero review — the classic misuse of this flag, and the source of most "CI accidentally destroyed something" incident post-mortems.

### 5.2 -var-file and -var — Supplying Variable Values

**Purpose:** Provide input variable values from a file (per-environment) or inline (one-off overrides), rather than relying on defaults or environment variables alone.

**Syntax:**

```bash
terraform plan -var-file="prod.tfvars"
terraform plan -var="instance_count=5"
terraform apply -var-file="prod.tfvars" -var-file="secrets.auto.tfvars"
```

**Example usage and expected output:**

```bash
$ cat prod.tfvars
environment    = "production"
instance_type  = "m5.large"
instance_count = 6

$ terraform plan -var-file="prod.tfvars"

  # aws_instance.web[0] will be created
  + resource "aws_instance" "web" {
      + instance_type = "m5.large"
      ...
    }
  ... (5 more similar)

Plan: 6 to add, 0 to change, 0 to destroy.
```

**Production usage example:** A CI pipeline parameterized by environment runs the identical configuration with `-var-file="dev.tfvars"`, `-var-file="staging.tfvars"`, or `-var-file="prod.tfvars"` depending on which branch or deployment target triggered it — one configuration, many environment-specific value files (full precedence rules in [§40](../Part6/Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)).

**Common errors:** Passing multiple `-var-file` flags where later files override earlier ones for overlapping keys is expected behavior, not a conflict error — a common point of confusion is assuming Terraform will reject duplicate keys across files rather than silently applying last-wins precedence.

### 5.3 -target — Scoping to Specific Resources

**Purpose:** Limit a plan/apply/destroy operation to a specific resource (and its dependencies), rather than the entire configuration.

**Syntax:**

```bash
terraform apply -target="aws_instance.web" -target="aws_security_group.web_sg"
```

**Example usage and expected output:**

```bash
$ terraform apply -target="aws_instance.web"

Warning: Resource targeting is in effect

You are creating a plan with the -target option, which means that the
result of this plan may not represent all of the changes present in your
configuration. The -target option is not for routine use, and is provided
only for exceptional situations such as recovering from errors or mistakes.

  # aws_instance.web will be created
  + resource "aws_instance" "web" { ... }

Plan: 1 to add, 0 to change, 0 to destroy.

Do you want to perform these actions?
  Enter a value: yes

aws_instance.web: Creating...
aws_instance.web: Creation complete after 14s [id=i-0abc123def456]

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** Recovering from a specific resource stuck in a bad state during an incident — e.g., a resource that failed to create partway through a large `apply` — without re-running the entire configuration's plan while other, unrelated fixes are still in progress.

**Common errors:** Habitually using `-target` to "speed up" routine applies leads to a configuration whose full, untargeted plan eventually surfaces a large, unreviewed backlog of accumulated pending changes — this is called out explicitly in Terraform's own CLI warning text for good reason (full anti-pattern discussion in [§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md), [§108](../Part15/Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md)).

### 5.4 -lock and -lock-timeout — Controlling State Locking Behavior

**Purpose:** Control whether an operation acquires the state lock, and how long it waits if the lock is currently held by another concurrent operation.

**Syntax:**

```bash
terraform apply -lock-timeout=5m
terraform plan -lock=false
```

**Example usage and expected output:**

```bash
$ terraform apply -lock-timeout=5m

Acquiring state lock. This may take a few moments...
```

If another operation is already holding the lock and doesn't release it within 5 minutes:

```text
Error: Error acquiring the state lock

Error message: ConditionalCheckFailedException: The conditional request
failed
Lock Info:
  ID:        d3b07384-d9a0-4e5c-8f1a-2b3c4d5e6f7a
  Path:      my-terraform-state/prod/terraform.tfstate
  Operation: OperationTypeApply
  Who:       ci-runner-42@github-actions
  Created:   2026-08-08 09:14:22 UTC
```

**Production usage example:** Every automated pipeline stage that calls `plan` or `apply` sets an explicit `-lock-timeout` (commonly 5–15 minutes) rather than relying on the default, so that concurrent pipeline runs against the same state fail with a clear, actionable error after a bounded wait rather than hanging indefinitely or timing out ambiguously at the CI platform level.

**Common errors:** Setting `-lock=false` to "work around" a locking error is almost always the wrong fix — it disables the exact safety mechanism ([§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) that prevents two concurrent operations from corrupting state by writing simultaneously; the correct fix is to find and resolve whatever is actually holding the lock (a stuck process, an interrupted run) via `terraform force-unlock` deliberately, not to bypass locking entirely.

## 6. Production Usage Notes

- **A well-built automation pipeline combines these flags consistently, not ad hoc**: `-input=false` on every command, a deliberate `-lock-timeout`, `-var-file` scoped per environment, `-out` to save the plan, and `-auto-approve` only on the apply-of-a-saved-plan step.
- **`-parallelism=n`** (default 10) controls how many resource operations Terraform executes concurrently — lowering it can help with provider APIs that rate-limit aggressively; raising it can speed up very large applies where the provider tolerates more concurrency ([§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md) covers this at scale).
- **`-no-color`** should be set in any CI system that doesn't render ANSI color codes cleanly in its log viewer — otherwise pipeline logs fill with unreadable escape-code noise.
- **Flag combinations differ slightly by command** — not every flag is valid on every subcommand (e.g., `-auto-approve` has no meaning for `plan`, which never prompts for confirmation in the first place); always check `terraform <command> -help` when combining flags unfamiliar together.

## 7. Security Considerations

- `-var` with inline sensitive values (`-var="db_password=hunter2"`) leaves that value visible in shell history and process listings on most systems — prefer `-var-file` (with the file itself excluded from version control and access-controlled) or environment variables for anything sensitive ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)).
- `-auto-approve` removes the human checkpoint entirely — pipelines using it must compensate with equivalent rigor elsewhere (mandatory saved-plan review, policy-as-code gates, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) rather than treating its absence as itself a security control.
- Overly permissive `-lock-timeout` values (or `-lock=false`) used as a workaround for locking friction can mask genuine concurrent-modification risk rather than surfacing and fixing it — treat repeated lock timeouts as a signal to investigate pipeline concurrency design, not just a flag to tune away.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                  | Likely Cause                                                                                                                                    | Resolution Path                                                                                                                                                                       |
| ---------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| CI job hangs indefinitely on `apply`                                                     | No `-input=false`, an interactive prompt is waiting for input that will never arrive                                                            | Add `-input=false` to every non-interactive invocation                                                                                                                                |
| `Error acquiring the state lock` in CI                                                   | Another concurrent run (or a crashed, stuck previous run) is holding the lock                                                                   | Set a deliberate `-lock-timeout`; if genuinely stuck, investigate and use `terraform force-unlock` ([§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) |
| Wrong environment's values applied (dev values hit prod)                                 | Wrong `-var-file` passed, or file precedence ([§40](../Part6/Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)) not accounted for | Verify the exact `-var-file` argument per pipeline branch/target; audit variable precedence rules                                                                                     |
| `-target` apply succeeds but full untargeted plan later shows a large backlog of changes | Routine reliance on `-target` accumulated unreviewed configuration drift over time                                                              | Run a full untargeted plan regularly; treat `-target` strictly as an exception-handling tool going forward                                                                            |
| Pipeline logs are full of garbled escape-code text                                       | ANSI color codes not stripped for a log viewer that doesn't render them                                                                         | Add `-no-color` to CI-invoked commands                                                                                                                                                |

## 9. Best Practices

- Standardize a consistent flag set across every pipeline stage (`-input=false`, explicit `-lock-timeout`, `-var-file` per environment) rather than letting each pipeline or team invent its own ad hoc combination.
- Reserve `-auto-approve` exclusively for applying saved, previously-reviewed plan files — never pair it with a freshly-computed, unreviewed plan in unattended automation.
- Treat `-target` as an incident-response tool with a mandatory follow-up: run a full untargeted plan afterward to confirm nothing else was left inconsistent.
- Never pass sensitive values via `-var` on the command line; use `-var-file` (gitignored, access-controlled) or environment variables instead.

## 10. Common Anti-Patterns / Mistakes

- **`-auto-approve` on a bare, unsaved `apply` in CI** — the single most common way automation causes unreviewed, surprising changes to reach production.
- **Using `-lock=false` to silence locking errors** instead of diagnosing why the lock is actually contended or stuck.
- **Passing secrets via `-var` on the command line**, leaving them in shell history and process listings.
- **Habitual `-target` use as a workaround for slow plans** rather than addressing the actual root cause (state/configuration size, Part 15) or accepting the full plan's cost as the price of full-configuration correctness.

## 11. Interview Questions

**🎯 Beginner:** _"What does `-auto-approve` do, and why does Terraform require it explicitly rather than making it the default in scripts?"_
**Model answer:** `-auto-approve` skips the interactive `Enter a value: yes` confirmation prompt that `apply`/`destroy` normally require, allowing the command to run unattended. It's not the default because that confirmation is Terraform's last built-in human safety checkpoint before making real infrastructure changes — requiring it explicitly as an opt-in flag makes automation authors consciously decide to remove that checkpoint, rather than it being silently absent by accident.
_What the interviewer is probing for:_ Basic understanding of the flag's purpose and why it's deliberately not silent-by-default.

**🎯 Intermediate:** _"Why should `-auto-approve` typically be used together with a saved plan file rather than a bare `terraform apply`?"_
**Model answer:** A bare `terraform apply -auto-approve` computes a fresh plan internally and immediately executes it with zero review — whatever that plan happens to be at that exact moment runs, with no human or automated check in between. Applying a saved plan file (`terraform apply -auto-approve tfplan`) instead executes exactly what was already reviewed and approved earlier — closing the gap between "what a human/policy engine looked at" and "what actually happened," and additionally, Terraform will refuse to apply a saved plan file if state has changed underneath it since the plan was generated, adding a further safety check the bare-apply pattern doesn't get.
_What the interviewer is probing for:_ Connects this section's flags back to the saved-plan-file safety pattern from [§25](./Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md) — tests whether the candidate sees these as one coherent workflow, not isolated flags.

**🎯 Senior:** _"A CI pipeline intermittently fails with 'Error acquiring the state lock.' How would you distinguish between normal, expected lock contention and a genuinely stuck lock, and what would you do about each?"_
**Model answer:** Normal contention looks like: two legitimate concurrent pipeline runs briefly overlapping, where the second simply needs to wait for the first to finish — a reasonable `-lock-timeout` (e.g., 5–15 minutes, sized to the longest expected apply duration) resolves this by waiting it out rather than failing immediately. A genuinely stuck lock looks like: the error persists well beyond any plausible apply duration, or the `Lock Info` in the error output shows a `Created` timestamp from a run that's known to have crashed or been forcibly killed rather than completing normally. For the stuck case, the fix is `terraform force-unlock <LOCK_ID>` ([§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) — but only after confirming, from CI run history or the `Who`/`Operation` fields in the lock info, that the holding operation is actually dead and not still legitimately in progress; force-unlocking a lock that's still legitimately held risks two concurrent writers corrupting state, which is exactly the scenario locking exists to prevent.
_What the interviewer is probing for:_ Real operational judgment distinguishing "wait it out" from "force-unlock," and respect for why the lock exists rather than treating it as pure friction to bypass.

**🎯 Architect:** _"Design the full set of CLI flags and their values for a production Terraform CI/CD pipeline serving multiple environments (dev/staging/prod) with different risk tolerances. Justify each choice."_
**Model answer:** Across all environments: `-input=false` (never hang on a prompt in CI) and `-no-color` (clean CI logs) unconditionally. `-var-file` scoped per environment (`dev.tfvars`/`staging.tfvars`/`prod.tfvars`), selected by pipeline branch or explicit deployment target, never inferred implicitly. `-lock-timeout` set uniformly (e.g., 10 minutes) sized to the longest realistic apply across environments, since lock contention is an infrastructure-wide concern independent of environment risk level. Where the environments diverge: dev/staging pipelines might reasonably auto-apply saved plans on every merge with `-auto-approve` and a lighter review bar, accepting faster iteration at lower risk; the production pipeline requires a saved plan (`-out`), a mandatory human approval gate (or policy-as-code check via `-json` output, [§30](./Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md)/[§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) between plan and apply, and only then `-auto-approve` against that specific saved artifact — never a fresh, unreviewed plan. `-target` is explicitly disallowed in the automated pipeline entirely (reserved for manual, logged, incident-response use only, run by a human with elevated access, never scripted into routine CI). `-parallelism` tuned down from the default if the production cloud account's APIs are known to rate-limit aggressively under the pipeline's typical apply size. The overall justification: treat every flag choice as a deliberate risk-calibration decision per environment, not a single uniform setting copy-pasted across all three.
_What the interviewer is probing for:_ Whether the candidate designs pipeline configuration as a risk-tiered system rather than a one-size-fits-all flag set, and ties each flag choice back to a concrete operational or safety rationale.

## 12. Common Misconceptions

1. **"`-auto-approve` is inherently unsafe and should never be used in production automation."** It's safe and standard when applying a saved, reviewed plan file — the risk is specifically pairing it with an unsaved, unreviewed plan.
2. **"`-lock=false` is a reasonable way to speed up or unblock a stuck pipeline."** It disables the exact mechanism preventing concurrent state corruption — the correct fix for a stuck lock is `force-unlock` after confirming the holder is actually dead, not disabling locking.
3. **"`-target` is just a performance optimization for large configurations."** It's explicitly documented as an exceptional-use, not routine-use, flag — habitual use accumulates unreviewed configuration drift, which is a correctness and safety concern, not just a convenience trade-off.
4. **"Passing `-var` for a password on the command line is fine as long as it's not committed anywhere."** It still persists in shell history and is visible to anything that can read process listings on the same machine during execution — a real, if often overlooked, exposure path.

## 13. 🔑 Key Takeaways

- Automation-friendly Terraform pipelines are built from a consistent combination of `-input=false`, deliberate `-lock-timeout`, environment-scoped `-var-file`, saved plans via `-out`, and `-auto-approve` applied only to those saved plans.
- `-target` and `-lock=false` are both exception-handling tools, not routine flags — their overuse is a well-documented, common Terraform anti-pattern.
- Never pass sensitive values via inline `-var` on the command line; use `-var-file` or environment variables instead.
- `-lock-timeout` should be sized deliberately to the pipeline's realistic apply duration, and a persistently stuck lock should be investigated (via lock metadata) before ever reaching for `force-unlock`.
- These flags are the practical glue connecting everything covered across [§24](./Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md)–[§30](./Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md) into a coherent, safe, unattended CI/CD workflow.

## 14. Related Concepts & What's Next

[§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md) covers resource targeting and partial applies — the full depth behind `-target` only introduced here. [§40](../Part6/Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md) covers variable precedence and assignment methods in full, including exactly how multiple `-var-file`/`-var` flags interact. [§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md) covers state locking mechanisms in depth, the mechanism `-lock`/`-lock-timeout` control. [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) covers full CI/CD pipeline integration patterns building directly on everything in this Part. This closes Part 4 — the hands-on operational core of the Terraform CLI workflow. Part 5 begins with resources and data sources, starting with [§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md), which covers how the resource blocks this Part has been planning, applying, and destroying are actually structured and addressed.

**Next Section:** [§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md) — `Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md`
