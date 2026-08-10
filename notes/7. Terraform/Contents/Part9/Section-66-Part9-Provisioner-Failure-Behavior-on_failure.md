# Section 66 (Part 9): Provisioner Failure Behavior (on_failure)

## 1. Definition

**Plain language:** When a provisioner's command exits with a non-zero status (or a connection can never be established), `on_failure` decides what Terraform does next: either treat the whole `apply` as failed and mark the resource broken (the default), or shrug it off and keep going as if nothing happened.

**Precise definition:** **`on_failure`** is an argument settable inside any `provisioner` block, accepting one of two literal values: **`fail`** (the default) — if the provisioner returns a non-zero exit code or its connection cannot be established, Terraform halts the `apply` operation with an error and marks the resource **tainted**, meaning Terraform will destroy and recreate that resource on the next `apply`; or **`continue`** — Terraform logs the failure as a warning but proceeds with the rest of `apply` as if the provisioner had succeeded, leaving the resource untainted. `on_failure` applies independently to each provisioner block — a resource with multiple provisioners can mix `fail` and `continue` behavior across them.

> 💡 **Tip:** Tainting is not unique to provisioner failure — it's a general Terraform state marking meaning "this resource's actual condition is unverified/suspect, destroy and recreate it next time" (`terraform taint` used to let you set this manually before it was deprecated in favor of `-replace`, [§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)). A failed creation-time provisioner with `on_failure = fail` is simply the most common way a resource ends up tainted without anyone touching it directly.

## 2. Why This Matters

- `on_failure`'s default (`fail` + taint) is a deliberately conservative choice: HashiCorp's position is that if a provisioner — which by definition does something Terraform can't verify — fails, Terraform should not pretend the resource is in a known-good state. Understanding this default is what stops the "why did my next apply try to destroy and recreate a server that seemed fine" surprise.
- Choosing `on_failure = continue` is a real, sometimes-correct choice (a best-effort logging or notification step that shouldn't block infrastructure provisioning if it fails) but it's frequently reached for as a way to silence an annoying failure rather than a deliberate design decision — knowing the difference matters for review.
- Tainting behavior directly determines what the _next_ `apply` does — a tainted resource gets destroyed and recreated even if nothing in its configuration changed, which can be expensive or disruptive (a stateful resource, a resource other resources depend on) if not anticipated.

## 3. Prerequisites and Dependencies

This section assumes the provisioner mechanics from [§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md) and the connection mechanics from [§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md), since a failure to establish a connection is one of the two failure modes `on_failure` governs (the other being a non-zero exit code from the command itself). It also assumes basic familiarity with `terraform apply`'s create/destroy cycle ([§26](../Part4/Section-26-Part4-terraform-apply-and-terraform-destroy.md)) to understand what "tainted, will be recreated" actually implies for the next run.

## 4. Architecture / Conceptual Diagram

```text
   Creation-time provisioner runs
        │
        ▼
   Did it succeed (exit 0, connection established, command completed)?
        │
   ┌────┴──────┐
   │           │
  YES          NO
   │           │
   ▼           ▼
 apply    on_failure setting?
 continues     │
 normally  ┌───┴────┐
           │        │
         "fail"  "continue"
        (default)    │
           │          ▼
           ▼      apply proceeds as if
   apply HALTS    provisioner succeeded;
   with an error  resource NOT tainted;
   resource is    warning logged only
   TAINTED
           │
           ▼
   Next `terraform apply`:
   tainted resource is DESTROYED
   and RECREATED, even if no
   configuration attributes changed
```

- The distinction is binary and per-provisioner-block — there's no partial-success or retry-count concept built into `on_failure` itself; it's exit-code-or-connection-success vs. failure, full stop.
- Tainting is the mechanism that keeps Terraform's model honest: rather than silently assuming a resource whose provisioner failed is "probably fine," it forces an explicit recreation cycle so the resource re-enters a known-good, freshly-provisioned state.

## 5. Hands-On

### 5.1 Default Behavior: `on_failure = fail`

**Purpose:** Show what happens with no `on_failure` specified — the default, conservative behavior.

**Syntax:**

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"

  provisioner "remote-exec" {
    inline = ["exit 1"]   # simulated failure
    # on_failure defaults to "fail"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
aws_instance.web: Creating...
aws_instance.web: Creation complete after 30s [id=i-0a1b2c3d4e5f6g7h8]
aws_instance.web (remote-exec): Connecting to remote host via SSH...
aws_instance.web (remote-exec): Connected!

╷
│ Error: remote-exec provisioner error
│
│ error executing "/tmp/terraform_xxxx.sh": Process exited with status 1
╵

$ terraform plan
  # aws_instance.web is tainted, so it will be destroyed and replaced with an equivalent object

Plan: 1 to add, 0 to change, 1 to destroy.
```

**Common errors:** A common misread is assuming the resource itself failed to create — it did not; the resource exists and its provisioner failed afterward, which is why the _next_ plan shows a replace, not the current apply retrying in place.

### 5.2 Non-Blocking Behavior: `on_failure = continue`

**Purpose:** Show a provisioner explicitly allowed to fail without affecting the resource's state.

**Syntax:**

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"

  provisioner "local-exec" {
    command    = "curl -sf https://notify.example.com/deployed || exit 1"
    on_failure = continue
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
aws_instance.web: Creating...
aws_instance.web: Creation complete after 30s [id=i-0a1b2c3d4e5f6g7h8]

aws_instance.web (local-exec): Executing: ["/bin/sh" "-c" "curl -sf https://notify.example.com/deployed || exit 1"]
aws_instance.web (local-exec): curl: (7) Failed to connect to notify.example.com

Warning: local-exec provisioner error

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** `on_failure = continue` fits a best-effort notification step exactly like this one — a Slack/webhook ping that shouldn't block infrastructure provisioning just because the notification endpoint happened to be briefly unreachable.

**Common errors:** Applying `on_failure = continue` to a provisioner that does something functionally essential (installing required software, registering the instance with a service it needs to function) hides a real failure — the `apply` reports success while the resource is actually left in a broken, half-configured state with no signal forcing a fix.

## 6. Production Usage Notes

- A tainted resource is visible in `terraform plan` output as "will be destroyed and replaced" — reviewers should treat an unexpected replace on an otherwise-unchanged resource as a signal to check whether a provisioner failure caused the taint, rather than assuming a configuration drift.
- Destroy-time provisioners (`when = destroy`) also respect `on_failure`, but a failed destroy-time provisioner with `on_failure = fail` blocks the destroy operation entirely, which can leave a resource stuck mid-destroy in a way that sometimes requires manual state surgery (`terraform state rm`, [§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) to resolve if the underlying issue can't be fixed.
- The now-deprecated `terraform taint` command let operators manually force this same "destroy and recreate next apply" state onto any resource; its replacement, `terraform apply -replace=<address>` ([§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)), achieves the same outcome through the modern CLI, and is worth knowing since a failed provisioner produces the identical state a manual `-replace` would.

## 7. Security Considerations

- `on_failure = continue` on a provisioner that establishes a security-relevant baseline (hardening a host, applying a firewall rule) is a real security risk disguised as convenience — a failed hardening step that's silently swallowed leaves the resource in production without the protection its provisioner was meant to apply, and nothing in the `apply` output distinguishes that from success at a glance.
- A tainted-and-recreated resource re-runs its creation-time provisioner from scratch on the next apply — if the provisioner handles credentials (via a `connection` block, [§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md)) that credential is exercised again, which is a reasonable moment to confirm rotation/expiry policies don't interfere with an automatic recreate-and-reprovision cycle.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                            | Likely Cause                                                                           | Resolution Path                                                                                                                                                                                                                                              |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `terraform apply` errors out mid-run, resource clearly exists in the cloud console | Creation-time provisioner failed with `on_failure = fail` (the default)                | This is expected behavior; fix the underlying script/connection, then re-`apply` to trigger the destroy-and-recreate                                                                                                                                         |
| Next `plan` unexpectedly shows an unrelated-looking resource being replaced        | The resource is tainted from a prior provisioner failure                               | Check prior `apply` logs for a provisioner error on that resource; address the root cause before re-applying                                                                                                                                                 |
| Provisioner clearly failed but `apply` reported success                            | `on_failure = continue` is set, masking the failure as a warning only                  | Review whether `continue` is appropriate for that specific provisioner's importance; switch to `fail` if the step is not truly optional                                                                                                                      |
| Destroy hangs or errors on a resource with a destroy-time provisioner              | Destroy-time provisioner failed with default `on_failure = fail`, blocking the destroy | Fix the underlying issue (often a connection no longer reachable on a resource about to be destroyed) or, as a last resort, remove from state ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) if the resource is already gone |

## 9. Best Practices

- Leave `on_failure` at its default (`fail`) unless there's a specific, documented reason a given provisioner's failure should not block the apply or taint the resource.
- When using `on_failure = continue`, add a comment explaining why the step is genuinely best-effort — this is the kind of setting a future reviewer needs justified, not assumed.
- Treat an unexpected "will be destroyed and replaced" in `plan` output as worth investigating rather than auto-approving, especially in any environment where recreation is disruptive (stateful resources, resources with dependents).

## 10. Common Anti-Patterns / Mistakes

- **Reaching for `on_failure = continue` to make a flaky provisioner "stop erroring"** instead of fixing the actual flakiness (a timeout too short, a script bug) — this converts a visible failure into a silent one, which is strictly worse.
- **Not anticipating what recreation actually costs** for a tainted resource — some resources are expensive or slow to recreate (a large database instance, a resource many others depend on), and a provisioner failure triggering an unplanned recreate can be a bigger production event than the original provisioner problem.
- **Assuming a failed `apply` means the resource wasn't created.** With `on_failure = fail`, the resource _was_ created — only the provisioner step afterward failed — which surprises people expecting an all-or-nothing transaction (Terraform applies are not transactional across a single resource's create-then-provision sequence).

## 11. Interview Questions

**🎯 Beginner:** _"What does `on_failure = fail` do, and is it the default?"_
**Model answer:** Yes, it's the default. If a provisioner fails (non-zero exit or an unreachable connection), Terraform halts the apply with an error and marks the resource tainted, meaning it will be destroyed and recreated on the next apply.
_What the interviewer is probing for:_ Basic recall of the default behavior and its consequence (tainting), not just the keyword.

**🎯 Intermediate:** _"What's the practical difference between `on_failure = fail` and `on_failure = continue`?"_
**Model answer:** `fail` halts the apply and taints the resource, forcing recreation on the next run. `continue` logs the failure as a warning only, lets `apply` proceed as if the provisioner succeeded, and leaves the resource untainted. The choice should depend on whether the provisioner's action is essential to the resource being considered correctly provisioned — essential steps should use `fail`; genuinely optional/best-effort steps (like a notification) are reasonable candidates for `continue`.
_What the interviewer is probing for:_ Whether the candidate can connect the mechanical difference to a judgment call about when each is appropriate, not just recite the two values.

**🎯 Senior:** _"A resource is tainted after a failed provisioner. What actually happens on the next `terraform apply`, and what should an operator watch out for?"_
**Model answer:** On the next apply, Terraform will destroy the tainted resource and create a new one in its place, even though nothing in the resource's own configuration attributes changed — this shows up in `plan` as a replace, not an in-place update. Operators should watch out for: the cost/disruption of recreating that specific resource type (a stateful resource loses its state unless it's backed by external storage); any other resources that depend on identifiers from the tainted resource that will change after recreation (a new instance ID, a new IP); and confirming the provisioner failure's root cause is actually fixed before re-applying, since recreation alone doesn't fix a broken script — it'll likely just fail again on the new resource.
_What the interviewer is probing for:_ Full understanding of the downstream consequences of tainting, not just the mechanical fact that recreation happens.

**🎯 Architect:** _"You inherit a module where several critical setup provisioners use `on_failure = continue` 'to keep pipelines green.' How do you evaluate and fix this?"_
**Model answer:** I'd treat this as a real reliability risk masquerading as pipeline hygiene: `continue` on essential steps means the pipeline reports success while resources can be silently misconfigured, which is worse than a red pipeline because it hides the problem instead of surfacing it. I'd audit each `continue`d provisioner for whether its action is load-bearing (security hardening, required software installation, service registration) vs. genuinely optional (best-effort notifications); flip essential ones back to `fail` (the default) so failures surface honestly; and for ones that are essential but currently flaky, fix the underlying flakiness (better `timeout`, more robust script, retry logic inside the script itself) rather than keep suppressing the symptom. I'd also add monitoring/alerting for tainted resources specifically, since a fleet with `continue` everywhere has likely accumulated silent taint or silent misconfiguration that current dashboards don't surface.
_What the interviewer is probing for:_ Whether the candidate treats `on_failure = continue` as a real production risk requiring root-cause remediation, not a cosmetic pipeline tweak.

## 12. Common Misconceptions

1. **"A failed provisioner means the resource wasn't created."** The resource was created — the provisioner runs _after_ creation succeeds; only the provisioner step itself failed.
2. **"`on_failure = continue` fixes the underlying provisioner problem."** It only suppresses the _consequence_ (halt + taint); the command still failed, and whatever it was supposed to do likely didn't happen.
3. **"Tainting is a one-time event that gets automatically cleared."** A tainted resource stays tainted until the next `apply` actually destroys and recreates it — running `plan` repeatedly without applying doesn't clear the taint.
4. **"`on_failure` applies once per resource."** It's set per `provisioner` block — a resource with three provisioner blocks can have three independent `on_failure` settings, mixing `fail` and `continue` as appropriate to each step.

## 13. 🔑 Key Takeaways

- `on_failure` governs what happens when a provisioner's command exits non-zero or its connection can't be established: `fail` (default) halts `apply` and taints the resource; `continue` logs a warning and proceeds.
- A tainted resource is destroyed and recreated on the next `apply`, even with no configuration changes — this shows up in `plan` output as a replace.
- The resource itself was successfully created even when a creation-time provisioner fails — Terraform applies are not transactional across create-then-provision.
- `on_failure` is set per provisioner block, allowing different failure tolerance for different steps within the same resource.
- `on_failure = continue` should be reserved for genuinely optional steps; using it to silence flaky-but-essential provisioners hides real failures instead of fixing them.

## 14. Related Concepts & What's Next

[§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md) and [§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md) cover the provisioner and connection mechanics whose failure modes this section governs. [§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md) covers `terraform apply -replace`, the modern equivalent of the manual tainting the deprecated `taint` command performed, useful for understanding what "tainted" state actually corresponds to in the CLI today. [§67](./Section-67-Part9-null_resource-and-Provisioner-Triggers.md) shows `null_resource`/`terraform_data` as a way to isolate provisioner failure risk away from real infrastructure resources. [§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) closes with the alternatives that avoid this failure-and-taint cycle by not using provisioners for essential setup in the first place.

**Next Section:** [§67](./Section-67-Part9-null_resource-and-Provisioner-Triggers.md) — `Section-67-Part9-null_resource-and-Provisioner-Triggers.md`
