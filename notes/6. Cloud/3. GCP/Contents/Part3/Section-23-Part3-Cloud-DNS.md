# Section 23 (Part 3): Cloud DNS

## 1. Definition

**Plain language:** Cloud DNS is Google's managed DNS service — it translates human-friendly domain names (like `www.example.com`) into IP addresses, and does it on Google's own globally distributed, highly available infrastructure so you never have to run your own DNS servers.

**Precise:** **Cloud DNS** is a managed, low-latency DNS service that hosts DNS records in **managed zones**, offered in two distinct scopes — **public zones** (resolvable from the public internet, served from Google's global anycast name server infrastructure) and **private zones** (resolvable only from within specified VPC networks) — with additional constructs (**DNS forwarding**, **DNS peering**, **DNS Server Policies**) to integrate on-premises and cross-VPC name resolution.

## 2. Why It Exists / Problem It Solves

Every application needs a way to translate names into addresses, but self-hosting DNS servers means managing availability, DDoS resilience, geographic distribution, and DNSSEC yourself — undifferentiated heavy lifting. Cloud DNS solves this for public-facing domains by running on the same anycast infrastructure that serves Google's own services (100% uptime SLA). It solves a second, GCP-specific problem for private/internal name resolution: since GCP VPCs are global but organizations often run many VPCs (via Shared VPC, Section 25, or standalone), private zones and DNS peering let internal service names resolve consistently across that VPC estate without exposing anything publicly, and DNS forwarding lets private, internal names on-premises and in GCP resolve into each other's namespace over an established hybrid connection (Section 24).

## 3. Core Concepts

### 3.1 Public Managed Zones

A **public zone** hosts DNS records for a domain you own (e.g., `example.com`), resolvable from anywhere on the internet. Google assigns a set of authoritative name servers to the zone; you point your domain registrar's NS records at them to delegate authority. Supports standard record types (A, AAAA, CNAME, MX, TXT, NS, SOA, etc.) plus DNSSEC for cryptographically signed responses that prevent DNS spoofing/cache-poisoning attacks.

### 3.2 Private Managed Zones

A **private zone** is resolvable only from VPC networks explicitly authorized to query it — it never appears on the public internet. Used for internal service discovery (e.g., `internal-api.corp.local` resolving only inside your VPCs). A private zone can be authorized for multiple VPC networks at creation or updated later, and multiple private zones can coexist for different internal namespaces.

### 3.3 DNS Forwarding

**DNS forwarding** (via **forwarding zones** and **Cloud DNS Server Policies**) lets Cloud DNS forward queries for specific domains to external DNS servers — most commonly, an on-premises DNS server reachable over Cloud VPN or Interconnect (Section 24). This enables split-horizon-style hybrid resolution: GCP-hosted workloads can resolve on-premises-only hostnames, and (via **inbound forwarding**, enabled through a DNS Server Policy) on-premises systems can resolve GCP private zone names, treating Cloud DNS's internal IP as their forwarder target.

### 3.4 DNS Peering

**DNS peering** lets one VPC network's Cloud DNS resolve names from another VPC network's private zone, without needing to duplicate the records or authorize the zone into both VPCs directly. This differs from simply authorizing a private zone to multiple VPCs: peering is useful when the zone's owning project should retain administrative control while still letting other VPCs (e.g., in a Shared VPC or multi-project architecture, Section 25) resolve its names.

### 3.5 DNS Server Policies

A **DNS Server Policy** is a per-VPC-network configuration object controlling two things: **inbound query forwarding** (allow on-premises systems to send DNS queries into a VPC's internal Cloud DNS resolver) and **outbound query forwarding / alternative name servers** (override what DNS servers VMs in the VPC use by default, e.g., to send all VPC DNS queries to an on-premises DNS server instead of Google's default internal resolver).

## 4. Comparison Table: Zone Types

| Zone Type            | Resolvable From                          | Common Use Case                                               |
| -------------------- | ---------------------------------------- | ------------------------------------------------------------- |
| Public managed zone  | Anywhere on the internet                 | Hosting DNS for a public-facing domain                        |
| Private managed zone | Authorized VPC networks only             | Internal service discovery within GCP                         |
| Forwarding zone      | VPC (forwards to external DNS server)    | Resolving on-premises hostnames from GCP                      |
| Peering zone         | VPC peered to another VPC's private zone | Cross-VPC internal name resolution without record duplication |

## 5. Architecture Diagram

```
   ON-PREMISES DATA CENTER                    GCP
  ┌──────────────────────┐      Cloud VPN /  ┌─────────────────────────────┐
  │  On-prem DNS server  │◄────Interconnect─►│  Cloud DNS                  │
  │  (corp.local)        │   (Section 24)    │  ┌─────────────────────┐    │
  └──────────────────────┘                   │  │ Private zone:       │    │
         ▲   outbound forwarding             │  │ gcp.internal        │    │
         │   (GCP ► on-prem)                 │  └─────────────────────┘    │
         │                                   │            │                │
         └──────inbound forwarding───────────┼────────────┘                │
             (on-prem ► GCP)                 │  authorized to VPC-A, VPC-B │
                                             └─────────────────────────────┘
                                                          │  DNS peering
                                                          ▼
                                                 ┌──────────────────────┐
                                                 │ VPC-C (peers to      │
                                                 │resolve gcp.internal) │
                                                 └──────────────────────┘
```

## 6. Comparison: Cloud DNS vs AWS Route 53 vs Azure DNS

| GCP Cloud DNS                                                                            | AWS Route 53                                                                                           | Azure DNS                                                 | Notes                                                                                                                                                                                             |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Public managed zone                                                                      | Public hosted zone                                                                                     | Public DNS zone                                           | Directly equivalent concept across all three                                                                                                                                                      |
| Private managed zone (per-VPC authorization)                                             | Private hosted zone (per-VPC association)                                                              | Private DNS zone (per-VNet link)                          | Directly equivalent concept across all three                                                                                                                                                      |
| DNS peering                                                                              | No direct equivalent (private zone association across accounts via Resource Access Manager is closest) | Azure Private DNS zone virtual network links (cross-VNet) | GCP's peering model is more explicit as a distinct construct                                                                                                                                      |
| DNS forwarding + Server Policies                                                         | Route 53 Resolver (inbound/outbound endpoints)                                                         | Azure DNS Private Resolver                                | Conceptually equivalent hybrid-forwarding capability, different product names                                                                                                                     |
| No traffic-routing policies (weighted, geolocation, latency) built into Cloud DNS itself | Route 53 has 7 native routing policies (weighted, latency, geolocation, failover, etc.)                | Azure Traffic Manager (separate product) handles this     | **Key differentiator:** GCP deliberately separates DNS from traffic-steering — that logic lives in Cloud Load Balancing's global anycast model (Section 22) instead of DNS-level routing policies |

> ⚠️ **Interview-relevant nuance:** Route 53's multiple routing policies exist partly because AWS load balancers are regional — DNS has to do the work of steering users to the nearest healthy region. GCP's Global External HTTP(S) Load Balancer (Section 22) already provides a single global anycast IP with automatic nearest-region routing at the network layer, so Cloud DNS doesn't need equivalent routing-policy machinery for that use case — a direct consequence of GCP's global load balancer architecture.

## 7. Hands-On Examples

**Beginner — create a public managed zone:**

```bash
gcloud dns managed-zones create example-public-zone \
  --dns-name="example.com." \
  --description="Public zone for example.com"
```

_Purpose:_ Creates a public managed zone that will hold DNS records for `example.com`, and returns the assigned Google name servers you'll delegate to at your domain registrar.

**Expected output:**

```
NAME: example-public-zone
DNS_NAME: example.com.
DESCRIPTION: Public zone for example.com
```

**Intermediate — create a private zone and an A record:**

```bash
gcloud dns managed-zones create internal-zone \
  --dns-name="gcp.internal." \
  --description="Internal zone" \
  --visibility=private \
  --networks=vpc-a

gcloud dns record-sets create api.gcp.internal. \
  --zone=internal-zone \
  --type=A \
  --ttl=300 \
  --rrdatas=10.0.1.5
```

_Purpose:_ Creates a private zone authorized only for `vpc-a`, then adds an internal-only A record resolvable exclusively from VMs within that VPC.

**Expected output:**

```
Created [https://dns.googleapis.com/dns/v1/projects/my-project/managedZones/internal-zone].
NAME              TYPE  TTL  DATA
api.gcp.internal.  A    300  10.0.1.5
```

## 8. Production & Enterprise Usage

- **Split-horizon DNS for hybrid environments:** enterprises commonly run the same domain name resolving to different IPs internally (via private zone) vs externally (via public zone), with DNS forwarding bridging on-premises and GCP namespaces during migration periods.
- **Centralized DNS zone management in Shared VPC architectures:** a single private zone in the host project is authorized across many service projects' VPCs, ensuring naming consistency without every team managing their own DNS.
- **DNSSEC on public zones** for any customer-facing domain in regulated industries, to protect against cache-poisoning and spoofing attacks.
- **Inbound/outbound Server Policies as the standard hybrid-DNS pattern** during and after data center migrations, so both environments can resolve each other's hostnames throughout a phased cutover.

## 9. Common Misconceptions

- **Misconception:** "A private zone authorized to one VPC is automatically visible to peered VPCs." It is not — VPC Network Peering (Section 25) does **not** automatically share DNS visibility; you must explicitly either authorize the zone to the other VPC or set up DNS peering.
- **Misconception:** "Cloud DNS needs a separate product like Route 53's routing policies to do global traffic steering." GCP intentionally handles global traffic steering at the load-balancer layer (global anycast IP, Section 22) rather than the DNS layer, so Cloud DNS's feature set looks "thinner" than Route 53's by design, not by gap.

## 10. Interview Questions

**🎯 Beginner:** _What's the difference between a public and a private managed zone in Cloud DNS?_
**Model answer:** A public managed zone is resolvable from anywhere on the internet and requires delegating your domain's NS records at your registrar to Google's assigned name servers. A private managed zone is resolvable only from VPC networks you explicitly authorize, and never appears on the public internet — used for internal service discovery that should never be publicly reachable.

**🎯 Intermediate:** _How would you let an on-premises data center resolve internal GCP hostnames, and vice versa?_
**Model answer:** I'd establish hybrid connectivity first (Cloud VPN or Interconnect, Section 24), then configure a DNS Server Policy with inbound query forwarding enabled so on-premises DNS servers can forward queries for GCP private-zone names to Cloud DNS's internal resolver IP. For the reverse direction, I'd create a forwarding zone in Cloud DNS pointing at the on-premises DNS server's IP for the on-premises domain, so GCP workloads can resolve on-premises-only hostnames.

**🎯 Senior/Architect:** _Design DNS for an enterprise with a Shared VPC host project, 20 service projects, and a requirement that all internal services use one consistent internal namespace, while a migration project temporarily needs on-premises and GCP hostnames to resolve into each other._
**Model answer:** I'd create one private managed zone (e.g., `corp.internal`) in the Shared VPC host project, authorized to the host VPC, since all 20 service projects attach to that same host VPC's network (Section 25) and therefore share DNS resolution automatically — no need for per-project zones or DNS peering in this specific topology. For the migration's bidirectional hybrid resolution, I'd set up Cloud VPN or Interconnect to the on-premises data center (Section 24), then a DNS Server Policy with inbound forwarding enabled (so on-premises can query GCP's zone) and a forwarding zone pointing at the on-premises DNS server for the on-premises domain (so GCP can resolve on-premises hostnames) — reviewing and decommissioning the forwarding zone once the migration cutover completes, to avoid a permanent unnecessary dependency.

## 11. Key Takeaways

- 🔑 Cloud DNS offers two zone scopes — public (internet-resolvable) and private (VPC-scoped) — plus forwarding and peering constructs for hybrid and cross-VPC resolution.
- 🔑 DNS visibility does **not** automatically follow VPC Peering; private zones must be explicitly authorized to a VPC or connected via DNS peering.
- 🔑 DNS forwarding (with Server Policies for inbound/outbound) is the standard hybrid-DNS bridge between on-premises and GCP namespaces.
- 🔑 GCP deliberately keeps global traffic-steering logic in Cloud Load Balancing's anycast model rather than in DNS routing policies, unlike Route 53's 7-policy model.

## 12. Related Concepts

VPC fundamentals and global scope (Section 19), Cloud Load Balancing as the layer that handles global traffic steering instead of DNS (Section 22), Cloud NAT/Interconnect/VPN for the hybrid connectivity DNS forwarding rides over (Section 24), and Shared VPC/Peering for the multi-VPC topologies that determine DNS zone authorization strategy (Section 25).
