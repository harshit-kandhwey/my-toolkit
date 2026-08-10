# Section 110 (Part 15): Versioning Strategy: Terraform Core, Providers, and Modules

## 1. Definition

**Plain language:** A Terraform codebase depends on three independently-versioned things — the Terraform CLI/core itself, the provider plugins it downloads, and any modules it calls — and each can change out from under a team if version constraints aren't deliberately managed. A versioning strategy is the deliberate, organization-wide policy for how each of those three is pinned, tested, and upgraded, so that "it worked yesterday" doesn't silently stop being true tomorrow.

**Precise definition:** **Terraform core versioning** is governed by the `required_version` constraint in a `terraform` block, controlling which CLI versions are permitted to run a given configuration. **Provider versioning** is governed by `required_providers` version constraints ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)) plus the `.terraform.lock.hcl` dependency lock file, which pins exact resolved provider versions (including checksums) per configuration. **Module versioning** is governed by the `version` argument on registry-sourced module calls ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) or Git ref pinning for Git-sourced modules ([§58](../Part8/Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)), combined with the module author's own adherence (or not) to semantic versioning when publishing releases. All three follow semantic versioning (`MAJOR.MINOR.PATCH`) by convention — HashiCorp for core and official providers, community authors for community providers and modules — and a coherent strategy treats all three as one coordinated system rather than three unrelated pinning decisions.

> 💡 **Tip:** The lock file (`.terraform.lock.hcl`) and the version constraint (`required_providers`) answer two different questions that are easy to conflate. The constraint says "what range of versions is this configuration allowed to use." The lock file says "which exact version, with which checksum, did we actually resolve to and verify last time." A constraint alone doesn't guarantee reproducibility across machines or time — two `init` runs against a loose constraint with no lock file present can resolve to different exact versions. The lock file is what makes provider resolution reproducible, not the constraint by itself.

## 2. Why This Matters

- **Unpinned or loosely pinned versions break reproducibility silently.** A configuration with `required_providers { aws = { version = ">= 4.0" } }` and no committed lock file can resolve to a different exact provider version on every fresh `init`, meaning "works on my machine" can genuinely mean a different provider version than CI used.
- **Terraform core upgrades can include breaking changes to HCL semantics or CLI behavior** across major versions — a codebase with no `required_version` constraint offers no protection against someone running `terraform apply` with an incompatible CLI version and hitting confusing, hard-to-diagnose errors.
- **Provider major version bumps routinely include breaking changes** (renamed arguments, removed deprecated resources, changed default behaviors) — the well-known `aws` provider v3→v4 transition, for instance, changed default tagging and S3 bucket resource structure significantly enough to require real migration work, not just a version bump.
- **Module version pinning is what makes shared modules safe to consume at all** — without it, a module's author can push a breaking change that silently propagates into every consumer's next `init`, which is the exact scenario [§106](./Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md) flags as the most common polyrepo module-consumption mistake.
- **Coordinated upgrades across dozens of root modules require a deliberate strategy**, not ad hoc "bump it when something breaks" — this is precisely what prevents the provider sprawl anti-pattern covered in [§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md).

## 3. Prerequisites and Dependencies

This section assumes familiarity with provider configuration and version constraints ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)), the Terraform Registry ([§10](../Part2/Section-10-Part2-The-Terraform-Registry-and-Sourcing-Providers.md)), module versioning ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)), and CLI installation/version pinning tools like tfenv ([§5](../Part1/Section-05-Part1-Installation-and-Setup-tfenv-package-managers-version-pinning.md)). It synthesizes those individually-introduced mechanisms into one coherent organizational strategy, directly extending [§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md)'s provider-sprawl anti-pattern into its concrete prevention.

## 4. Architecture / Conceptual Diagram

```text
THREE INDEPENDENTLY VERSIONED LAYERS, ONE COORDINATED STRATEGY

┌─────────────────────────────────────────────────────────────┐
│  TERRAFORM CORE                                             │
│  required_version = "~> 1.7.0"      (terraform block)       │
│  Enforced by tfenv/.terraform-version in CI and local dev   │
└─────────────────────────────────────────────────────────────┘
                          │ runs
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  PROVIDERS                                                  │
│  required_providers { aws = { version = "~> 5.30" } }       │
│  .terraform.lock.hcl — EXACT resolved version + checksums,  │
│  committed to version control, regenerated deliberately     │
│  ("terraform init -upgrade") not implicitly                 │
└─────────────────────────────────────────────────────────────┘
                          │ configuration calls
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  MODULES                                                    │
│  module "vpc" {                                             │
│    source  = "app.terraform.io/org/vpc/aws"                 │
│    version = "~> 2.1"        ◄── semantic versioning, module│
│  }                                                          │  author's release discipline
│  OR git source pinned to an immutable tag (?ref=v2.1.0)     │
└─────────────────────────────────────────────────────────────┘

UPGRADE FLOW (deliberate, not automatic):
  1. Bump constraint in a branch/PR, not directly on main
  2. terraform init -upgrade  → regenerates lock file
  3. terraform plan  → review for unexpected diffs from new
     provider/module defaults or renamed arguments
  4. Merge only after plan is clean or diffs are understood
     and intentional
```

- The lock file sits between the constraint and the actual resolved version — committing it is what turns "a range of acceptable versions" into "the exact version everyone, everywhere, actually uses" until someone deliberately runs `-upgrade`.
- Each layer's upgrade cadence can be — and often should be — independent: core might be bumped quarterly, providers monthly or on security advisory, modules whenever a consuming team opts in — but all three still need constraints expressive enough to prevent accidental drift between deliberate upgrades.

## 5. Hands-On

### 5.1 Pinning Terraform Core and Providers Together

**Purpose:** Show the combined `terraform` block pattern that pins both core and provider version ranges, and how the lock file complements it.

**Syntax:**

```hcl
terraform {
  required_version = "~> 1.7.0"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.30"
    }
  }
}
```

**Example usage and expected output:**

```bash
$ terraform version
Terraform v1.6.2

$ terraform init
Error: Unsupported Terraform Core version

This configuration does not support Terraform version 1.6.2.
To proceed, either choose another supported Terraform version or
update the required_version constraint.
```

**Production usage example:** Committing both `required_version` and a `.terraform.lock.hcl` file, combined with a `.terraform-version` file for tfenv ([§5](../Part1/Section-05-Part1-Installation-and-Setup-tfenv-package-managers-version-pinning.md)), means every engineer's local `init` and every CI run resolve to exactly the same core and provider versions with no manual coordination required — a new engineer running `tfenv install` and `terraform init` on day one gets an environment that matches production CI exactly.

**Common errors:** Setting `required_version` too loosely (e.g., `>= 1.0`) defeats its purpose — it permits any future major version, including ones with genuinely breaking behavior changes, to run the configuration without warning.

### 5.2 Deliberate Provider Upgrades with the Lock File

**Purpose:** Show the correct, reviewable workflow for bumping a provider version rather than letting it drift implicitly.

**Syntax:**

```bash
terraform init -upgrade
terraform plan
```

**Example usage and expected output:**

```bash
$ terraform init -upgrade
Initializing provider plugins...
- Finding hashicorp/aws versions matching "~> 5.30"...
- Installing hashicorp/aws v5.34.0...
- Installed hashicorp/aws v5.34.0 (signed, key ID 34365D9472D7468F)

$ git diff .terraform.lock.hcl
-      version     = "5.31.0"
+      version     = "5.34.0"
-      hashes = [ "h1:oldhash..." ]
+      hashes = [ "h1:newhash..." ]

$ terraform plan
No changes. Your infrastructure matches the configuration.
```

**Production usage example:** A dedicated PR that only bumps `.terraform.lock.hcl` (via `-upgrade`), reviewed on its own with `plan` output attached showing no unexpected diffs, is the standard pattern — bundling a provider version bump into an unrelated feature PR makes it much harder to attribute a later problem to the version change specifically.

**Common errors:** Deleting `.terraform.lock.hcl` and regenerating it to "fix" a checksum mismatch error without first understanding why the mismatch occurred (a legitimately tampered provider binary is one possible, serious cause) — the lock file's checksums exist specifically to detect exactly this kind of unexpected discrepancy, and bypassing the check without investigation defeats its purpose.

## 6. Production Usage Notes

- **`~>` (pessimistic constraint operator) is the standard default for both providers and modules** — `~> 5.30` allows `5.30.x` and `5.31+` up to (but not including) `6.0`, giving room for patch and minor upgrades (bug fixes, new resources) while blocking major-version breaking changes from being silently pulled in.
- **The lock file should always be committed to version control**, treated the same way a language ecosystem's lockfile (`package-lock.json`, `Gemfile.lock`) is treated — it's what makes `terraform init` reproducible across machines and time, not an optional artifact.
- **Core, provider, and module upgrade cadences can reasonably differ**, but each needs a defined cadence (e.g., providers reviewed monthly or on security advisory, core reviewed quarterly, modules upgraded per-consumer on their own schedule) rather than "whenever someone happens to notice" — an undefined cadence is how sprawl ([§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md)) accumulates.
- **Module authors publishing to a private registry ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) or via Git tags should follow semantic versioning strictly** — a MAJOR bump for any breaking input/output change, MINOR for backward-compatible additions, PATCH for bug fixes — since every consumer's `~>` constraint relies on that discipline being honest.

## 7. Security Considerations

- The lock file's checksums are a real supply-chain security control, not just a reproducibility convenience — they detect a provider binary that doesn't match what was previously verified, which would flag a compromised registry mirror or a tampered download.
- Overly permissive version constraints (`>= 3.0` with no upper bound, or no constraint at all) mean a compromised or unintentionally malicious provider/module release could be pulled into production automatically on the next fresh `init`, without any deliberate review step — pessimistic constraints (`~>`) are a meaningful mitigation, not just a convenience.
- Module version pinning to immutable references (registry version numbers, or Git tags — never mutable branch refs) is a direct extension of the same principle covered in [§106](./Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md)'s polyrepo consumption pattern, and matters equally whether the module lives in the same repo or a different one.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                  | Likely Cause                                                                                                            | Resolution Path                                                                                                                        |
| ------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| `terraform init` fails with a checksum mismatch for a provider           | Lock file's recorded checksum doesn't match the downloaded provider binary                                              | Investigate before regenerating — confirm the registry/mirror hasn't been compromised, then `init -upgrade` deliberately if legitimate |
| Two engineers get different `plan` results on identical configuration    | No committed lock file, or lock file not checked into version control, letting provider versions drift between machines | Commit `.terraform.lock.hcl`; ensure `.gitignore` isn't excluding it                                                                   |
| A provider upgrade unexpectedly proposes destroying/recreating resources | Provider major version bump changed default behavior or resource schema (breaking change)                               | Review the provider's changelog/upgrade guide before merging version bumps; test in a non-production environment first                 |
| A module consumer's `init` silently picks up a breaking module change    | Module `source` pinned to a mutable branch ref instead of a version/tag                                                 | Repin to an explicit version constraint or immutable Git tag; have the module author follow semantic versioning                        |

## 9. Best Practices

- Pin `required_version` for Terraform core and `required_providers` version constraints for every provider, using the pessimistic (`~>`) operator as the default choice.
- Always commit `.terraform.lock.hcl` to version control; never `.gitignore` it.
- Upgrade deliberately via `terraform init -upgrade` in its own reviewed PR, with `plan` output attached, never as an implicit side effect of routine `init`.
- Pin module sources to immutable, explicit versions (registry version constraints or Git tags) — never a mutable branch reference — in any configuration meant to be stable.
- Define an explicit upgrade cadence per layer (core, providers, modules) rather than leaving it to ad hoc discovery when something breaks.

## 10. Common Anti-Patterns / Mistakes

- **No `required_version` or `required_providers` constraints at all**, letting any locally-installed Terraform CLI or provider version run the configuration with no compatibility guarantee whatsoever.
- **Overly loose constraints** (`>= 1.0`, `>= 3.0` with no upper bound) that technically pin something but permit any future major version, defeating the purpose of pinning in the first place.
- **Not committing the lock file**, or regenerating it casually without review, losing the reproducibility guarantee it's meant to provide.
- **Consuming modules via mutable branch references** instead of versioned, immutable sources — directly the same anti-pattern [§106](./Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md) flags for polyrepo module consumption, equally applicable within a monorepo.
- **Bundling a version bump into an unrelated feature PR**, making it hard to isolate which change caused a later regression.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `required_providers` version constraint and the `.terraform.lock.hcl` file?"_
**Model answer:** `required_providers` declares an acceptable range of provider versions (e.g., `~> 5.30`, meaning 5.30.x and later 5.x versions but not 6.0). The lock file records the exact specific version and checksum that was actually resolved and verified the last time `init` ran, and is committed to version control so every subsequent `init` reproduces that exact version rather than potentially resolving to a different one within the allowed range.
_What the interviewer is probing for:_ Whether the candidate understands these as two distinct, complementary mechanisms rather than treating them as the same thing.

**🎯 Intermediate:** _"Why is `~>` generally preferred over `>=` for provider version constraints?"_
**Model answer:** `~>` (the pessimistic constraint operator) allows patch and minor version upgrades within a major version — bug fixes and backward-compatible additions — while blocking the next major version, which by semantic versioning convention is where breaking changes live. `>=` with no upper bound permits any future version including major ones, which can silently pull in breaking changes on the next fresh `init` with no deliberate review step. `~>` gives room to receive fixes automatically while still requiring a deliberate, reviewable decision to adopt a breaking major version.
_What the interviewer is probing for:_ Practical understanding of semantic versioning conventions as applied specifically to Terraform's constraint operators.

**🎯 Senior:** _"A provider major-version upgrade (v4 to v5) is proposed. Walk me through how you'd validate it's safe before merging."_
**Model answer:** Start by reading the provider's own upgrade guide/changelog for that major version — official providers like `hashicorp/aws` publish these specifically because major bumps are expected to include breaking changes (renamed arguments, changed defaults, removed deprecated resources). Bump the constraint in an isolated branch, run `terraform init -upgrade` to regenerate the lock file, then run `terraform plan` against a non-production environment first and scrutinize every proposed change — a clean "no changes" plan is the ideal outcome, but any proposed diff needs to be understood and confirmed intentional (versus an unexpected breaking-change side effect) before proceeding. Only after validating in a lower environment would I roll the same bump through staging and then production, each with its own plan review, rather than bumping every environment's constraint simultaneously.
_What the interviewer is probing for:_ A concrete, risk-aware validation process for major version bumps specifically, not a generic "read the changelog" hand-wave.

**🎯 Architect:** _"Design a versioning policy for an organization with 60 root modules, a shared module library, and no current constraint discipline (some root modules unpinned, some pinned to old versions with drifted lock files)."_
**Model answer:** Establish three coordinated policies, one per layer. Core: standardize on tfenv (or equivalent) with a `.terraform-version` file per root module, and a `required_version` constraint using `~>` against a small number of currently-supported minor versions, upgraded organization-wide on a quarterly cadence reviewed by the platform team. Providers: mandate `~>` constraints with committed lock files across all 60 root modules as a first remediation pass — audit which modules currently lack either, fix the highest-risk (production, most-frequently-changed) ones first, and require lock-file commits as a CI check (fail the build if `.terraform.lock.hcl` is missing or `.gitignore`'d) going forward. Modules: require the shared module library to adopt strict semantic versioning with tagged releases, publish through a private registry ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) rather than raw Git URLs where possible, and require every consumer to pin an explicit version constraint — with a deprecation policy (old major versions supported for N months post-release) so consumers have a defined, bounded window to migrate rather than an open-ended "upgrade whenever." The rollout itself should be staged: enforce the CI checks for lock-file presence and constraint discipline first (cheap, high-value, catches drift going forward), then work through the backlog of already-drifted root modules incrementally, prioritized by which are production-critical and which are furthest behind — not attempted as a single simultaneous mass upgrade across all 60.
_What the interviewer is probing for:_ Ability to design a coordinated, phased policy across all three versioning layers for a realistically messy existing codebase, not just describe the ideal constraint syntax in isolation.

## 12. Common Misconceptions

1. **"Pinning a version constraint is enough for reproducibility — the lock file is redundant."** A constraint alone still permits resolution to different exact versions within its range across separate `init` runs; the lock file is what actually pins the exact resolved version and checksum.
2. **"Provider version bumps within the same major version are always safe."** Usually true by semantic versioning convention, but not guaranteed — reviewing `plan` output after any bump, minor or major, remains good practice rather than assuming safety from the version number alone.
3. **"Module versioning only matters for public registry modules."** It matters identically for internal, private-registry, or Git-sourced modules — the risk (an unpinned or mutably-referenced module silently changing underneath consumers) is the same regardless of where the module is hosted.
4. **"`terraform init -upgrade` is something you'd only run when something is broken."** It's the deliberate, correct mechanism for routine, planned version bumps — waiting until something breaks to upgrade means upgrades happen reactively and under pressure rather than on a predictable, reviewed cadence.

## 13. 🔑 Key Takeaways

- Terraform core, providers, and modules are three independently-versioned layers that need one coordinated organizational strategy, not three unrelated pinning habits.
- `required_version`/`required_providers` constraints declare an acceptable range; `.terraform.lock.hcl` pins the exact resolved version and checksum — both are needed for real reproducibility.
- The pessimistic operator (`~>`) is the standard default: it allows safe patch/minor upgrades while requiring a deliberate decision to adopt a breaking major version.
- Module sources should always be pinned to immutable, versioned references — never mutable branch refs — whether sourced from a public registry, private registry, or Git.
- Version bumps belong in their own reviewed PR with `plan` output attached, on a defined cadence, not as an implicit side effect of routine work.

## 14. Related Concepts & What's Next

[§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md) introduced provider version constraint syntax in depth; this section extended it into a full organizational strategy. [§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md) named provider sprawl as an anti-pattern this section directly prevents. [§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md) and [§58](../Part8/Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md) cover module versioning and sourcing mechanics referenced here. [§111](./Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md) closes Part 15 with the boundary between Terraform and the tools that take over once infrastructure is provisioned.

**Next Section:** [§111](./Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md) — `Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md`
