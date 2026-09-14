# Section 42 (Part 5): Layer 2 vs. Layer 3 Switching

## 1. Definition

**Plain language:** Every device this Part has called a "switch" so far has actually been doing pure Layer 2 work — forwarding by MAC address within one broadcast domain. But most switches sold and deployed today can do more than that: they can also make IP-address-based routing decisions, in hardware, at switch speed, blurring the historical line between "switch" and "router." Understanding exactly what "Layer 3 switch" means — and what it doesn't mean — resolves a huge amount of vocabulary confusion in real network documentation and job postings.

**Precise definition:** A **Layer 2 switch** forwards Ethernet frames exclusively based on destination MAC address ([§36](Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md)) within a single broadcast domain or VLAN, with no awareness of IP addressing or routing at all — everything in [§35](Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md) through [§41](Section-41-Part5-Link-Aggregation-LACP-EtherChannel-Concepts.md) describes Layer 2 switching behavior. A **Layer 3 switch** is a switch that additionally implements IP routing functionality **in hardware** (typically via **ASICs**, Application-Specific Integrated Circuits, performing route lookups at line rate) rather than relying on a general-purpose CPU running routing software — it can hold IP interfaces (**SVIs**, Switched Virtual Interfaces, one per VLAN, as introduced in [§39](Section-39-Part5-Inter-VLAN-Routing.md)) and forward packets between them using a real IP routing table, at speeds comparable to its Layer 2 forwarding. This is architecturally different from a traditional **router**, which historically performed routing in general-purpose CPU software rather than dedicated hardware — though the practical distinction has blurred further as modern routers also increasingly use hardware-accelerated forwarding paths.

> 💡 **Tip:** The cleanest test for "is this a Layer 2 switch, Layer 3 switch, or router" in a real conversation: ask what it forwards on and where that forwarding decision happens. Pure MAC-address forwarding within one broadcast domain = Layer 2 switch. IP-address forwarding between VLANs/subnets, done in switch ASIC hardware at line rate = Layer 3 switch. The label "router" today mostly signals a device's role and feature set (WAN connectivity, NAT, complex routing protocol support, VPN termination) rather than a strict statement about software-vs-hardware forwarding, since that line has blurred considerably.

## 2. Why This Matters

- **This directly resolves the router-on-a-stick vs. Layer 3 switch trade-off from [§39](Section-39-Part5-Inter-VLAN-Routing.md)** by naming and formalizing exactly what a Layer 3 switch is and why it removes the shared-trunk bandwidth bottleneck — this section is where that comparison gets its full technical grounding.
- **Modern data center and campus network hardware overwhelmingly blends these roles** — nearly every enterprise-grade access/distribution switch sold today is a Layer 3 switch capable of both functions, and reading a vendor datasheet or a job description competently requires knowing what "Layer 3 switching" and "Layer 2 switching" each specifically mean.
- **This is the conceptual foundation for leaf-spine data center architectures**, which push Layer 3 routing much closer to the network edge (often all the way to the top-of-rack switch) specifically to avoid the scaling limits of large Layer 2 domains and Spanning Tree Protocol's single-active-path constraint ([§40](Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md)) — a design pattern that only makes sense once Layer 2 vs. Layer 3 switching is well understood.
- **Understanding the ASIC-based, hardware-accelerated nature of Layer 3 switching explains real performance characteristics** — why a Layer 3 switch can route at multi-gigabit line rate across many ports simultaneously in a way that would be prohibitively expensive for a CPU-software-based router to match at the same price point.
- **Interview and architecture-review fluency** — "when would you use a router instead of a Layer 3 switch" is a legitimate, common question, and answering it requires the specific distinctions this section draws (WAN/complex-protocol support vs. line-rate LAN/data-center forwarding).

## 3. Prerequisites and Dependencies

Builds directly on [§39](Section-39-Part5-Inter-VLAN-Routing.md) (Inter-VLAN Routing), which introduced SVIs and the router-on-a-stick vs. Layer 3 switch contrast this section formalizes fully. [§35](Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md) (hubs/switches/bridges) and [§36](Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md) (MAC tables) are the Layer 2 foundation this section contrasts against. [§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md) and [§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md) (broadcast domains and VLANs) matter because Layer 3 switching is specifically the mechanism that routes between the broadcast domains/VLANs those sections established. [§25](../Part4/Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md) (Part 4, routing fundamentals) is useful general routing background, applied here specifically to the hardware/architectural distinction between where routing happens. [§43](Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md) builds on this section directly, since understanding the Layer 2/Layer 3 switching boundary within one physical device is the necessary foundation for understanding how SDN and overlay networks abstract that boundary away entirely across many devices.

## 4. Architecture / Conceptual Diagram

```text
   LAYER 2 SWITCH                          LAYER 3 SWITCH                    ROUTER
   (MAC-address forwarding only,           (MAC forwarding PLUS IP           (traditionally
    one broadcast domain/VLAN)              routing between VLANs,           CPU-software
                                             in ASIC hardware)                 based routing,
   ┌────────────────────┐                  ┌────────────────────────┐        richer WAN/
   │  Forwards by:       │                  │  Forwards by:            │        protocol
   │  destination MAC    │                  │  MAC (within a VLAN)     │        feature set)
   │                     │                  │  OR IP (between VLANs,  │
   │  No IP awareness    │                  │  via SVIs) — decided     │       ┌──────────┐
   │  at all              │                  │  per-packet, in hardware│       │  WAN link │
   └────────────────────┘                  └────────────────────────┘       │  BGP/OSPF │
                                                                              │  VPN term.│
                                                                              └──────────┘

   PACKET FLOW THROUGH A LAYER 3 SWITCH (simplified)

   Frame arrives on Port 1 (VLAN 10)
        │
        ▼
   Destination MAC == this switch's own SVI MAC for VLAN 10?
        │                                   │
       NO                                  YES
        │                                   │
        ▼                                   ▼
   Layer 2 forward within VLAN 10    Strip frame, examine IP header,
   (§35, §36 — pure MAC lookup)      consult IP routing table,
                                     re-encapsulate into a NEW frame
                                     for the destination VLAN's SVI,
                                     forward out the correct port —
                                     ALL DONE IN HARDWARE (ASIC),
                                     not general-purpose CPU software.
```

- **The decision of "Layer 2 forward or Layer 3 route" happens per-packet, automatically**, based on whether the frame's destination MAC address matches the switch's own SVI interface (meaning it needs routing) or a different host's MAC on the same VLAN (meaning plain Layer 2 forwarding suffices).
- **ASIC-based forwarding is the concrete engineering reason Layer 3 switches achieve router-like functionality at switch-like line-rate speeds** — the routing table lookup and forwarding decision are implemented in dedicated hardware circuits rather than software running on a general-purpose CPU, which is fundamentally the same speed advantage switches have always had over general-purpose computers for Layer 2 forwarding, now extended to Layer 3.
- **Routers historically differentiated themselves on protocol richness and WAN connectivity**, not raw forwarding speed — complex routing protocols (BGP, [§33](../Part4/Section-33-Part4-Route-Redistribution-and-Administrative-Distance.md) area), VPN termination, NAT, deep packet inspection, and WAN interface types (not just Ethernet) were traditionally router-only territory, though the line has blurred as both device categories have absorbed more of each other's capabilities over time.

## 5. Hands-On

### 5.1 Distinguishing Layer 2 and Layer 3 Interfaces on a Linux Host

**Purpose:** Recognize the equivalent of a Layer 2 vs. Layer 3 interface distinction directly on a Linux system, which mirrors the same conceptual split found on a physical Layer 3 switch.

**Syntax:**

```bash
ip link show          # Layer 2 view: interfaces, MAC addresses, link state
ip addr show           # Layer 3 view: IP addresses assigned to interfaces
```

**Example usage and expected output:**

```bash
$ ip link show eth0.10
6: eth0.10@eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT
    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff

$ ip addr show eth0.10
6: eth0.10@eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP
    inet 10.0.10.1/24 brd 10.0.10.255 scope global eth0.10
```

**Production usage example:** This same VLAN sub-interface (`eth0.10`), first introduced in [§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md) and used as a router-on-a-stick gateway in [§39](Section-39-Part5-Inter-VLAN-Routing.md), is functionally acting as this host's equivalent of a Layer 3 switch's SVI — a single interface that participates in Layer 2 (has a MAC address, receives frames) and Layer 3 (has an IP address, participates in routing) simultaneously; this is the exact same conceptual layering a Layer 3 switch implements internally in hardware, just implemented here in Linux kernel software instead.

**Common errors:** Assuming an interface having an IP address (`ip addr show` output) automatically means routing between it and other interfaces is enabled — as covered in [§39](Section-39-Part5-Inter-VLAN-Routing.md), IP forwarding (`net.ipv4.ip_forward`) must be explicitly enabled for the host to actually route packets between its interfaces, regardless of how many interfaces have IP addresses configured.

### 5.2 Comparing Route Lookup Speed Behavior Conceptually via `ip route`

**Purpose:** Inspect a host's IP routing table structure, which is functionally the same data structure (conceptually) that a Layer 3 switch's ASIC consults for hardware-accelerated forwarding decisions — understanding the software version clarifies what the hardware version is doing faster.

**Syntax:**

```bash
ip route show
ip route get <destination-ip>
```

**Example usage and expected output:**

```bash
$ ip route show
10.0.10.0/24 dev eth0.10 proto kernel scope link src 10.0.10.1
10.0.20.0/24 dev eth0.20 proto kernel scope link src 10.0.20.1
default via 203.0.113.1 dev eth0

$ ip route get 10.0.20.7
10.0.20.7 dev eth0.20 src 10.0.20.1
```

**Production usage example:** This exact routing-table-lookup-then-forward operation — matching a destination IP against the most specific route and determining an outgoing interface — is what a Layer 3 switch's ASIC performs for every routed packet at line rate; a software router or Linux host performs the identical logical operation, just in kernel software rather than dedicated hardware, which is the entire performance distinction covered in this section.

**Common errors:** Assuming route lookup speed is the only relevant difference between software and hardware routing — Layer 3 switch ASICs also handle the packet rewriting (TTL decrement, MAC header rewrite for the new destination VLAN) in the same hardware pipeline, which is part of why the aggregate throughput advantage is so large at scale, not just the table lookup step alone.

### 5.3 Identifying Whether a Given Piece of Network Hardware Is Performing Layer 2 or Layer 3 Forwarding for a Given Flow

**Purpose:** Use `traceroute` to empirically distinguish whether traffic between two hosts is staying within one broadcast domain (Layer 2 only, no hop shown) or crossing a Layer 3 boundary (a hop appears, indicating a router or Layer 3 switch SVI was involved).

**Syntax:**

```bash
traceroute <destination-ip>
```

**Example usage and expected output:**

```bash
$ traceroute 10.0.10.7      # same VLAN/subnet as source — pure Layer 2, no hops
traceroute to 10.0.10.7 (10.0.10.7), 30 hops max
 1  10.0.10.7 (10.0.10.7)  0.312 ms  0.298 ms  0.287 ms

$ traceroute 10.0.20.7      # different VLAN/subnet — Layer 3 hop visible
traceroute to 10.0.20.7 (10.0.20.7), 30 hops max
 1  10.0.10.1 (10.0.10.1)  0.401 ms  0.389 ms  0.375 ms     # the Layer 3 switch's SVI
 2  10.0.20.7 (10.0.20.7)  0.599 ms  0.588 ms  0.571 ms
```

**Production usage example:** This is a fast, definitive way to confirm whether two hosts believed to be on the same VLAN are actually communicating at pure Layer 2 (single hop shown as the destination itself) or are unexpectedly being routed (an intermediate hop appears) — a useful sanity check when validating a VLAN/subnet design matches what's actually deployed.

**Common errors:** Interpreting a single-hop traceroute result as proof two hosts are on the same VLAN specifically — it only proves no Layer 3 hop was involved; two hosts could theoretically be bridged together across a non-VLAN-aware Layer 2 extension technology and still show a single hop, so this check confirms "Layer 2 only," not the specific VLAN topology.

## 6. Production Usage Notes

- **The vast majority of modern enterprise and data center access/distribution switches ship as Layer 3-capable by default**, even when deployed purely for Layer 2 access-layer duty — knowing a switch is "Layer 3 capable" and knowing it is actually **configured** to route (SVIs assigned, IP forwarding enabled) are two different facts, and conflating them is a common documentation/inventory mistake.
- **Leaf-spine data center architectures push Layer 3 routing as close to the network edge as practical** (often to the top-of-rack leaf switch itself) specifically to avoid large Layer 2 domains and Spanning Tree's single-active-path limitation — every leaf-to-spine link becomes a routed Layer 3 link using ECMP (Equal-Cost Multi-Path routing) to actively use multiple redundant paths simultaneously, which STP alone cannot do ([§40](Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md)'s blocked-port model keeps redundant paths idle by design).
- **Traditional routers retain a real, distinct role for WAN connectivity, complex routing protocol implementations, and features like NAT/VPN termination/deep packet inspection** that Layer 3 switches are typically not designed or licensed for — the practical guidance in most real designs is "Layer 3 switch for LAN/data-center inter-VLAN routing at line rate; router (or a firewall/router combination appliance) for WAN edge and complex policy," not "replace all routers with Layer 3 switches everywhere."

## 7. Security Considerations

- **Every point in [§39](Section-39-Part5-Inter-VLAN-Routing.md)'s inter-VLAN routing security discussion (ACLs at the routing chokepoint) applies identically here, whether the routing device is a router-on-a-stick or a Layer 3 switch** — the specific hardware implementation doesn't change the fundamental need for policy enforcement between VLANs/subnets.
- **Layer 3 switch ACL/policy hardware capacity is a real, finite resource** (TCAM entries specifically), distinct from routing table capacity — a switch that can hold a large routing table may still have a much smaller limit on the number of ACL rules it can enforce at line rate, which matters directly for designs relying on granular per-VLAN or per-flow policy at this layer.
- **Because Layer 3 switches sit at the boundary between broadcast domains, misconfiguring their routing or ACL behavior has the same blast-radius characteristics as misconfiguring a router at the same position** — a permissive or incorrect SVI/ACL configuration undermines VLAN segmentation just as thoroughly as a misconfigured router-on-a-stick would.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                     | Likely Cause                                                                                       | Resolution Path                                                                                                          |
| --------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| Switch is "Layer 3 capable" per its datasheet but inter-VLAN traffic isn't routing | Layer 3 routing feature not actually enabled/licensed, or no SVIs configured on the switch          | Verify Layer 3 mode/license status; confirm SVIs are configured with correct IP addressing for each VLAN                     |
| Inter-VLAN ACL policy silently stops applying above a certain rule count           | TCAM (hardware ACL table) capacity exceeded on the Layer 3 switch                                    | Check hardware ACL/TCAM utilization; consolidate or simplify ACL rules; consider a platform with larger TCAM capacity for the design's actual policy needs |
| A device believed to require a full router for its function works fine on a Layer 3 switch | Overestimating the router-specific feature set actually needed — many "router" requirements are just inter-VLAN routing | Confirm actual functional requirements (WAN link type, specific routing protocols, NAT/VPN needs) against what the Layer 3 switch genuinely lacks, if anything |

## 9. Best Practices

- Explicitly document whether a given switch is deployed in pure Layer 2 access mode or actively performing Layer 3 routing (SVIs configured, IP forwarding active) — "Layer 3 capable" hardware and "Layer 3 configured" deployment are different facts that should never be conflated in network documentation.
- Reserve traditional routers (or router/firewall appliances) for WAN edge connectivity, complex routing protocol requirements, and NAT/VPN/deep packet inspection needs; use Layer 3 switches for LAN and data-center inter-VLAN routing where line-rate hardware forwarding is the priority.
- Monitor hardware ACL/TCAM utilization on Layer 3 switches separately from routing table capacity, since exhausting this specific, often much smaller, hardware resource is a distinct and easy-to-miss failure mode.
- In new data center designs, default to pushing Layer 3 routing to the access/leaf layer (routed access, leaf-spine with ECMP) rather than relying on large Layer 2 domains and Spanning Tree for redundancy at scale.

## 10. Common Anti-Patterns / Mistakes

- **Assuming "Layer 3 switch" and "router" are interchangeable terms for procurement or architecture purposes.** They overlap significantly in modern hardware but differ meaningfully in typical feature depth (WAN protocols, complex routing policy, NAT/VPN) — using the wrong device category for a genuinely router-specific requirement (like multi-provider BGP peering at a WAN edge) can be a costly mistake to unwind.
- **Deploying large, flat Layer 2 domains across an entire data center and relying purely on STP for redundancy**, when pushing routing (and therefore ECMP-based multi-path redundancy) closer to the access layer would scale better and avoid Spanning Tree's single-active-path limitation entirely.
- **Treating a switch's advertised routing table capacity as the only relevant hardware limit** without checking its separate (often much smaller) ACL/TCAM capacity, then being surprised when a design relying on granular per-VLAN policy hits a wall well before the routing table does.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a Layer 2 switch and a Layer 3 switch?"_
**Model answer:** A Layer 2 switch forwards traffic based purely on destination MAC address within a single broadcast domain or VLAN, with no awareness of IP addressing at all. A Layer 3 switch does everything a Layer 2 switch does, plus it can also route traffic between VLANs based on IP address, using dedicated hardware (ASICs) to do that routing at speeds comparable to its normal Layer 2 forwarding, rather than relying on a general-purpose CPU running routing software the way a traditional router historically did.
_What the interviewer is probing for:_ Whether the candidate understands Layer 3 switching as an addition to, not a replacement of, Layer 2 switching capability, and that the key differentiator from a router is the hardware-based forwarding path.

**🎯 Intermediate:** _"If a Layer 3 switch can route traffic between VLANs just like a router, why do routers still exist as a separate product category?"_
**Model answer:** Layer 3 switches excel specifically at high-speed, hardware-accelerated IP forwarding within a LAN or data center — routing between VLANs/subnets at line rate. Traditional routers have historically differentiated on a broader feature set that Layer 3 switches typically don't match: rich support for complex routing protocols and policies, WAN interface types beyond Ethernet, NAT, VPN termination, and deep packet inspection — capabilities more relevant at a network's edge connecting to other networks (the internet, other sites) than within a single LAN or data center. In practice the two categories overlap more than they used to, but the general guidance remains: Layer 3 switches for LAN/data-center inter-VLAN routing, routers (or router/firewall appliances) for WAN edge and complex policy needs.
_What the interviewer is probing for:_ Whether the candidate can articulate the actual differentiating feature set rather than claiming the two device types are now fully identical or completely different.

**🎯 Senior:** _"A team wants to replace their WAN edge router with a Layer 3 switch to reduce cost. What would you evaluate before agreeing to that change?"_
**Model answer:** I'd start by cataloging exactly what the current router is doing beyond basic IP forwarding — specifically checking for WAN-specific interface types (non-Ethernet links), the routing protocols in use and their complexity (full BGP table handling, for instance, has real hardware and software requirements many Layer 3 switches aren't built for), and any NAT, VPN termination, or deep packet inspection functionality it provides. If the router's role is purely internal inter-VLAN or inter-subnet routing on Ethernet links with straightforward routing needs, a Layer 3 switch is very likely a legitimate, cost-effective replacement. If the router is doing meaningful WAN-edge work — terminating an internet or MPLS circuit, running full BGP with an ISP, providing NAT/VPN for site connectivity — those are exactly the areas where a Layer 3 switch is typically not designed or licensed to match router functionality, and replacing it without verifying that could remove capabilities the business actually depends on. I'd make the recommendation contingent on that specific functional audit, not a blanket answer either way.
_What the interviewer is probing for:_ Whether the candidate resists giving a dogmatic yes/no answer and instead identifies the concrete functional checks (WAN interfaces, routing protocol complexity, NAT/VPN) that actually determine whether the substitution is safe.

**🎯 Architect:** _"You're designing a new data center's Layer 2/Layer 3 boundary — where in the topology do you place routing, and how does that decision relate to Spanning Tree Protocol and link aggregation from earlier in this Part?"_
**Model answer:** I'd default to a routed-access or leaf-spine design that pushes Layer 3 routing as close to the edge as practical — ideally to the leaf/top-of-rack switch itself — rather than a traditional design with large Layer 2 domains spanning many racks and Layer 3 routing only at a centralized core or distribution layer. The reasoning ties directly back to [§40](Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md): large Layer 2 domains need Spanning Tree Protocol to stay loop-free, and STP's fundamental limitation is that it keeps only one path active per tree, leaving redundant paths idle. By routing at the leaf layer instead, every leaf-to-spine connection becomes a Layer 3 link, and ECMP (Equal-Cost Multi-Path routing) can actively use multiple redundant paths simultaneously rather than blocking all but one — meaningfully better bandwidth utilization and faster failover than STP provides for the same redundant topology. Link aggregation ([§41](Section-41-Part5-Link-Aggregation-LACP-EtherChannel-Concepts.md)) still has a role within this design wherever genuinely parallel physical links exist between the same device pair (e.g., multiple links from a leaf to the same spine switch), bundled via LACP before ECMP is even considered across the logically aggregated link. The overall principle: minimize the size of Layer 2 domains (reducing reliance on STP) by routing as close to the edge as the workload's actual Layer 2 adjacency requirements allow, using Layer 3 switch hardware specifically because it can do this at line rate across every leaf switch in the fabric.
_What the interviewer is probing for:_ Whether the candidate can synthesize the whole Part's concepts (STP's limitations, LACP's role, Layer 3 switching's hardware speed) into one coherent, modern data center architecture decision, rather than treating each concept in isolation.

## 12. Common Misconceptions

1. **"A Layer 3 switch is just a router with a different name."** A Layer 3 switch is architecturally a switch with hardware-accelerated IP routing added on top of its Layer 2 capability — it typically lacks the broader WAN, complex-protocol, and NAT/VPN feature depth traditionally associated with routers, even though the line has blurred.
2. **"If a switch supports Layer 3 features, it's automatically routing traffic."** Layer 3 capability is a hardware/software feature; actually routing requires configuration (SVIs with IP addresses, IP forwarding enabled) — a Layer 3-capable switch deployed with none of that configured is still operating purely as a Layer 2 switch.
3. **"Layer 3 switches have unlimited or equivalent capacity for both routing tables and ACL rules."** These are typically separate hardware resources (routing table memory vs. TCAM for ACLs) with independent, often very different, capacity limits — exhausting one doesn't imply anything about the other.
4. **"Modern data centers still rely primarily on Spanning Tree Protocol for core redundancy."** Leading-edge data center designs increasingly push routing to the access/leaf layer specifically to replace STP's single-active-path model with ECMP's simultaneous multi-path routing — STP still matters at smaller scale and within Layer 2 domains, but it is not the primary redundancy mechanism in modern large-scale leaf-spine fabrics.

## 13. 🔑 Key Takeaways

- Layer 2 switching forwards by MAC address within one broadcast domain; Layer 3 switching adds hardware-accelerated (ASIC-based) IP routing between VLANs/subnets on top of that same device.
- The Layer 3 switch vs. traditional router distinction today is mostly about feature depth (WAN connectivity, complex routing protocols, NAT/VPN) rather than a strict software-vs-hardware forwarding line, though hardware-based forwarding remains the core architectural differentiator from a Layer 3 switch's Layer 2 switch ancestor.
- "Layer 3 capable" hardware and "Layer 3 configured" deployment are distinct facts — a switch can have the feature without it being active.
- Routing table capacity and ACL/TCAM capacity are separate, independently limited hardware resources on a Layer 3 switch.
- Modern large-scale data center designs increasingly push Layer 3 routing to the access/leaf layer specifically to replace Spanning Tree's single-active-path limitation with ECMP's simultaneous multi-path utilization.

## 14. Related Concepts & What's Next

[§39](Section-39-Part5-Inter-VLAN-Routing.md) is this section's direct prerequisite, having introduced SVIs and the router-on-a-stick contrast this section fully formalizes. [§40](Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md) and [§41](Section-41-Part5-Link-Aggregation-LACP-EtherChannel-Concepts.md) are directly relevant to the leaf-spine architecture discussion here, since pushing routing to the access layer is explicitly a response to Spanning Tree's limitations, while link aggregation still applies to genuinely parallel links within that design. [§25](../Part4/Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md) (Part 4) provides the general routing background this section applies specifically to the hardware/architectural distinction. [§43](Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md) closes out Part 5 by taking the Layer 2/Layer 3 switching concepts built across this entire Part and showing how software-defined and overlay networking abstract that hardware-device boundary away across many devices and even across physical hosts and cloud environments entirely.

**Next Section:** [§43](Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md) — `Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md`
