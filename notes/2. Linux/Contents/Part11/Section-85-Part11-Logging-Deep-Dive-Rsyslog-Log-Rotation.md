# Section 85 (Part 11): Logging Deep Dive: rsyslog, Log Rotation (logrotate), Centralized Logging Pipelines

## 1. Overview: The Traditional Plain-Text Layer journald Sits Alongside

[§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md) introduced journald as systemd's structured, binary-format logging daemon and flagged — twice, deliberately — that its relationship to traditional syslog is coexistence, not replacement, with the full `rsyslog` treatment deferred here. This section is that promised continuation: `rsyslog` as the traditional plain-text syslog daemon, `logrotate` as the tool that keeps plain-text logs from growing without bound, and centralized logging pipelines as the fleet-scale answer to both.

Where journald stores structured, independently queryable records, `rsyslog` writes formatted text lines to files under `/var/log/` — the format generations of Unix and Linux administrators have built tooling, muscle memory, and `grep`/`awk` pipelines ([§48](../Part6/Section-48-Part6-Text-Processing-Tools-Grep-Sed-Awk.md)–[§49](../Part6/Section-49-Part6-Essential-Utilities-Cut-Sort-Uniq-Tr-Wc-Xargs-Find.md)) around. Both models are alive on real production hosts today, often on the same host at the same time.

> 💡 **Tip:** Don't read this section as "here's the old way, before journald fixed it." `rsyslog` remains the standard mechanism for file-based log output, remote syslog forwarding, and facility-based routing that plenty of tooling, compliance requirements, and third-party log shippers still expect — journald's structured store and rsyslog's plain-text files are complementary layers on a well-configured modern host, not competing generations.

## 2. rsyslog: Facility and Priority-Based Routing

`rsyslog` (the dominant modern implementation of the traditional syslog protocol) routes incoming log messages to destinations based on two pieces of metadata every syslog message carries: a **facility** (a rough category of what subsystem generated the message — `mail`, `auth`, `kern`, `cron`, `daemon`, `local0`–`local7` for custom use) and a **priority/severity** (the same `emerg`–`debug` scale [§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md) covered for journald — both trace back to the same original syslog specification).

`/etc/rsyslog.conf` (plus per-topic drop-in files under `/etc/rsyslog.d/`) expresses routing rules as `facility.priority destination` lines:

```
mail.*                          /var/log/mail.log
auth,authpriv.*                 /var/log/auth.log
kern.*                          /var/log/kern.log
*.emerg                         :omusrmsg:*
*.*;auth,authpriv.none          /var/log/syslog
```

Each line says, in effect, "anything matching this facility and priority (or above) goes to this destination" — a file path, but also potentially a named pipe, a remote host (`@` or `@@` prefix for UDP/TCP forwarding), or a user's terminal.

**The standard `/var/log/` file layout** this routing typically produces, and what each file conventionally holds:

| File                                                                   | Contents                                                                                                                                                                                          |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/var/log/syslog` (Debian/Ubuntu) or `/var/log/messages` (RHEL family) | The general-purpose catch-all — most non-auth, non-kernel activity lands here                                                                                                                     |
| `/var/log/auth.log` (Debian/Ubuntu) or `/var/log/secure` (RHEL family) | Authentication and authorization events — logins, `sudo` usage, SSH sessions — high-value for security review ([§89](../Part12/Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md)) |
| `/var/log/kern.log`                                                    | Kernel-facility messages specifically, a file-based parallel to `dmesg`/journald's kernel ring buffer capture                                                                                     |
| `/var/log/mail.log`, `/var/log/cron.log`, etc.                         | Per-facility files for specific subsystems, when a distro or admin chooses to split them out rather than lumping everything into the catch-all                                                    |

The exact filenames are a distribution convention, not a protocol requirement — the facility/priority routing rules in `rsyslog.conf` are what actually decide where each message ends up, and two distributions can legitimately route the same facility to differently named files.

## 3. How journald and rsyslog Actually Coexist

[§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md) raised this and deferred the mechanics here — on a modern systemd-based distribution, the two are typically layered rather than either/or:

- **journald is the primary collector.** Every unit's stdout/stderr, kernel messages, and syslog-protocol traffic land in journald first, as [§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md) described, because journald listens on the traditional syslog socket in addition to its own structured capture paths.
- **journald forwards to rsyslog for file-based and remote output.** The `ForwardToSyslog=` directive in `journald.conf` (default varies by distro) hands a copy of every journal entry onward to whatever's listening on the syslog socket — commonly `rsyslogd` — which then applies its own `facility.priority` routing rules (2) and writes the familiar plain-text files.
- **rsyslog independently handles remote forwarding.** A `rsyslog.conf` line like `*.* @@logserver.internal:514` (the double-`@` selects TCP over UDP) ships every matched message to a remote syslog collector — a capability journald's own forwarding doesn't replace, since remote log-shipping protocol handling is rsyslog's job even when journald is the thing that captured the message first.

The practical upshot: a host can run journald-only (nothing consuming the forwarded stream), journald-plus-rsyslog (both structured and plain-text logs available, which is the common default on many mainstream distributions), or rsyslog-only on older/minimal systems without journald's persistent structured store at all. Confirming which combination is actually active on an unfamiliar host (`systemctl status systemd-journald rsyslog`) is worth doing directly rather than assuming from the distribution family, the same audit discipline [§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md) and [§13](../Part2/Section-13-Part2-Init-Systems.md) both emphasized for init-system and logging assumptions generally.

## 4. logrotate: Keeping Plain-Text Logs Bounded

Unlike journald, which manages its own size and retention internally via `SystemMaxUse=`/`MaxRetentionSec=` ([§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md)), plain-text files that `rsyslog` (or any other application) writes to under `/var/log/` need an external mechanism to stay bounded — that mechanism is `logrotate`, run periodically via a systemd timer or cron entry (typically daily).

**Configuration structure:** `/etc/logrotate.conf` holds global defaults, and `/etc/logrotate.d/*` holds one file per application or log group — `rsyslog` itself ships a drop-in covering the standard `/var/log/` files, and any package that writes its own log file typically ships a matching `logrotate.d` config alongside it.

**Key directives:**

| Directive                      | Meaning                                                                                               |
| ------------------------------ | ----------------------------------------------------------------------------------------------------- |
| `daily` / `weekly` / `monthly` | How often to rotate, independent of file size                                                         |
| `rotate N`                     | How many rotated (old) copies to retain before the oldest is deleted — the retention count            |
| `compress`                     | gzip older rotated copies (typically all but the most recent, via `delaycompress`) to save disk space |
| `size`                         | Rotate when a file crosses a size threshold, as an alternative or supplement to time-based rotation   |
| `missingok`                    | Don't error if the log file doesn't exist — common for optional or not-yet-created logs               |
| `notifempty`                   | Skip rotation if the log file is empty                                                                |
| `postrotate` / `endscript`     | A shell command block run immediately after rotation completes                                        |

**Example `/etc/logrotate.d/myapp`:**

```
/var/log/myapp/*.log {
    daily
    rotate 14
    compress
    delaycompress
    missingok
    notifempty
    postrotate
        systemctl kill -s HUP myapp.service
    endscript
}
```

## 5. Why `postrotate` Matters: The Reopen-the-File-Descriptor Problem

This is the single most important mechanical detail in this section, and it's worth a dedicated explanation because getting it wrong silently breaks logging without any obvious error.

**What rotation actually does mechanically** is, at its simplest, a rename: `myapp.log` becomes `myapp.log.1` (optionally followed by compression). It is **not** an operation that touches the still-running application process at all. But that process, if it opened `myapp.log` for writing when it started, is holding an **open file descriptor** that points to the underlying inode — not to the path `/var/log/myapp/myapp.log`. A rename doesn't invalidate that descriptor or move it anywhere; the process keeps writing to the exact same inode, which now lives at the path `myapp.log.1` (or inside a `.gz` file after compression, in the worst case). Meanwhile, nothing is being written to a file at the original path `myapp.log` at all, until something creates a new one there.

The practical consequence: from the moment of rotation until the application is told to reopen its log file, its output is going into a file that logrotate has already rotated out — and once that rotated file is itself deleted N rotations later per `rotate N`, that log data is gone, even though the application appeared to be logging normally the entire time.

The `postrotate`/`endscript` block exists specifically to close this gap — it runs a command, immediately after the rename/compress step, that tells the application to close its current file descriptor and reopen the log file by path, which now correctly resolves to a fresh, empty file at the original name. The exact command varies by how the application supports this: sending `SIGHUP` (a very common convention, and what `rsyslog` itself listens for), a service-specific reload command, or in the systemd-unit case, `systemctl kill -s HUP <unit>` or `systemctl reload <unit>` if the unit defines a reload action.

> ⚠️ **Warning:** A `logrotate.d` config with rotation directives but no `postrotate` reopen hook for an application that doesn't already know to reopen its log files on its own is a silent, deferred outage — logs appear to keep flowing (they're still being written, just into an increasingly stale, already-rotated file) until the retention count catches up and deletes data nobody ever actually lost track of watching for. When adding a `logrotate.d` config for a new application, always confirm whether the application supports a reopen signal, and wire it into `postrotate` — don't assume rotation alone is sufficient just because the file sizes look bounded afterward.

## 6. Centralized Logging Pipelines: The Fleet-Scale Motivation

Everything so far — journald's structured store, rsyslog's file-based output, logrotate's retention — operates on a single host's own logs. That model breaks down operationally the moment there's more than a handful of hosts: an incident spanning several services on several machines can't be diagnosed by SSHing to each one and `tail -f`-ing a local file, and logs on a host that gets terminated (an autoscaled instance, a crashed container) are simply gone if they only ever existed locally.

**Centralized logging** addresses this by shipping logs off-host to a central aggregator, at a conceptual level worth knowing even without deep tooling coverage here:

- **Syslog-native forwarding** — `rsyslog` (or `syslog-ng`, a common alternative implementation) forwarding directly to a remote syslog collector via `@`/`@@` destination lines (3), the simplest path when the existing plain-text pipeline is already in place.
- **Dedicated log-shipping agents** — tools like Filebeat or Fluentd running on each host, tailing local log files (or reading the journal directly via `journalctl -o json`, which [§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md) noted is well-suited to this) and forwarding structured events onward, often with more parsing/enrichment capability than raw syslog forwarding provides.
- **Aggregation and search backends** — an ELK-style stack (Elasticsearch/Logstash/Kibana) or a Loki-style stack (paired with Grafana) as the destination that receives shipped logs, indexes them, and provides fleet-wide search and dashboards — the specific product landscape here is broad and evolves quickly, which is why this roadmap treats it at the motivating-concept level rather than committing to one tool's configuration syntax.

The underlying idea to retain, independent of which specific tools a given environment uses: **single-host log files don't scale operationally across a fleet** — the moment troubleshooting requires correlating events across more than one machine, or a host might disappear before anyone reads its local logs, centralizing log data becomes a requirement rather than a convenience. [§86](./Section-86-Part11-Observability-Strace-Ltrace-Perf-APM.md) (next) picks up the adjacent observability story — metrics and tracing — which centralized logging pipelines are typically built alongside, not instead of.

## 7. Hands-On: Auditing a Host's Rotation and Reopen-Hook Coverage

**Purpose:** Confirm that every application writing meaningfully sized logs on a host actually has a `logrotate.d` config, and that any config with rotation directives also has a working `postrotate` reopen hook — closing the exact silent-gap risk described in 5 before it causes a deferred outage.

```bash
# List every logrotate config on the host
ls /etc/logrotate.d/

# Check a specific config for rotation directives without a postrotate block
grep -L 'postrotate' /etc/logrotate.d/*

# Confirm which large files under /var/log/ have no matching logrotate.d entry at all
du -sh /var/log/* | sort -rh | head -20

# Dry-run what logrotate would actually do, without executing it
logrotate -d /etc/logrotate.conf
```

**Expected output:** A list of configured applications, any configs missing a `postrotate` block flagged by the `grep -L` (files with no match), the largest current log consumers under `/var/log/`, and a `-d` (debug/dry-run) trace showing exactly which files `logrotate` would rotate and which directives would apply, without actually touching anything.

**Production usage example:** This is a natural addition to a fleet-audit sweep in the same spirit as [§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md)'s persistence check and [§64](../Part8/Section-64-Part8-Managing-Repositories-GPG-Signing-Keys.md)'s repository-hygiene check — cheap to run at scale via SSH/Ansible, and it directly surfaces the "rotation configured but reopen hook missing" gap from 5 before it silently loses log data on the next rotation cycle, rather than discovering it only after an incident needed logs that turned out to be truncated.

**Common errors:** Assuming a `postrotate` block's presence alone means it's correct — also verify the actual command it runs is one the target application honors (right signal, right unit name, a reload action the unit file actually defines), not just that a block exists syntactically.

**Troubleshooting:** If `logrotate -d` reports a config file being skipped or a syntax error, check for `missingok`/`notifempty` handling of already-rotated files and confirm file permissions on both the log directory and any state file referenced by `/var/lib/logrotate/status` — a permission problem there silently prevents rotation from running at all under cron/timer-driven invocations even though a manual `-d` dry-run may not fully surface it.

## 8. Common Misconceptions

1. **"journald replaced rsyslog."** [§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md) already flagged this, and it bears repeating here with the mechanics filled in: forwarding (3) is a normal, common coexistence pattern, not a legacy transitional state — plenty of well-configured modern hosts run both deliberately.
2. **"Rotating a log file is enough on its own."** Rotation without a working `postrotate` reopen hook just changes which file a still-running process's descriptor happens to point at (5) — the application keeps writing, but to a file that's about to be deleted by the next rotation cycle, which is a much quieter failure than it sounds.
3. **"`SIGHUP` is a universal reopen signal."** It's a common convention (and what `rsyslog` uses), not a guarantee — some applications use a different signal, a reload subcommand, or don't support reopening their log file at all without a full restart, which needs to be confirmed per application before writing a `postrotate` block.
4. **"Centralized logging is only for huge fleets."** The tipping point is much lower than "huge" — even a handful of hosts behind a load balancer benefits from not needing to SSH into each one individually during an incident, and any host that can be terminated/replaced (autoscaling, spot instances, ephemeral containers) needs its logs shipped somewhere durable before that happens.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between what journald stores and what rsyslog writes to `/var/log/`?"_
**Model answer:** journald ([§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md)) stores structured, binary-format records with queryable named fields. rsyslog writes plain-text lines to files under `/var/log/`, routed by facility and priority rules in `rsyslog.conf`. On a modern systemd host they typically work together — journald captures everything first and can forward a copy to rsyslog via `ForwardToSyslog=`, which then writes the familiar `/var/log/syslog`/`auth.log`-style files.
_What the interviewer is probing for:_ Basic clarity that these are two different storage models operating together, not competing replacements.

**🎯 Intermediate:** _"Why does a `logrotate` config need a `postrotate` hook — what actually breaks without one?"_
**Model answer:** Rotation is fundamentally a rename (plus optional compression) — it doesn't touch the running application at all. A process that already has the log file open holds a file descriptor pointing at the underlying inode, not the path, so after rotation it keeps writing into what is now the renamed old file, while nothing populates a new file at the original path. Without a `postrotate` step telling the application to close and reopen its log file by path, output silently continues going into the rotated-out file until that file is eventually deleted per the `rotate N` retention count — at which point that data is gone, even though nothing looked broken in the meantime.
_What the interviewer is probing for:_ Real understanding of the file-descriptor-vs-path distinction, not just "postrotate restarts things."

**🎯 Senior:** _"A service's log file stopped growing right after a rotation, but the service is clearly still running and handling traffic. What's your diagnosis path?"_
**Model answer:** First suspect exactly the postrotate gap in 5 — check the `logrotate.d` config for that application for a `postrotate` block, and if present, confirm the reopen command it sends is actually one the application honors (right signal, right unit, reload action actually implemented). If there's no `postrotate` block at all, that's very likely the root cause: the process is still writing, just into the rotated-out file (verify with `lsof` against the process's PID, which will show it holding a deleted or renamed file open). The fix is adding or correcting the reopen hook; the immediate mitigation for already-lost visibility is checking whether the rotated file itself (or its `.gz`) still exists and hasn't been pruned by `rotate N` yet.
_What the interviewer is probing for:_ Ability to connect an observed symptom (log growth stopped, service fine) back to the specific rotation mechanics in 5 rather than guessing at unrelated causes.

**🎯 Architect:** _"You're designing the logging baseline for a fleet of autoscaled hosts that can be terminated at any time. What does the pipeline look like end to end?"_
**Model answer:** Local logging (journald persistent storage per [§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md), rsyslog for anything still syslog-based) stays as the first-line capture layer, but it can't be the only copy, since a terminated instance takes its local logs with it. I'd add a shipping layer — either rsyslog forwarding directly to a remote collector, or a dedicated agent reading local files/the journal and forwarding structured events — landing in a centralized aggregation backend with fleet-wide search (6). `logrotate` (or journald's own retention settings) still matters locally for disk-pressure control on each host, but retention policy for anything that actually matters for incident review or compliance lives in the central store, not on ephemeral local disks. I'd treat "logs survive the host that produced them" as a hard requirement for this fleet shape, not an optimization, and validate it by actually terminating a test instance and confirming its recent logs are still searchable centrally afterward.
_What the interviewer is probing for:_ Recognizing that ephemeral infrastructure changes logging from a local-retention problem into a durability-and-shipping problem, and designing accordingly rather than just tuning local rotation settings.

## 10. Key Takeaways

- `rsyslog` routes messages by `facility.priority` in `/etc/rsyslog.conf`/`rsyslog.d/`, producing the standard plain-text `/var/log/` layout (`syslog`/`messages`, `auth.log`/`secure`, `kern.log`) — a genuinely different storage model from journald's structured records, not a legacy version of the same thing.
- journald and rsyslog coexist on most modern hosts via `ForwardToSyslog=` — journald as primary collector, rsyslog handling file output and remote forwarding — confirmed directly per host rather than assumed (3).
- `logrotate` (`/etc/logrotate.conf` + `/etc/logrotate.d/*`) bounds plain-text log growth via `daily`/`weekly`, `rotate N`, `compress`, and `size` directives.
- The `postrotate`/`endscript` hook exists to solve a real mechanical problem: rotation is just a rename, and a running process's open file descriptor keeps pointing at the renamed (soon-to-be-deleted) file until it's told to reopen the log path — missing this hook is a silent, deferred logging outage (5).
- Centralized logging (syslog forwarding, dedicated shippers like Filebeat/Fluentd, ELK/Loki-style backends) exists because single-host log files don't scale operationally once troubleshooting spans multiple hosts or hosts can be terminated before anyone reads their local logs.

## 11. Related Concepts & What's Next

This section is the full rsyslog/logrotate depth [§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md) promised when it introduced journald's forwarding relationship to traditional syslog, and it builds on [§84](./Section-84-Part11-Network-Performance-Analysis.md)'s network-performance tooling only loosely (both are prior sections in this Part's resource-analysis sequence). [§86](./Section-86-Part11-Observability-Strace-Ltrace-Perf-APM.md) (next) moves from logs to the other two observability pillars — metrics and tracing tooling (`strace`, `ltrace`, `perf`) and where APM sits relative to OS-level tools — completing the picture this section's centralized-pipeline discussion (6) gestured toward.

**Next Section:** [§86](./Section-86-Part11-Observability-Strace-Ltrace-Perf-APM.md) — `Section-86-Part11-Observability-Strace-Ltrace-Perf-APM.md`
