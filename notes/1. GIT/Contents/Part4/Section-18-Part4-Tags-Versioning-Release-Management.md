# Section 18 (Part 4): Tags, Versioning & Release Management

## 1. Definition

**Plain language:** A tag is a permanent, human-readable label on one exact commit — used to mark releases so "version 2.3.1" always means one specific, unchanging point in history. This section is about using tags as part of a real release-management discipline, not just their ref mechanics.

**Precise:** Practically, release management with Git combines three layers: tags (the pointer mechanism, already covered structurally in §5 and §6), a versioning **scheme** giving tag names consistent meaning (Semantic Versioning), and a commit-message **convention** that lets tooling derive version bumps and changelogs automatically (Conventional Commits). None of these three layers is Git-enforced — all are team/tooling conventions layered on top of plain refs.

## 2. Recap — Tag Ref Mechanics (Full Depth: §5, §6)

Two tag kinds exist at the ref level: a **lightweight tag** (a plain file under `.git/refs/tags/`, structurally identical to a branch pointer, just conventionally not moved) and an **annotated tag** (a real, distinct tag object in the object database carrying tagger identity, timestamp, message, and optionally a signature). §5 already established the rule this section assumes: **use annotated tags for anything that will be shared, released, or audited.**

## 3. Creating Tags

```bash
# Lightweight — quick, throwaway, no metadata
$ git tag v1.2.3-scratch

# Annotated — the production/enterprise default for real releases
$ git tag -a v1.2.3 -m "Release 1.2.3: fix pagination, add search"
```

```bash
# Purpose: tag a PAST commit, not just HEAD
$ git tag -a v1.2.2 -m "Retroactive tag for 1.2.2" a1b2c3d
```

Expected inspection:

```bash
$ git show v1.2.3
tag v1.2.3
Tagger: Harshit Kandhwey <harshitkandhwey@gmail.com>
Date:   Tue Jul 21 10:00:00 2026 +0530

Release 1.2.3: fix pagination, add search

commit 9f2c1a4...
...
```

## 4. Listing and Filtering Tags

```bash
# Purpose: list all tags, alphabetically
$ git tag

# Purpose: filter by a glob pattern
$ git tag -l "v1.2.*"

# Purpose: list tags with their annotation message inline
$ git tag -n

# Purpose: list tags in creation/commit order rather than alphabetical
$ git tag --sort=-creatordate
```

> ⚠️ **Common confusion to preempt:** plain alphabetical `git tag` listing sorts `v1.10.0` **before** `v1.2.0` (string comparison, not numeric), which looks wrong at a glance — `--sort=-v:refname` sorts using Git's version-aware comparator instead, correctly ordering `v1.2.0` before `v1.10.0`.

## 5. Pushing Tags — The Common Gotcha

> ⚠️ **Critical clarification:** tags are **not pushed automatically** by a plain `git push` — this catches nearly everyone at least once. Creating and pushing tags are two separate steps, deliberately, so you can create local, exploratory tags without ever sharing them.

```bash
# Purpose: push ONE specific tag
$ git push origin v1.2.3

# Purpose: push ALL tags at once
$ git push origin --tags

# Purpose: push commits AND tags together in one command
$ git push --follow-tags     # only pushes ANNOTATED tags reachable from what's being pushed
```

| Command                  | What it pushes                                                                                               |
| ------------------------ | ------------------------------------------------------------------------------------------------------------ |
| `git push origin main`   | Commits on `main` only — **no tags**, even ones pointing at pushed commits                                   |
| `git push origin v1.2.3` | That one tag specifically                                                                                    |
| `git push origin --tags` | **Every** local tag, including throwaway lightweight ones — can be noisier than intended                     |
| `git push --follow-tags` | Commits plus any annotated tags reachable from them — the disciplined middle ground most teams actually want |

## 6. Deleting Tags — Local and Remote

```bash
# Purpose: delete a LOCAL tag
$ git tag -d v1.2.3-scratch

# Purpose: delete a tag on the REMOTE (does not touch your local copy)
$ git push origin --delete v1.2.3-scratch
# older, equivalent syntax:
$ git push origin :refs/tags/v1.2.3-scratch
```

As with branches (§20's remote mechanics), local and remote copies of a tag are entirely separate refs that happen to share a name — deleting one does not affect the other.

> ⚠️ **Critical clarification:** deleting and recreating a tag that's already been fetched by anyone else is exactly the supply-chain integrity risk §6 flagged — never move or reuse a released tag name. Cut a new version instead (e.g., `v1.2.4`) if a released tag turns out to be wrong.

## 7. Checking Out a Tag — Detached HEAD (Full Mechanics: §6)

```bash
$ git checkout v1.2.3
Note: switching to 'v1.2.3'.
You are in 'detached HEAD' state...
```

Checking out a tag always enters detached HEAD, since a tag is a fixed marker, not a movable branch pointer — exactly the mechanics §6 already covered. This is the standard way to inspect, build, or debug the exact state of a past release without disturbing any branch.

## 8. Semantic Versioning (SemVer)

The near-universal convention for what a version number itself _means_: `MAJOR.MINOR.PATCH`, e.g. `2.4.1`.

| Component | Increments when                                        | Example           |
| --------- | ------------------------------------------------------ | ----------------- |
| **MAJOR** | A breaking, backward-incompatible change is introduced | `1.x.x` → `2.0.0` |
| **MINOR** | New, backward-compatible functionality is added        | `2.4.x` → `2.5.0` |
| **PATCH** | A backward-compatible bug fix, no new functionality    | `2.4.1` → `2.4.2` |

```
v2.5.1-beta.3+build.789
 │ │ │  └───┬───┘ └───┬───┘
 │ │ │      │         └── build metadata (informational only, ignored in
 │ │ │      │              precedence comparisons — e.g., a CI build number)
 │ │ │      └── pre-release identifier (e.g., alpha, beta, rc.1) —
 │ │ │           sorts BEFORE the plain version it precedes
 │ │ └── PATCH
 │ └──── MINOR
 └────── MAJOR
```

- **Pre-release** (`-beta.3`, `-rc.1`, `-alpha`): marks a version as not yet stable; SemVer's comparison rules explicitly sort any pre-release version _before_ its corresponding plain release (`2.5.0-rc.1` < `2.5.0`).
- **Build metadata** (`+build.789`): purely informational — two versions differing only in build metadata are considered equal for precedence purposes, and most tooling ignores it entirely for comparison.

> 💡 **Tip:** SemVer is a **convention**, not something Git or any package manager can enforce mechanically — nothing stops a maintainer from making a breaking change in a patch release. It's valuable precisely because downstream consumers (and automated tooling, like dependency resolvers using version ranges such as `^2.4.0`) rely on the promise being honored; breaking it silently erodes trust in a package's versioning.

## 9. Conventional Commits

A structured commit-message format that gives commit history itself enough machine-readable semantic content to drive version bumps and changelogs automatically, rather than requiring a human to manually decide "was this a major, minor, or patch change" at release time.

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

| Type                                                                           | Meaning                      | Typical SemVer effect                         |
| ------------------------------------------------------------------------------ | ---------------------------- | --------------------------------------------- |
| `feat:`                                                                        | A new feature                | MINOR bump                                    |
| `fix:`                                                                         | A bug fix                    | PATCH bump                                    |
| `docs:`, `style:`, `refactor:`, `test:`, `chore:`                              | Non-functional changes       | No version bump (by convention)               |
| `BREAKING CHANGE:` (in the footer, or `!` after the type/scope, e.g. `feat!:`) | Backward-incompatible change | **MAJOR** bump, regardless of the prefix type |

```bash
# Examples
$ git commit -m "feat(auth): add OAuth login support"
$ git commit -m "fix(cart): correct off-by-one in quantity calculation"
$ git commit -m "feat(api)!: remove deprecated v1 endpoints

BREAKING CHANGE: /api/v1/* routes have been removed; use /api/v2/*"
```

### 9.1 How tooling consumes this

Tools like **semantic-release**, **standard-version**, and `release-please` parse the commit history since the last tag, scan every commit's `type:` prefix, compute the correct next SemVer version automatically (any `BREAKING CHANGE` forces a major bump regardless of other commits; otherwise the highest of `feat`→minor / `fix`→patch wins), generate a categorized changelog grouped by type, create the new annotated tag, and often push a hosting-platform Release (covered below) — all without a human manually deciding the version number. This is the concrete mechanism tying commit-message discipline directly into CI/CD automation (§25): a merge to `main` can trigger a fully automated release pipeline purely because the commit messages themselves carried enough structured information to drive it.

> 🔑 **Interview-grade summary:** SemVer defines what a version number _means_; Conventional Commits gives Git history enough structure for tooling to _compute_ that version number and changelog automatically, rather than a human deciding it by hand at release time.

## 10. Signed Tags — Preview (Full Mechanics: §28)

```bash
# Purpose: create a GPG- or SSH-signed annotated tag, cryptographically
# proving a specific key holder vouched for this exact commit as the release
$ git tag -s v1.2.3 -m "Release 1.2.3"

# Purpose: verify a signed tag's signature
$ git tag -v v1.2.3
```

A signed tag builds directly on the annotated tag object (§5) by adding a cryptographic signature over its content — meaning any tampering with the tagged commit, the tag message, or the tagger identity invalidates the signature. Full key management, GPG vs SSH signing, and verification policy in CI are §28's subject; noted here because it's a natural next step once you're using annotated tags for real releases and want tamper-evidence beyond Git's baseline hash-chaining (§2).

## 11. GitHub/GitLab Releases — A Platform Feature Built on Tags

A hosting platform's "Release" (GitHub Releases, GitLab Releases) is **not** a separate Git concept — it's a database record on the platform that wraps an existing tag with additional, platform-hosted content: release notes (often auto-generated from Conventional Commits or PR titles), downloadable binary attachments, and a "latest release" marker.

|                             | Git tag                                                       | Platform Release                                                               |
| --------------------------- | ------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Lives in                    | The Git object database, transferable via any clone/push      | The hosting platform's own database                                            |
| Portable across hosts       | Yes — tags travel with the repository                         | No — moving from GitHub to GitLab does not carry Releases automatically        |
| Can exist without the other | Yes, a tag needs no Release                                   | **No** — a Release always requires an underlying tag to point at               |
| Typical content             | Just a name and a commit pointer (plus metadata if annotated) | Human-readable release notes, binary artifacts, changelog links, "latest" flag |

> ⚠️ **Critical clarification:** deleting a GitHub Release does **not** delete the underlying Git tag, and vice versa — they're managed independently even though the platform's UI presents them together. Automated release tooling, as described above, typically creates both in one pipeline step, but they remain two separate systems underneath.

## 12. Hands-On — Full Release Workflow

```bash
$ mkdir releasedemo && cd releasedemo && git init -q
$ git commit --allow-empty -qm "feat: initial release"
$ git tag -a v1.0.0 -m "Release 1.0.0"

$ git commit --allow-empty -qm "fix: correct rounding in totals"
$ git commit --allow-empty -qm "feat: add CSV export"
$ git tag -a v1.1.0 -m "Release 1.1.0: CSV export, rounding fix"

$ git commit --allow-empty -qm "feat!: remove legacy XML export

BREAKING CHANGE: XML export endpoint removed; use CSV export instead"
$ git tag -a v2.0.0 -m "Release 2.0.0: breaking removal of XML export"

$ git tag -n --sort=v:refname
v1.0.0          Release 1.0.0
v1.1.0          Release 1.1.0: CSV export, rounding fix
v2.0.0          Release 2.0.0: breaking removal of XML export

$ git push origin --follow-tags
```

The version sequence here — `1.0.0` → `1.1.0` (a `feat:` commit, no breaking change) → `2.0.0` (a `feat!:`/`BREAKING CHANGE:` commit) — is exactly what an automated release tool would compute purely by reading the commit messages, with no human manually deciding the numbers.

## 13. Production & Enterprise Usage

- CI/CD pipelines (§25) commonly gate a release job on pushes to `main` that include a new annotated tag matching a version pattern, triggering build, publish, and Release-creation steps automatically.
- Enterprises with compliance requirements often mandate **signed** tags (the signed-tags workflow above, §28) for anything reaching production, giving an auditable, tamper-evident chain from a specific approved commit to a specific released artifact.
- Package registries (npm, PyPI, crates.io, Docker registries) almost universally expect SemVer-compliant version strings, making the convention load-bearing far beyond just Git — a Git tag frequently becomes the literal version string published to a package registry in the same CI step.

## 14. Troubleshooting

| Symptom                                                  | Likely cause                                                                                  | Fix                                                                                                                |
| -------------------------------------------------------- | --------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Tag exists locally but nobody else can see it            | Plain `git push` doesn't push tags                                                            | `git push origin <tag>` or `--tags`/`--follow-tags`                                                                |
| `git tag` listing looks out of numeric order             | Default alphabetical/string sort                                                              | `git tag --sort=-v:refname` for version-aware ordering                                                             |
| Automated release tool computed the "wrong" version bump | A commit's type prefix was missing, wrong, or a `BREAKING CHANGE` footer was mistyped/missing | Review Conventional Commits formatting; some teams enforce it via a commit-msg hook (§24) or CI lint step          |
| Deleted a tag but the GitHub Release still shows         | Release and tag are independently managed, as described above                                 | Delete the Release explicitly via the platform's UI/API, separate from the `git tag`/`git push --delete` operation |

## 15. Interview Questions

**[Beginner] Q1. Why doesn't `git push` send my tags to the remote automatically?**
**Model answer:** Pushing commits and pushing tags are deliberately separate operations in Git — a plain `git push` only sends commits on the current branch to its tracked upstream. This lets you create local, exploratory, or personal tags without accidentally sharing them. To actually publish a tag you need `git push origin <tag-name>`, `git push origin --tags` for everything, or `git push --follow-tags` for a more disciplined middle ground that only pushes annotated tags reachable from what you're pushing.

**[Beginner] Q2. What does Semantic Versioning's `MAJOR.MINOR.PATCH` scheme communicate?**
**Model answer:** MAJOR increments signal a breaking, backward-incompatible change; MINOR increments signal new functionality that remains backward-compatible; PATCH increments signal a backward-compatible bug fix with no new functionality. It's a convention, not something Git or a package manager enforces mechanically, but downstream tooling — especially dependency resolvers using version ranges — relies on the promise being honored to know whether upgrading is safe.

**[Intermediate] Q3. How do Conventional Commits enable automated changelog and release generation?**
**Model answer:** Conventional Commits impose a structured prefix on every commit message — `feat:`, `fix:`, `BREAKING CHANGE:` (or `!`), among others — that encodes semantic meaning directly into history in a machine-parseable way. Release automation tools like semantic-release read every commit since the last tag, use the highest-precedence type present (a breaking change always forces a major bump, otherwise `feat` forces minor and `fix` forces patch) to compute the correct next SemVer version automatically, and generate a changelog grouped by type — eliminating the need for a human to manually decide the version number or hand-write release notes at release time.

**[Senior] Q4. A production incident is traced to a tag, `v3.2.0`, that was deleted and recreated pointing at a different commit after a last-minute fix. What went wrong, and what should the policy be?**
**Model answer:** This is the same supply-chain integrity failure described in §6 for force-moved tags, just via delete-and-recreate instead of `tag -f`: anyone who fetched the original `v3.2.0` — CI build caches, downstream consumers pinning a dependency by tag, an auditor's records — now silently has content that diverges from whatever `v3.2.0` currently points to, with no obvious signal that anything changed. The fix that seemed urgent should have been released as `v3.2.1`, treating `v3.2.0` as a permanent, immutable historical record even though it was flawed. The team policy should mandate that released tags are never deleted or recreated, enforce this with tag-protection rules on the hosting platform (§23) restricting delete/force-push on tags matching a release pattern, and, for genuinely sensitive releases, require signed tags (§28) so any attempt at tampering is cryptographically detectable rather than merely against policy.

**[Senior] Q5. Explain the relationship between a Git tag and a GitHub Release, and a scenario where confusing the two causes a real problem.**
**Model answer:** A Git tag is a plain, portable Git ref (or, if annotated, a real object) that travels with the repository through any clone or push — it's Git's own concept, host-agnostic. A GitHub Release is a separate, platform-hosted database record that wraps a tag with additional content: formatted release notes, binary attachments, and a "latest" marker — it cannot exist without an underlying tag, but a tag needs no Release to be valid. A real problem this causes: a team migrating from GitHub to a self-hosted Git server or GitLab (§23) correctly transfers every tag via a normal clone/push, but discovers all their carefully written Release notes and binary download attachments simply don't exist on the new platform, because Releases were never actually part of the Git data at all — they lived exclusively in GitHub's own database and require separate, deliberate export/migration if they need to be preserved.

## 16. Common Misconceptions

1. **"`git push` sends my tags along with my commits."** It does not, by default — tags require an explicit `git push origin <tag>`, `--tags`, or `--follow-tags`.
2. **"SemVer is enforced by Git or npm/pip automatically."** It's a convention that tooling _relies on_ being honored; nothing prevents a maintainer from technically violating it.
3. **"A pre-release version like `2.0.0-rc.1` sorts after `2.0.0`."** SemVer precedence rules explicitly sort pre-release versions _before_ their corresponding plain release.
4. **"Deleting a GitHub Release also deletes the tag (or vice versa)."** They are managed independently on the platform, even though the UI usually presents them together.
5. **"Lightweight tags are fine for real releases as long as I remember the version number."** They carry no tagger identity, date, message, or signature — exactly the metadata compliance audits and incident post-mortems typically need a year later; always use annotated (and, where appropriate, signed) tags for real releases.

## 17. 🔑 Key Takeaways

- Tags aren't pushed automatically by `git push` — use `git push origin <tag>`, `--tags`, or the more disciplined `--follow-tags`; never delete and recreate a released tag, for the same supply-chain-integrity reasons as force-moving one.
- Semantic Versioning (`MAJOR.MINOR.PATCH`, with pre-release and build-metadata suffixes) defines what a version number means; it's a convention downstream tooling relies on, not something Git enforces.
- Conventional Commits (`feat:`, `fix:`, `BREAKING CHANGE:`) structure commit messages so automated tooling can compute the correct next SemVer version and generate changelogs without human intervention — the direct bridge into CI/CD release automation (§25).
- Signed tags (§28 for full mechanics) add cryptographic tamper-evidence on top of the annotated tag object, appropriate for anything reaching production in a compliance-sensitive environment.
- A platform Release (GitHub/GitLab) always wraps an underlying tag but is a separate, platform-hosted, non-portable record — migrating repositories transfers tags automatically but not Releases.

## 18. Related Concepts & What's Next

Everything in Part 4 so far has been about creating, combining, undoing, and marking commits. §19 closes out the part with the tools for **interrogating** history you didn't create yourself, or made long ago and no longer remember precisely — advanced `git log`, `git blame`, `git bisect`'s systematic search for a regression, and `git grep`'s historical-tree search — the investigative toolkit that everything from incident response to code archaeology depends on.
