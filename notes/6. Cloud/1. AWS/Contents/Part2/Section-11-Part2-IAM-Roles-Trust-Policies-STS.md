# Part 2 · Section 3 — IAM Roles, Trust Policies & Temporary Credentials (STS)

> AWS Zero-to-Enterprise Knowledge Base · Part 2: Identity, Security & Governance

---

## 1. Definition

**Plain-language:** STS hands out temporary, self-expiring keys to anyone/anything allowed to assume a role — a wristband good for the next hour, then it stops working.

**Precise:** **AWS Security Token Service (STS)** is a global (with regional endpoints), free service issuing **temporary security credentials** (access key ID, secret access key, session token) to principals who assume an IAM role or federate into AWS, valid for a configurable bounded duration.

---

## 2. Why It Exists

- Roles have no permanent credentials — STS is the mechanism that manufactures usable temporary credentials the instant a role is assumed, and invalidates them automatically at expiration.
- Core security property: a leaked temporary credential has a built-in expiration, unlike a leaked long-lived IAM user key (valid until manually revoked).
- STS underlies every flavor of "temporary access": service roles, cross-account access, federation, web identity federation — all just different `Assume*` API calls.

---

## 3. STS API Actions

| API action                  | Purpose                                                           | Typical caller                           |
| --------------------------- | ----------------------------------------------------------------- | ---------------------------------------- |
| `AssumeRole`                | Standard role assumption, same or cross-account                   | IAM user or role assuming another role   |
| `AssumeRoleWithSAML`        | Assume via SAML 2.0 assertion from a corporate IdP                | Federated humans via SAML                |
| `AssumeRoleWithWebIdentity` | Assume via an OIDC/web identity token                             | App end users, OIDC-federated CI/CD      |
| `GetSessionToken`           | Temp credentials for the calling IAM user itself                  | IAM user needing MFA-protected API calls |
| `GetFederationToken`        | Temp credentials for a federated user, no underlying IAM identity | Legacy custom federation brokers         |
| `GetCallerIdentity`         | Returns account/ARN/user ID of current credentials                | Anyone debugging "which identity am I"   |

> 🎯 `aws sts get-caller-identity` is the standard first diagnostic command when access behaves unexpectedly.

---

## 4. Temporary Credential Set

1. **Access Key ID** — `ASIA...` prefix (temporary) vs `AKIA...` (long-lived IAM user).
2. **Secret Access Key** — used with the access key for SigV4 signing.
3. **Session Token** — required in every signed request with temp credentials; absent from permanent-key requests.
4. **Expiration** — timestamp after which credentials stop working entirely.

> ⚠️ Forgetting `AWS_SESSION_TOKEN` alongside access key/secret when manually configuring temp credentials causes auth failures.

---

## 5. Session Duration

- Configurable per role, bounded by the role's **maximum session duration** (commonly as low as 15 min up to 12 hours for `AssumeRole`, depending on configuration).
- Caller can request shorter than the max, never longer.
- Trade-off: shorter duration = smaller blast radius but more frequent re-assumption. Sensitive roles (e.g., prod DB) often capped 15–30 min; routine CI/CD roles may use hours.

> ⚠️ Exact bounds vary by assumption method (console switch-role vs programmatic vs federation) — verify current docs.

---

## 6. Trust Policies — Full Mechanics

### 6.1 Structure

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": { "AWS": "arn:aws:iam::111122223333:root" },
      "Action": "sts:AssumeRole",
      "Condition": {
        "StringEquals": { "sts:ExternalId": "unique-shared-secret-123" }
      }
    }
  ]
}
```

- **`Principal`** — who is trusted; distinguishes a trust policy from a normal identity policy.
  - `{"AWS": "...:root"}` — trusts an entire account (both sides still need to agree, §6.2).
  - `{"AWS": "...:user/Alice"}` — trusts one specific user.
  - `{"Service": "ec2.amazonaws.com"}` — trusts an AWS service (service roles).
  - `{"Federated": "...:saml-provider/CorpSSO"}` — trusts a SAML IdP.
- **`Action`** — usually `sts:AssumeRole` (or `AssumeRoleWithSAML`/`AssumeRoleWithWebIdentity` for federation).
- **`Condition`** — often `sts:ExternalId` for third-party cross-account access (§7.2).

### 6.2 Both Sides Must Agree

For Account A's user to assume a role in Account B:

1. **Account B's trust policy** must include Account A (or the specific principal).
2. **Account A's own identity policy** must also grant `sts:AssumeRole` on that role's ARN in Account B.

> 🔑 Cross-account access requires permission from **both directions**. Missing either side → denial. This is the classic "why does cross-account access fail" scenario.

---

## 7. Cross-Account Access — Full Pattern

### 7.1 Standard Pattern

1. Account B creates a role trusting Account A.
2. Account B attaches a permissions policy defining what the role can do in B.
3. A principal in Account A calls `sts:AssumeRole` on that role's ARN (needs A's own permission too).
4. STS returns temp credentials scoped to B's role permissions.
5. The Account A principal operates as that role, inside Account B, for the session.

### 7.2 Confused Deputy Problem & External ID

- **Problem:** if Account B's role broadly trusts "any principal from vendor X," and vendor X serves many customers, an attacker could trick the vendor into assuming a role meant for a _different_ customer — the vendor becomes an unwitting confused deputy.
- **Solution:** `sts:ExternalId` condition requires a pre-shared secret value with the AssumeRole call; only the legitimate customer relationship knows it.
- **Where seen:** virtually every reputable third-party SaaS needing cross-account access (monitoring, security scanners, CI/CD). A vendor NOT requiring an External ID is a security red flag.

> 🎯 "What is External ID for?" tests real production-pattern understanding, not just syntax.

---

## 8. Service Roles — Full Mechanics

- Trust policy names an **AWS service** (`ec2.amazonaws.com`, `lambda.amazonaws.com`) as trusted principal, letting that service assume the role on your behalf.
- **Instance profiles (EC2):** EC2 attaches an **instance profile**, a thin wrapper holding exactly one IAM role. The Console creates this automatically when you "attach a role to an instance."
- **Credential retrieval:** the application queries the **Instance Metadata Service (IMDS)** at a well-known local address for the role's current temp credentials; the SDK does this automatically as part of its credential chain.
- **IMDSv2:** hardened, session-token-based version of IMDS, mitigating **SSRF** attacks that could otherwise leak instance credentials. Enforcing IMDSv2-only is a modern security baseline.

---

## 9. Web Identity Federation & Amazon Cognito (preview)

- **Web Identity Federation** — app end users authenticate with a third-party IdP (Google, Facebook, OIDC), receive a token, app calls `AssumeRoleWithWebIdentity` for scoped temp AWS credentials — no IAM user per end user, no AWS-visible login credentials.
- **Amazon Cognito** — AWS's managed service handling this flow (user pools for auth, identity pools for AWS credentials) instead of building raw STS federation by hand.

---

## 10. OIDC Federation for CI/CD

- CI/CD platforms (GitHub Actions, GitLab CI) can act as OIDC identity providers, letting a pipeline call `AssumeRoleWithWebIdentity` with a short-lived, per-run token.
- Eliminates storing **any** long-lived AWS credential as a CI/CD secret — historically a major leak vector.
- **Setup:** register the CI/CD platform as an OIDC provider in IAM; trust policy validates issuer + specific claims (exact repo/branch), so only your pipeline can assume the role.

---

## 11. Production & Enterprise Usage

- **Role chaining:** a role assuming another role (a role, once assumed, is just another principal). Common in hub-and-spoke multi-account designs. Chained sessions are generally capped shorter than direct ones — a real constraint.
- **Switch Role (Console):** lets a logged-in user assume a role in another account/same account via the UI, using the same trust-policy mechanics — common for admins managing multiple accounts.
- **Break-glass roles:** purpose-built, normally unassumable roles for genuine emergencies, gated behind approval workflows, heavily alerted via CloudTrail on use.

---

## 12. Security Considerations

- Session tokens must be protected as carefully as credentials while active — a stolen token is fully usable until expiration.
- External ID is a shared value mitigating confused-deputy, not a cryptographic secret/primary authentication.
- IMDSv2 enforcement closes a real, historically-exploited SSRF credential-theft vector — "IMDSv1 still enabled" is a genuine finding to remediate.
- Monitor `AssumeRole` calls via CloudTrail — unexpected source IP/time/principal is a strong alert signal.

---

## 13. Troubleshooting

| Symptom                                                  | Cause                                                                      | Fix                                                      |
| -------------------------------------------------------- | -------------------------------------------------------------------------- | -------------------------------------------------------- |
| AccessDenied calling AssumeRole                          | Missing permission on either side (source identity or target trust policy) | Check both directions (§6.2)                             |
| Credentials work then suddenly fail mid-task             | Session expired                                                            | Re-assume; consider a longer max duration if appropriate |
| Manually-configured temp creds fail auth entirely        | Missing AWS_SESSION_TOKEN                                                  | Set all three values together                            |
| Vendor cross-account assumption fails/flagged suspicious | Missing/incorrect sts:ExternalId                                           | Confirm exact, correctly-cased External ID               |
| Instance app can't retrieve IMDS credentials             | IMDSv2 enforced, app/SDK doesn't support token-based flow                  | Update SDK/app rather than disabling the control         |

---

## 14. Best Practices & Anti-Patterns

**Best practices:** shortest practical session duration; always require External ID for third-party cross-account roles; use OIDC federation for CI/CD instead of static credentials; enforce IMDSv2 on all EC2; alert on unexpected AssumeRole activity; use `get-caller-identity` as first diagnostic.

**Anti-patterns:** granting `sts:AssumeRole` with `"Resource": "*"`; cross-account trust for a third party without External ID; leaving IMDSv1 enabled when v2 is available; static AWS keys as CI/CD secrets when OIDC is supported.

---

## 15. Common Misconceptions

- "Trusting an account in a trust policy is enough." → False — source account's identity policy must also permit the call (§6.2).
- "External ID authenticates the caller." → Not quite — it's a confused-deputy mitigation/scoping safeguard, not primary authentication (that's the caller's own AWS credentials).
- "EC2 role credentials are static." → False — temporary STS credentials, auto-retrieved/refreshed via IMDS.
- "Longer sessions are always free convenience." → Each additional hour is more blast-radius time if compromised — a deliberate trade-off.

---

## 16. Interview Questions (with model answers)

**🟢 What does STS do?** Issues temporary credentials (access key, secret, session token) with bounded expiration whenever a principal assumes a role or federates. Makes roles have no permanent credentials of their own — every "assumption" is really an STS `Assume*` call.

**🟢 What's External ID for?** Shared value required in the AssumeRole call, mainly for third-party vendors serving many customers — prevents the confused-deputy problem where the vendor might be tricked into assuming a role meant for a different customer.

**🟡 User in Account A can't assume a role in Account B despite trust policy listing A — why?** Trust policies are one direction. Account A's own identity policy must also grant `sts:AssumeRole` on that specific role ARN in Account B. Both sides must agree; missing source-side permission is the common cause.

**🟡 How does an EC2 app actually get its role's credentials?** Instance profile wraps the IAM role; SDK queries the local Instance Metadata Service for temp STS credentials, auto-refreshed before expiry — app never sees a static permanent credential. IMDSv2 enforces session-token-based requests to prevent SSRF-based credential theft.

**🔴 Design secure access for a third-party monitoring SaaS to read-only CloudWatch metrics?** Role in my account trusting the vendor's specific account, requiring a unique `sts:ExternalId` from the vendor to prevent confused-deputy risk. Permissions policy strictly scoped to read-only CloudWatch, nothing else. Never issue a long-lived IAM user key. Set a reasonable max session duration; monitor AssumeRole via CloudTrail, alert on unexpected source.

**🔴 Trade-offs of role chaining in multi-account architecture — when to avoid?** Useful for hub-and-spoke designs (central role assumes scoped roles in spoke accounts without every spoke trusting every caller directly). Trade-offs: chained sessions capped shorter than direct assumption, complicating long-running automation; adds audit indirection (must trace multiple AssumeRole events in CloudTrail). Avoid deep chains (>2 hops) without genuine architectural reason; ensure CloudTrail session context is preserved end-to-end.

---

## 🔑 Key Takeaways

1. STS is the engine behind every role assumption — issues temp access key/secret/session token with bounded expiration, making roles safer than long-lived credentials.
2. Cross-account access requires agreement from both sides — target's trust policy AND source's own identity policy permitting AssumeRole.
3. External ID solves the confused-deputy problem for third-party cross-account access — required practice for vendor relationships.
4. Service roles use instance profiles + IMDS for auto-rotating credentials — IMDSv2 is the modern SSRF-resistant standard.
5. OIDC federation for CI/CD eliminates static long-lived credentials as pipeline secrets — the modern best practice.

## 🌐 Related Concepts (forward links)

- IAM Identity Center and SAML/OIDC federation for humans → [§12](./Section-12-Part2-IAM-Identity-Center-SSO-Federation.md)
- SCPs interacting with cross-account role assumption → [§13](./Section-13-Part2-AWS-Organizations-and-SCPs.md)
- CloudTrail monitoring of AssumeRole events → Part 8
- EC2 instance profiles and IMDSv2 configuration in depth → Part 3
