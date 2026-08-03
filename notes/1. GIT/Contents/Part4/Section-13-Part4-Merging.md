# Section 13 (Part 4): Merging — Fast-Forward, Three-Way Merges, Strategies & Conflict Resolution

## 1. Definition

**Plain language:** Merging is how you bring the work from one branch back into another — taking two lines of development that diverged and combining them into a single, unified line again.

**Precise:** `git merge <branch>` integrates the commit history of `<branch>` into the currently checked-out branch. Depending on the ancestry relationship between the two tips, Git performs one of two fundamentally different operations: a **fast-forward** (simply moving the current branch's pointer forward, when no divergence occurred) or a **three-way merge** (computing a diff against a common ancestor and creating a new **merge commit** with two parents, when both branches have unique commits).

## 2. Why It Exists / Problem It Solves

§12 gave you cheap, instant branches — the natural consequence is that work constantly diverges. Merging is the half of the branch lifecycle that reunites it: without a reliable, automatic way to combine parallel lines of development, branching would be a one-way trip, and the entire copy-modify-merge philosophy from §1's distributed-model discussion that Git is built on would collapse back into manual, error-prone reconciliation.

## 3. Fast-Forward Merges — Mechanics

A fast-forward is possible precisely when the branch you're merging _in_ is a direct descendant of your current branch's tip — meaning your current branch hasn't moved at all since the two diverged. There's nothing to reconcile: Git simply slides the current branch's pointer forward to match.

```
Before merge:

  refs/heads/main ────► C1 ──► C2
                                 ▲
                        refs/heads/feature ──► C3 ──► C4

After `git checkout main && git merge feature` (fast-forward):

  refs/heads/main ─────────────────────────────► C4
                                                    ▲
                                       refs/heads/feature
```

```bash
# Purpose: demonstrate a fast-forward merge end to end
$ git switch -c feature-notes
$ echo "notes" > notes.txt && git add notes.txt && git commit -m "Add notes"
$ git switch main
$ git merge feature-notes
```

Expected output:

```
Updating a3f8e21..9f2c1a4
Fast-forward
 notes.txt | 1 +
 1 file changed, 1 insertion(+)
```

No new commit object is created. `main` now points at exactly the same commit `feature-notes` points at — indistinguishable, at the ref level, from having committed those changes directly on `main`.

> ⚠️ **Common confusion to preempt:** fast-forward is not something you request — it's something Git _chooses_ automatically whenever the ancestry allows it. If you want a merge commit to exist regardless, you must explicitly suppress fast-forwarding with `--no-ff` (the forcing-a-merge-commit section below).

## 4. Three-Way Merges — Mechanics

When both branches have unique commits since they diverged, there is no single pointer move that represents "both". Git instead performs a **three-way merge**, comparing three trees:

1. The **merge base** — the nearest common ancestor commit of the two branch tips (found via a graph traversal, exposed directly by `git merge-base <branch1> <branch2>`).
2. **Ours** — the tree at the tip of the current branch.
3. **Theirs** — the tree at the tip of the branch being merged in.

For each file, Git compares what changed from the base to _ours_ and from the base to _theirs_. If only one side changed a given region, that side's version wins automatically — this is the vast majority of real-world merges and requires no human involvement at all. Only when **both sides changed the same region** does Git produce a **conflict** (see the conflict anatomy section below).

```
             C1 (merge base)
           ╱    ╲
          ╱      ╲
    main C2      C3 feature
    (ours) ╲     ╱  (theirs)
            ╲   ╱
             ╲ ╱
             M4  ◄── new merge commit, TWO parents: C2 and C3
```

```bash
$ git switch main
$ git merge feature-payments
```

Expected output (clean merge, no conflicts):

```
Merge made by the 'ort' strategy.
 payments.js | 12 ++++++++++++
 1 file changed, 12 insertions(+)
```

The resulting merge commit `M4` is structurally ordinary except for one thing: its commit object (§5's commit-object coverage) lists **two** `parent` lines instead of one. Everything else about it — a root tree, author/committer, a message — is identical in shape to any other commit.

> 💡 **Tip:** `git merge-base main feature-payments` prints the exact commit Git is using as the common ancestor — genuinely useful when you need to understand _why_ a merge behaved the way it did, or to manually diff "what changed on this branch since it diverged" (`git diff $(git merge-base main feature) feature`).

## 5. `--no-ff` — Forcing a Merge Commit

```bash
# Purpose: always create a merge commit, even when a fast-forward is possible
$ git merge --no-ff feature-notes
```

Expected output:

```
Merge made by the 'ort' strategy.
```

`--no-ff` deliberately sacrifices the fast-forward shortcut to preserve **topological information**: with `--no-ff`, every feature branch leaves a permanent, visible bump in the graph marking exactly when and how it was integrated, even if it could have been silently folded in as a pointer move. Many teams mandate `--no-ff` for all pull-request merges specifically so `git log --graph` remains a legible record of "what was a feature" rather than a flat, undifferentiated line of commits.

|                     | Fast-forward (default when possible)                                   | `--no-ff`                                                       |
| ------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------- |
| New commit created? | No                                                                     | Yes, even if a fast-forward was possible                        |
| History shape       | Linear, feature branch's commits absorbed indistinguishably            | Branch structure preserved as a visible merge bump              |
| Typical use         | Small personal branches, trunk-based workflows favoring linear history | Team workflows wanting an explicit record of feature boundaries |

The inverse flag, `--ff-only`, refuses to merge at all unless a fast-forward is possible — useful in scripts/CI that want to guarantee no surprise merge commit is ever silently created.

## 6. Merge Strategies vs Strategy Options — The Genuinely Confusing Distinction

This trips up even experienced engineers because Git overloads similar-sounding flags for two entirely different concepts.

- **`-s <strategy>` (a merge STRATEGY)** selects the _algorithm_ Git uses to perform the merge at a structural level — how it walks the graph, how many parents it can handle, whether it looks at content at all.
- **`-X <option>` (a strategy OPTION)** is a fine-tuning knob passed _to_ whichever strategy is running — it doesn't change the algorithm, only how that algorithm behaves in specific situations like a per-file conflict.

```bash
# Selects the STRATEGY (the algorithm)
$ git merge -s recursive feature-x

# Selects an OPTION passed to that strategy (still runs the recursive/ort algorithm,
# just tells it how to auto-resolve certain conflicts)
$ git merge -X ours feature-x
```

| Strategy (`-s`)              | What it is                                                                                                          | When Git uses it                                                                   |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| `ort` (default, Git 2.34+)   | "Ostensibly Recursive Twist" — the modern rewrite of `recursive`, faster and more correct on renames                | Default for merging two branches                                                   |
| `recursive` (legacy default) | Predecessor to `ort`; still available, still correct, just superseded                                               | Explicitly requested, or on older Git                                              |
| `resolve`                    | An older, simpler three-way merge, only handles two heads, doesn't handle renames as well                           | Rarely chosen manually today                                                       |
| `octopus`                    | Merges **more than two** branches simultaneously in one commit                                                      | Default automatically when you pass more than one branch to `git merge`            |
| `ours`                       | Records a merge but **discards all content changes from the other branch entirely** — keeps your tree exactly as-is | Deliberately "pretend to merge, keep only our history," a narrow and rare use case |
| `subtree`                    | A variant for merging a whole separate project as a subdirectory                                                    | Legacy alternative to `git subtree` (§27)                                          |

| Strategy Option (`-X`)   | Effect                                                                                                                                             | Requires strategy |
| ------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------- |
| `-X ours`                | On a genuine per-file/per-hunk **conflict**, prefer _our_ side automatically, but still incorporate the other branch's **non-conflicting** changes | `ort`/`recursive` |
| `-X theirs`              | Same, but prefer the incoming branch's side on conflicts                                                                                           | `ort`/`recursive` |
| `-X ignore-space-change` | Don't treat whitespace-only differences as conflicts                                                                                               | `ort`/`recursive` |
| `-X renormalize`         | Re-apply `.gitattributes` (§11) normalization before comparing, avoiding spurious line-ending conflicts                                            | `ort`/`recursive` |

> ⚠️ **Critical clarification / Common confusion to preempt:** `-s ours` and `-X ours` sound identical but do drastically different things. `git merge -s ours feature-x` produces a merge commit that **records feature-x as merged in the graph but silently discards every one of its content changes** — the resulting tree is byte-identical to what you had before, full stop, even for files feature-x never touched conflictingly. `git merge -X ours feature-x` performs a **real** three-way merge, incorporating feature-x's non-conflicting changes normally, and only falls back to "prefer our side" on the specific hunks that genuinely conflict. Using `-s ours` when you meant `-X ours` is a classic way to accidentally throw away an entire branch's work while the commit log claims it was merged.

## 7. Conflict Anatomy — Reading Conflict Markers

When the same region of a file was changed differently on both sides, Git cannot pick automatically and writes **conflict markers** directly into the working-directory file, leaving the merge paused mid-way.

```bash
$ git merge feature-pricing
Auto-merging pricing.js
CONFLICT (content): Merge conflict in pricing.js
Automatic merge failed; fix conflicts and then commit the result.
```

Opening `pricing.js`:

```
function getDiscount(user) {
<<<<<<< HEAD
  return user.isPremium ? 0.20 : 0.05;
=======
  return user.isPremium ? 0.25 : 0.10;
>>>>>>> feature-pricing
}
```

- `<<<<<<< HEAD` down to `=======` is **your** current branch's version (the "ours" side).
- `=======` down to `>>>>>>> feature-pricing` is the **incoming** branch's version (the "theirs" side).
- The branch name after `>>>>>>>` names exactly which ref you're merging in — useful confirmation when merging several branches in sequence.

`git status` during a conflict lists every conflicted path under "Unmerged paths," and `git diff` shows conflict markers inline with `++<<<<<<<` style annotations distinguishing which side each line belongs to.

## 8. Resolving a Conflict — Worked Example, Step by Step

```bash
# 1. See what's conflicted
$ git status
On branch main
You have unmerged paths.
  (fix conflicts and run "git commit")
Unmerged paths:
  (use "git add <file>..." to mark resolution)
        both modified:   pricing.js

# 2. Open pricing.js, decide on the correct final content, and edit out the
#    markers entirely — Git does NOT remove them for you
```

Manually edited to the intended resolution:

```javascript
function getDiscount(user) {
  return user.isPremium ? 0.25 : 0.1;
}
```

```bash
# 3. Stage the resolved file — this is how you tell Git "this conflict is resolved"
$ git add pricing.js

# 4. Confirm nothing else is still conflicted
$ git status
All conflicts fixed but you are still merging.
  (use "git commit" to conclude merge)

# 5. Complete the merge — Git pre-fills a merge commit message; accepting it is normal
$ git commit
```

Expected output:

```
[main 7c2a9f1] Merge branch 'feature-pricing'
```

> 💡 **Tip:** For multi-file conflicts, a configured mergetool (§8's mergetool configuration) turns this into a guided visual workflow — `git mergetool` launches your registered tool per conflicted file and stages each one automatically once you close it with a resolution saved.

## 9. `git merge --abort` — Backing Out Entirely

If a conflict resolution turns out to be more than you want to deal with right now, or you realize you merged the wrong branch:

```bash
# Purpose: cancel an in-progress merge and return to the exact pre-merge state
$ git merge --abort
```

This restores the working directory, index, and branch pointer to precisely how they were before `git merge` was run — as though the merge attempt never happened. It only works while a merge is actually in progress (i.e., conflict markers are still unresolved); once you've committed the merge, `--abort` is no longer applicable and undoing it becomes a `git reset`/`git revert` question instead (§15).

## 10. Squash Merges: `--squash`

```bash
# Purpose: bring feature-x's changes into main as a SINGLE new commit,
# with no merge commit and no ancestry link recorded
$ git switch main
$ git merge --squash feature-x
$ git status
Changes to be committed:
        modified:   app.js
        new file:   feature.js
$ git commit -m "Add feature X (squashed)"
```

`--squash` computes the combined diff of everything on `feature-x` since it diverged and stages it exactly as if you'd made those edits yourself right now — it deliberately does **not** create a merge commit, does **not** record `feature-x` as a parent, and leaves `main`'s history perfectly linear as though one person wrote one large commit. This is a genuinely different operation from `--no-ff`, which goes out of its way to _preserve_ ancestry — squash goes out of its way to _discard_ it, trading a clean, granular history on the feature branch for a single, tidy entry on the target branch.

|                                                                   | Ordinary merge               | `--no-ff` merge                           | `--squash` merge                                                                         |
| ----------------------------------------------------------------- | ---------------------------- | ----------------------------------------- | ---------------------------------------------------------------------------------------- |
| Merge commit created                                              | Only if not fast-forwardable | Always                                    | Never                                                                                    |
| Two parents recorded                                              | If a merge commit exists     | Yes                                       | No — single-parent commit, or none until you commit                                      |
| Feature branch's individual commits preserved in target's history | Yes                          | Yes                                       | No — collapsed into one                                                                  |
| Common use                                                        | Default day-to-day merging   | Teams wanting explicit feature boundaries | Platforms' "Squash and merge" PR button, keeping `main` history to one entry per feature |

## 11. Hands-On — Full Merge Lifecycle With a Conflict

```bash
$ mkdir mergedemo && cd mergedemo && git init -q
$ echo "v1" > shared.txt && git add . && git commit -q -m "base"

$ git switch -c branch-a
$ echo "branch-a change" > shared.txt && git commit -qam "A changes shared.txt"

$ git switch main
$ git switch -c branch-b
$ echo "branch-b change" > shared.txt && git commit -qam "B changes shared.txt"

$ git switch main
$ git merge branch-a          # fast-forward or three-way depending on main's state
$ git merge branch-b          # this one WILL conflict — both touched shared.txt
Auto-merging shared.txt
CONFLICT (content): Merge conflict in shared.txt
Automatic merge failed; fix conflicts and then commit the result.

$ cat shared.txt
<<<<<<< HEAD
branch-a change
=======
branch-b change
>>>>>>> branch-b

$ echo "resolved: combining both intents" > shared.txt
$ git add shared.txt
$ git commit -m "Merge branch-b, resolving conflict with branch-a"
```

## 12. Production & Enterprise Usage

- Hosting platforms' pull-request "Merge" button typically offers three modes mapping directly onto this section: **Merge commit** (ordinary/`--no-ff`), **Squash and merge** (the squash-merges section above), and **Rebase and merge** (§14) — the platform-level names for exactly the mechanics taught here.
- Branch protection rules (§23) commonly require PR checks (CI, review approval) to pass before the merge button is even enabled, but the underlying `git merge` mechanics are identical whether triggered by a human locally or by the platform's merge button.
- Large teams frequently standardize on one merge mode repo-wide specifically to keep `git log --graph` legible and consistent — mixing all three freely produces a genuinely confusing history over time.

## 13. Troubleshooting

| Symptom                                                                                                                         | Likely cause                                                                                 | Fix                                                                                                                     |
| ------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `fatal: You have not concluded your merge (MERGE_HEAD exists)`                                                                  | Trying to start a new operation while a conflicted merge is still unresolved                 | Finish resolving and `git commit`, or `git merge --abort` first                                                         |
| Merge succeeds automatically but produced the "wrong" result on a file both sides touched in different, non-overlapping regions | Git's three-way merge correctly combined non-overlapping edits — this is expected, not a bug | Review with `git diff <merge-base> HEAD -- <file>`; if genuinely wrong, fix manually and amend                          |
| `CONFLICT (modify/delete)`                                                                                                      | One branch edited a file, the other deleted it                                               | Decide whether the file should still exist; `git add` (keep, possibly edited) or `git rm` (confirm deletion) to resolve |
| Merge produced no conflicts but the result is semantically broken (both sides changed related-but-different lines)              | Line-level three-way merge has no understanding of program semantics                         | No shortcut — this is why code review and tests exist after any non-trivial merge                                       |

## 14. Interview Questions

**[Beginner] Q1. What's the difference between a fast-forward merge and a three-way merge?**
**Model answer:** A fast-forward happens when the branch being merged in is a direct descendant of the current branch's tip — nothing diverged, so Git just moves the current branch's pointer forward with no new commit. A three-way merge happens when both branches have unique commits since they diverged; Git compares the common ancestor (the merge base) against both tips, automatically combines non-overlapping changes, and creates a new merge commit with two parents recording the union.

**[Intermediate] Q2. What is a merge base, and how does Git find it?**
**Model answer:** The merge base is the nearest common ancestor commit of the two branches being merged — the point where their histories last agreed before diverging. Git finds it by walking the commit graph backward from both tips following parent pointers until it finds the closest commit reachable from both. `git merge-base <branch1> <branch2>` exposes this directly, and it's the third tree Git compares against in a three-way merge, alongside each branch's current tip.

**[Intermediate] Q3. Explain the difference between `git merge -s ours` and `git merge -X ours`.**
**Model answer:** `-s ours` selects the `ours` merge _strategy_ entirely, which records a merge commit with the correct two-parent ancestry but discards all of the other branch's content changes outright — the resulting tree is identical to what you had before, even for files that never conflicted. `-X ours` runs the normal `ort`/`recursive` strategy and performs a real merge, incorporating all non-conflicting changes from both sides as usual; the `ours` _option_ only kicks in to auto-resolve the specific hunks that genuinely conflict, preferring the current branch's version there. Confusing the two is a real, damaging mistake — `-s ours` can silently erase an entire branch's work while the log claims it was merged.

**[Senior] Q4. A teammate says `--squash` and `--no-ff` are opposites. Are they, and why does that framing help or mislead?**
**Model answer:** It's a useful mnemonic more than a precise technical statement. `--no-ff` forces a merge commit to exist and explicitly preserves full ancestry — both parent links, both branches' individual commit histories all remain intact and walkable. `--squash` does the opposite on the ancestry axis: it deliberately produces no merge commit and no parent link to the source branch at all, collapsing everything into one ordinary commit as if you'd typed the whole diff yourself. Where the framing is useful: both are explicit overrides of the _default_ merge behavior (which fast-forwards when possible and otherwise creates a two-parent merge commit preserving ancestry) pulling in opposite directions — more history-preserving on one side, more history-discarding on the other. Where it misleads: they're not mutually exclusive toggles of the same setting; you choose one merge mode per operation, not a spectrum between them, and `--squash` doesn't even create a merge commit for `--no-ff` to be "more" or "less" of.

**[Senior] Q5. Your team wants `main`'s history to read as one clean commit per feature, but individual contributors still want granular WIP commits on their own branches. What merge policy achieves both?**
**Model answer:** Squash merging feature branches into `main` on the hosting platform's PR flow achieves exactly this: contributors commit as often and messily as they like on their feature branch — that granular history is genuinely useful during review and for the author's own iteration — but the squash merge collapses the entire branch into a single, clean commit on `main` at merge time, with a commit message the team can standardize (often tied to Conventional Commits, §18, for changelog generation). The trade-off to flag explicitly: the feature branch's individual commit history is not preserved on `main` after this — if someone later needs `git blame` or `git bisect` (§19) granularity within that feature, it's gone from `main`'s perspective, though still recoverable from the original feature branch or PR if it hasn't been deleted. Teams that value that granular history long-term instead favor `--no-ff` merges or a rebase-then-merge policy (§14) that keeps individual commits but with a clean, linear, force-pushed-and-rebased history.

## 15. Common Misconceptions

1. **"Merging always creates a merge commit."** Only when a fast-forward isn't possible, or `--no-ff` is explicitly passed. The default behavior actively prefers fast-forwarding whenever ancestry allows it.
2. **"A conflict means Git failed."** A conflict means Git correctly identified that it _cannot_ safely guess your intent on an overlapping change and is deferring to a human — this is Git behaving exactly as designed, not an error state.
3. **"`-s ours` and `-X ours` are basically the same flag with different syntax."** They operate at entirely different levels — one discards an entire branch's content while claiming to merge it; the other performs a genuine merge and only overrides the specific conflicting hunks. See 13.6.
4. **"`--squash` is a kind of merge commit, just condensed."** It produces no merge commit and no parent link at all — it's closer to "compute a diff and apply it as a normal commit" than to any variety of merge.
5. **"Once conflict markers appear, my file content or history is at risk."** Nothing is lost — both full versions are still fully present (in the index at conflict stages 1/2/3, and in each branch's own history); the markers are just an editing aid, and `git merge --abort` cleanly returns to the pre-merge state at any point before you commit.

## 16. 🔑 Key Takeaways

- Fast-forward is a pointer move with no new commit, chosen automatically whenever the current branch hasn't diverged from the branch being merged; `--no-ff` forces a real merge commit anyway.
- A three-way merge compares the merge base against both tips, auto-resolving non-overlapping changes and flagging only genuinely overlapping edits as conflicts.
- Merge **strategies** (`-s`) select the algorithm; strategy **options** (`-X`) tune that algorithm's behavior on conflicts — `-s ours` discards a branch's content entirely, `-X ours` performs a real merge and only prefers "ours" on actual conflicts.
- Conflict markers (`<<<<<<<`/`=======`/`>>>>>>>`) mark the "ours" and "theirs" sides; resolving means editing out the markers to the intended final content and `git add`-ing the file before committing.
- `git merge --abort` cleanly cancels an in-progress, unresolved merge; `--squash` deliberately discards ancestry to produce one clean commit instead of a merge commit.

## 17. Related Concepts & What's Next

Merging is one of two ways to reconcile diverged history — §14 covers the other: rebasing, which rewrites commits onto a new base instead of joining two tips with a merge commit, trading a preserved-but-branchy history for a rewritten-but-linear one. The trade-offs between the two, and the hard rule about when rebasing is unsafe, are §14's core subject.
