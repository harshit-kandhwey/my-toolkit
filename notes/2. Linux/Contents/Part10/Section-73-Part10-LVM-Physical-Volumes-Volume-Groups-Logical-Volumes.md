# Section 73 (Part 10): Logical Volume Manager (LVM): Physical Volumes, Volume Groups, Logical Volumes

## 1. Overview: Closing Part 9, Opening Part 10

Part 9 ([§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)–[§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md)) closed with [§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md)'s clock-accuracy foundation and handed off directly to Part 10 without any dependency between the two — this section is a genuine topic switch, from systemd/services administration into storage. [§23](../Part3/Section-23-Part3-Disk-Partitioning-Concepts.md) already covered disk partitioning with `fdisk`/`parted`/`gdisk`, and [§18](../Part3/Section-18-Part3-Filesystem-Types.md) covered filesystem types like ext4 and XFS. This section sits conceptually **between** those two: LVM is a layer that can exist on top of a partition and underneath a filesystem, and understanding why that extra layer exists — rather than just partitioning a disk and putting a filesystem directly on it — is this section's core question.

**The problem LVM solves:** a traditional partition is a fixed-size region of a fixed physical disk. If `/var` is on `/dev/sdb1` and that partition fills up, growing it means either resizing the partition in place (risky, and bounded by whatever unallocated space happens to be adjacent to it on that exact disk) or migrating the whole filesystem to a bigger disk. Storage decisions made at provisioning time — "how big should this partition be" — are notoriously hard to get right permanently, and traditional partitioning offers little room to be wrong.

LVM decouples **logical storage** (what a filesystem sees and is mounted from) from **physical storage** (actual disks and partitions), by inserting an abstraction layer with three components:

```text
Physical Disks/Partitions
        │
        ▼
Physical Volumes (PV)   ── pvcreate
        │
        ▼
Volume Group (VG)       ── vgcreate  (pools PVs together)
        │
        ▼
Logical Volumes (LV)    ── lvcreate  (carved out of VG space)
        │
        ▼
Filesystem (ext4/XFS, §18) ── mkfs, then mounted per §20
```

> 💡 **Tip:** Keep the direction of the abstraction straight: a Logical Volume doesn't have to correspond to any single physical disk or partition. A VG can pool space from three separate physical disks, and an LV carved from that VG can be grown later by pulling in more space from the VG — space that might come from a disk added to the VG long after the LV was first created. This is the entire value proposition in one sentence: **a filesystem's size is no longer bound by any single physical device's boundaries.**

## 2. Physical Volumes (PVs): The Foundation Layer

A **Physical Volume** is a physical disk, or more commonly a partition, that has been initialized for LVM use — LVM writes a small metadata header onto it identifying it as part of the LVM system.

```bash
# Initialize a partition (or whole disk) as a PV
pvcreate /dev/sdb1 /dev/sdc1
```

**Key points:**

- A PV is typically created on a partition rather than a raw disk ([§23](../Part3/Section-23-Part3-Disk-Partitioning-Concepts.md)'s partitioning still matters — LVM doesn't replace the decision of whether to partition, it usually sits on top of one partition per disk, often marked with partition type `8e` on MBR or the Linux LVM GUID on GPT).
- Multiple PVs can be created at once and later added to the same VG, which is exactly how a VG ends up spanning multiple physical disks.
- A PV can be removed from LVM use later with `pvremove`, but only after it's no longer part of any VG.

**Inspecting PVs:**

```bash
# Full detail per PV
pvdisplay

# One-line-per-PV summary — faster for a quick fleet check
pvs
```

```bash
$ pvs
  PV         VG      Fmt  Attr PSize   PFree
  /dev/sdb1  data_vg lvm2 a--  <100.00g <20.00g
  /dev/sdc1  data_vg lvm2 a--  <100.00g <100.00g
```

## 3. Volume Groups (VGs): The Pooling Layer

A **Volume Group** aggregates one or more PVs into a single pool of storage. The VG is where the "decoupling from physical boundaries" claim in 1 actually becomes true — once `/dev/sdb1` and `/dev/sdc1` are both in `data_vg`, LVM no longer cares which physical disk any given chunk of that pooled space physically lives on when allocating a new LV (barring deliberate striping/mirroring configuration, which is out of scope here).

```bash
# Create a VG from one or more PVs
vgcreate data_vg /dev/sdb1 /dev/sdc1

# Add another PV to an existing VG later — this is how a VG grows
vgextend data_vg /dev/sdd1
```

**Inspecting VGs:**

```bash
vgdisplay
vgs
```

```bash
$ vgs
  VG      #PV #LV #SN Attr   VSize   VFree
  data_vg   2   1   0 wz--n- 199.99g  20.00g
```

## 4. Extents: LVM's Allocation Unit

LVM doesn't allocate space byte-by-byte or even block-by-block the way a filesystem does internally — it allocates in fixed-size chunks called **extents**.

- A **Physical Extent (PE)** is the allocation unit within a PV/VG — default size is commonly 4 MiB, though it's configurable at `vgcreate` time with `-s`.
- A **Logical Extent (LE)** is the corresponding unit within an LV, and LEs map to PEs one-to-one (or more than one-to-one for mirrored/striped configurations, not covered here).
- Every LVM size operation — creating, growing, shrinking an LV — is really an operation in whole extents under the hood, even when the command line accepts a size like `10G`; LVM rounds to the nearest extent boundary.

Extents matter operationally because they explain why `vgs`/`pvs` free-space numbers are always extent-aligned, and why an LV's actual allocated size can differ very slightly from what was literally requested.

## 5. Logical Volumes (LVs): The Consumable Layer

A **Logical Volume** is what actually gets a filesystem put on it and gets mounted — from the perspective of `mkfs` and `mount` ([§18](../Part3/Section-18-Part3-Filesystem-Types.md), [§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md)), an LV looks exactly like a partition or whole disk block device.

```bash
# Create a 50G LV named "app_lv" from the data_vg pool
lvcreate -L 50G -n app_lv data_vg

# Alternative: allocate by percentage of the VG's free space instead of an absolute size
lvcreate -l 100%FREE -n app_lv data_vg
```

**Key flags:**

| Flag                | Meaning                                                |
| ------------------- | ------------------------------------------------------ |
| `-L <size>`         | Absolute size (e.g. `50G`, `500M`)                     |
| `-l <extents or %>` | Size in extents, or a percentage (`100%FREE`, `50%VG`) |
| `-n <name>`         | Logical volume name                                    |

**Inspecting LVs:**

```bash
lvdisplay
lvs
```

```bash
$ lvs
  LV      VG      Attr       LSize  Pool Origin Data%
  app_lv  data_vg -wi-ao---- 50.00g
```

**Device naming — two paths to the same device:**

Once created, an LV is addressable two equivalent ways:

```text
/dev/data_vg/app_lv        ← conventional VG-name/LV-name path
/dev/mapper/data_vg-app_lv ← device-mapper path (LVM is built on top of device-mapper)
```

Both refer to the same underlying block device — the first is a friendlier symlink, the second reflects that LVM is implemented as a device-mapper target. `/etc/fstab` entries ([§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md)) commonly reference the LV by UUID instead of either path, for the same reason UUID is generally preferred over device paths there — device paths aren't guaranteed stable across reboots or hardware changes, and this is exactly as true for LVM devices as for plain partitions.

## 6. Full Workflow: PV → VG → LV → Filesystem → Mount

```bash
# 1. Create the PV(s)
pvcreate /dev/sdb1 /dev/sdc1

# 2. Create the VG from those PVs
vgcreate data_vg /dev/sdb1 /dev/sdc1

# 3. Create the LV from the VG's pooled space
lvcreate -L 80G -n app_lv data_vg

# 4. Put a filesystem on the LV (§18 covers filesystem type choice in depth)
mkfs.ext4 /dev/data_vg/app_lv

# 5. Mount it (§20 covers /etc/fstab persistence)
mkdir -p /mnt/app_data
mount /dev/data_vg/app_lv /mnt/app_data
```

**Production usage example:** A common real-world pattern is provisioning a VM with several smaller virtual disks attached to one VG rather than one large disk, specifically so additional virtual disks can be attached later and folded into the same VG with `vgextend` — turning "the app ran out of disk space" from a downtime-causing migration into a same-day `vgextend` + `lvextend` ([§74](./Section-74-Part10-LVM-Resizing-Snapshots-Thin-Provisioning.md)) operation with no data movement required.

## 7. Common Misconceptions

1. **"LVM is only useful for adding new physical disks."** That's one benefit, but the extent-based allocation model (4) and the PV/VG/LV separation also enable snapshots and thin provisioning ([§74](./Section-74-Part10-LVM-Resizing-Snapshots-Thin-Provisioning.md)) — capabilities that have nothing to do with spanning multiple disks and exist purely because of the abstraction layer itself.
2. **"An LV always corresponds to a contiguous region of one physical disk."** Not necessarily — a VG can pool PVs from multiple physical disks, and LVM's default linear allocation can (though doesn't have to) spread an LV's extents across whichever PVs have free space, which is precisely why a single physical disk failing under a VG spanning multiple disks (without RAID, [§75](./Section-75-Part10-RAID-Concepts-Mdadm.md)) can corrupt every LV in that VG, not just data that was "on" the failed disk.
3. **"`/dev/vgname/lvname` and `/dev/mapper/vgname-lvname` are different devices."** They're two paths to the identical device-mapper block device (5) — neither is more "real" than the other.

## 8. Tiered Interview Questions

**🎯 Beginner:** _"What problem does LVM actually solve that plain disk partitioning doesn't?"_
**Model answer:** A plain partition is a fixed-size region of one physical disk — if it fills up, growing it is constrained by adjacent free space on that exact disk, or requires migrating to a new disk entirely. LVM inserts an abstraction layer — Physical Volumes pooled into a Volume Group, with Logical Volumes carved out of that pool — so a filesystem's size is decoupled from any single disk's physical boundaries. Growing storage becomes "add a disk, extend the VG, extend the LV" instead of "migrate everything to a bigger disk."
_What the interviewer is probing for:_ Understanding the abstraction's purpose, not just being able to recite `pvcreate`/`vgcreate`/`lvcreate` syntax.

**🎯 Intermediate:** _"Walk me through the three-layer LVM model and what each layer's command creates."_
**Model answer:** `pvcreate` initializes a disk or partition as a Physical Volume — writing LVM metadata that marks it as available for pooling. `vgcreate` (and later `vgextend`) pools one or more PVs into a Volume Group, a single logical pool of storage that can span multiple physical disks. `lvcreate` carves a Logical Volume of a requested size out of a VG's free space — and it's the LV, not the PV or VG, that gets a filesystem via `mkfs` and gets mounted. Underneath all of it, LVM allocates in fixed-size chunks called extents, not arbitrary byte ranges.
_What the interviewer is probing for:_ Clean layer-by-layer recall with the right command mapped to the right layer, plus knowing extents exist as the real allocation unit.

**🎯 Senior:** _"What's the trade-off of putting LVM under everything by default, versus using plain partitions?"_
**Model answer:** LVM buys real operational flexibility — online growth, snapshots, thin provisioning ([§74](./Section-74-Part10-LVM-Resizing-Snapshots-Thin-Provisioning.md)) — at the cost of a genuinely more complex recovery story. A corrupted partition table on a plain-partitioned disk is a well-understood, heavily-documented recovery scenario; corrupted or lost LVM metadata (the PV headers, VG configuration) can make an entire VG's worth of LVs unrecoverable even if the underlying disk sectors holding actual data are fine, and recovery tooling/expertise for LVM metadata corruption is a narrower skill than generic partition-table recovery. I wouldn't avoid LVM for that reason on hosts that actually need the flexibility, but I would back up LVM metadata (`vgcfgbackup`) as routine hygiene and wouldn't reach for LVM by default on a simple single-disk host with no expected growth or snapshot need, where a plain partition is genuinely simpler and has one less thing to go wrong.
_What the interviewer is probing for:_ Honesty about a real trade-off rather than treating LVM as a strictly-better default, and awareness of `vgcfgbackup` as a concrete mitigation.

**🎯 Architect:** _"You're designing a storage layout standard for a new fleet. When do you mandate LVM, and when do you explicitly avoid it?"_
**Model answer:** I'd mandate LVM on any host where storage needs are expected to grow unpredictably over the host's lifetime — database hosts, application servers with growing log/data volumes, anything where a same-day non-disruptive resize ([§74](./Section-74-Part10-LVM-Resizing-Snapshots-Thin-Provisioning.md)) matters more than minimizing moving parts. I'd also want it wherever the backup strategy ([§79](./Section-79-Part10-Backup-Strategies-Tools.md)) benefits from LVM snapshots as a consistent point-in-time source. I'd avoid mandating it on narrowly-scoped, short-lived, or genuinely fixed-size hosts — a stateless worker node with a known, static disk footprint gains little from the extra abstraction and inherits the metadata-recovery complexity noted above for no real benefit. Either way, the standard would include `vgcfgbackup` as a mandatory scheduled task wherever LVM is used, since metadata is the single point of failure the abstraction introduces that plain partitioning doesn't have.
_What the interviewer is probing for:_ Fleet-scale, workload-driven decision-making rather than a blanket "always use LVM" or "never use LVM" answer, and connecting the decision to concrete downstream sections (snapshots, backups).

## 9. Key Takeaways

- LVM's value is decoupling logical storage from physical disk boundaries via a three-layer model: Physical Volume → Volume Group → Logical Volume.
- `pvcreate` initializes a PV, `vgcreate`/`vgextend` pool PVs into a VG, `lvcreate` carves an LV from VG free space — `pvdisplay`/`vgdisplay`/`lvdisplay` give full detail, `pvs`/`vgs`/`lvs` give fast one-line summaries.
- Extents (default commonly 4 MiB) are LVM's real allocation unit — every size operation rounds to extent boundaries under the hood.
- `/dev/vgname/lvname` and `/dev/mapper/vgname-lvname` are two paths to the same device-mapper block device, not two different devices.
- LVM trades real operational flexibility for a genuinely harder recovery story if its metadata is lost or corrupted — `vgcfgbackup` is the standard mitigation, and LVM isn't a universally-correct default for every host.

## 10. Related Concepts & What's Next

This section depends on [§18](../Part3/Section-18-Part3-Filesystem-Types.md) (filesystem types, Part 3 — an LV still needs a filesystem put on it) and [§23](../Part3/Section-23-Part3-Disk-Partitioning-Concepts.md) (disk partitioning, Part 3 — a PV is typically created on a partition, not a raw disk). [§20](../Part3/Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md)'s mounting/`/etc/fstab` conventions apply identically to LVM devices. [§74](./Section-74-Part10-LVM-Resizing-Snapshots-Thin-Provisioning.md) builds directly on this section's PV/VG/LV model to cover resizing, snapshots, and thin provisioning — capabilities that only exist because of the abstraction layer introduced here.

**Next Section:** [§74](./Section-74-Part10-LVM-Resizing-Snapshots-Thin-Provisioning.md) — `Section-74-Part10-LVM-Resizing-Snapshots-Thin-Provisioning.md`
