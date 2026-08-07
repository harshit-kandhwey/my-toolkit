# Section 14 (Part 4): Rebasing — Standard, Interactive, Autosquash & the Golden Rule

## 1. Definition

**Plain language:** Rebasing takes the commits you made on your branch and replays them, one by one, on top of a different starting point — as if you had started your work there in the first place — instead of joining the two histories together with a merge commit.

**Precise:** `git rebase <upstream>` identifies the commits unique to the current branch since it diverged from `<upstream>`, then, for each one in order, reapplies its content diff on top of `<upstream>`'s current tip, producing a **brand-new commit** with a new hash and new parent for each original commit. The original commits are left untouched and unreferenced (recoverable via the reflog, [§6](../Part2/Section-06-Part2-References-Branches-HEAD-Tags-Reflog.md)) while the current branch's ref is moved to point at the tip of the newly created sequence.

## 2. Why It Exists / Problem It Solves

[§13](./Section-13-Part4-Merging.md)'s three-way merge is safe and non-destructive but leaves a permanent, branchy record of every reconciliation — a merge commit for every sync with `main`, however trivial. Rebasing offers a different trade-off: a **linear** history that reads as if the work happened serially, with no merge commits cluttering `git log`, at the cost of rewriting commit identities. Teams that value `git log --oneline` reading as a clean, linear story — and `git bisect` ([§19](./Section-19-Part4-Interrogating-History.md)) walking a simple line rather than a tangled graph — reach for rebase specifically to get that shape.

## 3. Standard Rebase — Mechanics

```
Before rebase:

  main    ──► C1 ──► C2 ──► C5
                ╲
                 ╲──► C3 ──► C4   ◄── feature (your branch)

`git switch feature && git rebase main`:

  main    ──► C1 ──► C2 ──► C5
                              ╲
                               ╲──► C3' ──► C4'   ◄── feature (moved)

  C3 and C4 still exist in the object database, unreferenced by any
  branch — recoverable via reflog until garbage collected.
```

```bash
$ git switch feature
$ git rebase main
```

Expected output (no conflicts):

```
Successfully rebased and updated refs/heads/feature.
```

Mechanically, Git: (1) finds the merge base of `feature` and `main` — exactly the same computation as [§13](./Section-13-Part4-Merging.md)'s three-way merge; (2) temporarily sets `feature` aside as a list of commits (`C3`, `C4`) to replay; (3) resets the working tree to `main`'s tip; (4) applies each commit's diff in order, creating a new commit object each time, since each new commit's parent hash differs from the original's, its own hash necessarily differs too, per [§5](../Part2/Section-05-Part2-Object-Model.md)'s commit-object chaining; (5) finally moves `feature`'s ref to the last newly created commit.

> ⚠️ **Critical clarification:** rebasing does not "move" commits in any literal sense — it creates entirely new commit objects with the same tree content-diff but different parents (and therefore different hashes), then abandons the originals. This is the direct, unavoidable consequence of commit identity being computed from content including the parent hash ([§5](../Part2/Section-05-Part2-Object-Model.md)'s commit-object coverage) — there is no way to change a commit's ancestry without changing its identity.

## 4. Rebase vs Merge — Trade-offs

|                                    | Merge ([§13](./Section-13-Part4-Merging.md))       | Rebase                                                                                           |
| ---------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| History shape                      | Preserves the true, branchy shape of what happened | Rewrites into a clean, linear sequence                                                           |
| Commit hashes                      | Original commits untouched                         | Every replayed commit gets a new hash                                                            |
| Safe on shared/pushed commits      | Yes, always                                        | **No** — see the Golden Rule, 14.6                                                               |
| New commit created                 | Only a merge commit (or none, if fast-forwarded)   | None joining the histories; each original commit is individually replaced                        |
| `git bisect`/`git log` readability | Graph can get visually noisy with many merges      | Clean, easy to read serially                                                                     |
| Conflict resolution effort         | Resolve once, for the whole merge                  | Potentially resolve the same conflict repeatedly, once per replayed commit                       |
| Typical policy                     | Default for integrating into shared branches       | Common for cleaning up a personal feature branch before opening a PR, or for `git pull --rebase` |

Neither is universally "correct" — it's a genuine team-culture and workflow decision, revisited at the strategy level in [§22](../Part5/Section-22-Part5-Branching-Strategies.md).

## 5. Interactive Rebase: `git rebase -i`

Interactive rebase opens an editor listing every commit about to be replayed, one per line, letting you choose what happens to each before any replay occurs.

```bash
$ git rebase -i HEAD~3
```

Editor content:

```
pick a1b2c3d Add search input
pick d4e5f6a Fix search input typo
pick 7c2a9f1 Add search results rendering

# Rebase 9f2c1a4..7c2a9f1 onto 9f2c1a4 (3 commands)
#
# Commands:
# p, pick <commit> = use commit
# r, reword <commit> = use commit, but edit the commit message
# e, edit <commit> = use commit, but stop for amending
# s, squash <commit> = use commit, but meld into previous commit
# f, fixup <commit> = like "squash", but discard this commit's log message
# d, drop <commit> = remove commit
```

| Command  | Effect                                                                                                                                     |
| -------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `pick`   | Replay the commit unchanged (the default for every line)                                                                                   |
| `reword` | Replay the commit, but pause to let you edit its message                                                                                   |
| `edit`   | Replay the commit, then pause entirely — working tree is at that commit, letting you amend content, split it, or inspect before continuing |
| `squash` | Meld this commit into the **previous** line's commit, combining both diffs into one, and open an editor to merge their messages            |
| `fixup`  | Same as `squash`, but silently discard this commit's message, keeping only the previous one's                                              |
| `drop`   | Discard the commit entirely (equivalent to deleting the line)                                                                              |

### 5.1 Worked example — squashing three commits into one

```bash
$ git log --oneline
7c2a9f1 Add search results rendering
d4e5f6a Fix search input typo
a1b2c3d Add search input
9f2c1a4 Previous stable commit

$ git rebase -i HEAD~3
```

Change the editor content to:

```
pick a1b2c3d Add search input
squash d4e5f6a Fix search input typo
squash 7c2a9f1 Add search results rendering
```

Git then opens a second editor to combine all three commit messages into one, which you edit down to a single clean message (e.g., "Add search feature"). Result:

```bash
$ git log --oneline
e8f1a2b Add search feature
9f2c1a4 Previous stable commit
```

Three commits, three separate hashes, are now one commit with one new hash — the classic "clean up my messy WIP history before opening a pull request" workflow.

> 💡 **Tip:** Reordering lines in the interactive rebase editor reorders the replay itself — Git applies commits top-to-bottom exactly as listed, so moving a line up genuinely changes the sequence history is replayed in, not just its display order.

## 6. Autosquash: `--fixup`, `--squash`, `--autosquash`

Manually reordering and relabeling lines for a "fix an earlier commit" scenario is tedious; autosquash automates it.

```bash
# Purpose: create a commit explicitly marked as a fixup FOR an earlier commit,
# identified by its hash or any unique substring of its message
$ git commit --fixup=a1b2c3d

# Purpose: same idea, but meant to be SQUASHED (message combined, not discarded)
$ git commit --squash=a1b2c3d
```

```bash
# Purpose: rebase interactively, automatically reordering fixup!/squash! commits
# next to their targets and pre-filling the right rebase command for each
$ git rebase -i --autosquash HEAD~5
```

`git commit --fixup=a1b2c3d` creates a commit whose message is literally prefixed `fixup! <original subject>` — `--autosquash` scans for that prefix, moves the commit directly beneath its target in the rebase plan, and marks it `fixup` automatically, so you never have to manually reorder or relabel lines yourself. `git config --global rebase.autoSquash true` makes this the default behavior for every interactive rebase, so you don't need to remember the flag.

## 7. The Golden Rule of Rebasing

> ⚠️ **Critical clarification: never rebase commits that other people already have.** Once you've pushed a commit and anyone else may have fetched it, rebasing rewrites it into a new commit with a different hash — from their perspective, the commit they have and the commit you now have share no identity at all, even though the content is nearly the same.

**The concrete failure mode:**

```
You push commits C1, C2 to origin. A teammate fetches and builds C3 on top of C2.

  origin/main:  ... ──► C1 ──► C2
  teammate:     ... ──► C1 ──► C2 ──► C3 (their own new work)

You then rebase your LOCAL history (say, onto a newer main) and force-push:

  origin/main:  ... ──► C1' ──► C2'   (rewritten, different hashes)

Teammate's next `git pull`:

  Their C1 ──► C2 ──► C3 no longer has ANY common ancestor with the
  new origin/main as far as a normal merge/fast-forward can see —
  Git either creates a confusing duplicate merge of unrelated-looking
  history, or the teammate's push is rejected outright, or (worst case)
  they force-push their own version back, silently resurrecting C1/C2
  and burying your rewritten history.
```

The rule in practice: rebase freely on branches only you use (your own local feature branch before its first push, or before anyone else has fetched it); once a branch is shared, prefer merging, or coordinate explicitly with the team before any rewrite that requires a force-push (`git push --force-with-lease`, a safer variant covered fully in [§29](../Part7/Section-29-Part7-Maintenance-Performance-Troubleshooting.md)-adjacent disaster-recovery material and referenced again in [§22](../Part5/Section-22-Part5-Branching-Strategies.md)'s workflow policies).

> 💡 **Tip:** "Already pushed" is not automatically "shared" — a personal feature branch pushed only as a backup, that no one else has fetched from, is still safe to rebase and force-push. The rule is about whether _anyone else's local history_ might already be built on the commits you're about to rewrite, not about whether the commits technically exist on a remote.

## 8. Rebase Conflicts: `--continue` / `--skip` / `--abort`

Because rebase replays commits **one at a time**, a conflict can occur on any individual commit in the sequence — and, unlike a merge's single resolution point, you may need to resolve conceptually the same conflict more than once if multiple replayed commits touch the same lines.

```bash
$ git rebase main
Auto-merging pricing.js
CONFLICT (content): Merge conflict in pricing.js
error: could not apply d4e5f6a... Adjust discount logic
```

```bash
# 1. Resolve the conflict exactly as in §13's conflict-resolution walkthrough — edit out markers, then:
$ git add pricing.js

# 2. Tell rebase to proceed with the NEXT commit in the sequence
$ git rebase --continue

# Alternative: give up on this ONE commit, discarding just its changes,
# and move on to the next commit in the replay sequence
$ git rebase --skip

# Alternative: abandon the entire rebase, restoring the branch to exactly
# where it was before `git rebase` was run
$ git rebase --abort
```

`git status` during a paused rebase names the specific commit currently being applied and reminds you of all three options — the same discoverability pattern as a paused merge ([§13](./Section-13-Part4-Merging.md)'s abort-and-recovery coverage).

## 9. `git pull --rebase`

Plain `git pull` is `git fetch` followed by `git merge` — if your local branch has diverged from the remote-tracking branch, this creates a merge commit purely for "I had local commits and the remote had new ones too," which many find noisy for routine syncing.

```bash
# Purpose: fetch, then REBASE local commits on top of the fetched remote tip
# instead of merging — avoids a "sync merge commit" for routine pulls
$ git pull --rebase
```

```bash
# Purpose: make this the default behavior for every pull, repo-wide or globally
$ git config --global pull.rebase true
```

> ⚠️ **Common confusion to preempt:** `git pull --rebase` is safe specifically because it rebases _your own local, not-yet-pushed_ commits onto the newly fetched remote tip — it does not rewrite anything already on the remote. This does not violate the Golden Rule; it's rebasing exactly the kind of commit the rule says is safe (yours, not yet visible to anyone else in this form).

## 10. Hands-On — Rebase, Conflict, and Recovery Together

```bash
$ mkdir rebasedemo && cd rebasedemo && git init -q
$ echo "base" > f.txt && git add . && git commit -qm "base"

$ git switch -c feature
$ echo "feature line" >> f.txt && git commit -qam "feature change"

$ git switch main
$ echo "main line" >> f.txt && git commit -qam "main change"

$ git switch feature
$ git rebase main
Auto-merging f.txt
CONFLICT (content): Merge conflict in f.txt
error: could not apply ... feature change

$ cat f.txt
base
<<<<<<< HEAD
main line
=======
feature line
>>>>>>> feature change

$ printf "base\nmain line\nfeature line\n" > f.txt
$ git add f.txt
$ git rebase --continue
Successfully rebased and updated refs/heads/feature.

# If this had gone wrong entirely:
$ git rebase --abort     # returns feature to its pre-rebase state
# or, after completing, recover the ORIGINAL pre-rebase commits via reflog:
$ git reflog
$ git reset --hard HEAD@{2}    # example position — see §6 / §15
```

## 11. Production & Enterprise Usage

- Hosting platforms' "Rebase and merge" PR button performs exactly the mechanics of this section, non-interactively, replaying the PR's commits directly onto the target branch's tip and fast-forwarding — no merge commit results.
- `rebase.autoSquash` and `pull.rebase` are common team-wide `.gitconfig` or repo-template defaults specifically to keep contribution history clean without relying on individual discipline.
- CI pipelines that run on every push to a feature branch can be confused by force-pushes after a rebase (the "same branch, entirely different commits" scenario) — some CI systems specifically detect and re-trigger cleanly on this, others accumulate stale, confusing run history; understanding _why_ it happens (the standard-rebase mechanics covered earlier) is the prerequisite for configuring it correctly.

## 12. Troubleshooting

| Symptom                                                                      | Likely cause                                                                                                  | Fix                                                                                                                                                                                                           |
| ---------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `error: cannot rebase: You have unstaged changes`                            | Dirty working directory before starting the rebase                                                            | Commit or stash ([§16](./Section-16-Part4-Stashing.md)) first                                                                                                                                                 |
| Same conflict appears to resolve, then reappears on the next commit          | Multiple replayed commits touch the same lines — expected with rebase, unlike merge's single resolution point | Resolve each occurrence; consider squashing (see the interactive rebase section above) related commits first to reduce repeated conflicts                                                                     |
| Teammate's push rejected after your rebase-and-force-push to a shared branch | Exactly the Golden Rule failure mode (see the Golden Rule of Rebasing section above)                          | Coordinate: they should back up their work, reset onto your rewritten history, then reapply their commits — or you should not have rebased a shared branch                                                    |
| Commits "disappeared" after a rebase                                         | They were replaced by new commits with new hashes; originals still exist, unreferenced                        | `git reflog` to find the pre-rebase tip, `git reset --hard` or `git switch -c` from it ([§6](../Part2/Section-06-Part2-References-Branches-HEAD-Tags-Reflog.md), [§15](./Section-15-Part4-Undoing-Things.md)) |

## 13. Interview Questions

**[Beginner] Q1. What does `git rebase` actually do, mechanically?**
**Model answer:** It takes the commits unique to your current branch since it diverged from the target, and replays each one's content changes, in order, on top of the target branch's current tip — creating a brand-new commit for each original one, with a new parent and therefore a new hash. The original commits aren't modified in place; they're left behind, unreferenced by any branch, while your branch's pointer moves to the tip of the newly created sequence.

**[Intermediate] Q2. Why does every rebased commit get a new hash, even ones that had no actual conflict during the replay?**
**Model answer:** A commit's hash is computed over its full content, which includes its parent commit's hash as literal text. Rebasing changes what a commit's parent is — even the very first commit replayed now has a different parent than it originally did — so its content, and therefore its hash, is different, even if the file diff it introduces is identical. Every subsequent replayed commit in the sequence then also has a new parent (the previous commit's new hash), cascading the same effect down the whole chain, regardless of whether any individual commit needed conflict resolution.

**[Intermediate] Q3. What's the difference between `squash` and `fixup` in an interactive rebase?**
**Model answer:** Both combine a commit into the previous one in the rebase plan, merging their content changes into a single resulting commit. The difference is entirely about the commit message: `squash` opens an editor letting you combine both commits' messages into one, while `fixup` silently discards the fixup commit's message and keeps only the previous commit's message unchanged. `fixup` is the natural choice when the commit being folded in is purely a small correction with no message worth preserving — commonly generated automatically via `git commit --fixup=<hash>` and cleaned up with `git rebase -i --autosquash`.

**[Senior] Q4. State the Golden Rule of rebasing precisely, and explain the actual mechanism behind why violating it causes problems.**
**Model answer:** Never rebase commits that other people may already have fetched and potentially built work on top of. The mechanism: rebasing produces new commit objects with new hashes for what is conceptually "the same" work, so from a collaborator's perspective, the commits they already have and the rewritten commits you're about to push share no identity or ancestry relationship a normal merge or fast-forward can recognize. If they've already built commits on top of the old version, syncing after your rewrite either produces a confusing duplicate-looking merge, a rejected push on their end, or, in the worst case, someone force-pushes over someone else's work and silently discards it. The rule specifically concerns whether anyone else's local history might depend on the commits being rewritten — a branch that's technically been pushed but that no one else has fetched or built on is still safe to rebase and force-push; the risk is about downstream dependents' history, not the mere existence of a remote copy.

**[Senior] Q5. When would you choose rebase over merge for integrating a long-running feature branch back into `main`, and when would that choice be actively wrong?**
**Model answer:** Rebase is attractive when the team values a clean, linear `main` history and the feature branch is still exclusively the author's own — rebasing it onto `main`'s latest tip before opening or updating a pull request lets the eventual merge be a trivial fast-forward, and keeps `git log`/`git bisect` easy to reason about serially. It becomes actively wrong the moment the branch is shared: if multiple people are collaborating on that same feature branch and have already built commits on top of each other's pushed work, rebasing and force-pushing rewrites history out from under collaborators, triggering the Golden Rule failure mode. It's also a weaker choice when preserving the true, exact record of what happened and when genuinely matters for audit or compliance purposes — a merge commit's two-parent structure is an honest record of two lines of work joining, whereas a rebase actively erases the fact that the work was ever temporally divergent, which some regulated environments explicitly want to avoid rewriting away.

## 14. Common Misconceptions

1. **"Rebase moves my commits to a new location."** It creates entirely new commit objects and abandons the originals; nothing is literally moved, because a commit's identity is inseparable from its parent, and the parent has changed.
2. **"Rebasing is always safer/cleaner than merging, so prefer it by default."** It's a trade-off, not a strict improvement — it discards true historical shape and is actively dangerous on shared branches, where merging remains the only safe option.
3. **"`git pull --rebase` violates the Golden Rule."** It doesn't — it rebases your own local, not-yet-shared commits onto the newly fetched tip, which is exactly the kind of rebase the rule says is fine.
4. **"If a rebase conflict is resolved once, it won't happen again in the same rebase."** Each replayed commit is applied independently; the same lines can conflict again on a later commit in the sequence if multiple commits touch that region.
5. **"Once a rebase completes, the original commits are gone."** They still physically exist in the object database, unreferenced by any branch, and are recoverable via the reflog until garbage collection actually prunes them ([§6](../Part2/Section-06-Part2-References-Branches-HEAD-Tags-Reflog.md), [§15](./Section-15-Part4-Undoing-Things.md)).

## 15. 🔑 Key Takeaways

- Rebase replays your branch's unique commits onto a new base one at a time, producing new commit objects with new hashes and abandoning the originals — it does not literally move anything.
- Interactive rebase (`pick`/`reword`/`edit`/`squash`/`fixup`/`drop`) is the primary tool for cleaning up a personal branch's history before sharing it; `--autosquash` automates the common "fix an earlier commit" pattern.
- The Golden Rule: never rebase commits that others may already have fetched and built on — the mechanism is that rewriting produces new hashes with no recognizable ancestry link to what collaborators already have.
- Rebase conflicts are resolved per-commit in the replay sequence via `--continue`/`--skip`/`--abort`, potentially repeating for the same lines across multiple commits.
- `git pull --rebase` is safe and does not violate the Golden Rule, because it only rebases your own unshared local commits.

## 16. Related Concepts & What's Next

Both merging ([§13](./Section-13-Part4-Merging.md)) and rebasing rewrite or reconcile committed history going _forward_. [§15](./Section-15-Part4-Undoing-Things.md) turns to the opposite problem: undoing work that's already been done — the distinct tools (`restore`, `reset`, `revert`, `clean`) for discarding uncommitted changes, moving a branch pointer backward, or safely undoing an already-shared commit without the Golden Rule risk this section just established.
