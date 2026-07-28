# Section 74 (Part 10): Resizing, Snapshots, and Thin Provisioning with LVM

## 1. Overview: Why the PV/VG/LV Layer Pays Off

§73 introduced LVM's three-layer abstraction — Physical Volume, Volume Group, Logical Volume — and closed by promising that the payoff for that extra layer of complexity shows up here. Three capabilities exist specifically because storage was decoupled from physical boundaries: **online resizing** without unmounting or migrating data, **snapshots** that capture a point-in-time state cheaply, and **thin provisioning** that lets storage be allocated ahead of when it's physically backed. None of these are possible with a plain, non-LVM partition.

A recurring theme across all three: LVM operates at the **block-device level**, while the filesystem sitting on top of an LV (ext4, XFS — §18) is a separate layer with its own size and its own tools. Resizing the LV and resizing the filesystem on it are two distinct operations, and conflating them is the single most common mistake in this area.

## 2. Growing a Logical Volume: `lvextend`

Growing an LV is safe and can be done **online** — while the filesystem is mounted and in active use — because growing only adds free space at the end; it never touches or reinterprets data that's already there.

```bash
# Grow app_lv by an additional 20G, pulled from the VG's free space
lvextend -L +20G /dev/data_vg/app_lv

# Or grow to consume all remaining free space in the VG
lvextend -l +100%FREE /dev/data_vg/app_lv
```

Growing the LV alone does **not** grow the filesystem sitting on it — the filesystem still reports its old size until its own resize tool is run:

```bash
# ext4: grow the filesystem to fill the now-larger LV (online, no unmount needed)
resize2fs /dev/data_vg/app_lv

# XFS: grow the filesystem — note the target is the MOUNT POINT, not the device
xfs_growfs /mnt/app_data
```

A convenience shortcut combines both steps in one command:

```bash
lvextend -r -L +20G /dev/data_vg/app_lv   # -r resizes the filesystem automatically after extending the LV
```

> 💡 **Tip:** `resize2fs` takes a device path; `xfs_growfs` takes a mount point. This inconsistency trips people up in exactly the way you'd expect during an incident at 2 a.m. — memorize it as "ext4 talks to the block device, XFS talks to the live mounted filesystem," which is also a hint toward the bigger XFS limitation in 3.

## 3. Shrinking: Dangerous, and XFS Can't Do It At All

> ⚠️ **Warning:** Shrinking is fundamentally more dangerous than growing, and the order of operations matters critically — get it backwards and you will destroy data. The **filesystem must be shrunk first**, then the LV shrunk to match. Never shrink the LV before the filesystem: if the LV becomes smaller than the filesystem still thinks it is, the filesystem's own metadata and data blocks that now fall outside the LV's new (smaller) boundary are simply gone, with no warning and no recovery path short of backups.

Correct order for ext4 (the only one of the two filesystems covered here that supports shrinking at all):

```bash
# 1. Unmount first — ext4 shrink is not a safe online operation
umount /mnt/app_data

# 2. Check the filesystem before resizing (fsck is required before a resize2fs shrink)
e2fsck -f /dev/data_vg/app_lv

# 3. Shrink the filesystem to the target size FIRST
resize2fs /dev/data_vg/app_lv 40G

# 4. Only now shrink the LV to match (or slightly above) the new filesystem size
lvreduce -L 40G /dev/data_vg/app_lv

# 5. Remount
mount /dev/data_vg/app_lv /mnt/app_data
```

**XFS cannot shrink, period.** There is no `xfs_shrink` counterpart to `xfs_growfs` — XFS's on-disk structures are not designed to support shrinking, and the only way to reduce an XFS filesystem's effective size is to back up the data, recreate a smaller filesystem, and restore. This is a real, frequently-tested design limitation worth internalizing on its own (§76 covers filesystem creation/repair tooling in full and reinforces this same point from the creation side).

## 4. LVM Snapshots: Copy-on-Write Point-in-Time Capture

An **LVM snapshot** is a point-in-time view of an LV's state at the moment the snapshot was taken, implemented via **copy-on-write (CoW)**: the snapshot itself doesn't copy all the origin LV's data up front — it starts nearly empty and only stores the _original_ version of a data block right before the origin LV overwrites that block. Reading from the snapshot transparently reconstructs the point-in-time view by combining unchanged origin blocks with the snapshot's saved "before" copies of changed ones.

```bash
# Create a 5G snapshot of app_lv, named app_lv_snap
lvcreate -L 5G -s -n app_lv_snap /dev/data_vg/app_lv
```

**Why the snapshot needs its own allocated space, and why that space can run out:** the `-L 5G` here isn't the snapshot's "size" in the sense of holding a full copy of the origin — it's the space reserved to hold changed-block copies as the origin continues being written to. The more the origin LV changes after the snapshot is taken, and the longer the snapshot is kept around, the more of that reserved space gets consumed. Monitor it:

```bash
lvs -o+snap_percent
```

> ⚠️ **Warning:** If a snapshot's allocated space fills up completely before it's removed, the snapshot becomes **invalid** — LVM cannot track further changes to reconstruct the point-in-time view, and the snapshot is unusable from that point forward (some LVM versions automatically drop an exhausted snapshot rather than leaving it in a broken state). This is why a snapshot is a short-lived tool for a bounded operation, not a substitute for a real backup left running indefinitely — undersizing it, or letting it live far longer than planned while the origin churns heavily, is the classic way to lose the very thing it was taken to protect.

**Practical use cases:**

- **Consistent backup source.** Freeze a point-in-time view of a busy database or application data directory, mount the snapshot read-only, and back up _from the snapshot_ — the live origin keeps taking writes uninterrupted while the backup runs against a state that doesn't change mid-backup.
- **Safe testing of risky changes.** Snapshot before a risky upgrade, schema migration, or config change; if it goes wrong, roll back by merging the snapshot back onto the origin (`lvconvert --merge`) instead of restoring from a full backup.

Removing a snapshot once it's no longer needed is simple and important — an old, forgotten snapshot is silently consuming VG space and degrading write performance on the origin (every write to the origin now also costs a CoW copy into the snapshot):

```bash
lvremove /dev/data_vg/app_lv_snap
```

## 5. Thin Provisioning: Allocating More Than You Physically Have

**Thin provisioning** lets you create LVs whose _declared_ total size exceeds the physical space actually backing them, drawing from a shared **thin pool** rather than reserving dedicated space per LV up front.

```bash
# Create a 200G thin pool (the physically backed space)
lvcreate -L 200G -T data_vg/thin_pool

# Create three "thin" LVs, each declared at 100G — 300G declared against a 200G pool
lvcreate -V 100G -T data_vg/thin_pool -n thin_lv1
lvcreate -V 100G -T data_vg/thin_pool -n thin_lv2
lvcreate -V 100G -T data_vg/thin_pool -n thin_lv3
```

**Why this is useful:** provisioning decisions get made once at the pool level instead of per-LV, and individual LVs can be created at a "reasonable ceiling" size without immediately consuming that much real disk — data physically consumes pool space only as it's actually written, similar in spirit to how a snapshot only consumes space for changed blocks.

**Why this is risky:** the pool can be **overcommitted** — if the sum of actual data written across all thin LVs approaches the pool's real physical size, the pool fills up regardless of what any individual LV's declared size claims, and a full thin pool causes write failures across every thin LV drawing from it, not just the one that happened to trigger the exhaustion.

```bash
# Monitor thin pool usage — Data% and Meta% are the numbers that matter
lvs -o+data_percent,metadata_percent data_vg/thin_pool
```

> ⚠️ **Warning:** Monitoring thin pool usage is a real, ongoing operational responsibility, not a set-and-forget configuration choice — an overcommitted pool that quietly crosses 100% actual usage doesn't just affect the LV that pushed it over; it can cause write failures across every thin LV sharing that pool simultaneously. Automated alerting on pool usage thresholds (commonly 80%, 90%) belongs in the same monitoring baseline as disk-usage alerting on plain filesystems (§80s, Part 11) — treating thin pool capacity as "just LVM configuration, set once" is how thin-provisioned environments end up with a fleet-wide outage instead of one host running out of disk.

## 6. Common Misconceptions

1. **"Extending the LV automatically extends the filesystem."** It doesn't — `lvextend` grows the block device; `resize2fs`/`xfs_growfs` (2) is a separate required step unless the `-r` shortcut is used.
2. **"Shrinking works the same way for ext4 and XFS."** It doesn't — ext4 supports shrinking (with the strict filesystem-first order in 3), XFS supports growing only, with no shrink path at all short of backup/recreate/restore.
3. **"A snapshot is a full copy of the origin LV."** It's copy-on-write — the snapshot stores only pre-change copies of blocks the origin has since overwritten, which is why its allocated space can be much smaller than the origin, and why that space can also run out (4).
4. **"Thin provisioning means storage is free until you need it."** It means storage accounting is deferred, not eliminated — the physical pool still has a real, finite size, and overcommitment risk (5) is the direct cost of that deferral if usage isn't actively monitored.

## 7. Tiered Interview Questions

**🎯 Beginner:** _"You just ran `lvextend` to grow a volume. The `df` output still shows the old size. Why?"_
**Model answer:** `lvextend` only grows the logical volume — the block device itself. The filesystem sitting on top of it (ext4 or XFS) doesn't automatically know its container got bigger; it still reports its previous size until its own resize tool runs — `resize2fs` for ext4 (against the device path) or `xfs_growfs` for XFS (against the mount point). `lvextend -r` combines both steps in one command if that's preferred.
_What the interviewer is probing for:_ Whether the candidate treats LV size and filesystem size as the two distinct layers they are, rather than assuming one resize handles both.

**🎯 Intermediate:** _"How does an LVM snapshot actually work under the hood, and what happens if you let it run for a long time without checking on it?"_
**Model answer:** It's copy-on-write — the snapshot doesn't copy the origin's data up front, it only saves the pre-change version of a block right before the origin overwrites it, reconstructing the point-in-time view by combining unchanged origin blocks with those saved copies. That means the snapshot needs its own allocated space, and the more the origin changes after the snapshot is taken, the more of that space gets consumed. If it fills up completely before being removed, the snapshot becomes invalid and unusable — it can no longer track further origin changes. That's why snapshots are meant to be short-lived, bounded-purpose tools (a backup window, a risky-change rollback window), not long-running substitutes for real backups.
_What the interviewer is probing for:_ Understanding CoW mechanics specifically, not just "a snapshot is a copy," and knowing the exhaustion failure mode.

**🎯 Senior:** _"A teammate wants to shrink an ext4-backed LV to reclaim space for another volume. What's the correct procedure, and what happens if they get the order wrong?"_
**Model answer:** Unmount the filesystem first — ext4 shrink isn't a safe online operation. Run `e2fsck -f` to check it, since `resize2fs` requires a clean filesystem before a shrink. Shrink the filesystem itself to the target size with `resize2fs`, and only after that succeeds, shrink the LV to match with `lvreduce`. If the order is reversed — shrinking the LV first — the filesystem's metadata and data blocks that fall outside the LV's new, smaller boundary are simply gone from the block device's perspective, with no warning at the time it happens; that's straightforward, often unrecoverable data loss, not a recoverable error state. I'd also flag that if this were XFS instead of ext4, none of this procedure applies — XFS can't shrink at all, and the only path is backup, recreate smaller, restore.
_What the interviewer is probing for:_ Correct, specific ordering (not just "shrink carefully"), and awareness that the whole procedure is ext4-specific and doesn't transfer to XFS.

**🎯 Architect:** _"You're designing a thin-provisioned storage tier for a multi-tenant platform. What operational controls do you put in place before turning it on?"_
**Model answer:** Thin provisioning is genuinely useful here — it lets each tenant get a generous declared quota without pre-reserving that much physical disk per tenant — but the overcommitment risk means a single shared pool filling up can cause write failures across every tenant on it simultaneously, which is a much worse blast radius than one tenant running out of space on a dedicated volume. Before enabling it I'd put automated pool-usage monitoring and alerting in place at conservative thresholds (well before 100%, since remediation — adding physical capacity to the pool, or migrating tenants off it — isn't instantaneous), establish a policy for how declared-vs-actual overcommit ratio is capped rather than left unbounded, and make sure whoever's on call understands that a thin pool alert is a "the shared foundation is at risk" severity, not a per-tenant nuisance. I'd pair this with the same discipline the snapshot exhaustion warning implies — anything that can silently run out of backing space needs monitoring baked in from day one, not added reactively after the first incident.
_What the interviewer is probing for:_ Recognizing that thin provisioning's risk is a shared-blast-radius problem, and designing proactive monitoring/policy rather than treating it as a purely technical LVM feature to just enable.

## 8. Key Takeaways

- Growing an LV (`lvextend`) is safe and online; growing the filesystem on top of it (`resize2fs` for ext4, `xfs_growfs` for XFS) is a separate required step, or use `lvextend -r` to combine both.
- Shrinking must go filesystem-first, then LV — reversing the order destroys data that falls outside the LV's new boundary; XFS cannot shrink at all under any procedure.
- LVM snapshots are copy-on-write, need their own allocated space for changed-block copies, and become invalid if that space is exhausted before the snapshot is removed — they're a short-lived tool for backups or risky-change rollback, not a long-term backup substitute.
- Thin provisioning allocates declared LV sizes larger than physically backed pool space, trading up-front reservation for real overcommitment risk that requires active pool-usage monitoring as an ongoing operational responsibility.

## 9. Related Concepts & What's Next

This section builds directly on §73's PV/VG/LV model — every operation here (`lvextend`, `lvcreate -s`, thin pools) is a Logical Volume operation, unchanged at the PV/VG layer. It anticipates §76's filesystem-creation-and-repair depth, particularly the XFS-can't-shrink limitation, which §76 reinforces from the creation and repair angle rather than the resizing angle covered here. §18 (Part 3) remains the reference for filesystem type characteristics generally. §75 shifts to RAID and `mdadm` — a related but distinct storage-resilience mechanism that, unlike LVM, is specifically about surviving a disk failure rather than flexible allocation.

**Next Section:** §75 — `Section-75-Part10-RAID-Concepts-Mdadm.md`
