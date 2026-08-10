# Section 91 (Part 12): Teams, RBAC, and SSO in Terraform Cloud/Enterprise

## 1. Definition

**Plain language:** Terraform Cloud controls who can do what through teams — named groups of users, each granted a specific permission level (read, plan, write, or admin) on specific workspaces — and, for organizations with existing identity systems, those teams can be automatically populated and kept in sync through single sign-on (SSO) rather than managed by hand.

**Precise definition:** **Teams** in Terraform Cloud/Enterprise are the unit of access control: users are added to one or more teams, and each team is granted a **permission level** on a per-workspace basis — **Read** (view runs, state outputs, and configuration, no ability to trigger changes), **Plan** (can queue plans but not apply them), **Write** (can queue plans and apply runs, manage variables, and lock/unlock the workspace), and **Admin** (Write plus workspace settings, VCS connection, team access management, and deletion) — with a separate **organization-level owners team** holding org-wide administrative rights (billing, org settings, SSO configuration itself). **SSO** integration, typically via **SAML** (with some deployments supporting OIDC), lets an organization delegate authentication to its existing identity provider (Okta, Azure AD, PingFederate, etc.), and — through **team API-driven membership** or SAML group/attribute mapping — automatically synchronize which users belong to which TFC teams based on the identity provider's own group memberships, rather than requiring manual team management inside TFC itself.

> 💡 **Tip:** Permission levels are granted **per workspace**, not globally by default — a team with Write access on `app-api-prod` has no access at all to `infra-network` unless separately granted. This is easy to get backward when first configuring an organization: assuming a team's permission level is an organization-wide setting leads to either accidentally over-provisioning (granting broad access "to be safe") or confusing access-denied errors when a team correctly configured on one workspace has zero access on an adjacent one they assumed was covered by the same grant.

## 2. Why This Matters

- **Least-privilege access becomes enforceable at the workspace level**, not just at the organization level — a contractor or narrowly scoped team can get exactly Plan-only access to one workspace without any broader visibility into the organization's other infrastructure.
- **SSO eliminates a second identity system to maintain.** Without it, TFC user accounts and team membership are a parallel identity store an organization must manually keep in sync with who's actually employed and what role they hold — a well-known source of stale access (former employees retaining access, role changes not reflected).
- **The permission gradient (Read → Plan → Write → Admin) maps directly onto real operational risk levels.** A read-only auditor role, a plan-only reviewer role, and a write-capable operator role are meaningfully different risk profiles, and TFC's model lets an organization express that distinction precisely rather than an all-or-nothing access grant.
- **Team-based access scales far better than individually granted permissions.** Managing access via team membership (add/remove a user from a team) rather than per-user, per-workspace grants is the only practical approach once an organization has more than a handful of workspaces and engineers.
- **Compliance and audit requirements often mandate SSO and centralized access review.** Many regulated environments require that infrastructure-tooling access be provable as tied to centrally managed identity, not standalone credentials — SSO integration is frequently a hard requirement, not a convenience.

## 3. Prerequisites and Dependencies

Builds on the organization/workspace model ([§84](./Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md)) and assumes the run pipeline concepts from [§85](./Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md)–[§90](./Section-90-Part12-Cost-Estimation-Features.md) as context for what each permission level actually gates. General familiarity with SAML/SSO concepts is helpful but not required — this section explains the TFC-specific application of them. This is the final section of Part 12; [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) (opening Part 13) shifts to secrets-in-state risk, a topic that intersects with access control (who can read state containing secrets) but is a distinct concern from workspace permissioning.

## 4. Architecture / Conceptual Diagram

```text
   Identity Provider (Okta / Azure AD / PingFederate)
   Groups: "platform-team", "app-devs", "auditors"
              │
              │  SAML assertion / SSO login
              ▼
   ┌───────────────────────────────────────────────────┐
   │      TERRAFORM CLOUD ORGANIZATION                 │
   │                                                   │
   │  Team "platform-team"  ◄── mapped from IdP        │
   │  Team "app-devs"       ◄── mapped from IdP        │
   │  Team "auditors"       ◄── mapped from IdP        │
   │  Team "owners"          (org-wide admin, separate)|
   └────────────────┬──────────────────────────────────┘
                    │
      per-workspace permission grants
                    │
        ┌───────────┼────────────────┐
        ▼           ▼                ▼
  infra-network   app-api-prod   app-api-staging
  platform-team:   app-devs:      app-devs:
    Admin            Write          Write
  app-devs:         auditors:     auditors:
    Read              Read          Read
```

- Teams are org-level objects; permission grants connecting a team to a specific level of access exist per workspace.
- The "owners" team is structurally distinct from ordinary teams — it governs the organization itself (billing, SSO config, creating/deleting teams), not individual workspaces.
- SSO/SAML governs authentication and, where configured, team membership sync — it does not itself define per-workspace permission levels, which remain a TFC-side configuration.

## 5. Hands-On

### 5.1 Defining Teams and Workspace Permissions as Code

**Purpose:** Show the `tfe` provider representation of team creation and permission grants, continuing the "manage TFC with Terraform" pattern from [§85](./Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md) and [§88](./Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md).

**Syntax:**

```hcl
resource "tfe_team" "app_devs" {
  name         = "app-devs"
  organization = "acme-corp"
}

resource "tfe_team_access" "app_devs_write" {
  team_id      = tfe_team.app_devs.id
  workspace_id = tfe_workspace.app_api_prod.id
  access       = "write"
}

resource "tfe_team_access" "app_devs_read_network" {
  team_id      = tfe_team.app_devs.id
  workspace_id = tfe_workspace.infra_network.id
  access       = "read"
}
```

**Example usage and expected output:**

```bash
$ terraform apply
tfe_team.app_devs: Creating...
tfe_team.app_devs: Creation complete after 1s [id=team-8pQd3RtY]
tfe_team_access.app_devs_write: Creating...
tfe_team_access.app_devs_write: Creation complete after 1s
tfe_team_access.app_devs_read_network: Creating...
tfe_team_access.app_devs_read_network: Creation complete after 1s

Apply complete! Resources: 3 added, 0 changed, 0 destroyed.
```

**Production usage example:** A platform team codifies the entire access model — every team, every workspace grant — as version-controlled Terraform configuration, so access changes go through the same PR review process as infrastructure changes, and the current access state is always visible in Git rather than scattered across UI clicks.

**Common errors:** Granting `write` where `plan` would suffice (e.g., for a team that should review but not apply) over-provisions access — the four-level gradient exists specifically so grants can match actual need rather than defaulting to the broadest convenient level.

### 5.2 Configuring SAML SSO (Conceptual)

**Purpose:** Show the shape of SSO configuration and its relationship to team membership.

**Example usage and expected output:**

```text
Organization Settings → SSO

Identity Provider Metadata URL: https://acme.okta.com/app/exk.../sso/saml/metadata
Team membership mapping: SAML group attribute → TFC team
  "platform-team" (IdP group) → "platform-team" (TFC team)
  "app-devs"      (IdP group) → "app-devs"      (TFC team)

$ # After SSO login, a user's team membership reflects their IdP group
$ # membership automatically on next login — no manual TFC-side add needed.
```

**Production usage example:** When an engineer joins the `app-devs` group in Okta as part of onboarding, their next TFC login via SSO automatically places them in the corresponding TFC team with whatever workspace access that team already has — no separate manual TFC provisioning step required, and removal from the IdP group similarly revokes access on next sync.

**Common errors:** Assuming SSO alone revokes access instantly on IdP group removal — actual revocation timing depends on session expiry and sync mechanism specifics; a still-active TFC session isn't necessarily terminated the instant IdP group membership changes, which matters for time-sensitive offboarding.

## 6. Production Usage Notes

- **The owners team should stay small and deliberately curated.** Because it grants organization-wide administrative control (including SSO configuration itself and the ability to manage other teams), broad owners-team membership defeats the purpose of the granular per-workspace model built on top of it.
- **Team API tokens (distinct from individual user tokens) are the standard credential for automation acting on behalf of a team's granted access** — using them instead of a personal user token means automation's access lifecycle is tied to the team, not to any one individual's employment status.
- **SSO team-membership sync depends on the specific mapping mechanism configured** (SAML group attributes, or a separate directory-sync integration) — not every SSO setup automatically manages TFC team membership out of the box; some organizations configure SSO for authentication only and still manage team membership manually inside TFC.

## 7. Security Considerations

- Workspace-level permission grants are the actual enforcement boundary for who can trigger an apply against real infrastructure — reviewing these grants (who has Write/Admin on production workspaces) is as security-relevant as reviewing cloud IAM policies, and should receive comparable audit attention.
- SSO doesn't eliminate the need for TFC-side access review — it manages _authentication_ and, if configured, team _membership_, but per-workspace permission grants are still a TFC-native configuration surface that needs its own periodic review independent of IdP hygiene.
- Read-level access on a workspace still exposes state outputs, which can contain sensitive values if not properly marked `sensitive` ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) — "Read" being the lowest permission tier doesn't mean it's risk-free if state hygiene elsewhere in the workspace is poor; this is the direct link into the secrets-in-state risk covered next in [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                           | Likely Cause                                                                                                                                                       | Resolution Path                                                                                                                                                                   |
| --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A user with correct SSO login can't access a workspace they should have access to | Team membership sync hasn't run yet (stale session), or the workspace-level grant for their team was never configured                                              | Have the user re-authenticate (fresh session); verify the specific `tfe_team_access` grant exists for that workspace                                                              |
| A team has access to more workspaces than expected                                | Overly broad grants configured (e.g., granted at a level intended to be workspace-specific but applied more widely), or leftover grants from a past reorganization | Audit `tfe_team_access` resources (or UI equivalent) against current intended access model; remove stale grants                                                                   |
| Removing a user from an IdP group doesn't immediately revoke their TFC access     | Active session hasn't expired yet, or SSO isn't configured to sync team membership (auth-only SSO setup)                                                           | Understand the specific sync mechanism in use; for time-sensitive offboarding, manually remove team membership in TFC as a backstop rather than relying solely on IdP sync timing |
| A CI pipeline using a personal API token stops working after an employee leaves   | Automation was built on an individual user token rather than a team or organization token                                                                          | Migrate automation credentials to team/organization-scoped tokens as a standing practice, not just a reactive fix                                                                 |

## 9. Best Practices

- Grant the minimum permission level (Read/Plan/Write/Admin) that satisfies a team's actual need per workspace — default to narrower, widen only when a concrete need arises.
- Keep the owners team minimal and treat membership changes to it with the same rigor as granting root/admin access on any other critical system.
- Configure SSO with team-membership sync where the organization's identity provider supports it, and treat IdP group membership as the source of truth for team composition rather than manually maintaining both in parallel.
- Manage teams and workspace access grants as Terraform configuration (via the `tfe` provider) so access changes are reviewable and auditable through the same PR process as any other infrastructure change.

## 10. Common Anti-Patterns / Mistakes

- **Defaulting every team to Write or Admin "to avoid access-denied tickets."** This collapses the entire point of the permission gradient and makes a compromised or careless account's blast radius far larger than necessary.
- **Assuming permission grants are organization-wide rather than per-workspace.** Leads to either accidental over-provisioning or confusing, unexpected access-denied errors on workspaces the team assumed was covered.
- **Relying on individual user API tokens for production automation.** Ties automation credential lifecycle to a specific person's employment and account status, breaking silently when that person's access changes for unrelated reasons.
- **Treating SSO configuration as a one-time setup with no ongoing review.** Group-to-team mappings drift from actual organizational structure over time if not periodically reconciled.

## 11. Interview Questions

**🎯 Beginner:** _"What are the four workspace permission levels in Terraform Cloud, from lowest to highest?"_
**Model answer:** Read (view runs, state outputs, and configuration, no changes), Plan (can queue plans but not apply), Write (can queue plans, apply runs, manage variables, lock/unlock the workspace), and Admin (Write plus workspace settings, VCS connection management, and team access control for that workspace).
_What the interviewer is probing for:_ Basic factual recall of the permission model, foundational to any access-control discussion about TFC.

**🎯 Intermediate:** _"Are workspace permissions granted per team globally across an organization, or per workspace? Why does that distinction matter?"_
**Model answer:** Per workspace — a team's permission level is granted individually on each workspace it should have access to, not as an organization-wide setting. This matters because it's the mechanism that actually enables least-privilege access: a team can have Write on their own application's workspaces and no access at all (or Read-only) on unrelated workspaces like shared networking or another team's application, without needing separate organizations or heavyweight access boundaries to achieve that isolation.
_What the interviewer is probing for:_ Whether the candidate understands this as the actual enforcement mechanism, not just a vague "there are permission levels" answer.

**🎯 Senior:** _"How does SSO integration change the operational model for managing team membership in Terraform Cloud, and what doesn't it automatically solve?"_
**Model answer:** With SAML SSO and group-to-team mapping configured, a user's TFC team membership is automatically derived from their identity provider's group membership on login, removing the need to manually add/remove users in TFC as roles or employment change — the IdP becomes the single source of truth for "who belongs to what team." What it doesn't automatically solve: the workspace-level permission grants for each team (Read/Plan/Write/Admin per workspace) are still a TFC-native configuration that needs its own review process, independent of IdP hygiene; and revocation timing on IdP-side changes depends on session lifetime and sync mechanism, so it's not necessarily instantaneous — sensitive, time-critical offboarding may still need a manual TFC-side backstop rather than fully trusting sync latency.
_What the interviewer is probing for:_ Nuanced understanding that SSO addresses authentication/membership sync specifically, not the full access-control picture end to end.

**🎯 Architect:** _"Design the team and permission structure for an organization with a platform team, three application teams, an auditing/compliance team, and a strict requirement that no single compromised account can apply to production infrastructure alone."_
**Model answer:** Platform team gets Admin on shared/foundational workspaces (networking, IAM baseline) and no default access to application workspaces beyond what's needed for support. Each application team gets Write on their own workspaces only, with no cross-team access by default. The auditing/compliance team gets Read across all workspaces org-wide (visibility without change capability) — a deliberate exception to per-workspace scoping justified by the audit function's legitimate need for broad visibility. The owners team stays minimal (a small number of senior platform/security staff). To satisfy "no single compromised account can apply to production alone," permission grants alone aren't sufficient — this requires pairing RBAC with workspace-level run-pipeline controls: manual apply confirmation ([§85](./Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md)) rather than auto-apply on production workspaces, so even a team member with Write access triggers a run that still requires a distinct confirmation action, and ideally a required-reviewers policy on the backing VCS repository so the plan itself was reviewed by a second person before it could even be merged. The RBAC model and the run-pipeline gating are complementary controls; RBAC alone (even well-scoped) doesn't achieve a true two-person rule without the pipeline-level confirmation step working alongside it.
_What the interviewer is probing for:_ Whether the candidate can compose the permission model with pipeline controls (auto-apply settings, VCS review requirements) to actually achieve a stated security property, rather than treating RBAC as sufficient in isolation.

## 12. Common Misconceptions

1. **"A team's permission level applies across the whole organization."** Permission grants are per-workspace; a team can have entirely different access levels on different workspaces.
2. **"SSO automatically manages team membership."** Only true if group-to-team mapping is explicitly configured; some organizations use SSO purely for authentication and still manage team membership manually.
3. **"Read access is essentially risk-free since it can't trigger changes."** Read access still exposes state outputs, which can leak sensitive values if `sensitive` marking ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) and broader state hygiene aren't properly maintained.
4. **"RBAC alone enforces a two-person rule for production applies."** Achieving that requires pairing workspace permissions with pipeline controls like manual apply confirmation and required VCS review — permission grants alone don't guarantee a second reviewer touched the change.

## 13. 🔑 Key Takeaways

- Terraform Cloud's access model is team-based, with four workspace-level permission tiers (Read, Plan, Write, Admin) granted per workspace, not organization-wide.
- The organization's owners team is structurally distinct, holding org-wide administrative control and should stay minimal and tightly reviewed.
- SSO (typically SAML) delegates authentication to an existing identity provider and, where configured, syncs team membership from IdP groups — but per-workspace permission grants remain a separate, TFC-native configuration surface.
- Team-based, workspace-scoped grants are the enforcement mechanism for least-privilege access — defaulting broadly (Write/Admin everywhere) defeats the model's purpose.
- Achieving stronger guarantees like a two-person production-apply rule requires combining RBAC with pipeline controls (manual apply confirmation, required VCS review), not RBAC alone.

## 14. Related Concepts & What's Next

This closes Part 12's coverage of Terraform Cloud and Enterprise as the governance/collaboration layer built on everything in Parts 1–11. Part 13 shifts to security and secrets management specifically — [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) opens with the risk that Terraform state itself frequently contains secrets in plaintext, and the access-control model covered here (who can read a workspace's state via Read-level access) is one of the direct mitigations that section will revisit from the secrets-exposure angle.

**Next Section:** [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) — `Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md`
