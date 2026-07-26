# Section 3 (Part 1): Git Terminology & the Core Mental Model

This section defines every term Git uses precisely, the way Git itself uses it — not the generic VCS definitions from §1.9. Once these are solid, §4 onward (architecture and internals) requires zero pausing to define new vocabulary.

## 1. The Core Mental Model — Three Trees

Before individual terms, internalize this single picture. Git manages **three parallel representations of your project's files** at all times:

```
┌─────────────────┐   git add   ┌─────────────────┐  git commit  ┌─────────────────┐
│  WORKING        │ ──────────► │  STAGING AREA   │ ───────────► │  REPOSITORY     │
│  DIRECTORY      │             │  (INDEX)        │              │  (.git history) │
│                 │             │                 │              │                 │
│  Your actual    │ ◄────────── │  "What will go  │ ◄─────────── │  Permanent,     │
│  files on disk, │  git restore│   into the next │  git reset   │  immutable      │
│  editable       │  --staged   │   commit"       │              │  snapshots      │
└─────────────────┘             └─────────────────┘              └─────────────────┘
        ▲                                                                  │
        └───────────────────────── git checkout / git restore ─────────────┘
                                  (materialize a past snapshot)
```

Every Git operation you'll ever run is fundamentally about moving content between these three areas, or about inspecting/rewriting the history stored in the third. This three-tree model is unique to Git among mainstream VCS (SVN and Perforce have no equivalent middle "staging" step in ordinary use) and is the single most common source of beginner confusion — it gets its own full architectural treatment in §4. For now, just anchor the three names: **working directory**, **staging area / index**, **repository**.

## 2. Foundational Terms

**Repository (repo).** The `.git` directory and everything inside it: the complete object database (every snapshot ever committed), all branches, all tags, all configuration. "The repo" colloquially also refers to the whole project folder, but precisely, the repository _is_ the `.git` subdirectory — the working directory is not part of it, it's just what the repository currently has materialized on disk.

**Working directory (working tree).** The actual files and folders you see and edit in your file explorer or editor. At any moment it reflects one particular commit (or a mix of a commit plus your uncommitted edits). This is the _only_ one of the three trees you directly touch with a text editor.

**Staging area (the index).** A single file inside `.git` (literally named `index`) that lists exactly which file versions will be included in the _next_ commit. It is not a directory of copies — it's a structured file recording, for each tracked path, which exact blob (§5) it currently points to. `git add` copies a file's current working-directory content into the index. This staging step is what lets you build a commit up piece by piece — stage half your changes, review them, add more, then commit — rather than being forced to commit every modified file at once.

**Commit.** Both a verb (record the staged content as a new permanent snapshot) and a noun (the resulting immutable object). A commit object bundles: a pointer to a complete snapshot of the project tree, a pointer to its parent commit(s), the author, the committer (these can differ — explained in §5), a timestamp, and a message. Once created, a commit's content and hash never change — "editing" a commit (§14) always actually creates a brand-new commit object and, usually, moves a branch pointer to it.

**Branch.** In Git specifically, a branch is nothing more than a movable, named pointer to a single commit — physically, a 41-byte text file containing a hash, sitting under `.git/refs/heads/`. This minimalism is _why_ Git branching is instant regardless of repository size: creating a branch never copies any file content, it just writes a new tiny pointer file. Full mechanics in §6.

**HEAD.** A pointer to _"the commit you currently have checked out"_ — practically always implemented as a pointer to your _current branch_, which in turn points to a commit. So HEAD → branch pointer → commit, two levels of indirection in the normal case. When HEAD points directly at a commit instead of at a branch, you're in **detached HEAD** state — an important, commonly misunderstood condition covered fully in §12.

**Tag.** A permanent, (usually) unmoving name attached to one specific commit, conventionally used to mark releases (`v2.4.0`). Unlike a branch pointer, a tag is not expected to move forward as new commits are added. Two kinds exist — lightweight tags (just a pointer, like a branch but conventionally static) and annotated tags (a full object with its own message, tagger identity, and optional cryptographic signature) — the distinction and when to use each is covered in §5 and §18.

**Remote.** A named reference to another copy of the repository, usually hosted elsewhere (GitHub, GitLab, a colleague's machine, a bare server repo). "origin" is simply the conventional _default name_ Git gives the remote you cloned from — it carries no special technical meaning beyond being a name, and you can rename or add additional remotes freely. Full treatment in §20.

**Clone.** The act of copying an entire remote repository — full history, all branches, all tags — down to your machine, creating a new local repository connected back to that remote by default. Distinct from **checkout**, which materializes one particular commit's content into the working directory _within_ a repository you already have.

**Fork.** Not a Git concept at all — it's a _hosting platform_ concept (GitHub, GitLab, Bitbucket). A fork is a server-side copy of someone else's repository into your own account, used as the basis for proposing changes back via a pull/merge request. Core Git has no `git fork` command; this belongs entirely to §21 and §23.

**Merge.** Combining the history and content of two branches into one, producing a new commit (a **merge commit**) that has two (or more) parents, or, when possible, simply moving a pointer forward (**fast-forward**, §13).

**Rebase.** An alternative way to integrate changes: instead of joining two histories with a merge commit, Git re-applies your branch's commits one by one on top of a new base, producing entirely new commit objects with new hashes. This rewrites history rather than joining it — a fundamentally different operation from merge, not just a stylistic variant, and the source of Git's most important safety rule (§14's "golden rule of rebasing").

**Conflict.** A situation where two changes touch the same lines (or one side edits a file the other side deletes, etc.) such that Git cannot algorithmically decide which version — or combination — is correct. Resolution requires a human decision. Full mechanics, tooling, and prevention strategies in §13.

**Upstream / tracking branch.** A local branch can be configured to "track" a specific remote branch, meaning Git remembers the relationship and can report how many commits you're ahead/behind without you specifying the remote branch name every time (e.g., plain `git pull` or `git push` "just knows" where to go). Set up automatically by `git clone` and `git checkout -b <name> <remote>/<name>`; configurable manually. Detailed in §20.

**Fast-forward.** A special case of merging where the target branch's pointer can simply be moved forward to the incoming commit, because the target hasn't diverged at all — no new commit is created, no merge is needed, it's just a pointer update. Explained with diagrams in §13.

**Detached HEAD.** The state where HEAD points directly to a commit hash rather than to a branch name. Commits made here aren't attached to any branch and can become unreachable (effectively lost, though usually recoverable via reflog — §6, §30) if you switch away without creating a branch to hold them. Covered fully in §12.

**Reflog.** A local, private, time-ordered log of everywhere HEAD (and each branch) has pointed, kept automatically by Git on your machine. It is your safety net for recovering from mistakes — including "lost" commits after a reset, rebase, or accidental branch deletion. Not part of the shared history, not pushed to remotes, and expires after a default retention window. Deep dive in §6 and §30.

**Working tree vs. worktree (linked worktrees).** "Working tree" (two words, generic) is the general term used above. "**Worktree**" (one word) additionally refers to a specific advanced Git feature (`git worktree`) letting you check out _multiple branches simultaneously_ into separate directories from one repository — a distinct, advanced feature covered in §31. Don't conflate the two at this stage; just note the naming overlap so it doesn't confuse you later.

**Bare repository.** A repository that holds only the `.git` database — no working directory at all. This is the standard shape for a repository sitting on a shared server: nobody edits files directly on the server, so there's no need to materialize a working copy there. Covered in §20.

## 3. File-State Vocabulary

Every file Git knows about sits in exactly one of these states at any given moment — this vocabulary is what `git status` output is built from, and you'll see it constantly starting in §10:

| State          | Meaning                                                                                                                                    |
| -------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| **Untracked**  | Git has never been told to track this file; it exists in the working directory but is invisible to Git's snapshots until you `git add` it. |
| **Tracked**    | Git knows about this file — it appeared in at least one prior commit or has been staged.                                                   |
| **Unmodified** | Tracked, and identical to the version in the last commit.                                                                                  |
| **Modified**   | Tracked, and different from the last commit, but the difference hasn't been staged yet.                                                    |
| **Staged**     | The current working-directory version of this file has been added to the index — it's queued for the next commit.                          |

The classic tracked-file lifecycle:

```
   untracked ──git add──► staged ──git commit──► unmodified
                                                       │
                                                edit the file
                                                       ▼
                                                   modified ──git add──► staged ──git commit──► unmodified
```

## 4. Object & Content Vocabulary (Preview — Full Depth in §5)

You'll meet these names constantly starting in the very next section, so a lightweight preview now prevents confusion:

- **Blob** — the raw content of a single file's version (no filename, no metadata — just bytes and their type).
- **Tree** — a directory listing: an ordered list of (mode, type, name, hash) entries pointing to blobs and other trees.
- **Commit object** — metadata plus a pointer to one root tree plus pointer(s) to parent commit(s).
- **SHA** (commonly used loosely for "the hash/ID of an object") — short for the hash algorithm name (SHA-1 historically; §32 covers the SHA-256 transition). You'll see both the full 40-character hash and a shortened 7-character prefix used interchangeably once it's unambiguous.

## 5. Workflow-Level Vocabulary

- **Push** — upload your local commits (and optionally branch/tag pointers) to a remote.
- **Fetch** — download commits and refs from a remote _without_ touching your working directory or current branch — purely updates your knowledge of what the remote has.
- **Pull** — fetch, immediately followed by an integration step (by default a merge, optionally a rebase) into your current branch. A very common beginner trap is treating pull as a single atomic safe operation when it is really two operations glued together — expanded fully in §20.
- **Origin** — see Remote, above; the conventional default remote name.
- **Upstream** (second, distinct meaning) — in a fork workflow, "upstream" commonly refers to the _original_ repository a fork was copied from, as opposed to "origin," which refers to _your own_ fork. This is a different, second sense of the word "upstream" from the tracking-branch sense above — both are standard usage, and you must infer which is meant from context. Clarified again with examples in §21.

> ⚠️ **Common confusion to flag now:** the word "upstream" has two legitimate, unrelated Git-adjacent meanings — (1) the remote-tracking branch a local branch follows, and (2) in fork-based workflows, the original repo a fork came from. Both are correct; context disambiguates. This trips up learners reading multiple tutorials that each use only one sense.

## 6. Terminology Comparison Table — Git vs. SVN (Bridging from §1)

For anyone coming from a centralized-VCS background, this mapping prevents mental model contamination:

| Concept                       | SVN term/idea                                          | Git term/idea                                                                          |
| ----------------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------- |
| Full history location         | Server only                                            | Every clone                                                                            |
| Unit of history               | Global revision number (r1234)                         | Content-addressed commit hash                                                          |
| "Get latest code"             | `svn update`                                           | `git pull` (fetch + merge/rebase)                                                      |
| Parallel line of work         | Directory path convention (`/branches/x`)              | First-class lightweight pointer                                                        |
| Staging changes before commit | No equivalent — you commit working-copy state directly | The index / staging area                                                               |
| Undo a commit already shared  | Not straightforward                                    | `git revert` (safe, adds new commit) vs `git reset` (rewrites, unsafe if shared) — §15 |

## 7. Interview Questions — This Section's Material

**[Beginner] Q1. What are the three main areas Git works with, and what does each one represent?**
**Model answer:** Git manages three areas for every repository: the working directory, which is the actual editable files on disk; the staging area (also called the index), which is a record of exactly what content will go into the next commit; and the repository itself, the permanent history of committed snapshots stored in `.git`. `git add` moves content from the working directory into the staging area, and `git commit` takes what's staged and records it permanently as a new commit. This three-step model is what lets you build up a commit incrementally instead of committing every changed file at once.

**[Beginner] Q2. What exactly is a branch in Git, technically?**
**Model answer:** A branch is just a small pointer file containing a single commit hash, stored under `.git/refs/heads/`. It's not a copy of the project's files — creating a branch never duplicates any content, it just writes a new pointer. That's why branching in Git is essentially instantaneous no matter how large the repository is, unlike in some older systems where branching had a real cost.

**[Intermediate] Q3. What's the difference between `git fetch` and `git pull`?**
**Model answer:** `git fetch` downloads new commits and updated refs from a remote but does not touch your working directory or your current branch at all — it purely updates your local knowledge of what the remote has. `git pull` does a fetch and then immediately performs an integration step, by default a merge (or a rebase if configured), into your currently checked-out branch. The common mistake is treating `pull` as a single safe, inspectable operation — it actually bundles two distinct operations, and using `fetch` first lets you review incoming changes before deciding how to integrate them.

**[Intermediate] Q4. What is detached HEAD state, and why is it risky?**
**Model answer:** Normally HEAD points to a branch name, and that branch points to a commit — so HEAD moves along with the branch as you commit. In detached HEAD state, HEAD points directly to a specific commit instead of to a branch. You can still make commits in this state, but because no branch pointer is tracking them, if you switch to another branch afterward those commits can become unreachable by normal means — they're not immediately deleted, but they're not attached to anything that keeps them visible either. They're usually still recoverable through the reflog for a limited time, but the safe practice is to create a branch at that point (`git switch -c <name>`) before doing meaningful work, rather than relying on recovery after the fact.

**[Senior] Q5. Explain the two different meanings of "upstream" in Git and how you disambiguate them.**
**Model answer:** The first meaning is the tracking-branch relationship: a local branch can be configured to track a specific remote branch, and that remote branch is called its "upstream" — this is what lets plain `git push` or `git pull` work without specifying a remote and branch name explicitly. The second meaning is specific to fork-based workflows: when you fork a repository on a platform like GitHub, "upstream" conventionally refers to the original repository you forked from, as distinct from "origin," which refers to your own fork. Both usages are standard and you disambiguate by context — tracking-branch discussions use the first sense, fork/pull-request workflows use the second.

## 8. Common Misconceptions

1. **"The staging area is a folder with copies of files."** It's a single structured file (`.git/index`) recording which blob each path should get in the next commit — no per-file copies live loosely in a visible "staging folder."
2. **"`origin` is a special, hardcoded name Git treats differently."** It's purely a convention set by `git clone`; you can rename it or use any other name with no functional difference.
3. **"A tag is just a special kind of branch."** A branch pointer is expected to move forward with new commits; a tag is expected to stay fixed on the commit it was created at, and annotated tags are a distinct object type with their own metadata — not merely a static branch.
4. **"Fork is a Git feature."** It's a hosting-platform feature (GitHub/GitLab/Bitbucket); plain Git has no concept of forking.

## 9. 🔑 Key Takeaways

- Everything in daily Git use is movement between three trees: working directory → staging area (index) → repository history.
- A branch is a lightweight, movable pointer to a commit — not a copy of anything — which is why branching is instant.
- HEAD normally points at a branch, which points at a commit; detached HEAD skips the branch layer and carries real (if usually recoverable) risk.
- Fetch and pull are not the same operation — pull is fetch plus an automatic integration step.
- "Upstream" has two legitimate, context-dependent meanings; "origin" is a convention, not a Git primitive; "fork" belongs to hosting platforms, not Git itself.

## 10. Related Concepts & What's Next

Every term above will now be given full architectural depth. Section 4 opens Part 2 by mapping exactly where the working directory, index, and `.git` repository physically live on disk, how they relate as Git's core architecture, and what triggers movement between them — the direct expansion of the three-tree diagram in 3.1.
