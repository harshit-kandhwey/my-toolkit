# Part 2 · Section 10 — Part 2 Wrap-Up + Security & Governance Interview Drill

> AWS Zero-to-Enterprise Knowledge Base · Part 2: Identity, Security & Governance (Final Section)

---

## 1. Part 2 Consolidated Knowledge Map

```
                    IDENTITY, SECURITY & GOVERNANCE (Part 2)
                                     │
   ┌───────────────┬─────────────────┼─────────────────┬───────────────┐
   │               │                 │                  │               │
§1 IAM Core     §2 Policy         §3 Roles/STS      §4 Identity     §5 Organizations
Users/Groups/   Evaluation        Trust policies,    Center          & SCPs
Roles/Policies  Logic             temp credentials,  SSO across      Multi-account
                Deny-wins,        cross-account,     the             structure,
                default-deny      OIDC federation    Organization    ceiling policies
                                     │
                    ┌────────────────┼────────────────┐
                 §6 KMS &       §7 Secrets         §8 Detection    §9 Edge Security
                 Encryption     Manager &          GuardDuty,      WAF, Shield,
                 Data           Parameter          SecurityHub,    Network
                 protection     Store              Config,         Firewall
                 layer          Credential          Inspector
                                lifecycle
```

**Throughline:** [§1](../Part1/Section-01-Part1-What-is-AWS-and-Cloud-Computing-Fundamentals.md)–[§2](../Part1/Section-02-Part1-AWS-Global-Infrastructure.md) establish who can do what within an account. [§3](../Part1/Section-03-Part1-Shared-Responsibility-Model.md)–[§4](../Part1/Section-04-Part1-AWS-Accounts-Root-User-Identity-Basics.md) extend that across accounts and to humans at scale. [§5](../Part1/Section-05-Part1-Ways-to-Interact-with-AWS.md) provides the governing structure. [§6](../Part1/Section-06-Part1-AWS-Pricing-and-Cost-Fundamentals.md)–[§7](../Part1/Section-07-Part1-AWS-Support-Plans-and-Service-Category-Map.md) protect the data and credentials identities touch. [§8](../Part1/Section-08-Part1-Wrap-Up-and-Foundations-Interview-Drill.md) detects failures despite all of the above. [§9](./Section-09-Part2-IAM-Core-Concepts.md) stops bad traffic before it reaches anything else. Every section builds on the ones before it.

---

## 2. Consolidated Key-Takeaways Checklist

- [ ] State IAM's core purpose; distinguish authentication from authorization.
- [ ] Explain users vs groups vs roles; know groups cannot be nested.
- [ ] State both governing evaluation rules from memory: default deny, explicit deny always wins.
- [ ] Know which policy types grant (identity-based, resource-based) vs only restrict (SCP, permissions boundary, session policy).
- [ ] Explain STS and why temporary credentials are safer than long-lived ones.
- [ ] Describe a role's two policies (trust vs permissions); cross-account access needs agreement from both sides.
- [ ] Know what External ID solves (confused deputy) and when required.
- [ ] Explain IAM Identity Center and that Permission Sets are automated IAM roles.
- [ ] Know the management account is exempt from SCPs and should stay workload-free.
- [ ] Explain SCP inheritance down an OU tree and deny-list vs allow-list trade-off.
- [ ] Explain envelope encryption end-to-end; know a correct IAM policy alone isn't always enough for KMS.
- [ ] Know the Secrets Manager vs Parameter Store deciding factor (rotation); describe the four-step rotation process.
- [ ] Distinguish what GuardDuty, Config, Inspector, Security Hub each check.
- [ ] Distinguish WAF (application content) from Shield (DDoS/volumetric); know where Network Firewall fits.

---

## 3. Progressive Hands-On Labs — Part 2

### 🧪 Lab 1 (Beginner) — Least-Privilege IAM in Practice

1. Create an IAM group `LogViewers`.
2. Write a customer-managed policy granting `s3:GetObject`/`s3:ListBucket` on one specific test bucket only.
3. Attach to the group; add a test identity.
4. Confirm it can read that bucket but gets AccessDenied elsewhere/on writes.

_Success:_ a real, verified least-privilege policy.

### 🧪 Lab 2 (Beginner) — Explicit Deny Proof

1. Add a second statement with `"Effect": "Deny"` on `s3:GetObject` for one specific object key.
2. Confirm other objects remain readable, but that one object is denied despite the broader Allow.

_Success:_ hands-on proof explicit Deny overrides a broader Allow.

### 🧪 Lab 3 (Intermediate) — Assume a Role via STS

1. Create a role trusting your admin user, with read-only CloudWatch permissions.
2. `aws sts get-caller-identity` to confirm current identity.
3. `aws sts assume-role --role-arn <arn> --role-session-name test-session`; configure all three returned values as env vars.
4. `aws sts get-caller-identity` again — confirm it shows the assumed role.

_Success:_ manually walked through the role/STS mechanics.

### 🧪 Lab 4 (Intermediate) — Encrypt with a Customer Managed KMS Key

1. Create a CMK with a key policy granting your admin identity key-admin rights.
2. Create an S3 bucket with default encryption using that CMK.
3. Upload/verify encryption under the CMK.
4. Attempt access with a different identity (S3 permission, not in key policy) — confirm failure.

_Success:_ proof that S3 (IAM) Allow alone isn't sufficient without the KMS key policy also permitting access.

### 🧪 Lab 5 (Capstone) — Governance & Detection Readiness Review

1. Enable GuardDuty and AWS Config.
2. Enable Security Hub; review FSBP findings.
3. Extend the Part 1 account-health document with: SCP status, GuardDuty/Config/Security Hub enablement, IAM structure summary (users vs roles, Identity Center usage).
4. Note WAF/Shield status for any public-facing resource.

_Success:_ a materially more complete governance document, now covering identity, encryption, detection, and edge security.

---

## 4. Cross-Section Interview Drill

**🟢 How do a KMS key policy and an SCP both act as "ceilings," and how do they differ?**
Both restrict rather than grant — an SCP caps an entire account/OU regardless of in-account IAM; a KMS key policy gates one specific key and, unusually, is the _primary_ gate — an IAM Allow alone typically isn't sufficient without the key policy also permitting it. SCPs are org-wide governance; key policies are resource-specific access control behaving more strictly than most resources.

**🟢 Does Section 2's evaluation logic apply to an Identity Center Permission-Set-provisioned role?**
Yes, completely — it's a real IAM role under the hood, subject to the same default-deny/explicit-deny-wins evaluation, including any applicable SCPs. Identity Center automates role creation/assignment; it doesn't change how permissions are evaluated.

**🟡 A CI/CD pipeline (OIDC) needs a DB password from Secrets Manager to deploy to a KMS-encrypted RDS instance — what has to be configured?**
OIDC provider registered in IAM; target role's trust policy validates issuer/claims (repo/branch) so only the legitimate pipeline assumes it. Permissions policy needs `secretsmanager:GetSecretValue` scoped to the secret's ARN. The KMS key protecting that secret needs a key policy permitting this role to decrypt (IAM Allow alone insufficient). Any applicable SCP must not deny Secrets Manager/KMS actions. If RDS itself is separately KMS-encrypted, that's a distinct key policy check. Every layer — trust policy, permissions policy, key policy, SCP — must align.

**🔴 Design the complete security posture for a new regulated (healthcare) workload in a mature multi-account Organization.**
Dedicated member account(s) under a Production OU with an allow-list SCP restricting to needed services, inheriting org-wide guardrails (Deny disabling CloudTrail/GuardDuty/Config). Human access via IAM Identity Center federated to corporate IdP, Permission Sets by job function assigned to groups; no standalone users except a controlled break-glass role. Applications/services use IAM roles exclusively; CI/CD via OIDC. Data at rest encrypted with customer-managed KMS keys administered by a dedicated Security account, admin/user separation, automatic annual rotation. DB credentials in Secrets Manager with native rotation; non-rotating config in Parameter Store, hierarchical per environment. GuardDuty/Security Hub/Config/Inspector enabled org-wide via delegated administration, checking FSBP/CIS/relevant compliance standards, high-confidence findings auto-remediated. If internet-facing: CloudFront + validated WAF Managed Rule Groups; Shield Advanced justified given data sensitivity. Every control maps to a specific Part 2 section; none substitute for another — deliberately layered.

---

## 5. Related Technologies (forward links, consolidated)

| Concept touched in Part 2                                                                  | Fully covered in |
| ------------------------------------------------------------------------------------------ | ---------------- |
| CloudTrail, VPC Flow Logs (GuardDuty data sources); Systems Manager beyond Parameter Store | Part 8           |
| EventBridge-driven automated remediation                                                   | Part 7           |
| VPC, subnets, security groups, NACLs, Route 53, CloudFront, Network Firewall placement     | Part 4           |
| EC2 instance profiles, IMDSv2 configuration                                                | Part 3           |
| RDS/Aurora native Secrets Manager rotation integration                                     | Part 6           |
| Well-Architected Security pillar, formalizing this Part's principles                       | Part 10          |

---

## 6. Recommended Certification Alignment

- **AWS Certified Security – Specialty** — almost entirely a formalized test of Part 2's content.
- **Solutions Architect Associate** — draws heavily on Sections 1–2 (IAM), 5 (Organizations), 6 (KMS), alongside later Parts' compute/networking/storage content.

---

## 🔑 Part 2 — Final Consolidated Key Takeaways

1. IAM is the substrate everything runs through — users/groups/roles/policies combine via a strict deterministic algorithm: default deny, explicit deny always wins.
2. Roles and STS are how temporary, scoped access works — trust policies control who can assume, permissions policies control what it can do, cross-account access needs agreement from both sides.
3. IAM Identity Center and Organizations/SCPs scale the above to many humans and many accounts — Permission Sets are automated roles; SCPs are unbypassable ceilings the management account sits outside of.
4. KMS and secrets management protect data and credentials as an independent layer — envelope encryption keeps this fast; a KMS key's own policy is often the real access gate.
5. Detection and edge security close the loop — GuardDuty/Config/Inspector/Security Hub catch what prevention misses; WAF/Shield/Network Firewall stop bad traffic before arrival. No control in Part 2 substitutes for another — the whole Part is one continuous defense-in-depth argument.

---

## ✅ Part 2 Complete

All 10 sections of **Identity, Security & Governance** are done. Next: **Part 3 — Compute** (EC2, AMIs, instance families, purchasing models, Auto Scaling, ELB, Lambda, ECS, EKS, Fargate, Elastic Beanstalk, Batch, Lightsail).
