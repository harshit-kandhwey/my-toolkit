# Section 87 (Part 12): Private Module Registry and Private Provider Registry

## 1. Definition

**Plain language:** A private registry is an organization's own internal version of the public Terraform Registry ([§10](../Part2/Section-10-Part2-The-Terraform-Registry-and-Sourcing-Providers.md), [§59](../Part8/Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md)) — a place to publish internally built modules and providers so teams can `source = "app.terraform.io/acme-corp/vpc/aws"` them the same way they'd reference a public module, but with access restricted to the organization and versions controlled entirely internally.

**Precise definition:** Terraform Cloud and Enterprise provide a **private module registry** and a **private provider registry**, both hosted at the organization level and addressed through the same registry protocol the public Terraform Registry uses. Modules are published by tagging a VCS repository (`vX.Y.Z` semantic version tags trigger automatic ingestion) or pushed directly via API; the registry then serves versioned module source, documentation (auto-generated from the module's `README.md` and variable/output definitions), and a searchable UI, exactly mirroring the consumption experience of `registry.terraform.io`. The private provider registry serves the same role for custom-built providers, distributing signed provider binaries so `terraform init` can resolve `source = "app.terraform.io/acme-corp/internal-provider"` without needing a public registry publish.

> 💡 **Tip:** Consuming a private-registry module looks identical to consuming a public one — same `source` argument shape, same version-constraint syntax ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) — only the registry hostname prefix changes (`app.terraform.io/<org>/...` instead of the implicit `registry.terraform.io/...`). This is deliberate: it means a module can be developed and tested locally, published to the private registry, and consumed identically to any public module, with no special-casing in calling code beyond the source string.

## 2. Why This Matters

- **Internal reuse gets the same discoverability as public modules.** Without a private registry, internal module sharing tends to happen via copy-paste or ad hoc Git source references ([§58](../Part8/Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)) with no version browsing, changelog, or auto-generated docs — a private registry gives internal modules the same UX public ones enjoy.
- **Semantic versioning becomes enforceable and visible.** Publishing via VCS tags means every module version is traceable to an exact commit, and consumers pin versions with the same constraint operators ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) used for public modules.
- **Custom/internal providers become distributable without publishing publicly.** Organizations building providers for internal-only systems (an internal PaaS, a proprietary hardware API) need a way to distribute signed binaries without exposing them on the public registry — the private provider registry exists specifically for this.
- **Centralizes governance over what "approved" internal building blocks exist.** A platform team can position the private registry as the sanctioned source of truth for how VPCs, IAM roles, or standard compute patterns are provisioned org-wide, discouraging drift toward one-off reimplementations per team.
- **Reduces onboarding friction.** A new engineer browsing the org's private registry sees documented, versioned, ready-to-use modules instead of hunting through Slack history or tribal knowledge for "which repo has the VPC module."

## 3. Prerequisites and Dependencies

Assumes module fundamentals ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)–[§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md)), module sourcing patterns ([§58](../Part8/Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)), and the public Terraform Registry's consumption model ([§59](../Part8/Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md), [§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) — the private registry reuses the same mechanics, scoped to an organization. Assumes the organization/workspace model from [§84](./Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md).

## 4. Architecture / Conceptual Diagram

```text
   MODULE PUBLISHING                          PROVIDER PUBLISHING

   Git repo: terraform-aws-vpc                 Git repo: terraform-provider-internal
   tag: v1.4.0  ────────────┐                  signed release binaries (GPG) ────┐
                            │                                                    │
                            ▼                                                    ▼
              ┌─────────────────────────────────────────────────────────┐
              │        ORGANIZATION PRIVATE REGISTRY (app.terraform.io) │
              │  - versioned module storage + auto-generated docs       │
              │  - versioned, signed provider binary storage            │
              └─────────────────────────────────────────────────────────┘
                            │                                    │
                            ▼                                    ▼
   module "vpc" {                              terraform {
     source  = "app.terraform.io/acme-corp/     required_providers {
                 vpc/aws"                          internal = {
     version = "~> 1.4"                              source  = "app.terraform.io/
   }                                                             acme-corp/internal"
                                                     version = "~> 2.0"
                                                   }
                                                 }
                                               }
```

- Both registries live under the same organization namespace and are consumed with source strings that differ from public-registry consumption only by the explicit hostname prefix.
- Module publishing is typically automatic on VCS tag push; provider publishing requires signed release artifacts, since Terraform verifies provider binary signatures at install time regardless of registry source.

## 5. Hands-On

### 5.1 Publishing and Consuming a Private Module

**Purpose:** Show the source-string difference between public and private registry consumption, and the versioning mechanics.

**Syntax:**

```hcl
module "vpc" {
  source  = "app.terraform.io/acme-corp/vpc/aws"
  version = "~> 1.4"

  cidr_block = "10.0.0.0/16"
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing modules...
Downloading app.terraform.io/acme-corp/vpc/aws 1.4.2 for vpc...
- vpc in .terraform/modules/vpc

Initializing provider plugins...
Terraform has been successfully initialized!
```

**Production usage example:** A platform team maintains `terraform-aws-vpc` as a version-tagged repository; publishing `v1.5.0` immediately makes it available org-wide at that version to every workspace pinned with a compatible constraint, without any manual distribution step.

**Common errors:** A module repo's tag not following exact semantic-versioning format (`v1.4.0`, not `release-1.4` or `1.4`) means the registry never ingests it as a new version — the tag exists in Git but never appears in the registry's version list.

### 5.2 Consuming a Private Provider

**Purpose:** Show how a custom internal provider is referenced identically to a public one, differing only by registry host.

**Syntax:**

```hcl
terraform {
  required_providers {
    internal = {
      source  = "app.terraform.io/acme-corp/internal"
      version = "~> 2.0"
    }
  }
}

provider "internal" {
  endpoint = "https://internal-api.acme.corp"
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing provider plugins...
- Finding app.terraform.io/acme-corp/internal versions matching "~> 2.0"...
- Installing app.terraform.io/acme-corp/internal v2.1.0...
- Installed app.terraform.io/acme-corp/internal v2.1.0 (signed by a HashiCorp partner or your own key)

Terraform has been successfully initialized!
```

**Production usage example:** A team building Terraform automation against an internal, non-public service (an internal PaaS control plane) ships a custom provider through the private provider registry rather than distributing raw binaries via shared drives or manually placed plugin directories.

**Common errors:** Skipping GPG signing of provider release binaries causes `terraform init` to reject installation with a signature verification failure — provider registries (public or private) enforce signed releases, unlike raw local-path provider installs.

## 6. Production Usage Notes

- **Module registry ingestion is VCS-driven by default**, mirroring the same webhook mechanism VCS-connected workspaces use ([§85](./Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md)) — tagging a release is the entire publish action, with no separate upload step in the common case.
- **Documentation is auto-generated from module structure**, meaning well-written `variables.tf`/`outputs.tf` descriptions and a good `README.md` ([§56](../Part8/Section-56-Part8-Module-Structure-and-Conventions.md)) directly determine registry documentation quality — there's no separate documentation-authoring step in the registry itself.
- **Version constraints on private-registry modules behave identically to public ones** ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) — `~>`, exact pins, and range constraints all work the same way, so existing team conventions for module pinning carry over without modification.

## 7. Security Considerations

- Private registry access is scoped to the organization by TFC/TFE's authentication — but within that boundary, anyone with read access to the organization can typically browse and consume any published module or provider, so genuinely sensitive internal logic shouldn't be assumed hidden just because it's "private" relative to the public internet.
- Provider signature verification remains mandatory even for internally published providers — an organization must maintain its own GPG signing key management practice for internal provider releases, with the same key-custody care as any other code-signing key.
- A compromised VCS repository backing a published module (if an attacker gains push/tag access) can push a malicious new version that downstream workspaces pull on their next `terraform init` — repository protection (branch rules, tag protection) on module source repos is a real supply-chain control, not just a hygiene nicety.

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Likely Cause                                                                                                                        | Resolution Path                                                                                                       |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| A new Git tag doesn't appear as a new module version in the registry | Tag doesn't match required semantic-version format, or the VCS webhook/connection is misconfigured                                  | Verify tag format (`vX.Y.Z`); check the module's VCS connection status in the registry UI                             |
| `terraform init` fails to find a private module/provider             | Missing or expired authentication to the organization (no `terraform login` token), or incorrect source string                      | Re-run `terraform login`; double-check the exact `app.terraform.io/<org>/<name>/<provider>` source string             |
| Provider install fails with a signature verification error           | Release binaries weren't signed, or were signed with a key not registered to the organization                                       | Sign releases with the registered GPG key; verify the key is correctly configured in the provider's registry settings |
| A consumer is stuck on an old module version despite new releases    | Version constraint pins too tightly (e.g., exact `= "1.2.0"`) or `.terraform.lock.hcl`/cached `.terraform/modules` wasn't refreshed | Loosen the constraint deliberately if appropriate; run `terraform init -upgrade`                                      |

## 9. Best Practices

- Require semantic-version tagging discipline (with real changelog entries) on any repository backing a published private module, since consumers rely on version numbers to signal breaking vs. non-breaking changes ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)).
- Treat private-registry modules as the canonical, sanctioned way to provision common patterns org-wide, and actively discourage parallel one-off reimplementations once a module exists.
- Apply the same branch/tag protection to module and provider source repositories that you'd apply to any other supply-chain-sensitive code, since a bad publish is consumed automatically by every workspace pinned to a compatible version range.

## 10. Common Anti-Patterns / Mistakes

- **Treating "private registry" as "secure by obscurity."** Anyone with organization access can browse and consume it — sensitive logic still needs proper access control design, not just registry privacy.
- **Publishing modules without meaningful version bumps for breaking changes.** Reusing patch-version bumps for changes that alter required variables silently breaks every consumer relying on `~>` constraints assuming backward compatibility.
- **Letting the private registry become a dumping ground of unmaintained modules.** Without ownership and deprecation practices, a private registry accumulates abandoned modules just as public ones do, undermining the "sanctioned source of truth" value it's meant to provide.

## 11. Interview Questions

**🎯 Beginner:** _"What is a private module registry, in one sentence?"_
**Model answer:** It's an organization-scoped version of the public Terraform Registry, hosted by Terraform Cloud/Enterprise, that lets internal teams publish and consume versioned, documented modules using the same source-and-version syntax as public modules.
_What the interviewer is probing for:_ Basic understanding that this mirrors, rather than replaces, the public registry consumption model.

**🎯 Intermediate:** _"How does a module actually get published to a private registry, and how does a consumer pin a specific version?"_
**Model answer:** Publishing typically happens automatically when a semantic-version tag (`vX.Y.Z`) is pushed to the module's connected VCS repository, which the registry ingests as a new version, auto-generating documentation from the module's variable/output definitions and README. A consumer references it with `source = "app.terraform.io/<org>/<name>/<provider>"` and a `version` constraint using the same operators (`~>`, exact, range) used for public-registry modules — no special syntax is needed beyond the explicit registry hostname.
_What the interviewer is probing for:_ Whether the candidate has actually published or consumed from a private registry, not just knows it exists.

**🎯 Senior:** _"Your organization has a dozen teams each maintaining their own copy of a VPC module with slight variations. How would you use the private registry to consolidate this, and what resistance would you expect?"_
**Model answer:** Consolidate into a single, well-parameterized canonical module (using variables for the points of legitimate variation between teams, per [§62](../Part8/Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md)'s design guidance) published to the private registry with clear semantic versioning, then migrate each team's workspace to consume it via `source = "app.terraform.io/..."` incrementally, pinning to the version matching their current behavior before upgrading deliberately. Expected resistance: teams whose "slight variations" are actually meaningful divergences (different compliance requirements, different scale) may resist consolidation if the canonical module can't cleanly express their variation, requiring either genuinely optional parameters or, in some cases, accepting that not every use case should be forced into one module. The migration itself is the harder sell than the registry setup — publishing is the easy part; getting a dozen teams to adopt and re-pin is the actual organizational work.
_What the interviewer is probing for:_ Awareness that the registry is a mechanism, not a solution to the underlying organizational coordination problem.

**🎯 Architect:** _"When would you build and publish a custom internal Terraform provider rather than just using existing providers plus modules?"_
**Model answer:** A custom provider is justified when the resources being managed don't correspond to any existing provider's API surface at all — typically an internal platform, proprietary hardware control plane, or internal service with its own CRUD API that teams want to manage declaratively through the same Terraform workflow as everything else. It's a meaningfully bigger investment than a module: building a provider means implementing the Provider SDK's CRUD lifecycle ([§8](../Part2/Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md)) correctly, including drift detection and proper state representation, not just parameterizing existing resource blocks. The private provider registry is what makes this practical to distribute afterward, but the decision to build a provider at all should be reserved for cases where a module genuinely can't express the need — wrapping an existing provider's resources in a module is almost always less engineering effort than writing and maintaining a provider, and should be tried first.
_What the interviewer is probing for:_ Correct judgment about when the (nontrivial) cost of building a custom provider is actually justified versus reaching for a module.

## 12. Common Misconceptions

1. **"Private registry modules need different syntax to consume."** They use the identical `source`/`version` syntax as public modules — only the explicit registry hostname differs.
2. **"Publishing to the private registry requires a manual upload step."** The common path is fully automatic: pushing a semantic-version Git tag triggers ingestion, no manual artifact upload needed.
3. **"The private provider registry is only for HashiCorp-style community providers."** It's equally suited to fully custom, internal-only providers built by an organization for its own internal APIs, never intended for public distribution.
4. **"Private means access-controlled per-module."** Within an organization, registry content is generally visible to anyone with organization access — it isn't private per individual module by default.

## 13. 🔑 Key Takeaways

- The private module and provider registries mirror the public Terraform Registry's protocol and consumption UX, scoped to an organization.
- Module publishing is typically automatic on semantic-version Git tag push; provider publishing requires signed release binaries.
- Consumption syntax is identical to public-registry consumption, differing only by the explicit `app.terraform.io/<org>/...` hostname prefix.
- The registry centralizes internal reuse and versioning discipline but doesn't by itself solve organizational adoption/migration challenges.
- Provider signature verification remains mandatory even for internal, private-only providers.

## 14. Related Concepts & What's Next

[§88](./Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md) covers run triggers, which often connect workspaces consuming shared modules published here. [§59](../Part8/Section-59-Part8-The-Terraform-Registry-Publishing-and-Consuming-Public-Modules.md) and [§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md) cover the public registry equivalents this section directly parallels. [§62](../Part8/Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md) covers module design best practices relevant to what gets published to a private registry in the first place.

**Next Section:** [§88](./Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md) — `Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md`
