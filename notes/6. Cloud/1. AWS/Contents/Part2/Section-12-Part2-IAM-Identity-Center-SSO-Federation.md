# Part 2 · Section 4 — IAM Identity Center (SSO) & Federation

> AWS Zero-to-Enterprise Knowledge Base · Part 2: Identity, Security & Governance

---

## 1. Definition

**Plain-language:** Instead of every employee having a separate password per AWS account, they log in once, see a dashboard of every account/role they're allowed into, and click through — AWS handles temporary-credential mechanics behind the scenes.

**Precise:** **AWS IAM Identity Center** (formerly AWS SSO) is AWS's managed service for **centralized human workforce identity and access management** across an AWS Organization, providing an SSO portal, centralized permission assignment via **Permission Sets**, and external IdP integration.

> 💡 **Mental model:** Identity Center is the check-in desk at a large venue — show ID once, get exactly the wristbands (temporary role sessions) for exactly the rooms (accounts) you're allowed into.

---

## 2. Why It Exists

- Enterprises may have dozens/hundreds of accounts. Without centralization, human access means a separate IAM user in every account — password sprawl, inconsistent permissions, painful offboarding.
- Identity Center inverts the model: identity lives centrally, _roles_ (Permission Sets) push out to accounts — extending "prefer roles over long-lived users" to org scale.
- Solves discovery too — one portal lists everything a user can reach.

---

## 3. Core Components

### 3.1 Identity Source

1. **Built-in directory** — simple, for smaller orgs.
2. **AWS Managed Microsoft AD / AD Connector** — for AD-standardized orgs.
3. **External IdP via SAML 2.0** — Okta, Azure AD, Ping, etc. — existing corporate credentials.

> 🔑 Most enterprises federate to an existing corporate IdP (option 3) — identity already lives somewhere; duplicating it creates drift/offboarding risk.

### 3.2 AWS Organizations Integration

- Deployed once at the Organization's management account level; assigns access into any member account.
- Requires Organizations to be set up first (Section 5 full depth).

### 3.3 Permission Sets

- A **template defining IAM permissions**, auto-provisioned as an actual **IAM role** in each target account when assigned.
- **AWS managed** (pre-built, job-function-based) or **Custom** (org-specific policy).
- Under the hood: assigning a Permission Set creates an IAM role with a trust policy trusting Identity Center, and the Permission Set's policy as permissions policy — Section 3's role mechanics, automated at scale.

### 3.4 Assignments

- Links **user/group + Permission Set + target account** — the triple that actually grants access. A Permission Set alone grants nothing.
- Assign to **groups**, not individuals, mirroring Section 1's group-based management, now at Organization scale.

---

## 4. End-User Experience

1. Navigate to the org's AWS access portal URL.
2. Authenticate against the identity source (corporate SAML IdP, with its own MFA typically).
3. Portal shows every account/Permission Set combination assigned — a tile per account.
4. Clicking a role opens the Console already logged into that account, or provides short-term CLI/SDK credentials.

> 🎯 Being able to describe the actual user-facing flow, not just backend architecture, signals real hands-on exposure.

---

## 5. SAML 2.0 vs OIDC

|                 | SAML 2.0                               | OIDC                                                   |
| --------------- | -------------------------------------- | ------------------------------------------------------ |
| Format          | XML assertions                         | JSON Web Tokens (JWT)                                  |
| Typical AWS use | Workforce federation (Identity Center) | CI/CD, modern app/mobile auth, Cognito                 |
| Era             | Older, dominant for corporate SSO      | Newer, OAuth 2.0-based, dominant for apps/machine auth |
| STS API         | `AssumeRoleWithSAML`                   | `AssumeRoleWithWebIdentity`                            |

> 💡 Both produce temporary STS credentials, but suit different populations (human workforce vs modern apps/automation).

---

## 6. Direct SAML Federation (without Identity Center)

- Possible to configure an IAM SAML IdP object in a single account + a role trusting it directly (`"Federated": "...saml-provider/..."`).
- Identity Center preferred at scale because direct SAML must be configured **per account**, with no multi-account portal or centralized assignment management.
- Direct SAML still makes sense for single-account setups or highly custom federation needs.

---

## 7. Recommended Access Hierarchy

1. **Root** — locked away, MFA-protected, root-only actions (§4).
2. **IAM Identity Center federated to corporate IdP** — primary, default human access.
3. **Standalone IAM users** — narrow exceptions: break-glass, legacy systems, very small setups.
4. **IAM roles for non-human access** (service roles, OIDC CI/CD) — separate from human access (Section 3).

> 🔑 Modern design treats standing IAM users as the exception requiring justification, not the default — the full maturation beyond Part 1's simplified single-account starting advice.

---

## 8. Production & Enterprise Usage

- **ABAC with Identity Center:** pass attributes (department, cost-center) as session tags; write fewer, broader policies referencing those tags in conditions — dynamic scoping instead of many narrow Permission Sets.
- **Just-in-time/time-bound access:** request elevated Permission Set for a limited window with approval, rather than standing elevated access — reduces always-on attack surface.
- **Offboarding:** disable at the identity source (single action) revokes access to every account touched — one of the model's most concrete benefits.

---

## 9. Security Considerations

- **MFA enforcement:** at the external IdP or Identity Center's built-in directory — non-negotiable for all human access.
- **Permission Set least privilege:** same discipline as Section 1 — a Permission Set is still just an IAM policy; overly broad ones reproduce the same anti-pattern at org scale.
- **Centralization concentrates risk:** Identity Center is the single gateway to every account — its own security (MFA, admin Permission Set assignment, monitoring) is disproportionately important; a compromise has an unusually large blast radius by design.

---

## 10. Troubleshooting

| Symptom                                      | Cause                                                                        | Fix                                              |
| -------------------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------ |
| User can't see an account they should access | No assignment linking user/group + Permission Set + account                  | Verify the assignment triple exists              |
| AccessDenied inside the account after login  | Provisioned role's policy (from Permission Set) doesn't grant the action     | Update the Permission Set's policy               |
| Permission Set changes don't apply           | Needs explicit re-provisioning to already-assigned accounts                  | Trigger re-provisioning after edits              |
| SAML login loop/failure                      | Metadata mismatch (cert, entity ID, ACS URL) between IdP and Identity Center | Re-verify SAML metadata exchange matches exactly |

---

## 11. Best Practices & Anti-Patterns

**Best practices:** federate to an existing corporate IdP rather than duplicating identity; assign Permission Sets to groups not individuals; apply least privilege to Permission Sets; use time-bound/JIT elevation for high privilege; treat Identity Center's own security as disproportionately critical.

**Anti-patterns:** standalone IAM users per employee "for simplicity"; broad `AdministratorAccess`-equivalent Permission Sets for convenience; forgetting to re-provision after Permission Set edits; maintaining a parallel built-in directory alongside an existing corporate IdP.

---

## 12. Common Misconceptions

- "Identity Center replaces IAM." → False — it orchestrates real IAM roles via Permission Sets; a UX/orchestration layer over IAM and STS.
- "Users need a separate password per account." → False — that's the exact problem it solves.
- "A Permission Set alone grants access." → False — needs the full assignment triple.
- "SAML and OIDC are interchangeable." → False — different formats/populations/STS APIs.

---

## 13. Interview Questions (with model answers)

**🟢 What problem does IAM Identity Center solve?** Centralizes human access across an Organization's accounts — one authentication, one portal listing every assigned account/role, replacing per-account standing users with centrally-managed temporary role access.

**🟢 What is a Permission Set?** A template of IAM permissions Identity Center auto-provisions as a real IAM role in a target account when assigned to a user/group — AWS managed or custom, analogous to managed/customer-managed IAM policies at single-account scale.

**🟡 Identity Center vs direct SAML federation on one account?** Both use SAML-based STS federation, but direct SAML is manual, per-account, no centralized portal/assignment management. Identity Center automates the same mechanism org-wide via Permission Sets and assignments. Direct SAML still fits single-account or highly custom needs.

**🟡 Why is offboarding a key benefit?** Without centralization, an employee with access to 20 accounts might have 20 standing IAM users to individually disable — easy to miss one. With Identity Center federated to the corporate IdP, disabling at the identity source (often HR-tied) immediately revokes portal authentication, cutting off every account in one action.

**🔴 Design identity/access for 40 accounts under one Organization using Azure AD?** Deploy Identity Center at the management account, federate to Azure AD via SAML rather than duplicating users. Mirror job functions into least-privilege Permission Sets, assigned to Azure AD security groups (auto-propagates on membership change). Layer time-bound approval-gated elevation for high-privilege actions instead of standing broad Permission Sets. Root stays locked per account, outside this model. Apply extra scrutiny to Identity Center's own config and the Azure AD tenant, since it's the highest-leverage target.

**🔴 Security review flags Identity Center as a single point of compromise — response?** Correct, expected observation, not a flaw to fix by abandoning centralization — it's the direct trade-off for consistent offboarding and eliminating password sprawl. Treat Identity Center and its IdP as highest-priority: strong MFA at the source, rigorous least privilege on every Permission Set, time-bound elevation for sensitive access, heavy CloudTrail monitoring on admin actions and resulting AssumeRole activity. Reverting to per-account standing users trades one well-monitored risk point for many poorly-monitored ones — a worse outcome.

---

## 🔑 Key Takeaways

1. IAM Identity Center centralizes human access across an Organization — one authentication, one portal — solving per-account standing-user sprawl at scale.
2. Permission Sets are templates that auto-provision real IAM roles in target accounts — Section 3's role/trust-policy mechanics, automated.
3. An assignment (user/group + Permission Set + account) is what grants access — none of the three alone does anything.
4. Federating to an existing corporate IdP is preferred over Identity Center's built-in directory wherever one exists.
5. Centralization is a deliberate trade-off — eliminates sprawl and simplifies offboarding, but concentrates risk into Identity Center and its IdP, which must be the highest-priority security surface.

## 🌐 Related Concepts (forward links)

- AWS Organizations structure, OUs, SCPs → §13
- CloudTrail monitoring of Identity Center admin actions and AssumeRole calls → Part 8
- Amazon Cognito for customer-facing identity → Part 10
