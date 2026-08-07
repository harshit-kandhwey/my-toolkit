# Section 1 (Part 1): Version Control Fundamentals & The World Before Git

## 1. Definition

**Plain language:** A version control system (VCS) is software that remembers every meaningful version of your files, who changed them, when, and why — so you can look back, undo mistakes, work in parallel with others, and prove exactly what existed at any point in time.

**Precise:** A VCS manages an evolving set of files (a **repository**) as a sequence — or, in modern systems, a directed graph — of immutable, recorded states called **revisions** (in Git: **commits**), each carrying metadata (author, timestamp, message, parent revision(s)). It provides operations to record new revisions (**commit**), retrieve old ones (**checkout**), compare them (**diff**), develop lines of work in parallel (**branch**), and reconcile parallel work (**merge**).

Two synonyms you'll meet in job descriptions and older literature: **SCM** (Source Code Management / Software Configuration Management) and **revision control**. In practice all three terms refer to the same category of tool.

## 2. Why It Exists — The Problems It Solves

Each of these is a concrete failure mode that teams suffered before (and without) version control. Interviewers love asking "why do we even need Git?" — a strong answer names several of these explicitly.

1. **History and undo.** Without a VCS, "history" means folders named `project_final`, `project_final_v2`, `project_final_REALLY_final`. There is no reliable way to answer "what did this file look like last Tuesday?" A VCS makes every recorded state retrievable forever.
2. **The lost-update problem.** Two people open the same file from a shared folder, both edit, both save — whoever saves last silently destroys the other's work. This is the single biggest collaboration killer a VCS eliminates, either by locking files or by merging concurrent edits.
3. **Attribution and accountability.** Production breaks at 3 a.m. You need to know _which change_ broke it, _who_ made it, and _what they were trying to do_. Version control attaches author, timestamp, and an explanatory message to every change, creating an audit trail.
4. **Safe experimentation (branching).** You want to try a risky refactor without endangering the working code. Branches give you a parallel line of development that can be merged if it works or discarded if it doesn't.
5. **Release management and reproducibility.** "Customer X runs version 2.3.1 — rebuild exactly that." A VCS lets you tag and reproduce the precise file state of any shipped release, which is essential for patching old versions and for regulated industries.
6. **Debugging via history.** If you know version 100 worked and version 150 is broken, the bug entered somewhere in between. History enables systematic search for the offending change (Git automates this with `bisect`, covered in [§19](../Part4/Section-19-Part4-Interrogating-History.md)).
7. **Backup and redundancy.** In distributed systems specifically, every developer's copy is a complete backup of the entire project history — the server catching fire loses nothing but convenience.
8. **Compliance and governance.** Finance, healthcare, and government software must often _prove_ who approved and introduced every change (SOX, ISO 27001, FDA audit trails). Modern VCS platforms plus signed commits ([§28](../Part7/Section-28-Part7-Security.md)) provide exactly that evidence chain.

> 💡 **Tip:** Notice that only some of these problems are about _code_. Version control is equally valuable for documentation, configuration files, infrastructure-as-code (Terraform, Ansible — both future topics), and any evolving plain-text asset. This is why "GitOps" ([§25](../Part6/Section-25-Part6-Git-in-CICD-Pipelines.md)) treats Git as the source of truth for entire infrastructures.

## 3. Life Before Version Control — Manual "Systems"

To appreciate the tooling, understand what teams actually did:

- **Copy-and-rename backups:** duplicating the project folder before risky changes. Failure modes: no metadata (which copy is what?), enormous disk waste, no merging, human discipline required.
- **Shared network folders:** everyone edits files on a common drive. Failure mode: the lost-update problem in its purest form, plus zero history.
- **Sneakernet / emailed archives:** zipping the project and emailing it around. Failure modes: divergent copies with no way to reconcile them, "which zip is newest?" chaos.
- **Lock files by convention:** a `LOCKED_BY_RAJESH.txt` dropped in a folder. Failure modes: forgotten locks blocking everyone, no enforcement.

Every generation of VCS below mechanizes and enforces what these manual conventions attempted.

## 4. Generation 1 — Local Version Control (single machine, single file)

The first generation tracked versions of **individual files on one machine**. No collaboration, no networking — just history and undo for yourself.

**SCCS — Source Code Control System (1972–73, Marc Rochkind, Bell Labs).** The first real VCS. It stored each tracked file's entire history in a companion file using **interleaved deltas** (the "weave"): all versions woven into one structure, so retrieving _any_ version took roughly equal time. It introduced the **lock-modify-unlock** discipline: you had to lock a file to edit it, guaranteeing serial access.

**RCS — Revision Control System (1982, Walter Tichy, Purdue University).** SCCS's successor and far more widely adopted (it still ships on many Unix systems). RCS stored history in `filename,v` files using **reverse deltas**: the _newest_ version is stored in full, and older versions are stored as backward differences from it. Rationale: you check out the latest version far more often than old ones, so make that the fast path. Commands were `ci` (check in) and `co` (check out), with the same lock-based model.

> 🔑 **Two ideas from Generation 1 that echo in Git:**
>
> - **Delta storage** (storing differences rather than full copies) — Git rejects this at the _logical_ level but reuses it inside packfiles for compression ([§7](../Part2/Section-07-Part2-Inside-Git-Loose-Objects-Packfiles-GC.md)). This distinction is a classic interview trap; we'll nail it in [§5](../Part2/Section-05-Part2-Object-Model.md).
> - **Locking vs merging** as the two possible answers to concurrent edits — the fundamental fork in the road for all later systems.

**Limitations of Generation 1:** one file at a time (no concept of a coherent multi-file project state), one machine, one editor at a time per file. Fine for a lone sysadmin versioning `/etc` configs; useless for a software team.

## 5. Generation 2 — Centralized Version Control (CVCS)

The second generation added the missing ingredient: **collaboration through a central server**.

### 5.1 Architecture

```
                    ┌────────────────────────┐
                    │     CENTRAL SERVER     │
                    │  the ONLY full copy of │
                    │  the project history   │
                    └───────────┬────────────┘
                 network needed │ for almost everything
            ┌───────────────────┼───────────────────┐
            ▼                   ▼                   ▼
     ┌────────────┐      ┌────────────┐      ┌────────────┐
     │Developer A │      │Developer B │      │Developer C │
     │working copy│      │working copy│      │working copy│
     │(snapshot of│      │(snapshot of│      │(snapshot of│
     │ONE version)│      │ONE version)│      │ONE version)│
     └────────────┘      └────────────┘      └────────────┘
```

The server holds the repository — the complete history. Each developer **checks out** a **working copy**: the files of one version, plus a little bookkeeping. Nearly every meaningful operation (commit, view history, diff against an old version, branch) is a network round trip to the server.

### 5.2 The concurrency question: two philosophies

- **Lock-Modify-Unlock:** only one person may edit a file at a time (RCS heritage; optional in SVN and Perforce). Safe but serializing — developer B waits while developer A holds the lock. Still genuinely the _right_ model for unmergeable binary assets like game textures, a point we return to in 1.8 and [§26](../Part6/Section-26-Part6-Scaling-Git.md).
- **Copy-Modify-Merge:** everyone edits freely; the system merges concurrent changes and asks a human to resolve genuine **conflicts** (overlapping edits to the same lines). CVS pioneered this at scale, and it is the model Git inherits.

### 5.3 The major centralized systems

| System                               | Year                                                             | Key contribution                                                                                                                                                                     | Key weaknesses                                                                                                                                                                                                                                    |
| ------------------------------------ | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **CVS** (Concurrent Versions System) | 1986 scripts by Dick Grune; ~1989–90 C rewrite by Brian Berliner | First widely used copy-modify-merge collaboration; built atop RCS files                                                                                                              | **No atomic commits** (a multi-file commit could half-apply if interrupted, corrupting logical state); versions tracked per-file, not per-project; renames not tracked (looked like delete+add, losing history); branching/tagging painfully slow |
| **Subversion (SVN)**                 | 2000 (CollabNet), 1.0 in 2004                                    | Explicitly "a better CVS": **atomic commits**, whole-repository revision numbers (r1, r2, …), versioned directory operations and renames, cheap branching (branches are lazy copies) | Merging remained painful — real merge _tracking_ only arrived in SVN 1.5 (2008); history operations still require the server; branch model (branches live as directory paths like `/branches/feature-x`) confuses newcomers                       |
| **Perforce (Helix Core)**            | 1995                                                             | Exceptional performance on **huge repositories and large binary files**; robust file locking; fine-grained per-path permissions                                                      | Centralized (server dependency); commercial licensing; workspace/"changelist" model differs from everything else                                                                                                                                  |
| **IBM Rational ClearCase**           | 1992 (Atria)                                                     | Virtual filesystem (MVFS) presenting versions dynamically; powerful but heavyweight "config spec" selection rules                                                                    | Enormous administrative burden; slow; expensive; today almost exclusively legacy-enterprise                                                                                                                                                       |
| **Visual SourceSafe (VSS)**          | 1994 (Microsoft)                                                 | Brought VCS to the mass Windows market                                                                                                                                               | Notorious for silent database corruption; no atomicity; retired — its enterprise successor was **TFVC** inside Team Foundation Server (2005), itself now legacy as Microsoft moved to Git                                                         |

### 5.4 Strengths and fatal limitations of the centralized model

**Strengths (be fair — interviewers respect nuance):** a single authoritative source of truth; straightforward mental model; **fine-grained access control per directory** (easier than in Git, where you generally clone all-or-nothing); ability to check out only a subtree of a giant repo; effective handling of huge binaries (Perforce especially).

**Limitations:**

1. **Single point of failure.** Server down → nobody can commit, view history, or branch. Server disk lost without backups → the project's entire history is _gone_; developers hold only whatever single version they had checked out.
2. **Network dependency.** Committing, diffing against history, and log inspection all need connectivity — painful for remote work, travel, or slow links.
3. **Slow operations.** Every history query is a round trip. This shaped behavior: because commits were "expensive" events that immediately hit the shared server (and could break the build for everyone), developers committed rarely, in huge batches — the opposite of good practice.
4. **Expensive or awkward branching** (system-dependent), which discouraged the safe-experimentation workflow branching is supposed to enable.

## 6. Generation 3 — Distributed Version Control (DVCS)

The third generation's core move: **every developer's clone is a complete, first-class repository containing the full history.** There is no _technically_ privileged copy.

### 6.1 Architecture

```
                 ┌──────────────────────────────┐
                 │  "Central" remote (origin)   │
                 │  central BY CONVENTION only  │
                 │  — e.g., GitHub/GitLab —     │
                 │      full history            │
                 └──────────────┬───────────────┘
                    push/pull   │   push/pull
         ┌──────────────────────┼──────────────────────┐
         ▼                      ▼                      ▼
  ┌──────────────┐      ┌──────────────┐      ┌──────────────┐
  │ Developer A  │      │ Developer B  │      │ Developer C  │
  │ FULL repo:   │      │ FULL repo:   │      │ FULL repo:   │
  │ all history, │      │ all history, │      │ all history, │
  │ all branches │      │ all branches │      │ all branches │
  └──────┬───────┘      └──────────────┘      └──────────────┘
         │        (peer-to-peer sync also possible)
         └────────────────── push/pull ──────────────►
```

Consequences of "everyone has everything":

1. **Almost every operation is local**, hence near-instant: committing, branching, merging, diffing, and browsing the _entire_ history require zero network traffic. Network is needed only to synchronize with others (**push**/**pull** — [§20](../Part5/Section-20-Part5-Remotes-In-Depth.md)).
2. **Offline-first.** You can do a full day's work — dozens of commits across several branches — on a plane, then synchronize once.
3. **Inherent redundancy.** Every clone is a full backup of history. (⚠️ With one caveat we'll detail in [§20](../Part5/Section-20-Part5-Remotes-In-Depth.md) and [§30](../Part7/Section-30-Part7-Disaster-Recovery.md): a clone contains the history _as of its last fetch_, and typically not the server-side configuration like pull requests or permissions — those live in the hosting platform's database, which still needs its own backups.)
4. **Cheap, fast branching** changed developer culture: branches went from a ceremonial event to something you create ten times a day.
5. **Flexible topologies.** Teams can work hub-and-spoke (the near-universal choice), hierarchically (the Linux kernel's "web of trust" of maintainer trees), or fully peer-to-peer.

### 6.2 The distributed systems

| System             | Year       | Notes                                                                                                                                                                                                                                                                                                                     |
| ------------------ | ---------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **BitKeeper**      | 2000       | The first prominent DVCS — _proprietary_. The Linux kernel used it 2002–2005 under a controversial free-of-charge license. Its withdrawal directly triggered Git's creation — the full story is Section 2. (BitKeeper itself was open-sourced in 2016, far too late.)                                                     |
| **Monotone**       | 2003       | Open-source DVCS built on cryptographic (SHA-1) content addressing — a design Git visibly learned from. Linus evaluated it in 2005 but found it too slow for kernel scale.                                                                                                                                                |
| **Darcs**          | 2003       | Academically interesting "patch theory" model (history as a set of commutable patches rather than snapshots); performance problems kept it niche.                                                                                                                                                                         |
| **Git**            | April 2005 | Our topic. Created by Linus Torvalds for the Linux kernel.                                                                                                                                                                                                                                                                |
| **Mercurial (hg)** | April 2005 | Created by Matt Mackall for the same reason in the same month; conceptually very close to Git with a friendlier CLI. Git's only serious long-term rival; Meta (Facebook) famously chose and extended it — more in [§26](../Part6/Section-26-Part6-Scaling-Git.md) and [§32](../Part8/Section-32-Part8-Gits-Evolution.md). |
| **Bazaar (bzr)**   | 2005       | Canonical/Ubuntu's DVCS; lost the ecosystem war, now essentially dormant.                                                                                                                                                                                                                                                 |

### 6.3 Killing a misconception early: "distributed" ≠ "no central repository"

In practice, virtually every Git team designates one hosted repository (on GitHub, GitLab, Bitbucket, or a self-hosted server) as the shared hub — conventionally named **origin**. The difference from CVCS is that this centrality is a **social convention, not a technical constraint**: the hub is just another clone, it can be moved or replaced trivially, and losing it does not lose history because every developer holds a full copy. Distributed refers to where _repositories and capabilities_ live, not to the absence of coordination.

## 7. Centralized vs Distributed — Comparison Matrix

| Dimension                        | Centralized (SVN, Perforce, TFVC)                            | Distributed (Git, Mercurial)                                                                                                                                            |
| -------------------------------- | ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Where full history lives         | Server only                                                  | Every clone                                                                                                                                                             |
| Commit                           | Network operation, immediately visible to all                | Local operation; shared only when you push                                                                                                                              |
| View history / diff old versions | Network round trip                                           | Local, instant                                                                                                                                                          |
| Work offline                     | Barely (edit files only)                                     | Fully (commit, branch, merge, inspect history)                                                                                                                          |
| Branching cost                   | System-dependent; historically discouraging                  | Trivial and instant (a branch is a 41-byte pointer — proven in [§6](../Part2/Section-06-Part2-References-Branches-HEAD-Tags-Reflog.md))                                 |
| Failure of the server            | Work stops; history at risk if backups are poor              | Inconvenience only; any clone can reseed a new hub                                                                                                                      |
| Revision identity                | Sequential numbers (r1234) issued by the server              | Content-derived hashes (e.g., `a3f8e21…`) — no central authority needed                                                                                                 |
| Partial checkout of a huge repo  | Natural (check out one subdirectory)                         | Historically weak; addressed by sparse-checkout & partial clone ([§26](../Part6/Section-26-Part6-Scaling-Git.md))                                                       |
| Per-directory read permissions   | Natural                                                      | Weak in core Git (you clone a repo or you don't); enforced instead at the platform/repo boundary ([§23](../Part5/Section-23-Part5-Git-Hosting-Enterprise-Platforms.md)) |
| Huge binary assets               | Perforce excels; locking prevents unmergeable-conflict waste | Weak in core Git; mitigated by Git LFS ([§26](../Part6/Section-26-Part6-Scaling-Git.md))                                                                                |
| Mandatory single source of truth | Enforced by architecture                                     | Established by team convention                                                                                                                                          |

> 🎯 **Interview tip:** The two rows where centralized systems genuinely _win_ — partial checkouts/permissions and large binaries — are exactly what separates a senior answer from a memorized one. "Git is better at everything" is a junior answer.

## 8. Where Each Model Survives Today

- **Git** is the overwhelming default: developer surveys (e.g., Stack Overflow's annual survey) have consistently put Git usage above 90% of respondents in recent years (roughly 93–96% — treat exact figures as approximate and year-dependent). It is the assumed baseline skill in effectively every DevOps, SRE, cloud, and software engineering interview.
- **Perforce Helix Core** remains the standard in **game development** and some hardware/embedded shops: repositories with terabytes of binary art assets, and file locking so two artists never waste hours producing unmergeable edits to the same texture.
- **SVN** persists in **legacy enterprise** codebases (and a few large projects that stayed by choice). You may be hired partly to migrate such repos to Git — migration tooling appears in [§32](../Part8/Section-32-Part8-Gits-Evolution.md).
- **ClearCase / TFVC** are pure legacy-maintenance encounters.
- **At extreme monorepo scale**, even Git's model strains: Google runs its own centralized system (**Piper**) with local caching layers, and Meta evolved Mercurial into **Sapling** with a virtual filesystem; Microsoft pushed Git itself to handle the Windows repository via innovations (partial clone, sparse-checkout, FSMonitor, background maintenance) that have since landed in mainline Git. Full treatment with decision criteria in [§26](../Part6/Section-26-Part6-Scaling-Git.md) and [§32](../Part8/Section-32-Part8-Gits-Evolution.md) — for now, the takeaway is that "everyone has all history" has real costs at hundreds-of-gigabytes scale, and the industry's answers involve re-centralizing storage while keeping Git's _interface_.

## 9. Terminology Established in This Section

These definitions are VCS-generic; Section 3 layers on Git's precise, sometimes idiosyncratic, versions of them.

| Term                                        | Definition                                                                                           |
| ------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Repository (repo)**                       | The database holding the complete managed history of a project.                                      |
| **Revision / version**                      | One recorded, immutable state of the project (Git's term: **commit**).                               |
| **Working copy / working tree**             | The actual editable files on your disk, materialized from one revision.                              |
| **Check out**                               | Materialize a chosen revision into the working copy.                                                 |
| **Commit (verb/noun)**                      | Record the current changes as a new revision / the recorded revision itself.                         |
| **Branch**                                  | An independent line of development proceeding in parallel with others.                               |
| **Merge**                                   | Combine two lines of development into one, reconciling their changes.                                |
| **Conflict**                                | Overlapping concurrent edits the system cannot reconcile automatically; a human must decide.         |
| **Tag**                                     | A permanent human-readable label on one revision (e.g., `v2.3.1`).                                   |
| **Delta**                                   | The difference between two versions of content; Gen-1/2 systems stored history as deltas.            |
| **Lock-modify-unlock vs copy-modify-merge** | The two concurrency philosophies: serialize edits via locks, or allow parallel edits and merge them. |
| **CVCS / DVCS**                             | Centralized vs Distributed VCS, per the architectures in 1.5/1.6.                                    |

## 10. Interview Questions — This Section's Material

**[Beginner] Q1. What is version control, and why does a team need it?**
**Model answer:** Version control is software that records every version of a project's files along with who changed what, when, and why. Teams need it for five core reasons: (1) history and the ability to undo — any past state is retrievable; (2) safe parallel work — it prevents the lost-update problem where one person's save silently overwrites another's; (3) branching — risky work happens on an isolated line and merges back only when ready; (4) accountability — every change carries an author, timestamp, and message, which is essential for debugging and for audits; and (5) release reproducibility — you can rebuild exactly what shipped to a customer. Without it, teams fall back on copied folders and shared drives, which provide none of these guarantees.
_What the interviewer probes:_ whether you understand VCS as solving concrete collaboration problems, or just as "the thing where I type git push."

**[Beginner] Q2. What's the difference between a centralized and a distributed VCS?**
**Model answer:** In a centralized system like SVN, exactly one server holds the full history; developers hold only a working copy of a single version, and nearly every operation — committing, viewing history, branching — requires talking to that server. In a distributed system like Git, every clone contains the complete history, so commits, branches, merges, and history inspection are local and instant, and the network is needed only to synchronize via push and pull. Consequences: DVCS works offline, is much faster for daily operations, has no single point of failure for history, and makes branching cheap; CVCS retains genuine advantages in per-directory permissions, partial checkouts of huge repos, and (in Perforce's case) large binary assets with file locking.
_Probing for:_ architectural understanding plus awareness that centralized isn't simply "worse."

**[Intermediate] Q3. SVN identifies versions with sequential numbers (r1234) while Git uses hashes like `a3f8e21`. Why the difference, and what follows from it?**
**Model answer:** Sequential numbers require a single authority to hand them out — SVN's central server increments a global counter atomically. A distributed system has no such authority: two developers can create commits simultaneously on different continents with no coordination, so identity can't come from a counter. Instead Git derives a commit's identity from a cryptographic hash of its _content and ancestry_ — the same commit computes the same ID everywhere, with no server involved. Two consequences: first, ordering in Git comes from the ancestry graph, not from comparing IDs — you can't tell which of two hashes is "newer" by looking at them; second, the hash doubles as an integrity check, since any corruption or tampering changes the ID. (The full mechanism is content-addressable storage, and it's the heart of Git's design.)
_Probing for:_ whether you grasp _why_ distribution forces content-addressing — this is the bridge to Git internals, taught in [§5](../Part2/Section-05-Part2-Object-Model.md).

**[Senior] Q4. Your game studio versions 300 GB of binary art assets. A new VP mandates Git "because it's the industry standard." How do you respond?**
**Model answer:** I'd validate the instinct — Git is the right default for source code — but explain why vanilla Git is a poor fit for this asset repo, then propose options with trade-offs. Problems: Git's model gives every clone the _entire history_, so a repo with years of revised 300 GB assets means multi-terabyte clones; binary formats neither diff nor merge, so Git's core strength (merging parallel edits) is useless for them, and without file locking two artists can spend a day producing changes that can't be reconciled — one person's work is thrown away. Options: (a) keep code in Git, keep large binary assets in Perforce, which game studios use precisely for its performance on huge files and its locking workflow; (b) Git with Git LFS, which stores binaries outside normal history and downloads only the versions you check out, plus LFS's file-locking feature — workable at moderate scale but operationally heavier and with real storage/bandwidth costs on hosting platforms; (c) evaluate scale honestly: at 300 GB of actively churning binaries, most studios land on (a). The decision criteria are asset size and churn, need for locking, team tooling familiarity, and hosting cost — not fashion.
_Probing for:_ trade-off reasoning, knowing Git's actual weaknesses, and the professional skill of pushing back on a mandate with alternatives rather than either compliance or refusal.

**[Architect / FAANG-style] Q5. Google and Meta don't run vanilla Git on their main monorepos. What breaks at that scale, and what are the architectural responses?**
**Model answer:** Three things strain: (1) _clone size_ — "every clone has all history" means checkouts measured in terabytes and hours; (2) _object and file counts_ — millions of files make status/checkout operations that scan the working tree painfully slow; (3) _write coordination_ — thousands of engineers committing to one repo daily need serialization, permissions, and CI infrastructure a plain Git remote doesn't provide. Responses fall into two families. Google kept a centralized architecture: Piper stores the monorepo centrally, developers work through lightweight views/workspaces (historically CitC), so nobody materializes the whole repo. Meta took the DVCS interface but re-engineered the guts: Mercurial extended into Sapling, backed by a virtual filesystem (EdenFS) that fetches file contents lazily on access. Microsoft proved Git itself can stretch: the Windows repo drove VFS for Git and then Scalar, whose techniques — partial clone (fetch objects lazily), sparse-checkout (materialize only needed paths), filesystem monitors for fast status, and background maintenance — were upstreamed into core Git. The common thread: keep a distributed _interface_ for developers while re-centralizing or virtualizing _storage_ so no one pays for the whole repo. I'd flag that vendor specifics evolve, but the failure modes and the lazy-fetch/virtualization response are stable.
_Probing for:_ systems thinking about where the DVCS model's costs concentrate, and familiarity with how the industry actually operates at the extreme. (Deep dive with the concrete Git features: [§26](../Part6/Section-26-Part6-Scaling-Git.md).)

## 11. Common Misconceptions

1. **"Git and GitHub are the same thing."** Git is the version control _program_ running on your machine; GitHub is one _company's hosting platform_ for Git repositories (as are GitLab and Bitbucket). Git predates GitHub (2005 vs 2008) and needs no platform at all. Fully unpacked in [§2](./Section-02-Part1-Birth-of-Git.md) and [§23](../Part5/Section-23-Part5-Git-Hosting-Enterprise-Platforms.md).
2. **"Distributed means there's no main repository."** There almost always is one — by team convention, not technical necessity (see 1.6.3).
3. **"Git stores diffs between versions."** At the logical level Git stores complete **snapshots** of the project per commit; delta compression exists only as a storage optimization inside packfiles. This is one of the most common wrong answers in interviews — the full, correct picture is [§5](../Part2/Section-05-Part2-Object-Model.md) and [§7](../Part2/Section-07-Part2-Inside-Git-Loose-Objects-Packfiles-GC.md).
4. **"Version control is only for source code."** Docs, runbooks, database migration scripts, Kubernetes manifests, Terraform — anything plain-text and evolving belongs in VCS; entire operating models (GitOps) depend on this.
5. **"SVN/Perforce are dead technologies."** Legacy SVN estates and thriving Perforce game-dev deployments say otherwise; a DevOps engineer may well be paid to run or migrate them.

## 12. 🔑 Key Takeaways

- A VCS records immutable revisions with metadata, solving history/undo, lost updates, parallel work, attribution, release reproducibility, and auditability.
- Three generations: **local** (SCCS/RCS — one file, one machine, locking), **centralized** (CVS/SVN/Perforce — collaboration via a single server holding the only full history), **distributed** (Git/Mercurial — every clone is a complete repository).
- The two concurrency philosophies are **lock-modify-unlock** and **copy-modify-merge**; Git is built on the latter, but locking remains right for unmergeable binaries.
- Distribution forces **content-derived identity** (hashes) because no central counter can exist — the seed of Git's entire object model.
- Centralized systems retain honest advantages: partial checkouts, per-path permissions, giant binaries. Knowing them is a seniority signal.
- "Central" in Git-land (origin, GitHub) is convention, not architecture.

## 13. Related Concepts & What's Next

This section deliberately ended in 2005 with the stage set: the Linux kernel project is the world's most demanding distributed development effort, it has just lost its VCS (BitKeeper), and nothing existing is fast enough. Section 2 covers what happened next — the ten days in which Git was written, the design goals Linus set (speed, integrity, distribution, and a data model borrowed from filesystems), the philosophy that still explains every odd corner of Git's UX, and how Git went from kernel tool to ~95% market share.
