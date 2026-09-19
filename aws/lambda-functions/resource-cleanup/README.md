# Resource Cleanup

**When to use:** You want aged, unprotected resources found, announced, and acted on automatically, with a window for people to protect what they need.

**Status:** not yet verified against a real account (Verified: never, region: n/a). Passes 27 offline moto tests. **Start in `DRY_RUN=true` and keep it there until it has passed a sandbox test.**

**Cost note:** Small run cost. The risk is acting on the wrong resource, not the bill.

Runs **once a day** for discovery. When it tags or stops something it books its own one-time follow-up runs (EventBridge Scheduler) for the exact moment the next step is due, so the timeline is precise without polling. State lives in resource tags, so there is no database.

Example (fast-track instance):

| Time | What happens |
|---|---|
| 3:30 PM | Daily run finds the instance, tags it, publishes the SNS notice, books a follow-up for 5:30 PM |
| 5:30 PM | Follow-up run: the instance is still unprotected, so it is stopped (paused); a follow-up is booked for 11:30 PM |
| 11:30 PM | Follow-up run: 6 hours after the stop, the instance is terminated |

Follow-ups fire one minute after the due time. If one is missed, the next daily run acts on anything already due.

## What it does per group

| Group | Resources | Action |
|---|---|---|
| Compute | EC2 instances | Notice, then **stop**, then **terminate** the next business day (Mon–Fri +1 day; stopped on Friday, terminated Monday) |
| Compute | Lambda functions | Report only |
| Storage | EBS volumes (unattached only) | Notice, then delete |
| Storage | EBS snapshots (not backing an AMI, not AWS-managed) | Notice, then delete |
| Storage | S3 buckets | Report only (empty aged buckets are listed) |
| Database | RDS instances | Notice, then **final snapshot + stop**. Never deleted, never started by this function |
| Database | Stopped RDS instances | Listed as `idle-stopped` in every report, unless protected or scheduled (a protect or extra protect tag means the stop is intentional) |
| Network | NAT gateways, unassociated Elastic IPs, load balancers with no target groups | Report only |

## How a resource moves through the states

1. **Eligible:** older than `AGE_THRESHOLD_DAYS`, no protect tag, and (EC2) no termination protection.
2. **Notified:** tagged `Cleanup:NotifiedAt=<time>` and included in the SNS notice.
3. **Acted on:** on a later run, once `NOTICE_HOURS` have passed and the resource is still unprotected. EC2 and RDS get `Cleanup:StoppedAt`.
4. **EC2 terminate:** on the first weekday at least one day after the stop.

If the protect tag is added at any point before the action, the next run skips the resource. If someone restarts a stopped instance, its cleanup tags are cleared and it starts over.

## Fast track for fast-churn test accounts (EC2, optional)

Set `FAST_TRACK_TAG_KEY` (and `FAST_TRACK_TAG_VALUE`) in accounts where test resources are created and discarded quickly. Instances carrying that tag become eligible after `FAST_TRACK_MIN_AGE_HOURS` (default 24, i.e. launched more than a day ago) and are terminated `FAST_TRACK_TERMINATE_HOURS` (default 6) after being stopped, with no weekend skip. The notice window and protect tag still apply, and fast-track instances are exempt from the action cap. Unset by default.

**Terminating a fast-track instance takes its companions with it.** Only the instance needs the fast-track tag; the rest is found through it:

| Companion | How it is found |
|---|---|
| AMI | The instance's launch AMI (if owned by this account), plus any AMI created from it (found via the `Created by CreateImage(<instance id>)` snapshot description) |
| AMI snapshots | The snapshots behind those AMIs |
| EBS snapshots | Snapshots of the instance's volumes |
| EBS volumes | Attached volumes that would survive termination (`DeleteOnTermination=false`); the others are removed by AWS |

Before terminating, the function tags these with `Cleanup:FastTrackOwner=<instance id>`. A sweep in the same and later runs then deregisters the AMIs, deletes the snapshots, and deletes the volumes once the instance is fully terminated (retried automatically if a snapshot is still pending). No extra notice window or cap applies to companions.

Left alone, even for fast-track: anything carrying the protect tag, and an AMI still used by a running or stopped instance that is **not** fast-track (for example a shared golden image). The report lists exactly what was removed with each termination, and a dry run lists what it would remove.

## Environment variables

| Variable | Default | Description |
|---|---|---|
| `REGIONS` | the function's own region | Allowlist of regions, comma-separated, or `all` |
| `RESOURCE_TYPES` | `ec2,ebs,snapshot,rds,report` | Which groups to process |
| `AGE_THRESHOLD_DAYS` | `30` | Minimum age to be eligible |
| `NOTICE_HOURS` | `2` | Hours between notice and action |
| `MAX_ACTIONS_PER_RUN` | `10` | Cap on stop/terminate/delete actions; extras report `deferred-action-cap`. **Fast-track EC2 instances are exempt** (they don't count and aren't deferred) |
| `PROTECT_TAG_KEY` / `PROTECT_TAG_VALUE` | `Protect` / `true` | Exempting tag (value match is case-insensitive) |
| `EXTRA_PROTECT_TAGS` | unset | Extra tags that also protect a resource, comma-separated. `Key` protects any resource with that tag (any value); `Key=value` needs that value (case-insensitive). Example: `Schedule,AutoStop=true`. Use it to reuse an existing start/stop schedule tag as protection, so scheduled instances that are stopped every night are never treated as abandoned |
| `DRY_RUN` | `true` | Must be `false` to tag, stop, delete or snapshot anything |
| `SNS_TOPIC_ARN` | — | Topic for notices and reports (subscribe an email address to it) |
| `FAST_TRACK_TAG_KEY` | unset | Turns on the EC2 fast track |
| `FAST_TRACK_TAG_VALUE` | `true` | Value that selects fast-track instances |
| `FAST_TRACK_MIN_AGE_HOURS` | `24` | Fast-track eligibility age |
| `FAST_TRACK_TERMINATE_HOURS` | `6` | Fast-track hours from stop to terminate |
| `FAST_TRACK_AMI_AFFIXES` | unset | Optional comma-separated name prefixes/suffixes (e.g. `fast-,-fast`). When set, a fast-track instance's AMI is removed only if its name starts or ends with one of them; any other AMI, and its snapshots, is kept. Unset: every AMI found through the instance is removed |
| `SCHEDULER_ROLE_ARN` | unset | Role EventBridge Scheduler assumes to invoke the function. Enables the self-booked follow-ups; without it, follow-ups only happen on the periodic schedule |
| `SCHEDULER_GROUP` | `default` | Scheduler group for the follow-ups |

The function returns the full report from `lambda_handler` regardless of SNS, so you can invoke it directly and read the output. For testing, pass `{"now": "<ISO timestamp>"}` in the event to simulate time.

## Files

| File | Purpose |
|---|---|
| [lambda_function.py](lambda_function.py) | Function source |
| [execution-role-policy.json](execution-role-policy.json) | Execution role policy, including the explicit Deny |
| [permissions-boundary.json](permissions-boundary.json) | Permissions boundary for the execution role: a hard ceiling on what the role can ever do |
| [test_lambda_function.py](test_lambda_function.py) | Offline moto tests (`pytest`) |

Pair it with [resource-protect](../resource-protect/), which lists the queue and applies the exact protect tag.

## Deploy

```bash
cd aws/lambda-functions/resource-cleanup
zip function.zip lambda_function.py

aws sns create-topic --name resource-cleanup
aws sns subscribe --topic-arn <SNS_TOPIC_ARN> --protocol email --notification-endpoint <YOUR_EMAIL>

aws iam create-role --role-name resource-cleanup-role \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
# Fill in the placeholders in execution-role-policy.json first
aws iam put-role-policy --role-name resource-cleanup-role --policy-name resource-cleanup \
  --policy-document file://execution-role-policy.json

aws lambda create-function --function-name resource-cleanup \
  --runtime python3.13 --handler lambda_function.lambda_handler \
  --role arn:aws:iam::<ACCOUNT_ID>:role/resource-cleanup-role \
  --zip-file fileb://function.zip --timeout 300 --memory-size 256 \
  --environment "Variables={REGIONS=<REGION>,DRY_RUN=true,SNS_TOPIC_ARN=<SNS_TOPIC_ARN>}"

# Daily discovery run, e.g. 3:30 PM UTC
aws events put-rule --name resource-cleanup-daily --schedule-expression "cron(30 15 * * ? *)"
aws lambda add-permission --function-name resource-cleanup --statement-id events \
  --action lambda:InvokeFunction --principal events.amazonaws.com \
  --source-arn arn:aws:events:<REGION>:<ACCOUNT_ID>:rule/resource-cleanup-daily
aws events put-targets --rule resource-cleanup-daily \
  --targets "Id"="1","Arn"="arn:aws:lambda:<REGION>:<ACCOUNT_ID>:function:resource-cleanup"

# Role EventBridge Scheduler uses to invoke the function for the one-time follow-ups
aws iam create-role --role-name resource-cleanup-scheduler \
  --assume-role-policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"scheduler.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
aws iam put-role-policy --role-name resource-cleanup-scheduler --policy-name invoke \
  --policy-document '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Action":"lambda:InvokeFunction","Resource":"arn:aws:lambda:<REGION>:<ACCOUNT_ID>:function:resource-cleanup"}]}'
aws lambda update-function-configuration --function-name resource-cleanup \
  --environment "Variables={REGIONS=<REGION>,DRY_RUN=true,SNS_TOPIC_ARN=<SNS_TOPIC_ARN>,SCHEDULER_ROLE_ARN=arn:aws:iam::<ACCOUNT_ID>:role/resource-cleanup-scheduler}"
```

### Permissions boundary (recommended)

The execution role's policy says what it may do; a permissions boundary sets the most it can *ever* do, even if someone later attaches a broader policy (for example `AdministratorAccess`) to the role. Fill in the placeholders in [permissions-boundary.json](permissions-boundary.json), create it as a managed policy, and attach it as the role's boundary:

```bash
aws iam create-policy --policy-name resource-cleanup-boundary --policy-document file://permissions-boundary.json
aws iam put-role-permissions-boundary --role-name resource-cleanup-role \
  --permissions-boundary arn:aws:iam::<ACCOUNT_ID>:policy/resource-cleanup-boundary
```

The boundary allows only the same actions as the role policy and repeats the protect-tag Denies and the "never delete or start a database" Deny. Keep the two files in step when you add a resource type.

### Audit trail

Every action the function takes is a normal API call, so CloudTrail records it under the function's role. To review what it did:

```bash
aws cloudtrail lookup-events --lookup-attributes AttributeKey=Username,AttributeValue=resource-cleanup \
  --max-results 50 --query 'Events[].[EventTime,EventName,Resources[0].ResourceName]' --output table
```

Also check the function's CloudWatch Logs group and the SNS notices, which list what was notified, stopped, deleted or skipped and why. CloudTrail event history covers 90 days; create a trail to S3 if you need longer.

## Rolling it out safely

1. Deploy with `DRY_RUN=true` and read the report: does the `would-*` list match what you expect?
2. In a sandbox, create dummy resources (some old-looking via a low `AGE_THRESHOLD_DAYS`, some protected) and run with `DRY_RUN=false` and `RESOURCE_TYPES=ebs` first, then `ec2`, then `rds`.
3. Only then point it at a real account, with a small `MAX_ACTIONS_PER_RUN`.

## Safety notes

- **Explicit Deny:** `DenyActionsOnProtectedResources` blocks stop/terminate/delete on anything carrying the protect tag, whatever else the role allows. `DenyActionsOnScheduledResources` does the same for any resource that has the extra protect tag key (`<EXTRA_PROTECT_TAG_KEY>`, any value). Keep both in step with `PROTECT_TAG_*` and `EXTRA_PROTECT_TAGS`; if you use several extra tags, copy that statement once per key. The IAM statement matches on the key alone, so a `Key=value` rule is enforced by the function's own check but blocked more broadly by IAM. `NeverDeleteOrStartDatabases` blocks RDS delete and start outright.
- **RDS restarts:** AWS restarts a stopped RDS instance after 7 days. This function does not start it, but on a later run it will stop it again (no new snapshot). To keep a database running, protect it with [resource-protect](../resource-protect/).
- **RDS deletion protection** is not checked: the function only stops databases.
- **Age is creation time, not last use.** Old but actively used resources are swept up unless protected.
- **Follow-up schedules** are one-time and delete themselves after running. If booking one fails, the error appears in the report and the next daily run catches up.
- **Tags are the state.** Removing `Cleanup:NotifiedAt` resets a resource; the notice window then starts again.
- Aurora clusters are out of scope (this function does not stop clusters).
