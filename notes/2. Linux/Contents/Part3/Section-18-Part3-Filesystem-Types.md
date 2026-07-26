# Section 18 (Part 3): Filesystem Types (ext4, XFS, Btrfs, ZFS overview, tmpfs, overlayfs)

## 1. Overview: Why Filesystem Type Choice Matters

§17 walked the **Filesystem Hierarchy Standard** — the conventional layout of directories every Linux system agrees on. This section moves one layer down: the FHS describes _where_ things live, but says nothing about _how_ the bytes backing those directories are actually organized on a block device. That's the job of a **filesystem type** — the on-disk data structure and code (usually a kernel module) that turns a raw block device into something `open()`, `read()`, and `write()` can operate on.

Every mounted filesystem on a Linux host — root, `/home`, a database data directory, a container's writable layer — has exactly one filesystem type backing it, chosen at `mkfs` time (or, for network and pseudo-filesystems, defined by the protocol/kernel subsystem itself). That choice is not cosmetic. It determines:

- Maximum file and volume size
- Whether the filesystem journals metadata (and how that affects crash recovery time)
- Whether snapshots, checksumming, and compression are available natively
- How the filesystem behaves under specific workloads — many small files vs. few huge files, random writes vs. sequential, high metadata churn vs. mostly-static data
- Which recovery tools exist if something goes wrong

This section covers the filesystem types a working Linux administrator actually encounters: **ext4** and **XFS** (the two real default choices on mainstream distributions today), **Btrfs** (increasingly common, especially on SUSE and some Fedora spins), **ZFS** (important to understand conceptually, including why it's _not_ a first-class citizen in the Linux kernel), and two special-purpose, non-disk-backed filesystem types that show up constantly in modern infrastructure: **tmpfs** and **overlayfs**.

> 💡 **Tip:** "Which filesystem should I use?" almost never has one universal answer — it depends on the workload. Treat this section as building a mental model for making that call, not memorizing "XFS is best" or "ext4 is best" as a fixed fact.

## 2. ext4: The Long-Standing Default

**ext4** (fourth extended filesystem) is the direct successor to ext2/ext3 and has been the default root filesystem on most Debian/Ubuntu installations for a long time. It's a **journaling filesystem**: metadata changes (and optionally data, depending on journal mode) are written to a journal before being committed to their final location, so an unclean shutdown can replay the journal on next mount instead of requiring a full filesystem scan.

Key characteristics:

- **Extents-based allocation** — ext4 tracks contiguous ranges of blocks ("extents") rather than ext2/ext3's block-by-block mapping, which reduces fragmentation and metadata overhead for large files.
- **Journaling modes** — `data=ordered` (default; data is flushed before its metadata is journaled, a good balance), `data=journal` (both data and metadata journaled — safest, slowest), `data=writeback` (only metadata journaled — fastest, weakest crash guarantees). Set via a mount option or at `mkfs` time.
- **Backward compatibility** — an ext4 filesystem can, in many cases, be mounted as ext2/ext3 (with reduced feature support), and the ext2→ext3→ext4 lineage shares tooling (`e2fsck`, `tune2fs`, `resize2fs`) — §10 (Part 10, §76) covers `fsck`/repair tooling for this family in depth.
- **Practical limits** — maximum individual file size and maximum volume size are both in the exabyte range on modern configurations, which is not a real-world constraint for the overwhelming majority of deployments.
- **Maturity** — decades of production use, extremely well-understood failure modes, broad tooling support. This is its single biggest practical advantage: when something goes wrong, the diagnostic playbook is well trodden.

**Creating an ext4 filesystem:**

```bash
mkfs.ext4 /dev/sdb1
```

```bash
mkfs.ext4 -L data-vol /dev/sdb1
```

The `-L` flag sets a filesystem label, which is useful for referencing the device by label rather than a potentially unstable device path in `/etc/fstab` (§20 covers `/etc/fstab` and mount options in full).

## 3. XFS: The High-Throughput, Large-File Default

**XFS** originated at SGI and has been the default root filesystem on RHEL/CentOS/Rocky/Alma since RHEL 7. It's also a journaling filesystem, but its design center is different from ext4's: XFS was built from the start for **high-throughput, parallel I/O on large files and large volumes** — the kind of workload common on enterprise storage arrays.

Key characteristics:

- **Allocation groups** — an XFS filesystem is internally divided into multiple allocation groups, each capable of being managed somewhat independently, which is what enables strong parallel I/O scaling on multi-CPU, multi-disk systems.
- **Excellent large-file and large-volume performance** — XFS handles very large files and very large filesystems efficiently, which is a large part of why it's a common choice for database storage volumes, media/backup repositories, and large data lakes.
- **Online operations** — XFS filesystems can be **grown while mounted** (`xfs_growfs`) which is operationally convenient for expanding a volume without downtime. Notably, **XFS cannot be shrunk** at all — this is a real, frequently-surprising limitation, unlike ext4 which supports offline shrinking via `resize2fs`.
- **No built-in defragmentation gap** — XFS has historically handled fragmentation well under its native workloads, with `xfs_fsr` available for the rare cases it's needed.

**Creating an XFS filesystem:**

```bash
mkfs.xfs /dev/sdb1
```

```bash
mkfs.xfs -L data-vol -f /dev/sdb1
```

`-f` forces creation, overwriting any existing filesystem signature — required if `mkfs.xfs` detects a prior filesystem and refuses to proceed without confirmation.

> ⚠️ **Warning:** The "XFS cannot shrink" limitation is a real operational trap, not folklore — plan volume sizing (or use LVM, §10/§73, to size logical volumes with headroom) with the assumption that an XFS filesystem, once grown, can never be made smaller again without a full backup/recreate/restore cycle.

## 4. Btrfs: Copy-on-Write With Built-In Volume Management

**Btrfs** ("B-tree filesystem") takes a fundamentally different architectural approach from ext4 and XFS: it's a **copy-on-write (CoW)** filesystem that folds volume-management functionality — the kind of thing LVM (§10/§73) provides as a separate layer for ext4/XFS — directly into the filesystem itself.

Key characteristics:

- **Copy-on-write** — modifying data never overwrites the original blocks in place; a new copy is written and the filesystem's metadata is atomically updated to point at it. This is the foundation for Btrfs's cheap, near-instant **snapshots** — a snapshot is just a pointer to a consistent tree state, not a full data copy, until the underlying blocks actually diverge.
- **Native subvolumes** — Btrfs supports independently-mountable subvolumes within a single filesystem, which distributions like openSUSE use to give `/`, `/home`, and `/var` independent snapshot/rollback behavior without separate partitions.
- **Built-in checksumming** — Btrfs checksums both data and metadata by default, enabling detection (and, with redundancy configured, repair) of silent data corruption that ext4/XFS alone would not notice.
- **Native multi-device support and RAID-like profiles** — Btrfs can span multiple block devices directly and offers its own RAID0/1/10-like profiles, again without a separate LVM/mdadm layer (though RAID5/6 profiles in Btrfs have a well-documented history of stability issues and are generally avoided in production).
- **Transparent compression** — `zstd`/`lzo`/`zlib` compression can be enabled per-filesystem or per-file, transparently to applications.

Btrfs is the default root filesystem on openSUSE and is offered as an option on some Fedora spins, but it is **not** the default on mainstream Ubuntu or RHEL server installs — adoption is real but narrower than ext4/XFS, and its RAID5/6 caveat is worth knowing specifically if it comes up in an interview or a design review.

## 5. ZFS: Powerful, But Not a First-Class Linux Citizen

**ZFS** originated at Sun Microsystems for Solaris and is architecturally similar in spirit to Btrfs — copy-on-write, built-in volume management (ZFS "pools" and "datasets" replace the separate LVM layer), checksumming, snapshots, and native compression — but with a longer production track record and, in most comparisons, more mature RAID-Z (its RAID5/6-equivalent) implementations.

The critical nuance that distinguishes ZFS from every other filesystem in this section:

**ZFS is not shipped in the mainline Linux kernel, and cannot be**, for licensing reasons. ZFS is licensed under the CDDL (Common Development and Distribution License), which the Linux kernel community and the Linux kernel's GPLv2 license are considered legally incompatible with for the purpose of static/dynamic linking into the kernel tree. As a result:

- ZFS on Linux is delivered via **OpenZFS**, distributed as an **out-of-tree kernel module** (commonly via DKMS — Dynamic Kernel Module Support — which rebuilds the module against whatever kernel is currently running) rather than being compiled into the kernel or shipped in-tree.
- This has real operational consequences: a kernel upgrade can require the ZFS module to rebuild (DKMS usually handles this automatically, but it can fail, especially on very new or unusual kernel versions), and some distributions are more cautious than others about how tightly they integrate it.
- Ubuntu is notably more ZFS-friendly than most — it has shipped ZFS support (including as an installer-time root filesystem option) for years — but this is Canonical's own packaging/legal decision, not an upstream kernel change; RHEL-family distributions generally do not ship it by default at all.

⚠️ **Verify current source:** Which specific distributions bundle OpenZFS by default, and under what installer conditions, changes over time and by distro release — confirm against current vendor documentation before treating any specific distro's ZFS support level as a fixed fact.

Despite the licensing friction, ZFS remains a strong, deliberate choice for specific workloads — particularly storage-focused hosts (NAS-style file servers, backup targets, database hosts wanting checksummed, snapshot-friendly storage) where its maturity and RAID-Z reliability outweigh the operational overhead of an out-of-tree module. It is rarely the right choice for a generic application server's root filesystem.

## 6. tmpfs: RAM-Backed, Ephemeral by Design

**tmpfs** is architecturally unlike everything above it in this section — it is not disk-backed at all. A tmpfs filesystem lives in **volatile memory** (RAM, and it can spill into swap under memory pressure), which gives it two defining properties:

- **Extremely fast** — no disk I/O is involved for reads or writes, since the "storage" is memory itself.
- **Contents do not survive a reboot** (or an unmount) — by design, not as a limitation. This is why `/tmp` is commonly mounted as tmpfs on many modern distributions (§17 covered `/tmp`'s FHS role): its contents are explicitly meant to be transient.

Common real-world tmpfs mount points:

- `/tmp` — on distributions that mount it as tmpfs, this both speeds up build/temp-file-heavy workloads and guarantees `/tmp` starts clean on every boot.
- `/dev/shm` — the conventional shared-memory tmpfs mount, used by applications (including some database and messaging systems) for POSIX shared memory segments.
- `/run` — modern distributions mount `/run` as tmpfs for runtime state (PID files, sockets) that inherently shouldn't persist across a reboot.

**Mounting tmpfs manually, with a size cap:**

```bash
mount -t tmpfs -o size=512M tmpfs /mnt/scratch
```

Sizing tmpfs matters operationally: an unbounded or oversized tmpfs mount can be filled by a runaway process and consume real system RAM, potentially triggering OOM-killer activity (§11's Part-11 memory-analysis coverage goes deeper on OOM behavior) rather than simply failing a disk-full write the way a disk-backed filesystem would.

> 💡 **Tip:** Because tmpfs contents vanish on unmount/reboot, never treat it as a place to stage data you can't afford to lose — it's ideal for build caches, ephemeral sockets, and genuinely disposable scratch space, and a real hazard if a script mistakenly assumes any mounted filesystem is persistent.

## 7. overlayfs: Layered, Copy-on-Write Union Mounts

**overlayfs** solves a different problem than any filesystem above: it lets you present **multiple directory trees, stacked in layers, as a single unified mount point**, where writes are transparently redirected to a dedicated writable layer while the underlying layers stay untouched.

The core concepts:

- **Lower layer(s)** — one or more read-only directory trees forming the base. Multiple lower layers can be stacked.
- **Upper layer** — a single writable directory where any new or modified files actually land.
- **Merged view** — the mount point applications actually see, which transparently combines lower + upper into what looks like one normal filesystem.
- **Copy-up on write** — if a process writes to a file that currently exists only in a lower (read-only) layer, overlayfs transparently copies that file up into the upper layer first, then applies the write there — the lower layer is never modified.
- **workdir** — an additional directory overlayfs requires internally for atomic operations during the copy-up process; it must be on the same underlying filesystem as the upper layer.

**Mounting an overlay manually:**

```bash
mount -t overlay overlay \
  -o lowerdir=/mnt/lower,upperdir=/mnt/upper,workdir=/mnt/work \
  /mnt/merged
```

The single most important real-world application of overlayfs is **container image layering** — this is exactly the mechanism Docker's `overlay2` storage driver (and equivalent mechanisms in other container runtimes) uses to implement image layers: each image layer is a read-only lower directory, and a container's writable filesystem is a thin upper layer on top, which is why spinning up many containers from the same base image is cheap in both disk space and startup time — no per-container full filesystem copy is needed. Part 13's containers coverage (§97–§102) goes deeper on how this fits into the broader namespaces/cgroups/OverlayFS foundation that Docker and Kubernetes build on.

## 8. Comparison Table

| Dimension              | ext4                                 | XFS                                        | Btrfs                                              | ZFS (OpenZFS)                                    | tmpfs                            | overlayfs                            |
| ---------------------- | ------------------------------------ | ------------------------------------------ | -------------------------------------------------- | ------------------------------------------------ | -------------------------------- | ------------------------------------ |
| Backing store          | Block device                         | Block device                               | Block device                                       | Block device (pooled)                            | RAM / swap                       | Other filesystem(s), layered         |
| Journaling / integrity | Metadata (+data optional) journal    | Metadata journal                           | Copy-on-write, checksummed                         | Copy-on-write, checksummed                       | N/A (volatile)                   | Inherits from lower/upper filesystem |
| Snapshots              | No (native)                          | No (native)                                | Yes, native, cheap                                 | Yes, native, cheap                               | N/A                              | N/A                                  |
| Volume management      | Separate (LVM)                       | Separate (LVM)                             | Built in (subvolumes, multi-device)                | Built in (pools, datasets)                       | N/A                              | N/A                                  |
| Online grow            | Yes                                  | Yes (`xfs_growfs`)                         | Yes                                                | Yes                                              | N/A (resize via remount)         | N/A                                  |
| Online shrink          | Yes (offline for full support)       | **No, never**                              | Yes                                                | Limited                                          | N/A                              | N/A                                  |
| In mainline kernel     | Yes                                  | Yes                                        | Yes                                                | **No** — CDDL/GPL incompatibility                | Yes                              | Yes                                  |
| Typical default on     | Debian/Ubuntu (historically)         | RHEL/CentOS/Rocky/Alma                     | openSUSE                                           | Rarely default; opt-in (Ubuntu allows)           | `/tmp`, `/dev/shm`, `/run`       | Docker/container storage drivers     |
| Best-fit workload      | General-purpose, mature/stable needs | Large files, high-throughput, parallel I/O | Snapshot-heavy, checksummed data, flexible volumes | Storage-focused hosts wanting max data integrity | Ephemeral scratch, runtime state | Container image/layer storage        |

## 9. Hands-On: Identifying and Creating Filesystems

### 9.1 `df -T`

**Purpose:** List mounted filesystems along with their filesystem type — the fastest way to see what's actually backing every mount point on a running host.

**Syntax:**

```bash
df -T
```

**Example usage and expected output:**

```bash
$ df -T
Filesystem     Type   1K-blocks     Used Available Use% Mounted on
/dev/sda1      ext4    51475068 12345678  36483200  26% /
tmpfs          tmpfs    8123456        0   8123456   0% /dev/shm
/dev/sdb1      xfs    104857600 20971520  83886080  20% /data
overlay        overlay 51475068 12345678  36483200  26% /var/lib/docker/overlay2/abc123/merged
```

**Production usage example:** During an unfamiliar-host audit or an incident where a specific mount is behaving unexpectedly (e.g., unexpected fragmentation, a `resize2fs` vs. `xfs_growfs` decision), `df -T` is the fastest way to confirm exactly which filesystem type is in play before reaching for type-specific tooling — using an ext4 tool against an XFS volume (or vice versa) simply fails, so confirming type first avoids wasted troubleshooting steps.

**Common errors:** Confusing `df -T` (type) with plain `df -h` (human-readable sizes, no type column) — they're complementary, not interchangeable; scripts that need both should combine `-hT`.

### 9.2 `blkid`

**Purpose:** Report filesystem type, UUID, and label for block devices directly from their on-disk superblock signature — the authoritative source `/etc/fstab` entries are typically built from.

**Syntax:**

```bash
blkid [device]
```

**Example usage and expected output:**

```bash
$ blkid /dev/sdb1
/dev/sdb1: LABEL="data-vol" UUID="a1b2c3d4-e5f6-7890-abcd-ef1234567890" TYPE="xfs"
```

**Production usage example:** Before writing an `/etc/fstab` entry (§20) for a newly created filesystem, `blkid` supplies the UUID that should be used to reference the device — referencing by UUID rather than a device path like `/dev/sdb1` avoids boot failures if device enumeration order changes (a common issue after hardware/controller changes on physical or virtualized hosts).

### 9.3 `mkfs.ext4` / `mkfs.xfs` — Creating a Filesystem

**Purpose:** Format a block device (typically a freshly partitioned or freshly created LVM logical volume) with a chosen filesystem type, before it can be mounted and used.

**Syntax:**

```bash
mkfs.ext4 [options] device
mkfs.xfs [options] device
```

**Common errors:**

- Running `mkfs` against the wrong device — this is destructive and irreversible without a backup; always confirm the target with `lsblk` or `blkid` first, especially on hosts with multiple similarly-named block devices.
- Forgetting `-f` with `mkfs.xfs` when a prior filesystem signature exists — `mkfs.xfs` refuses by default as a safety check, which is a deliberate guard rail, not a bug to route around casually.

**Troubleshooting:** If `mkfs.ext4`/`mkfs.xfs` reports the device is busy, check `lsof` and `mount` output for anything still holding it open (including a leftover mount or an LVM logical volume still marked active) before forcing anything.

## 10. Production Relevance: Choosing a Filesystem Type

A few concrete, real-world decision patterns:

- **General-purpose application servers, root filesystem:** ext4 or XFS are both reasonable defaults today; the honest answer is "follow your distribution's default unless you have a specific reason not to" — RHEL-family defaults to XFS, Debian/Ubuntu-family historically defaults to ext4, and fighting the distro default adds operational surprise for marginal benefit in most cases.
- **Database storage volumes:** XFS is a very common production choice given its strength with large files and high-throughput parallel I/O, which matches typical database data-file access patterns closely.
- **Hosts needing frequent, cheap snapshots** (e.g., rollback-friendly desktop-adjacent servers, some CI/build hosts): Btrfs's native snapshot support is a genuine differentiator over ext4/XFS, which need LVM snapshots (§10/§74) layered on top to get comparable functionality.
- **Storage/NAS-focused hosts prioritizing data integrity above all else:** ZFS's checksumming and mature RAID-Z are strong arguments, provided the team accepts the out-of-tree-module operational overhead (10) and picks a distribution (commonly Ubuntu) with solid ZFS packaging support.
- **Anything under `/tmp`, `/dev/shm`, `/run`, or genuinely ephemeral scratch space:** tmpfs, sized deliberately rather than left unbounded.
- **Container runtimes:** overlayfs, essentially by default via Docker's `overlay2` driver — this isn't usually a choice an administrator makes directly per-container, but understanding why it's there (cheap layered images, fast container startup) matters for diagnosing container storage behavior.

> ⚠️ **Warning:** Filesystem type is a decision that's expensive to reverse in production — changing a live root or data filesystem's type requires a full backup, reformat, and restore, not an in-place conversion (with narrow exceptions like ext2→ext3→ext4 upgrades within the same family). Get this right at provisioning time rather than treating it as easily fixable later.

## 11. Common Misconceptions

1. **"XFS can be shrunk, it just needs the right tool."** No — this is a hard architectural limitation of XFS, not a missing feature waiting for the right flag. Shrinking an XFS filesystem requires backup, recreate, and restore.
2. **"ZFS isn't available on Linux."** It's available and widely used, but specifically as an out-of-tree module (OpenZFS via DKMS) rather than an in-kernel filesystem, because of CDDL/GPL license incompatibility — a nuance worth stating precisely rather than as a blanket "not supported."
3. **"Btrfs and ZFS are basically the same thing with different names."** They share a lot architecturally (CoW, snapshots, built-in volume management, checksumming) but are independent implementations with real differences, most notably in RAID5/6-equivalent maturity — Btrfs's is generally considered less production-ready than ZFS's RAID-Z.
4. **"tmpfs is just a regular filesystem that happens to be fast."** It's fundamentally different — it's RAM-backed and its contents are explicitly not meant to survive a reboot or unmount, which is a design property, not a limitation to work around.
5. **"overlayfs is a Docker-specific technology."** overlayfs is a general-purpose Linux kernel filesystem feature; Docker (and other container runtimes) are simply its most visible consumer via the `overlay2` storage driver. It can be mounted manually for other layered-filesystem use cases too.

## 12. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between ext4 and XFS, and how would you check which one a given mount point is using?"_
**Model answer:** Both are journaling filesystems and both are common distro defaults — ext4 on Debian/Ubuntu historically, XFS on RHEL-family distributions. XFS is generally stronger for large files and high-throughput parallel I/O; ext4 has a longer, extremely well-understood production track record. A practical difference that matters operationally is that XFS can be grown online but never shrunk, while ext4 supports both grow and shrink. To check which is in use, I'd run `df -T` for a quick mounted-filesystem overview, or `blkid` against the specific device for its type, UUID, and label directly from the superblock.
_What the interviewer is probing for:_ Basic fluency with the two mainstream default filesystems and knowing the practical (not just trivia-level) difference that actually bites people — the shrink limitation.

**🎯 Intermediate:** _"Why isn't ZFS shipped in the mainline Linux kernel, and what does that mean operationally for a team that wants to use it?"_
**Model answer:** ZFS is CDDL-licensed, and the Linux kernel community considers CDDL legally incompatible with the kernel's GPLv2 license for the purposes of linking into the kernel tree — so it can't be merged upstream the way ext4 or XFS are. On Linux it's delivered as OpenZFS, an out-of-tree kernel module, typically built and rebuilt automatically via DKMS whenever the running kernel changes. Operationally that means kernel upgrades carry a bit more risk with ZFS in the picture — a DKMS rebuild can fail, particularly against very new kernels — and not every distribution packages or supports it the same way; Ubuntu is notably more ZFS-friendly than RHEL-family distributions. Teams choosing ZFS need to accept that maintenance overhead in exchange for its checksumming, snapshot, and RAID-Z strengths.
_What the interviewer is probing for:_ Understanding that this is a licensing issue, not a technical limitation, plus awareness of the real operational consequence (DKMS/kernel-upgrade coupling).

**🎯 Senior:** _"A team wants to run many short-lived containers on a host and is seeing surprisingly high disk usage and slow container start times. Where would you look, filesystem-wise?"_
**Model answer:** I'd first confirm what storage driver the container runtime is actually using — `docker info` or equivalent — since overlayfs (`overlay2`) is the expected default and gives cheap, layered images with fast starts because most of a container's filesystem is shared, read-only lower layers, with only a thin writable upper layer per container. If it's instead running a driver that does full filesystem copies per container (an older or misconfigured driver), that alone would explain both symptoms. I'd also check what's actually landing in the writable layer — an application writing large amounts of data into its own container filesystem rather than to a mounted volume will bloat each container's upper layer individually, since overlayfs's copy-up behavior means any write to a lower-layer file gets duplicated into the upper layer too. And I'd sanity-check that `/var/lib/docker` (or wherever the storage driver keeps layers) is on fast, adequately sized storage — XFS is a common, well-supported choice there specifically because of its throughput characteristics.
_What the interviewer is probing for:_ Whether the candidate connects overlayfs's copy-on-write layering mechanics to a concrete operational symptom, not just knowing the term "overlayfs" exists.

**🎯 Architect:** _"You're designing storage layout for a fleet that includes general app servers, a database tier, and a container platform. How do you decide filesystem types across that fleet, and what do you standardize versus leave flexible?"_
**Model answer:** I wouldn't pick one filesystem type fleet-wide — the workloads are different enough that a single choice would be a compromise everywhere rather than a good fit anywhere. For general app servers, I'd default to whatever the chosen distribution ships as default (ext4 or XFS) unless there's a specific reason to deviate, since fighting the distro default just adds operational surprise for the team maintaining images and automation. For the database tier, I'd lean toward XFS on data volumes given its large-file, high-throughput characteristics, sized via LVM (§10/§73) so volumes can be grown online — and I'd make sure everyone provisioning those volumes internalizes that XFS can never be shrunk, so initial sizing needs headroom baked in rather than "we'll shrink it later" as a fallback plan. For the container platform, the filesystem choice is mostly indirect — I'd make sure the container runtime's storage driver is overlayfs-based (the modern default) and that the underlying filesystem backing `/var/lib/docker`-equivalent storage is fast and appropriately sized, since that's where actual I/O pressure from image layers and writable container layers lands. What I would standardize fleet-wide is the operational discipline around it: consistent use of LVM underneath ext4/XFS volumes so resizing has a safety valve, consistent UUID-based `/etc/fstab` entries rather than device-path-based ones, and a documented decision record for any host that deviates from the distro default (e.g., a storage-focused host running ZFS) so the DKMS/kernel-upgrade coupling that comes with it is a known, tracked risk rather than a surprise during the next kernel patch cycle.
_What the interviewer is probing for:_ Ability to make differentiated, workload-driven storage decisions across a heterogeneous fleet, awareness of XFS's shrink limitation and ZFS's operational overhead as real design inputs, and the instinct to standardize process/tooling even when the filesystem type itself intentionally varies.

## 13. Key Takeaways

- ext4 and XFS are the two real mainstream defaults — ext4 historically on Debian/Ubuntu, XFS on RHEL-family — both mature journaling filesystems; XFS excels at large-file/high-throughput workloads but can never be shrunk once created, only grown.
- Btrfs and ZFS are both copy-on-write filesystems with native snapshots, checksumming, and built-in volume management (no separate LVM layer needed) — but ZFS is CDDL-licensed and therefore shipped only as an out-of-tree module (OpenZFS/DKMS) on Linux, never in the mainline kernel, which carries real kernel-upgrade operational overhead.
- tmpfs is RAM-backed and its contents are deliberately non-persistent across reboot/unmount — common at `/tmp`, `/dev/shm`, and `/run`; size it explicitly to avoid memory-pressure surprises.
- overlayfs stacks read-only lower layers under a single writable upper layer with copy-on-write semantics — this is the mechanism behind Docker's `overlay2` storage driver and modern container image layering generally, not a container-specific technology in itself.
- `df -T` and `blkid` are the fast, ground-truth commands for identifying what filesystem type actually backs a given mount or device before reaching for type-specific tooling.
- Filesystem type is expensive to change after the fact in production — get the choice right at provisioning time, matched to the actual workload, rather than treating it as a low-cost decision to revisit later.

## 14. Related Concepts & What's Next

This section builds directly on §17's FHS coverage — the hierarchy describes where things live; this section describes what actually stores them. §19 (next) goes one level deeper into how files are represented within a filesystem — inodes, hard links, and symbolic links — which applies across ext4, XFS, and Btrfs alike. §20 covers mounting these filesystem types in practice via `/etc/fstab` and mount options, referenced throughout this section for UUID-based device references. Part 10 (§73–§79) returns to storage with full LVM, RAID (`mdadm`), and filesystem repair (`fsck`/`xfs_repair`) depth that this section deliberately left at introductory level. Part 13 (§97–§102) covers namespaces, cgroups, and OverlayFS's role in the container platform stack in full, building on overlayfs's mechanics introduced here in 7.

**Next Section:** §19 — `Section-19-Part3-Inodes-Hard-Links-Symbolic-Links.md`
