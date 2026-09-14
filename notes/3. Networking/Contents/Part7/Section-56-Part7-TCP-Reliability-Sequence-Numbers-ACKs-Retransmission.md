# Section 56 (Part 7): TCP Reliability: Sequence Numbers, ACKs, Retransmission

## 1. Definition

**Plain language:** TCP treats the data it sends as one continuous stream of numbered bytes. Every byte has a position number, the receiver tells the sender exactly how far along that stream it has successfully received, and if the sender doesn't hear confirmation within a reasonable time, it assumes the data got lost and sends it again. This numbering-and-confirming loop is the entire mechanism behind TCP's famous reliability guarantee.

**Precise definition:** TCP achieves reliable delivery through **sequence numbers** — a 32-bit counter, initialized to a randomized **Initial Sequence Number (ISN)** during the handshake ([§55](Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md)), that identifies the byte-offset position of the first byte of data in a given segment within the overall stream — and **acknowledgment numbers**, which a receiver returns to indicate the next byte-offset it expects to receive (a **cumulative ACK**, confirming everything up to that point has arrived correctly). When a sender does not receive an ACK for transmitted data within its **retransmission timeout (RTO)** — a value dynamically calculated from measured round-trip time (RTT) and its variance — it retransmits the unacknowledged data. **Fast retransmit** provides a quicker recovery path: three duplicate ACKs (the receiver repeatedly acknowledging the same byte offset because a later segment arrived out of order, implying an earlier one is missing) trigger immediate retransmission of the missing segment without waiting for the full RTO to expire. **Selective Acknowledgment (SACK)**, a widely supported TCP option, lets a receiver report specific non-contiguous blocks of data it has received, allowing the sender to retransmit only the genuinely missing gaps rather than everything after the first loss.

> 💡 **Tip:** TCP's reliability is fundamentally about the **receiver never having to keep asking "did you get my last message?"** — it's the opposite direction: the receiver constantly tells the sender "here's the furthest point I've received contiguously," and the sender's entire retransmission logic exists to fill in gaps below that point. This inversion (receiver reports progress, sender infers loss) is why understanding ACK numbers matters more for debugging than sequence numbers alone.

## 2. Why This Matters

- **It's the mechanism that lets application developers ignore packet loss entirely.** Every guarantee "TCP delivers my bytes reliably and in order" rests entirely on the sequence/ACK/retransmission loop described here — no application code has to detect or handle a dropped segment.
- **Retransmissions are directly visible and diagnosable in packet captures**, and a rising retransmission rate is one of the most reliable early indicators of network-path degradation, congestion, or a failing link, long before an application notices errors.
- **The distinction between timeout-based and fast retransmission explains real latency behavior** — a connection recovering from loss via fast retransmit barely stutters, while one waiting on a full RTO can stall for a second or more, and knowing which is happening changes how you interpret a latency spike.
- **SACK support (or its absence) materially affects recovery performance** under loss — a connection without SACK support (rare today, but relevant with legacy stacks or certain middleboxes) retransmits far more data than necessary after a single lost segment, a phenomenon worth recognizing when debugging unexpectedly poor throughput on lossy links.
- **This mechanism directly feeds congestion control ([§57](Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md))** — every retransmission event is also treated by the sender as a signal that the network path may be congested, tying reliability and congestion avoidance together at the implementation level.

## 3. Prerequisites and Dependencies

This section depends directly on [§55](Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md)'s three-way handshake, since the Initial Sequence Numbers exchanged during the handshake are the starting point for every sequence and acknowledgment number discussed here. It assumes the general connection-oriented model established in [§54](Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md) and benefits from the packet-capture fluency built in [§55](Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md)'s hands-on exercises, since retransmissions and duplicate ACKs are primarily diagnosed by reading captured traffic. [§57](Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md) (flow and congestion control) builds directly on the RTT measurement and loss-detection concepts introduced in this section, and [§61](Section-61-Part7-Connection-States-and-the-TCP-State-Machine-LISTEN-ESTABLISHED-TIME-WAIT.md) (the TCP state machine) assumes the ESTABLISHED-state data-transfer behavior described here.

## 4. Architecture / Conceptual Diagram

```text
   SEQUENCE NUMBERS AS STREAM BYTE OFFSETS

   Sender's byte stream:  [ 0 ... 999 ][ 1000 ... 1999 ][ 2000 ... 2999 ]
                             Segment A       Segment B        Segment C
                             seq=0           seq=1000         seq=2000
                             len=1000        len=1000         len=1000

   Receiver, after A and B arrive successfully, sends:
        ACK  ack=2000   ("I have everything up through byte 1999;
                          I expect byte 2000 next")

   NORMAL FLOW (no loss)

   Sender                                          Receiver
     │  seq=0,    len=1000                          │
     │──────────────────────────────────────────────►│
     │  seq=1000, len=1000                            │
     │──────────────────────────────────────────────►│
     │                     ack=2000                   │
     │◄──────────────────────────────────────────────│


   LOSS + FAST RETRANSMIT (segment B lost in transit)

   Sender                                          Receiver
     │  seq=0,    len=1000  (A)                       │
     │──────────────────────────────────────────────►│  ack=1000
     │  seq=1000, len=1000  (B)  ✗ LOST                │◄────────
     │───────────X                                    │
     │  seq=2000, len=1000  (C)                        │
     │──────────────────────────────────────────────►│  ack=1000  (dup #1 —
     │  seq=3000, len=1000  (D)                        │            still waiting
     │──────────────────────────────────────────────►│  ack=1000  (dup #2)   for B)
     │                                                 │  ack=1000  (dup #3)
     │◄════ 3 duplicate ACKs seen → FAST RETRANSMIT ══│
     │  seq=1000, len=1000  (B, retransmitted)         │
     │──────────────────────────────────────────────►│  ack=4000  (cumulative:
     │                                                 │            B filled the
     │                                                 │            gap, C and D
     │                                                 │            already buffered)
```

- The receiver **buffers out-of-order segments** (C and D above) rather than discarding them, which is why the cumulative ACK jumps straight to `4000` once the missing segment B is filled in — this is far more efficient than retransmitting C and D as well.
- **Duplicate ACKs** are the receiver's only way to signal "I received something, but it wasn't the byte offset I was expecting" — three of them (by convention) is the threshold TCP implementations use to infer loss without waiting for a timeout.
- If fast retransmit doesn't trigger (e.g., too few subsequent segments were in flight to generate three duplicate ACKs), the sender falls back to the **retransmission timeout (RTO)**, calculated from smoothed RTT measurements — this path is slower to recover but is the fallback of last resort.

## 5. Hands-On

### 5.1 Observing Retransmissions With `tcpdump`

**Purpose:** Directly identify retransmitted segments and duplicate ACKs in a live or captured trace.

**Syntax:**

```bash
sudo tcpdump -i <interface> -n tcp and host <host>
```

**Example usage and expected output:**

```bash
$ sudo tcpdump -i eth0 -n host 93.184.216.34
14:20:01.100000 IP 10.0.1.15.51500 > 93.184.216.34.443: Flags [.], seq 1000:2000, ack 1, win 502, length 1000
14:20:01.310000 IP 93.184.216.34.443 > 10.0.1.15.51500: Flags [.], ack 1000, win 501, length 0
14:20:01.320000 IP 10.0.1.15.51500 > 93.184.216.34.443: Flags [.], seq 2000:3000, ack 1, win 502, length 1000
14:20:01.530000 IP 93.184.216.34.443 > 10.0.1.15.51500: Flags [.], ack 1000, win 501, length 0
14:20:01.540000 IP 10.0.1.15.51500 > 93.184.216.34.443: Flags [.], seq 1000:2000, ack 1, win 502, length 1000
14:20:01.541001 IP 10.0.1.15.51500 > 93.184.216.34.443: Flags [.], seq 1000:2000, ack 1, win 502, length 1000 [TCP Retransmission]
```

- Repeated `ack 1000` lines with no growth are **duplicate ACKs** — the receiver keeps acknowledging the same offset because it's still missing the segment that would let it advance.
- `[TCP Retransmission]` is a marker Wireshark (and modern `tcpdump` builds) add when it recognizes a segment with a sequence number it has already seen going out — Wireshark's decode view ([§119](../Part14/Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md)) makes this far easier to spot at scale than raw `tcpdump` text.

**Production usage example:** Engineers grep captured traffic for `[TCP Retransmission]` or count duplicate ACKs per connection as a first-pass health signal when investigating "throughput is lower than expected" tickets — a link with a 2% retransmission rate has a fundamentally different problem (lossy path, congestion, or MTU-related fragmentation issues, [§122](../Part14/Section-122-Part14-MTU-Issues-and-Path-MTU-Discovery.md)) than one with none.

**Common errors:** Confusing a legitimate application-layer retry (a new HTTP request after a previous one failed) with a TCP-layer retransmission (the same segment, same sequence number, resent by the OS's TCP stack) — they look completely different in a capture (retransmissions reuse the exact sequence number; application retries are entirely new, independent TCP segments, often on a new connection).

### 5.2 Inspecting Retransmission Statistics Per Connection With `ss`

**Purpose:** Get a live, per-connection summary of retransmission counts and RTT without needing a full packet capture.

**Syntax:**

```bash
ss -ti
```

**Example usage and expected output:**

```bash
$ ss -ti dst 93.184.216.34
ESTAB  0  0  10.0.1.15:51500  93.184.216.34:443
    cubic wscale:7,7 rto:212 rtt:11.3/2.1 mss:1448 cwnd:10
    bytes_sent:184320 bytes_retrans:4096 retrans:3/28 send 10.2Mbps
```

- `rtt:11.3/2.1` is the smoothed round-trip time estimate and its variance (both in milliseconds), the direct inputs to the RTO calculation.
- `retrans:3/28` means 3 retransmissions occurred out of 28 segments sent on this connection so far — a small but nonzero retransmission rate, worth watching if it climbs.
- `rto:212` is the current retransmission timeout in milliseconds — how long the sender will wait for an ACK before assuming loss and retransmitting via the timeout path (as opposed to fast retransmit).

**Production usage example:** Site reliability teams script periodic `ss -ti` sampling against critical backend connections to build a lightweight retransmission-rate time series without deploying full packet capture infrastructure — a sudden jump in `retrans` counts against a specific backend is often the earliest available signal of a degrading network path or an overloaded host dropping packets.

**Common errors:** Reading `cwnd` (congestion window, covered fully in [§57](Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md)) as if it were related to reliability rather than congestion control — the two mechanisms share this same `ss -ti` output line but answer different questions (how much can I safely send right now, vs. did what I already sent arrive).

### 5.3 Simulating Packet Loss to Observe Retransmission Behavior

**Purpose:** Deliberately induce loss on a test interface to watch TCP's retransmission and recovery behavior in a controlled way.

**Syntax:**

```bash
sudo tc qdisc add dev <interface> root netem loss <percentage>%
```

**Example usage and expected output:**

```bash
$ sudo tc qdisc add dev eth0 root netem loss 5%
$ curl -o /dev/null -s -w 'time_total: %{time_total}\n' https://example.com
time_total: 1.842

$ sudo tc qdisc del dev eth0 root netem
$ curl -o /dev/null -s -w 'time_total: %{time_total}\n' https://example.com
time_total: 0.312
```

- Introducing artificial loss with `netem` causes visibly longer transfer times as TCP's retransmission logic (and, compounding it, the congestion-control backoff from [§57](Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md)) kicks in — this is a standard technique for testing an application's resilience to a degraded network path before it happens in production.

**Production usage example:** Platform and SRE teams use `tc netem` in staging environments to validate that timeouts, retry logic, and circuit breakers in application code behave sensibly under realistic loss and latency conditions, rather than discovering that behavior for the first time during a real network incident.

**Common errors:** Forgetting to remove the `netem` qdisc (`tc qdisc del ...`) after testing — a forgotten artificial-loss rule left on a shared or production-adjacent interface silently degrades every connection through it until someone traces the mystery slowness back to a stale `tc` rule.

## 6. Production Usage Notes

- Modern Linux TCP stacks default to **SACK enabled** (`net.ipv4.tcp_sack = 1`), which is a significant real-world performance factor — disabling it (rarely done deliberately, but seen with certain legacy middleboxes or misconfigured kernels) causes unnecessary retransmission of already-received data after any loss event, sometimes doubling recovery time on lossy paths.
- Retransmission timeout calculation uses **Karn's algorithm** in practice — RTT samples from retransmitted segments are excluded from the RTT estimate, because it's ambiguous whether the received ACK corresponds to the original transmission or the retransmission, and including it would corrupt the RTT/RTO calculation.
- High and rising retransmission rates on a specific backend or path are one of the most actionable early-warning signals available for network degradation — many production monitoring stacks ([§130](../Part15/Section-130-Part15-Alerting-on-Network-Layer-Signals.md)) track `retrans` counts per connection or per host as a leading indicator, ahead of visible application-level error rates.

## 7. Security Considerations

- Sequence numbers, while not a security mechanism by design, historically provided a thin layer of resistance to blind **TCP session hijacking/spoofing** — an off-path attacker without visibility into the actual sequence numbers in use cannot easily inject data into an established connection. Modern **randomized ISN generation** (rather than the predictable, incrementing ISNs used by very old TCP stacks) closes off a historical class of attacks that relied on guessing sequence numbers.
- An attacker who can observe traffic (on-path) can still forge acknowledgment numbers or inject RST/data segments with correct sequence numbers — this is precisely why TLS ([§65](../Part8/Section-65-Part8-TLS-SSL-Fundamentals-Handshake-Certificates-Cipher-Suites.md)), not TCP's sequence numbering, is the actual defense against tampering or injection for anything security-sensitive.
- Excessive, deliberately triggered retransmissions (forcing a target to repeatedly resend data, e.g., via an attacker selectively dropping ACKs) can be used as a resource-exhaustion or bandwidth-amplification technique in more sophisticated denial-of-service scenarios, though this is far less common than volumetric or SYN-flood-style attacks ([§88](../Part10/Section-88-Part10-DDoS-Attack-Types-and-Mitigation-Strategies.md)).

## 8. Common Troubleshooting Scenarios

| Symptom                                                        | Likely Cause                                                                    | Resolution Path                                                                                                       |
| ---------------------------------------------------------------- | -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| Throughput is much lower than expected bandwidth would suggest    | Retransmissions from packet loss, or unnecessarily conservative recovery         | Check `ss -ti` `retrans` counts and RTT; capture traffic to identify the source of loss ([§118](../Part14/Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md))                        |
| Occasional multi-second stalls in an otherwise fast connection    | Fast retransmit didn't trigger (too few packets in flight); recovery fell back to a full RTO wait | Investigate whether small/bursty traffic patterns are preventing 3 duplicate ACKs from accumulating; consider tuning application send patterns |
| High retransmission rate on one specific path/backend, not others | Path-specific loss — a failing link, an overloaded intermediate device, or MTU/fragmentation issues | Run `mtr`/traceroute ([§116](../Part14/Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md)) along that specific path to isolate which hop is introducing loss                        |
| Retransmissions visible but throughput still acceptable            | Low-level, tolerable loss rate; TCP is recovering correctly via fast retransmit | Usually not urgent — track the rate as a trend rather than treating an isolated low rate as an incident               |

## 9. Best Practices

- Monitor retransmission rate as a first-class network health metric, not just raw throughput or latency — it surfaces degradation earlier and more specifically than most application-level metrics.
- When debugging "slow but not broken" connections, check whether observed stalls correlate with fast-retransmit recovery (fast, small stutters) or full RTO timeouts (multi-second stalls) — the distinction changes where to focus remediation effort.
- Leave SACK enabled (the default on virtually all modern systems) unless a specific, documented compatibility reason requires disabling it — disabling SACK meaningfully worsens recovery behavior under loss.

## 10. Common Anti-Patterns / Mistakes

- **Treating any nonzero retransmission count as a critical incident.** A small, stable baseline retransmission rate is normal on real-world networks, particularly across the public internet or Wi-Fi links — the actionable signal is a rate that's unusually high or trending upward, not the mere presence of retransmissions.
- **Confusing application-level retries with TCP-level retransmissions when reading logs or dashboards.** They occur at completely different layers, have different causes, and require different remediation — conflating them leads to fixing the wrong layer.
- **Disabling SACK "for compatibility" without a specific documented reason.** This is a legacy workaround that, applied without cause today, actively worsens loss-recovery performance for no real benefit.

## 11. Interview Questions

**🎯 Beginner:** _"What is a TCP sequence number, and what is it used for?"_
**Model answer:** A sequence number identifies the byte-offset position of the first byte of data in a TCP segment within the overall data stream being sent. It lets the receiver reassemble data in the correct order and detect missing or duplicated data, which is the foundation of TCP's reliable, in-order delivery guarantee.
_What the interviewer is probing for:_ Basic correctness on what sequence numbers actually represent (byte offsets, not segment counts) — a common beginner confusion.

**🎯 Intermediate:** _"Explain the difference between fast retransmit and a timeout-based retransmission."_
**Model answer:** Fast retransmit is triggered when the sender receives three duplicate ACKs for the same byte offset — this implies a later segment arrived out of order, which means an earlier segment was likely lost, so the sender retransmits it immediately without waiting for a timer. A timeout-based retransmission occurs when no ACK arrives at all within the retransmission timeout (RTO), calculated from measured round-trip time and its variance — this is a slower recovery path, used as a fallback when there isn't enough subsequent traffic to generate three duplicate ACKs.
_What the interviewer is probing for:_ Understanding both recovery paths and, ideally, why one is faster than the other in practice.

**🎯 Senior:** _"A service's throughput has degraded, and you suspect packet loss. Walk me through how you'd confirm and quantify it."_
**Model answer:** I'd start with `ss -ti` on active connections to the affected backend to check the `retrans` counter and current RTT — a rising retransmission count relative to bytes sent is a strong signal. If that confirms loss, I'd capture traffic with `tcpdump` and look for `[TCP Retransmission]` markers and duplicate ACK patterns to see whether recovery is happening via fast retransmit (small stutters) or full RTO timeouts (larger stalls), since that changes the perceived severity. I'd then run `mtr` or traceroute along the specific path to try to isolate which hop is introducing the loss, since it could be anywhere from the local NIC to a congested upstream link. Finally, I'd correlate the timing of the loss with any known events — deployment, traffic spike, a specific backend host — to narrow the root cause rather than treating it as a purely network-layer mystery.
_What the interviewer is probing for:_ A structured, tool-by-tool diagnostic process rather than a single guess, and awareness that "packet loss" has to be quantified and localized, not just asserted.

**🎯 Architect:** _"You're designing a distributed system where nodes exchange large volumes of data over TCP across regions with meaningfully different, sometimes lossy, network paths. What reliability-related design decisions matter at the architecture level, beyond what TCP already gives you for free?"_
**Model answer:** TCP's reliability guarantees delivery of bytes on a single connection, but it doesn't protect against connection-level failures (a dropped connection mid-transfer still loses in-flight, unacknowledged application state that the application itself must be able to resume or retry). I'd design for idempotent, resumable transfers at the application layer — chunked transfers with checksums and resume offsets — so that a TCP-level failure (however TCP itself recovered internally, or ultimately gave up and reset) doesn't force a full retransfer from scratch. I'd also pay attention to how retransmission behavior differs across regions with different baseline RTT and loss characteristics — a fixed retry/timeout policy tuned for a low-latency intra-region path will misbehave (either giving up too early or masking real problems for too long) on a lossy, high-latency cross-region path, so timeout and retry policy should be informed by measured per-path characteristics rather than a single global constant. Finally, I'd instrument retransmission rate and RTT per path as first-class observability signals feeding into routing or failover decisions, not just raw application error rates, since transport-layer degradation is often the leading indicator.
_What the interviewer is probing for:_ Ability to reason about the boundary between what TCP's reliability actually guarantees (single-connection, byte-stream delivery) and what the application layer must still handle itself (idempotency, resumability, cross-path-aware tuning) in a distributed system.

## 12. Common Misconceptions

1. **"TCP sequence numbers count segments or packets."** They count individual bytes in the stream — a segment's sequence number is the byte-offset of its first byte, and its length determines the offset of the next segment.
2. **"Any retransmission means something is broken."** A low, stable rate of retransmission is normal on real networks and is TCP working exactly as designed — the concerning signal is an elevated or rising rate, not mere presence.
3. **"ACK numbers confirm exactly which segment arrived."** TCP's ACKs are cumulative — an ACK confirms everything up to that byte offset has arrived, not specifically which discrete segment(s) it corresponds to; SACK is what adds the ability to report non-contiguous received ranges.
4. **"Fast retransmit and timeout-based retransmission are the same mechanism."** They're distinct recovery paths with very different latency characteristics — fast retransmit is triggered by duplicate ACKs and is much quicker; RTO-based retransmission is the slower fallback when duplicate ACKs don't accumulate.

## 13. 🔑 Key Takeaways

- TCP sequence numbers track byte-offset position in the stream; acknowledgment numbers are cumulative confirmations of everything received contiguously up to that point.
- Loss is detected either via a retransmission timeout (RTO, calculated from measured RTT) or, faster, via three duplicate ACKs triggering fast retransmit.
- SACK lets receivers report specific missing gaps, letting senders retransmit only what's actually missing rather than everything after the first loss.
- Retransmission rate is one of the most useful early network-health signals available and should be monitored as a first-class metric, not just inferred from application symptoms.
- TCP's reliability guarantees byte-stream delivery on a single connection — it does not solve application-level resumability or idempotency after a connection-level failure, which remains the application's responsibility.

## 14. Related Concepts & What's Next

[§57](Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md) continues directly from this section's RTT measurement and loss-detection mechanics to explain how TCP paces its sending rate via flow control (the receiver's advertised window) and congestion control (the sender's self-imposed congestion window), including how a retransmission event specifically triggers congestion-control backoff. [§61](Section-61-Part7-Connection-States-and-the-TCP-State-Machine-LISTEN-ESTABLISHED-TIME-WAIT.md) places the ESTABLISHED-state behavior described here into the context of the full TCP state machine. [§118](../Part14/Section-118-Part14-Packet-Capture-Fundamentals-tcpdump-Basics.md) and [§119](../Part14/Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md) (Part 14) build out the packet-capture and Wireshark skills exercised in this section's hands-on work into a complete diagnostic methodology.

**Next Section:** [§57](Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md) — `Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md`
