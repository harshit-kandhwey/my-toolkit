# EC2 — Single Instance

**When to use:** You need one hardened EC2 instance quickly (IMDSv2, latest AL2023).

**Status:** not yet verified against a real account (Verified: never, region: n/a).

**Cost note:** Instance-hours bill until the stack is deleted.

A single EC2 instance on the latest Amazon Linux 2023 AMI (resolved via SSM public parameter, so it never goes stale), IMDSv2 enforced, and a security group that only opens SSH to a CIDR you specify.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `EnvironmentName` | `dev` | Prefix used in resource `Name` tags |
| `InstanceType` | `t3.micro` | x86_64 instance type only (`t3.*`); Graviton (`t4g`) needs the arm64 AMI path |
| `VpcId` | — | VPC to launch into |
| `SubnetId` | — | Subnet to launch into |
| `SshCidr` | — | CIDR allowed to reach port 22 — no default, and `0.0.0.0/0` is rejected by the parameter pattern |
| `KeyName` | — | Existing EC2 key pair name |
| `LatestAmiId` | AL2023 x86_64 SSM path | SSM parameter resolved to the AMI ID at deploy time |

## Outputs

| Output | Description |
|---|---|
| `InstanceId` | ID of the launched instance |
| `PrivateIp` | Private IP of the instance |
| `SecurityGroupId` | ID of the created security group |

## Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name my-instance \
  --parameter-overrides VpcId=vpc-xxxx SubnetId=subnet-xxxx SshCidr=203.0.113.0/32 KeyName=my-key
```

## Notes

- `MetadataOptions.HttpTokens: required` forces IMDSv2 — blocks the SSRF-to-credential-theft path that IMDSv1 allows.
- No egress rule is set, so the security group uses the AWS default (allow all outbound) — tighten `SecurityGroupEgress` if the workload needs restricted egress.
- Pair with [vpc-basic](../vpc-basic/) if you don't already have a VPC/subnet to target.
- **AMI drift:** `LatestAmiId` re-resolves on every stack update, so when AWS publishes a new AL2023 AMI the next update **replaces the instance**. To pin an AMI, store its ID in your own SSM parameter and override `LatestAmiId` with that parameter's name (a literal AMI ID is not accepted).
- The root volume is encrypted (gp3). There is no instance profile, so SSH is the only access path; add an `IamInstanceProfile` with `AmazonSSMManagedInstanceCore` for Session Manager.
