# Section 23 (Part 5): Git Hosting & Enterprise Platforms — GitHub, GitLab, Bitbucket; Protected Branches, CODEOWNERS, Governance

## 1. Definition

**Plain language:** A Git hosting platform is a service that runs Git remotes for you and wraps them in a web UI, access control, and collaboration tooling — issues, pull requests, CI, and administration — on top of the plain protocol [§20](./Section-20-Part5-Remotes-In-Depth.md) already covers.

**Precise:** At the protocol level, GitHub, GitLab, Bitbucket, and self-hosted alternatives are all, fundamentally, servers exposing Git repositories over HTTPS and/or SSH — anything [§20](./Section-20-Part5-Remotes-In-Depth.md)'s `fetch`/`push` can do against a bare repository ([§9](../Part3/Section-09-Part3-Creating-Cloning-Repositories.md)), these platforms do too. Everything distinguishing them — pull requests, issue trackers, CI runners, permission systems, compliance features — is **platform-layer product**, not Git itself. [§1](../Part1/Section-01-Part1-Version-Control-Fundamentals.md)'s Misconception #1 already flagged this distinction; this section is where it's earned in full.

## 2. Why It Exists / Problem It Solves

Bare Git, on its own, gives you object storage and refs — nothing about _who_ is allowed to push where, nowhere to discuss a change before merging it, no automated testing on incoming code, and no audit trail beyond commit metadata. Hosting platforms exist to close that gap at team and organization scale: centralized access control instead of manually managing SSH keys and shell accounts on a raw server, a web UI non-Git-experts can use, integrated code review ([§21](./Section-21-Part5-Collaboration-Models.md)), CI/CD ([§25](../Part6/Section-25-Part6-Git-in-CICD-Pipelines.md)), and governance features (SSO, audit logs, compliance reporting) that a bare `git` install has no concept of.

## 3. The Major Hosted Platforms

| Platform      | Owner                     | Distinguishing strength                                                                                                                                                                                                                                                                  |
| ------------- | ------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **GitHub**    | Microsoft (acquired 2018) | Largest ecosystem and open-source community by far; GitHub Actions for CI/CD; broad third-party/marketplace integration                                                                                                                                                                  |
| **GitLab**    | GitLab Inc.               | **Built-in CI/CD (GitLab CI/CD) as a first-class, deeply integrated part of the product from the start** — distinct from GitHub, where CI (Actions) was added later as a separate product; also ships integrated issue boards, container registry, and security scanning in one platform |
| **Bitbucket** | Atlassian                 | Deep native integration with **Jira** (issue tracking) and **Confluence** (docs) — the natural choice for teams already standardized on the Atlassian suite; supports both Git and (historically) Mercurial, though Mercurial support was discontinued                                   |

> ⚠️ **Common confusion to preempt:** GitLab CI/CD and GitHub Actions are **not the same product wearing different names** — they're separately engineered CI/CD systems with different config file formats (`.gitlab-ci.yml` vs `.github/workflows/*.yml`), different execution models, and different histories (GitLab's was built in from early on; GitHub's arrived years after GitHub itself). Full CI/CD mechanics are [§25](../Part6/Section-25-Part6-Git-in-CICD-Pipelines.md)'s subject; the distinction matters here only as a differentiator between the platforms.

All three offer broadly comparable core features today — pull/merge requests, issue tracking, wikis, protected branches, some form of built-in or pluggable CI — so platform choice in practice usually comes down to ecosystem fit (open-source visibility favors GitHub), existing tooling (Atlassian shops favor Bitbucket), or a team's preference for an all-in-one DevOps platform (GitLab's pitch).

## 4. Self-Hosting a Git Server

Not every organization wants — or is permitted — to store its code on a third party's infrastructure. Git's distributed design ([§1](../Part1/Section-01-Part1-Version-Control-Fundamentals.md)) means self-hosting requires nothing more exotic than a server that can serve a bare repository over a transport Git understands.

### 4.1 Bare Repositories over SSH — the Minimal Server

The simplest possible self-hosted Git server is: a machine with SSH access and a bare repository ([§9](../Part3/Section-09-Part3-Creating-Cloning-Repositories.md)) sitting on disk.

```bash
# On the server: create a bare repo (no working directory, just the
# object database and refs — exactly what §9 established a bare
# repo is for: a pure exchange point nobody edits directly)
$ mkdir -p /srv/git/webapp.git
$ cd /srv/git/webapp.git
$ git init --bare

# On a developer's machine: clone it over SSH, using whatever
# shell-account/SSH-key access the server already grants
$ git clone ssh://git@server.internal/srv/git/webapp.git

# ...or, if the developer already has a repo, just add it as a remote
$ git remote add origin ssh://git@server.internal/srv/git/webapp.git
$ git push -u origin main
```

That's a genuinely complete, working multi-developer Git server — every `fetch`/`push` mechanic from [§20](./Section-20-Part5-Remotes-In-Depth.md) works against it unmodified, access control is just standard Unix filesystem/SSH-key permissions on the server, and there's no platform software involved at all. This is precisely how many small teams and long-running open-source projects operated before hosting platforms existed, and it remains a legitimate, minimal option today.

### 4.2 `git daemon` — Read-Only Anonymous Access

For scenarios needing simple, read-only, unauthenticated access (mirrors, internal LAN distribution, no push capability), Git ships `git daemon`, a lightweight server for the plain `git://` protocol:

```bash
# On the server, serve every repository under /srv/git as read-only
$ git daemon --base-path=/srv/git --export-all /srv/git

# Clients fetch read-only, no authentication involved at all
$ git clone git://server.internal/webapp.git
```

The `git://` protocol has no encryption and no authentication — it is appropriate only for trusted networks or genuinely public read-only mirrors, never for anything requiring access control or transport security. It's mentioned here mainly because it appears in older documentation and exam material as one of Git's native transports (alongside `ssh://`, `https://`, and the local filesystem) — in current practice, SSH or HTTPS-backed platforms have almost entirely displaced it for anything beyond simple mirroring.

### 4.3 Self-Hosted Platforms

Between "bare repo over SSH" and a fully managed SaaS platform sits **self-hosted software that reimplements the platform layer** — PRs, issues, web UI, CI — on infrastructure the organization controls:

| Option                           | Notes                                                                                                                                                                |
| -------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **GitLab CE / EE, self-managed** | The same GitLab product, deployable on your own infrastructure; Community Edition is free/open-source, Enterprise Edition adds licensed governance/security features |
| **Gitea**                        | Lightweight, low-resource-footprint self-hosted Git service; simple to run (single binary), popular for small teams and homelab/self-hosting enthusiasts             |
| **Gogs**                         | Gitea's predecessor/sibling project (Gitea forked from Gogs in 2016); similar lightweight goals, smaller ongoing development pace today                              |
| **GitHub Enterprise Server**     | GitHub's own self-hosted offering, for organizations wanting GitHub's UI/workflow on-premises                                                                        |

### 4.4 When Organizations Choose Self-Hosting

- **Compliance and regulatory requirements.** Industries like finance, healthcare, and government often have contractual or legal obligations about where source code physically resides and who can access the infrastructure it runs on — a third-party SaaS platform may not satisfy those requirements regardless of its own security posture.
- **Air-gapped environments.** Defense, classified, or highly sensitive industrial systems sometimes require networks with no internet connectivity at all — a SaaS platform is categorically unusable, and self-hosting is the only option.
- **Cost at scale.** Per-seat SaaS pricing multiplied across a very large engineering org can exceed the cost of running equivalent infrastructure in-house, particularly once an org already has the operational capability (its own datacenter/ops team) to run the self-hosted equivalent efficiently.
- **Full infrastructure control.** Custom authentication integration, specific data-residency guarantees, or the ability to run security scanning/tooling entirely inside a private network without code ever leaving it.

The trade-off, honestly stated: self-hosting trades away the SaaS platform's managed reliability, automatic updates, and vendor-handled scaling for full control — an organization taking this path needs the operational maturity to run what is now their own critical piece of infrastructure.

## 5. Git GUI Clients

Not every developer, and not every workflow, is best served by the raw CLI this whole knowledge base has been teaching. GUI clients exist specifically to make common operations visually inspectable and less error-prone for their target use cases:

| Client                           | Notes                                                                                                                                                                                                                       |
| -------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **GitHub Desktop**               | Simple, opinionated, GitHub-centric; covers the common 80% of daily operations (commit, branch, push, pull, PR creation) with almost no learning curve                                                                      |
| **GitKraken**                    | Feature-rich commit-graph visualization, popular for understanding complex branch/merge topology at a glance; cross-platform, cross-platform-hosting-aware (works with GitHub, GitLab, Bitbucket, self-hosted)              |
| **Sourcetree**                   | Atlassian's free GUI client, tightly aligned with Bitbucket but works with any Git remote                                                                                                                                   |
| **VS Code's built-in Git panel** | Not a standalone app but an editor-integrated view — stage/commit/diff/branch without leaving the editor, plus a visual merge-conflict resolution UI; extremely popular simply because it requires installing nothing extra |

**What GUIs trade off against the CLI:** visual diffs, drag-and-drop staging, and a discoverable menu of common operations lower the barrier for less experienced users and make some operations (interactive staging of hunks, visualizing a tangled branch graph) genuinely easier to reason about than reading text output. Against that: GUIs rarely expose Git's full command surface (rebasing with unusual flags, plumbing commands, obscure refspec tricks), scripting/automation is CLI-only, and a developer who never learns the underlying CLI concepts can struggle badly the moment something goes wrong in a way the GUI doesn't have a button for. The professional norm is to know the CLI regardless of which tool you use day to day — every GUI client is, without exception, calling the same `git` binary and producing the same object-model changes underneath ([§4](../Part2/Section-04-Part2-Git-Architecture-Three-Areas.md)–[§7](../Part2/Section-07-Part2-Inside-Git-Loose-Objects-Packfiles-GC.md)), so nothing about using one changes what Git is actually doing.

## 6. Protected Branches

A **protected branch** is a hosting-platform rule (not a Git-core feature) that restricts what can happen to a specific branch — typically `main` and any release branches — regardless of who has general write access to the repository.

Common protections:

- **Require pull request review before merging** — no direct pushes allowed, even from users with write access; a specified number of approvals is mandatory.
- **Require status checks to pass** — CI ([§25](../Part6/Section-25-Part6-Git-in-CICD-Pipelines.md)) must report success before the merge button is even enabled.
- **Prevent force-pushes** — enforces [§20](./Section-20-Part5-Remotes-In-Depth.md)'s caution at the platform level, so a force-push to `main` is rejected outright regardless of local Git configuration.
- **Prevent branch deletion** — stops an accidental or malicious `git push origin --delete main`.
- **Require linear history** — rejects merge commits, effectively mandating rebase-and-merge or squash-and-merge ([§21](./Section-21-Part5-Collaboration-Models.md)) for that branch.
- **Restrict who can push, even within these rules** — e.g., only specific teams or roles can merge, even with an approved PR.

```
        Attempted push/merge to a PROTECTED branch
                          │
                          ▼
        ┌──────────────────────────────────┐
        │  Platform checks configured rules  │
        │  - PR + N approvals?               │
        │  - Required status checks green?   │
        │  - Not a force-push?               │
        │  - Author has required permission? │
        └──────────────┬────────────────────┘
                 all pass │  any fail
                    ▼            ▼
                 ALLOWED      REJECTED
```

> 💡 **Tip:** Protected branches are what makes a branching strategy ([§22](./Section-22-Part5-Branching-Strategies.md)) actually enforced rather than merely agreed-upon in a wiki page — without them, "we don't push directly to `main`" is a policy anyone with write access can accidentally or deliberately violate.

## 7. CODEOWNERS

A **CODEOWNERS** file declares which individuals or teams are automatically requested as reviewers when a pull request touches specific paths — turning "please remember to loop in the payments team on payment code" from a manual habit into an enforced rule.

```
# CODEOWNERS — supported by GitHub, GitLab, and Bitbucket with
# broadly similar syntax; this example uses GitHub's conventions.
# Location: .github/CODEOWNERS, docs/CODEOWNERS, or repo root

# Default owner for everything not matched below
*                       @platform-team

# Anything under /payments/ requires the payments team
/payments/              @acme/payments-team

# A specific file, owned by a named individual
/infra/terraform/prod.tf   @jane-doe

# Frontend code, multiple owners (any one approval may satisfy it,
# depending on platform branch-protection configuration)
/frontend/               @acme/frontend-team @john-smith
```

Matching is generally **last-match-wins**, like `.gitignore` ([§11](../Part3/Section-11-Part3-Ignoring-Controlling-Files.md)) — more specific patterns later in the file override earlier, broader ones, which is why `*` as a catch-all default typically sits at the top. When a PR touches a matched path, the platform automatically adds the corresponding owner(s) as requested reviewers; combined with a protected-branch rule requiring CODEOWNERS approval specifically, this guarantees the right domain experts are pulled into review without relying on anyone remembering to add them manually.

## 8. Governance at Scale

Beyond individual repositories, organizations running dozens or hundreds of repos and many teams need governance tooling operating above the repo level:

- **Organization/team permissions.** Role-based access (owner, admin, write, read, or platform-specific finer gradations) assigned per team and per repository, rather than managing individual user access on every repo one by one.
- **SSO/SAML integration.** Authentication delegated to the organization's existing identity provider (Okta, Azure AD, etc.), so platform access is provisioned and de-provisioned automatically as part of the company's normal employee lifecycle — critical for offboarding: a departed employee's access disappears the moment their central identity is disabled, without anyone remembering to separately revoke a Git-platform account.
- **Audit logs.** A record of security-relevant actions — permission changes, repository visibility changes, branch-protection rule changes, SSH key additions — for compliance review and incident investigation, distinct from Git's own commit history, which only records _content_ changes, not _administrative_ actions.
- **Branch protection rulesets / policy-as-code.** Larger platforms increasingly let organizations define protection rules once and apply them across many repositories by pattern (e.g., "every repo's `main` branch requires 2 approvals and passing CI"), rather than configuring each repository's protection individually — turning branch protection from a per-repo chore into an organization-wide policy.
- **Secret scanning / dependency and vulnerability alerts.** Increasingly bundled directly into the hosting platform rather than a bolt-on tool, flagging committed credentials or known-vulnerable dependencies automatically.

> ⚠️ **Critical clarification:** none of the protected-branches, CODEOWNERS, or governance features described above exist in plain Git. A bare repository served over SSH, as covered earlier in this section, has no concept of "protected branch," "CODEOWNERS," or "audit log" — these are entirely hosting-platform product features built on top of Git's protocol and object model. Understanding this boundary is exactly what separates "I know Git" from "I know GitHub" — genuinely distinct, if overlapping, bodies of knowledge, and precisely the conflation [§1](../Part1/Section-01-Part1-Version-Control-Fundamentals.md) flagged as the most common Git misconception on record.

## 9. Interview Questions

**[Beginner] Q1. What's the difference between Git and a platform like GitHub?**
**Model answer:** Git is the version control program itself — the object model, commands, and protocol for tracking history, which can run entirely locally with no server at all. GitHub is a company's hosting platform that runs Git servers and wraps them in a web UI plus additional product features: pull requests, issue tracking, CI/CD, and access control. GitLab and Bitbucket are competing platforms doing the same job. Git predates GitHub by three years and needs no hosting platform to function; you can self-host a fully working Git server with nothing but a bare repository and SSH access.

**[Beginner] Q2. What does marking a branch as "protected" typically prevent?**
**Model answer:** It's a platform-enforced set of rules on a specific branch, usually `main`, that commonly prevent direct pushes without an approved pull request, block merging until required CI status checks pass, forbid force-pushes, and prevent the branch from being deleted — regardless of what access an individual user otherwise has to the repository. It's the mechanism that makes a team's branching strategy actually enforced rather than just a written convention.

**[Intermediate] Q3. What problem does a CODEOWNERS file solve, and how does matching work?**
**Model answer:** It automatically requests specific people or teams as reviewers on a pull request based on which file paths the PR touches, so domain experts are guaranteed to be pulled into relevant reviews without anyone having to remember to add them manually — for example, any PR touching `/payments/` automatically requests the payments team. Matching works like `.gitignore`, using path patterns, with later, more specific rules in the file overriding earlier, broader ones — typically a catch-all `*` default owner sits at the top of the file, with more specific path rules below it taking precedence for the paths they match.

**[Intermediate] Q4. Why might an organization choose to self-host its Git infrastructure instead of using a SaaS platform?**
**Model answer:** The main drivers are compliance and regulatory requirements around where code physically resides and who can access its infrastructure, which a third-party SaaS platform may not be able to satisfy regardless of its own security practices; air-gapped environments with no internet connectivity at all, where a SaaS platform is categorically unusable; and cost at very large scale, where per-seat SaaS pricing can exceed running equivalent infrastructure in-house if the org already has the operational capacity to do so. Options range from a minimal bare repository served over SSH, needing no platform software at all, up to fully self-managed versions of platform software like GitLab CE/EE, GitHub Enterprise Server, or lightweight alternatives like Gitea. The trade-off is giving up managed reliability, automatic updates, and vendor-handled scaling in exchange for full control.

**[Senior] Q5. A newly acquired subsidiary needs its GitHub access revoked the day their employment system marks them terminated, with zero manual steps. What's the architecture, and why isn't repository-level permission management sufficient on its own?**
**Model answer:** The answer is SSO/SAML integration between the hosting platform and the organization's central identity provider, so platform authentication is entirely delegated rather than managed as a separate credential — the moment the identity provider disables the employee's account as part of the normal offboarding process, their ability to authenticate to the platform disappears automatically, with no separate manual revocation step. Repository-level permission management alone isn't sufficient because it only controls _authorization_ within the platform (what a valid, authenticated user can do) — it does nothing about _authentication_ itself; if the employee still has a valid platform login and password (or, worse, a still-valid SSH key or personal access token) independent of the company's central identity system, revoking their repo-level role doesn't actually lock them out, and someone has to remember to do it per-repository or per-organization. I'd also flag SSH keys and personal access tokens specifically as a common gap even with SSO in place — those need their own expiration/rotation policy, since a token issued before SSO enforcement may not automatically die when the identity provider account is disabled, depending on platform specifics.

## 10. Common Misconceptions

1. **"GitHub Actions and GitLab CI/CD are basically the same thing with different names."** They're separately built systems with different configuration formats and execution models; GitLab's was integrated into the product from early on, GitHub's arrived later as a distinct addition — full CI/CD treatment is [§25](../Part6/Section-25-Part6-Git-in-CICD-Pipelines.md).
2. **"You need a platform like GitHub to use Git collaboratively."** A bare repository served over SSH, requiring no platform software whatsoever, is a fully functional multi-developer Git server — platforms add convenience and governance, not the basic capability to collaborate.
3. **"Protected branches are a Git feature you configure with `git config`."** They're entirely a hosting-platform feature, configured through that platform's settings, not through Git itself — a bare Git server has no concept of a protected branch at all.
4. **"CODEOWNERS assigns commit access."** It only affects automatic reviewer requests; it doesn't grant or restrict who can push or merge on its own — that's the separate job of repository permissions and protected-branch rules (often used together, but mechanically distinct).
5. **"Self-hosting Git means giving up all modern collaboration features."** Self-hosted platforms like GitLab CE/EE or GitHub Enterprise Server provide essentially the same PR/review/CI feature set as their SaaS counterparts; only the truly minimal "bare repo over SSH" option covered earlier lacks that layer, and that's a deliberate choice for teams who don't need it, not a limitation of self-hosting generally.

## 11. 🔑 Key Takeaways

- Hosting platforms (GitHub, GitLab, Bitbucket) are product layers — PRs, issues, CI, permissions — built on top of plain Git; the underlying `fetch`/`push` protocol is unchanged from [§20](./Section-20-Part5-Remotes-In-Depth.md).
- GitLab's built-in CI/CD is a first-class, original part of the product, distinct from GitHub Actions, which arrived as a later addition; Bitbucket differentiates on native Jira/Confluence integration.
- Self-hosting ranges from a minimal bare repo over SSH, to `git daemon` for read-only anonymous access, to full self-managed platform software (GitLab CE/EE, Gitea, GitHub Enterprise Server) — chosen for compliance, air-gapped environments, or cost at scale.
- GUI clients (GitHub Desktop, GitKraken, Sourcetree, VS Code's Git panel) trade some of the CLI's full command surface and scriptability for visual discoverability; all of them call the same underlying `git` binary.
- Protected branches, CODEOWNERS, and org-level governance (SSO, audit logs, policy-as-code rulesets) are platform features with no equivalent in plain Git — they're what makes a chosen branching strategy and review process actually enforced rather than merely agreed-upon.

## 12. Related Concepts & What's Next

This section closes Part 5, which took Git from a single developer's local tool to a fully governed, multi-team collaboration system: remotes and synchronization ([§20](./Section-20-Part5-Remotes-In-Depth.md)), the human PR/review workflow ([§21](./Section-21-Part5-Collaboration-Models.md)), the branching-strategy policies that workflow operates within ([§22](./Section-22-Part5-Branching-Strategies.md)), and finally the platforms and governance tooling that host and enforce all of it ([§23](./Section-23-Part5-Git-Hosting-Enterprise-Platforms.md)). Part 6 turns to automating and scaling everything built here — hooks that run scripts at Git lifecycle events, CI/CD pipelines that plug into the PR checks referenced throughout this section, techniques for keeping Git usable at very large repository scale, and managing multi-repository projects with submodules and subtrees.
