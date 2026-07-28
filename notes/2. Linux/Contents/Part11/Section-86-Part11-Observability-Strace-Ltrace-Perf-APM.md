# Section 86 (Part 11): Observability on Linux: Metrics, Tracing (strace, ltrace, perf), APM Concepts

## 1. Overview: Metrics, Logs, and Traces — This Section Covers Two of Three

Observability is commonly framed around three pillars: **metrics** (numeric time-series measurements — the CPU/memory/disk/network figures §81–§84 pulled from `top`, `vmstat`, `iostat`, `sar`, and friends), **logs** (event records — §85's rsyslog/journald territory, just covered), and **traces** (the path a single request or operation takes through a system, including how long each step took). §81–§85 have already covered metrics and logs in depth; this section covers OS-level **tracing tooling** — `strace`, `ltrace`, `perf` — and closes with where **APM** sits relative to everything the OS itself can observe.

The throughline across `strace`, `ltrace`, and `perf` is a shift from "what happened" (logs) or "how loaded is the system" (metrics) to **"what is this specific process actually doing, right now, at the syscall or instruction level"** — a fundamentally different and much finer-grained question, reached for when the coarser tools already covered in this Part don't explain a hang, a crash, or an unexplained CPU/latency profile.

> 💡 **Tip:** Reach for these tools in the order the question demands, not habitually starting with the heaviest one. "Is the system under CPU/memory/disk/network pressure" is §81–§84's job. "What is this one process doing at the syscall level" is `strace`'s job. "Which function is burning CPU cycles" is `perf`'s job. Jumping straight to `strace` or `perf` on a problem that a `top`/`vmstat` glance would have explained is wasted effort in exactly the way §87's methodology warns against.

## 2. `strace`: Syscall-Level Tracing

**Purpose:** `strace` intercepts and prints every system call a process makes — the kernel-boundary crossings §11 (Part 2, system calls) introduced conceptually — along with its arguments and return value, in real time. It is the single most direct way to answer "what is this program actually doing" when normal debugging (logs, error messages, application-level tools) doesn't explain a hang, a crash, or unexpected behavior.

**Syntax and key flags:**

```bash
strace [options] -p <pid>       # attach to an already-running process
strace [options] <command>      # launch and trace a new process
```

| Flag             | Meaning                                                                                                                                                                      |
| ---------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-p <pid>`       | Attach to an already-running process by PID, rather than launching a new one                                                                                                 |
| `-c`             | Summary mode — instead of printing every call live, accumulate and report a count/time/error summary per syscall when the traced process exits (or `strace` is detached)     |
| `-e trace=<set>` | Filter to a specific syscall or category (`-e trace=open,read,write`, or a group like `-e trace=network`, `-e trace=file`) rather than the full, often overwhelming firehose |
| `-f`             | Follow forked child processes too, tracing the whole process tree rather than just the one PID                                                                               |
| `-T`             | Show the time spent in each syscall — useful for spotting one specific call that's unexpectedly slow                                                                         |
| `-o <file>`      | Write trace output to a file instead of stderr, useful when the volume is large or the target process's own output would interleave confusingly                              |

**Example usage and expected output:**

```bash
# Attach to a running, unresponsive process and see what it's doing right now
$ strace -p 4821
strace: Process 4821 attached
read(7, "SELECT * FROM orders WHERE...", 8192) = -1 EAGAIN (Resource temporarily unavailable)
epoll_wait(3, [], 10, 5000)             = 0
epoll_wait(3, [], 10, 5000)             = 0

# Summarize what syscalls a short-lived command spends its time on
$ strace -c curl -s https://example.com > /dev/null
% time     seconds  usecs/call     calls    errors syscall
------ ----------- ----------- --------- --------- ----------------
 42.11    0.000812          29        28           mmap
 18.30    0.000353          12        29           read
  ...
```

The first example is the archetypal "process is stuck, why" investigation: attaching live shows the process repeatedly polling a socket and getting nothing back — evidence pointing at a downstream dependency (a database connection, per the fragment shown) rather than a bug in the traced process itself, without needing any application-level instrumentation or a single added log line.

**Why this matters as a last-resort technique:** When logs are silent, the process shows no obvious error, and standard debugging has run out of ideas, `strace` answers the question at the one layer that can't lie or omit anything — every interaction the process has with the kernel (file I/O, network I/O, memory mapping, process/thread creation, signal handling) passes through a syscall, so tracing them exhaustively captures ground truth about the process's actual behavior, independent of whether the application bothered to log any of it.

**Common errors:**

- Running `strace` unfiltered on a busy or high-throughput process and getting an unreadable firehose — reach for `-e trace=` or `-c` first, the same "don't start with the raw firehose" discipline §68 emphasized for `journalctl`.
- Attaching to a process the invoking user doesn't own (or without sufficient privilege/ptrace permissions) and getting an `EPERM` — `strace -p` generally needs root or the same UID as the target, and some hardened environments restrict `ptrace` further via `kernel.yama.ptrace_scope` (§89, Part 12 covers kernel security parameters).

**Troubleshooting:** If attaching briefly pauses or visibly slows the target process, that's expected, not a bug in `strace` — see the overhead caveat below.

> ⚠️ **Warning:** `strace` adds real, sometimes substantial overhead — every syscall now involves an extra context switch and inspection step, which can measurably slow a syscall-heavy process, and in latency-sensitive production workloads that slowdown can itself become the incident. Use it for targeted, time-boxed investigation on a specific process, not as a continuous production monitoring tool — reach for `-c` mode or `-e trace=` filtering to limit both the output volume and the overhead window, and detach as soon as the needed information is captured.

## 3. `ltrace`: Library-Call-Level Tracing

`ltrace` is `strace`'s conceptual cousin one layer up the stack: instead of tracing **kernel syscalls**, it traces calls into **shared libraries** — `malloc()`, `strcpy()`, calls into a dynamically linked library a program depends on, rather than `read()`/`write()`/`open()` at the kernel boundary.

**When it's useful:** diagnosing a suspected issue inside library-level behavior — a crash that looks related to a specific library function, or wanting to see the arguments passed into library calls a program makes — rather than kernel-boundary I/O, which is `strace`'s territory.

**Syntax mirrors `strace` closely:**

```bash
ltrace -p <pid>
ltrace <command>
```

**An honest caveat worth stating plainly:** `ltrace` is used far less often than `strace` in modern practice, and it is less reliably maintained on some current systems — certain distributions ship it in a degraded or unsupported state, and it can behave inconsistently with statically linked binaries or certain optimization/security hardening flags. Know it exists and what question it answers (library calls, not syscalls), but don't expect the same rock-solid reliability `strace` provides — verify it actually works as expected on a given system before depending on it during a live investigation, rather than assuming parity with `strace`.

## 4. `perf`: Hardware-Counter-Based Profiling

**Purpose:** `perf` is the Linux profiling tool built on **hardware performance counters** — CPU-level facilities that count events like instructions retired, cache misses, and branch mispredictions — and on top of that, statistical sampling of where a program's execution actually spends its time. Where `strace` answers "which syscalls is this process making," `perf` answers a different question: **"which function or code path is actually burning CPU cycles."**

**Key subcommands:**

| Subcommand    | Purpose                                                                                                                                                                                                      |
| ------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `perf top`    | A live, continuously updating view of the hottest functions system-wide or per-process right now — the `perf` equivalent of `top`'s live refresh, but for CPU-hotspot code paths rather than whole processes |
| `perf record` | Capture a profile over a time window (or for the duration of a specific command) to a data file for later analysis                                                                                           |
| `perf report` | Analyze a file captured by `perf record`, presenting a breakdown of where time was spent, typically as a call-graph-annotated function list                                                                  |
| `perf stat`   | Run a command and report aggregate hardware-counter statistics (instructions, cycles, cache misses, context switches) for the whole run, without full sampling detail                                        |

**Example usage:**

```bash
# Live CPU hotspot view, system-wide
$ perf top

# Capture a 30-second profile of a specific process, then analyze it
$ perf record -p 4821 -- sleep 30
$ perf report
```

`perf report`'s output is typically a ranked list of functions by percentage of samples landed in them, often with the ability to drill into a call graph showing what called what — the tool for answering "this service is pegging a CPU core, which function in it is actually responsible" in a way that `top`'s process-level percentage (§81, prior this Part) can't, since `top` only tells you _which process_, not _which line of code inside it_.

**Positioning `perf` against `strace`:** these are not competing tools for the same job — a process can be spending 100% of a CPU core in pure computation with essentially no syscalls at all (a tight numeric loop, for instance), in which case `strace` would show almost nothing interesting while `perf top`/`perf record` would immediately identify the hot function. Conversely, a process that's mostly idle, blocked waiting on I/O, shows little of interest to `perf`'s CPU-cycle sampling but everything of interest to `strace`. Choosing between them is choosing which question the symptom actually points toward — CPU-bound compute versus syscall/I/O-bound waiting.

## 5. APM (Application Performance Monitoring): A Layer Above

**APM** — Application Performance Monitoring — is application-level, code-instrumented observability: distributed tracing across service boundaries (following one logical request as it hops from a load balancer, into service A, out to a database, into service B, and back), request-level latency breakdowns (how much of a request's total time was spent in each downstream call), and code-level error tracking tied to specific application transactions.

This is explicitly a **layer above** everything covered in 2–4. `strace`, `ltrace`, and `perf` all observe a process from the **outside**, at the OS/kernel boundary or via hardware counters — they see syscalls, library calls, and CPU cycles, but they have no concept of "this is request ID 8842's third downstream call" or "this span belongs to the checkout service's payment step." That kind of request-scoped, cross-service context only exists because the application itself was instrumented to create and propagate it (trace IDs threaded through HTTP headers or message metadata, span timing recorded by an APM agent or library embedded in the application code).

The practical distinction worth internalizing: OS-level tools in this section can tell you a process is slow and even which syscall or function is consuming the time, but they cannot tell you _which specific business request_ was affected or _which downstream service_ in a distributed call chain introduced the latency — that requires instrumentation these tools don't and can't provide, which is exactly what APM tooling (and the broader observability tooling landscape — distributed tracing systems, APM vendors, OpenTelemetry-style instrumentation standards) exists to add on top.

## 6. Hands-On: Diagnosing an Unresponsive Process With strace and perf Together

**Purpose:** Walk through the practical sequence of reaching for `strace` and `perf` in combination when a process is reported "hung" and neither the application's own logs nor §81's process-level tools (`top`, `ps`) explain why — a realistic composite of the guidance in 2 and 4.

```bash
# Step 1: confirm which state the process is actually in (§33/§34, Part 5)
ps -o pid,stat,%cpu,%mem,cmd -p <pid>

# Step 2: if it's not obviously CPU-bound (stat shows R with high %CPU), check syscalls first
strace -p <pid> -f -T

# Step 3: if strace shows the process rapidly making syscalls with little wait time,
# suspect a CPU-bound hot loop instead and switch tools
perf top -p <pid>

# Step 4: capture a short profile for offline analysis if perf top identifies a hotspot
perf record -p <pid> -- sleep 15
perf report
```

**Expected output:** `ps`'s `STAT` column narrows the investigation immediately — `D` (uninterruptible sleep, usually I/O) or `S` (sleeping, usually waiting on something) points toward `strace` as the next step, while `R` (running) with high `%CPU` points toward `perf` instead. `strace -T` additionally shows per-call timing, so a process blocked in a single slow syscall (a stalled `read()` on a socket, for instance) is visible directly as one call taking far longer than the rest.

**Production usage example:** During an on-call page for "service X is unresponsive," this sequence turns an ambiguous report into a concrete classification — I/O-blocked vs. CPU-pegged — within a couple of minutes, which then determines whether the next step is investigating a downstream dependency (I/O-blocked) or looking for an inefficient code path (CPU-pegged), rather than guessing at both simultaneously.

**Common errors:** Reaching for `perf` first on a process that's actually blocked on I/O — `perf top` on an idle-waiting process shows almost nothing useful, since there's no CPU activity to sample, which can waste time before falling back to `strace`.

**Troubleshooting:** If `strace -p` reports permission denied, confirm the invoking user matches the target process's owner (or use `sudo`), and check `kernel.yama.ptrace_scope` (§89, Part 12) if attaching is unexpectedly restricted even with adequate privilege.

## 7. Common Misconceptions

1. **"`strace` and `perf` do basically the same job."** They answer different questions from different vantage points — `strace` shows kernel syscall interactions (I/O-bound, blocking behavior), `perf` shows where CPU cycles are actually spent (compute-bound behavior). A process can be uninteresting to one and highly informative under the other, depending on whether its bottleneck is I/O or computation (4).
2. **"`strace` is safe to leave running in production continuously."** It adds real, sometimes significant per-syscall overhead — appropriate for a targeted, time-boxed investigation, not continuous monitoring (2's Warning).
3. **"`ltrace` is just `strace` for library calls, equally reliable."** It answers a related but distinct question (library calls vs. syscalls) and is honestly less consistently maintained on modern systems — worth knowing it exists, not worth assuming parity with `strace`'s reliability (3).
4. **"APM replaces the need for OS-level tools like `strace`/`perf`."** They operate at different layers and answer different questions — APM gives request-scoped, cross-service context that OS tools structurally cannot see, but OS tools can still show exactly what a single process is doing at the syscall or CPU-cycle level in ways an APM agent alone won't reveal (5).

## 8. Tiered Interview Questions

**🎯 Beginner:** _"What does `strace` actually show you, and when would you reach for it?"_
**Model answer:** `strace` shows every system call a process makes — file I/O, network I/O, memory operations, process/signal handling — along with arguments and return values, either live by attaching with `-p` or from the start of a new command. I'd reach for it when a process is hanging, crashing, or behaving unexpectedly and normal debugging (logs, application behavior) hasn't explained why — it shows ground-truth kernel-boundary activity regardless of whether the application logged anything about it.
_What the interviewer is probing for:_ Correctly identifying it as a syscall-level, last-resort diagnostic tool rather than a general-purpose one.

**🎯 Intermediate:** _"A service is pegging a CPU core but its logs show nothing unusual and it's making very few syscalls. What tool do you reach for, and why not `strace`?"_
**Model answer:** `perf` — specifically `perf top` for a live view or `perf record`/`perf report` to capture and analyze a profile. `strace` traces syscalls, and a CPU-bound process doing heavy in-process computation with few syscalls simply won't show much of interest there — the bottleneck isn't at the kernel boundary, it's inside the process's own code. `perf`'s hardware-counter-based sampling identifies which function is actually consuming the CPU cycles, which is the right question for a compute-bound symptom, whereas `strace` is the right tool for an I/O/syscall-bound symptom.
_What the interviewer is probing for:_ Correctly matching the symptom (CPU-bound vs. I/O-bound) to the right tool rather than defaulting to `strace` out of habit.

**🎯 Senior:** _"How would you use `strace -c` versus a live `strace -p` attach differently during an investigation?"_
**Model answer:** `strace -c` accumulates a summary — call counts, time spent, error counts per syscall — over the traced run and reports it at the end, which is better for understanding a process's overall syscall behavior pattern (e.g., "this process makes an enormous number of small `read()` calls" or "a large fraction of time is in `futex`, suggesting lock contention") without wading through a live firehose. A live `-p` attach with full output is better when I need to see the exact sequence and timing of calls right as something is happening — catching a hang in the act, watching what a process does immediately before it crashes, or correlating specific call arguments (a file path, a socket address) with what's actually going wrong. I'd typically start with `-c` to get an aggregate shape of the problem, then switch to a live, possibly `-e trace=`-filtered attach to look at the specific sequence once I have a hypothesis about which syscalls matter.
_What the interviewer is probing for:_ Practical fluency with both modes and a sense of which is the right first move for aggregate-pattern versus in-the-moment investigation.

**🎯 Architect:** _"Where do OS-level tools like `strace`/`perf` fit relative to an APM platform in your organization's overall observability strategy?"_
**Model answer:** They're complementary layers, not alternatives. APM gives request-scoped, cross-service visibility — which service in a distributed call chain introduced latency, what a specific slow request's timeline looked like — because it's instrumented at the application level with propagated trace context, something OS-level tools structurally can't see since they have no concept of a logical request. But APM instrumentation stops at the boundary of what the application chose to instrument — if a specific host or process is behaving strangely in a way the APM agent's spans don't explain (unexpected CPU burn inside a function the instrumentation doesn't cover, a process stuck on a syscall the APM layer never sees), `strace`/`perf` are what let an engineer drop down to ground truth at that host. I'd want both available: APM as the default lens for "where in this distributed request did the time go," and `strace`/`perf`/`ltrace` as the escalation path for "the APM data doesn't explain this, what is this specific process actually doing at the OS level" — treating them as different altitudes of the same observability stack rather than competing tools.
_What the interviewer is probing for:_ Clear layered thinking about observability altitude — application-instrumented vs. OS-level — and knowing when to escalate from one to the other.

## 9. Key Takeaways

- The three observability pillars are metrics (§81–§84), logs (§85), and traces — this section covers OS-level tracing tooling, the practical instrument for the traces pillar at the host/process level.
- `strace` traces kernel syscalls a process makes (`-p` to attach, `-c` for a summary, `-e trace=` to filter) — the ultimate "what is this program actually doing" tool, but with real overhead that makes it unsuitable for continuous production use (2).
- `ltrace` traces shared-library calls rather than syscalls — a less commonly needed, less consistently maintained cousin of `strace`, worth knowing exists rather than relying on routinely (3).
- `perf` profiles CPU usage via hardware performance counters (`perf top` live, `perf record`/`perf report` for captured analysis) — the tool for "which function is burning CPU" as distinct from `strace`'s "which syscalls is this making" (4).
- APM is application-instrumented, request-scoped observability — distributed tracing, per-request latency breakdowns — a layer structurally above what any OS-level tool in this section can see, since it requires instrumentation these tools don't provide (5).

## 10. Related Concepts & What's Next

This section builds on §33/§34's process fundamentals (Part 5) — `strace` reveals what a process is actually doing at the syscall level, a natural extension of understanding process states and the fork/exec lifecycle — and follows §85's logging depth as the metrics/tracing half of this Part's observability coverage. §87 (next) turns from individual tools to a structured troubleshooting methodology — the USE method and related discipline for organizing exactly the tools §81–§86 introduced into a coherent investigation process, rather than reaching for them ad hoc.

**Next Section:** §87 — `Section-87-Part11-Structured-Troubleshooting-Methodology-Runbooks.md`
