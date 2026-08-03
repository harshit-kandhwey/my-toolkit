# Part 2 · Section 5 — AWS Organizations & Service Control Policies (SCPs)

> AWS Zero-to-Enterprise Knowledge Base · Part 2: Identity, Security & Governance

---

## 1. Definition

**Plain-language:** AWS Organizations groups many AWS accounts under one roof, managed centrally — one consolidated bill, and rules that automatically bind every account in a group.

**Precise:** **AWS Organizations** is a free, global service for **centrally managing and governing multiple AWS accounts** — consolidated billing, hierarchical grouping via **Organizational Units (OUs)**, and org-wide enforcement via **Service Control Policies (SCPs)** and related policy types.

---

## 2. Why It Exists

- Many independent accounts (§7) left ungoverned creates inconsistency — nothing stops one team's account from being insecure while another's is locked down.
- Organizations adds a management layer above accounts — define guardrails once, apply automatically and unbypassably everywhere, without trusting every account owner individually.
- Solves billing fragmentation (§6) — one consolidated view instead of many separate bills, with per-account visibility preserved.

> 🔑 Organizations turns "many independent accounts" into "one governed estate" — the foundation for Identity Center and Part 8's cross-account monitoring.

---

## 3. Core Structure

### 3.1 Management Account (formerly "Master Account")

- Top of the Organization; creates it initially. Creates member accounts, invites existing ones, applies SCPs, consolidates billing.
- **Not subject to SCPs** — should hold minimal workloads, existing as an administrative control point only.

### 3.2 Member Accounts

- Where actual workloads live. Each has its own root user (secure every account's root, not just management's — §4). Subject to SCPs via their OU.

### 3.3 Organizational Units (OUs)

- Folders for grouping accounts; nestable, creating a hierarchical tree. Policies attached to an OU apply to everything nested inside, at any depth.
- Typical structures:
  - **By environment** (Production, NonProduction/Development, Sandbox) — most common top-level split.
  - **By business unit/team** (Finance, Engineering, Marketing).
  - **By function** (Security/Core OU for log-archive/security-tooling, Shared-Services OU for networking).
- Common pattern: environment top-level, business-unit sub-OUs nested inside — a Production-Finance account inherits both.

### 3.4 "Root" of the Organization vs Root User

- ⚠️ "Root" in Organizations = the top node of the OU tree. Completely different from the **root user** (§4), a credential/identity within a specific account. Context determines which is meant.

---

## 4. Creating and Managing Member Accounts

- New accounts created directly within the Organization auto-enroll, applying OU-assigned SCPs from creation.
- Existing standalone accounts can be invited to join.
- **Account vending** via **AWS Control Tower** (built on Organizations) automates creation so new accounts are born correctly placed with baseline security/logging already configured.

---

## 5. Service Control Policies (SCPs) — Full Mechanics

### 5.1 What an SCP Is

- Structurally identical JSON shape to IAM policies (Version/Statement/Effect/Action/Resource/Condition).
- Functionally different: **never grants** — only defines the maximum available permissions for accounts it's attached to. An in-account IAM Allow is still required for anything to actually happen.

### 5.2 Deny List vs Allow List

| Strategy                | How it works                                                                                            | Trade-off                                                         |
| ----------------------- | ------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------- |
| **Deny list (default)** | Start from default `FullAWSAccess`, layer explicit Deny for specific forbidden things                   | Simpler, incremental; new AWS services usable by default (a risk) |
| **Allow list**          | Remove default `FullAWSAccess`, explicitly Allow only approved services/actions; everything else denied | Stronger baseline, more upfront design/maintenance                |

> 🎯 No universally correct answer — deny-list is the common starting point; allow-list reserved for the most sensitive OUs (Production, Security).

### 5.3 Common Real-World SCP Examples

- Deny leaving the Organization.
- Deny disabling CloudTrail/GuardDuty/Config.
- Region restriction (enforcing §2's opt-in Region discussion).
- Enforce root MFA / deny root access key creation org-wide.
- Deny expensive resource types in non-production OUs (cost governance, enforced not just monitored).

### 5.4 SCP Inheritance

- SCPs at a higher OU level apply to everything nested beneath.
- **Effective restriction on any account = intersection of every SCP from Organization root → intermediate OUs → account's OU → account itself.**
- Since SCPs only restrict, stacking down the tree can only narrow, never widen.

> 🔑 Each SCP level is another restriction gate — deepest account is bound by the cumulative intersection of all SCPs above it.

---

## 6. Other Organizations Policy Types

- **Tag Policies** — enforce consistent tagging standards org-wide (supports §6's cost-allocation tagging, enforced).
- **Backup Policies** — centrally enforce AWS Backup plans (full depth Part 5).
- **AI Services Opt-Out Policies** — control AWS's use of your data for AI/ML improvement — compliance-relevant.

---

## 7. Consolidated Billing — Full Mechanics

- All member usage rolls into one bill paid by the management account.
- **Volume pricing/RI/Savings Plans discounts shared across the Organization** — many small accounts collectively crossing a threshold none would reach alone.
- Per-account cost visibility preserved — layered on top of, not instead of, Cost Explorer/CUR (§6).

---

## 8. Production & Enterprise Usage

- **AWS Control Tower** automates "landing zone" setup — pre-configured baseline OUs/SCPs, centralized logging account, centralized security-tooling account — the standard way large orgs bootstrap multi-account structure.
- **Dedicated Security/Log Archive accounts** — a `Security`/`Core` OU holding accounts whose sole purpose is centralized log storage and security tooling, isolated from application teams.
- **Delegated administration** — a dedicated security account can centrally manage GuardDuty/Security Hub/Config org-wide without needing management-account-level access.

---

## 9. Security Considerations

- **Management account = highest-value target** in the Organization — exempt from SCPs, controls SCP creation for everyone else — deserves the strictest security posture.
- **SCPs are genuinely unbypassable from within the account** — why Section 2's architect answer used an SCP, not IAM, to guarantee CloudTrail can't be disabled.
- **Deny-list SCPs don't protect against new AWS services by default** — a real operational gap to monitor.

---

## 10. Troubleshooting

| Symptom                                                  | Cause                                                    | Fix                                                                            |
| -------------------------------------------------------- | -------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Action denied despite permissive IAM policy              | An SCP up the OU tree denies it                          | Trace OU hierarchy from account to Organization root, check every attached SCP |
| New account missing expected guardrails                  | Wrong OU placement, or SCPs not yet attached at creation | Verify OU placement/SCP attachment; use Control Tower for consistency          |
| SCP change doesn't seem to apply                         | Eventual consistency (like IAM)                          | Wait and retest; confirm attached to correct OU/account                        |
| Management account seems unrestricted vs member accounts | Working as designed — exempt from SCPs                   | Not a bug — reason to minimize management-account workloads                    |

---

## 11. Best Practices & Anti-Patterns

**Best practices:** keep management account nearly workload-free; structure OUs by environment first then business unit/function; start deny-list, graduate to allow-list for sensitive OUs; use SCPs for unbypassable guardrails; use Control Tower for consistent account vending.

**Anti-patterns:** running production workloads in the management account; treating SCPs as a substitute for IAM (they only restrict); flat OU structure forcing repetitive per-account policy attachment; assuming deny-list protects against every risk.

---

## 12. Common Misconceptions

- "SCPs apply to the management account too." → False — explicitly exempt.
- "An SCP allowing a service means someone can use it." → False — still needs an actual IAM Allow.
- "OUs are just visual folders." → False — real policy-inheritance attachment points.
- "'Root' always means the root user." → False in Organizations context — can mean the OU tree's top node.

---

## 13. Interview Questions (with model answers)

**🟢 What is an AWS Organization and why use one?** Centrally manages multiple accounts — consolidated billing with per-account visibility, plus org-wide governance (SCPs) automatically binding every account in a group. The structural foundation for multi-account blast-radius isolation.

**🟢 Is the management account subject to SCPs?** No — exempt. Best practice: keep it nearly workload-free; its high privilege + SCP exemption makes it the most sensitive account in the Organization.

**🟡 Deny-list vs allow-list SCP strategy?** Deny-list starts from full access, layers explicit Denies — simpler, but new services usable by default. Allow-list removes full access, explicitly allows only approved actions — stronger but more maintenance. Most orgs start deny-list, reserve allow-list for sensitive OUs (production, security).

**🟡 SCP allows S3 but no IAM policy grants it to a user — can they use S3?** No. SCPs only set the ceiling, never grant. The user still needs an actual IAM Allow; without one, default-deny still applies.

**🔴 Design OU structure + SCP strategy for production/staging/internal tools, security + cost governance?** Top-level OUs: Production, Non-Production, Security/Core (log-archive/security-tooling); management account workload-free. Nest Sandbox (looser) separate from Staging (mirrors Production) within Non-Production. Org-wide deny-list baseline at root: deny disabling CloudTrail/Config/GuardDuty, deny leaving the Org, enforce approved Regions. Stricter allow-list SCP on Production OU. Cost-governance SCP on Sandbox denying expensive resources. Use Control Tower for consistent provisioning.

**🔴 New AWS service isn't blocked by deny-list SCP — flaw or trade-off?** Inherent, known trade-off, not a flaw — deny-list optimizes for low maintenance/default usability, accepting new services open by default. For unacceptable-risk OUs (Production, regulated), use allow-list instead, closing the gap. For deny-list OUs, pair with monitoring (Config, scheduled review) as a compensating detective control rather than trying to make deny-list behave like allow-list.

---

## 🔑 Key Takeaways

1. AWS Organizations is the structural layer above accounts — consolidated billing, hierarchical OUs, org-wide policy enforcement.
2. The management account is exempt from SCPs and should be kept nearly workload-free — the most sensitive account in the Organization.
3. SCPs are ceilings, never grants — structurally like IAM policies, functionally restriction-only; an in-account Allow is still always required.
4. SCPs inherit down the OU tree; effective restriction = intersection of every SCP from root to the account — stacking only narrows.
5. Deny-list vs allow-list is a genuine trade-off — deny-list is the common default, allow-list reserved for the most sensitive OUs.

## 🌐 Related Concepts (forward links)

- KMS and encryption enforcement, often paired with SCPs → §14
- Control Tower, delegated administration, centralized logging/security accounts → Part 8
- Backup Policies in depth → Part 5
