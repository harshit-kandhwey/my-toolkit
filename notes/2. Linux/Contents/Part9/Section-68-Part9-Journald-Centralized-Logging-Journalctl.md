# Section 68 (Part 9): journald and Centralized Logging (journalctl)

## 1. Overview: A Structured, Binary Departure From Plain-Text Logging

§66 showed `systemctl status` printing a handful of recent log lines directly beneath a unit's state, and treated that as a convenience without explaining where those lines actually come from. §67 covered writing custom unit files whose `ExecStart` process's stdout and stderr just show up in logs with no application code changes required. This section is the piece that makes both of those things true: **journald**, systemd's logging daemon, and **journalctl**, the tool used to query it.

The architectural shift worth internalizing before any command syntax: traditional Unix logging (syslog, and its common implementation `rsyslogd`) is fundamentally a **plain-text line** model — a daemon writes a formatted string to a file, and every downstream tool (`grep`, `tail`, log rotation, log shippers) works by parsing that string back apart. journald instead stores each log entry as a **structured record with named fields** — a binary, indexed format, not a text file you `cat` directly. A single journal entry isn't just "a line of text with a timestamp prefix"; it carries fields like the emitting unit, the PID, the priority level, the boot ID, and more, each independently queryable, without regex-parsing a string to extract them.

That distinction is the reason journald feels different to operate, not a cosmetic implementation detail:

- **Structured fields are queryable directly** — "show me only entries from this unit, at this priority, in this boot" is a first-class query (3), not a `grep` pipeline reconstructing structure that was thrown away at write time.
- **The binary format is not human-readable without `journalctl`** — this is a real operational adjustment for anyone used to `tail -f /var/log/messages`; the journal files under `/var/log/journal/` or `/run/log/journal/` aren't meant to be opened directly.
- **journald is tightly integrated with systemd**, not a bolted-on add-on — every unit's stdout/stderr is captured by default (2), which is a structural consequence of systemd owning both process supervision and logging, not a feature someone had to wire up separately.

> 💡 **Tip:** Don't think of journald as "syslog, but systemd's version." It's a genuinely different storage and query model built around structured records — syslog compatibility (8) is a bridge journald provides for older tooling, not a description of what journald fundamentally is.

## 2. What Gets Captured Automatically, With No Application Changes

journald begins collecting several categories of log data the moment it's running, without any service being written or configured to "log to journald" specifically:

- **Kernel messages** — the same information `dmesg` surfaces, ingested via the kernel ring buffer and stored as journal entries with their own identifiable source field, retrievable with `-k` (3).
- **stdout and stderr of every systemd-managed unit** — this is the detail §67 left implicit: when a unit's `ExecStart` process writes to stdout or stderr, systemd itself owns the pipes and forwards that output straight into the journal, tagged with the unit's name. A service author does not need to configure a log file path, rotate it, or link any logging library — printing to stdout is already "logging," which is a deliberate simplification versus the traditional model of every daemon inventing its own log-file convention.
- **Syslog-protocol messages** — anything still emitting classic syslog-formatted messages (older daemons, some third-party software) is received and stored by journald too, since journald listens on the traditional syslog socket. Old and new logging conventions land in the same store rather than being two disconnected systems.
- **Audit records**, when the audit subsystem is active — journald can ingest kernel audit events as well (full audit tooling depth is `auditd`/`ausearch`/`aureport`, Part 12 §93).

**Production usage example:** This is why a newly written custom `.service` unit (§67) never needs its own logging setup to be debuggable — `journalctl -u <unit>` (3) works from the very first `systemctl start`, because capture was never optional or something to enable; it's the default behavior of running anything under systemd.

## 3. `journalctl`: Core Query Patterns

`journalctl` is the single tool for reading everything journald has captured — kernel, unit, and syslog-sourced entries alike, filtered and formatted however the situation calls for.

**Purpose:** Query, filter, and format journal entries for a specific unit, time range, priority level, or boot, rather than scrolling an undifferentiated firehose of every message on the host.

**Syntax and key flags:**

```bash
journalctl [options]
```

| Flag                         | Meaning                                                                                                                              |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `-u <unit>`                  | Show only entries from a specific systemd unit — the most common single filter in daily use                                          |
| `-f`                         | Follow mode — stream new entries live, directly analogous to `tail -f`                                                               |
| `-b`                         | Entries from the current boot only; `-b -1` for the previous boot, `-b -2` for the one before that, etc.                             |
| `--since`, `--until`         | Time-range filtering — accepts absolute timestamps or relative expressions like `"1 hour ago"`, `"today"`                            |
| `-p <priority>`              | Filter by syslog priority level (`emerg` through `debug`, or numeric `0`–`7`) — shows that level and above                           |
| `-o json` / `-o json-pretty` | Emit structured JSON per entry instead of the default human-readable line — built for piping to `jq` or shipping to a log aggregator |
| `-k`                         | Kernel messages only — the journald-native equivalent of `dmesg`                                                                     |
| `-n <N>`                     | Show only the last N entries (default 10, same idea as `tail -n`)                                                                    |
| `-r`                         | Reverse order — newest entries first                                                                                                 |
| `-x`                         | Add explanatory help text for entries that have it (message catalog lookups)                                                         |

**Example usage and expected output:**

```bash
# Everything from a specific service, following live
$ journalctl -u nginx.service -f
Jul 27 10:03:41 web01 nginx[1842]: 10.0.0.5 - - "GET /health HTTP/1.1" 200

# Everything since an hour ago, at warning level or higher
$ journalctl --since "1 hour ago" -p warning

# Entries from the current boot for a unit, as structured JSON
$ journalctl -u myapp.service -b -o json-pretty
```

Flags combine freely — `journalctl -u myapp.service -b -1 --since "09:00" -p err` narrows to one unit, one specific prior boot, a time window, and a priority floor, all at once, which is the kind of combined query traditional multi-file plain-text logs make far more tedious to reconstruct.

**Production usage example:** During an incident, `journalctl -u <suspect-unit> --since "-15m" -o json-pretty` is a fast way to pull a tight, structured slice of recent behavior for a specific service — narrow enough to read quickly, structured enough to pipe into `jq` for further filtering, and scoped by both unit and time without needing to know which physical log file the service happens to write to.

**Common errors:**

- Running `journalctl` unfiltered on a busy host and expecting to scroll to something useful — always reach for `-u`, `--since`, or `-p` first rather than treating the raw firehose as a starting point.
- Forgetting that `-b` without `-1`/`-2` means "current boot" — someone debugging "why don't I see last week's logs" is very often actually hitting the persistence question in 4, not a query-syntax problem.

**Troubleshooting:** If `journalctl -u <unit>` returns nothing at all, confirm the unit name is exact (`systemctl list-units` per §66) and check 4 — a host running with volatile storage and a recent reboot has genuinely lost the history being searched for, not just filtered it out.

## 4. Persistence: `/etc/systemd/journald.conf` and `Storage=`

Where journal data physically lives, and whether it survives a reboot, is governed by `/etc/systemd/journald.conf`'s `Storage=` directive — and this is a real operational decision, not a detail to skip past.

| `Storage=` value | Location                                                      | Behavior                                                                                                   |
| ---------------- | ------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `volatile`       | `/run/log/journal/` (tmpfs)                                   | In-memory only — journal data is **lost on reboot**, since `/run` is a memory-backed filesystem            |
| `persistent`     | `/var/log/journal/`                                           | Written to disk — survives reboots; directory is created automatically if it doesn't exist                 |
| `auto`           | `/var/log/journal/` if it exists, else falls back to volatile | The common distro default — persistence depends entirely on whether that directory happens to exist        |
| `none`           | —                                                             | Journald keeps only a minimal in-memory buffer for forwarding purposes; effectively disables local storage |

Many mainstream distributions ship with `Storage=auto` and **no** `/var/log/journal/` directory present out of the box — which means logging is silently volatile by default on those hosts, even though `/var/log/` "feels" like the traditional home for persistent logs.

> ⚠️ **Warning:** This catches people off guard constantly: a host reboots — a routine patch, a crash, a planned maintenance window — and the logs from right before the reboot, the ones needed to diagnose _why_ it rebooted, are simply gone, because journald was never configured for persistent storage. If `/var/log/journal/` doesn't exist and `Storage=auto` (or `volatile`) is set, that is the expected, by-design outcome, not a bug. Making storage persistent is a one-time, deliberate action: create the directory (`mkdir -p /etc/systemd/journal ... ` — more precisely `mkdir -p /var/log/journal && systemd-tmpfiles --create --prefix /var/log/journal`), or set `Storage=persistent` explicitly in `journald.conf`, then restart `journald` (`systemctl restart systemd-journald`). Verify with `journalctl --disk-usage` or by checking whether `/var/log/journal/<machine-id>/` actually has files in it after the change.

**Production usage example:** Any host expected to retain logs across reboots for incident review — which in practice means nearly every production server — should have this checked explicitly during provisioning or hardening, not assumed. A golden image or configuration-management baseline (Part 13's §97–§102 covers IaC/config-management patterns) is the right place to enforce `Storage=persistent` fleet-wide rather than relying on each host's distro default.

## 5. Log Rotation and Retention: `SystemMaxUse=` and Vacuum Commands

Persistent journal storage still needs bounds — an unbounded journal on disk will eventually consume all available space, and journald manages this itself rather than depending on an external tool like `logrotate` for its own files (`logrotate` still matters for plenty of non-journald application logs, covered in Part 11 §86).

Key `journald.conf` directives:

| Directive            | Meaning                                                                                        |
| -------------------- | ---------------------------------------------------------------------------------------------- |
| `SystemMaxUse=`      | Maximum total disk space the persistent journal (`/var/log/journal/`) is allowed to consume    |
| `SystemKeepFree=`    | Minimum free disk space journald tries to leave available, regardless of `SystemMaxUse=`       |
| `SystemMaxFileSize=` | Maximum size of an individual journal file before it's rotated to a new one                    |
| `RuntimeMaxUse=`     | The volatile (`/run/log/journal/`) equivalent of `SystemMaxUse=`, for in-memory storage        |
| `MaxRetentionSec=`   | Maximum age of retained entries, independent of size — old entries beyond this age are dropped |

Beyond configured limits, `journalctl` supports **manual, on-demand vacuuming**:

```bash
# Shrink the journal to at most 500M, deleting oldest entries first
journalctl --vacuum-size=500M

# Delete entries older than 2 weeks
journalctl --vacuum-time=2weeks

# Check current disk usage of the journal
journalctl --disk-usage
```

**Production usage example:** A host that's been running for a long time with generous logging (debug-level services, verbose unit output) can accumulate a surprisingly large `/var/log/journal/` footprint — `journalctl --disk-usage` is the fast first check when investigating unexpected disk pressure on a systemd host, and `--vacuum-size=`/`--vacuum-time=` are the direct, immediate remediation, distinct from adjusting `SystemMaxUse=` for the ongoing policy going forward.

**Common errors:** Setting `SystemMaxUse=` without ever checking `journalctl --disk-usage` against actual retention needs — a limit set too small silently drops history sooner than an incident-review process expects, which is a quieter failure mode than running out of disk entirely.

## 6. Priority Levels

journald reuses the traditional syslog priority scale, and `-p` (3) filters against it directly:

| Numeric | Name    |
| ------- | ------- |
| 0       | emerg   |
| 1       | alert   |
| 2       | crit    |
| 3       | err     |
| 4       | warning |
| 5       | notice  |
| 6       | info    |
| 7       | debug   |

`-p warning` (or `-p 4`) shows `warning` and everything numerically lower (more severe) — `emerg` through `warning` — not just entries exactly at that level. This "at-or-above severity" semantics is the same convention syslog has always used, and it's worth confirming explicitly rather than assuming `-p` means an exact match.

## 7. Relationship to Traditional syslog/rsyslog: Not Strictly Either/Or

journald did not simply replace syslog outright the way systemd replaced SysVinit as PID 1 — the relationship between the two on a running host is more of a coexistence, and this section clarifies where journald sits without going into `rsyslog`'s own configuration depth, which is deferred to Part 11's logging deep dive (§86).

- **journald can forward to a traditional syslog daemon.** `journald.conf`'s `ForwardToSyslog=` directive (default varies by distro) sends every journal entry onward to whatever syslog implementation is also running — commonly `rsyslogd` — for compatibility with tooling, log shippers, or organizational standards built around plain-text syslog files under `/var/log/`.
- **Many distributions run both together**, at least for a transitional or compatibility period — journald as the structured, systemd-integrated primary store, with `rsyslogd` receiving a forwarded copy and writing it out to the familiar `/var/log/syslog` or `/var/log/messages` plain-text files that older scripts, log-shipping agents, or muscle memory still expect.
- **This isn't a permanent either/or decision system-wide** — a host can be journald-only (nothing consuming the forwarded syslog stream), journald-plus-rsyslog (both active, structured and plain-text logs both available), or, on older/minimal systems, rsyslog-only if journald's persistent structured storage isn't needed at all. Which combination is in play on a given host is worth confirming directly (`systemctl status systemd-journald rsyslog`) rather than assumed from the distribution.

Full `rsyslog` configuration — templates, remote log forwarding, filter rules — belongs to Part 11 §86's logging deep dive, alongside `logrotate` and centralized logging pipeline patterns; this section's job is only to establish that journald and rsyslog are complementary layers on many real hosts, not competing replacements where only one can be "the" answer.

## 8. Hands-On: Confirming Persistence Configuration on a Host

**Purpose:** Directly verify whether a host's journal will survive a reboot, rather than assuming based on distro defaults — the exact gap the Warning in 4 exists to close.

```bash
grep -E '^Storage=' /etc/systemd/journald.conf
ls -d /var/log/journal 2>/dev/null && echo "persistent directory exists" || echo "no persistent directory"
journalctl --disk-usage
```

**Expected output:** A `Storage=` line (or its absence, meaning the compiled-in default applies), confirmation of whether `/var/log/journal/` actually exists, and the current on-disk journal size.

**Production usage example:** This three-line check is a natural addition to the same kind of fleet-audit sweep §64 described for repository/GPG hygiene — cheap to run at scale via SSH/Ansible, and it directly answers "will this host still have useful logs after its next reboot," which is exactly the question that tends to surface only after an incident already needed logs that turned out not to exist.

**Common errors:** Checking only the `journald.conf` `Storage=` line and stopping there — `Storage=auto` with no `/var/log/journal/` directory present is functionally volatile, so the directory's actual existence matters as much as the configured value.

**Troubleshooting:** If persistence is missing on a host that needs it, apply the fix from 4's Warning (`mkdir -p /var/log/journal`, `systemd-tmpfiles --create --prefix /var/log/journal`, `systemctl restart systemd-journald`) and re-run this check to confirm the directory now has content after the restart.

## 9. Common Misconceptions

1. **"journald is just systemd's syslog."** It's a structured, binary-format store with independently queryable fields, not a text-line format with a different name — 1 covers why that's a real architectural difference, not branding. Syslog compatibility (7) is a bridge it provides, not what it fundamentally is.
2. **"Services need to be configured to log to journald."** Any unit's stdout/stderr is captured automatically the moment it runs under systemd (2) — there's no opt-in step, which is why a brand-new custom unit from §67 is immediately debuggable via `journalctl -u` with zero logging setup.
3. **"Logs under `/var/log/` are always persistent."** Whether journal data survives a reboot depends entirely on `Storage=` and whether `/var/log/journal/` exists (4) — `Storage=auto` with that directory absent, a common out-of-the-box state on several distributions, means logs are silently volatile despite `/var/log/` looking like the traditional persistent-logs location.
4. **"journald replaced rsyslog, full stop."** The real-world relationship is frequently coexistence, not replacement — journald forwarding to rsyslog for compatibility is a normal, supported configuration on many hosts, not a leftover transitional artifact (7).
5. **"`-p warning` shows only warning-level entries."** Priority filtering is "at this severity or worse," following the same numeric convention traditional syslog has always used (6) — `-p warning` includes `err`, `crit`, `alert`, and `emerg` too, not just exact `warning`-level entries.

## 10. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between journald and traditional syslog logging?"_
**Model answer:** journald stores each log entry as a structured record with named fields — which unit emitted it, its priority, its PID, the boot it came from — in a binary, indexed format, rather than a single plain-text line the way traditional syslog implementations like rsyslog write. That structure means `journalctl` can filter directly on fields (unit, priority, time range, boot) instead of needing to regex-parse a text line to reconstruct information that a plain-text log format didn't preserve as structured data.
_What the interviewer is probing for:_ Whether the candidate understands this as a storage-model difference, not just "journald is the newer command."

**🎯 Intermediate:** _"A teammate says logs from before this morning's reboot are just gone from `journalctl`. What's your first hypothesis, and how do you check it?"_
**Model answer:** My first hypothesis is volatile storage — `Storage=volatile` (or `Storage=auto` with no `/var/log/journal/` directory present, which many distros ship with by default) means journal data lives only in `/run/log/journal/`, a memory-backed tmpfs, and is genuinely lost on every reboot, not filtered out or hidden. I'd check `grep Storage= /etc/systemd/journald.conf` and confirm whether `/var/log/journal/` actually exists on disk. If persistence was never configured, the pre-reboot logs are unrecoverable — the fix going forward is creating `/var/log/journal/`, running `systemd-tmpfiles --create --prefix /var/log/journal`, and restarting `systemd-journald`, but that only protects future reboots, not the one that already happened.
_What the interviewer is probing for:_ Recognizing this as a real, common operational trap rather than a `journalctl` syntax problem, and knowing the concrete remediation.

**🎯 Senior:** _"How would you use `journalctl` to investigate a service that crashed intermittently overnight, three boots ago?"_
**Model answer:** I'd combine `-u` for the specific unit with `-b -3` to scope to that exact prior boot (assuming boots are numbered consistently back that far, which depends on persistent storage actually being enabled), then narrow with `--since`/`--until` around the approximate crash window if I have one from an alert or monitoring timestamp. I'd add `-p err` or lower to surface elevated-severity entries first, then widen the priority filter if the crash didn't log at that severity. For a deeper look I'd switch to `-o json-pretty` and pipe into `jq` to correlate fields — PID, restart count via cgroup information — across the crash boundary, since systemd's built-in restart behavior (§67) means the same unit name can represent multiple process instances across a night of restarts, and treating it as one continuous stream can misattribute log lines to the wrong crash cycle.
_What the interviewer is probing for:_ Fluency combining multiple `journalctl` filters purposefully, and awareness that unit restarts complicate naive log reading.

**🎯 Architect:** _"You're defining a logging baseline for a new fleet of systemd-based hosts. What does the journald piece of that baseline look like, and how does it relate to the rest of the logging pipeline?"_
**Model answer:** I'd start by making `Storage=persistent` (or ensuring `/var/log/journal/` exists under `Storage=auto`) an explicit, enforced setting in the golden image or config-management baseline (Part 13) rather than trusting each distro's out-of-the-box default — the volatile-by-default trap in 4 is exactly the kind of thing that only surfaces during an incident, when it's too late to matter. I'd set deliberate `SystemMaxUse=`/`MaxRetentionSec=` bounds sized to the host's disk budget and the organization's log-retention requirements, rather than leaving journald's defaults unexamined. For centralization, I'd decide explicitly whether journald forwards to rsyslog for onward shipping (`ForwardToSyslog=`) or whether a dedicated log-shipping agent reads the journal directly (`journalctl -o json` output is well-suited to this, since it's already structured) — both are legitimate architectures, but the choice should be intentional, not whatever the distro happened to ship. I'd tie the whole thing into the broader observability story from Part 11 (§80–§88) — journald is one source among CPU/memory/disk/network metrics and tracing, and the fleet's logging pipeline needs to be designed alongside that larger monitoring picture, not as an isolated per-host concern.
_What the interviewer is probing for:_ Fleet-scale, intentional logging architecture rather than accepting distro defaults, and correctly situating journald as one component of a larger observability strategy.

## 11. Key Takeaways

- journald is a structured, binary-format logging daemon — entries carry queryable named fields, not just a formatted text line — a real architectural shift from traditional plain-text syslog, not a rebrand of it (1).
- Kernel messages, every systemd unit's stdout/stderr, and syslog-protocol messages are all captured automatically with zero application-side logging configuration required — this is why a brand-new custom unit (§67) is immediately debuggable via `journalctl -u` (2).
- Persistence is a real, easy-to-miss operational decision: `Storage=` in `/etc/systemd/journald.conf`, plus whether `/var/log/journal/` actually exists, determines whether logs survive a reboot — many distros default to effectively volatile storage out of the box (4).
- `journalctl` supports rich combined filtering — `-u`, `-f`, `-b`, `--since`/`--until`, `-p`, `-o json`/`-o json-pretty`, `-k` — that plain-text multi-file logs make far more tedious to reconstruct (3).
- journald manages its own rotation and retention via `SystemMaxUse=`/`MaxRetentionSec=` and on-demand `--vacuum-size=`/`--vacuum-time=` commands, distinct from `logrotate`'s role for non-journald application logs (5).
- journald and rsyslog frequently coexist rather than one strictly replacing the other — `ForwardToSyslog=` is a normal, supported bridge for compatibility and centralized pipelines, not a legacy leftover (7).

## 12. Related Concepts & What's Next

This section is the full depth behind the log lines §66 showed inline under `systemctl status`, and it's the mechanism that makes §67's claim — that a custom unit's stdout/stderr is captured automatically — concretely true. §69 (next) moves to systemd timers, comparing them against cron for scheduled-task execution. The broader observability and performance story this section is one piece of — metrics, tracing, and a dedicated logging-pipeline deep dive covering `rsyslog` configuration and `logrotate` in full — is **Part 11, §80–§88**, and should be treated as where journald's centralized-logging role gets tied into the wider monitoring picture.

**Next Section:** §69 — `Section-69-Part9-Systemd-Timers-vs-Cron.md`
