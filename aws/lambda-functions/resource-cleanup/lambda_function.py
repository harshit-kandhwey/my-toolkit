"""
Notify-then-act cleanup of aged, unprotected resources. Schedule it once a day for
discovery; with SCHEDULER_ROLE_ARN set it books its own one-time follow-ups (notice
expiry, terminate deadline). State lives in resource tags, so there is no database.

Per resource group:
    EC2 instances    notify -> stop (after the notice window) -> terminate the next
                     business day (Mon-Fri +1 day; a Friday stop terminates Monday).
                     Fast-track instances are terminated together with their kept data
                     volumes, their AMI (launch AMI or created from it), and the EBS/AMI snapshots.
    EBS volumes      unattached only: notify -> delete
    EBS snapshots    not backing an AMI, not AWS-managed: notify -> delete
    RDS instances    notify -> final snapshot + stop. NEVER deleted or started by
                     this function. Stopped instances are listed as idle resources.
    Report-only      Lambda functions, empty S3 buckets, NAT gateways, unassociated
                     Elastic IPs, load balancers with no target groups: listed only.

A resource is only touched if it is older than AGE_THRESHOLD_DAYS, does not carry
the protect tag, and (EC2) has no termination protection. Each run first tags newly
found resources with Cleanup:NotifiedAt and publishes a notice; the action happens
on a later run once NOTICE_HOURS have passed and the resource is still unprotected.
Anyone can protect resources in that window with the resource-protect function.

DRY_RUN defaults to "true": nothing is tagged, stopped, or deleted, and the report
only says what would happen.

Environment variables:
    REGIONS              Comma-separated allowlist, or "all". Default: the
                         function's own region only.
    RESOURCE_TYPES       Subset of "ec2,ebs,snapshot,rds,report". Default: all.
    AGE_THRESHOLD_DAYS   Minimum age to be eligible. Default 30.
    NOTICE_HOURS         Hours between notice and action. Default 2.
    MAX_ACTIONS_PER_RUN  Cap on stop/terminate/delete actions per run. Default 10.
                         Fast-track EC2 instances are exempt: they neither count toward
                         the cap nor get deferred by it.
    PROTECT_TAG_KEY      Default "Protect".
    PROTECT_TAG_VALUE    Default "true" (case-insensitive).
    EXTRA_PROTECT_TAGS   Optional comma-separated extra protecting tags: "Key" protects any
                         resource that has the tag with any value; "Key=value" needs that
                         value (case-insensitive). Example: "Schedule,AutoStop=true".
    DRY_RUN              "true" (default) or "false".
    SNS_TOPIC_ARN        Topic that receives notices and reports.
    FAST_TRACK_TAG_KEY   Optional, off when unset. EC2 instances carrying this tag
                         (value FAST_TRACK_TAG_VALUE, default "true") use a short
                         cycle for accounts with fast-churn test resources.
    FAST_TRACK_MIN_AGE_HOURS   Age at which fast-track instances become eligible.
                         Default 24 (launched more than a day ago).
    FAST_TRACK_TERMINATE_HOURS Hours between stop and terminate for fast-track
                         instances. Default 6 (no weekend skip).

    FAST_TRACK_AMI_AFFIXES Optional comma-separated name prefixes/suffixes. When set, a
                         fast-track instance's AMI is only removed if its name starts or
                         ends with one of them; other AMIs (and their snapshots) are kept.
    SCHEDULER_ROLE_ARN   Role EventBridge Scheduler assumes to invoke this function. When set,
                         the function creates one-time follow-up schedules for each notice
                         and terminate deadline, so a once-a-day schedule is enough. Unset:
                         follow-ups only happen on whatever periodic schedule you configure.
    SELF_FUNCTION_ARN    ARN of this function (only needed outside Lambda, e.g. tests).
    SCHEDULER_GROUP      Scheduler group for the follow-ups. Default "default".

Test hook: the invoke event may contain {"now": "<ISO timestamp>"} to simulate time.
"""
import os
import re
from datetime import datetime, timedelta, timezone

import boto3

NOTIFIED_TAG = "Cleanup:NotifiedAt"
STOPPED_TAG = "Cleanup:StoppedAt"
FAST_OWNER_TAG = "Cleanup:FastTrackOwner"
ACTED = {"stopped", "terminated", "deleted", "snapshotted-and-stopped", "fast-track-deregistered", "fast-track-deleted"}
NOTABLE = ACTED | {"notified", "error"}


def _parse(ts):
    d = datetime.fromisoformat(ts)
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _tags(raw):
    return {t["Key"]: t["Value"] for t in (raw or [])}


def _terminate_deadline(stopped_at, fast_hours=None):
    if fast_hours is not None:
        return stopped_at + timedelta(hours=fast_hours)
    deadline = stopped_at + timedelta(days=1)
    while deadline.weekday() >= 5:
        deadline += timedelta(days=1)
    return deadline


def _parse_extra_protect(raw):
    """"Schedule, AutoStop=true" -> [("Schedule", None), ("AutoStop", "true")]"""
    pairs = []
    for item in (p.strip() for p in raw.split(",")):
        if not item:
            continue
        key, _, value = item.partition("=")
        pairs.append((key.strip(), value.strip().lower() if value.strip() else None))
    return pairs


def _config():
    regions = os.environ.get("REGIONS") or os.environ.get("AWS_REGION", "us-east-1")
    return {
        "regions": [r.strip() for r in regions.split(",") if r.strip()],
        "resource_types": {
            t.strip() for t in os.environ.get("RESOURCE_TYPES", "ec2,ebs,snapshot,rds,report").split(",") if t.strip()
        },
        "age_days": int(os.environ.get("AGE_THRESHOLD_DAYS", "30")),
        "notice_hours": int(os.environ.get("NOTICE_HOURS", "2")),
        "max_actions": int(os.environ.get("MAX_ACTIONS_PER_RUN", "10")),
        "protect_key": os.environ.get("PROTECT_TAG_KEY", "Protect"),
        "protect_value": os.environ.get("PROTECT_TAG_VALUE", "true").lower(),
        "dry_run": os.environ.get("DRY_RUN", "true").lower() != "false",
        "topic_arn": os.environ.get("SNS_TOPIC_ARN"),
        "fast_key": os.environ.get("FAST_TRACK_TAG_KEY"),
        "fast_value": os.environ.get("FAST_TRACK_TAG_VALUE", "true").lower(),
        "fast_min_age_hours": int(os.environ.get("FAST_TRACK_MIN_AGE_HOURS", "24")),
        "fast_terminate_hours": int(os.environ.get("FAST_TRACK_TERMINATE_HOURS", "6")),
        "extra_protect": _parse_extra_protect(os.environ.get("EXTRA_PROTECT_TAGS", "")),
        "fast_ami_affixes": [a.strip() for a in os.environ.get("FAST_TRACK_AMI_AFFIXES", "").split(",") if a.strip()],
        "scheduler_role_arn": os.environ.get("SCHEDULER_ROLE_ARN"),
        "scheduler_group": os.environ.get("SCHEDULER_GROUP", "default"),
    }


class Run:
    def __init__(self, cfg, now):
        self.cfg = cfg
        self.now = now
        self.entries = []
        self.errors = []
        self.mutations = 0
        self.wakeups = set()

    def wake(self, when):
        self.wakeups.add(when)

    def record(self, region, rtype, rid, age, status, detail=""):
        self.entries.append(
            {"Region": region, "Type": rtype, "Id": rid, "AgeDays": age, "Status": status, "Detail": detail}
        )

    def protected(self, tags):
        value = tags.get(self.cfg["protect_key"])
        if value is not None and value.lower() == self.cfg["protect_value"]:
            return True
        return any(
            key in tags and (want is None or tags[key].lower() == want) for key, want in self.cfg["extra_protect"]
        )

    def is_fast_track(self, tags):
        key = self.cfg["fast_key"]
        return bool(key) and tags.get(key, "").lower() == self.cfg["fast_value"]

    def eligible(self, age, tags):
        in_flight = NOTIFIED_TAG in tags or STOPPED_TAG in tags
        return age >= self.cfg["age_days"] or in_flight

    def notify_then_act(self, region, rtype, rid, age, tags, tag_fn, act_fn, act_status, would_status, capped=True):
        notified = tags.get(NOTIFIED_TAG)
        if notified is None:
            if self.cfg["dry_run"]:
                self.record(region, rtype, rid, age, "would-notify")
                return
            tag_fn({NOTIFIED_TAG: self.now.isoformat()})
            due = self.now + timedelta(hours=self.cfg["notice_hours"])
            self.record(region, rtype, rid, age, "notified", f"action after {due.isoformat()}")
            self.wake(due)
            return

        due = _parse(notified) + timedelta(hours=self.cfg["notice_hours"])
        if self.now < due:
            self.record(region, rtype, rid, age, "awaiting-notice", f"action after {due.isoformat()}")
            self.wake(due)
            return
        if self.cfg["dry_run"]:
            self.record(region, rtype, rid, age, would_status)
            return
        if capped and self.mutations >= self.cfg["max_actions"]:
            self.record(region, rtype, rid, age, "deferred-action-cap")
            return
        act_fn()
        if capped:
            self.mutations += 1
        self.record(region, rtype, rid, age, act_status)


def _companion_detail(companions):
    parts = [f"{kind}: {', '.join(ids)}" for kind, ids in companions.items() if ids]
    return ("also removed - " + "; ".join(parts)) if parts else ""


def _fast_track_companions(run, ec2, inst):
    """AMIs, snapshots and data volumes that go with a fast-track instance.

    Only the instance carries the fast-track tag; everything else is found through it.
    An AMI qualifies if it is owned by this account, is the instance's launch AMI or
    was created from it (found via the "Created by CreateImage(<id>)" snapshot
    description), and no other non-fast-track instance still uses it. Snapshots are
    the AMIs' snapshots plus snapshots of the instance's volumes. Volumes are the
    attached ones that survive termination. Anything carrying the protect tag is
    left alone.
    """
    iid = inst["InstanceId"]
    volume_ids = [m["Ebs"]["VolumeId"] for m in inst.get("BlockDeviceMappings", []) if "Ebs" in m]
    kept_volume_ids = [
        m["Ebs"]["VolumeId"]
        for m in inst.get("BlockDeviceMappings", [])
        if "Ebs" in m and not m["Ebs"].get("DeleteOnTermination", False)
    ]

    candidate_amis = {inst["ImageId"]}
    for page in ec2.get_paginator("describe_snapshots").paginate(
        OwnerIds=["self"], Filters=[{"Name": "description", "Values": [f"Created by CreateImage({iid})*"]}]
    ):
        for snap in page["Snapshots"]:
            match = re.search(r"for (ami-[0-9a-f]+)", snap.get("Description", ""))
            if match:
                candidate_amis.add(match.group(1))

    images, qualifying, backing_other = ec2.describe_images(Owners=["self"])["Images"], [], set()
    for img in images:
        tags = _tags(img.get("Tags"))
        ami_snaps = {m["Ebs"]["SnapshotId"] for m in img.get("BlockDeviceMappings", []) if "SnapshotId" in m.get("Ebs", {})}
        affixes = run.cfg["fast_ami_affixes"]
        name = img.get("Name", "")
        name_ok = not affixes or any(name.startswith(a) or name.endswith(a) for a in affixes)
        if img["ImageId"] not in candidate_amis or run.protected(tags) or not name_ok:
            backing_other |= ami_snaps
            continue
        others = ec2.describe_instances(
            Filters=[
                {"Name": "image-id", "Values": [img["ImageId"]]},
                {"Name": "instance-state-name", "Values": ["pending", "running", "stopping", "stopped"]},
            ]
        )["Reservations"]
        shared = any(
            i["InstanceId"] != iid and not run.is_fast_track(_tags(i.get("Tags"))) for r in others for i in r["Instances"]
        )
        if shared:
            backing_other |= ami_snaps
            continue
        qualifying.append((img["ImageId"], ami_snaps))

    snapshot_ids = {sid for _, snaps in qualifying for sid in snaps}
    if volume_ids:
        for page in ec2.get_paginator("describe_snapshots").paginate(
            OwnerIds=["self"], Filters=[{"Name": "volume-id", "Values": volume_ids}]
        ):
            for snap in page["Snapshots"]:
                if not run.protected(_tags(snap.get("Tags"))):
                    snapshot_ids.add(snap["SnapshotId"])
    snapshot_ids -= backing_other
    if snapshot_ids:
        for page in ec2.get_paginator("describe_snapshots").paginate(SnapshotIds=sorted(snapshot_ids)):
            for snap in page["Snapshots"]:
                if run.protected(_tags(snap.get("Tags"))):
                    snapshot_ids.discard(snap["SnapshotId"])

    volumes = []
    if kept_volume_ids:
        for vol in ec2.describe_volumes(VolumeIds=kept_volume_ids)["Volumes"]:
            if not run.protected(_tags(vol.get("Tags"))):
                volumes.append(vol["VolumeId"])

    return {"images": [i for i, _ in qualifying], "snapshots": sorted(snapshot_ids), "volumes": volumes}


def _fast_track_sweep(run, ec2, region):
    """Remove companions tagged Cleanup:FastTrackOwner: AMIs, then snapshots, then volumes
    once the owning instance is gone. Not capped, not subject to a notice window."""
    tag_filter = [{"Name": "tag-key", "Values": [FAST_OWNER_TAG]}]
    dry = run.cfg["dry_run"]

    all_images = ec2.describe_images(Owners=["self"])["Images"]
    images = [i for i in all_images if FAST_OWNER_TAG in _tags(i.get("Tags"))]
    swept_ids = {i["ImageId"] for i in images}
    still_backing = {
        m["Ebs"]["SnapshotId"]
        for i in all_images
        if i["ImageId"] not in swept_ids
        for m in i.get("BlockDeviceMappings", [])
        if "SnapshotId" in m.get("Ebs", {})
    }
    snapshot_ids = set()
    for img in images:
        snapshot_ids |= {m["Ebs"]["SnapshotId"] for m in img.get("BlockDeviceMappings", []) if "SnapshotId" in m.get("Ebs", {})}
        if not dry:
            ec2.deregister_image(ImageId=img["ImageId"])
        run.record(region, "ec2:image", img["ImageId"], None, "would-deregister" if dry else "fast-track-deregistered")

    for page in ec2.get_paginator("describe_snapshots").paginate(OwnerIds=["self"], Filters=tag_filter):
        snapshot_ids |= {s["SnapshotId"] for s in page["Snapshots"]}
    snapshot_ids -= still_backing
    if snapshot_ids:
        for page in ec2.get_paginator("describe_snapshots").paginate(SnapshotIds=sorted(snapshot_ids)):
            for snap in page["Snapshots"]:
                if run.protected(_tags(snap.get("Tags"))):
                    snapshot_ids.discard(snap["SnapshotId"])
    for sid in sorted(snapshot_ids):
        if dry:
            run.record(region, "ec2:snapshot", sid, None, "would-delete")
            continue
        try:
            ec2.delete_snapshot(SnapshotId=sid)
            run.record(region, "ec2:snapshot", sid, None, "fast-track-deleted")
        except Exception as exc:  # noqa: BLE001 - e.g. still pending; retried by a follow-up run
            run.record(region, "ec2:snapshot", sid, None, "error", f"delete failed, will retry: {exc}")
            run.wake(run.now + timedelta(minutes=15))

    for page in ec2.get_paginator("describe_volumes").paginate(Filters=tag_filter):
        for vol in page["Volumes"]:
            owner = _tags(vol.get("Tags")).get(FAST_OWNER_TAG)
            if vol["State"] != "available" or not _instance_gone(ec2, owner):
                run.wake(run.now + timedelta(minutes=10))
                continue
            if dry:
                run.record(region, "ec2:volume", vol["VolumeId"], None, "would-delete")
                continue
            try:
                ec2.delete_volume(VolumeId=vol["VolumeId"])
                run.record(region, "ec2:volume", vol["VolumeId"], None, "fast-track-deleted")
            except Exception as exc:  # noqa: BLE001
                run.record(region, "ec2:volume", vol["VolumeId"], None, "error", f"delete failed, will retry: {exc}")
                run.wake(run.now + timedelta(minutes=15))


def _instance_gone(ec2, instance_id):
    try:
        reservations = ec2.describe_instances(InstanceIds=[instance_id])["Reservations"]
    except ec2.exceptions.ClientError as exc:
        return "NotFound" in exc.response["Error"]["Code"]
    return all(i["State"]["Name"] == "terminated" for r in reservations for i in r["Instances"])


def _process_ec2(run, region):
    ec2 = boto3.client("ec2", region_name=region)
    paginator = ec2.get_paginator("describe_instances")
    for page in paginator.paginate(Filters=[{"Name": "instance-state-name", "Values": ["running", "stopped"]}]):
        for reservation in page["Reservations"]:
            for inst in reservation["Instances"]:
                iid = inst["InstanceId"]
                tags = _tags(inst.get("Tags"))
                age_hours = (run.now - inst["LaunchTime"]).total_seconds() / 3600
                age = int(age_hours // 24)
                fast = run.is_fast_track(tags)
                aged = age_hours >= run.cfg["fast_min_age_hours"] if fast else age >= run.cfg["age_days"]
                if not (aged or STOPPED_TAG in tags or NOTIFIED_TAG in tags):
                    continue
                if run.protected(tags):
                    run.record(region, "ec2:instance", iid, age, "skipped-protect-tag")
                    continue
                protection = ec2.describe_instance_attribute(InstanceId=iid, Attribute="disableApiTermination")
                if protection["DisableApiTermination"]["Value"]:
                    run.record(region, "ec2:instance", iid, age, "skipped-termination-protection")
                    continue

                def tag_fn(new, iid=iid):
                    ec2.create_tags(Resources=[iid], Tags=[{"Key": k, "Value": v} for k, v in new.items()])

                stopped_at = tags.get(STOPPED_TAG)
                if stopped_at:
                    if inst["State"]["Name"] == "running":
                        if run.cfg["dry_run"]:
                            run.record(region, "ec2:instance", iid, age, "would-clear-cleanup-tags")
                        else:
                            ec2.delete_tags(Resources=[iid], Tags=[{"Key": STOPPED_TAG}, {"Key": NOTIFIED_TAG}])
                            run.record(region, "ec2:instance", iid, age, "restarted-cleanup-tags-cleared")
                        continue
                    fast_hours = run.cfg["fast_terminate_hours"] if fast else None
                    deadline = _terminate_deadline(_parse(stopped_at), fast_hours)
                    if run.now < deadline:
                        run.record(region, "ec2:instance", iid, age, "awaiting-terminate", f"after {deadline.isoformat()}")
                        run.wake(deadline)
                    elif run.cfg["dry_run"]:
                        companions = _fast_track_companions(run, ec2, inst) if fast else {}
                        run.record(region, "ec2:instance", iid, age, "would-terminate", _companion_detail(companions))
                    elif not fast and run.mutations >= run.cfg["max_actions"]:
                        run.record(region, "ec2:instance", iid, age, "deferred-action-cap")
                    else:
                        companions = _fast_track_companions(run, ec2, inst) if fast else {}
                        everything = [rid for ids in companions.values() for rid in ids]
                        if everything:
                            ec2.create_tags(Resources=everything, Tags=[{"Key": FAST_OWNER_TAG, "Value": iid}])
                        ec2.terminate_instances(InstanceIds=[iid])
                        if not fast:
                            run.mutations += 1
                        run.record(region, "ec2:instance", iid, age, "terminated", _companion_detail(companions))
                    continue

                def stop_fn(iid=iid, state=inst["State"]["Name"], tag_fn=tag_fn, fast=fast):
                    if state == "running":
                        ec2.stop_instances(InstanceIds=[iid])
                    tag_fn({STOPPED_TAG: run.now.isoformat()})
                    run.wake(_terminate_deadline(run.now, run.cfg["fast_terminate_hours"] if fast else None))

                run.notify_then_act(
                    region, "ec2:instance", iid, age, tags, tag_fn, stop_fn, "stopped", "would-stop", capped=not fast
                )

    _fast_track_sweep(run, ec2, region)


def _process_ebs_volumes(run, region):
    ec2 = boto3.client("ec2", region_name=region)
    for page in ec2.get_paginator("describe_volumes").paginate(Filters=[{"Name": "status", "Values": ["available"]}]):
        for vol in page["Volumes"]:
            vid = vol["VolumeId"]
            tags = _tags(vol.get("Tags"))
            age = (run.now - vol["CreateTime"]).days
            if not run.eligible(age, tags):
                continue
            if run.protected(tags):
                run.record(region, "ec2:volume", vid, age, "skipped-protect-tag")
                continue

            def tag_fn(new, vid=vid):
                ec2.create_tags(Resources=[vid], Tags=[{"Key": k, "Value": v} for k, v in new.items()])

            run.notify_then_act(
                region, "ec2:volume", vid, age, tags, tag_fn,
                lambda vid=vid: ec2.delete_volume(VolumeId=vid), "deleted", "would-delete",
            )


def _process_snapshots(run, region):
    ec2 = boto3.client("ec2", region_name=region)
    ami_snapshots = {
        m["Ebs"]["SnapshotId"]
        for img in ec2.describe_images(Owners=["self"])["Images"]
        for m in img.get("BlockDeviceMappings", [])
        if "Ebs" in m and "SnapshotId" in m["Ebs"]
    }
    for page in ec2.get_paginator("describe_snapshots").paginate(OwnerIds=["self"]):
        for snap in page["Snapshots"]:
            sid = snap["SnapshotId"]
            tags = _tags(snap.get("Tags"))
            if sid in ami_snapshots or any(k.startswith("aws:") for k in tags):
                continue
            age = (run.now - snap["StartTime"]).days
            if not run.eligible(age, tags):
                continue
            if run.protected(tags):
                run.record(region, "ec2:snapshot", sid, age, "skipped-protect-tag")
                continue

            def tag_fn(new, sid=sid):
                ec2.create_tags(Resources=[sid], Tags=[{"Key": k, "Value": v} for k, v in new.items()])

            run.notify_then_act(
                region, "ec2:snapshot", sid, age, tags, tag_fn,
                lambda sid=sid: ec2.delete_snapshot(SnapshotId=sid), "deleted", "would-delete",
            )


def _process_rds(run, region):
    rds = boto3.client("rds", region_name=region)
    for page in rds.get_paginator("describe_db_instances").paginate():
        for db in page["DBInstances"]:
            dbid = db["DBInstanceIdentifier"]
            status = db["DBInstanceStatus"]
            age = (run.now - db["InstanceCreateTime"]).days
            if status == "stopped":
                stopped_tags = _tags(rds.list_tags_for_resource(ResourceName=db["DBInstanceArn"]).get("TagList"))
                if not run.protected(stopped_tags):
                    run.record(region, "rds:db", dbid, age, "idle-stopped", "stopped; start manually if still needed")
                continue
            if status != "available":
                continue
            tags = _tags(rds.list_tags_for_resource(ResourceName=db["DBInstanceArn"]).get("TagList"))
            if not run.eligible(age, tags):
                continue
            if run.protected(tags):
                run.record(region, "rds:db", dbid, age, "skipped-protect-tag")
                continue

            def tag_fn(new, arn=db["DBInstanceArn"]):
                rds.add_tags_to_resource(ResourceName=arn, Tags=[{"Key": k, "Value": v} for k, v in new.items()])

            def stop_fn(dbid=dbid, tags=tags, tag_fn=tag_fn):
                if STOPPED_TAG in tags:
                    rds.stop_db_instance(DBInstanceIdentifier=dbid)
                else:
                    stamp = run.now.strftime("%Y%m%d%H%M%S")
                    rds.stop_db_instance(DBInstanceIdentifier=dbid, DBSnapshotIdentifier=f"cleanup-{dbid}-{stamp}")
                tag_fn({STOPPED_TAG: run.now.isoformat()})

            run.notify_then_act(
                region, "rds:db", dbid, age, tags, tag_fn, stop_fn, "snapshotted-and-stopped", "would-snapshot-and-stop"
            )


def _process_report_only(run, region):
    age_days = run.cfg["age_days"]

    lam = boto3.client("lambda", region_name=region)
    for page in lam.get_paginator("list_functions").paginate():
        for fn in page["Functions"]:
            modified = datetime.strptime(fn["LastModified"], "%Y-%m-%dT%H:%M:%S.%f%z")
            age = (run.now - modified).days
            if age >= age_days:
                run.record(region, "lambda:function", fn["FunctionName"], age, "report-only", "not modified since threshold")

    ec2 = boto3.client("ec2", region_name=region)
    for page in ec2.get_paginator("describe_nat_gateways").paginate(Filters=[{"Name": "state", "Values": ["available"]}]):
        for nat in page["NatGateways"]:
            age = (run.now - nat["CreateTime"]).days
            if age >= age_days:
                run.record(region, "ec2:natgateway", nat["NatGatewayId"], age, "report-only", "verify it still carries traffic")
    for addr in ec2.describe_addresses()["Addresses"]:
        if "AssociationId" not in addr:
            run.record(region, "ec2:eip", addr.get("AllocationId", addr.get("PublicIp")), None, "report-only", "unassociated")

    elb = boto3.client("elbv2", region_name=region)
    for page in elb.get_paginator("describe_load_balancers").paginate():
        for lb in page["LoadBalancers"]:
            age = (run.now - lb["CreatedTime"]).days
            if age >= age_days and not elb.describe_target_groups(LoadBalancerArn=lb["LoadBalancerArn"])["TargetGroups"]:
                run.record(region, "elbv2:loadbalancer", lb["LoadBalancerName"], age, "report-only", "no target groups")


def _process_s3(run):
    s3 = boto3.client("s3")
    for bucket in s3.list_buckets()["Buckets"]:
        age = (run.now - bucket["CreationDate"]).days
        if age >= run.cfg["age_days"] and not s3.list_objects_v2(Bucket=bucket["Name"], MaxKeys=1).get("KeyCount"):
            run.record("global", "s3:bucket", bucket["Name"], age, "report-only", "empty bucket")


REGIONAL = {
    "ec2": _process_ec2,
    "ebs": _process_ebs_volumes,
    "snapshot": _process_snapshots,
    "rds": _process_rds,
    "report": _process_report_only,
}


def _all_regions():
    resp = boto3.client("ec2").describe_regions(
        Filters=[{"Name": "opt-in-status", "Values": ["opt-in-not-required", "opted-in"]}]
    )
    return sorted(r["RegionName"] for r in resp["Regions"])


def lambda_handler(event, context):
    cfg = _config()
    now = _parse(event["now"]) if event and event.get("now") else datetime.now(timezone.utc)
    run = Run(cfg, now)
    regions = _all_regions() if cfg["regions"] == ["all"] else cfg["regions"]

    for region in regions:
        for rtype in sorted(cfg["resource_types"]):
            processor = REGIONAL.get(rtype)
            if not processor:
                continue
            try:
                processor(run, region)
            except Exception as exc:  # noqa: BLE001 - report and keep going
                run.errors.append({"Region": region, "ResourceType": rtype, "Error": str(exc)})

    if "report" in cfg["resource_types"]:
        try:
            _process_s3(run)
        except Exception as exc:  # noqa: BLE001
            run.errors.append({"Region": "global", "ResourceType": "s3", "Error": str(exc)})

    report = {
        "GeneratedAt": now.isoformat(),
        "DryRun": cfg["dry_run"],
        "AgeThresholdDays": cfg["age_days"],
        "NoticeHours": cfg["notice_hours"],
        "RegionsScanned": regions,
        "Entries": run.entries,
        "Errors": run.errors,
    }

    if not cfg["dry_run"] and cfg["scheduler_role_arn"] and run.wakeups:
        function_arn = getattr(context, "invoked_function_arn", None) or os.environ.get("SELF_FUNCTION_ARN")
        if function_arn:
            _schedule_wakeups(cfg, run, function_arn)
        else:
            run.errors.append({"Region": "n/a", "ResourceType": "scheduler", "Error": "no function ARN to schedule"})

    if cfg["topic_arn"] and (run.errors or any(e["Status"] in NOTABLE or e["Status"].startswith("would-") for e in run.entries)):
        _publish(cfg["topic_arn"], report)
    return report


def _schedule_wakeups(cfg, run, function_arn):
    scheduler = boto3.client("scheduler", region_name=function_arn.split(":")[3])
    name_prefix = function_arn.split(":")[-1]
    for when in sorted(run.wakeups):
        fire_at = (when + timedelta(minutes=1)).astimezone(timezone.utc).replace(second=0, microsecond=0)
        if fire_at <= run.now:
            fire_at = run.now.astimezone(timezone.utc).replace(second=0, microsecond=0) + timedelta(minutes=1)
        try:
            scheduler.create_schedule(
                Name=f"{name_prefix}-{fire_at:%Y%m%dT%H%M}",
                GroupName=cfg["scheduler_group"],
                ScheduleExpression=f"at({fire_at:%Y-%m-%dT%H:%M:%S})",
                FlexibleTimeWindow={"Mode": "OFF"},
                Target={"Arn": function_arn, "RoleArn": cfg["scheduler_role_arn"], "Input": "{}"},
                ActionAfterCompletion="DELETE",
            )
        except scheduler.exceptions.ConflictException:
            continue
        except Exception as exc:  # noqa: BLE001 - a failed follow-up is reported, the daily run still catches up
            run.errors.append({"Region": "n/a", "ResourceType": "scheduler", "Error": str(exc)})


def _publish(topic_arn, report):
    mode = "DRY RUN" if report["DryRun"] else "LIVE"
    groups = {}
    for e in report["Entries"]:
        groups.setdefault(e["Status"], []).append(e)

    lines = [
        f"AWS resource cleanup [{mode}] - {report['GeneratedAt']}",
        f"Age threshold: {report['AgeThresholdDays']}d | notice window: {report['NoticeHours']}h | regions: {', '.join(report['RegionsScanned'])}",
        "",
        "To keep a resource, add the protect tag or invoke resource-protect with {\"ids\": [\"<id>\", ...]} before its action time.",
    ]
    for status in sorted(groups):
        lines.append("")
        lines.append(f"{status} ({len(groups[status])}):")
        for e in groups[status]:
            age = "" if e["AgeDays"] is None else f" age {e['AgeDays']}d"
            detail = f" - {e['Detail']}" if e["Detail"] else ""
            lines.append(f"  [{e['Region']}] {e['Type']} {e['Id']}{age}{detail}")
    if report["Errors"]:
        lines.append("")
        lines.append("Errors:")
        for err in report["Errors"]:
            lines.append(f"  [{err['Region']}] {err['ResourceType']}: {err['Error']}")

    try:
        boto3.client("sns").publish(
            TopicArn=topic_arn, Subject=f"AWS cleanup [{mode}]"[:100], Message="\n".join(lines)
        )
    except Exception as exc:  # noqa: BLE001 - never fail the run because notification failed
        report["Errors"].append({"Region": "n/a", "ResourceType": "sns", "Error": str(exc)})
