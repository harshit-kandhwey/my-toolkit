# Section 34 (Part 5): Viewing Processes: ps, top, htop, /proc/[pid]

## 1. Four Tools, One Underlying Data Source

[§33](./Section-33-Part5-What-A-Process-Is.md) established what a process actually is — PID, PPID, state, and the kernel's process table backing all of it — and closed by noting that `ps`, `top`, and direct `/proc/[pid]` reads are just different windows onto that same data ([§33](./Section-33-Part5-What-A-Process-Is.md)'s 6). This section is the hands-on companion: how to actually drive those tools in day-to-day administration and troubleshooting.

All four tools covered here — `ps`, `top`, `htop`, and raw `/proc/[pid]` files — read from the same source. None of them has privileged kernel access the others lack; they differ in **presentation** (static snapshot vs. live-updating vs. raw text), **interactivity** (read-only vs. sort/kill/renice in place), and **availability** (pre-installed everywhere vs. an optional package). Picking the right one is almost entirely about matching the tool to the task, not about one being objectively "better."

> 💡 **Tip:** If you only remember one fact from this section, make it this: when `ps`, `top`, or `htop` show something confusing or contradictory, `/proc/[pid]/status` is always the tiebreaker — it's the least-processed view of what the kernel actually has recorded for that PID.

## 2. `ps`: Option Styles and Why `ps aux` and `ps -ef` Both "Work"

`ps` is one of the few commands where the **same flag can mean different things** depending on which option-parsing convention it's read under, because `ps` historically supports three overlapping styles simultaneously:

| Style          | Convention                                          | Example        |
| -------------- | --------------------------------------------------- | -------------- |
| **UNIX/POSIX** | Options prefixed with a single dash, can be grouped | `ps -ef`       |
| **BSD**        | Options with **no** leading dash                    | `ps aux`       |
| **GNU long**   | Double-dash, word-style options                     | `ps --pid 123` |

This is why `ps aux` (no dash — BSD style) and `ps -ef` (dash — UNIX style) both run successfully and both produce a "list every process" table, yet they are **not** the same command syntactically, and mixing styles carelessly (`ps -aux`, dash plus BSD-style letters) can silently change meaning rather than erroring — `-a` in UNIX style and `a` in BSD style don't always mean the same thing, and `ps` resolves the ambiguity using rules most administrators never consciously learn, they just memorize the two idiomatic incantations.

**The two commands compared:**

```bash
ps aux
```

```text
$ ps aux
USER   PID %CPU %MEM    VSZ   RSS TTY   STAT START   TIME COMMAND
root     1  0.0  0.1  22528  9600 ?     Ss   08:01   0:03 /sbin/init
www      842 0.2  1.4 812000 58200 ?    Sl   08:02   1:22 nginx: worker
```

```bash
ps -ef
```

```text
$ ps -ef
UID    PID  PPID  C STIME TTY    TIME CMD
root     1     0  0 08:01 ?  00:00:03 /sbin/init
www    842     1  0 08:02 ?  00:01:22 nginx: worker
```

Both show every process on the system, but the **columns differ**: `aux` (BSD style) leads with `%CPU`/`%MEM` and memory sizes — better for a resource-usage sweep — while `-ef` (UNIX style) leads with `PPID` — better when the process tree relationship ([§33](./Section-33-Part5-What-A-Process-Is.md)'s 3) is what you're chasing. Neither is more "correct"; pick based on which column you need first.

> ⚠️ **Warning:** Don't memorize `ps aux` and `ps -ef` as arbitrary magic strings without understanding they're two different option grammars — the moment you need a flag combination neither idiom covers (say, a custom `-o` format string plus a specific sort), reaching for a random third flag under the wrong style guesses wrong more often than it should.

## 3. `ps -o`: Custom Output Format

The most durable `ps` skill for real troubleshooting isn't memorizing `aux` or `-ef` — it's the `-o` format specifier, which lets you request exactly the columns needed and nothing else, in whatever order is useful:

```bash
ps -eo pid,ppid,user,stat,pcpu,pmem,etime,cmd --sort=-pcpu
```

**Purpose:** List every process (`-e`) with a hand-picked column set (`-o`), sorted by CPU usage descending — the single most common ad-hoc query when a host feels slow and the question is "what's actually using the CPU right now."

**Key flags and format specifiers:**

| Specifier      | Meaning                                                                                                                                                                       |
| -------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `pid`, `ppid`  | Process and parent PID ([§33](./Section-33-Part5-What-A-Process-Is.md)'s 2, 3)                                                                                                |
| `stat`         | Process state letter, same encoding as [§33](./Section-33-Part5-What-A-Process-Is.md)'s 4 (`R`/`S`/`D`/`T`/`Z`)                                                               |
| `pcpu`, `pmem` | Percent CPU and percent memory currently in use                                                                                                                               |
| `etime`        | Elapsed real time since the process started — useful for spotting an unexpectedly long-lived or unexpectedly short-lived process                                              |
| `lstart`       | Full wall-clock start timestamp — what [§33](./Section-33-Part5-What-A-Process-Is.md)'s 2 recommended pairing with a PID for reliable correlation across `pid_max` wraparound |
| `cmd`/`args`   | Full command line, including arguments (`comm` gives just the bare executable name instead)                                                                                   |
| `--sort=-pcpu` | Sort descending by CPU% (drop the `-` for ascending); any column name works as a sort key                                                                                     |

**Production usage example:** `ps -eo pid,ppid,user,stat,pcpu,pmem,etime,cmd --sort=-pcpu | head -20` is a near-universal first command during an on-call "the box is slow" page — before reaching for `top` at all, this gives an immediately grep-able, scriptable snapshot that's easy to paste into an incident channel.

## 4. `ps` for Targeted Lookups

Beyond full-system listing, `ps` supports targeted queries that avoid scanning the entire process table by eye:

```bash
ps -p 1234                  # a specific PID
ps --ppid 1234              # all children of a specific parent
ps -C nginx                 # all processes matching a command name
pgrep -f "python.*worker"   # PIDs matching a pattern against the full command line
```

`pgrep` (and its counterpart `pkill`) deserve a specific mention here because they're frequently the fastest path from "I know roughly what this process is called" to "I have its PID" without eyeballing a full `ps` table — `pgrep -f` in particular matches against the entire command line, not just the executable name, which matters for distinguishing multiple instances of the same interpreter (several `python` workers with different script arguments, for instance).

## 5. `top`: The Live Interactive View

Where `ps` gives a single static snapshot, `top` refreshes continuously (every 3 seconds by default) and lets you sort and act on processes interactively without leaving the terminal.

**Reading the header:**

```text
top - 14:22:01 up 12 days,  3:41,  2 users,  load average: 2.15, 1.88, 1.02
Tasks: 187 total,   1 running, 185 sleeping,   0 stopped,   1 zombie
%Cpu(s): 22.3 us,  3.1 sy,  0.0 ni, 73.9 id,  0.5 wa,  0.0 hi,  0.2 si,  0.0 st
MiB Mem :  16034.0 total,   2140.5 free,   9821.3 used,   4072.2 buff/cache
MiB Swap:   2048.0 total,   2048.0 free,      0.0 used.   5610.8 avail Mem
```

- **Load average** (three numbers: 1-, 5-, 15-minute averages) — the count of processes runnable-or-uninterruptibly-waiting on average over each window; comparing the three numbers to each other shows whether load is rising, falling, or steady, and comparing the 1-minute figure to CPU core count is the classic first sanity check for "is this host actually overloaded."
- **Tasks** row breaks down process count by state, using the exact same letters [§33](./Section-33-Part5-What-A-Process-Is.md)'s 4 defined — a nonzero zombie count here is often the first visible clue of a reaping bug worth investigating per [§33](./Section-33-Part5-What-A-Process-Is.md)'s 7.
- **%Cpu(s)** breaks CPU time into categories: `us` (userspace), `sy` (kernel/system calls), `wa` (waiting on I/O — elevated `wa` alongside `D`-state processes in the task list corroborates [§33](./Section-33-Part5-What-A-Process-Is.md)'s I/O-stall diagnosis from its Warning), among others.

**Per-process columns worth knowing precisely:**

| Column          | Meaning                                                                                                                                                                                                                       |
| --------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `VIRT`          | Total virtual memory the process has mapped — includes memory it's reserved but may never actually touch, so a large `VIRT` alone is not evidence of a problem                                                                |
| `RES`           | Resident memory — pages actually held in physical RAM right now; the number most people mean when they informally say "memory usage"                                                                                          |
| `SHR`           | Shared memory — pages this process shares with others (loaded libraries, shared mappings); part of `RES` but double-counted across every process sharing it, so summing `RES` across all processes overstates true memory use |
| `%CPU` / `%MEM` | Same meaning as `ps`'s `pcpu`/`pmem` (3), just live-updating                                                                                                                                                                  |
| `S`             | Single-letter state column, same encoding as [§33](./Section-33-Part5-What-A-Process-Is.md)'s 4                                                                                                                               |

> ⚠️ **Warning:** Never sum `RES` across every row in `top` and treat it as total memory used — shared library pages (`SHR`) get counted once per process that maps them, so that sum systematically overcounts actual physical memory consumption. `free` (Part 11, [§82](../Part11/Section-82-Part11-Memory-Analysis.md)) gives the accurate system-wide figure.

**Interactive commands (pressed while `top` is running, not typed as shell arguments):**

| Key | Effect                                                                                                                                                          |
| --- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `P` | Sort by `%CPU` (default)                                                                                                                                        |
| `M` | Sort by `%MEM`                                                                                                                                                  |
| `T` | Sort by cumulative time                                                                                                                                         |
| `k` | Kill a process — prompts for PID, then signal (default `SIGTERM`; [§36](./Section-36-Part5-Signals.md) covers signal semantics in depth)                        |
| `r` | Renice a process — prompts for PID, then a new nice value ([§39](./Section-39-Part5-Scheduling-Tasks-Cron-At-Systemd-Timers.md) covers priority/`nice` in full) |
| `1` | Toggle per-CPU-core breakdown instead of an aggregate `%Cpu(s)` line                                                                                            |
| `u` | Filter the view to a specific user                                                                                                                              |
| `q` | Quit                                                                                                                                                            |

**Production usage example:** During a live incident, `top` sorted by `%MEM` (`M`) is frequently faster than composing a `ps -eo` sort command, precisely because it's live — a process leaking memory shows itself climbing in real time rather than requiring repeated re-runs of a static snapshot.

## 6. `htop`: The Friendlier Interactive Alternative

`htop` covers the same ground as `top` — live, interactive, sortable — with a materially nicer interface: color-coded per-core CPU/memory usage bars at the top, a **tree view** (`t` or `F5`) that shows parent/child relationships directly in the process list rather than requiring a separate `pstree` invocation ([§33](./Section-33-Part5-What-A-Process-Is.md)'s 3), mouse support for clicking to select and act on a process, and function-key shortcuts (`F6` to sort by any column via menu, `F9` to kill, `F7`/`F8` to renice) that are more discoverable than `top`'s single-letter prompts.

**Key difference from `top` worth internalizing:** `htop` is **not installed by default** on most minimal server images and distributions the way `ps` and `top` almost universally are — it's typically an extra package (`apt install htop` / `dnf install htop`). This has a direct operational consequence: on a fresh minimal server, a locked-down container, or a host where package installation is restricted or offline, `htop` may simply not be available, and falling back to `top` or `ps` isn't a downgrade in capability so much as a return to what's guaranteed to be present everywhere.

> 💡 **Tip:** Build the habit of being fully fluent in bare `ps`/`top` rather than treating `htop`'s friendlier interface as the primary tool — every production host guarantees `ps` and `top`; not every host guarantees `htop`. Use `htop` when it's available and convenient, but never let it become the only tool you know how to drive under pressure.

## 7. `/proc/[pid]`: The Lowest-Level Fallback

[§33](./Section-33-Part5-What-A-Process-Is.md)'s 6 established that `/proc/[pid]/status` and `/proc/[pid]/stat` are the same underlying data `ps` and `top` parse, exposed as plain text — this section applies that fact rather than re-deriving it ([§24](../Part3/Section-24-Part3-Proc-Sys-Virtual-Filesystems.md), covers `/proc` and `/sys` in general).

```bash
cat /proc/1234/status
```

**Purpose:** Read a specific process's state directly from the kernel's exposed view, bypassing `ps`/`top` entirely — the fallback of last resort when a tool's output looks wrong, when the host is too resource-starved to comfortably run an interactive tool, or when scripting needs a single field without parsing table output.

**Representative fields:**

```text
Name:   nginx
State:  S (sleeping)
Pid:    1234
PPid:   1
VmRSS:      58200 kB
Threads:    4
```

`Name`, `State`, `Pid`, and `PPid` map directly onto [§33](./Section-33-Part5-What-A-Process-Is.md)'s 2–4 concepts — same PID/PPID/state model, just read as text instead of through a formatting tool. `/proc/1234/stat` carries similar information in a compact, space-delimited single-line form intended for machine parsing rather than human reading — scripts favor `stat` for exactly that reason, while humans favor `status` for its labeled, one-field-per-line layout.

**Production usage example:** On a host so overloaded that spawning `top`'s own process competes noticeably for scarce resources, `cat /proc/[pid]/status` for a specific PID of interest is a lighter-weight way to check state without adding another resource-hungry process to an already-struggling system — it's a single `cat` against an already-open kernel data structure, not a tool that itself samples and formats the entire process table.

> 💡 **Tip:** `/proc/[pid]/status` is also the place to look when `ps`/`top` output looks internally inconsistent or when a value seems stale — since it's the least-processed source, discrepancies between it and a higher-level tool point at a bug or misunderstanding in how the tool's output is being read, not at the kernel's actual bookkeeping.

## 8. Comparison Table: Which Tool, When

| Situation                                                                           | Best tool                                                                                                                                                                                                               |
| ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Quick one-off snapshot, scriptable, pipeable to `grep`/`awk`                        | `ps` with `-o` custom format (3)                                                                                                                                                                                        |
| Need custom sort/columns for an incident paste                                      | `ps -eo ... --sort=`                                                                                                                                                                                                    |
| Live-updating view, want to interactively kill/renice, `htop` unavailable           | `top` (5)                                                                                                                                                                                                               |
| Live-updating view, tree relationships, friendlier UX, package installation allowed | `htop` (6)                                                                                                                                                                                                              |
| Need parent/child structure visually, one-shot                                      | `pstree -p` ([§33](./Section-33-Part5-What-A-Process-Is.md)'s 3)                                                                                                                                                        |
| Tool output looks wrong, or host too resource-starved for `top`/`htop`              | `/proc/[pid]/status` or `/stat` (7)                                                                                                                                                                                     |
| Scripting/automation reading a single process field                                 | `/proc/[pid]/stat` (compact, parseable) or targeted `ps -o`                                                                                                                                                             |
| Fleet-wide or scheduled perf triage entry point                                     | `ps`/`top` first, then Part 11's deeper tools (`vmstat`, `mpstat`, `iostat` — [§80](../Part11/Section-80-Part11-Performance-Fundamentals-Unified-Model.md)–[§88](../Part11/Section-88-Part11-Incident-Case-Studies.md)) |

## 9. Common Misconceptions

1. **"`ps aux` and `ps -ef` are just two ways of typing the same command."** They run under different option-parsing conventions (BSD vs. UNIX, 2) and produce genuinely different default column sets — they overlap heavily in purpose but aren't interchangeable syntax for identical output.
2. **"`top`'s `RES` column summed across all processes tells you total memory used."** Shared library pages get counted in every process's `RES` that maps them, so the sum overstates actual usage (5's Warning) — use `free` (Part 11) for the accurate system-wide figure.
3. **"`htop` is strictly better than `top`, so just always use it."** `htop` has a friendlier interface but is not guaranteed to be pre-installed (6) — over-relying on it leaves a gap in fluency for the one tool (`top`) guaranteed present on essentially every Linux host, including minimal images where `htop` was never installed.
4. **"Reading `/proc/[pid]` directly requires special privilege or tooling `ps`/`top` has that `cat` doesn't."** They're reading the exact same files — `ps` and `top` have no elevated access `cat` lacks ([§33](./Section-33-Part5-What-A-Process-Is.md)'s 6); the only real permission distinction is that a process can generally always read its own `/proc/[pid]` entries, while reading another user's process may be restricted depending on kernel hardening settings, unrelated to which tool is used.

## 10. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `ps` and `top`?"_
**Model answer:** `ps` prints a single static snapshot of processes at the moment it's run and then exits — good for scripting, piping, and one-off queries. `top` stays running and continuously refreshes a live view, and lets you interactively sort, kill, or renice processes without leaving the interface. Both read from the same underlying kernel process-table data; they differ in presentation and interactivity, not in what data they have access to.
_What the interviewer is probing for:_ Whether the candidate understands these are different interfaces to the same data, not different data sources.

**🎯 Intermediate:** _"Why do `ps aux` and `ps -ef` both work, and why do they show different columns?"_
**Model answer:** `ps` supports multiple historical option-parsing conventions simultaneously — BSD style (no leading dash, like `aux`) and UNIX/POSIX style (leading dash, like `-ef`). Both are valid ways of invoking `ps` and both request "show every process," but each style's default column set differs: `aux` leads with `%CPU`/`%MEM` and memory sizes, `-ef` leads with `PPID`. Neither is more correct; for a fixed, deliberately chosen column set instead of either default, `-o` with explicit format specifiers is more precise than relying on either idiom's defaults.
_What the interviewer is probing for:_ Recognition that this isn't a coincidence or a quirk to just memorize, but a real consequence of `ps` supporting multiple option grammars.

**🎯 Senior:** _"A host is showing high memory usage in `top`'s summary, but summing the `RES` column across all processes gives a much higher number than total RAM. What's going on?"_
**Model answer:** `RES` counts resident pages per process, and shared memory — most commonly shared library pages like libc that dozens of processes all map — gets counted in `RES` for every process that maps it. Summing `RES` across all rows double-, triple-, or N-times-counts that shared memory once per process sharing it, so the sum will overstate actual physical memory consumption, sometimes dramatically on a host running many instances of the same runtime (many PHP-FPM or Node worker processes sharing common libraries, for example). The accurate system-wide figure comes from `free` or `/proc/meminfo` (Part 11), which account for shared pages correctly rather than per-process.
_What the interviewer is probing for:_ Whether the candidate actually understands `VIRT`/`RES`/`SHR` semantics rather than treating `top`'s columns as interchangeable "memory numbers."

**🎯 Architect:** _"You're designing a lightweight process-health check that has to run inside minimal, resource-constrained containers where you can't guarantee `htop`, and shouldn't spawn heavyweight tooling. How do you approach it?"_
**Model answer:** I'd design it around `/proc/[pid]` reads directly rather than shelling out to `ps` or `top` at all — reading `/proc/[pid]/status` or `/proc/[pid]/stat` for the specific PIDs of interest is a plain file read against data the kernel already maintains, with no per-invocation process-table scan or formatting overhead the way spawning `ps` or `top` incurs, and no dependency on `htop` being installed at all. I'd pull state, RSS, and start time directly from those files, using start time (not bare PID, per [§33](./Section-33-Part5-What-A-Process-Is.md)'s wraparound caveat) if the check needs to correlate a specific process instance over time. For anything needing a broader sweep across many PIDs, `ps -eo` with a tight `-o` field list is still lighter weight than `top`'s continuous-refresh model, since it's a single snapshot rather than a persistent interactive session. The general principle: the friendlier a tool's interface, the more likely it's an optional package and the heavier its footprint — a constrained environment should default toward the guaranteed-present, lowest-overhead layer (`/proc` directly, or plain `ps`) rather than assuming convenience tooling will be there.
_What the interviewer is probing for:_ Practical judgment about tool overhead and availability in constrained environments, and fluency with `/proc` as a genuine first-class option, not just an academic fallback.

## 11. Key Takeaways

- `ps`, `top`, `htop`, and `/proc/[pid]` all read the same kernel process-table data ([§33](./Section-33-Part5-What-A-Process-Is.md)'s 6) — they differ in presentation, interactivity, and availability, not in what they can see.
- `ps aux` (BSD style) and `ps -ef` (UNIX style) are different option grammars that both mean "list every process," with different default columns — `ps -o` with explicit format specifiers is the precise, scriptable way to get exactly the fields needed.
- `top`'s header exposes load average, task-state counts (same letters as [§33](./Section-33-Part5-What-A-Process-Is.md)'s 4), and CPU-category breakdown; its per-process `VIRT`/`RES`/`SHR` columns must be read carefully — summing `RES` across processes overstates real memory use due to shared pages.
- Interactive `top` commands (`k` to kill, `r` to renice, `P`/`M`/`T` to sort) make it a live triage tool, not just a viewer; `htop` offers the same capability with a friendlier tree view and mouse support but is not guaranteed pre-installed.
- `/proc/[pid]/status` and `/proc/[pid]/stat` are the lowest-level, always-available fallback — useful when a higher-level tool's output looks wrong or the host is too constrained to run one comfortably.
- `ps`/`top` are the natural entry point into deeper performance triage — when their summary numbers indicate a problem, Part 11's dedicated tools (`vmstat`, `mpstat`, `iostat`, `free`, [§80](../Part11/Section-80-Part11-Performance-Fundamentals-Unified-Model.md)–[§88](../Part11/Section-88-Part11-Incident-Case-Studies.md)) take over for root-cause depth.

## 12. Related Concepts & What's Next

This section is the direct hands-on companion to [§33](./Section-33-Part5-What-A-Process-Is.md), applying its PID/PPID/state model through actual commands rather than introducing new concepts. It leans on [§24](../Part3/Section-24-Part3-Proc-Sys-Virtual-Filesystems.md)'s (Part 3) general introduction to `/proc` and `/sys`, applying that virtual-filesystem knowledge specifically to `/proc/[pid]`. The `k` (kill) and `r` (renice) interactive commands in `top`/`htop` are previews of [§36](./Section-36-Part5-Signals.md) (signals) and [§39](./Section-39-Part5-Scheduling-Tasks-Cron-At-Systemd-Timers.md) (`nice`/`renice`), covered in full mechanical depth later in this Part. [§35](./Section-35-Part5-Process-Lifecycle-Fork-Exec-Wait-Zombie-Orphan.md) (next) picks up the process lifecycle itself — `fork()`, `exec()`, `wait()`, and the zombie/orphan mechanics [§33](./Section-33-Part5-What-A-Process-Is.md) only sketched — using the same `ps`/`/proc` tools introduced here to observe that lifecycle in action. Part 11 ([§80](../Part11/Section-80-Part11-Performance-Fundamentals-Unified-Model.md)–[§88](../Part11/Section-88-Part11-Incident-Case-Studies.md)) returns to `ps`/`top` as the starting point for a much deeper performance-monitoring toolchain once basic process visibility here is second nature.

**Next Section:** [§35](./Section-35-Part5-Process-Lifecycle-Fork-Exec-Wait-Zombie-Orphan.md) — `Section-35-Part5-Process-Lifecycle-Fork-Exec-Wait-Zombie-Orphan.md`
