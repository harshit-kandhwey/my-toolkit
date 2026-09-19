# IAM — Cross-Account Role

**When to use:** You need to create the target-account role for cross-account access as code.

**Status:** not yet verified against a real account (Verified: never, region: n/a).

CloudFormation version of the [iam-assume-role-cross-account](../../policies/iam-assume-role-cross-account/) policy pattern: creates the target-account role itself (trust policy + attached permissions) in one stack, rather than hand-assembling the JSON.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `TrustedAccountId` | — | 12-digit account ID allowed to assume this role |
| `ExternalId` | — | Confused-deputy guard token (2–1224 chars). Not a secret: it is readable in the role's trust policy via `iam:GetRole` |
| `ManagedPolicyArn` | `arn:aws:iam::aws:policy/SecurityAudit` | Managed policy defining what the role can do once assumed |

## Outputs

| Output | Description |
|---|---|
| `RoleArn` | ARN of the created role — this is what the source account's principal assumes |

## Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name cross-account-role \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides TrustedAccountId=111111111111 ExternalId='<external-id>' \
  --no-fail-on-empty-changeset
```

## Notes

- `--capabilities CAPABILITY_IAM` is required because this stack creates a named IAM role.
- Swap `ManagedPolicyArn` for a custom policy ARN (or add a `Policies:` inline block) once the AWS-managed `SecurityAudit` default is too broad or too narrow for the real use case.
- The trusted account's own principal still needs an `sts:AssumeRole` permissions policy pointed at this role's output ARN — see the paired [permissions-policy.json](../../policies/iam-assume-role-cross-account/permissions-policy.json).
