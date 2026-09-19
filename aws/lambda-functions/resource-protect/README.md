# Resource Protect

**When to use:** [resource-cleanup](../resource-cleanup/) has queued something you need to keep, and you want to protect it without hand-typing tags.

**Status:** not yet verified against a real account (Verified: never, region: n/a). Passes 4 offline moto tests.

Lists resources queued for cleanup and applies the exact protect tag to the ones you name, so a misspelt tag can't leave a resource exposed. It also clears the cleanup state, so the resource stops counting down.

## Usage

```bash
# What is queued?
aws lambda invoke --function-name resource-protect --payload '{"action":"list"}' \
  --cli-binary-format raw-in-base64-out out.json && cat out.json

# Protect specific resources
aws lambda invoke --function-name resource-protect \
  --payload '{"action":"protect","ids":["i-0abc123","vol-0def456"]}' \
  --cli-binary-format raw-in-base64-out out.json && cat out.json
```

`protect` returns `Protected` (tagged), `NotInQueue` (IDs that weren't queued, left untouched) and `Errors`.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `REGIONS` | the function's own region | Regions to search, comma-separated, or `all` |
| `PROTECT_TAG_KEY` / `PROTECT_TAG_VALUE` | `Protect` / `true` | Must match resource-cleanup's settings |

## Files

| File | Purpose |
|---|---|
| [lambda_function.py](lambda_function.py) | Function source |
| [execution-role-policy.json](execution-role-policy.json) | Execution role policy |
| [test_lambda_function.py](test_lambda_function.py) | Offline moto tests |

## Deploy

Same pattern as [resource-cleanup](../resource-cleanup/#deploy): zip `lambda_function.py`, create a role with `execution-role-policy.json`, and create the function with `--handler lambda_function.lambda_handler`. No schedule is needed; it is invoked on demand.

## Safety notes

- **Restrict who can invoke it.** Anyone who can invoke this function can protect any queued resource. Grant `lambda:InvokeFunction` only to the people who should be able to.
- Only resources already queued (carrying `Cleanup:NotifiedAt`) can be protected here; use the console or CLI to tag anything else.
