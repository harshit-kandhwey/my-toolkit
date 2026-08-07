# Section 28 (Part 7): Security — Commit/Tag Signing (GPG/SSH), Credential Management, Leaked Secrets & History Remediation

## 1. Definition

**Plain language:** Git security in practice covers three distinct concerns: proving _who really authored_ a commit or tag (signing), keeping the credentials that authenticate you to remotes out of the wrong hands (credential management), and cleaning up after a secret — an API key, password, or private certificate — accidentally gets committed into history (leaked-secret remediation).

**Precise:** Git supports cryptographic signing of commit and tag objects using either GPG (OpenPGP) or an SSH key pair, producing a detached signature stored inside the object itself that hosting platforms can verify against a known public key. Separately, credential helpers ([§8](../Part3/Section-08-Part3-Installation-Configuration.md)) manage the secrets Git itself needs to authenticate outbound. Neither mechanism prevents a secret from being committed into tracked file content — that is a distinct failure mode requiring detection tooling and, if it occurs, a history-rewriting remediation workflow plus credential rotation at the source.

## 2. Why It Exists / Problem It Solves

1. **Authorship spoofing is trivial by default.** `git config user.name` / `user.email` are plain, unauthenticated local settings — anyone can `git config user.email "torvalds@linux-foundation.org"` and commit under that identity. Nothing in an unsigned commit cryptographically proves the stated author actually made it. Signing closes this gap.
2. **Supply-chain trust.** A tagged release ([§18](../Part4/Section-18-Part4-Tags-Versioning-Release-Management.md)) that consumers pin to by name is a high-value target for tampering; a signed tag lets anyone verify the release was produced by a specific, trusted key, not merely that it exists.
3. **Regulated environments need provable authorship**, not just plausible authorship — the same compliance driver named in [§1](../Part1/Section-01-Part1-Version-Control-Fundamentals.md)'s audit-trail point.
4. **Credentials must reach remotes without living in plaintext** in shell history, scripts, or Git config files — credential helpers exist precisely to avoid that.
5. **A secret committed once is effectively permanent** unless deliberately and correctly removed, because Git's object model ([§5](../Part2/Section-05-Part2-Object-Model.md)) is built on immutable, content-addressed, historically-retained snapshots — the same property that makes Git trustworthy for auditing makes an accidental secret commit uniquely dangerous compared to, say, a secret dropped in a shared folder that could simply be deleted.

## 3. Commit & Tag Signing — GPG

### 3.1 Setup

```bash
# Purpose: generate a GPG key pair if you don't already have one (interactive prompts follow)
$ gpg --full-generate-key

# Purpose: list your keys and find the key ID to use
$ gpg --list-secret-keys --keyid-format=long

# Purpose: tell Git which key to sign with
$ git config --global user.signingkey 3AA5C34371567BD2

# Purpose: export the public key to paste into GitHub/GitLab's "GPG keys" settings
$ gpg --armor --export 3AA5C34371567BD2
```

### 3.2 Signing commits and tags

```bash
# Purpose: sign one commit explicitly
$ git commit -S -m "Fix pagination bug"

# Purpose: make EVERY commit signed automatically, repo-wide or globally
$ git config --global commit.gpgsign true

# Purpose: create a signed (as opposed to merely annotated, §18) tag
$ git tag -s v2.3.1 -m "Release 2.3.1"

# Purpose: verify a signature manually
$ git verify-commit HEAD
$ git verify-tag v2.3.1
```

Expected output on a verified commit inspected with `git log --show-signature`:

```
gpg: Signature made Wed 22 Jul 2026 10:14:02 UTC
gpg: Good signature from "Jane Doe <jane@example.com>" [ultimate]
commit a3f8e21bc9d4f5e6789012345678901234567890
Author: Jane Doe <jane@example.com>
```

> ⚠️ **Critical clarification:** `commit.gpgsign true` makes signing the default, but Git will hard-fail the commit if `user.signingkey` is missing, unset correctly, or the key requires a passphrase you can't supply non-interactively (a common CI surprise) — plan for this explicitly in automation, not just on developer laptops.

## 4. SSH-Based Signing (`gpg.format ssh`)

GPG's setup friction (key generation ceremony, a separate trust model, `gpg-agent` passphrase caching) is disproportionate for developers who already have an SSH key pair for remote authentication ([§8](../Part3/Section-08-Part3-Installation-Configuration.md)). Git 2.34+ lets you reuse that same SSH key for signing instead.

```bash
# Purpose: switch Git's signing format from OpenPGP (default) to SSH
$ git config --global gpg.format ssh

# Purpose: point at the SSH public key to sign with (reuses your existing key from §8)
$ git config --global user.signingkey ~/.ssh/id_ed25519.pub

# Purpose: sign exactly as before — the -S flag and commit.gpgsign are format-agnostic
$ git commit -S -m "Fix pagination bug"
```

Verification with SSH signatures requires an **allowed signers file** — a local mapping of email addresses to trusted public keys, since SSH has no built-in web-of-trust equivalent to GPG's:

```bash
# Purpose: create the allowed-signers file Git checks SSH signatures against
$ echo "jane@example.com $(cat ~/.ssh/id_ed25519.pub)" >> ~/.ssh/allowed_signers
$ git config --global gpg.ssh.allowedSignersFile ~/.ssh/allowed_signers
```

> 💡 **Tip:** SSH signing's practical advantage is reuse — one key pair, already generated for authenticating to remotes as covered in [§8](../Part3/Section-08-Part3-Installation-Configuration.md), now also proves authorship, with no separate GPG toolchain, passphrase agent, or key-server infrastructure to maintain. Hosting platforms (GitHub, GitLab) accept SSH-signed commits and show the same "Verified" badge as GPG-signed ones.

## 5. GPG vs SSH Signing — Comparison

| Dimension                 | GPG signing                                       | SSH signing                                                                                      |
| ------------------------- | ------------------------------------------------- | ------------------------------------------------------------------------------------------------ |
| Key reuse                 | Separate key pair, separate purpose               | Reuses your existing SSH auth key (or a dedicated signing-only one)                              |
| Trust model               | Web of trust / key servers                        | Explicit allowed-signers file (simpler, more manual)                                             |
| Tooling                   | Requires GnuPG installed and `gpg-agent`          | Uses `ssh-keygen`/`ssh-agent`, already present on most dev machines                              |
| Platform support          | Universally supported, oldest and most mature     | Supported by GitHub/GitLab since ~2022; verify current support on any older/self-hosted platform |
| Passphrase handling in CI | Historically fiddly (agent forwarding, `--batch`) | Similarly requires care; neither is CI-trivial without deliberate setup                          |

## 6. What "Verified" Badges Actually Prove (and Don't)

> ⚠️ **Common confusion to preempt:** a "Verified" badge on GitHub/GitLab proves the commit was signed by a private key corresponding to a public key **the platform account has registered** — it proves cryptographic authorship identity. It proves **nothing about code correctness, safety, or intent**. A malicious or buggy commit can be perfectly, validly signed by its author. Signing answers "who wrote this," never "is this good/safe code" — that's what code review, CI, and branch protection ([§23](../Part5/Section-23-Part5-Git-Hosting-Enterprise-Platforms.md)) are for.

Additionally:

- A verified badge says the signature matches a key on file **at verification time** — if a key is later revoked or the account is compromised and a new key added, platforms differ in how they handle historical badges; don't treat it as an immutable, permanently re-checked property.
- Unsigned commits from a real, trusted contributor are not evidence of anything malicious — most teams and open-source projects run for years on entirely unsigned history. Signing is a hardening measure adopted deliberately, not a default expectation across the ecosystem.
- Signing proves authorship of the **commit object**, not that the diff it introduces was reviewed by anyone else — a single signed commit by a compromised developer account is still a real risk; this is why signing complements, and never replaces, branch protection and required reviews ([§23](../Part5/Section-23-Part5-Git-Hosting-Enterprise-Platforms.md)).

## 7. Credential Management — Recap and Deepening

[§8](../Part3/Section-08-Part3-Installation-Configuration.md) introduced credential helpers; the security framing here is why each choice matters:

| Helper                                             | Storage                                                                                     | Security posture                                                                                                                                      |
| -------------------------------------------------- | ------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `manager` (Git Credential Manager, cross-platform) | OS-native secure storage (Windows Credential Manager, macOS Keychain, Linux Secret Service) | Recommended default — encrypted at rest, OS-integrated                                                                                                |
| `cache`                                            | In-memory, time-limited (default 15 minutes)                                                | Never touches disk; good for shared/ephemeral machines, requires re-auth often                                                                        |
| `store`                                            | **Plaintext file** (`~/.git-credentials`)                                                   | Convenient but a real risk — anyone with filesystem read access to that file has your credentials in the clear; avoid on shared or untrusted machines |

```bash
# Purpose: confirm which helper is active before assuming credentials are stored securely
$ git config --get credential.helper
```

**Personal Access Tokens (PATs)** are the modern standard over passwords for HTTPS remotes — platforms have largely deprecated password authentication for Git operations entirely. Treat a PAT exactly like a password: scope it to the minimum required permissions, set an expiry, and never paste it directly into a remote URL (`https://<token>@github.com/...`) where it can leak into shell history or `.git/config` in plaintext — let the credential helper prompt-and-store it instead.

> 💡 **Tip:** SSH key-based authentication ([§8](../Part3/Section-08-Part3-Installation-Configuration.md)) sidesteps the credential-helper question entirely for the auth side of things — the private key never leaves your machine and is never transmitted, unlike a PAT which is a bearer secret sent over the wire on every HTTPS operation.

## 8. Leaked Secrets — Why "Deleting" Doesn't Work

This is the single most consequential misconception in Git security, and it follows directly from [§5](../Part2/Section-05-Part2-Object-Model.md) and [§7](../Part2/Section-07-Part2-Inside-Git-Loose-Objects-Packfiles-GC.md)'s object model:

```
Commit 1: config.yml contains  api_key: "sk_live_abc123..."
Commit 2: config.yml — the secret is removed, replaced with a placeholder

$ git log --oneline
9f2c1a4 Remove hardcoded API key   ← looks fixed
7e4f9a2 Add initial config          ← secret is STILL HERE, forever

$ git show 7e4f9a2:config.yml
api_key: "sk_live_abc123..."        ← trivially retrievable by anyone who clones
```

A new commit that removes a secret only changes what the **latest** tree snapshot contains. Commit 1's tree object, and the blob holding the secret, remain **fully intact and reachable** objects in `.git/objects` — reachable specifically because commit 2's parent pointer still references commit 1 ([§5](../Part2/Section-05-Part2-Object-Model.md)'s ancestry chain), and every clone that fetches the branch receives the entire chain, not just the tip. Anyone can run `git log -p` or `git show <old-hash>` and read the secret out of history exactly as it always was.

> ⚠️ **Critical clarification:** this is true even if the removal commit is the very next commit after the leak, even if nobody has "noticed" yet, and even in a private repository — the secret is not gone, it is one `git show` away from any past or future clone of the full history.

## 9. Detecting Leaked Secrets

- **Pre-commit prevention (the cheapest fix):** secret-scanning hooks ([§24](../Part6/Section-24-Part6-Git-Hooks-Automation.md)) that block a commit before it's ever created — tools like `gitleaks` or `detect-secrets` run as a `pre-commit` hook, checking staged content against regex/entropy patterns for API keys, private keys, and known credential formats.
- **Platform-native scanning:** GitHub Secret Scanning (and equivalents on GitLab/Bitbucket) continuously scans pushed history for recognizable secret patterns (cloud provider keys, common API token formats) and can alert automatically, in some cases even notifying the credential's issuing provider directly to auto-revoke it.
- **Periodic full-history scans:** running `gitleaks detect` or similar against the **entire history**, not just the working tree, since a secret from years ago that predates any scanning tooling's adoption is still sitting in old commits.

> 💡 **Tip:** prevention (pre-commit hooks) is dramatically cheaper than remediation (history rewriting, force-push coordination, credential rotation) — this is the standard "shift-left" security argument applied directly to Git.

## 10. Remediation Tooling — `filter-repo` vs `filter-branch` vs BFG

Once a secret is confirmed in history, it must be removed from **every commit that ever contained it**, not just the latest one — this requires rewriting history, which changes the hash of every affected commit and everything descended from it ([§5](../Part2/Section-05-Part2-Object-Model.md)'s content-addressing: change any input, the hash changes).

| Tool                    | Status                                                                                                                      | Notes                                                                                                                                                                                                                                                    |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **`git filter-repo`**   | **Modern, recommended** (an external, actively maintained Python tool; not a built-in `git` subcommand, install separately) | Fast, purpose-built for exactly this class of operation (strip files, rewrite content, remove paths across all history); the official Git project itself now recommends it over `filter-branch`                                                          |
| **`git filter-branch`** | **Legacy, built-in, explicitly discouraged**                                                                                | Ships with core Git but is notoriously slow on large histories, easy to misuse in ways that silently corrupt history, and carries an official deprecation warning in its own `--help` output pointing at `filter-repo`                                   |
| **BFG Repo-Cleaner**    | Third-party (Java-based), still widely used                                                                                 | Simpler, narrower interface specifically optimized for two common cases — stripping matched text/secrets and deleting large blobs by size — often faster to reach for when the need is exactly one of those two things and not a general history rewrite |

```bash
# Purpose (filter-repo): remove a specific file from ALL of history, not just the current tree
$ git filter-repo --path config.yml --invert-paths

# Purpose (filter-repo): replace a literal secret string wherever it appears across all history
$ echo "sk_live_abc123==>REDACTED" > replacements.txt
$ git filter-repo --replace-text replacements.txt

# Purpose (BFG): equivalent secret-scrubbing, BFG's syntax
$ bfg --replace-text passwords.txt repo.git
```

> ⚠️ **Critical clarification:** `git filter-repo` operates on a **fresh clone by design** and refuses to run on a repo that still has a remote configured, specifically to prevent someone from accidentally rewriting history and then immediately, un-thoughtfully pushing over shared work. This is a deliberate safety rail, not a bug — treat needing to work around it as a signal to slow down.

## 11. The Remediation Workflow End-to-End

1. **Rotate the credential first, or immediately in parallel — never last.** The secret must be treated as compromised the moment it's confirmed in a pushed commit, regardless of how quickly it's "cleaned up." Automated scrapers continuously harvest public (and sometimes even private-but-breached) repositories for exactly these patterns; by the time remediation finishes, the original secret may already have been copied outside Git entirely, where no amount of history rewriting can touch it. Rewriting history without rotation is remediation theater.
2. **Rewrite history locally** with `filter-repo`, `BFG`, or (last resort) `filter-branch`, per the tooling comparison above.
3. **Expire the reflog and gc locally** (`git reflog expire --expire=now --all && git gc --prune=now`, per [§7](../Part2/Section-07-Part2-Inside-Git-Loose-Objects-Packfiles-GC.md)) — the rewrite alone doesn't remove the old objects from _your own_ local repository either.
4. **Force-push the rewritten history**, coordinating explicitly with every collaborator — this directly invokes [§14](../Part4/Section-14-Part4-Rebasing.md)'s Golden Rule of Rebasing: rewriting and force-pushing shared history is exactly the destructive, disruptive operation that rule warns against, made unavoidable here by the security requirement. Every collaborator must be told to **discard their existing local clone and re-clone fresh** (or very carefully reset onto the new history) — a stale local clone still holds the old commits and can silently reintroduce the leaked secret on a future push or merge.
5. **Clean up everywhere else the old history reached:** forks, CI build caches, artifact repositories, and any other clone are entirely separate copies unaffected by the rewrite (generalizing the same point made in [§7](../Part2/Section-07-Part2-Inside-Git-Loose-Objects-Packfiles-GC.md)) — each needs its own remediation or, more practically, must simply be deleted and recreated from the cleaned repository.

```
Old history:  A──B(secret)──C──D
                    │
                    └── still fully reachable, in every existing clone/fork

After filter-repo + force-push, NEW history (different hashes from B onward):
              A──B'(no secret)──C'──D'

Any collaborator who does not re-clone or hard-reset still has the OLD
A──B──C──D chain locally, secret and all — and can reintroduce it with
a careless merge/push.
```

## 12. Hands-On Example — Demonstrating the Problem and the Fix

```bash
$ mkdir secretdemo && cd secretdemo && git init -q
$ echo 'api_key: "sk_live_abc123"' > config.yml
$ git add config.yml && git commit -qm "Add initial config"
$ echo 'api_key: "REDACTED"' > config.yml
$ git add config.yml && git commit -qm "Remove hardcoded API key"

# The secret is STILL fully retrievable from the earlier commit:
$ git log --oneline
9f2c1a4 Remove hardcoded API key
7e4f9a2 Add initial config
$ git show 7e4f9a2:config.yml
api_key: "sk_live_abc123"

# Remediate with filter-repo (run against a fresh clone in real usage)
$ git filter-repo --replace-text <(echo 'sk_live_abc123==>REDACTED') --force
$ git show 7e4f9a2:config.yml 2>&1 || echo "old hash no longer resolves — history was rewritten"
```

Expected outcome: the original commit hash `7e4f9a2` no longer exists at all — `filter-repo` produced a new commit with equivalent metadata but redacted content and a **different hash**, exactly as content-addressing ([§5](../Part2/Section-05-Part2-Object-Model.md)) predicts for any changed input.

## 13. Production & Enterprise Usage

- **CI/CD pipelines and infrastructure-as-code repos are disproportionately at risk** — cloud credentials, database connection strings, and TLS private keys are the recurring offenders, precisely because they're needed by automation and get pasted into config "just to get it working" far more often than application source code leaks secrets.
- **Signing is increasingly mandated, not optional, on regulated or high-trust projects** — some organizations enforce `commit.gpgsign true` and reject unsigned commits via server-side hooks or branch protection rules ([§23](../Part5/Section-23-Part5-Git-Hosting-Enterprise-Platforms.md)), particularly for release/tag creation.
- **Incident response runbooks** for a confirmed leak typically codify the end-to-end remediation sequence above as a checklist precisely because skipping rotation, or skipping collaborator re-clone coordination, are the two most common real-world remediation failures.

## 14. Interview Questions

**[Beginner] Q1. If I commit a secret and then delete it in the very next commit, is it safe?**
**Model answer:** No. Git stores full snapshots per commit, and the earlier commit — the one that still contains the secret — remains a fully intact, reachable object in the repository's history because the later commit's parent pointer references it. Anyone who clones the repository, or already has, can run `git show <old-hash>:<file>` and retrieve the secret exactly as it was, regardless of what the latest commit looks like. The only real fixes are rewriting history to strip the secret from every commit that ever held it, and rotating the credential at its source.

**[Intermediate] Q2. What does a "Verified" badge on a signed commit actually guarantee, and what doesn't it guarantee?**
**Model answer:** It guarantees the commit was signed with a private key whose corresponding public key is registered to that platform account — i.e., cryptographic proof of who authored the commit, assuming the key itself hasn't been compromised. It guarantees nothing about the quality, safety, or intent of the code in the commit; a malicious or buggy change can be perfectly validly signed by its legitimate author. Signing answers an identity question, not a correctness question — code review, CI checks, and branch protection remain necessary regardless of signing status.

**[Intermediate] Q3. Compare `git filter-repo` and `git filter-branch` for removing a secret from history.**
**Model answer:** Both rewrite history to strip content across every affected commit, but `filter-branch` is the legacy, built-in tool — it ships with Git but is slow on large repositories, has a well-documented history of subtle correctness pitfalls, and its own help text now recommends against using it. `filter-repo` is a separately installed, actively maintained, purpose-built tool that the Git project itself recommends as the modern default: it's substantially faster, has safer defaults (like refusing to run against a repo with a remote still configured, to prevent an accidental premature push), and has a more ergonomic interface for common operations like removing a path or replacing matched text across all of history.

**[Senior] Q4. A leaked AWS key is found in a commit from eight months ago, in a repository with twelve active contributors. Walk through your response.**
**Model answer:** First and immediately, in parallel with everything else: rotate the AWS key at the source — treat it as compromised the moment it's confirmed, since automated scrapers may have already harvested it regardless of how quickly the repository gets cleaned, and rewriting Git history does nothing to un-leak a credential that's already been copied elsewhere. Second, rewrite history with `git filter-repo` on a fresh clone to strip the secret from every commit that contains it, then locally expire the reflog and run `git gc --prune=now` to actually remove the old objects from that clone. Third, force-push the rewritten history to the remote — this is a real invocation of the Golden Rule's warning against rewriting shared history, made necessary here by the security requirement, so I'd communicate explicitly and synchronously with all twelve contributors before doing it. Fourth, every contributor must discard their existing local clone and re-clone fresh, or very carefully hard-reset their local branches onto the new history — a stale clone still has the old commits and can silently reintroduce the secret on a future push. Fifth, I'd check for forks, CI caches, and any artifact stores that might have fetched the old history and address each separately, since none of them are affected by the rewrite done to the primary repository.

**[Architect] Q5. Should an organization mandate commit signing across all repositories? Argue both sides.**
**Model answer:** In favor: signing provides genuine, verifiable proof of authorship, which matters for supply-chain integrity (especially on tagged releases that downstream systems pin to), strengthens audit trails for regulated environments, and raises the cost of impersonation attacks where an attacker with write access tries to attribute malicious commits to a trusted teammate. Against: it adds real friction — key management overhead, CI/automation complexity (service accounts and bots need their own keys and non-interactive signing setups), and a hard failure mode when a developer's signing key expires or their agent isn't running, which can block legitimate work if enforced too strictly. My actual recommendation would be tiered: mandate signing on protected branches and, at minimum, on release tags — the places where authorship actually matters for trust decisions downstream — while leaving feature-branch and day-to-day commits unsigned or optionally signed, avoiding blanket friction where the security benefit is marginal. I'd also insist signing is explicitly framed to the team as an authorship control, not a code-quality control, so it doesn't get treated as a substitute for code review.

## 15. Common Misconceptions

1. **"Deleting the file in a new commit removes the secret."** False — the secret remains in the tree/blob objects of every earlier commit that had it, fully reachable via the commit ancestry chain, until history is deliberately rewritten.
2. **"A private repository means a leaked secret is safe."** Private only restricts _who currently has read access_ through the platform; it doesn't retroactively protect against collaborators, CI systems, or anyone who already cloned it, and it provides zero protection once access is later widened, misconfigured, or compromised.
3. **"Rewriting history is sufficient remediation on its own."** It only fixes the repository; the credential itself must also be rotated/invalidated at the source, since it may already have been scraped, and every collaborator's stale clone must be addressed or the secret can be silently reintroduced.
4. **"A signed commit means the code is safe/trustworthy to merge."** Signing proves identity, not correctness or intent — it never substitutes for code review or CI.
5. **"GPG is the only way to sign commits."** SSH-based signing (`gpg.format ssh`, Git 2.34+) is a fully supported, platform-recognized alternative that reuses an existing SSH key pair.

## 16. 🔑 Key Takeaways

- Signing (GPG or SSH, via `gpg.format`) cryptographically proves commit/tag **authorship identity** — never code correctness — and platforms surface it as a "Verified" badge.
- Credential helpers ([§8](../Part3/Section-08-Part3-Installation-Configuration.md)) should default to OS-native secure storage; plaintext `store` and pasting tokens into remote URLs are avoidable risks.
- A secret committed once persists in every reachable historical commit forever, regardless of later "removal" commits — this follows directly from Git's immutable, content-addressed snapshot model ([§5](../Part2/Section-05-Part2-Object-Model.md), [§7](../Part2/Section-07-Part2-Inside-Git-Loose-Objects-Packfiles-GC.md)).
- Remediation requires all of: history rewriting with `git filter-repo` (modern) over `filter-branch` (legacy) or BFG, local reflog expiry plus `gc --prune=now`, a coordinated force-push under the Golden Rule ([§14](../Part4/Section-14-Part4-Rebasing.md)), mandatory re-clone by every collaborator, and — non-negotiably, and first — rotating the credential at its source.
- Prevention (pre-commit secret-scanning hooks, [§24](../Part6/Section-24-Part6-Git-Hooks-Automation.md)) is far cheaper than remediation.

## 17. Related Concepts & What's Next

Security here has focused on trust and secrets; [§29](./Section-29-Part7-Maintenance-Performance-Troubleshooting.md) turns to the operational health of a repository — keeping it fast and correctly functioning over time through routine maintenance (`git gc`, `git fsck`), diagnosing why a repository has become slow or bloated, and fixing the common day-to-day failures every Git user eventually hits, from stray detached HEAD confusion to SSH authentication errors.
