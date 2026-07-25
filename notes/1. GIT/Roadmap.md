# Complete Roadmap (Table of Contents)

## Part 1 — Foundations

1. Version control fundamentals & the world before Git
2. The birth of Git: history, design goals, philosophy & why it won
3. Git terminology & the core mental model

## Part 2 — Architecture & Internals

4. Git architecture: the three areas (working directory, index, repository) & repo anatomy
5. The object model: blobs, trees, commits, annotated tags & content-addressable storage
6. References: branches, HEAD, tags, refs & the reflog
7. Inside .git: loose objects, packfiles, delta compression & garbage collection

## Part 3 — Setup & the Daily Workflow

8. Installation & configuration (git config in depth)
9. Creating & cloning repositories
10. The core workflow: status, add, commit, diff, log
11. Ignoring & controlling files: .gitignore and .gitattributes

## Part 4 — Branching, Merging & History Surgery

12. Branching in depth
13. Merging: fast-forward, three-way merges, strategies & conflict resolution
14. Rebasing: standard, interactive, autosquash & the golden rule
15. Undoing things: restore, reset, revert, clean (and legacy checkout)
16. Stashing work in progress
17. Cherry-pick & moving changes between branches; patch files
18. Tags, versioning & release management
19. Interrogating history: log mastery, blame, bisect, grep, shortlog

## Part 5 — Remotes & Team Collaboration

20. Remotes in depth: fetch, pull, push, tracking branches & refspecs
21. Collaboration models: shared repository vs fork & pull request; code review workflow
22. Branching strategies: Git Flow, GitHub Flow, GitLab Flow & trunk-based development
23. Git hosting & enterprise platforms: GitHub, GitLab, Bitbucket; protected branches, CODEOWNERS, governance

## Part 6 — Automation & Scale

24. Git hooks & automation (client-side, server-side, pre-commit framework, Husky)
25. Git in CI/CD pipelines
26. Scaling Git: large repositories, monorepos, shallow & partial clones, sparse-checkout, Git LFS
27. Submodules & subtrees: composing multiple repositories

## Part 7 — Security & Operations

28. Security: commit/tag signing (GPG/SSH), credential management, leaked secrets & history remediation
29. Maintenance, performance tuning & troubleshooting common failures
30. Disaster recovery: reflog, fsck, recovering lost commits & repairing corruption

## Part 8 — Mastery, Interviews & Wrap-Up

31. Advanced tooling: worktrees, rerere, notes, bundles, filter-repo & history rewriting at scale
32. Git's evolution: version differences, deprecated features, SHA-256; Git vs SVN vs Mercurial vs Perforce
33. Consolidated best practices & anti-patterns
34. Interview preparation: tiered questions with model answers (beginner → FAANG)
35. Hands-on labs & mini-projects (beginner → production-style)
36. Key takeaways, knowledge graph & recommended next topics
