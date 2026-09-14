# Section 118 (Part 14): Packet Capture Fundamentals: tcpdump Basics

## 1. Definition

**Plain language:** When higher-level tools (`ping`, `curl`, application logs) tell you *that* something is wrong but not *why*, the only way to get ground truth is to look at the actual bytes crossing the wire. `tcpdump` captures those bytes in real time and prints (or saves) them in a human-readable summary.

**Precise definition:** **`tcpdump`** is a command-line packet-capture and analysis tool that uses a kernel-level packet-capture facility (`libpcap` on Unix-like systems, the same underlying library Wireshark uses) to copy packets passing through a specified network interface, optionally filtering them using the **Berkeley Packet Filter (BPF)** expression syntax, and print a one-line (or, with increasing verbosity flags, multi-line/hex) summary of each matching packet's headers and, optionally, payload. Because it operates below the application layer, `tcpdump` shows exactly what left or arrived at the network interface — independent of what any application, proxy, or higher-level tool claims happened — making it the definitive source of truth when other tools' reports conflict or seem implausible.

> 💡 **Tip:** `tcpdump`'s BPF filter syntax (`host`, `port`, `tcp`, `and`/`or`, and expressions like `tcp[tcpflags] & tcp-syn != 0`) is worth memorizing incrementally rather than all at once — start with `host` and `port` filters, which cover the large majority of real troubleshooting needs, and add flag-level filters only when a specific investigation needs them.

## 2. Why This Matters

- **It is the ultimate tie-breaker in any dispute between two tools' or two teams' accounts of what happened on the network** — an application log claiming "request sent" and a downstream service claiming "never received" can only be definitively resolved by a capture showing whether the packet actually left the sending host's interface.
- **It reveals problems invisible to every higher-level tool**, including retransmissions, out-of-order packets, malformed headers, unexpected RSTs, and asymmetric traffic patterns — none of which show up in a `curl` or `ping` result, which only report the end outcome.
- **It requires understanding of the protocol headers built up across the rest of this roadmap** (Ethernet, IP, TCP/UDP headers) to be useful at all — this is where that layered knowledge becomes directly, tangibly applicable.
- **It is available on effectively every Linux/Unix host and inside most containers with the right capabilities**, making it usable in production incident response without installing new software in most cases.
- **It is the foundation Wireshark ([§119](Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md)) builds on** — the same `libpcap` capture engine and the same BPF filter syntax carry directly over, so fluency here transfers immediately.

## 3. Prerequisites and Dependencies

This section requires solid familiarity with the TCP header and flag concepts from [§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md)-[§57](../Part7/Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md) and the encapsulation/PDU model from [§10](../Part2/Section-10-Part2-Encapsulation-and-De-Encapsulation-Across-Layers.md)-[§11](../Part2/Section-11-Part2-PDUs-at-Each-Layer-Bits-Frames-Packets-Segments-Data.md), since reading `tcpdump` output is fundamentally an exercise in recognizing those headers in compact textual form. It follows [§117](Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md) in the troubleshooting escalation path from [§115](Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md) — packet capture is the tool reached for once port- and protocol-level testing has narrowed a problem but not fully explained it. It assumes comfort with basic Linux command-line usage (per this roadmap's stated baseline) and directly sets up [§119](Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md)'s deeper Wireshark-based analysis, which operates on the same captured packet data via a graphical interface and more powerful filter/analysis tooling.

## 4. Architecture / Conceptual Diagram

```text
   WHERE tcpdump SITS IN THE STACK

   Application  ──┐
   Transport    ──┤   these are what higher-level tools (curl,
   Network      ──┤   application logs) REPORT about
   Data Link    ──┘
        │
        ▼
   Network Interface Card (NIC)
        │
        ▼
   libpcap / kernel capture facility  ◄── tcpdump reads HERE,
        │                                  below every application's
        ▼                                  own claims about what happened
   Physical wire / virtual network fabric


   TYPICAL tcpdump WORKFLOW

   1. Identify interface & narrow filter   (host, port, protocol)
        │
        ▼
   2. Capture live OR write to a .pcap file for later analysis
        │                                        │
        ▼                                        ▼
   3. Read one-line summaries            4. Open the .pcap in
      directly in the terminal              Wireshark (§119) for
      for quick checks                      deep, graphical analysis
```

- `tcpdump` captures at the interface level, which means a capture taken on one host only shows traffic that host's NIC actually saw — a packet dropped by an upstream firewall before reaching this host will simply never appear, which is itself diagnostic information (absence of evidence at this hop, when corroborated by "it was sent" evidence upstream, points squarely at whatever sits between the two capture points).
- Writing to a `.pcap` file (`-w`) rather than only printing to the terminal decouples *capturing* from *analyzing* — this matters enormously for capturing a rare, intermittent event now and analyzing it carefully (potentially in Wireshark, [§119](Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md)) later, without needing to catch and interpret it in real time.
- BPF filters are applied as early and as efficiently as possible (often partially in the kernel itself) specifically so that capturing on a busy production interface with a narrow filter has minimal performance impact compared to capturing everything.

## 5. Hands-On

### 5.1 Basic Host- and Port-Filtered Capture

**Purpose:** Capture only the traffic relevant to a specific investigation, avoiding the noise of unrelated traffic on a busy interface.

**Syntax:**

```bash
sudo tcpdump -i <interface> host <ip-or-hostname> and port <port> -n
```

**Example usage and expected output:**

```bash
$ sudo tcpdump -i eth0 host 10.0.4.15 and port 443 -n
14:22:01.100112 IP 10.0.1.15.51888 > 10.0.4.15.443: Flags [S], seq 129873, win 64240, length 0
14:22:01.100540 IP 10.0.4.15.443 > 10.0.1.15.51888: Flags [S.], seq 887123, ack 129874, win 65535, length 0
14:22:01.100601 IP 10.0.1.15.51888 > 10.0.4.15.443: Flags [.], seq 129874, ack 887124, win 64240, length 0
14:22:01.102203 IP 10.0.1.15.51888 > 10.0.4.15.443: Flags [P.], seq 129874:129950, ack 887124, win 64240, length 76
```

- `-n` disables reverse DNS lookups on captured addresses — without it, `tcpdump` tries to resolve every IP, which is both slow and can itself generate confusing extra traffic during the capture.
- `Flags [P.]` marks a PUSH+ACK segment carrying actual application data (`length 76`) — this is the point in the capture where you'd correlate against the specific request the application claims to have sent.

**Production usage example:** This exact filter pattern (a specific host plus a specific port) is the default starting capture for almost any "this one connection is misbehaving" investigation — narrow enough to be readable in real time, broad enough to see the full handshake, data exchange, and teardown for that one flow.

**Common errors:** Forgetting `sudo`/root privileges — packet capture requires elevated access on essentially every OS since it involves putting the interface into a mode that can observe traffic not addressed to the capturing process itself, and the resulting permission-denied error is sometimes mistaken for a tooling problem rather than a simple privilege issue.

### 5.2 Filtering by TCP Flags

**Purpose:** Isolate specific stages of a TCP conversation — handshakes, teardowns, or resets — out of a busy capture, rather than reading every packet.

**Syntax:**

```bash
sudo tcpdump -i <interface> 'tcp[tcpflags] & (tcp-syn|tcp-rst) != 0' -n
```

**Example usage and expected output:**

```bash
$ sudo tcpdump -i eth0 'tcp[tcpflags] & tcp-rst != 0' -n
14:25:11.883012 IP 10.0.4.20.5432 > 10.0.1.15.52011: Flags [R.], seq 4021, ack 118, win 0, length 0
14:25:44.201553 IP 10.0.4.20.5432 > 10.0.1.15.52344: Flags [R.], seq 8812, ack 220, win 0, length 0
```

**Production usage example:** Filtering for bare RST segments against a specific backend port is the standard technique for confirming a suspected connection-pool exhaustion or idle-timeout mismatch issue ([§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md), [§61](../Part7/Section-61-Part7-Connection-States-and-the-TCP-State-Machine-LISTEN-ESTABLISHED-TIME-WAIT.md)) — a steady stream of RSTs from the database's port during a reported "connection reset" incident confirms the database (or something in front of it) is actively terminating connections rather than the application misbehaving on its own.

**Common errors:** Writing the BPF flag expression incorrectly (a common mistake is `tcp-syn or tcp-rst` as a bare boolean rather than the correct bitwise form `tcp[tcpflags] & (tcp-syn|tcp-rst) != 0`) — `tcpdump`'s flag-matching requires this specific bitmask syntax because TCP flags are packed into a single header byte, not separate fields.

### 5.3 Writing Captures to a File for Later Analysis

**Purpose:** Capture traffic for a rare or intermittent event without needing to watch and interpret it live, and enable deeper offline analysis (including in Wireshark, [§119](Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md)).

**Syntax:**

```bash
sudo tcpdump -i <interface> -w <file>.pcap <filter-expression>
sudo tcpdump -r <file>.pcap -n     # read back later
```

**Example usage and expected output:**

```bash
$ sudo tcpdump -i eth0 -w /tmp/incident-2026-09-14.pcap host 10.0.4.15
tcpdump: listening on eth0, link-type EN10MB (Ethernet), capture size 262144 bytes
^C
1042 packets captured
1042 packets received by filter
0 packets dropped by kernel

$ sudo tcpdump -r /tmp/incident-2026-09-14.pcap -n port 443 | head -5
14:22:01.100112 IP 10.0.1.15.51888 > 10.0.4.15.443: Flags [S], seq 129873, win 64240, length 0
...
```

**Production usage example:** During an active incident where the root cause isn't yet known, starting a broad `-w` capture immediately (even before narrowing the filter) and only refining the analysis afterward is standard practice — it's far better to capture too much and filter during analysis than to under-capture and miss the one relevant packet because the live filter was too narrow.

**Common errors:** Letting an unfiltered, long-running capture fill available disk space on a production host — always combine `-w` with either a tight filter, a size limit (`-C` to rotate files by size), or a time-boxed capture window, especially on hosts with limited local storage.

## 6. Production Usage Notes

- On cloud instances, packet capture only sees traffic that has already passed through (or is about to pass through) the instance's own virtual NIC — it cannot see traffic dropped upstream by a security group, network ACL, or the cloud provider's own network fabric, so a capture showing "nothing arrived" on the destination host is consistent with either an application-side listener problem or an upstream cloud-network drop, and cloud console/flow-log evidence ([§108](../Part12/Section-108-Part12-Multi-Region-and-Multi-Cloud-Networking-Considerations.md), [§124](../Part15/Section-124-Part15-Network-Performance-Metrics-Latency-Jitter-Packet-Loss-Throughput.md)-[§130](../Part15/Section-130-Part15-Alerting-on-Network-Layer-Signals.md)) is needed to distinguish them.
- Capturing on both ends of a suspect connection simultaneously (client and server) and comparing the two captures is one of the most powerful techniques available — if a SYN is visible leaving the client's interface but never arrives at the server's, the problem is definitively located somewhere in between.
- Running `tcpdump` inside a container typically requires the `NET_ADMIN` and `NET_RAW` capabilities (or `--privileged`, which is broader than necessary) — teams that expect to need in-container packet capture should plan for granting these specific capabilities rather than defaulting to full privileged mode.

## 7. Security Considerations

- Packet captures can contain sensitive data in cleartext for any unencrypted protocol, and even for encrypted protocols they still reveal metadata (source/destination, timing, packet sizes) — captures should be treated as sensitive artifacts, stored securely, and deleted once no longer needed for the investigation.
- Capturing traffic requires elevated privileges precisely because unrestricted packet capture is a powerful surveillance capability — access to run `tcpdump` (or equivalent capture tools) on production hosts should be governed by the same access controls and audit logging as other sensitive administrative actions.
- A capture filter that is too broad on a shared or multi-tenant host can inadvertently capture other tenants' or teams' traffic — scope capture filters as narrowly as the investigation allows, and be aware of organizational policy on what can legitimately be captured.

## 8. Common Troubleshooting Scenarios

| Symptom                                                     | Likely Cause                                                              | Resolution Path                                                                                          |
| -------------------------------------------------------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| `tcpdump` shows nothing at all for expected traffic            | Wrong interface specified, or traffic genuinely never reaches this host    | Confirm interface name (`ip link`); capture on an upstream hop to see where the traffic actually stops    |
| Client-side capture shows SYN sent, server-side shows nothing  | Something between the two hosts is dropping the SYN silently               | Investigate firewall/security-group/NACL rules on the path ([§82](../Part10/Section-82-Part10-Firewall-Fundamentals-Stateless-vs-Stateful-Filtering.md)-[§90](../Part10/Section-90-Part10-Network-Access-Control-Lists-and-Micro-Segmentation.md)) between the two capture points        |
| Capture shows repeated retransmissions of the same segment     | Packet loss on the path, or the receiver's ACKs aren't arriving back       | Check for asymmetric routing ([§121](Section-121-Part14-Routing-and-Path-Troubleshooting-Asymmetric-Routing-Route-Leaks.md)) or a lossy link with `mtr` ([§116](Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md)); inspect for MTU issues ([§122](Section-122-Part14-MTU-Issues-and-Path-MTU-Discovery.md))      |
| "Permission denied" when starting a capture                    | Insufficient privileges (not root, or missing NET_ADMIN/NET_RAW in a container) | Re-run with `sudo`, or grant the required capabilities to the container                                   |

## 9. Best Practices

- Default to a narrow filter (specific host and port) whenever the target of the investigation is already known — this keeps output readable and avoids unnecessary load on busy interfaces.
- When the root cause isn't yet known, start a broad, time-boxed capture written to a file immediately rather than waiting to construct the perfect filter — filtering during offline analysis is easy; missing the one relevant packet because live filtering was too aggressive is not recoverable.
- Capture simultaneously at both ends of a suspect path whenever feasible — the comparison between two vantage points is often more informative than either capture alone.

## 10. Common Anti-Patterns / Mistakes

- **Running an unfiltered, unbounded capture on a busy production interface.** This risks filling disk space, generating unmanageable output volume, and adding unnecessary load — always scope with a filter, a size/count limit, or both.
- **Capturing only on one end of a two-host problem.** A single-sided capture often can't distinguish "never sent" from "sent but never arrived" — capturing both sides resolves this ambiguity directly.
- **Treating "no packets captured" as proof nothing was sent.** It may instead mean the filter or interface is wrong, or that the traffic was dropped before reaching this host's NIC at all — verify the capture setup itself before drawing conclusions from an empty result.

## 11. Interview Questions

**🎯 Beginner:** _"What is `tcpdump` used for, and why does it need elevated privileges to run?"_
**Model answer:** `tcpdump` captures raw packets passing through a network interface so you can inspect exactly what's happening on the wire, independent of what any application or higher-level tool reports. It needs elevated privileges because capturing traffic not specifically addressed to the running process is a powerful capability — without that restriction, any unprivileged process could eavesdrop on all traffic crossing a shared interface.
_What the interviewer is probing for:_ Basic understanding of the tool's purpose and why the OS gates it behind privilege.

**🎯 Intermediate:** _"You suspect a firewall is silently dropping SYN packets between two hosts. How would you use `tcpdump` to confirm this?"_
**Model answer:** I'd start captures simultaneously on both the client and the server, filtered to the relevant host/port pair, and initiate the connection attempt. If the SYN appears in the client-side capture (confirming it left the client) but never appears in the server-side capture, that proves something between the two hosts — most likely a firewall, security group, or NACL — is silently dropping the packet rather than the server simply not responding. If the SYN appears on both ends but no SYN-ACK comes back, the problem is instead that the server (or something between server and client on the return path) isn't responding, which is a different root cause.
_What the interviewer is probing for:_ The dual-capture technique and correct interpretation of what presence/absence at each end actually proves.

**🎯 Senior:** _"A production service is seeing intermittent timeouts under load. How would you use tcpdump to investigate without adding significant overhead to the system?"_
**Model answer:** I'd use a narrow BPF filter (specific host and port, or specific flag combinations like retransmission indicators) rather than an unfiltered capture, since filtering happens efficiently close to the kernel and dramatically reduces both the volume captured and the processing overhead. I'd write to a file with a size-based rotation (`-C`) and a snap length limit (`-s`) to cap per-packet capture size if payload isn't needed, keeping only header information for most investigations. I'd time-box the capture to a window correlated with when timeouts are actually occurring (based on application metrics) rather than running indefinitely, and I'd specifically look for retransmissions and RSTs correlated with the load spike, which would point toward resource exhaustion (connection table, SYN backlog) rather than a purely network-path problem.
_What the interviewer is probing for:_ Practical awareness of capture overhead and the discipline to scope captures appropriately in a live production environment.

**🎯 Architect:** _"How would you build packet-capture capability into your incident response process at scale, across many hosts and services?"_
**Model answer:** I'd avoid relying on ad-hoc, manually-triggered captures as the only mechanism, since by the time an engineer starts a capture, the triggering event has often already passed. Instead, I'd invest in always-on, low-overhead rolling captures (a small ring buffer of recent traffic per host, using size- and time-based rotation) on critical services, so that when an incident is reported, recent history is already available to pull rather than needing to reproduce the issue live. I'd standardize capture tooling and storage (a common location, retention policy, and access-control model for `.pcap` files) so captures taken during an incident are handled consistently with the sensitivity concerns from Section 7. For routine, non-incident troubleshooting, I'd rely on the lighter-weight tools from [§116](Section-116-Part14-Connectivity-Testing-ping-traceroute-tracert-mtr.md)-[§117](Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md) first, reserving packet capture — with its greater overhead and sensitivity — for cases those tools can't fully resolve, and I'd pair capture capability directly with the Wireshark-based deeper analysis workflow in [§119](Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md) for cases requiring more than command-line summary output.
_What the interviewer is probing for:_ Strategic, proactive thinking about incident response tooling rather than only reactive, manual technique.

## 12. Common Misconceptions

1. **"`tcpdump` shows what the application did."** It shows what actually crossed the network interface — this can differ from what an application log claims, which is precisely what makes it valuable as an independent source of truth.
2. **"An empty capture proves nothing was sent."** It may instead indicate a wrong filter, wrong interface, or that the traffic was dropped before reaching this host — always verify capture setup before concluding "nothing happened."
3. **"Capturing everything with no filter is safer because you won't miss anything."** Unfiltered captures on busy interfaces can overwhelm both storage and the engineer trying to read the output — targeted filters (or filtered offline analysis of a broadly-captured file) are almost always the better approach.
4. **"`tcpdump` and Wireshark are unrelated tools."** They share the same underlying `libpcap` capture engine and largely the same filter concepts — `tcpdump` capture files open directly in Wireshark, and skills transfer directly between them ([§119](Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md)).

## 13. 🔑 Key Takeaways

- `tcpdump` provides ground-truth, on-the-wire evidence independent of what any application or higher-level tool reports — it is the tie-breaker when accounts of what happened conflict.
- BPF filters (`host`, `port`, TCP flag bitmasks) let a capture stay scoped and readable rather than overwhelming; writing to a file with `-w` decouples capturing from analysis.
- Capturing simultaneously at both ends of a suspect path is one of the most powerful available techniques for definitively localizing where traffic is being dropped.
- Packet captures are sensitive artifacts (potentially containing cleartext data and always containing metadata) and require the same access discipline as other sensitive administrative capabilities.

## 14. Related Concepts & What's Next

[§117](Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md) covers the higher-level port/protocol testing that typically precedes reaching for `tcpdump`, and [§115](Section-115-Part14-A-Systematic-Troubleshooting-Methodology-OSI-Layer-Walkthrough.md) frames where in the overall troubleshooting methodology packet capture fits. [§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md)-[§57](../Part7/Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md) supply the TCP header and flag knowledge this section's filter examples depend on directly. [§119](Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md) builds directly on this section's capture fundamentals, moving from command-line summary output into Wireshark's graphical, deep-filtering analysis of the exact same captured data.

**Next Section:** [§119](Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md) — `Section-119-Part14-Deeper-Packet-Analysis-Wireshark-Concepts-and-Filters.md`
