# Section 48 (Part 6): Text Processing Tools: grep, sed, awk

## 1. Why These Three Tools, and How They Divide the Work

[§43](./Section-43-Part6-Redirection-Pipes-Stdin-Stdout-Stderr.md) established redirection and pipes as the plumbing that connects commands together; `grep`, `sed`, and `awk` are, collectively, the single most common thing that plumbing connects **to** — they're the classic pipe destination, the tools that actually do something with the text flowing through stdin rather than just moving it around. All three predate Linux itself (Unix heritage), all three read text line by line, and all three are still reached for daily in production troubleshooting, log analysis, and one-off data wrangling, decades after "just write a script" became trivially easy.

They divide the work along a clean conceptual line that's worth internalizing before the command-reference detail below:

- **`grep`** — finds and filters **lines**. It answers "which lines match this pattern?" and does nothing to the lines themselves beyond optionally showing surrounding context.
- **`sed`** — transforms **lines**. It answers "rewrite this line according to a rule" — substituting, deleting, or selectively printing — as a stream passes through it.
- **`awk`** — processes **fields within lines**. It answers "treat each line as structured columns and compute/report/filter based on those columns."

[§47](./Section-47-Part6-Functions-Arrays-String-Manipulation.md) covered bash's own string manipulation (parameter expansion, `[[ =~ ]]`); the boundary between "use bash's built-ins" and "shell out to grep/sed/awk" is a recurring judgment call this section returns to in its final section, after each tool has been covered on its own terms.

## 2. `grep`: Basic Syntax and Core Flags

**Purpose:** search input (files or stdin) for lines matching a pattern, and print (by default) the matching lines themselves.

**Syntax:**

```bash
grep [OPTIONS] PATTERN [FILE...]
```

If no `FILE` is given, `grep` reads from stdin — which is exactly what makes it the default destination at the end of a pipeline (`ps aux | grep nginx`).

**Basic usage:**

```bash
$ grep "error" app.log
2026-07-26 03:14:02 error: connection refused
2026-07-26 03:14:09 error: timeout waiting for upstream
```

**Key flags:**

| Flag       | Meaning                                                                                  |
| ---------- | ---------------------------------------------------------------------------------------- |
| `-i`       | Case-insensitive match (`ERROR`, `Error`, `error` all match)                             |
| `-v`       | Invert the match — print lines that do **not** match the pattern                         |
| `-r`, `-R` | Recurse into a directory; `-R` additionally follows symlinks, `-r` does not              |
| `-n`       | Prefix each matching line with its line number                                           |
| `-c`       | Print only a count of matching lines, not the lines themselves                           |
| `-l`       | Print only the names of files containing at least one match, not the matching lines      |
| `-w`       | Match whole words only — `grep -w cat` matches `cat` but not `category` or `concatenate` |
| `-E`       | Extended regular expressions (see 3 below) — equivalent to running `egrep`               |
| `-P`       | Perl-compatible regular expressions (PCRE) — see the caveat below                        |
| `-A N`     | Print `N` lines of trailing context **A**fter each match                                 |
| `-B N`     | Print `N` lines of leading context **B**efore each match                                 |
| `-C N`     | Print `N` lines of context on both sides — shorthand for `-A N -B N`                     |

**Examples:**

```bash
# Case-insensitive search across every file in a directory tree
$ grep -ri "timeout" /var/log/myapp/

# Count how many lines mention "OOM" without printing them
$ grep -c "OOM" /var/log/kern.log

# Find every config file that references a deprecated setting
$ grep -rl "old_setting_name" /etc/myapp/

# Show every line NOT matching "DEBUG" — filter out noisy debug logging
$ grep -v "DEBUG" app.log

# Show 3 lines of context around each occurrence of "panic" — enough to see what led up to it
$ grep -C 3 "panic" kernel.log

# Match "cat" as a whole word only, not as a substring of "category"
$ grep -w "cat" animals.txt
```

**The `-P` caveat:** `-P` enables PCRE, which supports constructs BRE/ERE don't have at all (lookahead `(?=...)`, lookbehind `(?<=...)`, non-greedy quantifiers `*?`). It's genuinely useful, but it is **not universally available** — it depends on GNU grep being built with PCRE support, which is standard on most mainstream Linux distributions but is not guaranteed on every Unix-like system (some BSD `grep` builds, minimal containers, and non-GNU grep implementations lack it entirely). Scripts intended to be portable across unknown target systems should treat `-P` as a "verify it's available first" feature, not an assumed baseline.

> 💡 **Tip:** `grep`'s exit code ([§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md) covered exit codes in general) is meaningful and frequently used in scripts: `0` if at least one line matched, `1` if no lines matched, `2` if an actual error occurred (bad pattern, unreadable file). `if grep -q "pattern" file; then ...` is a common idiom — `-q` (quiet) suppresses output entirely and is used purely for its exit code, when a script only needs to know "does this exist" rather than see the matching line.

## 3. Basic vs. Extended Regular Expressions: Why `-E` Changes What Characters Mean

`grep` without `-E` uses **BRE** (Basic Regular Expressions); `grep -E` (or `egrep`) uses **ERE** (Extended Regular Expressions). The practical difference that trips people up constantly: in BRE, several metacharacters lose their special meaning unless **escaped** with a backslash, whereas in ERE they're special by default.

| Metacharacter | Meaning                      | BRE (plain `grep`)         | ERE (`grep -E`)            |
| ------------- | ---------------------------- | -------------------------- | -------------------------- |
| `+`           | One or more of the preceding | `\+` (escaped to activate) | `+` (bare)                 |
| `?`           | Zero or one of the preceding | `\?` (escaped to activate) | `?` (bare)                 |
| `             | `                            | Alternation (OR)           | `\|` (escaped to activate) | `   | ` (bare) |
| `(` `)`       | Grouping                     | `\(` `\)` (escaped)        | `(` `)` (bare)             |

```bash
# BRE: matching one-or-more requires an escaped +
$ grep 'colou\+r' file.txt

# ERE: the same thing, bare
$ grep -E 'colou+r' file.txt

# ERE alternation — matches lines containing "error" or "warning"
$ grep -E 'error|warning' app.log
```

This BRE/ERE split is a legacy artifact worth knowing rather than a deliberate design choice anyone would pick fresh today — `-E` almost always produces the more readable pattern for anything beyond a trivial literal-string search, and reaching for it by default is a reasonable habit. [§50](./Section-50-Part6-Regular-Expressions-For-Linux-Administration.md) (next-but-one) covers regular expression syntax itself in full depth, including character classes, anchors, and quantifiers common to grep, sed, and awk alike — this section only covers enough regex vocabulary to make the BRE/ERE distinction and the tool-specific flags legible.

## 4. `sed`: The Stream Editor Concept

`sed` (**s**tream **ed**itor) processes input **line by line**, applying a script of editing commands to each line as it passes through, and — critically — it is **not interactive**: there's no cursor to move, no visual buffer to edit by hand the way `vi` or `nano` work. You give `sed` a set of rules up front, and it applies them mechanically to every line of input, emitting the transformed result to stdout (or, with `-i`, back into the file itself).

**Syntax:**

```bash
sed [OPTIONS] 'SCRIPT' [FILE...]
```

## 5. `sed`'s Substitution Command: `s/pattern/replacement/flags`

The substitution command is the single most-used piece of `sed` by a wide margin, and its full form is worth knowing precisely:

```bash
sed 's/pattern/replacement/flags' file.txt
```

- **`pattern`** — a regular expression (BRE by default, `sed -E` for ERE, mirroring grep's split in 3) to match against each line.
- **`replacement`** — the text to substitute in; `&` inside `replacement` refers to the entire matched text, and `\1`, `\2`, etc. refer to captured groups from parenthesized parts of `pattern`.
- **`flags`** — modify the substitution's behavior:

| Flag | Meaning                                                                                      |
| ---- | -------------------------------------------------------------------------------------------- |
| `g`  | Global — replace **every** match on the line, not just the first (sed's default without `g`) |
| `i`  | Case-insensitive matching (GNU sed; some other `sed` implementations use `I` instead)        |
| `N`  | Replace only the `N`th match on the line (e.g. `2` replaces only the second occurrence)      |

```bash
# Replace only the first "foo" per line with "bar"
$ sed 's/foo/bar/' file.txt

# Replace every "foo" per line with "bar"
$ sed 's/foo/bar/g' file.txt

# Case-insensitive, global
$ sed 's/error/ERROR/gi' file.txt
```

**The delimiter-can-be-anything trick:** `/` is the conventional delimiter, but it doesn't have to be — any character can serve as the delimiter, as long as it's used consistently across all three positions. This matters enormously when the pattern or replacement itself contains a literal `/`, which is common for filesystem paths:

```bash
# Awkward and error-prone: every literal "/" must be escaped
$ sed 's/\/var\/www\/old/\/var\/www\/new/' config.txt

# Much cleaner: pick a delimiter that doesn't collide with the content, e.g. "|" or "#"
$ sed 's|/var/www/old|/var/www/new|' config.txt
$ sed 's#/var/www/old#/var/www/new#' config.txt
```

## 6. `sed` In-Place Editing: `-i` and the Backup-Suffix Safety Pattern

By default `sed` never modifies its input file — it writes the transformed stream to stdout, leaving the original untouched, which is why `sed 's/.../.../ file.txt` alone is safe to experiment with (redirect to a new file, or just eyeball the output, before committing to anything destructive). The `-i` flag changes that: it edits the file **in place**.

```bash
# Rewrites config.txt directly, no backup kept
$ sed -i 's/old_value/new_value/g' config.txt
```

> ⚠️ **Warning:** `sed -i` with no backup suffix overwrites the original file with zero recovery path if the substitution was wrong — a mistyped pattern, an over-broad match, or a regex that behaves differently than expected can silently corrupt a config file, and there's no undo. This is a genuinely common way people cause real production incidents with a single misjudged command. Always supply a backup suffix unless the change has already been verified without `-i` first:

```bash
# GNU sed: -i takes an optional suffix argument (no space between -i and the suffix)
$ sed -i.bak 's/old_value/new_value/g' config.txt
```

This leaves `config.txt.bak` as an exact pre-edit copy alongside the modified `config.txt` — a trivial `mv config.txt.bak config.txt` reverts if the substitution turns out to be wrong. **Portability note:** BSD/macOS `sed` requires the suffix argument even when empty (`sed -i '' 's/.../.../ file`), which is a frequent source of "works on my Mac, breaks on the Linux server" (or vice versa) script bugs — GNU sed (the Linux default) treats `-i` with no argument as "no backup," while BSD sed treats a missing argument as a syntax error.

> 💡 **Tip:** For anything beyond a trivial one-off edit, running the `sed` command **without** `-i` first and reviewing the output is nearly free and catches mistakes before they touch a real file. Reserve `-i` (with a backup suffix) for once the pattern has been verified.

## 7. `sed`: Deletion and Selective Printing

**Deleting lines** with the `d` command:

```bash
# Delete every line matching "DEBUG" — output has those lines removed entirely
$ sed '/DEBUG/d' app.log

# Delete a specific line number
$ sed '3d' file.txt

# Delete a range of lines (5 through 10 inclusive)
$ sed '5,10d' file.txt
```

**Printing specific lines** with `-n` combined with `p`: by default `sed` auto-prints every line after processing it, which means a bare `p` command would print matching lines **twice** (once from the automatic print, once from `p` itself). The `-n` flag suppresses the automatic printing, so `p` becomes the only source of output — this combination is the standard idiom for using `sed` as a line-selector, functionally similar to a targeted `grep` but with `sed`'s line-range and pattern-range capabilities:

```bash
# Print only lines matching "ERROR"
$ sed -n '/ERROR/p' app.log

# Print only line 42
$ sed -n '42p' file.txt

# Print a range of lines (10 through 20)
$ sed -n '10,20p' file.txt
```

**A couple of real one-liners:**

```bash
# Strip trailing whitespace from every line in a file, in place, with backup
$ sed -i.bak 's/[ \t]*$//' file.txt

# Comment out every line containing "old_directive" in a config, without deleting it
$ sed -i.bak 's/^\(.*old_directive.*\)$/#\1/' config.conf

# Remove blank lines entirely
$ sed '/^$/d' file.txt
```

## 8. `awk`: The Field-Processing Model

`awk` treats each line of input as a record automatically split into **fields** — by default on whitespace (spaces and/or tabs, with leading/trailing whitespace ignored) — which makes it the natural tool once the data has a column-like structure: `/etc/passwd`, `ps` output, CSV-ish logs, `df -h` output, and so on.

**Syntax:**

```bash
awk [OPTIONS] 'pattern { action }' [FILE...]
```

**Built-in variables:**

| Variable | Meaning                                                                                      |
| -------- | -------------------------------------------------------------------------------------------- |
| `$0`     | The entire current line, unmodified                                                          |
| `$1`     | The first field of the current line                                                          |
| `$2`     | The second field, and so on for `$3`, `$4`, ...                                              |
| `NF`     | **N**umber of **F**ields in the current line                                                 |
| `NR`     | **N**umber of **R**ecords (lines) processed so far — i.e. the line number                    |
| `FS`     | **F**ield **S**eparator — whitespace by default                                              |
| `OFS`    | **O**utput **F**ield **S**eparator — used when rebuilding `$0` from fields, space by default |

**Changing the field separator** with `-F` (equivalent to setting `FS` inside the script):

```bash
# /etc/passwd is colon-delimited
$ awk -F: '{print $1}' /etc/passwd
```

## 9. `awk`: Pattern-Action Pairs

`awk`'s core structural idea is the **pattern-action pair**: `pattern { action }`. For every input line, `awk` checks whether the line matches `pattern` — a regex, a boolean condition on field values, or nothing at all (which matches every line) — and if it does, runs `action`. A script can chain multiple pattern-action pairs, each evaluated independently against every line.

```bash
# No pattern (matches every line) — print the first field of every line
$ awk '{print $1}' file.txt

# Pattern only, no explicit action — default action is to print the whole matching line ($0), like grep
$ awk '/error/' app.log

# Pattern: a field-value condition — print lines where the 3rd field exceeds 100
$ awk '$3 > 100 {print $0}' data.txt

# Pattern: NR-based — print only line 1 (the header)
$ awk 'NR==1 {print}' data.csv
```

**A couple of real one-liners:**

```bash
# Sum a column — total bytes transferred, assuming field 5 is a byte count
$ awk '{sum += $5} END {print sum}' access.log

# Print specific fields, reordered, tab-separated
$ awk -F: '{print $1 "\t" $3}' /etc/passwd

# Filter by a field's value — show only processes owned by "www-data" from ps output
$ ps aux | awk '$1 == "www-data" {print $2, $11}'

# Average of a column
$ awk '{sum += $1; count++} END {print sum / count}' numbers.txt
```

`BEGIN` and `END` blocks are worth recognizing here — `BEGIN { }` runs once before any input is read (commonly used to set `FS` or print a header), and `END { }` runs once after all input has been consumed (commonly used to print an accumulated total, as in the sum example above) — everything else in an `awk` script runs once per input line.

## 10. Choosing the Right Tool — and When None of Them Is Right

A practical decision guide, in the order these tools tend to get reached for during real troubleshooting:

- **Reach for `grep`** when the task is purely "find or filter lines" — does a pattern exist, which lines match, how many, in which files. If the output need is "just show me the matching lines" and nothing about the lines needs to change, `grep` alone is the complete answer and pulling in `sed` or `awk` would be unnecessary overhead.
- **Reach for `sed`** when lines need to be **transformed** — substituted, deleted, or selectively extracted — especially as a non-interactive step in a pipeline or script where opening an editor isn't an option (a deploy script normalizing a config file, a log-processing pipeline stripping ANSI color codes before archiving).
- **Reach for `awk`** the moment the data is **field-structured** and the task involves the fields themselves — summing a column, comparing one field against another, reordering or reformatting columns, producing a small report. Trying to do column-aware work in `grep` or `sed` alone usually means fighting the tool; `awk`'s field model is built for exactly this.
- **Reach for a real scripting language** ([§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md)–[§47](./Section-47-Part6-Functions-Arrays-String-Manipulation.md)'s bash, or Python/Perl for anything sed/awk start to strain against) once the logic stops being "per-line, mostly stateless" — multi-file joins, nested data structures, real error handling, anything needing more than a `BEGIN`/`END` accumulator's worth of state. `awk` **can** technically do associative-array-based, multi-pass, quite sophisticated processing, but past a certain complexity threshold a one-liner becomes an unmaintainable wall of punctuation, and that's the signal to stop and write an actual script instead. A useful personal rule of thumb: if an `awk` or `sed` invocation no longer fits comfortably on one terminal line, or needs a comment to explain what it's doing, it's usually time to switch tools.

These three are also frequently **chained together** in a single pipeline — `grep` to narrow down to relevant lines, then `awk` to extract and report on specific fields from just those lines — which is a natural extension of [§43](./Section-43-Part6-Redirection-Pipes-Stdin-Stdout-Stderr.md)'s pipe coverage and a very common real-world pattern (`grep "ERROR" app.log | awk '{print $1, $2}'`).

## 11. Common Misconceptions

1. **"`grep`, `sed`, and `awk` all use the same regex syntax."** They're related but not identical — plain `grep` and plain `sed` both default to BRE (with the same escaping quirks), `-E` on either switches to ERE, and `awk`'s pattern matching uses an ERE-like syntax by default without needing a flag at all. Assuming perfect interchangeability between them is a frequent source of "this regex worked in grep but not in sed" confusion (3).
2. **"`sed -i` is always safe because it's just find-and-replace."** It overwrites the file with zero recovery path unless a backup suffix is supplied — a wrong pattern or an over-broad match is unrecoverable without one (6).
3. **"`awk` is just for printing columns."** Column extraction is the simplest use case, but `awk` is a genuine (if minimal) programming language with variables, conditionals, loops, and associative arrays — the pattern-action model plus `BEGIN`/`END` blocks (9) support real aggregation and reporting logic, not just `{print $N}`.
4. **"`-P` (PCRE) is always available in `grep`."** It depends on the specific `grep` build having PCRE support compiled in — assumed on most mainstream Linux distributions but not guaranteed everywhere, and a script meant to be portable shouldn't rely on it without verifying (2).

## 12. Tiered Interview Questions

**🎯 Beginner:** _"What's the basic difference in what grep, sed, and awk are each for?"_
**Model answer:** `grep` finds and filters whole lines based on a pattern match — it doesn't change anything, it just shows you which lines matched. `sed` is a stream editor that transforms lines as they pass through — substituting text, deleting lines, or selectively printing them — and it does this non-interactively, applying a fixed set of rules rather than being edited by hand like `vi`. `awk` treats each line as a set of fields (columns) and lets you write pattern-action rules that operate on those fields specifically, which makes it the right tool once the data has column structure and you need to do things like sum a column or reorder fields.
_What the interviewer is probing for:_ A clean mental model of the three tools' distinct roles, not just "they're all for text processing."

**🎯 Intermediate:** _"Why does `sed -i 's/old/new/g' file.txt` make some engineers nervous, and how do you make it safer?"_
**Model answer:** `-i` edits the file in place with no backup and no undo — if the pattern is wrong, too broad, or matches something unexpected, the original content is gone the moment the command runs, and there's no recovery path. The safer pattern is `sed -i.bak 's/old/new/g' file.txt`, which writes a `file.txt.bak` copy of the pre-edit content alongside the modified file, so a bad substitution is a simple `mv` away from being reverted. Even safer for anything non-trivial: run the same `sed` command without `-i` first, eyeball the output, and only add `-i` once the substitution has been verified to do exactly what's intended.
_What the interviewer is probing for:_ Awareness that `-i` is a real production-risk surface, not just a syntax detail, and knowledge of the concrete backup-suffix mitigation.

**🎯 Senior:** _"You need to extract the second field from every line in a large log file where fields are comma-separated, but only for lines containing 'ERROR', and you want a count of errors per unique value in that field. How would you approach it, and why that tool?"_
**Model answer:** This is squarely an `awk` job because it needs both pattern-based filtering and field-structured aggregation in one pass, rather than grep's line-only filtering or sed's line-transformation model. Something like `awk -F, '/ERROR/ {count[$2]++} END {for (k in count) print k, count[k]}' file.log` — set the field separator to a comma, match only lines containing ERROR, accumulate counts per second-field value in an associative array, then print the accumulated totals in an `END` block once all lines have been read. I could chain `grep ERROR file.log | awk -F, '{print $2}' | sort | uniq -c` instead, and for a one-off that's perfectly reasonable and arguably more readable — but the single-pass `awk` version avoids re-reading the data multiple times and keeps the whole aggregation logic in one place, which matters more as the file size or the complexity of the aggregation grows.
_What the interviewer is probing for:_ Recognizing when field-aware aggregation calls for `awk` specifically, comfort writing an associative-array `awk` one-liner, and the judgment to acknowledge a simpler piped alternative rather than over-engineering.

**🎯 Architect:** _"A junior engineer wants to write a 40-line `awk` script with nested loops and multiple associative arrays to parse and cross-reference two log files. What's your guidance?"_
**Model answer:** I'd push back on the tool choice before reviewing the logic itself. `awk` is a genuine language and can technically do this, but once a script needs multi-file cross-referencing, nested control flow, and multiple stateful data structures, it's past the point where `awk`'s terse, punctuation-heavy syntax is a maintainability asset — it becomes a liability the moment anyone besides the author needs to read or modify it six months later. I'd recommend Python or a similar general-purpose scripting language instead: same logic, but with named variables, proper data structures, readable control flow, testability, and error handling that `awk` doesn't really support well. My rule of thumb is that `grep`/`sed`/`awk` earn their keep for per-line, largely stateless, one-pass-or-simple-accumulator tasks — the moment a script needs real state, multiple inputs reasoned about together, or logic dense enough to need inline comments to explain itself, that's the signal to switch tools rather than push the one-liner further. I'd also note this isn't a purity argument — it's about who has to maintain this in an incident at 3 a.m., and a readable Python script beats a clever but opaque `awk` script every time at that complexity level.
_What the interviewer is probing for:_ Judgment about tool boundaries and maintainability trade-offs, not just technical capability — recognizing that "can `awk` do this" and "should `awk` do this" are different questions.

## 13. Key Takeaways

- `grep` finds/filters lines by pattern; key flags include `-i`, `-v`, `-r`/`-R`, `-n`, `-c`, `-l`, `-w`, `-A`/`-B`/`-C` for context, and `-E`/`-P` for extended/Perl-compatible regex — plain `grep` uses BRE, where `+`, `?`, `|`, `(`/`)` need escaping to be special, unlike ERE (`-E`).
- `sed` transforms lines non-interactively via a script of commands, most commonly `s/pattern/replacement/flags` (with `g` for global, `i` for case-insensitive, and any character usable as the delimiter — useful for patterns containing `/`).
- `sed -i` edits in place with **no recovery path** unless a backup suffix is supplied (`-i.bak`) — treat unverified `-i` usage as a real production-risk surface, not a routine convenience.
- `sed -n '/pattern/p'` (or `-n 'Np'`) is the standard idiom for selective printing — `-n` suppresses `sed`'s default auto-print so `p` becomes the sole output source; `d` deletes matching lines or line ranges.
- `awk` splits each line into fields (`$1`, `$2`, ..., `$0` for the whole line, `NF`/`NR`/`FS`/`OFS` as built-ins) and runs `pattern { action }` pairs per line, with `BEGIN`/`END` blocks for setup and final aggregation — the right tool once data is column-structured.
- Tool selection: `grep` for line filtering, `sed` for line transformation, `awk` for field-structured processing and reporting — and a real scripting language (Python, or bash itself per [§45](./Section-45-Part6-Bash-Scripting-Fundamentals-Shebang-Arguments-Exit-Codes.md)–[§47](./Section-47-Part6-Functions-Arrays-String-Manipulation.md)) once logic needs real state, multi-file joins, or stops fitting comfortably on one line.

## 14. Related Concepts & What's Next

This section is the classic pipe destination [§43](./Section-43-Part6-Redirection-Pipes-Stdin-Stdout-Stderr.md)'s redirection/pipes coverage set up structurally, and follows directly from [§47](./Section-47-Part6-Functions-Arrays-String-Manipulation.md)'s bash string-manipulation coverage — the two together define the practical boundary between "handle it in bash" and "shell out to grep/sed/awk." All three tools' pattern matching leans on regular expression syntax that [§50](./Section-50-Part6-Regular-Expressions-For-Linux-Administration.md) (next-but-one) covers in full depth — this section deliberately covered only the BRE/ERE distinction needed to explain flag behavior, not regex syntax itself. [§49](./Section-49-Part6-Essential-Utilities-Cut-Sort-Uniq-Tr-Wc-Xargs-Find.md) (next) continues Part 6's text-processing arc with `cut`, `sort`, `uniq`, `tr`, `wc`, `xargs`, and `find` — utilities that frequently appear alongside grep/sed/awk in the same pipelines.

**Next Section:** [§49](./Section-49-Part6-Essential-Utilities-Cut-Sort-Uniq-Tr-Wc-Xargs-Find.md) — `Section-49-Part6-Other-Essential-Utilities.md`
