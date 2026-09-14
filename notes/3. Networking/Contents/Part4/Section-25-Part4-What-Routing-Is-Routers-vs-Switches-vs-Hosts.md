# Section 25 (Part 4): What Routing Is; Routers vs. Switches vs. Hosts

## 1. Definition

**Plain language:** Routing is the process of getting a packet from a device on one network to a device on a different network. A device that isn't sure whether the destination is "local" or "somewhere else" — and if it's somewhere else, which direction to send the packet in — is doing the job of a router. Switches, by contrast, only move frames around *within* a single network segment; hosts mostly just decide whether to send a packet directly to its destination or hand it off to something else (a router) that knows more about the wider world.

**Precise definition:** **Routing** is the Layer 3 (network layer) function of selecting a path for a packet to travel from a source network to a destination network, based on the packet's destination IP address, and forwarding it out the correct interface toward that destination — hop by hop, until it arrives. A **router** is a Layer 3 device: it maintains a **routing table** ([§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md)), inspects the destination IP address of every packet it receives, and forwards each packet out the interface associated with the best-matching route — critically, a router also rewrites the Layer 2 (MAC) header on every hop, and decrements the IP TTL. A **switch** is fundamentally a Layer 2 device: it forwards *frames* within a single broadcast domain based on destination MAC address, using a MAC address table ([§36](../Part5/Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md)), and has no concept of IP subnets unless it is a **Layer 3 switch** that additionally performs routing in hardware. A **host** (an end device — server, laptop, container) makes exactly one Layer 3 decision per outbound packet: is the destination on my own subnet (in which case ARP resolves the destination's MAC directly, [§23](../Part3/Section-23-Part3-Address-Resolution-ARP-and-NDP.md)) or not (in which case the packet is handed to the **default gateway**, [§28](Section-28-Part4-Default-Routes-Null-Routes-and-Route-Summarization.md), for onward routing)?

> 💡 **Tip:** The cleanest mental test for "is this device routing or switching?" is to ask what address it reads to make its forwarding decision. If it reads the destination **MAC address**, it's switching (Layer 2, same network). If it reads the destination **IP address** and picks an outbound interface based on a routing table, it's routing (Layer 3, potentially a different network) — regardless of whether the physical box is labeled "router," "switch," or "firewall."

## 2. Why This Matters

- **Everything above the physical wire depends on it.** Without routing, a request from your laptop could never reach a server in another data center, another cloud region, or across the public internet — routing is the mechanism that makes internetworking (the "inter" in "internet") possible at all.
- **Cloud "route tables" are the exact same concept, virtualized.** An AWS VPC route table, an Azure UDR (user-defined route), and a GCP VPC route are all software implementations of the same longest-prefix-match forwarding logic a physical router performs — understanding physical routing directly transfers to reading and debugging cloud networking constructs.
- **Troubleshooting connectivity issues requires knowing which layer failed.** "I can't reach that server" could mean a Layer 2 problem (ARP failure, VLAN misconfiguration) or a Layer 3 problem (missing route, wrong gateway, security group blocking traffic) — misdiagnosing which layer is broken wastes significant troubleshooting time.
- **Modern data centers blur the router/switch line.** Layer 3 switches, which route between VLANs in hardware at wire speed, are now the default in most data center designs — understanding the conceptual distinction between switching and routing matters more than ever because the physical boxes no longer make it obvious.
- **Every hop rewrites the frame, but not the packet.** Understanding that a router changes the Ethernet header at every hop while (mostly) preserving the IP header end-to-end is foundational to reading packet captures and reasoning about traceroute output (Part 14, [§115](../Part14/Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md)-123).

## 3. Prerequisites and Dependencies

This section opens Part 4 and builds directly on Part 2's OSI/TCP-IP layering model ([§8](../Part2/Section-08-Part2-The-OSI-7-Layer-Model-Purpose-and-Layer-by-Layer-Breakdown.md), [§9](../Part2/Section-09-Part2-The-TCP-IP-4-Layer-Model-and-How-It-Maps-to-OSI.md)) and Part 3's addressing material — specifically IPv4 structure ([§15](../Part3/Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md)), CIDR notation ([§16](../Part3/Section-16-Part3-Subnet-Masks-and-CIDR-Notation.md)), and ARP-based local resolution ([§23](../Part3/Section-23-Part3-Address-Resolution-ARP-and-NDP.md)). A reader should already be comfortable determining whether two IP addresses fall in the same subnet before this section, since that determination is exactly what triggers a host's routing decision. [§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md) immediately follows with the routing table structure only introduced conceptually here.

## 4. Architecture / Conceptual Diagram

```text
   Host A (10.0.1.10/24)                              Host B (10.0.2.20/24)
   ┌─────────────┐                                     ┌─────────────┐
   │   Layer 3:  │  Is 10.0.2.20 on my subnet          │   Layer 3:  │
   │  10.0.1.10  │  (10.0.1.0/24)? NO.                 │  10.0.2.20  │
   │  /24        │  → send to default gateway          │  /24        │
   └──────┬──────┘                                     └──────┬──────┘
          │ ARP for gateway MAC, frame to gateway              │
          ▼                                                    ▲
   ┌─────────────┐        ROUTED (Layer 3 decision)     ┌─────────────┐
   │   Switch    │───────────────►│  Router  │──────────►│   Switch    │
   │ (L2 only:   │                │ 10.0.1.1 │           │ (L2 only:   │
   │ forwards by │                │ 10.0.2.1 │           │ forwards by │
   │ dest MAC)   │                └──────────┘           │ dest MAC)   │
   └─────────────┘   new src/dst MAC written per hop     └─────────────┘

   Same subnet case (no routing needed):
   Host A (10.0.1.10) → ARP for Host C (10.0.1.11) directly → switch forwards
   by MAC, straight to Host C. Router never touched.
```

- The **switch** in this diagram never inspects an IP address — it only ever looks up destination MAC addresses in its CAM table ([§36](../Part5/Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md)) and forwards frames within the same broadcast domain.
- The **router** is the only device that rewrites the Ethernet source/destination MAC on each hop (the new source MAC is the router's outbound interface, the new destination MAC is the next hop's MAC) while leaving the IP header's source and destination addresses untouched end-to-end — this is precisely why `traceroute` can show you every router hop while the original source and destination IPs never change.
- **Host A's decision process** — "same subnet or not" — is the fundamental Layer 3 fork every packet takes at its origin: same-subnet traffic never leaves the local broadcast domain and never touches a router at all; cross-subnet traffic always transits at least one router (or Layer 3 switch performing the router's role).

## 5. Hands-On

### 5.1 Inspecting a Host's Own Routing Behavior

**Purpose:** Show how a host decides whether a destination is local or remote, and where it sends traffic when it is remote.

**Syntax:**

```bash
ip route show          # Linux — show the routing table
ip route get <dest-ip> # Linux — show which route/interface would be used
route -n               # Linux/macOS legacy tool, numeric output
route print             # Windows
```

**Example usage and expected output:**

```bash
$ ip route show
default via 10.0.1.1 dev eth0 proto dhcp metric 100
10.0.1.0/24 dev eth0 proto kernel scope link src 10.0.1.10

$ ip route get 10.0.2.20
10.0.2.20 via 10.0.1.1 dev eth0 src 10.0.1.10
    cache

$ ip route get 10.0.1.11
10.0.1.11 dev eth0 src 10.0.1.10
    cache
```

**Production usage example:** `ip route get <ip>` is the fastest way to confirm, on any Linux host (bare-metal, VM, or container), exactly which interface and next hop the kernel will use for a given destination — this is the first command run when diagnosing "why can't this pod/VM reach that IP" before ever touching a packet capture.

**Common errors:** Seeing `10.0.2.20 via 10.0.1.1 dev eth0` when you expected direct delivery usually means the destination is not actually inside the subnet you assumed — a subnet mask miscalculation ([§17](../Part3/Section-17-Part3-Subnetting-Fundamentals-Borrowing-Bits-Calculating-Ranges.md)) is the most common root cause.

### 5.2 Distinguishing a Router Hop from a Switch Hop with traceroute

**Purpose:** Empirically observe that only Layer 3 devices (routers) appear as hops, while switches in the same path are invisible to traceroute.

**Syntax:**

```bash
traceroute <destination>     # Linux/macOS
tracert <destination>        # Windows
```

**Example usage and expected output:**

```bash
$ traceroute 8.8.8.8
traceroute to 8.8.8.8 (8.8.8.8), 30 hops max
 1  10.0.1.1 (10.0.1.1)  0.412 ms   0.398 ms   0.375 ms
 2  100.64.0.1 (100.64.0.1)  1.203 ms   1.190 ms   1.175 ms
 3  203.0.113.1 (203.0.113.1)  8.442 ms   8.401 ms   8.390 ms
 4  8.8.8.8 (8.8.8.8)  9.112 ms   9.098 ms   9.087 ms
```

**Production usage example:** In cloud environments, `traceroute` from an EC2 instance or VM typically shows very few hops before reaching the destination (or none at all inside a VPC, since cloud fabric routing doesn't always decrement TTL the same way physical routers do) — engineers use this to distinguish "traffic is leaving my VPC as expected" from "traffic is stuck inside my own network."

**Common errors:** Intermediate hops showing `* * *` (no response) does not necessarily mean the path is broken — many routers are configured to not respond to the ICMP/UDP probes traceroute uses (rate-limited or explicitly filtered) while still forwarding the actual traffic correctly; only a `* * *` at the *final* hop combined with an actual connectivity failure is diagnostic.

## 6. Production Usage Notes

- **Layer 3 switches have made "the router is a separate box" an outdated mental model.** In most modern data centers and cloud fabrics, inter-VLAN routing ([§39](../Part5/Section-39-Part5-Inter-VLAN-Routing.md)) happens in ASIC-accelerated hardware on a switch, not a dedicated router appliance — but the logical function (Layer 3 forwarding decision by destination IP) is identical to what a traditional router performs.
- **Cloud VPCs have no physical routers at all** — the "route table" attached to a subnet ([§101](../Part12/Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)) is a software-defined construct implemented by the cloud provider's virtualized network fabric, but it performs the exact same longest-prefix-match forwarding logic conceptually covered in [§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md).
- **Hosts almost never need a full routing table.** A typical server or VM has exactly two kinds of routes: a connected route for its own subnet, and a default route pointing at the gateway — the elaborate multi-route tables in this Part's later sections are the concern of routers and Layer 3 switches, not end hosts.

## 7. Security Considerations

- Any device that performs Layer 3 forwarding is a potential inspection and enforcement point — security groups, network ACLs (Part 10, [§82](../Part10/Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md)-90), and firewalls are deployed at routing boundaries precisely because traffic crossing from one network to another is unavoidably visible to the routing device in a way that same-subnet traffic (switched only) is not.
- A host whose default gateway is spoofed (via ARP spoofing, [§23](../Part3/Section-23-Part3-Address-Resolution-ARP-and-NDP.md)) will unknowingly route all its cross-subnet traffic through an attacker-controlled device — this is a classic man-in-the-middle technique that exploits the exact "am I local or not" decision described in this section.
- Misconfigured Layer 3 switches or routers that leak routing information between security zones (for example, a route that inadvertently makes an isolated management network reachable from a general application subnet) silently defeat network segmentation controls that assume routing boundaries enforce isolation.

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Likely Cause                                                                                   | Resolution Path                                                                                                   |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------- |
| Host can reach devices on its own subnet but nothing else             | Default gateway is missing, unreachable, or misconfigured                                        | `ip route show` to confirm a default route exists; `ping` the gateway IP directly to confirm Layer 2/3 reachability   |
| Two hosts believed to be on the same subnet can't reach each other directly | Subnet mask mismatch — one host's mask makes the other appear to be on a different network | Recompute subnet boundaries ([§17](../Part3/Section-17-Part3-Subnetting-Fundamentals-Borrowing-Bits-Calculating-Ranges.md)); verify both hosts use identical masks |
| `traceroute` shows an unexpected extra hop mid-path                   | A Layer 3 switch or router is silently doing inter-VLAN routing where a flat network was assumed | Confirm actual network topology/VLAN design rather than the topology diagram; treat the extra hop as a real Layer 3 boundary |

## 9. Best Practices

- Always determine whether a connectivity problem is Layer 2 (switching, ARP, VLAN) or Layer 3 (routing, gateway, ACL) before reaching for deeper tools — this single fork eliminates half the possible root causes immediately.
- Document, for every subnet in your environment, which device (physical router, Layer 3 switch, or cloud route table) actually performs the routing decision for it — "who is my gateway and what enforces routing here" should never be a mystery during an incident.
- Treat cloud route tables with the same rigor as physical router configuration: review them in change management, since a single incorrect route can silently blackhole or misdirect an entire subnet's traffic.

## 10. Common Anti-Patterns / Mistakes

- **Assuming "it's on the same network" without checking the actual subnet mask.** Two IPs can look adjacent (10.0.1.50 and 10.0.1.200) but sit in different subnets if a /25 or smaller mask is in use — this is one of the most common sources of "why can't these two servers talk directly" confusion.
- **Treating the router/switch distinction as purely about the physical box.** A single physical appliance today routinely performs both switching and routing (a Layer 3 switch, or a router-on-a-stick for VLAN trunking, [§39](../Part5/Section-39-Part5-Inter-VLAN-Routing.md)) — diagnosing by function, not by box label, avoids confusion.
- **Forgetting that routing changes the Layer 2 header on every hop.** Engineers new to packet captures sometimes expect the source/destination MAC address to stay constant end-to-end the way the IP address does, and get confused when it changes at every router hop in a capture.

## 11. Interview Questions

**🎯 Beginner:** _"What's the core difference between what a switch does and what a router does?"_
**Model answer:** A switch forwards frames within a single network (broadcast domain) based on the destination MAC address, using a MAC address table it learns automatically. A router forwards packets between different networks based on the destination IP address, using a routing table, and rewrites the Layer 2 header (source/destination MAC) at every hop while the IP addresses stay the same end-to-end.
_What the interviewer is probing for:_ Whether the candidate has the Layer 2 vs. Layer 3 distinction cleanly internalized, not just "routers connect networks" as a vague phrase.

**🎯 Intermediate:** _"A host needs to send a packet to an IP address. Walk through exactly how it decides whether to ARP for that address directly or send the packet to its default gateway."_
**Model answer:** The host compares the destination IP address against its own IP address and subnet mask. If the destination falls within the same subnet (the network portion of the address matches), the host ARPs directly for the destination's MAC address and sends the frame straight to it — no router is involved. If the destination is outside the local subnet, the host instead ARPs for its default gateway's MAC address (if not already cached) and sends the frame to the gateway, which then makes the Layer 3 forwarding decision on the host's behalf.
_What the interviewer is probing for:_ Concrete understanding of the host-side routing decision, including the role of the subnet mask and ARP, not just "it goes to the gateway."

**🎯 Senior:** _"Why do modern data center and cloud designs increasingly blur the line between 'router' and 'switch'? What's actually happening under the hood?"_
**Model answer:** Layer 3 switches perform inter-VLAN routing in dedicated ASIC hardware at wire speed, which is both cheaper and faster than routing through a separate router appliance for east-west traffic within a data center — so the router function gets absorbed into the switching fabric itself rather than eliminated. In cloud VPCs, there's no physical router or switch at all: the provider's software-defined network fabric implements the same longest-prefix-match forwarding logic as a virtualized service attached to each subnet (a "route table"), so the router/switch distinction becomes purely conceptual/functional rather than describing separate physical devices.
_What the interviewer is probing for:_ Whether the candidate understands that the Layer 2/Layer 3 functional distinction persists even when the physical (or virtual) implementation no longer maps to separate boxes.

**🎯 Architect:** _"You're designing network segmentation for a new platform. A colleague argues that since VLANs already isolate traffic at Layer 2, inter-VLAN routing and firewall rules are redundant. How do you respond?"_
**Model answer:** VLANs isolate broadcast domains at Layer 2 — they prevent a broadcast storm or ARP traffic in one VLAN from reaching another, but they say nothing about whether traffic *should* be allowed to cross between VLANs once a router or Layer 3 switch is configured to route between them. The router/Layer 3 switch performing inter-VLAN routing is exactly the enforcement point where security policy (ACLs, firewall rules, security groups) belongs, because it's the only device that inspects the Layer 3/4 information needed to make an allow/deny decision — a bare VLAN boundary with unrestricted inter-VLAN routing configured provides zero actual traffic control between segments, only broadcast isolation. I'd insist that any VLAN-based segmentation design explicitly define and enforce the routing/firewall policy at every inter-VLAN boundary, not assume the VLAN boundary itself is a security control.
_What the interviewer is probing for:_ Whether the candidate distinguishes Layer 2 isolation (broadcast domains) from Layer 3/4 access control (routing plus filtering), a distinction that matters directly for real segmentation and zero-trust network design ([§85](../Part10/Section-85-Part10-Linux-Firewalling-iptables-nftables-and-firewalld-Concepts.md)).

## 12. Common Misconceptions

1. **"Switches and routers are always separate physical devices."** Layer 3 switches route in hardware, and cloud VPCs route entirely in software with no physical device at all performing the function.
2. **"A router changes the source and destination IP address as a packet passes through."** It does not (barring NAT, [§20](../Part3/Section-20-Part3-NAT-and-PAT-Concepts-and-Real-World-Use.md)) — the IP header's addresses stay constant end-to-end; only the Ethernet (Layer 2) header is rewritten at every hop.
3. **"If two IPs look numerically close, they're on the same network."** Subnet membership is determined entirely by the subnet mask, not visual proximity of the numbers — 10.0.1.50/25 and 10.0.1.200/25 are in different subnets despite looking adjacent.
4. **"traceroute always accurately shows every hop."** Many routers rate-limit or filter the ICMP/UDP probes traceroute relies on, producing `* * *` for hops that are still forwarding traffic correctly — a missing hop entry is not proof of a broken path.

## 13. 🔑 Key Takeaways

- Routing is a Layer 3 function: forwarding packets between different networks based on destination IP address, using a routing table.
- Switching is a Layer 2 function: forwarding frames within a single network based on destination MAC address, using a MAC address table.
- A host makes exactly one Layer 3 decision per outbound packet — same subnet (ARP directly) or different subnet (send to default gateway) — determined entirely by the subnet mask.
- A router rewrites the Layer 2 header at every hop while leaving the IP header's source/destination addresses unchanged end-to-end.
- Modern data centers and cloud fabrics implement the router function in hardware (Layer 3 switches) or entirely in software (cloud route tables), but the underlying Layer 3 forwarding logic is identical.

## 14. Related Concepts & What's Next

[§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md) opens up the routing table structure only gestured at here, including the longest-prefix-match rule that determines which route wins when multiple entries could match a destination. [§36](../Part5/Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md) covers the switch-side MAC address table this section contrasted routing against. [§39](../Part5/Section-39-Part5-Inter-VLAN-Routing.md) revisits the Layer 3 switch concept in the context of VLAN design. [§101](../Part12/Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md) applies these same concepts to cloud VPC route tables.

**Next Section:** [§26](Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md) — `Section-26-Part4-Routing-Tables-Structure-and-the-Longest-Prefix-Match-Rule.md`
