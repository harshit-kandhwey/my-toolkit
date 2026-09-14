# Section 38 (Part 5): VLANs: Purpose, Tagging (802.1Q), and Trunking

## 1. Definition

**Plain language:** A VLAN lets you carve one physical switch (or a whole fabric of interconnected switches) into multiple logically separate networks, as if you'd bought separate physical switches for each one — without actually needing separate hardware. Devices in different VLANs can't talk to each other at Layer 2 at all, even if they're plugged into the very same physical switch, unless something routes between them. To carry multiple VLANs' traffic over a single link between switches, each frame gets a small tag added to it saying which VLAN it belongs to — that's 802.1Q tagging, and a link carrying tagged traffic for multiple VLANs is called a trunk.

**Precise definition:** A **VLAN** (Virtual Local Area Network) is a logical partition of a Layer 2 network that creates a separate **broadcast domain** ([§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md)) within one or more physical switches, identified by a numeric **VLAN ID** (12-bit field, valid range 1–4094). Ports are assigned to VLANs either as **access ports** (untagged, carrying traffic for exactly one VLAN — the normal configuration for an end host) or **trunk ports** (carrying tagged traffic for multiple VLANs over a single physical link, typically used between switches or to a hypervisor host). **802.1Q** is the IEEE standard defining the VLAN tag itself: a 4-byte field inserted into the Ethernet frame header containing (among other fields) the 12-bit VLAN ID, allowing a single physical link to multiplex traffic for many VLANs while each switch correctly keeps their broadcast domains, MAC tables ([§36](Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md)), and forwarding decisions separate.

> 💡 **Tip:** The fastest way to reason about any VLAN question: a VLAN is a broadcast domain, full stop. Every other property (separate MAC tables per VLAN, no Layer 2 reachability between VLANs, the need for tagging on shared links) follows directly from "these are different broadcast domains sharing physical hardware," not from any separate, additional mechanism.

## 2. Why This Matters

- **VLANs are the practical answer to the broadcast-domain-scaling problem from [§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md)** — instead of buying a dedicated physical switch per department, environment, or tenant, one switch (or switch fabric) can host dozens of logically isolated networks.
- **Environment and tenant isolation in shared infrastructure** — separating production, staging, and management traffic onto different VLANs on the same physical switches is a standard, load-bearing security and operational boundary in traditional data centers.
- **Trunking is exactly how a hypervisor host serves VMs across multiple VLANs from a single physical NIC** — one physical uplink carries tagged traffic for every VLAN the host's VMs belong to, which is the same mechanism a cloud provider's underlying fabric conceptually resembles (even though the exact implementation is usually an overlay, [§43](Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md)).
- **VLAN misconfiguration is one of the most common real-world causes of "this host can't reach anything" incidents** — a port silently assigned to the wrong VLAN, or a trunk missing an allowed VLAN, produces symptoms that look like routing or firewall problems but are actually pure Layer 2 misconfiguration.
- **VLAN concepts map almost one-to-one onto cloud subnet design** — a cloud VPC subnet is the rough conceptual descendant of a VLAN (a bounded broadcast domain with its own address range), which is why this section pays dividends well beyond on-prem hardware.

## 3. Prerequisites and Dependencies

Builds directly on [§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md) (broadcast domains), since a VLAN's entire purpose is dividing one broadcast domain into several. [§36](Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md) (MAC address tables) matters because a VLAN-aware switch maintains logically separate MAC tables per VLAN — the same physical MAC address seen on two different VLANs is treated as two independent entries. [§39](Section-39-Part5-Inter-VLAN-Routing.md) (Inter-VLAN Routing) is the direct next step: once traffic must cross VLANs, a router or Layer 3 switch is required, and [§39](Section-39-Part5-Inter-VLAN-Routing.md) covers exactly how. [§41](Section-41-Part5-Link-Aggregation-LACP-EtherChannel-Concepts.md) (Link Aggregation) frequently interacts with trunk ports in production, since a trunk carrying many VLANs' traffic is often also bundled via LACP for redundancy and bandwidth — worth revisiting once both sections are read. [§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md) (Part 12, Cloud Networking) revisits the VLAN-to-subnet conceptual mapping once cloud-provider virtual networking is introduced.

## 4. Architecture / Conceptual Diagram

```text
   ONE PHYSICAL SWITCH, THREE VLANs                802.1Q TRUNK BETWEEN TWO SWITCHES

   Port 1 (access, VLAN 10) -- PC-A                SWITCH 1                SWITCH 2
   Port 2 (access, VLAN 10) -- PC-B                 Port 1 (VLAN 10) --PC-A  Port 1 (VLAN 10) --PC-D
   Port 3 (access, VLAN 20) -- PC-C                 Port 2 (VLAN 20) --PC-B  Port 2 (VLAN 20) --PC-E
   Port 4 (access, VLAN 20) -- PC-D                       │                       │
   Port 5 (access, VLAN 30) -- Mgmt-Host                  └──[TRUNK: 802.1Q]──────┘
                                                      carries VLAN 10 AND VLAN 20
   Broadcast from PC-A (VLAN 10) reaches ONLY         traffic, each frame tagged
   PC-B — never PC-C, PC-D, or Mgmt-Host, even        with its VLAN ID as it
   though all are on the same physical switch.        crosses the trunk link.

   802.1Q TAGGED FRAME STRUCTURE (simplified)

   ┌─────────────┬─────────────┬───────────┬────────┬──────┬─────┐
   │ Dest MAC    │ Src MAC     │ 802.1Q Tag│ EType  │ Data │ FCS │
   │ 6 bytes     │ 6 bytes     │ 4 bytes   │2 bytes │ ...  │     │
   └─────────────┴─────────────┴───────────┴────────┴──────┴─────┘
                                 │
                                 ├─ TPID (0x8100): "this is an 802.1Q tagged frame"
                                 ├─ PCP (3 bits): priority (QoS)
                                 ├─ DEI (1 bit): drop eligibility
                                 └─ VLAN ID (12 bits): 1–4094, identifies the VLAN
```

- **Access ports** carry untagged traffic for exactly one VLAN — the switch adds/removes the tag internally, and the attached device (a PC, a server NIC not doing VLAN-aware networking itself) never sees or needs to understand tags at all.
- **Trunk ports** carry tagged traffic for multiple VLANs over one physical link — every frame crossing the trunk carries its 802.1Q tag so the receiving switch (or VLAN-aware host NIC) knows which VLAN the frame belongs to. A trunk typically also has a configured list of "allowed VLANs" to explicitly restrict which VLANs' traffic may cross it.
- **The native VLAN** (on 802.1Q trunks) is a special case: exactly one VLAN on a trunk may be configured to be sent untagged — a legacy compatibility feature with real security implications covered in [§7](../Part1/Section-07-Part1-Prerequisites-Recap-and-How-This-Knowledge-Base-Is-Organized.md).
- Two switches (or a switch and a VLAN-aware hypervisor host) must agree on VLAN IDs across a trunk — VLAN 10 on one switch must mean the same logical network as VLAN 10 on the other, since the tag carries only a numeric ID with no inherent name.

## 5. Hands-On

### 5.1 Creating a VLAN-Tagged Sub-Interface on Linux

**Purpose:** Attach a Linux host directly to a specific VLAN by creating an 802.1Q sub-interface — the standard way a Linux server or hypervisor participates in tagged VLAN traffic without needing external switch configuration changes for every VLAN.

**Syntax:**

```bash
ip link add link <parent-interface> name <parent-interface>.<vlan-id> type vlan id <vlan-id>
ip addr add <ip>/<prefix> dev <parent-interface>.<vlan-id>
ip link set dev <parent-interface>.<vlan-id> up
```

**Example usage and expected output:**

```bash
$ sudo ip link add link eth0 name eth0.10 type vlan id 10
$ sudo ip addr add 10.0.10.5/24 dev eth0.10
$ sudo ip link set dev eth0.10 up
$ ip -d link show eth0.10
6: eth0.10@eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT
    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff
    vlan protocol 802.1Q id 10 <REORDER_HDR>
```

**Production usage example:** Bare-metal database or storage hosts that need to sit directly on a specific VLAN without going through a virtualization layer commonly use exactly this pattern — `eth0` remains the trunk-facing physical interface (requiring the upstream switch port to be configured as a trunk allowing VLAN 10), and `eth0.10` is the host's actual Layer 3 presence on that VLAN.

**Common errors:** Forgetting that the upstream switch port `eth0` connects to must itself be configured as a trunk allowing VLAN 10 — creating the tagged sub-interface on the Linux side alone does nothing if the switch port is still an access port for a different VLAN, or a trunk that doesn't permit VLAN 10.

### 5.2 Inspecting VLAN Configuration on a Linux Bridge

**Purpose:** Confirm VLAN filtering configuration on a Linux bridge used for VM/container networking, where multiple VLANs may need to be handled by a single bridge (VLAN-aware bridge mode).

**Syntax:**

```bash
ip link show type bridge
bridge vlan show
```

**Example usage and expected output:**

```bash
$ bridge vlan show
port              vlan-id
eth1              10 PVID Egress Untagged
eth1              20
vnet0             20 PVID Egress Untagged
```

**Production usage example:** A hypervisor host running a VLAN-aware Linux bridge uses this exact output to confirm which VMs (via their `vnet*` tap interfaces) are correctly bound to which VLAN, and which physical uplink port is trunking which VLANs toward the upstream switch — a direct troubleshooting step when a newly deployed VM can reach some hosts but not others.

**Common errors:** Misreading `PVID` (Port VLAN ID — the VLAN an untagged frame arriving on this port is assigned to) as meaning "this port only carries this VLAN" — a port can have a PVID for untagged traffic while also carrying tagged traffic for other VLANs simultaneously, exactly like a trunk with a native VLAN.

### 5.3 Verifying VLAN Tags on the Wire with a Packet Capture

**Purpose:** Confirm, empirically, that frames crossing a suspected trunk link actually carry 802.1Q tags with the expected VLAN ID — a definitive way to settle "is this actually a trunk" debates.

**Syntax:**

```bash
tcpdump -i <interface> -e -nn vlan
```

**Example usage and expected output:**

```bash
$ sudo tcpdump -i eth0 -e -nn vlan
14:22:01.884213 aa:aa:aa:aa:aa:aa > bb:bb:bb:bb:bb:bb, ethertype 802.1Q (0x8100), length 68:
    vlan 10, p 0, ethertype IPv4, 10.0.10.5 > 10.0.10.7: ICMP echo request
14:22:01.884401 bb:bb:bb:bb:bb:bb > aa:aa:aa:aa:aa:aa, ethertype 802.1Q (0x8100), length 68:
    vlan 10, p 0, ethertype IPv4, 10.0.10.7 > 10.0.10.5: ICMP echo reply
```

**Production usage example:** When a newly cabled trunk link "seems to work for VLAN 10 but not VLAN 20," a capture directly on the trunk interface confirming whether VLAN 20-tagged frames are present at all (versus absent entirely) immediately distinguishes a switch-side "allowed VLAN list" misconfiguration from a routing or host-side issue further along the path.

**Common errors:** Running the capture on an access port expecting to see 802.1Q tags — access ports strip tags before delivering frames to the attached device by design, so tags are only visible on trunk links or VLAN-aware sub-interfaces/bridges, never on a plain access port's traffic as seen by the end host.

## 6. Production Usage Notes

- **VLAN IDs 1 and 1002–1005 carry historical baggage on many vendor platforms** (VLAN 1 is often a factory-default, sometimes discouraged for production use; the 1002–1005 range is reserved on some legacy Cisco platforms for now-obsolete legacy protocols) — production VLAN numbering schemes commonly start from a deliberately chosen range (e.g., 100+) to avoid ambiguity with defaults.
- **Trunk "allowed VLAN" lists are a real, load-bearing security and hygiene control**, not a formality — explicitly restricting a trunk to only the VLANs it actually needs to carry (rather than allowing all VLANs by default) limits the blast radius if a VLAN is later compromised or misconfigured elsewhere on the fabric.
- **The native VLAN on a trunk deserves deliberate configuration, not default acceptance** — leaving it at a vendor default (often VLAN 1) on every trunk in a fabric is a common, avoidable inconsistency; explicitly setting and matching the native VLAN across both ends of every trunk avoids a specific class of subtle Layer 2 misconfiguration ([§7](../Part1/Section-07-Part1-Prerequisites-Recap-and-How-This-Knowledge-Base-Is-Organized.md)).

## 7. Security Considerations

- **VLAN hopping** is an attack class where a host on one VLAN gains unauthorized access to traffic on another VLAN it shouldn't reach — the two classic techniques are **switch spoofing** (a host pretends to negotiate a trunk with the switch, e.g., abusing Dynamic Trunking Protocol on vulnerable equipment) and **double tagging** (a host sends a frame with two stacked 802.1Q tags, exploiting how some switches strip only the outer tag on the native VLAN and then forward the inner-tagged frame onto a different VLAN than intended).
- **Mitigating VLAN hopping** is largely configuration hygiene: explicitly setting every access port to a fixed, non-trunking mode (disabling automatic trunk negotiation protocols on ports that should never be trunks), never using the default/native VLAN for any actual production traffic, and explicitly pruning trunk "allowed VLAN" lists to only what's needed.
- **VLANs are a segmentation and blast-radius control, not a strong security boundary on their own** — VLAN separation is appropriate for organizational/environment isolation on trusted, well-managed infrastructure, but genuinely sensitive isolation requirements (regulatory, multi-tenant with adversarial tenants) typically also need routed firewalling between VLANs ([§39](Section-39-Part5-Inter-VLAN-Routing.md)) and, in cloud contexts, provider-enforced isolation ([§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md)) rather than VLAN tagging alone.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                       | Likely Cause                                                                                   | Resolution Path                                                                                                              |
| ---------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| A host can't reach anything, including its own default gateway                     | Switch access port assigned to the wrong VLAN, or the port's PVID doesn't match the intended VLAN | Check switch port VLAN assignment/PVID; verify against `bridge vlan show` or the switch's port configuration                  |
| Two hosts on the same VLAN, on different switches, can't reach each other          | Trunk between the switches doesn't have that VLAN in its "allowed VLAN" list                      | Check and correct the trunk's allowed-VLAN configuration on both ends; confirm with a capture (§5.3) that tagged frames arrive |
| A newly attached VM can reach some VLANs from the hypervisor but not others        | Hypervisor's VLAN-aware bridge or physical uplink trunk is missing that VLAN, or PVID mismatch    | `bridge vlan show` on the hypervisor host; confirm the physical uplink's trunk configuration matches on the upstream switch    |

## 9. Best Practices

- Assign VLAN IDs deliberately using a documented numbering scheme, avoiding platform-reserved/default ranges (VLAN 1, and any vendor-specific reserved ranges) for actual production traffic.
- Explicitly configure and prune trunk "allowed VLAN" lists to only the VLANs a given trunk actually needs to carry, rather than leaving trunks open to all VLANs by default.
- Disable automatic trunk negotiation protocols on any port that should always remain an access port, closing off the switch-spoofing VLAN hopping vector at the source.
- Treat every VLAN boundary that carries genuinely sensitive traffic as also needing a routed firewall/ACL boundary ([§39](Section-39-Part5-Inter-VLAN-Routing.md)) — don't rely on VLAN separation alone as the sole isolation control for sensitive workloads.

## 10. Common Anti-Patterns / Mistakes

- **Using the default/native VLAN (often VLAN 1) for real production traffic.** This is both an operational hygiene problem (hard to distinguish accidental defaults from deliberate configuration) and a security exposure (native VLAN traffic is untagged on trunks by convention, a known target for double-tagging attacks).
- **Leaving trunk ports open to "all VLANs" instead of explicitly listing allowed VLANs.** This maximizes the blast radius of any future VLAN-hopping vulnerability or misconfiguration for no operational benefit in the vast majority of real deployments.
- **Treating VLAN separation as sufficient security isolation on its own** for genuinely sensitive or multi-tenant workloads, without a routed firewall boundary reinforcing it — VLANs are a broadcast-domain and organizational boundary first, a security control second.
- **Renumbering or reusing VLAN IDs across unrelated purposes without updating all switch and host-side configuration consistently**, which produces exactly the kind of silent, hard-to-diagnose Layer 2 misconfiguration described in [§8](../Part2/Section-08-Part2-The-OSI-7-Layer-Model-Purpose-and-Layer-by-Layer-Breakdown.md).

## 11. Interview Questions

**🎯 Beginner:** _"What is a VLAN, and why would you use one instead of just buying more physical switches?"_
**Model answer:** A VLAN is a way to logically divide a single physical switch (or set of switches) into multiple separate broadcast domains, so that devices in different VLANs can't reach each other at Layer 2 even though they're plugged into the same physical hardware. You'd use VLANs instead of separate physical switches because it's far more cost-effective and flexible — one switch can serve many logically isolated networks, and reassigning a port to a different VLAN is a configuration change, not a cabling change.
_What the interviewer is probing for:_ Whether the candidate connects VLANs to their actual purpose (broadcast domain division, cost/flexibility) rather than just naming the feature.

**🎯 Intermediate:** _"Explain the difference between an access port and a trunk port, and why 802.1Q tagging is necessary."_
**Model answer:** An access port carries untagged traffic for exactly one VLAN — it's the normal configuration for an end host, which never needs to know about VLAN tags at all. A trunk port carries traffic for multiple VLANs over a single physical link, which requires a way to tell frames from different VLANs apart as they share that one link — that's exactly what 802.1Q tagging does, inserting a 4-byte tag containing the VLAN ID into each frame as it crosses the trunk. Without tagging, a switch receiving frames from multiple VLANs on one physical link would have no way to know which VLAN each frame belongs to.
_What the interviewer is probing for:_ Clear understanding of why tagging exists as a solution to a specific problem (multiplexing multiple broadcast domains onto one physical link), not just memorized terminology.

**🎯 Senior:** _"A colleague configures a trunk between two switches but doesn't explicitly restrict the allowed VLANs, leaving it open to all VLANs by default. What's the practical risk, and how would you fix it?"_
**Model answer:** Leaving a trunk open to all VLANs means every VLAN that exists anywhere on either switch's configuration — including ones that shouldn't logically need to cross that particular link — can potentially cross it, unnecessarily widening the blast radius of any future misconfiguration or VLAN-hopping style attack across that trunk. It also makes the topology harder to reason about: an engineer looking at that trunk can't tell from its configuration which VLANs are actually intended to use it. The fix is to explicitly configure the trunk's allowed-VLAN list to only the VLANs actually needed across that specific link, and to review and prune that list whenever VLAN usage changes, rather than defaulting to "allow everything and hope nothing crosses that shouldn't."
_What the interviewer is probing for:_ Whether the candidate treats "allowed VLAN" scoping as a real security/hygiene practice with a concrete rationale, not a purely cosmetic configuration detail.

**🎯 Architect:** _"You're migrating a data center from a small number of very large, flat VLANs to a larger number of smaller, purpose-specific VLANs. What operational and design considerations do you need to account for beyond just creating the new VLANs?"_
**Model answer:** Several things beyond VLAN creation itself. First, every new VLAN boundary is a new broadcast domain boundary, which means traffic that previously flowed freely at Layer 2 now needs Layer 3 routing between VLANs ([§39](Section-39-Part5-Inter-VLAN-Routing.md), [§42](Section-42-Part5-Layer-2-vs-Layer-3-Switching.md)) — I'd need to plan inter-VLAN routing capacity and placement (centralized router-on-a-stick versus distributed Layer 3 switching) before cutting over, since this is a new hop and potential bottleneck that didn't exist before. Second, every trunk in the fabric needs its allowed-VLAN list updated and audited — this is the point where lingering "allow all VLANs" trunk configurations get cleaned up, since the migration is a natural forcing function to fix that anti-pattern. Third, host and hypervisor-side configuration (VLAN-tagged sub-interfaces, VLAN-aware bridges) needs to move in lockstep with the switch-side changes, since a mismatch between what a switch trunk allows and what a hypervisor's bridge expects produces exactly the "can reach some VLANs but not others" symptom class. Finally, I'd sequence the migration VLAN-by-VLAN with rollback points rather than a single cutover, precisely because VLAN misconfigurations tend to be silent (hosts just stop reaching things) rather than loudly erroring, making a staged approach with verification at each step far safer than a big-bang change.
_What the interviewer is probing for:_ Whether the candidate thinks through the full blast radius of a VLAN redesign — routing capacity, trunk configuration, host-side consistency, and migration sequencing — rather than treating it as a purely switch-configuration exercise.

## 12. Common Misconceptions

1. **"VLANs provide the same level of isolation as physically separate networks in every respect."** VLANs isolate Layer 2 broadcast domains effectively, but they run on shared physical infrastructure and switch control planes — for genuinely adversarial multi-tenancy, additional isolation (routed firewalling, sometimes physical separation) is still warranted.
2. **"Any port carrying more than one VLAN's traffic must be a trunk."** A native VLAN complicates this — a trunk can carry one VLAN untagged (the native VLAN) alongside other VLANs tagged, which is a source of real confusion when reading packet captures or port configurations.
3. **"VLAN IDs need to be globally unique across an entire organization's network."** VLAN IDs only need to be consistent and unambiguous within the scope of a connected Layer 2 fabric — the same VLAN ID can mean something entirely different in two unconnected parts of a large network, as long as they never share a trunk.
4. **"Tagging happens on every port, including access ports."** Tags exist only on trunk links (and VLAN-aware sub-interfaces/bridges) — access ports deliver and accept untagged frames by design, adding/stripping the tag internally within the switch.

## 13. 🔑 Key Takeaways

- A VLAN is fundamentally a broadcast domain ([§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md)) carved out logically within shared physical switch hardware, identified by a numeric VLAN ID.
- Access ports carry untagged traffic for one VLAN; trunk ports carry 802.1Q-tagged traffic for multiple VLANs over a single physical link.
- 802.1Q tagging inserts a 4-byte field (including the 12-bit VLAN ID) into the Ethernet frame header, letting one physical link multiplex many logically separate broadcast domains.
- VLAN hopping (switch spoofing, double tagging) is a real attack class mitigated primarily through configuration hygiene: disabling unnecessary trunk negotiation, avoiding the default/native VLAN for production traffic, and pruning allowed-VLAN lists.
- VLANs are a segmentation and blast-radius tool, not a complete security boundary on their own — sensitive isolation requirements need routed firewalling on top of VLAN separation.

## 14. Related Concepts & What's Next

[§39](Section-39-Part5-Inter-VLAN-Routing.md) is the direct continuation of this section: once traffic needs to cross VLAN boundaries, inter-VLAN routing is required, and covers exactly how that's implemented (router-on-a-stick, Layer 3 switching). [§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md) is this section's prerequisite, establishing why broadcast domain division matters in the first place. [§41](Section-41-Part5-Link-Aggregation-LACP-EtherChannel-Concepts.md) (Link Aggregation) frequently combines with trunk ports in production for bandwidth and redundancy on the same physical links carrying tagged VLAN traffic. [§100](../Part12/Section-100-Part12-Cloud-Virtual-Networking-Fundamentals-VPC-VNet-Concepts-Across-Providers.md) (Part 12) revisits the VLAN-to-cloud-subnet conceptual mapping once cloud provider virtual networking is covered, and [§43](Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md) revisits VLAN-like segmentation in the context of overlay networks that solve the same isolation problem across, rather than within, physical switches.

**Next Section:** [§39](Section-39-Part5-Inter-VLAN-Routing.md) — `Section-39-Part5-Inter-VLAN-Routing.md`
