# Section 35 (Part 5): What Switching Is; Hubs vs. Switches vs. Bridges

## 1. Definition

**Plain language:** Switching is how devices on the same local network exchange data directly with each other instead of every device shouting on a shared wire and hoping the right one hears. A switch is the device that makes this efficient: it looks at where a frame is going and forwards it only out the one port that leads there, rather than blasting it out every port. Hubs and bridges are the ancestors that led to the modern switch, and understanding why they were replaced explains why switches behave the way they do.

**Precise definition:** **Switching** is the Layer 2 (Data Link layer) function of forwarding **Ethernet frames** between devices on the same local segment based on destination **MAC address**, rather than flooding every frame to every attached device. A **hub** is a legacy, purely electrical Layer 1 device: it repeats every incoming electrical signal out every other port with no awareness of frames or addresses at all, so every attached device shares one **collision domain** and one **bandwidth budget**. A **bridge** is the historical bridge between hub and switch: an early Layer 2 device, typically with only a handful of ports, that learns MAC addresses and forwards frames intelligently but does so mostly in software, limiting throughput. A **switch** is, functionally, a **multi-port bridge implemented in dedicated hardware (ASICs)** — the same MAC-learning and selective-forwarding logic as a bridge, but built to switch dozens or hundreds of ports at line rate.

> 💡 **Tip:** The cleanest way to remember the hierarchy: a hub doesn't read frames at all (Layer 1, pure electrical repeater), a bridge reads frames but forwards them in software at a handful of ports (Layer 2, low port density), and a switch is a bridge that got hardware-accelerated and given many more ports (Layer 2, ASIC-forwarded, high port density). Modern infrastructure essentially never uses hubs or standalone bridges — the vocabulary survives because "bridge" is still the correct term for a Linux kernel software construct (`brctl`, `ip link add type bridge`) that behaves exactly like this historical device.

## 2. Why This Matters

- **Every data center and cloud instance's virtual networking is switching under the hood.** A hypervisor's virtual switch, a Linux bridge behind a set of containers, and a cloud provider's VPC subnet fabric are all doing MAC-address-based Layer 2 forwarding — understanding physical switching is the mental model for all of them.
- **Collision domains explain why old shared-media networks degraded under load and modern switched networks don't.** This directly informs why a hub-based network is essentially never seen in production today, and why "shared bandwidth" complaints from that era don't apply to switched Ethernet.
- **Troubleshooting a "device unreachable on the LAN" problem starts by understanding what a switch actually does with a frame** — if you don't know a switch floods frames for unknown destinations and forwards known ones out a single port, you can't reason about why a `ping` fails but ARP succeeds, or vice versa.
- **Container and VM networking on a single host is implemented with software bridges** (Linux `bridge`, Open vSwitch) — every Docker or Kubernetes host networking diagram assumes the reader understands what a bridge does, since `docker0` or `cni0` literally is one.
- **Interview and certification relevance.** Distinguishing hub/bridge/switch behavior by OSI layer and collision-domain impact is one of the most common entry-level networking screening questions.

## 3. Prerequisites and Dependencies

This section assumes the OSI/TCP-IP layer model and basic frame/packet terminology from Part 2 ([§8](../Part2/Section-08-Part2-The-OSI-7-Layer-Model-Purpose-and-Layer-by-Layer-Breakdown.md)-[§14](../Part2/Section-14-Part2-Common-Protocols-Mapped-to-Their-OSI-TCP-IP-Layer.md)), and general network-type vocabulary from [§4](../Part1/Section-04-Part1-Network-Types-LAN-WAN-MAN-PAN-and-the-Data-Center-Network.md). No prior switching-specific knowledge is assumed — this is the entry point of Part 5. [§36](Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md) builds directly on this section by explaining exactly how a switch decides which single port to forward a frame out of (the MAC address table). [§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md) depends on this section's collision-domain concept to introduce the parallel idea of broadcast domains. [§25](../Part4/Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md) (Part 4) contrasts switches against routers at the "what problem does each device solve" level, which is worth revisiting once inter-VLAN routing ([§39](Section-39-Part5-Inter-VLAN-Routing.md)) and Layer 3 switching ([§42](Section-42-Part5-Layer-2-vs-Layer-3-Switching.md)) come up later in this Part.

## 4. Architecture / Conceptual Diagram

```text
   HUB (Layer 1)                BRIDGE (Layer 2, few ports)      SWITCH (Layer 2, many ports, ASIC)

   PC-A --\                     PC-A --\                         PC-A --\
   PC-B ---+-- [ HUB ] --+      PC-B ---+-[BRIDGE]-+              PC-B ---+
   PC-C --/              |      PC-C --/           |              PC-C ---+--[ SWITCH ]--+-- PC-D
                          |                          |                     PC-D ---+       (hardware-
   Frame from PC-A -------+      Frame from PC-A -----+          PC-E ---+       forwarded,
   is repeated out EVERY   (electrical signal only,    is examined; learns    per-port
   other port — no frame    no frame inspection)        source MAC; forwards  bandwidth,
   inspection at all.                                   only toward known     no shared
                                                         destination port,     collision
   ONE collision domain                                 floods if unknown     domain)
   shared by all ports.
```

- **Hub:** operates purely at Layer 1 — it has no concept of a "frame," only electrical signal levels. It repeats bits out every port simultaneously, which means every device attached to a hub is in the same collision domain ([§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md)) and effectively shares total bandwidth. Two devices transmitting at once on a hub produces a **collision**, requiring retransmission (CSMA/CD).
- **Bridge:** the first Layer 2 device — it reads the destination MAC address in each frame, maintains a learned table of which port each MAC address lives behind, and forwards frames only toward the correct port when known (flooding when unknown, exactly as a switch does — see [§36](Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md)). Early bridges did this forwarding in software on general-purpose CPUs, limiting them to a handful of ports before performance collapsed.
- **Switch:** functionally identical logic to a bridge, but implemented in purpose-built ASIC hardware capable of looking up and forwarding frames at line rate across dozens or hundreds of ports simultaneously — this is why a switch, unlike a hub, gives every port its own effective collision domain (a full-duplex switch port has no collisions at all).
- The historical arc (hub → bridge → switch) is also the mental model for **virtual** switching: a Linux bridge or Open vSwitch instance on a hypervisor host is architecturally a software bridge, doing the exact same MAC-learning and forwarding logic described here for virtual machines and containers instead of physical ports.

## 5. Hands-On

### 5.1 Inspecting a Host's Link-Layer Interfaces

**Purpose:** Confirm which network interfaces on a Linux host exist at Layer 2, and distinguish a physical NIC from a software bridge interface.

**Syntax:**

```bash
ip link show
ip -d link show <interface>
```

**Example usage and expected output:**

```bash
$ ip link show
1: lo: <LOOPBACK,UP,LOWER_UP> mtu 65536 qdisc noqueue state UNKNOWN
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP mode DEFAULT
    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff
3: docker0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT
    link/ether 02:42:9a:1b:7c:44 brd ff:ff:ff:ff:ff:ff

$ ip -d link show docker0
3: docker0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc noqueue state UP mode DEFAULT
    link/ether 02:42:9a:1b:7c:44 brd ff:ff:ff:ff:ff:ff promiscuity 0
    bridge forward_delay 1500 hello_time 200 max_age 2000 ageing_time 30000 ...
```

**Production usage example:** Every Docker host runs `docker0` as a real Linux bridge; `ip -d link show docker0` confirming `bridge <parameters>` in its output is a standard first troubleshooting step when containers on the same host can't reach each other, confirming the bridge device itself is up before investigating iptables/nftables rules or container-side interfaces.

**Common errors:** Confusing a bridge interface's own MAC address (assigned to the bridge device itself) with the MAC addresses of the interfaces attached to it — `bridge link show` (§5.2) shows attached members, `ip link show` alone does not.

### 5.2 Creating and Inspecting a Linux Software Bridge

**Purpose:** Demonstrate the bridge concept concretely by building one, attaching a physical/virtual interface to it, and confirming forwarding behavior — this is exactly what container runtimes and hypervisors automate.

**Syntax:**

```bash
ip link add name br0 type bridge
ip link set dev eth1 master br0
ip link set br0 up
bridge link show
```

**Example usage and expected output:**

```bash
$ sudo ip link add name br0 type bridge
$ sudo ip link set dev eth1 master br0
$ sudo ip link set br0 up
$ bridge link show
3: eth1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 master br0 state forwarding priority 32 cost 4
5: br0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 state up priority 32768
```

**Production usage example:** This is precisely how a KVM/libvirt hypervisor host wires virtual machine tap interfaces into a shared Layer 2 segment, and how `docker0`/`cni0` are constructed under the hood for container networking ([§101](../Part12/Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md), Part 13) — the same primitive scales from "one engineer's lab VM" to a production container host with dozens of pod interfaces attached.

**Common errors:** Attaching an interface to a bridge (`master br0`) without first removing any IP address configured directly on that interface — an interface that is a bridge member should not itself hold the host's IP; the IP belongs on the bridge device (`br0`) instead, and forgetting this is one of the most common Linux bridging misconfigurations.

### 5.3 Legacy `brctl` Bridge Inspection (for Reading Older Systems)

**Purpose:** Recognize the older `bridge-utils` tooling (`brctl`) still found on older Linux systems and in older documentation, even though `ip link`/`bridge` (iproute2) is the modern standard.

**Syntax:**

```bash
brctl show
brctl showmacs <bridge-name>
```

**Example usage and expected output:**

```bash
$ brctl show
bridge name     bridge id               STP enabled     interfaces
br0             8000.0242ac110002       no              eth1

$ brctl showmacs br0
port no    mac addr           is local?    ageing timer
1          02:42:ac:11:00:03      no           12.34
```

**Production usage example:** Encountering `brctl` in an older runbook or on a legacy host is common enough that recognizing its output format matters even though new automation should use `ip link`/`bridge` — `bridge-utils` is deprecated but still installed on many long-lived systems.

**Common errors:** Assuming `brctl` and `ip link`/`bridge` show identical information in identical formats — the STP-enabled column and MAC-table view differ in presentation, and mixing tooling generations in scripts causes brittle text-parsing bugs.

## 6. Production Usage Notes

- **Physical hubs are essentially extinct in production infrastructure.** Their only realistic modern appearance is legacy lab equipment or deliberately inserted for packet-capture "tap" scenarios where the property of "everyone sees everything" is actually desired (and even then, a dedicated network TAP or switch SPAN/mirror port is the modern equivalent, [§14](../Part2/Section-14-Part2-Common-Protocols-Mapped-to-Their-OSI-TCP-IP-Layer.md)).
- **"Bridge" as a term survives specifically in software networking.** Every mention of a Linux bridge, an Open vSwitch bridge, or a hypervisor's virtual switch is invoking the same Layer 2 learn-and-forward model described here, just implemented as a kernel data structure instead of physical silicon.
- **Switch ASICs forward at line rate using dedicated lookup hardware (CAM/TCAM), not general-purpose CPU cycles** — this is the concrete engineering reason a 48-port hardware switch can forward frames on every port simultaneously at full line rate while a software bridge on a busy Linux host can become CPU-bound under heavy traffic.

## 7. Security Considerations

- A **hub's** broadcast-everything behavior is a passive eavesdropping risk by design — any device on a hub segment can observe all traffic; this is one of the concrete security reasons hubs were retired industry-wide, independent of their performance limitations.
- A switch's per-destination forwarding means passive eavesdropping requires an active attack technique (MAC flooding to force fail-open flooding behavior, or ARP spoofing to redirect traffic) rather than simply listening — [§36](Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md) covers the MAC table exhaustion attack this enables, and switch **port security** features exist specifically to mitigate it.
- A Linux software bridge with promiscuous-mode member interfaces (common in packet-capture and network-function-virtualization setups) intentionally reintroduces hub-like visibility on that segment — this is a deliberate design choice for tools like `tcpdump`/traffic mirroring, but it must never be left enabled on a production data-carrying bridge.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Likely Cause                                                                                   | Resolution Path                                                                                                     |
| ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| Two devices behind the same switch can't reach each other at all         | An interface is administratively down, or attached to the wrong bridge/VLAN                    | `ip link show` to confirm interface state; `bridge link show` to confirm correct bridge membership                    |
| Intermittent packet loss and high collision counters on an old segment   | A hub (or hub-like shared-media segment) is still in use, overloading one shared collision domain | Replace the hub with a switch; verify with `ethtool <iface>` that ports are running full-duplex, not half-duplex     |
| Containers on the same Docker host cannot reach each other               | `docker0` bridge is down, or a container's veth pair isn't attached to the bridge               | `ip -d link show docker0` to confirm bridge is up; `bridge link show` to confirm the container's veth is a member    |

## 9. Best Practices

- Treat any discovery of a physical hub in a production network path as an immediate replacement candidate — the collision-domain and eavesdropping downsides have no modern justification outside deliberate lab/tap use cases.
- When building or debugging Linux bridges, always verify interface state with both `ip link show` (interface up/down) and `bridge link show` (bridge membership and STP forwarding state) — checking only one gives an incomplete picture.
- Prefer modern `iproute2` tooling (`ip link`, `bridge`) over legacy `brctl` for any new automation or scripts, reserving `brctl` familiarity for reading older systems and documentation.

## 10. Common Anti-Patterns / Mistakes

- **Assigning an IP address directly to a bridge member interface instead of the bridge device itself.** The IP belongs on `br0` (or `docker0`), not on the physical/virtual interface attached to it — this is one of the most common Linux bridging setup mistakes and produces confusing, asymmetric connectivity.
- **Conflating "switch" and "router" as interchangeable terms** because both are "the box in the network closet" — a switch forwards based on MAC address within one broadcast domain; a router forwards based on IP address between networks ([§25](../Part4/Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md)). Using the terms interchangeably in documentation causes real confusion during incident response.
- **Leaving a bridge or switch port in promiscuous/mirror mode after a debugging session ends**, silently reintroducing hub-like traffic visibility on a segment that should have switched (per-destination) forwarding.

## 11. Interview Questions

**🎯 Beginner:** _"What is the fundamental difference between a hub and a switch?"_
**Model answer:** A hub is a Layer 1 device that repeats every incoming electrical signal out every other port with no awareness of frames or addresses, meaning all connected devices share one collision domain and one bandwidth pool. A switch is a Layer 2 device that reads the destination MAC address of each frame and forwards it only out the port leading to that specific destination, giving each port its own effective collision domain and much better performance and security.
_What the interviewer is probing for:_ Basic grasp of the OSI layer distinction and why it has real performance consequences, not just rote vocabulary.

**🎯 Intermediate:** _"How does a switch differ from a bridge, given that they use the same forwarding logic?"_
**Model answer:** A bridge and a switch both learn MAC addresses and forward frames selectively rather than flooding — a switch is, functionally, a bridge. The practical difference is implementation and scale: classic bridges forwarded frames in software on general-purpose hardware and typically had only a handful of ports, which limited throughput as traffic grew. Switches implement the identical logic in dedicated ASIC hardware, letting them forward frames at line rate across dozens or hundreds of ports simultaneously. The term "bridge" survives today mainly for software constructs like Linux bridges and Open vSwitch, which behave exactly like the historical device.
_What the interviewer is probing for:_ Understanding that "switch" isn't a different algorithm from "bridge," just a different implementation and scale — a subtlety that's easy to memorize backward.

**🎯 Senior:** _"A junior engineer says 'we should use a hub here so the monitoring tool can see all the traffic.' How do you respond, and what's the actual right way to achieve that goal?"_
**Model answer:** The underlying goal — visibility into all traffic on a segment — is legitimate, but a hub is the wrong tool: it degrades every device on the segment to a shared collision domain and shared bandwidth pool, and it's effectively unavailable/unsupported hardware today. The correct modern approach is a switch **SPAN/mirror port** (or a dedicated network TAP device) that explicitly copies traffic from one or more source ports to a monitoring port, without affecting the collision domain or forwarding behavior of the production ports at all. This achieves full visibility for the monitoring tool while keeping the production segment fully switched.
_What the interviewer is probing for:_ Whether the candidate can translate an outdated but still commonly proposed idea ("use a hub for visibility") into the correct modern equivalent, showing they understand the underlying goal, not just the vocabulary.

**🎯 Architect:** _"You're designing the host networking for a new container platform. Walk through why a Linux bridge is the right primitive here, and what happens conceptually as you scale from one host to a multi-host cluster."_
**Model answer:** On a single host, containers need to exchange Layer 2 frames with each other and reach the outside world through the host's physical NIC — a Linux bridge is exactly the right primitive because it gives every container's veth interface a shared Layer 2 segment with MAC-learning and selective forwarding, identical to a physical switch, at essentially zero extra cost since it's a kernel feature. As the platform scales to multiple hosts, the single-bridge model breaks down: containers on different hosts are not on the same physical segment, so pure bridging can't span hosts without either a Layer 2 extension technology (VXLAN or similar overlay, [§43](Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md)) or a Layer 3 routed approach between hosts. This is exactly the point where the mental model shifts from "one big switched segment" to "an overlay network across independently switched segments," which is the architectural bridge (no pun intended) into SDN and container networking's overlay model.
_What the interviewer is probing for:_ Whether the candidate can extend the single-host bridging model to the actual scaling problem multi-host container networking solves, previewing the overlay-network concepts covered later ([§43](Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md), [§101](../Part12/Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md)).

## 12. Common Misconceptions

1. **"Switches and bridges use fundamentally different forwarding logic."** They don't — a switch is functionally a hardware-accelerated, high-port-density bridge; the forwarding algorithm (learn source MAC, forward toward known destination, flood unknown) is identical.
2. **"Hubs are just slower switches."** A hub isn't a slower version of the same device — it operates at a different OSI layer entirely (Layer 1, no frame awareness) and creates a fundamentally different collision-domain topology, not merely a performance difference.
3. **"A switch port with nothing obviously wrong can't be a security risk."** Passive eavesdropping on a switched network is harder than on a hub, but active techniques (MAC table exhaustion, forcing fail-open flooding) can recreate hub-like visibility — switch security is not "solved by default" just because switches forward selectively.
4. **"Bridge" always means physical hardware.** In modern infrastructure, "bridge" most commonly refers to a software construct (Linux kernel bridge, Open vSwitch) — the term outlived the specific hardware device it originally named.

## 13. 🔑 Key Takeaways

- Hubs (Layer 1, no frame awareness, one shared collision domain), bridges (Layer 2, software-forwarded, few ports), and switches (Layer 2, hardware/ASIC-forwarded, many ports) form a historical progression of the same core idea: forward data only where it needs to go.
- A switch is functionally a multi-port, hardware-accelerated bridge — not a different forwarding algorithm.
- Every full-duplex switch port has its own collision domain, eliminating the shared-bandwidth and collision problems inherent to hubs.
- "Bridge" survives today mostly as a software networking term (Linux bridges, Open vSwitch) that implements the identical learn-and-forward logic for virtual machines and containers.
- Understanding this device hierarchy is the foundation for everything else in Part 5: MAC learning ([§36](Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md)), broadcast/collision domains ([§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md)), VLANs ([§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md)), and eventually SDN/overlay networking ([§43](Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md)).

## 14. Related Concepts & What's Next

[§36](Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md) opens up exactly how a switch decides which single port to forward a frame toward — the MAC address table (CAM table) only gestured at here. [§37](Section-37-Part5-Broadcast-Domains-vs-Collision-Domains.md) formalizes the collision-domain concept introduced in this section and contrasts it with the separate concept of broadcast domains. [§25](../Part4/Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md) (Part 4) revisits the switch-vs-router distinction from the routing side once inter-VLAN routing ([§39](Section-39-Part5-Inter-VLAN-Routing.md)) and Layer 3 switching ([§42](Section-42-Part5-Layer-2-vs-Layer-3-Switching.md)) are on the table. [§101](../Part12/Section-101-Part12-Subnets-Route-Tables-and-Availability-Zones-in-Cloud-Networks.md) (Part 13) returns to the Linux bridge example built in §5.2 in the specific context of container networking.

**Next Section:** [§36](Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md) — `Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md`
