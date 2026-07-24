# Section 8 — Role-Based Access Control (RBAC)

## 8.1 Definition

**Plain language:** RBAC is how Azure decides what an already-authenticated identity is allowed to actually do. Instead of granting permissions to individuals one-by-one for every possible action, you assign them a **role** — a predefined bundle of permissions — at a specific **scope** (a management group, subscription, resource group, or individual resource).

**Precise definition:** Azure RBAC is an authorization system built into Azure Resource Manager that enforces access control by evaluating **role assignments** — the combination of a **security principal** (who), a **role definition** (what actions are allowed), and a **scope** (where those actions apply) — for every ARM API request, granting or denying the request based on whether an applicable assignment exists.

## 8.2 Why It Exists / Problem It Solves

Without RBAC, the only alternatives would be granting either full access to everything or no access at all — a completely unworkable model for any organization beyond a single person. Even simple alternatives like "give this person the resource's admin password" don't scale: passwords can't be scoped to specific actions, can't be easily audited per-person, and can't be revoked for one individual without affecting everyone who shares that credential. RBAC solves this by decomposing access into three independently configurable dimensions (who, what, where), allowing fine-grained, auditable, and revocable permission grants that can be assigned to exactly the set of people or systems that need them, at exactly the scope they need them for, without needing a distinct password or credential per permission level.

## 8.3 The Three Components of a Role Assignment

### 8.3.1 Security Principal (Who)

A security principal is any entity that can be assigned a role: a **User** (Section 6.3.2), a **Group** (Section 6.3.3, the recommended target for most role assignments), a **Service Principal** (representing an application, Section 9), or a **Managed Identity** (a special, more secure type of service principal, Section 9).

### 8.3.2 Role Definition (What)

A role definition is a named collection of permitted (and optionally, explicitly denied) **actions** — specific operations against specific resource types, expressed as strings like `Microsoft.Compute/virtualMachines/start/action`. Azure provides many **built-in roles** covering common scenarios, and supports fully **custom roles** for scenarios built-ins don't fit.

**Key built-in roles (the ones every engineer should know cold):**

| Role                          | Permissions Summary                                                                                                   | Typical Use                                                                           |
| ----------------------------- | --------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| **Owner**                     | Full access to all resources, _including the ability to grant access to others_                                       | Reserved for a very small number of trusted administrators                            |
| **Contributor**               | Full access to create/modify/delete resources, but **cannot** grant access to others (cannot manage RBAC assignments) | Engineers who need to build/manage resources but shouldn't manage who else has access |
| **Reader**                    | Read-only view of resources and their configuration, no modification rights                                           | Auditors, monitoring dashboards, read-only stakeholders                               |
| **User Access Administrator** | Manages _only_ who has access to resources — can assign roles, but cannot modify the resources themselves             | Identity/access administrators who shouldn't need broader resource permissions        |

> ⚠️ **The Owner vs. Contributor distinction is one of the single most commonly tested RBAC facts in interviews:** Contributor can do almost everything Owner can, _except_ manage other users' access — this single difference is what makes least-privilege design possible (most engineers should be Contributor, not Owner, since day-to-day work rarely requires granting access to others).

**Custom roles:** When built-in roles don't precisely match a real need (e.g., "can restart VMs but cannot delete them"), a custom role can be defined listing exact allowed (and denied) actions. Custom roles are defined via JSON and should be used sparingly — an explosion of overly specific custom roles becomes its own management burden, so built-in roles should always be preferred unless a genuine gap exists.

**Example custom role definition (illustrative):**

```json
{
  "Name": "VM Operator - Restart Only",
  "IsCustom": true,
  "Description": "Can restart VMs but cannot delete or reconfigure them.",
  "Actions": [
    "Microsoft.Compute/virtualMachines/restart/action",
    "Microsoft.Compute/virtualMachines/read"
  ],
  "NotActions": [],
  "AssignableScopes": ["/subscriptions/<subscription-id>"]
}
```

> ⚠️ Exact action-string names and JSON schema fields should always be verified against current Azure RBAC documentation before use — the general "Actions/NotActions/AssignableScopes" structure is stable, but individual action-string identifiers for specific resource operations are numerous and easy to mistype.

### 8.3.3 Scope (Where)

Scope is the boundary at which a role assignment applies, following the ARM hierarchy introduced in Section 4.3: Management Group → Subscription → Resource Group → Resource. A role assigned at a higher scope is inherited by everything beneath it (Section 4.4) — assigning "Contributor" at a subscription applies it to every resource group and resource within that subscription, unless a more specific consideration overrides it (Azure RBAC does not support true "deny at a lower level" the way some other systems do; the closest tool for genuinely blocking specific actions regardless of role is an explicit **Deny Assignment**, a more advanced and less commonly used mechanism).

## 8.4 Architecture Diagram — Role Assignment Evaluation

```
Incoming Request: "Can User Alice start VM 'vm-web-01'?"

ARM checks all role assignments applicable to Alice at:
  vm-web-01 (Resource level)          ← most specific
  rg-myapp-prod (Resource Group level)
  Production (Subscription level)
  Contoso-Root (Management Group level) ← broadest

If ANY applicable assignment grants the action → Allowed
If NO applicable assignment grants the action → Denied (implicit deny by default)
```

## 8.5 Configuration & Commands

**Assigning a role (Azure CLI):**

```bash
az role assignment create \
  --assignee "sg-devops-engineers" \
  --role "Contributor" \
  --scope "/subscriptions/<sub-id>/resourceGroups/rg-myapp-prod"
```

- **Purpose:** Grants the `sg-devops-engineers` group Contributor access, scoped only to the `rg-myapp-prod` resource group — following the best practice of assigning to a group (Section 6.3.3) at the narrowest scope that satisfies the actual need.
- **Important arguments explained individually:**
  - `--assignee` — the security principal receiving the role; can be a user, group, or service principal, referenced by object ID, UPN, or (for some resources) display name.
  - `--role` — the role definition name, either built-in (like `Contributor`) or a custom role's name.
  - `--scope` — the full ARM resource ID defining where this assignment applies; note that using a broader scope (e.g., the subscription ID alone) would extend this Contributor access to every resource group in the subscription, not just this one — scope precision is a deliberate security decision, not a formality.
- **Common error:** `RoleAssignmentExists` if an identical assignment already exists (Azure prevents true duplicates); `PrincipalNotFound` if the assignee's object ID is stale or mistyped, commonly caused by referencing a deleted-and-recreated identity by an old cached ID.

**Listing role assignments for a scope:**

```bash
az role assignment list --scope "/subscriptions/<sub-id>/resourceGroups/rg-myapp-prod" --output table
```

- **Purpose:** Audits exactly who has access to a given scope, and via which role — an essential command for periodic access reviews and security audits.

## 8.6 Production & Enterprise Usage

Enterprises formalize RBAC design as part of their landing zone architecture (Part 13), typically defining a small set of standard custom or built-in roles mapped to organizational job functions (e.g., "Application Owner," "Network Operator," "Security Auditor"), assigned exclusively to groups (never individual users) at the narrowest scope that satisfies the team's actual responsibilities, and reviewed periodically via **Access Reviews** (Part 11) to catch and remove stale or over-broad access. A common enterprise anti-pattern this design explicitly guards against is "Owner sprawl" — engineers accumulating Owner role assignments because it's the path of least resistance, rather than the more restrictive but more appropriate Contributor role, gradually eroding least-privilege posture over time.

## 8.7 Security Considerations

- **Least privilege** is the guiding principle: always assign the least permissive role, at the narrowest scope, that satisfies the actual requirement — this minimizes the damage a compromised or misused credential can do.
- **Owner role** should be tightly restricted, since it uniquely grants the ability to modify access for others — a compromised Owner credential can be used to grant an attacker even broader access than the original compromise.
- **Regular audits** via `az role assignment list` (or the Portal's Access Control (IAM) blade) and formal Access Reviews are essential; permissions granted for a temporary project are a common source of long-forgotten, unnecessary access if not periodically reviewed.

## 8.8 Performance Considerations

RBAC evaluation happens on every ARM API call and is designed to be low-latency, but at very large scale (thousands of role assignments across a complex management group hierarchy), poorly organized assignment structures (e.g., excessive numbers of narrowly-scoped individual-user assignments instead of group-based assignments at appropriate levels) can increase management overhead and audit complexity, even though raw request-time evaluation performance is generally not the practical bottleneck — the real cost is administrative and security complexity, not runtime latency.

## 8.9 Troubleshooting

| Symptom                                                             | Likely Cause                                                                                                                       | Fix                                                                                           |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- |
| "AuthorizationFailed" error despite user believing they have access | No role assignment at the required scope, or wrong role (e.g., Reader instead of Contributor)                                      | Run `az role assignment list` at the relevant scope(s) to confirm actual assignments          |
| User can see a resource in the Portal but cannot modify it          | User has Reader (or no role) rather than Contributor/Owner at that scope                                                           | Assign an appropriate role at the correct scope                                               |
| Role assignment command fails with `PrincipalNotFound`              | Stale/incorrect object ID, often from a deleted-and-recreated identity                                                             | Re-fetch the current object ID via `az ad user show` / `az ad group show` before reattempting |
| A user has more access than expected                                | An inherited role assignment from a higher scope (Management Group/Subscription) not visible when only checking the resource group | Check role assignments at every level of the hierarchy, not just the immediate scope          |

## 8.10 Interview Questions — Section 8

### 🎯 Beginner

**Q: What's the difference between the Owner and Contributor built-in roles?**

_Model answer:_ Both roles can create, modify, and delete resources. The key difference is that Owner can additionally manage access — assigning or removing roles for other users — while Contributor cannot manage anyone's access, including their own. This makes Contributor the safer default for most engineers, since day-to-day resource work rarely requires the ability to grant access to others.

_What the interviewer is probing:_ the single most commonly-needed RBAC fact in real operational work — getting this backwards (assuming Contributor can manage access) is a frequent mistake among newer engineers.

### 🎯 Senior/Architect

**Q: How would you design RBAC for a 50-person engineering organization to follow least-privilege principles at scale, without creating unmanageable administrative overhead?**

_Model answer:_ I'd avoid individual-user role assignments entirely, instead mapping job functions to Entra ID security groups (e.g., "sg-platform-engineers," "sg-app-developers-teamA") and assigning built-in roles to those groups at the narrowest appropriate scope — typically resource-group level for team-specific work, with only a small number of trusted platform administrators holding broader subscription- or management-group-level roles. I'd prefer built-in roles over custom roles unless a genuine, recurring gap exists, since custom roles multiply management overhead. I'd implement scheduled Access Reviews (Part 11) to periodically validate group memberships stay accurate as people change teams, and would restrict Owner role assignment to a minimal, documented set of individuals, with even platform administrators using Contributor plus a separate, tightly-scoped access-management role rather than blanket Owner where avoidable. This keeps day-to-day administration group-based and low-overhead (add/remove group membership) while maintaining tight control over the small number of high-privilege exceptions.

_What the interviewer is probing:_ whether the candidate can design a scalable, maintainable access model rather than just defining RBAC terms — architecture-level thinking about how access management holds up as an organization grows.

## 8.11 Common Misconceptions

- **"Contributor can manage who else has access."** False — this is exclusively an Owner capability (or a dedicated User Access Administrator role); Contributor is deliberately restricted from it.
- **"RBAC supports true deny rules like a firewall."** Mostly false for standard use — Azure RBAC is fundamentally additive/allow-based; genuinely blocking a specific action regardless of other grants requires the separate, more advanced Deny Assignment mechanism, not a standard role assignment.
- **"If I don't see a role assignment on this resource group, the user has no access."** False — always check inherited assignments from higher scopes (subscription, management group) before concluding a user lacks access.

## 8.12 Key Takeaways

- 🔑 Every RBAC role assignment is the combination of a Security Principal (who), a Role Definition (what), and a Scope (where) — memorize this triad.
- 🔑 Owner vs. Contributor is defined by exactly one capability: managing others' access — this single fact is one of the most frequently tested RBAC concepts in interviews.
- 🔑 Role assignments inherit downward through the ARM hierarchy and are additive; there is no standard "deny" mechanism, only the advanced/uncommon Deny Assignment feature.
- 🔑 Best practice assigns roles to groups, not individuals, at the narrowest scope that satisfies the actual need, and reviews assignments periodically to prevent access sprawl.

## 8.13 Related Concepts (Next Up)

Section 9 covers **Managed Identities and Service Principals** — the non-human security principals referenced throughout this section (Section 8.3.1) as valid RBAC assignment targets, explaining exactly how applications and automation (rather than people) authenticate and receive authorization without ever handling a stored password or secret.
