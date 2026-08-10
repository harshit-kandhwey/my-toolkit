# Section 68 (Part 9): Alternatives to Provisioners (cloud-init, user_data, Ansible Handoff)

## 1. Definition

**Plain language:** Almost everything provisioners are used for — installing software, running setup scripts, configuring an application — can be done a different way that doesn't require Terraform to reach back into the resource over SSH/WinRM after creating it. This section covers the two main alternatives: boot-time scripts (cloud-init via `user_data` and its cloud-specific equivalents) that the instance runs on itself the moment it starts, and handing off to a dedicated configuration-management tool like Ansible as a separate step after Terraform finishes.

**Precise definition:** **Boot-time provisioning** (`user_data` on AWS, `custom_data` on Azure, `metadata_startup_script` on GCP) is a native resource argument that supplies a script or **cloud-init** configuration document to the instance at launch; the cloud platform's instance-metadata service delivers this payload to the instance itself, which executes it locally during boot — no network connection _from_ Terraform _to_ the instance is required at any point, only the one-way handoff of the script's content as part of the resource's own creation API call. **Ansible handoff** is an architectural pattern where Terraform's responsibility ends at provisioning the infrastructure (create the compute resources, output their addresses), and a separate, independently-run Ansible playbook — triggered as a distinct pipeline stage, often consuming Terraform's `output` values ([§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md)) as its inventory — performs all application-level configuration, using Ansible's own SSH-based, idempotent, and purpose-built configuration-management engine rather than Terraform's provisioner mechanism.

> 💡 **Tip:** The test for "should this be a provisioner or a boot-time script" is almost always: does this action need to happen exactly once, synchronously, as part of `apply`, with Terraform waiting for it — or can the instance just as well configure itself independently the moment it boots? The overwhelming majority of "install this package, start this service" use cases are the second kind, and boot-time scripts handle them with none of a provisioner's SSH-reachability dependency.

## 2. Why This Matters

- This is the practical payoff of everything [§63](./Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md) argued: knowing _specifically_ what to use instead of a provisioner, not just that provisioners are discouraged in the abstract.
- Boot-time scripts eliminate the single biggest source of provisioner fragility identified across this Part — the requirement that Terraform, at the exact moment `apply` runs, have live SSH/WinRM reachability to a resource that may still be booting, behind a security group, or on a private subnet.
- The Ansible-handoff pattern is the standard division of labor at most organizations that use both tools together, and is explicitly the subject of [§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md) later in the roadmap — understanding why that split exists (provisioning vs. configuration, echoing [§3](../Part1/Section-03-Part1-Terraform-vs-Configuration-Management-Ansible-Puppet-Chef.md)'s original Terraform-vs-Ansible framing) closes the loop opened in Part 1.
- This distinction — "does the exam expect a provisioner or a native alternative here" — is a recurring theme in Terraform Associate exam-style scenario questions ([§113](../Part16/Section-113-Part16-Common-Exam-Style-Scenario-Questions-Worked-Through.md)).

## 3. Prerequisites and Dependencies

This section assumes the full provisioner picture from [§63](./Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)–[§67](./Section-67-Part9-null_resource-and-Provisioner-Triggers.md), since it's framed explicitly as the alternative to that mechanism. It also revisits the provisioning-vs.-configuration-management distinction first drawn in [§3](../Part1/Section-03-Part1-Terraform-vs-Configuration-Management-Ansible-Puppet-Chef.md) (Terraform vs. Ansible/Puppet/Chef), now applied specifically to the provisioner-replacement decision rather than as a general tool comparison. Output values ([§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md)), consumed by an Ansible inventory in the handoff pattern, are a light prerequisite for 5.3 below.

## 4. Architecture / Conceptual Diagram

```text
   PROVISIONER APPROACH                     BOOT-TIME SCRIPT APPROACH
   (remote-exec, §64)                       (user_data / cloud-init)

   terraform apply                          terraform apply
        │                                        │
        ▼                                        ▼
   ┌────────────────┐                        ┌───────────────────────┐
   │ Create instance│                        │ Create instance,      │
   └────────────────┘                        │ PASS user_data script │
        │                                    │ as part of the SAME   │
        ▼                                    │ create API call       │
   Terraform OPENS SSH                       └───────────────────────┘
   CONNECTION to the                              │
   instance, waits,                               ▼
   sends commands over                       apply RETURNS — Terraform
   the network                                is done; no SSH round-trip
        │                                          │
        ▼                                          ▼
   apply blocked until                        Instance boots, cloud-init
   remote commands finish                     reads its OWN metadata,
   or timeout                                 runs the script LOCALLY,
        │                                     independently of Terraform
        ▼
   apply completes (or fails
   on connection/command error)


   ANSIBLE-HANDOFF APPROACH

   terraform apply  ──►  outputs (IPs, DNS names, tags)  ──►  ansible-playbook -i <dynamic inventory from outputs>
   (provisions infra only)                                    (configures applications, idempotently,
                                                                 as its own independently-run, retryable step)
```

- The boot-time approach fundamentally changes _where_ the script executes and _who_ waits for it: the instance configures itself; Terraform's `apply` doesn't block on that configuration completing (from Terraform's perspective, the resource is "created" the moment the create API call returns, regardless of how long cloud-init takes afterward).
- The Ansible-handoff approach makes the separation a first-class pipeline structure: Terraform's job ends at "infrastructure exists," and a second, independently retryable tool takes over from there — failures in configuration don't leave a `terraform apply` half-finished or a resource tainted ([§66](./Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md)).

## 5. Hands-On

### 5.1 AWS: `user_data` with a Cloud-Init Script

**Purpose:** Replace a `remote-exec` package-install pattern with a boot-time equivalent that needs no SSH connection from Terraform at all.

**Syntax:**

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"

  user_data = <<-EOF
    #!/bin/bash
    yum install -y nginx
    systemctl enable nginx
    systemctl start nginx
  EOF
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
aws_instance.web: Creating...
aws_instance.web: Creation complete after 12s [id=i-0a1b2c3d4e5f6g7h8]

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
# apply finished in ~12s — no SSH wait, versus ~30-60s+ typical for
# an equivalent remote-exec provisioner that must wait for boot AND
# SSH availability before it can even start running commands

$ ssh ec2-user@<instance-ip> "systemctl status nginx"
● nginx.service - The nginx HTTP and reverse proxy server
     Active: active (running) since ...
```

**Production usage example:** This is the default recommended pattern for any "install and start a service" need on a newly launched instance — it's also what auto-scaling groups rely on structurally, since a provisioner has no meaningful way to attach to instances an ASG launches dynamically, while `user_data` is simply part of the launch template every instance receives identically.

**Common errors:** Errors inside a `user_data` script are not visible to Terraform at all — `apply` succeeds regardless of whether the script inside actually worked, since Terraform's role ends at delivering the script; debugging requires checking the instance's own cloud-init logs (`/var/log/cloud-init-output.log` on most Linux distributions), not Terraform output.

### 5.2 Templated `user_data` with `templatefile`

**Purpose:** Show a more realistic pattern where the boot script is parameterized rather than a static heredoc, using the templating mechanism from [§19](../Part3/Section-19-Part3-String-Interpolation-and-Templating-heredoc-templatefile.md).

**Syntax:**

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"

  user_data = templatefile("${path.module}/templates/bootstrap.sh.tpl", {
    app_version = var.app_version
    environment = var.environment
  })
}
```

```bash
# templates/bootstrap.sh.tpl
#!/bin/bash
echo "Deploying version ${app_version} to ${environment}"
yum install -y nginx
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
aws_instance.web: Creation complete after 11s [id=i-0a1b2c3d4e5f6g7h8]
```

**Production usage example:** Templated boot scripts are the standard way to inject environment-specific configuration (an app version, a feature flag, a config endpoint) into a boot-time script without hardcoding it, keeping the same script reusable across dev/staging/prod ([§74](../Part10/Section-74-Part10-Environment-Promotion-Patterns-dev-staging-prod.md)'s environment promotion patterns).

**Common errors:** `templatefile` requires every variable referenced in the template to be supplied in the second argument's map — an unreferenced or misspelled variable name produces a clear error at `plan` time, before any instance is even created, unlike a provisioner script's errors which only surface at `apply` time against a live connection.

### 5.3 Terraform-Provisions, Ansible-Configures Handoff

**Purpose:** Show the full division-of-labor pattern: Terraform outputs what Ansible needs, and configuration happens as a genuinely separate step.

**Syntax:**

```hcl
# outputs.tf
output "web_instance_ips" {
  value = aws_instance.web[*].public_ip
}
```

```bash
$ terraform output -json web_instance_ips > inventory_ips.json
$ ansible-playbook -i generate_inventory.py site.yml
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
Apply complete! Resources: 3 added, 0 changed, 0 destroyed.

$ ansible-playbook -i generate_inventory.py site.yml
PLAY [webservers] *********************************************
TASK [Gathering Facts] ****************************************
ok: [10.0.1.11]
ok: [10.0.1.12]
ok: [10.0.1.13]

TASK [Install nginx] ******************************************
changed: [10.0.1.11]
changed: [10.0.1.12]
changed: [10.0.1.13]

PLAY RECAP *****************************************************
10.0.1.11    : ok=3  changed=1  unreachable=0  failed=0
10.0.1.12    : ok=3  changed=1  unreachable=0  failed=0
10.0.1.13    : ok=3  changed=1  unreachable=0  failed=0
```

**Production usage example:** This is the standard pattern in organizations running both tools: a CI/CD pipeline runs `terraform apply` as one stage, then a subsequent stage runs the Ansible playbook against the freshly created infrastructure — each tool fails and retries independently, and Ansible's own idempotent module system (unlike a raw provisioner script) can be safely re-run to converge configuration drift over time, something no Terraform provisioner offers.
**Common errors:** A common integration mistake is running the Ansible stage before instances have finished booting and become SSH-reachable — the pipeline needs its own readiness check (a health-check loop, or an explicit wait stage) independent of anything Terraform provides, since `terraform apply` completing only means the API call succeeded, not that the instance is fully booted.

## 6. Production Usage Notes

- Boot-time scripts have a hard practical limit on payload size (cloud-provider-specific, commonly in the tens of kilobytes for raw `user_data`) — very large bootstrap logic is usually better served by having the script download and run a larger script/package from internal storage (S3, a package repository) rather than inlining everything.
- Because `user_data` changes are visible to Terraform as a plain resource attribute, changing it shows up cleanly in `plan` output like any other diff — a meaningful advantage over provisioners, whose effects are invisible to `plan` entirely ([§63](./Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)).
- The Ansible-handoff pattern requires the CI/CD pipeline itself to own sequencing and readiness checks that a single-tool `apply` would have handled implicitly — this is real added pipeline complexity, and is the honest trade-off against provisioners' convenience of "it's all one command."

## 7. Security Considerations

- Boot-time scripts delivered via `user_data`/`custom_data` are visible to anyone who can query the instance's metadata service or, depending on the cloud, read the instance's own console/describe output — never place secrets directly in a boot-time script; fetch them from a secrets manager ([§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md), [§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)) from within the script at boot time instead.
- The Ansible-handoff pattern still requires SSH/WinRM reachability and credentials, exactly as a provisioner would — moving configuration out of Terraform doesn't eliminate that security surface, it just relocates it to Ansible's own credential-handling model (typically an SSH key or vault-backed credential Ansible manages independently), which is often easier to govern separately from Terraform's execution role.
- Both alternatives reduce Terraform's own execution role's required permissions: a Terraform pipeline that never needs `remote-exec` never needs to hold SSH/WinRM credentials at all, shrinking that pipeline's blast radius relative to one that does ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)'s least-privilege execution role principle).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                     | Likely Cause                                                                                                                                           | Resolution Path                                                                                                                                                                   |
| --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `user_data` script silently didn't run or partially failed                  | Terraform has no visibility into boot-time script success/failure — `apply` succeeding says nothing about the script's outcome                         | Check the instance's own cloud-init logs directly (SSH in after the fact, or a cloud-provider console log); add script-level error handling/logging                               |
| `user_data` change doesn't take effect on an existing instance              | Most compute resources only read `user_data` at launch, not on every boot — changing it in config doesn't retroactively reconfigure a running instance | Trigger a replace (`terraform apply -replace`, [§37](../Part5/Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) or handle in-place reconfiguration via Ansible instead |
| Ansible playbook run immediately after `terraform apply` fails to connect   | Instance hasn't finished booting/becoming SSH-reachable yet — `terraform apply` completing is not the same as "instance is ready"                      | Add an explicit readiness/wait step in the pipeline between the Terraform and Ansible stages                                                                                      |
| Templated `user_data` fails at `plan` time with an undefined variable error | `templatefile`'s variable map doesn't supply every variable referenced in the template file                                                            | Cross-check the template's variable references against the map passed as `templatefile`'s second argument                                                                         |

## 9. Best Practices

- Default to a boot-time script (`user_data`/`custom_data`/`metadata_startup_script`) for any "install and configure this instance" need before considering a provisioner — it should be the first alternative evaluated, not an afterthought.
- For anything beyond simple bootstrap logic — ongoing configuration management, drift correction, multi-host orchestration — hand off to Ansible (or an equivalent configuration-management tool) as a distinct pipeline stage rather than trying to force it into either a provisioner or an ever-growing boot script.
- Keep boot-time scripts idempotent and logged (write output to a known log path) even though they typically run only once at boot, since debugging a boot-time failure after the fact depends entirely on that log existing.

## 10. Common Anti-Patterns / Mistakes

- **Defaulting to `remote-exec` out of familiarity** without first checking whether the target resource type's native boot-time argument (`user_data` and equivalents) already covers the same need with none of the SSH-reachability dependency.
- **Growing a `user_data` script into an unmaintainable wall of bash** that really should have been handed off to Ansible once it passed simple package-install/service-start complexity — boot scripts are best kept short and delegate anything substantial to a proper configuration-management run.
- **Assuming the Ansible-handoff pattern removes the need for pipeline sequencing discipline.** Splitting provisioning and configuration into two tools means the pipeline itself must now guarantee correct ordering and readiness checks that a single-tool `apply` would have handled implicitly through the provisioner's own wait-and-connect behavior.

## 11. Interview Questions

**🎯 Beginner:** _"Name one alternative to using a `remote-exec` provisioner to install software on a new instance."_
**Model answer:** Use the instance's native boot-time script argument — `user_data` on AWS, `custom_data` on Azure, `metadata_startup_script` on GCP — which the instance itself executes at boot, with no SSH connection needed from Terraform.
_What the interviewer is probing for:_ Basic awareness that a native, provisioner-free alternative exists and roughly how it works.

**🎯 Intermediate:** _"Why does a `user_data` boot script avoid the reliability problems `remote-exec` has?"_
**Model answer:** `remote-exec` requires Terraform to open a live SSH/WinRM connection to the instance at the exact moment `apply` runs, which depends on the instance already being network-reachable and fully booted — a common source of timeouts and hangs. `user_data` is delivered as part of the same API call that creates the instance; the instance reads it from its own metadata service and runs it locally once it boots, with no network round-trip back to Terraform required at all. Terraform's `apply` doesn't wait on the script's execution — it only waits on the create API call succeeding.
_What the interviewer is probing for:_ Understanding of exactly what mechanism removes the reachability dependency, not just that the alternative "is better."

**🎯 Senior:** _"When would you still choose Ansible over a `user_data` boot script, given that both avoid Terraform provisioners?"_
**Model answer:** `user_data` runs once, at boot, and typically isn't designed to be re-run to correct drift on a live instance — it's a one-shot bootstrap mechanism. Ansible is built for ongoing, idempotent configuration management: re-running a playbook against already-configured hosts safely converges any drift, supports more complex orchestration across many hosts (rolling updates, ordered multi-tier configuration), and has a mature module ecosystem for application-level configuration that a shell script reimplements poorly. I'd use `user_data` for simple, one-shot bootstrap (install a base agent, join a fleet) and Ansible for anything that needs to be maintained, re-applied, or orchestrated across multiple hosts over the instance's lifetime.
_What the interviewer is probing for:_ Nuanced judgment — recognizing that "avoid provisioners" doesn't collapse into one universal alternative; the two alternatives serve different needs.

**🎯 Architect:** _"Design the division of responsibility between Terraform and Ansible for a fleet of application servers that need both initial bootstrap and ongoing configuration management. Where does each tool's responsibility start and end?"_
**Model answer:** Terraform owns everything about the infrastructure's existence and shape: instances, networking, security groups, load balancer registration, and IAM roles — its output is a set of running, reachable instances plus structured outputs (IPs, tags, DNS names) that downstream tooling can consume. A minimal `user_data` script handles only what's needed for the instance to become manageable at all — installing an SSH-accessible base image, joining a known network, perhaps registering with a configuration-management control node — deliberately kept thin. Ansible then owns everything about the instance's ongoing application state: package versions, application configuration, service management, and rolling updates, run as its own pipeline stage (or on a schedule, for drift correction) entirely independent of Terraform's apply cycle, using Terraform's outputs as a dynamically generated inventory. The boundary is explicit: Terraform answers "does the right infrastructure exist," Ansible answers "is the software on it correctly configured" — and neither tool's failure mode blocks or corrupts the other's state, unlike a provisioner failure which directly taints a Terraform resource.
_What the interviewer is probing for:_ A clear, defensible architectural boundary between the two tools' responsibilities, echoing back to the provisioning-vs.-configuration-management distinction from [§3](../Part1/Section-03-Part1-Terraform-vs-Configuration-Management-Ansible-Puppet-Chef.md), now applied concretely.

## 12. Common Misconceptions

1. **"`user_data` and provisioners accomplish the exact same thing, just with different syntax."** They differ fundamentally in _where_ execution happens and _what_ Terraform waits on — `user_data` executes on the instance itself at boot with no Terraform-side wait on the script's outcome; a provisioner executes over a live connection Terraform establishes and blocks on.
2. **"Since `user_data` avoids provisioner problems, it should replace every provisioner use case."** It replaces most creation-time bootstrap use cases well, but has no equivalent for destroy-time actions (deregistering from a cluster before termination) or actions needing a return value fed back into Terraform — those remain provisioner (or entirely different-approach) territory.
3. **"Changing `user_data` reconfigures a running instance."** Most compute resources only read `user_data` at initial launch — modifying it in Terraform doesn't push the change to an already-running instance without a replace or an independent re-configuration mechanism (Ansible, most typically).
4. **"Ansible handoff means Terraform and Ansible are redundant with each other."** They're complementary by design in this pattern — Terraform provisions infrastructure once; Ansible configures and re-configures it repeatedly over its lifetime; neither replaces the other's role.

## 13. 🔑 Key Takeaways

- Boot-time scripts (`user_data`, `custom_data`, `metadata_startup_script`) execute on the instance itself at boot via the cloud's metadata service — no SSH/WinRM connection from Terraform is required, eliminating the reachability dependency that makes `remote-exec` fragile.
- Terraform has no visibility into a boot-time script's success or failure — `apply` completing only means the create API call succeeded, not that the script ran correctly; debugging requires checking the instance's own boot logs.
- The Ansible-handoff pattern splits responsibility cleanly: Terraform provisions infrastructure and exposes outputs; a separately run, independently retryable Ansible playbook performs ongoing, idempotent application configuration.
- Boot-time scripts suit simple, one-shot bootstrap; Ansible (or equivalent configuration management) suits ongoing, re-appliable, drift-correcting configuration across a fleet.
- Neither alternative eliminates all provisioner use cases entirely — destroy-time actions and cases needing a value fed back into Terraform's own state remain harder to fully replace, which is why [§63](./Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md) frames provisioners as discouraged rather than banned.

## 14. Related Concepts & What's Next

This section closes Part 9 by resolving the tension [§63](./Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md) opened: provisioners exist and are supported, but the overwhelming majority of real use cases are better served by the boot-time and Ansible-handoff patterns covered here. [§19](../Part3/Section-19-Part3-String-Interpolation-and-Templating-heredoc-templatefile.md)'s `templatefile` mechanics underpin the templated boot-script pattern in 5.2. [§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md)'s output values are what the Ansible-handoff pattern in 5.3 depends on for building a dynamic inventory. [§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md), much later in the roadmap, returns to this exact Terraform/Ansible/Kubernetes division of labor at full-stack scale. Part 10, starting next, moves from provisioners entirely into CLI workspaces and multi-environment patterns.

**Next Section:** [§69](../Part10/Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md) — `Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md`
