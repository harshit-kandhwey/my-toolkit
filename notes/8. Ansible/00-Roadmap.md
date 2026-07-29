# 00 — Roadmap: Ansible (Complete Topic Roadmap)

## 0. Assumption Line

Ansible is treated in its most common **DevOps / Cloud / Infrastructure Automation / SRE** interpretation: Ansible as an agentless configuration-management, application-deployment, and orchestration tool (inventories, modules, playbooks, roles, collections, Vault, and Tower/AWX/Automation Platform), covering everything from first principles through enterprise CI/CD integration and multi-cloud dynamic inventory — with explicit, direct coverage of the **EX294 (Red Hat Certified Specialist in Ansible Automation)** exam curriculum. This roadmap runs **119 sections across 19 parts**, sized to the same standard of depth as this repo's other tracks (comparable to GCP's 85, Azure's 100, and Linux's 125 sections) rather than a shallow tool overview.

Because Ansible touches networking devices, Windows, cloud provisioning, and enterprise automation platforms in addition to core Linux configuration management, this project is split into **named Parts**, generated sequentially. Do not ask which part to start with — Part 1 begins immediately after this roadmap.

---

## 1. Complete Numbered Roadmap

### Part 1 — Foundations and Architecture

1.1 What Ansible Is; the Agentless Automation Model
1.2 History: Ansible → Ansible Tower → AWX → Red Hat Ansible Automation Platform (AAP)
1.3 Architecture Overview: Control Node, Managed Nodes, Inventory, Modules, Plugins
1.4 Push vs. Pull Model; Ansible vs. Puppet/Chef/Salt/Terraform — Positioning
1.5 Installation and Setup (pip, OS packages, ansible-core vs. the community `ansible` package)
1.6 Prerequisites Recap (SSH, Python, YAML, Linux fundamentals)
1.7 EX294 Certification Landscape and How This Roadmap Maps to It

### Part 2 — Inventory and Configuration

2.1 Static Inventory Files: INI and YAML Formats
2.2 Dynamic Inventory Scripts and Plugins (aws_ec2, azure_rm, gcp_compute overview)
2.3 Host and Group Variables (host_vars, group_vars directories)
2.4 Inventory Patterns and Host-Selection Syntax
2.5 ansible.cfg: Configuration Precedence and Key Settings
2.6 Connection Methods: SSH, WinRM, local, Paramiko
2.7 Privilege Escalation: become, become_user, become_method

### Part 3 — Ad-Hoc Commands and Core Modules

3.1 Ad-Hoc Command Syntax and Real-World Use Cases
3.2 command vs. shell vs. raw Modules — When Each Applies
3.3 File and Content Modules: file, copy, template, fetch
3.4 Package Management Modules: yum/dnf/apt/package
3.5 Service Management Modules: service, systemd
3.6 User and Group Management Modules
3.7 Module Idempotency Patterns and Why They Matter
3.8 Module Documentation: ansible-doc and Reading Module Specs

### Part 4 — Playbooks Fundamentals

4.1 Playbook Structure: Plays, Tasks, and Hosts
4.2 YAML Syntax for Ansible (deep dive, common gotchas)
4.3 Tasks, Modules, and Task-Naming Best Practices
4.4 Variables: Definition and the Full Precedence Order
4.5 Facts: gather_facts, the setup Module, and Custom Facts
4.6 Conditionals: when Statements
4.7 Loops: loop, with_items, with_dict, loop_control
4.8 Handlers and notify
4.9 Tags: Selective Playbook Execution

### Part 5 — Templating and Jinja2

5.1 Jinja2 Templating Fundamentals in Ansible
5.2 Filters: Built-In Filters and Common Patterns
5.3 Tests and Conditionals Within Jinja2 Expressions
5.4 The template Module Deep Dive
5.5 Lookups: file, env, password, pipe
5.6 Vars Files and Their Interplay With Template Rendering
5.7 Advanced Jinja2: Macros and Custom Filter Plugins

### Part 6 — Roles

6.1 Role Directory Structure and Conventions
6.2 Creating Roles: ansible-galaxy init
6.3 Role Dependencies (meta/main.yml)
6.4 Role Variables, Defaults, and Precedence
6.5 Ansible Galaxy: Finding and Consuming Community Roles
6.6 Publishing Roles to Galaxy / Automation Hub
6.7 Role Design Best Practices and Anti-Patterns

### Part 7 — Collections and Content Distribution

7.1 What Collections Are and Why They Replaced Standalone Roles as the Distribution Unit
7.2 Collection Directory Structure (galaxy.yml, plugins/, roles/)
7.3 Installing and Managing Collections (ansible-galaxy collection install)
7.4 requirements.yml for Roles and Collections Together
7.5 Building and Publishing a Custom Collection
7.6 Key Certified Content Collections (ansible.posix, community.general, ansible.windows)

### Part 8 — Advanced Playbook Features

8.1 Blocks: rescue and always (Structured Error Handling)
8.2 Error Handling: ignore_errors, failed_when, changed_when
8.3 Delegation: delegate_to, run_once, local_action
8.4 Async and Polling for Long-Running Tasks
8.5 Execution Strategies: linear vs. free vs. host_pinned
8.6 Serial and Rolling-Update Batch Execution
8.7 Includes vs. Imports: include_tasks vs. import_tasks (Dynamic vs. Static)
8.8 Playbook Reuse Patterns: include_playbook vs. import_playbook

### Part 9 — Vault and Secrets Management

9.1 Ansible Vault Fundamentals: Encrypting Files and Variables
9.2 Vault Password Management (vault-id, password files, password scripts)
9.3 Encrypting Single Strings vs. Whole Files
9.4 Vault in CI/CD Pipelines
9.5 Integrating External Secrets (HashiCorp Vault Lookup Plugin)
9.6 Secrets Management Best Practices and Common Pitfalls

### Part 10 — Networking Automation

10.1 Network Modules Overview (ios, eos, junos, nxos Families)
10.2 Network Device Connection Methods: network_cli, netconf, httpapi
10.3 Idempotent Network Configuration Patterns
10.4 Gathering Network Facts
10.5 Network Automation Use Cases and Real-World Limitations

### Part 11 — Windows Automation

11.1 WinRM Setup and Configuration
11.2 Windows Modules Overview (win_* and the ansible.windows Collection)
11.3 PowerShell Integration: win_shell and win_command
11.4 Windows-Specific Playbook Patterns
11.5 Cross-Platform Playbook Design (Linux and Windows in One Play)

### Part 12 — Testing and Quality

12.1 ansible-lint: Rule Categories and CI Integration
12.2 Molecule: the Role Testing Framework
12.3 Writing Molecule Test Scenarios
12.4 --check Mode and --diff for Dry Runs
12.5 Syntax Checking: ansible-playbook --syntax-check
12.6 Idempotency Testing Strategies

### Part 13 — Ansible Tower / AWX / Automation Platform

13.1 AWX vs. Ansible Tower vs. Red Hat Ansible Automation Platform (AAP) — How They Relate
13.2 Job Templates and Workflow Templates
13.3 Inventories, Credentials, and Projects in Tower/AWX
13.4 RBAC in Tower/AWX: Organizations, Teams, Permissions
13.5 Execution Environments (Containerized Automation)
13.6 Scheduling and Notifications
13.7 REST API and Automation Controller Integration

### Part 14 — Dynamic and Cloud Inventory Deep Dive

14.1 AWS Dynamic Inventory (aws_ec2 Plugin) Deep Dive
14.2 Azure Dynamic Inventory (azure_rm Plugin) Deep Dive
14.3 GCP Dynamic Inventory (gcp_compute Plugin) Deep Dive
14.4 Multi-Cloud Inventory Aggregation Patterns
14.5 Cloud Provisioning Modules (ec2_instance, azure_rm_virtualmachine, gcp_compute_instance)

### Part 15 — Security and Compliance Automation

15.1 Ansible for CIS Benchmark Remediation
15.2 Ansible for Patch Management at Scale
15.3 Compliance-as-Code Patterns
15.4 Integrating Ansible With Security Scanning Tools
15.5 Least-Privilege Execution Patterns for Automation Runs

### Part 16 — Enterprise Patterns and CI/CD Integration

16.1 GitOps for Ansible: Playbooks Under Version Control
16.2 CI/CD Pipeline Integration (Jenkins, GitLab CI, GitHub Actions Running ansible-playbook)
16.3 Multi-Environment Strategies (dev/staging/prod Inventories)
16.4 Ansible + Terraform Division of Labor in Idempotent Infrastructure Patterns
16.5 Scaling Ansible: Performance Tuning (forks, pipelining, fact caching)
16.6 Enterprise Change Management and Approval Workflows

### Part 17 — Troubleshooting

17.1 Common Playbook Errors and Debugging Techniques
17.2 Verbose Modes (-v through -vvvv) and the debug Module
17.3 Connection Troubleshooting (SSH Failures, WinRM Failures)
17.4 Fact-Gathering Failures and Timeout Issues
17.5 Debugging Templates and Variable-Resolution Issues
17.6 Incident Case Studies and Runbooks

### Part 18 — Interview and Exam Preparation (EX294)

18.1 EX294 Exam Domain Breakdown and Time-Management Strategy
18.2 Common EX294-Style Scenario Tasks (Worked Through Step by Step)
18.3 Ansible CLI Speed Techniques for Exam Conditions
18.4 General Ansible Interview Question Bank (Beginner to Architect)
18.5 Scenario-Based Automation Design Questions

### Part 19 — Wrap-Up

19.1 Progressive Hands-On Labs (beginner → production-style, exam-simulation labs)
19.2 Consolidated Key-Takeaways Checklist
19.3 Common Misconceptions and Anti-Patterns Recap
19.4 Related Technologies and Recommended Next Topics

---

## 2. Prerequisites

| Prerequisite                                  | Needed For     | Introduced                                        |
| ------------------------------------------------ | -------------- | ---------------------------------------------------- |
| Linux fundamentals (users, permissions, services) | Throughout      | Assumed baseline (see [[../2. Linux/00-Roadmap]])   |
| SSH key-based authentication                     | Part 2 onward  | Briefly recapped in 2.6                              |
| YAML syntax                                      | Part 4 onward  | Deep dive in 4.2                                     |
| Basic Python literacy (reading, not writing)     | Part 5, 7      | Assumed baseline (modules/filters are Python under the hood) |

No external topic must be studied before starting; this roadmap builds every Ansible-specific prerequisite in place, though Linux and SSH fundamentals are assumed baseline knowledge.

---

## 3. Learning Phases

| Phase                                  | Parts Covered   | Goal                                                   |
| ---------------------------------------- | --------------- | --------------------------------------------------------- |
| Phase 1 — Foundations                    | Part 1, 2       | Understand Ansible's model and configure inventory         |
| Phase 2 — Core Execution                 | Part 3, 4       | Ad-hoc commands and playbook fundamentals                   |
| Phase 3 — Reusability                    | Part 5, 6, 7    | Templating, roles, and collections                          |
| Phase 4 — Advanced Control Flow          | Part 8, 9       | Error handling, delegation, secrets management               |
| Phase 5 — Platform-Specific Automation   | Part 10, 11     | Network devices and Windows targets                          |
| Phase 6 — Quality and Scale              | Part 12, 13     | Testing, linting, Tower/AWX/AAP                               |
| Phase 7 — Cloud and Enterprise Operations | Part 14, 15, 16 | Dynamic cloud inventory, compliance, CI/CD integration        |
| Phase 8 — Operations                     | Part 17         | Troubleshooting methodology                                   |
| Phase 9 — Certification Readiness        | Part 18         | Full EX294 exam-style scenario bank                            |
| Phase 10 — Wrap-Up                       | Part 19         | Labs, checklists, next steps                                   |

---

## 4. Section-to-File Mapping

Each roadmap subsection (e.g., `1.1`, `4.5`) is authored as its own file, following the `Contents/PartN/Section-NN-PartN-Slug.md` convention shared with this repo's other knowledge bases (Linux, AWS, Azure, GCP, Kubernetes, GIT). Section numbers (`§`) are continuous across the entire 19-part roadmap (1–119), not reset per part.

| Part                                                  | Roadmap Range | Continuous § Range | Folder             |
| -------------------------------------------------------- | -------------- | ------------------- | ------------------- |
| Part 1 — Foundations and Architecture                     | 1.1–1.7        | §1–§7                | `Contents/Part1/`   |
| Part 2 — Inventory and Configuration                      | 2.1–2.7        | §8–§14               | `Contents/Part2/`   |
| Part 3 — Ad-Hoc Commands and Core Modules                 | 3.1–3.8        | §15–§22              | `Contents/Part3/`   |
| Part 4 — Playbooks Fundamentals                            | 4.1–4.9        | §23–§31              | `Contents/Part4/`   |
| Part 5 — Templating and Jinja2                             | 5.1–5.7        | §32–§38              | `Contents/Part5/`   |
| Part 6 — Roles                                             | 6.1–6.7        | §39–§45              | `Contents/Part6/`   |
| Part 7 — Collections and Content Distribution              | 7.1–7.6        | §46–§51              | `Contents/Part7/`   |
| Part 8 — Advanced Playbook Features                        | 8.1–8.8        | §52–§59              | `Contents/Part8/`   |
| Part 9 — Vault and Secrets Management                      | 9.1–9.6        | §60–§65              | `Contents/Part9/`   |
| Part 10 — Networking Automation                            | 10.1–10.5      | §66–§70              | `Contents/Part10/`  |
| Part 11 — Windows Automation                               | 11.1–11.5      | §71–§75              | `Contents/Part11/`  |
| Part 12 — Testing and Quality                              | 12.1–12.6      | §76–§81              | `Contents/Part12/`  |
| Part 13 — Ansible Tower / AWX / Automation Platform        | 13.1–13.7      | §82–§88              | `Contents/Part13/`  |
| Part 14 — Dynamic and Cloud Inventory Deep Dive           | 14.1–14.5      | §89–§93              | `Contents/Part14/`  |
| Part 15 — Security and Compliance Automation               | 15.1–15.5      | §94–§98              | `Contents/Part15/`  |
| Part 16 — Enterprise Patterns and CI/CD Integration        | 16.1–16.6      | §99–§104             | `Contents/Part16/`  |
| Part 17 — Troubleshooting                                  | 17.1–17.6      | §105–§110            | `Contents/Part17/`  |
| Part 18 — Interview and Exam Preparation (EX294)           | 18.1–18.5      | §111–§115            | `Contents/Part18/`  |
| Part 19 — Wrap-Up                                          | 19.1–19.4      | §116–§119            | `Contents/Part19/`  |

**Total: 119 sections across 19 parts.**

---

## 5. Certification Domain Mapping (EX294 — Red Hat Certified Specialist in Ansible Automation)

| Official EX294 Domain                                            | Covered By                              |
| -------------------------------------------------------------------- | ------------------------------------------ |
| Understand core components of Ansible (inventories, modules, variables, facts, plugins) | Part 1, Part 2, Part 4                     |
| Install and configure Ansible (control node setup, ansible.cfg)        | Part 1, Part 2                              |
| Configure Ansible managed nodes (SSH, become, WinRM)                   | Part 2                                      |
| Create Ansible plays and playbooks                                     | Part 3, Part 4                              |
| Automate standard system administration tasks using Ansible            | Part 3, Part 4                              |
| Manage variables and facts                                             | Part 4, Part 5                              |
| Manage inventories, static and dynamic                                 | Part 2, Part 14                             |
| Manage task control: loops, conditionals, handlers, tags               | Part 4, Part 8                              |
| Create and use templates to generate customized configuration files    | Part 5                                      |
| Work with roles and Ansible Content Collections                        | Part 6, Part 7                              |
| Manage transactions and reversal of playbooks (idempotency, error handling, --check, debugging) | Part 8, Part 12, Part 17                    |
| Manage and troubleshoot Ansible automation                             | Part 17                                     |
| Secure sensitive data with Ansible Vault                                | Part 9                                      |

Part 18 (§111–115) additionally provides dedicated exam-day strategy and a step-by-step scenario-task bank modeled on EX294's hands-on, task-based exam format (unlike CKA/CKAD/CKS, EX294 is not multiple-choice — it is graded entirely on working playbooks against live managed nodes, which Part 18 and Part 19's labs are built to simulate).

---

## 6. Cross-Topic Dependency Graph

```text
Foundations and Architecture (P1)
        │
        ▼
Inventory and Configuration (P2) ──────────────► Static/dynamic inventory, become, connections
        │
        ▼
Ad-Hoc Commands and Core Modules (P3)
        │
        ▼
Playbooks Fundamentals (P4) ──► Variables, facts, conditionals, loops, handlers
        │
        ├──► Templating and Jinja2 (P5)
        │
        ▼
Roles (P6) ──► Collections and Content Distribution (P7)
        │
        ▼
Advanced Playbook Features (P8) ──► Blocks, delegation, async, strategies
        │
        ▼
Vault and Secrets Management (P9)
        │
        ├──► Networking Automation (P10)
        ├──► Windows Automation (P11)
        │
        ▼
Testing and Quality (P12) ──► ansible-lint, Molecule
        │
        ▼
Ansible Tower / AWX / Automation Platform (P13)
        │
        ▼
Dynamic and Cloud Inventory Deep Dive (P14) ──► AWS/Azure/GCP dynamic inventory
        │
        ▼
Security and Compliance Automation (P15)
        │
        ▼
Enterprise Patterns and CI/CD Integration (P16) ──► GitOps, pipeline integration, Terraform division of labor
        │
        ▼
Troubleshooting (P17)
        │
        ▼
Interview and Exam Preparation: EX294 (P18)
        │
        ▼
Wrap-Up: Labs & Next Steps (P19) ──► Recommended next topics: Terraform, Kubernetes, CI/CD, Red Hat Ansible Automation Platform deep dive
```

**Recommended technologies to learn alongside or after Ansible:** Terraform (provisioning vs. Ansible's configuration-management role — see [[../7. Terraform]]), Kubernetes (see [[../12. Kubernetes/00-Roadmap]]), CI/CD pipelines (see [[../9. CI-CD]]), Git (already covered — see [[../1. GIT]]), cloud-provider fundamentals (see [[../6. Cloud]]).

---

## 7. Roadmap Expansion Backlog

_(Empty at project start. Populated when the user requests additions, gap coverage, or new parts.)_

| Item | Requested Reason / Gap | Placement | Status | Target Filename |
| ---- | ----------------------- | --------- | ------ | ----------------- |
| —    | —                       | —         | —      | —                  |

---

## 8. Current Roadmap State

| #   | Part                                                    | Section     | Status       |
| --- | ---------------------------------------------------------| ------------ | ------------ |
| 01  | Part 1 — Foundations and Architecture                     | 1.1–1.7      | ⏳ Remaining |
| 02  | Part 2 — Inventory and Configuration                      | 2.1–2.7      | ⏳ Remaining |
| 03  | Part 3 — Ad-Hoc Commands and Core Modules                 | 3.1–3.8      | ⏳ Remaining |
| 04  | Part 4 — Playbooks Fundamentals                           | 4.1–4.9      | ⏳ Remaining |
| 05  | Part 5 — Templating and Jinja2                            | 5.1–5.7      | ⏳ Remaining |
| 06  | Part 6 — Roles                                            | 6.1–6.7      | ⏳ Remaining |
| 07  | Part 7 — Collections and Content Distribution             | 7.1–7.6      | ⏳ Remaining |
| 08  | Part 8 — Advanced Playbook Features                       | 8.1–8.8      | ⏳ Remaining |
| 09  | Part 9 — Vault and Secrets Management                     | 9.1–9.6      | ⏳ Remaining |
| 10  | Part 10 — Networking Automation                           | 10.1–10.5    | ⏳ Remaining |
| 11  | Part 11 — Windows Automation                              | 11.1–11.5    | ⏳ Remaining |
| 12  | Part 12 — Testing and Quality                             | 12.1–12.6    | ⏳ Remaining |
| 13  | Part 13 — Ansible Tower / AWX / Automation Platform       | 13.1–13.7    | ⏳ Remaining |
| 14  | Part 14 — Dynamic and Cloud Inventory Deep Dive           | 14.1–14.5    | ⏳ Remaining |
| 15  | Part 15 — Security and Compliance Automation              | 15.1–15.5    | ⏳ Remaining |
| 16  | Part 16 — Enterprise Patterns and CI/CD Integration        | 16.1–16.6    | ⏳ Remaining |
| 17  | Part 17 — Troubleshooting                                  | 17.1–17.6    | ⏳ Remaining |
| 18  | Part 18 — Interview and Exam Preparation (EX294)          | 18.1–18.5    | ⏳ Remaining |
| 19  | Part 19 — Wrap-Up                                          | 19.1–19.4    | ⏳ Remaining |

**Next Section:** Part 1 — Foundations and Architecture (§1–§7)
