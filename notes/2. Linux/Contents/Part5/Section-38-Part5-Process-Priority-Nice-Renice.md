# Section 38 (Part 5): Process Priority: nice and renice

## 1. A Different Axis From §37

§37 covered where a process's output goes and whether it survives session exit — foreground, background, stopped, `nohup`'d, or inside a multiplexer. None of that touches a completely separate question the kernel's scheduler answers dozens of times a second on a busy host: **when two or more processes both want the CPU right now, which one gets it, and for how long?** That's process priority, and on Linux the primary lever an administrator has over it is **niceness**.

Part 2's kernel-fundamentals coverage (§8–§16) introduced the CPU scheduler conceptually — the kernel component responsible for deciding which runnable process gets the CPU at any given instant, and for how long, when there are more runnable processes than CPU cores to run them on. This section doesn't re-derive scheduler internals; it picks up exactly where that leaves off and covers the one knob most administrators actually touch: adjusting a process's scheduling weight via `nice` and `renice`.

> 💡 **Tip:** Niceness is a request, not a guarantee. It changes how much CPU time a process is favored or disfavored for relative to other runnable processes competing for the same CPU — it does nothing at all if the CPU isn't contended in the first place. Renicing a process on an otherwise-idle box changes nothing observable, because there's no competition for the scheduler to arbitrate.

## 2. The Niceness Scale: -20 to 19

Every process on Linux has a **niceness** value, an integer ranging from **-20 to 19**. The naming is famously counterintuitive on first encounter, and it's worth internalizing the mnemonic explicitly rather than just memorizing the direction:

- **A high niceness value means the process is being "nice" to everyone else** — it voluntarily accepts a smaller share of CPU time when the CPU is contended, yielding to other processes more readily. High niceness = low scheduling priority.
- **A low (more negative) niceness value means the process is being less nice** — it demands a larger share of CPU time relative to others, at their expense. Low (negative) niceness = high scheduling priority.

| Niceness | Scheduling priority | Behavior under contention                                           |
| -------- | ------------------- | ------------------------------------------------------------------- |
| -20      | Highest             | Gets the largest relative share of CPU time; least willing to yield |
| 0        | Default             | Standard scheduling weight, no adjustment                           |
| 19       | Lowest              | Gets the smallest relative share of CPU time; most willing to yield |

The mnemonic that sticks: **a "nicer" process is more considerate of its neighbors**, which in scheduling terms means it steps back and takes less CPU, not more. Every new process inherits niceness **0** by default unless explicitly launched otherwise — 0 is the baseline every other value is relative to, not a special "unset" state.

> ⚠️ **Warning:** Don't confuse niceness with the raw scheduling priority number the kernel actually uses internally. Niceness is the user-facing abstraction `nice`/`renice`/`ps`/`top` expose; the kernel's CFS/EEVDF scheduler (Part 2's §8–§16 territory) translates niceness into an internal scheduling weight that determines actual CPU-time proportions, and the relationship between adjacent niceness values isn't linear in wall-clock terms — the practical effect of nicing a process depends on what else is runnable at the same time, not on the niceness number alone.

## 3. `nice`: Launching a New Process With Adjusted Priority

**`nice`** launches a brand-new process with a specified niceness, decided at launch time — analogous to how §37's `nohup` decides `SIGHUP` disposition at launch rather than after the fact.

**Syntax:**

```bash
nice -n <adjustment> command [args...]
```

**Examples:**

```bash
# Launch a compression job at reduced priority (niceness 10)
$ nice -n 10 tar -czf backup.tar.gz /data

# Default adjustment if -n is omitted is +10
$ nice tar -czf backup.tar.gz /data
```

Without any argument, running a command under plain `nice` (no `-n`) applies a default adjustment of **+10** relative to the shell's current niceness — a sensible default for "run this but don't let it compete aggressively with everything else."

**Verifying the result:**

```bash
$ nice -n 10 sleep 300 &
[1] 7421
$ ps -o pid,ni,comm -p 7421
    PID  NI COMMAND
   7421  10 sleep
```

The `NI` column in `ps` (and the `PR`/`NI` columns in `top`) shows the effective niceness directly — always confirm rather than assuming the requested adjustment took effect, especially when the requested value pushes toward the negative end (4).

## 4. Who Can Set What: The Root/CAP_SYS_NICE Boundary

Niceness adjustment is **asymmetric by design**, and this is the single most commonly misunderstood part of the mechanism:

- **Any user can raise their own process's niceness** (move it toward 19, i.e., lower its own priority) — making your own process nicer to others requires no special privilege, because you're only ever giving up CPU share, never taking it from someone else without permission.
- **Only root (or a process holding the `CAP_SYS_NICE` capability) can lower a process's niceness** (move it toward -20, i.e., raise its priority above default) — because doing so lets that process claim a disproportionate share of CPU time at the expense of every other process on the box, which is a privileged action for the same reason arbitrary signal delivery to another user's process is (§36).
- A **non-root user also cannot renice their own already-niced-up process back down** past its original starting point — once you've made a process nicer (raised its niceness), you can continue raising it further, but you cannot reverse the adjustment below where you started without root, even though it's still your own process.

```bash
$ nice -n -5 some_command
nice: cannot set niceness: Permission denied
$ sudo nice -n -5 some_command
```

> ⚠️ **Warning:** This asymmetry is a genuine, deliberate security boundary, not an arbitrary inconvenience — it exists because unprivileged users demanding a disproportionate CPU share is precisely the kind of resource-hog behavior niceness is designed to constrain. Any request for elevated ("negative-niceness") process priority in production is a request worth scrutinizing the same way a `sudo` grant would be, not a default to hand out casually.

## 5. `renice`: Changing an Already-Running Process's Priority

**`renice`** adjusts niceness on a process that's already running, identified by PID (or, with the right flags, by user or process group) — the direct analog to how §37's `disown` acts on an already-launched job rather than requiring foresight at launch time.

**Syntax:**

```bash
renice -n <niceness> -p <pid>
renice -n <niceness> -u <user>
renice -n <niceness> -g <pgid>
```

**Key flags:**

| Flag         | Meaning                                                                              |
| ------------ | ------------------------------------------------------------------------------------ |
| `-n <value>` | The absolute niceness value to set (not a relative adjustment, unlike `nice`'s `-n`) |
| `-p <pid>`   | Target a specific process by PID                                                     |
| `-u <user>`  | Target every process owned by a given user                                           |
| `-g <pgid>`  | Target every process in a given process group                                        |

**Examples:**

```bash
# Lower the priority of a runaway batch job already in progress
$ renice -n 15 -p 8842
8842 (process ID) old priority 0, new priority 15

# Raise priority (requires root) on a latency-sensitive daemon
$ sudo renice -n -5 -p 1203
1203 (process ID) old priority 0, new priority -5
```

**The critical distinction from `nice`:** `nice` sets niceness at process creation and has no effect on anything already running; `renice` operates entirely on the live process table and has no bearing on how future child processes it might spawn are niced (a child inherits the parent's niceness at the moment of `fork()`, not retroactively from a later `renice` on the parent — reniced children spawned afterward do pick up the new value, but existing ones don't move unless reniced separately).

> 💡 **Tip:** `renice` targeting a multi-threaded process affects the whole thread group's scheduling weight as seen by `-p`, but on Linux, threads are themselves schedulable entities with their own TIDs — for fine-grained per-thread niceness control beyond what `renice -p` gives you by default, that's `/proc/[pid]/task/[tid]`-level territory, a level of granularity rarely needed outside specialized real-time or latency-sensitive tuning work.

## 6. `nice` Affects CPU Scheduling Weight, Not I/O Priority

A common and costly assumption: reducing a process's niceness also throttles its disk I/O. It doesn't. Niceness is purely a **CPU scheduling** concept — it changes how the scheduler (CFS historically, EEVDF on newer kernels — both covered conceptually under Part 2's §8–§16) weighs a process against others when handing out CPU time. It has **no effect on I/O scheduling** at all.

A heavily reniced-down (deprioritized) process can still saturate disk I/O and starve every other process's storage access, even while barely touching the CPU — CPU contention and I/O contention are separate resources with separate contention mechanisms, and treating `nice` as a general-purpose "be less disruptive" knob misses this entirely.

**`ionice`** is the analogous tool for I/O priority — conceptually parallel to `nice`/`renice` but operating on the kernel's I/O scheduler instead of the CPU scheduler, with its own scale (`idle`, `best-effort` with 0–7 sub-levels, `realtime`). It's a separate tool with separate mechanics, not covered in depth here since it sits outside this section's roadmap scope — but its existence is worth retaining precisely so a CPU-only mental model of `nice` doesn't get silently over-applied to I/O-heavy batch jobs.

```bash
# Analogous I/O deprioritization, conceptually parallel to nice -n
$ ionice -c 3 -p 8842
```

> ⚠️ **Warning:** Reniceing a backup or compression job down (raising its niceness) without also considering `ionice` is a common half-fix — the job stops hogging CPU but can still saturate disk throughput and cause the exact interactive-latency complaints the renice was meant to solve, because the actual bottleneck was I/O contention, not CPU contention, and `nice` never touched that axis at all.

## 7. Practical Use Case: Niceing a Backup or Batch Job

The canonical production scenario: a backup job, a large compression task, or a batch data-processing script needs to run on a host that also serves interactive or latency-sensitive workloads, and it shouldn't be allowed to starve them of CPU time during the run.

```bash
# Launch a compression job that yields CPU readily to everything else
$ nice -n 19 gzip -9 large_dataset.csv &

# Or, if it's already running and starting to cause visible contention:
$ renice -n 19 -p $(pgrep -f large_dataset)
```

Niceness 19 (or close to it) is the right choice for genuinely deferrable, non-time-sensitive batch work — it tells the scheduler "run this only with CPU cycles nothing else currently wants," which is exactly the behavior a backup job should have relative to, say, a web server handling live requests on the same host. This is a load-average-diagnosis-adjacent concern in practice — Part 11's performance coverage (§80–§88) is where you'd confirm, via load average and per-process CPU usage, whether a host's interactive latency complaints are actually attributable to CPU contention from an un-niced batch job in the first place, before reaching for `renice` as the fix.

> 💡 **Tip:** Niceing a job down is a mitigation for _contention_, not a substitute for capacity planning. If a host is consistently CPU-saturated even with batch work correctly deprioritized, the right answer is more capacity or workload separation, not squeezing every batch job down to niceness 19 and hoping it's enough — §80–§88 (Part 11) covers recognizing that distinction from load-average and CPU-utilization data.

## 8. Common Misconceptions

1. **"Lower niceness number means lower priority."** Backwards — lower (more negative) niceness means _higher_ scheduling priority; the naming reflects how "nice" the process is being to its neighbors, not the priority magnitude directly (2).
2. **"Any user can set any niceness on their own processes."** Any user can raise their own process's niceness freely, but lowering niceness (raising priority) requires root or `CAP_SYS_NICE`, and even reversing a self-imposed niceness increase back down requires the same privilege (4).
3. **"`nice`/`renice` control I/O priority too."** They control CPU scheduling weight only; I/O priority is a separate mechanism entirely, addressed by `ionice` (6), and a process reniced for CPU can still fully saturate disk I/O.
4. **"Renicing a process on an idle system will make it noticeably 'faster.'"** Niceness only matters under contention — a process with no competition for the CPU runs at essentially the same effective speed regardless of its niceness value, since there's nothing for the scheduler to arbitrate between (1).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What does it mean for a process to have niceness 19 versus niceness -20?"_
**Model answer:** Niceness ranges from -20 to 19. A niceness of 19 means the process is being maximally "nice" to other processes — it yields CPU time readily and gets the smallest relative share when the CPU is contended, i.e., lowest scheduling priority. A niceness of -20 means the opposite — the process demands the largest relative share of CPU time and is least willing to yield, i.e., highest scheduling priority. The naming is about how considerate the process is being toward its neighbors, not a direct "bigger number equals more priority" scale, which is the opposite of how most people initially guess it works.
_What the interviewer is probing for:_ Correctly internalizing the inverted relationship rather than getting the direction backwards under pressure.

**🎯 Intermediate:** _"What's the difference between using `nice` and using `renice`, and when would you reach for each?"_
**Model answer:** `nice` sets niceness at the moment a new process is launched — it's a launch-time decision, like `nohup` from §37, and has no effect on anything already running. `renice` changes the niceness of a process that's already running, identified by PID, user, or process group — it's the retroactive tool, analogous to `disown`. I'd reach for `nice` when I know ahead of time that a job I'm about to start (a backup, a compression task) shouldn't compete aggressively for CPU. I'd reach for `renice` when I discover an already-running process is causing CPU contention I didn't originally plan for — say, during an incident where load average is elevated and I've identified a specific runaway process I want to deprioritize without killing it outright.
_What the interviewer is probing for:_ Clear mapping of launch-time vs. already-running tooling, and recognizing the parallel to the nohup/disown pattern from job control.

**🎯 Senior:** _"A junior engineer renices a disk-heavy backup job down to niceness 19 to stop it from impacting an interactive service, but users are still complaining about latency during the backup window. What's likely wrong?"_
**Model answer:** Niceness only affects CPU scheduling weight — it has no bearing on I/O priority at all. If the backup job is disk-I/O-heavy rather than CPU-heavy, deprioritizing it with `nice`/`renice` does essentially nothing to reduce the actual bottleneck, because the contention was never on the CPU scheduler in the first place. I'd check per-process CPU usage and load average (Part 11, §80–§88) to confirm whether CPU is even the constrained resource during the backup window, and separately check disk I/O utilization (`iostat`/`iotop`, also Part 11) to see if the backup job is saturating storage throughput instead. If it's I/O-bound, the correct tool is `ionice`, not a lower niceness — and possibly both, if the job is genuinely heavy on both resources. This is a classic case of applying the right-shaped tool to the wrong resource because the two axes (CPU scheduling vs. I/O scheduling) look superficially similar but are mechanically unrelated.
_What the interviewer is probing for:_ Not conflating CPU and I/O contention, and knowing to diagnose with actual utilization data rather than assuming a nice/renice fix addresses every "this job is disruptive" complaint.

**🎯 Architect:** _"You're designing a policy for how batch and interactive workloads should coexist on shared hosts in a fleet. Where does nice/renice fit, and where does it stop being sufficient?"_
**Model answer:** `nice`/`renice` are a fine, cheap first line of defense for CPU-scheduling coexistence on a single host — niceing batch jobs down (toward 19) so the CFS/EEVDF scheduler (Part 2, §8–§16) favors interactive workloads under contention costs nothing to implement and requires no infrastructure change. But it's a soft, best-effort mechanism operating on one resource axis only: it doesn't touch I/O contention (that's `ionice`'s job), it doesn't provide hard isolation or guaranteed resource shares (that's cgroup-based resource limiting territory, adjacent to the containers material in Part 13), and it does nothing at all if the host is capacity-constrained overall rather than merely contended at a given moment — reniceing everything down doesn't create CPU that doesn't exist. For a fleet-wide policy I'd treat nice/renice as tactical, incident-response-friendly tooling — quickly deprioritizing an identified runaway process — and push toward cgroup CPU shares/quotas or dedicated capacity separation as the structural fix for workloads that are chronically incompatible on the same host, informed by the load-average and utilization diagnosis methodology in Part 11 (§80–§88) rather than reflexively reaching for renice as a permanent architecture.
_What the interviewer is probing for:_ Recognizing nice/renice as a lightweight, single-axis, best-effort tool rather than a substitute for real resource isolation or capacity planning, and connecting it correctly to the broader performance-diagnosis toolchain.

## 10. Key Takeaways

- Niceness ranges from -20 (highest scheduling priority) to 19 (lowest scheduling priority), with 0 as the default — the naming reflects how considerate a process is toward others' CPU share, which is the inverse of what "higher number, higher priority" intuition suggests.
- `nice` sets niceness at process launch time; `renice` changes it on an already-running process identified by PID, user, or group — the same launch-time-vs-retroactive split §37 established between `nohup` and `disown`.
- Any user can raise their own process's niceness (lower its priority); only root or `CAP_SYS_NICE` can lower niceness (raise priority) — including reversing a user's own prior niceness increase, which is a deliberate privilege boundary against unprivileged resource hogging.
- Niceness affects CPU scheduling weight only, under the kernel's scheduler (Part 2's §8–§16 territory) — it has no effect on I/O priority, which is `ionice`'s separate, analogous domain.
- The practical use case is deprioritizing deferrable batch work (backups, compression, bulk processing) so it yields CPU to interactive or latency-sensitive workloads under contention — but it's only relevant when the CPU is actually contended, and it's a soft, single-resource mechanism, not a substitute for I/O-aware tuning, cgroup-based isolation, or genuine capacity planning.
- Diagnosing whether CPU contention is actually the cause of a latency complaint — rather than assuming and applying `renice` reflexively — belongs to Part 11's performance methodology (§80–§88), particularly load average and per-process CPU analysis.

## 11. Related Concepts & What's Next

This section is a direct continuation of §37's launch-time-vs-retroactive pattern (`nice`/`renice` mirroring `nohup`/`disown`), applied to a different axis of process management — CPU scheduling weight rather than session survival. It depends on Part 2's kernel-scheduler conceptual coverage (§8–§16) for what the scheduler is actually doing with the niceness value it's handed, and it connects forward to Part 11's performance-diagnosis material (§80–§88), where load average and CPU-utilization analysis determine whether reniceing a process is even the correct response to an observed latency problem. §39 (next) moves to task scheduling — `cron`, `at`, and systemd timers — shifting from "how much CPU priority does a running process get" to "when should a process run in the first place."

**Next Section:** §39 — `Section-39-Part5-Scheduling-Tasks-Cron-At-Systemd-Timers.md`
