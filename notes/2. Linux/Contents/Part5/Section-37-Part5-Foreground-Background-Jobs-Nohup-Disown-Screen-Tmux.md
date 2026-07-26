# Section 37 (Part 5): Foreground/Background Jobs, nohup, disown, screen/tmux

## 1. Job Control: What the Shell Is Actually Tracking

Every command run from an interactive shell is, from the shell's perspective, a **job** — and the shell maintains a small table of jobs distinct from the kernel's process table. This distinction matters more than it looks: a **PID** is a kernel-level identifier for a process, unique system-wide and persistent regardless of which shell (if any) started it; a **job ID** is a shell-local bookkeeping number, meaningful only within that one interactive shell session, and it disappears the moment that shell exits. §36 covered signals as the kernel-level mechanism for controlling process execution; this section covers the shell-level layer built on top of that mechanism — how an interactive shell lets you move a job between running in the foreground, running in the background, and suspended, and what happens to that job once the shell itself goes away.

A job enters the shell's table the moment it's launched, and it can be in one of a few states: **running in the foreground** (the default — the shell blocks, waiting for it to finish, and the job has control of the terminal for input/output), **running in the background**, or **stopped** (suspended, not running at all, but still resident in memory).

> 💡 **Tip:** Job control is a feature of the shell itself, not a universal property of all processes — it only applies to jobs launched interactively from a shell that has job control enabled (bash and zsh do by default in interactive mode; scripts run non-interactively typically don't have it active, which is why `bg`/`fg`/`Ctrl+Z` behave oddly or not at all inside a script).

## 2. Backgrounding, Suspending, and Resuming

**Starting a job directly in the background** — appending `&` to a command hands control back to the shell immediately, without waiting for the command to finish:

```bash
$ long_running_task.sh &
[1] 4821
```

The bracketed number is the **job ID**; the number after it is the **PID**. Both refer to the same process, but they're used in different places — job control commands (`fg`, `bg`, `kill %1`) accept job IDs prefixed with `%`, while `ps`, `kill`, and everything outside this one shell session need the real PID.

**Suspending a foreground job** — `Ctrl+Z` sends `SIGTSTP` (§36) to the job currently holding the terminal, stopping it in place without terminating it:

```bash
$ long_running_task.sh
^Z
[1]+  Stopped                 long_running_task.sh
```

The process is now stopped — resident in memory, holding whatever resources it had, but consuming no CPU and making no progress — until something resumes it.

**Resuming a stopped job in the background** — `bg` sends it `SIGCONT` (§36) and lets it continue running, but detached from the terminal's foreground:

```bash
$ bg %1
[1]+ long_running_task.sh &
```

**Bringing a job back to the foreground** — `fg` reattaches a background or stopped job to the terminal, giving it control of stdin again and making the shell block on it once more:

```bash
$ fg %1
```

**Listing all jobs known to the current shell** — `jobs` shows job IDs, state, and the command, without touching the kernel's full process table at all:

```bash
$ jobs
[1]+  Running                 long_running_task.sh &
[2]-  Stopped                 vim notes.txt
```

The `+` marks the **current job** (the default target of a bare `fg` or `bg` with no job ID); `-` marks the **previous job**, the one that would become current if the `+` job ended.

> ⚠️ **Warning:** `Ctrl+Z` suspends, it does not stop-and-resume-elsewhere — a genuinely common beginner mistake is `Ctrl+Z`-ing a job to "free up the terminal" and then closing the terminal window, assuming the job is safely backgrounded. It isn't running at all at that point (it's stopped), and closing the terminal without an explicit `bg` first can still result in it being terminated along with the session (3–4) rather than continuing.

## 3. Why a Backgrounded Job Still Dies When the Terminal Closes

Backgrounding a job with `&` or `bg` gets it off the foreground and out of the way, but it does **not** by itself protect the job from what happens when the terminal session ends. §13 (Part 2) mentioned `SIGHUP`'s historical origin in passing while surveying init systems' service-supervision gaps — this section is where that history becomes directly operational: `SIGHUP` originally signaled a literal **hangup** of a physical modem line, and on modern systems it's what the terminal (or the terminal emulator/SSH session) sends to every process attached to it when that controlling terminal goes away. A backgrounded job launched with `&` is still, by default, a member of the shell's process group and still has that terminal as its controlling terminal — so closing the terminal, logging out, or losing an SSH connection sends `SIGHUP` to it just as it would to a foreground job, and the default action for `SIGHUP` (§36) is termination.

This is the exact gap `nohup` and `disown` (4–5) exist to close, and it's also why backgrounding alone is a wholly different concern from surviving terminal exit — `&` answers "can I keep using this terminal while this runs," not "will this survive after I disconnect."

## 4. nohup: Ignoring SIGHUP Before It's Sent

**`nohup`** wraps a command so that it explicitly ignores `SIGHUP`, decided at the moment the process starts rather than negotiated afterward:

```bash
$ nohup long_running_task.sh &
[1] 5102
$ nohup: ignoring input and appending output to 'nohup.out'
```

By default, `nohup` also redirects stdout/stderr to `nohup.out` in the current directory (or appends to an existing one) — a deliberate side effect, since the terminal that would have displayed that output is exactly the thing about to disappear, and an unredirected write to a now-gone terminal would itself cause problems. Redirecting explicitly avoids depending on that default file location:

```bash
$ nohup long_running_task.sh > task.log 2>&1 &
```

**The core mechanic:** `nohup` doesn't do anything clever at runtime — it sets `SIGHUP`'s disposition to `SIG_IGN` (ignored) before `exec`-ing the target command, so when the terminal later sends `SIGHUP`, the process simply doesn't react to it, and continues running as an orphan once its parent shell exits (§35's orphan-reparenting to PID 1 is exactly what happens to it at that point).

> 💡 **Tip:** `nohup` must be applied at launch time — there's no way to retroactively make an already-running foreground or background job immune to `SIGHUP` after the fact using `nohup` itself. If you forgot to prefix a long-running command with `nohup` and it's already running, `disown` (5) is the tool for that situation, not `nohup`.

## 5. disown: Detaching an Already-Running Job From the Shell

**`disown`** solves the "I forgot to use `nohup`" problem — it removes a job from the invoking shell's job table so the shell no longer considers it one of its children to manage or signal on exit:

```bash
$ long_running_task.sh &
[1] 6234
$ disown %1
```

After `disown`, `jobs` no longer lists it, and — critically — some shells (bash, when configured with `huponexit` off, which is the common default) won't send it `SIGHUP` on shell exit in the first place, precisely because it's no longer in the table of jobs the shell believes it owns.

**`disown -h`** is the more surgical variant: it leaves the job listed in `jobs` (so you can still `fg`/`bg` it within this shell session) but marks it to be exempted from the `SIGHUP`-on-exit that would otherwise apply — useful when you want to keep managing it locally for now but still guarantee it survives if the shell ends unexpectedly.

**The real distinction from `nohup`:** `nohup` prevents the signal from having effect via the process's own signal disposition, decided at launch; `disown` prevents the shell from sending it (or from counting it as something to clean up) in the first place, decided any time after launch, entirely from the shell side. They solve the same practical problem — process survives past terminal/session exit — through different mechanisms, and either one alone is usually sufficient; using both is not typically necessary.

## 6. The Real Production Distinction: nohup/disown vs. a Terminal Multiplexer

`nohup` and `disown` solve exactly one problem: **keep a specific already-launched process alive past the shell session's end.** That's it. Once a job is `nohup`'d or `disown`'d and the terminal closes, the process runs on, but there is no shell left attached to it — no way to see its live output interactively, no way to `Ctrl+C` it, no way to pipe new input into it, nothing. You get whatever you redirected to a file, and that's the entire interface you have left.

**`screen` and `tmux`** solve a categorically different problem: **give an entire interactive terminal session persistence, independent of any one connection to it.** Conceptually, a multiplexer runs as a background server process that owns the actual pseudo-terminal (pty) your shell and any programs inside it are attached to. Your SSH client, terminal emulator, or local terminal window is just a **viewer** attaching to that server — when you disconnect, the multiplexer server keeps running, and the shell and everything inside it never lose their controlling terminal at all, because that terminal was never the physical connection to begin with. This is the key architectural difference from §3's problem: inside a multiplexer session, `SIGHUP` semantics are irrelevant to the question of survival, not merely handled — there is no hangup event reaching the inner processes when your outer connection drops, because the pty they're attached to belongs to the multiplexer, which never goes away.

**Basic `tmux` usage:**

```bash
# Start a new named session
$ tmux new -s deploy

# ... work interactively inside it, run long jobs, etc. ...

# Detach without killing anything: Ctrl+b, then d
[detached]

# Reattach later, from the same host or a fresh SSH connection
$ tmux attach -t deploy

# List all sessions currently running
$ tmux ls
deploy: 1 windows (created ...)
```

`screen` follows the same conceptual model with different keybindings (`screen -S name` to start, `Ctrl+a d` to detach, `screen -r name` to reattach) — the mental model transfers directly between the two tools even though the exact commands differ.

> ⚠️ **Warning:** A multiplexer session surviving disconnection is a feature, not a guarantee of survival through everything — the multiplexer server process itself is still an ordinary process on the host. A host reboot, an OOM kill (§36/Part 11 territory) targeting the multiplexer server, or killing it directly still takes every session inside it down at once, unlike `nohup`'d jobs which are fully independent processes with no shared point of failure between them.

## 7. Choosing the Right Tool

| Situation                                                                                                                            | Right tool                                                                                                                 |
| ------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| A quick one-off command you want to keep running after you disconnect, no further interaction needed                                 | `nohup command &` (planned ahead) or `disown %1` (already running)                                                         |
| A long-running interactive session — a build you want to watch, a debugging session, multiple panes/windows you'll want to return to | `tmux`/`screen` — you get the whole session back, not just a log file                                                      |
| A background task inside a script that shouldn't block the next command                                                              | Plain `&`, since the script's own exit behavior toward its children is usually the relevant concern, not terminal `SIGHUP` |
| Something that must keep running reliably regardless of any interactive session existing at all                                      | Neither — a proper `systemd` service unit (Part 9, §65–§72) with real supervision, not a terminal trick                    |

The last row matters operationally: `nohup`, `disown`, `screen`, and `tmux` are all fundamentally **interactive-session conveniences**. None of them restart a crashed process, none of them start automatically on boot, and none of them give you structured logging or supervision. For anything that needs to be genuinely production-durable — restarted on crash, started on boot, logged centrally — the correct tool is a systemd unit, not a terminal multiplexer session someone has to remember is still running on a specific host.

## 8. Common Misconceptions

1. **"Backgrounding a job with `&` is enough to survive logging out."** It isn't — `&` only detaches the job from the terminal's foreground while the session is alive; it does nothing about `SIGHUP` on session exit (3). `nohup`, `disown`, or a multiplexer are what actually address that.
2. **"`nohup` and `disown` do the same thing the same way."** Both achieve "survives terminal exit," but `nohup` works by making the process itself ignore `SIGHUP` from the moment it starts, while `disown` works by removing the job from the shell's own table so the shell doesn't manage or signal it — one is a property of the process, the other is a property of the shell's bookkeeping (4–5).
3. **"tmux/screen are just a fancier way to background a process, like a GUI version of nohup."** The mechanism is fundamentally different, not just more convenient — a `nohup`'d process has no terminal to return to once you're disconnected; a multiplexer session is a full interactive terminal you can reattach to and keep working in, because the pty never belonged to your connection in the first place (6).
4. **"A job ID and a PID are interchangeable."** A job ID (`%1`) is meaningful only within the one shell session that created it and vanishes when that shell exits; a PID is a global kernel identifier usable from any context, including after the originating shell is long gone (1–2).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `bg` and `nohup`?"_
**Model answer:** `bg` resumes a stopped job so it runs in the background of the current shell session — it's purely about not blocking the terminal while it runs. It does nothing to protect the job from `SIGHUP` if the terminal or session later closes. `nohup` is specifically about surviving that closure — it makes the wrapped command ignore `SIGHUP` from the moment it starts, so it keeps running even after the shell that launched it is gone. A job can be backgrounded with `bg` and still die the instant you close the terminal if it was never `nohup`'d or `disown`'d.
_What the interviewer is probing for:_ Not conflating "runs in the background" with "survives session exit" — they're independent properties.

**🎯 Intermediate:** _"You started a long job without `nohup` and now need to safely disconnect. What do you do, and why does it work?"_
**Model answer:** I'd background it if it isn't already (`Ctrl+Z` then `bg`, or it may already be running in the foreground and I background it directly), then run `disown %1` on it. That removes the job from the shell's own job table, so the shell no longer treats it as a child it needs to signal or wait on when it exits — on most shell configurations that also means it won't get sent `SIGHUP` when the session ends, since the shell isn't tracking it as something to hang up in the first place. It works after the fact, unlike `nohup`, because it's a property of the shell's bookkeeping rather than something baked into the process's own signal disposition at launch time.
_What the interviewer is probing for:_ Knowing `disown` is the retroactive fix when `nohup` wasn't used ahead of time, and understanding roughly why it works (shell-side job-table removal, not process-side signal ignoring).

**🎯 Senior:** _"Why would you choose tmux over nohup for a deployment task you're running manually?"_
**Model answer:** `nohup` gets the process to survive disconnection, but once I've disconnected I have no live interface to it at all — just whatever I redirected to a log file. If the deployment needs any judgment calls mid-flight, or I want to watch its output live, or it's actually several related steps I'm running interactively rather than one single command, `nohup` gives me none of that back. `tmux` gives me a full session I can detach from and reattach to exactly as I left it — same shell, same scrollback, same running foreground process — because the session's pty is owned by the tmux server, not by my SSH connection, so there's no `SIGHUP` boundary to cross at all. I'd reach for `nohup`/`disown` for a genuinely fire-and-forget single command, and `tmux` for anything I expect to want to check in on, intervene in, or reattach to more than once.
_What the interviewer is probing for:_ Understanding the two tool families solve different classes of problem — one-shot backgrounding vs. persistent interactive session — not just "which one is more modern."

**🎯 Architect:** _"A team is relying on tmux sessions left running on production hosts as their deployment mechanism. What's your concern, and what would you push them toward instead?"_
**Model answer:** My concern is that tmux sessions on a host are an informal, host-bound, tribal-knowledge dependency masquerading as infrastructure — the session survives disconnection, but it doesn't survive a host reboot, it isn't supervised (a crash inside it just leaves a dead pane, nothing restarts anything), it isn't discoverable by anyone who doesn't already know which host and session name to check, and it has zero centralized logging beyond whatever's in that pty's scrollback. It's a fine interactive convenience but a poor durability guarantee for anything the business actually depends on running. I'd push toward treating any process that genuinely needs to keep running as a `systemd` unit (Part 9) with an explicit restart policy, proper `journald`-integrated logging, and boot-time enablement if appropriate — and reserve tmux/screen for what they're actually good at: a human's live interactive session, debugging, or a task explicitly meant to be watched and intervened on, not as a substitute for process supervision.
_What the interviewer is probing for:_ Recognizing that terminal-persistence tools are an interactive-operator convenience, not a substitute for real service supervision, and being able to name the correct production alternative concretely.

## 10. Key Takeaways

- Job control is shell-local: job IDs (`%1`) only mean something inside the shell session that created them, while PIDs are global kernel identifiers usable anywhere — `jobs`, `fg`, `bg`, and `Ctrl+Z` operate on the shell's own job table, not directly on the kernel's process table.
- `&` backgrounds a job, `Ctrl+Z` suspends the foreground job (sending `SIGTSTP`, §36), `bg` resumes a stopped job in the background, `fg` brings a job back to the foreground — none of these by themselves protect a job from `SIGHUP` when the session ends.
- `SIGHUP`'s original meaning — a literal modem hangup, per §13's brief historical mention — is exactly why a backgrounded-but-not-`nohup`'d job dies when its terminal or SSH session closes: the terminal sends `SIGHUP` to every attached process, and the default action is termination (§36).
- `nohup` sets `SIGHUP` to be ignored at launch time (a process-side signal disposition); `disown` removes an already-running job from the shell's job table after the fact (a shell-side bookkeeping change) — either is usually sufficient on its own to survive session exit.
- `screen`/`tmux` solve a different, larger problem than either: a persistent, reattachable interactive session where the inner shell's pty is owned by the multiplexer server rather than the outer connection, so `SIGHUP` semantics never come into play at all — not handled, simply irrelevant.
- Use `nohup`/`disown` for quick one-off background tasks with no further interaction needed; use `tmux`/`screen` for long-running interactive work you'll want to reattach to; use a real `systemd` unit (Part 9) for anything that genuinely needs supervision, crash recovery, or boot-time durability — none of the terminal-level tools in this section provide that.

## 11. Related Concepts & What's Next

This section builds directly on §36's signal coverage — `Ctrl+Z` sending `SIGTSTP`, `Ctrl+C` sending `SIGINT`, and `SIGHUP`'s role in the terminal-close scenario that motivates `nohup` and `disown` entirely — and on §13 (Part 2)'s brief historical framing of `SIGHUP` as a literal modem-hangup signal, which is the origin story behind why terminal disconnection kills backgrounded processes by default. Backgrounding a job still involves the same `fork()` mechanics §35 covered for any child process — nothing about `&`, `bg`, or a multiplexer session changes how the child process comes into existence, only what happens to it afterward. §37 (next) moves to process priority — `nice` and `renice` — a separate axis of process management concerned with CPU scheduling weight rather than foreground/background/session-survival state.

**Next Section:** §38 — `Section-38-Part5-Process-Priority-Nice-Renice.md`
