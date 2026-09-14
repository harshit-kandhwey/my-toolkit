# Section 125 (Part 15): Bandwidth Testing Tools: iperf and Friends

## 1. Definition

**Plain language:** Where `ping` and `mtr` tell you whether a path is reachable and roughly how it behaves, bandwidth-testing tools actually push data across the link at controlled rates and measure exactly how much of it arrives — answering "how fast can this link actually go" with a real, reproducible number instead of an inference.

**Precise definition:** **`iperf3`** (and its predecessor `iperf2`) is a client-server network throughput measurement tool that generates TCP or UDP traffic between two endpoints under a controlled test configuration (duration, parallel streams, buffer size, protocol) and reports achieved throughput, retransmissions, and (for UDP) jitter and datagram loss. It requires an `iperf3` process running in server mode (`-s`) on one endpoint and a client (`-c`) initiating the test from the other, distinguishing it from passive tools like `ping` that need no cooperating process on the far end. Related tools in the same family include **`nuttcp`** and **`netperf`** (similar controlled-load throughput testers with different feature sets), **`speedtest-cli`** (measures throughput against public internet speed-test servers, useful for last-mile/ISP testing rather than internal infrastructure), and **`nload`**/**`iftop`** (real-time passive bandwidth-utilization monitors that show what's already flowing on an interface rather than generating new test traffic).

> 💡 **Tip:** `iperf3` measures what a link *can* do under a controlled synthetic load; it does not measure what your actual application traffic *is* doing right now — for that, reach for the passive/observability tools in [§126](Section-126-Part15-SNMP-and-Network-Device-Monitoring-Concepts.md)-[§128](Section-128-Part15-Network-Observability-in-Cloud-and-Modern-Stacks-VPC-Flow-Logs-Metrics.md) instead of running iperf against a live production path.

## 2. Why This Matters

- **Bandwidth testing turns a suspected capacity problem into a measured fact** — "the link feels slow" is not actionable, while "measured throughput is 320 Mbits/sec on a provisioned 1 Gbps link" is immediately actionable evidence.
- **It is the standard tool for validating new infrastructure before it goes live** — a newly provisioned inter-region VPN, a new cloud interconnect, or a freshly cabled data-center uplink should always be bandwidth-tested against its expected capacity before being trusted with production traffic.
- **It isolates whether a throughput problem is the network or the application** — if `iperf3` between two hosts achieves near-line-rate throughput but the actual application transfer between the same two hosts is far slower, the bottleneck is in the application (or a middlebox specific to that application's ports/protocol), not the raw network path.
- **UDP-mode testing exposes loss and jitter under a known, fixed send rate** — which is a more controlled signal than inferring loss/jitter from best-effort ICMP probes, and is directly relevant to validating paths for real-time and streaming workloads.
- **These tools are the practical, hands-on complement to [§124](Section-124-Part15-Network-Performance-Metrics-Latency-Jitter-Packet-Loss-Throughput.md)'s metric definitions** — this section is where latency, jitter, loss, and throughput actually get measured rather than merely defined.

## 3. Prerequisites and Dependencies

This section depends directly on [§124](Section-124-Part15-Network-Performance-Metrics-Latency-Jitter-Packet-Loss-Throughput.md)'s precise definitions of latency, jitter, packet loss, and throughput — every field in `iperf3`'s output maps onto one of those concepts. It also assumes TCP window/congestion-control behavior from [§57](../Part7/Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md), since single-stream TCP throughput tests are frequently limited by window size rather than link capacity, and assumes basic port/socket vocabulary from [§62](../Part7/Section-62-Part7-QUIC-and-the-Shift-Toward-UDP-Based-Transport.md) and [§60](../Part7/Section-60-Part7-Common-Port-Reference-22-80-443-53-3306-5432-6379-etc.md), since `iperf3`'s client/server model is a plain TCP/UDP socket application like any other. It connects forward into [§129](Section-129-Part15-Capacity-Planning-and-Baseline-Establishment.md), where periodic bandwidth tests become one of the standard inputs to a capacity baseline.

## 4. Architecture / Conceptual Diagram

```text
    IPERF3 CLIENT-SERVER MODEL

    Host A (server)                              Host B (client)
    $ iperf3 -s                                  $ iperf3 -c <Host A IP> -t 10
      listens on TCP 5201                          initiates test connection
         │                                                │
         │◄──────────── control connection ──────────────│
         │                                                │
         │◄══════════ data stream (TCP or UDP) ══════════│
         │           (parallel streams -P N)              │
         │                                                │
         │─────────── results reported both sides ───────►│

    SINGLE-STREAM TCP THROUGHPUT vs. LINK CAPACITY (bandwidth-delay product limit)

    Link capacity:      ██████████████████████████  1000 Mbps
    Single TCP stream:  ████████░░░░░░░░░░░░░░░░░░   300 Mbps  ◄── window-limited, not link-limited
    4 parallel streams: █████████████████████████░   960 Mbps  ◄── aggregate reveals true capacity
```

- A single TCP stream's achievable throughput is capped by `window size / RTT`; on a high-latency path (e.g., cross-region), a single stream can badly under-report the link's real capacity, which is exactly why `iperf3 -P <n>` (parallel streams) exists — this is a critical detail when validating any long-haul link.
- Running the server (`-s`) on the far end and the client (`-c`) on the near end (vs. reversed) tests the send direction from client to server by default; `-R` reverses the direction, and both directions should be tested independently since many links (especially asymmetric consumer/ISP links or asymmetrically-shaped cloud egress paths) are not symmetric.
- UDP mode (`-u`) sends at a fixed target rate (`-b`) regardless of network conditions, which is why it directly reports loss and jitter — TCP mode instead self-adjusts its send rate via congestion control, which is why it reports achieved throughput and retransmissions rather than loss directly.

## 5. Hands-On

### 5.1 Basic TCP Throughput Test

**Purpose:** Establish baseline achievable TCP throughput between two hosts.

**Syntax:**

```bash
# On the server host:
iperf3 -s

# On the client host:
iperf3 -c <server-ip> -t <seconds>
```

**Example usage and expected output:**

```bash
$ iperf3 -c 10.20.0.5 -t 10
Connecting to host 10.20.0.5, port 5201
[  5] local 10.20.0.10 port 44212 connected to 10.20.0.5 port 5201
[ ID] Interval           Transfer     Bitrate         Retr  Cwnd
[  5]   0.00-1.00   sec   111 MBytes   934 Mbits/sec    0    1.41 MBytes
[  5]   1.00-2.00   sec   112 MBytes   940 Mbits/sec    0    1.41 MBytes
...
[  5]   0.00-10.00  sec  1.09 GBytes   937 Mbits/sec    0             sender
[  5]   0.00-10.00  sec  1.09 GBytes   936 Mbits/sec                  receiver
```

**Production usage example:** This result — near-line-rate on a 1 Gbps link with zero retransmissions (`Retr`) — is the expected baseline recorded immediately after provisioning a new same-datacenter link, and becomes the reference value that later measurements are compared against for regression detection ([§129](Section-129-Part15-Capacity-Planning-and-Baseline-Establishment.md)).

**Common errors:** Running a single short test (1-2 seconds) and treating a low first-second reading as representative — TCP slow start means the first second or two of any test under-reports steady-state throughput; always let the test run at least 10 seconds and read the cumulative summary line, not an early interval.

### 5.2 Parallel Streams to Reveal True Link Capacity

**Purpose:** Avoid understating link capacity when a single TCP stream is window-limited, particularly on higher-latency paths.

**Syntax:**

```bash
iperf3 -c <server-ip> -P <parallel-streams> -t <seconds>
```

**Example usage and expected output:**

```bash
$ iperf3 -c 198.51.100.20 -P 4 -t 10
[ ID] Interval           Transfer     Bitrate
[  5]   0.00-10.00  sec   580 MBytes   486 Mbits/sec                  sender
[  7]   0.00-10.00  sec   575 MBytes   482 Mbits/sec                  sender
[  9]   0.00-10.00  sec   578 MBytes   484 Mbits/sec                  sender
[ 11]   0.00-10.00  sec   582 MBytes   488 Mbits/sec                  sender
[SUM]   0.00-10.00  sec  2.26 GBytes  1.94 Gbits/sec                  sender
```

**Production usage example:** A single stream to this cross-region target had measured only ~480 Mbits/sec, but four parallel streams aggregate to ~1.94 Gbits/sec — confirming the link itself supports far more capacity than a single connection can extract, which reframes an application-level "slow transfer" complaint on this path as a client concurrency/window-tuning issue rather than a network capacity shortfall.

**Common errors:** Concluding a link's true capacity is only what a single stream achieved, without testing with `-P` — this is the single most common source of underestimating cross-region or high-RTT link capacity.

### 5.3 UDP Mode for Loss and Jitter at a Fixed Rate

**Purpose:** Directly measure packet loss and jitter under a known, fixed-rate load — the pattern most relevant to validating a path for real-time/streaming traffic.

**Syntax:**

```bash
iperf3 -c <server-ip> -u -b <target-bandwidth> -t <seconds>
```

**Example usage and expected output:**

```bash
$ iperf3 -c 10.20.0.5 -u -b 50M -t 10
[ ID] Interval           Transfer     Bitrate         Jitter    Lost/Total
[  5]   0.00-10.00  sec  59.6 MBytes  50.0 Mbits/sec  0.412 ms  0/43201 (0%)
```

**Production usage example:** Validating a new site-to-site VPN tunnel intended to carry VoIP traffic, a target run at 50 Mbits/sec (well above the expected real voice load) showing 0% loss and sub-millisecond jitter provides concrete evidence the tunnel is fit for purpose before cutting real call traffic over to it, rather than discovering jitter problems from user complaints after go-live.

**Common errors:** Setting the UDP target bandwidth (`-b`) far above what the link can actually sustain and misreading the resulting loss as a link fault — `iperf3` in UDP mode sends at the requested rate regardless of capacity, so a loss percentage at a target rate deliberately set above link capacity reflects the test parameters, not a hidden network problem; always test at or modestly above the actual expected application load, not an arbitrary large number.

## 6. Production Usage Notes

- Never leave an `iperf3` server (`-s`) running unauthenticated and exposed on a production host indefinitely — treat it like any other administrative service: bind it to a management interface, firewall it to known test-runner sources, and tear it down after the test window.
- Schedule periodic (not just one-off) bandwidth tests between critical infrastructure pairs (cross-region links, VPN tunnels, on-prem-to-cloud interconnects) to catch capacity degradation over time, feeding directly into the baseline practice in [§129](Section-129-Part15-Capacity-Planning-and-Baseline-Establishment.md).
- When testing cloud-to-cloud or cloud-to-on-prem paths, be aware that egress bandwidth is frequently billed per byte — a sustained multi-gigabit `iperf3` test across a metered link can generate meaningful and unexpected cost; scope test duration and bandwidth deliberately.

## 7. Security Considerations

- An `iperf3` server left running and reachable from the public internet can be used by a third party as free bandwidth for testing (or abused as part of a reflection/amplification scheme in some configurations) — always restrict access with firewall rules or security groups scoped to known test sources ([§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)).
- Running a large bandwidth test against a shared or production link without coordination can itself cause a self-inflicted denial-of-service by saturating capacity other services depend on — treat bandwidth testing on shared infrastructure as a change requiring the same approval as any other potentially disruptive operation.
- UDP-mode tests bypass congestion control entirely by design, meaning a misconfigured or malicious high-rate UDP test can saturate a link far more aggressively and abruptly than any TCP-based tool would — apply the same access and rate discipline to UDP tests as to TCP ones, and prefer the lowest rate that answers the actual question being asked.

## 8. Common Troubleshooting Scenarios

| Symptom                                                     | Likely Cause                                                                 | Resolution Path                                                                                          |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------- |
| Single-stream `iperf3` result far below provisioned bandwidth | TCP window/bandwidth-delay-product limit on a high-RTT path                    | Re-test with `-P` (parallel streams); tune TCP window sizing if a single-stream result must be improved |
| `iperf3` client cannot connect to server at all               | Firewall/security group blocking TCP 5201 (or configured custom port)          | Confirm port reachability with `nc -zv` ([§117](../Part14/Section-117-Part14-Port-and-Service-Testing-telnet-nc-curl-for-Network-Diagnostics.md)); open the specific port/source needed, nothing broader |
| UDP test shows high loss at a high target bandwidth           | Target bandwidth (`-b`) set above actual link/path capacity                    | Lower the target rate to match realistic expected application load; re-test incrementally to find the real ceiling |
| iperf throughput is fine but the real application transfer is slow | Application-layer bottleneck (disk I/O, single-threaded transfer, app-level rate limiting) — not the network | Compare `iperf3` result against the application's actual transfer rate on the same path to confirm the network is exonerated, then investigate the application |

## 9. Best Practices

- Always run tests in both directions (`-R` for reverse) and at multiple times of day, since many links are asymmetric or exhibit time-of-day congestion patterns that a single one-way, one-time test would miss.
- Use parallel streams (`-P`) whenever testing a higher-latency path, and record both the single-stream and aggregate results — the gap between them is itself diagnostic information about window tuning versus true capacity.
- Record test parameters (duration, stream count, protocol, direction, time of day) alongside every result so future comparisons are apples-to-apples, feeding cleanly into the capacity-baseline discipline in [§129](Section-129-Part15-Capacity-Planning-and-Baseline-Establishment.md).

## 10. Common Anti-Patterns / Mistakes

- **Judging link capacity from a single, short, single-stream TCP test.** Slow start and window limits can badly understate true capacity; always test with adequate duration and parallel streams before concluding a link is under-provisioned.
- **Leaving an `iperf3` server running and open indefinitely on a production or internet-facing host.** This is both a security exposure and an invitation for accidental interference from unrelated testing.
- **Running a heavy, uncoordinated bandwidth test against a live production link.** This can itself cause the very congestion/outage the test was meant to investigate; coordinate timing and scope with anyone else relying on that capacity.

## 11. Interview Questions

**🎯 Beginner:** _"What does `iperf3` actually measure, and how is that different from `ping`?"_
**Model answer:** `iperf3` measures actual achievable throughput between two hosts by generating real TCP or UDP data traffic under a controlled test and reporting the bitrate achieved (plus loss/jitter in UDP mode). `ping` only measures reachability and round-trip latency using small ICMP packets — it tells you a host is there and roughly how quickly it responds, but says nothing about how much data the path can actually carry.
_What the interviewer is probing for:_ Clear distinction between reachability/latency testing and throughput testing, and that they're not interchangeable diagnostics.

**🎯 Intermediate:** _"You run a single-stream `iperf3` test across a transcontinental link and get only 200 Mbits/sec on a link provisioned for 1 Gbps. Is the link under-provisioned?"_
**Model answer:** Not necessarily — a single TCP stream's throughput is capped by the bandwidth-delay product (window size divided by RTT), and a transcontinental link has high RTT, so a single stream can be window-limited well below the link's actual capacity. Before concluding the link is under-provisioned, I'd re-test with multiple parallel streams (`-P`) and, if needed, larger TCP window sizes; if the aggregate of several parallel streams approaches 1 Gbps, the link itself is fine and the original single-stream number was a window-tuning artifact, not a capacity problem.
_What the interviewer is probing for:_ Understanding that raw throughput numbers must be interpreted in context of TCP mechanics, not taken at face value.

**🎯 Senior:** _"How would you validate a newly provisioned site-to-site VPN before cutting production VoIP traffic over to it?"_
**Model answer:** I'd run `iperf3` in UDP mode at a target rate representative of (or modestly above) the expected real voice load, since UDP mode directly reports loss and jitter at a fixed send rate — the two metrics that matter most for VoIP quality, far more than raw throughput. I'd run the test in both directions, at multiple times of day to catch time-dependent congestion on the underlying transport, and for a long enough duration to smooth out transient noise. I'd also run a TCP throughput test separately to confirm the tunnel's raw capacity is adequate for any other traffic sharing it. Only after seeing consistently low loss and jitter across these runs would I sign off on cutting real call traffic over, and I'd keep the same test as a recurring synthetic check afterward to catch regressions (tying into [§129](Section-129-Part15-Capacity-Planning-and-Baseline-Establishment.md)'s baseline practice).
_What the interviewer is probing for:_ Ability to select the right test mode and metric for the actual workload being validated, not just running a generic throughput test and calling it done.

**🎯 Architect:** _"How would you build a scalable, safe bandwidth-testing practice across dozens of inter-region links without it becoming a source of cost or self-inflicted outages?"_
**Model answer:** I'd deploy dedicated, access-controlled `iperf3` (or `nuttcp`) endpoints in each region specifically for synthetic testing, firewalled to only accept connections from an internal test-orchestration service — never exposed broadly. I'd schedule tests to run at low, controlled bandwidth targets on a regular cadence rather than periodic full-capacity blasts, reserving full-capacity tests for deliberate, coordinated validation windows (e.g., right after provisioning new capacity, or during planned maintenance), specifically to avoid the cost and self-inflicted congestion risk of routine high-bandwidth synthetic load on metered or shared links. Results would feed into a central time-series store so degradation over time is visible as a trend rather than only a point-in-time comparison, directly supporting the capacity-planning and baseline discipline in [§129](Section-129-Part15-Capacity-Planning-and-Baseline-Establishment.md) and the alerting patterns in [§130](Section-130-Part15-Alerting-on-Network-Layer-Signals.md). I'd also make sure test infrastructure itself doesn't become a blind spot — monitoring the health of the iperf endpoints themselves, not just what they report.
_What the interviewer is probing for:_ Operational maturity: treating bandwidth testing as a governed, cost-aware, safety-conscious practice at scale, not a one-off manual command.

## 12. Common Misconceptions

1. **"A single `iperf3` TCP test always shows a link's true capacity."** A single stream is frequently window-limited on higher-latency paths; parallel streams are often necessary to reveal actual capacity.
2. **"High UDP loss in an `iperf3` test always means the network is broken."** If the target bandwidth (`-b`) was set above the link's real capacity, the loss reflects the test parameters, not a hidden fault.
3. **"`iperf3` and `speedtest-cli`-style tools measure the same thing."** Public speed-test tools measure last-mile/ISP performance against a specific test server; `iperf3` between your own controlled endpoints measures your actual internal or dedicated-link path — they answer different questions.
4. **"Running a bandwidth test is always safe to do at any time."** A heavy test on a shared or metered production link can cause real congestion, cost, or contention with genuine traffic; scope, schedule, and coordinate tests deliberately.

## 13. 🔑 Key Takeaways

- `iperf3` measures actual achievable throughput (and, in UDP mode, loss/jitter) under controlled synthetic load — a fundamentally different and complementary measurement to `ping`'s reachability/latency check.
- Single-stream TCP results can badly understate true link capacity on higher-latency paths; parallel streams (`-P`) reveal the real ceiling.
- UDP mode is the right tool for validating paths intended for real-time/streaming traffic, since it directly reports loss and jitter at a known fixed rate.
- Bandwidth-testing endpoints and test traffic both carry real security, cost, and self-inflicted-outage risk and must be governed accordingly.

## 14. Related Concepts & What's Next

This section operationalizes the metrics defined in [§124](Section-124-Part15-Network-Performance-Metrics-Latency-Jitter-Packet-Loss-Throughput.md) with concrete, runnable tooling. It depends on TCP congestion-control behavior from [§57](../Part7/Section-57-Part7-TCP-Flow-Control-and-Congestion-Control-Windowing-Slow-Start.md) to correctly interpret single-stream results, and on port/firewall concepts from [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md) for securing test endpoints. It feeds forward directly into [§129](Section-129-Part15-Capacity-Planning-and-Baseline-Establishment.md), where recurring bandwidth measurements become one of the standard inputs to a capacity baseline, and into [§130](Section-130-Part15-Alerting-on-Network-Layer-Signals.md), where sustained deviations from a known-good throughput baseline become an alertable condition.

**Next Section:** [§126](Section-126-Part15-SNMP-and-Network-Device-Monitoring-Concepts.md) — `Section-126-Part15-SNMP-and-Network-Device-Monitoring-Concepts.md`
