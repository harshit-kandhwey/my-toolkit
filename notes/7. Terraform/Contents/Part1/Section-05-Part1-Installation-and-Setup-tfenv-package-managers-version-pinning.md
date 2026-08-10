# Section 5 (Part 1): Installation and Setup (tfenv, Package Managers, Version Pinning)

## 1. Definition

**Plain language:** Getting Terraform running on a machine means installing the single self-contained binary — but in practice, most teams need to run _multiple_ Terraform versions across different projects, so the real-world setup question isn't "how do I install Terraform" but "how do I install and switch between several pinned versions cleanly."

**Precise definition:** Terraform ships as a **single statically-linked binary** with no external runtime dependencies, distributable via direct download from HashiCorp's releases site, OS package managers (Homebrew, Chocolatey, apt/yum via HashiCorp's official repositories), or a **version manager** — most commonly **tfenv** (a `rbenv`-style tool that installs and switches between multiple Terraform versions per-project) or its more modern OpenTofu/multi-tool equivalent, **`tfswitch`** or **`asdf`** with the Terraform plugin. **Version pinning** — constraining exactly which Terraform Core version a given configuration requires via the `required_version` argument in a `terraform` block — is the mechanism that makes a specific installed version _enforced_, not just installed, preventing accidental use of an incompatible version in CI or by a teammate.

> 💡 **Tip:** Install method and version pinning are two separate concerns that are easy to conflate: the install method (package manager, tfenv, manual download) determines _what's available_ on a machine; `required_version` in configuration determines _what Terraform will actually let you run_ against that specific codebase. A project should always pin `required_version` regardless of how Terraform itself was installed.

## 2. Why This Matters

- **Version drift across a team is a real, common source of "works on my machine" bugs.** Terraform's plan output and even valid HCL syntax can differ meaningfully between major/minor versions — an unpinned team will eventually hit a plan that looks different (or fails outright) purely because of version skew.
- **Different projects legitimately need different Terraform versions.** A team maintaining both a legacy 0.12-era codebase (which cannot be safely auto-upgraded) and new 1.9-era work needs to switch versions per-directory without reinstalling — this is tfenv's core use case.
- **CI/CD reproducibility depends on install method being deterministic.** A pipeline that installs "whatever `apt install terraform` currently resolves to" is not reproducible across time the way a pinned tfenv version or a Docker image with a fixed version tag is.
- **The OpenTofu fork ([§2](./Section-02-Part1-History-Terraform-Origins-IaC-Tooling-Landscape.md)) adds a real decision point at install time.** Teams now genuinely choose between installing `terraform` or `tofu` (or both), which affects every download/package-manager choice covered here.
- **Certification relevance.** The Terraform Associate exam's "install and configure Terraform" domain expects familiarity with installation options and version-pinning syntax specifically.

## 3. Prerequisites and Dependencies

Builds on [§4](./Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md) (architecture — understanding that Terraform is a single Core binary plus separately-downloaded providers clarifies why installing Terraform itself is a lightweight step, while `terraform init` is the heavier, project-specific one). Assumes basic command-line/shell comfort (see [§6](./Section-06-Part1-Prerequisites-Recap-Cloud-Fundamentals-CLI-Basics.md), this Part, for a fuller prerequisites recap) and, for package-manager installs, basic familiarity with the relevant OS's package manager.

## 4. Architecture / Conceptual Diagram

```text
   Without a version manager                  With tfenv

   /usr/local/bin/terraform                   ~/.tfenv/versions/
     (one version, system-wide,                 1.5.7/terraform
      manually replaced to upgrade/              1.8.2/terraform
      downgrade)                                 1.9.5/terraform
                                                       │
   Every project on this machine              ~/.tfenv/bin/terraform (symlink)
   uses the SAME version, regardless               │
   of what each project's                    resolves per-directory via:
   required_version says.                      - .terraform-version file
                                                 - TFENV_TERRAFORM_VERSION env var
                                                 - `tfenv use <version>`

                                              Project A/.terraform-version → 1.8.2
                                              Project B/.terraform-version → 1.9.5
                                              (tfenv switches automatically per cd)
```

- **Direct binary download**: HashiCorp publishes signed zip archives per OS/architecture at `releases.hashicorp.com` — the simplest install, but manual version switching (replace the binary) and no per-project automatic switching.
- **Package managers** (Homebrew on macOS, Chocolatey/winget on Windows, apt/yum via HashiCorp's official Linux repos): convenient, but typically install and manage a single system-wide version, same limitation as direct download for multi-version needs.
- **tfenv**: installs the tfenv tool itself (via Homebrew or git clone), then `tfenv install <version>` fetches specific Terraform versions into `~/.tfenv/versions/`, and a `.terraform-version` file dropped in a project directory makes `tfenv`-managed `terraform` resolve to that exact version automatically when invoked from that directory — this per-directory automatic resolution is tfenv's core value over a plain package manager install.
- **`required_version` in HCL** is enforced regardless of install method: it's Terraform's own runtime check that refuses to proceed if the currently-invoked binary doesn't satisfy the constraint, providing a second, configuration-level guarantee independent of whatever installed the binary.

## 5. Hands-On

### 5.1 Installing Terraform via tfenv

**Purpose:** Set up multi-version management so different projects can pin and use different Terraform Core versions on the same machine.

**Syntax:**

```bash
# macOS / Linux (Homebrew)
brew install tfenv
tfenv install 1.9.5
tfenv use 1.9.5
```

**Example usage and expected output:**

```bash
$ brew install tfenv
==> Installing tfenv
🍺  /usr/local/Cellar/tfenv/3.0.0: 8 files, 27KB

$ tfenv install 1.9.5
Installing Terraform v1.9.5
Downloading release tarball...
Installation of terraform v1.9.5 successful

$ tfenv use 1.9.5
Switching default version to v1.9.5
Default version (when not overridden by .terraform-version) is now: 1.9.5

$ terraform version
Terraform v1.9.5
```

**Production usage example:** A monorepo containing several Terraform root modules on different version tracks drops a `.terraform-version` file in each root module's directory — `cd` into any of them and `terraform` automatically resolves to the pinned version for that specific codebase, no manual `tfenv use` needed per switch.

**Common errors:** Forgetting to add `~/.tfenv/bin` to `$PATH` after installing via git clone (rather than Homebrew) results in `terraform: command not found` even though tfenv itself installed correctly.

### 5.2 Pinning the Required Version in Configuration

**Purpose:** Enforce, at the configuration level, that only a compatible Terraform Core version can run against a given codebase — independent of what's installed.

**Syntax:**

```hcl
terraform {
  required_version = ">= 1.7.0, < 2.0.0"
}
```

**Example usage and expected output:**

```bash
$ terraform version
Terraform v1.5.7

$ terraform plan
╷
│ Error: Unsupported Terraform Core version
│
│ This configuration does not support Terraform version 1.5.7. To proceed,
│ either choose another supported Terraform version or update the
│ VersionConstraint specified in the configuration.
╵
```

**Production usage example:** Every root module in a production codebase pins `required_version`, so that a teammate (or a CI runner) with an incompatible local Terraform install fails fast with a clear error at `plan`/`apply` time, rather than producing a subtly wrong plan due to version-specific behavior differences.

**Common errors:** Setting an overly narrow constraint (e.g., pinning to an exact patch version with `= 1.9.5`) unnecessarily blocks routine patch upgrades across the team — a range constraint (`~> 1.9.0` or `>= 1.7.0, < 2.0.0`) is the more common production pattern, tightened only when a specific bug requires it.

## 6. Production Usage Notes

- **CI/CD pipelines typically pin Terraform version via the pipeline's own tooling** (a specific Docker image tag `hashicorp/terraform:1.9.5`, or a `setup-terraform` GitHub Action's `terraform_version` input) rather than relying on whatever's pre-installed on the runner — this makes the install method itself part of the pinned, reproducible pipeline definition.
- **`required_version` and the actual installed binary are complementary, not redundant.** `required_version` fails fast with a clear error message when there's a mismatch; without it, an incompatible Terraform version might still technically run and produce a plan that's subtly wrong (parses successfully but behaves differently) rather than failing outright.
- **Provider version pinning (`required_providers`, [§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)) is a separate, equally important pinning axis** — pinning Terraform Core version alone doesn't protect against provider version drift; both should be pinned together in production configurations.

## 7. Security Considerations

- Always install Terraform from official sources (HashiCorp's releases site, official package repositories, or tfenv fetching from HashiCorp's releases) — verify checksums/signatures where the install method supports it, since a tampered Terraform binary would have the same broad execution privileges as any provider plugin it spawns.
- CI/CD pipelines pulling a Terraform Docker image should pin to a specific digest or tag from an official HashiCorp image, not `latest`, for the same reproducibility and supply-chain reasons as provider version pinning ([§2](./Section-02-Part1-History-Terraform-Origins-IaC-Tooling-Landscape.md)).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Likely Cause                                                                       | Resolution Path                                                                                                              |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| `terraform: command not found` after installing tfenv via git clone     | `~/.tfenv/bin` not added to shell `$PATH`                                          | Add `export PATH="$HOME/.tfenv/bin:$PATH"` to shell profile, reload shell                                                    |
| `Unsupported Terraform Core version` error on `plan`/`apply`            | Installed Terraform version doesn't satisfy the configuration's `required_version` | Install/switch to a compatible version (tfenv, or manual reinstall); do not loosen the constraint just to silence the error  |
| Different team members get different `plan` output for identical config | Team is running different, unpinned Terraform Core or provider versions            | Enforce `required_version` and `required_providers` version constraints repo-wide; standardize on tfenv or a pinned CI image |

## 9. Best Practices

- Use a version manager (tfenv or equivalent) on any machine that touches more than one Terraform codebase — manual binary swapping does not scale past a single project.
- Always set `required_version` in every root module's `terraform` block, using a range constraint that allows routine patch/minor upgrades but blocks major-version jumps until explicitly tested.
- Keep CI/CD's Terraform version pinning explicit and version-controlled (in the pipeline definition itself), not dependent on whatever a runner image happens to have pre-installed.

## 10. Common Anti-Patterns / Mistakes

- **Relying solely on "whatever's installed" without `required_version`.** This defers version-mismatch discovery from a clear, immediate error to a confusing, possibly-silent difference in plan behavior.
- **Pinning `required_version` to an exact version (`= x.y.z`) by default.** This blocks routine, safe patch upgrades across the team for no real safety benefit in most cases — reserve exact pinning for situations with a known, specific compatibility issue.
- **Installing Terraform system-wide via a package manager on a machine that works across multiple codebases with different version needs**, then fighting version mismatches manually instead of adopting a version manager.

## 11. Interview Questions

**🎯 Beginner:** _"What are the main ways to install Terraform?"_
**Model answer:** Direct binary download from HashiCorp's releases site, an OS package manager (Homebrew, Chocolatey, or HashiCorp's official apt/yum repositories), or a version manager like tfenv that allows installing and switching between multiple Terraform versions on the same machine.
_What the interviewer is probing for:_ Basic familiarity with the installation landscape.

**🎯 Intermediate:** _"Why would a team use tfenv instead of just installing Terraform via a package manager?"_
**Model answer:** A package manager typically installs and manages a single system-wide Terraform version, so switching versions means manually reinstalling or replacing the binary — fine for a single-project machine, but painful for anyone working across multiple codebases pinned to different Terraform versions. tfenv installs multiple versions side by side and automatically resolves which one to use per-directory based on a `.terraform-version` file, so `cd`-ing between projects on different version tracks "just works" without manual switching.
_What the interviewer is probing for:_ Understanding of the actual operational problem version managers solve, not just that they exist.

**🎯 Senior:** _"Explain the difference between how Terraform is installed on a machine and how `required_version` in configuration enforces version compatibility. Why do you need both?"_
**Model answer:** Installation (via package manager, tfenv, or manual download) determines what Terraform binaries are physically available and which one gets invoked when you type `terraform`. `required_version` is a configuration-level constraint that Terraform itself checks at runtime against whichever binary actually gets invoked — it doesn't install or select a version, it validates the one that's running. You need both because installation alone doesn't protect against version drift across a team: if one engineer's machine happens to have an older or newer Terraform than the codebase was tested against, without `required_version` that mismatch would only surface as a possibly-subtle behavioral difference in plan output, not a clear error, since an incompatible-but-similar version will often still run. `required_version` converts a silent behavioral risk into an explicit, immediate failure.
_What the interviewer is probing for:_ Whether the candidate understands these as two distinct, complementary mechanisms rather than treating "installed version" and "required version" as the same concept.

**🎯 Architect:** _"You're setting up Terraform tooling standards for an organization with 40 engineers across a dozen repositories on different Terraform version tracks, plus CI/CD pipelines. What would you actually mandate, and why?"_
**Model answer:** I'd mandate three things working together. First, every engineer's local machine uses tfenv (not a package manager), with each repository carrying a `.terraform-version` file committed to source control, so `cd`-ing into any repo automatically resolves the correct version with zero manual steps — this removes the most common source of "works on my machine" version drift. Second, every root module's `terraform` block sets `required_version` as a range constraint matching that repo's actual tested compatibility, so even if someone bypasses tfenv, an incompatible version fails fast with a clear message rather than producing a subtly wrong plan. Third, CI/CD pipelines pin their own Terraform version explicitly in pipeline definition (a specific image tag or `setup-terraform` action version), version-controlled alongside the pipeline config itself, so pipeline behavior doesn't silently drift when a shared runner image updates. The unifying principle: version resolution should be automatic and committed to source control wherever possible (`.terraform-version`, pipeline definitions), with `required_version` as the safety net that catches whatever slips through.
_What the interviewer is probing for:_ Ability to design a coherent, multi-layered organizational standard rather than a single ad-hoc fix, and awareness that local, CI, and configuration-level pinning are three separate surfaces that all need addressing.

## 12. Common Misconceptions

1. **"Installing the latest Terraform version is always the safe default."** Without a corresponding `required_version` check and team-wide coordination, "latest" varies by whoever installed it last and when — the safe default is a pinned, agreed-upon version, not "whatever's newest."
2. **"`required_version` installs or upgrades Terraform automatically."** It only validates the currently-invoked binary against a constraint — it never installs anything itself; a version manager or manual install is still required to actually obtain a compatible binary.
3. **"tfenv and package-manager installs can't coexist."** They can conflict on `$PATH` resolution if not managed carefully, but many engineers do use tfenv specifically to override a package-manager-installed system default per-project.
4. **"Version pinning is only a CI/CD concern."** Local developer machines are just as susceptible to version drift as CI runners — pinning matters everywhere Terraform is invoked, not only in automated pipelines.

## 13. 🔑 Key Takeaways

- Terraform installs as a single self-contained binary, distributable via direct download, package managers, or a version manager like tfenv.
- tfenv (and equivalents like `tfswitch`/`asdf`) solve the specific problem of needing different Terraform versions across different projects on the same machine, via automatic per-directory version resolution.
- `required_version` in a `terraform` block is a distinct, configuration-level enforcement mechanism, independent of install method — it validates whatever binary is actually invoked.
- Both installation strategy and `required_version` pinning should be addressed together for real reproducibility; neither alone is sufficient.
- CI/CD pipelines should pin their Terraform version explicitly as part of the pipeline definition itself, not rely on a runner's pre-installed default.

## 14. Related Concepts & What's Next

[§4](./Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md) (architecture) explained why Terraform's install footprint is lightweight (a single Core binary; providers download separately at `init`). [§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md) covers the parallel, equally important pinning concern for provider versions. [§110](../Part15/Section-110-Part15-Versioning-Strategy-Terraform-Core-Providers-and-Modules.md) revisits versioning strategy across Terraform Core, providers, and modules together as a holistic organizational practice. [§6](./Section-06-Part1-Prerequisites-Recap-Cloud-Fundamentals-CLI-Basics.md) (next) recaps the broader prerequisite knowledge — cloud fundamentals and CLI basics — assumed from this point forward in the roadmap.

**Next Section:** [§6](./Section-06-Part1-Prerequisites-Recap-Cloud-Fundamentals-CLI-Basics.md) — `Section-06-Part1-Prerequisites-Recap-Cloud-Fundamentals-CLI-Basics.md`
