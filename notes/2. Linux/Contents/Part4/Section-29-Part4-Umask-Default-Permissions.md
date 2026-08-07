# Section 29 (Part 4): umask and Default Permissions

## 1. The Kernel-Level Starting Point: 666 for Files, 777 for Directories

[§27](./Section-27-Part4-Standard-Permission-Model.md) covered `chmod` as the tool for setting permissions explicitly after a file already exists. This section answers the question that comes before that: **what permissions does a file or directory get the instant it's created, before anyone has run `chmod` at all?**

The answer starts at the kernel/syscall level, not with `umask`. When a program calls `open()` with `O_CREAT` to create a new file, or `mkdir()` to create a new directory, it requests a **maximum requested mode** — and the conventional, near-universal request is:

- **666** (`rw-rw-rw-`) for files — read and write for everyone, no execute for anyone.
- **777** (`rwxrwxrwx`) for directories — read, write, and traverse for everyone.

These aren't arbitrary numbers baked into the kernel as a hardcoded default; they're the mode values that `coreutils` (`touch`, `mkdir`, `cp`), compilers, and virtually every program that creates files pass as the requested mode argument. The reasoning behind the specific values:

- **No program should ever request execute permission by default on a plain file it's creating.** A newly created file is data, not code, until something explicitly makes it executable — so 666, not 777, is the file baseline. This is the same reasoning [§27](./Section-27-Part4-Standard-Permission-Model.md) attached to why `chmod 777` on a file is almost always wrong: execute has no business being on by default.
- **Directories need `x` (traversal) to be usable at all** — per [§27](./Section-27-Part4-Standard-Permission-Model.md) [§2](../Part1/Section-02-Part1-History-and-Evolution.md), a directory without `x` is unreachable even by its own owner, so 777 as the _requested_ maximum makes directories at least potentially fully accessible before any restriction is applied.

Critically, **666/777 is only the requested maximum, not the final result.** `umask` is what subtracts from that request to produce the mode the file or directory actually ends up with. Nothing sets a file's real-world permissions to `666` in practice — every modern system has a non-zero umask precisely so this never happens.

> 💡 **Tip:** If you ever see a raw `666` or `777` on a freshly created file, that's a red flag, not a neutral fact — it means either the umask was `000` at creation time, or something explicitly `chmod`ed it afterward. Neither is a normal steady state on a properly configured host.

## 2. How umask Subtracts: Bitwise AND with the Complement

`umask` is a per-process value — a three-digit (or four-digit, matching `chmod`'s octal form) octal mask that represents **permission bits to strip away**, not bits to grant. The arithmetic:

```
final permissions = requested mode  AND  (NOT umask)
```

In octal-digit terms, applied independently to each of the three (owner/group/other) digits: for each bit position, if the umask digit has that bit **set**, the corresponding bit is **removed** from the requested mode; if the umask digit has the bit **clear**, the requested mode's bit passes through unchanged. This is the complement-then-AND operation, not subtraction in the arithmetic sense — a common source of confusion for anyone trying to compute it by simple subtraction and getting the wrong answer on values where that shortcut doesn't hold.

**Worked example — the standard `umask 022` on a new file:**

```
  requested (files):   666  =  110 110 110
  umask:                022  =  000 010 010
  NOT umask:                   111 101 101
  ---------------------------------------------
  result (AND):         644  =  110 100 100
```

Reading it per digit: owner's requested `6` (`rw-`) ANDed with `NOT 0` (`7`, all bits pass) stays `6`. Group's requested `6` (`rw-`) ANDed with `NOT 2` (`5`, write bit stripped) becomes `4` (`r--`). Other's requested `6` ANDed with `NOT 2` again becomes `4`. Result: `644` (`rw-r--r--`) — exactly the standard "owner read/write, everyone else read-only" file mode from [§27](./Section-27-Part4-Standard-Permission-Model.md)'s table.

**Same umask, applied to a new directory (requested 777):**

```
  requested (dirs):    777  =  111 111 111
  umask:                022  =  000 010 010
  NOT umask:                   111 101 101
  ---------------------------------------------
  result (AND):         755  =  111 101 101
```

Owner keeps full `rwx` (`7`), group and other each lose the write bit, keeping `r-x` (`5`). Result: `755` (`rwxr-xr-x`) — the standard directory mode [§27](./Section-27-Part4-Standard-Permission-Model.md) also listed.

This is precisely why the well-known pairing "files land at 644, directories land at 755" is a direct, mechanical consequence of one umask value (`022`) applied to two different requested-mode starting points (666 vs. 777) — not two independent rules that happen to coincide.

> ⚠️ **Warning:** Because umask _subtracts_ bits, it can never _add_ execute permission to a newly created plain file — a file created via `open()`/`O_CREAT` always starts from a 666 request, and no umask value can push a bit back on that was never in the requested mode to begin with. This is exactly why a freshly `touch`ed file is never executable straight out of the box, regardless of umask, while `mkdir` output can be — directories request `x` from the start; files never do.

## 3. Checking and Setting umask Per Shell

**`umask`** with no arguments prints the current shell's mask:

```bash
$ umask
0022
```

The leading `0` is the (rarely used) special-permissions digit position — SUID/SGID/sticky from [§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md) — which umask can also mask, though in practice it's almost always left at `0` since new files/directories never request those bits by default anyway.

**`umask -S`** prints the symbolic, human-readable form of what will actually remain after masking — often easier to reason about than the raw mask itself:

```bash
$ umask -S
u=rwx,g=rx,o=rx
```

**Setting umask for the current shell session:**

```bash
$ umask 027
```

This is process-local and temporary — it affects only the current shell (and anything it subsequently spawns, per 4) and reverts once that shell exits. It does not retroactively change any file that already exists; umask only ever affects files/directories created _after_ it takes effect.

**Making a umask setting persistent** means placing the `umask` command in a shell startup file that runs for every new session:

- **`~/.bashrc`** (or the equivalent for another shell) — a per-user override, takes effect for that one user's interactive shells.
- **`/etc/profile`** or files under **`/etc/profile.d/`** — a system-wide default applied to every login shell on the host, read before any per-user `~/.bashrc` customization, which is the standard place to enforce an organization-wide baseline umask across a fleet.

```bash
# /etc/profile.d/umask.sh
umask 027
```

> 💡 **Tip:** `/etc/profile` (and `/etc/profile.d/*`) apply to **login shells**; `~/.bashrc` applies to **interactive non-login shells**. A umask set only in one may silently not apply in the other context (SSH sessions, cron jobs, systemd services) — a frequent source of "why does this host have a different default umask than I expected" confusion during a fleet audit. [§41](../Part6/Section-41-Part6-Shells-Overview-Configuration-Files.md) covers the login-vs-non-login shell distinction and which startup files run in which case, in full.

## 4. Inheritance: umask and Child Processes

`umask` is a property of a **process**, inherited by every child process it forks — not a filesystem-wide or user-account-wide setting stored anywhere persistent. A shell's umask is copied into any command it runs; that command's children inherit the same value, and so on down the process tree, exactly the parent/child relationship [§33](../Part5/Section-33-Part5-What-A-Process-Is.md) covers for process attributes generally.

The practical consequence: **there is no single "the umask" for a host or a user** — there's only "whatever umask the process that created this file happened to have inherited at the moment it called `open()`/`mkdir()`." This is why:

- A cron job's umask is whatever cron itself was started with (often `022` by default, but distribution-dependent) — not automatically whatever the invoking user's interactive shell had set in `~/.bashrc`, since cron doesn't source that file.
- A systemd service's umask is controlled by the `UMask=` directive in its unit file ([§67](../Part9/Section-67-Part9-Writing-Custom-Systemd-Unit-Files.md)), independent of any shell-level umask setting on the host — services don't inherit an interactive login shell's umask at all, because they aren't forked from one.
- Changing `umask` inside a running shell has zero effect on processes that were already started before the change — only processes forked _after_ the new umask is set inherit it.

> ⚠️ **Warning:** A common production surprise: files created by an application (say, a web server or a batch job running as a service account) end up with unexpectedly permissive or restrictive permissions compared to what an admin expects from their own interactive shell's umask — because the service's umask was inherited from whatever spawned it (systemd, an init script, a container entrypoint), not from the admin's personal shell configuration. Diagnosing this means checking the umask **in the actual process's context** (`/proc/[pid]/status` shows it, or `cat /proc/[pid]/status | grep Umask` on Linux), not assuming it matches an interactive `umask` check.

## 5. System-Wide Defaults: `/etc/login.defs` and PAM

Two mechanisms set the umask that new login sessions start with, independent of what any individual `~/.bashrc` might later override:

**`/etc/login.defs`** — a `UMASK` directive that historically governed the umask applied by `login`-family tools for interactive sessions:

```
# /etc/login.defs
UMASK           022
```

**`pam_umask`** — the PAM module ([§32](./Section-32-Part4-PAM-Overview.md)'s PAM overview covers the general PAM architecture) that many modern distributions use instead of, or alongside, `/etc/login.defs`'s `UMASK`, configured in files like `/etc/pam.d/login` or `/etc/pam.d/common-session`:

```
session optional pam_umask.so
```

`pam_umask` can also read a per-user umask from `/etc/default/login` or respect a `UMASK` line inside a user's own login shell config, and on some distributions it takes precedence over `/etc/login.defs`'s value when both are present — which mechanism actually wins on a given host is distribution-specific and worth verifying directly (`pam_umask`'s man page, or empirically checking `umask` immediately after a fresh login) rather than assumed from one authoritative-sounding config file alone.

> 💡 **Tip:** For a fleet-wide security baseline, the layered reality is: kernel-level 666/777 requests (1) → PAM/`login.defs` system default umask (this section) → any per-user `~/.bashrc` override → any per-process/per-service override (`UMask=` in a systemd unit, an application's own explicit `chmod` after creation). An audit that only checks one layer (commonly just `/etc/login.defs`) can miss a per-user or per-service override that actually determines the real-world result on a specific host.

## 6. umask Combined with SGID Directories ([§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md))

[§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md) introduced the **SGID bit on a directory** — new files and subdirectories created inside it inherit the directory's owning group instead of the creating process's primary group, which solves the shared-team-directory group-ownership problem. umask and SGID solve two **different, complementary** problems, and shared/collaborative directories almost always need both configured correctly together:

- **SGID** controls **who the group owner of a new file becomes** (group inheritance).
- **umask** controls **what permission bits that new file gets** for owner/group/other (this section).

Neither one substitutes for the other. A directory with SGID set but a restrictive umask like `077` still produces files that no other group member can read or write — the group inherits correctly, but the permission bits lock everyone else out anyway, so the SGID inheritance accomplishes nothing practically:

```bash
$ chmod 2775 /srv/team-shared      # SGID + rwxrwxr-x
$ umask 077                        # overly restrictive — group bits get stripped on creation
$ touch /srv/team-shared/report.txt
$ ls -l /srv/team-shared/report.txt
-rw------- 1 alice team-shared 0 Jul 26 10:00 report.txt
```

Even though `report.txt` correctly inherited the `team-shared` group via SGID, `umask 077` stripped every group and other bit at creation time, so teammates in `team-shared` still can't read or write it. The correct pairing for a genuinely shared, group-collaborative directory is SGID **plus** a permissive-enough umask (commonly `002`, leaving group write intact):

```bash
$ umask 002                        # group keeps write; only other is restricted
$ touch /srv/team-shared/report.txt
$ ls -l /srv/team-shared/report.txt
-rw-rw-r-- 1 alice team-shared 0 Jul 26 10:00 report.txt
```

Now the file is both correctly group-owned (SGID) and correctly group-writable (umask `002`) — the combination that actually delivers "any team member can create and edit files here" rather than one half of it silently undermining the other.

> ⚠️ **Warning:** This interaction is a frequent root cause of "the SGID bit isn't working" tickets — SGID is working exactly as designed (group ownership is inheriting correctly), the umask is simply independently stripping the permission bits that would make that inherited group ownership actually useful. Always check both when troubleshooting a shared-directory collaboration problem, not just whichever one you set up more recently.

## 7. Common Misconceptions

1. **"umask sets the permissions a new file gets."** It doesn't set anything directly — it's a subtractive mask applied against the kernel/syscall's requested mode (666 for files, 777 for directories), per the AND-with-complement arithmetic in 2. umask can only remove bits that were requested in the first place; it can never add a bit, which is why umask alone can never make a newly `touch`ed file executable.
2. **"There's one umask for the whole system/user."** umask is a per-process attribute, inherited down the fork tree from whatever process created the file (4) — a cron job, a systemd service, and an interactive shell can all have different effective umasks on the very same host, even for the same user, depending on how each was started.
3. **"022 subtracted from 666 is 644 because 666 − 022 = 644."** The arithmetic coincidentally produces the right answer for this specific pair of values, which is exactly why it's a trap — umask is bitwise AND-with-complement, not decimal subtraction, and using decimal subtraction as a mental shortcut gives wrong answers for other umask/requested-mode combinations.
4. **"Setting SGID on a shared directory is enough for team collaboration."** SGID only handles group _ownership_ inheritance; umask independently controls the permission _bits_ a new file gets, and an overly restrictive umask (like `077`) can silently neutralize SGID's benefit by stripping group read/write anyway (6).
5. **"Changing umask in my shell changes permissions of files that already exist."** umask only affects files and directories created _after_ the change takes effect in that process — it has no retroactive effect on anything already on disk; existing files need an explicit `chmod` ([§27](./Section-27-Part4-Standard-Permission-Model.md)) to change.

## 8. Tiered Interview Questions

**🎯 Beginner:** _"With a umask of 022, what permissions does a newly created file get, and why not 666?"_
**Model answer:** New files are requested at 666 (`rw-rw-rw-`) by the process creating them, before any masking. umask 022 (`000 010 010` in binary) removes the write bit from group and other via a bitwise AND with the complement of the mask, leaving owner's `rw-` untouched but reducing group and other to `r--` each. The result is 644 (`rw-r--r--`) — never 666 in practice, because a nonzero umask is applied on essentially every real system specifically to prevent that.
_What the interviewer is probing for:_ Whether the candidate understands umask as subtractive against a starting request, not as the thing that directly assigns permissions.

**🎯 Intermediate:** _"Why do files created with the standard umask end up at 644 while directories end up at 755, using the same umask value?"_
**Model answer:** Because files and directories start from different requested modes at the syscall level — files request 666 (no execute, since a new file is data, not code), directories request 777 (they need the execute/traversal bit to be usable at all, per [§27](./Section-27-Part4-Standard-Permission-Model.md)'s directory-execute semantics). The same umask 022 subtracts the same relative bits (group and other write) from both, but since the starting points differ, the results differ too: 666 minus group/other write is 644; 777 minus group/other write is 755. It's one umask value producing two different, correct results because of two different requested-mode baselines, not two separate rules.
_What the interviewer is probing for:_ Understanding that the file-vs-directory difference originates before umask is even applied, not from umask treating files and directories differently.

**🎯 Senior:** _"A batch job running under cron is producing world-writable output files, but the engineer who owns the script insists their shell's umask is 027. How do you explain and diagnose this?"_
**Model answer:** umask is inherited per-process down the fork tree, and cron does not source the user's `~/.bashrc` — cron's own umask (often the system default, sometimes `022` or even `000` depending on distribution and how the crontab/service was configured) is what's actually in effect when the batch job runs, completely independent of whatever the engineer's interactive shell reports. Checking `umask` in an interactive terminal tells you nothing about the umask a detached, non-interactively-started process is running under. To diagnose, I'd check the umask inside the actual running job's context — `/proc/[pid]/status`'s `Umask` field while it's running, or explicitly setting `umask` as the first line of the cron script/crontab entry itself rather than relying on inherited shell configuration. The fix is to set umask explicitly within the job's own execution context (in the script, or via cron's environment, or a systemd `UMask=` directive if it's been converted to a timer unit per [§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)), not to assume interactive shell configuration propagates to background job execution.
_What the interviewer is probing for:_ Recognizing that umask inheritance follows the actual process tree, not user identity or shell config files, and knowing where to actually verify a running process's effective umask.

**🎯 Architect:** _"Design the umask and SGID strategy for a multi-team shared build-artifact filesystem where several service accounts and human engineers all need to read and write into the same directory tree without permission errors, but the tree must not be world-writable."_
**Model answer:** I'd set SGID ([§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md)) on every directory in the tree so new files and subdirectories inherit a shared group (say, `build-team`) regardless of which account creates them, rather than relying on each account's primary group matching. Separately, I'd standardize umask at `002` for every account that writes into this tree — human engineers via `/etc/profile.d/` or PAM's `pam_umask` (5) for interactive sessions, and each service account's launcher (systemd `UMask=` directive, or an explicit `umask 002` line at the top of any cron/batch script) for non-interactive ones, since umask doesn't propagate across those execution contexts automatically (4). That combination gives group read/write to every file, correct shared group ownership regardless of creator, and critically leaves `other` at read-only (or no access) so the tree is never world-writable. I'd explicitly avoid the shortcut of just using umask `000` or `002` with a permissive `other` bit as a substitute for proper group management — that would solve the immediate friction but create a genuinely world-writable tree, which is exactly the anti-pattern [§27](./Section-27-Part4-Standard-Permission-Model.md) flags with `chmod 777`. Finally, I'd periodically audit the tree for drift — files with unexpected permissions are usually evidence that something in the chain (a specific service's umask, a manual `chmod`, a misconfigured PAM setup) fell out of the standardized baseline, and that's worth catching via monitoring rather than discovering during an incident.
_What the interviewer is probing for:_ Ability to combine SGID and umask correctly as complementary mechanisms across heterogeneous process contexts (interactive, cron, systemd), and awareness that "make it permissive" and "make it correctly shared" are different goals that shouldn't be conflated.

## 9. Key Takeaways

- New files are requested at kernel/syscall level as 666 (`rw-rw-rw-`); new directories as 777 (`rwxrwxrwx`) — neither is the final permission; umask determines what actually survives.
- umask subtracts via bitwise AND with its own complement, not decimal subtraction — the shortcut coincidentally works for common values like `022` but isn't the actual mechanism, and using it as a mental model breaks on other values.
- The standard `umask 022` produces the familiar 644 (files) / 755 (directories) pairing directly from applying the same subtraction to two different requested-mode starting points.
- `umask` (per-shell, temporary) vs. `umask` set in `~/.bashrc` (per-user, persistent) vs. `/etc/profile`/`/etc/profile.d/` (system-wide, login shells) are three different persistence scopes — login vs. non-login shell context determines which startup file actually applies.
- umask is a per-process attribute inherited down the fork tree — there is no single system-wide umask in effect at all times; cron jobs, systemd services, and interactive shells can each have a different effective umask on the same host.
- `/etc/login.defs`'s `UMASK` directive and PAM's `pam_umask` module are the two system-wide mechanisms that set the umask new login sessions start with; which one wins is distribution-specific and worth verifying directly.
- SGID ([§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md)) and umask solve different problems — group-ownership inheritance vs. permission-bit assignment — and shared/collaborative directories need both configured correctly together, since a restrictive umask can silently neutralize SGID's benefit.

## 10. Related Concepts & What's Next

This section depends directly on [§27](./Section-27-Part4-Standard-Permission-Model.md)'s octal permission model (umask's arithmetic operates on the same `rwx`/owner-group-other structure) and on [§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md)'s SUID/SGID/sticky bit, whose interaction with umask in shared-directory scenarios (6) is one of the more commonly misdiagnosed permission issues in production. [§22](../Part3/Section-22-Part3-File-Metadata-Timestamps-Ownership-Attributes.md) touched on file creation via `touch` without going into what determines the resulting permissions — this section is that missing piece. [§30](./Section-30-Part4-Access-Control-Lists.md) (next) covers Access Control Lists, the mechanism reached for once umask's uniform, process-wide approach and the standard three-slot ownership model both fall short of expressing a more granular sharing requirement.

**Next Section:** [§30](./Section-30-Part4-Access-Control-Lists.md) — `Section-30-Part4-Access-Control-Lists.md`
