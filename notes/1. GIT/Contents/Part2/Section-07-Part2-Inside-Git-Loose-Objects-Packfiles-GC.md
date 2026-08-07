# Section 7 (Part 2): Inside `.git`: Loose Objects, Packfiles, Delta Compression & Garbage Collection

## 1. Definition

**Plain language:** Beyond the logical object model ([§5](./Section-05-Part2-Object-Model.md)), Git has a physical storage layer that decides _how_ those objects actually sit on disk — as many small individual files, or consolidated into a few large, compressed archive-like files. This layer is purely a storage optimization and never changes what objects logically exist or how you interact with them.

**Precise:** Git objects exist on disk in one of two physical forms: **loose objects** (one zlib-compressed file per object, under `.git/objects/<first-2-hex-chars>/<remaining-38-chars>`) or **packfiles** (many objects consolidated into a single binary file, internally delta-compressed against similar objects). Git periodically repacks loose objects into packfiles via **garbage collection** (`git gc`), which also identifies and removes objects that are no longer reachable from any ref.

## 2. Why It Exists / Problem It Solves

1. **Loose objects don't scale.** One file per object is simple and exactly what you see immediately after a commit (as shown in [§4](./Section-04-Part2-Git-Architecture-Three-Areas.md)'s repository anatomy), but a repository with hundreds of thousands of commits accumulates hundreds of thousands of tiny files — filesystem overhead (inode allocation, directory traversal, per-file open/close costs) becomes a real performance and disk-usage problem at scale.
2. **Related content compresses far better together than individually.** Two commits a day apart typically share the overwhelming majority of their content (most files unchanged). Compressing each object in isolation (as loose objects do) misses this; compressing similar objects _together_, storing one as a base and others as small deltas against it, is dramatically more space-efficient — directly reusing the "delta storage" idea from Generation 1 VCS (as covered in [§1](../Part1/Section-01-Part1-Version-Control-Fundamentals.md)), but purely as a storage trick invisible above this layer.
3. **Network transfer efficiency.** When you clone or fetch, Git transmits packfiles, not thousands of individual loose objects — hugely reducing both the number of network round trips and total bytes transferred.
4. **Reclaiming space from abandoned work.** Commits made in detached HEAD and later abandoned (per [§6](./Section-06-Part2-References-Branches-HEAD-Tags-Reflog.md)'s detached-HEAD coverage), amended commits' old versions (per [§5](./Section-05-Part2-Object-Model.md)'s amend discussion), and other objects that become unreachable still physically occupy disk until `gc` prunes them — necessary periodic cleanup.

## 3. Loose Objects — Physical Detail

As established in [§4](./Section-04-Part2-Git-Architecture-Three-Areas.md)'s repository anatomy and [§5](./Section-05-Part2-Object-Model.md), every new object Git creates (from `add`, `commit`, etc.) is initially written as a **loose object**: an individual file, zlib-deflate-compressed, named by its own hash, split into a 2-character directory prefix and a 38-character filename purely to avoid having tens of thousands of files in one flat directory (a filesystem performance consideration, not a Git-logical one).

```bash
$ echo "hello" | git hash-object -w --stdin
ce013625030ba8dba906f756967f9e9ca394464

$ ls -la .git/objects/ce/
-r--r--r-- 1 user user 15 ... 013625030ba8dba906f756967f9e9ca394464
```

Each loose object is independently compressed — no relationship to any other object's storage is exploited at this stage.

## 4. Packfiles — Physical Detail

### 4.1 What a packfile contains

A packfile (`.git/objects/pack/pack-<hash>.pack`) is a single binary file containing many objects, stored as either:

- **A full, compressed copy** of an object's content (a "base" object), or
- **A delta** — instructions for reconstructing an object's content by applying a small set of changes to a chosen base object, which is itself in the same pack.

Git's packing algorithm (during `git gc` or `git repack`) groups similar objects (typically successive versions of the same file across commits) and picks efficient base/delta relationships automatically, using heuristics based on object size, type, and name similarity.

### 4.2 The companion index file

Every packfile has a matching `.idx` file (`pack-<hash>.idx`) — an index enabling Git to find any specific object _inside_ the packfile quickly (by hash) without scanning the entire pack sequentially. Without this index, looking up one object among millions in a multi-gigabyte packfile would be prohibitively slow.

```
.git/objects/pack/
├── pack-9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e.pack     ← the actual object data
└── pack-9f8e7d6c5b4a3f2e1d0c9b8a7f6e5d4c3b2a1f0e.idx      ← index into that pack
```

### 4.3 Diagram — Loose Objects vs. Packed Objects

```
BEFORE gc (loose objects):                  AFTER gc (packed):

.git/objects/                                .git/objects/
├── 1a/2b3c4d5e...  (commit 1, full)          ├── pack/
├── 4f/5e6d7c8b...  (commit 2, full)          │   ├── pack-abc123....pack
├── 7g/8h9i0j1k...  (commit 3, full)          │   │     commit1 (base, full)
├── ab/cdef123456... (blob v1, full)          │   │     commit2 (delta vs commit1)
├── bc/def1234567... (blob v2, full)          │   │     commit3 (delta vs commit2)
└── cd/ef12345678... (blob v3, full)          │   │     blob v1 (base, full)
                                              │   │     blob v2 (delta vs v1)
   Six separate compressed files,             │   │     blob v3 (delta vs v2)
   each independently compressed,             │   └── pack-abc123....idx
   no cross-object compression                │
   exploited at all.                          Much smaller total size — deltas
                                              between similar successive
                                              versions are tiny compared to
                                              storing each version in full.
```

## 5. Delta Compression — How It Actually Works

**Plain language:** instead of storing "version 2 of this file, in full," Git stores "here's how to turn version 1 into version 2" — a much smaller set of instructions, when the two versions are mostly similar.

**Precise mechanism:** Git's packing algorithm looks for objects with similar content (often by comparing objects of similar size and type, and using name/path similarity as a heuristic hint) and computes a compact binary diff between a chosen "base" object and each "delta" object referencing it. Reconstructing a delta object at read time means reading its base plus applying the delta instructions — a small amount of extra CPU work at read time in exchange for large storage savings.

> ⚠️ **Critical distinction to never blur (revisited from [§1](../Part1/Section-01-Part1-Version-Control-Fundamentals.md)'s delta-storage discussion and [§5](./Section-05-Part2-Object-Model.md)'s tree coverage):** this delta compression is a **physical, storage-layer** technique, completely invisible at the logical object-model layer covered in [§5](./Section-05-Part2-Object-Model.md). Logically, every commit still points to a **complete, full tree snapshot** — `git cat-file -p <tree>` always shows you the complete directory listing, never "here's what changed." Delta compression only describes how that logically-complete data happens to be _packed on disk_; it is never something you interact with directly, and it never changes what `git log`, `git diff`, or `git checkout` show you.

## 6. Garbage Collection (`git gc`)

### 6.1 What it actually does

`git gc` performs several related maintenance tasks in one operation:

1. **Repacks loose objects into packfiles** (as described above), including recompacting existing packs if beneficial.
2. **Prunes genuinely unreachable objects** — objects not referenced, directly or transitively, by any ref (branch, tag) _and_ not protected by the reflog's retention window (per [§6](./Section-06-Part2-References-Branches-HEAD-Tags-Reflog.md)'s safety-net discussion). This is where detached-HEAD commits you abandoned, or old commits replaced by `amend`/`rebase`, are eventually actually deleted from disk.
3. **Packs refs** into the single `packed-refs` file (per [§6](./Section-06-Part2-References-Branches-HEAD-Tags-Reflog.md)'s refs-architecture diagram) for faster bulk ref resolution when there are many refs.
4. **Removes stale/expired reflog entries** past the configured retention window.

### 6.2 When it runs

Git runs `gc` **automatically** in the background after operations that accumulate enough loose objects (a configurable threshold, `gc.auto`, defaulting to a few thousand loose objects — verify the exact current default against your Git version's documentation, since this has been tuned across releases). You can also invoke it manually.

```bash
$ git gc                    # standard maintenance
$ git gc --aggressive        # more thorough, slower repacking — rarely necessary
$ git count-objects -v       # inspect current loose object count before/after
```

### 6.3 The safety relationship with the reflog

`gc` will **not** prune an object that's still within the reflog's retention window, even if no branch or tag currently references it — this is precisely the safety mechanism that makes "recover a lost commit via reflog" (per [§6](./Section-06-Part2-References-Branches-HEAD-Tags-Reflog.md)'s recovery walkthrough) actually work in practice: the object survives specifically _because_ gc respects reflog entries as a form of reachability, until those entries themselves expire.

```
Object reachability for gc purposes:

  Reachable from a branch/tag  →  NEVER pruned (this is "real" history)
  Unreachable from any ref,
    but referenced in reflog
    within retention window   →  KEPT (this is your safety net)
  Unreachable from any ref,
    AND reflog entry expired  →  ELIGIBLE FOR PRUNING by gc
```

## 7. Commands (Full Documentation per [§9](../Part3/Section-09-Part3-Creating-Cloning-Repositories.md) Template)

### `git gc`

- **Purpose:** perform routine repository maintenance — repacking loose objects, pruning genuinely unreachable objects past their reflog retention window, and compacting refs.
- **Syntax:** `git gc [--aggressive] [--auto] [--prune=<date>]`
- **Key options:**
  - `--auto` — only run if Git's internal heuristics determine enough loose objects have accumulated to make it worthwhile (this is what runs silently in the background after normal operations).
  - `--aggressive` — spend significantly more CPU time finding optimal delta relationships; produces marginally smaller packs but is rarely necessary for typical repositories and can be slow on very large ones.
  - `--prune=<date>` — override the default grace period for pruning unreachable loose objects (default grace period exists specifically to avoid a race condition with concurrent operations; verify the current default against documentation).
- **Practical example:**

  ```bash
  $ git count-objects -v
  count: 3421
  size: 15234
  in-pack: 0
  packs: 0

  $ git gc
  Enumerating objects: 3421, done.
  Counting objects: 100% (3421/3421), done.
  Delta compression using up to 8 threads
  Compressing objects: 100% (1205/1205), done.
  Writing objects: 100% (3421/3421), done.

  $ git count-objects -v
  count: 0
  size: 0
  in-pack: 3421
  packs: 1
  ```

  Expected outcome: loose object count drops to (near) zero, replaced by objects consolidated into one or more packfiles — a direct, visible demonstration of the loose-objects-vs-packfiles diagram above.

- **Production usage:** typically left to run automatically; explicitly invoked as part of scheduled repository maintenance jobs on self-hosted Git servers, or after operations known to generate large numbers of loose objects (e.g., a large history rewrite via `filter-repo`, [§31](../Part8/Section-31-Part8-Advanced-Tooling.md)).
- **Common errors:** `warning: There are too many unreachable loose objects; run 'git prune' to remove them` — informational, not an error; indicates gc's automatic pruning threshold hasn't triggered yet.
- **Security impact:** `gc` pruning objects is actually security-_relevant_ in a good way for secret remediation — it's the step that actually frees disk space after history has been rewritten to remove a leaked secret ([§28](../Part7/Section-28-Part7-Security.md)), though the reflog must also be cleared/expired first for the secret to be fully gone locally.
- **Performance impact:** `gc` itself can be CPU- and I/O-intensive on very large repositories (potentially minutes on huge monorepos); this is why it typically runs automatically in the background rather than blocking your commands, and why enterprises with very large repos schedule it deliberately during low-usage windows rather than relying purely on automatic triggers ([§29](../Part7/Section-29-Part7-Maintenance-Performance-Troubleshooting.md)).

### `git count-objects`

- **Purpose:** report how many loose objects currently exist and their total size, plus packfile statistics — the primary diagnostic tool for understanding current repository storage state.
- **Syntax:** `git count-objects [-v]`
- **Key options:** `-v` (verbose) adds packfile counts and sizes to the basic loose-object count.
- **Practical example:** shown above in the `git gc` walkthrough — `count` and `size` reflect loose objects specifically; `in-pack` and `packs` reflect the packed state.
- **Production usage:** used in repository health monitoring/dashboards for self-hosted Git infrastructure, and as a quick manual check before deciding whether manual `gc` is worthwhile.
- **Common errors:** none typical; purely informational.
- **Security impact:** none.
- **Performance impact:** negligible; this is a fast metadata read, not a full repository scan.

### `git prune`

- **Purpose:** a narrower operation than full `gc` — specifically removes unreachable loose objects past their grace period, without necessarily repacking everything.
- **Syntax:** `git prune [--expire=<time>]`
- **Key options:** `--expire=<time>` controls the grace period before an unreachable object becomes eligible for removal (default exists to avoid races with concurrent operations that might be about to reference a new object).
- **Practical example:**
  ```bash
  $ git prune --dry-run   # shows what WOULD be removed, without removing anything
  ```
- **Production usage:** occasionally run directly (rather than via full `gc`) when specifically trying to reclaim space after a known history rewrite, without paying the cost of a full repack.
- **Common errors:** running `prune` without understanding the reflog relationship can lead to confusion about why an "unreachable" object wasn't actually removed — check reflog retention first.
- **Security impact:** as with `gc`, relevant to actually completing secret-remediation cleanup ([§28](../Part7/Section-28-Part7-Security.md)).
- **Performance impact:** generally lighter than a full `gc` since it skips the repacking step.

## 8. Hands-On Example — Watching Loose Objects Become a Packfile

```bash
$ mkdir gcdemo && cd gcdemo && git init -q

# Generate a reasonable number of loose objects via several commits
$ for i in $(seq 1 20); do
    echo "line $i" >> file.txt
    git add file.txt
    git commit -q -m "commit $i"
  done

$ git count-objects -v
count: 40
size: 1200
in-pack: 0
packs: 0

$ git gc
Enumerating objects: 40, done.
Counting objects: 100% (40/40), done.
Delta compression using up to 8 threads
Compressing objects: 100% (20/20), done.
Writing objects: 100% (40/40), done.
Total 40 (delta 15), reused 0 (delta 0), pack-reused 0

$ git count-objects -v
count: 0
size: 0
in-pack: 40
packs: 1

$ ls .git/objects/pack/
pack-<hash>.idx
pack-<hash>.pack
```

Note the `Total 40 (delta 15)` line: 15 of the 40 objects were stored as deltas against similar objects (the 20 nearly-identical successive versions of `file.txt`'s blob compress extremely well against each other), directly demonstrating the space savings described in the delta-compression section above.

## 9. Production & Enterprise Usage

- **Self-hosted Git server maintenance:** enterprises running GitLab, Gitea, or bare Git servers typically schedule periodic `git gc`/repack jobs across all hosted repositories during low-traffic windows, since automatic per-operation `gc.auto` triggers may not aggressively optimize very large or very active repositories without administrator tuning.
- **Repository size monitoring:** platform/infrastructure teams often track packfile size growth over time as a repository health metric, using it to decide when techniques like history filtering ([§31](../Part8/Section-31-Part8-Advanced-Tooling.md)), Git LFS migration for binaries ([§26](../Part6/Section-26-Part6-Scaling-Git.md)), or splitting a monorepo become worthwhile.
- **CI/CD clone performance:** because clones transfer packfiles (not loose objects), CI system performance is directly affected by how well a repository is packed — a poorly-maintained repository (many loose objects, fragmented packs) can measurably slow down CI checkout times at scale, motivating shallow clones (`--depth`) and partial clone techniques covered in [§26](../Part6/Section-26-Part6-Scaling-Git.md).

## 10. Security Considerations

- **Secret remediation is incomplete without gc.** Rewriting history to remove a leaked secret (via `filter-repo` or similar, [§28](../Part7/Section-28-Part7-Security.md), [§31](../Part8/Section-31-Part8-Advanced-Tooling.md)) only detaches the secret from reachable refs — the actual object with the secret's content still exists as a loose (or already-packed) object until `git gc --prune=now` (or equivalent) actually removes it, and even then, remote copies, forks, and other clones are entirely unaffected and must be separately addressed. This is one of the most commonly mishandled aspects of secret-leak incident response.
- **Packfiles themselves carry no additional security properties** beyond what loose objects already have (per [§5](./Section-05-Part2-Object-Model.md)'s security considerations) — packing is purely a size/performance optimization, not an encryption or access-control mechanism.

## 11. Performance Considerations

- Packed repositories are dramatically smaller on disk and faster to clone/fetch than the equivalent loose-object repository, due to both delta compression and reduced per-object filesystem overhead.
- Reading a delta-compressed object requires reconstructing it from its base at access time — a small CPU cost traded for large storage/network savings; Git optimizes this by keeping delta chains reasonably short and by caching recently reconstructed objects, but pathologically long delta chains (rare, generally only with unusual repack configurations) can measurably slow down access to specific objects.
- `git gc --aggressive` trades significantly more CPU time for marginally better compression — appropriate occasionally for a repository nearing a major milestone (e.g., before a large public release or migration) but not as routine practice, since ordinary `gc` already achieves the great majority of the available benefit.

## 12. Monitoring

- `git count-objects -v` is the primary lightweight health-check command; a persistently high loose-object count across normal operation suggests `gc.auto` isn't triggering appropriately (worth checking `gc.auto`'s configured threshold) or that manual scheduled maintenance is warranted.
- Repository size growth over time (via hosting-platform dashboards, or periodic `du -sh .git`) is a useful longer-term monitoring signal feeding into decisions covered in [§26](../Part6/Section-26-Part6-Scaling-Git.md) and [§29](../Part7/Section-29-Part7-Maintenance-Performance-Troubleshooting.md).

## 13. Troubleshooting

| Symptom                                                    | Likely cause                                                                 | Fix                                                                                                                                                                                                                                       |
| ---------------------------------------------------------- | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Repository `.git` directory unexpectedly large             | Many loose objects not yet packed, or genuinely large history/binary content | Run `git count-objects -v` and `git gc` first; if still large, investigate large blobs ([§26](../Part6/Section-26-Part6-Scaling-Git.md), [§29](../Part7/Section-29-Part7-Maintenance-Performance-Troubleshooting.md)) or consider Git LFS |
| `warning: There are too many unreachable loose objects`    | Objects past the gc auto-pack threshold but not yet cleaned                  | Run `git gc` manually, or wait for the next automatic trigger                                                                                                                                                                             |
| Secret still recoverable from `.git` after history rewrite | Old objects not yet pruned, or reflog still referencing them                 | Run `git reflog expire --expire=now --all` followed by `git gc --prune=now`; remember this only affects the local clone — remote copies need separate remediation ([§28](../Part7/Section-28-Part7-Security.md))                          |
| `git gc` unexpectedly slow on a very large repository      | Large object count/history depth, or `--aggressive` used unnecessarily       | Schedule gc during low-usage windows; avoid `--aggressive` for routine maintenance                                                                                                                                                        |

## 14. Best Practices

- Let automatic `gc.auto` handle routine maintenance for typical repositories; only invoke `git gc` manually after unusual events (large history rewrites, bulk imports) or as part of deliberate scheduled maintenance on self-hosted infrastructure.
- When remediating a leaked secret, always follow the history rewrite with reflog expiry and `git gc --prune=now` locally, and treat remote repository cleanup, forks, and CI caches as separate, equally necessary steps ([§28](../Part7/Section-28-Part7-Security.md)).
- Monitor `.git` directory size and loose object counts periodically on any self-hosted, high-activity repository rather than assuming defaults scale indefinitely without attention.

## 15. Anti-Patterns & Common Mistakes

- **Anti-pattern:** assuming a history rewrite alone (e.g., `filter-repo` to strip a secret) has removed the sensitive data from the local repository — without also expiring the reflog and running `gc --prune=now`, the object frequently still exists on disk and is retrievable by anyone with local access.
- **Common mistake:** running `git gc --aggressive` routinely "just to be safe," when ordinary automatic `gc` already captures nearly all the practical benefit — the aggressive mode's extra CPU cost is rarely justified for typical workflows.

## 16. Interview Questions

**[Beginner] Q1. What is the difference between a loose object and a packed object in Git?**
**Model answer:** A loose object is stored as its own individual compressed file under `.git/objects`, named directly by its hash — this is the form every new object takes immediately after being created by commands like `git add` or `git commit`. A packed object lives inside a packfile, a single binary file that consolidates many objects together, often storing similar objects as small deltas against a shared base rather than each in full. Both forms represent exactly the same logical objects — blobs, trees, commits, tags — the difference is purely how they're physically stored on disk, and it never changes what those objects logically contain or how commands like `git log` or `git diff` behave.

**[Intermediate] Q2. Explain how delta compression in packfiles differs from Git supposedly "storing diffs" as commits.**
**Model answer:** These are two completely different layers and it's a common point of confusion. Logically, every commit points to a complete, full snapshot of the project tree — nothing about a commit's logical content is a diff, and `git cat-file -p` on any tree always shows the full directory listing. Delta compression is a separate, physical storage-layer optimization that happens only inside packfiles: when Git repacks objects (via `git gc`), it looks for similar objects — typically successive versions of the same file's blob across commits — and stores most of them as small deltas against one chosen full base object, purely to save disk space and network bandwidth. This is entirely invisible above the storage layer; if you retrieve any object, Git transparently reconstructs its full content by applying the delta to its base, and every higher-level Git command sees complete, non-delta content.

**[Senior] Q3. Why doesn't `git gc` immediately delete a commit the moment no branch or tag points to it anymore?**
**Model answer:** Because the reflog still remembers that ref position for a configurable retention window, and Git deliberately treats reflog entries as a form of reachability for garbage collection purposes. This is the concrete mechanism behind being able to recover from mistakes like an accidental `reset --hard` or an abandoned detached-HEAD commit — the object is technically unreferenced by any current branch or tag, but as long as a reflog entry still points to it within the retention window, `git gc` will not prune it. Only once the corresponding reflog entries expire, typically after 30 to 90 days depending on the specific reflog expiry settings, does the object become eligible for actual removal on the next garbage collection run.

**[Architect] Q4. Your security team asks you to confirm that a leaked API key, committed six months ago and then removed via a history rewrite last week, is now fully gone from the repository. How do you verify this properly?**
**Model answer:** I'd break this into layers rather than giving a single yes/no. First, locally: a history rewrite like `filter-repo` only detaches the secret from currently reachable branches and tags — the original commit object containing the secret can still exist as a loose or packed object, and can still be referenced by reflog entries, until I explicitly run `git reflog expire --expire=now --all` followed by `git gc --prune=now` to actually remove it from this local repository's object database; I'd verify with `git cat-file -p <old-hash>` failing after that. Second, and just as critical: the remote repository, any forks, any other developers' local clones, and any CI/CD caches or artifact stores that may have fetched that commit before the rewrite are entirely separate copies and are completely unaffected by anything done to my local repository — each of those needs its own remediation, which typically means force-pushing the rewritten history to the remote with old refs removed, invalidating CI caches, and, critically, actually rotating the leaked credential itself, since a determined attacker may already have a copy of the old history regardless of any cleanup. I'd tell the security team that the safest assumption is that the credential must be treated as compromised and rotated, independent of how thoroughly the repository is cleaned.

## 17. Common Misconceptions

1. **"Delta compression means commits store diffs."** Delta compression is a storage-layer optimization inside packfiles only; every commit's logical content remains a complete, full tree snapshot at the object-model layer ([§5](./Section-05-Part2-Object-Model.md)).
2. **"`git gc` immediately deletes anything not currently referenced by a branch."** The reflog's retention window protects recently-unreferenced objects from immediate deletion — this delay is deliberate and is exactly what makes local recovery from mistakes possible.
3. **"Rewriting history removes a leaked secret from the repository."** It only detaches the secret from reachable history; the object still exists locally until reflog expiry and `gc --prune=now`, and remote copies/forks/clones are entirely unaffected and need separate handling.
4. **"Packing is a rarely-relevant internal detail I'll never need to know."** Understanding it directly explains observed behavior — why clones transfer quickly despite huge history, why `.git` directory size sometimes drops sharply after `gc`, and why secret remediation requires more than a single history-rewriting command.

## 18. 🔑 Key Takeaways

- Git objects exist physically as either loose objects (one file per object) or consolidated into packfiles with delta compression between similar objects — a purely physical storage optimization that never changes the logical object model from [§5](./Section-05-Part2-Object-Model.md).
- `git gc` repacks loose objects into packfiles, prunes genuinely unreachable objects (respecting the reflog's retention window), and compacts refs — running automatically in the background and manually invocable.
- The reflog protects recently-unreferenced objects from immediate garbage collection, which is the underlying mechanism that makes local mistake-recovery ([§6](./Section-06-Part2-References-Branches-HEAD-Tags-Reflog.md)) actually work.
- Secret remediation requires more than rewriting history: local reflog expiry plus `gc --prune=now`, remote repository cleanup, and credential rotation are all separately necessary.
- `git count-objects -v` and `git gc` are the primary diagnostic and maintenance tools for this storage layer.

## 19. Related Concepts & What's Next

This completes Part 2 — Architecture & Internals. Every mechanism taught from here forward (staging, committing, branching, merging, rebasing, remotes) now has a solid physical and logical foundation underneath it. Part 3 begins with Section 8: installing Git and understanding `git config` in full depth — the first genuinely hands-on, command-driven section, and the direct prerequisite for the daily workflow commands (`status`, `add`, `commit`, `diff`, `log`) taught in Sections 9–10.
