# Section 102 (Part 12): Internet Gateways, NAT Gateways, and Egress Patterns

## 1. Definition

**Plain language:** A cloud network needs two distinct kinds of door to the outside internet: one that lets resources be reached *from* the internet (and reach back out with their own public identity), and one that lets resources reach *out* to the internet without ever being reachable from it. Cloud providers implement these as two separate managed components rather than one, so that "can be seen from the internet" and "can reach the internet" are always independent decisions.

**Precise definition:** An **Internet Gateway (IGW)** — called a Virtual Network Gateway/Public IP association on Azure and a default internet route via Cloud NAT's counterpart on GCP — is a horizontally scaled, managed component attached to a VPC/VNet that performs bidirectional NAT between a resource's private IP and an assigned public IP, enabling both inbound and outbound internet connectivity for anything routed to it. A **NAT Gateway** (AWS/Azure naming; **Cloud NAT** on GCP) is a managed component that performs only source NAT ([§20](../Part3/Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md)) for outbound-initiated traffic, translating many private-subnet source addresses to one (or a small pool of) public IP address, while never allowing any inbound connection to be initiated from outside — the cloud-managed realization of the PAT (Port Address Translation) concept from [§20](../Part3/Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md), operated as a fully managed, highly available service rather than a customer-run NAT instance.

> 💡 **Tip:** The distinction to internalize permanently is: **Internet Gateway = two-way door (in and out)**, **NAT Gateway = one-way door (out only)**. Every egress-pattern decision in this section reduces to choosing which of these two doors — or neither — a given subnet's route table points to.

## 2. Why This Matters

- **Choosing the wrong gateway type is a direct, high-severity security mistake.** Routing a subnet meant to hold private data-tier resources to an Internet Gateway instead of a NAT Gateway can make those resources unintentionally reachable from the public internet.
- **NAT Gateway costs are a frequent, underestimated line item in cloud bills** — NAT Gateways bill per hour and per gigabyte processed, and high-throughput workloads routed through them for outbound-only traffic can produce surprisingly large charges compared to running the same traffic through an Internet Gateway (which has no comparable per-GB data-processing fee) when public IP exposure would actually have been acceptable.
- **Every private-subnet workload that needs any outbound internet access at all** — pulling OS package updates, calling a third-party API, sending telemetry — depends on this section's concepts being applied correctly.
- **This is one of the most common real-world troubleshooting categories in cloud networking** — "why can't my private instance reach the internet" or "why is my private instance reachable from the internet" both trace back directly to gateway and route table misconfiguration covered here and in [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md).
- **Certification exams test this distinction heavily** precisely because it's such a common production misconfiguration.

## 3. Prerequisites and Dependencies

This section depends directly on [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)'s route table concept — gateways are meaningless without understanding that it's a subnet's route table entry, not the gateway's mere existence in the VPC/VNet, that determines whether a given subnet actually uses it. It also assumes the NAT/PAT conceptual foundation from [§20](../Part3/Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md) and the private/public IP distinction from [§19](../Part3/Section-19-Part3-Private-vs-Public-IP-Ranges-RFC-1918.md) — a NAT Gateway is, at its core, exactly the PAT mechanism from [§20](../Part3/Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md) operated as a managed cloud service. It is a direct prerequisite for reasoning correctly about the security-group/NACL placement decisions in [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md), since gateway routing and security-group rules together determine actual reachability.

## 4. Architecture / Conceptual Diagram

```text
                                   INTERNET

                       ▲                          ▲
                       │ (in + out)                │ (out only,
                       │                            │  never in)
              ┌────────┴────────┐          ┌────────┴────────┐
              │ Internet Gateway │          │   NAT Gateway    │
              │ (bidirectional   │          │ (source NAT      │
              │  NAT, §20)       │          │  only, §20)      │
              └────────┬────────┘          └────────┬────────┘
                       │                             │
              ┌────────┴────────┐          ┌────────┴────────┐
              │ Public Subnet    │          │ Private Subnet   │
              │ (route: 0/0 ►IGW)│  ◄─────► │ (route: 0/0 ►NAT)│
              │ has public IPs   │  (local  │ no public IPs    │
              └─────────────────┘   route)  └─────────────────┘

   Traffic pattern:
   - Public subnet resource ◄──► Internet directly (both directions)
   - Private subnet resource ──► NAT Gateway ──► Internet Gateway ──► Internet
     (outbound only; internet cannot initiate a connection back in)
```

- The NAT Gateway itself is placed in a **public** subnet (routed to the Internet Gateway) — it needs a public IP of its own to perform the source-NAT translation, even though the resources behind it never get public IPs.
- Traffic from a private subnet always transits **through** the NAT Gateway and then the Internet Gateway — the NAT Gateway does not replace the Internet Gateway, it depends on one already existing in the VPC/VNet.
- On GCP, **Cloud NAT** has no equivalent standalone "gateway resource with its own subnet placement" — it's configured as a regional policy attached directly to a router, a structurally different implementation of the identical outbound-only NAT concept.

## 5. Hands-On

### 5.1 Attaching an Internet Gateway to an AWS VPC

**Purpose:** Show the two-step process — create the gateway, then attach it — that's a common source of "gateway exists but nothing uses it" confusion.

**Syntax:**

```bash
aws ec2 create-internet-gateway
aws ec2 attach-internet-gateway --internet-gateway-id <igw-id> --vpc-id <vpc-id>
```

**Example usage and expected output:**

```bash
$ aws ec2 create-internet-gateway
{"InternetGateway": {"InternetGatewayId": "igw-0a1b2c3d4e5f6a7b8", "Attachments": []}}

$ aws ec2 attach-internet-gateway --internet-gateway-id igw-0a1b2c3d4e5f6a7b8 --vpc-id vpc-0a1b2c3d4e5f6a7b8
```

- Note the empty `Attachments` array immediately after creation — an unattached Internet Gateway does nothing at all; it must be explicitly attached to a VPC, and a subnet's route table must then explicitly route to it (§5.2's counterpart from [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)) before it has any effect.

**Production usage example:** This create-then-attach pattern is standard in every AWS IaC template that provisions a public-facing VPC tier, always paired immediately with a `0.0.0.0/0` route to the new gateway in the intended public subnets' route table.

**Common errors:** Creating and attaching an Internet Gateway but forgetting to add the corresponding route in the target subnet's route table — the gateway exists and is attached, but the subnet remains fully private since nothing routes to it.

### 5.2 Creating an AWS NAT Gateway for Private-Subnet Egress

**Purpose:** Show the managed NAT Gateway creation flow and its dependency on an Elastic IP and a public subnet.

**Syntax:**

```bash
aws ec2 allocate-address --domain vpc
aws ec2 create-nat-gateway --subnet-id <public-subnet-id> --allocation-id <eip-allocation-id>
```

**Example usage and expected output:**

```bash
$ aws ec2 allocate-address --domain vpc
{"AllocationId": "eipalloc-0abc123def456", "PublicIp": "54.210.10.20"}

$ aws ec2 create-nat-gateway --subnet-id subnet-0f1e2d3c4b5a69788 --allocation-id eipalloc-0abc123def456
{
    "NatGateway": {
        "NatGatewayId": "nat-0def4567890abcdef",
        "SubnetId": "subnet-0f1e2d3c4b5a69788",
        "State": "pending"
    }
}
```

- The NAT Gateway is created **in the public subnet** (`subnet-0f1e2d3c4b5a69788`), not in the private subnet it will serve — this is the detail most often missed by engineers new to this pattern.
- The private subnet's own route table then needs a `0.0.0.0/0` route pointing at this `nat-0def...` gateway ID, exactly as shown in [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)'s §5.2.

**Production usage example:** One NAT Gateway per AZ (rather than one shared NAT Gateway for an entire multi-AZ VPC) is the standard production pattern, avoiding a single NAT Gateway becoming a cross-AZ single point of failure and avoiding inter-AZ data transfer charges.

**Common errors:** Sharing a single NAT Gateway across all AZs works functionally but reintroduces a cross-AZ dependency that undermines the AZ-isolation redundancy design from [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md) — if that AZ fails, every other AZ's private subnets lose internet egress too.

### 5.3 Configuring GCP Cloud NAT for Outbound-Only Egress

**Purpose:** Contrast GCP's router-attached Cloud NAT model against AWS/Azure's standalone-gateway-resource model.

**Syntax:**

```bash
gcloud compute routers nats create <nat-name> \
  --router=<router-name> \
  --auto-allocate-nat-external-ips \
  --nat-all-subnet-ip-ranges
```

**Example usage and expected output:**

```bash
$ gcloud compute routers nats create prod-nat --router=prod-router \
    --auto-allocate-nat-external-ips --nat-all-subnet-ip-ranges
Creating NAT [prod-nat] in router [prod-router]...done.
```

- Unlike AWS's per-subnet NAT Gateway placement, `--nat-all-subnet-ip-ranges` applies the NAT policy to every subnet the router serves in one command — reflecting GCP's regional-router-centric model rather than a per-subnet gateway resource model.

**Production usage example:** Cloud NAT is the standard way to give GCP compute instances with no external IP outbound internet access (for package updates, API calls) while keeping them entirely unreachable from inbound internet connections, functionally identical in outcome to an AWS/Azure NAT Gateway despite the different configuration surface.

**Common errors:** Assuming Cloud NAT requires a standalone "gateway resource" the way AWS does — on GCP it's a NAT policy attached to an existing Cloud Router, and looking for a separate gateway object leads to confusion for engineers coming from AWS/Azure.

## 6. Production Usage Notes

- **NAT Gateway (and Cloud NAT) costs scale with data volume processed, not just uptime** — high-throughput outbound workloads (large software updates, data exports) through a NAT Gateway can become a meaningfully large line item, worth monitoring specifically rather than assuming it's a negligible fixed cost.
- **One NAT Gateway per AZ, matched to that AZ's private subnets, is the standard highly-available pattern on AWS**; Azure's equivalent (NAT Gateway resource, or a UDR pointing at a firewall/NVA) and GCP's Cloud NAT (regional by nature) achieve the same outcome with different resource shapes.
- **A resource behind a NAT Gateway has no fixed, individually addressable public IP** — all outbound connections from every private-subnet resource behind it appear to external services as coming from the NAT Gateway's shared public IP(s), which matters for allowlisting scenarios on third-party services.

## 7. Security Considerations

- Placing any workload holding sensitive data behind a NAT Gateway rather than an Internet Gateway is a foundational control — it guarantees no inbound connection can ever be initiated from the public internet to that resource, regardless of any security-group misconfiguration, providing defense in depth alongside [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)'s access controls.
- NAT Gateway/Cloud NAT shared public IPs can be used as an allowlisting anchor for third-party API access — since all outbound traffic from the private subnets behind it shares that IP, a third party can safely allowlist just that one address rather than every private instance's (nonexistent) individual public IP.
- An Internet Gateway attached to a VPC does nothing on its own without a route pointing to it — but once that route exists on a subnet, every resource in it that also has a public IP and permissive security-group rules becomes internet-reachable, making the gateway-plus-route-table-plus-security-group combination the actual unit of security review, not any one piece in isolation.

## 8. Common Troubleshooting Scenarios

| Symptom | Likely Cause | Resolution Path |
| --- | --- | --- |
| Private-subnet instance can't reach the internet at all | No NAT Gateway/Cloud NAT configured, or the private subnet's route table doesn't point to it | Verify the NAT resource exists and the subnet's `0.0.0.0/0` route targets it |
| Instance in a "public" subnet still unreachable from the internet | Instance lacks a public IP, or the Internet Gateway isn't attached/routed to that subnet | Assign a public/Elastic IP and confirm the subnet's route table sends `0.0.0.0/0` to the Internet Gateway |
| NAT Gateway costs unexpectedly high | High-volume outbound data processed through NAT Gateway (per-GB billing) | Audit outbound traffic volume; consider VPC endpoints/PrivateLink ([§105](Section-105-Part12-Private-Connectivity-PrivateLink-Private-Endpoints-VPC-Service-Controls-Conceptual.md)) for traffic to the same provider's services to bypass NAT entirely |
| Third-party service can't allowlist a private workload's traffic | Team attempted to allowlist individual private IPs, which aren't visible externally at all | Allowlist the NAT Gateway/Cloud NAT's shared public IP instead |

## 9. Best Practices

- Always place workloads with no legitimate need for inbound internet reachability behind a NAT Gateway/Cloud NAT rather than an Internet Gateway, even if it would technically "work" either way — minimizing exposure surface is the point, not merely achieving connectivity.
- Provision one NAT Gateway per AZ on AWS to preserve AZ-level fault isolation established in [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md), rather than a single shared NAT Gateway across all AZs.
- Monitor NAT Gateway/Cloud NAT data-processing costs specifically, and consider provider-native private connectivity ([§105](Section-105-Part12-Private-Connectivity-PrivateLink-Private-Endpoints-VPC-Service-Controls-Conceptual.md)) for high-volume traffic destined to the same provider's own managed services, which can bypass NAT egress entirely.

## 10. Common Anti-Patterns / Mistakes

- **Routing a data-tier or otherwise sensitive subnet to an Internet Gateway "just to make internet access work" instead of using a NAT Gateway.** This grants two-way reachability when only one-way egress was ever needed.
- **Sharing a single NAT Gateway across all AZs in a multi-AZ VPC.** This reintroduces a cross-AZ single point of failure that the subnet-per-AZ design in [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md) was meant to eliminate.
- **Ignoring NAT Gateway/Cloud NAT per-GB data processing costs until a cloud bill spikes unexpectedly.** This cost dimension should be part of initial capacity and architecture planning, not discovered reactively.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between an Internet Gateway and a NAT Gateway?"_
**Model answer:** An Internet Gateway allows two-way traffic — resources behind it can both initiate outbound connections and receive inbound connections from the internet, provided they have a public IP. A NAT Gateway only allows outbound-initiated traffic — resources behind it can reach out to the internet, but nothing on the internet can initiate a connection back in, because the NAT Gateway only performs source NAT for traffic that started inside the private network.
_What the interviewer is probing for:_ Basic, correct understanding of directionality — the single most commonly tested distinction in this area.

**🎯 Intermediate:** _"Why does an AWS NAT Gateway need to be placed in a public subnet, if it's meant to serve private subnets?"_
**Model answer:** The NAT Gateway itself needs a public IP (an Elastic IP) to perform the source-NAT translation of outbound traffic from the private subnets it serves, and to get a route to the internet at all it must sit in a subnet whose route table points to an Internet Gateway — i.e., a public subnet. The private subnets it serves route their own outbound traffic *to* the NAT Gateway (via the NAT Gateway's private-side interface), which then forwards it out through the Internet Gateway using its own public IP — the NAT Gateway is effectively the bridge between the two subnet types, not a resident of the private subnet it protects.
_What the interviewer is probing for:_ Understanding the actual traffic path and dependency chain, not just memorizing "NAT Gateway goes in a public subnet" as an arbitrary rule.

**🎯 Senior:** _"A cost review flags that your production VPC's NAT Gateway is one of the largest line items on the AWS bill. How would you investigate and address this?"_
**Model answer:** I'd first check whether the cost is coming from the per-hour charge (unlikely to dominate) or the per-GB data processing charge (the usual culprit), by looking at the NAT Gateway's data-processing metrics in CloudWatch. If it's data volume, I'd identify what's actually generating that outbound traffic — commonly large software/OS updates, data exports to third-party APIs, or unnecessarily verbose logging/telemetry being sent externally. For traffic destined to the same provider's own services (S3, other AWS APIs), I'd evaluate moving that traffic onto a VPC endpoint/PrivateLink connection ([§105](Section-105-Part12-Private-Connectivity-PrivateLink-Private-Endpoints-VPC-Service-Controls-Conceptual.md)), which bypasses the NAT Gateway (and its per-GB charge) entirely for that traffic. For genuinely necessary third-party internet traffic, I'd assess whether the volume itself can be reduced (caching, batching, compression) rather than assuming the NAT Gateway architecture itself needs to change.
_What the interviewer is probing for:_ Practical cost-optimization instincts that connect the NAT Gateway's billing model to concrete architectural levers, including knowing that private connectivity options can eliminate NAT costs for same-provider traffic entirely.

**🎯 Architect:** _"Design the internet connectivity layer for a VPC hosting a three-tier application (web, app, data) across three AZs, balancing security, availability, and cost."_
**Model answer:** The web tier's load balancer subnets would be public, routed to an Internet Gateway, since they need to be reachable from the internet by design. The app and data tiers would be entirely private, with no route to the Internet Gateway at all. For the app tier's legitimate outbound needs (calling third-party APIs, pulling packages), I'd provision one NAT Gateway per AZ rather than a single shared one, preserving AZ-level fault isolation and avoiding cross-AZ data transfer charges, even though this means paying for three NAT Gateways instead of one. The data tier, if it needs no internet egress at all, would have no NAT route configured — the most restrictive and cheapest option, and the correct default unless a specific requirement (e.g., calling a managed backup service) proves otherwise. For any traffic between the app tier and the same provider's own managed services (object storage, managed databases), I'd use VPC endpoints/PrivateLink ([§105](Section-105-Part12-Private-Connectivity-PrivateLink-Private-Endpoints-VPC-Service-Controls-Conceptual.md)) instead of routing that traffic through the NAT Gateway, both for security (traffic never traverses the public internet) and for cost (avoiding NAT Gateway data-processing charges for that portion of traffic).
_What the interviewer is probing for:_ The ability to synthesize gateway choice, AZ redundancy, and cost awareness into one coherent design, and specifically the instinct to question whether the data tier needs any internet egress at all rather than defaulting to "give everything a NAT route just in case."

## 12. Common Misconceptions

1. **"A NAT Gateway and an Internet Gateway are basically the same thing with different names."** They differ fundamentally in directionality — an Internet Gateway is bidirectional, a NAT Gateway is outbound-only by design.
2. **"Attaching an Internet Gateway to a VPC automatically makes its subnets public."** Nothing changes until a subnet's route table is explicitly updated to route `0.0.0.0/0` to that gateway, per [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md).
3. **"Resources behind a NAT Gateway each get their own effective public identity for allowlisting purposes."** They all share the NAT Gateway's public IP(s) as far as any external service observing the traffic is concerned.
4. **"NAT Gateway costs are negligible compared to compute costs."** The per-GB data processing charge can become a significant, easily overlooked line item for high-throughput outbound workloads.

## 13. 🔑 Key Takeaways

- An Internet Gateway provides bidirectional internet connectivity; a NAT Gateway (Cloud NAT on GCP) provides outbound-only connectivity and never allows an internet-initiated inbound connection.
- A NAT Gateway is the managed cloud realization of the PAT concept from [§20](../Part3/Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md), operated as a highly available service rather than a customer-run instance.
- On AWS, a NAT Gateway is placed in a public subnet and serves private subnets whose route tables point to it — it doesn't reside inside the private subnet it protects.
- Gateway existence alone does nothing; a subnet's route table ([§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)) must explicitly route to the gateway for it to affect that subnet's traffic.
- NAT Gateway/Cloud NAT costs scale with data volume processed and deserve explicit cost monitoring, with provider-native private connectivity ([§105](Section-105-Part12-Private-Connectivity-PrivateLink-Private-Endpoints-VPC-Service-Controls-Conceptual.md)) as a common cost- and security-improving alternative for same-provider traffic.

## 14. Related Concepts & What's Next

This section depends entirely on [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)'s route table mechanism to actually take effect, and its egress patterns connect directly to [§105](Section-105-Part12-Private-Connectivity-PrivateLink-Private-Endpoints-VPC-Service-Controls-Conceptual.md), where traffic to the same provider's own services can bypass NAT egress entirely through a private connectivity mechanism. [§106](Section-106-Part12-Hybrid-Connectivity-Direct-Connect-ExpressRoute-Cloud-Interconnect-Conceptual.md) covers a third connectivity category — dedicated private links back to on-premises infrastructure — distinct from both the internet-facing gateways covered here and the peering connections covered next in [§103](Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md).

**Next Section:** [§103](Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md) — `Section-103-Part12-VPC-VNet-Peering-and-Transitive-Routing-Limitations.md`
