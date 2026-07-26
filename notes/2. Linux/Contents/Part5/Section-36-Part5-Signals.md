# Section 36 (Part 5): Signals: SIGTERM, SIGKILL, SIGHUP, SIGINT, and Signal Handling

## 1. What a Signal Actually Is

§35 walked through a process's normal lifecycle — `fork()`, `exec()`, running, exiting, `wait()`-ed on by its parent. What that lifecycle didn't cover is how a process gets interrupted from _outside_ that normal flow — how the kernel tells a process "stop what you're doing" without going through any of its regular input channels at all. That mechanism is a **signal**.

A signal is a small, asynchronous notification delivered to a process by the kernel — not data passed through a pipe, a file descriptor, or any channel the receiving process explicitly reads from. A process doesn't "poll" for signals as part of its normal logic; the kernel interrupts whatever the process is doing, delivers the signal, and either runs a handler the process registered in advance or falls back to a default kernel-defined action if the process registered nothing.

This asynchrony is the entire point and the entire danger. A signal can arrive between any two machine instructions — mid-loop, mid-syscall, mid-anything — which is why signal handlers are conventionally written to do as little as possible (commonly just setting a flag a program checks later) rather than performing complex work inside the handler itself.

Signals originate from several places, not just other processes deliberately targeting one:

- **The kernel itself**, in response to a hardware exception (e.g., a process dereferences invalid memory and the kernel delivers `SIGSEGV`).
- **Another process**, via the `kill()` system call (despite the name, `kill()` sends any signal, not just termination — §3 covers the actual `kill` command).
- **The terminal driver**, translating a keystroke like Ctrl+C into a signal sent to the foreground process group (§37 covers foreground/background job control and exactly how this delivery works).
- **The process itself**, sending a signal to itself or another process it has permission to signal.

> 💡 **Tip:** The signal-vs-data distinction is worth holding onto precisely because it explains why signals are so limited as an IPC mechanism (§40 covers real inter-process communication) — a signal carries almost no payload beyond "which signal number arrived," so it's suited to notifying a process that something happened, not to transferring any actual information about what that something was.

## 2. Key Signals

Every signal has both a **number** and a **symbolic name**; scripts and command-line tools accept either, though the name is more portable across kernel versions (numbering below is the common Linux/x86 convention — a small number of signals vary by architecture).

| Signal    | Number | Default Action              | Typical Meaning / Origin                                                                            |
| --------- | ------ | --------------------------- | --------------------------------------------------------------------------------------------------- |
| `SIGHUP`  | 1      | Terminate                   | Historically: controlling terminal disconnected. Today: widely repurposed as "reload configuration" |
| `SIGINT`  | 2      | Terminate                   | Interrupt from the keyboard — Ctrl+C, sent to the foreground process group                          |
| `SIGKILL` | 9      | Terminate (un-catchable)    | Immediate, unconditional termination — the kernel simply removes the process                        |
| `SIGSEGV` | 11     | Terminate (+ core dump)     | Invalid memory access — a genuine fault, not a graceful request                                     |
| `SIGTERM` | 15     | Terminate                   | The polite, catchable request to terminate — the default signal sent by `kill` with no flags        |
| `SIGSTOP` | 19     | Stop process (un-catchable) | Suspend the process — job control (§37), cannot be caught, blocked, or ignored, same as `SIGKILL`   |
| `SIGCONT` | 18     | Continue if stopped         | Resume a process previously suspended by `SIGSTOP`/`SIGTSTP`                                        |

**`SIGHUP`'s repurposing is worth calling out explicitly** because it's a common source of confusion for anyone reading older documentation literally: it originally meant "the terminal line hung up" — the controlling terminal session ended, so the process should exit. Modern long-running daemons (nginx, many others) instead hook a `SIGHUP` handler to mean "re-read your configuration file without restarting" — the signal number and delivery mechanism didn't change, but the convention layered on top of it did, entirely by application-level agreement rather than any kernel enforcement.

## 3. Why SIGKILL and SIGSTOP Cannot Be Caught, Blocked, or Ignored

This is a **kernel guarantee**, not a convention that a sufficiently determined program could work around. Every other signal in the table above can be intercepted by a process — given a custom handler, deliberately ignored, or temporarily blocked from delivery. `SIGKILL` (9) and `SIGSTOP` (19) are structurally different: the kernel does not offer any API surface for a process to register a handler for them, ignore them, or block them. When either is sent, the kernel acts directly — terminating or suspending the process — without ever giving the target process's own code a chance to run in response.

The reason is deliberate: every other signal being catchable means a sufficiently broken or malicious process could catch `SIGTERM`, do nothing, and simply never die — leaving an administrator with no way to forcibly stop it. `SIGKILL` exists specifically as the guaranteed backstop that cannot be defeated this way, and `SIGSTOP` exists as the equivalent guarantee for job control (§37) — a shell needs to be able to suspend a job unconditionally, not subject to that job's own cooperation.

> ⚠️ **Warning:** "Un-catchable" doesn't mean "instantaneous" from an administrator's point of view. `SIGKILL` reaching a process's signal-handling code is guaranteed and immediate, but the process still has to actually exit — and if it's blocked in an uninterruptible kernel wait (D state, §33 covered process states), the kernel itself won't act on the pending signal until that wait resolves. This is the concrete answer to "why does `kill -9` sometimes not work" — covered in full in 7.

## 4. Signal Handling Options: Default, Ignore, Custom Handler

For every signal a process is actually allowed to intercept (i.e., everything except `SIGKILL`/`SIGSTOP`), a process has exactly three dispositions available, set via the `signal()` or `sigaction()` system calls:

1. **Default action** — do nothing special; let the kernel apply whatever its built-in default is for that signal (terminate, terminate-with-core-dump, stop, continue, or in a handful of cases, ignore). This is every process's disposition unless it explicitly changes it.
2. **Ignore** — explicitly tell the kernel to discard the signal on delivery, doing nothing at all. A process can ignore `SIGTERM`, for instance, though doing so for a shutdown signal without providing an alternative graceful-exit path is generally poor practice — it defeats the cooperative shutdown pattern covered in 6.
3. **Custom handler** — register a function that runs when the signal arrives, executing arbitrary (ideally minimal, per §1's Tip) application code instead of the kernel's default action. This is how a daemon implements "on `SIGHUP`, re-read config" or "on `SIGTERM`, finish the in-flight request, close connections cleanly, then exit" rather than dying mid-work.

The distinction between disposition 1 and 2 matters more than it looks: a process that has taken no action at all for `SIGTERM` still dies immediately on receipt (default action = terminate) — a process only survives `SIGTERM` if it has deliberately registered a handler or set it to be ignored. "I didn't write any signal-handling code" is not the same as "my process is protected from `SIGTERM`."

## 5. `kill`, `pkill`, and `killall`: Sending Signals from the Shell

**Purpose:** These three commands all send signals to running processes; they differ in how the target is identified.

### 5.1 `kill` — target by PID

```bash
kill [-signal] pid [pid ...]
```

| Flag      | Meaning                                                                                       |
| --------- | --------------------------------------------------------------------------------------------- |
| (no flag) | Sends `SIGTERM` (15) by default                                                               |
| `-9`      | Sends `SIGKILL` — immediate, un-catchable termination                                         |
| `-15`     | Sends `SIGTERM` explicitly — equivalent to the no-flag default, useful for clarity in scripts |
| `-HUP`    | Sends by symbolic name instead of number — `-HUP`, `-INT`, `-KILL` all accepted               |
| `-l`      | Lists all available signal names and numbers, rather than sending anything                    |

```bash
$ kill -l
 1) SIGHUP       2) SIGINT       3) SIGQUIT      4) SIGILL       5) SIGTRAP
 6) SIGABRT      7) SIGBUS       8) SIGFPE       9) SIGKILL     10) SIGUSR1
11) SIGSEGV     12) SIGUSR2     13) SIGPIPE     14) SIGALRM     15) SIGTERM
...
```

```bash
kill 4821        # send SIGTERM to PID 4821 — a graceful request
kill -9 4821      # send SIGKILL to PID 4821 — unconditional termination
kill -HUP 4821    # send SIGHUP — often means "reload config" for daemons
```

**Common errors:**

- Reaching for `kill -9` as a first move. It is a last resort, not a default — it gives the target process zero opportunity to clean up open files, flush buffered writes, close network connections, or remove lock files, all of which `SIGTERM` gives it the chance to do (6).
- `kill` with no `-9` does not guarantee the process actually dies — it only guarantees `SIGTERM` was delivered; a process that catches and ignores it, or is stuck in D-state, will still be running afterward (7).

### 5.2 `pkill` — target by name or attribute

```bash
pkill [-signal] pattern
```

Matches against process name (or full command line with `-f`) instead of requiring a PID lookup first:

```bash
pkill -9 nginx          # SIGKILL every process whose name matches "nginx"
pkill -f "worker.py"    # match against full command line, not just the process name
```

> ⚠️ **Warning:** `pkill`'s pattern matching is broader than it looks — a loose pattern can match more processes than intended, including unrelated ones that happen to share a substring. Always sanity-check with `pgrep` (the read-only equivalent, listing matches without signaling them) before running `pkill` with a destructive signal.

### 5.3 `killall` — target by exact process name

```bash
killall [-signal] name
```

Similar intent to `pkill`, but matches the exact process name rather than a regex-style pattern — `killall nginx` signals every process literally named `nginx`. Distribution availability varies (some minimal images omit it), and its name is a frequent point of confusion for admins coming from other Unix variants where `killall` historically meant something closer to "kill every process on the system" — on Linux it does not do that.

## 6. The Graceful-Shutdown Pattern: SIGTERM, Wait, Escalate to SIGKILL

The pattern underlying almost every well-behaved process-stopping mechanism on Linux is the same three-step sequence:

1. **Send `SIGTERM`.** Give the target process a chance to catch the signal, finish in-flight work, close resources cleanly, and exit on its own terms.
2. **Wait a bounded grace period.** Long enough for well-behaved cleanup, short enough not to hang indefinitely on a process that never intends to exit.
3. **Escalate to `SIGKILL` if the process is still alive after the grace period.** At this point, cooperation has been given a fair chance and failed — `SIGKILL`'s un-catchable guarantee (3) is what makes this step reliable regardless of what the target process's code does or doesn't do.

> 💡 **Tip:** This exact pattern is not just a shell scripting idiom — it's precisely what **systemd** does internally when stopping a service (`TimeoutStopSec`, full depth in Part 9, §65–§72) and what **Docker/Kubernetes** do when stopping a container (`docker stop`'s grace period, Kubernetes's `terminationGracePeriodSeconds`). Understanding this three-step sequence at the signal level directly explains behavior that otherwise looks like unrelated, tool-specific configuration in each of those higher-level systems — they're all the same underlying pattern with a different grace-period knob exposed.

A manual shell version of the same idea:

```bash
kill -15 4821                     # step 1: ask nicely
sleep 10                           # step 2: bounded grace period
kill -0 4821 2>/dev/null && kill -9 4821   # step 3: still alive? force it
```

(`kill -0` sends no actual signal — it only checks whether the PID still exists and is signalable, a common idiom for "is this process still running" without disturbing it.)

## 7. Why `kill -9` Sometimes "Doesn't Work"

This is one of the most common points of genuine confusion, because it looks like it contradicts §3's kernel guarantee — it doesn't. `SIGKILL` delivery to a process is guaranteed; what isn't guaranteed is that the process can act on it _immediately_.

The concrete cause is almost always **uninterruptible sleep (D state)**, covered in §33's process-states discussion. A process blocked in D-state is waiting on a kernel-level operation — typically slow or hung I/O (an unresponsive NFS mount, a failing disk, a stuck device driver) — and the kernel will not deliver even `SIGKILL` to the process's own code path until that kernel-level wait resolves one way or another. The signal is recorded as pending, not lost, but "pending forever" looks indistinguishable from "`kill -9` didn't work" to an administrator watching `ps` show the process still there.

**Diagnosing it:**

```bash
ps -o pid,stat,comm -p 4821
```

A `STAT` column showing `D` (rather than `S`, `R`, `T`, or `Z`) confirms uninterruptible sleep is the cause, not a signal-handling bug. The practical fix is almost never "send the signal harder" — it's identifying and resolving whatever the process is actually blocked on at the kernel level (the hung mount, the failing device), since no signal, including `SIGKILL`, can pull a process out of D-state from the outside.

> ⚠️ **Warning:** Don't mistake a zombie (`Z` state, §33 and §35) for this problem — a zombie process is already dead and holds no resources beyond its exit-status entry; sending it any signal, including `SIGKILL`, is a no-op because there's no running process left to signal. A zombie's exit code needs to be reaped via `wait()` by its parent (§35), not killed.

## 8. Common Misconceptions

1. **"`kill` always terminates a process."** `kill`'s name is historical and misleading — it's a general signal-sending system call and command, capable of sending `SIGSTOP`, `SIGCONT`, `SIGHUP`, or any other signal, not exclusively termination signals. `kill -STOP pid` suspends a process; it doesn't touch it in a way that ends it.
2. **"`SIGTERM` and `SIGKILL` are just two strengths of the same request."** They're categorically different — `SIGTERM` is a cooperative request a process can catch, handle, or ignore (4); `SIGKILL` is an unconditional kernel action the target process has zero say in (3). Treating `-9` as merely "a stronger `-15`" misses that it skips the target's own cleanup code entirely.
3. **"`kill -9` failing means the signal wasn't delivered."** The signal is delivered (or recorded as pending) regardless; what can fail is the process's ability to act on it while stuck in an uninterruptible kernel wait (7) — a distinction that matters because the fix is diagnosing the underlying I/O problem, not retrying the kill.
4. **"`SIGHUP` always means terminate."** Only by original, historical convention — most modern long-running daemons repurpose it as "reload configuration," entirely by application-level agreement (2). Sending `SIGHUP` to an arbitrary process without knowing what it does with that signal risks either outcome.

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `SIGTERM` and `SIGKILL`?"_
**Model answer:** `SIGTERM` (15) is a polite, catchable request to terminate — the process can register a handler, run cleanup code, and exit on its own terms, or even ignore it entirely. `SIGKILL` (9) is an unconditional kernel action — the process cannot catch, block, or ignore it, and the kernel terminates it directly without giving its own code any chance to run. `SIGTERM` should always be tried first because it allows graceful shutdown; `SIGKILL` is the last-resort backstop for when a process doesn't respond to `SIGTERM`.
_What the interviewer is probing for:_ Basic fluency with the two most common signals and the reasoning for preferring one as a default.

**🎯 Intermediate:** _"Why can't a process catch or ignore `SIGKILL`, and why does that matter operationally?"_
**Model answer:** It's a deliberate kernel guarantee, not a limitation that could theoretically be worked around — the kernel provides no API for a process to register a handler for `SIGKILL` or `SIGSTOP`, so delivery bypasses the target's own code entirely. Operationally, this matters because every other signal being catchable means a broken or malicious process could catch `SIGTERM` and simply never exit, leaving no way to forcibly stop it — `SIGKILL` exists specifically as the guaranteed backstop for that case, which is exactly why the standard shutdown pattern is "try `SIGTERM` first, escalate to `SIGKILL` only after a grace period."
_What the interviewer is probing for:_ Understanding this as a kernel-enforced guarantee with a specific operational reason, not just a memorized fact.

**🎯 Senior:** _"A `kill -9` on a hung process isn't working — the process is still showing up in `ps`. Walk me through your diagnosis."_
**Model answer:** First I'd check the process's state with `ps -o pid,stat,comm -p <pid>` — if `STAT` shows `D`, that's uninterruptible sleep, meaning the process is blocked on a kernel-level operation, typically slow or hung I/O like an unresponsive NFS mount or a failing disk, and the kernel won't act on any pending signal, including `SIGKILL`, until that wait resolves. In that case, retrying the kill accomplishes nothing — I'd instead investigate what the process is actually blocked on (`/proc/<pid>/stack` if available, checking the underlying mount or device) and fix that root cause rather than the symptom. If instead the state shows `Z` (zombie), the process is already dead and no signal can do anything further — it needs its parent to call `wait()` on it, or if the parent itself is gone or unresponsive, addressing the parent is the actual fix.
_What the interviewer is probing for:_ Correctly distinguishing D-state from zombie state as two different reasons `kill -9` looks like it "isn't working," and knowing the diagnosis path (`ps` STAT column) rather than just repeating the kill.

**🎯 Architect:** _"You're designing the shutdown behavior for a custom service that systemd will manage. How do you think about signal handling end to end?"_
**Model answer:** I'd implement a `SIGTERM` handler that does real graceful shutdown — stop accepting new work, let in-flight requests finish (bounded by a sensible internal timeout so a stuck request doesn't hang the whole shutdown), close connections and flush any buffered state, then exit cleanly with an appropriate exit code. I would not ignore `SIGTERM` or rely purely on the process dying by default action, since that skips cleanup. I'd also decide deliberately whether `SIGHUP` means "reload config" for this service, following the now-common convention (2), and document that choice since it's not something a downstream operator can safely assume. On the systemd side, I'd size `TimeoutStopSec` to comfortably exceed the worst-case graceful-shutdown time my `SIGTERM` handler needs, understanding that systemd's model is exactly the pattern in 6 — `SIGTERM`, wait, escalate to `SIGKILL` — so an undersized timeout means systemd force-kills the service before my handler finishes, defeating the whole point of having one. Finally, I'd make sure the process never ends up doing meaningful work inside the signal handler itself — just setting a flag or writing to a self-pipe that the main loop checks — since signal handlers interrupting arbitrary code mid-instruction are a poor place to run anything non-trivial.
_What the interviewer is probing for:_ End-to-end ownership of signal handling as a design decision — not just "catch SIGTERM" but sizing the timeout against systemd's real behavior, being deliberate about SIGHUP, and respecting signal-handler-safety constraints.

## 10. Key Takeaways

- A signal is an asynchronous kernel-delivered notification, not data passed through a normal I/O channel — it can interrupt a process between any two instructions, which is why handlers should stay minimal.
- `SIGTERM` (15, graceful/catchable), `SIGKILL` (9, unconditional/un-catchable), `SIGHUP` (1, historically terminal-disconnect, now widely "reload config"), `SIGINT` (2, Ctrl+C), and `SIGSTOP`/`SIGCONT` (job control) are the signals worth knowing cold.
- `SIGKILL` and `SIGSTOP` cannot be caught, blocked, or ignored — a kernel-enforced guarantee, not a convention, that exists specifically as an unconditional backstop against processes that won't respond to anything catchable.
- A process's disposition toward any catchable signal is one of three things: default action, explicitly ignored, or a custom handler — "no code written" still means the default action applies, not immunity.
- `kill`/`pkill`/`killall` all send signals (`SIGTERM` by default, `-9` for `SIGKILL`); `kill -l` lists every signal name/number; `pkill`/`killall` target by name/pattern instead of requiring a PID lookup first.
- The graceful-shutdown pattern — `SIGTERM`, bounded wait, escalate to `SIGKILL` — is the same pattern systemd and Docker/Kubernetes use internally to stop services and containers, just with the grace period exposed as a configuration knob.
- `kill -9` "not working" almost always means the target process is stuck in uninterruptible D-state (§33) waiting on a kernel-level I/O operation, not that the signal failed to deliver — diagnose via `ps`'s `STAT` column and fix the underlying I/O stall, not the kill command.

## 11. Related Concepts & What's Next

This section builds directly on §35's process lifecycle — a process can be interrupted by a signal at essentially any point along that lifecycle, and signals are the actual mechanism behind much of what looked like "the process just stopped" in §33 and §35's coverage of process states. It also connects back to §13's PID 1 coverage: systemd's role in propagating shutdown signals to every managed service during a system halt or reboot is this section's graceful-shutdown pattern (6) applied at the whole-system level. §37 (next) covers foreground/background job control, where Ctrl+C and Ctrl+Z are shown to be nothing more than the terminal driver translating keystrokes into exactly the signals covered here (`SIGINT`, `SIGTSTP`). Part 9's systemd deep dive (§65–§72) revisits `SIGTERM`-then-`SIGKILL` escalation as `TimeoutStopSec` and related unit-file settings, and Part 13's containers coverage applies the same pattern again at the Docker/Kubernetes layer.

**Next Section:** §37 — `Section-37-Part5-Foreground-Background-Jobs.md`
