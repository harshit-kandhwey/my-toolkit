# Cost Report

**When to use:** Cost Explorer shows spend per service and usage type, but you need it per instance (for example, which of the `c6a.16xlarge` instances drives a $10k/month bill).

**Status:** not yet verified against a real account (Verified: never, region: n/a). Passes 7 offline moto tests. The Cost Explorer calls are replaced by a stub in those tests, so the real response shape and the region usage-type prefixes are unchecked.

Two actions:

| Action | Schedule | What it does |
|---|---|---|
| `record` (default) | hourly | Adds `SAMPLE_HOURS` to one DynamoDB row per running EC2 / available RDS instance for the current month |
| `report` | monthly, about the 3rd | Prices each row with the account's effective rate, writes `cost-report/YYYY-MM.json` to S3, publishes a top-N summary to SNS |

## How the cost is worked out

Per usage type (for example `APS3-BoxUsage:c6a.16xlarge`) the report takes Cost Explorer's **amortized** cost divided by its billed hours. That is the effective hourly rate, so Savings Plans and reservations are already reflected. Each instance's cost is its sampled hours times that rate.

The report also reconciles sampled hours against billed hours per usage type (`CoveragePercent`). Low coverage means instances in regions outside `REGIONS`, hours before this function was deployed, or instances that started and stopped between two hourly samples.

## Usage

```bash
aws lambda invoke --function-name cost-report --payload '{"action":"record"}' \
  --cli-binary-format raw-in-base64-out out.json
aws lambda invoke --function-name cost-report --payload '{"action":"report","month":"2030-01"}' \
  --cli-binary-format raw-in-base64-out out.json && cat out.json
```

Schedule `record` with `rate(1 hour)` and `report` with `cron(0 6 3 * ? *)` (the 3rd, after the month's bill has settled).

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `TABLE_NAME` | required | DynamoDB table, partition key `pk` (S), sort key `sk` (S), TTL attribute `ExpiresAt` |
| `REGIONS` | the function's own region | Regions to sample, comma-separated, or `all` |
| `SAMPLE_HOURS` | `1` | Hours each `record` run represents (match your schedule) |
| `REPORT_BUCKET` / `REPORT_PREFIX` | none / `cost-report/` | Where the monthly JSON goes |
| `SNS_TOPIC_ARN` | none | Receives the summary |
| `TOP_N` | `10` | Resources listed in the summary |

## Files

- `lambda_function.py` — the function
- `execution-role-policy.json` — least-privilege role; fill in the `<PLACEHOLDER>` tokens
- `test_lambda_function.py` — moto tests (run with `python -m pytest` from this folder)

## Limits and gotchas

- **Sampling, not events.** An instance that runs for 20 minutes between two samples is missed; one sampled at :59 and stopped at :01 counts a full hour. Coverage in the report shows the size of the error. Precise uptime would need EC2 state-change events, which this version does not use.
- **Only EC2 instance hours and RDS instance hours.** EBS, snapshots, data transfer, NAT and everything else stay in Cost Explorer's service view.
- **Blended rate per usage type.** Instances of the same type and region share one rate, even if only some are covered by a Savings Plan.
- **Regions missing from `REGION_PREFIX`** cannot be priced and are listed as `Unpriced`. The prefix table has not been verified against a real bill.
- **Spot and non-default OS/tenancy** usage types are not matched.
- **Cost Explorer needs enabling** in the account, and each `report` run makes a few `GetCostAndUsage` calls (about $0.01 each).
- Rows are already one summary per resource per month, so there is nothing to compact; they expire through the DynamoDB TTL after about 400 days.
- Deploy per account; the report carries each row's `Account`. A cross-account roll-up bucket is future work.

## Cost

An hourly invocation is under 1,000 tiny runs a month (free tier), a small on-demand DynamoDB table, and a handful of Cost Explorer requests a month.
