# Section 106 (Part 12): Hybrid Connectivity: Direct Connect, ExpressRoute, Cloud Interconnect — Conceptual

## 1. Definition

**Plain language:** Most organizations don't run entirely in the cloud — they have existing data centers, offices, or co-location facilities that need reliable, high-bandwidth, private connectivity into their cloud VPC/VNet. Every major provider offers a dedicated physical (or partner-mediated) network connection product for exactly this, as an alternative to routing that traffic over a VPN across the public internet.

**Precise definition:** **AWS Direct Connect**, **Azure ExpressRoute**, and **GCP Cloud Interconnect** are each a dedicated, private, physical (or partner-provisioned virtual) network connection between an organization's on-premises infrastructure and the provider's cloud network, bypassing the public internet entirely for that traffic — unlike a site-to-site VPN ([§95](../Part11/Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md)), which is an encrypted tunnel that still traverses the public internet. All three products offer both a **dedicated** connection type (a physical cross-connect at a specific provider-designated facility, requiring the most setup effort and offering the highest, most consistent bandwidth and lowest latency) and a **hosted/partner** connection type (provisioned through a telecom or network partner that already has infrastructure at the provider's facility, offering faster setup at typically lower bandwidth tiers). These are the "hard-wired" tier of hybrid connectivity, sitting above VPN-based hybrid connectivity in cost, setup complexity, and performance consistency, and are the standard choice once bandwidth, latency consistency, or the specific compliance requirement to avoid the public internet altogether make a VPN insufficient.

> 💡 **Tip:** This section is deliberately conceptual, matching this Part's stated scope — provider-specific ordering procedures, exact partner lists, and pricing tiers for these products live in this repo's dedicated AWS, Azure, and GCP knowledge base tracks, not here. The goal is to recognize when hybrid connectivity is the right category of solution at all, and to map these three product names onto the same underlying concept fluently.

## 2. Why This Matters

- **Choosing between a VPN and a dedicated hybrid connection is a genuine, high-stakes architecture decision** — a VPN over the public internet, however well encrypted, cannot offer the consistent low latency and guaranteed bandwidth a dedicated connection can, which matters directly for latency-sensitive or very high-throughput hybrid workloads.
- **These products are foundational to any enterprise hybrid-cloud or cloud-migration strategy** — an organization migrating workloads to the cloud incrementally, while keeping some infrastructure on-premises indefinitely, almost always needs one of these products at some point.
- **This is a standard attachment point for the hub architectures covered in [§104](Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md)** — connecting a dedicated on-premises link once to a Transit Gateway/Virtual WAN hub, rather than to every individual VPC/VNet, is the standard production pattern for sharing hybrid connectivity across an entire cloud estate.
- **Certification tracks and real interviews test the ability to reason about when a VPN is sufficient versus when dedicated connectivity is required** — this is a recurring, practically important judgment call in enterprise network design.
- **The cost model differs meaningfully from a VPN** — dedicated connections involve provisioning lead time (sometimes weeks) and often a fixed monthly port/circuit cost independent of usage, versus a VPN's near-instant provisioning and usage-based cost, a trade-off worth understanding before committing to either.

## 3. Prerequisites and Dependencies

This section assumes the VPC/VNet and route table concepts from [§100](Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md) and [§101](Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md), since a hybrid connection ultimately terminates as another routable path in the cloud network's routing configuration. It draws a direct contrast with site-to-site VPN connectivity, covered in this roadmap's Part 11 as [§95](../Part11/Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md) (Site-to-Site VPNs and Cloud Gateway Patterns) — understanding that section's VPN-over-public-internet model is what makes this section's "dedicated, non-internet-routed" distinction meaningful by contrast. It also connects forward to [§104](Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md)'s hub architectures, since a dedicated hybrid connection is commonly attached at the hub level to be shared across many spoke VPCs/VNets.

## 4. Architecture / Conceptual Diagram

```text
   ON-PREMISES DATA CENTER

        │
        ├── OPTION 1: Site-to-Site VPN (§95, Part 11)
        │   ┌────────────────────────────────────┐
        │   │ Encrypted tunnel over the PUBLIC     │
        │   │ INTERNET — fast to provision, usage- │
        │   │ based cost, variable latency/         │
        │   │ bandwidth subject to internet         │
        │   │ conditions                            │
        │   └────────────────────────────────────┘
        │                     │
        │                     ▼
        │              Cloud VPC/VNet
        │
        └── OPTION 2: Dedicated Hybrid Connection (this section)
            ┌────────────────────────────────────┐
            │ AWS Direct Connect /                 │
            │ Azure ExpressRoute /                 │
            │ GCP Cloud Interconnect               │
            │                                       │
            │ Dedicated physical cross-connect OR   │
            │ partner-provisioned virtual circuit   │
            │ — bypasses the public internet         │
            │   entirely — consistent latency,       │
            │   guaranteed bandwidth, higher cost     │
            │   and setup lead time                   │
            └───────────────────┬──────────────────┘
                                 ▼
                          Cloud VPC/VNet
                     (often via a Transit Gateway/
                      Virtual WAN hub, §104, shared
                      across many spoke VPCs/VNets)
```

- Both options terminate at the same logical point — the cloud VPC/VNet's routing configuration — but differ entirely in the physical/logical path traffic takes to get there and in their cost/performance/provisioning trade-offs.
- Many production designs run **both simultaneously**: a dedicated connection as the primary path for its performance and privacy characteristics, with a site-to-site VPN configured as an automatic failover if the dedicated connection experiences an outage — treating the VPN as the redundancy layer for the higher-performance primary path.
- Attaching the dedicated connection at a hub ([§104](Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md)) rather than to each individual VPC/VNet is the standard way to share one physical/logical connection's cost and capacity across an entire multi-VPC/VNet estate.

## 5. Hands-On

### 5.1 Creating an AWS Direct Connect Virtual Interface (Conceptual)

**Purpose:** Show the conceptual API shape of attaching an already-provisioned Direct Connect physical connection to a VPC via a virtual interface — the actual physical cross-connect provisioning happens outside the API, through AWS or a partner.

**Syntax:**

```bash
aws directconnect create-private-virtual-interface \
  --connection-id <dx-connection-id> \
  --new-private-virtual-interface '{"virtualInterfaceName":"<name>","vlan":<vlan-id>,"asn":<customer-asn>,"virtualGatewayId":"<vgw-id>"}'
```

**Example usage and expected output:**

```bash
$ aws directconnect create-private-virtual-interface --connection-id dxcon-fabcdef12 \
    --new-private-virtual-interface '{"virtualInterfaceName":"prod-dx-vif","vlan":100,"asn":65000,"virtualGatewayId":"vgw-0abc123"}'
{
    "virtualInterfaceId": "dxvif-0abc123def456",
    "virtualInterfaceState": "pending",
    "vlan": 100,
    "asn": 65000
}
```

- The `asn` field reflects that Direct Connect virtual interfaces use **BGP** ([§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)) to dynamically exchange routes between the on-premises network and the VPC, rather than requiring static route configuration on both sides.

**Production usage example:** This exact pattern — a private virtual interface attached to a Virtual Private Gateway or, more commonly in modern designs, a Transit Gateway — is standard for connecting an on-premises data center's BGP-speaking router to an AWS VPC over a pre-provisioned dedicated or hosted Direct Connect connection.

**Common errors:** Attempting to create a virtual interface before the underlying physical Direct Connect connection has actually been provisioned and activated (a process that happens outside this API and can take days to weeks for a dedicated connection) results in the interface remaining in a non-functional state indefinitely.

### 5.2 Creating an Azure ExpressRoute Circuit (Conceptual)

**Purpose:** Show the equivalent Azure resource-creation step, highlighting Azure's explicit choice of connectivity provider and SKU tier at circuit-creation time.

**Syntax:**

```bash
az network express-route create \
  --name <circuit-name> \
  --resource-group <resource-group> \
  --provider <connectivity-provider> \
  --peering-location <location> \
  --bandwidth <mbps> \
  --sku-family MeteredData \
  --sku-tier Standard
```

**Example usage and expected output:**

```bash
$ az network express-route create --name prod-expressroute --resource-group prod-rg \
    --provider "Equinix" --peering-location "Washington DC" --bandwidth 1000 \
    --sku-family MeteredData --sku-tier Standard
{
  "name": "prod-expressroute",
  "serviceProviderProvisioningState": "NotProvisioned",
  "circuitProvisioningState": "Enabled"
}
```

- `"serviceProviderProvisioningState": "NotProvisioned"` reflects the same reality as AWS's pending virtual interface state — creating the Azure-side circuit object is only half of the process; the connectivity provider (here, Equinix) must separately complete their own provisioning before the circuit is actually usable.

**Production usage example:** ExpressRoute circuits provisioned through a well-known connectivity provider at a major peering location are standard for enterprises with existing co-location or network-provider relationships already established at that location.

**Common errors:** Selecting a `--peering-location` where the organization's chosen connectivity provider has no physical presence causes the circuit to remain stuck in `NotProvisioned`, since the physical prerequisite for the entire connection doesn't exist at that location.

### 5.3 Checking GCP Cloud Interconnect Attachment Status

**Purpose:** Show the diagnostic-oriented command used to confirm whether a Cloud Interconnect attachment is actually passing traffic, since (as with the previous two providers) resource creation and full operational readiness are distinct states.

**Syntax:**

```bash
gcloud compute interconnects attachments describe <attachment-name> --region=<region>
```

**Example usage and expected output:**

```bash
$ gcloud compute interconnects attachments describe prod-interconnect-attachment --region=us-east1
name: prod-interconnect-attachment
state: ACTIVE
bandwidth: BPS_1G
cloudRouterIpAddress: 169.254.0.1/29
customerRouterIpAddress: 169.254.0.2/29
```

- `state: ACTIVE` together with both BGP peer IP addresses populated confirms the attachment has completed provisioning on both the GCP and on-premises router sides — a `state` of anything else (e.g., `PENDING_PARTNER`) means the connection is not yet usable, mirroring the "pending" states seen in the AWS and Azure examples above.

**Production usage example:** This describe command is the standard first diagnostic step when on-premises-to-GCP connectivity over Cloud Interconnect isn't working, confirming whether the issue is the attachment itself (not yet active) or something further along the path (BGP session, firewall, routing).

**Common errors:** Assuming a Cloud Interconnect attachment is fully operational as soon as it's created in the GCP console/API, without checking that the partner or physical cross-connect side has also completed provisioning — exactly the same category of "half-provisioned" trap seen in the AWS and Azure examples.

## 6. Production Usage Notes

- **Provisioning lead time is a major planning consideration** — a dedicated cross-connect can take weeks to establish depending on facility and provider logistics, in sharp contrast to a site-to-site VPN's near-instant setup ([§95](../Part11/Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md)) — this lead time should be factored into any migration timeline that depends on dedicated connectivity being in place.
- **Redundancy is typically achieved with two dedicated connections at physically diverse locations**, not one — a single dedicated connection, however reliable, is still a single physical path with a non-zero failure probability, and enterprise designs commonly pair it with either a second dedicated connection or a VPN failover path.
- **BGP is the standard routing protocol across all three providers' dedicated connection products** — reflecting the same path-vector routing concepts from [§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md), applied here to dynamically exchange on-premises and cloud routes rather than relying on static routes that would need manual updates as either side's network changes.

## 7. Security Considerations

- Dedicated hybrid connections bypass the public internet, but this alone doesn't guarantee encryption — many organizations layer an additional encryption mechanism (such as MACsec at the link layer, or application/transport-layer TLS) on top of the dedicated connection for defense in depth, rather than relying solely on physical path privacy.
- The connectivity provider (in a hosted/partner connection) is a trust boundary worth explicitly considering — the traffic passes through infrastructure operated by that partner, which is a different trust model than a fully dedicated, direct physical cross-connect.
- Route advertisement over BGP on a hybrid connection should be scoped carefully — advertising overly broad on-premises or cloud routes across the connection can expose more of either network than intended, echoing the same least-privilege discipline emphasized for hub route tables in [§104](Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md).

## 8. Common Troubleshooting Scenarios

| Symptom | Likely Cause | Resolution Path |
| --- | --- | --- |
| Virtual interface/circuit/attachment created but no traffic passes | Underlying physical connection or partner-side provisioning not yet complete | Check the connection's provisioning state specifically (not just the logical resource's existence) and confirm with the connectivity provider/facility |
| BGP session between on-premises and cloud router won't establish | Mismatched ASN, incorrect BGP peer IP configuration, or a firewall blocking BGP (TCP 179) between the routers | Verify ASN and peer IP configuration on both sides and confirm BGP traffic isn't being blocked |
| Hybrid connection works but only a subset of expected on-premises routes are reachable | Route advertisement over BGP intentionally or accidentally scoped too narrowly | Review and correct the BGP route advertisement/filter configuration on the on-premises or cloud-side router |
| Primary dedicated connection outage causes a full hybrid connectivity outage | No VPN or secondary dedicated connection configured as a failover path | Provision a site-to-site VPN ([§95](../Part11/Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md)) or a second physically diverse dedicated connection as redundancy |

## 9. Best Practices

- Plan for dedicated connectivity provisioning lead time explicitly in project timelines, rather than assuming it can be stood up as quickly as a VPN.
- Pair a dedicated connection with a site-to-site VPN ([§95](../Part11/Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md)) as an automatic failover path, rather than treating the dedicated connection as a single point of failure for hybrid connectivity.
- Attach shared hybrid connectivity at a hub ([§104](Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md)) rather than provisioning a separate dedicated connection per VPC/VNet, for both cost efficiency and centralized route management.

## 10. Common Anti-Patterns / Mistakes

- **Assuming a dedicated hybrid connection is automatically encrypted because it bypasses the public internet.** Physical path privacy and encryption are separate properties; many designs still layer explicit encryption on top for defense in depth.
- **Relying on a single dedicated connection with no VPN or secondary connection as a failover path.** A dedicated connection is still a single physical path subject to outages.
- **Treating resource creation (virtual interface, circuit, attachment) as equivalent to the connection being operational**, without verifying the underlying physical/partner-side provisioning has also completed.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a site-to-site VPN and AWS Direct Connect (or Azure ExpressRoute/GCP Cloud Interconnect)?"_
**Model answer:** A site-to-site VPN creates an encrypted tunnel between on-premises infrastructure and the cloud, but that tunnel still travels over the public internet, meaning its latency and available bandwidth depend on general internet conditions. Direct Connect, ExpressRoute, and Cloud Interconnect are dedicated, private connections — either a physical cross-connect or a partner-provisioned circuit — that bypass the public internet entirely, offering more consistent latency and guaranteed bandwidth, at the cost of higher price and longer setup time.
_What the interviewer is probing for:_ Clear understanding that the defining difference is "still uses the public internet" vs. "bypasses it entirely," not merely "one is a VPN and one isn't."

**🎯 Intermediate:** _"Why would an organization use BGP over a Direct Connect/ExpressRoute/Cloud Interconnect connection instead of static routes?"_
**Model answer:** BGP allows the on-premises and cloud routers to dynamically exchange and update reachability information as either network's topology changes, without requiring a manual route update on both sides every time a subnet is added, removed, or changed. This also enables automatic failover behavior — if a redundant path exists (a second dedicated connection or a VPN), BGP can dynamically withdraw and re-advertise routes as connections go up or down, something static routing would require manual intervention to replicate.
_What the interviewer is probing for:_ Connecting the choice of BGP specifically to the dynamic-routing benefits from [§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md), rather than treating it as an arbitrary protocol requirement.

**🎯 Senior:** _"A finance team complains that a newly provisioned Direct Connect connection is taking six weeks to become active, and asks whether this can be avoided. How do you respond?"_
**Model answer:** Provisioning lead time is inherent to dedicated physical connectivity — establishing a physical cross-connect at a specific facility (or coordinating with a hosted connectivity partner) genuinely takes real-world logistics time that a purely software-defined connection like a VPN doesn't require. I'd explain that this lead time should be planned for explicitly in any project timeline that depends on the dedicated connection, and in the interim, I'd recommend standing up a site-to-site VPN ([§95](../Part11/Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md)) immediately as a bridge — it can typically be provisioned within hours, giving the team working hybrid connectivity right away, with a planned cutover (or permanent coexistence as a failover path) once the Direct Connect connection completes provisioning.
_What the interviewer is probing for:_ Practical project-management awareness of the real-world provisioning constraint, plus the specific, actionable mitigation (a VPN bridge) rather than simply explaining why the delay exists.

**🎯 Architect:** _"Design the hybrid connectivity strategy for a large enterprise with three on-premises data centers, an expectation of very high-bandwidth, latency-sensitive data replication to the cloud, and a requirement for no single point of failure."_
**Model answer:** I'd provision dedicated connections (Direct Connect/ExpressRoute/Cloud Interconnect depending on the provider) at physically diverse peering locations for at least two of the three data centers, explicitly avoiding using the same facility or the same connectivity partner for both, so that a single facility or partner outage doesn't take down all dedicated connectivity simultaneously. Each dedicated connection would run BGP for dynamic route exchange, and I'd configure route preferences so that traffic prefers the dedicated paths but automatically fails over to a site-to-site VPN ([§95](../Part11/Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md)) configured from each data center as a lower-priority backup path, giving redundancy even in a scenario where both dedicated connections are simultaneously unavailable. All of this connectivity would terminate at a central transit hub ([§104](Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md)) rather than being wired individually into every VPC/VNet, so that the redundancy and BGP route management is handled once, centrally, and every spoke VPC/VNet inherits it automatically. For the third data center, given cost constraints, I'd evaluate whether its actual bandwidth/latency requirements justify a third dedicated connection or whether a well-provisioned VPN is sufficient, rather than assuming every location automatically needs the same tier of connectivity.
_What the interviewer is probing for:_ The ability to design genuine redundancy (diverse facilities/partners, dedicated-plus-VPN failover, centralized hub attachment) rather than simply recommending "get Direct Connect" without addressing the explicit no-single-point-of-failure requirement, and the judgment to right-size connectivity per location rather than applying one template everywhere.

## 12. Common Misconceptions

1. **"Direct Connect/ExpressRoute/Cloud Interconnect traffic is automatically encrypted because it doesn't use the public internet."** Physical path privacy and encryption are separate properties; many designs add explicit encryption on top for defense in depth.
2. **"Creating the virtual interface/circuit/attachment resource means the connection is immediately operational."** The underlying physical cross-connect or partner-side provisioning is a separate step that must also complete, and can take significant time.
3. **"A dedicated hybrid connection removes the need for any VPN."** A VPN remains valuable as a fast-to-provision bridge during dedicated-connection setup and as an ongoing failover path for redundancy.
4. **"These three provider products are functionally identical beyond naming."** The core dedicated-connectivity concept is shared, but each has provider-specific SKU/tier structures, partner ecosystems, and provisioning workflows that a real deployment must account for in its own dedicated cloud-track documentation.

## 13. 🔑 Key Takeaways

- AWS Direct Connect, Azure ExpressRoute, and GCP Cloud Interconnect are the same underlying concept: a dedicated, non-public-internet-routed connection between on-premises infrastructure and a cloud VPC/VNet, contrasted directly with the public-internet-routed site-to-site VPN model covered in [§95](../Part11/Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md).
- All three use BGP ([§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)) for dynamic route exchange between on-premises and cloud routers.
- Dedicated connections offer more consistent latency and guaranteed bandwidth than a VPN, at the cost of higher price and meaningfully longer provisioning lead time.
- Encryption is not automatic on a dedicated connection and is often layered on top explicitly for defense in depth.
- Production designs typically pair a dedicated connection with a VPN as a failover path and attach shared hybrid connectivity at a transit hub ([§104](Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md)) rather than wiring it into every individual VPC/VNet.

## 14. Related Concepts & What's Next

This section contrasts directly with the site-to-site VPN model covered in [§95](../Part11/Section-95-Part11-Site-to-Site-VPNs-and-Cloud-Gateway-Patterns.md), and it commonly attaches to the transit hub architectures from [§104](Section-104-Part12-Hub-and-Spoke-and-Transit-Gateway-Hub-Architectures.md) for sharing across many spoke VPCs/VNets. Once traffic reaches the cloud network by any of these paths, [§107](Section-107-Part12-Cloud-DNS-and-Service-Discovery-Patterns.md) covers how resources — whether on-premises or cloud-native — actually locate each other by name across this connected environment.

**Next Section:** [§107](Section-107-Part12-Cloud-DNS-and-Service-Discovery-Patterns.md) — `Section-107-Part12-Cloud-DNS-and-Service-Discovery-Patterns.md`
