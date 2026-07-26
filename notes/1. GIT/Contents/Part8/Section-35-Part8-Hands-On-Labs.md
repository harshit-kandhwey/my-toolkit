# Section 35 (Part 8): Hands-On Labs & Mini-Projects (Beginner → Production-Style)

## 1. Purpose of This Section

**Plain language:** Reading about Git builds recognition; running Git builds fluency. This section is a sequence of self-contained labs, each isolated in its own scratch directory, that turn the concepts from earlier sections into muscle memory — exactly the kind of lived experience §34.2 says interviewers can detect the presence or absence of.

**Precise:** Each lab states a goal, the prerequisite sections to have read first, numbered steps using real `git` commands, and a verification check describing exactly what you should observe if you did it correctly. Labs increase in difficulty and are designed to be run in order, since later labs assume the environment/skills of earlier ones. Every lab uses a disposable directory outside any real project — nothing here touches your actual repositories.

> 💡 **Tip:** Do these in an actual terminal, not by reading the commands and imagining the output. The value is entirely in watching real state change and occasionally hitting an unexpected result you have to reason about.

## 2. Lab Environment Setup

```bash
# Purpose: create one parent scratch directory to hold every lab, isolated
# from any real project
$ mkdir -p ~/git-labs && cd ~/git-labs

# Purpose: confirm identity is configured (needed for every commit below)
$ git config --global user.name
$ git config --global user.email
```

If either is empty, set them (§8) before continuing — every lab below assumes commits succeed without prompting for identity.

## 3. Lab 1 (Beginner) — The Object Model, Made Concrete

**Goal:** See blobs, trees, and commits as literal objects on disk, connecting §5's theory to physical files.
**Prerequisites:** §4 (three areas), §5 (object model).

```bash
$ mkdir lab1-objects && cd lab1-objects && git init -q

$ echo "hello git" > file.txt
$ git add file.txt
$ git commit -qm "First commit"

# Find the commit's hash
$ git log --oneline
```

Take the commit hash from the log output and inspect it with plumbing commands:

```bash
# Purpose: show the commit object's raw content — tree, parent (none, it's the
# root commit), author, committer, message
$ git cat-file -p <commit-hash>

# Purpose: show what type of object a hash refers to
$ git cat-file -t <commit-hash>

# Purpose: list the tree the commit points to — one entry per file/dir
$ git cat-file -p <commit-hash>^{tree}

# Purpose: show the blob's raw content directly, by its own hash from the
# tree listing above
$ git cat-file -p <blob-hash-from-tree-listing>
```

Now add a second file with identical content to an existing one elsewhere in the tree, to observe content-addressing directly:

```bash
$ cp file.txt file-copy.txt
$ git add file-copy.txt
$ git commit -qm "Duplicate content"
$ git cat-file -p HEAD^{tree}
```

**What you should observe:** `git cat-file -p <commit-hash>` prints exactly the structure §5 describes — a `tree` line, no `parent` line (root commit), then `author`/`committer` lines and the message. The tree listing for the second commit shows **two file entries pointing at the same blob hash** — `file.txt` and `file-copy.txt` share one blob object, because Git addresses content, not paths; identical content is stored exactly once regardless of filename. If you don't see the same hash for both entries, re-check that the file contents are byte-identical (no trailing newline difference).

## 4. Lab 2 (Beginner/Intermediate) — Branching and a Deliberate Merge Conflict

**Goal:** Create a real conflict, read the markers, resolve it correctly.
**Prerequisites:** §12 (branching), §13 (merging).

```bash
$ mkdir lab2-conflict && cd lab2-conflict && git init -q
$ echo "line one" > notes.txt && git add . && git commit -qm "base"

$ git switch -c feature-a
$ echo "feature A change" >> notes.txt
$ git commit -qam "feature-a edit"

$ git switch main
$ echo "main change" >> notes.txt
$ git commit -qam "main edit"

$ git merge feature-a
```

**Expected output:**

```
Auto-merging notes.txt
CONFLICT (content): Merge conflict in notes.txt
Automatic merge failed; fix conflicts and then commit the result.
```

```bash
$ cat notes.txt
```

You'll see conflict markers (`<<<<<<< HEAD`, `=======`, `>>>>>>> feature-a`). Resolve by editing the file to keep both lines sensibly, then:

```bash
$ printf "line one\nmain change\nfeature A change\n" > notes.txt
$ git add notes.txt
$ git status
$ git commit
```

**What you should observe:** `git status` before committing lists `notes.txt` under "Unmerged paths" until you `git add` it; after `git add`, status shows it as ready to commit. The completed commit is a merge commit with **two parents** — verify with `git log --graph --oneline -3`, which should show the graph fork and rejoin exactly as diagrammed in §13.

## 5. Lab 3 (Intermediate) — Interactive Rebase to Clean Up History

**Goal:** Turn a messy sequence of WIP commits into clean, atomic ones before an imagined pull request.
**Prerequisites:** §14 (rebasing), especially 14.5.

```bash
$ mkdir lab3-rebase && cd lab3-rebase && git init -q
$ echo "base" > app.js && git add . && git commit -qm "initial"

$ echo "function login() {}" >> app.js && git commit -qam "wip login"
$ echo "  // fix typo" >> app.js && git commit -qam "fix typo"
$ echo "function logout() {}" >> app.js && git commit -qam "wip logout"
$ echo "  // add comment" >> app.js && git commit -qam "small tweak"

$ git log --oneline
```

You should see five commits, the last four messy. Start an interactive rebase over the four messy ones:

```bash
$ git rebase -i HEAD~4
```

In the editor, change the plan to squash the "fix typo" and "small tweak" commits into their preceding commits:

```
pick <hash1> wip login
squash <hash2> fix typo
pick <hash3> wip logout
squash <hash4> small tweak
```

Git will pause twice to let you write combined commit messages — write clean, atomic ones (e.g., "Add login function", "Add logout function").

```bash
$ git log --oneline
```

**What you should observe:** the branch now has three commits total (initial + two clean feature commits) instead of five, and every commit after the rebase point has a **new hash** — including "wip login," even though its content-diff never changed, exactly per §14.3's explanation of why parent-hash chaining cascades new hashes through an entire replayed sequence.

## 6. Lab 4 (Intermediate) — Break Something, Recover via Reflog

**Goal:** Deliberately lose commits with `reset --hard`, then recover them — the single most valuable recovery sequence to have reflexive.
**Prerequisites:** §6.6 (reflog), §15 (reset), §30 (disaster recovery, if written).

```bash
$ mkdir lab4-recovery && cd lab4-recovery && git init -q
$ echo "v1" > important.txt && git add . && git commit -qm "commit 1"
$ echo "v2" > important.txt && git commit -qam "commit 2"
$ echo "v3" > important.txt && git commit -qam "commit 3 - the important one"

$ git log --oneline
```

Now simulate the mistake:

```bash
$ git reset --hard HEAD~2
$ git log --oneline
$ cat important.txt
```

**Expected output at this point:** only "commit 1" remains in the log, `important.txt` shows "v1" — commits 2 and 3 appear gone from both history and the working directory.

Recover:

```bash
$ git reflog
```

**Expected output (abbreviated):**

```
a1b2c3d HEAD@{0}: reset: moving to HEAD~2
9f2e1a4 HEAD@{1}: commit: commit 3 - the important one
7c2a9f1 HEAD@{2}: commit: commit 2
...
```

```bash
# Purpose: move the branch back to the commit right before the destructive reset
$ git reset --hard HEAD@{1}
$ git log --oneline
$ cat important.txt
```

**What you should observe:** after the recovery `reset --hard`, "commit 3 - the important one" is back at the tip, and `important.txt` again shows "v3." This confirms §15.4's claim directly: `reset` never deletes the commits it moves away from — it only relabels which one the branch pointer names — and the reflog is what lets you find them again. Note this only works because garbage collection hasn't run; in production, act quickly.

## 7. Lab 5 (Advanced) — Two "Developers," One Bare Repo, a Conflicting Push

**Goal:** Simulate real multi-developer remote collaboration, including a rejected push, entirely on one machine.
**Prerequisites:** §20 (remotes), §9 (bare vs non-bare repos).

```bash
$ mkdir lab5-remote && cd lab5-remote

# Purpose: create a BARE repo acting as the shared "origin" — no working
# directory, exactly the shape a self-hosted Git server uses (§9)
$ git init -q --bare origin.git

# Purpose: two independent clones simulate two developers
$ git clone -q origin.git dev-a
$ git clone -q origin.git dev-b
```

Developer A commits and pushes first:

```bash
$ cd dev-a
$ echo "shared file" > shared.txt && git add . && git commit -qm "dev-a: initial"
$ git push -q origin main
```

Developer B, without pulling first, makes a conflicting local commit and tries to push:

```bash
$ cd ../dev-b
$ git pull -q origin main   # syncs to dev-a's commit first, for this lab
$ echo "dev-b addition" >> shared.txt && git commit -qam "dev-b: addition"

$ echo "another dev-a commit" >> shared.txt
```

To actually see a rejected push, simulate A pushing again before B does, without B fetching in between:

```bash
$ cd ../dev-a
$ echo "dev-a: second change" >> shared.txt && git commit -qam "dev-a: second change"
$ git push -q origin main

$ cd ../dev-b
$ echo "dev-b: unrelated change" >> shared.txt && git commit -qam "dev-b: local change, stale base"
$ git push origin main
```

**Expected output:**

```
! [rejected]        main -> main (fetch first)
error: failed to push some refs to '...origin.git'
hint: Updates were rejected because the remote contains work that you do
hint: not have locally.
```

```bash
# Purpose: sync first, then push — the correct response to a rejected push
$ git pull origin main
$ git push origin main
```

**What you should observe:** the first push attempt is rejected because `origin/main` moved since dev-b's last fetch — Git refuses to silently overwrite dev-a's second commit. `git pull` (fetch + merge) brings both histories together locally, possibly opening an editor for a merge commit message if the changes don't cleanly auto-merge; only after that does the second push succeed. This is the everyday, non-catastrophic version of the coordination problem §34.6's force-push scenario escalates.

## 8. Lab 6 (Advanced) — A Working Pre-Commit Hook That Blocks a Forbidden Word

**Goal:** Write a functioning hook that simulates basic secret detection, tying §24's hooks to §28's security material.
**Prerequisites:** §24 (hooks), §28 (security), if written.

```bash
$ mkdir lab6-hooks && cd lab6-hooks && git init -q
```

Create the hook file directly (hooks are plain executable scripts inside `.git/hooks`):

```bash
$ cat > .git/hooks/pre-commit << 'EOF'
#!/bin/sh
# Blocks any commit whose staged content contains the literal string
# "SECRET_KEY=" — a toy stand-in for real secret-scanning tools.
if git diff --cached | grep -q "SECRET_KEY="; then
  echo "COMMIT BLOCKED: staged changes contain a forbidden pattern (SECRET_KEY=)."
  echo "Remove the secret and re-stage before committing."
  exit 1
fi
exit 0
EOF
$ chmod +x .git/hooks/pre-commit
```

Test that it blocks a bad commit:

```bash
$ echo "SECRET_KEY=abc123" > config.txt
$ git add config.txt
$ git commit -m "add config"
```

**Expected output:**

```
COMMIT BLOCKED: staged changes contain a forbidden pattern (SECRET_KEY=).
Remove the secret and re-stage before committing.
```

Confirm nothing was committed, then fix and retry:

```bash
$ git log --oneline    # no new commit exists
$ echo "SAFE_CONFIG=abc123" > config.txt
$ git add config.txt
$ git commit -qm "add config"
$ git log --oneline    # commit now exists
```

**What you should observe:** the first commit attempt is refused entirely (exit code 1 from the hook aborts `git commit` before it creates anything), while identical content minus the forbidden pattern commits normally. Note per §4.9's clarification that the hook reads `git diff --cached` — the **index**, not just working-directory files — which matters for correctness (a hook that scanned working-directory files instead could pass content that isn't actually what's about to be committed). This is a local safety net only; real secret-detection setups (§28) pair this with server-side scanning too, since hooks in `.git/hooks` are not version-controlled or transferred by clone, and a developer can bypass them with `--no-verify` — the `pre-commit` framework or Husky (§24) solve the distribution problem, but not the bypass problem, which is why CI-side scanning remains necessary.

## 9. Lab 7 (Capstone) — A Small Project With Branching Discipline and a CI-Like Pre-Push Check

**Goal:** Combine a branching strategy, protected-branch-style discipline, and an automated check into one coherent small workflow — the closest this lab sequence gets to a real team setup.
**Prerequisites:** §22 (branching strategies), §23 (hosting/protected branches), §24 (hooks), §25 (CI/CD), all ideally read first.

```bash
$ mkdir lab7-capstone && cd lab7-capstone
$ git init -q --bare origin.git
$ git clone -q origin.git work && cd work
```

Set up a minimal "application" with a trivial test script that a pre-push check will run:

```bash
$ mkdir src
$ cat > src/app.js << 'EOF'
function add(a, b) { return a + b; }
module.exports = { add };
EOF
$ cat > test.sh << 'EOF'
#!/bin/sh
# Toy "test suite": fails if app.js contains the word TODO, simulating a
# CI gate that blocks unfinished work from reaching the shared branch.
if grep -rq "TODO" src/; then
  echo "TEST FAILED: unresolved TODO found in src/"
  exit 1
fi
echo "All checks passed."
exit 0
EOF
$ chmod +x test.sh
$ git add . && git commit -qm "initial project skeleton"
$ git push -q origin main
```

Add a pre-push hook that runs the "test suite" before allowing a push — a local stand-in for a CI gate:

```bash
$ cat > .git/hooks/pre-push << 'EOF'
#!/bin/sh
echo "Running pre-push checks..."
./test.sh
EOF
$ chmod +x .git/hooks/pre-push
```

Now follow trunk-based, short-lived-branch discipline (§22.4-style) for a feature:

```bash
$ git switch -c feature/subtract
$ cat > src/subtract.js << 'EOF'
// TODO: implement subtract
EOF
$ git add . && git commit -qm "wip: start subtract feature"
$ git push origin feature/subtract
```

**Expected output:**

```
Running pre-push checks...
TEST FAILED: unresolved TODO found in src/
error: failed to push some refs
```

Fix the "failing test" and push again:

```bash
$ cat > src/subtract.js << 'EOF'
function subtract(a, b) { return a - b; }
module.exports = { subtract };
EOF
$ git add . && git commit -qm "Implement subtract function"
$ git push origin feature/subtract
```

**Expected output:**

```
Running pre-push checks...
All checks passed.
... (push succeeds)
```

Finally, merge the feature into `main` the way a reviewed pull request would (simulated locally, since this lab has no real hosting platform):

```bash
$ git switch main
$ git merge --no-ff feature/subtract -m "Merge feature/subtract: add subtract function"
$ git push origin main
$ git log --graph --oneline --all
```

**What you should observe:** the push carrying the unresolved `TODO` is blocked client-side before it ever reaches `origin.git`, exactly mirroring what a required CI status check enforces server-side in a real platform (§23, §25) — the difference is that a real pre-push hook is easy to bypass locally (`--no-verify`), which is precisely why production setups enforce the equivalent check as a **required status check on the server**, not merely as a local hook; this lab's version is for building the mental model, not as a substitute for real branch protection. The final graph shows a short-lived feature branch merging cleanly into `main` with `--no-ff`, preserving the fact that it was a distinct unit of work (§13, §22).

## 10. Troubleshooting Across Labs

| Symptom                                                    | Likely cause                                                                    | Fix                                                                                                                                                                   |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Hook doesn't run at all                                    | Not executable, or wrong filename                                               | `chmod +x .git/hooks/<name>`; filename must exactly match (`pre-commit`, `pre-push`, no extension)                                                                    |
| `git rebase -i` opens an unfamiliar or unusable editor     | `core.editor` unset, defaults to something unexpected (e.g., vi, if unfamiliar) | `git config --global core.editor "code --wait"` or your preferred editor, per §8                                                                                      |
| Reflog entry from Lab 4 not found                          | Reflog expired, or a different repo/branch than expected                        | Reflog is per-repo and per-ref; confirm you're in the right directory and check `git reflog show <branch>` explicitly, not just `git reflog` (which defaults to HEAD) |
| Push in Lab 5/7 succeeds when it should have been rejected | Steps run out of order, or an intermediate `pull` already synced state          | Re-run from a fresh `origin.git` and clones; ordering matters for reproducing the rejection                                                                           |

## 11. Interview Questions

**[Beginner] Q1. Why is it valuable to inspect objects with `git cat-file` instead of only using `git log`/`git show`?**
**Model answer:** `git log` and `git show` are user-facing views built on top of the object model, formatted for readability. `git cat-file -p` shows the actual raw content of blob, tree, and commit objects — seeing that a commit object literally contains a `tree` line and `parent` line as plain text, or that two differently-named files with identical content share one blob hash, converts the object model from an abstract diagram (§5) into something directly observed, which is far stickier knowledge than reading a description.

**[Intermediate] Q2. In Lab 6's hook, why does it matter that the hook reads `git diff --cached` rather than scanning the working directory?**
**Model answer:** `git diff --cached` (equivalently `git diff --staged`) shows exactly what's in the index — what will actually become part of the next commit. Scanning working-directory files instead could either miss a forbidden pattern that's staged but has since been edited out of the working copy, or flag a pattern that exists in the working directory but was never staged and isn't part of this commit at all. A correctness-sensitive hook must check the same content the commit is actually going to contain, which is the index, not the working tree — the same distinction §4.9 raises about pre-commit hooks generally.

**[Senior] Q3. Lab 7's pre-push hook can be bypassed with `--no-verify`. Given that, what's actually the point of writing it, versus relying purely on server-side CI?**
**Model answer:** A local pre-push (or pre-commit) hook gives fast, offline feedback before a network round trip and a CI queue — catching an obvious mistake in seconds rather than minutes, and without consuming CI capacity for something trivially detectable locally. But because it's bypassable and, crucially, not distributed automatically to every clone (hooks live in `.git/hooks`, which clone does not populate from a remote), it cannot be the sole enforcement mechanism for anything that matters — that has to be a server-side required status check tied to branch protection (§23, §25), which no individual developer can opt out of. The correct mental model is defense in depth: local hooks for fast feedback and developer convenience, server-side checks for actual enforcement.

## 12. Common Misconceptions

1. **"Running through these labs once means I understand Git."** Fluency comes from repetition and from occasionally deviating from the script and reasoning through an unexpected result — treat these as a starting template, not a one-time checkbox.
2. **"A pre-push hook is a real substitute for CI."** As Lab 7 and Q3 above cover, hooks are bypassable and not distributed by clone; they complement server-side enforcement, they don't replace it.
3. **"Reflog recovery always works."** It works only until garbage collection prunes unreachable objects past their grace period (default two weeks for unreachable objects) — it's a safety net with a time limit, not a permanent undo history.

## 13. 🔑 Key Takeaways

- Object-model labs (35.3) convert §5's abstract diagrams into observed fact — do this one first if you skip everything else.
- The reflog recovery sequence in Lab 4 (35.6) is the single most valuable reflex from this entire lab set; rehearse it until it's automatic.
- Lab 5's rejected push and Lab 7's blocked push both demonstrate the same underlying principle — automated checks (server-enforced sync state, or a local/CI test gate) exist to catch problems before they reach shared history, not after.
- Hooks (Lab 6, Lab 7) are genuinely useful for fast local feedback but are not a substitute for server-side, non-bypassable enforcement — that distinction is a recurring senior-level interview probe (§35.11 Q3).

## 14. Related Concepts

Each lab names its prerequisite sections inline. For the theory these labs made concrete, revisit: §4-5 (objects), §13-14 (merge/rebase), §6.6/§15 (reflog/reset), §20 (remotes), §24 (hooks), §22-23 (branching strategy and hosting platform enforcement), §25 (CI/CD). For interview framing of the same material, see §34. For the corpus-wide synthesis, see §36.
