# Section 25 (Part 6): Git in CI/CD Pipelines

## 25.1 Definition

**Plain language:** CI/CD systems watch a Git repository for events — someone pushed code, someone opened a pull request, someone created a tag — and automatically react by building, testing, and sometimes deploying, without a human manually triggering each step.

**Precise:** A CI/CD platform (GitHub Actions, GitLab CI, Jenkins, CircleCI, and others) registers itself against a repository's events, typically via a webhook the hosting platform fires on push/PR/tag activity, or via polling in older self-hosted setups. On each triggering event, the platform provisions a runner, performs a clone or fetch of the relevant ref, and executes a defined pipeline (build, lint, test, package, deploy) against that exact snapshot, then reports results back — often directly onto the pull request itself (§23).

## 25.2 Why It Exists / Problem It Solves

1. **Consistency.** "It works on my machine" is eliminated by running every check in an identical, disposable, reproducible environment rather than trusting each developer's local setup.
2. **Speed of feedback at scale.** Local hooks (§24) catch problems for one developer before they leave a machine; CI catches problems across every contributor's changes, continuously, without requiring anyone to remember to run anything.
3. **Gatekeeping merges.** Combined with branch protection (§23), CI results become a hard gate — code that fails tests or linting simply cannot merge, removing reliance on manual review catching every regression.
4. **Automating the path to production.** CD (continuous delivery/deployment) extends the same event-driven model past testing into actually shipping — the same Git event that triggers a build can, once it passes, trigger a deployment.

## 25.3 The Events CI Systems Trigger Off

| Git event                                               | Typical CI reaction                                                                                                        |
| ------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| **Push to any branch**                                  | Run build + test pipeline for fast feedback on that branch alone                                                           |
| **Push to a specific branch** (e.g., `main`, `develop`) | Run the same pipeline plus possibly deploy to a shared environment (staging)                                               |
| **Pull/merge request opened or updated**                | Run the full check suite against the _merged result_ (not just the source branch) and report status back onto the PR (§23) |
| **Tag created** (e.g., `v2.4.0`, §17)                   | Build and publish a release artifact, often triggering a production deployment                                             |
| **Scheduled (cron)**                                    | Not itself a Git event, but commonly layered on top — nightly full-suite runs, dependency-update checks                    |

```
Developer pushes commit
        │
        ▼
Hosting platform fires webhook ──► CI system receives event
        │
        ▼
Runner provisioned (fresh, disposable environment)
        │
        ▼
Clone/fetch the relevant ref  (often SHALLOW — §25.4)
        │
        ▼
Run pipeline: build → lint → test → package
        │
        ▼
Report status back
   ├─ onto the commit / PR (§23 status checks)
   └─ to dashboards, chat notifications, etc.
```

> 💡 **Tip:** Platform-specific syntax (`.github/workflows/*.yml`, `.gitlab-ci.yml`, Jenkinsfiles, CircleCI's `config.yml`) differs considerably, but the underlying model — event triggers a pipeline against a specific Git ref — is the same shape across every mainstream CI system. Understanding that shape transfers directly between platforms; memorizing one platform's YAML dialect does not.

## 25.4 Shallow Clones in CI

CI runners are disposable — they don't need the full commit history most of the time, only the working tree contents at one specific commit, plus enough context to run the pipeline. Cloning the entire history of a large, old repository on every single pipeline run wastes real time and bandwidth, multiplied across potentially hundreds of runs a day.

```bash
# Purpose: fetch only the most recent commit, not the full history
$ git clone --depth 1 https://github.com/example/large-repo.git
Cloning into 'large-repo'...
remote: Enumerating objects: 412, done.
remote: Total 412 (delta 89), reused 200 (delta 40)
Receiving objects: 100% (412/412), 8.2 MiB, done.
```

**Expected outcome:** a working tree identical to a full clone at that commit, but with only one commit's worth of history — dramatically faster on large or long-lived repositories, since most of the transferred data in a full clone is old commits' objects the pipeline will never touch.

Most CI platforms default to shallow clones (often `--depth 1` or a small configurable depth) precisely for this reason. Full mechanics of `--depth` and its close relative, partial clone, are covered in §26; this section previews only the CI-specific motivation and its limits.

**When shallow clones break down:**

- **Anything needing history depth.** `git log`, `git blame`, `git describe`, and diffing against an older commit all need commits the shallow clone never fetched — operations that work fine locally can fail or behave unexpectedly in a shallow CI checkout.
- **Merge-base calculations.** Determining the common ancestor between a PR branch and its target (needed for an accurate diff of "what actually changed in this PR") can require history beyond depth 1, especially on long-running branches — a common cause of CI diffs looking wrong or including unrelated changes.
- **Full-history operations.** Release tooling that walks the entire tag history, or security scanners auditing every historical commit, need `git fetch --unshallow` (converting a shallow clone into a complete one) or a full clone from the start.

```bash
# Purpose: convert an existing shallow clone into a full one when a later
# pipeline step turns out to need complete history
$ git fetch --unshallow
```

> ⚠️ **Common confusion to preempt:** a shallow clone is not corrupted or partial in the sense of missing files — the working tree at that one commit is completely correct and complete. What's missing is _history depth_ (older commits), not _content breadth_ (files at the current commit). Confusing the two leads to unnecessary "just do a full clone to be safe" defaults that undo the entire performance benefit for the common case.

## 25.5 GitOps

Introduced as a tip in §1 and previewed there, GitOps is the practice of treating a Git repository — not a dashboard, not a running server's mutable state, not an engineer's memory of "what I last deployed" — as the **single source of truth** for what infrastructure and application state _should_ be.

### 25.5.1 The core model

```
┌─────────────────────────┐
│   Git repository         │   desired state, declared as code:
│   (source of truth)      │   Kubernetes manifests / Terraform / Helm values
└────────────┬──────────────┘
             │ operator continuously watches for changes
             ▼
┌─────────────────────────┐
│   Operator (e.g. ArgoCD,  │   compares desired state (Git) against
│   Flux)                   │   actual state (live cluster/infra)
└────────────┬──────────────┘
             │ reconciles differences automatically
             ▼
┌─────────────────────────┐
│   Live infrastructure     │   converges to match Git — no manual
│   (cluster, environment)  │   `kubectl apply` by a human required
└─────────────────────────┘
```

An engineer changes desired state by opening a pull request against the Git repository — the same review, approval, and status-check machinery already covered for ordinary code (§23) applies unchanged to infrastructure changes. Once merged, an **operator** (commonly named tools like ArgoCD or Flux in the Kubernetes ecosystem — mentioned here by name only, not deep-dived, since they're platform-specific tools rather than Git concepts) continuously polls or watches the repository and reconciles the live environment to match, pulling the change rather than a human pushing it out.

### 25.5.2 Why this is attractive

- **Git's existing guarantees become infrastructure's guarantees.** Full history of every infrastructure change, `git blame` on who changed what and why, `git revert` as the rollback mechanism, pull-request review as the change-approval process — none of this needs separate tooling; it's already there.
- **Drift detection.** Because the operator continuously compares live state against Git, any out-of-band manual change (someone `kubectl edit`-ing a resource directly) is detected as drift and can be automatically reverted, which enforces that Git genuinely stays authoritative rather than becoming stale documentation.
- **Auditability.** Every change to production infrastructure has an associated commit, author, and (ideally) review trail — directly serving the compliance use case named back in §1.2.

> ⚠️ **Critical clarification:** GitOps is an operating _model_, not a specific tool or a Git feature. Git itself has no special "GitOps mode" — GitOps works because ordinary Git mechanics (commits, PRs, tags, history) happen to be exactly what's needed for a reconciliation loop, combined with an external operator that does the watching and applying.

## 25.6 Branch- and Tag-Triggered Deployment Patterns

| Trigger                                                                                      | Common deployment target                       | Rationale                                                                                                                                                                                                                                            |
| -------------------------------------------------------------------------------------------- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Push/merge to `main` (or `develop`, depending on branching strategy — full treatment in §22) | Staging / shared integration environment       | Continuous integration of everyone's work into one environment for early conflict detection                                                                                                                                                          |
| Tag creation (`v2.4.0`, §17)                                                                 | Production                                     | Tags mark deliberate, immutable release points (§17) — using them as the production trigger means production only ever deploys something explicitly, intentionally marked as a release, not just "whatever happened to be the latest commit on main" |
| Push to `release/*` branch                                                                   | Pre-production / release-candidate environment | Isolates stabilization work (bug fixes only, no new features) from ongoing `main` development, per branching-strategy models covered in §22                                                                                                          |
| Pull request opened                                                                          | Ephemeral preview/review environment           | Lets reviewers see a running version of the actual proposed change before approving, common on platforms with preview-deployment integrations                                                                                                        |

```bash
# Conceptual pipeline trigger config (platform-agnostic pseudocode,
# illustrating the shape shared across GitHub Actions / GitLab CI / etc.)
on:
  push:
    tags:
      - 'v*'
jobs:
  deploy-production:
    steps:
      - checkout
      - build release artifact
      - deploy to production
```

**Purpose:** ties production deployment strictly to tag creation, not to every commit landing on a branch — a deliberate, auditable trigger rather than an implicit one.

## 25.7 Status Checks Reported to a Pull Request

Once a pipeline runs against a PR's commits, its pass/fail result is reported back to the hosting platform and surfaced directly on the pull request — the mechanism §23 covers from the branch-protection side (requiring specific checks to pass before merge is even allowed). From the CI side, this typically means the pipeline authenticates back to the platform's API (or the integration is native, as with GitHub Actions) and posts a status against the exact commit SHA it ran against.

```
Pull Request #482: "Add payment retry logic"
├─ Commits: 3
├─ Status checks:
│    ✔ lint              (12s)
│    ✔ unit-tests         (2m 14s)
│    ✗ integration-tests  (failed — 1 test)
│    ⏳ deploy-preview     (running)
└─ Merge blocked: required check "integration-tests" is failing
```

**Consequence:** because status is tied to the specific commit SHA, pushing a new commit to the PR (even a one-line fix) invalidates prior passing statuses for the old SHA and re-triggers the pipeline against the new one — reviewers should never treat "this PR passed CI" as durable across further pushes without checking which commit the green check actually refers to.

## 25.8 Hands-On Conceptual Walkthrough — Full Event-to-Deploy Flow

```bash
# Developer's local flow (nothing platform-specific yet)
$ git switch -c feature/retry-logic
$ git commit -am "feat(payments): add retry with exponential backoff"
$ git push -u origin feature/retry-logic

# On the hosting platform: open a PR feature/retry-logic -> main
# CI fires automatically on the push and again whenever the PR updates
# Reviewer approves once required checks are green (§23)
# PR is merged -> triggers pipeline again against main
# Team tags a release once ready:
$ git tag -a v2.5.0 -m "Release 2.5.0: payment retry logic"
$ git push origin v2.5.0
# Tag push triggers the production deployment pipeline (25.6)
```

## 25.9 Interview Questions

**[Beginner] Q1. What Git events commonly trigger a CI pipeline, and what does each typically produce?**
**Model answer:** The three most common triggers are a push to a branch, a pull/merge request being opened or updated, and a tag being created. A push to a feature branch typically runs build and test for fast feedback; a PR update runs the full check suite and reports results directly onto the PR, gating whether it can merge; a tag creation is commonly used to trigger building and publishing a release artifact, often followed by a production deployment, since tags mark deliberate, immutable release points rather than arbitrary commits.

**[Intermediate] Q2. Why do CI systems default to shallow clones, and what can go wrong because of it?**
**Model answer:** CI runners typically only need the working tree contents at one specific commit to run a build or test suite, not the repository's entire history — cloning full history on every pipeline run wastes time and bandwidth, especially on large or long-lived repositories, multiplied across many runs per day. `git clone --depth 1` fetches just the latest commit, which is fine for most build/test steps. It breaks down for operations that genuinely need history: `git log`, `git blame`, `git describe`, merge-base calculations between a PR branch and its target, or any tooling that walks tag history — these either fail outright or behave unexpectedly against a shallow clone, and the fix is either `git fetch --unshallow` mid-pipeline or clone with sufficient depth (or fully) from the start when the pipeline is known to need it.

**[Intermediate] Q3. Explain GitOps in your own words, and name the two things it fundamentally requires.**
**Model answer:** GitOps treats a Git repository as the single source of truth for desired infrastructure or application state — instead of applying changes directly to a live environment, an engineer changes a declarative file (Kubernetes manifests, Terraform, etc.) in Git via a normal pull request. It fundamentally requires two things: state expressed as version-controlled, declarative files that Git can meaningfully diff and review, and an external operator (commonly named tools like ArgoCD or Flux) that continuously watches the repository and reconciles the live environment to match it. Git itself has no built-in GitOps feature — the pattern works because ordinary Git mechanics (history, PR review, revert, tags) happen to provide exactly the audit trail and change-control infrastructure needs.

**[Senior] Q4. A team's PR shows a green checkmark for "all tests passing," but the reviewer later discovers the merged code actually fails in production. What's a likely Git-related explanation?**
**Model answer:** Status checks are tied to a specific commit SHA, not to "the PR" as an abstract, ever-current entity. If a reviewer approved based on a check that ran against an earlier commit, and then either the base branch moved (new commits landed on `main` that the PR wasn't re-tested against) or a subsequent push to the PR branch happened without re-triggering or without the reviewer noticing the check re-ran against a new SHA, the green checkmark they saw may no longer correspond to what actually got merged. Also worth checking: whether CI actually ran tests against the _merged result_ (PR branch merged into target) versus only the PR branch in isolation — a common gap where the PR branch passes alone but conflicts semantically, not just textually, with concurrent changes already on the target branch. The mitigation is requiring checks to run against the up-to-date merge result and requiring branches be current with their target before merge, both configurable via branch protection (§23).

**[Architect] Q5. Design a branch/tag-triggered deployment strategy for a service with distinct staging and production environments, and justify the Git event you'd tie each to.**
**Model answer:** I'd tie staging deployment to merges into `main` (or `develop`, depending on the team's branching model, §22) — every integrated change flows to staging automatically and quickly, since staging exists precisely to catch integration problems early with low ceremony. I'd deliberately _not_ tie production to the same trigger; instead, production deploys only on tag creation following semantic versioning (§17) — a human deliberately decides "this exact commit is release 2.5.0" by creating an annotated, ideally signed, tag, and that explicit, auditable act — not the accident of being the latest commit on main at 5pm on a Friday — is what triggers production. This gives a clean audit trail (which tag deployed when, tied to release notes generated from Conventional Commits, §18), a natural rollback story (redeploy a previous tag), and separates "code is integrated and tested" from "code is a release," which are genuinely different decisions that shouldn't share a trigger. I'd pair this with required status checks on the PRs that fed `main` (§23) so that by the time anything is even eligible to be tagged, it has already passed the full gate.

## 25.10 Common Misconceptions

1. **"CI needs the full repository history to build and test code."** Almost never true for ordinary build/test — the working tree at one commit suffices, which is exactly why shallow clones are the sane default; full history is only needed for specific history-aware operations.
2. **"GitOps means 'we use Git for our infrastructure code.'"** That's a necessary ingredient but not the whole model — GitOps specifically means an automated operator continuously reconciles live state to match Git, not merely that Terraform files happen to live in a repository that a human applies manually.
3. **"A green CI check on a PR is a permanent guarantee."** It's a snapshot tied to one specific commit SHA at one point in time; new commits to the PR or changes to the target branch can invalidate it, and platforms differ in how aggressively they force re-verification (§23's "require branches up to date" setting exists specifically to close this gap).
4. **"Shallow clones are unsafe or produce incomplete code."** The checked-out content at the target commit is completely correct and complete; what's absent is history depth, not file content — a distinction worth being precise about in an interview.

## 25.11 🔑 Key Takeaways

- CI/CD systems trigger off Git events — push, PR/MR open or update, tag creation — and run pipelines against the exact ref associated with that event, reporting results back onto the commit or pull request.
- Shallow clones (`--depth 1`) are the sane default for most CI runs since only the working tree at one commit is usually needed; history-dependent operations require `git fetch --unshallow` or a deliberately deeper/full clone.
- GitOps treats a Git repository as the source of truth for desired infrastructure/application state, with an external operator (ArgoCD, Flux, etc.) continuously reconciling live state to match it — a Git-adjacent operating model, not a Git feature.
- Tag-triggered production deployment (vs branch-triggered staging deployment) ties the highest-stakes trigger to a deliberate, auditable, semantically versioned act (§17) rather than to an arbitrary latest commit.
- Status checks are tied to specific commit SHAs, not to a PR as a whole — this is central to how branch protection (§23) actually enforces "only tested code merges."

## 25.12 Related Concepts & What's Next

This section connected Git's event model to the automation layer built on top of it, completing the automation arc started with local hooks in §24. §26 turns to a different pressure entirely — what happens when the repository itself becomes too large to clone, check out, or work with comfortably at all, and the toolbox (shallow clones revisited in depth, partial clone, sparse-checkout, Git LFS) Git and the ecosystem provide for scaling past that point.
