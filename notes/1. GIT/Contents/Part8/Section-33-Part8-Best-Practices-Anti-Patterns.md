# Section 33 (Part 8): Consolidated Best Practices & Anti-Patterns

## 33.1 Definition

**Plain language:** This section is a synthesis, not new material — it pulls the good habits and the traps that have been scattered across §1-32 into one place, organized by theme, so they can be used as a single reference rather than re-derived from memory of thirty-two separate sections.

**Precise:** Five hygiene themes are covered — commit hygiene, branching hygiene, history hygiene, security hygiene, and collaboration hygiene — each paired with the anti-patterns that violate it and a brief statement of the concrete mechanism (not just "this is bad practice") behind why it causes real problems. A consolidated checklist closes the section.

## 33.2 Why a Consolidation Section Exists

Individually, each earlier section taught one mechanism deeply — how rebasing works, how the object model hashes content, how PRs get reviewed. None of them, on their own, answer "given everything I now know about Git, what should my team's actual day-to-day discipline be?" That synthesis question is what this section answers, deliberately organized by _theme_ rather than by chronological section number, because that's how the guidance actually gets used in practice: a team writing a contribution guide reaches for "commit hygiene" as one block, not for "recall everything from §17."

## 33.3 Commit Hygiene

### 33.3.1 Atomic commits

Each commit should represent **one logical, self-contained change** — a single bug fix, a single small feature increment, a single refactor — not an unrelated bundle of changes. The mechanism this protects: `git bisect` (§19) and `git revert` (§15) both operate on the assumption that a commit is a coherent unit; a commit mixing a bug fix with an unrelated formatting pass makes `git revert` undo both together, and makes `bisect` implicate a commit that "did too much" to cleanly diagnose.

### 33.3.2 Imperative mood, descriptive messages

Write commit messages as commands ("Fix pagination off-by-one," not "Fixed pagination off-by-one" or "Fixes pagination"), matching the convention Git's own tooling uses (e.g., `git revert`'s generated message, merge commit messages). The subject line should be a short summary; a blank line plus a longer body explains **why**, not just what — the diff already shows what changed.

### 33.3.3 Conventional Commits, recap

§18.9 covered this in full: a `type(scope): description` prefix convention (`feat:`, `fix:`, `chore:`, etc., with a `BREAKING CHANGE:` footer for breaking changes) that lets tooling automatically compute SemVer version bumps and generate changelogs. Adopting it is optional but, once adopted, should be enforced consistently (commonly via a commit-msg hook, §24) — a mix of conforming and non-conforming messages defeats the automation entirely.

### 33.3.4 Commit early, commit often, locally

Because commits are local and cheap in a DVCS (§1.6.1), there's no cost to committing frequently in your own working branch — this preserves fine-grained undo points. Cleaning that history up (via interactive rebase, §14) before it's shared is a separate, later step, not a reason to avoid frequent local commits in the first place.

## 33.4 Branching Hygiene

### 33.4.1 Short-lived branches

§22.6's core argument, worth restating as a standalone principle: merge-conflict cost grows with how long a branch and its target have diverged, not linearly but in a way that compounds — a branch open for two days conflicts far less than the same branch left open for two months while `main` keeps moving. Whichever branching strategy a team adopts (§22's Git Flow, GitHub Flow, GitLab Flow, or trunk-based development), the common thread across all the ones that scale well is keeping feature branches as short-lived as the team's release cadence allows.

### 33.4.2 Descriptive, conventionally-named branches

A branch name like `feature/payments-retry-backoff` communicates purpose at a glance in a branch list; `jd-temp2` does not. Most teams converge on a `<type>/<short-description>` convention (§12), which also lets tooling (protected-branch rules, CI triggers) pattern-match on branch type.

### 33.4.3 Don't let branches become long-running parallel realities

A branch that diverges for months effectively becomes a second `main` in practice, and merging it back becomes a high-risk, high-effort event exactly like Git Flow's `release` branches at their worst (§22.3). If a piece of work genuinely can't ship soon, prefer feature flags to decouple "merged" from "released" (§22.6) over keeping a branch open indefinitely.

## 33.5 History Hygiene

### 33.5.1 When rewriting history is fine

Rewriting **your own, not-yet-shared** commits — squashing, rewording, reordering via interactive rebase (§14) — is safe and often genuinely improves the readability of history before it becomes permanent and public.

### 33.5.2 The Golden Rule (§14.7), restated as a standalone principle

**Never rewrite commits that others may already have fetched and built on.** The mechanism, not just the rule: rewriting produces new commit hashes (§5.5.3), and a rewritten history has no recognizable ancestry link to what a collaborator's clone already has — their next `pull` either produces a confusing divergent-history merge or, if they've been told to force-reset, requires manually recovering and reapplying any local work they had on top of the old commits. This is the single most consequential history-hygiene rule in the entire series, and it is why `git push --force-with-lease`, not plain `--force`, is the safer default when a force-push to a shared branch is genuinely necessary (§20).

### 33.5.3 Large-scale rewrites (`filter-repo`, §31.7)

Removing secrets, large binaries, or bulk-correcting author identity via `filter-repo` is a full history rewrite of every affected commit, subject to the same Golden Rule at full force — it requires explicit, coordinated, whole-team communication, not a quiet solo operation on a shared repository.

## 33.6 Security Hygiene

### 33.6.1 Signing commits and tags

Cryptographic signing (GPG/SSH signing, covered as its own topic) proves that a specific holder of a specific key vouched for a specific commit or tag's exact content — building directly on the annotated-tag and commit-object structure from §5.5.3-5.5.4. Meaningful particularly for release tags and for repositories with a real threat model around impersonated commits.

### 33.6.2 Never commit secrets, and have a real plan for when it happens anyway

Prevention is cheaper than remediation: `.gitignore` patterns (§11) for credential files, pre-commit hooks (§24) that scan staged content for credential-shaped patterns, and secret-scanning features on the hosting platform (§23) all reduce the odds of a leak reaching a shared branch. But prevention will eventually fail somewhere, so a team needs a known remediation path (history rewrite via `filter-repo`, §31.7, **plus mandatory credential rotation** — the rewrite alone does not undo the exposure that already happened) rather than improvising one under incident pressure for the first time.

### 33.6.3 Protected branches and required review

Branch protection rules (required reviews, required status checks, restrictions on who can force-push, §23) turn "please don't force-push to `main`" from a social norm into an enforced technical constraint — the more consequential a branch, the less its safety should depend purely on everyone remembering the rules.

## 33.7 Collaboration Hygiene

### 33.7.1 Small, focused PRs (§21.7)

A PR changing one coherent thing gets a real review; a PR touching forty files across three unrelated concerns gets rubber-stamped out of reviewer fatigue, which defeats the actual purpose of review — catching problems before they merge.

### 33.7.2 Descriptive PR titles and bodies, responsive review culture

State what changed and why, link the relevant ticket, and flag anything a reviewer should specifically scrutinize. Respond to every review comment, even briefly — an unanswered comment is a silently stalled PR. Review the code, not the author.

### 33.7.3 Merge strategy consistency (§21.6)

Whichever merge strategy a team adopts at PR-merge time (merge commit, squash, or rebase-and-merge), applying it **consistently** matters more than which one is chosen — a history that mixes strategies unpredictably makes `git log` and `git bisect` harder to reason about for everyone.

## 33.8 The Anti-Patterns List

Each entry states the pattern, then the concrete mechanism that makes it costly — not just "this is frowned upon."

| Anti-pattern                                                            | Why it's actually bad                                                                                                                                                                                                                                                                                                                              |
| ----------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Committing generated/build artifacts**                                | Build output changes on every build (often non-deterministically — timestamps, absolute paths), producing enormous, meaningless diff noise on every commit and bloating the object database with content that should be regenerated, not versioned; the fix is a correct `.gitignore` (§11), not manual discipline to avoid `git add`-ing them     |
| **Giant commits mixing unrelated changes**                              | Breaks `git bisect`'s ability to cleanly implicate one change, breaks `git revert`'s ability to undo one thing without undoing others bundled into the same commit, and makes code review effectively impossible to do carefully (§33.3.1, §33.7.1)                                                                                                |
| **Force-pushing to shared branches**                                    | Rewrites commit hashes that collaborators' clones already reference (§5.5.3), breaking their ancestry link to the branch and risking silent loss of their local work if they aren't warned before their next pull — the direct violation of the Golden Rule (§14.7, §33.5.2)                                                                       |
| **Committing secrets**                                                  | The object database is content-addressable and (by default) permanent; once a secret is committed and pushed, anyone who fetched it has a copy, and removing it later requires a full history rewrite plus mandatory credential rotation, not just a quiet follow-up commit deleting the file (§28, §31.7.3, §33.6.2)                              |
| **Ignoring merge conflicts by blindly accepting "theirs" (or "ours")**  | Silently discards one side's actual intended change rather than genuinely reconciling both — often introduces a regression that looks like a clean merge and passes review because the diff looks unremarkable, only surfacing later as a mysteriously "undone" fix                                                                                |
| **Running `git add .` without reviewing `git status`/`git diff` first** | Stages everything in the working directory indiscriminately, including accidental debug output, local config overrides, stray temp files, or — worst case — a credentials file that isn't yet in `.gitignore`; reviewing staged content before committing is the cheapest possible check against exactly the two worst anti-patterns in this table |

> ⚠️ **Common confusion to preempt:** none of these anti-patterns are "advanced" mistakes — they are the small number of failure modes responsible for the overwhelming majority of real-world Git incidents a working engineer actually encounters. Interviewers ask about them precisely because avoiding them is a better signal of practical competence than knowing an obscure plumbing command.

## 33.9 A Practical Git Hygiene Checklist

A team can adopt this directly as a contribution-guide baseline:

**Before committing:**

- [ ] `git status` and `git diff --staged` reviewed before every commit — nothing staged blindly via `git add .` without a look
- [ ] Commit is atomic — one logical change, not several unrelated ones bundled together
- [ ] Commit message is imperative-mood, descriptive, and (if the team has adopted it) Conventional-Commits-formatted
- [ ] No generated/build artifacts, credentials, or local-only config in the diff

**Before opening a PR:**

- [ ] Branch is reasonably short-lived and rebased/updated against the current target branch
- [ ] Branch name follows the team's convention
- [ ] PR is scoped to one coherent concern, not several
- [ ] PR description states what changed and why, with any areas the reviewer should scrutinize called out

**Before merging:**

- [ ] All review comments addressed or explicitly resolved with a response
- [ ] Required status checks passing
- [ ] Merge strategy matches the team's established convention (merge commit / squash / rebase, consistently)

**Repository-wide, ongoing:**

- [ ] Protected-branch rules enforced on `main` (and any release branches) — required review, no unreviewed force-push
- [ ] `.gitignore` covers build output, dependency directories, and local config for the stack in use
- [ ] Secret-scanning enabled on the hosting platform; pre-commit or commit-msg hooks catch obvious credential patterns before they leave a local machine
- [ ] Release tags are annotated (§5.5.4, §18), not lightweight, and signed where the team's threat model warrants it
- [ ] A known, rehearsed remediation plan exists for "a secret was just pushed" — not something improvised for the first time during an actual incident

## 33.10 Interview Questions

**[Beginner] Q1. What makes a commit "atomic," and why does it matter?**
**Model answer:** An atomic commit represents exactly one logical, self-contained change — a single bug fix or a single small increment of a feature — rather than several unrelated changes bundled together. It matters because tools that operate on individual commits assume this: `git revert` undoes an entire commit as a unit, so a commit mixing a bug fix with unrelated formatting changes forces you to undo both together or manually pick apart the diff; `git bisect` narrows a regression down to a single implicated commit, which is only useful if that commit did one coherent thing. Atomic commits keep both tools — and code review — actually usable.

**[Intermediate] Q2. Explain, mechanically, why force-pushing to a shared branch is dangerous, not just "against convention."**
**Model answer:** Every commit's hash is derived from its own content plus its parent's hash, so rewriting history — via rebase, amend, or a history-rewriting tool — produces entirely new hashes for every changed commit. If those old commits were already pushed and someone else has fetched and built on top of them, a force-push replacing them with the new-hash versions leaves that collaborator's local branch pointing at commits that no longer have any recognizable ancestry relationship to the new shared history. Their next pull either produces a confusing, unwanted merge of two divergent histories, or — if they're told to reset onto the new history — requires them to manually identify and reapply whatever local work they had on top of the old commits, with real risk of silently losing something if they're not careful. This is exactly the Golden Rule of rebasing (§14.7) generalized to any history-rewriting operation, not a rule specific to `rebase` alone.

**[Intermediate] Q3. Why is "committing generated build artifacts" considered a real problem rather than just messy?**
**Model answer:** Build output typically changes on every build run, often in ways unrelated to any real source change — embedded timestamps, absolute file paths, non-deterministic ordering from the build tool. Committing it means every commit touching the build carries large, meaningless diff noise that obscures the actual, reviewable change, and the object database accumulates a growing amount of content that should be regenerable on demand from source, not versioned as a first-class artifact. It also risks stale build output silently shipping if the artifact isn't actually rebuilt before deployment, since Git has no way to know a committed binary is out of sync with the source that supposedly produced it. The fix is a correct `.gitignore` for the stack in use, not relying on every contributor remembering not to `git add` the build directory.

**[Senior] Q4. A new engineer asks why the team enforces so many rules — protected branches, required review, signed tags, pre-commit secret scanning — when "Git already tracks everything, so nothing is really lost." How do you respond?**
**Model answer:** I'd separate two different guarantees Git actually provides from the ones people often assume it provides. Git's object model genuinely does give strong guarantees around integrity and history retrieval — content is content-addressed, tampering with an existing object is detectable, and the reflog (§6, §30) gives a real local safety net for a wide range of local mistakes. But none of that protects against categories of harm that are fundamentally about **exposure** or **coordination**, not loss: a committed secret is exposed the moment it's pushed and fetched by anyone, and no amount of subsequent history rewriting undoes that exposure — only rotating the credential does. Similarly, "nothing is lost" doesn't help a collaborator who force-pushed over shared history and now has to manually reconstruct what a teammate's diverged local branch actually contained; the objects might technically still exist in someone's reflog, but recovering them under pressure, correctly, isn't a reliable substitute for having prevented the situation. Protected branches, required review, and secret scanning aren't distrust of Git's mechanics — they're process controls for exactly the failure modes Git's object model does not, and structurally cannot, protect against on its own.

**[Architect] Q5. You're asked to write a Git contribution policy for a 200-engineer organization migrating off a more restrictive centralized tool. What do you actually put in it, and what do you deliberately leave out?**
**Model answer:** I'd anchor the policy on the themes in this section rather than an exhaustive rulebook, because an over-specified policy gets ignored while a themed one gets internalized: commit hygiene (atomic commits, a message convention — likely Conventional Commits if the org wants automated changelogs/versioning), branching hygiene (pick one branching strategy from §22 matched to the org's actual release cadence, not the most sophisticated-sounding one — GitHub Flow for continuous deployment, something closer to GitLab Flow if there are genuinely multiple supported release lines), history hygiene (the Golden Rule stated explicitly, with `--force-with-lease` as the only sanctioned force-push method and only on personal branches), security hygiene (mandatory protected branches and required review on `main` and release branches from day one, secret scanning enabled at the platform level before the first real commit lands, signed tags at least for releases), and collaboration hygiene (a PR size/scope norm and a review-response-time expectation). What I'd deliberately leave out: mandating a specific commit-message length or an exhaustive list of exactly which words are banned in messages, prescribing exactly how many approvals every PR needs regardless of size or risk (better handled by CODEOWNERS-style path-based rules, §23), and any rule that can't be enforced by tooling (a human-enforced-only rule decays the moment the person who cares moves teams). The overarching principle: prefer automatable, tool-enforced rules over purely social ones wherever the two options are actually equivalent in effect, because tooling enforcement is what survives team turnover.

## 33.11 Common Misconceptions

1. **"These rules are about being tidy, not about avoiding real damage."** Nearly every anti-pattern in §33.8 maps to a concrete, mechanistic failure mode — broken bisect, lost work, exposed secrets, silently discarded fixes — not merely aesthetic preference.
2. **"Force-pushing is always forbidden."** It's forbidden specifically on **shared** branches others may have built on; force-pushing your own personal, not-yet-shared branch (including your own open PR branch, per §21.10 Q3) is normal and expected, ideally via `--force-with-lease`.
3. **"Accepting 'theirs' during a conflict is a safe default when unsure."** It silently discards one side's actual change; the safe default when unsure is to read both sides and understand the conflict, not to pick a side mechanically.
4. **"A secret removed from history via filter-repo is fully remediated."** The rewrite prevents _future_ exposure from that repository copy; it does not undo the fact that the secret was already exposed to anyone who fetched it beforehand — rotation is mandatory regardless.
5. **"More required approvals on a PR is always safer."** Beyond a point it just produces rubber-stamping and review fatigue (§33.7.1); the more effective lever is PR size and focus, not approval count alone.

## 33.12 🔑 Key Takeaways

- Five hygiene themes cover nearly everything: **commit hygiene** (atomic, well-described, optionally Conventional-Commits-formatted), **branching hygiene** (short-lived, descriptively named), **history hygiene** (rewrite freely before sharing, never after — the Golden Rule), **security hygiene** (signing, secret prevention, and a rehearsed remediation plan, not just prevention), and **collaboration hygiene** (small PRs, responsive, consistent review culture).
- Every anti-pattern in §33.8 traces to a concrete mechanism — broken bisect/revert, exposed secrets that rewriting alone can't undo, silently discarded fixes, hash-breaking force-pushes — not vague "best practice" superstition.
- The most valuable rules are the ones tooling can enforce (branch protection, secret scanning, commit-msg hooks) rather than ones that rely purely on everyone remembering — tooling enforcement survives team turnover; social-only rules don't.
- This section deliberately introduced no new mechanisms — everything here was already taught in §1-32; the value is in the synthesis and the checklist form.

## 33.13 Related Concepts & What's Next

This closes Part 8's technical content. §34 shifts into interview preparation proper — drilling the kind of rapid-fire and scenario-based questions a real Git-heavy interview loop uses, pulling from the tiered questions built into every section so far. §35 provides hands-on labs to actually practice the mechanisms covered across all thirty-three sections rather than only read about them. §36, the final section of this entire series, closes with a consolidated key-takeaways wrap-up across the whole thirty-six-section arc.
