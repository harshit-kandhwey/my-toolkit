# Section 116 (Part 14): Connectivity Testing: ping, traceroute/tracert, mtr

## 1. Definition

**Plain language:** Before assuming a remote host is unreachable, three tools answer three progressively deeper questions: is it there at all (`ping`), what path does traffic take to get there (`traceroute`/`tracert`), and which specific hop along that path is dropping or slowing packets (`mtr`).

**Precise definition:** **`ping`** sends ICMP Echo Request messages to a target and reports whether and how quickly ICMP Echo Reply messages come back, providing a basic Layer 3 reachability and round-trip-time (RTT) measurement. **`traceroute`** (Linux/macOS) and **`tracert`** (Windows) discover the sequence of routers (hops) between the source and a destination by sending probes with incrementing Time-To-Live (TTL) values and recording the ICMP Time Exceeded message each router sends back as the TTL expires at each hop, reconstructing the path one hop at a time. **`mtr`** ("My Traceroute") combines both techniques into a single continuously-updating tool: it performs a traceroute-style hop discovery but then keeps sending probes to every hop on the path indefinitely, providing running packet-loss and latency statistics per hop rather than a single snapshot.

> 💡 **Tip:** `ping` answers "can I reach it," `traceroute`/`tracert` answers "what's the path," and `mtr` answers "where exactly on that path is the problem" — reach for them in that order of increasing specificity, not `mtr` first for every question.

## 2. Why This Matters

- **These three tools are the most universally available network diagnostics in existence** — present on essentially every OS from a bare Linux container to a Windows laptop, making them the lowest-common-denominator first response to almost any connectivity report.
- **They provide Layer 3 evidence independent of any application-level assumption** — they work identically whether the target is a database server, a load balancer, or a router, which makes them the natural first step in the OSI-layer walkthrough from [§115](Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md).
- **`traceroute`/`mtr`'s hop-by-hop view is often the only way to distinguish "my network is fine, theirs is broken" from "the problem is somewhere in the middle,"** which directly determines whether a fix is even within your organization's control.
- **Per-hop packet loss and latency spikes shown by `mtr` are frequently the first hard evidence of a degrading link, an overloaded router, or an ISP peering issue** — long before those show up as user-facing symptoms elsewhere.
- **Interpreting these tools correctly (recognizing ICMP rate-limiting and deprioritization) prevents a very common false alarm**: high or dropped-looking ping/traceroute results at intermediate hops that do not actually indicate a real problem for the rest of the path.

## 3. Prerequisites and Dependencies

This section builds on the ICMP-adjacent Layer 3 reachability concepts implicit in routing fundamentals ([§25](../Part4/Section-25-Part4-What-Routing-Is-Routers-vs-Switches-vs-Hosts.md)-[§28](../Part4/Section-28-Part4-Default-Routes-Null-Routes-and-Route-Summarization.md)) and depends on understanding TTL and IP addressing from Part 3 ([§15](../Part3/Section-15-Part3-IPv4-Address-Structure-Binary-Dotted-Decimal-and-Address-Classes.md)-[§24](../Part3/Section-24-Part3-DHCP-Lease-Lifecycle-Relay-and-Options.md)) and Part 4, since both tools work by manipulating the IP header's TTL field. It follows directly from [§115](Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md)'s methodology, supplying the concrete Layer 3 tools for the reachability-testing step of that walk. Familiarity with [§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md) (BGP/path-vector routing) is useful context for why a traceroute path can legitimately change between runs (asymmetric or load-balanced routing across multiple upstream links), a point revisited in more depth in [§121](Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md).

## 4. Architecture / Conceptual Diagram

```text
   TRACEROUTE / TRACERT MECHANISM (TTL-expiry probing)

   Source                Hop 1            Hop 2            Destination
     │  probe TTL=1        │                │                    │
     │─────────────────────►│ TTL expires,   │                    │
     │◄─────────────────────│ sends ICMP     │                    │
     │  "Time Exceeded"      Time Exceeded   │                    │
     │                                       │                    │
     │  probe TTL=2                          │                    │
     │──────────────────────────────────────►│ TTL expires here   │
     │◄──────────────────────────────────────│ ICMP Time Exceeded │
     │                                       │                    │
     │  probe TTL=3 (reaches destination)                         │
     │────────────────────────────────────────────────────────────►│
     │◄────────────────────────────────────────────────────────────│
     │              ICMP Echo Reply / port-unreachable                │

   Each increment of TTL reveals one more hop; the process repeats
   until a probe reaches the actual destination.

   MTR: same TTL-probing technique, but continuous per-hop stats

   Hop  Address           Loss%   Avg    Best    Worst
   1    10.0.1.1           0.0%   0.4ms  0.3ms   0.6ms
   2    203.0.113.1        0.0%   1.2ms  0.9ms   2.1ms
   3    198.51.100.9      12.0%  45.3ms  40.1ms  89.4ms   ◄── suspect hop
   4    <target host>      0.0%  46.1ms  41.0ms  90.2ms
```

- Loss showing up at an intermediate hop but **not** at the final destination hop (as at hop 3 above) usually indicates that intermediate router is deprioritizing or rate-limiting the ICMP replies it generates about itself — not that real traffic passing through it is actually being lost, since the router still forwards the packets on to later hops successfully.
- Loss that appears at an intermediate hop **and persists at every hop after it** is a much stronger signal of a genuine problem at or immediately after that hop.
- Both `traceroute` and `mtr` reveal the **forward path only** — the return path (from destination back to source) is invisible to these tools and can differ entirely, which matters directly for [§121](Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md)'s asymmetric routing discussion.

## 5. Hands-On

### 5.1 Basic Reachability and RTT With `ping`

**Purpose:** Confirm Layer 3 reachability to a target and get a first read on latency and packet loss.

**Syntax:**

```bash
ping -c <count> <destination>
ping -t <destination>          # Windows: continuous ping (Ctrl+C to stop)
```

**Example usage and expected output:**

```bash
$ ping -c 4 10.0.4.15
PING 10.0.4.15 (10.0.4.15) 56(84) bytes of data.
64 bytes from 10.0.4.15: icmp_seq=1 ttl=63 time=0.412 ms
64 bytes from 10.0.4.15: icmp_seq=2 ttl=63 time=0.389 ms
64 bytes from 10.0.4.15: icmp_seq=3 ttl=63 time=0.401 ms
64 bytes from 10.0.4.15: icmp_seq=4 ttl=63 time=0.395 ms

--- 10.0.4.15 ping statistics ---
4 packets transmitted, 4 received, 0% packet loss, time 3054ms
rtt min/avg/max/mdev = 0.389/0.399/0.412/0.010 ms
```

**Production usage example:** A sub-millisecond, 0%-loss result like this against a host in the same subnet confirms Layer 1-3 are fully healthy for that path, which immediately shifts a "can't connect" investigation up to Layer 4/7 ([§117](Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md)) rather than continuing to suspect the network fabric.

**Common errors:** Concluding "the host is down" from a failed ping when ICMP is simply blocked by a security group or host firewall while the actual service (e.g., TCP 443) is perfectly reachable — always corroborate with a port-level test ([§117](Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md)) before declaring a host unreachable based on ping alone.

### 5.2 Discovering the Path With `traceroute` / `tracert`

**Purpose:** Enumerate the routers between source and destination to see where a path diverges from expectation or where it terminates unexpectedly.

**Syntax:**

```bash
traceroute <destination>        # Linux/macOS
tracert <destination>           # Windows
```

**Example usage and expected output:**

```bash
$ traceroute example.com
traceroute to example.com (93.184.216.34), 30 hops max, 60 byte packets
 1  10.0.1.1 (10.0.1.1)  0.412 ms  0.389 ms  0.371 ms
 2  203.0.113.1 (203.0.113.1)  1.204 ms  1.150 ms  1.198 ms
 3  * * *
 4  198.51.100.9 (198.51.100.9)  14.302 ms  13.998 ms  14.511 ms
 5  93.184.216.34 (93.184.216.34)  15.001 ms  14.887 ms  14.902 ms
```

**Production usage example:** The `* * *` at hop 3 with valid responses continuing at hop 4 and a successful arrival at hop 5 is the classic signature of a router that simply doesn't respond to the TTL-expiry probes (often deliberately, for security or load reasons) but still forwards traffic normally — this is a routine, expected result and not itself evidence of a problem, an important distinction to make before escalating.

**Common errors:** Treating every `* * *` line as proof of an outage at that hop — the correct read is "this hop did not reply to the probe," which is different from "this hop is dropping the traffic," and only a persistent failure to reach any hop beyond that point (including the final destination) indicates a genuine break in the path.

### 5.3 Continuous Per-Hop Diagnosis With `mtr`

**Purpose:** Identify exactly which hop on a path is introducing loss or latency, using continuously updated statistics rather than a single traceroute snapshot.

**Syntax:**

```bash
mtr --report --report-cycles <n> <destination>
mtr -n <destination>            # interactive mode, numeric output only
```

**Example usage and expected output:**

```bash
$ mtr --report --report-cycles 20 -n 198.51.100.20
Start: 2026-09-14T10:02:11+0000
HOST: my-host                    Loss%   Snt   Last   Avg  Best  Wrst StDev
  1.|-- 10.0.1.1                  0.0%    20    0.4   0.4   0.3   0.6   0.1
  2.|-- 203.0.113.1                0.0%    20    1.2   1.3   0.9   2.1   0.3
  3.|-- 198.51.100.9              15.0%    20   44.1  45.3  40.1  89.4  12.2
  4.|-- 198.51.100.20              0.0%    20   45.9  46.1  41.0  90.2  10.9
```

**Production usage example:** This exact report — real loss at hop 3 but 0% loss at the final destination (hop 4) — is presented as evidence when opening a ticket with an upstream ISP or transit provider, since it demonstrates the problem lies specifically at their infrastructure and not at your own edge or the destination's; most transit providers require exactly this kind of per-hop evidence before investigating.

**Common errors:** Running `mtr` for only a few cycles and drawing conclusions from a short sample — transient network events can produce a misleading single-cycle result; running with `--report-cycles` set to at least 20-50 (or running interactively for a few minutes) gives statistically meaningful loss percentages rather than noise.

## 6. Production Usage Notes

- Many cloud provider security groups and network ACLs block inbound ICMP by default while still allowing the relevant TCP/UDP application traffic — a failed `ping` against a cloud VM is often expected behavior, not a fault, and should not by itself be treated as an outage signal in cloud environments.
- `traceroute` on Linux defaults to UDP probes to high, typically-unused ports (relying on the destination's ICMP port-unreachable reply to detect arrival), while `tracert` on Windows defaults to ICMP Echo probes — this difference means the two tools can behave differently against the same destination if UDP and ICMP are filtered inconsistently, which is worth knowing when comparing results across a mixed OS fleet.
- Automating periodic `mtr` reports (or an equivalent synthetic check) between key infrastructure pairs — for example, between regions or between an on-prem data center and a cloud VPC — establishes a latency/loss baseline that makes anomalies detectable immediately rather than only after a user complaint.

## 7. Security Considerations

- ICMP is commonly rate-limited or entirely blocked at network boundaries specifically to reduce the effectiveness of network reconnaissance and to blunt certain classes of denial-of-service technique — this is a deliberate security posture, and its side effect (ping/traceroute appearing to "fail" against a perfectly healthy host) should be expected rather than treated as suspicious.
- `traceroute`/`mtr` output reveals internal network topology (private router IPs, hop counts, internal addressing schemes) — sharing raw traceroute output externally (in a public support ticket, for instance) can leak information about internal network architecture that would otherwise not be exposed.
- Because these tools are lightweight and universally available, they are also commonly used as reconnaissance tools by attackers mapping a target's network — high-volume ICMP or traceroute-style probing from a single external source is a signal worth including in network intrusion detection ([§87](../Part10/Section-87-Part10-Intrusion-Detection-Prevention-Systems-IDS-IPS-Conceptual-Overview.md)).

## 8. Common Troubleshooting Scenarios

| Symptom                                                     | Likely Cause                                                                   | Resolution Path                                                                                                  |
| -------------------------------------------------------------- | ------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `ping` fails but the application connects fine                 | ICMP blocked by a security group/firewall while the application port is open   | Confirm with `nc -zv`/`curl -v` ([§117](Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md)); treat the failed ping as expected, not a fault                             |
| `traceroute` shows `* * *` at one hop, then continues normally  | Intermediate router doesn't reply to TTL-expiry probes but forwards traffic fine | No action needed if the path completes and reaches the destination; this is routine, not a fault                  |
| `mtr` shows sustained loss at one hop and every hop after it    | Real congestion or a failing link at or immediately after that hop             | Escalate to the network/ISP owning that hop with the `mtr` report as evidence; consider a path/route change if possible |
| `ping`/`traceroute` results differ across repeated runs         | Load-balanced/multi-path routing (ECMP) or asymmetric routing across upstreams | Run several samples over time before drawing conclusions; cross-reference with [§121](Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md) for path-instability causes    |

## 9. Best Practices

- Use `ping` for a fast first-pass reachability check, `traceroute`/`tracert` for a one-time path snapshot, and `mtr` when you need statistically meaningful loss/latency evidence over time — matching the tool to the depth of question actually being asked avoids wasted effort.
- Always run several cycles/samples before concluding a hop is genuinely faulty; a single lost probe is noise, not evidence.
- When escalating a network issue to an upstream provider or another team, always attach an `mtr` report rather than a single `ping` or `traceroute` — it is the format most network operators expect and trust as evidence.

## 10. Common Anti-Patterns / Mistakes

- **Treating a failed `ping` against a cloud instance as proof the instance is down.** Default security-group posture in every major cloud provider frequently blocks ICMP while leaving application ports open — verify with a port-level test before escalating.
- **Interpreting a single `* * *` hop in `traceroute` as a network outage.** As shown in 5.2, this commonly reflects a router declining to reply to probes, not a break in the path — only a failure to progress past that hop (including at the final destination) indicates a real problem.
- **Drawing conclusions from one `mtr` cycle or one `traceroute` run.** Transient blips are common; always sample over a meaningful window before escalating or making infrastructure changes based on the result.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `ping` and `traceroute`?"_
**Model answer:** `ping` tests whether a destination is reachable and measures round-trip time by sending ICMP Echo Requests and waiting for Echo Replies — it gives a single reachability/latency data point for the whole path. `traceroute` discovers the actual sequence of routers between source and destination by sending probes with increasing TTL values, so each router along the way replies once its TTL expires — it maps the path rather than just confirming the endpoint is reachable.
_What the interviewer is probing for:_ Basic, accurate understanding of what each tool actually measures.

**🎯 Intermediate:** _"You run `mtr` and see 20% loss at hop 4, but 0% loss at the final destination (hop 8). What does this mean, and what would you do next?"_
**Model answer:** This is the classic signature of a router that deprioritizes or rate-limits the ICMP Time Exceeded replies it generates about itself, while continuing to forward the actual traffic through to later hops without loss — the loss shown at hop 4 is about that router's replies to the probe, not necessarily about traffic passing through it. Since loss doesn't persist at the final destination, I would not treat this as an active outage; I'd note it, run a longer `mtr` sample to confirm the pattern is stable, and only escalate if loss also started appearing at hop 8 or if users reported real symptoms correlated with this hop.
_What the interviewer is probing for:_ Correct interpretation of intermediate-hop artifacts versus genuine end-to-end problems — a very common point of confusion.

**🎯 Senior:** _"A remote office reports intermittent slowness to a service in another region, but pings look fine most of the time. How would you use these tools to build a case?"_
**Model answer:** A single ping snapshot is unlikely to catch an intermittent issue, so I'd run a long-duration `mtr` (report-cycles in the hundreds, or run interactively over an extended window overlapping the reported slow periods) to capture loss/latency statistics across the whole sampling window rather than a point-in-time check. I'd correlate spikes in the `mtr` data against the times the office reported slowness. If the path is asymmetric or multi-path (common with ECMP or multiple ISP uplinks), I'd also run `traceroute` multiple times to see whether the path itself is changing between samples, since an unstable path can produce exactly this kind of intermittent symptom even when a single test looks clean ([§121](Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md) covers this pattern in depth). I'd present the aggregated, time-correlated `mtr` data as the evidence base for further escalation.
_What the interviewer is probing for:_ Understanding that intermittent problems require sustained sampling, not single-shot tools, and awareness of path instability as a root cause.

**🎯 Architect:** _"How would you design ongoing, automated use of these tools across a multi-region infrastructure to catch network degradation before users report it?"_
**Model answer:** I'd deploy lightweight synthetic-monitoring agents in each region (or key network segment) that continuously run `mtr`-style probes against a fixed set of critical internal and external destinations (other regions, key third-party dependencies, DNS resolvers), on a schedule frequent enough to catch transient issues but light enough not to itself generate noticeable load. I'd feed per-hop loss and latency data into a time-series monitoring system with baseline-deviation alerting, so a sustained increase in loss or latency at a specific hop triggers an alert well before it manifests as user-facing symptoms — this connects directly into the network observability practices covered later in Part 15 ([§124](../Part15/Section-124-Part15-Network-Performance-Metrics-Latency-Jitter-Packet-Loss-Throughput.md)-[§130](../Part15/Section-130-Part15-Alerting-on-Network-Layer-Signals.md)). I'd deliberately avoid alerting on single-cycle spikes (to prevent alert fatigue from routine ICMP deprioritization artifacts) and instead alert on sustained, multi-sample degradation, mirroring the "don't trust one `mtr` cycle" lesson from hands-on use of the tool.
_What the interviewer is probing for:_ Ability to scale a manual diagnostic technique into automated, proactive infrastructure monitoring, with attention to avoiding false-positive noise.

## 12. Common Misconceptions

1. **"A failed ping always means the host is unreachable."** ICMP is frequently and deliberately blocked while the actual service remains fully reachable — this is one of the most common false alarms in cloud environments.
2. **"`* * *` in a traceroute means that hop, and everything past it, is broken."** It often just means that one router doesn't reply to probes; the path frequently continues working normally beyond it.
3. **"Traceroute/mtr show the round-trip path."** They show the forward path from source to destination only — the return path can differ entirely, and this asymmetry is itself a common root cause investigated in [§121](Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md).
4. **"One `mtr` cycle or one `traceroute` run is enough evidence to escalate a network issue."** Transient, single-sample results are frequently noise; meaningful evidence requires sampling over a longer window.

## 13. 🔑 Key Takeaways

- `ping`, `traceroute`/`tracert`, and `mtr` answer three progressively more specific questions: reachable at all, what path, and which specific hop is the problem.
- Loss or non-response at an intermediate hop that does not persist to the final destination is usually a benign artifact of ICMP deprioritization, not a real fault.
- These tools reveal only the forward path; the return path can differ, which matters for diagnosing asymmetric routing.
- Always sample over multiple runs/cycles before drawing conclusions or escalating — single-shot results are frequently misleading.

## 14. Related Concepts & What's Next

[§115](Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md)'s OSI-layer methodology frames when in a troubleshooting session these tools get used; [§121](Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md) revisits the path-instability and asymmetric-routing patterns these tools can reveal in much greater depth. [§117](Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md) continues the layer walk upward from Layer 3 reachability (this section's focus) into Layer 4/7 port and service testing, which is the next question to ask once basic connectivity is confirmed. [§32](../Part4/Section-32-Part4-Path-Vector-Protocols-BGP-Concepts-and-Why-the-Internet-Runs-on-It.md)'s BGP/path-vector routing concepts explain the underlying reason paths can legitimately change between traceroute runs on the public internet.

**Next Section:** [§117](Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md) — `Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md`
