# Section 45 (Part 6): Bash Scripting Fundamentals: Shebang, Arguments, Exit Codes

## 1. The Shebang Line: How the Kernel Knows What to Run a Script With

§41 covered the shells that exist on a typical Linux system and how a login shell gets selected; this section starts from a different but related question — when a script file is executed directly, how does the kernel know which interpreter should run it? The answer is the **shebang line**, the first line of an executable script:

```bash
#!/bin/bash
echo "hello"
```

The `#!` characters (pronounced "shebang" or "hashbang") are not a comment in this position, even though `#` starts a comment everywhere else in the file. The kernel reads exactly this first line, before anything else, when asked to execute a file directly — if the line starts with `#!`, the kernel treats the rest of the line as the path to an interpreter, and instead of trying to execute the script's contents as machine code, it runs `<interpreter> <script-path>` on your behalf. This is a kernel-level convention (part of the `execve()` behavior covered conceptually in §34's fork/exec/wait lifecycle), not a bash feature — it works identically for Python, Perl, or any other interpreted language's scripts.

Two common forms of the shebang for bash specifically:

```bash
#!/bin/bash
```

```bash
#!/usr/bin/env bash
```

**Why the two forms differ, and why it matters:** `#!/bin/bash` hardcodes the absolute path to the bash binary. That path is nearly universal on mainstream Linux distributions, but it isn't guaranteed everywhere — some minimal distributions, some BSD systems, and macOS in particular may have bash installed somewhere other than `/bin/bash` (macOS ships an old bash at `/bin/bash` but developers frequently install a newer bash via Homebrew at `/usr/local/bin/bash` or `/opt/homebrew/bin/bash`). `#!/usr/bin/env bash` instead invokes `env`, a small utility that's reliably at `/usr/bin/env` across virtually every Unix-like system, and asks it to find `bash` by searching `$PATH` — the same lookup the shell itself would do for any other command. This makes the script portable across systems where bash exists but not at a fixed, predictable path.

> 💡 **Tip:** `#!/bin/bash` is the more common convention in production Linux scripting because most target environments (servers, containers, CI runners) have a known, fixed bash location — but `#!/usr/bin/env bash` is the safer default for anything that might run on a developer's laptop, a heterogeneous fleet, or an unknown environment, because it defers to `$PATH` instead of assuming a specific filesystem layout.

The shebang only takes effect when a script is executed **directly** as a program (§2 below covers exactly what that requires) — if a script is invoked as `bash script.sh`, the shebang line is irrelevant, because you've already told the kernel which interpreter to use by naming it explicitly on the command line; bash simply treats the shebang line as an ordinary comment in that case, which is harmless but does nothing.

## 2. Making a Script Executable, and the Two Ways to Run One

A freshly written script file, even with a correct shebang, is not runnable by path until it has the **executable permission bit** set — §27 (Part 4) covered `chmod` in full; the relevant invocation here is:

```bash
$ chmod +x deploy.sh
```

With the executable bit set and a valid shebang, there are two genuinely different ways to run the same script, and the distinction matters operationally:

**Method 1 — direct execution:**

```bash
$ ./deploy.sh
```

This requires **both** the executable bit (chmod'd) **and** a valid shebang line — the kernel's `execve()` call is what reads the shebang and dispatches to the named interpreter. The leading `./` (or a full path) is required because, by design, the current directory is not on `$PATH` by default on Linux — typing `deploy.sh` alone would search `$PATH` and (correctly) fail to find a script sitting in your current directory, a deliberate security convention that prevents a malicious file dropped into a shared or writable directory from silently shadowing a real system command of the same name.

**Method 2 — explicit interpreter invocation:**

```bash
$ bash deploy.sh
```

This requires **neither** the executable bit **nor** a shebang line — you're telling the shell directly "run bash, and give it this file as a script argument," which works even on a file with `644` permissions and no shebang at all, because the kernel never has to figure out what to execute the file's contents _as_; bash itself opens and reads the file as a script.

**Practical implication:** if a script fails with `Permission denied`, the executable bit is missing (`chmod +x` fixes it, or fall back to `bash script.sh` as a workaround). If it fails with something like `bad interpreter` or `no such file or directory` pointing at the shebang path, the interpreter named on the shebang line doesn't exist at that exact path on this system — a classic symptom of `#!/bin/bash` on a system where bash lives elsewhere, which is exactly the portability gap `#!/usr/bin/env bash` (1) exists to close.

## 3. Positional Parameters: Reading Arguments Into a Script

Every argument passed to a script on the command line is made available inside the script as a **positional parameter**, numbered starting from 1:

```bash
#!/usr/bin/env bash
echo "Script name: $0"
echo "First arg:   $1"
echo "Second arg:  $2"
echo "Arg count:   $#"
```

```bash
$ ./greet.sh Alice Bob
Script name: ./greet.sh
First arg:   Alice
Second arg:  Bob
Arg count:   2
```

The key variables:

| Variable        | Meaning                                                                                                                |
| --------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `$0`            | The script's own invocation name/path — not counted as an argument                                                     |
| `$1`, `$2`, ... | Individual positional arguments, in order                                                                              |
| `${10}`         | Braces are required beyond `$9` — `$10` parses as `${1}0` (parameter `$1` followed by a literal `0`), not parameter 10 |
| `$#`            | The total count of positional arguments (not counting `$0`)                                                            |
| `$@`            | All positional arguments, as a list                                                                                    |
| `$*`            | All positional arguments, as a single combined value                                                                   |

`$@` and `$*` look interchangeable in casual use and behave identically when left unquoted, but they diverge sharply — and this divergence is one of the most common sources of subtle bash bugs — the moment they're quoted.

> ⚠️ **Warning:** `"$@"` expands to each positional parameter as its **own separate, individually quoted word** — exactly preserving arguments that contain spaces. `"$*"` expands to **all** positional parameters joined into a **single word**, separated by the first character of `$IFS` (a space, by default). This matters enormously the moment any argument contains whitespace. If a script is called as `./run.sh "file one.txt" "file two.txt"` and it loops with `for f in "$@"; do echo "[$f]"; done`, the output is two lines: `[file one.txt]` and `[file two.txt]` — the two arguments stay intact. The same loop over `"$*"` instead produces one line: `[file one.txt file two.txt]` — the arguments have been silently flattened into one string, which then gets treated as a single (nonexistent) filename by anything downstream expecting two separate files. As a default rule: use `"$@"` (quoted) whenever forwarding or iterating over "all the arguments," essentially always — reach for `"$*"` only in the rare case you deliberately want them collapsed into one string.

**Forwarding all arguments to another command** is the single most common use of `"$@"` in real scripts — for example, a wrapper script that adds a default flag and then passes everything else through untouched:

```bash
#!/usr/bin/env bash
exec mytool --verbose "$@"
```

## 4. `shift`: Consuming Positional Arguments One at a Time

`shift` discards `$1` and renumbers every remaining positional parameter down by one — `$2` becomes the new `$1`, `$3` becomes the new `$2`, and so on, and `$#` decreases by one accordingly. This is the standard pattern for scripts that process an arbitrary or variable number of arguments one at a time, most commonly for hand-rolled flag parsing:

```bash
#!/usr/bin/env bash
while [[ $# -gt 0 ]]; do
    case "$1" in
        --env)
            ENVIRONMENT="$2"
            shift 2   # consume both --env and its value
            ;;
        --verbose)
            VERBOSE=true
            shift     # consume just --verbose
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 1
            ;;
    esac
done
```

`shift N` consumes `N` arguments at once (default `1` if omitted) — the `--env)` branch above consumes two positional parameters (the flag itself and its value) in a single `shift 2` rather than two separate `shift` calls, which is a common idiom worth recognizing when reading other people's flag-parsing loops. §46 (next) covers `while` and `case` themselves in full depth; this section assumes just enough of their shape to show `shift` in a realistic context.

## 5. Exit Codes: How a Script Reports Success or Failure

§44 introduced exit codes conceptually as the mechanism `&&` and `||` branch on; this section covers them in full depth as their own topic. Every command and every script, on completion, sets a numeric **exit status** that the calling shell can inspect via the special variable `$?` immediately afterward:

```bash
$ grep "pattern" file.txt
$ echo $?
0
```

```bash
$ grep "pattern" missing-file.txt
grep: missing-file.txt: No such file or directory
$ echo $?
2
```

**The core convention, universal across essentially all Unix tooling:** `0` means success, and any nonzero value in the range `1`–`255` means some kind of failure — but nonzero doesn't have one universal meaning beyond "not success"; the _specific_ nonzero value is program-defined and only meaningful in the context of the command that returned it (`grep` returning `1` means "no match found," which is a normal, expected outcome for a filtering use case, not necessarily an error worth alerting on).

**Setting a script's own exit code** with `exit N`:

```bash
#!/usr/bin/env bash
if [[ ! -f "$1" ]]; then
    echo "Error: file not found: $1" >&2
    exit 1
fi
echo "Processing $1..."
exit 0
```

If a script reaches its end without an explicit `exit`, its exit code is simply the exit code of the last command it ran — an implicit, easy-to-overlook behavior worth knowing when debugging why a script "succeeded" despite an earlier command failing partway through (this is exactly the gap `set -e`, §6, exists to close).

**A handful of exit codes carry reserved, conventional meanings worth recognizing on sight** rather than treating as arbitrary numbers:

| Code    | Conventional meaning                                                                                                                                                       |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `0`     | Success                                                                                                                                                                    |
| `1`     | General/catch-all failure — the most common non-success code, no more specific meaning implied                                                                             |
| `2`     | Frequently used for shell builtin misuse (bad flag/argument) — convention, not a kernel-enforced rule                                                                      |
| `126`   | Command found but not executable — usually a missing `chmod +x` (2) on a script being invoked                                                                              |
| `127`   | Command not found — a typo, or the binary isn't installed/isn't on `$PATH`                                                                                                 |
| `128+N` | Process terminated by signal `N` — e.g. `130` = `128 + 2` (`SIGINT`, Ctrl+C), `137` = `128 + 9` (`SIGKILL`) — §36's signal coverage explains the signal numbers themselves |

> 💡 **Tip:** `130` showing up as a script's exit code is a very common real-world signal, not a bug to chase — it almost always means someone pressed Ctrl+C while the script (or something it called) was running, and the shell translated that `SIGINT` into the `128+2` convention above.

## 6. Defensive Scripting Flags: `set -e`, `set -u`, `set -o pipefail`, `set -x`

By default, bash is remarkably permissive about things that would be considered outright errors in most other languages — a script keeps running after a command fails, referencing an unset variable silently expands to an empty string, and a failure in the middle of a pipeline is invisible unless it happens to be the pipeline's last command. Four `set` flags, usually combined near the top of a script, close most of these gaps:

**`set -e`** ("errexit") — causes the script to **exit immediately** if any command returns a nonzero exit status, instead of continuing on to the next line as if nothing happened. This turns silent, cascading failures (a failed `mkdir` followed by a `cd` into a directory that was never created, followed by files being written to the wrong place entirely) into an immediate, loud stop at the actual point of failure.

**`set -u`** ("nounset") — causes the script to **exit with an error** the moment it references a variable that was never set, instead of silently substituting an empty string. This catches typos in variable names (`$ENVIROMENT` instead of `$ENVIRONMENT`) at the exact line they occur, rather than letting the script continue with silently wrong, empty data.

**`set -o pipefail`** — changes a pipeline's exit status to be the exit status of the **first** command in the pipeline that fails, rather than just the exit status of the pipeline's last command (bash's unhelpful default). Without it, `false | true` reports exit status `0` — success — because `true` is the last command and it succeeded, completely masking that `false` failed.

**`set -x`** ("xtrace") — echoes every command to stderr, expanded, immediately before executing it — a debugging aid, not a production-safety flag, typically enabled temporarily (or via `bash -x script.sh` from the outside) rather than left on permanently.

The first three are commonly combined into a single, widely recognized production-script header:

```bash
#!/usr/bin/env bash
set -euo pipefail
```

> ⚠️ **Warning:** `set -e` has real, well-known gaps that surprise people who trust it as a complete safety net. It does **not** trigger inside a command whose failure is already being checked (`if some_command; then ... fi` — the whole point of testing it), inside the condition of `while`/`until`, on the left side of `&&` or `||`, or — critically — on a **non-last command in a pipeline**, which is exactly the gap `pipefail` exists to close: `grep "pattern" missing.txt | sort` with only `set -e` (no `pipefail`) will not stop the script even though `grep` failed, because `sort` (the last command) still exited `0`. `set -e` alone is not sufficient for pipeline safety — `pipefail` is a separate, necessary addition, not a redundant one.

## 7. Basic Script Structure and Style Conventions

A few conventions consistently distinguish scripts that are easy to maintain months later from ones that aren't, and they cost nothing to apply from the start:

- **A `set -euo pipefail` header** (6) as close to the top as possible (immediately after the shebang and any leading comment block), so defensive behavior applies to the entire script rather than being adopted partway through.
- **A short comment block** near the top stating what the script does, what arguments it expects, and any non-obvious assumptions — future readers (including the original author, months later) shouldn't have to read the whole body just to know what it's for.
- **Meaningful variable names**, `UPPER_CASE` by convention for variables meant to be treated like constants/config (`LOG_DIR`, `MAX_RETRIES`), lowercase for ordinary local working variables — not a bash-enforced rule, but a widely followed convention that makes a script's intent legible at a glance.
- **Quoting variable expansions** (`"$var"` rather than bare `$var`) essentially everywhere they're used, not just in the `"$@"` case (3) — unquoted expansions are subject to word-splitting and globbing that produce exactly the kind of subtle, input-dependent bugs `"$@"` vs `$*` (3) demonstrates in miniature.
- **Checking prerequisites early** — required arguments present, required commands available (`command -v` checks), required files existing — and failing fast with a clear message on stderr and a nonzero exit code (5), rather than letting a missing precondition surface as a confusing error many lines later.

None of these are enforced by bash itself — they're accumulated operational wisdom from scripts that failed in production in ways a little more discipline up front would have caught, which is exactly why `set -euo pipefail` (6) has become close to a de facto standard opening line for any bash script expected to run unattended.

## 8. Common Misconceptions

1. **"`#!/bin/bash` and `#!/usr/bin/env bash` are just stylistic preference."** They resolve the interpreter differently — a hardcoded absolute path versus a `$PATH` lookup via `env` — and that difference has real portability consequences on systems where bash isn't at `/bin/bash` (1).
2. **"`./script.sh` and `bash script.sh` are two syntaxes for the same thing."** They have different requirements: the former needs both the executable bit and a valid shebang (the kernel does the interpreter dispatch); the latter needs neither, because the interpreter is named explicitly on the command line (2).
3. **"`$@` and `$*` are interchangeable."** They behave identically unquoted, but diverge sharply when quoted — `"$@"` preserves each argument as a separate word, `"$*"` flattens all arguments into one, which silently breaks any argument containing whitespace (3).
4. **"`set -e` makes a script fail-safe against any command failure."** It has specific, well-documented gaps — conditions already being tested, non-last pipeline commands without `pipefail`, and a few other cases — that make it necessary but not sufficient on its own (6).
5. **"A nonzero exit code always means something went wrong."** The convention is only "0 = success"; nonzero values are program-defined and sometimes represent an entirely normal outcome (`grep` returning `1` for "no match," not an error) (5).

## 9. Tiered Interview Questions

**🎯 Beginner:** _"What does the shebang line at the top of a bash script actually do?"_
**Model answer:** It tells the kernel which interpreter to run the rest of the file with, when the script is executed directly as a program. The kernel reads the first line, and if it starts with `#!`, treats everything after it as the path to an interpreter, then effectively runs that interpreter with the script file as its argument, instead of trying to execute the file's raw contents as machine code. It only matters for direct execution (`./script.sh`) — if you run `bash script.sh` explicitly, you've already told the shell which interpreter to use, so the shebang line is ignored.
_What the interviewer is probing for:_ Understanding that the shebang is a kernel-level convention tied to direct execution, not a bash-specific feature that always applies.

**🎯 Intermediate:** _"What's the practical difference between `"$@"` and `"$*"`, and when does it actually matter?"_
**Model answer:** Unquoted, they behave the same — both expand to all positional parameters, word-split. Quoted, they diverge: `"$@"` expands to each argument as its own separate, individually quoted word, while `"$*"` joins all arguments into a single word separated by the first character of `$IFS`. It matters the moment any argument contains a space — looping over `"$@"` with two arguments `"file one.txt"` and `"file two.txt"` correctly processes two items, while looping over `"$*"` collapses them into one flattened string that gets treated as a single, wrong value downstream. As a rule, I default to `"$@"` for forwarding or iterating over all arguments, and only reach for `"$*"` when I deliberately want everything joined into one string.
_What the interviewer is probing for:_ Whether the candidate has actually been bitten by this distinction, not just memorized "they're different."

**🎯 Senior:** _"Your team uses `set -e` in all production scripts and considers it sufficient error handling. What's missing?"_
**Model answer:** `set -e` has real, specific gaps that trip people who treat it as a complete safety net. It doesn't fire inside a condition that's already being explicitly tested — `if some_command; then` — because a nonzero result there is expected, checked behavior, not an unhandled error. It doesn't fire on the left side of `&&` or `||`. And critically, in a pipeline, `set -e` only looks at the pipeline's overall exit status, which by bash's default is just the last command's exit status — so a failure in an earlier stage of a multi-stage pipeline is invisible unless `set -o pipefail` is also set. I'd pair `set -e` with `set -o pipefail` always, and `set -u` to catch unset-variable typos, giving the `set -euo pipefail` header — and I'd still not treat that combination as a complete substitute for explicit error checking on operations where the failure mode actually needs a specific recovery action, not just "stop."
_What the interviewer is probing for:_ Knowing `set -e`'s specific documented gaps (not just "it has gaps"), and recognizing `pipefail` as a necessary companion rather than redundant.

**🎯 Architect:** _"You're reviewing a colleague's deployment script that uses `#!/bin/bash` and passes user-supplied filenames as `$*` to a downstream tool. What do you flag, and why?"_
**Model answer:** Two separate issues, both with real production consequences. First, `#!/bin/bash` hardcodes an absolute interpreter path — fine if every target host is guaranteed to have bash at exactly that path, but a portability risk the moment this script might run somewhere it isn't (a different distro, a container base image, a contributor's machine) — I'd switch it to `#!/usr/bin/env bash` unless there's a specific reason to pin the path. Second, and more urgent: using `$*` (or worse, unquoted `$*`) to pass along filenames means any filename containing a space gets silently flattened into the surrounding arguments, which for a deployment script handling user-supplied input isn't just a correctness bug — it's the kind of subtle failure that can send the wrong file to the wrong place with no error raised, because nothing here fails loudly. I'd require `"$@"` (quoted) for the argument-forwarding, and I'd also check whether the script has a `set -euo pipefail` header at all — a deployment script that continues past a failed step because nobody caught it is exactly the operational failure mode that combination exists to prevent.
_What the interviewer is probing for:_ Prioritizing the argument-quoting bug as the more severe, silent-data-corruption risk over the shebang portability issue, while still correctly flagging both, and tying the review back to concrete production consequences rather than reciting rules.

## 10. Key Takeaways

- The shebang (`#!`) is a kernel-level convention read only on direct execution (`./script.sh`) — `#!/bin/bash` hardcodes an absolute path, `#!/usr/bin/env bash` resolves via `$PATH` and is the more portable choice across heterogeneous environments.
- `chmod +x` plus a valid shebang enables direct execution; `bash script.sh` needs neither, since the interpreter is named explicitly — two genuinely different invocation paths, not two syntaxes for the same thing.
- Positional parameters (`$1`, `$2`, ..., `$0` for the script name, `$#` for the count) are how a script reads its arguments; `shift` consumes them from the front, commonly used in hand-rolled flag-parsing loops.
- `"$@"` preserves arguments as separate words when quoted; `"$*"` flattens them into one — a distinction that only shows up with whitespace-containing arguments and is a frequent source of subtle bugs when gotten wrong.
- Exit codes follow the universal convention of `0` = success, nonzero = failure, with a handful of reserved conventional values (`126`, `127`, `128+N` for signals) worth recognizing on sight; `$?` reads the most recent command's exit status.
- `set -e`, `set -u`, and `set -o pipefail` each close a specific default-bash permissiveness gap — but `set -e` alone has real, documented blind spots (tested conditions, non-last pipeline commands) that `pipefail` specifically addresses; `set -x` is a debugging aid, not a safety flag.
- `set -euo pipefail` as a standard script header, meaningful variable names, consistent quoting, and early prerequisite checks are accumulated operational conventions, not bash-enforced rules — but they're what separates scripts that fail loudly and early from ones that fail silently and late.

## 11. Related Concepts & What's Next

This section builds directly on §41's shell-selection groundwork (which interpreter the shebang line ultimately names) and on §44's introductory treatment of exit codes as the mechanism `&&`/`||` branch on, going to full depth on exit codes here instead. It also leans on §21's (Part 3) `chmod` coverage for the executable-bit half of running a script directly. §46 (next) picks up exactly where the flag-parsing example in 4 left off, covering `if`/`else`, `case`, `for`, `while`, and `until` in full depth — the control-flow vocabulary this section deliberately used only minimally.

**Next Section:** §46 — `Section-46-Part6-Control-Structures.md`
