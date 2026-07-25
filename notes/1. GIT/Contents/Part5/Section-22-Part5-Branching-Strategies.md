# Section 22 (Part 5): Branching Strategies — Git Flow, GitHub Flow, GitLab Flow & Trunk-Based Development

## 22.1 Definition

**Plain language:** A branching strategy is a team-wide agreement about which branches exist, what each one means, how long branches live, and exactly when and how they merge into each other — the policy layer sitting on top of the mechanical branch commands from §12.

**Precise:** Formally, a branching strategy specifies: (1) the set of **long-lived** branches and their roles, (2) the rules for creating **short-lived** branches from them, (3) the merge direction and method (§21.6) permitted between each pair, and (4) how releases and hotfixes are cut. None of this is enforced by Git itself — it's convention, optionally backed by platform tooling like protected branches (§23).

## 22.2 Why It Exists / Problem It Solves

Branches are cheap (§12.2) — that's exactly the problem a strategy solves. Cheap branches mean a team of twenty can easily end up with two hundred branches, no shared understanding of which ones are safe to build on, which are stale, which represent what's actually in production versus what's merely "done," and no consistent process for cutting a release or an emergency hotfix. A branching strategy answers, in advance and for the whole team: where do I branch from to start new work, where does my work go when it's done, and how does a fix reach production. Different strategies answer these questions differently because different teams have genuinely different constraints — release cadence, number of concurrently supported versions, team size, and deployment model all push toward different answers.

## 22.3 Git Flow

Introduced by Vincent Driessen in a widely circulated 2010 blog post, Git Flow was the first branching model to gain broad, named adoption — for years it was treated as _the_ default answer to "what's your branching strategy," to the point of becoming near-synonymous with "using Git properly" in many teams' minds.

### 22.3.1 The Model

Five branch types, each with a defined role:

| Branch               | Lives          | Branched from            | Merges into              | Purpose                                                                        |
| -------------------- | -------------- | ------------------------ | ------------------------ | ------------------------------------------------------------------------------ |
| `main` (or `master`) | Forever        | —                        | —                        | Always reflects production-released code; every commit on it is a release      |
| `develop`            | Forever        | `main` (once, initially) | —                        | Integration branch; always reflects the latest delivered development state     |
| `feature/*`          | Until merged   | `develop`                | `develop`                | New functionality, in progress                                                 |
| `release/*`          | Until released | `develop`                | `main` **and** `develop` | Stabilization window for an upcoming release — bug fixes only, no new features |
| `hotfix/*`           | Until released | `main`                   | `main` **and** `develop` | Urgent production fix, bypassing the normal `develop` cycle                    |

```
main     ●───────────────●──────────────●───────────►  (each commit = a release)
          \             ▲ \             ▲
           \    hotfix /   \   release /
            \   fix───●     \  1.1────●
             \               \        ▲
develop  ●────●──────●─────────●──────●──────●────────►
          \          ▲          \    (merge back)
           \feature /            \
            \login─●              \feature/search
                                   ●─────●
```

- **New feature work:** branch `feature/x` from `develop`, work, merge back into `develop` when done (never directly into `main`).
- **Preparing a release:** branch `release/1.1` from `develop` once `develop` has everything the release needs; only bug fixes land on the release branch during stabilization; when ready, merge into both `main` (tagging the release, §18) and back into `develop` (so those fixes aren't lost from ongoing development).
- **Emergency production fix:** branch `hotfix/x` directly from `main` (skipping `develop` entirely, since `develop` may contain unfinished, unreleased work you don't want in the emergency fix), fix, merge into both `main` (tag a new patch release) and `develop`.

### 22.3.2 Why It's Considered Heavyweight Today

Git Flow was designed for a world of **scheduled, infrequent releases** — think desktop software shipped quarterly, where "what's in `develop`" and "what's actually released" are genuinely different things worth tracking separately. Two long-lived branches plus three categories of short-lived ones, each with strict merge-direction rules, is substantial process overhead. For teams practicing continuous delivery — deploying many times a day, where every merge to `main` can go to production within minutes — the `develop`/`main` split adds a layer of indirection with no corresponding benefit: there's no meaningful gap between "integrated" and "released" to model. This is precisely why the simpler models below emerged and now dominate for web/SaaS-style delivery, while Git Flow (or something close to it) still fits contexts that genuinely have Git Flow's original constraints: shipping multiple supported versions simultaneously (e.g., versioned desktop or embedded software, libraries with LTS branches).

## 22.4 GitHub Flow

A deliberately minimal model, popularized by GitHub for its own simplicity: **one long-lived branch, everything else is short-lived, deploy from feature branches or immediately after merge.**

### 22.4.1 The Model

```
main  ●───●───────●───────●───────●───────●─────────►   always deployable
       \         ▲ \             ▲
        \feature/  \  feature/  /
         \login────●  \search──●
          (PR, review, merge)
```

1. Branch off `main` for anything — feature, fix, experiment. Name it descriptively.
2. Commit and push regularly.
3. Open a PR early, even in draft form, for visibility and CI.
4. Discuss and review (§21.5–21.7).
5. Deploy from the branch for final validation, or merge to `main` and deploy from there — the model is explicit that `main` is _always_ deployable, so merging is not a scary event.
6. Merge, then deploy (if not already validated pre-merge).

There is no `develop`, no `release/*`, no `hotfix/*` — a production bug fix is just a normal branch off `main`, reviewed and merged the same way as any feature, because there's no separate integration branch it needs to reconcile with.

### 22.4.2 Trade-offs

- **Strength:** minimal ceremony, matches continuous-deployment reality directly, easy to teach to a new team member in five minutes.
- **Weakness:** offers no built-in answer for supporting multiple released versions simultaneously (there's only one `main`, representing "current"), and provides no natural "stabilization window" for teams that do need one before a release.

## 22.5 GitLab Flow

Positioned explicitly as a middle ground: keep GitHub Flow's simplicity for day-to-day feature work, but add environment or release branches for teams that need a deployment-stage story or must support multiple released versions — needs Git Flow addressed but GitHub Flow deliberately left out.

### 22.5.1 Environment Branches Variant

```
main        ●───●───●───●───●───►   merged features land here first
             \       \       \
              ▼        ▼        ▼   (deploy by merging main forward
staging      ●────────●────────●     through each environment branch,
              \         \             not by branching backward)
               ▼          ▼
production   ●────────────●
```

Code always flows **downstream** — `main` → `staging` → `production` — by merging forward through environment branches, never by branching an environment off arbitrarily. Each environment branch's tip is, by definition, what's actually deployed there right now, giving you a precise, git-native answer to "what's in production" (`git log production`) without a separate deployment tracking system.

### 22.5.2 Release Branches Variant

For teams shipping multiple supported versions (closer to Git Flow's original problem): `main` stays the trunk, and a `release/2.4` branch is cut when version 2.4 ships. Fixes destined for the current release are cherry-picked (§17) from `main` onto the relevant `release/*` branch rather than developed there directly — keeping `main` as the single source of truth for all new work while still letting `2.4.1`, `2.4.2` patch releases happen independently.

### 22.5.3 GitLab Flow vs the Other Two

| Aspect              | Git Flow                                        | GitHub Flow                                   | GitLab Flow                                                                                                    |
| ------------------- | ----------------------------------------------- | --------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| Long-lived branches | `main` + `develop`                              | `main` only                                   | `main` + environment or release branches as needed                                                             |
| Best fit            | Scheduled releases, multiple supported versions | Continuous deployment, single current version | Continuous deployment with an explicit staged rollout, or multi-version support without full Git Flow overhead |
| Release visibility  | Tags on `main`, separate from `develop`         | Deploys are just "merged to `main`"           | Environment branch tips directly show what's deployed where                                                    |
| Ceremony            | High                                            | Low                                           | Medium — only as much as the team's actual deployment/release needs require                                    |

## 22.6 Trunk-Based Development

Not a naming convention for branches so much as a discipline about branch **lifetime**: everyone works off one shared trunk (`main`), branches — if used at all — live for hours to a couple of days, and integration happens continuously rather than in occasional large merges.

### 22.6.1 The Model

```
main  ●─●──●─●───●──●─●────●──●───●─●──●────►   many small, frequent
       \ \  \ \   \  \ \    \  \   \ \  \        integrations; branches
        ●  ●  ●    ●  ●      ●  ●   ●  ●         (if used) live hours,
       (short-lived branches, or direct            not days or weeks
        small commits straight to main by
        trusted, experienced contributors)
```

Two operating variants:

- **Branch-per-change, merged same-day** — the common variant, compatible with PR review; branches exist mainly as a PR staging area, not as a place work lives for weeks.
- **Committing straight to `main`** — some highly disciplined teams (notably at Google-scale, with very strong CI/testing gates and code review before submit rather than after) skip feature branches almost entirely, relying on pre-submit review and automated testing as the gate instead of a long-lived branch.

### 22.6.2 Feature Flags: The Enabling Technology

Trunk-based development's central problem is obvious: if everyone merges to `main` constantly and `main` is always deployable, how do you work on something that takes three weeks without shipping a half-finished feature to users? The answer is **feature flags** (also called feature toggles): the incomplete code merges to `main` and ships to production like anything else, but is wrapped in a runtime conditional that keeps it inactive (or active only for internal users/a canary cohort) until it's ready. This decouples **merging** (a Git/code event, safe and continuous) from **releasing** (a business/product event, controlled separately) — a distinction that's central to modern continuous-delivery pipelines and is revisited from the deployment-automation side in §25.

> 💡 **Tip:** Feature flags trade a code-complexity cost (conditional logic, eventual flag cleanup debt) for a process-complexity win (no long-lived branches, no giant merge-day risk). Teams that adopt trunk-based development without disciplined flag lifecycle management (removing flags once a feature is fully rolled out) accumulate exactly the kind of cruft the model was supposed to avoid.

### 22.6.3 Why Large Tech Companies Favor It

- **Merge conflict cost grows with branch lifetime and divergence**, roughly proportional to how much both `main` and the branch have changed since they diverged — short-lived branches keep this cost small and constant; long-lived branches accumulate it exponentially, culminating in the dreaded multi-day "integration merge" that Git Flow's `develop`-then-`release` model is especially prone to at scale.
- **Continuous integration is only meaningful with frequent integration.** CI (§25) is designed to catch problems the moment code is combined; a team that branches for weeks before merging is running CI on isolated code that hasn't actually been "integrated" until the final merge, defeating much of CI's purpose.
- **Large organizations, huge monorepos, thousands of daily commits** (§1.8's Google/Meta/Microsoft examples) make long-lived divergent branches operationally unworkable at scale — the coordination cost of many teams each holding weeks-old branches against a fast-moving trunk compounds badly.

## 22.7 Decision Framework

| Factor                       | Leans toward Git Flow                     | Leans toward GitHub Flow         | Leans toward GitLab Flow                                | Leans toward Trunk-Based                                 |
| ---------------------------- | ----------------------------------------- | -------------------------------- | ------------------------------------------------------- | -------------------------------------------------------- |
| Release cadence              | Scheduled, infrequent (monthly/quarterly) | Continuous, multiple times a day | Continuous, with staged rollout                         | Continuous, very high commit velocity                    |
| Number of supported versions | Multiple simultaneous                     | One (current)                    | One or a few, explicitly modeled                        | One (current)                                            |
| Team size / experience       | Any                                       | Small-to-medium                  | Small-to-large                                          | Large, with strong CI/testing culture                    |
| Product type                 | Desktop/embedded/versioned libraries      | Web apps, SaaS                   | Web apps needing explicit staging/production visibility | High-scale web services, monorepos                       |
| Tooling maturity needed      | Low                                       | Low                              | Medium                                                  | High (feature flags, strong CI/CD, fast automated tests) |

No strategy is objectively "best" — the honest senior answer is always "it depends on release cadence, how many versions you support in parallel, and how mature your CI/testing/feature-flag tooling is," not a single favorite recited from memory.

## 22.8 Interview Questions

**[Beginner] Q1. What problem does a branching strategy solve that plain Git branching (§12) doesn't already solve?**
**Model answer:** Git makes branches cheap and easy to create, but it has no opinion at all about what any given branch _means_, how long it should live, or which branches are allowed to merge into which. A branching strategy is the team-level convention that answers those questions — for example, that `feature/*` branches always come from and return to `develop`, or that `main` must always be deployable — so that everyone on the team shares the same mental model of the repository's branch structure instead of each person inventing their own.

**[Beginner] Q2. Describe Git Flow's branch structure in one or two sentences.**
**Model answer:** Git Flow has two permanent branches — `main`, which always reflects released production code, and `develop`, which reflects the latest integrated development work — plus three kinds of temporary branches: `feature/*` branched from and merged back into `develop`, `release/*` branched from `develop` for stabilization before merging into both `main` and `develop`, and `hotfix/*` branched directly from `main` for urgent production fixes, also merged into both.

**[Intermediate] Q3. Why has Git Flow fallen out of favor for many modern web/SaaS teams even though it was once the default recommendation?**
**Model answer:** Git Flow was designed around scheduled, infrequent releases where "what's integrated in `develop`" and "what's actually released to users" are meaningfully different states worth tracking with separate branches. Teams practicing continuous delivery — deploying many times a day, where a merge to `main` can reach production within minutes — don't have that gap, so the `develop`/`main` split and the multiple branch categories add process overhead without a corresponding benefit. Simpler models like GitHub Flow, with a single long-lived branch that's always deployable, fit that delivery cadence far better; Git Flow remains a good fit specifically for products that do support multiple released versions simultaneously, like versioned libraries or desktop/embedded software.

**[Intermediate] Q4. What is a feature flag, and why is it considered essential to trunk-based development?**
**Model answer:** A feature flag is a runtime conditional that lets incomplete or unreleased functionality exist in the codebase, merged into `main` and even deployed to production, while remaining inactive — or active only for a limited internal/canary audience — until it's deliberately turned on. Trunk-based development relies on very frequent merges to a single shared trunk, but real features often take longer to build than a single day; without feature flags, developers would be forced to either merge unfinished, potentially broken functionality live to all users, or keep long-lived branches around, which undermines the whole point of trunk-based development. Flags decouple the Git-level act of merging from the product-level act of releasing, letting both happen on their own independent schedules.

**[Senior] Q5. A 200-person engineering org is debating trunk-based development vs GitLab Flow with release branches. What questions would you ask before recommending one?**
**Model answer:** The central question is whether the org needs to support multiple released versions of the product simultaneously, or only ever has one "current" version live. If it's the latter — a typical SaaS product with continuous deployment — trunk-based development is usually the stronger fit, but only if the org actually has the supporting maturity: fast, reliable automated test suites (since there's no long-lived branch acting as a review buffer), a working feature-flag system with discipline around flag cleanup, and strong code-review or pre-submit gating to compensate for short-lived or absent branches. If the org genuinely ships and patches multiple versions in parallel — for example, enterprise customers pinned to different release trains — GitLab Flow's release-branch variant, cherry-picking fixes from `main` onto the relevant `release/*` branches, models that reality directly in a way pure trunk-based development doesn't naturally handle. I'd also probe team structure: 200 engineers on one trunk needs very strong CI throughput and merge-conflict tooling, or trunk-based development becomes a bottleneck rather than a speed-up; a large org sometimes splits into services/monorepo boundaries specifically to keep each trunk's contributor count manageable, which is really an architecture question wearing a branching-strategy costume.

## 22.9 Common Misconceptions

1. **"Git Flow is the 'correct' or 'official' Git branching model."** It's one popular convention proposed in a 2010 blog post, not a feature of Git itself or an endorsed standard; Git has no opinion on branching strategy at all.
2. **"Trunk-based development means no branches, ever."** It means branches, if used, are short-lived (hours to a couple of days), not that branching is forbidden — most trunk-based teams still use short-lived branches as a PR staging mechanism.
3. **"GitHub Flow and GitLab Flow are the same thing, just from different vendors."** GitHub Flow is deliberately minimal (one long-lived branch); GitLab Flow explicitly extends that minimalism with optional environment or release branches for teams that need staged deployment visibility or multi-version support — they solve different scopes of problem.
4. **"Feature flags are only a trunk-based-development concept."** They're broadly useful in any strategy for decoupling deploy from release (e.g., dark-launching a feature), but they're specifically _necessary_ — not just useful — for trunk-based development's viability, which is why they're treated as core to it.
5. **"Choosing a branching strategy is a purely technical decision the tech lead makes alone."** It has to match release cadence, support/versioning commitments, team size, and CI/testing maturity — getting it wrong shows up as either excessive process overhead or chaotic, conflict-heavy integration, so it's as much an organizational fit question as a technical one.

## 22.10 🔑 Key Takeaways

- Branching strategies are team convention layered on Git's mechanically opinion-free branch primitives (§12) — Git enforces none of this on its own.
- Git Flow: `main` + `develop` permanent, plus `feature/*`, `release/*`, `hotfix/*` temporary branches — built for scheduled releases and multi-version support; heavyweight for continuous delivery.
- GitHub Flow: one long-lived `main`, short-lived branches, PR-and-merge, always deployable — minimal ceremony, fits continuous deployment.
- GitLab Flow: GitHub Flow's simplicity plus optional environment or release branches — the deliberate middle ground.
- Trunk-based development: very short-lived branches (or direct trunk commits), enabled by feature flags decoupling merge from release; favored at scale because merge-conflict and integration cost grows with branch divergence.
- No strategy is universally best — match it to release cadence, number of supported versions, team size, and CI/testing/feature-flag maturity.

## 22.11 Related Concepts & What's Next

This section built on §12's branch mechanics and §21's PR/review workflow to describe the higher-level policies teams layer on top of both. §23 closes out Part 5 by looking at where all of this actually runs: the hosting platforms (GitHub, GitLab, Bitbucket) and the governance features — protected branches, CODEOWNERS, org-level permissions — that make a chosen branching strategy actually enforceable rather than merely agreed-upon.
