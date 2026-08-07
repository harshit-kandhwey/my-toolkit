# Section 27 (Part 4): Standard Permission Model (rwx, Owner/Group/Other)

## 1. The Three Permissions and the Three Identity Classes

Every file and directory on a Linux filesystem carries permission bits that answer two separate questions: **what actions are permitted** (read, write, execute), and **who they're permitted for** (owner, group, other). [§19](../Part3/Section-19-Part3-Inodes-Hard-Links-Symbolic-Links.md) already established that these bits live in the file's inode, not in the directory entry — `ls -l` and `stat` are both reading the same inode-stored data, just formatted differently.

The three permission types:

| Symbol | Name    | Meaning on a **file**                | Meaning on a **directory**                                             |
| ------ | ------- | ------------------------------------ | ---------------------------------------------------------------------- |
| `r`    | Read    | Can view the file's contents         | Can list the directory's contents (`ls`)                               |
| `w`    | Write   | Can modify the file's contents       | Can create, delete, or rename entries **within** the directory         |
| `x`    | Execute | Can run the file as a program/script | Can **traverse** into the directory (enter it, access entries by name) |

The three identity classes a permission set can apply to, always in this fixed order:

| Class | Symbol | Meaning                                                          |
| ----- | ------ | ---------------------------------------------------------------- |
| Owner | `u`    | The single user who owns the file (the UID stored in the inode)  |
| Group | `g`    | Members of the file's owning group (the GID stored in the inode) |
| Other | `o`    | Everyone else — anyone who is neither the owner nor in the group |

`ls -l` displays all nine bits as one contiguous string, always in `owner`/`group`/`other` order:

```bash
$ ls -l notes.txt
-rw-r--r-- 1 alice devs 220 Jul 26 09:00 notes.txt
```

Reading `-rw-r--r--` left to right: the leading `-` is the file type ([§19](../Part3/Section-19-Part3-Inodes-Hard-Links-Symbolic-Links.md) covered `l` for symlink; `d` for directory follows the same convention), then three groups of three — `rw-` (owner: read+write, no execute), `r--` (group: read only), `r--` (other: read only).

> 💡 **Tip:** [§25](./Section-25-Part4-Users-Groups-Passwd-Shadow-Group.md)/[§26](./Section-26-Part4-User-Group-Management-Commands.md) covered where owner and group identity actually come from (`/etc/passwd`'s UID, `/etc/group`'s GID) and how they're assigned/changed at the account level. This section is about the bits themselves, not about user/group provisioning — the two topics compose, but they're distinct layers.

## 2. The Directory Execute Bit: The Single Most Common Interview Gotcha

The table in the permissions-and-identity-classes overview above already states it, but it deserves its own section because it is the permission-model fact most candidates get wrong under questioning: **execute on a directory does not mean "run this directory as a program"** — directories aren't executable code — it means **"permission to traverse/enter this directory and resolve names inside it."**

The practical consequences of this distinction:

- **`r` without `x` on a directory:** you can `ls` the directory and see filenames, but you cannot `cd` into it, and you cannot access any file inside it by path — even a file you personally own — because resolving `dir/file` requires traversal permission on `dir` first. `ls` will show names but every `stat`-dependent detail (size, permissions, timestamps) will fail or show as unavailable, since fetching that requires the traversal step `x` gates.
- **`x` without `r` on a directory:** you cannot list the directory's contents with `ls` (its output will be empty or an error), but you **can** access a specific file inside it if you already know its exact name — `cat dir/secret.txt` succeeds even though `ls dir/` shows nothing. This is a deliberate, real pattern: a directory with `--x` for `other` lets processes reach a known file path without exposing a directory listing to enumerate what else is there.
- **Neither `r` nor `x`:** the directory is completely opaque from outside — no listing, no traversal, no access to anything inside regardless of that inner file's own permissions.

```bash
$ mkdir secretdir && touch secretdir/file.txt
$ chmod 600 secretdir   # rw- --- --- : no traversal for anyone but owner
$ ls secretdir/         # ls: cannot open directory 'secretdir': Permission denied
$ cat secretdir/file.txt   # cat: secretdir/file.txt: Permission denied
```

> 💡 **Tip:** The clean mental model: **`r` on a directory controls what `ls` can see; `x` on a directory controls whether you can get in at all** (and, transitively, whether anything inside is reachable by path). A file's own permissions are irrelevant if any directory in its path lacks the traversal bit for you — permission checking walks the entire path, not just the final component.

## 3. Symbolic vs. Octal chmod Notation

`chmod` changes the permission bits on a file or directory, and accepts two independent notations that produce identical results — knowing both, and when each is the better tool, is expected of anyone operating Linux day to day.

### 3.1 Symbolic Notation

**Syntax:**

```bash
chmod [ugoa][+-=][rwx] FILE
```

The three parts: **who** (`u`/`g`/`o`/`a` for all three combined), an **operator** (`+` add, `-` remove, `=` set exactly — clearing anything not listed), and **which bits**.

```bash
$ chmod u+x script.sh          # add execute for owner only
$ chmod g-w shared.conf        # remove write for group only
$ chmod o=r public.txt         # set other to read-only, exactly (clears w and x if present)
$ chmod a+r,u+w draft.md       # multiple clauses, comma-separated: read for all, write for owner
```

**Why reach for symbolic notation:** it's the right tool when you want to change **one specific bit** without needing to know or recompute the other eight — `chmod u+x` doesn't care what the group/other bits currently are, it just adds one bit to owner. This makes it safer for targeted, incremental changes and for scripting where the starting permission state is unknown or shouldn't matter.

### 3.2 Octal Notation

**Syntax:**

```bash
chmod NNN FILE
```

Each digit is the sum of `r`=4, `w`=2, `x`=1 for one identity class, in `owner`/`group`/`other` order — three digits, one per class.

**Full translation table:**

| Octal | Symbolic | Meaning                |
| ----- | -------- | ---------------------- |
| 0     | `---`    | No permissions         |
| 1     | `--x`    | Execute only           |
| 2     | `-w-`    | Write only             |
| 3     | `-wx`    | Write + execute        |
| 4     | `r--`    | Read only              |
| 5     | `r-x`    | Read + execute         |
| 6     | `rw-`    | Read + write           |
| 7     | `rwx`    | Read + write + execute |

Combining three digits gives the full permission set for a file:

| Command       | Symbolic form | Common use case                                                                 |
| ------------- | ------------- | ------------------------------------------------------------------------------- |
| `chmod 644 f` | `rw-r--r--`   | Standard file: owner read/write, everyone else read-only                        |
| `chmod 755 d` | `rwxr-xr-x`   | Standard directory or executable: owner full, everyone else read+traverse/run   |
| `chmod 600 f` | `rw-------`   | Private file: only owner can read/write — SSH private keys, credential files    |
| `chmod 700 d` | `rwx------`   | Private directory: only owner can enter/list/modify — home directories, secrets |
| `chmod 664 f` | `rw-rw-r--`   | Group-collaborative file: owner and group can edit, others read-only            |
| `chmod 775 d` | `rwxrwxr-x`   | Group-collaborative directory: owner and group full access, others traverse     |
| `chmod 777 f` | `rwxrwxrwx`   | Wide open — every class gets everything; almost never the correct answer        |
| `chmod 400 f` | `r--------`   | Read-only even to the owner — a common pattern for archived/immutable evidence  |

**Why reach for octal notation:** it's the right tool when you want to **set the entire permission state explicitly and unambiguously** in one command — deploy scripts, Ansible/Terraform provisioning, and Dockerfiles overwhelmingly use octal precisely because it's an absolute assignment, not a delta, so the resulting state doesn't depend on whatever permissions happened to exist beforehand.

> ⚠️ **Warning:** `chmod 777` is not a "make it work" fix, it's an anti-pattern that shows up constantly in troubleshooting threads and should be treated as a red flag in code review — it grants write access to `other`, meaning any user or process on the box (or, for a world-readable/writable path served by a misconfigured service, potentially unauthenticated remote actors) can modify or replace the file. The correct fix for a permission error is almost always to identify the actual owner/group mismatch, per the `chmod -R` recursion section below, or the actual bit that's missing, not to remove every restriction.

## 4. `chmod -R`: Recursion and the Mixed-Permission Trap

`chmod -R` applies a permission change recursively through an entire directory tree — but it applies the **same** mode string to every entry regardless of whether that entry is a file or a directory, which is where a very common production mistake originates.

```bash
$ chmod -R 755 /opt/app
```

This looks reasonable — "owner full access, everyone else read+execute" — but it sets the **execute bit on every file**, not just directories and actual programs. A `.conf`, `.json`, `.pem`, or `.log` file inside that tree now has execute permission it has no business having: harmless to functionality in most cases (nothing tries to execute a config file), but a real hygiene and audit-surface problem — security scanners and CIS-style benchmarks ([§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md)) routinely flag unexpected execute bits on non-executable file types as a sign of sloppy permission management, and it obscures the meaningful signal execute bits are supposed to carry ([§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md)'s SUID/SGID coverage depends on execute bits meaning something specific).

The reverse mistake is just as common: `chmod -R 644 /opt/app` sets a uniform read/write-no-execute mode, which correctly fixes files but **removes the traversal bit from every directory in the tree** — per the directory-execute-bit discussion above, that makes the entire tree unreachable, including to the owner, because `cd` and path resolution both require directory `x`.

**The correct pattern separates files from directories using `find`:**

```bash
find /opt/app -type d -exec chmod 755 {} +   # directories: rwx for owner, r-x for group/other
find /opt/app -type f -exec chmod 644 {} +   # files: rw- for owner, r-- for group/other
```

For files that specifically need to be executable (actual scripts/binaries), a third pass or a more targeted `find ... -name '*.sh'` handles those separately, rather than folding them into a blanket recursive `chmod -R`.

> ⚠️ **Warning:** Before running any `chmod -R`, ask whether the tree contains a mix of files and directories with genuinely different intended permissions — it almost always does. `chmod -R` is safe and correct only when every entry in the tree truly should end up with the identical mode, which is rare outside of narrow cases like a directory of uniformly-private secret files.

## 5. `chown` and `chgrp`: Changing Ownership

Where `chmod` changes **what the existing owner/group/other are allowed to do**, `chown` and `chgrp` change **who the owner and group actually are** — a completely separate axis of the permission model, and the inode fields [§19](../Part3/Section-19-Part3-Inodes-Hard-Links-Symbolic-Links.md) listed (UID, GID) rather than the mode bits.

### 5.1 `chown` — Change Owner (and Optionally Group)

**Syntax:**

```bash
chown [OPTIONS] USER[:GROUP] FILE...
```

```bash
$ chown alice file.txt              # change owner only, leave group untouched
$ chown alice:devs file.txt         # change owner AND group in one command
$ chown :devs file.txt              # change group only (equivalent to chgrp devs file.txt)
$ chown -R alice:devs /opt/app      # recursive ownership change through a whole tree
```

**Key flags:**

| Flag | Meaning                                                                                                                                                    |
| ---- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-R` | Recursive — apply through an entire directory tree                                                                                                         |
| `-v` | Verbose — print each file as its ownership changes, useful for auditing a bulk operation                                                                   |
| `-h` | Act on a symlink itself rather than the file it points to (relevant given [§19](../Part3/Section-19-Part3-Inodes-Hard-Links-Symbolic-Links.md)'s symlinks) |

Unlike `chmod -R`'s mixed-permission trap covered above, `chown -R` doesn't have an equivalent structural hazard — ownership is a single flat concept that applies identically whether the target is a file or a directory, so a recursive ownership change is generally safe to apply uniformly across a whole tree.

### 5.2 `chgrp` — Change Group Only

**Syntax:**

```bash
chgrp [OPTIONS] GROUP FILE...
```

```bash
$ chgrp devs shared.conf
$ chgrp -R devs /srv/shared
```

`chgrp devs file.txt` and `chown :devs file.txt` are exactly equivalent — `chgrp` exists as a dedicated, slightly clearer command for the group-only case, not because it does anything `chown` can't.

### 5.3 Why Only root Can `chown` to Another User

This is a deliberate security boundary, not an arbitrary restriction: an unprivileged user is **never** permitted to change a file's owner to someone else, even a file they themselves own. Only `root` (or a process with the `CAP_CHOWN` capability) can perform an owner change to a different UID.

The reasoning: if ordinary users could give away ownership of their own files, disk-quota accounting ([§29](./Section-29-Part4-Umask-Default-Permissions.md)'s umask territory adjoins this, but quotas specifically are enforced per-owning-UID) could be trivially defeated — a user near their quota limit could `chown` files to another user to dodge the accounting, or worse, could `chown` a malicious file to make it appear to have been created and be owned by someone else entirely, muddying audit trails and blame attribution during an incident. Ownership is meant to be an authoritative, tamper-resistant record of who a file belongs to, which only requires trusting the one privileged actor (root) rather than every user's self-reported claims.

**A regular user _can_, however, `chgrp` a file they own — but only to a group they are themselves already a member of.** This is a narrower, safe capability: you can hand group-read/write access to a team you belong to without needing root, but you can't grant yourself membership in a group you're not in as a side effect of a `chgrp` call — group membership itself is still gated through `/etc/group` and the `usermod`/`groupadd` tooling [§26](./Section-26-Part4-User-Group-Management-Commands.md) covered.

```bash
$ whoami
alice
$ groups alice
alice devs

$ chgrp devs myfile.txt      # succeeds — alice is a member of devs
$ chgrp root myfile.txt      # fails: Operation not permitted — alice is not in group 'root'
$ chown bob myfile.txt       # fails: Operation not permitted — only root can reassign owner
```

> 💡 **Tip:** If a deploy or CI pipeline needs to reassign file ownership to a service account (a very common pattern — artifacts built as one user, deployed to run as another), that step must run as root (or via `sudo chown`, [§31](./Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md)) — expecting an unprivileged deploy user to `chown` its own output to a different service account will fail every time, and this is a frequent source of confusing pipeline permission errors that gets misdiagnosed as a `chmod` problem when it's actually this ownership-reassignment restriction.

## 6. A Richer Alternative: Access Control Lists

The owner/group/other model is exactly three identity slots per file — it cannot natively express "give this one specific additional user read access, without changing the owning group or exposing it to everyone else." Real-world sharing needs frequently don't fit into three slots, and forcing them to (by creating narrow one-off groups for every combination of collaborators, for instance) doesn't scale cleanly. **Access Control Lists (ACLs)** extend permissions to an arbitrary number of named users and groups per file, via `getfacl`/`setfacl` — full syntax and depth is [§30](./Section-30-Part4-Access-Control-Lists.md); this section only needs you to know ACLs exist as the answer when the standard model's three-slot limit becomes the actual constraint.

## 7. Common Misconceptions

1. **"Execute on a directory means you can run it."** Directories aren't executable programs — `x` on a directory grants traversal (the ability to `cd` into it and resolve paths through it), a completely different meaning from `x` on a regular file, as the directory-execute-bit section above covers.
2. **"`chmod -R 755` is a safe, general-purpose fix for permission errors."** It's a common anti-pattern — applying one mode uniformly to a mixed tree gives every file an execute bit it likely shouldn't have, and the equally common reverse mistake (`chmod -R 644`) strips directory traversal and makes the tree unreachable entirely, per the `chmod -R` recursion section above. Separate `find -type f` and `find -type d` passes are the correct approach.
3. **"`chown` to another user works the same way `chgrp` does — any owner can reassign either."** They're asymmetric by design: any user can `chgrp` their own file to a group they belong to, but only root can `chown` a file to a different owning user at all — a deliberate boundary that protects quota accounting and audit-trail integrity, as the root-only-`chown` section above covers.
4. **"777 means 'fully working,' so it's a reasonable troubleshooting step."** It resolves the symptom (permission denied) by removing the entire access-control boundary, including granting write access to every user and process on the system — the correct fix is identifying the specific missing bit or the actual owner/group mismatch, not eliminating restrictions altogether, per the octal-notation section above.
5. **"If I can read a file, I can read it regardless of where it lives."** File-level read permission is necessary but not sufficient — every directory in the path also needs traversal (`x`) permission for you, or the file is unreachable no matter how permissive its own bits are, as the directory-execute-bit section above covers.

## 8. Tiered Interview Questions

**🎯 Beginner:** _"What do read, write, and execute mean when applied to a directory, as opposed to a file?"_
**Model answer:** On a file, `r` means you can view its contents, `w` means you can modify them, and `x` means you can run it as a program or script. On a directory, the meanings shift: `r` means you can list its contents with something like `ls`, `w` means you can create, delete, or rename entries inside it, and `x` means you can traverse into it — `cd` into it, or resolve any path that goes through it. Execute on a directory has nothing to do with "running" the directory; it's purely about whether you're allowed to enter and pass through it.
_What the interviewer is probing for:_ Whether the candidate knows the directory-execute meaning is different from the file-execute meaning, rather than assuming `x` means one universal thing.

**🎯 Intermediate:** _"When would you use symbolic chmod notation like `u+x` instead of octal notation like `755`, and vice versa?"_
**Model answer:** Symbolic notation is the right tool for a targeted, incremental change to one bit without needing to know or preserve the current state of the other eight — `chmod u+x script.sh` adds execute for the owner regardless of whatever the group/other bits currently are. Octal notation sets the entire nine-bit permission state explicitly and absolutely in one command, which is why deploy scripts, Ansible, Terraform, and Dockerfiles favor it — the resulting permissions are deterministic and don't depend on whatever the file's permissions happened to be beforehand. I reach for symbolic when I'm adjusting one thing on an existing file interactively, and octal when I'm provisioning or asserting a known-good state from scratch.
_What the interviewer is probing for:_ Practical fluency with both notations and an understanding of _why_ one is preferred in automation contexts (idempotent absolute state) versus interactive use (incremental deltas).

**🎯 Senior:** _"A junior engineer ran `chmod -R 755` across a deployment directory to 'fix a permissions issue,' and now a security scan is flagging unexpected execute bits on config and log files. Walk me through what happened and how you'd remediate it."_
**Model answer:** `chmod -R` applies one uniform mode to every entry in the tree regardless of whether it's a file or a directory — `755` is a sensible mode for directories (owner full access, everyone else read+traverse) and for actual executables, but applied blindly to every file it also grants execute to `.conf`, `.json`, `.log`, and any other non-executable file in the tree. Functionally this is often harmless — nothing tries to execute a config file — but it's exactly the kind of finding a CIS-benchmark-style scan flags, because unexpected execute bits are a signal of sloppy permission management and widen the audit surface unnecessarily. To remediate, I'd split the operation: `find /path -type d -exec chmod 755 {} +` for directories, `find /path -type f -exec chmod 644 {} +` for files, and then a separate, explicit pass for the actual small set of files that do need to be executable (deploy scripts, binaries) rather than folding everything into one recursive command. I'd also use this as a teaching moment — `chmod -R` is safe only when every entry in a tree genuinely should end up with an identical mode, which is the exception rather than the rule for a real deployment directory.
_What the interviewer is probing for:_ Recognition of the specific mixed-permission failure mode, not just "chmod -R can be risky" in the abstract, plus a concrete, correct remediation using `find`.

**🎯 Architect:** _"Design the ownership and permission strategy for a shared build artifact directory where a CI pipeline (running as a `ci` service account) produces files, and a deploy pipeline (running as a `deploy` service account) needs to read and move them, but neither should be able to arbitrarily modify each other's other files on the host."_
**Model answer:** I'd create a dedicated group, say `build-artifacts`, with both `ci` and `deploy` as members, and set the artifact directory's owning group to that — `chown -R ci:build-artifacts /srv/artifacts` initially, with `chmod 2775` on the directory (the leading `2` is SGID, covered fully in [§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md), which makes new files inside automatically inherit the `build-artifacts` group rather than each process's primary group). Files the `ci` account writes would get mode `644` or `664` depending on whether `deploy` also needs write access to them, and I'd avoid `777` entirely — neither pipeline needs `other` access, so that class stays at `0` or read-only. Critically, I would not have `deploy` try to `chown` artifacts to itself — since only root can reassign ownership across users, per the root-only-`chown` section above, a service account can't do that even for its own convenience, and trying to work around that restriction (for example running the deploy step as root just to chown) is itself a red flag that expands blast radius unnecessarily. Instead, `deploy` operates entirely via its group membership and the group-write bits already in place — no ownership changes required in steady state, and if I did need broader per-user sharing beyond what the owner/group/other model expresses cleanly, I'd reach for ACLs, covered in the richer-alternative section above, rather than multiplying narrow one-off groups. I'd also want auditd ([§95](../Part12/Section-95-Part12-Secrets-Management-Linux-Hosts.md)) watching that directory for unexpected chmod/chown events, since a permission or ownership drift on a shared artifact path is exactly the kind of thing that should be caught immediately rather than discovered during an incident.
_What the interviewer is probing for:_ Ability to design a real multi-actor permission scheme using groups correctly, awareness of the chown-privilege boundary as a design constraint rather than an obstacle to route around, and knowing when to escalate to ACLs instead of forcing everything through three identity slots.

## 9. Key Takeaways

- Permissions are three bits (`rwx`) times three identity classes (owner/group/other), stored in the inode ([§19](../Part3/Section-19-Part3-Inodes-Hard-Links-Symbolic-Links.md)) and always displayed in that fixed order by `ls -l`.
- Execute on a directory means traversal — the ability to enter it and resolve paths through it — not "run it as a program"; this is the model's most common interview gotcha, and every directory in a path needs `x` for you or the whole path is unreachable regardless of the target file's own permissions.
- `chmod` supports symbolic notation (`u+x`, `g-w`, `o=r` — best for targeted incremental changes) and octal notation (`755`, `644` — best for absolute, deterministic state, which is why automation tooling favors it).
- `chmod -R` applies one mode uniformly across a mixed tree of files and directories — the classic overreach is `755` giving every file an unwanted execute bit, and the mirror mistake is a restrictive mode stripping directory traversal; split with `find -type f`/`find -type d` instead.
- `chown user:group` changes owner and/or group in one call; `chgrp` changes group only and is equivalent to `chown :group`.
- Only root can `chown` a file to a different owning user — a security boundary protecting quota accounting and audit integrity — but any user can `chgrp` their own file to a group they already belong to.
- When the three-slot owner/group/other model can't express a sharing requirement, ACLs (`getfacl`/`setfacl`, [§30](./Section-30-Part4-Access-Control-Lists.md)) extend permissions to arbitrary named users and groups per file.

## 10. Related Concepts & What's Next

This section depends on [§19](../Part3/Section-19-Part3-Inodes-Hard-Links-Symbolic-Links.md)'s inode model (permissions and ownership are inode fields, not directory-entry properties) and on [§25](./Section-25-Part4-Users-Groups-Passwd-Shadow-Group.md)/[§26](./Section-26-Part4-User-Group-Management-Commands.md)'s user and group provisioning (owner/group identity has to exist before it can be assigned here). [§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md) (next) builds directly on the octal notation from the octal-notation section above by introducing the fourth permission dimension — SUID, SGID, and the sticky bit — which occupy a leading digit this section deliberately left at `0` in every example. [§29](./Section-29-Part4-Umask-Default-Permissions.md) covers `umask`, the mechanism that determines what permissions a newly created file gets _before_ any `chmod` is ever run. [§30](./Section-30-Part4-Access-Control-Lists.md) covers ACLs, introduced above, in full syntax once the three-slot model's limits are reached. [§31](./Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md) (`sudo`) is the privilege-escalation layer that lets an otherwise-unprivileged user perform root-only operations like the `chown` restriction covered above, under controlled, audited conditions.

**Next Section:** [§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md) — `Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md`
