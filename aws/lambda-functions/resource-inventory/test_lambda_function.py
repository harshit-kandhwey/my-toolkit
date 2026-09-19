import os

import boto3
import pytest
from moto import mock_aws

import lambda_function


@pytest.fixture(autouse=True)
def aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "us-east-1")
    monkeypatch.setenv("REGIONS", "us-east-1")
    for var in ("OUTPUT_S3_BUCKET", "SENDER_EMAIL", "RECIPIENT_EMAIL"):
        monkeypatch.delenv(var, raising=False)


@mock_aws
def test_counts_instances_volumes_and_buckets():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.run_instances(ImageId="ami-12345678", MinCount=2, MaxCount=2)
    ec2.create_volume(AvailabilityZone="us-east-1a", Size=1)
    boto3.client("s3", region_name="us-east-1").create_bucket(Bucket="inventory-test-bucket")

    result = lambda_function.lambda_handler({}, None)

    assert result["SummaryByType"]["ec2:instance"] == 2
    assert result["SummaryByType"]["s3:bucket"] == 1
    assert result["SummaryByType"]["ec2:volume"] >= 1
    assert result["Errors"] == []


@mock_aws
def test_uploads_report_when_bucket_configured(monkeypatch):
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="report-bucket")
    monkeypatch.setenv("OUTPUT_S3_BUCKET", "report-bucket")

    lambda_function.lambda_handler({}, None)

    keys = [o["Key"] for o in s3.list_objects_v2(Bucket="report-bucket").get("Contents", [])]
    assert len(keys) == 1
    assert keys[0].startswith("resource-inventory/")


@mock_aws
def test_bad_region_is_reported_not_raised(monkeypatch):
    monkeypatch.setenv("REGIONS", "not-a-region")

    result = lambda_function.lambda_handler({}, None)

    assert result["Errors"], "collector failures should be surfaced in Errors"
    assert os.environ["REGIONS"] == "not-a-region"


@mock_aws
def test_tagged_resources_already_enumerated_are_not_double_counted():
    ec2 = boto3.client("ec2", region_name="us-east-1")
    ec2.run_instances(
        ImageId="ami-12345678", MinCount=1, MaxCount=1,
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": "web"}]}],
    )

    result = lambda_function.lambda_handler({}, None)

    assert result["SummaryByType"]["ec2:instance"] == 1
    assert result["OtherTaggedResourceCount"] == 0


def test_arn_key_distinguishes_services_and_regions():
    a = lambda_function._arn_key("arn:aws:lambda:us-east-1:123456789012:function:web")
    b = lambda_function._arn_key("arn:aws:ec2:us-east-1:123456789012:instance/web")
    assert a != b
    assert lambda_function._arn_key("arn:aws:s3:::bucket") == ("s3", "global", "", "bucket")


def test_rds_instance_and_cluster_with_same_name_do_not_collide():
    db = lambda_function._arn_key("arn:aws:rds:us-east-1:123456789012:db:app")
    cluster = lambda_function._arn_key("arn:aws:rds:us-east-1:123456789012:cluster:app")
    assert db != cluster
    record = {"Type": "rds:db", "Id": "app", "Region": "us-east-1"}
    assert lambda_function._record_key(record) == db
