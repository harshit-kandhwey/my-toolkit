# Section 31 (Part 4): sudo, /etc/sudoers, and the Privilege Escalation Model

## 1. Two Different Answers to "How Do I Become Root?"

[§26](./Section-26-Part4-User-Group-Management-Commands.md)'s coverage of `su`/`su -` already introduced one answer to "how does a regular user get root privileges": switch identity entirely, drop into a root shell, and do whatever's needed until you exit back out. This section covers the other, now far more common answer — **`sudo`** — and it's worth being precise about why these aren't just two syntaxes for the same idea:

- **`su -`** performs a **full identity switch**. Once inside, every command runs as root, indistinguishable (from an audit-log perspective) from any other root activity, until the shell is exited.
- **`sudo`** performs **per-command, per-invocation privilege elevation**. Each individual command is run with elevated rights, logged as a discrete, attributable event, and the calling user's own identity never actually changes — `sudo whoami` reports `root`, but the shell that ran it is still `jane`'s shell.

That per-command, attributable model is the entire reason `sudo` displaced `su` as the default day-to-day privilege-escalation mechanism on modern fleets: it produces an audit trail of _who_ ran _what_ as root and _when_, rather than an undifferentiated block of "someone was root for a while." This section covers `sudo`'s configuration model in depth; [§32](./Section-32-Part4-PAM-Overview.md) (next) covers PAM, the authentication framework `sudo` itself calls into to actually verify a password.

> 💡 **Tip:** `sudo su -` and `sudo -i` both exist specifically to get a full root login shell _through_ `sudo`'s audit and authorization layer, for situations where a genuine interactive root session is unavoidable — they're a deliberate bridge between the two models, not a contradiction of `sudo`'s per-command philosophy.

## 2. `sudo` Is Itself a SUID-Root Binary

[§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md) covered the SUID bit — a binary that runs with its **owner's** privileges rather than the invoking user's. `sudo` is the canonical real-world example: the `/usr/bin/sudo` binary is owned by `root` with the SUID bit set, which is precisely what lets an unprivileged user's invocation of `sudo` gain root-level capability in the first place, before any policy decision about whether that user is actually _allowed_ to has even been consulted.

```bash
$ ls -l /usr/bin/sudo
-rwsr-xr-x 1 root root 231344 Jan 10  2026 /usr/bin/sudo
```

That `s` in the owner-execute position is the same mechanism [§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md) walked through generically — this section is that mechanism's single most important production instance. It's worth internalizing the two-stage model this implies:

1. **SUID gets `sudo` root capability at the OS level**, unconditionally, the moment it's executed — the kernel doesn't ask `/etc/sudoers` anything at this stage.
2. **`sudo`'s own code then consults `/etc/sudoers`** (and PAM, [§32](./Section-32-Part4-PAM-Overview.md)) to decide whether _this_ user, running _this_ command, from _this_ context, is actually permitted — and refuses if not, despite already technically holding root capability via SUID.

> ⚠️ **Warning:** Because `sudo` is a SUID-root binary, any bug in `sudo` itself is a direct path to unauthenticated or policy-bypassing root escalation — `sudo` has a real CVE history (several critical ones, including buffer-overflow and policy-bypass classes) precisely because it sits at this SUID trust boundary. Keeping `sudo` patched is not optional hygiene; it's patching the literal gatekeeper.

## 3. `/etc/sudoers` and Why `visudo` Is Mandatory, Not a Suggestion

`/etc/sudoers` is the policy file `sudo` consults for stage 2 above — it defines which users and groups can run which commands, as which target users, under what conditions. It has strict, unforgiving syntax, and a single malformed line can either lock every administrator out of `sudo` simultaneously or, worse, silently grant far broader access than intended.

**This is why `/etc/sudoers` must always be edited with `visudo`, never a plain text editor:**

```bash
sudo visudo
```

`visudo` doesn't just open the file in an editor (it respects `$EDITOR`, so it's frequently vim or nano under the hood) — it **locks the file** against simultaneous edits and, critically, **runs a syntax validation pass before allowing the save to take effect**. If the syntax is broken, `visudo` refuses to commit the change and gives the option to re-edit or discard, rather than writing a broken file to disk.

> ⚠️ **Warning: Editing `/etc/sudoers` with a plain text editor is a self-inflicted lockout waiting to happen.** A stray typo committed directly with `vim /etc/sudoers` can break `sudo` parsing for every user on the box, including whoever needs `sudo` to fix it — a genuine "how do I get back in" incident that, on a remote host with no other root access path, can mean falling back to single-user/rescue mode or a cloud provider's out-of-band console. `visudo`'s pre-save validation exists specifically to make this class of incident structurally impossible during a routine edit.

**Troubleshooting:** If `visudo` reports a syntax error on save, note the exact line number it flags and fix that line specifically — don't just discard and start over from memory, since the error message points at the actual malformed rule.

## 4. `sudoers` Syntax Breakdown

The canonical rule syntax is:

```text
who    where = (as_whom)  what
```

**Concrete examples, unpacked:**

```text
root    ALL=(ALL:ALL) ALL
%sudo   ALL=(ALL:ALL) ALL
jane    ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nginx
deploy  ALL=(www-data) /usr/bin/php /var/www/artisan
```

| Field           | Meaning                                                                                                                                |
| --------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `who`           | The user (or `%group`, with a leading `%`) the rule applies to                                                                         |
| `where` (`ALL`) | Which hosts the rule applies to — `ALL` in nearly every single-host `sudoers` file; meaningful mainly in centrally distributed configs |
| `(as_whom)`     | Which target user (and optionally group, after the colon) the command can be run as — `(ALL:ALL)` means any user, any group            |
| `what`          | The command(s) permitted — `ALL` means any command; otherwise a specific absolute path (or comma-separated list) to a binary           |
| `NOPASSWD:`     | A tag prefixing the command list that waives the password prompt for those specific commands                                           |

Reading `root ALL=(ALL:ALL) ALL` in full: "user `root`, on any host, may run any command as any user/group" — root's own unrestricted baseline. `jane ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nginx` reads: "user `jane`, on any host, may run exactly that one `systemctl` command as root, without being prompted for a password" — a narrow, auditable, deliberately scoped grant.

### 4.1 The `%wheel` / `%sudo` Group Convention: Debian vs. RHEL

[§26](./Section-26-Part4-User-Group-Management-Commands.md) flagged this tie-in directly: `usermod -aG sudo` or `usermod -aG wheel` is how an admin is granted `sudo` access day to day, and which group name is meaningful depends on distribution family:

| Distribution family          | Convention group | Enabled via                                                                                             |
| ---------------------------- | ---------------- | ------------------------------------------------------------------------------------------------------- |
| Debian / Ubuntu              | `sudo`           | `%sudo   ALL=(ALL:ALL) ALL` present by default in `/etc/sudoers`                                        |
| RHEL / CentOS / Rocky / Alma | `wheel`          | `%wheel  ALL=(ALL) ALL` present, sometimes commented out by default and requiring explicit uncommenting |

> ⚠️ **Warning:** Assuming `wheel` works on Debian/Ubuntu (or `sudo` works on RHEL-family) because it worked on "the other" distro family is a real, recurring cross-distro mistake — adding a user to the wrong group name grants nothing, and the failure mode (`user is not in the sudoers file`) gives no hint that the group name itself was the problem. Always confirm which group name a given `/etc/sudoers` actually wires up before granting access via group membership.

## 5. `/etc/sudoers.d/`: The Modern Preferred Approach

Rather than accumulating every custom rule inside the single monolithic `/etc/sudoers` file, modern practice is to drop individual, purpose-scoped files into `/etc/sudoers.d/` — a directory `sudoers` includes via a line near the bottom of the main file:

```text
#includedir /etc/sudoers.d
```

Each file in that directory is parsed as if its contents were inlined at that point. A typical drop-in, `/etc/sudoers.d/deploy-nginx`:

```text
deploy  ALL=(ALL) NOPASSWD: /usr/bin/systemctl restart nginx, /usr/bin/systemctl reload nginx
```

**Why this is preferred over editing the monolithic file directly:**

- **Isolation.** A syntax mistake in one drop-in file, when using `visudo -f`, is validated and contained to that file rather than risking the entire base policy.
- **Configuration-management friendliness.** Ansible, Puppet, or Chef can manage a single, purpose-named file per grant (`deploy-nginx`, `oncall-emergency`) idempotently, without needing to parse or template the entire base `sudoers` file — a much smaller, safer blast radius per change.
- **Clean auditability and removal.** Revoking a specific grant is deleting or renaming one file, not surgically removing lines from a shared file that other rules also live in.
- **Per-file validation.** `visudo -f /etc/sudoers.d/deploy-nginx` validates just that file's syntax, same locking-and-checking guarantee as editing the main file.

```bash
sudo visudo -f /etc/sudoers.d/deploy-nginx
```

> 💡 **Tip:** Files in `/etc/sudoers.d/` must **not** contain a dot in the filename (and on most distributions, not a `~` either) — `sudoers`'s parser silently ignores files matching backup/editor-swap patterns like `deploy-nginx~` or `deploy-nginx.bak`, which is a deliberate safeguard against accidentally activating a stray editor backup as live policy, but also a common "why isn't my new rule taking effect" gotcha if you name the file carelessly.

## 6. `sudo -l`: Listing What a User Can Actually Do

**Purpose:** Show the effective, fully-resolved set of `sudo` permissions for the invoking user (or another user, as root) — the fast diagnostic for "what is this account actually allowed to do," without needing to hand-trace every applicable rule across the base file and every `sudoers.d` drop-in.

**Syntax:**

```bash
sudo -l
sudo -l -U username
```

**Example usage and expected output:**

```bash
$ sudo -l
Matching Defaults entries for jane on this host:
    env_reset, mail_badpass, secure_path=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin

User jane may run the following commands on this host:
    (ALL) NOPASSWD: /usr/bin/systemctl restart nginx, /usr/bin/systemctl reload nginx
    (ALL : ALL) ALL
```

**Production usage example:** `sudo -l` is the standard first step in both onboarding verification ("did the grant actually take effect") and incident investigation ("what could this compromised account have done as root") — it reflects every applicable rule already merged together, which is far more reliable than manually reading `/etc/sudoers` plus every file in `/etc/sudoers.d/` by eye.

**Common errors:**

- Reading only the base `/etc/sudoers` file and missing a broader (or narrower) grant that actually lives in a `sudoers.d` drop-in — `sudo -l` sidesteps this entirely by showing the resolved outcome.

## 7. Logging: Where `sudo` Activity Actually Lands

Every `sudo` invocation — successful or refused — is logged, which is the concrete payoff of the per-command audit-trail model from 1:

| Distribution family          | Log location        |
| ---------------------------- | ------------------- |
| Debian / Ubuntu              | `/var/log/auth.log` |
| RHEL / CentOS / Rocky / Alma | `/var/log/secure`   |

```bash
$ grep sudo /var/log/auth.log | tail -5
Jul 26 09:14:02 web01 sudo: jane : TTY=pts/0 ; PWD=/home/jane ; USER=root ; COMMAND=/usr/bin/systemctl restart nginx
Jul 26 09:20:11 web01 sudo: alice : command not allowed ; TTY=pts/1 ; PWD=/home/alice ; USER=root ; COMMAND=/usr/sbin/useradd hacker
```

Each successful line records who ran it, from which terminal, from what working directory, as which target user, and the exact command — and refused attempts are logged too, which is often the more security-relevant signal (an account repeatedly attempting commands it isn't authorized for), the concrete payoff of the per-command audit-trail model introduced at the top of this section. [§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md) (journald, Part 9) and [§92](../Part12/Section-92-Part12-Kernel-Hardening-Sysctl-Security-Parameters.md) (auditd, Part 12) both build on this same raw log data for centralized and compliance-grade logging respectively — this section's log lines are the ground-truth source both eventually consume.

> 💡 **Tip:** During an incident investigation involving a potentially compromised account, `grep username /var/log/auth.log` (or `/var/log/secure`) is one of the fastest ways to establish exactly what that account attempted as root, successful or not — cross-reference against `sudo -l`'s current permitted set to spot anything that looks like escalation beyond the account's normal grant.

## 8. Session Caching and the Timeout Window

By default, `sudo` doesn't prompt for a password on every single invocation — after a successful authentication, it caches that credential for a configurable window (**15 minutes by default** on most distributions) tied to the originating terminal session, so a string of `sudo` commands run in quick succession only prompts once.

```text
Defaults        timestamp_timeout=15
```

This is convenient, but it's also a real security consideration worth naming explicitly: within that cached window, **anything** with access to that terminal session — a script, a forgotten unattended shell, a hijacked session — can invoke `sudo` without a fresh password check. `sudo -k` invalidates the cached timestamp immediately (forcing the next `sudo` call to re-prompt), and is a reasonable thing to run explicitly before stepping away from a privileged terminal rather than trusting the timeout alone.

```bash
$ sudo -k
```

## 9. Footguns: Rules That Look Narrow but Grant Full Root

The single most consequential class of `sudoers` mistake isn't syntax — it's granting `sudo` on a command that _looks_ narrowly scoped but actually provides a shell-escape path to unrestricted root. This is a real, well-documented privilege-escalation vector, not a theoretical edge case.

> ⚠️ **Warning: `NOPASSWD` (or even password-gated) `sudo` access to shell-capable programs is effectively unrestricted root, regardless of how narrow the rule looks.** Programs like `vim`, `less`, `more`, `awk`, `find`, `python`, and many others support an internal shell-escape (`:!bash` in `vim`, `!bash` in `less`/`more`, `find . -exec /bin/bash \;`, and so on). A rule like `jane ALL=(ALL) NOPASSWD: /usr/bin/vim /etc/nginx/nginx.conf` was almost certainly written to let `jane` edit one config file without a password — but it actually lets her spawn an interactive root shell from inside `vim` with zero further authorization. [GTFOBins](https://gtfobins.github.io) catalogs this exact class of escape for a huge range of common Unix binaries, and it's the standard reference to check any command _before_ it's granted via `sudoers`. Prefer wrapper scripts with no shell-escape surface, or tools with a documented restricted/rbash mode, over granting raw `sudo` on general-purpose editors, pagers, or interpreters.

Related, narrower footguns worth naming explicitly:

- **Overly broad `NOPASSWD: ALL` grants**, often added "temporarily" during an incident and never revoked — the single most common way a fleet drifts from "auditable per-command access" back toward "unrestricted root with extra steps."
- **Wildcards in command paths** (`/usr/bin/systemctl *`) can be more permissive than intended — `systemctl` itself has subcommands (`systemctl edit`, which opens `$EDITOR`) that reintroduce the same shell-escape problem as above, even though the top-level binary looks legitimately scoped.
- **Granting `sudo` on scripts writable by the granted user** — if `jane` can `sudo` run `/opt/scripts/deploy.sh` and also has write access to that same script, the `sudo` grant is only as narrow as the script's current contents, which she can freely rewrite.

## 10. Common Misconceptions

1. **"`sudo` and `su -` are basically interchangeable ways to become root."** They differ fundamentally in model: `sudo` is per-command, attributable elevation without an identity switch; `su -` is a full identity switch into an undifferentiated root session. `sudo -i`/`sudo su -` deliberately bridge the two when a full root shell is genuinely needed, but that's a deliberate escape hatch, not evidence they're the same thing, as the section-opening comparison covers.
2. **"Editing `/etc/sudoers` with `vim` directly is fine as long as you're careful."** `visudo`'s value isn't convenience, it's the pre-save syntax validation that makes a lockout-inducing typo structurally impossible — "being careful" is exactly the failure mode `visudo` exists to remove reliance on, as the `visudo` section above explains.
3. **"`wheel` and `sudo` are the same group under a different name."** Which group name is actually wired up to a `%group ALL=(ALL:ALL) ALL` rule is distribution-family-specific (Debian/Ubuntu use `sudo`, RHEL-family uses `wheel`) — assuming the other family's convention grants nothing and fails silently from the group-membership side, as the Debian-vs-RHEL group convention section above details.
4. **"A narrowly-named `sudo` command grant is inherently narrow in what it allows."** Many common binaries (`vim`, `less`, `find`, interpreters) have built-in shell-escape functionality that turns a seemingly scoped grant into unrestricted root — the command name being specific doesn't mean the access it grants is specific, as the footguns section above covers.
5. **"`sudo -l` only shows what's in `/etc/sudoers`."** It shows the fully merged, resolved permission set across the base file **and** every applicable file in `/etc/sudoers.d/` — it's the authoritative resolved view precisely because manually reading every source file separately is error-prone, as the `sudo -l` section above shows.

## 11. Tiered Interview Questions

**🎯 Beginner:** _"What's the conceptual difference between `sudo` and `su -`?"_
**Model answer:** `su -` fully switches identity into a login shell as the target user (commonly root) — every subsequent command in that shell runs as root, until you exit. `sudo` elevates privilege for a single command at a time, without switching the calling user's actual identity, and logs each invocation individually. That per-command granularity and logging is why `sudo` is the standard day-to-day mechanism on modern fleets — it produces an attributable audit trail rather than an undifferentiated block of root activity.
_What the interviewer is probing for:_ Understanding the model difference, not just "both let you become root."

**🎯 Intermediate:** _"Why must `/etc/sudoers` always be edited with `visudo` instead of a normal text editor?"_
**Model answer:** `visudo` locks the file against concurrent edits and, critically, runs a syntax validation pass before committing any save — if the edit introduces a syntax error, `visudo` refuses to write it and offers to re-edit or discard. Editing `/etc/sudoers` directly with `vim` or `nano` has no such safeguard — a single malformed line can break `sudo` parsing for every user on the host, including whoever would need `sudo` to fix it, which on a remote host with no other root path can turn a typo into a genuine lockout incident.
_What the interviewer is probing for:_ Specific mechanism (locking plus pre-save validation), not just "it's best practice."

**🎯 Senior:** _"A junior admin added `jane ALL=(ALL) NOPASSWD: /usr/bin/vim /etc/app/config.yml` so she could edit one config file without a password. Why is this a security problem, and what's the fix?"_
**Model answer:** `vim` has a built-in shell-escape (`:!bash` or `:shell`), so that rule doesn't actually restrict Jane to editing that one file — it gives her an unauthenticated path to a full interactive root shell, which is a much broader grant than intended and a well-known privilege-escalation pattern (catalogued for many common binaries on GTFOBins). The fix depends on the real requirement: if she genuinely just needs to edit that file, a small wrapper script with no shell-escape surface (or a tool with a real restricted/rbash mode) scoped via `sudoers` is safer than granting raw `sudo` on a general-purpose editor. I'd also audit the rest of `/etc/sudoers` and `/etc/sudoers.d/` for the same pattern against other shell-capable binaries, since this is rarely a one-off mistake once it's been made once.
_What the interviewer is probing for:_ Recognizing that command-name specificity doesn't equal scope specificity, and proposing a concrete, safer alternative rather than just flagging the problem.

**🎯 Architect:** _"Design the `sudo`/`sudoers` governance model for a fleet managed by a mix of Ansible-driven config management and occasional manual admin access. What do you standardize on?"_
**Model answer:** I'd push every grant into named, purpose-scoped files under `/etc/sudoers.d/` managed idempotently by Ansible — never hand-editing the base `/etc/sudoers` file for routine grants — so each grant is independently reviewable, revocable by deleting one file, and has a small, auditable blast radius per change. I'd require every proposed command grant to be checked against GTFOBins-style shell-escape risk before merging, banning raw `sudo` on general-purpose editors/pagers/interpreters in favor of narrow wrapper scripts with no escape surface, and I'd forbid wildcard command paths unless the subcommand surface has been explicitly reviewed. I'd standardize on `NOPASSWD` only for narrowly-scoped, low-risk operational commands (service restarts, specific read-only diagnostics) and require a password prompt for anything broader. Group-based access (`%sudo`/`%wheel`, correctly matched to the distribution family) would be the default onboarding mechanism rather than per-user rules, kept consistent with [§26](./Section-26-Part4-User-Group-Management-Commands.md)'s `usermod -aG` conventions. For visibility, I'd centralize `/var/log/auth.log`/`/var/log/secure` sudo events into whatever log pipeline the fleet uses ([§92](../Part12/Section-92-Part12-Kernel-Hardening-Sysctl-Security-Parameters.md)'s auditd coverage extends this further for compliance-grade requirements), specifically watching for `NOPASSWD: ALL`-style rules added during incidents and never revoked, since that's the most common way a disciplined `sudoers` policy quietly degrades over time.
_What the interviewer is probing for:_ Systems-level governance — drop-in file discipline, shell-escape risk review, and log-driven detection of policy drift — not just knowledge of individual `sudoers` syntax.

## 12. Key Takeaways

- `sudo` and `su -` solve the same underlying problem — becoming root — with fundamentally different models: per-command attributable elevation versus a full identity-switched shell.
- `sudo` itself is a SUID-root binary ([§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md)'s tie-in) — SUID grants the raw OS-level capability; `/etc/sudoers` policy is the second-stage authorization check on top of it, which is why unpatched `sudo` CVEs are a direct root-escalation risk.
- Always edit `/etc/sudoers` with `visudo` (or `visudo -f` for a `sudoers.d` file) — its locking and pre-save syntax validation is what makes a lockout-inducing typo structurally impossible, not just discouraged.
- Core syntax is `who where=(as_whom) command`, with `NOPASSWD:` waiving the password prompt for specific commands — and the `sudo`/`wheel` group convention differs by distribution family (Debian/Ubuntu vs. RHEL-family).
- `/etc/sudoers.d/` drop-in files are the modern preferred approach over editing the monolithic file — better isolation, config-management friendliness, and per-grant revocability.
- `sudo -l` shows the fully resolved permission set across the base file and all drop-ins; `/var/log/auth.log` (Debian-family) or `/var/log/secure` (RHEL-family) records every attempt, successful or refused.
- Session caching (`timestamp_timeout`, 15 minutes by default) means not every `sudo` call re-prompts — `sudo -k` forces immediate re-authentication when that matters.
- The single biggest `sudoers` footgun is granting `sudo` on shell-capable binaries (`vim`, `less`, interpreters) — narrow-looking command grants can be full unrestricted root via a built-in shell escape.

## 13. Related Concepts & What's Next

This section builds directly on [§26](./Section-26-Part4-User-Group-Management-Commands.md)'s `usermod -aG sudo`/`wheel` group-membership pattern, covered above in the Debian-vs-RHEL convention section, and [§28](./Section-28-Part4-Special-Permissions-SUID-SGID-Sticky-Bit.md)'s SUID mechanism, which `sudo` itself is the canonical real-world instance of, as the SUID-root binary section above shows. [§32](./Section-32-Part4-PAM-Overview.md) (next) covers PAM — the pluggable authentication framework `sudo` actually calls into to verify a password before consulting `/etc/sudoers`, completing the authentication-plus-authorization picture this section only covered the authorization half of. Part 12's security hardening coverage ([§89](../Part12/Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)–[§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md)) returns to `sudo` from a compliance and auditing angle — `auditd`/`ausearch` ([§92](../Part12/Section-92-Part12-Kernel-Hardening-Sysctl-Security-Parameters.md)) build on the same log data introduced in the logging section above, and CIS Benchmarks ([§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md)) formalize several of this section's footgun warnings, covered above, as checkable hardening controls.

**Next Section:** [§32](./Section-32-Part4-PAM-Overview.md) — `Section-32-Part4-PAM-Overview.md`
