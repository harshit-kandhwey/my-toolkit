# Section 59 (Part 8): The Terraform Registry: Publishing and Consuming Public Modules

## 1. Definition

**Plain language:** The Terraform Registry (registry.terraform.io) is a public catalog of ready-made modules and providers that anyone can browse, and that Terraform can pull directly into a configuration by name — similar in spirit to npm for JavaScript packages or the Python Package Index for Python libraries, but for infrastructure modules and provider plugins.

**Precise definition:** The **Terraform Registry** is HashiCorp's hosted service for discovering and distributing Terraform **modules** and **providers**. Public modules are indexed under a three-part address, `<NAMESPACE>/<NAME>/<PROVIDER>` (e.g., `terraform-aws-modules/vpc/aws` — namespace `terraform-aws-modules`, module name `vpc`, target provider `aws`), and are published by connecting a GitHub repository whose name follows the required convention `terraform-<PROVIDER>-<NAME>` (e.g., a repo named `terraform-aws-vpc` publishes as `<your-namespace>/vpc/aws`). The registry generates published versions directly from that repository's Git **tags**, which must follow semantic versioning (`vX.Y.Z`) — there is no separate "upload" step; pushing a correctly formatted tag to the connected repository is what creates a new published module version. The registry also auto-generates documentation pages from each version's `variables.tf`/`outputs.tf`/`README.md` ([§56](./Section-56-Part8-Module-Structure-and-Conventions.md)), and enterprise/paid tiers additionally offer a **private registry** ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) with the same mechanics scoped to an organization.

> 💡 **Tip:** The registry doesn't host module code itself in any separate storage — it's a thin index and documentation layer over your GitHub repository's tags. This means "publishing a new version" is literally just "pushing a semver-formatted Git tag to the connected repo" — there's no separate build, package, or upload step to remember, which is both the registry's biggest convenience and its biggest gotcha (a bad tag pushed by accident is immediately a "published" version).

## 2. Why This Matters

- **The registry is the default first place engineers look before writing a module from scratch** — for common, well-solved patterns (a standard VPC, a standard EKS cluster, a standard RDS instance), a well-maintained public module often saves days of provisioning-logic work and encodes provider-specific best practices the author may not know to apply.
- **Semantic versioning tags are what make `version` constraints on registry sources ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) meaningful at all** — this only works because the registry enforces (and generates version listings from) the tag-based semver convention described above.
- **Auto-generated documentation reduces the maintenance burden of publishing a module publicly** — the registry renders `README.md` plus structured input/output tables directly from the source repository, so authors don't maintain a separate documentation site.
- **Understanding how publishing actually works (tag-driven, GitHub-repo-based) demystifies the registry** — it's not a mysterious managed service with its own release process; it's a well-defined, entirely Git-based convention any team can also apply internally to a private registry ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)).
- Consuming and evaluating third-party public modules responsibly (checking maintenance activity, download counts, verified-publisher status, and vulnerabilities) is now a standard part of production Terraform practice, not an edge case.

## 3. Prerequisites and Dependencies

This section builds directly on [§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)'s `source` syntax for registry addresses and assumes the standard module structure from [§56](./Section-56-Part8-Module-Structure-and-Conventions.md), since that structure is exactly what the registry parses to generate documentation. [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md) (immediately following) depends on this section's tag-driven versioning model to make sense of version constraint operators. Familiarity with Git tags and semantic versioning as a general convention is assumed baseline knowledge.

## 4. Architecture / Conceptual Diagram

```text
PUBLISHING FLOW (public registry)
┌───────────────────────────────────────────────────────────────────┐
│ 1. Author creates GitHub repo: terraform-aws-vpc                  │
│    (naming convention: terraform-<PROVIDER>-<NAME>)               │
│                                                                   │
│ 2. Repo follows standard module structure (§56):                  │
│    main.tf, variables.tf, outputs.tf, README.md, examples/        │
│                                                                   │
│ 3. Author connects the repo at registry.terraform.io              │
│    (one-time GitHub OAuth authorization)                          │
│                                                                   │
│ 4. Author pushes a semver tag:  git tag v1.0.0 && git push --tags │
│                                                                   │
│ 5. Registry auto-detects the tag, publishes version 1.0.0,        │
│    generates docs from variables.tf/outputs.tf/README.md          │
└───────────────────────────────────────────────────────────────────┘

RESULTING PUBLIC ADDRESS:
  registry.terraform.io/modules/<namespace>/vpc/aws/1.0.0
                          └─────┬─────┘  └┬┘ └┬┘
                          GitHub username  name provider
                          (or org name)   (from repo   (from repo
                                          suffix)      suffix)

CONSUMING FLOW
  module "vpc" {
    source  = "terraform-aws-modules/vpc/aws"   <- namespace/name/provider
    version = "~> 5.0"                            <- semver constraint (§60)
  }
        │
        ▼
  terraform init resolves highest version matching "~> 5.0"
  among all tags the registry has indexed for that module,
  downloads it into .terraform/modules/vpc
```

- The `<PROVIDER>` segment of the address is the **target provider the module is written for** (e.g., `aws`, `azurerm`, `google`), not a reference to the registry's own provider listings — a module and a provider can share the same word in different contexts, which is a common point of confusion for newcomers.
- Every version listed on a module's registry page corresponds one-to-one with a Git tag on the connected repository — there's no registry-side version that doesn't trace back to a real tag.

## 5. Hands-On

### 5.1 Consuming a Public Registry Module

**Purpose:** Show the full consumption flow, from browsing to using a specific version.

**Syntax:**

```hcl
module "vpc" {
  source  = "terraform-aws-modules/vpc/aws"
  version = "~> 5.8"

  name = "app-vpc"
  cidr = "10.0.0.0/16"

  azs             = ["us-east-1a", "us-east-1b"]
  private_subnets = ["10.0.1.0/24", "10.0.2.0/24"]
  public_subnets  = ["10.0.101.0/24", "10.0.102.0/24"]
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing modules...
Downloading registry.terraform.io/terraform-aws-modules/vpc/aws 5.8.1 for vpc...
- vpc in .terraform/modules/vpc

$ terraform plan
Plan: 12 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Consuming a well-maintained public module for a common pattern like VPC provisioning is the standard, expected approach in most organizations rather than hand-rolling equivalent resources — it encodes best practices (correct route table associations, NAT gateway placement, tagging conventions) that would otherwise need to be independently re-derived and maintained.

**Common errors:** Confusing the registry address's `<PROVIDER>` segment with a provider version constraint — `terraform-aws-modules/vpc/aws` means "a module named vpc, written for the aws provider," which is entirely separate from `required_providers { aws = { version = "~> 5.0" } }` ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)), the actual provider plugin version constraint.

### 5.2 Preparing and Publishing a Module

**Purpose:** Show the minimum repository setup and tagging steps required to publish.

**Syntax:**

```bash
# Repo name MUST follow terraform-<PROVIDER>-<NAME> convention:
$ git init terraform-aws-s3-bucket
$ cd terraform-aws-s3-bucket
# ... add main.tf, variables.tf, outputs.tf, versions.tf, README.md (§56) ...
$ git add .
$ git commit -m "Initial module implementation"
$ git tag v1.0.0
$ git push origin main --tags
```

**Example usage and expected output:**

```text
# At registry.terraform.io, after connecting the GitHub repo:
Module published: <namespace>/s3-bucket/aws
Latest version: 1.0.0
Documentation generated from README.md, variables.tf, outputs.tf
```

**Production usage example:** Organizations standing up their own suite of public modules (common for vendors and cloud-tooling companies, and for teams wanting to give back to the community) follow exactly this flow — the repo naming convention and semver tagging are the only hard requirements; everything else (README quality, example completeness) is what determines actual adoption.

**Common errors:** Pushing a tag that doesn't match `vX.Y.Z` semantic versioning format (e.g., `release-1`, `1.0`) is either ignored by the registry or fails to register as a valid version — the registry's automatic version detection depends entirely on strict semver tag formatting.

## 6. Production Usage Notes

- **Evaluate third-party public modules before adopting them in production** — check maintenance recency (last commit/release date), open issue volume, download counts, and whether the publisher is a HashiCorp "Verified" partner (a trust signal, not a security guarantee) before depending on an unfamiliar module for anything beyond experimentation.
- **A module version once published (tagged) is effectively permanent** — the registry does not support meaningfully "unpublishing" a version that others may already depend on via `version` constraints; breaking changes belong in a new major version tag, never by force-moving an existing tag.
- **Private registries ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) reuse this exact same mechanics** — namespace/name/provider addressing, semver-tag-driven publishing, auto-generated docs — scoped to an organization's own VCS and Terraform Cloud/Enterprise account, which is why understanding the public registry's mechanics transfers directly.

## 7. Security Considerations

- Treat consuming an unfamiliar public module the same as adding any third-party dependency with code-execution-equivalent trust — a malicious or compromised module has the same access as hand-written configuration to whatever provider credentials the calling root module supplies.
- Always pin a `version` constraint ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) rather than leaving it unconstrained — an unconstrained registry source resolves to the latest version at each `init -upgrade`, which can introduce unreviewed behavior changes exactly like the mutable-branch Git risk described in [§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md).
- For a module your own organization publishes, protect the repository's tag-push permissions (e.g., branch/tag protection rules in GitHub) — since a pushed tag becomes an immediately "published," consumable version with no review gate built into the registry itself, tag-push access is effectively equivalent to release-approval access.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                      | Likely Cause                                                                                                                                                    | Resolution Path                                                                                                                                                                          |
| ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A pushed Git tag doesn't appear as a new version on the registry page        | Tag doesn't match strict `vX.Y.Z` semantic version format, or the registry hasn't re-synced yet                                                                 | Verify exact tag format; check the registry's webhook/sync status for the connected repository                                                                                           |
| `terraform init` can't find a registry module by the expected address        | Namespace, name, or provider segment typo, or the module was never actually published under that address                                                        | Verify the exact address on the registry's module page, not assumed from the repository name alone                                                                                       |
| Registry documentation page looks empty or incomplete for a published module | `README.md`/`variables.tf`/`outputs.tf` don't follow the standard structure ([§56](./Section-56-Part8-Module-Structure-and-Conventions.md)) the registry parses | Ensure the standard module file layout is present and well-formed before tagging a new version                                                                                           |
| Consumers report a "breaking change" after upgrading to a new module version | The module's maintainer released a breaking change under a minor/patch version instead of a major bump                                                          | Adopt/enforce semantic versioning discipline ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) for the module going forward; pin consumers more tightly meanwhile |

## 9. Best Practices

- Follow the `terraform-<PROVIDER>-<NAME>` repository naming convention exactly — it's not optional; the registry derives the published address directly from it.
- Adhere strictly to semantic versioning semantics when tagging: breaking changes bump the major version, backward-compatible additions bump the minor version, fixes bump the patch version — consumers' `~>` constraints ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) depend on this discipline being honored.
- Keep a module's `examples/` directory current and its README accurate — the registry surfaces exactly these artifacts as the primary way prospective consumers evaluate whether to adopt the module.

## 10. Common Anti-Patterns / Mistakes

- **Publishing a module with no version constraints guidance and inconsistent tagging** — e.g., some releases tagged `v1.2.0`, others `1.2.0` (no leading `v`) — inconsistent tag formatting confuses both the registry's parsing and downstream consumers' expectations.
- **Treating the public registry as the only source of truth without evaluating maintenance health** — adopting an abandoned module (no updates in years, open critical issues) purely because it appeared first in a search, without checking whether it's actively maintained against current provider versions.
- **Force-moving or deleting a published tag to "fix" a mistaken release** — since consumers may have already resolved and cached that version, this creates non-reproducible builds for anyone who initializes fresh after the tag changes; the correct fix is always a new patch version, never rewriting history on an already-published tag.

## 11. Interview Questions

**🎯 Beginner:** _"What does the three-part address `terraform-aws-modules/vpc/aws` mean in a module source?"_
**Model answer:** It's `<namespace>/<name>/<provider>` — `terraform-aws-modules` is the publisher's namespace, `vpc` is the module's name, and `aws` is the provider the module is written for. Terraform resolves this against the Terraform Registry to download the module.
_What the interviewer is probing for:_ Basic recall of registry address structure and that the third segment is the target provider, not a registry category.

**🎯 Intermediate:** _"How does the Terraform Registry actually know a new version of a module exists — is there a publish/upload step?"_
**Model answer:** No separate upload step — the registry connects directly to the module's GitHub repository and watches for Git tags formatted as semantic versions (`vX.Y.Z`). Pushing a correctly formatted tag to the connected repository is what causes the registry to index and publish that version, along with auto-generating its documentation page from the repository's `README.md`/`variables.tf`/`outputs.tf` at that tag.
_What the interviewer is probing for:_ Understanding that the registry is a thin, Git-tag-driven index rather than a separate artifact-hosting system — this matters for reasoning about how publishing mistakes (bad tags) propagate immediately.

**🎯 Senior:** _"Your team wants to standardize on public registry modules wherever reasonable rather than writing everything in-house. What criteria would you use to evaluate whether a specific public module is safe to adopt for production use?"_
**Model answer:** Beyond basic functional fit, I'd check: recent maintenance activity (commit/release recency relative to current provider major versions, since Terraform providers change frequently enough that a module untouched for two years is a real risk signal); the issue tracker's health (open critical/security issues, response time); whether the publisher is a HashiCorp Verified partner (a helpful but not sufficient trust signal); download/usage popularity as a rough proxy for how battle-tested it is; the module's own examples and test coverage (does it ship `examples/` and, ideally, `terraform test` files, [§100](../Part14/Section-100-Part14-Terratest-and-Native-terraform-test-Framework.md)); and finally, a version-pinning strategy ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) so an in-house `~>` constraint controls exactly when and how updates are consumed rather than tracking latest automatically.
_What the interviewer is probing for:_ A concrete, repeatable evaluation framework for third-party dependency risk, not just "check if it has good reviews."

**🎯 Architect:** _"You're deciding whether your organization should publish its internal modules to the public Terraform Registry versus keeping them on a private registry ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) or plain Git sourcing ([§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)). What factors actually drive that decision?"_
**Model answer:** The public registry makes sense only if the modules are genuinely intended for external consumption — either as open-source contribution to the community, or as a deliberate marketing/ecosystem play (common for infrastructure vendors publishing modules for their own product). For purely internal, organization-specific modules (encoding internal account structure, internal naming conventions, or proprietary patterns), a private registry or Git sourcing is almost always the right call: it avoids exposing internal architecture details publicly, avoids the reputational/support burden of maintaining a public-facing artifact, and — for organizations already on Terraform Cloud/Enterprise — the private registry gives identical semver-constraint ergonomics ([§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) without the public-exposure trade-off. Git sourcing from an internal monorepo ([§58](./Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)) is the lower-overhead alternative for organizations not yet on Terraform Cloud/Enterprise, accepting the version-constraint ergonomics trade-off discussed there in exchange for zero additional infrastructure.
_What the interviewer is probing for:_ Business/architecture judgment about public vs. private module distribution, not just registry mechanics — recognizing that "can we publish publicly" and "should we" are different questions.

## 12. Common Misconceptions

1. **"Publishing to the registry requires uploading a package or artifact."** It doesn't — the registry indexes directly from a connected GitHub repository's semver-formatted tags; there is no separate build/upload/package step.
2. **"The `<PROVIDER>` segment in a module address refers to the registry's provider category, unrelated to the module's actual dependencies."** It specifically means the provider the module is written to work with (e.g., `aws`), and is a required, meaningful part of the address, not decoration.
3. **"A module published on the registry is inherently trustworthy or reviewed by HashiCorp."** Registry publishing is largely self-service (connect a repo, push a tag) — "Verified" publisher status is a helpful signal but the registry itself does not vet module code for correctness or security.
4. **"You can delete or overwrite a published version if you made a mistake."** Once tagged and indexed, a version is effectively permanent for reproducibility reasons — the correct remediation for a mistaken release is always a new version, not retroactively altering an existing one.

## 13. 🔑 Key Takeaways

- The Terraform Registry indexes public modules under `<namespace>/<name>/<provider>`, generated directly from a connected GitHub repository named `terraform-<PROVIDER>-<NAME>`.
- Publishing a new version is literally pushing a semantic-version-formatted Git tag (`vX.Y.Z`) to the connected repository — there is no separate upload step.
- The registry auto-generates documentation from each version's `README.md`, `variables.tf`, and `outputs.tf`, reinforcing why the standard module structure from [§56](./Section-56-Part8-Module-Structure-and-Conventions.md) matters.
- Evaluating a public module's maintenance health, popularity, and versioning discipline is a real production due-diligence step before adoption, not optional.
- Private registries ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) apply this exact same tag-driven mechanics scoped to an organization's own VCS, via Terraform Cloud/Enterprise.

## 14. Related Concepts & What's Next

[§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md) covers the version constraint operators (`~>`, `>=`, exact pins) that consumers use against the semver tags this section's publishing model produces, and clarifies which source types support them. [§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md) extends this same registry mechanics to private, organization-scoped registries. [§56](./Section-56-Part8-Module-Structure-and-Conventions.md)'s standard module structure is what the registry's documentation generation parses.

**Next Section:** [§60](./Section-60-Part8-Module-Versioning-and-Version-Constraints.md) — `Section-60-Part8-Module-Versioning-and-Version-Constraints.md`
