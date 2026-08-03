# Part 4 - Section 4 - VPC Peering, Transit Gateway & PrivateLink

AWS Zero-to-Enterprise Knowledge Base - Part 4: Networking & Content Delivery

---

## 1. Definition

Plain-language: VPC Peering directly connects two VPCs as if they were one network. Transit Gateway acts as a central hub connecting many VPCs (and on-premises networks) without needing a direct connection between every pair. PrivateLink lets you privately consume a specific service in another VPC without connecting the networks at all.

Precise: VPC Peering is a direct, one-to-one, non-transitive network connection between two VPCs. AWS Transit Gateway is a centralized, transitive routing hub connecting many VPCs and on-premises networks through a single attachment point each. AWS PrivateLink provides private connectivity to a specific service via an interface endpoint, without exposing either network to the other.

---

## 2. Why This Category Exists

- VPCs are isolated by default (mirroring account isolation, Part 2 Section 5) - something must bridge that isolation deliberately.
- The core question: do you need full network-level connectivity, connectivity among many networks at once, or just access to one specific service without merging networks? Each mechanism optimizes for a different answer.

---

## 3. VPC Peering

### 3.1 Definition and Mechanics

- Creates a direct network route between two VPCs, private IP communication, never traverses the public internet.
- Requires non-overlapping CIDR blocks (Section 1) - the hard constraint making peering impossible without re-addressing.
- Cross-account and cross-Region peering supported (mutual acceptance required); cross-Region incurs inter-Region data transfer charges (Part 1 Section 6).

### 3.2 Critical Limitation - Non-Transitive

- Most important fact: peering connections are non-transitive. A peered with B, B peered with C - A CANNOT reach C through B.
- Practical consequence: fully connecting N VPCs via peering requires a separate connection per pair - N(N-1)/2 connections, quadratic growth, unmanageable at scale. Exactly the problem Transit Gateway solves.

### 3.3 Route Table Requirements

- Peering alone doesn't enable traffic flow - each VPC's route table must be explicitly updated to route to the peer's CIDR through the connection, plus Security Groups/NACLs (Section 3) must allow the traffic.

---

## 4. AWS Transit Gateway

### 4.1 Definition and Mechanics

- A regional, managed network hub that VPCs (and on-premises networks via VPN/Direct Connect, Section 5) attach to, rather than connecting pairwise - one attachment per VPC.
- Genuinely transitive - VPCs attached to the same Transit Gateway can communicate through it without a direct connection to each other.

### 4.2 Why This Solves Peering's Scaling Problem

- Connecting N VPCs requires only N attachments - linear, not quadratic. Adding a new VPC needs one new attachment, not a connection to every existing VPC.

### 4.3 Transit Gateway Route Tables - Segmentation

- Transit Gateway supports its own route tables, separate from each VPC's; multiple route tables enable segmentation - e.g., production VPCs reach each other and shared services, but explicitly not development VPCs, even on the same Transit Gateway - a networking-layer parallel to Part 2 Section 5's OU segmentation.

### 4.4 Centralized Connectivity Patterns

- Hub-and-spoke - a central hub VPC (shared services, NAT, security tooling) connects to many spoke VPCs via Transit Gateway rather than each spoke having its own - extends the centralized Security/Shared-Services account pattern to networking.
- Combining with Direct Connect/VPN - Transit Gateway as the central attachment point for on-premises connectivity, gaining access to every attached VPC through one connection.

---

## 5. VPC Peering vs Transit Gateway - The Decision

|                      | VPC Peering                                 | Transit Gateway                                   |
| -------------------- | ------------------------------------------- | ------------------------------------------------- |
| Connectivity model   | Direct, pairwise                            | Centralized hub, transitive                       |
| Scaling to many VPCs | Quadratic growth (full mesh)                | Linear growth (one attachment each)               |
| Transitivity         | None                                        | Full                                              |
| Cost                 | No hourly charge; data transfer applies     | Hourly charge per attachment plus data processing |
| Segmentation         | Implicit (only connected pairs communicate) | Explicit via Transit Gateway route tables         |
| Best for             | Small, stable VPC count (2-3)               | Many/growing VPCs, or need for segmentation       |

Clean summary: VPC Peering is simple and free of hourly charges but doesn't scale past a handful of VPCs. Transit Gateway costs more but scales linearly and supports genuine segmentation - the standard choice for more than a few VPCs or any growth expectation.

---

## 6. AWS PrivateLink

### 6.1 Definition and the Problem It Solves

- Provides private connectivity to a specific service in another VPC (or to AWS services directly) without VPC Peering, Transit Gateway, or any broader network connection - without exposing either party's full network.
- Core distinction: Peering/Transit Gateway connect NETWORKS; PrivateLink connects to a specific SERVICE ENDPOINT - narrower, more security-conscious.

### 6.2 Interface Endpoints

- Implemented via an Interface Endpoint - an ENI placed in the consumer's VPC/subnet with a private IP, forwarding traffic privately to the target service, never traversing the public internet.
- Different from a Gateway Endpoint (Section 9) - Interface Endpoints work broadly; Gateway Endpoints are specifically S3/DynamoDB only, using route-table mechanics instead of an ENI.

### 6.3 VPC Endpoint Services - Exposing Your Own Service

- A provider (AWS service or your own app behind an NLB) can be published as a VPC Endpoint Service, letting other VPCs/accounts privately connect via PrivateLink, without peering or Transit Gateway.
- A powerful SaaS/multi-tenant pattern - a vendor exposes their product to many customer VPCs privately, without ever needing network-level connectivity (and CIDR-overlap risk) to any of them.

---

## 6a. VPC Lattice

### 6a.1 Definition and the Problem It Solves

- VPC Lattice is an application-layer (not network-layer) connectivity service - it connects services to each other, across VPCs and accounts, without requiring VPC Peering, Transit Gateway attachments, or PrivateLink endpoints to be individually configured for every consumer.
- The problem it targets: in a growing microservices environment, connecting many services across many VPCs/accounts using PrivateLink means standing up a VPC Endpoint Service and Interface Endpoint pair for every service-to-consumer relationship - workable at small scale, genuinely tedious to manage as the number of services and consumers grows into the dozens or hundreds.
- Core distinction from everything else in this section: Peering, Transit Gateway, and PrivateLink all operate at Layer 3/4 (IP/TCP) - VPC Lattice operates at Layer 7 (HTTP/HTTPS/gRPC), meaning it understands and can route on application-level concepts like paths and headers, not just network reachability.

### 6a.2 Service Network - The Core Construct

- A Service Network is the central Lattice construct - a logical boundary that services and consumers are associated with, similar in spirit to how Transit Gateway is a central hub VPCs attach to, but operating on services rather than entire VPC networks.
- Once a service is associated with a Service Network, every consumer also associated with that Service Network can reach it - without a separate point-to-point connection per pair, avoiding PrivateLink's "one Endpoint Service and one Interface Endpoint per relationship" overhead at scale.
- Access to a service within a Service Network is governed by an auth policy (an IAM-based resource policy, following the same access-control mechanics as other AWS resource policies) - meaning connectivity and authorization are handled together, not as two separate configuration steps.

### 6a.3 VPC Lattice vs PrivateLink - The Decision

- PrivateLink remains the right choice for exposing a single, specific service to a bounded, relatively small/stable set of consumers, or for the common third-party SaaS integration pattern (Section 6.3) where a vendor exposes one product endpoint broadly.
- VPC Lattice is the better fit when an organization has many internal services that many other services/teams need to consume, in an environment where standing up individual PrivateLink Endpoint Services per relationship has become a genuine management burden - it is specifically a scaling solution for the many-services-to-many-consumers problem, the same kind of scaling gap Transit Gateway closes for VPC Peering, but one layer up the stack (services, not networks).
- Interview tip: framing VPC Lattice as "PrivateLink at scale" is a reasonable first-pass mental model, but the more precise distinction is the OSI layer - PrivateLink is a network/transport-layer private connection to a specific endpoint, VPC Lattice is an application-layer service mesh-like construct aware of HTTP semantics.

### 6a.4 Key Takeaways

1. VPC Lattice solves service-to-service connectivity at the application layer, avoiding the per-relationship overhead of standing up individual PrivateLink endpoints as the number of internal services and consumers grows.
2. A Service Network is the central construct services and consumers associate with - connectivity and IAM-based authorization are handled together, not as separate steps.
3. PrivateLink remains the right choice for single-service exposure or third-party SaaS patterns; VPC Lattice is the right choice for many-to-many internal service connectivity at genuine scale.

## 7. Full Decision Framework

Question: do you need full network-level connectivity (many resources, ports/protocols) between VPCs, or just one specific service?

- Just one service -> Use PrivateLink (Interface Endpoint / VPC Endpoint Service)
- Full network connectivity, few/stable VPCs (2-3) -> Use VPC Peering
- Full network connectivity, many/growing VPCs or need segmentation -> Use Transit Gateway

Key idea: the deciding question isn't "which is more powerful" - PrivateLink is deliberately the narrowest, most restrictive option, exactly its value when only service-level access is needed. Reaching for full network connectivity when only a specific service is needed is more connectivity than necessary - a least-privilege violation at the network layer.

---

## 8. Production & Enterprise Usage

- Transit Gateway is the standard enterprise pattern for more than a handful of VPCs, given peering's quadratic scaling - connects to Part 2 Section 5's multi-account-per-team pattern.
- Hub-and-spoke with centralized egress VPC - routing all VPCs' internet-bound traffic through one central VPC's NAT Gateways via Transit Gateway, consolidating cost and centralizing egress monitoring.
- PrivateLink for third-party SaaS integrations and internal multi-team service consumption - a platform team exposes a shared service via a VPC Endpoint Service without broader network connectivity.
- Transit Gateway peering (distinct from VPC Peering) connects Transit Gateways across Regions, extending hub-and-spoke to multi-Region scale.

---

## 9. Security Considerations

- PrivateLink's narrow exposure is a genuine security advantage - zero visibility into or reachability toward anything in the provider's VPC beyond the published service.
- Transit Gateway route table segmentation is a real enforceable security boundary - preventing dev VPCs from reaching production VPCs even on the same Transit Gateway, parallel to SCP-based OU segmentation.
- VPC Peering's full mesh, at scale, expands blast radius - every peered pair has full network reachability (subject to SGs/NACLs) - a reason beyond complexity to prefer Transit Gateway's segmentable model as VPC count grows.

---

## 10. Performance Considerations

- VPC Peering and Transit Gateway both use AWS's private backbone - never the public internet, low latency/high throughput vs VPN alternatives (Section 5).
- Transit Gateway introduces a small amount of additional processing as a routing hub vs direct peering - rarely significant, but worth knowing the trade-off exists.

---

## 11. Troubleshooting

| Symptom                                                             | Cause                                                                                  | Fix                                                                 |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ------------------------------------------------------------------- |
| Two peered VPCs still can't communicate                             | Route tables not updated on one/both sides                                             | Verify both VPCs' route tables route to the peer's CIDR             |
| A can reach B, B can reach C, but A can't reach C                   | Assuming VPC Peering is transitive - it isn't                                          | Direct A-C peering, or migrate to Transit Gateway                   |
| Two VPCs can't be peered at all                                     | Overlapping CIDR blocks                                                                | Requires re-addressing; prevent via central CIDR planning           |
| Spoke VPC reaches some Transit-Gateway-attached VPCs but not others | Route table segmentation intentional or misconfigured                                  | Review the specific Transit Gateway route table for that attachment |
| Consumer can't reach a published VPC Endpoint Service               | Provider hasn't accepted the connection, or consumer SG doesn't allow endpoint traffic | Verify acceptance and security group config on both sides           |

---

## 12. Best Practices & Anti-Patterns

Best practices: use Transit Gateway once VPC count grows beyond a handful; use PrivateLink when only a specific service is needed; segment Transit Gateway route tables deliberately (production vs non-production at minimum); plan CIDR ranges centrally.

Anti-patterns: building a large peering mesh instead of migrating to Transit Gateway; assuming VPC Peering is transitive; using full Peering/Transit Gateway when PrivateLink would suffice; a flat Transit Gateway route table with no segmentation.

---

## 13. Common Misconceptions

- "If A is peered with B, and B with C, A can reach C." False - non-transitive; needs direct A-C peering or a shared Transit Gateway.
- "Transit Gateway is just VPC Peering at larger scale." False - architecturally different, a routing hub enabling transitivity and segmentation.
- "PrivateLink connects two VPCs' networks, like lighter peering." False - connects to one specific service, no broader network reachability either direction.
- "Peering/Transit Gateway traffic goes over the public internet." False - both use AWS's private backbone regardless of account/Region.

---

## 14. Interview Questions (with model answers)

Beginner - What does it mean that VPC Peering is non-transitive? A peering connection only connects the two specific VPCs directly involved - A peered with B, B peered with C doesn't let A reach C through B. Each pair needing communication needs its own direct connection.

Beginner - Fundamental difference between Peering/Transit Gateway and PrivateLink? Peering/Transit Gateway connect entire networks, broad reachability subject to routing/SG rules. PrivateLink connects a consumer only to one specific published service without exposing either party's broader network - narrower, appropriate when only service-level access is needed.

Intermediate - Why does Transit Gateway scale better than Peering as VPC count grows? Peering requires a direct connection per pair (non-transitive) - N VPCs need roughly N(N-1)/2 connections, quadratic, unmanageable quickly. Transit Gateway has each VPC attach once to a central hub - N attachments, linear; a new VPC needs only one new attachment.

Intermediate - Platform team wants to expose an internal API to dozens of teams' VPCs without broader network access - recommendation? PrivateLink, publishing the API as a VPC Endpoint Service. Each consuming VPC creates an Interface Endpoint connecting privately, no Peering/Transit Gateway attachment needed. Gives exactly the needed access with zero visibility into anything else in the platform VPC - the least-privilege outcome. Transit Gateway/Peering would grant more access than necessary.

Senior - Design connectivity for 40 VPCs across accounts: production reaches shared services and each other, never development, plus on-prem connectivity for production? Transit Gateway as central hub, every VPC attached once, avoiding a peering mesh. At least two route tables: production route table (production attachments + shared-services, routing between all) and development route table (development VPCs + shared services if needed, critically NOT production) - enforcing segmentation at the routing layer, not just Security Groups. Attach Direct Connect/VPN to the Transit Gateway itself, associated with the production route table, giving on-prem access to all production VPCs and shared services through one attachment. Centralized, segmented, linearly-scaling, architecturally enforced isolation.

---

## Key Takeaways

1. VPC Peering is direct, simple, but non-transitive - connecting many VPCs requires a full mesh, scaling quadratically.
2. Transit Gateway is a centralized, transitive hub - each VPC attaches once, scaling linearly, with route tables enabling genuine segmentation.
3. PrivateLink connects to a specific service, not a network - the narrowest, most restrictive option, right when only service-level access is needed.
4. The decision among the three is a least-privilege architectural question, not "which is most powerful" - more connectivity than necessary is itself an anti-pattern.
5. All this connectivity happens over AWS's private backbone, never the public internet, and still passes through Security Group/NACL firewall layers regardless of mechanism.

## Related Concepts (forward links)

- VPN and Direct Connect for on-premises connectivity, including Transit Gateway attachment -> §33
- Gateway Endpoints (S3/DynamoDB) vs Interface Endpoints (PrivateLink) in full depth -> §37
- Route 53 Resolver for DNS across peered/Transit-Gateway-connected VPCs -> §34
- AWS Global Accelerator, a complementary network-layer global traffic-routing service -> §34a (within Section 6, Route 53)
- VPC Lattice (see Section 6a above) as the application-layer alternative for many-to-many internal service connectivity
