# Part 5 - Section 3 - S3 Security, Encryption & Access Control

AWS Zero-to-Enterprise Knowledge Base - Part 5: Storage

---

## 1. Definition

Plain-language: S3 gives you several layers of access control - who can do what to a bucket or object - plus encryption options for protecting data at rest and in transit. Understanding how these layers stack together (and which is the real safety net) is essential to avoiding classic S3 breach scenarios.

Precise: S3 access control combines IAM policies (Part 2), bucket policies (resource-based), Access Control Lists (ACLs, largely legacy), and the account/bucket-level S3 Block Public Access setting - evaluated together per standard policy-evaluation logic - alongside encryption at rest (SSE-S3, SSE-KMS, or SSE-C) and encryption in transit (TLS).

---

## 2. Why This Category Exists

- "Leaky S3 buckets" have been referenced throughout this course as the canonical customer-side Shared Responsibility Model failure - this section explains exactly which controls exist and which most commonly gets misconfigured.
- S3 access control evolved over time: ACLs (original) -> bucket policies (modern, IAM-policy-like) -> Block Public Access (safety net against both being misconfigured).

---

## 3. IAM Policies vs Bucket Policies

- IAM policies (identity-based) attach to a user/group/role, defining what that principal can do, including to S3 resources via s3: actions and ARNs.
- Bucket policies (resource-based) attach to the bucket itself, defining who can access it - exactly the mechanism enabling cross-account S3 access without creating an IAM identity for the other account.
- Both evaluated together per full policy evaluation logic - an explicit Deny in either overrides an Allow in the other; generally both need to permit an action (mirrors KMS's "both key policy and IAM must align" pattern, though S3's same-account default behavior is somewhat more permissive - verify current docs for the exact nuance).

---

---

## 3a. S3 Access Points & Multi-Region Access Points

### 3a.1 The Problem With a Single Bucket Policy at Scale

- A bucket policy is one document attached to one bucket - as the number of applications/teams sharing a single large bucket grows, that one policy tends to become large, hard to reason about, and risky to change (one team's access-scoping change can accidentally affect another team's access, since it's all one shared document).
- S3 Access Points solve this by letting you create multiple, named "front doors" into the same bucket, each with its own dedicated access policy and even its own network origin restriction - without touching the underlying bucket policy or splitting data into multiple buckets.

### 3a.2 What an Access Point Is

- An access point is a distinct hostname/ARN, always tied to exactly one bucket, with its own resource policy (evaluated in addition to, not instead of, the bucket policy - both must permit an action, same "all applicable policies must align" pattern seen throughout S3 and KMS).
- Each access point can also be restricted to a specific VPC, meaning requests reaching that particular access point must originate from within that VPC - a network-level restriction layered on top of the identity-level policy, independent of whether the bucket itself is otherwise reachable from the public internet.
- Practical example: a shared "data-lake" bucket used by three teams (analytics, ML training, compliance) can expose three access points - `analytics-ap`, `ml-training-ap`, `compliance-ap` - each scoped to that team's specific prefix and permissions, letting each team's access be managed and reasoned about independently, while the underlying bucket policy stays simple (or is even reduced to close to nothing, since access points carry the real scoping).

```bash
# Create an access point restricted to a specific prefix, for a specific team
aws s3control create-access-point \
  --account-id 111122223333 \
  --name analytics-ap \
  --bucket data-lake-bucket \
  --vpc-configuration VpcId=vpc-0123456789abcdef0
```

- Common error: forgetting that an access point's policy is evaluated _in addition to_ the bucket policy, not as a replacement for it - an access point granting broad access is still constrained by whatever the underlying bucket policy allows, and vice versa.

### 3a.3 Multi-Region Access Points (MRAP)

- A Multi-Region Access Point is a single global endpoint that routes requests to the lowest-latency replica of a dataset across multiple buckets in multiple AWS Regions, typically paired with S3 Cross-Region Replication ([§42](./Section-42-Part5-S3-Advanced-Versioning-Replication-Performance.md)) keeping those regional buckets in sync.
- Why it exists: without an MRAP, a globally-distributed application has to implement its own region-selection/failover logic across several regional bucket endpoints; an MRAP gives applications one stable endpoint and lets AWS handle routing to the nearest/healthy replica, including automatic failover if a Region becomes unavailable.
- Practical fit: a global media platform storing user-uploaded content replicated across three Regions for latency and resilience can front all three with one MRAP, so client applications never need Region-specific logic or manual failover handling.

### 3a.4 Security and Production Usage

- Access Points are the modern recommended pattern for any bucket shared across multiple applications or teams, specifically to avoid one large, high-blast-radius bucket policy.
- VPC-restricted access points are a meaningful defense-in-depth control for sensitive data - even a correctly-scoped IAM policy can't reach the bucket through that access point from outside the designated VPC.
- MRAPs inherit the security posture of their underlying buckets (encryption, access control) - they add routing/failover, not a separate security model.

### 3a.5 Key Takeaways

1. Access Points let a single bucket expose multiple, independently-scoped "front doors," avoiding one unwieldy shared bucket policy as the number of consuming teams/applications grows.
2. An access point's policy and the underlying bucket policy are both evaluated - one does not replace the other.
3. Multi-Region Access Points give a globally-distributed application one stable endpoint with automatic routing/failover across regional bucket replicas, commonly paired with Cross-Region Replication.

---

## 4. Access Control Lists (ACLs) - Legacy

- S3's original, pre-IAM access control mechanism, granting permissions to specific accounts or predefined groups (like "All Users" - the mechanism behind many historical public-bucket incidents).
- AWS's current guidance: disable ACLs entirely, use bucket policies and IAM policies exclusively. Bucket-owner-enforced setting (modern default for new buckets) disables ACLs outright.
- Historically, an accidental "public" ACL grant was a common breach cause - modern defaults (ACLs disabled, BPA enabled) specifically close this gap.

---

## 5. S3 Block Public Access - The Safety Net

- Operates at account and/or bucket level, can OVERRIDE any other configuration that would grant public access - an absolute safety net, similar in spirit to SCPs' unbypassable-ceiling pattern, implemented as an S3-specific feature.
- Four independently toggleable settings: block public access via new ACLs; via any ACLs; via new public bucket policies; via any public bucket policies.
- Enabled by default for new buckets and new accounts - "secure by default" theme continues.

Interview tip: BPA is the modern safety net specifically preventing the classic leaky-bucket scenario - even an accidentally overly-permissive bucket policy can be blocked from taking effect. The S3-specific expression of the "unbypassable ceiling" philosophy.

---

## 6. Encryption at Rest

### 6.1 SSE-S3 (S3-Managed Keys)

- Simplest option - S3 manages keys entirely (AES-256), no KMS involvement, no extra cost.
- Default for all NEW S3 objects as of a 2023 update - encryption at rest is now automatic, even without explicit config. Older material may describe it as opt-in.

### 6.2 SSE-KMS (KMS Keys)

- Uses a KMS key (AWS managed `aws/s3` or a customer-managed CMK), following envelope encryption mechanics.
- Why choose it: fine-grained access control (KMS key's own policy gates decryption independently of S3 permissions) and a detailed CloudTrail audit trail - neither provided by SSE-S3.
- The "both must align" gotcha applies: an IAM/bucket policy granting s3:GetObject is NOT sufficient to decrypt an SSE-KMS object unless the KMS key policy also permits it.

### 6.3 SSE-C (Customer-Provided Keys)

- You supply your own key per request; S3 encrypts/decrypts but does NOT store the key - full responsibility for key management, losing the key means permanently losing the data.
- Narrow use case: hard requirement to manage keys entirely outside AWS KMS, accepting real key-loss risk.

### 6.4 Client-Side Encryption

- Strongest model - encrypt before sending to S3, so S3 never sees plaintext at all, often using KMS via envelope encryption underneath.

---

## 7. Encryption in Transit

- TLS/HTTPS protects data moving between client and S3 - a separate mechanism from at-rest encryption, enforceable via a bucket policy condition requiring aws:SecureTransport, denying non-HTTPS requests explicitly.
- A common, practical bucket-policy pattern - an explicit Deny (explicit-deny-always-wins) blocking non-TLS requests, ensuring in-transit encryption is enforced, not just available.

---

## 8. Presigned URLs

- Grants temporary access to a specific object to anyone holding the URL, without requiring any AWS credentials - generated by a principal with permission, using their own credentials to sign a URL with built-in expiration.
- Useful pattern: an app backend generates a presigned URL for a user to upload/download directly, without routing file data through the app server, and without giving the user standing AWS credentials - parallel in spirit to CloudFront signed URLs but a distinct mechanism.

---

## 9. Production & Enterprise Usage

- Bucket policies as the primary mechanism today - modern architectures use bucket policies (cross-account/resource-based) plus IAM policies (identity-based), ACLs disabled account-wide.
- SSE-KMS with CMKs for regulated data - audit trail and independent access-control layer for compliance requirements.
- Enforcing TLS via bucket policy - standard hardening step, often via SCP or Config rule detection.
- Presigned URLs for direct-to-S3 uploads - standard pattern for user-generated content, avoiding routing large uploads through app servers.

---

## 10. Security Considerations - Full Picture

- Layered defense: IAM + bucket policies (access control) + Block Public Access (safety net) + encryption at rest (data protection if access control fails) + TLS enforcement (in-transit protection) - defense-in-depth applied comprehensively to one service.
- BPA should stay enabled unless there's a specific, deliberate, reviewed reason for public content - never disabled as a quick troubleshooting fix.
- Encryption at rest doesn't substitute for access control - an encrypted object with an overly permissive policy is still fully readable by anyone that policy grants access to; they protect against different threat models.

---

## 11. Performance Considerations

- Encryption (SSE-S3 or SSE-KMS) adds negligible latency - not a meaningful trade-off.
- SSE-KMS has its own request-rate considerations tied to KMS API quotas - relevant only at extremely high throughput.

---

## 12. Troubleshooting

| Symptom                                                               | Cause                                                                               | Fix                                                                                     |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| Bucket unexpectedly publicly accessible                               | Overly permissive bucket policy/ACL, BPA not enabled or not covering the grant type | Enable all four BPA settings unless public access is deliberate                         |
| AccessDenied reading SSE-KMS object despite correct IAM/bucket policy | KMS key policy doesn't grant the principal decrypt permission                       | Update the KMS key policy, not just the S3-level policy                                 |
| Presigned URL stopped working                                         | Expiration reached, or generating principal's permissions revoked after issuance    | Generate a new URL; note revoking generator permissions can invalidate outstanding URLs |
| TLS-enforcing bucket rejects a legitimate client                      | Client making an HTTP (non-HTTPS) request                                           | Ensure client uses HTTPS                                                                |

---

## 13. Best Practices & Anti-Patterns

Best practices: leave Block Public Access enabled unless a specific reviewed exception exists; disable ACLs (bucket-owner-enforced); use SSE-KMS with a CMK for regulated/sensitive data; enforce TLS via bucket policy condition; use presigned URLs for temporary scoped access instead of standing credentials.

Anti-patterns: disabling BPA as a quick access-problem fix; continuing to rely on ACLs for new architectures; assuming encryption at rest substitutes for access control; embedding long-lived credentials in client apps when a presigned URL would work.

---

## 14. Common Misconceptions

- "S3 objects are unencrypted by default." False since 2023 - SSE-S3 is now automatic default.
- "IAM policy granting s3:GetObject is enough regardless of encryption." False for SSE-KMS - the KMS key policy must also permit decryption.
- "Disabling BPA is sometimes necessary to fix access issues." False - correct fix is almost always adjusting the actual policy; BPA should stay enabled except for deliberate public use cases.
- "ACLs and bucket policies serve the same purpose." False - ACLs are legacy/error-prone; bucket policies are the modern standard, disabled by default for new buckets.

---

## 15. Interview Questions (with model answers)

Beginner - IAM policy vs bucket policy for S3 access? IAM policy: identity-based, attached to a user/group/role. Bucket policy: resource-based, attached to the bucket, enabling cross-account access without creating an IAM identity in the other account. Both evaluated together.

Beginner - Is S3 encryption at rest something I need to enable? Not anymore - since a 2023 change, SSE-S3 is automatic default for every new object. Only need to configure something for a different approach like SSE-KMS with a CMK.

Intermediate - Why might a correctly-scoped IAM policy still yield AccessDenied reading an S3 object? If SSE-KMS with a CMK, S3-level permission alone isn't enough - the KMS key policy must also grant decrypt permission independently. The same "both resource policy and IAM must align" pattern as KMS generally.

Intermediate - When use a presigned URL instead of direct IAM access? When giving temporary scoped access to someone who doesn't have (and shouldn't have) standing AWS credentials - e.g., an end user uploading/downloading a file. Backend generates a URL with built-in expiration, letting the request happen directly against S3 without routing through the app server or issuing real IAM credentials.

Senior - Design S3 security for a multi-tenant SaaS storing sensitive documents, requiring even admins need an explicit audited action to read customer data? Disable ACLs account-wide, rely on bucket/IAM policies, keep BPA fully enabled. Use SSE-KMS with a CMK rather than SSE-S3 specifically because the "explicit audited action" requirement maps to KMS's independent access-control layer - even a broadly-permissioned admin can't decrypt without separate KMS key policy permission, and every decrypt attempt is CloudTrail-logged. Scope the KMS key policy narrowly (application's execution role only), requiring a deliberate, reviewable key-policy change for anyone else including admins to gain access. Enforce TLS via bucket policy; use presigned URLs for customer upload/download so customers never hold standing bucket credentials.

---

## Key Takeaways

1. IAM policies (identity-based) and bucket policies (resource-based) are evaluated together, with bucket policies specifically enabling cross-account access.
2. ACLs are legacy and should be disabled - modern S3 security relies on bucket policies and IAM policies, disabled by default for new buckets.
3. Block Public Access is the unbypassable safety net - can override any policy/ACL that would grant public access; stay enabled except for deliberate exceptions.
4. Encryption at rest is now automatic default (SSE-S3), with SSE-KMS for independent access control and audit logging - the "KMS key policy must align" gotcha applies directly to S3.
5. Presigned URLs provide temporary scoped access without standing credentials - the standard pattern for direct client-to-S3 upload/download.

## Related Concepts (forward links)

- Versioning, replication, and performance optimization, including Cross-Region Replication as the usual pairing for Multi-Region Access Points (see [§3](../Part1/Section-03-Part1-Shared-Responsibility-Model.md)a) -> [§42](./Section-42-Part5-S3-Advanced-Versioning-Replication-Performance.md)
- EBS encryption, following the same KMS patterns -> [§43](./Section-43-Part5-EBS-Full-Depth.md)
- AWS Config rules detecting S3 misconfigurations at scale -> [§16](../Part2/Section-16-Part2-GuardDuty-SecurityHub-Config-Inspector.md)
