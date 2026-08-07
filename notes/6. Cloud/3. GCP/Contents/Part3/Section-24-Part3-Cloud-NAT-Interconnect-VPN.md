# Section 24 (Part 3): Cloud NAT, Cloud Interconnect & VPN

## 1. Definition

**Plain language:** These three services answer two very different connectivity questions. Cloud NAT lets private instances (with no public IP at all) reach out to the internet for things like software updates, without ever being reachable from the internet. Cloud Interconnect and Cloud VPN answer a different question: how do you connect your GCP VPC to a physical location you already have — an on-premises data center, a colocation facility, or another cloud — either over a dedicated private line (Interconnect) or an encrypted tunnel over the public internet (VPN).

**Precise:** **Cloud NAT** is a regional, distributed, managed Network Address Translation service providing **outbound-only** internet connectivity for resources without external IP addresses. **Cloud VPN** (in HA VPN or Classic VPN form) establishes **IPsec-encrypted tunnels** over the public internet between a GCP VPC and a peer network. **Cloud Interconnect** (Dedicated or Partner) establishes **private, non-internet Layer 2/3 connectivity** between a GCP VPC and an on-premises or colocated network via physical circuits, either directly with Google (Dedicated) or through a supported service provider (Partner).

## 2. Why It Exists / Problem It Solves

Private instances often need outbound internet access (OS patches, package repositories, calling external APIs) without being directly reachable from the internet — a bastion/NAT-instance-per-subnet approach is operationally heavy and doesn't scale or fail over automatically; Cloud NAT solves this as a fully managed, regional, highly available service requiring no instances to patch or manage. Separately, virtually every enterprise has existing on-premises infrastructure that must talk to the cloud — for data migration, hybrid application architectures, or gradual cloud adoption — and sending that traffic over the raw public internet is often unacceptable for latency, bandwidth guarantees, or security/compliance reasons. VPN and Interconnect solve this at two different price/reliability points: VPN is fast to provision and encrypted-by-default over existing internet connectivity; Interconnect is a dedicated physical/private path offering higher bandwidth and more predictable latency, at higher cost and longer lead time to provision.

## 3. Core Concepts

### 3.1 Cloud NAT

Cloud NAT is configured per-region, per-VPC (attached to a Cloud Router for the region), and applies to Compute Engine VMs and GKE nodes lacking an external IP. It is **outbound-only by design** — Cloud NAT never allows unsolicited inbound connections from the internet, only translating outbound connections initiated from inside the VPC and their return traffic. It is fully distributed (no single NAT gateway instance to become a bottleneck or single point of failure) and requires no manual patching, unlike a self-managed NAT instance/appliance.

### 3.2 Cloud VPN (Classic vs HA VPN)

**Classic VPN** offers a single tunnel with no SLA and is largely legacy/deprecated for new deployments. **HA VPN (High Availability VPN)** is the current standard: it provisions two interfaces on redundant Google infrastructure, each with its own external IP, giving a 99.99% availability SLA when configured with two tunnels to a peer device that also supports redundancy (or four tunnels for maximum redundancy against a single-peer-device setup). VPN traffic is IPsec-encrypted and travels over the public internet, using Cloud Router for dynamic BGP route exchange with the peer network.

### 3.3 Dedicated Interconnect

**Dedicated Interconnect** provisions a direct physical (Layer 1) connection between your network and Google's network at a Google-owned colocation facility, at 10 Gbps or 100 Gbps circuit increments. It requires you (or your presence via a colocation provider) to physically be in a facility where Google has a peering edge, and provides the highest bandwidth and lowest, most predictable latency of the three options, at higher cost and setup complexity/lead time.

### 3.4 Partner Interconnect

**Partner Interconnect** achieves similar private connectivity through a supported service provider, for organizations that aren't physically present in a Dedicated Interconnect colocation facility, or that need sub-10 Gbps increments. The service provider maintains the physical connection to Google on your behalf; you get a private, non-internet path without the physical colocation requirement of Dedicated Interconnect.

### 3.5 Cloud Router and BGP

**Cloud Router** is the shared control-plane component underlying both dynamic-routing VPN and Interconnect: it uses BGP to dynamically exchange routes between your VPC and the peer network, so route tables update automatically as subnets are added/removed, rather than requiring static route management on both sides.

## 4. Comparison Table

| Service                | Path                             | Encryption               | Direction     | Typical Bandwidth              | Setup Time       |
| ---------------------- | -------------------------------- | ------------------------ | ------------- | ------------------------------ | ---------------- |
| Cloud NAT              | Internet (via Google infra)      | N/A (not a hybrid link)  | Outbound-only | N/A (scales with instances)    | Minutes          |
| HA VPN                 | Public internet (IPsec tunnel)   | Encrypted (IPsec)        | Bidirectional | Up to ~3 Gbps per tunnel       | Minutes to hours |
| Partner Interconnect   | Private, via service provider    | Not encrypted by default | Bidirectional | 50 Mbps–50 Gbps                | Days to weeks    |
| Dedicated Interconnect | Private, direct physical circuit | Not encrypted by default | Bidirectional | 10 Gbps or 100 Gbps increments | Weeks to months  |

## 5. Architecture Diagram

```
                         PUBLIC INTERNET
                                │
      ┌─────────────────────────┼────────────────────────────┐
      │                         │                            │
      ▼                         ▼                            │
┌───────────┐          ┌────────────────┐                    │
│  VM (no   │          │  HA VPN        │                    │
│  external │◄─NAT─────┤  gateway       │◄──IPsec tunnels────┤ ON-PREM
│  IP)      │  (out-   │ (2 interfaces) │                    │ ROUTER
└───────────┘  bound)  └────────────────┘                    │
                                                             │
                        ┌────────────────┐  private circuit  │
                        │  Interconnect  │◄────(no internet)─┘
                        │  attachment    │
                        └────────────────┘
                                │
                        ┌────────────────┐
                        │  Cloud Router  │  (BGP route exchange,
                        │  (per region)  │   shared by VPN & Interconnect)
                        └────────────────┘
```

## 6. Comparison: GCP vs AWS vs Azure

| GCP                    | AWS Equivalent                      | Azure Equivalent                       | Notes                                                                                                                  |
| ---------------------- | ----------------------------------- | -------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Cloud NAT              | NAT Gateway                         | NAT Gateway (Virtual Network NAT)      | All three: managed, outbound-only, no instances to patch; GCP's is regional/distributed rather than AZ-pinned          |
| HA VPN                 | Site-to-Site VPN (with two tunnels) | VPN Gateway (active-active)            | Directly comparable IPsec-over-internet model; GCP's HA VPN 99.99% SLA requires the redundant two/four-tunnel topology |
| Dedicated Interconnect | Direct Connect                      | ExpressRoute                           | Directly comparable dedicated-physical-circuit model at similar bandwidth tiers                                        |
| Partner Interconnect   | Direct Connect via APN Partner      | ExpressRoute via connectivity provider | Same "no physical colocation required, provider-mediated" model across all three                                       |

> ⚠️ **Interview-relevant nuance:** Unlike AWS NAT Gateway (which is provisioned per-AZ and requires one per AZ for AZ-level HA), Cloud NAT is configured once per region per VPC and Google manages its internal distribution/redundancy — there's no "one NAT Gateway per zone" pattern to replicate in GCP the way there is in AWS.

## 7. Hands-On Examples

**Beginner — create a Cloud NAT gateway:**

```bash
gcloud compute routers nats create nat-config \
  --router=my-region-router \
  --region=us-central1 \
  --nat-all-subnet-ip-ranges \
  --auto-allocate-nat-external-ips
```

_Purpose:_ Configures Cloud NAT for all subnets in the region, letting private instances without external IPs reach the internet outbound, using auto-allocated NAT IPs.

**Expected output:**

```
Updated [https://www.googleapis.com/compute/v1/projects/my-project/regions/us-central1/routers/my-region-router].
```

**Intermediate — create an HA VPN gateway and tunnel:**

```bash
gcloud compute vpn-gateways create ha-vpn-gw-1 \
  --network=prod-vpc \
  --region=us-central1

gcloud compute vpn-tunnels create tunnel-1 \
  --peer-gcp-gateway=ha-vpn-gw-1 \
  --region=us-central1 \
  --ike-version=2 \
  --shared-secret=REDACTED \
  --vpn-gateway=ha-vpn-gw-1 \
  --interface=0
```

_Purpose:_ Provisions an HA VPN gateway (two redundant external IPs) and one of the tunnels needed toward on-premises or a peer VPC, as part of the two/four-tunnel topology required for the 99.99% SLA.

**Expected output:**

```
Created [https://www.googleapis.com/compute/v1/projects/my-project/regions/us-central1/vpnGateways/ha-vpn-gw-1].
Created [https://www.googleapis.com/compute/v1/projects/my-project/regions/us-central1/vpnTunnels/tunnel-1].
```

## 8. Production & Enterprise Usage

- **Cloud NAT as the default for all private-subnet workloads** needing outbound internet (patching, external API calls) — the standard pattern is private-by-default instances with Cloud NAT for egress, never assigning external IPs to backend/app-tier VMs.
- **HA VPN as a fast-to-deploy hybrid link or as a failover path for Interconnect** — many enterprises run Dedicated/Partner Interconnect as primary and HA VPN as an automatic BGP-based failover if the Interconnect circuit degrades or fails.
- **Dedicated Interconnect for high-bandwidth, latency-sensitive hybrid workloads** (large data migrations, real-time replication, VDI) where enterprises are physically present or willing to colocate at a Google peering facility.
- **Partner Interconnect for enterprises without colocation presence** needing private connectivity below the 10 Gbps Dedicated Interconnect increment, common for mid-size enterprises.

## 9. Common Misconceptions

- **Misconception:** "Cloud NAT lets external users initiate connections into my private instances if I allow it." It cannot — Cloud NAT is architecturally outbound-only; there is no configuration that makes it accept unsolicited inbound connections, unlike a firewall rule which can be misconfigured to allow inbound.
- **Misconception:** "Interconnect traffic is encrypted like VPN traffic." It is not, by default — Dedicated and Partner Interconnect are private physical/logical paths that don't traverse the public internet, but the traffic itself isn't IPsec-encrypted unless you layer application-level encryption (e.g., TLS) or run a VPN over the Interconnect connection (MACsec is available for Dedicated Interconnect as an added option).

## 10. Interview Questions

**🎯 Beginner:** _What does Cloud NAT do, and what can't it do?_
**Model answer:** Cloud NAT provides outbound-only internet connectivity for instances that don't have an external IP address, translating their outbound requests and routing return traffic back correctly. It cannot accept unsolicited inbound connections from the internet under any configuration — it is architecturally one-directional, unlike an external IP with a permissive firewall rule.

**🎯 Intermediate:** _When would you choose Cloud VPN over Cloud Interconnect, and vice versa?_
**Model answer:** Cloud VPN (HA VPN) is preferred when you need to get hybrid connectivity established quickly, don't require guaranteed high bandwidth or the lowest possible latency, or are connecting a lower-traffic site — it's provisioned in minutes to hours and runs over existing internet connectivity. Cloud Interconnect (Dedicated or Partner) is preferred for high-bandwidth, latency-sensitive, or high-volume steady-state hybrid traffic where the higher cost and longer provisioning lead time are justified by performance and reliability requirements — and it's common to run VPN as an automatic failover path even when Interconnect is primary.

**🎯 Senior/Architect:** _Design hybrid connectivity for an enterprise with a primary data center needing sub-5ms consistent latency to GCP for real-time database replication, and a secondary smaller office that just needs occasional access to internal GCP services._
**Model answer:** For the primary data center, I'd provision Dedicated Interconnect (or Partner Interconnect if the enterprise lacks colocation presence at a Google peering facility) sized to the replication bandwidth requirement, with Cloud Router and BGP for dynamic route exchange, and I'd layer HA VPN as an automatic BGP-preferenced failover path in case the Interconnect circuit degrades — since consistent low latency is a hard requirement, I would not rely on VPN as primary given its public-internet path introduces latency variability. For the secondary smaller office with occasional, lower-volume access needs, HA VPN alone is appropriate — it avoids the cost and lead time of a second Interconnect circuit that wouldn't be justified by the traffic volume. All private-subnet compute in both scenarios would additionally use Cloud NAT for any outbound internet access (e.g., OS patching) that shouldn't traverse the hybrid link at all.

## 11. Key Takeaways

- 🔑 Cloud NAT is outbound-only, regional, fully managed, and requires no per-zone gateway provisioning, unlike AWS NAT Gateway's per-AZ model.
- 🔑 HA VPN is encrypted-by-default, fast to provision, and runs over the public internet; Interconnect is a private (not encrypted by default) physical/logical path offering higher, more predictable bandwidth at higher cost and lead time.
- 🔑 Dedicated Interconnect requires physical colocation presence; Partner Interconnect removes that requirement via a service provider, at the cost of an added intermediary.
- 🔑 Cloud Router and BGP are the shared dynamic-routing control plane underlying both VPN and Interconnect, avoiding static route management as the network changes.

## 12. Related Concepts

VPC fundamentals and routing (Sections 19–20) that Cloud NAT and Interconnect/VPN attach to, firewall rules governing what traffic is permitted regardless of path ([Section 21](./Section-21-Part3-Firewall-Rules.md)), Cloud DNS forwarding that rides over these hybrid links ([Section 23](./Section-23-Part3-Cloud-DNS.md)), and hybrid/multi-cloud networking patterns that compose these building blocks end-to-end ([Section 26](./Section-26-Part3-Hybrid-Multi-Cloud-Networking.md)).
