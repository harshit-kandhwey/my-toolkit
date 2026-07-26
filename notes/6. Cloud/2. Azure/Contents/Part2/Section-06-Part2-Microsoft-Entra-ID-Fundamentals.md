# Section 6 — Microsoft Entra ID Fundamentals

## 1. Definition

**Plain language:** Microsoft Entra ID (formerly Azure Active Directory / Azure AD) is Microsoft's cloud-based identity system — it's the "who are you, and what are you allowed to do" service that sits behind every sign-in to Azure, Microsoft 365, and thousands of third-party applications.

**Precise definition:** Microsoft Entra ID is a cloud-based Identity and Access Management (IAM) service that provides authentication (verifying identity), authorization support (via integration with RBAC and application permissions), directory services (storing users, groups, and application registrations), and identity federation (via standard protocols like OAuth 2.0, OpenID Connect, and SAML) for an organization's tenant.

## 2. Why It Exists / Problem It Solves

Every cloud platform needs a trustworthy way to answer two questions before allowing any action: "who is making this request?" (authentication) and "are they allowed to do this specific thing?" (authorization). Before centralized cloud identity systems, organizations relied on on-premises Active Directory (AD), which worked well for internal, network-bound resources but wasn't designed for internet-facing, multi-device, multi-application, cloud-native scenarios. Entra ID exists to provide identity as a **cloud-native, internet-accessible service** that can authenticate users from anywhere, support modern protocol standards used by web and mobile applications, and serve as the single identity backbone across not just Azure resources but Microsoft 365, third-party SaaS applications, and custom-built applications — avoiding a proliferation of separate username/password systems per application.

## 3. Core Concepts

### 3.1 Tenant

**Definition:** A **Tenant** is a dedicated, isolated instance of Entra ID representing one organization. Every Entra ID tenant has a unique Tenant ID (a GUID) and a default domain (e.g., `contoso.onmicrosoft.com`), and contains that organization's users, groups, registered applications, and configuration. Azure Subscriptions (Section 4.3.3) are always associated with exactly one Entra ID tenant, though a single tenant can be associated with many subscriptions — this is why enterprises with multiple subscriptions (Production, Dev, per business unit) usually still share one central tenant for unified identity management, unless a specific business reason (like a fully independent subsidiary or M&A scenario) calls for tenant separation.

> ⚠️ **Do not confuse Tenant with Subscription.** A Tenant is an identity boundary (who exists and can sign in); a Subscription is a billing/resource boundary (Section 4.3.3). One tenant → many subscriptions is the common pattern; a subscription belonging to multiple tenants is not possible.

### 3.2 Users

**Definition:** A **User** object represents a person (or occasionally a non-human actor represented as a user, though Managed Identities/Service Principals are the correct mechanism for that, Section 9) who can authenticate against the tenant. Users can be:

- **Cloud-only** — created directly in Entra ID, with no on-premises counterpart.
- **Synchronized (hybrid)** — created in an on-premises Active Directory and synchronized into Entra ID via a tool like Microsoft Entra Connect, common in enterprises transitioning from or maintaining on-premises AD alongside cloud identity.
- **Guest (B2B)** — an external user (e.g., a partner organization's employee, or a personal Microsoft/Google account) invited into the tenant with restricted, controllable access, without needing a full internal account created for them.

### 3.3 Groups

**Definition:** A **Group** is a collection of users (and/or devices or other groups) used to assign permissions or licenses collectively rather than one user at a time. Entra ID supports:

- **Security groups** — used for access control (e.g., RBAC role assignment, Section 8), typically the group type used in access-management scenarios.
- **Microsoft 365 groups** — broader collaboration groups tied to shared resources like a mailbox, calendar, and Teams channel, more relevant to end-user collaboration than infrastructure access control.
- **Dynamic groups** — group membership computed automatically based on rules against user or device attributes (e.g., "all users in the Finance department"), reducing manual membership management overhead at scale.

> 💡 **Tip:** Best practice is to assign RBAC roles and access to **groups**, not individual users, so that access changes when someone joins/leaves a team are handled by adding/removing group membership rather than reconfiguring permissions on every resource individually — this is a foundational access-management pattern expected knowledge at intermediate level and above.

### 3.4 App Registrations and Enterprise Applications

**Definition:** An **App Registration** is how you register an application (whether built in-house or a third-party SaaS product) with Entra ID so it can authenticate users and, where needed, call APIs on their behalf. Registering an app creates an **Application object** (the global definition of the app) and, within each tenant that uses it, a corresponding **Service Principal** — the tenant-local identity representing that application's permissions and access within that specific tenant. This Application/Service Principal distinction matters for multi-tenant SaaS applications (one Application object, many tenant-specific Service Principals) — covered further in Section 9.

### 3.5 Authentication Protocols

Entra ID supports the modern, industry-standard protocols that underlie virtually all contemporary web/mobile sign-in flows:

- **OAuth 2.0** — an authorization framework (not itself an authentication protocol) that allows an application to obtain limited, scoped access to a user's resources without handling their password directly, using access tokens.
- **OpenID Connect (OIDC)** — an authentication layer built on top of OAuth 2.0, adding a standardized way to verify user identity (via an ID token) alongside OAuth's authorization capabilities — this is the protocol behind most modern "Sign in with Microsoft" flows.
- **SAML (Security Assertion Markup Language)** — an older, XML-based protocol still widely used for enterprise single sign-on (SSO) with legacy or enterprise SaaS applications that haven't adopted OIDC.

> ⚠️ A full protocol-level walkthrough of OAuth2/OIDC token flows is covered in Section 7, immediately following this section — this section introduces them only by name and purpose.

## 4. Architecture Diagram — Tenant Structure

```
Microsoft Entra ID Tenant ("contoso.onmicrosoft.com")
 ├── Users (cloud-only, synced-from-on-prem, guest/B2B)
 ├── Groups (security, M365, dynamic)
 ├── App Registrations
 │     ├── Application object (global definition)
 │     └── Service Principal (tenant-local instance, permissions)
 └── Associated with:
       ├── Azure Subscription "Production"
       ├── Azure Subscription "Development"
       └── Microsoft 365 licenses/services
```

## 5. Configuration & Commands

**Listing users in the tenant (Azure CLI):**

```bash
az ad user list --output table
```

- **Purpose:** Queries Entra ID (not ARM directly — this command talks to the Microsoft Graph API under the hood) for all users visible to the caller within the current tenant.
- **Common error:** `Insufficient privileges to complete the operation` — the signed-in account lacks the Entra ID role needed to read directory data broadly (directory read permissions are managed separately from Azure RBAC, an important distinction covered further in Section 8).

**Creating a security group:**

```bash
az ad group create --display-name "sg-devops-engineers" --mail-nickname "sg-devops-engineers"
```

- **Purpose:** Creates a new security group that can subsequently be used as the target of an RBAC role assignment (Section 8) or an Azure Policy exemption, rather than assigning access to individuals directly.
- **Important arguments:** `--display-name` is the human-readable name; `--mail-nickname` is a required unique identifier used internally (relevant even though the group itself isn't necessarily mail-enabled for security-group use cases).

## 6. Production & Enterprise Usage

Enterprises typically run **hybrid identity**, synchronizing an existing on-premises Active Directory into Entra ID via Microsoft Entra Connect, so that a single set of corporate credentials works both for on-premises resources (file shares, legacy applications) and cloud resources (Azure, Microsoft 365, SaaS apps), rather than maintaining two separate identity systems. Enterprises also make heavy use of **guest/B2B access** for external collaborators, **dynamic groups** to reduce manual access-list maintenance at scale, and enforce **Conditional Access policies** (Section 10) requiring multi-factor authentication and compliant devices before granting access to sensitive resources — none of which is optional in a mature enterprise security posture.

## 7. Security Considerations

- Entra ID is the single most consequential security boundary in an Azure environment — compromising a high-privilege identity (especially a Global Administrator) can compromise the entire tenant, all subscriptions, and all Microsoft 365 data. It is the highest-value target for attackers and therefore the highest-priority component to harden (MFA, Conditional Access, PIM — covered in Section 10).
- Guest/B2B users should be reviewed periodically (via **Access Reviews**, a feature covered further in Part 11) since external accounts that are no longer needed represent lingering access risk if forgotten.

## 8. Interview Questions — Section 6

### 🎯 Beginner

**Q: What is a Microsoft Entra ID tenant, and how does it relate to an Azure subscription?**

_Model answer:_ A tenant is a dedicated, isolated instance of Entra ID representing one organization's users, groups, and identity configuration. A subscription is a billing and resource boundary that belongs to exactly one tenant, though a tenant can have many subscriptions. They solve different problems: the tenant answers "who exists and can sign in," while the subscription answers "what resources exist and who's billed for them."

_What the interviewer is probing:_ whether the candidate can cleanly separate the identity concept from the billing/resource concept — a very common early confusion.

### 🎯 Senior

**Q: Your organization uses on-premises Active Directory today and is planning a phased migration to Azure. How would you approach identity during this transition?**

_Model answer:_ I'd recommend hybrid identity via Microsoft Entra Connect, synchronizing on-premises AD accounts into Entra ID so users have one consistent identity across both environments during the transition, rather than maintaining separate credential sets. Depending on requirements, this could use password hash synchronization (simplest, cloud validates a synced hash) or federation (on-premises infrastructure validates credentials directly) — the choice depends on existing infrastructure investment and specific compliance requirements. I'd also plan for eventual decommissioning of on-premises AD dependencies as more workloads move to the cloud, and would layer Conditional Access and MFA onto the synced identities early rather than treating security hardening as a separate later phase.

_What the interviewer is probing:_ real-world familiarity with hybrid identity as a _transitional_ architecture, not a permanent end state, and awareness that identity migration decisions have long tails that should be planned deliberately.

## 9. Common Misconceptions

- **"Azure AD and Microsoft Entra ID are different products."** They are not — Entra ID is the renamed continuation of Azure AD (as covered in Section 1.4); the underlying service and much of its terminology persist even as branding changes.
- **"RBAC roles and Entra ID directory roles are the same thing."** They are not — Azure RBAC (Section 8) controls access to Azure _resources_ (VMs, storage, etc.), while Entra ID directory roles (like Global Administrator) control access to _identity/directory management itself_; conflating the two is a common and important mistake, elaborated fully in Section 8.

## 10. Key Takeaways

- 🔑 A Tenant is Entra ID's isolation boundary for an organization's identities — distinct from a Subscription, which is a billing/resource boundary; one tenant typically maps to many subscriptions.
- 🔑 Entra ID supports cloud-only, synced (hybrid), and guest (B2B) user types, and access should be assigned to groups rather than individual users wherever practical.
- 🔑 App Registrations create an Application object plus a tenant-local Service Principal, forming the identity that applications (rather than humans) use to authenticate — this is the direct segue into Managed Identities and Service Principals in Section 9.
- 🔑 Entra ID is the highest-value security target in an Azure environment and should be hardened first, before resource-level controls.

## 11. Related Concepts (Next Up)

Section 7 builds directly on the protocol names introduced here (Section 6.3.5) by walking through **authentication vs. authorization** in detail and explaining exactly how OAuth 2.0, OpenID Connect, and SAML flows work in the Azure context — the mechanics behind every sign-in event this section has discussed only at a conceptual level.
