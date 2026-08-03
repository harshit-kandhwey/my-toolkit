# Section 12 (Part 4): Branching in Depth

## 1. Definition

**Plain language:** A branch is an independent, named line of development that lets you work on something — a feature, a fix, an experiment — without disturbing anyone else's work or the stable line you branched from.

**Precise:** Mechanically, a Git branch is nothing more than a movable ref: a small file under `.git/refs/heads/` holding a single commit hash, which advances automatically each time you commit while that branch is checked out. Everything in this section is about the _commands_ that create, inspect, switch between, and remove those pointers — the underlying mechanics were already established in §6.

## 2. Recap — Why Branches Are "Free" (Brief; See §6 for the Full Mechanics)

§6 already proved the core fact this whole section leans on: creating a branch writes one small file containing a hash — no file copying, no history duplication, no dependency on repository size. That's _why_ Git culture treats branches as disposable, cheap, and constantly created, in sharp contrast to centralized systems (§1) where branching was a heavyweight, discouraged event. This section doesn't re-derive that; it builds the full command vocabulary on top of it.

> 💡 **Tip:** If any of "ref", "movable pointer", or "HEAD resolves through the branch" feels shaky, re-read §6 before continuing — this section assumes that mental model as settled.

## 3. `git branch` — Listing, Creating, Deleting

`git branch` is the general-purpose branch-management command. Run with no arguments, it lists local branches; given a name, it creates a new branch ref at the current commit **without switching to it**.

```bash
# List local branches (current branch marked with *)
$ git branch
* main
  feature-login

# Create a new branch pointing at HEAD's current commit — does NOT switch to it
$ git branch feature-payments
$ git branch
* main
  feature-login
  feature-payments
```

Key listing flags:

| Flag                     | Effect                                                                     |
| ------------------------ | -------------------------------------------------------------------------- |
| _(none)_                 | List local branches only                                                   |
| `-a`                     | List local **and** remote-tracking branches (the local/remote-tracking/remote distinction below) |
| `-r`                     | List remote-tracking branches only                                         |
| `-v`                     | Show each branch's latest commit hash + subject line                       |
| `-vv`                    | Also show the upstream (tracked) branch and ahead/behind counts            |
| `--merged [<commit>]`    | List branches already merged into the given commit (default HEAD) — see the merged/unmerged listing section below |
| `--no-merged [<commit>]` | List branches **not** merged into the given commit — see the merged/unmerged listing section below                |

```bash
$ git branch -vv
* main             a3f8e21 [origin/main] Fix pagination bug
  feature-payments a3f8e21 Add payments skeleton
```

> ⚠️ **Common confusion to preempt:** `git branch <name>` creates a branch but leaves you checked out on whatever you were already on. Beginners routinely run this expecting to now be "on" the new branch, then are confused why their commits land on the old one. Use `git switch -c <name>` (see the create-and-switch section below) when you want create-and-switch in one step.

## 4. Deleting Branches: `-d` vs `-D`

```bash
# Safe delete — refuses if the branch has commits not reachable from
# its upstream or the current branch
$ git branch -d feature-payments
error: The branch 'feature-payments' is not fully merged.
If you are sure you want to delete it, run 'git branch -D feature-payments'.

# Force delete — deletes regardless of merge status
$ git branch -D feature-payments
Deleted branch feature-payments (was 7c2a9f1).
```

- **`-d`** (safe delete) checks whether the branch's commits are reachable from another ref (typically its upstream or the branch you're currently on). If not, Git refuses — this is exactly the protection described in §6's `git branch` documentation, preventing you from silently discarding unmerged work.
- **`-D`** is shorthand for `--delete --force`: it deletes unconditionally. The branch _ref_ disappears immediately, but the commit objects it pointed at are untouched in `.git/objects` and remain recoverable through the reflog (§6's reflog coverage) until garbage collection — deleting a branch is not the same operation as deleting its commits.
- Deleting a **remote-tracking** branch (`git branch -d -r origin/old-feature`) only removes your local bookkeeping copy; it does not touch anything on the remote server. Deleting the actual branch on the remote is a separate operation (`git push origin --delete <branch>`, §20).

> 💡 **Tip:** After a feature branch is merged via pull request and the remote branch is deleted by the hosting platform, `git fetch --prune` (§20) cleans up your now-stale local remote-tracking refs, and `git branch -d` then cleanly removes your local branch since it's provably merged.

## 5. Renaming Branches: `-m`

```bash
# Rename the current branch
$ git branch -m new-name

# Rename a specific (possibly non-current) branch
$ git branch -m old-name new-name

# Force-rename, overwriting an existing branch of that name
$ git branch -M old-name new-name
```

Renaming a branch is, unsurprisingly, just renaming its ref file and updating HEAD if it was the checked-out branch — no commits are touched, no hashes change. The most common real-world use is the historical `master` → `main` rename that most repositories performed industry-wide: `git branch -m master main`, followed by pushing the new name and updating the remote's default branch (§20, §23).

## 6. `git switch` vs `git checkout` — The Modern Split

Before Git 2.23 (2019), `git checkout` did two unrelated jobs: switching branches _and_ restoring individual files from the index or a commit. Overloading one command with two unrelated meanings was a genuine, long-standing usability problem — `git checkout <branch>` and `git checkout -- <file>` look similar but do entirely different things, and a stray or missing `--` could switch a branch when you meant to discard a file's edits, or vice versa.

Git 2.23 split the responsibilities into two new, single-purpose commands:

| Old (still works)        | New (recommended)              | Job                                               |
| ------------------------ | ------------------------------ | ------------------------------------------------- |
| `git checkout <branch>`  | `git switch <branch>`          | Change which branch HEAD points to                |
| `git checkout -- <file>` | `git restore <file>`           | Discard working-directory changes to a file (§15) |
| `git checkout <commit>`  | `git switch --detach <commit>` | Enter detached HEAD (§6's detached HEAD coverage) |
| `git checkout -b <name>` | `git switch -c <name>`         | Create a branch and switch to it                  |

`git checkout` was **not** deprecated or removed — it still does everything it always did, and you will see it constantly in existing tutorials, CI scripts, Stack Overflow answers, and muscle memory predating 2019. `switch` and `restore` are narrower, safer, and harder to misuse by accident, which is why they're the recommended default for new work and new scripts, while recognizing `checkout` remains essential reading-comprehension for any real codebase.

```bash
$ git switch feature-login
Switched to branch 'feature-login'

$ git switch main
Switched to branch 'main'
```

> ⚠️ **Critical clarification:** `git switch` refuses to switch if doing so would silently overwrite uncommitted changes that conflict with the target branch's version of a file — the same protection `checkout` always had. It does not bypass Git's core safety guarantees; it only narrows what one command is responsible for.

## 7. Creating and Switching in One Step

```bash
# Modern
$ git switch -c feature-payments
Switched to a new branch 'feature-payments'

# Equivalent, legacy
$ git checkout -b feature-payments
Switched to a new branch 'feature-payments'

# Both accept a starting point other than HEAD
$ git switch -c hotfix-1 v2.3.0
$ git checkout -b hotfix-1 v2.3.0
```

Both forms are exactly `git branch <name> [<start-point>]` followed immediately by switching to it — no new mechanic, just a convenience combining the branch-creation and switch operations described earlier in this section into one command.

## 8. Tracking a Remote Branch on Creation: `--track`

When you create a local branch intended to follow a specific remote branch — pushing to it and pulling from it by default without specifying the remote each time — you set up an **upstream tracking relationship**.

```bash
# Explicit tracking
$ git switch -c feature-x --track origin/feature-x

# Shorthand: if a remote-tracking branch named EXACTLY 'feature-x' exists
# and no local branch of that name does, Git DWIMs ("Do What I Mean") and
# creates a local tracking branch automatically
$ git switch feature-x
Branch 'feature-x' set up to track remote branch 'feature-x' from 'origin'.
Switched to a new branch 'feature-x'
```

Once tracking is set up, `git status` reports ahead/behind counts against the upstream, and plain `git push` / `git pull` (no arguments) know where to send and fetch from. You can inspect or change tracking with:

```bash
$ git branch -vv                       # shows [origin/feature-x] per branch
$ git branch --set-upstream-to=origin/feature-x feature-x
$ git branch --unset-upstream feature-x
```

Full push/pull/fetch mechanics and the remote side of tracking are §20's subject; this section covers only the branch-creation-time hook into it.

## 9. Local vs Remote-Tracking vs Remote Branches — The Three-Way Distinction

This is one of the most consistently confused areas for people coming from centralized systems, so it's worth stating precisely — it was previewed in §6's tip on tracking branches and is fully earned here.

```
                         (only exists on the SERVER)
                         ┌──────────────────────┐
                         │  origin's "main"     │   ← a REMOTE branch:
                         │  refs/heads/main     │     someone else's local branch,
                         │  lives on the remote │     as far as your clone is concerned
                         └──────────┬───────────┘
                                    │ git fetch
                                    ▼
   ┌──────────────────────────────────────────────────────────────┐
   │  YOUR CLONE                                                  │
   │                                                              │
   │  refs/remotes/origin/main   ← REMOTE-TRACKING branch:        │
   │  a3f8e21                       your read-only local bookmark │
   │                                 of where origin's main was   │
   │                                 as of your LAST fetch        │
   │                                                              │
   │  refs/heads/main            ← LOCAL branch:                  |
   │  7e4f9a2                       your own, freely committable, │
   │                                 possibly ahead of/behind     │
   │                                 origin/main right now        │
   └──────────────────────────────────────────────────────────────┘
```

| Kind                       | Physical location                                 | Who moves it                              | Can you commit onto it directly?                                               |
| -------------------------- | ------------------------------------------------- | ----------------------------------------- | ------------------------------------------------------------------------------ |
| **Local branch**           | `.git/refs/heads/<name>` in your clone            | You, via `git commit`                     | Yes                                                                            |
| **Remote-tracking branch** | `.git/refs/remotes/<remote>/<name>` in your clone | Git, automatically, during `fetch`/`pull` | No — it's read-only bookkeeping                                                |
| **Remote branch**          | `refs/heads/<name>` on the _remote server itself_ | Whoever pushes to that remote             | N/A — you don't have it locally; you only see it via your remote-tracking copy |

The everyday consequence: `origin/main` in your local clone can silently drift out of date with the _actual_ `main` on the server the moment a teammate pushes — you only find out, and only update your remote-tracking copy, on your next `git fetch` or `git pull`. This is the single biggest source of "but I thought I had the latest code" confusion, and it's a direct, mechanical consequence of what a remote-tracking branch actually is.

> 🔑 **Interview-grade summary:** a local branch is yours and writable; a remote-tracking branch is a local, read-only snapshot of someone else's branch as of your last sync; a remote branch is the real thing living on the server, which you never touch directly — only through push/fetch.

## 10. Branch Naming Conventions

Git itself enforces almost nothing about branch names beyond a small set of forbidden characters and sequences (no spaces, no `..`, no leading `-`, no trailing `.lock`, among others — `git check-ref-format` is the authoritative validator). Naming _conventions_ are entirely a team/tooling choice, but a few patterns are near-universal in industry and worth knowing by name, since branching-strategy discipline (§22) builds directly on them:

| Convention                      | Example                     | Typical meaning                                           |
| ------------------------------- | --------------------------- | --------------------------------------------------------- |
| `feature/<name>`                | `feature/checkout-redesign` | New functionality in progress                             |
| `bugfix/<name>` or `fix/<name>` | `fix/null-pointer-cart`     | A non-urgent bug fix                                      |
| `hotfix/<name>`                 | `hotfix/payment-outage`     | Urgent fix, often branched from a release/production line |
| `release/<version>`             | `release/2.4.0`             | Stabilization branch preparing a release                  |
| `chore/<name>`                  | `chore/upgrade-deps`        | Non-feature maintenance work                              |
| `<ticket-id>-<slug>`            | `JIRA-4821-add-2fa`         | Traceability back to an issue tracker                     |

Slashes in branch names are not merely cosmetic: Git branch names live in the same namespace as directory paths under `refs/heads/`, so `feature/login` is physically the file `refs/heads/feature/login`. This has one real consequence — you cannot simultaneously have a branch named `feature` and a branch named `feature/login`, because one would require `feature` to be both a file and a directory on disk.

## 11. Listing Merged / Unmerged Branches: `--merged` / `--no-merged`

Before deleting branches in bulk, or auditing what's safe to clean up, `--merged` and `--no-merged` tell you which local branches are (or aren't) fully incorporated into a given commit — almost always used against the current branch or a release branch.

```bash
# Branches already merged into the current branch — safe to delete
$ git branch --merged
  feature-login
  feature-payments
* main

# Branches with commits NOT yet merged into the current branch — deleting
# these with -d will be refused; -D would discard real, unmerged work
$ git branch --no-merged
  experimental-refactor
```

```bash
# A common cleanup one-liner: delete every local branch already merged
# into main, excluding main itself
$ git branch --merged main | grep -v '^\*\|main' | xargs -r git branch -d
```

This is precisely the mechanism `git branch -d`'s safety check (the deleting-branches section above) relies on internally — `--merged`/`--no-merged` just exposes that same reachability check as a queryable listing.

## 12. Orphan Branches: `--orphan`

An orphan branch starts with **no parent commit at all** — its first commit will have zero parents, meaning it shares no history with any other branch in the repository, even though it lives in the same repo and object database.

```bash
$ git switch --orphan gh-pages
$ git status
On branch gh-pages
No commits yet
...
```

Immediately after creating an orphan branch, the working directory and index still contain whatever files were checked out on the _previous_ branch — Git does not clear them for you. The typical follow-up is to remove everything and start clean before the first commit:

```bash
$ git rm -rf .
$ echo "<html>...</html>" > index.html
$ git add index.html
$ git commit -m "Initial commit for gh-pages"
```

**Legitimate uses:** publishing generated static site content (the classic `gh-pages` branch pattern predating dedicated hosting features) or maintaining a genuinely unrelated document set (e.g., project documentation with its own independent history) inside the same physical repository without polluting the main line's commit graph with unrelated content or forcing a merge base to exist where none logically should.

## 13. Hands-On Walkthrough — Full Branch Lifecycle

```bash
$ git switch -c feature-search
Switched to a new branch 'feature-search'

$ echo "search module" > search.js
$ git add search.js && git commit -m "Add search module skeleton"
[feature-search 9f2c1a4] Add search module skeleton

$ git switch main
Switched to branch 'main'

$ git branch --no-merged
  feature-search

$ git merge feature-search           # full merge mechanics: §13
Updating a3f8e21..9f2c1a4
Fast-forward
 search.js | 1 +

$ git branch --merged
  feature-search
* main

$ git branch -d feature-search
Deleted branch feature-search (was 9f2c1a4).
```

## 14. Interview Questions

**[Beginner] Q1. What actually happens when you run `git branch new-feature`?**
**Model answer:** Git creates a new file at `.git/refs/heads/new-feature` containing the same commit hash that HEAD currently resolves to. No files are copied, no history is duplicated, and — importantly — you are _not_ switched onto the new branch; you remain on whichever branch you were previously on. To create and switch in one step you'd use `git switch -c new-feature` instead.

**[Intermediate] Q2. What's the difference between `git branch -d` and `git branch -D`, and why does the distinction matter?**
**Model answer:** `-d` is a safe delete: Git checks whether the branch's commits are reachable from another ref, typically its upstream or your current branch, and refuses to delete if they aren't, protecting you from silently discarding unmerged work. `-D` forces deletion regardless of merge status. The ref disappears either way, but the underlying commit objects are never immediately destroyed — they stay in the object database and are recoverable via the reflog until garbage collection actually runs, so `-D` is risky but not instantly catastrophic if caught quickly.

**[Intermediate] Q3. What's the practical difference between a local branch and a remote-tracking branch like `origin/main`?**
**Model answer:** A local branch, like `main`, lives at `refs/heads/main`, is yours to commit onto directly, and moves whenever you commit. A remote-tracking branch, like `origin/main` at `refs/remotes/origin/main`, is a read-only local bookmark recording where `origin`'s actual `main` was as of your last `fetch` or `pull` — you never commit directly onto it, and Git updates it automatically only during network operations. This means `origin/main` in your clone can be stale relative to the real branch on the server at any given moment; it only refreshes on your next fetch.

**[Senior] Q4. Why was `git switch` introduced when `git checkout` already did the job?**
**Model answer:** `git checkout` historically had two unrelated responsibilities: switching which branch HEAD points to, and restoring individual files from the index or a historical commit — two very different operations sharing one command name and a subtly different flag syntax (`git checkout <branch>` versus `git checkout -- <file>`). That overload was a real source of mistakes, especially when a missing `--` could make Git interpret an intended file-restore as a branch switch, or vice versa. Git 2.23 split the responsibilities into `git switch` (branch/HEAD movement only) and `git restore` (file content restoration only, §15), each with a narrower and less error-prone surface. `git checkout` wasn't removed or deprecated — both forms coexist — but `switch`/`restore` are the recommended default going forward because they make each command's intent unambiguous from its name alone.

**[Senior] Q5. A teammate insists their branch `feature-x` is up to date because `origin/feature-x` shows the commit they expect. Why might they still be wrong?**
**Model answer:** `origin/feature-x` is a remote-tracking branch, not a live view of the remote — it's a snapshot Git recorded during their last `fetch` or `pull`. If anyone has pushed new commits to the actual `feature-x` on the server since then, their local `origin/feature-x` is simply stale until they fetch again; Git gives no automatic notification of this. The reliable check is to run `git fetch` first, then compare, or examine ahead/behind counts via `git branch -vv` or `git status` immediately after a fresh fetch — never trust a remote-tracking branch's currency without having just synchronized.

## 15. Common Misconceptions

1. **"`git branch <name>` switches me to the new branch."** It only creates the ref; you remain on your previous branch. Use `switch -c` / `checkout -b` to create and switch together.
2. **"`git checkout` is deprecated in favor of `switch`/`restore`."** It is not deprecated; it still performs both of its historical jobs and remains extremely common in existing scripts, docs, and habits. `switch`/`restore` are the _recommended_ narrower alternatives, not replacements that remove `checkout`.
3. **"Deleting a branch deletes its commits."** Deleting a branch removes only the pointer file; the commit objects remain in the object database, reachable via the reflog, until garbage collection actually prunes genuinely unreferenced objects.
4. **"`origin/main` always reflects the real, current state of `main` on the server."** It reflects the state as of your last fetch — it is a cached, read-only bookmark, not a live view.
5. **"Orphan branches are a rare, obscure feature with no real use."** They're the standard mechanism behind patterns like the classic `gh-pages` publishing branch, kept deliberately historyless from the main line.

## 16. 🔑 Key Takeaways

- A branch is a movable pointer file; every command in this section (`branch`, `switch`, `checkout -b`) ultimately manipulates that one small fact from §6's ref mechanics.
- `git switch` and `git restore` (Git 2.23+) split `checkout`'s two historically overloaded jobs into single-purpose commands; `checkout` still works and remains common in the wild.
- `-d` is the safe branch delete (reachability-checked); `-D` forces it — neither immediately destroys the underlying commits.
- Local branches, remote-tracking branches, and remote branches are three distinct things; remote-tracking branches are read-only, locally cached snapshots updated only by `fetch`/`pull`.
- `--merged`/`--no-merged` expose the same reachability check `branch -d` uses internally, making them the right tool for bulk cleanup audits.
- Orphan branches (`--orphan`) start with zero parent commits, deliberately sharing no history with the rest of the repository.

## 17. Related Concepts & What's Next

This section assumed the ref mechanics from §6 and built the full command surface on top of them. Branches you create here become meaningful once you need to combine their work back together — §13 covers exactly that: fast-forward and three-way merges, conflict resolution, and merge strategies. Later, §22 revisits the naming conventions introduced earlier in this section (see the branch naming conventions section above) as part of full branching-strategy models (Git Flow, trunk-based development, and others) at the team-workflow level.
