# Section 43 (Part 6): Redirection and Pipes (stdin, stdout, stderr, |, >, >>, 2>&1)

## 1. The Three Standard File Descriptors

Every process on Linux starts life with three file descriptors already open, before it has done anything itself to open a single file. §40 introduced file descriptors in passing while explaining anonymous pipes; this section starts by naming the three that exist for every process, unconditionally:

| FD  | Name                     | Default destination           |
| --- | ------------------------ | ----------------------------- |
| 0   | stdin (standard input)   | The terminal's keyboard input |
| 1   | stdout (standard output) | The terminal's display        |
| 2   | stderr (standard error)  | The terminal's display        |

A program that calls `printf("hello\n")` in C, or a shell command that writes normal output, isn't writing "to the screen" as some special built-in behavior — it's writing to file descriptor 1, and file descriptor 1 happens to be connected to the terminal by default. That's the entire idea this section builds on: **stdin, stdout, and stderr are not magic — they're just three numbered file descriptors, open by convention, that can be pointed at anything else a file descriptor can be pointed at** (a regular file, a pipe, `/dev/null`, another process's input). Redirection is nothing more than changing what these numbers point to before a program starts running.

Both stdout and stderr default to the same destination — the terminal — but they are **separate channels**. A command's normal output and its error messages are interleaved on screen only because both descriptors happen to point at the same place right now; the moment either is redirected independently (5), that interleaving stops, which is the whole reason stderr exists as a distinct descriptor rather than programs just writing errors to stdout.

> 💡 **Tip:** The `ls -l /dev/std{in,out,err}` trick is a fast way to prove this isn't abstract — on most Linux systems `/dev/stdin`, `/dev/stdout`, and `/dev/stderr` are symlinks into `/proc/self/fd/0`, `/proc/self/fd/1`, and `/proc/self/fd/2` respectively, which is the kernel's live, per-process view of exactly what each descriptor currently points to.

## 2. Output Redirection: `>` and `>>`

`>` redirects a command's stdout to a file, **overwriting** the file's existing contents (or creating it if it doesn't exist):

```bash
$ echo "first line" > out.txt
$ cat out.txt
first line
$ echo "second line" > out.txt
$ cat out.txt
second line
```

The second `echo` didn't append — it truncated `out.txt` to zero length and wrote fresh, which is the single most common redirection mistake: reaching for `>` when the intent was actually to add to a file, and silently destroying whatever was there before.

`>>` **appends** instead, opening the file in append mode rather than truncating it:

```bash
$ echo "first line" > out.txt
$ echo "second line" >> out.txt
$ cat out.txt
first line
second line
```

> ⚠️ **Warning:** `>` truncates the moment the shell opens the destination file — before the command that's supposedly generating the new content has even run. This means `sort out.txt > out.txt` is a real, common trap: the shell opens `out.txt` for writing (truncating it to empty) as part of setting up redirection, and only then execs `sort`, which now reads an already-empty file. The fix is never to redirect a command's output back into one of its own input files directly — write to a temporary file and `mv` it into place, or use a tool built for in-place editing (`sed -i`, covered in §48).

## 3. Input Redirection: `<`

`<` redirects a command's stdin to read from a file instead of the keyboard:

```bash
$ wc -l < access.log
1284
```

Note the subtle difference between `wc -l < access.log` and `wc -l access.log`: the second form passes the filename as an argument, and `wc` prints the filename alongside the count; the first form gives `wc` no filename at all — it just receives the file's bytes as its stdin stream, unaware of where they came from, and prints only the count. This distinction matters for any tool whose output format depends on knowing the filename versus not.

## 4. The Pipe (`|`): Connecting Stdout to Stdin

§40 introduced the pipe at the kernel level: a `|` between two commands creates an in-memory kernel buffer and wires the left-hand command's stdout (fd 1) to the right-hand command's stdin (fd 0), so bytes flow from one process to the other without ever touching disk. This section is the hands-on shell-level companion to that conceptual coverage — the same kernel object, now used deliberately as a daily tool.

```bash
$ ps aux | grep nginx | wc -l
3
```

Each `|` creates one pipe and starts both processes **concurrently** — `ps aux` doesn't have to finish before `grep` starts consuming its output; the two run side by side, throttled against each other by the pipe's buffer exactly as §40 described. A three-stage pipeline like the one above is really two pipes and three processes, all running at once, not a sequential batch of three separate steps.

**What flows through a pipe is only stdout, by default** — a command's stderr is _not_ connected to the next command's stdin unless explicitly redirected there (6 covers exactly this). This is why an error message from the first command in a pipeline still shows up on the terminal even while its normal output is being piped elsewhere — stdout went into the pipe, stderr stayed pointed at the terminal.

> 💡 **Tip:** A pipeline's exit status, by default, is the exit status of its _last_ command — an error from an earlier stage in the pipeline is easy to miss silently (`grep nonexistent-pattern | wc -l` exits 0, from `wc`, even though `grep` "failed" to find a match). §44 covers control operators and exit-status chaining in depth; `bash`'s `set -o pipefail` (worth knowing exists now, covered fully later) changes this default so the pipeline's exit status reflects any failing stage, not just the last one.

## 5. Redirecting Stderr: `2>` and `2>>`

Because stderr is just file descriptor 2, it redirects with the same `>`/`>>` syntax, prefixed with its number:

```bash
$ grep "pattern" /no/such/file 2> errors.log
$ cat errors.log
grep: /no/such/file: No such file or directory
```

`2>` overwrites, `2>>` appends — identical semantics to stdout's `>`/`>>`, just applied to a different descriptor. Separating stderr from stdout this way is exactly what lets a script capture normal output for processing while still letting error messages surface on the terminal (or into a separate log a monitoring pipeline watches specifically for failures):

```bash
$ backup_script.sh > backup.log 2> backup-errors.log
```

Here stdout (progress messages, say) and stderr (failures) land in two independent files, even though both started out pointing at the same terminal — each redirection only changes the one descriptor it names.

## 6. The `2>&1` Ordering Gotcha

Combining stdout and stderr into a single destination is one of the most common redirection needs — and one of the most commonly gotten wrong, because the syntax hides a left-to-right, order-dependent duplication step that isn't obvious from reading it casually.

`2>&1` means "make file descriptor 2 point at wherever file descriptor 1 currently points." The `&` before the `1` is what distinguishes this from `2>1`, which would instead try to redirect stderr into a file _literally named_ `1` — a classic typo that fails silently in the sense that it "works" (creates a file called `1`) without doing what was intended.

**The critical detail: redirections are processed left to right, and `2>&1` captures whatever fd 1 points to at that exact moment — not "wherever it eventually ends up."**

```bash
# CORRECT — stderr and stdout both go to file.log
$ command > file.log 2>&1
```

Reading this left to right as the shell does: first `> file.log` redirects fd 1 (stdout) to `file.log`. Then `2>&1` redirects fd 2 (stderr) to point at whatever fd 1 currently points to — which is now `file.log`. Both descriptors end up pointing at the same file.

```bash
# WRONG — stderr still goes to the terminal, only stdout goes to file.log
$ command 2>&1 > file.log
```

Reading this left to right: first `2>&1` redirects fd 2 (stderr) to point at whatever fd 1 currently points to — which, at this point in the command, is still the terminal (nothing has redirected stdout yet). Stderr is now pointing at the terminal, independently. Then `> file.log` redirects fd 1 (stdout) to `file.log` — but this doesn't retroactively move stderr along with it; stderr already grabbed a copy of "wherever fd 1 pointed at that moment" and keeps pointing at the terminal even after fd 1 moves on to the file.

> ⚠️ **Warning:** `2>&1` is a snapshot, not a link. It does not mean "stderr and stdout are now permanently tied together" — it means "point fd 2 at fd 1's _current_ target, right now, as a one-time copy." Everything after that point in the command line that changes fd 1 again has no effect on fd 2. This is precisely why `command > file.log 2>&1` works and `command 2>&1 > file.log` doesn't do what most people expect on first reading it — the only difference is which redirection came first, and that ordering entirely determines the outcome.

**Sending both to `/dev/null` (discarding everything) follows the same rule:**

```bash
$ command > /dev/null 2>&1
```

## 7. `&>`: Bash's Combined Shorthand

Bash (though not all POSIX-compliant shells — `sh`, dash, and strict-POSIX scripts should stick to `> file 2>&1`) provides `&>` as shorthand for redirecting both stdout and stderr to the same destination in one step, sidestepping the ordering question in 6 entirely:

```bash
$ command &> file.log
# equivalent to: command > file.log 2>&1
```

`&>>` is the append form:

```bash
$ command &>> file.log
```

Because `&>` is a bash-specific extension, scripts intended to run under `/bin/sh` or that need portability across shells should prefer the explicit `> file 2>&1` form — §41 (this Part's shell-overview section) covers which constructs are bash-only versus POSIX-portable in more depth.

## 8. Discarding Output: `/dev/null`

`/dev/null` is a special device file that silently discards anything written to it and produces immediate end-of-file when read from — the standard way to say "I don't want this output at all" rather than routing it somewhere and then ignoring the file:

```bash
$ noisy_command > /dev/null 2>&1
```

This is common in cron jobs and automation (§37's coverage of scheduling) where a command's routine chatter isn't worth capturing but genuine failures might still need surfacing some other way (an explicit exit-code check, alerting, or redirecting only stderr somewhere meaningful while discarding stdout: `command > /dev/null` alone leaves stderr on the terminal or wherever it was already headed).

> 💡 **Tip:** Reading from `/dev/null` is just as useful as writing to it — `command < /dev/null` gives a command an immediately-empty stdin, which is a reliable way to stop an interactive command from hanging while waiting for input it will never receive, particularly inside scripts or `cron` where nothing is attached to provide input at all.

## 9. `tee`: Splitting a Stream to a File and Stdout Simultaneously

Every redirection covered so far sends a stream to exactly one destination. `tee` is the tool for the common case where a stream needs to go to **both** a file and continue on to the terminal (or the next stage of a pipeline) at the same time — named for a plumbing T-joint, splitting one input into two identical outputs:

```bash
$ some_command | tee output.log
```

`some_command`'s stdout goes into the pipe; `tee` reads it, writes an identical copy to `output.log`, and _also_ writes it back out to its own stdout — which, absent further redirection, still shows on the terminal. This is why `tee` is the standard answer to "I want to watch this run in real time but also keep a log of it," rather than running the command once to watch it and a second time (possibly with different results) to capture it.

`tee -a` appends instead of overwriting, mirroring `>>` vs `>`:

```bash
$ some_command | tee -a output.log
```

`tee` can also write to multiple files at once, and can sit in the middle of a longer pipeline — the copy to the terminal doesn't have to be the end of the line:

```bash
$ build.sh | tee build.log | grep -i error
```

Here the full build output is both logged in full to `build.log` and filtered live for the word "error" on the terminal — one stream, captured completely, while a derived view of it is also produced, without running `build.sh` twice.

## 10. Here-Documents and Here-Strings

Two related constructs feed literal text into a command's stdin directly from the script, without a separate file — briefly worth knowing here even though full scripting depth is later (§45 onward).

A **here-document** (`<<`) feeds a multi-line block of text as stdin, terminated by a chosen delimiter word on its own line:

```bash
$ cat <<EOF
line one
line two
EOF
line one
line two
```

This is common for embedding multi-line SQL, config snippets, or usage/help text directly inside a shell script without an external file — `mysql < query.sql` and `mysql <<EOF ... EOF` accomplish similar things, but the here-document keeps the content inline and version-controlled alongside the script that uses it.

A **here-string** (`<<<`) is the single-line equivalent — it feeds one expression's value as stdin without needing an opening/closing delimiter pair:

```bash
$ grep "error" <<< "$log_line"
```

This is frequently a cleaner alternative to `echo "$log_line" | grep "error"` for a single variable — it avoids spawning an extra `echo` process just to get a value into a pipe, at the cost of being bash-specific rather than universally POSIX-portable (the same portability caveat as `&>` in 7).

## 11. Common Misconceptions

1. **"stdout and stderr are the same thing since they both show up on screen."** They're separate file descriptors that only _appear_ combined because both default to the same destination — the terminal. The moment either is redirected independently (5), the distinction becomes visible and matters (1).
2. **"`2>&1` permanently links stderr to stdout, so order doesn't matter."** It's a one-time copy of fd 1's _current_ target at the point it's evaluated, not a persistent link — which is exactly why `command > file 2>&1` and `command 2>&1 > file` behave differently (6).
3. **"`>` and `>>` are interchangeable as long as the file ends up with the right content eventually."** `>` truncates on open, which can destroy existing content the moment the command starts — including, disastrously, when the destination file is also an input to the same command (2).
4. **"A pipe passes everything a command produces to the next stage."** Only stdout flows through a pipe by default — stderr from an earlier stage in a pipeline still goes to its original destination (typically the terminal) unless explicitly redirected into the pipe as well (4, 5).
5. **"`tee` is just for logging, not real pipelines."** `tee` can sit in the middle of a multi-stage pipeline, not just at the end — it's a legitimate way to both capture a full stream and continue processing a filtered view of it in the same command (9).

## 12. Tiered Interview Questions

**🎯 Beginner:** _"What are file descriptors 0, 1, and 2, and where do they point by default?"_
**Model answer:** They're stdin, stdout, and stderr respectively. Every process gets all three open automatically at start, without doing anything special to open them — by default all three are connected to the controlling terminal, so a program reads keyboard input via fd 0 and writes both normal output and error messages to the screen via fd 1 and fd 2. They're not special beyond being open-by-convention numbered file descriptors — any of the three can be redirected to point somewhere else entirely, like a file or a pipe.
_What the interviewer is probing for:_ Whether the candidate understands these as ordinary file descriptors rather than some kind of built-in special-cased mechanism.

**🎯 Intermediate:** _"Explain why `command > file 2>&1` combines stdout and stderr into the file, but `command 2>&1 > file` does not."_
**Model answer:** Redirections are applied left to right, and `2>&1` means "point fd 2 at whatever fd 1 currently points to" — a one-time copy, not a persistent link. In the first form, `> file` runs first, so fd 1 already points at the file by the time `2>&1` executes, and fd 2 copies that — both end up at the file. In the second form, `2>&1` runs first, while fd 1 still points at the terminal, so fd 2 copies the terminal target; then `> file` moves fd 1 to the file afterward, but fd 2 was already fixed pointing at the terminal and isn't affected by fd 1 moving later. The fix is always to redirect stdout to its final destination first, then duplicate stderr onto it.
_What the interviewer is probing for:_ Real understanding of the left-to-right evaluation and "snapshot, not link" semantics, not memorized syntax.

**🎯 Senior:** _"A pipeline `stepA | stepB | stepC` exits 0 even though `stepA` failed partway through. Why, and how would you make the pipeline surface that failure?"_
**Model answer:** A pipeline's exit status defaults to the exit status of its last command only — `stepB` and `stepC` can both succeed even if `stepA` failed or produced partial/empty output, and nothing about the pipe mechanism itself propagates an earlier stage's failure forward. `set -o pipefail` (bash) changes this so the pipeline's exit status is the last _non-zero_ status among all stages, or zero only if every stage succeeded — that's the standard fix in scripts where any stage failing should be treated as the whole pipeline failing. It's also worth checking whether `stepA`'s errors are even visible at all — its stderr isn't part of the piped stream (only its stdout is), so if diagnostics were needed they'd have to be captured separately, e.g. redirecting `stepA`'s stderr to a log file rather than assuming it shows up wherever the pipeline's output goes.
_What the interviewer is probing for:_ Awareness that pipe exit-status semantics are a real production gotcha, not just how `|` moves bytes — and knowing the concrete fix (`pipefail`) rather than a vague "check for errors."

**🎯 Architect:** _"You're writing a script that runs a noisy third-party tool in production automation. How do you handle its output so nothing important is lost, but logs stay usable?"_
**Model answer:** I wouldn't blanket-discard everything to `/dev/null`, because that throws away exactly the diagnostic signal I'd need during an incident — but I also wouldn't let unfiltered noisy stdout pollute the operational log at full volume. I'd typically separate the streams deliberately: redirect stdout to a rotated log file for a full record (`> tool.log`), let stderr go to a separate error-specific log or straight to whatever the automation platform already captures as failure signal, and if I need to both watch progress live and retain a full transcript I'd use `tee` rather than choosing one or the other. If the tool's stdin needs to be non-interactive (common in cron or CI, §39), I'd explicitly redirect it from `/dev/null` so it can never hang waiting on input nobody's going to provide. And critically, I'd get the `2>&1` ordering right up front and verify it once by deliberately triggering both a success and a failure path in a non-production run — this is exactly the class of mistake (6) that looks correct on a quick read and only reveals itself when an actual error occurs and isn't where the runbook expects it to be.
_What the interviewer is probing for:_ Production-mindedness around log usefulness versus noise, correct handling of the ordering gotcha under real stakes, and treating stdin/stdout/stderr as three independently-designed decisions rather than one blanket "redirect everything" choice.

## 13. Key Takeaways

- Stdin (0), stdout (1), and stderr (2) are ordinary numbered file descriptors, open by default and pointed at the terminal — nothing about them is special beyond that convention, and any of the three can be redirected independently.
- `>` overwrites, `>>` appends — for both stdout and, with the `2>`/`2>>` prefix, stderr; redirecting a command's output back into one of its own input files is a truncation trap to actively avoid.
- `|` connects one process's stdout directly to the next's stdin via the same in-memory kernel pipe object §40 introduced conceptually — only stdout flows through by default, stderr does not, and both processes run concurrently rather than sequentially.
- `2>&1` copies fd 1's _current_ target onto fd 2 at the moment it's evaluated — a snapshot, not a persistent link — which is why redirection order (`> file 2>&1` vs. `2>&1 > file`) produces genuinely different results, a routinely misunderstood gotcha worth verifying deliberately rather than assuming.
- `&>`/`&>>` are bash-specific shorthand for combining stdout and stderr in one step; prefer the explicit `> file 2>&1` form for POSIX-portable scripts.
- `/dev/null` discards writes and yields immediate EOF on reads — useful both for silencing unwanted output and for giving a command a definite empty stdin so it can't hang waiting for input.
- `tee` splits a stream to a file and stdout (or the next pipeline stage) simultaneously, avoiding the need to run a command twice to both watch and capture its output.
- Here-documents (`<<EOF`) and here-strings (`<<<`) feed literal inline text as stdin without a separate file — bash-specific conveniences with the same portability caveat as `&>`.

## 14. Related Concepts & What's Next

This section is the hands-on shell-level continuation of §40's kernel-level pipe explanation (Part 5), and builds directly on §42's variable/expansion coverage — redirection targets and here-document/here-string content are frequently expanded values, not just literal filenames. §44 (next) covers command chaining and control operators (`&&`, `||`, `;`) — how multiple commands combine based on success/failure, a related but distinct question from how their input/output streams connect. §48's text-processing tools (`grep`, `sed`, `awk`) are, in practice, the most common things sitting on the receiving end of a pipe or redirected input built with the mechanics covered here.

**Next Section:** §44 — `Section-44-Part6-Command-Chaining-Control-Operators.md`
