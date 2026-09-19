# IAM Cross-Account Role Assumption

**When to use:** A person, pipeline or vendor in another account needs to assume a role in yours.

**Status:** not yet verified against a real account (Verified: never, region: n/a).

Lets a principal in Account A assume a role in Account B, using an external ID to guard against the confused-deputy problem. This is the standard pattern for cross-account admin access, CI/CD deploy roles, and third-party tool access (e.g. monitoring vendors).

## Files

| File | Attach to | Purpose |
|---|---|---|
| [trust-policy.json](trust-policy.json) | The role's trust policy in Account B (target account) | Defines who is allowed to assume this role |
| [permissions-policy.json](permissions-policy.json) | An IAM user/role in Account A (source account) | Grants that principal permission to call `sts:AssumeRole` on the target role |

## Placeholders

| Placeholder | Replace with |
|---|---|
| `<TRUSTED_ACCOUNT_ID>` | 12-digit AWS account ID of the source account (Account A) |
| `<EXTERNAL_ID>` | A shared secret string agreed between both parties, required when a third party (not just another of your own accounts) is assuming the role |
| `<TARGET_ACCOUNT_ID>` | 12-digit AWS account ID of the account owning the role being assumed (Account B) |
| `<TARGET_ROLE_NAME>` | Name of the IAM role in Account B to assume |

## Notes

- `sts:ExternalId` is required by AWS best practice whenever a third party assumes your role (prevents them from being tricked into assuming a role on your behalf for an unrelated customer). For assumption between two accounts you own, it's optional but still good hygiene — omit the `Condition` block if not needed.
- The target role (Account B) still needs its own permissions policy attached (separate from the trust policy) defining what the assumed role can actually do once assumed.
- Add an MFA condition (`aws:MultiFactorAuthPresent`) to the trust policy for higher-privilege roles — see [iam-enforce-mfa](../iam-enforce-mfa/) for the underlying pattern.
