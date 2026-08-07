# Part 2 · Section 1 — IAM Core Concepts: Users, Groups, Roles, Policies

> AWS Zero-to-Enterprise Knowledge Base · Part 2: Identity, Security & Governance

---

## 1. Definition

**Plain-language:** IAM is AWS's system for deciding _who_ (a person, an application, another AWS service) is allowed to do _what_ (an action) to _which_ resource, and under what conditions.

**Precise:** **AWS IAM** is a **global, free** service providing **authentication** (verifying who you are) and **authorization** (verifying what you're allowed to do) for every request to AWS, via any interface.

> 💡 **Mental model:** IAM is the bouncer and the guest list combined — checks your ID (authentication), then checks which rooms you're allowed into (authorization), every single time, not just once at the door.

---

## 2. Why It Exists

- Root can't be safely scoped down ([§4](../Part1/Section-04-Part1-AWS-Accounts-Root-User-Identity-Basics.md)); IAM lets you create identities with exactly the permissions a task requires — least privilege in practice.
- Without IAM, access is all-or-nothing. Real orgs need graduated, precise, revocable access (DBA ≠ billing analyst ≠ CI/CD pipeline).
- IAM also provides identity for non-human actors (EC2, Lambda, other AWS accounts) without a human typing a password.

> 🔑 IAM is the substrate every AWS interaction runs through — every API call, every interface, is authenticated/authorized by IAM first.

---

## 3. IAM Terminology

- **Principal** — any entity that can make a request: IAM user, IAM role (assumed), or an AWS service. Root is also a principal, but unrestricted.
- **Authentication** — proving who you are.
- **Authorization** — determining what an authenticated principal can do, per attached policies.
- **Resource** — the thing acted upon; identified by an **ARN**.
- **Action** — the specific operation, `service:Action` format (e.g., `s3:GetObject`).
- **Policy** — JSON document defining allow/deny permissions, optionally with conditions.
- **ARN** — globally unique resource ID: `arn:partition:service:region:account-id:resource`.

**Example ARNs:**

```
arn:aws:s3:::my-app-logs-bucket
```

(region/account blank — S3 bucket names are globally unique)

```
arn:aws:ec2:us-east-1:123456789012:instance/i-0abcd1234efgh5678
```

(region + account populated — EC2 is regional/zonal)

> 🎯 Being able to read/construct an ARN and explain why fields are blank for some services signals real hands-on experience.

---

## 4. IAM Users

### 4.1 Definition

A persistent identity representing a person or app, with its own name and long-term credentials.

### 4.2 What a User Has

Name (unique in account); optional password (Console); optional access keys (CLI/SDK/API); permissions (direct or via groups); optional MFA.

### 4.3 Legacy Pattern Status

- Long-lived credentials are a standing risk — a leaked key stays valid until manually revoked.
- Modern guidance favors **roles with temporary credentials** (IAM Identity Center for humans, attached roles for compute).
- Still legitimate for: break-glass scenarios, legacy apps that can't assume roles, small accounts/labs. Rotate/monitor keys regardless.

### 4.4 Best Practices

1. One IAM user per human/app — never share credentials (destroys audit traceability).
2. Enforce MFA on every Console-access user.
3. Avoid creating access keys unless necessary; rotate regularly; remove unused.
4. Never embed access keys in code.
5. Prefer group-based permission assignment over direct attachment.

---

## 5. IAM Groups

### 5.1 Definition

A named collection of IAM users; policies attached to the group apply to every member.

### 5.2 Why It Exists

Avoids attaching/updating the same policy across many individual users — one attachment, freely add/remove members.

### 5.3 Key Characteristics

- **Not a true identity** — cannot be a principal, cannot log in, cannot be assumed. Purely organizational.
- **Cannot be nested** (commonly tested limitation).
- A user can belong to multiple groups, inheriting the union of permissions.

> ⚠️ Don't assume groups nest or can be role-assumed — neither is true.

### 5.4 Best Practices

- Organize by job function (`Developers`, `Billing-ReadOnly`, `DBAdmins`).
- Attach AWS managed policies for standard functions; layer custom policies only where org-specific.

---

## 6. IAM Roles

### 6.1 Definition

An identity with a set of permissions, **not permanently tied** to one person/app — assumed temporarily by a trusted principal, which receives short-lived, auto-expiring credentials.

### 6.2 Roles vs Users

|                     | IAM User                     | IAM Role                                            |
| ------------------- | ---------------------------- | --------------------------------------------------- |
| Credential lifetime | Long-lived                   | Short-lived, auto-expires                           |
| Tied to             | One person/app permanently   | Assumed temporarily by any trusted principal        |
| Who can use it      | Only that user's credentials | Anyone the trust policy allows                      |
| Typical use         | Legacy/break-glass           | Modern default for humans (federation) and services |

> 🔑 A role has no permanent credentials — only permissions + a trust policy. STS issues temporary credentials (access key, secret, session token) that auto-expire when assumed. (Full STS mechanics: Section 3.)

### 6.3 Two Policies on Every Role

1. **Trust policy** — resource-based, on the role itself; specifies who can call `sts:AssumeRole`.
2. **Permissions policy** — identity-based; defines what the role can do once assumed.

> 🎯 Trust policy = "who can become this role" (checked at assumption). Permissions policy = "what can this role do" (checked at every subsequent action).

### 6.4 Common Role Use Cases

1. **Service roles** — AWS service (EC2, Lambda) assumes a role to act on your behalf (e.g., EC2 reading S3 with no stored keys).
2. **Cross-account access** — role in Account B trusts Account A; A's users assume it without a separate IAM user in B.
3. **Federation** — human authenticates via SAML/OIDC or IAM Identity Center, assumes a role instead of a standing user (Section 4).
4. **Web/mobile app federation (Cognito)** — app end users authenticate via a third-party IdP, assume a scoped role directly.

### 6.5 Production/Enterprise Usage

- Roles are the default for virtually all non-human access.
- Roles increasingly default for human access too, via IAM Identity Center/SSO federation.

---

## 7. IAM Policies

### 7.1 Definition

A JSON document defining allowed/denied actions on resources, optionally under conditions.

### 7.2 Policy Structure

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "AllowS3ReadOnlySpecificBucket",
      "Effect": "Allow",
      "Action": ["s3:GetObject", "s3:ListBucket"],
      "Resource": [
        "arn:aws:s3:::my-app-logs-bucket",
        "arn:aws:s3:::my-app-logs-bucket/*"
      ],
      "Condition": {
        "IpAddress": { "aws:SourceIp": "203.0.113.0/24" }
      }
    }
  ]
}
```

- `Version` — always `"2012-10-17"` for new policies.
- `Statement` — array of one or more permission statements.
- `Sid` — optional human-readable label, no functional effect.
- `Effect` — `"Allow"` or `"Deny"`; explicit Deny always wins (Section 2).
- `Action` — `service:Action`, supports wildcards.
- `Resource` — target ARN(s), supports wildcards; some actions require `"Resource": "*"`.
- `Condition` (optional) — extra constraints (IP, time, MFA, tags) — where fine-grained control lives.

### 7.3 Policy Types

| Type                 | Attached to               | Managed by               | Example                                                                      |
| -------------------- | ------------------------- | ------------------------ | ---------------------------------------------------------------------------- |
| AWS managed          | Users/groups/roles        | AWS                      | `AmazonS3ReadOnlyAccess`                                                     |
| Customer managed     | Users/groups/roles        | You                      | Custom app-scoped policy                                                     |
| Inline               | A single user/group/role  | You                      | One-off, non-reusable policy                                                 |
| Resource-based       | The resource itself       | You                      | S3 bucket policy, role trust policy                                          |
| Permissions boundary | A user/role, as ceiling   | You                      | Caps max permissions regardless of other policies                            |
| SCP                  | Org OU/account            | You (management account) | Org-wide guardrail ([§13](./Section-13-Part2-AWS-Organizations-and-SCPs.md)) |
| Session policy       | Passed at role-assumption | You                      | Further restricts a single session                                           |

> 🔑 **Identity-based** policies attach to a principal ("what can this identity do?"). **Resource-based** policies attach to a resource ("who can access this, and how?"). Both evaluated together — underpins cross-account access.

### 7.4 Managed vs Inline

- Prefer managed (AWS or customer) — reusable, versioned, centrally auditable.
- Use inline sparingly, only for permissions permanently coupled to one identity's unique purpose.

---

## 8. How a Request Gets Evaluated (preview)

IAM gathers every applicable policy — identity-based, resource-based, permissions boundary, SCP, session policy — and evaluates them together for one Allow/Deny decision. Full evaluation logic (explicit deny wins, default deny, layer combination) is **Section 2's** entire subject.

---

## 9. Hands-On Example

**Beginner:** attach `AmazonS3ReadOnlyAccess` (AWS managed) directly to an IAM user.

**Intermediate:** create a customer-managed policy scoped to one bucket, attach to a `LogViewers` group, add users to the group.

**Production-grade:** IAM role with a trust policy allowing only the CI/CD pipeline's specific role to assume it, a permissions policy scoped to an exact S3 prefix + DynamoDB table, a permissions boundary as a hard ceiling, and a Condition requiring the request from a known CI/CD IP range.

---

## 10. Security Considerations

- Least privilege is the organizing principle — start at zero, add exactly what's needed (narrowing later is harder and riskier).
- **IAM Access Analyzer** identifies externally-shared resources and can generate least-privilege policies from observed access.
- Leaked credentials remain the top real-world IAM risk — abused by automated scanners within minutes of public exposure.

---

## 11. Performance & Monitoring

- IAM adds negligible latency — evaluation is part of the request path, not a slow separate lookup.
- **CloudTrail** logs every IAM-relevant event (AssumeRole calls, policy changes, auth attempts) — fully auditable (Part 8 full detail).

---

## 12. Troubleshooting

| Symptom                                         | Cause                                                                 | Fix                                            |
| ----------------------------------------------- | --------------------------------------------------------------------- | ---------------------------------------------- |
| AccessDenied despite policy seeming to allow it | An explicit Deny elsewhere (SCP, boundary, resource policy) overrides | Check all applicable policy layers (Section 2) |
| User can't assume a role                        | Trust policy missing that principal                                   | Add correct principal ARN to trust policy      |
| Policy change doesn't seem to apply             | IAM is eventually consistent                                          | Wait briefly and retry                         |
| Group permissions not applying                  | User not actually in group, or group has no policies                  | Verify membership and attached policies        |

---

## 13. Best Practices & Anti-Patterns

**Best practices:** prefer roles over users for nearly everything; use groups not per-user inline policies; least privilege as default; customer-managed over inline for reusable permissions; universal MFA for humans.

**Anti-patterns:** broad `AdministratorAccess` "to avoid headaches"; sharing user credentials across people; long-lived keys for compute that could use a role; assuming groups nest (they don't).

---

## 14. Common Misconceptions

- "A group is a special kind of user." → False — not a principal at all.
- "Roles are only for AWS services." → False — increasingly primary for humans via federation.
- "More permissions = fewer tickets, so be generous." → False — inflates blast radius; least privilege pays off the first leak.
- "IAM changes take effect instantly everywhere." → Mostly, but eventually consistent — don't panic-debug immediately after a change.

---

## 15. Interview Questions (with model answers)

**🟢 IAM user vs IAM role?** User = persistent identity, long-lived credentials, tied to one person/app. Role = no permanent credentials, temporarily assumed, STS issues short-lived auto-expiring credentials. Roles are the modern default for services and increasingly humans via federation.

**🟢 Can IAM groups be nested?** No. A group is purely a policy-attachment collection, not a principal, and can't contain another group. Layer permissions via multiple group memberships or role-based patterns instead.

**🟡 The two policies on every role — why separate?** Trust policy (resource-based) = who can assume it, checked at `sts:AssumeRole`. Permissions policy (identity-based) = what it can do once assumed, checked on every action. Separation lets you independently control "who becomes this identity" and "what that identity can do."

**🟡 Identity-based vs resource-based policy — when to use each?** Identity-based attaches to a principal, defines what it can do. Resource-based attaches to a resource (bucket policy, trust policy), defines who can access it. Resource-based is the canonical tool for cross-account access — grants access to another account's principal without creating an identity for them locally.

**🔴 Design IAM for a CI/CD pipeline deploying to prod S3/DynamoDB, minimizing compromise risk?** Avoid IAM users/long-lived keys — use OIDC federation so the pipeline assumes a role with a short-lived per-run token, no static secret. Permissions policy scoped to exact S3 prefix + DynamoDB table. Permissions boundary as a hard ceiling. Condition requiring the expected OIDC subject/audience. CloudTrail capturing every AssumeRole and subsequent action for visibility.

**🔴 Audit finds dozens of users with AdministratorAccess directly attached — remediate and prevent recurrence?** Remediate: use Access Analyzer + CloudTrail activity data to see actual usage, replace with least-privilege customer-managed policies or move to role-based access via IAM Identity Center, retire standing users. Prevent: SCP denying direct attachment of AdministratorAccess-type policies to users org-wide, forcing role assumption instead; SCP requiring permissions boundaries org-wide. Track as a recurring Security Hub/Trusted Advisor finding to catch drift automatically.

---

## 🔑 Key Takeaways

1. IAM authenticates and authorizes every AWS request across every interface — the substrate, not a bolt-on.
2. Users = long-lived credentials tied to one identity; roles = temporarily assumed, short-lived STS credentials — roles are the modern default.
3. Groups are user collections for policy attachment at scale — not principals, cannot be nested.
4. Every role has a trust policy (who can assume it) and a permissions policy (what it can do) — evaluated at different times.
5. Policy types (managed, inline, resource-based, permissions boundary, SCP, session) exist, with identity-based vs resource-based as the most fundamental distinction underpinning cross-account access.

## 🌐 Related Concepts (forward links)

- Full policy evaluation logic → [§10](./Section-10-Part2-IAM-Policy-Evaluation-Logic.md)
- STS mechanics and trust-policy deep dive → [§11](./Section-11-Part2-IAM-Roles-Trust-Policies-STS.md)
- IAM Identity Center and federation → [§12](./Section-12-Part2-IAM-Identity-Center-SSO-Federation.md)
- Service Control Policies → [§13](./Section-13-Part2-AWS-Organizations-and-SCPs.md)
