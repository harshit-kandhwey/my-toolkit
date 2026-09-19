"""
Companion to resource-cleanup: lists resources queued for cleanup and protects the
ones you name, using the exact protect tag so a typo can't leave a resource exposed.

Invoke with:
    {"action": "list"}                       list everything currently queued
    {"action": "protect", "ids": ["i-0abc", "us-east-1:vol-0def", "arn:aws:..."]}
                                             tag those queued resources as protected
                                             and clear their cleanup state. Use a full
                                             ARN or "region:id" when the same id is
                                             queued in more than one region; ambiguous
                                             bare ids are rejected and returned under
                                             "Ambiguous".

A resource is "queued" when it carries the Cleanup:NotifiedAt tag. Only queued
resources can be protected here (IDs not in the queue are reported back, not tagged).
Restrict who may invoke this function: anyone who can invoke it can protect any
queued resource.

Environment variables:
    REGIONS            Comma-separated regions to search, or "all". Default: the
                       function's own region.
    PROTECT_TAG_KEY    Default "Protect".
    PROTECT_TAG_VALUE  Default "true".
"""
import os

import boto3

QUEUE_TAG = "Cleanup:NotifiedAt"
CLEANUP_TAGS = ["Cleanup:NotifiedAt", "Cleanup:StoppedAt"]


def _regions():
    raw = os.environ.get("REGIONS") or os.environ.get("AWS_REGION", "us-east-1")
    if raw.strip() == "all":
        resp = boto3.client("ec2").describe_regions(
            Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}]
        )
        return sorted(r["RegionName"] for r in resp["Regions"])
    return [r.strip() for r in raw.split(",") if r.strip()]


def _queued(region):
    client = boto3.client("resourcegroupstaggingapi", region_name=region)
    queued = []
    for page in client.get_paginator("get_resources").paginate(TagFilters=[{"Key": QUEUE_TAG}]):
        for item in page["ResourceTagMappingList"]:
            tags = {t["Key"]: t["Value"] for t in item.get("Tags", [])}
            queued.append({"Arn": item["ResourceARN"], "Region": region, "NotifiedAt": tags.get(QUEUE_TAG)})
    return queued


def _resource_id(arn):
    return arn.replace(":", "/").split("/")[-1]


def lambda_handler(event, context):
    action = (event or {}).get("action", "list")
    queue = []
    errors = []
    for region in _regions():
        try:
            queue.extend(_queued(region))
        except Exception as exc:  # noqa: BLE001
            errors.append({"Region": region, "Error": str(exc)})

    if action == "list":
        return {"Queued": [{**q, "Id": _resource_id(q["Arn"])} for q in queue], "Errors": errors}

    if action != "protect":
        return {"Error": f"unknown action '{action}'; use 'list' or 'protect'"}

    wanted = list(event.get("ids", []))
    key = os.environ.get("PROTECT_TAG_KEY", "Protect")
    value = os.environ.get("PROTECT_TAG_VALUE", "true")
    selected, not_in_queue, ambiguous = {}, [], []
    for sel in wanted:
        matches = _match(queue, sel)
        if not matches:
            not_in_queue.append(sel)
        elif len(matches) > 1:
            ambiguous.append(sel)
        else:
            selected[matches[0]["Arn"]] = matches[0]

    by_region = {}
    for q in selected.values():
        by_region.setdefault(q["Region"], []).append(q["Arn"])

    protected = []
    for region, arns in by_region.items():
        client = boto3.client("resourcegroupstaggingapi", region_name=region)
        for batch in _batches(arns):
            tagged = _apply(client, "tag_resources", batch, region, errors, Tags={key: value})
            if tagged:
                _apply(client, "untag_resources", tagged, region, errors, TagKeys=CLEANUP_TAGS)
                protected.extend(_resource_id(a) for a in tagged)

    return {
        "Protected": sorted(protected),
        "NotInQueue": sorted(not_in_queue),
        "Ambiguous": sorted(ambiguous),
        "Errors": errors,
    }


def _match(queue, selector):
    """A selector is a full ARN, 'region:id', or a bare id (which must match exactly one queued resource)."""
    if selector.startswith("arn:"):
        return [q for q in queue if q["Arn"] == selector]
    if ":" in selector:
        region, rid = selector.split(":", 1)
        return [q for q in queue if q["Region"] == region and _resource_id(q["Arn"]) == rid]
    return [q for q in queue if _resource_id(q["Arn"]) == selector]


def _batches(items, size=20):
    for i in range(0, len(items), size):
        yield items[i:i + size]


def _apply(client, method, arns, region, errors, **kwargs):
    """Call a Tagging API method for up to 20 ARNs; return the ARNs that succeeded."""
    try:
        result = getattr(client, method)(ResourceARNList=arns, **kwargs)
    except Exception as exc:  # noqa: BLE001
        errors.append({"Region": region, "Error": f"{method} failed: {exc}"})
        return []
    failed = result.get("FailedResourcesMap", {})
    errors.extend({"Region": region, "Arn": arn, "Error": f"{method}: {info['ErrorMessage']}"} for arn, info in failed.items())
    return [a for a in arns if a not in failed]
