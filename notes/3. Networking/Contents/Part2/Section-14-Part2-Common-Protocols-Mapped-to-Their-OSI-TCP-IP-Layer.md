# Section 14 (Part 2): Common Protocols Mapped to Their OSI/TCP-IP Layer

## 1. Definition

**Plain language:** This section is a reference: a single place that lists the protocols you'll actually encounter as an infrastructure engineer — HTTP, DNS, TCP, IP, Ethernet, TLS, SSH, and dozens more — and states plainly which OSI layer and which TCP/IP layer each one belongs to, so that when a later section of this roadmap (or a real production incident) mentions "an OSI Layer 7 protocol" or "a Transport-layer protocol," you have an immediate, concrete answer for what that means.

**Precise definition:** This section provides a **protocol-to-layer reference mapping** covering the protocols most relevant to infrastructure, cloud, and DevOps engineering — organized by which OSI layer (1–7) and which TCP/IP layer (Network Access, Internet, Transport, Application) each protocol operates at. Some protocols map unambiguously to a single layer (IP is unambiguously Internet-layer/OSI Layer 3); others are commonly discussed at a layer that's an approximation or a matter of convention rather than a strict technical fact (TLS is often called "Layer 6-ish" despite functionally wrapping around and interacting with Transport and Application layer concerns); this section notes those ambiguities explicitly rather than forcing an artificially clean answer where the real-world classification is genuinely debated.

> 💡 **Tip:** Don't try to memorize this table by rote. Instead, for each protocol you use in a given week, pause and ask "what layer does this operate at, and what does that tell me about what it can and can't do?" — that habit builds durable, applied recall far better than memorizing a static list, and it's exactly the skill [§13](Section-13-Part2-Layer-by-Layer-Troubleshooting-Mental-Model.md)'s troubleshooting methodology depends on.

## 2. Why This Matters

- **This table is the vocabulary every later Part in this roadmap assumes.** Part 3 (Addressing) assumes fluency with IP as the Internet-layer protocol; Part 7 (Transport) assumes fluency with TCP/UDP as Transport-layer protocols; Part 8 (Application-Layer Protocols) assumes the reader already knows why HTTP, DNS, and SSH are all "Application layer" despite being wildly different protocols doing wildly different things.
- **Directly informs what a given security or networking control can see.** Knowing DNS operates at the Application layer (even though it's often used to bootstrap lower-layer connectivity) explains why a Layer 3/4 firewall can block or allow DNS traffic by port/IP but cannot inspect or filter based on the actual domain name being queried — that requires Application-layer awareness.
- **Clarifies why some tools blur categories.** `tcpdump` captures at essentially every layer simultaneously (it captures raw frames, which contain everything nested inside); a WAF only "sees" Layer 7 — this table is what lets you correctly reason about a new tool's capabilities by first asking which layer(s) it operates at.
- **A concentrated, high-yield interview/exam topic.** "What layer does protocol X operate at, and why" is asked constantly, precisely because the answer reveals whether a candidate understands the protocol's actual function, not just its name.
- **Closes out Part 2 as the payoff for [§8](Section-08-Part2-The-OSI-7-Layer-Model-Purpose-and-Layer-by-Layer-Breakdown.md) through [§13](Section-13-Part2-Layer-by-Layer-Troubleshooting-Mental-Model.md).** Every concept from this Part — the OSI layers, the TCP/IP layers, encapsulation, PDUs, protocol data flow, and troubleshooting — comes together in this section as a single, concrete, applied reference.

## 3. Prerequisites and Dependencies

This section assumes familiarity with all of [§8](Section-08-Part2-The-OSI-7-Layer-Model-Purpose-and-Layer-by-Layer-Breakdown.md)–[§13](Section-13-Part2-Layer-by-Layer-Troubleshooting-Mental-Model.md) — the OSI and TCP/IP layer definitions, encapsulation, PDU naming, protocol data flow, and the troubleshooting methodology are all referenced or implied throughout the table below without being re-explained. It intentionally does not teach any of the listed protocols' internal mechanics — IP addressing is covered starting at [§15](../Part3/Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md) (Part 3), TCP/UDP mechanics at [§54](../Part7/Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)–[§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md) (Part 7), and application protocols like HTTP/TLS/SSH at [§63](../Part8/Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)–[§71](../Part8/Section-71-Part8-gRPC-and-Modern-RPC-Protocol-Concepts.md) (Part 8) — this section exists purely to place each protocol correctly on the map before those deep dives begin.

## 4. Architecture / Conceptual Diagram

```text
   OSI LAYER          TCP/IP LAYER        PROTOCOLS (this roadmap's scope)

   7  Application  ┐                      HTTP/1.1, HTTP/2, HTTP/3, DNS, SSH,
   6  Presentation ├──►  Application       SMTP, IMAP, POP3, FTP, SFTP, WebSocket,
   5  Session      ┘                      gRPC, TLS/SSL (commonly discussed here
                                            despite spanning concerns), SNMP

   4  Transport    ──►   Transport         TCP, UDP, QUIC (transport-like, built on UDP)

   3  Network      ──►   Internet          IP (IPv4/IPv6), ICMP, IGMP, routing
                                            protocols in their control-plane role
                                            (OSPF, BGP — Part 4)

   2  Data Link    ┐                      Ethernet (802.3), 802.1Q (VLAN tagging),
   1  Physical     ┴──►  Network Access    ARP*, Wi-Fi (802.11), PPP

   * ARP is a genuine edge case: it resolves Layer 3 addresses (IP) to Layer 2
     addresses (MAC) and is typically classified as operating "between" Layers
     2 and 3, or placed at Layer 2 by convention since it's carried directly
     in an Ethernet frame with no IP header of its own.
```

- Protocols in the **Application** bucket vary enormously in what they actually do (serving web pages vs. resolving names vs. transferring files vs. sending email) — they share a layer classification, not a function; the shared layer only tells you they all run "on top of" a completed Transport-layer connection (or, for UDP-based ones like DNS's typical usage, on top of a connectionless Transport-layer exchange).
- **TLS/SSL** is deliberately called out as spanning classification conventions — it's frequently taught as "Layer 6 (Presentation)" because it handles encryption (a presentation-layer concern), but it also negotiates a session (a session-layer concern) and, in TCP/IP terms, is simply bucketed into "Application" since TCP/IP doesn't separate Presentation at all.
- **ARP** is the clearest case of a protocol that doesn't map cleanly to a single layer — it exists specifically to bridge Layer 3 (IP) addressing to Layer 2 (MAC) addressing, and different textbooks classify it differently as a result ([§23](../Part3/Section-23-Part3-Address-Resolution-ARP-and-NDP.md), Part 3, covers ARP's actual mechanics in full).

## 5. Hands-On

### 5.1 Cross-Referencing `/etc/services` Against the Layer Table

**Purpose:** Use a real system file that lists well-known ports and their associated protocols/services to practice mapping real, everyday protocols to the layers established in this section's table.

**Syntax:**

```bash
grep -E '^(http|https|ssh|dns|domain|smtp|ftp)\b' /etc/services
```

**Example usage and expected output:**

```bash
$ grep -E '^(http|https|ssh|domain|smtp|ftp)\b' /etc/services
ftp             21/tcp
ssh             22/tcp
smtp            25/tcp
domain          53/tcp
domain          53/udp
http            80/tcp
https           443/tcp
```

- Every entry here names an **Application-layer protocol** (FTP, SSH, SMTP, DNS via `domain`, HTTP, HTTPS) alongside the **Transport-layer protocol and port** (`21/tcp`, `53/udp`) it runs on top of — this file is, in effect, a small slice of exactly the mapping this section covers, expressed as literal system configuration rather than abstract theory.
- Note that `domain` (DNS) appears on both `tcp` and `udp` — DNS is one of relatively few common Application-layer protocols that routinely uses either Transport-layer protocol depending on the situation (UDP for ordinary queries, TCP for zone transfers or responses too large for a single UDP datagram, [§48](../Part6/Section-48-Part6-Zone-Files-and-Zone-Transfers-AXFR-IXFR.md) covers this).

**Production usage example:** `/etc/services` is consulted (often implicitly, by tools resolving a service name to a port number) any time a command or configuration file refers to a service by name rather than a raw port number — understanding that this file is itself a protocol-to-port-to-layer mapping reinforces that the abstract table in this section corresponds directly to real, everyday system configuration.

**Common errors:** Assuming every entry in `/etc/services` uses only one Transport-layer protocol (only TCP, or only UDP) is a common mistake — many services, DNS being the clearest example, are correctly configured to use both depending on context, and firewall rules that only account for one can cause intermittent, hard-to-diagnose failures for the other.

### 5.2 Confirming a Protocol's Layer Behavior Directly With `ss`

**Purpose:** Use `ss` to observe, live on a running system, which Transport-layer protocol (TCP vs. UDP) a given Application-layer service is actually using — directly confirming the table's mapping against real, observable system state rather than trusting it as pure reference material.

**Syntax:**

```bash
ss -tulpn | grep <port-or-service>
```

**Example usage and expected output:**

```bash
$ ss -tulpn | grep -E ':(53|22|443)\b'
udp   UNCONN 0      0            0.0.0.0:53          0.0.0.0:*     users:(("named",pid=812,fd=8))
tcp   LISTEN 0      128          0.0.0.0:22           0.0.0.0:*     users:(("sshd",pid=901,fd=3))
tcp   LISTEN 0      511          0.0.0.0:443          0.0.0.0:*     users:(("named",pid=812,fd=9))
```

- The `udp`/`tcp` column at the far left directly confirms, for this specific running system, which Transport-layer protocol each Application-layer service (`named` running DNS, `sshd` running SSH, and a webserver on `443`) is actually using — turning the abstract table into a live, verifiable fact about this particular host.

**Production usage example:** This exact command is used when auditing what's actually listening on a host before writing firewall or security group rules — since a rule written for the wrong Transport-layer protocol (allowing TCP/53 while DNS traffic is actually arriving over UDP/53) silently fails to have the intended effect.

**Common errors:** Forgetting that a service can simultaneously listen on both TCP and UDP for the same port (as DNS commonly does) and only checking or allowing one in a firewall configuration is a frequent, easy-to-miss misconfiguration.

## 6. Production Usage Notes

- Cloud security group and firewall interfaces almost universally require specifying both a **protocol** (TCP/UDP/ICMP — a Transport or Internet-layer choice) and a **port** (a Transport-layer concept) when writing a rule — this table's Transport-layer column is directly what those interfaces are asking you to specify, whether or not the tool's UI uses OSI/TCP-IP terminology explicitly.
- Protocol-to-layer mapping directly determines what kind of load balancer or proxy is even capable of routing a given protocol correctly — a Layer 7/Application-aware load balancer can route HTTP traffic based on URL path, but for a non-HTTP TCP-based protocol (a raw database connection, for instance), only Layer 4 routing is possible, since there's no HTTP-shaped Application-layer content for a Layer 7 device to inspect.
- New or emerging protocols don't always fit neatly into a single layer's box — QUIC ([§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)) is the modern example, implementing Transport-layer-like functionality (reliability, congestion control, multiplexing) while running on top of UDP, which is itself already a Transport-layer protocol; this table should be treated as a living reference to extend, not a fixed, closed list.

## 7. Security Considerations

- Security tooling capability maps directly to the layer(s) it's aware of: a stateless Layer 3/4 ACL can filter by IP and port but is completely blind to protocol-specific content; a Layer 7-aware tool (a WAF, a modern next-generation firewall) can inspect and filter based on actual protocol semantics (an HTTP method, a specific DNS query name) — using this table to reason about exactly which layer a given security control operates at reveals gaps in a security architecture that a purely feature-list-based evaluation might miss.
- Some protocols carry inherent security risk specifically because of their layer and design — plaintext Application-layer protocols (unencrypted HTTP, FTP, plain SMTP, Telnet) transmit content, and sometimes credentials, in the clear, fully visible to anyone with visibility at the lower layers the traffic passes through; their encrypted counterparts (HTTPS, SFTP/FTPS, SMTP with STARTTLS, SSH) exist specifically to close this gap by adding encryption at or near the same layer.
- Protocol identification itself is a security-relevant capability — being able to correctly identify what layer and what protocol a given piece of traffic represents (rather than just "traffic on port 443," which could be legitimate HTTPS or could be a completely different protocol tunneled over that port to evade port-based filtering) is a real and ongoing challenge for security tooling, and directly explains why modern security appliances increasingly perform actual protocol inspection rather than relying on port number alone.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                | Likely Cause                                                                                          | Resolution Path                                                                                                              |
| --------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| A firewall/security group rule "should" allow DNS but some queries still fail | The rule only allows one Transport-layer protocol (e.g., UDP/53) while some DNS traffic (large responses, zone transfers) needs TCP/53 too | Explicitly allow both TCP and UDP on port 53, per [§48](../Part6/Section-48-Part6-Zone-Files-and-Zone-Transfers-AXFR-IXFR.md)'s coverage of when DNS uses each                                        |
| A Layer 4 load balancer can't route traffic based on URL path                | The load balancer genuinely has no Layer 7/Application-layer visibility — this is an architectural limitation of the device's layer, not a misconfiguration | Use a Layer 7-capable load balancer or reverse proxy ([§73](../Part9/Section-73-Part9-Layer-4-vs-Layer-7-Load-Balancing.md), Part 9) instead, if path-based routing is a hard requirement       |
| Traffic on a "well-known" port turns out to be a completely different protocol than expected | An application or attacker is deliberately running a different protocol over a commonly-allowed port to bypass port-based filtering | Use protocol-aware inspection (`tcpdump` payload inspection, or a Layer 7-aware security tool) rather than trusting port number alone |
| Confusion about which layer ARP operates at during a discussion             | ARP is a genuine, widely-acknowledged edge case that doesn't map cleanly to one single layer            | Acknowledge the ambiguity explicitly (Layer 2 by convention, functionally bridging Layer 2 and Layer 3) rather than forcing a false-precision answer |

## 9. Best Practices

- Maintain (personally or as a team reference) an up-to-date protocol-to-layer mapping specific to the protocols your organization actually runs, rather than relying purely on generic reference tables — internal or less common protocols (proprietary RPC formats, internal service mesh protocols) benefit from the same explicit layer classification as the well-known ones listed here.
- When writing firewall/security group rules, explicitly verify both the Transport-layer protocol (TCP vs. UDP) and confirm it matches what the actual Application-layer protocol requires — don't assume a single protocol always uses a single Transport-layer choice.
- When evaluating a new networking or security tool, ask explicitly "which OSI/TCP-IP layer(s) does this tool operate at and have visibility into?" as a first-pass filter for whether it's even architecturally capable of the task being considered.

## 10. Common Anti-Patterns / Mistakes

- **Assuming port number alone reliably identifies the protocol and its layer.** Port 443 is conventionally HTTPS, but nothing prevents a completely different protocol from being run over that port number — relying on port number as a proxy for protocol identity, especially in security contexts, is a well-known and exploitable assumption.
- **Forcing every protocol into a single, unambiguous layer when the honest answer is "it's genuinely a blurred case."** TLS and ARP are the two clearest examples in this section — presenting them with false precision (declaring TLS is "definitely Layer 6" with no caveat) misrepresents how the protocols actually function and how the industry actually discusses them.
- **Treating this table as static and complete.** New protocols (QUIC being the most significant recent example) don't always fit neatly into pre-existing categories, and treating any protocol-to-layer table as a permanently fixed, closed reference rather than a living one leads to confusion when genuinely new designs emerge.

## 11. Interview Questions

**🎯 Beginner:** _"What OSI layer does HTTP operate at? What about TCP? What about IP?"_
**Model answer:** HTTP is an Application-layer protocol (Layer 7) — it defines how a client and server exchange requests and responses. TCP is a Transport-layer protocol (Layer 4) — it provides reliable, ordered, connection-oriented delivery between two endpoints. IP is a Network-layer protocol (Layer 3) — it provides addressing and routing between different networks. In a typical web request, HTTP data is carried inside a TCP segment, which is carried inside an IP packet — each protocol operating at its own distinct layer.
_What the interviewer is probing for:_ Basic, correct recall of the most common protocol-to-layer associations, and understanding that they're nested (HTTP inside TCP inside IP), not independent alternatives.

**🎯 Intermediate:** _"Why is DNS considered an Application-layer protocol, even though it's often used to bootstrap much more basic connectivity, like resolving a hostname before a TCP connection can even be attempted?"_
**Model answer:** DNS's layer classification is based on what DNS itself does — it's a query/response protocol with its own message format, semantics, and behavior, running on top of a completed Transport-layer exchange (typically UDP, sometimes TCP) — which is exactly the definition of an Application-layer protocol, regardless of how "foundational" or "early" in a connection's lifecycle it happens to run. Its layer classification isn't about *when* in a session it's used, but about *what* it does relative to the layers below it: it still needs UDP or TCP (Transport) running on top of IP (Internet) running on top of a physical/data-link connection to function at all — DNS doesn't replace or operate below any of those layers, it just happens to be the very first Application-layer exchange in a typical connection sequence ([§12](Section-12-Part2-Protocol-Data-Flow-A-Packets-Journey-From-Application-to-Wire.md)).
_What the interviewer is probing for:_ Understanding that layer classification is about a protocol's function and dependencies, not about its position in a typical usage timeline — a subtle but important distinction.

**🎯 Senior:** _"TLS is sometimes described as a Presentation-layer (Layer 6) protocol and sometimes as spanning Session and Application layers. Why is there disagreement, and how would you actually classify it for a practical discussion?"_
**Model answer:** The disagreement exists because TLS genuinely performs functions associated with multiple OSI layers: it negotiates and maintains connection state across multiple exchanges (a Session-layer concern, including session resumption), and it handles encryption/data formatting (a Presentation-layer concern) — but it's implemented and typically discussed as running directly on top of TCP and wrapping Application-layer protocols like HTTP, which is why TCP/IP's model, with no separate Session or Presentation layer, simply buckets it into "Application" without controversy. For a practical discussion, I'd classify it based on what's actually useful in context: if the conversation is about what a network device can inspect (can it see decrypted HTTP content? No, unless it terminates TLS itself), calling it "Application-layer, encrypting layer 7 payloads" is the most operationally useful framing. If the conversation is specifically about OSI-layer taxonomy for its own sake, acknowledging it as a genuine edge case spanning Presentation and Session concerns is the more textbook-accurate answer. I'd avoid presenting a single, falsely confident layer number without that context, since the "correct" answer genuinely depends on what the classification is being used for.
_What the interviewer is probing for:_ Comfort with genuine ambiguity in the model, and the ability to give a contextually useful answer rather than reciting a single memorized (and debatable) layer number as if it were an uncontested fact.

**🎯 Architect:** _"You're evaluating three candidate tools for a new API gateway: one operates purely at Layer 4, one at Layer 7 for HTTP/1.1 and HTTP/2 only, and one claims full Layer 7 support including gRPC and WebSockets. How does this section's protocol-to-layer framework inform your evaluation criteria?"_
**Model answer:** I'd start by mapping exactly what each candidate protocol I need to support actually is and which layer it operates at: HTTP/1.1 and HTTP/2 are both squarely Application-layer/Layer 7 protocols with well-established semantics (methods, headers, status codes) that a Layer 7 gateway can route and inspect against. gRPC ([§71](../Part8/Section-71-Part8-gRPC-and-Modern-RPC-Protocol-Concepts.md)) is also Application-layer but built on top of HTTP/2 with its own additional framing and semantics (streaming, protobuf payloads) — a gateway that only understands generic HTTP/2 without gRPC-specific awareness may pass gRPC traffic through at a basic level but won't be able to make gRPC-aware routing or observability decisions (per-RPC-method routing, for instance). WebSockets ([§70](../Part8/Section-70-Part8-WebSockets-and-Persistent-Connections.md)) start as an HTTP/1.1 request but then upgrade to a persistent, bidirectional connection that no longer looks like ordinary request/response HTTP — a gateway needs explicit protocol-upgrade awareness to handle this correctly rather than treating it as a stalled or malformed HTTP request. Given this, I'd disqualify the purely Layer 4 gateway immediately if any Application-layer routing (path-based, header-based, or protocol-specific) is required — a Layer 4 device architecturally cannot provide that regardless of how it's configured. Between the two Layer 7 candidates, I'd weight the third tool's explicit gRPC and WebSocket support heavily, since "Layer 7 support" is not a single monolithic capability — a tool can be genuinely Layer 7-aware for basic HTTP while still being functionally blind to the additional semantics that gRPC and WebSockets layer on top of HTTP, which is exactly the kind of gap this section's framework is designed to surface before a costly tool selection mistake.
_What the interviewer is probing for:_ The ability to use protocol-layer classification as a genuine, granular tool-evaluation framework — recognizing that "Layer 7 support" is not binary and that specific protocols built on top of a base protocol (gRPC/WebSockets on HTTP) can have their own distinct layer-awareness requirements.

## 12. Common Misconceptions

1. **"Every protocol maps cleanly to exactly one layer with no ambiguity."** TLS and ARP are two well-known, widely-discussed exceptions where the honest, technically accurate answer acknowledges the protocol spans or bridges layers rather than fitting a single box.
2. **"The port number reliably tells you the protocol and its layer."** Port numbers are a convention, not an enforced guarantee — any protocol can technically run on any port, and security-conscious engineers should not treat port number alone as proof of what protocol is actually present.
3. **"DNS being 'Application-layer' means it's a late or optional step in a connection."** DNS's layer classification reflects its function and dependencies, not its position in a typical sequence — it's frequently the very first Application-layer exchange to occur, as shown in [§12](Section-12-Part2-Protocol-Data-Flow-A-Packets-Journey-From-Application-to-Wire.md)'s protocol data flow.
4. **"'Layer 7-aware' is a single, uniform capability shared equally by every tool that claims it."** Different Layer 7-aware tools can have very different depth of understanding of specific Application-layer protocols built on top of a common base (e.g., generic HTTP awareness versus genuine gRPC- or WebSocket-specific awareness) — the label alone doesn't guarantee equivalent capability.

## 13. 🔑 Key Takeaways

- HTTP, DNS, SSH, TLS, SMTP, and most protocols an infrastructure engineer directly interacts with are Application-layer (OSI Layer 7, or TCP/IP's collapsed Application layer) protocols, running on top of a Transport-layer connection (TCP or UDP).
- TCP and UDP are the two foundational Transport-layer (OSI Layer 4) protocols; QUIC is a newer transport-like protocol built on top of UDP that complicates a strictly one-protocol-per-layer view.
- IP is the unambiguous Internet-layer (OSI Layer 3) protocol; ARP is a genuine edge case that bridges Layer 2 and Layer 3 rather than fitting cleanly into either.
- A protocol's layer classification reflects its function and what it depends on, not when in a typical connection sequence it happens to be used — DNS being "Application-layer" doesn't contradict it being the very first exchange in a typical request ([§12](Section-12-Part2-Protocol-Data-Flow-A-Packets-Journey-From-Application-to-Wire.md)).
- Understanding exactly which layer a security or networking tool operates at and has visibility into is a direct, practical application of this table — it reveals real architectural capabilities and gaps that a feature-list alone can obscure.

## 14. Related Concepts & What's Next

This section closes out Part 2 by drawing together [§8](Section-08-Part2-The-OSI-7-Layer-Model-Purpose-and-Layer-by-Layer-Breakdown.md) (OSI layers), [§9](Section-09-Part2-The-TCP-IP-4-Layer-Model-and-How-It-Maps-to-OSI.md) (TCP/IP layers), [§10](Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md) (encapsulation), [§11](Section-11-Part2-PDUs-at-Each-Layer-Bits-Frames-Packets-Segments-Data.md) (PDUs), [§12](Section-12-Part2-Protocol-Data-Flow-A-Packets-Journey-From-Application-to-Wire.md) (protocol data flow), and [§13](Section-13-Part2-Layer-by-Layer-Troubleshooting-Mental-Model.md) (troubleshooting methodology) into one applied, protocol-by-protocol reference. Every subsequent Part of this roadmap builds on the classifications established here: Part 3 ([§15](../Part3/Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md)–[§24](../Part3/Section-24-Part3-DHCP-Lease-Lifecycle-Relay-and-Options.md)) begins with IP addressing, the Internet-layer protocol at the center of this table; Part 7 ([§54](../Part7/Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)–[§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)) returns to TCP, UDP, and QUIC in full depth; Part 8 ([§63](../Part8/Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)–[§71](../Part8/Section-71-Part8-gRPC-and-Modern-RPC-Protocol-Concepts.md)) covers HTTP, TLS, SSH, and the other Application-layer protocols listed here one by one; and Part 9 ([§72](../Part9/Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md)–[§81](../Part9/Section-81-Part9-Software-Load-Balancers-NGINX-HAProxy-Envoy-Conceptual-Comparison.md)) picks the Layer 4 vs. Layer 7 load-balancing distinction touched on above back up in full architectural depth.

**Next Section:** [§15](../Part3/Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md) — `Part 3, Section 15 (not yet authored) — IPv4 Address Structure: Binary, Dotted-Decimal, and Address Classes`
