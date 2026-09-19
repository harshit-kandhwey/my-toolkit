import boto3
import pytest
from moto import mock_aws

import lambda_function


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for k, v in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "REGIONS": "us-east-1",
    }.items():
        monkeypatch.setenv(k, v)


def launch(ec2, tags):
    return ec2.run_instances(
        ImageId="ami-12345678", MinCount=1, MaxCount=1,
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": k, "Value": v} for k, v in tags.items()]}],
    )["Instances"][0]["InstanceId"]


def tags_of(ec2, rid):
    return {t["Key"]: t["Value"] for t in ec2.describe_tags(Filters=[{"Name": "resource-id", "Values": [rid]}])["Tags"]}


@mock_aws
def test_list_shows_only_queued_resources():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    queued = launch(ec2, {"Cleanup:NotifiedAt": "2030-01-04T10:00:00+00:00"})
    launch(ec2, {"Name": "not-queued"})

    result = lambda_function.lambda_handler({"action": "list"}, None)

    assert [q["Id"] for q in result["Queued"]] == [queued]


@mock_aws
def test_protect_applies_exact_tag_and_clears_cleanup_state():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    iid = launch(ec2, {"Cleanup:NotifiedAt": "2030-01-04T10:00:00+00:00", "Cleanup:StoppedAt": "x"})

    result = lambda_function.lambda_handler({"action": "protect", "ids": [iid, "i-doesnotexist"]}, None)

    assert result["Protected"] == [iid]
    assert result["NotInQueue"] == ["i-doesnotexist"]
    assert tags_of(ec2, iid) == {"Protect": "true"}


@mock_aws
def test_protect_uses_configured_tag(monkeypatch):
    monkeypatch.setenv("PROTECT_TAG_KEY", "KeepMe")
    monkeypatch.setenv("PROTECT_TAG_VALUE", "yes")
    ec2 = boto3.client("ec2", region_name="us-east-1")
    iid = launch(ec2, {"Cleanup:NotifiedAt": "2030-01-04T10:00:00+00:00"})

    lambda_function.lambda_handler({"action": "protect", "ids": [iid]}, None)

    assert tags_of(ec2, iid) == {"KeepMe": "yes"}


def test_unknown_action_is_rejected():
    with mock_aws():
        assert "Error" in lambda_function.lambda_handler({"action": "delete"}, None)


@mock_aws
def test_bare_id_queued_in_two_regions_is_rejected_but_region_qualified_id_works(monkeypatch):
    monkeypatch.setenv("REGIONS", "us-east-1,us-west-2")
    east = boto3.client("ec2", region_name="us-east-1")
    west = boto3.client("ec2", region_name="us-west-2")
    ia = launch(east, {"Cleanup:NotifiedAt": "2030-01-04T10:00:00+00:00"})
    ib = launch(west, {"Cleanup:NotifiedAt": "2030-01-04T10:00:00+00:00"})
    if ia != ib:
        pytest.skip("moto generated distinct ids; cannot force a cross-region clash")

    result = lambda_function.lambda_handler({"action": "protect", "ids": [ia]}, None)
    assert result["Ambiguous"] == [ia] and result["Protected"] == []

    result = lambda_function.lambda_handler({"action": "protect", "ids": [f"us-west-2:{ia}"]}, None)
    assert result["Protected"] == [ia]
    assert tags_of(west, ia) == {"Protect": "true"}
    assert "Protect" not in tags_of(east, ia)


def test_batches_of_twenty():
    assert [len(b) for b in lambda_function._batches(list(range(45)))] == [20, 20, 5]
