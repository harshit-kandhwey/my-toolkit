# Section 20 (Part 3): Mounting and Unmounting, /etc/fstab, Mount Options

## 1. What Mounting Actually Means

A filesystem sitting on a block device — a disk partition, an LVM logical volume (§73–§79), a network share, an ISO image — is inert data until it is **mounted**: attached at a specific point in the single, unified directory tree §17 described. Linux has no concept of separate drive letters; every accessible filesystem, however many physical or virtual devices back it, is grafted onto some directory under `/`. That directory is the **mount point**, and until something is mounted there, it's just an ordinary (usually empty) directory.

Mounting does three things at once: it tells the kernel which **filesystem driver** to use to interpret the device's contents (ext4, XFS, Btrfs, vfat, nfs — §18 covered the filesystem types themselves), it makes that filesystem's directory tree visible at the mount point, and it can attach a set of **mount options** that govern how the kernel treats that filesystem for as long as it stays mounted (read-only, no `atime` updates, no `setuid` honored, and so on — covered in depth in 4).

> 💡 **Tip:** Whatever was in the mount point directory before mounting is not deleted — it's just hidden. Unmount the filesystem and the original contents reappear untouched. This is a common source of "where did my files go" confusion when someone mounts a new filesystem on top of a non-empty directory.

## 2. The `mount` Command

**Purpose:** Attach a filesystem to a mount point, either using values already declared in `/etc/fstab` (3) or by specifying everything explicitly on the command line.

**Syntax:**

```bash
mount [-t fstype] [-o options] device mountpoint
mount mountpoint          # short form — must have a matching /etc/fstab entry
mount -a                  # mount everything listed in /etc/fstab that isn't already mounted
```

**Key flags:**

| Flag                 | Meaning                                                                                          |
| -------------------- | ------------------------------------------------------------------------------------------------ |
| `-t <fstype>`        | Filesystem type (`ext4`, `xfs`, `nfs`, `vfat`, ...) — often auto-detected if omitted             |
| `-o <options>`       | Comma-separated mount options (4) — e.g. `-o ro,noatime`                                         |
| `-a`                 | Mount all filesystems in `/etc/fstab` (except those marked `noauto`) that aren't already mounted |
| `-r` / `--read-only` | Shortcut for `-o ro`                                                                             |
| `-v`                 | Verbose — show each step taken                                                                   |
| `-n`                 | Mount without writing to `/etc/mtab` (used when `/` is still read-only, e.g. during early boot)  |

**Example usage and expected output:**

```bash
$ sudo mount -t ext4 -o defaults /dev/sdb1 /mnt/data
$ mount | grep sdb1
/dev/sdb1 on /mnt/data type ext4 (rw,relatime)

$ sudo mount -a
```

Running `mount` with no arguments at all lists every currently mounted filesystem, device, mount point, type, and active options — the fastest way to answer "what's mounted where, with what options, right now."

**Production usage example:** After running `parted`/`fdisk` and `mkfs` to create a new partition and filesystem (§18, §77), the mount step is what actually makes it usable — a common runbook is: partition → `mkfs` → add an `/etc/fstab` entry → `mount -a` to test the entry works exactly as it will on next boot, rather than mounting manually and forgetting to persist it.

**Common errors:**

- `mount: unknown filesystem type` — the kernel module for that filesystem isn't loaded or the userspace helper (e.g. `nfs-common` for NFS) isn't installed.
- `mount: /mnt/data: special device /dev/sdb1 does not exist` — device path is wrong, or the disk hasn't been partitioned/recognized yet (check `lsblk`).
- Mounting over a non-empty directory without realizing it — the pre-existing contents are hidden, not deleted, but this confuses people until they unmount.

**Troubleshooting:** If `mount -a` silently does nothing for an entry, check the `noauto` option and whether the entry has a typo in its device/UUID field — `mount -a` skips entries it can't parse without always erroring loudly depending on the field involved.

## 3. `/etc/fstab`: The Persistent Mount Table

`/etc/fstab` ("filesystem table") is the configuration file that tells the system which filesystems to mount **automatically at boot**, and gives short, memorable references (mount points) to filesystems that can otherwise be mounted manually by just naming the mount point (`mount /data` rather than typing the full device and options). Every line describes one filesystem, in **six whitespace-separated fields**:

```text
<device>              <mount point>   <fstype>   <options>          <dump>   <pass>
UUID=1a2b3c4d-...      /data           ext4       defaults,noatime   0        2
/dev/sdb2              swap            swap       sw                 0        0
10.0.0.5:/export/nfs   /mnt/nfs        nfs        defaults,nofail    0        0
```

**Field-by-field breakdown:**

1. **Device** — what to mount. Can be a raw device path (`/dev/sdb1`), a `UUID=`, a `LABEL=`, or (for network filesystems) a host:path pair. See 3.1 for why UUID is strongly preferred over the raw path.
2. **Mount point** — the absolute directory the filesystem attaches to. Must already exist as a directory before `mount -a` can succeed against it. `swap` is a special-case placeholder for swap space, which has no directory mount point.
3. **Filesystem type** — `ext4`, `xfs`, `nfs`, `vfat`, `swap`, or `auto` to let the kernel detect it.
4. **Options** — comma-separated, no spaces (4 covers the common ones in depth). `defaults` expands to a standard baseline (`rw,suid,dev,exec,auto,nouser,async`).
5. **Dump** — legacy field for the `dump` backup utility; `0` means "don't back up with `dump`," `1` means "do." In practice almost every modern system sets this to `0` — `dump` itself is rarely used today (§79 covers modern backup tooling).
6. **Pass** — controls `fsck` order at boot. `0` means never `fsck` this filesystem (correct for swap, network filesystems, and anything that shouldn't be checked at boot). `1` is reserved for the root filesystem specifically. `2` means check it, but after root, and filesystems with the same pass number can be checked in parallel. XFS ignores this field in practice (it doesn't use traditional `fsck` the way ext4 does — §77 covers filesystem-specific check/repair tools).

### 3.1 UUID vs. Device Name: Why UUID Wins

Referencing `/dev/sdb1` directly is fragile: device names are assigned by **enumeration order** at boot, which can shift when a disk is added, removed, or a controller re-enumerates devices differently after a kernel or hardware change. A filesystem that was `/dev/sdb1` yesterday can become `/dev/sdc1` today with no configuration change on your part — and if `/etc/fstab` hardcodes the old name, the system can fail to boot cleanly, or worse, silently mount the wrong device at that mount point.

A **UUID** (Universally Unique Identifier) is generated once, at filesystem-creation time, and stored inside the filesystem's own metadata — it travels with the filesystem regardless of which device node the kernel happens to assign it on a given boot. `LABEL=` is a middle ground (human-assigned, more readable than a UUID, but not guaranteed unique across disks the way a UUID is).

```bash
# Find a device's UUID
$ blkid /dev/sdb1
/dev/sdb1: UUID="1a2b3c4d-5e6f-7a8b-9c0d-1e2f3a4b5c6d" TYPE="ext4"

# Or list all block devices with their UUIDs at once
$ lsblk -f
```

> ⚠️ **Warning:** Editing `/etc/fstab` incorrectly can leave a system **unable to boot to a usable state** — a bad entry for a non-`nofail` filesystem can drop the boot process into an emergency shell waiting for a root password at the console. Always test new entries with `sudo mount -a` before rebooting, and know the `nofail` option (4) for anything that isn't strictly required for the system to function.

## 4. Common Mount Options

| Option            | Effect                                                                                                                                                                                                                              |
| ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `defaults`        | Baseline set: `rw,suid,dev,exec,auto,nouser,async` — the sane default for most local filesystems                                                                                                                                    |
| `ro`              | Mount read-only — no writes permitted, useful for recovery media, compliance-locked data, or protecting a source volume                                                                                                             |
| `rw`              | Mount read-write (default, but sometimes stated explicitly)                                                                                                                                                                         |
| `noatime`         | Don't update file **access time** on every read — meaningfully reduces write I/O on read-heavy workloads (databases, high-traffic web roots) since a plain read no longer triggers a metadata write                                 |
| `relatime`        | A middle ground (and the modern kernel default even without specifying it): update access time only when it's older than the modify or change time — most of `noatime`'s I/O benefit with slightly more POSIX-conventional behavior |
| `nofail`          | Don't block boot if this filesystem fails to mount (log the failure and continue) — critical for removable media, optional network shares, or any mount that shouldn't be able to strand the boot process                           |
| `noauto`          | Don't mount automatically at boot or on `mount -a` — only mount when explicitly named (`mount /mnt/data`)                                                                                                                           |
| `nosuid`          | Ignore SUID/SGID bits on this filesystem — a hardening option for untrusted or removable media (§27, §89 cover SUID/SGID and kernel-hardening context)                                                                              |
| `noexec`          | Prevent execution of binaries from this filesystem — common on `/tmp` or upload directories as a defense-in-depth measure                                                                                                           |
| `user` / `nouser` | Whether non-root users are permitted to mount this filesystem themselves (`nouser` is the safer default)                                                                                                                            |
| `sync` / `async`  | Whether writes are flushed to the device immediately (`sync`, slower, safer) or buffered (`async`, faster, default for most filesystems)                                                                                            |

> 💡 **Tip:** `nofail` is worth defaulting to for anything that isn't the root filesystem or otherwise mission-critical to have mounted before the system is considered "up" — an NFS share that's briefly unreachable at boot, or a secondary disk that's occasionally removed for maintenance, shouldn't be able to hang the entire boot sequence or drop the box into an emergency shell.

## 5. Unmounting: `umount`

**Purpose:** Detach a mounted filesystem, making its mount point directory revert to showing whatever (if anything) was underneath it.

**Syntax:**

```bash
umount <mountpoint>
umount <device>
umount -l <mountpoint>     # lazy unmount
umount -f <mountpoint>     # force (mainly for unresponsive NFS mounts)
```

**Example usage and expected output:**

```bash
$ sudo umount /mnt/data
$ mount | grep /mnt/data
# (no output — successfully unmounted)
```

**Common errors — "device is busy":**

```bash
$ sudo umount /mnt/data
umount: /mnt/data: target is busy.
```

This means some process still has an open file handle, a working directory, or a mapped memory region on that filesystem. Diagnose with:

```bash
$ sudo lsof +f -- /mnt/data      # list open files under the mount point
$ sudo fuser -vm /mnt/data       # list processes using the mount point
```

`fuser -vm` is usually the faster first check for "which process, specifically" — it prints PIDs and access mode (`c` for current directory, `e` for executable, `f` for open file, `r` for root directory) directly against the mount point. Once identified, either stop/redirect that process cleanly or, if it genuinely can't be stopped in time, fall back to a lazy unmount.

**Lazy unmount (`umount -l`):** Detaches the filesystem from the directory tree **immediately** — no new opens against it will succeed — but defers the actual cleanup (releasing the underlying device) until every existing open reference to it is closed. This is useful when you need the mount point free right now (to remount something else there, for instance) but can't cleanly stop whatever process is holding it open.

> ⚠️ **Warning:** `umount -l` doesn't fix "device is busy," it defers the problem — the underlying device isn't actually released until the last reference closes, and if that process never releases its handle (a stuck or leaked process), the device stays partially attached indefinitely. Prefer identifying and stopping the offending process with `lsof`/`fuser` first; reach for `-l` when you need the mount point free immediately and can't wait, not as a routine substitute for a clean unmount.

**Force unmount (`umount -f`):** Primarily relevant for NFS or other network filesystems that have become unresponsive — it forces the unmount even though the kernel can't cleanly negotiate it with the remote side. It is not a generally safe substitute for resolving a "busy" local filesystem and can leave I/O in an inconsistent state for whatever process was mid-operation.

## 6. Common Misconceptions

1. **"Mounting deletes whatever was already in the mount point directory."** It hides it, not deletes it — the original contents reappear once the filesystem is unmounted. This trips people up when they mount onto a non-empty directory by mistake and think data was lost.
2. **"`umount -l` is a safe, routine way to unmount something that's busy."** It defers releasing the device rather than resolving the underlying cause — the correct first step is identifying the offending process with `lsof`/`fuser` and stopping it, reserving `-l` for cases where the mount point must be freed immediately and the process truly can't be stopped in time.
3. **"Device paths like `/dev/sdb1` are a stable, safe way to reference disks in `/etc/fstab`."** Device enumeration order can shift across boots or hardware changes; `UUID=` (or `LABEL=`) is the durable reference, not the device path (3.1).
4. **"The `pass` field in `/etc/fstab` matters equally for every filesystem type."** XFS doesn't use traditional boot-time `fsck` the way ext4 does, so the field is effectively inert for XFS entries even though it's still conventionally set.
5. **"`noatime` breaks anything that depends on access times."** Very few things actually depend on `atime` in practice (some mail delivery agents and a handful of niche tools are the classic exceptions) — for the overwhelming majority of servers, `noatime`'s I/O savings are a safe, standard-practice win, and `relatime` is the still-safer modern default even without specifying it.

## 7. Tiered Interview Questions

**🎯 Beginner:** _"What does mounting a filesystem actually do, and what happens to a directory's existing contents if you mount something on top of it?"_
**Model answer:** Mounting attaches a filesystem (from a device, partition, network share, etc.) to a directory in the tree, making its contents accessible at that path and telling the kernel which filesystem driver to use to interpret it. If you mount onto a directory that already has files in it, those files aren't deleted — they're just hidden while the new filesystem is mounted there, and they reappear once you unmount.
_What the interviewer is probing for:_ Basic correctness on a commonly-misunderstood mechanic, since "where did my files go" is a real, frequent point of confusion.

**🎯 Intermediate:** _"Walk me through the six fields of an `/etc/fstab` line, and explain why UUID is generally preferred over a raw device path."_
**Model answer:** The fields are device, mount point, filesystem type, options, dump, and pass. Device identifies what to mount — UUID, LABEL, or a raw path like `/dev/sdb1`; mount point is where it attaches; fstype tells the kernel which driver to use; options control behavior like `noatime` or `nofail`; dump is a legacy flag for the largely-obsolete `dump` backup tool; pass controls `fsck` ordering at boot, with `1` reserved for root and `0` meaning never check. UUID is preferred over a raw device path because device names are assigned by enumeration order at boot and can shift when disks are added, removed, or hardware changes — a UUID is generated once at filesystem creation and stored in the filesystem's own metadata, so it stays correct regardless of which device node the kernel happens to assign that boot.
_What the interviewer is probing for:_ Whether the candidate has actually edited `/etc/fstab` in practice, not just recited field names, and understands the operational reason behind the UUID convention rather than treating it as arbitrary.

**🎯 Senior:** _"A colleague runs `umount /mnt/data` and gets 'device is busy.' They immediately follow up with `umount -l` and consider the problem solved. What's your take?"_
**Model answer:** `umount -l` isn't wrong to know, but treating it as "solved" is the mistake — a lazy unmount detaches the mount point from the directory tree immediately so no new opens succeed, but it doesn't release the underlying device until every existing open handle closes. If whatever process was holding it open is stuck, leaked, or simply never exits, the device stays partially attached indefinitely, which can bite later — e.g., trying to physically remove or repurpose that disk while it's still not fully released. The better first step is `fuser -vm /mnt/data` or `lsof +f -- /mnt/data` to identify exactly which process has it open, then decide whether to stop that process cleanly, wait for it to finish, or, only if there's a genuine time constraint, accept the lazy unmount as a deliberate tradeoff rather than a default reflex.
_What the interviewer is probing for:_ Understanding that `-l` defers rather than resolves the underlying issue, and the diagnostic instinct to reach for `lsof`/`fuser` before reaching for a shortcut flag.

**🎯 Architect:** _"You're designing the `/etc/fstab` policy for a fleet where some hosts have optional NFS shares and some secondary disks that are periodically physically swapped for maintenance. What do you standardize on, and why?"_
**Model answer:** Every non-root mount that isn't strictly required for the host to be considered "up" gets `nofail`, full stop — an NFS share that's briefly unreachable at boot or a disk that's out for maintenance should never be able to strand the boot process in an emergency shell waiting at a console nobody's physically in front of. I'd reference every device by UUID rather than a raw device path given how easily enumeration order shifts, especially on hosts where disks are physically swapped. For the NFS shares specifically I'd also default to `noatime`/`relatime` plus whatever timeout/retry options make sense for the network path, since a hung, un-tuned NFS mount is one of the more common causes of a seemingly-unrelated process appearing to stall. And I'd bake "test with `mount -a` before rebooting" into whatever change-management process touches `/etc/fstab`, since a bad entry on a fleet host without console access nearby is a much more expensive mistake to recover from than on a single workstation.
_What the interviewer is probing for:_ Fleet-scale judgment — recognizing that a single misconfigured `/etc/fstab` entry has a much higher blast radius in production than in a lab, and translating that into concrete, defensible defaults (`nofail`, UUID references, tested changes) rather than just listing mount options.

## 8. Key Takeaways

- Mounting attaches a filesystem to a mount point in the single unified tree — it hides, but never deletes, whatever was previously in that directory.
- `/etc/fstab` has six fields: device, mount point, fstype, options, dump, pass — `pass=1` is reserved for root, `pass=0` skips `fsck` entirely (appropriate for swap and network filesystems).
- UUID (or LABEL) references are strongly preferred over raw device paths in `/etc/fstab`, because device enumeration order can shift across boots or hardware changes while a UUID stays fixed to the filesystem itself.
- `noatime`/`relatime`, `nofail`, `ro`, and `defaults` are the mount options worth knowing cold — `nofail` in particular is what prevents a non-critical mount failure from stranding boot.
- "Device is busy" on `umount` is diagnosed with `lsof`/`fuser`, not reflexively worked around with `umount -l` — lazy unmount defers releasing the device rather than resolving why it's held open.
- Always test new `/etc/fstab` entries with `mount -a` before rebooting — a bad entry can leave a fleet host stuck at an emergency console prompt.

## 9. Related Concepts & What's Next

This section builds directly on the Filesystem Hierarchy Standard from §17 (mount points are FHS directories) and the filesystem types introduced in §18 (what's actually being mounted). §19's inode/hard-link/symlink coverage is a useful companion concept: a mount point is itself a directory entry, but crossing a mount boundary is one of the few cases where a hard link cannot be created (hard links can't span filesystems — a detail §19 flags). §21 (next) moves to everyday file and directory operations — navigation, creation, copying, moving, deletion — now that filesystems are assumed to be mounted and available. LVM and other advanced storage layers that commonly sit underneath what gets mounted here (physical/volume groups, logical volumes, RAID) are covered in full in Part 10, §73–§79.

**Next Section:** §21 — `Section-21-Part3-File-Directory-Operations.md`
