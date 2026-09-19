"""
Cross-region AWS resource inventory.

Directly enumerates the most common cost/ops-relevant resource types in
every enabled region (EC2 instances, EBS volumes, RDS instances, Lambda
functions, ELBv2 load balancers, NAT gateways, Elastic IPs) plus global S3
buckets, then supplements that with a Resource Groups Tagging API pass to
surface anything else that happens to be tagged.

Environment variables:
    REGIONS               Comma-separated region list to scan.
                           Default: every region enabled for the account.
    OUTPUT_S3_BUCKET       Optional. If set, the full JSON report is
                           uploaded here.
    OUTPUT_S3_KEY_PREFIX   Optional. Key prefix for the uploaded report.
                           Default: "resource-inventory/".
    SENDER_EMAIL           Optional. SES-verified sender address. If set
                           together with RECIPIENT_EMAIL, a summary email
                           is sent (counts only — see OUTPUT_S3_BUCKET for
                           the full resource list).
    RECIPIENT_EMAIL        Optional. Recipient address for the summary
                           email.

Limitations:
    - The tagging-API pass ("OtherTaggedResources" in the report) only
      sees resources that have at least one tag. Untagged resources of
      types not directly enumerated above will not appear anywhere in
      the report.
    - Each describe/list call is a single, unpaginated-safe pass per
      region using the client's paginator where available; very large
      accounts may take longer than the default Lambda timeout — raise
      the function timeout (see README) rather than lowering scan scope.
"""
import json
import os
from datetime import datetime, timezone

import boto3


def _regions():
    env_regions = os.environ.get("REGIONS")
    if env_regions:
        return [r.strip() for r in env_regions.split(",") if r.strip()]
    ec2 = boto3.client("ec2")
    resp = ec2.describe_regions(
        Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}]
    )
    return sorted(r["RegionName"] for r in resp["Regions"])


def _tags_to_dict(tags):
    return {t["Key"]: t["Value"] for t in (tags or [])}


def _ec2_instances(region):
    client = boto3.client("ec2", region_name=region)
    resources = []
    for page in client.get_paginator("describe_instances").paginate():
        for reservation in page["Reservations"]:
            for instance in reservation["Instances"]:
                resources.append({
                    "Type": "ec2:instance",
                    "Id": instance["InstanceId"],
                    "Region": region,
                    "State": instance["State"]["Name"],
                    "InstanceType": instance["InstanceType"],
                    "LaunchTime": instance["LaunchTime"].isoformat(),
                    "Tags": _tags_to_dict(instance.get("Tags")),
                })
    return resources


def _ebs_volumes(region):
    client = boto3.client("ec2", region_name=region)
    resources = []
    for page in client.get_paginator("describe_volumes").paginate():
        for volume in page["Volumes"]:
            resources.append({
                "Type": "ec2:volume",
                "Id": volume["VolumeId"],
                "Region": region,
                "State": volume["State"],
                "SizeGiB": volume["Size"],
                "CreateTime": volume["CreateTime"].isoformat(),
                "Attached": bool(volume.get("Attachments")),
                "Tags": _tags_to_dict(volume.get("Tags")),
            })
    return resources


def _rds_instances(region):
    client = boto3.client("rds", region_name=region)
    resources = []
    for page in client.get_paginator("describe_db_instances").paginate():
        for db in page["DBInstances"]:
            resources.append({
                "Type": "rds:db",
                "Id": db["DBInstanceIdentifier"],
                "Region": region,
                "State": db["DBInstanceStatus"],
                "Engine": db["Engine"],
                "CreateTime": db["InstanceCreateTime"].isoformat(),
                "DeletionProtection": db.get("DeletionProtection", False),
            })
    return resources


def _lambda_functions(region):
    client = boto3.client("lambda", region_name=region)
    resources = []
    for page in client.get_paginator("list_functions").paginate():
        for fn in page["Functions"]:
            resources.append({
                "Type": "lambda:function",
                "Id": fn["FunctionName"],
                "Region": region,
                "Runtime": fn.get("Runtime", "-"),
                "LastModified": fn["LastModified"],
            })
    return resources


def _load_balancers(region):
    client = boto3.client("elbv2", region_name=region)
    resources = []
    for page in client.get_paginator("describe_load_balancers").paginate():
        for lb in page["LoadBalancers"]:
            resources.append({
                "Type": "elasticloadbalancing:loadbalancer",
                "Id": lb["LoadBalancerName"],
                "Arn": lb["LoadBalancerArn"],
                "Region": region,
                "State": lb["State"]["Code"],
                "CreatedTime": lb["CreatedTime"].isoformat(),
            })
    return resources


def _nat_gateways(region):
    client = boto3.client("ec2", region_name=region)
    resources = []
    for page in client.get_paginator("describe_nat_gateways").paginate():
        for nat in page["NatGateways"]:
            if nat["State"] == "deleted":
                continue
            resources.append({
                "Type": "ec2:natgateway",
                "Id": nat["NatGatewayId"],
                "Region": region,
                "State": nat["State"],
                "CreateTime": nat["CreateTime"].isoformat(),
            })
    return resources


def _elastic_ips(region):
    client = boto3.client("ec2", region_name=region)
    resources = []
    for address in client.describe_addresses()["Addresses"]:
        resources.append({
            "Type": "ec2:eip",
            "Id": address.get("AllocationId", address.get("PublicIp")),
            "Region": region,
            "AssociatedInstanceId": address.get("InstanceId"),
            "Tags": _tags_to_dict(address.get("Tags")),
        })
    return resources


def _s3_buckets():
    client = boto3.client("s3")
    resources = []
    for bucket in client.list_buckets()["Buckets"]:
        resources.append({
            "Type": "s3:bucket",
            "Id": bucket["Name"],
            "Region": "global",
            "CreationDate": bucket["CreationDate"].isoformat(),
        })
    return resources


def _arn_key(arn):
    """(service, region, resource type, id) so that, for example, an RDS instance and an RDS
    cluster with the same name, or a Lambda and an EC2 resource, cannot shadow each other.
    S3 ARNs carry no region or resource type; inventory records S3 as 'global'."""
    parts = arn.split(":", 5)
    service, region, resource = parts[2], parts[3] or "global", parts[5]
    normalized = resource.replace(":", "/")
    rtype = normalized.split("/")[0] if "/" in normalized else ""
    return service, region, rtype, normalized.split("/")[-1]


_ARN_RESOURCE_TYPES = {"eip": "elastic-ip", "bucket": ""}


def _record_key(record):
    """The _arn_key equivalent for an enumerated record."""
    if record.get("Arn"):
        return _arn_key(record["Arn"])
    service, kind = record["Type"].split(":", 1)
    return service, record["Region"], _ARN_RESOURCE_TYPES.get(kind, kind), record["Id"]


def _other_tagged_resources(region):
    client = boto3.client("resourcegroupstaggingapi", region_name=region)
    resources = []
    for page in client.get_paginator("get_resources").paginate():
        for item in page.get("ResourceTagMappingList", []):
            resources.append({
                "Arn": item["ResourceARN"],
                "Region": region,
                "Tags": _tags_to_dict(item.get("Tags")),
            })
    return resources


REGIONAL_COLLECTORS = {
    "ec2:instance": _ec2_instances,
    "ec2:volume": _ebs_volumes,
    "rds:db": _rds_instances,
    "lambda:function": _lambda_functions,
    "elasticloadbalancing:loadbalancer": _load_balancers,
    "ec2:natgateway": _nat_gateways,
    "ec2:eip": _elastic_ips,
}


def lambda_handler(event, context):
    regions = _regions()
    resources = []
    other_tagged = []
    errors = []

    for region in regions:
        for resource_type, collector in REGIONAL_COLLECTORS.items():
            try:
                resources.extend(collector(region))
            except Exception as exc:  # noqa: BLE001 - report and keep scanning
                errors.append({"Region": region, "Collector": resource_type, "Error": str(exc)})

        try:
            other_tagged.extend(_other_tagged_resources(region))
        except Exception as exc:  # noqa: BLE001
            errors.append({"Region": region, "Collector": "tagging-api", "Error": str(exc)})

    try:
        resources.extend(_s3_buckets())
    except Exception as exc:  # noqa: BLE001
        errors.append({"Region": "global", "Collector": "s3:bucket", "Error": str(exc)})

    known = {_record_key(r) for r in resources}
    other_tagged = [t for t in other_tagged if _arn_key(t["Arn"]) not in known]

    summary = {}
    for r in resources:
        summary[r["Type"]] = summary.get(r["Type"], 0) + 1

    report = {
        "GeneratedAt": datetime.now(timezone.utc).isoformat(),
        "RegionsScanned": regions,
        "TotalResources": len(resources),
        "SummaryByType": summary,
        "Resources": resources,
        "OtherTaggedResources": other_tagged,
        "Errors": errors,
    }

    if os.environ.get("OUTPUT_S3_BUCKET"):
        try:
            _upload_report(report)
        except Exception as exc:  # noqa: BLE001 - delivery is optional; keep the summary
            errors.append({"Region": "global", "Collector": "s3-upload", "Error": str(exc)})

    if os.environ.get("SENDER_EMAIL") and os.environ.get("RECIPIENT_EMAIL"):
        try:
            _email_summary(report)
        except Exception as exc:  # noqa: BLE001
            errors.append({"Region": "global", "Collector": "email", "Error": str(exc)})

    return {
        "TotalResources": report["TotalResources"],
        "SummaryByType": report["SummaryByType"],
        "OtherTaggedResourceCount": len(other_tagged),
        "Errors": report["Errors"],
    }


def _upload_report(report):
    s3 = boto3.client("s3")
    bucket = os.environ["OUTPUT_S3_BUCKET"]
    prefix = os.environ.get("OUTPUT_S3_KEY_PREFIX", "resource-inventory/")
    key = f"{prefix}{datetime.now(timezone.utc).strftime('%Y-%m-%dT%H-%M-%S')}.json"
    s3.put_object(
        Bucket=bucket,
        Key=key,
        Body=json.dumps(report, default=str, indent=2).encode("utf-8"),
        ContentType="application/json",
    )


def _email_summary(report):
    ses = boto3.client("ses")
    lines = [
        f"AWS resource inventory - {report['GeneratedAt']}",
        "",
        f"Regions scanned: {', '.join(report['RegionsScanned'])}",
        f"Total resources (directly enumerated): {report['TotalResources']}",
        f"Other tagged resources (tagging API only): {len(report['OtherTaggedResources'])}",
        "",
        "By type:",
    ]
    for rtype, count in sorted(report["SummaryByType"].items(), key=lambda x: -x[1]):
        lines.append(f"  {rtype}: {count}")

    if report["Errors"]:
        lines.append("")
        lines.append("Errors during scan:")
        for e in report["Errors"]:
            lines.append(f"  [{e['Region']}] {e['Collector']}: {e['Error']}")

    ses.send_email(
        Source=os.environ["SENDER_EMAIL"],
        Destination={"ToAddresses": [os.environ["RECIPIENT_EMAIL"]]},
        Message={
            "Subject": {"Data": f"AWS resource inventory - {report['TotalResources']} resources"},
            "Body": {"Text": {"Data": "\n".join(lines)}},
        },
    )
