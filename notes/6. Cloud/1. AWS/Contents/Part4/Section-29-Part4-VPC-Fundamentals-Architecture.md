# Part 4 - Section 1 - VPC Fundamentals & Architecture

AWS Zero-to-Enterprise Knowledge Base - Part 4: Networking & Content Delivery

---

## 1. Definition

Plain-language: A VPC is your own private, isolated slice of the AWS network - like having your own data center's network, logically carved out of AWS's infrastructure, where you control IP ranges, traffic flow, and what can reach in or out.

Precise: An Amazon Virtual Private Cloud (VPC) is a logically isolated virtual network, scoped to a single AWS Region, within which you launch AWS resources, defining your own IP address range, subnets, route tables, and gateways - the networking foundation every compute/database resource with network presence sits inside.

---

## 2. Why It Exists

- Multi-tenancy (Part 1 Section 4) means many customers share AWS's physical infrastructure - a VPC is the networking-layer expression of that isolation: your VPC's traffic is invisible to and unreachable from another customer's VPC by default, mirroring account-level isolation at the network layer.
- Without a VPC construct, you couldn't replicate on-premises networking concepts (subnets, routing, firewalls) every real application architecture needs.
- Every account gets a Default VPC per Region automatically, pre-configured with public subnets in every AZ and internet connectivity wired up - so a brand-new account can launch an instance immediately (what Part 3's labs relied on). Production architectures almost always use a deliberately-designed custom VPC instead.

---

## 3. IP Addressing - CIDR Blocks

### 3.1 CIDR Notation

- A VPC is defined by an IPv4 CIDR block (e.g., 10.0.0.0/16) - the /16 indicates fixed network bits, leaving the rest for host addresses.
- Smaller number after the slash = larger address range. A /16 provides 65,536 addresses; a /24 provides 256 - a commonly confused inverse relationship.

### 3.2 VPC CIDR Sizing

- Primary CIDR ranges from /16 (largest, 65,536 addresses) to /28 (smallest, 16 addresses).
- Sizing is a real architectural decision - too small constrains future growth; AWS guidance favors starting large (like /16) since resizing later is disruptive.
- Private IP ranges (RFC 1918): 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16 - same as traditional on-prem networking, non-routable on the public internet.

### 3.3 Secondary CIDR Blocks

- Additional CIDR blocks can be added after creation to expand address space - a mitigation for under-sizing, not a substitute for planning generously upfront.

---

## 4. Availability Zones and VPCs - Regional Scope

- A VPC spans an entire Region - not confined to a single AZ. Subnets (Section 2) are the construct tied to a specific single AZ.
- This is why "spread across multiple AZs" HA guidance is implemented via subnets: one VPC per Region, multiple subnets within it (one or more per AZ), resources placed across those AZ-specific subnets.

---

## 5. Core VPC Components - Full Inventory

- Subnets - AZ-specific subdivisions of the VPC's CIDR range (Section 2).
- Route Tables - control where subnet traffic is directed (Section 2).
- Internet Gateway (IGW) - provides internet connectivity (Section 2).
- NAT Gateway/Instance - outbound-only internet access for private resources (Section 2).
- Security Groups and NACLs - the two firewall layers (Section 3).
- VPC Peering, Transit Gateway, PrivateLink - connecting VPCs to each other or services privately (Section 4).
- VPN and Direct Connect - connecting a VPC to on-premises networks (Section 5).
- ENIs (Part 3 Section 4.3) - the actual attachment point giving any resource its VPC presence.

---

## 6. Default VPC vs Custom VPC

|                 | Default VPC                                | Custom VPC                             |
| --------------- | ------------------------------------------ | -------------------------------------- |
| Creation        | Automatic, one per Region/account          | Deliberately designed                  |
| Subnets         | Pre-created public subnet in every AZ      | You define exactly what's needed       |
| Internet access | Pre-wired (IGW attached, route configured) | Configured deliberately                |
| CIDR            | AWS-chosen (typically 172.31.0.0/16)       | You choose, sized/planned deliberately |
| Best for        | Quick starts, learning                     | Production architectures               |

Key idea: the Default VPC's convenience (everything pre-wired for internet access) is precisely why it's inappropriate for production - production needs deliberate public/private subnet separation the Default VPC's "everything public by default" design doesn't provide.

---

## 7. Multi-VPC and Multi-Account Architecture

- Enterprises use multiple VPCs, often per account, following the same environment/business-unit separation logic (Part 1 Section 7, Part 2 Section 5) at the network layer.
- The resulting connectivity challenge is what Section 4 (Peering, Transit Gateway, PrivateLink) solves: VPCs are isolated from each other by default, exactly like accounts.

---

## 8. IPv6 Support

- VPCs can optionally support IPv6 (dual-stack) or IPv6-only subnets, given IPv6's vastly larger address space vs IPv4's constrained availability.
- Most existing AWS architectures remain primarily IPv4-based; IPv6 adoption is growing but not yet the default assumption.

---

## 9. DNS Within a VPC

- Two settings: enableDnsSupport (Amazon-provided DNS resolution) and enableDnsHostnames (instances get DNS hostnames) - both enabled by default, but explicit checkable settings.
- Amazon-provided DNS resolver reachable at the VPC's CIDR base +2 (e.g., 10.0.0.2 for a 10.0.0.0/16 VPC) - resolves public and internal AWS/private DNS names (full Route 53 depth, Section 6).

---

## 10. Production & Enterprise Usage

- Standardized VPC design via Infrastructure as Code - CIDR/subnets/route tables as a Terraform/CloudFormation module, deployed consistently across accounts/environments.
- CIDR planning across an Organization - overlapping CIDR ranges between VPCs that might ever connect (peering/Transit Gateway) makes connection impossible without disruptive re-addressing. Plan centrally: each account/team gets a non-overlapping block from a master range.
- Landing zone VPC patterns (Control Tower) - account vending includes a standardized, pre-approved VPC design as part of baseline setup.

---

## 11. Security Considerations

- A VPC's isolation is itself a security boundary - nothing reaches in or out by default except as explicitly configured, mirroring account isolation at the network layer.
- CIDR overlap is a security design constraint too - resolving it under time pressure later is riskier than planning correctly from the start.
- Full security group/NACL depth is Section 3.

---

## 12. Troubleshooting

| Symptom                                           | Cause                                                          | Fix                                                                        |
| ------------------------------------------------- | -------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Two VPCs can't be peered                          | Overlapping CIDR blocks                                        | Requires re-addressing one VPC (disruptive) - prevent via upfront planning |
| Ran out of IPs adding subnets                     | VPC CIDR too small at creation                                 | Add a secondary CIDR block; size future VPCs more generously               |
| Instance has no DNS hostname                      | enableDnsHostnames disabled                                    | Enable the setting at the VPC level                                        |
| Default VPC used for production, causing concerns | Public-by-default design used without deliberate custom design | Migrate to a properly designed custom VPC                                  |

---

## 13. Best Practices & Anti-Patterns

Best practices: design custom VPCs deliberately for production; size CIDR blocks generously (favor /16); plan CIDR allocation centrally across the Organization; define VPC architecture as IaC.

Anti-patterns: using the Default VPC for production; under-sizing CIDR blocks; allocating CIDR per-team without central coordination; manually clicking through VPC setup repeatedly instead of codifying it.

---

## 14. Common Misconceptions

- "A VPC is confined to a single AZ." False - spans an entire Region; subnets are AZ-specific.
- "A smaller CIDR slash number means a smaller range." False - inverted; /16 is larger than /24.
- "The Default VPC is fine for production." False - its public-by-default design is why custom VPCs exist.
- "Any two VPCs can always be connected later." False - overlapping CIDR blocks prevent it without disruptive re-addressing.

---

## 15. Interview Questions (with model answers)

Beginner - What is a VPC, and what problem does it solve? A logically isolated virtual network within a Region, with your own IP range, subnets, and routing. The networking-layer expression of AWS's multi-tenancy isolation - invisible/unreachable from other customers' VPCs by default, replicating on-prem networking concepts like public/private tiers.

Beginner - Is a VPC tied to a single AZ? No - spans an entire Region. Subnets are the AZ-specific construct. This is why HA architectures create multiple subnets across multiple AZs within one VPC, not separate VPCs per AZ.

Intermediate - Why size a VPC CIDR generously (like /16) even without immediate need? Resizing later is genuinely disruptive - a secondary CIDR block is a workaround for under-sizing, not a clean fix. A /16 gives 65,536 addresses, room for many subnets/AZs and future growth, avoiding retrofitting address space under pressure later.

Intermediate - Two teams both used 10.0.0.0/16 and now want VPC peering - problem and prevention? Overlapping CIDR blocks prevent peering - AWS can't route between identical address ranges. Fixing now requires disruptive re-addressing of one VPC. Prevent via centralized CIDR allocation - each team/account gets a non-overlapping block from a coordinated master range.

Senior - Design VPC/CIDR strategy for an org anticipating 50 accounts over three years with near-certain future Transit Gateway connectivity? Establish centralized CIDR allocation before any account creates a VPC - reserve a large master range, carve non-overlapping /16 allocations per account/business unit, tracked in a central registry. Codify VPC creation as an IaC module taking the pre-assigned CIDR as a parameter for consistency. Design with Transit Gateway connectivity in mind from day one, since retrofitting non-overlapping addressing across 50 already-deployed accounts later would be enormously disruptive compared to getting it right upfront.

---

## Key Takeaways

1. A VPC is a logically isolated virtual network scoped to a Region (not an AZ) - the network-layer expression of multi-tenancy isolation.
2. CIDR notation is inverted from intuition - smaller slash number means larger range; VPC CIDR blocks range from /16 to /28.
3. The Default VPC is convenient but inappropriate for production - custom VPCs with public/private subnet separation exist to replace it.
4. CIDR planning must be centralized and proactive across an Organization - overlapping CIDR blocks make future peering/Transit Gateway connectivity impossible without disruptive re-addressing.
5. A VPC is the container; subnets, route tables, gateways, and firewalls are the components giving it function - this section named the inventory; Sections 2-4 build each to full depth.

## Related Concepts (forward links)

- Subnets, route tables, Internet Gateway, NAT Gateway in full depth -> §30
- Security Groups vs NACLs in full depth -> §31
- VPC Peering, Transit Gateway, PrivateLink -> §32
- Route 53 DNS in full depth -> §34
