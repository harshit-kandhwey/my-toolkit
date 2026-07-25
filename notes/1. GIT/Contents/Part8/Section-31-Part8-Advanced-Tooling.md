# Section 31 (Part 8): Advanced Tooling — Worktrees, Rerere, Notes, Bundles, Filter-Repo & History Rewriting at Scale

## 31.1 Definition

**Plain language:** Beyond the day-to-day commands covered so far, Git ships (or the ecosystem provides) a set of specialized tools for less frequent but genuinely important jobs: working on two branches at once without switching, never resolving the same conflict twice, attaching notes to commits without touching their hashes, shipping an entire repository as one file, and rewriting history safely at scale.

**Precise:** This section covers five largely independent tools — `git worktree`, `git rerere`, `git notes`, `git bundle`, and `git filter-repo` — that sit above the object model (§5) and refs (§6) already established, and below the everyday porcelain commands (branching §12, merging §13, rebasing §14) used constantly. Each solves a specific operational problem that a working engineer eventually hits, even if not daily.

## 31.2 Why This Tooling Exists

Ordinary Git usage assumes: one working directory per repository, conflicts resolved fresh each time, commit metadata fixed at commit time, and a remote server as the transfer mechanism. Each of those assumptions breaks down in a real scenario:

1. A production hotfix lands while your feature branch's working directory is mid-refactor and you don't want to stash or lose your build state — `git worktree`.
2. A long-lived branch being repeatedly rebased against a fast-moving `main` reproduces the _identical_ conflict on every rebase — `git rerere`.
3. You want to attach a code-review verdict, a CI build result, or a bug-tracker link to a commit **after** the fact, without altering the commit's hash (which would break every reference to it) — `git notes`.
4. You need to hand someone a complete repository, or take an air-gapped backup, with no network or hosting platform involved at all — `git bundle`.
5. You need to permanently remove a large binary or a leaked secret from every commit in history, or split a subdirectory into its own repository — `git filter-repo`.

## 31.3 `git worktree` — Multiple Working Directories, One Repository

### 31.3.1 The problem it solves

Without worktrees, working on two branches "at once" means either two full clones (duplicated object database, manual syncing, disk cost) or repeatedly stashing (§16) and switching (§12.6) in a single working directory — disruptive if you have an in-progress build, running dev server, or uncommitted experiment you don't want to touch.

### 31.3.2 The model

A **worktree** is a separate working directory, with its own checked-out branch and its own index, that shares the **same object database** and refs as the main repository. There is exactly one object store; N worktrees are N independent views into it.

```
                     ┌───────────────────────────┐
                     │   .git/  (ONE object DB,  │
                     │   ONE set of refs, shared)│
                     └─────────────┬─────────────┘
              ┌────────────────────┼─────────────────────┐
              ▼                    ▼                     ▼
     ┌────────────────┐   ┌────────────────┐    ┌────────────────┐
     │ main worktree  │   │ worktree #2    │    │ worktree #3    │
     │ branch: feature│   │ branch: hotfix │    │ branch: v2-rc  │
     │ own index +    │   │ own index +    │    │ own index +    │
     │ working files  │   │ working files  │    │ working files  │
     └────────────────┘   └────────────────┘    └────────────────┘
```

> ⚠️ **Critical clarification:** worktrees are **not** clones. A clone (§9) creates an entirely new `.git` directory with its own copy of the object database — a second, independent repository that happens to share history at clone time and then diverges in storage. A worktree has no separate object database at all; new commits made in any worktree are immediately visible (as reachable objects) to every other worktree of the same repository, because there is only one `.git/objects`.

### 31.3.3 Core rule: one branch, one worktree

Git refuses to check the same branch out in two worktrees simultaneously — this prevents two working directories from silently diverging on what "the tip of `main`" means. Use a detached checkout (§6.4.2) or a distinct branch if you need two views of similar content.

```bash
# Purpose: create a new worktree for a hotfix branch without touching the current working directory
$ git worktree add ../repo-hotfix hotfix/urgent-payment-bug
```

**Expected output:**

```
Preparing worktree (new branch 'hotfix/urgent-payment-bug')
HEAD is now at 7e4f9a2 Fix off-by-one error in pagination logic
```

```bash
# Purpose: list all worktrees attached to this repository
$ git worktree list
/home/jane/repo            7e4f9a2 [feature-payments]
/home/jane/repo-hotfix     a1b2c3d [hotfix/urgent-payment-bug]

# Purpose: remove a worktree once the hotfix is merged and the directory is no longer needed
$ git worktree remove ../repo-hotfix
```

> 💡 **Tip:** Worktrees are the direct answer to "should I stash and switch, or clone a second copy?" for a temporary parallel task — they cost only the disk space of the checked-out files, not a second history, and they stay perfectly in sync because there is nothing to sync: it's the same database.

### 31.3.4 Common use cases

- Running a hotfix build in one worktree while a feature branch's dev server keeps running in another.
- Building and comparing two branches side by side (e.g., benchmarking `main` vs a performance-optimization branch) without a rebuild-per-switch cycle.
- Running long CI-like tasks (a full test suite, a release build) against a specific tag in an isolated worktree while continuing normal work elsewhere.

## 31.4 `git rerere` — Reuse Recorded Resolution

### 31.4.1 The problem it solves

A long-lived feature branch, repeatedly rebased (§14) against a fast-moving `main`, frequently produces the **same textual conflict** on every rebase — the same two lines in the same file collide each time, because the underlying divergence hasn't been resolved at the source, only patched around commit by commit. Resolving it by hand every single rebase is repetitive and error-prone.

### 31.4.2 The mechanism

When enabled, `rerere` ("**re**use **re**corded **re**solution") records the **pre-conflict state** and **your resolution** the first time you resolve a given conflict. The next time Git encounters a textually identical conflict (same conflicting hunks), it automatically applies your previously recorded resolution instead of stopping and asking again.

```bash
# Purpose: enable rerere for this repository (or set it globally, § 8)
$ git config rerere.enabled true

# Purpose: (optional) auto-stage a conflict once rerere resolves it automatically
$ git config rerere.autoupdate true
```

**Workflow:**

```bash
$ git rebase main
# CONFLICT (content): Merge conflict in payments/retry.py
# ...you resolve it by hand, then:
$ git add payments/retry.py
$ git rebase --continue
# rerere has now recorded this exact conflict + your resolution

# Weeks later, the same branch is rebased again, hitting the identical conflict:
$ git rebase main
# Recorded preimage found for 'payments/retry.py'
# rerere applies your prior resolution automatically
```

> ⚠️ **Common confusion to preempt:** `rerere` matches on the **textual shape of the conflict itself** (the conflicting hunks), not on "this file" or "this branch" in general. A genuinely different conflict in the same file will not be auto-resolved; only a byte-for-byte repeat of a previously seen conflict triggers replay. It is not magic merge intelligence — it is a recorded-diff cache.

### 31.4.3 When it matters

- Long-lived branches under active, repeated rebasing (a common pattern with `git pull --rebase` on a feature branch tracked over weeks).
- Large-scale refactors landing on `main` in stages while several other branches keep rebasing through them, hitting the same collision repeatedly.
- Cherry-picking (§17) the same patch across multiple release branches, where the same conflict recurs on each target.

## 31.5 `git notes` — Metadata Without Rewriting History

### 31.5.1 The problem it solves

Sometimes you want to attach information to a commit **after** it already exists — a code review verdict, a CI build ID, a link to an incident ticket, a "verified by QA" stamp — without amending the commit (which would change its hash, per §5.5.3, and break every reference, branch, tag, and downstream fork pointing at it).

### 31.5.2 The mechanism

A **note** is a separate object, stored under a special ref namespace (`refs/notes/commits` by default), that maps a commit hash to a piece of text. Crucially, **notes are not part of the commit object** — attaching, editing, or removing a note never changes the commit's hash.

> ⚠️ **Critical clarification / contrast with §5:** §5 established that everything Git hashes is part of the object's permanent identity. Notes are the deliberate exception to that pattern at the _user-visible_ layer — they live alongside a commit, referenced by its hash, rather than inside it. This is precisely why they can be added, edited, or deleted freely without any of the cascading-hash consequences described in §5.5.3 and §5.7.

```bash
# Purpose: attach a note to the current commit
$ git notes add -m "Verified in staging by QA — ticket OPS-4821"

# Purpose: view notes alongside normal log output
$ git log --show-notes
```

**Expected output:**

```
commit 7e4f9a2c8b1d3e5f6a7b8c9d0e1f2a3b4c5d6e7f
Author: Jane Doe <jane@example.com>
Date:   Tue Jul 21 10:14:00 2026 +0530

    Fix off-by-one error in pagination logic

Notes:
    Verified in staging by QA — ticket OPS-4821
```

```bash
# Purpose: edit an existing note
$ git notes edit 7e4f9a2

# Purpose: remove a note
$ git notes remove 7e4f9a2
```

### 31.5.3 Sharing notes

Notes live in their own ref (`refs/notes/commits`) and are **not** transferred by a plain `git push`/`git fetch` unless explicitly configured — this is a deliberate default, since notes are often personal or workflow-local annotations rather than something every collaborator wants synced automatically.

```bash
# Purpose: explicitly push notes to a remote
$ git push origin refs/notes/commits

# Purpose: explicitly fetch notes from a remote
$ git fetch origin refs/notes/commits:refs/notes/commits
```

> 💡 **Tip:** `git notes` is niche in day-to-day interactive use but shows up in automation — CI systems sometimes attach a note recording the build/test result for a commit, queryable later without polluting commit messages or requiring a database lookup outside Git itself.

## 31.6 `git bundle` — Repository-in-a-File

### 31.6.1 The problem it solves

You need to move a complete repository, or a specific range of history, somewhere with **no network connectivity and no hosting platform** — an air-gapped environment, a USB drive handoff, an offline backup. A bundle packages exactly what `push`/`fetch` would transfer, into one ordinary file.

### 31.6.2 The mechanism

A bundle is a single file containing packed objects (§7) plus enough ref information to reconstruct branches and tags on the receiving end. It can hold an entire repository's history or a specific range (e.g., "everything since the last bundle, for an incremental transfer").

```bash
# Purpose: bundle the entire repository (all branches) into one file
$ git bundle create repo-full-backup.bundle --all

# Purpose: bundle only commits reachable from main that aren't already on origin/main
$ git bundle create incremental.bundle origin/main..main
```

**Expected output:**

```
Enumerating objects: 1204, done.
Counting objects: 100% (1204/1204), done.
...
```

```bash
# Purpose: verify a bundle is well-formed and readable before trusting it
$ git bundle verify repo-full-backup.bundle

# Purpose: clone directly FROM a bundle, exactly as if it were a remote
$ git clone repo-full-backup.bundle restored-repo

# Purpose: pull specific branches from a bundle into an EXISTING repository
$ git fetch repo-full-backup.bundle main:refs/heads/recovered-main
```

> 💡 **Tip:** `git clone <bundle-file>` and `git fetch <bundle-file>` both work because a bundle satisfies the same interface a remote does — Git doesn't distinguish "a file on disk packaged as a bundle" from "a repository reachable over a URL" at the transport-abstraction level.

### 31.6.3 Real use cases

- **Offline transfer:** handing a contractor or an air-gapped secure environment a full repository without any network path between the two machines.
- **Cold backup:** a periodic `git bundle create --all` written to durable, offline storage as a restore-from-scratch guarantee independent of the hosting platform (complements, but does not replace, platform-side backups — a point relevant to disaster recovery, §30).
- **Incremental sneakernet sync:** repeated `<last-known-ref>..HEAD` bundles to keep a disconnected mirror current without re-transferring the whole history each time.

## 31.7 `git filter-repo` — General-Purpose History Rewriting

### 31.7.1 Why it exists, and why it replaced `filter-branch`

Git shipped a built-in history-rewriting command, `git filter-branch`, for years. It is now **officially discouraged** by the Git project itself for two concrete reasons: it is extremely slow on any repository of real size (it re-checks-out and re-commits history largely serially), and it has well-documented correctness pitfalls (subtle handling of merge commits, empty commits, and ref updates that can silently produce a rewritten history different from what the user intended).

**`git filter-repo`** is a actively maintained, community-standard Python tool that replaces it: dramatically faster (single-pass, purpose-built rather than shelling out to many Git subprocesses per commit), safer by default (refuses to run on a repository that isn't a fresh clone, to avoid destroying someone's only copy), and far more capable.

> ⚠️ **Common confusion to preempt:** `filter-repo` is not a built-in Git subcommand shipped in Git core the way `worktree` or `bundle` are — it's a separate, official Git-project-recommended tool that must be installed independently. Treat its exact packaging/installation as something to verify against current documentation, since distribution details evolve.

### 31.7.2 What it can do

| Task                                               | Effect                                                                                                                                                                                                          |
| -------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Remove a file/path from all of history             | Every commit is rewritten with that path stripped; the file (and every byte of its history) no longer exists anywhere reachable                                                                                 |
| Extract a subdirectory into its own repository     | Produces a new history containing only commits touching that subtree, with paths rebased to the new root — the standard way to split a monorepo directory into its own repo while preserving its commit history |
| Rewrite author/committer identity at scale         | Bulk-corrects, e.g., an old email domain or a misconfigured name across the entire commit history, not just future commits                                                                                      |
| Strip a leaked secret from every historical commit | The core remediation mechanism referenced when a credential was accidentally committed and pushed                                                                                                               |

```bash
# Purpose: permanently remove a file (and its history) from every commit — MUST run on a fresh clone
$ git clone --no-local original-repo.git scrub-repo
$ cd scrub-repo
$ git filter-repo --path secrets/credentials.json --invert-paths
```

```bash
# Purpose: extract only the "billing-service/" subdirectory into a standalone repo history
$ git filter-repo --path billing-service/ --path-rename billing-service/:
```

```bash
# Purpose: rewrite a specific author's identity across all of history
$ git filter-repo --mailmap mailmap.txt
```

> ⚠️ **Critical clarification:** exactly like every other history-rewrite tool, `filter-repo` produces **new commit hashes for every rewritten commit** (per the chaining mechanism in §5.5.3) — this is a repository-wide history rewrite, subject to the full weight of the Golden Rule (§14.7). Every existing clone, fork, and open PR based on the old history becomes incompatible and must be re-cloned or reset onto the new history; this is not something to do to a shared branch without full team coordination and advance notice.

### 31.7.3 Relationship to secret remediation

Removing a secret from history with `filter-repo` (or its equivalents) is a **necessary but not sufficient** remediation step: the credential must also be treated as permanently compromised and rotated, because the secret was already exposed to anyone who fetched the repository before the rewrite, and because old objects can linger in reflogs, caches, forks, or CI logs the rewrite never touched. The full remediation workflow, including rotation and forensic cleanup, is covered as a dedicated topic elsewhere in this series.

## 31.8 Comparison — When to Reach for Which Tool

| Tool              | Solves                       | Touches history hashes?             | Typical trigger                                           |
| ----------------- | ---------------------------- | ----------------------------------- | --------------------------------------------------------- |
| `git worktree`    | Parallel working directories | No                                  | Need two branches checked out at once                     |
| `git rerere`      | Repeated identical conflicts | No                                  | Long-lived branch, repeated rebases                       |
| `git notes`       | Post-hoc metadata            | No                                  | Attach info without amending a commit                     |
| `git bundle`      | Offline/portable transfer    | No                                  | No network path, or cold backup                           |
| `git filter-repo` | Structural history rewrite   | **Yes, for every rewritten commit** | Remove secrets/large files, split repos, bulk-fix authors |

## 31.9 Interview Questions

**[Beginner] Q1. What problem does `git worktree` solve, and how is it different from cloning the repository a second time?**
**Model answer:** `git worktree` lets you have two (or more) working directories checked out from the same repository at the same time — for example, your feature branch in one directory and a hotfix branch in another — without stashing or switching in a single directory. The key difference from a second clone is that worktrees share one underlying object database; there's no duplicated history, no syncing needed, and a commit made in one worktree is immediately visible as part of the shared history in every other worktree of the same repository. A second clone, by contrast, creates an entirely separate `.git` directory with its own copy of the object database that then has to be explicitly kept in sync via push/fetch.

**[Intermediate] Q2. Explain what `git rerere` does and what specifically triggers it to auto-resolve a conflict.**
**Model answer:** `rerere` ("reuse recorded resolution") records the exact pre-conflict state of a merge/rebase conflict together with how you resolved it, the first time you resolve it by hand. If Git later encounters a **textually identical** conflict — the same conflicting hunks in the same file — it automatically applies the previously recorded resolution instead of stopping to ask again. This is most valuable on long-lived branches that get rebased repeatedly against a moving `main`, where the same underlying divergence keeps producing the same conflict on every rebase. It only matches on the literal shape of the conflict, not on "this file in general," so a genuinely different conflict still requires manual resolution.

**[Intermediate] Q3. Why can `git notes` attach information to a commit without changing that commit's hash, when Section 5 established that everything hashed is part of an object's identity?**
**Model answer:** A note is a separate object in its own right, referenced through a distinct ref namespace (`refs/notes/commits` by default) that maps a commit's hash to a note's content — it is not embedded inside the commit object itself. Because the commit object's content is unchanged, its hash is unchanged, and every branch, tag, and downstream reference to that commit stays valid. This is a deliberate design choice specifically so metadata can be added, edited, or removed after the fact without triggering the cascading hash changes that amending a commit's actual content would cause.

**[Senior] Q4. Why is `git filter-repo` recommended over the built-in `git filter-branch`, and what must a team do besides run it after removing a leaked secret from history?**
**Model answer:** `filter-branch` is officially discouraged because it's slow at any real scale — it effectively replays history commit by commit through many subprocesses — and it has known correctness edge cases around merge commits and empty commits that can produce subtly wrong results. `filter-repo` is a purpose-built, actively maintained replacement: much faster, safer by default (it refuses to run against anything but a fresh clone, to avoid an unrecoverable mistake on someone's only copy), and more capable — removing paths, extracting subdirectories into new repositories, and bulk-rewriting author identities are all first-class operations. Critically, removing a secret from history with `filter-repo` only fixes the repository's history going forward; it doesn't undo the exposure that already happened. The secret must be treated as compromised and rotated regardless, because anyone who fetched the repository before the rewrite already has the old objects, and copies can persist in forks, CI logs, or caches the rewrite never touched. And because every rewritten commit gets a new hash, this is a full history rewrite subject to the Golden Rule — every collaborator's existing clone becomes incompatible and needs to be re-cloned or hard-reset onto the new history, which requires explicit team-wide coordination.

**[Architect] Q5. A team wants to split one directory out of a 10-year-old monorepo into its own repository, preserving that directory's commit history. Walk through the approach and the trade-offs.**
**Model answer:** The tool for this is `git filter-repo` with path-filtering and path-renaming: clone the monorepo fresh, run `filter-repo --path <subdirectory>/ --path-rename <subdirectory>/:` to keep only commits touching that subtree and rebase their paths to the new repository's root, then push the result to a brand-new remote. Trade-offs to communicate up front: every retained commit gets a new hash (it's a full history rewrite of the extracted content), so the new repository's history, while faithful to what happened in that subdirectory, is not byte-identical in hash terms to the corresponding commits in the old monorepo — anyone needing to trace a commit back to the original monorepo needs a mapping, not an assumption of identical hashes. Merge commits that touched both the extracted directory and unrelated parts of the monorepo need care, since filter-repo's simplification of such commits can change what the graph looks like structurally even though the file-level content is correctly preserved. Finally, this is a one-time, coordinated cutover: once the new repository is the source of truth, the old monorepo's copy of that directory should be removed (in a separate, clearly communicated commit) to avoid two diverging sources of truth for the same code, and CI/CD, hooks, and any submodule/subtree references (§27) pointing at the old path need to be updated in the same change window.

## 31.10 Common Misconceptions

1. **"A worktree is just a lightweight clone."** It shares one object database with no duplication and no independent history; a clone is a fully separate repository. They solve superficially similar problems ("work on two things at once") through fundamentally different mechanisms.
2. **"`rerere` is smart conflict resolution / AI-assisted merging."** It is a literal record-and-replay cache keyed on the exact conflicting text; it has no understanding of code semantics and will not resolve a conflict it hasn't seen in this exact textual form before.
3. **"Notes are part of the commit and get pushed automatically like branches do."** Notes live in a separate ref namespace and require an explicit `git push`/`git fetch` of that ref; a normal push does not transfer them by default.
4. **"`filter-branch` still is the standard way to rewrite history."** It is officially discouraged in favor of `filter-repo` due to speed and correctness issues; `filter-branch` still exists and works but is not the recommended tool for new work.
5. **"Removing a secret from history with filter-repo means the exposure is resolved."** The secret was already exposed to anyone who had fetched the repository before the rewrite; rotation of the credential is mandatory regardless of how thoroughly history is scrubbed.

## 31.11 🔑 Key Takeaways

- `git worktree` gives multiple working directories over one shared object database — no duplicated history, unlike a second clone.
- `git rerere` records and replays conflict resolutions by exact textual match, most valuable for long-lived branches under repeated rebasing.
- `git notes` attach metadata to a commit via a separate ref namespace, without changing the commit's hash — the deliberate exception to "everything hashed is part of identity."
- `git bundle` packages history into one portable file, usable anywhere `push`/`fetch`/`clone` would work, including fully offline.
- `git filter-repo` is the modern, recommended replacement for the discouraged `git filter-branch` — faster, safer by default, and capable of path removal, subdirectory extraction, and bulk author rewriting; it is a full history rewrite subject to the Golden Rule, and secret removal always requires separate credential rotation.

## 31.12 Related Concepts & What's Next

This section covered the specialized tools sitting above the object model and refs. §32 turns to Git's own evolution over time — the `master`→`main` rename, the `checkout`-splitting story completed, default merge-strategy changes, the ongoing SHA-1-to-SHA-256 transition previewed in §5.4, and how Git compares today against SVN, Mercurial, and Perforce. §33 then consolidates best practices and anti-patterns from across this entire series into one reference.
