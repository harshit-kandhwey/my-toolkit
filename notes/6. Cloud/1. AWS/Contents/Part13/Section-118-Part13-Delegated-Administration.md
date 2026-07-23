# Part 13, Section 4: Delegated Administration Across AWS Services

## 1. Definition

**Plain language:** Part 13 §1-3 established the management account as the top of the landing zone hierarchy — but that raises an operational question: does every organization-wide security or governance task actually need to be performed *from* the management account? Doing so would make the management account a constant, high-traffic operational bottleneck, and would mean an ever-growing number of people needing access to the single most sensitive account in the entire Organization. Delegated administration is AWS's answer: letting specific, individual services be administered organization-wide from a different, dedicated account instead.

**Precise definition:** Delegated administration is a capability, supported by many AWS Organizations-integrated services (GuardDuty, Security Hub, Config, IAM Identity Center, and others), that lets the management account designate a different member account as that specific service's **delegated administrator** — granting that account the ability to manage the service's configuration and view its findings/data organization-wide, without requiring day-to-day operation from, or broad standing access to, the management account itself.

## 2. Why It Exists / Problem It Solves

- The management account, as established throughout Part 2 §5 and this Part, is the single highest-value target and most sensitive account in an AWS Organization — every security best practice this course has covered points toward minimizing who has access to it and what's actually done from it, day to day.
- But many organization-wide security/governance services genuinely need to be configured and operated *somewhere* with organization-wide visibility — someone needs to review GuardDuty findings across every account, or manage Security Hub's aggregated compliance posture, or administer Config Rules organization-wide. Without delegated administration, the only way to do this would be granting the relevant personnel standing access to the management account itself — directly undermining the "minimize management account access" principle for what is, after all, routine, ongoing operational work, not a rare, exceptional action.
- Delegated administration resolves this tension directly: the management account performs the one-time act of *designating* a delegated administrator account for a specific service, and from that point forward, the actual day-to-day administration of that service happens entirely from the delegated account — the people doing that ongoing work never need management account access at all.
- 🔑 **Key takeaway:** this is the exact same underlying principle as the Log Archive/Audit account separation from Part 13 §3 — narrow the set of people/processes that ever touch the most sensitive account, by moving routine operational work to a purpose-specific account instead — now applied not to logging specifically, but generally, across every AWS Organizations-integrated service that supports it.

## 3. Prerequisites and Dependencies

- **AWS Organizations** (Part 2 §5): delegated administration is an Organizations-integrated capability, requiring the multi-account structure established there.
- **GuardDuty, Security Hub, Config** (Part 2 §8, Part 8 §6): common services administered via delegation — this section assumes familiarity with what these services actually do, focusing here specifically on the delegation mechanism itself.
- **Centralized logging/Audit account architecture** (Part 13 §3): the Audit account is frequently also configured as the delegated administrator for security-focused services, extending its role from "read access to centralized logs" to "organization-wide administration of security tooling" — a natural, common pairing.

## 4. Internal Working / Architecture & Components

### 4.1 The Delegation Mechanism

- From the management account, an administrator designates a specific member account as the delegated administrator *for a specific service* — this is a per-service designation, not a single, blanket "this account administers everything" grant; an organization might delegate GuardDuty administration to the Audit account while delegating IAM Identity Center administration to a different, dedicated account, based on genuinely distinct operational ownership.
- Once designated, the delegated administrator account gains the ability to perform organization-wide actions specific to that service — for GuardDuty, this means enabling GuardDuty across every account in the Organization and viewing aggregated findings from all of them; for Security Hub, viewing aggregated compliance/security posture across every account; for Config, managing organization-wide Conformance Packs.
- ⚠️ **Warning:** delegated administration doesn't grant the delegated account broad, general access to member accounts — it grants specifically the administrative capability for that one designated service, scoped to that service's own actions and data; it is not a backdoor into arbitrary access across the Organization, and should not be treated (or misconfigured) as one.

### 4.2 Why Per-Service Delegation, Not a Single Delegated Account for Everything

- Different organization-wide services often have genuinely different natural owners within a real organization — a security operations team is the natural owner of GuardDuty/Security Hub administration, while an identity/access team might be the natural owner of IAM Identity Center administration, and a platform/infrastructure team might own Config administration — per-service delegation lets each capability be delegated to whichever account/team actually owns that operational responsibility, rather than forcing an artificial, single "does everything" delegated account that doesn't map to how the organization is actually structured.
- 🔑 **Key takeaway:** this mirrors the same "narrow, purpose-specific scoping beats broad, do-everything grants" principle established throughout this course for IAM policies (Part 2 §1-2) — here applied at the account-delegation level rather than the individual-permission level, but the same underlying least-privilege philosophy.

### 4.3 Delegated Administration vs. Cross-Account IAM Roles

- Delegated administration is a distinct mechanism from the cross-account IAM role pattern covered in Part 2 §3 and used for Audit account access in Part 13 §3 — cross-account roles grant a specific set of IAM permissions into another account; delegated administration specifically grants a designated account the ability to act as that *service's* organization-wide administrator, using that service's own native multi-account management capabilities (which often go beyond what a simple assumed IAM role alone would provide, such as GuardDuty's ability to auto-enable itself across new accounts as they're added to the Organization).
- In practice, a delegated administrator account commonly *also* uses cross-account IAM roles for personnel actually operating within it day to day — the two mechanisms work together: delegation grants the account its organization-wide administrative capability for a service, and standard IAM (and, if applicable, cross-account role assumption) governs which specific people/systems can use that capability from within the delegated account.

## 5. Lifecycle / Workflow

1. From the management account, an administrator identifies which AWS Organizations-integrated services should have organization-wide administration delegated, and to which specific account each should be delegated (commonly the Audit account for security-focused services, per §3's common pairing, though this varies by organization).
2. For each service, the management account performs the one-time delegation action, designating the chosen member account as that service's delegated administrator.
3. From that point forward, day-to-day administration of that service — enabling it across accounts, managing its configuration, reviewing its findings — happens entirely from the delegated administrator account, by whichever team/personnel are authorized (via standard IAM, within that account) to perform that work.
4. The management account's involvement in that service's ongoing operation drops to near-zero — its role was establishing the delegation, not performing the ongoing administrative work itself.
5. As the organization's structure evolves (a new team taking ownership of a particular security function, for example), delegation can be revoked and re-designated to a different account, without needing to reconstruct the underlying service configuration from scratch.

## 6. Configuration

| Setting | Purpose |
|---|---|
| Delegated administrator account designation (per service) | Which member account administers a given service organization-wide. |
| IAM permissions within the delegated administrator account | Governs which specific personnel/systems, operating from the delegated account, can actually exercise that service's administrative capability — standard least-privilege IAM scoping still applies within the delegated account itself. |
| Service-specific organization-wide settings (e.g., GuardDuty auto-enable for new accounts) | Configured from the delegated administrator account once delegation is established, applying organization-wide. |

## 7. Commands / API (Full Documentation)

### 7.1 Designating a Delegated Administrator

- **Purpose:** Grant a member account organization-wide administrative capability for a specific service.
- **Syntax (example using GuardDuty; the general pattern — an `enable-organization-admin-account`-style API call from the management account — applies similarly across other delegation-supporting services):**

```bash
aws guardduty enable-organization-admin-account \
  --admin-account-id 222233334444
```

- **Important arguments:** `--admin-account-id` specifies the member account (commonly the Audit account, per §3) being designated as GuardDuty's organization-wide delegated administrator. This command must be run from the management account — a deliberate restriction, mirroring the organization-trail creation restriction from Part 13 §3 §7.1.
- **Practical example / expected output:** after this call, account `222233334444` (the delegated administrator) can enable GuardDuty across every member account in the Organization and view aggregated findings from all of them, without any further involvement from the management account required for GuardDuty's ongoing operation.
- **Common errors:** attempting this designation from a non-management account (will fail — this action is specifically restricted to the management account, by design); designating an account that doesn't have appropriate downstream IAM controls of its own, effectively creating a new, under-governed concentration of organization-wide administrative capability.

## 8. Hands-On Example — Delegation Strategy

```text
Management Account
  (performs one-time delegation actions only, minimal ongoing operational use)
      |
      +-- Delegates GuardDuty administration --> Audit Account
      |     (security team operates GuardDuty org-wide from here,
      |      reviewing findings across every member account, per
      |      Part 13 §3's established Audit account role)
      |
      +-- Delegates Security Hub administration --> Audit Account
      |     (same security team, same account -- natural pairing
      |      with GuardDuty given both are security-posture tools)
      |
      +-- Delegates IAM Identity Center administration --> Identity Account
            (a SEPARATE, dedicated account -- identity/access team's
             natural ownership boundary, distinct from the security
             team's GuardDuty/Security Hub ownership)

Result: three genuinely different organization-wide administrative
capabilities, each delegated to the account/team that actually owns
that operational responsibility -- NOT all forced into one single
"does everything" delegated account, and NOT requiring any of this
routine work to touch the management account at all.
```

This demonstrates §4.2's principle concretely: delegation should map to genuine organizational ownership boundaries, not be collapsed into a single delegated account purely for the sake of having "one less account to manage" — that convenience would come at the cost of blending genuinely distinct operational responsibilities together.

## 9. Production and Enterprise Usage

- Delegated administration is standard practice in any mature, security-conscious AWS Organization — minimizing management account access is treated as a foundational security posture, not merely a nice-to-have, given how catastrophic a management account compromise would be relative to a compromise of any individual delegated administrator account.
- Security operations teams commonly operate GuardDuty, Security Hub, and (per Part 13 §3) centralized log/Audit account access all from the same delegated Audit account, reflecting a natural, common organizational pattern where one team owns the full "detect and investigate security issues organization-wide" responsibility.
- Larger, more complex organizations commonly delegate a wider range of services to a correspondingly wider range of purpose-specific accounts (identity, security, cost-management, networking) — reflecting genuinely distinct organizational ownership, rather than a smaller organization's more consolidated structure where fewer distinct accounts/teams might reasonably hold several delegated responsibilities together.

## 10. Security Considerations

- Delegated administration directly reduces the management account's operational footprint and the number of people/systems needing any access to it — a meaningful, structural risk reduction given the management account's outsized blast radius if compromised.
- A delegated administrator account, precisely because it holds genuine organization-wide administrative capability for its delegated service(s), itself warrants strong protection — MFA enforcement, tightly-scoped internal IAM permissions, and the same general account-hardening discipline this course has emphasized throughout, since it is now a meaningfully higher-value target than an ordinary workload account, even though it remains less catastrophic than the management account itself.
- §4.1's warning bears repeating as a security consideration specifically: delegation is scoped to one specific service's administrative actions, not broad account access — misconfiguring or misunderstanding this boundary (assuming a delegated administrator account has broader access than it actually does, or conversely under-protecting it based on a false assumption its access is narrower than it is) is a genuine risk worth explicit verification against current documentation for each specific service's delegation semantics.

## 11. Performance Considerations

- Delegated administration is a governance/access-control mechanism, not a workload-performance concern — this section's "performance" consideration is, similar to Part 13 §2, really about *operational efficiency*: how effectively administrative work can be distributed across appropriately-scoped accounts without funneling everything through a single bottleneck account.
- A well-designed delegation strategy (mapping services to genuine organizational ownership, per §4.2) reduces coordination overhead — teams operate within their own delegated account's scope without needing to request management-account-mediated changes for their routine, ongoing work.

## 12. Monitoring

- CloudTrail (Part 8 §5), centralized per Part 13 §3's architecture, captures both the one-time delegation-designation actions (performed from the management account) and the ongoing administrative activity performed from delegated administrator accounts — providing a complete audit trail of both who delegated what, and how that delegated capability has actually been used since.
- Periodically reviewing which services are delegated to which accounts, and confirming that delegation still reflects genuine, current organizational ownership (echoing the periodic access-review discipline established in Part 2 §1), is a worthwhile governance practice as an organization's team structure evolves over time.

## 13. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| Cannot designate a delegated administrator | Command run from a non-management account | Delegation designation must be performed from the management account specifically |
| Delegated administrator account can't perform an expected action | The specific action isn't covered by that service's delegation scope, or falls under a different service's separate delegation | Verify current documentation for exactly which actions a given service's delegated administrator role covers |
| Personnel in the delegated account have more (or less) access than intended | Internal IAM permissions within the delegated account aren't correctly scoped, independent of the delegation itself | Review and correct IAM policies within the delegated administrator account — delegation grants the account capability; IAM governs who within that account can use it |

## 14. Best Practices

- Delegate each Organizations-integrated service to the account/team that genuinely owns that operational responsibility, rather than consolidating everything into one delegated account by default.
- Treat delegated administrator accounts as high-value, requiring strong protection (MFA, tightly-scoped internal IAM) proportional to the genuine organization-wide capability they hold.
- Minimize ongoing, routine use of the management account itself — if a service supports delegation, use it, rather than continuing to operate that service directly from the management account out of habit or convenience.
- Periodically review delegation assignments against current organizational ownership, adjusting as team responsibilities evolve.

## 15. Anti-Patterns and Common Mistakes

- ❌ Continuing to administer organization-wide services directly from the management account when delegation is available, unnecessarily expanding who needs management account access for routine work.
- ❌ Delegating every service to a single account purely for administrative simplicity, blending genuinely distinct organizational ownership boundaries together and creating an outsized concentration of capability in one account.
- ❌ Under-protecting a delegated administrator account based on an assumption that only the management account is truly high-value — delegated accounts, while less catastrophic than the management account, still warrant serious protection given their genuine organization-wide capability.
- ❌ Assuming delegation grants broader access than it actually does (§4.1's warning) — misconfiguring downstream trust or access based on this misunderstanding.

## 16. Interview Questions with Model Answers

**🎯 Junior:** *"Why would an organization delegate administration of a service like GuardDuty to a different account instead of just managing it from the management account?"*
**Model answer:** The management account is the most sensitive, highest-value account in an AWS Organization, and best practice is to minimize who has access to it and what's routinely done from it. Delegated administration lets a different, purpose-specific account (commonly a dedicated security/Audit account) manage GuardDuty organization-wide instead — enabling it across accounts and reviewing findings — without the security team needing any standing access to the management account itself for that ongoing, routine work.

**🎯 Intermediate:** *"Why would an organization delegate different services to different accounts, rather than delegating everything to one account for simplicity?"*
**Model answer:** Different organization-wide services often have genuinely different natural owners within a real organization — a security team naturally owns GuardDuty and Security Hub, while an identity team naturally owns IAM Identity Center, for example. Delegating each service to whichever account/team actually owns that responsibility keeps the delegation structure aligned with how the organization is actually structured and who's actually accountable for what. Consolidating everything into one delegated account might look simpler on paper, but it would blend genuinely distinct responsibilities together and concentrate a large amount of organization-wide capability into a single account, which works against the same least-privilege, narrow-scoping principle this course applies to IAM permissions generally — just applied here at the account level instead.

**🎯 Senior:** *"Your organization currently manages GuardDuty, Security Hub, and Config directly from the management account, with about 15 people having standing access to it for this routine work. How would you use delegated administration to improve this, and how would you sequence the change?"*
**Model answer:** I'd first identify the appropriate delegated administrator account for these services — likely the existing Audit account if one is already established (Part 13 §3), given its natural alignment with security/compliance operational ownership, or a newly-provisioned dedicated account via Account Factory (Part 13 §2) if not. I'd then delegate each service individually from the management account, verifying after each delegation that the intended administrative capability actually works correctly from the new delegated account before proceeding to the next — a staged approach, similar in spirit to the incremental account-enrollment sequencing from Part 13 §1's Senior answer, reducing the risk of a single large, disruptive cutover. Only after confirming the delegated account fully replicates the needed administrative capability would I begin removing the 15 individuals' standing management-account access, replacing it with appropriately-scoped IAM access within the new delegated account instead — directly reducing the management account's access footprint from 15 standing users down to ideally just the small number of people who genuinely need occasional, infrequent management-account-level access for the few things that must remain there (like performing further delegation changes themselves).

**🎯 Architect:** *"Design the delegated administration strategy for a large enterprise with distinct security operations, identity/access management, cost/finance, and network operations teams, each needing organization-wide administrative capability for their respective domain, while keeping the management account's operational footprint minimal."*
**Model answer:** Establish four purpose-specific delegated administrator accounts, each mapped to one team's genuine ownership domain, following §4.2's principle directly rather than consolidating: a Security account (delegated administrator for GuardDuty, Security Hub, and paired with the centralized Log Archive/Audit architecture from Part 13 §3, since security operations and log/audit investigation are naturally the same team's responsibility), an Identity account (delegated administrator for IAM Identity Center, Part 2 §4), a Finance/Cost account (delegated administrator for AWS Cost and Usage Report aggregation and any organization-wide cost-management tooling), and a Network account (delegated administrator for organization-wide networking services like Transit Gateway sharing or Route 53 Resolver, Part 4 §4/§6, where centralized network administration is the natural ownership model). Each account's internal IAM is then scoped by its own owning team, independently, following standard least-privilege principles — the Security team doesn't need any access to the Finance account's capabilities and vice versa, and each team can operate their domain's organization-wide administrative work entirely within their own delegated account, with the management account's ongoing role reduced to essentially just the initial delegation designations themselves and any rare, genuinely account-structure-level changes (like adding an entirely new delegated domain in the future) that inherently require management-account-level authority. This directly achieves the "minimal management account footprint" goal while ensuring every team has full, appropriately-scoped organization-wide capability for their own domain, mapped cleanly onto the enterprise's actual team structure rather than an artificial, technically-convenient grouping.

## 17. Common Misconceptions

- "Delegated administration grants the delegated account broad access across every other account." False — per §4.1's warning, delegation is scoped specifically to the designated service's own administrative actions and data, not general cross-account access.
- "Delegating a service removes the management account's involvement entirely." Mostly false — the management account performs the initial delegation designation and retains the ultimate authority to revoke or re-delegate; its *ongoing, routine operational* involvement drops to near-zero, but it isn't removed from the picture structurally.
- "One delegated account handling everything is simpler and therefore better." False as a general practice — as §4.2 and the Architect answer establish, mapping delegation to genuine organizational ownership boundaries, even if that means multiple delegated accounts, is the more sound practice than a single, convenience-driven consolidation.

## 18. Key Takeaways

🔑 Delegated administration lets AWS Organizations-integrated services be administered organization-wide from a purpose-specific member account, rather than requiring standing management account access for routine operational work.
🔑 Delegation is per-service and scoped specifically to that service's administrative actions — not a general grant of broad cross-account access.
🔑 Different services should generally be delegated to different accounts based on genuine organizational ownership (security, identity, finance, networking), rather than consolidated into one account purely for convenience.
🔑 A delegated administrator account, while less catastrophic than the management account if compromised, still holds genuine organization-wide capability and warrants correspondingly strong protection.
🔑 Delegated administration and cross-account IAM roles work together, not as competing mechanisms — delegation grants the account its organization-wide capability; standard IAM governs who within that account can actually use it.

## 19. Related Concepts

- **AWS Organizations & SCPs** (Part 2 §5) — the foundational multi-account structure delegation operates within.
- **Centralized Logging & Audit Account Architecture** (Part 13 §3) — the Audit account frequently serves as the delegated administrator for security-focused services, a natural, common pairing.
- **GuardDuty, Security Hub, Config** (Part 2 §8, Part 8 §6) — common examples of services administered via delegation.
- **Guardrails — Preventive & Detective Control Operations** (Part 13 §5, next section) — the operational discipline of actually running the guardrails this Part's landing zone establishes, commonly performed from delegated administrator accounts.
