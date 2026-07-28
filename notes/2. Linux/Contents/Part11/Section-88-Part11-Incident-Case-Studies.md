# Section 88 (Part 11): Incident Case Studies (Disk Full, Memory Leak, Fork Bomb, Network Saturation, Zombie Apocalypse)

## 1. Overview: Methodology Applied to Five Concrete Scenarios

§87 built the structured troubleshooting method — USE, top-down/bottom-up, hypothesis-driven testing, runbooks. This section, the last of Part 11, applies that method to five worked incident case studies drawn directly from the resource areas §81–§86 covered. Each follows the same consistent structure: **Symptom → Diagnostic steps → Root cause → Fix → Prevention** — deliberately mirroring §87's discipline rather than presenting these as isolated war stories.

## 2. Case Study 1: Disk Full

**Symptom:** A service crashes, hangs, or starts throwing write errors. `df -h` shows a filesystem at or near 100% used.

**Diagnostic steps:**

1. Confirm the actual condition first — `df -h` (§83) to see which filesystem is full, not just that "disk space" is a vague concern.
2. Find what's consuming the space — `du -sh /*` (or scoped into the full filesystem's mount point) narrowing directory by directory, per §83's disk-analysis tooling, until the specific large consumer is identified. This is very often an unrotated or runaway log file, a forgotten large temp file, or a directory of accumulated artifacts (old backups, core dumps, container image layers) nobody's been pruning.
3. **The deleted-but-open-file gotcha** (§83's key disk-analysis misconception): if `du` accounts for less space than `df` reports as used, the difference is very often a file that's been deleted but is still held open by a running process — `rm` unlinks the directory entry, but the underlying disk blocks aren't freed until every file descriptor referencing the inode is closed, so a process that keeps writing to a "deleted" log file keeps consuming space `du` can no longer see by walking the directory tree. `lsof +L1` (or `lsof | grep deleted`) surfaces exactly this case — open file descriptors pointing at unlinked inodes, with their still-growing size visible.

**Root cause:** Commonly one of: a log file that grew unbounded because rotation (§85) was never configured or its `postrotate` hook was broken, an application writing temp/cache data with no cleanup policy, or the deleted-but-open-file case above where a process kept a rotated-away or manually deleted file open and kept writing to it.

**Fix:** Free space immediately by removing or truncating the actual offender — if it's a deleted-but-open file, the space only returns once the process holding it is restarted or told to reopen/truncate its output (the same reopen-the-descriptor mechanic §85's `postrotate` discussion covered in detail), not merely by re-deleting something that's already unlinked.

**Prevention:** Proper `logrotate` configuration with a working `postrotate` hook (§85) for anything writing meaningful log volume, disk-usage monitoring with alerting well before 100% (not at it), and, for temp/cache data, an explicit retention or cleanup policy rather than relying on manual intervention after the fact.

## 3. Case Study 2: Memory Leak

**Symptom:** A process's resident memory (RSS) grows steadily and doesn't plateau over hours or days, eventually triggering the OOM Killer (§82) or degrading host performance for everything else running alongside it.

**Diagnostic steps:**

1. Confirm this is a genuine leak, not the normal cache-growth pattern §82 flagged as a common misconception — Linux aggressively uses free memory for page cache, and a `free -h` "available" figure that stays healthy while "used" climbs is often completely normal, not a leak.
2. Trend the specific process's RSS over time — repeated `ps -o pid,rss,cmd -p <pid>` samples, or reading `/proc/<pid>/status` (`VmRSS` field) at intervals, rather than a single point-in-time snapshot. A genuine leak shows RSS climbing monotonically with no plateau across a stable, repeating workload — if RSS grows in proportion to a genuinely growing workload (more connections, more cached application-level data that's expected to grow), that's not necessarily a leak either.
3. Distinguish the process's own private memory growth from shared/cache pages it maps — `/proc/<pid>/smaps` (or `smaps_rollup`) breaks RSS into private vs. shared components, which matters because shared library pages counted in RSS aren't the same as private heap growth pointing at an actual leak in the process's own allocations.

**Root cause:** Application-level — memory allocated and never freed (a genuine leak in unmanaged code), or references retained indefinitely in a managed-runtime application preventing garbage collection, or a connection/object pool with no upper bound that grows under sustained load and never shrinks back down.

**Fix (and the honest practical reality):** Actually fixing a memory leak requires application-level debugging — heap profiling, code review of allocation/retention patterns, tools specific to the application's language/runtime — which is beyond what OS-level tooling in this Part can diagnose past "confirm it's happening and to which process." Until that code fix ships, the practical operational mitigation is very often **restarting the affected process on a schedule** (a cron job, a systemd timer, or an orchestrator's scheduled rolling restart) frequent enough to stay ahead of the leak's growth rate before it triggers an OOM kill or degrades the host — a real, common, and reasonable stopgap, not a failure of ops discipline, as long as it's explicitly tracked as a workaround for a known application bug rather than treated as a permanent solution.

**Prevention:** Memory usage trend monitoring per service (not just host-wide `free` output) to catch a leak's growth curve well before it becomes an incident, and, longer-term, tracking the underlying application fix so the scheduled-restart mitigation can eventually be retired.

## 4. Case Study 3: Fork Bomb

**Symptom:** The system becomes unresponsive or extremely sluggish; new commands fail to start with errors like "resource temporarily unavailable" or "cannot fork"; the process count spikes rapidly.

**Diagnostic steps:**

1. A rapidly spiking process count (`ps aux | wc -l`, or a process-count metric on a monitoring dashboard) climbing far faster than any normal workload pattern is the characteristic signature — this is a case where the symptom itself (an exploding process count) is close to self-diagnosing, unlike the more investigative cases above.
2. Confirm via `ps` or `top` that a large number of processes trace back to the same runaway parent or shell — the canonical fork bomb (`:(){ :|:& };:` is the commonly cited shell one-liner example — its exact syntax isn't the important part; what matters is that it's a function that recursively forks and backgrounds copies of itself with no termination condition) rapidly exhausts available process slots by forking without bound.

**Root cause:** A process (malicious, or far more commonly an accidental bug — a recursive script or a retry loop that forks on each iteration without any bound) forking faster than the system can be reasoned about, consuming process table entries and approaching `pid_max`, and starving every other process on the host of the ability to fork new children at all — including the shell/tools an administrator would need to intervene.

**Fix:** Once the process table is already saturated, remediation is often difficult specifically because the tools needed to kill the offending processes may themselves be unable to fork — this is part of why fork bombs are disproportionately disruptive relative to how simple they are to write. Killing the responsible parent/session (where still possible) or, in a severe case, rebooting the host, are the practical recovery paths.

**Prevention — the concrete, real defensive control:** resource limits that cap how many processes a single user or service can create, enforced **before** a runaway fork loop can exhaust the whole system:

- **`ulimit -u <N>`** — a per-user process count ceiling, set via `/etc/security/limits.conf` (PAM-enforced, §32 (Part 4) covers PAM) or a shell session's `ulimit -u` — once a user hits this ceiling, further `fork()` calls fail for that user specifically, containing the damage rather than letting it exhaust the entire system's process table.
- **systemd's `TasksMax=`** — the modern, cgroup-backed equivalent scoped to a specific unit: a service's unit file can declare `TasksMax=<N>` to cap how many tasks (processes/threads) that unit's cgroup may ever contain, so a bug in one service can't fork its way into starving every other service and the host itself.

Both are genuinely worth having configured proactively on any production host or service that runs less-than-fully-trusted code or has any history of runaway-process bugs, rather than treated as a response to plan only after the first incident.

## 5. Case Study 4: Network Saturation

**Symptom:** A host or service becomes slow or unreachable under load — requests time out, connections are refused or hang, and the immediate assumption is often "the network is the problem."

**Diagnostic steps:**

1. Confirm whether this is actually bandwidth/link saturation or an application-layer bottleneck that merely presents the same way — `iftop`/`nload` for a live per-connection or per-interface bandwidth view, `sar -n DEV` for a historical trend, per §84's network-analysis tooling.
2. If interface utilization is genuinely near link capacity with a growing send/receive queue (the USE method's saturation dimension, §87, applied specifically to the network resource), that confirms real bandwidth saturation.
3. If interface utilization looks unremarkable but the symptom persists, redirect the investigation toward the application layer — connection pool exhaustion, a slow downstream dependency causing connections to pile up and hold sockets open, or CPU saturation on the host preventing timely packet processing despite the network itself being far from its capacity limit. This is exactly the top-down-then-bottom-up correction §87 described: a network-shaped symptom that turns out to trace back to a different resource entirely once actually measured rather than assumed.

**Root cause:** Genuinely two different families of root cause that present identically to an end user — either actual link/bandwidth saturation (a real traffic spike, a misbehaving process consuming bandwidth, an under-provisioned link) or an application-layer bottleneck (exhausted connection pools, a slow dependency, CPU contention preventing timely network processing) that only looks like a network problem from the outside.

**Fix:** Genuine bandwidth saturation calls for either provisioning more capacity, rate-limiting or deprioritizing the consuming traffic, or addressing whatever caused an unexpected traffic spike. An application-layer bottleneck misdiagnosed as network trouble needs to be redirected to the actual resource — fixing a network link doesn't help if the real constraint is a connection pool size or a downstream dependency's latency.

**Prevention:** Baseline network utilization trending (§84's `sar` historical data) so a genuine saturation event is recognizable against a known-normal pattern rather than guessed at, and treating "looks like a network problem" as a hypothesis to verify (§87) rather than an assumed conclusion, given how often the true cause sits one layer up in the application.

## 6. Case Study 5: Zombie Apocalypse

**Symptom:** A large and growing number of processes in `Z` (zombie) state accumulate on a host, visible in `ps aux` output or a process-state breakdown, often without an obviously matching resource-usage symptom (zombies consume essentially no CPU or memory — §34, Part 5, covers why).

**Diagnostic steps:**

1. `ps -eo pid,ppid,state,cmd | grep ' Z '` (or equivalent) to enumerate zombie processes and, critically, their **parent PID (PPID)** column.
2. Confirm the pattern: a large number of zombies sharing the **same parent process** is the diagnostic signature of this specific incident type, as opposed to a handful of transient zombies that are a completely normal, harmless, momentary state (§34's zombie-lifecycle explanation covers why a zombie briefly existing between a child's exit and its parent's `wait()` call is expected and not itself a problem).

**Root cause:** A **parent process bug** — the parent is failing to call `wait()` (or `waitpid()`) on its terminated children, so each child that exits leaves behind a zombie entry (an exit status the kernel is required to keep around until the parent collects it) that never gets reaped, accumulating one zombie per unreaped child exit over the parent's lifetime. This directly ties back to §34's fork/exec/wait mechanics: a zombie is a process that has exited but whose entry persists specifically because nothing has called `wait()` on it yet, and a buggy parent that never calls `wait()` at all is why the count keeps climbing rather than staying transient.

**Fix — and why zombies can't be killed directly:** A zombie process has already exited — it has no running code, no memory, and no way to respond to any signal, including `SIGKILL`; there's nothing left running to kill. The only ways a zombie entry clears are the parent finally calling `wait()` on it, or the parent itself dying, in which case the zombie is re-parented to PID 1 (§13, Part 2, covered PID 1's role as the ultimate orphan-reaper), which does call `wait()` on it and cleans it up. So the actual fix is **fixing or restarting the buggy parent process**, not attempting to act on the zombies themselves — restarting the parent immediately clears every zombie it was failing to reap, since they all get re-parented to PID 1 and reaped as part of the parent's own exit.

**Prevention:** The durable fix is a code-level correction in the parent process — properly calling `wait()`/`waitpid()` on every child it forks, or using a signal handler for `SIGCHLD` to reap children as they exit rather than leaking zombie entries indefinitely. Operationally, monitoring for an unusually high or steadily climbing zombie count (distinct from the normal, transient baseline) catches this pattern before it accumulates far enough to threaten `pid_max`/process-table exhaustion in its own right — a large enough zombie apocalypse is, in the end, a variant of the same process-table-pressure risk the fork bomb case (4) covered, just caused by a reaping bug rather than a forking bug.

## 7. Hands-On: A Consolidated First-Response Checklist

**Purpose:** Bring the five case studies together into a single quick-triage sequence — the kind of checklist worth having ready before an on-call page, not derived fresh mid-incident.

```bash
# Disk full? (Case 1)
df -h | awk '$5+0 >= 90'
lsof +L1 2>/dev/null | head            # deleted-but-open files

# Memory leak? (Case 2)
ps -eo pid,rss,comm --sort=-rss | head -10
free -h

# Fork bomb? (Case 3)
ps aux | wc -l
ps -eo pid,ppid,cmd --sort=-pid | head -20

# Network saturation? (Case 4)
sar -n DEV 1 3
ss -s

# Zombie apocalypse? (Case 5)
ps -eo pid,ppid,state,cmd | grep ' Z '
```

**Expected output:** Each command targets the specific diagnostic signature its case study relies on — filesystems near capacity, top RSS consumers, an abnormal total process count, network device throughput/socket summary, and any zombie entries grouped by parent.

**Production usage example:** Running this whole block (or an equivalent scripted version) as the very first step of any "something's wrong with this host" page gives a fast read on which of these five well-understood failure modes (if any) is in play, before committing to a deeper, more time-consuming investigation down one specific path.

**Common errors:** Treating a match on one of these checks as automatically the whole story — a host can show early signs of more than one condition at once (memory pressure that's also driving swap-related disk I/O, for instance), so confirm root cause per §87's hypothesis-driven discipline rather than stopping at the first matching symptom.

**Troubleshooting:** If none of the five checks show anything abnormal but a symptom was still reported, fall back to the full USE sweep (§87) and consider that the cause may be at the application layer, outside what host-level resource checks alone can reveal.

## 8. Common Misconceptions

1. **"`du` and `df` disagreeing means one of the tools is broken."** §83's deleted-but-open-file gotcha, applied concretely in Case 1, is almost always the explanation — a discrepancy points at an open file descriptor to an unlinked inode, not a tooling bug.
2. **"Rising memory usage always means a leak."** Case 2's distinction — cache growth is normal and expected, a genuine leak shows unbounded RSS growth with no plateau under a stable workload — is the same misconception §82 raised generally, applied here to a specific worked scenario.
3. **"A network-shaped symptom always means a network problem."** Case 4 is the direct counterexample — plenty of network-presenting symptoms trace back to application-layer bottlenecks (connection pools, slow dependencies, CPU contention) that never actually saturate the link.
4. **"Zombies can be cleared by killing them."** A zombie has already exited and has no running code left to signal — Case 5's fix is restarting or fixing the parent that's failing to reap them, never attempting to act on the zombie processes directly.
5. **"Fork bombs only matter as a malicious attack vector."** Far more common in practice is an accidental bug — a recursive script or unbounded retry loop that forks per iteration — which is exactly why `ulimit -u`/`TasksMax=` (Case 3) are worth configuring proactively on ordinary production services, not just as a security control against intentional abuse.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"A disk shows 100% full in `df`, but `du` on the mounted filesystem only accounts for 60% of that space. What's going on?"_
**Model answer:** This is almost always a deleted-but-still-open file — a process deleted (or had rotated out from under it) a file it still has open, so the directory entry is gone (which is why `du`, which walks the directory tree, doesn't see it) but the underlying disk blocks aren't freed until every open file descriptor referencing that inode is closed. `lsof +L1` (or `lsof | grep deleted`) surfaces exactly this — an open descriptor pointing at an unlinked file, still consuming space. The fix is getting the holding process to close or reopen that descriptor, typically via a restart or a proper reopen signal.
_What the interviewer is probing for:_ Recognition of this specific, common gotcha rather than assuming a tooling malfunction.

**🎯 Intermediate:** _"You see a large, growing number of zombie processes on a host. Walk me through your diagnosis and fix."_
**Model answer:** I'd check `ps -eo pid,ppid,state,cmd` filtered to `Z` state and look at the PPID column — a large count of zombies sharing the same parent points squarely at that parent failing to call `wait()`/`waitpid()` on its exited children. Since a zombie has already exited and has no running code to signal, I can't kill the zombies directly — the fix is restarting (or ultimately code-fixing) the buggy parent process, which immediately clears every zombie it was leaking, since on the parent's exit they're re-parented to PID 1 and reaped there. Longer-term, the actual fix is correcting the parent's code to properly reap children, whether via explicit `wait()` calls or a `SIGCHLD` handler.
_What the interviewer is probing for:_ Correctly identifying the parent-process root cause and explicitly knowing zombies can't be acted on directly — a common gap.

**🎯 Senior:** _"A service's RSS has been climbing steadily for two days. How do you determine whether this is a leak worth escalating to engineering, versus something you can leave alone?"_
**Model answer:** First I'd rule out the normal-cache-growth misconception — check whether `free`'s "available" figure is staying healthy while "used" climbs, which would point at page cache rather than a leak. Then I'd trend the specific process's RSS over time via repeated `ps`/`/proc/<pid>/status` samples against a stable, repeating workload — if it climbs without ever plateauing even while load is flat, that's the leak signature. I'd also check `/proc/<pid>/smaps` to confirm the growth is in the process's own private memory rather than shared/mapped pages. If confirmed as a genuine leak, I'd escalate to engineering with the trend data, and in the meantime set up a scheduled restart of the affected process frequent enough to stay ahead of the OOM threshold — an accepted operational mitigation for a known application bug, tracked explicitly as a stopgap rather than a permanent fix, with the restart cadence tied to the measured growth rate.
_What the interviewer is probing for:_ Rigor in distinguishing cache from leak, and a realistic, non-hand-wavy mitigation plan rather than either ignoring it or claiming ops can fix an application bug directly.

**🎯 Architect:** _"After a fork bomb incident (accidental, from a buggy deployment script) took down a shared host, what changes do you make to prevent recurrence, and at what layer?"_
**Model answer:** I'd treat this as a resource-isolation gap, not just a one-off bug to patch in the script. Immediately, I'd add `TasksMax=` limits to the systemd units for any service that runs less-trusted or historically-buggy code, and `ulimit -u` limits via `/etc/security/limits.conf` for any shared multi-tenant user context, so that a future runaway fork loop hits a hard ceiling scoped to its own user/cgroup rather than exhausting the entire host's process table — which is exactly what made this incident disproportionately disruptive relative to how simple the triggering bug was. I'd also push for the script itself to be fixed with proper bounds on its retry/recursion logic, since defensive limits contain the blast radius but don't replace fixing the actual bug. At a broader architecture level, I'd reconsider whether that class of script should run with elevated concurrency/parallelism on a shared host at all versus in an isolated, resource-capped context (a container with its own cgroup limits) where a similar bug in the future can't affect co-located, unrelated services.
_What the interviewer is probing for:_ Thinking beyond the immediate incident to systemic resource-isolation controls, and correctly treating `ulimit`/`TasksMax=` as containment rather than a substitute for fixing the underlying bug.

## 10. Key Takeaways

- Every case study follows Symptom → Diagnostic steps → Root cause → Fix → Prevention, directly applying §87's structured methodology rather than ad-hoc investigation.
- **Disk full:** `df`+`du` to locate the consumer, watch for the deleted-but-open-file gotcha (§83) via `lsof`, prevent via `logrotate` (§85) and proactive disk monitoring.
- **Memory leak:** trend RSS over time and distinguish it from normal cache growth (§82); the real fix is application-level, with scheduled restarts as an honest, common operational stopgap in the meantime.
- **Fork bomb:** a spiking process count from runaway forking (accidental far more often than malicious); prevention is concrete — `ulimit -u` and systemd's `TasksMax=` cap the blast radius before the whole process table is exhausted.
- **Network saturation:** confirm actual bandwidth saturation via §84's tools before assuming it — a network-shaped symptom frequently traces back to an application-layer bottleneck instead.
- **Zombie apocalypse:** many `Z`-state processes sharing one parent means that parent isn't calling `wait()` (§34); zombies can't be killed directly since they have no running code — fixing or restarting the parent is the only real remedy.

## 11. Related Concepts & What's Next

This section is the applied capstone of Part 11 (§80–§88) — every case study here draws directly on §81–§86's diagnostic tools and §87's structured methodology, and the fork bomb and zombie cases tie back explicitly to §34's (Part 5) fork/exec/wait process lifecycle mechanics. With Part 11 complete, **Part 12 (§89, Security Hardening)** is next — starting with a recap of the Linux security model and threat landscape, moving into SSH hardening, Mandatory Access Control (SELinux/AppArmor), kernel `sysctl` security parameters, and auditing, building on this Part's operational troubleshooting foundation with a security-focused lens.

**Next Section:** §89 — `Section-89-Part12-Linux-Security-Model-Recap-Threat-Landscape.md`
