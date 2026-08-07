# Section 17 (Part 3): Filesystem Hierarchy Standard (FHS): /, /etc, /bin, /usr, /var, /home, /tmp, /proc, /sys, /dev

## 1. What the FHS Is and Why It Exists

The **Filesystem Hierarchy Standard (FHS)** is a specification, maintained by the Linux Foundation, that defines the directory structure and directory contents on Linux (and Unix-like) systems. It answers a question that sounds trivial but has real operational consequences: _if I need to find configuration files, executables, log files, or a user's home directory, where should they be — on any distribution?_

Before a shared standard, every Unix vendor and every Linux distribution could plausibly have invented its own layout. The FHS exists so that they mostly didn't: a system administrator who knows `/etc/nginx/nginx.conf` holds configuration, `/var/log/nginx/access.log` holds logs, and `/usr/bin/nginx` holds the binary can walk onto an unfamiliar Ubuntu, Debian, RHEL, or SUSE box and immediately be productive, without relearning the filesystem layout from scratch. Package managers ([§59](../Part8/Section-59-Part8-Package-Management-Concepts.md)–[§64](../Part8/Section-64-Part8-Managing-Repositories-GPG-Signing-Keys.md)), configuration management tools (Ansible, Puppet — Part 13), monitoring agents, and backup tooling all depend on this predictability to work correctly across a heterogeneous fleet.

The FHS is not perfectly, universally followed — distributions deviate in small ways, and some historical directories exist mostly for backward compatibility (3) — but it is followed closely enough that "where does X live" has a mostly-consistent answer across the entire mainstream Linux ecosystem, which is the whole point.

> 💡 **Tip:** Treat the FHS as a **map of intent**, not just a list of folder names. Each top-level directory encodes a promise about what kind of data lives there — static vs. variable, essential-for-boot vs. optional, machine-local vs. shareable — and that promise is what backup strategies, read-only root filesystems, and container image design (Part 13) are built around.

## 2. The Root Filesystem (`/`) and Top-Level Layout

Everything on a Linux system hangs off a single root directory, `/` — there is no concept of separate drive letters the way Windows has `C:\`, `D:\`. Additional physical or logical devices are **mounted** onto directories within this single tree ([§20](./Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md) covers mounting and `/etc/fstab` in depth), so a `df -h` output showing `/dev/sda1` mounted at `/` and `/dev/sdb1` mounted at `/var` still presents to every application as one continuous, unified filesystem tree.

The standard top-level directories under `/`:

| Directory        | Purpose                                                                                                                                                                                |
| ---------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/bin`           | Essential user command binaries needed in single-user mode and by all users (historically separate from `/usr/bin`; now usually a symlink — see 4)                                     |
| `/sbin`          | Essential system administration binaries (`fsck`, `reboot`, `iptables`) — historically root-only tools needed for boot/repair                                                          |
| `/etc`           | Host-specific system-wide configuration files (2)                                                                                                                                      |
| `/usr`           | The bulk of installed software: binaries, libraries, documentation, shared data (4)                                                                                                    |
| `/var`           | Variable data that changes during normal operation: logs, spool files, caches, databases (5)                                                                                           |
| `/home`          | Per-user home directories (6)                                                                                                                                                          |
| `/root`          | The root user's home directory — deliberately kept outside `/home` so it's accessible even if `/home` is a separate, unmounted filesystem                                              |
| `/tmp`           | World-writable temporary storage, typically cleared on reboot (7)                                                                                                                      |
| `/opt`           | Optional, self-contained third-party software packages (e.g., vendor-supplied applications that don't follow the distro's package layout)                                              |
| `/boot`          | Kernel image, initramfs, and bootloader (GRUB) configuration — everything needed to boot before the root filesystem is fully usable ([§12](../Part2/Section-12-Part2-Boot-Process.md)) |
| `/dev`           | Device files representing hardware and virtual devices (10)                                                                                                                            |
| `/proc`          | Virtual filesystem exposing kernel and process information (8)                                                                                                                         |
| `/sys`           | Virtual filesystem exposing kernel objects and device/driver state (9)                                                                                                                 |
| `/mnt`, `/media` | Conventional mount points — `/mnt` for temporary manual mounts (administrator use), `/media` for removable media auto-mounted by the desktop/system                                    |
| `/srv`           | Data for services hosted by this system (e.g., web server content, FTP data) — less consistently used in practice than the spec intends                                                |
| `/lib`, `/lib64` | Essential shared libraries needed by binaries in `/bin` and `/sbin` (also usually merged into `/usr/lib` today — see 4)                                                                |

> ⚠️ **Warning:** `/tmp` and `/var/tmp` are not interchangeable despite both being writable temp locations. `/tmp` is commonly backed by `tmpfs` (RAM-backed, wiped on reboot) or cleared aggressively by `systemd-tmpfiles`; `/var/tmp` is meant for temporary files that should **survive a reboot** and persist longer. Writing large, long-lived temp files to `/tmp` on a `tmpfs`-backed system can silently consume RAM and cause memory pressure — a surprisingly common production incident (11).

## 3. `/etc` — System-Wide Configuration

`/etc` (originally "et cetera," now commonly backronymed as "editable text configuration") holds **host-specific, static configuration files** — plain text, not executable programs. This is where an administrator or configuration-management tool goes to change how a service behaves.

Key contents relevant to later Parts of this roadmap:

- `/etc/passwd`, `/etc/shadow`, `/etc/group` — user and group account definitions ([§25](../Part4/Section-25-Part4-Users-Groups-Passwd-Shadow-Group.md), covers these files field-by-field)
- `/etc/fstab` — persistent filesystem mount definitions ([§20](./Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md))
- `/etc/sudoers` — privilege escalation policy ([§31](../Part4/Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md))
- `/etc/hosts`, `/etc/resolv.conf`, `/etc/nsswitch.conf` — name resolution configuration ([§53](../Part7/Section-53-Part7-DNS-Resolution-Resolv-Conf-Hosts-Nsswitch.md))
- `/etc/systemd/` — systemd unit files and configuration overrides ([§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)–[§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md))
- Per-application subdirectories like `/etc/nginx/`, `/etc/ssh/`, `/etc/cron.d/` — the near-universal convention of one subdirectory per installed service

Nothing in `/etc` is a compiled binary or a variable runtime artifact — that distinction is precisely what separates it from `/usr` (static program files) and `/var` (data that changes constantly). A useful mental test: if a file answers "how should this service behave," it belongs in `/etc`; if it answers "what did this service produce or record," it belongs in `/var`.

## 4. `/bin`, `/sbin`, and `/usr` — The Historical Split and the Modern Merge

Classic Unix and early Linux drew a hard line between two categories of binaries:

- **`/bin` and `/sbin`** — binaries considered essential enough to be available even if `/usr` wasn't yet mounted (relevant in eras when `/usr` might live on a separate, larger disk or network mount that wasn't available during early boot or single-user recovery).
- **`/usr/bin` and `/usr/sbin`** — the much larger body of "everything else": most installed software, whether from the distro's package manager or built from source.

This split made sense when storage was scarce and `/usr` might genuinely be a separate, sometimes-unavailable mount. It has become largely vestigial on modern systems, because initramfs-based boot ([§12](../Part2/Section-12-Part2-Boot-Process.md)) and larger, cheaper local storage removed most of the original justification. As a result, essentially all mainstream distributions today implement the **usr-merge**: `/bin`, `/sbin`, and `/lib` are symlinks pointing into `/usr/bin`, `/usr/sbin`, and `/usr/lib` respectively, so there is functionally one location for system binaries, not two.

```bash
$ ls -ld /bin /sbin /lib
lrwxrwxrwx 1 root root 7 Mar  1 09:12 /bin -> usr/bin
lrwxrwxrwx 1 root root 8 Mar  1 09:12 /sbin -> usr/sbin
lrwxrwxrwx 1 root root 8 Mar  1 09:12 /lib -> usr/lib
```

> ⚠️ **Warning:** Scripts and documentation that hardcode `/bin/bash` or `/sbin/iptables` still work correctly after the usr-merge — the symlink makes both paths valid — but don't assume `/bin` and `/usr/bin` are two genuinely distinct locations you could independently mount, remove, or diverge on a modern distribution. Treating them as separate is an outdated mental model that no longer matches most real systems.

`/usr` itself further subdivides: `/usr/bin` (user binaries), `/usr/sbin` (admin binaries), `/usr/lib` (libraries), `/usr/share` (architecture-independent data — man pages, icons, documentation), and `/usr/local` (software installed manually/locally, outside the distro's package manager, kept separate specifically so it survives a package-manager-driven system upgrade without being overwritten).

## 5. `/var` — Variable Data

`/var` holds data that a running system **writes and modifies continuously** during normal operation — the direct counterpart to `/etc`'s static configuration and `/usr`'s static program files.

| Subdirectory | Contents                                                                                                                                                       |
| ------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/var/log`   | System and application log files ([§84](../Part11/Section-84-Part11-Network-Performance-Analysis.md), covers log analysis in depth)                            |
| `/var/spool` | Queued data awaiting processing — mail queues, print jobs, cron job definitions                                                                                |
| `/var/cache` | Application-generated cache data that can be regenerated if deleted (e.g., package manager download caches)                                                    |
| `/var/lib`   | Persistent state data applications need between runs — package manager databases (`/var/lib/dpkg`, `/var/lib/rpm`), application data directories               |
| `/var/tmp`   | Temporary files meant to survive a reboot (unlike `/tmp`)                                                                                                      |
| `/var/run`   | Runtime data such as PID files and sockets — on modern systems this is typically a symlink to `/run`, a `tmpfs`-backed directory recreated fresh at every boot |

`/var` is operationally significant for a specific reason: it's the top-level directory most likely to **grow unpredictably and fill the disk** in production — runaway logs, an unrotated log file, a stuck mail queue, or an accumulating cache are among the most common causes of a full disk on a Linux server. This is why many production storage layouts deliberately mount `/var` (or `/var/log` specifically) as its own filesystem or logical volume — so that `/var` filling up doesn't take down the root filesystem and, with it, the whole system's ability to even log in and diagnose the problem.

## 6. `/home` — User Data

`/home` contains one subdirectory per non-root user account, conventionally `/home/<username>`, holding that user's personal files, shell configuration (`.bashrc`, `.profile` — [§41](../Part6/Section-41-Part6-Shells-Overview-Configuration-Files.md)), and application-specific state (`.ssh/`, `.config/`, `.cache/`).

Two operational points worth internalizing:

- **`/root` is deliberately separate from `/home`.** The root user's home directory lives at `/root`, not `/home/root`, specifically so that root can still log in and use a functioning home directory even if `/home` is on a separate filesystem that failed to mount — a real recovery-scenario consideration, not an arbitrary inconsistency.
- **`/home` is a natural candidate for its own mount point or network filesystem** (NFS-mounted home directories were historically common in enterprise/university environments) precisely because it's the one top-level directory whose contents are genuinely user-owned data rather than anything the OS or its packages manage — which makes it easy to back up, migrate, or re-provision independently of the rest of the system.

## 7. `/tmp` — Temporary Storage

`/tmp` is world-writable (mode `1777` — the sticky bit prevents one user from deleting another user's files even though everyone can write into the directory; [§29](../Part4/Section-29-Part4-Umask-Default-Permissions.md), covers the sticky bit in full) and intended for short-lived files that any process or user might need to create.

On most modern distributions, `/tmp` is either:

- Backed by **`tmpfs`**, a RAM-backed virtual filesystem ([§18](./Section-18-Part3-Filesystem-Types.md) covers filesystem types including `tmpfs` in depth) — extremely fast, but its contents vanish on reboot and consume RAM, not disk, while populated, or
- A regular on-disk directory that gets cleared periodically by `systemd-tmpfiles` ([§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md)) rather than only at reboot.

**Production usage example:** A common real-world incident pattern is an application (or a poorly written deployment script) writing large temporary files — build artifacts, uploaded file staging, database dump scratch space — into `/tmp` on a host where `/tmp` is `tmpfs`-backed. Under enough concurrent load this quietly consumes system RAM rather than disk space, and the failure mode looks like memory pressure or OOM-killer activity ([§86](../Part11/Section-86-Part11-Observability-Strace-Ltrace-Perf-APM.md)) rather than an obviously-full disk, which makes it a genuinely confusing incident to diagnose the first time you encounter it.

## 8. `/proc` — The Process and Kernel Virtual Filesystem (Introduction)

`/proc` is a **virtual filesystem** — it has no backing storage on disk at all. Its contents are generated on demand by the kernel, in memory, the moment something reads them. Every running process gets a numbered subdirectory, `/proc/<pid>/`, exposing that process's command line (`/proc/<pid>/cmdline`), open file descriptors (`/proc/<pid>/fd/`), memory maps, and current status directly from kernel data structures.

`/proc` also exposes system-wide kernel information outside any specific process: `/proc/cpuinfo`, `/proc/meminfo`, `/proc/version` (used in [§1](../Part1/Section-01-Part1-What-Linux-Is-Kernel-vs-OS-vs-Distribution.md)'s hands-on section), and `/proc/sys/`, a tunable subtree that overlaps with the `sysctl` interface for adjusting live kernel parameters.

```bash
$ cat /proc/1/comm
systemd
$ ls /proc/1/fd | wc -l
34
```

This section introduces `/proc` only at the "what it is and why it's a virtual filesystem, not a real one" level needed to place it correctly in the FHS layout. [§24](./Section-24-Part3-Proc-Sys-Virtual-Filesystems.md), later in this same Part, is the full deep dive into `/proc` and `/sys` for system introspection, and Part 2's kernel coverage ([§8](../Part2/Section-08-Part2-System-Architecture-Overview.md)–[§16](../Part2/Section-16-Part2-Virtual-Memory-Paging-Swap.md)) is the architectural background on the kernel-space/user-space boundary that `/proc` exposes a controlled window into.

## 9. `/sys` — The Kernel Object Virtual Filesystem (Introduction)

`/sys` is also a virtual, in-memory filesystem, introduced later than `/proc` (alongside the kernel's unified **device model**) to expose a more structured, purpose-built view of kernel objects — devices, drivers, buses, and their attributes — than `/proc` was ever cleanly designed for.

Where `/proc` grew organically and ended up holding a mix of process info, kernel tunables, and miscellaneous system data, `/sys` is deliberately organized: `/sys/class/`, `/sys/devices/`, `/sys/bus/`, and `/sys/block/` present a consistent, hierarchical, machine-parseable representation of the hardware and driver state the kernel currently knows about. Tools like `udev` (device node management) and `lsblk` build directly on `/sys` data.

```bash
$ cat /sys/class/net/eth0/address
02:42:ac:11:00:02
$ cat /sys/block/sda/size
20971520
```

As with `/proc`, this is intentionally a light introduction — full depth, including practical introspection workflows and the relationship between `/sys` and `udev`, is [§24](./Section-24-Part3-Proc-Sys-Virtual-Filesystems.md).

## 10. `/dev` — Device Files

`/dev` holds **device files** — special files that represent hardware devices and certain virtual devices, letting userspace programs interact with hardware through the same open/read/write file-based interface used for regular files, which is a core piece of the "everything is a file" Unix philosophy referenced back in [§4](../Part1/Section-04-Part1-Linux-Philosophy-Design-Principles.md).

Common examples:

| Path                          | Represents                                                                                                           |
| ----------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `/dev/sda`, `/dev/nvme0n1`    | Whole-disk block devices                                                                                             |
| `/dev/sda1`, `/dev/nvme0n1p1` | Individual partitions on those disks                                                                                 |
| `/dev/null`                   | Discards anything written to it; reads return EOF immediately — used constantly in shell scripting to silence output |
| `/dev/zero`                   | Produces an infinite stream of null bytes when read                                                                  |
| `/dev/random`, `/dev/urandom` | Kernel sources of random data                                                                                        |
| `/dev/tty`, `/dev/pts/N`      | Terminal devices (physical and pseudo-terminals for SSH sessions, terminal emulators)                                |

Modern systems populate `/dev` dynamically at boot and as hardware is hot-plugged, via `udevd` reading kernel events and creating/removing device nodes accordingly — `/dev` is not a static, pre-populated directory shipped with the distribution the way `/etc` is.

## 11. Hands-On: Exploring the Hierarchy

### 11.1 `df -h`

**Purpose:** Show which physical/logical filesystems are mounted where, and how full each one is — the fastest way to see how the logical FHS layout maps onto actual separate storage devices on a given host.

```bash
$ df -h
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        50G   12G   38G  24% /
/dev/sdb1       100G   67G   33G  67% /var
tmpfs           7.9G  1.2M  7.9G   1% /tmp
/dev/sda2       512M   98M  414M  20% /boot
```

**Production usage example:** This is frequently the very first command run when an alert fires for "disk full" — it immediately shows which mount point is actually the problem (often `/var` from runaway logs, per 5) rather than assuming the entire root filesystem is affected.

### 11.2 `findmnt`

**Purpose:** Show the mount tree in a structured, hierarchical view including filesystem type and mount options — more informative than `df` when the question is "what kind of filesystem is this and how was it mounted," not just "how full is it."

```bash
$ findmnt /tmp
TARGET SOURCE FSTYPE OPTIONS
/tmp   tmpfs  tmpfs  rw,nosuid,nodev,size=8153420k
```

**Troubleshooting:** If `/tmp` unexpectedly behaves as non-persistent across a reboot when an application assumed otherwise, `findmnt /tmp` immediately reveals whether it's `tmpfs`-backed (7) rather than requiring guesswork.

### 11.3 `stat`

**Purpose:** Show detailed metadata for a file or directory — including which underlying filesystem device it resides on — useful for confirming exactly what kind of storage a given path is actually backed by.

```bash
$ stat -f /var/log
  File: "/var/log"
    ID: 0        Namelen: 255     Type: xfs
Block size: 4096       Fundamental block size: 4096
```

## 12. Debian/Ubuntu vs. RHEL/CentOS Family Differences

The FHS is followed closely by both major families, but a few practical differences are worth knowing for cross-distro fleet work:

| Aspect                           | Debian/Ubuntu                                                                                                                                            | RHEL/CentOS/Rocky/Alma                                                                                                    |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| Network config location          | `/etc/netplan/` (modern) or `/etc/network/interfaces` (legacy)                                                                                           | `/etc/sysconfig/network-scripts/` (legacy) or NetworkManager keyfiles                                                     |
| Service unit overrides           | `/etc/systemd/system/` (same convention — systemd is common ground, [§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)) | `/etc/systemd/system/`                                                                                                    |
| Package manager state            | `/var/lib/dpkg/`                                                                                                                                         | `/var/lib/rpm/`                                                                                                           |
| Default web root (if applicable) | `/var/www/html`                                                                                                                                          | `/var/www/html` (largely converged)                                                                                       |
| SELinux/AppArmor config          | `/etc/apparmor.d/` (AppArmor, Ubuntu default)                                                                                                            | `/etc/selinux/` (SELinux, RHEL default) — [§91](../Part12/Section-91-Part12-SELinux-AppArmor-Mandatory-Access-Control.md) |

The core top-level FHS directories (`/etc`, `/var`, `/usr`, `/home`, `/proc`, `/sys`, `/dev`) are effectively identical across both families — the differences live one or two levels deeper, in per-subsystem convention, not in the top-level hierarchy itself.

## 13. Common Misconceptions

1. **"`/bin` and `/usr/bin` are meaningfully different locations today."** On essentially every modern mainstream distribution, `/bin` is a symlink into `/usr/bin` (4) — the historical split is preserved for path compatibility, not because the two are independently mountable or divergent in practice anymore.
2. **"`/tmp` and `/var/tmp` are interchangeable."** They differ specifically in expected lifetime and storage backing — `/tmp` is commonly `tmpfs`-backed and cleared on reboot or aggressively by `systemd-tmpfiles`; `/var/tmp` is meant to survive reboots (2).
3. **"`/proc` and `/sys` are regular directories that happen to hold system info."** Both are virtual, in-memory filesystems generated on demand by the kernel with no on-disk backing at all — conceptually closer to a live API than to a directory of files (8, 9; full depth in [§24](./Section-24-Part3-Proc-Sys-Virtual-Filesystems.md)).
4. **"FHS compliance means every distribution's layout is identical."** The top-level structure is highly consistent, but per-subsystem conventions (network config paths, MAC framework config) genuinely diverge between Debian and RHEL families (12) — "FHS-compliant" doesn't mean "byte-for-byte identical layout."

## 14. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `/etc` and `/var`?"_
**Model answer:** `/etc` holds static, host-specific configuration files — plain text that defines how a service should behave, changed deliberately by an administrator or configuration management tool. `/var` holds variable data that the system generates and modifies continuously during normal operation — logs, caches, spool queues, package manager state. The practical test is: if it answers "how should this behave," it's `/etc`; if it answers "what did this produce," it's `/var`.
_What the interviewer is probing for:_ Whether the candidate has an organizing principle for the FHS rather than memorized folder names with no underlying logic.

**🎯 Intermediate:** _"Why might a production server have `/var` mounted as its own separate filesystem or logical volume, rather than as part of the root filesystem?"_
**Model answer:** `/var` is the directory most likely to grow unpredictably in production — runaway or unrotated logs, a stuck mail spool, an accumulating cache. If `/var` and `/` share one filesystem and `/var` fills the disk, the entire root filesystem is full too, which can prevent logging in, writing PID files, or even completing a clean shutdown — turning a contained problem into a system-wide outage. Mounting `/var` (or `/var/log` specifically) separately means it can fill up on its own without starving the root filesystem, keeping the system recoverable.
_What the interviewer is probing for:_ Operational reasoning connecting the FHS's logical structure to real storage-layout decisions, not just definitional knowledge.

**🎯 Senior:** _"Explain what the usr-merge is and why it happened."_
**Model answer:** Historically, `/bin` and `/sbin` held binaries considered essential enough to be available even before `/usr` was mounted — relevant when `/usr` might be a separate, larger, or network-mounted filesystem not yet available during early boot or single-user recovery. `/usr/bin` and `/usr/sbin` held the much larger body of regular installed software. Modern initramfs-based boot processes and the near-universal practice of keeping `/usr` on the same local filesystem as root removed the original justification for the split. The usr-merge collapses this by making `/bin`, `/sbin`, and `/lib` symlinks into their `/usr` equivalents, so there's functionally one canonical location for system binaries rather than two historically-justified-but-now-redundant ones. It simplifies packaging and reduces a class of bugs where a binary or library existed in one location but not the symlinked-equivalent path a script expected.
_What the interviewer is probing for:_ Understanding that FHS conventions have historical reasons that can become obsolete, and that the candidate tracks how the ecosystem evolves rather than treating the standard as frozen.

**🎯 Architect:** _"You're designing a base image / partitioning scheme for a fleet of stateless application servers. How do you apply FHS knowledge to decide what gets its own mount point, what's read-only, and what's ephemeral?"_
**Model answer:** I'd separate the tree along the same lines the FHS itself implies: `/`, `/usr`, and `/etc` hold mostly static content defined by the image build, so I'd bias toward making the base OS portion read-only where the distribution supports it, reducing the blast radius of runtime tampering or accidental modification. `/var` gets its own mount (or is backed by a separate volume/overlay) specifically because it's the directory expected to grow and change continuously — logs in particular should probably ship off-host via centralized logging ([§84](../Part11/Section-84-Part11-Network-Performance-Analysis.md)) rather than accumulate indefinitely on ephemeral instances. `/tmp` I'd leave `tmpfs`-backed for speed but size it deliberately, since on a stateless, frequently-recycled fleet I don't need `/tmp` to survive anything, and I'd rather it fail fast on hitting its RAM-backed size limit than silently pressure system memory. `/home` is mostly irrelevant on stateless application servers — no interactive users are expected to accumulate meaningful data there. I'd keep `/proc` and `/sys` as the kernel provides them by default; they're not something you design around, just something automation and monitoring tooling reads from. The overall goal is to align "what changes at runtime" with "what's mounted separately or shipped elsewhere," so a host can be destroyed and replaced without losing anything that matters and without a filling directory taking down the whole instance.
_What the interviewer is probing for:_ Ability to translate FHS structure into concrete infrastructure decisions — read-only root design, log shipping, ephemeral vs. persistent storage boundaries — at a fleet-architecture level, not just single-host administration.

## 15. Key Takeaways

- The FHS standardizes where things live on Linux so administrators, package managers, and automation tooling can rely on consistent locations across distributions.
- `/etc` (static config), `/usr` (static programs/libraries), and `/var` (variable runtime data) are the three top-level directories whose distinct purposes explain most of the rest of the hierarchy's logic.
- The historical `/bin`-vs-`/usr/bin` split is now largely vestigial on modern distributions due to the usr-merge — `/bin`, `/sbin`, and `/lib` are typically symlinks into their `/usr` equivalents.
- `/tmp` and `/var/tmp` differ in expected lifetime and storage backing — conflating them is a real source of production incidents, especially when `/tmp` is `tmpfs`-backed.
- `/proc` and `/sys` are virtual, in-memory filesystems generated on demand by the kernel, not real on-disk directories — this section introduces them conceptually; [§24](./Section-24-Part3-Proc-Sys-Virtual-Filesystems.md) is the full introspection deep dive.
- `/var` is the top-level directory most likely to fill unpredictably in production, which is why it's a common candidate for its own dedicated mount point or volume.
- Debian/Ubuntu and RHEL/CentOS families agree closely on the top-level FHS structure; their real differences live one or two levels deeper, in per-subsystem convention (12).

## 16. Related Concepts & What's Next

This section builds on Part 2's kernel/userland layering ([§8](../Part2/Section-08-Part2-System-Architecture-Overview.md)–[§16](../Part2/Section-16-Part2-Virtual-Memory-Paging-Swap.md)) — `/proc` and `/sys` are direct, filesystem-shaped windows into the kernel-space concepts introduced there — and lightly extends [§3](../Part1/Section-03-Part1-Open-Source-Licensing-GPL-Governance.md)'s brief mention of where Linux runs. `/etc`'s account files (`/etc/passwd`, `/etc/shadow`, `/etc/group`) are covered field-by-field in [§25](../Part4/Section-25-Part4-Users-Groups-Passwd-Shadow-Group.md), and `/etc/systemd/` ties directly into the full systemd architecture in [§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)–[§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md). [§18](./Section-18-Part3-Filesystem-Types.md), immediately next, covers the filesystem **types** (ext4, XFS, Btrfs, tmpfs, overlayfs) that actually back these directories on disk or in memory. [§24](./Section-24-Part3-Proc-Sys-Virtual-Filesystems.md), later in this Part, returns to `/proc` and `/sys` for full introspection depth — treat this section's coverage of both as intentionally introductory.

**Next Section:** [§18](./Section-18-Part3-Filesystem-Types.md) — `Section-18-Part3-Filesystem-Types.md`
