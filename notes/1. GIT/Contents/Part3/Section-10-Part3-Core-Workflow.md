# Section 10 (Part 3): The Core Workflow — status, add, commit, diff, log

## 1. Definition

**Plain language:** This is the loop you run dozens of times a day: look at what changed (`status`), decide what goes into the next snapshot (`add`), record it (`commit`), and later look back at what happened (`diff`, `log`). Everything else in Git is either preparation for this loop or a variation on it.

**Precise:** `git status` reports the working directory and index state relative to `HEAD`'s tree; `git add` copies content into a blob object and updates the index ([§4](../Part2/Section-04-Part2-Git-Architecture-Three-Areas.md)); `git commit` builds a tree object from the index and a new commit object pointing at it, then advances the current branch ref ([§4](../Part2/Section-04-Part2-Git-Architecture-Three-Areas.md)); `git diff` compares two of {working directory, index, a commit} depending on flags; `git log` walks the commit graph from a starting point (default `HEAD`) following parent links. None of these commands introduce new concepts beyond the three-areas model from [§4](../Part2/Section-04-Part2-Git-Architecture-Three-Areas.md) — this section is about fluency with their day-to-day surface, not new architecture.

## 2. Why It Exists / Problem It Solves

1. **You need constant visibility into "what's different right now."** Without a fast, cheap status check, every commit would be a leap of faith. `git status` answers "what have I touched?" in local, near-instant time ([§4](../Part2/Section-04-Part2-Git-Architecture-Three-Areas.md)).
2. **Not every edit belongs in the next commit.** `git add` exists so you can curate — stage exactly the changes that form one coherent unit of work, even down to individual hunks, and leave the rest for later (the hunk-level staging walkthrough below).
3. **A commit needs a permanent, reviewable boundary.** `git commit` is the moment uncommitted, mutable work becomes an immutable, addressable point in history ([§5](../Part2/Section-05-Part2-Object-Model.md)) — everything before it can still be freely changed; everything after requires deliberate history-rewriting tools ([§15](../Part4/Section-15-Part4-Undoing-Things.md)).
4. **You need to inspect before and after committing.** `git diff` in its various forms answers "what exactly am I about to stage/commit/have I already committed" — the single most common source of "wait, what did I just do" confusion is not knowing which of these three comparisons you're looking at.
5. **History is only useful if you can navigate it.** `git log` and its flags turn the commit graph ([§5](../Part2/Section-05-Part2-Object-Model.md), [§6](../Part2/Section-06-Part2-References-Branches-HEAD-Tags-Reflog.md)) from an abstract DAG into something a human can actually scan, search, and reason about day to day.

## 3. `git status` — What Changed

### 3.1 Long format (the default)

```bash
# Purpose: see everything Git currently knows about your working directory and index
$ git status
On branch main
Changes to be committed:
  (use "git restore --staged <file>..." to unstage)
        modified:   src/app.py

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
        modified:   README.md

Untracked files:
  (use "git add <file>..." to include in what will be committed)
        scratch.log
```

Three buckets, always in this order: **staged** (index differs from `HEAD`), **unstaged** (working directory differs from index, for already-tracked files), **untracked** (files Git has never been told to track). A single file can even appear staged _and_ unstaged simultaneously if you edited it again after `git add` — the index holds one version, the working directory holds a newer one, both differ from `HEAD` and from each other.

### 3.2 Short format

```bash
# Purpose: compact, script-friendly status — one line per changed path
$ git status --short
 M README.md
M  src/app.py
?? scratch.log
```

Two columns matter: the **first character** is the index-vs-HEAD state (staged), the **second** is the working-directory-vs-index state (unstaged). `M ` means staged-modified with no further unstaged edits; ` M` means unstaged-modified with nothing staged; `MM` means both — staged one version, then edited again. `??` means untracked.

| Code | Meaning                                                                                            |
| ---- | -------------------------------------------------------------------------------------------------- |
| `??` | Untracked                                                                                          |
| `A ` | Newly added to the index                                                                           |
| `M ` | Modified, staged                                                                                   |
| ` M` | Modified, not staged                                                                               |
| `MM` | Staged, then modified again                                                                        |
| `D ` | Deleted, staged                                                                                    |
| ` D` | Deleted, not staged                                                                                |
| `R ` | Renamed (staged)                                                                                   |
| `UU` | Unmerged — both sides changed, conflict during merge ([§13](../Part4/Section-13-Part4-Merging.md)) |

### 3.3 Porcelain format

```bash
# Purpose: a stable, version-independent output format for scripts and tooling
$ git status --porcelain
 M README.md
M  src/app.py
?? scratch.log
```

`--porcelain` looks identical to `--short` for simple cases but is a **guaranteed-stable contract** — Git promises not to change its format across versions, whereas the human-facing `--short`/long formats can gain new decorations over time. Any CI script, pre-commit hook ([§24](../Part6/Section-24-Part6-Git-Hooks-Automation.md)), or tool parsing `git status` output should use `--porcelain`, never the long format, and ideally `--porcelain=v2` for even more explicit machine-readable fields (rename tracking, submodule state).

> ⚠️ **Common confusion to preempt:** `git status --short` and `git status --porcelain` produce the same output for the common cases shown above, which tempts people to treat them as interchangeable. They aren't — `--short` is documented as subject to change for human readability; `--porcelain` is the one with a compatibility guarantee. Script against `--porcelain`.

## 4. `git add` — Staging Changes

### 4.1 Basics

```bash
# Purpose: stage one specific file
$ git add src/app.py

# Purpose: stage several explicit files
$ git add src/app.py README.md

# Purpose: stage everything inside the current directory and below
$ git add .
```

### 4.2 `-A` vs `.` vs `-u` — a genuinely confusing trio

| Command                   | Stages new files | Stages modified files | Stages deletions | Scope                                                  |
| ------------------------- | ---------------- | --------------------- | ---------------- | ------------------------------------------------------ |
| `git add .`               | Yes              | Yes                   | Yes              | Current directory and below only                       |
| `git add -A` (`--all`)    | Yes              | Yes                   | Yes              | **Entire repository**, regardless of current directory |
| `git add -u` (`--update`) | No               | Yes                   | Yes              | Entire repository (already-tracked files only)         |

> ⚠️ **Critical clarification:** In modern Git (2.x, since the 2.0 behavior change), `git add .` run from the repository root and `git add -A` run from anywhere are effectively equivalent — both cover the whole repo and both pick up deletions. The historically dangerous gotcha was **pre-2.0 Git**, where `git add .` ignored deletions entirely (you needed `git add -A` for those). If you're on a current Git version this legacy trap doesn't bite, but the distinction is still worth knowing cold: `.` is scoped to your current working directory (so running it from a subfolder only stages that subfolder), while `-A` and `-u` always operate repo-wide regardless of where you run them.

```bash
# Purpose: stage only modifications and deletions to files Git already tracks — never stages new/untracked files
$ git add -u
```

`-u` is the deliberate choice when you want "capture everything I changed in tracked files" but are not yet ready to start tracking some new scratch file sitting in the working directory.

### 4.3 `git add -p` — Interactive Patch Staging

The single most powerful everyday staging tool: stage individual **hunks** (contiguous blocks of changed lines) within a file, not the whole file at once.

```bash
# Purpose: interactively review and select hunks to stage, one at a time
$ git add -p src/app.py
diff --git a/src/app.py b/src/app.py
index 3f2a1c9..8b1d4e2 100644
--- a/src/app.py
+++ b/src/app.py
@@ -10,6 +10,9 @@ def handler(request):
     if not request.user:
         raise AuthError()
+
+    # TODO: rate limit here
     return process(request)
@@ -40,3 +43,5 @@ def process(request):
     return response
+
+print("debugging leftover")
Stage this hunk [y,n,q,a,d,s,e,?]?
```

Key responses at the prompt:

| Key | Action                                                                                                          |
| --- | --------------------------------------------------------------------------------------------------------------- |
| `y` | Stage this hunk                                                                                                 |
| `n` | Skip this hunk                                                                                                  |
| `s` | **Split** this hunk into smaller hunks (when Git grouped unrelated changes together)                            |
| `e` | **Edit** the hunk manually in your editor — the ultimate fallback for surgical control down to individual lines |
| `q` | Quit — stop reviewing this and all remaining files                                                              |
| `a` | Stage this hunk and all remaining hunks in this file                                                            |
| `d` | Skip this hunk and all remaining hunks in this file                                                             |

This is exactly the scenario from [§4](../Part2/Section-04-Part2-Git-Architecture-Three-Areas.md): a real bug fix and an unrelated debug `print()` sitting in the same file. `git add -p`, answer `y` to the bug fix hunk and `n` (or `s` then selectively `y`/`n`) to the debug line, produces a commit containing only the fix, while the `print()` stays unstaged and uncommitted, ready to be deleted or committed separately.

> 💡 **Tip:** `git add -p` operates per-file by default when you name a file, or walks every modified tracked file if you run it with no path. `git add -i` is the broader interactive menu `-p` is one mode of — rarely used directly, since `-p` covers the common case.

### 4.4 Unstaging

```bash
# Purpose: remove a file from the staging area without touching working directory content
$ git restore --staged src/app.py
```

Covered fully as part of the three-areas command table in [§4](../Part2/Section-04-Part2-Git-Architecture-Three-Areas.md); the modern `git restore` subcommand replaced the older, more overloaded `git reset <file>` for this specific purpose (both still work).

## 5. `git commit` — Recording a Snapshot

### 5.1 Basic forms

```bash
# Purpose: commit with an inline message
$ git commit -m "Fix auth token refresh race condition"

# Purpose: commit with no -m opens your configured core.editor (§8) for a longer message
$ git commit
```

```bash
# Expected output
[main 4a1f2c9] Fix auth token refresh race condition
 1 file changed, 3 insertions(+), 1 deletion(-)
```

### 5.2 `-am` — stage and commit tracked files in one step

```bash
# Purpose: stage all MODIFIED tracked files (not new/untracked ones) and commit, in one command
$ git commit -am "Update config defaults"
```

`-a` is shorthand for "run `git add -u` first, then commit" — it stages modifications and deletions to files Git already tracks, but it **never** picks up new untracked files, exactly like `-u` in the add-variants comparison above. This is a frequent point of confusion: `-am` feels like "commit everything," but a brand-new file you forgot to `git add` at least once will silently stay untracked and uncommitted.

> ⚠️ **Common confusion to preempt:** `git commit -am` skips the review step entirely — there is no chance to inspect a diff before it's committed, unlike the deliberate `add` then `diff --staged` then `commit` sequence. It's a legitimate convenience for small, obviously-correct changes to files you're already tracking, but reaching for it as a default habit reintroduces exactly the "committed something I didn't mean to" risk the index was built to prevent ([§4](../Part2/Section-04-Part2-Git-Architecture-Three-Areas.md)).

### 5.3 `--amend` — a preview

```bash
# Purpose: replace the most recent commit with a new one (new message and/or new staged content)
$ git commit --amend -m "Corrected commit message"
```

`--amend` doesn't edit history in place — it builds an entirely new commit object with the old one's parent, then moves the branch ref to point at the new commit; the original commit object still exists, unreferenced, until garbage collected ([§7](../Part2/Section-07-Part2-Inside-Git-Loose-Objects-Packfiles-GC.md), [§29](../Part7/Section-29-Part7-Maintenance-Performance-Troubleshooting.md)). This makes it a genuinely dangerous operation to run on a commit **already pushed and visible to others**, because it changes the commit's hash, which diverges your local branch from anyone who already pulled the old version. The full mechanics — including safely amending, force-pushing conventions, and recovering an amend you regret via the reflog — belong to undo operations in [§15](../Part4/Section-15-Part4-Undoing-Things.md); the only thing to internalize here is that `--amend` is a **workflow-level convenience for fixing your last commit before anyone else has seen it**, not a way to edit history that's already shared.

## 6. `git diff` — Comparing States

This is the command where knowing exactly **which two things are being compared** matters most.

```
 Working Directory          Index (staged)              HEAD (last commit)
┌─────────────────┐        ┌─────────────────┐         ┌─────────────────┐
│  file.txt: "v3" │        │  file.txt: "v2" │         │  file.txt: "v1" │
└─────────────────┘        └─────────────────┘         └─────────────────┘
         │                          │                             │
         └────── git diff ──────────┘                             │
           (unstaged changes:                                     │
            "what haven't I staged yet")                          │
                                     │                            │
                                     └──── git diff --staged ─────┘
                                       (staged changes:
                                        "what have I staged
                                         but not committed")

         └──────────────────── git diff HEAD ──────────────────────┘
                (everything different from the last commit,
                 staged AND unstaged combined)
```

### 6.1 The three core comparisons

```bash
# Purpose: working directory vs index — what you HAVEN'T staged yet
$ git diff

# Purpose: index vs HEAD — what you've staged but not yet committed (also spelled --cached, identical meaning)
$ git diff --staged
$ git diff --cached

# Purpose: working directory vs HEAD — everything different from the last commit, staged and unstaged combined
$ git diff HEAD
```

| Command                            | Compares            | Answers                                         |
| ---------------------------------- | ------------------- | ----------------------------------------------- |
| `git diff`                         | Working dir ↔ Index | "What haven't I staged yet?"                    |
| `git diff --staged` (= `--cached`) | Index ↔ HEAD        | "What have I staged but not committed?"         |
| `git diff HEAD`                    | Working dir ↔ HEAD  | "What's different from my last commit, period?" |

### 6.2 Comparing arbitrary commits, branches, and files

```bash
# Purpose: compare two specific commits
$ git diff a1b2c3d 8e9f0a1

# Purpose: compare two branch tips
$ git diff main feature-login

# Purpose: restrict a diff to one file or path
$ git diff main feature-login -- src/app.py

# Purpose: summary of files changed and line counts rather than the full patch
$ git diff --stat HEAD~3
```

> 💡 **Tip:** `git diff branchA branchB` shows the changes needed to turn `branchA` into `branchB` — order matters, and reversing it inverts every `+`/`-`. This is the same "direction" gotcha that trips people up in merge conflict markers ([§13](../Part4/Section-13-Part4-Merging.md)).

## 7. `git log` — Everyday History Reading

Full mastery — every filter, format placeholder, and history-searching flag — is [§19](../Part4/Section-19-Part4-Interrogating-History.md). This is the working vocabulary you reach for constantly while developing.

### 7.1 The default view

```bash
# Purpose: full log, newest first
$ git log
commit 4a1f2c9d8e3b7a6f5c4d3e2b1a0f9e8d7c6b5a4f
Author: Harshit Kandhwey <harshitkandhwey@gmail.com>
Date:   Fri Jul 25 09:14:02 2026 +0530

    Fix auth token refresh race condition
```

### 7.2 Compact, everyday flags

```bash
# Purpose: one line per commit — hash + subject, the single most-used log invocation
$ git log --oneline
4a1f2c9 Fix auth token refresh race condition
8e9f0a1 Update config defaults
b2c3d4e Initial notes

# Purpose: visualize branch/merge topology as ASCII graph lines alongside the log
$ git log --oneline --graph --all
* 4a1f2c9 (HEAD -> main) Fix auth token refresh race condition
| * 7d6e5f4 (feature-login) Add login form validation
|/
* 8e9f0a1 Update config defaults

# Purpose: show which files changed and how much, per commit
$ git log --stat
```

```bash
# Expected output for --stat (abbreviated)
commit 4a1f2c9d8e3b7a6f5c4d3e2b1a0f9e8d7c6b5a4f
    Fix auth token refresh race condition
 src/app.py | 4 +++-
 1 file changed, 3 insertions(+), 1 deletion(-)
```

| Flag                                    | Effect                                                                                                        |
| --------------------------------------- | ------------------------------------------------------------------------------------------------------------- |
| `--oneline`                             | One compact line per commit (short hash + subject)                                                            |
| `--graph`                               | ASCII-art lines showing branch/merge structure                                                                |
| `--all`                                 | Include every ref (all local branches, not just the current one) — commonly combined with `--oneline --graph` |
| `--stat`                                | Per-commit summary of files touched and line counts                                                           |
| `-p` / `--patch`                        | Full diff content for each commit, not just metadata                                                          |
| `-n <N>`                                | Limit to the last N commits, e.g. `-5`                                                                        |
| `--author="name"`                       | Filter by author                                                                                              |
| `--since="2 weeks ago"` / `--until=...` | Filter by date, accepts natural-language-ish relative dates                                                   |

### 7.3 Pretty formats

```bash
# Purpose: fully custom, script-friendly one-liner format
$ git log --pretty=format:"%h %ad %s (%an)" --date=short
4a1f2c9 2026-07-25 Fix auth token refresh race condition (Harshit Kandhwey)
8e9f0a1 2026-07-22 Update config defaults (Harshit Kandhwey)
```

Common placeholders: `%h` (abbreviated hash), `%H` (full hash), `%an` (author name), `%ad` (author date), `%s` (subject line), `%b` (body). This is the mechanism behind the `lg` alias built in [§8](./Section-08-Part3-Installation-Configuration.md) (`log --oneline --graph --all --decorate`) — `--decorate` is what prints branch/tag names like `(HEAD -> main)` next to the commits that carry them.

> 💡 **Tip:** Reach for `git log --oneline --graph --all` constantly while learning branching ([§12](../Part4/Section-12-Part4-Branching-In-Depth.md)) and merging ([§13](../Part4/Section-13-Part4-Merging.md)) — it's the fastest way to build an accurate mental picture of the actual commit graph, rather than guessing at it.

## 8. End-to-End Example: Edit → Partial Stage → Commit → Log

```bash
# Purpose: a realistic sequence combining every command from this section

# 1. Edit two unrelated things in the same file
$ cat src/app.py
def handler(request):
    if not request.user:
        raise AuthError()
    return process(request)

$ vim src/app.py    # add a real fix AND a stray debug print in one editing session
$ git diff
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,7 @@
 def handler(request):
     if not request.user:
         raise AuthError()
+    if request.token_expired():
+        refresh_token(request)
     return process(request)
+print("checking handler behavior")

# 2. Stage only the real fix, leaving the debug print unstaged
$ git add -p src/app.py
# ... answer y to the token-refresh hunk, n to the print() hunk ...

# 3. Confirm exactly what's about to be committed
$ git diff --staged
diff --git a/src/app.py b/src/app.py
--- a/src/app.py
+++ b/src/app.py
@@ -1,4 +1,6 @@
 def handler(request):
     if not request.user:
         raise AuthError()
+    if request.token_expired():
+        refresh_token(request)
     return process(request)

# 4. Confirm the debug print is still sitting unstaged, untouched
$ git diff
diff --git a/src/app.py b/src/app.py
@@ -4,3 +4,4 @@ def handler(request):
     return process(request)
+print("checking handler behavior")

# 5. Commit only the reviewed, staged fix
$ git commit -m "Refresh auth token before processing expired-token requests"
[main 9c1d2e3] Refresh auth token before processing expired-token requests
 1 file changed, 2 insertions(+)

# 6. Verify it landed as its own clean commit
$ git log --oneline -3
9c1d2e3 Refresh auth token before processing expired-token requests
4a1f2c9 Fix auth token refresh race condition
8e9f0a1 Update config defaults

# 7. The debug print is STILL sitting uncommitted in the working directory
$ git status --short
 M src/app.py
```

This is the loop in full: `status` for orientation, `add -p` for deliberate curation, `diff --staged` for a final pre-commit review, `commit` to make it permanent, `log` to confirm, and `status` again showing the leftover debug line was never swept in by accident — exactly the outcome [§4](../Part2/Section-04-Part2-Git-Architecture-Three-Areas.md) promised the index would enable.

## 9. Troubleshooting

| Symptom                                                         | Likely cause                                                          | Fix                                                                                   |
| --------------------------------------------------------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| `git commit` opens an editor unexpectedly                       | No `-m` passed                                                        | Either supply `-m "message"` or write the message in the opened editor and save/close |
| "Changes not staged for commit" reappears right after `git add` | File was edited again after staging                                   | `git add` once more to re-stage the latest content (classic `MM` status code)         |
| `git diff` shows nothing but you know you changed a file        | The change is already staged — you're looking at the wrong comparison | Use `git diff --staged` instead                                                       |
| `git commit -am` didn't include a new file                      | `-a`/`-am` never stages untracked files                               | `git add <newfile>` explicitly first, or use `git add -A` before committing           |
| `git log` shows far fewer commits than expected                 | Missing `--all`; you're only seeing the current branch's ancestry     | Add `--all`, or check you're on the branch you think you're on                        |

## 10. Interview Questions

**[Beginner] Q1. What's the difference between `git diff` and `git diff --staged`?**
**Model answer:** `git diff` with no flags compares the working directory against the index — it shows changes you've made but haven't run `git add` on yet. `git diff --staged` (equivalently `--cached`) compares the index against the last commit (`HEAD`) — it shows exactly what will go into the next commit if you run `git commit` right now. They can show completely different content simultaneously: if you edit a file, stage it, then edit it again, `git diff --staged` shows the first edit and plain `git diff` shows the second.

**[Intermediate] Q2. Why does `git add -p` matter, and what problem does it solve that whole-file `git add` doesn't?**
**Model answer:** `git add -p` lets you stage individual hunks — contiguous blocks of changed lines — within a file rather than the entire file at once. This matters because real editing sessions often mix unrelated changes in the same file: a genuine bug fix alongside leftover debug statements, or two logically separate improvements. Whole-file `git add` forces an all-or-nothing choice, which either bundles unrelated changes into one commit (making history harder to review, bisect, or revert cleanly) or forces you to manually comment out code before staging. `-p` lets you build precisely-scoped commits directly from a messier working session, with `e` (manual hunk editing) as the escape hatch for splitting changes finer than Git's automatic hunk boundaries allow.

**[Senior] Q3. A teammate ran `git commit -am "wip"` and pushed. Walk through what is and isn't in that commit, and what you'd check.**
**Model answer:** `-a` stages modifications and deletions to already-tracked files only — it never stages new, untracked files. So the commit contains every change to files Git was already tracking at the time, but if the teammate created any new file during that work session and never ran `git add` on it at least once, that file is still untracked and simply isn't in the commit at all, possibly silently missing from what they intended to ship. I'd run `git show --stat <commit>` to see exactly which files landed, then `git status` on their branch (or ask them to check locally) for any lingering untracked files that should have been included. Separately, `-am` skips any staged-diff review, so it's worth diffing the commit against its parent to sanity-check the actual content, not just the file list, especially since "wip" as a message tells you nothing about intent for future archaeology ([§19](../Part4/Section-19-Part4-Interrogating-History.md) covers writing better messages and searching history when messages like this exist).

## 11. Common Misconceptions

1. **"`git add .` and `git commit -am` do the same thing."** `add .` stages new, modified, and deleted files (repo-wide behavior in modern Git, scoped to the current directory and below). `commit -am` only auto-stages modifications and deletions to already-tracked files — it never picks up new untracked files. Conflating them is a common source of "why isn't my new file in this commit?"
2. **"`git diff` with no arguments shows my latest changes, period."** It shows only the working-directory-vs-index comparison. Anything already staged is invisible to plain `git diff` — you need `--staged` for that half of the picture.
3. **"`--amend` edits the existing commit in place."** It creates a brand-new commit object and moves the branch ref to it; the old commit object still exists, unreferenced, until garbage collected. This matters enormously once the commit has been pushed ([§15](../Part4/Section-15-Part4-Undoing-Things.md)).
4. **"`git status --short` and `git status --porcelain` are just two names for the same thing."** They usually render identically today, but only `--porcelain` carries a stability guarantee across Git versions — scripts and hooks should target it specifically.

## 12. 🔑 Key Takeaways

- `git status` (long, `--short`, `--porcelain`) reports the same three-areas comparison from [§4](../Part2/Section-04-Part2-Git-Architecture-Three-Areas.md) in three different verbosity levels; `--porcelain` is the only one scripts should parse.
- `git add` has meaningful variants: plain paths, `.` vs `-A` vs `-u` (scope and what gets swept up differs), and `-p` for hunk-level curation — the direct mechanism for building clean, reviewable commits.
- `git commit -am` is a convenience that stages tracked-file modifications only, never new files, and skips the pre-commit review step; `--amend` replaces the last commit with a new object rather than editing history in place.
- `git diff` has three everyday forms distinguished purely by which two areas are being compared: plain (working vs index), `--staged` (index vs HEAD), and `HEAD` (working vs HEAD combined).
- `git log --oneline --graph --all` is the fastest way to see the real shape of the commit graph; pretty formats (`--pretty=format:...`) build custom, scriptable output.

## 13. Related Concepts & What's Next

Everything here operates on the assumption of a single line of history; [§12](../Part4/Section-12-Part4-Branching-In-Depth.md) introduces branching, at which point `git log --graph` stops being a curiosity and becomes essential daily reading. `--amend` previewed here gets its full treatment — along with `reset`, `revert`, `restore`, and the reflog as a safety net — in [§15](../Part4/Section-15-Part4-Undoing-Things.md) (Undoing Things). `git log`'s complete surface, including `git bisect`, range syntax (`A..B`, `A...B`), and searching history by content (`git log -S`/`-G`), is [§19](../Part4/Section-19-Part4-Interrogating-History.md). [§11](./Section-11-Part3-Ignoring-Controlling-Files.md), immediately next, covers keeping files out of this workflow entirely via `.gitignore`.
