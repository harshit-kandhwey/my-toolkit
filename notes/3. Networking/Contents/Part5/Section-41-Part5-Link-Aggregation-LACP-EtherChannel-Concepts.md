# Section 41 (Part 5): Link Aggregation (LACP/EtherChannel) Concepts

## 1. Definition

**Plain language:** If you plug two cables between the same two switches (or a server and its switch), Spanning Tree Protocol will notice the loop and block one of them, leaving it idle — good for safety, wasteful for bandwidth. Link aggregation is the alternative for exactly this specific case: instead of treating the two cables as a loop to defend against, you bundle them into one logical link that both devices agree to use simultaneously, getting combined bandwidth and redundancy at the same time, with no port ever sitting idle.

**Precise definition:** **Link aggregation** is the combination of multiple physical network links between the same two devices into a single logical link, presented to upper layers (MAC learning, STP, routing) as one interface with combined bandwidth and built-in redundancy — if one member link fails, traffic continues over the remaining members with no topology recalculation needed. **LACP** (Link Aggregation Control Protocol, IEEE 802.3ad, standardized further under 802.1AX) is the vendor-neutral **standard** protocol that dynamically negotiates and monitors which physical links should be active members of the aggregate, using periodic LACPDU control messages between both ends. **EtherChannel** is Cisco's brand name for its link aggregation feature, which can operate using LACP, Cisco's own proprietary **PAgP** (Port Aggregation Protocol), or **static/manual** configuration with no negotiation protocol at all. Other vendors have their own branded terms for the identical underlying concept (e.g., "Link Aggregation Group"/LAG, "trunk" in some non-Cisco vendor terminology — a genuinely overloaded word across the industry, distinct from the 802.1Q "trunk" meaning used in [§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md)).

> 💡 **Tip:** The clean mental separation from STP ([§40](Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md)): STP manages redundancy **between separate paths through different devices**, keeping only one path active at a time. Link aggregation manages redundancy **for multiple parallel links between the very same two devices**, keeping all of them active simultaneously as one logical link. If you ever find yourself asking "should this be LACP or STP," the answer is determined entirely by whether the redundant links terminate on the same device pair (LACP) or different devices (STP) — not personal preference.

## 2. Why This Matters

- **Bandwidth aggregation without wasting hardware** — a single 10 Gbps link becoming a bottleneck doesn't necessarily require replacing the NIC/switch with faster hardware; bundling two or four existing 10 Gbps links via LACP can multiply available bandwidth between the same two devices using equipment already in place.
- **Sub-second failover with zero STP recalculation** — because the aggregate is presented as one logical interface, losing a member link doesn't trigger any spanning-tree topology change at all; traffic simply redistributes across the remaining active members, which is meaningfully faster and less disruptive than an STP re-convergence event.
- **This is directly relevant to server/hypervisor NIC teaming** — a database server or hypervisor host with two or four physical NICs bonded together (Linux "bonding," which implements the identical LACP concept in software) is one of the most common real-world applications of this exact mechanism outside of switch-to-switch uplinks.
- **Load-balancing/hashing behavior on an aggregate is a genuinely subtle, production-relevant detail** — understanding how traffic is actually distributed across member links (by flow hash, not evenly per-packet) explains real-world symptoms like "the aggregate shows 40 Gbps total capacity but one flow never exceeds 10 Gbps."
- **Interview and design-review fluency** — link aggregation is one of the most common redundancy/bandwidth design questions in infrastructure interviews, and confusing it with STP or VLAN trunking (a common vocabulary collision) is an easy, telling mistake.

## 3. Prerequisites and Dependencies

Builds directly on [§40](Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md) (Spanning Tree Protocol), since the clearest way to understand link aggregation's purpose is by contrast with STP's different approach to the same underlying goal (redundant physical links). [§35](Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md) and [§36](Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md) (switch/bridge forwarding and MAC learning) matter because an aggregate link is presented as a single logical interface to the MAC learning process — the switch learns MAC addresses against the aggregate as a whole, not against individual member links. [§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md) (VLANs and trunking) is relevant because an aggregate link commonly also carries 802.1Q-tagged trunk traffic simultaneously — the two features compose (an aggregated trunk), and it's worth being precise that "trunk" in the 802.1Q sense and "trunk" as some vendors' term for a LAG are different things.

## 4. Architecture / Conceptual Diagram

```text
   WITHOUT LINK AGGREGATION            WITH LINK AGGREGATION (LACP)
   (STP must block one link)           (both links active as ONE logical interface)

   Switch A                            Switch A
     │  eth1 ──┐                         │  eth1 ┐
     │  eth2 ──┼── Switch B                │  eth2 ┴─ bond0 (LAG) ──── Switch B
     │         │   (eth1: FORWARDING,      │         (both members ACTIVE,
     │         │    eth2: BLOCKING          │          traffic hashed across
     │         │    via STP — idle!)       │          both, combined bandwidth,
                                            │          logical single interface)

   Failure of eth1:                    Failure of one member (e.g. eth1):
   STP recalculates topology,          LACP detects it within its hello
   unblocks eth2 — takes on the         interval, redistributes traffic
   order of seconds (even with RSTP)    across remaining member(s) — no
   to converge.                        STP recalculation triggered at all.

   TRAFFIC DISTRIBUTION ACROSS AN LACP AGGREGATE (hash-based, per-flow)

   Flow 1 (5-tuple hash A) ──────────────► always sent via member eth1
   Flow 2 (5-tuple hash B) ──────────────► always sent via member eth2
   A SINGLE flow's traffic never splits across multiple members — the
   AGGREGATE's total bandwidth is shared across many flows, not any one flow.
```

- **LACP negotiation:** both ends periodically exchange LACPDUs identifying themselves and their configured aggregation preferences; only links where both ends agree to aggregate (matching speed, duplex, and LACP configuration) are placed into the **active** aggregate — mismatched or misconfigured links are excluded rather than silently causing a loop.
- **Static (manual) aggregation** skips this negotiation entirely — both ends are simply configured to treat a set of links as one logical bundle, with no protocol verifying the other end agrees. This works but is fragile: a cabling mistake or one-sided misconfiguration produces a real, undetected mismatch rather than the automatic exclusion LACP would perform.
- **Hashing (load distribution) is per-flow, not per-packet.** A hash function (commonly based on some combination of source/destination MAC, IP, and/or Layer 4 port — the "5-tuple") assigns each individual flow deterministically to one member link for its entire duration, preserving in-order delivery for that flow. This is why a single large transfer between two hosts never exceeds one member link's bandwidth, even on a multi-member aggregate — only aggregate traffic across many flows benefits from the combined bandwidth.

## 5. Hands-On

### 5.1 Creating a Linux Bonded Interface (LACP Mode)

**Purpose:** Build a working link aggregation group on a Linux host using LACP negotiation — the direct software equivalent of configuring LACP EtherChannel on a switch, commonly used for server/hypervisor NIC teaming.

**Syntax:**

```bash
ip link add bond0 type bond mode 802.3ad
ip link set <interface> master bond0
ip link set bond0 up
```

**Example usage and expected output:**

```bash
$ sudo ip link add bond0 type bond mode 802.3ad
$ sudo ip link set eth1 master bond0
$ sudo ip link set eth2 master bond0
$ sudo ip link set bond0 up
$ cat /proc/net/bonding/bond0
Bonding Mode: IEEE 802.3ad Dynamic link aggregation
Transmit Hash Policy: layer2 (0)
MII Status: up
802.3ad info
    LACP active: on
    Aggregator selected: 1
    Number of ports: 2
Slave Interface: eth1
MII Status: up
Slave Interface: eth2
MII Status: up
```

**Production usage example:** A hypervisor host with two 10 Gbps NICs commonly bonds them into one `bond0` interface in LACP mode connected to matching LACP-configured switch ports — VM traffic is then distributed across both physical NICs by flow, with automatic failover if either NIC or its cable fails, without any VM-visible network interruption.

**Common errors:** Configuring LACP mode (`802.3ad`) on the Linux host without configuring the corresponding switch ports as an LACP-negotiated EtherChannel — LACP requires **both ends** to agree; a one-sided configuration results in the bond failing to aggregate correctly (often falling back to using only one member link, or none at all, depending on the failure mode).

### 5.2 Verifying Bond/Aggregate Member Status and Traffic Distribution

**Purpose:** Confirm which physical interfaces are actually active members of an aggregate at a given moment, and observe per-member traffic to validate hash-based distribution is actually spreading load.

**Syntax:**

```bash
cat /proc/net/bonding/<bond-name>
ip -s link show <member-interface>
```

**Example usage and expected output:**

```bash
$ cat /proc/net/bonding/bond0 | grep -A2 "Slave Interface"
Slave Interface: eth1
MII Status: up
Slave Interface: eth2
MII Status: down            # this member has failed but traffic continues on eth1

$ ip -s link show eth1
2: eth1: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP
    RX: bytes  packets ...
```

**Production usage example:** During a suspected NIC or cabling failure on a bonded server, checking `/proc/net/bonding/bond0` immediately shows whether the bond has already failed over correctly (one member `down`, the other still `up` and presumably carrying all traffic) — a fast, definitive confirmation that redundancy worked as intended, versus needing to infer it indirectly from application-level symptoms.

**Common errors:** Assuming even traffic distribution across bond members proves the bond is healthy — a bond can show one member handling nearly all traffic simply because most active flows hashed to that member, which is normal hash-based behavior, not a sign of a failed or misconfigured member; checking `MII Status` directly is the definitive health signal, not traffic volume alone.

### 5.3 Choosing and Setting a Transmit Hash Policy

**Purpose:** Select an appropriate load-distribution hash policy for a bond, since the default may not distribute traffic well for a given traffic pattern (e.g., traffic between the same two hosts on the same ports would hash identically under a source/destination-MAC-only policy).

**Syntax:**

```bash
ip link set <bond-name> type bond xmit_hash_policy <policy>
```

**Example usage and expected output:**

```bash
$ sudo ip link set bond0 type bond xmit_hash_policy layer3+4
$ cat /proc/net/bonding/bond0 | grep "Transmit Hash Policy"
Transmit Hash Policy: layer3+4 (1)
```

**Production usage example:** A bonded host that is a router or gateway for many client flows between the same pair of outer IP addresses (e.g., a NAT gateway) benefits from a `layer3+4` (IP address plus Layer 4 port) hash policy rather than a MAC-address-only policy, since the latter would hash all traffic between the same two next-hop MAC addresses onto the same single member link regardless of how many distinct underlying flows are actually present — defeating the purpose of aggregation for that specific traffic pattern.

**Common errors:** Leaving the default hash policy in place for a traffic pattern it doesn't suit well, then concluding "link aggregation isn't giving us more bandwidth" — the aggregate's total capacity is real, but a poorly chosen hash policy can concentrate the actual traffic pattern onto too few member links to realize it.

## 6. Production Usage Notes

- **LACP is strongly preferred over static/manual aggregation in production** specifically because it actively verifies both ends agree before including a link in the aggregate — a static aggregate with a one-sided misconfiguration or a miscabled link can silently create a real loop or a broken aggregate, exactly the kind of failure LACP's negotiation is designed to catch and exclude automatically.
- **A single flow's throughput is capped at one member link's bandwidth, never the aggregate total** — this is a frequent point of confusion during capacity planning, and matters directly when the workload is dominated by a small number of very large flows (e.g., one large backup transfer) rather than many concurrent smaller flows.
- **Hash policy choice is a real production tuning lever**, not a cosmetic setting — the right policy depends on the actual traffic pattern (many hosts and flows vs. a small number of high-volume flows between the same endpoints), and the default is not universally optimal.

## 7. Security Considerations

- **LACP itself carries limited direct security exposure** compared to STP's BPDU-spoofing concerns ([§40](Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md)), since LACPDUs are typically only exchanged on links explicitly configured for aggregation between trusted infrastructure devices — but a rogue device physically inserted into an aggregate-eligible link could attempt to negotiate LACP itself, so aggregation-capable ports facing untrusted or unmanaged spaces should be explicitly restricted, similar in spirit to BPDU Guard for STP.
- **A misconfigured static (non-LACP) aggregate is itself a latent security and stability risk** — because there's no negotiation to catch a one-sided or asymmetric configuration, a mistake here can produce genuinely unpredictable forwarding behavior (including loop-like symptoms) that's harder to diagnose than an LACP failure, which fails safely by simply excluding the mismatched link.
- **Bonded/aggregated interfaces don't add or remove any of the actual traffic-encryption or access-control properties of the underlying links** — aggregation is purely a bandwidth/redundancy mechanism, and any security posture (segmentation, ACLs, VLANs) that applied to the traffic before aggregation still needs to be enforced identically afterward.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                       | Likely Cause                                                                                       | Resolution Path                                                                                                             |
| ------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| Bond/EtherChannel shows fewer active members than physically connected          | LACP negotiation failing on one or more links (mismatched speed/duplex, or switch-side not configured for LACP) | Check LACP status on both host and switch; confirm matching mode, speed, and duplex on all intended member links            |
| A single large transfer never exceeds one member link's bandwidth              | Expected hash-based behavior — one flow is pinned to one member link by design                       | Confirm this is expected behavior (not a fault); if aggregate bandwidth for single large flows is a real requirement, consider a different design (e.g., a single faster link) |
| Aggregate appears to work but occasional packet reordering or drops occur       | Static (non-LACP) aggregate with a subtle one-sided misconfiguration, or a hash policy mismatch between ends | Migrate to LACP for active negotiation and verification; audit both ends' configuration for consistency                     |

## 9. Best Practices

- Prefer LACP over static/manual link aggregation in essentially all production scenarios, specifically for its active mismatch detection and exclusion behavior.
- Choose a hash policy deliberately based on actual traffic patterns (many small flows vs. few large flows, Layer 2 vs. Layer 3/4 diversity) rather than leaving a default that may not distribute load effectively for the workload.
- Ensure matching configuration (speed, duplex, LACP mode, VLAN/trunk settings) across every member link on both ends before enabling aggregation, since mismatches are a common source of partial or failed aggregation.
- Monitor both aggregate-level and per-member-link traffic and health, since aggregate-level metrics alone can mask an already-failed individual member being silently compensated for by the others.

## 10. Common Anti-Patterns / Mistakes

- **Expecting a single flow's throughput to scale with the number of aggregated links.** Aggregation increases total aggregate capacity across many flows, not the ceiling for any individual flow — a common, costly misunderstanding during capacity planning for workloads dominated by a few large transfers.
- **Using static aggregation instead of LACP "because it's simpler," without accounting for the loss of negotiation-based mismatch detection** — the simplicity comes at the cost of exactly the safety property that makes aggregation reliable in production.
- **Configuring aggregation on only one end of a link pair** (e.g., bonding on the server but leaving the switch ports as independent, non-aggregated access ports) — with LACP this typically fails safely (no aggregate forms), but with static aggregation this can produce genuinely broken or loop-like behavior.
- **Conflating link aggregation ("LAG"/EtherChannel/bonding) with 802.1Q VLAN trunking** just because both are sometimes casually called "trunk" — they are different features that frequently coexist (an aggregated link commonly also carries tagged VLAN traffic) but solve entirely different problems.

## 11. Interview Questions

**🎯 Beginner:** _"What problem does link aggregation solve, and how is LACP different from a purely static/manual configuration?"_
**Model answer:** Link aggregation combines multiple physical links between the same two devices into one logical link, giving combined bandwidth and automatic failover without any of the member links sitting idle. LACP is the standard protocol that actively negotiates this between both ends — each side advertises its configuration, and only links where both ends agree are included in the active aggregate, with mismatches automatically excluded. A static/manual configuration skips that negotiation entirely, simply treating a set of links as bundled by configuration on both ends without any protocol verifying agreement, which makes misconfigurations harder to detect.
_What the interviewer is probing for:_ Whether the candidate understands aggregation's core value (combined bandwidth plus redundancy with no idle links) and specifically why LACP's negotiation is safer than static configuration.

**🎯 Intermediate:** _"How does link aggregation distribute traffic across its member links, and what's a common misunderstanding about this?"_
**Model answer:** Traffic is distributed using a hash function — commonly based on some combination of source/destination MAC address, IP address, and Layer 4 port — that deterministically assigns each individual flow to exactly one member link for its duration, which preserves in-order packet delivery for that flow. A common misunderstanding is expecting a single flow's throughput to scale with the number of aggregated links; in reality, one flow is always pinned to one member link, so its throughput ceiling is that single link's bandwidth, not the aggregate's total. The combined bandwidth benefit only materializes across many concurrent flows being spread across different member links.
_What the interviewer is probing for:_ Whether the candidate understands the hash-based, per-flow nature of load distribution and its direct practical implication for single-flow throughput expectations.

**🎯 Senior:** _"When would you choose Spanning Tree Protocol over link aggregation for redundant links, and when would you choose the reverse?"_
**Model answer:** The deciding factor is topology, not preference: link aggregation only applies when the redundant links connect the exact same pair of devices — it bundles multiple parallel links into one logical interface, using all of them simultaneously. STP is necessary whenever redundancy comes from genuinely separate paths through different devices (a switch with uplinks to two different upstream switches, for instance), where there's no way to bundle the links into a single logical interface because they don't terminate on the same device pair. In practice, both are often used together in the same topology: LACP bundles any parallel links between the same device pair for bandwidth and fast local failover, while STP (or a modern equivalent like Layer 3 ECMP routing) still manages the broader topology's genuinely separate redundant paths.
_What the interviewer is probing for:_ Whether the candidate correctly identifies topology (same device pair vs. different devices) as the deciding factor, rather than treating LACP and STP as interchangeable or competing choices for the same problem.

**🎯 Architect:** _"You're designing server-to-switch connectivity for a fleet of database hosts that need both high throughput and resilience to a single NIC or cable failure, with a mix of workloads — some dominated by many small connections, others by a few very large data transfers. How do you approach the bonding design?"_
**Model answer:** I'd use LACP-based bonding (802.3ad mode) across at least two NICs per host to matching LACP-configured switch ports, for the active mismatch-detection benefits over static aggregation. For the hash policy, I'd deliberately choose based on the dominant traffic pattern per workload tier rather than accepting a single default across the whole fleet: hosts serving many concurrent smaller connections benefit from a Layer 3/4-aware hash policy that spreads that flow diversity well across member links, while I'd flag explicitly to stakeholders that hosts dominated by a few very large transfers (e.g., large backup or replication jobs) will NOT see those specific transfers exceed one member link's bandwidth no matter how many links are bonded, since a single flow is always pinned to one member — for those specific workloads, if per-transfer throughput beyond a single link's speed is a hard requirement, the actual fix is faster individual links (upgrading from bonded 10 Gbps to fewer, faster 25/40/100 Gbps links) rather than more aggregation. I'd also ensure monitoring covers both aggregate-level and per-member-link health and utilization, since a silently degraded member (still passing LACP but with elevated errors) can be masked by the others compensating, and would only surface as a capacity or reliability issue once a second member also degrades or fails.
_What the interviewer is probing for:_ Whether the candidate correctly separates "aggregation solves aggregate/many-flow bandwidth and redundancy" from "aggregation does not solve single-flow throughput," and proposes the architecturally correct alternative (faster links, not more aggregation) for the workload where that distinction actually matters.

## 12. Common Misconceptions

1. **"Link aggregation and Spanning Tree Protocol solve the same problem."** They solve related but distinct problems: STP manages redundancy across genuinely separate paths through different devices, keeping only one active at a time per path; link aggregation combines multiple parallel links between the same device pair into one logical link, using all of them simultaneously.
2. **"Bonding four links together gives any single transfer four times the bandwidth."** A single flow is hashed to exactly one member link; combined bandwidth benefits only appear across many concurrent flows spread across different members, not for any one flow.
3. **"LACP and EtherChannel are competing, incompatible technologies."** EtherChannel is Cisco's branded feature name for link aggregation, which can itself use the LACP standard protocol (or Cisco's proprietary PAgP, or static configuration) — LACP is a protocol option within EtherChannel, not a separate competing technology.
4. **"Static (manual) link aggregation is just as safe as LACP, only without the extra protocol overhead."** Static aggregation has no mechanism to detect a one-sided misconfiguration or mismatched link, which LACP's negotiation actively catches and safely excludes — the "extra overhead" buys real, meaningful safety.

## 13. 🔑 Key Takeaways

- Link aggregation bundles multiple physical links between the same two devices into one logical link with combined bandwidth and no idle standby ports, distinct from STP's separate-path, one-active-at-a-time redundancy model.
- LACP is the standard, vendor-neutral negotiation protocol for link aggregation; EtherChannel is Cisco's branded feature that can use LACP, proprietary PAgP, or static configuration.
- Traffic is distributed across an aggregate's member links by a per-flow hash — a single flow's throughput never exceeds one member link's bandwidth, only aggregate traffic across many flows benefits from combined capacity.
- LACP's active negotiation, which excludes mismatched or one-sided links automatically, is strongly preferred over static aggregation's unverified configuration in production.
- Choosing between LACP and STP for a given redundancy scenario is determined by topology (same device pair vs. genuinely separate paths through different devices), not personal preference — and the two frequently coexist in the same network.

## 14. Related Concepts & What's Next

[§40](Section-40-Part5-Spanning-Tree-Protocol-STP-Loop-Prevention-Concepts.md) is the direct point of contrast for this section, covering the alternative redundancy mechanism (STP) for genuinely separate paths rather than parallel links between the same device pair. [§38](Section-38-Part5-VLANs-Purpose-Tagging-802-1Q-and-Trunking.md) is relevant background since an aggregated link commonly also carries 802.1Q-tagged trunk traffic simultaneously, worth being precise about given the overloaded use of "trunk" across vendors. [§42](Section-42-Part5-Layer-2-vs-Layer-3-Switching.md) revisits redundancy considerations briefly when contrasting Layer 3 switching and ECMP routing against Layer 2 mechanisms like LACP and STP for large-scale data center designs. [§43](Section-43-Part5-Software-Defined-Networking-SDN-and-Overlay-Networks-Conceptual-Introduction.md) closes out this Part by connecting the physical-link redundancy concepts here to the broader shift toward software-defined and overlay networking, where much of this link-level complexity is abstracted away from the operator entirely.

**Next Section:** [§42](Section-42-Part5-Layer-2-vs-Layer-3-Switching.md) — `Section-42-Part5-Layer-2-vs-Layer-3-Switching.md`
