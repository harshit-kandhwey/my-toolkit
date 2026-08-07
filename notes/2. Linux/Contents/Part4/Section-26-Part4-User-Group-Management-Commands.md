# Section 26 (Part 4): User and Group Management Commands

## 1. From Files to Commands

[§25](./Section-25-Part4-Users-Groups-Passwd-Shadow-Group.md) covered `/etc/passwd`, `/etc/shadow`, and `/etc/group` as the raw data files that define every user and group on a system. This section covers the command layer that mutates those files correctly — with locking, validation, and the right side effects (home directory creation, mail spool setup, skeleton files) — rather than editing them by hand. Every command below is, at its core, a safe wrapper around exactly those three files (plus `/etc/gshadow` for group passwords); understanding [§25](./Section-25-Part4-Users-Groups-Passwd-Shadow-Group.md) first is what makes the flags in this section make sense rather than feel arbitrary.

> 💡 **Tip:** Never hand-edit `/etc/passwd`, `/etc/shadow`, or `/etc/group` directly with a text editor while the system is live — use `vipw` / `vipw -s` / `vigr` if a manual edit is ever genuinely necessary, since they lock the file and validate syntax on save. The commands in this section exist specifically to make manual edits unnecessary for routine work.

## 2. `useradd`: Creating Users

**Purpose:** Create a new user account by adding an entry to `/etc/passwd`, `/etc/shadow`, and (depending on configuration) `/etc/group`, optionally provisioning a home directory and shell.

**Syntax:**

```bash
useradd [OPTIONS] USERNAME
```

**Key flags:**

| Flag         | Meaning                                                                                     |
| ------------ | ------------------------------------------------------------------------------------------- |
| `-m`         | Create the home directory if it doesn't exist, populated from `/etc/skel`                   |
| `-d DIR`     | Specify a custom home directory path instead of the default `/home/USERNAME`                |
| `-s SHELL`   | Set the login shell (e.g., `/bin/bash`, `/usr/sbin/nologin` for service accounts)           |
| `-G LIST`    | Set supplementary groups (comma-separated) at creation time                                 |
| `-g GROUP`   | Set the primary group (by name or GID) instead of relying on `USERGROUPS_ENAB` defaults     |
| `-u UID`     | Specify an explicit UID instead of letting the system pick the next available one           |
| `-c COMMENT` | Set the GECOS comment field (often the full name)                                           |
| `-e DATE`    | Set an account expiration date (`YYYY-MM-DD`)                                               |
| `-r`         | Create a system account (UID from the system range, no aging, often no home dir by default) |

**Example usage and expected output:**

```bash
$ useradd -m -s /bin/bash -G sudo,docker -c "Jane Doe" jane
$ id jane
uid=1002(jane) gid=1002(jane) groups=1002(jane),27(sudo),999(docker)
```

**Production usage example:** Provisioning scripts for new engineering hires or CI service accounts almost always wrap `useradd -m -s /bin/bash -G ...` with a fixed set of supplementary groups so every account is created consistently — inconsistent ad hoc `useradd` invocations across a fleet are a common source of "why does this one host's account behave differently" tickets.

**Common errors:**

- Forgetting `-m` and being surprised the user has no home directory — on many distributions `useradd`'s raw defaults do **not** create a home directory automatically, unlike `adduser` below.
- Omitting `-s` and getting whatever the system default shell is (frequently `/bin/sh` or even no shell at all on minimal images), then wondering why an interactive login "doesn't work right."

**Troubleshooting:** If a newly created user can't log in interactively at all, check `-s` was set to a real shell and cross-check `/etc/shadow`'s password field isn't `!` or `*` (locked, [§25](./Section-25-Part4-Users-Groups-Passwd-Shadow-Group.md)) — `useradd` without `-p` or a following `passwd` call creates an account with no usable password by default.

### 2.1 `useradd` vs. `adduser`: Raw Tool vs. Debian Wrapper

`useradd` is the low-level tool present on essentially every distribution, and its **defaults are deliberately minimal** — no home directory, no interactive prompts, behavior governed by `/etc/login.defs` and `/etc/default/useradd`. On Debian/Ubuntu, `adduser` is a friendlier **Perl wrapper around `useradd`** that interactively prompts for a password and GECOS fields, creates the home directory by default, and generally does the "obviously right thing" without needing flags.

> ⚠️ **Warning:** Don't assume `useradd` and `adduser` are interchangeable across distributions or that either one's defaults match your mental model from the other system. Scripts intended to be portable should call `useradd` explicitly with every relevant flag spelled out (`-m`, `-s`, etc.) rather than relying on either tool's implicit defaults, since those defaults differ by distribution and by local `/etc/login.defs` configuration.

## 3. `usermod`: Modifying Existing Users

**Purpose:** Change an existing user's attributes — shell, home directory, group memberships, lock status — without recreating the account.

**Syntax:**

```bash
usermod [OPTIONS] USERNAME
```

**Key flags:**

| Flag         | Meaning                                                                                    |
| ------------ | ------------------------------------------------------------------------------------------ |
| `-aG LIST`   | **Append** to supplementary groups (comma-separated) — adds without removing existing ones |
| `-G LIST`    | **Replace** the entire supplementary group list with exactly what's given                  |
| `-s SHELL`   | Change the login shell                                                                     |
| `-d DIR -m`  | Change home directory and move existing contents to the new location                       |
| `-l NEWNAME` | Rename the login (username) — does not rename the home directory                           |
| `-L`         | Lock the account (prefixes the shadow password hash with `!`)                              |
| `-U`         | Unlock the account (removes the `!` prefix)                                                |
| `-e DATE`    | Set/change account expiration date                                                         |
| `-u UID`     | Change the UID (does not automatically `chown` existing files — see below)                 |

**Example usage and expected output:**

```bash
$ usermod -aG docker jane
$ groups jane
jane : jane sudo docker
```

**Production usage example:** Onboarding a user onto a new service (adding them to a `docker` or `wheel` group, [§31](./Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md)'s sudo coverage ties in directly here for `sudo`/`wheel`) is one of the single most common day-to-day admin actions on any fleet — and it's exactly where the `-aG` vs `-G` distinction below causes real incidents.

> ⚠️ **Warning: The single most common `usermod` mistake — `-G` silently drops every other group.** `usermod -G docker jane` does not _add_ `jane` to `docker`; it **replaces** her entire supplementary group list with just `docker`, silently removing her from `sudo`, `adm`, or any other group she previously belonged to. The fix is `usermod -aG docker jane` — `-a` ("append") tells `usermod` to add to the existing list rather than overwrite it. `-a` is meaningless without `-G` right next to it; there is no standalone "append" flag. This single missing character has locked engineers out of `sudo` access on live hosts more than once — always run `groups USERNAME` or `id USERNAME` before and after to confirm the change did what was intended.

**Common errors:**

- Running `usermod -G` alone (no `-a`) intending to add one group, and silently dropping every other supplementary group membership the account had.
- Using `-u` to change a UID and then wondering why the user's existing files under their home directory (or elsewhere) still show the _old_ UID as owner — `usermod -u` changes the account's UID going forward but does **not** retroactively `chown` files; that's a manual `find / -uid OLDUID -exec chown NEWUID {} +` step ([§27](./Section-27-Part4-Standard-Permission-Model.md) covers ownership mechanics in depth).

**Troubleshooting:** If a user reports they've lost `sudo` access after what should have been an unrelated group change, `groups USERNAME` is the first diagnostic step — a stray `-G` without `-a` is the leading suspect.

## 4. `userdel`: Removing Users

**Purpose:** Remove a user account from `/etc/passwd`, `/etc/shadow`, and group membership, optionally cleaning up the home directory and mail spool.

**Syntax:**

```bash
userdel [-r] [-f] USERNAME
```

**Key flags:**

| Flag | Meaning                                                                                          |
| ---- | ------------------------------------------------------------------------------------------------ |
| `-r` | Also remove the home directory and mail spool                                                    |
| `-f` | Force removal even if the user is currently logged in or owns files elsewhere (use with caution) |

**Example usage:**

```bash
$ userdel -r jane
```

Without `-r`, `userdel jane` removes the account entries but leaves `/home/jane` (and its contents) in place on disk, now owned by a UID that no longer resolves to any username — an orphaned-ownership situation identical in shape to the `usermod -u` gotcha above.

> ⚠️ **Warning:** `userdel -r` is irreversible and deletes the entire home directory tree — there's no confirmation prompt. Before offboarding an account, confirm whether the home directory needs to be archived (`tar`/`rsync` to cold storage) first; deleting it as part of account removal and needing it back a week later is a recurring, avoidable incident.

**Common errors:**

- Forgetting `-r` and assuming the account is fully gone — orphaned home directories accumulate silently across a fleet's lifetime and are a common finding in security audits.
- Attempting to `userdel` a user who is currently logged in or has running processes — this fails without `-f`, which is usually the correct behavior (it's telling you to check what's still using that account first, not an obstacle to force past reflexively).

## 5. `groupadd`, `groupdel`, `gpasswd`: Group Management

**Purpose:** Create, remove, and manage membership/passwords for groups independently of any single user.

**Syntax:**

```bash
groupadd [-g GID] [-r] GROUPNAME
groupdel GROUPNAME
gpasswd [-a USER | -d USER] GROUPNAME
```

**Key flags:**

| Command    | Flag       | Meaning                                                       |
| ---------- | ---------- | ------------------------------------------------------------- |
| `groupadd` | `-g GID`   | Specify an explicit GID instead of the next available one     |
| `groupadd` | `-r`       | Create a system group (GID from the system range)             |
| `gpasswd`  | `-a USER`  | Add `USER` to the group (equivalent effect to `usermod -aG`)  |
| `gpasswd`  | `-d USER`  | Remove `USER` from the group                                  |
| `gpasswd`  | (no flags) | Set/change the group's own password (rarely used in practice) |

**Example usage:**

```bash
$ groupadd -g 3000 deployers
$ gpasswd -a jane deployers
Adding user jane to group deployers
$ gpasswd -d jane deployers
Removing user jane from group deployers
```

**Common errors:**

- Running `groupdel` on a group that is still some user's **primary** group — this fails, and rightly so, since that user would be left with a dangling primary GID; the primary group must be reassigned first (`usermod -g`).

**Troubleshooting:** `gpasswd -a`/`-d` is often more convenient than `usermod -aG` for a single group-membership change since it operates on one group at a time without needing to know or restate the user's full existing group list.

## 6. `passwd`: Password Management

**Purpose:** Set or change a user's password, and manage basic account lock state.

**Syntax:**

```bash
passwd [OPTIONS] [USERNAME]
```

**Key flags:**

| Flag       | Meaning                                                                  |
| ---------- | ------------------------------------------------------------------------ |
| (no flags) | Change your own password (interactive prompt)                            |
| `USERNAME` | As root, change another user's password                                  |
| `-l`       | Lock the account (same shadow-file effect as `usermod -L`)               |
| `-u`       | Unlock the account                                                       |
| `-e`       | Expire the password immediately, forcing a change at next login          |
| `-S`       | Show a short status summary (locked/unlocked, password-set state, aging) |

**Example usage and expected output:**

```bash
$ passwd -S jane
jane P 2026-06-01 0 90 7 -
```

**Production usage example:** `passwd -l` is a fast, reversible way to suspend an account (e.g., during an offboarding investigation, or a suspected credential compromise) without deleting it — reversible via `passwd -u`, unlike `userdel`.

> 💡 **Tip:** `passwd -l` and `usermod -L` do the same underlying thing (prepend `!` to the shadow hash) — either is fine; teams typically standardize on one for consistency in runbooks.

### 6.1 Password Aging with `chage`

**Purpose:** View and set password aging policy — expiration, warning period, minimum/maximum age between changes — the same fields `passwd -S` summarizes, in full detail.

**Syntax:**

```bash
chage [OPTIONS] USERNAME
chage -l USERNAME
```

**Key flags:**

| Flag      | Meaning                                                            |
| --------- | ------------------------------------------------------------------ |
| `-l`      | List current aging settings for the user                           |
| `-M DAYS` | Maximum days before a password change is required                  |
| `-m DAYS` | Minimum days that must pass before a password can be changed again |
| `-W DAYS` | Warning period (days before expiration) shown at login             |
| `-E DATE` | Account expiration date                                            |
| `-d DATE` | Set the last-password-change date manually                         |

**Example usage:**

```bash
$ chage -M 90 -W 7 jane
$ chage -l jane
Last password change                                   : Jun 01, 2026
Password expires                                       : Aug 30, 2026
Password inactive                                       : never
Account expires                                          : never
```

**Production usage example:** `chage -M 90` enforced fleet-wide is a common, concrete implementation of a "passwords must rotate every 90 days" compliance requirement ([§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md)'s CIS Benchmark coverage, Part 12, formalizes this kind of policy at the audit level).

## 7. Identity Inspection: `id`, `whoami`, `groups`

**Purpose:** Answer "who am I / who is this user, and what groups do they belong to" — read-only commands used constantly for verification after any of the mutating commands above.

**Syntax:**

```bash
id [USERNAME]
whoami
groups [USERNAME]
```

**Example usage and expected output:**

```bash
$ id jane
uid=1002(jane) gid=1002(jane) groups=1002(jane),27(sudo),999(docker)
$ whoami
jane
$ groups jane
jane : jane sudo docker
```

`id` with no argument reports the current shell's identity, which is subtly different from `whoami` in one edge case worth knowing: under `sudo` ([§31](./Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md)), `whoami` reports the **effective** user (e.g., `root`), while `id` shows both real and effective UID/GID together when they differ — making `id` the more complete diagnostic when investigating a privilege-related issue.

> 💡 **Tip:** After any `usermod -aG`/`-G`, `gpasswd -a`/`-d`, or lock/unlock change, run `id USERNAME` (or have the affected user log out and back in, since group membership is generally read at login time, not live) as the standard verification step — this is the direct antidote to the `-aG` vs `-G` gotcha covered in the `usermod` section above.

## 8. `su` vs. `su -`: Switching Users

**Purpose:** Start a shell as a different user, most commonly root.

**Syntax:**

```bash
su [USERNAME]
su - [USERNAME]
```

**Key distinction:**

| Form        | Behavior                                                                                                                                                   |
| ----------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `su jane`   | Switches to `jane`'s UID/GID but **keeps the current shell's environment** — working directory, `$PATH`, etc.                                              |
| `su - jane` | A full **login shell** — resets the environment as if `jane` had logged in fresh (`$HOME`, `$PATH`, shell rc files, working directory all become `jane`'s) |

**Example usage:**

```bash
$ su - deploy
Password:
deploy@host:~$ pwd
/home/deploy
```

> ⚠️ **Warning:** Plain `su jane` (no dash) is a common source of "it works when I `su` in but breaks in a real login" confusion — inherited environment variables (especially `$PATH`, which may still contain directories relevant to the switching-_from_ user but not the target) can cause scripts or tools to behave differently than they would under a genuine login. Default to `su -` unless there's a specific reason to preserve the calling shell's environment.

`su` with no username at all defaults to switching to root. Note that `su` still exists and works even on hosts where `sudo` ([§31](./Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md)) is the primary day-to-day privilege-escalation mechanism — `su -` is what most `sudo` configurations effectively wrap when an admin runs `sudo -i` or `sudo su -`.

## 9. Command Reference Table

| Command       | Purpose                                           | Key flags                                         | Destructive?                               |
| ------------- | ------------------------------------------------- | ------------------------------------------------- | ------------------------------------------ |
| `useradd`     | Create a user                                     | `-m -s -G -u -d -c -e -r`                         | No                                         |
| `usermod`     | Modify a user                                     | `-aG` (append), `-G` (replace!), `-s -L -U -l -e` | Yes if `-G` used carelessly                |
| `userdel`     | Remove a user                                     | `-r` (remove home), `-f` (force)                  | **Yes with `-r` — irreversible**           |
| `groupadd`    | Create a group                                    | `-g -r`                                           | No                                         |
| `groupdel`    | Remove a group                                    | (none common)                                     | Yes (fails safely if it's a primary group) |
| `gpasswd`     | Manage group membership/password                  | `-a -d`                                           | No (reversible)                            |
| `passwd`      | Set/change password, lock/unlock                  | `-l -u -e -S`                                     | Low (lock is reversible)                   |
| `chage`       | Password aging policy                             | `-l -M -m -W -E`                                  | No                                         |
| `id`          | Show UID/GID/groups                               | (none)                                            | No (read-only)                             |
| `whoami`      | Show effective username                           | (none)                                            | No (read-only)                             |
| `groups`      | Show group memberships                            | (none)                                            | No (read-only)                             |
| `su` / `su -` | Switch user (with/without full login environment) | `-` (login shell)                                 | No                                         |

## 10. A Note on systemd-homed

Part 9 ([§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)–[§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md)) covers systemd in depth, but it's worth flagging here that modern systemd-based distributions increasingly offer **`systemd-homed`** (managed via `homectl`) as an alternative to the classic `/etc/passwd`+`useradd` model — it stores user records (including, optionally, encrypted home directories) in a more self-contained, portable format rather than flat files split across `passwd`/`shadow`/`group`. It is **not** yet the default on most production server distributions, and the commands in this section remain the standard, portable baseline every Linux admin needs regardless of whether a given host also has `homectl` available. Treat `systemd-homed` as an alternative worth recognizing by name, not as something to substitute for this section's commands in day-to-day work.

## 11. Common Misconceptions

1. **"`usermod -G group` adds the user to `group`."** It **replaces** the entire supplementary group list with whatever is given — the classic incident-causing mistake covered in depth in the `usermod` section above. `-aG` is the append form; `-G` alone is destructive to existing memberships.
2. **"`useradd` and `adduser` are just two names for the same command."** `useradd` is the low-level, minimal-defaults tool present everywhere; `adduser` (Debian/Ubuntu) is a friendlier interactive wrapper around it with different defaults (home directory creation, prompts). Scripts intended to be portable should call `useradd` with explicit flags rather than assume either tool's defaults, as the `useradd` vs. `adduser` comparison above covers.
3. **"`userdel` without `-r` fully removes a user."** It removes the account entries but leaves the home directory and mail spool on disk, now owned by an orphaned UID — a common source of stale data found in later audits, per the `userdel` section above.
4. **"`su jane` and `su - jane` are basically equivalent."** They differ in environment — `su -` is a full login shell resetting `$HOME`, `$PATH`, and working directory to the target user's; plain `su` keeps the calling shell's environment, which can cause tools to behave inconsistently versus a genuine login, as the `su` vs. `su -` section above covers.
5. **"Changing a UID with `usermod -u` updates file ownership automatically."** It changes the account's UID going forward only — existing files on disk still reference the old numeric UID and need an explicit `find ... -exec chown` pass to be reconciled, per the `usermod` section above.

## 12. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `useradd -m` and plain `useradd`?"_
**Model answer:** `useradd`'s raw defaults on most distributions do not create a home directory — `-m` tells it to create one, populated from `/etc/skel`. Without `-m`, the account exists in `/etc/passwd` and `/etc/shadow` but has no home directory on disk, which typically breaks anything expecting `$HOME` to exist (shell rc files, default working directory at login).
_What the interviewer is probing for:_ Awareness that `useradd`'s defaults are intentionally minimal, not "do the obviously right thing" — a common gap for people who've only used `adduser`.

**🎯 Intermediate:** _"A colleague ran `usermod -G docker alice` to add her to the docker group, and now she can't `sudo` anymore. What happened?"_
**Model answer:** `-G` without `-a` replaces the entire supplementary group list rather than appending to it — so `alice` was removed from `sudo` (and every other group she was in) at the same moment she was added to `docker`. The fix going forward is `usermod -aG docker alice`, and the immediate remediation is to restore her previous group list (`sudo`, and whatever else `id alice` or an audit log shows she had before) via either `usermod -aG` for each missing group or `gpasswd -a`. I'd verify with `id alice` before considering it resolved.
_What the interviewer is probing for:_ Direct, specific knowledge of this exact gotcha, plus a concrete remediation path rather than just naming the cause.

**🎯 Senior:** _"You're auditing a fleet and find several home directories under `/home` owned by numeric UIDs with no corresponding username in `/etc/passwd`. How did that likely happen, and what's your remediation?"_
**Model answer:** Most likely `userdel` was run without `-r` at some point, removing the account entries from `/etc/passwd`/`/etc/shadow` but leaving the home directory (and its ownership metadata) on disk — the numeric UID no longer resolves to a name because nothing in `/etc/passwd` claims it anymore. It's also possible a UID was reused by a later `useradd` for a different person without reconciling old files, though that's less common. Remediation: confirm via backups/change logs whether the data is still needed; if not, archive it to cold storage and clean it up; if the UID needs to be reactivated under a new account, `useradd -u OLDUID` recreates the account at the same UID so the existing files become valid again without a mass `chown`. Going forward, I'd standardize offboarding on `userdel -r` (after confirming any needed archival happens first) specifically to prevent this class of orphaned-ownership finding from recurring.
_What the interviewer is probing for:_ Connecting a filesystem-level symptom back to the specific command behavior that caused it, and proposing both a one-time fix and a process change to prevent recurrence.

**🎯 Architect:** _"Design the account-lifecycle conventions (onboarding, group changes, offboarding) for a fleet managed partly by hand and partly by automation. What do you standardize on?"_
**Model answer:** For onboarding, I'd standardize on explicit `useradd` invocations with every relevant flag spelled out (`-m -s -G -c`) rather than relying on `adduser` or distribution defaults, so provisioning behaves identically regardless of which distro a given host runs — and I'd wrap it in a shared script or Ansible role rather than trusting ad hoc manual commands. For group changes, I'd ban bare `usermod -G` from runbooks and automation entirely in favor of `usermod -aG` or `gpasswd -a`/`-d`, specifically because the `-G` replace-vs-append distinction is a proven, recurring source of accidental privilege loss — and I'd require `id USERNAME` output attached to any change ticket as before/after verification. For offboarding, I'd require an explicit decision point on whether the home directory needs archival before `userdel -r` runs, rather than defaulting either to "always keep" (accumulating orphaned data indefinitely) or "always delete" (risking irrecoverable loss) — and I'd prefer `passwd -l`/`usermod -L` as an immediate, reversible suspension step ahead of full `userdel`, giving an investigation window before the irreversible step. I'd also periodically audit for orphaned-UID home directories as a standing fleet health check, since that finding reliably indicates a skipped `-r` somewhere in the process.
_What the interviewer is probing for:_ Systems-level process design that closes off the specific failure modes covered in this section (the `-G` gotcha, orphaned home directories) by convention and tooling, not just individually correct command usage.

## 13. Key Takeaways

- `useradd` is the low-level, minimal-defaults account-creation tool; `adduser` (Debian/Ubuntu) is a friendlier interactive wrapper with different defaults — don't assume either's behavior when scripting portably, per the `useradd`/`adduser` sections above.
- `usermod -aG` **appends** to supplementary groups; `usermod -G` **replaces** the entire list — this is the single most consequential command distinction in this section, and the direct cause of a recurring class of accidental-lockout incidents, covered in the `usermod` section above.
- `userdel` needs `-r` to remove the home directory and mail spool along with the account; without it, orphaned, numerically-owned data accumulates silently on disk, as the `userdel` section above covers.
- `groupadd`/`groupdel`/`gpasswd` manage groups and membership independently of `usermod`, and `groupdel` correctly refuses to remove a group that's still someone's primary group.
- `passwd -l`/`-u` and `chage` cover account locking and password-aging policy — `passwd -S` and `chage -l` are the fast status-check commands.
- `id`, `whoami`, and `groups` are the read-only verification trio to run after any mutating command — especially after any group-membership change, given the `-aG`/`-G` gotcha.
- `su -` gives a full login-shell environment reset; plain `su` inherits the calling shell's environment, which can produce subtly different behavior than a genuine login, per the `su` vs. `su -` section above.

## 14. Related Concepts & What's Next

This section is the command-layer counterpart to [§25](./Section-25-Part4-Users-Groups-Passwd-Shadow-Group.md)'s `/etc/passwd`/`/etc/shadow`/`/etc/group` file formats — every command here ultimately just edits those files safely. [§27](./Section-27-Part4-Standard-Permission-Model.md) (next) covers the standard `rwx` permission model (`chmod`, `chown`, `chgrp`) that determines what a user or group created here can actually do to files. [§31](./Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md)'s sudo/privilege-escalation coverage depends directly on the `usermod -aG sudo`/`wheel` pattern shown in the `usermod` section above. Part 9's systemd coverage ([§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)–[§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md)) is where `systemd-homed`/`homectl`, briefly flagged in the systemd-homed note above as a modern alternative, would be covered in operational depth if a given fleet adopts it.

**Next Section:** [§27](./Section-27-Part4-Standard-Permission-Model.md) — `Section-27-Part4-Standard-Permission-Model.md`
