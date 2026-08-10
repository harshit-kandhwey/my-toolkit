# Section 106 (Part 15): Project Structure Best Practices at Scale (Monorepo vs. Polyrepo)

## 1. Definition

**Plain language:** Once an organization has dozens or hundreds of Terraform-managed environments instead of one, the question stops being "how do I write a resource block" and becomes "where do these files live, in how many repositories, and how do changes in one part avoid accidentally touching another." Monorepo vs. polyrepo is the decision of whether all that Terraform configuration lives in a single Git repository or is split across many.

**Precise definition:** A **monorepo** layout keeps all (or most) Terraform root modules, shared modules, and environment configurations for an organization inside a single version-control repository, typically with a directory structure that separates environments, teams, and modules by path. A **polyrepo** layout splits Terraform configuration across multiple independent repositories — often one per team, one per application, or one per major system boundary (networking, platform, application) — each with its own history, access controls, and CI pipeline. Neither is a Terraform feature; both are organizational conventions layered on top of ordinary root modules ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)) and remote state ([§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md)), and the choice interacts directly with how state is split ([§109](./Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)), how modules are versioned and sourced ([§58](../Part8/Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md), [§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)), and how CI/CD pipelines are wired ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)).

> 💡 **Tip:** The real axis of decision isn't "one repo vs. many" — it's "what is the blast radius of a single `terraform apply`, and what is the blast radius of a single pull request." Repo structure is one lever for controlling both, but state splitting ([§109](./Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) is the lever that actually enforces blast-radius boundaries; repo structure without corresponding state splitting just organizes files without limiting what a bad apply can touch.

## 2. Why This Matters

- **Blast radius control.** A monorepo with one giant state file lets one bad `apply` touch every environment an organization has; correct structure — regardless of repo count — keeps root modules and their state scoped to something a team can reason about.
- **Change velocity and review friction.** Polyrepo isolates changes so a networking team's PR never shows up in an application team's review queue, but it also means shared module updates require coordinated multi-repo bumps; monorepo makes cross-cutting changes atomic but risks review queues drowning in unrelated diffs.
- **Ownership and access control.** Repo boundaries are a natural (if coarse) enforcement point for who can propose changes to what — a polyrepo split along team lines maps access control directly onto repository permissions, something a monorepo has to achieve instead through CODEOWNERS files and CI path filters.
- **CI/CD pipeline design.** Structure determines whether a single pipeline run can know exactly which root modules changed (crucial for pipelines that run `plan`/`apply` per environment, [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) or whether it must diff paths to figure out what changed inside a large monorepo.
- **Onboarding and discoverability.** A well-structured monorepo lets a new engineer `grep` across the whole organization's infrastructure in one place; a sprawling, inconsistent polyrepo (dozens of repos with different internal conventions) makes "where does X live" a genuine research problem.

## 3. Prerequisites and Dependencies

This section assumes familiarity with root vs. child modules ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)), remote backends ([§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)), and file layout for multi-environment projects ([§71](../Part10/Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md)), since project structure decisions are really an extension of those choices applied at organizational scale. [§109](./Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md) (state splitting for performance) and [§110](./Section-110-Part15-Versioning-Strategy-Terraform-Core-Providers-and-Modules.md) (versioning strategy) build directly on the structural choices made here.

## 4. Architecture / Conceptual Diagram

```text
MONOREPO LAYOUT                          POLYREPO LAYOUT
(single Git repository)                  (multiple Git repositories)

infra/                                   terraform-modules-networking/
├── modules/                               ├── modules/vpc/
│   ├── vpc/                               ├── modules/subnets/
│   ├── ecs-service/                       └── versions tagged v1.4.0, v2.0.0
│   └── rds-postgres/
├── live/                                terraform-live-networking/
│   ├── prod/                              ├── prod/us-east-1/
│   │   ├── us-east-1/                     └── staging/us-east-1/
│   │   │   ├── networking/
│   │   │   ├── platform/                terraform-live-team-payments/
│   │   │   └── payments-app/              ├── prod/
│   │   └── eu-west-1/                     └── staging/
│   ├── staging/
│   └── dev/                             terraform-live-team-checkout/
└── .github/workflows/                     ├── prod/
    ├── plan-on-pr.yml                     └── staging/
    └── apply-on-merge.yml
                                          Each repo: own CI pipeline, own
One repo, one CI system, path-based      access controls, own release
triggers decide which root modules       cadence for shared modules
`plan`/`apply` per PR (§102)             (pinned via module registry, §60)
```

- The monorepo's `live/` tree mirrors environment/region/team boundaries in directory paths; each leaf directory is its own root module with its own state (state splitting, [§109](./Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md), happens by directory even though everything is one repo).
- The polyrepo split here is by concern: a dedicated repo for shared modules (versioned and tagged, consumed via registry or Git source refs, [§58](../Part8/Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)) and separate "live" repos per team or per major system, each independently deployable.
- Both layouts can — and in mature organizations usually do — combine: a monorepo of shared modules alongside polyrepo "live" repositories per team that consume those modules at pinned versions.

## 5. Hands-On

### 5.1 A Monorepo `live/` Directory Convention

**Purpose:** Show a concrete, scalable directory convention for keeping many environments' root modules inside one repository without them colliding.

**Syntax:**

```text
live/
  <environment>/
    <region>/
      <system>/
        main.tf
        variables.tf
        outputs.tf
        backend.tf
        terraform.tfvars
```

**Example usage and expected output:**

```bash
$ find live -maxdepth 4 -type d
live/prod/us-east-1/networking
live/prod/us-east-1/platform
live/prod/us-east-1/payments-app
live/staging/us-east-1/networking
live/staging/us-east-1/payments-app

$ cd live/prod/us-east-1/payments-app && terraform init
Initializing the backend...
Successfully configured the backend "s3"!
```

**Production usage example:** CI pipelines use path-based change detection (e.g., `paths:` filters in GitHub Actions, or a tool like `tfvars`-aware diffing scripts) so a PR touching only `live/staging/us-east-1/payments-app/` triggers a plan against just that root module's state — not every environment in the repository.

**Common errors:** Placing shared logic directly inside a `live/` leaf directory (instead of factoring it into `modules/` and calling it) causes the same resource blocks to be copy-pasted across dozens of environment directories, which is the structural root cause of the "hardcoded values, duplicated blocks" anti-pattern covered in depth in [§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md).

### 5.2 A Polyrepo Module-Consumption Pattern

**Purpose:** Show how a "live" repository pins a specific version of a module published from a separate repository, which is the mechanism that makes polyrepo module reuse safe.

**Syntax:**

```hcl
module "vpc" {
  source  = "git::https://git.example.com/infra/terraform-modules-networking.git//modules/vpc?ref=v2.0.0"

  cidr_block = "10.20.0.0/16"
  az_count   = 3
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing modules...
Downloading git::https://git.example.com/infra/terraform-modules-networking.git?ref=v2.0.0 for vpc...
- vpc in .terraform/modules/vpc/modules/vpc

$ terraform plan
Plan: 4 to add, 0 to change, 0 to destroy.
```

**Production usage example:** A dedicated `terraform-modules-networking` repository tags releases (`v1.4.0`, `v2.0.0`) using semantic versioning ([§110](./Section-110-Part15-Versioning-Strategy-Terraform-Core-Providers-and-Modules.md)); every consuming "live" repository pins an explicit `ref`, so a breaking change to the module (e.g., a renamed variable) never silently propagates into a live environment until that environment's owner deliberately bumps the ref.

**Common errors:** Pointing `source` at a branch (`?ref=main`) instead of a tag is the single most common polyrepo mistake — it silently pulls whatever the module repo's `main` branch contains at `init` time, meaning two `terraform init` runs on the same unchanged "live" configuration can resolve to different module code.

## 6. Production Usage Notes

- **State boundaries should drive directory boundaries, not the other way around.** Decide first how state should be split for blast-radius and performance reasons ([§109](./Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)), then let the directory (monorepo) or repository (polyrepo) structure mirror those boundaries — designing directories first and discovering state problems later tends to produce structures that don't actually limit blast radius.
- **Monorepo scaling requires tooling investment.** Beyond a few dozen root modules, a monorepo needs path-based CI triggers, a consistent module-versioning convention even for in-repo modules, and often a tool like Terragrunt or a custom wrapper to avoid every root module needing hand-maintained, near-duplicate `backend.tf`/`provider.tf` boilerplate.
- **Polyrepo scaling requires governance investment.** Beyond a handful of repositories, an organization needs a template/scaffolding process (so every new "live" repo starts from the same conventions), a private module registry ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) or consistent Git-tag discipline, and a way to answer "which repos are on module version X" — without that, polyrepo drifts into dozens of inconsistent snowflake repositories.

## 7. Security Considerations

- Polyrepo access control maps naturally onto least privilege — a team that should only ever modify its own environments gets repository-level permissions matching exactly that, whereas a monorepo requires path-scoped CODEOWNERS and CI job permissions to achieve the same isolation, and a misconfigured path filter can silently grant broader write access than intended.
- Shared modules consumed across repo or directory boundaries are a supply-chain surface: a compromised or maliciously altered module (especially one pulled by branch reference rather than a pinned, ideally signed, tag) can inject unwanted resources or data exfiltration into every consumer at once — pin module sources and prefer the private registry's provenance features ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) over raw Git URLs where available.
- In a monorepo, a single compromised CI credential with repo-wide write access can potentially touch every environment's state; scoping CI service-account credentials per path or per environment (least-privilege execution roles, [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)) is more work in a monorepo than in a polyrepo, where repo-scoped credentials are the default.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                          | Likely Cause                                                                                     | Resolution Path                                                                                                                                                                                                                                                                  |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A PR touching one environment's config triggers `plan`/`apply` on unrelated ones | CI pipeline lacks path-based filtering in a monorepo, or is misconfigured to scan the whole tree | Add explicit path filters per root module in the CI workflow; verify with a dry-run PR touching one path                                                                                                                                                                         |
| Module changes break consumers unexpectedly across several repos                 | Consumers pinned `source` to a branch ref instead of a tagged version                            | Repin all consumers to explicit version tags ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)); adopt semantic versioning discipline in the module repo ([§110](./Section-110-Part15-Versioning-Strategy-Terraform-Core-Providers-and-Modules.md)) |
| Two engineers can't find where a given environment's configuration lives         | Inconsistent or undocumented directory/repo naming conventions grew organically over time        | Document and enforce one naming convention (environment/region/system) repo-wide or org-wide; add a root-level index                                                                                                                                                             |
| Onboarding a new team to Terraform takes days of "where does X go" questions     | No scaffolding/template for new root modules or repos exists                                     | Build a `cookiecutter`-style or internal template repo that new environments/teams are cloned from                                                                                                                                                                               |

## 9. Best Practices

- Mirror state boundaries in directory or repository structure — every leaf that has its own state ([§109](./Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) should be its own clearly named root module directory or repository, never a shared one.
- Separate reusable modules from environment-specific root configurations structurally (`modules/` vs. `live/`, or a dedicated modules repo vs. live repos) so the difference between "code meant to be called with different inputs" and "code meant to be applied directly" is unambiguous at a glance.
- Standardize a naming convention (environment, region, system/team) and apply it consistently whether the structure is monorepo directories or polyrepo repository names — consistency matters more than which specific convention is chosen.
- Pin all module sources to explicit, immutable version references (Git tags, registry version constraints, [§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) regardless of monorepo or polyrepo — never consume a module by a mutable branch reference in a live environment.

## 10. Common Anti-Patterns / Mistakes

- **One giant root module for an entire organization's infrastructure**, regardless of whether it lives in a monorepo or polyrepo — this is really a state-splitting failure ([§109](./Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) wearing a directory-structure costume, and it's covered from the state angle in [§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md).
- **Polyrepo sprawl without shared conventions.** Dozens of repositories that each invented their own directory layout, backend configuration style, and naming scheme independently — technically decoupled, but practically as hard to navigate as no structure at all.
- **Monorepo without path-based CI scoping.** Running `terraform plan`/`apply` against the entire tree on every PR regardless of what changed, which both wastes CI time and increases the chance of an unrelated environment being touched by mistake.
- **Choosing monorepo or polyrepo as a company-wide religious commitment rather than a per-boundary decision.** Large organizations often benefit from a hybrid: a monorepo of shared modules, polyrepo for team-owned live environments — a single dogmatic choice for everything is rarely optimal at real scale.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a monorepo and a polyrepo approach for Terraform?"_
**Model answer:** A monorepo keeps all Terraform configuration — modules and environment-specific root configurations — in one Git repository, usually organized by directory (environment, region, team). A polyrepo splits configuration across multiple repositories, often one per team or one per major system, each with independent history and access controls. Neither is a Terraform-specific feature; it's an organizational convention for how files and repositories are organized.
_What the interviewer is probing for:_ Basic awareness that this is an organizational decision, not a Terraform CLI or language feature.

**🎯 Intermediate:** _"What are the tradeoffs between monorepo and polyrepo for a mid-size platform team?"_
**Model answer:** Monorepo gives atomic cross-cutting changes (one PR can update a shared module and every consumer's pin in the same commit), easier organization-wide search, and simpler tooling setup, but requires investment in path-based CI triggers to avoid touching unrelated environments and can produce noisy, unfocused review queues. Polyrepo gives natural access-control boundaries mapped to repository permissions and fully independent CI/release cadences per team, but requires coordinated multi-repo updates for shared module changes and more governance overhead to keep conventions consistent across repos. The right choice depends on team topology more than technical merit — teams that already own separate deployment cadences tend to fit polyrepo naturally.
_What the interviewer is probing for:_ Whether the candidate sees this as an organizational-design tradeoff, not a purely technical one.

**🎯 Senior:** _"A team's monorepo has grown to 40 root modules and CI now runs `plan` on every one for every PR, taking 45 minutes. How do you fix this without a full restructure?"_
**Model answer:** The fix is almost always path-based change detection rather than restructuring: configure CI to diff the PR against the base branch, determine which root module directories actually changed (directly or via a changed shared module they depend on), and only plan/apply those. Tools like `tj-actions/changed-files` in GitHub Actions, or purpose-built wrappers like Terragrunt's `run-all` with `--terragrunt-strict-include`, are common implementations. The harder part is dependency-aware triggering — a shared module change under `modules/vpc` needs to trigger plans on every root module that consumes it, which requires either a dependency graph the CI script maintains or accepting a coarser "changed module → plan everything" fallback. A full split into polyrepo is a much bigger, usually unnecessary, hammer for what's fundamentally a CI-triggering problem.
_What the interviewer is probing for:_ Whether the candidate reaches for the proportionate fix (CI tooling) instead of jumping to a structural rewrite, and understands the dependency-detection subtlety.

**🎯 Architect:** _"You're setting structural policy for an organization with 12 independent product teams, each owning separate AWS accounts, all consuming a shared set of platform modules (networking, IAM baseline, logging). Design the repo/directory structure and justify the boundaries."_
**Model answer:** Use a hybrid: one dedicated monorepo for platform modules (`terraform-platform-modules`), versioned with semantic tags per module or per repo release ([§110](./Section-110-Part15-Versioning-Strategy-Terraform-Core-Providers-and-Modules.md)), consumed via a private registry ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) so every team pins explicit versions. Each product team gets its own "live" repository (polyrepo) scoped to their AWS account(s), containing only root modules that call the shared platform modules plus their own application-specific resources — this maps access control directly onto AWS account boundaries and lets each team release independently without touching a shared PR queue. Inside each team's live repo, use a monorepo-style directory convention (environment/region) since that's a single team's own concern and doesn't need repo-level isolation. The platform modules repo needs the heaviest governance — a CODEOWNERS-gated review process, semantic versioning discipline, and a deprecation policy for breaking changes — because a bad module release potentially affects every one of the 12 teams. This design optimizes for the actual organizational boundary (team/account ownership) rather than applying one repo-count decision uniformly.
_What the interviewer is probing for:_ Ability to design structure around real organizational boundaries (ownership, blast radius, release cadence) rather than reciting "monorepo good" or "polyrepo good" as absolutes.

## 12. Common Misconceptions

1. **"Monorepo vs. polyrepo is primarily a Terraform state decision."** State splitting ([§109](./Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) is the mechanism that actually limits blast radius; repo/directory structure is an organizational convenience layered on top, not a substitute.
2. **"Polyrepo automatically means better isolation."** Without independently split state per repository, a polyrepo can still share a single giant state file (via a shared remote backend key) across repos — repo boundaries alone guarantee nothing about blast radius.
3. **"An organization must pick one model for everything."** Mature organizations routinely mix a monorepo for shared modules with polyrepo live environments, or vice versa, matched to where the actual ownership boundaries sit.
4. **"Monorepos don't scale."** They scale fine with proper path-based CI tooling; what doesn't scale is a monorepo with no change-detection tooling, which is a CI design gap, not an inherent monorepo limitation.

## 13. 🔑 Key Takeaways

- Monorepo vs. polyrepo is an organizational convention for where Terraform files live, layered on top of (not a substitute for) state splitting for blast-radius control ([§109](./Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)).
- Directory or repository structure should mirror state boundaries — every independently-stated root module should be a clearly named, discoverable unit regardless of which model is chosen.
- Monorepos need path-based CI tooling to scale; polyrepos need shared conventions and governance to avoid sprawl.
- Always pin module sources to immutable version references, never mutable branch refs, regardless of structure.
- Hybrid approaches — a monorepo of shared modules consumed by polyrepo "live" environments — are common and often optimal at real organizational scale.

## 14. Related Concepts & What's Next

[§109](./Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md) covers the state-splitting decisions that should actually drive the directory/repo boundaries discussed here. [§110](./Section-110-Part15-Versioning-Strategy-Terraform-Core-Providers-and-Modules.md) covers the versioning discipline that makes shared-module consumption safe across either model. [§111](./Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md) closes Part 15 by placing Terraform's structural role alongside Ansible and Kubernetes in a full infrastructure stack.

**Next Section:** [§107](./Section-107-Part15-Terraform-vs-Pulumi-vs-CDK-vs-CloudFormation-Bicep.md) — `Section-107-Part15-Terraform-vs-Pulumi-vs-CDK-vs-CloudFormation-Bicep.md`
