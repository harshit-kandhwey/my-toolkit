# Section 49 (Part 6): Other Essential Utilities: cut, sort, uniq, tr, wc, xargs, find

## 1. Where These Fit Relative to grep/sed/awk

§48 covered `grep`, `sed`, and `awk` as the heavyweight text-processing tools — pattern matching, stream editing, and field-based programmable processing. This section covers seven smaller, single-purpose utilities that are used constantly _alongside_ those three, usually chained together in the same pipeline (§43 covered the pipe mechanics these all depend on). None of these tools is individually as powerful as `awk`, and that's deliberate — each does one narrow thing well, which is exactly the small-composable-tools philosophy that shows up repeatedly across this knowledge base. Real production one-liners rarely use just one of these; they chain two, three, or four together, and recognizing the idiomatic combinations (`sort | uniq -c`, `find | xargs`) is more valuable than memorizing any single tool's full flag list.

## 2. `cut`: Extracting Fixed Fields or Character Ranges

**Purpose:** Pull out specific fields or character positions from each line of input — the lightest-weight field extractor available, faster to write than `awk` for the simple, single-character-delimiter case it's built for.

**Syntax:**

```bash
cut -d<delimiter> -f<field-list> [file]
cut -c<range> [file]
```

**Key flags:**

| Flag           | Meaning                                                                                            |
| -------------- | -------------------------------------------------------------------------------------------------- |
| `-d`           | Field delimiter (single character only — this is `cut`'s central limitation, covered below)        |
| `-f`           | Field number(s) to select — `-f1`, `-f1,3`, `-f2-4`, `-f2-` (field 2 to end)                       |
| `-c`           | Character position(s) to select, same range syntax as `-f`                                         |
| `--complement` | Invert the selection — output everything _except_ the given fields/characters                      |
| `-s`           | Suppress lines that don't contain the delimiter at all (silently skip rather than print unchanged) |

**Example usage:**

```bash
$ cat /etc/passwd | cut -d: -f1,7
root:/bin/bash
daemon:/usr/sbin/nologin
deploy:/bin/bash

$ echo "hello world" | cut -c1-5
hello
```

**The key limitation vs. `awk`:** `cut -d` accepts exactly **one delimiter character**, and it treats fields as separated by exactly that character with no collapsing of repeats — a line with multiple consecutive spaces (common in `ps` or `ls -l` output) produces empty fields between them, because `cut` doesn't understand "one or more spaces" as a single separator the way `awk`'s default field-splitting does. `ps aux | cut -d' ' -f2` on real `ps` output is a classic beginner mistake that silently returns garbage, because the columns aren't separated by exactly one space. `awk '{print $2}'` (§48) handles that correctly by treating any run of whitespace as one delimiter. Reach for `cut` when the input has a single, consistent, single-character delimiter (`:`, `,`, `\t`) — reach for `awk` the moment delimiters are irregular or multi-character.

> 💡 **Tip:** `cut` is meaningfully faster and more readable than `awk` for the simple case it's built for — don't reach for `awk '{print $1}'` out of habit when `cut -d, -f1` says exactly the same thing more directly for well-formed, single-delimiter input like CSV.

## 3. `sort`: Ordering Lines

**Purpose:** Sort lines of text — alphabetically by default, with flags to sort numerically, by a specific column, in reverse, or with duplicates collapsed.

**Syntax:**

```bash
sort [options] [file...]
```

**Key flags:**

| Flag        | Meaning                                                                                                 |
| ----------- | ------------------------------------------------------------------------------------------------------- |
| `-n`        | Numeric sort — compares values as numbers, not as strings (string sort would put `"10"` before `"9"`)   |
| `-r`        | Reverse the sort order                                                                                  |
| `-k<N>`     | Sort by field/column `N` (1-indexed) rather than the whole line                                         |
| `-t<delim>` | Field delimiter to use with `-k` (default: whitespace)                                                  |
| `-u`        | Unique — collapse adjacent equal lines to one, after sorting (equivalent to `sort \| uniq` in one step) |
| `-h`        | Human-numeric sort — correctly orders sizes like `2K`, `1M`, `3G` by actual magnitude, not string order |
| `-f`        | Case-insensitive sort                                                                                   |

**Example usage:**

```bash
$ sort -n numbers.txt
$ sort -t: -k3 -n /etc/passwd          # sort passwd entries by numeric UID (field 3)
$ du -sh */ | sort -rh                  # largest directories first
```

**Common error:** using plain `sort` (default lexical) on a column of numbers — `"10"` sorts before `"2"` as a string, because lexical comparison looks at the first character (`1` < `2`) without ever considering magnitude. `-n` (or `-h` for human-readable sizes with unit suffixes) fixes this; forgetting it is one of the most common silent-wrong-output bugs in shell one-liners.

## 4. `uniq`: Collapsing Duplicate Lines

**Purpose:** Remove or count duplicate lines — but only **adjacent** ones.

**Syntax:**

```bash
uniq [options] [file]
```

**Key flags:**

| Flag | Meaning                                                                                 |
| ---- | --------------------------------------------------------------------------------------- |
| `-c` | Prefix each output line with a count of how many times it occurred consecutively        |
| `-d` | Print only lines that had at least one duplicate (the duplicates themselves, once each) |
| `-u` | Print only lines that had **no** duplicates — the opposite of `-d`                      |
| `-i` | Case-insensitive comparison                                                             |

> ⚠️ **Warning:** `uniq` only detects duplicates that are **immediately adjacent** in the input — it does not scan the whole file for repeats. Running `uniq` directly on an unsorted file silently fails to collapse duplicates that aren't next to each other, and nothing about the output looks obviously wrong — it just quietly doesn't do what most people expect. The fix is universal: **sort first**. `sort file | uniq` (or the single-step `sort -u file`) guarantees every duplicate is adjacent before `uniq` ever sees it.

**Example usage — the classic frequency-count idiom:**

```bash
$ sort access.log | uniq -c | sort -rn | head -10
```

This three-stage pipeline — sort to make duplicates adjacent, `uniq -c` to count them, `sort -rn` to rank by count descending — is one of the most common patterns in all of shell scripting for answering "what values show up most often in this file," and it's worth recognizing on sight rather than re-deriving each time.

## 5. `tr`: Character Translation and Deletion

**Purpose:** Translate, squeeze, or delete individual characters in a stream — operates on characters, not lines or fields, which distinguishes it from every other tool in this section.

**Syntax:**

```bash
tr [options] SET1 [SET2]
```

**Key flags and forms:**

| Form                                                            | Meaning                                                                                                                |
| --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| `tr 'a-z' 'A-Z'`                                                | Translate every character in SET1 to the corresponding character in SET2 (position-by-position)                        |
| `tr -d 'SET'`                                                   | Delete every character in SET, no SET2 needed                                                                          |
| `tr -s 'SET'`                                                   | Squeeze — collapse consecutive repeats of characters in SET down to a single occurrence                                |
| `tr -cd 'SET'`                                                  | Complement + delete — delete everything **not** in SET (a common way to strip to just digits, or just printable ASCII) |
| `[:upper:]`, `[:lower:]`, `[:digit:]`, `[:space:]`, `[:punct:]` | POSIX character classes, usable in place of explicit ranges — more portable and readable than `a-z`/`A-Z`              |

**Example usage:**

```bash
$ echo "Hello World" | tr '[:lower:]' '[:upper:]'
HELLO WORLD

$ echo "line1   line2" | tr -s ' '
line1 line2

$ cat file.txt | tr -d '\r'             # strip Windows-style CRLF line endings

$ echo "abc123def456" | tr -cd '0-9'
123456
```

`tr` only reads from **stdin** — it has no file-argument form the way `grep`/`sed`/`sort` do, so it always appears after a pipe or with input redirected (`tr ... < file`).

## 6. `wc`: Counting Lines, Words, Bytes, Characters

**Purpose:** Produce basic counts of input — the fastest way to answer "how many lines/words/bytes is this" without writing a script.

**Syntax:**

```bash
wc [options] [file...]
```

**Key flags:**

| Flag | Meaning                                                                   |
| ---- | ------------------------------------------------------------------------- |
| `-l` | Line count                                                                |
| `-w` | Word count                                                                |
| `-c` | Byte count                                                                |
| `-m` | Character count (differs from `-c` under multi-byte encodings like UTF-8) |

**Example usage:**

```bash
$ wc -l access.log
15234 access.log

$ find . -name '*.py' | wc -l           # count matching files
$ grep -c ERROR app.log                 # note: grep -c counts matching LINES, not occurrences — wc -l after grep gives the same result for single-match-per-line cases
```

`wc -l` piped from another command (no filename argument) is an extremely common idiom for turning "list of things" into "count of things" — `ps aux | grep nginx | wc -l` to count running worker processes is a pattern seen constantly in ad hoc operational checks.

## 7. `xargs`: Turning Stdin Into Command Arguments

**Purpose:** Bridge the gap between commands that _produce_ a list on stdout (`find`, `grep -l`, `ls`) and commands that _expect_ their targets as command-line arguments rather than reading stdin themselves (`rm`, `chmod`, `cp` don't read filenames from stdin — `xargs` is what feeds them from a pipeline).

**Syntax:**

```bash
command1 | xargs [options] command2
```

**Key flags:**

| Flag    | Meaning                                                                                                                                                                                            |
| ------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `-n<N>` | Pass at most `N` arguments to each invocation of `command2`, invoking it multiple times if needed rather than one giant argument list                                                              |
| `-I{}`  | Define a placeholder (commonly `{}`) that gets substituted with each input item individually — required when the item needs to appear in the _middle_ of the command, not just appended at the end |
| `-p`    | Prompt before running each command — a safety check when experimenting with something destructive                                                                                                  |
| `-0`    | Read null-delimited input instead of whitespace/newline-delimited — pairs with `find -print0` (below)                                                                                              |
| `-t`    | Print each constructed command to stderr before running it (trace/debug mode)                                                                                                                      |

**Example usage:**

```bash
$ find . -name '*.tmp' | xargs rm
$ echo "file1.txt file2.txt" | xargs -n1 echo "Processing:"
$ find . -name '*.conf' | xargs -I{} cp {} {}.bak
```

> ⚠️ **Warning:** The classic `find | xargs rm` pattern above has a well-known filename-with-spaces bug. `xargs` by default splits its input on whitespace (and newlines), so a filename like `my report.txt` gets split into two separate arguments — `my` and `report.txt` — and `rm` then either fails on two nonexistent files or, worse, deletes something unintended if a file named `my` genuinely exists elsewhere in the argument list. The fix is to use **null bytes** as the delimiter instead of whitespace, since `\0` cannot legally appear in a Unix filename (unlike spaces, newlines, or almost any other character): `find . -name '*.tmp' -print0 | xargs -0 rm`. `-print0` tells `find` to separate output entries with `\0` instead of `\n`, and `-0` tells `xargs` to split on `\0` instead of whitespace — together they make the pipeline safe for every legal filename, including ones with spaces, tabs, or embedded newlines. Treat plain `find | xargs` (no `-print0`/`-0`) on anything that touches real filesystem paths as a latent bug, not just a style preference.

## 8. `find`: Locating Files by Attribute

**Purpose:** Search a directory tree for files/directories matching name, type, modification time, size, and other attributes — §21 (Part 3) covered basic filesystem navigation; `find` is the tool for locating files by _criteria_ rather than by known path.

**Syntax:**

```bash
find <path> [expression]
```

**Key match criteria:**

| Flag                  | Meaning                                                                                                    |
| --------------------- | ---------------------------------------------------------------------------------------------------------- |
| `-name '<pattern>'`   | Match by filename (glob pattern, case-sensitive)                                                           |
| `-iname '<pattern>'`  | Case-insensitive name match                                                                                |
| `-type f` / `-type d` | Restrict to regular files / directories                                                                    |
| `-mtime -N` / `+N`    | Modified less than / more than `N` days ago                                                                |
| `-mmin -N` / `+N`     | Same, in minutes — for finer-grained recency checks                                                        |
| `-size +N<unit>`      | Size greater than `N` (`k`, `M`, `G` suffixes)                                                             |
| `-exec <cmd> {} \;`   | Run `<cmd>` once per match, `{}` substituted with the matched path                                         |
| `-exec <cmd> {} +`    | Same, but batches matches into fewer invocations (like `xargs`, more efficient than `\;` for many matches) |
| `-delete`             | Delete matches directly — no external command needed                                                       |
| `-print0`             | Null-delimited output, for safe piping into `xargs -0` (7)                                                 |

**Example usage:**

```bash
$ find /var/log -name '*.log' -mtime +30
$ find /data -type f -size +1G
$ find /tmp -type f -mtime +7 -delete
```

**`-exec` vs. piping to `xargs`:** both run a command against each match, but they differ in process-spawning cost and syntax. `find ... -exec cmd {} \;` invokes `cmd` once **per file**, which is simple and safe (no filename-splitting risk at all, since `find` hands each path to `-exec` directly) but can be slow across a large result set. `find ... -exec cmd {} +` batches many matches into fewer invocations, closing most of that performance gap while keeping `-exec`'s safety. `find ... -print0 | xargs -0 cmd` achieves similar batching and is often preferred when the target command isn't easily expressed inline, or when the pipeline needs to insert `sort`/`uniq`/other filtering between `find` and the final command — something `-exec` alone can't do, since it has no stage for intermediate processing.

> 💡 **Tip:** For simple delete-what-I-just-found cases, `find ... -delete` is safer and faster than either `-exec rm {} \;` or piping to `xargs rm` — it never spawns an external process at all, so there's no filename-splitting risk to worry about in the first place. Reach for `-exec`/`xargs` only when the operation is something other than delete, or needs a command `find` doesn't have a built-in flag for.

## 9. Combined Pipeline Examples

**Find and safely delete old log files:**

```bash
$ find /var/log/app -name '*.log' -mtime +30 -print0 | xargs -0 rm -v
```

Null-delimited throughout (7's Warning), scoped to a specific name pattern and age threshold rather than a blanket delete — the kind of pipeline that's safe to run unattended in a cron job (§40 covers scheduling).

**Top 10 largest directories under the current path:**

```bash
$ du -sh */ 2>/dev/null | sort -rh | head -10
```

`du -sh` produces human-readable sizes per top-level directory, `sort -rh` orders them largest-first using human-numeric comparison (3) rather than lexical string order, and `head -10` trims to the top result set.

**Count unique client IPs in a web server log, ranked by request count:**

```bash
$ awk '{print $1}' access.log | sort | uniq -c | sort -rn | head -20
```

`awk` extracts the first whitespace-delimited field (the client IP, in standard combined log format — §48), `sort` makes identical IPs adjacent so `uniq -c` (4) can count them correctly, and the final `sort -rn` ranks by request volume descending. This exact shape — extract, sort, uniq -c, sort again — is worth memorizing as a template; it answers "what are the most common values of column X" for almost any structured log file.

## 10. Common Misconceptions

1. **"`cut` and `awk '{print $N}'` are interchangeable."** They coincide only for single-character, non-repeating delimiters — `cut` breaks silently on runs of whitespace or multi-character delimiters, where `awk`'s default field-splitting handles them correctly (2).
2. **"`uniq` removes all duplicates from a file, like a dedup command."** It only removes **adjacent** duplicates — running it on unsorted input leaves non-adjacent duplicates untouched, with no error or warning (4). `sort | uniq` is the reliable pattern, not `uniq` alone.
3. **"`find | xargs rm` is a safe, standard way to bulk-delete matched files."** It breaks on filenames containing spaces or newlines because `xargs` splits on whitespace by default — `-print0`/`-0` (7) is the fix, and `find -delete` (8) sidesteps the issue entirely for the simple delete case.
4. **"`sort` without flags sorts numbers correctly."** Default `sort` is lexical (string) comparison — `"10"` sorts before `"2"` — `-n` (or `-h` for sizes with unit suffixes) is required for numeric correctness (3).
5. **"`-exec` and piping to `xargs` are just two syntaxes for the same operation."** `-exec ... \;` spawns one process per match (safe but potentially slow); `-exec ... +` and `xargs` both batch invocations for efficiency, but only the `xargs` pipeline allows inserting other tools (`sort`, `uniq`, filtering) between the file list and the final command (8).

## 11. Tiered Interview Questions

**🎯 Beginner:** _"What does `sort | uniq -c` do, and why does the `sort` have to come first?"_
**Model answer:** It counts how many times each distinct line appears in the input. `uniq -c` prefixes each line with a count, but `uniq` only detects duplicates that are immediately adjacent to each other in the input stream — it doesn't scan the whole file for matches. `sort` has to run first to bring every occurrence of an identical line next to each other; without it, two identical lines separated by a different line in between would be counted as two separate groups of one instead of one group of two.
_What the interviewer is probing for:_ Understanding `uniq`'s adjacency limitation specifically, not just knowing the idiom by rote.

**🎯 Intermediate:** _"Why does `ps aux | cut -d' ' -f2` often produce wrong output, and what's the fix?"_
**Model answer:** `ps aux` output columns are separated by variable-width runs of spaces for alignment, not a single consistent space character. `cut -d' '` treats every individual space as a field separator, so multiple consecutive spaces produce multiple empty fields, throwing off the field numbering — field 2 by `cut`'s count often isn't the PID column at all. `awk '{print $2}'` fixes it because `awk`'s default field-splitting treats any run of whitespace as one delimiter, correctly collapsing the padding. As a rule, `cut` is reliable for genuinely single-character delimited data (CSV, `/etc/passwd`) and unreliable for whitespace-padded columnar output like `ps` or `ls -l`.
_What the interviewer is probing for:_ Recognizing `cut`'s single-character-delimiter limitation as a concrete, specific failure mode rather than a vague "cut is less powerful than awk."

**🎯 Senior:** _"A teammate's cleanup script runs `find /tmp -name '*.old' | xargs rm -f` nightly via cron. What's your review comment?"_
**Model answer:** The core issue is that `xargs` splits its input on whitespace by default, so any matched filename containing a space gets split into multiple arguments — `rm -f` then either silently fails on the fragments (masked anyway by `-f`) or, in a worse case, could act on an unintended argument if one of the fragments happens to match something else on the system. Since this runs unattended via cron, a silent failure is worse than a loud one — nobody's watching it interactively to notice. The fix is `find /tmp -name '*.old' -print0 | xargs -0 rm -f`, using null-byte delimiters that can't appear in a legal filename, or better yet, replacing the whole pipeline with `find /tmp -name '*.old' -delete`, which never spawns `rm` as a separate process at all and has no filename-splitting risk to reason about in the first place. I'd also ask whether `-f` is masking other legitimate failures (permissions issues, files that vanished mid-run) that a cron job's log should probably surface rather than silently swallow.
_What the interviewer is probing for:_ Correctly identifying the filename-splitting bug as the primary issue, knowing the concrete fix (`-print0`/`-0` or `-delete`), and connecting "runs unattended via cron" to why silent failure modes matter more here than in an interactive session.

**🎯 Architect:** _"You need a nightly job that reports the top 20 most active client IPs from a multi-gigabyte access log, without loading the whole file into memory in a custom script. How would you build it, and what would you watch for at scale?"_
**Model answer:** I'd build it as a streaming pipeline rather than a script that reads the whole file in: `awk '{print $1}' access.log | sort | uniq -c | sort -rn | head -20` — each stage processes a stream and hands output to the next via a pipe (§43), so nothing needs the full file resident in memory except `sort`, which spills to disk temp files automatically once its buffer is exceeded rather than failing outright, which is exactly why this scales to multi-gigabyte input where a naive in-memory approach in a custom script wouldn't without deliberate care. At real scale I'd watch a few things: `sort`'s temp-file I/O can become the bottleneck on a disk-constrained host, so I'd consider `sort --parallel` or ensuring `/tmp` has headroom and reasonable I/O; if the log rotates, I'd make sure the job targets the correct file (or globs across a rotation window) rather than assuming one static path; and if this needs to run frequently against a live, actively-appended log, I'd consider whether a proper log-analysis pipeline (structured logging into something queryable) is a better long-term answer than re-deriving this awk/sort/uniq chain by hand every night — the shell pipeline is the right tool for an ad hoc or lightweight recurring check, not necessarily for a system that needs this data queryable on demand.
_What the interviewer is probing for:_ Recognizing that Unix pipelines are inherently streaming and don't require the whole file in memory, awareness of `sort`'s disk-spill behavior as the actual scaling mechanism, and the judgment to flag when a shell one-liner is the wrong long-term tool despite working correctly today.

## 12. Key Takeaways

- `cut` extracts fields/characters fast but only handles a single-character delimiter with no whitespace-collapsing — `awk` (§48) is the fallback the moment delimiters are irregular.
- `sort` defaults to lexical ordering — `-n` for numbers and `-h` for human-readable sizes are required for correct numeric ordering, and `-k`/`-t` target a specific column rather than the whole line.
- `uniq` only catches **adjacent** duplicates — `sort | uniq -c` (sort first, then count) is the standard, necessary pattern, not `uniq` used alone on unsorted input.
- `tr` operates on individual characters, not lines or fields, and only reads stdin — `-d` deletes, `-s` squeezes repeats, and POSIX classes like `[:upper:]` are more portable than explicit ranges.
- `wc -l/-w/-c/-m` gives fast line/word/byte/character counts, and `wc -l` piped from another command is a common "count of things" idiom.
- `xargs` bridges stdout-producing commands into commands that expect arguments — but the classic `find | xargs rm` pattern is unsafe on filenames with spaces unless paired with `-print0`/`-0`, which is a genuine, well-documented production bug pattern, not a theoretical edge case.
- `find` locates files by name/type/time/size criteria; `-exec ... +` and `-print0 | xargs -0` both batch operations efficiently, while `-delete` avoids spawning an external process (and its filename-splitting risk) entirely for the simple delete case.
- The `extract → sort → uniq -c → sort -rn` chain (9) is a reusable template for "what are the most common values of column X" across nearly any structured log or delimited file.

## 13. Related Concepts & What's Next

This section builds directly on §48's `grep`/`sed`/`awk` coverage — these seven utilities are the smaller tools most frequently chained alongside those three in real pipelines — and depends on §43's redirection/pipe mechanics for how data actually flows between each stage. `find`'s file-matching criteria overlap conceptually with the filesystem-navigation groundwork in §21 (Part 3), applied here to search-by-attribute rather than known-path access. §50 (next) closes out Part 6 with regular expressions in depth — the pattern-matching syntax `grep`, `sed`, and (implicitly) several of this section's `-name`/glob-style matches have been using informally throughout.

**Next Section:** §50 — `Section-50-Part6-Regular-Expressions.md`
