# Part 1 · Section 4 — AWS Accounts, Root User & Identity Basics

> AWS Zero-to-Enterprise Knowledge Base · Part 1: Foundations & Global Infrastructure

---

## 1. Definition

**Plain-language:** An AWS account is your own private, isolated space within AWS. Everything you create lives inside it, everything you're billed for is tied to it, and you control who else can act inside it.

**Precise:** An **AWS account** is the fundamental **container and billing/security boundary** in AWS — a unique namespace for resources, a single consolidated bill, and a trust boundary IAM identities/permissions operate within by default.

> 💡 **Mental model:** An account is like a country — its own currency (billing), its own citizenship registry (IAM users/roles), its own borders (resource isolation). Resources in one account are invisible to another unless a bridge (cross-account access) is explicitly built.

---

## 2. Why It Exists

- **Isolation:** multi-tenancy means many customers share physical infra; accounts keep Customer A's resources invisible/inaccessible to Customer B by default — the fundamental blast-radius boundary.
- **Billing separation:** all usage rolls up to exactly one account → clean, attributable billing.
- **Security boundary:** nothing crosses an account boundary by default; cross-account access must be explicit and auditable.

> 🔑 The account is the **strongest** security boundary — stronger than any IAM policy, since IAM lives inside an account. Multi-account strategy (Organizations, Part 2) is a top-rated security practice.

---

## 3. Creating an Account — What Happens

Sign-up requires email, password, account name, payment info, identity verification. Creates:

1. **12-digit Account ID** (e.g., `123456789012`) — permanent unique identifier used in ARNs and cross-account trust.
2. **The Root User** — tied to sign-up email (see §4).
3. **Free Tier eligibility window** for new accounts (§6).

> ⚠️ Free Tier specifics change over time — verify on the AWS pricing page.

---

## 4. The Root User

### 4.1 Definition

Automatically created identity, identified by account sign-up **email + password**, with **complete, unrestricted access** to everything — no permission it lacks.

### 4.2 Why Dangerous

Unlimited power, no guardrails → highest-value attacker target. Unlike IAM identities, **root's permissions cannot be restricted by policy**.

### 4.3 Root-Only Actions

- Change root **email/password**.
- **Close the AWS account**.
- Change the **AWS Support plan**.
- Restore IAM access if the **only administrator locks themselves out**.
- Certain one-time actions (activating IAM access to Billing Console, some sandbox-removal requests, GovCloud sign-up, other legacy settings).

> 🎯 Mental model: root = account-level, one-time admin tasks AWS deliberately withholds from IAM — not for daily work.

### 4.4 Root Best Practices

1. **Never use root for daily tasks** — create an admin IAM identity immediately (ideally via IAM Identity Center).
2. **Enable MFA on root immediately** — hardware key or authenticator app, not SMS.
3. **Do not create root access keys**; delete any that exist.
4. **Strong unique password**, stored securely and separately from daily credentials.
5. **Keep recovery email/phone current** — last line of account recovery.
6. **Lock down root in every member account**, not just the management account.
7. **Monitor root usage via CloudTrail**; alert on any root activity.

> ⚠️ Every individual account (including auto-created ones in an Organization) has its **own separate root user** needing securing.

---

## 5. IAM — First Look (full depth Part 2)

- **IAM users** — individual identities with own credentials (modern best practice favors IAM Identity Center federation over long-lived users).
- **IAM roles** — temporary identities anyone/anything can _assume_ for limited-time permissions; the modern default for human and service-to-service access.
- **IAM policies** — JSON documents defining allowed/denied actions; the mechanism for giving less power than root (least privilege).
- **MFA** — second proof of identity beyond password; mandatory on root, strongly encouraged everywhere.

> 💡 IAM exists precisely so you never need root for daily work.

---

## 6. AWS Free Tier

- Lets new/all accounts try services at no/reduced cost.
- **Always-free** — capped monthly usage, indefinitely, every account.
- **12-months-free** — larger allowances on core services, first 12 months only.
- **Short-term trials** — limited-time allowance from first use of a specific service.

> ⚠️ Free Tier ≠ "can't be charged." Exceeding allowances, using non-covered services, or running past the trial window bills you. Set up billing alarms.

---

## 7. Account Structure — Multi-Account Preview (full depth Part 2)

- Enterprises separate accounts **per environment** (dev/staging/prod) and/or **per team/business unit** for blast-radius containment.
- **AWS Organizations** — central management: consolidated billing, Service Control Policies (guardrails), delegated permissions.
- **Management account** sits atop an Organization with special (root-adjacent) org-level privileges; also must be tightly secured.

> 🔑 "One account for everything" = beginner pattern. "Many purpose-scoped accounts under an Organization" = enterprise pattern.

---

## 8. Production & Enterprise Usage

- **Root as break-glass identity** — secured, rarely touched, monitored, used only for root-only actions.
- **Centralized identity federation** — IAM Identity Center or external IdP (Okta/Azure AD via SAML); employees log in once, assume roles across accounts.
- **Account vending** — AWS Control Tower automates creation of new, pre-secured accounts (root locked, guardrails applied, logging on).
- **Billing consolidation** — Organizations' consolidated billing rolls up usage into one bill (often volume discounts) with per-account attribution.

---

## 9. Security Considerations

- **Root compromise = total account compromise** — no policy limits it; root protection is priority one on a new account.
- **CloudTrail logging essential** — alert on any root login/API call.
- **Root access keys** are especially dangerous and rarely needed — don't create them.
- **Multi-account blast-radius design** is itself a security control.

---

## 10. Troubleshooting

| Symptom                                | Cause                                                           | Fix                                                                                         |
| -------------------------------------- | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Locked out of root                     | No backup MFA / stale recovery contact                          | Use AWS account recovery via registered email; keep contacts current                        |
| Unexpected charges despite "Free Tier" | Exceeded allowance / non-covered service / past 12-month window | Check Billing/Cost Explorer; set billing alarms; verify current terms                       |
| Admin locked themselves out            | Over-restrictive policy on the only admin identity              | Use root's unique recovery power to restore access; avoid single-admin setups               |
| Unexplained periodic root logins       | Root creds known/used by more than intended, or compromised     | Rotate password, check CloudTrail, ensure no access keys exist, restrict knowledge of creds |

---

## 11. Best Practices & Anti-Patterns

**Best practices:** secure root (MFA, no access keys, strong password) immediately; create an admin IAM identity right away; treat root as break-glass; move to multi-account under Organizations as usage grows; monitor root usage via CloudTrail.

**Anti-patterns:** using root for everyday logins/scripts; leaving active root access keys; sharing root credentials across a team; assuming Free Tier prevents charges; securing root only in the management account.

---

## 12. Common Misconceptions

- "Root is just a more powerful admin user." → False — has permissions no IAM identity can ever hold, and can't be policy-restricted.
- "I need root for most AWS work." → False — daily work, even full admin work, should use IAM/federated identities.
- "Free Tier means I can't be charged." → False.
- "Deleting root access keys removes root's power." → False — only removes programmatic access; console/password access remains fully powerful.

---

## 13. Interview Questions (with model answers)

**🟢 What is the root user, and why risky?** Auto-created identity tied to sign-up email/password with unrestricted, non-policy-limitable access — a high-value target. Secure with MFA, no access keys; use IAM for everyday work.

**🟢 What can only root do?** Change root email/password, close the account, change Support plan, restore a locked-out sole admin, a few legacy/recovery actions. Everything else (incl. full admin work) → IAM identity.

**🟡 Why multiple AWS accounts?** Account boundary is the strongest isolation mechanism — resources, IAM, root all scoped per account. Multi-account (via Organizations) contains blast radius, gives clean cost attribution, and enables different guardrails (stricter prod vs dev) via SCPs.

**🟡 Junior wants to use root to move faster — response?** Root's power is exactly the problem — can't be scoped down, so any mistake/leak has account-wide blast radius. Give them a least-privilege IAM role/federated identity instead — safer and just as fast day to day; root stays for the handful of root-only actions.

**🔴 Audit root security across a 50-account Organization?** Per account check: root MFA enabled, no root access keys, CloudTrail enabled/alerting on root activity. At scale, use Config rules or Security Hub controls to continuously evaluate root MFA/access-key status org-wide, route root login events through monitored alerting, and verify recovery contact info is current.

---

## 🔑 Key Takeaways

1. An AWS account is the fundamental billing/isolation/security boundary — stronger than any IAM policy.
2. Root is created automatically, has unrestricted non-restrictable access — secure it (MFA, no access keys) then reserve it for root-only actions.
3. IAM exists so you never need root for daily work — create an admin identity immediately after account creation.
4. Free Tier reduces learning risk but doesn't eliminate charges — monitor usage.
5. Production/enterprise AWS moves toward multi-account structure under Organizations, using the account boundary as a security control.

## 🌐 Related Concepts (forward links)

- IAM users, roles, policies, IAM Identity Center, Organizations, SCPs → Part 2
- CloudTrail logging of root/API activity → Part 8
- Consolidated billing, Cost Explorer, Budgets → Section 6 (next), Part 10 FinOps
