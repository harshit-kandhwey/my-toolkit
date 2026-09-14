# Section 100 (Part 12): Cloud Virtual Networking Fundamentals: VPC/VNet Concepts Across Providers

## 1. Definition

**Plain language:** A cloud virtual network is a private, logically isolated slice of a provider's physical network that a customer controls — their own address space, their own subnets, their own routing and connectivity rules — running on shared physical infrastructure the customer never sees. Every major provider gives customers this same basic building block; only the name and some implementation details differ.

**Precise definition:** A **Virtual Private Cloud (VPC)** on AWS and GCP, or a **Virtual Network (VNet)** on Azure, is a software-defined, logically isolated network within a cloud provider's infrastructure, to which the customer assigns a private IP address range (in CIDR notation, per [§16](../Part3/Section-16-Part3-Subnet-Masks-and-CIDR-Notation.md)), within which the customer creates subnets ([§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)), attaches gateways for external connectivity ([§102](Section-102-Part12-Internet-Gateways-NAT-Gateways-and-Egress-Patterns.md)), and applies routing and security controls independent of any other customer's network on the same physical hardware. It is the cloud-native realization of the same "isolated logical network on shared infrastructure" idea that overlay networking and SDN ([§43](../Part5/Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md)) introduced conceptually — a VPC/VNet is what that idea looks like as a fully managed, API-driven product.

> 💡 **Tip:** Every remaining section in this Part builds on top of the VPC/VNet concept introduced here. If a term like "route table," "subnet," or "peering connection" doesn't yet have a home in your mental model, that's expected — this section only establishes the container; the pieces inside it are covered [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md) onward.

## 2. Why This Matters

- **The VPC/VNet is the foundational unit of nearly every cloud architecture diagram** — before a single server or database is provisioned, an infrastructure engineer must already understand what network it lives in, because almost every other cloud resource (compute, managed databases, load balancers from [§80](../Part9/Section-80-Part9-Cloud-Load-Balancer-Types-ALB-NLB-Azure-LB-App-Gateway-GCP-LB-Conceptual.md)) is deployed *into* one.
- **Address planning mistakes made at VPC creation time are expensive to fix later.** Choosing a CIDR block that's too small, or one that overlaps with an on-premises network or another VPC that will eventually need peering ([§103](Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md)), often forces a full network recreation months into a project.
- **Cloud certifications treat VPC/VNet fluency as baseline knowledge**, not an advanced topic — every associate-level AWS, Azure, and GCP certification assumes comfort with creating and reasoning about virtual networks.
- **Cost and security both trace back to network design decisions made here.** Whether a workload is reachable from the public internet, how it reaches other services, and how traffic is billed (in-region vs. cross-region vs. egress) are all downstream of the VPC/VNet topology chosen at the start.
- **Multi-cloud and cloud-migration work requires translating this exact concept across provider vocabularies fluently** — a network engineer moving between AWS and Azure job requirements needs to recognize "VPC" and "VNet" as the same idea instantly.

## 3. Prerequisites and Dependencies

This section assumes full comfort with CIDR notation and subnet masking ([§16](../Part3/Section-16-Part3-Subnet-Masks-and-CIDR-Notation.md)), private IP address ranges under RFC 1918 ([§19](../Part3/Section-19-Part3-Private-vs-Public-IP-Ranges-RFC-1918.md)), and basic routing concepts ([§25](../Part4/Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md), [§26](../Part4/Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md)) — a VPC/VNet is fundamentally an address space plus a routing domain, and none of its cloud-specific behavior makes sense without those foundations already in place. It also benefits from the SDN/overlay networking conceptual introduction in [§43](../Part5/Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md), since a VPC/VNet is, under the hood, an SDN-managed overlay on the provider's physical network fabric. Every other section in this Part ([§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)–[§109](Section-109-Part12-Cross-Reference-Where-AWS-Azure-GCP-Specific-Networking-Continues-in-This-Repo.md)) depends directly on the container concept established here; this is the entry point for all cloud networking content in this roadmap.

## 4. Architecture / Conceptual Diagram

```text
                         PHYSICAL CLOUD PROVIDER INFRASTRUCTURE
                         (shared across all customers, invisible to any one of them)

   ┌───────────────────────────────┐        ┌───────────────────────────────┐
   │   Customer A's VPC/VNet       │        │   Customer B's VPC/VNet       │
   │   CIDR: 10.0.0.0/16           │        │   CIDR: 10.0.0.0/16           │
   │                                │        │                                │
   │   ┌────────────┐ ┌───────────┐│        │   ┌────────────┐ ┌───────────┐│
   │   │ Subnet A   │ │ Subnet B  ││        │   │ Subnet A   │ │ Subnet B  ││
   │   │(§101)      │ │(§101)     ││        │   │            │ │           ││
   │   └────────────┘ └───────────┘│        │   └────────────┘ └───────────┘│
   │                                │        │                                │
   │   Route Table (§101) ◄──────► │        │   Route Table (§101) ◄──────► │
   │   Gateways (§102)             │        │   Gateways (§102)             │
   └───────────────────────────────┘        └───────────────────────────────┘
        Logically isolated                       Logically isolated
        (no traffic crosses without             (no traffic crosses without
         explicit peering, §103)                 explicit peering, §103)

   AWS name:   Virtual Private Cloud (VPC)
   Azure name: Virtual Network (VNet)
   GCP name:   VPC Network (can span all regions in one network — see note below)
```

- Both Customer A's and Customer B's networks reuse the identical `10.0.0.0/16` CIDR block with zero conflict — logical isolation means overlapping address space between two different customers' VPCs/VNets is completely normal and expected, since nothing routes between them by default.
- **AWS and Azure VPCs/VNets are regional resources** — a VPC created in `us-east-1` or a VNet created in `East US` exists only in that region; multi-region designs require either multiple VPCs/VNets connected via peering ([§103](Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md)) or a transit architecture ([§104](Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md)).
- **GCP's VPC Network is a global resource by default** — a single GCP VPC network can contain subnets in many regions simultaneously, a genuine structural difference from AWS/Azure that changes how multi-region designs are approached on GCP, similar in spirit to GCP's global load balancer product discussed in [§80](../Part9/Section-80-Part9-Cloud-Load-Balancer-Types-ALB-NLB-Azure-LB-App-Gateway-GCP-LB-Conceptual.md).

## 5. Hands-On

### 5.1 Creating an AWS VPC

**Purpose:** Show the minimal API call that creates the foundational network container everything else in this Part attaches to.

**Syntax:**

```bash
aws ec2 create-vpc \
  --cidr-block <cidr-block> \
  --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=<name>}]'
```

**Example usage and expected output:**

```bash
$ aws ec2 create-vpc --cidr-block 10.0.0.0/16 \
    --tag-specifications 'ResourceType=vpc,Tags=[{Key=Name,Value=prod-vpc}]'
{
    "Vpc": {
        "VpcId": "vpc-0a1b2c3d4e5f6a7b8",
        "CidrBlock": "10.0.0.0/16",
        "State": "pending",
        "InstanceTenancy": "default"
    }
}
```

- `--cidr-block 10.0.0.0/16` reserves 65,536 addresses for this VPC — sizing this block correctly up front, per [§17](../Part3/Section-17-Part3-Subnetting-Fundamentals-Borrowing-Bits-Calculating-Ranges.md)'s subnetting math, is the single most consequential decision made at VPC creation time.

**Production usage example:** Nearly every AWS Infrastructure-as-Code template (Terraform, CloudFormation, CDK) begins with exactly this resource — the VPC is the root node of the dependency graph for an AWS network stack.

**Common errors:** Choosing a CIDR block that later overlaps with an on-premises network or a VPC that needs peering ([§103](Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md)) forces either a full VPC recreation or complex NAT-based workarounds — this is the most common irreversible mistake made at this step.

### 5.2 Creating an Azure Virtual Network

**Purpose:** Show the equivalent Azure construct and its slightly different address-space syntax.

**Syntax:**

```bash
az network vnet create \
  --name <vnet-name> \
  --resource-group <resource-group> \
  --address-prefixes <cidr-block> \
  --location <region>
```

**Example usage and expected output:**

```bash
$ az network vnet create --name prod-vnet --resource-group prod-rg \
    --address-prefixes 10.1.0.0/16 --location eastus
{
  "newVNet": {
    "name": "prod-vnet",
    "addressSpace": {"addressPrefixes": ["10.1.0.0/16"]},
    "provisioningState": "Succeeded",
    "resourceGroup": "prod-rg"
  }
}
```

- Azure's `--address-prefixes` accepts a **list**, not a single value — an Azure VNet can be created with multiple, non-contiguous CIDR blocks from the start, a flexibility AWS's single `--cidr-block` argument on `create-vpc` doesn't offer at creation time (AWS requires a separate `associate-vpc-cidr-block` call to add a second range afterward).

**Production usage example:** Terraform's `azurerm_virtual_network` resource maps directly onto this command and is the standard root resource for Azure network IaC, mirroring the AWS VPC's role in §5.1.

**Common errors:** Forgetting `--resource-group` (or pointing it at the wrong one) creates the VNet in an unexpected resource group, which then complicates later cleanup and role-based access scoping — a very common early-Azure-adoption mistake since resource groups have no AWS equivalent to build intuition from.

### 5.3 Creating a GCP VPC Network

**Purpose:** Contrast GCP's global-by-default network model directly against AWS/Azure's regional model from §5.1/§5.2.

**Syntax:**

```bash
gcloud compute networks create <network-name> \
  --subnet-mode=custom
```

**Example usage and expected output:**

```bash
$ gcloud compute networks create prod-network --subnet-mode=custom
Created [https://www.googleapis.com/compute/v1/projects/my-project/global/networks/prod-network].

NAME            SUBNET_MODE  BGP_ROUTING_MODE  IPV4_RANGE  GATEWAY_IPV4
prod-network    CUSTOM       REGIONAL
```

- Note there is **no CIDR block on the network itself** — the `NAME` in the URL is under `global/networks/`, confirming the network object itself is global; IP address ranges are only assigned per-subnet inside it, covered in [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md).
- `--subnet-mode=custom` is the recommended production choice — it prevents GCP from auto-creating a subnet in every region, which the default `auto` mode does and which is rarely what a deliberately designed network wants.

**Production usage example:** `--subnet-mode=custom` paired with explicitly created regional subnets ([§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)) is the standard production pattern on GCP, giving the same deliberate control over address allocation that AWS and Azure require by default.

**Common errors:** Using the default `auto` subnet mode in a production project results in subnets silently created in every GCP region with a fixed `/20` block each — an unpleasant surprise for teams expecting AWS/Azure's "nothing exists until you create it" behavior.

## 6. Production Usage Notes

- **CIDR block sizing should always assume future growth**, not just current needs — resizing later, especially once peering connections ([§103](Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md)) or hybrid connectivity ([§106](Section-106-Part12-Hybrid-Connectivity-Direct-Connect-ExpressRoute-Cloud-Interconnect-Conceptual.md)) exist, ranges from disruptive to effectively impossible without downtime.
- **Address planning across an organization should be centralized**, not left to individual teams creating VPCs/VNets independently — uncoordinated CIDR choices are the single most common blocker to peering or hub-and-spoke consolidation ([§104](Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md)) discovered later.
- **GCP's global VPC network model changes multi-region design conversations** — a team moving from AWS/Azure to GCP should not assume they need one VPC per region; a single custom-mode VPC with regional subnets is usually the right GCP-native pattern.

## 7. Security Considerations

- Logical isolation between VPCs/VNets is the default and starting security boundary — no traffic crosses between two separate VPCs/VNets unless a customer explicitly configures peering ([§103](Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md)), a gateway, or hybrid connectivity ([§106](Section-106-Part12-Hybrid-Connectivity-Direct-Connect-ExpressRoute-Cloud-Interconnect-Conceptual.md)) — this default-deny-between-networks posture should never be casually opened.
- Choosing private, non-publicly-routable CIDR ranges (RFC 1918, [§19](../Part3/Section-19-Part3-Private-vs-Public-IP-Ranges-RFC-1918.md)) for the VPC/VNet is standard practice and avoids ever conflating internal addressing with public internet addressing.
- Segregating workloads of different sensitivity levels into separate VPCs/VNets (or at minimum separate subnets, [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)) rather than one flat network for an entire organization limits blast radius if any single workload is compromised.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely Cause | Resolution Path |
| --- | --- | --- |
| Two VPCs/VNets can't be peered | Their CIDR blocks overlap | Recreate one network with a non-overlapping range, or use a NAT-based workaround if recreation isn't feasible |
| Resources created in the wrong network context | Wrong VPC/VNet (or, on Azure, wrong resource group) specified at resource creation time | Verify the target network ID/name explicitly in every provisioning command or IaC module rather than relying on defaults |
| GCP subnets unexpectedly exist in every region | Network created in `auto` subnet mode instead of `custom` | Recreate the network with `--subnet-mode=custom` and provision only the intended regional subnets |
| Running out of usable IP addresses in a VPC/VNet | Initial CIDR block sized too small for current workload count | Add a secondary, non-overlapping CIDR block (AWS `associate-vpc-cidr-block`, Azure additional `--address-prefixes`) or plan a migration to a larger network |

## 9. Best Practices

- Reserve CIDR blocks centrally across an organization before any team creates a VPC/VNet, treating IP address space as shared, finite infrastructure rather than a per-team decision.
- Default to private RFC 1918 address ranges ([§19](../Part3/Section-19-Part3-Private-vs-Public-IP-Ranges-RFC-1918.md)) and size blocks generously — a `/16` per VPC/VNet is a common, comfortable starting point that leaves room for the subnetting done in [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md).
- On GCP, use `--subnet-mode=custom` for any production network and explicitly provision only the regional subnets actually needed.

## 10. Common Anti-Patterns / Mistakes

- **Treating VPC/VNet creation as an afterthought rather than a deliberate, organization-wide address-planning exercise.** This is the single most common source of downstream peering and hybrid-connectivity pain covered later in this Part.
- **Creating one enormous flat VPC/VNet for an entire organization with no subnet-level segmentation.** This forfeits the isolation benefits [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md) and [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) are designed to provide.
- **Assuming GCP's VPC model works exactly like AWS's or Azure's regional model.** Its global-by-default network object is a genuine structural difference, not just a naming difference.

## 11. Interview Questions

**🎯 Beginner:** _"What is a VPC, and how does it relate to a VNet?"_
**Model answer:** A VPC (AWS/GCP term) and a VNet (Azure term) are the same underlying concept — a logically isolated, private virtual network within a cloud provider's infrastructure, where the customer defines their own IP address range and controls routing and connectivity independent of any other customer sharing the same physical hardware. It's the foundational container almost every other cloud resource is deployed into.
_What the interviewer is probing for:_ Basic fluency translating cloud provider terminology onto the same underlying concept, rather than treating each provider's product as unrelated.

**🎯 Intermediate:** _"Why is choosing the CIDR block for a new VPC one of the most consequential decisions in cloud network design?"_
**Model answer:** The CIDR block determines the total address space available for every subnet, resource, and future subdivision inside that network — sizing it too small forces a painful expansion or migration later, and choosing a range that overlaps with an on-premises network or another VPC that will eventually need peering ([§103](Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md)) can make that future connectivity impossible without recreating the network. Because changing a VPC's primary CIDR block after the fact is disruptive or, in some respects, impossible, getting the address plan right at creation time avoids compounding problems downstream.
_What the interviewer is probing for:_ Understanding that address planning is a strategic decision with long-lived consequences, not a one-time technical detail.

**🎯 Senior:** _"A team tells you their AWS VPC and their GCP VPC 'work basically the same way.' Where would you push back?"_
**Model answer:** The core isolation and CIDR-based addressing concept is genuinely the same, but the structural model differs in an important way: an AWS VPC is a regional resource — it exists in exactly one region, and multi-region designs require multiple VPCs connected via peering or a transit architecture. A GCP VPC network, by contrast, is global by default and can contain subnets spanning many regions within a single network object, with regional scoping only applied at the subnet level. That difference changes how a team should approach multi-region architecture on GCP versus AWS — treating them as identical risks either over-provisioning separate networks on GCP unnecessarily, or under-provisioning connectivity layers on AWS assuming global reach that doesn't exist by default.
_What the interviewer is probing for:_ Whether the candidate knows a real structural difference between providers rather than assuming naming parity implies functional parity everywhere.

**🎯 Architect:** _"You're designing address space allocation for an organization that will eventually run dozens of VPCs/VNets across AWS and Azure, some of which will need to peer with each other and with an on-premises network. How do you approach this?"_
**Model answer:** I'd treat IP address space as a centrally governed, finite organizational resource from day one rather than letting individual teams pick ranges independently. I'd carve out a non-overlapping CIDR super-block for the whole organization, then sub-allocate distinct, non-overlapping ranges to each VPC/VNet from that super-block — including the on-premises network's existing range as one reserved segment that nothing else may reuse. This guarantees that any future peering ([§103](Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md)) or hybrid connectivity ([§106](Section-106-Part12-Hybrid-Connectivity-Direct-Connect-ExpressRoute-Cloud-Interconnect-Conceptual.md)) request is achievable without a network recreation, since the single most common reason peering fails outright is an overlapping CIDR block discovered only after both networks already exist with production workloads in them.
_What the interviewer is probing for:_ Strategic, organization-wide thinking about address planning as governance, not just correct syntax for creating a single network.

## 12. Common Misconceptions

1. **"VPC and VNet are different technologies with different capabilities."** They are the same underlying concept under different provider branding — a logically isolated, customer-controlled virtual network.
2. **"A cloud virtual network's CIDR block can be freely resized later with no impact."** Shrinking or replacing a primary CIDR block is highly disruptive; even adding a secondary block has constraints around what it can overlap with.
3. **"All three providers' virtual network objects work identically in scope."** AWS and Azure's VPC/VNet are regional resources; GCP's VPC network is global by default, spanning subnets across regions within one network object.
4. **"Two VPCs/VNets are automatically reachable from each other since they're both 'in the cloud.'** Logical isolation is the default; explicit peering, gateways, or hybrid connectivity are required for any cross-network traffic.

## 13. 🔑 Key Takeaways

- A VPC (AWS/GCP) and a VNet (Azure) are the same concept: a private, logically isolated, customer-controlled virtual network built on shared physical cloud infrastructure.
- Every VPC/VNet begins with a CIDR block ([§16](../Part3/Section-16-Part3-Subnet-Masks-and-CIDR-Notation.md)) chosen from private address space ([§19](../Part3/Section-19-Part3-Private-vs-Public-IP-Ranges-RFC-1918.md)), and that choice has long-lived consequences for future peering and connectivity.
- AWS and Azure VPCs/VNets are regional resources; GCP's VPC network is global by default, a genuine structural difference worth knowing precisely.
- Logical isolation between virtual networks is the default security posture — nothing crosses between two separate networks without explicit configuration.
- Everything else in this Part — subnets, gateways, peering, hub-and-spoke, private connectivity, hybrid connectivity, DNS, and multi-region design — is built on top of the container concept introduced here.

## 14. Related Concepts & What's Next

This section is the foundation for the entire Part: [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md) subdivides the VPC/VNet into subnets and introduces route tables and availability zones; [§102](Section-102-Part12-Internet-Gateways-NAT-Gateways-and-Egress-Patterns.md) covers how a VPC/VNet reaches (and is reached from) the public internet; and [§103](Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md) covers connecting two or more VPCs/VNets together, the first place the CIDR planning discipline emphasized here pays off directly.

**Next Section:** [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md) — `Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md`
