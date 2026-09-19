import json
from datetime import datetime, timezone

import boto3
import pytest
from moto import mock_aws

import lambda_function

T1 = datetime(2030, 1, 10, 10, 0, tzinfo=timezone.utc)
T2 = datetime(2030, 1, 10, 11, 0, tzinfo=timezone.utc)
FEB = datetime(2030, 2, 3, 6, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    for k, v in {
        "AWS_ACCESS_KEY_ID": "testing",
        "AWS_SECRET_ACCESS_KEY": "testing",
        "AWS_DEFAULT_REGION": "us-east-1",
        "REGIONS": "us-east-1",
        "TABLE_NAME": "cost-hours",
    }.items():
        monkeypatch.setenv(k, v)
    for var in ("REPORT_BUCKET", "SNS_TOPIC_ARN"):
        monkeypatch.delenv(var, raising=False)


def make_table():
    return boto3.resource("dynamodb", region_name="us-east-1").create_table(
        TableName="cost-hours",
        KeySchema=[{"AttributeName": "pk", "KeyType": "HASH"}, {"AttributeName": "sk", "KeyType": "RANGE"}],
        AttributeDefinitions=[{"AttributeName": "pk", "AttributeType": "S"}, {"AttributeName": "sk", "AttributeType": "S"}],
        BillingMode="PAY_PER_REQUEST",
    )


def launch(ec2, itype="t3.micro"):
    return ec2.run_instances(
        ImageId="ami-12345678", InstanceType=itype, MinCount=1, MaxCount=1,
        TagSpecifications=[{"ResourceType": "instance", "Tags": [{"Key": "Name", "Value": "web"}]}],
    )["Instances"][0]["InstanceId"]


def test_usage_type_uses_region_prefix_and_rds_flavour():
    assert lambda_function.usage_type("ec2", "us-east-1", "c6a.16xlarge") == "BoxUsage:c6a.16xlarge"
    assert lambda_function.usage_type("ec2", "ap-south-1", "c6a.16xlarge") == "APS3-BoxUsage:c6a.16xlarge"
    assert lambda_function.usage_type("rds", "eu-west-1", "db.t3.micro") == "EU-InstanceUsage:db.t3.micro"
    assert lambda_function.usage_type("rds", "eu-west-1", "db.t3.micro", multi_az=True) == "EU-Multi-AZUsage:db.t3.micro"
    assert lambda_function.usage_type("ec2", "xx-nowhere-1", "t3.micro") is None


@mock_aws
def test_record_adds_hours_only_for_running_instances():
    table = make_table()
    ec2 = boto3.client("ec2", region_name="us-east-1")
    running = launch(ec2)
    stopped = launch(ec2)
    ec2.stop_instances(InstanceIds=[stopped])

    lambda_function.lambda_handler({"action": "record", "now": T1.isoformat()}, None)
    result = lambda_function.lambda_handler({"now": T2.isoformat()}, None)

    assert result["ResourcesSampled"] == 1
    items = table.scan()["Items"]
    assert [i["ResourceId"] for i in items] == [running]
    assert items[0]["Hours"] == 2
    assert items[0]["UsageType"] == "BoxUsage:t3.micro"
    assert items[0]["Name"] == "web"


@mock_aws
def test_report_prices_hours_with_effective_rate_and_reconciles(monkeypatch):
    table = make_table()
    ec2 = boto3.client("ec2", region_name="us-east-1")
    launch(ec2)
    for _ in range(3):
        lambda_function.lambda_handler({"action": "record", "now": T1.isoformat()}, None)
    s3 = boto3.client("s3", region_name="us-east-1")
    s3.create_bucket(Bucket="reports")
    monkeypatch.setenv("REPORT_BUCKET", "reports")
    # Cost Explorer says 12 billable hours cost $6.00 -> $0.50/h; we sampled 3 of them.
    monkeypatch.setattr(
        lambda_function, "_ce_usage",
        lambda month: {"BoxUsage:t3.micro": {"cost": 6.0, "hours": 12.0}},
    )

    result = lambda_function.lambda_handler({"action": "report", "now": FEB.isoformat()}, None)

    assert result["Month"] == "2030-01"
    assert result["TotalAllocatedCost"] == 1.5
    report = json.loads(s3.get_object(Bucket="reports", Key="cost-report/2030-01.json")["Body"].read())
    assert report["Resources"][0]["Cost"] == 1.5
    assert report["Reconciliation"]["BoxUsage:t3.micro"]["CoveragePercent"] == 25.0
    assert table.scan()["Items"][0]["Cost"] == 1.5


@mock_aws
def test_report_lists_resources_without_a_matching_usage_type_as_unpriced(monkeypatch):
    make_table()
    launch(boto3.client("ec2", region_name="us-east-1"), "t3.small")
    lambda_function.lambda_handler({"action": "record", "now": T1.isoformat()}, None)
    monkeypatch.setattr(lambda_function, "_ce_usage", lambda month: {})

    result = lambda_function.lambda_handler({"action": "report", "now": FEB.isoformat()}, None)

    assert result["Unpriced"] == 1
    assert result["TotalAllocatedCost"] == 0


@mock_aws
def test_report_summary_is_published(monkeypatch):
    make_table()
    launch(boto3.client("ec2", region_name="us-east-1"))
    lambda_function.lambda_handler({"action": "record", "now": T1.isoformat()}, None)
    sns = boto3.client("sns", region_name="us-east-1")
    topic = sns.create_topic(Name="cost")["TopicArn"]
    sqs = boto3.client("sqs", region_name="us-east-1")
    queue = sqs.create_queue(QueueName="q")["QueueUrl"]
    arn = sqs.get_queue_attributes(QueueUrl=queue, AttributeNames=["QueueArn"])["Attributes"]["QueueArn"]
    sns.subscribe(TopicArn=topic, Protocol="sqs", Endpoint=arn)
    monkeypatch.setenv("SNS_TOPIC_ARN", topic)
    monkeypatch.setattr(lambda_function, "_ce_usage", lambda month: {"BoxUsage:t3.micro": {"cost": 1.0, "hours": 2.0}})

    lambda_function.lambda_handler({"action": "report", "now": FEB.isoformat()}, None)

    assert "2030-01" in sqs.receive_message(QueueUrl=queue)["Messages"][0]["Body"]


def test_unknown_action_is_rejected():
    assert "unknown action" in lambda_function.lambda_handler({"action": "nope"}, None)["Error"]


def test_month_bounds_handle_year_end():
    assert lambda_function._month_bounds("2030-12") == ("2030-12-01", "2031-01-01")
