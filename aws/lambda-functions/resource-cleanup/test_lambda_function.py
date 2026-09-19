from datetime import datetime, timedelta, timezone

import boto3
import pytest
from moto import mock_aws

import lambda_function

FRI = datetime(2030, 1, 4, 10, 0, tzinfo=timezone.utc)
MON = datetime(2030, 1, 7, 10, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for k, v in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "REGIONS": "us-east-1",
        "AGE_THRESHOLD_DAYS": "0",
        "DRY_RUN": "false",
        "RESOURCE_TYPES": "ec2",
    }.items():
        monkeypatch.setenv(k, v)
    for var in ("SNS_TOPIC_ARN", "FAST_TRACK_TAG_KEY"):
        monkeypatch.delenv(var, raising=False)


def run(now):
    return lambda_function.lambda_handler({"now": now.isoformat()}, None)


def statuses(report):
    return [e["Status"] for e in report["Entries"]]


def tags_of(ec2, rid):
    resp = ec2.describe_tags(Filters=[{"Name": "resource-id", "Values": [rid]}])
    return {t["Key"]: t["Value"] for t in resp["Tags"]}


def launch(ec2, tags=None):
    kwargs = {}
    if tags:
        kwargs["TagSpecifications"] = [
            {"ResourceType": "instance", "Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}
        ]
    return ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1, **kwargs)["Instances"][0]["InstanceId"]


def state(ec2, iid):
    return ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]["State"]["Name"]


@mock_aws
def test_dry_run_changes_nothing(monkeypatch):
    monkeypatch.setenv("DRY_RUN", "true")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    iid = launch(ec2)

    report = run(FRI)

    assert statuses(report) == ["would-notify"]
    assert tags_of(ec2, iid) == {}
    assert state(ec2, iid) == "running"


@mock_aws
def test_friday_stop_terminates_on_monday():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    iid = launch(ec2)

    assert statuses(run(FRI)) == ["notified"]
    assert statuses(run(FRI + timedelta(hours=1))) == ["awaiting-notice"]
    assert statuses(run(FRI + timedelta(hours=3))) == ["stopped"]
    assert state(ec2, iid) == "stopped"

    assert statuses(run(FRI + timedelta(hours=10))) == ["awaiting-terminate"]
    assert statuses(run(MON + timedelta(hours=2))) == ["awaiting-terminate"]
    assert statuses(run(MON + timedelta(hours=4))) == ["terminated"]
    assert state(ec2, iid) == "terminated"


@mock_aws
def test_weekday_stop_terminates_next_day():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    tue = datetime(2030, 1, 1, 10, 0, tzinfo=timezone.utc)
    iid = launch(ec2)

    run(tue)
    run(tue + timedelta(hours=3))
    assert statuses(run(tue + timedelta(hours=26))) == ["awaiting-terminate"]
    assert statuses(run(tue + timedelta(hours=28))) == ["terminated"]
    assert state(ec2, iid) == "terminated"


@mock_aws
def test_protect_tag_and_termination_protection_are_skipped():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    tagged = launch(ec2, {"Protect": "TRUE"})
    locked = launch(ec2)
    ec2.modify_instance_attribute(InstanceId=locked, DisableApiTermination={"Value": True})

    report = run(FRI)

    assert sorted(statuses(report)) == ["skipped-protect-tag", "skipped-termination-protection"]
    assert tags_of(ec2, tagged).get("Cleanup:NotifiedAt") is None
    assert tags_of(ec2, locked).get("Cleanup:NotifiedAt") is None


@mock_aws
def test_protect_tag_added_during_notice_window_cancels_the_stop():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    iid = launch(ec2)
    run(FRI)
    ec2.create_tags(Resources=[iid], Tags=[{"Key": "Protect", "Value": "true"}])

    assert statuses(run(FRI + timedelta(hours=3))) == ["skipped-protect-tag"]
    assert state(ec2, iid) == "running"


@mock_aws
def test_fast_track_instances_use_short_cycle(monkeypatch):
    monkeypatch.setenv("FAST_TRACK_TAG_KEY", "Purpose")
    monkeypatch.setenv("FAST_TRACK_TAG_VALUE", "test")
    monkeypatch.setenv("AGE_THRESHOLD_DAYS", "30")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    fast = launch(ec2, {"Purpose": "test"})
    slow = launch(ec2)
    launched = ec2.describe_instances(InstanceIds=[fast])["Reservations"][0]["Instances"][0]["LaunchTime"]

    assert statuses(run(launched + timedelta(hours=12))) == []
    t0 = launched + timedelta(hours=25)
    report = run(t0)
    assert [(e["Id"], e["Status"]) for e in report["Entries"]] == [(fast, "notified")]
    run(t0 + timedelta(hours=3))
    assert state(ec2, fast) == "stopped"
    assert statuses(run(t0 + timedelta(hours=8))) == ["awaiting-terminate"]
    assert statuses(run(t0 + timedelta(hours=10))) == ["terminated"]
    assert state(ec2, slow) == "running"


@mock_aws
def test_restarted_instance_has_cleanup_state_cleared():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    iid = launch(ec2)
    run(FRI)
    run(FRI + timedelta(hours=3))
    ec2.start_instances(InstanceIds=[iid])

    assert statuses(run(FRI + timedelta(hours=5))) == ["restarted-cleanup-tags-cleared"]
    assert "Cleanup:StoppedAt" not in tags_of(ec2, iid)


@mock_aws
def test_action_cap_defers_extra_stops(monkeypatch):
    monkeypatch.setenv("MAX_ACTIONS_PER_RUN", "1")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    launch(ec2)
    launch(ec2)
    run(FRI)

    assert sorted(statuses(run(FRI + timedelta(hours=3)))) == ["deferred-action-cap", "stopped"]


@mock_aws
def test_orphan_volume_deleted_after_notice_but_attached_volume_untouched(monkeypatch):
    monkeypatch.setenv("RESOURCE_TYPES", "ebs")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    orphan = ec2.create_volume(AvailabilityZone="us-east-1a", Size=1)["VolumeId"]
    attached = ec2.create_volume(AvailabilityZone="us-east-1a", Size=1)["VolumeId"]
    iid = ec2.run_instances(ImageId="ami-12345678", MinCount=1, MaxCount=1)["Instances"][0]["InstanceId"]
    ec2.attach_volume(VolumeId=attached, InstanceId=iid, Device="/dev/sdf")

    assert [e["Id"] for e in run(FRI)["Entries"]] == [orphan]
    assert statuses(run(FRI + timedelta(hours=3))) == ["deleted"]
    remaining = [v["VolumeId"] for v in ec2.describe_volumes()["Volumes"]]
    assert orphan not in remaining and attached in remaining


@mock_aws
def test_snapshot_backing_an_ami_is_never_touched(monkeypatch):
    monkeypatch.setenv("RESOURCE_TYPES", "snapshot")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    vol = ec2.create_volume(AvailabilityZone="us-east-1a", Size=1)["VolumeId"]
    orphan = ec2.create_snapshot(VolumeId=vol)["SnapshotId"]
    seed = ec2.create_snapshot(VolumeId=vol)["SnapshotId"]
    ec2.register_image(
        Name="img", RootDeviceName="/dev/sda1",
        BlockDeviceMappings=[{"DeviceName": "/dev/sda1", "Ebs": {"SnapshotId": seed}}],
    )
    image = ec2.describe_images(Owners=["self"])["Images"][0]
    backing = image["BlockDeviceMappings"][0]["Ebs"]["SnapshotId"]

    ids = [e["Id"] for e in run(FRI)["Entries"]]
    assert orphan in ids
    assert backing not in ids


@mock_aws
def test_rds_is_snapshotted_and_stopped_never_deleted_and_stopped_dbs_reported(monkeypatch):
    monkeypatch.setenv("RESOURCE_TYPES", "rds")
    rds = boto3.client("rds", region_name="us-east-1")
    rds.create_db_instance(
        DBInstanceIdentifier="app-db", DBInstanceClass="db.t3.micro", Engine="postgres",
        MasterUsername="u", MasterUserPassword="password123", AllocatedStorage=20,
    )

    assert statuses(run(FRI)) == ["notified"]
    assert statuses(run(FRI + timedelta(hours=3))) == ["snapshotted-and-stopped"]
    assert rds.describe_db_instances()["DBInstances"][0]["DBInstanceStatus"] == "stopped"
    assert rds.describe_db_snapshots(DBInstanceIdentifier="app-db")["DBSnapshots"]

    later = run(FRI + timedelta(days=5))
    assert statuses(later) == ["idle-stopped"]
    assert len(rds.describe_db_instances()["DBInstances"]) == 1


@mock_aws
def test_dry_run_does_not_clear_cleanup_tags_on_restarted_instance(monkeypatch):
    ec2 = boto3.client("ec2", region_name="us-east-1")
    iid = launch(ec2, {"Cleanup:NotifiedAt": FRI.isoformat(), "Cleanup:StoppedAt": FRI.isoformat()})
    monkeypatch.setenv("DRY_RUN", "true")

    assert statuses(run(FRI + timedelta(hours=5))) == ["would-clear-cleanup-tags"]
    assert set(tags_of(ec2, iid)) >= {"Cleanup:NotifiedAt", "Cleanup:StoppedAt"}


@mock_aws
def test_sns_notice_is_published_when_something_happens(monkeypatch):
    sns = boto3.client("sns", region_name="us-east-1")
    topic = sns.create_topic(Name="cleanup")["TopicArn"]
    sqs = boto3.client("sqs", region_name="us-east-1")
    queue = sqs.create_queue(QueueName="notices")["QueueUrl"]
    queue_arn = sqs.get_queue_attributes(QueueUrl=queue, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    sns.subscribe(TopicArn=topic, Protocol="sqs", Endpoint=queue_arn)
    monkeypatch.setenv("SNS_TOPIC_ARN", topic)
    ec2 = boto3.client("ec2", region_name="us-east-1")
    launch(ec2)

    report = run(FRI)

    assert statuses(report) == ["notified"]
    assert report["Errors"] == []
    assert sqs.receive_message(QueueUrl=queue).get("Messages")


@mock_aws
def test_report_only_lists_unassociated_eip_without_touching_it(monkeypatch):
    monkeypatch.setenv("RESOURCE_TYPES", "report")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    alloc = ec2.allocate_address(Domain="vpc")["AllocationId"]

    report = run(FRI)

    assert [(e["Id"], e["Status"]) for e in report["Entries"]] == [(alloc, "report-only")]
    assert ec2.describe_addresses()["Addresses"]


FUNCTION_ARN = "arn:aws:lambda:us-east-1:123456789012:function:resource-cleanup"
ROLE_ARN = "arn:aws:iam::123456789012:role/scheduler"


def schedules(monkeypatch=None):
    client = boto3.client("scheduler", region_name="us-east-1")
    out = {}
    for s in client.list_schedules()["Schedules"]:
        out[s["Name"]] = client.get_schedule(Name=s["Name"])["ScheduleExpression"]
    return out


@pytest.fixture
def scheduling(monkeypatch):
    monkeypatch.setenv("SCHEDULER_ROLE_ARN", ROLE_ARN)
    monkeypatch.setenv("SELF_FUNCTION_ARN", FUNCTION_ARN)


@mock_aws
def test_daily_run_schedules_its_own_follow_ups_for_the_fast_track_timeline(monkeypatch, scheduling):
    monkeypatch.setenv("FAST_TRACK_TAG_KEY", "Purpose")
    monkeypatch.setenv("FAST_TRACK_TAG_VALUE", "test")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    iid = launch(ec2, {"Purpose": "test"})
    launched = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]["LaunchTime"]

    collect = (launched + timedelta(hours=30)).replace(minute=30, second=0, microsecond=0)
    assert statuses(run(collect)) == ["notified"]
    first = collect + timedelta(hours=2, minutes=1)
    assert list(schedules().values()) == [f"at({first:%Y-%m-%dT%H:%M:%S})"]

    stop_run = collect + timedelta(hours=2, minutes=1)
    assert statuses(run(stop_run)) == ["stopped"]
    assert state(ec2, iid) == "stopped"
    terminate_at = stop_run + timedelta(hours=6, minutes=1)
    assert f"at({terminate_at:%Y-%m-%dT%H:%M:%S})" in schedules().values()

    assert statuses(run(stop_run + timedelta(hours=6, minutes=1))) == ["terminated"]


@mock_aws
def test_friday_stop_schedules_the_monday_terminate(scheduling):
    ec2 = boto3.client("ec2", region_name="us-east-1")
    launch(ec2)
    run(FRI)
    stop_run = FRI + timedelta(hours=2, minutes=1)
    run(stop_run)

    expected = (stop_run + timedelta(days=3, minutes=1)).replace(second=0, microsecond=0)
    assert f"at({expected:%Y-%m-%dT%H:%M:%S})" in schedules().values()


@mock_aws
def test_no_schedules_in_dry_run_or_without_a_scheduler_role(monkeypatch):
    ec2 = boto3.client("ec2", region_name="us-east-1")
    launch(ec2)
    monkeypatch.setenv("SELF_FUNCTION_ARN", FUNCTION_ARN)

    run(FRI)
    assert schedules() == {}

    monkeypatch.setenv("DRY_RUN", "true")
    monkeypatch.setenv("SCHEDULER_ROLE_ARN", ROLE_ARN)
    run(FRI)
    assert schedules() == {}


@mock_aws
def test_repeated_runs_do_not_fail_on_duplicate_schedules(scheduling):
    ec2 = boto3.client("ec2", region_name="us-east-1")
    launch(ec2)
    run(FRI)
    report = run(FRI + timedelta(minutes=5))

    assert report["Errors"] == []
    assert len(schedules()) == 1


@mock_aws
def test_action_cap_does_not_apply_to_fast_track_instances(monkeypatch):
    monkeypatch.setenv("MAX_ACTIONS_PER_RUN", "1")
    monkeypatch.setenv("FAST_TRACK_TAG_KEY", "Purpose")
    monkeypatch.setenv("FAST_TRACK_TAG_VALUE", "test")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    fast = [launch(ec2, {"Purpose": "test"}) for _ in range(3)]
    normal = [launch(ec2) for _ in range(2)]
    launched = ec2.describe_instances(InstanceIds=[fast[0]])["Reservations"][0]["Instances"][0]["LaunchTime"]
    t0 = launched + timedelta(hours=25)

    run(t0)
    stop_run = run(t0 + timedelta(hours=3))

    by_id = {e["Id"]: e["Status"] for e in stop_run["Entries"]}
    assert [by_id[i] for i in fast] == ["stopped"] * 3
    assert sorted(by_id[i] for i in normal) == ["deferred-action-cap", "stopped"]

    later = run(t0 + timedelta(hours=10))
    assert [e["Status"] for e in later["Entries"] if e["Id"] in fast] == ["terminated"] * 3


def image_ids(ec2):
    return {i["ImageId"] for i in ec2.describe_images(Owners=["self"])["Images"]}


def snapshot_ids(ec2):
    return {s["SnapshotId"] for s in ec2.describe_snapshots(OwnerIds=["self"])["Snapshots"]}


def volume_ids(ec2):
    return {v["VolumeId"] for v in ec2.describe_volumes()["Volumes"]}


@mock_aws
def test_fast_track_termination_also_removes_its_volumes_amis_and_snapshots(monkeypatch):
    monkeypatch.setenv("FAST_TRACK_TAG_KEY", "Purpose")
    monkeypatch.setenv("FAST_TRACK_TAG_VALUE", "test")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    seed = ec2.create_snapshot(VolumeId=ec2.create_volume(AvailabilityZone="us-east-1a", Size=1)["VolumeId"])["SnapshotId"]
    custom_ami = ec2.register_image(
        Name="custom", RootDeviceName="/dev/sda1",
        BlockDeviceMappings=[{"DeviceName": "/dev/sda1", "Ebs": {"SnapshotId": seed}}],
    )["ImageId"]
    custom_ami_snaps = {
        m["Ebs"]["SnapshotId"]
        for m in ec2.describe_images(ImageIds=[custom_ami])["Images"][0]["BlockDeviceMappings"] if "Ebs" in m
    }
    unrelated_ami = ec2.register_image(Name="unrelated", RootDeviceName="/dev/sda1")["ImageId"]

    iid = ec2.run_instances(
        ImageId=custom_ami, MinCount=1, MaxCount=1,
        BlockDeviceMappings=[{"DeviceName": "/dev/sdf", "Ebs": {"VolumeSize": 1, "DeleteOnTermination": False}}],
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Purpose", "Value": "test"}]}],
    )["Instances"][0]["InstanceId"]
    inst = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]
    data_vol = next(m["Ebs"]["VolumeId"] for m in inst["BlockDeviceMappings"] if m["DeviceName"] == "/dev/sdf")

    vol_snap = ec2.create_snapshot(VolumeId=data_vol)["SnapshotId"]
    protected_snap = ec2.create_snapshot(VolumeId=data_vol)["SnapshotId"]
    ec2.create_tags(Resources=[protected_snap], Tags=[{"Key": "Protect", "Value": "true"}])
    other_vol = ec2.create_volume(AvailabilityZone="us-east-1a", Size=1)["VolumeId"]
    other_snap = ec2.create_snapshot(VolumeId=other_vol)["SnapshotId"]

    t0 = inst["LaunchTime"] + timedelta(hours=25)
    run(t0)
    run(t0 + timedelta(hours=3))
    final = run(t0 + timedelta(hours=10))
    run(t0 + timedelta(hours=11))

    assert state(ec2, iid) == "terminated"
    assert custom_ami not in image_ids(ec2)
    assert unrelated_ami in image_ids(ec2)
    remaining_snaps = snapshot_ids(ec2)
    assert not (custom_ami_snaps & remaining_snaps)
    assert vol_snap not in remaining_snaps
    assert {protected_snap, other_snap} <= remaining_snaps
    assert data_vol not in volume_ids(ec2)
    assert other_vol in volume_ids(ec2)
    terminated = next(e for e in final["Entries"] if e["Status"] == "terminated")
    assert custom_ami in terminated["Detail"] and data_vol in terminated["Detail"]


@mock_aws
def test_sweep_keeps_protected_ami_snapshots(monkeypatch):
    monkeypatch.setenv("FAST_TRACK_TAG_KEY", "Purpose")
    monkeypatch.setenv("FAST_TRACK_TAG_VALUE", "test")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    seed = ec2.create_snapshot(VolumeId=ec2.create_volume(AvailabilityZone="us-east-1a", Size=1)["VolumeId"])["SnapshotId"]
    ami = ec2.register_image(
        Name="leftover", RootDeviceName="/dev/sda1",
        BlockDeviceMappings=[{"DeviceName": "/dev/sda1", "Ebs": {"SnapshotId": seed}}],
    )["ImageId"]
    snap = next(
        m["Ebs"]["SnapshotId"]
        for m in ec2.describe_images(ImageIds=[ami])["Images"][0]["BlockDeviceMappings"] if "Ebs" in m
    )
    ec2.create_tags(Resources=[snap], Tags=[{"Key": "Protect", "Value": "true"}])
    ec2.create_tags(Resources=[ami], Tags=[{"Key": "Cleanup:FastTrackOwner", "Value": "i-gone"}])

    report = run(datetime(2030, 1, 4, 10, 0, tzinfo=timezone.utc))

    assert ami not in image_ids(ec2)
    assert snap in snapshot_ids(ec2)
    assert not [e for e in report["Entries"] if e["Id"] == snap]


@mock_aws
def test_ami_shared_with_a_regular_instance_is_not_removed(monkeypatch):
    monkeypatch.setenv("FAST_TRACK_TAG_KEY", "Purpose")
    monkeypatch.setenv("FAST_TRACK_TAG_VALUE", "test")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    golden = ec2.register_image(Name="golden", RootDeviceName="/dev/sda1")["ImageId"]
    fast = ec2.run_instances(
        ImageId=golden, MinCount=1, MaxCount=1,
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Purpose", "Value": "test"}]}],
    )["Instances"][0]["InstanceId"]
    ec2.run_instances(ImageId=golden, MinCount=1, MaxCount=1, TagSpecifications=[
        {"ResourceType": "instance", "Tags": [{"Key": "Protect", "Value": "true"}]}])
    t0 = ec2.describe_instances(InstanceIds=[fast])["Reservations"][0]["Instances"][0]["LaunchTime"] + timedelta(hours=25)

    run(t0)
    run(t0 + timedelta(hours=3))
    run(t0 + timedelta(hours=10))

    assert state(ec2, fast) == "terminated"
    assert golden in image_ids(ec2)


@mock_aws
def test_non_fast_track_termination_leaves_amis_snapshots_and_volumes_alone():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    iid = ec2.run_instances(
        ImageId="ami-12345678", MinCount=1, MaxCount=1,
        BlockDeviceMappings=[{"DeviceName": "/dev/sdf", "Ebs": {"VolumeSize": 1, "DeleteOnTermination": False}}],
    )["Instances"][0]["InstanceId"]
    inst = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]
    data_vol = next(m["Ebs"]["VolumeId"] for m in inst["BlockDeviceMappings"] if m["DeviceName"] == "/dev/sdf")
    snap = ec2.create_snapshot(VolumeId=data_vol)["SnapshotId"]
    ami = ec2.create_image(InstanceId=iid, Name="img")["ImageId"]

    run(FRI)
    run(FRI + timedelta(hours=3))
    run(MON + timedelta(hours=4))

    assert state(ec2, iid) == "terminated"
    assert ami in image_ids(ec2) and snap in snapshot_ids(ec2)


@pytest.mark.parametrize(
    "ami_name,removed",
    [("fast-web-01", True), ("web-01-fast", True), ("golden-web", False)],
)
@mock_aws
def test_ami_is_removed_only_when_its_name_matches_a_configured_affix(monkeypatch, ami_name, removed):
    monkeypatch.setenv("FAST_TRACK_TAG_KEY", "Purpose")
    monkeypatch.setenv("FAST_TRACK_TAG_VALUE", "test")
    monkeypatch.setenv("FAST_TRACK_AMI_AFFIXES", "fast-, -fast")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    seed = ec2.create_snapshot(VolumeId=ec2.create_volume(AvailabilityZone="us-east-1a", Size=1)["VolumeId"])["SnapshotId"]
    ami = ec2.register_image(
        Name=ami_name, RootDeviceName="/dev/sda1",
        BlockDeviceMappings=[{"DeviceName": "/dev/sda1", "Ebs": {"SnapshotId": seed}}],
    )["ImageId"]
    ami_snaps = {
        m["Ebs"]["SnapshotId"]
        for m in ec2.describe_images(ImageIds=[ami])["Images"][0]["BlockDeviceMappings"] if "Ebs" in m
    }
    iid = ec2.run_instances(
        ImageId=ami, MinCount=1, MaxCount=1,
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Purpose", "Value": "test"}]}],
    )["Instances"][0]["InstanceId"]
    t0 = ec2.describe_instances(InstanceIds=[iid])["Reservations"][0]["Instances"][0]["LaunchTime"] + timedelta(hours=25)

    run(t0)
    run(t0 + timedelta(hours=3))
    run(t0 + timedelta(hours=10))

    assert state(ec2, iid) == "terminated"
    assert (ami not in image_ids(ec2)) is removed
    assert (not (ami_snaps & snapshot_ids(ec2))) is removed


@mock_aws
def test_extra_protect_tags_protect_scheduled_instances(monkeypatch):
    monkeypatch.setenv("EXTRA_PROTECT_TAGS", "Schedule, AutoStop=true")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    any_value = launch(ec2, {"Schedule": "office-hours"})
    exact = launch(ec2, {"AutoStop": "TRUE"})
    wrong_value = launch(ec2, {"AutoStop": "false"})
    plain = launch(ec2)

    by_id = {e["Id"]: e["Status"] for e in run(FRI)["Entries"]}

    assert by_id[any_value] == "skipped-protect-tag"
    assert by_id[exact] == "skipped-protect-tag"
    assert by_id[wrong_value] == "notified"
    assert by_id[plain] == "notified"


@mock_aws
def test_extra_protect_tag_added_mid_window_cancels_the_stop(monkeypatch):
    monkeypatch.setenv("EXTRA_PROTECT_TAGS", "Schedule")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    iid = launch(ec2)
    run(FRI)
    ec2.create_tags(Resources=[iid], Tags=[{"Key": "Schedule", "Value": "office-hours"}])

    assert statuses(run(FRI + timedelta(hours=3))) == ["skipped-protect-tag"]
    assert state(ec2, iid) == "running"


@mock_aws
def test_stopped_rds_is_reported_idle_unless_it_is_protected_or_scheduled(monkeypatch):
    monkeypatch.setenv("RESOURCE_TYPES", "rds")
    monkeypatch.setenv("EXTRA_PROTECT_TAGS", "Schedule")
    rds = boto3.client("rds", region_name="us-east-1")
    for name, tags in {
        "plain-db": [],
        "scheduled-db": [{"Key": "Schedule", "Value": "office-hours"}],
        "protected-db": [{"Key": "Protect", "Value": "true"}],
    }.items():
        rds.create_db_instance(
            DBInstanceIdentifier=name, DBInstanceClass="db.t3.micro", Engine="postgres",
            MasterUsername="u", MasterUserPassword="password123", AllocatedStorage=20, Tags=tags,
        )
        rds.stop_db_instance(DBInstanceIdentifier=name)

    report = run(FRI)

    assert [(e["Id"], e["Status"]) for e in report["Entries"]] == [("plain-db", "idle-stopped")]
