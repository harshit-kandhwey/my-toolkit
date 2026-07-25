# Section 29 (Part 7): Maintenance, Performance Tuning & Troubleshooting Common Failures

## 29.1 Definition

**Plain language:** A Git repository is not maintenance-free — left alone, it accumulates loose objects, stale refs, and (for repos with long-lived binary churn or careless history) genuinely large stored content, all of which measurably slow down everyday commands. This section covers the routine health-check and cleanup tools, how to diagnose a slow or bloated repository, and the fixes for the failure scenarios every Git user eventually hits.

**Precise:** Git ships built-in maintenance commands (`git gc`, `git fsck`, `git count-objects`, `git maintenance`) that repack storage, verify object-database integrity, and report health statistics. Diagnosing size/performance problems is a matter of walking the object graph to find outsized blobs; diagnosing behavioral failures is a matter of recognizing a small set of recurring symptom patterns and applying the corresponding fix, most of which trace back to concepts already established in §6 (refs/reflog), §7 (packfiles/gc), and §15 (undoing things).

## 29.2 Why It Exists / Problem It Solves

1. **Loose objects and stale packs degrade real performance**, not just disk usage — filesystem overhead per tiny loose-object file (§7.2) and unoptimized delta relationships both slow down `status`, `log`, `checkout`, and clone operations as a repository ages.
2. **Corruption, while rare, does happen** — disk failures, interrupted operations, or misuse of low-level plumbing commands can leave the object database in an inconsistent state; `fsck` is the tool that detects this before it causes silent, confusing downstream failures.
3. **A small set of situations account for the overwhelming majority of "Git is broken" support requests** — detached HEAD confusion, commits on the wrong branch, conflict-resolution paralysis, and SSH authentication failures. Recognizing the pattern immediately, rather than re-deriving the fix from first principles under panic, is a genuine practical skill.
4. **At scale, default Git configuration leaves real performance on the table** — a handful of configuration knobs and the scaling techniques from §26 exist specifically because "everyone has all history, plus a full working-tree scan on every status" (§1.6.1's DVCS model) has real costs once a repository grows large enough.

## 29.3 `git gc` in Practice — When and How to Run It Manually

§7.6 covered the mechanics; the operational question here is _when a developer or repo administrator should intervene_ rather than trust `gc.auto`.

```bash
# Purpose: standard maintenance — safe to run any time, cheap on small/medium repos
$ git gc

# Purpose: force a run even if gc.auto's threshold hasn't been reached
$ git gc --force

# Purpose: more thorough delta search — meaningfully slower, marginally smaller output;
# reserve for deliberate one-off events (pre-major-release, pre-migration), not routine use
$ git gc --aggressive
```

Manual intervention is worth it specifically:

- **After a large history rewrite** (`filter-repo`, §28.10) — this generates a burst of loose objects that `gc.auto`'s threshold-based trigger may not immediately catch, and the old, now-unreferenced objects should be pruned promptly rather than left occupying disk.
- **After a bulk import** (converting a large SVN/Perforce history, §1.8) — same reasoning, large one-time object churn.
- **On self-hosted infrastructure**, where administrators typically schedule `git gc` (or the newer `git maintenance`, 29.3.1) as a deliberate cron job across many repositories during low-traffic windows, rather than relying purely on each individual repo's automatic trigger.

### 29.3.1 `git maintenance` — the modern scheduler

Recent Git versions ship a higher-level `git maintenance` command that can register background, scheduled maintenance tasks (gc, commit-graph updates, pack optimization) per repository, rather than relying solely on the per-operation `gc.auto` heuristic:

```bash
# Purpose: register this repository for Git's own background maintenance scheduler
$ git maintenance start
```

> 💡 **Tip:** treat `git maintenance start` as the modern, "set and forget" upgrade over manually remembering to run `git gc` periodically — it's increasingly the recommended default for actively developed repositories, especially large ones.

## 29.4 `git fsck` — Integrity Checking

```bash
# Purpose: verify the connectivity and validity of every object in the database,
# reporting anything corrupt, missing, or dangling
$ git fsck

# Purpose: also check unreachable/dangling objects, not just reachable ones —
# this is the same command §30 uses for disaster recovery
$ git fsck --full --unreachable

# Purpose: exhaustive check, including packfile internals
$ git fsck --full
```

Expected output on a healthy repository:

```
Checking object directories: 100% (256/256), done.
```

On a problem:

```
error: bad tree object HEAD^{tree}
error: <hash> is not a valid tree object
missing blob <hash>
dangling commit <hash>
```

`fsck` distinguishes several categories worth knowing precisely:

| Category                    | Meaning                                                                    | Concerning?                                                                                                                                                         |
| --------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `dangling commit/blob/tree` | A valid, uncorrupted object that nothing currently references              | Not inherently a problem — often just an abandoned detached-HEAD commit (§6.4.2) or amend/rebase leftover (§7.6.3); occasionally a deliberate recovery target (§30) |
| `missing <type> <hash>`     | Something references an object that doesn't actually exist in the database | Genuine corruption or an incomplete clone/fetch                                                                                                                     |
| `error: bad <type> object`  | An object exists but fails to parse/validate                               | Genuine corruption — file truncation, disk error, or manual tampering                                                                                               |

## 29.5 `git count-objects` — Repository Health Stats

Already introduced in §7.7; the operational habit worth calling out here is using it as the _first_ diagnostic step before reaching for `gc`, so you have a before/after comparison and aren't running maintenance blind:

```bash
$ git count-objects -v
count: 1847
size: 6820
in-pack: 92034
packs: 3
size-pack: 158200
```

A persistently high `count` (loose objects) relative to `in-pack` across normal usage is the signal that `gc.auto`'s threshold isn't triggering appropriately for this repo's activity level, and manual/scheduled maintenance (29.3, 29.3.1) is warranted.

## 29.6 Repository Size Troubleshooting — Finding Large Objects in History

The generic diagnostic pattern for "why is my `.git` directory huge": walk every object ever created, sort by size, and identify which blobs are the actual culprits — because `du -sh .git` tells you _that_ it's big, not _why_.

```bash
# Purpose: list every object reachable from every ref, along with its type and path,
# and pipe through cat-file to get sizes, then sort to find the biggest offenders
$ git rev-list --objects --all |
  git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' |
  awk '/^blob/ {print substr($0,6)}' |
  sort --numeric-sort --key=2 --reverse |
  head -20
```

Expected output (trimmed to key columns): a ranked list of `<hash> <size> <path>`, immediately revealing whether the bloat is one accidentally committed video file, years of a repeatedly-modified large binary, or genuinely just a very large amount of legitimate history.

**General diagnostic approach once the large blobs are identified:**

1. Confirm whether the large file is **still needed in the working tree today** or is purely historical baggage.
2. If it's a currently-needed large/binary asset that churns, that's a Git LFS candidate (§26.7), not a history-rewriting problem.
3. If it's genuinely accidental (a build artifact, a debug dump, a media file committed by mistake) and no longer needed even historically, it's a `git filter-repo` removal — the same class of operation as §28.10's secret remediation, with the same force-push/re-clone coordination consequences (§14.7's Golden Rule) and the same requirement to inform every collaborator.
4. If the size is simply "a large, long-lived, active repository with a lot of legitimate history," the answer isn't rewriting — it's the scaling techniques from §26: shallow clones, partial clone, sparse-checkout.

## 29.7 Common Failure Scenarios — Symptom → Diagnosis → Fix

### 29.7.1 "I'm in detached HEAD and I don't know what happened"

- **Symptom:** `git status` reports "HEAD detached at `<hash>`"; branch name is missing from the prompt/status.
- **Diagnosis:** you checked out a specific commit or tag rather than a branch (§6.4.2), likely deliberately at the time (inspecting an old release, or a CI checkout) but now need to continue working.
- **Fix:** if you want to keep any commits made here, `git switch -c <new-branch-name>` immediately; if you just want to get back to normal work, `git switch main` (or whichever branch), accepting that any uncommitted detached-HEAD commits become reflog-recoverable-only (§6.9) unless branched off first.

### 29.7.2 "I committed to the wrong branch"

- **Symptom:** a commit landed on `main` (or another shared branch) that should have gone on a feature branch.
- **Diagnosis:** forgot to `git switch -c` before starting work.
- **Fix, if not yet pushed:** `git reset --soft HEAD~1` on the wrong branch (undoes the commit, keeps changes staged, §15.4), `git switch -c correct-branch`, then commit there. **Fix, if already pushed and shared:** don't `reset` a shared branch (§14.7's Golden Rule) — instead `git revert` the mistaken commit on the wrong branch (§15.5), then cherry-pick (§17) or recreate the change on the correct branch.

### 29.7.3 "Merge conflict I can't resolve, how do I start over"

- **Symptom:** mid-merge, conflict markers are confusing, multiple files are affected, and the safest move feels like "undo all of this."
- **Diagnosis:** normal outcome of overlapping concurrent edits (§13.7-13.8); panic, not an actual error state.
- **Fix:** `git merge --abort` restores the pre-merge state exactly, with zero risk — this is always safe as long as the merge hasn't been completed with a commit yet. Same pattern for a rebase gone wrong: `git rebase --abort` (§14.8). Only after aborting and calming down should you re-attempt, ideally resolving one file at a time and checking `git status` between each.

### 29.7.4 "My repo is huge and slow"

- **Symptom:** `clone`, `status`, or `checkout` taking noticeably longer than expected.
- **Diagnosis:** apply 29.5-29.6's process — check loose object count first, then hunt for outsized historical blobs.
- **Fix:** `git gc` if it's simply unpacked/unoptimized storage; large-blob removal via `filter-repo` (28.10) or migration to LFS (§26.7) if specific objects are the culprit; shallow/partial clone and sparse-checkout (§26.4-26.6) if the repository is legitimately large and the real fix is not fetching/materializing all of it in the first place.

### 29.7.5 "Permission denied (publickey)"

- **Symptom:** `git fetch`/`push` over SSH fails with `Permission denied (publickey). fatal: Could not read from remote repository.`
- **Diagnosis:** the SSH key being offered doesn't match a key registered with the remote host — most commonly: no key generated yet, the public key was never added to the platform (§8.7.1), the wrong key is being offered when multiple exist, or the SSH agent isn't running/loaded with the key.
- **Fix:**

  ```bash
  # Purpose: confirm the exact identity Git/SSH will authenticate with
  $ ssh -T git@github.com

  # Purpose: verify the agent has the intended key loaded
  $ ssh-add -l

  # Purpose: explicitly load the key if it's missing from the agent
  $ ssh-add ~/.ssh/id_ed25519
  ```

  If multiple keys exist for different accounts/hosts, an SSH config (`~/.ssh/config`) `Host` block specifying `IdentityFile` per host is the durable fix, rather than repeatedly `ssh-add`ing the right key by hand.

## 29.8 Performance Configuration Knobs

Beyond the scaling techniques already covered in depth in §26, a few configuration-level knobs matter specifically for day-to-day command speed on large working trees:

| Setting                                      | Effect                                                                                                                                                                                                                                                                                                       |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `core.fsmonitor`                             | Delegates working-tree change detection to a filesystem watcher (built-in since Git 2.37, or the older Watchman integration) instead of Git scanning every file on every `status` — the single biggest `status`/`add` speedup on repositories with very large working trees (hundreds of thousands of files) |
| `feature.manyFiles`                          | A convenience meta-setting that bundles several defaults (including enabling `fsmonitor`-friendly behavior and the untracked-cache) tuned for exactly this large-file-count scenario                                                                                                                         |
| `core.untrackedCache`                        | Caches which paths are untracked between runs, avoiding a full untracked-file re-scan every time                                                                                                                                                                                                             |
| Partial clone / sparse-checkout (§26.5-26.6) | Not a config knob so much as an architectural mitigation — reduces how much history/working-tree content exists locally at all, which is the more fundamental fix once a repository crosses from "large" into "too large for a full clone to be reasonable"                                                  |

```bash
# Purpose: enable the bundle of large-repository-friendly defaults in one setting
$ git config --global feature.manyFiles true
```

## 29.9 Hands-On Example — Diagnosing and Cleaning a Bloated Repository

```bash
$ git count-objects -v
count: 4200
size: 812000
in-pack: 0
packs: 0

# Find the worst offenders
$ git rev-list --objects --all |
  git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' |
  awk '/^blob/ {print substr($0,6)}' | sort -k2 -rn | head -3
a1b2c3d4... 500000000 assets/demo-recording.mp4
e5f6a7b8... 12000     src/app.js
c9d0e1f2... 8400      README.md

# The 500MB video is clearly the culprit — remove it from all of history
$ git filter-repo --path assets/demo-recording.mp4 --invert-paths

$ git reflog expire --expire=now --all
$ git gc --prune=now
$ git count-objects -v
count: 0
size: 0
in-pack: 3421
packs: 1
```

Exactly as §28.10-28.11 describe for secret remediation, this rewrite changes every commit hash from the point the file was introduced onward — the same force-push/re-clone coordination under the Golden Rule (§14.7) applies here too, even though the motive is disk space rather than security.

## 29.10 Troubleshooting Reference Table

| Symptom                                                 | Likely cause                                                      | Fix                                                                                                                     |
| ------------------------------------------------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `fatal: bad object <hash>`                              | Corruption — truncated file, disk error, interrupted operation    | `git fsck --full`; if the object is unrecoverable locally, re-fetch from a remote or another collaborator's clone (§30) |
| `warning: There are too many unreachable loose objects` | Past `gc.auto`'s threshold, not yet cleaned                       | `git gc` manually, or wait for the next automatic trigger                                                               |
| `status`/`add` noticeably slow on a large working tree  | No filesystem monitor caching, huge file count scanned every time | `git config core.fsmonitor true` and/or `feature.manyFiles true`                                                        |
| Clone takes far longer than expected                    | Full history of a large/old repository being fetched in full      | Shallow clone (`--depth`) or partial clone (`--filter=blob:none`), §26.4-26.5                                           |
| `Permission denied (publickey)` on fetch/push           | SSH key not registered, not loaded in agent, or wrong key offered | `ssh -T git@<host>` to diagnose; `ssh-add`; per-host `~/.ssh/config` entries                                            |
| Merge/rebase feels unrecoverable mid-conflict           | Normal conflict-resolution overwhelm, not an actual broken state  | `git merge --abort` / `git rebase --abort` — always safe before completion                                              |

## 29.11 Interview Questions

**[Beginner] Q1. What does `git gc` actually do, and is it something you need to run manually?**
**Model answer:** `git gc` repacks loose objects into compressed packfiles, prunes objects that are no longer reachable from any ref or protected reflog entry, and compacts the refs into `packed-refs`. Git runs it automatically in the background once enough loose objects accumulate, so for most day-to-day work you never need to invoke it manually. Manual runs are worth it after events that generate a large burst of loose objects that the automatic threshold might not immediately catch — a large history rewrite, a bulk import, or as part of scheduled maintenance on busy self-hosted infrastructure.

**[Beginner] Q2. You run `git status` and see "HEAD detached at a3f8e21." Is something wrong?**
**Model answer:** Not necessarily — it means HEAD is pointing directly at a commit instead of at a branch name, which happens whenever you check out a specific commit or a tag rather than a branch. It's completely normal in contexts like CI builds (which deliberately check out one exact commit) or inspecting an old release. The thing to be careful about is committing while in this state: those commits aren't tracked by any branch, so if I want to keep them I need to run `git switch -c <name>` before switching to another branch, otherwise they become findable only via the reflog.

**[Intermediate] Q3. How would you find out why a repository's `.git` directory is unexpectedly large?**
**Model answer:** First I'd run `git count-objects -v` to see whether it's simply a large number of unpacked loose objects, which a plain `git gc` would fix immediately. If the size persists after packing, I'd walk the full object history with `git rev-list --objects --all` piped through `git cat-file --batch-check`, filter for blobs, and sort by size to find the specific large objects — often one accidentally committed binary or media file rather than genuinely large legitimate history. From there the fix depends on whether that content is still needed: if it's an actively used large/binary asset, Git LFS is the right tool; if it's dead weight from a past mistake, `git filter-repo` can strip it from all of history, though that requires the same force-push and full-team re-clone coordination as any history rewrite.

**[Intermediate] Q4. A teammate gets "Permission denied (publickey)" trying to push. What do you have them check, in order?**
**Model answer:** First, `ssh -T git@<host>` to see exactly what identity, if any, the remote host recognizes them as — this immediately tells you whether it's an authentication problem at all versus something else being misreported. Second, `ssh-add -l` to confirm their SSH agent actually has a key loaded — a generated key that was never added to the running agent is a common gap. Third, confirm the matching public key is actually registered in their account settings on the hosting platform, not just generated locally. Fourth, if they have multiple SSH keys for different hosts or accounts, check whether the wrong one is being offered by default, which is best solved durably with per-host `IdentityFile` entries in `~/.ssh/config` rather than manually managing which key is loaded each time.

**[Senior] Q5. Your CI pipeline's checkout step has gotten noticeably slower over the past year as the repository has grown. Walk through your diagnostic and remediation approach.**
**Model answer:** I'd first separate two possible causes: is the repository genuinely larger (more history, more/bigger files), or is it the same logical size but poorly packed/maintained? `git count-objects -v` and a size-sorted object scan (§29.6's `rev-list`/`cat-file` pipeline) answer that quickly. If it's poor packing, scheduled `git gc` or `git maintenance` on the hosting side fixes it without touching CI at all. If it's genuine growth, I'd challenge whether CI actually needs full history at all — most CI jobs only need the working tree at one commit, which makes shallow clone (`--depth=1`) or, better, partial clone (`--filter=blob:none` with sparse-checkout if only part of the tree is needed for a given job) the right fix, since it avoids fetching object content the job will never use rather than trying to make fetching all of it faster. If a specific class of large binary asset is driving growth and is actively churning (not just legacy weight), I'd propose migrating it to Git LFS so ordinary clones/checkouts don't pay for it by default. I'd avoid reaching for history rewriting here unless the growth is traceable to specific accidental commits — rewriting is disruptive and requires full-team coordination, and is the wrong tool for "the repository is just larger now than it used to be."

## 29.12 Common Misconceptions

1. **"`git gc` is dangerous and should be avoided."** It's a safe, routine operation that respects reflog-protected objects (§7.6.3) and never removes anything still reachable or within its retention window; it runs automatically for exactly this reason.
2. **"A slow repository always means corruption."** Corruption is rare; slowness is far more commonly unpacked loose objects, an unusually large file-count working tree without `fsmonitor`, or genuinely large history that needs a scaling technique (§26), not a repair.
3. **"`fsck` reporting dangling commits means something is broken."** Dangling objects are frequently harmless, expected leftovers (abandoned detached-HEAD work, amend/rebase remnants) — not evidence of corruption; only `missing`/`bad object` errors indicate an actual integrity problem.
4. **"Aborting a merge or rebase mid-conflict is risky."** `--abort` on either is specifically designed to be fully safe and restore the exact pre-operation state, as long as the operation hasn't been completed with a final commit yet — it's the correct move whenever conflict resolution feels overwhelming, not a last resort.
5. **"Permission denied (publickey) means my account doesn't have access."** It almost always means the _SSH key being offered_ isn't recognized, not that the account itself lacks permission — a distinct, and much more common, failure mode.

## 29.13 🔑 Key Takeaways

- `git gc`, `git fsck`, and `git count-objects` are the core maintenance/diagnostic trio: repack and prune, verify integrity, and report current health stats respectively; `git maintenance start` is the modern scheduled-background alternative to manual `gc` runs.
- Repository bloat is diagnosed by walking `git rev-list --objects --all` through `git cat-file --batch-check`, sorted by size — this pinpoints the actual offending blobs rather than guessing.
- The recurring real-world failure scenarios — detached HEAD confusion, wrong-branch commits, conflict panic, and SSH auth failures — each have a small, learnable, reliable fix rooted in concepts from earlier sections (§6, §13-15, §8).
- `git merge --abort` / `git rebase --abort` are always safe before the operation is finalized with a commit — the correct first response to conflict overwhelm, not a last resort.
- `core.fsmonitor` and `feature.manyFiles` meaningfully speed up day-to-day commands on large working trees; genuine scale problems are better solved architecturally with shallow/partial clone and sparse-checkout (§26) than with configuration tuning alone.

## 29.14 Related Concepts & What's Next

Maintenance and troubleshooting cover the routine and the recoverable; §30 goes one level further into genuine disaster recovery — commits lost so thoroughly they've fallen out of even the reflog, and repository corruption severe enough that local recovery isn't possible at all, requiring a re-fetch from a remote or a restored backup as the last line of defense.
