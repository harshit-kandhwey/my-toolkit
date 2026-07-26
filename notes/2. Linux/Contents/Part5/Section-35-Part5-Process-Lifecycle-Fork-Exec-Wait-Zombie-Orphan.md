# Section 35 (Part 5): Process Lifecycle: fork, exec, wait, Zombie and Orphan Processes

## 1. Overview: Where This Picks Up

§33 established that every process has a PID and a PPID, and walked through the process state machine — including the zombie state (`Z`) as one entry in that state table. §33 deliberately didn't explain _why_ zombies exist or _how_ a process comes into being in the first place; it only named the states. This section closes both gaps: it covers the actual mechanism Linux uses to create processes (`fork()` and `exec()`), the mechanism a parent uses to learn a child has finished (`wait()`/`waitpid()`), and why the zombie and orphan states are direct, unavoidable consequences of that mechanism rather than bugs or edge cases.

Nearly everything that happens when you run a command on Linux — a shell launching `ls`, a web server spawning a worker, a script launching a subprocess — goes through this same fork-then-exec pattern underneath, whether or not the language or tool you're using makes that visible.

## 2. `fork()`: Duplicating a Process

`fork()` is a system call that creates a new process — the **child** — as a near-identical copy of the calling process — the **parent**. "Near-identical" is precise here: the child gets a copy of the parent's memory space, open file descriptors, environment variables, and signal dispositions, and execution resumes in _both_ processes at the exact instruction right after the `fork()` call returned. The only immediate difference between parent and child at that point is the return value of `fork()` itself: it returns the child's PID to the parent, `0` to the child, and a negative value to the parent if the fork failed.

> 💡 **Tip:** The phrase "copies the process's memory" is the single most misleading part of how `fork()` is often described casually. Modern Linux does **not** physically duplicate the parent's entire address space at fork time — it uses **copy-on-write (COW)**: both parent and child initially share the same physical memory pages, marked read-only, and the kernel only actually copies a page the moment either process tries to _write_ to it. This is why `fork()`ing even a process with several gigabytes of resident memory is fast — the cost is proportional to the page-table bookkeeping, not to copying the underlying data.

Because the child is a copy, right after `fork()` it is running the exact same program the parent was running — same code, same data, just a different PID and a fresh, independent copy-on-write view of memory. On its own, `fork()` cannot make a process run a _different_ program; that's `exec()`'s job (3).

**What a child inherits vs. what's independent:**

| Inherited (initially shared/copied)                  | Independent immediately after `fork()`       |
| ---------------------------------------------------- | -------------------------------------------- |
| Open file descriptors (same underlying file offsets) | PID                                          |
| Environment variables                                | PPID (set to the forking parent's PID)       |
| Memory contents (COW)                                | Memory writes (COW divergence on write)      |
| Signal handler dispositions                          | Pending signals, own resource usage counters |
| Current working directory, umask                     | —                                            |

## 3. `exec()`: Replacing the Process Image

The `exec()` family of system calls (`execve()` underneath, with `execl()`, `execvp()`, and other libc wrappers around it) **replaces the calling process's memory image with a new program**. Unlike `fork()`, `exec()` does not create a new process — the PID stays exactly the same. What changes is everything the PID is running: the code, the data segments, the stack, and the heap are all discarded and replaced with a freshly loaded program, which then starts executing from that program's entry point.

`exec()` only returns to the caller **if it fails** — on success, there is no "caller" left to return to, because the caller's code has literally been replaced by the new program's code.

**The fork-then-exec pattern:** the combination of these two calls is how nearly every new program on Linux gets started. When you type `ls` in a shell:

1. The shell calls `fork()`, producing a child that is, at that instant, a copy of the shell.
2. The child calls one of the `exec()` variants, e.g. `execvp("ls", argv)`, which replaces that child's memory image with the `ls` binary.
3. The child's PID is unchanged, but it is now running `ls`, not the shell — and the parent shell, unaffected by the child's `exec()`, continues running as the shell it always was.

This is precisely why the pattern needs two separate calls rather than one "run this other program" call: `fork()` gets you a second, independent process to work with; `exec()` is what turns that second process into something other than a copy of the parent. A single combined "spawn" primitive would lose the useful middle step where the child can still adjust its own environment — redirecting file descriptors, changing its working directory, dropping privileges — after `fork()` but before `exec()`, entirely within its own copy, without touching the parent at all. Shells' `>`, `<`, and `2>&1` redirection all happen in exactly that window.

## 4. `wait()` and `waitpid()`: Collecting the Exit Status

When a child process terminates — normally via `exit()` or `_exit()`, or abnormally via an uncaught signal — the kernel does not simply erase it. The kernel keeps a small **process table entry** for the terminated child, holding its exit status (and some accounting info), and expects the parent to retrieve that status via `wait()` or `waitpid()`.

| Call                             | Behavior                                                                                                           |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `wait(&status)`                  | Blocks until **any** child terminates, then returns its PID and exit status                                        |
| `waitpid(pid, &status, options)` | Waits for a **specific** child (or a specific process group), with options like `WNOHANG` to poll without blocking |

Calling `wait()`/`waitpid()` is what allows the kernel to fully discard the terminated child's process table entry — this is the step that actually reaps the process. Until the parent does this, the terminated child sits in the state §33 named **zombie** (`Z`).

## 5. The Zombie State, Precisely

A **zombie** is a process that has terminated but whose parent has not yet called `wait()`/`waitpid()` to collect its exit status. §33 named this state; here is exactly what it means and doesn't mean:

- The zombie's code, data, heap, and stack are **already gone** — the kernel released all of that at termination. There is no program running, no CPU time being consumed, and no meaningful memory footprint being held by the zombie.
- What remains is a **minimal process table entry**: PID, exit status, and a handful of accounting fields (CPU time used, etc.) — just enough for the parent to eventually learn how the child ended.
- A zombie cannot be killed with `SIGKILL` or any other signal — there is no running process left to receive one. It's already dead; it's waiting to be acknowledged, not waiting to be terminated.

> ⚠️ **Warning:** The common misconception that "zombie processes consume memory and CPU and need to be killed" is wrong on both counts, and worth correcting explicitly because it leads to the wrong remediation. A zombie holds essentially no resources beyond its process table entry, and it cannot be signaled away. The only way a zombie disappears is for its parent to call `wait()`/`waitpid()` on it (5) — or for the parent itself to terminate, at which point the zombie is re-parented and reaped as described in 7.

A single zombie, or even a handful, is close to harmless — a few bytes of kernel bookkeeping, nothing more. The reason zombies matter operationally is entirely about **accumulation**: every zombie occupies one entry in a finite resource — the kernel's process table — and the maximum number of PIDs a system can allocate is bounded (`/proc/sys/kernel/pid_max`). A parent that spawns children in a loop and never calls `wait()` on any of them will accumulate zombies indefinitely, and eventually the system can hit its PID ceiling, at which point it can no longer create **any** new process — not just for that faulty program, but system-wide. In that sense, an accumulating zombie count is never itself the problem to fix; it's a **symptom of a parent process with a bug** — one that forks children but never reaps them.

## 6. Diagnosing Zombies: Finding the Neglectful Parent

Since a zombie is harmless in isolation, the diagnostic goal is never "kill the zombie" (impossible, per 5) — it's **identifying which parent process is failing to call `wait()`**, because that parent is the thing that actually needs fixing or restarting.

**Step 1 — confirm zombies exist and how many:**

```bash
ps aux | grep 'Z'
```

or more precisely, filtering on the state column itself:

```bash
ps -eo pid,ppid,stat,cmd | awk '$3 ~ /Z/'
```

A zombie's `STAT` column shows `Z` (commonly `Z+` if it's also in the foreground process group). Its `CMD` column typically shows `<defunct>`, another reliable marker.

**Step 2 — find the parent via PPID:**

```bash
ps -o pid,ppid,stat,cmd -p <zombie_pid>
```

The `PPID` column names the process responsible for reaping this zombie. That parent PID is the actual target for investigation — check what it's running (`ps -p <ppid> -o cmd=`), how long it's been running, and whether it's a known service with a documented bug in its child-process handling (a common real-world cause: a script or daemon that forks worker subprocesses and only checks whether they started, never whether they finished).

**Step 3 — remediate the parent, not the zombie.** Options, in order of preference:

- Fix the parent's code to actually call `wait()`/`waitpid()` on children it spawns (the correct long-term fix).
- If the parent can't be fixed quickly, restarting the parent process reaps all of its zombie children as a side effect — when a parent terminates, any of its remaining zombie children get re-parented (7) and are then reaped by the new parent, clearing them out.
- As a stopgap on a system with a very large accumulated zombie count actively approaching `pid_max`, restarting the offending service is far safer and faster than any zombie-specific tooling, because no such tooling exists — there is nothing to signal or kill directly.

> 💡 **Tip:** `ps -eo pid,ppid,stat,cmd | awk '$3 ~ /Z/'` combined with a second `ps -o ppid= -p <pid>` lookup is the entire diagnostic toolkit for zombies — there's no deeper zombie-specific command, because a zombie has no runtime behavior left to inspect beyond its exit status.

## 7. The Orphan Process and Re-Parenting

An **orphan** is the mirror-image situation: a child whose **parent terminates before the child does**. The child process itself is still very much alive and running — orphan describes a broken parent link, not a broken or defunct process.

When a parent dies while it still has living children, the kernel immediately **re-parents** those children rather than leaving them parentless (every process must have a valid PPID at all times). The traditional target for re-parenting is **PID 1** — §13 covered PID 1's role as the orphan reaper directly: init (or systemd) is written to periodically `wait()` on any children that get re-parented to it, which is exactly what prevents an orphan from itself becoming a zombie once it eventually exits.

Modern Linux refines this with the **subreaper** mechanism (`PR_SET_CHILD_SUBREAPER`, via `prctl()`): a process can mark itself as a subreaper, and orphans within its subtree get re-parented to the nearest subreaper ancestor instead of jumping all the way to PID 1. This matters in practice for anything that manages its own tree of subprocesses — container runtimes and process supervisors are the canonical example, since a container's PID 1 (often the containerized application itself, not a full init system) may not be written to reap orphans at all, so a subreaper closer to the actual orphaning event ensures re-parented children still get properly waited on.

**Diagnosing an orphan** is normally uninteresting — re-parenting is instantaneous and transparent, and the process itself continues running correctly. It becomes worth checking only when a process's behavior seems to assume a parent relationship that no longer holds (e.g., code that checks `getppid()` and behaves differently once it observes PID 1 or a subreaper instead of its original parent):

```bash
ps -o pid,ppid,cmd -p <pid>
```

A `PPID` of `1` (or the relevant container's supervisor PID) on a process you expect to be a child of some other still-running process is the signal that re-parenting already happened — the original parent is gone, and this process is now an orphan under its reaper.

## 8. Common Misconceptions

1. **"`fork()` copies the entire process's memory, which is slow."** Modern Linux uses copy-on-write (2) — pages are shared until either process writes to them, so `fork()` is cheap even for processes with large memory footprints. The "full copy" mental model is a holdover from how `fork()` was implemented decades ago, not how it behaves today.
2. **"Zombies consume meaningful memory or CPU and should be killed."** A zombie has already released its code, data, and running state — all that remains is a small process-table entry holding the exit status, and it can't be signaled or killed because there's no running process left to receive a signal (5). The fix is always to make the parent call `wait()`, not to attack the zombie directly.
3. **"A single zombie means something is broken."** One or a few zombies are a completely normal, transient artifact of any process that has exited moments before its parent gets around to calling `wait()` — that window is typically milliseconds. It's a large, sustained, or continuously growing zombie count that indicates a genuine parent bug (5), not the mere existence of any zombie at all.
4. **"Orphan and zombie are the same problem, or interchangeable terms."** They're near-opposite situations. A zombie is a dead process whose parent hasn't reaped it yet; an orphan is a live process whose parent died first (7). A process can even pass through both roles at different points, but the underlying conditions — child exited first vs. parent exited first — are distinct and diagnosed differently.
5. **"`exec()` starts a new process."** It does not — it replaces the current process's program image in place, keeping the same PID (3). The new-process step is entirely `fork()`'s job; `exec()`'s job is only ever "become a different program," which is why the two are almost always used together rather than either alone.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `fork()` and `exec()`?"_
**Model answer:** `fork()` creates a new process — the child — as a copy of the calling process, with a new PID but otherwise starting out with the same memory contents (via copy-on-write), open files, and environment as the parent. `exec()` doesn't create a new process at all; it replaces the calling process's own memory image with a different program, keeping the same PID. They're used together — fork to get a second process, then exec in the child to turn that second process into something other than a copy of the parent — because that's how a shell launches every command you type.
_What the interviewer is probing for:_ Whether the candidate can state the actual division of responsibility rather than treating "fork/exec" as one vague blended concept.

**🎯 Intermediate:** _"A process shows up as `Z` in `ps`. What is it, and what do you actually do about it?"_
**Model answer:** It's a zombie — a process that has already terminated, but whose parent hasn't called `wait()`/`waitpid()` yet to collect its exit status, so the kernel keeps a minimal process-table entry around holding that status. It holds essentially no memory or CPU — you can't kill it with a signal because there's no running process left. The fix is never to target the zombie; it's to find its parent via `ps -o ppid= -p <pid>` and figure out why that parent isn't reaping its children — usually a bug where it forks workers but never waits on them. If the parent can't be fixed quickly, restarting it clears out its zombies as a side effect, since re-parented orphans among the zombie's own children get reaped by whatever process picks them up next.
_What the interviewer is probing for:_ Correcting the "zombies consume resources" misconception and jumping straight to the parent-focused diagnostic instead of trying to act on the zombie itself.

**🎯 Senior:** _"Why can accumulating zombies actually bring down a system, given each one is nearly free?"_
**Model answer:** Individually a zombie costs almost nothing, but each one permanently occupies a slot in the finite process table until reaped, and PID allocation on Linux is bounded by `pid_max`. A parent with a systemic bug — forking children in a loop, maybe under load, and never calling `wait()` on any of them — will accumulate zombies without bound over time. Eventually the system exhausts available PIDs, and at that point it can't fork any new process at all, for any workload on the box, not just the buggy one. That's why the operational lesson is that zombie count is a leading indicator to alert on, not a cosmetic detail — by the time you're actually hitting `pid_max`, you're one step from a total inability to spawn processes, and the actual root cause (a parent that never reaps) has usually been present and worsening for a long time before it becomes visible as an outage.
_What the interviewer is probing for:_ Connecting an individually-trivial artifact to a systemic, finite-resource failure mode, and recognizing zombie accumulation as a monitoring signal rather than a one-off nuisance.

**🎯 Architect:** _"You're running a custom process supervisor inside a container that itself is the container's PID 1. What do you need to get right about child reaping that you wouldn't need to worry about on a normal host?"_
**Model answer:** On a normal host, PID 1 is systemd or init, and it's specifically written to `wait()` on anything re-parented to it (§13), so orphans are always eventually reaped no matter what spawned them. Inside a container, PID 1 is often the application or supervisor itself, and unless that program was deliberately written to also act as a reaper — waiting on arbitrary re-parented orphans, not just its own direct children — any orphaned grandchild process re-parented to it can sit as a zombie forever, since there's no systemd underneath to catch it. The concrete fix is either to use an init-capable entrypoint designed for containers (something that acts as a proper subreaper for the container's PID namespace) or to explicitly mark the supervisor as a subreaper via `prctl(PR_SET_CHILD_SUBREAPER)` and make sure its main loop actually calls `waitpid()` broadly, not just on the specific children it launched directly. I'd verify this concretely by intentionally orphaning a grandchild process in a test container and confirming it gets reaped rather than piling up as a permanent zombie — assuming it will "just work like it does on a normal host" is exactly the assumption that breaks here.
_What the interviewer is probing for:_ Recognizing that PID 1's reaping guarantee (§13) is an init-system property, not a kernel guarantee that automatically holds for any arbitrary PID-1 program, and knowing the subreaper mechanism as the concrete remediation inside containers.

## 10. Key Takeaways

- `fork()` creates a new process as a copy-on-write copy of the caller — cheap regardless of the parent's memory size, because pages are only actually duplicated on write, not at fork time.
- `exec()` replaces the calling process's own memory image with a different program in place, keeping the same PID — it never creates a new process, and it only returns to the caller on failure.
- The fork-then-exec pattern is how nearly every new process on Linux is created, and the gap between the two calls is exactly where a child can adjust its own environment (redirection, working directory, privileges) before becoming a different program.
- `wait()`/`waitpid()` is how a parent collects a terminated child's exit status; until that call happens, the child sits as a zombie holding only a minimal process-table entry — no meaningful memory or CPU, and not killable by signal.
- A zombie is basically harmless individually; a large or growing zombie count is a symptom of a parent bug (never reaping its children) that risks exhausting the finite process table (`pid_max`) system-wide.
- An orphan is a live child whose parent died first; the kernel re-parents it to PID 1 or the nearest subreaper (§13), which is what ultimately reaps it once it exits — this is why PID 1 or a proper subreaper must exist for orphans to ever be cleaned up, a guarantee that doesn't automatically hold for arbitrary container PID-1 programs.
- Diagnosis is always parent-focused: `ps -eo pid,ppid,stat,cmd` to find the zombie's state and PPID, then investigate or restart that parent — there is no way to act on a zombie directly.

## 11. Related Concepts & What's Next

This section explains the mechanism behind the zombie state §33 named but didn't derive, and it depends directly on §13's coverage of PID 1 as the orphan reaper — re-parenting (7) is the concrete mechanism behind that claim. The subreaper discussion previews a concern that becomes fully concrete in Part 13's containers coverage (namespaces, cgroups), where a container's PID 1 frequently isn't a full init system at all. §36 (next) moves to signals — `SIGTERM`, `SIGKILL`, `SIGHUP`, `SIGINT` — the mechanism a parent (or any process with permission) uses to actually influence a running process's behavior, including how a child's abnormal termination via an uncaught signal is exactly the kind of exit `wait()` reports back to a parent.

**Next Section:** §36 — `Section-36-Part5-Signals.md`
