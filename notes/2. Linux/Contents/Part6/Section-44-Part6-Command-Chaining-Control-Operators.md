# Section 44 (Part 6): Command Chaining and Control Operators (&&, ||, ;)

## 1. The Foundation: Every Command Returns an Exit Code

§43 covered redirection and pipes — wiring file descriptors so data flows between commands and files. This section covers a different kind of wiring: deciding **whether** a command runs at all, based on whether the previous one succeeded or failed. That decision is only possible because every command that finishes on Linux — every single one, without exception — leaves behind a small integer called an **exit code** (also called an exit status or return code).

The convention, universal across the entire ecosystem, is simple:

- **`0`** means success.
- **Any non-zero value (1–255)** means failure, and different non-zero values conventionally mean different kinds of failure (a specific tool might use `1` for a generic error and `2` for a usage error, for instance, though this isn't kernel-enforced).

The shell exposes the most recently completed foreground command's exit code through the special variable **`$?`**:

```bash
$ grep "root" /etc/passwd
root:x:0:0:root:/root:/bin/bash
$ echo $?
0

$ grep "nonexistent-user" /etc/passwd
$ echo $?
1
```

Nothing in this section works without that concept — `&&`, `||`, and even `;` in more subtle ways are all just different policies for what to do with a command's exit code once it's known. **Full depth on exit codes** — conventions across tools, `exit` in scripts, checking `$?` deliberately, propagating a script's own exit code to its caller — is §45's job; this section needs only the concept above to make sense of the operators that follow.

> 💡 **Tip:** "Success" and "failure" here are about the process's own exit code, not about whether it produced output you expected. `grep` that finds zero matches exits `1` — that's success at the mechanical task of searching, encoded as "no match found" by convention, not a crash. Don't conflate "ran without error" with "did what I wanted."

## 2. `;` — Sequential, Unconditional Execution

The semicolon is the simplest control operator: it just separates commands, telling the shell to run one after another **regardless of whether the first one succeeded or failed**.

```bash
$ echo "first"; false; echo "third"
first
third
```

`false` is a trivial built-in that does nothing except exit with status `1` — included here purely to prove the point. Despite `false` failing, `echo "third"` still ran. `;` carries no information from one command's outcome to the next; it's functionally equivalent to writing each command on its own line and running the script straight through.

This is the right tool when commands are genuinely independent and you want all of them attempted no matter what — for example, a cleanup step that should always run even if an earlier check failed, chained inline rather than as separate lines:

```bash
$ cd /tmp; ls -la; df -h .
```

## 3. `&&` — Run Only If the Previous Command Succeeded

`&&` is a **short-circuit AND**: the right-hand command runs only if the left-hand command exited `0`.

```bash
$ mkdir /tmp/newdir && echo "created successfully"
created successfully

$ mkdir /tmp/newdir && echo "created successfully"
mkdir: cannot create directory '/tmp/newdir': File exists
$
```

The second run produces no `echo` output at all — `mkdir` failed (the directory already existed, non-zero exit), so the `echo` after `&&` never executes. This is the pattern behind the extremely common idiom of chaining a sequence of steps that only make sense if every prior step worked:

```bash
$ ./configure && make && make install
```

Each stage depends on the previous one having actually succeeded — running `make` against a failed `./configure` would just produce a confusing downstream error instead of a clear, early stop.

## 4. `||` — Run Only If the Previous Command Failed

`||` is the mirror image: a **short-circuit OR**. The right-hand command runs only if the left-hand command exited **non-zero**.

```bash
$ grep "web-server" /etc/hostname || echo "hostname does not match"
hostname does not match
```

The most common real-world use is a fallback or an error-reporting path — do this, but if it fails, do that instead:

```bash
$ ping -c 1 8.8.8.8 || echo "network appears to be down"
```

`||` is also how scripts commonly bail out cleanly on a failed step, using `exit` (§45 covers `exit` and exit-code semantics inside scripts in full) to stop the script rather than letting it barrel forward on a bad foundation:

```bash
$ cd /some/required/directory || exit 1
```

If the `cd` fails — the directory doesn't exist, permissions are wrong — the script exits immediately with status `1` rather than continuing to run every subsequent command from the wrong working directory, which is a classic and dangerous class of bug when it goes unnoticed.

## 5. Combining `&&` and `||` in Real One-Liners

These operators chain together freely, and the combination is where they earn their keep in day-to-day shell use. A very common production pattern:

```bash
$ mkdir -p dir && cd dir || exit 1
```

Read left to right: create the directory (and any missing parents, `-p`); if that succeeded, `cd` into it; if _either_ of those two steps failed, exit the script with status `1`. This single line encodes "do these two things in order, and bail out immediately if anything goes wrong" — a much more compact expression of the same intent as a multi-line `if` block, useful in ad hoc one-liners and short scripts alike (§46 covers the `if`/`else` alternative when the logic gets complex enough to need it).

Another common shape checks a condition and reacts either way:

```bash
$ systemctl is-active --quiet nginx && echo "nginx is running" || echo "nginx is NOT running"
```

## 6. The Precedence Gotcha: `&&` / `||` Is Not a Ternary

The one-liner in 5 looks, at a glance, like an if/else: "do X, and if X fails do Y." That reading is correct only because the specific example was carefully constructed. It breaks down the moment the **fallback command can itself fail**.

> ⚠️ **Warning:** `cmd1 && cmd2 || cmd3` does **not** mean "if cmd1 succeeds run cmd2, otherwise run cmd3" in the strict, mutually-exclusive sense a ternary operator implies. It means: run `cmd2` if `cmd1` succeeded; then run `cmd3` if the **most recently evaluated command in the chain** failed — and if `cmd2` itself fails, `cmd3` runs too, even though `cmd1` succeeded. The "else" branch isn't gated on `cmd1` failing; it's gated on the chain's running total not yet having produced a success.
>
> ```bash
> $ true && false || echo "this prints, and it's misleading"
> this prints, and it's misleading
> ```
>
> Here `true` succeeds, so `false` runs (per `&&`) — and `false` fails, so `echo` also runs (per `||`), even though the first command in the chain never failed. Anyone reading this as "if true then false else echo" would wrongly conclude the `echo` branch only fires when `true` fails; it actually fires whenever the chain's last executed command failed, which `false` guaranteed here regardless of what came before it.

The safe, unambiguous way to express genuine if/else logic is the real `if`/`else` construct (§46) once either branch could plausibly fail — reserve `&&`/`||` chaining for cases like §5's `mkdir -p dir && cd dir || exit 1`, where the fallback (`exit 1`) cannot itself fail in a way that matters.

## 7. Background Execution `&` as a Control Operator

A single trailing `&` is technically a control operator too, though it controls _when_ a command's output rejoins the shell rather than _whether_ the next command runs based on an exit code — it launches the command as a **background job** and returns control to the shell immediately, without waiting for it to finish:

```bash
$ long-running-backup.sh &
[1] 8842
```

The shell prints a job number and PID and gives the prompt straight back; the script keeps running detached from the interactive foreground. This is a brief tie-back rather than new depth — §37 (job control: `jobs`, `fg`, `bg`, `nohup`, `disown`) is where managing what happens to backgrounded and detached processes is covered properly. The relevant point for this section is narrower: `&` sits in the same syntactic family as `;`, `&&`, and `||` — all four are ways of telling the shell how one command relates to the next in a single line — even though only `&` changes _timing_ rather than _conditional execution_.

## 8. Grouping Commands: `()` Subshell vs. `{}` Current Shell

Both `&&` and `||` bind to individual commands by default, but sometimes a whole group of commands needs to be treated as one unit against a condition. Two syntaxes group commands, and they are not interchangeable:

```bash
$ (cd /tmp && touch scratchfile) && echo "done, but still in original directory"

$ { cd /tmp && touch scratchfile; } && echo "done, and now IN /tmp"
```

- **`( ... )`** runs the enclosed commands in a **subshell** — a forked child shell (§34's fork model) with its own copy of the environment. A `cd` inside `()` does not affect the parent shell's working directory; once the subshell exits, the parent is exactly where it started.
- **`{ ... }`** runs the enclosed commands in the **current shell**, no fork involved — a `cd` inside `{}` genuinely changes the parent shell's working directory. Note the syntactic quirks: `{}` needs a space after `{` and a semicolon (or newline) before the closing `}`, unlike `()`.

Reach for `()` when isolation is the goal (temporarily changing directory or environment variables without affecting the calling shell); reach for `{}` when you specifically need the group's side effects — like a `cd` — to persist.

## 9. Common Misconceptions

1. **"`||` means 'or' in the boolean-logic sense, evaluating both sides."** It's a short-circuit operator — the right-hand side only runs at all if the left-hand side failed. If the left-hand command succeeds, the right-hand command never executes, isn't evaluated, and has no effect on anything (3).
2. **"`cmd1 && cmd2 || cmd3` is a safe if/else."** As 6 demonstrates, it isn't — if `cmd2` fails after `cmd1` succeeded, `cmd3` still runs, which is not what if/else semantics would produce. It's safe only when the "else" branch cannot itself fail in a way that matters.
3. **"`;` checks whether the previous command succeeded, like a milder `&&`."** It checks nothing — `;` is purely sequential and unconditional. The command after `;` runs whether the command before it succeeded, failed, or crashed outright (2).
4. **"A subshell `()` and a `{}` group are just cosmetic syntax differences."** They have materially different scope — `()` forks a child process with its own environment copy, so changes like `cd` or variable assignments inside it vanish when it exits; `{}` runs in the calling shell directly, so the same changes persist (8).

## 10. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between `cmd1 ; cmd2` and `cmd1 && cmd2`?"_
**Model answer:** `;` runs `cmd2` unconditionally, regardless of whether `cmd1` succeeded or failed — it's just sequencing, with no information passed between the two commands. `&&` only runs `cmd2` if `cmd1` exited with status `0` (success); if `cmd1` fails, `cmd2` is skipped entirely. Both rely on the fact that every command produces an exit code when it finishes, which the shell can inspect via `$?` — `;` simply ignores that code, `&&` acts on it.
_What the interviewer is probing for:_ Basic grasp that exit codes are the underlying mechanism, not just memorized syntax.

**🎯 Intermediate:** _"Why does `mkdir -p dir && cd dir || exit 1` work well as a one-liner, and when would that same && / || pattern become unsafe?"_
**Model answer:** It works well here because the fallback, `exit 1`, is a shell builtin that essentially cannot fail in a way that matters — so `||` reliably means "if either the mkdir or the cd failed, bail out." It becomes unsafe the moment the command after `&&` can itself fail independently of the first command, because `||`'s trigger condition is "the most recently executed command in the chain failed," not "the first command failed." If I wrote `cmd1 && cmd2 || cmd3` and `cmd2` could fail even when `cmd1` succeeds, `cmd3` would run in that case too — which usually isn't the intended "else" behavior. Once that risk is real, I'd switch to an explicit `if`/`else` block instead of relying on chained short-circuit operators to approximate one.
_What the interviewer is probing for:_ Recognizing that the safety of this pattern is situational, not a property of the operators themselves — and knowing when to escalate to a real control structure.

**🎯 Senior:** _"Walk through exactly what happens, step by step, in `true && false || echo done` — and explain why a developer might misread it."_
**Model answer:** The shell evaluates left to right, tracking the most recently run command's exit status at each step. `true` runs first and exits `0`. Because of `&&`, `false` then runs — it exits `1`. Now `||` looks at the most recent exit status, which is `1` (from `false`), not `0` (from `true`) — so `echo done` runs. The output is `done`. A developer misreads this as if/else because the surface syntax resembles a ternary — "condition && then-branch || else-branch" — but the actual semantics are two independent short-circuit checks chained together, each looking only at the exit status immediately to its left, with no memory of what happened further back in the chain. The `false` in the middle "resets" the condition that `||` reacts to, which is exactly the trap: the else-branch fires based on the immediately preceding command, not the original condition.
_What the interviewer is probing for:_ Precise, step-by-step exit-code tracing rather than a hand-wavy "it's not really if/else" answer — this is the section's core gotcha and the interviewer wants to see it actually traced through.

**🎯 Architect:** _"You're reviewing a deploy script full of chained `&&` and `||` one-liners with no `if` blocks at all. What do you look for, and when do you push back on that style?"_
**Model answer:** I'd trace each chain the way I just did for `true && false || echo done` — for every `||` fallback, I'd ask "can the command immediately to its left fail for a reason other than the condition the author actually cares about?" Anywhere the answer is yes, that's a latent bug: the fallback will fire under conditions the author didn't intend, and worse, it'll usually look correct in casual testing because the common-case failure mode matches the intended one. I'd also check whether any chain silently swallows a real failure — for instance `step1 && step2` with no trailing `|| exit 1`, where a failed `step1` just causes `step2` to be skipped without the script itself reporting failure to its caller (its own exit code might still read `0` depending on what runs last). Chained operators are fine, and often clearer than a bloated if-block, for short, single-condition guards like `cd dir || exit 1` where the fallback truly can't fail in a confusing way. Once a chain has more than two operators or any step whose failure mode is ambiguous, I'd push for an explicit `if`/`else` (§46) precisely because deploy scripts are exactly the place where a silently-wrong fallback is expensive to discover.
_What the interviewer is probing for:_ Applying the precedence gotcha as a real code-review lens, not just as a party-trick example — and judgment about where terse chaining is appropriate versus where it's a liability in production automation.

## 11. Key Takeaways

- Every command leaves an exit code — `0` for success, non-zero for failure — inspectable via `$?`; this is the mechanism every operator in this section acts on (full depth: §45).
- `;` sequences commands unconditionally, ignoring exit codes entirely.
- `&&` runs the next command only if the previous one succeeded (short-circuit AND); `||` runs the next command only if the previous one failed (short-circuit OR).
- `cmd1 && cmd2 || cmd3` is not a safe if/else — if `cmd2` also fails, `cmd3` runs too, because `||` reacts to the most recently executed command's exit status, not to whether `cmd1` specifically failed. Use `if`/`else` (§46) once either branch can plausibly fail.
- `&` backgrounds a command and returns the prompt immediately — a control operator about timing rather than conditional execution; full job-control depth is §37.
- `()` groups commands in a forked subshell (changes like `cd` don't persist to the parent); `{}` groups commands in the current shell (changes do persist) — pick based on whether isolation or persistence of side effects is the goal.

## 12. Related Concepts & What's Next

This section builds directly on §43's redirection and pipe mechanics, adding conditional and sequential control on top of the data-flow wiring already covered, and leans on the exit-code concept that §45 (Bash Scripting Fundamentals) develops in full depth — shebangs, script arguments, and deliberate exit-code handling inside scripts. §46 (Control Structures: if/else, case, for, while, until) is the natural next step once chained `&&`/`||` one-liners stop being expressive enough, and it resolves the exact ambiguity flagged in 6 with real, unambiguous branching syntax. **§45 is next**, picking up the exit-code thread this section only introduced at the concept level and turning it into full scripting fluency.

**Next Section:** §45 — `Section-45-Part6-Bash-Scripting-Fundamentals.md`
