# Section 55 (Part 7): TCP Three-Way Handshake and Connection Teardown (FIN/RST)

## 1. Definition

**Plain language:** Before two computers exchange any real data over TCP, they perform a short three-message handshake to agree "yes, I'm here, let's talk, and here's where each of us is starting counting from." When they're done, they perform a similarly polite (or, if something goes wrong, distinctly impolite) exchange to close the conversation — either a graceful multi-step goodbye (FIN) or an abrupt hang-up (RST).

**Precise definition:** The **TCP three-way handshake** is the connection-establishment procedure defined in RFC 793 (and its successors): the client sends a segment with the **SYN** flag set and an **Initial Sequence Number (ISN)**; the server responds with a segment carrying both **SYN** and **ACK** flags, acknowledging the client's ISN and supplying its own ISN; the client completes the exchange with a final **ACK** segment acknowledging the server's ISN. Only after this exchange does the connection enter the **ESTABLISHED** state ([§61](Section-61-Part7-Connection-States-and-the-TCP-State-Machine-LISTEN-ESTABLISHED-TIME-WAIT.md)) and carry application data. Connection teardown normally uses the **FIN** (finish) flag in a four-step exchange that allows each side to close its half of the connection independently (a **half-close**), while an abrupt, non-graceful termination uses the **RST** (reset) flag, which immediately tears down the connection with no negotiation and typically signals an error condition (connection refused, or an attempt to send on an already-closed connection).

> 💡 **Tip:** The handshake exists for one reason above all others: to synchronize **initial sequence numbers** between the two endpoints, which is the foundation everything in [§56](Section-56-Part7-TCP-Reliability-Sequence-Numbers-ACKs-Retransmission.md) (reliability) depends on. "Three-way" is not an arbitrary number — two messages are insufficient because the server also needs the client to acknowledge the server's own ISN, and this is the minimum exchange that lets both sides confirm both directions of the connection are viable before committing resources.

## 2. Why This Matters

- **It's the single most captured, most interview-tested TCP mechanic in networking.** Nearly every packet capture debugging session for a connectivity issue starts by looking for whether a SYN even received a SYN-ACK — this is the first diagnostic checkpoint above Layer 3.
- **A stuck or failing handshake has a small, well-known set of causes**, each pointing to a different layer of the stack (firewall drop, no listener, routing asymmetry) — recognizing which handshake stage failed massively narrows troubleshooting.
- **The handshake's resource cost is the mechanism behind SYN flood DDoS attacks** ([§88](../Part10/Section-88-Part10-DDoS-Attack-Types-and-Mitigation-Strategies.md)) — understanding exactly what state the server allocates after receiving a bare SYN explains why this specific attack works and how SYN cookies defend against it.
- **Graceful (FIN) vs. abrupt (RST) teardown produce different, diagnosable signatures** in packet captures and application error messages — "connection reset by peer" (RST) and a clean close (FIN exchange) mean structurally different things and point troubleshooting in different directions.
- **Load balancers, firewalls, and proxies must correctly track handshake and teardown state** to function as stateful devices ([§82](../Part10/Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md)) — misconfigured timeout or state-tracking behavior around this exchange is a recurring source of production incidents (premature connection drops, orphaned half-open connections).

## 3. Prerequisites and Dependencies

This section builds directly on [§54](Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)'s distinction between connection-oriented and connectionless transport — everything here is specific to TCP and has no UDP equivalent. It assumes the encapsulation model from [§10](../Part2/Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md) (a TCP segment is wrapped inside an IP packet, itself wrapped inside a Layer 2 frame) and benefits from familiarity with the packet-capture techniques introduced conceptually in [§8](../Part2/Section-08-Part2-The-OSI-7-Layer-Model-Purpose-and-Layer-by-Layer-Breakdown.md)'s `tcpdump -XX` example, since this section's hands-on work relies heavily on reading captured SYN/SYN-ACK/ACK exchanges. [§56](Section-56-Part7-TCP-Reliability-Sequence-Numbers-ACKs-Retransmission.md) (sequence numbers and reliability) and [§61](Section-61-Part7-Connection-States-and-the-TCP-State-Machine-LISTEN-ESTABLISHED-TIME-WAIT.md) (the full TCP state machine) both depend directly on the handshake and teardown mechanics established here.

## 4. Architecture / Conceptual Diagram

```text
   THREE-WAY HANDSHAKE (connection establishment)

   Client                                          Server
     │                                                │
     │  SYN  seq=X                                    │
     │───────────────────────────────────────────────►│   (server allocates
     │                                                  │    partial connection
     │  SYN, ACK  seq=Y, ack=X+1                        │    state — SYN_RECEIVED)
     │◄───────────────────────────────────────────────│
     │                                                │
     │  ACK  seq=X+1, ack=Y+1                          │
     │───────────────────────────────────────────────►│
     │                                                │
     │        both sides now: ESTABLISHED             │
     │◄════════ application data flows ══════════════►│


   GRACEFUL TEARDOWN (four-way FIN exchange, independent half-closes)

   Client                                          Server
     │  FIN  seq=M          (client done sending)      │
     │───────────────────────────────────────────────►│   → server: CLOSE_WAIT
     │  ACK  ack=M+1                                    │
     │◄───────────────────────────────────────────────│   → client: FIN_WAIT_2
     │           (server may still send data here)      │
     │  FIN  seq=N          (server done sending)       │
     │◄───────────────────────────────────────────────│   → server: LAST_ACK
     │  ACK  ack=N+1                                    │
     │───────────────────────────────────────────────►│   → server: CLOSED
     │  (client waits TIME_WAIT, then CLOSED — §61)     │


   ABRUPT TEARDOWN (reset)

   Client                                          Server
     │  data to a port with no listener,               │
     │  or a broken/killed connection                  │
     │───────────────────────────────────────────────►│
     │  RST                                            │
     │◄───────────────────────────────────────────────│   connection torn down
     │                                                  │   immediately, no
     │                                                  │   negotiation
```

- The handshake's second message (**SYN-ACK**) does double duty — it is simultaneously the server's own SYN (proposing its ISN) and its ACK of the client's SYN, which is why the exchange only needs three messages rather than four.
- Graceful teardown is **independent per direction**: a FIN only says "I will send no more data," not "stop sending me data" — this is why the server can continue sending data after receiving the client's FIN (the **half-close**), and why the exchange takes four messages total (though the middle ACK and FIN are sometimes combined, making it look like three).
- RST carries **no sequence negotiation** and skips straight to tearing down state on receipt — it is used for error conditions (connecting to a closed port), forcibly aborting a connection, or by firewalls actively rejecting a connection rather than silently dropping it.

## 5. Hands-On

### 5.1 Capturing a Live Handshake With `tcpdump`

**Purpose:** Observe the SYN, SYN-ACK, and ACK segments of a real handshake, with their flags and sequence numbers visible.

**Syntax:**

```bash
sudo tcpdump -i <interface> -n 'tcp[tcpflags] & (tcp-syn|tcp-ack) != 0' -c 6
```

**Example usage and expected output:**

```bash
$ sudo tcpdump -i eth0 -n port 443 -c 3
14:10:02.001122 IP 10.0.1.15.51422 > 93.184.216.34.443: Flags [S], seq 1898273001, win 64240, length 0
14:10:02.024871 IP 93.184.216.34.443 > 10.0.1.15.51422: Flags [S.], seq 3021948833, ack 1898273002, win 65535, length 0
14:10:02.024933 IP 10.0.1.15.51422 > 93.184.216.34.443: Flags [.], seq 1898273002, ack 3021948834, win 64240, length 0
```

- `Flags [S]` is a bare SYN, `Flags [S.]` is SYN-ACK (`tcpdump` shorthand: `.` means ACK is also set), and `Flags [.]` is a pure ACK with no other flags — this is the final handshake message.
- Note `ack 1898273002` in the second line — this is the client's ISN (`1898273001`) plus 1, confirming the receiver's sequence-number bookkeeping already discussed in the definition above and expanded in [§56](Section-56-Part7-TCP-Reliability-Sequence-Numbers-ACKs-Retransmission.md).

**Production usage example:** This exact filter is the starting point for diagnosing "connection sometimes hangs" reports — capturing traffic and confirming whether a SYN ever receives a SYN-ACK immediately tells you whether the problem is server-side (no response at all — firewall drop or dead service) or later in the exchange (handshake completes but the application never responds).

**Common errors:** Forgetting that a firewall which **drops** SYN packets (vs. one that **rejects** with an RST) produces no visible response at all in the capture on the client side — the client will simply retransmit the SYN repeatedly until it gives up, which can look identical to "the server is just slow" unless you also capture on the server side to confirm the SYN never arrived.

### 5.2 Distinguishing a Graceful Close From a Reset

**Purpose:** Tell, from a packet capture, whether a connection ended cleanly (FIN exchange) or was aborted (RST).

**Syntax:**

```bash
sudo tcpdump -i <interface> -n 'tcp[tcpflags] & (tcp-fin|tcp-rst) != 0'
```

**Example usage and expected output:**

```bash
$ sudo tcpdump -i eth0 -n 'tcp[tcpflags] & (tcp-fin|tcp-rst) != 0'
14:12:40.881212 IP 10.0.1.15.51422 > 93.184.216.34.443: Flags [F.], seq 812, ack 4501, win 502, length 0
14:12:40.903355 IP 93.184.216.34.443 > 10.0.1.15.51422: Flags [F.], seq 4501, ack 813, win 501, length 0
14:12:40.903400 IP 10.0.1.15.51422 > 93.184.216.34.443: Flags [.], seq 813, ack 4502, win 502, length 0

# vs. an abrupt reset:
14:15:02.552310 IP 93.184.216.34.443 > 10.0.1.15.51500: Flags [R], seq 0, win 0, length 0
```

- `Flags [F.]` shows FIN combined with ACK — a normal, graceful close where both sides exchange FINs.
- `Flags [R]` with `seq 0, win 0` is a raw reset — no graceful negotiation, connection torn down immediately, often seen when connecting to a closed port or when an application crashes mid-connection.

**Production usage example:** Application logs reporting `Connection reset by peer` correspond directly to receiving an RST — this is the diagnostic bridge between an application-level error message and its exact on-the-wire cause, and is one of the most common things engineers grep for when correlating app logs with packet captures during an incident.

**Common errors:** Assuming every RST indicates a bug — RST is also the **correct, expected** response when a client connects to a port with no listener (instead of a silent timeout), so seeing an RST is not inherently a problem; context (was a connection supposed to be established and stable, or was this a legitimate probe of a closed port?) determines whether it's actually an issue.

### 5.3 Testing Handshake Behavior Against a Closed vs. Filtered Port

**Purpose:** See directly how a closed port (RST) differs from a filtered/firewalled port (no response, timeout) — a distinction that matters constantly in production troubleshooting.

**Syntax:**

```bash
nc -zv <host> <port>
```

**Example usage and expected output:**

```bash
$ nc -zv 10.0.1.20 9999
nc: connect to 10.0.1.20 port 9999 (tcp) failed: Connection refused
# (server actively sent an RST — port is closed, but reachable)

$ nc -zv 10.0.1.20 8443
# ... hangs for a long time, eventually:
nc: connect to 10.0.1.20 port 8443 (tcp) timed out: Operation now in progress
# (no response at all — a firewall dropped the SYN silently)
```

**Production usage example:** This distinction is exactly how engineers determine whether a security group or firewall is configured to **drop** (silent, causes timeouts) or **reject** (sends RST, fails fast) — a "drop" policy is more secure (doesn't confirm to a scanner that a host even exists) but makes legitimate troubleshooting slower because every blocked attempt hangs for the full connection timeout instead of failing immediately.

**Common errors:** Interpreting a long hang as "the network is slow" rather than "something is silently dropping this traffic" — a fast `Connection refused` and a 30-second timeout both indicate the port isn't usable, but they point to entirely different remediation paths (application not running vs. a firewall rule).

## 6. Production Usage Notes

- Load balancers and reverse proxies ([§72](../Part9/Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md), [§77](../Part9/Section-77-Part9-Session-Persistence-Sticky-Sessions-and-Its-Trade-Offs.md)) generally terminate the client-facing TCP connection themselves and open a **separate** TCP connection (with its own independent handshake) to the backend — this means a single logical client request actually involves two full handshakes, which matters when reasoning about connection-count limits and handshake-related latency in a proxied architecture.
- **TCP Fast Open (TFO)** is a real-world optimization that allows data to be included in the initial SYN itself for previously-seen connections, skipping the round trip normally required to wait for the handshake to complete before sending data — relevant context for why QUIC ([§62](Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md)) pursues similar 0-RTT goals more aggressively.
- Connection teardown that never completes (a FIN sent but never acknowledged, or an endpoint that crashes mid-close) leaves connections stuck in intermediate states until OS-level timers expire — this directly feeds into the TIME_WAIT and orphaned-connection discussion in [§61](Section-61-Part7-Connection-States-and-the-TCP-State-Machine-LISTEN-ESTABLISHED-TIME-WAIT.md).

## 7. Security Considerations

- **SYN flood attacks** exploit the asymmetry in the handshake: a server allocates connection-tracking state upon receiving a SYN, before the handshake completes, so an attacker flooding SYNs (often from spoofed source addresses, since no reply is expected) can exhaust that state without ever completing a single real connection. **SYN cookies** mitigate this by deferring state allocation — the server encodes the necessary state into the SYN-ACK's sequence number itself rather than storing it, only allocating real state once the final ACK proves the client is legitimate.
- An RST can be **injected by a third party** (an on-path attacker, or historically some ISP-level traffic-shaping middleboxes) to forcibly and maliciously terminate a legitimate connection — TCP has no cryptographic protection against a spoofed RST unless the connection itself is wrapped in TLS ([§65](../Part8/Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)), which detects (though does not prevent) the tampering at the application layer.
- Firewalls that **drop** rather than **reject** unauthorized connection attempts (silently discarding the SYN) provide a small but real security benefit by not confirming to a port scanner that a host exists at all — this is a deliberate, common hardening choice, not an oversight, and explains why some ports "just hang" rather than refuse cleanly.

## 8. Common Troubleshooting Scenarios

| Symptom                                                        | Likely Cause                                                                 | Resolution Path                                                                                                     |
| ---------------------------------------------------------------- | --------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Connection attempt hangs, eventually times out, no RST seen      | Firewall/security group is silently dropping the SYN                        | Capture on both client and server sides to confirm the SYN never arrives server-side; fix the firewall/SG rule ([§82](../Part10/Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md), [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)) |
| Connection immediately fails with "Connection refused"           | Port is reachable but nothing is listening, or the app explicitly rejected it | Confirm the target service is running and bound to the expected port (`ss -tlnp`, [§59](Section-59-Part7-Ports-and-Sockets-Well-Known-Registered-and-Ephemeral-Ranges.md)); check application logs      |
| Application logs "Connection reset by peer" mid-transfer         | Peer sent an RST — application crash, load balancer idle timeout, or explicit abort | Correlate timing with application/load-balancer logs; capture traffic to confirm the RST's origin and timing        |
| Many connections stuck, never fully closing                      | FIN sent but the peer's ACK/FIN never arrives — half-open or hung connection  | Inspect connection states with `ss -tan` ([§61](Section-61-Part7-Connection-States-and-the-TCP-State-Machine-LISTEN-ESTABLISHED-TIME-WAIT.md)); check for a crashed peer process or a network path drop mid-teardown |
| Server under load suddenly refuses all new connections            | Possible SYN flood exhausting connection-tracking state                       | Check SYN backlog/queue metrics; verify SYN cookies are enabled (`net.ipv4.tcp_syncookies`)                          |

## 9. Best Practices

- When debugging any TCP connectivity issue, capture traffic and look at the handshake stage first — knowing exactly which of SYN, SYN-ACK, or final ACK is missing (or absent entirely) tells you which side and which layer to investigate next.
- Distinguish "connection refused" (RST, port closed) from "connection timed out" (no response, likely filtered) explicitly in monitoring and alerting — they are different failure modes requiring different remediation.
- Enable SYN cookies (`net.ipv4.tcp_syncookies = 1`, the Linux default on most modern distributions) on any internet-facing host as a baseline defense against SYN flood attacks.

## 10. Common Anti-Patterns / Mistakes

- **Treating every RST in a packet capture as evidence of a bug.** RST is the normal, correct response to connecting to a closed port or a deliberately aborted connection — context determines whether an observed RST is actually a problem.
- **Ignoring the distinction between a dropped and a rejected connection attempt when writing firewall rules.** Silently dropping everything by default is often the right security posture, but doing so without understanding that it produces slow timeouts rather than fast failures leads to confusing, hard-to-diagnose "hanging" symptoms in dependent systems and health checks.
- **Assuming a completed handshake means the application is healthy.** A successful three-way handshake only proves the TCP stack on both hosts is reachable and functioning — the application behind the listening socket can still be broken, slow, or unresponsive at Layer 7, which is a completely separate failure mode requiring Layer 7 diagnostics ([§115](../Part14/Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md)).

## 11. Interview Questions

**🎯 Beginner:** _"Walk me through the TCP three-way handshake."_
**Model answer:** The client sends a SYN segment with its initial sequence number. The server replies with a SYN-ACK — acknowledging the client's sequence number and providing its own initial sequence number. The client sends a final ACK acknowledging the server's sequence number. After this, the connection is established and both sides can exchange application data.
_What the interviewer is probing for:_ Correct sequencing and terminology — the foundational fact every deeper TCP question builds on.

**🎯 Intermediate:** _"What's the difference between a connection closing via FIN versus being terminated via RST, and how would you tell them apart in a packet capture?"_
**Model answer:** A FIN-based close is graceful and negotiated — each side independently signals it has no more data to send (a FIN), the other acknowledges it, and this happens in both directions before the connection fully closes; a half-close lets one side keep sending after the other has finished. An RST is an abrupt, unilateral termination with no negotiation — used for connecting to closed ports, aborting a connection, or signaling an error. In a capture, FIN appears as `Flags [F.]` (FIN+ACK) messages exchanged in sequence with corresponding ACKs; RST appears as a single `Flags [R]` segment with no further negotiation, often with `seq 0, win 0`.
_What the interviewer is probing for:_ Practical packet-capture literacy, not just textbook knowledge of the flags.

**🎯 Senior:** _"Explain how a SYN flood attack works and how SYN cookies mitigate it."_
**Model answer:** A SYN flood exploits the fact that a server must allocate connection-tracking state (in the SYN backlog/queue) as soon as it receives a SYN, before the handshake completes — an attacker (often with spoofed source IPs, since no reply is needed for the attack to work) sends a large volume of SYNs and never completes the handshake, exhausting the server's connection-tracking resources and preventing legitimate connections. SYN cookies mitigate this by not allocating any real state upon receiving a SYN — instead, the server encodes the necessary connection information into the sequence number it sends back in the SYN-ACK. If the client is legitimate, its final ACK will echo back that encoded sequence number, and the server can reconstruct the connection state at that point, having never stored anything for the flood of never-completed connections.
_What the interviewer is probing for:_ Genuine mechanical understanding of both the attack and the defense, not just the term "SYN flood."

**🎯 Architect:** _"You're designing a high-throughput API gateway that terminates millions of client TCP connections per day. What handshake- and teardown-related design decisions matter most for reliability and cost?"_
**Model answer:** First, connection reuse matters enormously — encouraging keep-alive and HTTP/1.1 persistent connections (or HTTP/2 multiplexing, [§64](../Part8/Section-64-Part8-HTTP-2-and-HTTP-3-Multiplexing-Header-Compression-QUIC-Transport.md)) amortizes the handshake's round-trip cost across many requests instead of paying it per request; at scale, that round trip is a meaningful fraction of total latency and CPU cost. Second, I'd tune the SYN backlog and enable SYN cookies to withstand both legitimate traffic spikes and SYN flood attempts without dropping connection attempts. Third, teardown behavior needs explicit design: idle-connection timeouts (closing gracefully with FIN rather than letting connections linger, and coordinating those timeouts with any downstream load balancer or backend so timeouts don't mismatch and cause one side to RST a connection the other side still considers alive — a very common source of intermittent "connection reset" errors in layered proxy architectures). Finally, I'd monitor RST rates as a first-class health signal — a rising RST rate against backends often signals timeout mismatches or backend instability well before it shows up in higher-level error-rate dashboards.
_What the interviewer is probing for:_ Ability to connect low-level handshake/teardown mechanics to real system-design trade-offs (cost, latency, cross-component timeout coordination) at production scale.

## 12. Common Misconceptions

1. **"The three-way handshake transmits application data."** It transmits only control information (SYN/ACK flags and sequence numbers) — the very first application data byte is sent only after the handshake completes (TCP Fast Open being a narrow, opt-in exception).
2. **"A FIN immediately closes the entire connection in both directions."** A FIN only closes the sender's outbound direction (a half-close); the other side can continue sending data until it, too, sends its own FIN.
3. **"An RST always indicates malicious activity or a serious bug."** It is also the normal, correct response to connecting to a closed port and a routine outcome of many legitimate connection-abort scenarios (application shutdown, load balancer timeout).
4. **"A completed handshake means the service is healthy and working."** It only confirms the TCP stack is reachable and responsive — the application behind the socket can still be broken or unresponsive at Layer 7.

## 13. 🔑 Key Takeaways

- The three-way handshake (SYN, SYN-ACK, ACK) exists primarily to synchronize initial sequence numbers between both endpoints before any data flows.
- Graceful teardown uses FIN in an independent, per-direction exchange (a half-close is possible); abrupt teardown uses RST with no negotiation.
- SYN floods exploit the state a server allocates upon receiving a bare SYN; SYN cookies defend against this by deferring state allocation until the handshake actually completes.
- "Connection refused" (RST) and "connection timed out" (silently dropped) are distinct failure signatures pointing to different root causes — closed port vs. filtered/firewalled port.
- A completed handshake proves transport-layer reachability only, not application health.

## 14. Related Concepts & What's Next

[§56](Section-56-Part7-TCP-Reliability-Sequence-Numbers-ACKs-Retransmission.md) picks up immediately where this section's ISN synchronization leaves off, detailing exactly how sequence numbers and acknowledgments deliver TCP's reliability guarantee segment by segment. [§57](Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md) builds on the same connection state to explain how the window sizes exchanged during and after the handshake govern flow and congestion control. [§61](Section-61-Part7-Connection-States-and-the-TCP-State-Machine-LISTEN-ESTABLISHED-TIME-WAIT.md) assembles the handshake and teardown states covered here, plus several intermediate states not discussed in depth here, into the complete TCP state machine. [§88](../Part10/Section-88-Part10-DDoS-Attack-Types-and-Mitigation-Strategies.md) revisits the SYN flood attack introduced in this section's security discussion as part of a broader survey of DDoS attack types.

**Next Section:** [§56](Section-56-Part7-TCP-Reliability-Sequence-Numbers-ACKs-Retransmission.md) — `Section-56-Part7-TCP-Reliability-Sequence-Numbers-ACKs-Retransmission.md`
