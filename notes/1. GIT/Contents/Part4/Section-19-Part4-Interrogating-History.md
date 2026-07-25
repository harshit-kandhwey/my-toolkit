# Section 19 (Part 4): Interrogating History — log Mastery, blame, bisect, grep, shortlog

## 19.1 Definition

**Plain language:** Once history exists, you often need to *ask it questions*: who wrote this line, when did this bug first appear, which commits touched this file last month, was a specific string ever present anywhere in the project's past. This section is the investigative toolkit for querying history rather than changing it.

**Precise:** Git provides a family of read-only history-interrogation commands, all operating over the same commit graph and object database established in §5-§7: `git log` (commit history traversal and filtering), `git blame` (per-line attribution), `git bisect` (binary search over history for a regression), `git grep` (content search across tracked trees, including historical ones), and `git shortlog` (aggregate contributor summaries). None of these mutate any ref, object, or working-directory state.

## 19.2 Why It Exists / Problem It Solves

§10 covered `git log` at the level needed for daily workflow — "what did I just commit." Real investigative work needs far more: "which commit introduced this exact string," "who last touched this specific line and why," "which of these 200 commits between a known-good and known-bad state broke the build," "has this function ever existed in a deleted file." Without dedicated tooling for these questions, debugging a regression or understanding unfamiliar code would mean manually eyeballing `git log -p` output — infeasible at any real repository size.

## 19.3 `git log` Deep Dive — Beyond the Basics

### 19.3.1 Graph, decoration, and scope flags

```bash
# Purpose: visualize the FULL branch/merge topology across every ref, not just the current branch
$ git log --graph --oneline --decorate --all
```

Expected output (illustrative):
```
* 9f2c1a4 (HEAD -> main, origin/main) Merge branch 'feature-search'
|\
| * 7c2a9f1 (feature-search) Add search results rendering
| * a1b2c3d Add search input
|/
* 1a2b3c4 Previous stable commit
```

| Flag | Effect |
|---|---|
| `--graph` | ASCII-art the branch/merge topology alongside each entry |
| `--oneline` | One line per commit: short hash + subject |
| `--decorate` | Show which refs (branches, tags, HEAD) point at each commit |
| `--all` | Include every ref (all local branches, all remote-tracking branches), not just the current branch's ancestry |

> 💡 **Tip:** `git log --graph --oneline --decorate --all` is common enough as a daily-driver command that most engineers alias it — recall §8.6's `alias.lg` example configured exactly this.

### 19.3.2 Custom formatting: `--pretty=format:`

```bash
# Purpose: fully custom output — hash, author, relative date, subject
$ git log --pretty=format:"%h | %an | %ar | %s"
```

Expected output:
```
9f2c1a4 | Harshit Kandhwey | 2 hours ago | Merge branch 'feature-search'
7c2a9f1 | Harshit Kandhwey | 3 hours ago | Add search results rendering
```

| Placeholder | Meaning |
|---|---|
| `%h` / `%H` | Abbreviated / full commit hash |
| `%an` / `%ae` | Author name / email |
| `%ad` / `%ar` | Author date (absolute) / author date (relative, "2 hours ago") |
| `%s` | Subject line (first line of the commit message) |
| `%cn` / `%cd` | Committer name / committer date — distinct from author, per §5.5.3 |

### 19.3.3 Filtering by author, date, and path

```bash
# Purpose: commits by a specific author
$ git log --author="Harshit"

# Purpose: commits within a date range
$ git log --since="2026-06-01" --until="2026-07-01"

# Purpose: commits that touched a SPECIFIC PATH only, ignoring everything else
$ git log -- src/payments.js

# Purpose: follow a file's history THROUGH renames, not just its current name
$ git log --follow -- src/payments.js
```

`--follow` matters concretely: `git log -- <path>` alone stops at the commit where a file was renamed *to* its current name, silently hiding all history from before the rename — `--follow` continues tracing backward through the rename boundary.

### 19.3.4 Pickaxe search: `-S` and `-G`

```bash
# Purpose: find every commit that CHANGED THE NUMBER OF OCCURRENCES of an exact
# string — i.e., commits that added or removed this string, not ones that
# merely touched a file containing it
$ git log -S "MAX_RETRY_COUNT"

# Purpose: find every commit whose diff matches a REGEX pattern
$ git log -G "function\s+getDiscount"
```

| | `-S` (pickaxe) | `-G` (regex pickaxe) |
|---|---|---|
| Matches | Exact string, and only where its **occurrence count changed** | Any line added/removed matching a regex, regardless of count change |
| Use case | "When was this exact constant/function name introduced or removed" | "When did any line matching this pattern change" |

> ⚠️ **Common confusion to preempt:** `-S "text"` does **not** match every commit whose diff merely contains "text" somewhere — it specifically finds commits where the *number of times* "text" appears changed between the old and new version of a file. A commit that moves a line containing "text" from one place to another without changing the total count won't match `-S`, which surprises people expecting a simple full-text diff search.

## 19.4 `git blame` — Per-Line Attribution

```bash
# Purpose: show who last touched each line of a file, and in which commit
$ git blame pricing.js
```

Expected output (illustrative):
```
a1b2c3d4 (Harshit Kandhwey 2026-05-10 14:22:00 +0530  1) function getDiscount(user) {
7c2a9f1e (Priya Sharma      2026-06-14 09:11:00 +0530  2)   return user.isPremium ? 0.25 : 0.10;
a1b2c3d4 (Harshit Kandhwey 2026-05-10 14:22:00 +0530  3) }
```

```bash
# Purpose: ignore WHITESPACE-only changes when attributing a line
$ git blame -w pricing.js

# Purpose: detect lines MOVED OR COPIED from elsewhere, attributing them to
# their true original commit rather than the commit that merely relocated them
$ git blame -C pricing.js
```

> ⚠️ **Critical clarification: blame shows who last touched a line, not who's "responsible" for it.** A line reformatted by an automated linter commit, or moved verbatim during a refactor, shows that reformatting/refactoring commit's author as the "blame" target — not the person who wrote the actual logic, unless `-w`/`-C` are used to see past superficial changes. Treating raw `git blame` output as an accusation of authorship or fault, without checking what the change actually *was*, is a common and unfair misreading — always open the referenced commit (`git show <hash>`) before drawing conclusions.

## 19.5 `git bisect` — Systematic Regression Search

When you know a specific commit was **good** and a later one is **bad**, but not which of potentially hundreds of commits in between introduced the regression, `git bisect` performs an automated binary search over the commit graph, checking out (in detached HEAD, exactly as described in §6.4.3) successive candidate commits for you to test.

### 19.5.1 Manual workflow

```bash
$ git bisect start
$ git bisect bad                    # current HEAD is known bad
$ git bisect good v1.4.0            # this known-good tag/commit

# Git checks out a commit roughly halfway between good and bad
Bisecting: 47 revisions left to test after this (roughly 6 steps)
[7c2a9f1...] Add caching layer

# You manually test THIS commit, then tell bisect the result
$ git bisect good        # or: git bisect bad
# Git narrows the range and checks out the next candidate automatically

# ... repeat until Git identifies the exact first bad commit ...
7c2a9f1e is the first bad commit

$ git bisect reset       # return to your original branch/commit, exit bisect mode
```

Each `good`/`bad` judgment halves the remaining search space — `log₂(n)` steps for `n` candidate commits, which is why bisecting even hundreds of commits typically takes under ten manual test cycles.

### 19.5.2 Automated workflow: `git bisect run`

```bash
# Purpose: fully automate the search by supplying a script that exits 0
# for "good" and non-zero for "bad"
$ git bisect start
$ git bisect bad HEAD
$ git bisect good v1.4.0
$ git bisect run npm test -- --grep "pagination"
```

Git runs the given command at every candidate commit automatically, interprets its exit code, and narrows the search with zero manual intervention until it reports the exact first bad commit — the highest-leverage form, since a fast, reliable, automatable reproduction script turns a potentially day-long manual hunt into a few minutes of unattended searching.

> 💡 **Tip:** `git bisect run` requires the test script itself to be checkable out consistently across the bisected range — if the script (or its dependencies) didn't exist at older commits, or its own behavior changed, results become unreliable. This is a real, practical constraint worth checking before trusting an automated bisect over a wide historical range.

## 19.6 `git grep` — Searching Tracked Content (and History)

```bash
# Purpose: search the CURRENT working tree's tracked content for a pattern
$ git grep "TODO: remove before release"

# Purpose: search a HISTORICAL tree WITHOUT checking it out
$ git grep "getDiscount" v1.4.0

# Purpose: show line numbers and limit to a file type
$ git grep -n "getDiscount" -- "*.js"
```

| | `git grep` | OS `grep`/`ripgrep` over the working directory |
|---|---|---|
| Respects `.gitignore` (§11) | Yes, automatically — never searches ignored files/build output | No — searches everything on disk unless manually excluded |
| Search historical commits without checkout | **Yes** — `git grep <pattern> <commit>` searches that commit's tree directly | No — requires checking out or cloning that state first |
| Requires being inside a Git repository | Yes | No |
| Speed on large repos | Generally fast; can leverage Git's own tree/index structures | Depends entirely on the tool and file count on disk |

`git grep <pattern> <commit>` is the specific capability worth internalizing: you can search *any past commit's* content directly, with no `checkout`, no detached HEAD, no working-directory disruption at all — genuinely useful for "did this string ever exist anywhere in history" investigations combined with `-S`/`-G` (19.3.4) or a manual walk across tags.

## 19.7 `git shortlog` — Contributor Summaries

```bash
# Purpose: summarize commit counts per author, sorted by count (-n), condensed (-s)
$ git shortlog -sn
```

Expected output:
```
   142  Harshit Kandhwey
    58  Priya Sharma
    12  Contractor Bot
```

```bash
# Purpose: restrict to a date range or branch, same filters as `git log`
$ git shortlog -sn --since="2026-01-01"
```

`git shortlog` groups `git log` output by author, collapsing potentially thousands of individual commit lines into a compact per-contributor summary — useful for release notes ("thanks to these N contributors"), rough activity auditing, or a quick sanity check on whether a suspiciously large commit count belongs to a human or an automated bot account.

## 19.8 Hands-On — Combining Tools for a Real Investigation

```bash
# Scenario: a bug appeared sometime after v1.4.0; find and fix it

# Step 1: narrow the search space with pickaxe, in case a specific known
# constant's introduction is a likely suspect
$ git log -S "MAX_RETRY_COUNT" --oneline

# Step 2: bisect systematically if the pickaxe search doesn't immediately
# identify the culprit
$ git bisect start
$ git bisect bad HEAD
$ git bisect good v1.4.0
$ git bisect run ./run-regression-test.sh
# ... Git reports the first bad commit ...
$ git bisect reset

# Step 3: once the culprit commit is known, understand WHO wrote the
# specific line and WHY, before assuming carelessness
$ git blame -C -w src/retry.js
$ git show <culprit-hash>

# Step 4: check whether this exact bug pattern ever existed before,
# searching historical trees directly
$ git grep -n "retryCount" v1.0.0
```

## 19.9 Production & Enterprise Usage

- Incident postmortems routinely use `git bisect run` against an automated regression test as the fastest, most objective way to identify a root-cause commit, replacing much slower manual code review of the entire suspect range.
- `git blame` output is a standard input to code-review tooling and IDE integrations (inline "who last changed this line" annotations), though senior engineers know to treat it as a starting point for a conversation, not a verdict, per 19.4's caveat.
- `git shortlog -sn` output frequently appears in release notes, contributor-recognition tooling, and open-source project reporting (e.g., "N contributors made M commits since the last release").
- Security incident response sometimes uses `git log -S`/`-G` and `git grep` across historical commits specifically to determine whether a secret or vulnerable pattern was ever introduced anywhere in history, not just in the current tree — directly feeding into the secret-remediation workflow of §28.

## 19.10 Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `git log -- <path>` history looks incomplete, stops abruptly | File was renamed at some point; plain path filtering doesn't cross rename boundaries | Add `--follow` |
| `git blame` attributes an entire file to one recent commit, hiding real history | A mass reformat/linter commit rewrote every line's whitespace/formatting | `git blame -w` (ignore whitespace) and `-C` (detect moved/copied lines) to see past it |
| `git bisect run` produces an unreliable or wrong result | The test script's own behavior, dependencies, or build tooling changed across the bisected range, making old commits fail to build/test for unrelated reasons | Narrow the bisect range to avoid crossing major tooling changes, or mark unbuildable commits with `git bisect skip` |
| `git grep` finds nothing you're sure exists somewhere in history | Searching only the current tree by default, not historical commits | Specify a commit/tag/branch explicitly: `git grep <pattern> <ref>`, or a range across multiple refs |

## 19.11 Interview Questions

**[Beginner] Q1. What's the difference between `git log -S` and a plain `git log --grep`?**
**Model answer:** `git log --grep` searches **commit messages** for a pattern — it tells you which commits' messages mention something. `git log -S` (pickaxe) searches the actual **content diffs**, finding commits where the number of occurrences of an exact string in the file content changed — i.e., where that string was actually added or removed from the codebase, regardless of what the commit message said. They answer different questions: one is about what people wrote in their messages, the other is about what actually changed in the code.

**[Intermediate] Q2. How does `git bisect` find a regression, and why is it efficient?**
**Model answer:** Given one commit known to be good and one known to be bad, `git bisect` performs a binary search over the commit graph between them: it checks out a commit roughly halfway between the two, you (or an automated script via `git bisect run`) test it and report good or bad, and Git uses that answer to eliminate half of the remaining candidates each time. This makes it logarithmic in the number of commits — a few hundred candidate commits typically resolve in under ten test cycles — dramatically faster than manually reviewing or testing every commit in the range one by one.

**[Intermediate] Q3. Why might `git blame` mislead you about who's "responsible" for a line of code?**
**Model answer:** `git blame` shows the most recent commit that touched a given line, not necessarily who wrote the underlying logic or who should be consulted about it. A line can show a recent author simply because an automated formatter, a mass rename, or an unrelated refactor touched it last, even though the actual logic was written by someone else years earlier. The `-w` flag ignores whitespace-only changes and `-C` detects moved or copied lines, both of which help blame attribute more accurately to genuine original authorship — but even then, the right practice is to open the referenced commit with `git show` and read what it actually did before treating blame output as a conclusion about responsibility.

**[Senior] Q4. Design a `git bisect run` workflow for finding a performance regression, and explain what could make the results unreliable.**
**Model answer:** I'd write a script that builds the project and runs a targeted performance benchmark, exiting 0 if a measured metric (e.g., request latency) stays under a defined threshold and non-zero otherwise, then run `git bisect start`, mark the current HEAD bad and a known-good older commit good, and hand the script to `git bisect run` to search unattended. Reliability risks: if the build system, dependency versions, or the benchmark script itself changed meaningfully across the bisected range, old commits might fail to build or run for reasons unrelated to the actual regression, producing a false "bad" result that isn't about performance at all — `git bisect skip` lets you mark such commits as untestable rather than wrongly good or bad, but a large enough tooling change partway through the range can still corrupt the search. I'd also flag that performance measurements carry noise, so a single-run pass/fail threshold can produce flaky bisect results; a more robust script would average multiple runs before deciding good or bad.

**[Senior] Q5. A security team asks whether an API key was ever committed to the repository at any point in its history, even if it's not present now. How do you answer this with Git's history tools, precisely?**
**Model answer:** I'd combine `git log -S "<the exact key or a distinctive fragment>"` across all branches (`--all`) to find any commit where that string's occurrence count changed — this catches both its introduction and its later removal — and `git grep "<pattern>" <ref>` against specific historical tags or commits for a more targeted check without needing to check anything out. I'd also widen the search with `-G` for a regex pattern if the exact key value isn't known but its format is (e.g., a known API key prefix pattern). Importantly, I'd be precise with the security team about what a negative result actually proves: these tools search the reachable commit graph, so anything already garbage-collected as truly unreferenced (e.g., from an old force-pushed rewrite that was never actually pushed anywhere else, or old enough to be pruned) may no longer be searchable this way — a genuinely thorough audit for a leaked secret also needs to consider the reflog (§6.6) and, since the secret may already have propagated to clones or forks before removal, treat rotation of the actual credential as mandatory regardless of what the history search finds, exactly the remediation posture §28 covers in full.

## 19.12 Common Misconceptions

1. **"`git log -S` searches for any commit whose diff contains this text."** It only matches commits where the *occurrence count* of the exact string changed — a line merely moved without changing the count won't match.
2. **"`git blame` tells you who's at fault for a line's problems."** It only shows who last touched that line, which is frequently an unrelated reformat, rename, or refactor commit, not the person who wrote the actual logic.
3. **"`git bisect` requires you to test every commit in the range."** It performs a binary search, typically needing only a logarithmic number of good/bad judgments relative to the total commit count.
4. **"`git grep` searches your history the way `git log -S` does."** By default it searches only the current working tree; searching history requires explicitly passing a commit/tag/branch, or a range of them.
5. **"`git log -- <path>` shows a file's complete history."** It stops at a rename boundary by default; `--follow` is required to trace history through renames.

## 19.13 🔑 Key Takeaways

- `git log` beyond the basics: `--graph --oneline --decorate --all` for topology, `--pretty=format:` for custom output, `--author`/`--since`/`--until`/`-- <path>` for filtering, `--follow` to cross rename boundaries, `-S`/`-G` (pickaxe) to search content-diff history for exact strings or regex patterns.
- `git blame` shows last-touched-by, not responsible-for; `-w` and `-C` help see past superficial reformats and moves to more meaningful attribution.
- `git bisect` performs a logarithmic-time binary search for a regression's first bad commit; `git bisect run` fully automates it given a pass/fail test script, with reliability depending on the script staying valid across the whole bisected range.
- `git grep` respects `.gitignore` and can search any historical tree directly by ref, with no checkout required — a capability plain OS `grep` cannot replicate without first materializing that state on disk.
- `git shortlog -sn` aggregates commit counts per contributor, the standard tool behind release-note "thanks to our contributors" sections.

## 19.14 Related Concepts & What's Next

This section closes Part 4: creating and combining branches (§12-13), rewriting history (§14), undoing mistakes (§15), setting work aside (§16), moving specific changes deliberately (§17), marking releases (§18), and now interrogating everything that's accumulated (§19). Part 5 moves outward from single-repository mechanics to collaboration at scale: remotes in full depth, SSH/HTTPS transport, collaboration models, branching strategies as team-level policy built on everything Part 4 taught, and Git hosting platforms including self-hosted servers and GUI clients.
