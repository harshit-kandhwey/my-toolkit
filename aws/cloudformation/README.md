# AWS CloudFormation Templates

Reusable CloudFormation templates, one pattern per folder, each independently deployable.

## Index

| Template | Folder | Summary |
|---|---|---|
| VPC — basic | [vpc-basic/](vpc-basic/) | Two-AZ VPC with public/private subnets, IGW, and a single NAT gateway |
| S3 — secure bucket | [s3-secure-bucket/](s3-secure-bucket/) | Encrypted, versioned, publicly-blocked bucket with TLS-only bucket policy |
| EC2 — single instance | [ec2-instance/](ec2-instance/) | One EC2 instance, IMDSv2-only, latest AL2023 AMI via SSM parameter |
| IAM — cross-account role | [iam-cross-account-role/](iam-cross-account-role/) | Role assumable from a trusted account, external-ID guarded |
| Lambda — basic function | [lambda-basic/](lambda-basic/) | Function with a least-privilege execution role and explicit log retention |
| Lambda — cleanup toolkit stack | [lambda-cleanup-stack/](lambda-cleanup-stack/) | Cleanup, protect and inventory functions with roles, permissions boundary, SNS topic and daily schedule |

## Conventions

- Each folder is a standalone `template.yaml` deployable with `aws cloudformation deploy`, plus a README covering parameters, outputs, the deploy command, and stack-specific notes.
- Parameters with no safe default (VPC/subnet IDs, account IDs, secrets) are left required rather than defaulted, so a stack can't be deployed into the wrong network or with an overly permissive fallback by accident.
- Templates that create named IAM resources need `--capabilities CAPABILITY_IAM` or `CAPABILITY_NAMED_IAM` on deploy — called out in each template's own README.
