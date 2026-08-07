# Section 67 (Part 9): Writing Custom systemd Unit Files

## 1. Overview: Where This Section Sits

[§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) introduced unit files conceptually — declarative configuration replacing SysVinit scripts and Upstart job definitions — and [§66](./Section-66-Part9-Managing-Services-Systemctl.md) covered operating on units that already exist (`systemctl start/stop/enable/status/mask`). This section is where those two threads meet in practice: **writing a real unit file from scratch** for a service that doesn't ship one, the single most common piece of hands-on systemd work an engineer actually does — packaging an internal tool, a custom daemon, a one-off script that needs to survive reboots and crashes, none of which arrive with a vendor-provided `.service` file.

Every directive covered here maps directly onto commands [§66](./Section-66-Part9-Managing-Services-Systemctl.md) already established: `systemctl daemon-reload` after editing a unit file on disk, `systemctl enable --now` to both symlink and start it, `systemctl status` to see whether `Type=` was configured correctly. Treat this section as filling in the file that all of [§66](./Section-66-Part9-Managing-Services-Systemctl.md)'s commands operate on.

## 2. Anatomy of a Unit File: Three Sections

A `.service` unit file is an INI-style text file with (at minimum) three sections, each answering a different question:

| Section     | Question It Answers                                                     |
| ----------- | ----------------------------------------------------------------------- |
| `[Unit]`    | What is this, and what does it depend on / need to come after?          |
| `[Service]` | How do I actually start, stop, and supervise this specific process?     |
| `[Install]` | If someone runs `systemctl enable` on this, where does it get wired in? |

`[Unit]` and `[Install]` are common to every unit type (`.service`, `.timer`, `.mount`, etc. — [§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)); `[Service]` is specific to service units, which is the type this section focuses on since it's what a custom daemon or app needs.

## 3. The `[Unit]` Section in Depth

```ini
[Unit]
Description=My Application Service
After=network.target
Wants=network-online.target
```

- **`Description=`** — a free-text, human-readable summary shown by `systemctl status` and in logs. Not functional, but skipping it makes `systemctl status` output and `journalctl` less useful during an incident — write one line that actually says what the service does, not just its name restated.
- **`After=`** — a **pure ordering** directive: if both units are going to start anyway, start this one after the listed unit(s). `After=network.target` does **not** guarantee the network is actually usable (interfaces up, DNS resolvable) by the time this service starts — it only guarantees systemd has finished whatever it considers "reaching" `network.target`, which can be reached before an interface actually has an address.
- **`Wants=`/`Requires=`** — **dependency strength**, not ordering. `Wants=` is a soft dependency: if the listed unit fails to start, this service still starts anyway. `Requires=` is a hard dependency: if the listed unit fails, this service is pulled down with it. `Wants=` is the far more common, safer default — `Requires=` is easy to reach for and easy to regret, because it means an unrelated dependency failing takes your service down with it even when your service could have run fine without it.
- **`network-online.target`** vs **`network.target`** — this pairing (`After=network.target` + `Wants=network-online.target`) is the idiomatic way to express "start after basic network setup has begun, and actually wait for a working connection first" for services that make outbound calls on startup — `network-online.target` is systemd's closer approximation of "the network is actually usable," at the cost of a slightly slower boot since it waits longer.

> 💡 **Tip:** `After=`/`Before=` control **order**; `Wants=`/`Requires=` control **whether a dependency failing matters**. They're orthogonal and commonly used together (`After=` + `Wants=` on the same target, as above) — declaring only `Wants=` without `After=` means systemd may start both units in parallel with no ordering guarantee at all, which is rarely what's intended for a service that assumes network access on startup.

## 4. The `[Service]` Section: `Type=` — the Single Most Consequential Directive

`Type=` tells systemd **how to know the service has finished starting**, which determines when systemd fires `ExecStart=`-dependent dependents, when `systemctl start` returns, and — critically — whether systemd correctly recognizes a running service as running at all.

| `Type=`   | Meaning                                                                                                                                                                                                                                 | When to Use                                                                                                                                                                                                               |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `simple`  | (Default) The process launched by `ExecStart=` **is** the service — systemd considers it started the instant `fork()`/`exec()` succeeds, with no further signal expected.                                                               | Foreground daemons that don't fork — most modern apps: `node server.js`, `python app.py`, most Go binaries.                                                                                                               |
| `forking` | `ExecStart=` launches a process that **forks and exits**, leaving a child running in the background as the real service — systemd waits for the parent to exit before considering startup complete.                                     | Traditional Unix daemons written to double-fork themselves into the background (nginx, older-style daemons).                                                                                                              |
| `oneshot` | The process is expected to **run to completion and exit** — this isn't a long-running service at all, just a task. Commonly paired with `RemainAfterExit=yes` so `systemctl status` still shows it as "active" after the process exits. | Setup/init tasks, migrations, one-off scripts triggered by a timer ([§69](./Section-69-Part9-Systemd-Timers-Vs-Cron-Deep-Comparison.md)) rather than a persistent process.                                                |
| `notify`  | The process itself tells systemd it's ready via the `sd_notify()` API (`READY=1` over a socket) — systemd waits for that explicit signal rather than guessing from process state.                                                       | Services written with startup-readiness awareness that genuinely have a slow or asynchronous init phase (loading a large model, warming a cache) and want dependents to wait for real readiness, not just process-exists. |

> ⚠️ **Warning:** The most common real-world `Type=` misconfiguration is declaring `Type=simple` (or omitting `Type=` and getting the default) for a program that **actually forks and backgrounds itself**. When that happens, systemd's `ExecStart=` process exits almost immediately (the parent forks and exits, as the program was written to do) — and because `Type=simple` treats "the launched process exited" as "the service died," systemd reports the service as **failed to start**, even though the real daemon is alive and working fine in the background, untracked. The fix isn't a restart policy or a longer timeout — it's the opposite problem: `Type=` doesn't match what the program actually does, and no amount of `Restart=` tuning fixes a `Type=` mismatch. When packaging an unfamiliar binary, check whether it daemonizes itself (many have a `--no-daemonize`/`-D`/foreground flag specifically so they can be run correctly under `Type=simple`) rather than guessing `Type=forking` and hoping.

## 5. `ExecStart=`, `ExecStop=`, `ExecReload=`

```ini
ExecStart=/usr/bin/python3 /opt/myapp/app.py
ExecStop=/bin/kill -TERM $MAINPID
ExecReload=/bin/kill -HUP $MAINPID
```

- **`ExecStart=` requires an absolute path** to the executable — systemd does not consult `$PATH` the way an interactive shell does, since unit files run outside any shell login context by default. `ExecStart=python3 app.py` fails outright; `ExecStart=/usr/bin/python3 /opt/myapp/app.py` (or whatever `which python3` resolves to on the target host) is required. This trips up anyone porting a command that "just works" when typed at a shell prompt.
- **`ExecStop=` is optional** — if omitted, systemd's default stop behavior is to send `SIGTERM` to the main process (and eventually `SIGKILL` if it doesn't exit within `TimeoutStopSec=`), which is correct for most well-behaved processes and is exactly the signal-handling model [§35](../Part5/Section-35-Part5-Process-Lifecycle-Fork-Exec-Wait-Zombie-Orphan.md) covers in depth. Only specify `ExecStop=` when the service needs a different, specific shutdown command — a custom signal, or a wrapper script that needs to run cleanup logic.
- **`ExecReload=`** defines what `systemctl reload myapp` actually does — commonly sending `SIGHUP` ([§35](../Part5/Section-35-Part5-Process-Lifecycle-Fork-Exec-Wait-Zombie-Orphan.md)) to prompt the process to re-read its config without a full restart, if the application supports that. Omitting it means `systemctl reload` isn't meaningfully available for this unit; `systemctl restart` still works regardless.
- **`$MAINPID`** is a systemd-provided variable resolving to the PID systemd is tracking as this service's main process — using it instead of hardcoding a PID-file lookup keeps the unit file simpler and correct even across restarts.

## 6. `Restart=` and `RestartSec=`: The Supervision Policy

```ini
Restart=on-failure
RestartSec=5
```

This is the built-in supervision [§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) described conceptually — no separate process-monitor tool needed.

| `Restart=`   | Behavior                                                                                                                                                              |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `no`         | (Default) Never automatically restart, regardless of exit reason.                                                                                                     |
| `on-failure` | Restart only if the process exited with a **non-zero** code, was killed by a signal, or timed out — a clean, intentional `systemctl stop` does not trigger a restart. |
| `always`     | Restart unconditionally, including after a clean exit or an explicit stop outside `systemctl` — rarely what's actually wanted, since it fights a deliberate stop.     |

`on-failure` is the right default for the overwhelming majority of long-running application services — it recovers from crashes without fighting an administrator's intentional `systemctl stop`. `RestartSec=` sets the delay before each restart attempt (`5` above means a 5-second pause) — without it, a service crash-looping on a bad deploy restarts as fast as it can crash, which can pin CPU and flood logs; a non-trivial `RestartSec=` (and, for genuinely bad cases, `StartLimitBurst=`/`StartLimitIntervalSec=` to give up after N failures in a window) turns an unbounded crash loop into a bounded, diagnosable one.

## 7. `User=` and `Group=`: Running as a Non-Root User

```ini
User=myappuser
Group=myappuser
```

Without `User=`/`Group=`, a service started by systemd's system instance runs as **root** by default — the same over-privileged-by-default problem the principle of least privilege (covered fully in Part 12's security hardening, [§89](../Part12/Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)–[§96](../Part12/Section-96-Part12-CIS-Benchmarks-Compliance-Frameworks.md)) exists to push back on. A web app or background worker almost never needs root; it needs read access to its own code and config, and write access to whatever specific paths it actually writes to (logs, a data directory).

> ⚠️ **Warning:** Running an application as root because "it's simpler" or "it avoids permission errors" converts every vulnerability in that application — an unpatched dependency, a deserialization bug, an unvalidated file-write path — into a full root compromise of the host if exploited. `User=`/`Group=` plus deliberately scoped file ownership (`chown myappuser:myappuser /opt/myapp`) is a small amount of upfront setup that meaningfully bounds the blast radius of almost any application-level vulnerability. Treat a unit file with no `User=` as a finding worth questioning in review, not a neutral default.

The target user/group must already exist (created via `useradd`/`groupadd`, [§26](../Part4/Section-26-Part4-User-Group-Management-Commands.md)) and must have the filesystem permissions the service actually needs — nothing more. `DynamicUser=yes` is a further hardening option worth knowing exists: systemd allocates a transient, unique UID for the service's lifetime with no persistent account on the system at all, though it adds constraints (no writable state outside systemd-managed paths) that don't fit every service.

## 8. `WorkingDirectory=`, `Environment=`, `EnvironmentFile=`

```ini
WorkingDirectory=/opt/myapp
Environment=NODE_ENV=production
Environment=LOG_LEVEL=info
EnvironmentFile=/etc/myapp/myapp.env
```

- **`WorkingDirectory=`** sets the process's current working directory before `ExecStart=` runs — important for any application that reads relative paths (a config file, a `.env` load, relative log paths) assuming it's launched from its own project root, which is not the default behavior of a systemd-launched process otherwise.
- **`Environment=`** sets individual environment variables directly in the unit file — fine for a small, fixed number of non-sensitive values, but every `Environment=` line is plainly visible to anyone who can read the unit file (and to `systemctl show`), so it's the wrong place for secrets.
- **`EnvironmentFile=`** points at an external file of `KEY=value` lines (no quoting/export syntax — just plain assignments) loaded at start time — the better home for larger configs and, with restrictive file permissions (`chmod 600`, owned by the service's own user), a reasonable place for secrets that don't warrant a dedicated secrets-management tool ([§95](../Part12/Section-95-Part12-Secrets-Management-Linux-Hosts.md), covers that territory in full). `EnvironmentFile=-/etc/myapp/myapp.env` (leading `-`) makes a missing file non-fatal, which is a useful pattern for optional local overrides.

Both forms are equivalent to the process's own `os.environ`/`process.env` — this is systemd's answer to "how do I pass config to a service without hardcoding it in the app," parallel to but distinct from `/etc/environment` and `profile.d` ([§71](./Section-71-Part9-Environment-Configuration-Etc-Environment-Profile-D-Systemd.md) covers environment configuration across all of these mechanisms in full).

## 9. The `[Install]` Section: What `systemctl enable` Actually Reads

```ini
[Install]
WantedBy=multi-user.target
```

[§66](./Section-66-Part9-Managing-Services-Systemctl.md) covered `systemctl enable` as a command; this is the configuration it actually acts on. `[Unit]` and `[Service]` matter every time the unit is started or stopped — `[Install]` matters exactly once, at `enable`/`disable` time, and nowhere else. `systemctl enable myapp` reads this section and creates a symlink from the target's `.wants/` directory (e.g. `/etc/systemd/system/multi-user.target.wants/myapp.service`) back to the unit file — that symlink is the entire mechanism by which the service starts automatically on the next boot; `systemctl disable` simply removes it.

`WantedBy=multi-user.target` is the standard pattern for an ordinary background service — `multi-user.target` is what a normal server-mode boot reaches ([§70](./Section-70-Part9-Runlevels-Targets-System-State-Transitions.md) covers targets and the boot-time state graph in full), so a unit `WantedBy=` it starts automatically on every normal boot. A unit file with `[Service]` but no `[Install]` section can still be started manually (`systemctl start myapp`) but `systemctl enable` on it does nothing useful — there's no target relationship for it to wire in, and systemd will say so.

## 10. Full Worked Example: A Python Application Service

Putting 3 through 9 together into one complete, valid unit file for a long-running Python app:

```ini
# /etc/systemd/system/myapp.service

[Unit]
Description=My Application (Python)
After=network.target
Wants=network-online.target

[Service]
Type=simple
User=myappuser
Group=myappuser
WorkingDirectory=/opt/myapp
EnvironmentFile=-/etc/myapp/myapp.env
Environment=PYTHONUNBUFFERED=1
ExecStart=/usr/bin/python3 /opt/myapp/app.py
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

Every line traces back to a directive already explained: `Type=simple` because this is a normal foreground Python process that doesn't fork (4); an absolute-path `ExecStart=` (5); `on-failure` restart with a 5-second backoff so a crash-looping deploy doesn't spin unbounded (6); a dedicated non-root `myappuser` (7); working directory and config file handling (8); and `WantedBy=multi-user.target` so a normal `systemctl enable` wires it into standard boot (9). `PYTHONUNBUFFERED=1` is a small but common real-world addition — without it, Python buffers stdout, and log lines can appear in `journalctl` ([§68](./Section-68-Part9-Journald-Centralized-Logging-Journalctl.md)) late or out of order relative to when they were actually written.

## 11. Workflow: Deploying a Custom Unit File

The end-to-end sequence for taking the file in 10 from disk to running service:

```bash
# 1. Write the file
sudo vi /etc/systemd/system/myapp.service

# 2. Tell systemd to re-read unit files from disk
sudo systemctl daemon-reload

# 3. Enable (create the [Install] symlink) and start in one step
sudo systemctl enable --now myapp
```

`systemctl daemon-reload` is the step [§66](./Section-66-Part9-Managing-Services-Systemctl.md)'s Warning already flagged as easy to forget — systemd caches parsed unit files in memory, and a hand-edited or newly created `.service` file under `/etc/systemd/system/` is invisible to `systemctl start`/`enable` until `daemon-reload` re-parses it. Skipping it after creating `myapp.service` for the first time typically produces a "unit not found" error, not a silent no-op, but skipping it after **editing** an already-loaded unit is more dangerous: the command still succeeds, but against the stale in-memory version, not the file on disk.

`systemctl enable --now` combines what [§66](./Section-66-Part9-Managing-Services-Systemctl.md) covered as two separate commands (`enable` then `start`) into one — the standard, idiomatic way to deploy a new service that should both run immediately and survive the next reboot.

## 12. Validating a Unit File: `systemd-analyze verify`

```bash
sudo systemd-analyze verify /etc/systemd/system/myapp.service
```

**Purpose:** Catch syntax errors, unknown directives, and structural problems in a unit file **before** attempting to start it — much faster feedback than `systemctl start` failing and then digging through `journalctl` to figure out whether the problem was the unit file's syntax or the application itself.

**Expected output:** Silence on success — `systemd-analyze verify` follows the common Unix convention of no output meaning no problems found. Warnings or errors are printed directly, referencing the specific line/directive at fault (a typo'd directive name, a reference to a target that doesn't exist, a `Type=` value that isn't one of the recognized set).

**Common errors:** Running `systemd-analyze verify` and seeing nothing, then assuming the service will definitely behave correctly — verification catches structural/syntax problems, not logical ones like a `Type=` mismatch (4's Warning) where the file is syntactically valid but doesn't describe how the program actually behaves. Verification is a necessary check before deploying, not a substitute for actually starting the service and confirming `systemctl status` shows the state expected.

> 💡 **Tip:** Run `systemd-analyze verify` as a standing step in any deployment pipeline that writes or updates unit files — it's cheap, fast, and catches the class of error ("typo'd `WantedBy=`", "missing `=` on a line") that's otherwise only discovered at the worst possible time, mid-deploy.

## 13. Common Misconceptions

1. **"`Type=simple` is always safe to leave as the default."** It's the default, but only correct when the launched process genuinely doesn't fork into the background — using it against a program that daemonizes itself produces the false "failed to start" behavior in 4's Warning, which is a real, recurring misconfiguration, not a hypothetical.
2. **"`ExecStart=myscript.sh` works the same as typing it at a shell."** systemd doesn't consult `$PATH` or a shell environment by default — `ExecStart=` needs an absolute path, and relies on `WorkingDirectory=`/`Environment=`/`EnvironmentFile=` to supply what an interactive shell would normally provide implicitly.
3. **"Editing the unit file takes effect immediately."** systemd caches parsed units in memory; `systemctl daemon-reload` is required after any change to a unit file on disk before `systemctl start`/`restart`/`enable` sees the new content (11).
4. **"Restart=always is the 'more reliable' choice over on-failure."** `always` also restarts after a clean, intentional stop, which usually isn't wanted — `on-failure` is the correct default for recovering from crashes without fighting a deliberate `systemctl stop` (6).
5. **"Running the service as root is fine since it's an internal tool."** Every application-level vulnerability in a root-run service is a full root compromise if exploited — `User=`/`Group=` costs little setup and meaningfully bounds that risk (7), and this applies just as much to internal tooling as to internet-facing services.

## 14. Tiered Interview Questions

**🎯 Beginner:** _"What are the three main sections of a systemd service unit file, and what does each one do?"_
**Model answer:** `[Unit]` describes what the service is and its ordering/dependency relationships to other units (`Description=`, `After=`, `Wants=`/`Requires=`). `[Service]` describes how to actually run and supervise the process — `Type=`, `ExecStart=`, restart policy, the user to run as, and environment configuration. `[Install]` is only consulted by `systemctl enable`/`disable` — it defines which target's `.wants/` directory gets a symlink to this unit, which is what makes the service start automatically on boot.
_What the interviewer is probing for:_ Whether the candidate understands `[Install]` is fundamentally different in when it matters (enable-time only) versus the other two sections (every start/stop).

**🎯 Intermediate:** _"You write a unit file with `Type=simple` for a daemon that turns out to fork itself into the background. What happens, and how do you fix it?"_
**Model answer:** systemd's `ExecStart=` process — the parent — forks and exits almost immediately, which is exactly what the program is designed to do. But `Type=simple` treats the launched process exiting as the service having stopped, so systemd reports the service as failed to start, even though the actual daemon is alive and running fine in the background, just untracked. The fix is changing `Type=` to `forking` so systemd correctly waits for the parent to exit as the startup-complete signal, rather than treating it as a failure — restart policy tuning doesn't address a `Type=` mismatch at all.
_What the interviewer is probing for:_ Real understanding of `Type=`'s actual mechanism, not just memorized definitions — and recognizing this as a `Type=` problem, not a supervision or timing problem.

**🎯 Senior:** _"Why does `Restart=on-failure` matter more than just 'restart the service if it dies,' and what's the risk of getting the restart policy wrong in either direction?"_
**Model answer:** `on-failure` specifically distinguishes crash/error exits from a clean, intentional stop — it restarts after a non-zero exit, a signal kill, or a timeout, but not after `systemctl stop` or a deliberate clean exit, which respects an administrator's intent. Getting it wrong in one direction — `Restart=no` (or omitted) — means a crashed service just stays down silently until someone notices, no different from SysVinit's lack of supervision that systemd was specifically built to fix. Getting it wrong in the other direction — `Restart=always` without a sane `RestartSec=`/`StartLimitBurst=` — means a service crash-looping on a bad config or bad deploy restarts as fast as it can crash, which can pin CPU, flood `journalctl` with noise that buries the actual error, and in some failure modes make an incident harder to diagnose rather than easier, because the service is bouncing rather than staying down long enough to be a clear signal. The combination of `on-failure`, a non-trivial `RestartSec=`, and a start-limit is what turns supervision into a bounded, diagnosable recovery mechanism rather than either silent downtime or an uncontrolled loop.
_What the interviewer is probing for:_ Depth beyond "restart policies exist" — understanding the failure modes on both sides of the choice and why the specific combination of directives matters together, not any single one in isolation.

**🎯 Architect:** _"You're standardizing how internal services at your company get packaged as systemd units. What does a baseline unit file template enforce, and why?"_
**Model answer:** A few non-negotiables, each tied to a real failure mode this section covers: a correct `Type=` verified against how the actual binary behaves (never guessed) so `systemctl status` and dependent-unit ordering are trustworthy; `User=`/`Group=` set to a dedicated, minimally-privileged account rather than defaulting to root, since every application vulnerability in a root-run service is a full host compromise; `Restart=on-failure` with an explicit `RestartSec=` and start-limit so crashes recover automatically but bounded, rather than either silent downtime or an unbounded crash loop; secrets loaded via `EnvironmentFile=` from a restrictively-permissioned file (or a proper secrets-management integration, [§95](../Part12/Section-95-Part12-Secrets-Management-Linux-Hosts.md)) rather than inline `Environment=` lines that are trivially readable by anyone with unit-file access; and `systemd-analyze verify` run as a required CI step before any unit file change ships, so syntax and structural errors are caught before a deploy rather than during one. The underlying principle is that a unit file isn't just "the command to run" — it's the service's entire supervision, security, and dependency contract with the rest of the system, and a template exists specifically so individual teams don't each independently rediscover the `Type=` mismatch and root-by-default pitfalls this section walks through.
_What the interviewer is probing for:_ Ability to turn section-level tactical knowledge into an organizational standard, and correctly identifying which directives are the ones worth mandating versus leaving to per-service judgment.

## 15. Key Takeaways

- A service unit file has three sections with fundamentally different lifetimes: `[Unit]`/`[Service]` matter on every start/stop, `[Install]` matters only at `enable`/`disable` time, since it's what creates the `.wants/` symlink `systemctl enable` relies on (2, 9).
- `Type=` is the single highest-stakes `[Service]` directive — `simple` for non-forking foreground processes, `forking` for programs that daemonize themselves, `oneshot` for run-to-completion tasks, `notify` for apps with real `sd_notify()` readiness signaling; a `Type=simple`/actual-forking-behavior mismatch produces a false "failed to start" even when the daemon is running fine (4).
- `ExecStart=` requires an absolute path — systemd doesn't consult `$PATH` or provide a shell context by default (5).
- `Restart=on-failure` plus a non-trivial `RestartSec=` is the standard, safe supervision policy — it recovers from crashes without fighting a deliberate `systemctl stop`, and bounds a bad-deploy crash loop rather than letting it spin unbounded (6).
- `User=`/`Group=` running as a dedicated non-root account is a real, low-cost security practice — running as root by default turns any application-level vulnerability into a full root compromise (7).
- `WorkingDirectory=`, `Environment=`, and `EnvironmentFile=` are how a unit file supplies the runtime context (paths, config, secrets) a systemd-launched process doesn't get implicitly the way a shell-launched one does (8).
- The deploy workflow is write the file → `systemctl daemon-reload` (required after any on-disk change, not just first creation) → `systemctl enable --now`, and `systemd-analyze verify` should run before any of that to catch syntax/structural errors early (11, 12).

## 16. Related Concepts & What's Next

This section is the direct operational continuation of [§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)'s conceptual introduction to unit files and [§66](./Section-66-Part9-Managing-Services-Systemctl.md)'s `systemctl` commands — everything here is the file those commands act on. `Type=notify`'s readiness-signaling model and `ExecStop=`'s default `SIGTERM` behavior both connect back to [§35](../Part5/Section-35-Part5-Process-Lifecycle-Fork-Exec-Wait-Zombie-Orphan.md)'s (Part 5) signal-handling coverage, worth revisiting for the mechanics of what a process actually does when it receives `SIGTERM`/`SIGHUP`. [§68](./Section-68-Part9-Journald-Centralized-Logging-Journalctl.md) (next) covers where a custom service's stdout/stderr actually goes by default — journald — which is the natural next step once a service like the one in 10 is running and needs to be observed.

**Next Section:** [§68](./Section-68-Part9-Journald-Centralized-Logging-Journalctl.md) — `Section-68-Part9-Journald-Centralized-Logging.md`
