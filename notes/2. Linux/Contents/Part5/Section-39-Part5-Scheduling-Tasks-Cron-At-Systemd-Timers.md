# Section 39 (Part 5): Scheduling Tasks: cron, at, systemd Timers

## 1. The Scheduling Problem, Distinct From Everything Else in Part 5

§37 and §38 covered controlling processes that already exist or that a human launches interactively — backgrounding, surviving disconnection, tuning CPU priority. This section covers a different problem entirely: running something **without a human present to launch it at all**, on a recurring schedule or at a specific future time. That's a categorically different requirement, and three tools address it on a standard Linux host, each with a different scope: **cron** (recurring, the long-standing default), **at** (one-off, fire-once), and **systemd timers** (the modern alternative to both, covered here only at a conceptual level).

All three ultimately do the same basic thing — cause a command to run later, unattended, outside of any interactive shell session — but they differ sharply in expressiveness, logging, and how failures are surfaced, which is most of what this section is about.

## 2. cron: The Daemon and the Crontab Syntax

**cron** is a background daemon (`crond` on most distributions) that wakes up once a minute, reads a set of schedule files called **crontabs**, and executes any command whose schedule matches the current minute. It has existed on Unix-like systems for decades and remains the most universally available scheduling tool on Linux.

A crontab line has exactly **five time/date fields followed by the command**:

```text
minute hour day-of-month month day-of-week command
  0-59  0-23    1-31      1-12     0-7
```

(`day-of-week` accepts both `0` and `7` for Sunday, depending on implementation.) Each field can be a specific value, a `*` wildcard (meaning "every"), a comma-separated list, a range (`1-5`), or a step (`*/15`).

**Worked example:**

```cron
30 2 * * 1-5 /opt/scripts/backup.sh
```

Read field by field: minute `30`, hour `2`, day-of-month `*` (any), month `*` (any), day-of-week `1-5` (Monday through Friday). Combined: **run `/opt/scripts/backup.sh` at 2:30 AM, Monday through Friday.**

A few more common patterns worth recognizing on sight:

| Schedule expression | Meaning                            |
| ------------------- | ---------------------------------- |
| `*/15 * * * *`      | Every 15 minutes                   |
| `0 * * * *`         | Once an hour, on the hour          |
| `0 0 1 * *`         | Midnight on the 1st of every month |
| `0 9 * * 1`         | 9:00 AM every Monday               |

> 💡 **Tip:** When day-of-month and day-of-week are both restricted (neither is `*`), cron treats them as an **OR**, not an AND — `0 0 1 * 1` runs at midnight on the 1st of the month _or_ every Monday, not only when the 1st falls on a Monday. This trips people up because every other field in the line behaves like a straightforward AND.

## 3. Per-User Crontabs vs. System-Wide Cron

Cron reads schedules from two distinct places, and mixing them up is a common source of "why isn't this running" confusion:

**Per-user crontabs**, managed with the `crontab` command rather than edited as a raw file:

| Command                  | Purpose                                                                              |
| ------------------------ | ------------------------------------------------------------------------------------ |
| `crontab -e`             | Edit the current user's crontab (opens `$EDITOR`)                                    |
| `crontab -l`             | List the current user's crontab entries                                              |
| `crontab -r`             | Remove the current user's entire crontab (no per-line removal — it's all-or-nothing) |
| `crontab -u username -e` | Edit another user's crontab (requires privilege)                                     |

A per-user crontab line has **no user field** — cron already knows whose crontab it's reading, and every job in it runs as that user.

**System-wide cron**, which is where cron's own privilege model differs:

- **`/etc/crontab`** — a single system file with the same five time fields, but with an **extra sixth field for the username** the command should run as, since this file isn't scoped to one user by definition:

  ```cron
  30 2 * * * root /opt/scripts/backup.sh
  ```

- **`/etc/cron.d/`** — a directory of separate files, each following the same six-field-with-username format as `/etc/crontab`. This is the preferred place for packages and configuration management tools to drop their own scheduled jobs, because it avoids every package having to edit one shared file.

> ⚠️ **Warning:** Per-user crontabs (5 fields, no username) and `/etc/crontab`/`/etc/cron.d/` entries (6 fields, username required) use **different line formats**. Pasting a line copied from `/etc/crontab` straight into `crontab -e` (or vice versa) silently misparses — cron will interpret the username field as the command, or the first word of the real command as a username, and the job either does nothing or fails in a way that isn't obviously about the field-count mismatch.

## 4. The Convenience Directories: cron.hourly, cron.daily, cron.weekly, cron.monthly

For the common case of "just run this script once a day" without hand-writing a schedule expression, most distributions provide:

```text
/etc/cron.hourly/
/etc/cron.daily/
/etc/cron.weekly/
/etc/cron.monthly/
```

Any executable script dropped into one of these directories runs on that cadence automatically — no crontab line needed at all. Under the hood, a single `/etc/crontab` (or `/etc/cron.d/`) entry typically invokes `run-parts` against each directory at the appropriate time, so this convenience layer is really just cron itself with the scheduling boilerplate abstracted away. Log rotation (`logrotate`, Part 11) and various system maintenance tasks commonly ship as `/etc/cron.daily/` scripts.

## 5. Cron's Real-World Gotchas

Three problems account for the overwhelming majority of "cron isn't working" incidents, and all three stem from the same root cause: **a cron job runs in a minimal, non-interactive environment that shares almost nothing with your interactive login shell.**

> ⚠️ **Warning:** The classic "works when I run it myself, fails in cron" bug is almost always **`PATH`**. Cron jobs run with a bare-minimum environment — often just `PATH=/usr/bin:/bin` — not the `PATH` your interactive shell builds from `.bashrc`/`.bash_profile`/`.profile`. A script that calls `python3`, `node`, `aws`, or any tool installed somewhere your interactive shell finds via a customized `PATH` (a version manager's shim directory, `/usr/local/bin`, a venv) can fail outright in cron while working perfectly by hand. The fix is always to use **absolute paths** for every command and binary inside a cron-invoked script, or to explicitly set `PATH` (and any other required environment variables) at the top of the crontab or inside the script itself — never assume the interactive shell's environment carries over.

- **Output silently disappears unless redirected.** By default, cron mails a job's stdout/stderr to the owning user's local mail spool (via a local MTA, if one is even configured) — on many modern hosts there's no MTA set up at all, so the output simply vanishes. The standard fix is explicit redirection in the crontab line itself: `... /opt/scripts/backup.sh >> /var/log/backup.log 2>&1`. Without it, a silently failing job can go unnoticed indefinitely.
- **No built-in retry or dependency logic.** Cron has no concept of "retry this job three times before giving up" or "only run job B after job A succeeds" — each crontab line is scheduled independently, with no awareness of any other job's outcome. Any retry or ordering logic has to be built into the script itself (or handed off to an external orchestrator), which is one of the concrete gaps systemd timers and CI/CD schedulers (§97–§102) address more directly.

## 6. at: One-Off Scheduled Tasks

Where cron is for recurring schedules, **`at`** schedules a command to run **exactly once**, at a specified future time — useful for a single deferred action ("restart this service in 20 minutes," "run this cleanup at 3 AM tonight") without cluttering a crontab with a job you intend to delete right after it runs.

```bash
$ at now + 1 hour
at> /opt/scripts/one_time_task.sh
at> <Ctrl+D>
job 4 at Thu Jul 26 15:30:00 2026
```

`at` accepts a flexible range of time expressions — `at now + 1 hour`, `at 15:30`, `at tomorrow`, `at 09:00 next Monday` — and drops into an interactive prompt (or reads a script via `at -f script.sh 15:30`) where you enter the command(s) to run, terminated with `Ctrl+D`.

**Managing pending `at` jobs:**

| Command             | Purpose                                                                    |
| ------------------- | -------------------------------------------------------------------------- |
| `atq`               | List pending jobs queued for the current user (job number, scheduled time) |
| `atrm <job-number>` | Cancel a pending job before it runs                                        |

Like cron, `at` jobs run non-interactively with a limited environment — the same `PATH`/environment gotcha from 5 applies equally here, and output handling has the same silent-unless-redirected default behavior.

## 7. systemd Timers: The Modern Alternative — Conceptually

**systemd timers** are systemd's answer to both cron and `at`, and on any host already running systemd (§13 introduced systemd conceptually; the vast majority of current distributions) they're increasingly the preferred choice for new scheduled work. This section covers them only at the **conceptual comparison level** — full unit-file syntax, calendar expression depth, and hands-on `systemctl`/`journalctl` workflows for timers belong to **Part 9 (§65–§72)**, and are deliberately not duplicated here.

The core idea: a **`.timer` unit** is paired with a **`.service` unit** of the same base name (`backup.timer` triggers `backup.service`) — the timer defines _when_, the service defines _what_, cleanly separating scheduling from the actual work, unlike a crontab line where both are fused into one entry.

Two categories of timer trigger exist:

- **`OnCalendar=`** — a calendar-based, cron-like schedule (`OnCalendar=Mon..Fri 02:30`) — the closest conceptual match to a crontab line's five fields, but with a more readable calendar expression syntax.
- **`OnBootSec=` / `OnUnitActiveSec=`** — _relative_ triggers with no cron equivalent at all: "run 15 minutes after boot" or "run every 6 hours after this timer last activated" — schedules anchored to an event rather than a fixed wall-clock point, which cron has no native way to express.

`systemctl list-timers` shows every active timer on the host, its next scheduled run, and when it last ran — a single command giving visibility that cron has no equivalent for (auditing what's scheduled on a box via cron alone means manually checking every user's crontab plus `/etc/crontab` plus `/etc/cron.d/` plus four convenience directories).

**Real, concrete advantages over cron**, not just syntactic preference:

- **Dependency ordering** — a `.timer`'s paired `.service` can declare `After=`/`Requires=` against other units, so a scheduled job can be made to wait on a database being up or a filesystem being mounted, something cron has no mechanism for at all (5).
- **Logging via journald** — output from a timer-triggered service goes to the journal automatically (§68), structured and queryable with `journalctl -u backup.service`, rather than depending on someone remembering to redirect output in a crontab line or configuring a local MTA that may not exist (5).
- **Missed-run catch-up with `Persistent=true`** — if the host was powered off (or the service was down) when a scheduled run should have fired, a timer with `Persistent=true` runs it as soon as the system is back, rather than silently skipping that run entirely, which is cron's default behavior for any job whose scheduled minute the host slept through.

> 💡 **Tip:** None of this makes cron obsolete or wrong to reach for — a simple, well-understood five-field crontab entry is still often the fastest, most portable way to schedule something on a box, and cron's plain-text format is trivially version-controlled and understood by essentially every Linux administrator without further explanation. Reach for systemd timers specifically when you need the dependency ordering, structured logging, or missed-run guarantees cron structurally can't provide — not as a blanket "always prefer the newer tool" reflex.

## 8. Comparison Table

| Dimension                   | cron                                                                                 | `at`                                                           | systemd timers                                                                       |
| --------------------------- | ------------------------------------------------------------------------------------ | -------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| Recurrence                  | Recurring, cron-expression based                                                     | One-off only                                                   | Recurring (`OnCalendar=`) or relative/event-based (`OnBootSec=`, `OnUnitActiveSec=`) |
| Schedule expressiveness     | Fixed 5-field wall-clock expressions                                                 | Flexible natural-language-ish one-time expressions             | Calendar expressions plus relative/boot-anchored triggers cron can't express         |
| Dependency ordering         | None                                                                                 | None                                                           | Full systemd unit dependency graph (`After=`, `Requires=`)                           |
| Logging                     | Mail (if configured) or nothing, unless manually redirected                          | Same as cron                                                   | journald-integrated by default (§68)                                                 |
| Missed-run behavior         | Skipped silently if host was down                                                    | N/A (fire-once; missed if host was down at the scheduled time) | Configurable catch-up via `Persistent=true`                                          |
| Visibility/auditing         | Scattered across per-user crontabs, `/etc/crontab`, `/etc/cron.d/`, convenience dirs | `atq`                                                          | Single `systemctl list-timers` view                                                  |
| Portability                 | Nearly universal across Unix-like systems                                            | Nearly universal, less commonly pre-installed                  | systemd-only (irrelevant on non-systemd/minimal hosts)                               |
| Learning curve / simplicity | Low — a well-known plain-text line                                                   | Low                                                            | Higher — requires understanding systemd units (§65–§72)                              |

## 9. Common Misconceptions

1. **"A cron job that fails just retries automatically."** It doesn't — cron has no retry logic whatsoever (5). A failed job stays failed until its next scheduled occurrence, and unless output is redirected somewhere monitored, the failure may not even be visible.
2. **"If it runs fine when I type it myself, it'll run fine in cron."** The single most common cron failure mode is exactly the opposite — cron's minimal environment (especially `PATH`) is not the same as an interactive login shell's, and scripts relying on that richer environment fail silently or with confusing errors (5).
3. **"`at` is just cron for one job."** They're related in purpose but not interchangeable in mechanism — `at` has no recurrence concept at all; a job either runs once or is cancelled with `atrm` before it does. Trying to make `at` recur (e.g., by having a job re-schedule itself) is a workaround, not a feature it provides.
4. **"systemd timers are strictly better, so cron should always be replaced."** Systemd timers have real structural advantages (dependency ordering, journald logging, catch-up runs), but cron's simplicity, portability, and plain-text format remain genuinely useful, especially for quick, low-stakes, single-purpose scheduling where systemd's unit-file overhead isn't worth the setup (7).

## 10. Tiered Interview Questions

**🎯 Beginner:** _"Break down what `30 2 * * 1-5 /opt/scripts/backup.sh` means."_
**Model answer:** Reading the five fields in order — minute `30`, hour `2`, day-of-month `*` (any day), month `*` (any month), day-of-week `1-5` (Monday through Friday) — this runs `/opt/scripts/backup.sh` at 2:30 AM on weekdays only.
_What the interviewer is probing for:_ Basic fluency reading the five-field cron syntax without needing a reference.

**🎯 Intermediate:** _"A script works perfectly when you run it manually but fails silently when cron runs it. What's your first suspicion, and why?"_
**Model answer:** My first suspicion is the environment cron provides — specifically `PATH`. Cron jobs run with a minimal environment, often just `/usr/bin:/bin`, not the richer `PATH` an interactive shell builds from `.bashrc`/`.profile`. If the script calls a binary that's only reachable via a customized `PATH` in my interactive shell — a version manager shim, a venv, `/usr/local/bin` — it'll fail in cron while working fine by hand. I'd fix it by using absolute paths for every command in the script, or explicitly setting `PATH` at the top of the crontab entry or inside the script, and I'd also make sure output is redirected to a log file so I can actually see the failure instead of it disappearing into an unconfigured mail spool.
_What the interviewer is probing for:_ Recognition of the specific, well-known cron environment gap rather than a vague "check the logs" non-answer — and knowing output silently vanishing is a second, related gotcha.

**🎯 Senior:** _"Why would you choose a systemd timer over a cron job for a new scheduled task?"_
**Model answer:** It depends what the task actually needs. If it's a simple, self-contained job with no dependencies on other services and no strict requirement to guarantee execution even after downtime, cron's simplicity and portability are still perfectly fine — a five-field crontab line is fast to write, easy for anyone to read, and works identically across almost any Linux host. I'd reach for a systemd timer specifically when I need something cron structurally can't give me: dependency ordering against other units (so the job waits for a database or mount to be ready), structured logging into journald so failures are queryable rather than silently mailed or lost, or guaranteed catch-up execution via `Persistent=true` if the host was down when the job should have fired. Those are concrete operational guarantees, not just newer syntax, and they're the actual deciding factor — not "systemd is more modern" as a blanket reason.
_What the interviewer is probing for:_ Choosing based on concrete operational requirements (dependency ordering, logging, catch-up semantics) rather than reflexively picking the newer tool, and being able to articulate cron's continued legitimate use cases.

**🎯 Architect:** _"You're auditing a fleet and find scheduled jobs scattered across per-user crontabs, `/etc/cron.d/`, and a handful of systemd timers, with no documentation of what any of them do. How do you approach bringing this under control?"_
**Model answer:** First I'd build a full inventory rather than trusting any one source — every user's `crontab -l`, the contents of `/etc/crontab` and every file in `/etc/cron.d/`, the four `cron.{hourly,daily,weekly,monthly}` directories, and `systemctl list-timers --all` for the systemd side, since cron's schedule information is genuinely scattered across all of those locations by design (8) and nothing short of checking every location gives ground truth. For each job found, I'd want to know what it does, whether it has externally observable output going anywhere (a log file, monitoring, or nothing), and whether its absence would be silently unnoticed — that last question usually surfaces the highest-risk jobs, since cron's default failure mode is silence (5). Going forward, I'd push new scheduled work toward systemd timers where the job has real dependencies or needs guaranteed execution and auditable logging via journald, keep cron for simple, well-documented, low-stakes jobs, and in both cases require jobs be defined in version-controlled configuration (Ansible, config management) rather than ad hoc edits on individual hosts, so `crontab -e` on a live box stops being the only record of what's actually scheduled.
_What the interviewer is probing for:_ Fleet-scale audit discipline across cron's genuinely scattered configuration surface, prioritizing by silent-failure risk, and pushing toward reproducible, version-controlled scheduling rather than tribal-knowledge crontabs.

## 11. Key Takeaways

- A crontab line is five time fields (`minute hour day-of-month month day-of-week`) followed by a command; day-of-month and day-of-week combine as an OR when both are restricted, not an AND.
- Per-user crontabs (`crontab -e`/`-l`/`-r`, no username field) and system-wide cron (`/etc/crontab`, `/etc/cron.d/`, username required as a sixth field) use different line formats — mixing them up silently misparses. The `cron.{hourly,daily,weekly,monthly}` directories offer a no-syntax convenience layer on top of the same mechanism.
- Cron's minimal, non-interactive environment — especially a bare-minimum `PATH` — is the classic root cause of "works in my shell, fails in cron," and output vanishes silently unless explicitly redirected; cron also has no built-in retry or inter-job dependency logic.
- `at` schedules a single one-off future execution (`at now + 1 hour`), managed with `atq`/`atrm` — a fundamentally different tool from cron's recurrence model, not a lightweight version of it.
- systemd timers pair a `.timer` unit with a same-named `.service` unit, support both calendar (`OnCalendar=`) and relative/event-based (`OnBootSec=`, `OnUnitActiveSec=`) triggers, and offer real structural advantages over cron — dependency ordering, journald-integrated logging, and missed-run catch-up via `Persistent=true` — visible fleet-wide via `systemctl list-timers`; full syntax is deferred to Part 9 (§65–§72).
- Neither tool is a strict upgrade over the other — cron remains simple and portable for low-stakes jobs; systemd timers earn their added complexity when dependency ordering, structured logging, or execution guarantees actually matter.

## 12. Related Concepts & What's Next

This section builds on §13's conceptual systemd introduction (Part 2) — the `.timer`/`.service` unit pairing in 7 is a direct application of the unit-file model §13 introduced without full syntax — and follows §38's process-priority coverage as the next axis of unattended process management in Part 5. Full systemd timer syntax, `OnCalendar=` expression depth, and hands-on `systemctl`/`journalctl` workflows are Part 9 (§65–§72), which this section deliberately deferred to rather than duplicating. Cron and scheduled automation also connect forward to Part 13's automation and DevOps coverage (§97–§102), where scheduling ties into CI/CD pipelines and broader automation strategy rather than single-host job scheduling. §40 (next) moves to inter-process communication — pipes, sockets, and shared memory — a conceptual overview of how processes exchange data, closing out Part 5's process-and-job-management arc.

**Next Section:** §40 — `Section-40-Part5-Inter-Process-Communication-Overview.md`
