# Section 62 (Part 8): Module Design Best Practices and Anti-Patterns

## 1. Definition

**Plain language:** This section pulls together everything Part 8 has covered — structure, inputs/outputs, sourcing, versioning, composition — into a single set of design judgments: what makes a module genuinely good to work with, and what recurring mistakes make modules a liability instead of an asset.

**Precise definition:** **Module design quality** is the degree to which a module's interface (inputs/outputs, [§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)), structure ([§56](./Section-56-Part8-Module-Structure-and-Conventions.md)), versioning discipline ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)), and scope (what it does and doesn't try to do) minimize the total cost of using, maintaining, and evolving it across all its consumers over time — not just whether it works correctly for its first use case. Well-designed modules follow the **single-responsibility principle** (a module represents one cohesive, well-bounded piece of infrastructure, not an arbitrary grab-bag), keep their **interface surface minimal and stable** (few required inputs, curated outputs, per [§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)), and are **provider-agnostic where the pattern allows it** (no hardcoded provider blocks, per [§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)). Common **anti-patterns** include the "god module" (one module trying to provision an entire application's infrastructure with dozens of conditional flags), premature abstraction (extracting a module after a single use case, before a second consumer reveals what's actually variable versus incidental), and interface instability (frequent breaking changes to widely-consumed modules without version discipline, per [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)).

> 💡 **Tip:** The strongest signal that a module's design is right is usually "the second consumer was easy." A module designed around one team's exact needs often has variable and fixed pieces tangled together in a way that isn't obvious until a genuinely different second consumer tries to use it — if adding that second consumer requires forking the module or bolting on a pile of special-case conditionals, the original abstraction boundary was probably wrong, not just incomplete.

## 2. Why This Matters

- **Module design mistakes compound across every consumer.** A single resource block written badly costs one team some debugging time; a badly designed module used by 30 teams multiplies that cost 30 times over, and worse, tends to get copy-paste-forked by frustrated consumers rather than fixed at the source — fragmenting the very reuse benefit modules exist to provide ([§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)).
- **This section is where Part 8's individual mechanics (structure, I/O, sourcing, versioning, composition) become judgment calls**, not just syntax — knowing how `~>` version constraints work ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) doesn't by itself tell you when a breaking change is actually justified versus avoidable.
- **Anti-patterns here are exactly the kind of thing that looks fine in a single-team, single-use-case review** and only reveals its cost months later at the second or third consumer — which is why deliberate design discipline up front is cheaper than remediation later.
- **This closes Part 8** and sets up Part 9's provisioners material, where a related design discipline applies: just as modules should have minimal, stable interfaces, provisioners ([§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)) should be a last resort rather than a first reach, for related "don't let convenience create long-term liabilities" reasons.

## 3. Prerequisites and Dependencies

This section is a synthesis of every prior Part 8 section: [§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)'s root/child distinction and state addressing, [§56](./Section-56-Part8-Module-Structure-and-Conventions.md)'s structural conventions, [§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)'s input/output design, [§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)'s sourcing options, [§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)'s registry publishing model, [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)'s version constraint discipline, and [§61](./Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md)'s composition patterns. No new mechanics are introduced here — this is where those mechanics become design principles.

## 4. Architecture / Conceptual Diagram

```text
GOOD MODULE DESIGN                                ANTI-PATTERN: "GOD MODULE"
┌──────────────────────────────────────┐          ┌──────────────────────────────────────────────────────────┐
│ modules/database/                    │          │ modules/entire-app/                                      │
│                                      │          │                                                          │
│ Single responsibility:               │          │ Tries to provision: network,                             │
│ "an RDS instance and its             │          │ compute, database, IAM, DNS,                             │
│ security group"                      │          │ monitoring, CI/CD triggers...                            │
│                                      │          │                                                          │
│ variable "instance_class" {}         │          │ variable "enable_multi_az" {}                            │
│ variable "allocated_storage" {}      │          │ variable "enable_public_compute" {}                      │
│   default = false                    │          │ variable "use_legacy_iam_pattern" {}                     │
│ }                                    │          │ ...47 more conditional flags...                          │
│                                      │          │                                                          │
│ output "endpoint" {}                 │          │ resource blocks with count = var.x ? (var.y ? 1 : 0) : 0 │
│ output "sg_id" {}                    │          │  scattered throughout — nobody can predict what          │
│                                      │          │  a given flag combination actually creates               │
│ -> Easy 2nd/3rd consumer: pass       │          │                                                          │
│    different instance_class/storage, │          │ -> Every new team's edge case adds another flag,         │
│    reuse everything else unchanged   │          │    interface grows unboundedly, nobody can safely        │
└──────────────────────────────────────┘          │    predict the blast radius of a change                  │
                                                  └──────────────────────────────────────────────────────────┘

VERSIONING DISCIPLINE                     ANTI-PATTERN: INTERFACE INSTABILITY
  v1.0.0 -> v1.1.0 -> v1.2.0                v1.0.0 -> v1.0.1 (removes a variable!)
  (additive, backward compatible,            -> v1.0.2 (renames an output!)
   defaults preserve old behavior)            Consumers' "~>" constraints (§60) assumed
  v1.2.0 -> v2.0.0                            these were safe patch bumps -> broken applies
  (explicit major bump for the
   one genuinely breaking change)
```

- The "god module" pattern typically starts reasonably (one team's real use case) and grows one conditional flag at a time as each new consumer's edge case gets bolted on rather than triggering a redesign — no single addition looks unreasonable in isolation, which is exactly why it's hard to stop once it starts.
- Interface instability (removing/renaming variables or outputs without a major version bump) breaks the entire premise of [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)'s version constraint discipline — consumers relying on `~>` for "safe" automatic updates get burned exactly when they trusted the mechanism most.

## 5. Hands-On

### 5.1 Refactoring a "God Module" Toward Single Responsibility

**Purpose:** Show the practical difference between an over-scoped module and its decomposed equivalent.

**Syntax:**

```hcl
# ANTI-PATTERN: one module doing everything, gated by flags
module "entire_app" {
  source = "./modules/entire-app"

  enable_database        = true
  enable_public_compute   = false
  use_legacy_iam_pattern    = true
  skip_dns_if_external        = false
  # ...dozens more flags, each changing internal behavior unpredictably
}
```

```hcl
# BETTER: composed from focused, single-responsibility modules (§61)
module "network" {
  source = "./modules/network"
  cidr_block = "10.0.0.0/16"
}

module "database" {
  source     = "./modules/database"
  vpc_id     = module.network.vpc_id
  subnet_ids = module.network.private_subnet_ids
}

module "compute" {
  source     = "./modules/compute"
  vpc_id     = module.network.vpc_id
  subnet_ids = module.network.public_subnet_ids
  public     = false
}
```

**Example usage and expected output:**

```bash
$ terraform plan
# With the decomposed version, a reviewer can predict exactly what
# "module.database" and "module.compute" each create by reading their
# focused interfaces — no need to trace 47 interacting boolean flags
# through one module's internals to understand the resulting plan.
```

**Production usage example:** This decomposition is the standard remediation path when a "god module" is identified in review — rather than a risky big-bang rewrite, teams typically extract the most tangled responsibility first (often the database or IAM portion) into its own focused module, wire it back in via composition, and repeat.

**Common errors:** Attempting to decompose a god module all at once, in a single large refactor, risks a difficult-to-review diff and a higher chance of an unintended `state mv` ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) mistake — incremental extraction, one responsibility at a time, each verified with `terraform plan` showing no unintended resource replacement, is the safer path.

### 5.2 Version-Disciplined Interface Evolution

**Purpose:** Show how to add a genuinely necessary breaking change without ambushing consumers relying on `~>` constraints.

**Syntax:**

```hcl
# v1.x: original interface
variable "storage_type" {
  type    = string
  default = "gp2"
}
```

```hcl
# v2.0.0: storage_type removed, replaced by storage_config object
# (a genuine breaking change — bump the MAJOR version, per §60)
variable "storage_config" {
  type = object({
    type = string
    iops = optional(number)
  })
  default = {
    type = "gp3"
  }
}
```

**Example usage and expected output:**

```text
CHANGELOG.md excerpt:
## v2.0.0 (BREAKING)
- Removed `storage_type` variable; replaced with `storage_config` object
  to support IOPS configuration. Migration: replace
  `storage_type = "gp2"` with `storage_config = { type = "gp2" }`.

## v1.3.0
- Added optional `backup_retention_days` variable (default preserves
  prior hardcoded 7-day behavior) — non-breaking, safe under existing
  "~> 1.0" consumer constraints.
```

**Production usage example:** A clear changelog documenting exactly which version introduced which breaking change, paired with strict semver discipline, is what makes it safe for 30+ consumers to run `terraform init -upgrade` routinely without fear — they trust that a `~>` constraint genuinely won't cross into breaking territory unannounced.

**Common errors:** Releasing a breaking interface change (removed variable, renamed output) under a minor or patch version bump is the single most damaging module-maintenance mistake — it silently breaks every consumer whose `~>` constraint ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) was relying on that version range being safe, often discovered only when their next routine `-upgrade` fails or, worse, applies successfully with wrong behavior.

## 6. Production Usage Notes

- **Extract a module after the second real consumer, not before.** A module designed from a single use case tends to bake that use case's incidental details into the interface as if they were fundamental — waiting for a genuine second consumer (even a slightly different one) reveals what's actually variable and what was coincidental, producing a better-designed interface than speculative up-front abstraction.
- **A module's `CHANGELOG.md` (paired with disciplined semver tagging, [§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)/[§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) is as important as its README** for any module with more than one or two consumers — consumers need to be able to answer "is it safe to upgrade" without reading a full diff of the module's source.
- **Periodically audit widely-used modules for accumulated conditional-flag sprawl** — a module that had 3 boolean flags at v1.0.0 and has 25 by v1.8.0 is very likely drifting toward the "god module" anti-pattern one reasonable-seeming addition at a time, and is worth a deliberate decomposition review before it gets worse.

## 7. Security Considerations

- God modules with dozens of interacting conditional flags are genuinely harder to security-review — predicting exactly what a given combination of flags will provision (and whether that combination could produce an insecure configuration, like accidentally public compute with `enable_public_compute = true` combined with an unrelated flag) is much harder than reviewing a focused, single-responsibility module's plan output.
- Breaking interface changes released without a major version bump ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) can silently change security-relevant defaults (e.g., a renamed variable's replacement defaulting to a less restrictive setting) for consumers who trusted their `~>` constraint to only pull in safe changes — version discipline is a security control, not just a stability one, as also noted in [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md).
- When decomposing a god module, review each extracted module's new, narrower interface for whether it now over-exposes something that should have stayed an internal default ([§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)'s guidance on curated outputs applies directly during this kind of refactor).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                     | Likely Cause                                                                                          | Resolution Path                                                                                                                                                                  |
| --------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A module's interface has grown to dozens of conditional variables over time | Each new consumer's edge case was accommodated with another flag rather than triggering a redesign    | Audit for genuinely independent responsibilities inside the module; decompose into focused modules ([§61](./Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md)) |
| Consumers report broken applies after a routine `terraform init -upgrade`   | A breaking change was released under a minor/patch version instead of a major bump (semver violation) | Fix forward with a correctly major-bumped release; document the mistake in the changelog; tighten CI checks on tagging                                                           |
| New consumers keep forking a shared module instead of extending it          | The module's interface is too rigid, too narrowly scoped to its first use case, or poorly documented  | Gather the actual variation across forks; redesign the shared module's interface to accommodate it properly                                                                      |
| Reviewers can't predict what a module's plan will actually create           | Deeply tangled conditional logic (god module) makes the resulting configuration hard to reason about  | Decompose into single-responsibility modules with clearer, more predictable per-module behavior                                                                                  |

## 9. Best Practices

- Design every module around a single, cohesive responsibility — if describing what a module does requires "and," it's very likely a candidate for decomposition ([§61](./Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md)).
- Wait for a genuine second consumer before extracting a new shared module; resist speculative up-front abstraction based on only one use case.
- Treat any variable removal, rename, or output removal as a breaking change requiring a major version bump and clear changelog documentation — never rely on consumers reading a source diff to discover this.

## 10. Common Anti-Patterns / Mistakes

- **The "god module."** One module accumulating dozens of interacting conditional flags to serve every consumer's edge case, until its actual behavior for any given input combination becomes unpredictable without reading deep into its internals.
- **Premature abstraction.** Extracting a module after exactly one use case, baking that single consumer's incidental details into the "reusable" interface, then discovering at the second consumer that the abstraction boundary was wrong and needs a disruptive redesign.
- **Silent breaking changes.** Removing, renaming, or changing the meaning of a variable or output without a major version bump — this is the single most consumer-damaging mistake a module maintainer can make, because it violates the trust that `~>` version constraints ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) are built on.
- **Copy-paste module forking as the default response to a rigid interface.** When a module doesn't accommodate a new consumer's legitimate need, forking (rather than extending the shared module properly) fragments the reuse benefit and multiplies future maintenance burden.

## 11. Interview Questions

**🎯 Beginner:** _"What does it mean for a module to follow the 'single-responsibility principle'?"_
**Model answer:** It means a module represents one cohesive, well-bounded piece of infrastructure — like "an RDS instance and its security group," or "a VPC with subnets" — rather than trying to provision many unrelated things gated behind a large number of conditional flags. A module you can describe in one clear sentence without "and" is usually well-scoped; one that needs several "and"s in its description is a decomposition candidate.
_What the interviewer is probing for:_ Basic grasp of module scoping as a design principle, not just a syntax rule.

**🎯 Intermediate:** _"Why is 'extract a module after the second consumer, not before' generally better advice than abstracting early?"_
**Model answer:** A module designed from a single use case tends to encode that one consumer's incidental, coincidental details as if they were fundamental to the abstraction, because there's no second data point to reveal what's actually variable versus what just happened to be true for the first case. Waiting for a genuine second consumer — even a somewhat different one — surfaces the real variation the module's interface needs to accommodate, producing a more accurate, more stable interface than a guess made from one example.
_What the interviewer is probing for:_ Understanding of premature abstraction as a real, common failure mode, not just book-learned advice repeated without grasping why it's true.

**🎯 Senior:** _"You inherit a module with 30+ boolean/conditional variables that's used by 15 teams, each of which only exercises a handful of the flags relevant to their case. How would you approach decomposing it without breaking anyone?"_
**Model answer:** First, audit actual usage across all 15 consumers — which flag combinations are genuinely exercised versus theoretical — since the real decomposition boundaries should follow actual usage patterns, not the flag list as designed. Then identify the most tangled, independently meaningful responsibility (often something like the database or IAM portion) and extract it first as its own focused module, keeping the original module's interface unchanged and internally delegating to the new extracted module — this is a non-breaking internal refactor from every consumer's perspective. Only once the extraction is proven stable would I introduce a new major version of the original module that actually removes the now-redundant flags and expects consumers to call the extracted modules directly, giving each of the 15 teams an explicit, reviewed migration window rather than forcing simultaneous adoption. This staged approach (internal extraction first, interface change second, always under proper version discipline per [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) avoids the risk of a single big-bang rewrite breaking 15 teams' infrastructure at once.
_What the interviewer is probing for:_ A concrete, low-risk staged migration strategy for a real god-module remediation, showing awareness of both the design problem and the operational risk of fixing it carelessly.

**🎯 Architect:** _"How do you build organizational incentives and processes so that module design quality doesn't degrade over time as more teams contribute flags and features to shared modules, rather than relying on any single reviewer catching every problematic addition?"_
**Model answer:** Relying on reviewer vigilance alone doesn't scale — the fix is structural. First, assign clear ownership: every widely-shared module should have a named owning team responsible for interface decisions, not an open free-for-all where any consumer can add a flag via PR approval from whoever happens to review it. Second, set an explicit review bar for new module inputs specifically (not just general code review) — a new required variable or a new conditional flag should require justifying why it can't be achieved via composition (a new sibling module, [§61](./Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md)) instead of growing the existing module's surface, since "just add a flag" is almost always the path of least resistance in the moment and the path of most accumulated debt over a year. Third, track module interface size and churn as a lightweight metric over time (variable count, output count, version history) — not to hit an arbitrary number, but as a signal that triggers a deliberate design review when a module's interface starts growing unusually fast relative to its actual scope. Fourth, make decomposition a normal, expected maintenance activity with allocated time, not something that only happens reactively after a module has become unmanageable — treating module health as ongoing platform-team work, not a one-time design exercise, is what actually prevents degradation at scale.
_What the interviewer is probing for:_ Systems-level thinking about sustaining design quality across an organization over time, not just knowing what good design looks like for one module at one point in time.

## 12. Common Misconceptions

1. **"More configuration flexibility (more optional variables) always makes a module better."** Every additional variable is permanent interface surface area and cognitive load for every consumer — flexibility has a real, ongoing cost, not just an upside.
2. **"Extracting a module as early as possible is always good practice, since reuse is the whole point of modules."** Premature abstraction from a single use case often produces a worse interface than waiting for genuine variation to reveal itself at a second consumer.
3. **"A patch or minor version bump is always safe to release without careful review, since only major versions can be 'breaking' by definition."** Semver conventions are only meaningful if the maintainer actually enforces them correctly — an accidental breaking change released under a minor/patch version is exactly the failure mode that damages consumer trust in version constraints ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)).
4. **"Forking a rigid module to accommodate a new need is a reasonable, low-cost workaround."** It fragments the shared reuse benefit and creates ongoing duplicate-maintenance burden — extending the shared module's interface properly (or composing around it, [§61](./Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md)) is almost always the better long-term choice, even though forking feels faster in the moment.

## 13. 🔑 Key Takeaways

- Good module design follows single-responsibility scoping, a minimal and curated interface ([§57](./Section-57-Part8-Module-Inputs-and-Outputs.md)), and provider-agnostic construction ([§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)) — these compound in value across every consumer.
- Extract shared modules after a genuine second consumer reveals real variation, not preemptively from a single use case.
- Any removal or rename of a variable or output is a breaking change requiring a major version bump ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) and clear changelog documentation — never assume consumers will notice from a source diff.
- The "god module" anti-pattern (one module with dozens of interacting conditional flags) typically accumulates gradually, one reasonable-seeming addition at a time, and is best prevented by treating composition ([§61](./Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md)) as the default answer to new requirements rather than adding another flag.
- Sustaining module design quality at organizational scale requires structural incentives (ownership, review bars for new interface surface, periodic health audits) rather than relying on any single reviewer's vigilance.

## 14. Related Concepts & What's Next

This closes Part 8's coverage of modules — the reuse and packaging layer built on top of Part 5's resources, Part 6's variables/outputs, and Part 7's state. Part 9 shifts to provisioners: [§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md) opens with why HashiCorp actively discourages provisioners as a first-choice tool, a design-discipline theme directly related to this section's emphasis on choosing the right abstraction rather than the most convenient one.

**Next Section:** [§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md) — `Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md`
