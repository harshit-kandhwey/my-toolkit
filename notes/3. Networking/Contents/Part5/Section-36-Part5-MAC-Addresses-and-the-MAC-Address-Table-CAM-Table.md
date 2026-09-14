# Section 36 (Part 5): MAC Addresses and the MAC Address Table (CAM Table)

## 1. Definition

**Plain language:** Every network interface has a unique hardware address burned into it (or assigned to its virtual equivalent), and a switch keeps a running list mapping each of those addresses to the physical port it's reachable through. That list is how a switch knows to forward a frame out exactly one port instead of every port — it's the switch's memory of "who's plugged in where."

**Precise definition:** A **MAC address** (Media Access Control address) is a 48-bit identifier, conventionally written as six hexadecimal octets (e.g., `02:42:ac:11:00:02`), that uniquely identifies a network interface at the Data Link layer. The first three octets (the **OUI**, Organizationally Unique Identifier) identify the manufacturer; the remaining three are assigned by that manufacturer. A switch's **MAC address table** — historically called the **CAM table** (Content-Addressable Memory table, after the specialized hardware memory used to implement fast lookups) — is a dynamically built mapping of `{MAC address → switch port, VLAN}` that the switch populates through a process called **MAC learning**: on receiving any frame, the switch records the frame's **source** MAC address against the port it arrived on, then consults the table for the frame's **destination** MAC to decide where to forward it — flooding out all ports (except the one it arrived on) only when the destination is not yet known.

> 💡 **Tip:** The entire behavior of a switch reduces to one loop, run for every single frame: "learn the source, look up the destination." Learning always happens; forwarding is either targeted (destination known) or flooded (destination unknown, or the frame is itself a broadcast/multicast). If you can trace through that loop by hand for a given frame, you can predict exactly what a switch will do with it.

## 2. Why This Matters

- **This is the mechanism, not just the theory, behind "why did my ping work but the switch didn't know where to send it the first time."** The very first frame to any destination is always flooded because the table starts empty for that address — subsequent frames are targeted once the destination's source frame (e.g., its ARP reply) has been learned.
- **MAC table capacity is a real, finite hardware resource** — enterprise and data-center switches have documented maximum table sizes (often tens of thousands of entries), and exceeding it (through misconfiguration, an attack, or a genuinely huge number of hosts on one segment) causes fail-open flooding behavior that has real performance and security consequences.
- **MAC table exhaustion is an actual, exploitable attack vector** (CAM table overflow / MAC flooding) — understanding how the table is populated and what happens when it fills explains why switch **port security** features exist and what they actually protect against.
- **Every "why isn't traffic reaching this VM/container" investigation on a virtualized host** eventually comes down to inspecting the same concept in software form — a Linux bridge's forwarding database (`bridge fdb`) is a CAM table in every functional sense.
- **Aging and stale entries directly explain real production symptoms**, like a MAC address that moved to a new port (VM migration, NIC replacement) taking a few seconds to become reachable again while the old entry ages out.

## 3. Prerequisites and Dependencies

Builds directly on [§35](Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md), which introduced the switch's role and gestured at MAC learning without detailing the mechanism — this section makes that mechanism explicit. [§9](../Part2/Section-09-Part2-The-TCP-IP-4-Layer-Model-and-How-It-Maps-to-OSI.md) (Part 2, Address Resolution / PDUs, if covering ARP) and any prior ARP/NDP treatment in Part 3 are helpful context for understanding how a host discovers a destination's MAC address in the first place, though this section is self-contained for the switch-side behavior. [§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md) depends on this section: broadcast frames are exactly the case where a switch floods regardless of table state, and understanding MAC learning is necessary to understand why broadcast domains behave the way they do. [§40](Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md) (Spanning Tree) revisits MAC table behavior specifically in the context of what happens (badly) when a Layer 2 loop causes constant re-learning and table thrashing.

## 4. Architecture / Conceptual Diagram

```text
   MAC Learning and Forwarding — Frame by Frame

   Switch ports:  1 ---- PC-A (aa:aa:aa:aa:aa:aa)
                  2 ---- PC-B (bb:bb:bb:bb:bb:bb)
                  3 ---- PC-C (cc:cc:cc:cc:cc:cc)

   Frame 1: PC-A sends a frame to PC-B (dst=bb:bb..., src=aa:aa...), arrives on port 1

     Step 1 — LEARN:  MAC table currently empty → record {aa:aa:aa:aa:aa:aa → port 1}
     Step 2 — LOOKUP:  destination bb:bb:bb:bb:bb:bb not in table yet
     Step 3 — FLOOD:   frame sent out ports 2 AND 3 (every port except the one it arrived on)

   ┌──────────────────────────────┐
   │  MAC Address Table (so far)  │
   ├───────────────────┬──────────┤
   │ aa:aa:aa:aa:aa:aa │  port 1  │
   └───────────────────┴──────────┘

   Frame 2: PC-B replies to PC-A (dst=aa:aa..., src=bb:bb...), arrives on port 2

     Step 1 — LEARN:   record {bb:bb:bb:bb:bb:bb → port 2}
     Step 2 — LOOKUP:  destination aa:aa:aa:aa:aa:aa IS in table → port 1
     Step 3 — FORWARD: frame sent ONLY out port 1 (targeted, not flooded)

   ┌──────────────────────────────┐
   │  MAC Address Table (updated) │
   ├───────────────────┬──────────┤
   │ aa:aa:aa:aa:aa:aa │  port 1  │
   │ bb:bb:bb:bb:bb:bb │  port 2  │
   └───────────────────┴──────────┘
   PC-C (port 3) never saw either frame — true point-to-point forwarding once both
   ends are learned.
```

- **Learning is unconditional and per-frame:** the switch learns the source MAC of every frame it receives, regardless of whether it can resolve the destination — this is why a table fills up quickly even under light, one-directional traffic.
- **Flooding is the fallback, not the default:** a switch floods a frame only when the destination MAC is unknown, is a broadcast address (`ff:ff:ff:ff:ff:ff`), or is a multicast address it hasn't been told to prune (IGMP snooping, out of scope here) — once a destination has sent at least one frame, subsequent traffic to it is targeted.
- **Entries age out:** each table entry carries an **aging timer** (commonly 300 seconds on many platforms); if no frame from that MAC is seen before the timer expires, the entry is removed, and the next frame to that destination is flooded again until re-learned. This is deliberate — it lets the table adapt when a device physically moves to a different port or a VM migrates to a different host uplink.

## 5. Hands-On

### 5.1 Viewing a Linux Bridge's Forwarding Database (the Software CAM Table)

**Purpose:** Inspect the exact software equivalent of a switch's MAC address table for a Linux bridge, confirming which MAC addresses are learned behind which member port.

**Syntax:**

```bash
bridge fdb show
bridge fdb show br <bridge-name>
```

**Example usage and expected output:**

```bash
$ bridge fdb show br docker0
02:42:ac:11:00:02 dev vethabc123 master docker0
02:42:ac:11:00:03 dev vethdef456 master docker0
33:33:00:00:00:01 dev docker0 self permanent
```

**Production usage example:** When two containers on the same Docker host can't reach each other despite both being "up," checking `bridge fdb show` confirms whether the bridge has actually learned each container's MAC against the correct veth — an entry missing or pointing at the wrong interface (e.g., after a container restart reassigned a veth) is a concrete, verifiable root cause rather than a guess.

**Common errors:** Expecting a freshly started container's MAC to appear immediately — like a hardware switch, the bridge only learns a MAC after it has actually seen a frame sourced from it; an idle new container may not appear until it sends its first packet (commonly a gratuitous ARP or DHCP request).

### 5.2 Inspecting a Host's Own MAC Address and OUI

**Purpose:** Read a specific interface's MAC address directly, and recognize the OUI portion as a manufacturer identifier — useful when distinguishing physical NICs from virtual ones in a mixed environment.

**Syntax:**

```bash
ip link show <interface>
ip -br link show
```

**Example usage and expected output:**

```bash
$ ip link show eth0
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP mode DEFAULT
    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff

$ ip -br link show
lo               UNKNOWN        00:00:00:00:00:00 <LOOPBACK,UP,LOWER_UP>
eth0             UP             02:42:ac:11:00:02 <BROADCAST,MULTICAST,UP,LOWER_UP>
```

**Production usage example:** Distinguishing a locally administered MAC (second-hex-digit of the first octet is 2, 6, A, or E — as in `02:42:...` above, a common Docker-assigned pattern) from a manufacturer-burned-in address is a routine step when auditing a mixed fleet of physical hosts and virtualized/containerized interfaces, since locally administered addresses reliably indicate software-assigned virtual interfaces.

**Common errors:** Assuming a MAC address is globally guaranteed unique in all contexts — locally administered addresses (used heavily by virtualization platforms) are only guaranteed unique within the administrator's own assignment scheme, and colliding locally administered MACs across unrelated virtual networks is a real (if rare) misconfiguration risk.

### 5.3 Observing MAC Learning Behavior with a Packet Capture

**Purpose:** Correlate the abstract "learn source, look up destination" model against real frames on the wire, confirming the first frame to a new destination triggers flooding while later ones don't.

**Syntax:**

```bash
tcpdump -i <interface> -e -c 20
```

**Example usage and expected output:**

```bash
$ sudo tcpdump -i eth0 -e -c 5
14:02:11.001923 aa:aa:aa:aa:aa:aa > ff:ff:ff:ff:ff:ff, ethertype ARP, ...  # ARP request: broadcast, always flooded
14:02:11.002105 bb:bb:bb:bb:bb:bb > aa:aa:aa:aa:aa:aa, ethertype ARP, ... # ARP reply: unicast, now learnable
14:02:11.002310 aa:aa:aa:aa:aa:aa > bb:bb:bb:bb:bb:bb, ethertype IPv4, ... # first real frame, targeted once learned
```

**Production usage example:** During a hard-to-reproduce intermittent connectivity issue, a capture like this on both ends of a suspected link confirms whether frames are actually reaching a host at Layer 2 at all — if the destination never appears as a source in captures on the switch side, the MAC table genuinely has no entry for it, redirecting the investigation toward the destination host itself (NIC down, wrong VLAN) rather than the switch.

**Common errors:** Running a capture on a switch port expecting to see all traffic on the segment, as if it were a hub — on a switched network a capture only sees traffic destined to, sourced from, or flooded/broadcast to that specific port unless a SPAN/mirror port or promiscuous bridging is explicitly configured ([§35](Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md), [§7](../Part1/Section-07-Part1-Prerequisites-Recap-and-How-This-Knowledge-Base-Is-Organized.md) Security Considerations).

## 6. Production Usage Notes

- **MAC table size is a genuine capacity-planning number on physical switches.** Enterprise access switches commonly support 8,000–32,000+ entries; exceeding this (a very large flat Layer 2 segment, or a MAC flooding attack) forces the switch into fail-open behavior, flooding traffic that should have been targeted — a real performance and security regression, not just a theoretical limit.
- **Aging time is a tunable trade-off, not a fixed constant.** A shorter aging time adapts faster to devices moving between ports (VM live migration between hypervisor uplinks) at the cost of more frequent flooding while re-learning; a longer aging time reduces flooding at the cost of slower adaptation to topology changes.
- **Virtual/software forwarding databases (Linux `bridge fdb`, Open vSwitch's MAC table) follow the identical conceptual model** as hardware CAM tables, but are typically far less capacity-constrained on a modern host — the constraint that matters in virtualized environments is usually elsewhere (vCPU/interrupt handling, virtual switch throughput), not table size.

## 7. Security Considerations

- **MAC (CAM) table exhaustion / MAC flooding attacks** deliberately send frames from a huge number of forged source MAC addresses to fill the table's capacity; once full, the switch can no longer learn new legitimate entries and falls back to flooding **all** traffic on the segment out **all** ports — turning a switch into a hub for the purposes of an attacker capturing traffic. This is the concrete mechanism behind the "switches aren't automatically safe from eavesdropping" caveat in [§35](Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md).
- **Port security** (limiting the number of MAC addresses learnable on a given switch port, or restricting a port to specific known MAC addresses) is the standard mitigation for MAC flooding — a port exceeding its configured MAC limit can be configured to shut down, restrict, or alert rather than allow unlimited learning.
- **MAC spoofing** (a host presenting a MAC address it doesn't own) can be used to hijack another device's learned table entry, redirecting traffic intended for the legitimate device to the attacker — this is distinct from MAC flooding and is mitigated by port security combined with DHCP snooping/dynamic ARP inspection on managed switches, which is out of scope for the depth of this roadmap but worth knowing exists.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Likely Cause                                                                                   | Resolution Path                                                                                                     |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| A device becomes unreachable for a few seconds right after a VM live-migrates | The switch's old MAC table entry (pointing at the old physical/virtual port) hasn't aged out yet | Send a gratuitous ARP/frame from the new location to force immediate re-learning, or wait for the aging timer to expire |
| Sudden network-wide slowdown and every device seeing traffic that isn't theirs | MAC table exhaustion (accidental — huge flat segment, or a MAC flooding attack) forcing fail-open flooding | Check switch MAC table utilization; enable port security with a MAC address limit per port; segment the network with VLANs ([§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md)) |
| Two containers on the same Docker host can't reach each other                 | Bridge forwarding database has no learned entry for one container's veth (interface down, or never sent a frame) | `bridge fdb show` to confirm the entry exists; `ip link show <veth>` to confirm the interface is up                    |

## 9. Best Practices

- Enable port security (MAC address limits per port) on access-layer switch ports in any environment where the physical or logical topology is not fully trusted, as a baseline defense against MAC flooding.
- When troubleshooting intermittent Layer 2 reachability after a topology change (VM migration, cable move, interface replacement), check for stale MAC table entries and aging behavior before assuming a routing or firewall issue.
- Monitor MAC table utilization as a genuine capacity metric on switches serving very large flat Layer 2 segments — approaching the documented table limit is a signal to segment the network (VLANs, [§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md)) rather than simply hoping it doesn't overflow.

## 10. Common Anti-Patterns / Mistakes

- **Assuming a switch "just knows" where every device is from the start.** The table is built dynamically from observed traffic; a switch has zero prior knowledge of any device until that device (or something responding to it) sends a frame.
- **Treating MAC address filtering as a real security boundary.** MAC addresses are trivially spoofable in software; port security based on MAC limits mitigates flooding-style attacks but should never be relied on as the sole access control for anything security-sensitive.
- **Debugging Layer 2 reachability issues by staring at IP-layer tools only (`ping`, `traceroute`) without ever checking the MAC table.** A large class of "unreachable" symptoms are actually stale or missing MAC table entries, which `bridge fdb` (software) or switch CLI MAC-table commands (hardware) resolve directly.

## 11. Interview Questions

**🎯 Beginner:** _"What does a switch do the very first time it receives a frame destined for a MAC address it has never seen before?"_
**Model answer:** It floods the frame out every port except the one it arrived on, because its MAC address table has no entry yet mapping that destination MAC to a specific port. At the same time, it learns the frame's source MAC address against the port it arrived on, so future frames destined to that source can be forwarded directly rather than flooded.
_What the interviewer is probing for:_ Whether the candidate understands flooding as a fallback behavior tied to an empty/incomplete table, not random or constant switch behavior.

**🎯 Intermediate:** _"What is a CAM table, and why does its aging timer matter in practice?"_
**Model answer:** A CAM table is the switch's dynamically learned mapping of MAC addresses to the ports they're reachable through, implemented in fast content-addressable memory hardware for line-rate lookups. Each entry has an aging timer — if the switch doesn't see a frame from that MAC again before the timer expires, the entry is removed. This matters in practice because it's what lets the table adapt when a device physically moves to a different port, or a VM migrates to a different host uplink — without aging, the table would eventually contain permanently stale entries pointing traffic at ports the destination no longer occupies.
_What the interviewer is probing for:_ Understanding that table aging is a deliberate adaptivity mechanism, not an incidental detail — this is directly relevant to real VM-migration and cable-move troubleshooting.

**🎯 Senior:** _"Explain how a MAC flooding attack works and why it's effective even against a fully switched network."_
**Model answer:** An attacker sends a very large volume of frames with forged, constantly changing source MAC addresses. The switch dutifully learns every one of them, since learning is unconditional per frame, and the table quickly reaches its hardware capacity limit. Once full, the switch can no longer learn legitimate new entries, and most switches respond to a full table by failing open — flooding all subsequent traffic out all ports rather than dropping it, to preserve connectivity at the cost of confidentiality. This effectively turns the switch into a hub for the segment, letting the attacker passively capture traffic that would normally have been forwarded only to its intended destination. It's effective specifically because the learning mechanism has no built-in trust or rate limiting by default — port security (limiting learnable MAC addresses per port) is the standard mitigation because it directly targets this unconditional-learning weakness.
_What the interviewer is probing for:_ Depth beyond "MAC flooding is a bad thing" — specifically, whether the candidate can explain the fail-open mechanism that makes the attack effective, and connect it to the concrete mitigation.

**🎯 Architect:** _"You're designing network monitoring for a data center with very large flat Layer 2 domains serving thousands of hosts. What MAC-table-related failure modes do you need to plan for, and how does your design address them?"_
**Model answer:** Two related risks: exceeding switch MAC table capacity under legitimate scale (thousands of real hosts plus their virtual interfaces can genuinely approach table limits on some hardware), and MAC flooding attacks that exploit the same fail-open behavior deliberately. My design would monitor MAC table utilization as a first-class capacity metric per switch, alerting well before the documented hardware limit, and would use port security with reasonable per-port MAC limits at the access layer to bound the damage from either cause — legitimate scale or attack — before the table fills. More fundamentally, I'd push back on very large flat Layer 2 domains as a design pattern at all: segmenting the data center into smaller VLANs ([§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md)) with routing between them ([§39](Section-39-Part5-Inter-VLAN-Routing.md), [§42](Section-42-Part5-Layer-2-vs-Layer-3-Switching.md)) both reduces the blast radius of any single segment's MAC table exhaustion and shrinks the broadcast domain each segment has to deal with ([§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md)), which is usually the better long-term fix versus continuing to grow one flat segment and hoping table capacity keeps up.
_What the interviewer is probing for:_ Whether the candidate connects a low-level mechanism (MAC table capacity/aging) to an actual architectural decision (segmentation via VLANs) rather than treating it as a purely operational monitoring problem.

## 12. Common Misconceptions

1. **"A switch pre-loads or is configured with a MAC address table."** The table is built dynamically and passively from observed traffic — a switch out of the box knows nothing about any device until it sees a frame from it.
2. **"MAC addresses are always globally unique."** Burned-in addresses are manufacturer-assigned and effectively globally unique, but locally administered addresses (common in virtualization) are only guaranteed unique within whatever scheme assigned them.
3. **"A full MAC table just drops new devices' traffic."** Most switches fail open, not closed — a full table causes flooding of subsequent traffic rather than blocking it, which is precisely what makes MAC flooding an effective eavesdropping technique rather than merely a denial-of-service one.
4. **"MAC address filtering is a meaningful access-control security measure."** MAC addresses are trivially spoofed in software; filtering by MAC raises only a very low bar and should never be relied upon as a primary security control.

## 13. 🔑 Key Takeaways

- A switch's MAC address table (CAM table) is built dynamically by learning the source MAC of every frame received, and consulted to look up the destination MAC of every frame forwarded.
- Flooding is the fallback behavior for unknown destinations, broadcasts, and unpruned multicasts — not the default or constant behavior of a switch.
- Table entries age out on a timer, which is what allows the table to adapt to devices moving between ports (cable moves, VM migration).
- MAC table exhaustion (accidental, from scale, or deliberate, from a flooding attack) causes fail-open flooding behavior — a real performance and security risk mitigated by port security and network segmentation.
- The Linux bridge forwarding database (`bridge fdb`) is the exact software equivalent of a hardware CAM table, learnable and inspectable with the same conceptual model.

## 14. Related Concepts & What's Next

[§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md) builds directly on the flooding behavior described here to formalize broadcast domains as distinct from collision domains. [§35](Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md) is the prerequisite device-level context this section assumed. [§40](Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md) revisits MAC table behavior in the specific failure context of a Layer 2 loop, where constant re-learning and table thrashing is one of the most visible symptoms of a spanning-tree failure. [§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md) depends on the MAC table concept extending per-VLAN once VLAN tagging is introduced — a switch actually maintains one logical MAC table per VLAN, not one global table.

**Next Section:** [§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md) — `Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md`
