# Section 25 (Part 4): Users and Groups: /etc/passwd, /etc/shadow, /etc/group

## 1. Why Three Separate Files

Linux identity and authentication is spread across three plain-text files, each with a distinct job: `/etc/passwd` answers "who is this user, and where does their environment live" ([§22](../Part3/Section-22-Part3-File-Metadata-Timestamps-Ownership-Attributes.md) covered UID/GID as the numbers the kernel actually enforces ownership against — this section is where those numbers get a name and a story). `/etc/shadow` answers "how is this user's password verified, and what are the aging rules around it." `/etc/group` answers "what groups exist, and who's in them beyond their primary group." A fourth, `/etc/gshadow`, does for group passwords roughly what `/etc/shadow` does for user passwords, though it's rarely exercised in practice, as the brief note on it below covers.

This split isn't historical accident — it's a deliberate security boundary. `/etc/passwd` must be **world-readable**, because an enormous number of ordinary operations depend on it: `ls -l` resolving a UID to a username, `id`, shell prompts showing a username, any program calling `getpwnam()`/`getpwuid()` to map between names and numbers. If password hashes lived in that same world-readable file — as they did in the original Unix design — every local user could copy the hash file and run an offline brute-force or dictionary attack against it at their leisure. `/etc/shadow` exists specifically to move the one genuinely sensitive field (the password hash) into a file readable only by root (and, on most distributions, the `shadow` group for controlled delegation), while leaving everything else — the fields ordinary tools legitimately need — in the world-readable file. This is the **shadow password** scheme, and essentially every modern distribution uses it by default.

> 💡 **Tip:** The mental model that keeps these three files straight: `/etc/passwd` is the public directory listing, `/etc/shadow` is the locked authentication vault, and `/etc/group` is the membership roster. A user always has exactly one line in `passwd` and at most one line in `shadow`, but can appear in the membership list of many lines in `group`.

## 2. `/etc/passwd` Field by Field

Each line is seven colon-separated fields:

```text
username:password_placeholder:UID:GID:GECOS:home_directory:shell
```

**Example:**

```text
$ grep '^harsh:' /etc/passwd
harsh:x:1000:1000:Harsh Kandhwey,,,:/home/harsh:/bin/bash
```

| Field                  | Meaning                                                                                                                                                                                                                                      |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `username`             | Login name, up to 32 characters by convention on most distributions                                                                                                                                                                          |
| `password_placeholder` | Almost always the literal character `x`, signaling "the real hash lives in `/etc/shadow`" — see the `/etc/shadow` field breakdown below                                                                                                      |
| `UID`                  | Numeric user ID — the value the kernel actually checks for ownership and permissions ([§22](../Part3/Section-22-Part3-File-Metadata-Timestamps-Ownership-Attributes.md)); the username is purely a human-facing label resolved via this file |
| `GID`                  | The user's **primary group** GID, detailed in the `/etc/group` section below — cross-referenced against `/etc/group` to resolve a name                                                                                                       |
| `GECOS`                | Free-form comment field — historically "General Electric Comprehensive Operating System" info, in practice usually the full name and sometimes comma-separated phone/office fields, often just left blank or holding a display name          |
| `home_directory`       | The user's `$HOME`, set on login                                                                                                                                                                                                             |
| `shell`                | The program executed on interactive login (`/bin/bash`, `/bin/zsh`) — or a deliberately non-interactive value like `/usr/sbin/nologin` or `/bin/false` for service accounts that must exist but should never get an interactive session      |

**Legacy field-order mnemonic worth knowing even though it's rarely typed manually today:** `username:password:UID:GID:GECOS:home:shell` — seven fields, always in that order, and every field is present even when empty (an empty GECOS field is just `::` with nothing between the colons, not a missing field).

## 3. UID Ranges: System vs. Regular Users

UID values aren't arbitrary — ranges carry meaning that both tooling and administrators rely on:

| Range                         | Meaning                                                                                                                                                                                                                                                                                                                                                                                                                                              |
| ----------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `0`                           | **root**, always and unconditionally — UID 0 is what actually grants superuser power, not the username "root" (a second account with UID 0 is just as privileged as root, which is exactly why finding one during an audit is a serious red flag)                                                                                                                                                                                                    |
| `1`–`99` (or `1`–`999`)       | **System/service accounts** — created by the OS and packages for daemons that need a distinct identity (`daemon`, `bin`, `sys`, `www-data`, `sshd`) but never log in interactively                                                                                                                                                                                                                                                                   |
| Distribution-dependent cutoff | Where "system" ends and "regular human user" begins — **Debian/Ubuntu** conventionally start regular users at UID **1000**; **RHEL/CentOS/Fedora family** conventionally start at UID **1000** as well in modern releases, but historically RHEL 6 and earlier used **500** as the cutoff — this specific number is exactly the kind of detail worth confirming against `/etc/login.defs`'s `UID_MIN`/`UID_MAX` on a given host rather than assuming |
| `65534`                       | Conventionally **`nobody`** — an intentionally unprivileged, no-login account used as a fallback identity (e.g., for NFS's `root_squash` behavior, or processes deliberately dropped to minimal privilege)                                                                                                                                                                                                                                           |

> ⚠️ **Warning:** Never hardcode an assumed UID cutoff (1000 vs. 500) into automation or audit scripts across a mixed fleet — read the authoritative value from `/etc/login.defs` (`UID_MIN`) on each host instead. A script that assumes "UID ≥ 1000 means human user" will silently misclassify service accounts on an older RHEL-lineage host still using the 500 convention, and the failure mode (treating a service account as a human user, or vice versa) is exactly the kind of thing that shows up in a security audit finding, not a crash.

## 4. `/etc/shadow` Field by Field

`/etc/shadow` is readable only by root (mode `0640` or `0600`, owned by `root:shadow` on most distributions), and has exactly one line per user that has a shadow entry, in the same relative order as `/etc/passwd` by convention (though lookups are by username, not position). Nine colon-separated fields:

```text
username:password_hash:last_change:min_age:max_age:warn:inactive:expire:reserved
```

**Example:**

```text
$ sudo grep '^harsh:' /etc/shadow
harsh:$6$randomsalt123$longhashvalue...:19920:0:99999:7:::
```

| Field           | Meaning                                                                                                                                                                                  |
| --------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `password_hash` | The actual hash, in `$id$salt$hash` format, detailed just below — or a special non-hash value (below)                                                                                    |
| `last_change`   | Days since the Unix epoch (1970-01-01) that the password was last changed — a day count, not a timestamp                                                                                 |
| `min_age`       | Minimum days that must pass before the password can be changed again (`0` = no restriction) — prevents a user from immediately cycling back to a previous password after a forced change |
| `max_age`       | Maximum days the password is valid before it must be changed — `99999` is the conventional "effectively never expires" sentinel                                                          |
| `warn`          | Days before expiry that the user starts seeing a login warning                                                                                                                           |
| `inactive`      | Days after expiry before the account is locked entirely if the password still hasn't been changed (grace period)                                                                         |
| `expire`        | Absolute account expiration date, again as days since the epoch (not password expiry — the whole account) — commonly used for contractor/temporary-access accounts with a hard end date  |
| `reserved`      | Reserved for future use, conventionally left empty                                                                                                                                       |

**Special non-hash values in the `password_hash` field**, each meaning something operationally distinct:

- `!` or `!!` — account is **locked**; login via password is disabled, but the field still holds (or preserves, prefixed onto) a real hash underneath in some tools' convention, meaning `passwd -u` can potentially unlock it. This is what `usermod -L` / `passwd -l` produce ([§26](./Section-26-Part4-User-Group-Management-Commands.md)).
- `*` — password authentication is **disabled entirely**, with no hash to fall back to — the conventional value for system/service accounts that should never authenticate via password at all (SSH key-only or no login, enforced independently by the shell field too).
- Empty field — the account has **no password required** — a serious misconfiguration if found on an interactive account during an audit, since it means anyone can log in as that user with an empty password (subject to PAM configuration actually permitting empty passwords, which is itself usually disabled by default — but relying on that second control rather than fixing the empty field is not a sound posture).

> ⚠️ **Warning:** Treat any account with an empty `/etc/shadow` password field, or a UID-0 account other than `root`, as an immediate audit finding — both are classic privilege-escalation or backdoor patterns worth grepping for explicitly (`awk -F: '($2 == "") {print $1}' /etc/shadow` and `awk -F: '($3 == 0) {print $1}' /etc/passwd`) during any security review ([§89](../Part12/Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md) covers the fuller hardening checklist).

### 4.1 Password Hash Format: `$id$salt$hash`

Modern Linux password hashes follow a self-describing format: `$id$salt$hash`, where `$id` identifies which hashing algorithm produced it, `salt` is the per-password random salt (preventing identical passwords from producing identical hashes across accounts, which defeats naive rainbow-table attacks), and `hash` is the resulting digest.

| `$id$` prefix        | Algorithm                                                                                                                                                                                         |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `$1$`                | MD5 — legacy, cryptographically broken for this purpose by modern standards, still occasionally seen on old systems                                                                               |
| `$2a$`/`$2b$`/`$2y$` | bcrypt — common on BSD-lineage systems and some application-level auth, less common as the OS-level default on mainstream Linux                                                                   |
| `$5$`                | SHA-256                                                                                                                                                                                           |
| `$6$`                | **SHA-512** — the current default on essentially every mainstream Linux distribution today                                                                                                        |
| `$y$`                | yescrypt — the newer, memory-hard default adopted by some recent distribution releases (Debian/Fedora moving toward it) in place of `$6$`; worth confirming per-distribution rather than assuming |

Recognizing `$6$` versus `$1$` at a glance during an audit is a fast, meaningful signal — a fleet with `$1$` hashes anywhere in `/etc/shadow` indicates passwords set (or never rotated) under a very old policy, and rotating them forces regeneration under the modern algorithm, since Linux doesn't retroactively re-hash existing passwords when the default algorithm changes.

## 5. `/etc/group` Field by Field and Primary vs. Supplementary Groups

`/etc/group` has one line per group, four colon-separated fields:

```text
groupname:password_placeholder:GID:member_list
```

**Example:**

```text
$ grep -E '^(sudo|docker):' /etc/group
sudo:x:27:harsh,alice
docker:x:999:harsh
```

| Field                  | Meaning                                                                                                                                |
| ---------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `groupname`            | The group's name                                                                                                                       |
| `password_placeholder` | Almost always `x`, mirroring `passwd` — the real group password (rarely used) lives in `/etc/gshadow`, covered in the brief note below |
| `GID`                  | Numeric group ID                                                                                                                       |
| `member_list`          | Comma-separated usernames who belong to this group **as a supplementary group** — see the primary/supplementary distinction below      |

**Primary vs. supplementary groups is the single most important distinction in this file, and it's easy to get backwards:**

- A user's **primary group** is recorded in `/etc/passwd`'s fourth field (GID), not in `/etc/group`'s member list. It's the group assigned to files the user creates by default (subject to umask, [§29](./Section-29-Part4-Umask-Default-Permissions.md)) and is always exactly one group.
- A user's **supplementary groups** (also called secondary groups) are the groups listing that user in `/etc/group`'s member field — a user can belong to any number of these simultaneously, and they grant access to whatever those groups' permissions allow (a shared project directory, `docker`'s socket access, `sudo`'s privilege) without changing which group new files get created under.

This is precisely why a user can be in the `docker` or `sudo` group and have that membership **not take effect in an already-open shell** — supplementary group membership is read and attached to the process's credentials at login/session-start time, so a `usermod -aG docker harsh` run in one terminal doesn't retroactively add `docker` to a `harsh` shell that was already running before the change; the user needs to start a new login session (or run `newgrp docker`, which spawns a new shell with the group added) to pick it up.

> 💡 **Tip:** `id` shows both halves at once and is the fastest way to check what's actually in effect for the current session: `uid=1000(harsh) gid=1000(harsh) groups=1000(harsh),27(sudo),999(docker)` — the `gid=` value is the primary group; everything listed after `groups=` beyond that is supplementary. If a group you just added yourself to via `usermod -aG` isn't showing up here, that's the stale-session symptom above, not a broken command.

## 6. `/etc/gshadow`: Brief Note

`/etc/gshadow` exists for the same reason `/etc/shadow` exists relative to `/etc/passwd`: it moves group password hashes and administrative delegation info out of the world-readable `/etc/group` and into a root-only file, with fields for a group password hash, group administrators (users allowed to add/remove members without full root via `gpasswd -A`), and the member list again. In practice, group passwords are rarely used in modern infrastructure — group-based access is almost always managed by adding users to `/etc/group`'s member list via `usermod`/`gpasswd` ([§26](./Section-26-Part4-User-Group-Management-Commands.md)) rather than by anyone actually authenticating with a shared group password — so `/etc/gshadow` is worth knowing exists and roughly why, without expecting to interact with it directly in day-to-day administration.

## 7. Common Misconceptions

1. **"Deleting a user's line from `/etc/passwd` deletes the user."** It removes the account's ability to log in and be resolved by name, but files the user owned on disk still carry that UID as their numeric owner — `ls -l` on those files will show a bare UID number instead of a name once nothing in `/etc/passwd` resolves it ([§22](../Part3/Section-22-Part3-File-Metadata-Timestamps-Ownership-Attributes.md)'s ownership-is-numeric point applies directly here). Proper user removal is `userdel` ([§26](./Section-26-Part4-User-Group-Management-Commands.md)), and even then, orphaned UID-owned files aren't automatically found or reassigned unless explicitly searched for (`find / -uid <deleted-uid>`).
2. **"The `x` in the password field of `/etc/passwd` is itself part of the password hash."** It's a placeholder meaning "look in `/etc/shadow` instead" — it is not a truncated hash, not a default password, and has no cryptographic meaning at all. Confusing this leads people to think a passwd-only account (no shadow entry) has a trivial password, when in practice `getpwnam()`-based tools simply won't find a valid credential to check against at all in that state.
3. **"UID 1000 is always the first regular human user, on every distribution."** Debian/Ubuntu and current RHEL-family releases both default to 1000, but this is a convention set by `/etc/login.defs`'s `UID_MIN`, not a kernel rule — older RHEL-lineage systems used 500, and any given host's automation or images could have overridden the default. Always verify per-host, per the UID-ranges discussion above, rather than assuming.
4. **"Adding a user to a group with `usermod -aG` takes effect immediately in every open terminal."** Supplementary group membership is attached to a session at login time — an already-running shell keeps the group list it started with until a new login session begins or `newgrp` is used, as the primary-vs-supplementary-groups section above covers. This is one of the most common "why doesn't my permission change work" support tickets.
5. **"A locked account (`!` in `/etc/shadow`) and a disabled-login account (`*`, or shell set to `/usr/sbin/nologin`) are the same thing."** They address different attack surfaces: locking (`!`) specifically blocks password authentication while potentially leaving other auth methods (SSH key) intact, `*` signals "no password auth was ever configured, full stop," and a `nologin` shell blocks interactive shell sessions regardless of how authentication succeeded. A hardened service account often combines more than one of these deliberately, and conflating them can lead to an incomplete lockdown.

## 8. Tiered Interview Questions

**🎯 Beginner:** _"Why was `/etc/shadow` introduced when `/etc/passwd` already existed?"_
**Model answer:** `/etc/passwd` has to stay world-readable because so many ordinary tools and lookups (`ls -l` resolving owners, `id`, login prompts) depend on mapping UIDs to usernames without needing root. In the original Unix design, password hashes lived right in that same world-readable file, which meant any local user could copy the hash list and run an offline cracking attempt against it whenever they wanted. `/etc/shadow` moves just the sensitive authentication fields — the hash and the aging policy — into a separate file readable only by root, while leaving the identity-lookup fields that ordinary tools legitimately need in the still-world-readable `/etc/passwd`.
_What the interviewer is probing for:_ Understanding this as a deliberate security boundary (least-exposure of sensitive data), not just "shadow is where passwords are now."

**🎯 Intermediate:** _"A user reports that after being added to the `docker` group, `docker ps` still gives a permission-denied error in their current terminal. What's going on?"_
**Model answer:** Supplementary group membership is read and attached to a process's credentials when its session starts — typically at login. `usermod -aG docker` updates `/etc/group` immediately, but a shell that was already open before that change was made doesn't retroactively pick up the new group; `id` in that stale shell will still show the old group list. The fix is starting a new login session (logging out and back in, opening a new SSH connection) or using `newgrp docker` to spawn a subshell with the group added without a full new login. I'd confirm with `id` before assuming anything is actually broken in the group configuration itself.
_What the interviewer is probing for:_ Recognizing this as a session-timing issue rather than a permissions or configuration bug — a very common real-world support scenario.

**🎯 Senior:** _"During an audit you find a line in `/etc/passwd` with UID `0` and username `sysadm`, distinct from `root`. What's your assessment and next steps?"_
**Model answer:** UID 0 is what the kernel actually checks for superuser privilege — the username is cosmetic. A second UID-0 account is functionally a second root account, indistinguishable in privilege from `root` itself, and it's a classic pattern for both legitimate-but-risky historical practice (some older shops created a second UID-0 account for a "safety" login) and for a deliberately planted backdoor after a compromise. I'd treat it as a critical finding regardless of stated intent: check its `/etc/shadow` entry for how it authenticates (password hash present? SSH keys installed for it? `!`/`*` locked?), check its home directory and shell history for signs of use, check login/audit logs (`last`, `auditd` if enabled, [§90](../Part12/Section-90-Part12-SSH-Hardening-Bastion-Host-Patterns.md)) for any sessions under that account, and cross-reference against change-management records to see if it was ever legitimately provisioned. Unless there's a documented, currently-justified reason for it, the remediation is removing the duplicate UID-0 account (or reducing it to a normal UID with sudo grants instead, [§31](./Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md)), not just leaving it locked, since a locked password hash doesn't prevent key-based or otherwise-configured authentication from still working.
_What the interviewer is probing for:_ Correctly identifying UID 0 (not the username) as the actual privilege signal, and a methodical incident-response-style investigation rather than a one-line "delete it" answer.

**🎯 Architect:** _"You're designing the account-provisioning standard for a new fleet spanning both Debian- and RHEL-family hosts. What passwd/shadow/group-level decisions do you need to standardize, and why?"_
**Model answer:** First, I wouldn't rely on either distribution family's default `UID_MIN`/`GID_MIN` — I'd pin an explicit, fleet-wide UID/GID range convention in configuration management (e.g., service accounts always provisioned in a specific reserved band, human accounts in another) so that "is this a system or human account" is answerable by policy rather than by guessing at each distro's historical default, especially since RHEL's older 500-cutoff convention and Debian's 1000-cutoff convention would otherwise produce inconsistent classifications across the same fleet, per the UID-ranges discussion above. Second, I'd standardize the password-hash algorithm expectation — confirming `$6$`/`$y$` as the enforced minimum via `/etc/login.defs` or an equivalent config-management-enforced setting, and treating any `$1$` hash discovered on a host as a rotation trigger. Third, service accounts get a consistent, deliberate combination of `*` in the shadow hash field and a `nologin` shell, provisioned via automation rather than ad hoc `useradd` calls, so "no interactive login, no password auth" is enforced two ways rather than relying on either alone. Fourth, group strategy: supplementary groups (not shared login accounts, not group passwords via `/etc/gshadow`) as the sole mechanism for shared access, since that keeps individual accountability intact for auditing — I'd explicitly forbid the group-password mechanism in the standard. Finally, I'd bake an automated periodic audit (the empty-password and UID-0 checks from the `/etc/shadow` section above) into the fleet's compliance tooling rather than treating this as a one-time provisioning-day concern, since drift — a manually added account, a locally overridden default — is the realistic long-term risk, not the initial provisioning.
_What the interviewer is probing for:_ Fleet-wide, policy-driven thinking that accounts for cross-distribution inconsistency, and treating identity hygiene as an ongoing audited control rather than a one-time setup step.

## 9. Key Takeaways

- `/etc/passwd` (world-readable, 7 fields: username, `x` placeholder, UID, primary GID, GECOS, home, shell) handles identity lookup; `/etc/shadow` (root-only, 9 fields including hash and aging) handles authentication — the split exists specifically so ordinary UID/username lookups don't require exposing password hashes.
- UID 0 is always root's actual privilege signal, not the username "root" — any second UID-0 account is a critical audit finding. System/service account UID ranges start near 1–999, and the system-vs-human-user cutoff (1000 on modern Debian and RHEL families, historically 500 on older RHEL) must be read from `/etc/login.defs`'s `UID_MIN` per host, never assumed.
- The `/etc/shadow` password field's format is `$id$salt$hash` — `$6$` (SHA-512) is today's mainstream default, `$1$` (MD5) is a legacy red flag; special values `!`/`!!` (locked), `*` (no password auth configured), and empty (no password required — a serious finding) each mean something operationally distinct.
- A user's primary group lives in `/etc/passwd`'s GID field (exactly one); supplementary groups live in `/etc/group`'s member list (any number) — supplementary membership is attached at session start, so a running shell won't see a `usermod -aG` change until a new login or `newgrp`.
- `/etc/gshadow` mirrors `/etc/shadow`'s role for group passwords and group-admin delegation, but group passwords are rarely used in practice — group-based access control is almost always just `/etc/group` membership managed via `usermod`/`gpasswd`.

## 10. Related Concepts & What's Next

This section builds directly on [§22](../Part3/Section-22-Part3-File-Metadata-Timestamps-Ownership-Attributes.md)'s UID/GID ownership model (Part 3) — the numbers the kernel enforces against file metadata are exactly the numbers `/etc/passwd` and `/etc/group` give names to. It's also the natural companion to [§24](../Part3/Section-24-Part3-Proc-Sys-Virtual-Filesystems.md)'s `/proc` coverage, since a running process's credentials (`/proc/<pid>/status`'s `Uid`/`Gid` lines) trace directly back to the account records covered here. [§26](./Section-26-Part4-User-Group-Management-Commands.md) (next) moves to the command-line tooling — `useradd`, `usermod`, `userdel`, `groupadd`, `passwd`, `gpasswd` — that manipulates these three files safely instead of hand-editing them. [§27](./Section-27-Part4-Standard-Permission-Model.md) builds the standard `rwx` permission model on top of the ownership this section establishes, [§31](./Section-31-Part4-Sudo-Sudoers-Privilege-Escalation.md) covers `sudo` as a structured alternative to UID-0 account sprawl, and [§32](./Section-32-Part4-PAM-Overview.md) covers PAM, which governs the actual authentication decision logic that consults `/etc/shadow` (and much more) at login time.

**Next Section:** [§26](./Section-26-Part4-User-Group-Management-Commands.md) — `Section-26-Part4-User-Group-Management-Commands.md`
