# Section 32 (Part 8): Git's Evolution — Version Differences, Deprecated Features, SHA-256; Git vs SVN vs Mercurial vs Perforce

## 32.1 Definition

**Plain language:** Git in 2026 is not the Git of 2005, or even of 2015. Defaults have changed, commands have been split for clarity, the underlying hash algorithm is in a slow, deliberate transition, and the surrounding ecosystem of rival tools has both consolidated and specialized. Knowing this evolution matters for reading old scripts, understanding why current defaults are what they are, and answering "how does Git compare" honestly.

**Precise:** This section covers three things: (1) concrete version-era changes to Git's defaults and command surface, (2) the SHA-1-to-SHA-256 transition in full, building on the preview in §5.4, and (3) a comparative analysis of Git against the other version control systems introduced in §1 — SVN, Mercurial, and Perforce — as they stand today, not merely as historical footnotes.

## 32.2 Why This Matters

Interviewers and real work both reward knowing that Git's current behavior is the product of deliberate, dated changes, not eternal fixed truths. Reading a five-year-old blog post, a decade-old Stack Overflow answer, or an inherited CI script requires recognizing which parts reflect defaults that have since changed. And "why doesn't your team just migrate off SVN/Perforce" is a real question with a real, non-dismissive answer, not an assumed conclusion.

## 32.3 The `master` → `main` Default Branch Rename

### 32.3.1 What changed

Historically, `git init` created a default branch named `master`. Starting around 2020, in the context of broader industry conversations about non-inclusive terminology in technology, GitHub, GitLab, and other major hosting platforms changed their **platform-side default** for newly created repositories to `main`. Git itself followed by making the default configurable and, later, `init.defaultBranch` a first-class setting rather than a hardcoded value.

```bash
# Purpose: set your own default branch name for all future `git init` calls
$ git config --global init.defaultBranch main
```

> ⚠️ **Critical clarification:** Git core never hardcoded `master` as something un-overridable, and it did not silently rename branches in **existing** repositories — the change affects the name used for **newly initialized** repositories going forward, and is driven substantially by hosting-platform defaults as much as by Git itself. Existing repositories with a `master` branch continue to work exactly as before; renaming an existing repository's default branch is a deliberate, manual action (`git branch -m master main`, plus updating the remote's default branch and any CI/scripts referencing the old name).

### 32.3.2 Practical consequence for reading old material

Any script, CI config, or tutorial predating roughly 2020-2021 that hardcodes `master` as "the" default branch name reflects the prior universal convention, not a mistake — treat it as period-accurate rather than wrong.

## 32.4 `git switch` and `git restore` — The Historical Why

§12.6 and §15.3 already covered the mechanics: Git 2.23 (2019) split the two historically unrelated jobs `git checkout` performed — switching branches, and restoring files from the index or a commit — into two narrower, single-purpose commands. Worth adding here, from a version-history lens:

- This was a **long-recognized** usability problem, not a sudden discovery — `checkout`'s dual role had been a known source of confusion (and occasional real mistakes, like discarding uncommitted file changes when a user meant to switch branches, or vice versa) for years before the split shipped.
- `checkout` was deliberately **not removed or deprecated** — a design choice consistent with Git's broader backward-compatibility discipline: existing scripts, muscle memory, and a decade-plus of tutorials all continue to work unchanged.
- The split is a useful marker for dating material: any doc or script written before 2019 will use `checkout` exclusively for both jobs, because `switch`/`restore` did not yet exist.

## 32.5 Default Merge Strategy: `recursive` → `ort`

Git's default three-way merge strategy for regular merges (§13) was historically `recursive`. Git 2.33 (2021) switched the default to **`ort`** ("ostensibly recursive's twin"), a from-scratch reimplementation designed to be faster (particularly on merges involving many renames) and to fix a class of correctness edge cases the older `recursive` strategy handled inconsistently, especially around criss-cross merges and rename detection.

> 💡 **Tip:** For nearly all everyday merges the change is invisible — `ort` produces the same result `recursive` would in the common case. It matters concretely in two situations: performance on merge-heavy histories with extensive file renames, and specific edge cases around conflicting renames where `ort`'s handling is more correct. You can still explicitly request the older strategy (`git merge -s recursive`) if you ever need to reproduce historical behavior exactly.

## 32.6 The SHA-1 to SHA-256 Transition, in Full

### 32.6.1 Why SHA-1 is a problem at all

§5.4 flagged this; here is the complete picture. SHA-1 produces a 160-bit hash, and it has known **theoretical and, since 2017, practically demonstrated** collision weaknesses: the "SHAttered" research published by Google and CWI Amsterdam in 2017 produced two different PDF files with an identical SHA-1 hash, proving that a well-resourced attacker can, in principle, construct two different pieces of content that hash identically — a **collision**. This is not a Git-specific vulnerability; it's a property of the SHA-1 algorithm itself, used across many systems well beyond Git.

For Git specifically, a collision would in theory let an attacker substitute a malicious object for a legitimate one that shares the same hash, defeating the tamper-evidence property established in §2.4.4 and §5. In practice this is an extremely high-effort, targeted attack, not a casual risk — but "extremely high-effort today" is not the same guarantee as "structurally impossible," which is precisely the standard a cryptographic integrity mechanism should meet.

### 32.6.2 Git's interim mitigation: `sha1dc`

Rather than an immediate wholesale algorithm change (which would break compatibility with essentially every existing Git repository, tool, and hosting platform overnight), Git adopted **`sha1dc`** — a hardened SHA-1 implementation specifically engineered to detect the structural patterns characteristic of known collision-attack constructions (like the one used in SHAttered) and refuse to accept an object matching them. This is the mitigation already running in the Git you use today; it does not eliminate SHA-1's theoretical weakness, but it closes the specific, currently-known practical attack technique.

### 32.6.3 The SHA-256 repository format

Git supports an **opt-in repository format using SHA-256** (256-bit digests) instead of SHA-1, offering a much larger security margin against collision attacks. Key facts about this transition, stated at the appropriate level of confidence:

- It is opt-in at repository creation time, not a retroactive change to existing repositories.
- SHA-1 repositories and SHA-256 repositories are, as of this writing, **not natively interoperable** — you cannot directly push/pull/fetch between a SHA-1 repository and a SHA-256 repository without an explicit conversion step, because every object's identity (and therefore every hash-based reference throughout the object graph, per §5.6) is computed differently under the two algorithms.
- Ecosystem support (major hosting platforms, third-party tooling, CI systems) for SHA-256 repositories has historically lagged behind core Git's own support, which has been the practical bottleneck slowing real-world adoption more than any technical blocker in Git itself.

> ⚠️ **Version-specific note, flagged per accuracy rules:** this is an actively evolving area. The high-level facts above (SHA-1's known weakness, the `sha1dc` mitigation already in production use, and an opt-in, not-yet-fully-interoperable SHA-256 format) are stable and safe to state confidently. The exact current state of hosting-platform support, tooling compatibility, and any timeline toward SHA-256 becoming a practical default should be verified against current Git and platform documentation before being stated as a specific fact in a real decision — this is precisely the kind of detail that changes between when this material is written and when it's read.

### 32.6.4 Interview framing

A strong answer distinguishes three separate claims that are easy to conflate: (1) SHA-1 has a demonstrated theoretical weakness (true, and important to know), (2) Git's production SHA-1 usage today is meaningfully hardened against the specific known attack technique via `sha1dc` (true, and the reason this isn't an active five-alarm crisis), and (3) SHA-256 is available as a forward-looking, opt-in option with real current interoperability limitations (true, and the reason "just switch everyone to SHA-256" isn't yet a simple recommendation).

## 32.7 Git vs SVN vs Mercurial vs Perforce — Where Things Stand Today

This extends the Generation 2/3 comparison from §1.5–§1.8 with a today-focused lens.

| Dimension                                | Git                                                                                   | SVN                                                                       | Mercurial                                                                                                                              | Perforce (Helix Core)                                                                                      |
| ---------------------------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Architecture                             | Distributed                                                                           | Centralized                                                               | Distributed                                                                                                                            | Centralized                                                                                                |
| Revision identity                        | Content hash (SHA-1, moving toward SHA-256)                                           | Sequential global revision number                                         | Content hash (different internal scheme, same DAG philosophy)                                                                          | Sequential changelist number                                                                               |
| Core data model                          | Content-addressed snapshot Merkle DAG (§5)                                            | Linear revision history per repository                                    | DAG of changesets, conceptually close to Git's but with different internal storage and a historically more consistent CLI              | Depot tree + changelists; strong native support for exclusive file locking                                 |
| Large binary handling                    | Weak natively; mitigated by Git LFS (§26)                                             | Workable; still a single server-side store                                | Weak natively, similar to Git; Meta's internal Sapling/EdenFS work addresses this at their scale                                       | Excellent — the primary reason it remains dominant for huge binary-heavy repositories                      |
| Where it still sees real-world use today | The default nearly everywhere: open source, startups, enterprise software engineering | Legacy enterprise estates; some teams that never migrated by choice       | Deliberately retained/extended internally at Meta (via Sapling); a smaller population of teams that value its historically cleaner CLI | Game development, film/VFX, and other asset-heavy pipelines with huge binaries and a need for file locking |
| Branching cost                           | Trivial, instant (§1.7)                                                               | Historically discouraging, though improved since SVN 1.5's merge tracking | Trivial, instant — comparable to Git                                                                                                   | System-dependent; workable but not the tool's primary strength                                             |
| Typical adoption driver today            | Ecosystem gravity (GitHub/GitLab), tooling ubiquity, hiring-pipeline default          | Inertia — migrating a mature enterprise history off SVN is nontrivial     | Deliberate technical choice for very large monorepos with heavy internal investment (Meta)                                             | Deliberate technical choice for large binary asset pipelines, not inertia                                  |

### 32.7.1 Mercurial's data model, a bit more precisely

Mercurial is often described as "Git's sibling" because both are distributed VCS created the same month (§2.7) with broadly comparable capabilities: local commits, cheap branching, full-history clones. The genuine differences are in the details, not the philosophy: Mercurial's internal storage and revision-addressing mechanisms differ from Git's object model, and Mercurial deliberately prioritized a more consistent, smaller command surface from the start rather than exposing Git's lower-level "plumbing" commands (§2.4.2) to everyday users. Functionally, for most day-to-day developer workflows, the two systems solve the same problems in recognizably similar ways.

### 32.7.2 Perforce's continued dominance in specific niches

Perforce's changelist/depot model is architecturally centralized, which §1 already identified as the "wrong" answer for source code collaboration at scale — but for **huge binary-heavy repositories** (game engines, film and VFX asset pipelines, hardware design files), the calculus is different: files are large, frequently un-mergeable by nature (a texture, a compiled asset, a CAD file), and a team benefits far more from Perforce's fast handling of huge repositories and its native, robust file-locking than from Git's distributed model, which offers little value when files can't meaningfully be merged in the first place. This is the same conclusion §1.10 Q4 reached from the theoretical side; it remains true in practice today.

## 32.8 Deprecated and Legacy Features Worth Recognizing

These aren't things to use in new work, but recognizing them is essential for reading older scripts, tutorials, and inherited automation:

| Feature                                                                           | Status                                           | What to know                                                                                                                                                                 |
| --------------------------------------------------------------------------------- | ------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `git checkout` (overloaded dual-purpose usage)                                    | Not deprecated, but superseded in recommendation | Still fully functional for both switching branches and restoring files; `switch`/`restore` (Git 2.23+, §12.6, §15.3) are the modern, narrower recommendation for new scripts |
| `git filter-branch`                                                               | Officially discouraged                           | Still present in Git, but the project itself recommends `git filter-repo` (§31.7) for any real history-rewriting task, citing performance and correctness concerns           |
| `recursive` merge strategy as default                                             | Superseded as the default                        | Still available via `git merge -s recursive`; `ort` (§32.5) is the default since Git 2.33                                                                                    |
| `master` as the universal default branch name                                     | Superseded as the platform/tooling default       | Existing repositories using `master` are entirely unaffected; only the default for **new** repositories changed                                                              |
| Global `.gitattributes`/`.gitignore` conventions predating standardized templates | Not deprecated, just less standardized           | Older repos may show ad hoc ignore patterns predating widely shared community templates (§11)                                                                                |

## 32.9 Interview Questions

**[Beginner] Q1. Why did the default branch name change from `master` to `main`?**
**Model answer:** Starting around 2020, major hosting platforms like GitHub and GitLab changed the default branch name used for newly created repositories from `master` to `main`, as part of a broader industry move away from non-inclusive terminology. Git itself made the default branch name configurable via `init.defaultBranch` rather than hardcoding it. It's important to be precise about scope: this only affects the default used for new repositories going forward — existing repositories with a `master` branch are completely unaffected and continue working exactly as before; renaming an existing repository's default branch is a separate, deliberate action a team takes on its own.

**[Intermediate] Q2. What is SHAttered, and how has Git responded to it?**
**Model answer:** SHAttered was 2017 research (by Google and CWI Amsterdam) that practically demonstrated a SHA-1 collision — two different files engineered to produce the identical SHA-1 hash — proving a known theoretical weakness in SHA-1 was practically exploitable, at least by a well-resourced attacker. This matters for Git because object identity is exactly what a hash collision would undermine. Git's response was layered: first, a hardened SHA-1 implementation called `sha1dc`, which detects the structural signature of known collision-attack constructions like the one SHAttered used and refuses to accept a matching object — this is already running in production Git today and is the main reason this isn't an active emergency. Second, longer-term, Git added an opt-in repository format using SHA-256 instead, offering a much larger security margin, though SHA-1 and SHA-256 repositories can't yet natively interoperate, and I'd want to verify the current state of ecosystem-wide support before calling it a mature, drop-in replacement.

**[Intermediate] Q3. `git checkout` still exists and works. Why did Git introduce `switch` and `restore` instead of just fixing `checkout`?**
**Model answer:** `checkout` historically did two conceptually unrelated jobs — switching which branch HEAD points to, and restoring individual files' content from the index or a specific commit — disambiguated only by argument shape and, in the file-restoring case, a `--` separator. This overloading was a long-standing, well-recognized source of real mistakes: a stray or missing `--`, or a filename that happened to match a branch name, could make Git do something different from what the user intended. Rather than "fixing" `checkout` by changing its existing behavior (which would break enormous amounts of existing scripts and muscle memory), Git 2.23 added two new, narrower, single-purpose commands and left `checkout` fully intact and unremoved — consistent with Git's general discipline of not breaking backward compatibility. `switch`/`restore` are the recommended default for new work; `checkout` remains essential reading-comprehension for the huge body of existing material that predates 2019.

**[Senior] Q4. A hardware design team wants your recommendation: stay on Perforce, or migrate to Git? Their repository is 4 TB of CAD files with heavy binary churn, edited by 40 engineers.**
**Model answer:** I'd recommend staying on Perforce, and explain precisely why, rather than defaulting to "Git is the industry standard." The core mismatch is that Git's entire value proposition — cheap distributed branching and automatic content-based merging — assumes content that can be meaningfully diffed and merged; CAD binaries generally can't be. Under Git's model, every clone would need the full 4 TB history by default (mitigable with partial clone/LFS, but that adds real operational complexity, §26), and without native file locking, two engineers editing the same binary asset in parallel risk producing genuinely unreconcilable, silently conflicting work — exactly the lost-update problem version control exists to prevent (§1.2), which Git's merge model doesn't solve for un-mergeable content. Perforce's changelist/depot model handles huge binary repositories efficiently and provides robust, native exclusive locking specifically so two people never waste effort on the same unmergeable asset. If there's a genuine driver toward Git (e.g., unifying tooling with a software team that already lives in Git), I'd scope a hybrid: keep the binary-heavy CAD assets in Perforce or a Git-LFS-backed store with locking enabled, and only migrate genuinely text-based, mergeable artifacts. Recommending a wholesale Git migration here on "everyone uses Git" grounds alone, without addressing the locking and binary-scale mismatch, would be a mistake regardless of Git's general dominance elsewhere.

**[Architect] Q5. Your organization has a decade of history in SVN and is evaluating a migration to Git. What technical and organizational factors actually determine whether this is worth doing?**
**Model answer:** Technically: repository size and binary content (large binaries make a naive full-history Git clone painful, requiring LFS or partial clone strategies, §26); whether the team currently relies on SVN-specific features like fine-grained per-directory permissions or partial checkouts of a subtree, both of which are naturally weaker in core Git and need a deliberate replacement plan (sparse-checkout, or platform-level access control, §23); and the sheer mechanical cost of the migration itself — tools exist to convert SVN history into Git commits, but very old or heavily-branched SVN histories (where SVN's directory-based branch model doesn't map cleanly onto Git's ref model) can produce messy, imperfect conversions that need manual cleanup, and this is where I'd point to current migration-tooling documentation rather than assume a clean one-command conversion. Organizationally: the real cost is retraining muscle memory and CI/CD tooling built around SVN's centralized, sequential-revision-number workflow, and the migration is worth it primarily when the team is already paying real costs from SVN's limitations — slow branching discouraging experimentation, painful merges, lack of true offline work — rather than migrating for its own sake. I'd frame the decision as: quantify the current SVN pain concretely, quantify the one-time migration and retraining cost, and only recommend migrating if the former clearly outweighs the latter over a realistic time horizon — "Git is more modern" alone is not a sufficient business case.

## 32.10 Common Misconceptions

1. **"Git renamed all `master` branches to `main`."** Git changed the default for **new** repositories; it never touched existing repositories' branch names.
2. **"`checkout` is deprecated."** It remains fully functional for both of its historical jobs; `switch`/`restore` are the newer, narrower recommendation, not a replacement that removes `checkout`.
3. **"Git has already fully switched to SHA-256."** SHA-256 is an opt-in repository format with real current interoperability limitations against SHA-1 repositories; SHA-1 (hardened via `sha1dc`) remains what the overwhelming majority of real-world Git repositories use today.
4. **"SVN, Mercurial, and Perforce are all just obsolete."** Each has a real, current, technically justified niche: SVN in legacy enterprise estates, Mercurial in Meta's large-scale internal tooling lineage, and Perforce as the still-dominant choice for huge binary-heavy repositories like game and film asset pipelines.
5. **"SHAttered means Git commits can be silently forged today."** Git's production SHA-1 usage is hardened via `sha1dc` specifically against the SHAttered-style attack technique; the underlying algorithm's theoretical weakness is real and is why SHA-256 exists as a forward path, but it is not an active, trivially exploitable vulnerability in ordinary Git usage today.

## 32.11 🔑 Key Takeaways

- Git's defaults have changed materially over time: `master`→`main` (platform/tooling default, not a retroactive rename), `checkout` split into `switch`/`restore` (2019, `checkout` not removed), and `recursive`→`ort` as the default merge strategy (2021).
- SHA-1's known weakness (demonstrated by SHAttered, 2017) is mitigated in production Git today by the hardened `sha1dc` implementation; SHA-256 is an available, opt-in, forward-looking repository format with real current interoperability limits against SHA-1 repos — treat exact current rollout status as something to verify against live documentation.
- Git dominates general software development, but SVN (legacy enterprise), Mercurial (Meta's internal lineage), and Perforce (huge binary-heavy asset pipelines like games and film) each retain genuine, technically justified real-world usage today, not just historical footprint.
- Recognizing deprecated/legacy patterns (`filter-branch`, overloaded `checkout` usage, `recursive` as an explicit non-default choice) is essential for reading older scripts and documentation accurately.

## 32.12 Related Concepts & What's Next

This section closed the loop on how Git itself has changed and how it stacks up against its remaining rivals today. §33 consolidates the best practices and anti-patterns scattered across every prior section — commit hygiene, branching hygiene, history hygiene, security hygiene, and collaboration hygiene — into one synthesized reference, closing out Part 8's technical content before §34's interview-prep drills, §35's hands-on labs, and §36's final wrap-up.
