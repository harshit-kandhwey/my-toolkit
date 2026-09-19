"""
Per-resource cost report for EC2 and RDS instances, reconciled against Cost Explorer.

Cost Explorer only reports per service and usage type, not per instance. This function
fills the gap in two steps:

  record  (run hourly)  samples running EC2 instances and available RDS instances and adds
                        hours to one DynamoDB row per resource per month.
  report  (run monthly) prices those hours with the account's *effective* rate for the
                        matching usage type (amortized cost / usage hours from Cost Explorer,
                        so Savings Plans and reservations are reflected), writes a JSON
                        report to S3, and publishes a summary to SNS.

Invoke with:
    {"action": "record"}                        default
    {"action": "report"}                        previous calendar month
    {"action": "report", "month": "2030-01"}    a specific month
    {"now": "<ISO timestamp>"}                  test hook, accepted by both actions

Each table row is already a single monthly summary for one resource (key: resource, month),
so nothing needs compacting; rows expire through the DynamoDB TTL attribute ExpiresAt.

Reconciliation: per usage type the report compares hours Cost Explorer billed with hours this
function sampled (CoveragePercent). A gap means instances outside REGIONS, hours before the
function was deployed, or instances that ran between two samples.

Environment variables:
    TABLE_NAME       DynamoDB table (partition key "pk" S, sort key "sk" S). Required.
    REGIONS          Comma-separated regions to sample, or "all". Default: the function's own.
    SAMPLE_HOURS     Hours each "record" run represents. Default 1 (hourly schedule).
    REPORT_BUCKET    S3 bucket for the monthly JSON report. Optional.
    REPORT_PREFIX    Key prefix. Default "cost-report/".
    SNS_TOPIC_ARN    Optional. Receives a short top-N summary.
    TOP_N            Resources listed in the summary. Default 10.
"""
import json
import os
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import boto3
from boto3.dynamodb.conditions import Attr

EC2_SERVICE = "Amazon Elastic Compute Cloud - Compute"
RDS_SERVICE = "Amazon Relational Database Service"

# Cost Explorer usage-type prefix per region ("" = no prefix). Not verified against a real
# account; a region missing from this map gets no price and is listed under "Unpriced".
REGION_PREFIX = {
    "us-east-1": "", "us-east-2": "USE2", "us-west-1": "USW1", "us-west-2": "USW2",
    "ca-central-1": "CAN1", "sa-east-1": "SAE1",
    "eu-west-1": "EU", "eu-west-2": "EUW2", "eu-west-3": "EUW3", "eu-central-1": "EUC1",
    "eu-north-1": "EUN1", "eu-south-1": "EUS1",
    "ap-south-1": "APS3", "ap-southeast-1": "APS1", "ap-southeast-2": "APS2",
    "ap-northeast-1": "APN1", "ap-northeast-2": "APN2", "ap-northeast-3": "APN3",
    "ap-east-1": "APE1", "me-south-1": "MES1", "af-south-1": "AFS1",
}
TTL_DAYS = 400


def _regions():
    raw = os.environ.get("REGIONS") or os.environ.get("AWS_REGION", "us-east-1")
    if raw.strip() == "all":
        resp = boto3.client("ec2").describe_regions(
            Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}]
        )
        return sorted(r["RegionName"] for r in resp["Regions"])
    return [r.strip() for r in raw.split(",") if r.strip()]


def _now(event):
    if event and event.get("now"):
        return datetime.fromisoformat(event["now"])
    return datetime.now(timezone.utc)


def usage_type(kind, region, instance_type, multi_az=False):
    """Cost Explorer usage type for an instance hour, or None if the region prefix is unknown."""
    if region not in REGION_PREFIX:
        return None
    if kind == "rds":
        core = f"{'Multi-AZUsage' if multi_az else 'InstanceUsage'}:{instance_type}"
    else:
        core = f"BoxUsage:{instance_type}"
    prefix = REGION_PREFIX[region]
    return f"{prefix}-{core}" if prefix else core


def _tag(tags, key):
    return next((t["Value"] for t in tags or [] if t["Key"] == key), "")


def _running_ec2(region):
    ec2 = boto3.client("ec2", region_name=region)
    filters = [{"Name": "instance-state-name", "Values": ["running"]}]
    for page in ec2.get_paginator("describe_instances").paginate(Filters=filters):
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                yield {
                    "Kind": "ec2", "Id": inst["InstanceId"], "InstanceType": inst["InstanceType"],
                    "Name": _tag(inst.get("Tags"), "Name"), "MultiAZ": False,
                }


def _available_rds(region):
    rds = boto3.client("rds", region_name=region)
    for page in rds.get_paginator("describe_db_instances").paginate():
        for db in page["DBInstances"]:
            if db["DBInstanceStatus"] == "available":
                yield {
                    "Kind": "rds", "Id": db["DBInstanceIdentifier"], "InstanceType": db["DBInstanceClass"],
                    "Name": db["DBInstanceIdentifier"], "MultiAZ": bool(db.get("MultiAZ")),
                }


def _record(event):
    table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    now = _now(event)
    month = f"{now:%Y-%m}"
    hours = Decimal(os.environ.get("SAMPLE_HOURS", "1"))
    expires = int((now + timedelta(days=TTL_DAYS)).timestamp())
    account = boto3.client("sts").get_caller_identity()["Account"]
    recorded, errors = 0, []

    for region in _regions():
        for collector in (_running_ec2, _available_rds):
            try:
                resources = list(collector(region))
            except Exception as exc:  # noqa: BLE001 - report and keep sampling other regions
                errors.append({"Region": region, "Collector": collector.__name__, "Error": str(exc)})
                continue
            for r in resources:
                table.update_item(
                    Key={"pk": f"{r['Kind']}#{region}#{r['Id']}", "sk": month},
                    UpdateExpression=(
                        "ADD #h :h SET #kind = :kind, #region = :region, #rid = :rid, #type = :type, "
                        "#name = :name, #ut = :ut, #acct = :acct, #month = :month, #exp = :exp"
                    ),
                    ExpressionAttributeNames={
                        "#h": "Hours", "#kind": "Kind", "#region": "Region", "#rid": "ResourceId",
                        "#type": "InstanceType", "#name": "Name", "#ut": "UsageType", "#acct": "Account",
                        "#month": "Month", "#exp": "ExpiresAt",
                    },
                    ExpressionAttributeValues={
                        ":h": hours, ":kind": r["Kind"], ":region": region, ":rid": r["Id"],
                        ":type": r["InstanceType"], ":name": r["Name"],
                        ":ut": usage_type(r["Kind"], region, r["InstanceType"], r["MultiAZ"]) or "",
                        ":acct": account, ":month": month, ":exp": expires,
                    },
                )
                recorded += 1
    return {"Action": "record", "Month": month, "ResourcesSampled": recorded, "Errors": errors}


def _month_bounds(month):
    start = date.fromisoformat(f"{month}-01")
    end = (start.replace(day=28) + timedelta(days=4)).replace(day=1)
    return start.isoformat(), end.isoformat()


def _ce_usage(month):
    """{usage_type: {"cost": amortized cost, "hours": usage quantity}} for EC2 and RDS."""
    ce = boto3.client("ce", region_name="us-east-1")
    start, end = _month_bounds(month)
    usage = {}
    for service in (EC2_SERVICE, RDS_SERVICE):
        token = None
        while True:
            kwargs = {
                "TimePeriod": {"Start": start, "End": end},
                "Granularity": "MONTHLY",
                "Metrics": ["AmortizedCost", "UsageQuantity"],
                "GroupBy": [{"Type": "DIMENSION", "Key": "USAGE_TYPE"}],
                "Filter": {"Dimensions": {"Key": "SERVICE", "Values": [service]}},
            }
            if token:
                kwargs["NextPageToken"] = token
            resp = ce.get_cost_and_usage(**kwargs)
            for period in resp["ResultsByTime"]:
                for group in period["Groups"]:
                    entry = usage.setdefault(group["Keys"][0], {"cost": 0.0, "hours": 0.0})
                    entry["cost"] += float(group["Metrics"]["AmortizedCost"]["Amount"])
                    entry["hours"] += float(group["Metrics"]["UsageQuantity"]["Amount"])
            token = resp.get("NextPageToken")
            if not token:
                break
    return usage


def _scan_month(table, month):
    items, kwargs = [], {"FilterExpression": Attr("Month").eq(month)}
    while True:
        resp = table.scan(**kwargs)
        items.extend(resp["Items"])
        if "LastEvaluatedKey" not in resp:
            return items
        kwargs["ExclusiveStartKey"] = resp["LastEvaluatedKey"]


def _report(event):
    table = boto3.resource("dynamodb").Table(os.environ["TABLE_NAME"])
    now = _now(event)
    month = (event or {}).get("month") or f"{(now.replace(day=1) - timedelta(days=1)):%Y-%m}"
    usage = _ce_usage(month)

    resources, unpriced = [], []
    sampled = {}
    for item in _scan_month(table, month):
        hours = float(item["Hours"])
        ut = item.get("UsageType") or ""
        rate_info = usage.get(ut)
        rate = rate_info["cost"] / rate_info["hours"] if rate_info and rate_info["hours"] else None
        cost = round(hours * rate, 2) if rate is not None else None
        row = {
            "Kind": item["Kind"], "Region": item["Region"], "ResourceId": item["ResourceId"],
            "Name": item.get("Name", ""), "InstanceType": item["InstanceType"], "UsageType": ut,
            "Hours": hours, "EffectiveRatePerHour": round(rate, 4) if rate is not None else None, "Cost": cost,
        }
        resources.append(row)
        if cost is None:
            unpriced.append(row["ResourceId"])
        else:
            sampled[ut] = sampled.get(ut, 0.0) + hours
            table.update_item(
                Key={"pk": item["pk"], "sk": item["sk"]},
                UpdateExpression="SET #c = :c, #r = :r",
                ExpressionAttributeNames={"#c": "Cost", "#r": "ReportedAt"},
                ExpressionAttributeValues={":c": Decimal(str(cost)), ":r": now.isoformat()},
            )

    resources.sort(key=lambda r: r["Cost"] or 0, reverse=True)
    reconciliation = {
        ut: {
            "CostExplorerCost": round(v["cost"], 2),
            "CostExplorerHours": round(v["hours"], 1),
            "SampledHours": round(sampled.get(ut, 0.0), 1),
            "CoveragePercent": round(100 * sampled.get(ut, 0.0) / v["hours"], 1) if v["hours"] else None,
        }
        for ut, v in sorted(usage.items())
        if "BoxUsage:" in ut or "InstanceUsage:" in ut or "Multi-AZUsage:" in ut
    }
    report = {
        "Month": month,
        "GeneratedAt": now.isoformat(),
        "TotalAllocatedCost": round(sum(r["Cost"] or 0 for r in resources), 2),
        "Resources": resources,
        "Unpriced": sorted(unpriced),
        "Reconciliation": reconciliation,
    }

    bucket = os.environ.get("REPORT_BUCKET")
    key = None
    if bucket:
        key = f"{os.environ.get('REPORT_PREFIX', 'cost-report/')}{month}.json"
        boto3.client("s3").put_object(
            Bucket=bucket, Key=key, Body=json.dumps(report, indent=2).encode(), ContentType="application/json"
        )
    if os.environ.get("SNS_TOPIC_ARN"):
        _publish(os.environ["SNS_TOPIC_ARN"], report, key)
    return {
        "Action": "report", "Month": month, "Resources": len(resources),
        "TotalAllocatedCost": report["TotalAllocatedCost"], "Unpriced": len(unpriced), "ReportKey": key,
    }


def _publish(topic_arn, report, key):
    top_n = int(os.environ.get("TOP_N", "10"))
    lines = [f"EC2/RDS cost report for {report['Month']}: ${report['TotalAllocatedCost']:.2f} allocated"]
    for r in report["Resources"][:top_n]:
        cost = f"${r['Cost']:.2f}" if r["Cost"] is not None else "unpriced"
        lines.append(f"  {r['ResourceId']} {r['Name']} ({r['InstanceType']}, {r['Region']}): {r['Hours']:.0f}h, {cost}")
    low = {ut: v for ut, v in report["Reconciliation"].items() if v["CoveragePercent"] is not None and v["CoveragePercent"] < 90}
    if low:
        lines.append("Coverage below 90% (sampled vs billed hours):")
        lines.extend(f"  {ut}: {v['CoveragePercent']}%" for ut, v in low.items())
    if report["Unpriced"]:
        lines.append(f"{len(report['Unpriced'])} resource(s) could not be priced")
    if key:
        lines.append(f"Full report: {key}")
    boto3.client("sns").publish(
        TopicArn=topic_arn, Subject=f"Cost report {report['Month']}"[:100], Message="\n".join(lines)
    )


def lambda_handler(event, context):
    action = (event or {}).get("action", "record")
    if action == "record":
        return _record(event)
    if action == "report":
        return _report(event)
    return {"Error": f"unknown action '{action}'; use 'record' or 'report'"}
