# Section 63 (Part 9): Provisioners Overview and Why HashiCorp Discourages Them

## 1. Definition

**Plain language:** A provisioner is an escape hatch inside a Terraform resource block that lets you run an arbitrary command — either on your own machine or, over SSH/WinRM, on the resource Terraform just created — as part of `apply`. It's how Terraform reaches outside its own declarative model to do imperative things like "copy this file onto the new server" or "run this shell script once the instance boots."

**Precise definition:** A **provisioner** is a Terraform configuration block (`provisioner "local-exec" { ... }` or `provisioner "remote-exec" { ... }`, among others) nested inside a `resource` block that executes a script or command at a specific point in that resource's lifecycle — by default, immediately after the resource is created (a **creation-time provisioner**), or, if `when = destroy` is set, immediately before the resource is destroyed (a **destroy-time provisioner**). Provisioners are the one mechanism in core Terraform that runs imperative, procedural logic as a side effect of an otherwise declarative resource operation, and HashiCorp's own documentation explicitly labels them "a last resort" — the mechanism exists, is fully supported, and is also actively discouraged by its own authors in favor of alternatives covered in [§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md).

> 💡 **Tip:** If you find yourself reaching for a provisioner, ask first whether the target resource type already exposes a native, declarative way to inject the same behavior — most compute resources across AWS, Azure, and GCP accept a boot-time script (`user_data`, `custom_data`, `metadata_startup_script`) that accomplishes the same goal without any of a provisioner's downsides. [§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) covers this comparison directly.

## 2. Why This Matters

- **Provisioners are the single biggest crack in Terraform's declarative guarantees.** Everything else in this roadmap — the resource graph ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)), state-driven diffing ([§12](../Part2/Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md)), idempotent re-application — depends on Terraform being able to reason about desired state. A provisioner's side effects are opaque to that model: Terraform has no idea what a `local-exec` script actually does to the world.
- **They are a common source of "why did apply hang / fail / half-succeed" incidents.** A `remote-exec` block waiting on an SSH connection that never becomes reachable (security group misconfiguration, slow boot) is one of the most frequently reported causes of a stuck `apply` in production Terraform usage.
- **Understanding why HashiCorp discourages them is what lets you use them responsibly in the rare cases they're genuinely warranted** — bootstrapping a resource type with no native alternative, or gluing together a legacy process that can't be replaced overnight — rather than reaching for them by default out of familiarity with imperative scripting.
- Provisioners appear repeatedly in the Terraform Associate exam curriculum specifically because the correct exam answer is often "prefer not to use a provisioner here" — recognizing when they're being misapplied is itself a tested skill ([§112](../Part16/Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md)).

## 3. Prerequisites and Dependencies

This section assumes familiarity with resource blocks and their lifecycle ([§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md)), the `lifecycle` meta-argument ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)), and Terraform's execution model ([§12](../Part2/Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md)) — specifically that `apply` performs creates, updates, and destroys as distinct graph operations, since provisioners attach to specific points in that sequence. [§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md) covers the two most common provisioner types in full syntactic detail; [§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) covers the alternatives referenced throughout this section.

## 4. Architecture / Conceptual Diagram

```text
   RESOURCE LIFECYCLE, WITH PROVISIONERS ATTACHED

   terraform apply
        │
        ▼
   ┌─────────────────────┐
   │ Provider API call:  │
   │ create the resource │   (e.g. aws_instance.web is launched)
   └─────────────────────┘
        │
        ▼
   ┌──────────────────────────────────────────┐
   │ CREATION-TIME PROVISIONER (default)      │
   │ provisioner "local-exec" / "remote-exec" │
   │ runs ONCE, immediately after create      │
   │ succeeds ──────────────► apply continues │
   │ fails ──► on_failure = fail (default):   │
   │           resource marked TAINTED (§66)  │
   └──────────────────────────────────────────┘
        │
        │   ... resource exists, is used, time passes ...
        │
        ▼
   terraform destroy  (or replacement forcing a destroy)
        │
        ▼
   ┌──────────────────────────────────────────┐
   │ DESTROY-TIME PROVISIONER (when = destroy)│
   │ runs ONCE, immediately BEFORE the        │
   │ provider API call that deletes the       │
   │ resource — e.g. deregistering a node     │
   │ from a cluster before terminating it     │
   └──────────────────────────────────────────┘
        │
        ▼
   ┌─────────────────────┐
   │ Provider API call:  │
   │ destroy the resource│
   └─────────────────────┘
```

- A provisioner is **not** part of the diff Terraform computes. It has no "desired state" to converge toward — it's an imperative action that runs once, at a lifecycle transition, with no way for Terraform to verify afterward that it did what it was supposed to do or that running it again would be safe.
- This is the structural reason provisioners are discouraged: every other line inside a `resource` block describes desired state that Terraform reconciles on every `plan`/`apply`; a provisioner block describes a one-time action Terraform executes blindly and then forgets.

## 5. Hands-On

### 5.1 A Minimal Provisioner, to See the Escape Hatch Directly

**Purpose:** Show the smallest possible provisioner so the syntax and its "outside the declarative model" nature are visible before [§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md) goes deeper.

**Syntax:**

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"

  provisioner "local-exec" {
    command = "echo Instance ${self.id} is up"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
aws_instance.web: Creating...
aws_instance.web: Creation complete after 34s [id=i-0a1b2c3d4e5f6g7h8]

aws_instance.web (local-exec): Executing: ["/bin/sh" "-c" "echo Instance i-0a1b2c3d4e5f6g7h8 is up"]
aws_instance.web (local-exec): Instance i-0a1b2c3d4e5f6g7h8 is up

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** This exact pattern — logging a resource's ID after creation — is harmless and common. The risk profile changes sharply the moment the command mutates external state (registering the instance in a load balancer via a raw API call, for instance) rather than just observing it, because that mutation is invisible to `terraform plan`.

**Common errors:** Referencing `self.id` outside a provisioner block (in unrelated parts of the config) fails, since `self` ([§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md)) is only valid inside the provisioner block of the resource it refers to.

## 6. Production Usage Notes

- HashiCorp's own reference documentation for provisioners opens with an explicit warning that they should be a last resort — this is not a community norm or a style guide preference, it's the tool authors' stated position, and it should weigh heavily in any design review that proposes adding one.
- **No idempotency guarantee.** Terraform re-applying with no configuration changes does not re-run a creation-time provisioner (it already ran once, at creation) — but it also does not verify the provisioner's effect is still true. If someone manually undoes what the provisioner did, Terraform has no way to detect or repair that drift, unlike a normal resource attribute.
- **No dependency-graph awareness of provisioner _content_.** Terraform knows a provisioner block belongs to a resource and therefore runs it at the right lifecycle point, but it has zero visibility into what the provisioner's command actually does — it cannot compute a diff, cannot include the provisioner's effects in `plan` output, and cannot roll back a partial failure.
- Teams that adopt provisioners heavily often find their `apply` runs become slow and flaky in direct proportion to provisioner usage — SSH/WinRM connections ([§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md)) waiting on network reachability are a frequent source of multi-minute hangs that a purely API-driven `apply` would never have.

## 7. Security Considerations

- Creation-time `remote-exec`/`connection` provisioners require Terraform to hold SSH private keys or WinRM credentials for target hosts, meaning whatever runs `terraform apply` — often a CI/CD pipeline — needs live network reachability plus a credential capable of logging into every provisioned host, which is a materially larger blast radius than the cloud API credentials alone.
- `local-exec` executes with the OS-level permissions of whatever process is running Terraform; a poorly reviewed `command` argument (especially one built from interpolated variables) is a shell-injection risk if any of the interpolated values come from untrusted input (an `.auto.tfvars` sourced from a pull request, for example).
- Commands and their output are written into Terraform's log stream and can end up in CI/CD logs; a provisioner command that includes a secret inline (`command = "curl -H 'Authorization: Bearer ${var.token}' ..."`) leaks that secret into plaintext logs — pass secrets via environment variables into the provisioned command rather than inline interpolation where possible.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                                        | Likely Cause                                                                                                 | Resolution Path                                                                                                                                                                                                              |
| -------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `terraform apply` hangs for many minutes on a resource with a `remote-exec` block                              | SSH/WinRM connection cannot be established (security group, NACL, or boot delay)                             | Verify network reachability and `connection` block settings ([§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md)) independent of Terraform; add explicit `timeout`                                                      |
| Resource shows as "tainted" after a failed `apply`                                                             | Creation-time provisioner failed with default `on_failure = fail`                                            | Understand tainting behavior in [§66](./Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md); fix the underlying script and re-`apply`, which will recreate the resource                                             |
| Re-running `apply` does not re-execute a provisioner that clearly needs to run again                           | Provisioners are not part of the declarative diff — they run once at the lifecycle event, not on every apply | Use `null_resource`/`terraform_data` with `triggers` ([§67](./Section-67-Part9-null_resource-and-Provisioner-Triggers.md)) to force intentional re-execution                                                                 |
| A `local-exec` provisioner "worked" but the change it made isn't reflected anywhere in `terraform plan`/`show` | Provisioner side effects are entirely outside Terraform's state and diff model by design                     | Do not rely on provisioners for anything that needs to be visible in plan output; prefer a native resource attribute or alternative ([§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) |

## 9. Best Practices

- Treat every proposed provisioner as something to actively argue against in review — the burden of proof should be on demonstrating no declarative alternative exists (native resource argument, `user_data`, a dedicated configuration-management tool), not on justifying avoiding one.
- If a provisioner is genuinely necessary, scope it as narrowly and idempotently as possible, and document in a comment exactly why no alternative was viable, so a future reader doesn't assume it was an oversight.
- Prefer destroy-time provisioners only for genuinely one-shot deregistration actions (removing a node from a cluster before termination) rather than anything that could instead be handled by the target system's own lifecycle hooks.

## 10. Common Anti-Patterns / Mistakes

- **Using provisioners as a general-purpose configuration management substitute** — installing packages, writing config files, and starting services entirely via chained `remote-exec` blocks, when a boot-time script or Ansible handoff ([§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) would do the same job without coupling Terraform's `apply` to live SSH reachability.
- **Assuming a provisioner is idempotent because the script it calls happens to be written idempotently.** Terraform itself makes no idempotency guarantee about provisioners; whatever guarantee exists is entirely the responsibility of the script author, and it's invisible to Terraform's own model regardless.
- **Ignoring `on_failure` semantics** ([§66](./Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md)) and being surprised when a failed provisioner leaves a resource tainted, forcing an unplanned recreate on the next `apply`.

## 11. Interview Questions

**🎯 Beginner:** _"What is a Terraform provisioner, in one sentence?"_
**Model answer:** A provisioner is a block inside a resource that runs a command — locally or on the newly created resource over SSH/WinRM — at a specific point in that resource's lifecycle, typically right after it's created.
_What the interviewer is probing for:_ Basic recognition of the mechanism and where it sits (inside a resource block, tied to a lifecycle event).

**🎯 Intermediate:** _"Why does HashiCorp discourage the use of provisioners?"_
**Model answer:** Because they're an imperative escape hatch inside an otherwise declarative tool: Terraform can't include a provisioner's actions in its diff, can't verify the provisioner is idempotent, and can't detect or repair drift if the provisioner's effect is later undone outside Terraform. They also introduce operational fragility — for example, `remote-exec` provisioners depend on live SSH/WinRM reachability to the target at exactly the moment `apply` runs, which is a common source of hangs and failures that a purely declarative, API-driven resource wouldn't have.
_What the interviewer is probing for:_ Whether the candidate understands the structural reason (not just "HashiCorp said so"), tying it back to the declarative model from [§1](../Part1/Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md).

**🎯 Senior:** _"Your team wants to use a `remote-exec` provisioner to install and configure an application on every new EC2 instance. What would you push back on, and what would you recommend instead?"_
**Model answer:** I'd push back because this couples `terraform apply` to SSH reachability of every instance at apply time, makes the install step invisible to `plan`, and gives no idempotency guarantee if `apply` is re-run. I'd recommend a boot-time approach instead: bake configuration into `user_data`/cloud-init so the instance configures itself independently the moment it boots, with no SSH round-trip from Terraform's process at all, or hand off to a dedicated configuration-management tool (Ansible) as a separate pipeline stage after `apply` completes. Terraform's job stays "provision the infrastructure," not "configure the application," which is a cleaner division of responsibility ([§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md) covers this further).
_What the interviewer is probing for:_ Practical judgment — can the candidate propose a concrete alternative, not just recite "provisioners are bad."

**🎯 Architect:** _"A legacy Terraform codebase has 40+ `remote-exec` provisioners scattered across modules, and `apply` regularly takes 45 minutes and occasionally hangs. How would you approach remediating this without a risky big-bang rewrite?"_
**Model answer:** I'd triage the provisioners into categories: those that duplicate what a native `user_data`/boot-time script could do (migrate first — lowest risk, highest payoff, since it removes the SSH dependency entirely), those that are really configuration-management work masquerading as provisioning (hand off to Ansible as a separate, decoupled pipeline stage), and any that are genuinely one-shot bootstrapping with no equivalent (leave as provisioners, but harden with explicit timeouts and `on_failure` review). I'd migrate module by module, verifying each migrated resource still reaches the same end state via a plan-diff-free apply, rather than attempting to eliminate all 40 at once. The measurable goal is reducing `apply` wall-clock time and eliminating hangs, which gives concrete, incremental proof the migration is working rather than relying on a "provisioners are bad" mandate alone.
_What the interviewer is probing for:_ Migration strategy and risk management at scale, not just theoretical knowledge that provisioners are discouraged.

## 12. Common Misconceptions

1. **"Provisioners are deprecated and about to be removed."** They are not deprecated — they remain a fully supported, documented feature. They are _discouraged as a default choice_, which is a different, softer statement than deprecation.
2. **"A provisioner running successfully once means it will work the same way on every future apply."** Provisioners run once, at a lifecycle event; nothing about that single successful run guarantees the same command is safe or correct to re-run, and Terraform makes no such guarantee.
3. **"Provisioners are part of Terraform's declarative diff, just like resource arguments."** They are not — `plan` output does not preview what a provisioner will do, only that a provisioner is attached to a resource that's about to be created or destroyed.
4. **"local-exec and remote-exec are the only provisioners that exist."** They're the most common ([§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md)), but Terraform also supports a `file` provisioner for copying files, and providers can historically ship custom provisioners, though the ecosystem has moved away from that pattern.

## 13. 🔑 Key Takeaways

- A provisioner is an imperative escape hatch that runs a command at a resource's creation or destroy lifecycle event — it is not part of Terraform's declarative diff.
- HashiCorp's own documentation calls provisioners "a last resort" because they have no idempotency guarantee Terraform can verify and no visibility in `plan` output.
- Creation-time provisioners run after the resource is created (default); destroy-time provisioners (`when = destroy`) run immediately before the resource is deleted.
- Failure of a creation-time provisioner (with default `on_failure = fail`) marks the resource tainted, forcing recreation on the next apply ([§66](./Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md)).
- Nearly every provisioner use case has a native, declarative alternative worth checking first ([§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) — boot-time scripts, native resource arguments, or a dedicated configuration-management handoff.

## 14. Related Concepts & What's Next

[§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md) goes deep on the two most common provisioner types (`local-exec`, `remote-exec`) and their exact syntax. [§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md) covers the `connection` block that `remote-exec` and `file` provisioners depend on. [§66](./Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md) explains `on_failure` behavior and resource tainting in full. [§67](./Section-67-Part9-null_resource-and-Provisioner-Triggers.md) covers `null_resource`/`terraform_data` as a pattern for running provisioners not tied to a real infrastructure resource. [§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) closes out Part 9 with the declarative alternatives that should usually be tried first.

**Next Section:** [§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md) — `Section-64-Part9-local-exec-and-remote-exec-Provisioners.md`
