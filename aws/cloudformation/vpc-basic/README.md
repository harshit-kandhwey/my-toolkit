# VPC — Basic

**When to use:** You need a standard public/private two-AZ network for a new environment.

**Status:** not yet verified against a real account (Verified: never, region: n/a).

**Cost note:** The NAT gateway bills hourly plus per GB; delete the stack when done testing.

A standard two-AZ VPC: public + private subnet pair per AZ, an internet gateway for the public subnets, and a single NAT gateway (in AZ1) for private subnet egress.

## Parameters

| Parameter | Default | Description |
|---|---|---|
| `EnvironmentName` | `dev` | Prefix used in resource `Name` tags |
| `VpcCidr` | `10.0.0.0/16` | VPC CIDR block |
| `PublicSubnet1Cidr` / `PublicSubnet2Cidr` | `10.0.0.0/24` / `10.0.1.0/24` | Public subnet CIDRs, one per AZ |
| `PrivateSubnet1Cidr` / `PrivateSubnet2Cidr` | `10.0.10.0/24` / `10.0.11.0/24` | Private subnet CIDRs, one per AZ |

## Outputs

| Output | Description |
|---|---|
| `VpcId` | ID of the created VPC |
| `PublicSubnet1Id` / `PrivateSubnet1Id` | Single subnet IDs. Use `PublicSubnet1Id` as `SubnetId` in [ec2-instance](../ec2-instance/) when you need SSH: the private subnet has no public IPs and outbound-only NAT, so reaching an instance there needs SSM Session Manager, an EC2 Instance Connect Endpoint, a bastion or a VPN |
| `PublicSubnetIds` | Comma-separated public subnet IDs |
| `PrivateSubnetIds` | Comma-separated private subnet IDs |

## Deploy

```bash
aws cloudformation deploy \
  --template-file template.yaml \
  --stack-name my-vpc \
  --parameter-overrides EnvironmentName=dev
```

## Notes

- Single NAT gateway (not one per AZ) to minimize cost — private subnet 2's egress traverses AZ1's NAT. For production HA, add a second NAT gateway in `PublicSubnet2` and a second private route table.
- AZs are selected via `!GetAZs ""` (the first two available in the deploying region), not hardcoded.
- The subnet CIDRs must sit inside `VpcCidr`; if you change `VpcCidr`, change all four subnet CIDRs too. The parameters only validate CIDR format, not containment.
