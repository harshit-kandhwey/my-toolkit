# Section 9 — Managed Identities & Service Principals

## 1. Definition

**Plain language:** Applications, scripts, and automated processes need to authenticate to Azure just like people do — but they shouldn't use a human's username and password. Service Principals and Managed Identities are the two mechanisms Azure provides for giving non-human actors their own identity, so they can authenticate and be granted RBAC permissions independently of any person.

**Precise definition:** A **Service Principal** is the tenant-local security principal representing an application's identity and permissions within Microsoft Entra ID (introduced conceptually in Section 6.3.4), authenticated via a client secret, certificate, or federated credential. A **Managed Identity** is a special, Microsoft-managed type of service principal, automatically created and lifecycle-bound to a specific Azure resource, that eliminates the need to store, rotate, or manage any credential at all.

## 2. Why It Exists / Problem It Solves

Automated processes — a CI/CD pipeline, a web application that needs to read from a Storage Account, a scheduled script — need to authenticate to Azure APIs. The naive approach of embedding a human's username/password (or even a service account's password) directly into application configuration or pipeline scripts creates serious problems: the credential must be stored somewhere (configuration files, environment variables, secrets stores), it must be rotated periodically to limit exposure from a leak, and if it does leak (committed to source control, exposed in logs), it grants an attacker whatever access that credential has, with no automatic way to detect the misuse as distinct from legitimate use. Service Principals solve the "give an application its own identity" half of this problem; Managed Identities go further and eliminate the credential-management burden entirely by having Microsoft handle credential issuance and rotation transparently, behind the scenes.

## 3. Service Principals — Deep Dive

**Definition:** A Service Principal is created when an application is registered in Entra ID (Section 6.3.4) — it represents that application's identity and permissions within a specific tenant, separate from the global Application object.

**Authentication methods for Service Principals:**

- **Client secret** — a password-like string generated for the application, which must be stored securely (ideally in Azure Key Vault, Section 56) and rotated periodically. The simplest method, but carries the most credential-management burden and risk.
- **Certificate** — a X.509 certificate used for authentication instead of a shared secret, generally considered more secure since the private key never needs to be transmitted, but still requires certificate lifecycle management (renewal, secure storage).
- **Federated credential (Workload Identity Federation)** — allows an external system (such as a GitHub Actions pipeline or another cloud provider's workload identity) to exchange its own trusted token for an Azure access token, without storing any Azure-specific secret at all. This is the modern recommended approach for CI/CD pipelines specifically because it removes the stored-secret problem entirely for that use case.

**When to use a Service Principal (rather than a Managed Identity):** When the application or process runs _outside_ Azure (e.g., on-premises, in another cloud, in a third-party CI/CD system) and therefore cannot use a Managed Identity, which is fundamentally tied to Azure-hosted resources.

## 4. Managed Identities — Deep Dive

**Definition:** A Managed Identity is a service principal that Azure creates and manages automatically for a specific Azure resource (such as a VM, an App Service, or a Function App), with credential issuance and rotation handled entirely by the Azure platform — the application code never sees, stores, or manages any secret at all.

**Two types:**

| Type                | Lifecycle                                                                                                                      | Sharing                                              |
| ------------------- | ------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------- |
| **System-assigned** | Created and deleted automatically alongside the specific resource it's attached to (e.g., a VM) — a true 1:1 lifecycle binding | Cannot be shared between resources                   |
| **User-assigned**   | Created as a standalone Azure resource with its own independent lifecycle                                                      | Can be assigned to multiple resources simultaneously |

**When to use system-assigned vs. user-assigned:** System-assigned is simplest and appropriate when exactly one resource needs the identity and it's acceptable for the identity to be deleted when that resource is deleted. User-assigned is appropriate when multiple resources need to share the same identity and permission set (e.g., several VM instances in a scale set that all need identical Storage Account access), or when the identity needs to persist independently of any single resource's lifecycle (e.g., surviving a VM being recreated).

**How it works internally (simplified):** A resource with a Managed Identity enabled can query a local, non-internet-routable metadata endpoint available only from within that specific Azure resource, requesting a token. Azure's platform infrastructure validates that the request genuinely originates from that specific resource, then issues a short-lived access token on the identity's behalf — the application code calls a local endpoint and receives a token; it never handles a long-lived secret at any point.

⚠️ Exact endpoint URLs, token lifetimes, and specific implementation details of the Managed Identity metadata service change and vary by hosting service (VM vs App Service vs AKS, for example) — verify current specifics against official documentation for the specific compute service being used before implementing.

### 4.1 Comparison — Service Principal vs. Managed Identity

| Aspect                | Service Principal                                           | Managed Identity                                               |
| --------------------- | ----------------------------------------------------------- | -------------------------------------------------------------- |
| Credential management | Manual (secret/certificate rotation is your responsibility) | Automatic, handled entirely by Azure                           |
| Where it can be used  | Anywhere (Azure, on-premises, other clouds)                 | Only from within Azure-hosted resources                        |
| Setup complexity      | Higher (manage secret storage, rotation)                    | Lower (enable a flag on the resource)                          |
| Best use case         | External CI/CD, cross-cloud/hybrid automation               | Any Azure-hosted application/resource needing Azure API access |

🎯 **Interview Tip:** "Always prefer a Managed Identity over a Service Principal with a stored secret, whenever the workload runs inside Azure" is close to a universally correct best-practice statement and a strong default answer to almost any "how should this Azure-hosted app authenticate" question.

## 5. Configuration & Commands

**Enabling a system-assigned Managed Identity on an existing VM:**

```bash
az vm identity assign --resource-group rg-myapp-prod --name vm-web-01
```

- **Purpose:** Enables a system-assigned Managed Identity on an existing VM, creating a new service principal in Entra ID automatically bound to that VM's lifecycle.
- **Expected output (abbreviated):**

```json
{
  "systemAssignedIdentity": "a1b2c3d4-...",
  "userAssignedIdentities": {}
}
```

- **Next step required:** Enabling the identity alone grants no permissions — an RBAC role assignment (Section 8) must still be created, targeting this new identity as the security principal, before it can actually access any resource.

**Granting the newly created Managed Identity access to a Storage Account:**

```bash
az role assignment create \
  --assignee "a1b2c3d4-..." \
  --role "Storage Blob Data Reader" \
  --scope "/subscriptions/<sub-id>/resourceGroups/rg-myapp-prod/providers/Microsoft.Storage/storageAccounts/stmyappdata"
```

- **Purpose:** Grants the VM's Managed Identity read-only access to blob data in a specific Storage Account, following least-privilege scoping (a narrow role, a narrow scope) rather than a broad Contributor grant.
- **Common error:** Assigning the role too quickly after identity creation can occasionally fail due to Entra ID replication delay — retrying after a short wait typically resolves this.

## 6. Production & Enterprise Usage

Enterprise Azure environments strongly standardize on Managed Identities for any workload actually hosted in Azure, reserving Service Principals with stored credentials for the genuinely necessary cases: CI/CD systems hosted outside Azure (though even here, Workload Identity Federation is increasingly preferred to avoid stored secrets entirely), hybrid/multi-cloud automation, and legacy systems that predate Managed Identity availability for their specific resource type. A common enterprise governance control is an Azure Policy (Section 57) that flags or blocks the creation of Service Principal credentials with long-lived secrets (e.g., secrets with multi-year expiration) or without an expiration date at all, forcing shorter rotation cycles as a security baseline.

## 7. Security Considerations

- Managed Identities structurally eliminate an entire class of credential-leak risk (there is no secret to leak, since the application never handles one directly) — this is their single biggest security advantage over Service Principals with stored secrets.
- Service Principal secrets, when required, should always be stored in Azure Key Vault (Section 56) rather than in application configuration files, environment variables committed to source control, or CI/CD pipeline variables stored in plaintext.
- Both Service Principals and Managed Identities should follow the same least-privilege RBAC principles as human identities (Section 8.7) — an over-privileged application identity is just as dangerous as an over-privileged human one, and arguably more so since applications often run unattended and continuously.

## 8. Troubleshooting

| Symptom                                                                      | Likely Cause                                                                                                                                                                                         | Fix                                                                                                                                                                           |
| ---------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Application code fails to acquire a token from the Managed Identity endpoint | Managed Identity not yet enabled on the resource, or code is running somewhere other than the expected Azure resource (e.g., a developer's local machine, where no Managed Identity endpoint exists) | Verify identity is enabled (`az vm identity show`); use a different local-development credential mechanism when running outside Azure                                         |
| Token acquired successfully but API calls still fail with "Forbidden"        | Identity has no RBAC role assignment for the target resource                                                                                                                                         | Assign an appropriate role at the correct scope (Section 8.5)                                                                                                                 |
| Service Principal authentication suddenly stops working in production        | Client secret expired                                                                                                                                                                                | Rotate/regenerate the secret and update wherever it's stored (ideally Key Vault), then investigate moving to a Managed Identity or federated credential to prevent recurrence |

## 9. Interview Questions — Section 9

### 🎯 Intermediate

**Q: What is the key advantage of a Managed Identity over a Service Principal with a client secret?**

_Model answer:_ A Managed Identity eliminates the need to store, secure, and rotate any credential at all — Azure handles token issuance transparently behind a local metadata endpoint that only the bound resource can access, so there's no secret to leak, expire unexpectedly, or manage. A Service Principal with a client secret requires ongoing credential lifecycle management and creates a real leak risk if the secret ends up in source control, logs, or an insecure configuration store.

_What the interviewer is probing:_ whether the candidate defaults to the more secure, lower-operational-burden option for Azure-hosted workloads, rather than reflexively reaching for a Service Principal out of habit.

### 🎯 Senior

**Q: A CI/CD pipeline running in an external system (not Azure-hosted) needs to deploy resources to Azure. Since Managed Identity isn't available here, how would you authenticate it as securely as possible?**

_Model answer:_ Since the pipeline runs outside Azure, a system-assigned Managed Identity isn't an option — but rather than defaulting to a Service Principal with a stored client secret, I'd first check whether the CI/CD platform supports Workload Identity Federation (federated credentials) with Entra ID. Platforms like GitHub Actions support this: the pipeline presents its own platform-issued token, Entra ID validates it against a configured trust relationship, and issues an Azure access token in exchange — with no Azure secret stored in the pipeline at all. If federation isn't supported by the specific CI/CD platform in use, I'd fall back to a Service Principal with a certificate (preferred over a plain client secret) or client secret, stored in a secrets manager (ideally Key Vault, referenced securely by the pipeline rather than hardcoded), with a short rotation cycle and RBAC scoped as narrowly as possible to only the resources the pipeline actually needs to touch.

_What the interviewer is probing:_ awareness of the modern federated-credential approach as the preferred solution, with a sound fallback plan when it's unavailable — this differentiates a candidate current on modern Azure security practices from one only familiar with older patterns.

## 10. Common Misconceptions

- **"Managed Identities work from anywhere, including my local machine."** False — Managed Identity's metadata endpoint is only reachable from within the specific Azure resource it's bound to; local development requires a different credential mechanism (such as a developer's own `az login` session via the SDK's default credential chain).
- **"A Service Principal and an App Registration are the same thing."** Related but distinct — the App Registration creates the global Application object, and the Service Principal is the tenant-local identity instance derived from it (as introduced in Section 6.3.4); in casual conversation the terms are sometimes used loosely, but the distinction matters precisely in multi-tenant application scenarios.

## 11. Key Takeaways

- 🔑 Service Principals and Managed Identities both give non-human actors their own Entra ID identity so they don't need to borrow a human's credentials.
- 🔑 Managed Identities are Azure-managed service principals bound to a specific resource's lifecycle, requiring no manual credential management — always prefer them for Azure-hosted workloads.
- 🔑 System-assigned Managed Identities have a 1:1 lifecycle with their resource; user-assigned identities are standalone and can be shared across multiple resources.
- 🔑 For workloads outside Azure, prefer Workload Identity Federation over a stored client secret wherever the external platform supports it.
- 🔑 Enabling an identity grants no access by itself — an explicit RBAC role assignment is always required afterward.

## 12. Related Concepts (Next Up)

Section 10 covers **Conditional Access, Multi-Factor Authentication (MFA), and Privileged Identity Management (PIM)** — the additional Entra ID security controls layered on top of the identities (human and non-human) discussed across Sections 6–9, completing Part 2 before Part 3 moves into Core Compute services.
