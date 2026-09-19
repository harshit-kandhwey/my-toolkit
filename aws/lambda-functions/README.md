# AWS Lambda Functions

Standalone Lambda function source, one folder per function. Unlike [cloudformation/lambda-basic](../cloudformation/lambda-basic/) (a generic, empty-handler template), these are complete, working functions meant to be deployed as-is and configured via environment variables.

## Index

| Function | Folder | Summary | Destructive? |
|---|---|---|---|
| Resource inventory | [resource-inventory/](resource-inventory/) | Lists EC2/EBS/RDS/Lambda/ELB/NAT/EIP/S3 resources across all enabled regions; optional S3 report + email summary | No |
| Resource cleanup | [resource-cleanup/](resource-cleanup/) | Notify-then-act cleanup of aged, unprotected EC2/EBS/snapshots; snapshots and stops (never deletes) RDS; report-only for the rest | **Yes** — dry-run by default, `DRY_RUN=false` to act |
| Resource protect | [resource-protect/](resource-protect/) | Lists what cleanup has queued and applies the exact protect tag to resources you name | Tags only |
| Cost report | [cost-report/](cost-report/) | Samples running EC2/RDS instances hourly into DynamoDB, then prices the hours per instance from Cost Explorer effective rates and reconciles against billed hours | No (writes its own table and report) |

## Conventions

- Each folder is a deployable unit: `lambda_function.py` (entrypoint `lambda_handler`), an `execution-role-policy.json` scoped to exactly what that function needs, and a README with env vars, deploy steps, and gotchas.
- Any function that can modify/delete resources defaults to a dry-run mode and requires an explicit opt-in environment variable to act for real — same convention as [../scripts/cleanup-old-ebs-snapshots.sh](../scripts/cleanup-old-ebs-snapshots.sh).
- Functions use only `boto3` (available in the standard Lambda Python runtime) — no third-party dependencies, no layers required.
- IAM policies in `execution-role-policy.json` use `<PLACEHOLDER>` tokens the same way as [../policies/](../policies/) — fill them in before attaching.
