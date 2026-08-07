# Section 76 (Part 10): Filesystem Creation, Checking, and Repair (mkfs, fsck, tune2fs/xfs_repair)

## 1. Overview: The Layer Above the Block Device

[§73](./Section-73-Part10-LVM-Physical-Volumes-Volume-Groups-Logical-Volumes.md)–[§75](./Section-75-Part10-RAID-Concepts-Mdadm.md) covered three different ways to construct a block device — a plain partition, an LVM Logical Volume, an `mdadm` RAID array — but every one of them still needs a filesystem put on it before it's usable, and that filesystem can still develop problems that need checking and repair regardless of what's underneath it. [§18](../Part3/Section-18-Part3-Filesystem-Types.md) introduced filesystem types (ext4, XFS, Btrfs, tmpfs, overlayfs) at a conceptual level; this section is where the full operational depth — creation options, checking, repair, and tuning — actually lives, deliberately scoped to ext4 and XFS as the two mainstream production choices.

> 💡 **Tip:** Everything in this section is filesystem-agnostic to _what's underneath it_ — `mkfs.ext4` works identically whether the target is `/dev/sdb1`, `/dev/data_vg/app_lv` ([§73](./Section-73-Part10-LVM-Physical-Volumes-Volume-Groups-Logical-Volumes.md)), or `/dev/md0` ([§75](./Section-75-Part10-RAID-Concepts-Mdadm.md)). The filesystem layer doesn't know or care which of those it's sitting on.

## 2. Creating Filesystems: the `mkfs` Family

`mkfs` is a front-end dispatching to filesystem-specific tools (`mkfs.ext4`, `mkfs.xfs`, `mkfs.btrfs`, etc.) based on the type requested.

```bash
# Create an ext4 filesystem with a volume label
mkfs.ext4 -L app_data /dev/data_vg/app_lv

# Create an XFS filesystem with a volume label
mkfs.xfs -L app_data /dev/data_vg/app_lv
```

**Key ext4 creation-time options:**

| Flag           | Meaning                                                                                   |
| -------------- | ----------------------------------------------------------------------------------------- |
| `-L <label>`   | Volume label, settable later too via `tune2fs` (5)                                        |
| `-m <percent>` | Reserved-blocks percentage for root (defaults to 5%; see 5 for changing it post-creation) |
| `-b <size>`    | Block size (commonly 4096 bytes; rarely worth overriding on modern disks)                 |

**Key XFS creation-time options:**

| Flag         | Meaning                                                                                                                                              |
| ------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-L <label>` | Volume label                                                                                                                                         |
| `-f`         | Force creation even if an existing filesystem signature is detected on the target — needed when reusing a device that previously held something else |

> ⚠️ **Warning:** `mkfs` (of any type) is destructive and irreversible against whatever was previously on the target device — there's no built-in confirmation prompt beyond XFS's existing-signature check (and even that's bypassed by `-f`). Double-checking the target device path before running `mkfs` against it belongs in the same category of "measure twice" discipline as `dd` ([§79](./Section-79-Part10-Backup-Strategies-Tools.md)) — a single wrong device argument silently destroys whatever filesystem or data was there.

## 3. `fsck`/`e2fsck`: Checking and Repairing ext-Family Filesystems

**`fsck`** ("filesystem check") is the generic front-end; for ext2/ext3/ext4 specifically, it dispatches to **`e2fsck`**, which does the actual work.

**When it runs automatically:** modern ext4 filesystems track a mount count and a time-since-last-check, and historically would force a full check after a certain number of mounts or elapsed time — on most current distributions this automatic-check-on-boot behavior is disabled or set to effectively never trigger by default, but it's still configurable per-filesystem (5). ext4 also runs a fast, automatic **journal replay** on mount after an unclean shutdown — this is not the same thing as a full `fsck` check; it's much faster and only replays the last few pending journal transactions rather than scanning the whole filesystem.

**Running it manually:**

```bash
# Force a full check even if the filesystem otherwise looks clean
e2fsck -f /dev/data_vg/app_lv

# Force a check AND automatically fix any problems found without prompting
e2fsck -fy /dev/data_vg/app_lv
```

**Key flags:**

| Flag | Meaning                                                                                                          |
| ---- | ---------------------------------------------------------------------------------------------------------------- |
| `-f` | Force a full check even if the filesystem's clean flag says it doesn't need one                                  |
| `-y` | Assume "yes" to every repair prompt — needed for unattended/scripted runs                                        |
| `-n` | Assume "no" to every prompt — a safe, read-only-answer way to see what _would_ be flagged without making changes |

> ⚠️ **Warning:** Never run `fsck`/`e2fsck` against a filesystem that is currently mounted read-write and in active use. `fsck` assumes exclusive access to make structural changes to the filesystem's metadata — running it against a live, actively-changing mounted filesystem risks the check and repair logic racing against the kernel's own in-flight writes, which can cause **worse** corruption than whatever prompted the check in the first place, not a fix. The correct sequence is always: unmount first ([§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md)), then check/repair, then remount. The one narrow exception is the root filesystem itself, which typically can't be unmounted while running — that's specifically why root filesystem checks happen very early in boot, before it's mounted read-write, rather than being run against a live root filesystem later.

## 4. `xfs_repair`: XFS's Equivalent, With a Real Difference

XFS does **not** use `fsck` or `e2fsck` — running generic `fsck` against an XFS filesystem is effectively a no-op (XFS's own `fsck.xfs` stub does nothing beyond a trivial check by design). XFS's actual repair tool is **`xfs_repair`**, and it works differently in a way worth calling out explicitly:

```bash
xfs_repair /dev/data_vg/app_lv
```

- **XFS must be unmounted before `xfs_repair` runs** — there is no live/mounted-repair equivalent at all, unlike ext4 where the danger is real but the _possibility_ of accidentally running it mounted at least exists. `xfs_repair` will typically refuse outright against a mounted filesystem rather than silently risking damage.
- XFS relies heavily on its own internal **journaling/log replay** to recover from unclean shutdowns automatically at mount time (similar in spirit to ext4's journal replay in 3) — `xfs_repair` is reserved for structural corruption beyond what log replay can fix on its own, not routine post-crash recovery.
- If `xfs_repair` reports that the log itself is corrupt and can't be replayed cleanly, the `-L` flag force-zeroes the log — this is a **data-loss operation** (any transactions that hadn't been fully committed are discarded) and is a last resort, not a routine flag to reach for.

> 💡 **Tip:** The clean mental shortcut for this whole section: **ext4 → `fsck`/`e2fsck`; XFS → `xfs_repair`.** Reaching for `fsck` on an XFS filesystem out of habit is a common tell that someone is applying ext4 muscle memory to XFS without realizing the tools genuinely don't correspond.

## 5. `tune2fs`: Adjusting ext-Family Parameters Post-Creation

**`tune2fs`** adjusts ext2/ext3/ext4 filesystem parameters after creation, without needing to recreate the filesystem — several of `mkfs.ext4`'s creation-time options (2) have a `tune2fs` counterpart for changing them later.

```bash
# View current filesystem parameters
tune2fs -l /dev/data_vg/app_lv

# Change the reserved-blocks percentage (default is 5%, reserved for root)
tune2fs -m 1 /dev/data_vg/app_lv

# Set or change the volume label
tune2fs -L app_data_v2 /dev/data_vg/app_lv

# Force a check every N mounts, or disable mount-count-based checks (0 = disable)
tune2fs -c 20 /dev/data_vg/app_lv
tune2fs -c 0 /dev/data_vg/app_lv
```

**Why the reserved-blocks percentage matters operationally:** ext4 reserves a percentage of total space (default 5%) that only root can write into, specifically so that a filesystem filling up under a non-root workload doesn't lock out root's ability to log in, write logs, or otherwise fix the problem. On a large data volume, 5% can be a genuinely large amount of unusable space from the application's perspective — lowering it with `tune2fs -m` on volumes where that safety margin isn't needed (e.g., a dedicated data volume where root doesn't need write headroom the way it does on `/` or `/var`) reclaims real usable space, but it's a deliberate trade-off against that safety margin, not a free win.

## 6. Troubleshooting Flow: "The Filesystem Won't Mount"

A practical sequence tying this section's tools together, for a filesystem that refuses to mount:

1. **Check what `mount` itself reports.** The error message often distinguishes between "wrong filesystem type / bad superblock" and other issues outright.
2. **Confirm the filesystem type actually matches what's being assumed** — `blkid /dev/data_vg/app_lv` or `lsblk -f` reports the detected filesystem type; mounting with the wrong `-t` type explicitly specified is a surprisingly common self-inflicted cause.
3. **For ext4:** run `e2fsck -f` (unmounted, per the Warning in 3) and let it report or repair whatever it finds — a bad superblock can often be recovered from a backup superblock location, which `e2fsck` can be pointed at with `-b <backup-superblock-block>` if the primary superblock itself is unreadable.
4. **For XFS:** run `xfs_repair` (unmounted, per 4) — if it reports the log can't be replayed, weigh the `-L` force-zero-log option's data-loss implication before using it, and only after confirming a backup exists.
5. **If repair succeeds, remount and verify** — check `dmesg`/`journalctl` ([§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md)) for kernel-level messages logged at the time of the original failure, since they often point at the root cause (failing disk hardware, a RAID array that was degraded at the time, [§75](./Section-75-Part10-RAID-Concepts-Mdadm.md)) rather than just the filesystem-level symptom.
6. **If repair doesn't fully succeed**, this is the point where restoring from backup ([§79](./Section-79-Part10-Backup-Strategies-Tools.md)) is the correct next step rather than continuing to escalate repair attempts against a filesystem that's telling you it can't reliably reconstruct its own metadata.

## 7. Common Misconceptions

1. **"`fsck` works the same way regardless of filesystem type."** It doesn't — `fsck` is a real, functional front-end for ext-family filesystems (dispatching to `e2fsck`), but for XFS it's effectively a no-op stub; XFS repair goes through `xfs_repair` exclusively (4).
2. **"It's fine to run a quick fsck on a live mounted filesystem to check for problems."** It's not, for read-write mounted filesystems (3's Warning) — the check-and-write nature of `fsck` racing against ongoing filesystem activity risks causing worse damage than it fixes; unmount first.
3. **"XFS can be shrunk the same way it can be grown."** Covered in depth in [§74](./Section-74-Part10-LVM-Resizing-Snapshots-Thin-Provisioning.md), but worth repeating here from the creation/repair angle: XFS's on-disk design has no shrink path at all — `xfs_growfs` only grows, and reducing an XFS filesystem's size requires backup/recreate/restore.
4. **"tune2fs and mkfs.ext4 options are basically the same thing at different times."** Related but not identical in scope — several `mkfs.ext4` creation-time choices (like block size) are fixed permanently at creation and can't be changed later by any tool, while others (label, reserved-blocks percentage, check interval) remain adjustable post-creation via `tune2fs` (5); knowing which category a given option falls into matters before committing to it at creation time.

## 8. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `mkfs` and `fsck`, and when would you use each?"_
**Model answer:** `mkfs` (and its type-specific variants like `mkfs.ext4`/`mkfs.xfs`) creates a brand-new, empty filesystem on a block device — it's a destructive, one-time operation against whatever was previously there. `fsck` (dispatching to `e2fsck` for ext-family filesystems) checks an existing filesystem's structural integrity and can repair problems it finds — used after a suspected corruption event like an unclean shutdown or reported I/O errors, not as part of normal creation.
_What the interviewer is probing for:_ Clean separation of "create" versus "check/repair" as distinct lifecycle operations, not conflating the two.

**🎯 Intermediate:** _"Why doesn't `fsck` work on XFS the way it does on ext4?"_
**Model answer:** XFS was designed with a different repair philosophy — its own internal journaling handles routine unclean-shutdown recovery automatically at mount time, and structural repair beyond that goes through its own dedicated tool, `xfs_repair`, rather than the generic `fsck` front-end. Running plain `fsck` against an XFS filesystem hits a stub that does effectively nothing by design; it's not a bug or a missing feature, it's XFS deliberately not participating in the ext-family `fsck` model. `xfs_repair` also requires the filesystem to be unmounted first, with no live-repair equivalent at all, which is a stricter requirement than ext4's fsck-on-a-live-filesystem danger (which is possible, just strongly discouraged).
_What the interviewer is probing for:_ Recognizing this as a genuine architectural difference between the two filesystems, not just a syntax difference between two equivalent tools.

**🎯 Senior:** _"A production ext4 volume is reporting I/O errors, and you suspect filesystem corruption. Walk me through your response."_
**Model answer:** First, I'd check `dmesg`/`journalctl` for the underlying hardware signal — is this a failing disk, a degraded RAID array ([§75](./Section-75-Part10-RAID-Concepts-Mdadm.md)), or a genuinely filesystem-level issue — because if the disk itself is failing, running repair tools against it repeatedly without addressing the hardware is treating a symptom. Assuming the disk is healthy enough to proceed, I'd schedule a maintenance window to unmount the filesystem — never run `e2fsck` against it live — and run `e2fsck -f` first without `-y` to see what it reports before automatically applying fixes, since understanding the scope of corruption matters before blindly accepting every proposed repair. If the corruption is severe enough that `e2fsck` can't cleanly reconstruct the filesystem's own metadata, I'd stop escalating repair attempts and restore from backup instead ([§79](./Section-79-Part10-Backup-Strategies-Tools.md)) rather than risk further silent damage from repeated repair passes. Throughout, I'd want to know whether this volume has a recent LVM snapshot ([§74](./Section-74-Part10-LVM-Resizing-Snapshots-Thin-Provisioning.md)) or backup available before touching anything destructive.
_What the interviewer is probing for:_ Root-cause thinking (hardware vs. filesystem), correct unmount-first discipline, knowing when to stop repairing and restore instead, and connecting back to backup/snapshot readiness rather than treating repair as the only tool available.

**🎯 Architect:** _"You're setting a fleet-wide standard for filesystem provisioning. What decisions do you bake in at `mkfs` time, and why does it matter to get them right upfront rather than adjusting later?"_
**Model answer:** For ext4 volumes, I'd standardize the reserved-blocks percentage per volume role — default 5% for `/` and `/var` where root needs write headroom during a full-disk incident, lowered via `tune2fs -m` (or set at creation) on dedicated data volumes where that headroom isn't needed and the reclaimed space is meaningful at scale. Block size I'd leave at the modern default rather than override without a specific, measured reason, since it's one of the options that's fixed permanently at creation and can't be changed later without recreating the filesystem entirely. For any volume expected to need growth, I'd make sure it's provisioned on an LVM LV ([§73](./Section-73-Part10-LVM-Physical-Volumes-Volume-Groups-Logical-Volumes.md)) rather than a bare partition from the start, since retrofitting LVM under an existing filesystem is far more disruptive than provisioning it that way from day one. For volumes with any realistic chance of ever needing to shrink, I'd standardize on ext4 rather than XFS specifically because of XFS's grow-only limitation — that's a decision that's essentially free to make correctly at provisioning time and expensive to fix later (backup/recreate/restore) if it turns out to matter.
_What the interviewer is probing for:_ Recognizing which `mkfs`-time decisions are cheap to change later versus effectively permanent, and designing provisioning standards around that asymmetry rather than treating every option as equally adjustable after the fact.

## 9. Key Takeaways

- `mkfs.ext4`/`mkfs.xfs` create filesystems identically regardless of what block device sits underneath (plain partition, LVM LV, RAID array) — the filesystem layer is agnostic to that.
- `fsck`/`e2fsck` is the ext-family check/repair tool — `-f` forces a full check, `-y` auto-fixes — and must never run against a mounted, actively-written read-write filesystem.
- XFS uses `xfs_repair`, not `fsck` (which is a no-op stub for XFS) — it requires the filesystem to be unmounted first, with no live-repair path, and `-L` to force-zero a corrupted log is a data-loss last resort.
- `tune2fs` adjusts ext-family parameters post-creation (label, reserved-blocks percentage, check interval) — but some `mkfs`-time decisions like block size are effectively permanent and can't be changed this way.
- A practical "won't mount" troubleshooting flow: confirm the actual filesystem type, run the correct type-specific repair tool unmounted, check `dmesg`/`journalctl` for the underlying hardware signal, and fall back to backup restore once repair stops making reliable progress.

## 10. Related Concepts & What's Next

This section is the full operational depth behind [§18](../Part3/Section-18-Part3-Filesystem-Types.md)'s (Part 3) conceptual filesystem-type introduction, and it closes the loop [§74](./Section-74-Part10-LVM-Resizing-Snapshots-Thin-Provisioning.md) opened on the ext4-vs-XFS shrink asymmetry — reinforced here from the creation/repair side rather than the resizing side. [§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md)'s (Part 3) mount/unmount conventions are the precondition for nearly every repair operation covered here. This is also the natural point to connect back to [§75](./Section-75-Part10-RAID-Concepts-Mdadm.md)'s RAID coverage — a filesystem-level symptom sometimes has a hardware-level root cause one layer down. [§77](./Section-77-Part10-Swap-Management.md) continues Part 10 with swap management, a different storage-adjacent topic with no direct dependency on this section's repair tooling.

**Next Section:** [§77](./Section-77-Part10-Swap-Management.md) — `Section-77-Part10-Swap-Management.md`
