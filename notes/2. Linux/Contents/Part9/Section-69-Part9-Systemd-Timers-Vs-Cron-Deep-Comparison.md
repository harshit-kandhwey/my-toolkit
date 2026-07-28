# Section 69 (Part 9): systemd Timers vs. cron (Deep Comparison)

## 1. Where This Picks Up

§39 (Part 5) introduced systemd timers only conceptually, deliberately deferring full unit-file syntax to Part 9 rather than duplicating it early — this section is that promised deep dive. Everything in §39's 7 and 8 (the `.timer`/`.service` pairing idea, `OnCalendar=` vs. `OnBootSec=`/`OnUnitActiveSec=`, `Persistent=true`, and the high-level comparison table) is assumed as background here and not re-derived; this section's job is to make it concrete and hands-on: real `.timer` file syntax, a worked example, `systemctl list-timers`, manual testing, and an expanded comparison that goes well past §39's conceptual pass.

A `.timer` unit is, structurally, just another unit type alongside the `.service` units §67 covered — it uses the same `[Unit]`/`[Install]` sections and the same `systemctl`/`systemd-analyze` tooling §66/§67 already established. The only genuinely new section is `[Timer]`.

## 2. Anatomy of a `.timer` Unit File

```ini
# /etc/systemd/system/backup.timer

[Unit]
Description=Run backup.service on a schedule

[Timer]
OnCalendar=Mon..Fri 02:30:00
Persistent=true

[Install]
WantedBy=timers.target
```

`[Unit]` and `[Install]` behave exactly as they do for a `.service` file (§67): `Description=` is free-text shown by `systemctl status`/`list-timers`, and `[Install]`'s `WantedBy=timers.target` is what `systemctl enable` actually wires up — `timers.target` is the standard target that pulls in enabled timers at boot, parallel to `multi-user.target` for ordinary services (§70 covers targets in full). The section that's new here is `[Timer]`.

## 3. `OnCalendar=`: Wall-Clock Schedules

`OnCalendar=` is the calendar-based trigger — the closest conceptual analog to a crontab's five fields, but readable as an actual calendar expression rather than five terse numeric columns:

| `OnCalendar=` expression  | Meaning                                                  |
| ------------------------- | -------------------------------------------------------- |
| `daily`                   | Once a day, at midnight (shorthand for `*-*-* 00:00:00`) |
| `weekly`                  | Once a week, Monday at midnight                          |
| `hourly`                  | Once an hour, on the hour                                |
| `Mon..Fri *-*-* 09:00:00` | 9:00 AM, Monday through Friday                           |
| `*-*-* 00,12:00:00`       | Twice a day, midnight and noon                           |
| `Mon *-*-1..7 02:00:00`   | The first Monday of every month, at 2:00 AM              |

The general form is `weekday year-month-day hour:minute:second`, with `*` meaning "any" in each position — structurally similar to cron's wildcard idea, but with named weekdays, comma lists, and ranges spelled out explicitly instead of packed into terse numeric fields. `daily`/`weekly`/`hourly`/`monthly`/`yearly` are shorthand aliases for the most common cases, so the trivial "once a day" schedule doesn't require writing out a full expression.

> 💡 **Tip:** Never guess whether an `OnCalendar=` expression parses the way intended — `systemd-analyze calendar "Mon..Fri *-*-* 09:00:00"` parses the expression and prints exactly when it next fires (and several runs after that), without creating or touching any unit at all. Run this before deploying any non-trivial calendar expression; it's the calendar equivalent of `systemd-analyze verify` (§67) for unit-file syntax.

## 4. `OnBootSec=` and `OnUnitActiveSec=`: Monotonic/Relative Triggers

Where `OnCalendar=` anchors to a wall-clock point, these anchor to an **event**, with no cron equivalent at all:

```ini
[Timer]
OnBootSec=15min
OnUnitActiveSec=6h
```

- **`OnBootSec=`** fires a fixed duration after the system boots — `OnBootSec=15min` means "15 minutes after this boot," regardless of what wall-clock time that happens to be. Useful for startup housekeeping that should run once per boot but doesn't need to coincide with boot itself (giving other services time to settle first).
- **`OnUnitActiveSec=`** fires a fixed duration after **this timer unit was last activated** — `OnUnitActiveSec=6h` means "6 hours after the last time this timer ran," which produces a recurring interval schedule anchored to actual run history rather than a fixed clock time. This is the systemd equivalent of `*/360 * * * *` in spirit, but self-relative rather than wall-clock-aligned — if the timer's own activation slips (a delayed boot, a long-running previous job), the next run slips with it rather than snapping back to the nearest clock boundary.

Both can be combined with `OnCalendar=` on the same timer, though mixing monotonic and calendar triggers on one unit is unusual outside specific bootstrap-then-recur scenarios and is worth a comment in the unit file explaining why if done.

## 5. `Persistent=true`: The Concrete Advantage Over Cron

```ini
[Timer]
OnCalendar=daily
Persistent=true
```

`Persistent=true` tells systemd to record the last time this timer actually fired. If the system was powered off, suspended, or the timer unit itself was inactive at the moment a scheduled run should have occurred, systemd runs it **once, as soon as the system is next able to** — rather than silently skipping straight to the next scheduled occurrence, which is cron's unconditional default behavior (§39, 5 and 8) for any minute the host was down.

This matters concretely on laptops, dev VMs that get suspended overnight, or any host that isn't guaranteed 24/7 uptime: a `daily` backup timer without `Persistent=true` on a machine that's routinely off at 2 AM simply never runs unless the host happens to be up at exactly that moment. With `Persistent=true`, it runs once at next boot/wake instead, catching up the missed execution.

> ⚠️ **Warning:** `Persistent=true` catches up **one** missed run, not every run that was missed — a host down for three days with a `daily` timer doesn't fire three catch-up runs on boot, it fires once. It's a "don't let this fall through the cracks entirely" guarantee, not a queue-and-replay mechanism. For jobs where every missed occurrence genuinely needs to happen (not just "at least once, eventually"), the timer alone isn't sufficient — that requires application-level logic tracking what was actually processed.

## 6. The Timer-Plus-Service Pairing Pattern in Full

A `.timer` unit never runs a command directly — it only ever activates a same-named unit, by default the `.service` unit sharing its base name (`backup.timer` → `backup.service`, unless overridden with `Unit=` inside `[Timer]`). The service unit is a completely ordinary unit built exactly as §67 describes, almost always with `Type=oneshot` since a timer-triggered job is a task that runs to completion and exits, not a persistent background process:

```ini
# /etc/systemd/system/backup.service

[Unit]
Description=Run the nightly backup script

[Service]
Type=oneshot
User=backupuser
ExecStart=/opt/scripts/backup.sh
```

Notice this service file has **no `[Install]` section**. That's deliberate and correct — `[Install]` is only relevant to units that get enabled directly (§67, 9), and a timer-triggered service is never enabled or started at boot on its own; the timer is what's enabled, and the timer is what pulls the service in when it fires. Enabling `backup.service` directly would be a no-op at best and a source of confusion at worst.

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now backup.timer
```

`systemctl enable --now backup.timer` does two things: `enable` creates the `[Install]`-driven symlink into `timers.target.wants/` so the timer itself starts on every boot, and `--now` starts the timer immediately in the current session. Critically, this **does not** run `backup.service` right away — it only starts the timer counting toward its next scheduled activation (per `OnCalendar=`/`OnBootSec=`/`OnUnitActiveSec=`). `backup.service` itself stays inactive until the timer actually fires.

> 💡 **Tip:** `enable --now` on the `.timer`, never on the paired `.service` — this is the single most common point of confusion for anyone coming from cron's mental model, where "the job" and "the schedule" are the same line. Under systemd they're two separate units with two separate lifecycles, and only the timer gets enabled.

## 7. `systemctl list-timers`: Visibility Cron Doesn't Have

```bash
$ systemctl list-timers --all
NEXT                        LEFT     LAST                         PASSED   UNIT           ACTIVATES
Mon 2026-07-27 02:30:00 UTC 8h left  Fri 2026-07-24 02:30:00 UTC  2 days   backup.timer   backup.service
Tue 2026-07-28 00:00:00 UTC 30h left n/a                          n/a      cleanup.timer  cleanup.service
```

Every column here is information cron structurally has no single command for: **NEXT**/**LEFT** show exactly when a timer will next fire and the countdown to it; **LAST**/**PASSED** show when it last actually activated and how long ago; **ACTIVATES** shows which service it triggers, making the timer-to-service relationship explicit rather than requiring the reader to infer it from naming convention alone. `--all` includes inactive/disabled timers as well as active ones; without it, only currently-active timers are listed.

Auditing what's scheduled on a box via cron means checking every user's `crontab -l`, `/etc/crontab`, every file in `/etc/cron.d/`, and four convenience directories (§39, 8) — `systemctl list-timers --all` is that entire audit surface collapsed into one command, for the systemd-managed half of a host's scheduled work.

## 8. Testing a Timer's Service Manually

A timer-triggered service is still just an ordinary service unit, which means it can be started directly, completely independent of its timer:

```bash
sudo systemctl start backup.service
```

This runs `backup.service` immediately — right now, synchronously with respect to systemd's scheduling — without touching `backup.timer` at all or waiting for its next scheduled occurrence. This is the standard way to validate that the job itself actually works (correct `ExecStart=`, correct permissions, correct environment) before trusting the timer to fire it unattended, and it's meaningfully faster feedback than editing `OnCalendar=` to something a minute in the future, waiting, then reverting it back.

```bash
journalctl -u backup.service
```

confirms what happened on that manual run — output and exit status flow through journald exactly as they do for any other service (§68), regardless of whether the run was triggered manually or by the timer. There's no separate "timer log" to check; the service's own unit log is the complete record either way.

> ⚠️ **Warning:** `systemctl start backup.service` succeeding proves the job itself works — it does **not** prove the timer is configured correctly. A typo'd `OnCalendar=` expression, a timer that was never enabled, or a service accidentally left with `WantedBy=` pointing at the wrong target are all failures the manual test won't surface. Confirm the timer separately with `systemctl status backup.timer` and `systemctl list-timers` (7) showing a sane **NEXT** value — testing the service alone is necessary but not sufficient.

## 9. Comprehensive Comparison: systemd Timers vs. cron

| Dimension                | cron                                                                                                        | systemd timers                                                                                                                                                                          |
| ------------------------ | ----------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Schedule/action coupling | Fused into one crontab line                                                                                 | Separated: `.timer` (when) + `.service` (what) — §67's whole unit-file model applies to the latter                                                                                      |
| Schedule expressiveness  | 5-field wall-clock only                                                                                     | `OnCalendar=` (wall-clock, more readable) plus `OnBootSec=`/`OnUnitActiveSec=` (relative/event-based, no cron equivalent)                                                               |
| Dependency ordering      | None — every crontab line is independent                                                                    | Full unit dependency graph on the paired service (`After=`, `Requires=`, §67 2) — can wait on a database or mount being ready                                                           |
| Logging                  | Mail (if an MTA is configured) or nothing, unless the crontab line manually redirects output                | Automatic, structured journald logging via the paired service, queryable with `journalctl -u` (§68) — no redirection to remember                                                        |
| Missed-run handling      | Skipped silently, no exceptions                                                                             | Configurable catch-up via `Persistent=true` (5) — runs once on next boot/wake if a scheduled fire was missed                                                                            |
| Environment              | Famously minimal (`PATH=/usr/bin:/bin` and little else) — the classic "works by hand, fails in cron" trap   | Whatever the paired service unit explicitly declares (`Environment=`, `EnvironmentFile=`, `WorkingDirectory=`, §67 8) — explicit and reviewable, not inherited implicitly from anywhere |
| Scope                    | Per-user (`crontab -e`) and system-wide (`/etc/crontab`, `/etc/cron.d/`) both exist, different line formats | Per-user (`systemctl --user`) and system (`/etc/systemd/system/`) instances both exist, same unit-file syntax in both                                                                   |
| Resource control         | None built in — a cron job can consume unbounded CPU/memory unless externally constrained                   | Full cgroup-based resource limits via the paired service unit (`CPUQuota=`, `MemoryMax=`, etc. — Part 12 covers resource control in depth)                                              |
| Manual testing           | Re-run the script by hand directly — no unit to start independently                                         | `systemctl start foo.service` (8) — runs the exact same unit the timer would trigger, with the same logging path                                                                        |
| Visibility/auditing      | Scattered across multiple files/directories (§39, 8)                                                        | Single `systemctl list-timers --all` view (7)                                                                                                                                           |
| Portability              | Nearly universal across Unix-like systems, decades of institutional familiarity                             | systemd-only — irrelevant on non-systemd or minimal/embedded hosts                                                                                                                      |
| Setup overhead           | One line in an existing crontab                                                                             | Two unit files (`.timer` + `.service`) plus `daemon-reload` and `enable --now`                                                                                                          |

## 10. Common Misconceptions

1. **"Enabling `foo.service` also schedules it."** It doesn't — a timer-triggered service has no `[Install]` section by convention (6) precisely because it's never meant to be enabled directly. Only `foo.timer` gets `enable --now`; the service stays inactive until the timer fires it.
2. **"`Persistent=true` replays every run that was missed."** It catches up exactly one missed occurrence on next boot/wake, not a backlog of every skipped run during extended downtime (5's Warning) — it's a floor guarantee, not a replay queue.
3. **"`systemctl start foo.service` proves the whole timer setup works."** It proves the job itself runs correctly, but says nothing about whether `foo.timer` is enabled, correctly scheduled, or even exists — the timer has to be verified separately via `systemctl status`/`list-timers` (8's Warning).
4. **"systemd timers are always the right choice now that they exist."** They carry real setup overhead — two files instead of one crontab line, `daemon-reload`, and systemd-only portability — that isn't worth paying for a trivial, low-stakes, single-host job where cron's one-line simplicity is genuinely the better engineering trade-off (§39, 7's Tip still applies at this depth).

## 11. Tiered Interview Questions

**🎯 Beginner:** _"What does `Persistent=true` do on a systemd timer, and how is that different from how cron behaves in the same situation?"_
**Model answer:** `Persistent=true` makes systemd remember the last time the timer actually fired; if the host was off or the timer inactive at a scheduled run, it fires that run once as soon as the system is next available, rather than skipping it. Cron has no equivalent — if the host is down when a crontab entry's scheduled minute arrives, that run simply never happens, silently, with no catch-up of any kind.
_What the interviewer is probing for:_ Correctly locating `Persistent=true` as the specific mechanism (not just "timers are more reliable" in the abstract), and knowing cron's actual default behavior in the same scenario.

**🎯 Intermediate:** _"Walk through what happens when you run `systemctl enable --now backup.timer` — does `backup.service` run immediately?"_
**Model answer:** No. `enable` creates the `[Install]`-driven symlink so `backup.timer` itself starts on every future boot, and `--now` starts the timer immediately — but starting the timer just means it begins counting toward its next scheduled activation per `OnCalendar=`/`OnBootSec=`/`OnUnitActiveSec=`. `backup.service` stays inactive until the timer actually fires on its own schedule. If I want to run the job right now, I'd separately run `systemctl start backup.service` directly, which is completely independent of the timer's own schedule.
_What the interviewer is probing for:_ Understanding that the timer and service are two separate units with separate lifecycles — the most common point of confusion coming from cron's single-line mental model.

**🎯 Senior:** _"A team wants to migrate a fleet of cron jobs to systemd timers purely because 'systemd is the modern way.' What pushback, if any, would you give?"_
**Model answer:** I'd want the migration justified by actual operational gaps cron has, not by newness for its own sake. If any of these jobs need dependency ordering on other units, structured queryable logging, missed-run catch-up on hosts that aren't always up, or cgroup-based resource limits, systemd timers deliver real, concrete value there that cron structurally cannot. But for simple, well-understood, low-stakes jobs — a five-field crontab line that's been running fine for years — the migration cost (writing two unit files instead of one line, `daemon-reload`, losing the plain-text portability that makes crontabs trivially readable and version-controlled across any Unix-like host) isn't obviously worth paying just for the sake of modernization. I'd migrate case by case based on which jobs actually need the systemd-specific guarantees, and leave the rest on cron.
_What the interviewer is probing for:_ Resistance to reflexive "newer tool is always better" reasoning, backed by being able to name the specific, concrete advantages that would justify the migration cost on a per-job basis.

**🎯 Architect:** _"Design the scheduling standard for a fleet that currently mixes ad hoc cron jobs and systemd timers with no consistency. What do you mandate, and why?"_
**Model answer:** First, a decision rule for which mechanism a given job uses: if it needs dependency ordering against another unit, resource limits via cgroups, structured journald logging for compliance/audit purposes, or execution guarantees across host downtime, it's a systemd timer, full stop — cron cannot provide any of those. If it's a simple, self-contained, low-stakes job with no such requirements, cron remains an acceptable, lower-overhead choice, and I wouldn't mandate migrating those purely for consistency's sake. Second, for every systemd-timer job, I'd require the paired service to omit `[Install]` (so it can never be accidentally enabled standalone), use `Type=oneshot`, and declare explicit `User=`/`Group=` and resource limits rather than inheriting root and unbounded resources by default — the same non-negotiables §67's unit-file template already enforces for ordinary services, applied here too since a timer-triggered service is still just a service. Third, I'd require `systemd-analyze calendar` run against any new `OnCalendar=` expression before it ships, exactly as `systemd-analyze verify` is already required for unit-file syntax (§67), since a silently-wrong calendar expression is a scheduling bug that won't surface until the wrong (or no) time it fires. Finally, both cron entries and timer/service unit pairs go through version control and configuration management rather than direct edits on live hosts, so `systemctl list-timers --all` and a grep across a config repo — not tribal knowledge — are the source of truth for what's scheduled fleet-wide.
_What the interviewer is probing for:_ Ability to turn a two-tool comparison into an actual organizational policy — a concrete decision rule for choosing between them, security/resource-limit discipline applied consistently, and reproducibility over ad hoc per-host configuration.

## 12. Key Takeaways

- A `.timer` unit's `[Timer]` section is the only genuinely new syntax over an ordinary unit file: `OnCalendar=` for wall-clock schedules (readable calendar expressions, verifiable in advance with `systemd-analyze calendar`), `OnBootSec=`/`OnUnitActiveSec=` for relative/event-anchored schedules cron cannot express at all, and `Persistent=true` to catch up exactly one missed run if the host was down at the scheduled time — a concrete, real advantage over cron's unconditional silent-skip default.
- A timer never runs a command directly — it activates a same-named `.service` unit, almost always `Type=oneshot`, deliberately with no `[Install]` section since only the timer gets `enable --now`; enabling the service directly is a no-op mistake.
- `systemctl list-timers --all` collapses an entire fleet-scheduling audit (next run, last run, which service it activates) into one command — a visibility cron structurally cannot offer without checking every crontab, `/etc/crontab`, `/etc/cron.d/`, and the convenience directories separately.
- `systemctl start foo.service` runs a timer-triggered job immediately and independently of its schedule, for manual testing — but proves only that the job itself works, not that the timer is correctly configured; verify the timer separately via `systemctl status`/`list-timers`.
- The real, structural advantages of systemd timers over cron are dependency ordering, automatic journald logging, missed-run catch-up, explicit environment configuration, and cgroup-based resource limits via the paired service — all inherited from the same unit-file model §67 already covers for ordinary services. None of that makes cron obsolete: for a trivial, low-stakes, single-host job, cron's one-line simplicity and near-universal portability remain a legitimate, lower-overhead choice.

## 13. Related Concepts & What's Next

This section is the full hands-on continuation §39 (Part 5) explicitly deferred — everything here builds directly on that section's conceptual introduction to timers rather than re-deriving it. The timer-plus-service pairing pattern in 6 leans entirely on §67's unit-file model (`Type=oneshot`, `User=`/`Group=`, `ExecStart=` with an absolute path, and the `daemon-reload`/`enable --now` deploy workflow all apply unchanged), and every log a timer-triggered service produces flows through journald exactly as §68 described for any other service — there is no separate timer-specific logging mechanism. §70 (next) covers targets and system state transitions in depth, including `timers.target` itself and how it fits into the boot-time dependency graph that `WantedBy=timers.target` (2) relies on.

**Next Section:** §70 — `Section-70-Part9-Runlevels-Targets-System-State-Transitions.md`
