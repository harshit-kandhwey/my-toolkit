# Section 16 (Part 2): Virtual Memory, Paging, and Swap Fundamentals

## 1. Why Every Process Gets Its Own Virtual Address Space

§10 already stated the headline claim: the memory manager gives each process "the illusion of its own private, contiguous virtual address space." This subsection is about _why_ that illusion exists and what mechanism enforces it.

Two independent problems are solved by the same design:

1. **Isolation.** If processes addressed physical RAM directly, any process could read or corrupt any other process's memory (or the kernel's) simply by guessing an address. Virtual memory makes this structurally impossible, not just policy-forbidden: a process's virtual addresses only resolve to physical pages the kernel has explicitly mapped for it. There is no address a process can construct that reaches another process's private pages, because the translation step — not a permission check on a shared space — is what stands in the way.
2. **The illusion of more memory than physically exists.** A process's virtual address space can be far larger than installed physical RAM (historically the full 32-bit or 48-bit addressable range). Pages are only backed by real physical RAM (or swap) **on demand**, when actually touched — not reserved up front. This is what makes it reasonable for dozens of processes to each behave as if they had gigabytes of address space on a host with far less physical RAM installed in total.

**The MMU (Memory Management Unit).** Address translation is not done in software on every memory access — that would be far too slow. The CPU includes dedicated hardware, the MMU, that translates every virtual address a running instruction touches into a physical address, consulting the current process's page tables (maintained by the kernel, read by the MMU) to do so. The kernel's job is to build and maintain correct page tables; the MMU's job is to walk them at hardware speed, on every single memory access, without the CPU pipeline stalling to ask software each time.

```text
Process's view:                    Reality (kernel + MMU + hardware):
┌─────────────────────┐
│ Virtual Address      │  0x00007fa3...
│ Space (private,      │────────────┐
│ looks contiguous)    │            ▼
└─────────────────────┘      ┌─────────────┐        ┌──────────────────┐
                              │     MMU      │───────►│  Physical RAM     │
                              │ (translates   │        │  (fragmented,     │
                              │  using page    │        │  shared across    │
                              │  tables)       │        │  all processes)   │
                              └─────────────┘        └──────────────────┘
                                     │
                                     ▼ (page not resident)
                              ┌──────────────┐
                              │  Swap space   │
                              │  (disk)       │
                              └──────────────┘
```

> 💡 **Tip:** §10's misconception #4 already flagged this precisely: "virtual address space size is not a promise of physical RAM backing." This subsection is the mechanical explanation of _why_ that's true — demand paging, covered next.

## 2. Paging: Pages, Page Tables, Page Faults, and the TLB

**Fixed-size pages.** Physical RAM and virtual address space are both divided into fixed-size chunks called **pages** — commonly **4 KB** on x86-64 Linux, though the kernel also supports larger **huge pages** (2 MB or 1 GB) for workloads where managing millions of tiny 4 KB entries becomes its own overhead (databases, JVMs, hypervisors are common huge-page users). ⚠️ Exact default page sizes and huge-page support vary by architecture and kernel configuration — verify against `getconf PAGE_SIZE` and `/proc/meminfo`'s `Hugepagesize` on the actual target system rather than assuming a fixed number.

**Page tables.** For each process, the kernel maintains a **page table** — the data structure mapping that process's virtual pages to physical page frames (or marking them as not-yet-resident, or swapped out). Modern architectures use **multi-level page tables** (a tree of tables rather than one flat table) specifically because a flat table covering a full 48-bit address space at 4 KB granularity would itself be unworkably large to keep for every process.

**Page faults.** A page fault occurs when the CPU/MMU cannot complete a virtual-to-physical translation because the referenced virtual page has no valid mapping loaded right now. Contrary to the everyday sense of "fault" as an error, most page faults are a completely normal, expected part of how demand paging works — they are the mechanism by which pages get backed by physical RAM lazily instead of all at once:

| Fault type      | What triggers it                                                                                                                                                                           | Cost                                                                  |
| --------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------- |
| **Minor fault** | The page exists in physical RAM already (e.g., shared library pages another process already loaded, or a page the kernel pre-zeroed) but isn't yet mapped into _this_ process's page table | Cheap — just updates the page table entry, no disk I/O                |
| **Major fault** | The page is not in physical RAM at all and must be read in from disk — either from the backing file (a program binary, memory-mapped file) or from **swap**                                | Expensive — a disk (or swap) I/O, orders of magnitude slower than RAM |

A process that runs entirely out of minor faults is healthy and expected — this is simply demand paging working as designed (first touch of a page, or reuse of an already-resident shared page). A sudden, sustained spike in **major faults** is the real warning sign: it means the working set no longer fits in RAM and the kernel is repeatedly going to disk to service basic memory access, which is the mechanical root cause of the swap performance cliff covered in 3.

**The TLB (Translation Lookaside Buffer).** Walking a multi-level page table on _every single memory access_ would be catastrophically slow if done in full each time — a single memory reference could require several extra memory reads just to resolve the address. The **TLB** is a small, extremely fast hardware cache inside the CPU that stores recently used virtual-to-physical translations, so the MMU can skip the full page-table walk on a cache hit. A **TLB miss** forces the MMU to fall back to the full multi-level page-table walk, which is measurably slower and, at scale under high-frequency memory access (or with many processes causing frequent context switches that flush/invalidate TLB entries), a real contributor to CPU-bound performance degradation — this is part of why huge pages help certain workloads: a 2 MB huge page covers the same virtual range as 512 individual 4 KB pages with a single TLB entry, dramatically reducing TLB pressure for large-memory-footprint applications.

```text
CPU wants to read virtual address X
        │
        ▼
   Check TLB ──── hit ────► Physical address (fast path)
        │
       miss
        │
        ▼
  Walk page tables (multi-level, in RAM) ──► physical address found
        │                                            │
        │                                            ▼
        │                                   Load into TLB for next time
        ▼
  Page table entry says "not resident" ──► PAGE FAULT
        │
        ├─ Minor fault: page is elsewhere in RAM → remap, resume
        └─ Major fault: page must be read from disk/swap → I/O, resume
```

## 3. Swap: The Last Line of Defense Before OOM

When physical RAM fills up and the kernel needs to free some for active work, it does not simply refuse new allocations — it tries to reclaim space first. One reclaim strategy is moving pages that haven't been touched recently (approximately least-recently-used, tracked via active/inactive LRU-style lists) out to **swap space**, a reserved area on disk (a dedicated swap partition or a swap file), freeing the physical RAM those pages occupied for pages actually in use right now. If that page is touched again later, it triggers a major fault and is read back in from swap — this round trip is exactly the mechanism described in 2.

**The performance cliff.** Moving a handful of genuinely cold pages to swap is cheap and largely invisible — this is swap working correctly. The cliff appears when the **working set** (the pages actively being touched) itself exceeds physical RAM: the kernel is then forced to continuously swap pages _out_ to make room, only to swap other pages back _in_ moments later when they're touched again, in a self-defeating cycle informally called **thrashing** or "swapping to death." Because disk I/O (even fast SSD/NVMe) is orders of magnitude slower than RAM access, a host in this state can show near-zero forward progress on real work while CPU and disk both appear saturated servicing swap I/O — one of the most severe and recognizable production performance failures.

> ⚠️ **Warning:** Swap management commands (`swapon`, `swapoff`, configuring a swap file vs. a swap partition) are covered hands-on in **§79** (Part 10, Advanced Storage and LVM). This section is deliberately conceptual — the mechanics of _why_ swap exists and what it costs, not the administration commands for provisioning it.

## 4. The OOM Killer: The Last Resort After Swap Is Exhausted

If physical RAM **and** swap are both exhausted, the kernel reaches a genuine crisis: it cannot honor a memory allocation request, and unlike a userspace program, it cannot simply throw an exception and let something upstream catch it — an unrecoverable kernel-level allocation failure risks a full system deadlock or crash. The **OOM (Out-Of-Memory) Killer** is the kernel's last-resort mechanism for this scenario: it selects a process to kill outright, freeing its memory immediately, specifically to keep the system as a whole alive rather than let it deadlock or crash entirely.

Selection is not random. Each process has a computed **`oom_score`** (visible per-process at `/proc/[pid]/oom_score`) that estimates how much memory it's responsible for, factoring in its own RSS plus children, with adjustments for process age, privilege, and other heuristics — the kernel targets the highest-scoring process first, on the reasoning that killing the single biggest memory consumer frees the most RAM for the least collateral damage. Administrators can bias this decision via **`oom_score_adj`** (`/proc/[pid]/oom_score_adj`, range roughly -1000 to +1000) — setting it to `-1000` makes a process effectively immune to the OOM killer (used sparingly, for genuinely critical processes), while a positive value makes a process a preferred target. ⚠️ The exact scoring formula and available knobs have evolved across kernel versions — verify current behavior against the running kernel's documentation rather than assuming a fixed formula.

🔑 **Key Takeaway:** The OOM killer firing is a symptom, not the root cause — it means RAM _and_ swap were both already exhausted before it acted. Full memory-analysis depth (interpreting `dmesg` OOM kill messages, correlating with `/proc/meminfo`, tuning `oom_score_adj` for critical services) is covered in **§82** (Part 11, Performance and Troubleshooting).

## 5. Hands-On: `free -h` and `/proc/meminfo`

### `free -h`

| Element          | Detail                                                                                                                   |
| ---------------- | ------------------------------------------------------------------------------------------------------------------------ |
| **Purpose**      | Quick human-readable summary of physical RAM and swap usage                                                              |
| **Syntax**       | `free -h` (`-h` = human-readable units; `-s N` repeats every N seconds; `-m`/`-g` force fixed units)                     |
| **Common flags** | `-h` human units, `-s SECONDS` continuous sampling, `-t` add a total row, `-w` split buffers/cache into separate columns |

```bash
$ free -h
              total        used        free      shared  buff/cache   available
Mem:           15Gi       4.2Gi       1.1Gi       412Mi        10Gi        10Gi
Swap:         2.0Gi          0B       2.0Gi
```

**Reading this correctly — the common misreading trap:**

- **`free`** (1.1Gi above) is memory doing _absolutely nothing_ — not even cached. This is the number most people mistakenly treat as "how much memory do I have left," and it is almost always far smaller and far more alarming-looking than the true usable figure.
- **`buff/cache`** (10Gi above) is memory the kernel is using for the page cache and buffers — disk data cached in RAM to speed up future reads, and write-back buffers. Critically, this memory is **reclaimable on demand**: if an application needs it, the kernel drops cache pages instantly (they can simply be re-read from disk later) without ever touching swap.
- **`available`** (10Gi above) is the number that actually answers "how much memory can a new process get right now without swapping" — it is `free` **plus** the portion of `buff/cache` the kernel estimates it can reclaim instantly. This is the column that should drive alerting thresholds, not `free`.

> ⚠️ **Warning:** Monitoring systems that alert on low "free" memory rather than low "available" memory generate persistent false alarms on any healthy Linux host, because a well-behaved kernel deliberately uses nearly all otherwise-idle RAM for page cache — a huge `buff/cache` figure with a tiny `free` figure is _normal and desirable_, not a problem. This exact misreading is common enough that it's worth calling out explicitly here, ahead of the full production memory-analysis treatment in §82.

### `cat /proc/meminfo`

`free -h` is a curated summary of `/proc/meminfo`; the raw file has far more fields for deeper triage:

```bash
$ cat /proc/meminfo | head -12
MemTotal:       16384000 kB
MemFree:         1148392 kB
MemAvailable:   10871204 kB
Buffers:          182044 kB
Cached:          9213880 kB
SwapCached:            0 kB
SwapTotal:        2097148 kB
SwapFree:         2097148 kB
Active:          6213112 kB
Inactive:        4102340 kB
Dirty:               1284 kB
Writeback:              0 kB
```

`Active`/`Inactive` are the LRU-style buckets 3 referenced — `Inactive` pages are the kernel's candidates for reclaim or swap-out first. `Dirty` is cached data modified in memory but not yet flushed to disk — a large sustained `Dirty` figure under I/O pressure is a different diagnostic thread than a pure memory-pressure one. Field-by-field production depth is §82's subject.

## 6. Common Misconceptions

1. **"Any swap usage means the system has a memory problem."** False — a healthy system with plenty of free RAM may still show some nonzero swap usage, because the kernel proactively swaps out genuinely cold, long-untouched pages to keep more RAM available for cache and active work. Some background swap activity is normal and even beneficial; the warning sign is _high swap I/O throughput_ (constant swap-in/swap-out activity, i.e., thrashing), not a nonzero `SwapUsed` figure sitting idle.
2. **"More RAM always eliminates the need for swap."** Not entirely — swap still serves purposes beyond "RAM ran out": it provides a safety margin that lets the kernel absorb a sudden memory spike without immediately invoking the OOM killer, and on many systems swap is a hard requirement for **hibernation** (suspend-to-disk needs somewhere to write the full RAM contents). Disabling swap entirely on a memory-constrained system removes that safety margin and makes the OOM killer fire sooner and more aggressively under pressure.
3. **"`free` in `free -h` tells you how much memory is available for new processes."** Covered in depth above — it doesn't; `available` does, because it accounts for instantly-reclaimable cache.
4. **"A page fault always means something went wrong."** False — minor page faults are a routine, expected part of normal demand-paged memory allocation; only a sustained spike in _major_ faults indicates the working set has outgrown physical RAM.

## 7. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between a minor and a major page fault?"_
**Model answer:** Both happen when the CPU can't complete a virtual-to-physical address translation because the page isn't currently mapped for this process. A minor fault means the page is already somewhere in physical RAM — for example a shared library page another process already loaded — so the kernel just updates this process's page table entry, which is cheap and doesn't touch disk. A major fault means the page isn't in RAM at all and has to be read from disk, either from the file it's backed by or from swap, which is orders of magnitude slower because it involves real I/O.
_What the interviewer is probing for:_ Basic correctness on a frequently-confused pair of terms, and whether the candidate understands that page faults are largely normal rather than always errors.

**🎯 Intermediate:** _"A colleague sees `free -h` reporting only 500MB 'free' on a server with 16GB RAM and says the server is almost out of memory. How do you respond?"_
**Model answer:** I'd point them at the `available` column instead of `free`. `free` only counts memory doing literally nothing — not even cached — while most of the rest is almost always sitting in `buff/cache`, which is the kernel's page cache: reclaimable on demand, dropped instantly if an application needs the RAM, no swap involved. A Linux system deliberately uses nearly all idle RAM for page cache because unused RAM caching disk data is strictly better than unused RAM doing nothing — so a small `free` figure next to a large `buff/cache` figure is expected and healthy, not a warning sign. The number that actually reflects "how much can a new process get right now" is `available`, which already accounts for reclaimable cache.
_What the interviewer is probing for:_ Whether the candidate has actually internalized the free/available distinction rather than just memorized it — this is one of the single most common real production monitoring false alarms.

**🎯 Senior:** _"You're paged for a server that's swapping heavily and feels unresponsive over SSH. Walk through your diagnosis and what you'd check before deciding whether to just add more RAM."_
**Model answer:** First I'd distinguish healthy background swap use from thrashing — check swap I/O rate (via `vmstat` `si`/`so` columns or `/proc/vmstat`), not just `SwapUsed` in isolation, because a nonzero swap figure alone isn't damning. If `si`/`so` are sustained and nonzero, that's the working set exceeding RAM, and I'd correlate with major fault rate and `Active`/`Inactive` memory from `/proc/meminfo` to see how much is genuinely in active use versus reclaimable cache. Before jumping to "just add RAM," I'd also check whether this is a single runaway process (a memory leak or an unbounded cache in the application) via per-process RSS, since fixing one misbehaving process is cheaper and faster than a capacity change, and adding RAM to a host with an actual leak just delays the same failure. I'd also sanity-check whether swap itself is on slow storage — swap on a spinning disk versus NVMe changes how bad the cliff looks for the same swap I/O rate. Only after ruling out a single-process leak and confirming the aggregate working set genuinely exceeds capacity would I treat it as a capacity-planning problem rather than an application bug.
_What the interviewer is probing for:_ Structured incident diagnosis that doesn't jump straight to "add more RAM" — distinguishing symptom from root cause, and whether the candidate knows what specific metrics (si/so, not just SwapUsed) actually confirm thrashing versus normal behavior.

**🎯 Architect:** _"Would you disable swap entirely on latency-sensitive production hosts, e.g., for a low-latency trading or real-time system? What are the trade-offs?"_
**Model answer:** It depends on what you're optimizing against. Disabling swap removes the unpredictable-latency risk of a major fault triggering disk I/O in the middle of a latency-sensitive code path — for a system where p99.9 tail latency matters more than absolute uptime under memory pressure, that's a real and legitimate argument, and it's a pattern I've seen used deliberately alongside strict memory-limit enforcement (cgroups) so the workload simply can't exceed physical RAM in the first place. The trade-off is that without swap, the safety margin before the OOM killer fires is gone — any memory spike beyond physical RAM goes straight to OOM kills rather than being absorbed by swap, so this decision only makes sense paired with aggressive memory limits, capacity headroom, and monitoring, not as a standalone tuning knob. I'd also flag that this removes hibernation as an option on that host, which is usually irrelevant for a server but worth stating explicitly. So: yes, situationally, but only as part of a broader memory-governance strategy (cgroup limits, capacity planning, §82's monitoring), never as an isolated "swap is generally bad" default.
_What the interviewer is probing for:_ Whether the candidate can reason about a genuine architectural trade-off with real costs on both sides, rather than reciting either "always keep swap on" or "swap is legacy, always disable it" as an absolute rule.

## 8. 🔑 Key Takeaways

- Every process gets its own virtual address space for two reasons: **isolation** (structurally, not just by policy) and the **illusion of more memory than physically exists**, backed on demand.
- The **MMU** translates virtual to physical addresses at hardware speed on every access, consulting the kernel-maintained **page tables**.
- **Minor faults** are cheap and routine (page already in RAM, just needs a mapping); **major faults** are expensive (real disk/swap I/O) — a spike in major faults is the real warning sign, not page faults in general.
- The **TLB** caches recent translations so most accesses skip the full page-table walk; TLB misses and pressure are a genuine performance factor, part of why huge pages exist.
- **Swap** lets the kernel free RAM by writing cold pages to disk; this is healthy in moderation and becomes a severe performance cliff ("thrashing") only when the active working set itself exceeds physical RAM.
- The **OOM killer** is the last resort after RAM and swap are both exhausted, using `oom_score`/`oom_score_adj` to pick a target — its firing is a symptom that prior capacity was already gone, not the root cause itself.
- In `free -h`, **`available` — not `free`** — is the number that reflects real usable memory, because it accounts for instantly-reclaimable page cache (`buff/cache`).
- Nonzero swap usage alone is not a problem signal; sustained swap I/O throughput (thrashing) is.

## 9. Common Misconceptions (Part 2 Summary)

Synthesizing the strongest, most interview-relevant misconceptions across §8–§16:

1. **"The kernel is one big undifferentiated blob of code."** False — "monolithic" (§9) describes the _privilege/address-space model_ (all subsystems run in one privileged kernel space, sharing one address space, for performance), not a lack of internal structure. Internally the kernel decomposes cleanly into the process scheduler, memory manager, VFS, network stack, and device drivers (§10), each a distinct subsystem with its own internal boundaries — "monolithic" and "modular internal design" are not contradictory.
2. **"User space programs talk to the kernel however they want."** False — the system call interface (§11) is the sole sanctioned, stable boundary between user space and kernel space; it's precisely what makes a program a legitimate user-space application rather than a derivative work requiring kernel-level privilege, and it's the same boundary GPLv2 derivative-work reasoning (§3, Part 1) depends on.
3. **"CFS uses fixed time slices like older round-robin schedulers."** False (§10) — CFS makes scheduling decisions based on tracked virtual runtime fairness, not a fixed quantum.
4. **"Boot is just 'power on, then the OS starts.'"** False (§12) — boot is a multi-stage handoff (BIOS/UEFI → bootloader/GRUB → kernel → initramfs → init/systemd), and a failure at any single stage produces a distinctly different symptom, which is why boot troubleshooting depends on identifying _which_ stage failed, not treating "won't boot" as one undifferentiated failure mode.
5. **"All init systems are basically interchangeable and the choice doesn't matter."** False (§13) — SysVinit, Upstart, and systemd differ meaningfully in parallelism, dependency expression, and tooling, and "which init system does this distro use" changes both boot behavior and the correct administration commands (full depth: Part 9, §65–§72).
6. **"Kernel modules are a niche/desktop-only feature."** False (§14, and §10's misconception #3) — loadable kernel modules are how a single kernel image supports wildly different server and cloud hardware (including `virtio` drivers in virtualized/cloud environments) without recompilation; a missing or mismatched module is a common real cause of cloud instances failing to detect disks or NICs at boot.
7. **"Interrupts and context switches are the same thing."** False (§15) — an interrupt is a hardware/software signal that asynchronously demands CPU attention; a context switch is the kernel's act of saving one task's state and loading another's, which an interrupt handler may trigger but is not itself synonymous with.
8. **"Virtual address space size promises physical RAM backing."** False (§10, §16) — virtual memory is demand-paged; pages are mapped to physical RAM (or swap, or nothing yet) only when actually touched.
9. **"Any swap usage means a memory problem."** False (§16) — some swap usage of genuinely cold pages is normal and beneficial; sustained swap I/O throughput, not a nonzero swap figure, is the actual warning sign.

## 10. Part 2 🔑 Key Takeaways Checklist

```text
□ System architecture layers as Hardware → Kernel → Userland/System Software →
  Applications, and each higher layer depends on the correctness of every layer
  beneath it (§8)
□ The Linux kernel is monolithic — all subsystems run in one privileged kernel
  space sharing one address space — which is a privilege/performance model, not
  an absence of internal structure (§9)
□ The kernel internally decomposes into five major subsystems: process scheduler
  (CFS), memory manager, VFS, network stack, device drivers — each with its own
  full-depth Part later in this roadmap (§10)
□ System calls are the sole sanctioned, stable boundary between user space and
  kernel space — every userspace request to any of the five subsystems crosses
  this boundary (§11)
□ Boot is a multi-stage pipeline — BIOS/UEFI → bootloader (GRUB) → kernel →
  initramfs → init/systemd — and troubleshooting depends on isolating which
  stage failed (§12)
□ init systems evolved SysVinit → Upstart → systemd, with systemd now dominant
  across major distros; the choice materially affects boot parallelism and
  administration tooling (§13, full depth Part 9 §65–§72)
□ Kernel modules (lsmod, modprobe, insmod) let one kernel image support diverse
  hardware, including cloud/virtualized devices, without recompilation (§14)
□ Interrupts asynchronously demand CPU attention; the scheduler and context
  switching decide/execute which task actually runs next — related but distinct
  mechanisms (§15)
□ Virtual memory gives each process isolation and the illusion of more memory
  than physically exists, via MMU-translated, demand-paged, page-table-backed
  addressing (§16)
□ Minor page faults are cheap and routine; major faults (real disk/swap I/O) are
  the real cost signal; the TLB caches translations to avoid full page-table
  walks on every access (§16)
□ Swap is a normal pressure-relief valve until the working set exceeds RAM, at
  which point thrashing causes a severe, recognizable performance cliff; the
  OOM killer is the last-resort mechanism after RAM and swap are both
  exhausted (§16)
□ free -h's "available" column, not "free," is the correct number for real
  usable memory, because it accounts for reclaimable page cache (§16)
```

## 11. Related Concepts & What's Next

- **Part 3 — The Filesystem and Storage Basics (§17–§24)** is next, and is the direct expansion of the VFS subsystem §10 introduced only conceptually: the Filesystem Hierarchy Standard, filesystem types (ext4, XFS, Btrfs, ZFS, tmpfs, overlayfs), inodes and links, mounting, and `/proc`/`/sys` as the live kernel-introspection interfaces this Part has already been reading from repeatedly (`/proc/meminfo`, `/proc/[pid]/sched`, `/proc/filesystems`).
- **Part 5 (§33–§40)** returns to the process scheduler and full process lifecycle §10 introduced only conceptually — `nice`/`renice`, signals, fork/exec/wait, zombie processes.
- **Part 7 (§51–§58)** returns to the network stack §10 introduced only conceptually, at full protocol and diagnostic depth.
- **Part 9 — Systemd and Services (§65–§72)** is the full depth treatment of the init-system material §13 covered only comparatively.
- **Part 10 — Advanced Storage and LVM (§73–§79)**, specifically **§79**, covers hands-on swap administration (`swapon`, `swapoff`, swap file vs. partition) that this section deliberately deferred.
- **Part 11 — Performance, Monitoring, and Troubleshooting (§80–§88)**, specifically **§82** (memory analysis depth, OOM killer tuning, `/proc/meminfo` field-by-field) and **§88** (the unified subsystem-based troubleshooting methodology §10 previewed), is where this Part's conceptual foundations become full production diagnostic skill.
- **Part 13 (§97–§102)** returns to kernel primitives — namespaces, cgroups, chroot, OverlayFS — as the foundation for containers, building on the kernel-space/user-space and monolithic-design vocabulary established in §9.

**Next:** Part 3 — The Filesystem and Storage Basics (§17–§24)
