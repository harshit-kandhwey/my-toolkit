# Section 97 (Part 13): Infrastructure as Code on Linux (Ansible, Terraform Provisioning)

Part 12 (§89–§96) closed out Security Hardening — threat modeling, SSH hardening, mandatory access control, kernel-parameter hardening, auditing, patch management, secrets, and CIS Benchmarks. Part 13 shifts to a different concern entirely: how Linux hosts and their configuration get **created and managed at scale in the first place**, rather than how an individual host is locked down once it exists. §97, the first section of this Part, starts with the broadest framing — Infrastructure as Code — before later sections in this Part go deeper on specific pieces of that picture.

## 1. What Infrastructure as Code Actually Means

**Infrastructure as Code (IaC)** means defining infrastructure — servers, networking, storage, configuration — as version-controlled, declarative files, rather than as a sequence of manual commands typed into a terminal or a one-off script run by hand against a single host. The infrastructure's intended state lives in text files that can be reviewed, diffed, and reproduced, not in the accumulated memory of whoever happened to SSH into the box and change something.

This distinction matters specifically for Linux fleets, not just as an abstract best practice:

- **Repeatability across many hosts.** The same declarative definition can be applied to produce ten identical hosts as easily as one — there's no "the first server was set up carefully and the other nine were cloned from it and slowly diverged" problem.
- **Auditability via git history.** A change to infrastructure is a commit, with an author, a timestamp, and (ideally) a reviewed pull request — a fundamentally different audit trail than trying to reconstruct what a manual SSH session did from shell history or memory.
- **Eliminating undocumented drift.** The single most common failure mode IaC directly targets is the classic "it works on this one server because someone SSHed in and fixed it by hand, six months ago, and nobody wrote it down." That fix lives only on that one host, isn't applied anywhere else, and isn't reproducible if that host is rebuilt — IaC makes the fix a file change instead, applied everywhere the definition is applied.

> 💡 **Tip:** The test for whether something is genuinely "as code" isn't just "is it in a file" — a shell script full of one-off `ssh host "some command"` invocations is still fundamentally imperative and manually triggered. The real shift is toward **declarative** definitions (describing the desired end state) applied by a tool that knows how to reconcile actual state with that description — §98 goes deep on exactly why that distinction matters.

## 2. Two Layers, Often Confused: Provisioning vs. Configuration

IaC tooling is commonly split across two distinct layers, and conflating them is the single most common point of confusion for anyone new to this space.

**Terraform's role: provisioning.** Terraform's job is creating the Linux host itself — the VM or cloud instance, its networking, its attached storage, its security groups/firewall rules — along with whatever other cloud resources (load balancers, DNS records, managed databases) surround it. Terraform answers the question **"does this machine exist, with these attributes, in this environment?"** It is provider-agnostic at a conceptual level — the same declarative model applies whether the target is AWS, Azure, GCP, or on-premises virtualization — and it does not, by itself, know or care what software ends up installed inside the Linux host it just created.

**Ansible's role: configuration.** Once a Linux host exists — whether Terraform just created it or it's an existing host being brought under management — Ansible's job is making sure that host is configured correctly: packages installed, configuration files written, services enabled and running. Ansible answers the question **"is this machine configured correctly?"**, a question that only makes sense once the machine already exists. Ansible is **agentless**, meaning it doesn't require a persistent daemon running on every managed host — it connects over plain SSH (§56's SSH architecture is exactly the transport Ansible rides on) and executes tasks through that existing, already-hardened connection, rather than requiring a separate agent-installation step and its own attack surface.

| Layer         | Tool (commonly) | Question answered                            | Operates on                        |
| ------------- | --------------- | -------------------------------------------- | ---------------------------------- |
| Provisioning  | Terraform       | Does this machine (and its resources) exist? | Cloud/virtualization APIs          |
| Configuration | Ansible         | Is this machine configured correctly?        | An already-existing host, over SSH |

## 3. Why Real Pipelines Commonly Use Both, Together

Because these are genuinely different layers rather than competing tools solving the same problem, real-world pipelines very commonly use both in sequence: Terraform provisions the host (and whatever networking/security-group resources it needs), and once that host exists and is reachable, Ansible takes over to install packages, deploy configuration, and start services on it. Terraform's output — the new host's IP address or hostname — commonly feeds directly into Ansible's inventory (the list of hosts Ansible will target), making the handoff between the two tools a natural, scriptable pipeline step rather than a manual one.

Treating this as an either/or choice is a common mistake: Terraform is a poor fit for expressing "install these six packages and template this config file" — it can technically execute arbitrary provisioning-time scripts, but that pushes it into the imperative, non-idempotent territory §98 covers, back toward the very "runs a script once at boot and hopes it stays correct" problem IaC exists to avoid. Ansible, conversely, has no concept of a cloud provider's API for creating a VM in the first place — it needs a host to already exist and be SSH-reachable before it can do anything. The two are complementary layers of the same overall pipeline, not overlapping alternatives.

## 4. A Conceptual Example: An Ansible Playbook Targeting a Linux Host

The following is conceptual, not complete working code — it's meant to connect an Ansible **playbook** (a declarative file describing desired configuration) to commands the reader already has from earlier Parts of this roadmap.

```yaml
# Conceptual structure only — not a complete, runnable playbook.
- hosts: webservers # a group of Linux hosts from Ansible's inventory
  become: true # run tasks with elevated privilege (sudo, §31)
  tasks:
    - name: Ensure nginx is installed
      package:
        name: nginx
        state: present # declarative — "should be installed," not "run apt install"

    - name: Ensure nginx service is running and enabled
      service:
        name: nginx
        state: started
        enabled: true
```

Notice what this maps back onto from earlier Parts: the `package` task is a declarative wrapper around exactly the package-manager operations §59–§64 covered directly (`apt install`/`dnf install` and their dependency-resolution machinery underneath) — Ansible doesn't reinvent package installation, it calls into the same underlying tooling, just idempotently (§98) rather than imperatively. The `service` task is a declarative wrapper around exactly the `systemctl start`/`systemctl enable` operations §66 (Part 9) covered directly. Ansible's value here isn't a new mechanism for installing software or managing services — it's a declarative, repeatable, auditable layer on top of the same commands the reader already knows how to run by hand on a single host.

> ⚠️ **Warning:** A playbook that "runs a package-manager install command" and one that declares "this package should be present" look similar on the surface but behave very differently on a second run — the former can error or produce different output depending on what already happened, while the latter checks current state first and changes nothing if the desired state already holds. §98 is dedicated entirely to this distinction, because it's the property that makes tools like Ansible safe to run repeatedly against a fleet rather than only once at initial setup.

## 5. Common Misconceptions

1. **"Terraform and Ansible do the same job, just with different syntax."** They operate at genuinely different layers — Terraform answers "does this machine exist," Ansible answers "is this machine configured correctly." A real pipeline commonly needs both, in sequence, not one instead of the other (2, 3).
2. **"Ansible needs an agent installed on every host, like some other configuration management tools."** Ansible is agentless — it connects over plain SSH using credentials/keys already set up per §56, executing tasks through that connection rather than requiring a persistent daemon and a separate agent-installation step (2).
3. **"IaC just means 'my setup script is in a git repo.'"** Being version-controlled is necessary but not sufficient — an imperative script full of one-off commands still suffers from the same "worked the first time, unpredictable the second time" problems IaC's declarative model exists to solve (1, and fully explored in §98).

## 6. Tiered Interview Questions

**🎯 Beginner:** _"In one sentence each, what does Terraform do and what does Ansible do?"_
**Model answer:** Terraform provisions infrastructure — it creates the Linux host itself along with its surrounding cloud resources like networking and storage. Ansible configures infrastructure — once a host exists, it installs packages, writes configuration, and manages services on it, connecting agentlessly over SSH.
_What the interviewer is probing for:_ A clean, correct one-line distinction between the two layers, not a vague "they're both DevOps tools."

**🎯 Intermediate:** _"Why is Ansible described as 'agentless,' and why does that matter operationally?"_
**Model answer:** Ansible doesn't require installing and running a persistent daemon on every managed host — it connects over standard SSH, the same transport and credential model §56 covers, and executes tasks through that connection. Operationally this matters because there's no separate agent software to install, patch, or secure on every host, and no additional listening service representing extra attack surface — the security boundary is the same SSH access control the fleet already has to manage carefully anyway.
_What the interviewer is probing for:_ Understanding agentless as a genuine architectural property with real operational and security implications, not just a marketing term.

**🎯 Senior:** _"A team wants to use Terraform to also install and configure software on the Linux VMs it provisions, avoiding Ansible entirely. What's your concern?"_
**Model answer:** Terraform can technically run provisioning-time scripts against a newly created host, but that pushes configuration into imperative, one-shot script territory — exactly the pattern IaC and configuration-management tools exist to move away from. It typically only runs once, at creation time, with no built-in mechanism to detect and correct drift afterward, and no clean idempotent re-application if the script needs to run again against an already-configured host. I'd push back toward keeping provisioning (Terraform) and configuration (Ansible or equivalent) as separate concerns, with Terraform's output feeding an Ansible inventory — that keeps each tool doing what it's actually good at, and keeps ongoing configuration re-appliable and driftresistant rather than a fragile one-time script.
_What the interviewer is probing for:_ Recognizing that blurring the provisioning/configuration boundary reintroduces exactly the problems IaC is meant to solve, and being able to articulate why, not just assert a tool preference.

**🎯 Architect:** _"How would you design the handoff between Terraform and Ansible for a fleet that scales up and down regularly?"_
**Model answer:** I'd have Terraform's output (new hosts' IPs or DNS names, tagged appropriately) feed directly into Ansible's dynamic inventory rather than a manually maintained static host list, so newly provisioned hosts are automatically in scope for configuration without a manual step. I'd keep the two tools' state cleanly separated — Terraform's state tracks what infrastructure exists, Ansible has no independent notion of "state" beyond what it can observe live on each host each run — and I'd make sure Ansible's playbooks are genuinely idempotent (§98) so that scaling events, which mean new hosts are configured for the first time while existing hosts might be re-converged on the same run, don't produce different behavior depending on which case a given host falls into. I'd also treat both the Terraform configuration and the Ansible playbooks as version-controlled artifacts reviewed through the same pull-request process, so infrastructure changes and configuration changes get the same audit trail (1) rather than one being disciplined and the other left informal.
_What the interviewer is probing for:_ Designing a real, scalable pipeline rather than describing the two tools in isolation, and correctly identifying idempotency as the property that makes the pipeline safe under repeated, variable-scale execution.

## 7. Key Takeaways

- Infrastructure as Code means defining infrastructure in version-controlled, declarative files rather than manual or one-off imperative commands — enabling repeatability, git-based auditability, and eliminating undocumented manual drift (1).
- Terraform provisions — it answers "does this machine exist" — while Ansible configures — it answers "is this machine configured correctly" — and these are genuinely different layers, not competing tools for the same job (2).
- Ansible is agentless, connecting over the same SSH transport and credential model covered in §56, rather than requiring a persistent daemon on every managed host (2).
- Real pipelines commonly chain the two: Terraform provisions a host and feeds its output into Ansible's inventory, which then configures it — treating provisioning and configuration as an either/or choice reintroduces the problems IaC exists to solve (3, 4).
- Ansible's declarative modules (`package`, `service`) are idempotent wrappers around the same underlying package-manager and `systemctl` operations covered directly in §59–§64 and §66 — not a new mechanism, but a repeatable, auditable layer on top of it (4).

## 8. Related Concepts & What's Next

This section connects directly to §56 (SSH, the transport Ansible rides on), §59–§64 (package management, Part 8, which Ansible's `package` module wraps), and §66 (systemctl, Part 9, which Ansible's `service` module wraps). §98, next, goes deeper on the concept this section only introduced by name — idempotency and desired state — which is the property that makes tools like Ansible safe to run repeatedly rather than only once.

**Next Section:** §98 — `Section-98-Part13-Configuration-Management-Concepts-Idempotency.md`
