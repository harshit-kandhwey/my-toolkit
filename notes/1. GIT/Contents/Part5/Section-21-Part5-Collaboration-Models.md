# Section 21 (Part 5): Collaboration Models — Shared Repository vs Fork & Pull Request; Code Review Workflow

## 1. Definition

**Plain language:** A collaboration model is the agreed shape of how a team's contributors get their changes from a personal branch into the project's shared history — who can push where, and what has to happen (review, checks, approval) before that's allowed.

**Precise:** Git itself is agnostic about collaboration structure — §20 gave you `fetch`/`pull`/`push` and nothing more. Everything in this section is a **social and platform-level convention** layered on top of those primitives: which remotes exist, who has write access to which repository, and what gate (a pull/merge request plus review) sits between a contributor's branch and the shared history. The two dominant conventions are the **shared repository model** and the **fork-and-pull-request model**.

## 2. Why It Exists / Problem It Solves

§20's commands let anyone with write access push directly to any branch, including `main`, with zero review. That's fine for a single developer or a tiny trusted team, and actively dangerous at any larger scale: broken code lands in the shared line of truth, nobody sees the change before it ships, and there's no recorded conversation about _why_ a change was made beyond the commit message. Collaboration models exist to insert a deliberate checkpoint — the **pull request** (GitHub/Bitbucket terminology) or **merge request** (GitLab terminology) — between "I wrote this" and "this is part of the project," giving the team a place to review, discuss, run automated checks (§25), and require explicit approval before history changes.

## 3. Shared Repository Model

Every contributor has push access to one single repository. Nobody forks; everyone clones the same remote and works on branches within it.

```
                    ┌───────────────────────────┐
                    │  ONE shared repository    │
                    │  (origin) — everyone has  │
                    │  write access             │
                    └──────────────┬────────────┘
                push/pull to branches (not main)
       ┌───────────────────────────┼───────────────────────────┐
       ▼                           ▼                           ▼
┌─────────────┐            ┌─────────────┐            ┌─────────────┐
│ Developer A │            │ Developer B │            │ Developer C │
│ clone       │            │ clone       │            │ clone       │
│ feature/a   │            │ feature/b   │            │ hotfix/c    │
└─────────────┘            └─────────────┘            └─────────────┘
```

- **Who uses it:** internal teams inside a company or organization, where every contributor is a known, trusted employee/team member with legitimate reason to have write access.
- **Mechanics:** each contributor pushes a feature branch directly to `origin`, opens a pull request from `feature/a` into `main` _within the same repository_, gets it reviewed, and merges. There is no second repository involved at any point.
- **Access control:** enforced through branch protection rules (§23) on the shared repo — contributors can push to their own branches freely, but `main` (and other protected branches) requires a PR with approval, not raw push access.

## 4. Fork-and-Pull-Request Model

Contributors do **not** have write access to the canonical (**upstream**) repository. Each contributor **forks** it — the hosting platform creates a full server-side copy under the contributor's own account — pushes freely to their fork, and opens a pull request asking the upstream maintainers to pull specific commits from the fork into upstream.

```
                 ┌───────────────────────────────┐
                 │  UPSTREAM repository          │
                 │  (canonical project)          │
                 │contributor has NO write access│
                 └───────────────┬───────────────┘
                    fork (server-side copy)
                                 │
                                 ▼
                 ┌───────────────────────────────┐
                 │   Contributor's FORK          │
                 │   full write access           │
                 └───────────────┬───────────────┘
                    clone to local machine
                                 │
                                 ▼
                 ┌───────────────────────────────┐
                 │ Local clone                   │
                 │ origin  → contributor's fork  │
                 │ upstream → canonical project  │
                 └───────────────────────────────┘

  Pull request flow: contributor pushes to origin (their fork),
  then opens a PR from fork:feature-branch → upstream:main.
  Maintainers review and merge; the contributor never pushes
  directly to upstream at any point.
```

- **Who uses it:** open-source projects with an unbounded, untrusted-by-default pool of external contributors — nobody wants to hand out write access to anyone who opens a first PR. Also common inside large enterprises for particularly sensitive repositories, or where a subset of contractors/partners should be able to propose changes without gaining direct write access.
- **Mechanics:** contributor forks, clones their fork locally, adds the canonical repo as a second remote (conventionally named `upstream`), works on a branch, pushes to their own fork (`origin`), and opens a PR targeting `upstream`'s default branch.
- **Access control:** trivially strict — write access to upstream simply isn't granted to external contributors at all; the PR is the _only_ channel by which their code can ever reach upstream, and a maintainer must explicitly merge it.

### 4.1 Comparison

| Dimension                       | Shared Repository Model                                       | Fork-and-Pull-Request Model                        |
| ------------------------------- | ------------------------------------------------------------- | -------------------------------------------------- |
| Write access to canonical repo  | All contributors                                              | Maintainers only                                   |
| Number of repositories involved | One                                                           | Two (fork + upstream) per contributor              |
| Typical audience                | Internal team, known employees                                | Open-source, external/untrusted contributors       |
| Branch namespace                | Shared — needs naming discipline (§12.10) to avoid collisions | Isolated per fork — no collision risk              |
| Setup overhead per contributor  | Low (just clone)                                              | Slightly higher (fork, clone, add upstream remote) |
| Typical PR direction            | branch → main, same repo                                      | fork:branch → upstream:main                        |

## 5. The Full Pull Request Lifecycle

Both models converge on essentially the same review workflow once a PR is open; the difference is only which repository the branch physically lives in.

1. **Branch.** Create a feature/fix branch off the latest `main` (§12.7): `git switch -c feature-payments`.
2. **Commit.** Make a series of focused commits (§10, tag/commit conventions in §18) as work progresses.
3. **Push.** `git push -u origin feature-payments` (shared model) or to your fork (fork model, §21.4).
4. **Open the PR.** On the hosting platform, open a pull request targeting the appropriate base branch, with a description of what changed and why. Many teams use a PR template requiring a summary, testing notes, and linked issue.
5. **Automated checks run.** CI (§25) runs tests, linters, and build steps automatically against the PR; most teams block merge until these pass.
6. **Review.** One or more reviewers read the diff, leave inline comments, request changes, or approve. This is where most of the _value_ of the model lives — a second set of eyes catches bugs, design issues, and knowledge silos before they become permanent.
7. **Address feedback.** The contributor pushes more commits addressing comments. Two common styles:
   - **New commits on top** (`git commit -m "Address review: validate input"`), preserving the exact sequence of what happened during review — easy to see what changed in response to which comment, but a noisier final history.
   - **Amend/fixup and force-push** (`git commit --amend` or `git commit --fixup=<hash>` + `git rebase -i --autosquash`, full mechanics §14 and §15) to keep the branch's history clean, then `git push --force-with-lease` to update the PR. Force-pushing to _your own_ PR branch is normal and expected here — §20.6.2's caution about force-push applies to shared integration branches, not to a personal feature branch only you and the PR's CI are working from.
8. **Approval.** Once required reviewers approve and required checks pass, the platform allows merging (often enforced by protected-branch rules, §23).
9. **Merge.** A maintainer (or the author, if permitted) merges using one of three strategies (21.6).

> 💡 **Tip:** Re-requesting review after pushing fixes, rather than assuming a reviewer will notice new commits, is basic PR hygiene that keeps review cycles fast on busy teams.

## 6. Merge Strategies at PR-Merge Time

| Strategy             | What happens                                                                                                   | History shape                                                                     | Trade-off                                                                                                                                              |
| -------------------- | -------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Merge commit**     | All of the branch's commits are added as-is, plus one new merge commit joining them to the base                | Preserves the branch's exact commit-by-commit history, plus a visible merge point | Most information preserved; can clutter history with many small "wip" commits and review-fixup commits unless the branch was cleaned first             |
| **Squash and merge** | All of the branch's commits are collapsed into a single new commit on the base branch                          | One clean commit per PR, linear history                                           | Loses individual commit granularity (useful review-iteration history disappears); simplest `git log` and easiest to revert a whole feature in one step |
| **Rebase and merge** | Each of the branch's commits is individually replayed onto the tip of the base branch, no merge commit created | Fully linear history, but with every original commit preserved                    | Keeps granular history _and_ linearity; rewrites commit hashes, so anyone else who'd pulled the original branch needs to reconcile (§14)               |

There's no universally correct choice — it's a team convention, and most hosting platforms let you configure which strategies are even offered.

- Teams that value a clean, one-commit-per-feature `main` and don't care about in-branch commit granularity: **squash and merge**.
- Teams doing careful, atomic commit discipline where each commit is independently meaningful and should survive into `main` as such: **rebase and merge**.
- Teams that want the review-and-fixup history itself preserved as a record, or that merge long-lived branches with genuine parallel structure: **merge commit**.

> ⚠️ **Critical clarification / Common confusion to preempt:** "Squash and merge" operates only on the PR's branch commits at merge time — it is a platform-level convenience equivalent to `git merge --squash`, not the same operation as an interactive rebase you'd run yourself beforehand (§14). Both compress multiple commits into one, but squash-merge does it automatically as part of the merge button and never touches your local branch's actual commits.

## 7. Code Review Practices

- **Small, focused PRs.** A PR that changes one thing is reviewable in minutes; a PR touching forty files across three concerns gets rubber-stamped out of reviewer fatigue, defeating the point of review.
- **Descriptive PR title and body.** State _what_ changed and _why_, link the relevant issue/ticket, and note anything a reviewer should specifically scrutinize (e.g., "changed the retry backoff — please check the timing math").
- **Draft PRs.** Most platforms support opening a PR in a "draft" state — visible, CI-checkable, but explicitly not ready for review or merge. Useful for early feedback on direction, or to keep a WIP branch's CI status visible without inviting a full review pass yet.
- **Required reviewers / CODEOWNERS.** Platforms can mandate that specific people or teams review changes to specific paths automatically — full syntax and mechanics in §23.
- **Respond to every comment**, even just to say "done" or explain why you disagree — an unanswered review comment is a stalled PR.
- **Don't take review personally; don't review personally.** Comment on the code, not the person; a good review culture treats feedback as protecting the codebase, not judging the author.

## 8. Keeping a Fork in Sync with Upstream

A fork does not automatically stay current with the canonical repository — it's a snapshot at fork time plus whatever you've pushed to it since. Left alone, it drifts, and PRs opened from a stale fork accumulate unrelated merge conflicts.

```bash
# One-time setup: add the canonical repo as a second remote
$ git remote add upstream https://github.com/original-org/webapp.git
$ git remote -v
origin    https://github.com/your-username/webapp.git (fetch)
origin    https://github.com/your-username/webapp.git (push)
upstream  https://github.com/original-org/webapp.git (fetch)
upstream  https://github.com/original-org/webapp.git (push)

# Fetch upstream's latest history (downloads only — §20.4)
$ git fetch upstream

# Update your local main to match upstream's main
$ git switch main
$ git merge upstream/main
# or, for a linear history:
$ git rebase upstream/main

# Push the now-updated main to your own fork so it's visible there too
$ git push origin main
```

Doing this before starting new work (or periodically on a long-lived branch) keeps your PRs mergeable with minimal conflicts, and is standard practice on any active open-source project.

## 9. Hands-On Walkthrough — Fork Model End to End

```bash
# 1. Fork upstream/webapp on the hosting platform (web UI action, not a git command)

# 2. Clone YOUR fork
$ git clone git@github.com:your-username/webapp.git
$ cd webapp

# 3. Add the canonical repo as 'upstream'
$ git remote add upstream https://github.com/original-org/webapp.git

# 4. Branch, work, commit
$ git switch -c fix-null-check
$ git commit -am "Fix null check in payment validator"

# 5. Push to YOUR fork (origin), not upstream
$ git push -u origin fix-null-check

# 6. Open a PR on the platform: your-username:fix-null-check -> original-org:main

# 7. Address review feedback, then re-push
$ git commit --amend --no-edit
$ git push --force-with-lease

# 8. Maintainer merges; you sync your fork's main afterward (21.8)
```

## 10. Interview Questions

**[Beginner] Q1. What's the core difference between the shared repository model and the fork-and-pull-request model?**
**Model answer:** In the shared repository model, every contributor has direct write access to one repository and pushes branches into it, opening PRs within that same repo. In the fork model, contributors don't have write access to the canonical repository at all — they create their own server-side copy (a fork), push their work there, and open a PR asking maintainers to pull specific commits from the fork into the canonical repo. The shared model suits trusted internal teams; the fork model suits open-source or any situation where you want to accept contributions without granting write access.

**[Beginner] Q2. What are the three common ways to merge a pull request, and how do they differ?**
**Model answer:** A regular merge commit keeps every commit from the branch plus adds one new commit joining it to the base, preserving full history including a visible merge point. Squash and merge collapses all the branch's commits into a single new commit on the base, producing the cleanest possible linear history but losing individual commit granularity. Rebase and merge replays each of the branch's commits individually onto the tip of the base with no merge commit, giving a linear history while keeping every original commit intact, at the cost of rewriting commit hashes.

**[Intermediate] Q3. Why is it normal to force-push to your own pull request branch, when force-pushing is usually discouraged?**
**Model answer:** The caution against force-push is about branches other people are actively building work on top of — rewriting shared history invalidates their local state. A PR branch that only you (and CI) are working from doesn't have that problem: after amending a commit or squashing review-fixup commits with an interactive rebase, force-pushing (ideally with `--force-with-lease`) simply updates the PR to reflect your cleaned-up history, and reviewers just see the PR's diff refresh. It only becomes dangerous if someone else has also pushed to that exact branch in the meantime, which `--force-with-lease` specifically guards against.

**[Intermediate] Q4. Why doesn't a fork automatically stay up to date with the repository it was forked from?**
**Model answer:** A fork is a one-time server-side copy made at the moment you fork; after that, it's an entirely independent repository as far as synchronization is concerned; the hosting platform doesn't push upstream's new commits into your fork for you. You have to explicitly add the canonical repo as a second remote (conventionally `upstream`), fetch from it, and merge or rebase your fork's branches onto its latest state — otherwise your fork, and any PRs based on it, silently drift further out of date and accumulate avoidable merge conflicts.

**[Senior] Q5. A team wants a clean, linear `main` for readability, but also wants to preserve individual commit history for detailed blame/bisect work. Which merge strategy fits, and what's the cost?**
**Model answer:** Rebase and merge is the fit — it replays each of the PR's commits individually onto the tip of the base branch with no merge commit, so `main` stays fully linear while every original commit (and its message, author, and content) survives intact, which keeps `git blame` and `git bisect` (§19) precise down to the individual change rather than one large squashed blob. The cost is that rebasing rewrites commit hashes, so if the same branch had been pulled or built upon anywhere else before the merge, those copies now diverge from the merged history and need reconciling — this is why rebase-and-merge works best when PR branches are genuinely personal and short-lived, which pairs naturally with a trunk-based or GitHub-Flow-style workflow (§22).

## 11. Common Misconceptions

1. **"Forking and cloning are the same thing."** Cloning copies a repository to your local machine; forking creates a new, independent _server-side_ copy under your own account on the hosting platform. A typical fork-model workflow does both: fork on the platform, then clone your fork locally.
2. **"Squash and merge is the same as running an interactive rebase yourself."** It achieves a similar visual result (fewer commits) but is a distinct, platform-triggered operation at merge time; it doesn't touch your local branch's actual commit history the way `git rebase -i` does.
3. **"You need write access to contribute to any project on GitHub."** The fork-and-pull-request model exists specifically so external contributors can propose changes without ever being granted write access to the canonical repository.
4. **"Force-pushing to a PR branch is always risky."** It's risky on branches other people also push to; on a personal PR branch it's routine practice for keeping history clean, especially combined with `--force-with-lease`.
5. **"A merged PR's source branch and history live forever exactly as pushed."** Depending on the chosen merge strategy, the branch's individual commits may be squashed into one or rewritten via rebase — what lands on the base branch is not always a byte-for-byte preservation of what was pushed.

## 12. 🔑 Key Takeaways

- Collaboration models are conventions built on top of §20's primitives, not new Git mechanics — Git itself doesn't know what a "pull request" is; that lives entirely at the hosting-platform layer.
- Shared repository model: everyone has write access to one repo. Fork model: contributors work in their own server-side copy and propose changes via PR into an upstream they can't write to directly.
- The PR lifecycle is branch → commit → push → open PR → automated checks → review → address feedback (new commits or amend+force-push) → approval → merge.
- Three merge strategies — merge commit, squash and merge, rebase and merge — trade off history granularity against linearity; there's no universally right answer, only team convention.
- Keeping a fork current requires an explicit `upstream` remote and periodic fetch+merge/rebase; it does not happen automatically.

## 13. Related Concepts & What's Next

This section assumed §20's remote vocabulary and layered the human workflow — forks, PRs, review, merge strategy — on top of it. §22 zooms out further, to the branching _strategies_ (Git Flow, GitHub Flow, GitLab Flow, trunk-based development) that determine which branches exist in the first place and how long they live before the PR process covered here brings them back together.
