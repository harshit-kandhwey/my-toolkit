# Section 35 (Part 5): IAM Fundamentals (Members, Roles, Policies)

## 35.1 Definition

**Plain language:** Identity and Access Management (IAM) is how GCP answers the question "who is allowed to do what, to which resource?" Every action in GCP — creating a VM, reading a bucket, deploying to GKE — is checked against an IAM policy before it's allowed to happen.

**Precise:** GCP IAM is a unified access-control system that binds **principals** (identities — users, groups, service accounts, or domains) to **roles** (named collections of permissions) on a specific **resource** in the hierarchy (Organization, Folder, Project, or individual resource). The resulting **IAM policy** is a set of **bindings**, each optionally scoped by a **condition**, and the effective access on any resource is the union of every policy inherited down the hierarchy plus anything bound directly on it.

## 35.2 Why It Exists

Without a centralized access model, every service would need to invent its own permission system, and administrators would have no consistent way to answer "does this person have access to this resource, and why?" IAM exists to provide one uniform mechanism — principals, roles, bindings — that every GCP service plugs into, so access can be reasoned about, audited, and governed consistently across VMs, storage, databases, and everything else, and so that access can be granted once at a high level in the resource hierarchy (Section 3) and inherited automatically rather than configured per-resource.

## 35.3 Core Concepts

### 35.3.1 Principals (Members)

A **principal** is "who" — the identity being granted access. GCP principal types:

- **Google Account** — an individual human user (`user:alice@example.com`).
- **Service account** — a non-human identity used by workloads/applications (`serviceAccount:app@project.iam.gserviceaccount.com`; covered fully in Section 36).
- **Google Group** — a collection of users/service accounts managed as one unit (`group:team-x@example.com`); the standard way to grant access to a team without binding individuals directly.
- **Google Workspace domain / Cloud Identity domain** — every user in an entire domain (`domain:example.com`); broad and rarely used for fine-grained access.
- **All authenticated users / allUsers** — the special, extremely broad principals meaning "anyone with a Google account" or "literally anyone on the internet," respectively. `allUsers` bindings on storage or APIs are a top security misconfiguration and are flagged by Security Command Center (Section 39).

### 35.3.2 Roles

A **role** is "what" — a named bundle of permissions (e.g., `storage.buckets.get`, `compute.instances.start`). GCP has three role categories:

| Role type             | Description                                                                                                                                                | Example                                                        |
| --------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------- |
| **Basic (primitive)** | Legacy, extremely broad roles predating fine-grained IAM: Owner, Editor, Viewer. Apply across every service in a project.                                  | `roles/owner`, `roles/editor`, `roles/viewer`                  |
| **Predefined**        | Curated, service-specific roles maintained by Google, scoped to a coherent set of tasks within one service. The recommended default for most access needs. | `roles/compute.instanceAdmin.v1`, `roles/storage.objectViewer` |
| **Custom**            | Organization- or project-defined roles built from an exact list of permissions, for when predefined roles are too broad or too narrow.                     | `projects/my-proj/roles/customLogReaderNoDelete`               |

> ⚠️ **Interview-relevant nuance:** Basic roles (`Owner`/`Editor`/`Viewer`) are almost never appropriate in production — `Editor` alone grants write access to nearly every resource type in a project, far beyond least privilege. Predefined roles are the default recommendation; custom roles are reserved for cases where no predefined role expresses the exact needed permission set.

### 35.3.3 IAM Policy and Bindings

An **IAM policy** is a JSON/YAML document attached to a resource, consisting of a list of **bindings**. Each binding maps one role to a list of principals, and can carry an optional **condition**:

```json
{
  "bindings": [
    {
      "role": "roles/storage.objectViewer",
      "members": ["group:data-analysts@example.com"]
    },
    {
      "role": "roles/storage.objectAdmin",
      "members": ["user:alice@example.com"],
      "condition": {
        "title": "expires_end_of_project",
        "expression": "request.time < timestamp('2026-12-31T00:00:00Z')"
      }
    }
  ]
}
```

### 35.3.4 IAM Conditions

**IAM Conditions** attach a Common Expression Language (CEL) expression to a binding, making the grant conditional on attributes like time, resource name/type, or (for some resources) request tags. This enables temporary access grants, resource-name-pattern restrictions, and other fine-grained scoping without needing a separate custom role for every variation.

### 35.3.5 Policy Inheritance

As introduced in Section 3, IAM bindings set at the Organization or Folder level are inherited by every Project and resource beneath them, and this inheritance is strictly additive — a lower-level policy can grant additional access but can never revoke an inherited grant. The effective policy on any resource is always the union of its own bindings plus every ancestor's bindings, evaluated top-down through Organization → Folder → Project → Resource.

### 35.3.6 IAM Deny Policies

Since inherited grants cannot be revoked, GCP separately offers **IAM Deny policies** — explicit deny rules that block specified permissions for specified principals regardless of any Allow binding, evaluated before Allow policies. This is the mechanism to use when a hard "never allow this, no matter what role someone is later granted" rule is needed (e.g., denying `iam.serviceAccountKeys.create` org-wide), complementing Organization Policies (Section 37), which restrict actions rather than principals.

## 35.4 Architecture Diagram

```
                         IAM POLICY EVALUATION (simplified)
                                       │
     ┌─────────────────────────────────┼─────────────────────────────────────┐
     │                                 │                                     │
  Org-level policy                Folder-level policy                    Project-level policy
roles/viewer ► group:all-eng    roles/editor ► group:payments-team     roles/storage.admin ► user:alice
     │                                  │                                    │
     └──────────────────┬───────────────┴───────────────┬────────────────────┘
                        ▼                               ▼
                 Effective policy on "payments-prod-01" Project
                 = union of all bindings above + any bound directly here
                          │
                          ▼
              IAM Deny policy checked FIRST (if any) ► blocks matching permissions
              regardless of the Allow union above
                          │
                          ▼
                 Final decision: ALLOW or DENY for the requested action
```

## 35.5 Comparison with AWS and Azure

| Concept                          | GCP                                               | AWS                                                                      | Azure                                                          |
| -------------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------------- |
| Core unit                        | IAM policy binding (role + members [+ condition]) | IAM policy document (JSON, attached to identity/resource)                | RBAC role assignment (role definition + principal + scope)     |
| Non-human identity               | Service account                                   | IAM Role (assumed via STS)                                               | Managed Identity / Service Principal                           |
| Broad legacy grants              | Basic roles (Owner/Editor/Viewer)                 | Not directly analogous (AWS never had a "project-wide Editor" primitive) | Classic Admin roles (largely deprecated)                       |
| Grants flow downward?            | Yes, additive, non-revocable below                | No native hierarchy grant-flow; SCPs restrict only                       | Yes, additive via Management Group/Subscription/RG inheritance |
| Restrict without touching grants | Organization Policy / IAM Deny policy             | Service Control Policy (SCP)                                             | Azure Policy                                                   |
| Conditional access on a binding  | IAM Conditions (CEL expression)                   | IAM policy `Condition` block                                             | Azure AD Conditional Access / ABAC (limited)                   |

## 35.6 Hands-On Example: Granting and Inspecting IAM Roles

**Purpose:** Grant a predefined role to a group at the Project level, then inspect the resulting policy — the standard workflow for onboarding a team to a project.

```bash
gcloud projects add-iam-policy-binding my-project-id \
  --member="group:data-analysts@example.com" \
  --role="roles/bigquery.dataViewer"
```

**Expected output (abbreviated):**

```
Updated IAM policy for project [my-project-id].
bindings:
- members:
  - group:data-analysts@example.com
  role: roles/bigquery.dataViewer
etag: BwXhZ...
version: 1
```

**Viewing the full effective policy:**

```bash
gcloud projects get-iam-policy my-project-id --format=json
```

> 💡 **Tip:** `gcloud projects get-iam-policy` only shows bindings set directly on the project — it does **not** show inherited Organization/Folder bindings. To see the full effective picture, use the Policy Analyzer (Cloud Asset Inventory) or `gcloud asset analyze-iam-policy`, which walks the full ancestry.

## 35.7 Production & Enterprise Usage

- **Group-based bindings, never individual users.** Enterprises bind roles to Google Groups synced from an external identity provider (via Cloud Identity, Section 42), and manage membership in the group source of truth — this avoids IAM policy churn every time an employee joins, leaves, or changes teams.
- **Custom roles for least privilege at scale.** Large organizations maintain a curated library of custom roles trimmed from overly broad predefined roles (e.g., a "Compute Viewer minus serial-port access" role), version-controlled and deployed via Terraform (Section 52).
- **Periodic access review via Policy Analyzer and Recommender.** IAM Recommender automatically flags over-provisioned bindings (e.g., a principal with `roles/editor` who only ever used `storage.objectViewer` permissions in the last 90 days) for security teams to review and tighten.

## 35.8 Common Misconceptions

- **Misconception:** "Removing a role binding at the Project level removes all access, even if it was granted at the Organization level." Inherited grants from a higher node remain in effect regardless of what's removed at the Project level — the only way to block them is an IAM Deny policy or removing the binding at the level where it was actually set.
- **Misconception:** "IAM Conditions can restrict any grant however I want." CEL conditions can reference a specific, limited set of attributes (mainly request time and resource attributes) — they are not a general-purpose custom-logic engine, and not every resource type supports every attribute.
- **Misconception:** "`roles/viewer` is always safe to grant broadly since it's read-only." `roles/viewer` still exposes a very large surface of metadata and configuration across nearly every service in a project, which can itself be sensitive (e.g., viewing all secrets' metadata, network configuration, IAM policies) — "read-only" is not the same as "harmless."

## 35.9 Interview Questions

**🎯 Beginner:** _What are the three types of IAM roles in GCP, and which should be the default choice?_
**Model answer:** Basic (primitive) roles — Owner, Editor, Viewer — are legacy and extremely broad; predefined roles are Google-maintained, service-scoped roles that should be the default choice for most access needs; custom roles let you assemble an exact permission set when no predefined role fits, at the cost of ongoing maintenance as GCP's permission surface evolves.

**🎯 Intermediate:** _A user was granted `roles/editor` at the Organization level. Can a Project administrator revoke that user's editor access just within their own project?_
**Model answer:** No — IAM grants are additive and flow downward through the resource hierarchy without the ability to be revoked at a lower level. The Project administrator cannot remove access that was granted above their level. To block it, they would need an IAM Deny policy scoped to that project explicitly denying the relevant permissions for that user, or escalate to whoever controls the Organization-level binding to remove it there.

**🎯 Senior/Architect:** _Design an IAM access model for a company with 500 engineers across 20 teams, needing least privilege, auditability, and minimal ongoing administrative burden._
**Model answer:** I would federate identity through Cloud Identity (Section 42) synced from the corporate IdP, and never bind IAM roles to individual users directly — bindings target Google Groups whose membership is managed in the IdP, so joiner/mover/leaver changes require zero IAM policy edits. I'd build a small library of custom roles derived from predefined roles but trimmed to the actual permissions each team uses (informed by IAM Recommender data), granted at the team's Folder level so it flows down to every project the team owns without per-project configuration. For anything security-critical (service account key creation, IAM policy modification itself), I'd add IAM Deny policies at the Organization level as a hard backstop that no team-level grant can override. I'd review Policy Analyzer / Recommender output quarterly to catch drift and over-provisioning, and require all bindings to be applied via Terraform (Section 52) rather than console clicks, so every change is code-reviewed and auditable in version control in addition to Cloud Audit Logs (Section 40).

## 🔑 Key Takeaways

- 🔑 IAM binds principals (users, groups, service accounts, domains) to roles (basic/predefined/custom) on a resource, forming a policy made of bindings, each optionally scoped by a CEL condition.
- 🔑 IAM grants are additive and inherit downward through the resource hierarchy permanently — they cannot be revoked below where they were set; use IAM Deny policies or Organization Policies to restrict instead.
- 🔑 Basic roles (Owner/Editor/Viewer) are legacy and overly broad for production use; predefined roles should be the default, with custom roles reserved for gaps.
- 🔑 Group-based bindings (not individual users) are the enterprise standard, minimizing IAM churn as team membership changes.
- 🔑 GCP's grant-flows-down IAM model is architecturally different from AWS's non-hierarchical IAM + restriction-only SCPs, though similar in spirit to Azure RBAC's Management Group inheritance.

## Related Concepts

Resource hierarchy and policy inheritance (Section 3), Service Accounts (Section 36), Organization Policies (Section 37), Security Command Center (Section 39), Cloud Audit Logs (Section 40), and Cloud Identity / Context-Aware Access (Section 42) all build directly on the IAM model introduced here.
