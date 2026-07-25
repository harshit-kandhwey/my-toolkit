# Section 3 (Part 1): Resource Hierarchy (Organization → Folder → Project → Resource)

## 3.1 Definition

**Plain language:** Every resource you create in GCP — a VM, a bucket, a database — has to live somewhere inside a nested structure of containers, similar to folders and subfolders on a hard drive. This structure exists so that permissions and policies set at a high level automatically apply to everything nested underneath it, instead of having to be configured resource-by-resource.

**Precise:** GCP's resource hierarchy is a four-level tree — **Organization → Folder → Project → Resource** — that provides the structural backbone for both **access control** (IAM policies) and **governance** (Organization Policies). Policies attached at any node are inherited by every node beneath it, and the effective policy on a given resource is the union of everything inherited from its ancestors plus anything set directly on it.

## 3.2 Why It Exists / Problem It Solves

Without a hierarchy, every project would be an island: an administrator would have to grant permissions and configure security guardrails individually on every single project, and there would be no way to enforce an organization-wide rule (e.g., "no one may create a publicly-readable Cloud Storage bucket") except by manually replicating that rule everywhere. At enterprise scale — with hundreds or thousands of projects across many teams — this becomes unmanageable and error-prone; a single missed project is a single security gap.

The resource hierarchy solves this by letting policy be set **once, at the right level**, and inherited automatically:

- A security team can enforce a guardrail at the Organization node, and it applies to every project created by every team, forever, with no per-project setup.
- A department can be given administrative rights over its own Folder without being granted any access to a sibling department's Folder.
- Billing, quota, and API enablement remain scoped to the Project level, so cost and blast radius stay contained to a well-understood unit even as governance is centralized above it.

## 3.3 The Four Levels

### 3.3.1 Organization

The **Organization** is the root node of the hierarchy, automatically created when a company uses a Google Workspace or Cloud Identity account to first interact with GCP. It represents the entire company. There is exactly one Organization node per company (in the typical case), and every Folder and Project a company creates can, and normally should, live underneath it.

- Without an Organization node (e.g., an individual using a personal Gmail account), projects have no common root and Organization Policies/company-wide IAM cannot be centrally enforced — this is why enterprises are strongly pushed to set up Cloud Identity/Workspace and an Organization node immediately.

### 3.3.2 Folder

A **Folder** is an optional grouping node beneath the Organization (or beneath another Folder — folders can nest). Folders exist purely to group Projects (or other Folders) for the purpose of applying shared IAM and Organization Policies, typically mirroring the company's structure: business units, departments, environments (`prod`/`nonprod`), or teams.

- Folders have no billing account, quota, or API-enablement semantics of their own — those all live at the Project level. A Folder is purely a policy/organizational container.
- Nesting is common: `Organization → Folder: "Engineering" → Folder: "Payments Team" → Project: "payments-prod-01"`.

### 3.3.3 Project

The **Project** is the fundamental unit of resource ownership, billing, quota, and API management in GCP — every resource (VM, bucket, database, etc.) belongs to exactly one Project. See Section 4 for a full treatment of projects, billing accounts, and quotas.

### 3.3.4 Resource

Individual services and objects — a Compute Engine VM, a Cloud Storage bucket, a BigQuery dataset — sit at the bottom of the hierarchy, each belonging to exactly one Project.

## 3.4 Policy Inheritance

### 3.4.1 IAM Policy Inheritance

IAM policies (who can do what — Section 35 covers IAM in full) can be attached at any node in the hierarchy. A policy attached at a higher node is inherited by every descendant node, and inherited permissions **cannot be revoked** at a lower level — GCP's IAM model only allows adding permissions as you descend, never subtracting them.

> ⚠️ **Interview-relevant nuance:** This is a frequently tested distinction versus AWS. An AWS SCP (Service Control Policy) is a _guardrail_ that sets the maximum permissions a principal can have — it can only restrict, never grant. A GCP IAM policy at the Organization/Folder level, by contrast, actively _grants_ permissions that flow down and cannot be stripped away lower in the tree. To restrict what an inherited IAM grant can do in GCP, you use a separate mechanism — Organization Policies (Section 3.4.2) or, for finer identity restriction, IAM Deny policies — rather than expecting a lower-level IAM binding to override a higher one.

### 3.4.2 Organization Policy Inheritance

**Organization Policies** (Section 37 covers these in depth) are a distinct mechanism from IAM: instead of granting permissions, they constrain _what actions are allowed at all_ within a scope, regardless of a principal's IAM permissions — e.g., "no VM may be created with a public IP address" or "resources may only be created in EU regions." Like IAM, Organization Policies attached at a higher node apply to all descendants by default, but unlike IAM, a lower node can override an inherited Organization Policy (subject to the policy's own configuration of whether overrides are allowed), making them the correct tool for enforcing hard guardrails that IAM inheritance cannot express.

## 3.5 Architecture Diagram

```
                              ORGANIZATION
                          "example.com" (root)
                                   │
              ┌────────────────────┼─────────────────────┐
              ▼                    ▼                     ▼
        FOLDER: "Prod"       FOLDER: "Nonprod"      FOLDER: "Shared-Services"
              │                    │                     │
      ┌───────┴───────┐            │                     ▼
      ▼               ▼            ▼               PROJECT: "net-hub-01"
 FOLDER:          PROJECT:    PROJECT:              (Shared VPC host project,
 "Payments"       "web-prod"  "web-dev"               Section 25)
      │
      ▼
 PROJECT: "payments-prod-01"
      │
   ┌──┴──────────────┐
   ▼                 ▼
Compute VM      Storage Bucket
(resource)        (resource)

IAM granted at Organization  ► inherited by every Folder/Project/Resource below.
Org Policy set at "Prod" Folder ► inherited by "Payments" Folder and its Projects,
                                   can be overridden lower down if the policy allows it.
```

## 3.6 Comparison with AWS and Azure

| Concept                                  | GCP                                                   | AWS                                                                 | Azure                                                         |
| ---------------------------------------- | ----------------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------- |
| Root node                                | Organization                                          | Organization (management account)                                   | Tenant (Microsoft Entra ID)                                   |
| Grouping layer                           | Folder (nestable)                                     | Organizational Unit / OU (nestable)                                 | Management Group (nestable)                                   |
| Base billable/isolation unit             | Project                                               | Account                                                             | Subscription                                                  |
| Guardrail mechanism                      | Organization Policy (constrains allowed actions)      | Service Control Policy / SCP (constrains max permissions)           | Azure Policy (constrains/audits configuration)                |
| Grants-flow-down mechanism               | IAM policy (adds permission, cannot be revoked below) | IAM policy (per-account; SCPs set ceiling, not grants)              | Azure RBAC (adds permission, inherits down Management Groups) |
| Can a lower node override the guardrail? | Yes, if the Organization Policy allows overrides      | No — SCPs are a hard ceiling, never overridable by a member account | Yes, if the Azure Policy assignment allows exemptions         |

## 3.7 Hands-On Example: Exploring the Hierarchy

**Purpose:** List the Folders directly under an Organization, and view a Project's ancestry (which Folders/Organization it sits beneath) — the exact query an auditor or new team member runs to understand where a project fits in the company's governance structure.

```bash
gcloud resource-manager folders list --organization=123456789012
```

**Expected output:**

```
DISPLAY_NAME          PARENT_NAME
Prod                  organizations/123456789012
Nonprod               organizations/123456789012
Shared-Services       organizations/123456789012
```

**Viewing a project's ancestry:**

```bash
gcloud projects get-ancestors payments-prod-01
```

**Expected output:**

```
ID              TYPE
payments-prod-01   project
987654321012       folder
123456789012       organization
```

> 💡 **Tip:** `get-ancestors` is the fastest way to answer "what IAM/Organization Policies could possibly be affecting this project?" during an access-troubleshooting session — the effective policy is always the union of everything on this list, top to bottom.

## 3.8 Production & Enterprise Usage

- **Folder design mirrors org structure or environment, not both loosely mixed.** Common enterprise patterns are either business-unit-first (`Folder: Payments → Folder: Prod/Nonprod`) or environment-first (`Folder: Prod → Folder: Payments/Marketing/...`) — mixing conventions inconsistently across the tree makes policy auditing much harder. This exact design decision is explored at scale in Section 59 (Landing Zone Architecture).
- **Security/platform teams typically hold IAM at the Organization or top Folder level** (e.g., organization-wide viewer access for a central security team via Section 39's Security Command Center), while application teams are delegated ownership of their own Folder/Projects without visibility into siblings.
- **Automation for folder/project creation at scale** (rather than manual console clicks) is standard in large organizations — covered fully in Section 63 (Folder/Project Vending Automation).

## 3.9 Common Misconceptions

- **Misconception:** "A Folder is required." Folders are optional — a small company can place Projects directly under the Organization with no Folders at all. Folders only add value once grouping for policy/delegation purposes is actually needed.
- **Misconception:** "IAM inheritance can be blocked at a lower level, the same way a firewall rule can be overridden." IAM grants inherited from above are permanent as they flow down the tree — they cannot be revoked at a Project or Folder below. Restricting behavior requires Organization Policies or IAM Deny policies, not "un-granting" an inherited IAM role.
- **Misconception:** "Billing is set at the Organization level." Billing accounts are linked to individual Projects (Section 4), not to Folders or the Organization directly, even though a single billing account is commonly linked to many projects across the hierarchy.

## 3.10 Interview Questions

**🎯 Beginner:** _What are the four levels of the GCP resource hierarchy, in order?_
**Model answer:** Organization at the top, then optional nested Folders, then Projects, then individual Resources (VMs, buckets, etc.) at the bottom. Every resource belongs to exactly one Project, and Projects can sit directly under the Organization or be nested inside one or more Folders.

**🎯 Intermediate:** _Can a Project override an IAM permission that was granted at the Organization level?_
**Model answer:** No. IAM grants flow downward through the hierarchy and are additive only — a permission granted at the Organization level is inherited by every Folder and Project beneath it and cannot be revoked at a lower level. If the goal is to restrict what an inherited grant can actually do (e.g., prevent public bucket creation even for someone with Storage Admin), the correct tool is an Organization Policy or an IAM Deny policy, not an attempt to override the IAM binding itself.

**🎯 Senior/Architect:** _A company has an "Engineering" business unit with 40 teams, each needing autonomy over their own projects, while the central security team needs to guarantee no team can ever disable audit logging or create public storage buckets. How would you design the Folder structure and policy placement?_
**Model answer:** I'd create a top-level Folder per major business unit (e.g., "Engineering"), with per-team sub-Folders beneath it, and delegate Project Creator/Owner-equivalent IAM roles at each team's sub-Folder so teams can self-serve project creation without touching siblings. For the hard guarantees — no disabling audit logging, no public buckets — I would not rely on IAM at all, since IAM only grants and any team with sufficiently broad roles could otherwise take those actions; instead I'd attach Organization Policies enforcing those constraints as high as possible, ideally at the Organization root, and explicitly configure them as non-overridable further down the tree so no team Folder or Project can loosen the constraint even if granted broad IAM roles. This combination — delegated IAM for velocity, non-overridable Organization Policy for the non-negotiable guardrails — is the standard landing zone pattern covered in depth in Section 59.

## 3.11 Key Takeaways

- 🔑 The hierarchy is Organization → Folder (optional, nestable) → Project → Resource; every resource belongs to exactly one Project.
- 🔑 IAM policies are additive and flow downward permanently — a lower node cannot revoke a higher node's grant.
- 🔑 Organization Policies constrain allowed actions regardless of IAM permissions, and — unlike IAM — can be configured to allow or disallow overrides lower in the tree.
- 🔑 Billing, quota, and API enablement are Project-level concerns, not Folder or Organization-level ones (Section 4).
- 🔑 GCP's Folder ≈ AWS's OU ≈ Azure's Management Group; GCP's Project ≈ AWS's Account ≈ Azure's Subscription, but the guardrail mechanisms (Organization Policy vs. SCP vs. Azure Policy) differ meaningfully in whether overrides are permitted.

## 3.12 Related Concepts

Projects, billing accounts, and quotas (Section 4), IAM fundamentals (Section 35), Organization Policies in depth (Section 37), landing zone architecture (Section 59), and folder/project vending automation (Section 63) all build directly on the hierarchy introduced here.
