# Section 17 (Part 4): Cherry-Pick & Moving Changes Between Branches; Patch Files

## 1. Definition

**Plain language:** Cherry-picking takes one specific commit from anywhere in the repository and reapplies just that commit's changes onto your current branch — grabbing a single "cherry" out of another branch's history rather than merging or rebasing everything.

**Precise:** `git cherry-pick <commit>` computes the diff a given commit introduced (relative to its own parent) and applies that diff as a **new commit** on the current branch, with a new hash and a parent equal to whatever the current branch's tip already was. Patch files (`git format-patch`/`git apply`/`git am`) generalize the same underlying idea — extracting a diff and applying it elsewhere — but as portable files that can move entirely outside Git's own transport (§20), including over email.

## 2. Why It Exists / Problem It Solves

Merge (§13) and rebase (§14) both operate on **entire branches or ranges of commits**. Sometimes you want exactly one commit — a specific bugfix that needs to land on an older release branch, without dragging along everything else that's happened on the branch it originated from. Cherry-pick and patch files exist for this precise, narrower need: moving a deliberately chosen, specific unit of change from one place to another, independent of the surrounding history either side has accumulated.

## 3. `git cherry-pick` — Mechanics and Contrast

```bash
$ git switch release-2.4
$ git cherry-pick a1b2c3d
```

Expected output:

```
[release-2.4 9f2c1a4] Fix null pointer in cart total
 Date: Tue Jul 21 10:15:00 2026 +0530
 1 file changed, 3 insertions(+), 1 deletion(-)
```

```
Before:                                  After `git cherry-pick a1b2c3d`:

  main       C1 ──► C2 ──► a1b2c3d         main       C1 ──► C2 ──► a1b2c3d

  release-2.4  ──► R1 ──► R2               release-2.4  ──► R1 ──► R2 ──► 9f2c1a4
                                                                    (SAME diff, NEW hash,
                                                                     new parent R2)
```

|                   | Cherry-pick                                                 | Rebase (§14)                                               | Merge (§13)                                              |
| ----------------- | ----------------------------------------------------------- | ---------------------------------------------------------- | -------------------------------------------------------- |
| Scope             | One specific commit (or an explicit list/range)             | An entire sequence of commits since divergence             | Two branch tips, reconciled via their merge base         |
| Result            | One new commit on the target branch                         | Many new commits, replayed in original order               | Usually one new merge commit (or a fast-forward)         |
| Ancestry recorded | None — the new commit has no link back to the source branch | None — replayed commits abandon their original parents too | **Yes** — a merge commit explicitly records both parents |
| Typical intent    | "I want just this one change, deliberately, here"           | "I want my whole branch replayed cleanly elsewhere"        | "I want these two full lines of history reconciled"      |

```bash
# Purpose: cherry-pick a RANGE of commits (exclusive of the first, inclusive of the last)
$ git cherry-pick a1b2c3d^..7c2a9f1

# Purpose: stage the cherry-picked changes WITHOUT committing — lets you review/amend first
$ git cherry-pick -n a1b2c3d
# or: git cherry-pick --no-commit a1b2c3d

# Purpose: append a "(cherry picked from commit ...)" line to the new commit's message,
# preserving a traceable link back to the original — standard practice for backports
$ git cherry-pick -x a1b2c3d
```

Expected message with `-x`:

```
Fix null pointer in cart total

(cherry picked from commit a1b2c3d4e5f6789012345678901234567890abcd)
```

## 4. Cherry-Pick Conflicts

Because a cherry-pick applies a diff computed relative to the _original_ commit's parent onto a potentially very different target tip, conflicts are common when the surrounding code has diverged meaningfully.

```bash
$ git cherry-pick a1b2c3d
Auto-merging cart.js
CONFLICT (content): Merge conflict in cart.js
error: could not apply a1b2c3d... Fix null pointer in cart total
hint: after resolving the conflicts, mark the corrected paths
hint: with 'git add <paths>' or 'git rm <paths>'
hint: and commit the result with 'git commit'
```

```bash
# Resolve exactly as in §13.7-13.8, then:
$ git add cart.js
$ git cherry-pick --continue

# Or abandon this specific cherry-pick, restoring the pre-attempt state
$ git cherry-pick --abort

# Or, mid-multi-commit cherry-pick, skip just this one and move to the next
$ git cherry-pick --skip
```

## 5. When Cherry-Pick Is Right vs a Smell

**Legitimate uses:**

- **Backporting a fix** to an older, still-supported release branch (e.g., `release-2.4` needs the security fix that landed on `main`, without pulling in every unrelated feature `main` has also accumulated since).
- **Recovering a specific commit** that was made on the wrong branch — cherry-pick it onto the correct one, then optionally remove it from the wrong one (§15).
- **Hotfixes** that need to reach both a release branch and `main` independently, when a full merge between them isn't yet appropriate.

**A smell, not a pattern:**

- **Systematically cherry-picking instead of merging** between two long-lived branches that are actually meant to converge — e.g., manually cherry-picking every commit from `develop` into `main` one at a time, repeatedly, as a substitute for ever actually merging them. This duplicates commits (same content, different hashes, no recorded ancestry between the branches) at scale, makes `git log`/`git blame` history genuinely confusing (the "same" fix appears to have two independent, unrelated origins), and is exactly the kind of ad hoc process a real branching strategy (§22) is meant to replace with an explicit, disciplined convergence policy.

> ⚠️ **Common confusion to preempt:** a cherry-picked commit and its original share **identical content** (the same diff) but are **entirely different objects with different hashes** and no ancestry relationship Git can see automatically. If the same logical fix later needs to be merged normally between the two branches, Git has no inherent way to know "these are the same change" — it can still cause conflicts or, at best, a harmless no-op merge, depending on exact circumstances. `-x`'s "(cherry picked from...)" trailer is a human-readable breadcrumb for this exact ambiguity, not something Git's merge machinery itself understands structurally.

## 6. Patch Files — The Portable Alternative

A patch file captures a diff as a plain text file that can be emailed, attached to a ticket, or applied to a completely disconnected repository with no shared remote or network access at all.

### 6.1 `git format-patch` vs a plain `git diff`

```bash
# Purpose: produce ONE FILE PER COMMIT, formatted as a proper email/patch with
# full commit metadata (author, date, message) preserved
$ git format-patch -1 a1b2c3d
0001-Fix-null-pointer-in-cart-total.patch

# Purpose: produce patches for a range of commits, one file each
$ git format-patch main..feature-x
```

```bash
# Contrast: plain diff has NO commit metadata at all — just the content change
$ git diff HEAD~1 HEAD > plain.diff
```

|                               | `git diff > file`                                               | `git format-patch`                                                                                   |
| ----------------------------- | --------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| Content                       | Raw content diff only                                           | Content diff **plus** author, date, commit message, formatted as an email (`From`/`Subject` headers) |
| One file per commit           | No — a single combined diff regardless of commit count          | Yes — one `.patch` file per commit by default                                                        |
| Applying preserves authorship | No — whoever applies it becomes the sole author of a new commit | **Yes**, when applied with `git am` (17.6.3) — original author metadata is preserved                 |
| Typical use                   | Quick "here's what changed" sharing, code review snippets       | Formal patch submission, backporting across disconnected repos, mailing-list workflows               |

### 6.2 `git apply` — Content Only

```bash
# Purpose: apply a patch's CONTENT changes to the working directory,
# WITHOUT creating a commit and WITHOUT preserving author/message metadata
$ git apply 0001-Fix-null-pointer-in-cart-total.patch
```

`git apply` is the lower-level tool: it modifies the working directory (and, with `--index`, the index) to match the patch's content changes, but it never creates a commit itself and discards all of `format-patch`'s email-style metadata — you'd `git add` and `git commit` manually afterward, becoming the new commit's sole author regardless of who actually wrote the original change.

### 6.3 `git am` — Apply Mailbox, With Metadata

```bash
# Purpose: apply one or more format-patch files AS COMMITS, preserving the
# original author, date, and message exactly
$ git am 0001-Fix-null-pointer-in-cart-total.patch

# Purpose: apply an entire directory of sequentially numbered patches at once
$ git am 000*.patch
```

Expected output:

```
Applying: Fix null pointer in cart total
```

`git am` ("apply mailbox") is named for its origin: it parses patch files in the exact format an email client would produce for a `git format-patch` output, applies each one, and **commits it**, preserving the original author's name, email, and commit message precisely as recorded in the patch file — the committer becomes whoever runs `git am`, while the author remains whoever originally wrote it, exactly the author-vs-committer distinction §5.5.3 introduced.

```bash
# Purpose: if applying a patch produces a conflict
$ git am --continue    # after resolving and `git add`ing
$ git am --skip
$ git am --abort
```

## 7. Tying Back to §2's Email Workflow

§2.1 described the Linux kernel's pre-Git era: contributors emailed patches, applied by hand. `git format-patch` and `git am` are not a historical footnote — they are the **direct, still-actively-used mechanism** the kernel project and many other large open-source projects use _today_ for their entire contribution workflow: a contributor runs `format-patch`, emails the resulting files (often via `git send-email`, a companion tool) to a mailing list, and a maintainer runs `git am` to apply them, preserving full authorship with zero dependency on a shared Git hosting platform, GitHub account, or even a shared remote at all. Understanding cherry-pick and patch files together demystifies why some of the most consequential software on earth is still developed with a workflow that predates GitHub and pull requests entirely.

> 💡 **Tip:** A pull request on GitHub/GitLab is, functionally, a hosted, GUI-wrapped convenience layer over "here is a set of commits I'd like you to apply to your branch" — conceptually the same request `format-patch`/`am` fulfilled by email for a decade before platforms existed, even though the mechanics (merge via the platform's API) differ from literal patch application.

## 8. Hands-On — Cherry-Pick a Backport and Generate a Patch

```bash
$ mkdir cherrydemo && cd cherrydemo && git init -q
$ echo "v1" > app.js && git add . && git commit -qm "base"

$ git switch -c release-1.0
$ git switch main
$ echo "critical fix" >> app.js && git commit -qam "Fix critical null check"

# Backport the fix to the release branch
$ git switch release-1.0
$ git cherry-pick -x main
[release-1.0 e8f1a2b] Fix critical null check
 (cherry picked from commit ...)

# Generate a portable patch file for this same fix, for a team without repo access
$ git switch main
$ git format-patch -1 HEAD
0001-Fix-critical-null-check.patch
$ head -5 0001-Fix-critical-null-check.patch
From a1b2c3d4e5f6789012345678901234567890abcd Mon Sep 17 00:00:00 2001
From: Harshit Kandhwey <harshitkandhwey@gmail.com>
Date: Tue, 21 Jul 2026 10:15:00 +0530
Subject: [PATCH] Fix critical null check
```

## 9. Production & Enterprise Usage

- **Security backports:** a CVE fix lands on `main` and must be independently applied to every still-supported release branch (2.4, 2.5, 2.6) without pulling in unrelated features — the textbook cherry-pick use case, often scripted across many branches at once.
- **Vendor/fork syncing:** teams maintaining a fork of an upstream project sometimes cherry-pick specific upstream fixes rather than merging the entire upstream history, to keep their fork's divergence deliberate and reviewable.
- **Air-gapped or offline environments:** some regulated or high-security environments transfer changes via patch files precisely because no direct network path between two Git instances is permitted — `format-patch`/`am` (or even plain `apply`) remain the standard mechanism for that transfer.
- **Mailing-list-based open source projects** (the Linux kernel foremost among them, but also many other C/systems projects) still run their entire contribution and review process over `format-patch`/`send-email`/`am`, with no pull-request mechanism in the primary workflow at all.

## 10. Troubleshooting

| Symptom                                                                                            | Likely cause                                                                         | Fix                                                                                                                                                                                                                |
| -------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `error: could not apply <hash>... <message>` during cherry-pick                                    | Conflict between the cherry-picked diff and the target branch's current state        | Resolve as in §13.8, `git add`, `git cherry-pick --continue`                                                                                                                                                       |
| `git am` fails with `patch does not apply`                                                         | The patch's base content has diverged too far from the target branch's current state | `git apply --check <patch>` to preview without applying; may need `git am --3way` to attempt a three-way merge fallback instead of exact context matching                                                          |
| Cherry-picked commit shows as a completely separate, duplicate entry when later doing a real merge | Expected — cherry-pick creates no ancestry link to the original (17.5)               | Accept the harmless duplicate/no-op, or use `git merge -s ours`-style conscious handling if it causes real conflicts; better, adopt a branching strategy (§22) that avoids relying on repeated ad hoc cherry-picks |
| `git apply` succeeds but the resulting commit has the wrong author                                 | Expected — `apply` never carries commit metadata, only `am` does                     | Use `git am` instead if authorship preservation matters                                                                                                                                                            |

## 11. Interview Questions

**[Beginner] Q1. What does `git cherry-pick` do?**
**Model answer:** It takes one specific commit from anywhere in the repository's history and applies just that commit's changes as a new commit on your current branch. The new commit has a new hash and its parent is whatever your current branch's tip already was — it carries no recorded ancestry link back to the original commit or the branch it came from, even though the actual content change is identical.

**[Intermediate] Q2. How does cherry-pick differ from rebase, given both create new commits with new hashes for existing changes?**
**Model answer:** Rebase replays an entire sequence of commits — everything unique to a branch since it diverged from another — in their original order, onto a new base, as a single operation intended to move a whole line of work. Cherry-pick applies exactly one commit (or an explicitly chosen list/range) you select individually, with no assumption that you want everything else that branch has done. Rebase is about relocating your whole branch; cherry-pick is about deliberately picking a single, specific change.

**[Intermediate] Q3. What's the difference between `git apply` and `git am`?**
**Model answer:** Both apply a patch file's content changes, but `git apply` only modifies the working directory (and optionally the index) — it never creates a commit and discards all author/date/message metadata, so whoever runs it and later commits becomes the sole recorded author. `git am` parses the patch as a full formatted email produced by `git format-patch`, applies the change, and commits it automatically, preserving the original author's name, email, and message exactly — the person running `git am` becomes the committer while the original contributor remains the author, the same distinction Git's commit object always tracks.

**[Senior] Q4. A team is using cherry-pick to move nearly every commit from `develop` into `main`, one at a time, as their normal release process. What's wrong with this, and what would you recommend instead?**
**Model answer:** Systematic, wholesale cherry-picking between two branches that are actually meant to converge is a process smell, not a legitimate pattern. Every cherry-picked commit is a genuinely new object with a new hash and no ancestry link back to its origin on `develop`, so Git has no way to recognize "this content already exists over there" — history ends up with duplicated-looking changes with two independent origins, `git log`/`git blame` become confusing about where a fix actually first appeared, and if `develop` and `main` are ever properly merged later, Git may re-present already-cherry-picked changes as if they were new, or produce unnecessary conflicts reconciling content that's actually identical. The right fix is an explicit branching strategy (§22) — typically, either merge `develop` into `main` properly at release time (or vice versa, depending on the flow direction chosen), reserving cherry-pick specifically for the legitimate exception cases: an urgent backport to an older, otherwise-frozen release branch, or recovering an isolated commit made on the wrong branch — not as the default mechanism for routine, whole-scale integration between two branches that are supposed to reconcile.

**[Senior] Q5. Why does the Linux kernel project still use `git format-patch`/`git am` over email instead of GitHub pull requests, and what does that tell you about Git's design?**
**Model answer:** The kernel's contributor base predates GitHub by well over a decade, and its entire review culture — public mailing-list discussion, maintainer trees reviewing and forwarding patches up a hierarchy, no dependency on any single hosting company — was built around email and patch files from the start; migrating tens of thousands of contributors and a deeply embedded review process to a platform-centric model has enormous cultural and workflow cost for uncertain benefit, especially given the project's stated priority on being maximally distributed and platform-independent, echoing exactly the design philosophy from §2.4.3. What it reveals about Git's design is that `format-patch`/`apply`/`am` were never a stopgap bolted on before "real" collaboration tooling arrived — they were designed as first-class, fully sufficient primitives for exactly this workflow, and pull requests are better understood as one popular, GUI-convenient layer built on top of the same underlying idea (here are some commits, please apply them), not the only legitimate way to collaborate with Git. A senior answer should recognize that PR-based workflows are a platform convention, not a Git requirement.

## 12. Common Misconceptions

1. **"Cherry-picking is the same as a small rebase."** Rebase moves your branch's entire unique commit sequence; cherry-pick moves exactly the commit(s) you individually specify, with no assumption of taking everything else.
2. **"A cherry-picked commit is 'linked' to its original in some way Git tracks."** Git records no structural ancestry relationship between them at all — they're independent objects that happen to share identical (or near-identical) content; `-x`'s trailer is a human-readable note, not something Git's merge/diff machinery understands natively.
3. **"`git apply` and `git am` are basically interchangeable."** `apply` never commits and discards metadata; `am` commits automatically and preserves original authorship — a meaningful difference whenever attribution matters.
4. **"Patch files are an obsolete, pre-GitHub relic."** They remain the primary contribution mechanism for major projects (the Linux kernel foremost) and the standard tool for air-gapped/offline change transfer today.
5. **"Cherry-picking between two branches instead of merging is always fine since the code ends up the same."** At scale and as a systematic substitute for real integration, it produces duplicated history with no recognized common ancestry, confusing blame/log output and potential conflicts if a real merge happens later.

## 13. 🔑 Key Takeaways

- `git cherry-pick` applies one specific commit's diff as a brand-new commit on the current branch, with a new hash and no recorded ancestry link back to the source — contrast with rebase's whole-sequence replay and merge's explicit two-parent reconciliation.
- `-x` appends a "(cherry picked from...)" trailer for human traceability; `-n` stages without committing for review first.
- Legitimate uses: backporting fixes to release branches, recovering a misplaced commit, targeted hotfixes. Systematic cherry-picking as a substitute for real branch integration is a process smell — use a real branching strategy instead (§22).
- `git diff` captures content only; `git format-patch` captures full commit metadata as portable, per-commit files; `git apply` applies content only (no commit, no attribution); `git am` applies and commits, preserving original authorship.
- Patch-file workflows aren't a historical relic — they remain the primary, actively used contribution mechanism for major projects like the Linux kernel, and the standard tool for air-gapped change transfer.

## 14. Related Concepts & What's Next

Cherry-pick and patches both move already-committed change around deliberately. §18 shifts to a different kind of permanent marker on committed history — tags — covering the practical discipline of creating, pushing, and managing them for real release management, Semantic Versioning, and how Conventional Commits feed automated changelog and release tooling in CI/CD (§25).
