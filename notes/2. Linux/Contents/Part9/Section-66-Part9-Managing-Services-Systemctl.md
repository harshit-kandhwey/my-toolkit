# Section 66 (Part 9): Managing Services: systemctl

## 1. Overview: From Architecture to Operation

[§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) covered systemd's architecture — units, targets, and how the dependency graph between them drives parallel startup. This section is where that architecture becomes something you actually operate: `systemctl` is the single command-line tool for querying and controlling every unit systemd manages, and it's the tool a working engineer reaches for dozens of times a day on any systemd host. Everything here assumes the vocabulary [§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) built — "unit," "target," "dependency" — and turns it into concrete commands: starting and stopping services, controlling whether they survive a reboot, reading their status output correctly, and the two commands (`mask`/`daemon-reload`) that trip up even experienced administrators when used carelessly.

## 2. The Core Distinction: Runtime State vs. Boot-Time State

This is the single most important thing to internalize in this entire section, and it's worth stating before any individual command: `systemctl` separates **two completely independent questions** about a service, and conflating them is the most common systemd operational mistake.

- **`start` / `stop` / `restart`** control whether a service is running **right now**, in the current boot session. They have no effect on what happens at the next boot.
- **`enable` / `disable`** control whether a service **starts automatically at boot**, by creating or removing a symlink from the unit into the appropriate target's `.wants/` directory ([§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) covered targets and the `.wants/` mechanism). They have **no effect on whether the service is currently running**.

These two axes are **orthogonal** — every combination of the two is a valid, meaningful state a service can be in, and assuming one implies the other is the mistake that produces "but I disabled it, why is it still running" and "I started it, why didn't it come back after the reboot" incidents.

> ⚠️ **Warning:** `enable` does **not** start a service, and `disable` does **not** stop one. Running `systemctl enable nginx` on a freshly installed package leaves nginx enabled-for-next-boot but **not currently running** until something also starts it — a genuinely common gotcha right after installing a new service. Symmetrically, `systemctl disable nginx` on a service that's currently serving traffic leaves it **running right now**, only preventing it from starting at the _next_ boot — it will keep serving traffic until something explicitly stops it or the host reboots. Always reason about these as two separate switches, not one.

The four resulting combinations, worked through concretely:

| Current state | Boot state | How it got there                                                         | Practical meaning                                                                                                                                                                 |
| ------------- | ---------- | ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Started       | Enabled    | `systemctl enable --now nginx`                                           | Running now, will also start on next boot — the normal steady state for a production service                                                                                      |
| Started       | Disabled   | `systemctl start nginx` only (never enabled)                             | Running now, but a reboot will **not** bring it back — common for ad hoc/manual testing, and a frequent source of "it worked yesterday, why is it down after the patching reboot" |
| Stopped       | Enabled    | `systemctl stop nginx` after it was enabled, or `enable` without `start` | Not running now, but **will** start at the next boot — easy to forget, and surprising if someone stopped a service for maintenance without also disabling it                      |
| Stopped       | Disabled   | `systemctl disable --now nginx`                                          | Fully off, both now and across reboots — the correct end state when genuinely decommissioning a service                                                                           |

`systemctl is-active` and `systemctl is-enabled` (7) are the scriptable way to check which of these four cells a service is actually sitting in, rather than assuming from memory.

## 3. Basic Lifecycle Commands: `start` / `stop` / `restart` / `reload`

```bash
sudo systemctl start nginx
sudo systemctl stop nginx
sudo systemctl restart nginx
```

**`start`** launches the unit if it isn't already running; **`stop`** terminates it (systemd sends the signal(s) declared in the unit file, defaulting to `SIGTERM` then `SIGKILL` after a timeout — [§67](./Section-67-Part9-Writing-Custom-Systemd-Unit-Files.md) covers unit-file-level control of this); **`restart`** is a stop followed immediately by a start, unconditionally — it runs even if the service was already stopped, which then just performs a start.

**`reload`** is a distinct, narrower operation:

```bash
sudo systemctl reload nginx
```

`reload` asks the running service to **re-read its configuration without terminating the process** — nginx, for example, can pick up a changed config file this way with zero dropped connections, because the master process forks new workers with the new config while the old workers finish in-flight requests. This is meaningfully different from `restart`, which tears the process down entirely (dropping any in-flight connections or state) and starts a fresh one.

> 💡 **Tip:** `reload` only works if the service's unit file declares an `ExecReload=` directive telling systemd _how_ to ask it to reload (commonly sending `SIGHUP`, or invoking the daemon's own reload subcommand) — not every service supports this, and systemd cannot invent a reload behavior for a service that doesn't implement one. `systemctl reload-or-restart nginx` is the safe default to reach for when you're not sure whether a given unit supports reload: it reloads if `ExecReload=` is defined, and transparently falls back to a full restart if it isn't — appropriate for scripted automation where you don't want to special-case each service's capability.

## 4. `enable` / `disable` and the `--now` Shortcut

```bash
sudo systemctl enable nginx
sudo systemctl disable nginx
```

`enable` creates the symlink(s) that pull the unit into its target's boot sequence (typically `/etc/systemd/system/multi-user.target.wants/nginx.service` → the actual unit file); `disable` removes them. Neither touches the service's current running state (2).

The `--now` flag combines the boot-time and runtime operations into one command, which is what you almost always actually want when bringing a new service into production or fully decommissioning one:

```bash
sudo systemctl enable --now nginx    # enable at boot AND start it right now
sudo systemctl disable --now nginx   # disable at boot AND stop it right now
```

**Production usage example:** After installing a new service package, `systemctl enable --now servicename` in one line is the standard idiom — it's both more concise and less error-prone than running `enable` and `start` as two separate commands where it's easy to run one and forget the other, leaving the service in one of the mismatched states from 2's table without intending to.

## 5. `status`: Reading the Output Correctly

```bash
systemctl status nginx
```

**Example output, annotated:**

```
● nginx.service - A high performance web server
     Loaded: loaded (/lib/systemd/system/nginx.service; enabled; vendor preset: enabled)
     Active: active (running) since Mon 2026-07-27 09:14:02 UTC; 3h 12min ago
       Docs: man:nginx(8)
   Main PID: 1842 (nginx)
      Tasks: 5 (limit: 4678)
     Memory: 12.4M
        CPU: 891ms
     CGroup: /system.slice/nginx.service
             ├─1842 nginx: master process /usr/sbin/nginx
             └─1843 nginx: worker process

Jul 27 09:14:02 web01 systemd[1]: Starting A high performance web server...
Jul 27 09:14:02 web01 systemd[1]: Started A high performance web server.
```

Three lines carry most of the operationally relevant information:

- **`Loaded:`** — confirms the unit file was parsed successfully, shows its **absolute path** (useful for confirming which of several possible unit-file locations is actually in effect — [§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) covers unit-file precedence), and reports **`enabled`/`disabled`/`static`/`masked`** — answering the boot-time half of 2's distinction directly in the status output.
- **`Active:`** — the runtime half of 2's distinction: `active (running)` for a normal running service, `inactive (dead)` for a stopped one, `failed` when the service exited unexpectedly or its start command errored, plus a human-readable **since-when** timestamp showing exactly when it entered that state — invaluable for correlating a service's uptime against a deploy, an incident window, or an unexpected restart.
- **The trailing log lines** — `status` inlines the **most recent journal entries** for this specific unit (sourced from journald, [§68](./Section-68-Part9-Journald-Centralized-Logging-Journalctl.md)) directly in its output, which makes it the fastest first-look during an incident: a failed service's `status` output frequently shows the actual error in the last line or two without needing a separate `journalctl` invocation, though [§68](./Section-68-Part9-Journald-Centralized-Logging-Journalctl.md) covers going deeper when the truncated inline view isn't enough.

**Common errors:** Reading only the `Active:` line and skipping `Loaded:` — a service can be `active (running)` right now while being `disabled`, which is exactly the "started but disabled" cell from 2's table, and easy to miss if you only glance at whether it's currently up.

## 6. `mask` / `unmask`: Stronger Than Disable

```bash
sudo systemctl mask nginx
sudo systemctl unmask nginx
```

`disable` (4) removes a unit from its target's boot sequence, but it doesn't prevent the unit from being started by **other means** — another unit that declares a dependency on it (`Requires=`/`Wants=`, [§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)), or a plain manual `systemctl start nginx`, will still start it successfully even while disabled. `mask` closes that gap entirely: it symlinks the unit file to `/dev/null`, making the unit **completely unstartable by any mechanism** — manual `start`, dependency-driven pulls from other units, everything — until it's explicitly `unmask`ed.

> 💡 **Tip:** Reach for `mask`, not `disable`, when the goal is genuinely "this must never run, even by accident" rather than just "don't start this automatically at boot." A concrete case: two services conflict if both bind the same port, and disabling the one you don't want still leaves it startable if some other unit's dependency chain pulls it in — masking removes that failure mode entirely, because systemd refuses to start a masked unit under any circumstance, dependency-driven or manual.

`systemctl status` on a masked unit shows `Loaded: masked` — distinct from both `enabled` and `disabled` in the `Loaded:` line covered in 5, which is the fastest way to confirm a unit is masked rather than merely disabled.

## 7. Boolean-Style Checks for Scripting: `is-active` / `is-enabled` / `is-failed`

```bash
systemctl is-active nginx
systemctl is-enabled nginx
systemctl is-failed nginx
```

These three commands are built specifically for **automation and scripting**, not human reading — each prints a short single-word answer (`active`/`inactive`/`failed`, `enabled`/`disabled`/`masked`/`static`, `active`/`failed`) and, critically, sets its **exit code** to `0` for the "positive" case and non-zero otherwise, making them directly usable in shell conditionals without parsing `status`'s multi-line output:

```bash
if systemctl is-active --quiet nginx; then
  echo "nginx is running"
fi
```

**Production usage example:** A deploy script that restarts a service and then wants to verify success without scraping `status` text is the canonical use case — `systemctl is-active --quiet servicename && echo ok` (or the equivalent in a CI/CD health-check step) is more robust than grepping `status` output, since `status` formatting is meant for humans and isn't a stable interface to parse against.

## 8. Discovery: `list-units` and `list-unit-files`

```bash
systemctl list-units --type=service
systemctl list-unit-files --type=service
```

These answer two different discovery questions, and the distinction matters:

- **`list-units`** shows units systemd currently **knows about and has loaded** — by default, only active/loaded ones (add `--all` to include inactive units systemd has still loaded into memory). This is "what's actually running or has run recently."
- **`list-unit-files`** shows **every unit file systemd can find on disk**, regardless of whether it's currently loaded, along with its enabled/disabled/static/masked state. This is "what's installed and what will it do at boot," independent of current runtime state.

**Common errors:** Using `list-units` alone to answer "is this service installed on this host" — a unit that's never been started won't appear in `list-units`'s default view, but its unit file (and enabled state) will show up correctly in `list-unit-files` regardless.

## 9. `daemon-reload`: When systemd's Cached View Goes Stale

```bash
sudo systemctl daemon-reload
```

systemd parses unit files once and keeps that parsed representation in memory — it does **not** watch unit files on disk for changes and reload automatically. Editing a unit file (adding an `ExecStart=` argument, changing a `Restart=` policy, adjusting dependencies — all covered in full in [§67](./Section-67-Part9-Writing-Custom-Systemd-Unit-Files.md)) leaves systemd operating against the **old, cached** definition until something explicitly tells it to reread the file.

> ⚠️ **Warning:** This is one of the most common systemd operational mistakes, and it's a genuinely deceptive one because the symptom looks like the edit "didn't take" rather than "wasn't loaded": after editing a unit file, running `systemctl restart servicename` **without** first running `daemon-reload` restarts the process using the **old unit definition** — none of the edits apply, and there's no error or warning telling you this happened. The fix is always: edit the unit file, run `sudo systemctl daemon-reload`, **then** `restart` (or `start`) the affected unit. `daemon-reload` itself does not start, stop, or restart anything — it only makes systemd reparse unit files from disk so that the _next_ start/restart uses the current version.

`daemon-reload` is required specifically for changes to unit files **already known to systemd** (existing services being edited) and for **newly added** unit files before they can be `start`ed or `enable`d for the first time — systemd needs to discover the new file exists before it can act on it.

## 10. Common Misconceptions

1. **"`enable`d means running."** They're orthogonal (2) — a service can be enabled and currently stopped, exactly as validly as it can be started and currently disabled. Always check `Active:` for runtime state and `Loaded:` for boot-time state separately (5).
2. **"`disable` stops a running service."** It only removes the boot-time symlink; a currently running, disabled service keeps running until explicitly stopped (2, 4). `disable --now` is the shortcut when both effects are actually wanted at once.
3. **"`reload` always works, since it's less disruptive than `restart`."** `reload` only works if the unit declares `ExecReload=`; many simple services don't implement any reload behavior at all, and `reload` against one either fails outright or silently does nothing depending on the unit — `reload-or-restart` is the safer default when a unit's capability isn't already known (3).
4. **"`mask` and `disable` are just two words for the same thing."** `disable` only removes automatic boot-time startup; a masked unit cannot be started by any mechanism at all, including another unit's dependency pulling it in — a materially stronger guarantee, appropriate when a service must never run under any circumstance (6).
5. **"Editing a unit file takes effect immediately."** systemd caches parsed unit definitions in memory and does not watch files on disk; `daemon-reload` is required after any unit-file edit before a subsequent `restart`/`start` will actually pick up the change (9).

## 11. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `systemctl start nginx` and `systemctl enable nginx`?"_
**Model answer:** `start` affects whether nginx is running right now, in the current boot session, and has no effect on what happens at the next reboot. `enable` affects whether nginx starts automatically at the next boot, by creating a symlink into the target's `.wants/` directory, and has no effect on whether it's running right now. They're independent — running one doesn't imply the other, so a service can be started-but-disabled or stopped-but-enabled.
_What the interviewer is probing for:_ Whether the candidate has internalized the single most load-bearing distinction in day-to-day systemd operation, rather than treating the two commands as interchangeable synonyms for "turn the service on."

**🎯 Intermediate:** _"You edited a unit file's `ExecStart=` line and ran `systemctl restart`, but the service still behaves like the old configuration. What's going on?"_
**Model answer:** systemd caches parsed unit files in memory and doesn't watch the filesystem for changes, so `restart` alone runs the process against the definition systemd already had loaded, not the edited one on disk. The fix is `systemctl daemon-reload` after the edit, before the restart — that makes systemd reparse unit files from disk so the subsequent restart actually uses the new definition. This is one of the most common systemd gotchas precisely because there's no error message telling you the reload was skipped.
_What the interviewer is probing for:_ Direct familiarity with the daemon-reload gotcha from hands-on experience, not just book knowledge — this is a very common real-world debugging scenario.

**🎯 Senior:** _"When would you reach for `mask` instead of `disable`, and why does the distinction matter operationally?"_
**Model answer:** `disable` only removes a unit from its target's automatic boot sequence — it doesn't stop the unit from being started manually or pulled in as a dependency by some other unit's `Requires=`/`Wants=`. `mask` symlinks the unit to `/dev/null`, making it completely unstartable by any path, including dependency-driven starts. I'd reach for `mask` specifically when two services genuinely conflict — say, both trying to bind the same port — and I need a hard guarantee that the one I don't want can never start, even accidentally via some other package's dependency chain pulling it in during a later install. `disable` alone leaves that failure mode open; `mask` closes it. The trade-off is that masking is a stronger, more deliberate action — it should be reserved for "this must never run" cases, not used reflexively in place of `disable` for routine boot-time management, since it also blocks legitimate manual starts that `disable` would still permit.
_What the interviewer is probing for:_ Understanding mask as solving a specific, narrower problem than disable — not just "a stronger version of the same command" without grasping why the extra strength is sometimes exactly what's needed and sometimes overkill.

**🎯 Architect:** _"You're auditing a fleet and want a script that flags any host where a critical service is in a mismatched or unexpected state — say, enabled but not running, or running but not enabled. How would you build that check?"_
**Model answer:** I'd use `systemctl is-active --quiet servicename` and `systemctl is-enabled --quiet servicename` per host, since both are purpose-built for scripting — clean exit codes rather than text I'd have to parse out of `status`'s human-oriented output, which isn't a stable interface to grep against. I'd cross the two boolean results into the four-state table from 2: active+enabled is the expected steady state for a production service, and I'd flag every other combination for follow-up rather than assuming any one of them is fine by default — active-but-disabled is a real risk because it silently won't survive the next reboot or patching cycle, and enabled-but-inactive on something meant to be always-on is worth investigating for why it's currently down. I'd also run `is-failed` in the same sweep, since a service can be `active` from systemd's perspective in some in-between states while its last start attempt actually failed, and I'd cross-reference `list-unit-files` against the expected service inventory to catch services that are missing entirely, not just misconfigured. For anything genuinely safety-critical — a service that must never run on hosts it doesn't belong on — I'd check for `masked` specifically as the intended state, not just `disabled`, since `disabled` alone doesn't block a dependency-driven start (6).
_What the interviewer is probing for:_ Fleet-scale scripting discipline using the correct purpose-built commands rather than parsing human-readable output, and applying the orthogonal start/enable model systematically rather than checking only one axis.

## 12. Key Takeaways

- `start`/`stop`/`restart` control **current runtime state**; `enable`/`disable` control **boot-time behavior**; the two are completely orthogonal, and conflating them is the most common systemd operational mistake (2) — `enable --now`/`disable --now` (4) combine both when that's genuinely the intent.
- `restart` unconditionally tears down and relaunches a process; `reload` asks a service to re-read its config without a full restart, but only works if the unit declares `ExecReload=` — `reload-or-restart` is the safe scripted default (3).
- `systemctl status` output's `Loaded:` line answers the boot-time question (enabled/disabled/masked + unit file path) and `Active:` line answers the runtime question (running/dead/failed + since-when), with recent journal lines inlined for fast first-look triage (5).
- `mask` is strictly stronger than `disable` — it makes a unit unstartable by any mechanism, including another unit's dependency pull, by symlinking it to `/dev/null`; reserve it for "must never run" cases (6).
- `is-active`/`is-enabled`/`is-failed` are the scriptable, exit-code-driven checks for automation — prefer them over parsing `status` text in any script or health check (7).
- `daemon-reload` is required after editing (or adding) a unit file, before the change takes effect on the next `start`/`restart` — systemd caches parsed units in memory and does not watch the filesystem, and skipping this step fails silently rather than with an error (9).

## 13. Related Concepts & What's Next

This section operates directly on the units and targets [§65](./Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md) introduced architecturally — every `systemctl` command here acts on the unit types and dependency relationships that section established. [§67](./Section-67-Part9-Writing-Custom-Systemd-Unit-Files.md) (next) goes one level deeper, into actually **writing** the unit files whose lifecycle this section manages — `ExecStart=`, `Restart=` policy, `ExecReload=`, and dependency directives like `Requires=`/`After=` all get full syntax treatment there, directly extending the `reload` and `daemon-reload` mechanics introduced here. [§68](./Section-68-Part9-Journald-Centralized-Logging-Journalctl.md)'s `journalctl` deep dive is the natural next stop for diagnosing _why_ a service is `failed` beyond what `status`'s inline log tail (5) shows — the two tools are typically used back-to-back during any real incident: `systemctl status` for the fast first look, `journalctl -u servicename` for the full history.

**Next Section:** [§67](./Section-67-Part9-Writing-Custom-Systemd-Unit-Files.md) — `Section-67-Part9-Writing-Custom-Unit-Files.md`
