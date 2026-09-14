# Section 23 (Part 3): Address Resolution: ARP and NDP

## 1. Definition

**Plain language:** When a device wants to send a packet to another device on the same local network, it knows the destination's IP address, but the actual delivery at Layer 2 requires knowing the destination's MAC address. ARP (for IPv4) and NDP (for IPv6) are the protocols that answer "what's the MAC address for this IP address on my local segment?" — turning a Layer 3 address into the Layer 2 address needed to actually put a frame on the wire.

**Precise definition:** **Address Resolution Protocol (ARP)**, defined in **RFC 826**, resolves an IPv4 address to a MAC address by **broadcasting** an ARP Request ("who has this IP?") to every device on the local segment and accepting the unicast ARP Reply from whichever device owns it, caching the result in a local **ARP table/cache** for a limited time. **Neighbor Discovery Protocol (NDP)**, defined in **RFC 4861**, is IPv6's structurally different replacement: it uses **ICMPv6 multicast messages** (Neighbor Solicitation and Neighbor Advertisement) instead of broadcast, and additionally subsumes several functions that IPv4 handled with separate protocols or manual configuration — router discovery (finding the default gateway, historically via manual config or a separate protocol), prefix discovery (learning the subnet's address range), and **SLAAC** (Stateless Address Autoconfiguration, letting a host construct its own global address without a DHCP server) are all part of NDP's scope, not bolted-on separately. Both protocols solve the same fundamental problem — Layer 3-to-Layer 2 mapping on a local segment — but NDP's multicast-based design directly reflects IPv6's removal of broadcast as a concept ([§21](Section-21-Part3-IPv6-Addressing-Structure-Notation-and-Address-Types.md)).

> 💡 **Tip:** ARP and NDP only ever operate within a single local segment (a broadcast/multicast domain) — they never cross a router. This is precisely why the ARP/neighbor cache only ever contains entries for directly-connected local devices, and why "the ARP entry for a remote server" is a category error: you resolve the MAC of your *default gateway* to reach anything off-segment, never the remote host's actual MAC.

## 2. Why This Matters

- **Address resolution is the mechanism underlying every single local-network packet delivery.** Without it, a device with a correct IP-layer route to a destination still has no way to actually address a Layer 2 frame to get the packet moving at all.
- **ARP/NDP cache poisoning is a real, actively-used attack technique** (ARP spoofing/poisoning for IPv4, NDP spoofing for IPv6) — understanding the trust model (any device can claim to own any IP, with no built-in authentication) is a direct prerequisite to understanding why this attack works and how to mitigate it.
- **Address resolution failures are a common, specific troubleshooting category** distinct from routing failures — "I can ping the gateway but not a host on my own subnet" often traces directly to an ARP/NDP resolution problem, not a routing problem.
- **NDP's expanded scope (subsuming router discovery, prefix discovery, and SLAAC) means understanding it well is a prerequisite for understanding IPv6 autoconfiguration** covered by reference in [§22](Section-22-Part3-IPv6-Subnetting-and-Dual-Stack-Coexistence.md) — NDP is not "just IPv6's ARP," it does considerably more.
- **These are foundational, exam- and interview-tested concepts** across essentially every networking certification and cloud infrastructure interview, precisely because they're small, precisely-defined, and easy to verify understanding of.

## 3. Prerequisites and Dependencies

Requires [§15](Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md) (IPv4 basics) and [§21](Section-21-Part3-IPv6-Addressing-Structure-Notation-and-Address-Types.md) (IPv6 address types, particularly link-local and multicast, which NDP depends on directly) as prerequisites. Builds conceptually on the OSI/TCP-IP layer model from Part 2 of this Networking topic, since address resolution is specifically the Layer 3-to-Layer 2 boundary function. Directly supports [§22](Section-22-Part3-IPv6-Subnetting-and-Dual-Stack-Coexistence.md)'s SLAAC reference and [§24](Section-24-Part3-DHCP-Lease-Lifecycle-Relay-and-Options.md)'s DHCP coverage, since SLAAC and DHCP/DHCPv6 are the two competing IPv6 address-assignment mechanisms and NDP underlies one of them.

## 4. Architecture / Conceptual Diagram

```text
                    ARP (IPv4) — BROADCAST-BASED RESOLUTION

  Host A (10.0.1.10) wants to reach Host B (10.0.1.20) — same subnet

  1. Host A checks its ARP cache: no entry for 10.0.1.20
  2. Host A broadcasts an ARP Request to ff:ff:ff:ff:ff:ff (all devices):
       "Who has 10.0.1.20? Tell 10.0.1.10 (aa:aa:aa:aa:aa:aa)"
  3. EVERY device on the segment receives and processes this broadcast
  4. Only Host B replies, via unicast:
       "10.0.1.20 is at bb:bb:bb:bb:bb:bb"
  5. Host A caches (10.0.1.20 → bb:bb:bb:bb:bb:bb) in its ARP table

              NDP (IPv6) — MULTICAST-BASED RESOLUTION

  Host A (2001:db8::10) wants to reach Host B (2001:db8::20) — same subnet

  1. Host A checks its neighbor cache: no entry for 2001:db8::20
  2. Host A computes the Solicited-Node Multicast address derived from
     the target's address (only devices whose address matches the last
     24 bits join this specific multicast group — far fewer than "everyone")
  3. Host A sends a Neighbor Solicitation to that multicast address
  4. Only Host B (and any other host coincidentally sharing that last-24-bit
     suffix, extremely rare) receives and processes it
  5. Host B replies via unicast Neighbor Advertisement:
       "2001:db8::20 is at bb:bb:bb:bb:bb:bb"
  6. Host A caches this in its neighbor cache

  NDP additionally handles (no direct ARP equivalent):
  - Router Solicitation/Advertisement  → discovering the default gateway
  - Prefix Information                  → learning the subnet's /64 prefix
  - Duplicate Address Detection (DAD)   → verifying no other host already
                                           has the address before using it
```

- **The core structural difference:** ARP's broadcast reaches literally every device on the segment for every resolution; NDP's Solicited-Node Multicast address is derived from the target address itself, so in practice only the target device (and a vanishingly small chance of coincidental overlap) processes the request — a genuine efficiency and scalability improvement, not just a rename.
- **Duplicate Address Detection (DAD)** has no IPv4/ARP equivalent at all — before a host starts using a new IPv6 address (assigned via SLAAC or otherwise), NDP requires it to first verify via multicast that no other host on the segment already claims that same address, preventing address collisions before they cause a conflict.
- **Router discovery is built into NDP** (Router Solicitation/Advertisement) — IPv4 has no equivalent protocol for a host to dynamically discover its default gateway; that information is either statically configured or learned via DHCP instead.

## 5. Hands-On

### 5.1 Inspecting and Manipulating the ARP Cache

**Purpose:** View, and if necessary manually clear, a host's ARP cache — a first-line diagnostic step for local-segment connectivity issues.

**Syntax:**

```bash
ip neigh show          # modern Linux
arp -a                  # traditional/cross-platform
```

**Example usage and expected output:**

```bash
$ ip neigh show
10.0.1.1 dev eth0 lladdr 02:42:ac:11:00:01 REACHABLE
10.0.1.20 dev eth0 lladdr bb:bb:bb:bb:bb:bb STALE

$ sudo ip neigh flush 10.0.1.20
```

**Production usage example:** During a network migration where a host's MAC address changes (hardware swap, VM migration) but its IP stays the same, other hosts' stale ARP cache entries pointing to the old MAC are a common cause of temporary unreachability until the cache naturally expires or is manually flushed — engineers proactively flush ARP caches on adjacent devices during planned cutover windows specifically to avoid this delay.

**Common errors:** Confusing an ARP entry's `STALE` state (still usable, just due for reconfirmation) with a hard failure — `STALE` is a normal part of the ARP cache lifecycle, not an error condition requiring intervention.

### 5.2 Inspecting the IPv6 Neighbor Cache

**Purpose:** View NDP's neighbor cache, the IPv6 equivalent of the ARP table, and confirm SLAAC-related router/prefix information was received.

**Syntax:**

```bash
ip -6 neigh show
```

**Example usage and expected output:**

```bash
$ ip -6 neigh show
fe80::1 dev eth0 lladdr 02:42:ac:11:00:01 router REACHABLE
2001:db8:1234:1::20 dev eth0 lladdr bb:bb:bb:bb:bb:bb STALE
```

**Production usage example:** The `router` flag on the `fe80::1` entry confirms this host correctly received a Router Advertisement identifying its default gateway via NDP — a useful first check when diagnosing "IPv6 host can't reach anything off-link" issues, distinguishing an NDP/router-discovery problem from a routing table problem further downstream.

**Common errors:** Expecting to see off-link (non-local-segment) IPv6 addresses in the neighbor cache — like ARP, NDP's neighbor cache only ever contains directly-connected local devices; anything beyond the local segment is resolved via the default gateway's own MAC, not the remote host's.

### 5.3 Capturing ARP and NDP Traffic to Diagnose a Resolution Failure

**Purpose:** Directly observe whether ARP requests/NDP solicitations are being sent and answered, to isolate a resolution failure from a routing or firewall failure.

**Syntax:**

```bash
tcpdump -i <interface> arp
tcpdump -i <interface> icmp6 and 'ip6[40] == 135 or ip6[40] == 136'
```

**Example usage and expected output:**

```bash
$ sudo tcpdump -i eth0 arp
14:22:01.001122 ARP, Request who-has 10.0.1.20 tell 10.0.1.10, length 28
                                    # no reply follows — resolution failure

$ sudo tcpdump -i eth0 icmp6 and 'ip6[40] == 135 or ip6[40] == 136'
14:22:05.221331 IP6 2001:db8::10 > ff02::1:ff00:20: ICMP6, neighbor solicitation, who has 2001:db8::20
14:22:05.221890 IP6 2001:db8::20 > 2001:db8::10: ICMP6, neighbor advertisement, tgt is 2001:db8::20
```

**Production usage example:** When a host reports "can't reach a specific local neighbor" while general connectivity otherwise works, a targeted `tcpdump` capture like this directly answers "is a resolution request even going out, and if so, is anything answering it" — narrowing the fault to either the requesting host, the target host, or something filtering the traffic in between (a misconfigured switch port security policy, for instance).

**Common errors:** Filtering for ICMPv6 broadly without narrowing to the specific Neighbor Solicitation (type 135) and Neighbor Advertisement (type 136) message types produces a noisy capture full of unrelated ICMPv6 traffic (Router Advertisements, Echo Requests, etc.) that obscures the actual resolution exchange being diagnosed.

## 6. Production Usage Notes

- ARP cache entries have a limited, OS-configurable timeout (commonly minutes) — this timeout, combined with **gratuitous ARP** (a host proactively announcing its own IP-to-MAC mapping unsolicited, typically after a failover event), is the mechanism many high-availability setups (VRRP/keepalived-style virtual IP failover) rely on to update other devices' ARP caches quickly after an active/standby switchover, rather than waiting for natural cache expiry.
- Switches implementing **Dynamic ARP Inspection (DAI)** or equivalent NDP-snooping protections validate ARP/NDP traffic against a trusted binding table (often built from DHCP snooping records) and drop spoofed resolution traffic — a standard hardening measure on production switch infrastructure, not just a theoretical mitigation.
- NDP's Router Advertisement mechanism means IPv6 hosts can dynamically re-learn their default gateway and subnet prefix if network topology changes, without requiring DHCP-style lease renewal — a meaningful operational difference from IPv4's typically more static or DHCP-dependent gateway configuration.

## 7. Security Considerations

- **ARP spoofing/poisoning** exploits the complete lack of authentication in ARP's design — any device can send an ARP Reply claiming to own any IP address, and receiving hosts accept it unconditionally, enabling man-in-the-middle attacks by redirecting traffic intended for a legitimate host/gateway to the attacker's MAC address instead. **Dynamic ARP Inspection** (validating ARP against a trusted DHCP-snooping-derived binding table) is the standard production mitigation.
- **NDP spoofing** is the structurally identical attack applied to IPv6's Neighbor Advertisement messages — the same lack of built-in authentication exists, and the same class of man-in-the-middle risk applies; **RA Guard** and NDP-snooping-equivalent switch features provide analogous protection to DAI, but require deliberate configuration since they're less universally deployed than the more mature IPv4 ARP protections.
- Because both protocols are strictly local-segment (never crossing a router), the attack surface is bounded to devices sharing the same broadcast/multicast domain — proper network segmentation (smaller VLANs/subnets) directly reduces ARP/NDP spoofing blast radius as a secondary benefit beyond its primary addressing purpose.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                     | Likely Cause                                                                                       | Resolution Path                                                                                                     |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- |
| A host can ping its default gateway but not another host on the same local subnet | ARP (or NDP) resolution for that specific host is failing, or a switch-level ARP/NDP filtering policy is blocking it | Check the requesting host's ARP/neighbor cache and capture traffic (§5.1, §5.3) to see if a request goes out and is answered |
| After a server hardware replacement (same IP, new MAC), other hosts still route traffic to the old, decommissioned hardware | Stale ARP cache entries on adjacent hosts pointing to the retired MAC address haven't yet expired      | Send gratuitous ARP from the new hardware, or manually flush ARP caches on affected adjacent devices during the cutover window |
| Intermittent connectivity or unexplained traffic redirection on a local segment | Possible ARP or NDP spoofing/poisoning attack redirecting traffic via a forged resolution reply       | Enable/verify Dynamic ARP Inspection (or RA Guard for IPv6) on switch infrastructure; inspect for duplicate/conflicting ARP replies for the same IP |

## 9. Best Practices

- Enable Dynamic ARP Inspection (and its IPv6/NDP-equivalent protections, such as RA Guard) on production switch infrastructure as a standard hardening baseline, not an optional extra — the underlying protocols have no built-in authentication and are trivially spoofable otherwise.
- Use gratuitous ARP deliberately in any active/standby failover design (virtual IP-based high availability) to minimize the window during which other hosts' stale ARP caches point to the now-inactive node.
- When diagnosing "can't reach a local host" issues, check ARP/NDP resolution status explicitly and early — it's a fast, cheap check that immediately distinguishes a Layer 2 resolution problem from a routing, firewall, or application-layer problem further up the stack.

## 10. Common Anti-Patterns / Mistakes

- **Treating ARP/NDP resolution as reliably authenticated or trustworthy by default**, without enabling switch-level protections (DAI, RA Guard) that specifically compensate for the protocols' inherent lack of authentication.
- **Assuming an ARP or neighbor cache entry for a remote (off-segment) host should exist and troubleshooting as if it's missing/broken** — ARP and NDP never resolve anything beyond the local segment; this is a conceptual error, not a configuration bug to chase.
- **Skipping the ARP/neighbor cache check early in local-connectivity troubleshooting** and jumping straight to routing table or firewall investigation, when the actual fault is a simple, quickly-diagnosable resolution failure.

## 11. Interview Questions

**🎯 Beginner:** _"What problem does ARP solve, and what does NDP do differently to solve the same problem in IPv6?"_
**Model answer:** ARP resolves a known IPv4 address to the MAC address needed to actually deliver a frame at Layer 2, by broadcasting a request to every device on the local segment and accepting whichever device's reply matches. NDP solves the identical problem for IPv6, but uses multicast instead of broadcast — since IPv6 removed broadcast as a concept entirely — and targets a Solicited-Node Multicast address derived from the destination address itself, so in practice only the actual target device processes the request, rather than every device on the segment.
_What the interviewer is probing for:_ Correct understanding of the shared purpose and the specific broadcast-vs-multicast mechanism difference, not just "NDP is IPv6's ARP" as an unexplained label.

**🎯 Intermediate:** _"Explain how ARP spoofing works and why it's possible in the first place."_
**Model answer:** ARP has no built-in authentication — any device on a local segment can send an ARP Reply claiming ownership of any IP address, and receiving hosts cache and trust that claim unconditionally, with no way to verify it's actually coming from the legitimate owner of that IP. An attacker exploits this by sending forged ARP replies claiming to own, say, the default gateway's IP address; victim hosts then send their gateway-bound traffic to the attacker's MAC address instead, enabling a man-in-the-middle position. It's possible specifically because ARP was designed in an era (1982, RFC 826) with no adversarial threat model in mind — the protocol simply trusts whoever answers first or most recently.
_What the interviewer is probing for:_ Whether the candidate understands the actual mechanism (lack of authentication, unconditional trust of replies) rather than just naming the attack.

**🎯 Senior:** _"A host can reach its default gateway and external internet destinations, but cannot reach another host on its own local subnet — even though both hosts' IP configuration looks correct. Walk through your diagnosis, considering ARP/NDP specifically."_
**Model answer:** Reachability to the gateway and beyond confirms the host's own IP configuration, default route, and general Layer 3 connectivity are fine — that rules out most routing-layer explanations for the local failure, since traffic to the gateway succeeds using the exact same interface and Layer 2 path a local-subnet packet would also use. This pattern points specifically at an ARP (or NDP, for IPv6) resolution failure isolated to that one destination: I'd check the requesting host's ARP/neighbor cache for an entry for the target IP, and if absent or incomplete, capture traffic to see whether an ARP Request/Neighbor Solicitation for that specific IP is actually going out and, if so, whether anything replies. Possible root causes at that point: the target host is actually down or has a firewall dropping ARP/NDP traffic specifically (rare, but possible with host-based firewall misconfiguration); a switch-level ARP/NDP inspection or port-security policy is blocking that specific host's resolution traffic; or a duplicate/conflicting IP address on the segment is causing inconsistent replies. I would not suspect the default gateway or general routing configuration further, since the working gateway/internet path already rules those out as the shared cause.
_What the interviewer is probing for:_ Ability to use the differential symptom (gateway/internet works, one specific local host doesn't) to correctly localize the fault to Layer 2 address resolution rather than re-checking Layer 3 configuration that's already proven functional.

**🎯 Architect:** _"You're designing network security policy for a large, flat corporate LAN where ARP spoofing has previously caused a real security incident. What structural and control-plane changes do you recommend, beyond just 'enable DAI'?"_
**Model answer:** Enabling Dynamic ARP Inspection (backed by DHCP snooping to build the trusted binding table it validates against) is necessary but not sufficient on its own — I'd pair it with genuine network segmentation, breaking the large flat LAN into smaller VLANs/subnets scoped by function or trust level, since ARP/NDP spoofing's blast radius is structurally bounded to whatever broadcast/multicast domain the attacker sits in; a smaller segment directly limits how much traffic any single compromised or malicious device can intercept even if a spoofing attempt succeeds somewhere. I'd also extend equivalent protections to IPv6 explicitly (RA Guard and NDP-snooping-equivalent features) rather than treating ARP hardening as sufficient, since the same class of vulnerability exists for NDP and IPv6 may already be active on the network by default even without conscious adoption (as covered in [§22](Section-22-Part3-IPv6-Subnetting-and-Dual-Stack-Coexistence.md)). Beyond switch-level controls, I'd recommend 802.1X port-based authentication for devices connecting to sensitive segments, since it addresses a related but distinct risk (an unauthorized device joining the segment at all) that DAI alone doesn't solve — DAI protects the resolution protocol's integrity once a device is already on the segment, but doesn't prevent an unauthorized device from being there in the first place. Finally, I'd add monitoring specifically for ARP/NDP anomalies (a MAC address suddenly claiming an IP previously associated with a different MAC, for instance) as a detective control layered on top of the preventive ones, since no single control here is likely to be perfectly comprehensive against a determined attacker.
_What the interviewer is probing for:_ Whether the candidate can design defense-in-depth around this specific vulnerability class — combining segmentation, protocol-level protections for both IPv4 and IPv6, access control, and monitoring — rather than proposing a single silver-bullet fix.

## 12. Common Misconceptions

1. **"NDP is just IPv6's version of ARP, functionally identical."** NDP subsumes considerably more than address resolution alone — router discovery, prefix discovery, Duplicate Address Detection, and SLAAC support are all part of NDP's scope, with no direct IPv4/ARP equivalent for most of them.
2. **"ARP/NDP entries exist for remote, off-segment hosts too."** Both protocols resolve addresses strictly within the local broadcast/multicast domain — reaching an off-segment host always resolves the default gateway's MAC, never the remote host's own MAC.
3. **"ARP spoofing is a purely theoretical/academic attack."** It's a well-established, actively used real-world attack technique for local man-in-the-middle positioning, which is precisely why Dynamic ARP Inspection and DHCP snooping are standard hardening features on production enterprise switches, not niche options.
4. **"IPv6's NDP is inherently more secure than ARP because it's newer."** NDP has the same fundamental lack of built-in authentication as ARP and is subject to an analogous spoofing attack (NDP spoofing) — its protections (RA Guard, etc.) are also less universally deployed in practice than the more mature ARP protections, arguably making it a weaker point in some real environments today, not a stronger one.

## 13. 🔑 Key Takeaways

- ARP (IPv4) and NDP (IPv6) both resolve a Layer 3 address to a Layer 2 MAC address, strictly within the local segment — neither ever operates across a router.
- ARP uses broadcast to every device on the segment; NDP uses multicast targeted at an address derived from the destination itself, a genuine efficiency improvement reflecting IPv6's removal of broadcast entirely.
- NDP's scope extends well beyond address resolution alone, subsuming router discovery, prefix discovery, Duplicate Address Detection, and SLAAC support — it is not merely "ARP renamed for IPv6."
- Neither protocol has built-in authentication, making both ARP spoofing and NDP spoofing genuine, actively-exploited local man-in-the-middle attack techniques; Dynamic ARP Inspection and RA Guard are the standard production mitigations.
- A working path to the default gateway/internet but a failing path to a specific local host is a strong diagnostic signature pointing specifically at an ARP/NDP resolution failure for that host, not a routing problem.

## 14. Related Concepts & What's Next

[§21](Section-21-Part3-IPv6-Addressing-Structure-Notation-and-Address-Types.md) and [§22](Section-22-Part3-IPv6-Subnetting-and-Dual-Stack-Coexistence.md) supplied the IPv6 addressing and SLAAC context that NDP directly supports. [§24](Section-24-Part3-DHCP-Lease-Lifecycle-Relay-and-Options.md) covers DHCP, the other major address-assignment mechanism (alongside SLAAC, which NDP enables) and closes out this Part's addressing coverage. Switch-level hardening features referenced here (Dynamic ARP Inspection, DHCP snooping, RA Guard) connect forward to this Networking roadmap's later switching and security Parts.

**Next Section:** [§24](Section-24-Part3-DHCP-Lease-Lifecycle-Relay-and-Options.md) — `Section-24-Part3-DHCP-Lease-Lifecycle-Relay-and-Options.md`
