# AWS Policies

Reusable IAM and resource-based policy JSON, organized one pattern per folder. Every policy uses `<PLACEHOLDER>` tokens for values that must be filled in before use — see each folder's README for what to replace and why.

## Index

| Pattern | Folder | Summary |
|---|---|---|
| S3 cross-account access | [s3-cross-account-access/](s3-cross-account-access/) | IAM + bucket policy pair granting an Account B principal access to an Account A bucket |
| S3 scoped folder access | [s3-scoped-folder-access/](s3-scoped-folder-access/) | Limits a principal to one key prefix ("folder") within a bucket |
| S3 read-only access | [s3-read-only-access/](s3-read-only-access/) | List + get access to a bucket, no write/delete |
| IAM enforce MFA | [iam-enforce-mfa/](iam-enforce-mfa/) | Denies all actions except self-service MFA setup unless the session used MFA |
| IAM cross-account role assumption | [iam-assume-role-cross-account/](iam-assume-role-cross-account/) | Trust + permissions policy pair for assuming a role in another account |
| IAM permissions boundary — developer | [iam-permissions-boundary-developer/](iam-permissions-boundary-developer/) | Caps maximum developer privileges and blocks IAM privilege-escalation paths |

## Conventions

- One folder per pattern, `kebab-case` named after what it does, not the service alone.
- Every JSON file is valid, parseable JSON — no inline comments. Placeholder explanations live in the folder's README instead.
- Placeholders use `<SCREAMING_SNAKE_CASE>` and are listed in a table in the folder's README.
- A folder pairs an IAM (identity-based) policy with a resource-based policy only when the pattern genuinely requires both sides (e.g. cross-account access); single-sided patterns get a single file.
