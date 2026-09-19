# Resource Inventory

**When to use:** You want a scheduled, cross-region list of what is running in an account.

**Status:** not yet verified against a real account (Verified: never, region: n/a).

**Cost note:** Cost is small: API calls plus a few seconds of Lambda per run.

Scans every enabled region in the account and reports what's running: EC2 instances, EBS volumes, RDS instances, Lambda functions, ELBv2 load balancers, NAT gateways, and Elastic IPs — plus global S3 buckets. Also runs a Resource Groups Tagging API pass per region to surface any other *tagged* resource types not directly enumerated.

## Files

| File | Purpose |
|---|---|
| [lambda_function.py](lambda_function.py) | Function source (`lambda_handler` entrypoint) |
| [execution-role-policy.json](execution-role-policy.json) | Least-privilege policy for the function's execution role |

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `REGIONS` | all enabled regions | Comma-separated region list to scan instead of the whole account |
| `OUTPUT_S3_BUCKET` | — | If set, uploads the full JSON report (every resource, not just counts) to this bucket |
| `OUTPUT_S3_KEY_PREFIX` | `resource-inventory/` | Key prefix for the uploaded report |
| `SENDER_EMAIL` | — | SES-verified sender; if set with `RECIPIENT_EMAIL`, sends a **counts-only** summary email |
| `RECIPIENT_EMAIL` | — | Recipient for the summary email |

The Lambda return value always contains the summary counts, regardless of whether S3/SES are configured — useful for testing via `aws lambda invoke` without setting anything up.

## Deploy

```bash
# Package
cd aws/lambda-functions/resource-inventory
zip function.zip lambda_function.py

# Create the execution role (trust policy: lambda.amazonaws.com — see
# ../../cloudformation/lambda-basic/template.yaml for the equivalent
# AssumeRolePolicyDocument if you prefer to provision this via CloudFormation)
aws iam create-role --role-name resource-inventory-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'

# Fill in execution-role-policy.json placeholders first, then attach it
aws iam put-role-policy --role-name resource-inventory-role \
  --policy-name resource-inventory-policy \
  --policy-document file://execution-role-policy.json

# Create the function (increase --timeout for large accounts/many regions)
aws lambda create-function \
  --function-name resource-inventory \
  --runtime python3.13 \
  --handler lambda_function.lambda_handler \
  --role arn:aws:iam::<ACCOUNT_ID>:role/resource-inventory-role \
  --zip-file fileb://function.zip \
  --timeout 300 \
  --memory-size 256
```

Schedule it with EventBridge for a recurring report:

```bash
aws events put-rule --name daily-resource-inventory --schedule-expression "rate(1 day)"
aws lambda add-permission --function-name resource-inventory --statement-id eventbridge \
  --action lambda:InvokeFunction --principal events.amazonaws.com \
  --source-arn arn:aws:events:<REGION>:<ACCOUNT_ID>:rule/daily-resource-inventory
aws events put-targets --rule daily-resource-inventory \
  --targets "Id"="1","Arn"="arn:aws:lambda:<REGION>:<ACCOUNT_ID>:function:resource-inventory"
```

## Limitations

- **Tag-API coverage only, for anything outside the enumerated types.** The `OtherTaggedResources` section of the report comes from `resourcegroupstaggingapi:GetResources`, which only sees resources that have at least one tag. An untagged resource of a type not in the directly-enumerated list (EC2, EBS, RDS, Lambda, ELBv2, NAT gateways, EIPs, S3) will not appear in the report at all.
- **Default Lambda timeout (3s) is far too short** — set `--timeout` to at least a few minutes for accounts with many regions/resources; the function scans every enabled region sequentially.
- SES must be out of sandbox mode (or both sender and recipient verified) for `_email_summary` to succeed — the function still returns the full summary in its response either way, so email is optional for testing.

## Extending

To track a resource type not covered here, add a `_your_type(region)` collector following the same pattern as `_ec2_instances` etc., register it in `REGIONAL_COLLECTORS`, and add the matching `Describe`/`List` action to `execution-role-policy.json`.
