# Section 30 (Part 4): Access Control Lists (ACLs)

## 1. The Limitation ACLs Exist to Solve

[§27](./Section-27-Part4-Standard-Permission-Model.md) established the standard permission model as exactly three identity slots per file — owner, group, other — and closed with the case where that model breaks down: **you cannot express "give this one additional specific user read access, without changing the owning group or exposing the file to everyone else"** using `chmod`/`chown` alone.

This isn't a rare edge case. Real sharing requirements routinely need more than three slots:

- A contractor needs read access to one directory in a project they aren't otherwise part of, without joining the team's group and gaining access to everything else that group can see.
- Two different teams each need different levels of access to the same shared file — one read-write, one read-only — and neither is a subset of the other.
- An auditor needs read-only access to a specific log directory, but adding them to the owning group would also hand them access to unrelated files owned by that same group elsewhere on the host.

The workaround people reach for without ACLs — creating a narrow, one-off group for every combination of collaborators — doesn't scale. Every new sharing requirement spawns a new group, `/etc/group` grows unmanageably, and the actual access-control intent ("alice specifically, read-only, on this one file") gets buried inside indirection through group membership that has to be reverse-engineered later.

**Access Control Lists (ACLs)** extend the permission model to an arbitrary number of named users and groups per file or directory, layered on top of the standard `rwx`/owner/group/other bits rather than replacing them.

> 💡 **Tip:** ACLs don't replace the standard permission model — they extend it. The traditional owner/group/other bits still exist on every file and still matter; ACL entries add named exceptions on top. Removing all ACL entries returns a file to being governed purely by the bits [§27](./Section-27-Part4-Standard-Permission-Model.md) covered.

## 2. `getfacl`: Reading ACL State

**Purpose:** Display the full access control list for a file or directory — every named user entry, named group entry, the owning user/group, other, and (for directories) any default entries.

**Syntax:**

```bash
getfacl FILE
```

**Example usage and expected output:**

```bash
$ getfacl report.csv
# file: report.csv
# owner: bob
# group: finance
user::rw-
user:alice:r--
group::r--
group:auditors:r--
mask::rw-
other::---
```

Reading this: `bob` (owner) has read-write, `finance` (owning group) has read-only, a named ACL entry grants `alice` read-only, another named entry grants the `auditors` group read-only, `mask` caps what named entries can effectively grant, as the `setfacl` section below details, and `other` has nothing.

**Common errors:**

- Assuming a file with no visible `+` in `ls -l` still needs `getfacl` checked — it doesn't; the `+` is a reliable signal that ACL entries exist beyond the standard bits, so `getfacl` is only necessary once that flag is spotted.

## 3. `setfacl`: Setting and Modifying ACL Entries

**Syntax:**

```bash
setfacl -m ENTRY FILE      # modify: add or change one or more entries
setfacl -x ENTRY FILE      # remove one specific entry
setfacl -b FILE            # remove ALL ACL entries, back to plain owner/group/other
```

**Key flags:**

| Flag | Meaning                                                                                                                                     |
| ---- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| `-m` | Modify — add or update one or more ACL entries (comma-separated for multiple in one call)                                                   |
| `-x` | Remove one named entry, leaving other ACL entries and the base bits intact                                                                  |
| `-b` | Strip every ACL entry from the file, reverting to pure owner/group/other                                                                    |
| `-R` | Recursive — apply through a directory tree (same mixed-tree caution as [§27](./Section-27-Part4-Standard-Permission-Model.md)'s `chmod -R`) |
| `-d` | Set a **default** ACL on a directory, for inheritance — see the default ACL section below                                                   |

**Example usage:**

```bash
$ setfacl -m u:alice:rx report.csv          # grant alice read+execute
$ setfacl -m g:devs:rw shared.conf          # grant the devs group read-write
$ setfacl -m u:alice:rx,g:auditors:r file   # multiple entries in one call
$ setfacl -x u:alice report.csv             # remove alice's entry specifically
$ setfacl -b report.csv                     # strip all ACL entries entirely
```

Entry syntax follows `[u|g]:name:permissions` — `u:alice:rx` for a named user, `g:devs:rw` for a named group. Omitting the name (`u::rw`, `g::r`) targets the file's actual owner/owning-group entries rather than a named addition, which is a less common but valid form of the same syntax.

**Production usage example:** Granting a deploy auditor temporary read access to a specific release directory without folding them into the `deploy` group — `setfacl -m u:auditor:rx /srv/releases/2026-07` — is a common, narrowly-scoped ACL use that avoids widening group membership just to satisfy a one-off access need.

**Common errors:**

- Forgetting that `-x` takes just the identity (`u:alice`), not a permission string — `setfacl -x u:alice:rx file` is invalid syntax for removal; only `setfacl -x u:alice file` removes the entry.
- Running `setfacl -m` and expecting the new entry to take effect immediately regardless of the mask — it doesn't, as the mask entry below explains.

### 3.1 The Mask Entry: A Silent Permission Cap

The **mask** entry (visible in `getfacl` output as `mask::rw-`) is the single biggest source of ACL confusion in production, and deserves to be understood on its own.

The mask defines the **maximum effective permission** for every named user entry and named group entry (and the owning group entry) on the file — not the owner, and not `other`. If a named entry grants more than the mask allows, the **effective** permission is silently reduced to whatever the mask permits, with no error and no warning at the point the ACL was set.

```bash
$ setfacl -m u:alice:rwx file
$ setfacl -m m::r file          # tighten the mask to read-only
$ getfacl file
# file: file
# owner: bob
# group: finance
user::rw-
user:alice:rwx          #effective:r--
mask::r--
other::---
```

`alice`'s entry still reads `rwx` in the listing, but the `#effective:r--` comment shows the mask has capped it down to read-only in practice. `getfacl` surfaces this comment automatically whenever a mask reduces an entry's effective permission — but it's easy to miss in a quick scroll of output, and it's invisible entirely if nobody thinks to re-run `getfacl` after a change.

> ⚠️ **Warning:** `setfacl -m` automatically **recalculates the mask** to the union of all named-entry permissions by default, unless you set the mask explicitly with `m::PERMS` in the same or a later call — so ACL behavior can shift unexpectedly as entries are added over time. Before troubleshooting "why doesn't this user's ACL grant seem to work," always check the mask first — it is the most common cause of an ACL entry that looks correct in `getfacl` but doesn't actually grant the access it appears to.

## 4. Default ACLs on Directories: Inheritance

A **default ACL**, set with `setfacl -d`, applies only to directories and defines the ACL that new files and subdirectories created inside it inherit automatically — it doesn't grant any access on the directory itself beyond what the equivalent non-default entry would.

**Syntax:**

```bash
setfacl -d -m ENTRY DIRECTORY
```

**Example usage:**

```bash
$ setfacl -d -m g:devs:rw /srv/shared
$ touch /srv/shared/newfile.txt
$ getfacl /srv/shared/newfile.txt
# file: newfile.txt
# owner: bob
# group: finance
user::rw-
group::r--
group:devs:rw-
mask::rw-
other::---
```

`newfile.txt` inherited the `devs:rw` entry automatically, without anyone running `setfacl` on it directly — this is the ACL analog of [§29](./Section-29-Part4-Umask-Default-Permissions.md)'s umask, and the two interact: umask still determines the base owner/group/other bits a new file gets by default, while a directory's default ACL layers named entries on top of whatever umask would otherwise produce. Neither one overrides the other; they apply to different parts of the resulting permission set.

> 💡 **Tip:** Setting a default ACL on a directory (`setfacl -d`) does not retroactively apply it to files already inside that directory — it only governs what happens at creation time going forward. Combine it with `setfacl -R -m` once, on existing content, if the directory already has files that need the same entries applied.

## 5. How ACLs Surface in `ls -l`

Any file or directory carrying ACL entries beyond the standard bits shows a trailing **`+`** immediately after the nine-character permission string in `ls -l` output:

```bash
$ ls -l report.csv
-rw-r--r--+ 1 bob finance 4096 Jul 26 09:00 report.csv
```

That `+` is the only signal `ls -l` gives that ACL entries exist — the nine `rwx` characters shown are still just the owner/group/other bits and do not reflect what any named ACL entry grants. Seeing `-rw-r--r--` without checking for the trailing `+` and concluding "only the owner and group have access" is a common and incorrect read of a file that actually has additional named grants via ACL.

**Production usage example:** During an access review or incident investigation, grepping `ls -l` output for a trailing `+` across a directory tree is the fast way to flag which files carry ACL entries that need a separate `getfacl` pass — treating the nine visible bits as the complete picture would miss real grants entirely.

## 6. Filesystem Support Requirements

ACLs require filesystem-level support, not just kernel support in the abstract:

- **ext4 and XFS** support POSIX ACLs natively, and on modern distributions the `acl` mount option is enabled by default — `setfacl`/`getfacl` work out of the box on a standard install.
- Historically, ACL support on ext-family filesystems required the `acl` mount option to be set explicitly in `/etc/fstab` (`defaults,acl`) — omitting it produced `setfacl: Operation not supported` errors even though the tooling itself was installed. This is largely a non-issue on current distribution defaults but is worth checking directly (`mount | grep acl`, or `tune2fs -l /dev/DEVICE` for ext filesystems) on older systems, minimal images, or filesystems mounted with a hand-tuned option list that dropped it.
- Not every filesystem type supports POSIX ACLs the same way — network filesystems and some legacy formats have partial or absent support, which matters when a directory tree spans mount points with different underlying filesystems.

**Troubleshooting:** If `setfacl` fails with an operation-not-supported error on a filesystem that should support ACLs, verify the mount options actually include `acl` before assuming a tooling or permissions problem.

## 7. Removing ACLs

```bash
$ setfacl -b report.csv        # strip every ACL entry, back to plain owner/group/other
$ getfacl report.csv
# file: report.csv
# owner: bob
# group: finance
user::rw-
group::r--
other::---
```

After `-b`, the file's standard bits ([§27](./Section-27-Part4-Standard-Permission-Model.md)) remain exactly as they were — `-b` only removes the ACL layer, it doesn't touch owner, group, or the base `rwx` triplet. `getfacl` on a file with no ACL entries at all shows only the three base lines and no `mask` entry, and `ls -l` drops the trailing `+`.

## 8. Operational Complexity: Use ACLs Narrowly

ACLs solve a real gap, but they come with a real cost that's easy to underweight when reaching for them:

- **They're invisible in the tool most admins check first.** `ls -l` shows only the `+` flag, not what the ACL actually grants — anyone auditing permissions by eye has to know to run `getfacl` on every flagged file, which is an easy step to skip under time pressure.
- **The mask makes "looks right" and "is right" diverge.** A `getfacl` listing can show an entry granting `rwx` while the effective permission is silently `r--` because of the mask entry covered above — debugging an access-denied report on a file with ACLs takes longer than debugging the same report on a file governed purely by standard bits.
- **They don't compose cleanly with some backup, sync, and archive tools.** Not every `cp`, `rsync`, or `tar` invocation preserves ACL entries by default (`rsync -A`, `cp --preserve=all`/`-p` with ACL-aware builds are needed) — a routine backup or migration that doesn't explicitly preserve ACLs can silently drop them, leaving the restored copy under-permissioned relative to the original without any error being raised.
- **They spread access-control logic across two places instead of one.** Once ACLs are in use, understanding "who can access this file" requires checking both the standard bits and the ACL entries — for a host or fleet where ACLs are used pervasively, that doubling of what has to be audited is a genuine, ongoing operational cost, not a one-time setup cost.

The practical guidance senior teams converge on: reach for ACLs when the three-slot model genuinely can't express the requirement, as established by [§27](./Section-27-Part4-Standard-Permission-Model.md)'s three-slot limitation, not as a default habit for every sharing need — a well-designed group structure handles most real cases more transparently, and ACLs are best reserved for the specific, narrow exceptions groups can't cleanly cover.

> ⚠️ **Warning:** Treat any file or directory carrying ACL entries as needing explicit documentation of _why_ — a stray `setfacl` entry left over from a resolved one-off request is a common source of stale access that outlives its justification, precisely because it's invisible to a casual `ls -l` review and easy to forget was ever set.

## 9. Common Misconceptions

1. **"ACLs replace the standard permission bits."** They extend them — every file still has its owner/group/other bits, and `setfacl -b` proves this by showing those bits fully intact once every ACL entry is stripped away, as the removing-ACLs section above demonstrates.
2. **"If `getfacl` shows `rwx` on a named entry, that's the effective permission."** Not necessarily — the mask entry caps what every named user/group entry (and the owning group entry) can actually grant, and `getfacl` only surfaces the reduction via an easy-to-miss `#effective:` comment, as covered in the mask section above.
3. **"A default ACL on a directory retroactively protects existing files inside it."** It only governs files created after the default ACL is set — existing content needs a separate, explicit `setfacl -R` pass, as the default ACL section above notes.
4. **"`ls -l`'s `rwx` string is the complete permission picture."** If the string ends in `+`, it isn't — that flag means ACL entries exist beyond the nine visible characters, and only `getfacl` shows the full picture, as the `ls -l` section above covers.
5. **"ACLs are always available wherever chmod works."** They require filesystem-level support and, historically, an explicit `acl` mount option — assuming availability without checking can produce a confusing operation-not-supported error on older systems or unusually mounted filesystems, as the filesystem-support section above details.

## 10. Tiered Interview Questions

**🎯 Beginner:** _"What problem do ACLs solve that the standard owner/group/other permission model can't?"_
**Model answer:** The standard model gives exactly three identity slots per file — one owner, one group, and everyone else — so it can't express "grant this one additional specific user access without changing the owning group or exposing the file to everyone." ACLs extend permissions to an arbitrary number of named users and groups per file via `setfacl`, layered on top of the existing bits rather than replacing them, which handles sharing requirements that don't fit cleanly into three slots.
_What the interviewer is probing for:_ Understanding that ACLs are additive to, not a replacement for, the standard model, and a concrete grasp of the specific limitation being solved rather than a vague "more flexible permissions" answer.

**🎯 Intermediate:** _"You ran `setfacl -m u:alice:rwx file` but alice reports she still can't write to the file. What's the most likely cause, and how do you confirm it?"_
**Model answer:** The most likely cause is the ACL mask capping the effective permission below what alice's named entry appears to grant — the mask defines the maximum effective permission for every named user and group entry, and `setfacl` can silently leave or recalculate a restrictive mask depending on prior calls. I'd confirm by running `getfacl file` and checking specifically for an `#effective:` comment next to alice's entry, which `getfacl` prints automatically whenever the mask reduces what an entry actually grants. If that's the issue, the fix is `setfacl -m m::rwx file` (or otherwise widening the mask), not re-granting alice's entry, since her entry was already correct.
_What the interviewer is probing for:_ Direct familiarity with the mask as the most common ACL gotcha, and a concrete diagnostic step rather than guessing at re-running `setfacl`.

**🎯 Senior:** _"A team wants to use ACLs pervasively across a shared filesystem instead of maintaining groups. What would you push back on?"_
**Model answer:** I'd push back on ACLs as the default mechanism rather than the narrow exception. Groups are visible in one place (`/etc/group`), audited with one set of tools, and preserved consistently by nearly every backup and sync tool by default. ACLs are invisible to a plain `ls -l` beyond a single `+` flag, require a second command (`getfacl`) to actually inspect, carry the mask gotcha where a listed permission and its effective permission silently diverge, and aren't reliably preserved by every `cp`/`rsync`/`tar` invocation unless ACL-aware flags are used explicitly — so a routine backup or migration can quietly drop access grants nobody notices until something breaks. Pervasive ACL usage also means every access review has to check two systems instead of one. I'd recommend groups as the default design and reserve ACLs specifically for cases groups genuinely can't express cleanly — narrow, well-documented exceptions rather than the primary access-control mechanism for the whole filesystem.
_What the interviewer is probing for:_ Ability to weigh a feature's real operational cost against its convenience, and a concrete list of specific downsides rather than a generic "ACLs are complex" statement.

**🎯 Architect:** _"Design an access model for a shared `/data` filesystem where most access should be group-based, but a small number of one-off external-user grants are unavoidable. How do you keep this auditable long-term?"_
**Model answer:** I'd keep groups as the primary access-control layer for anything that maps to a real, ongoing team or role — that covers the overwhelming majority of access needs and stays visible via `/etc/group` and standard permission audits. For the genuinely one-off cases — a contractor needing read access to one directory without joining a team's group — I'd use a narrowly scoped ACL entry (`setfacl -m u:contractor:rx /data/project-x`) rather than creating a throwaway group, and I'd pair every such grant with an explicit tracking mechanism outside the filesystem itself — a ticket reference, an expiry date in whatever access-review process exists — precisely because ACL entries are invisible to casual inspection and have no built-in expiration. I'd periodically audit for the `+` flag across the tree (`find /data -type f -perm /+`-equivalent scripted check, or `getfacl -R` on scoped subtrees) specifically to catch stale ACL entries that outlived their justification, since that's the failure mode ACLs are most prone to — access nobody remembers granting and nobody notices persisting. I'd also make sure default ACLs (`setfacl -d`) are set deliberately on any directory where inheritance is wanted, rather than relying on umask alone, and document that decision so a future admin doesn't have to reverse-engineer why new files in that directory pick up unexpected grants.
_What the interviewer is probing for:_ Realistic design balancing groups as the default with ACLs as a scoped, tracked exception, plus concrete awareness of the audit burden ACLs introduce and how to mitigate it operationally rather than just avoiding ACLs entirely.

## 11. Key Takeaways

- ACLs exist because the standard owner/group/other model has exactly three identity slots and cannot express arbitrary named-user or named-group grants without ACLs or unscalable one-off groups.
- `getfacl FILE` reads the full ACL; `setfacl -m ENTRY FILE` adds/modifies entries (`u:name:perms`, `g:name:perms`); `setfacl -x ENTRY FILE` removes one entry; `setfacl -b FILE` strips all ACL entries back to plain standard permissions.
- The **mask** entry caps the effective permission of every named entry (and the owning group) — a listed `rwx` can be silently reduced to less, visible only via `getfacl`'s `#effective:` comment; this is the single most common ACL debugging trap.
- Default ACLs (`setfacl -d`) on a directory govern what new files/subdirectories inherit going forward only — they don't retroactively apply to existing content, and they layer on top of, rather than override, umask's ([§29](./Section-29-Part4-Umask-Default-Permissions.md)) role in setting base bits.
- A trailing `+` after the permission string in `ls -l` is the only signal that ACL entries exist — the nine visible `rwx` characters alone are not the complete access picture on a flagged file.
- ext4/XFS support ACLs natively and modern distributions mount with `acl` enabled by default; older systems or unusual mount option lists should be verified directly if `setfacl` reports operation-not-supported.
- ACLs add real operational cost — invisible to casual review, prone to mask-related surprises, inconsistently preserved by backup/sync tooling unless ACL-aware flags are used — so they should be reserved for narrow cases groups genuinely can't cover, not used as a default access-control mechanism.

## 12. Related Concepts & What's Next

This section is the direct continuation of [§27](./Section-27-Part4-Standard-Permission-Model.md)'s three-slot limitation and depends on [§27](./Section-27-Part4-Standard-Permission-Model.md)'s owner/group/other model as the base layer ACL entries extend rather than replace. [§29](./Section-29-Part4-Umask-Default-Permissions.md)'s umask governs the base bits a new file receives at creation; default ACLs, as covered above, layer named-entry inheritance on top of that same creation-time moment without overriding it. [§31](./Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md) (`sudo`, next) moves to a different axis of access control entirely — privilege escalation for specific commands rather than per-file named grants — and is the mechanism an admin would actually use to run `setfacl` on files they don't already have write access to.

**Next Section:** [§31](./Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md) — `Section-31-Part4-Sudo-Privilege-Escalation.md`
