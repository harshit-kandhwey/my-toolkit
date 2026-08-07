# Section 21 (Part 3): Firewall Rules

## 1. Definition

**Plain language:** Firewall rules are the traffic cops of a VPC network — they decide, for every packet, whether it's allowed in or out, based on where it's from, where it's going, and what protocol/port it's using. GCP layers this decision at both the network level (per-VPC firewall rules) and, for large organizations, at the org/folder level (hierarchical firewall policies) so central security teams can enforce guardrails no project owner can override.

**Precise:** **VPC firewall rules** are stateful, distributed rules evaluated at the virtual network interface of every VM (not at a central appliance), attached to a VPC network, that allow or deny traffic based on direction, protocol, port, and source/destination, matched against IP ranges, **network tags**, or **service accounts**. **Hierarchical firewall policies** are an additional, higher-priority layer of rules attached to an Organization or Folder node in the resource hierarchy ([Section 3](../Part1/Section-03-Part1-Resource-Hierarchy.md)), enforced centrally and evaluated before or after project-level VPC firewall rules depending on configuration.

## 2. Why It Exists / Problem It Solves

Without firewalling, every resource on a network would be reachable by every other resource, and the network would be reachable from the internet by default — an unacceptable security posture. GCP firewall rules solve this at the VPC level for day-to-day application-level segmentation (e.g., "only the web tier can reach the app tier on port 8080").

Hierarchical firewall policies solve a distinct enterprise problem: a central security team needs to guarantee certain rules (e.g., "no SSH from the public internet, ever, anywhere in the company") are enforced across every project in every folder, **regardless of what any individual project owner configures** at the VPC level. Without a hierarchical layer, enforcing an organization-wide guardrail would require auditing every project's firewall rules individually — impractical at scale and prone to drift.

## 3. Core Concepts

### 3.1 Implied Rules

Every VPC network has two **implied rules** that always exist, cannot be deleted, and sit at the lowest possible priority (65535) so any explicit rule overrides them:

- **Implied allow egress:** All outbound traffic to any destination is allowed by default.
- **Implied deny ingress:** All inbound traffic from any source is denied by default.

This means a brand-new custom-mode VPC ([Section 19](./Section-19-Part3-VPC-Fundamentals.md)) is "closed" to the outside world for inbound traffic until you explicitly add an allow rule — the opposite of the permissive `default` network's pre-populated rules.

### 3.2 Rule Components

Each VPC firewall rule is defined by:

| Field                                   | Meaning                                                                                                                                                    |
| --------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Direction                               | `INGRESS` (inbound) or `EGRESS` (outbound)                                                                                                                 |
| Priority                                | 0–65535, lower number = evaluated first / higher precedence                                                                                                |
| Action                                  | `ALLOW` or `DENY`                                                                                                                                          |
| Target                                  | Which VMs the rule applies to: all instances in the VPC, instances with a matching **network tag**, or instances running as a matching **service account** |
| Source (ingress) / Destination (egress) | IP ranges, or another network tag/service account                                                                                                          |
| Protocol and port                       | e.g., `tcp:443`, `tcp:22`, `all`                                                                                                                           |

Rules are **stateful**: an allowed inbound connection's return traffic is automatically allowed outbound (and vice versa) without needing a matching rule in the opposite direction — closer to AWS Security Groups than to NACLs in this respect.

### 3.3 Tags vs Service Accounts as Targets

GCP firewall rules can target VMs in two ways instead of listing individual instance names:

- **Network tags:** Simple string labels attached to VM instances (e.g., `web-server`, `app-tier`). A rule targeting tag `app-tier` applies to any VM carrying that tag, however it was created. Tags are easy to use but are just strings — anyone with permission to edit a VM's metadata/tags can add or remove them, so tags alone provide weak assurance in high-security environments.
- **Service accounts:** A rule can instead target VMs running as a specific **service account** identity ([Section 36](../Part5/Section-36-Part5-Service-Accounts.md)). Because a VM's service account is tied to its IAM identity and is harder to casually change than a tag, service-account-based targeting is the **recommended enterprise practice** for firewall rules that gate access to sensitive tiers — it ties network access directly to a controlled IAM identity rather than a freely editable label.

> 💡 **Tip:** In modern GCP deployments, prefer service-account-based firewall targeting over tag-based targeting wherever the target VMs' identity is already governed by IAM — it collapses "who can reach this" and "who is allowed to be this" into one controlled identity.

### 3.4 Hierarchical Firewall Policies

A **hierarchical firewall policy** is created and attached at the Organization or Folder level (not a Project or VPC), containing rules evaluated across every VPC network in every project beneath that node. Key properties:

- Rules can be marked with an explicit **priority** and, critically, a rule can be a **"go to next"** rule (delegating evaluation down to lower levels) or a rule that **cannot be overridden** by any lower-level VPC firewall rule, giving central security teams a true guardrail rather than a suggestion.
- Evaluation order: Organization-level hierarchical rules → Folder-level hierarchical rules (walking down the hierarchy toward the project) → Project-level VPC firewall rules → implied rules — with an explicit non-overridable Organization rule always winning regardless of what's configured below it.
- Typical enterprise use: a mandatory Organization-level rule denying ingress from `0.0.0.0/0` on ports 22/3389 network-wide, that no individual project team can override even if they add a permissive VPC-level rule.

## 4. Comparison: GCP Firewall Rules vs AWS Security Groups/NACLs vs Azure NSGs

| Aspect                       | GCP Firewall Rules                                  | AWS Security Groups                                        | AWS NACLs                                            | Azure NSGs                                                 |
| ---------------------------- | --------------------------------------------------- | ---------------------------------------------------------- | ---------------------------------------------------- | ---------------------------------------------------------- |
| Statefulness                 | Stateful                                            | Stateful                                                   | Stateless                                            | Stateful                                                   |
| Allow/Deny                   | Both allow and deny rules                           | Allow-only                                                 | Both allow and deny                                  | Both allow and deny                                        |
| Attachment point             | VPC network (applies via tag/service account match) | ENI / instance                                             | Subnet                                               | NIC / Subnet                                               |
| Central org-wide enforcement | Hierarchical firewall policies (Org/Folder)         | No native equivalent (requires AWS Firewall Manager)       | No native equivalent (requires AWS Firewall Manager) | Azure Firewall Policy / Azure Policy (separate constructs) |
| Default posture              | Implied deny-ingress, allow-egress                  | Deny all inbound by default, allow all outbound by default | Allow all by default (until customized)              | Deny inbound from internet by default, allow VNet-internal |

## 5. Hands-On Examples

**Beginner — create a firewall rule allowing internal traffic from a tag:**

```bash
gcloud compute firewall-rules create allow-internal-app \
  --network=prod-vpc \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:8080 \
  --source-tags=web-tier \
  --target-tags=app-tier \
  --priority=1000
```

_Purpose:_ Allows only VMs tagged `web-tier` to reach VMs tagged `app-tier` on port 8080, denying all other inbound sources by the network's implied deny rule.

**Expected output:**

```
Creating firewall...done.
NAME                 NETWORK    DIRECTION  PRIORITY  ALLOW      DENY  SOURCE_TAGS  TARGET_TAGS
allow-internal-app   prod-vpc   INGRESS    1000      tcp:8080         web-tier     app-tier
```

**Intermediate — create a firewall rule scoped to a service account instead of a tag:**

```bash
gcloud compute firewall-rules create allow-app-to-db \
  --network=prod-vpc \
  --direction=INGRESS \
  --action=ALLOW \
  --rules=tcp:5432 \
  --source-service-accounts=app-tier-sa@my-project.iam.gserviceaccount.com \
  --target-service-accounts=db-tier-sa@my-project.iam.gserviceaccount.com
```

_Purpose:_ Ties access to the database tier's port 5432 directly to the app tier's IAM service account identity rather than an editable tag — the recommended pattern for sensitive tiers.

## 6. Production & Enterprise Usage

- **Deny-by-default posture, explicit allow rules:** Production VPCs rely on the implied deny-ingress rule and add narrowly scoped allow rules per tier, rather than adding broad allow rules and trying to deny specific exceptions.
- **Hierarchical policies as non-negotiable guardrails:** Security teams enforce non-overridable Organization-level rules for the highest-risk exposures (public SSH/RDP, unrestricted `0.0.0.0/0` ingress) so no individual project can accidentally (or intentionally) create a critical exposure.
- **Service-account targeting for tiered architectures:** Multi-tier applications (web/app/database) commonly use one service account per tier and firewall rules keyed to those service accounts, so network access policy and IAM identity stay in lock-step as the architecture evolves.
- **Firewall Insights** ([Section 27](./Section-27-Part3-Network-Intelligence-Center-Traffic-Director.md)) is used in production to detect overly permissive or entirely unused firewall rules — an ongoing hygiene practice, not a one-time setup task.

## 7. Common Misconceptions

- **Misconception:** "GCP firewall rules behave like AWS NACLs because they support both allow and deny." GCP firewall rules are stateful (like AWS Security Groups) even though, unlike Security Groups, they also support explicit deny rules — it's a hybrid model, not a direct analog of either AWS construct.
- **Misconception:** "Tags are a secure way to gate access to sensitive resources." Tags are simple metadata strings anyone with VM-edit permission can change; only service-account-based targeting ties firewall access to a governed IAM identity.

## 8. Interview Questions

**🎯 Beginner:** _What are the two implied firewall rules every GCP VPC network has, and what do they do?_
**Model answer:** Every VPC has an implied allow-egress rule (all outbound traffic permitted by default) and an implied deny-ingress rule (all inbound traffic denied by default), both at the lowest possible priority so any explicit rule overrides them. This means a fresh custom-mode VPC is closed to inbound traffic until you add explicit allow rules.

**🎯 Intermediate:** _Why would you target a firewall rule using a service account instead of a network tag?_
**Model answer:** A network tag is just a string attached to VM metadata that anyone with edit permission on the VM can add or remove, making it a weak basis for high-security access control. A service account is a governed IAM identity — targeting firewall rules by service account ties network reachability directly to that IAM identity, so access control and identity management stay consistent, and it's much harder to accidentally or maliciously reassign.

**🎯 Senior/Architect:** _A large enterprise with hundreds of GCP projects across multiple business units needs to guarantee that no project can ever expose SSH/RDP to the public internet, while still letting individual teams manage their own application-level firewall rules. Design the approach._
**Model answer:** I'd create a hierarchical firewall policy attached at the Organization node, containing a high-priority, non-overridable deny rule for ingress from `0.0.0.0/0` on ports 22 and 3389, evaluated before any project-level VPC firewall rule and impossible for a project team to override even if they add a conflicting allow rule at the VPC level. Below that, I'd let each business unit's Folder optionally add its own hierarchical rules for folder-specific guardrails, and leave application-level segmentation (web-to-app, app-to-db) to project teams via ordinary VPC firewall rules, ideally targeted by service account rather than tag for the sensitive tiers. I'd pair this with Firewall Insights ([Section 27](./Section-27-Part3-Network-Intelligence-Center-Traffic-Director.md)) and a periodic audit process to catch drift or newly-added risky rules that fall outside the hierarchical guardrail's scope (e.g., risky ports other than 22/3389).

## 9. Key Takeaways

- 🔑 Every VPC has implied allow-egress and deny-ingress rules at the lowest priority; explicit rules override them.
- 🔑 GCP firewall rules are stateful and support both allow and deny — a hybrid of AWS Security Group statefulness and NACL bidirectional action support.
- 🔑 Prefer service-account-based targeting over tag-based targeting for firewall rules gating sensitive tiers — it ties network access to a governed IAM identity.
- 🔑 Hierarchical firewall policies at the Organization/Folder level let central security teams enforce non-overridable guardrails across every project, closing a gap VPC-level rules alone cannot close.

## 10. Related Concepts

VPC fundamentals ([Section 19](./Section-19-Part3-VPC-Fundamentals.md)), service accounts as IAM identities ([Section 36](../Part5/Section-36-Part5-Service-Accounts.md)), Organization Policy and governance ([Section 37](../Part5/Section-37-Part5-Organization-Policies.md)), and Firewall Insights for auditing rule hygiene ([Section 27](./Section-27-Part3-Network-Intelligence-Center-Traffic-Director.md)) all build directly on the firewall model introduced here.
