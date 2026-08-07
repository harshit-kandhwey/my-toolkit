# Section 42 (Part 6): Shell Basics: Variables, Quoting, Expansion, Command Substitution

## 1. Shell Variables: The Basic Mechanism

[§41](./Section-41-Part6-Shells-Overview-Configuration-Files.md) introduced the shell as the program that reads a command line and turns it into `fork()`/`exec()` calls ([§34](../Part5/Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md)). Before any of that dispatch logic matters, the shell has to do something more basic first: it has to parse the line itself, and a huge part of that parsing is **variable assignment and expansion** — substituting names for values before the resulting words are ever handed to a program. This section is entirely about that substitution layer.

A shell variable is created with a plain assignment:

```bash
$ name=harshit
$ greeting="hello there"
$ echo $name
harshit
```

**The syntax rule that trips up nearly every newcomer:** there must be **no spaces around the `=`**. `name = harshit` is not an assignment at all — the shell parses it as a command called `name` being run with two arguments, `=` and `harshit`, and (assuming no such command exists) fails with `name: command not found`. `name=harshit` — no spaces — is the only valid form.

```bash
$ name = harshit
bash: name: command not found
$ name=harshit
$ echo "$name"
harshit
```

By default, a shell variable is **local to the current shell process** — it's visible to the interactive shell or script that created it, and to nothing else. This locality is the exact distinction [§3](../Part1/Section-03-Part1-Open-Source-Licensing-GPL-Governance.md) develops next: a shell variable versus an environment variable are not two different kinds of storage, they're the same storage with a different visibility flag set on it.

> 💡 **Tip:** Variable names are case-sensitive and, by convention (not enforcement), lowercase names are used for shell/script-local variables while uppercase names (`PATH`, `HOME`, `EDITOR`) are reserved for variables the shell or system itself relies on. Nothing stops a script from breaking that convention, but doing so risks accidentally shadowing a variable something else depends on.

## 2. Environment Variables: What "Environment" Actually Means

[§34](../Part5/Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md) established that a new process is created by `fork()`ing an existing one and then `exec()`ing a new program image into it. What `fork()`/`exec()` actually carries across that transition — beyond just the program to run — includes a specific block of data called the **environment**: a list of `KEY=value` strings the child process inherits from its parent at the moment it's created. That inherited block is precisely what "environment variable" refers to — a variable that isn't just visible in the current shell, but gets copied forward into every child process that shell subsequently spawns.

A plain shell variable, by contrast, is **not** part of that inherited block by default — it exists only in the shell's own memory and stops there. `export` is the command that flips a shell variable into an environment variable, marking it for inclusion in the environment block handed to every child process from that point forward:

```bash
$ TOKEN=abc123          # shell variable only
$ echo $TOKEN
abc123
$ bash -c 'echo "child sees: $TOKEN"'
child sees:              # empty — the child never received it

$ export TOKEN           # now promoted to an environment variable
$ bash -c 'echo "child sees: $TOKEN"'
child sees: abc123        # inherited, because export flagged it for the environment block
```

`export VAR=value` combines assignment and promotion in a single line and is the far more common form in real scripts:

```bash
$ export API_URL="https://api.internal.example.com"
```

**The mental model worth keeping precise:** exporting a variable does not make it "global" in the sense of shared, mutable storage two processes both read and write — it's a one-way, one-time copy made at the exact instant `fork()`/`exec()` happens. A child process that modifies its own copy of `TOKEN` has zero effect on the parent's `TOKEN`, and a parent that changes `TOKEN` after a child has already started has zero effect on that already-running child. This is a direct, practical consequence of [§34](../Part5/Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md)'s process-isolation model (also the model underpinning [§40](../Part5/Section-40-Part5-Inter-Process-Communication-Overview.md)'s IPC section) — environment inheritance is a snapshot, not a live link.

> ⚠️ **Warning:** `export`-ing a variable inside a script only affects that script's own child processes, never its parent shell. A common beginner mistake is running `export FOO=bar` inside a script (or a sourced-vs-executed confusion) and expecting the interactive shell that launched it to see `FOO` afterward — it won't, because the script runs as a child process with its own isolated environment copy, and nothing a child does can write back into its parent's shell state. `env` (view a process's current environment) and `printenv VAR` are the fast way to confirm whether a given variable actually made it into a specific process's environment block.

Umask ([§29](../Part4/Section-29-Part4-Umask-Default-Permissions.md)) is a useful concrete anchor for this same inheritance idea from a different angle: a process's umask is inherited by its children exactly the way environment variables are, which is why setting `umask 027` in a shell's startup/config file ([§41](./Section-41-Part6-Shells-Overview-Configuration-Files.md) covered which files load when) reliably applies to everything launched from that shell afterward — it's the same fork/exec inheritance mechanism, just carrying a different piece of process state.

## 3. Quoting: Controlling What the Shell Expands

Before the shell can run any command, it does a pass over the line converting it into a list of separate **words** — and quoting is the mechanism that controls how much of the shell's usual word-splitting, globbing, and expansion behavior applies to any given chunk of text. Getting quoting wrong is the single most common source of subtle shell scripting bugs, and it deserves to be understood precisely rather than by pattern-matching examples.

There are three distinct quoting states, and they behave very differently:

### 3.1 No Quotes (Bare Word)

An unquoted word is fully subject to the shell's expansion machinery: variable expansion happens, the result is then **word-split** on whitespace, and any remaining `*`/`?`/`[...]` characters are subject to **globbing** (filename pattern matching) against the current directory. This is almost never what's wanted when a variable's value might contain spaces — see 4 for the concrete failure mode.

### 3.2 Double Quotes (`"..."`)

Inside double quotes, **variable expansion and command substitution still happen**, but the word-splitting and globbing that would otherwise follow are suppressed — the entire quoted string is treated as a single word, whitespace and all.

```bash
$ file="my report.txt"
$ echo "$file"
my report.txt        # one argument to echo, exactly as stored
```

Double quotes are the **default, safe choice** for any variable expansion in a script unless there's a specific, understood reason to omit them.

### 3.3 Single Quotes (`'...'`)

Single quotes are **fully literal** — nothing inside them is expanded at all, not variables, not command substitution, not anything. `'$name'` is the two literal characters `$` and `name` followed by the rest, not a reference to a variable.

```bash
$ name=harshit
$ echo '$name'
$name                 # printed literally — no expansion happened
```

Single quotes are the right choice whenever the literal text needs to be preserved exactly — writing a `sed`/`awk` program that itself contains `$` ([§48](./Section-48-Part6-Text-Processing-Tools-Grep-Sed-Awk.md)–[§49](./Section-49-Part6-Essential-Utilities-Cut-Sort-Uniq-Tr-Wc-Xargs-Find.md) cover both in depth), or constructing a string that's meant to be evaluated by something else later rather than by the current shell right now.

| Quoting           | Variable expansion | Command substitution |  Word-splitting / globbing  |
| ----------------- | :----------------: | :------------------: | :-------------------------: |
| Unquoted          |        Yes         |         Yes          | Yes — the dangerous default |
| `"double quotes"` |        Yes         |         Yes          |       No — suppressed       |
| `'single quotes'` |         No         |          No          |     No — fully literal      |

> 💡 **Tip:** A reliable rule of thumb for scripts: quote every variable expansion with double quotes by default (`"$var"`, `"$@"`), reach for single quotes only when the literal text must not be touched at all, and treat a bare, unquoted `$var` as something that needs a specific justification every time it appears — not a default style choice.

## 4. The Unquoted-Variable Footgun: Word-Splitting and Globbing in Practice

This is worth its own section because it is, without close competition, the most common bug in real-world shell scripts written by people who haven't internalized 3 yet.

**The broken version:**

```bash
$ filename="my report.txt"
$ rm $filename
rm: cannot remove 'my': No such file or directory
rm: cannot remove 'report.txt': No such file or directory
```

What actually happened: `$filename` expanded to `my report.txt`, and because it was unquoted, the shell then **word-split** that single value on whitespace into two separate arguments — `my` and `report.txt` — and handed `rm` two nonexistent filenames instead of the one intended target. `rm` never saw "my report.txt" as one string at all; by the time it ran, the shell had already split it.

**The fixed version:**

```bash
$ rm "$filename"
```

Quoting suppresses the word-splitting, so `rm` receives exactly one argument — `my report.txt` — matching the actual file.

**A second, closely related failure mode — accidental globbing:**

```bash
$ pattern="*.tmp"
$ echo Found: $pattern
Found: file1.tmp file2.tmp notes.txt.tmp    # expanded against real files in cwd!
```

Here the unquoted `$pattern` expanded to the literal text `*.tmp`, and because it was unquoted, the shell then treated the `*` as a glob and matched it against real filenames in the current directory instead of printing the pattern as text. `echo Found: "$pattern"` would correctly print `Found: *.tmp`.

> ⚠️ **Warning:** This class of bug is dangerous, not just cosmetic, precisely because it most often shows up with destructive commands — `rm`, `mv`, `cp` — where the consequence of a variable unexpectedly splitting into multiple arguments (or expanding into a glob nobody intended) is data loss, not just a wrong echo. A filename containing a space, a wildcard character, or worse — an adversarially crafted filename in a directory a script iterates over — turns an unquoted `rm $var` into a real incident. Quote every variable expansion that could plausibly contain whitespace, a glob character, or attacker-influenced content, which in practice means: quote essentially all of them, all the time, and treat leaving a variable unquoted as a deliberate exception that needs its own justification.

## 5. Parameter Expansion: `$VAR` and `${VAR}`

**Parameter expansion** — substituting a variable's stored value into the command line — is the most basic of the four expansion types this section names explicitly. `$VAR` and `${VAR}` are equivalent in the simple case; the braced form exists to disambiguate where the variable name ends when it's adjacent to other text:

```bash
$ file=report
$ echo "$file.txt"
report.txt          # unambiguous — . isn't a valid variable-name character
$ echo "$file_final.txt"
.txt                 # $file_final is treated as one (empty) variable name!
$ echo "${file}_final.txt"
report_final.txt     # braces make the boundary explicit
```

`${VAR}` also unlocks a family of parameter-expansion modifiers beyond plain substitution — default values (`${VAR:-default}`), length (`${#VAR}`), substring/pattern removal, and more — that belong to [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md)'s (Part 6) bash scripting depth rather than this introductory section; the point to retain here is simply that `${...}` exists as the disambiguated, extensible form of `$...`.

## 6. Command Substitution: `$(...)` and the Legacy Backtick Form

**Command substitution** runs a command, captures its standard output, and substitutes that captured text into the surrounding command line — it's how a shell script turns "the output of a command" into "a value I can use."

```bash
$ current_dir=$(pwd)
$ echo "Working in: $current_dir"
Working in: /home/harshit/projects

$ files_count=$(ls | wc -l)
$ echo "There are $files_count files here"
```

The older, equivalent syntax uses backticks:

```bash
$ current_dir=`pwd`
```

**`$(...)` is preferred over backticks for two concrete, practical reasons:**

- **Nesting is unambiguous.** Backticks require awkward, error-prone escaping to nest (`` `echo \`date\`` ``), while `$(...)` nests cleanly because each `$(` and `)` pair is visually and syntactically self-delimiting: `$(echo $(date))`.
- **Readability.** A backtick is visually easy to confuse with a single quote in many fonts and terminal renderings, especially at a glance in a long script; `$(` has no such ambiguity.

Backticks still appear constantly in older scripts and documentation and are fully supported — recognizing them is necessary — but new scripts should default to `$(...)` without exception.

## 7. Arithmetic Expansion: `$((expr))`

**Arithmetic expansion** evaluates an integer arithmetic expression and substitutes the result, without needing an external tool like `expr` or `bc` for simple integer math:

```bash
$ a=5
$ b=3
$ echo $((a + b))
8
$ echo $((a * b - 1))
14
$ count=$((count + 1))     # common increment pattern in loops
```

Variables inside `$((...))` don't need a leading `$` (though `$a` also works) — the arithmetic context itself already knows to treat bare names as variable references. This only handles **integer** arithmetic; floating-point math needs an external tool, which is out of scope for this basics section.

## 8. Brace Expansion: `{a,b,c}` and `{1..5}`

**Brace expansion** is a purely textual, pre-expansion step — it doesn't look at variables, the filesystem, or a command's output at all, it just mechanically generates every combination of the comma-separated or range-specified items inside `{}` before anything else runs:

```bash
$ echo file{1,2,3}.txt
file1.txt file2.txt file3.txt

$ mkdir -p project/{src,bin,docs,tests}
$ ls project/
bin  docs  src  tests

$ echo {1..5}
1 2 3 4 5

$ echo {a..e}
a b c d e

$ echo {01..10}
01 02 03 04 05 06 07 08 09 10
```

Because it's purely textual generation with no filesystem lookup, brace expansion works even against paths that don't exist yet — `mkdir -p project/{src,bin,docs,tests}` creates four directories in one call precisely because the brace expansion happens first, turning that one word into four separate arguments to `mkdir`, before `mkdir` ever runs.

> 💡 **Tip:** Brace expansion is easy to confuse with globbing (`*`, `?`, `[...]`) because both look like filename shorthand, but they work in opposite directions: globbing matches _existing_ filenames against a pattern, while brace expansion generates text combinations with no regard for what does or doesn't exist on disk yet. That's exactly why brace expansion is the right tool for _creating_ a batch of new paths, while globbing is the right tool for _selecting_ from paths that already exist.

## 9. The Four Expansion Types, Compared

| Expansion type       | Syntax                                     | What it does                                                  | Runs a command? |
| -------------------- | ------------------------------------------ | ------------------------------------------------------------- | :-------------: |
| Parameter expansion  | `$VAR`, `${VAR}`                           | Substitutes a stored variable's value                         |       No        |
| Command substitution | `$(cmd)` (preferred), `` `cmd` `` (legacy) | Runs `cmd`, substitutes its captured stdout                   |       Yes       |
| Arithmetic expansion | `$((expr))`                                | Evaluates integer arithmetic, substitutes the numeric result  |       No        |
| Brace expansion      | `{a,b,c}`, `{1..5}`                        | Purely textual generation of every combination, pre-expansion |       No        |

All four can combine in a single line — `echo "Backup-$(date +%F)-$((count+1)).tar.gz"` runs a command substitution and an arithmetic expansion inside one double-quoted string — which is exactly why disciplined quoting (3) matters even more once expansions start nesting: an unquoted line with several expansion types compounding is where word-splitting bugs get hardest to spot by eye.

## 10. Hands-On: Observing the Difference Directly

### 10.1 Comparing Quoting Behavior Side by Side

**Purpose:** See unquoted, double-quoted, and single-quoted expansion of the same variable in one place, rather than trusting the rules from memory.

**Syntax:**

```bash
name="Site Reliability"
echo Unquoted: $name
echo "Double-quoted: $name"
echo 'Single-quoted: $name'
```

**Example usage and expected output:**

```bash
$ name="Site Reliability"
$ echo Unquoted: $name
Unquoted: Site Reliability     # printf happens to still look fine here...
$ printf '%s\n' Unquoted: $name
Unquoted:
Site
Reliability                    # ...but printf reveals 3 separate arguments were passed
$ echo "Double-quoted: $name"
Double-quoted: Site Reliability
$ echo 'Single-quoted: $name'
Single-quoted: $name
```

**Common errors:**

- Trusting `echo`'s output alone to judge whether word-splitting happened — `echo`'s arguments get joined back with single spaces regardless of how many separate arguments it actually received, which can visually mask a word-splitting bug that a stricter command (like `printf '%s\n'`, which prints one argument per line) exposes immediately.

**Troubleshooting:** If a script behaves correctly with simple test values but breaks in production, suspect unquoted variables and test with a value containing a space or a `*` specifically — the bug is often invisible until the actual data has whitespace or glob characters in it.

### 10.2 Checking Whether a Variable Made It Into a Process's Environment

**Purpose:** Directly verify export behavior rather than assuming it, using the ground-truth source — the process's actual environment block.

**Syntax:**

```bash
env | grep VARNAME
printenv VARNAME
```

**Example usage and expected output:**

```bash
$ export LOG_LEVEL=debug
$ bash -c 'printenv LOG_LEVEL'
debug
$ LOCAL_ONLY=set
$ bash -c 'printenv LOCAL_ONLY'
                                # empty output — never exported, never inherited
```

**Production usage example:** Debugging a service that isn't picking up a configuration value set in a shell session before launch is a routine incident-response step — `env` or `printenv` against the actual running process (via `/proc/[pid]/environ` if it's already running, [§33](../Part5/Section-33-Part5-What-A-Process-Is.md)'s Part 5 process coverage) confirms definitively whether the variable was ever in that process's environment block, rather than guessing based on what was typed in some other shell.

**Troubleshooting:** If a variable is set and exported in an interactive shell but a service still doesn't see it, check whether the service was started by a different parent (a systemd unit, a different login session) — export only propagates down the fork/exec chain from the shell that ran `export`, not sideways to unrelated process trees.

## 11. Common Misconceptions

1. **"`export` makes a variable global, so any process can read it."** Export only affects processes created afterward via `fork()`/`exec()` from that shell — it's a one-way copy at process-creation time, not shared live storage. An already-running process, or a process started from an entirely different shell/session, never sees it (2).
2. **"Double and single quotes are basically interchangeable stylistic choices."** They behave completely differently — double quotes still allow variable and command expansion while suppressing word-splitting; single quotes suppress everything, including expansion itself. Using the wrong one silently changes what a script does, not just how it looks (3).
3. **"`$(...)` and backticks are just two spellings of the same thing, use whichever."** They're functionally equivalent for simple cases but not interchangeable in practice once nesting or readability matter — `$(...)` nests cleanly with no escaping, backticks don't (6).
4. **"An unquoted variable is fine as long as I remember what value it holds."** The value at the moment of writing the script is irrelevant — the bug shows up the moment that variable later holds a value with a space, a glob character, or attacker-controlled content, which is precisely why "it worked when I tested it" is not evidence a script is safe (4).

## 12. Tiered Interview Questions

**🎯 Beginner:** _"What's the difference between a shell variable and an environment variable?"_
**Model answer:** They're the same underlying storage — a name bound to a value inside the shell — differing only in whether that value gets copied into the environment block handed to child processes at `fork()`/`exec()` time. A plain assignment like `name=value` creates a shell variable visible only within the current shell; running `export name` (or `export name=value` directly) flags it for inclusion in that inherited environment block, so every child process launched afterward receives its own copy. Without `export`, a child process started from that shell simply never sees the variable at all.
_What the interviewer is probing for:_ Whether the candidate understands `export` as a promotion mechanism tied to process creation, not a vague notion of "environment variables are more global."

**🎯 Intermediate:** _"Why does `rm $filename` sometimes fail or, worse, delete the wrong thing?"_
**Model answer:** Because an unquoted variable expansion is subject to word-splitting and globbing after the value is substituted in. If `$filename` holds `my report.txt`, the unquoted form expands to two separate arguments — `my` and `report.txt` — instead of one filename, so `rm` either fails to find either file or, in a worse case, matches unrelated files if the value happens to contain a glob character like `*`. The fix is always to double-quote the expansion — `rm "$filename"` — which suppresses word-splitting and globbing while still allowing the variable's value to be substituted. This is the single most common real-world shell scripting bug, and it's dangerous specifically because it tends to hide until a value with whitespace or special characters actually shows up in production data.
_What the interviewer is probing for:_ Concrete understanding of the word-splitting mechanism, not just "always quote variables" as a memorized rule without knowing why.

**🎯 Senior:** _"Walk through exactly what happens, mechanically, when a shell evaluates `count=$(( $(ls | wc -l) + 1 ))`."_
**Model answer:** The shell processes this in layers, innermost first. `ls | wc -l` runs as a pipeline — `ls`'s stdout is connected to `wc -l`'s stdin via a kernel pipe ([§40](../Part5/Section-40-Part5-Inter-Process-Communication-Overview.md)'s IPC coverage), and `wc -l` outputs the line count. That whole pipeline is wrapped in `$(...)`, command substitution, which captures that output as text and substitutes it into the surrounding expression. The result then sits inside `$((...))`, arithmetic expansion, which evaluates the captured number plus 1 as an integer arithmetic expression, and the final numeric result is assigned to `count` via plain parameter assignment. So three of this section's four expansion types are stacked in one line: command substitution nested inside arithmetic expansion, with the final value bound to a shell variable — and because it's all inside `$((...))`, no separate quoting is even needed here, since arithmetic context isn't subject to word-splitting the way a bare command argument would be.
_What the interviewer is probing for:_ Ability to decompose a nested expansion into its constituent mechanisms rather than treating it as one opaque idiom, and correctly identifying that arithmetic context has different quoting exposure than a normal argument position.

**🎯 Architect:** _"You're reviewing a fleet of shell scripts before a security audit. What variable/quoting patterns would you specifically flag as risk, and why?"_
**Model answer:** I'd grep aggressively for unquoted variable expansions in any position that reaches a filesystem or process-invocation command — `rm`, `mv`, `cp`, `eval`, anything building a command line from variable content — because that's exactly the word-splitting/globbing footgun (4) that turns attacker-influenced or merely unexpected input into unintended file operations or, worse, command injection if it reaches `eval` or a similarly permissive construct. I'd also flag any script that exports secrets as environment variables and then shells out to third-party tools or scripts it doesn't control — since environment inheritance is a full copy at fork/exec time, any child process (including one from a compromised or malicious dependency invoked mid-script) gets a full copy of that secret whether it needs it or not, which is a real blast-radius concern, not just a style issue. I'd also check for backtick command substitution nested inside other backticks or unquoted contexts, since that's both a readability smell and, in older, less-audited scripts, sometimes a sign the script predates any real quoting discipline being applied to it at all. None of this replaces a proper static-analysis pass (`shellcheck` is the standard tool for exactly this class of bug), but a manual read focused specifically on unquoted expansions and unnecessary secret exports catches a large fraction of real-world script vulnerabilities before automated tooling even runs.
_What the interviewer is probing for:_ Security-minded review instincts that connect quoting/expansion mechanics to concrete attack surface (injection, secret propagation) rather than treating this as a purely stylistic code-review topic.

## 13. Key Takeaways

- A shell variable (`VAR=value`, no spaces around `=`) is local to the current shell; `export` promotes it into the environment block copied into every child process at `fork()`/`exec()` time ([§34](../Part5/Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md)) — export is a one-way snapshot copy, not shared live storage.
- Quoting controls expansion: unquoted is subject to word-splitting and globbing, double quotes allow expansion but suppress splitting/globbing, single quotes suppress everything including expansion — defaulting to double-quoting every variable expansion avoids the majority of real-world scripting bugs.
- The unquoted-variable word-splitting/globbing footgun (4) is the single most common real shell scripting bug, and it's dangerous specifically with destructive commands (`rm`, `mv`) because the failure mode is silent until a value with whitespace or glob characters actually occurs.
- Four expansion types matter by name: parameter expansion (`$VAR`/`${VAR}`), command substitution (`$(cmd)`, preferred over legacy backticks for nesting and readability), arithmetic expansion (`$((expr))`, integer-only), and brace expansion (`{a,b,c}`/`{1..5}`, purely textual, no filesystem lookup).
- `$(...)` should be the default over backticks in all new scripts — functionally similar for simple cases, but backticks nest badly and read ambiguously.
- `env`/`printenv` against a real process is the ground-truth way to verify whether a variable actually made it into that process's environment, rather than assuming from what was typed in some other shell session.

## 14. Related Concepts & What's Next

This section builds directly on [§41](./Section-41-Part6-Shells-Overview-Configuration-Files.md)'s shell overview and config-file coverage — the export/inheritance model here is exactly why setting a variable in the right shell config file (`.bashrc`, `.bash_profile`, `/etc/environment`) makes it available fleet-wide to every subsequently spawned process, and it leans on [§34](../Part5/Section-34-Part5-Viewing-Processes-Ps-Top-Htop-Proc.md)'s fork/exec/wait process model (Part 5) for why environment inheritance is a one-way copy rather than shared state. It also ties back to [§29](../Part4/Section-29-Part4-Umask-Default-Permissions.md)'s umask (Part 4) as a parallel example of the same inheritance mechanism applied to a different piece of process state. **[§43](./Section-43-Part6-Redirection-Pipes-Stdin-Stdout-Stderr.md) (next) covers redirection and pipes** — stdin/stdout/stderr, `>`, `>>`, `2>&1`, and the pipe mechanic [§40](../Part5/Section-40-Part5-Inter-Process-Communication-Overview.md) introduced conceptually — which depends on this section's quoting discipline the moment a redirected filename comes from a variable. [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md) later builds full bash scripting fundamentals (shebang, arguments, exit codes) directly on top of the variable and expansion vocabulary established here.

**Next Section:** [§43](./Section-43-Part6-Redirection-Pipes-Stdin-Stdout-Stderr.md) — `Section-43-Part6-Redirection-and-Pipes.md`
