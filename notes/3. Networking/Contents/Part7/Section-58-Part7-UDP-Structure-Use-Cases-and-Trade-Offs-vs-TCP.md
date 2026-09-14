# Section 58 (Part 7): UDP: Structure, Use Cases, and Trade-Offs vs. TCP

## 1. Definition

**Plain language:** UDP is TCP with almost everything stripped away — no handshake, no sequence numbers used for reordering, no acknowledgments, no retransmission, no flow control, no congestion control. What's left is a minimal header just big enough to get a chunk of data from one application's port to another's, sent and forgotten. That minimalism is a deliberate feature, not a missing one: it makes UDP cheap, fast, and predictable in exactly the ways TCP's overhead is not.

**Precise definition:** **UDP (User Datagram Protocol)**, defined in RFC 768, is a **connectionless**, **unreliable**, **unordered** transport-layer protocol. Its header is a fixed 8 bytes containing only source port, destination port, length, and an optional checksum — none of the connection state, sequence/acknowledgment numbers, or window fields that make up the bulk of a TCP header. Each **UDP datagram** is transmitted independently; the protocol provides no mechanism to detect loss, no mechanism to reorder datagrams that arrive out of sequence, and no mechanism to slow down a sender that's overwhelming a receiver or the network path. Any of those guarantees, if an application needs them, must be built at the application layer — which is exactly what protocols like DNS (simple retry-on-timeout), and more elaborately, QUIC ([§62](Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md), a full reliability and congestion-control layer built entirely in user-space on top of UDP) do.

> 💡 **Tip:** The right mental model for UDP is not "TCP but broken" — it's "a bare, minimal-cost primitive for sending a message, with delivery guarantees left as an exercise for whoever needs them." Applications choose UDP precisely because they either don't need those guarantees (a stale video frame is useless anyway, so retransmitting it is pointless) or need a different, custom guarantee that TCP's fixed reliability model can't provide as efficiently (QUIC's per-stream, rather than per-connection, ordering).

## 2. Why This Matters

- **A huge and growing share of critical infrastructure traffic is UDP-based** — DNS ([§44](../Part6/Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md)–[§53](../Part6/Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md)), DHCP ([§24](../Part3/Section-24-Part3-DHCP-Lease-Lifecycle-Relay-and-Options.md)), NTP, and increasingly QUIC/HTTP-3 ([§62](Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md), [§64](../Part8/Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)) all run over UDP; misunderstanding UDP's behavior means misunderstanding how a large fraction of real network traffic actually works.
- **UDP's lack of guarantees is the direct cause of a specific, recognizable class of application bugs and design decisions** — from custom retry logic in DNS resolvers to jitter buffers in VoIP applications — recognizing "this is UDP's fault, and it's supposed to work this way" versus "this is a bug" is a core diagnostic skill.
- **UDP's minimal header and lack of connection state make it dramatically cheaper per-packet**, which matters directly for high-volume, latency-sensitive workloads (real-time telemetry, gaming, streaming) where TCP's overhead would be a genuine performance liability, not just an inconvenience.
- **UDP's spoofability and lack of built-in flow control make it a favored vector for amplification DDoS attacks** ([§88](../Part10/Section-88-Part10-DDoS-Attack-Types-and-Mitigation-Strategies.md)) — understanding UDP's structure explains exactly why open UDP-based services (DNS resolvers, NTP servers) are common attack amplification points.
- **UDP is the substrate the industry is actively rebuilding critical transport behavior on top of** (QUIC, [§62](Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)) — understanding UDP's raw properties is a prerequisite for understanding why QUIC exists and what problem it's actually solving.

## 3. Prerequisites and Dependencies

This section depends on [§54](Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)'s foundational connection-oriented vs. connectionless distinction, and is best understood in direct contrast to the TCP mechanics built up across [§55](Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md) (handshake), [§56](Section-56-Part7-TCP-Reliability-Sequence-Numbers-ACKs-Retransmission.md) (reliability), and [§57](Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md) (flow/congestion control) — nearly every property described here is defined by what UDP deliberately omits from that TCP machinery. It also assumes the encapsulation and PDU concepts from [§10](../Part2/Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md) and [§11](../Part2/Section-11-Part2-PDUs-at-Each-Layer-Bits-Frames-Packets-Segments-Data.md) (a UDP datagram is the Layer 4 PDU, wrapped inside an IP packet exactly as a TCP segment is). [§59](Section-59-Part7-Ports-and-Sockets-Well-Known-Registered-and-Ephemeral-Ranges.md) (ports and sockets) applies equally to UDP and TCP and is referenced here for port-related behavior. [§62](Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md) (QUIC) is the direct forward continuation of this section's discussion of reliability being rebuilt on top of raw UDP.

## 4. Architecture / Conceptual Diagram

```text
   UDP HEADER (8 bytes total — vastly smaller than TCP's minimum 20 bytes)

    0                   1                   2                   3
    0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |          Source Port         |       Destination Port       |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |            Length            |           Checksum           |
   +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
   |                                                               |
   |                       Application Data                       |
   |                                                               |

   NO sequence number. NO acknowledgment number. NO window field.
   NO flags (SYN/ACK/FIN/RST). NO connection state anywhere.


   TCP vs. UDP: WHAT EACH ACTUALLY GUARANTEES

   ┌────────────────────────┬───────────────────┬───────────────────┐
   │ Property                │ TCP                │ UDP                │
   ├────────────────────────┼───────────────────┼───────────────────┤
   │ Connection setup        │ 3-way handshake    │ None               │
   │ Delivery guarantee      │ Yes (retransmit)   │ No                 │
   │ Ordering guarantee      │ Yes                │ No                 │
   │ Flow control             │ Yes (rwnd)         │ No                 │
   │ Congestion control       │ Yes (cwnd)         │ No                 │
   │ Header size (min)        │ 20 bytes           │ 8 bytes            │
   │ Per-packet overhead      │ Higher             │ Minimal            │
   │ Latency to first byte    │ 1+ RTT (handshake) │ 0 RTT              │
   │ Head-of-line blocking    │ Yes (per-connection)│ N/A (independent) │
   └────────────────────────┴───────────────────┴───────────────────┘

   A LOST DATAGRAM, UNDER EACH MODEL

   TCP: seq=1000 lost ──► receiver buffers everything after it,
        cannot deliver ANY of it to the application until seq=1000
        is retransmitted and arrives (head-of-line blocking).

   UDP: datagram lost ──► gone. The next datagram (independent,
        no sequence relationship) is delivered to the application
        immediately, with no memory that anything was ever lost.
```

- UDP's **checksum field is optional** in IPv4 (though effectively always used in practice) and covers the UDP header plus payload plus a pseudo-header derived from the IP addresses — this catches corruption but has nothing to do with reliability (there is no retransmission triggered by a failed checksum; the datagram is simply discarded).
- The **absence of head-of-line blocking** is one of UDP's most important structural advantages for real-time or multi-stream applications: because datagrams are independent, losing one has zero effect on the delivery of the next, unlike TCP where a single lost segment blocks delivery of everything queued behind it until it's retransmitted.
- **Length** in the UDP header is redundant with information IP itself carries (total datagram length) but is retained for historical and integrity-checking reasons, and matters when UDP is carried over IPv6 with jumbograms.

## 5. Hands-On

### 5.1 Sending and Capturing Raw UDP Traffic

**Purpose:** Directly observe a UDP exchange's header fields and confirm the complete absence of handshake or acknowledgment traffic.

**Syntax:**

```bash
nc -u -l <port>              # UDP listener
nc -u <host> <port>          # UDP sender
sudo tcpdump -i <interface> -n udp -X
```

**Example usage and expected output:**

```bash
$ sudo tcpdump -i lo -n udp port 5001 -X
14:40:11.221 IP 127.0.0.1.51900 > 127.0.0.1.5001: UDP, length 14
        0x0000:  4500 002a 0000 4000 4011 3ccf 7f00 0001  E..*..@.@.<.....
        0x0010:  7f00 0001 cabc 1389 0016 fe21 6865 6c6c  ...........hell
        0x0020:  6f20 6f76 6572 2075 6470                 o over udp
```

- Note there is exactly **one** packet for this send — no SYN, no SYN-ACK, no ACK, and (unless the application chooses to reply) no response packet at all. Compare this directly to the multi-packet handshake capture from [§55](Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md)'s hands-on section.
- `0x0016` in the hex dump is the UDP length field (22 bytes: 8-byte header + 14-byte payload), and `fe21` is the checksum.

**Production usage example:** This exact single-packet-per-send behavior is why UDP-based protocols (DNS, syslog, metrics/telemetry emitters like StatsD) can achieve very high throughput per CPU cycle compared to TCP-based equivalents — there's no per-message connection-state bookkeeping at all, which matters at the scale of millions of small metric emissions per second.

**Common errors:** Expecting `nc -u` to report an error if the listener isn't running — since UDP has no handshake, the sender has no way to know whether anything is listening on the other end; the send call succeeds locally regardless of whether any process ever receives it.

### 5.2 Observing UDP's Lack of Delivery Confirmation Under Loss

**Purpose:** Show concretely that UDP provides no signal at all when a datagram is lost, in contrast to TCP's visible retransmission behavior from [§56](Section-56-Part7-TCP-Reliability-Sequence-Numbers-ACKs-Retransmission.md).

**Syntax:**

```bash
sudo tc qdisc add dev <interface> root netem loss <percentage>%
```

**Example usage and expected output:**

```bash
$ sudo tc qdisc add dev lo root netem loss 30%
$ for i in $(seq 1 10); do echo "msg $i" | nc -u -w1 127.0.0.1 5001; done
# Sender sees no errors, no indication of which messages were dropped.

# On the listener side:
$ nc -u -l 5001
msg 1
msg 2
msg 4
msg 5
msg 8
msg 10
# msg 3, 6, 7, 9 are simply gone — no gap indicator, no notification.

$ sudo tc qdisc del dev lo root netem
```

**Production usage example:** This exact blind spot is why production systems relying on UDP for anything beyond best-effort telemetry build explicit application-level sequence numbers and gap detection into their own message format (many custom binary protocols, and DNS's simple query-ID-and-timeout retry model) — without that, there is no way to even detect that loss occurred, let alone recover from it.

**Common errors:** Building a UDP-based system and assuming "it mostly works in testing" is sufficient validation — UDP loss characteristics vary enormously with network conditions, and a system with no loss-detection logic at all can silently drop a meaningful fraction of messages in production without any visible error, alert, or log entry anywhere.

### 5.3 Identifying UDP Services and Their Ports

**Purpose:** Enumerate which UDP services are active on a host, since UDP services don't show a `LISTEN` state the way TCP does.

**Syntax:**

```bash
ss -uln
```

**Example usage and expected output:**

```bash
$ ss -uln
State   Recv-Q  Send-Q  Local Address:Port   Peer Address:Port
UNCONN  0       0       0.0.0.0:68            0.0.0.0:*
UNCONN  0       0       127.0.0.53:53         0.0.0.0:*
UNCONN  0       0       0.0.0.0:123           0.0.0.0:*
```

- Every bound UDP socket shows state `UNCONN` — there is no `LISTEN`, `ESTABLISHED`, or any of the TCP states covered in [§61](Section-61-Part7-Connection-States-and-the-TCP-State-Machine-LISTEN-ESTABLISHED-TIME-WAIT.md), because UDP maintains no per-peer connection state at all; a single bound socket can receive from any source at any time.
- Port 68 (DHCP client), 53 (DNS), and 123 (NTP) are all classic UDP-first services — cross-reference [§60](Section-60-Part7-Common-Port-Reference-22-80-443-53-3306-5432-6379-etc.md) for the full common-port table.

**Production usage example:** Security and compliance audits routinely enumerate UDP listeners separately from TCP listeners specifically because UDP services are frequently overlooked in firewall rule reviews that assume "check the listening ports" means checking TCP only — an exposed UDP service (an open DNS resolver, an unauthenticated NTP or SNMP endpoint) is a classic, recurring finding.

**Common errors:** Running only `ss -tln` (TCP-only) during a security review and missing UDP-exposed services entirely — always pair `-t` and `-u` flags, or use `-tuln` together, to get a complete picture of a host's exposed surface.

## 6. Production Usage Notes

- **DNS** ([§44](../Part6/Section-44-Part6-DNS-Fundamentals-Namespace-Hierarchy-and-Purpose.md)–[§53](../Part6/Section-53-Part6-Common-DNS-Troubleshooting-Tools-dig-nslookup-host.md)) is the most universally encountered UDP-based protocol — the vast majority of DNS queries use UDP for its low latency (no handshake required for a lookup that's often faster than a handshake alone would take), falling back to TCP only for oversized responses or zone transfers ([§48](../Part6/Section-48-Part6-Zone-Files-and-Zone-Transfers-AXFR-IXFR.md)).
- **Real-time media** (VoIP, video conferencing) almost universally uses UDP (often via RTP) specifically because retransmitting a lost audio/video frame after the fact is worse than simply skipping it — by the time a retransmission would arrive, the moment has passed and the receiving application has already moved on; applications instead implement jitter buffers and graceful degradation rather than TCP-style retransmission.
- **Telemetry and metrics emission** (StatsD-style UDP metrics, syslog over UDP) deliberately accept occasional loss in exchange for extremely low per-emission cost — losing an occasional metric sample is an acceptable trade-off against the CPU and connection-state cost of a TCP connection per emission at high volume.

## 7. Security Considerations

- **UDP-based amplification/reflection DDoS attacks** ([§88](../Part10/Section-88-Part10-DDoS-Attack-Types-and-Mitigation-Strategies.md)) are UDP's most consequential security liability: an attacker sends a small, spoofed-source-IP request to an open UDP service (DNS, NTP, memcached, and others have all been abused this way) that responds with a much larger reply, sent to the spoofed victim address — this works specifically because UDP never verifies the source address is reachable or genuine the way TCP's handshake implicitly does.
- **No built-in authentication or integrity** exists at the UDP layer itself — the checksum only catches accidental corruption, not deliberate tampering or spoofing; any UDP-based protocol needing those guarantees must add them itself (DNSSEC for DNS integrity, DTLS for encrypted/authenticated UDP transport).
- **Firewalls and NAT devices must track UDP "pseudo-connections" heuristically** (typically via a short idle timeout keyed on the 5-tuple) since there's no explicit open/close signal the way TCP's SYN/FIN provides — this is why some UDP-based applications (VoIP, certain VPN protocols) need explicit keep-alive traffic to prevent NAT mappings from expiring mid-session.

## 8. Common Troubleshooting Scenarios

| Symptom                                                          | Likely Cause                                                                   | Resolution Path                                                                                                     |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Intermittent, silent message loss in a custom UDP application         | Expected UDP behavior — no built-in delivery guarantee                          | Add application-level sequence numbers and gap/loss detection, or migrate to a reliable transport (TCP, or QUIC [§62](Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)) |
| UDP service appears "down" to a security scanner but works fine       | Scanner used a TCP-style probe against a UDP-only service, or the service silently drops unrecognized packets | Use a protocol-aware UDP probe (e.g., an actual DNS query against a DNS server) rather than a generic port scan       |
| VoIP/video call has choppy audio despite good raw bandwidth            | Jitter or loss on the UDP path; no retransmission masks the underlying network issue | Check for loss/jitter with `mtr` ([§116](../Part14/Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md)); tune jitter buffer settings; verify QoS/prioritization for real-time UDP traffic |
| Open UDP service is implicated in an outbound DDoS reflection incident | Service (DNS resolver, NTP, etc.) is open to the internet and abusable for amplification | Restrict access to trusted sources only; disable unnecessary open recursive/monlist-style UDP services ([§88](../Part10/Section-88-Part10-DDoS-Attack-Types-and-Mitigation-Strategies.md))         |

## 9. Best Practices

- Choose UDP deliberately, only when the application either tolerates loss gracefully (real-time media) or is prepared to implement its own reliability/ordering layer (or adopt an existing one like QUIC) — never choose UDP purely for "it's supposedly faster" without accounting for what has to be rebuilt on top of it.
- Always include `-u` alongside `-t` when auditing listening services (`ss -tuln`) — UDP services are commonly missed in security reviews that default to TCP-only tooling and mental models.
- Restrict any UDP-based service that could be abused for amplification (open DNS resolvers, NTP, SNMP) to authenticated or trusted-source-only access, given UDP's inherent susceptibility to source-spoofing-based reflection attacks.

## 10. Common Anti-Patterns / Mistakes

- **Building a custom UDP-based protocol and only discovering its loss-handling gaps in production.** UDP's silent, undetectable loss under normal operation means inadequate testing (especially testing only on low-loss local networks) routinely fails to surface bugs that manifest immediately on real, lossier paths.
- **Assuming a UDP service is unreachable just because a TCP-style connectivity test fails against it.** UDP has no handshake to test with a generic TCP connect — the correct test is a protocol-aware probe (an actual DNS query, an actual NTP request) or a raw UDP send/response check.
- **Leaving UDP-based administrative or diagnostic services (SNMP, NTP `monlist`, open resolvers) exposed to the public internet "because nobody uses them."** These are precisely the services most frequently abused for reflection/amplification attacks, and their obscurity is not a meaningful security control.

## 11. Interview Questions

**🎯 Beginner:** _"What guarantees does UDP provide, and what does it not provide, compared to TCP?"_
**Model answer:** UDP provides only basic port-to-port delivery with an optional checksum for corruption detection. It does not provide connection setup, delivery guarantees, ordering guarantees, flow control, or congestion control — any of those, if needed, must be implemented by the application itself. TCP provides all of those guarantees natively, at the cost of a handshake and per-connection overhead that UDP avoids entirely.
_What the interviewer is probing for:_ A clean, accurate list of what's missing, not a vague "UDP is unreliable and TCP is reliable."

**🎯 Intermediate:** _"Why do real-time voice and video applications typically prefer UDP over TCP, even though TCP is 'more reliable'?"_
**Model answer:** TCP's reliability comes from retransmission and in-order delivery, both of which introduce delay — a lost segment blocks delivery of everything after it (head-of-line blocking) until it's retransmitted and arrives. For real-time audio/video, a delayed frame is often worse than a dropped one, because by the time a retransmission would arrive, the playback moment has already passed; the receiving application would rather skip the lost frame and keep playing in real time than stall waiting for it. UDP's independent, unordered delivery means losing one frame has no effect on delivering the next one immediately, which better matches the actual requirement of real-time media.
_What the interviewer is probing for:_ Understanding of head-of-line blocking as the specific mechanical reason TCP is a poor fit for real-time media, not just a general "UDP is faster" answer.

**🎯 Senior:** _"You're reviewing a security audit finding that a company's public DNS resolvers are 'open' and could be used in an amplification attack. Explain the attack mechanism and how you'd remediate it."_
**Model answer:** An open DNS resolver will answer queries from any source IP. An attacker sends a small DNS query with a spoofed source address set to the intended victim's IP, requesting a response type known to produce a large reply (like an ANY or DNSSEC-related record). Because UDP never verifies that the source address is reachable or legitimate — there's no handshake to fail — the resolver sends its (much larger) response directly to the spoofed victim address, achieving significant amplification of the attacker's original small request. Remediation is to restrict the resolver to only answer queries from authorized/internal source IPs (closing it to open recursive resolution from the public internet), rate-limit responses, and where public authoritative resolution is genuinely required, apply response-rate limiting (RRL) specifically to blunt the amplification factor even for legitimate-looking traffic patterns.
_What the interviewer is probing for:_ Precise understanding of why UDP's spoofability specifically enables this attack class, plus concrete, practical remediation steps rather than a vague "add a firewall."

**🎯 Architect:** _"Your team is designing a new telemetry ingestion pipeline expected to handle millions of small events per second from edge devices worldwide. Walk through your transport-layer decision and its trade-offs."_
**Model answer:** Given the volume and the tolerance for occasional sample loss inherent to most telemetry use cases (a missing data point among millions is rarely individually significant), UDP is the strong default over TCP — avoiding per-connection state and handshake overhead at this scale meaningfully reduces both device-side and ingestion-side resource cost. I'd design the event format with a lightweight application-level sequence number per device/stream specifically so the ingestion side can at least measure loss rate as an observability signal, even without recovering the lost events themselves — silent, unmeasured loss is the real risk, not loss itself. For any subset of events that are individually critical (e.g., a billing-relevant threshold crossing, not routine telemetry), I'd route those through a separate, explicitly reliable path — either a TCP-based channel or a store-and-forward mechanism with acknowledgment — rather than trying to force UDP to carry a guarantee it isn't designed to provide, or over-engineering full reliability onto every event when only a small subset actually needs it.
_What the interviewer is probing for:_ Ability to make and justify a transport choice at scale, and specifically to split traffic by actual reliability requirement rather than applying one transport strategy uniformly regardless of per-event importance.

## 12. Common Misconceptions

1. **"UDP is just a worse, older version of TCP."** They serve different, deliberately distinct purposes — UDP's minimalism is a feature for latency- and overhead-sensitive workloads, not an unfinished or inferior design.
2. **"UDP means no reliability is possible, period."** Reliability can absolutely be built on top of UDP at the application layer — DNS's simple retry model and QUIC's full reliability/ordering/congestion-control stack ([§62](Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)) are both proof this works, just as a deliberate, custom-fit design rather than TCP's one-size-fits-all guarantee.
3. **"A UDP port that doesn't respond to a probe is definitely closed or filtered."** UDP services frequently don't respond at all to malformed or unexpected probes even when open and healthy — accurate UDP service detection requires a protocol-aware request, not a generic connectivity check.
4. **"UDP's checksum makes it 'reliable enough' for most purposes."** The checksum only detects accidental corruption of a single datagram already in hand — it does nothing to detect or recover from a datagram that never arrived at all, which is UDP's actual primary reliability gap.

## 13. 🔑 Key Takeaways

- UDP's 8-byte header carries only source port, destination port, length, and checksum — no connection state, sequencing, or windowing exists anywhere in the protocol.
- UDP provides no delivery guarantee, no ordering guarantee, no flow control, and no congestion control — any of these must be built at the application layer if needed.
- The absence of per-connection state and head-of-line blocking makes UDP structurally cheaper and better suited to high-volume, latency-sensitive, or loss-tolerant workloads than TCP.
- UDP's lack of source-address verification is the root cause of amplification/reflection DDoS attacks against open UDP services.
- Modern protocols like QUIC ([§62](Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)) deliberately rebuild TCP-like reliability and ordering on top of raw UDP rather than using TCP directly, specifically to avoid TCP's fixed, connection-wide head-of-line blocking.

## 14. Related Concepts & What's Next

[§59](Section-59-Part7-Ports-and-Sockets-Well-Known-Registered-and-Ephemeral-Ranges.md) explains the port numbers referenced throughout this section's hands-on examples in full — their ranges, allocation, and role in the 5-tuple that identifies a socket, applying identically to both TCP and UDP. [§60](Section-60-Part7-Common-Port-Reference-22-80-443-53-3306-5432-6379-etc.md) provides the complete common-port reference table, including the specific UDP-first services (DNS, DHCP, NTP) named in this section's production notes. [§62](Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md) picks up directly from this section's closing point, detailing exactly how QUIC builds reliability, ordering, and congestion control on top of UDP without inheriting TCP's connection-wide head-of-line blocking. [§88](../Part10/Section-88-Part10-DDoS-Attack-Types-and-Mitigation-Strategies.md) (Part 10) expands the amplification/reflection DDoS mechanism introduced in this section's security discussion into a full survey of DDoS attack types and mitigations.

**Next Section:** [§59](Section-59-Part7-Ports-and-Sockets-Well-Known-Registered-and-Ephemeral-Ranges.md) — `Section-59-Part7-Ports-and-Sockets-Well-Known-Registered-and-Ephemeral-Ranges.md`
