# Section 81 (Part 11): CPU and Load Analysis: uptime, top, mpstat, vmstat

## 1. Load Average: What the Three Numbers Actually Measure

§80 introduced CPU, memory, disk I/O, and network as a unified four-resource model for reasoning about performance, and framed the recurring job as bottleneck identification — figuring out which of the four is actually constrained rather than guessing. This section is the first of the four resource-specific deep dives that model implies, starting with CPU.

`uptime` is usually the first command run on an unfamiliar host, and its output is the most commonly misread number in Linux performance work:

```bash
$ uptime
 14:32:07 up 41 days,  3:12,  2 users,  load average: 8.42, 6.15, 3.90
```

The three numbers are the **1-minute, 5-minute, and 15-minute load averages** — exponentially-decaying averages of the **run-queue length**, sampled continuously by the kernel. Two details matter far more than they first appear to:

- **"Run-queue length" is not "percent CPU busy."** It's a count of processes that are either currently running on a CPU or **waiting to run** (runnable but not scheduled yet) — plus one category almost everyone forgets, covered next.
- **Processes in uninterruptible sleep (D state) count toward load average too**, not just runnable processes. D-state is the state a process enters while blocked on an I/O operation it cannot be interrupted out of — waiting on a disk read, an NFS mount, or similar. This means load average conflates two structurally different situations: processes queued because the **CPU** is saturated, and processes stuck because **I/O** is slow, and the raw number alone cannot distinguish them.

> ⚠️ **Warning:** This is a genuinely common and consequential misconception: reading a load average of 8 on a 4-core box as "the CPU is at 200% capacity" or "double-saturated." It might mean exactly that — or it might mean the CPUs are almost entirely idle while eight processes sit in D-state waiting on a slow disk or an unresponsive NFS server, in which case adding CPU capacity would do nothing at all. Load average by itself only tells you **how many processes want to run or are stuck waiting**, never **why**. Section 5's worked scenario walks through disambiguating exactly this.

**Interpreting the number against core count** is the second half of reading it correctly: a load average needs to be compared to the number of logical CPUs (`nproc`), not read as an absolute. A load average of 4 is "fully loaded, no queueing" on a 4-core box but "heavily oversubscribed" on a 2-core box and "comfortably idle" on a 16-core box.

**Reading the trend across the three windows** is itself diagnostic: 1-minute higher than 5-minute and 15-minute (`8.42, 6.15, 3.90` above) indicates load is currently **rising** — something got worse recently. The reverse pattern — 1-minute lower than 15-minute — indicates a spike is **subsiding**. A single load-average reading is a snapshot; the three numbers together are a short trendline for free.

## 2. `top`'s CPU Fields in Depth: us, sy, ni, id, wa, hi, si

§34 (Part 5) introduced `top` for viewing processes generally — this section goes deeper specifically on its CPU summary line, which is where the actual bottleneck-classification work happens.

```bash
$ top
%Cpu(s): 22.3 us,  4.1 sy,  0.0 ni, 15.8 id, 57.2 wa,  0.4 hi,  0.2 si
```

| Field | Meaning                                                                                                                    |
| ----- | -------------------------------------------------------------------------------------------------------------------------- |
| `us`  | User time — CPU spent running normal, unprivileged application code                                                        |
| `sy`  | System time — CPU spent in kernel code on behalf of processes (system calls, context switching)                            |
| `ni`  | User time spent running processes that have a **nice**d (adjusted) priority (§38, Part 5, covers `nice`/`renice` directly) |
| `id`  | Idle — CPU genuinely has nothing to do                                                                                     |
| `wa`  | **I/O wait** — CPU is idle, specifically because it's waiting on an outstanding disk or network I/O operation to complete  |
| `hi`  | Hardware interrupt time — servicing interrupts raised directly by hardware devices                                         |
| `si`  | Softirq time — deferred, lower-priority interrupt-related kernel work                                                      |

The field worth dedicated attention is **`wa`**, because it's the one most often misdiagnosed as a CPU problem when it's the opposite. A high `wa` value means the CPU has no runnable work available — it is **idle**, just idle in a specific, named way, sitting there because the process it would otherwise run is blocked on I/O. The `57.2 wa` reading above is not a CPU bottleneck at all; it's a direct symptom that disk or network I/O is the actual constraint (§83 covers the disk-I/O-specific tools for confirming which).

> 💡 **Tip:** A quick mental model for the whole line: `us` + `sy` + `ni` is genuine CPU work being done. `id` is genuine spare capacity. `wa` is neither — it's idle capacity being held hostage by something else entirely, and it's the single field most worth checking first when load average is high but the workload "shouldn't" be CPU-bound.

## 3. `mpstat`: Per-Core Breakdown

`top`'s summary line is an **aggregate** across every logical CPU, and aggregates hide a specific, real failure mode: a single-threaded application can peg one core at 100% while every other core sits idle, and the aggregate might read as an unremarkable "modest load," because seven idle cores dilute the one saturated one in the average.

**Purpose:** Break the same `us`/`sy`/`id`/`wa` breakdown down **per CPU core**, revealing single-core saturation an aggregate view conceals.

**Syntax:**

```bash
mpstat -P ALL 1
```

**Key flags:**

| Flag     | Meaning                                                                                                      |
| -------- | ------------------------------------------------------------------------------------------------------------ |
| `-P ALL` | Report every logical CPU individually rather than only the aggregate                                         |
| `1`      | Repeat every 1 second — like `vmstat`, a single invocation is a snapshot; a repeating one shows a live trend |

**Example usage and expected output:**

```bash
$ mpstat -P ALL 1
14:35:02     CPU    %usr   %nice    %sys %iowait    %irq   %soft   %idle
14:35:03     all    12.50    0.00    3.10    0.20    0.00    0.10   84.10
14:35:03       0    98.90    0.00    1.00    0.00    0.00    0.10    0.00
14:35:03       1     0.50    0.00    0.30    0.00    0.00    0.00   99.20
14:35:03       2     0.60    0.00    0.20    0.00    0.00    0.00   99.20
14:35:03       3     0.40    0.00    0.30    0.00    0.00    0.00   99.30
```

**Interpretation:** The aggregate (`all`) row reads as a calm 12.5% user time and 84% idle — nothing alarming on its own. The per-core rows reveal CPU 0 pinned at 98.9% while cores 1–3 are essentially idle. This is the signature of a single-threaded process (or a poorly parallelized workload) that cannot benefit from the extra cores at all — scaling out to more cores would do nothing; the fix is making the workload multi-threaded, distributing load differently, or accepting the ceiling of one core's throughput.

**Production usage example:** Diagnosing "the box has plenty of headroom according to monitoring, but this one service is slow" reports — aggregate CPU dashboards frequently show comfortable overall utilization while a single hot core is quietly capping a specific application's throughput, and `mpstat -P ALL` is the fastest way to confirm or rule that out.

**Common errors:** Reading only the aggregate row out of habit and concluding "CPU isn't the problem" without checking per-core — the single most common way this specific bottleneck gets missed entirely.

## 4. `vmstat`: Run Queue and Blocked-Process Trend

**Purpose:** Show run-queue length, blocked-process count, and CPU/memory summary figures together, refreshed at an interval — the tool for watching load-average's underlying numbers move in real time rather than reading a single decayed average.

**Syntax:**

```bash
vmstat 1
```

**Key flags:**

| Flag                 | Meaning                                                                                                                                                        |
| -------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| (interval, e.g. `1`) | Repeat every N seconds; the **first line** printed is always a since-boot average and should be discarded — only subsequent lines reflect the current interval |

**Example usage and expected output:**

```bash
$ vmstat 1
procs -----------memory---------- ---swap-- -----io---- -system-- ------cpu-----
 r  b   swpd   free   buff  cache   si   so    bi    bo   in   cs us sy id wa st
 6  3  102400 512340  88120 2451200    0    0    45   210 1200 3400 22  4 16 58  0
 5  2  102400 508210  88130 2451800    0    0    12   180 1180 3300 21  5 17 57  0
```

**Key columns:**

| Column              | Meaning                                                                                                                                                                                            |
| ------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `r`                 | Number of processes currently runnable — actively running or waiting for a CPU (this is the CPU-contention half of what feeds load average)                                                        |
| `b`                 | Number of processes **blocked**, uninterruptible sleep / D-state (this is the I/O-wait half feeding load average — §2's `wa` field and this column are two views of the same underlying condition) |
| `us`/`sy`/`id`/`wa` | Same meaning as `top`'s CPU line (2)                                                                                                                                                               |

**Interpretation:** A sustained non-zero `r` well above the core count, alongside a comfortably low `wa`, points toward genuine CPU contention. A sustained non-zero `b`, alongside a high `wa`, points toward I/O contention instead — the same distinction §1's load-average warning raised, now visible as two separate live columns rather than one blended number.

> 💡 **Tip:** Always discard `vmstat`'s first output line — it's a since-boot cumulative average, not a live sample, and reading it as "current state" is a common first-time mistake.

## 5. Worked Diagnostic Scenario: CPU-Bound vs. I/O-Bound vs. Single-Core-Saturated

A host reports `load average: 8.20, 7.95, 6.10` on a 4-core box. All three symptoms below can produce that same load-average reading — the point of this walkthrough is that load average alone cannot tell them apart, but the next two commands can.

**Step 1 — check `top`'s CPU summary line for `wa`:**

- **If `wa` is high (e.g. 60%+)** and `us`+`sy` are comparatively low: the box is **I/O-bound**, not CPU-bound. The high load average is mostly D-state processes stuck on disk/network I/O, not runnable processes contending for CPU cycles. Adding CPU capacity would not help; the investigation moves to §83 (disk I/O tools — `iostat`, `iotop`).
- **If `us`+`sy` together are high and `wa` is low**: the box is genuinely **CPU-bound** — proceed to step 2 to determine whether it's evenly spread or concentrated.

**Step 2 — if CPU-bound, check `mpstat -P ALL` for per-core distribution:**

- **If every core shows comparably high utilization**: the workload is **genuinely, evenly CPU-saturated** — the fix space is scaling out (more instances/cores) or reducing actual CPU work (algorithmic optimization, caching).
- **If one core is pinned near 100% while others sit idle**: the box has **spare aggregate capacity that a single-threaded bottleneck cannot use** (3) — scaling out won't help this specific process; the fix is making the hot code path parallel or accepting its single-core ceiling.

**Step 3 — corroborate with `vmstat 1`'s `r` and `b` columns**, watched over a few seconds rather than one snapshot, to confirm the trend matches: a high `r` with low `b` confirms CPU contention; a high `b` with low `r` confirms I/O blocking; both fluctuating together suggests a mixed workload worth investigating further before concluding either way.

This three-step sequence — load average for "is something queued," `top`'s `wa` for "CPU-bound or I/O-bound," `mpstat` for "evenly saturated or single-core-pinned" — is the concrete, repeatable version of §80's bottleneck-identification principle applied specifically to the CPU resource.

## 6. Common Misconceptions

1. **"Load average is a percentage of CPU capacity used."** It's a count of runnable-plus-uninterruptible-sleep processes, not a percentage of anything — it has no fixed upper bound and must be interpreted relative to core count (1), and critically it includes D-state processes that have nothing to do with CPU contention at all.
2. **"A high `wa` in `top` means the CPU is overloaded."** The opposite — `wa` is time the CPU spent **idle**, specifically idle because it was waiting on I/O rather than having runnable work available (2). High `wa` is evidence the CPU is _not_ the bottleneck.
3. **"If `top`'s aggregate CPU usage looks moderate, CPU isn't the problem."** Aggregates dilute single-core saturation across every core in the average — a workload can be capped by one pegged core while the aggregate reads as comfortably idle (3); `mpstat -P ALL` is required to rule this out.
4. **"`vmstat`'s first line is a useful current reading."** It's a since-boot cumulative average, not a live sample — only subsequent lines reflect the current interval (4).

## 7. Tiered Interview Questions

**🎯 Beginner:** _"What do the three numbers in `load average: 8.42, 6.15, 3.90` actually represent?"_
**Model answer:** They're the 1-minute, 5-minute, and 15-minute exponentially-decaying averages of the run-queue length — the count of processes that are either running/waiting to run on a CPU, or stuck in uninterruptible sleep (D-state) waiting on I/O. It's not a CPU-busy percentage and has no fixed maximum; it needs to be read relative to the number of cores on the box, and the fact that 1-minute is higher or lower than 15-minute tells you whether load is currently rising or subsiding.
_What the interviewer is probing for:_ Whether the candidate knows load average includes D-state processes, not just CPU-runnable ones — the single most common gap.

**🎯 Intermediate:** _"A 4-core server shows load average around 8. What are the possible explanations, and how would you narrow it down?"_
**Model answer:** It could be genuinely CPU-bound (twice as many runnable processes as cores can service), I/O-bound (most of that count is D-state processes waiting on slow disk/network, not CPU contention at all), or some mix. I'd check `top`'s CPU summary line first — a high `wa` percentage points to I/O wait, not CPU saturation, since `wa` is idle-CPU-time-spent-waiting, not busy time. If `wa` is low and `us`+`sy` are high, it's genuinely CPU-bound, and I'd check `mpstat -P ALL` next to see whether that CPU time is spread evenly across all four cores or concentrated on one — the latter suggesting a single-threaded bottleneck rather than true full-machine saturation.
_What the interviewer is probing for:_ The specific tool sequence for disambiguating, not just naming that "it could be CPU or I/O."

**🎯 Senior:** _"You're paged for 'high load' on a host, but the on-call engineer who first looked at it added more application worker processes and it made things worse. What likely happened, and what would you check?"_
**Model answer:** Adding more workers assumes the bottleneck is CPU contention with spare I/O capacity — if the actual bottleneck was I/O wait (a high `wa` in `top`, or a high `b` count in `vmstat`), adding more workers just creates more processes competing to get stuck in the same I/O queue, worsening contention on the actual constrained resource (disk or network) without adding any CPU relief, since CPU wasn't the constraint to begin with. I'd immediately check `top`'s `wa` field and `vmstat 1`'s `r` versus `b` columns to confirm whether the original bottleneck was CPU or I/O before taking any further remediation action, and if it's I/O, redirect the investigation to §83's tools (`iostat`, `iotop`) rather than continuing to add compute capacity that can't help.
_What the interviewer is probing for:_ Recognizing that misdiagnosing I/O-bound load as CPU-bound leads to remediation that actively makes things worse, and knowing the fast diagnostic sequence to catch that before acting.

**🎯 Architect:** _"How would you build automated alerting around CPU health for a fleet, given that load average alone is ambiguous?"_
**Model answer:** I wouldn't alert on raw load average alone — I'd normalize it against core count per host first (load-per-core), then pair it with `wa` percentage (or the equivalent from `/proc/stat` collected by the monitoring agent) so alerts can be classified at generation time as CPU-pressure versus I/O-pressure rather than a single ambiguous "load is high" page. I'd also collect per-core utilization (the `mpstat` view) on a lower-frequency basis, since single-core saturation hidden by aggregates is exactly the kind of issue that silently caps a specific service's throughput without tripping an aggregate-based threshold — a fleet-wide "max single-core utilization" metric catches that class of problem an average never will. The goal is for the alert itself to already point toward §5's diagnostic branch (CPU-bound vs. I/O-bound vs. single-core-pinned) rather than paging someone with just a bare number and making them re-derive the same three-step process from scratch every incident.
_What the interviewer is probing for:_ Designing monitoring that encodes the diagnostic reasoning up front rather than just forwarding a raw, ambiguous metric.

## 8. Key Takeaways

- Load average is a count of runnable-plus-uninterruptible-sleep (D-state) processes, not a CPU-busy percentage — it must be read relative to core count, and a high value can mean CPU-bound, I/O-bound, or both (1).
- `top`'s CPU line breaks down into `us`/`sy`/`ni`/`id`/`wa`/`hi`/`si` — a high `wa` specifically means the CPU is idle waiting on I/O, not CPU-bound at all, the single most important field for the CPU-vs-I/O distinction (2).
- `mpstat -P ALL` reveals per-core utilization, exposing single-core saturation an aggregate view (`top`'s summary line) hides entirely (3).
- `vmstat`'s `r` (runnable) and `b` (blocked) columns are the live, per-second version of load average's two components, and its first output line is a since-boot average that should always be discarded (4).
- The full CPU diagnostic sequence — load average for "is something queued," `top`'s `wa` for CPU-vs-I/O, `mpstat` for evenly-saturated-vs-single-core — is the concrete application of §80's bottleneck-identification model to the CPU resource specifically (5).

## 9. Related Concepts & What's Next

This section is the first of §80's four resource-specific continuations, going deeper on the CPU-diagnostic angle that §34's `top` coverage (Part 5) only introduced at a process-visibility level, and connecting to §38's `nice`/`renice` (Part 5) for the `ni` field's meaning. §82 (next) applies the same resource-specific depth to memory — `free`, `/proc/meminfo`, and the OOM killer — continuing the four-part sequence this Part is built around.

**Next Section:** §82 — `Section-82-Part11-Memory-Analysis.md`
