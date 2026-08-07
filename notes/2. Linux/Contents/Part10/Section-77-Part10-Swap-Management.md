# Section 77 (Part 10): Swap Management (swapon, swapoff, Swap Files vs. Partitions)

## 1. Overview: From Swap Theory to Swap Operations

[§16](../Part2/Section-16-Part2-Virtual-Memory-Paging-Swap.md) covered virtual memory, paging, and swap at the conceptual level — the kernel's memory manager can move infrequently-used pages out of physical RAM onto disk to free RAM for more active use, and page back in whatever gets touched again. This section is the hands-on operational continuation: how to actually create, activate, size, and tune swap on a running system, using the same conceptual foundation without re-deriving it.

Swap sits in an odd place in modern infrastructure conversations — some administrators treat it as an obsolete relic from an era of scarce RAM, others treat old sizing rules as gospel without questioning whether they still apply. Both instincts are partly wrong. Swap remains operationally relevant on modern high-RAM systems, just for different reasons than it was in the 1990s, and this section tries to be honest about which old advice still holds and which doesn't.

## 2. Swap Partitions vs. Swap Files

Linux supports two mechanisms for providing swap space, and they behave identically once active — the difference is entirely in how the space is provisioned.

**Swap partition:** A dedicated disk partition (`/dev/sdb2`, for example) formatted specifically as swap space via `mkswap`, with no filesystem living on it at all — it's raw block space reserved solely for the kernel's paging use.

**Swap file:** An ordinary file living inside a regular filesystem (commonly `/swapfile` at the root), formatted as swap space the same way, but stored as file data rather than occupying its own partition.

**The historical-advice point worth stating explicitly:** for a long time, swap partitions were considered meaningfully faster than swap files, because a swap file added filesystem-layer overhead (block mapping, fragmentation risk) on top of the raw I/O a swap partition avoided entirely. That was legitimate advice on spinning disks with older filesystems. On modern systems — SSD/NVMe storage and modern filesystems (ext4, XFS) that support extent-based, largely-contiguous file allocation — that performance gap has shrunk to the point of being negligible for the overwhelming majority of workloads. Repeating the "always use a partition, never a file" rule today without qualification is exactly the kind of stale advice this knowledge base tries to flag rather than pass along uncritically.

**Why swap files are usually the better default now:** they can be created, resized, and removed without repartitioning a disk — a genuinely significant operational advantage on cloud VMs and any host where repartitioning means downtime or an image rebuild. A swap partition still has a legitimate niche (some hibernation configurations and certain highly latency-sensitive workloads still prefer it), but "swap file by default, swap partition only for a specific documented reason" is the more defensible modern position, not the reverse.

> 💡 **Tip:** If asked in an interview "should you use a swap partition or a swap file," resist giving the old unconditional answer. The strong answer is: they perform close enough to identically on modern SSD-backed systems that flexibility (files) usually wins by default, and partitions are a deliberate choice for specific cases (like hibernation) rather than a categorical best practice.

## 3. Creating a Swap File

**Purpose:** Provision additional swap space without repartitioning, using files as the container.

**Step-by-step syntax:**

```bash
# 1. Allocate the file (fallocate is fast; dd is the portable fallback)
fallocate -l 4G /swapfile
# Fallback if fallocate isn't supported on the target filesystem:
dd if=/dev/zero of=/swapfile bs=1M count=4096 status=progress

# 2. Restrict permissions — swap files should not be world-readable
chmod 600 /swapfile

# 3. Format the file as swap space
mkswap /swapfile

# 4. Activate it
swapon /swapfile
```

**Key flags:**

| Command/Flag          | Meaning                                                                                                                                                                    |
| --------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fallocate -l 4G`     | Allocate a 4 GB file quickly without writing every byte (metadata-only allocation on supporting filesystems)                                                               |
| `dd bs=1M count=4096` | Portable byte-by-byte allocation (4096 MB = 4 GB) — slower, but works everywhere `fallocate` might not                                                                     |
| `chmod 600`           | Owner read/write only — a world-readable swap file is a real information-disclosure risk, since swapped-out pages can contain sensitive process memory (credentials, keys) |
| `mkswap`              | Writes the swap signature/metadata the kernel needs to recognize the file as swap space, analogous to formatting a partition with a filesystem                             |
| `swapon`              | Activates the swap space immediately for the current boot                                                                                                                  |

**Common errors:**

- Skipping `chmod 600` — a widely-readable swap file is a genuine local-privilege-escalation-adjacent risk, since any process memory that gets paged out (potentially including secrets) lands in a file other local users could read.
- Running `mkswap` on a file that already has `swapon` applied to a previous version at the same path without first `swapoff`-ing it — reformatting active swap space out from under the kernel is asking for trouble.

**Troubleshooting:** `fallocate` failing with "operation not supported" typically means the underlying filesystem doesn't support fast extent-based allocation for that call (some older or unusual filesystems) — fall back to `dd`, which is slower but universally supported.

## 4. Viewing Active Swap

**Purpose:** Confirm what swap space is currently active, its size, and how much of it is in use.

**Syntax:**

```bash
swapon -s
# or, the underlying source swapon -s reads from:
cat /proc/swaps
```

**Example usage and expected output:**

```bash
$ swapon -s
Filename                                Type            Size            Used            Priority
/swapfile                               file            4194300         102400          -2
```

**Key columns:**

| Column          | Meaning                                                                                                                                                              |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Type`          | `file` or `partition` — confirms which mechanism (2) is providing this swap space                                                                                    |
| `Size` / `Used` | In KB — how much swap exists and how much is currently occupied by paged-out data                                                                                    |
| `Priority`      | Higher-priority swap areas are preferred by the kernel when multiple swap areas exist; `-1`/`-2` are default auto-assigned values when priority isn't explicitly set |

**Production usage example:** During a memory-pressure incident, checking `Used` here alongside `free -h` ([§82](../Part11/Section-82-Part11-Memory-Analysis.md) covers memory analysis tools in depth) quickly answers "is this host actually swapping meaningfully, or is swap essentially idle" — a host with gigabytes of swap `Used` under sustained load is a very different diagnosis than one with a few MB used, which is often just normal kernel housekeeping rather than a sign of memory pressure.

## 5. Persisting Swap via `/etc/fstab`

Everything in 3 only activates swap for the current boot — `swapon` doesn't survive a reboot on its own. Persisting it follows the same `/etc/fstab` mechanism [§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md) covered for regular mounts.

**Example `/etc/fstab` entry:**

```
/swapfile   none   swap   sw   0   0
```

| Field       | Meaning                                                                        |
| ----------- | ------------------------------------------------------------------------------ |
| `/swapfile` | The swap file (or partition device, e.g. `/dev/sdb2`)                          |
| `none`      | Swap has no mount point — it isn't mounted into the filesystem tree            |
| `swap`      | Filesystem type field, set literally to `swap`                                 |
| `sw`        | Mount option indicating swap usage                                             |
| `0 0`       | Dump and fsck-order fields, both irrelevant for swap and conventionally zeroed |

> ⚠️ **Warning:** Add the `/etc/fstab` line only _after_ confirming `mkswap` and a manual `swapon` succeeded. An `/etc/fstab` entry pointing at a swap file that doesn't exist or was never properly formatted can, on some systems, delay or interfere with boot the same way a bad regular-mount entry can ([§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md)) — verify first, persist second.

## 6. `swappiness`: What It Actually Controls

**`vm.swappiness`** is one of the most commonly misunderstood tunables in Linux. It is **not** a simple "how aggressively does the system swap" on/off dial in the way its name suggests to many administrators on first encounter.

**What it actually controls:** the kernel's relative preference between two different reclaim strategies when it needs to free up memory — swapping out anonymous memory pages (process heap/stack data that has nowhere else to go but swap) versus reclaiming the page cache (file-backed pages that can simply be dropped and re-read from disk later, since the original data still exists on disk). A **lower** `swappiness` value biases the kernel toward reclaiming page cache first and swapping out process memory only as a last resort; a **higher** value makes the kernel more willing to swap out process memory sooner, even while page cache is still available to reclaim.

**Viewing and setting it:**

```bash
# View the current value (0-100 scale)
cat /proc/sys/vm/swappiness

# Set it for the current boot only (not persistent)
sysctl vm.swappiness=10

# Persist across reboots
echo "vm.swappiness = 10" >> /etc/sysctl.conf
sysctl -p
```

**Practical implication:** the historical default of `60` was tuned with general-purpose desktop/server workloads in mind. Database servers and other workloads sensitive to latency spikes commonly lower this (often to `1`–`10`) so the kernel strongly prefers dropping reclaimable page cache over swapping out active process memory, since a page fault against swap is dramatically slower than a page fault that just re-reads a file from the page cache (or from disk if evicted). Setting `swappiness=0` does **not** disable swap entirely on modern kernels — it's still a strong preference, not an absolute switch, though its exact edge-case behavior has shifted across kernel versions and is worth verifying against current kernel documentation for a specific version if it's load-bearing for a tuning decision.

## 7. Swap Sizing: Why "2x RAM" No Longer Has One Universal Answer

The historically quoted rule — "swap should be roughly twice your RAM" — dates from an era when RAM was scarce and expensive (often single-digit gigabytes on a server), and it made rough sense in that context. It does not sensibly generalize to a server with 256 GB of RAM, where "2x RAM" would mean provisioning half a terabyte of swap space for a scenario that will essentially never occur in practice.

**What actually drives swap sizing today:**

- **Hibernation support.** If a system needs to hibernate (suspend-to-disk), the swap space must be at least as large as the amount of RAM being written out — this is a hard, mechanical requirement, not a rule of thumb. Most production servers never hibernate, which removes this driver entirely for that population.
- **Workload memory-pressure patterns.** A host that occasionally has short-lived memory spikes benefits from a modest swap buffer (a few GB) as a safety margin against the OOM killer ([§83](../Part11/Section-83-Part11-Disk-IO-Analysis.md) covers the OOM killer in Part 11) firing on a transient spike rather than a sustained real shortage. A host that is chronically memory-constrained needs more RAM, not more swap — swap is a shock absorber for occasional spikes, not a substitute for adequate memory sizing.
- **Latency tolerance.** Workloads where any swapping at all is unacceptable (very latency-sensitive services) sometimes run with minimal or even no swap deliberately, accepting that the OOM killer is the fallback for genuine memory exhaustion rather than a slow-but-surviving swapped state.

**Honest guidance:** there is no single correct swap size for the modern era the way "2x RAM" once claimed to be. A reasonable default for a general-purpose server without hibernation needs is a modest fixed amount (commonly in the low single-digit GB range) sized as a pressure buffer rather than scaled proportionally to RAM, with the real sizing decision driven by the workload's actual memory-pressure behavior observed in practice — not a formula applied uniformly across a fleet with very different workloads.

## 8. Common Misconceptions

1. **"Swap files are always slower than swap partitions."** True historically on spinning disks with older filesystems; largely negligible on modern SSD/NVMe storage with extent-based filesystems (2) — the flexibility advantage of files usually outweighs a performance gap that's shrunk close to zero for most workloads.
2. **"`swappiness` is a swap on/off dial."** It governs the kernel's relative preference between swapping out anonymous memory versus reclaiming page cache when memory is needed — not whether swapping happens at all (6).
3. **"More swap always helps under memory pressure."** Swap is a shock absorber for occasional spikes, not a fix for a chronically undersized RAM allocation — a host that needs to swap heavily and continuously to function needs more RAM, and adding more swap just delays the OOM killer rather than solving the underlying capacity problem.
4. **"The 2x-RAM rule still applies."** It was reasonable when RAM was scarce; on modern high-RAM hosts, the real drivers are hibernation support (a hard requirement, if applicable) and observed workload memory-pressure patterns, not a fixed multiple of installed RAM (7).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between a swap file and a swap partition?"_
**Model answer:** Both provide the same swap functionality to the kernel once activated — the difference is provisioning. A swap partition is a dedicated raw block device formatted specifically as swap; a swap file is an ordinary file inside a regular filesystem, formatted the same way with `mkswap`. Historically, partitions were considered faster due to filesystem overhead a file incurs, but on modern SSD-backed systems with extent-based filesystems that gap is negligible for most workloads, and files have won out for most use cases due to their flexibility — they can be resized or removed without repartitioning a disk.
_What the interviewer is probing for:_ Whether the candidate knows the mechanism difference and is aware the "partition is always better" advice is outdated rather than repeating it uncritically.

**🎯 Intermediate:** _"What does `vm.swappiness` actually control?"_
**Model answer:** It's not a simple swap on/off aggressiveness dial — it controls the kernel's relative preference between two reclaim strategies when memory is needed: swapping out anonymous process memory versus reclaiming file-backed page cache. A lower value biases toward dropping reclaimable page cache first, since that's cheap to reclaim (the data still exists on disk) and swapping is comparatively expensive; a higher value makes the kernel more willing to swap out process memory even while cache is still available. Database servers commonly lower it well below the historical default of 60 because they're especially sensitive to the latency cost of swapping active memory.
_What the interviewer is probing for:_ Correcting the common misconception that swappiness is a blunt on/off toggle, and connecting the tunable to a concrete workload-tuning decision.

**🎯 Senior:** _"A host is showing swap usage climbing steadily under normal load. How do you approach it?"_
**Model answer:** First I'd distinguish transient from sustained — `swapon -s`/`/proc/swaps` and `free -h` ([§82](../Part11/Section-82-Part11-Memory-Analysis.md)) sampled over time tell me whether `Used` is a small, stable amount (often just normal kernel housekeeping moving genuinely cold pages out, harmless) versus a steadily growing trend under otherwise normal load, which suggests real memory pressure. I'd check what's actually consuming memory (`/proc/meminfo`, per-process RSS) rather than assuming the fix is "add more swap" — swap is a shock absorber for occasional spikes, not a substitute for adequate RAM, so a steadily climbing trend under normal (not spiking) load points toward either a memory leak in a specific process or a genuinely undersized host for its workload. I'd also check `vm.swappiness` — an unusually high value on a latency-sensitive workload can cause more swapping than the actual memory pressure would otherwise justify, which is a tuning fix rather than a capacity fix.
_What the interviewer is probing for:_ Diagnostic discipline — distinguishing normal background swap activity from a real problem, and not reflexively treating "add more swap" as the answer to underlying memory pressure.

**🎯 Architect:** _"How would you set a swap-sizing standard across a fleet with very different workloads — some memory-light web frontends, some memory-heavy databases?"_
**Model answer:** I wouldn't apply one formula fleet-wide, because the historical "2x RAM" rule breaks down completely on modern high-RAM hosts and doesn't account for workload differences anyway. I'd start by asking whether hibernation is needed anywhere in the fleet at all — if not, that removes the one hard sizing requirement entirely. For the rest, I'd size swap as a modest, fixed pressure buffer per host class rather than scaling with RAM — web frontends with predictable memory profiles might need very little, while workloads prone to occasional spiky memory use (batch jobs, certain caching layers) get a slightly larger buffer sized from observed memory-pressure telemetry, not a guess. For latency-sensitive database hosts specifically, I'd pair a modest swap allocation with a deliberately low `vm.swappiness` so the kernel strongly favors page-cache reclaim over swapping active memory, and I'd bake both the swap-file provisioning and the sysctl tuning into the golden image (Part 13) so it's consistent and version-controlled rather than a manual per-host setting that drifts over time.
_What the interviewer is probing for:_ Fleet-scale thinking — workload-differentiated sizing rather than a blanket rule, correctly identifying hibernation as the one hard requirement, and tying the decision into standardized, version-controlled provisioning rather than ad hoc tuning.

## 10. Key Takeaways

- This section is the hands-on operational continuation of [§16](../Part2/Section-16-Part2-Virtual-Memory-Paging-Swap.md)'s virtual-memory/paging/swap theory (Part 2) — the mechanisms here (`swapon`, `mkswap`, `/etc/fstab`) are how that theory gets applied to a running system.
- Swap partitions vs. swap files perform nearly identically on modern SSD-backed systems — the old "partitions are always faster" advice is outdated; files are the more flexible modern default (2).
- Creating a swap file is `fallocate`/`dd` → `chmod 600` → `mkswap` → `swapon`, and must be added to `/etc/fstab` separately to persist across reboots (3, 5).
- `swapon -s` / `/proc/swaps` show active swap areas, size, and usage — a fast diagnostic during memory-pressure incidents (4).
- `vm.swappiness` controls the kernel's preference between swapping out process memory and reclaiming page cache — it is not a swap on/off toggle, and lowering it is a common latency-sensitive-workload tuning move (6).
- Swap sizing has no single universal modern answer — hibernation support is the one hard requirement when applicable, and otherwise sizing should follow observed workload memory-pressure patterns rather than a fixed multiple of RAM (7).

## 11. Related Concepts & What's Next

This section builds directly on [§16](../Part2/Section-16-Part2-Virtual-Memory-Paging-Swap.md)'s virtual memory and paging fundamentals (Part 2) and connects forward to [§82](../Part11/Section-82-Part11-Memory-Analysis.md) (memory analysis, Part 11) and [§83](../Part11/Section-83-Part11-Disk-IO-Analysis.md) (the OOM killer, Part 11), both of which depend on correctly interpreting swap activity during troubleshooting. It follows [§75](./Section-75-Part10-RAID-Concepts-Mdadm.md)'s RAID coverage earlier in this Part — RAID protects against disk failure while swap management is an unrelated storage-configuration concern, and the two shouldn't be conflated. [§78](./Section-78-Part10-Network-Storage-NFS-Samba.md) (next) moves to network storage — NFS and Samba — a different corner of storage administration entirely.

**Next Section:** [§78](./Section-78-Part10-Network-Storage-NFS-Samba.md) — `Section-78-Part10-Network-Storage-NFS-Samba.md`
