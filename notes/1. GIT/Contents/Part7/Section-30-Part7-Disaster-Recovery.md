# Section 30 (Part 7): Disaster Recovery — reflog, fsck, Recovering Lost Commits & Repairing Corruption

## 30.1 Definition

**Plain language:** "I think I just destroyed hours of work" is rarely true in Git — almost every apparent loss is recoverable, because Git deletes almost nothing immediately and keeps multiple, layered safety nets. This section is the complete escalation path: from the everyday reflog, to `fsck`-based recovery of objects the reflog no longer remembers, to the last-resort case where the local repository itself is damaged and recovery has to come from somewhere else entirely.

**Precise:** Git's disaster-recovery guarantees rest on three layered facts established across earlier sections: (1) commit objects are never deleted the instant a ref stops pointing at them (§7.6.3), (2) the reflog (§6.6) records ref movements locally and protects recently-orphaned objects from garbage collection for a retention window, and (3) even after both the reflog and any local recovery path are exhausted, every full clone anywhere is an independent, complete copy of history (§1.6.1) that can reseed a damaged or lost local repository entirely.

## 30.2 Why It Exists / Problem It Solves

1. **Destructive-looking operations are common and encouraged in Git's daily workflow** — `reset --hard`, force-pushes, branch deletion, and history rewriting (§14, §15, §28) are all normal, useful operations, not exotic edge cases. A safety net has to exist or none of them would be usable without constant fear.
2. **Mistakes happen under pressure and often compound** — a wrong-branch `reset --hard`, a panicked force-push, an accidental branch deletion during cleanup. Recovery procedures need to be calm, repeatable, and not dependent on remembering exact hashes from memory.
3. **Not every loss is recoverable from the same layer** — knowing which tool applies to which stage of "how lost is this" (still on a branch → reflog → fsck → another clone entirely) is the actual skill; reaching for the wrong tool, or assuming something is unrecoverable prematurely, both waste time in an actual incident.
4. **Corruption, while rare, is categorically different from "lost" history** — a lost commit still exists intact somewhere in the object database; a corrupted object is damaged data that may need to come from an entirely separate, uncorrupted copy.

## 30.3 The Reflog as the Primary Recovery Tool (Deepening §6.6)

The reflog is the first tool to reach for in nearly every recovery scenario, because it directly records the _before_ state of any ref-moving operation — commits, resets, rebases, checkouts, merges.

### 30.3.1 Recovering a commit after a bad `reset --hard`

```bash
$ git log --oneline
7e4f9a2 commit B
a3f8e21 commit A

$ git reset --hard HEAD~1
HEAD is now at a3f8e21 commit A
# "commit B" appears to be gone from git log

$ git reflog
a3f8e21 (HEAD -> main) HEAD@{0}: reset: moving to HEAD~1
7e4f9a2 HEAD@{1}: commit: commit B
...

$ git reset --hard HEAD@{1}
HEAD is now at 7e4f9a2 commit B
```

`HEAD@{1}` names exactly the ref position one movement ago — before the destructive reset — and resetting back to it restores the branch pointer precisely, because the commit object itself was never deleted (§7.6.3), only unreferenced.

> 💡 **Tip:** `git switch -c recovery-branch HEAD@{1}` is a strictly safer alternative to a second `reset --hard` when recovering — it creates a new branch at the recovered position without touching your current branch pointer again, letting you inspect the recovered state before deciding what to do with it.

### 30.3.2 Recovering a deleted branch

```bash
$ git branch -D feature-payments
Deleted branch feature-payments (was 9d8e7f6).

# The hash was printed on deletion — but even without that, it's in the reflog:
$ git reflog | grep feature-payments
9d8e7f6 HEAD@{4}: checkout: moving from feature-payments to main

$ git branch feature-payments 9d8e7f6
```

Branch deletion, exactly like `reset`, never deletes the underlying commit objects — it removes only the small pointer file under `.git/refs/heads/` (§6.3.1). Recreating a branch ref at the last known hash — found either from the deletion command's own output or from the reflog — fully restores it.

### 30.3.3 The retention window and its limits

> ⚠️ **Critical scope limitation (restated from §6.6.3 with full disaster-recovery framing):** the reflog is **local only** — it is never included in a clone, fetch, or push, so a teammate cannot recover _your_ mistake from their copy of the repository via reflog, and a fresh clone of your own repository from another machine has no reflog history either. It also **expires**: unreachable entries by default around 30 days, reachable ones around 90 (exact values are controlled by `gc.reflogExpire` / `gc.reflogExpireUnreachable` and worth confirming against your Git version). Once an entry expires and a subsequent `gc` runs, that recovery path closes permanently — this is precisely why the next tool, `fsck`, matters: it can still find some objects the reflog has already forgotten, provided `gc` hasn't pruned them yet either.

## 30.4 Recovering Dangling Commits the Reflog No Longer Remembers

### 30.4.1 When this applies

The reflog itself has expired the relevant entry, or the loss happened via an operation that didn't create a normal reflog entry you can find (a scripted operation, a different clone/worktree, or simply too much time has passed). The commit object may still physically exist — objects aren't deleted the moment they become unreferenced, only once `gc` actually prunes them (§7.6.1-7.6.3) — but nothing, including the reflog, currently points at it. This is a **dangling** object.

### 30.4.2 `git fsck --full --unreachable`

```bash
# Purpose: list every object not reachable from any ref, including ones
# the reflog no longer references either
$ git fsck --full --unreachable
unreachable commit 9d8e7f6a1b2c3d4e5f6789012345678901234567
unreachable blob e5f6a7b8c9d0e1f2a3b4c5d6e7f8901234567890
dangling commit 9d8e7f6a1b2c3d4e5f6789012345678901234567
```

`dangling commit` entries are the primary interest — a fully intact commit object that nothing currently references. Blobs and trees can also show up dangling (e.g., from a `git add` that staged content which was never committed), but a dangling **commit** is usually the recoverable unit of actual work, since it carries its own tree snapshot and message.

### 30.4.3 Inspecting before deciding

Never blindly reattach a dangling commit — `fsck` can surface a large number of them in an active repository (amend/rebase leftovers, old detached-HEAD experiments), most of which are genuinely disposable. Inspect first:

```bash
# Purpose: view a dangling commit's metadata and message without touching any ref
$ git cat-file -p 9d8e7f6a1b2c3d4e5f6789012345678901234567
tree e5f6a7b8...
parent a3f8e21...
author Jane Doe <jane@example.com> 1721654321 +0000

Refactor payment retry logic

# Purpose: view the actual file tree/content it represents, once it looks relevant
$ git show 9d8e7f6a1b2c3d4e5f6789012345678901234567
```

Once confirmed as the commit you actually want back:

```bash
$ git switch -c recovered-payment-work 9d8e7f6a1b2c3d4e5f6789012345678901234567
```

> ⚠️ **Critical clarification:** `fsck --unreachable` is strictly a _superset_ recovery layer beyond the reflog — anything findable via reflog is also findable this way, but `fsck` additionally surfaces objects whose reflog entries have already expired. It is not, however, unlimited: once `git gc` actually prunes an unreachable object (past both the reflog's retention window and `gc`'s own grace period, §7.6.2's `--prune=<date>`), it is genuinely gone from this repository — `fsck` can only find what still physically exists on disk.

## 30.5 Repository Corruption

### 30.5.1 Symptoms

```
error: object file .git/objects/ab/cdef1234... is empty
error: bad object HEAD
fatal: loose object <hash> (stored in .git/objects/ab/cdef...) is corrupt
fatal: bad tree object <hash>
```

These indicate the object database itself is damaged — not merely a ref pointing at the wrong (but intact) place, which is what 30.3-30.4 address. Common causes: disk failures or filesystem errors, an interrupted operation that left a partially-written file, or (rarely) manual/scripted tampering with `.git/objects` outside of Git's own commands.

### 30.5.2 General recovery approaches

1. **Run `git fsck --full` first** to get a complete inventory of exactly what's damaged versus intact — corruption is frequently localized to a handful of objects, not the entire database.
2. **Re-fetch the missing/corrupt objects from a remote.** If the corrupted object still exists intact on `origin` (or any other remote), a fresh `git fetch` can often repair the local copy without any special recovery procedure, since Git will re-download objects it doesn't already have valid local copies of. This is the direct practical payoff of §1.6.1's point that **every clone is a full, independent backup** — the fastest recovery for local corruption is very often simply "get it again from somewhere else that isn't corrupted."
3. **Pull from a collaborator's clone**, if no central remote has the needed objects (or none exists) — any teammate's local repository is an equally valid full copy of shared history and can be added as a temporary remote to fetch from.
4. **Restore from a dedicated backup**, most robustly a bare repository (§9.5, §23.4.1) maintained specifically as a mirror/backup target — `git clone --mirror` or scheduled `git fetch` into a bare repo is the standard pattern for exactly this purpose, giving you a clean, independently-stored copy of all refs and objects to restore from or re-clone entirely.
5. **As an absolute last resort**, if no clone anywhere has the needed object and no backup exists, that specific commit's content is genuinely unrecoverable — this is the scenario every earlier layer of this section (reflog, fsck, remotes-as-backups) exists specifically to make rare.

```
Recovery escalation, in order of "how bad is this":

  Ref moved, commit still reachable            →  simple checkout/reset to known hash
  Ref moved, commit unreachable but in reflog   →  §30.3  git reflog
  Reflog expired, object still on disk          →  §30.4  git fsck --full --unreachable
  Object itself corrupted/missing locally       →  §30.5  fetch from remote / collaborator / backup
  Corrupted AND no clone/backup exists anywhere  →  genuinely unrecoverable — the case
                                                      everything above exists to prevent
```

## 30.6 Worked Scenario — Accidental `reset --hard` on the Wrong Branch, Losing 3 Commits

**Setup:** you meant to reset a scratch branch but were actually on `main`, and ran `git reset --hard origin/main` — moving `main` backward by three commits that existed only locally and hadn't been pushed yet.

```bash
$ git log --oneline
# (only 2 commits shown — the 3 you just lost are missing)
7e4f9a2 Add error handling
1a2b3c4 Initial setup

# Step 1: don't panic, don't run anything else destructive. Check the reflog immediately.
$ git reflog
7e4f9a2 (HEAD -> main) HEAD@{0}: reset: moving to origin/main
d4e5f6a HEAD@{1}: commit: Add retry logic for payment gateway
c3d4e5f HEAD@{2}: commit: Add integration test for retries
b2c3d4e HEAD@{3}: commit: Wire up retry config flag
7e4f9a2 HEAD@{4}: commit: Add error handling

# Step 2: HEAD@{1} is the state immediately before the reset — exactly the three
# lost commits, still fully intact.
$ git log --oneline HEAD@{1}
d4e5f6a Add retry logic for payment gateway
c3d4e5f Add integration test for retries
b2c3d4e Wire up retry config flag
7e4f9a2 Add error handling
1a2b3c4 Initial setup

# Step 3: recover onto a new branch first, rather than immediately re-resetting main,
# so you can review before deciding what to do with it
$ git switch -c recovered-retry-work HEAD@{1}
Switched to a new branch 'recovered-retry-work'

# Step 4: confirmed correct — now safely fast-forward main back onto it
$ git switch main
$ git merge --ff-only recovered-retry-work
Updating 7e4f9a2..d4e5f6a
Fast-forward
 ...

$ git log --oneline
d4e5f6a Add retry logic for payment gateway
c3d4e5f Add integration test for retries
b2c3d4e Wire up retry config flag
7e4f9a2 Add error handling
1a2b3c4 Initial setup
# Fully restored, nothing lost.

$ git branch -d recovered-retry-work
```

This walkthrough deliberately uses the safer two-step pattern (recover to a new branch, verify, then fast-forward `main` onto it) rather than immediately `reset --hard HEAD@{1}`-ing `main` directly — in a real incident, verifying the recovered state before touching the branch you actually care about again is the disciplined move, even though the direct reset would have worked identically in this clean example.

## 30.7 Production & Enterprise Usage

- **Bare-repository backups** (§9.5, §23.4.1) maintained via scheduled `git fetch`/`clone --mirror` jobs are the standard enterprise pattern for self-hosted Git infrastructure — a hosting platform's own database backups (users, PRs, permissions, issues — none of which live inside the Git object model itself, per §1.6.1's caveat) are a separate, equally necessary concern that pure repository mirroring does not cover.
- **"Just re-clone from a teammate" is a genuinely common, informal recovery path** on small teams without dedicated backup infrastructure — it works precisely because of the DVCS guarantee that every clone is complete, but it's not a substitute for deliberate backups at organizational scale, since it depends entirely on some individual's machine still having the needed history.
- **Incident postmortems for repository disasters** typically reveal the same root causes: force-pushing without `--force-with-lease` (§20.6.2), running destructive commands against the wrong branch due to unclear terminal context, or (rarely) genuine infrastructure failure with inadequate backup cadence — the fixes are largely disciplinary/tooling (clear prompts, `--force-with-lease` as default habit) rather than purely technical.

## 30.8 Interview Questions

**[Beginner] Q1. You accidentally deleted a local branch with `git branch -D` before merging it. Is the work gone?**
**Model answer:** No, almost certainly not. Deleting a branch only removes the small pointer file that referenced its last commit — the commit objects themselves, and everything they point to, remain fully intact in the object database. The branch deletion itself is recorded in the reflog, and Git even prints the deleted branch's last commit hash in the deletion confirmation message. Recovery is `git branch <name> <hash>`, using either that printed hash or one found via `git reflog`, which recreates the branch pointer exactly where it was.

**[Intermediate] Q2. What's the difference between recovering a commit via `git reflog` versus via `git fsck --unreachable`?**
**Model answer:** The reflog records every place a ref has pointed, locally, with an automatically maintained retention window — it's the first and easiest recovery tool, letting you jump straight to a `HEAD@{n}` position. `fsck --full --unreachable` operates one layer beneath that: it scans the entire object database for objects that no ref, and no reflog entry, currently references, but that are still physically intact on disk because garbage collection hasn't pruned them yet. In practice, you reach for `fsck` specifically when the reflog entry you need has already expired, or the loss happened in a way that didn't leave a normal reflog trail — it's a superset recovery layer, not the first tool to try, since it returns many more objects (including harmless leftovers) and requires manually inspecting each candidate with `git cat-file`/`git show` before deciding it's the one you want back.

**[Intermediate] Q3. Why is the reflog not a substitute for backups?**
**Model answer:** Two structural reasons. First, it's strictly local — never included in a clone, fetch, or push — so it protects only against your own local mistakes on your own machine, and offers zero help if that machine's disk fails or the repository is lost entirely. Second, it expires: entries are pruned after a configurable retention window (by default on the order of 30 to 90 days depending on reachability), after which garbage collection can permanently remove the underlying objects too. A real backup strategy needs to survive both "this specific machine is gone" and "more time has passed than the reflog retains" — which is why bare-repository mirrors and the general DVCS property that every full clone is an independent copy of history (§1.6.1) are the actual backstops, not the reflog.

**[Senior] Q4. Your repository's `.git/objects` directory shows `error: bad object` for several commits after a suspected disk issue. Walk through recovery.**
**Model answer:** First, `git fsck --full` to get the complete picture of exactly which objects are damaged versus intact — corruption is often localized. For each corrupted-but-still-referenced object, the fastest fix is usually the least dramatic: run `git fetch` against any remote that has the same history, since Git will re-download objects it can't validate locally, effectively self-healing without any manual object surgery. If no remote has it (a purely local branch, for instance), the next check is whether any collaborator's local clone has the needed commits — any full clone is an equally valid, independent copy of shared history, and can be temporarily added as a remote to fetch from. If neither a remote nor a collaborator's clone can supply the missing objects, the next resort is a dedicated backup — ideally a bare-repository mirror maintained specifically for this purpose — restored either by re-cloning fresh from it or fetching the missing refs into the damaged repository. Only if none of those exist is the specific corrupted content genuinely gone, which is the scenario that motivates having backup infrastructure in the first place rather than relying solely on any single developer's working copy.

**[Architect] Q5. Design a disaster-recovery policy for a self-hosted Git server, given that "every clone is a backup" is true but informal.**
**Model answer:** I'd treat "every developer's clone is a backup" as a genuinely useful emergent property, not a designed one, and build formal recovery on top of it rather than depending on it directly. Concretely: (1) scheduled, automated bare-repository mirrors (`git clone --mirror` refreshed on a regular fetch cadence) for every hosted repository, stored on infrastructure independent of the primary Git server — this is the actual recoverable backup, not any individual's laptop. (2) Explicit backup coverage for what pure repository mirroring misses: the hosting platform's own database — pull request/merge request state, issues, permissions, webhooks — none of which lives inside Git's object model itself, a gap called out back in §1.6.1. (3) A documented, regularly _tested_ restore procedure — a backup nobody has ever restored from is not a verified backup — including how long a restore takes and what data-loss window it implies (time since the last mirror sync). (4) Team-level practices that reduce how often disaster recovery is even needed: defaulting to `--force-with-lease` over `--force`, protected branches on anything shared (§23.6), and a documented "if you think you've lost something, stop and check `git reflog`/`git fsck` before doing anything else" runbook, since the majority of "disasters" are actually simple reflog-level recoveries if approached calmly rather than compounded by a second panicked destructive command.

## 30.9 Common Misconceptions

1. **"A deleted branch or a reset commit is gone."** In the overwhelming majority of cases it's merely unreferenced, not deleted — the commit objects persist in the database until garbage collection actually prunes them, which respects both current refs and the reflog's retention window.
2. **"The reflog is a shared safety net."** It's strictly local to one machine's repository; it cannot recover a teammate's mistake, and a fresh clone of your own repository elsewhere starts with no reflog history at all.
3. **"If it's not in the reflog, it's unrecoverable."** `git fsck --full --unreachable` can still find dangling objects whose reflog entries have already expired, as long as garbage collection hasn't pruned them yet — a real, if less convenient, second recovery layer.
4. **"Corruption and 'lost' history are the same problem."** A lost commit is intact data that's simply unreferenced — reflog/fsck fix that. Corruption is damaged data, which local tools generally cannot repair; the fix is re-fetching intact copies from a remote, collaborator, or backup.
5. **"Re-fetching from origin can't fix a broken local repository."** It very often can — Git re-downloads objects it can't validate locally during a normal fetch, which is frequently the simplest fix for local corruption when an uncorrupted remote copy exists.

## 30.10 🔑 Key Takeaways

- Git deletes almost nothing immediately: unreferenced commits persist until garbage collection actually prunes them, and the reflog protects recent ones from that pruning entirely for a retention window.
- Recovery escalates in layers: known hash on a branch → `git reflog` → `git fsck --full --unreachable` (for reflog-expired dangling objects) → re-fetch from a remote/collaborator/backup (for local corruption or total local loss).
- The reflog is local-only and expires — never a substitute for real backups; a bare-repository mirror (§9.5, §23.4.1) is the actual durable backstop.
- `git fsck --full --unreachable` combined with `git cat-file -p`/`git show` lets you inspect a dangling commit safely before deciding whether to reattach it with `git switch -c`.
- Every full clone of a repository is, by DVCS design (§1.6.1), an independent complete copy of history — the practical foundation of "just re-fetch/re-clone" as a genuine recovery strategy, formalized at organizational scale through dedicated backup mirrors.
- The calm, correct first response to any apparent loss is to check the reflog before running any further commands — compounding a mistake with a second panicked destructive operation is the actual cause of most truly unrecoverable situations.

## 30.11 Related Concepts & What's Next

This closes Part 7 (Security & Reliability) — signing and secret hygiene (§28), routine maintenance and everyday troubleshooting (§29), and now the full disaster-recovery escalation path. Part 8 turns to advanced tooling and the broader professional picture: worktrees, `git rerere`, and `filter-repo` in more general use beyond secret remediation (§31); Git's own evolution, including the SHA-256 transition and how Git compares directly against SVN, Mercurial, and Perforce with the benefit of everything covered since §1 (§32); best practices and anti-patterns distilled across the entire guide, including commit-message conventions (§33); and finally, structured interview preparation, hands-on labs, and a full wrap-up of the material (§34-36).
