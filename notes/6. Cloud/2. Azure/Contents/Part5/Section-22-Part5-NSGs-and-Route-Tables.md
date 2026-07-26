# Section 22 — Subnets, Network Security Groups (NSGs), and Route Tables

## 1. Definition

**Plain language:** Network Security Groups are Azure's basic firewall — a list of allow/deny rules controlling what traffic can flow in and out of a subnet or a specific network interface. Route Tables control which path traffic actually takes as it leaves a subnet, letting you override Azure's default routing behavior when needed.

**Precise definition:** A **Network Security Group (NSG)** is a stateful, rule-based traffic filter evaluated against inbound and outbound traffic at either the subnet or network-interface level. A **Route Table (User-Defined Route table, UDR)** is a set of custom routing rules that override Azure's default system routes, controlling the next hop for traffic leaving a subnet.

## 2. Why It Exists / Problem It Solves

A VNet (Section 21) provides isolation and address space, but by itself doesn't restrict what traffic can flow between resources within it, or dictate any specific path traffic must take — by default, Azure provides basic connectivity (VNet-internal traffic flows freely, and Azure's system routes handle default internet/VNet routing sensibly) but this default openness is inappropriate for production security postures requiring the principle of least privilege applied to network traffic itself, not just to RBAC-controlled management operations (Section 8). NSGs solve the "what traffic should be allowed" problem; Route Tables solve the separate "what path should traffic take" problem — for example, forcing all outbound internet traffic through a centralized firewall appliance rather than allowing it to route directly to the internet from each subnet independently.

## 3. Network Security Groups (NSGs)

### 3.1 Rule Structure

Each NSG rule specifies: **Priority** (a number determining evaluation order — lower numbers are evaluated first, and the first matching rule wins, with evaluation stopping there), **Source** (IP range, service tag, or Application Security Group), **Destination** (similarly), **Port** (or port range), **Protocol** (TCP, UDP, or Any), and **Action** (Allow or Deny).

**Default rules:** Every NSG comes with a set of default rules (unmodifiable, but able to be overridden by higher-priority custom rules) that, in general terms, allow VNet-internal traffic and traffic from Azure's load balancer infrastructure, while denying inbound traffic from the internet by default — meaning production security postures typically involve **adding** explicit allow rules for legitimately required traffic (e.g., allowing inbound HTTPS on port 443 to a web-facing subnet) rather than needing to add deny rules to restrict an otherwise-open-by-default posture.

### 3.2 Stateful Behavior

NSGs are **stateful** — meaning if an inbound rule allows a connection, the corresponding outbound return traffic for that same connection is automatically allowed as well, without requiring a separate explicit outbound rule (and vice versa for outbound-initiated connections) — this mirrors standard firewall behavior familiar from on-premises networking and means NSG rule sets typically only need to explicitly address the traffic-initiating direction, not both directions of every legitimate conversation.

### 3.3 Association Levels

An NSG can be associated with a **subnet** (applying to all resources within it) or a specific **network interface** (applying to just that one resource) — both can be applied simultaneously, in which case traffic must be allowed by **both** the subnet-level and NIC-level NSG to actually pass, providing an additional layer of defense-in-depth if desired, though this dual-association pattern adds complexity and should be used deliberately rather than by default.

### 3.4 Application Security Groups (ASGs)

**Definition:** An Application Security Group lets you group VMs by application role (e.g., "web-tier-vms," "db-tier-vms") and reference that group directly in NSG rules, rather than having to specify individual IP addresses or ranges — allowing NSG rules to be written in terms of application roles ("allow web-tier to reach db-tier on port 1433") rather than raw IP addresses, which is both more readable and automatically stays correct as VMs are added or removed from a role, without requiring the NSG rule itself to be edited.

## 4. Route Tables (User-Defined Routes)

### 4.1 System Routes vs. User-Defined Routes

By default, Azure automatically creates **system routes** handling common cases sensibly: traffic to other resources within the same VNet routes directly, traffic destined for the internet routes directly to the internet, and traffic to a peered VNet or connected on-premises network routes appropriately once that connectivity is configured. A **User-Defined Route (UDR)**, contained within a **Route Table** associated with a subnet, overrides this default system routing behavior for specific address ranges, most commonly to force traffic through a **Network Virtual Appliance (NVA)** — a firewall or other traffic-inspection appliance — rather than taking the default direct path.

### 4.2 Common Use Case — Forced Tunneling / Hub-and-Spoke Firewall Inspection

**Definition:** "Forced tunneling" (or more generally, routing all outbound traffic through a central inspection point) uses a UDR to override the default direct-to-internet system route, instead directing all outbound internet-bound traffic from a spoke subnet through a central firewall/NVA sitting in a hub VNet (the hub-and-spoke pattern introduced in Section 21.6), ensuring all outbound traffic is inspected and filtered centrally rather than allowing each subnet's resources to reach the internet directly and independently.

**Why this matters:** Without a UDR forcing this centralized routing, NSGs alone can restrict which ports/protocols are allowed, but can't provide the deeper content inspection, threat intelligence-based filtering, and centralized logging that a dedicated firewall appliance (like Azure Firewall, covered in Part 11) provides — UDRs are what make it possible to actually force traffic through such an appliance rather than merely hoping application configuration sends it there voluntarily.

## 5. Architecture Diagram

```
Subnet "snet-frontend" (10.0.1.0/24)
 NSG "nsg-frontend":
   Priority 100: Allow Inbound TCP 443 from Internet (Any) → VNet
   Priority 110: Allow Inbound TCP 80  from Internet (Any) → VNet
   [Default rules: Allow VNet-internal, Deny Internet inbound otherwise]

Subnet "snet-backend" (10.0.2.0/24)
 NSG "nsg-backend":
   Priority 100: Allow Inbound TCP 1433 from ASG "asg-webtier" → ASG "asg-dbtier"
   [Default rules: Deny Internet inbound]
   — no rule allows direct internet inbound; only frontend can reach backend on 1433

Route Table "rt-spoke-outbound" (associated with snet-frontend AND snet-backend):
   Route: 0.0.0.0/0 → Next Hop: Virtual Appliance (Firewall IP in hub VNet)
   — overrides default direct-to-internet system route,
     forcing ALL outbound traffic through the central firewall for inspection
```

## 6. Configuration & Hands-On Example

**Creating an NSG with a rule allowing HTTPS inbound, and associating it with a subnet:**

```bash
az network nsg create --resource-group rg-myapp-prod --name nsg-frontend

az network nsg rule create \
  --resource-group rg-myapp-prod \
  --nsg-name nsg-frontend \
  --name allow-https-inbound \
  --priority 100 \
  --direction Inbound \
  --access Allow \
  --protocol Tcp \
  --destination-port-ranges 443 \
  --source-address-prefixes Internet

az network vnet subnet update \
  --resource-group rg-myapp-prod \
  --vnet-name vnet-prod \
  --name snet-frontend \
  --network-security-group nsg-frontend
```

- **Purpose:** Creates an NSG, adds an explicit rule allowing inbound HTTPS (port 443) from the internet, then associates the NSG with the frontend subnet from Section 21.5's example — implementing the security posture shown conceptually in Section 22.5's diagram.
- **Important arguments explained individually:**
  - `--priority` — lower numbers are evaluated first; setting this to `100` leaves room for additional rules to be inserted at lower-priority-number (higher-precedence) or higher-priority-number (lower-precedence) positions later without needing to renumber existing rules.
  - `--source-address-prefixes Internet` — uses Azure's built-in **service tag** for "the internet" rather than requiring an explicit, unwieldy enumeration of IP ranges; service tags (covering constructs like `Internet`, `VirtualNetwork`, `AzureLoadBalancer`, and many specific Azure service ranges) are a significant convenience and accuracy improvement over manually maintained IP lists.
- **Common error:** Forgetting to associate the NSG with a subnet or NIC after creating it — the NSG resource existing alone has no effect until explicitly associated.

**Creating a Route Table forcing outbound traffic through a firewall appliance:**

```bash
az network route-table create --resource-group rg-myapp-prod --name rt-spoke-outbound

az network route-table route create \
  --resource-group rg-myapp-prod \
  --route-table-name rt-spoke-outbound \
  --name default-via-firewall \
  --address-prefix 0.0.0.0/0 \
  --next-hop-type VirtualAppliance \
  --next-hop-ip-address 10.100.0.4

az network vnet subnet update \
  --resource-group rg-myapp-prod \
  --vnet-name vnet-prod \
  --name snet-frontend \
  --route-table rt-spoke-outbound
```

- **Purpose:** Creates a route sending all traffic (`0.0.0.0/0`, meaning "any destination not otherwise more specifically routed") to a specific IP address representing a firewall/NVA's internal interface, then associates this Route Table with the frontend subnet, forcing that subnet's outbound traffic through the appliance rather than taking Azure's default direct route.
- **Important arguments explained individually:**
  - `--next-hop-type VirtualAppliance` — indicates traffic should be sent to a specific IP address running a network appliance, as opposed to other next-hop types like `Internet` (direct default routing) or `VNetPeering` (routing toward a peered VNet, Section 23).

## 7. Production & Enterprise Usage

Enterprises apply NSGs systematically at the subnet level as a baseline (with NIC-level NSGs reserved for cases genuinely requiring per-resource-specific rules beyond the subnet baseline), using Application Security Groups to keep rules readable and maintainable as the environment grows, and enforce a **default-deny** posture for inbound traffic from the internet, with only explicitly required ports/protocols allowed. Route Tables forcing traffic through a centralized firewall (Azure Firewall or a third-party NVA, Part 11) are standard in hub-and-spoke enterprise topologies, providing centralized traffic inspection, logging, and threat-intelligence-based filtering that NSGs alone cannot provide — NSGs and centralized firewall inspection are complementary, not redundant, layers of the same defense-in-depth strategy.

## 8. Security Considerations

- NSG rule review should be a regular practice — overly permissive rules (e.g., allowing broad port ranges or `Any` source when a specific, narrower rule would suffice) accumulate over time and represent unnecessary attack surface; periodic audits should tighten rules to the minimum necessary.
- Relying solely on NSGs without any centralized inspection (Route Tables forcing traffic through a firewall) means each subnet's traffic filtering is independent and lacks the deeper content-inspection and centralized-visibility benefits a dedicated firewall appliance provides — mature enterprise security postures typically layer both.
- Management ports (SSH port 22, RDP port 3389) should never be directly allowed from the internet in an NSG rule; secure remote access should instead use a bastion service (Azure Bastion, covered in Part 11) or a VPN connection.

## 9. Performance Considerations

Forcing traffic through a centralized firewall/NVA via Route Tables introduces an additional network hop and processing step compared to direct routing — this is a deliberate, accepted trade-off (security/inspection benefit versus a small latency/throughput cost), but the firewall appliance itself must be sized appropriately to handle the aggregated traffic volume from all the spoke subnets routing through it, or it can become a genuine bottleneck for the entire hub-and-spoke topology.

## 10. Monitoring

**NSG Flow Logs** record every allowed and denied connection evaluated by an NSG's rules, providing detailed traffic visibility essential both for troubleshooting unexpected connectivity failures (was a specific connection denied, and by which rule?) and for security monitoring (are there patterns of denied connection attempts suggesting reconnaissance or attack activity?) — this connects directly to the broader security monitoring capabilities covered in Part 11.

## 11. Troubleshooting

| Symptom                                                                | Likely Cause                                                                                                                      | Fix                                                                                                                              |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Expected traffic is unexpectedly blocked                               | An NSG rule (subnet-level, NIC-level, or a higher-priority deny rule) is blocking it                                              | Review NSG Flow Logs or use Azure's Network Watcher "IP flow verify" tool to identify exactly which rule is responsible          |
| Traffic that should be inspected by a central firewall is bypassing it | No Route Table associated with the relevant subnet, or the UDR's address prefix doesn't cover the actual destination              | Verify Route Table association and that the `0.0.0.0/0` (or more specific) route correctly covers the intended traffic           |
| A newly added NSG rule doesn't seem to take effect                     | A higher-priority (lower-number) rule is matching first and already allowing/denying the traffic before the new rule is evaluated | Review rule priorities; remember that NSG rule evaluation stops at the first match, so rule order/priority matters significantly |

## 12. Interview Questions — Section 22

### 🎯 Intermediate

**Q: What does it mean that Network Security Groups are "stateful," and why does this matter?**

_Model answer:_ Stateful means that once an NSG rule allows an inbound (or outbound) connection to be established, the corresponding return traffic for that same connection is automatically permitted, without needing a separate explicit rule for the reverse direction. This matters because it significantly simplifies rule management — you generally only need to write rules addressing the traffic-initiating direction of a legitimate conversation, rather than manually crafting matching allow rules for both directions of every permitted connection, which would be considerably more error-prone and harder to maintain.

_What the interviewer is probing:_ whether the candidate understands stateful vs. stateless firewall behavior conceptually, a foundational networking concept relevant well beyond just Azure specifically.

### 🎯 Senior

**Q: Design a network security approach for a three-tier application (web, application, database tiers) deployed across separate subnets, ensuring the database tier is never directly reachable from the internet.**

_Model answer:_ I'd place each tier in its own subnet, with NSGs applied at the subnet level enforcing a default-deny posture for inbound internet traffic. The web-tier subnet's NSG would allow inbound HTTPS (443) from the internet specifically. The application-tier subnet's NSG would allow inbound traffic only from the web-tier subnet (using an Application Security Group for the web tier, rather than hardcoded IP ranges, so the rule remains correct as web-tier VM instances scale up or down) on whatever port the application-tier service listens on — critically, with no rule allowing direct internet inbound access at all. The database-tier subnet's NSG would similarly allow inbound traffic only from the application-tier's Application Security Group on the database's specific port (e.g., 1433 for SQL Server), again with no internet-facing rule whatsoever. I'd also layer a Route Table forcing all outbound internet-bound traffic from all three subnets through a centralized firewall appliance in a hub VNet, ensuring even legitimate outbound traffic (like software update checks) is inspected and logged centrally, and I'd avoid ever allowing direct SSH/RDP management access to any tier from the internet, instead using Azure Bastion (Part 11) for secure administrative access. This layered approach — subnet segmentation, ASG-based least-privilege NSG rules per tier, and centralized outbound inspection — implements defense in depth so that even if the web tier were compromised, the attacker's lateral movement toward the database tier would be constrained by the application-tier NSG boundary rather than being able to reach the database directly.

_What the interviewer is probing:_ whether the candidate can design a complete, layered, tier-appropriate network security architecture using the specific mechanisms covered (NSGs, ASGs, Route Tables, centralized firewall) rather than describing security in only vague, generic terms — a strong signal of genuine hands-on network security design experience.

## 13. Common Misconceptions

- **"NSGs alone provide the same protection as a dedicated firewall appliance."** False — NSGs provide basic, stateful, port/protocol/source-based filtering; a dedicated firewall (Azure Firewall or a third-party NVA) typically adds deeper content inspection, threat intelligence integration, and centralized logging that NSGs don't provide on their own; the two are complementary, not interchangeable.
- **"You need to write a separate NSG rule for return traffic on an allowed connection."** False — NSGs are stateful (Section 22.3.2); return traffic for an already-allowed connection is handled automatically.

## 14. Key Takeaways

- 🔑 NSGs are stateful, priority-ordered, allow/deny traffic filters applied at the subnet or NIC level, with default rules generally denying inbound internet traffic unless explicitly allowed.
- 🔑 Application Security Groups let NSG rules reference application roles rather than raw IP addresses, improving readability and automatically staying correct as resources scale.
- 🔑 Route Tables (User-Defined Routes) override Azure's default system routing, most commonly used to force traffic through a centralized firewall/NVA for inspection in a hub-and-spoke topology.
- 🔑 NSGs and centralized firewall inspection (via Route Tables) are complementary layers of defense in depth, not redundant alternatives to each other.

## 15. Related Concepts (Next Up)

Section 23 covers **VNet Peering and Service Endpoints/Private Link** — the mechanisms for connecting separate VNets to each other and for privately reaching Azure PaaS services (like Storage Accounts or Azure SQL Database) without traffic ever traversing the public internet, extending the single-VNet networking model just covered into multi-VNet and hybrid-service architectures.
