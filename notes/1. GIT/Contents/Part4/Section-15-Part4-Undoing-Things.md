# Section 15 (Part 4): Undoing Things — restore, reset, revert, clean (and legacy checkout)

## 1. Definition

**Plain language:** Git gives you several distinct "undo" commands, and picking the wrong one is one of the most common ways people either lose work they wanted to keep or fail to undo what they meant to. Each operates on a different one of the three areas from §4, and each has a different safety profile.

**Precise:** Undoing in Git is not one operation but a family of them, differentiated by (1) which area they touch — working directory, index, or committed history — and (2) whether they rewrite existing refs/objects in place (destructive to history, safe only locally) or add new history that cancels out old history (non-destructive, safe on shared branches). `git restore`, `git reset`, and `git revert` are the three modern, purpose-built tools; `git clean` handles untracked files, a separate concern none of the other three touch.

## 2. Why It Exists / Problem It Solves

Mistakes are constant and varied in kind: a bad edit not yet staged, a bad edit already staged, a bad commit not yet pushed, a bad commit already pushed and fetched by others, stray generated files cluttering `git status`. A single "undo" command cannot safely handle all of these — undoing a local, unpushed commit can safely rewrite history, while undoing a commit already on a shared branch cannot (§14's Golden Rule applies here too). Git deliberately provides distinct tools scoped to distinct situations rather than one dangerously overloaded command.

## 3. `git restore` — Working Directory & Index Undo

Introduced in Git 2.23 alongside `git switch` (§12's create-and-switch coverage) specifically to give "undo my local edits" a dedicated, narrowly scoped command, splitting this responsibility out of the historically overloaded `git checkout`.

```bash
# Purpose: discard UNSTAGED changes in the working directory, reverting the
# file back to whatever the index currently has for it
$ git restore file.txt

# Purpose: unstage a file — remove it from the index, but LEAVE the working
# directory edits untouched
$ git restore --staged file.txt

# Purpose: restore a file's content from a specific historical commit,
# rather than from the index
$ git restore --source=HEAD~2 file.txt
```

| Command                                  | Working directory                   | Index                                   | Effect                                                                               |
| ---------------------------------------- | ----------------------------------- | --------------------------------------- | ------------------------------------------------------------------------------------ |
| `git restore <file>`                     | **writes** (overwritten from index) | reads                                   | Discards uncommitted edits; matches the index's current version                      |
| `git restore --staged <file>`            | —                                   | **writes** (reverted to HEAD's version) | Unstages; working directory is untouched                                             |
| `git restore --staged --worktree <file>` | **writes**                          | **writes**                              | Fully reverts both staged and unstaged changes back to HEAD's version in one command |

> ⚠️ **Critical clarification:** `git restore <file>` is genuinely destructive to uncommitted work — the discarded edits are not staged, not committed, and therefore not in the object database at all; there is no reflog entry, no recovery path, for content that was only ever in the working directory. Always double-check with `git diff` before running it on anything you might still want.

## 4. `git reset` — Moving the Branch Pointer, With Three Modes

`git reset` moves the current branch's ref to a different commit, and, depending on the mode, also rewrites the index and/or working directory to match.

```
Before: main ──► C1 ──► C2 ──► C3   (HEAD here)

git reset --soft HEAD~1:
  main ──► C1 ──► C2                (HEAD moved; C3's changes now STAGED)

git reset --mixed HEAD~1  (the default):
  main ──► C1 ──► C2                (HEAD moved; C3's changes now UNSTAGED, in working dir)

git reset --hard HEAD~1:
  main ──► C1 ──► C2                (HEAD moved; C3's changes GONE from working dir too)
```

| Mode                | Branch pointer | Index                                                                        | Working directory                                                                      | Typical use                                                                                    |
| ------------------- | -------------- | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `--soft`            | Moved          | **Unchanged relative to old HEAD** — the undone commit's changes land staged | Untouched                                                                              | "I want to redo this commit's message or combine it with new edits, keeping everything staged" |
| `--mixed` (default) | Moved          | Reset to match new HEAD — undone commit's changes become unstaged            | Untouched                                                                              | "Uncommit, but let me re-review and re-stage selectively"                                      |
| `--hard`            | Moved          | Reset to match new HEAD                                                      | **Reset to match new HEAD — uncommitted AND undone-commit changes are gone from disk** | "I want this file state to genuinely no longer exist" — the dangerous one                      |

```bash
# Purpose: undo the last commit but keep its changes staged, ready to amend or recombine
$ git reset --soft HEAD~1

# Purpose: undo the last commit, unstage its changes, leave them in the working directory
$ git reset --mixed HEAD~1     # or simply: git reset HEAD~1

# Purpose: undo the last commit AND discard its changes entirely from disk
$ git reset --hard HEAD~1
```

> ⚠️ **Critical clarification / Common confusion to preempt:** `--hard` is the only one of the three that can destroy working-directory content that was never committed at all — `--soft` and `--mixed` never touch the working directory, so anything sitting there uncommitted survives either of them untouched. The commit(s) `reset` moves you away from are **not** deleted from the object database by any mode — they remain, unreferenced, recoverable via the reflog (§6) until garbage collection — but files that only ever existed in the working directory and were never staged or committed have no such safety net, per the same caveat noted in the `git restore` section above.

`git reset` also works on individual files (not just `HEAD~N`), where it behaves like a plumbing-level partial unstage:

```bash
# Purpose: unstage one specific file without moving the branch pointer at all
$ git reset HEAD -- file.txt
```

This form is what `git restore --staged` (see the `git restore` section above) replaced for the common case — both exist, `restore --staged` is the modern, narrower recommendation.

## 5. `git revert` — Undoing With a New Commit

```bash
# Purpose: create a NEW commit that applies the inverse of a previous commit's changes
$ git revert a1b2c3d
```

Expected output (pauses for a commit message, pre-filled):

```
[main 9f2c1a4] Revert "Add discount code validation"
 1 file changed, 3 deletions(-)
```

`git revert` computes the diff a commit introduced and applies its exact opposite as a **new** commit on top of current history — the original commit is untouched, still fully present, still reachable in `git log`; a brand-new commit sits after it canceling its effect. This is the single largest practical distinction from `reset`: revert **adds** to history rather than rewriting it, making it the only one of these tools that is unconditionally safe to use on a commit that's already been pushed and fetched by others — exactly the situation where `reset` (which moves a branch pointer backward, requiring a force-push to share) runs straight into the Golden Rule (§14).

```bash
# Purpose: revert a range of commits, oldest to newest
$ git revert C1^..C3

# Purpose: revert without auto-committing, letting you review/combine the result first
$ git revert -n a1b2c3d
```

> ⚠️ **Reverting a merge commit** requires specifying which parent's line of history to treat as the "mainline" via `-m <parent-number>` (`git revert -m 1 <merge-commit>`), since a merge commit has two parents and Git cannot infer which side you're reverting relative to — a common trip-up when trying to back out a bad merge.

## 6. `reset` vs `revert` — Direct Contrast

|                                                     | `git reset`                                                       | `git revert`                                                                      |
| --------------------------------------------------- | ----------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Rewrites existing history/refs                      | Yes — branch pointer moves backward                               | No — adds a new commit; nothing existing changes                                  |
| Original commit still in `git log`                  | No (unreferenced, off the branch's line)                          | **Yes**, unchanged, plus a new commit undoing its effect                          |
| Safe on a commit already pushed/shared              | **No** — requires a force-push others must reconcile with (§14's Golden Rule) | **Yes** — the standard, safe way to undo shared history                           |
| Local-only quick cleanup                            | Excellent fit                                                     | Overkill/unnecessary ceremony for something no one else has seen                  |
| Effect on working directory/index (depends on mode) | Can rewrite both (`--hard`)                                       | Never touches anything but committing a new change; behaves like any other commit |

> 💡 **Tip:** A blunt rule of thumb that resolves nearly every "which one do I use" question: **if it's already pushed and someone else might have it, `revert`; if it's purely local and unpushed, `reset` is fine and often simpler.**

## 7. `git clean` — Removing Untracked Files

None of `restore`, `reset`, or `revert` touch **untracked** files — files Git has never been told to track at all (build output, stray scratch files, `.env.local` copies). `git clean` is the dedicated tool for that separate concern.

```bash
# Purpose: DRY RUN — show what would be deleted, without deleting anything
$ git clean -n

# Purpose: actually delete untracked files
$ git clean -f

# Purpose: also delete untracked DIRECTORIES, not just files
$ git clean -fd

# Purpose: also remove files that are untracked BUT ignored via .gitignore
# (e.g., clearing out node_modules or build artifacts entirely)
$ git clean -fdx
```

| Flag               | Effect                                                                                                          |
| ------------------ | --------------------------------------------------------------------------------------------------------------- |
| `-n` / `--dry-run` | Preview only — always run this first                                                                            |
| `-f`               | Actually force deletion (Git refuses to run destructively without it, or `clean.requireForce=false`)            |
| `-d`               | Include untracked directories, not just files                                                                   |
| `-x`               | Also remove files ignored by `.gitignore` (§11) — dangerous if it includes things like local environment config |
| `-i`               | Interactive mode — confirm per file/pattern before deleting                                                     |

> ⚠️ **Critical clarification:** `git clean -f` (and especially `-fdx`) is genuinely, permanently destructive with **no reflog safety net whatsoever** — untracked files were never Git objects to begin with, so there is nothing in `.git/objects` to recover from. Always run `-n` first, without exception, on anything beyond a scratch repo.

## 8. Legacy: `git checkout -- <file>`

Pre-2.23, discarding working-directory changes to a file was `git checkout -- <file>` — the same command, `git checkout`, also used for switching branches (§12's create-and-switch coverage), disambiguated only by the `--` separator marking everything after it as a pathspec, not a branch name.

```bash
# Legacy form — still fully functional, equivalent to `git restore file.txt`
$ git checkout -- file.txt
```

This is exactly the ambiguity §12 described as motivating `switch`/`restore`'s creation — a missing `--`, or a filename that happens to match a branch name, could make Git interpret the command entirely differently. It remains extremely common in existing scripts, tutorials, and muscle memory; recognizing it is essential even though `git restore` is the modern recommendation for new work.

## 9. Decision Table — "I Want to Undo X, in Situation Y"

| Situation                                               | Command                                                       |
| ------------------------------------------------------- | ------------------------------------------------------------- |
| Discard uncommitted edits to a file, not yet staged     | `git restore <file>`                                          |
| Unstage a file, keep the edits in the working directory | `git restore --staged <file>`                                 |
| Undo the last commit, keep its changes staged           | `git reset --soft HEAD~1`                                     |
| Undo the last commit, keep its changes but unstaged     | `git reset HEAD~1` (or `--mixed`)                             |
| Undo the last commit and discard its changes entirely   | `git reset --hard HEAD~1`                                     |
| Undo a commit that's **already been pushed/shared**     | `git revert <commit>`                                         |
| Undo a bad merge that's already been pushed             | `git revert -m 1 <merge-commit>`                              |
| Remove stray untracked scratch files                    | `git clean -n` then `git clean -f` (add `-d` for directories) |
| Wipe untracked files **and** ignored build artifacts    | `git clean -n` then `git clean -fdx`                          |
| "I think I lost a commit entirely"                      | `git reflog`, then `git switch -c <name> <hash>` (§6)       |

## 10. Hands-On — Comparing All Three Modern Tools on the Same Mistake

```bash
$ mkdir undodemo && cd undodemo && git init -q
$ echo "v1" > f.txt && git add . && git commit -qm "v1"
$ echo "v2" > f.txt && git add . && git commit -qm "v2 - actually a mistake"

# Option A: it's local, unpushed — reset is fine and simplest
$ git reset --soft HEAD~1
$ git status
Changes to be committed:
        modified:   f.txt
$ git restore --staged f.txt   # or just leave it staged and re-commit differently

# Option B: pretend "v2" was ALREADY pushed and fetched by a teammate — revert instead
$ git commit -am "v2 - actually a mistake"   # re-create it for this demo
$ git revert --no-edit HEAD
$ git log --oneline
c3d4e5f Revert "v2 - actually a mistake"
9f2c1a4 v2 - actually a mistake
a1b2c3d v1
# Both the mistake AND the correction are visible in history — nothing hidden, nothing rewritten
```

## 11. Troubleshooting

| Symptom                                                                                   | Likely cause                                                                                         | Fix                                                                                                       |
| ----------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- |
| `error: Your local changes ... would be overwritten` during `restore`/`switch`/`checkout` | Uncommitted changes conflict with the target state                                                   | Commit, stash (§16), or deliberately `git restore` to discard first                                       |
| Ran `git reset --hard` and immediately regret it                                          | Working directory changes since the last commit are gone; the commit itself may still be recoverable | `git reflog` to find the pre-reset commit hash; working-directory-only losses have no recovery path       |
| `git clean -f` deleted something important                                                | No `.gitignore` entry protected it, and it wasn't tracked/committed                                  | No recovery via Git; check editor local history, OS backups, or version-aware cloud sync as a last resort |
| `git revert` produces a conflict                                                          | The commit being reverted overlaps with later changes to the same lines                              | Resolve exactly like a merge conflict (§13's conflict-resolution walkthrough): edit markers, `git add`, `git revert --continue`           |

## 12. Interview Questions

**[Beginner] Q1. What's the difference between `git restore` and `git reset`?**
**Model answer:** `git restore` operates on the working directory and/or index without moving the branch pointer at all — it discards uncommitted edits or unstages files, never touching committed history. `git reset` moves the current branch's pointer to a different commit, optionally also resetting the index and working directory to match, depending on `--soft`/`--mixed`/`--hard` — it operates on committed history, undoing commits rather than uncommitted edits.

**[Beginner] Q2. What are the three modes of `git reset`, and what does each one touch?**
**Model answer:** `--soft` moves only the branch pointer, leaving the index and working directory untouched, so the undone commit's changes end up staged and ready to recommit. `--mixed`, the default, moves the branch pointer and resets the index but leaves the working directory alone, so the changes end up unstaged but still present on disk. `--hard` moves the branch pointer and resets both the index and the working directory, so any changes from the undone commit, and any other uncommitted changes, are gone from disk entirely — the only one of the three that can destroy work with no object-database backing.

**[Intermediate] Q3. Why is `git revert` considered safe for shared/pushed commits while `git reset` is not?**
**Model answer:** `git revert` never modifies or removes any existing commit — it computes the inverse of a commit's changes and applies that as a brand-new commit on top of current history, so the original commit remains fully present and reachable, and nothing anyone else already has becomes invalid. `git reset` moves the branch pointer backward, which, if pushed, requires a force-push to share, and anyone who already fetched the "undone" commits now has local history that diverges unrecognizably from the rewritten remote — precisely the Golden Rule failure mode from §14. Revert is additive; reset is subtractive/destructive to the shared ref's history.

**[Senior] Q4. A teammate ran `git reset --hard HEAD~3` and lost work they wanted to keep. Walk through recovery.**
**Model answer:** First determine what exactly was lost. If those three commits were genuinely committed before the reset, they still physically exist in the object database, unreferenced by any branch — `git reflog` will show the pre-reset HEAD position (something like `HEAD@{1}: reset: moving to HEAD~3`), and `git reset --hard HEAD@{1}` (or more safely, `git switch -c recovery-branch HEAD@{1}` to avoid another destructive reset) restores exactly that state. If instead the "lost work" includes uncommitted edits that existed only in the working directory at the time of the `--hard` reset, there is no recovery path through Git at all — those changes were never written as objects, so nothing in `.git` can bring them back; the only remaining options are editor-level local history, OS-level file recovery, or backups outside Git entirely. The key diagnostic question is always "was it committed," because that single fact determines whether Git's reflog-based recovery applies.

**[Senior] Q5. Design a team policy for undoing commits that distinguishes "local mistake" from "public mistake," and explain the reasoning.**
**Model answer:** The dividing line should be whether the commit has been pushed to a shared branch and could plausibly have been fetched by someone else — not simply "is it on the remote," since a personal backup push to a branch nobody else touches is still effectively local. For anything not yet shared, `git reset` (in whichever mode fits) is appropriate and simpler, since there's no one else's history to invalidate. Once a commit is on a shared branch, policy should mandate `git revert`, because it preserves the shared branch's existing commit identities entirely and only adds new history, meaning anyone who already has the old commits experiences a normal, ordinary `git pull` with no rewritten hashes and no need to reconcile diverged history. I'd also explicitly carve out `--force-with-lease` as a narrowly permitted exception for coordinated, communicated rewrites of shared branches (e.g., cleaning up a PR branch before merge, with active collaborators notified) rather than a blanket ban, since an absolute "never force-push" rule is sometimes more restrictive than the actual risk warrants.

## 13. Common Misconceptions

1. **"`reset` and `revert` do the same thing, just with different names."** `reset` moves a branch pointer and can rewrite the index/working directory in place; `revert` never touches existing commits at all and only ever adds a new one. Their safety profiles on shared history are opposite.
2. **"`git reset --hard` deletes the commits I'm resetting past."** It only moves the branch pointer away from them; the commit objects remain in the database, recoverable via reflog, until garbage collection actually prunes truly unreferenced objects.
3. **"`git clean` has a reflog-based undo, same as reset/rebase."** Untracked files were never Git objects — `git clean -f` has no recovery path through Git whatsoever. Always dry-run (`-n`) first.
4. **"`git checkout -- <file>` is deprecated."** It still works exactly as before; `git restore` is the newer, narrower, recommended alternative, not a replacement that removes the old form.
5. **"Reverting a commit removes it from history."** The opposite — the original commit stays fully visible in `git log`; a new commit is added afterward canceling its effect. Both are permanently part of the record.

## 14. 🔑 Key Takeaways

- `git restore` undoes uncommitted working-directory/index changes; `git reset` moves the branch pointer through committed history with three modes of increasing destructiveness (`--soft`/`--mixed`/`--hard`); `git revert` adds a new commit that cancels an old one without touching existing history.
- The single most load-bearing distinction: `reset` rewrites/removes refs to existing history (unsafe once shared, per §14's Golden Rule), while `revert` only ever adds new commits (always safe, even on shared branches).
- `git clean` is the separate tool for untracked files, with **no reflog safety net** — always dry-run (`-n`) before forcing.
- Commit objects removed from a branch's line by `reset` are not deleted; they remain recoverable via the reflog (§6) until garbage collection. Working-directory-only content has no such backing and, once discarded, is unrecoverable through Git.
- `git checkout -- <file>` is the legacy equivalent of `git restore <file>`, still fully functional, superseded in recommendation but not removed.

## 15. Related Concepts & What's Next

Undoing committed or staged work is one thing; §16 covers the adjacent, distinct need to temporarily set aside **uncommitted** work-in-progress without committing it at all — stashing — which is often the right tool reached for just before you'd otherwise be tempted to use one of this section's more destructive options.
