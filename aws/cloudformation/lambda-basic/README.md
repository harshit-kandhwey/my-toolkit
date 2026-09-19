# Lambda — Basic Function

**When to use:** You need a starting point for a new Lambda with least-privilege logging.

**Status:** not yet verified against a real account (Verified: never, region: n/a).

**Cost note:** Negligible cost at idle.

A minimal Lambda function with its own least-privilege execution role (CloudWatch Logs write access only, scoped to its own log group) and an explicit log retention period, so logs don't accumulate forever at the account's default (never expire).

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `FunctionName` | `my-basic-function` | Name of the Lambda function |
| `Runtime` | `python3.13` | Python runtime only (the inline handler is Python) |
| `LogRetentionInDays` | `30` | CloudWatch Logs retention; must be a value CloudWatch supports (1, 3, 5, 7, 14, 30, 60, 90, ...) |

## Outputs

| Output | Description |
|---|---|
| `FunctionArn` | ARN of the created function |
| `ExecutionRoleArn` | ARN of the function's execution role |

## Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name my-basic-function \
  --capabilities CAPABILITY_IAM
```

## Notes

- Ships with an inline placeholder handler (`ZipFile`) that just returns HTTP 200 — replace the `Code` property with an `S3Bucket`/`S3Key` reference (or a `sam`/`aws lambda update-function-code` follow-up) once you have real function code; inline `ZipFile` only supports single-file Python/Node runtimes and a handful of KB of code.
- The execution role is scoped to `logs:CreateLogStream`/`logs:PutLogEvents` on its own log group only — add further `Policies:` statements as the function needs to touch other services (e.g. S3, DynamoDB), rather than attaching a broad managed policy.
- `DependsOn: LogGroup` ensures the log group (with its retention policy) exists before Lambda's own implicit log group creation would otherwise apply the account default of "never expire."
- If a function with this name ever ran outside this stack, its auto-created `/aws/lambda/<name>` log group survives and makes the stack fail with "already exists" — delete that log group first.
- The log group has `DeletionPolicy: Retain`, so the function's logs outlive the stack. Delete `/aws/lambda/<name>` by hand after removing the stack, or the next deploy with the same name fails with "already exists".
