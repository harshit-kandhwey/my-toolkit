# Section 134 (Part 16): Network-as-Code: Infrastructure Tooling for Network Configuration

## 1. Definition

**Plain language:** For decades, network configuration meant an engineer typing commands directly into a router or switch's console, one device at a time, with the "documentation" living in someone's head or a Word document that was out of date the moment it was saved. Network-as-code applies the same discipline software engineers use for application code — version control, code review, automated testing, repeatable deployment — to network configuration itself, so the configuration a device is running and the configuration recorded in a repository are structurally guaranteed to be the same thing.

**Precise definition:** **Network-as-code** (a specific application of the broader infrastructure-as-code discipline) is the practice of defining network configuration — cloud VPC/VNet resources, on-premises device configuration, or both — as declarative or procedural code stored in version control, applied through an automated, repeatable tool rather than manual console access, and reviewed via the same pull-request workflow used for application code. The dominant tools are **Terraform** and **Pulumi** for declarative, provider-API-driven cloud networking (VPCs, subnets, route tables, security groups per [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) and [§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md)–[§103](../Part12/Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md)), and **Ansible** for procedural, agentless configuration push to both cloud and on-premises network devices, commonly used to manage router/switch configuration, VLAN assignments, and ACLs at fleet scale. Network-as-code directly operationalizes the change-management discipline from [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md) by making "the documented intended state" and "what actually gets applied to devices" the identical artifact, closing the drift gap at a structural level rather than a process-discipline level.

> 💡 **Tip:** The core mental model: network-as-code doesn't eliminate the need for good change management from [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md) — it automates the *mechanism* by which that discipline is enforced, replacing "please remember to document this change" with "the change literally cannot be applied without first being written down as reviewable code."

## 2. Why This Matters

- **This is the direct technical resolution to the entire configuration-drift problem described in [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md)** — a network whose state is fully defined in version-controlled code has no meaningful gap between "intended" and "actual," beyond whatever brief window exists between an approved code change and its deployment.
- **Nearly every modern cloud networking deployment (VPCs, subnets, route tables, security groups) is provisioned via network-as-code tooling in professional environments**, making Terraform/Pulumi fluency a baseline expectation for cloud/DevOps engineering roles, not an optional specialization.
- **Code review becomes the change-approval mechanism from [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md)**, meaning a pull request against network configuration gets the same scrutiny, history, and rollback-via-revert capability as any application code change, with far less process overhead than a traditional change ticket.
- **Automated drift detection becomes possible for the first time** — a `terraform plan` or Ansible check-mode run against live infrastructure directly reveals any divergence from the code's declared state, operationalizing the diff-based detection technique introduced in [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md).
- **Interviewers increasingly expect basic fluency with these tools even for candidates in traditional networking roles**, since the industry-wide shift toward network-as-code means manual console-only configuration skills alone are no longer sufficient for most cloud/infrastructure positions.

## 3. Prerequisites and Dependencies

This section is the direct technical continuation of the change-management and drift problem introduced in [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md), and assumes the cloud VPC/VNet, subnet, and security-group concepts from [§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md) through [§103](../Part12/Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md) and [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md), since those are the most common resources network-as-code tooling actually manages. It also depends on basic familiarity with the routing and switching concepts from Parts 4 and 5, since Ansible-managed on-premises network automation directly targets router/switch configuration syntax built on those fundamentals. It connects forward to [§135](Section-135-Part16-Common-Anti-Patterns-and-Misconceptions.md) and [§137](Section-137-Part16-Security-Best-Practices-Recap-Across-the-Stack.md), since manual, undocumented configuration is one of the anti-patterns synthesized there and network-as-code is presented as the structural best-practice answer, and to [§138](Section-138-Part16-Scaling-Networking-for-Growth-From-Single-VPC-to-Multi-Region-Enterprise.md), since scaling a network across regions is dramatically more tractable when the network's definition is code that can be parameterized and replicated rather than manually re-created per site.

## 4. Architecture / Conceptual Diagram

```text
   TRADITIONAL (MANUAL) WORKFLOW:

   Engineer ──console/SSH──► Device ──configuration change applied directly──►
                                              (no review, no history, no
                                               guaranteed source of truth)


   NETWORK-AS-CODE WORKFLOW:

   Engineer ──writes change──► Version-Controlled Code (Terraform/Ansible)
                                        │
                                        ▼
                              Pull Request opened
                                        │
                              ┌─────────┴─────────┐
                              │   Peer Review      │  = the change-management
                              │   (§133's approval  │    approval step,
                              │    step, automated) │    automated by tooling
                              └─────────┬─────────┘
                                        ▼
                          terraform plan / ansible --check
                          (shows EXACT diff vs. live state)
                                        │
                                        ▼
                              Approved ──► Merge ──► Automated Apply
                                        │
                                        ▼
                          Device/Cloud Resource Configuration
                          (now IDENTICAL to what's in version control)
                                        │
                                        ▼
                          Scheduled `plan`/`--check` re-runs =
                          continuous, automated drift detection
```

- The "plan"/"check" step before apply is the structural equivalent of [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md)'s manual "verify" and "diff against baseline" steps, except it happens automatically, before every single change, rather than depending on an engineer remembering to run it.
- Version control history replaces the informal change-ticket record from [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md) with a complete, permanent, and searchable audit trail — every change has an author, a timestamp, a reviewer, and a diff, by construction.
- Because the code IS the source of truth, drift detection becomes a scheduled, automated re-run of the same plan/check step used for every change, rather than a separate manual auditing process.

## 5. Hands-On

### 5.1 Defining a Cloud VPC and Subnet as Terraform Code

**Purpose:** Show the declarative pattern that replaces manually clicking through a cloud console or running one-off CLI commands to create a VPC (per [§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md)'s concepts) — with every parameter now version-controlled and reviewable.

**Syntax:**

```hcl
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  tags       = { Name = "prod-vpc" }
}

resource "aws_subnet" "app" {
  vpc_id     = aws_vpc.main.id
  cidr_block = "10.0.1.0/24"
  tags       = { Name = "prod-app-subnet" }
}
```

**Example usage and expected output:**

```bash
$ terraform plan
Terraform will perform the following actions:
  # aws_vpc.main will be created
  # aws_subnet.app will be created
Plan: 2 to add, 0 to change, 0 to destroy.

$ terraform apply
aws_vpc.main: Creation complete after 3s [id=vpc-0a1b2c3d]
aws_subnet.app: Creation complete after 1s [id=subnet-0e4f5g6h]
```

- `terraform plan`'s explicit "2 to add, 0 to change, 0 to destroy" summary is exactly the kind of pre-change verification that a manual console-based workflow has no equivalent for — every resource affected is enumerated before anything actually happens.

**Production usage example:** Cloud teams define their entire VPC/subnet/route-table layout ([§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md)–[§101](../Part12/Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)) as Terraform modules, parameterized per environment (dev/staging/prod) and per region, so a new region's network can be stood up by changing a handful of input variables rather than manually re-clicking through console workflows.

**Common errors:** Manually modifying a Terraform-managed resource through the cloud console "just this once" creates exactly the drift scenario from [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md) — the next `terraform plan` will show an unexpected diff (or, worse, silently revert the manual change on the next apply), which is precisely why network-as-code environments should disable or tightly restrict console-based manual access to managed resources.

### 5.2 Using Ansible to Push Configuration to Network Devices at Fleet Scale

**Purpose:** Show the procedural, agentless automation pattern used for on-premises router/switch configuration that Terraform's cloud-API-centric model doesn't directly address.

**Syntax:**

```yaml
# playbook.yml
- name: Configure standby priority on distribution switches
  hosts: distribution_switches
  tasks:
    - name: Set HSRP priority
      ios_config:
        lines:
          - standby 1 priority 110
          - standby 1 preempt
        parents: interface GigabitEthernet0/1
```

**Example usage and expected output:**

```bash
$ ansible-playbook -i inventory.yml playbook.yml --check
PLAY [Configure standby priority on distribution switches] *******
TASK [Set HSRP priority] ******************************************
changed: [dist-switch-01]   # --check mode: shows what WOULD change
changed: [dist-switch-02]

$ ansible-playbook -i inventory.yml playbook.yml
PLAY RECAP *********************************************************
dist-switch-01 : ok=2  changed=1  unreachable=0  failed=0
dist-switch-02 : ok=2  changed=1  unreachable=0  failed=0
```

- Running with `--check` first, and only then without it, mirrors the `terraform plan` → `apply` pattern exactly, letting an engineer confirm the exact intended change (here, an HSRP priority/preempt setting from [§132](Section-132-Part16-High-Availability-Networking-Redundancy-Failover-HSRP-VRRP-Concepts.md)) across an entire fleet before committing it anywhere.

**Production usage example:** Enterprises managing dozens or hundreds of on-premises switches use Ansible playbooks, organized by device role (access, distribution, core per [§131](Section-131-Part16-Enterprise-Network-Architecture-Patterns-Three-Tier-Spine-Leaf.md)), to push consistent configuration changes fleet-wide in minutes rather than one device at a time via console access.

**Common errors:** Writing a playbook that doesn't idempotently check current state before applying a change can cause `changed` to report true on every run even when nothing actually needed to change, undermining the reliability of the tool's own change-detection output — well-written network automation modules (like `ios_config`) handle this correctly, but hand-rolled raw command-execution tasks often don't.

### 5.3 Detecting Drift Automatically With a Scheduled Terraform Plan

**Purpose:** Show network-as-code's structural drift-detection capability in action, directly answering the manual-diff technique from [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md) with an automated equivalent.

**Syntax:**

```bash
terraform plan -detailed-exitcode
# exit code 0 = no changes (no drift)
# exit code 2 = changes detected (drift or pending legitimate change)
# exit code 1 = error
```

**Example usage and expected output:**

```bash
$ terraform plan -detailed-exitcode
  # aws_security_group_rule.app_ingress has been changed outside of Terraform
  ~ resource "aws_security_group_rule" "app_ingress" {
      ~ cidr_blocks = ["10.0.0.0/16"] -> ["0.0.0.0/0"]
    }
Plan: 0 to add, 1 to change, 0 to destroy.
$ echo $?
2
```

- This is a real, security-relevant drift finding: a security group rule's source CIDR was manually widened from an internal range to the entire internet outside of the code-managed process — exactly the kind of change [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md) warns is dangerous precisely because it happened outside review.

**Production usage example:** CI/CD pipelines run a scheduled `terraform plan -detailed-exitcode` against production infrastructure on a regular cadence (hourly or daily), alerting the team automatically whenever exit code 2 appears outside of an expected, in-progress deployment.

**Common errors:** Treating every detected drift as something to immediately auto-remediate by force-reapplying the code's state — sometimes a manual out-of-band change was a legitimate emergency fix (per [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md)'s accelerated emergency path) that should be reconciled back into the code deliberately, not silently overwritten.

## 6. Production Usage Notes

- **Terraform/Pulumi dominate cloud-native network resource management** (VPCs, subnets, route tables, security groups, load balancers), while **Ansible remains the standard for on-premises and hybrid device configuration push**, and most real organizations use both, matched to where each tool's model fits best.
- **State file management (Terraform's state, specifically) is a critical operational concern** — the state file is the tool's own record of what it believes it manages, and losing or corrupting it (or having two engineers apply changes from stale, unsynced local state) can itself become a drift and consistency problem, which is why remote, locked state backends are standard practice.
- **Not every network element is realistically manageable as code** — some legacy hardware, vendor-specific features, or manual physical cabling changes remain outside network-as-code's reach, and a mature program is explicit about which parts of the network are and aren't currently code-managed rather than pretending full coverage exists.

## 7. Security Considerations

- Network-as-code repositories themselves become high-value security targets — a compromised CI/CD pipeline or a leaked cloud credential used by the automation can modify security groups ([§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)), routing, or firewall rules ([§82](../Part10/Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md)) at scale, far faster than a human attacker manually reconfiguring devices one at a time.
- Least-privilege credentials for the automation tooling itself matter enormously — an Ansible or Terraform service account with broader permissions than the specific resources it's meant to manage is a significant blast-radius risk if that credential is ever compromised.
- Code review for network-as-code changes should specifically scrutinize security-relevant resources (security groups, NACLs, firewall rules) with the same rigor a security team would apply to a manual change-ticket review, since a rubber-stamped pull request is not meaningfully safer than an unreviewed manual change.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely Cause | Resolution Path |
| --- | --- | --- |
| `terraform plan` shows an unexpected change to a resource nobody intended to modify | A manual out-of-band change was made directly through the console/CLI, creating drift | Reconcile the manual change back into code deliberately (if legitimate) or reapply the code's intended state (if the manual change was unauthorized) |
| Two engineers' Terraform applies conflict or one overwrites the other's changes | Local, unsynced state files, or missing remote state locking | Migrate to a remote, locked state backend so concurrent applies are serialized safely |
| An Ansible playbook reports `changed` on every run even when nothing should have changed | Non-idempotent task implementation (e.g., raw command execution instead of a proper idempotent module) | Rewrite the task using an idempotent, state-aware module rather than unconditional command execution |
| A scheduled drift-detection plan run finds many false positives | Comparing against fields that legitimately vary at the provider/device level, or state file drift unrelated to actual device configuration | Refine the plan/check scope and, if needed, `terraform refresh`/reconcile the state file against verified actual reality |

## 9. Best Practices

- Manage every network resource that a provider's API or device automation tooling can reach as code, and treat any remaining manually-managed exceptions as explicitly tracked technical debt, not a silent gap.
- Require pull-request review for every network-as-code change, with heightened scrutiny for security-relevant resources, exactly mirroring the risk-scaled review discipline recommended in [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md).
- Run drift-detection plan/check operations on a recurring, automated schedule rather than only at the moment of an intentional change, so unauthorized or emergency out-of-band modifications surface quickly.

## 10. Common Anti-Patterns / Mistakes

- **Manually modifying a network-as-code-managed resource through a console "just this once,"** which reintroduces exactly the drift problem the tooling exists to prevent, and can result in the next automated apply silently reverting a change someone believed was intentional.
- **Storing cloud credentials or device automation secrets directly in the network-as-code repository**, rather than in a dedicated secrets manager referenced at runtime — a mistake with especially severe consequences given the broad blast radius these credentials typically carry.
- **Adopting network-as-code tooling only for greenfield resources while leaving the existing production network entirely unmanaged by it**, which leaves the majority of the actual risk (the existing, drift-prone estate) untouched while giving a false sense of having "solved" the problem.

## 11. Interview Questions

**🎯 Beginner:** _"What does it mean to manage network configuration 'as code,' and what's the main benefit over manual console configuration?"_
**Model answer:** It means defining network resources — cloud VPCs, subnets, security groups, or on-premises device configuration — as version-controlled code, applied through an automated tool rather than typed directly into a console. The main benefit is that the code becomes the single source of truth: every change has a reviewable diff, an author, and a history, and the tool can show exactly what will change before it happens, which eliminates the guesswork and undocumented-change risk that comes with manual configuration.
_What the interviewer is probing for:_ A clear grasp of the core value proposition — traceability and review — rather than just naming tools.

**🎯 Intermediate:** _"What's the difference between how Terraform and Ansible are typically used for network automation, and why would an organization use both?"_
**Model answer:** Terraform (and similarly Pulumi) is declarative and provider-API-driven — you describe the desired end state of cloud resources like VPCs, subnets, and security groups, and it figures out what API calls achieve that state, tracking everything in a state file. Ansible is procedural and agentless, executing a defined sequence of tasks against a target — commonly used to push configuration to on-premises routers and switches where there's no cloud-style declarative API, or to perform ordered operational tasks that aren't naturally expressed as "desired state." Organizations with both cloud and on-premises/hybrid footprints typically use Terraform for the cloud-native resource layer and Ansible for on-premises device configuration and operational automation, since each tool's model fits its respective domain better than trying to force one tool to do both jobs.
_What the interviewer is probing for:_ Understanding that tool choice follows the underlying resource model (declarative cloud APIs vs. procedural device configuration), not arbitrary preference.

**🎯 Senior:** _"A team's `terraform plan` on production infrastructure keeps showing unexpected diffs on a specific security group, even though no one on the team recalls making manual changes. How would you investigate and resolve this?"_
**Model answer:** First, I'd check cloud provider audit logs (e.g., CloudTrail) for the specific security group's resource ID to see exactly what API calls modified it, when, and under which identity — this either confirms an undocumented manual change or reveals an automated process outside Terraform's awareness (another pipeline, an auto-remediation tool, or even a different Terraform state managing an overlapping resource). If it's a genuine manual change, I'd treat it per [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md)'s process — determine if it was a legitimate emergency fix that needs to be reconciled into code, or an unauthorized change that needs to be reverted and reviewed. If it's a competing automation tool, I need to establish clear resource ownership so only one system of record manages that security group going forward, since two systems both "owning" the same resource is a structural drift generator that no amount of individual vigilance fixes. I'd also verify the Terraform state file itself isn't stale or corrupted, since a `terraform refresh` mismatch can sometimes present similarly to genuine drift.
_What the interviewer is probing for:_ A methodical investigation process that distinguishes between human-caused drift, competing automation, and tooling/state issues, rather than assuming the first plausible explanation.

**🎯 Architect:** _"Design the network-as-code strategy for an organization migrating from a decade of manual, console-managed on-premises networking plus ad hoc cloud resource creation, toward a fully code-managed network across both environments."_
**Model answer:** I'd sequence this by risk and tractability rather than attempting both environments simultaneously. Cloud resources are the more tractable starting point given their native declarative APIs — I'd begin by importing existing cloud VPCs, subnets, security groups, and route tables ([§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md)–[§103](../Part12/Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md)) into Terraform state using its import functionality, validating that the generated code accurately matches the actual live resources before treating Terraform as authoritative, then requiring all future cloud changes to go through code review. For the on-premises fleet, I'd introduce Ansible incrementally, starting with the highest-value, most repetitive configuration tasks (VLAN assignments, ACL pushes, standardized HA settings per [§132](Section-132-Part16-High-Availability-Networking-Redundancy-Failover-HSRP-VRRP-Concepts.md)) across device groups, while leaving genuinely one-off or vendor-quirky legacy configuration as an explicitly tracked, still-manual exception list rather than forcing full coverage prematurely. Throughout, I'd pair this rollout with the change-management process from [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md) — even resources not yet code-managed should go through ticketed review — so the organization gets the governance benefit immediately while the tooling coverage expands over subsequent quarters. I'd also insist on remote, locked state management and least-privilege automation credentials from day one, since retrofitting those securely after a team has grown dependent on loose practices is far harder than establishing them at the outset.
_What the interviewer is probing for:_ Realistic sequencing of a large-scale organizational change, correctly identifying cloud resources as the faster win and on-premises device automation as requiring a more incremental approach, while keeping security and state-management fundamentals non-negotiable from the start.

## 12. Common Misconceptions

1. **"Network-as-code means the network is now 'set and forget.'"** It still requires ongoing review discipline, credential hygiene, and monitoring for drift — the tooling automates enforcement of good practice, it doesn't eliminate the need for the practice.
2. **"Terraform and Ansible are interchangeable and it doesn't matter which one you use for a given task."** Their underlying models (declarative desired-state vs. procedural task execution) fit different problem shapes — cloud resource provisioning versus on-premises device configuration push, respectively — and forcing the wrong tool onto the wrong problem produces worse outcomes than picking deliberately.
3. **"Once a resource is imported into network-as-code, drift is impossible."** Drift remains entirely possible if anyone retains manual console access and uses it — code management reduces drift's likelihood and improves its detectability, but doesn't make it structurally impossible unless manual access is also restricted.
4. **"Automated drift detection means automated drift remediation should always be immediate and unconditional."** Some detected drift reflects a legitimate emergency change that should be reconciled into code deliberately, not silently and automatically overwritten by the next apply.

## 13. 🔑 Key Takeaways

- Network-as-code applies version control, code review, and automated, repeatable deployment to network configuration, structurally closing the drift gap described in [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md) rather than relying purely on process discipline.
- Terraform/Pulumi are the standard tools for declarative cloud network resource management; Ansible is the standard for procedural, agentless on-premises and hybrid device configuration.
- `terraform plan`/`ansible --check` before every apply is the automated equivalent of [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md)'s manual verification step, and running the same operation on a schedule provides continuous, automated drift detection.
- Manual out-of-band changes to a code-managed resource reintroduce exactly the drift problem network-as-code exists to prevent, and should be treated as a process exception requiring deliberate reconciliation.
- Credential hygiene and state-file management for the automation tooling itself deserve the same security rigor as the network resources they manage, given the tooling's broad operational blast radius.

## 14. Related Concepts & What's Next

This section operationalizes [§133](Section-133-Part16-Network-Change-Management-and-Configuration-Drift.md)'s change-management principles into concrete tooling, and its drift-detection capability directly extends the manual technique introduced there. It sets up [§135](Section-135-Part16-Common-Anti-Patterns-and-Misconceptions.md)'s synthesis of anti-patterns across the whole topic, where manual, undocumented configuration is highlighted as a recurring root cause this section's practices are meant to eliminate, and it connects forward to [§138](Section-138-Part16-Scaling-Networking-for-Growth-From-Single-VPC-to-Multi-Region-Enterprise.md), since replicating a network design across multiple regions is dramatically more tractable when that design already exists as parameterized, version-controlled code rather than as tribal knowledge.

**Next Section:** [§135](Section-135-Part16-Common-Anti-Patterns-and-Misconceptions.md) — `Section-135-Part16-Common-Anti-Patterns-and-Misconceptions.md`
