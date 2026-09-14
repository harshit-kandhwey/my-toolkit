# Section 101 (Part 12): Subnets, Route Tables, and Availability Zones in Cloud Networks

## 1. Definition

**Plain language:** Once a VPC/VNet exists, it's carved into smaller address ranges called subnets, each one anchored to a specific physical location the provider calls an availability zone. A route table then decides, for each subnet, where traffic destined for any given address range actually goes — out to the internet, to another subnet, or nowhere at all.

**Precise definition:** A **subnet** is a contiguous sub-range of a VPC/VNet's CIDR block ([§100](Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md)), created using the same subnetting math introduced in [§17](../Part3/Section-17-Part3-Subnetting-Fundamentals-Borrowing-Bits-Calculating-Ranges.md), and associated with exactly one **Availability Zone (AZ)** — an isolated physical data center (or cluster of them) within a cloud region, engineered to fail independently of other AZs in the same region. A **route table** is the cloud-managed equivalent of the routing table concept from [§26](../Part4/Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md), applied per-subnet (AWS, GCP) or per-subnet-with-inheritance (Azure): it holds a set of destination-CIDR-to-target rules, evaluated by longest-prefix match exactly as in on-premises routing, that determine where traffic leaving that subnet is forwarded. The combination of subnet-per-AZ placement plus explicit route tables is how every major provider implements both fault isolation and traffic control inside a single VPC/VNet.

> 💡 **Tip:** "Public subnet" and "private subnet" are not a formal cloud API concept — they are informal shorthand for "a subnet whose route table sends `0.0.0.0/0` traffic to an internet gateway" versus "one that doesn't." Understanding this now avoids confusion later when a subnet behaves unexpectedly and the route table, not some hidden subnet property, turns out to be the actual cause.

## 2. Why This Matters

- **Subnet-to-AZ placement is the primary mechanism for achieving high availability in the cloud.** Spreading application instances across subnets in multiple AZs is the standard way to survive a single data center failure without any custom failover logic — this is the cloud-native realization of the redundancy principle introduced generally in [§72](../Part9/Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md).
- **Route tables, not subnet labels, actually determine reachability.** Assuming a subnet is "private" because a team named it that, without checking its actual route table, is a frequent and dangerous misunderstanding that leads to accidental public exposure or unexpected connectivity failures.
- **Certification exams and real interviews test this distinction relentlessly** — being unable to explain precisely why a subnet is public or private (in terms of its route table, not its name) is one of the fastest ways to fail a cloud networking screening question.
- **Almost every managed cloud service (databases, load balancers from [§80](../Part9/Section-80-Part9-Cloud-Load-Balancer-Types-ALB-NLB-Azure-LB-App-Gateway-GCP-LB-Conceptual.md), compute) requires choosing a subnet at creation time**, making this one of the most frequently exercised pieces of cloud networking knowledge in daily operational work.
- **Multi-AZ subnet design is a prerequisite for the higher-level architectures in this Part** — hub-and-spoke ([§104](Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md)) and multi-region design ([§108](Section-108-Part12-Multi-Region-and-Multi-Cloud-Networking-Considerations.md)) both assume a correct single-VPC multi-AZ foundation is already in place.

## 3. Prerequisites and Dependencies

This section builds directly on [§100](Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md)'s VPC/VNet container concept and assumes the subnetting mechanics from [§17](../Part3/Section-17-Part3-Subnetting-Fundamentals-Borrowing-Bits-Calculating-Ranges.md) and [§18](../Part3/Section-18-Part3-VLSM-Variable-Length-Subnet-Masking-and-Subnetting-Practice-Problems.md) (VLSM, used routinely to size subnets of different purposes differently within one VPC/VNet). It also depends on the routing table and longest-prefix-match concepts from [§26](../Part4/Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md) and the default/null route concepts from [§28](../Part4/Section-28-Part4-Default-Routes-Null-Routes-and-Route-Summarization.md), since a cloud route table is a direct, API-managed application of those same ideas. It is a direct prerequisite for [§102](Section-102-Part12-Internet-Gateways-NAT-Gateways-and-Egress-Patterns.md) (the internet/NAT gateways that route table entries point to) and for the security-group/NACL placement decisions covered in [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md).

## 4. Architecture / Conceptual Diagram

```text
   VPC/VNet: 10.0.0.0/16

   Availability Zone A            Availability Zone B
   ┌─────────────────────┐        ┌─────────────────────┐
   │ Public Subnet        │        │ Public Subnet        │
   │ 10.0.0.0/24          │        │ 10.0.2.0/24          │
   │ Route: 0.0.0.0/0     │        │ Route: 0.0.0.0/0     │
   │   ► Internet Gateway │        │   ► Internet Gateway │
   ├─────────────────────┤        ├─────────────────────┤
   │ Private Subnet       │        │ Private Subnet       │
   │ 10.0.1.0/24          │        │ 10.0.3.0/24          │
   │ Route: 0.0.0.0/0     │        │ Route: 0.0.0.0/0     │
   │   ► NAT Gateway      │        │   ► NAT Gateway      │
   │ Route: 10.0.0.0/16   │        │ Route: 10.0.0.0/16   │
   │   ► local            │        │   ► local            │
   └─────────────────────┘        └─────────────────────┘
             ▲                               ▲
             └──────────── same VPC ─────────┘
                (both AZs isolated physical
                 failure domains — §102 covers
                 the gateways referenced above)
```

- Every subnet lives in exactly one AZ — this is a hard constraint on AWS and Azure; a subnet cannot span two AZs, which is precisely why high-availability designs create at least one subnet per tier *per AZ*, not one large subnet shared across zones.
- The `local` route for the VPC's own CIDR range (`10.0.0.0/16` above) exists implicitly in every route table on AWS and Azure and cannot be removed — it's what allows same-VPC subnet-to-subnet traffic to flow without any explicit gateway.
- The only structural difference between the "public" and "private" subnets drawn above is their `0.0.0.0/0` route's target — everything else about them (their own CIDR, their AZ, the resources placed in them) is identical in kind.

## 5. Hands-On

### 5.1 Creating an AWS Subnet Tied to a Specific Availability Zone

**Purpose:** Show how AZ placement is set explicitly at subnet-creation time, the mechanism underlying every multi-AZ design.

**Syntax:**

```bash
aws ec2 create-subnet \
  --vpc-id <vpc-id> \
  --cidr-block <subnet-cidr> \
  --availability-zone <az-name>
```

**Example usage and expected output:**

```bash
$ aws ec2 create-subnet --vpc-id vpc-0a1b2c3d4e5f6a7b8 \
    --cidr-block 10.0.0.0/24 --availability-zone us-east-1a
{
    "Subnet": {
        "SubnetId": "subnet-0f1e2d3c4b5a69788",
        "VpcId": "vpc-0a1b2c3d4e5f6a7b8",
        "CidrBlock": "10.0.0.0/24",
        "AvailabilityZone": "us-east-1a",
        "State": "available"
    }
}
```

- `--availability-zone us-east-1a` is what pins this subnet's fault domain — repeating this call with `us-east-1b` and a non-overlapping CIDR is the standard next step for a two-AZ design.

**Production usage example:** Production AWS architectures near-universally create subnets in at least two (often three) AZs per tier, so that an Auto Scaling group or a load balancer's targets ([§80](../Part9/Section-80-Part9-Cloud-Load-Balancer-Types-ALB-NLB-Azure-LB-App-Gateway-GCP-LB-Conceptual.md)) can be spread across independent failure domains.

**Common errors:** Creating all subnets in a single AZ defeats the purpose of AZ-based redundancy entirely — a single AZ outage then takes down the whole workload despite the VPC nominally being "multi-subnet."

### 5.2 Creating and Associating a Custom Route Table on AWS

**Purpose:** Demonstrate explicitly overriding a subnet's default route table association — the exact mechanism that turns a subnet "private" or "public."

**Syntax:**

```bash
aws ec2 create-route-table --vpc-id <vpc-id>
aws ec2 create-route --route-table-id <rtb-id> --destination-cidr-block 0.0.0.0/0 --nat-gateway-id <nat-gw-id>
aws ec2 associate-route-table --route-table-id <rtb-id> --subnet-id <subnet-id>
```

**Example usage and expected output:**

```bash
$ aws ec2 create-route --route-table-id rtb-0abc123 \
    --destination-cidr-block 0.0.0.0/0 --nat-gateway-id nat-0def456
{
    "Return": true
}

$ aws ec2 describe-route-tables --route-table-ids rtb-0abc123 \
    --query 'RouteTables[0].Routes'
[
    {"DestinationCidrBlock": "10.0.0.0/16", "GatewayId": "local", "State": "active"},
    {"DestinationCidrBlock": "0.0.0.0/0", "NatGatewayId": "nat-0def456", "State": "active"}
]
```

- The `describe-route-tables` output is the definitive way to confirm whether a subnet is "public" or "private" in practice — it shows the `0.0.0.0/0` route pointing at a NAT gateway (private-style egress, [§102](Section-102-Part12-Internet-Gateways-NAT-Gateways-and-Egress-Patterns.md)) rather than an internet gateway directly.

**Production usage example:** This describe-route-tables call is the standard first diagnostic step when a subnet's actual reachability doesn't match what its name or documentation claims — trusting the route table over any label is the correct instinct.

**Common errors:** Forgetting the explicit `associate-route-table` call leaves a subnet attached to the VPC's **main route table** by default, which may have very different (or no) internet egress rules than intended — a subtle, frequently-missed step.

### 5.3 Listing Subnets and Their Route Associations on Azure

**Purpose:** Show the Azure equivalent of inspecting subnet/route-table associations, noting Azure's per-subnet **Route Table** resource model.

**Syntax:**

```bash
az network vnet subnet show \
  --resource-group <resource-group> \
  --vnet-name <vnet-name> \
  --name <subnet-name>
```

**Example usage and expected output:**

```bash
$ az network vnet subnet show --resource-group prod-rg --vnet-name prod-vnet --name app-subnet
{
  "name": "app-subnet",
  "addressPrefix": "10.1.1.0/24",
  "routeTable": {
    "id": "/subscriptions/.../routeTables/app-rt"
  }
}
```

- The `routeTable` field being present confirms a custom User-Defined Route (UDR) table is attached; its absence means the subnet relies entirely on Azure's implicit system routes (local VNet traffic, and default internet egress unless explicitly blocked).

**Production usage example:** Azure UDRs are commonly used to force all outbound subnet traffic through a network virtual appliance or Azure Firewall rather than direct internet egress — a pattern verified with exactly this command during a security review.

**Common errors:** Assuming a subnet with no explicit route table has no internet access at all — Azure's implicit system routes still provide default internet egress unless a UDR or NSG explicitly overrides it, a common point of confusion for engineers coming from AWS, where a subnet with no route to an internet or NAT gateway has none.

## 6. Production Usage Notes

- **Standard production convention reserves one small subnet tier per AZ for load balancers/gateways ("public"), one for application compute, and one for data stores ("private"), repeated identically in every AZ used** — this tiering, layered on top of AZ redundancy, is the most common real-world VPC/VNet subnet layout.
- **AWS and Azure require creating a subnet per AZ explicitly; GCP subnets are regional, not zonal** — a single GCP subnet spans all zones within its region automatically, meaning GCP achieves zone-level redundancy without the "one subnet per AZ" pattern AWS/Azure require.
- **Route table changes take effect immediately and silently** — there's no confirmation step before an added or removed route changes live traffic behavior, making route table edits in production networks a change that deserves the same review rigor as a firewall rule change.

## 7. Security Considerations

- The "public vs. private subnet" distinction is a routing property, not an access-control property — a subnet routed to an internet gateway is *reachable from* the internet only if security groups/NACLs ([§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)) also permit it; conflating the two leads to either false confidence or unnecessary over-restriction.
- Data-tier subnets should almost always have no direct route to an internet gateway at all, relying instead on NAT egress ([§102](Section-102-Part12-Internet-Gateways-NAT-Gateways-and-Egress-Patterns.md)) only if outbound internet access is genuinely required, and ideally none.
- Route table changes should be subject to the same change-review process as firewall/security-group changes, since a route table edit can silently redirect or expose traffic without any corresponding security-group change to draw attention to it.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely Cause | Resolution Path |
| --- | --- | --- |
| Resource in a "private" subnet is unexpectedly internet-reachable | Subnet's route table actually routes `0.0.0.0/0` to an internet gateway despite its name/tag | Inspect the route table directly (`describe-route-tables` / `az network vnet subnet show`) rather than trusting the subnet's label |
| Instance has no internet access despite being in a "public" subnet | Subnet associated with the VPC's default/main route table instead of the intended custom one | Explicitly associate the correct route table with the subnet |
| Application deployed across "multiple subnets" still fails entirely during a single data center outage | All subnets created in the same Availability Zone | Recreate subnets across at least two AZs and redistribute resources |
| Azure subnet has internet access nobody explicitly configured | Azure's implicit system route provides default outbound internet access absent an overriding UDR/NSG | Attach a UDR or NSG rule explicitly denying unwanted egress if that access is unintended |

## 9. Best Practices

- Design subnet CIDR sizing with VLSM ([§18](../Part3/Section-18-Part3-VLSM-Variable-Length-Subnet-Masking-and-Subnetting-Practice-Problems.md)) deliberately — smaller ranges for load-balancer/gateway tiers, larger ranges for elastic application compute tiers, sized to realistic maximum scale.
- Always verify a subnet's actual routing behavior via the route table API/CLI output rather than relying on naming conventions or tags, especially during security reviews.
- On AWS and Azure, replicate the full subnet tier structure identically across at least two AZs from the start, rather than retrofitting redundancy after a single-AZ design is already in production.

## 10. Common Anti-Patterns / Mistakes

- **Naming a subnet "private" without verifying its route table actually has no path to an internet gateway.** The name carries no enforcement; only the route table does.
- **Building a single-AZ network and treating multi-AZ expansion as a "later" concern.** Retrofitting AZ redundancy onto a live production network is significantly more disruptive than designing for it from the start.
- **Editing production route tables without the same change-control rigor applied to security group/firewall changes.** A route change can silently redirect traffic with no corresponding alert.

## 11. Interview Questions

**🎯 Beginner:** _"What makes a subnet 'public' versus 'private' in a cloud VPC?"_
**Model answer:** It comes down entirely to that subnet's route table — specifically, whether its `0.0.0.0/0` (default) route points to an internet gateway (making it effectively public, assuming security groups/NACLs also permit the traffic) or to something else, like a NAT gateway or no default route at all (making it private). There's no separate "public/private" flag on the subnet itself; it's purely a consequence of routing configuration.
_What the interviewer is probing for:_ Understanding that public/private is a routing behavior, not an inherent subnet attribute, and knowing exactly which route table entry determines it.

**🎯 Intermediate:** _"Why does a production VPC typically have multiple subnets per tier instead of just one subnet per tier?"_
**Model answer:** Because each subnet is tied to exactly one Availability Zone, and a single subnet per tier would concentrate every instance of that tier in one physical failure domain. Creating one subnet per tier *per AZ* (for example, two app-tier subnets across two AZs) allows resources to be spread across independent failure domains, so that a single AZ outage doesn't take down the entire tier — this is the standard way cloud architectures achieve high availability without any custom failover code.
_What the interviewer is probing for:_ Connecting subnet-per-AZ design directly to the availability goal it serves, not just reciting that "you should use multiple subnets."

**🎯 Senior:** _"A teammate insists their database subnet is secure because it's tagged 'private-db-subnet' and has strict security group rules. What would you still want to verify before agreeing?"_
**Model answer:** Security group rules control *who* can reach the resource, but they say nothing about whether the subnet itself has an outbound path to the internet at all — I'd explicitly check the subnet's route table to confirm there's no `0.0.0.0/0` route to an internet gateway (and ideally none at all, or only to a NAT gateway if truly required). A tag is documentation, not enforcement; the security groups control inbound/outbound rules at the resource level, but a genuinely isolated data tier should also have no unnecessary route out to the public internet in the first place, giving defense in depth rather than relying on security groups alone.
_What the interviewer is probing for:_ Recognizing that naming conventions and security group rules are necessary but not sufficient — actual route table verification is the ground truth, and layered controls (routing plus security groups) are stronger than either alone.

**🎯 Architect:** _"You're designing the subnet layout for a new AWS VPC that will eventually need to scale to hundreds of application instances across three tiers and three AZs, plus room for future growth. Walk through your approach."_
**Model answer:** I'd start by using VLSM to size each tier's subnets according to realistic maximum scale rather than splitting the VPC's CIDR evenly — the load-balancer/gateway tier needs relatively few addresses, while the application compute tier, which will scale elastically, needs a generously sized range. I'd replicate that same tier structure identically across all three target AZs from day one, even if initial capacity only requires two, so that adding the third AZ later is a route-table and resource-placement change rather than a full subnet redesign. I'd also reserve a portion of the VPC's overall CIDR block unallocated up front, specifically to accommodate a future tier or a larger-than-expected application tier without requiring a secondary CIDR block association later. Route tables would be created per-tier-purpose (one shared "public" route table used by all AZ instances of the gateway tier, one shared "private" route table for the app tier routing through NAT, and a maximally restrictive route table for the data tier) rather than one bespoke table per subnet, keeping the design auditable as it scales.
_What the interviewer is probing for:_ The ability to design for scale and future flexibility from the outset — sizing with VLSM deliberately, replicating structure across AZs consistently, and keeping route table management auditable as the number of subnets grows into the hundreds of instances scale.

## 12. Common Misconceptions

1. **"A subnet is 'public' or 'private' because of a setting on the subnet itself."** It's entirely a function of that subnet's route table, specifically its default route's target.
2. **"One subnet per tier is sufficient for high availability."** A subnet lives in exactly one AZ on AWS/Azure; true AZ redundancy requires at least one subnet per tier per AZ.
3. **"GCP subnets need to be duplicated per zone the way AWS/Azure subnets are duplicated per AZ."** GCP subnets are regional and automatically span all zones in that region; the AWS/Azure "one subnet per AZ" pattern doesn't apply the same way.
4. **"Azure subnets with no explicitly attached route table have no internet access."** Azure provides implicit system routes granting default outbound internet access unless an explicit User-Defined Route or NSG overrides it — a subnet's absence of a custom route table doesn't mean it's isolated.

## 13. 🔑 Key Takeaways

- A subnet is a sub-range of a VPC/VNet's CIDR block bound to exactly one Availability Zone (AWS/Azure) or spanning a whole region automatically (GCP).
- "Public" and "private" subnet are informal terms describing route table behavior — specifically the destination of the `0.0.0.0/0` route — not a formal, separately configured subnet property.
- Spreading subnets (and the resources in them) across multiple AZs is the primary mechanism for cloud-native high availability, directly extending the fault-isolation goals introduced generally in [§72](../Part9/Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md).
- Route table changes take effect immediately with no separate confirmation step and deserve the same change-control discipline as security group/firewall rule changes.
- Always verify actual subnet reachability via the route table API, not by trusting subnet names, tags, or documentation.

## 14. Related Concepts & What's Next

This section's route tables reference gateways that [§102](Section-102-Part12-Internet-Gateways-NAT-Gateways-and-Egress-Patterns.md) covers in depth — internet gateways, NAT gateways, and the egress patterns they enable. The subnet-per-AZ redundancy pattern established here is also a direct prerequisite for the multi-VPC and multi-region architectures in [§104](Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md) and [§108](Section-108-Part12-Multi-Region-and-Multi-Cloud-Networking-Considerations.md). Security group and NACL placement at the subnet boundary, covered fully in [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md), is the access-control layer that works alongside — but is distinct from — the routing behavior covered here.

**Next Section:** [§102](Section-102-Part12-Internet-Gateways-NAT-Gateways-and-Egress-Patterns.md) — `Section-102-Part12-Internet-Gateways-NAT-Gateways-and-Egress-Patterns.md`
