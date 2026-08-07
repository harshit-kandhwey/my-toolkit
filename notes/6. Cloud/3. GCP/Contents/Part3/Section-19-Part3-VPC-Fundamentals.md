# Section 19 (Part 3): VPC Fundamentals

## 1. Definition

**Plain language:** A Virtual Private Cloud (VPC) network is your own private, software-defined network inside GCP — the container that everything else in this Part (subnets, firewall rules, load balancers, routes) lives inside. In GCP, this container is not tied to any single region; it spans the entire globe.

**Precise:** A GCP **VPC network** is a **global**, project-scoped, virtual Layer-3 network providing connectivity for Compute Engine VM instances, GKE clusters, App Engine flexible environments, and other resources, implemented as a software-defined overlay on Google's physical network rather than a traditional per-region networking construct. A VPC network itself holds no IP address ranges; its **subnets** — regional sub-resources — hold the IP ranges (covered fully in [Section 20](./Section-20-Part3-Subnets-IP-Addressing-and-Routes.md)).

## 2. Why It Exists / Problem It Solves

Every cloud resource needs network isolation from other customers' resources and a private address space for internal communication. Without a VPC construct, every VM would either be exposed directly to the internet or share an address space with unrelated tenants — both unacceptable for security and manageability. A VPC solves this by giving each project (or group of projects, via Shared VPC — [Section 25](./Section-25-Part3-Shared-VPC-Peering-PSC.md)) an isolated, private IP address space with full control over routing and firewalling.

GCP's specific design choice — making the VPC itself **global** rather than regional — solves an additional problem that AWS and Azure customers must engineer around manually: it lets a single network span every region on Earth without any peering, transit gateway, or explicit inter-region connectivity setup. A VM in `us-central1` and a VM in `asia-south1` can be in the same VPC network, communicate over internal (private) IP addresses, and be governed by the same set of firewall rules, by default.

## 3. Core Concepts

### 3.1 VPC as a Global Resource

A VPC network is created once, with no region specified, and its scope automatically extends to every GCP region. This is fundamentally different from AWS (where a VPC is created inside one specific region) and Azure (where a VNet is likewise regional). Consequences:

- Firewall rules attached to a VPC apply network-wide, across all regions, unless scoped down with target tags/service accounts and regional considerations.
- Routes ([Section 20](./Section-20-Part3-Subnets-IP-Addressing-and-Routes.md)) can direct traffic between subnets in different regions without any peering construct — it is one network.
- Only **subnets** carry a region and an IP range; the VPC itself is just the enclosing global namespace.

### 3.2 Auto Mode vs Custom Mode VPCs

Every VPC network is created in one of two modes, chosen at creation time (mode can later be converted from auto to custom, but not back):

- **Auto mode:** GCP automatically creates one subnet in **every** GCP region, each using a predetermined `/20` CIDR block from a reserved `10.128.0.0/9` range. Convenient for quick starts and learning, but you have no control over subnet CIDR ranges and a subnet exists in every region whether you use it or not, which is rarely desirable for real architecture.
- **Custom mode:** No subnets are created automatically. You explicitly create each subnet, in each region you actually need, with an IP range you choose. This is the mode used for essentially all production and enterprise deployments, because it gives full control over IP address planning and avoids unwanted regional footprint.

> 💡 **Tip:** Always create new production VPCs in custom mode. Auto mode is a convenience for tutorials, not an architecture pattern — most enterprises disable auto-mode VPC creation entirely via an Organization Policy constraint (`compute.skipDefaultNetworkCreation` and related constraints, covered in [Section 37](../Part5/Section-37-Part5-Organization-Policies.md)).

### 3.3 The Default VPC and Its Pitfalls

Every new GCP project is created with a **default VPC network** — an auto-mode network named `default`, pre-populated with permissive firewall rules (allowing internal traffic across the entire `10.128.0.0/9` range, SSH from `0.0.0.0/0` on port 22, RDP from `0.0.0.0/0` on port 3389, and ICMP from anywhere). This exists purely for a frictionless first-run experience.

- **Pitfall — implicit broad exposure:** The default SSH/RDP rules mean any VM created without changes is reachable from the entire internet on those ports. This is a common source of real-world security incidents and audit findings.
- **Pitfall — uncontrolled IP planning:** Because it is auto-mode, it has a subnet (and IP range) in every region automatically, complicating later custom IP address planning if left in place.
- **Enterprise practice:** Delete the default VPC (or prevent its creation entirely via Org Policy on new projects) and build custom-mode VPCs deliberately, with firewall rules following least-privilege from the start ([Section 21](./Section-21-Part3-Firewall-Rules.md)).

### 3.4 VPC Network Components (Forward Map)

A VPC network by itself is just a namespace; its practical behavior comes from components covered in the rest of Part 3:

| Component                                       | Scope                                         | Covered In                                                           |
| ----------------------------------------------- | --------------------------------------------- | -------------------------------------------------------------------- |
| Subnets (primary + secondary IP ranges)         | Regional                                      | [Section 20](./Section-20-Part3-Subnets-IP-Addressing-and-Routes.md) |
| Routes (system-generated + custom)              | Global (routes can target regional next-hops) | [Section 20](./Section-20-Part3-Subnets-IP-Addressing-and-Routes.md) |
| Firewall rules / hierarchical firewall policies | Global (VPC) / Org-Folder (hierarchical)      | [Section 21](./Section-21-Part3-Firewall-Rules.md)                   |
| Load balancers                                  | Global or Regional depending on type          | [Section 22](./Section-22-Part3-Cloud-Load-Balancing.md)             |
| Cloud DNS                                       | Global (public) / VPC-scoped (private)        | [Section 23](./Section-23-Part3-Cloud-DNS.md)                        |
| Cloud NAT, VPN, Interconnect                    | Regional (NAT/VPN gateway) / Global reach     | [Section 24](./Section-24-Part3-Cloud-NAT-Interconnect-VPN.md)       |
| Shared VPC, Peering, Private Service Connect    | Cross-project / cross-VPC                     | [Section 25](./Section-25-Part3-Shared-VPC-Peering-PSC.md)           |

## 4. Comparison: GCP VPC vs AWS VPC vs Azure VNet

| Aspect                              | GCP VPC                                                  | AWS VPC                                                | Azure VNet                                             |
| ----------------------------------- | -------------------------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------ |
| Scope                               | **Global** — one network spans all regions               | Regional — one VPC lives in one region                 | Regional — one VNet lives in one region                |
| Subnet scope                        | Regional                                                 | Zonal (AZ)                                             | Regional (subnets don't map to AZs)                    |
| Cross-region connectivity           | Native — no extra construct needed                       | Requires VPC Peering or Transit Gateway across regions | Requires VNet Peering (global peering) across regions  |
| IP addressing                       | Subnets have explicit primary + secondary (alias) ranges | Subnets have a CIDR carved from the VPC CIDR           | Subnets have a CIDR carved from the VNet address space |
| Default network per project/account | `default` auto-mode VPC (deletable)                      | Default VPC per region (deletable)                     | No default VNet is auto-created                        |
| Multiple networks per project       | Yes, many VPCs per project, each independent             | Yes, many VPCs per region/account                      | Yes, many VNets per subscription                       |

## 5. Architecture Diagram

```
                    PROJECT: my-enterprise-prod
                    ┌─────────────────────────────────────────────────────────┐
                    │        VPC NETWORK: "prod-vpc" (custom mode, GLOBAL)    │
                    │                                                         │
                    │   REGION: us-central1        REGION: europe-west1       │
                    │   ┌───────────────────┐      ┌───────────────────┐      │
                    │   │ Subnet:           │      │ Subnet:           │      │
                    │   │ prod-usc1-sub     │◄────►│ prod-euw1-sub     │      │
                    │   │ 10.0.0.0/20       │ same │ 10.0.16.0/20      │      │
                    │   └───────────────────┘ VPC, └───────────────────┘      │
                    │                          no peering needed              │
                    │   Firewall rules, routes: apply network-wide (global)   │
                    └─────────────────────────────────────────────────────────┘
```

## 6. Hands-On Examples

**Beginner — create a custom-mode VPC:**

```bash
gcloud compute networks create prod-vpc \
  --subnet-mode=custom \
  --bgp-routing-mode=global
```

_Purpose:_ Creates a global VPC network with no auto-created subnets, ready for deliberate, region-by-region subnet planning.

**Expected output:**

```
Created [https://www.googleapis.com/compute/v1/projects/my-project/global/networks/prod-vpc].
NAME       SUBNET_MODE  BGP_ROUTING_MODE  IPV4_RANGE  GATEWAY_IPV4
prod-vpc   CUSTOM       GLOBAL
```

**Intermediate — list all VPCs and their mode in a project:**

```bash
gcloud compute networks list
```

**Expected output:**

```
NAME       SUBNET_MODE  BGP_ROUTING_MODE  IPV4_RANGE  GATEWAY_IPV4
default    AUTO         REGIONAL
prod-vpc   CUSTOM       GLOBAL
```

> ⚠️ **Note:** Seeing `default` with `AUTO` mode in a production project is a red flag during an architecture review — it signals the default network was never cleaned up.

## 7. Production & Enterprise Usage

- **Delete or block the default VPC** in every production project; enforce this at scale via an Organization Policy constraint applied at the Folder or Organization level ([Section 37](../Part5/Section-37-Part5-Organization-Policies.md)), not case-by-case.
- **One VPC per environment, not per team**, is a common enterprise pattern using Shared VPC ([Section 25](./Section-25-Part3-Shared-VPC-Peering-PSC.md)) — a single host VPC per environment (`prod`, `staging`, `dev`) shared into many service projects, rather than one VPC per application team, to keep IP address planning centralized.
- **Global BGP routing mode** (`--bgp-routing-mode=global`) is standard for enterprises using Cloud Router with Interconnect/VPN ([Section 24](./Section-24-Part3-Cloud-NAT-Interconnect-VPN.md)), since it advertises routes to all regions rather than just the local one.

## 8. Common Misconceptions

- **Misconception:** "A GCP VPC works like an AWS VPC, just bigger." In reality the fundamental unit that carries an IP CIDR and lives in one place is the **subnet**, not the VPC — the VPC is purely a global policy/routing namespace. This inverts a lot of AWS-trained intuition about "what region is my VPC in."
- **Misconception:** "Auto mode is a sensible default to build on." Auto mode is intended for quick starts; it silently creates a subnet in every current and future GCP region, which is almost never the intended production footprint.

## 9. Interview Questions

**🎯 Beginner:** _Is a GCP VPC network a regional or global resource?_
**Model answer:** Global. A single VPC network spans every GCP region without requiring any peering or additional configuration. Only its subnets are regional resources, each with its own IP address range in one specific region.

**🎯 Intermediate:** _What is the difference between auto mode and custom mode VPC networks, and which would you use in production?_
**Model answer:** Auto mode automatically creates one subnet per region using predetermined `/20` ranges from a reserved block, offering convenience but no control over IP planning. Custom mode creates no subnets automatically — you explicitly create subnets in only the regions you need, with CIDR ranges you choose. Production deployments almost always use custom mode for deliberate IP address management and to avoid an unwanted regional footprint.

**🎯 Senior/Architect:** _A new enterprise customer wants every application team to have isolated projects for billing/IAM, but a single centrally-managed network with consistent firewall and IP address governance. How do the VPC-global design and auto/custom modes factor into your design?_
**Model answer:** I'd use a Shared VPC ([Section 25](./Section-25-Part3-Shared-VPC-Peering-PSC.md)) architecture: one custom-mode host VPC per environment, owned by a central networking team, with subnets deliberately planned per region to avoid overlap. Application teams get their own service projects for billing/IAM isolation but attach to the shared host VPC's subnets for compute resources, inheriting centrally-managed firewall rules and routes. Because the VPC is global, this single host network can span every region the organization operates in without any cross-region peering, and because it's custom mode, IP address planning stays centrally controlled rather than fragmented per team — critical at enterprise scale to avoid CIDR overlap when connecting to on-premises networks via Interconnect/VPN ([Section 24](./Section-24-Part3-Cloud-NAT-Interconnect-VPN.md)).

## 10. Key Takeaways

- 🔑 A GCP VPC network is a **global** resource; only subnets are regional — the reverse of AWS's model, where the VPC itself is regional.
- 🔑 Auto mode is a convenience for quick starts (one subnet per region, fixed CIDRs); custom mode gives full control and is the production standard.
- 🔑 Every new project ships with a permissive `default` auto-mode VPC that should be deleted or blocked in production via Organization Policy.
- 🔑 The VPC itself carries no IP ranges — it is the global namespace that subnets, routes, and firewall rules attach to.

## 11. Related Concepts

Subnets and IP addressing ([Section 20](./Section-20-Part3-Subnets-IP-Addressing-and-Routes.md)), firewall rules ([Section 21](./Section-21-Part3-Firewall-Rules.md)), Shared VPC and Peering ([Section 25](./Section-25-Part3-Shared-VPC-Peering-PSC.md)), and Organization Policy enforcement of network guardrails ([Section 37](../Part5/Section-37-Part5-Organization-Policies.md)) all build directly on the VPC fundamentals introduced here.
