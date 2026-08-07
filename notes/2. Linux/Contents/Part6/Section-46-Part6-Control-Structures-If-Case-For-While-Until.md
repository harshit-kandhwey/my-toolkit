# Section 46 (Part 6): Control Structures: if/else, case, for, while, until

## 1. The Core Idea: `if` Tests an Exit Code, Not a Boolean

Every mainstream language treats `if` as evaluating a boolean expression. Bash does not — this is the single most important mental adjustment for anyone arriving from another language, and it's the reason a huge amount of bash conditional syntax looks strange until this clicks. `if` in bash runs a **command** and branches on that command's **exit status** ([§44](./Section-44-Part6-Command-Chaining-Control-Operators.md), [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md) covered exit codes as the `0` = success / nonzero = failure convention):

```bash
if command; then
    echo "command succeeded (exit 0)"
else
    echo "command failed (exit nonzero)"
fi
```

There is no boolean type being evaluated here at all — `command` is executed, and `if` inspects `$?` afterward exactly the way `&&`/`||` do ([§44](./Section-44-Part6-Command-Chaining-Control-Operators.md)). This is why `if grep "pattern" file.txt; then ...` is completely ordinary bash: `grep` is the command, its exit status (`0` if it found a match, `1` if not, `2` on a real error) is what `if` branches on, no boolean conversion involved anywhere.

## 2. `[ ]` Is a Command: Why `if [ condition ]` Works

Given 1, `if [ -f "$file" ]` looks like special syntax but isn't — `[` is an actual command (historically a real binary at `/usr/bin/[`, though bash also has it as a builtin for performance), and it is simply another name for `test`. `[ -f "$file" ]` and `test -f "$file"` are the exact same invocation; the trailing `]` is itself a required argument to the `[` command, not punctuation the shell strips away. Because `[` is a command like any other, it sets an exit status — `0` if the condition holds, `1` if it doesn't — and that's the only reason `if [ condition ]` works: `if` is still just running a command and reading `$?`, the command just happens to be `[`.

Common `test`/`[` operators worth having memorized:

| Category | Operator                      | Meaning                                                                  |
| -------- | ----------------------------- | ------------------------------------------------------------------------ |
| File     | `-f`                          | Regular file exists                                                      |
| File     | `-d`                          | Directory exists                                                         |
| File     | `-e`                          | Path exists (any type)                                                   |
| File     | `-r` / `-w` / `-x`            | Readable / writable / executable                                         |
| File     | `-s`                          | File exists and is non-empty                                             |
| File     | `-L`                          | Path is a symbolic link                                                  |
| String   | `-z`                          | String is empty (zero length)                                            |
| String   | `-n`                          | String is non-empty                                                      |
| String   | `=` / `!=`                    | String equality / inequality                                             |
| Numeric  | `-eq` / `-ne`                 | Numeric equal / not equal                                                |
| Numeric  | `-lt` / `-le` / `-gt` / `-ge` | Numeric less-than / less-or-equal / greater-than / greater-or-equal      |
| Logic    | `-a` / `-o` / `!`             | AND / OR / NOT (inside a single `[ ]` — legacy, largely superseded by 3) |

```bash
if [ -f "/etc/myapp.conf" ]; then
    echo "config found"
fi

if [ "$USER" = "root" ]; then
    echo "running as root"
fi

if [ "$count" -gt 10 ]; then
    echo "count exceeds threshold"
fi
```

Note `-eq`/`-gt`/etc. for **numbers** versus `=`/`!=` for **strings** — using `-eq` on non-numeric strings, or `=` when a numeric comparison was intended (`"9" = "09"` is false as strings, true as numbers), is a routine source of bugs.

## 3. `[[ ]]`: The Bash-Specific, Safer Alternative

`[[ ]]` is a bash **keyword** (parsed by the shell itself, not an external/builtin command like `[`), and it exists specifically to close a set of quoting and behavioral pitfalls that `[ ]`/`test` carries as legacy baggage.

> ⚠️ **Warning:** `[ ]` performs word-splitting and filename globbing on unquoted variable expansions inside it, because it's an ordinary command receiving ordinary arguments — `[ $var = "foo" ]` with an unset or space-containing `$var` can produce a confusing `[: too many arguments` error or, worse, silently misbehave. `[[ ]]` does **not** word-split or glob its contents, so `[[ $var = "foo" ]]` is safe even when `$var` is unset or contains spaces — though quoting inside `[[ ]]` remains good practice for readability and consistency, it's a defense-in-depth habit rather than a strict requirement the way it is with `[ ]`.

`[[ ]]` also adds capabilities `[ ]` never had:

```bash
# Pattern matching (glob-style) on the right-hand side of =
if [[ "$filename" == *.txt ]]; then
    echo "text file"
fi

# Regex matching with =~
if [[ "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    echo "looks like a semver string"
fi

# Native && / || inside the brackets, no -a/-o needed
if [[ -f "$file" && -r "$file" ]]; then
    echo "file exists and is readable"
fi
```

`=~` performs full POSIX extended regex matching ([§50](./Section-50-Part6-Regular-Expressions-For-Linux-Administration.md) covers regex syntax in depth) and populates `${BASH_REMATCH[@]}` with captured groups — a capability `[ ]` has no equivalent for at all.

> 💡 **Tip:** Default to `[[ ]]` for anything bash-specific — scripts with a `#!/bin/bash` or `#!/usr/bin/env bash` shebang, which is nearly everything covered in this knowledge base. Reach for `[ ]`/`test` only when a script must run under a strict POSIX `sh` (no bash extensions available) — `[[ ]]` is a bash (and zsh/ksh) extension, not part of POSIX `sh`, so a script targeting `#!/bin/sh` on a system where `sh` is genuinely minimal (e.g., `dash` on Debian/Ubuntu) cannot use it.

## 4. `if` / `elif` / `else` / `fi` Structure

Full multi-branch form:

```bash
#!/usr/bin/env bash
if [[ "$response_code" -lt 300 ]]; then
    echo "success"
elif [[ "$response_code" -lt 500 ]]; then
    echo "client error"
else
    echo "server error"
fi
```

`elif` chains as many times as needed; `else` is optional; every `if` must close with `fi` (the `if` reversed — a bash convention shared with `case`/`esac`, `for`/`done`, `while`/`done`). Because 1 established that `if` branches on any command's exit status, the condition slot isn't limited to `[[ ]]` at all — `if ping -c1 -W1 "$host" &>/dev/null; then` is just as valid an `if` as one built on `test`, since `ping`'s own exit code is exactly what's being branched on.

## 5. `case` / `esac`: Pattern-Matching Branches

`case` matches a single value against a list of glob-style patterns, executing the first match and stopping — the idiomatic replacement for a long `if`/`elif`/`elif`/... chain that's all testing the same variable:

```bash
#!/usr/bin/env bash
case "$1" in
    start)
        echo "starting service"
        ;;
    stop|halt)
        echo "stopping service"
        ;;
    restart)
        echo "restarting service"
        ;;
    status*)
        echo "checking status"
        ;;
    *)
        echo "usage: $0 {start|stop|restart|status}" >&2
        exit 1
        ;;
esac
```

Key mechanics:

- Each pattern branch ends in `;;`, which terminates that branch (no fallthrough into the next pattern by default — unlike C-family `switch`).
- `|` separates multiple patterns that share the same branch (`stop|halt` above).
- Patterns are **glob-style** (`*`, `?`, `[...]`), the same wildcard matching `for` loops over filenames use — not regex; `=~`-style regex matching belongs to `[[ ]]` (3), not `case` patterns.
- `*)` as the final pattern is the conventional catch-all/default branch, matching anything not caught above — [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md)'s flag-parsing loop ([§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md), section 4) used exactly this `case` shape for `--env`/`--verbose`/unknown-flag handling.
- `;;&` (bash 4+) and `;&` are less common fallthrough variants — worth recognizing on sight if encountered, not something to reach for by default.

## 6. `for` Loops: List-Iteration and C-Style

**List-iteration form** — the idiomatic bash default, iterating over words, filenames, or command output:

```bash
for item in apple banana cherry; do
    echo "fruit: $item"
done

for file in /var/log/*.log; do
    echo "processing: $file"
done

for user in $(cut -d: -f1 /etc/passwd); do
    echo "user: $user"
done
```

**C-style form** — for numeric ranges or when the loop needs explicit index arithmetic:

```bash
for ((i = 0; i < 10; i++)); do
    echo "iteration $i"
done
```

**Which to prefer:** list-iteration (`for item in list`) is the more idiomatic bash default and reads more naturally for the overwhelmingly common case of "do this for each file/argument/line" — reach for C-style `for ((...))` specifically when the loop logic genuinely needs a numeric counter with arbitrary step/comparison logic (`i += 2`, counting down, nested index math), not as a reflexive habit carried over from C-family languages.

> ⚠️ **Warning:** `for file in *.txt` iterates over unquoted glob results, which word-splits on whitespace — a filename with a space in it silently becomes two loop iterations instead of one. This is the same class of bug [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md) (section 3) covered for `$@` vs `$*`; there's no fully clean fix within `for item in list` itself for filenames with spaces (`find ... -print0` piped into a `while read -d ''` loop, 8, is the robust pattern for that specific case).

## 7. `while` and `until`: Condition-Driven Loops

`while` repeats its body as long as its condition command **succeeds** (exit `0`); `until` is the exact inverse — it repeats as long as its condition **fails** (nonzero), stopping the moment it succeeds:

```bash
count=0
while [[ $count -lt 5 ]]; do
    echo "count: $count"
    ((count++))
done

# until stops once the condition becomes true — inverse of while
attempts=0
until curl -sf "https://api.example.com/health" &>/dev/null; do
    ((attempts++))
    echo "not ready yet, attempt $attempts..."
    sleep 2
done
echo "service is up after $attempts attempts"
```

`until` is a genuinely useful readability tool for exactly this "keep retrying until it succeeds" shape — `while ! curl ...; do` works identically but reads less naturally than `until curl ...; do` for a condition that's fundamentally about waiting for success.

## 8. The `while read` Pattern for Line-by-Line Processing

The single most common production use of `while` in shell scripting is reading input **line by line**, most often from a file or a command's output:

```bash
while read -r line; do
    echo "line: $line"
done < input.txt
```

`read -r` reads one line into `$line` per iteration, returning nonzero (ending the loop) once input is exhausted — which is exactly `while`'s condition (7), just fed by `read`'s own exit status rather than `test`/`[[ ]]`. The `-r` flag disables backslash-escape interpretation in the input, which should be the default assumption for reading arbitrary file content rather than an optional extra.

Feeding a **command's output** into the same pattern via a pipe is just as common:

```bash
grep "ERROR" app.log | while read -r line; do
    echo "found: $line"
done
```

> ⚠️ **Warning:** Piping into a `while read` loop runs the loop in a **subshell** — bash executes each side of a pipeline in its own subprocess, and the `while` loop on the right-hand side of `|` is no exception. Any variable set _inside_ that loop does not persist after the loop ends, because the subshell's entire variable state disappears when the subshell exits:
>
> ```bash
> count=0
> grep "ERROR" app.log | while read -r line; do
>     ((count++))
> done
> echo "$count"   # prints 0 — NOT the number of ERROR lines, despite appearances
> ```
>
> This surprises people constantly because the loop _looks_ like it's accumulating state correctly while it runs. The standard fixes: use **input redirection instead of a pipe** where possible (`while read -r line; do ...; done < <(grep "ERROR" app.log)` via process substitution, or simply `done < app.log` if no upstream filtering is needed) — process substitution and plain redirection keep the `while` loop in the _current_ shell, so variables set inside it survive; or restructure to capture the needed result via command substitution instead of accumulating it inside the loop body.

## 9. Loop Control: `break` and `continue`

`break` exits the enclosing loop immediately; `continue` skips the rest of the current iteration and jumps to the next one — both work identically across `for`, `while`, and `until`:

```bash
for file in /var/log/*.log; do
    if [[ ! -s "$file" ]]; then
        continue   # skip empty files, move to the next one
    fi
    if grep -q "FATAL" "$file"; then
        echo "found fatal error in $file"
        break      # stop scanning further files once found
    fi
done
```

`break N` and `continue N` (less commonly needed) break or continue N levels of nested loops at once, rather than just the innermost one — worth knowing exists, rarely necessary if loop bodies are kept reasonably flat and simple.

## 10. Infinite Loops: The Daemon/Polling Pattern

A deliberate infinite loop is a standard, non-exotic building block for daemons, watchers, and polling scripts — not something to treat as inherently a bug:

```bash
#!/usr/bin/env bash
while true; do
    if ! systemctl is-active --quiet nginx; then
        echo "$(date): nginx is down, restarting" >> /var/log/watcher.log
        systemctl restart nginx
    fi
    sleep 30
done
```

`while true` (or the equivalent `while :`, using the `:` no-op builtin that always exits `0`) is the idiomatic bash spelling of "loop forever." An infinite loop like this is only safe in production when it has an actual exit path — a `sleep` interval so it doesn't spin the CPU, a `break` condition reachable from inside the loop, or reliance on an external signal (SIGTERM from a process supervisor, [§36](../Part5/Section-36-Part5-Signals.md)'s signal coverage) to end the process — an infinite loop with none of those is a resource leak or a runaway process waiting to happen, not a polling script.

## 11. Common Misconceptions

1. **"`if` evaluates a boolean expression."** It runs a command and branches on that command's exit status (1) — `[ ]`/`[[ ]]` only work as `if` conditions because they're themselves commands/keywords that produce an exit status, not because bash has special boolean-expression syntax for `if`.
2. **"`[ ]` and `[[ ]]` are interchangeable syntax variants."** `[ ]` is an external command/builtin subject to word-splitting and globbing on unquoted expansions; `[[ ]]` is a bash keyword that avoids those pitfalls and adds pattern matching and `=~` regex support (3) — they are not equivalent, and `[[ ]]` is unavailable under strict POSIX `sh`.
3. **"`case` patterns support regex."** They're glob-style wildcard patterns (`*`, `?`, `[...]`), the same matching `for item in *.txt` uses (5) — full regex belongs to `[[ $x =~ ... ]]` (3), not `case`.
4. **"Variables set inside a piped `while read` loop are available afterward."** They aren't, because the loop runs in a subshell created by the pipe (8) — a routine, well-documented gotcha, not a bug, and process substitution or plain redirection is the standard fix.
5. **"An infinite `while true` loop is inherently bad practice."** It's a standard building block for daemons and pollers (10) — the concern is whether it has a real exit path (sleep interval, break condition, signal handling), not the infinite-loop shape itself.

## 12. Tiered Interview Questions

**🎯 Beginner:** _"What does `if [ -f "$file" ]` actually do, mechanically?"_
**Model answer:** `[` is a real command — another name for `test` — and `if` doesn't evaluate a boolean expression at all; it runs a command and checks that command's exit status afterward. So `if [ -f "$file" ]` runs the `[` command with `-f`, `"$file"`, and a closing `]` as its arguments, `[` checks whether that path is a regular file and exits `0` if so or `1` if not, and `if` branches on that exit status exactly the way it would for any other command.
_What the interviewer is probing for:_ Whether the candidate understands `if` tests exit codes, not booleans — the foundational fact the rest of bash conditional syntax builds on.

**🎯 Intermediate:** _"What's the practical difference between `[ ]` and `[[ ]]`, and when would you have to use `[ ]` instead of `[[ ]]`?"_
**Model answer:** `[ ]` is an external command/builtin, so it's subject to ordinary word-splitting and globbing on unquoted expansions — `[ $var = foo ]` can break with `too many arguments` if `$var` is unset or contains spaces. `[[ ]]` is a bash keyword, parsed specially, so it doesn't word-split or glob its contents, and it adds glob pattern matching (`==`) and full regex matching (`=~`) that `[ ]` has no equivalent for. I'd default to `[[ ]]` in any bash-specific script. The case where I'd have to use `[ ]` instead is a script that must run under strict POSIX `sh` — `dash` on Debian/Ubuntu, for instance — where `[[ ]]` isn't available at all because it's a bash/ksh/zsh extension, not POSIX.
_What the interviewer is probing for:_ Concrete knowledge of the quoting-safety and feature differences, not just "`[[ ]]` is newer/better," plus awareness that portability constraints can force `[ ]` regardless of preference.

**🎯 Senior:** _"A script has `count=0` before a `grep ... | while read -r line; do ((count++)); done`, and `echo $count` afterward prints 0 instead of the expected match count. What's happening, and how do you fix it?"_
**Model answer:** Every command on either side of a pipe runs in its own subshell — the `while` loop here is the right-hand side of the pipe, so it executes in a subshell, and `count` gets incremented inside that subshell's own copy of the shell's variable state. When the subshell exits at the end of the pipeline, that state is gone; the parent shell's `count` was never actually touched. The fix is to avoid putting the `while` loop on the receiving end of a pipe at all — use process substitution instead, `while read -r line; do ((count++)); done < <(grep ... )`, which keeps the loop running in the current shell rather than a subshell, so `count` persists correctly afterward. If the grep target is just a file with no upstream command needed, plain input redirection (`done < file`) avoids the issue entirely.
_What the interviewer is probing for:_ Recognizing the pipeline-subshell gotcha specifically (not just "something about scoping"), and knowing process substitution as the concrete, standard fix rather than a vague workaround.

**🎯 Architect:** _"You're reviewing a teammate's polling script built around `while true; do ...; sleep 5; done` that watches a service and restarts it on failure. What do you look for before approving it for production?"_
**Model answer:** The infinite-loop shape itself isn't the concern — that's the standard pattern for a daemon/poller — what matters is everything around it. First, does it have a real exit path: does it handle SIGTERM/SIGINT cleanly (so a process supervisor like systemd can actually stop it, rather than needing SIGKILL) rather than just looping forever regardless of signals. Second, is the health check itself using the right exit-status-based conditional — `if ! systemctl is-active --quiet service; then` is testing `systemctl`'s exit code correctly, and I'd flag anything that's instead grepping human-readable status text, which is fragile. Third, does the `sleep` interval make sense for the failure mode being detected, and is there any backoff or alerting if it's restarting repeatedly (a restart loop silently masking a real underlying failure is worse than no automation at all). Fourth, I'd check quoting throughout — `[[ ]]` over `[ ]` for anything bash-specific, quoted variable expansions — since a polling script is exactly the kind of thing that runs unattended for months and needs to fail loudly rather than silently misbehave on an edge case nobody tested.
_What the interviewer is probing for:_ Recognizing that an infinite loop is a legitimate structural choice, then shifting the review to the operationally significant details — signal handling, exit-status-based health checks, and failure visibility — rather than flagging the loop itself as the issue.

## 13. Key Takeaways

- `if` branches on a command's **exit status**, not a boolean value — `[ ]`/`[[ ]]` work as `if` conditions only because they're themselves commands/keywords that produce an exit status (1, 2).
- `[` is literally another name for `test`, an ordinary command subject to word-splitting/globbing on unquoted expansions; `[[ ]]` is a bash keyword that avoids those pitfalls and adds `==` glob matching and `=~` regex matching (2, 3).
- `case`/`esac` matches glob-style (not regex) patterns against a single value, with `;;` terminating each branch and `*)` as the conventional catch-all (5).
- `for item in list` is the idiomatic default for iterating collections/filenames; C-style `for ((i=0;i<n;i++))` suits explicit numeric-index arithmetic (6).
- `while`/`until` are exact inverses of each other on exit-status polarity; `while read -r line` is the standard line-by-line processing idiom (7, 8).
- Piping into a `while read` loop runs it in a subshell — variables set inside don't survive past the loop; process substitution (`< <(command)`) or plain file redirection (`< file`) fixes it (8).
- `break`/`continue` (optionally with a level count `N`) work identically across `for`/`while`/`until` (9); a well-formed infinite loop (`while true`) is a standard daemon/polling pattern, not inherently a bug, as long as it has a real sleep interval and exit path (10).

## 14. Related Concepts & What's Next

This section is the direct continuation of [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md), which used `while` and `case` minimally in its flag-parsing example and deferred full control-flow depth here; it also builds on [§44](./Section-44-Part6-Command-Chaining-Control-Operators.md)'s exit-code-as-branching-signal foundation, applied throughout every conditional and loop construct covered here. [§50](./Section-50-Part6-Regular-Expressions-For-Linux-Administration.md) (later in Part 6) covers regular expressions in the depth `[[ ]]`'s `=~` operator only introduced by name in 3. [§47](./Section-47-Part6-Functions-Arrays-String-Manipulation.md) (next) moves to functions, arrays, and string manipulation — the vocabulary needed to keep scripts that lean heavily on the loops and conditionals from this section organized and reusable rather than one long linear script body.

**Next Section:** [§47](./Section-47-Part6-Functions-Arrays-String-Manipulation.md) — `Section-47-Part6-Functions-Arrays-String-Manipulation.md`
