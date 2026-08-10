# Section 3 (Part 1): Terraform vs. Configuration Management (Ansible/Puppet/Chef) — Provisioning vs. Configuration

## 1. Definition

**Plain language:** Terraform's job is to make infrastructure _exist_ — a VM, a network, a database instance. Configuration management tools like Ansible, Puppet, and Chef have a different job: once a machine exists, they install packages, edit config files, and manage the software running on it. Confusing the two — or trying to make one do the other's job — is one of the most common early mistakes in IaC adoption.

**Precise definition:** **Provisioning** is the act of creating, modifying, and destroying infrastructure resources (compute instances, networks, storage, managed services) against a cloud or platform API — Terraform's core competency. **Configuration management** is the act of installing software, managing configuration files, and enforcing the desired state of what's running _inside_ an already-existing machine — the core competency of tools like **Ansible** (agentless, SSH-based, YAML playbooks), **Puppet** (agent-based, pull model, its own DSL), and **Chef** (agent-based, pull model, Ruby DSL). While both categories are "declarative-ish" (Ansible is imperative-leaning with declarative modules; Puppet and Chef are more strictly declarative/convergent), they operate at different **layers of the stack** and are frequently used _together_ rather than as substitutes — Terraform provisions the VM, then hands off to Ansible/Puppet/Chef (or cloud-native bootstrapping like `user_data`/cloud-init, [§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) to configure what runs on it.

> 💡 **Tip:** A fast mental test for "is this a Terraform job or a configuration-management job?": if the answer to "does this resource need to exist at all" is what's being decided, it's provisioning (Terraform). If the resource already exists and the question is "what should be running inside it, and how should it be configured," it's configuration management (Ansible/Puppet/Chef).

## 2. Why This Matters

- **Avoiding tool misuse.** Using Terraform provisioners ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md), [§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)) to imperatively install and configure software inside a VM works, but fights the tool's design and forfeits idempotent convergence — the exact failure mode configuration-management tools are built to solve well.
- **Team structure and ownership boundaries.** Many organizations split "infrastructure provisioning" (platform/infra team, Terraform) from "application/OS configuration" (could be the same team, via Ansible) — understanding the boundary clarifies who owns what and where a given change belongs.
- **State model differences have operational consequences.** Terraform tracks resource state in a state file and reasons about drift structurally; Ansible has no persistent state file by default and instead re-evaluates the live target's actual condition on every run — mixing up these models leads to wrong assumptions about what "drift" even means in each tool.
- **Certification relevance.** The HashiCorp Terraform Associate exam explicitly tests understanding of "purpose of Infrastructure as Code" including how Terraform differs from configuration-management tools — this distinction is examinable, not just conceptual color.
- **Full-stack design decisions depend on this boundary.** [§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md) returns to this exact division of labor across Terraform + Ansible + Kubernetes for a complete stack — getting the boundary right here pays off directly there.

## 3. Prerequisites and Dependencies

Builds on [§1](./Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md) (declarative vs. imperative) and [§2](./Section-02-Part1-History-Terraform-Origins-IaC-Tooling-Landscape.md) (Terraform's origins and the IaC landscape). Assumes no prior Ansible/Puppet/Chef knowledge — this section introduces just enough of each to draw the contrast; a dedicated Ansible knowledge base exists at `../../../8. Ansible/00-Roadmap` for readers who want the full depth on that side.

## 4. Architecture / Conceptual Diagram

```text
   PROVISIONING LAYER                       CONFIGURATION LAYER
   (Terraform)                              (Ansible / Puppet / Chef)

   ┌──────────────────────────┐             ┌──────────────────────────┐
   │  Does the VM/DB/network  │   hands     │  Given a running VM,     │
   │  exist? Create/modify/   │   off to →  │  what packages, files,   │
   │  destroy against the     │             │  services, and configs   │
   │  cloud API.              │             │  should be present on    │
   │                          │             │  it?                     │
   │  resource "aws_instance" │             │  - name: install nginx   │
   │    "web" { ... }         │             │    apt: name=nginx       │
   └──────────────────────────┘             └──────────────────────────┘
            │                                          │
            ▼                                          ▼
   State file records what              No persistent state file
   Terraform created (§46)              by default — re-evaluates
                                         live target condition
                                         every run (idempotent
                                         modules, not a diff engine)

   Typical handoff: Terraform provisions VM → outputs its IP (§42) →
   Ansible inventory consumes that IP → Ansible configures the VM
```

- **Terraform**: agentless against the _provisioning_ API (cloud provider APIs), state-tracked, plan-before-apply. Operates at the "does this resource exist and what are its top-level attributes" layer.
- **Ansible**: agentless against the _target machine_ (SSH/WinRM), no default persistent state file — each run re-checks actual conditions on the target and converges idempotently module-by-module (e.g., the `apt` module checks if a package is already installed before acting).
- **Puppet/Chef**: agent-based (a daemon runs on each managed node, pulling configuration from a central server on an interval), more strictly declarative/convergent than Ansible's more script-like playbook execution, heavier operational footprint (requires running and maintaining agents and a control server) but stronger continuous-enforcement guarantees between manual runs.
- Terraform _can_ invoke configuration inside a resource via provisioners (`local-exec`/`remote-exec`, [§64](../Part9/Section-64-Part9-local-exec-and-remote-exec-Provisioners.md)), but this is explicitly discouraged by HashiCorp ([§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)) precisely because it blurs this layer boundary and forfeits idempotent convergence.

## 5. Hands-On

### 5.1 Terraform Provisioning a VM, Then Handing Off an Output

**Purpose:** Show the seam where Terraform's job ends and a configuration-management tool's job begins.

**Syntax:**

```hcl
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"
  tags = { Name = "web-01" }
}

output "web_public_ip" {
  value = aws_instance.web.public_ip
}
```

**Example usage and expected output:**

```bash
$ terraform apply
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

Outputs:

web_public_ip = "54.201.11.42"
```

**Production usage example:** A CI/CD pipeline runs `terraform apply`, captures `web_public_ip` via `terraform output -json` ([§30](../Part4/Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md)), writes it into a generated Ansible inventory file, then triggers `ansible-playbook -i inventory site.yml` — a clean, common two-stage pipeline pattern.

**Common errors:** Trying to SSH into the instance and configure it immediately after `apply` returns can race the instance's boot process (cloud-init/SSH daemon not yet ready) — production pipelines typically add a readiness check (a wait-for-SSH step) between the two stages rather than assuming instant availability.

### 5.2 Ansible Playbook Configuring What Terraform Provisioned

**Purpose:** Show the configuration-management side of the same workflow — idempotent software/config management on an already-existing machine.

**Syntax:**

```yaml
- hosts: web
  become: true
  tasks:
    - name: Install nginx
      apt:
        name: nginx
        state: present
    - name: Ensure nginx is running
      service:
        name: nginx
        state: started
        enabled: true
```

**Example usage and expected output:**

```bash
$ ansible-playbook -i inventory.ini site.yml
PLAY [web] *********************************************************
TASK [Install nginx] ***********************************************
changed: [54.201.11.42]
TASK [Ensure nginx is running] *************************************
ok: [54.201.11.42]
PLAY RECAP **********************************************************
54.201.11.42 : ok=2 changed=1 unreachable=0 failed=0
```

**Production usage example:** Running this same playbook again shows `changed=0` (nginx is already installed and running) — Ansible's module-level idempotency, distinct from but philosophically parallel to Terraform's plan/apply idempotency, applied at the OS/software layer instead of the infrastructure-resource layer.

**Common errors:** Assuming Ansible tracks state the way Terraform does — there's no equivalent of `terraform.tfstate` by default; each run re-evaluates live target conditions, meaning "drift" detection in Ansible is really just "the next run's idempotency check," not a persistent diff against a recorded prior state.

## 6. Production Usage Notes

- **The handoff pattern is the standard production integration**, not an edge case: Terraform provisions and outputs connection details (IPs, DNS names, secret ARNs); a separate tool (Ansible, or cloud-native `user_data`/cloud-init, [§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) configures what's running. Baking configuration logic into Terraform provisioners instead is the exception, used sparingly if at all.
- **Terraform's declarative-and-state-tracked model vs. Ansible's idempotent-but-stateless model has a practical consequence**: Terraform can tell you precisely what it will change before it acts (`plan`, [§25](../Part4/Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md)) because it has a recorded prior state to diff against; Ansible's `--check` (dry-run) mode approximates this by simulating module execution against live target state, but without a persisted "last known configuration" to diff from the way Terraform has.
- **Puppet/Chef's agent-based, pull model** suits environments needing continuous drift correction between explicit runs (an agent re-applies configuration on an interval, e.g., every 30 minutes, without a human triggering it) — a capability neither Terraform nor typical Ansible usage provides out of the box (Terraform only reconciles on explicit `apply`; Ansible only runs when explicitly invoked, absent additional scheduling infrastructure).

## 7. Security Considerations

- Ansible's SSH-based, agentless model means the control node needs SSH access (often privileged, via `become`) to every managed target — securing and rotating those SSH credentials is a distinct concern from securing Terraform's cloud provider API credentials ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) covers least-privilege for Terraform specifically).
- Puppet/Chef's agent-based model means every managed node runs a persistent daemon with elevated local privileges, communicating with a central control server — that control server becomes a high-value target, structurally different from Terraform's stateless-between-runs CLI invocation model.
- Whichever tool provisions vs. configures, secrets must not be hardcoded into either Terraform variables or Ansible playbooks/Puppet manifests — [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)–[§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md) cover dedicated secrets-management patterns applicable across both layers.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                             | Likely Cause                                                                                                                                                                        | Resolution Path                                                                                                                                                                                                                                                                           |
| ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Ansible playbook run immediately after `terraform apply` fails to connect           | Instance not yet fully booted / SSH daemon not ready; provisioning finished but the OS isn't ready                                                                                  | Add a wait-for-connection step (Ansible's `wait_for_connection` module) between provisioning and configuration stages                                                                                                                                                                     |
| Team member tries to "fix" application config drift by re-running `terraform apply` | Confusing configuration-layer drift (inside the VM) with infrastructure-layer drift (the VM's existence/attributes) — Terraform has no visibility into what's installed inside a VM | Use the configuration-management tool (Ansible/Puppet/Chef) to detect and correct in-VM drift; Terraform only tracks the resources it directly manages                                                                                                                                    |
| Terraform provisioner (`remote-exec`) intermittently fails mid-`apply`              | Using Terraform provisioners for what should be configuration management — no idempotent retry/convergence model, network blip fails the whole apply                                | Move the configuration logic out of Terraform provisioners entirely into Ansible/cloud-init ([§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md), [§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) |

## 9. Best Practices

- Keep the provisioning/configuration boundary explicit in team documentation and pipeline design: Terraform's job ends when infrastructure exists with correct attributes and outputs; a separate stage owns everything that happens "inside" that infrastructure.
- Prefer cloud-native bootstrapping (`user_data`, cloud-init) or a dedicated configuration-management tool over Terraform provisioners for anything beyond the most trivial one-time setup command — [§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md) covers exactly why HashiCorp discourages provisioners for this.
- When both tools are in the same pipeline, pass data across the boundary explicitly via Terraform outputs ([§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md)) consumed as Ansible inventory/variables, rather than hardcoding values independently in both tools (which will drift from each other).

## 10. Common Anti-Patterns / Mistakes

- **Using Terraform provisioners as a substitute for a real configuration-management tool.** This is the single most common instance of the "wrong tool for the layer" mistake — it works for trivial cases and fails poorly (no idempotent retry, opaque failures) as complexity grows.
- **Using Ansible (or Puppet/Chef) to provision cloud infrastructure instead of Terraform.** Ansible does have cloud modules capable of creating infrastructure, but doing so forfeits Terraform's plan-before-apply review, structured state tracking, and dependency graph — most teams that start this way eventually migrate provisioning to Terraform anyway.
- **Assuming one tool makes the other unnecessary.** "We use Terraform, so we don't need Ansible" (or vice versa) usually reflects a team that hasn't yet needed the layer the missing tool covers — not that the layer doesn't exist.

## 11. Interview Questions

**🎯 Beginner:** _"What's the basic difference between what Terraform does and what Ansible does?"_
**Model answer:** Terraform provisions infrastructure — it creates, modifies, and destroys things like VMs, networks, and databases by calling a cloud provider's API. Ansible is a configuration-management tool — once a machine exists, Ansible installs software, manages config files, and ensures the right things are running on it. They operate at different layers and are commonly used together: Terraform creates the VM, Ansible configures what's on it.
_What the interviewer is probing for:_ Basic conceptual separation of provisioning vs. configuration, the most fundamental distinction in this space.

**🎯 Intermediate:** _"Why does HashiCorp discourage using Terraform provisioners (like remote-exec) for configuration tasks that Ansible or Chef could do instead?"_
**Model answer:** Terraform provisioners execute imperative scripts/commands as a side effect of resource creation, which breaks the declarative, idempotent guarantees Terraform otherwise provides — there's no structured retry or convergence model if a provisioner partially fails, and Terraform has no visibility into whether the provisioner's changes are still in effect on a later run. Configuration-management tools like Ansible are purpose-built for this: their modules are individually idempotent, they can be re-run safely to correct drift, and they don't couple configuration logic to the infrastructure resource's create lifecycle. Using provisioners for anything beyond trivial bootstrapping reintroduces the exact non-idempotency problems declarative IaC is meant to solve.
_What the interviewer is probing for:_ Understanding of _why_ the recommendation exists, not just that it exists — ties back to the idempotency concepts from [§1](./Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md).

**🎯 Senior:** _"How do Terraform's and Ansible's state models fundamentally differ, and what operational consequence does that have?"_
**Model answer:** Terraform maintains a persistent state file recording exactly what it created and its last-known attribute values, and computes an explicit diff against that recorded state on every `plan`/`apply` — this is what lets it show you precisely what will change before acting. Ansible has no equivalent persistent state file by default; each playbook run re-evaluates the live target's actual condition module-by-module and acts idempotently based on what it currently observes, not a stored prior snapshot. The operational consequence: Terraform can detect and report drift as a structured diff against recorded state (though only current as of the last refresh, [§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md)); Ansible's "drift correction" is really just the natural idempotency of re-running the playbook — it has no way to tell you in advance, before running, exactly what has drifted, only what it will do about it once it re-evaluates.
_What the interviewer is probing for:_ Deep enough familiarity with both tools' internal models to reason about a real operational difference, not just "they're different tools."

**🎯 Architect:** _"Design the provisioning/configuration split for a new platform: EC2 instances running a Java application, RDS for the database, and application config that changes more frequently than the infrastructure itself. Where does each concern live?"_
**Model answer:** Terraform owns everything at the infrastructure-resource layer: the EC2 instances (count, instance type, networking, security groups), the RDS instance (engine, size, storage, backups), and IAM roles/policies attached to them — anything where the unit of change is "does this resource exist, and what are its top-level attributes." Application configuration that changes independently and more frequently (config files, environment-specific settings, deployed application version) should NOT live in Terraform, because that would mean every config change triggers a Terraform plan/apply cycle against infrastructure that hasn't actually changed, and increases blast radius unnecessarily. Instead, I'd bootstrap the EC2 instances minimally via `user_data`/cloud-init to install a base agent, then hand off ongoing application configuration and deployment to Ansible (or a dedicated deployment tool/CI pipeline) that can run independently of infrastructure changes, on its own cadence, without needing to touch Terraform state at all. RDS's own configuration (parameter groups, engine version) stays in Terraform since those genuinely are infrastructure-layer, low-frequency-change attributes.
_What the interviewer is probing for:_ Whether the candidate can draw the provisioning/configuration boundary correctly under a concrete, slightly ambiguous scenario (RDS parameter tuning could plausibly go either way) and justify the reasoning, not just recite the general rule.

## 12. Common Misconceptions

1. **"Ansible/Puppet/Chef and Terraform are competing, interchangeable tools."** They solve different layers of the problem (provisioning vs. configuration) and are commonly used together, not as alternatives to each other.
2. **"Terraform provisioners are the recommended way to configure a newly created resource."** HashiCorp explicitly discourages this as a first resort ([§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)) precisely because it undermines idempotency guarantees.
3. **"Ansible has no concept of state, so it can't detect drift at all."** It detects drift implicitly through each module's idempotent re-evaluation of live conditions on every run — it just doesn't persist a state file the way Terraform does to diff against in advance.
4. **"Puppet and Chef are obsolete now that Ansible exists."** They remain in active production use, particularly where continuous, agent-driven enforcement between manual runs is valued over Ansible's on-demand, agentless execution model.

## 13. 🔑 Key Takeaways

- Terraform provisions infrastructure (makes resources exist with correct attributes); Ansible/Puppet/Chef configure what runs inside already-existing infrastructure — different layers, commonly combined.
- Terraform maintains persistent state and computes an explicit pre-action diff; Ansible has no default persistent state file and instead re-evaluates live target conditions idempotently on each run.
- Puppet/Chef differ from Ansible by using an agent-based, pull model capable of continuous enforcement between manual runs, at the cost of a heavier operational footprint (running agents and a control server).
- HashiCorp explicitly discourages using Terraform provisioners as a substitute for real configuration management, because provisioners forfeit idempotent convergence.
- The standard production pattern is an explicit handoff: Terraform outputs connection details, a configuration-management tool consumes them to configure what's running.

## 14. Related Concepts & What's Next

[§1](./Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md) and [§2](./Section-02-Part1-History-Terraform-Origins-IaC-Tooling-Landscape.md) established the declarative model and Terraform's origins that this section contrasts against configuration management. [§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)–[§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) return to Terraform provisioners in full depth, including exactly why and when `local-exec`/`remote-exec` are (rarely) appropriate. [§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md) revisits this exact division of labor across a full Terraform + Ansible + Kubernetes stack. The Ansible knowledge base at `../../../8. Ansible/00-Roadmap` covers the configuration-management side in full depth.

**Next Section:** [§4](./Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md) — `Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md`
