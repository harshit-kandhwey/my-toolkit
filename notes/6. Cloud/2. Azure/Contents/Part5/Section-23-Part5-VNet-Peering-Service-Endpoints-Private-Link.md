# Section 23 — VNet Peering & Service Endpoints/Private Link

## 23.1 Definition

**Plain language:** VNet Peering connects two separate Virtual Networks so resources in each can talk to each other privately, as if they were in the same network. Service Endpoints and Private Link solve a related but different problem — letting resources inside a VNet reach Azure PaaS services (like a Storage Account or a database) privately, without that traffic ever going out over the public internet.

**Precise definition:** **VNet Peering** is a low-latency, high-bandwidth connection between two Virtual Networks, routed entirely over Microsoft's backbone network, enabling private connectivity between resources in each VNet as though they shared a single network. **Service Endpoints** extend a VNet's identity to specific Azure PaaS service traffic, allowing that traffic to remain on the Azure backbone rather than the public internet while still targeting the service's public endpoint. **Private Link** goes further, provisioning a private IP address within the VNet itself for the PaaS service, making it appear as a first-class private resource within the VNet's own address space.

## 23.2 Why It Exists / Problem It Solves

Real-world architectures rarely fit inside a single VNet — different applications, business units, or environments (dev/test/prod) are commonly deployed in separate VNets for isolation and governance reasons, yet often still need to communicate with each other (e.g., a shared services VNet reachable by multiple application VNets). VNet Peering solves this connectivity need without requiring traffic to route through the public internet or a VPN gateway. Separately, PaaS services like Storage Accounts and Azure SQL Database are, by default, reachable via public endpoints on the internet (even though authentication/authorization still applies) — for architectures requiring that this traffic never traverse the public internet at all, whether for compliance, defense-in-depth, or eliminating exposure to internet-based threats entirely, Service Endpoints and Private Link solve this by keeping that traffic within Azure's private backbone network or, in Private Link's case, fully within the VNet's own private address space.

## 23.3 VNet Peering

### 23.3.1 How It Works

Once two VNets are peered, resources in each can communicate using their private IP addresses directly, with traffic routed over Microsoft's private backbone network rather than the public internet — from a latency and bandwidth perspective, this performs similarly to communication within a single VNet, not like a typical internet-routed connection.

### 23.3.2 Key Characteristics and Constraints

- **Non-transitive by default** — if VNet A is peered with VNet B, and VNet B is peered with VNet C, VNet A cannot automatically reach VNet C through that chain; each pair requiring direct communication needs its own explicit peering (or must route through a central hub with appropriate configuration, discussed in Section 23.3.4) — this non-transitivity is a frequently tested and frequently misunderstood characteristic.
- **No overlapping address spaces** — as emphasized in Section 21.3.1 and 21.11's troubleshooting table, peered VNets must have non-overlapping CIDR ranges; this constraint is precisely why upfront address planning matters so much at enterprise scale.
- **Cross-region and cross-subscription support** — VNets can be peered across different Azure regions ("Global VNet Peering") and across different subscriptions (and even different Entra ID tenants, with appropriate permissions), not just within the same subscription and region.

### 23.3.3 Peering vs. VPN Gateway (Preview)

VNet Peering is used for VNet-to-VNet connectivity (both endpoints are Azure VNets); connecting an Azure VNet to an **on-premises** network instead requires VPN Gateway or ExpressRoute (Section 26), a fundamentally different connectivity mechanism covered later in this Part — VNet Peering doesn't extend to non-Azure networks.

### 23.3.4 Hub-and-Spoke Topology (Full Explanation)

**Definition:** The hub-and-spoke topology, referenced in Sections 21.6 and 22.7, uses a central "hub" VNet — typically containing shared services like a firewall/NVA, VPN/ExpressRoute gateways, and shared DNS infrastructure — peered individually with multiple "spoke" VNets, each typically representing one application or business unit.

**Why non-transitivity matters here:** Because peering is non-transitive, two spoke VNets peered only with the hub (not with each other) cannot communicate directly by default, even though both are peered with the same hub — if spoke-to-spoke communication is genuinely required, this must either be enabled through an additional mechanism (such as **Virtual Network Gateway transit** configuration, or routing spoke-to-spoke traffic through a central firewall NVA sitting in the hub, using Route Tables as covered in Section 22.4.2, so the hub actively forwards permitted traffic between spokes rather than relying on peering transitivity that doesn't exist by default) or via direct spoke-to-spoke peering for specific pairs that need it. This non-transitivity is often actually a **desired** security property in hub-and-spoke designs — it means spoke VNets don't automatically get open access to each other, and any spoke-to-spoke communication that is allowed can be deliberately routed through the hub's firewall for inspection, rather than happening invisibly and uninspected.

## 23.4 Service Endpoints

**Definition:** A **Service Endpoint** enables a subnet to reach specific Azure PaaS services (such as Storage Accounts or Azure SQL Database) over a direct, optimized route on the Azure backbone network, rather than routing that traffic out to the public internet — while the PaaS service still has a public IP address, traffic originating from a Service Endpoint-enabled subnet takes this optimized private path instead of the general internet path.

**Combined with resource firewall rules:** Service Endpoints are commonly paired with the target PaaS resource's own network firewall rules (e.g., a Storage Account configured to only accept traffic from specific VNets/subnets) — the Service Endpoint provides the optimized network path, while the resource-level firewall rule provides the actual access restriction, together achieving both an optimized route and genuine access control limited to specified VNets/subnets.

⚠️ Service Endpoints, while improving the network path, do **not** give the PaaS service a private IP address within the VNet itself — the service retains its public IP address, and the traffic path optimization is a distinct mechanism from Private Link's more complete "give the service a private IP inside my VNet" approach, described next. This distinction is a frequently tested point in interviews.

## 23.5 Private Link (Private Endpoints)

**Definition:** **Private Link**, implemented via a **Private Endpoint**, provisions an actual private IP address within your VNet's own subnet, representing a specific PaaS resource (a specific Storage Account, a specific Azure SQL Database, and so on) — traffic to that private IP is routed directly and privately to the specific target resource, with the PaaS resource's public endpoint able to be disabled entirely if full network isolation is required.

**Why this is a stronger isolation guarantee than Service Endpoints:** Because the PaaS resource now has a genuine private IP address living inside your VNet, it can be treated architecturally almost like any other private VNet resource — reachable via on-premises hybrid connectivity (Section 26) through the VNet, subject to standard NSG-based traffic filtering at the subnet level, and with the option to fully disable the resource's public endpoint, eliminating internet exposure entirely rather than merely optimizing the network path to it while a public endpoint still technically exists.

**Comparison — Service Endpoint vs. Private Link:**

| Aspect                                             | Service Endpoint                                                                                  | Private Link (Private Endpoint)                                                     |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- |
| PaaS resource gets a private IP in your VNet       | No                                                                                                | Yes                                                                                 |
| Public endpoint can be fully disabled              | Not directly via the Service Endpoint mechanism itself (requires separate firewall configuration) | Yes, cleanly, since the private endpoint provides full private connectivity         |
| Reachable from on-premises via hybrid connectivity | Not directly (traffic still targets the service's public IP)                                      | Yes (since it's a private VNet IP, reachable like any other private resource)       |
| Granularity                                        | VNet/subnet-level access to the service                                                           | Connection to one specific resource instance                                        |
| Relative complexity                                | Simpler to configure                                                                              | More setup (DNS considerations especially — see below), but more complete isolation |

⚠️ Private Link requires careful **DNS configuration** — clients must resolve the PaaS resource's standard hostname (e.g., `mystorageaccount.blob.core.windows.net`) to the new private IP address rather than the public IP, which typically requires an Azure Private DNS Zone integrated with the VNet; misconfigured DNS is one of the most common real-world Private Link implementation problems, where traffic still ends up routing to the public endpoint because name resolution wasn't correctly redirected to the private IP.

🎯 **Interview Tip:** "Service Endpoint vs. Private Link — what's the difference?" is an extremely common Azure networking interview question; the core answer to lead with is that Private Link gives the PaaS resource an actual private IP address inside your VNet, while a Service Endpoint only optimizes the network path to the resource's still-public IP address.

## 23.6 Architecture Diagram

```
Hub VNet "vnet-hub" (10.0.0.0/16)
 ├── Firewall/NVA subnet
 ├── VPN/ExpressRoute Gateway subnet
 │
 ├──(peered)── Spoke VNet "vnet-app-a" (10.1.0.0/16)
 │                 └── Subnet with Private Endpoint → Storage Account "stappadata"
 │                       (private IP: 10.1.1.10, public endpoint disabled)
 │
 └──(peered)── Spoke VNet "vnet-app-b" (10.2.0.0/16)
                   └── Subnet with Service Endpoint enabled → Azure SQL Database
                         (traffic uses optimized backbone path; SQL firewall
                          restricts access to this specific subnet)

vnet-app-a and vnet-app-b are NOT directly peered (non-transitive) —
  any spoke-to-spoke traffic would need to route through the hub's firewall
```

## 23.7 Configuration & Hands-On Example

**Creating VNet Peering between a hub and a spoke:**

```bash
az network vnet peering create \
  --resource-group rg-hub \
  --name hub-to-spoke-a \
  --vnet-name vnet-hub \
  --remote-vnet vnet-app-a \
  --allow-vnet-access true

az network vnet peering create \
  --resource-group rg-app-a \
  --name spoke-a-to-hub \
  --vnet-name vnet-app-a \
  --remote-vnet vnet-hub \
  --allow-vnet-access true
```

- **Purpose:** Peering must be configured on **both** VNets (one peering resource per direction) for the connection to become fully active — a commonly overlooked step, since creating peering from only one side leaves the connection in an incomplete/non-functional state.
- **Common error:** Forgetting the second, reverse-direction peering resource, resulting in connectivity that appears configured but doesn't actually work.

**Creating a Private Endpoint for a Storage Account:**

```bash
az network private-endpoint create \
  --resource-group rg-app-a \
  --name pe-storage-appadata \
  --vnet-name vnet-app-a \
  --subnet snet-data \
  --private-connection-resource-id "/subscriptions/<sub-id>/resourceGroups/rg-app-a/providers/Microsoft.Storage/storageAccounts/stappadata" \
  --group-id blob \
  --connection-name pe-connection-storage
```

- **Purpose:** Provisions a private IP address within `snet-data` representing the specific Storage Account's Blob service, implementing the private-endpoint architecture shown in Section 23.6's diagram.
- **Important arguments explained individually:**
  - `--group-id` — specifies which specific sub-service of the target resource the private endpoint targets (e.g., `blob` for Blob Storage specifically, as opposed to `file` or `queue` on the same Storage Account, which would each require their own private endpoint if needed).
- ⚠️ As emphasized in Section 23.5, this command alone doesn't complete the setup — an Azure Private DNS Zone must also be configured and linked to the VNet so that clients resolve the storage account's standard hostname to this new private IP; omitting this step is the most common reason a newly created Private Endpoint doesn't seem to "work" as expected.

## 23.8 Production & Enterprise Usage

Enterprises standardize on Private Link for PaaS services holding sensitive data (databases, storage accounts with confidential content) as part of a defense-in-depth network isolation strategy, often enforced via Azure Policy (Section 57) requiring Private Endpoints and disabling public network access by default for specific resource types. Service Endpoints remain useful for less sensitive scenarios where the simpler configuration and lack of DNS-management overhead outweigh the benefit of full private-IP isolation. Hub-and-spoke VNet Peering, combined with centralized firewall inspection for any necessary spoke-to-spoke or spoke-to-internet traffic (Section 22.4.2), is the standard enterprise network topology pattern, formalized as part of landing zone architecture (Part 13).

## 23.9 Security Considerations

- Private Link's ability to fully disable a PaaS resource's public endpoint is a significant security hardening step — for genuinely sensitive resources, eliminating public network exposure entirely (rather than merely restricting it via firewall rules while a public endpoint still technically exists) closes off an entire category of potential attack vectors.
- VNet Peering's non-transitivity (Section 23.3.2) is a security-relevant default, not just a technical limitation — it prevents unintended, implicit connectivity between spokes that haven't been deliberately configured to communicate.

## 23.10 Troubleshooting

| Symptom                                                                                            | Likely Cause                                                         | Fix                                                                                                                                           |
| -------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------- |
| VNet Peering appears configured but resources still can't communicate                              | Peering was only configured from one VNet's side, not both           | Create the corresponding peering resource on the other VNet as well                                                                           |
| Resources in Spoke A cannot reach resources in Spoke B, despite both being peered with the Hub     | VNet Peering is non-transitive by default                            | Configure direct Spoke-to-Spoke peering if needed, or route the traffic through the Hub's firewall/NVA via Route Tables                       |
| Traffic to a Storage Account with a Private Endpoint still appears to route to the public endpoint | DNS isn't resolving the storage account's hostname to the private IP | Verify Azure Private DNS Zone configuration and that it's correctly linked to the VNet                                                        |
| Cannot create VNet Peering between two VNets                                                       | Address spaces overlap                                               | Address space overlap must be resolved (typically requiring one VNet to be recreated with a non-overlapping range) before peering can succeed |

## 23.11 Interview Questions — Section 23

### 🎯 Intermediate

**Q: Is VNet Peering transitive? If VNet A is peered with VNet B, and VNet B is peered with VNet C, can A reach C?**

_Model answer:_ No, VNet Peering is non-transitive by default. A being peered with B, and B being peered with C, does not automatically allow A to reach C — that would require either a direct peering between A and C, or traffic being explicitly routed through B (for example, via a firewall/NVA in B with appropriate Route Tables configured to forward permitted traffic between A and C). This non-transitivity is actually often a desirable security property in hub-and-spoke designs, since it prevents unintended, implicit connectivity between spokes.

_What the interviewer is probing:_ this is one of the most commonly and specifically tested VNet Peering facts — getting it wrong suggests a real gap in hands-on peering experience.

### 🎯 Senior/Architect

**Q: A team wants to connect their application to an Azure SQL Database with the strongest possible network isolation — no public internet exposure at all. Walk through your recommended approach and why it's better than the alternatives.**

_Model answer:_ I'd implement Private Link via a Private Endpoint for the Azure SQL Database, provisioning a private IP address for the database within the application's VNet, and would then disable the database's public network access entirely, ensuring there's no public endpoint left exposed at all — not merely a public endpoint restricted by firewall rules, but genuinely no public path to the resource. This is stronger than using a Service Endpoint alone, since a Service Endpoint only optimizes the network path to the database's still-public IP address and requires the resource's public endpoint to remain reachable (even if firewall-restricted) rather than eliminating it. I'd ensure an Azure Private DNS Zone is correctly configured and linked to the VNet so that the application's connection string, using the database's standard hostname, correctly resolves to the new private IP rather than inadvertently falling back to the public endpoint if DNS isn't set up correctly — this DNS step is the most common point of failure in Private Link implementations and needs explicit verification, not just assumption that it works once the private endpoint resource itself is created. If the application also needs to be reachable from an on-premises network, I'd note that this Private Link setup, being a genuine private VNet IP, would also be reachable via the organization's existing hybrid connectivity (VPN or ExpressRoute, Section 26) without any additional configuration specific to the database, unlike a Service Endpoint-based approach.

_What the interviewer is probing:_ whether the candidate can correctly distinguish Private Link from Service Endpoints at a functional level, articulate specifically why Private Link achieves stronger isolation, and demonstrates awareness of the DNS configuration step that's easy to overlook but essential for the solution to actually work as intended.

## 23.12 Common Misconceptions

- **"VNet Peering is transitive, so peering with a hub gives spokes access to each other automatically."** False — this is one of the most consequential VNet Peering misconceptions, and assuming it's true can lead to either broken connectivity expectations or, worse, an incorrect assumption about network isolation between spokes.
- **"Service Endpoints and Private Link accomplish the same thing, just with different setup steps."** False — they provide meaningfully different isolation guarantees; Service Endpoints optimize the path to a still-public endpoint, while Private Link provides an actual private IP address and can fully eliminate public exposure.

## 23.13 Key Takeaways

- 🔑 VNet Peering connects VNets over Microsoft's private backbone network but is non-transitive by default — peering with a shared hub does not automatically grant spoke-to-spoke connectivity.
- 🔑 Service Endpoints optimize the network path to a PaaS service's still-public endpoint; Private Link/Private Endpoints provision an actual private IP address for the service within your VNet, enabling full public-endpoint elimination.
- 🔑 Private Link requires correct DNS configuration (typically via Azure Private DNS Zones) to actually redirect traffic to the private IP — a frequently overlooked but essential implementation step.
- 🔑 Hub-and-spoke topology, combined with centralized firewall inspection for any required spoke-to-spoke traffic, is the standard enterprise VNet architecture pattern.

## 23.14 Related Concepts (Next Up)

Section 24 covers **Load Balancer (Layer 4) vs. Application Gateway (Layer 7)** — the traffic-distribution mechanisms that sit in front of the compute resources (VMs, VM Scale Sets, App Service) covered in Part 3, directing incoming traffic across multiple instances using the private networking foundation established in Sections 21-23.
