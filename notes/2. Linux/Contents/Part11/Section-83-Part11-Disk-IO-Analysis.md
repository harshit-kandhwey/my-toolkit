# Section 83 (Part 11): Disk I/O Analysis: iostat, iotop, df, du

## 1. `df -h`: Filesystem-Level Space Usage

§82 covered memory diagnostics as the second of §80's four resource-specific continuations — and touched on how page cache and dirty pages relate to when writes actually land on disk, a thread this section picks back up when discussing why space and throughput are different questions entirely. This section moves to disk, starting with the most basic question: how full is each filesystem.

**Purpose:** Show space usage per mounted filesystem — total, used, available, and percent used.

**Syntax:**

```bash
df -h
```

**Key flags:**

| Flag | Meaning                                                                                                                                                                      |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-h` | Human-readable units                                                                                                                                                         |
| `-i` | Show **inode** usage instead of block/space usage — a filesystem can be 100% full on inodes while showing plenty of free space, if it holds an enormous number of tiny files |

**Example usage and expected output:**

```bash
$ df -h
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        50G   48G  0.0G 100% /
tmpfs           3.9G     0  3.9G   0% /dev/shm
```

> ⚠️ **Warning:** A filesystem reporting `100%` used immediately after a large file was deleted — and staying at 100% — is a genuinely common and confusing gotcha, and it isn't a `df` bug. If a process still has that file **open** at the time it was deleted, the underlying disk blocks are **not released** until every process holding it open closes it (or exits). The directory entry (the name) is gone, `ls` won't show it, but the inode and its data blocks persist, still counted as used space, for as long as any file descriptor referencing it remains open — a direct consequence of the inode/link-count model §19 (Part 3) covers. The fix is finding and dealing with the holding process, not deleting the (already invisible) file again.
>
> **Diagnostic command:**
>
> ```bash
> lsof | grep deleted
> ```
>
> This lists open file handles pointing at files that have been unlinked from the directory tree but are still held open — the exact signature of this scenario. The size reclaimed once the holding process closes the file (or is restarted) is usually immediately visible in `df`'s output.

## 2. `du`: Directory-Level Usage

`df` answers "how full is this filesystem"; `du` answers the natural follow-up — "which directory is actually eating that space."

**Purpose:** Report disk usage recursively for files and directories, letting you drill down from a full filesystem to the specific directory responsible.

**Syntax:**

```bash
du -sh /path
du -h --max-depth=1 /path
```

**Key flags:**

| Flag            | Meaning                                                                                                                       |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| `-s`            | Summarize — total for the given path only, not every subdirectory individually                                                |
| `-h`            | Human-readable units                                                                                                          |
| `--max-depth=1` | Show one level of subdirectories individually, rather than either a single total (`-s`) or every nested directory recursively |

**Example usage and expected output — a practical "what's eating this directory" workflow:**

```bash
$ du -sh /var
12G     /var

$ du -h --max-depth=1 /var
8.2G    /var/log
3.1G    /var/lib
0.5G    /var/cache
12G     /var
```

This two-step pattern — total first with `-sh`, then one level deeper with `--max-depth=1` — repeated on whichever subdirectory looks disproportionately large, is the standard way to walk down a filesystem tree toward the actual offender without recursing through every file individually.

> 💡 **Tip:** `du`'s totals and `df`'s totals for the same filesystem can legitimately disagree, and it's worth knowing why before assuming one of them is wrong. Beyond the deleted-but-open-file scenario in §1 (which `du` never sees, since it can't count a file with no directory entry, while `df` still counts its blocks as used), **sparse files** are the other common cause — a file can report a large logical size but occupy far fewer actual disk blocks, and `du` by default reports actual block usage while some tools report logical size, producing numbers that look inconsistent unless the sparse-file behavior is understood.

## 3. `iostat`: Throughput and Latency, Not Space

`df` and `du` answer _space_ questions. Neither tells you whether the disk is actually **struggling to keep up** with the I/O being asked of it — a filesystem can have plenty of free space while still being the performance bottleneck. `iostat` is the tool for that different question.

**Purpose:** Report per-device I/O throughput, utilization, and latency statistics.

**Syntax:**

```bash
iostat -x 1
```

**Key flags:**

| Flag | Meaning                                                                                                             |
| ---- | ------------------------------------------------------------------------------------------------------------------- |
| `-x` | Extended statistics — utilization, average queue size, and latency breakdowns, not just raw throughput              |
| `1`  | Repeat every 1 second, since a single snapshot (like `vmstat`, §81) is far less informative than watching the trend |

**Example usage and expected output:**

```bash
$ iostat -x 1
Device            r/s     w/s   rkB/s   wkB/s  await  svctm  %util
sda              12.0    85.0   480.0  6800.0   45.20   1.10  92.30
```

**Key columns:**

| Column                                             | Meaning                                                                                                                                                                                                                                                       |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `%util`                                            | Percentage of time the device had at least one I/O request outstanding — the closest single-number analog to "how saturated is this disk," though it can understate saturation on devices capable of servicing multiple requests in parallel (some SSDs/NVMe) |
| `await`                                            | **Average time an I/O request spends waiting**, including queueing time plus actual service time — this is what an application actually experiences as I/O latency                                                                                            |
| `svctm`                                            | Average time the device itself took to service a request, excluding queue wait — deprecated/unreliable on many modern kernels, but conceptually the piece of `await` that isn't queueing delay                                                                |
| queue depth (`avgqu-sz` on some `iostat` versions) | Average number of I/O requests queued waiting — a rising queue depth alongside rising `await` is the clearest sign of a device that can't keep up with demand                                                                                                 |

**Interpretation:** A large gap between `await` and `svctm` means most of the latency an application experiences is **queueing delay**, not the device's raw per-request speed — the disk is receiving more requests than it can service concurrently, which is a saturation signal distinct from "this disk is just slow." `%util` near 100% alongside climbing `await` is the clearest overall signature of a disk that's the actual bottleneck.

**Production usage example:** "The database feels slow" investigations frequently start with `iostat -x 1` running against the underlying volume — a high `await` with high `%util` confirms the storage layer itself is saturated, redirecting the investigation away from query tuning and toward storage throughput, volume type, or I/O-pattern changes.

## 4. `iotop`: Per-Process I/O Attribution

`iostat` confirms a device is saturated; it says nothing about **which process** is generating the load. `iotop` is to disk I/O what `top` is to CPU (§81) — a live, per-process view of who's actually responsible.

**Purpose:** Show real-time disk I/O usage broken down by process, identifying the specific process generating read/write load.

**Syntax:**

```bash
sudo iotop
sudo iotop -oa
```

**Key flags:**

| Flag | Meaning                                                                                                                                                |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `-o` | Only show processes actually performing I/O, rather than every process (most show zero)                                                                |
| `-a` | Show accumulated I/O since `iotop` started, rather than a per-refresh instantaneous rate — smooths out bursty processes into a clearer overall picture |

**Example usage and expected output:**

```bash
$ sudo iotop -oa
  PID  PRIO  USER     DISK READ  DISK WRITE  SWAPIN  IO>    COMMAND
 4821  be/4  postgres    1.2 G     340.0 M     0.00 %  62.10 % postgres: writer
 5103  be/4  root        0.0 B     890.0 M     0.00 %  15.40 % tar -czf backup.tar.gz /data
```

**Interpretation:** In this example, a database writer process and a running backup job are the two actual I/O consumers — directly identifying which one to investigate (or reschedule, if the backup job is contending with production database I/O during business hours) rather than treating "the disk is busy" as an undifferentiated fact.

**Common errors:** Running `iotop` without root privileges — it requires elevated access to read per-process I/O accounting, and will show empty or heavily restricted output otherwise.

## 5. Worked Diagnostic Flow: "The Disk Is Slow"

A vague report like "the disk is slow" or "the app feels sluggish and we suspect storage" benefits from a fixed sequence rather than jumping straight to any one tool:

1. **Rule out space pressure first** — `df -h` (1) to confirm the filesystem isn't near 100% full (some filesystems degrade in write performance as they approach capacity, independent of raw I/O throughput), and `du -sh --max-depth=1` (2) if it is, to find what's actually consuming the space.
2. **Confirm throughput/latency saturation** — `iostat -x 1` (3), watching `%util` and `await` over a live window rather than a single snapshot. If `%util` is low and `await` is small, the underlying storage isn't actually struggling, and the "slowness" likely has a different root cause entirely (application logic, network, a different resource from §80's model).
3. **Attribute the load to a specific process** — `iotop` (4), once storage saturation is confirmed, to identify exactly which process is driving it, distinguishing "the whole workload legitimately needs this much I/O" from "one unexpected process (a backup job, a runaway log write, a misbehaving service) is consuming disk capacity that should be going to something else."

This space-then-throughput-then-attribution ordering mirrors §81's CPU sequence (load average → `top`'s `wa` → `mpstat`) and §82's memory sequence (`free`'s `available` → `/proc/meminfo` detail → OOM evidence) — each resource-specific section in this Part follows the same broad shape: a coarse signal, a more detailed breakdown, then per-process attribution, all in service of §80's general bottleneck-identification model.

## 6. Common Misconceptions

1. **"Deleting a file always immediately frees its disk space."** Not if a process still has it open — the space isn't released until the last open file descriptor referencing it is closed, even though the file is invisible in the directory tree already (1). `lsof | grep deleted` is the diagnostic for this exact scenario.
2. **"`du` and `df` totals for the same filesystem should always match."** They commonly diverge because of the deleted-but-open scenario above (which `du` can't see at all) and sparse files (where logical and actual block usage differ) — a mismatch isn't necessarily a bug in either tool (2).
3. **"A full disk and a slow disk are the same problem."** Space usage (`df`/`du`) and throughput/latency saturation (`iostat`) are entirely different dimensions — a filesystem can have abundant free space while still being I/O-saturated, and a nearly-full filesystem can have perfectly healthy throughput (3, 5).
4. **"`iostat` showing high `%util` tells you which process to fix."** It confirms the device is saturated but says nothing about attribution — `iotop` is the tool for identifying the responsible process (4).

## 7. Tiered Interview Questions

**🎯 Beginner:** _"`df -h` shows a filesystem at 100% used, but you deleted a large file and it's still showing 100%. What's going on?"_
**Model answer:** The file's directory entry is gone, but if some process still has it open, the actual disk blocks aren't released until every open file descriptor referencing it is closed — Linux keeps a file's data alive as long as either a directory entry or an open handle references it. `lsof | grep deleted` finds exactly this situation — open handles pointing at unlinked (deleted) files — and the space frees up once the holding process closes the file or is restarted.
_What the interviewer is probing for:_ Connecting the symptom to the inode/open-file-descriptor model rather than assuming `df` is simply wrong or stale.

**🎯 Intermediate:** _"What's the difference between what `df`/`du` tell you and what `iostat` tells you, and why would you need both?"_
**Model answer:** `df` and `du` are about space — how much capacity is used and by what, at the filesystem and directory level respectively. `iostat` is about throughput and latency — how much I/O is actually flowing through a device and how long requests are taking, via metrics like `%util` and `await`. A disk can be nearly empty and still be the performance bottleneck if it's I/O-saturated, and a disk can be nearly full with perfectly fine throughput if nothing is actively hammering it — they're independent dimensions, and a full "is disk a problem" investigation checks both rather than assuming one implies the other.
_What the interviewer is probing for:_ Recognizing space and throughput as genuinely separate concerns, not two views of the same underlying number.

**🎯 Senior:** _"`iostat -x` shows a device at 95% `%util` with high `await`. How do you find out what's actually driving that, and what would you look at next?"_
**Model answer:** `iostat` confirms the device is saturated but doesn't attribute it to a process, so the next step is `iotop -oa` to see which process is generating the read/write load in practice — accumulated mode smooths out bursty processes for a clearer picture than the instantaneous rate. Once attributed, the remediation depends on what's found: a legitimate but poorly scheduled job (a backup running during peak hours) suggests rescheduling; an unexpectedly large consumer (a misconfigured log rotation, a runaway process) suggests fixing that process directly; and if the load turns out to be the genuine, expected workload for the box, the conversation shifts toward whether the storage tier itself (volume type, IOPS provisioning) is undersized for that workload rather than assuming a single process is at fault.
_What the interviewer is probing for:_ Going past "the disk is saturated" to attribution and a differentiated remediation path depending on what's actually found.

**🎯 Architect:** _"How would you build a standard 'disk performance' incident runbook that a less experienced on-call engineer could follow?"_
**Model answer:** I'd encode the same three-stage sequence this section walks through as a fixed runbook: first `df -h` (and `du` if space-constrained) to rule out or confirm capacity pressure, since some filesystems degrade in write performance near full capacity independent of raw I/O; second `iostat -x 1` watched over a live window (not a single snapshot) for `%util` and `await` to confirm whether the storage layer itself is actually saturated; third `iotop -oa` to attribute any confirmed saturation to a specific process before escalating further. I'd explicitly call out the deleted-but-open-file gotcha in the runbook, since it's a recurring, easily-diagnosed-wrong situation ("we deleted files but the disk is still full") that otherwise burns time — with `lsof | grep deleted` as the named diagnostic step. The goal is that an on-call engineer without deep storage-internals background can still correctly distinguish "we need more space," "the storage tier is undersized for this workload," and "one specific process needs fixing" without guessing, and knows which of the three to escalate rather than trying to fix all of them at once.
_What the interviewer is probing for:_ Turning a diagnostic sequence into a repeatable, teachable runbook rather than tribal knowledge, and correctly separating the three distinct remediation paths (capacity, storage tier, specific process) a disk-performance incident can resolve to.

## 8. Key Takeaways

- `df -h`'s "100% full after deleting files" gotcha is caused by a process still holding the deleted file open — space isn't reclaimed until every open handle closes; `lsof | grep deleted` is the diagnostic (1).
- `du -sh` and `du -h --max-depth=1` are the practical drill-down workflow for finding what's consuming space within a full filesystem, and can legitimately disagree with `df`'s totals due to open-deleted-files or sparse files (2).
- `iostat -x` measures throughput and latency (`%util`, `await` vs. `svctm`, queue depth), a fundamentally different question from `df`/`du`'s space usage — a disk can be nearly empty and still be the bottleneck (3).
- `iotop` attributes I/O load to specific processes, the disk equivalent of what `top` does for CPU (§81) — necessary once `iostat` confirms saturation but before it's clear who's causing it (4).
- The standard "disk is slow" diagnostic flow is space (`df`/`du`) → throughput/latency (`iostat`) → attribution (`iotop`), mirroring the coarse-to-detailed-to-per-process pattern used for CPU (§81) and memory (§82) (5).

## 9. Related Concepts & What's Next

This section connects to §82's page-cache/dirty-page discussion (Part 11, prior) for when buffered writes actually reach disk, and depends on §19's inode/hard-link model (Part 3) for the deleted-but-open-file mechanism, along with §18's filesystem types and §76's `fsck`/repair coverage (Parts 3 and 10) for related filesystem-health context. It's the third of §80's four resource-specific continuations. §84 (next) closes out the sequence with network performance analysis — `iftop`, `nload`, `sar` — the fourth and final resource in §80's unified model.

**Next Section:** §84 — `Section-84-Part11-Network-Performance-Analysis.md`
