# Section 122 (Part 14): MTU Issues and Path MTU Discovery

## 1. Definition

**Plain language:** Small packets sail through almost any network without trouble, but large ones sometimes mysteriously vanish — a connection hangs after the handshake completes, or a file transfer stalls partway through while a small request/response exchange on the same connection works perfectly. This pattern, more often than any other single symptom, points to an MTU problem.

**Precise definition:** The **Maximum Transmission Unit (MTU)** is the largest frame or packet size, in bytes, that a given link or interface can carry without fragmentation. **Path MTU Discovery (PMTUD)** is the mechanism (defined for IPv4 in RFC 1191 and for IPv6 in RFC 8201) by which a sending host discovers the smallest MTU along the entire path to a destination — the **Path MTU** — by sending packets with the IP "Don't Fragment" (DF) bit set and relying on any router along the path whose outbound link is too small to respond with an ICMP "Fragmentation Needed" (Type 3, Code 4 for IPv4; Packet Too Big for IPv6) message, prompting the sender to reduce its packet size and retry. **MTU mismatch problems** arise almost entirely from a break in this feedback loop — most commonly when a firewall or security policy blocks the ICMP messages PMTUD depends on, causing large packets to be silently dropped with no error ever reaching the sender, a failure mode widely known as a **PMTUD black hole**.

> 💡 **Tip:** Whenever a symptom is specifically "small packets work, large packets don't" — SSH sessions that connect but hang on any command producing large output, TLS handshakes that complete (small packets) but application data transfer stalls (large packets) — treat MTU/PMTUD as the leading hypothesis immediately, since almost no other class of problem produces this exact size-dependent signature.

## 2. Why This Matters

- **MTU black holes are notoriously silent** — because the failure mode is a dropped ICMP message rather than a dropped data packet directly, the sending host often has no error to report at all; the connection simply appears to hang, which sends many engineers looking everywhere except at MTU.
- **It's one of the most common causes of "works over a normal link, breaks over a VPN/tunnel" reports**, because every tunneling protocol ([§92](../Part11/Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md)-[§98](../Part11/Section-98-Part11-MPLS-Concepts-and-Where-It-Fits-in-Enterprise-WANs.md)) adds encapsulation overhead that reduces the effective MTU available to the original payload, and that reduction is easy to overlook when the tunnel's own outer interface reports the normal, unreduced MTU.
- **It directly exploits a gap between two otherwise-correct-looking pieces of evidence** — the interface MTU (`ip link show`) looks normal, and the destination is reachable via ping (which uses small packets by default), so the problem is invisible to naive checks and requires specifically size-varying tests to surface.
- **It builds directly on the encapsulation and PDU concepts from Part 2** ([§10](../Part2/Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md)-[§11](../Part2/Section-11-Part2-PDUs-at-Each-Layer-Bits-Frames-Packets-Segments-Data.md)) and the TCP three-way handshake and options from [§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md), since understanding MTU requires understanding exactly where in a frame's structure the size constraint bites and how TCP's Maximum Segment Size (MSS) option is meant to negotiate around it.
- **It is one of the few network problems where the fix is often a single, well-understood configuration change** (clamping MSS, or ensuring ICMP is permitted) once correctly diagnosed — making accurate diagnosis, rather than the fix itself, the main challenge this section addresses.

## 3. Prerequisites and Dependencies

This section depends on the encapsulation and PDU model from [§10](../Part2/Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md)-[§11](../Part2/Section-11-Part2-PDUs-at-Each-Layer-Bits-Frames-Packets-Segments-Data.md) (understanding that each layer's header consumes space out of a fixed frame budget is essential to understanding why MTU constraints exist at all), the TCP handshake and options coverage from [§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md) (where MSS negotiation happens), and the IPv4/IPv6 addressing and header structure from [§16](../Part3/Section-16-Part3-Subnet-Masks-and-CIDR-Notation.md)-[§24](../Part3/Section-24-Part3-DHCP-Lease-Lifecycle-Relay-and-Options.md). It also depends on the connectivity-testing tools from [§116](Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md) (`ping`, `traceroute`) and the packet-capture skills from [§118](Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md), both of which are used directly in this section's hands-on diagnostics to observe fragmentation and ICMP behavior. Because tunnel and VPN encapsulation is one of the most common practical causes of reduced effective MTU, familiarity with the tunneling overhead discussed in [§92](../Part11/Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md) (IPsec), [§94](../Part11/Section-94-Part11-WireGuard-Design-Philosophy-and-Key-Concepts.md) (WireGuard), and [§97](../Part11/Section-97-Part11-GRE-and-Other-Tunneling-Protocols.md) (GRE) sharpens the diagnostic instinct for where MTU problems are most likely to originate. It follows [§121](Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md)'s routing and path-troubleshooting content in the escalation path from [§115](Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md), since a symmetric, correctly-routed path can still fail specifically due to a size-dependent constraint that routing-focused tools don't reveal.

## 4. Architecture / Conceptual Diagram

```text
   WHERE MTU LIVES IN THE FRAME

   |◄──────────────── Link MTU (e.g., 1500 bytes) ───────────────►|
   | Eth hdr | IP hdr | TCP hdr | ................ payload ...... |
             |◄── consumed by headers ──►|◄── space left for data ─►|

   Tunnel encapsulation eats further into the SAME budget:

   |◄──────────────── Link MTU (1500 bytes) ───────────────►|
   | Outer Eth | Outer IP | Tunnel hdr | Inner IP | Inner TCP | data |
                                        |◄── effective inner MTU is SMALLER ──►|


   PATH MTU DISCOVERY — WORKING CASE

   Sender (MTU 1500)     Router (outbound link MTU 1400)     Receiver
        │  packet, 1500B, DF=1                                    │
        ├───────────────────►│                                    │
        │   ICMP "Frag Needed, MTU=1400" ◄──┤ (link is too small)  │
        │◄───────────────────┤                                    │
        │  retries at 1400B, DF=1                                 │
        ├────────────────────┼───────────────────────────────────►│
                                                          delivered OK


   PATH MTU DISCOVERY — BLACK HOLE (ICMP BLOCKED)

   Sender (MTU 1500)     Router (outbound link MTU 1400)   [FW drops ICMP]   Receiver
        │  packet, 1500B, DF=1                                                   │
        ├───────────────────►│                                                   │
        │   ICMP "Frag Needed" generated, but blocked by a firewall ──✕          │
        │            (sender never learns; keeps retrying at 1500B; hangs)       │
```

- The link MTU is a single shared budget across every header at every layer of a given frame — adding an outer tunnel header doesn't change the link's physical/logical MTU, it simply leaves less room for the original inner payload, which is why tunnels reduce *effective* MTU without ever showing a reduced MTU on their own outer-facing interface.
- PMTUD's entire mechanism depends on ICMP messages successfully returning to the sender — any firewall, security group, or NACL ([§82](../Part10/Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md)-[§90](../Part10/Section-90-Part10-Network-Access-Control-Lists-and-Micro-Segmentation.md)) that blocks ICMP Type 3 (IPv4) or ICMPv6 Type 2 (Packet Too Big) breaks the feedback loop completely, producing a silent black hole rather than a visible error.
- TCP's MSS option, negotiated during the three-way handshake ([§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md)), is a *local* estimate based on each side's own outgoing interface MTU — it does not account for a smaller MTU somewhere in the middle of the path, which is exactly the gap PMTUD (or, more robustly, MSS clamping at a gateway) exists to close.

## 5. Hands-On

### 5.1 Confirming Interface MTU

**Purpose:** Establish the baseline MTU each host and any relevant tunnel interface believes it has, before testing what actually gets through end to end.

**Syntax:**

```bash
ip link show <interface>
```

**Example usage and expected output:**

```bash
$ ip link show eth0
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP mode DEFAULT group default qlen 1000

$ ip link show wg0
5: wg0: <POINTOPOINT,NOARP,UP,LOWER_UP> mtu 1420 qdisc noqueue state UNKNOWN group default qlen 1000
```

- `eth0` reports the standard Ethernet MTU of 1500; `wg0`, a WireGuard tunnel interface ([§94](../Part11/Section-94-Part11-WireGuard-Design-Philosophy-and-Key-Concepts.md)), reports 1420 — the 80-byte reduction reflects the tunnel's own encapsulation overhead, and this is exactly the kind of interface where MTU-related symptoms are most likely to appear.
- This check alone does not confirm the *path* MTU end to end — it only confirms what each local interface is configured to believe, which is why the size-varying `ping` test in 5.2 is the next essential step.

**Production usage example:** Comparing the physical interface MTU against every tunnel or overlay interface on a host (VPN, container overlay network, service mesh sidecar) is a standard first check whenever a symptom is reported as size-dependent, since a tunnel interface with an MTU that wasn't correctly reduced for its encapsulation overhead is one of the most common root causes.

**Common errors:** Assuming that because the *physical* interface shows the expected 1500-byte MTU, the effective path MTU for traffic actually traversing a tunnel on that host must also be 1500 — the physical interface's MTU is irrelevant to traffic that's being encapsulated and sent out through a tunnel interface with its own, smaller MTU.

### 5.2 Testing Path MTU with `ping -M do -s`

**Purpose:** Directly determine the largest packet size that can reach a destination without fragmentation, by sending packets with the Don't Fragment bit set at varying sizes.

**Syntax:**

```bash
ping -M do -s <payload-size> -c 3 <destination>
```

**Example usage and expected output:**

```bash
$ ping -M do -s 1472 -c 3 10.0.4.15
PING 10.0.4.15 (10.0.4.15) 1472(1500) bytes of data.
1480 bytes from 10.0.4.15: icmp_seq=1 ttl=61 time=1.2 ms
1480 bytes from 10.0.4.15: icmp_seq=2 ttl=61 time=1.1 ms
1480 bytes from 10.0.4.15: icmp_seq=3 ttl=61 time=1.3 ms

$ ping -M do -s 1473 -c 3 10.0.4.15
PING 10.0.4.15 (10.0.4.15) 1473(1501) bytes of data.
ping: local error: message too long, mtu=1500
```

- A payload of 1472 bytes (which, with the 8-byte ICMP header and 20-byte IP header, totals exactly 1500 bytes) succeeds — this confirms the standard Ethernet MTU is intact on this path for at least the local link.
- The `-M do` flag sets the Don't Fragment bit; without it, the kernel would silently fragment oversized packets locally and the test would never reveal a genuine path constraint.
- Bisecting the payload size (trying progressively smaller values) when a large size fails is the direct way to find the exact usable MTU on a path where something in the middle — not the local interface — is the limiting factor.

**Production usage example:** After a report of "large file transfers hang but small requests work" over a specific path (especially one crossing a VPN or cloud interconnect), running this size-bisection test end to end is the fastest way to get a concrete number (the actual usable path MTU) to compare against every interface and tunnel MTU along the path.

**Common errors:** Forgetting that the payload size and the total packet size differ by the ICMP+IP header overhead (28 bytes on IPv4) — a common off-by-28 mistake leads to testing the wrong boundary and concluding the MTU is different from what it actually is; always account for headers when interpreting a `ping -s` result against a target MTU.

### 5.3 Diagnosing PMTUD Black Holes with `tracepath` and ICMP Capture

**Purpose:** Determine whether a suspected MTU problem is a working PMTUD negotiation (visible, self-correcting) or a black hole (ICMP blocked, silent hang) — the distinction that determines the fix.

**Syntax:**

```bash
tracepath <destination>
sudo tcpdump -i <interface> icmp -n
```

**Example usage and expected output:**

```bash
$ tracepath 203.0.113.50
 1?: [LOCALHOST]                      pmtu 1500
 1:  gw-a-internal.local                                  0.412ms
 2:  vpn-gateway.local                                    1.203ms pmtu 1400
 3:  203.0.113.50                                          reached
     Resume: pmtu 1400 hops 3 back 3

$ sudo tcpdump -i eth0 icmp -n
14:40:02.113321 IP 10.0.4.1 > 10.0.1.15: ICMP 10.0.4.1 unreachable - need to frag (mtu 1400), length 36
```

- `tracepath` reports the discovered path MTU directly (`pmtu 1400`) and shows exactly which hop caused the reduction (`vpn-gateway.local`) — a working, non-black-holed PMTUD negotiation reports a clean final MTU like this.
- The `tcpdump` capture confirms the ICMP "Fragmentation Needed" (Type 3, Code 4) message is actually being generated and successfully arriving back at the sender — if this message is present in a capture but the application still hangs, suspect the application or OS isn't honoring PMTUD correctly; if it is *absent* despite an oversized packet clearly being sent, that confirms a black hole where the ICMP message is being generated but dropped somewhere on the return path (most often by a firewall between the router and the sender).
- The critical diagnostic branch: `tracepath` succeeding with a clean `pmtu` value means PMTUD is working end to end; `tracepath` hanging or timing out at a specific hop, combined with no corresponding ICMP message appearing in a capture at the sender, is the signature of a black hole.

**Production usage example:** This is the standard technique for confirming a suspected PMTUD black hole after a VPN or cloud-interconnect deployment, where a newly introduced tunnel hop reduces MTU and a security policy somewhere on the path (often unintentionally) blocks the ICMP messages needed to signal that reduction back to senders.

**Common errors:** Concluding "ICMP is fine" because ordinary `ping` (ICMP Echo Request/Reply) works, without checking specifically for ICMP Type 3 Code 4 (Fragmentation Needed) — many firewall policies permit basic Echo traffic for reachability checks while blocking other ICMP types wholesale, which is precisely the configuration that causes a PMTUD black hole while leaving `ping` itself looking completely healthy.

## 6. Production Usage Notes

- **MSS clamping** at a tunnel or VPN gateway — actively rewriting the TCP MSS option during the handshake to a value that accounts for the tunnel's encapsulation overhead — is the standard production mitigation for MTU problems on tunneled paths, because it works even when ICMP is blocked somewhere on the path, sidestepping the black-hole failure mode entirely rather than depending on PMTUD's fragile ICMP feedback loop.
- Cloud provider virtual networks commonly default to a 1500-byte MTU on standard instances but support jumbo frames (typically up to 9001 bytes) on internal, same-VPC traffic for supported instance types — mixing jumbo-frame-capable and non-jumbo-capable paths within the same logical network is a frequent, easy-to-overlook source of MTU mismatches introduced during infrastructure changes.
- Any newly introduced tunnel, overlay network, or service-mesh sidecar proxy should have its effective MTU explicitly verified with a size-bisection test (5.2) as part of rollout validation, rather than assumed correct because the underlying physical network's MTU was already known to be fine.

## 7. Security Considerations

- Blocking all ICMP at a network boundary is a common but counterproductive security practice specifically because it breaks PMTUD — the more precise and equally secure approach is to permit the specific ICMP types PMTUD depends on (Type 3 for IPv4, Type 2 for IPv6) while still blocking or rate-limiting other ICMP types that carry genuine risk (e.g., ICMP Redirect).
- MSS clamping performed at an untrusted or unauthorized point on a path (rather than at the intended gateway) could theoretically be used to degrade performance or, in principle, be leveraged as part of a fragmentation-based evasion technique against poorly configured intrusion-detection systems — MSS-clamping configuration should be reviewed and owned as deliberately as any other traffic-shaping security control, not left as an undocumented legacy setting.
- Deliberately crafted packet fragmentation has historically been used to evade signature-based network security inspection (fragments that individually don't match a signature but reassemble into malicious content) — modern IDS/IPS systems ([§86](../Part10/Section-86-Part10-Network-Segmentation-and-Zero-Trust-Networking-Principles.md)) that perform proper reassembly before inspection are the correct defense, and this history is part of why understanding fragmentation and MTU behavior matters even outside pure performance troubleshooting.

## 8. Common Troubleshooting Scenarios

| Symptom                                                          | Likely Cause                                                                 | Resolution Path                                                                                     |
| ----------------------------------------------------------------- | ------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| SSH session connects, but hangs on any command with large output  | PMTUD black hole — ICMP Fragmentation Needed blocked somewhere on the path    | Run `tracepath` and confirm with an ICMP capture ([§122](Section-122-Part14-MTU-Issues-and-Path-MTU-Discovery.md)); permit ICMP Type 3 Code 4, or enable MSS clamping |
| TLS handshake completes but bulk data transfer stalls              | Same black-hole pattern — small handshake packets succeed, large data packets are silently dropped | Same as above; also verify MSS clamping is active on any VPN/tunnel gateway in the path                |
| Problem appears only after adding a VPN or overlay network        | Tunnel encapsulation reduced effective MTU without a corresponding MSS clamp   | Verify tunnel interface MTU with `ip link show`; enable MSS clamping on the tunnel gateway              |
| `ping` works perfectly but application traffic fails intermittently | `ping`'s default small payload never exercises the MTU boundary that larger application packets hit | Re-test using `ping -M do -s` at sizes matching real application packet sizes, not default small pings  |

## 9. Best Practices

- Enable MSS clamping by default on every VPN, tunnel, and overlay gateway as a standard, documented configuration item, rather than relying on PMTUD alone — this removes an entire class of silent black-hole failures regardless of what ICMP policy exists elsewhere on the path.
- Permit the specific ICMP types PMTUD depends on at every firewall boundary, rather than blocking ICMP wholesale for a false sense of security — this keeps the standards-based fallback mechanism functional as a second line of defense even where clamping isn't configured.
- Explicitly validate effective end-to-end MTU with a size-bisection test as part of any change that introduces new encapsulation (a new VPN, a new overlay network, a new service mesh) rather than discovering the reduction only when a user reports a stalled transfer.

## 10. Common Anti-Patterns / Mistakes

- **Blocking all ICMP at the network edge "for security."** This is one of the most common, self-inflicted causes of PMTUD black holes — block or rate-limit specific risky ICMP types instead of eliminating the protocol entirely.
- **Testing MTU-related symptoms with default-sized `ping` packets.** A default `ping` (56-byte payload on Linux) never approaches the MTU boundary — always test with `-M do -s` at sizes near the suspected limit to actually exercise the constraint.
- **Assuming a tunnel or overlay interface automatically has a correctly reduced MTU.** MTU on a virtual interface is a configuration value, not a law of physics — it must be explicitly set to account for the actual encapsulation overhead, and a misconfigured value (left at the physical default) is a frequent, entirely preventable root cause.

## 11. Interview Questions

**🎯 Beginner:** _"What is MTU, and what does Path MTU Discovery do?"_
**Model answer:** MTU is the largest packet size a given network link can carry without fragmenting it. Path MTU Discovery is the process by which a sending host finds the smallest MTU along the whole path to a destination, by sending packets with the Don't Fragment bit set and reducing the size whenever a router along the way responds with an ICMP message saying the packet was too large for its outbound link.
_What the interviewer is probing for:_ Correct basic definitions and understanding of the discovery mechanism, not just the term.

**🎯 Intermediate:** _"A user reports that SSH connects fine but hangs whenever they run a command that produces a lot of output. What would you check first?"_
**Model answer:** This is a classic MTU/PMTUD symptom — small packets (the initial handshake and short commands) succeed while large packets (bulk output) don't, which strongly suggests either an MTU mismatch or a PMTUD black hole. I'd run a size-bisected `ping -M do -s` test to the destination to find the actual usable packet size, and run `tracepath` alongside a packet capture for ICMP traffic to check whether the "Fragmentation Needed" message is being generated and actually returning to the sender. If it's being blocked somewhere, that confirms a black hole, and the fix is either permitting that specific ICMP type through the blocking firewall or enabling MSS clamping on the relevant gateway.
_What the interviewer is probing for:_ Recognition of the size-dependent symptom pattern and a concrete, evidence-based diagnostic sequence.

**🎯 Senior:** _"Why does MSS clamping fix MTU problems that PMTUD alone doesn't reliably handle?"_
**Model answer:** PMTUD depends entirely on ICMP messages successfully returning from a router in the middle of the path back to the original sender — if any firewall or security policy anywhere on that return path blocks those ICMP messages, the sender never learns its packets are too large and keeps sending them, producing a silent black hole rather than a visible, self-correcting adjustment. MSS clamping sidesteps this dependency entirely by actively rewriting the TCP MSS option during the handshake itself, at a gateway that knows its own encapsulation overhead, so that both endpoints negotiate a segment size that already accounts for the smaller MTU — no ICMP round-trip is required at all. This makes clamping strictly more robust for tunnel and VPN gateways, where the reduced MTU is a known, static property of the gateway's own configuration rather than something that needs to be dynamically discovered.
_What the interviewer is probing for:_ Deep understanding of why PMTUD is fragile in practice and why a static, gateway-enforced alternative is preferred in production.

**🎯 Architect:** _"How would you prevent MTU-related incidents proactively across an organization operating many VPNs, cloud interconnects, and overlay networks?"_
**Model answer:** I'd establish MSS clamping as a mandatory, default configuration on every tunnel and overlay gateway type the organization operates, documented and enforced through infrastructure-as-code templates rather than left to individual engineers to remember. I'd pair that with an explicit ICMP policy standard — permitting Fragmentation Needed/Packet Too Big messages at every firewall boundary by default, rather than blocking ICMP wholesale — so PMTUD remains functional as a fallback wherever clamping isn't or can't be applied. I'd add automated, periodic path-MTU validation (a scheduled size-bisection test) across critical inter-site and inter-cloud paths, alerting if the discovered path MTU drops unexpectedly, so a newly introduced encapsulation layer or a misconfigured device is caught by monitoring rather than by a user-reported hang. Finally, I'd make MTU verification an explicit, documented step in the rollout checklist for any new VPN, interconnect, or overlay network, treating it with the same rigor as connectivity and security-group validation.
_What the interviewer is probing for:_ Systemic prevention through defaults, policy, and monitoring, rather than relying on any single engineer's diagnostic skill during an incident.

## 12. Common Misconceptions

1. **"If `ping` works, MTU is fine."** Default `ping` packets are small and rarely approach the MTU boundary — MTU problems specifically require testing with larger, size-varied packets to surface.
2. **"Blocking ICMP is always safer."** Blocking the specific ICMP types PMTUD depends on trades a marginal, theoretical security benefit for a very real, common, and hard-to-diagnose class of production outage.
3. **"A tunnel interface automatically accounts for its own overhead in its reported MTU."** This is a configuration choice, not automatic behavior — a misconfigured tunnel interface can report a full 1500-byte MTU while its actual usable payload capacity is smaller once encapsulation overhead is accounted for.
4. **"PMTUD failures always produce a clear error message."** The defining characteristic of a PMTUD black hole is precisely the *absence* of any error — the connection simply hangs, because the ICMP message that would have explained the problem never arrived.

## 13. 🔑 Key Takeaways

- MTU problems have a distinctive size-dependent signature — small packets succeed, large packets stall or vanish — and this pattern alone should immediately raise MTU/PMTUD as a leading hypothesis.
- PMTUD depends entirely on ICMP messages successfully returning to the sender; any firewall blocking those messages creates a silent "black hole" rather than a visible error.
- MSS clamping at tunnel and VPN gateways is the standard, more robust production mitigation, because it doesn't depend on the fragile ICMP round-trip that PMTUD requires.
- Diagnosing MTU issues requires size-varying tests (`ping -M do -s`, `tracepath`) and ICMP-focused packet capture — default connectivity tools like plain `ping` never exercise the actual constraint.

## 14. Related Concepts & What's Next

[§10](../Part2/Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md)-[§11](../Part2/Section-11-Part2-PDUs-at-Each-Layer-Bits-Frames-Packets-Segments-Data.md) and [§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md) supply the encapsulation and TCP-options foundation this section's MTU and MSS discussion depends on. [§116](Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md) and [§118](Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md) supply the connectivity-testing and packet-capture tooling used throughout this section's hands-on diagnostics. [§92](../Part11/Section-92-Part11-IPsec-AH-ESP-Tunnel-vs-Transport-Mode-IKE-Phases.md), [§94](../Part11/Section-94-Part11-WireGuard-Design-Philosophy-and-Key-Concepts.md), and [§97](../Part11/Section-97-Part11-GRE-and-Other-Tunneling-Protocols.md) cover the specific tunneling protocols whose encapsulation overhead is the most common practical cause of reduced effective MTU. [§121](Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md) covers the related but distinct class of path-level problem — where the path itself, not any single link's size limit, is the source of unexpected behavior. [§123](Section-123-Part14-Common-Failure-Scenarios-and-Root-Cause-Case-Studies.md) concludes Part 14 by walking through realistic, multi-symptom case studies that combine this section's MTU diagnostics with the routing, DNS, port-testing, and packet-capture techniques from every earlier section in this Part.

**Next Section:** [§123](Section-123-Part14-Common-Failure-Scenarios-and-Root-Cause-Case-Studies.md) — `Section-123-Part14-Common-Failure-Scenarios-and-Root-Cause-Case-Studies.md`
