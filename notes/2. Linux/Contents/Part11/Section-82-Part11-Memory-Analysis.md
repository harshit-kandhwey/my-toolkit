# Section 82 (Part 11): Memory Analysis: free, /proc/meminfo, OOM Killer

## 1. `free -h`: Reading Used vs. Available Correctly

§81 covered CPU-specific diagnostic tools as the first of the four resource-specific continuations §80 set up. This section moves to memory, and opens with the single most consequential misreading in all of Linux performance work: what "used" memory actually means.

**Purpose:** Show a summary of total, used, free, and available memory, plus swap, in one command.

**Syntax:**

```bash
free -h
```

**Key flags:**

| Flag   | Meaning                                            |
| ------ | -------------------------------------------------- |
| `-h`   | Human-readable units (GiB/MiB rather than raw KiB) |
| `-s N` | Repeat every N seconds, for watching a trend live  |

**Example usage and expected output:**

```bash
$ free -h
               total        used        free      shared  buff/cache   available
Mem:            15Gi       2.1Gi       0.3Gi        45Mi        13Gi        13Gi
Swap:          2.0Gi          0B       2.0Gi
```

> ⚠️ **Warning:** A system showing only `0.3Gi` free is, in the overwhelming majority of cases, **not a problem** — and reading it as one is the misconception this whole section exists to correct. The `free` column only counts memory doing absolutely nothing. The `buff/cache` column (13Gi here) is memory the kernel is using productively for page cache and buffers (2), and almost all of it is **instantly reclaimable** the moment an application actually needs it. The number that matters is **`available`** — the kernel's own estimate of how much memory could be handed to a new process right now without swapping, accounting for that reclaimable cache. A healthy, well-utilized Linux host is _supposed_ to show low "free" and high "available" — Linux deliberately uses idle RAM for caching rather than leaving it sitting empty, because idle RAM doing nothing is a wasted resource, not a safety margin.

The practical rule: **judge memory pressure by `available`, never by `free`.** A low `available` figure — not a low `free` figure — is the actual signal worth investigating.

## 2. `/proc/meminfo`: The Detail Behind `free`'s Summary

`free`'s columns are a curated summary computed from a much more detailed source: `/proc/meminfo` (§24, Part 3, introduced `/proc` as a virtual filesystem for kernel introspection generally — this is one of its most frequently read files in practice).

**Purpose:** Expose the full set of kernel memory-accounting figures `free` summarizes, useful when `free -h` alone doesn't answer a specific question.

**Syntax:**

```bash
cat /proc/meminfo
```

**Example usage and expected output (abridged to the fields that matter most):**

```bash
$ cat /proc/meminfo
MemTotal:       16384000 kB
MemFree:          320000 kB
MemAvailable:   13500000 kB
Buffers:          210000 kB
Cached:         12800000 kB
SwapTotal:       2097152 kB
SwapFree:        2097152 kB
```

| Field                    | Meaning                                                                                                                                                                                    |
| ------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `MemTotal`               | Total installed, usable RAM                                                                                                                                                                |
| `MemFree`                | Memory doing literally nothing — the same figure as `free`'s `free` column, and just as misleading read alone                                                                              |
| `MemAvailable`           | The kernel's estimate of memory available for new allocations without swapping — accounts for reclaimable cache, and is the figure `free -h`'s `available` column is derived from directly |
| `Buffers`                | Raw block-device I/O buffers (a comparatively small component)                                                                                                                             |
| `Cached`                 | Page cache — file data the kernel is holding in RAM after reading it from disk (2 goes deeper)                                                                                             |
| `SwapTotal` / `SwapFree` | Total configured swap, and how much of it is currently unused                                                                                                                              |

**Production usage example:** `MemAvailable` didn't always exist as a kernel-provided field — administrators used to hand-estimate "true" available memory by summing `MemFree` + `Buffers` + `Cached`, which overestimates in some cases because not all cached pages are equally reclaimable. Modern kernels compute `MemAvailable` properly, and any monitoring or alerting built on memory pressure should read this field directly rather than reimplementing an approximation of it.

## 3. The Page Cache: A Feature, Not Consumed Memory

The `Cached` figure in §2 deserves its own explanation because it's the mechanism behind §1's warning, not just a number that happens to be large.

The **page cache** is the kernel opportunistically using otherwise-idle RAM to hold copies of recently-read (and recently-written, pending flush) file data. The next time that same data is requested — the same file read again, the same database page accessed again — the kernel can serve it straight from RAM instead of going back to disk, which is dramatically faster. This happens automatically and transparently: applications don't request it, and most don't even know it's happening.

Two properties make this genuinely a feature rather than memory being wasted:

- **It's free to use.** The kernel fills spare RAM with page cache precisely because idle RAM produces zero benefit sitting empty — using it to speed up subsequent disk reads costs nothing as long as nothing else needs that memory.
- **It's reclaimed instantly under pressure.** The moment an application actually needs memory the page cache is occupying, the kernel evicts cached pages (discarding clean ones outright, since they're just a copy of data still safely on disk) and hands the freed memory to the requesting application, essentially immediately. This reclaim is what makes `MemAvailable` a meaningful number rather than a hopeful estimate — it's counting memory the kernel can genuinely get back on demand, not "memory that would need something risky to free."

> 💡 **Tip:** A useful gut-check when someone reports "the server is almost out of memory" based on `free`'s `free` column: ask what `available` shows first, and separately whether swap usage is actually climbing (§77, Part 10, covers swap management directly) — climbing swap usage under sustained low `available` is a real pressure signal; a large `buff/cache` figure with high `available` is not a problem at all.

## 4. The OOM Killer: What Triggers It and How It Chooses a Victim

Page cache reclaim (3) handles the common case of memory pressure gracefully. The **OOM (Out-Of-Memory) killer** is the kernel's last resort for the case reclaim can't solve: genuinely running out of allocatable memory _and_ swap, with no reclaimable cache left to free and no way to satisfy a memory request any other way.

**What triggers it:** The OOM killer activates when the kernel cannot satisfy a memory allocation request through any combination of free memory, reclaimable cache, and available swap. This is a materially different, more severe condition than "cache is large" or "available is moderate" — it's the kernel genuinely unable to grant memory to something that's asking for it.

**How it chooses a victim:** Rather than failing the allocation and crashing whatever asked for it, the kernel selects a process to kill outright, freeing its memory to relieve the pressure. The selection is driven by a per-process **`oom_score`**, computed heuristically from factors including how much memory the process is using (larger consumers score higher, all else equal), how long it's been running, and its `oom_score_adj` setting (5). The process with the highest score is the one killed — the heuristic aims for "the process most likely to be the actual cause of the pressure, and least likely to be critical," but it's a heuristic, not a guarantee it picks correctly.

**Finding evidence the OOM killer fired:** The kernel logs an OOM kill event, and it's visible via `dmesg` or the journal (§68's journald coverage, Part 9, applies directly — kernel messages land in the journal too):

```bash
dmesg | grep -i "out of memory"
journalctl -k | grep -i "killed process"
```

A typical log line names the killed process, its PID, and its `oom_score`, which is the fastest way to confirm after the fact that a mysteriously-vanished process was actually OOM-killed rather than crashing on its own or being stopped deliberately.

> ⚠️ **Warning:** A process disappearing without an obvious crash log of its own, especially on a host that had climbing memory pressure beforehand, should always be checked against `dmesg`/`journalctl -k` for an OOM kill before being investigated as an application-level bug — the two look similar from the application's own logs (which simply stop) but have completely different root causes and remediation paths.

## 5. `oom_score_adj`: Protecting Critical Processes

**`oom_score_adj`** is a real, per-process tunable — writable under `/proc/<pid>/oom_score_adj` — that biases the OOM killer's victim-selection heuristic (4) for a specific process, without changing the underlying memory-pressure condition itself.

**Syntax:**

```bash
# View current value
cat /proc/<pid>/oom_score_adj

# Adjust: range is -1000 to +1000
echo -500 > /proc/<pid>/oom_score_adj
```

| Value           | Effect                                                                           |
| --------------- | -------------------------------------------------------------------------------- |
| `-1000`         | Process is **never** selected by the OOM killer — a strong, deliberate exemption |
| Negative values | Make the process **less likely** to be chosen as the victim                      |
| `0`             | Default, unadjusted                                                              |
| Positive values | Make the process **more likely** to be chosen as the victim                      |

**Production usage example:** A host running a critical, low-memory-footprint control-plane process alongside larger, more expendable batch or worker processes is a reasonable candidate for setting a strongly negative `oom_score_adj` on the critical process — biasing the kernel toward killing a large batch job instead of the small but essential process, if memory pressure ever does escalate to that point. systemd unit files expose this as the `OOMScoreAdjust=` directive (§67, Part 9, covers unit file syntax generally), which is the normal way to set it declaratively rather than writing to `/proc` by hand on every boot.

**Common errors:** Treating `oom_score_adj` as a substitute for actually fixing a memory-pressure problem — it changes _who_ gets killed when the kernel truly runs out of memory, not _whether_ that condition happens at all; a process protected with `-1000` on a host that keeps hitting genuine OOM conditions will simply force something else to be killed each time, without addressing the underlying capacity or leak problem.

## 6. Common Misconceptions

1. **"Low 'free' memory means the system is almost out of memory."** The `free` column only counts memory doing nothing at all — a low `free` figure alongside a high `buff/cache` and high `available` is normal, healthy behavior, not a warning sign (1).
2. **"Page cache is memory being consumed/wasted by the OS."** It's memory the kernel is using productively to speed up repeated disk reads, filled opportunistically because idle RAM produces no benefit sitting empty, and it's reclaimed essentially instantly the moment an application actually needs that memory (3).
3. **"The OOM killer fires whenever memory usage looks high."** It fires only when the kernel cannot satisfy an allocation through any combination of free memory, reclaimable cache, and swap — a high `buff/cache` figure or even a moderate `available` figure is nowhere near this condition (4).
4. **"A killed process's own logs will show why it died."** An OOM-killed process is terminated abruptly by the kernel — its own application logs simply stop, with no self-generated crash message; the evidence lives in `dmesg`/`journalctl -k`, not the application's own log output (4).

## 7. Tiered Interview Questions

**🎯 Beginner:** _"`free -h` shows very little in the 'free' column. Is that a problem?"_
**Model answer:** Almost certainly not, by itself. The `free` column only counts memory doing nothing at all — Linux deliberately fills spare RAM with page cache to speed up disk access, and that cache shows up under `buff/cache`, not `free`. The number that actually indicates memory pressure is `available`, which accounts for how much of that cache could be reclaimed instantly if an application needed the memory. Low `free` with high `available` is normal, healthy behavior on a well-utilized host.
_What the interviewer is probing for:_ Whether the candidate has internalized the used-vs-available distinction rather than reacting to a surface-level low number.

**🎯 Intermediate:** _"Walk me through what actually triggers the OOM killer, and how it picks which process to kill."_
**Model answer:** It fires only when the kernel can't satisfy a memory allocation through free memory, reclaimable page cache, or available swap combined — not just because usage looks high. Once that condition is hit, the kernel picks a victim based on each process's `oom_score`, a heuristic weighted by memory consumption and other factors, further adjustable per-process via `oom_score_adj` — a value of -1000 exempts a process entirely, positive values make it more likely to be picked. Evidence that it fired shows up in `dmesg` or `journalctl -k`, since the killed process's own logs just stop without explanation.
_What the interviewer is probing for:_ Accurate sequencing — trigger condition, then victim selection, then where to find evidence — rather than a vague "it kills something when memory is low."

**🎯 Senior:** _"A critical process died with no application-level error, and the host's monitoring showed climbing memory usage beforehand. How do you investigate, and how would you prevent a recurrence?"_
**Model answer:** First, confirm it was actually an OOM kill via `dmesg`/`journalctl -k` rather than assuming — an application-level crash and an OOM kill can look identical from the outside if you only check the app's own logs. If confirmed, I'd look at what was actually consuming memory in the lead-up (via historical monitoring, or `/proc/meminfo`'s `MemAvailable` trend if retained) to find the actual pressure source — often a separate process leaking or genuinely growing, not necessarily the process that got killed, since the OOM heuristic doesn't always pick the true root cause. For prevention, I'd consider whether the critical process needs `oom_score_adj` protection (via systemd's `OOMScoreAdjust=`) so a future pressure event kills something more expendable instead — but I'd treat that as damage mitigation, not a fix, since it doesn't address why the host hit genuine OOM in the first place; that requires either more capacity, fixing a leak, or better memory limits on the actual consumer.
_What the interviewer is probing for:_ Distinguishing "protect the critical process" from "fix the root cause," and not assuming the killed process is automatically the one that caused the pressure.

**🎯 Architect:** _"How would you design memory-pressure alerting for a fleet, given that 'free' memory numbers are so commonly misread?"_
**Model answer:** I'd alert on `MemAvailable` (or `free -h`'s `available` column) trending down and staying low, combined with actual swap utilization trending up, rather than on raw `free` or even on `buff/cache` size, since both of those are expected to be large on a healthy, well-utilized host and produce constant false positives if used naively. I'd also build in OOM-kill detection as its own distinct alert — scraping `dmesg`/journald for OOM kill events — since that's an unambiguous, high-severity signal that shouldn't wait for a memory-percentage threshold to catch it after the fact. For genuinely critical system processes, I'd bake `OOMScoreAdjust=` into their standard unit-file template as a baseline protection, while making clear in runbooks that this changes victim selection during an OOM event, not whether the event happens — capacity planning and leak detection remain the actual prevention layer, with OOM-kill alerting as the safety net for when they fail.
_What the interviewer is probing for:_ Building alerting around the metrics that actually indicate pressure (available, swap trend, OOM events) rather than the intuitive-but-misleading ones (free, cache size), and separating mitigation from root-cause prevention.

## 8. Key Takeaways

- `free -h`'s `available` column, not its `free` column, is the correct measure of memory pressure — low `free` with high `buff/cache` and high `available` is normal, healthy behavior (1).
- `/proc/meminfo` provides the full detail behind `free`'s summary, including `MemAvailable`, the kernel's own reclaim-aware estimate that should be read directly rather than hand-approximated (2).
- The page cache is a deliberate performance feature — spare RAM opportunistically holding recently-read file data — not consumed or wasted memory, and it's reclaimed essentially instantly under real pressure (3).
- The OOM killer fires only when free memory, reclaimable cache, and swap combined are exhausted, selecting a victim via the `oom_score` heuristic; evidence it fired lives in `dmesg`/`journalctl -k`, not the killed process's own logs (4).
- `oom_score_adj` (or systemd's `OOMScoreAdjust=`) is a real tunable for biasing victim selection toward or away from a specific process, but it changes _who_ gets killed, not _whether_ genuine OOM pressure occurs — it's mitigation, not a root-cause fix (5).

## 9. Related Concepts & What's Next

This section builds directly on §16's virtual memory/paging/swap fundamentals (Part 2) and §77's swap management coverage (Part 10), and connects to §68's journald coverage (Part 9) for where OOM kill evidence actually lives. It follows §81's CPU-specific diagnostics as the second of §80's four resource-specific continuations. §83 (next) moves to disk I/O — `iostat`, `iotop`, `df`, `du` — continuing the same resource-specific pattern for the third of the four resources.

**Next Section:** §83 — `Section-83-Part11-Disk-IO-Analysis.md`
