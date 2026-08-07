# Section 84 (Part 11): Network Performance Analysis: iftop, nload, sar

## 1. Connectivity vs. Throughput: Two Different Questions

[§81](./Section-81-Part11-CPU-Load-Analysis.md) through [§83](./Section-83-Part11-Disk-IO-Analysis.md) covered CPU, memory, and disk I/O as the first three of [§80](./Section-80-Part11-Performance-Fundamentals-Unified-Model.md)'s four resource-specific deep dives. This section closes the sequence with network — the fourth resource in that unified model.

[§55](../Part7/Section-55-Part7-Network-Diagnostics.md) covered network diagnostics — `ping`, `ss`, `tcpdump`, and similar tools — but those tools answer a fundamentally different question than the ones in this section, and it's worth stating the distinction explicitly before going further: **[§55](../Part7/Section-55-Part7-Network-Diagnostics.md)'s tools answer "can I reach it, and is DNS/routing/the connection itself correct."** They're about connectivity and correctness. **This section's tools answer "how much bandwidth is actually being used, and by what."** They're about throughput and capacity. A host can pass every connectivity check `ping`/`ss`/`tcpdump` would run and still be network-performance-constrained — saturating its interface, or having one specific connection monopolize available bandwidth — which is a throughput problem invisible to a pure connectivity check.

> 💡 **Tip:** When a network-adjacent complaint comes in ("the transfer is slow," "the API feels sluggish over the network"), decide up front which of the two questions is actually being asked. "Is it reachable / is the connection healthy" points to [§55](../Part7/Section-55-Part7-Network-Diagnostics.md)'s toolkit. "Is bandwidth the constraint, and if so who's consuming it" points to this section's toolkit. Reaching for the wrong set first is a common source of wasted diagnostic time.

## 2. `iftop`: Real-Time Per-Connection Bandwidth

**Purpose:** Show live bandwidth usage broken down **per connection**, on a given network interface — the network equivalent of what `iotop` ([§83](./Section-83-Part11-Disk-IO-Analysis.md)) does for disk I/O, attributing usage to a specific source rather than just reporting an aggregate.

**Syntax:**

```bash
sudo iftop -i eth0
```

**Key flags:**

| Flag             | Meaning                                                                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------- |
| `-i <interface>` | Specify which network interface to monitor                                                                                       |
| `-n`             | Skip DNS resolution of remote addresses — faster and less noisy when reverse-DNS lookups would slow the display or aren't useful |
| `-P`             | Show port numbers alongside addresses                                                                                            |

**Example usage and expected output:**

```bash
$ sudo iftop -i eth0 -n
                  128Kb          256Kb          384Kb          512Kb
+----------------+----------------+----------------+----------------
10.0.1.15  =>     10.0.2.20        420Kb   380Kb   395Kb
           <=                        12Kb    10Kb    11Kb
10.0.1.15  =>     10.0.3.44         88Kb    90Kb    89Kb
           <=                         5Kb     4Kb     4Kb
```

**Interpretation:** Each pair of rows is one connection, showing outbound (`=>`) and inbound (`<=`) throughput averaged over a few rolling windows. In this example, the connection to `10.0.2.20` is clearly the dominant consumer of the interface's bandwidth — the kind of attribution that's impossible to get from an aggregate interface counter alone.

**Production usage example:** During a "this host's network feels saturated" investigation, `iftop` is the fastest way to see whether one specific destination or connection is responsible for the load, versus the traffic being evenly spread across many legitimate connections — directly analogous to reaching for `iotop` once `iostat` ([§83](./Section-83-Part11-Disk-IO-Analysis.md)) has confirmed disk saturation, or `mpstat` ([§81](./Section-81-Part11-CPU-Load-Analysis.md)) once aggregate CPU looked ambiguous.

## 3. `nload`: Simple Aggregate Bandwidth Graph

**Purpose:** Show a simple, real-time graph of total incoming and outgoing bandwidth on an interface — less detail than `iftop`, but faster to read at a glance for a single yes/no question: is this interface busy.

**Syntax:**

```bash
nload eth0
```

**Example usage and expected output:**

```
Device eth0 [10.0.1.15] (1/1):
================================================================
Incoming:
Curr: 45.32 MBit/s
Avg:  38.10 MBit/s
Min:   2.10 MBit/s
Max:  62.40 MBit/s

Outgoing:
Curr:  8.20 MBit/s
Avg:   7.95 MBit/s
Min:   1.10 MBit/s
Max:  12.30 MBit/s
```

**Interpretation:** `nload` deliberately doesn't break usage down by connection or process — it answers "how saturated is this interface right now" in the simplest possible form, with no per-connection detail to parse. That trade-off is the point: it's the tool to reach for when the question is just "is this interface near its limit," and `iftop` is the tool to reach for once the answer is yes and the follow-up question becomes "saturated by what."

**Common errors:** Expecting `nload` to explain _why_ an interface is busy — it intentionally doesn't attribute traffic to a connection or process; that's `iftop`'s job (2), not `nload`'s.

## 4. `sar`: Historical Network Statistics — and a Distinct Capability

**Purpose:** Report network interface statistics — and, more broadly, statistics across CPU, memory, and disk too — with a capability none of the other tools in this Part share: **`sar` collects and retains historical data**, not just a live view.

**Syntax:**

```bash
sar -n DEV 1
sar -n DEV -f /var/log/sysstat/saXX
```

**Key flags:**

| Flag        | Meaning                                                                                                              |
| ----------- | -------------------------------------------------------------------------------------------------------------------- |
| `-n DEV`    | Report per-network-device statistics                                                                                 |
| `1`         | Live mode — repeat every 1 second, similar to `iostat`/`vmstat`/`mpstat`                                             |
| `-f <file>` | Read from a previously recorded `sysstat` data file instead of live-sampling, for after-the-fact historical analysis |

**Example usage and expected output:**

```bash
$ sar -n DEV 1
12:05:01 PM     IFACE   rxpck/s   txpck/s    rxkB/s    txkB/s
12:05:02 PM      eth0   1520.00    980.00    980.40    620.15
```

| Column                | Meaning                                                                   |
| --------------------- | ------------------------------------------------------------------------- |
| `rxpck/s` / `txpck/s` | Packets received/transmitted per second                                   |
| `rxkB/s` / `txkB/s`   | Kilobytes received/transmitted per second — the direct throughput figures |

**The broader, more valuable point about `sar`:** unlike `iftop` and `nload` (both live-only — their view disappears the moment the terminal closes), `sar` is backed by the **`sysstat`** package, which runs as a background service periodically recording system statistics — CPU, memory, disk, and network alike — to disk. This means `sar -f` can answer **"what was network throughput on this host at 3 AM last Tuesday, during the incident,"** a question `iftop`/`nload`/live `iostat`/live `top` categorically cannot answer once the moment has passed, since none of them retain anything.

> ⚠️ **Warning:** This retained-history capability depends entirely on `sysstat`'s data-collection service actually being installed, enabled, and running with adequate retention configured _before_ the incident happens — `sar -f` against a host that never had `sysstat` collecting is simply not an option, no matter how badly the historical data is needed afterward. This is a genuine "should have configured this ahead of time" gap, not something fixable in the moment of an incident.

**Production usage example:** Post-incident retrospectives frequently need to answer "was the network actually saturated during the outage window, or was the slowness caused by something else" after the fact, once the live moment has long passed — `sar -n DEV -f` against the retained `sysstat` data is the only tool in this section's set that can answer that question at all, which is why fleet-wide `sysstat` enablement is a reasonable baseline hardening/observability decision independent of any specific incident.

## 5. Is the Interface the Bottleneck, or Is It Application-Layer?

A sustained high-throughput reading from any of the above tools doesn't automatically mean the network interface itself is the constraint — distinguishing "the pipe is genuinely full" from "something upstream just looks like a network problem" matters for choosing the right remediation:

- **Interface-level bottleneck:** throughput sustained **near the interface's rated speed** (a 1 Gbps interface consistently reading close to 1 Gbps aggregate via `nload`/`sar`) is genuine saturation — the physical or virtual link itself is the constraint, and the fix is a faster interface, traffic reduction, or spreading load across more links.
- **Looks like a network problem but isn't:** intermittent slowness, high latency, or poor throughput on a connection while the interface's _aggregate_ utilization (via `nload`) is nowhere near its rated capacity points elsewhere — a slow application-layer protocol exchange, TCP window/congestion-control behavior interacting badly with latency (a topic `tcpdump`, from [§55](../Part7/Section-55-Part7-Network-Diagnostics.md), is better suited to inspect than any tool in this section), or a downstream/upstream service being slow to respond rather than the network transport itself being constrained.

The practical check: compare sustained throughput against the interface's known rated speed first. If it's nowhere close, the "network" complaint is very likely actually a connectivity/protocol/application issue and the investigation should move back to [§55](../Part7/Section-55-Part7-Network-Diagnostics.md)'s toolkit (`ss`, `tcpdump`) rather than staying in throughput-monitoring tools that have nothing further to reveal.

## 6. Common Misconceptions

1. **"Network diagnostic tools are interchangeable — `ping`/`ss` and `iftop`/`sar` answer the same kind of question."** They don't — [§55](../Part7/Section-55-Part7-Network-Diagnostics.md)'s tools confirm reachability and connection correctness; this section's tools measure bandwidth usage and attribution (1). A host can pass every connectivity check and still be throughput-constrained, or vice versa.
2. **"`nload` and `iftop` show the same thing at different levels of detail."** They're both live-only bandwidth tools, but `nload` deliberately shows only an aggregate in/out figure with no attribution, while `iftop` breaks usage down per connection — reaching for `nload` to find out _who_ is consuming bandwidth will not work; that's `iftop`'s specific job (2, 3).
3. **"Any of these tools can tell you what network conditions looked like during a past incident."** Only `sar`, backed by `sysstat`'s continuous background collection, retains historical data — `iftop` and `nload` show only the live present moment and retain nothing once closed (4).
4. **"High reported throughput always means the network interface is the bottleneck."** Only if that throughput is sustained near the interface's rated capacity — intermittent or moderate throughput readings alongside a slow-feeling connection more often point to an application-layer or protocol issue than genuine link saturation (5).

## 7. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between using `ping`/`ss` and using `iftop`/`nload` to investigate a network issue?"_
**Model answer:** `ping` and `ss` (covered in [§55](../Part7/Section-55-Part7-Network-Diagnostics.md)) answer whether a host is reachable and whether a connection is established and healthy — connectivity and correctness questions. `iftop` and `nload` answer a different question entirely: how much bandwidth is actually being used right now, and by what. A host can be perfectly reachable with healthy connections and still be network-performance-constrained if it's pushing close to its interface's maximum throughput — that's a throughput problem `ping`/`ss` wouldn't reveal, which is why the two toolkits serve different diagnostic purposes rather than being interchangeable.
_What the interviewer is probing for:_ Whether the candidate treats "network tools" as one undifferentiated bucket or understands the connectivity-vs-throughput distinction specifically.

**🎯 Intermediate:** _"When would you reach for `nload` versus `iftop`?"_
**Model answer:** `nload` for a fast, single-glance answer to "is this interface busy" — a simple aggregate incoming/outgoing graph with no per-connection detail. `iftop` once that answer is yes and I need to know _who_ is consuming the bandwidth — it breaks usage down per connection, which `nload` deliberately doesn't do. In practice that's often a two-step flow: `nload` to confirm the interface looks saturated, then `iftop` to attribute it to a specific connection or destination.
_What the interviewer is probing for:_ Understanding the aggregate-vs-attribution trade-off between the two tools rather than treating them as arbitrary alternatives.

**🎯 Senior:** _"An incident happened at 3 AM last night and you suspect network saturation was involved, but you're investigating this morning. How do you check?"_
**Model answer:** `iftop` and `nload` are both live-only — they show nothing from a moment that's already passed, so neither can answer this after the fact. `sar -n DEV -f`, reading from `sysstat`'s retained historical data files, is the only tool in this set built for exactly this — assuming `sysstat` was actually installed and running with adequate retention on that host beforehand. If it wasn't, there's no way to reconstruct that window's network throughput after the fact from these tools at all, which is itself worth flagging as an observability gap to close before the next incident, rather than something recoverable in the moment.
_What the interviewer is probing for:_ Recognizing which tool in the set actually supports historical analysis, and treating missing `sysstat` coverage as a gap to fix going forward rather than something to work around after the fact.

**🎯 Architect:** _"How would you decide whether a reported network slowness is a genuine interface bottleneck versus an application-layer issue that merely looks like one?"_
**Model answer:** I'd start by pulling sustained throughput for the affected interface — via `sar -n DEV` if it's a past window or `nload`/`iftop` if it's ongoing — and compare it directly against the interface's rated capacity. If throughput is consistently near that ceiling, it's a genuine link-level bottleneck, and the fix space is capacity (faster interface, load spread across more links) or reducing the traffic itself. If throughput is nowhere near capacity but the connection still feels slow or exhibits high latency, I'd treat the "network" framing as likely a misdiagnosis and move the investigation to [§55](../Part7/Section-55-Part7-Network-Diagnostics.md)'s connectivity/protocol tools — `tcpdump` for packet-level behavior, `ss` for connection state — since intermittent slowness at low aggregate utilization is much more often a TCP behavior issue, an upstream/downstream service being slow to respond, or an application-layer protocol inefficiency than a saturated pipe. I'd also make sure `sysstat` is enabled fleet-wide as a baseline so this comparison is always possible after the fact, not just when it happens to be actively monitored live at the moment something goes wrong.
_What the interviewer is probing for:_ A concrete, capacity-based test for distinguishing genuine saturation from a look-alike problem, and proactive observability posture (retained history via `sysstat`) rather than only live-tool reliance.

## 8. Key Takeaways

- [§55](../Part7/Section-55-Part7-Network-Diagnostics.md)'s tools (`ping`, `ss`, `tcpdump`) answer connectivity and correctness questions; this section's tools (`iftop`, `nload`, `sar`) answer bandwidth/throughput questions — a genuinely useful distinction to lead with when triaging a network complaint (1).
- `iftop` gives live, per-connection bandwidth attribution — the network analog of `iotop` for disk ([§83](./Section-83-Part11-Disk-IO-Analysis.md)) and `mpstat` for per-core CPU ([§81](./Section-81-Part11-CPU-Load-Analysis.md)) (2).
- `nload` gives a simple, aggregate incoming/outgoing bandwidth graph — fast for "is this interface busy," but no attribution; that's `iftop`'s job (3).
- `sar` (via `sysstat`) is the only tool here that retains **historical** data across all resource types, not just network — `sar -n DEV -f` can answer "what did throughput look like during an incident that already ended," which live-only tools categorically cannot, provided `sysstat` was actually running beforehand (4).
- Sustained throughput near an interface's rated capacity indicates a genuine link-level bottleneck; moderate or intermittent throughput alongside perceived slowness more often points to an application-layer or protocol issue, best investigated with [§55](../Part7/Section-55-Part7-Network-Diagnostics.md)'s tools instead (5).

## 9. Related Concepts & What's Next

This section closes the four-part resource-specific sequence — [§81](./Section-81-Part11-CPU-Load-Analysis.md) (CPU), [§82](./Section-82-Part11-Memory-Analysis.md) (memory), [§83](./Section-83-Part11-Disk-IO-Analysis.md) (disk I/O), and this section (network) — that together operationalize [§80](./Section-80-Part11-Performance-Fundamentals-Unified-Model.md)'s unified four-resource performance model with hands-on, tool-specific depth. It builds directly on [§55](../Part7/Section-55-Part7-Network-Diagnostics.md)'s connectivity/diagnostics coverage (Part 7), which this section deliberately distinguishes itself from rather than duplicates. [§85](./Section-85-Part11-Logging-Deep-Dive-Rsyslog-Log-Rotation.md) (next) moves to logging in depth — `rsyslog`, log rotation via `logrotate`, and centralized logging pipelines — a related but distinct operational concern from the four-resource performance model this Part opened with.

**Next Section:** [§85](./Section-85-Part11-Logging-Deep-Dive-Rsyslog-Log-Rotation.md) — `Section-85-Part11-Logging-Deep-Dive.md`
