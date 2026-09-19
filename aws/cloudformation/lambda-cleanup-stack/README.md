# Lambda Cleanup Stack

One stack that deploys the [resource-cleanup](../../lambda-functions/resource-cleanup/), [resource-protect](../../lambda-functions/resource-protect/) and [resource-inventory](../../lambda-functions/resource-inventory/) functions: roles, a permissions boundary on the cleanup role, an SNS notice topic, a daily schedule, and the role EventBridge Scheduler uses for the follow-up runs.

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

## Limits

- The IAM Deny statements use the fixed tag key `Protect`; CloudFormation cannot parameterize a condition key. Extra protect tags are honoured by the function code but not by an IAM Deny. If you need an IAM Deny for another key, copy the statement from `permissions-boundary.json` in the cleanup folder.
- The Lambda code is too large for inline `ZipFile`, hence the S3 bucket and `package.sh`.
- The inventory function has no schedule; invoke it on demand.

## Cost

Three small functions, one daily invocation plus a few one-time schedules, an SNS topic and log groups. Well under a dollar a month.
