# Section 75 (Part 10): RAID Concepts and mdadm (Software RAID)

## 1. Overview: A Different Problem Than LVM Solves

§73–§74 covered LVM — flexible allocation, online resizing, snapshots, thin provisioning. **RAID (Redundant Array of Independent Disks)** solves a related but distinct problem: **surviving the failure of one or more physical disks** without losing data or availability. LVM and RAID are not competitors and are frequently combined — a common production pattern is a `mdadm` RAID array providing fault tolerance, with LVM's PV/VG/LV layer built on top of the resulting RAID device for flexible allocation, snapshots, and resizing. Neither replaces the other; they operate at different layers of the same problem space.

> 💡 **Tip:** Keep RAID's actual job narrow in your head: it protects against **a disk failing**. It says nothing about protecting against a file being accidentally deleted, data being corrupted by a buggy application, ransomware encrypting everything in place, or the entire building housing the array burning down — all of those get faithfully replicated or mirrored across every disk in the array right along with the good data, precisely because RAID doesn't know the difference between good data and bad data, it just protects the bits from a specific hardware failure mode. This distinction is worth its own dedicated point later (4) because it's the single most consequential misconception around RAID in practice.

## 2. RAID Levels Relevant to Linux Administration

| Level   | Mechanism                                    | Fault Tolerance                                                          | Capacity Efficiency                                      | Performance                                                           | Minimum Disks |
| ------- | -------------------------------------------- | ------------------------------------------------------------------------ | -------------------------------------------------------- | --------------------------------------------------------------------- | ------------- |
| RAID 0  | Striping, no redundancy                      | None — any disk failing loses the whole array                            | 100% (full capacity of all disks usable)                 | Best (reads/writes spread across disks)                               | 2             |
| RAID 1  | Mirroring                                    | Survives loss of all but one disk in the mirror                          | 50% (with 2 disks) — usable capacity is one disk's worth | Good read performance, write performance roughly one disk's worth     | 2             |
| RAID 5  | Striping with single distributed parity      | Survives exactly 1 disk failure                                          | (n-1)/n — e.g. 75% usable with 4 disks                   | Good read; write performance reduced by parity calculation            | 3             |
| RAID 6  | Striping with dual distributed parity        | Survives exactly 2 simultaneous disk failures                            | (n-2)/n — e.g. 67% usable with 6 disks                   | Similar to RAID 5, slightly more write overhead for the second parity | 4             |
| RAID 10 | Striped mirrors (mirror pairs, then striped) | Survives multiple failures, as long as no mirror pair loses both members | 50%                                                      | Excellent — combines striping's speed with mirroring's redundancy     | 4             |

**Choosing between them in practice:**

- **RAID 0** — performance only, zero redundancy; appropriate only for genuinely disposable/reconstructible data (scratch space, cache) where losing everything is an acceptable, cheap-to-recover outcome.
- **RAID 1** — simplest redundancy story, good for small arrays (boot/OS disks) where capacity efficiency matters less than reliability and simplicity.
- **RAID 5** — was historically popular for capacity-efficient redundancy, but is increasingly disfavored on large modern disks because of rebuild risk (5) — a long rebuild window with no tolerance for a second failure.
- **RAID 6** — the more conservative modern choice over RAID 5 for the same use case, specifically because it tolerates a second failure, which matters more as individual disk sizes (and therefore rebuild times) grow.
- **RAID 10** — the preferred choice when performance and redundancy both matter and the capacity cost (50% usable) is acceptable — common for database storage.

## 3. Software RAID with `mdadm`

`mdadm` ("multiple disk admin") is the standard Linux tool for managing **software RAID** — RAID implemented by the kernel rather than by dedicated hardware RAID controller firmware.

**Creating an array:**

```bash
# Create a RAID 5 array from three disks, device name /dev/md0
mdadm --create /dev/md0 --level=5 --raid-devices=3 /dev/sdb /dev/sdc /dev/sdd
```

**Key flags:**

| Flag                 | Meaning                                                   |
| -------------------- | --------------------------------------------------------- |
| `--create <device>`  | Name for the new array device (conventionally `/dev/mdN`) |
| `--level=<N>`        | RAID level (0, 1, 5, 6, 10)                               |
| `--raid-devices=<N>` | Number of disks composing the array                       |

**Checking array status — two complementary tools:**

```bash
# Live, continuously-updated summary of every md array on the host
cat /proc/mdstat

# Full detail on one specific array
mdadm --detail /dev/md0
```

```bash
$ cat /proc/mdstat
Personalities : [raid6] [raid5] [raid4]
md0 : active raid5 sdd[2] sdc[1] sdb[0]
      209584128 blocks super 1.2 level 5, 512k chunk, algorithm 2 [3/3] [UUU]

$ mdadm --detail /dev/md0
/dev/md0:
        Version : 1.2
  Creation Time : Mon Jul 27 10:02:14 2026
     Raid Level : raid5
     Array Size : 209584128 (199.86 GiB 214.61 GB)
  Used Dev Size : 104792064 (99.93 GiB 107.30 GB)
   Raid Devices : 3
  Total Devices : 3
    Persistence : Superblock is persistent

          State : clean
 Active Devices : 3
Failed Devices : 0
  Spare Devices : 0

           Layout : left-symmetric
       Chunk Size : 512K

           Number   Major   Minor   RaidDevice State
              0       8       16        0      active sync   /dev/sdb
              1       8       32        1      active sync   /dev/sdc
              2       8       48        2      active sync   /dev/sdd
```

**Reading `/proc/mdstat`'s `[UUU]` notation:** each letter position corresponds to one disk in the array — `U` means that disk is Up/healthy, and an underscore (`_`) in its place means that disk is missing or failed. A degraded RAID 5 array with one failed disk out of three shows `[UU_]` (or similar depending on which disk failed) — a fast, glanceable way to spot a degraded array during routine checks without parsing the fuller `--detail` output.

## 4. RAID Is Not a Backup

This point deserves emphasis on its own, separate from the levels comparison above, because it's the misconception most likely to cause a genuinely bad day:

> ⚠️ **Warning:** RAID protects against exactly one failure category — a physical disk dying. It provides **zero** protection against: accidental deletion (`rm -rf` on the wrong directory replicates across every mirror/parity member instantly), data corruption (a buggy application writing garbage gets faithfully mirrored/striped just like good data), ransomware or malicious encryption (every disk in the array ends up encrypted together), or site-level loss (fire, flood, theft — RAID disks in the same chassis or same building share the same site risk). None of these are edge cases; they're the actual leading causes of real data loss in production, and RAID does nothing for any of them. A real backup strategy — separate media, ideally separate location, with retained point-in-time history (§79 covers this in full) — is not optional just because an array is redundant. Treat "we have RAID" and "we have backups" as two completely independent checkboxes, because they answer two completely different threat models.

## 5. Rebuilding After a Disk Failure

When a disk in a redundant array fails, the array continues operating in a **degraded** state — still serving reads/writes, but with no remaining redundancy margin (for RAID 5) or reduced margin (for RAID 6/10) until the failed disk is replaced and the array **rebuilds**.

```bash
# Mark a failed disk as failed (if mdadm hasn't already), then remove it
mdadm --manage /dev/md0 --fail /dev/sdc
mdadm --manage /dev/md0 --remove /dev/sdc

# Add the replacement disk — this triggers the rebuild automatically
mdadm --manage /dev/md0 --add /dev/sde

# Monitor rebuild progress
cat /proc/mdstat
```

During a rebuild, `/proc/mdstat` shows a progress percentage and estimated completion time alongside the array's degraded state.

> ⚠️ **Warning:** A rebuild is a real operational risk window, not just a background maintenance task to ignore — rebuilding a large RAID 5 array (especially with modern multi-terabyte disks) can take many hours, during which the array has **zero** remaining fault tolerance: a second disk failure during that window means total data loss for that array, because RAID 5 can only tolerate exactly one failed disk at a time. This risk scales directly with disk size (bigger disks take longer to rebuild) and is the single biggest practical argument for preferring RAID 6 or RAID 10 over RAID 5 on modern large-capacity disks — RAID 6's tolerance for a second simultaneous failure specifically covers the "another disk dies mid-rebuild" scenario that RAID 5 cannot survive. It's also a good argument for proactively replacing disks that show early warning signs (SMART errors, elevated reallocated-sector counts) before they fail outright, rather than waiting for an unplanned failure to trigger a rebuild under worse conditions.

## 6. Common Misconceptions

1. **"RAID means I don't need backups."** Directly addressed in 4 — RAID and backups protect against entirely different failure categories, and neither substitutes for the other.
2. **"RAID 5 is always a reasonable choice for redundancy."** It was a reasonable default when disks were smaller and rebuild windows were short — on modern large-capacity disks, the long rebuild time and zero fault-tolerance margin during that window (5) make RAID 6 or RAID 10 the more commonly recommended modern choice for anything where a second failure during rebuild would be costly.
3. **"A degraded array is functionally fine to leave as-is."** It's still serving data, but with reduced or zero redundancy margin — treating a degraded array as a low-priority fix rather than an urgent one is exactly how a second failure turns into total data loss.
4. **"Hardware RAID and software RAID (`mdadm`) are interchangeable in every way that matters."** Functionally similar from a redundancy standpoint, but they differ operationally — software RAID's array metadata and management live in the OS/kernel (visible and portable via tools like `mdadm --detail`, movable between machines by moving the disks), whereas hardware RAID controllers store configuration in controller firmware, which can create a dependency on that specific controller (or a compatible replacement) for future disk recovery — worth knowing when assessing an inherited fleet's DR posture.

## 7. Tiered Interview Questions

**🎯 Beginner:** _"What does RAID actually protect against, and what does it not protect against?"_
**Model answer:** RAID protects against a physical disk failing — depending on the level, the array keeps serving data (RAID 1/5/6/10) or loses everything (RAID 0) when one or more disks die. It provides no protection against accidental deletion, data corruption, ransomware, or losing the whole site — those all replicate or destroy data across every disk in the array just as faithfully as legitimate writes do, because RAID has no concept of "good" versus "bad" data, only "which physical disk is currently working." Real protection against those requires a separate backup strategy.
_What the interviewer is probing for:_ Whether "RAID is not a backup" is understood as a specific, reasoned distinction rather than a memorized slogan.

**🎯 Intermediate:** _"Compare RAID 5 and RAID 6, and explain when you'd choose one over the other."_
**Model answer:** Both use striping with parity for redundancy — RAID 5 uses single distributed parity and tolerates exactly one disk failure; RAID 6 uses dual distributed parity, needs one more disk minimum, has slightly more write overhead, and tolerates two simultaneous failures. The practical deciding factor is disk size and rebuild time: on modern large-capacity disks, rebuilding a failed RAID 5 array after a replacement can take many hours, during which there's zero remaining fault tolerance — a second failure during that window means total array loss. RAID 6 specifically covers that scenario by surviving a second failure even mid-rebuild, which is why it's increasingly preferred over RAID 5 for large arrays despite the extra disk and slight write-performance cost.
_What the interviewer is probing for:_ Connecting the capacity/performance trade-off to the rebuild-window risk, not just reciting the parity-count difference.

**🎯 Senior:** _"A RAID 5 array just lost a disk and is now rebuilding after you added a replacement. What are you watching for during that window, and why?"_
**Model answer:** The array is degraded with zero remaining fault tolerance until the rebuild finishes — a second disk failure during that window is total data loss for that array, so I'm watching `/proc/mdstat`'s rebuild progress and, more importantly, keeping an eye on the health (SMART status) of the remaining disks in the array, since a rebuild puts sustained heavy read load on every surviving disk, which is itself a known trigger for exposing a second, previously-marginal disk's latent failure. I'd also make sure there's a verified, current backup of whatever this array holds, precisely because "we have RAID" was never a substitute for that, and this is the exact window where the gap between the two would actually get tested. If this were a recurring pattern on large RAID 5 arrays, I'd push to migrate to RAID 6 or RAID 10 going forward rather than accepting this risk window as routine.
_What the interviewer is probing for:_ Operational awareness of the rebuild-window risk in real time, not just knowing it exists abstractly, plus tying it back to backup verification rather than treating RAID and backup as unrelated topics.

**🎯 Architect:** _"You're designing storage resilience for a fleet with a mix of database servers and stateless application servers. How does your RAID strategy differ between them, and how does it relate to your backup strategy?"_
**Model answer:** For database servers, where both performance and redundancy matter and downtime/data loss is costly, I'd lean toward RAID 10 — the striped-mirror combination handles the database's I/O pattern well and tolerates disk failures without the rebuild-window fragility of parity-based RAID. For stateless application servers with no meaningful local state, I might skip redundant local RAID entirely, or use RAID 0/1 depending on whether local disk performance matters at all versus just running on whatever's fastest and replaceable — the redundancy story for that data lives in the application's horizontal scaling, not the local disk. Across both categories, RAID choice is a separate decision from backup strategy (§79), not a substitute for it — every host, RAID or not, has a defined backup policy proportional to how costly its data would be to lose, because RAID's fault-tolerance model and backup's very-different threat model (accidental deletion, corruption, site loss) both need independent answers regardless of which RAID level, if any, sits underneath.
_What the interviewer is probing for:_ Workload-appropriate RAID-level selection reasoning, and explicit separation of RAID strategy from backup strategy as two independent, both-necessary decisions.

## 8. Key Takeaways

- RAID and LVM solve different, complementary problems — RAID for disk-failure fault tolerance, LVM for flexible allocation — and are commonly layered together (RAID underneath, LVM on top).
- RAID 0 (striping, no redundancy), RAID 1 (mirroring), RAID 5 (single parity), RAID 6 (dual parity), RAID 10 (striped mirrors) trade capacity efficiency, fault tolerance, and performance differently — see the comparison table (2) for the specifics.
- `mdadm --create` builds a software RAID array; `/proc/mdstat` gives a fast live status check (including the `[UUU]`-style health notation), `mdadm --detail` gives full detail.
- RAID is not a backup — it protects against a disk failing, not against deletion, corruption, ransomware, or site loss; both are independently necessary (4).
- A degraded array has reduced or zero fault-tolerance margin until it rebuilds, and the rebuild window itself carries real risk — a second failure during a long RAID 5 rebuild on large disks means total data loss, which is the main modern argument for RAID 6 or RAID 10 over RAID 5 (5).

## 9. Related Concepts & What's Next

This section relates to §73 (LVM, prior in this Part) as a complementary rather than competing technology — the two are frequently layered together in real deployments. It sets up §79 (backup strategies, later this Part), where the "RAID is not a backup" distinction from 4 gets its full counterpart treatment — what an actual backup strategy needs to look like precisely because RAID doesn't provide it. §76 (next) shifts to filesystem creation, checking, and repair — the layer that sits on top of whatever block device (plain disk, LVM LV, or `mdadm` RAID array) is presented to it, and is agnostic to which of those it's actually built on.

**Next Section:** §76 — `Section-76-Part10-Filesystem-Creation-Checking-Repair.md`
