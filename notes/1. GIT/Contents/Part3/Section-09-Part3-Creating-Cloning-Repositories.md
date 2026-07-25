# Section 9 (Part 3): Creating & Cloning Repositories

## 9.1 Definition

**Plain language:** There are exactly two ways a Git repository comes into existence for you: you create a brand-new, empty one (`git init`), or you copy an existing one from somewhere else, history and all (`git clone`).

**Precise:** `git init` creates the `.git` directory anatomy described in §4.3 — object database, refs, HEAD, index, config — from nothing, with zero commits. `git clone` performs a network (or local-filesystem) transfer of a remote repository's entire object database and refs, then materializes a working directory from the resulting default branch, additionally configuring a **remote** named `origin` and a full set of **remote-tracking branches** (§6.7) pointing at the source's branches.

## 9.2 Why It Exists / Problem It Solves

Every project needs exactly one moment where "there is no repository yet" transitions to "there is." Git deliberately keeps this transition **cheap and unopinionated**: `git init` imposes no directory structure, no required files, no network call — it simply prepares a repo to start accepting commits. This matters because Git needs to work equally well for a solo developer starting a new script, a team importing a decades-old codebase, and a CI system spinning up ephemeral clones thousands of times a day — a single, minimal primitive scales to all three.

## 9.3 `git init` in Depth

### 9.3.1 Basic usage

```bash
# Purpose: create a new empty repository in the current directory
$ mkdir my-project && cd my-project
$ git init
Initialized empty Git repository in /home/user/my-project/.git/
```

This creates the entire `.git` anatomy from §4.3 with zero commits — `git log` at this point fails with `fatal: your current branch 'main' does not have any commits yet`, because there is nothing to log.

### 9.3.2 Converting an existing folder vs starting fresh

`git init` works identically whether the directory is empty or already full of files — this is the mechanism behind "adding version control to an existing project":

```bash
# Purpose: retroactively put an existing, unversioned project under Git
$ cd existing-project        # already has files, no .git yet
$ git init
$ git status
Untracked files:
  (use "git add <file>..." to include in what will be committed)
        src/main.py
        README.md
        ...
$ git add .
$ git commit -m "Initial commit"
```

Nothing about `git init` inspects or cares what's already in the directory — it purely creates the empty repository scaffolding; your first `git add`/`git commit` is what actually brings existing files into history.

### 9.3.3 Naming the initial branch: `--initial-branch`

```bash
# Purpose: explicitly name the first branch, overriding whatever init.defaultBranch (§8.5) or Git's fallback default is
$ git init --initial-branch=main
# short form:
$ git init -b main
```

If neither `init.defaultBranch` is configured nor `-b` is passed, Git falls back to `master` and prints a warning on every `init` — this is precisely why §8.5 recommends setting `init.defaultBranch` once, globally, rather than passing `-b` on every single `init`.

### 9.3.4 `--bare` repositories

```bash
# Purpose: create a repository with NO working directory — pure object database + refs
$ git init --bare project.git
Initialized empty Git repository in /srv/git/project.git/
```

A bare repository has the same internal structure as `.git/` in a normal repo, but it _is_ the top-level directory — there is no working directory, no index in the usual sense, nothing to edit directly. Full contrast in 9.5.

## 9.4 `git clone` — Full Mechanics

### 9.4.1 What actually happens on disk

```bash
# Purpose: copy an entire remote repository, including all history, to your machine
$ git clone https://github.com/example-org/example-repo.git
Cloning into 'example-repo'...
remote: Enumerating objects: 1204, done.
remote: Counting objects: 100% (1204/1204), done.
remote: Compressing objects: 100% (612/612), done.
Receiving objects: 100% (1204/1204), 3.2 MiB | 4.1 MiB/s, done.
Resolving deltas: 100% (589/589), done.
```

Step by step, `git clone` performs:

1. **Full object transfer.** Every reachable commit, tree, and blob object across every branch and tag on the remote is transferred (as compressed packfiles over the wire — §7), not just the currently-checked-out branch's content. This is why a clone can be large even if you only ever intend to work on `main`.
2. **`origin` remote creation.** A remote named `origin` is registered in `.git/config`, pointing at the URL you cloned from — this is purely a convention name (§20 covers remotes formally), not a Git keyword.
3. **Remote-tracking branches for every branch on the remote.** Each of the source repo's branches becomes a _local, read-only_ bookkeeping ref under `refs/remotes/origin/<branch>` (§6.7) — `origin/main`, `origin/develop`, etc. — recording where each branch was as of this clone/fetch.
4. **A local branch for the default branch only.** Git creates exactly one local, checked-out branch — matching whatever the remote's default branch is (commonly `main`) — set to **track** the corresponding remote-tracking branch. Other remote branches exist only as `origin/<name>` refs until you explicitly check them out locally (`git switch <name>` auto-creates the local tracking branch on first use, per §6.13's troubleshooting table).
5. **Working directory materialization.** Git checks out the default branch's tree, writing every file into a new working directory, and populates the index to match.

```
BEFORE clone:                          AFTER clone:

Remote (GitHub):                       Local machine:
  refs/heads/main    → C5              .git/refs/heads/main         → C5   (local, checked out)
  refs/heads/develop → C3              .git/refs/remotes/origin/main    → C5
                                        .git/refs/remotes/origin/develop → C3
  ALL objects reachable                .git/objects/  (full copy of everything reachable)
  from either branch                   working directory/  (materialized from C5's tree)
                                        .git/config: [remote "origin"] url = ...
```

### 9.4.2 Cloning via HTTPS vs SSH URL forms

```bash
# HTTPS form — prompts for credentials/PAT per §8.7.4 (or uses a cached credential helper)
$ git clone https://github.com/example-org/example-repo.git

# SSH form — authenticates via your registered SSH key (§8.7.1)
$ git clone git@github.com:example-org/example-repo.git
```

Both produce an identical resulting repository — the URL scheme only affects _how_ the transfer authenticates and transports (§8.7.3 covers the trade-offs), never what ends up in `.git/objects`.

### 9.4.3 Naming the destination directory

```bash
# Purpose: clone into a custom directory name instead of the default (derived from the repo name)
$ git clone https://github.com/example-org/example-repo.git my-local-name
```

### 9.4.4 Shallow clones — a preview

```bash
# Purpose: clone only the most recent commit's history, not the full depth — dramatically faster/smaller on huge repos
$ git clone --depth 1 https://github.com/example-org/example-repo.git
```

This is genuinely useful (CI checkouts that only need the latest snapshot, quickly inspecting a huge repo without downloading years of history) but comes with real limitations — a shallow clone can't `git log` arbitrarily far back, and certain operations (some rebases, full blame, bisect across the truncated boundary) behave differently or fail outright. Full treatment of shallow/partial clone trade-offs, deepening (`git fetch --unshallow`), and monorepo-scale usage is §26.

## 9.5 Bare vs Non-Bare Repositories

| Aspect                               | Non-bare (normal) repo                                                                                                           | Bare repo                                                                 |
| ------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- |
| Working directory                    | Yes — files you edit                                                                                                             | None                                                                      |
| Index                                | Yes                                                                                                                              | No meaningful index                                                       |
| Typical location                     | Your local machine, `.git/` subfolder inside the project                                                                         | A server, IS the top-level directory (conventionally named `project.git`) |
| Can you `git commit` directly in it? | Yes                                                                                                                              | No — there's nothing to edit or stage                                     |
| Can you `git push` to it?            | Discouraged (pushing to a repo with a working directory can leave that directory out of sync with the branch it has checked out) | Yes — this is its entire purpose                                          |
| Purpose                              | Where humans actually do work                                                                                                    | A shared hub other repositories push to and pull from                     |

### 9.5.1 Why you'd (almost) never `--bare` init for your own dev work

A bare repository has no working directory, so you cannot edit files, `git add`, or `git commit` in the everyday sense inside one. It exists purely to be a **push/pull target** — a shared reference point with no local editing concerns to conflict with incoming pushes. This is exactly the shape of what lives behind `github.com/<org>/<repo>` or a self-hosted Git server (§23): the platform's storage layer is a bare repository, and every developer's machine holds a full, non-bare clone of it. Setting up your own personal Git server on a home network or internal box follows the same pattern — `git init --bare` on the server, `git clone`/`git push` from your normal working machine.

> ⚠️ **Common confusion to preempt:** pushing to a _non-bare_ repository's currently-checked-out branch is technically possible but actively discouraged by Git itself (it refuses by default, with `receive.denyCurrentBranch` protecting you) because the push would update the branch ref without touching that repo's working directory or index, leaving them silently out of sync with what the ref now says HEAD should look like. Bare repos sidestep this entire problem by having no working directory to desync.

## 9.6 Hands-On Walkthrough

```bash
# Purpose: full walkthrough — init a "server" bare repo, clone it, work, push back, clone again elsewhere

# 1. Create a bare repo to act as our shared hub
$ mkdir -p /srv/demo && cd /srv/demo
$ git init --bare team-project.git
Initialized empty Git repository in /srv/demo/team-project.git/

# 2. Clone it (currently empty) to a working location
$ cd ~/work
$ git clone /srv/demo/team-project.git
Cloning into 'team-project'...
warning: You appear to have cloned an empty repository.

# 3. Do normal work
$ cd team-project
$ echo "# Team Project" > README.md
$ git add README.md
$ git commit -m "Initial commit"
[main (root-commit) 9f8e7d6] Initial commit
 1 file changed, 1 insertion(+)

# 4. Push back to the shared hub
$ git push origin main
To /srv/demo/team-project.git
 * [new branch]      main -> main

# 5. A second clone (simulating a teammate) sees the same history
$ cd ~/other-location
$ git clone /srv/demo/team-project.git teammate-copy
$ cd teammate-copy
$ git log --oneline
9f8e7d6 Initial commit
```

This mirrors real GitHub/GitLab usage exactly, substituting a local bare repo for the hosted equivalent — the mechanics (bare hub, full clones, push/pull) are identical.

## 9.7 Production & Enterprise Usage Notes

- **CI pipelines clone (usually shallow) on every job** rather than reusing a persistent checkout, trading a few seconds of clone time for a guaranteed-clean, reproducible starting state — full CI patterns in §25.
- **Monorepo-scale organizations** increasingly avoid full clones altogether via partial clone (`--filter=blob:none`) and sparse-checkout, deferred fully to §26, because "download everything" stops scaling once a repo reaches many gigabytes.
- **Server-side bare repos are the near-universal shape** of what a Git hosting platform stores per-repository, whether GitHub's infrastructure, a self-hosted GitLab instance, or a bare-bones `git init --bare` on a company file server accessed over SSH.

## 9.8 Interview Questions

**[Beginner] Q1. What's the difference between `git init` and `git clone`?**
**Model answer:** `git init` creates a brand-new, empty repository from scratch — no history, no remotes configured automatically, just the bare scaffolding of `.git`. `git clone` copies an _existing_ repository from somewhere else, transferring its entire history, setting up a remote named `origin` pointing back at the source, creating remote-tracking branches for all of the source's branches, and checking out a working copy of its default branch. You use `init` to start something new; you use `clone` to obtain a working copy of something that already exists.

**[Intermediate] Q2. When you clone a repository with five branches, how many local branches do you end up with, and what happens to the other four?**
**Model answer:** You end up with exactly one local, checked-out branch — matching the remote's default branch — configured to track its corresponding remote-tracking branch. The other four branches aren't ignored; they're represented as remote-tracking branches under `refs/remotes/origin/<name>`, which are read-only bookkeeping refs recording where each branch was as of the clone. You don't get a local, independently-committable branch for them until you explicitly check one out (e.g. `git switch feature-x`), at which point Git creates a real local branch tracking the matching remote-tracking branch.

**[Senior] Q3. Why does a Git hosting platform's server-side storage use bare repositories, and what would go wrong if it used normal, non-bare ones instead?**
**Model answer:** A bare repository has no working directory or meaningful index — it's purely an object database and a set of refs, which is exactly the right shape for something that exists solely to be pushed to and pulled from by many clients, with no local editing of its own. If the server instead ran a normal repository with a checked-out working directory, every incoming push that moved the currently-checked-out branch would leave that working directory and index silently out of sync with the new ref value — nothing would update them automatically, since push only writes objects and moves refs. Git actually protects against this by default (`receive.denyCurrentBranch`), refusing pushes to the checked-out branch of a non-bare repo precisely because the desync has no automatic resolution. Bare repos sidestep the entire class of problem by having no working directory to desync in the first place.

## 9.9 Common Misconceptions

1. **"Cloning only downloads the current branch."** By default, clone transfers every reachable object across all branches and tags on the remote; only shallow clone (`--depth`) restricts what's downloaded, and even then it's depth-limited, not branch-limited by default.
2. **"A bare repository is just a `.git` folder renamed."** Structurally true, but the meaningful distinction is behavioral: a bare repo has no working directory or index to keep in sync, which is precisely why it's safe as a push target and a normal repo (by default) is not.
3. **"`git init` on a folder full of existing files automatically tracks them."** `git init` only creates the empty repository scaffolding; nothing is tracked until you `git add` and `git commit` those files yourself.
4. **"HTTPS and SSH clones behave differently once cloned."** The resulting repository is identical either way; the URL scheme only affects the authentication/transport used during clone, fetch, and push.

## 9.10 🔑 Key Takeaways

- `git init` creates an empty repository from nothing; `git clone` copies a full existing repository, setting up `origin` and remote-tracking branches automatically.
- A clone transfers _all_ reachable history by default, checks out only the default branch locally, and represents the rest as remote-tracking refs until you check them out.
- Bare repositories (`--bare`) have no working directory or index and exist purely as push/pull targets — the standard shape for server-side hosting; you'd essentially never use one for your own local editing.
- Shallow clones (`--depth`) trade completeness of history for speed and size — a preview here, full trade-off analysis in §26.
- HTTPS vs SSH clone URLs differ only in authentication/transport, never in the resulting repository's content.

## 9.11 Related Concepts & What's Next

`origin` and remote-tracking branches, created automatically by clone here, are only lightly explained in this section — §20 (Remotes in Depth) covers fetch/pull/push mechanics, multiple remotes, and tracking relationships in full. Bare repositories reappear as the foundation of §23's hosting-platform discussion and §30's disaster-recovery scenarios (a bare repo elsewhere is a legitimate backup strategy). With a repository created or cloned, §10 covers the everyday commands — status, add, commit, diff, log — that make up the vast majority of daily Git usage.
