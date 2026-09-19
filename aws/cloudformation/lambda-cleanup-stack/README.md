# Lambda Cleanup Stack

One stack that deploys the [resource-cleanup](../../lambda-functions/resource-cleanup/), [resource-protect](../../lambda-functions/resource-protect/), [resource-inventory](../../lambda-functions/resource-inventory/) and (optionally) [cost-report](../../lambda-functions/cost-report/) functions: roles, a permissions boundary on the cleanup role, an SNS notice topic, a daily schedule, and the role EventBridge Scheduler uses for the follow-up runs.

**When to use:** deploying the cleanup toolkit into an account without hand-filling the placeholders in the per-function policy files.

**Status:** not yet verified. cfn-lint clean, never deployed. (Verified: never)

## Deploy

```bash
./package.sh <code-bucket>            # zips the three functions and uploads them
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name toolkit-cleanup \
  --capabilities CAPABILITY_IAM \
  --parameter-overrides CodeBucket=<code-bucket> Regions=ap-south-1 NoticeEmail=you@example.com
```

`DryRun` is `true` by default: the function only reports. Read a few daily reports, then redeploy with `DryRun=false`.

## Parameters worth knowing

| Parameter | Effect |
|---|---|
| `DryRun` | `true` reports only; `false` tags, stops and deletes |
| `Regions` | Allowlist for cleanup and protect |
| `DailyRunCron` | UTC; default 10:00 (15:30 IST). Keep it away from other automation |
| `FastTrackTagKey` | Empty disables fast track. Set it on fast-churn test accounts only |
| `FastTrackAmiAffixes` | Empty means fast-track AMIs are never deleted |
| `ExtraProtectTags` | Code-level protection only (see below) |
| `NoticeEmail` | Must confirm the SNS subscription email |
| `EnableCostReport` | `true` adds the cost-report function, its on-demand DynamoDB table (TTL on `ExpiresAt`), an hourly `record` schedule and a monthly `report` schedule (06:00 UTC on the 3rd) |
| `CostReportBucket` | Optional existing bucket for the monthly JSON; without it the report only goes to SNS |

## Limits

- The IAM Deny statements use the fixed tag key `Protect`; CloudFormation cannot parameterize a condition key. Extra protect tags are honoured by the function code but not by an IAM Deny. If you need an IAM Deny for another key, copy the statement from `permissions-boundary.json` in the cleanup folder.
- The Lambda code is too large for inline `ZipFile`, hence the S3 bucket and `package.sh`.
- The inventory function has no schedule; invoke it on demand.
- The cost-report summary goes to the same SNS topic as the cleanup notices. Cost Explorer must be enabled in the account, and the report is only meaningful after a few days of hourly samples.

## Cost

Four small functions, one daily cleanup run, about 730 hourly cost samples a month (within the free tier), a few Cost Explorer requests a month (about $0.01 each), an SNS topic, an on-demand DynamoDB table and log groups. A few dollars a month at most.
