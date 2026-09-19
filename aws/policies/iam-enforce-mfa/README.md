# IAM Enforce MFA

**When to use:** IAM users with console/CLI access must be forced to use MFA.

**Status:** not yet verified against a real account (Verified: never, region: n/a).

Denies all actions except a small self-service allowlist (managing your own password and MFA device) unless the session was authenticated with MFA. This is the standard AWS-recommended "force MFA" pattern for IAM users with console/CLI access.

## Files

| File | Purpose |
|---|---|
| [iam-policy.json](iam-policy.json) | Attach to IAM users (or a group) that must use MFA |

## How it works

- The first three statements allow an unauthenticated-by-MFA session to view account info and set up/manage its own password and virtual MFA device — otherwise a user without MFA configured could never bootstrap it.
- `DenyAllExceptListedIfNoMFA` denies every action *not* in that same allowlist when `aws:MultiFactorAuthPresent` is `false` or absent (`BoolIfExists` — covers the case where the condition key isn't present at all, e.g. access keys without MFA context).

## Notes

- No placeholders — this policy is self-contained and scopes to `${aws:username}`, the session's own IAM user.
- Attach as a **managed policy on a group**, not inline per-user, so it stays consistent as users are added.
- This does not enforce MFA on API access via long-lived access keys directly — pair with a policy requiring `sts:GetSessionToken`-issued temporary credentials for anything beyond the allowlist, or disable long-lived keys entirely in favor of IAM Identity Center / role assumption.
- `iam:CreateVirtualMFADevice` is allowed on `mfa/*` (not only `mfa/${aws:username}`) because the console often creates a device whose name isn't the username; scoping it would lock users out of MFA setup. `iam:DeleteVirtualMFADevice` is scoped to `mfa/${aws:username}` so a user without MFA cannot delete other people's unassigned devices. A stale device with a different name has to be removed by an admin.
