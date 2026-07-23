# Part 4 - Section 5 - Hybrid Connectivity: VPN & Direct Connect

AWS Zero-to-Enterprise Knowledge Base - Part 4: Networking & Content Delivery

---

## 1. Definition

Plain-language: VPN creates an encrypted tunnel over the public internet between your on-premises network and your VPC - fast to set up, but subject to internet variability. Direct Connect is a dedicated, private physical network connection from your facility to AWS - more work to establish, but consistent, high-bandwidth, and doesn't touch the public internet.

Precise: AWS Site-to-Site VPN provides an encrypted IPsec tunnel over the public internet connecting an on-premises network to a VPC. AWS Direct Connect provides a dedicated, private physical network connection between an on-premises facility and AWS, bypassing the public internet entirely.

---

## 2. Why This Category Exists

- Hybrid cloud (Part 1 Section 6) is a deliberate combination of on-premises and public cloud, connected together - this section builds that connection.
- Two different problems: get connected quickly/cheaply (VPN's strength) vs get connected with consistent, high-bandwidth, private connectivity (Direct Connect's strength) - genuinely different trade-offs.

---

## 3. AWS Site-to-Site VPN

### 3.1 Definition and Mechanics

- Establishes an IPsec VPN tunnel - two tunnels by default for redundancy - between a Customer Gateway (on-prem endpoint) and a Virtual Private Gateway (attached to your VPC) or Transit Gateway.
- Traffic travels over the public internet but is encrypted via IPsec - security via encryption, not network isolation.

### 3.2 Customer Gateway vs Virtual Private Gateway

- Customer Gateway (CGW) - a resource representing your on-premises VPN device, a logical AWS-side representation.
- Virtual Private Gateway (VGW) - the VPN concentrator on the AWS side, attached to a specific VPC.
- Two tunnels by default - so a single tunnel/endpoint failure doesn't cause complete connectivity loss (Part 1 Section 2's redundancy principle applied to hybrid connectivity).

### 3.3 Setup Speed and Cost

- Can be set up quickly, often within hours - no physical infrastructure installation.
- Cost: hourly charge per connection plus data transfer - meaningfully cheaper to establish than Direct Connect.

### 3.4 Limitations

- Subject to public internet variability - bandwidth/latency not guaranteed, can fluctuate.
- Bandwidth ceiling generally lower and less consistent than Direct Connect.

---

## 4. AWS Direct Connect

### 4.1 Definition and Mechanics

- A dedicated, private physical network connection between your facility (or colocation) and an AWS Direct Connect location - traffic never touches the public internet.
- Requires physical infrastructure setup, either direct or via an AWS Direct Connect Partner - weeks to months, a fundamentally different timeline than VPN.

### 4.2 Virtual Interfaces (VIFs)

- A Direct Connect connection hosts one or more VIFs:
  - Private VIF - connects to VPC resources (via Virtual Private Gateway or Direct Connect Gateway).
  - Public VIF - connects to AWS public service endpoints (S3, DynamoDB) WITHOUT traversing the public internet - counterintuitive but useful.
  - Transit VIF - connects to a Transit Gateway (Section 4), reaching multiple VPCs through the hub-and-spoke model.

### 4.3 Direct Connect Gateway

- Allows a single Direct Connect connection to reach multiple VPCs across multiple Regions - without it, a private VIF ties to one VPC's VGW, requiring separate VIFs/connections per VPC. Extends the "avoid a connectivity mesh" theme from Transit Gateway (Section 4).

### 4.4 Bandwidth Options and Cost

- Dedicated connections at fixed bandwidth tiers, or hosted connections (smaller increments via a Partner).
- Cost: port-hour charge plus data transfer out - but Direct Connect data-transfer rates are typically LOWER than standard internet transfer-out rates, potentially more cost-effective at high sustained volume despite higher setup cost/complexity.

### 4.5 Limitations

- Setup time/complexity - weeks to months, physical proximity or partner relationship required.
- No built-in encryption - private (never touches public internet) but NOT encrypted by default; layer VPN over it (Section 5) or use TLS if encryption in transit is required.

---

## 5. VPN Over Direct Connect - Combining Both

- Running an IPsec VPN connection over a Direct Connect private VIF - combines Direct Connect's private/dedicated/high-bandwidth path with VPN's encryption, directly addressing the "not encrypted by default" gap.
- Matters when compliance mandates encryption in transit even over already-private paths - satisfies this without falling back to lower/less-predictable VPN-over-internet bandwidth.

---

## 6. VPN vs Direct Connect - The Decision

|                               | Site-to-Site VPN                                       | Direct Connect                                                          |
| ----------------------------- | ------------------------------------------------------ | ----------------------------------------------------------------------- |
| Path                          | Public internet (encrypted)                            | Dedicated private physical link                                         |
| Setup time                    | Hours                                                  | Weeks to months                                                         |
| Bandwidth/latency consistency | Variable                                               | Consistent, dedicated                                                   |
| Encryption                    | Built-in (IPsec)                                       | Not built-in (layer VPN if needed)                                      |
| Cost model                    | Lower setup cost, hourly + data transfer               | Higher setup complexity; potentially lower data-transfer rates at scale |
| Best for                      | Quick setup, backup/failover, lower/moderate bandwidth | Sustained high-bandwidth, latency-sensitive, large-scale transfer       |

Clean summary: VPN is fast and encrypted by default but rides the variable public internet. Direct Connect is a dedicated private link with consistent performance and often better economics at scale, but takes weeks to months and isn't encrypted unless VPN is layered on top. Many enterprises use both - Direct Connect primary, VPN as automatic failover.

---

## 7. VPN as Direct Connect Failover - Standard Pattern

- Using Site-to-Site VPN as an automatic backup path if Direct Connect fails - Direct Connect is still a physical link that can fail (fiber cut, equipment failure); VPN's internet path provides genuine physical-path diversity as fallback.
- Directly extends Part 1 Section 2's redundancy philosophy - just as production compute shouldn't run in a single AZ, critical hybrid connectivity shouldn't rely on a single physical network path without a fallback.
- Redundant Direct Connect connections (different locations/providers) used when even VPN failover's lower bandwidth isn't acceptable - a further redundancy layer for the most critical architectures.

---

## 8. Production & Enterprise Usage

- Direct Connect + Transit Gateway (via Transit VIF) - standard large-enterprise pattern connecting on-prem to many VPCs, on-prem as one more "spoke" through the central hub.
- Migration-phase hybrid connectivity - start with VPN for immediate connectivity, establish Direct Connect once sustained bandwidth needs/timelines justify the investment - a common staged pattern, not always Direct-Connect-from-day-one.
- Direct Connect Gateway for multi-Region hybrid architectures - one connection reaching VPCs across multiple Regions from a centralized on-prem data center.

---

## 9. Security Considerations

- Direct Connect's lack of default encryption is a genuine compliance consideration - explicitly layer VPN over it or ensure TLS covers relevant traffic; "private link means automatically compliant" is a dangerous assumption.
- VPN security relies on correct IPsec configuration - keys/certificates, algorithms, tunnel config must be correctly set on both Customer Gateway and Virtual Private Gateway sides.
- Both mechanisms still terminate into a VPC subject to Security Groups/NACLs (Section 3) - hybrid connectivity establishes the path, doesn't bypass firewall layers.

---

## 10. Performance Considerations

- Direct Connect's consistent, dedicated bandwidth is its primary advantage - the deciding factor for latency-sensitive/sustained-high-throughput workloads over VPN's variable performance.
- VPN throughput is generally capped lower than comparable Direct Connect - check against actual requirements before assuming VPN suffices.

---

## 11. Troubleshooting

| Symptom                                                       | Cause                                                                                               | Fix                                                                                          |
| ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| VPN up but on-prem can't reach VPC resources                  | Route tables not routing through VGW, or on-prem routing not sending VPC traffic through the tunnel | Verify routing on both AWS side (VPC route table) and on-prem side (Customer Gateway device) |
| Direct Connect up but traffic not flowing to a VPC            | Missing/misconfigured VIF (Public used where Private needed, or vice versa)                         | Verify correct VIF type for intended traffic                                                 |
| Inconsistent hybrid performance                               | VPN used for a workload exceeding what internet-path VPN reliably provides                          | Evaluate migrating to Direct Connect                                                         |
| Direct Connect traffic unencrypted but compliance requires it | No built-in encryption                                                                              | Layer IPsec VPN over the Direct Connect private VIF                                          |

---

## 12. Best Practices & Anti-Patterns

Best practices: use VPN as an automatic failover for Direct Connect; use Direct Connect Gateway/Transit Gateway rather than per-VPC connectivity; layer VPN over Direct Connect when encryption in transit is required; start with VPN during early migration, establish Direct Connect once bandwidth needs justify it.

Anti-patterns: relying on a single Direct Connect connection with no failover for critical workloads; assuming Direct Connect is encrypted by default; provisioning separate Direct Connect connections per VPC; choosing Direct Connect when VPN would serve actual needs, incurring unnecessary cost/lead time.

---

## 13. Common Misconceptions

- "Direct Connect traffic is automatically encrypted since it's private." False - no built-in encryption; VPN must be layered on top if required.
- "VPN and Direct Connect are mutually exclusive." False - VPN-as-failover and VPN-over-Direct-Connect-for-encryption are both standard complementary patterns.
- "Direct Connect is always better since it's dedicated and private." False as a blanket claim - VPN's fast setup/lower cost is the better fit for many scenarios.
- "A Public VIF means traffic goes over the public internet." False - still traverses Direct Connect's private link; "public" refers to reaching AWS's public service endpoints, not the path being public.

---

## 14. Interview Questions (with model answers)

Beginner - Fundamental difference between Site-to-Site VPN and Direct Connect? VPN: encrypted tunnel over the public internet, fast setup, variable performance. Direct Connect: dedicated private physical link bypassing the internet, consistent performance, weeks-to-months setup, not encrypted by default.

Beginner - Is Direct Connect traffic encrypted? Not by default. Private path but not encryption; layer an IPsec VPN over the Direct Connect private VIF (or use TLS) if encryption in transit is required.

Intermediate - Why use both VPN and Direct Connect together? Most common reason: VPN as automatic failover if Direct Connect fails (still a physical link that can fail) - the same redundancy principle used elsewhere in AWS architecture. Another reason: layering VPN over Direct Connect specifically to add encryption while keeping the dedicated path's performance.

Intermediate - Single Direct Connect connection, no other hybrid connectivity - risk and fix? Single point of failure - an outage loses all hybrid connectivity. Fix: establish Site-to-Site VPN as automatic backup, accepting reduced bandwidth during failover rather than total loss. For stricter needs, a second physically-diverse Direct Connect connection provides stronger redundancy at higher cost.

Senior - Design hybrid connectivity for a large enterprise: on-prem to 15 VPCs across 3 Regions, encryption-in-transit compliance requirement, high consistent bandwidth requirement? Direct Connect as primary given bandwidth/consistency needs. Use Direct Connect Gateway (or Transit VIF into Transit Gateway if VPCs already hub-and-spoke) to reach 15 VPCs across 3 Regions without per-VPC connectivity. Layer IPsec VPN over the Direct Connect private/transit VIF to satisfy the encryption requirement without sacrificing dedicated bandwidth. For resilience: second physically-diverse Direct Connect connection as primary failover (VPN-over-internet alone may be insufficient given stated bandwidth needs), with Site-to-Site VPN as a final backstop.

---

## Key Takeaways

1. VPN is fast, encrypted by default, rides the variable public internet; Direct Connect is a dedicated private link with consistent performance, weeks-to-months setup, not encrypted by default - genuinely different trade-offs.
2. Direct Connect's lack of built-in encryption is a real, commonly-missed gap - "private" does not mean "encrypted."
3. VPN as an automatic failover path for Direct Connect is a standard, important production pattern - the same redundancy discipline applied throughout AWS architecture.
4. Direct Connect Gateway (and Transit VIF into Transit Gateway) solve the "one connection, many VPCs/Regions" problem, extending the "avoid a connectivity mesh" theme to hybrid connectivity.
5. Both VPN and Direct Connect traffic still terminate into a VPC subject to Security Groups/NACLs - hybrid connectivity establishes the path, doesn't bypass firewall layers.

## Related Concepts (forward links)

- Route 53 DNS, including hybrid DNS resolution patterns -> Part 4, Section 6
- VPC Flow Logs for observing hybrid connection traffic -> Part 4, Section 9
- Migration strategies and the 6 Rs, where hybrid connectivity is foundational -> Part 10
