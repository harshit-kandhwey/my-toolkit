# aws/

Reusable AWS configs, templates, and scripts — organized by kind, then by pattern.

```
aws/
├── policies/          # Reusable IAM & resource-based policy JSON
├── cloudformation/    # Reusable CloudFormation templates
├── scripts/           # AWS CLI automation scripts (audits, cleanup, reports)
└── lambda-functions/  # Deployable Lambda functions (inventory, cleanup, protect)
```

## What's here

- **[policies/](policies/)** — one folder per access pattern (S3 cross-account, scoped folder access, read-only, MFA enforcement, cross-account role assumption, developer permissions boundary). Every file is valid JSON with `<PLACEHOLDER>` tokens; see [policies/README.md](policies/README.md) for the full index and conventions.
- **[cloudformation/](cloudformation/)** — one folder per template (VPC, secure S3 bucket, EC2 instance, IAM cross-account role, Lambda function), each independently deployable via `aws cloudformation deploy`; see [cloudformation/README.md](cloudformation/README.md).
- **[scripts/](scripts/)** — AWS CLI + `jq` scripts for recurring audit/cleanup/reporting tasks, CSV output, dry-run-by-default for anything destructive; see [scripts/README.md](scripts/README.md).
- **[lambda-functions/](lambda-functions/)** — complete, deployable Lambda functions: a cross-region resource inventory, a notify-then-act cleanup function, and a companion that protects queued resources; see [lambda-functions/README.md](lambda-functions/README.md).

## Conventions across all four

- Folders are `kebab-case`, named after the pattern/purpose, not just the AWS service.
- Nothing here embeds real account IDs, ARNs, or secrets — everything uses `<PLACEHOLDER>` tokens or required (no-default) parameters.
- Every folder/script has its own README covering what it does, required inputs, and any gotchas — check there before use, not just this file.
