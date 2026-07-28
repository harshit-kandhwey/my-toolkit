# Section 72 (Part 9): Time Synchronization: chrony/ntpd, timedatectl

## 1. Overview: Why Clock Accuracy Is an Operational Concern, Not a Cosmetic One

It's tempting to treat system time as a background detail — the clock in the corner of a screen nobody's looking at on a server. On a production fleet, an inaccurate clock is a correctness problem with concrete failure modes, several of which have already surfaced implicitly elsewhere in this knowledge base without being named as time-synchronization issues:

- **TLS/SSL certificate validation depends on correct time.** §56 covered SSH and TLS handshakes; every certificate carries a validity window (`notBefore`/`notAfter`), and a client or server with a clock skewed far enough outside that window will reject an otherwise-valid certificate as expired or not-yet-valid — a failure that looks like a certificate problem but is actually a clock problem.
- **Distributed log correlation across a fleet assumes synchronized clocks.** §68 covered journald's structured, queryable timestamps in depth, but query precision is only as good as clock accuracy — reconstructing the order of events across multiple hosts during an incident (which host's request hit which service first) silently falls apart if each host's clock drifts independently, even though every individual host's own local log ordering still looks internally consistent.
- **Authentication protocols with tight clock-skew tolerances can fail outright.** Kerberos is the canonical example — it typically enforces a default skew tolerance on the order of five minutes, and a client or server outside that window fails authentication with an error that gives no obvious hint the root cause is clock drift rather than credentials or configuration.
- **Scheduled task accuracy depends on it.** §69 covered systemd timers' `OnCalendar=` scheduling — a timer configured to fire at 02:00 UTC assumes the system clock reading 02:00 UTC actually corresponds to 02:00 UTC, not a clock that has quietly drifted by minutes or hours.

None of these are exotic edge cases — they're the direct, predictable consequences of clock drift on any host that talks TLS, ships logs to a central store, authenticates against Kerberos/AD, or runs scheduled jobs, which describes most production Linux servers. This section covers how Linux keeps its clock accurate: the NTP protocol conceptually, the three common implementations (`chrony`, `ntpd`, `systemd-timesyncd`), the unified `timedatectl` control surface, and timezone configuration.

> 💡 **Tip:** Keep two layers distinct throughout this section, the same way §13 separated "what is PID 1" from "how does it start services": (1) the **backend daemon** actually doing the network time-sync work — `chrony`, `ntpd`, or `systemd-timesyncd`, only one of which is normally active at a time — and (2) `timedatectl`, a **systemd-level control and query tool** that sits above whichever backend is running, regardless of which one it is.

## 2. NTP Conceptually: Stratum Hierarchy and Gradual Adjustment

**NTP (Network Time Protocol)** is the underlying protocol nearly every Linux time-sync tool speaks, and understanding its two core ideas explains why the tooling behaves the way it does.

**Stratum hierarchy.** NTP organizes time sources into numbered strata:

| Stratum | Meaning                                                                                    |
| ------- | ------------------------------------------------------------------------------------------ |
| 0       | Reference clocks themselves — atomic clocks, GPS receivers — not directly queried over NTP |
| 1       | Servers directly attached to a stratum-0 source                                            |
| 2       | Servers that sync from stratum-1 servers                                                   |
| 3+      | Servers that sync from the stratum above them, and so on                                   |

A typical Linux server is a stratum-2 or stratum-3 NTP client, querying a handful of upstream servers (public pools like `pool.ntp.org`, or internal corporate NTP servers) rather than talking to a stratum-1 source directly. Querying multiple servers isn't redundancy for its own sake — the client compares responses across several sources to detect and discard an outlier (a server that's itself wrong), rather than trusting a single source blindly.

**Gradual adjustment, not a hard jump.** This is the detail most worth internalizing. When an NTP client discovers its clock is off from the network-consensus time, its default behavior is to **slew** the clock — speed it up or slow it down very slightly over a period of time until it converges — rather than **stepping** it, which is an instantaneous jump straight to the correct value. Small, ongoing drift (the kind every un-synced clock naturally accumulates from imperfect hardware oscillators) is corrected by slewing; a large enough initial offset (well past what continuous slewing could reasonably fix, or after being offline long enough to drift substantially) is corrected by an outright step, typically only once, at startup.

> ⚠️ **Warning:** A sudden **backward** time jump — stepping the clock back rather than forward — can break things that assume time only moves forward. Build tools like `make` compare file modification timestamps to decide what needs rebuilding, and a backward jump can make a file appear "from the future" relative to the new (earlier) clock reading, causing stale-looking rebuild decisions. Log entries written just before and just after a backward step can appear out of chronological order in anything sorting purely by timestamp. This is exactly why slewing is preferred for small corrections — it never reverses the direction of time, it just changes its rate briefly — and why a hard step is reserved for startup or genuinely large offsets rather than being the routine correction mechanism.

## 3. `chrony`: The Modern Default

**chrony** is the default NTP implementation on most current mainstream distributions (RHEL/CentOS/Fedora, and increasingly Debian/Ubuntu as well) — this section treats it as the primary tool, with `ntpd` (4) and `systemd-timesyncd` (5) as the alternatives worth recognizing on other hosts.

chrony was designed with characteristics that suit modern, especially virtualized or intermittently-connected, infrastructure better than the legacy `ntpd`:

- **Faster resynchronization after being offline.** A laptop that sleeps, or a VM that's paused/migrated/snapshotted, comes back with a clock that may be significantly off — chrony converges on the correct time much faster than `ntpd` does in this scenario, which matters directly for cloud VMs that get live-migrated or resumed from a snapshot.
- **Better behavior on intermittent or high-latency network connections** — it doesn't require a constant, low-jitter connection to a time server to perform well, which suits cloud and virtualized environments where network conditions to an external NTP pool aren't always as stable as a physical on-prem network.
- **Works even without a network connection at boot**, adjusting once connectivity appears, rather than requiring network availability at the moment it starts.

**Key operational commands:**

```bash
# Overall sync status: current offset, source, tracking state
chronyc tracking

# List configured time sources and their current state
chronyc sources

# More detailed per-source statistics
chronyc sourcestats
```

**Example usage and expected output:**

```bash
$ chronyc tracking
Reference ID    : C0A80101 (ntp1.internal.example.com)
Stratum         : 3
Ref time (UTC)  : Mon Jul 27 09:58:11 2026
System time     : 0.000023091 seconds slow of NTP time
Last offset     : +0.000015382 seconds
RMS offset      : 0.000041207 seconds
Frequency       : 4.312 ppm slow
...

$ chronyc sources
MS Name/IP address         Stratum Poll Reach LastRx Last sample
===============================================================================
^* ntp1.internal.example.com     2   6   377    23   +12us[  +9us] +/-  1.1ms
^+ ntp2.internal.example.com     2   6   377    45   -8us[ -11us] +/-  1.4ms
```

**Key flags/columns:**

| Field                       | Meaning                                                                           |
| --------------------------- | --------------------------------------------------------------------------------- |
| `^*` (in `chronyc sources`) | The source currently selected as the best/synchronized-to reference               |
| `^+`                        | A candidate source being tracked but not currently the primary selection          |
| `System time`               | Current offset between the local clock and chrony's best estimate of correct time |
| `Stratum`                   | The stratum of the upstream source being used (1)                                 |

**Production usage example:** During an incident where TLS handshakes are unexpectedly failing or Kerberos auth is intermittently rejecting valid credentials, `chronyc tracking` is a fast first check — a `System time` offset of multiple seconds (rather than sub-millisecond, which is typical for a healthy synced host) is a strong signal the clock, not the application or credentials, is the actual root cause.

**Common errors:** Assuming chrony is running and synced just because the package is installed — `chronyc tracking` reporting a large offset, or `chronyc sources` showing no reachable sources (`Reach` column at `0`), means the daemon isn't actually achieving sync, often due to a firewall blocking outbound NTP traffic (UDP port 123) to the configured servers.

## 4. `ntpd`: The Legacy Daemon

**`ntpd`** is the original, historical NTP daemon — the reference implementation many administrators cut their teeth on, and still found on older systems or in environments that haven't migrated to chrony. It implements the same underlying NTP protocol (2) but with slower convergence after being offline and a heavier resource footprint than chrony, which is precisely the gap chrony was built to close for modern, often-virtualized infrastructure.

`ntpd`'s operational surface is analogous to chrony's — `ntpq -p` lists configured peers and their sync state, roughly the equivalent of `chronyc sources`. This section doesn't go deeper into `ntpd`-specific syntax: on a currently-provisioned mainstream distribution host, seeing `ntpd` running rather than `chrony` is itself a signal worth investigating — either a deliberate legacy choice or a host that predates the distribution's switch to chrony as default — the same kind of "which init system is this, and why" question §13's hands-on check raised for PID 1.

## 5. `systemd-timesyncd`: The Lightweight SNTP Option

**`systemd-timesyncd`** is a third option, bundled with systemd itself, and it takes a deliberately narrower approach than either chrony or `ntpd`: it's an **SNTP (Simple NTP) client only** — it synchronizes the system clock against a remote server but doesn't implement chrony/ntpd's fuller feature set (it can't act as an NTP server for other hosts, and its accuracy characteristics are less refined than a full NTP implementation's).

That narrower scope is a deliberate trade-off, not an oversight — `systemd-timesyncd` is common on:

- **Minimal or container-oriented base images**, where a lightweight built-in client that needs no separate package is preferable to installing and configuring a full chrony/ntpd stack.
- **Desktop and general-purpose installs** where sub-millisecond accuracy doesn't matter and "close enough, with minimal footprint" is the right trade-off.

For most application-serving production hosts — especially anything with TLS-heavy traffic, Kerberos/AD integration, or a need for tight fleet-wide log correlation (1) — chrony's better accuracy and faster resync justify the extra weight over `timesyncd`. `timesyncd` is adequate, not a strict downgrade to avoid everywhere; the right choice depends on how much clock precision the workload actually needs.

## 6. `timedatectl`: The Unified Control Surface

**`timedatectl`** is the systemd-level tool for querying and controlling time settings, and — this is the key structural point from the Tip in 1 — it works **regardless of which backend** (chrony, `ntpd`, or `timesyncd`) is actually doing the network synchronization. `timedatectl` reports status and toggles high-level settings; it does not itself implement NTP.

**Purpose:** Inspect and control system time, timezone, and whether NTP synchronization is enabled, from one consistent command regardless of the underlying sync daemon.

**Syntax and key subcommands:**

```bash
timedatectl [command]
```

| Command                          | Meaning                                                                                    |
| -------------------------------- | ------------------------------------------------------------------------------------------ |
| `status`                         | Show current time, timezone, whether the RTC is in local time or UTC, and NTP sync state   |
| `set-ntp true` / `set-ntp false` | Enable or disable NTP-based synchronization (starts/stops the active backend accordingly)  |
| `set-timezone <Region/City>`     | Change the system timezone (6)                                                             |
| `set-time "YYYY-MM-DD HH:MM:SS"` | Manually set the system clock — **only works when NTP sync is disabled** (`set-ntp false`) |
| `list-timezones`                 | List all valid timezone identifiers accepted by `set-timezone`                             |

**Example usage and expected output:**

```bash
$ timedatectl status
               Local time: Mon 2026-07-27 09:58:11 UTC
           Universal time: Mon 2026-07-27 09:58:11 UTC
                 RTC time: Mon 2026-07-27 09:58:10
                Time zone: UTC (UTC, +0000)
System clock synchronized: yes
              NTP service: active
          RTC in local TZ: no
```

**Key concept — system clock vs. RTC:** The **system clock** is what the kernel maintains in memory while the machine is running, and what NTP synchronization actually adjusts. The **RTC (Real-Time Clock)**, sometimes called the hardware clock, is a small battery-backed clock on the motherboard that keeps running while the machine is powered off, and is what the system clock gets initialized from at boot before any network sync has happened. `timedatectl status`'s `RTC in local TZ` line matters because a hardware clock set to local time rather than UTC is a classic source of confusion on dual-boot machines and a general best-practice violation on servers (6).

**Common errors:** Running `timedatectl set-time ...` on a host where NTP sync is currently enabled and being confused by the failure — the command explicitly refuses when `set-ntp` is `true`, since a manual time set would just be immediately overwritten by the next sync cycle anyway; the fix is `timedatectl set-ntp false` first, set the time, then decide whether to re-enable NTP sync afterward.

**Troubleshooting:** If `System clock synchronized: no` persists, check the active backend directly — `chronyc tracking`/`chronyc sources` (3) for chrony, `ntpq -p` for `ntpd` — since `timedatectl` surfaces the backend's sync state but doesn't diagnose _why_ it isn't synced (firewall blocking UDP 123, unreachable configured servers, or the backend service not actually running are the usual causes).

## 7. Timezone Configuration: `/etc/localtime` and UTC-on-Servers

Timezone is configured independently of NTP sync — a host can be perfectly time-synced and still display the wrong local time if its timezone is misconfigured, and the two are easy to conflate when troubleshooting "the time looks wrong."

- **`/etc/localtime`** is a **symlink** to a zoneinfo file under `/usr/share/zoneinfo/` (for example, `/usr/share/zoneinfo/America/New_York`) — this is the actual mechanism `timedatectl set-timezone` manipulates under the hood; changing timezone is just repointing this symlink to a different zoneinfo file.
- **`/etc/timezone`** exists as a separate, plain-text file on Debian-family distributions (containing just the zone name, e.g. `America/New_York`) — kept in sync with the `/etc/localtime` symlink by the distribution's tooling, but a detail that's Debian/Ubuntu-specific rather than universal.

> ⚠️ **Warning:** Production servers should run **UTC**, not a local timezone, and this is a deliberate best practice rather than a default to leave unquestioned. Local time observing Daylight Saving Time creates a genuine ambiguity: on the "fall back" transition, a given wall-clock hour occurs **twice** in the same day, and on "spring forward" a given wall-clock hour doesn't occur at all — either case makes log timestamps, `OnCalendar=` timer scheduling (§69), and cross-host event correlation (1) ambiguous or outright broken for that one day a year. UTC has no DST transitions, so a timestamp is always unambiguous. This doesn't mean nothing on the host should ever display local time — application-layer display logic can convert UTC to a user's local timezone at presentation time — but the system clock and logs themselves should be UTC, with timezone conversion pushed to whatever layer actually needs to show a human a localized time.

**Hands-On: Setting a server to UTC and confirming sync status:**

```bash
# Set the system timezone to UTC
timedatectl set-timezone UTC

# Confirm timezone and NTP sync state together
timedatectl status

# Confirm which zoneinfo file /etc/localtime now points to
readlink -f /etc/localtime
```

**Expected output:** `timedatectl status` showing `Time zone: UTC (UTC, +0000)` and `System clock synchronized: yes`; `readlink -f /etc/localtime` resolving to `/usr/share/zoneinfo/UTC`.

**Production usage example:** This pair of checks belongs in the same kind of provisioning/hardening baseline §68 recommended for journald persistence — confirming both "is this host's clock actually syncing" and "is it configured to UTC" during initial setup or a fleet audit is far cheaper than discovering a DST-related scheduling or log-correlation bug in production months later.

## 8. Common Misconceptions

1. **"chrony and NTP are the same thing."** NTP (2) is the protocol; chrony is one of several implementations that speak it (alongside `ntpd` and `systemd-timesyncd`, 3–5). Conflating the two obscures that a host can switch which daemon does the syncing without changing what protocol is being spoken on the wire.
2. **"`timedatectl` is what synchronizes the clock."** `timedatectl` is a control and status surface sitting above whichever backend (chrony/`ntpd`/`timesyncd`) is actually doing the network sync work (6) — it can enable/disable sync and report status, but it isn't itself an NTP client implementation.
3. **"NTP just jumps the clock to the correct time whenever it's off."** The default and preferred behavior is gradual slewing, not a hard step, specifically because a sudden backward jump can produce out-of-order logs or confuse timestamp-dependent tools like `make` (2) — steps are reserved for startup or genuinely large offsets, not routine correction.
4. **"Local timezone on a server is just a cosmetic display preference."** DST transitions create a genuinely ambiguous or missing wall-clock hour twice a year, which directly breaks unambiguous log ordering and `OnCalendar=` timer scheduling (§69) — UTC-on-servers (7) is a correctness recommendation, not a stylistic one.
5. **"The system clock and the RTC/hardware clock are the same thing."** They're distinct — the system clock is kernel-maintained and what NTP adjusts while the machine runs; the RTC is a separate battery-backed hardware clock that persists across power-off and seeds the system clock at boot (6). A drifted RTC on a machine that's been powered off for a long time is a normal, expected state that NTP sync corrects shortly after boot.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"Why does it matter if a server's clock is slightly wrong?"_
**Model answer:** Beyond the clock just "looking wrong," an inaccurate clock breaks concrete things: TLS certificate validation checks the current time against the certificate's validity window, so a sufficiently skewed clock can cause valid certificates to be rejected; log timestamps across a fleet stop being reliably comparable for reconstructing event order during an incident; authentication protocols like Kerberos enforce tight clock-skew tolerances and fail outright if a host drifts past them; and scheduled tasks (systemd timers, cron) fire at the wrong actual moment relative to intended time. It's a correctness issue with several distinct failure modes, not a cosmetic one.
_What the interviewer is probing for:_ Whether the candidate has concrete examples beyond a vague "things could break," and connects clock accuracy to specific protocols/mechanisms rather than treating it as an abstract concern.

**🎯 Intermediate:** _"What's the difference between chrony and systemd-timesyncd, and when would you choose one over the other?"_
**Model answer:** Both ultimately keep the system clock synced over the network, but chrony is a fuller NTP implementation with better accuracy, faster resynchronization after being offline (important for VMs that pause/resume or migrate), and better behavior over intermittent or higher-latency connections — it's the modern default on most current distributions. `systemd-timesyncd` is a deliberately lightweight SNTP-only client bundled with systemd — simpler, no separate package needed, adequate accuracy for general use, but not as precise or full-featured as chrony, and it can't act as an NTP server for other hosts. I'd default to chrony for production application servers, especially anything doing TLS-heavy traffic, Kerberos/AD auth, or needing tight fleet-wide log correlation, and consider `timesyncd` acceptable on minimal/container-oriented images or general-purpose hosts where sub-millisecond precision doesn't matter.
_What the interviewer is probing for:_ Understanding that this is a genuine trade-off (footprint/simplicity vs. accuracy/resync speed) rather than "chrony is just strictly better," and the ability to map the trade-off to a workload's actual requirements.

**🎯 Senior:** _"A teammate manually ran `date` to fix a server's clock during an incident, and now some log timestamps around that moment appear out of order. What happened, and how should this have been handled instead?"_
**Model answer:** Manually setting the clock with `date` (or `timedatectl set-time`, which requires disabling NTP sync first) performs a hard step rather than the gradual slewing NTP prefers — if the correction moved the clock backward, any log entries written in the brief window between the (wrong) pre-correction time and the (correct) post-correction time can appear out of chronological order relative to what was written just before the jump, since time briefly appeared to run backward from the log's perspective. The better approach during the incident would have been to let the existing NTP backend (chrony, most likely) resolve the offset itself — `chronyc tracking` to confirm the actual offset and whether chrony was even running/synced, and if it had drifted for some structural reason (blocked firewall port, misconfigured servers), fix that root cause and let chrony's own convergence logic correct the clock, which avoids the abrupt jump. If an immediate hard correction genuinely was necessary, it's worth flagging to anyone investigating that incident's logs that timestamps spanning the manual correction window aren't reliably ordered.
_What the interviewer is probing for:_ Connecting the slew-vs-step distinction (2) to a concrete incident scenario, and knowing the right remediation path (fix the sync mechanism, don't fight it with manual overrides) rather than just diagnosing the symptom.

**🎯 Architect:** _"You're defining a time-sync baseline for a new fleet spanning bare-metal, VMs, and containers. What does that baseline look like?"_
**Model answer:** I'd standardize on chrony as the backend on any host with a full OS (bare-metal and VMs) given its better resync behavior after VM pause/migrate cycles and its suitability for intermittently-connected infrastructure — and reserve `systemd-timesyncd` only for genuinely minimal images where footprint matters more than sub-millisecond accuracy, deciding that deliberately rather than by whatever the base image happens to default to. I'd point every host at internal, redundant NTP servers rather than public pool servers directly where network policy allows it, since that keeps sync traffic inside the network and reduces dependency on external reachability. UTC would be enforced fleet-wide as a baked-in golden-image setting (Part 13's config-management coverage) rather than left to each host's regional default, specifically to avoid the DST log-ordering and scheduling ambiguity from 7. I'd build a fleet-wide check — `chronyc tracking`'s offset and `timedatectl status`'s `System clock synchronized` field, collected the same way as the journald-persistence audit in §68 — into routine health monitoring, since clock drift is exactly the kind of silent failure that doesn't announce itself until it causes a downstream TLS or Kerberos failure that looks unrelated. For containers specifically, I'd confirm they inherit the host kernel's clock (containers don't run their own independent clock the way a VM does) rather than assuming any in-container time-sync tooling is doing meaningful work.
_What the interviewer is probing for:_ Fleet-scale, proactive baseline design — standardizing rather than accepting per-image defaults, building drift detection into monitoring rather than waiting for a downstream symptom, and understanding how containers' clock model differs from VMs'.

## 10. Key Takeaways

- Clock accuracy is an operational correctness concern, not cosmetic — TLS certificate validation, fleet-wide log correlation (§68), Kerberos/AD's tight skew tolerances, and `OnCalendar=` timer accuracy (§69) all depend on it directly (1).
- NTP organizes time sources into a stratum hierarchy and, critically, prefers gradually **slewing** the clock over hard **stepping** — a sudden backward jump can cause out-of-order logs or confuse timestamp-dependent tools like `make` (2).
- `chrony` is the modern default on most current distributions, chosen for faster resync after being offline and better behavior on intermittent/virtualized network conditions — `chronyc tracking`/`chronyc sources` are the primary status commands (3).
- `ntpd` is the legacy daemon, still found on older systems, superseded by chrony's better fit for virtualized/intermittently-connected infrastructure (4); `systemd-timesyncd` is a deliberately lightweight SNTP-only alternative common on minimal/container-oriented images, adequate but less precise than chrony (5).
- `timedatectl` is a unified systemd-level control surface that works regardless of which backend is doing the actual syncing — `status`, `set-ntp`, `set-timezone`, and `set-time` (which only works with NTP sync disabled) — and it's distinct from the system clock vs. RTC/hardware-clock distinction it also reports on (6).
- `/etc/localtime` (a symlink to a zoneinfo file) and Debian's separate `/etc/timezone` control timezone independently of sync status; servers should run **UTC**, not local time, specifically to avoid the DST-transition ambiguity that breaks unambiguous log ordering and scheduling (7).

## 11. Related Concepts & What's Next

This section closes Part 9 (§65–§72) by tying together threads several earlier sections in this Part left implicit: §68's journald timestamps and §69's `OnCalendar=` timer scheduling both silently assumed an accurate system clock, and this section is where that assumption finally gets examined directly rather than taken for granted. It also connects forward to §56 (Part 7), where TLS certificate validity windows and SSH's own time-sensitive behaviors depend on the same clock-accuracy foundation covered here. Part 10 (§73, Advanced Storage and LVM) is next, moving from systemd/services administration into logical volume management — physical volumes, volume groups, and logical volumes — a different corner of system administration with no direct dependency on this section's material.

**Next Section:** §73 — `Section-73-Part10-LVM-Physical-Volumes-Volume-Groups-Logical-Volumes.md`
