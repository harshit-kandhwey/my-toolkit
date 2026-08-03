# Section 22 (Part 3): File Metadata: Timestamps, Ownership, and Attributes

## 1. The Three Timestamps: mtime, ctime, atime

§19 listed timestamps as one of the fields an inode stores, and flagged that full detail was coming here. Every regular file, directory, and symlink carries three distinct timestamps in its inode — not one "last modified" value, but three, each answering a different question:

| Timestamp | Full name         | What actually changes it                                                                                                                                                                        |
| --------- | ----------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **mtime** | Modification time | The file's **content** (data blocks) was written — `echo` appended, a text editor saved, a process wrote new bytes                                                                              |
| **ctime** | Change time       | The inode's **metadata** was changed — permissions (`chmod`), ownership (`chown`), link count, or the file's content (since a content write also updates the inode's size/block-pointer fields) |
| **atime** | Access time       | The file's content was **read** — `cat`, a text editor opening it, a process reading its bytes                                                                                                  |

The relationship is asymmetric and worth internalizing precisely: **every mtime-triggering event also triggers ctime** (writing content changes the inode too), but **not every ctime-triggering event touches mtime** — running `chmod 600 file` changes ctime alone, because permissions are inode metadata but the file's actual bytes never moved. atime is independent of both — reading a file changes neither its content nor its permissions, only the fact that it was read.

> ⚠️ **Warning:** ctime is **not** creation time, despite what the "c" strongly suggests to almost everyone the first time they encounter it. It stands for **change** time — the last time the inode's metadata changed — and it updates on `chmod`, `chown`, renames, and content writes alike. This is the single most common misconception about Linux timestamps, and it trips up people writing backup scripts, forensic timelines, and log-retention logic who assume `ctime` answers "when was this file made."

## 2. Is There a True Creation Timestamp?

Traditional Unix inode structures — the model ext2/ext3/ext4 inherited — have **no field for creation time at all**. Only mtime, ctime, and atime exist. If you need "when was this file first created," the honest traditional answer is: **you can't reliably get it** from the filesystem alone; the closest proxy is often a ctime from before any content or metadata was ever modified, which is fragile and easily invalidated by a single later `chmod`.

Some modern filesystems (ext4 with the right feature flags, XFS, Btrfs) do store a fourth timestamp — commonly called **birth time** (`crtime`) — and `stat`'s output includes a `Birth:` line when the underlying filesystem and `stat` version support it, as the `stat` walkthrough below shows. But it is not universal, not exposed by all tools consistently, and not something to assume is present without checking on the specific filesystem in front of you.

> 💡 **Tip:** If an audit or compliance requirement genuinely needs "when was this file created" as an immutable fact, don't rely on filesystem birth time alone — it can still be altered by certain low-level tools, isn't preserved across all copy/backup operations, and isn't universally supported. An application-level creation record (a database row, a signed manifest) is the reliable answer; filesystem metadata is a convenience, not a guarantee.

## 3. `stat`: Reading All Three Timestamps at Once

§19's introduction of `stat` already showed the three timestamp lines in passing — this section is the deliberate walkthrough.

**Syntax:**

```bash
stat [FILE]...
```

**Example usage and expected output:**

```bash
$ stat notes.txt
  File: notes.txt
  Size: 512             Blocks: 8          IO Block: 4096   regular file
Device: 259,2   Inode: 145002      Links: 1
Access: (0644/-rw-r--r--)  Uid: ( 1000/  harsh)   Gid: ( 1000/  harsh)
Access: 2026-07-26 08:41:03.221000000 +0000
Modify: 2026-07-25 22:10:47.000000000 +0000
Change: 2026-07-25 22:10:47.000000000 +0000
 Birth: 2026-07-20 09:00:00.000000000 +0000
```

Read the three lines deliberately, matching them against the three-timestamps overview above: **Access** is atime, **Modify** is mtime, **Change** is ctime. In this example, Modify and Change are identical because the last thing that touched this file was a content write (which bumps both together) — no separate permission or ownership change has happened since.

**Getting a single timestamp field programmatically** (useful in scripts, where parsing the full block is wasteful):

```bash
$ stat -c '%X %Y %Z' notes.txt
1753515663 1753481447 1753481447
```

`%X`/`%Y`/`%Z` (GNU `stat` format specifiers) print atime/mtime/ctime respectively as Unix epoch seconds — `%x`/`%y`/`%z` (lowercase) print the human-readable form instead.

**Common errors:**

- Assuming `%Z` in `stat -c` means "compressed size" or some size-related field by analogy with other tools — in `stat`'s format-specifier vocabulary it is ctime, not related to size at all.
- Trusting atime precision for auditing "who read this file and when" without first checking mount options, covered next — atime updates are frequently disabled or coarsened in production for performance reasons, silently breaking that assumption.

## 4. `noatime` / `relatime`: Why atime Often Isn't What You Expect

§20 covered mount options in `/etc/fstab`; this is the direct tie-back for timestamps specifically. Updating atime on every single read sounds cheap but isn't: a filesystem that honors strict atime semantics (`strictatime`) has to perform a **metadata write on every read**, even for a file nobody actually modified — on a busy host serving heavy read traffic, that turns every read into a read-plus-write, a real and measurable I/O cost for information almost nobody uses.

Two mount options address this, and knowing which one is active on a given filesystem explains a lot of "why doesn't this file's atime look right" confusion:

- **`noatime`** — atime updates are disabled entirely for that mount. Reads never touch the inode's atime field at all. Maximizes I/O savings; the trade-off is that nothing relying on genuine last-read tracking (some mail systems, some cache-eviction tools, some intrusion-detection heuristics) works correctly.
- **`relatime`** — the modern default on most distributions — updates atime only when the existing atime is **older than the current mtime or ctime**, or when it's been longer than roughly a day since the last atime update. This preserves the one thing most tooling actually needs atime for ("has this file been read since it was last modified") while eliminating the write-on-every-read cost for files that are read repeatedly without changing.

> ⚠️ **Warning:** Don't assume atime reflects "the last time anyone opened this file" in a modern production environment without first checking the mount option (`mount | grep <mountpoint>` or the relevant `/etc/fstab` line). Under `relatime` (the common default) or `noatime`, atime can be stale by design — this is a routine source of wrong conclusions during forensic or access-audit work if the mount behavior isn't checked first.

## 5. Manipulating Timestamps with `touch`

**Purpose:** Create an empty file if it doesn't exist, or — more relevant to this section — explicitly set a file's mtime/atime to a specific value, independent of what actually happened to the file's content.

**Syntax:**

```bash
touch [OPTIONS] FILE...
```

**Key flags:**

| Flag         | Meaning                                                                                             |
| ------------ | --------------------------------------------------------------------------------------------------- |
| (no flags)   | Create the file if missing; if it exists, set both mtime and atime to the current time              |
| `-t STAMP`   | Set mtime/atime to an explicit timestamp (`[[CC]YY]MMDDhhmm[.ss]` format) instead of "now"          |
| `-d STRING`  | Set mtime/atime using a flexible, human-readable date string (`"2 days ago"`, `"2026-01-01 12:00"`) |
| `-r REFFILE` | Use another file's timestamps as the source, instead of specifying one manually                     |
| `-m`         | Change only mtime, leave atime untouched                                                            |
| `-a`         | Change only atime, leave mtime untouched                                                            |
| `-c`         | Don't create the file if it doesn't exist (suppresses the default create-on-missing behavior)       |

**Example usage and expected output:**

```bash
$ touch -t 202601150930 report.log
$ stat -c '%y' report.log
2026-01-15 09:30:00.000000000 +0000

$ touch -r golden.conf staged.conf   # copy golden.conf's timestamps onto staged.conf
```

**Production usage example:** Build and deployment tooling frequently uses `touch -r` or `-t` deliberately — a build system re-touching an output file's mtime to match its source can force (or suppress) `make`-style dependency graphs from re-triggering downstream steps; a deployment script normalizing timestamps across a batch of files makes `rsync --checksum`-independent diffing tools compare cleanly. Note that `touch` **never changes ctime directly** to an arbitrary value — ctime always reflects "when the inode metadata last changed," and calling `touch` is itself a metadata change, so ctime jumps to the current real time as a side effect, even though mtime/atime were set to whatever you specified. This is a frequent surprise: you can fake mtime and atime, but you cannot fake ctime through ordinary tools, which is exactly why ctime is more trustworthy for tamper-detection purposes, as the extended attributes section below revisits.

## 6. Ownership Metadata: uid/gid at the Inode Level

§19 listed ownership among the fields an inode stores, alongside permissions. At the metadata level, ownership is simply two integers stored directly in the inode: a **UID** (owning user ID) and a **GID** (owning group ID) — the human-readable names `stat` prints (`Uid: (1000/ harsh)`) are a lookup against `/etc/passwd`/`/etc/group` performed for display purposes, not something stored in the inode itself. If those name mappings are ever missing (a user deleted, an NFS mount with no matching local account), `stat`/`ls -l` fall back to printing the bare numeric UID/GID, which is a useful diagnostic signal on its own — a numeric-only owner column usually means "this file's owning account no longer resolves on this host."

This section deliberately stops at that metadata-level fact. The full ownership and permission model — the `rwx` bits, `chmod`/`chown`/`chgrp`, SUID/SGID/sticky bit, umask, and ACLs — is **Part 4, §25–§32**, and isn't duplicated here; treat this as just enough to know that ownership lives in the same inode structure as the timestamps covered above, updates ctime like any other metadata change per the three-timestamps overview earlier, and is looked up by name only for display.

## 7. Extended Attributes: Metadata Beyond the Standard Inode Fields

Beyond the fixed set of fields every inode carries (type, permissions, uid/gid, size, timestamps, link count, data pointers), Linux filesystems that support **extended attributes** (xattrs) allow arbitrary additional name/value metadata to be attached to a file — a mechanism several higher-level features are built on top of:

- **SELinux security labels** (Part 12, §91) are stored as an xattr (`security.selinux`) — the mandatory-access-control decision for a file rides on metadata, not on the standard permission bits.
- **POSIX ACLs** (§30, Part 4) are implemented as xattrs (`system.posix_acl_access`/`_default`) under the hood.
- **User-defined attributes** (`user.*` namespace) can hold arbitrary application metadata — a checksum, a source URL, a classification tag — without needing a separate sidecar file or database row.

**Inspecting and setting xattrs directly:**

```bash
$ setfattr -n user.comment -v "reviewed 2026-07-20" report.log
$ getfattr -n user.comment report.log
# file: report.log
user.comment="reviewed 2026-07-20"
```

Most day-to-day administration never touches xattrs directly — they matter here primarily as the mechanism underneath `chattr`, covered next, and as context for why `cp`/`tar`/`rsync` sometimes need explicit flags (`--xattrs`, `-X`) to preserve this metadata across a copy; a naive copy tool that only handles the standard inode fields silently drops xattrs, which is a real, easy-to-miss data-loss mode when migrating files between hosts or filesystems that both support them.

## 8. `chattr` / `lsattr`: File Attributes Beyond Permissions

`chattr` and `lsattr` operate on a different layer than everything above — a small set of **filesystem-level attribute flags**, stored inline in the inode on ext-family filesystems (with partial support on others), that constrain what can be done to a file at a level **even root's normal permission checks don't override**. This is the key distinguishing fact: standard `rwx` permissions (Part 4) govern who can read/write/execute a file, but `chattr` flags govern what operations are possible **at all**, regardless of who's asking — including root, unless root first removes the flag.

### 8.1 `lsattr` — List Attributes

**Purpose:** Show the current attribute flags set on a file.

**Syntax:**

```bash
lsattr [FILE]...
```

**Example usage and expected output:**

```bash
$ lsattr /etc/important.conf
----i---------e------- /etc/important.conf
```

Each position corresponds to a specific flag; a `-` means that flag isn't set. Above, `i` (immutable) is set; the trailing `e` is a normal, unremarkable flag most modern ext4 files carry (extent-mapped storage) and isn't something you typically manage yourself.

### 8.2 `chattr` — Change Attributes

**Syntax:**

```bash
chattr [+-=]ATTRIBUTE FILE...
```

**Key flags (the two that matter operationally):**

| Attribute          | Meaning                                                                                                                                                                           |
| ------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `+i` (immutable)   | File **cannot** be modified, deleted, renamed, or hard-linked to — not by its owner, not by root — until the flag is removed                                                      |
| `+a` (append-only) | File can be **opened for writing only in append mode** — existing content cannot be altered or truncated, and the file cannot be deleted or renamed, but new data can be appended |

**Example usage:**

```bash
# Protect a critical config file from any modification, including accidental root edits
$ chattr +i /etc/important.conf
$ rm /etc/important.conf
rm: cannot remove '/etc/important.conf': Operation not permitted
$ echo "x" >> /etc/important.conf
bash: /etc/important.conf: Operation not permitted

# Make a log file append-only — new entries are fine, tampering with history is not
$ chattr +a /var/log/audit/audit.log
$ echo "fake entry" > /var/log/audit/audit.log
bash: /var/log/audit/audit.log: Operation not permitted
$ echo "fake entry" >> /var/log/audit/audit.log     # succeeds — append is allowed
```

**Removing a flag** uses `-` in place of `+`, and requires the same elevated capability that setting it did:

```bash
$ chattr -i /etc/important.conf
```

**Production usage example — why this matters operationally, not just academically:** `+i` and `+a` are two of the few mechanisms on a stock Linux host that constrain **root itself**, which is exactly what makes them valuable for a specific, narrow threat model: protecting against accidental damage (a fat-fingered `rm -rf` or a bad config-management run overwriting a file it shouldn't) and against a specific class of attacker — one who has gained root but not the ability to unset `chattr` flags (which typically requires the `CAP_LINUX_IMMUTABLE` capability, and can be further constrained via kernel securelevel/lockdown mechanisms in a hardened setup). `+a` on audit and authentication log files (`/var/log/audit/`, `/var/log/auth.log`) is a concrete, common hardening pattern: it means an intruder who compromises a service and gains root cannot simply truncate or edit the log to erase evidence of what they did — they can still append fake noise, but they cannot delete or rewrite the true history, which materially raises the bar for covering tracks. §91 (Part 12) covers this as part of broader kernel and audit-log hardening; this section is the mechanical `chattr`/`lsattr` foundation that hardening builds on.

> 💡 **Tip:** `+i` is also a useful, low-ceremony safeguard for things that have nothing to do with security — a golden reference file, a critical cron script, a Terraform state backup you never want silently overwritten by a bad automation run. Setting it costs nothing and fails loudly (a clear "Operation not permitted") the moment something tries to touch the file unexpectedly, which is often a faster signal than discovering the damage after the fact.

> ⚠️ **Warning:** `chattr +i`/`+a` are filesystem-level flags with only partial and inconsistent support outside ext2/ext3/ext4 — behavior on XFS, Btrfs, and especially network filesystems (NFS) varies and shouldn't be assumed without checking. They also don't survive being copied to a filesystem or tool that doesn't understand them (a plain `cp` to a non-ext filesystem, or an archive/restore path that doesn't preserve extended flags, silently drops the protection) — verify with `lsattr` after any copy or restore where this matters, don't assume it carried over.

## 9. Common Misconceptions

1. **"ctime is creation time."** Covered in depth in the timestamps sections above, but worth restating as the single highest-value correction in this section: ctime is inode **change** time, updated by permission changes, ownership changes, renames, and content writes alike — not a creation timestamp. Traditional Unix inodes have no creation-time field at all; `Birth:`/`crtime` exists only on some modern filesystems and isn't universal.
2. **"atime always tells you the last time a file was actually read."** Only true under strict atime semantics, which is rarely the active mount behavior in production — `relatime` (the common modern default) and `noatime` both mean atime can be stale by design, as the `noatime`/`relatime` section above covers. Always check the mount option before trusting atime for anything access-audit-related.
3. **"`touch -t` can fake any timestamp, including ctime."** `touch` can set mtime and atime to arbitrary values, but calling `touch` is itself a metadata change, so ctime always jumps to the real current time as a side effect — you cannot backdate ctime through ordinary tools, which is exactly what makes it more trustworthy than mtime for tamper-evidence purposes, as the `touch` and `chattr` sections above cover.
4. **"chmod/chown-level permissions are enough to protect a critical file from accidental or malicious modification."** Standard permissions (Part 4) only constrain who is allowed to act on a file — root and, depending on setup, the file's owner can always modify or delete it regardless of `rwx` bits. `chattr +i`/`+a` operate at a layer standard permissions don't reach, which is precisely why they're the mechanism reached for when the threat model includes "even a compromised root" or "even an operator mistake," as the `chattr` section above covers.

## 10. Tiered Interview Questions

**🎯 Beginner:** _"What are the three timestamps stored in a Linux file's inode, and what triggers each one?"_
**Model answer:** mtime (modification time) changes when the file's content is written. ctime (change time) changes when the inode's metadata changes — permissions, ownership, link count, or content (since a content write also updates inode fields like size). atime (access time) changes when the file's content is read. Every mtime-triggering event also touches ctime, but ctime can change without mtime changing at all — for example, running `chmod` changes only ctime, because the file's actual data never moved.
_What the interviewer is probing for:_ Whether the candidate can name all three and correctly state the mtime/ctime relationship, not just recite "modify, change, access" as three unrelated labels.

**🎯 Intermediate:** _"Why does ctime specifically not mean 'creation time,' and how would you actually determine when a file was created?"_
**Model answer:** ctime stands for change time, not creation time — it's the last time the inode's metadata changed, and permission or ownership changes bump it just as content writes do, so it gets overwritten by routine administrative operations that have nothing to do with when the file was made. Traditional Unix inodes (ext2/ext3, and ext4 without the right feature flags) have no creation-time field at all. Some modern filesystems store an actual birth time (`crtime`), visible as `stat`'s `Birth:` line when supported, but it isn't universal and isn't guaranteed to survive every copy or backup path. If a real, tamper-resistant creation record is actually required — for compliance or forensics — I'd rely on an application-level record (a database insert timestamp, a signed manifest) rather than trusting filesystem metadata alone.
_What the interviewer is probing for:_ Correcting the "c is for creation" instinct with the right reasoning, and knowing the limits of filesystem-level metadata as a source of truth.

**🎯 Senior:** _"You need to protect `/etc/passwd`-adjacent config and audit logs from being tampered with, even by a process that has somehow gained root. What's your approach, and what are its limits?"_
**Model answer:** Standard permissions don't help here by definition — root bypasses `rwx` checks. I'd reach for `chattr`: `+i` (immutable) on static critical config files, so they can't be modified, deleted, or renamed until the flag is explicitly removed, and `+a` (append-only) on audit/auth logs, so new entries can still be written but existing history can't be truncated or rewritten — which specifically defeats a common track-covering move after a compromise. The limits matter, though: removing these flags typically only requires the `CAP_LINUX_IMMUTABLE` capability, which a full root compromise likely still has unless it's been further restricted via kernel lockdown/securelevel mechanisms — so this raises the bar rather than making tampering impossible. It's also ext-family-specific with inconsistent support elsewhere, doesn't survive copies to tools/filesystems that don't preserve the flag, and needs `lsattr` verification after any restore. I'd treat it as one layer in defense-in-depth — alongside centralized/remote log shipping so a local copy being protected isn't the only copy that exists — not a standalone guarantee.
_What the interviewer is probing for:_ Knowing chattr goes beyond standard permissions specifically because it constrains root, while also being honest about its actual limits rather than presenting it as bulletproof.

**🎯 Architect:** _"Design a strategy for a fleet where you need confidence that critical config files haven't been silently modified outside of your configuration-management pipeline."_
**Model answer:** I'd combine several layers rather than relying on any single metadata field. First, ctime is the most reliable _local_ tamper signal for "did anything about this file's metadata or content change," since — unlike mtime/atime — it can't be arbitrarily backdated through normal tools like `touch`; a file-integrity-monitoring pass comparing current ctime (and a content hash) against a known-good baseline is a reasonable detection layer. Second, for files where the requirement is prevention, not just detection, `chattr +i` (immutable) is the right mechanical control specifically because it constrains even root, forcing any legitimate change — including from the config-management tool itself — to go through an explicit `chattr -i`/edit/`chattr +i` cycle that can be scripted and audited as part of the pipeline. Third, I'd not treat filesystem attributes as the whole story: SELinux/AppArmor labels (extended attributes, covered above) add mandatory access control on top, and centralized log shipping means an attacker tampering with a local append-only log still doesn't erase the copy that already left the host. Finally, I'd document that `chattr` protection is ext-family-specific and verify it's actually preserved across whatever backup/restore or image-baking process the fleet uses, since it's a common silent gap — a golden image built with a tool that doesn't preserve xattrs/chattr flags ships without the protection anyone assumed was there.
_What the interviewer is probing for:_ Layered thinking rather than a single silver-bullet answer, correct use of ctime's tamper-evidence property, and awareness that chattr protection can silently fail to propagate through image/backup pipelines if not explicitly verified.

## 11. Key Takeaways

- Every inode carries three distinct timestamps — mtime (content write), ctime (metadata change, including content writes), atime (content read) — and ctime is emphatically **not** creation time; traditional inodes have no creation-time field at all, and `Birth:`/`crtime` support is filesystem-dependent, not universal.
- `stat` is the tool for reading all three timestamps (and the rest of the inode's metadata) at once; `stat -c` format specifiers (`%X`/`%Y`/`%Z` vs. `%x`/`%y`/`%z`) extract them individually for scripting.
- `noatime`/`relatime` mount options (tied back to §20) mean atime often does not reflect true last-read time in production — verify the active mount option before trusting atime for any access-audit purpose.
- `touch` can set mtime/atime to arbitrary values, but cannot backdate ctime — calling `touch` is itself a metadata change that always advances ctime to the real current time, which is exactly why ctime is more trustworthy for tamper-evidence than mtime.
- Ownership (uid/gid) is stored as plain integers in the inode, resolved to names via `/etc/passwd`/`/etc/group` only for display; the full permission and ownership model is Part 4, §25–§32.
- Extended attributes (xattrs) let filesystems attach arbitrary metadata beyond the fixed inode fields, and are the mechanism underneath SELinux labels, POSIX ACLs, and `chattr` itself — and a common silent data-loss mode when a copy/backup tool doesn't preserve them.
- `chattr +i` (immutable) and `+a` (append-only) operate at a layer standard `rwx` permissions don't reach — they constrain even root — making them the right mechanism for protecting critical config from accidental damage and audit/log files from tampering by a compromised root process, with real limits (`CAP_LINUX_IMMUTABLE` can remove them, ext-family-specific, must be verified across copies) covered further in §91 (Part 12).

## 12. Related Concepts & What's Next

This section is the deferred detail promised by §19's inode field list, and depends directly on §20's mount-option coverage for the `noatime`/`relatime` timestamp behavior covered above. Ownership is introduced here only at the metadata-storage level — the full `rwx`/`chmod`/`chown`/ACL model is Part 4, §25–§32, and should be treated as this section's required follow-up before hands-on permission administration. The `chattr`/`lsattr` immutable and append-only attributes covered above are revisited with full hardening context in §91 (Part 12), particularly for protecting audit logs. §23 (next) moves to disk partitioning concepts — MBR vs. GPT and the `fdisk`/`parted`/`gdisk` tooling — a level below the filesystem entirely, addressing how a disk is divided before any filesystem or inode structure is created on it at all.

**Next Section:** §23 — `Section-23-Part3-Disk-Partitioning-Concepts.md`
