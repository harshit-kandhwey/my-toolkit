# Section 95 (Part 11): Site-to-Site VPNs and Cloud Gateway Patterns

## 1. Definition

**Plain language:** A site-to-site VPN doesn't connect one person to a network — it connects two entire networks to each other, permanently, so that any host on one side can reach any authorized host on the other side without any individual device needing its own VPN client. This is the pattern behind connecting an on-prem data center to a cloud VPC, or linking two cloud regions together across providers.

**Precise definition:** A **site-to-site VPN** is a persistent tunnel between two **gateways** — not individual hosts — where each gateway sits at the edge of its own private network and transparently routes traffic destined for the other side's private address range through the tunnel. Hosts behind either gateway need no VPN software or awareness that a tunnel exists at all; from their perspective, the remote private network is simply another reachable set of routes. This pattern is almost always built on IPsec ([§92](Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md)), sometimes on WireGuard ([§94](Section-94-Part11-WireGuard-Design-Philosophy-and-Key-Concepts.md)) for simpler or more performance-sensitive deployments, and is exposed by every major cloud provider as a **managed VPN gateway service** — AWS Site-to-Site VPN (paired with a **Virtual Private Gateway** or **Transit Gateway** attachment), Azure **VPN Gateway**, and GCP **Cloud VPN** — each of which handles the IPsec/IKE negotiation, redundancy, and public-IP endpoint management as a managed service, exposing configuration through the provider's console/API/Terraform rather than raw `strongswan` config files. A critical architectural refinement is **dynamic vs. static routing**: a **static** site-to-site VPN uses fixed, manually-configured route entries (or IPsec traffic selectors) defining exactly which CIDRs traverse the tunnel, while a **dynamic** (BGP-based) VPN runs BGP ([§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)) over the tunnel itself, letting each side advertise and withdraw routes automatically — the latter is the standard modern pattern for any site-to-site VPN expected to support redundant tunnels or route changes without manual reconfiguration.

> 💡 **Tip:** Cloud provider site-to-site VPN products typically provision **two tunnels per connection by default** specifically for redundancy (e.g., AWS Site-to-Site VPN always creates two tunnels to two different public IPs on the AWS side) — treating only one of the two as "the real one" and ignoring the second is a common oversight that quietly discards the redundancy the service was designed to provide.

## 2. Why This Matters

- **Site-to-site VPNs are the standard, default way to connect on-prem infrastructure to a cloud VPC**, or to connect separate cloud environments (different accounts, regions, or even providers) that need private network-layer reachability without traversing the public internet unencrypted.
- **Every cloud provider's site-to-site VPN product is a routine, high-frequency configuration task** for cloud and platform engineers doing hybrid-cloud or multi-cloud work, and misconfiguring it (mismatched CIDRs, wrong ASN for BGP, missing redundant tunnel) is a common source of hybrid-connectivity incidents.
- **The static vs. dynamic (BGP) routing decision has direct, material availability consequences** — a static configuration requires manual intervention to fail over between redundant tunnels, while a properly configured BGP-based VPN fails over automatically within seconds of a tunnel going down.
- **Site-to-site VPN throughput and latency directly affect application architecture decisions** made on top of it — a database replication job, backup transfer, or synchronous cross-site application dependency all need to be sized and designed against the real throughput ceiling a VPN tunnel provides, which is meaningfully lower than a dedicated interconnect like AWS Direct Connect or Azure ExpressRoute.
- **This pattern is a common systems-design and troubleshooting interview topic** precisely because it combines routing, cryptography, and cloud-specific product knowledge into one realistic scenario.

## 3. Prerequisites and Dependencies

This section directly applies the IPsec mechanics from [§92](Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md) and the WireGuard alternative from [§94](Section-94-Part11-WireGuard-Design-Philosophy-and-Key-Concepts.md) to a specific, common deployment pattern, and assumes both as background. It also assumes BGP concepts from [§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md), since dynamic routing over site-to-site VPN tunnels is the production-grade standard this section recommends, and static routing basics from [§26](../Part4/Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md). Familiarity with private addressing and CIDR planning ([§16](../Part3/Section-16-Part3-Subnet-Masks-and-CIDR-Notation.md)–[§19](../Part3/Section-19-Part3-Private-vs-Public-IP-Ranges-RFC-1918.md)) is important context, since overlapping private CIDR ranges between the two sites being connected is one of the most common blocking issues encountered when designing a site-to-site VPN. This section is deployment-pattern-focused; [§96](Section-96-Part11-Client-to-Site-Remote-Access-VPN-Patterns.md) immediately following covers the individual-user counterpart to this gateway-to-gateway pattern.

## 4. Architecture / Conceptual Diagram

```text
   On-Prem Data Center                              Cloud VPC (e.g., AWS/Azure/GCP)
   10.0.0.0/16                                       172.16.0.0/16

   ┌───────────────────┐         Tunnel 1           ┌───────────────────┐
   │  Customer Gateway  │◄──────────────────────────►│  Managed VPN       │
   │  (on-prem router/  │         Tunnel 2           │  Gateway            │
   │   firewall,        │◄──────────────────────────►│  (redundant public  │
   │   public IP)       │  (two tunnels for           │   endpoints)        │
   └─────────┬──────────┘   redundancy — both use     └─────────┬──────────┘
             │               IPsec/IKEv2, and BGP               │
             │               runs over each for                 │
             │               automatic failover)                 │
             ▼                                                   ▼
   Hosts on 10.0.0.0/16                              Hosts on 172.16.0.0/16
   (no VPN awareness —                                (no VPN awareness —
    routes to 172.16.0.0/16                            routes to 10.0.0.0/16
    exist via the gateway)                              exist via the gateway)
```

- **Both tunnels are active simultaneously in a well-configured BGP-based deployment**, not one primary and one idle standby — BGP path selection (often influenced by AS-path prepending or local preference) determines which tunnel actually carries traffic in normal operation, and the other takes over automatically if BGP detects the primary path failed.
- **The "Customer Gateway" and "managed VPN Gateway" are the IPsec peers from [§92](Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md)'s terminology** — the cloud side is simply a managed implementation of the same IKE/ESP mechanics, abstracted behind the provider's console and API.
- **No individual host on either side runs any VPN software** — the entire tunnel is transparent to them; this is the defining structural difference from the client-to-site pattern in [§96](Section-96-Part11-Client-to-Site-Remote-Access-VPN-Patterns.md), where each end-user device is itself a tunnel endpoint.

## 5. Hands-On

### 5.1 Provisioning an AWS Site-to-Site VPN Connection (Conceptual CLI Walkthrough)

**Purpose:** Understand the sequence of cloud resources a managed site-to-site VPN gateway service requires, using AWS as a representative example of the pattern shared conceptually across providers.

**Syntax:**

```bash
aws ec2 create-customer-gateway --type ipsec.1 --public-ip <on-prem-public-ip> --bgp-asn <on-prem-asn>
aws ec2 create-vpn-gateway --type ipsec.1
aws ec2 create-vpn-connection --type ipsec.1 --customer-gateway-id <cgw-id> --vpn-gateway-id <vgw-id> --options StaticRoutesOnly=false
```

**Example usage and expected output:**

```bash
$ aws ec2 create-customer-gateway --type ipsec.1 --public-ip 203.0.113.5 --bgp-asn 65000
{
    "CustomerGateway": {
        "CustomerGatewayId": "cgw-0abc123",
        "State": "available",
        "BgpAsn": "65000"
    }
}

$ aws ec2 create-vpn-connection --type ipsec.1 --customer-gateway-id cgw-0abc123 --vpn-gateway-id vgw-0def456 --options StaticRoutesOnly=false
{
    "VpnConnection": {
        "VpnConnectionId": "vpn-0ghi789",
        "State": "pending",
        "VgwTelemetry": [
            {"OutsideIpAddress": "52.1.2.3", "Status": "DOWN"},
            {"OutsideIpAddress": "52.4.5.6", "Status": "DOWN"}
        ]
    }
}
```

- `--options StaticRoutesOnly=false` explicitly requests BGP-based dynamic routing rather than static traffic selectors — this single flag is the difference between the "manual failover" and "automatic failover" architectures discussed above.
- Two `OutsideIpAddress` entries confirm the redundant two-tunnel design mentioned in this section's Tip — both need matching on-prem-side configuration (IKE and BGP peering) to actually achieve the intended redundancy.
- `Status: DOWN` for both tunnels immediately after creation is expected — the on-prem customer gateway (strongSwan, a hardware firewall, or equivalent) still needs its own matching IKE/BGP configuration applied before either tunnel comes up.

**Production usage example:** This exact resource sequence (customer gateway → VPN gateway → VPN connection) is what Terraform's `aws_customer_gateway`/`aws_vpn_gateway`/`aws_vpn_connection` resources provision under the hood — infrastructure-as-code is the standard way this is deployed and version-controlled in production rather than manual console clicks.

**Common errors:** Configuring the on-prem side with a mismatched BGP ASN or IKE pre-shared key relative to what was specified when creating the cloud-side resources — both tunnels will show `DOWN` indefinitely with no cloud-side error beyond the generic down status, requiring a check of the on-prem gateway's own IKE/BGP logs to find the actual mismatch.

### 5.2 Verifying Tunnel and BGP Session State

**Purpose:** Confirm both redundant tunnels are actually up and that BGP is exchanging routes correctly, not just that the tunnel connection resource exists.

**Syntax:**

```bash
aws ec2 describe-vpn-connections --vpn-connection-ids <vpn-connection-id> --query "VpnConnections[0].VgwTelemetry"
```

**Example usage and expected output:**

```bash
$ aws ec2 describe-vpn-connections --vpn-connection-ids vpn-0ghi789 --query "VpnConnections[0].VgwTelemetry"
[
    {"OutsideIpAddress": "52.1.2.3", "Status": "UP", "StatusMessage": "1 BGP ROUTES", "AcceptedRouteCount": 1},
    {"OutsideIpAddress": "52.4.5.6", "Status": "UP", "StatusMessage": "1 BGP ROUTES", "AcceptedRouteCount": 1}
]
```

- Both tunnels showing `Status: UP` with a non-zero `AcceptedRouteCount` confirms both the IPsec/IKE layer and the BGP layer above it are functioning correctly — a tunnel can show `UP` at the IKE level while still showing zero accepted BGP routes if BGP peering itself has a separate misconfiguration.
- This distinction — IPsec tunnel state vs. BGP session state — mirrors the same "distinguish which layer is failing" diagnostic principle from [§92](Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md)'s Phase 1/Phase 2 troubleshooting.

**Production usage example:** Automated monitoring for hybrid-connectivity health commonly polls exactly this API (or the equivalent in Azure/GCP) on a schedule, alerting if either redundant tunnel goes down or if accepted route counts drop to zero, since either condition threatens availability even while the other tunnel may still be functioning.

**Common errors:** Treating "at least one tunnel is up" as fully healthy without alerting — this masks a real, ongoing redundancy loss that will become a full outage if the second tunnel also fails before the first is repaired.

## 6. Production Usage Notes

- **Overlapping private CIDR ranges between the two sites being connected is a common, sometimes late-discovered blocker** — if both the on-prem network and the cloud VPC use, for example, `10.0.0.0/16`, no amount of correct IPsec/BGP configuration resolves the fundamental routing ambiguity; this must be caught during design, not after tunnel setup.
- **BGP-based dynamic routing is the strongly preferred pattern for any production site-to-site VPN**, since it enables automatic failover between redundant tunnels and automatic propagation of route changes (new subnets added on either side) without manual route-table edits on both sides.
- **Bandwidth ceilings on managed VPN gateway services are real and often lower than expected** (frequently limited to roughly 1–1.5 Gbps per tunnel depending on provider) — for higher-throughput hybrid connectivity needs, a dedicated interconnect (AWS Direct Connect, Azure ExpressRoute, GCP Cloud Interconnect — covered conceptually in Part 12) is the appropriate alternative or complement, not a differently-tuned VPN.

## 7. Security Considerations

- **The on-prem customer gateway's public IP and pre-shared key/certificate are the trust anchors for the entire tunnel** — the same credential-protection rigor from [§92](Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md)'s Security Considerations applies directly here.
- **A site-to-site VPN grants broad network-layer reachability between two entire private networks** by design — this makes proper security-group/NACL layering ([§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)) on both sides of the tunnel especially important, since the tunnel itself doesn't restrict what's reachable beyond the routes it carries.
- **BGP route advertisements over the tunnel should be filtered/scoped deliberately**, not accepted or advertised wholesale — accidentally advertising more of a private network's routes than intended over BGP can expose more internal reachability across the tunnel than the design called for.

## 8. Common Troubleshooting Scenarios

| Symptom                                                       | Likely Cause                                                                                 | Resolution Path                                                                                                    |
| ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Both tunnels show DOWN immediately after provisioning | On-prem customer gateway hasn't been configured with matching IKE parameters yet | Apply the corresponding IKE configuration on the on-prem device, matching PSK/ASN/algorithms exactly |
| Tunnel shows UP but zero BGP routes accepted | BGP peering misconfigured (wrong ASN, route filters blocking advertisements) separately from the IKE/tunnel layer | Check BGP session state and route-filter policy independently of tunnel/IKE status |
| Only one of two redundant tunnels ever shows traffic | Local preference/AS-path BGP attributes on the on-prem side favor one tunnel over the other (expected) or the second tunnel's BGP session is actually down (not expected) | Confirm whether asymmetric preference is intentional (fine) or the second BGP session is genuinely failing (needs investigation) |
| Hosts on one side cannot reach hosts on the other despite tunnel/BGP being healthy | Overlapping private CIDR ranges, or a security group/NACL on one side blocking the traffic independently of the VPN | Check for CIDR overlap during design; verify security group/NACL rules explicitly allow the remote CIDR |

## 9. Best Practices

- Always provision and validate both redundant tunnels a managed VPN gateway service creates, and monitor both tunnels' status and accepted route counts continuously, not just at initial setup.
- Use BGP-based dynamic routing as the default for any production site-to-site VPN rather than static traffic selectors, specifically for automatic failover behavior.
- Plan private CIDR allocation across all sites/environments that may eventually need site-to-site connectivity as an explicit, upfront design step, to avoid discovering overlapping ranges only after a connectivity requirement arises.

## 10. Common Anti-Patterns / Mistakes

- **Treating a managed cloud VPN gateway's default redundant-tunnel setup as optional and only configuring one side** — this silently discards the availability guarantee the service was specifically designed to provide.
- **Choosing static routing for a production site-to-site VPN "to keep it simple"**, then discovering during an actual tunnel failure that failover requires manual route changes rather than happening automatically.
- **Designing private CIDR ranges for each new environment independently, without a shared allocation plan**, leading to overlap discoveries only once a site-to-site connectivity requirement surfaces late in a project.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a site-to-site VPN and a client-to-site VPN?"_
**Model answer:** A site-to-site VPN connects two entire private networks via gateways at each side, transparently to the individual hosts behind them, so no client software is needed on any individual machine. A client-to-site (remote-access) VPN connects an individual device directly to a private network, with that device running its own VPN client software as one endpoint of the tunnel.
_What the interviewer is probing for:_ A clear structural distinction between the two most common VPN deployment patterns, since they're frequently confused or used loosely as synonyms.

**🎯 Intermediate:** _"Why would you choose BGP-based dynamic routing over static routing for a site-to-site VPN?"_
**Model answer:** BGP-based dynamic routing enables automatic failover between redundant tunnels — if one tunnel's BGP session goes down, routes learned over it are automatically withdrawn and traffic shifts to the surviving tunnel within seconds, with no manual intervention. Static routing requires either pre-configuring both tunnels' routes with specific priority/preference (limited flexibility) or manually updating routes if a tunnel fails, which is slower and error-prone. BGP also automatically propagates new subnet advertisements from either side without requiring manual route-table updates on both ends.
_What the interviewer is probing for:_ Whether the candidate understands the operational, not just theoretical, value of dynamic routing for availability.

**🎯 Senior:** _"A site-to-site VPN connection shows both tunnels as UP, but application traffic between the two sites is completely failing. What's your diagnostic sequence?"_
**Model answer:** Since both tunnels show UP at the IKE/IPsec layer, I'd first check BGP session state and accepted route counts on both tunnels, since a tunnel can be cryptographically established while its BGP peering (a separate layer) has failed or is filtering out the needed routes, resulting in zero effective reachability despite a healthy tunnel. If BGP routes are being exchanged correctly, I'd next check for overlapping private CIDR ranges between the two sites, since that produces exactly this "tunnel healthy, nothing reachable" symptom. Finally, I'd check security groups/NACLs on both sides independently, since the VPN tunnel only provides the path — it doesn't override security-group-level traffic filtering on either end.
_What the interviewer is probing for:_ Systematic, layer-by-layer troubleshooting instinct rather than assuming "the VPN" is a single monolithic thing to check once.

**🎯 Architect:** _"Design hybrid connectivity between an on-prem data center and a multi-region cloud deployment, considering both cost and availability."_
**Model answer:** For initial or lower-throughput connectivity needs, I'd start with redundant, BGP-based site-to-site VPN tunnels to each cloud region, since this requires no physical circuit provisioning lead time and gives reasonable availability through the redundant-tunnel-plus-BGP-failover pattern. For higher-throughput or latency-sensitive production traffic, I'd add a dedicated interconnect (AWS Direct Connect/Azure ExpressRoute/GCP Cloud Interconnect, covered conceptually in Part 12) as the primary path, with the site-to-site VPN retained as an automatic BGP-based failover path if the dedicated circuit fails — a very common hybrid pattern that gets both the throughput of a dedicated connection and the resilience of a VPN as backup. I'd plan private CIDR allocation across every region and the on-prem network upfront to avoid overlap, and monitor both the dedicated circuit and VPN tunnel health continuously so a silent single-path failure doesn't go unnoticed.
_What the interviewer is probing for:_ Ability to combine site-to-site VPN with other hybrid connectivity options (rather than treating VPN as the only tool) and reason about cost/throughput/availability trade-offs at an architectural level.

## 12. Common Misconceptions

1. **"A site-to-site VPN requires VPN client software on every host that needs to communicate across it."** The entire point of the pattern is that individual hosts need no VPN awareness at all — only the two gateways are tunnel endpoints.
2. **"Both redundant tunnels from a managed cloud VPN gateway are automatically configured and working without any on-prem-side setup."** The cloud side is only half the equation — the on-prem customer gateway needs matching IKE and (for dynamic routing) BGP configuration applied independently before either tunnel comes up.
3. **"If the VPN tunnel is up, connectivity between the two sites should just work."** Tunnel/IKE health, BGP route exchange, CIDR overlap, and security-group/NACL rules are all independent layers that must each be correct — a healthy tunnel is necessary but not sufficient for end-to-end reachability.
4. **"Site-to-site VPN and a dedicated interconnect (Direct Connect/ExpressRoute) solve the same problem, so only one is needed."** They're complementary — VPN is faster to provision and often used as a backup path, while a dedicated interconnect provides higher, more consistent throughput; many production hybrid architectures use both together.

## 13. 🔑 Key Takeaways

- A site-to-site VPN connects two entire private networks via gateways, transparently to individual hosts — this is its defining structural difference from client-to-site VPN.
- Cloud provider managed VPN gateway services provision redundant tunnel pairs by default; both must be configured and monitored, not just one.
- BGP-based dynamic routing is the production standard for site-to-site VPN specifically because it enables automatic failover, unlike static routing.
- Overlapping private CIDR ranges between connected sites is a design-time problem that no amount of correct tunnel/BGP configuration can fix after the fact.
- A site-to-site VPN provides the path, not the access control — security groups/NACLs on both sides still fully apply to traffic crossing the tunnel.

## 14. Related Concepts & What's Next

This section applies [§92](Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md)'s IPsec mechanics and [§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)'s BGP concepts to a concrete deployment pattern, and connects forward to the cloud VPC networking concepts in Part 12 ([§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md)–[§109](../Part12/Section-109-Part12-Cross-Reference-Where-AWS-Azure-GCP-Specific-Networking-Continues-in-This-Repo.md)), where hub-and-spoke and hybrid connectivity patterns like Direct Connect/ExpressRoute/Cloud Interconnect are covered in their own right. [§96](Section-96-Part11-Client-to-Site-Remote-Access-VPN-Patterns.md) immediately following covers the individual-user counterpart to this gateway-to-gateway pattern, and the security-group/NACL layering this section relies on connects back to [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) in Part 10.

**Next Section:** [§96](Section-96-Part11-Client-to-Site-Remote-Access-VPN-Patterns.md) — `Section-96-Part11-Client-to-Site-Remote-Access-VPN-Patterns.md`
