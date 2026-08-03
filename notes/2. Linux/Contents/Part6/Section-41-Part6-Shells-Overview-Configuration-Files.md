# Section 41 (Part 6): Shells Overview (bash, sh, zsh) and Shell Configuration Files

## 1. What a Shell Actually Is

§40 closed Part 5 by naming the shell pipe as the everyday IPC mechanism nearly every reader has already used, then handed off to Part 6 to build real fluency on top of it. Before any of that fluency — redirection, pipes, control operators, scripting — makes sense, one thing needs to be nailed down precisely: **a shell is not part of the kernel.** It is an ordinary userspace program, running as an ordinary process with its own PID, that happens to have one specific job: read commands typed by a user (or piped in from a script) and turn them into `fork()`/`exec()` calls against the kernel (§34 covered that lifecycle in full).

That distinction matters more than it first appears:

- The kernel has no concept of "shell." It only knows about processes, system calls, and file descriptors. When a shell runs `ls`, it `fork()`s itself, and the child `exec()`s the `ls` binary — the kernel is just servicing normal process-creation syscalls, indifferent to the fact that a shell orchestrated them.
- Because a shell is a program, there can be more than one **kind** of shell installed on the same system simultaneously, each a separate binary living somewhere under `/bin` or `/usr/bin`, and a user (or a script) can choose which one interprets a given set of commands.
- A shell is both an **interactive command interpreter** (what you type at after logging in) and a **scripting language interpreter** (what runs a `.sh` file's `#!/bin/bash` line, §45) — the same program serves both roles, which is part of why scripting habits and interactive habits sometimes bleed into each other in ways that cause bugs.

> 💡 **Tip:** Every confusion in this section eventually traces back to one thing: there is no single "the shell" on a Linux box. There is a specific binary, selected by a specific mechanism, running in a specific mode (interactive vs. non-interactive, login vs. non-login) — and each of those specifics changes which configuration files load and how commands behave. Get in the habit of asking "which shell, in which mode?" rather than assuming.

## 2. The Major Shells: `sh`, `bash`, `zsh`, and `dash`

### 2.1 `sh` — the POSIX Baseline, Not a Specific Program

`sh` (the "Bourne shell," historically) is best understood as a **standard**, not a single implementation — POSIX defines a baseline set of shell syntax and behavior that any conforming shell must support. On a modern Linux system, `/bin/sh` is essentially always a **symlink** to some other shell running in a POSIX-compatibility mode, not a distinct binary implementing the original 1970s Bourne shell. Which shell `/bin/sh` actually points to varies by distribution, and that variance is the source of the most common real-world gotcha in this entire section, covered in the dash subsection below.

### 2.2 `bash` — the Dominant Default

**bash** (Bourne Again SHell) is the de facto standard interactive and scripting shell across essentially all mainstream Linux distributions — it's what a new user lands in after logging into an Ubuntu, Debian, RHEL, or Fedora box by default. It's a superset of POSIX `sh` syntax, adding arrays, `[[ ]]` extended test syntax, process substitution, associative arrays (bash 4+), and a large set of other conveniences that plain POSIX `sh` does not guarantee (§45 and §47 build hands-on fluency on top of this).

### 2.3 `zsh` — Increasingly Common, macOS's Default

**zsh** (Z shell) is a POSIX-compatible shell that has grown from a power-user niche into a mainstream default — most notably, it has been macOS's default login shell since Catalina (2019), and it's an increasingly common choice for Linux developer workstations. Its draw is largely ergonomic: richer tab-completion, better globbing (extended glob patterns bash doesn't support without extra configuration), and a large plugin ecosystem — **oh-my-zsh** being the best-known framework, bundling themes, prompt customization, and plugin management on top of raw zsh. zsh is close enough to bash syntactically that most everyday interactive commands and simple scripts behave identically, but it is not a drop-in superset — some parameter-expansion and array-indexing behavior differs in ways that can matter for anything beyond trivial scripts.

### 2.4 `dash` — Debian/Ubuntu's Real `/bin/sh`

**dash** (Debian Almquist Shell) is a minimal, POSIX-focused shell whose entire design goal is to be small and fast — no interactive conveniences, no bash extensions, just a lean implementation of the POSIX standard. It matters operationally for one specific reason: on Debian and Ubuntu (and their many derivatives), `/bin/sh` is symlinked to `dash`, not `bash`. RHEL-family distributions, by contrast, typically symlink `/bin/sh` to `bash` itself (running in a restricted POSIX-compliance mode). This split is not a historical footnote — it actively breaks scripts today.

> ⚠️ **Warning:** A script that starts with `#!/bin/sh` but uses bash-specific syntax — `[[ ]]` tests, arrays, `local` in some contexts, `source` instead of `.`, `function name() { }` declarations, string manipulation like `${var//search/replace}` — will run **silently differently, or fail outright**, on any Debian-family system, because `#!/bin/sh` invokes dash there, not bash. It often works fine on the author's RHEL-based dev box (where `/bin/sh` happens to be bash) and then breaks the moment it's deployed to an Ubuntu host or run inside a `debian`/`ubuntu`-based container image. The fix is not "hope it's fine" — either shebang the script `#!/bin/bash` explicitly and require bash to be present, or genuinely restrict the script's syntax to POSIX `sh` and test it against dash directly (`dash myscript.sh`), not just against whatever `/bin/sh` happens to resolve to on the machine you wrote it on.

## 3. Login vs. Non-Login, Interactive vs. Non-Interactive

Which configuration files a shell reads on startup is governed by two independent, orthogonal distinctions — conflating them is the single most common source of "why isn't my `.bashrc` change taking effect" confusion.

- **Login shell vs. non-login shell** — a **login shell** is one started as part of authenticating a session: logging in at a TTY, over SSH, or via `su -`/`su -l` (the `-` explicitly requests a login shell). A **non-login shell** is one started from within an already-running session — opening a new terminal window/tab in a desktop environment, or running `bash` from inside an existing shell. Login shells are expected to set up the environment for the entire session (`PATH`, environment variables); non-login shells inherit whatever environment the parent process already had.
- **Interactive vs. non-interactive shell** — an **interactive** shell is one connected to a terminal, presenting a prompt and reading commands typed by a human. A **non-interactive** shell is one running a script or a single command non-interactively (`bash script.sh`, or a cron job invoking bash) — no prompt, no human at the keyboard. Interactive shells load conveniences like aliases, prompt customization (`PS1`), and completion; non-interactive shells generally skip that entirely for speed and predictability.

These two axes combine into four real combinations, and bash treats each one differently for the purpose of config-file loading:

| Combination                 | Typical real-world example                                               | bash's general behavior                                                                   |
| --------------------------- | ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------- |
| Login + interactive         | SSH-ing into a server; a fresh TTY login                                 | Reads login-shell config files — see the login-shells section below                       |
| Non-login + interactive     | Opening a new terminal tab in an existing desktop session                | Reads `~/.bashrc` only — see the non-login interactive shells section below               |
| Non-login + non-interactive | Running a script (`./deploy.sh`), a cron job                             | Reads neither by default (unless `BASH_ENV` is set, or the script sources one explicitly) |
| Login + non-interactive     | Rare — e.g., some remote-command SSH invocations with `bash -l -c "cmd"` | Reads login-shell config files, runs the command, exits                                   |

## 4. bash Configuration File Load Order

This is the part worth memorizing precisely, because "which file do I edit" questions are a constant, low-grade source of wasted time without it.

### 4.1 Login Shells

On startup, a bash login shell reads, in order:

1. **`/etc/profile`** — the system-wide file, read for every user's login shell regardless of which shell they end up using day-to-day (it's `sh`-syntax by convention, since other shells may source it too). On most distributions it also sources everything under `/etc/profile.d/*.sh` (§72's environment-configuration coverage in Part 9 goes deeper on this pattern).
2. **The first of `~/.bash_profile`, `~/.bash_login`, or `~/.profile` that exists** — bash checks for these in exactly that order and reads only the **first one found**, not all three. This surprises people who edit `~/.profile` expecting it to load, not realizing a stale `~/.bash_profile` from years ago is shadowing it.

Because `~/.bashrc` is **not** in that login-shell list, the conventional pattern — seen in nearly every default `~/.bash_profile` on any mainstream distribution — is for `~/.bash_profile` to explicitly `source ~/.bashrc` itself, so that a login shell still picks up alias/function definitions meant for interactive use. This is a convention, not something bash does automatically — if that `source` line is ever accidentally deleted, a login shell will stop seeing your aliases even though nothing else looks wrong.

### 4.2 Non-Login Interactive Shells

A non-login interactive shell — the far more common case day-to-day, since most terminal windows opened from within a desktop session fall here — reads **only `~/.bashrc`**. `/etc/profile` and the login-shell personal files are not read at all in this mode. This is precisely why aliases and functions are conventionally defined in `~/.bashrc`, while one-time environment setup (`PATH` exports, `umask`) is conventionally left in the login-shell files — a `PATH` export placed only in `~/.bashrc` won't apply to processes that never opened an interactive non-login shell.

### 4.3 System-Wide Interactive Config

Distributions commonly also ship `/etc/bashrc` or `/etc/bash.bashrc` (naming varies — RHEL-family uses `/etc/bashrc`, Debian-family uses `/etc/bash.bashrc`), sourced from within the default `~/.bashrc` template, giving administrators a system-wide hook for interactive-shell behavior without touching every user's home directory individually.

### 4.4 Summary Table

| File                                               | Read by                                                                            | Typical contents                                                        |
| -------------------------------------------------- | ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| `/etc/profile` (+ `/etc/profile.d/*.sh`)           | Login shells (system-wide)                                                         | `PATH`, `umask`, system-wide environment variables                      |
| `~/.bash_profile` / `~/.bash_login` / `~/.profile` | Login shells (per-user, first found only)                                          | Per-user environment setup; conventionally sources `~/.bashrc`          |
| `~/.bashrc`                                        | Non-login interactive shells (and login shells, via the `source` convention above) | Aliases, functions, `PS1` prompt, completion                            |
| `/etc/bashrc` or `/etc/bash.bashrc`                | Interactive shells (system-wide, via `~/.bashrc` sourcing it)                      | System-wide aliases, prompt defaults                                    |
| None by default                                    | Non-login, non-interactive shells (plain script execution)                         | N/A — use `BASH_ENV` or explicit sourcing if config is genuinely needed |

> ⚠️ **Warning:** "I set an environment variable in `~/.bashrc` and my cron job still doesn't see it" is one of the most common tickets rooted directly in this table — cron jobs run non-login, non-interactive shells, which read none of these files by default. The fix is to export the variable somewhere the cron job's execution path actually reads (an explicit `source` line in the script itself, `/etc/environment`, or the cron entry's own environment setting), not to add another line to `~/.bashrc` and hope.

## 5. zsh's Parallel Structure (Brief)

zsh follows a conceptually parallel but separately-named set of files, worth knowing exists even at a conceptual level: `/etc/zshenv` and `~/.zshenv` (read for essentially every zsh invocation, login or not), `/etc/zprofile`/`~/.zprofile` (login shells), `/etc/zshrc`/`~/.zshrc` (interactive shells — this is the one oh-my-zsh and most user customization lives in), and `/etc/zlogin`/`~/.zlogin` (login shells, read after `.zshrc`). The naming maps loosely onto bash's `profile`/`bashrc` split, but the file count and exact ordering differ — treat this as "know the shape exists," not something to memorize to the same depth as bash's load-order table above, since bash remains the default scripting target on Linux.

## 6. Changing a User's Default Shell

The shell a user lands in after logging in — their **default shell** — is recorded in `/etc/passwd`, in the final field of each user's entry (§25's coverage of `/etc/passwd` structure). Changing it is done with `chsh`:

```bash
$ chsh -s /bin/zsh
```

`chsh` will only accept a path listed in **`/etc/shells`** — a plain text file enumerating the shells the system administrator considers valid, legitimate login shells:

```bash
$ cat /etc/shells
/bin/sh
/bin/bash
/usr/bin/bash
/bin/zsh
/usr/bin/zsh
```

This file matters for a reason beyond convenience: some services check membership in `/etc/shells` as a security gate — for example, certain FTP daemons refuse login to an account whose shell isn't listed there, on the theory that an unlisted shell means the account isn't meant for interactive human login at all (a common pattern for service accounts deliberately set to `/usr/sbin/nologin` or `/bin/false`, neither of which appears in `/etc/shells`, specifically to block interactive login while still letting the account own files and run scheduled jobs).

## 7. `$SHELL` vs. What's Actually Running

`$SHELL` is an environment variable set once, at login, to the user's default shell as recorded in `/etc/passwd` — and it is **not** updated if you manually invoke a different shell afterward. Running `zsh` from inside a bash session leaves `$SHELL` still reporting `/bin/bash`, because nothing re-exports it. Treating `$SHELL` as "what shell am I in right now" is a common and incorrect assumption.

The reliable ways to check the **actually running** shell:

- **`echo $0`** — inside an interactive shell, `$0` reports the name of the shell binary itself (e.g., `-bash` for a login bash shell, `zsh` for zsh) — the leading `-` is bash's own convention for signaling a login shell.
- **`ps -p $$`** — `$$` is the PID of the current shell process; asking `ps` to describe that specific PID returns the actual command running as that process, independent of any environment variable that might be stale.

```bash
$ echo $SHELL
/bin/bash
$ zsh
% ps -p $$
    PID TTY          TIME CMD
  48213 pts/0    00:00:00 zsh
```

`$SHELL` still says `/bin/bash` in that example even after switching into zsh — `ps -p $$` is the ground-truth answer, the same "trust the running process, not the label" discipline §13's `ps -p 1 -o comm=` check applied to identifying a host's init system.

## 8. Common Misconceptions

1. **"`/bin/sh` is the original Bourne shell."** On essentially every modern Linux system it's a symlink to some other shell running in POSIX-compatibility mode — dash on Debian/Ubuntu, bash (restricted) on RHEL-family — not a distinct historical binary. Which shell it actually resolves to is distribution-dependent and directly determines whether bash-specific syntax in a `#!/bin/sh` script will work, as the dash subsection above covers.
2. **"`~/.bashrc` and `~/.bash_profile` are basically interchangeable — just put everything in whichever one."** They're read in different, non-overlapping circumstances (login vs. non-login interactive shells) — code that only ever runs from one will silently not run in the other's context, which is exactly why the standard convention has `~/.bash_profile` explicitly source `~/.bashrc` rather than duplicating content, as the login-shells subsection above explains.
3. **"`#!/bin/sh` is safer/more portable than `#!/bin/bash`, so I should always use it."** It's only safer if the script's contents are genuinely restricted to POSIX syntax — using `#!/bin/sh` while writing bash-specific syntax is worse than being explicit, because it fails inconsistently depending on what `/bin/sh` happens to be symlinked to on whatever host runs it, as the dash subsection above covers.
4. **"`$SHELL` tells me what shell I'm currently running."** It tells you the user's configured default login shell, set once at login time and never automatically updated — it does not track shell changes made afterward within the session. `echo $0` or `ps -p $$` are the commands that report the actual running process, as the section above on `$SHELL` versus the actually-running shell details.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What is a shell, and is it part of the Linux kernel?"_
**Model answer:** A shell is an ordinary userspace program — not part of the kernel at all — whose job is to read commands, typed interactively or from a script, and turn them into process creation via `fork()`/`exec()` against the kernel. The kernel has no concept of "shell"; it only sees the resulting syscalls. Because it's just a program, multiple different shells (bash, zsh, dash, and others) can be installed on the same system simultaneously, and which one interprets a given command depends on how it was invoked.
_What the interviewer is probing for:_ Whether the candidate has internalized the kernel/userspace boundary from Part 2 well enough to place the shell correctly on the wrong side of it — a surprisingly common confusion.

**🎯 Intermediate:** _"Why does `#!/bin/sh` sometimes behave differently on different Linux distributions?"_
**Model answer:** `/bin/sh` isn't a fixed program — it's a symlink whose target varies by distribution. Debian and Ubuntu (and derivatives) point it at dash, a minimal shell that only implements the POSIX standard with no bash extensions. RHEL-family distributions typically point it at bash itself, running in a POSIX-compliance mode. A script that uses bash-specific syntax — `[[ ]]`, arrays, certain parameter expansions — under a `#!/bin/sh` shebang will work fine wherever `/bin/sh` happens to be bash and break, sometimes silently, wherever it's dash. The fix is to either shebang `#!/bin/bash` explicitly when bash features are actually used, or genuinely restrict the script to POSIX syntax and test it against dash directly rather than assuming.
_What the interviewer is probing for:_ Real operational awareness of the dash/bash split, not just textbook knowledge that "sh is POSIX" — this is a bug class that shows up constantly in Docker images and cross-distribution automation.

**🎯 Senior:** _"Walk through exactly which config files load when a user SSHes into a Debian server versus when they open a second terminal tab on their already-logged-in desktop."_
**Model answer:** SSHing in starts a login, interactive bash shell, so it reads `/etc/profile` (plus anything it sources from `/etc/profile.d/`), then the first of `~/.bash_profile`, `~/.bash_login`, or `~/.profile` that exists — and by convention that file itself sources `~/.bashrc`, which is how alias and function definitions end up available even though `~/.bashrc` isn't in bash's own login-shell read list. Opening a second terminal tab on an already-logged-in desktop starts a non-login, interactive shell instead — it reads only `~/.bashrc` directly, skipping `/etc/profile` and the personal login files entirely, because the environment those files are responsible for setting up was already established when the desktop session itself logged in. Practically, that means `PATH` exports belong in the login-shell files so they apply once per session, while aliases and prompt customization belong in `~/.bashrc` so they apply in both cases.
_What the interviewer is probing for:_ Precise, ordered recall of the load-order table, not just "there are some config files" — and understanding why the `~/.bash_profile` → `~/.bashrc` sourcing convention exists rather than treating it as arbitrary.

**🎯 Architect:** _"You're auditing a fleet of mixed RHEL and Ubuntu hosts and find deployment scripts shebanged `#!/bin/sh` that use bash arrays. How do you assess and fix this at scale?"_
**Model answer:** I'd treat this as a real, not theoretical, production risk — every Ubuntu/Debian host in the fleet has `/bin/sh` pointed at dash, so any of these scripts will fail the moment they execute an array assignment or other bash-only construct on those hosts, even though they've probably been "working fine" on RHEL boxes where `/bin/sh` happens to be bash, which is exactly the kind of latent bug that survives testing and detonates on the wrong host. First step is inventory: grep the fleet's script repositories for `#!/bin/sh` shebangs combined with bash-specific syntax (arrays, `[[ ]]`, `local`, process substitution) to size the actual exposure rather than assuming. For remediation, the honest fix in almost every case is changing the shebang to `#!/bin/bash` and adding bash as an explicit dependency wherever it isn't guaranteed present — rewriting to strict POSIX syntax is possible but usually more effort than it's worth for internal deployment tooling that isn't trying to be portable to non-Linux POSIX systems. I'd also add a CI check — running `dash -n script.sh` or equivalent syntax-check against every `#!/bin/sh` script in the repo — so a script that's genuinely meant to be POSIX-portable actually gets verified against dash rather than just against whatever `/bin/sh` resolves to on the CI runner itself, closing the gap that let this drift in undetected in the first place.
_What the interviewer is probing for:_ Fleet-scale thinking that goes beyond "fix the shebang" — sizing the actual risk, choosing pragmatic remediation over gold-plating, and building a verification mechanism so the same class of bug doesn't silently reappear.

## 10. Key Takeaways

- A shell is a userspace program, not a kernel component — it turns typed or scripted commands into `fork()`/`exec()` calls, and multiple distinct shells can coexist on one system.
- `sh` names a POSIX standard, not one implementation; `/bin/sh` is a symlink whose actual target (dash on Debian/Ubuntu, bash on RHEL-family) varies by distribution and is the root cause of a real, recurring class of production bugs.
- bash is the dominant interactive/scripting default on Linux; zsh (macOS's default, with a strong plugin ecosystem like oh-my-zsh) is an increasingly common alternative; dash is deliberately minimal and is the actual `/bin/sh` on Debian-family systems.
- Login vs. non-login and interactive vs. non-interactive are independent axes that together determine which config files a shell reads — never assume "my config file" without specifying which combination applies.
- bash's load order: `/etc/profile` then the first of `~/.bash_profile`/`~/.bash_login`/`~/.profile` for login shells; `~/.bashrc` alone for non-login interactive shells; nothing by default for non-login non-interactive shells (scripts, cron).
- `chsh -s <path>` changes a user's default shell, restricted to paths listed in `/etc/shells` — a file some services also use as a security gate against interactive login.
- `$SHELL` reflects the login-time default and is not updated when a different shell is invoked mid-session; `echo $0` or `ps -p $$` report the actually-running shell, the same ground-truth-over-label discipline §13 applied to identifying a host's init system.

## 11. Related Concepts & What's Next

This section opens Part 6 by naming the program §40 closed Part 5 by demonstrating the effect of — the shell that turns a pipeline like `ls | grep` into the pipe-connected processes §40 described at the kernel level. It leans on §25's `/etc/passwd` structure for the default-shell field, covered above in the default-shell section, and echoes §13's "trust the running process over the label" discipline in distinguishing `$SHELL` from the actually-running shell, covered above. §42 (next) moves from "which shell, which config files" into shell basics proper — variables, quoting, and expansion — the vocabulary every later Part 6 section assumes. §45 returns to this section's shell-selection material when it introduces bash scripting fundamentals and the shebang line in full.

**Next Section:** §42 — `Section-42-Part6-Shell-Basics-Variables-Quoting-Expansion.md`
