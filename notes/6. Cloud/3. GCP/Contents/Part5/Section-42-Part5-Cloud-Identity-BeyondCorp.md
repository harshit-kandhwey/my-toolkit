# Section 42 (Part 5): Cloud Identity & Context-Aware Access (BeyondCorp Enterprise)

## 1. Definition

**Plain language:** Before anyone can be granted a GCP IAM role, they need an identity to grant it _to_ — a username and login system, independent of whether the organization uses Gmail/Google Workspace at all. And once someone is logged in, a traditional VPN-based "you're on the corporate network, so you're trusted" model is increasingly considered weak — this section covers GCP's identity provider and its "trust based on context, not network location" access model.

**Precise:** **Cloud Identity** is GCP's Identity-as-a-Service (IDaaS) offering, providing user/group identity management independent of Google Workspace. **Identity-Aware Proxy (IAP)** enforces access control at the application layer, in front of a web app or VM, based on identity and context rather than network location. **Context-Aware Access** evaluates signals like device state, location, and IP address as conditions for granting access. **BeyondCorp Enterprise** is Google's productized zero-trust access platform built on these primitives, letting an organization replace or reduce reliance on a traditional perimeter VPN.

## 2. Why It Exists

Two separate gaps drove these tools into existence. First, **not every organization uses Google Workspace** — many run Microsoft 365, Okta, or another IdP for email/productivity, but still need a way to create and manage GCP user identities and groups for IAM purposes. Cloud Identity exists to decouple "who can log into GCP and be granted IAM roles" from "whose email inbox runs on Google" — you can adopt Cloud Identity purely for identity/IAM purposes with zero Workspace usage.

Second, the traditional security model — a VPN perimeter where anyone on the corporate network is implicitly more trusted — breaks down for several modern realities: remote work means "the corporate network" is porous or meaningless, a compromised laptop on the VPN is just as dangerous as one that isn't, and internal applications historically assumed network location alone was a sufficient trust signal, layering little to no additional identity verification on top. **Zero trust** (the model Google itself pioneered internally as "BeyondCorp," years before "zero trust" became industry terminology) exists to replace "trusted because you're inside the network" with "trusted because you and your device satisfy specific, continuously re-evaluated conditions," regardless of network location.

## 3. Cloud Identity

Cloud Identity provides the user and group objects that GCP IAM principals (Section 35) are ultimately bound to. It is offered as a **Free edition** (core identity management, group creation, basic device management) and a **Premium edition** (adds advanced endpoint management, security features like Context-Aware Access enforcement, and app management). Crucially, it can be adopted **standalone**, with no Google Workspace subscription — an organization already using Microsoft 365 for email can still use Cloud Identity purely to manage the users/groups that map onto GCP IAM, and typically federates it with their existing corporate IdP (Azure AD/Entra ID, Okta) via SAML/OIDC so employees still use one single sign-on rather than a separate GCP-specific login.

## 4. Identity-Aware Proxy (IAP)

**IAP** sits in front of an application (an App Engine app, a load-balanced backend, a Compute Engine VM's SSH/RDP access, or a GKE-hosted service) and enforces authentication and authorization _before_ any request reaches the application itself — the application no longer needs to implement its own login screen or trust that the network path is secure, because IAP has already verified the caller's identity and applied an IAM check (`roles/iap.httpsResourceAccessor` or similar) before forwarding the request.

For SSH/RDP specifically, **IAP TCP forwarding** lets administrators reach a VM's management port through an encrypted tunnel authorized by IAM, without that VM needing a public IP address or a traditional bastion host/VPN — a major simplification of remote administrative access that also means there's no standing public attack surface to defend.

## 5. Context-Aware Access

**Context-Aware Access** lets an access decision depend on more than "is this identity authorized" — it evaluates an **access level**, a named set of conditions built from signals like:

- **Device state** — is the device managed and compliant (encrypted disk, OS patch level, screen lock enabled), verified via endpoint verification.
- **IP address / network** — is the request originating from an approved IP range (e.g., corporate egress IPs) or a disallowed geography.
- **User identity/group membership** — layered on top of, not instead of, standard IAM.

An access level might state "allow access to this application only from a managed, compliant device, from an approved country, for users in the `finance-team` group" — and that access level can be attached to IAP-protected resources, to Cloud Identity sign-in itself, or (in more advanced configurations) to API access more broadly.

## 6. BeyondCorp Enterprise

**BeyondCorp Enterprise** packages IAP, Context-Aware Access, endpoint verification, and integrated threat/data protection (URL filtering, DLP for browser-based access) into Google's productized zero-trust platform — the direct external offering of the model Google itself uses internally to let employees access internal applications without a traditional VPN, based purely on verified identity and device/context signals re-evaluated continuously rather than trusted once at VPN connect time.

## 7. Architecture Diagram

```
     USER (remote, no VPN)
           │
           │ HTTPS request to internal app URL
           ▼
   ┌────────────────────────────────┐
   │   IDENTITY-AWARE PROXY (IAP)   │
   │                                │
   │  1. Verify identity            │◄── Cloud Identity / federated
   │     (who is this?)             │    corporate IdP (SAML/OIDC)
   │                                │
   │  2. Evaluate Context-Aware     │◄── Signals: device compliance,
   │     Access level               │    IP range, geography
   │     (is context acceptable?)   │
   │                                │
   │  3. Check IAM binding          │◄── roles/iap.httpsResourceAccessor
   │     (is this identity allowed?)│
   └───────────────┬────────────────┘
                   │ all three pass
                   ▼
          ┌───────────────────┐
          │  Internal App /   │
          │  VM SSH / GKE svc │   ◄ no public IP, no VPN,
          └───────────────────┘      no standing attack surface
```

## 8. Comparison with AWS and Azure

| Concept                                                          | GCP                        | AWS                                                                              | Azure                                                                                                 |
| ---------------------------------------------------------------- | -------------------------- | -------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Standalone identity provider (independent of productivity suite) | Cloud Identity             | AWS IAM Identity Center (still AWS-account-scoped identity, not a general IDaaS) | Microsoft Entra ID (can be standalone, independent of Microsoft 365)                                  |
| Application-layer access proxy                                   | Identity-Aware Proxy (IAP) | Verified Access                                                                  | Azure AD Application Proxy                                                                            |
| Context/condition-based access decisions                         | Context-Aware Access       | Verified Access policies (device trust signals)                                  | Conditional Access                                                                                    |
| Productized zero-trust platform                                  | BeyondCorp Enterprise      | Verified Access (narrower scope than BeyondCorp Enterprise)                      | Entra Conditional Access + Zero Trust reference architecture (broader ecosystem, less single-product) |
| SSH/RDP without public IP or VPN                                 | IAP TCP forwarding         | Systems Manager Session Manager                                                  | Azure Bastion                                                                                         |

> 💡 **Tip:** Azure's Conditional Access is the closest one-to-one analog to Context-Aware Access in terms of maturity and adoption — both evaluate device, location, and identity signals as access conditions. AWS's Verified Access is the newest of the three and narrower in scope than BeyondCorp Enterprise's bundled offering (threat/data protection, endpoint verification) as of general availability.

## 9. Hands-On Example: Protecting an App Engine App with IAP and an Access Level

**Purpose:** Enable IAP on an existing App Engine application, grant a group access, and create a basic Context-Aware Access level restricting access to a specific IP range.

```bash
gcloud iap web enable --resource-type=app-engine --project=my-project

gcloud iap web add-iam-policy-binding \
  --resource-type=app-engine --project=my-project \
  --member="group:finance-team@example.com" \
  --role="roles/iap.httpsResourceAccessor"

gcloud access-context-manager levels create corp_network_only \
  --title="Corp Network Only" \
  --basic-level-spec=level-spec.yaml \
  --policy=THE_POLICY_ID
```

Where `level-spec.yaml` contains:

```yaml
- ipSubnetworks:
    - "203.0.113.0/24"
```

**Expected output (abbreviated):**

```
IAP enabled for App Engine application on project [my-project].
Updated IAM policy for App Engine application.
Created access level [corp_network_only].
```

> ⚠️ **Interview-relevant nuance:** IAP is an _additional_ authorization layer, not a replacement for the application's own IAM-based access control — a user still needs the `roles/iap.httpsResourceAccessor` binding to pass IAP itself, and typically also needs whatever IAM role the underlying resource requires; IAP guards the front door, it doesn't grant permissions on what's behind it.

## 10. Production & Enterprise Usage

- **Federating Cloud Identity with an existing corporate IdP.** Enterprises rarely have employees log in twice — Cloud Identity is federated (via SAML/OIDC) with the organization's primary IdP (Entra ID, Okta), so GCP access uses the same single sign-on and MFA employees already use for every other corporate system, with Cloud Identity acting as the GCP-facing identity layer rather than a separate credential store.
- **Replacing VPN-based access to internal tools with IAP.** Organizations migrating off traditional VPN access commonly start with lower-risk internal tools (wikis, dashboards, admin panels) behind IAP with a Context-Aware Access level, proving the model works operationally before extending it to more sensitive systems — a gradual rollout rather than a single cutover.
- **IAP TCP forwarding to eliminate bastion hosts.** Removing public IPs and standing bastion infrastructure for SSH/RDP access, replaced by IAP TCP forwarding gated on IAM and Context-Aware Access, removes an entire class of "exposed management port" findings that would otherwise show up repeatedly in Security Command Center (Section 39).

## 11. Common Misconceptions

- **Misconception:** "Cloud Identity requires a Google Workspace subscription." It does not — Cloud Identity can be adopted entirely standalone for identity/IAM purposes, with an organization's actual email/productivity suite running elsewhere.
- **Misconception:** "IAP replaces the need for IAM roles on the underlying resource." IAP is an additional front-door layer; a user still needs both the IAP accessor role and whatever IAM permissions the underlying resource itself requires — it doesn't collapse two authorization checks into one.
- **Misconception:** "Context-Aware Access and Zero Trust/BeyondCorp Enterprise are the same thing." Context-Aware Access is one building block (evaluating conditions like device and location); BeyondCorp Enterprise is the broader productized platform that bundles Context-Aware Access with IAP, endpoint verification, and additional threat/data protection features.

## 12. Interview Questions

**🎯 Beginner:** _What is Cloud Identity, and why might an organization use it even if they don't use Google Workspace?_
**Model answer:** Cloud Identity is GCP's identity-as-a-service offering, providing the user and group objects that GCP IAM roles are ultimately bound to. It's independent of Google Workspace — an organization can adopt Cloud Identity purely to manage identities for GCP access, typically federated with their actual corporate IdP (like Entra ID or Okta), while running email and productivity tools elsewhere entirely.

**🎯 Intermediate:** _How does Identity-Aware Proxy change the security model for accessing an internal application, compared to a traditional VPN?_
**Model answer:** A traditional VPN grants network-level trust once a device connects — after that, the application often relies on network location as an implicit trust signal, with limited additional verification. IAP instead sits in front of the specific application and verifies identity, evaluates Context-Aware Access conditions (device compliance, location), and checks an explicit IAM binding on every request, regardless of network location — there's no broad "inside the network" trust zone at all. This also means an internal app behind IAP doesn't need a public IP, VPN, or bastion host to be reached securely, since IAP itself is the enforcement point.

**🎯 Senior/Architect:** _Design a plan to migrate a mid-size company off traditional VPN-based access to internal GCP-hosted tools, toward a BeyondCorop Enterprise-style zero-trust model._
**Model answer:** I'd start by federating Cloud Identity with the company's existing corporate IdP so no new credential system is introduced for employees. I'd inventory internal applications and rank them by sensitivity and current VPN dependency, then migrate lower-risk internal tools first (wikis, internal dashboards) behind IAP, proving the operational model — IAM bindings for `iap.httpsResourceAccessor`, plus a baseline Context-Aware Access level requiring a managed/compliant device — before touching higher-sensitivity systems. For remote administrative access to VMs, I'd replace bastion hosts and VPN-based SSH/RDP with IAP TCP forwarding, removing public IPs from those VMs entirely and eliminating a recurring class of exposed-port findings. As confidence grows, I'd extend Context-Aware Access levels to be genuinely risk-based — tighter conditions (specific approved networks, stricter device posture) for more sensitive applications — and only fully decommission the legacy VPN once the highest-risk applications have been migrated and validated under the new model, rather than cutting over all at once. Throughout, I'd track Policy Denied audit logs (Section 40) and Security Command Center findings (Section 39) to catch both attempted unauthorized access and any access level misconfiguration during the transition.

## 🔑 Key Takeaways

- 🔑 Cloud Identity is GCP's standalone identity provider, independent of Google Workspace, supplying the user/group principals that GCP IAM roles are bound to; it's typically federated with an organization's existing corporate IdP.
- 🔑 Identity-Aware Proxy (IAP) enforces identity- and context-based access at the application layer, in front of web apps and via TCP forwarding for SSH/RDP, removing the need for public IPs, bastion hosts, or a traditional VPN.
- 🔑 Context-Aware Access evaluates conditions like device compliance, IP range, and location as access-level requirements, layered on top of (not instead of) standard IAM checks.
- 🔑 BeyondCorp Enterprise is Google's productized zero-trust platform bundling IAP, Context-Aware Access, endpoint verification, and threat/data protection — the external offering of the model Google itself pioneered internally.
- 🔑 GCP's IAP/Context-Aware Access maps closely to AWS Verified Access and Azure AD Application Proxy/Conditional Access respectively, with Azure's Conditional Access being the most mature comparable offering among the three.

## Related Concepts

IAM Fundamentals (Section 35), VPC Service Controls (Section 41), Compliance & Governance (Section 40), Security Command Center (Section 39), GKE Security & Workload Identity (Section 33), and networking fundamentals (Part 3) all connect directly to the identity and zero-trust concepts introduced here.
