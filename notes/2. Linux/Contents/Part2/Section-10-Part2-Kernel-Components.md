# Section 10 (Part 2): Kernel Components (Process Scheduler, Memory Manager, VFS, Network Stack, Device Drivers)

## 1. The Process Scheduler

**Definition:** The process scheduler is the kernel subsystem responsible for deciding which runnable task gets the CPU next, for how long, and on which core — on a multi-tasking system with far more runnable processes than physical CPU cores, this decision happens continuously, thousands of times per second.

**What it does:** Modern Linux uses the **CFS (Completely Fair Scheduler)** as its default scheduling algorithm for normal (non-realtime) tasks. Conceptually, CFS does not use fixed time slices the way older schedulers did. Instead, it tracks each task's **virtual runtime** (a measure of how much CPU time it has already received, weighted by priority) and always picks the runnable task with the least virtual runtime to run next — the intuition is "run whichever task has been fairest-share starved the longest." Tasks are organized in scheduling classes, not just one flat pool:

- **`SCHED_NORMAL` (CFS)** — the default class for ordinary processes; fairness-driven, no hard timing guarantees.
- **`SCHED_FIFO` / `SCHED_RR`** — real-time classes for latency-sensitive workloads; these always preempt `SCHED_NORMAL` tasks and are used sparingly (e.g., audio/industrial control processes), because a misbehaving real-time task can starve everything else.
- **`SCHED_BATCH` / `SCHED_IDLE`** — lower-priority variants for background/batch work that should yield to interactive tasks.

The full mechanics of process states, `nice`/`renice` priority tuning, and scheduling in production troubleshooting are covered in Part 5 (§33–§40, especially §36 for `nice`/`renice`); this section only needs the conceptual model: **CFS picks the "most deserving" runnable task, weighted by priority, on every scheduling decision — it does not use a fixed round-robin time slice.**

**Hands-on:**

```bash
# View the scheduling policy and priority currently applied to a process
$ chrt -p 1234
pid 1234's current scheduling policy: SCHED_OTHER
pid 1234's current scheduling priority: 0

# View detailed scheduler statistics for a specific PID directly from the kernel
$ cat /proc/1234/sched | head -15
systemd (1234, #threads: 1)
-------------------------------------------------------------------
se.exec_start                      :     129384210.123456
se.vruntime                        :         48213.884210
se.sum_exec_runtime                :          9142.331200
...
```

`SCHED_OTHER` is the POSIX name for the `SCHED_NORMAL`/CFS class shown by `chrt`. `se.vruntime` in the `/proc/[pid]/sched` output is the exact virtual-runtime value CFS uses to make its next scheduling decision.

## 2. The Memory Manager

**Definition:** The memory manager is the kernel subsystem that allocates, tracks, and reclaims physical RAM, and presents each process with the illusion of its own private, contiguous **virtual address space** — regardless of how physical memory is actually fragmented or shared underneath.

**What it does:** Every process sees virtual addresses; the memory manager translates those to physical RAM addresses via **page tables**, working together with the CPU's memory management unit (MMU) hardware. Memory is managed in fixed-size chunks called **pages** (commonly 4 KB), not arbitrary byte ranges — this is what makes allocation, protection, and swapping tractable at scale. When physical RAM runs short, the memory manager can move less-active pages out to swap space to free RAM for active work, and under severe pressure the kernel's **OOM (Out-Of-Memory) killer** terminates processes to prevent a total memory deadlock (troubleshooting depth: §82). Virtual memory also provides **isolation** — one process cannot read or corrupt another process's memory, because each process's virtual addresses map only to physical pages the kernel has explicitly assigned to it.

⚠️ **Warning:** This is an intentionally shallow introduction. Full virtual memory mechanics — page tables in depth, paging vs. swapping, memory overcommit, huge pages — are covered in `§16` (Part 2's own closing section). Production memory analysis tooling (`free`, `/proc/meminfo` field-by-field, OOM killer tuning) is covered in `§82` (Part 11).

**Hands-on:**

```bash
$ cat /proc/meminfo | head -6
MemTotal:       16384000 kB
MemFree:         2148392 kB
MemAvailable:    9871204 kB
Buffers:          182044 kB
Cached:          4213880 kB
SwapTotal:        2097148 kB
```

`MemAvailable` (not `MemFree`) is the field that actually reflects usable memory for new workloads — `MemFree` alone is misleading because it excludes reclaimable cache the kernel would happily hand back on demand (§82 covers why this distinction trips up so many first-pass "server is out of memory" diagnoses).

## 3. VFS — The Virtual Filesystem Switch

**Definition:** The VFS (Virtual Filesystem Switch, sometimes called the Virtual File System) is an abstraction layer inside the kernel that presents a single, uniform filesystem interface (`open`, `read`, `write`, `close`, `stat`, …) to userspace, regardless of which actual filesystem implementation is backing a given path.

**What it does:** This is the mechanical answer to _why_ "everything is a file" (`§4`, Principle 1) actually works rather than being just a slogan. When a program calls `open("/var/log/syslog")`, it does not need to know or care whether `/var` lives on ext4, XFS, Btrfs, or a network-mounted NFS share — the VFS sits between the generic system call and the specific filesystem driver, translating the generic request into whatever operations that particular filesystem's driver actually implements. `/proc` and `/sys` (§24) are the most striking proof of this: they are not backed by any disk at all — they are entirely synthetic filesystems that generate their content on the fly from live kernel state, yet they honor the exact same `open`/`read`/`write` contract as a real ext4 file, because the VFS makes "is this data on disk or generated live" invisible to the calling program. This is the same pattern `sendfile()` exploits (6 below) to move data from a file straight into a network socket without a userspace round trip.

**Hands-on:**

```bash
# List every filesystem type the running kernel currently knows how to mount
$ cat /proc/filesystems
nodev	sysfs
nodev	proc
nodev	tmpfs
nodev	cgroup2
nodev	overlay
	ext4
	xfs
	vfat
nodev	nfs4

# See which concrete filesystem type backs each currently mounted path
$ mount | grep -E "^/dev"
/dev/sda1 on / type ext4 (rw,relatime)
/dev/sda2 on /var type xfs (rw,relatime,noatime)
```

Full filesystem-type depth, mounting, `/proc`/`/sys` as introspection interfaces, and inode mechanics live in Part 3 (§17–§24).

## 4. The Network Stack

**Definition:** The network stack is the kernel's implementation of the layered TCP/IP protocol suite — the code path that carries data from a userspace socket call down through transport, network, and link layers, and out onto physical or virtual network hardware (and the reverse path for inbound traffic).

**What it does:** Conceptually, the stack mirrors the standard networking layer model, implemented entirely inside the kernel for performance and centralized control:

```text
Userspace: socket(), connect(), send(), recv()   ◄── socket API — the boundary applications call
        │
        ▼
Transport layer   — TCP (connection-oriented, reliable) / UDP (connectionless)
        │
        ▼
Network layer     — IP (addressing, routing decisions)
        │
        ▼
Link layer        — Ethernet framing, ARP, hands frames to the NIC driver
        │
        ▼
Device driver     — NIC hardware
```

Every network-facing syscall a userspace program makes (`socket()`, `bind()`, `connect()`, `send()`) crosses the same syscall boundary covered in `§11`, then travels down through this layering before touching a physical wire. Full protocol depth, socket programming concepts, firewalls, and diagnostics are Part 7's entire subject (§51–§58).

**Hands-on:**

```bash
$ ss -s
Total: 342
TCP:   58 (estab 21, closed 12, orphaned 0, timewait 12)

Transport Total     IP        IPv6
RAW	  0         0         0
UDP	  9         6         3
TCP	  46        30        16
INET	  55        36        19
```

`ss -s` gives an instant socket-count summary — a fast first check when triaging "is this box under unusual connection load" before reaching for `tcpdump` or per-connection detail (§54).

## 5. Device Drivers

**Definition:** A device driver is the kernel code that translates generic requests from a kernel subsystem (block I/O, character I/O, network I/O) into the specific commands a piece of hardware understands — and translates hardware responses back into a form the rest of the kernel can use.

**What it does:** Drivers are the abstraction boundary between "the kernel wants to read a block from a disk" and "this exact NVMe controller's register-level protocol for reading a block." This is what lets the memory manager, VFS, and network stack stay hardware-agnostic: the VFS calls a generic block-device read; the driver for that specific disk controller is the only code that needs to know the hardware's actual command set. Drivers can be **built-in** (compiled directly into the kernel image, loaded at boot) or **loadable kernel modules** (`.ko` files loaded on demand, `§14` covers `lsmod`/`modprobe`/`insmod` in depth) — the loadable-module model is what lets a single kernel image support wildly different hardware across a fleet without recompiling, and what lets a driver be unloaded/reloaded (e.g., after a firmware update) without rebooting.

**Hands-on:**

```bash
# Which driver is currently bound to each PCI device (e.g., NIC, disk controller)?
$ lspci -k | head -10
00:1f.2 SATA controller: Intel Corporation SATA Controller
	Kernel driver in use: ahci
	Kernel modules: ahci

01:00.0 Ethernet controller: Intel Corporation I350 Gigabit Network Connection
	Kernel driver in use: igb
	Kernel modules: igb

# Same idea for USB devices
$ lsusb -t
```

`Kernel driver in use` is the line that answers "what module is actually handling this hardware right now" — the single fastest way to confirm a driver bound correctly after adding new hardware or updating firmware.

## 6. How the Five Components Relate to Each Other and to the Syscall Boundary

These five subsystems are not five independent silos — userspace requests routinely traverse more than one of them in a single system call, and all of them sit beneath the same syscall boundary (`§11`) that separates kernel space from user space:

```text
┌──────────────────────────────────────────────────────────────────────┐
│                        Userspace Applications                        │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │  system calls (§11)
═════════════════════════════════════════════════════════════════════════
                                 ▼           kernel/userland boundary
┌──────────────────────────────────────────────────────────────────────┐
│                                                                      │
│   ┌───────────────┐   ┌───────────────┐   ┌───────────────┐          │
│   │    Process    │   │    Memory     │   │      VFS      │          │
│   │   Scheduler   │◄─►│    Manager    │◄─►│  (filesystem  │          │
│   │  (§33–§40)    │   │    (§16)      │   │   switch, §17–│          │
│   │               │   │               │   │   §24)        │          │
│   └───────┬───────┘   └───────┬───────┘   └───────┬───────┘          │
│           │                   │                   │                  │
│           │      ┌────────────┴────────────┐      │                  │
│           │      │                         │      │                  │
│           ▼      ▼                         ▼      ▼                  │
│   ┌────────────────────┐            ┌────────────────────┐           │
│   │   Network Stack    │            │   Device Drivers   │           │
│   │     (§51–§58)      │◄──────────►│     (§14)          │           │
│   └────────────────────┘            └────────────────────┘           │
│                                                                      │
└──────────────────────────────────────────────────────────────────────┘
                                 │
                                 ▼
                             Hardware
```

The scheduler decides _which_ process runs when any of these subsystems needs CPU time to do its work; the memory manager backs every subsystem's data structures and buffers; the VFS and network stack both ultimately hand off to device drivers to actually move bytes to/from hardware. A single syscall like `sendfile()` — used to efficiently serve a static file over a network socket — is the clearest proof these are not separate code paths: it asks the VFS to read file data and the network stack to transmit it, entirely inside the kernel, without ever copying the data into userspace in between. Understanding this diagram is the real payoff of this section: it is the map every subsequent Part hangs its detail on.

## 7. Production Relevance: Subsystem-Based Troubleshooting Triage

Naming these five subsystems is not academic — mapping a production symptom to the responsible subsystem is often the fastest way to narrow a troubleshooting search space before reaching for any specific tool (full methodology in §88):

| Symptom                                            | Likely responsible subsystem      | Where the deep-dive lives |
| -------------------------------------------------- | --------------------------------- | ------------------------- |
| High load average, CPU-bound processes stacking up | Process scheduler                 | §33–§40                   |
| Slow disk I/O, high `iowait`                       | VFS / block layer / device driver | §17–§24, §83              |
| Process killed unexpectedly, `dmesg` shows OOM     | Memory manager                    | §16, §82                  |
| Dropped packets, connection timeouts, high latency | Network stack                     | §51–§58                   |
| Hardware not detected, device missing from `/dev`  | Device driver                     | §14                       |

🔑 **Key Takeaway:** "Which subsystem owns this symptom" is a triage question every senior engineer asks in the first sixty seconds of an incident — it determines whether the next command is `chrt`/`top`, `free`/`/proc/meminfo`, `mount`/`iostat`, `ss`/`tcpdump`, or `lspci -k`/`dmesg`.

## 8. Common Misconceptions

1. **"The kernel handles filesystems and networking as totally separate, unrelated code paths."** False — `sendfile()`, `splice()`, and similar zero-copy syscalls deliberately traverse both the VFS and the network stack in one kernel-internal operation specifically to avoid the cost of treating them as separate paths with a userspace hop in between.
2. **"CFS uses fixed time slices like older round-robin schedulers."** False — CFS makes its "who runs next" decision based on tracked virtual runtime fairness, not a fixed quantum; the effective time a task runs before being preempted varies based on system load and the number of competing runnable tasks.
3. **"Device drivers only matter for desktop peripherals like printers and webcams."** False in a server/cloud context — every disk controller, NIC, and virtualized device (`virtio` drivers in cloud VMs) is bound to a driver; a driver mismatch or missing module is a common cause of "cloud instance won't detect its disk/NIC" boot failures.
4. **"Virtual memory means my process actually has the RAM size shown by its virtual address space."** False — virtual address space size is not a promise of physical RAM backing; pages are mapped to physical RAM (or swap, or not mapped at all yet) on demand (§16 covers demand paging in depth).

---

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What is the process scheduler, and what does CFS stand for?"_
**Model answer:** The process scheduler is the kernel component that decides which runnable process gets CPU time next. CFS stands for Completely Fair Scheduler — it's the default scheduling algorithm for normal Linux processes, and instead of fixed time slices it tracks how much CPU time each process has already received (virtual runtime) and always favors the process that has received the least, weighted by priority, so CPU time is shared fairly over time.
_What the interviewer is probing for:_ Basic recall of what the scheduler does and correct terminology — not implementation depth.

**🎯 Intermediate:** _"Explain what the VFS is and why it matters for the 'everything is a file' idea covered earlier in this roadmap."_
**Model answer:** The VFS, or Virtual Filesystem Switch, is an abstraction layer in the kernel that gives userspace one uniform filesystem interface — open, read, write, close — regardless of what's actually backing a given path. It's the reason "everything is a file" isn't just a slogan: `/proc` and `/sys` are synthetic filesystems with no disk behind them at all, generating content live from kernel state, but because the VFS presents them through the same interface as ext4 or XFS, tools like `cat` and `grep` work on them identically to real files. The VFS is what lets ext4, XFS, Btrfs, and NFS all coexist under one filesystem tree without applications needing filesystem-specific code.
_What the interviewer is probing for:_ Whether the candidate can connect an abstract kernel concept to the practical /proc-as-a-file behavior they've likely already used.

**🎯 Senior:** _"A production server is showing high load average but CPU utilization looks normal, and disk iowait is elevated. Walk me through which kernel subsystems you'd suspect and why."_
**Model answer:** Load average on Linux counts processes in uninterruptible sleep (D state) as well as runnable ones, so a high load average with normal CPU utilization and elevated iowait points away from the scheduler being CPU-starved and toward the storage path — processes are blocked waiting on I/O completion, not waiting for CPU. That means I'd focus on the VFS/block layer and the device driver underneath it rather than scheduler tuning: checking `iostat` for per-disk queue depth and service time, confirming the disk driver and underlying hardware/storage backend isn't degraded, and checking whether a specific filesystem or mount is the bottleneck. The scheduler is doing its job correctly here — it's just that the processes it would schedule are blocked further down the stack.
_What the interviewer is probing for:_ Real diagnostic reasoning that connects a specific metric (load average counting D-state processes) to the correct subsystem, not a rehearsed generic answer.

**🎯 Architect:** _"How would you design an onboarding mental model for new SREs so they map symptoms to kernel subsystems quickly during incidents, and what's the risk of getting that mapping wrong?"_
**Model answer:** I'd anchor the model on the five-subsystem breakdown — scheduler, memory manager, VFS, network stack, device drivers — and drill a simple triage table mapping common symptoms (load, OOM kills, iowait, dropped packets, missing hardware) to the responsible subsystem and the first diagnostic tool to reach for, similar to what's used in incident runbooks (§88). The risk of getting the mapping wrong is real: engineers who don't have this model tend to reach for whatever tool they're most comfortable with regardless of the actual bottleneck — e.g., tuning `nice` values on a process that's actually blocked on disk I/O, which wastes response time and can even mask the real problem by changing scheduling behavior around a symptom that was never scheduler-caused. I'd also make sure the model explicitly calls out that subsystems interact — `sendfile()` spanning VFS and network stack is a good teaching example — so engineers don't over-narrow their search to one subsystem when a symptom genuinely spans two.
_What the interviewer is probing for:_ Ability to turn a technical mental model into a scalable team practice, and awareness that oversimplified mental models carry real operational risk if taken too literally.

---

## 10. 🔑 Key Takeaways

- The Linux kernel's internals decompose into five major subsystems: the **process scheduler** (CFS, deciding what runs next), the **memory manager** (virtual memory, page tables, OOM killer), the **VFS** (uniform filesystem interface across ext4/XFS/Btrfs/NFS/`/proc`), the **network stack** (socket API down through TCP/IP to the link layer), and **device drivers** (the hardware-specific translation layer, built-in or loadable modules).
- The VFS is the mechanical explanation for _why_ "everything is a file" (§4) works — it is an abstraction layer, not a slogan.
- These subsystems are not isolated silos — `sendfile()` is the canonical example of a single syscall traversing both the VFS and the network stack inside the kernel.
- All five subsystems sit beneath the syscall boundary (§11) and are invisible to userspace except through that controlled interface.
- Mapping a production symptom to the responsible subsystem (scheduler / memory / VFS / network / drivers) is a core, fast troubleshooting triage skill, formalized later in §88.
- This section is intentionally shallow on each subsystem by design — §14, §16, and Parts 3/5/7 each return to one of these five components at full depth.

## 11. Related Concepts & What's Next

This section builds directly on `§9` (monolithic kernel design) and sets up everything that follows in the rest of the roadmap: `§11` covers the system-call boundary sitting directly above these five subsystems; `§14` returns to device drivers as loadable kernel modules; `§16` closes out Part 2 with full virtual memory depth. Part 3 (§17–§24) is the VFS and filesystem subsystem expanded to full production depth; Part 5 (§33–§40) is the process scheduler and process lifecycle expanded to full depth, including `§36`'s `nice`/`renice` priority tuning; Part 7 (§51–§58) is the network stack expanded to full depth; Part 11 (§80–§88) returns to all five subsystems together as the unified performance-and-troubleshooting model this section's triage table previews.

**Next Section:** §11 — `Section-11-Part2-System-Calls-Kernel-Userland-Boundary.md`
