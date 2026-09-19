# AWS Scripts

**When to use:** You need a quick CLI audit or report and don't want to build tooling.

**Status:** not yet verified against a real account (Verified: never, region: n/a).

CLI-based (AWS CLI + `jq`) automation scripts for recurring audit/ops tasks. All output CSV to stdout so results can be piped/redirected/filtered as needed.

## Index

| Script | Summary | Destructive? |
|---|---|---|
| [audit-public-s3-buckets.sh](audit-public-s3-buckets.sh) | Lists buckets missing public access block or granting public ACLs | No |
| [audit-unused-iam-roles.sh](audit-unused-iam-roles.sh) | Lists IAM roles unused beyond a day threshold (default 90) | No |
| [list-idle-ec2-instances.sh](list-idle-ec2-instances.sh) | Lists running instances below a CPU threshold over a lookback window | No |
| [cleanup-old-ebs-snapshots.sh](cleanup-old-ebs-snapshots.sh) | Deletes self-owned EBS snapshots older than a threshold, skipping AMI-referenced ones | **Yes** — dry-run by default, requires `--apply` |
| [s3-bucket-size-report.sh](s3-bucket-size-report.sh) | Reports size/object count per bucket via CloudWatch storage metrics | No |

## Requirements

- AWS CLI v2, configured with credentials/region for the target account (`aws configure` or `AWS_PROFILE`).
- `jq`.
- GNU `date` (`date -d`) — scripts are written for Linux/WSL/Git Bash, not macOS's BSD `date`. On macOS, install `coreutils` and alias `date` to `gdate`, or run under Docker/WSL.

## Conventions

- Any script that deletes or modifies resources defaults to a dry-run and requires an explicit `--apply` flag to act — see [cleanup-old-ebs-snapshots.sh](cleanup-old-ebs-snapshots.sh) for the pattern.
- Read-only/audit scripts print CSV (`header` row + `field,field,...`) so results compose with `grep`/`awk`/spreadsheet import.
- CloudWatch-metric-based scripts (idle EC2, bucket size) trade precision for speed — they read pre-aggregated metrics instead of enumerating every object/instance's real-time state, which is fine for a "candidates to review" list but not a billing-grade source of truth.
