# Section 11 (Part 2): PDUs at Each Layer: Bits, Frames, Packets, Segments, Data

## 1. Definition

**Plain language:** At every layer of the network stack, the blob of data being handled has a specific name — this matters because "packet" doesn't just mean "any chunk of network data," it specifically means the unit of data at the Internet/Network layer with an IP header on it. Using the right term for the right layer is how engineers communicate precisely about exactly where in the stack something is happening.

**Precise definition:** A **Protocol Data Unit (PDU)** is the generic term for "the unit of data that a given layer operates on," and each layer of the OSI/TCP-IP stack has its own specific PDU name: at the **Physical layer**, the PDU is a **bit** (or a raw electrical/optical/radio signal representing bits); at the **Data Link layer**, it's a **frame**; at the **Network/Internet layer**, it's a **packet** (for IP specifically, sometimes called a **datagram**, particularly for connectionless protocols); at the **Transport layer**, it's a **segment** for TCP or a **datagram** for UDP; and at the **Session/Presentation/Application layers**, it's generically just called **data** (or **message**), since those upper layers don't add a distinct, universally-named wrapper the way the lower layers do. This naming convention exists specifically so that engineers can refer unambiguously to which layer's unit of data they mean — "the packet was dropped" implies an Internet-layer/routing problem, while "the frame was dropped" implies a Data-Link/switching problem, and those are different failure domains requiring different diagnostic tools.

> 💡 **Tip:** "Datagram" is the one term that appears at two different layers and trips people up: an IP packet is sometimes called an "IP datagram" (Internet layer), and a UDP payload is called a "UDP datagram" (Transport layer) — these are two completely different PDUs at two different layers that happen to share a name because both protocols are **connectionless** ("datagram" historically implies "sent independently, with no guaranteed delivery or ordering," which is true of both IP and UDP but not of TCP).

## 2. Why This Matters

- **Precise incident communication.** "We're seeing frame loss" versus "we're seeing packet loss" versus "we're seeing segment retransmissions" each point a troubleshooting effort toward a completely different layer and toolset — imprecise terminology sends investigations to the wrong team or the wrong tool.
- **Tool output uses these terms directly.** `ip -s link` reports frame-level counters; `netstat -s` and TCP-focused tools report segment-level retransmission counts; `tcpdump` calls what it captures "packets" generically but the actual structure inside is layer-specific — knowing the vocabulary is required to correctly interpret tool output.
- **MTU is defined in terms of a specific PDU.** The Maximum Transmission Unit is, precisely, the largest **frame** payload a Data Link technology supports — but engineers often reason about it in terms of packet or segment size, and the distinction (which PDU's size limit is actually being discussed) matters for correct MTU/fragmentation calculations ([§10](Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md), [§122](../Part14/Section-122-Part14-MTU-Issues-and-Path-MTU-Discovery.md)).
- **Distinguishes connection-oriented from connectionless PDU handling.** A "segment" (TCP) implies ordered, acknowledged, retransmitted delivery; a "datagram" (UDP) implies none of that — recognizing which PDU term is in play immediately tells you what delivery guarantees (or lack thereof) apply.
- **Exam and interview relevance.** Precisely naming and defining each PDU is extremely common as an opening networking interview or certification question, since it's a fast proxy for whether a candidate has internalized the layered model at all, or only memorized the layer names.

## 3. Prerequisites and Dependencies

Builds directly on [§8](Section-08-Part2-The-OSI-7-Layer-Model-Purpose-and-Layer-by-Layer-Breakdown.md) (the OSI layers each PDU belongs to) and [§10](Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md) (encapsulation, which is the process that actually produces each of these PDUs by wrapping the one above it). [§54](../Part7/Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)–[§58](../Part7/Section-58-Part7-UDP-Structure-Use-Cases-and-Trade-Offs-vs-TCP.md) (Part 7) later cover TCP segments and UDP datagrams' internal header structure in full depth; this section only needs the reader to know that TCP and UDP exist as two Transport-layer protocols (briefly introduced conceptually here, detailed later). [§35](../Part5/Section-35-Part5-What-Switching-Is-Hubs-vs-Switches-vs-Bridges.md)–[§36](../Part5/Section-36-Part5-MAC-Addresses-and-the-MAC-Address-Table-CAM-Table.md) (Part 5) cover frames and MAC addressing at the Data Link layer in much greater depth than needed here.

## 4. Architecture / Conceptual Diagram

```text
   LAYER                    PDU NAME              WHERE THE NAME COMES FROM

   Application/                                    Generic — no single, universally
   Presentation/    ──►      "Data" / "Message"     used PDU name across these three
   Session                                          collapsed OSI layers

   Transport        ──►      Segment (TCP)          TCP: an ordered "segment" of a
                              Datagram (UDP)          reliable byte stream
                                                      UDP: a self-contained, unordered
                                                      "datagram" (connectionless)

   Network/         ──►      Packet                  The Internet layer's core unit;
   Internet                  (a.k.a. IP datagram)     "datagram" here again signals
                                                       connectionless, best-effort delivery

   Data Link        ──►      Frame                   Bounded by a start/end delimiter
                                                       and a Frame Check Sequence (FCS)
                                                       for error detection

   Physical         ──►      Bit(s) / signal          The literal electrical, optical,
                                                       or radio-wave representation

   ── Encapsulation direction (§10) ──►
   Data → Segment/Datagram → Packet → Frame → Bits
   (each arrow = one layer's header gets added, and the PDU gets a new name)
```

- The PDU name changes **precisely at the point a new header is added** — this is not an arbitrary labeling convention; a "packet" literally means "a segment/datagram with an IP header now wrapped around it."
- "Datagram" appearing at both the Transport (UDP) and Internet (IP) layers is a historical naming collision, not a sign that UDP and IP are the same layer — context (is the discussion about ports, which is Transport-layer, or about routing/addressing, which is Internet-layer) always disambiguates which "datagram" is meant.
- The upper three OSI layers (Session, Presentation, Application) don't have a single standardized PDU name the way the lower four do, precisely because TCP/IP collapses them into one Application layer ([§9](Section-09-Part2-The-TCP-IP-4-Layer-Model-and-How-It-Maps-to-OSI.md)) with no single universally-agreed wrapper format at that level — "message" or just "data" is used loosely and contextually.

## 5. Hands-On

### 5.1 Observing Frame-Level Counters With `ip -s link`

**Purpose:** Show that "frame" is not just an abstract term — the Linux kernel tracks Data-Link-layer statistics using exactly this vocabulary, distinct from packet-level statistics.

**Syntax:**

```bash
ip -s link show <interface>
```

**Example usage and expected output:**

```bash
$ ip -s link show eth0
2: eth0: <BROADCAST,MULTICAST,UP,LOWER_UP> mtu 1500 qdisc fq_codel state UP mode DEFAULT group default qlen 1000
    link/ether 02:42:ac:11:00:02 brd ff:ff:ff:ff:ff:ff
    RX: bytes  packets  errors  dropped missed  mcast
    8842103    61204    0       0       0       12
    TX: bytes  packets  errors  dropped carrier collsns
    5120983    48211    0       0       0       0
```

- Note that even the kernel's own tooling loosely uses "packets" here for what are, strictly, frame-level counters at this interface (RX/TX at the Ethernet device level) — in casual and even official tooling usage, "packet" is often used generically for "PDU of some kind," and only careful technical writing distinguishes frame from packet precisely. `errors` and `dropped` at this level reflect Data-Link-layer problems (bad frames, buffer drops) independent of anything happening at the IP layer above.

**Production usage example:** Rising `RX errors` or `dropped` counters at the interface level (Data Link layer) while application-level metrics look otherwise healthy is a strong signal to investigate physical media, NIC driver issues, or switch port problems — because this counter increments before IP-layer processing even happens, ruling out routing or application causes entirely.

**Common errors:** Conflating interface-level `dropped` (a Data-Link/driver-level drop, before the packet ever reaches the IP stack) with IP-layer or firewall-level drops (visible instead via `netstat -s` or `iptables` counters) leads to investigating the wrong subsystem — these are genuinely different PDUs being dropped at genuinely different layers.

### 5.2 Distinguishing Segment Retransmissions From Packet Loss With `ss` and `netstat -s`

**Purpose:** Show that TCP segment-level retransmission statistics (Transport layer) are tracked and reported separately from Internet-layer packet loss, using standard Linux tools, reinforcing that these are genuinely distinct PDUs with distinct failure modes.

**Syntax:**

```bash
ss -ti
netstat -s | grep -i retrans
```

**Example usage and expected output:**

```bash
$ ss -ti
ESTAB 0 0  10.0.1.15:47832 93.184.216.34:443
     cubic wscale:7,7 rto:212 rtt:11.2/2.1 mss:1448 pmtu:1500 rcvmss:536 advmss:1448
     cwnd:10 bytes_sent:14829 bytes_retrans:1448 bytes_acked:13381 segs_out:24 segs_in:19
     retrans:1/3 send 10.3Mbps

$ netstat -s | grep -i retrans
    3 segments retransmitted
    3 fast retransmits
```

- `segs_out`/`segs_in` and `retrans:1/3` in the `ss -ti` output are explicitly reported in terms of TCP **segments** — this is Transport-layer-specific vocabulary describing reliability behavior (retransmission) that has no equivalent concept at the Internet or Data-Link layer, where a dropped packet or frame is simply gone with no built-in retry.

**Production usage example:** A rising segment retransmission rate on a connection (visible via `ss -ti` or aggregate `netstat -s` counters) while frame-level interface counters (5.1) stay clean points specifically to a Transport-layer or above-it problem (congestion somewhere on the path, an overloaded receiver, or a lossy link further upstream that TCP is compensating for) rather than a local Data-Link-layer fault — because TCP retransmission is precisely the mechanism that hides packet loss from the application, at the cost of visible segment-level retransmission counters.

**Common errors:** Seeing TCP retransmissions and concluding the local network interface is faulty is a common misdiagnosis — retransmissions are frequently caused by loss occurring elsewhere entirely along the path (an intermediate router, congestion at the receiver), which the local interface's clean frame-level counters (5.1) would already have ruled out as the cause.

## 6. Production Usage Notes

- Monitoring and observability tooling generally exposes metrics named after the specific PDU they're counting — "packet loss" (Internet layer, often measured via ICMP/`ping`, [§116](../Part14/Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md)), "retransmission rate" (Transport-layer/TCP-specific), "frame errors" (Data-Link/interface-level) — and conflating these terms when writing alerts or dashboards leads to genuinely different, sometimes contradictory-seeming signals being lumped together under one vague "network health" metric.
- Load balancers and proxies that operate "at Layer 4" are described that way specifically because they make routing decisions based on Transport-layer PDU information (TCP/UDP ports) without needing to de-encapsulate further into the Application-layer "data" above — this PDU-precise language is exactly what distinguishes an L4 load balancer's actual capability from an L7 load balancer's ([§73](../Part9/Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md)).
- "Jumbo frames" (a Data-Link-layer configuration raising the standard Ethernet MTU, typically from 1500 to 9000 bytes) is named precisely because it's a **frame**-level size configuration — it doesn't change anything about packet or segment structure directly, only the boundary constraint those PDUs must fit within.

## 7. Security Considerations

- Fragmentation attacks and certain classes of intrusion-detection-system evasion techniques work specifically by manipulating **packet**-level (Internet-layer) fragmentation in ways that reassemble differently than an inspecting device expects — understanding that fragmentation is a packet-level (not frame-level or segment-level) concept is necessary to understand why these specific evasion techniques exist and what layer of tooling has to correctly handle reassembly to defend against them.
- SYN flood attacks specifically abuse the TCP **segment**-level handshake ([§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md)) — sending a flood of SYN segments without completing the handshake — which is a Transport-layer-specific attack vector distinct from a volumetric packet flood at the Internet layer (a distinction that matters for choosing the correct mitigation: SYN cookies, a Transport-layer defense, versus rate-limiting/blackholing, an Internet-layer defense).
- Deep packet inspection tooling, despite the name, generally needs to reconstruct all the way up to the Application-layer "data" PDU to be useful against modern threats — genuinely inspecting only at the packet (Internet-layer) level misses payload-based attacks entirely, since IP headers carry no application content.

## 8. Common Troubleshooting Scenarios

| Symptom                                                        | Likely Cause                                                                                     | Resolution Path                                                                                                    |
| ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| Interface shows rising RX errors/drops, application unaffected      | Data-Link-layer (frame-level) problem — bad cable, NIC/driver issue, duplex mismatch                | Investigate physical layer and driver logs (`ip -s link`, `dmesg`) before looking at IP or application layers      |
| `ping` shows packet loss but TCP connections still complete slowly  | Internet-layer packet loss being compensated for by Transport-layer (TCP segment) retransmission    | Check `ss -ti` retransmission counters to confirm TCP is masking loss that `ping`'s ICMP packets are also revealing |
| Application reports "connection reset" with no clear cause          | A RST at the Transport (segment) layer — could be the OS, a firewall, or the remote application terminating the segment stream | Correlate timing with `ss -ti` state and packet captures ([§118](../Part14/Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md)) to identify who sent the RST and why               |
| Team uses "packet loss" to describe an issue that's actually frame-level | Imprecise PDU terminology obscuring which layer is actually at fault                              | Reframe the investigation using the correct PDU name for the layer showing symptoms, to route it to the right diagnostic tool |

## 9. Best Practices

- Use PDU-precise language deliberately in incident reports and monitoring dashboards ("frame errors on eth0," not just "network errors") so that the terminology itself routes the investigation to the correct layer and team.
- When reading tool output, note explicitly which PDU-level statistic you're looking at (frame-level interface counters vs. segment-level TCP retransmission counters vs. Internet-layer ICMP loss) before drawing conclusions about where a fault lies.
- Remember that "datagram" means two different things depending on context (IP datagram vs. UDP datagram) and always clarify which layer is meant when the term comes up in discussion or documentation.

## 10. Common Anti-Patterns / Mistakes

- **Using "packet" as a catch-all term for any unit of network data, regardless of layer.** This is extremely common informally (even some tool names, like `tcpdump`, use "packet" loosely) but loses the precision that makes layer-specific troubleshooting fast — a "dropped packet" and a "dropped frame" point to different failure domains.
- **Assuming TCP retransmission (a segment-level behavior) is visible or meaningful at the packet or frame layer.** Retransmission is a Transport-layer reliability mechanism; the Internet and Data-Link layers have no concept of "retry" at all — a lost packet or frame is simply gone, and it's entirely TCP's job, at the segment level, to notice and resend.
- **Treating "datagram" (IP) and "datagram" (UDP) as the same PDU because they share a name.** They're two distinct PDUs at two distinct layers that happen to share a descriptive term because both protocols share the connectionless, best-effort delivery philosophy the word "datagram" originally described.

## 11. Interview Questions

**🎯 Beginner:** _"Name the PDU at each of the following layers: Physical, Data Link, Network, Transport."_
**Model answer:** Physical layer: bit (the raw signal). Data Link layer: frame. Network layer: packet (also called an IP datagram). Transport layer: segment for TCP, or datagram for UDP.
_What the interviewer is probing for:_ Direct recall of the layer-to-PDU mapping — a very common opening question to confirm basic model fluency.

**🎯 Intermediate:** _"Why is UDP's PDU called a 'datagram' while TCP's is called a 'segment'? What does that naming difference actually signal?"_
**Model answer:** The naming reflects a real behavioral difference. "Datagram" (used for both UDP and, at a different layer, IP) implies each unit is sent independently and self-contained, with no guaranteed ordering, delivery, or relationship to other datagrams sent by the same source — UDP is connectionless and doesn't track state between datagrams. "Segment" implies a *piece of a larger, ordered stream* — TCP treats the data it sends as one continuous byte stream, breaking it into segments that are individually sequenced, acknowledged, and retransmitted if lost, with the receiver reassembling them back into the original ordered stream. The different terms aren't arbitrary; they directly reflect TCP's connection-oriented, ordered delivery model versus UDP's connectionless, unordered, best-effort model.
_What the interviewer is probing for:_ Whether the candidate understands the terminology as meaningfully descriptive of actual protocol behavior, not just memorized labels.

**🎯 Senior:** _"A colleague says 'we're seeing packet loss' based on elevated TCP retransmission counts in an APM dashboard. Is that accurate terminology, and does it matter?"_
**Model answer:** It's imprecise, and the imprecision can misdirect the investigation. TCP retransmission counts are a Transport-layer (segment-level) statistic — they reflect that some previously-sent segment wasn't acknowledged in time and had to be resent, which is TCP's own visible symptom of loss happening somewhere below it. That underlying loss is very likely occurring at the Internet layer (an actual dropped packet somewhere on the path) or even the Data Link layer (a frame dropped at a congested switch or a lossy Wi-Fi hop) — but the retransmission counter itself is measured at the Transport layer, once removed from wherever the actual loss occurred. Saying "packet loss" isn't wrong as a root-cause hypothesis, but conflating the Transport-layer symptom (retransmission) with a specific claim about where in the stack the loss physically occurred can send an investigation toward the wrong layer — for instance, blaming the local NIC (Data Link) when the actual loss is happening at a congested router several hops away (Internet layer, an entirely different failure domain).
_What the interviewer is probing for:_ Precision about the relationship between an observable Transport-layer symptom and its actual, potentially lower-layer, root cause — a genuinely nuanced distinction that shows real diagnostic depth.

**🎯 Architect:** _"You're designing a network observability platform. How would you structure metric naming and layer tagging to avoid the PDU-terminology confusion discussed above at organizational scale?"_
**Model answer:** I'd enforce PDU-precise metric naming as a platform convention rather than leaving it to individual teams' judgment — metrics explicitly tagged with the layer and PDU they measure (`datalink.frame.errors`, `network.packet.loss_pct`, `transport.tcp.retransmit_rate`, `application.http.5xx_rate`) rather than a generic, ambiguous `network.errors` bucket that different teams populate with data from different layers. I'd also build the dashboard hierarchy to mirror the stack itself — a top-level "network health" view that decomposes into layer-specific panels in stack order, so an on-call engineer's eye is naturally drawn to check Data Link and Internet-layer health before Transport, and Transport before Application, mirroring the systematic bottom-up troubleshooting methodology ([§13](Section-13-Part2-Layer-by-Layer-Troubleshooting-Mental-Model.md)). This directly prevents the organizational anti-pattern where "packet loss" becomes an umbrella term covering symptoms from three different layers, which historically causes exactly the kind of misrouted, wasted investigation time described in the previous question.
_What the interviewer is probing for:_ The ability to turn a conceptual/terminology precision issue into a concrete platform/tooling design decision at organizational scale, not just personal diagnostic discipline.

## 12. Common Misconceptions

1. **"Packet is a generic term for any chunk of network data."** Precisely, "packet" refers specifically to the Internet-layer PDU (an IP datagram); frames, segments, and bits are distinct PDUs at other layers, even though "packet" is very commonly used loosely as a catch-all in casual speech and even some tool names.
2. **"IP datagram and UDP datagram are the same thing because they're both called 'datagram.'** They're PDUs at two entirely different layers (Internet vs. Transport) that share the term because both protocols are connectionless — an IP datagram (packet) typically has a UDP datagram (or TCP segment) nested inside it as its payload.
3. **"Retransmission happens at the packet or frame level."** Retransmission is specifically a Transport-layer (TCP segment) behavior — neither IP (Internet layer/packets) nor Ethernet (Data Link layer/frames) has any built-in concept of detecting loss and automatically resending; that reliability is entirely TCP's responsibility, layered on top.
4. **"MTU refers to packet size."** MTU is technically defined as the maximum **frame** payload a Data-Link technology supports — in practice this constrains the maximum packet size that can travel unfragmented over that link, but the formal limit is a frame-level (Data Link) property, not a packet-level (Internet layer) one.

## 13. 🔑 Key Takeaways

- Each layer's unit of data has a specific name: bit (Physical), frame (Data Link), packet/IP datagram (Network/Internet), segment (TCP) or datagram (UDP) (Transport), and generically "data" or "message" for the collapsed upper layers.
- "Datagram" appears at two different layers (IP and UDP) because both protocols share a connectionless, best-effort delivery philosophy — context always disambiguates which is meant.
- Retransmission is a Transport-layer/segment-specific reliability mechanism with no equivalent at the packet or frame level — a dropped packet or frame simply vanishes; only TCP notices and resends.
- Using PDU-precise language when describing a network symptom directly routes the investigation to the correct layer and correct diagnostic tool, while generic terms like "packet loss" used loosely can misdirect troubleshooting.
- MTU is formally a frame-level (Data Link) size limit that, in practice, constrains how large the packet and segment nested inside that frame can be.

## 14. Related Concepts & What's Next

[§10](Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md) covered the encapsulation process that literally produces each PDU named in this section, layer by layer. [§8](Section-08-Part2-The-OSI-7-Layer-Model-Purpose-and-Layer-by-Layer-Breakdown.md) and [§9](Section-09-Part2-The-TCP-IP-4-Layer-Model-and-How-It-Maps-to-OSI.md) established the OSI and TCP/IP layers each PDU belongs to. [§12](Section-12-Part2-Protocol-Data-Flow-A-Packets-Journey-From-Application-to-Wire.md) traces a full real-world request through multiple complete encapsulation/de-encapsulation cycles, using this section's exact PDU vocabulary throughout. [§54](../Part7/Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)–[§58](../Part7/Section-58-Part7-UDP-Structure-Use-Cases-and-Trade-Offs-vs-TCP.md) (Part 7) return to TCP segments and UDP datagrams specifically, covering header structure and reliability mechanisms (sequence numbers, acknowledgments, retransmission) in full depth. [§118](../Part14/Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md) (Part 14) picks the packet-capture vocabulary from this section back up for hands-on `tcpdump` troubleshooting practice.

**Next Section:** [§12](Section-12-Part2-Protocol-Data-Flow-A-Packets-Journey-From-Application-to-Wire.md) — `Section-12-Part2-Protocol-Data-Flow-A-Packets-Journey-From-Application-to-Wire.md`
