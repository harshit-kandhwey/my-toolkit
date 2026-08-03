# Section 16 (Part 4): Stashing Work in Progress

## 1. Definition

**Plain language:** A stash lets you set aside your uncommitted work-in-progress, get a clean working directory, do something else (switch branches, pull, fix an urgent bug), and then bring your work-in-progress back exactly as it was.

**Precise:** `git stash` records the current state of the working directory and index as a special commit-like structure, resets the working directory and index to match `HEAD`, and stores a reference to that structure at `refs/stash`. It is not a mysterious separate storage mechanism — it is built entirely from ordinary Git objects (commits and trees) living in the same object database as everything else, referenced by one specific ref.

## 2. Why It Exists / Problem It Solves

You're mid-edit on a feature when an urgent bug report arrives, or you need to `git pull` but have local changes that would conflict, or you simply want to switch branches without committing half-finished work. Committing "WIP, don't look at this" just to switch away is a common workaround, but it pollutes history with meaningless commits and requires cleanup later (an interactive rebase to squash them away, §14). The stash gives you a genuine, purpose-built "shelf" for uncommitted work that isn't part of your permanent history at all.

## 3. Mechanics — What a Stash Actually Is

When you run `git stash`, Git creates up to three commit objects (the exact count depends on whether you have staged changes, unstaged changes, and untracked files) and a special **stash commit** with **multiple parents** tying them together — structurally similar to a merge commit (§13), except its parents are "HEAD at the time," "the index's state," and optionally "untracked files' state," rather than two diverged branches.

```
refs/stash ──► stash commit
                 ├─ parent 1: HEAD at time of stash (base)
                 ├─ parent 2: commit representing the INDEX's state
                 └─ parent 3 (if -u/-a used): commit representing untracked files
```

Each stash you create doesn't overwrite the last — Git maintains a **stack**, referenced via `refs/stash`'s own reflog (`git stash list` reads exactly this), so multiple stashes coexist, addressable as `stash@{0}`, `stash@{1}`, and so on, most recent first.

> 💡 **Tip:** Because a stash is just commits plus a ref, everything you already know about commits applies — `git show stash@{0}` shows its diff like any commit, `git log --oneline -1 stash@{0}` shows a one-line summary, and the objects are just as reflog-recoverable (§6) as any other commit if you accidentally drop one.

## 4. Creating a Stash: `push` vs Bare `stash`

```bash
# Modern, explicit form — recommended
$ git stash push

# Equivalent shorthand — still extremely common, works identically for the
# no-argument case
$ git stash
```

Expected output:

```
Saved working directory and index state WIP on feature-search: 7c2a9f1 Add search skeleton
```

`git stash push` is the fuller command name, added specifically because it accepts a pathspec — `git stash push -- file.txt` stashes only that file's changes, leaving everything else in the working directory untouched, a capability the bare `git stash` shorthand also supports but that reads more clearly with `push` named explicitly.

```bash
# Purpose: stash only specific files
$ git stash push -- payments.js pricing.js
```

## 5. Naming, Untracked Files, and Everything

```bash
# Purpose: attach a descriptive message instead of the default "WIP on <branch>: ..."
$ git stash push -m "WIP: refactor pagination before urgent hotfix"

# Purpose: include untracked files (new files not yet `git add`ed) in the stash —
# by DEFAULT, stash only captures TRACKED changes, silently leaving new
# untracked files sitting in the working directory
$ git stash push -u
# or: git stash push --include-untracked

# Purpose: include EVERYTHING — tracked, untracked, AND ignored files
$ git stash push -a
# or: git stash push --all
```

| Flag                         | What gets stashed                                                       |
| ---------------------------- | ----------------------------------------------------------------------- |
| _(none)_                     | Tracked, modified files only (staged and unstaged)                      |
| `-u` / `--include-untracked` | Tracked changes + new untracked files                                   |
| `-a` / `--all`               | Tracked changes + untracked files + files ignored by `.gitignore` (§11) |
| `-m "<message>"`             | Any of the above, with a custom label instead of the auto-generated one |

> ⚠️ **Common confusion to preempt:** forgetting `-u` is one of the most common stash surprises — you stash, your working directory looks clean, you switch branches confidently, and then discover the brand-new files you created are still sitting there (or, worse, get silently carried along onto the new branch since untracked files aren't branch-scoped at all). If you created any new files as part of the work you're stashing, `-u` is almost always what you want.

## 6. Inspecting Stashes: `list`, `show`

```bash
# Purpose: list every stash currently on the stack, most recent first
$ git stash list
stash@{0}: WIP: refactor pagination before urgent hotfix
stash@{1}: WIP on main: a1b2c3d Fix typo

# Purpose: show a summary diffstat of a specific stash's changes
$ git stash show stash@{0}
 pagination.js | 8 +++++---
 1 file changed, 5 insertions(+), 3 deletions(-)

# Purpose: show the FULL diff, not just the summary
$ git stash show -p stash@{0}
```

## 7. Restoring: `pop` vs `apply`

```bash
# Purpose: reapply the most recent stash's changes AND remove it from the stack
$ git stash pop

# Purpose: reapply the most recent stash's changes but KEEP it on the stack
$ git stash apply

# Both accept a specific stash reference instead of defaulting to stash@{0}
$ git stash pop stash@{2}
$ git stash apply stash@{1}
```

|                                                       | `git stash pop`                                                                           | `git stash apply`                                                                                                                  |
| ----------------------------------------------------- | ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Reapplies changes to working directory/index          | Yes                                                                                       | Yes                                                                                                                                |
| Removes the stash from the stack **on success**       | Yes                                                                                       | No — stays on the stack                                                                                                            |
| Removes the stash if a conflict occurs during reapply | **No** — a conflicted pop leaves the stash entry intact specifically so you don't lose it | N/A, never removes                                                                                                                 |
| Typical use                                           | The common case — you're done with this stash, one-shot use                               | Reapplying the same stash to multiple branches, or when you want to keep a safety copy until you're certain the reapply is correct |

> ⚠️ **Critical clarification:** if `git stash pop` produces a merge conflict, Git deliberately does **not** drop the stash entry, precisely because you might still need to re-attempt the pop after resolving, or abandon the attempt and try elsewhere. In that specific case, resolve the conflict as usual (§13), `git add` the resolved files, and then manually run `git stash drop` yourself once you're confident the reapply is correct — `pop`'s automatic drop only happens on a clean, conflict-free application.

## 8. Removing Stashes: `drop`, `clear`

```bash
# Purpose: delete one specific stash entry without reapplying it
$ git stash drop stash@{1}

# Purpose: delete EVERY stash entry — irreversible in practice
$ git stash clear
```

Because a stash is built from ordinary commit objects, as described in the mechanics section above, `drop`/`clear` behave exactly like any other ref removal — the underlying commits aren't immediately destroyed, and are recoverable via `git fsck --unreachable` or the reflog on `refs/stash` for a window, until garbage collection actually prunes them. In practice this is a narrower, less convenient recovery path than the branch reflog most people are used to, so treat `stash drop`/`clear` as effectively permanent for planning purposes.

## 9. Applying a Specific Stash — Stash Isn't Strictly LIFO-Only

```bash
# Purpose: apply an OLDER stash without touching newer ones on the stack
$ git stash apply stash@{2}
$ git stash pop stash@{2}
```

> ⚠️ **Common confusion to preempt:** many assume stash only supports strict "last in, first out" access, like a literal stack that only exposes its top. In reality every entry is individually addressable by its `stash@{n}` index at any time — you can pop or apply the third-oldest stash while leaving the two more recent ones untouched on the stack, exactly as demonstrated above. The "stack" framing describes how entries are numbered and listed (most recent as `{0}`), not a restriction on which one you're allowed to act on.

## 10. `git stash branch` — Divergence Recovery

A specific, genuinely useful failure mode: you stash work, then make commits on the same branch that conflict with what you stashed, such that a plain `pop`/`apply` now conflicts unpleasantly or no longer makes sense against the branch's current state.

```bash
# Purpose: create a NEW branch starting from the commit the stash was originally
# taken against, check it out, and apply the stash there — sidesteps any
# conflict with commits made on the original branch SINCE the stash
$ git stash branch recovery-branch stash@{0}
```

This checks out a new branch at the exact commit the stash was based on, applies the stashed changes there (cleanly, since nothing has diverged yet on this fresh branch), and drops the stash entry on success — effectively "give my stashed work a clean branch to land on, as if I'd branched before making the changes that now conflict with it."

## 11. Stash Conflicts

Applying a stash uses the same three-way-merge machinery as `git merge`/`git rebase` — if the stash's changes overlap with edits made to the working directory or committed since the stash was taken, you get ordinary conflict markers (§13).

```bash
$ git stash pop
Auto-merging pricing.js
CONFLICT (content): Merge conflict in pricing.js
```

Resolve exactly as in §13: edit out the markers, `git add` the resolved file. As noted above in the discussion of `pop` vs `apply`, a conflicted `pop` deliberately leaves the stash entry in place; run `git stash drop` manually once you've confirmed the resolution is correct.

## 12. Hands-On — Full Stash Lifecycle

```bash
$ mkdir stashdemo && cd stashdemo && git init -q
$ echo "base" > f.txt && git add . && git commit -qm "base"

$ echo "wip edit" >> f.txt
$ echo "new file" > scratch.txt   # untracked

$ git stash push -u -m "WIP: exploring an idea"
Saved working directory and index state On main: WIP: exploring an idea

$ git status
On branch main
nothing to commit, working tree clean

$ git stash list
stash@{0}: On main: WIP: exploring an idea

# do something else entirely — e.g., an urgent unrelated fix
$ echo "hotfix" > hotfix.txt && git add . && git commit -qm "urgent hotfix"

# bring the WIP back
$ git stash pop
On branch main
Changes not staged for commit:
        modified:   f.txt
Untracked files:
        scratch.txt
Dropped stash@{0} (a1b2c3d...)
```

## 13. Production & Enterprise Usage

- Stashing before `git pull`/`git pull --rebase` when the working directory has uncommitted changes is routine — many developers alias a "safe pull" that stashes, pulls, then pops automatically.
- CI/CD build scripts occasionally use stash mechanics internally (e.g., temporarily setting aside a local config override before running a clean build), though this is far less common than interactive developer use.
- Because stash content lives in the object database like anything else, it is included when someone inspects `git fsck --unreachable` output during repository forensics or cleanup audits (§29) — a reminder that "just stashed, never committed" is not equivalent to "never wrote anything to disk in `.git`" for anyone doing a security review (§28) of what a repository might contain.

## 14. Troubleshooting

| Symptom                                                                      | Likely cause                                                                                                    | Fix                                                                                                                                                                                  |
| ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| New files "vanished" after `git stash`                                       | Forgot `-u`/`--include-untracked`; untracked files aren't captured by default                                   | `git stash pop` won't help if they were never stashed — check they weren't accidentally left behind or gitignored; going forward, always use `-u` when new files are part of the WIP |
| `git stash pop` fails with a conflict and you're unsure what state you're in | Normal — the stash entry is intentionally preserved on a conflicted pop                                         | Resolve conflicts (§13), `git add`, then manually `git stash drop` once satisfied                                                                                                  |
| Applied a stash to the wrong branch                                          | Stash isn't branch-scoped — `refs/stash` is a single, repo-wide stack, applicable from any branch               | If unwanted, `git restore`/`git reset` to undo the application (§15); the stash itself is untouched unless you popped it                                                             |
| `git stash list` is empty but you're sure you stashed something              | Possibly `git stash clear` or `drop` ran (intentionally or via a script/alias), or the stash was already popped | Check `git fsck --unreachable` for a dangling commit matching the expected content, as a last-resort recovery attempt                                                                |

## 15. Interview Questions

**[Beginner] Q1. What does `git stash` do, and why would you use it instead of just committing?**
**Model answer:** `git stash` saves your current uncommitted changes — working directory and staged edits — aside, and resets your working directory to match the last commit, giving you a clean state to switch branches, pull, or handle something urgent. You'd use it instead of committing because the work isn't finished or meaningful enough to be a real commit yet; stashing avoids polluting history with throwaway "WIP" commits that would need cleaning up later, while still letting you safely set the work aside and retrieve it exactly as it was.

**[Intermediate] Q2. What's the difference between `git stash pop` and `git stash apply`?**
**Model answer:** Both reapply a stash's changes to the working directory and index. `pop` additionally removes the stash entry from the stack once the reapply succeeds cleanly, treating it as a one-shot "use it up" operation. `apply` leaves the stash entry on the stack regardless, which is useful when you want to apply the same stashed changes to more than one branch, or want a safety copy retained until you're confident the reapply is correct — including specifically the case where a conflicted `pop` also leaves the entry in place, since Git won't drop something it isn't sure was fully, successfully restored.

**[Intermediate] Q3. Is `git stash` strictly a last-in-first-out structure? Can you retrieve an older stash without touching newer ones?**
**Model answer:** It's addressed like a stack for numbering purposes — `stash@{0}` is always the most recent — but any entry is individually addressable and can be popped or applied directly by its index at any time, regardless of what else is on the stack. `git stash apply stash@{2}` or `git stash pop stash@{2}` acts on that specific entry without requiring you to first remove `stash@{0}` and `stash@{1}`. The stack framing describes ordering and default behavior (bare `git stash pop` acts on `stash@{0}`), not an access restriction.

**[Senior] Q4. Explain, mechanically, what a stash actually is under the hood, and why that matters for how you'd recover a dropped one.**
**Model answer:** A stash is not a separate storage system — it's built from ordinary Git objects. `git stash push` creates one or more commit objects representing the current index and working-directory state, wrapped in a special multi-parent commit (structurally similar to a merge commit) whose parents include the commit HEAD was at, and a commit representing the index's state at stash time, referenced by the single ref `refs/stash`. Because it's just commits, dropping or clearing a stash behaves like any ref removal: the commit objects aren't immediately deleted, only unreferenced, and remain recoverable for a window via `git fsck --unreachable` (looking for a dangling commit matching the expected content) until garbage collection prunes them. This matters practically because the recovery path is less convenient than the branch reflog most people reach for instinctively — there's no per-branch "stash reflog" equivalent to casually browse, so recovering a dropped stash requires knowing to reach for `fsck` specifically.

**[Senior] Q5. A teammate stashed work, then continued committing on the same branch, and now `git stash pop` conflicts badly. What's the cleanest recovery path, and why?**
**Model answer:** Rather than fighting through a messy conflict resolution against a branch that has moved on significantly since the stash was taken, `git stash branch <new-branch-name> stash@{n}` is the purpose-built tool for exactly this situation: it creates a new branch starting from the commit the stash was originally based on, checks it out, and applies the stash there — since nothing has diverged yet on that fresh branch, the application is clean, with no conflict against the newer commits that were made on the original branch after the stash. The stashed work then lives on its own branch, which can be reviewed, cleaned up, and merged back deliberately using ordinary merge or rebase tooling (§13, §14), rather than being force-reconciled against unrelated later commits in a single conflicted pop.

## 16. Common Misconceptions

1. **"Stash is a mysterious separate storage area outside the repository."** It's built entirely from ordinary commit and tree objects in the same object database, referenced by one ref (`refs/stash`) with its own reflog for numbering entries.
2. **"`git stash` captures everything in my working directory."** By default it captures only tracked, modified content; new untracked files require `-u`, and ignored files require `-a`.
3. **"Stash only lets me access the most recent entry."** Every `stash@{n}` is individually addressable at any time; it isn't restricted to strict LIFO access.
4. **"A conflicted `git stash pop` loses my stash."** Git deliberately leaves the stash entry intact when the pop conflicts, specifically so you don't lose it; only a clean, successful pop removes it automatically.
5. **"Dropped stashes are recoverable exactly like a `reset --hard`, via `git reflog`."** They're recoverable via `git fsck --unreachable` in principle, but there's no dedicated per-branch reflog for stashes the way there is for `HEAD`/branches — the recovery path is real but less convenient.

## 17. 🔑 Key Takeaways

- A stash is a special multi-parent commit (built from ordinary Git objects) referenced by `refs/stash`, not a separate storage mechanism — this is why it's inspectable with `git show`/`git log` like any commit.
- By default, only tracked, modified content is stashed; `-u`/`--include-untracked` and `-a`/`--all` extend that to new files and ignored files respectively.
- `pop` reapplies and removes on success (but preserves the entry on conflict); `apply` always reapplies without removing — every entry remains individually addressable by `stash@{n}` regardless of stack order.
- `git stash branch` solves the specific "stash conflicts badly against a diverged branch" problem by applying the stash on a fresh branch rooted at the stash's original base commit.
- Dropped/cleared stashes aren't instantly destroyed but lack the convenient per-branch reflog recovery path that commits have — treat drops as effectively permanent in practice.

## 18. Related Concepts & What's Next

Stashing moves uncommitted work sideways temporarily; §17 covers a related but distinct need — moving already-committed work between branches deliberately, via cherry-pick, plus the patch-file mechanisms (`format-patch`/`apply`/`am`) for transferring changes entirely outside a shared Git remote, tracing back to the email-based kernel workflow §2 described before Git even existed.
