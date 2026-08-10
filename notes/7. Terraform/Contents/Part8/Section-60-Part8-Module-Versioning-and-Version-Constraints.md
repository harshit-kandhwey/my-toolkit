# Section 60 (Part 8): Module Versioning and Version Constraints

## 1. Definition

**Plain language:** Once a module is published with real version numbers (via the registry's tag-based publishing, [§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)), a consumer needs a way to say "give me a compatible version, but don't silently jump to a version with breaking changes." Version constraints are that mechanism — the same idea as a `package.json` or `requirements.txt` version range, applied to a `module` block's `version` argument.

**Precise definition:** A **version constraint** is an expression in a `module` block's `version` argument that restricts which published semantic-version tags Terraform is allowed to select during resolution. Terraform supports the standard set of constraint operators: **exact pin** (`version = "5.8.1"`, only that precise version); **minimum bound** (`>= 5.0.0`); **maximum bound** (`<= 6.0.0`); **range** (combining bounds, `>= 5.0.0, < 6.0.0`); and the **pessimistic operator** `~>` ("approximately greater than"), which allows the rightmost version segment to increment but not any segment to its left — `~> 5.8` allows `5.9`, `5.999` but not `6.0`; `~> 5.8.1` allows `5.8.2`, `5.8.99` but not `5.9.0`. Critically, **version constraints only apply to sources that publish discrete, resolvable versions** — Terraform Registry sources (public or private) are the primary case. Local path sources ([§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)) have no `version` argument at all (there is nothing to resolve; it's whatever is on disk). Git sources support pinning via `?ref=`, but `ref=` is a single fixed revision selector, not a constraint range Terraform resolves against a list of candidates — a Git source cannot express "give me the latest 5.x" the way `~> 5.0` can against a registry.

> 💡 **Tip:** `~>` is the operator you want almost all the time in production. `>= 5.0.0` alone lets Terraform jump to any future major version with no ceiling, including ones with breaking changes; an exact pin (`version = "5.8.1"`) never updates at all, even for security patches, without a manual edit. `~> 5.8` is the middle ground: automatic patch/minor updates within a version line that (if the module author follows semver correctly, per [§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)) shouldn't break your configuration, while still requiring a deliberate constraint edit to cross a major version boundary.

## 2. Why This Matters

- **Version constraints are the direct payoff of the registry's tag-based semver publishing model ([§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md))** — without a strict, machine-parseable versioning scheme on the publisher side, none of these operators would have anything reliable to resolve against.
- **They're the primary defense against the "it worked yesterday" class of incident** where a fresh `terraform init` (perhaps on a new CI runner, or after a teammate's `-upgrade`) resolves to a different, unreviewed module version than what was tested.
- **Choosing the right constraint tightness is a real trade-off**, not a default to memorize: too loose (`>= 5.0.0`) risks unreviewed breaking changes; too tight (exact pin everywhere) means security patches and bug fixes require manual constraint bumps across every consumer, which doesn't scale across dozens of modules and callers.
- **Understanding which source types do and don't support constraints** (registry: yes; local: no concept; Git: `ref=` pinning only, no range resolution) prevents a common mistake of trying to add a `version` argument to a local or Git-sourced module block, which Terraform will reject.
- This directly extends [§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)'s provider version constraint mechanics (same operators, same philosophy) to modules — recognizing the two systems share a syntax makes both easier to reason about together.

## 3. Prerequisites and Dependencies

This section depends on [§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)'s explanation of how registry modules get their semantic version tags in the first place — the constraint operators covered here are meaningless without that publishing model as context. It also assumes [§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)'s source-type distinctions (local/registry/Git), since which source types support `version` at all is central to this section. [§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)'s provider version constraints use an identical operator syntax and are worth reviewing side-by-side if unfamiliar.

## 4. Architecture / Conceptual Diagram

```text
Published versions available on the registry for a module (via git tags, §59):
  4.9.0   5.0.0   5.1.0   5.2.0   5.8.0   5.8.1   5.9.0   6.0.0   6.1.0

version = "5.8.1"            -> resolves ONLY to 5.8.1 (exact pin)
                                 [═] 5.8.1

version = ">= 5.0.0"         -> resolves to the HIGHEST available: 6.1.0
                                 [══════════════════════════════════►]
                                 (no ceiling — crosses major version!)

version = ">= 5.0.0, < 6.0.0" -> resolves to highest in range: 5.9.0
                                 [══════════════════════►]
                                 5.0.0                5.9.0   |6.0.0 excluded

version = "~> 5.8"            -> resolves to highest 5.x >= 5.8: 5.9.0
                                          [═══════►]
                                          5.8.0  5.8.1  5.9.0   |6.0.0 excluded
                                 (rightmost segment "8" free to climb,
                                  leftmost segment "5" locked)

version = "~> 5.8.1"          -> resolves to highest 5.8.x >= 5.8.1: 5.8.1
                                          [═]
                                          5.8.1 only available match
                                          (5.9.0 excluded — patch-level lock)

SOURCE TYPE SUPPORT:
  Registry source  -> version = "..."     FULL constraint operator support
  Local path source -> (no version arg)    N/A — always whatever's on disk
  Git source        -> ?ref=<tag|sha>      single fixed pin only, no range resolution
```

- The pessimistic `~>` operator's "locked" segment count depends on how many segments you write: `~> 5.8` locks the major (`5`) and lets minor/patch float; `~> 5.8.1` locks major.minor (`5.8`) and lets only patch float.
- A range like `>= 5.0.0, < 6.0.0` is written as a comma-separated list inside one `version` string — Terraform treats multiple comma-separated constraints as an AND (all must be satisfied).

## 5. Hands-On

### 5.1 Pessimistic Constraint on a Registry Module (Recommended Default)

**Purpose:** Show the standard production pattern for module version pinning.

**Syntax:**

```hcl
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.8"

  name = "app-vpc"
  cidr = "10.0.0.0/16"
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing modules...
Downloading registry.terraform.io/terraform-aws-modules/vpc/aws 5.9.2 for vpc...
- vpc in .terraform/modules/vpc

# A later 6.0.0 release is published upstream:
$ terraform init -upgrade
Initializing modules...
Downloading registry.terraform.io/terraform-aws-modules/vpc/aws 5.9.2 for vpc...
# still 5.9.x — 6.0.0 is correctly excluded by "~> 5.8"
```

**Production usage example:** This is the default recommended constraint style for most production module consumption — it allows the module to absorb bug fixes and backward-compatible feature additions automatically on `-upgrade` while requiring an explicit, reviewed constraint change to adopt a new major version.

**Common errors:** Assuming `~> 5.8` behaves like `~> 5.8.0` — they are subtly different: `~> 5.8` allows any `5.x >= 5.8` (including `5.9`, `5.10`), while `~> 5.8.0` (three segments) would lock to `5.8.x` only, excluding `5.9.0`. Segment count changes what's locked.

### 5.2 Attempting (Incorrectly) to Version-Pin a Local or Git Source

**Purpose:** Show the errors that result from misapplying `version` outside a registry source.

**Syntax:**

```hcl
module "network" {
  source  = "./modules/network"
  version = "1.0.0"   # INVALID — local sources don't support version
}
```

**Example usage and expected output:**

```bash
$ terraform init
Error: Reserved argument name in module block

  on main.tf line 2, in module "network":
   2:   version = "1.0.0"

The name "version" is reserved for use in a future version of Terraform.
# (local sources: version has no meaning; some Terraform versions reject
#  it outright or silently ignore it depending on source type detection)
```

**Production usage example:** For a Git-sourced module, the correct equivalent of "pinning a version" is baking the desired tag into the `source` string itself via `?ref=v1.2.0` ([§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)) — there is no separate `version` argument to combine with a Git source's `source` string.

**Common errors:** Trying to combine a Git `source` with a separate `version` argument, expecting Terraform to resolve a range against Git tags the way it does for registry sources — Git sources don't support range resolution; `ref=` in the source string is the only pinning mechanism available.

## 6. Production Usage Notes

- **`terraform init -upgrade` is the only way a version constraint is re-evaluated.** As with source resolution generally ([§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)), simply editing `version` in configuration does not retroactively re-resolve until `init` (typically `-upgrade`) runs.
- **Version constraints compound across a dependency tree.** If module A depends on module B with `version = "~> 2.0"`, and your root module also directly depends on module B with `version = "~> 3.0"`, Terraform must find a version satisfying both — an unsatisfiable combination produces a clear resolution error at `init` time rather than a silently wrong version.
- **CI pipelines should generally run plain `terraform init` (no `-upgrade`) by default**, relying on whatever was already resolved and (ideally) recorded via a committed `.terraform.lock.hcl`-adjacent process or pinned exact versions for infrastructure code — `-upgrade` is a deliberate, reviewed action taken when the team decides to adopt newer module versions, not something that should happen implicitly on every pipeline run.

## 7. Security Considerations

- An unconstrained or overly loose module version (`>= 1.0.0` with no ceiling) means a compromised or maliciously altered upstream module release could be pulled in automatically on the next `-upgrade` with no review — tight, deliberate constraints are a real supply-chain security control, not just a stability one.
- When a module needs to be upgraded to pick up a security-relevant fix, review the actual diff/changelog between the currently pinned version and the target version before widening a constraint or bumping an exact pin — semantic versioning is a convention the module author is expected to follow correctly, not a guarantee enforced by tooling.
- For highly sensitive infrastructure (IAM, network security boundaries), exact version pins combined with a deliberate, reviewed upgrade process are often preferred over `~>` ranges specifically to ensure every version change — even a "safe" patch release — goes through explicit review before being adopted.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                  | Likely Cause                                                                                                                    | Resolution Path                                                                                                                                                          |
| ---------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `Error: Failed to query available provider/module versions` or similar resolution error  | No published version satisfies the combined constraint (e.g., conflicting constraints from multiple callers of the same module) | Loosen or align the conflicting constraints; check what versions are actually published on the registry                                                                  |
| `terraform init` resolves to an unexpectedly old version                                 | Constraint is more restrictive than intended (e.g., `~> 5.8.1` when `~> 5.8` was intended)                                      | Recount version segments carefully — the number of segments in the constraint determines the lock point                                                                  |
| Adding `version` to a local or Git-sourced `module` block errors out                     | `version` is only valid for registry sources; local/Git sources don't support it                                                | Remove `version` for local sources; use `?ref=` in the `source` string for Git sources instead ([§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)) |
| A module upgrade broke consumers despite a `~>` constraint that should have prevented it | The module author released a breaking change under a minor/patch version, violating semver expectations                         | Report/track the semver violation upstream; pin more tightly (exact version) for that module going forward                                                               |

## 9. Best Practices

- Default to `~>` pessimistic constraints for registry-sourced modules in production — they balance automatic safe updates against protection from unreviewed breaking changes.
- Reserve exact version pins for the highest-sensitivity modules (IAM, network boundaries) where even minor/patch updates should go through explicit review before adoption.
- Never leave a production module consumption entirely unconstrained (`version` omitted, or an open-ended `>=` with no ceiling) — always give Terraform an explicit ceiling, even a generous one.

## 10. Common Anti-Patterns / Mistakes

- **Treating `>= X.0.0` as "safe" because it has a lower bound.** A lower bound alone provides zero protection against jumping to a future breaking major version — it is functionally almost as loose as no constraint at all.
- **Assuming Git-sourced modules can be pinned with a `version` argument the same way registry modules can.** They cannot — the mental model of "just add a version constraint" doesn't transfer; Git sources need `ref=` in the source string itself.
- **Never running `-upgrade`, ever, out of caution — even for security patches.** Over-cautious teams sometimes pin so tightly and upgrade so rarely that modules drift years out of date, accumulating both security exposure and a much larger, riskier jump when an upgrade finally becomes unavoidable.

## 11. Interview Questions

**🎯 Beginner:** _"What does `version = "~> 5.8"` mean for a registry module source?"_
**Model answer:** It means Terraform will resolve to the highest available published version that is `5.8` or greater, but strictly less than `6.0` — the pessimistic operator locks the leftmost specified version segment (here, the major version `5`) while allowing everything to its right (minor and patch) to float upward automatically.
_What the interviewer is probing for:_ Correct mechanical understanding of the `~>` operator, specifically how segment count determines what's locked.

**🎯 Intermediate:** _"Why doesn't a Git-sourced module support the same `~>` version constraints as a registry-sourced module?"_
**Model answer:** Version constraints require Terraform to resolve a range against a known list of discrete published versions — that list only exists because the registry indexes semantic-version tags for a module ([§59](./Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)). A Git source has no such registry-side version list for Terraform to query; `?ref=` in the source string selects one single fixed revision (a tag, branch, or commit) directly, with no range-resolution step. There's no equivalent of "give me the latest 5.x" against arbitrary Git tags the way there is against a registry's indexed version list.
_What the interviewer is probing for:_ Understanding that version constraint resolution is a registry-specific capability tied to how modules get published there, not a generic Terraform feature independent of source type.

**🎯 Senior:** _"Two different child modules in your configuration each declare a `module` block sourcing the same shared module, but with different version constraints — one `~> 2.0`, one `~> 3.0`. What happens, and how would you resolve it?"_
**Model answer:** This scenario as described is actually about two separate `module` blocks (even if they reference the same underlying source), which Terraform treats as fully independent instances — each resolves its own constraint independently and can genuinely run different versions simultaneously, since each `module` block gets its own state address ([§55](./Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)) with no cross-block version-sharing requirement. Real version-conflict resolution errors occur specifically in the nested-module case, where a parent module's own internal `module` block constraint must be jointly satisfiable with any constraint the root applies to that same nested module call — in that case, an "unable to resolve version" error at `init` surfaces the conflict, and the fix is aligning both constraints (typically widening the tighter one, or explicitly deciding which caller's constraint should win) after understanding why each caller pinned what it did in the first place, rather than blindly loosening for convenience.
_What the interviewer is probing for:_ Precision about what's actually a "conflict" in Terraform's module model (independent module blocks vs. a genuinely shared nested dependency) — a common area where candidates over-generalize.

**🎯 Architect:** _"You're setting module version-pinning policy for an organization with ~50 root modules consuming a mix of public registry modules and ~15 internal modules on a private registry. What policy would you set, and how would you enforce it rather than relying on individual engineer discipline?"_
**Model answer:** Policy: every registry-sourced module must have an explicit `~>` constraint (never unconstrained, never a bare lower-bound-only `>=`); internal modules touching high-sensitivity domains (IAM, network security boundaries) get exact pins with a deliberate, reviewed bump process; public modules get `~>` at the minor-version level as the default, tightened to patch-level for anything with a history of semver violations. Enforcement: a static check in CI (`tflint` or a custom policy check, tying into [§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)'s linting and [§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)'s policy-as-code testing) that fails any `module` block missing a `version` constraint or using an unbounded `>=`, rather than relying on code review catching it manually across 50 root modules maintained by different teams. I'd also periodically run a scheduled (not ad hoc) `-upgrade` + `plan` dry-run across all root modules — surfacing what a real upgrade would change on a predictable cadence, so version drift is discovered proactively rather than only when someone happens to touch that configuration again.
_What the interviewer is probing for:_ Organization-scale policy design that relies on automated enforcement rather than convention alone, plus a proactive (not purely reactive) approach to staying current.

## 12. Common Misconceptions

1. **"`>= 5.0.0` is a reasonably safe constraint because it has a version floor."** It has no ceiling, so it can resolve to any future major version with breaking changes — a floor alone provides essentially no protection.
2. **"You can pin a Git-sourced module's version the same way as a registry module, just with a `version` argument."** You cannot — Git sources use `?ref=` embedded in the `source` string; the `version` argument is registry-source-specific.
3. **"`~> 5.8` and `~> 5.8.0` mean the same thing."** They don't — segment count determines the lock point: `~> 5.8` allows any `5.x`; `~> 5.8.0` (with the implicit third segment) locks to `5.8.x` patch releases only.
4. **"Local module sources can be version-pinned too, you just have to add a `version` argument."** Local sources have no version concept at all — there's nothing to resolve since the code is already on disk exactly as it currently exists.

## 13. 🔑 Key Takeaways

- Version constraints (`~>`, `>=`, `<=`, exact pin, ranges) apply meaningfully only to sources that publish discrete resolvable versions — in practice, Terraform Registry sources (public or private).
- The pessimistic `~>` operator is the standard production default: it locks everything to the left of the rightmost specified segment while allowing that segment (and anything further right) to float upward.
- Local path sources have no versioning concept; Git sources pin via a single `?ref=` value in the `source` string, not via a separate `version` argument or range resolution.
- Constraints only re-resolve at `terraform init` (typically `init -upgrade`) — editing a constraint alone does not change what's already cached.
- Unconstrained or lower-bound-only constraints provide essentially no protection against unreviewed breaking or malicious changes landing automatically — a real supply-chain security consideration, not just a stability one.

## 14. Related Concepts & What's Next

[§61](./Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md) moves from single-module versioning into composition patterns — how multiple versioned modules, each independently constrained, combine into larger configurations, including nested modules where a parent module's own internal version constraints interact with the root's. [§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md) covers the identical constraint operator syntax as applied to provider versions rather than modules, worth comparing directly. [§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) covers policy-as-code checks that can enforce version-constraint discipline automatically in CI.

**Next Section:** [§61](./Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md) — `Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md`
