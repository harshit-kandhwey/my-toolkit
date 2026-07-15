# Part 2 · Section 2 — IAM Policy Deep Dive: Evaluation Logic

> AWS Zero-to-Enterprise Knowledge Base · Part 2: Identity, Security & Governance

---

## 1. Definition

**Plain-language:** When you make a request, several policies could weigh in — attached to you, the resource, your account, your role's boundary. IAM has strict, deterministic rules for combining all of these into one final Allow/Deny.

**Precise:** The **IAM policy evaluation logic** is the deterministic algorithm combining every applicable policy (identity-based, resource-based, permissions boundary, SCP, session policy) into a single decision, governed by: **default deny**, and **explicit deny always wins**.

---

## 2. Why It Exists

- A single request can be governed by many policies simultaneously (user, group, SCP, boundary, resource policy).
- Without strict predictable rules, nobody could reason about what's actually allowed. AWS uses a small number of absolute rules that always apply the same way.
- Misunderstanding this is the top cause of "my policy allows this but I get AccessDenied" — usually an explicit Deny elsewhere silently overriding an Allow.

---

## 3. The Two Governing Principles

### 3.1 Default Deny (Implicit Deny)

Everything is denied unless something explicitly allows it. A new IAM user with zero policies can do nothing. Every permission must be explicitly granted somewhere.

### 3.2 Explicit Deny Always Wins

If _any_ applicable policy has explicit `"Effect": "Deny"` for the action, the request is denied — regardless of how many other policies say Allow. No "higher layer" Allow can override it.

> 🔑 **Formula:**
> Explicit Deny anywhere → **Deny**.
> No explicit Deny, no explicit Allow → **Deny** (implicit).
> No explicit Deny, at least one explicit Allow → **Allow**.

---

## 4. Evaluation Flow

```
Request arrives
  → SCP applicable? Explicit Deny anywhere → DENY (stop)
  → Resource-based policy? Explicit Deny → DENY (stop)
  → Identity-based policies? Explicit Deny → DENY (stop)
  → Permissions boundary (if set)? Not within it → DENY (stop)
  → Session policy (if passed)? Not within it → DENY (stop)
  → At least one explicit ALLOW across applicable policies?
      No → DENY (implicit)   Yes → ALLOW
```

> 💡 Each layer is a gate: "explicit no" = instant stop; "not explicitly yes" = still blocks; "yes" = passes. Request succeeds only if every applicable gate says yes or has nothing to say, AND at least one gate said yes.

---

## 5. Each Layer's Role

### 5.1 Service Control Policies (SCPs) — full detail Section 5

- Applied at AWS Organizations level to an account/OU.
- **Never grant permissions** — only define the maximum possible (a ceiling). Even AdministratorAccess can't exceed the SCP.
- SCP explicit Deny on an action → nothing in that account can ever do it, regardless of in-account IAM.

### 5.2 Resource-Based Policies

- Attached to the resource (S3 bucket policy, KMS key policy, role trust policy, SNS topic policy).
- Can grant access to a principal with **no identity-based policy at all** — this is how cross-account access works: Account B's bucket policy grants access to a principal in Account A directly, as long as Account A's own identity policy doesn't explicitly deny it.

### 5.3 Identity-Based Policies

- Attached to users/groups/roles (Section 1). Multiple apply simultaneously (user's own + every group) and combine with the same explicit-deny-wins, default-deny logic.

### 5.4 Permissions Boundaries

- Attached to a **user or role**, capping maximum possible permissions regardless of identity-based policy generosity.
- **Never grants** — only limits. Effective permission = **intersection** of identity-based policy AND boundary.
- Classic use: letting developers self-create IAM roles safely — attach a boundary so even self-created roles can't exceed a safe ceiling.

### 5.5 Session Policies

- Passed at `sts:AssumeRole` time, further restricting that session below the role's permissions policy.
- Only restricts, never grants — effective permission = intersection of role's policy and session policy.

> 🎯 Permissions boundaries and session policies are **restriction-only** — they narrow, never add. Only identity-based and resource-based policies can grant an Allow.

---

## 6. Explicit Deny vs Implicit Deny

- **Implicit (default) deny** — nothing said anything about this action; denied by silence.
- **Explicit deny** — a policy specifically states `"Effect": "Deny"` for this action; a deliberate active statement.
- **Why it matters:** implicit deny can be overridden by an explicit Allow elsewhere (nothing actively forbade it). Explicit deny **cannot** be overridden by anything.

> ⚠️ There's no "more specific/local policy wins" rule — only "is there an explicit Deny anywhere applicable" matters.

---

## 7. Policy Variables and Wildcards

- **Wildcards:** `*` matches any sequence, `?` matches one character (e.g., `s3:Get*` matches `s3:GetObject`, `s3:GetBucketPolicy`).
- **Policy variables:** resolved at evaluation time, e.g., `${aws:username}` — write one reusable policy instead of per-user copies.
  ```json
  {
    "Effect": "Allow",
    "Action": "s3:GetObject",
    "Resource": "arn:aws:s3:::company-home-dirs/${aws:username}/*"
  }
  ```
  One statement, attached to 500 users, auto-scopes each to their own prefix.

---

## 8. Condition Keys

- **Global condition keys:** `aws:SourceIp`, `aws:CurrentTime`, `aws:MultiFactorAuthPresent`, `aws:PrincipalOrgID`.
- **Service-specific:** `s3:x-amz-server-side-encryption`, `ec2:InstanceType`.
- **Operators:** `StringEquals`, `StringLike`, `IpAddress`, `DateGreaterThan`, `Bool`, `NumericLessThan`.

**Example — require MFA for a sensitive action:**

```json
{
  "Effect": "Deny",
  "Action": "iam:DeleteUser",
  "Resource": "*",
  "Condition": {
    "BoolIfExists": { "aws:MultiFactorAuthPresent": "false" }
  }
}
```

Explicit Deny that fires unless MFA was used — a "deny unless X" pattern, easier to reason about when layered with other policies than "allow only if X."

---

## 9. `NotAction` and `NotResource`

- **`NotAction`** — applies the effect to every action **except** those listed.
- **`NotResource`** — same for resources.
- **Caution:** `NotAction` + `Allow` can grant far broader access than intended (everything except the list, across the whole namespace). Safer paired with `Deny`.

---

## 10. Production & Enterprise Usage

- **Layered defense-in-depth:** combine SCPs (org-wide ceilings), permissions boundaries (per-identity ceilings), and scoped identity policies — any layer acts as a safety net others can't override.
- **"Deny unless MFA"** and similar conditional-Deny patterns standard for protecting sensitive actions (deleting users, billing changes, security config changes).
- **IAM Policy Simulator** (`iam:SimulatePrincipalPolicy`) — test what a principal can/cannot do before deploying, used in real change management.

---

## 11. Troubleshooting

| Symptom                                                          | Cause                                                                    | Fix                                                  |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------ | ---------------------------------------------------- |
| "My policy allows this but still AccessDenied"                   | Explicit Deny elsewhere (SCP, boundary, resource policy)                 | Check every layer, not just the one you wrote        |
| Cross-account bucket-policy access still fails                   | Requester's own identity policy explicitly denies or lacks the statement | Ensure requester's account has an Allow (or no Deny) |
| Role with a boundary can't do what its permissions policy allows | Boundary doesn't include that action; effective = intersection           | Widen boundary or reconsider the action              |
| Policy variable not resolving as expected                        | Variable not defined for that principal type (e.g., federated sessions)  | Check which variables apply to that principal type   |

---

## 12. Best Practices & Anti-Patterns

**Best practices:** use explicit Deny deliberately for non-negotiable rules (MFA requirement, dangerous-action blocks); use permissions boundaries when delegating role-creation; test with IAM Policy Simulator before deploying; remember SCPs are ceilings not grants.

**Anti-patterns:** assuming specificity overrides a broader Deny; `NotAction` + `Allow` without careful resource scoping; debugging AccessDenied by checking only your own policy.

---

## 13. Common Misconceptions

- "If my policy says Allow, I should be able to do it." → False — any applicable explicit Deny overrides completely.
- "A permissions boundary grants permissions." → False — restriction only; still needs an actual Allow.
- "More specific policies win." → False — no specificity precedence in IAM.
- "SCPs directly give people permissions." → False — only cap the ceiling; grants still needed within it.

---

## 14. Interview Questions (with model answers)

**🟢 What happens with no IAM policies attached at all?** Implicit deny — nothing is allowed by default; every permission must be explicitly granted.

**🟢 One policy allows, another explicitly denies — outcome?** Explicit deny wins unconditionally, regardless of how many Allows exist or how "local" they are.

**🟡 SCP deny vs identity-policy deny — practical difference?** Both deny via the same rule, but SCP applies at the Organizations level to an entire account/OU as an unconditional ceiling nothing inside can exceed; identity-based Deny only affects that specific principal. SCPs = org-wide guardrails; identity Denies = principal-specific.

**🟡 Why are boundaries/session policies "restriction-only"?** Neither can grant on its own — they intersect with and narrow what the identity-based policy already allows. If the identity policy doesn't allow it, the boundary/session policy including it changes nothing. Only identity-based and resource-based policies can originate an Allow.

**🔴 Lambda role has s3:PutObject in its permissions policy but calls fail — debug process?** Work through the stack: check for an SCP denying S3 actions at account/OU level; check the target bucket's resource policy for an explicit deny; re-verify the role's identity policy ARN/action scoping (typo/wildcard is common); if a permissions boundary exists, confirm the action is within the intersection; check for a restrictive session policy passed at assume-role. Use the IAM Policy Simulator to test the exact combination directly.

**🔴 Guarantee no engineer, even an admin, can disable CloudTrail or delete audit logs?** Org-level SCP with explicit Deny on the CloudTrail-disabling/log-bucket-deleting actions, applied to the engineering OU — SCPs are enforced independently of in-account IAM, so even AdministratorAccess can't override it. Scope an exception only via a tightly controlled break-glass role, with its use triggering a high-priority CloudTrail/EventBridge alert. Only an SCP-level explicit Deny provides this unbypassable guarantee.

---

## 🔑 Key Takeaways

1. Two absolute rules govern every decision: default deny, and explicit deny always wins.
2. Multiple layers can apply (SCPs, resource-based, identity-based, boundaries, session policies) — evaluated together, with no specificity/locality precedence.
3. Only identity-based and resource-based policies can grant an Allow; SCPs, boundaries, session policies are restriction-only.
4. Policy variables (`${aws:username}`) and condition keys (`aws:MultiFactorAuthPresent`) enable reusable, context-aware policies.
5. The IAM Policy Simulator is a real tool for testing evaluation outcomes before deploying changes.

## 🌐 Related Concepts (forward links)

- SCPs in full depth (OU hierarchy, inheritance) → Part 2, Section 5
- STS and session credential/session policy issuance → Part 2, Section 3
- IAM Access Analyzer, Trusted Advisor IAM checks → Part 2, Section 8
