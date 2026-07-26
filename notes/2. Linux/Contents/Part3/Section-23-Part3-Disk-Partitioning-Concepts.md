# Section 23 (Part 3): Disk Partitioning Concepts (MBR vs. GPT)

## 1. What a Partition Table Is and Why It Exists

A raw block device — `/dev/sda`, `/dev/nvme0n1` — is, from the kernel's point of view, just a linear sequence of addressable blocks with no inherent structure. Before any filesystem (§18) can be created on it, something has to answer a prior question: _which byte ranges of this device belong to which logical section?_ That answer is the **partition table** — a small, fixed-location structure near the start of the disk that divides the device into one or more **partitions**, each of which then becomes the target of a separate filesystem, swap area, or other consumer.

Partitioning exists for reasons that are still relevant on modern cloud and bare-metal hosts alike:

- **Isolation of failure and growth.** A filesystem that fills up or corrupts stays contained to its own partition rather than taking down the whole disk — a full `/var/log` partition doesn't prevent `/` from having free space to operate.
- **Different filesystems for different purposes.** `/boot` frequently needs a filesystem type or size constraint the rest of the system doesn't (§7, Part 2's boot process depends on `/boot` being reachable by the bootloader before more advanced filesystem features are available); swap needs no filesystem at all.
- **Multi-boot and layout control.** Multiple operating systems, or deliberate separation of OS from data, both require carving one physical disk into independently addressable regions.
- **A foundation for more advanced storage.** LVM (§73–§79, Part 10) doesn't replace partitioning conceptually — a partition (or the whole disk) still becomes a **physical volume**; LVM adds a flexible layer on top of, not instead of, the partition/disk-as-container concept this section covers.

Every partition table format has to solve the same core problem — record where each partition starts, how big it is, and what type it is — but **MBR** and **GPT** solve it in structurally different ways, with very different limitations.

> 💡 **Tip:** Keep the layering straight: partition table → partition → filesystem → mount point. §23 (this section) is entirely about the first arrow. §18 covers what goes _inside_ a partition (the filesystem), and §20 covers how a partition, once it holds a filesystem, gets attached into the directory tree. A partition with no filesystem on it is a perfectly valid, empty container — `mkfs` (§75, Part 10) is what turns it into something mountable.

## 2. MBR: Master Boot Record

**MBR** (Master Boot Record) is the original PC partitioning scheme, dating to the early 1980s, and it is still encountered today on older systems, some embedded/legacy appliances, and disks under roughly the 2 TiB size boundary where its limitations don't yet bite.

**Structure:** MBR lives entirely in the disk's **first 512 bytes** (sector 0):

- The first 446 bytes hold **boot code** — historically executed by BIOS firmware to hand off control toward an operating system (§7 ties this directly to the BIOS side of the boot process).
- The next 64 bytes are the **partition table** itself — a fixed-size array with room for exactly **four 16-byte partition entries**.
- The final 2 bytes are a fixed **boot signature** (`0x55AA`) that marks the sector as a valid MBR.

**MBR's real, structural limitations — not just historical quirks:**

- **Only four primary partitions.** The 64-byte table has room for exactly four entries, full stop. Needing a fifth partition requires converting one primary partition into an **extended partition**, which itself acts as a container for any number of **logical partitions** chained together via pointers — a workaround bolted onto the format after the fact, not a native capability.
- **2 TiB size ceiling per partition.** Partition size and starting sector in the classic MBR entry are stored in 32-bit fields addressed in 512-byte sectors, which caps addressable size at 2^32 × 512 bytes ≈ 2 TiB. A disk (or partition) larger than that cannot be fully represented in a pure MBR scheme.
- **No redundancy.** The entire partition table lives in one 512-byte sector. Corruption of that one sector — a bad write, a stray `dd`, a firmware bug — can render every partition on the disk unreadable by table lookup, even though the actual partition data is untouched. There is no backup copy anywhere on the disk.
- **No checksum.** MBR has no built-in integrity check comparable to GPT's CRC32 header checksum (3) — silent corruption of the table isn't even self-detected, let alone recoverable.

> ⚠️ **Warning:** The 2 TiB ceiling is a genuinely live operational trap, not just trivia — attaching a large modern cloud data-disk (say 4 TiB) and partitioning it with a tool defaulting to MBR silently truncates usable space to ~2 TiB with no obvious error at partition-creation time; the missing capacity often isn't noticed until someone is confused why `df` doesn't show the disk's full advertised size.

## 3. GPT: GUID Partition Table

**GPT** (GUID Partition Table) is the modern replacement, defined as part of the UEFI specification (§7's UEFI side of the boot-process comparison), and it is the default on essentially all current Linux installations, cloud provider disk images, and modern hardware.

**Structure and advantages, each addressing a specific MBR weakness:**

- **128 partitions by default**, with no extended/logical-partition workaround needed — the partition entry array is simply large enough (and the format allows even more if a tool chooses to allocate a bigger array).
- **64-bit sector addressing** removes the 2 TiB ceiling entirely — GPT supports disks into the exabyte range, far beyond any storage hardware in practical use.
- **Redundancy via a backup header.** GPT stores a **primary header and partition table near the start of the disk** and an identical **backup copy at the very end of the disk**. If the primary is damaged, GPT-aware tools can detect the mismatch and reconstruct from the backup — a direct structural answer to MBR's single-point-of-failure table.
- **CRC32 checksums** on both the header and the partition entries let tools detect corruption rather than silently trusting a damaged table.
- **GUID-based partition identification.** Every disk and every partition gets a globally unique identifier (GUID) rather than relying purely on device-path ordering (`/dev/sda1`, `/dev/sda2`) — this is what makes `/etc/fstab` entries like `UUID=...` (§20) robust to device-name renumbering after a disk is added, removed, or reordered.
- **Protective MBR.** A GPT disk still has a single MBR-formatted sector at the very start, deliberately marked as one giant partition spanning the whole disk. This isn't legacy baggage — it exists specifically so that older, MBR-only tools don't misread an unrecognized GPT disk as blank and offer to overwrite it.

## 4. BIOS vs. UEFI: Why the Boot Firmware Matters Here

MBR and GPT aren't purely a storage-capacity story — they're entangled with the boot-firmware distinction §7 (Part 2) introduced:

- **Legacy BIOS** firmware boots by reading the MBR's boot code directly from disk sector 0 and executing it — BIOS-based booting has a structural expectation of an MBR-shaped first sector (or a GPT disk's protective MBR pointing at a small **BIOS boot partition** holding the actual bootloader stage, when GPT is used with legacy BIOS via GRUB's `bios_grub` partition type).
- **UEFI** firmware understands GPT natively and boots via a dedicated **EFI System Partition (ESP)** — a FAT32-formatted partition holding bootloader binaries UEFI reads directly, rather than executing raw boot-sector code.

The practical consequence: a disk's partition table choice and a system's firmware mode need to agree. Installing onto a GPT disk expecting UEFI boot, on hardware only offering legacy BIOS, fails at boot time even though partitioning itself succeeded — this is a common real-world installation and cloud-image gotcha, not a theoretical edge case.

## 5. Partitioning Tools

### 5.1 `fdisk`

**Purpose:** The traditional, interactive, menu-driven partitioning tool. Historically MBR-only, but modern `fdisk` (util-linux, most current distros) fully supports GPT as well — the "MBR-focused" reputation is a legacy of its origins, not a current limitation.

**Syntax:**

```bash
fdisk [DEVICE]
```

**Example usage:**

```bash
$ sudo fdisk /dev/sdb
Welcome to fdisk (util-linux 2.38).
Command (m for help): p
Disk /dev/sdb: 20 GiB, 21474836480 bytes, 41943040 sectors
Disklabel type: gpt

Command (m for help): n
Command (m for help): w
```

**Key interactive commands:**

| Command | Meaning                                                           |
| ------- | ----------------------------------------------------------------- |
| `p`     | Print the current partition table                                 |
| `n`     | Create a new partition                                            |
| `d`     | Delete a partition                                                |
| `t`     | Change a partition's type                                         |
| `g`     | Create a new empty GPT partition table                            |
| `o`     | Create a new empty MBR (DOS) partition table                      |
| `w`     | Write changes to disk and exit — nothing is committed before this |
| `q`     | Quit without saving                                               |

> ⚠️ **Warning:** `fdisk` (and `gdisk`/`parted`) hold every change in memory until `w` is executed. This is a safety feature — freely explore with `p`, `n`, `d` and back out with `q` if unsure — but it also means a rushed `w` after building up several unreviewed changes is a common source of real, non-undoable mistakes. Always `p` to review the full pending table immediately before writing.

### 5.2 `gdisk`

**Purpose:** A GPT-specific counterpart to `fdisk`, with the same interactive command style (`n`, `d`, `p`, `w`) but built from the ground up around GPT's structures (GUIDs, backup header verification and repair). Useful when a task specifically wants GPT-only tooling, or when diagnosing GPT header corruption — `gdisk` can detect and repair primary/backup header mismatches in ways plain `fdisk` doesn't surface as clearly.

### 5.3 `parted`

**Purpose:** A scriptable partitioning tool supporting both MBR and GPT, usable both interactively and via non-interactive one-line commands — the natural choice for automation (Ansible, provisioning scripts, golden-image pipelines, §13 Part 13) where an interactive `fdisk` session isn't practical.

**Syntax:**

```bash
parted [DEVICE] [COMMAND...]
```

**Example usage:**

```bash
$ sudo parted /dev/sdb mklabel gpt
$ sudo parted /dev/sdb mkpart primary ext4 0% 100%
$ sudo parted /dev/sdb print
Model: Virtio Block Device (virtblk)
Disk /dev/sdb: 21.5GB
Partition Table: gpt
Number  Start   End     Size    File system  Name     Flags
 1      1049kB  21.5GB  21.5GB               primary
```

**Key subcommands:**

| Subcommand                      | Meaning                                                                                                         |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `mklabel gpt` / `mklabel msdos` | Create a new GPT or MBR partition table (`msdos` is `parted`'s name for MBR)                                    |
| `mkpart`                        | Create a partition                                                                                              |
| `rm`                            | Delete a partition                                                                                              |
| `print`                         | Display the current table                                                                                       |
| `resizepart`                    | Resize an existing partition (table entry only — the filesystem inside must be resized separately, §75 Part 10) |

> 💡 **Tip:** `parted`'s non-interactive one-liners (`parted /dev/sdb -- mkpart primary ext4 0% 100%`) are what make it the right tool for automation and scripted provisioning, where `fdisk`'s menu-driven interaction model can't be cleanly scripted without fragile expect-style input piping.

### 5.4 `lsblk`, `blkid`, `partprobe`

These three are inspection and re-sync utilities, not partition editors:

- **`lsblk`** — lists block devices and their partition/mount tree in a readable hierarchy (`lsblk -f` adds filesystem type and UUID columns). The fastest first command to run when orienting on an unfamiliar host's disk layout.
- **`blkid`** — prints filesystem/partition attributes (UUID, filesystem type, label) for a given device, the same UUIDs referenced in `/etc/fstab` (§20).
- **`partprobe`** — asks the kernel to re-read a disk's partition table without a reboot, needed after a partitioning tool has written changes, because the running kernel's in-memory view of a disk's partitions doesn't always update automatically the instant the table on disk changes (this is also why some `fdisk`/`parted` sessions print a note about the kernel needing a reread, or the device being busy).

## 6. Hands-On Walkthrough: Partition → Format → Mount

Partitioning a disk is only step one of a three-step sequence that ties directly back into §18 and §20 — a raw partition, on its own, holds no usable filesystem and cannot be mounted.

```bash
# Step 1: Create the partition table and a partition (parted, scripted)
$ sudo parted /dev/sdb mklabel gpt
$ sudo parted /dev/sdb mkpart primary ext4 0% 100%

# Step 2: Ensure the kernel's view of the partition table is current
$ sudo partprobe /dev/sdb

# Step 3: Confirm the new partition device node exists
$ lsblk /dev/sdb
NAME   MAJ:MIN RM SIZE RO TYPE MOUNTPOINT
sdb      8:16   0  20G  0 disk
└─sdb1   8:17   0  20G  0 part

# Step 4: Create a filesystem ON the partition (§18's territory, not this section's)
$ sudo mkfs.ext4 /dev/sdb1

# Step 5: Mount it (§20's territory)
$ sudo mkdir -p /mnt/data
$ sudo mount /dev/sdb1 /mnt/data

# Step 6: Persist across reboot via /etc/fstab, keyed by UUID (§20)
$ blkid /dev/sdb1
/dev/sdb1: UUID="a1b2c3d4-..." TYPE="ext4"
```

Each step depends on the previous one succeeding: a partition with no filesystem fails to mount (`mount: unknown filesystem type`), and a filesystem created but never mounted is simply inert, occupying space but invisible to the running directory tree.

> ⚠️ **Warning:** Partitioning a disk that is currently mounted, or that holds a running system's root filesystem, is genuinely dangerous — the kernel may refuse certain operations outright, but others (like deleting or resizing a partition table entry while its filesystem is actively in use) can succeed at the table level while leaving the live filesystem in an inconsistent, unrecoverable state. Always unmount (§20) a target device fully before repartitioning it, and never repartition the disk a running system is booted from without a rescue/live environment. Cloud-disk workflows that hot-attach a fresh volume to a running instance and partition it live are safe specifically because that volume was never mounted in the first place — the danger is repartitioning something already in active use, not disk attachment itself.

## 7. Common Misconceptions

1. **"fdisk can't handle GPT disks."** True historically, not true of modern `fdisk` (util-linux) — it fully supports creating and editing GPT tables today. `gdisk` remains relevant for GPT-specific diagnostics and repair, not because `fdisk` lacks GPT support outright.
2. **"Partitioning a disk creates a usable filesystem."** Partitioning only defines byte ranges and their type metadata in the partition table — a partition holds no filesystem, and therefore cannot be mounted, until `mkfs` (§75, Part 10) formats it. Skipping straight from `parted`'s `mkpart` to `mount` fails.
3. **"GPT disks can't be booted on BIOS-only hardware."** They can, via a protective MBR plus a small `bios_grub` partition holding GRUB's second-stage bootloader (4) — GPT and legacy BIOS aren't mutually exclusive, though GPT-with-UEFI is the more common modern pairing.
4. **"LVM replaces the need for partitioning."** LVM sits on top of a partition (or a whole raw disk used as a physical volume) — it's an additional flexible layer for volume management, not a substitute for the partition-table-as-disk-container concept this section covers (§73–§79, Part 10 covers LVM's own layer in full).

## 8. Tiered Interview Questions

**🎯 Beginner:** _"What is a partition table, and why can't you just format a raw disk directly without one?"_
**Model answer:** A partition table is a structure near the start of a disk that divides it into logical sections (partitions), each of which can hold an independent filesystem, swap area, or other data. You technically _can_ put a filesystem directly on a whole raw disk device with no partition table at all, but in practice partitioning is used because it isolates failures and growth between sections, allows different filesystem types or purposes (like a `/boot` partition vs. swap) on one physical disk, and is the expected structure most tooling and bootloaders assume.
_What the interviewer is probing for:_ Basic grasp that a partition table is a layer below the filesystem, not the filesystem itself.

**🎯 Intermediate:** _"What are the concrete limitations of MBR that led to GPT, beyond just 'MBR is old'?"_
**Model answer:** MBR's 64-byte partition table only fits four primary partition entries, forcing the extended/logical-partition workaround for more than four partitions. Its 32-bit sector-addressing fields cap addressable size at roughly 2 TiB per partition. The entire table lives in one 512-byte sector with no backup copy and no checksum, so corruption of that single sector can make every partition unreadable even though the actual data is intact. GPT fixes all three: 128 partitions by default with no extended-partition workaround, 64-bit addressing removing the size ceiling, and a redundant backup header at the end of the disk plus CRC32 checksums for corruption detection.
_What the interviewer is probing for:_ Specific, structural limitations rather than a vague "GPT is newer and better."

**🎯 Senior:** _"A team attached a new 4 TiB cloud data disk, partitioned it, and later noticed only about 2 TiB was usable. What happened, and how do you prevent recurrence?"_
**Model answer:** Whatever partitioning path they used defaulted to an MBR (DOS) partition table rather than GPT — MBR's 32-bit sector-addressing fields cap a partition at roughly 2 TiB regardless of how large the underlying disk actually is, and critically, this doesn't fail loudly; the partition is created successfully, just truncated, so nothing alerts anyone at partition-creation time. The fix is to repartition using GPT (`parted mklabel gpt` or `fdisk`'s `g` command) — which requires the data to be migrated off first since repartitioning destroys the existing table — and to standardize provisioning scripts/golden-image tooling to explicitly create GPT tables rather than relying on a tool's default, since some tools still default to MBR for backward compatibility. I'd also add a post-provisioning check (`lsblk`/`parted print` showing `Partition Table: gpt` and the full expected size) into the provisioning pipeline so a silent MBR-default doesn't reach production disks again.
_What the interviewer is probing for:_ Recognizing the 2 TiB ceiling as a live operational failure mode, not textbook trivia, plus a concrete prevention step (pipeline validation), not just "use GPT."

**🎯 Architect:** _"You're designing the disk-provisioning step of a golden-image pipeline (§102, Part 13) that needs to support both legacy BIOS and UEFI target hardware. What partitioning decisions do you need to get right?"_
**Model answer:** I'd standardize on GPT universally rather than branching logic by target firmware, since GPT supports both boot paths — UEFI natively via an EFI System Partition, and legacy BIOS via a protective MBR plus a small `bios_grub` partition holding GRUB's second-stage loader. That means the image build needs to conditionally include the right boot-support partition (ESP for UEFI targets, `bios_grub` for BIOS targets) while keeping the rest of the partition layout — root, and whatever data/log partitions the standard applies — identical across both, so the rest of the pipeline (filesystem creation, fstab generation by UUID per §20, not by device path) doesn't need firmware-aware branching. I'd script all of this through `parted`'s non-interactive one-liners rather than `fdisk`'s interactive menu, since the pipeline needs to be fully unattended and idempotent, and I'd add an explicit `partprobe` plus `lsblk`/`blkid` verification step after partitioning to confirm the kernel's view and the UUIDs actually match what the rest of the pipeline (fstab generation, bootloader installation) expects before proceeding — silent mismatches here are exactly the kind of failure that only surfaces at first boot, which is the most expensive place to discover a provisioning bug.
_What the interviewer is probing for:_ Ability to reason about GPT/MBR and BIOS/UEFI as a combined constraint in an automated pipeline context, not just definitional knowledge of each piece in isolation.

## 9. Key Takeaways

- A partition table divides a raw block device into logical partitions before any filesystem can be created — it is the layer directly below §18's filesystem-type coverage, and a partition holding no filesystem cannot be mounted (§20).
- MBR (512-byte sector 0) is limited to four primary partitions natively (extended/logical partitions as a workaround), caps partitions at roughly 2 TiB via 32-bit sector addressing, and has no backup copy or checksum — a single point of failure.
- GPT supports 128 partitions by default, 64-bit addressing removing the size ceiling, a redundant backup header at the end of the disk plus CRC32 checksums, and GUID-based identification that underpins UUID-keyed `/etc/fstab` entries.
- BIOS boots via MBR boot code (or a `bios_grub` partition on a GPT disk); UEFI boots via a dedicated EFI System Partition on GPT — the partition table format and firmware mode have to agree, and GPT-with-`bios_grub` lets one partitioning scheme serve both.
- `fdisk` (now GPT-capable too) and `gdisk` (GPT-specific) are interactive tools; `parted` is the scriptable choice for automation; `lsblk`/`blkid`/`partprobe` inspect and re-sync rather than edit.
- Partition → format (`mkfs`, §75 Part 10) → mount (§20) is a strict sequence, and repartitioning a disk that is currently mounted or actively in use is a real, non-theoretical corruption risk — always unmount first.

## 10. Related Concepts & What's Next

This section is the layer directly beneath §18's filesystem-type coverage and a direct prerequisite for §20's mounting and `/etc/fstab` mechanics — a partition only becomes mountable once §18 and §20's steps are applied on top of it. It ties back to §7 (Part 2)'s BIOS/UEFI boot-process coverage for the MBR/GPT-to-firmware relationship, and forward to §73–§79 (Part 10), where LVM adds a flexible volume-management layer on top of the partition-as-container concept introduced here. §24 (next) moves to `/proc` and `/sys` — the virtual filesystems used for live kernel and hardware introspection, a different kind of "filesystem" than the on-disk partitions this section covers.

**Next Section:** §24 — `Section-24-Part3-Proc-Sys-Virtual-Filesystems.md`
