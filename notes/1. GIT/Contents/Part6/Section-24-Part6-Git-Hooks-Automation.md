# Section 24 (Part 6): Git Hooks & Automation

## 24.1 Definition

**Plain language:** A Git hook is a script Git runs automatically at a specific point in its own workflow — right before a commit is recorded, right after a checkout, right before a push leaves your machine — letting you inject custom checks or automation into normal Git operations without changing Git itself.

**Precise:** Hooks are executable scripts (any language, provided the file has a shebang and executable permission, or is a recognized executable on Windows) living in `.git/hooks/`, named after the exact event they respond to (`pre-commit`, `commit-msg`, `pre-push`, and about a dozen others). Git invokes the matching script at that point in the operation, passing relevant arguments/stdin, and — for most hooks — treats a non-zero exit code as "abort the operation."

## 24.2 Why It Exists / Problem It Solves

1. **Shifting checks left.** Waiting for CI to reject a badly formatted commit or a failing test wastes a round trip (push, wait, get a red build, fix, push again). A local hook catches the same problem in seconds, before anything leaves the machine.
2. **Enforcing conventions without relying on memory.** Commit message formats (§18's Conventional Commits), no-secrets-in-diff checks, and linting are easy to forget under deadline pressure; a hook makes them automatic rather than aspirational.
3. **Server-side gatekeeping.** A hosting server can refuse pushes that don't meet policy (no force-pushes to `main`, no oversized files, no unsigned commits) at the one point that's actually enforceable for everyone, not just cooperative clients.
4. **Automation triggers.** Hooks are also a convenient place to fire side effects — updating a deployed working tree after a push, notifying a chat channel, regenerating derived files after checkout.

## 24.3 Where Hooks Live and How Git Finds Them

Every repository's `.git/hooks/` directory ships with several `*.sample` files on `git init`/`git clone` — inert examples showing the expected interface for each hook, not active until renamed (drop the `.sample` suffix) and made executable.

```bash
$ ls .git/hooks/
applypatch-msg.sample      pre-merge-commit.sample
commit-msg.sample          pre-push.sample
fsmonitor-watchman.sample  pre-rebase.sample
post-update.sample         pre-receive.sample
pre-applypatch.sample      prepare-commit-msg.sample
pre-commit.sample          update.sample
```

> ⚠️ **Critical clarification: hooks are not versioned by default.** `.git/` is never committed — it is the repository's private local metadata, not tracked content (§4). That means a `pre-commit` script you write and rely on lives only on your machine; a teammate cloning the same repository gets none of it, silently. This single fact is the reason 24.5's frameworks exist at all — "just write a hook" doesn't scale past a solo project.

## 24.4 Client-Side Hooks

These fire on the developer's own machine during ordinary local operations.

| Hook                 | Fires                                                                                               | Typical use                                                                             | Can abort the operation?                         |
| -------------------- | --------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- | ------------------------------------------------ |
| `pre-commit`         | After `git commit` is invoked, before the commit message editor opens                               | Linting, formatting, running fast unit tests, blocking secrets                          | Yes (non-zero exit)                              |
| `prepare-commit-msg` | Before the commit message editor opens, after the default message is generated                      | Pre-populating a message template (e.g., injecting a ticket ID from the branch name)    | Yes, but rarely used for that purpose            |
| `commit-msg`         | After the message is written, before the commit is finalized                                        | Validating message format — e.g., enforcing Conventional Commits (§18)                  | Yes                                              |
| `post-commit`        | After the commit is recorded                                                                        | Notifications, triggering local build tooling                                           | No (informational only; commit already happened) |
| `post-checkout`      | After `git checkout`/`git switch` completes                                                         | Regenerating environment files, warning about stale dependencies, cache invalidation    | No                                               |
| `post-merge`         | After a merge completes                                                                             | Reinstalling dependencies if a lockfile changed                                         | No                                               |
| `pre-push`           | Before refs are pushed to a remote, after the remote has been contacted but before objects transfer | Running the full test suite, blocking pushes of `WIP` commits or protected branch names | Yes                                              |
| `pre-rebase`         | Before a rebase begins                                                                              | Blocking rebase of already-published branches                                           | Yes                                              |

```bash
# .git/hooks/pre-commit — must be executable: chmod +x .git/hooks/pre-commit
#!/usr/bin/env bash
set -e
echo "Running linter before commit..."
npx eslint . --max-warnings=0
```

**Purpose:** blocks the commit if linting fails, catching style/quality issues before they're recorded at all.

```bash
$ git commit -m "Add cart discount logic"
Running linter before commit...
/src/cart.js
  12:1  error  'total' is defined but never used  no-unused-vars

husky - pre-commit hook exited with code 1 (error)
```

**Expected output:** the commit is refused; nothing is recorded until the linter passes.

> 💡 **Tip:** Hooks receive their input differently per hook — some via command-line arguments, some via stdin, some via environment variables. `commit-msg`, for example, receives the path to a temporary file containing the message as its one argument, letting the hook read and even rewrite that file before Git proceeds.

## 24.5 The Versioning Problem — and Its Standard Solutions

Because `.git/hooks/` is local-only (24.3), teams needing hooks to be **shared, versioned, and automatically installed** for every contributor rely on one of three approaches.

### 24.5.1 The `pre-commit` framework (language-agnostic, Python-distributed)

A popular, language-agnostic tool (itself named `pre-commit`, distinct from the git hook of the same name) that reads a versioned config file and manages installing/running many small check "hooks" — its own plugin ecosystem, not limited to Git's `pre-commit` event despite the name overlap.

```yaml
# .pre-commit-config.yaml — committed to the repo, so every clone has it
repos:
  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v4.5.0
    hooks:
      - id: trailing-whitespace
      - id: end-of-file-fixer
      - id: check-added-large-files
  - repo: https://github.com/psf/black
    rev: 23.9.1
    hooks:
      - id: black
```

```bash
# Purpose: install the framework's actual .git/hooks/pre-commit shim once per clone
$ pip install pre-commit
$ pre-commit install
pre-commit installed at .git/hooks/pre-commit
```

**Expected outcome:** `pre-commit install` writes a small dispatcher script into `.git/hooks/pre-commit` that, on every commit, reads `.pre-commit-config.yaml` and runs the configured checks — this is the actual mechanism that bridges "config is versioned" to "the local hook exists," and it must be re-run once per fresh clone.

### 24.5.2 Husky (Node.js ecosystem)

Husky ties hook installation to `npm install` via `package.json`, so any contributor who installs project dependencies gets working hooks for free, without a separate manual step.

```json
// package.json (relevant excerpt)
{
  "scripts": { "prepare": "husky install" }
}
```

```bash
# .husky/pre-commit — this file itself IS committed to the repo
#!/usr/bin/env sh
. "$(dirname "$0")/_/husky.sh"
npx lint-staged
```

**Mechanism:** Husky's own scripts live in a committed `.husky/` directory (ordinary tracked files, unlike `.git/hooks/`); its `install` step (run automatically via npm's `prepare` lifecycle script) points Git's `core.hooksPath` (24.5.3) at that committed directory, so Git executes the versioned scripts directly.

### 24.5.3 `core.hooksPath` — the manual, tool-free alternative

Both frameworks above ultimately lean on a single underlying Git config option: `core.hooksPath` redirects Git to look for hooks in any directory you choose, instead of the fixed `.git/hooks/`.

```bash
# Purpose: point Git at a committed hooks directory instead of the local-only default
$ git config core.hooksPath .githooks
```

```bash
$ mkdir .githooks
$ cat > .githooks/pre-commit <<'EOF'
#!/usr/bin/env bash
npx eslint .
EOF
$ chmod +x .githooks/pre-commit
$ git add .githooks
$ git commit -m "chore: add versioned pre-commit hook"
```

**Trade-off:** this requires no external tool at all — just a config setting — but that setting itself is **per-clone local config**, so every contributor must still run the one `git config core.hooksPath .githooks` command themselves after cloning (often documented in a README or automated via an onboarding script); it does not self-install the way Husky's npm `prepare` hook does.

> ⚠️ **Common confusion to preempt:** none of these three approaches make Git itself "version hooks." They all work around the same underlying fact from 24.3 — `.git/` is never committed — either by installing a dispatcher into `.git/hooks/` that reads versioned config (`pre-commit` framework), by redirecting `core.hooksPath` to a committed directory (Husky, manual), or by requiring an explicit one-time setup step contributors must remember to run.

## 24.6 Server-Side Hooks

These run on the machine hosting the bare repository that receives pushes — meaningful primarily for self-hosted Git servers (§23); major SaaS platforms (GitHub, GitLab, Bitbucket) don't expose raw server-side hooks to repository owners, offering equivalent functionality instead through branch protection rules, required status checks, and webhooks/CI integrations.

| Hook           | Fires                                                                    | Typical use                                                                                                      |
| -------------- | ------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------- |
| `pre-receive`  | Once, before any refs are updated, receiving **all** pushed refs at once | Global policy checks: reject force-pushes to protected branches, reject oversized files, reject unsigned commits |
| `update`       | Once per ref being updated, after `pre-receive` accepts overall          | Per-branch policy — e.g., different rules for `release/*` vs feature branches                                    |
| `post-receive` | After refs are updated, once the push is fully accepted                  | Triggering CI, deployment, notifications, mirroring to another remote                                            |

```
Push arrives at server
        │
        ▼
  pre-receive  ──reject──► push refused, nothing updated, client sees error
        │ accept
        ▼
  update (per ref)  ──reject one ref──► that ref refused, others may still proceed
        │ accept
        ▼
   refs actually updated
        │
        ▼
  post-receive  ──► side effects (CI trigger, deploy, notify) — cannot reject anymore
```

> 💡 **Tip:** The three-stage server pipeline mirrors the client-side `pre-commit` → `commit-msg` → `post-commit` shape deliberately: "can still reject" hooks come first, "already happened, just react" hooks come last. Recognizing that pattern makes any new hook's semantics predictable from its name alone.

## 24.7 Practical Example — `commit-msg` Enforcing Conventional Commits

Building on the Conventional Commits format from §18 (`type(scope): description`), a `commit-msg` hook can reject any commit whose message doesn't match.

```bash
# .githooks/commit-msg  (installed via core.hooksPath, 24.5.3)
#!/usr/bin/env bash
commit_msg_file="$1"
pattern='^(feat|fix|docs|style|refactor|test|chore)(\([a-z0-9-]+\))?: .{1,72}$'

if ! grep -qE "$pattern" "$commit_msg_file"; then
  echo "ERROR: commit message does not follow Conventional Commits format."
  echo "Expected: type(scope): description   e.g. feat(auth): add SSO login"
  exit 1
fi
```

```bash
$ git commit -m "fixed the bug"
ERROR: commit message does not follow Conventional Commits format.
Expected: type(scope): description   e.g. feat(auth): add SSO login

$ git commit -m "fix(auth): correct token refresh race condition"
[main 7c2a9f1] fix(auth): correct token refresh race condition
```

**Expected outcome:** malformed messages never reach history at all, which matters because Conventional Commits' whole value (§18) — automated changelog generation, semantic-version bumping — depends on every commit reliably following the format; a hook is the only local enforcement point.

## 24.8 Practical Example — `pre-push` Running the Test Suite

```bash
# .githooks/pre-push
#!/usr/bin/env bash
echo "Running test suite before push..."
npm test
```

```bash
$ git push origin feature-payments
Running test suite before push...

  ✗ CartTotal calculates discount correctly
    Expected 90, received 100

error: failed to push some refs — pre-push hook declined
```

**Purpose and trade-off:** catches regressions before they reach a shared branch, but a slow full suite makes every push slower — teams commonly run only a fast subset locally (`pre-push`) and reserve the full suite for CI (§25), rather than duplicating the entire pipeline on every developer's machine.

## 24.9 Bypassing Hooks

```bash
# Purpose: skip client-side hooks for one operation (use sparingly and deliberately)
$ git commit --no-verify -m "emergency: revert broken deploy"
$ git push --no-verify
```

> ⚠️ **Critical clarification:** `--no-verify` only bypasses **client-side** hooks on your machine — it has no effect on server-side `pre-receive`/`update` hooks or on CI status checks (§25) or branch protection rules (§23), which run independently of anything the client requested. A developer who locally skips a check cannot force a server that enforces the same policy to also skip it.

## 24.10 Interview Questions

**[Beginner] Q1. What is a Git hook, and where does it live?**
**Model answer:** A Git hook is an executable script Git automatically runs at a specific point in its workflow — for example, right before finalizing a commit, or right before pushing. Hooks live in `.git/hooks/`, one file per event, named exactly after that event (`pre-commit`, `commit-msg`, `pre-push`, and others). A repository ships with inert `.sample` versions of each; a hook only becomes active once you create an executable file with the exact matching name and no `.sample` suffix.

**[Intermediate] Q2. Why can't a team just commit a `pre-commit` script into `.git/hooks/` and rely on everyone having it?**
**Model answer:** Because `.git/` is the repository's local, private metadata directory — it is never tracked or committed, by Git's own design (the same reason config and the reflog are per-clone, not shared history). A script placed directly in `.git/hooks/` exists only on the machine that created it; cloning the repository gives you none of it. This is exactly the gap tools like the `pre-commit` framework, Husky, and `core.hooksPath` exist to close — each gets a versioned, committed source of truth actually wired into the local `.git/hooks/` dispatch point, through slightly different mechanisms.

**[Intermediate] Q3. What's the practical difference between how the `pre-commit` framework and Husky solve the versioning problem?**
**Model answer:** The `pre-commit` framework (Python-distributed, language-agnostic) keeps its configuration in a committed `.pre-commit-config.yaml`; running `pre-commit install` once writes a small dispatcher into `.git/hooks/pre-commit` that reads that config at commit time. Husky, built for the Node ecosystem, instead points Git's `core.hooksPath` at a committed `.husky/` directory containing the actual hook scripts, and wires its own installation into npm's `prepare` lifecycle script so that anyone who runs `npm install` gets working hooks with no separate manual step. Both ultimately rely on committed, versioned files reaching `.git/hooks/` or an equivalent redirected path — they differ in ecosystem, installation trigger, and whether a manual one-time command is still required.

**[Senior] Q4. A developer complains their commit was rejected locally by a `commit-msg` hook, so they ran `git commit --no-verify` to get around it — then their push was also rejected by the server. Explain what happened.**
**Model answer:** `--no-verify` only disables client-side hooks on the developer's own machine — it skipped their local `commit-msg` check, letting a malformed commit get recorded locally. But if the team's Git server (self-hosted, §23) or CI/branch-protection layer (§25) independently enforces the same policy — via a server-side `update` hook, a required CI status check, or a branch protection rule — that enforcement runs on the server regardless of anything requested client-side, because the server has no way to know or honor a client's `--no-verify` flag. The lesson: client-side hooks are a convenience and an early warning, not a security or policy boundary; genuine enforcement that must hold for every contributor belongs server-side, exactly as `pre-receive`/`update` hooks or platform-level protections are designed to provide.

**[Architect] Q5. Design a hook strategy for a 200-engineer monorepo where local hook execution time is becoming a productivity complaint.**
**Model answer:** I'd separate hooks by cost and by what they can actually catch locally versus what only makes sense centrally. Fast, deterministic, file-scoped checks (formatting, basic linting on changed files only — using something like `lint-staged` to scope work to the diff rather than the whole repository) stay in `pre-commit`, since they run in well under a second and catch mistakes before they're even recorded. Anything requiring a broader build or the full test suite moves to `pre-push` at most, and ideally is trimmed to a fast, targeted subset (affected-package testing in a monorepo, not the entire suite) — with the authoritative full suite living in CI (§25), not duplicated locally. I'd standardize hook installation through `core.hooksPath` pointing at a committed directory (or Husky, if the stack is Node-heavy) wired into onboarding tooling, so no engineer has hooks silently missing. Finally, I'd make sure genuinely non-negotiable policy — commit signing (§28), branch protection, required status checks — is enforced server-side or at the platform level, never solely relied upon as a local hook, since local hooks are always bypassable with `--no-verify` and must never be the only line of defense for anything security- or compliance-relevant.

## 24.11 Common Misconceptions

1. **"Hooks are automatically shared when you clone a repository."** They are not — `.git/hooks/` is local, unversioned content; sharing requires the `pre-commit` framework, Husky, or `core.hooksPath` pointed at a committed directory.
2. **"`--no-verify` bypasses all checks, including CI."** It only bypasses client-side hooks on the local machine; server-side hooks, branch protection rules, and CI status checks (§23, §25) are entirely unaffected.
3. **"Server-side hooks work the same way on GitHub/GitLab as on a self-hosted server."** SaaS platforms generally don't expose raw `pre-receive`/`update`/`post-receive` hooks to repository owners; they provide equivalent policy enforcement through branch protection rules, required status checks, and webhooks instead (§23).
4. **"A pre-commit hook and the `pre-commit` framework's `pre-commit` config key are the same thing."** They share a name by design, but one is a specific Git hook event; the other is a third-party tool's own naming convention for the checks it happens to run at that event — mind the overlap when reading documentation.

## 24.12 🔑 Key Takeaways

- Hooks are executable scripts in `.git/hooks/`, named after specific Git lifecycle events, invoked automatically, and able to abort the operation via non-zero exit code (for most hook types).
- `.git/hooks/` is never committed, which is the root cause of the "team-wide hook" problem — the `pre-commit` framework, Husky, and manual `core.hooksPath` are the three standard solutions, differing in ecosystem and installation mechanics but converging on the same fix: get versioned, committed scripts actually wired into Git's local hook dispatch.
- Client-side hooks (`pre-commit`, `commit-msg`, `pre-push`) run on the developer's machine and are always bypassable with `--no-verify`; they are a convenience, not an enforcement guarantee.
- Server-side hooks (`pre-receive`, `update`, `post-receive`) run on self-hosted Git servers and are the actual enforcement point that cannot be bypassed client-side; SaaS platforms offer equivalent policy through branch protection and status checks instead.
- Real-world use: linting/formatting at `pre-commit`, Conventional Commits validation (§18) at `commit-msg`, test execution at `pre-push`.

## 24.13 Related Concepts & What's Next

Hooks are Git's local automation entry point; §25 zooms out to how CI/CD systems build on top of Git events (push, PR open, tag creation) at a fleet scale hooks alone can't reach — the two are complementary layers, with hooks catching problems in seconds before code leaves a machine, and CI providing the authoritative, unbypassable check once it arrives at the shared remote.
