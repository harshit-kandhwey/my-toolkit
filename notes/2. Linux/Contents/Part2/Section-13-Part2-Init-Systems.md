# Section 13 (Part 2): init Systems: SysVinit vs. Upstart vs. systemd

## 1. Overview: What "init" Actually Is

[§12](./Section-12-Part2-Boot-Process.md) ended with the kernel executing exactly one program as **PID 1** and then stepping back from driving the boot sequence at all. This section picks up at that exact handoff and answers the question [§12](./Section-12-Part2-Boot-Process.md) deliberately left open: **what is that PID 1 program, and why has the Linux ecosystem gone through three fundamentally different answers to "what should it be" over its history?**

Every running Linux system has exactly one process with PID 1, and it is special in ways no other process is:

- It is the **first userspace process** — the kernel creates it directly rather than it being `fork()`ed from something else.
- It is the **ancestor of every other process** on the system, directly or indirectly — every process is created via `fork()`/`exec()` from some parent, and tracing that parent chain far enough always terminates at PID 1.
- It is the **reaper of orphaned processes** — when a process's original parent dies before it does, the orphan is re-parented to PID 1, whose job includes eventually `wait()`-ing on it so it doesn't linger as a zombie forever ([§34](../Part5/Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md) covers the fork/exec/wait lifecycle and zombie/orphan states in full).
- If PID 1 itself dies, the **kernel panics** — there is no fallback, no automatic restart, because there is nothing left to restart it. This is a large part of why init systems are engineered conservatively: PID 1 is the one process on the entire machine that isn't allowed to have an unhandled crash.

Beyond just existing, PID 1 has historically also been the process responsible for **starting and supervising system services** — bringing up networking, mounting filesystems beyond root, starting daemons like SSH or a web server, and taking the system to a usable state. That combined responsibility — "be PID 1" plus "orchestrate every service on the box" — is where SysVinit, Upstart, and systemd diverge sharply, and where most of this section's content lives.

> 💡 **Tip:** Keep two questions separate throughout this section, because conflating them is the single most common source of confusion: (1) _"what process is PID 1?"_ — a narrow, structural question with one answer per running system — and (2) _"how does that process decide what services to start, in what order, and how to keep them running?"_ — a design question where SysVinit, Upstart, and systemd take genuinely different approaches, not just different syntax for the same idea.

## 2. SysVinit: The Historical Default

**SysVinit** (System V init) was the dominant Linux init system for roughly the first two decades of Linux's existence, inherited from the Unix System V lineage referenced in [§2](../Part1/Section-02-Part1-History-and-Evolution.md) (Part 1's history section). Its model is sequential, script-based, and organized around **runlevels**.

**Runlevels 0–6** each represent a distinct system state:

| Runlevel | Meaning                                                                                                            |
| -------- | ------------------------------------------------------------------------------------------------------------------ |
| 0        | Halt (shut down the system)                                                                                        |
| 1        | Single-user / rescue mode (minimal services, root shell, no networking)                                            |
| 2–5      | Multi-user modes — the specific meaning of 2–5 varies by distribution (Debian-family and RHEL-family diverge here) |
| 6        | Reboot                                                                                                             |

Each runlevel has a corresponding directory — conventionally `/etc/rc0.d/` through `/etc/rc6.d/` — full of **symlinks** pointing back into `/etc/init.d/`, where the actual per-service shell scripts live. A symlink name like `S20ssh` (Start, priority 20) or `K80ssh` (Kill, priority 80) tells SysVinit both _whether_ to start or stop that service when entering the runlevel and, via the numeric prefix, _what order_ to do it in relative to other services in the same directory.

**Why this was eventually seen as limiting:**

- **Strictly sequential startup.** Services start one at a time, in numeric-prefix order, waiting for each script to finish before starting the next — there is no concept of "these three services have no dependency on each other, start them in parallel." On a host with many services, boot time is the sum of every script's runtime, not the longest dependency chain.
- **Dependency ordering is manual and fragile.** The only mechanism for "start networking before SSH" is naming the SSH script's symlink with a higher numeric prefix than the networking script's — an implicit convention enforced by whoever wrote the number, not a declared, checkable dependency.
- **No built-in service supervision.** SysVinit's job ends once a service's start script exits successfully — if the actual daemon then crashes five minutes later, SysVinit has no mechanism to notice or restart it. Supervision, if it existed at all, had to be bolted on separately (`respawn` entries in `/etc/inittab` covered a narrow subset of cases).
- **Boilerplate per service.** Every service needs its own `/etc/init.d/` shell script reimplementing the same start/stop/status/restart logic — checking if the process is already running, handling PID files, parsing arguments like a mini command-line tool — which is a lot of repeated, error-prone shell scripting multiplied across every service on every distribution.

None of these were fatal on lightly loaded, single-purpose hosts from the era SysVinit was designed for — but as machines ran more services, and as boot-time and restart-reliability expectations rose, these limitations became the direct motivation for what came next.

## 3. Upstart: The Transitional, Event-Driven Step

**Upstart** was Ubuntu's answer to SysVinit's limitations, and it's best understood as a deliberate stepping stone rather than a long-term destination — it saw real production use (Ubuntu and, for a period, RHEL 6/Fedora used it as their default) but was ultimately superseded before it became the universal standard SysVinit once was.

Upstart's core idea was **event-driven** service management rather than SysVinit's strict sequential-script model: jobs (Upstart's term for managed services) could declare that they should start _in response to an event_ — "the filesystem is mounted," "networking is up," "this other job has started" — rather than being pinned to a fixed numeric position in a fixed sequence. This unlocked genuine **parallel startup**: jobs with no dependency relationship to each other could start at the same time instead of waiting in a single queue, and it added basic supervision — Upstart could notice a job's process had died and respawn it, something SysVinit never did natively.

⚠️ **Verify current source:** Which specific distributions shipped Upstart as default, and for which release ranges, is a historical detail worth confirming against current documentation if it matters for a specific audit — this section covers Upstart's architectural role, not a precise version/release timeline.

Upstart is mostly historical at this point — it does not warrant deep investment in a modern operational knowledge base, but it matters for two reasons worth retaining: it proved that event-driven, parallel service startup was both possible and valuable on Linux, and its existence as a _second_ serious contender (alongside systemd) is part of why the eventual convergence on systemd was contentious rather than an uncontested default (7).

## 4. systemd: Conceptual Introduction Only

**systemd** is the init system on essentially every mainstream Linux distribution today. This section introduces it at a **conceptual level only** — full depth is reserved for **Part 9 ([§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)–[§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md))**, and deliberately isn't duplicated here:

- **Unit files** replace both SysVinit's shell scripts and Upstart's job definitions — declarative configuration files describing a service, its dependencies, and how to start/stop/restart it, rather than imperative shell logic (full syntax: [§67](../Part9/Section-67-Part9-Writing-Custom-Systemd-Unit-Files.md)).
- **Targets** replace runlevels conceptually — named synchronization points (`multi-user.target`, `graphical.target`) that group units together, though targets are more flexible than the fixed 0–6 runlevel numbering (full depth: [§70](../Part9/Section-70-Part9-Runlevels-Targets-System-State-Transitions.md)).
- **Parallel, dependency-based startup** is systemd's default behavior, not an opt-in feature — it builds a dependency graph from declared unit relationships and starts everything it safely can at the same time, which is the direct architectural answer to SysVinit's strictly sequential model.
- **Built-in service supervision** — systemd tracks a service's process(es) via Linux cgroups ([§13](./Section-13-Part2-Init-Systems.md)'s later Part-13 coverage of cgroups goes deeper) and can automatically restart a crashed service per policy declared right in the unit file, without any separate supervisor tool.
- **journald** — tightly integrated structured logging ([§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md)), rather than services independently deciding how and where to log.

The full architecture — `systemctl` operational commands, writing custom unit files, `journalctl` in depth, systemd timers vs. cron, and target-based state transitions — is **Part 9, [§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)–[§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md)**, not here. Treat everything in this subsection as just enough vocabulary to compare systemd against SysVinit and Upstart in [§5](../Part1/Section-05-Part1-Major-Distribution-Families.md), not as operational competence.

## 5. Comparison Table

| Dimension             | SysVinit                                                         | Upstart                                             | systemd                                                                                                                              |
| --------------------- | ---------------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| Startup model         | Strictly sequential, numeric-ordered shell scripts               | Event-driven, allows parallel job starts            | Dependency-graph-based, parallel by default                                                                                          |
| Dependency handling   | Implicit, via symlink numeric prefixes                           | Explicit event declarations ("start on")            | Explicit declared dependencies (`Requires=`, `After=`, etc. — [§67](../Part9/Section-67-Part9-Writing-Custom-Systemd-Unit-Files.md)) |
| Service supervision   | None built in (manual/bolted-on at best)                         | Basic respawn-on-death support                      | Built in, cgroup-tracked, policy-configurable restart                                                                                |
| Logging integration   | None — each service logs however it chooses (commonly to syslog) | None built in beyond syslog                         | journald — structured, integrated by default ([§68](../Part9/Section-68-Part9-Journald-Centralized-Logging-Journalctl.md))           |
| Adoption status today | Legacy; occasionally found on older or minimalist systems        | Effectively retired; largely of historical interest | De facto standard on essentially all mainstream distributions                                                                        |

## 6. Hands-On: Identifying Which init System a Host Is Running

Auditing an unfamiliar fleet — inherited infrastructure, older hosts, third-party images — often starts with a basic question that isn't always obvious from the distribution name alone: _what is actually running as PID 1 on this box?_

### 6.1 `ps -p 1 -o comm=`

**Purpose:** Directly ask the running kernel what process is PID 1, by name — the ground-truth answer, independent of any configuration file that might be stale or misleading.

**Syntax:**

```bash
ps -p 1 -o comm=
```

**Key flags:**

| Flag       | Meaning                                                                                                                     |
| ---------- | --------------------------------------------------------------------------------------------------------------------------- |
| `-p 1`     | Select PID 1 specifically                                                                                                   |
| `-o comm=` | Output only the command name column, with the header suppressed (the trailing `=` on the column name suppresses the header) |

**Example usage and expected output:**

```bash
$ ps -p 1 -o comm=
systemd
```

On an older or minimalist system, this might instead print `init` — which is ambiguous on its own, because `init` is frequently a symlink rather than a distinct binary (see below).

**Production usage example:** During a fleet audit ahead of a planned migration or a security review, running `ps -p 1 -o comm=` (or the equivalent one-liner across a fleet via SSH/Ansible) is the fastest way to segment hosts into "modern systemd," "needs deeper investigation," and "confirmed legacy SysVinit" buckets before deciding which hosts need extra care during automation changes that assume systemd is present.

**Common errors:**

- Assuming the distribution name alone answers this question — some distributions historically supported multiple init systems, and container base images in particular often run _no_ full init system at all (PID 1 is frequently the containerized application itself, not an init system) — always check directly rather than inferring from the OS label.

**Troubleshooting:** If the output is `init` rather than a specific name, that alone doesn't confirm SysVinit — resolve what `init` actually points to with the next command.

### 6.2 `readlink /sbin/init`

**Purpose:** Resolve what `/sbin/init` — the kernel's conventional default PID 1 target — actually points to, since on modern distributions it is almost always a symlink rather than a standalone binary.

**Syntax:**

```bash
readlink /sbin/init
```

**Example usage and expected output:**

```bash
$ readlink /sbin/init
/lib/systemd/systemd
```

An older SysVinit host would instead show `/sbin/init` as a real, non-symlinked binary — `readlink` on a non-symlink file prints nothing and exits non-zero, which is itself informative (it signals "not a symlink," pointing toward a traditional init binary rather than systemd).

**Production usage example:** Combined with `ps -p 1 -o comm=`, this pair of commands gives a fast, scriptable, two-line fleet-audit check — `ps` confirms what's actually running right now, `readlink` confirms what the boot-time default is configured to point at, and a mismatch between the two (unusual, but possible after certain manual interventions) is itself a signal worth investigating further.

**Common errors:**

- Running this inside a container and concluding the host's init system from it — a container's `/sbin/init` (if present at all) reflects the container image's filesystem, not the underlying host kernel's actual PID 1, which is a namespacing distinction covered properly in Part 13's containers section.

**Troubleshooting:** If `readlink` reports the file doesn't exist at all, some minimal or container-oriented distributions don't ship a `/sbin/init` path by convention — check what the kernel was actually told to execute as init via `/proc/cmdline`'s `init=` parameter ([§12](./Section-12-Part2-Boot-Process.md) introduced kernel boot parameters) or fall back to `ps -p 1 -o comm=` as the authoritative source.

## 7. Production Relevance: Why This Migration Was So Contentious

The SysVinit → systemd transition is one of the most contentious ecosystem changes in Linux's history, and it's worth understanding _why_, not just _that_ it happened — it's a concrete instance of the uneven-ecosystem-rollout pattern [§2](../Part1/Section-02-Part1-History-and-Evolution.md) raised at a general level: fundamental changes in an open, decentralized ecosystem don't roll out uniformly or instantly, and adoption friction is often as much about scope and philosophy as about technical merit.

A few concrete reasons the transition generated real, sustained pushback:

- **Scope, not just speed.** systemd wasn't positioned as "a faster init system with the same job as SysVinit" — it absorbed logging (journald), device management integration, time synchronization, login/session management, and more, under one project umbrella. Critics argued this violated the traditional Unix philosophy ([§4](../Part1/Section-04-Part1-Linux-Philosophy-Design-Principles.md)) of small, single-purpose tools composed together, concentrating what used to be many independent, swappable components into one large, tightly integrated system.
- **Distribution-by-distribution adoption timelines varied significantly** — some distributions adopted early, some held out for years, and a small number of projects exist specifically as systemd-free alternatives to this day. This is the uneven-rollout pattern in direct, visible action: a change with strong technical arguments on one side still took years to become near-universal, because ecosystem-wide consensus in open, decentralized software doesn't arrive on anyone's schedule.
- **Operational muscle memory had to be relearned.** Decades of SysVinit-era tooling, scripts, and administrator habits (`/etc/init.d/servicename start`, runlevel-based automation) needed updating for a genuinely different model — not a drop-in syntax change, which raised the real migration cost for large existing fleets.

Despite the controversy, the ecosystem did largely converge on systemd — parallel dependency-based startup, built-in supervision, and integrated logging solved real, widely-felt operational pain points that neither SysVinit nor Upstart fully addressed, and a critical mass of distributions, tooling, and documentation eventually made systemd the practical default even for administrators who preferred the older model philosophically.

## 8. Common Misconceptions

1. **"systemd is 'just' a faster init system."** This understates it considerably, and understanding _why_ the misconception matters is part of understanding the controversy in 7 — systemd is a broader system-management suite that happens to include an init system as one component among several (journald, `systemd-networkd`, `timedatectl`, login/session management, and more). The scope itself — not just implementation quality — is what much of the debate has actually been about.
2. **"Upstart and systemd are basically the same idea, just different projects."** They're architecturally distinct, not two implementations of one idea. Upstart is event-driven around jobs reacting to discrete events; systemd is built around an explicit, declared dependency graph between units, with parallel startup as a structural property of resolving that graph rather than a reaction to individual events. Treating them as interchangeable obscures why the ecosystem ultimately settled on one over the other.
3. **"Every Linux system today runs systemd."** True for the overwhelming majority of mainstream server distributions, but not universal — some distributions deliberately avoid it, embedded and minimal systems sometimes use lighter alternatives, and containers frequently run with no full init system at all (6). This section's hands-on check (6) exists precisely because this can't be safely assumed for an unfamiliar host.
4. **"Runlevels and targets are just renamed versions of the same thing."** They're related in intent (both represent named system states) but not equivalent in mechanism — runlevels are a fixed, numbered 0–6 scheme with implicit script-ordering; targets are a more flexible, named, dependency-graph-integrated concept that can express relationships runlevels can't (full comparison: [§70](../Part9/Section-70-Part9-Runlevels-Targets-System-State-Transitions.md)).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What is PID 1, and why does every Linux system need exactly one?"_
**Model answer:** PID 1 is the first userspace process the kernel starts directly after boot completes ([§12](./Section-12-Part2-Boot-Process.md)) — it isn't `fork()`ed from anything else. It's the ancestor of every other process on the system, it's responsible for reaping orphaned processes that get re-parented to it, and historically it's also been responsible for starting and supervising system services. A system needs exactly one because process ancestry and orphan-reaping only make sense with a single root of the process tree — and if PID 1 itself dies, there's nothing left to restart it, so the kernel panics rather than continuing.
_What the interviewer is probing for:_ Whether the candidate understands PID 1's structural role (process tree, orphan reaping) as distinct from just "it starts services" — many candidates only know the second half.

**🎯 Intermediate:** _"What specifically was limiting about SysVinit that motivated Upstart and later systemd?"_
**Model answer:** SysVinit's runlevel scripts start strictly sequentially in numeric-prefix order, so boot time is the sum of every script's runtime rather than the longest dependency chain — there's no parallel startup. Dependency ordering is implicit and fragile, expressed only through symlink numbering rather than declared relationships. It has no built-in service supervision, so a service that starts successfully but later crashes just stays down unless something else notices. And every service needs its own boilerplate-heavy shell script reimplementing start/stop/status logic. Upstart addressed the first two with event-driven parallel starts and basic respawn support; systemd went further with a full dependency graph, built-in cgroup-based supervision, and declarative unit files instead of shell scripts.
_What the interviewer is probing for:_ Concrete, specific limitations rather than a vague "SysVinit was old and slow" — and correctly attributing which successor solved which specific problem.

**🎯 Senior:** _"Why did the ecosystem largely converge on systemd despite the controversy around it?"_
**Model answer:** The controversy was real and largely about scope — systemd absorbed logging, device management, time sync, and session management into one project, which a lot of the community saw as violating the traditional small-tools-composed-together Unix philosophy. But convergence happened anyway because systemd solved real, widely felt operational pain: parallel dependency-based startup meaningfully cut boot times on service-heavy hosts, built-in cgroup-based supervision replaced ad-hoc or third-party process-supervision tooling that admins were bolting onto SysVinit and Upstart anyway, and integrated structured logging via journald addressed real gaps in how services logged inconsistently before. Once enough major distributions adopted it as default, the tooling, documentation, and operational ecosystem around it reached critical mass, which made staying on SysVinit or Upstart an increasingly high-friction minority choice even for administrators who preferred the philosophical stance behind the older model. It's a good example of a technically-motivated change winning out over time despite non-uniform, contentious adoption — not because the debate was resolved, but because the operational value proposition outweighed the philosophical objection for most of the ecosystem.
_What the interviewer is probing for:_ Ability to separate the technical merits from the philosophical objections, and to explain _ecosystem_ convergence dynamics rather than just listing systemd's features.

**🎯 Architect:** _"You've inherited a fleet with a mix of very old and fairly recent hosts, and you don't yet know which init systems are actually running where. How do you approach the audit and the eventual migration risk?"_
**Model answer:** I wouldn't trust the distribution label or version number alone — I'd run the direct check from 6 (`ps -p 1 -o comm=`, cross-checked with `readlink /sbin/init`) across the fleet via whatever orchestration tool is available, since that's ground truth from the running kernel rather than an assumption. I'd bucket hosts into systemd, confirmed-legacy SysVinit/Upstart, and containers-with-no-full-init (which need a different mental model entirely, since PID 1 there is often the application itself). For any host still on SysVinit or Upstart, I'd treat it as carrying real migration risk beyond just "old syntax" — service-supervision behavior, logging integration, and boot-ordering assumptions baked into existing automation may not translate directly, so I'd want an inventory of exactly what init-system-specific behavior current tooling depends on before touching it, rather than assuming a systemd unit file is a drop-in replacement for an init.d script. I'd also flag that a full remediation plan needs Part 9's systemd depth (unit files, targets, journald) applied per-service, not just "install systemd and move on."
_What the interviewer is probing for:_ Fleet-scale audit discipline, correctly distrusting assumptions in favor of ground-truth checks, and recognizing that init-system migration risk extends beyond syntax into supervision and logging behavior.

## 10. Key Takeaways

- PID 1 is structurally unique — first userspace process, ancestor of every process, reaper of orphans, and a process whose crash panics the kernel rather than being recoverable.
- SysVinit's model — sequential runlevel scripts under `/etc/init.d/` — was limited by strictly sequential startup, implicit/fragile dependency ordering, no built-in supervision, and per-service script boilerplate.
- Upstart was a genuine but ultimately transitional event-driven step — parallel starts and basic respawn support — largely historical today, but relevant to why the eventual systemd convergence was contested rather than an uncontested default.
- systemd (near-universal today) replaces shell scripts with declarative unit files, runlevels with targets, and adds dependency-graph-based parallel startup plus built-in cgroup-tracked supervision and integrated journald logging — but this section is deliberately shallow on internals; full depth is Part 9 ([§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)–[§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md)).
- `ps -p 1 -o comm=` and `readlink /sbin/init` are the fast, ground-truth way to identify a host's actual init system during a fleet audit — never assume from the distro label alone, especially for containers.
- The SysVinit→systemd transition is a concrete case study in [§2](../Part1/Section-02-Part1-History-and-Evolution.md)'s uneven-ecosystem-rollout pattern: strong technical merit still took years to become near-universal because of legitimate scope/philosophy objections and real migration cost.

## 11. Related Concepts & What's Next

This section is the direct continuation of [§12](./Section-12-Part2-Boot-Process.md)'s PID 1 handoff and depends on [§34](../Part5/Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md)'s fork/exec/wait process lifecycle (Part 5) for the orphan-reaping detail. It's a concrete instance of the uneven, contentious ecosystem-change pattern [§2](../Part1/Section-02-Part1-History-and-Evolution.md) introduced generally, and echoes the small-composable-tools Unix philosophy from [§4](../Part1/Section-04-Part1-Linux-Philosophy-Design-Principles.md) that much of the systemd scope debate hinges on. [§14](./Section-14-Part2-Kernel-Modules.md) (next) moves to kernel modules — `lsmod`, `modprobe`, `insmod` — a different, more mechanical corner of kernel-adjacent administration. The full systemd architecture only briefly sketched here — unit file syntax, `systemctl`, `journalctl` in depth, timers vs. cron, targets and state transitions — is Part 9, [§65](../Part9/Section-65-Part9-Systemd-Architecture-Units-Targets-Dependencies.md)–[§72](../Part9/Section-72-Part9-Time-Synchronization-Chrony-Ntpd-Timedatectl.md), and should be treated as this section's required follow-up before any hands-on systemd administration work.

**Next Section:** [§14](./Section-14-Part2-Kernel-Modules.md) — `Section-14-Part2-Kernel-Modules.md`
