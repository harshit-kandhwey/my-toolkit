# Section 65 (Part 9): systemd Architecture: Units, Targets, Dependencies

## 1. Overview: Where This Section Sits

§13 introduced systemd conceptually, deliberately shallow, as the third and final answer to "what should PID 1 do beyond just existing" — unit files replacing shell scripts, targets replacing runlevels, parallel dependency-based startup replacing SysVinit's strict sequence, all just enough vocabulary to compare systemd against SysVinit and Upstart. It promised the real depth was Part 9. §64 then closed out Part 8's package-management arc on repository trust and GPG signing. This section is where those two threads hand off to the promised deep dive: **Part 9 starts here**, and this first section builds the structural model — units, where their files live, what the three standard file sections mean, targets as a dependency graph rather than a numbered list, and the ordering-versus-dependency distinction that trips up more administrators than any other single systemd detail. Operational commands (`systemctl`), full unit-file directive syntax, `journalctl`, timers, and target state transitions are §66–§72 — this section is architecture, not yet hands-on operation.

## 2. The Unit: systemd's Fundamental Abstraction

Everything systemd manages is a **unit**. That single word covers a deliberately broad range of things a traditional init system would never have grouped together — not just "a service," but a mount point, a listening socket, a scheduled timer, a device, a swap area, and more. Each unit is defined by a plain-text configuration file, and systemd determines the unit's **type** from the file's extension:

| Extension  | Unit Type | Manages                                                                                                              |
| ---------- | --------- | -------------------------------------------------------------------------------------------------------------------- |
| `.service` | Service   | A single process/daemon — start, stop, restart, supervise (the type covered in most operational depth going forward) |
| `.socket`  | Socket    | A network or IPC socket, optionally starting its associated service on first connection (socket activation)          |
| `.mount`   | Mount     | A filesystem mount point, as an alternative to (or generated from) `/etc/fstab`                                      |
| `.target`  | Target    | A synchronization point that groups other units — covered in depth in 5                                              |
| `.timer`   | Timer     | A scheduled trigger for another unit, systemd's declarative alternative to cron (full comparison: §69)               |
| `.device`  | Device    | A kernel-exposed device node, tracked via udev integration                                                           |
| `.swap`    | Swap      | A swap file or partition, analogous to `.mount` for swap space                                                       |
| `.path`    | Path      | Triggers another unit when a watched file or directory changes state                                                 |
| `.slice`   | Slice     | A cgroup grouping for resource-management purposes (cgroups proper: Part 13)                                         |

The practical implication of this design is that systemd doesn't treat "start a service" and "mount a filesystem" and "listen on a socket" as different subsystems bolted together — they're all units, all expressible with the same dependency and ordering directives (6), and all inspectable with the same tooling. That uniformity is a direct architectural consequence of the parallel, dependency-graph startup model §13 described only in outline: systemd can only safely parallelize startup because every managed thing — not just services — is a first-class node in one graph it can reason about.

> 💡 **Tip:** `systemctl list-units --type=service` (and `--type=` with any other extension above) filters the live unit list down to one type — useful the moment the full unit list feels too broad to scan, even before §66 covers `systemctl` properly.

## 3. Unit Files and Where They Live

A unit's configuration is a single file, conventionally named `<unit-name>.<type>` (e.g., `sshd.service`, `multi-user.target`). Where that file lives on disk matters more than it might first appear, because systemd searches **multiple directories in a defined precedence order**, and which directory a given file sits in is itself operationally meaningful:

| Directory                                                                        | Purpose                                                                                                                    | Precedence                                |
| -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------- |
| `/usr/lib/systemd/system/` (or `/lib/systemd/system/`, distro-dependent symlink) | Units installed by **packages** — the vendor-shipped, package-manager-owned definition of a service                        | Lowest — the baseline                     |
| `/etc/systemd/system/`                                                           | **Administrator-created or administrator-overridden** units — local units, and override snippets for package-shipped units | Highest — wins over the package copy      |
| `/run/systemd/system/`                                                           | Runtime-only units, generated dynamically or created transiently (not covered further here — later sections)               | Between the two above, and gone on reboot |

The operationally important fact is **precedence, not just location**: a unit file with the same name under `/etc/systemd/system/` takes priority over one under `/usr/lib/systemd/system/`. This is intentional and is systemd's answer to a problem SysVinit handled with sed edits directly into `/etc/init.d/` scripts (a package upgrade would silently clobber those edits): drop a same-named file, or better, a `<unit-name>.d/override.conf` drop-in directory, under `/etc/systemd/system/`, and it survives package upgrades of the vendor unit untouched, because the package manager only owns `/usr/lib/systemd/system/`.

> 💡 **Tip:** `systemctl cat <unit-name>` — even before §66's full command coverage — is worth knowing now: it prints the effective unit definition **and** shows exactly which file(s) contributed to it, including any `/etc/systemd/system/` override, which is the fastest way to answer "why is this service not behaving like the vendor's shipped defaults" without manually diffing two directories.

**Common error:** editing the package-shipped file under `/usr/lib/systemd/system/` directly to make a local change. It works until the next package upgrade overwrites it silently, at which point the customization is gone with no error, no warning, and no obvious trail — exactly the SysVinit-era failure mode the `/etc/systemd/system/` precedence model exists to prevent. Local changes belong in `/etc/systemd/system/`, full stop.

## 4. The Three Standard Unit-File Sections (Conceptual Level)

Unit files are INI-style — bracketed section headers, `Key=Value` lines underneath. §67 covers directive-level syntax and every commonly used key in depth; this section covers only what each of the three standard sections is **for**, conceptually, since that framing matters before the directive list does.

**`[Unit]`** — metadata and dependency/ordering declarations that apply regardless of unit type: a human-readable `Description=`, and the `Requires=`/`Wants=`/`After=`/`Before=` family covered in 6. Every unit type has a `[Unit]` section; it's the one part of the file format shared universally.

**Type-specific section** — named after the unit type: `[Service]` for a `.service` unit, `[Socket]` for `.socket`, `[Mount]` for `.mount`, `[Timer]` for `.timer`, and so on. This is where the type-specific behavior lives — for a `.service` unit, `ExecStart=` (what to run), `Type=` (how systemd should interpret the process's lifecycle — simple, forking, oneshot, and others), `Restart=` (supervision policy). A `.target` unit conspicuously has **no** type-specific section at all — 5 explains why that absence is itself meaningful, not an omission.

**`[Install]`** — governs what happens when a unit is **enabled**: `WantedBy=`/`RequiredBy=` declare which target(s) should pull this unit in when that target is activated, which is what `systemctl enable` actually wires up (mechanically: a symlink into a `.wants/` or `.requires/` directory under the target's own unit directory — §66 covers `enable`/`disable` operationally). The distinction worth holding onto now: `[Unit]`'s dependency directives describe what _this_ unit needs; `[Install]`'s directives describe how _other_ units (specifically, targets) come to want _this_ one, and only the latter is consulted at enable-time rather than at every start.

## 5. Targets: systemd's Generalization of Runlevels

§13 named targets only as "runlevels but more flexible" — this section makes that concrete. A **target** is, structurally, just another unit — a `.target` file, with no type-specific section (4) because a target has nothing of its own to start. Its entire purpose is to exist as a **named synchronization point**: a unit that other units declare a relationship to, so that "bring the system to state X" reduces to "activate target X and let the dependency graph pull in everything that target wants or requires."

`multi-user.target` — the rough analog of SysVinit's runlevel 3, a full non-graphical multi-user system — is reached not by running a numbered sequence of scripts, but by systemd resolving every unit that declares `WantedBy=multi-user.target` (via `[Install]`, 4) or that some already-active unit `Requires=`/`Wants=` transitively, and starting all of it, in parallel wherever the dependency graph allows. `graphical.target` extends this further: it commonly declares `Requires=multi-user.target` plus `After=multi-user.target`, meaning reaching a graphical login state is defined as "reach multi-user state, then add the display-manager layer on top" — a target depending on another target, forming a small graph rather than SysVinit's flat 0–6 numbering.

This is the key conceptual upgrade over runlevels: SysVinit's runlevels are a fixed, mutually exclusive set of seven numbered states with no expressible relationship between them beyond the implicit "higher number, more services." Targets are named, can depend on each other exactly like any other unit dependency (6), and a system can define custom targets for scenarios runlevels have no vocabulary for at all — an application-specific "everything my platform needs is up" synchronization point, for instance, sitting on top of `multi-user.target` without needing to invent a new numbered runlevel to do it.

> 💡 **Tip:** This section introduces targets as a concept — what they are and why they generalize runlevels. §70 is the dedicated deep dive on target-based state transitions: `systemctl isolate`, the default target, rescue/emergency targets, and how a target switch actually unwinds and re-establishes the active unit set. Treat 5 here as the vocabulary §70 will operate on, not a substitute for it.

## 6. Dependency Directives: The Two Separate Questions

systemd's parallel startup model works because every unit declares its relationships to other units explicitly, in `[Unit]` (4). Those declarations answer **two genuinely separate questions**, and conflating them is the single most common source of broken or subtly-wrong unit files:

**Question 1 — "Does this unit need that unit to be active at all?"** (dependency, not ordering)

| Directive   | Meaning                                                                                                                    |
| ----------- | -------------------------------------------------------------------------------------------------------------------------- |
| `Requires=` | Hard dependency — if the listed unit fails to start (or is stopped later), systemd stops this unit too                     |
| `Wants=`    | Soft dependency — systemd tries to start the listed unit alongside this one, but this unit proceeds even if that one fails |

**Question 2 — "Does this unit need that unit to be started before (or after) it, once both are going to run anyway?"** (ordering, not dependency)

| Directive | Meaning                                                                          |
| --------- | -------------------------------------------------------------------------------- |
| `After=`  | If both units are going to start, start the listed unit first                    |
| `Before=` | If both units are going to start, start _this_ unit first, before the listed one |

The part worth internalizing precisely: **declaring `Requires=` or `Wants=` alone says nothing about order.** Without an accompanying `After=`/`Before=`, systemd is free to start both units **in parallel**, at the same time, because "must both be active" and "must start in a specific sequence" are independently declared facts, not one fact systemd infers from the other. This is a deliberate design choice, not an oversight — it's exactly what enables the parallel-by-default startup model §13 promised over SysVinit's forced sequencing, but it means a unit author must declare _both_ directives whenever _both_ constraints genuinely apply.

> ⚠️ **Warning:** This is the single most common systemd unit-file mistake, worth a dedicated example. Suppose a custom `.service` unit needs a database to be not just present but genuinely reachable before its own process starts — an engineer writes:
>
> ```ini
> [Unit]
> Description=Example App
> Requires=postgresql.service
>
> [Service]
> ExecStart=/usr/local/bin/example-app
> ```
>
> This declares that the app **needs** PostgreSQL to be active — if PostgreSQL isn't running or fails, systemd will stop this unit too. But it says **nothing about start order**. systemd is free to start `example-app.service` and `postgresql.service` at the same time, in parallel, since only `Requires=` was declared. In practice this frequently "works" in testing (PostgreSQL happens to be fast enough, or already running) and then fails intermittently in production — a cold boot, a slower disk, a busier host — when the app's process starts and immediately fails to connect because PostgreSQL genuinely hasn't finished initializing yet. The fix is declaring **both** constraints, because they're both true and neither implies the other:
>
> ```ini
> [Unit]
> Description=Example App
> Requires=postgresql.service
> After=postgresql.service
> ```
>
> `Requires=` says "this must be up." `After=` says "start it first." A unit that only needs one of the two — say, a unit that merely _prefers_ another be up but tolerates its absence and genuinely doesn't care about order — should declare only the directive that's actually true, rather than reflexively pairing them out of caution. But whenever both matter, which is common for anything with a real runtime dependency on another service, both directives are required, and reasoning "I declared `Requires=`, so ordering is implied" is the exact misconception that produces boot-order-dependent, hard-to-reproduce production failures.

`Requires=`/`After=` together is common enough that `BindsTo=` exists as a stricter variant of `Requires=` (the bound-to unit stopping immediately stops this one too, not just on failure) — full directive-level nuance, including `Wants=`/`After=` combinations and the negative directives (`Conflicts=`), is §67's territory; this section's job is establishing that ordering and dependency are separate axes at all.

## 7. `systemd-analyze`: Visualizing the Dependency Graph

Once units, targets, and the dependency/ordering distinction exist as a mental model, the natural next question is _how to see it_ on a real running system rather than reasoning about it purely from unit-file text. `systemd-analyze` is the tool family for that — full flag-level coverage belongs in a later hands-on pass, but two subcommands are worth knowing exist now, as a teaser rather than a tutorial:

- **`systemd-analyze blame`** — lists every unit that was started during boot, sorted by how long it took to become active, slowest first. It's the fastest way to answer "what's actually making boot slow" with data instead of guessing, and it directly demonstrates the payoff of the parallel startup model 6 described: a unit high on this list isn't necessarily delaying _everything else_, only whatever specifically declared `After=` on it.
- **`systemd-analyze critical-path`** — shows the actual **critical path**: the specific chain of `After=`-ordered units that determined total boot time, as opposed to `blame`'s flat slowest-individually list. This is the more precise tool when the real question is "which chain of ordering dependencies is the one actually limiting how fast this system can possibly boot," since a slow unit not on the critical path could be made instant with zero effect on total boot time.

Both commands are direct, practical payoffs of everything in 2 through 6: they only make sense once units, dependency directives, and ordering directives are understood as the graph systemd is actually resolving at boot — a flat list of process start times, absent that model, wouldn't distinguish "slow but harmless" from "slow and the actual bottleneck."

## 8. Common Misconceptions

1. **"A unit is basically just a service."** Services are the most commonly authored unit type, but sockets, mounts, timers, devices, and targets are all units too, sharing the same dependency/ordering vocabulary (2) — treating "unit" and "service" as synonyms causes confusion the moment a `.target` or `.timer` file needs reasoning about.
2. **"Editing the vendor's unit file under `/usr/lib/systemd/system/` is fine if it's a small change."** It survives exactly until the next package upgrade silently overwrites it — `/etc/systemd/system/` exists specifically so local changes survive upgrades, and its higher precedence is the whole mechanism that makes that true (3).
3. **"`Requires=` implies start order."** It doesn't — dependency (`Requires=`/`Wants=`) and ordering (`After=`/`Before=`) are separate, independently declared axes, and a unit needing both must declare both explicitly (6). This is the single most common source of intermittent, boot-order-dependent failures in hand-written unit files.
4. **"Targets are just renamed runlevels."** §13 flagged this briefly; this section makes the mechanism concrete — a target is a unit like any other, capable of depending on other targets and being depended on by ordinary units via `[Install]`, forming a graph rather than SysVinit's flat, mutually exclusive 0–6 numbering (5).
5. **"`[Unit]`'s dependency directives and `[Install]`'s `WantedBy=` do the same job."** `[Unit]` directives describe what _this_ unit needs at start time; `[Install]`'s `WantedBy=`/`RequiredBy=` describe how _other_ units (targets, typically) come to pull this one in when _enabled_ — one is evaluated when this unit starts, the other when `systemctl enable` is run against it (4).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What is a systemd unit, and how does systemd know what kind of unit a given file describes?"_
**Model answer:** A unit is systemd's fundamental abstraction for anything it manages — not just services, but sockets, mounts, timers, devices, swap areas, and targets too. systemd determines the unit's type from the file's extension — `.service`, `.socket`, `.mount`, `.target`, `.timer`, and so on — and each type has its own type-specific configuration section in the file beyond the shared `[Unit]` section every unit type has.
_What the interviewer is probing for:_ Whether the candidate understands "unit" as a genuinely broader category than "service," which is the foundation everything else in systemd's architecture builds on.

**🎯 Intermediate:** _"A colleague writes a unit file with `Requires=postgresql.service` and no `After=`, expecting their app to wait for PostgreSQL to be ready before starting. What's wrong, and what actually happens?"_
**Model answer:** `Requires=` only declares that PostgreSQL must be active — it says nothing about start order. Without an `After=postgresql.service` line too, systemd is free to start both units in parallel, since dependency and ordering are separate, independently declared constraints. In practice the app unit may start before PostgreSQL has actually finished initializing, causing intermittent connection failures that are especially likely on a cold boot or a slower host, even though the same setup might "work" in testing where PostgreSQL happens to already be up. The fix is declaring both `Requires=` and `After=` together, since both constraints are actually true here.
_What the interviewer is probing for:_ Direct, specific understanding of the ordering-versus-dependency split, not just awareness that "systemd has dependencies" — this is one of the most common real-world unit-file bugs.

**🎯 Senior:** _"Why does `/etc/systemd/system/` take precedence over `/usr/lib/systemd/system/`, and what operational problem does that solve?"_
**Model answer:** Package managers own and overwrite `/usr/lib/systemd/system/` on every package upgrade — any local edit made directly to a file there is silently lost the next time that package updates, with no warning. `/etc/systemd/system/` exists as the administrator-owned layer specifically so local customizations — either a full same-named override or a `<unit>.d/override.conf` drop-in — persist across vendor package upgrades, because the package manager never touches that directory. It's the systemd-era fix for a real SysVinit-era failure mode, where hand-edited `/etc/init.d/` scripts routinely got clobbered by package upgrades with no trail of what was lost. `systemctl cat <unit>` is the fast way to confirm which layer is actually in effect for a given unit before assuming vendor defaults are what's running.
_What the interviewer is probing for:_ Recognizing precedence as solving a specific, real operational failure mode, not just reciting "there are two directories."

**🎯 Architect:** _"You've inherited a fleet where boot times vary widely across otherwise-identical hosts, and some services intermittently fail to connect to dependencies on first boot after a reboot. How do you approach diagnosing this using systemd's architecture, before touching any config?"_
**Model answer:** I'd treat the intermittent first-boot connection failures and the boot-time variance as two related but distinct investigations, both rooted in the same architectural facts. For the connection failures, my first hypothesis is exactly the ordering-vs-dependency gap — a unit declaring `Requires=`/`Wants=` on a dependency without the matching `After=`, meaning systemd is legitimately free to start both in parallel and the failure is a race, not a fluke; `systemctl cat` on the affected unit tells me immediately whether both directives are present. For boot-time variance, I'd reach for `systemd-analyze blame` to see which units are slow in absolute terms and `systemd-analyze critical-path` to see which chain of `After=`-ordered units is actually gating total boot time on the slower hosts — variance across "identical" hosts often means the critical path itself differs, which points toward environment-specific slowness (disk, network-dependent units) rather than a config difference. I'd also check whether affected hosts have accumulated local overrides under `/etc/systemd/system/` that drifted from the fleet baseline, since that's a common source of "identical" hosts behaving differently. None of this requires touching config yet — it's establishing, from the running system's own graph and timing data, exactly which architectural fact (missing ordering directive, genuine critical-path difference, or config drift) is actually responsible before deciding what to change.
_What the interviewer is probing for:_ Using the ordering/dependency model and `systemd-analyze` as real diagnostic tools against a production-shaped scenario, not just reciting definitions — and separating symptom investigation from premature remediation.

## 10. Key Takeaways

- A **unit** is systemd's universal abstraction — services, sockets, mounts, timers, devices, swap, and targets are all units, sharing the same file-based configuration model and the same dependency/ordering vocabulary (2).
- Unit files live in a precedence order: `/usr/lib/systemd/system/` for package-installed units (lowest), `/etc/systemd/system/` for administrator overrides and local units (highest, and survives package upgrades) — editing vendor files directly is a common, silently-reversible mistake (3).
- Unit files have three conceptual sections: `[Unit]` (shared metadata and dependency/ordering declarations), a type-specific section (`[Service]`, `[Socket]`, etc. — absent entirely for `.target` units, since targets start nothing of their own), and `[Install]` (governs what `systemctl enable` wires up, via `WantedBy=`/`RequiredBy=`) (4).
- **Targets** generalize SysVinit's fixed 0–6 runlevels into named units that group other units as synchronization points and can depend on each other, forming a graph (`graphical.target` building on `multi-user.target`) rather than a flat numbered sequence (5).
- **Dependency** (`Requires=`/`Wants=` — is the other unit active at all) and **ordering** (`After=`/`Before=` — in what sequence do they start) are separate, independently declared concerns — declaring one does not imply the other, and this gap is the most common real-world unit-file bug (6).
- `systemd-analyze blame` and `systemd-analyze critical-path` turn this architectural model into observable boot-time data — slowest-individually versus the actual ordering chain limiting total boot time — and are the natural first tools once the unit/dependency/ordering model is understood (7).

## 11. Related Concepts & What's Next

This section is the direct, promised continuation of §13's conceptual systemd introduction from Part 2, and opens Part 9 following Part 8's close at §64. The unit-file locations and precedence model here (3) sets up §66's operational `systemctl` commands (`enable`/`disable` manipulate exactly the symlinks 4 described), and the `[Unit]`/type-specific/`[Install]` section overview here is the scaffolding §67 fills in with full directive-level syntax for writing custom unit files. The targets introduced conceptually in 5 get their full state-transition treatment — `systemctl isolate`, default targets, rescue/emergency modes — in §70. `systemd-analyze`'s teaser in 7 will resurface with more operational depth once `journalctl` (§68) and timers (§69) are covered, since boot-time analysis and logging are closely related diagnostic tools in practice.

**Next Section:** §66 — `Section-66-Part9-Managing-Services-Systemctl.md`
