# IAM Permissions Boundary — Developer

**When to use:** Developers can create their own roles/policies but must never exceed a fixed ceiling.

**Status:** not yet verified against a real account (Verified: never, region: n/a).

A permissions boundary that caps what a developer role/user can ever do, regardless of what other identity-based policies are later attached to it. Set this as the *permissions boundary* on developer IAM users/roles — it's a ceiling, not a grant, so it must be combined with an actual permissions policy to grant real access.

## Files

| File | Purpose |
|---|---|
| [boundary-policy.json](boundary-policy.json) | Attach as the **permissions boundary** (not a regular policy) on developer IAM users/roles |

## How it works

- `AllowScopedServices` caps the *maximum* the boundary permits: S3, Lambda, DynamoDB, CloudWatch/Logs, and read-only EC2. The developer's actual permissions policy must still separately grant these — the boundary only sets the upper limit.
- `DenyIAMPrivilegeEscalation` blocks the classic boundary-bypass moves: creating new users/access keys, attaching or writing IAM policies, and `iam:PassRole` (which could otherwise be used to hand a Lambda or EC2 instance broader privileges than the developer has directly).
- `DenyBoundaryTampering` prevents a developer from creating a new principal or changing a boundary to anything other than this same policy — without this, a developer with `iam:CreateUser` could create a user with no boundary at all.
- `DenyOrganizationAndAccountActions` blocks AWS Organizations and account-level changes outright.

## Placeholders

| Placeholder | Replace with |
|---|---|
| `<ACCOUNT_ID>` | 12-digit AWS account ID |
| `<THIS_BOUNDARY_POLICY_NAME>` | The name this policy is given once created in IAM, so `DenyBoundaryTampering` can reference itself |

## Notes

- A permissions boundary alone grants nothing — the effective permissions are the **intersection** of the boundary and the identity's actual attached policy/policies.
- Adjust `AllowScopedServices` to match the services your developers actually need; this list is a reasonable starting cap, not a fixed standard.

## PassRole and role creation

- `iam:PassRole` is allowed only for roles matching `<DEV_ROLE_PREFIX>*` and only when passed to Lambda or EC2 (`iam:PassedToService`), so developers can create functions and launch instances without being able to hand a service a more privileged role. The identity policy must also allow `iam:PassRole`; the boundary only caps it.
- `iam:CreateRole` is allowed only when this same boundary is attached to the new role (`DenyBoundaryTampering`). Roles created this way start with no permissions, because attaching/putting role policies is denied — pre-provision the roles developers pass to services.

| Placeholder | Replace with |
|---|---|
| `<DEV_ROLE_PREFIX>` | Name prefix of the roles developers may pass to Lambda/EC2, e.g. `dev-` |
