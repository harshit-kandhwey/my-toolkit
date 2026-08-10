# Section 65 (Part 9): Connection Blocks (SSH/WinRM)

## 1. Definition

**Plain language:** A `connection` block tells Terraform exactly how to log into the resource it just created — the address, the username, the credential, and which protocol (SSH for Linux, WinRM for Windows) to use — so that a `remote-exec` or `file` provisioner has somewhere to send its commands or files.

**Precise definition:** A **`connection` block** is a nested configuration block, placed either inside a specific `provisioner` block (scoping it to that provisioner only) or directly inside the `resource` block (making it the default connection for every provisioner in that resource), that supplies the parameters Terraform needs to establish a remote shell session with a provisioned resource. It supports two `type` values — `"ssh"` (the default, for Linux/Unix targets) and `"winrm"` (for Windows targets) — each accepting a different set of authentication and protocol arguments (SSH: `private_key` or `password`; WinRM: `password`, with `https`/`insecure`/`use_ntlm` protocol options). The connection block is a prerequisite for `remote-exec` and `file` provisioners; `local-exec` never uses one, since it never leaves the machine running Terraform.

> 💡 **Tip:** A `connection` block declared at the `resource` level applies to every provisioner in that resource by default; a `connection` block declared inside a specific `provisioner` block overrides it for that provisioner only. This lets one resource mix, say, an SSH `remote-exec` and a `file` provisioner sharing one connection, without repeating the block twice — but it also means an unexpected override buried inside one provisioner is an easy thing to miss on review.

## 2. Why This Matters

- Every `remote-exec` example in [§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md) quietly depended on a working `connection` block — this section is what makes those examples actually function, and gaps here (wrong `host`, wrong `user`, expired key) are the most common reason a provisioner-based `apply` fails outright.
- Connection credentials are, functionally, an additional live secret Terraform's execution environment must hold beyond the cloud provider's API credentials — understanding exactly what's required (a private key file, a WinRM password) is central to reasoning about the security posture of any pipeline running provisioners ([§7](../Part1/Section-07-Part1-Terraform-Associate-Certification-Landscape-and-How-This-Roadmap-Maps-to-It.md) below, and [§63](./Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)'s broader security discussion).
- SSH vs. WinRM is not just "pick the right protocol" — the argument sets genuinely differ (bastion-host jump-hosts are an SSH-only concept, `https`/`use_ntlm` are WinRM-only concerns), and conflating them produces configuration that silently does nothing for the wrong target OS.

## 3. Prerequisites and Dependencies

This section assumes the `remote-exec` provisioner syntax from [§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md), since a connection block's only purpose is enabling that (and the `file`) provisioner. General SSH concepts (public/private key pairs, known-hosts) are covered in the Linux knowledge base if unfamiliar; this section focuses specifically on how those concepts map into Terraform's `connection` block arguments.

## 4. Architecture / Conceptual Diagram

```text
   resource "aws_instance" "web" { ... }
        │
        ├── connection {                    ◄── resource-level: default for
        │     type = "ssh"                      every provisioner below,
        │     user = "ec2-user"                 unless overridden
        │     private_key = file(...)
        │     host = self.public_ip
        │   }
        │
        ├── provisioner "remote-exec" {
        │     inline = [ ... ]                  uses the resource-level
        │   }                                   connection above
        │
        └── provisioner "file" {
              source      = "app.conf"
              destination = "/tmp/app.conf"

              connection {                   ◄── provisioner-level override:
                type = "ssh"                     applies ONLY to this
                user = "deploy"                  provisioner, e.g. a
                private_key = file(...)          different login user
                host = self.public_ip
              }
            }
```

- SSH (`type = "ssh"`, the default): key- or password-based auth, optional `bastion_host` for jump-host access, `agent` to use a running SSH agent instead of an inline key.
- WinRM (`type = "winrm"`): password-based auth only (no key-pair concept), `https`/`insecure`/`use_ntlm` control transport security, default port differs (5985 plain / 5986 HTTPS vs. SSH's 22).

## 5. Hands-On

### 5.1 SSH Connection with a Private Key

**Purpose:** The most common connection form — key-based SSH auth to a Linux target.

**Syntax:**

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"
  key_name      = "deploy-key"

  connection {
    type        = "ssh"
    host        = self.public_ip
    user        = "ec2-user"
    private_key = file("${path.module}/keys/deploy-key.pem")
    timeout     = "5m"
  }

  provisioner "remote-exec" {
    inline = ["echo connected"]
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
aws_instance.web (remote-exec): Connecting to remote host via SSH...
aws_instance.web (remote-exec):   Host: 54.210.11.22
aws_instance.web (remote-exec):   User: ec2-user
aws_instance.web (remote-exec):   Password: false
aws_instance.web (remote-exec):   Private key: true
aws_instance.web (remote-exec):   Certificate: false
aws_instance.web (remote-exec): Connected!
aws_instance.web (remote-exec): connected
```

**Production usage example:** `private_key` reading from a local `.pem` file is common for standalone/demo use; in CI pipelines the key more often comes from a secrets manager and is written to a temp path or injected via a Terraform variable marked `sensitive` ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) rather than committed to the repo.

**Common errors:** `Permission denied (publickey)` almost always means either the wrong `user` for the AMI (e.g., `ubuntu` vs. `ec2-user` vs. `admin`, which varies by distribution) or a `private_key` that doesn't match the `key_name` actually attached to the instance.

### 5.2 SSH Connection Through a Bastion Host

**Purpose:** Reach a private-subnet instance with no direct public IP by hopping through a public bastion host — a common real-world topology.

**Syntax:**

```hcl
connection {
  type                = "ssh"
  host                = self.private_ip
  user                = "ec2-user"
  private_key         = file("${path.module}/keys/deploy-key.pem")
  bastion_host        = aws_instance.bastion.public_ip
  bastion_user        = "ec2-user"
  bastion_private_key = file("${path.module}/keys/bastion-key.pem")
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
aws_instance.web (remote-exec): Connecting to remote host via SSH...
aws_instance.web (remote-exec):   Host: 10.0.2.15
aws_instance.web (remote-exec):   Bastion Host: 54.210.11.22
aws_instance.web (remote-exec): Connected!
```

**Production usage example:** This is the standard pattern for provisioning private-subnet application servers whose only path to the outside world is through a hardened bastion/jump host — common in regulated environments where instances are deliberately not internet-reachable.

**Common errors:** Forgetting `bastion_private_key` (defaulting to reuse `private_key` only works if both hosts share the same key) causes an authentication failure at the bastion hop specifically, distinguishable in the log from a failure at the final host.

### 5.3 WinRM Connection for a Windows Target

**Purpose:** Show the WinRM equivalent for provisioning a Windows instance, where SSH-specific concepts (key pairs, bastion) don't apply.

**Syntax:**

```hcl
resource "aws_instance" "win" {
  ami           = "ami-0fedcba9876543210"
  instance_type = "t3.medium"

  connection {
    type     = "winrm"
    host     = self.public_ip
    user     = "Administrator"
    password = var.windows_admin_password
    https    = true
    insecure = true
    timeout  = "10m"
  }

  provisioner "remote-exec" {
    inline = ["powershell.exe -Command \"Write-Host 'connected'\""]
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
aws_instance.win (remote-exec): Connecting to remote host via WinRM...
aws_instance.win (remote-exec):   Host: 54.210.44.9
aws_instance.win (remote-exec):   Port: 5986
aws_instance.win (remote-exec):   User: Administrator
aws_instance.win (remote-exec): Connected!
aws_instance.win (remote-exec): connected
```

**Production usage example:** `insecure = true` (skipping certificate validation) is common in quick demos and internal networks but should be paired with a properly issued certificate and `insecure = false` in any production pipeline — treating certificate validation as optional defeats the purpose of `https = true`.

**Common errors:** WinRM connections often fail simply because the target's WinRM listener isn't enabled/configured yet — unlike SSH, which is enabled by default on most Linux AMIs, Windows AMIs frequently need WinRM explicitly enabled via `user_data` before Terraform's connection attempt can succeed at all.

## 6. Production Usage Notes

- `private_key` and `password` accept literal strings, but production usage almost always wraps them in `file()` (reading a key from disk) or a `sensitive` input variable ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) — never hardcode a credential directly in the `.tf` file.
- The `timeout` argument (default `5m`) is the single most impactful tuning knob for reducing spurious `remote-exec` failures on slow-booting instances — raising it costs nothing on the happy path and prevents false failures on the slow one.
- `host` is very commonly `self.public_ip` or `self.private_ip` — referencing the resource's own just-created attribute — which only works because the connection block lives inside the same resource; it cannot reference an entirely different resource's attributes without that resource already being fully created (i.e., an explicit `depends_on`).

## 7. Security Considerations

- A `connection` block is, functionally, a live credential the Terraform execution environment must hold to every host it provisions — treat the pipeline running `apply` with the same scrutiny as any system holding SSH private keys or admin passwords for your fleet.
- `insecure = true` on a WinRM connection disables certificate validation entirely, making the session vulnerable to interception on any network path that isn't otherwise trusted — acceptable for isolated lab networks, not for anything crossing an untrusted network segment.
- Prefer `agent = true` (using an already-running, already-authenticated SSH agent) over inlining a raw private key into configuration where feasible — it keeps the actual key material off disk in the Terraform working directory and out of any accidental state/log capture.
- Passwords and private keys referenced in a `connection` block can end up in Terraform state if they're derived from resource attributes rather than external secrets — mark any variable feeding a `connection` block `sensitive` ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) so it's at least redacted from CLI output, understanding that redaction does not remove it from the state file itself ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) covers that risk in full).

## 8. Common Troubleshooting Scenarios

| Symptom                                                | Likely Cause                                                                                                                             | Resolution Path                                                                                                                                |
| ------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------- |
| `Permission denied (publickey)` on SSH connection      | Wrong `user` for the target AMI, or `private_key` doesn't match the attached key pair                                                    | Confirm the correct default user for the AMI/distribution; verify `key_name` on the resource matches the key file referenced                   |
| Connection times out entirely, no auth attempt visible | Security group/firewall blocks the port, or `host` resolves to an unreachable address (private IP with no route from the Terraform host) | Verify network path independently (e.g., manual `ssh`/`Test-NetConnection`) before re-running `apply`                                          |
| WinRM connection refused                               | WinRM listener not enabled on the target Windows instance yet                                                                            | Ensure `user_data` enables WinRM at boot before the provisioner's connection attempt, or increase `timeout` to allow boot-time setup to finish |
| Bastion hop succeeds but final host connection fails   | `bastion_private_key` not set, defaulting to the wrong key for the target host                                                           | Set `bastion_private_key` and `bastion_user` explicitly rather than relying on defaults                                                        |

## 9. Best Practices

- Set an explicit `timeout` on every connection block rather than relying on the default — tune it to the slowest realistic boot time for the resource type in use.
- Scope connection blocks at the `provisioner` level (rather than `resource` level) whenever different provisioners in the same resource genuinely need different credentials (e.g., a `file` provisioner running as a deploy user vs. a `remote-exec` running as root) — resource-level blocks are simpler when one credential covers everything.
- Source credentials from variables marked `sensitive` or from a secrets manager ([§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md), [§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)) rather than inline literals, even in throwaway configuration — the habit matters more than the specific instance's risk.

## 10. Common Anti-Patterns / Mistakes

- **Hardcoding a private key or password directly as a string literal** in a `connection` block instead of `file()` or a sensitive variable — trivially leaks the credential to anyone with repo read access.
- **Setting `insecure = true` on WinRM as a permanent default** rather than a temporary workaround, silently normalizing unencrypted/unvalidated remote sessions across the fleet.
- **Assuming `host = self.public_ip` will work immediately after resource creation** without accounting for cloud-provider delay in public IP assignment or propagation — a `timeout` too short for this delay produces intermittent, hard-to-reproduce failures.

## 11. Interview Questions

**🎯 Beginner:** _"What is a `connection` block used for in Terraform?"_
**Model answer:** It supplies the details Terraform needs to log into a resource remotely — host address, username, credential, and protocol (SSH or WinRM) — so that a `remote-exec` or `file` provisioner has somewhere to send commands or files.
_What the interviewer is probing for:_ Basic recognition that this block exists to serve those two specific provisioner types.

**🎯 Intermediate:** _"What's the difference between placing a `connection` block at the resource level vs. inside a specific `provisioner` block?"_
**Model answer:** A resource-level connection block is the default for every provisioner in that resource. A connection block placed inside a specific provisioner overrides the resource-level default for that provisioner only — useful when, say, one provisioner needs to authenticate as a different user than another within the same resource.
_What the interviewer is probing for:_ Understanding of block scoping and override precedence, which is easy to get backward.

**🎯 Senior:** _"You need to provision a private-subnet instance with no public IP. How does the `connection` block need to change?"_
**Model answer:** `host` needs to point at the instance's private IP rather than a public one, and Terraform itself needs a network path to reach that private IP — typically achieved by adding `bastion_host`, `bastion_user`, and `bastion_private_key` arguments so Terraform tunnels the SSH session through a reachable bastion host rather than connecting directly, since the machine running `terraform apply` generally has no direct route into the private subnet.
_What the interviewer is probing for:_ Practical knowledge of the bastion pattern and why direct connection is impossible in that topology.

**🎯 Architect:** _"Your organization runs Terraform from a CI pipeline with no long-lived SSH keys stored anywhere, per security policy. How do you reconcile that with provisioners that need `remote-exec`?"_
**Model answer:** The cleanest reconciliation is usually to avoid `remote-exec` for that workload entirely and rely on boot-time provisioning (`user_data`/cloud-init, [§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) instead, since it requires no SSH credential held by the CI pipeline at all — the target host configures itself using instance metadata already available to it. If `remote-exec` is truly unavoidable, I'd look at ephemeral, just-in-time credential issuance (a short-lived certificate signed per-run by an internal CA or SSH certificate authority, injected only for the duration of that specific `apply` and never persisted) rather than a standing key, and I'd document why the no-provisioner alternative wasn't viable for that specific case, since it should be the exception, not the norm.
_What the interviewer is probing for:_ Whether the candidate can reconcile competing constraints (security policy vs. a real technical need) with a concrete mechanism, not just "that's a hard problem."

## 12. Common Misconceptions

1. **"`connection` blocks are needed for `local-exec` too."** They are not — `local-exec` never leaves the machine running Terraform, so it has nothing to connect to.
2. **"SSH and WinRM connection blocks accept the same arguments."** They share some (`host`, `user`, `password`, `timeout`), but key-based auth, `bastion_*` arguments, and `agent` are SSH-only; `https`, `insecure`, and `use_ntlm` are WinRM-only.
3. **"A `connection` block at the resource level always applies to every provisioner."** It applies by default, but any provisioner-level `connection` block silently overrides it for that specific provisioner — a common source of "why did this provisioner connect as a different user" confusion.
4. **"Setting a long `timeout` fixes any connection failure."** It only helps with slow-but-eventually-successful connections (boot delay); it does nothing for a connection that's fundamentally blocked (wrong security group, wrong credential) and will simply make that failure take longer to surface.

## 13. 🔑 Key Takeaways

- A `connection` block supplies host, user, credential, and protocol details so a `remote-exec` or `file` provisioner can reach the provisioned resource — `local-exec` never needs one.
- `type = "ssh"` (default) supports key- or password-based auth plus bastion-host tunneling via `bastion_host`/`bastion_user`/`bastion_private_key`.
- `type = "winrm"` supports password auth only, with `https`/`insecure`/`use_ntlm` controlling transport security for Windows targets.
- Connection blocks can be declared at the resource level (default for all provisioners) or inside a specific provisioner (override for that one).
- Connection credentials are live secrets the Terraform execution environment must hold — treat them with the same scrutiny as any fleet-wide SSH/WinRM credential.

## 14. Related Concepts & What's Next

[§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md) is the direct prerequisite this section completes — every `remote-exec` example there depended on a working connection. [§66](./Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md) covers what happens when a connection or the provisioner using it fails, via `on_failure`. [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) covers the deeper risk of connection credentials or their derived values ending up persisted in Terraform state. [§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) revisits whether a `remote-exec`/connection-based approach was the right call in the first place versus a boot-time or Ansible-handoff alternative.

**Next Section:** [§66](./Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md) — `Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md`
