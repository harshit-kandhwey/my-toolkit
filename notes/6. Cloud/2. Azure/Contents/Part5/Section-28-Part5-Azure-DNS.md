# Section 28 — Azure DNS (Public Zones & Private DNS Zones)

## 1. Definition

**Plain language:** Azure DNS is Azure's service for hosting DNS domains — translating human-readable names (like `www.contoso.com`) into IP addresses. It comes in two flavors: public DNS zones for internet-facing domains anyone can resolve, and private DNS zones for name resolution that only works within your own private Azure network.

**Precise definition:** Azure DNS is a hosting service for DNS domains, providing name resolution using Microsoft's global network of DNS servers for high availability and performance. **Public DNS Zones** host domains resolvable from anywhere on the public internet. **Private DNS Zones** provide name resolution scoped to one or more linked Virtual Networks, not resolvable from the public internet, and are the specific mechanism required to correctly resolve Private Link endpoints (introduced in Section 23.5) to their private IP addresses.

## 2. Why It Exists / Problem It Solves

Every networking concept covered throughout this Part — VNets, Load Balancers, Application Gateway, Front Door, Private Link — ultimately needs a reliable way for clients to translate a domain name into the correct IP address, and this need differs meaningfully between public-facing and private/internal scenarios. Public DNS Zones solve the standard "host my domain's DNS records so the world can find my website" problem, which organizations previously needed a separate third-party DNS provider for even when the rest of their infrastructure ran on Azure. Private DNS Zones solve a distinct and increasingly important problem specific to cloud architectures: ensuring that internal, VNet-scoped name resolution (including, critically, Private Link endpoint resolution) works correctly and privately, without requiring internal hostnames to be either publicly resolvable (a potential information-disclosure and security concern) or manually managed via static host-file-style configuration across every client.

## 3. Public DNS Zones

### 3.1 Core Concepts

**Definition:** A Public DNS Zone hosts the DNS records for a specific domain (e.g., `contoso.com`), with Azure DNS's global anycast network of name servers serving resolution requests for that domain from anywhere on the internet.

**Standard record types supported:** Azure DNS supports the standard DNS record types any DNS host would — **A records** (mapping a name to an IPv4 address), **AAAA records** (IPv6 address), **CNAME records** (an alias pointing to another domain name), **MX records** (mail server routing), **TXT records** (arbitrary text, commonly used for domain verification or SPF/email-authentication purposes), and others.

**Delegation:** To actually use Azure DNS for a domain, the domain's registrar (wherever it was purchased/registered) must be configured with **NS (nameserver) records** pointing to the specific name servers Azure DNS assigns to that zone — this delegation step is what actually routes DNS queries for the domain to Azure DNS's servers rather than wherever the domain was previously hosted, and is a manual, one-time step performed at the domain registrar, separate from Azure DNS zone configuration itself.

### 3.2 Alias Records

**Definition:** Azure DNS supports a special **Alias record** type that can point directly to certain Azure resources (a Public IP address, an Azure Front Door endpoint, a Traffic Manager profile) rather than to a static IP or hostname — the key benefit being that if the underlying Azure resource's IP address changes, the Alias record automatically reflects the change without requiring manual DNS record updates, unlike a standard A record which would need to be manually updated if the target IP changed.

## 4. Private DNS Zones

### 4.1 Core Concepts

**Definition:** A Private DNS Zone provides name resolution for one or more **linked** Virtual Networks, resolving names only for clients within those linked VNets (or networks connected to them via peering/hybrid connectivity with appropriate DNS configuration) — completely inaccessible from the public internet.

**Why linked, not just deployed:** A Private DNS Zone must be explicitly **linked** to each VNet that should use it for resolution — this linking step is what actually connects the zone's records to a specific VNet's DNS resolution behavior, and a zone can be linked to multiple VNets simultaneously, enabling shared internal name resolution across a hub-and-spoke topology (Section 21.6) from one central zone rather than duplicating records per VNet.

### 4.2 Auto-Registration

Private DNS Zones support an optional **auto-registration** feature for VM hostnames specifically — when enabled on a linked VNet, VMs deployed into that VNet automatically get an A record created in the Private DNS Zone reflecting their private IP address, without manual DNS record management, keeping internal VM name resolution current automatically as VMs are created, deleted, or have their IP addresses change.

### 4.3 Private Link Integration (Critical Connection to Section 23.5)

As introduced in Section 23.5, Private Link/Private Endpoints require correct DNS configuration to actually function as intended — when a Private Endpoint is created for a PaaS resource (like a Storage Account), a specific Private DNS Zone (following a predictable, resource-type-specific naming convention, such as `privatelink.blob.core.windows.net` for Blob Storage) must be created (or an existing one used) and linked to the relevant VNet(s), with an A record mapping the PaaS resource's standard hostname to its new private IP address. This is precisely what ensures that when an application resolves `mystorageaccount.blob.core.windows.net`, it receives the private IP address (routed privately within the VNet) rather than the resource's public IP address — without this specific Private DNS Zone configuration, traffic would continue resolving to and using the public endpoint even after a Private Endpoint has been technically created, silently undermining the network isolation the Private Endpoint was meant to provide.

⚠️ The specific required Private DNS Zone names for each Azure service type (e.g., `privatelink.blob.core.windows.net` for Blob Storage, a different specific zone name for Azure SQL Database, and so on) are defined by Microsoft and must match exactly — verify the current, correct zone name for each specific service type against official documentation when configuring Private Link, since using an incorrect zone name silently fails to achieve the intended private resolution.

## 5. Architecture Diagram

```
Public DNS Zone "contoso.com" (hosted in Azure DNS)
 ├── A record: www.contoso.com → Public IP of Application Gateway/Front Door
 ├── Alias record: app.contoso.com → Azure Front Door endpoint (auto-updates if FD's address changes)
 └── (Delegated via NS records at the domain registrar)

Private DNS Zone "privatelink.blob.core.windows.net" (linked to vnet-app-a and vnet-hub)
 └── A record: stappadata.blob.core.windows.net → 10.1.1.10 (Private Endpoint IP, Section 23.7)
       — only resolvable by clients within vnet-app-a or vnet-hub

Private DNS Zone "internal.contoso.local" (linked to vnet-hub, vnet-app-a, vnet-app-b; auto-registration enabled)
 ├── A record: vm-web-01.internal.contoso.local → 10.1.1.4  (auto-registered)
 └── A record: vm-db-01.internal.contoso.local  → 10.1.2.4  (auto-registered)
```

## 6. Configuration & Hands-On Example

**Creating a Public DNS Zone and an A record:**

```bash
az network dns zone create --resource-group rg-dns --name contoso.com

az network dns record-set a add-record \
  --resource-group rg-dns \
  --zone-name contoso.com \
  --record-set-name www \
  --ipv4-address 20.185.xx.xx
```

- **Purpose:** Creates a public DNS zone for `contoso.com`, then adds an A record so `www.contoso.com` resolves to a specific public IP address.
- **Next required step (not shown):** The domain registrar must be updated with the NS records Azure DNS assigns to this zone (retrievable via `az network dns zone show`) for this configuration to actually take effect for internet queries — creating the zone in Azure alone doesn't redirect queries here until delegation is completed at the registrar.

**Creating a Private DNS Zone, linking it to a VNet, and adding a Private Link A record:**

```bash
az network private-dns zone create \
  --resource-group rg-app-a \
  --name "privatelink.blob.core.windows.net"

az network private-dns link vnet create \
  --resource-group rg-app-a \
  --zone-name "privatelink.blob.core.windows.net" \
  --name link-vnet-app-a \
  --virtual-network vnet-app-a \
  --registration-enabled false

az network private-dns record-set a add-record \
  --resource-group rg-app-a \
  --zone-name "privatelink.blob.core.windows.net" \
  --record-set-name stappadata \
  --ipv4-address 10.1.1.10
```

- **Purpose:** Creates the specific, correctly-named Private DNS Zone required for Blob Storage Private Link resolution (per Section 28.4.3), links it to the application VNet, and adds the A record mapping the storage account's hostname prefix to its Private Endpoint IP — completing the Private Endpoint configuration started in Section 23.7's example.
- **Important arguments explained individually:**
  - `--registration-enabled false` — auto-registration (Section 28.4.2) is a VM-hostname feature and isn't relevant/applicable to this Private Link-specific zone, so it's explicitly disabled here.
- ⚠️ In practice, Azure can automate much of this Private Link DNS record creation automatically when a Private Endpoint is created with DNS integration configured — verify current tooling capabilities (which have improved to reduce manual DNS record management for Private Link scenarios) against official documentation, since manually replicating every step shown here may not always be necessary with current tooling.

## 7. Production & Enterprise Usage

Enterprises typically centralize Private DNS Zone management within the hub VNet's resource group (or a dedicated shared-services subscription), linking each relevant zone to every spoke VNet that needs it, rather than each application team independently managing their own DNS zones — this ensures consistent internal name resolution and Private Link functionality across the entire hub-and-spoke estate from a single, centrally-governed source, and avoids duplicated or inconsistent DNS configuration across VNets. Public DNS Zone management, while it can technically be delegated to individual teams, is also commonly centralized for larger domains to maintain consistency and avoid accidental misconfiguration of a shared, business-critical public domain.

## 8. Security Considerations

- Correct Private DNS Zone configuration is not merely an operational nicety for Private Link — it's the actual mechanism that determines whether traffic uses the private, isolated path or falls back to a resource's public endpoint; misconfigured or missing Private DNS Zones can silently undermine an otherwise well-designed network isolation strategy without any obvious error, making DNS configuration verification an essential, not optional, step when auditing Private Link security posture.
- Public DNS Zone records should be reviewed periodically for stale or unnecessary entries (e.g., an old A record pointing to a decommissioned resource) which could represent an information-disclosure risk or, in worse cases, a "dangling DNS" vulnerability where an attacker could claim an IP address or resource an old DNS record still points to.

## 9. Performance Considerations

Azure DNS's global anycast network generally provides fast, low-latency resolution for public zones from anywhere in the world without additional configuration; for Private DNS Zones, resolution performance is effectively local to the VNet/region and not typically a meaningful bottleneck, though very high DNS query volume scenarios should still be considered as part of overall capacity planning like any other dependency.

## 10. Monitoring

DNS query analytics and zone configuration changes can be monitored via Azure Monitor and activity logs (Part 10); given how silently a DNS misconfiguration can undermine Private Link's intended isolation (Section 28.8), some organizations specifically monitor for unexpected changes to Private DNS Zone records tied to sensitive Private Link endpoints as part of their broader security monitoring posture (Part 11).

## 11. Troubleshooting

| Symptom                                                                                       | Likely Cause                                                                            | Fix                                                                                                                                                                                           |
| --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Public DNS zone created and records added, but domain still doesn't resolve from the internet | Domain registrar not yet updated with Azure DNS's NS records (delegation not completed) | Update the domain registrar's nameserver configuration to point to the NS records Azure DNS assigned to the zone                                                                              |
| Private Endpoint created, but application still connects to the resource's public IP          | Private DNS Zone missing, not linked to the correct VNet, or missing/incorrect A record | Verify the specific required Private DNS Zone name (per service type), confirm it's linked to the client's VNet, and confirm the A record correctly maps to the Private Endpoint's private IP |
| VM hostname resolution not working automatically for newly created VMs                        | Auto-registration not enabled on the Private DNS Zone's VNet link                       | Enable `--registration-enabled true` on the relevant VNet link, or manually create the A record if auto-registration isn't desired                                                            |

## 12. Interview Questions — Section 28

### 🎯 Intermediate

**Q: Why is a Private DNS Zone necessary for Private Link to actually work, and what happens if it's misconfigured?**

_Model answer:_ A Private Endpoint provisions a private IP address for a PaaS resource within a VNet, but applications typically connect using the resource's standard hostname (like `mystorageaccount.blob.core.windows.net`), not a raw IP address. Without a correctly configured Private DNS Zone mapping that hostname to the new private IP, DNS resolution continues returning the resource's public IP address, meaning traffic still routes to the public endpoint even though a Private Endpoint technically exists — silently undermining the network isolation the Private Endpoint was meant to provide, without necessarily producing any obvious error. A correctly configured and linked Private DNS Zone, with the appropriate A record, is what actually redirects that hostname resolution to the private IP, completing the Private Link configuration.

_What the interviewer is probing:_ whether the candidate understands that Private Link is a two-part configuration (the Private Endpoint itself, plus DNS) and that omitting the DNS piece results in a silent, easy-to-miss failure to achieve the intended isolation — a genuinely common real-world misconfiguration.

### 🎯 Senior

**Q: How would you design DNS management for an enterprise with a hub-and-spoke network topology, multiple application teams, and a mix of public-facing and Private Link-dependent internal services?**

_Model answer:_ I'd centralize Private DNS Zone management within the hub's shared-services resource group, creating the specific, correctly-named zones required for each Azure PaaS service type used with Private Link across the organization (e.g., the Blob Storage-specific zone, the Azure SQL-specific zone, and so on), and linking each zone to every spoke VNet that has resources needing to resolve those specific Private Link endpoints — rather than having each application team independently create and manage their own potentially inconsistent or incorrectly-named zones. For internal VM/service name resolution not related to Private Link specifically, I'd similarly centralize a private zone (or zones) for internal hostname resolution, using auto-registration where appropriate to reduce manual DNS record maintenance as VMs are created and destroyed. Public-facing DNS would be managed as a centrally-governed public zone for the organization's primary domain(s), with delegation to Azure DNS completed once at the registrar, and any subdomain delegation to individual application teams handled carefully and deliberately rather than granting broad, unrestricted public DNS zone management access to every team. I'd also establish a periodic review process for both public and private DNS records to catch stale entries, particularly any that could represent a dangling-DNS security risk or a Private Link isolation gap if a zone or link were accidentally removed or misconfigured.

_What the interviewer is probing:_ whether the candidate can design a centrally-governed, consistent DNS management strategy appropriate for a multi-team enterprise environment, correctly distinguishing the different DNS needs (public-facing, internal VM resolution, and Private Link-specific resolution) rather than treating DNS as a single undifferentiated concern.

## 13. Common Misconceptions

- **"Creating a Private Endpoint automatically handles all necessary DNS configuration."** Not always true, and historically a very common gap — while current tooling has improved integration in many scenarios, DNS configuration (the correct Private DNS Zone, linked to the right VNet, with the correct record) has traditionally been a distinct, easy-to-overlook step separate from Private Endpoint creation itself, and should always be explicitly verified.
- **"Public and Private DNS Zones are just the same feature applied at different scopes."** They share underlying Azure DNS infrastructure concepts, but serve fundamentally different purposes (internet-wide resolution vs. VNet-scoped private resolution) with different linking/delegation mechanisms and should be understood as distinct tools for distinct needs.

## 14. Key Takeaways

- 🔑 Public DNS Zones host internet-resolvable domain records, requiring delegation (NS records) at the domain registrar to actually take effect.
- 🔑 Private DNS Zones provide VNet-scoped, non-internet-resolvable name resolution, and must be explicitly linked to each VNet that should use them.
- 🔑 Private DNS Zones are the essential, often-overlooked second half of a correct Private Link configuration — without the correct zone, link, and record, traffic silently continues using the resource's public endpoint despite a Private Endpoint existing.
- 🔑 Auto-registration simplifies internal VM hostname resolution by automatically creating/maintaining A records as VMs are created or removed.
- 🔑 Enterprise DNS management is typically centralized (in the hub/shared-services scope) for consistency across a hub-and-spoke topology, rather than delegated independently per application team.

## 15. Related Concepts / Part 5 Wrap-Up

This completes **Part 5 — Networking**, covering VNets, NSGs/Route Tables, VNet Peering/Private Link, Load Balancer/Application Gateway, Front Door/CDN, VPN Gateway/ExpressRoute, and Azure DNS — the full networking foundation underlying every compute (Part 3) and storage (Part 4) resource covered so far, and essential context for every subsequent Part. **Part 6 — Databases & Data Services** begins next with Section 29, covering Azure SQL Database & Managed Instance, the first of Azure's managed relational database offerings, building on the compute, storage, and now networking foundations established across Parts 3 through 5.
