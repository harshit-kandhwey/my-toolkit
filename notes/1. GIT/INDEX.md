# Git Zero-to-Mastery Knowledge Base — Index

A comprehensive, 36-section learning resource organized into 8 parts covering Git from first principles and internals through daily workflow, branching/merging/rebasing, team collaboration, automation and scale, security and disaster recovery, to mastery-level interview and hands-on preparation. Navigate by part, read sections sequentially, or jump to topics of interest.

---

## Quick Navigation

| Part                          | Topic                                        | Sections |
| ------------------------------ | --------------------------------------------- | -------- |
| **[Part 1](./Contents/Part1)** | Foundations                                   | 1–3      |
| **[Part 2](./Contents/Part2)** | Architecture & Internals                      | 4–7      |
| **[Part 3](./Contents/Part3)** | Setup & the Daily Workflow                    | 8–11     |
| **[Part 4](./Contents/Part4)** | Branching, Merging & History Surgery          | 12–19    |
| **[Part 5](./Contents/Part5)** | Remotes & Team Collaboration                  | 20–23    |
| **[Part 6](./Contents/Part6)** | Automation & Scale                            | 24–27    |
| **[Part 7](./Contents/Part7)** | Security & Operations                         | 28–30    |
| **[Part 8](./Contents/Part8)** | Mastery, Interviews & Wrap-Up                 | 31–36    |

---

## Folder Structure

```
1. GIT/
├── README.md (quick-start guide)
├── INDEX.md (this file — comprehensive navigation & section index)
├── Roadmap.md (original planning roadmap)
│
└── Contents/ (modular organization by part)
    ├── Part1/ (3 sections: Foundations)
    ├── Part2/ (4 sections: Architecture & Internals)
    ├── Part3/ (4 sections: Setup & the Daily Workflow)
    ├── Part4/ (8 sections: Branching, Merging & History Surgery)
    ├── Part5/ (4 sections: Remotes & Team Collaboration)
    ├── Part6/ (4 sections: Automation & Scale)
    ├── Part7/ (3 sections: Security & Operations)
    └── Part8/ (6 sections: Mastery, Interviews & Wrap-Up)
```

---

## Part Summaries

### Part 1 — Foundations

Version control fundamentals and the world before Git, the birth of Git (the BitKeeper crisis, Linus Torvalds's requirements, and the four design pillars: speed, simplicity, distribution, integrity), and Git's terminology built around the core three-tree mental model (working directory, staging area, repository).

| §   | Section                                             | File                                                                                                             |
| --- | ---------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Version Control Fundamentals & the World Before Git | [Section-01-Part1-Version-Control-Fundamentals](./Contents/Part1/Section-01-Part1-Version-Control-Fundamentals.md) |
| 2   | The Birth of Git                                    | [Section-02-Part1-Birth-of-Git](./Contents/Part1/Section-02-Part1-Birth-of-Git.md)                                 |
| 3   | Git Terminology & the Core Mental Model             | [Section-03-Part1-Git-Terminology-Core-Mental-Model](./Contents/Part1/Section-03-Part1-Git-Terminology-Core-Mental-Model.md) |

### Part 2 — Architecture & Internals

Git's physical architecture (working directory, index, object database), the object model (blobs, trees, commits, annotated tags, content-addressable storage and the Merkle DAG), references (branches, HEAD, tags, the reflog), and what's physically inside `.git` (loose objects, packfiles, delta compression, garbage collection).

| §   | Section                                                        | File                                                                                                                                     |
| --- | ---------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Git Architecture: the Three Areas & Repo Anatomy                | [Section-04-Part2-Git-Architecture-Three-Areas](./Contents/Part2/Section-04-Part2-Git-Architecture-Three-Areas.md)                         |
| 2   | The Object Model: Blobs, Trees, Commits & Content-Addressable Storage | [Section-05-Part2-Object-Model](./Contents/Part2/Section-05-Part2-Object-Model.md)                                                          |
| 3   | References: Branches, HEAD, Tags, Refs & the Reflog             | [Section-06-Part2-References-Branches-HEAD-Tags-Reflog](./Contents/Part2/Section-06-Part2-References-Branches-HEAD-Tags-Reflog.md)         |
| 4   | Inside `.git`: Loose Objects, Packfiles & Garbage Collection     | [Section-07-Part2-Inside-Git-Loose-Objects-Packfiles-GC](./Contents/Part2/Section-07-Part2-Inside-Git-Loose-Objects-Packfiles-GC.md)       |

### Part 3 — Setup & the Daily Workflow

Installing and configuring Git (including SSH keys, credential helpers, and diff/merge tools), creating and cloning repositories, the everyday core workflow (status/add/commit/diff/log), and controlling what Git tracks (`.gitignore`/`.gitattributes`, including line-ending/`autocrlf` handling).

| §   | Section                                                  | File                                                                                                                       |
| --- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Installation & Configuration                             | [Section-08-Part3-Installation-Configuration](./Contents/Part3/Section-08-Part3-Installation-Configuration.md)             |
| 2   | Creating & Cloning Repositories                           | [Section-09-Part3-Creating-Cloning-Repositories](./Contents/Part3/Section-09-Part3-Creating-Cloning-Repositories.md)       |
| 3   | The Core Workflow — status, add, commit, diff, log       | [Section-10-Part3-Core-Workflow](./Contents/Part3/Section-10-Part3-Core-Workflow.md)                                       |
| 4   | Ignoring & Controlling Files — .gitignore/.gitattributes | [Section-11-Part3-Ignoring-Controlling-Files](./Contents/Part3/Section-11-Part3-Ignoring-Controlling-Files.md)             |

### Part 4 — Branching, Merging & History Surgery

The largest part of the corpus: branching in depth, merging (fast-forward/three-way/strategies/conflicts), rebasing (interactive/autosquash/the Golden Rule), undoing things (restore/reset/revert/clean), stashing, cherry-pick & patch files, tags/versioning (SemVer, Conventional Commits), and interrogating history (log mastery, blame, bisect, grep).

| §   | Section                                                          | File                                                                                                                                 |
| --- | ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Branching in Depth                                               | [Section-12-Part4-Branching-In-Depth](./Contents/Part4/Section-12-Part4-Branching-In-Depth.md)                                       |
| 2   | Merging — Fast-Forward, Three-Way Merges & Conflict Resolution   | [Section-13-Part4-Merging](./Contents/Part4/Section-13-Part4-Merging.md)                                                             |
| 3   | Rebasing — Standard, Interactive, Autosquash & the Golden Rule   | [Section-14-Part4-Rebasing](./Contents/Part4/Section-14-Part4-Rebasing.md)                                                           |
| 4   | Undoing Things — restore, reset, revert, clean                   | [Section-15-Part4-Undoing-Things](./Contents/Part4/Section-15-Part4-Undoing-Things.md)                                               |
| 5   | Stashing Work in Progress                                        | [Section-16-Part4-Stashing](./Contents/Part4/Section-16-Part4-Stashing.md)                                                           |
| 6   | Cherry-Pick & Moving Changes Between Branches; Patch Files       | [Section-17-Part4-Cherry-Pick-Patches](./Contents/Part4/Section-17-Part4-Cherry-Pick-Patches.md)                                     |
| 7   | Tags, Versioning & Release Management                            | [Section-18-Part4-Tags-Versioning-Release-Management](./Contents/Part4/Section-18-Part4-Tags-Versioning-Release-Management.md)       |
| 8   | Interrogating History — log Mastery, blame, bisect, grep, shortlog | [Section-19-Part4-Interrogating-History](./Contents/Part4/Section-19-Part4-Interrogating-History.md)                                 |

### Part 5 — Remotes & Team Collaboration

Remotes in depth (fetch/pull/push, tracking branches, refspecs), collaboration models (shared repo vs fork & pull request, code review), branching strategies (Git Flow, GitHub Flow, GitLab Flow, trunk-based development), and Git hosting & enterprise platforms (including self-hosted servers, protected branches, and CODEOWNERS).

| §   | Section                                                             | File                                                                                                                                                     |
| --- | ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Remotes in Depth — fetch, pull, push, tracking branches & refspecs | [Section-20-Part5-Remotes-In-Depth](./Contents/Part5/Section-20-Part5-Remotes-In-Depth.md)                                                               |
| 2   | Collaboration Models — Shared Repository vs Fork & Pull Request     | [Section-21-Part5-Collaboration-Models](./Contents/Part5/Section-21-Part5-Collaboration-Models.md)                                                       |
| 3   | Branching Strategies — Git Flow, GitHub Flow, GitLab Flow & Trunk-Based | [Section-22-Part5-Branching-Strategies](./Contents/Part5/Section-22-Part5-Branching-Strategies.md)                                                       |
| 4   | Git Hosting & Enterprise Platforms — GitHub, GitLab, Bitbucket       | [Section-23-Part5-Git-Hosting-Enterprise-Platforms](./Contents/Part5/Section-23-Part5-Git-Hosting-Enterprise-Platforms.md)                               |

### Part 6 — Automation & Scale

Git hooks & automation (pre-commit framework, Husky), Git in CI/CD pipelines (including GitOps), scaling Git for large repositories and monorepos (shallow/partial clones, sparse-checkout, Git LFS), and submodules & subtrees for composing multiple repositories.

| §   | Section                                    | File                                                                                                                     |
| --- | --------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Git Hooks & Automation                     | [Section-24-Part6-Git-Hooks-Automation](./Contents/Part6/Section-24-Part6-Git-Hooks-Automation.md)                       |
| 2   | Git in CI/CD Pipelines                     | [Section-25-Part6-Git-in-CICD-Pipelines](./Contents/Part6/Section-25-Part6-Git-in-CICD-Pipelines.md)                     |
| 3   | Scaling Git — Large Repos, Monorepos, LFS  | [Section-26-Part6-Scaling-Git](./Contents/Part6/Section-26-Part6-Scaling-Git.md)                                         |
| 4   | Submodules & Subtrees                      | [Section-27-Part6-Submodules-Subtrees](./Contents/Part6/Section-27-Part6-Submodules-Subtrees.md)                         |

### Part 7 — Security & Operations

Security (commit/tag signing, credential management, leaked secrets & history remediation via `filter-repo`), maintenance/performance tuning/troubleshooting common failures, and disaster recovery (reflog, `fsck`, recovering lost commits & repairing corruption).

| §   | Section                                                                  | File                                                                                                                                                 |
| --- | ----------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Security — Signing, Credential Management, Leaked Secrets & Remediation | [Section-28-Part7-Security](./Contents/Part7/Section-28-Part7-Security.md)                                                                           |
| 2   | Maintenance, Performance Tuning & Troubleshooting                       | [Section-29-Part7-Maintenance-Performance-Troubleshooting](./Contents/Part7/Section-29-Part7-Maintenance-Performance-Troubleshooting.md)             |
| 3   | Disaster Recovery — reflog, fsck & Repairing Corruption                 | [Section-30-Part7-Disaster-Recovery](./Contents/Part7/Section-30-Part7-Disaster-Recovery.md)                                                         |

### Part 8 — Mastery, Interviews & Wrap-Up

Advanced tooling (worktrees, rerere, notes, bundles, `filter-repo`), Git's evolution (main vs master, SHA-256 transition, Git vs SVN/Mercurial/Perforce), consolidated best practices & anti-patterns, tiered interview preparation, hands-on labs, and a final knowledge-graph wrap-up.

| §   | Section                                                     | File                                                                                                                                     |
| --- | ---------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Advanced Tooling — Worktrees, Rerere, Notes, Bundles, Filter-Repo | [Section-31-Part8-Advanced-Tooling](./Contents/Part8/Section-31-Part8-Advanced-Tooling.md)                                               |
| 2   | Git's Evolution — SHA-256; Git vs SVN vs Mercurial vs Perforce   | [Section-32-Part8-Gits-Evolution](./Contents/Part8/Section-32-Part8-Gits-Evolution.md)                                                   |
| 3   | Consolidated Best Practices & Anti-Patterns                      | [Section-33-Part8-Best-Practices-Anti-Patterns](./Contents/Part8/Section-33-Part8-Best-Practices-Anti-Patterns.md)                       |
| 4   | Interview Preparation — Tiered Questions (Beginner → FAANG)      | [Section-34-Part8-Interview-Preparation](./Contents/Part8/Section-34-Part8-Interview-Preparation.md)                                     |
| 5   | Hands-On Labs & Mini-Projects                                    | [Section-35-Part8-Hands-On-Labs](./Contents/Part8/Section-35-Part8-Hands-On-Labs.md)                                                     |
| 6   | Key Takeaways, Knowledge Graph & Recommended Next Topics         | [Section-36-Part8-Key-Takeaways-Knowledge-Graph](./Contents/Part8/Section-36-Part8-Key-Takeaways-Knowledge-Graph.md)                     |

---

## How Sections Cross-Reference

Every section uses inline `§N` (or `§N.M` for a specific subsection) references to point forward and backward to related material — e.g. "detached HEAD (§6.4.2)" or "covered in full in §14". Section numbers are continuous 1–36 across the whole corpus; the `§` column in the tables above is only the section's position *within its Part*, while the filename and H1 header always carry the absolute section number.
