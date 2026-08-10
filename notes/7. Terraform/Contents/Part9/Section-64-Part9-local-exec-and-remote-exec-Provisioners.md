# Section 64 (Part 9): local-exec and remote-exec Provisioners

## 1. Definition

**Plain language:** `local-exec` runs a command on the machine where Terraform itself is executing (your laptop, or the CI runner). `remote-exec` runs a command on the resource Terraform just created, reaching it over SSH or WinRM. They're the two workhorse provisioners covered in [§63](./Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)'s overview, and understanding their exact syntax is what separates "using a provisioner correctly, as a last resort" from writing something that silently breaks on the next `apply`.

**Precise definition:** **`local-exec`** is a provisioner that invokes an external program on the host running Terraform, using either a single `command` string (passed to a shell by default) or an explicit `interpreter` list to bypass the shell. **`remote-exec`** is a provisioner that executes one or more commands on the remote resource itself, over a connection defined by a `connection` block ([§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md)), using either an `inline` list of commands, a single `script` file uploaded and executed, or `scripts` (plural) for multiple uploaded scripts run in sequence. Both are declared as `provisioner` blocks nested inside a `resource` block and, unless `when = destroy` is set, run once, synchronously, immediately after the resource is created — `apply` does not proceed past that resource until the provisioner exits (or the configured timeout elapses).

> 💡 **Tip:** `local-exec` never needs a `connection` block — it runs where Terraform runs, full stop. `remote-exec` always needs one, because it has to reach into the resource over the network. If you find yourself writing a `connection` block next to a `local-exec` provisioner, it's very likely a copy-paste leftover with no effect.

## 2. Why This Matters

- These are the two provisioners you will actually encounter in real Terraform codebases — the `file` provisioner and other historical provisioner types are comparatively rare. Knowing their exact syntax is a practical, testable skill ([§112](../Part16/Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md), [§113](../Part16/Section-113-Part16-Common-Exam-Style-Scenario-Questions-Worked-Through.md)).
- The difference between "runs where Terraform runs" (`local-exec`) and "runs on the newly created resource" (`remote-exec`) is the single most important distinction to internalize — using the wrong one is a common cause of "why did this run on my laptop instead of the server" or vice versa.
- `interpreter` and `inline` vs. `command`/`script` are exact syntax the exam and real debugging both test — getting them subtly wrong (e.g., assuming `command` accepts a list) is a frequent source of `terraform validate` failures.

## 3. Prerequisites and Dependencies

This section builds directly on [§63](./Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)'s overview of what provisioners are and why they're discouraged — read that first if you haven't. [§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md) is a required companion for any `remote-exec` usage, since `remote-exec` cannot function without a `connection` block. [§66](./Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md) covers what happens when either of these provisioners fails mid-`apply`.

## 4. Architecture / Conceptual Diagram

```text
   local-exec                              remote-exec
   ─────────────────────────               ─────────────────────────
   Terraform process (laptop/CI runner)     Terraform process (laptop/CI runner)
        │                                        │
        │ runs command directly,                 │ opens SSH/WinRM connection
        │ no network hop                         │  (connection block, §65)
        ▼                                        ▼
   ┌────────────────────┐                    ┌────────────────────────┐
   │ Local shell/binary │                    │  Newly created resource│
   │ e.g. write a file, │                    │  (EC2 instance, VM)    │
   │ call an API, log   │                    │  runs inline/script    │
   └────────────────────┘                    │  commands over the     │
                                             │  established connection│
                                             └────────────────────────┘
```

- `local-exec` never leaves the machine running `terraform apply` — it has no concept of the target resource beyond whatever attributes you interpolate into the command string (commonly `self.private_ip` or similar).
- `remote-exec` requires the target resource to be network-reachable from wherever Terraform is running, on the SSH (22) or WinRM (5985/5986) port, at the exact moment the provisioner runs — this reachability requirement is the single biggest source of `remote-exec` fragility referenced in [§63](./Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md).

## 5. Hands-On

### 5.1 local-exec: `command` (Shell) Form

**Purpose:** The most common `local-exec` form — a single command string interpreted by the local shell.

**Syntax:**

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"

  provisioner "local-exec" {
    command = "echo ${self.private_ip} >> inventory.txt"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
aws_instance.web: Creating...
aws_instance.web: Creation complete after 32s [id=i-0a1b2c3d4e5f6g7h8]

aws_instance.web (local-exec): Executing: ["/bin/sh" "-c" "echo 10.0.1.15 >> inventory.txt"]

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

$ cat inventory.txt
10.0.1.15
```

**Common errors:** `command` takes a single string, not a list — writing `command = ["echo", "hi"]` is a type error caught by `terraform validate`.

### 5.2 local-exec: `interpreter` Form (Bypassing the Default Shell)

**Purpose:** Run a command through an explicit interpreter (a specific shell, PowerShell, Python) rather than the platform default (`/bin/sh` on Unix, `cmd.exe` on Windows).

**Syntax:**

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"

  provisioner "local-exec" {
    command     = "Write-Host 'Instance ${self.id} created'"
    interpreter = ["PowerShell", "-Command"]
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
aws_instance.web (local-exec): Executing: ["PowerShell" "-Command" "Write-Host 'Instance i-0a1b2c3d4e5f6g7h8 created'"]
aws_instance.web (local-exec): Instance i-0a1b2c3d4e5f6g7h8 created
```

**Production usage example:** `interpreter` is most commonly reached for on Windows-heavy CI runners where the default `cmd.exe` shell syntax is awkward, or to invoke a Python script directly (`interpreter = ["python3"]`) instead of shelling through `sh -c`.

**Common errors:** `interpreter` is a list where the first element is the executable and remaining elements are arguments prepended before `command` — passing a bare string instead of a list is a type mismatch.

### 5.3 remote-exec: `inline` Form

**Purpose:** Run a sequence of commands directly on the created resource over an established connection — the most common `remote-exec` pattern.

**Syntax:**

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"

  connection {
    type        = "ssh"
    user        = "ec2-user"
    private_key = file("~/.ssh/id_rsa")
    host        = self.public_ip
  }

  provisioner "remote-exec" {
    inline = [
      "sudo yum install -y nginx",
      "sudo systemctl enable nginx",
      "sudo systemctl start nginx",
    ]
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
aws_instance.web: Creating...
aws_instance.web: Creation complete after 30s [id=i-0a1b2c3d4e5f6g7h8]
aws_instance.web (remote-exec): Connecting to remote host via SSH...
aws_instance.web (remote-exec):   Host: 54.210.11.22
aws_instance.web (remote-exec):   User: ec2-user
aws_instance.web (remote-exec): Connected!
aws_instance.web (remote-exec): Installed:
aws_instance.web (remote-exec):   nginx.x86_64 1:1.24.0-1.amzn2023.0.3
aws_instance.web (remote-exec): Created symlink from /etc/systemd/system/multi-user.target.wants/nginx.service...

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** This pattern — install and start a package on a freshly launched instance — is exactly the kind of use case [§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) argues should usually be a boot-time `user_data` script instead, precisely because it removes the SSH round-trip and its reachability dependency.

**Common errors:** `inline` commands run non-interactively with no TTY; commands that assume an interactive shell (some `sudo` configurations prompting for a password) hang until the provisioner's timeout is reached.

### 5.4 remote-exec: `script` / `scripts` Form

**Purpose:** Upload a local script file to the remote host and execute it, useful when the setup logic is too long or complex for readable `inline` entries.

**Syntax:**

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"

  connection {
    type        = "ssh"
    user        = "ec2-user"
    private_key = file("~/.ssh/id_rsa")
    host        = self.public_ip
  }

  provisioner "remote-exec" {
    script = "${path.module}/scripts/bootstrap.sh"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
aws_instance.web (remote-exec): Connecting to remote host via SSH...
aws_instance.web (remote-exec): Connected!
aws_instance.web (remote-exec): + apt-get update
aws_instance.web (remote-exec): + apt-get install -y nginx
```

**Production usage example:** `scripts = [...]` (plural) runs several uploaded scripts in order — a common pattern for separating "install base packages" from "apply app-specific configuration" into two maintainable files rather than one long `inline` list.

**Common errors:** The script must be executable and use a valid shebang line matching the remote host's OS — a script written for `bash` uploaded to a minimal image without `bash` installed fails with "command not found."

## 6. Production Usage Notes

- `local-exec` runs are only as reliable as the machine running Terraform — a CI runner with ephemeral, restricted network egress may be unable to reach an external API a `local-exec` command tries to call, in a way that's invisible until that specific `apply` run.
- `remote-exec`'s default timeout for establishing the connection is generous but not infinite; a security group that blocks SSH entirely causes the provisioner to fail only after that timeout elapses, which can make `apply` runs appear to hang for several minutes before failing.
- Both provisioners' output streams into the standard `apply` log inline with the resource's other output, prefixed with the resource address and provisioner type (`aws_instance.web (remote-exec): ...`) — this is genuinely useful for debugging but also means verbose scripts can flood CI logs.

## 7. Security Considerations

- `remote-exec` requires Terraform to hold a working credential (private key, WinRM password) capable of logging into every resource it provisions — see [§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md) for the full connection-credential security discussion.
- `local-exec` command strings built from interpolated Terraform variables are vulnerable to shell injection if any interpolated value can be influenced by an untrusted source (a variable sourced from a webhook payload, for instance) — prefer `interpreter` with an argument list over shell string concatenation when any input isn't fully trusted.
- Avoid putting secrets directly in an `inline` command list or a `command` string — both are visible in Terraform's log output and, for `remote-exec`, may also appear in the target host's shell history unless explicitly suppressed.

## 8. Common Troubleshooting Scenarios

| Symptom                                                          | Likely Cause                                                                                                                 | Resolution Path                                                                                                                                               |
| ---------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `local-exec` command runs but has no effect on the actual server | Confusion between `local-exec` (runs on the Terraform host) and `remote-exec` (runs on the resource)                         | Re-read which provisioner type is declared; switch to `remote-exec` with a proper `connection` block if the intent was to affect the remote resource          |
| `remote-exec` provisioner fails with a connection timeout        | Security group/firewall doesn't allow inbound SSH/WinRM from the Terraform host, or the instance hasn't finished booting yet | Verify security group rules; increase the `connection` block's `timeout` ([§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md)) to accommodate slow boots |
| `terraform validate` errors on a `local-exec` block              | `command` passed as a list instead of a string, or `interpreter` passed as a string instead of a list                        | Check argument types against the syntax in 5.1/5.2 above                                                                                                      |
| `remote-exec` `inline` command hangs indefinitely                | A command in the list expects interactive input (a `sudo` password prompt, a confirmation prompt)                            | Rewrite the command to run fully non-interactively (`sudo -n`, `apt-get install -y`)                                                                          |

## 9. Best Practices

- Prefer `inline` for short, simple command sequences and `script`/`scripts` once the logic exceeds roughly a handful of lines — readability degrades fast in a long `inline` list embedded in HCL.
- Always set an explicit `timeout` on `remote-exec` (via the `connection` block, [§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md)) rather than relying on the default, especially for instance types with historically slow boot times.
- Keep `local-exec` commands idempotent by convention even though Terraform doesn't enforce it — write them so a manual re-run wouldn't corrupt anything, since a failed `apply` followed by a retry may re-trigger them.

## 10. Common Anti-Patterns / Mistakes

- **Using `remote-exec` for full application deployment** (cloning a repo, installing dependencies, starting a service) when a boot-time script or a dedicated configuration-management run ([§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) would accomplish the same thing without coupling `apply` to live SSH reachability.
- **Writing a `connection` block next to a `local-exec` provisioner.** It has no effect — `local-exec` never uses a connection — and its presence misleads readers into thinking the command runs remotely.
- **Chaining many long `remote-exec` `inline` blocks across multiple resources** to simulate a full configuration-management run, effectively reimplementing Ansible poorly, inside HCL, without Ansible's idempotency primitives, error handling, or reporting.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `local-exec` and `remote-exec`?"_
**Model answer:** `local-exec` runs a command on the machine executing Terraform itself; `remote-exec` runs a command on the resource Terraform just created, reaching it over a network connection defined in a `connection` block.
_What the interviewer is probing for:_ The fundamental "where does this run" distinction — the most common point of confusion for newcomers.

**🎯 Intermediate:** _"Show the two different ways you can supply commands to a `remote-exec` provisioner, and when you'd choose one over the other."_
**Model answer:** `inline` takes a list of command strings executed in sequence directly in the block — good for short, simple setup steps. `script` (or `scripts` for multiple) uploads a local script file and executes it remotely — better once the logic is long enough that embedding it as HCL list entries hurts readability, or when the same script needs to be reused across multiple resources.
_What the interviewer is probing for:_ Concrete syntax knowledge plus a sense of when each form is the more maintainable choice.

**🎯 Senior:** _"A `remote-exec` provisioner that installs nginx works reliably in one AWS region but intermittently times out in another. What would you investigate?"_
**Model answer:** First, whether the connection's `host` value is resolving to a reachable address in that region — a common cause is referencing a resource attribute that isn't actually populated yet, or a public IP that hasn't propagated. Second, whether the instance's boot time differs meaningfully between regions (different AMI, different instance type availability) such that SSH isn't up yet when the provisioner first tries to connect — the fix there is usually increasing the connection `timeout` rather than assuming intermittent failure is unfixable. Third, whether a security group or NACL differs between the two regions' network setups. I'd avoid assuming it's inherently unreliable and instead isolate which of these three it actually is before proposing a fix.
_What the interviewer is probing for:_ Systematic debugging of a live-network dependency, not just "provisioners are flaky, expected."

**🎯 Architect:** _"Your organization has dozens of modules using `remote-exec` to bootstrap application servers. Leadership wants faster, more reliable `apply` runs. What's your remediation plan?"_
**Model answer:** I'd first classify what each `remote-exec` block actually does: pure OS-level bootstrapping (package installs, service enablement) can usually move to a boot-time `user_data`/cloud-init script with zero SSH dependency at apply time, which is both faster (no synchronous wait in the Terraform run) and more reliable (no reachability precondition). Application-level configuration that's genuinely complex is better handed off to Ansible as a separate pipeline stage run after `apply` completes, decoupling infrastructure provisioning from application configuration entirely. I'd migrate incrementally, module by module, and measure `apply` wall-clock time and failure rate before/after as concrete evidence the change is working, rather than a blanket "remove all provisioners" directive that risks breaking working modules with no equivalent alternative built yet.
_What the interviewer is probing for:_ Ability to drive an org-level migration with measurable outcomes, connecting back to the alternatives in [§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md).

## 12. Common Misconceptions

1. **"`local-exec` runs on the resource being created."** It does not — it runs wherever Terraform itself is executing, which could be a laptop or CI runner with no direct relationship to the resource beyond whatever attributes are interpolated into the command.
2. **"`remote-exec` works without a `connection` block."** It cannot — `remote-exec` has no way to reach the target resource without connection details ([§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md)); omitting the block is a validation error.
3. **"`command` in `local-exec` can take multiple commands as a list."** It takes a single string; chain multiple commands with shell operators (`&&`, `;`) inside that string, or use `interpreter` to hand the whole string to a specific interpreter.
4. **"`inline` and `script` can be used together in the same `remote-exec` block."** They're mutually exclusive within a single `remote-exec` provisioner — choose one form per block (though a resource can have multiple `remote-exec` provisioner blocks, each independently choosing either form).

## 13. 🔑 Key Takeaways

- `local-exec` runs on the machine executing Terraform; `remote-exec` runs on the newly created resource over SSH/WinRM via a `connection` block.
- `local-exec` uses either a single `command` string interpreted by the default shell, or an explicit `interpreter` list to bypass it.
- `remote-exec` uses either `inline` (a list of command strings) or `script`/`scripts` (uploaded and executed file(s)) — never both in the same block.
- `remote-exec` cannot function without a `connection` block, and a `connection` block next to `local-exec` has no effect.
- Both provisioners run once at the resource's creation-time lifecycle event by default; neither is part of Terraform's declarative diff.

## 14. Related Concepts & What's Next

[§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md) covers the `connection` block's full syntax, including SSH- and WinRM-specific arguments, in the detail this section only sketched. [§66](./Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md) explains exactly what happens when either provisioner fails, via `on_failure`. [§67](./Section-67-Part9-null_resource-and-Provisioner-Triggers.md) shows using these provisioners on `null_resource`/`terraform_data` rather than a real infrastructure resource. [§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) lays out the alternatives worth checking before reaching for either of these.

**Next Section:** [§65](./Section-65-Part9-Connection-Blocks-SSH-WinRM.md) — `Section-65-Part9-Connection-Blocks-SSH-WinRM.md`
