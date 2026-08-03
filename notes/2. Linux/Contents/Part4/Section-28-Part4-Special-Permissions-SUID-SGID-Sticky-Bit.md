# Section 28 (Part 4): Special Permissions: SUID, SGID, Sticky Bit

## 1. The Problem the Standard Model Can't Solve

§27 covered the standard `rwx` permission model — owner, group, other — and how it always evaluates permissions using the identity of the process that's **running** a file, not any property of the file's owner. That model has a gap: sometimes a program legitimately needs to do something the invoking user isn't allowed to do directly. The canonical example is changing your own password — `/etc/shadow`, which holds password hashes, is (and must be) unreadable and unwritable by ordinary users, yet every ordinary user needs a way to change their own entry in it.

Standard permissions offer no way to say "any user can run this program, but while it runs, treat it as if root were running it." That's exactly the gap the three **special permission bits** — SUID, SGID, and the sticky bit — exist to fill. They sit on top of the standard model from §27, not instead of it: a file always has both its normal `rwx` bits and, optionally, one of these special bits layered on.

> 💡 **Tip:** All three special bits answer a version of the same question — "should this file or directory behave differently than the standard owner/group/other model would predict?" — but each answers it in a genuinely different way. Don't try to memorize them as one concept with three flavors; SUID and SGID-on-files are about **who a process runs as**, SGID-on-directories is about **inheritance**, and the sticky bit is about **deletion rights**. Keep the mechanisms separate.

## 2. SUID (Set User ID): Run as the File's Owner

When the **SUID** bit is set on an executable file, any user who runs that file starts a process running with the **effective UID of the file's owner**, not the UID of the user who invoked it. This is a genuine privilege transfer — the kernel makes the decision at `exec()` time, not something the program itself has to request.

**The canonical example: `/usr/bin/passwd`.**

```bash
$ ls -l /usr/bin/passwd
-rwsr-xr-x 1 root root 68208 Jan 10  2026 /usr/bin/passwd
```

`passwd` is owned by `root` and has the SUID bit set (the `s` in the owner's execute position). When an ordinary user runs `passwd` to change their own password, the resulting process runs with `root`'s effective UID for as long as it executes — which is exactly what lets it write to `/etc/shadow`, a file the invoking user has no direct permission to touch. Once `passwd` exits, the privilege is gone; it never persists beyond that one process's lifetime.

**Setting SUID:**

```bash
chmod u+s file          # symbolic
chmod 4755 file          # octal — leading 4 is the SUID bit
```

**Important mechanical detail:** SUID has no effect on a **directory** — it's meaningful only on executable files. Setting it on a directory is either silently ignored in practice or simply doesn't do what a naive reading of "set owner ID" might suggest; the behavior that matters for directories belongs to SGID, covered in the SGID-on-a-directory section below, not SUID.

> ⚠️ **Warning:** A SUID-root binary is one of the highest-value targets an attacker can find on a compromised host — any exploitable bug in that binary (buffer overflow, unsafe environment-variable handling, a shell escape, a symlink race) potentially hands the attacker root, because the process was already running with root's effective UID before the bug was ever triggered. This is why hardening guidance is consistently "minimize the SUID-root inventory," not "audit it occasionally" — every SUID-root binary is permanent, standing attack surface, not a one-time review item. §89–§96 (Part 12) cover the broader security-hardening posture this feeds into.

## 3. SGID (Set Group ID): Two Different Behaviors

SGID is the one special bit that means something genuinely different depending on whether it's set on a **file** or a **directory** — these are not the same behavior described twice, and conflating them is the most common SGID mistake.

### 3.1 SGID on a File: Run as the File's Group

Set on an executable file, SGID works exactly like SUID but for the **group**, not the owner: the resulting process runs with the effective GID of the file's owning group, regardless of the invoking user's own group memberships.

```bash
$ ls -l /usr/bin/wall
-rwxr-sr-x 1 root tty 35000 Jan 10  2026 /usr/bin/wall
```

The `s` in the group execute position marks SGID. `wall` (broadcasts a message to every logged-in terminal) needs group `tty` privileges to write to other users' terminal devices — SGID grants that for the duration of the process, the same mechanism as SUID, just scoped to the group identity instead of the owner identity.

### 3.2 SGID on a Directory: New Files Inherit the Directory's Group

This is the behavior that actually matters most in day-to-day system administration, and it's a **different mechanism entirely** from SGID-on-a-file above — not a process-privilege transfer at all. When SGID is set on a **directory**, any new file or subdirectory created inside it automatically inherits that directory's **group ownership**, rather than the creating user's primary group (which is the standard-model default §27 established).

```bash
$ mkdir /srv/teamshare
$ chgrp devteam /srv/teamshare
$ chmod g+s /srv/teamshare
$ ls -ld /srv/teamshare
drwxr-sr-x 2 root devteam 4096 Jul 26 09:00 /srv/teamshare
```

Any file `alice` or `bob` creates inside `/srv/teamshare` is now automatically group-owned by `devteam`, regardless of their own primary group — solving a real, common problem: a shared team directory where multiple users with different primary groups need every file they drop in to be readable/writable by the whole team without everyone manually `chgrp`-ing after every file creation. Newly created subdirectories also inherit the SGID bit itself, so the behavior propagates down the tree without having to re-apply it at every level.

**Setting SGID:**

```bash
chmod g+s file_or_dir     # symbolic
chmod 2755 file_or_dir     # octal — leading 2 is the SGID bit
```

**Production usage example:** Shared project directories (`/srv/<team>/`, a shared `www-data` upload directory, a build artifact drop shared between a CI service account and human operators) routinely combine SGID with a permissive group `rwx` and a restrictive `other`, so the whole team can read/write each other's files without loosening permissions to world-writable — SGID-on-directory is the standard, correct tool for this, not a workaround.

## 4. The Sticky Bit: Restricting Deletion, Not Execution

The sticky bit has a name that reflects history it no longer carries — on very old Unix systems, setting it on an executable told the kernel to keep the program's text segment resident in swap after exit, speeding up subsequent runs. That meaning is **obsolete** on modern Linux; the kernel's memory management makes it irrelevant. On modern Linux, the sticky bit has exactly **one** meaningful use: set on a **directory**, it restricts file deletion inside that directory so that only the **file's owner** (or the directory's owner, or root) can remove or rename a file — even if other users have write permission on the directory itself.

This matters because, under the standard model alone, **write permission on a directory** is what controls whether you can delete files inside it — not permissions on the file being deleted. A world-writable directory without the sticky bit would let any user delete or rename _any other user's_ files in it, which is obviously unacceptable for a shared, world-writable location.

**The canonical example: `/tmp`.**

```bash
$ ls -ld /tmp
drwxrwxrwt 12 root root 4096 Jul 26 09:00 /tmp
```

The trailing `t` shows `/tmp` is world-writable (any user can create files there) but sticky — so `alice` can create files in `/tmp` freely, and `bob` can too, but `bob` cannot delete or rename `alice`'s files even though he has write access to the directory itself. Without the sticky bit, `/tmp` being world-writable would make it trivial for any local user to delete or tamper with any other user's temporary files.

**Setting the sticky bit:**

```bash
chmod +t dir       # symbolic
chmod 1777 dir      # octal — leading 1 is the sticky bit
```

## 5. Notation: Symbolic and Octal, and the Capital-vs-Lowercase Rule

**Symbolic notation** adds the special bits with `u+s` (SUID), `g+s` (SGID), and `+t` or `o+t` (sticky bit) — layered on top of the same `chmod` symbolic syntax §27 introduced for `rwx`.

**Octal notation** uses a **fourth leading digit** in front of the familiar three-digit `rwx` octal value, itself a sum of bit values:

| Special bit | Octal value |
| ----------- | ----------- |
| SUID        | 4           |
| SGID        | 2           |
| Sticky bit  | 1           |

```bash
chmod 4755 /usr/local/bin/tool     # SUID + rwxr-xr-x
chmod 2775 /srv/teamshare          # SGID + rwxrwxr-x
chmod 1777 /tmp                    # sticky + rwxrwxrwx
chmod 6750 file                    # SUID + SGID (4+2) + rwxr-x---
```

**Capital vs. lowercase in `ls -l` output — this distinction is a real, frequently-tested signal, not cosmetic:** the special-bit character occupies the same column position as the corresponding **execute** bit. Whether `ls` shows it lowercase or uppercase tells you whether the underlying execute bit is _also_ set:

| Position       | Execute bit set | Execute bit NOT set |
| -------------- | --------------- | ------------------- |
| Owner (SUID)   | `s` (lowercase) | `S` (uppercase)     |
| Group (SGID)   | `s` (lowercase) | `S` (uppercase)     |
| Other (sticky) | `t` (lowercase) | `T` (uppercase)     |

An **uppercase** `S` or `T` is a strong signal something is misconfigured or at least unusual: SUID/SGID without execute permission means the special bit can never actually take effect (there's no process to run with elevated privilege — the file can't be executed at all by the relevant class), and it's frequently a leftover from a `chmod` applied before execute permissions were set, rather than an intentional configuration. Seeing `-rwSr--r--` should prompt a "why is this here" question, not a shrug.

## 6. Auditing SUID/SGID Binaries System-Wide

Because every SUID-root binary is standing attack surface, as the SUID section above covers, a real, recurring security-hardening task — not a one-off — is enumerating exactly which binaries on a host carry these bits, so the inventory can be reviewed against what's actually expected for that host's role.

```bash
find / -xdev -perm -4000 -type f 2>/dev/null    # SUID binaries
find / -xdev -perm -2000 -type f 2>/dev/null    # SGID binaries
find / -xdev -perm -6000 -type f 2>/dev/null    # both SUID and SGID
```

**Key flags:**

| Flag          | Meaning                                                                                        |
| ------------- | ---------------------------------------------------------------------------------------------- |
| `-perm -4000` | Match files where the SUID bit is set (the leading `-` means "at least these bits," not exact) |
| `-xdev`       | Don't cross filesystem/mount boundaries — keeps the search scoped to the intended filesystem   |
| `2>/dev/null` | Suppress permission-denied noise from directories the invoking user can't traverse             |

**Production usage example:** A CIS-benchmark-style hardening pass (§96 references compliance frameworks at the concept level) typically runs this `find` sweep against a known-good baseline list for the distribution and flags any SUID/SGID binary that isn't on that expected list — a new, unexpected SUID-root binary appearing after a package install, a manual build, or (worst case) a compromise is exactly the kind of drift this audit exists to catch. Binaries not actually needed for the host's role are frequently hardened by stripping the SUID bit outright (`chmod u-s`) rather than removing the binary, preserving functionality for an admin who explicitly elevates via `sudo` while removing the always-on privilege escalation surface for every other user.

## 7. Common Misconceptions

1. **"SGID is basically SUID for groups — same behavior, different identity."** True only for SGID-on-files, covered above. SGID-on-directories, covered just after it, is a completely different mechanism — group inheritance for newly created files — with no SUID analog at all. Treating SGID as "just SUID with group instead of owner" misses its most commonly used behavior in real system administration.
2. **"The sticky bit keeps programs faster by pinning them in swap."** That was its original historical meaning; it's obsolete on modern Linux kernels. Its only meaningful modern use is the directory-deletion restriction, per the sticky-bit section above — if someone mentions the swap-pinning behavior as current, they're describing 1990s Unix, not a production Linux host today.
3. **"An uppercase `S` or `T` in `ls -l` is just a stylistic variant of lowercase."** It's a distinct, meaningful signal — it means the execute bit underlying that position is absent, so the special bit as set currently has no effect. It's frequently a configuration mistake worth investigating, not a cosmetic detail, as the notation section above covers.
4. **"SUID/SGID bits are dangerous, so they should never be used."** They're a necessary, standard mechanism — `passwd`, `sudo` itself in some implementations, `wall`, `ping` on some distributions, and countless legitimate shared-directory setups depend on them. The actual operational discipline isn't "avoid special bits" — it's "keep the SUID-root inventory minimal and audited," per the SUID and auditing sections above, which is a very different, more nuanced posture than blanket avoidance.

## 8. Tiered Interview Questions

**🎯 Beginner:** _"What does the SUID bit do, and what's the classic example of why it's needed?"_
**Model answer:** SUID makes a process run with the effective UID of the file's owner rather than the user who invoked it. The classic example is `/usr/bin/passwd`, owned by root with SUID set — any user needs to be able to run `passwd` to change their own password, which requires writing to `/etc/shadow`, a file ordinary users can't touch directly. SUID lets the `passwd` process temporarily run as root for exactly that purpose, and the elevated privilege ends when the process exits.
_What the interviewer is probing for:_ Understanding that SUID is a per-process privilege transfer at `exec()` time, not a permanent change to the invoking user's rights.

**🎯 Intermediate:** _"What's the difference between SGID on a file versus SGID on a directory?"_
**Model answer:** SGID on an executable file works like SUID but for the group — the process runs with the effective GID of the file's owning group instead of the owner's UID. SGID on a directory is a completely different behavior: any new file or subdirectory created inside it automatically inherits the directory's group ownership instead of the creating user's primary group, and the SGID bit itself propagates to new subdirectories. The directory behavior is the one used constantly in practice, for shared team directories where multiple users with different primary groups need everything they create to end up group-owned consistently.
_What the interviewer is probing for:_ Recognizing these as genuinely different mechanisms sharing one bit, not one behavior described two ways.

**🎯 Senior:** _"You find a binary with permissions `-rwsr-xr-x` owned by root that isn't a standard distribution package. What's your response?"_
**Model answer:** That's a SUID-root binary outside the expected baseline, which is exactly the pattern a SUID/SGID audit (`find / -xdev -perm -4000`) exists to catch — any code path in it that has an exploitable bug hands an attacker root, because the process already runs with root's effective UID before any vulnerability is even triggered. I'd first determine whether it's legitimate — check if it belongs to a known, intentionally-installed package, review who put it there and when, and compare against the host's expected baseline for its role. If it isn't clearly justified, I'd treat it as a potential compromise indicator worth escalating, not just a permissions cleanup — an unexplained new SUID-root binary is a classic post-exploitation persistence technique. If it turns out legitimate but unnecessary for this host's role, I'd strip the SUID bit (`chmod u-s`) rather than deleting the binary outright, preserving functionality behind explicit `sudo` elevation while removing the always-on attack surface.
_What the interviewer is probing for:_ Treating unexpected SUID-root binaries as a security event with an investigation path, not just a permissions oddity to quietly fix.

**🎯 Architect:** _"Design the shared-directory permission scheme for a team of 15 engineers who all need to read and write each other's files in `/srv/build-artifacts`, without loosening things to world-writable."_
**Model answer:** I'd create a dedicated group (say `builders`), add all 15 engineers to it, and set the directory group-owned by `builders` with `chmod 2775` — SGID plus `rwxrwxr-x`. The SGID bit means every file any engineer creates in there is automatically group-owned by `builders` regardless of that engineer's own primary group, so nobody has to remember to `chgrp` after creating a file, and nothing ever silently ends up owned by a group other engineers can't write to. I'd also consider layering the sticky bit if there's any risk of one engineer's files getting deleted by another engineer's script or automation running under a different identity, though within a single trusted team that's less critical than in a fully world-writable location like `/tmp`. I'd explicitly avoid making the directory world-writable — group-based access via SGID inheritance covers the actual requirement without exposing the directory to every user on the host. For a case needing finer-grained control than one group can express (e.g., some engineers read-only, others read-write), I'd reach for ACLs (§30) layered on top of this base rather than trying to force the standard/special-bit model to express it.
_What the interviewer is probing for:_ Correctly reaching for SGID-on-directory as the standard tool for this exact problem, and recognizing when the requirement outgrows what SGID alone can express.

## 9. Key Takeaways

- SUID makes a process run with the effective UID of the file's **owner**, not the invoking user — the canonical example is `/usr/bin/passwd` needing root's rights to write `/etc/shadow`; the privilege exists only for the process's lifetime.
- SGID on a **file** does the same thing for the group; SGID on a **directory** is an entirely different mechanism — new files/subdirectories inherit the directory's group automatically, the standard, correct pattern for shared team directories.
- The sticky bit's historical swap-pinning meaning is obsolete; its only modern use is on directories (`/tmp` being the canonical case) — it restricts deletion/renaming to the file's owner even when others have directory write access.
- Symbolic notation: `u+s`, `g+s`, `+t`. Octal notation: a fourth leading digit (4=SUID, 2=SGID, 1=sticky) in front of the standard three-digit `rwx` value.
- Uppercase `S`/`T` versus lowercase `s`/`t` in `ls -l` output signals whether the underlying execute bit is present — uppercase means the special bit is set but currently inert, often a misconfiguration worth investigating.
- Every SUID-root binary is permanent standing attack surface, not a one-time review item — `find / -xdev -perm -4000` (and `-2000` for SGID) against a known-good baseline is the standard audit, with unexpected findings treated as a potential security event.

## 10. Related Concepts & What's Next

This section builds directly on §27's standard `rwx`/owner-group-other model — every special bit here layers on top of that model rather than replacing it. §29 (next) covers `umask` and default permissions, which determines the baseline permissions new files get before any special bits are ever considered. §89–§96 (Part 12, security hardening) is where the SUID-root audit introduced in the auditing section above becomes an operational, recurring practice — CIS benchmark baselines, compliance scanning, and the broader threat model special bits contribute to. §30's ACLs are the tool to reach for when SGID-on-directory's single-group model isn't expressive enough for a real access-control requirement.

**Next Section:** §29 — `Section-29-Part4-umask-and-Default-Permissions.md`
