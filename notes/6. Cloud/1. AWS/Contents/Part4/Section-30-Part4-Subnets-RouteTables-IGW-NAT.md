# Part 4 - Section 2 - Subnets, Route Tables & Internet Connectivity (IGW/NAT)

AWS Zero-to-Enterprise Knowledge Base - Part 4: Networking & Content Delivery

---

## 1. Definition

Plain-language: A subnet is a slice of your VPC's address range, tied to one Availability Zone. A route table is the traffic director for a subnet. Internet Gateways and NAT Gateways are the two different doors to the internet - one for resources that should be directly reachable, one for resources that should only reach out.

Precise: A subnet is an AZ-scoped subdivision of a VPC's CIDR block. A route table is a set of routes determining where traffic is directed based on destination IP. An Internet Gateway (IGW) provides bidirectional internet connectivity; a NAT Gateway provides outbound-only internet access for resources that shouldn't be directly reachable.

---

## 2. Subnets - Carving Up the VPC

### 2.1 Subnet CIDR Blocks

- Each subnet has its own CIDR block, a subset of the VPC's CIDR, non-overlapping with other subnets in the same VPC.
- AWS reserves 5 IP addresses per subnet (first 4, last 1) - a /24 subnet (256 addresses) has only 251 usable, a practical sizing detail.

### 2.2 Subnets Are AZ-Specific

- A subnet exists within exactly one AZ, cannot span multiple AZs - this is why HA architectures require multiple subnets, one per AZ.

### 2.3 Public vs Private Subnets - Defined by Routing, Not Labeling

- Most important concept in this section: a subnet is NOT inherently public or private as a fixed property - it's "public" if its route table has a route to an Internet Gateway, "private" if it doesn't. Entirely a function of the route table.
- A subnet with instances having public IPs but no IGW route is still effectively unreachable from the internet.

---

## 3. Route Tables - The Traffic Director

### 3.1 Structure

- Contains routes: destination CIDR + target (IGW, NAT Gateway, peering connection, Transit Gateway attachment, or "local" for traffic staying in the VPC).
- The local route is automatic and non-removable, routing VPC-CIDR-destined traffic within the VPC - what lets different subnets of the same VPC reach each other by default.

### 3.2 Main Route Table vs Custom Route Tables

- Every VPC has a main route table, auto-associated with subnets not explicitly assigned elsewhere.
- Custom route tables should be created and associated per-subnet for real architectures - this is how public/private separation is actually implemented.
- Each subnet has exactly one route table association at a time; one route table can serve multiple subnets.

### 3.3 Longest Prefix Match

- When multiple routes could match, the most specific (longest prefix) route wins - e.g., a /24 route beats a /16 route for a destination within both.

---

## 4. Internet Gateway (IGW)

### 4.1 Definition

A horizontally scaled, highly available VPC component enabling communication between VPC resources and the internet - performs NAT for instances with public IPs and serves as the target for internet-bound routes.

### 4.2 Three Requirements for a "Public" Subnet

All three must be true:

1. VPC has an IGW attached.
2. Subnet's route table has a route to that IGW (typically 0.0.0.0/0 -> IGW).
3. The specific instance has a public IP (or Elastic IP) assigned.

Key idea: missing any one condition means the instance isn't actually internet-reachable - this three-part checklist is the correct systematic troubleshooting approach.

---

## 5. NAT Gateway / NAT Instance

### 5.1 The Problem NAT Solves

- Private-subnet resources (no IGW route) have no direct internet access - appropriate for databases/internal tiers - but often still need outbound access (patches, external APIs) without being inbound-reachable.
- NAT allows outbound-initiated traffic to reach the internet and receive responses, while blocking unsolicited inbound connections - a fundamentally asymmetric gateway.

### 5.2 NAT Gateway (Managed, Recommended)

- AWS-managed, highly available within a single AZ, auto-scales bandwidth.
- Deployed in a PUBLIC subnet (needs internet access itself); private subnets route internet-bound traffic TO the NAT Gateway, not directly to the IGW.
- Scoped to a single AZ - best practice is one NAT Gateway per AZ, avoiding cross-AZ dependency and data transfer cost.

### 5.3 NAT Instance (Legacy, Self-Managed)

- An EC2 instance configured for NAT - older approach requiring you to patch and manage its own HA (single point of failure unless self-built redundancy).
- AWS guidance favors NAT Gateway for new architectures; NAT Instances remain in legacy environments or edge cases needing capabilities NAT Gateway lacks.

### 5.4 NAT Gateway Cost Model

- Hourly charge PLUS per-GB data processing charge - a significant cost line item for high outbound-traffic architectures. VPC Endpoints (Section 9) can avoid this for AWS-service-bound traffic specifically.

---

---

## 5a. IPv6 Routing & Egress-Only Internet Gateway (EIGW)

### 5a.1 Why IPv6 Routing Is a Different Problem Than IPv4

- Every IPv6 address assigned in a VPC is globally unique and publicly routable by design - there is no private/public address distinction like IPv4's RFC 1918 ranges. Whether an IPv6-enabled resource is actually internet-reachable is therefore determined entirely by routing and security-group/NACL configuration, never by the address itself.
- A VPC's IPv6 CIDR is a /56 block (Amazon-provided or, via BYOIP, customer-owned); each subnet gets a fixed /64 - unlike IPv4, subnet IPv6 prefix length isn't a design choice, it's a hard constraint.

### 5a.2 Egress-Only Internet Gateway (EIGW) - the IPv6 Analog to NAT Gateway

- An EIGW is the IPv6-specific component that lets subnet resources initiate outbound IPv6 connections while blocking unsolicited inbound connections from the internet - functionally similar to what a NAT Gateway does for IPv4, but architecturally different: an EIGW does NOT perform address translation (IPv6 addresses are already globally unique), it purely enforces connection directionality.
- Route table pattern: `::/0 -> eigw-id` (instead of `::/0 -> igw-id`, which would make the subnet bidirectionally reachable, same as attaching an IGW route would for IPv4).

```bash
# Create an egress-only internet gateway
aws ec2 create-egress-only-internet-gateway --vpc-id vpc-0123456789abcdef0

# Route IPv6 default traffic through it for a "private" route table
aws ec2 create-route \
  --route-table-id rtb-0123456789abcdef0 \
  --destination-ipv6-cidr-block ::/0 \
  --egress-only-internet-gateway-id eigw-0123456789abcdef0
```

Interview tip: for IPv4, "public vs private subnet" is an addressing-plus-NAT question. For IPv6 it's purely a routing-target question - IGW target means bidirectional reachability, EIGW target means outbound-only. This is the single most commonly missed distinction when a team that has correctly separated public/private IPv4 route tables adds IPv6 without realizing the IPv6 default route needs a different target to preserve the same "private" intent.

### 5a.3 Dual-Stack Operational Considerations

- Security groups and NACLs evaluate IPv4 and IPv6 rules independently - an IPv4-only inbound rule does not cover IPv6 traffic on the same port. Every IPv4 rule reviewed for correctness needs its own explicit IPv6 review; it's never inherited automatically.
- Dual-stack subnets typically need both an IPv4 default route (to an IGW or NAT Gateway) and an IPv6 default route (to an IGW or EIGW) in the same route table - a common production incident pattern is a correctly locked-down IPv4 posture next to an unreviewed (and therefore too permissive, or simply missing) IPv6 posture.
- VPC Flow Logs capture IPv6 traffic in the same log format as IPv4 (source/destination fields simply contain IPv6 addresses instead of dotted-quad IPv4), so existing flow-log-based troubleshooting extends to IPv6 without new tooling - but custom parsing logic written assuming IPv4 address format needs updating.

### 5a.4 Troubleshooting

| Symptom                                                                   | Cause                                                                   | Fix                                                                                                                    |
| ------------------------------------------------------------------------- | ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| IPv6 resources in a "private" subnet are unexpectedly internet-reachable  | Route table's `::/0` route points at a real IGW instead of an EIGW      | Replace the IGW-targeted IPv6 default route with an EIGW-targeted one                                                  |
| IPv6 works over some paths but not others in a dual-stack subnet          | IPv4 and IPv6 security group/NACL rules are out of sync                 | Explicitly review and add matching IPv6 rules; never assume IPv4 rules cover IPv6                                      |
| Resources have valid IPv6 addresses but IPv6 traffic never actually flows | Application/load balancer/health checks not configured dual-stack aware | Verify DNS (AAAA records), load balancer listener config, and health checks are dual-stack, not just the network layer |

### 5a.5 Key Takeaways

1. IPv6 addresses are globally routable by default - "private" is entirely a routing/security-control statement, never an addressing property, unlike IPv4.
2. EIGW is the IPv6-specific outbound-only mechanism, replacing the NAT Gateway pattern for IPv6 traffic - route `::/0` to an EIGW, not an IGW, to preserve "private subnet" intent.
3. Security groups/NACLs evaluate IPv4 and IPv6 independently - dual-stack environments require an explicit, separate IPv6 review of every rule, not an assumption of parity.

---

## 6. Complete Public/Private Subnet Architecture

A VPC spans two AZs, each with:

- Public subnet: route table has local + 0.0.0.0/0 -> IGW. Contains NAT Gateway, ALB, bastion.
- Private subnet: route table has local + 0.0.0.0/0 -> NAT Gateway (in that AZ's public subnet). Contains EC2 app instances, RDS database.

Public subnet contents typically: load balancers, NAT Gateways, bastion hosts.
Private subnet contents typically: application servers, databases - never directly internet-reachable, outbound only via that AZ's NAT Gateway.

This is the exact mechanics behind Part 3 Section 6's "multi-tier load balancing" pattern preview.

---

## 7. Subnet Sizing and Planning

- Size for maximum expected resources (remembering the 5 reserved addresses per subnet) - a /24's 251 usable addresses can be consumed faster than expected by an ASG's max size or many Lambda-in-VPC ENIs.
- Common pattern: larger subnets for private tiers (where scaling happens), smaller subnets for public tiers (load balancers, NAT Gateways, few bastion hosts).

---

## 8. Production & Enterprise Usage

- One NAT Gateway per AZ is standard for genuine multi-AZ resilience, despite added cost - an availability-over-cost trade-off.
- VPC design as IaC modules typically parameterize this exact pattern - N public/private subnet pairs across N AZs with correct route tables and per-AZ NAT Gateways.
- Bastion hosts increasingly replaced by Systems Manager Session Manager - administrative access without any inbound SSH port open at all, a stronger security posture.

---

## 9. Security Considerations

- Private subnets are a genuine security control, not just organizational labeling - removing direct-internet-exposure risk independent of security group rules (defense in depth at the routing layer).
- NAT Gateway's asymmetric outbound-only nature is itself a security property.
- Bastion hosts, if used, are a concentrated risk point - a single internet-facing SSH target, which is why Session Manager is increasingly preferred.

---

## 10. Performance Considerations

- NAT Gateway bandwidth auto-scales up to a high ceiling, but extreme-throughput workloads should be aware it exists.
- Cross-AZ NAT Gateway sharing introduces both cost and a single point of failure - double reason to prefer per-AZ NAT Gateways.

---

## 11. Troubleshooting

| Symptom                                                           | Cause                                                                           | Fix                                                                                    |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- |
| Instance has public IP but unreachable from internet              | Missing one of the three public requirements, often missing IGW route           | Check all three: IGW attached, route table has IGW route, instance has public IP       |
| Private instance can't reach internet for updates                 | No NAT Gateway, or private subnet route table doesn't route to it               | Verify NAT Gateway exists (public subnet) and route table has 0.0.0.0/0 -> NAT Gateway |
| One AZ's private resources lose outbound access, others fine      | That AZ's NAT Gateway failed, no per-AZ redundancy                              | Deploy NAT Gateway per AZ instead of sharing                                           |
| Resources in different subnets of same VPC can't reach each other | Unexpected security group/NACL blocking it (local route should work by default) | Verify local route exists; check security groups/NACLs (Section 3)                     |

---

## 12. Best Practices & Anti-Patterns

Best practices: use route tables, not labels, to reason about public/private; deploy one NAT Gateway per AZ; size subnets generously accounting for scaling maximums; prefer Session Manager over bastion hosts; codify the pattern as an IaC module.

Anti-patterns: assuming "private" without checking the route table; sharing one NAT Gateway across AZs to save cost; under-sizing subnets causing IP exhaustion during scaling; broad inbound SSH on bastion hosts from 0.0.0.0/0.

---

## 13. Common Misconceptions

- "A subnet is public/private based on a setting at creation." False - determined entirely by the route table's IGW route.
- "A public IP alone makes an instance internet-reachable." False - needs all three conditions (IGW attached, route, public IP).
- "NAT Gateways allow both inbound and outbound like a normal connection." False - asymmetric, outbound-initiated only.
- "One NAT Gateway is sufficient for a multi-AZ VPC." Functionally true but a poor practice - creates cross-AZ SPOF.

---

## 14. Interview Questions (with model answers)

Beginner - What determines whether a subnet is public or private? Entirely the associated route table - specifically whether it routes 0.0.0.0/0 to an Internet Gateway. Not a label; a subnet with public IPs but no IGW route is still unreachable.

Beginner - What does a NAT Gateway do, and why would a private subnet need one? Lets private-subnet resources initiate outbound internet connections (patches, external APIs) while blocking inbound-initiated connections. Sits in a public subnet itself (needs internet access); the private subnet's route table sends internet-bound traffic to the NAT Gateway instead of an IGW.

Intermediate - Why one NAT Gateway per AZ rather than shared? A NAT Gateway is scoped to one AZ. Sharing across AZs creates a cross-AZ dependency - if that AZ fails, every other AZ's private resources lose outbound access too, undermining multi-AZ availability, plus cross-AZ data transfer charges. Per-AZ NAT Gateways avoid both, at the cost of paying for multiple.

Intermediate - Instance has a public IP and its subnet routes to an IGW, but still unreachable - what to check? Two of three conditions confirmed. Check whether the IGW is actually attached to the VPC. If fine, the issue is likely security groups or NACLs (Section 3) blocking the traffic - route table and public IP being correct doesn't guarantee the firewall layers allow it.

Senior - Design subnet/routing for a three-tier app (public web, private app, private DB) across two AZs, optimizing availability and cost? Six subnets: public, app-private, db-private, each duplicated per AZ. Public subnets host the ALB and one NAT Gateway per AZ. Each AZ's private subnets route to that AZ's own NAT Gateway. Evaluate VPC Endpoints for AWS-service-bound app-tier traffic to avoid NAT data-processing charges. Database tier ideally has no NAT route at all if no outbound internet is needed - only the local route. Size private (app) subnets generously for ASG headroom; public/database subnets smaller given predictable lower counts.

---

## Key Takeaways

1. Public vs private is a function of the route table, not a subnet property - public specifically because of an IGW route.
2. Three conditions must all hold for internet reachability: attached IGW, route table route to it, and a public IP on the instance.
3. NAT Gateways provide asymmetric outbound-only access, sit in a public subnet, and cost hourly plus per-GB - a real cost line item.
4. One NAT Gateway per AZ is the production standard, trading extra cost for avoiding a cross-AZ single point of failure.
5. The public-subnet/private-subnet/NAT-Gateway pattern is the concrete mechanics behind every internet-facing-tier-plus-internal-tier architecture referenced throughout Parts 1-3.

## Related Concepts (forward links)

- Security Groups vs NACLs, the firewall layers on top of this routing foundation, including their independent IPv4/IPv6 evaluation (see §5a) -> §31
- VPC Peering, Transit Gateway, PrivateLink for cross-VPC routing -> §32
- VPC Endpoints as a NAT Gateway cost-avoidance mechanism -> §37
- Bastion hosts vs Systems Manager Session Manager -> Part 8
