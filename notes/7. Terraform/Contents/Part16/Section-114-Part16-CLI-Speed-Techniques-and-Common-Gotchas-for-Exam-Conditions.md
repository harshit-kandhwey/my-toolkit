# Section 114 (Part 16): CLI Speed Techniques and Common Gotchas for Exam Conditions

## 1. Definition

**Plain language:** This section covers the CLI habits that make you fast and accurate under time pressure — both for the exam, where several questions show CLI output and ask what it means or what command produced it, and for real production incidents, where the same speed matters for different reasons.

**Precise definition:** **CLI speed techniques** are the specific flag combinations, workflow shortcuts, and debugging patterns that reduce the time and error-rate of common Terraform CLI operations — saved plan files, scoped applies via `-target`, structured logging via `TF_LOG`, and shell completion. **Exam gotchas** are the specific, recurring points of confusion the Terraform Associate exam tests deliberately because they trip up candidates who've only used Terraform casually: flag behaviors that look similar but aren't (`-target` vs. `-replace`), commands that look destructive but aren't (`terraform state rm`), and output formats that look like errors but are actually the CLI working as designed (`No changes.`).

> 💡 **Tip:** Every flag covered in this section exists in Terraform's own `-help` output (`terraform plan -help`, `terraform apply -help`) — if you're ever unsure of a flag's exact behavior while studying, running `-help` locally against a real Terraform binary is faster and more authoritative than any secondhand summary, including this one.

## 2. Why This Matters

- Several exam questions present a CLI command or its output verbatim and ask what will happen next or what already happened — recognizing flags and output formats on sight, without having to reason from scratch, is a direct exam-time saving.
- In real production incident response, minutes matter — knowing `-target` exists but is a last resort (not a routine tool), knowing how to get `TF_LOG` output without restarting a whole debugging session, and being fast with saved-plan workflows are all genuinely operational skills, not exam trivia.
- A large fraction of avoidable exam mistakes come from confusing similarly-named or similarly-behaving flags (`-target` vs. `-replace`, `plan -destroy` vs. `destroy`) rather than not knowing Terraform conceptually — this section exists specifically to disambiguate those pairs.

## 3. Prerequisites and Dependencies

Builds on the CLI workflow fundamentals in [§24](../Part4/Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md)-[§31](../Part4/Section-31-Part4-Common-CLI-Flags-Automation-Friendly-Patterns.md) (`init`, `plan`, `apply`/`destroy`, `validate`/`fmt`, `console`/`graph`, CLI configuration, `show`/`output`, and common flags) and the resource-targeting mechanics in [§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md). This section assumes those commands are already familiar and focuses specifically on speed and disambiguation rather than introducing any command for the first time.

## 4. Architecture / Conceptual Diagram

```text
   THE SAVE-THEN-APPLY SPEED PATTERN (the single highest-value habit)

   terraform plan -out=tfplan
           │
           │  (review the diff carefully — this IS the safety gate)
           ▼
   terraform apply tfplan
           │
           ▼
   No re-diffing, no re-prompting, no re-reading data sources —
   exactly what was reviewed is exactly what gets applied.


   FLAG-CONFUSION MAP (commonly mixed up on the exam)

   -target=ADDR          scopes plan/apply to ONE resource + its
                          dependencies — a surgical, LAST-RESORT tool,
                          not a routine workflow (§37)

   -replace=ADDR          forces a specific resource to be destroyed
                          and recreated on the NEXT plan/apply, without
                          editing configuration — replaces the old
                          `terraform taint` command (deprecated)

   -refresh-only          plan/apply that ONLY updates state to match
                          real infrastructure — makes no config changes,
                          used to reconcile detected drift deliberately

   -destroy               (on `plan` only) previews a full destroy
                          without actually destroying — NOT the same
                          as running `terraform destroy`
```

- The save-then-apply pattern above is the exam's most-tested CLI workflow shortcut and the production world's most important safety habit — both reward the same behavior.
- The four flags in the confusion map look similar (all scope or modify a plan/apply in some way) but do fundamentally different things — mixing them up is the single most common category of CLI-question wrong answer.

## 5. Hands-On

### 5.1 The Save-and-Apply Speed Pattern

**Purpose:** Guarantee that what gets reviewed is exactly what gets applied, with zero drift between review and execution — both an exam-tested workflow and a real production safety practice.

**Syntax:**

```bash
terraform plan -out=tfplan
terraform apply tfplan
```

**Example usage and expected output:**

```bash
$ terraform plan -out=tfplan
Saving a generated plan to disk is recommended, since it can then be
applied exactly as intended.

Plan: 2 to add, 1 to change, 0 to destroy.

Saved the plan to: tfplan
$ terraform apply tfplan
aws_instance.app: Modifying... [id=i-0abc123]
aws_instance.app: Modifications complete after 4s
...
Apply complete! Resources: 2 added, 1 changed, 0 destroyed.
```

**Production usage example:** Nearly every mature CI/CD pipeline ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) separates plan (with a human or automated approval gate) from apply, passing the exact `tfplan` artifact between the two jobs, precisely to eliminate the possibility of the world changing between what a reviewer approved and what actually gets executed.

**Common errors:** Running `terraform apply` with no arguments after already running `terraform plan -out=tfplan` — this ignores the saved plan entirely and computes a brand-new diff, silently discarding the speed and safety benefit of having saved one in the first place.

### 5.2 -target: The Scalpel, Not the Default Tool

**Purpose:** Demonstrate correct, minimal use of `-target` for isolating a single resource, and why it's discouraged as a habitual workflow.

**Syntax:**

```bash
terraform apply -target=aws_instance.app
```

**Example usage and expected output:**

```bash
$ terraform apply -target=aws_instance.app
Warning: Resource targeting is in effect

You are creating a plan with the -target option, which means the
result of this plan may not represent all of the changes requested
by the current configuration.

...
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** A legitimate use is recovering from a partially-failed apply where one resource errored and needs to be retried in isolation without touching everything else in a large plan — used sparingly, as a recovery tool, not as a substitute for normal, full applies.

**Common errors:** Using `-target` routinely to "speed up" applies by only touching what you're currently working on — this produces a state that no longer matches a full, untargeted plan, and the very next untargeted apply can surface a large, confusing batch of changes that accumulated silently while targeted applies were being used as the default workflow ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md) covers this anti-pattern in depth).

### 5.3 TF_LOG for Fast Debugging

**Purpose:** Get detailed diagnostic output without restarting a whole troubleshooting session from scratch.

**Syntax:**

```bash
export TF_LOG=DEBUG
export TF_LOG_PATH=./terraform-debug.log
terraform apply
```

**Example usage and expected output:**

```bash
$ export TF_LOG=DEBUG
$ export TF_LOG_PATH=./terraform-debug.log
$ terraform apply
# (normal apply output on screen, full debug trace written to file)

$ tail -n 20 terraform-debug.log
2026-08-03T10:14:02.113Z [DEBUG] provider.terraform-provider-aws: ...
2026-08-03T10:14:02.201Z [DEBUG] provider: plugin process exited
```

**Production usage example:** `TF_LOG=TRACE` (the most verbose level) is the standard first step when diagnosing a provider crash or an unexplained API error, since it surfaces the exact underlying HTTP request/response the provider made — far more informative than the terse error Terraform surfaces by default.

**Common errors:** Forgetting to unset `TF_LOG` after debugging — leaving it set globally causes every subsequent, unrelated Terraform command to produce large log files and noticeably slower output, which is easy to mistake for a real performance regression.

### 5.4 Tab Completion and terraform console for Quick Checks

**Purpose:** Reduce typos and speed up quick expression checks without a full plan/apply cycle.

**Syntax:**

```bash
terraform -install-autocomplete
terraform console
```

**Example usage and expected output:**

```bash
$ terraform console
> var.instance_type
"t3.micro"
> length(var.subnet_names)
3
> [for s in var.subnet_names : upper(s)]
[
  "A",
  "B",
  "C",
]
> exit
```

**Production usage example:** `terraform console` ([§28](../Part4/Section-28-Part4-terraform-console-and-terraform-graph.md)) is the fastest way to sanity-check a `for` expression or function call against real variable values before committing it to a resource block, avoiding a slow plan/apply/inspect loop just to verify string manipulation logic.

**Common errors:** Assuming `terraform console` has side effects on real infrastructure — it's read-only against current state and variables; it evaluates expressions but never applies anything.

## 6. Production Usage Notes

- All four techniques above (`-out`/apply-from-file, targeted apply as a recovery tool, `TF_LOG`, and `console`) are genuinely used in day-to-day production Terraform work, not exam-only tricks — this section's "speed" framing applies equally to incident response, where the same minutes saved matter for very different reasons than exam pacing.
- `-target` and `-replace` in particular should be treated as break-glass tools with a mental note to run a full, untargeted `plan` immediately afterward to confirm no unrelated drift was masked by the scoped operation.

## 7. Security Considerations

- `TF_LOG=TRACE` output can include sensitive values (API request bodies, sometimes provider credentials in transit) — treat debug log files as sensitive artifacts, never commit them to version control, and delete them once the issue is resolved.
- Saved plan files (`tfplan` from `-out`) contain the full resolved diff, which can include sensitive variable values in plaintext depending on provider behavior — treat them as sensitive-adjacent artifacts in CI, not as safe-to-archive build outputs ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md) covers `sensitive` marking, which redacts console/log output but not necessarily the binary plan file's raw contents).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                            | Likely Cause                                                                              | Resolution Path                                                                                                                                                                                                 |
| -------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `terraform apply tfplan` errors with a stale-plan message                                          | Real state changed since the plan was saved (someone else applied first)                  | Discard the stale plan, re-run `terraform plan -out=tfplan` fresh, review, apply again                                                                                                                          |
| A targeted apply "fixed" the immediate issue but the next full plan shows a large, unexpected diff | `-target` was used repeatedly as a routine workflow instead of a recovery tool            | Run a full, untargeted `plan` regularly; treat `-target` as break-glass only ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md))                                                       |
| Debug logging isn't producing any output                                                           | `TF_LOG` set but `TF_LOG_PATH` not set (output going to stdout, mixed with normal output) | Set `TF_LOG_PATH` explicitly to separate debug trace from normal CLI output                                                                                                                                     |
| Tab completion doesn't work after `-install-autocomplete`                                          | Shell RC file wasn't reloaded, or a non-default shell wasn't detected correctly           | Restart the shell session, or manually source the generated completion script ([§29](../Part4/Section-29-Part4-CLI-Configuration-terraformrc-Config-Blocks-Credentials-Helpers.md) covers CLI config specifics) |

## 9. Best Practices

- Default to `terraform plan -out=tfplan` followed by `terraform apply tfplan` for any apply in a shared or production environment — untargeted, unsaved `apply` should be reserved for solo scratch/sandbox work.
- Treat `-target` and `-replace` as explicitly logged, deliberate exceptions — note in a PR or runbook why a targeted operation was necessary, and follow it with a full plan to confirm nothing else drifted.
- Learn `terraform console`'s expression-checking workflow early — it removes an enormous amount of trial-and-error from writing `for` expressions and function chains against real data.

## 10. Common Anti-Patterns / Mistakes

- **Using `-target` as a default speed habit rather than a recovery tool.** This silently accumulates untargeted drift that surfaces confusingly, often much later, in a full plan.
- **Leaving `TF_LOG` set globally in a shell profile "just in case."** This slows down and clutters every Terraform invocation, including ones with nothing to debug.
- **Treating `plan -destroy` and `terraform destroy` as interchangeable.** `plan -destroy` only previews what a destroy would do; it makes no actual change. Only `terraform destroy` (or `apply` against a plan generated with `-destroy`) actually removes infrastructure.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `terraform plan -destroy` and `terraform destroy`?"_
**Model answer:** `terraform plan -destroy` only computes and displays what a full destroy would do — it's a preview and makes no actual changes to infrastructure. `terraform destroy` (equivalent to `terraform apply -destroy`) actually executes that destroy plan and removes the real infrastructure. Confusing the two is a genuine risk since their names look almost identical.
_What the interviewer is probing for:_ Basic but important CLI precision — assuming a "plan" command is always non-destructive is broadly true but this specific flag combination is exactly where that assumption needs to be checked carefully.

**🎯 Intermediate:** _"When would you legitimately use `-target`, and why is it discouraged as a routine tool?"_
**Model answer:** Legitimate use is narrow — recovering from a partially-failed apply, isolating a single resource for a focused fix, or breaking a circular-dependency situation temporarily. It's discouraged routinely because a targeted apply only computes and applies a diff scoped to that resource and its dependencies, silently ignoring any other drift elsewhere in configuration — repeated targeted applies can let real, untracked changes accumulate that only surface, confusingly, the next time someone runs a full untargeted plan.
_What the interviewer is probing for:_ Whether the candidate understands `-target` as a scoping mechanism with real side effects on visibility, not just "a flag that makes apply faster."

**🎯 Senior:** _"A junior engineer asks why your team enforces `plan -out=tfplan` followed by `apply tfplan` in CI instead of just running `terraform apply -auto-approve` directly. What's your answer?"_
**Model answer:** Two separate guarantees are at stake. First, review integrity: saving the plan lets a human or automated policy gate (Sentinel/OPA, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) review the _exact_ diff before anything is touched, rather than trusting that a live `apply` will do what was intended. Second, and less obvious: applying a saved plan file never re-reads data sources or recomputes the diff at apply time — it applies exactly what was reviewed, with no possibility of the underlying world (a newly-published AMI, a changed data source result) silently shifting between review and execution. Running `apply -auto-approve` directly collapses plan and apply into one step, which is fine for solo sandbox work but removes both of those guarantees in a shared or production pipeline.
_What the interviewer is probing for:_ Whether the candidate can articulate the _mechanism_ behind a best practice, not just recite it as a rule to follow.

**🎯 Architect:** _"Your team's incident response playbook currently tells engineers to 'use `-target` to quickly fix the broken resource' during an outage. What's wrong with that guidance, and what would you replace it with?"_
**Model answer:** The guidance optimizes for speed in the moment but ignores the accumulated-drift risk `-target` introduces, which is exactly the kind of thing that turns one incident into two. I'd replace it with a tiered playbook: first, attempt the fix via a full, untargeted `plan`/`apply` cycle if time allows, since it surfaces the complete picture and is inherently safer. Only if the full plan is dangerously large, slow, or touches unrelated critical resources during an active outage would `-target` be authorized — and even then, paired with a mandatory follow-up: a full untargeted plan run and reviewed within a fixed window (e.g., same business day) to confirm no drift was masked. I'd also make sure the playbook explicitly calls out `-target`'s side effect (partial state visibility) so responders understand _why_ the follow-up step exists, not just that it's a checkbox to tick.
_What the interviewer is probing for:_ Whether the candidate can balance incident-response pragmatism against the specific risk `-target` introduces, and design a process that accounts for both rather than picking one extreme.

## 12. Common Misconceptions

1. **"`terraform plan -destroy` destroys infrastructure."** It only previews a destroy; no actual change occurs until `terraform destroy` or an apply against that destroy plan is run.
2. **"`-target` is a normal, safe way to speed up applies."** It's a scoping mechanism with a real side effect: it hides drift outside its scope, making it appropriate only as an occasional, deliberate recovery tool.
3. **"Applying a saved plan file re-checks the latest state of the world first."** It applies exactly what was computed at plan time; if real infrastructure or state has since changed, Terraform rejects the stale plan rather than silently reconciling it.
4. **"`terraform console` can accidentally change infrastructure."** It's strictly read-only — it evaluates expressions against current variables and state but never applies changes.

## 13. 🔑 Key Takeaways

- `terraform plan -out=tfplan` followed by `terraform apply tfplan` is both the highest-value exam-tested CLI pattern and the standard production safety habit — it guarantees what's reviewed is exactly what's applied.
- `-target`, `-replace`, `-refresh-only`, and `plan -destroy` are frequently confused on the exam because they sound similar but do fundamentally different things — know each one's precise scope.
- `-target` is a scalpel for recovery situations, not a routine speed tool; habitual use silently accumulates drift outside its scope.
- `TF_LOG`/`TF_LOG_PATH` give detailed diagnostic output for debugging provider or API issues without restarting a session, but should never be left set globally.
- `terraform console` is a fast, side-effect-free way to sanity-check expressions and function calls against real variable and state values.

## 14. Related Concepts & What's Next

[§115](./Section-115-Part16-General-Terraform-Interview-Question-Bank.md) broadens from exam-specific CLI mechanics into a general Terraform interview question bank spanning conceptual, architectural, and behavioral questions. [§113](./Section-113-Part16-Common-Exam-Style-Scenario-Questions-Worked-Through.md) (the preceding section) applied similar precision-of-mechanism reasoning to state and resource-addressing scenario questions. [§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md) covers resource targeting in full depth if a deeper refresher is needed before continuing.

**Next Section:** [§115](./Section-115-Part16-General-Terraform-Interview-Question-Bank.md) — `Section-115-Part16-General-Terraform-Interview-Question-Bank.md`
