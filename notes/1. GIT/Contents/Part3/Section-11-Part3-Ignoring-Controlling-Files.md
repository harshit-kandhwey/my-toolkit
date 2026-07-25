# Section 11 (Part 3): Ignoring & Controlling Files — .gitignore and .gitattributes

## 11.1 Definition

**Plain language:** Not every file in a project belongs in version control — build output, dependency folders, secrets, editor junk — and not every tracked file should be treated identically — some are binary, some need consistent line endings across Windows and Linux machines, some shouldn't even end up in a release archive. `.gitignore` and `.gitattributes` are the two path-based configuration files that tell Git how to treat files by pattern.

**Precise:** `.gitignore` is a plain-text pattern file (one or more, at any directory level, plus global/system fallbacks) that tells Git which **untracked** paths to exclude from `git status`, `git add .`, and similar operations — it does not affect files Git already tracks. `.gitattributes` is a separate, more powerful pattern file that assigns **path-specific attributes**: text vs binary handling, line-ending normalization, custom diff drivers, merge strategies, and export behavior — attributes apply to tracked files and influence how Git's core machinery (diff, merge, checkout, archive) processes them.

## 11.2 Why It Exists / Problem It Solves

1. **Generated and environment-specific files pollute `git status` and history.** Compiled binaries, `node_modules/`, `__pycache__/`, IDE settings, log files — none of these belong in a shared history; they're either regenerable, machine-specific, or simply noise. `.gitignore` lets Git filter them out of everyday visibility permanently rather than requiring constant manual discipline.
2. **Not everything Git tracks is text.** Git's diff/merge machinery assumes line-oriented text by default; binary files (images, compiled artifacts) need Git to detect that and stop trying to line-diff or line-merge them, which would produce garbage or false conflicts. `.gitattributes` gives Git explicit, per-path knowledge of what it's dealing with.
3. **Cross-platform teams hit a specific, painful failure mode around line endings.** Windows and Unix-family systems have used different line-ending conventions since long before Git existed; without explicit configuration, this silently corrupts diffs and creates spurious conflicts across every text file in a mixed-OS team (11.6 is dedicated entirely to this).
4. **A repository's working tree and its distributable archive aren't always the same set of files.** `.gitattributes`' `export-ignore` lets internal-only files (CI config, test fixtures) exist in the repo without polluting a `git archive` release tarball.

## 11.3 `.gitignore` Syntax

### 11.3.1 Basic patterns

```gitignore
# Comments start with #

# Ignore a specific file by name, anywhere in the tree
secrets.env

# Ignore every file with this extension, anywhere in the tree
*.log

# Ignore an entire directory and everything inside it
node_modules/
build/

# Ignore a file only at the repo root (leading slash anchors the pattern)
/config.local.json

# Wildcards: ? matches one character, * matches any run of characters (not across /)
temp?.txt
cache/*.tmp

# ** matches across directory boundaries
logs/**/*.log
```

### 11.3.2 Negation with `!`

```gitignore
# Ignore all .log files...
*.log

# ...except this one specific file, which SHOULD be tracked
!important.log
```

> ⚠️ **Critical clarification:** negation cannot re-include a file if one of its **parent directories** is already ignored — Git never even looks inside an ignored directory to evaluate further rules. `build/` followed by `!build/keep.txt` does **not** work; you'd need to un-ignore the directory itself first (`!build/` then re-ignore its contents selectively), which is awkward enough that the common advice is to structure ignore rules to avoid needing this pattern at all.

### 11.3.3 Directory-only patterns (`/` suffix)

```gitignore
# Matches a directory named "build" anywhere, but NOT a file named "build"
build/

# Without the trailing slash, this would match both a file and a directory named "build"
build
```

### 11.3.4 Where `.gitignore` files live and how they combine

| Location                               | Scope                                        | Typically used for                                                                                 |
| -------------------------------------- | -------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `<repo-root>/.gitignore`               | Whole repo (committed, shared with the team) | Language/framework build artifacts, dependency folders — things every contributor should ignore    |
| `<subdirectory>/.gitignore`            | That subdirectory and below                  | Rules specific to one module/package in a monorepo                                                 |
| `.git/info/exclude`                    | This one local clone only, never committed   | Personal, machine-specific ignores you don't want to impose on teammates                           |
| Global gitignore (`core.excludesfile`) | Every repo on this machine, for this user    | Editor/OS junk that has nothing to do with any specific project — `.DS_Store`, `*.swp`, `.vscode/` |

```bash
# Purpose: register a global gitignore file that applies across every repository on this machine
$ git config --global core.excludesfile ~/.gitignore_global
```

```gitignore
# ~/.gitignore_global — personal, machine-wide, never committed to any project repo
.DS_Store
Thumbs.db
*.swp
.idea/
.vscode/
```

> 💡 **Tip:** Keep project-shared ignores (`node_modules/`, `dist/`) in the committed repo `.gitignore` so every teammate benefits automatically, and keep purely personal preferences (your editor's swap files) in the global gitignore — mixing the two means either polluting the shared file with your personal editor's junk, or forcing every teammate to configure their own machine-wide ignores for things that are really project concerns.

### 11.3.5 Precedence and pattern order

More specific rules (later in a file, or in a more deeply nested `.gitignore`) can override earlier, broader ones via negation. A useful debugging tool when a file that "should" be ignored isn't, or vice versa:

```bash
# Purpose: show exactly WHICH .gitignore rule (and file) is responsible for ignoring a given path
$ git check-ignore -v build/output.bin
.gitignore:3:build/    build/output.bin
```

### 11.3.6 `git rm --cached` — Un-tracking a File That's Already Committed

> ⚠️ **Critical clarification / common interview trap:** adding a path to `.gitignore` does **nothing** to a file Git is already tracking. `.gitignore` only controls whether Git considers **untracked** paths for staging; a file already committed keeps being tracked, keeps showing modifications in `git status`, and keeps being included in every future commit, ignore rule or not.

```bash
# Purpose: stop tracking a file going forward, WITHOUT deleting it from the working directory
$ git rm --cached secrets.env
rm 'secrets.env'

# Then add it to .gitignore so it doesn't get re-added by accident later
$ echo "secrets.env" >> .gitignore
$ git add .gitignore
$ git commit -m "Stop tracking secrets.env; add to .gitignore"
```

`--cached` removes the path from the **index only** — the working-directory file is untouched, so nothing is deleted from disk. Without `--cached`, plain `git rm secrets.env` removes it from both the index and the working directory. For an entire directory: `git rm -r --cached node_modules/`.

> ⚠️ **Critical clarification:** this only stops tracking the file **going forward** — the file's prior committed content remains permanently in history, retrievable by anyone with the repo, forever (or until history is rewritten — §15, §28). If the file contained a secret, `git rm --cached` plus `.gitignore` is not remediation; the secret must be treated as compromised and rotated, and full history-scrubbing procedures are §28.

## 11.4 `.gitattributes` Syntax and Purpose

`.gitattributes` lives at the repo root (or any subdirectory, scoped like `.gitignore`) and assigns one or more attributes to paths matching a pattern, using the same glob syntax as `.gitignore`.

```gitattributes
# Pattern                Attribute assignments
*.png                    binary
*.jpg                    binary
*.md                     text
*.sh                     text eol=lf
*.bat                    text eol=crlf
```

### 11.4.1 Text vs binary detection

```gitattributes
# Force Git to treat these as binary — never diff, never merge, never line-ending-convert
*.psd binary
*.exe binary

# Equivalent longhand (binary is shorthand for: -text -diff -merge)
*.psd -text -diff -merge
```

Without `.gitattributes`, Git guesses text-vs-binary heuristically (checking for a NUL byte in the first several KB of content) — usually correct, but not guaranteed. Explicitly marking known binary types avoids Git ever attempting a line-based diff on, say, a compiled `.dll` and producing meaningless output, or worse, attempting an automatic three-way text merge on a binary file during a merge (§13) and corrupting it.

### 11.4.2 Custom diff drivers

```gitattributes
# Route .docx files through a custom textconv filter for readable diffs
*.docx diff=word
```

```ini
# In .git/config or ~/.gitconfig
[diff "word"]
    textconv = pandoc --to=plain
```

This tells `git diff` to pipe the file through an external converter (here, `pandoc`) before diffing, so a binary-format document produces a readable text diff instead of `Binary files a/doc.docx and b/doc.docx differ`. The same `diff=<name>` mechanism underlies specialized diff drivers for structured formats (e.g. treating JSON or Jupyter notebooks more intelligently than raw text diffing would).

### 11.4.3 `export-ignore` — Excluding Files from Archives

```gitattributes
# These paths exist in the repo but should NOT appear in a git archive tarball/zip release
.github/ export-ignore
tests/fixtures/large-sample-data/ export-ignore
CONTRIBUTING.md export-ignore
```

```bash
# Purpose: produce a release archive that respects export-ignore rules
$ git archive --format=zip -o release.zip HEAD
```

`export-ignore` solves a different problem than `.gitignore`: these files are legitimately tracked, versioned, and needed by contributors working in the repo — they simply shouldn't ship in a packaged release artifact (CI workflow files, internal test fixtures, contributor docs). GitHub's own "download as zip" and `git archive` both honor this attribute.

## 11.5 Other Common Attributes (Brief Survey)

| Attribute                             | Effect                                                                                                                            |
| ------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `linguist-vendored`                   | Tells GitHub's language-detection (Linguist) to exclude a path from a repo's language statistics (e.g. vendored third-party code) |
| `filter=lfs diff=lfs merge=lfs -text` | The standard Git LFS attribute block redirecting large files to pointer-file storage (§26)                                        |
| `merge=ours`                          | Always resolve conflicts on this path by keeping "our" side, useful for auto-generated files that shouldn't be manually merged    |
| `linguist-generated`                  | Marks generated code so it's collapsed/hidden in GitHub's diff view by default                                                    |

Full LFS mechanics are §26; the pattern to internalize now is simply that `.gitattributes` is Git's general-purpose "treat this path specially" mechanism, of which line-ending policy (next) is the single most operationally important use.

## 11.6 Line Endings in Depth

This is the single most common source of "every line in this file shows as changed" confusion on cross-platform teams, and it deserves full treatment.

### 11.6.1 The root cause

- **Windows** text editors have historically written line endings as **CRLF** (`\r\n`, carriage return + line feed).
- **Unix-family systems** (Linux, macOS) use **LF** only (`\n`).

If a repository's files exist in Git with LF endings but a Windows developer's editor writes CRLF, the moment that developer saves a file, Git sees **every single line** as changed (the LF became a CRLF), even though no meaningful content changed at all. Multiply this across a whole file and a whole team, and diffs become useless, blame history gets destroyed (every line's "last modified" attribution shifts to whoever's editor first flipped the ending), and merge conflicts appear on lines nobody actually touched.

### 11.6.2 `core.autocrlf`

```bash
# Purpose: convert LF to CRLF on checkout (working dir), convert CRLF back to LF on commit (repo) — Windows default
$ git config --global core.autocrlf true

# Purpose: convert CRLF to LF on commit, but do NOT convert on checkout — macOS/Linux default
$ git config --global core.autocrlf input

# Purpose: no conversion at all — Git stores and checks out exactly what's on disk
$ git config --global core.autocrlf false
```

| Value   | On checkout (repo → disk) | On commit (disk → repo)   | Typical use                                                                                     |
| ------- | ------------------------- | ------------------------- | ----------------------------------------------------------------------------------------------- |
| `true`  | LF converted to CRLF      | CRLF converted back to LF | Windows developers working with repos that store LF (the common convention)                     |
| `input` | No conversion             | CRLF converted to LF      | macOS/Linux developers — never want CRLF written to disk, but normalize anything that sneaks in |
| `false` | No conversion             | No conversion             | Repos that intentionally store CRLF, or teams relying entirely on `.gitattributes` instead      |

`core.autocrlf` is a **per-developer, per-machine** setting (global config, §8.4) — it does not travel with the repository, which is precisely its weakness: a repo relies on every single contributor having configured it correctly and consistently, and one person with the wrong setting (or `false` when everyone else uses `true`) reintroduces the spurious-diff problem for everyone who later touches files they saved.

### 11.6.3 The robust fix: `.gitattributes`

Because `core.autocrlf` is machine-local and easy to misconfigure, the more reliable approach is to commit line-ending policy **into the repository itself** via `.gitattributes`, so it applies uniformly regardless of any individual developer's Git config:

```gitattributes
# Normalize all text files to LF in the repository, let Git auto-detect text vs binary,
# and convert to the platform's native ending only in the working directory if needed
* text=auto

# Force specific file types to a specific ending regardless of platform
*.sh  text eol=lf
*.bat text eol=crlf
*.png binary
```

- **`text=auto`** tells Git to auto-detect whether a file is text, and if so, normalize its line endings to LF **inside the repository** (the canonical stored form) regardless of what the contributor's working directory uses.
- **`eol=lf`** / **`eol=crlf`** force a specific ending in the **working directory** for that pattern, overriding whatever `core.autocrlf` would otherwise do — useful for files where the ending genuinely matters functionally (a shell script with CRLF endings can fail to execute at all inside a Linux container, even though it looks fine in a Windows editor).

> 💡 **Tip:** The generally recommended combination for a cross-platform team is `* text=auto` as a blanket default in a repo-root `.gitattributes`, with explicit `eol=lf`/`eol=crlf` overrides only for the specific file types that functionally require one ending (shell scripts, Windows batch files). This takes the decision out of individual developers' hands entirely — `.gitattributes` is committed, versioned, and applies identically to every clone.

### 11.6.4 Why cross-platform teams still get "every line changed" diffs

Even with `core.autocrlf` configured correctly by everyone, teams get burned when:

1. **The repository already contains mixed line endings** from before any policy was set — some files LF, some CRLF, committed at different times by different contributors' unconfigured machines.
2. **`.gitattributes` was added after the fact**, so it governs new checkouts/commits but the already-committed blobs in history still hold the old, inconsistent endings — files won't be renormalized until they're re-checked-out and re-committed.
3. **A tool outside Git's control** (some IDEs, some Windows-native build tools) rewrites line endings on save independent of Git's own conversion, silently reintroducing CRLF into a working directory that Git believes is LF-normalized.

### 11.6.5 Fixing an Already-Messed-Up Repository

```bash
# Purpose: renormalize an existing repo's line endings to match a newly added .gitattributes policy

# 1. Add/commit the .gitattributes policy first
$ git add .gitattributes
$ git commit -m "Add .gitattributes line-ending policy"

# 2. Force Git to re-evaluate and re-normalize every already-tracked file against the new rules
$ git add --renormalize .
$ git status
# shows every file whose stored line endings didn't match the new policy as "modified"

# 3. Commit the normalization as its own dedicated commit
$ git commit -m "Normalize line endings per .gitattributes"
```

`git add --renormalize .` re-runs the `text=auto` (and any `eol=`) rules against files already in the index, staging any content that needs converting to match the new policy — without this, `.gitattributes` only affects files touched (edited and re-committed) after the file was added, leaving old files in their original, inconsistent state indefinitely.

> ⚠️ **Common confusion to preempt:** always commit a mass line-ending renormalization as its **own isolated commit**, never mixed with actual code changes. A renormalization commit touches every line of every affected file, which makes `git blame` and code-review diffs on that commit meaningless noise — but an isolated, clearly-labeled "normalize line endings" commit lets `git blame -w` (ignore whitespace) or tools aware of line-ending-only commits skip past it cleanly when tracing real history (§19 covers `blame` in depth).

### 11.6.6 Quick Diagnostic

```bash
# Purpose: check whether a file in the repo currently has CRLF line endings
$ file src/script.sh
src/script.sh: Bourne-Again shell script, ASCII text, with CRLF line terminators

# Purpose: see Git's own text/eol/binary attribute determination for a path
$ git check-attr text eol src/script.sh
src/script.sh: text: set
src/script.sh: eol: lf
```

## 11.7 Hands-On: Setting Up Both Files for a New Cross-Platform Project

```bash
# Purpose: a realistic starter .gitignore + .gitattributes pair for a mixed-OS team's Python/Node project

$ cat .gitignore
# Dependencies
node_modules/
venv/
__pycache__/

# Build output
dist/
build/
*.pyc

# Editor/OS junk (better in global gitignore, shown inline here for completeness)
.DS_Store
.vscode/

# Secrets — never commit
.env
*.local.json

$ cat .gitattributes
# Normalize line endings for all text files
* text=auto

# Shell scripts must always use LF, even checked out on Windows
*.sh text eol=lf

# Windows batch files always CRLF
*.bat text eol=crlf

# Known binaries — never diff/merge as text
*.png binary
*.jpg binary
*.ico binary

# Exclude CI/test-only files from release archives
.github/ export-ignore
tests/ export-ignore
```

## 11.8 Troubleshooting

| Symptom                                                              | Likely cause                                                                                                    | Fix                                                                                                                                  |
| -------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| A file I added to `.gitignore` still shows up in `git status`        | It was already tracked before being ignored — `.gitignore` never affects tracked files                          | `git rm --cached <file>` (11.3.6)                                                                                                    |
| Every line of a file shows as changed in a diff with no real edits   | Line-ending mismatch — CRLF/LF inconsistency                                                                    | Set `core.autocrlf` correctly per-platform AND add a `.gitattributes` `text=auto` policy; renormalize with `git add --renormalize .` |
| `.gitignore` rule doesn't seem to match                              | Pattern typo, or file already tracked, or a parent directory's ignore rule blocks a negation from taking effect | `git check-ignore -v <path>` to see exactly which rule (if any) applies                                                              |
| Binary file shows a garbled/useless diff                             | Git guessed "text" via heuristic incorrectly                                                                    | Explicitly mark the pattern `binary` in `.gitattributes`                                                                             |
| `git archive` output includes files that shouldn't ship in a release | No `export-ignore` configured                                                                                   | Add `export-ignore` to the relevant `.gitattributes` patterns                                                                        |

## 11.9 Interview Questions

**[Beginner] Q1. Does adding a file to `.gitignore` remove it from Git if it's already tracked?**
**Model answer:** No. `.gitignore` only tells Git which **untracked** paths to leave out of `git status` and `git add`. A file Git is already tracking keeps being tracked, keeps showing modifications, and keeps being committed regardless of any `.gitignore` rule. To actually stop tracking it, you need `git rm --cached <file>`, which removes it from the index (future commits) while leaving the working-directory copy on disk, and then it's genuinely useful to also list it in `.gitignore` so it isn't accidentally re-added later.

**[Intermediate] Q2. Explain why a cross-platform team might see every line of a file marked as "changed" in a diff even though nobody meaningfully edited the file.**
**Model answer:** This is almost always a line-ending mismatch. Windows editors have historically written CRLF line endings while Unix-family systems use LF only. If the repository's stored content uses one convention and a developer's editor or Git configuration silently converts to the other on save or checkout, every line's terminating character changes, which Git's line-based diff reports as every line being modified — even though the visible content is identical. The fix is configuring line-ending handling explicitly and consistently: `core.autocrlf` per developer machine, and more robustly, a committed `.gitattributes` with `* text=auto` (and explicit `eol=lf`/`eol=crlf` for file types that functionally require one ending) so the policy travels with the repository rather than depending on every contributor's local config being correct.

**[Senior] Q3. You inherit a repo with years of history containing a mix of CRLF and LF line endings across different files, with no `.gitattributes` in place. How do you fix it without destroying blame history or creating a disruptive commit?**
**Model answer:** First, add a `.gitattributes` with `* text=auto` (plus any necessary `eol=` overrides for functionally sensitive files like shell scripts) and commit that alone. Then run `git add --renormalize .`, which re-evaluates every tracked file against the new policy and stages whichever files need their stored line endings converted to match; I'd commit that renormalization as its own single, clearly labeled commit ("Normalize line endings per .gitattributes"), never mixed with functional code changes, since it will touch every line of every affected file. This doesn't erase old blame history — `git blame` on lines predating the renormalization still correctly attributes them to their real original author/commit — but I'd make sure the team knows to use `git blame -w` (or `--ignore-rev`/`.git-blame-ignore-revs` for that specific commit hash) so tooling skips past the renormalization commit and keeps surfacing the meaningful prior change instead of the mass line-ending commit. I'd also communicate the change and timing to the team, since anyone with local uncommitted work will see it as a large merge/rebase conflict surface if they don't pull and rebase promptly.

## 11.10 Common Misconceptions

1. **"`.gitignore` untracks files."** It only prevents **untracked** files from being picked up; already-tracked files require `git rm --cached` to actually stop tracking.
2. **"`core.autocrlf` alone is a sufficient fix for line-ending problems."** It's a per-developer, per-machine setting that must be configured correctly and consistently by every single contributor to work at all; a `.gitattributes` policy committed to the repo is the more robust fix because it travels with the repo itself.
3. **"Adding `.gitattributes` retroactively fixes line endings in already-committed files."** It only governs files touched (checked out/committed) after it's added; existing blobs in history keep their original endings until explicitly renormalized with `git add --renormalize .`.
4. **"Marking a file `binary` in `.gitattributes` is only about avoiding ugly diff output."** It also disables Git's merge machinery for that path (no attempted three-way text merge), which matters far more — an unwanted automatic text merge on a binary file can silently corrupt it.
5. **"A `.gitignore` pattern with `!` can always un-ignore something."** Negation cannot re-include a path whose parent directory is already ignored — Git never descends into an ignored directory to evaluate further rules.

## 11.11 🔑 Key Takeaways

- `.gitignore` controls whether **untracked** paths are considered by `git status`/`git add`; it has zero effect on files already tracked — use `git rm --cached` for those.
- Scope layers from most to least shareable: repo-root `.gitignore` (committed, team-wide), subdirectory `.gitignore`, `.git/info/exclude` (local-only), and the global `core.excludesfile` (machine-wide, personal editor/OS junk).
- `.gitattributes` assigns per-path behavior — text/binary detection, custom diff drivers, `export-ignore` for archives, and critically, line-ending policy — and, unlike `core.autocrlf`, travels with the repository when committed.
- Cross-platform line-ending pain comes from CRLF (Windows) vs LF (Unix) mismatches; the robust fix combines correct per-machine `core.autocrlf` with a committed `* text=auto` (+ targeted `eol=`) `.gitattributes` policy.
- Fixing an already-inconsistent repo requires `git add --renormalize .` after adding the policy, committed as its own isolated commit so it doesn't pollute code-review diffs or blame.

## 11.12 Related Concepts & What's Next

The staging concepts referenced here (`git add`, `git status`, `git diff`) were built in full in §10; this section assumed that vocabulary throughout. `export-ignore` and binary-handling attributes reappear when large binary assets are discussed properly in §26 (Git LFS). Renormalization commits and their effect on history-reading tools connect directly to `git blame` and history search, covered fully in §19. With ignoring and attribute-based file control established, Part 4 moves into branching (§12) — the mechanism for developing multiple lines of work in parallel within the repository this and prior sections have shown how to populate and curate.
