# Section 20 (Part 3): Subnets, IP Addressing & Routes

## 1. Definition

**Plain language:** If the VPC network ([Section 19](./Section-19-Part3-VPC-Fundamentals.md)) is the global container, subnets are the actual regional "neighborhoods" where IP addresses are handed out to VMs and other resources. Routes are the signposts that tell traffic where to go next, whether that destination is another subnet, the internet, or a private connection back to an on-premises network.

**Precise:** A **subnet** (subnetwork) is a **regional** resource within a VPC network that defines a range of private IPv4 (and optionally IPv6) addresses available for allocation to resources created in that region. A **route** is a VPC-network-scoped rule mapping a destination IP range to a next hop, used by every resource in the network to determine where to forward packets.

## 2. Why It Exists / Problem It Solves

A global VPC ([Section 19](./Section-19-Part3-VPC-Fundamentals.md)) needs some mechanism to actually carve out usable, non-overlapping IP address blocks per region — that's the subnet's job. Without regional subnets, there would be no way to control which IP ranges are consumed in which physical location, which matters both for capacity planning (not running out of addresses) and for connecting to other networks (on-premises VPNs, peered VPCs) without CIDR collisions.

Routes exist because a network is useless without a way to decide, for any given destination address, which direction to send a packet. GCP auto-generates the routes needed for basic connectivity (so a new VPC works out of the box for internal and internet-bound traffic) but also lets you define custom routes for advanced scenarios like traffic inspection appliances or Interconnect connectivity.

## 3. Core Concepts

### 3.1 Subnets Are Regional Resources

Each subnet exists in exactly one region and its IP range is only ever allocated to resources created in zones within that region (a subnet is not zonal itself — it spans all zones of its region). Subnets in the same VPC, even across different regions, can freely communicate over private IP addresses by default because they belong to the same global network.

- Subnet CIDR ranges must **not overlap** with each other within the same VPC, nor with any peered VPC or on-premises network reachable via VPN/Interconnect.
- Subnet ranges can be expanded after creation (making the range larger) but never shrunk — plan conservatively.

### 3.2 Primary IP Ranges

Every subnet has one **primary IP range**, the default CIDR block from which primary internal IP addresses are assigned to VM network interfaces. This is the range you specify at subnet creation (e.g., `10.0.0.0/20`), and it's what most resources use unless configured otherwise.

### 3.3 Secondary (Alias) IP Ranges

A subnet can additionally have one or more **secondary IP ranges**, used for **alias IP ranges** — additional IP addresses (or entire small CIDR blocks) assigned to a VM's network interface beyond its single primary IP. The most important production use case is **GKE**: a GKE cluster running in VPC-native mode (the default and recommended mode) uses two secondary ranges on the subnet — one for Pod IPs and one for Service (ClusterIP) IPs — so that Pods and Services get real, routable IP addresses within the VPC rather than requiring an overlay network (detailed in [Section 31](../Part4/Section-31-Part4-GKE-Networking-and-Storage.md)).

| Range type                 | Purpose                           | Typical example |
| -------------------------- | --------------------------------- | --------------- |
| Primary range              | VM primary internal IP            | `10.0.0.0/20`   |
| Secondary range — Pods     | GKE Pod IPs (VPC-native clusters) | `10.4.0.0/14`   |
| Secondary range — Services | GKE Service (ClusterIP) IPs       | `10.8.0.0/20`   |

### 3.4 Routes: System-Generated vs Custom

Every VPC network automatically has **system-generated routes**:

- A **default route** (`0.0.0.0/0`) pointing at the "default internet gateway" next hop, giving instances with external IPs (and NAT-configured instances, [Section 24](./Section-24-Part3-Cloud-NAT-Interconnect-VPN.md)) a path to the internet.
- A **subnet route** for each subnet's primary and secondary ranges, automatically created when the subnet is created, enabling communication within and across subnets in the same VPC.

**Custom (static) routes** are explicitly created for scenarios the system-generated routes don't cover, with a next hop of: a VM instance (e.g., a NAT/proxy appliance), an internal load balancer, a VPN tunnel, an Interconnect attachment (VLAN attachment), or Cloud Router's dynamically learned BGP routes.

### 3.5 Route Priority

Every route (system-generated or custom) has a **priority** value (0–65535, default 1000, lower number = higher priority). When multiple routes match a destination, GCP selects the route with the **lowest priority number**; if priorities tie, the most specific matching destination range wins, and if that also ties, the choice is made using a deterministic hash.

- Custom routes are commonly given a lower priority number (e.g., `100`) than the default internet route (`1000`) to force traffic through an inspection appliance or a specific gateway ahead of the default path.
- Route priority is the mechanism enterprises use to implement "hub-and-spoke" traffic inspection: a custom `0.0.0.0/0` route at a lower priority number than the default, pointing to a next-hop VM running a firewall/NGFW appliance.

## 4. Comparison: GCP Routes vs AWS Route Tables

| Aspect              | GCP Routes                                                                                                             | AWS Route Tables                                                                    |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| Scope               | One implicit route table per VPC network — every route applies network-wide unless scoped by tag/instance/network tags | Explicit route table per subnet (or shared across subnets)                          |
| Conflict resolution | Priority number (lowest wins) plus most-specific-match                                                                 | Most-specific-match only (longest prefix match); no priority field                  |
| Association model   | Routes apply globally to the whole VPC, optionally filtered by instance tags                                           | Routes belong to a specific route table explicitly associated with specific subnets |
| Dynamic routing     | Cloud Router (BGP) injects dynamic routes automatically                                                                | Managed via Transit Gateway route tables / Direct Connect BGP                       |

## 5. Hands-On Examples

**Beginner — create a subnet with a secondary range for GKE:**

```bash
gcloud compute networks subnets create prod-usc1-sub \
  --network=prod-vpc \
  --region=us-central1 \
  --range=10.0.0.0/20 \
  --secondary-range=pods=10.4.0.0/14,services=10.8.0.0/20
```

_Purpose:_ Creates a regional subnet with a primary range for VM IPs and two secondary ranges reserved for a future VPC-native GKE cluster's Pods and Services.

**Expected output:**

```
Created [https://www.googleapis.com/compute/v1/projects/my-project/regions/us-central1/subnetworks/prod-usc1-sub].
NAME             REGION        NETWORK    RANGE
prod-usc1-sub    us-central1   prod-vpc   10.0.0.0/20
```

**Intermediate — list routes and inspect priority:**

```bash
gcloud compute routes list --filter="network:prod-vpc"
```

**Expected output:**

```
NAME                          NETWORK    DEST_RANGE     NEXT_HOP                 PRIORITY
default-route-...             prod-vpc   0.0.0.0/0      default-internet-gateway 1000
prod-usc1-sub-...              prod-vpc   10.0.0.0/20    prod-vpc                 1000
inspect-all-egress             prod-vpc   0.0.0.0/0      fw-appliance-vm          100
```

_Purpose:_ Confirms a custom route (`inspect-all-egress`, priority 100) overrides the default internet route (priority 1000) for all egress traffic, forcing it through a firewall appliance VM first.

## 6. Production & Enterprise Usage

- **CIDR planning discipline:** Enterprises maintain a centralized IP address management (IPAM) plan across all subnets, peered VPCs, and on-premises ranges before creating a single subnet, since overlapping ranges are extremely disruptive to fix after the fact (especially once VPN/Interconnect or VPC Peering is in place).
- **Secondary ranges sized generously up front:** Because GKE Pod secondary ranges cannot be resized after cluster creation without significant disruption, production subnet plans size the Pods secondary range for multi-year node/pod growth, not current-day capacity.
- **Custom routes for centralized egress inspection:** A common enterprise pattern routes all outbound internet traffic through a centralized "hub" VPC running next-generation firewall appliances, using a low-priority-number custom `0.0.0.0/0` route pointing at an internal load balancer in front of the appliance fleet.

## 7. Common Misconceptions

- **Misconception:** "A subnet is tied to a single zone, like AWS." In GCP, a subnet's IP range is available across every zone in its region — only individual VM instances are zonal, not the subnet itself.
- **Misconception:** "Lower route priority number means lower precedence." It's the opposite: GCP route priority uses lowest-number-wins, matching typical BGP-style conventions but easy to get backwards if assuming "higher number = higher priority."

## 8. Interview Questions

**🎯 Beginner:** _What is a secondary (alias) IP range used for?_
**Model answer:** A secondary range lets a subnet allocate additional IP addresses or CIDR blocks beyond the primary range assigned to VM interfaces. The most common production use is VPC-native GKE clusters, which use one secondary range for Pod IPs and another for Service IPs, giving containers real routable VPC IP addresses.

**🎯 Intermediate:** _How does GCP decide which route to use when two routes both match a destination?_
**Model answer:** GCP picks the route with the lowest priority number first (default is 1000; lower numbers win). If multiple matching routes share the same priority, GCP prefers the most specific destination range (longest prefix match), and if that still ties, a deterministic hash-based selection applies.

**🎯 Senior/Architect:** _Design a centralized egress-inspection pattern for an enterprise with dozens of service projects attached to a Shared VPC, where all internet-bound traffic must pass through a firewall appliance fleet._
**Model answer:** I'd create a custom static route in the Shared VPC host project with destination `0.0.0.0/0` and a priority number lower than the default internet route (e.g., 100 vs. 1000), with a next hop pointing to an internal regional load balancer in front of an auto-scaled managed instance group running the firewall appliance. Because routes apply network-wide by default in a VPC, every attached service project's VMs would automatically have their default egress path redirected through the appliance without per-project route configuration, provided the route isn't scoped away by instance tags. I'd size the appliance fleet's internal load balancer and MIG for peak egress bandwidth, and pair this with VPC Flow Logs / Firewall Insights ([Section 27](./Section-27-Part3-Network-Intelligence-Center-Traffic-Director.md)) to validate no traffic is bypassing inspection.

## 9. Key Takeaways

- 🔑 Subnets are regional (not zonal); their primary range serves VM IPs and secondary ranges commonly serve GKE Pod/Service IPs.
- 🔑 GCP has one implicit route table per VPC network (not per subnet like AWS); routes apply network-wide unless scoped by instance tags.
- 🔑 Route priority uses lowest-number-wins; custom routes with low priority numbers are the standard way to override the default internet route for egress inspection patterns.
- 🔑 Secondary range sizing for GKE must be planned generously up front since resizing later is disruptive.

## 10. Related Concepts

VPC fundamentals and global scope ([Section 19](./Section-19-Part3-VPC-Fundamentals.md)), firewall rules that further restrict what these routes actually permit ([Section 21](./Section-21-Part3-Firewall-Rules.md)), Cloud NAT and Cloud Router's dynamic route injection ([Section 24](./Section-24-Part3-Cloud-NAT-Interconnect-VPN.md)), and GKE's VPC-native networking model ([Section 31](../Part4/Section-31-Part4-GKE-Networking-and-Storage.md)) all build directly on the subnet and routing concepts here.
