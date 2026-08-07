# Section 19 (Part 3): Inodes, Hard Links, and Symbolic Links

## 1. What an Inode Actually Is

Every file on a Linux filesystem — ext4, XFS, and most others [§18](./Section-18-Part3-Filesystem-Types.md) covered — is really two separate pieces of information stored in two separate places: the file's **data** (the actual bytes) and the file's **metadata**, which lives in a fixed-size on-disk structure called an **inode** (index node). The critical fact that unlocks everything else in this section: **an inode does not store the filename.**

An inode stores:

- **File type** — regular file, directory, symlink, device node, socket, FIFO
- **Permissions** — the `rwx` bits for owner/group/other ([§28](../Part4/Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md), covers this model in depth)
- **Ownership** — owning UID and GID
- **Size** in bytes
- **Timestamps** — mtime (content modified), ctime (metadata/inode changed), atime (last accessed) — full detail in [§22](./Section-22-Part3-File-Metadata-Timestamps-Ownership-Attributes.md) later in this Part
- **Link count** — how many directory entries currently point at this inode, covered in the hard links section below
- **Pointers to the actual data blocks** on disk holding the file's contents (or, for a symlink, the target path string itself, as covered in the symbolic links section below)

What an inode explicitly does **not** store is the filename. The filename lives in the **directory entry** — a directory is itself just a special kind of file whose content is a table mapping names to inode numbers. Looking up `/etc/hosts` means: read the `/etc` directory's data, find the entry named `hosts`, get its inode number, then read that inode to find the actual data blocks. This separation — name-to-inode mapping in the directory, everything else in the inode — is the entire mechanism that makes hard links possible, as the hard links section below explains.

Every inode is identified by an **inode number**, unique within a single filesystem (not globally unique across the whole machine — a file on `/` and a file on a separate `/data` mount can share the same inode number without being related, because inode numbers are only meaningful relative to the filesystem that issued them).

> 💡 **Tip:** The mental model that resolves most confusion in this section: a filename is a _pointer_ to an inode, not a property _of_ the file. A file, structurally, is its inode plus its data blocks — names are just labels other things (directory entries) attach to that inode, and a single inode can have more than one label pointing at it.

## 2. Inspecting Inodes: `ls -i`, `stat`, and `df -i`

### 2.1 `ls -i` — Show Inode Numbers

**Purpose:** List files alongside the inode number each filename resolves to — the fastest way to check whether two different filenames are actually the same underlying file.

**Syntax:**

```bash
ls -i [FILE]...
```

**Example usage and expected output:**

```bash
$ ls -i /etc/hosts
131074 /etc/hosts
```

### 2.2 `stat` — Full Inode Metadata

**Purpose:** Print the complete metadata an inode holds — everything listed in the inode-contents overview above — in one command. This is the tool for actually inspecting what an inode contains, not just its number.

**Syntax:**

```bash
stat [FILE]...
```

**Example usage and expected output:**

```bash
$ stat /etc/hosts
  File: /etc/hosts
  Size: 220             Blocks: 8          IO Block: 4096   regular file
Device: 259,2   Inode: 131074      Links: 1
Access: (0644/-rw-r--r--)  Uid: (    0/    root)   Gid: (    0/    root)
Access: 2026-07-20 09:12:44.000000000 +0000
Modify: 2026-06-15 14:02:11.000000000 +0000
Change: 2026-06-15 14:02:11.000000000 +0000
 Birth: 2026-01-04 08:00:03.000000000 +0000
```

**Key fields to read deliberately:**

| Field                      | Meaning                                                                                                                                         |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------- |
| `Inode`                    | The inode number (matches `ls -i`)                                                                                                              |
| `Links`                    | The hard link count, covered in the hard links section below — how many directory entries point at this inode                                   |
| `Access`/`Modify`/`Change` | atime/mtime/ctime — three distinct timestamps, frequently confused ([§22](./Section-22-Part3-File-Metadata-Timestamps-Ownership-Attributes.md)) |
| `Device`                   | Identifies which filesystem/mount this inode belongs to — relevant because inode numbers are only unique per-filesystem                         |

**Production usage example:** During an incident where a process is writing to what looks like the wrong file (e.g., a log rotation gone wrong, or a deployment that swapped a config file), `stat`-ing both the path the process has open (via `/proc/<pid>/fd/`, [§24](./Section-24-Part3-Proc-Sys-Virtual-Filesystems.md)) and the path an admin expects, then comparing `Inode` and `Device` fields, definitively answers "are these actually the same file on disk" — filenames alone can't answer that when hard links or bind mounts are in play.

### 2.3 `df -i` — Inode Usage Per Filesystem

**Purpose:** Report inode consumption (used/free/percentage) per mounted filesystem, as opposed to plain `df` which reports **space** consumption. These are two entirely independent resources that can each run out on their own.

**Syntax:**

```bash
df -i [MOUNTPOINT]
```

**Example usage and expected output:**

```bash
$ df -i /var
Filesystem      Inodes  IUsed    IFree IUse% Mounted on
/dev/sda1      6553600 6553600      0  100% /var
```

**Production usage example — inode exhaustion is a real, distinct production failure mode.** A filesystem is created with a **fixed number of inodes** at format time (`mkfs`, [§75](../Part10/Section-75-Part10-RAID-Concepts-Mdadm.md) in Part 10) on traditional filesystems like ext4 — that count generally cannot be changed without reformatting. A host can therefore hit `ENOSPC` ("No space left on device") from application writes, package installs, or even SSH login (PAM needing to write session files) while `df -h` shows plenty of free **space**, because what actually ran out was the fixed inode pool — typically from a workload that creates enormous numbers of tiny files (a runaway session-cache directory, a mail queue, a build system leaving thousands of small artifacts, a misbehaving logger writing one file per event instead of appending). `df -i` is the diagnostic that catches this; `df -h` alone will not.

> ⚠️ **Warning:** "Disk full" errors are not always a disk-space problem. Always check `df -i` alongside `df -h` during a `No space left on device` incident — treating every such error as a space problem leads you to delete large files that free up plenty of space but zero inodes, while the actual fix is deleting large _quantities_ of small files (or, for XFS, considering that XFS allocates inodes dynamically and is far less prone to this specific failure mode than ext4's fixed-at-format-time allocation, per [§18](./Section-18-Part3-Filesystem-Types.md)'s filesystem comparison).

## 3. Hard Links: A Second Name for the Same Inode

A **hard link** is a second directory entry pointing at the exact same inode number as an existing file. It is not a copy, not a shortcut, and not a reference to another file — it is structurally indistinguishable from the "original" name, because there is no original: both names are equally valid, equally direct pointers to the same inode and the same data blocks.

**Creating one:**

```bash
ln existing_file new_hardlink
```

```bash
$ echo "content" > original.txt
$ ln original.txt hardlink.txt
$ ls -i original.txt hardlink.txt
131099 hardlink.txt   131099 original.txt
$ stat -c '%h' original.txt
2
```

Note the `Links` count (`%h` in `stat`'s format syntax) is now `2` — the inode knows how many names currently point at it. Editing `hardlink.txt` changes the content read via `original.txt` too, because they are the same file; there is nothing to "keep in sync," they were never two things.

**Deleting a file is really "remove one directory entry and decrement the link count."** `rm` does not delete an inode's data directly — it unlinks a name. The kernel only actually frees the inode and its data blocks once the link count reaches **zero and no process still has the file open** (a process holding an open file descriptor keeps the inode alive even after every name pointing at it is removed — this is the mechanism behind the classic "deleted log file still consuming disk space until the process holding it is restarted" incident).

**Hard link constraints — both are structural, not arbitrary policy:**

- **Cannot cross filesystems.** A hard link is a pointer to an inode number, and inode numbers are only meaningful within the filesystem that assigned them — `ln /mnt/diskA/file /mnt/diskB/link` fails with "Invalid cross-device link" because there is no inode `diskB` could point at that means the same thing on `diskA`. Symlinks don't have this restriction, as the symbolic links section below explains.
- **Cannot (normally) point to a directory.** Hard-linking directories is disallowed on virtually every Linux filesystem in practice, because it would let the directory tree contain cycles (a directory could become its own ancestor), which breaks the assumption that directory traversal always terminates — tools like `find`, backup utilities, and `du` all rely on the tree having no cycles. (The kernel does use directory hard links internally for `.` and `..`, but that's a controlled special case, not something available to `ln` for ordinary use.)

**Production usage example:** Backup tools like `rsync --link-dest` and utilities like `cp -al` exploit hard links to implement space-efficient incremental snapshots — each snapshot directory hard-links to files unchanged since the previous snapshot rather than copying them, so N nightly snapshots of a mostly-static filesystem cost roughly one full copy's worth of disk space, not N copies, while still presenting N independently browsable directory trees.

## 4. Symbolic Links: A File That Contains a Path

A **symbolic link** (symlink, or "soft link") is a fundamentally different mechanism: it is its own real file, with its own inode, whose data is simply the **text of a path string** pointing at another file or directory. Resolving a symlink means the kernel reads that path string and re-resolves the lookup starting from it — an indirection step, not a second name for the same inode.

**Creating one:**

```bash
ln -s target_path link_name
```

```bash
$ ln -s /etc/hosts hosts_link
$ ls -l hosts_link
lrwxrwxrwx 1 root root 10 Jul 26 09:00 hosts_link -> /etc/hosts
```

The leading `l` in `ls -l`'s permission column identifies it as a symlink, and the `-> /etc/hosts` shows the stored target path. Note the symlink's own size (10 bytes above) is the length of that path string — not the size of the target file.

**Symlinks vs. hard links — the practical differences that drive when to use which:**

| Property                            | Hard Link                                                                    | Symbolic Link                                                                  |
| ----------------------------------- | ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| What it stores                      | Nothing new — another directory entry for an existing inode                  | A path string, in its own inode                                                |
| Can cross filesystems/mounts        | No                                                                           | Yes                                                                            |
| Can point to a directory            | No (not for ordinary use)                                                    | Yes                                                                            |
| Behavior if target is deleted       | Not possible to "orphan" — the inode stays alive as long as any link remains | **Dangles** — the symlink file still exists, but resolving it fails (`ENOENT`) |
| Distinguishable from the "original" | No — structurally identical, no original/copy distinction                    | Yes — always visibly a pointer (`ls -l` shows `->`)                            |
| Absolute vs. relative target        | N/A                                                                          | Either — author's choice, with different portability trade-offs (below)        |

**Dangling symlinks** are a routine, expected state, not automatically an error — a symlink can point at a path that doesn't exist yet (or no longer exists), and the symlink itself continues to exist and list fine under `ls`; the failure only surfaces when something tries to actually open/read through it.

```bash
$ ln -s /does/not/exist danglink
$ ls -l danglink
lrwxrwxrwx 1 root root 15 Jul 26 09:05 danglink -> /does/not/exist
$ cat danglink
cat: danglink: No such file or directory
```

**Absolute vs. relative symlink targets** is a deliberate design choice with real operational consequences: an absolute-target symlink (`/opt/app/current -> /opt/app/releases/v3`) resolves correctly no matter what directory you're standing in when you access it, but breaks if the tree is ever relocated to a different absolute path (e.g., mounted somewhere else, or copied into a container image at a different root). A relative-target symlink (`current -> releases/v3`) survives being moved as a unit but only resolves correctly if accessed relative to its own directory — a relative symlink dereferenced from an unexpected working directory, or after being copied without its siblings, is a common source of "works on my machine" breakage. Release-management patterns (blue/green deploy directories, `current` pointing at a versioned release folder) almost always use relative targets specifically so the whole tree can be relocated intact.

> ⚠️ **Warning:** `rm` on a symlink removes the symlink itself, not the target it points to — but a trailing slash or careless use of `rm -r` on a symlink _to a directory_ can behave unexpectedly depending on shell/tool, and copying through a symlink (`cp` without `-P`/`--no-dereference`) by default follows it and copies the target's contents, not the link. Always verify with `ls -l` before scripting destructive operations anywhere a symlink might be involved.

## 5. Common Misconceptions

1. **"A hard link is like a shortcut, similar to a symlink."** They are not similar mechanisms — a hard link is a second name for the _same_ inode (no indirection, no target path, no way to tell which name is "the real one"), while a symlink is an independent file containing a path string that gets re-resolved on each access. Confusing the two leads to wrong assumptions about cross-filesystem behavior, dangling states, and what happens when the "original" is deleted.
2. **"Deleting a file frees its space immediately."** `rm` decrements a link count and removes one directory entry; the inode and its data blocks are only freed once the link count reaches zero _and_ no process still holds the file open. This is exactly why a deleted log file a running process still has open keeps consuming disk space until that process closes it or restarts (a routine incident-response gotcha, diagnosable via `lsof | grep deleted`).
3. **"Running out of disk space always means running out of bytes."** ext4-family filesystems allocate a fixed inode count at format time, entirely separate from space capacity — a filesystem can report abundant free space in `df -h` while `df -i` shows 100% inode usage, and writes will still fail with `ENOSPC`, as the `df -i` discussion above covers.
4. **"Symlinks are strictly worse/riskier than hard links, so prefer hard links when possible."** They solve different problems — symlinks are the only option across filesystems or to directories, and their explicit, visible indirection (`ls -l` always shows the target) is arguably safer than a hard link's silent, indistinguishable duplication of a name. Neither is categorically superior; the right choice depends on whether you need cross-filesystem/directory linking (symlink) or true single-inode identity (hard link).

## 6. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between a hard link and a symbolic link?"_
**Model answer:** A hard link is another directory entry pointing at the same inode as an existing file — there's no "original," both names are equally direct references to the same data, and editing through either name edits the same content. A symbolic link is a separate file with its own inode whose content is a path string pointing at another file; accessing it requires the kernel to resolve that path as an extra indirection step. Deleting the target breaks a symlink (it "dangles") but a hard link keeps the data alive as long as at least one name still points at its inode.
_What the interviewer is probing for:_ Whether the candidate understands these as structurally different mechanisms rather than two flavors of "shortcut."

**🎯 Intermediate:** _"Why can't you hard-link a file across two different mounted filesystems, but you can symlink across them?"_
**Model answer:** A hard link is literally a pointer to an inode number, and inode numbers are only assigned and meaningful within a single filesystem — filesystem B has no idea what inode number N on filesystem A refers to, so there's no way to create a valid cross-filesystem hard link; the kernel returns "Invalid cross-device link." A symlink doesn't reference an inode number at all — it just stores a path string as its own file content, and path resolution happily walks across mount points the same way any other path lookup does, so there's no equivalent restriction.
_What the interviewer is probing for:_ Understanding that the constraint is a direct structural consequence of what a hard link actually _is_ (an inode pointer), not an arbitrary limitation.

**🎯 Senior:** _"A host is throwing `No space left on device` errors, but `df -h` shows 40% free space. What's your diagnostic path?"_
**Model answer:** The first thing I check is `df -i` on the affected filesystem, since space exhaustion and inode exhaustion are independent resources and `ENOSPC` is the same error for both. If inodes are at or near 100%, I'm looking for a workload creating a very large number of small files — a runaway cache, session-file directory, mail queue, or a logging pattern writing one file per event. I'd hunt for the worst offender with something like `find <mount> -xdev -printf '%h\n' | sort | uniq -c | sort -rn | head` to find directories with abnormal file counts rather than guessing. If it turns out to actually be a deleted-but-still-open file holding space (a different but related "df -h lies" scenario), `lsof +L1` or checking `/proc/<pid>/fd` for processes with deleted files open is the follow-up. I wouldn't accept "df shows free space, so it's not a disk issue" at face value — that's exactly the assumption this failure mode breaks.
_What the interviewer is probing for:_ Recognizing that `df -h` looking fine doesn't clear the disk as a root cause, and having a concrete, ordered diagnostic sequence rather than a vague "check disk space" answer.

**🎯 Architect:** _"You're designing a release-deployment convention using a `current` symlink pointing at versioned release directories (`/opt/app/releases/v1`, `v2`, ...). What design decisions around the symlink itself do you need to get right, and why?"_
**Model answer:** First, relative vs. absolute target: I'd use a relative target (`current -> releases/v3`) rather than an absolute one, because the whole `/opt/app` tree needs to be relocatable as a unit — across hosts, into container images at different mount roots, or during disaster recovery restores to a different path — without every deploy having to rewrite the symlink. Second, atomicity: the cutover from one release to the next needs to replace the symlink with a single atomic `ln -sfn` (or equivalent rename-based swap), not a delete-then-recreate, so a process resolving `current` mid-deploy never sees a dangling or half-updated state — this leans on the fact that symlink replacement via rename is atomic at the filesystem level. Third, I'd make sure whatever process or service definition references `/opt/app/current/...` re-resolves the symlink on each access rather than caching a resolved absolute path or an open file descriptor from before the swap, since some daemons hold a directory handle across the switch and won't pick up the new release without a restart — that's an operational rollout detail, not a symlink limitation, but it has to be accounted for in the deployment runbook. Finally, I'd keep old release directories around (pruned on a retention policy) rather than deleting the previous version immediately, so rollback is just re-pointing the symlink rather than a redeploy.
_What the interviewer is probing for:_ Ability to apply inode/symlink mechanics to a real deployment-pattern design, including atomicity and relocatability concerns that a surface-level "symlinks point at files" understanding wouldn't surface.

## 7. Key Takeaways

- An inode stores a file's metadata (type, permissions, ownership, size, timestamps, link count, data-block pointers) but never the filename — names live only in directory entries mapping name → inode number.
- `ls -i` shows inode numbers, `stat` shows full inode metadata including the hard-link count, and `df -i` shows inode _capacity_ usage — a resource entirely independent of `df -h`'s space usage, and a real, distinct production failure mode (inode exhaustion) when a workload creates huge numbers of small files.
- A hard link (`ln`) is a second directory entry for the same inode — no original/copy distinction, cannot cross filesystems (inode numbers are per-filesystem), cannot target a directory (would create tree cycles), and the underlying data isn't freed until the link count hits zero and no process still has it open.
- A symbolic link (`ln -s`) is its own file containing a target path string, resolved via an extra indirection step on each access — it can cross filesystems, can target directories, but can dangle if the target is missing, and its absolute-vs-relative target choice has real operational consequences for relocatable trees like release-deployment directories.
- `rm` never directly frees inode data — it decrements a link count and removes a directory entry, which is the mechanism behind "deleted but still consuming space" files held open by a running process.

## 8. Related Concepts & What's Next

This section builds directly on [§18](./Section-18-Part3-Filesystem-Types.md)'s filesystem-type coverage — ext4's fixed-at-format-time inode allocation vs. XFS's more dynamic behavior, covered in the `df -i` discussion above, is a concrete consequence of the filesystem design choices [§18](./Section-18-Part3-Filesystem-Types.md) introduced. [§17](./Section-17-Part3-Filesystem-Hierarchy-Standard.md)'s FHS coverage is where these mechanics show up structurally in practice — `/proc` and `/dev` entries, and the pervasive use of symlinks throughout a standard Linux tree (e.g., `/etc/mtab`, `/sbin -> usr/sbin` conventions on some distros). [§20](./Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md) (next) moves to mounting and `/etc/fstab` — the layer that determines which filesystem (and therefore which independent inode namespace) a given path actually belongs to, which is the direct prerequisite for correctly reasoning about when hard links will and won't work across a real host's mount layout.

**Next Section:** [§20](./Section-20-Part3-Mounting-Unmounting-Fstab-Mount-Options.md) — `Section-20-Part3-Mounting-fstab.md`
