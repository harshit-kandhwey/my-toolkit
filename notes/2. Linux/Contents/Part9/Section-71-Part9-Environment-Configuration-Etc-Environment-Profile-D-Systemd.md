# Section 71 (Part 9): Environment Configuration: /etc/environment, profile.d, systemd Environment Files

## 1. The Question This Section Answers

"Where do I set an environment variable so that _X_ picks it up?" sounds like it should have one answer. On Linux it doesn't — it has at least four, and they apply in genuinely different, non-overlapping contexts. §41 already walked through the shell-level load order (`/etc/profile`, `~/.bash_profile`, `~/.bashrc`, and friends) for interactive and login shells specifically. This section covers the layer §41 deliberately deferred: the **system-wide, non-shell-specific** environment mechanisms — `/etc/environment`, `/etc/profile.d/`, and systemd's own, entirely separate environment machinery — and, most importantly, the boundary between them that trips up more production deployments than almost any other environment-configuration detail.

The organizing insight for this whole section is that these are **layers that don't all apply in the same context**. Picking the wrong one doesn't usually produce an error — it produces a variable that's silently missing exactly where you needed it, discovered hours later when a service that "obviously" should see it doesn't.

> 💡 **Tip:** Before setting any environment variable system-wide, ask one question first: _who or what is going to read this — a human's login shell, or a systemd-managed daemon?_ Nearly every mistake in this area comes from answering that question implicitly instead of explicitly.

## 2. `/etc/environment`: The One True "Set This Everywhere" File

`/etc/environment` is the closest thing Linux has to a single, unconditional "apply this variable to every login, regardless of shell" mechanism. Its defining characteristic, and the one most often gotten wrong, is that it is **not a shell script**:

```text
PATH="/usr/local/bin:/usr/bin:/bin"
JAVA_HOME="/usr/lib/jvm/default-java"
EDITOR="vim"
```

- **Simple `KEY=value` pairs only** — one per line, optionally quoted. No variable expansion (`$PATH` inside the file does not reference the shell's `$PATH`), no `export` keyword, no command substitution, no conditionals, no comments beyond what the parser happens to ignore. It is deliberately closer to a flat key-value config file than a script.
- **Read by PAM**, specifically `pam_env.so`, during the login process itself — before any shell has even started. This is the mechanism's defining property: it applies to **every login session on the system regardless of which shell the user ends up in** (bash, zsh, or anything else), because it's injected at the PAM layer, upstream of shell selection entirely.
- Because it's parsed by PAM rather than sourced by a shell interpreter, trying to write shell logic into it — `if` statements, `$(command)` substitution, referencing another variable defined earlier in the same file — simply doesn't work. The parser doesn't understand shell syntax at all; it understands `KEY=value`, full stop.

This makes `/etc/environment` the right tool for exactly one job: a small number of **static, unconditional, shell-agnostic** values that genuinely need to exist for every interactive login on the box — a system-wide `JAVA_HOME`, a corporate proxy setting, an addition to the system `PATH`. It is the wrong tool the moment the value needs any logic (a hostname-dependent value, a conditional default, anything computed) — for that, §3's `profile.d` is the mechanism, at the cost of no longer being shell-agnostic.

> ⚠️ **Warning:** `/etc/environment` is read by PAM at login time, not re-evaluated per shell invocation — changes to it take effect for **new** login sessions only. Editing the file does not retroactively update variables in a session that's already running, a common source of "I set it and it's still not there" confusion during live troubleshooting.

## 3. `/etc/profile.d/*.sh`: Login-Shell Scripts With Real Logic

Where `/etc/environment` is a flat data file, `/etc/profile.d/` is a directory of genuine shell scripts, with real conditionals, command substitution, and arbitrary logic available. The connection back to §41's load order is direct: `/etc/profile` — the first file bash reads on login (§41) — conventionally contains a loop that sources every `*.sh` file under `/etc/profile.d/` as part of its own execution:

```bash
# excerpt of the sourcing pattern inside /etc/profile
if [ -d /etc/profile.d ]; then
  for i in /etc/profile.d/*.sh; do
    if [ -r "$i" ]; then
      . "$i"
    fi
  done
fi
```

Because these are sourced as part of `/etc/profile`, they inherit exactly `/etc/profile`'s applicability from §41's table: **login shells only** — an SSH session or a fresh TTY login, not a new terminal tab opened inside an already-running desktop session (that case reads only `~/.bashrc`, per §41, and never touches `/etc/profile.d/` at all).

What `profile.d` buys over `/etc/environment` is real shell capability:

```bash
# /etc/profile.d/company-tooling.sh
if [ -d /opt/company-tools/bin ]; then
  export PATH="$PATH:/opt/company-tools/bin"
fi

if command -v aws >/dev/null 2>&1; then
  export AWS_DEFAULT_REGION="us-east-1"
fi
```

Package maintainers use this pattern constantly — installing a package that needs an environment tweak (a JDK installer adding to `PATH`, a language runtime setting a version manager hook) is one of the most common real-world sources of files appearing under `/etc/profile.d/` without an administrator having written them by hand. Splitting the directory into one file per concern, rather than one monolithic `/etc/profile`, also keeps package-managed and hand-written entries from colliding.

## 4. The Boundary That Actually Matters: Neither of These Applies to systemd Services

This is the single most consequential fact in the whole section, and it's the reason this topic earns its own place in Part 9 rather than being folded into §41: **a systemd-managed service does not go through a login shell, and it does not go through PAM's login-time environment setup, at all.**

Walk through why. `/etc/environment` is read by PAM during an interactive login. `/etc/profile.d/` is sourced by `/etc/profile`, which is itself only read by a bash **login shell**. A systemd unit started by `systemctl start myservice` is launched directly by the systemd manager (PID 1 or a user-session instance) via `fork()`/`exec()` of the configured `ExecStart=` binary — there is no login, no PAM session setup for that exec, and no shell in the picture at all unless the unit's `ExecStart=` explicitly invokes one. A daemon started this way inherits none of §2's PAM-injected variables and none of §3's `profile.d` exports, no matter how carefully either was configured.

> ⚠️ **Warning:** "It works when I run it manually but fails as a systemd service" is one of the most common environment-related production bugs, and it is almost always this exact mismatch. An administrator SSHes in (a login shell — `/etc/environment` and `/etc/profile.d/` both apply), runs the application binary by hand, and it works because `JAVA_HOME`, a proxy variable, or an API key happens to be set in their interactive session. The same binary, launched by systemd as a service, starts with none of that — because systemd services never pass through the login path those variables were injected at. The fix is never "make the login environment more thorough"; it's supplying the variable through one of §5's systemd-native mechanisms, which are the only things a service process actually inherits from.

This is a direct, more severe cousin of the cron gotcha §39 flagged in its own Warning — cron jobs run non-login, non-interactive shells and so skip shell config files; systemd services skip an even larger set of mechanisms, because they skip the login/PAM path those shell config files depend on in the first place.

## 5. systemd's Own Environment Mechanisms

Because services need environment configuration too, systemd provides its own set of mechanisms — layered from most-specific to broadest, and entirely separate from everything in 2–3.

### 5.1 `Environment=` — Inline, Per-Unit

Covered in operational depth in §67 §8; recapped here for completeness of the layering picture:

```ini
[Service]
Environment=NODE_ENV=production
Environment=LOG_LEVEL=info
```

Sets one or more variables directly inside the unit file. Fine for a small number of fixed, non-sensitive values — but every line is plainly visible to anyone who can read the unit file or run `systemctl show`, so it's the wrong place for secrets (§67 §8 covers that caveat in full).

### 5.2 `EnvironmentFile=` — Loaded From a Separate File

```ini
[Service]
EnvironmentFile=/etc/myapp/myapp.env
EnvironmentFile=-/etc/myapp/myapp.local.env
```

Points the unit at a flat `KEY=value` file (`/etc/myapp/myapp.env`), similar in format to `/etc/environment` — loaded at service start, not baked into the unit file itself. This is the natural place for values that change per-environment (dev/staging/prod) without editing the unit, or for values kept outside version control. The leading `-` on the second line marks the file optional — systemd won't fail the unit if it's missing, a pattern §67 also covers for layering a base file with an optional local override.

### 5.3 `/etc/systemd/system.conf` and `DefaultEnvironment=`

For a variable that should apply to **every** service the systemd manager runs, not just one, `/etc/systemd/system.conf` supports a `DefaultEnvironment=` directive:

```ini
[Manager]
DefaultEnvironment="HTTP_PROXY=http://proxy.internal:3128" "NO_PROXY=localhost,127.0.0.1"
```

This requires a full systemd manager reload (or reboot) to take effect for already-running units, since it's read at manager startup, not per-service-start.

### 5.4 `systemctl set-environment` — Runtime, Manager-Wide

```bash
$ sudo systemctl set-environment HTTP_PROXY=http://proxy.internal:3128
$ systemctl show-environment
$ sudo systemctl unset-environment HTTP_PROXY
```

Sets a manager-wide variable at runtime, without editing any file — it affects units started **after** the command runs (already-running services don't retroactively pick it up), and it doesn't survive a reboot unless paired with a persistent mechanism like 5.3. Useful for one-off operational changes or for scripted provisioning that needs to inject a value before starting a batch of services, less suitable as the permanent source of truth for a value that should always be set.

## 6. Decision Guide

| Need                                                                                | Mechanism                                                                                                                              |
| ----------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| A static value for **every interactive login**, regardless of shell                 | `/etc/environment` (2)                                                                                                                 |
| A value needing **shell logic** (conditionals, `PATH` appends) for **login shells** | `/etc/profile.d/*.sh` (3)                                                                                                              |
| A value for **one specific systemd service**                                        | Unit file `Environment=` (small, non-secret) or `EnvironmentFile=` (larger, per-environment, or file-based secrets handling) (5.1–5.2) |
| A value for **all systemd-managed services**, persistently                          | `/etc/systemd/system.conf`'s `DefaultEnvironment=` (5.3)                                                                               |
| A value for **all systemd-managed services**, at runtime, non-persistent            | `systemctl set-environment` (5.4)                                                                                                      |

The recurring failure mode this table exists to prevent: reaching for a login/shell-layer mechanism (2 or 3) because that's the tool that's habitually reached for, when the actual consumer is a systemd service that will never see it (4).

## 7. Common Misconceptions

1. **"If I put it in `/etc/environment`, every process on the system will see it."** Only processes descended from a PAM-managed login session see it — systemd services, launched directly by the systemd manager, never go through that path at all (4). "Every process" is not the same as "every login shell."
2. **"`/etc/environment` is just another shell config file, like `/etc/profile`."** It's parsed by PAM as flat `KEY=value` data, not sourced by a shell — no `export`, no expansion, no logic. Writing shell syntax into it doesn't error loudly; it just doesn't do what was intended (2).
3. **"A systemd service inherits whatever environment the admin who enabled it had."** It doesn't — `systemctl enable`/`start` launches the unit fresh via the systemd manager, not by forking from the administrator's own shell, so none of that shell's exported variables carry over unless explicitly supplied through §5's mechanisms.
4. **"`EnvironmentFile=` and `/etc/environment` are basically the same format, so they're interchangeable."** The file format is similar (flat `KEY=value`), but the consumer is different — one is read by PAM at login, the other is read by systemd when starting a specific unit. Pointing a unit's `EnvironmentFile=` at `/etc/environment` itself is technically possible but conflates two mechanisms meant to serve different audiences, and mixes unrelated values into one file.

## 8. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `/etc/environment` and `/etc/profile.d/`?"_
**Model answer:** `/etc/environment` is a flat `KEY=value` file, not a shell script — no expansion, no logic, no `export` keyword — read by PAM during login for every user regardless of which shell they end up using. `/etc/profile.d/*.sh` files are real shell scripts, sourced by `/etc/profile` during a **login shell**'s startup specifically, so they can contain conditionals and command substitution but only apply to login shells, not every login session's PAM-level setup and not non-login interactive shells.
_What the interviewer is probing for:_ Whether the candidate knows the format distinction (data file vs. script) and the applicability distinction (PAM/every-shell vs. login-shell-only), not just that both files "set environment variables somewhere in `/etc`."

**🎯 Intermediate:** _"Why does a variable set in `/etc/environment` not show up in a systemd service's process environment?"_
**Model answer:** `/etc/environment` is injected by PAM as part of setting up an interactive login session. A systemd-managed service is launched directly by the systemd manager via `fork()`/`exec()` — it never authenticates through PAM's login path and never runs as a login shell, so there's no point in that startup sequence where `/etc/environment`'s values would be injected. The service only sees what's explicitly supplied through systemd's own mechanisms — `Environment=`, `EnvironmentFile=` in the unit, or manager-wide defaults — because those are the only paths a systemd-launched process actually goes through.
_What the interviewer is probing for:_ Understanding that this is a structural consequence of how processes are started (login/PAM path vs. systemd-manager fork/exec), not an arbitrary systemd limitation to be worked around with a workaround like "just add PAM environment reading to the unit."

**🎯 Senior:** _"A colleague says a Python service 'works fine when I run it by hand but fails to find its API key when it's a systemd service.' Walk through your diagnosis and fix."_
**Model answer:** This is the canonical login-shell-vs-systemd-service environment mismatch. Running it "by hand" means an interactive login shell — PAM has already applied `/etc/environment`, and `/etc/profile.d/` (or the colleague's own `~/.bashrc`/`~/.bash_profile`, per §41) has likely exported the API key at some point in their setup. The systemd service, launched by the systemd manager directly, went through none of that — no PAM session, no shell config files — so the variable simply isn't in its environment. I wouldn't chase this by trying to make the service "log in" somehow; I'd confirm the diagnosis quickly with `systemctl show myservice.service -p Environment` and by checking `/proc/<pid>/environ` for the running service versus the manually-run process, then fix it at the correct layer: put the key in an `EnvironmentFile=` referenced by the unit (readable only by the service's user, permissions locked down, since it's a secret) rather than `Environment=` inline, which would leave it visible via `systemctl show`. I'd also flag this as a class of bug worth catching before production — anything that "just works" when run manually needs to be explicitly verified running as the actual systemd service, in a clean environment, before being trusted.
_What the interviewer is probing for:_ Correct root-cause diagnosis of the login-path-vs-manager-fork distinction, a concrete verification method rather than guesswork, and choosing `EnvironmentFile=` over inline `Environment=` for a secret specifically because of the visibility difference.

**🎯 Architect:** _"You're standardizing environment configuration across a fleet of mixed workloads — some interactive admin tooling, dozens of systemd services, and a shared corporate HTTP proxy that everything needs. How do you lay out which mechanism owns what?"_
**Model answer:** I'd split by consumer, not by convenience. For the proxy setting, since it genuinely needs to reach both interactive admin sessions and every systemd service, I'd set it in two places deliberately rather than hoping one covers both: `/etc/environment` for interactive logins (since it's a static, unconditional value with no logic needed — a textbook `/etc/environment` case) and `/etc/systemd/system.conf`'s `DefaultEnvironment=` for the systemd-managed side, accepting that these are two independent settings that happen to carry the same value, not one setting that magically covers both paths. For admin tooling needing conditional logic (version-dependent `PATH` entries, tool-detection guards), that goes in `/etc/profile.d/`, split into one file per concern so package-managed and hand-written entries don't collide. For each systemd service's own configuration — its own API endpoints, feature flags, per-environment values — I'd use `EnvironmentFile=` pointing at a file under that service's own config directory, with secrets kept in a permissions-locked file separate from non-sensitive config, rather than inline `Environment=` lines that `systemctl show` would expose. I'd explicitly document the boundary from 4 somewhere the team will actually see it, because the "works manually, fails as a service" bug report is the single most predictable support ticket this setup will generate if that boundary isn't understood fleet-wide, not just by whoever wrote the units.
_What the interviewer is probing for:_ Fleet-scale judgment that treats the login/systemd boundary as a first-class design constraint rather than an edge case, correct secret-handling instincts (`EnvironmentFile=` over inline `Environment=`), and awareness that documentation of the boundary itself is part of the deliverable, not just the configuration.

## 9. Key Takeaways

- `/etc/environment` is a flat `KEY=value` file (not a shell script — no expansion, no `export`), read by PAM at login for every user regardless of shell — the one true "set this everywhere" mechanism, but limited to static values with no logic.
- `/etc/profile.d/*.sh` files are real shell scripts, sourced by `/etc/profile` as part of §41's login-shell load order — they apply to login shells specifically and support genuine conditionals and command substitution, unlike `/etc/environment`'s flat format.
- Neither `/etc/environment` nor `/etc/profile.d/` applies to systemd services — a service launched by the systemd manager never goes through a login shell or PAM's login-time environment setup, which is the direct cause of the extremely common "works manually, fails as a service" class of bug (4).
- systemd's own mechanisms — `Environment=` and `EnvironmentFile=` in a unit file (full syntax in §67), plus `/etc/systemd/system.conf`'s `DefaultEnvironment=` and runtime `systemctl set-environment` for manager-wide defaults — are the only things a systemd-launched process actually inherits from.
- The decision guide in 6 collapses to one question: who's the consumer — every interactive login (`/etc/environment`), login shells needing logic (`profile.d`), one systemd service (unit file), or all systemd services (manager-wide)?
- Diagnosing a suspected environment mismatch is fast and concrete: `systemctl show <unit> -p Environment` and `/proc/<pid>/environ` show exactly what a running service process actually has, rather than guessing from what an interactive shell happens to see.

## 10. Related Concepts & What's Next

This section is the system-wide, non-shell-specific counterpart to §41's login/non-login shell configuration load order (Part 6) — read together, they cover the full picture of "where does an environment variable actually come from" across both human sessions and systemd services. It builds on §42's variable/`export` fundamentals (Part 6) and goes deeper than §67's brief `Environment=`/`EnvironmentFile=` mention (5.1–5.2) into the full layering picture, including the manager-wide mechanisms §67 didn't cover. §72 (next) moves to time synchronization — `chrony`/`ntpd` and `timedatectl` — a different, more self-contained corner of system administration than this section's cross-cutting environment layering.

**Next Section:** §72 — `Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md`
