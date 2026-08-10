# Section 58 (Part 8): Calling Modules: Local Paths, Registry Sources, Git Sources

## 1. Definition

**Plain language:** When you write a `module` block, the `source` argument tells Terraform where to actually get that module's code from. It could be a folder sitting right next to your configuration, a published module on the Terraform Registry, or a specific repository (and even a specific path and ref within it) on GitHub or any other Git host.

**Precise definition:** The `source` argument on a `module` block accepts several address formats, each triggering different resolution logic during `terraform init`: a **local path** (beginning with `./` or `../`), which Terraform reads directly with no download step and no separate versioning; a **Terraform Registry source** (`<NAMESPACE>/<NAME>/<PROVIDER>`, e.g., `terraform-aws-modules/vpc/aws`), which Terraform resolves against a registry (public or private, [§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)) and downloads into `.terraform/modules/`; and a **generic remote source** — most commonly a **Git source** (`git::https://github.com/org/repo.git` or the shorthand `github.com/org/repo`), optionally with `//<subdirectory>` to select a path within the repo and `?ref=<tag|branch|commit>` to pin a specific revision — alongside other supported protocols (HTTP archive URLs, S3, GCS). Local sources are read live from disk on every `plan`/`apply` with no caching; registry and Git sources are downloaded once during `terraform init` and cached under `.terraform/modules/` until `init -upgrade` is run.

> 💡 **Tip:** The single most common source of "why did my module suddenly behave differently" incidents is a Git source pinned to a branch (`?ref=main`) instead of a tag or commit SHA. A branch ref is mutable — the next `terraform init` (or `init -upgrade`) can silently pull in commits nobody on the consuming team reviewed. Registry sources sidestep this by supporting proper semantic version constraints ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)); Git sources only get equivalent safety if `ref=` points at an immutable tag or commit SHA.

## 2. Why This Matters

- **Source choice determines the entire lifecycle of how a module gets updated.** Local paths change the instant the file on disk changes (no `init` needed); registry and Git sources require an explicit `terraform init` (or `-upgrade`) to pick up any change — understanding this distinction is essential for reasoning about "why doesn't my module change show up."
- **Local modules are the standard pattern within a single monorepo-style configuration**, where a `modules/` directory sits alongside the root module(s) that consume it and both live in the same Git repository and get reviewed/merged together.
- **Registry and Git sources are how modules are shared across repository boundaries** — across teams, across an organization, or with the public — enabling the reuse case that's the entire point of modularity ([§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)).
- **Git sources with subdirectory and ref syntax unlock precise sourcing** — pulling just one module out of a monorepo of many modules at a specific pinned commit, without needing that repo published to any registry at all.
- This section is the practical prerequisite for [§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md) (the public registry specifically) and [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md) (version constraints), since both depend on understanding the source syntax established here.

## 3. Prerequisites and Dependencies

This section assumes [§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)'s root/child module distinction and [§56](./Section-56-Part8-Module-Structure-and-Conventions.md)'s standard module structure — the various source addresses below all resolve to a directory following that structure. It also assumes basic familiarity with `terraform init`'s role in resolving providers and (now) modules, covered fully in [§24](../Part4/Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md), and with Git basics (cloning, tags, branches, commit SHAs) assumed as baseline knowledge per this roadmap's prerequisites.

## 4. Architecture / Conceptual Diagram

```text
module "network" {
  source = "???"     # three families of source address
}

┌────────────────────────────┬───────────────────────────────┬───────────────────────────────────────┐
│  LOCAL PATH                │  REGISTRY SOURCE              │  GIT SOURCE                           │
├────────────────────────────┼───────────────────────────────┼───────────────────────────────────────┤
│ source = "./modules/vpc"   │ source = "terraform-aws-      │ source = "git::https://github.com/    │
│ source = "../shared/vpc"   │   modules/vpc/aws"            │   org/tf-modules.git//vpc?ref=v1.2.0" │
│                            │ version = "~> 5.0"    (§60)   │                                       │
│                            │                               │ source = "github.com/org/repo"        │
│                            │                               │   (shorthand for git::https://...)    │
├────────────────────────────┼───────────────────────────────┼───────────────────────────────────────┤
│ Resolved: read live from   │ Resolved: `terraform init`    │ Resolved: `terraform init` clones     │
│ disk, every plan/apply,    │ downloads matching version    │ the repo (or fetches archive) once,   │
│ no caching, no `version`   │ into .terraform/modules/,     │ checks out `ref`, into                │
│ argument supported         │ respects `version` constraint │ .terraform/modules/                   │
├────────────────────────────┼───────────────────────────────┼───────────────────────────────────────┤
│ No version pinning —       │ Semantic version constraints  │ `ref=` can be a tag (immutable-ish),  │
│ always "whatever is on     │ (§60) — the safest, most      │ a branch (MUTABLE — risky), or a      │
│ disk right now"            │ standard mechanism            │ commit SHA (fully immutable)          │
└────────────────────────────┴───────────────────────────────┴───────────────────────────────────────┘
```

- Local paths are resolved relative to the **calling module's own directory**, not the root module's directory or the current working directory — a nested module referencing `./helper` resolves relative to itself, not to the top-level root.
- `terraform init` is the single moment all non-local sources are fetched; changing a registry `version` constraint or a Git `ref` requires re-running `init` (often `init -upgrade`) before the change takes effect — a `plan` alone will not re-fetch an updated source.

## 5. Hands-On

### 5.1 Local Path Source

**Purpose:** Show the simplest and most common source form, used for in-repo reuse.

**Syntax:**

```hcl
module "network" {
  source = "./modules/network"

  cidr_block = "10.0.0.0/16"
}

module "shared_tags" {
  source = "../shared-modules/tags"

  environment = "production"
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing modules...
- network in modules/network
- shared_tags in ../shared-modules/tags

Terraform has been successfully initialized!
```

**Production usage example:** Local sources are the default choice for a `modules/` directory living inside the same repository as the root module(s) consuming it — the standard shape for a single team's project, where both the module and its consumers are reviewed and merged in the same pull request.

**Common errors:** A local path is resolved relative to the calling module, not the current working directory — running `terraform init` from an unexpected directory does not change how `./modules/network` resolves; a mistyped relative path produces a clear "module not found" error at `init` time.

### 5.2 Terraform Registry Source

**Purpose:** Show the canonical `<NAMESPACE>/<NAME>/<PROVIDER>` registry address with a version constraint.

**Syntax:**

```hcl
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.0"

  name = "app-vpc"
  cidr = "10.0.0.0/16"
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing modules...
Downloading registry.terraform.io/terraform-aws-modules/vpc/aws 5.8.1 for vpc...
- vpc in .terraform/modules/vpc

Terraform has been successfully initialized!
```

**Production usage example:** This is the standard way to consume well-maintained public modules ([§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)) — the `terraform-aws-modules` namespace's `vpc`, `eks`, and `rds` modules are among the most widely used community modules in the AWS ecosystem, saving teams from re-implementing well-trodden provisioning patterns.

**Common errors:** Omitting `version` on a registry source is valid syntax but resolves to the latest published version at `init` time with no constraint — on a re-run of `init -upgrade` months later, this can silently pull a major version with breaking changes; [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md) covers the constraint operators that prevent this.

### 5.3 Git Source with Subdirectory and Ref Pin

**Purpose:** Show sourcing a single module out of a monorepo of many modules, pinned to an immutable tag.

**Syntax:**

```hcl
module "network" {
  source = "git::https://github.com/my-org/tf-modules.git//network?ref=v2.3.0"

  cidr_block = "10.0.0.0/16"
}

# GitHub shorthand (equivalent underlying protocol for github.com specifically):
module "iam" {
  source = "github.com/my-org/tf-modules//iam?ref=v1.0.4"
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing modules...
Downloading git::https://github.com/my-org/tf-modules.git?ref=v2.3.0 for network...
- network in .terraform/modules/network/network

Terraform has been successfully initialized!
```

**Production usage example:** Git sources with `//<subdir>` are the standard pattern for organizations that keep all their internal modules in a single "modules monorepo" without publishing to any registry — each module lives in its own subdirectory, and consumers pin to a tagged release of that subdirectory's content.

**Common errors:** Pinning `ref=main` (a branch, not a tag) means every `terraform init -upgrade` can pull in unreviewed new commits pushed to `main` after the consumer last initialized — this is the exact risk called out in the Tip above, and the fix is pinning to an immutable tag or full commit SHA instead.

## 6. Production Usage Notes

- **`terraform init -upgrade` is required to pick up a changed registry version constraint or Git ref** — simply editing the `version`/`ref` in configuration and running `plan` does not re-fetch the module; Terraform continues using whatever was cached in `.terraform/modules/` from the last `init` until explicitly told to upgrade.
- **Local sources have no version pinning mechanism at all** — because there's no concept of "download a specific version" for a path already on disk, reproducibility across a local-sourced module is entirely a function of Git history in the consuming repository (i.e., what commit of the whole repo you're on determines what's in `./modules/network`).
- **`.terraform.lock.hcl` ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)'s provider lock file) does not lock module sources the way it locks provider versions** — module source pinning is entirely the responsibility of the `source`/`version`/`ref` arguments in configuration; there is no separate module lock file equivalent for non-registry sources.

## 7. Security Considerations

- Git sources pulling from a URL over plain `http::` rather than `https::`, or from an untrusted third-party organization's repository, carry the same supply-chain risk as any external code dependency — a compromised or malicious module has full access to whatever provider credentials the calling configuration's provider blocks supply ([§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)).
- Prefer commit-SHA or immutable-tag pinning (`ref=<sha>` or `ref=v1.2.3` on a protected/tag-locked release process) for any Git-sourced module used in production, exactly to avoid the mutable-branch risk highlighted in the Tip.
- Private registry sources ([§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md), [§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) and private Git repositories both require credentials to resolve during `init` — ensure those credentials (Git SSH keys, registry tokens) are themselves handled via a secrets manager or CI secret store rather than committed into `.terraformrc` or checked-in configuration.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Likely Cause                                                                                         | Resolution Path                                                                                        |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ |
| `Error: Failed to download module` at `terraform init`                     | Typo in local path, invalid registry namespace/name/provider, or unreachable Git URL/ref             | Verify the exact source string against the module's documentation; check network/auth for Git/registry |
| Module behavior changed unexpectedly after a teammate ran `terraform init` | Git source pinned to a mutable branch ref (e.g., `ref=main`) picked up new unreviewed commits        | Repin to an immutable tag or commit SHA; treat this as equivalent to an unpinned dependency upgrade    |
| Editing a module's `version` constraint has no visible effect              | `terraform init -upgrade` was not run after the change; the previously cached module is still in use | Run `terraform init -upgrade` to force re-resolution against the new constraint                        |
| `Error: Module not installed` when running `terraform plan`                | `terraform init` was never run (or failed) after adding a new `module` block                         | Run `terraform init` before `plan`/`apply` any time a new `module` block or changed source is added    |

## 9. Best Practices

- Use local paths for modules that live in the same repository as their consumers and are always reviewed/merged together; use registry or Git sources once a module needs to be shared across repository boundaries.
- Always pin Git sources to an immutable tag or full commit SHA in anything beyond a personal scratch environment — never leave a production-consumed module pinned to a mutable branch.
- Prefer registry sources over raw Git sources when both are available for the same module — registry sources get first-class semantic version constraint support ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) that generic Git sources cannot offer as cleanly.

## 10. Common Anti-Patterns / Mistakes

- **Pinning a Git-sourced module to a branch instead of a tag or SHA "for convenience."** This silently reintroduces the exact non-reproducibility problem declarative IaC ([§1](../Part1/Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md)) exists to solve — two `terraform init` runs on the same configuration can resolve to different code.
- **Mixing local and remote sourcing inconsistently for the same logical module across environments** (e.g., `dev` uses a local path for fast iteration, `prod` uses a pinned registry version) without a deliberate process to promote tested local changes into a released version — this can let untested local-only changes silently diverge from what's actually running in production.
- **Forgetting `terraform init -upgrade` after intentionally bumping a version/ref**, then being confused when `plan` shows no change — a frequent, low-severity but recurring source of "did my module update actually take effect" confusion.

## 11. Interview Questions

**🎯 Beginner:** _"What are the three main kinds of `source` addresses a `module` block can use?"_
**Model answer:** A local filesystem path (`./modules/network`, beginning with `./` or `../`), a Terraform Registry address (`namespace/name/provider`, e.g., `terraform-aws-modules/vpc/aws`), and a generic remote source such as Git (`git::https://...` or the `github.com/org/repo` shorthand), optionally with a `//subdirectory` and a `?ref=` to pin a specific tag, branch, or commit.
_What the interviewer is probing for:_ Basic recall of the three source families and their correct syntax shapes.

**🎯 Intermediate:** _"You change a module's `version` constraint from `~> 5.0` to `~> 6.0` and run `terraform plan`. Nothing changes. Why, and what's the fix?"_
**Model answer:** Registry (and Git) module sources are resolved and downloaded once during `terraform init`, then cached in `.terraform/modules/` — `terraform plan` reads from that cache and does not re-resolve the source or re-check the version constraint on its own. The fix is running `terraform init -upgrade`, which forces Terraform to re-evaluate the constraint against available versions and re-download if a newer matching version is selected.
_What the interviewer is probing for:_ Understanding that module resolution is an `init`-time operation, distinct from `plan`/`apply`, which is a common point of confusion for newcomers.

**🎯 Senior:** _"Your organization keeps ~20 internal modules in one 'modules monorepo' repository, not published to any registry. What source strategy would you use for consumers, and what are the trade-offs versus using the private registry ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md))?"_
**Model answer:** Git sources with `//<subdirectory>?ref=<tag>` per module, tagging releases of the monorepo (or per-module tags like `network/v1.2.0` if modules are versioned independently within it) so each consumer pins to an immutable, reviewed revision. The trade-off versus a private registry is meaningful: Git sources give you version pinning via tags but lack the registry's structured semantic version constraint resolution (`~> 5.0` style ranges resolving against a list of published versions), lack the registry's auto-generated documentation UI, and require consumers to know the exact tag/subdirectory syntax rather than a clean `namespace/name/provider` address. A private registry ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md), part of Terraform Cloud/Enterprise) is generally the better long-term investment once the module count and consumer count justify the operational overhead of running or subscribing to one; Git sourcing from a monorepo is a reasonable, lower-overhead starting point for a smaller module inventory.
_What the interviewer is probing for:_ Real trade-off reasoning between Git-based and registry-based internal module distribution, not just knowing both exist.

**🎯 Architect:** _"A security incident review found that a Git-sourced module used across 30 root modules was pinned to `ref=main`, and an unreviewed commit to that branch had been silently picked up by several teams' `terraform init -upgrade` runs over the prior month, changing IAM policy resources. How do you prevent recurrence at an organizational level, not just fix this one module?"_
**Model answer:** This is a policy/tooling problem, not a one-off fix: (1) enforce immutable-ref pinning (tag or commit SHA, never a branch name) for all Git module sources via a linter/policy check (`tflint` custom rule or a pre-merge CI check scanning for `ref=` values that resolve to branches) rather than relying on individual authors remembering the convention; (2) migrate genuinely shared, multi-consumer modules to a private registry ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) where semantic version constraints ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) are the norm and there's no equivalent "mutable ref" footgun; (3) require any module source or version/ref change to go through the same PR review and CI plan-diff visibility as any other configuration change, since the actual failure here was that a code change propagated into production-adjacent configuration with no review gate at the point where it mattered; (4) audit all other Git-sourced modules across the organization for the same `ref=main`-style pinning as an immediate remediation sweep, since this is very unlikely to be an isolated instance.
_What the interviewer is probing for:_ Systemic thinking — treating a specific incident as a signal to fix a whole class of risk via tooling/policy, not just patching the one module that caused the incident.

## 12. Common Misconceptions

1. **"`terraform plan` will pick up a module source change just like it picks up a resource attribute change."** It will not — module source resolution happens at `terraform init` time; `plan`/`apply` operate against whatever was already resolved and cached.
2. **"A Git source pinned to a tag is exactly as safe as a commit SHA."** Tags are conventionally treated as immutable but can technically be force-moved by anyone with push access to re-point at a different commit — a full commit SHA is the only truly immutable pin; tags are a strong convention, not a hard guarantee, unless the Git host enforces tag protection.
3. **"Local module sources support version constraints just like registry sources."** They do not — the `version` argument is only meaningful for registry sources; a local path always reflects whatever is currently on disk, with reproducibility coming entirely from the consuming repository's own Git history.
4. **"The `github.com/org/repo` shorthand works for any Git host."** That specific shorthand is a convenience recognized for GitHub URLs; other Git hosts generally need the explicit `git::https://...` form.

## 13. 🔑 Key Takeaways

- `source` addresses fall into three families: local paths (no versioning, read live from disk), registry sources (`namespace/name/provider`, support semantic version constraints), and Git/generic remote sources (support `//subdirectory` and `?ref=` pinning, but no semantic version constraint resolution).
- Non-local sources are resolved and cached at `terraform init` time; changes to `version`/`ref` require `terraform init -upgrade` to take effect, not just a subsequent `plan`.
- Only registry sources get first-class semantic version constraint operators ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)); Git sources get pinning via `ref=`, which is only as immutable as the tag/commit it points to.
- Pinning a Git source to a mutable branch is a real, recurring production risk — always prefer an immutable tag or commit SHA for anything beyond local experimentation.
- Local module sources have no versioning mechanism of their own; their reproducibility depends entirely on the consuming repository's Git history.

## 14. Related Concepts & What's Next

[§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md) goes deeper into the Terraform Registry specifically — both consuming public modules and publishing your own. [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md) covers the version constraint operators (`~>`, `>=`, exact pins) that apply to registry sources, and clarifies exactly which source types do and don't support them. [§24](../Part4/Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md) covers `terraform init`'s broader responsibilities (backend init, provider install) alongside the module install behavior introduced here.

**Next Section:** [§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md) — `Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md`
