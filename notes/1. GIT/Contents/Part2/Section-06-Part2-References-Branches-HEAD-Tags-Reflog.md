# Section 6 (Part 2): References: Branches, HEAD, Tags, Refs & the Reflog

## 6.1 Definition

**Plain language:** A reference (ref) is a human-friendly name that points to a specific commit hash, so you don't have to memorize or type 40-character hex strings to find your way around history.

**Precise:** A ref is a file (or, at scale, a line in a packed-refs file) whose content is either a raw object hash (a **direct ref**) or the text `ref: <path-to-another-ref>` (a **symbolic ref**, used by HEAD). All refs live under `.git/refs/` (or are referenced from `.git/HEAD` and `.git/packed-refs`), and every ref ultimately resolves to one object hash — almost always a commit.

## 6.2 Why It Exists / Problem It Solves

1. **Human usability over raw hashes.** Nobody wants to type `git checkout a3f8e21bc9d4f5e6...` daily. `main`, `develop`, `v2.3.1` are memorable, meaningful names layered over the anonymous hash-addressed object graph from §5.
2. **Movable pointers enable "current state" tracking.** A branch ref is _designed_ to move forward automatically as you commit — this is precisely what lets "main" always mean "the latest commit on the main line" without you manually updating anything.
3. **Fixed pointers enable permanent markers.** Tags are designed to _not_ move, giving you a stable, permanent name for one exact point in history — essential for releases (§18).
4. **A safety net independent of the shared graph.** The reflog (6.6) records ref movements locally, so mistakes that seem to "lose" commits are almost always recoverable — a deliberate design response to the fact that history rewriting (§14, §15) is a first-class, encouraged operation in Git, and needs a safety net to be usable without fear.

## 6.3 Branch Refs — Full Mechanics

### 6.3.1 Physical form

A local branch is a file at `.git/refs/heads/<branch-name>` containing exactly one line: the 40-character (or 64-character, SHA-256) hash of the commit it currently points to.

```bash
$ cat .git/refs/heads/main
7e4f9a2c8b1d3e5f6a7b8c9d0e1f2a3b4c5d6e7f
```

That's the _entire_ implementation of a branch. Nothing else exists — no metadata file, no copy of file content, nothing.

### 6.3.2 What happens when you commit

1. Git creates a new commit object whose `parent` field is the _current_ commit that the active branch points to.
2. Git overwrites the branch's ref file with the new commit's hash.
3. HEAD (pointing at the branch, not directly at the commit — see 6.4) automatically reflects the new commit, because it resolves through the branch.

This is why committing "moves the branch forward" — literally, one text file's content is rewritten to a new hash.

### 6.3.3 What happens when you create a branch

```bash
$ git branch feature-x
```

Git simply writes a new file, `.git/refs/heads/feature-x`, containing the _same_ hash as whatever HEAD currently resolves to. No files are copied, no history is duplicated — this is the entire mechanism behind §2's claim that Git branching is "trivial and instant regardless of repository size."

```
Before:                          After `git branch feature-x`:

refs/heads/main → C3              refs/heads/main    → C3
                                   refs/heads/feature-x → C3   (new file, same hash)
```

Both branches point at the _same_ commit until one of them receives new commits and diverges.

## 6.4 HEAD — Full Mechanics

**Physical form:** `.git/HEAD`, almost always containing:

```
ref: refs/heads/main
```

This is a **symbolic ref** — a pointer to another ref, not directly to a commit. Resolving "what commit am I on" therefore takes two hops in the normal case: `HEAD` → `refs/heads/main` → commit hash.

### 6.4.1 Why the indirection matters

Because HEAD points at the _branch name_, not directly at a commit, committing automatically "carries HEAD forward" — you never have to manually update HEAD yourself. Git updates the branch ref (6.3.2), and HEAD, still pointing at that branch name, transparently resolves to the new commit.

### 6.4.2 Detached HEAD — the direct-pointer case

If you check out a specific commit, or a tag, instead of a branch:

```bash
$ git checkout a3f8e21
Note: switching to 'a3f8e21'.

You are in 'detached HEAD' state. You can look around, make experimental
changes and commit them, and you can discard any commits you make in this
state without impacting any branches by switching back to a branch.
...
```

Now `.git/HEAD` contains the raw commit hash directly, **not** `ref: refs/heads/...`:

```
a3f8e21bc9d4f5e6789012345678901234567890
```

**Consequence:** if you commit in this state, the new commit's parent is `a3f8e21`, but _no branch ref moves_ to point at your new commit — nothing is tracking it except HEAD itself. If you then check out a different branch, HEAD moves to point at _that_ branch, and your detached-HEAD commits become unreferenced by anything except (temporarily) the reflog.

```
Detached HEAD committing:

  HEAD (direct) ──► C_new ──parent──► a3f8e21 ──► ... (older history)

  refs/heads/main still points at wherever it was before —
  completely unaware C_new exists.
```

> ⚠️ **This is not silent data loss** — the commit object physically still exists in `.git/objects` and is recoverable via the reflog (6.6) for a retention window (default 90 days for reachable-losing entries, though exact defaults are configurable and worth verifying against current documentation) — but it is genuinely easy to lose track of casually, which is why the standard advice is: the moment you want to keep work made in detached HEAD, immediately run `git switch -c <new-branch-name>` to attach a real branch pointer to it.

### 6.4.3 When you deliberately want detached HEAD

Legitimate uses: inspecting an old release's exact state without disturbing any branch, running a one-off build from a specific historical commit, or bisecting (§19) — where Git deliberately detaches HEAD at each candidate commit during the search.

## 6.5 Tag Refs

Covered structurally in §5.5.4; here we cover them purely as **refs**.

- **Physical form:** `.git/refs/tags/<tag-name>`, containing either a commit hash directly (lightweight tag) or the hash of a tag _object_ (annotated tag), which in turn points to a commit.
- **Key behavioral difference from branches:** nothing in Git prevents you from moving a tag (`git tag -f`), but doing so on a tag anyone else may have already fetched is a serious foot-gun — anyone who built or deployed something referencing that tag now silently gets different content if they re-fetch, breaking the entire "tags are permanent" assumption the ecosystem relies on. Full discipline in §18.

## 6.6 The Reflog

### 6.6.1 What it is

**Plain language:** a private, chronological diary that Git keeps on your machine of everywhere HEAD (and each branch) has pointed, so you can find your way back after a mistake.

**Precise:** for every ref update (commits, checkouts, merges, rebases, resets — practically anything that moves a ref), Git appends a line to `.git/logs/HEAD` (and to `.git/logs/refs/heads/<branch>` for that specific branch) recording the old hash, the new hash, who did it, when, and a short description of the operation.

### 6.6.2 Physical inspection

```bash
$ git reflog
a3f8e21 (HEAD -> main) HEAD@{0}: commit: Fix pagination bug
7e4f9a2 HEAD@{1}: commit: Add pagination tests
1a2b3c4 HEAD@{2}: checkout: moving from feature-x to main
9d8e7f6 HEAD@{3}: commit (amend): Refactor auth module
...
```

Each `HEAD@{n}` is a **time-based reference** you can check out or reset to directly — `git checkout HEAD@{3}` takes you to exactly the state HEAD was in 3 ref-movements ago, regardless of whether any branch currently points there.

### 6.6.3 Why this matters — the core safety property

The reflog is precisely why Git's aggressive, encouraged history-rewriting operations (amend, rebase, reset --hard, force-push locally observed, branch deletion) are usable without excessive fear: almost every "I think I just destroyed my work" scenario is recoverable, because the commit objects are still physically present in `.git/objects` (nothing is deleted immediately) and the reflog remembers exactly which hash to point back to.

> ⚠️ **Critical scope limitation:** the reflog is **entirely local** — it is never pushed, never fetched, never part of the shared repository, and not visible to anyone else. It only records refs _you personally_ moved on _this specific clone_, and it has a default expiry (unreachable entries are pruned after a default of 30 days, reachable ones after 90 — exact defaults are configurable via `gc.reflogExpire` and `gc.reflogExpireUnreachable`, and you should verify current defaults against your Git version's documentation). This means the reflog is a personal undo history, not a substitute for backups or for careful force-push discipline on shared branches.

## 6.7 Full Refs Architecture Diagram

```
.git/
├── HEAD                          "ref: refs/heads/main"   (symbolic ref)
├── refs/
│   ├── heads/
│   │   ├── main                   → a3f8e21...   (local branch)
│   │   └── feature-x               → 7e4f9a2...   (local branch)
│   ├── tags/
│   │   ├── v1.0.0                  → <tag object hash>   (annotated)
│   │   └── quick-marker            → 9d8e7f6...   (lightweight)
│   └── remotes/
│       └── origin/
│           ├── main                → a3f8e21...   (remote-tracking branch, §20)
│           └── feature-x            → 1a2b3c4...
├── packed-refs                     (many refs consolidated into one file for efficiency — §7)
└── logs/
    ├── HEAD                        (reflog for HEAD movements)
    └── refs/heads/
        ├── main                    (reflog specific to the main branch)
        └── feature-x
```

> 💡 **Tip:** `refs/remotes/origin/main` (a **remote-tracking branch**) looks like a branch but is read-only bookkeeping — it records where `origin`'s `main` was as of your last fetch. You never commit directly onto it; Git updates it automatically during fetch/pull. Full treatment in §20.

## 6.8 Commands (Full Documentation per §9 Template)

### `git branch`

- **Purpose:** create, list, rename, or delete branch refs — the primary tool for managing local lines of development.
- **Syntax:** `git branch [<branch-name>] [options]`
- **Key options:**
  - _(no args)_ — list all local branches, with `*` marking the currently checked-out one.
  - `<name>` — create a new branch ref pointing at the current HEAD's commit (does **not** switch to it).
  - `-d <name>` — delete a branch, but only if it's already fully merged into its upstream or current branch (a safety check).
  - `-D <name>` — force-delete a branch regardless of merge status — genuinely destructive if the branch has unique unmerged commits (though recoverable via reflog if caught quickly).
  - `-m <old> <new>` — rename a branch.
  - `-a` — list local _and_ remote-tracking branches.
  - `-v` — list branches with their latest commit hash and message summary.
- **Practical example:**
  ```bash
  $ git branch feature-login
  $ git branch
  * main
    feature-login
  $ git branch -v
  * main           a3f8e21 Fix pagination bug
    feature-login  a3f8e21 Fix pagination bug
  ```
  Expected output: both branches point at the identical commit immediately after creation, exactly as the mechanics in 6.3.3 predict.
- **Production usage:** naming conventions for branches (`feature/*`, `bugfix/*`, `release/*`) are a core part of branching-strategy discipline, covered fully in §22; `git branch -d` is the routine cleanup step after a feature branch is merged via pull request.
- **Common errors:** `error: the branch 'feature-x' is not fully merged` when running `-d` on a branch with unmerged unique commits — this is Git protecting you; either merge it first or consciously use `-D` if you're certain you want to discard those commits.
- **Security impact:** none directly; branch names sometimes leak information (e.g., a branch named `hotfix-customer-acme-breach`) — a minor information-disclosure consideration in public repositories.
- **Performance impact:** negligible; branch creation/deletion is a tiny file write/delete.

### `git switch` (modern) / `git checkout` (legacy, dual-purpose)

- **Purpose:** change which branch (or commit) HEAD points to, updating the working directory and index to match. `git switch` was introduced specifically to split this responsibility out of the historically overloaded `git checkout` command (which also handles restoring individual files — a separate, unrelated responsibility now covered by `git restore`, §15).
- **Syntax:** `git switch <branch-name>` / `git switch -c <new-branch-name>` / `git switch --detach <commit>`
- **Key options:**
  - `-c <name>` — create a new branch at the current commit _and_ switch to it in one step (equivalent to `git branch <name>` + `git switch <name>`).
  - `--detach <commit-or-tag>` — deliberately enter detached HEAD state at a specific commit.
- **Practical example:**
  ```bash
  $ git switch -c feature-payments
  Switched to a new branch 'feature-payments'
  ```
- **Production usage:** the modern, recommended day-to-day command for branch switching in scripts and muscle memory; `git checkout` remains extremely common in existing tutorials, CI scripts, and muscle memory from before `switch`/`restore` existed (Git 2.23+), so recognizing both is essential.
- **Common errors:** `error: Your local changes to the following files would be overwritten by checkout` — you have uncommitted changes that conflict with the target branch's version of a file; resolve by committing, stashing (§16), or discarding first.
- **Security impact:** none directly.
- **Performance impact:** proportional to how many files differ between your current and target state — Git only rewrites files that actually differ, not the entire working tree, which is why switching between branches with small diffs is fast even in large repos.

### `git reflog`

- **Purpose:** view (and, indirectly through the `HEAD@{n}` syntax, recover from) the local history of ref movements — the practical recovery tool for "I think I lost a commit."
- **Syntax:** `git reflog [show] [<ref>]`
- **Key options:** defaults to showing HEAD's reflog; `git reflog show <branch-name>` shows a specific branch's own reflog.
- **Practical example:**
  ```bash
  $ git reflog
  a3f8e21 (HEAD -> main) HEAD@{0}: reset: moving to HEAD~1
  7e4f9a2 HEAD@{1}: commit: Add feature flag check
  $ git reset --hard HEAD@{1}
  HEAD is now at 7e4f9a2 Add feature flag check
  ```
  This concretely recovers a commit that an accidental `git reset --hard HEAD~1` appeared to discard — full mechanics of `reset` in §15, full disaster-recovery treatment in §30.
- **Production usage:** the first tool reached for after any local history mistake — accidental force-push undone locally, bad rebase, wrong branch deleted (as long as you know the approximate former commit hash or reflog position).
- **Common errors:** confusing HEAD's reflog with a specific branch's reflog when the branch in question wasn't checked out at the time of the mistake — check `git reflog show <branch>` specifically if `git reflog` (HEAD's) doesn't show what you expect.
- **Security impact:** the reflog can retain traces of commits you intended to fully purge (e.g., accidentally committed secrets) even after `reset`/`rebase` seem to remove them from visible history — a real security consideration covered fully in §28's secret-remediation material; simply rewriting visible history is _not_ sufficient to guarantee a secret is gone from the local repository until the reflog entries are also expired and gc'd.
- **Performance impact:** negligible to read; reflog files are small and append-only.

## 6.9 Hands-On Example — Detached HEAD, Recovery, and Branch Mechanics Together

```bash
$ mkdir refdemo && cd refdemo && git init -q
$ echo "a" > f.txt && git add f.txt && git commit -q -m "commit A"
$ echo "b" >> f.txt && git add f.txt && git commit -q -m "commit B"
$ git log --oneline
7e4f9a2 commit B
a3f8e21 commit A

# Enter detached HEAD deliberately, at the older commit
$ git checkout a3f8e21
Note: switching to 'a3f8e21'.
You are in 'detached HEAD' state...

# Make a commit here — it has no branch tracking it
$ echo "c" >> f.txt && git add f.txt && git commit -q -m "detached commit C"
$ git log --oneline
9d8e7f6 detached commit C
a3f8e21 commit A

# Switch back to main WITHOUT creating a branch for C first
$ git switch main
Warning: you are leaving 1 commit behind, not connected to
any of your branches...

$ git log --oneline
7e4f9a2 commit B
a3f8e21 commit A
# "detached commit C" is no longer visible in normal log output!

# Recover it via the reflog
$ git reflog
7e4f9a2 (HEAD -> main) HEAD@{0}: checkout: moving from 9d8e7f6... to main
9d8e7f6 HEAD@{1}: commit: detached commit C
a3f8e21 HEAD@{2}: checkout: moving from a3f8e21 to a3f8e21

$ git switch -c recovered-branch 9d8e7f6
Switched to a new branch 'recovered-branch'
$ git log --oneline
9d8e7f6 detached commit C
a3f8e21 commit A
```

This walkthrough demonstrates, concretely: detached HEAD committing, the commit becoming invisible to normal branch-based navigation, and full recovery via the reflog — exactly the safety-net property described in 6.6.3.

## 6.10 Production & Enterprise Usage

- **CI/CD systems deliberately use detached HEAD.** Most CI runners check out a specific commit (not a branch) for a build job — this is intentional: the job should build _exactly_ the commit that triggered it, immune to the branch moving forward mid-build. Understanding detached HEAD demystifies why CI logs often show "You are in 'detached HEAD' state" without it being an error.
- **Branch protection rules** (§23) operate on branch refs specifically — a platform like GitHub enforces "no force-push, no deletion, required reviews" on the `refs/heads/main` ref, which is exactly the physical object described in 6.3.1.
- **Reflog retention as an operational policy consideration:** some enterprises shorten or extend `gc.reflogExpire` settings depending on their balance between disk usage and desired local-recovery window — a minor but real operational tuning knob covered further in §29.

## 6.11 Security Considerations

- Tags and branches are **not** access-control boundaries by themselves — anyone with push access can create, move, or delete any ref unless the hosting platform's branch/tag protection rules (§23) explicitly restrict it.
- As flagged in 6.8, the reflog can retain sensitive content (e.g., a secret committed and then "removed" via amend/rebase) locally even after it disappears from visible branch history — full remediation workflow in §28.
- Force-moving a tag that others have already fetched is a supply-chain integrity risk: if `v2.3.1` is retagged to point at different content, systems that pin to `v2.3.1` by name (rather than by exact hash) will silently receive different code on their next fetch — a real, documented category of software supply-chain attack.

## 6.12 Performance Considerations

- With many thousands of refs (common in large monorepos or forks with many stale branches), reading refs one file at a time becomes measurably slower; Git consolidates old refs into a single `packed-refs` file (a plain, git-managed text file) for faster bulk reference resolution — this happens automatically during garbage collection (§7, §29).
- Reflog files are small and rarely a performance concern, but repositories with extremely high commit/rebase churn over years can accumulate reflog data worth periodically pruning as part of maintenance (§29).

## 6.13 Troubleshooting

| Symptom                                                                                              | Likely cause                                                                                                                             | Fix                                                                                                                                                                                         |
| ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `fatal: You are in 'detached HEAD' state` (as a surprise, not intentional)                           | Checked out a tag or specific commit rather than a branch                                                                                | If you want to keep any commits made here, run `git switch -c <name>` immediately before switching away                                                                                     |
| A commit seems to have vanished after `reset --hard` or switching branches                           | The commit is likely just unreferenced by any branch, not deleted                                                                        | `git reflog`, find the hash, `git switch -c <name> <hash>` to recover it                                                                                                                    |
| `error: pathspec 'X' did not match any file(s) known to git` when trying to `checkout` a branch name | Branch doesn't exist locally (may exist only as a remote-tracking branch)                                                                | `git switch X` in modern Git auto-creates a local tracking branch from a matching remote one; otherwise `git checkout -b X origin/X`                                                        |
| Reflog entry expected but missing                                                                    | Reflog entries expired per `gc.reflogExpire`/`gc.reflogExpireUnreachable`, or `gc` already ran and pruned genuinely unreferenced objects | Check backup remotes/clones; unfortunately, once both the reflog entry and the object itself are gc'd, local recovery is no longer possible — see §30 for broader disaster recovery options |

## 6.14 Best Practices

- The instant you make a commit you want to keep while in detached HEAD, run `git switch -c <descriptive-name>` before doing anything else — don't rely on remembering to check the reflog later.
- Always use annotated tags for releases (§5.5.4, §18) and treat tags as immutable once published — never force-move a tag that may already have been fetched by anyone else.
- Use `git branch -d` (safe delete) as your default; reserve `-D` (force delete) for cases where you've deliberately confirmed the branch's unique commits are disposable.

## 6.15 Anti-Patterns & Common Mistakes

- **Anti-pattern:** treating the reflog as a substitute for real backups or for careful force-push discipline on shared branches — it is local-only, has an expiry window, and offers zero protection to your collaborators if you force-push a destructive rewrite to a shared remote branch.
- **Common mistake:** panicking after a commit "disappears" from `git log` without realizing `git log` only shows commits reachable from the current HEAD/branch — checking the reflog is almost always the correct first troubleshooting step before assuming data loss.

## 6.16 Interview Questions

**[Beginner] Q1. What is HEAD, and how does it normally relate to a branch?**
**Model answer:** HEAD is a pointer that tells Git which commit is currently checked out. In the normal case, HEAD doesn't point directly at a commit — it points at the name of your current branch, and that branch in turn points at a commit. This indirection is why committing automatically "moves you forward": Git updates the branch's pointer to the new commit, and since HEAD is still pointing at that branch name, it transparently follows along.

**[Intermediate] Q2. What is detached HEAD state, and what's the correct way to preserve work done in it?**
**Model answer:** Detached HEAD happens when HEAD points directly at a specific commit hash instead of at a branch name — typically because you checked out a tag or a raw commit hash rather than a branch. You can still make commits in this state, but no branch pointer tracks them, so if you switch to another branch afterward, those commits become unreachable through normal navigation, though the commit objects still physically exist in the object database. The correct practice is to run `git switch -c <new-branch-name>` immediately if you want to keep any work made while detached, which creates a real branch pointer at that commit before you move away from it.

**[Intermediate] Q3. What exactly is the reflog, and what are its limitations?**
**Model answer:** The reflog is a local, chronological log Git keeps of every place HEAD and individual branches have pointed, recorded automatically whenever a ref is updated — through commits, checkouts, merges, rebases, or resets. It's the primary recovery mechanism for local mistakes: you can look up an earlier position with `HEAD@{n}` syntax and reset or check out back to it. Its key limitations are that it's entirely local — never pushed, fetched, or shared with anyone else — and it has a default expiry window, so entries eventually age out and get garbage collected, at which point recovery through the reflog is no longer possible.

**[Senior] Q4. Why is creating a Git branch essentially instantaneous even in a repository with millions of commits and files?**
**Model answer:** Because a branch is nothing more than a small text file containing a single commit hash, stored under `.git/refs/heads/`. Creating a branch is just writing a new file with that hash as its content — it never copies any file content, never touches the object database's existing objects, and never depends on the size of the repository's history or working tree. This is a direct consequence of Git's ref design: branches are lightweight, movable pointers layered on top of the immutable object graph, not independent copies of anything, which is precisely why branching cost in Git is constant-time regardless of repository scale — in sharp contrast to version control systems where branching historically involved copying files or directories.

**[Architect] Q5. A team member force-pushed over a shared release tag, `v3.1.0`, after discovering a last-minute bug, intending to "fix and retag." What are the risks, and what should the team's policy be?**
**Model answer:** The core risk is that a tag, once pushed and fetched by anyone else — including CI systems, downstream consumers pinning dependencies, or auditors — is assumed to be a permanent, immutable marker for one exact piece of history. If it's moved, anyone who already has the old `v3.1.0` locally now has content that silently diverges from what the tag currently points to on the remote, and anyone who re-fetches gets different content under the same name with no obvious warning — this is a textbook supply-chain integrity problem, not just an inconvenience. The correct practice is to never reuse a released tag name: cut a new tag, such as `v3.1.1`, for the fix, and treat the original `v3.1.0` as a historical, if flawed, permanent record. Organizationally, this should be enforced with tag-protection rules on the hosting platform (§23) that prevent force-pushes or deletions on tags matching a release naming pattern, combined with clear team documentation that "tags are append-only, never edited," so this isn't left to individual discipline alone.

## 6.17 Common Misconceptions

1. **"HEAD always points directly to a commit."** In the normal case it points to a branch name, which then points to a commit — a two-hop resolution, not a direct one. Only in detached HEAD does it point straight at a commit.
2. **"A 'lost' commit after reset or checkout is gone."** It almost always still physically exists in the object database and is recoverable through the reflog, provided it hasn't yet been garbage-collected.
3. **"The reflog is part of the shared repository history."** It is strictly local, never transmitted via push/fetch/clone, and has an expiry window — it is a personal safety net, not shared history.
4. **"Branches and tags are fundamentally different kinds of objects."** At the ref level, a lightweight tag and a branch are structurally identical (a file pointing at a commit hash); the difference is purely one of convention (moving vs. static) and, for annotated tags specifically, the presence of a genuinely distinct tag object with its own metadata.

## 6.18 🔑 Key Takeaways

- A ref is a name pointing at a commit hash; branches are movable refs, tags are (by convention) fixed refs, and HEAD is a special ref that normally points at your current branch rather than directly at a commit.
- Branch creation is instantaneous because it only ever writes a small pointer file — never copies content — which is the direct mechanism behind Git's famous branching speed.
- Detached HEAD lets you check out a specific commit directly; commits made there aren't tracked by any branch and can become hard to find (though not immediately lost) if you switch away without creating a branch first.
- The reflog is your local, automatic safety net recording every ref movement — the first tool to reach for after any "I think I lost my work" moment — but it is local-only and has an expiry window, not a backup substitute.
- Never force-move a published tag; cut a new tag instead, to preserve the "tags are permanent markers" guarantee the whole ecosystem relies on.

## 6.19 Related Concepts & What's Next

Refs point at objects, but so far we've only seen those objects stored one-per-file as **loose objects** (§4.3's `objects/ab/cdef...` layout). Section 7 goes underneath that simple picture to show how Git actually keeps large repositories fast and small on disk: packfiles, delta compression between similar objects, and the garbage collection process that consolidates loose objects into packs and prunes truly unreachable ones — the last piece needed before Part 3's hands-on daily workflow commands can be taught with full understanding of what's happening underneath them.
