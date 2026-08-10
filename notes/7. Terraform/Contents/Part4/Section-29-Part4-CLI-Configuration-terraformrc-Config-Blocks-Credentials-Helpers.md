# Section 29 (Part 4): CLI Configuration (.terraformrc, CLI Config Blocks, Credentials Helpers)

## 1. Definition

**Plain language:** Separate from any single project's `.tf` files, Terraform reads a personal, machine-wide configuration file that controls how the CLI itself behaves — things like where it looks for providers, whether it phones home for version-check telemetry, and how it authenticates to private registries. This is different from provider credentials (like AWS access keys); it's about the Terraform tool's own behavior across every project on that machine.

**Precise definition:** The **CLI configuration file** (`.terraformrc` on Linux/macOS, `terraform.rc` on Windows, or a path pointed to by the `TF_CLI_CONFIG_FILE` environment variable) is an HCL file, separate from any Terraform configuration, that controls CLI-wide behavior via a small set of top-level blocks: `credentials` and `credentials_helper` (registry authentication), `provider_installation` (mirrors and installation method overrides), `plugin_cache_dir` (a shared local cache to avoid re-downloading identical providers across projects), and `disable_checkpoint` (opting out of HashiCorp's version-check telemetry). This is distinct from **Terraform Cloud/Enterprise API tokens**, which can also live here under `credentials` blocks, and distinct from provider-specific authentication (AWS/Azure/GCP credentials, [§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md)), which lives in provider configuration or standard cloud SDK credential chains, not the CLI config file.

> 💡 **Tip:** The CLI configuration file is **machine/user-scoped, not project-scoped** — it is never checked into a repository and never travels with a project. A `provider_installation` block redirecting to an internal mirror, for instance, applies to every Terraform project run by that user on that machine, regardless of which repository they're currently in.

## 2. Why This Matters

- **`plugin_cache_dir` is one of the single highest-impact local performance settings** — without it, every separate project directory downloads its own copy of every provider it uses, even if ten other projects on the same machine already have that exact provider version cached.
- **`provider_installation` mirrors are essential in air-gapped or tightly firewalled environments** where `init` cannot reach the public Terraform Registry at all — this is the mechanism that redirects provider installation to an internal, approved source.
- **Credentials helpers decouple registry authentication from hardcoded tokens in plaintext files** — a credentials helper is an external program Terraform calls to fetch a token dynamically (e.g., from an OS keychain or a secrets manager), rather than storing it directly in `.terraformrc`.
- **Getting this file wrong silently affects every project on a machine**, not just one — a misconfigured `provider_installation` block can make `init` fail (or worse, silently succeed against the wrong provider source) across an entire team's local environments if distributed via onboarding scripts.
- **It's a common source of "works on my machine" confusion** specifically because it's invisible to anyone reading only the project repository — two engineers with identical `.tf` files can behave differently in `init` due to differing local CLI configuration.

## 3. Prerequisites and Dependencies

Builds directly on provider installation mechanics covered in [§8](../Part2/Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md)–[§10](../Part2/Section-10-Part2-The-Terraform-Registry-and-Sourcing-Providers.md) (the provider plugin model, version constraints, and the public Terraform Registry) and on `terraform init`'s provider-installation step ([§24](./Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md)) — this section covers how to _redirect or customize_ that process, not the base mechanics themselves. Private module/provider registries in Terraform Cloud/Enterprise ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) are the most common reason a team configures `credentials` blocks here. Installation and version management (tfenv, [§5](../Part1/Section-05-Part1-Installation-and-Setup-tfenv-package-managers-version-pinning.md)) is related but distinct — that's about which Terraform _binary_ runs, this is about how the running binary behaves.

## 4. Architecture / Conceptual Diagram

```text
Project-scoped (checked into Git, per-repository)     Machine/user-scoped (never in Git)
┌───────────────────────────────┐                      ┌───────────────────────────────────┐
│ main.tf, versions.tf          │                      │ ~/.terraformrc  (Linux/macOS)     │
│  required_providers { ... }   │                      │ %APPDATA%\terraform.rc (Windows)  │
│  backend "s3" { ... }         │                      │ or path via TF_CLI_CONFIG_FILE    │
└───────────────────────────────┘                      │                                   │
                                                       │  plugin_cache_dir = "~/.tf-cache" │
                                                       │  disable_checkpoint = true        │
                                                       │                                   │
                                                       │  credentials "app.terraform.io" { │
                                                       │    token = "xxxxx.atlasv1...."    │
                                                       │  }                                │
                                                       │                                   │
                                                       │  provider_installation {          │
                                                       │    network_mirror {               │
                                                       │      url = "https://internal/..." │
                                                       │    }                              │
                                                       │  }                                │
                                                       └───────────────────────────────────┘
                                                                      │
                     terraform init reads BOTH,                       │
                     applies CLI config on top of                     │
                     project configuration                            ▼
                                                          Governs: where providers come
                                                          from, registry auth, local cache
                                                          location, telemetry opt-out
```

- **Project config** declares _what_ is needed (`required_providers`, backend). **CLI config** declares _how_ the local machine fulfills that need (where from, cached where, authenticated how).
- **`terraform login`** is the interactive command that writes a `credentials` block into the CLI config file automatically, rather than requiring manual token entry.

## 5. Hands-On

### 5.1 Setting Up a Shared Provider Plugin Cache

**Purpose:** Avoid re-downloading identical provider binaries across every separate project directory on the same machine.

**Syntax (in `~/.terraformrc`):**

```hcl
plugin_cache_dir = "$HOME/.terraform.d/plugin-cache"
```

**Example usage and expected output:**

```bash
$ mkdir -p ~/.terraform.d/plugin-cache
$ cat >> ~/.terraformrc <<'EOF'
plugin_cache_dir = "$HOME/.terraform.d/plugin-cache"
EOF

$ cd project-a && terraform init
Initializing provider plugins...
- Installing hashicorp/aws v5.42.0...
- Installed hashicorp/aws v5.42.0 (signed by HashiCorp)

$ cd ../project-b && terraform init
Initializing provider plugins...
- Using previously-installed hashicorp/aws v5.42.0 from the shared cache directory
```

**Production usage example:** Every engineer's onboarding script/dotfiles for a team working across many separate Terraform repositories sets this once, cutting `init` time dramatically on any repository whose providers overlap with one already cached — a very common real-world setup step.

**Common errors:** Pointing `plugin_cache_dir` at a path that doesn't exist or isn't writable causes `init` to silently fall back to per-project downloading rather than failing loudly — always verify the directory exists and has correct permissions after setting this.

### 5.2 Authenticating to a Private Registry with terraform login

**Purpose:** Obtain and store an API token for Terraform Cloud (or a private registry) without manually copy-pasting a token into a config file.

**Syntax:**

```bash
terraform login [hostname]
```

**Example usage and expected output:**

```bash
$ terraform login

Terraform will request an API token for app.terraform.io using your browser.

If login is successful, Terraform will store the token in plain text in
the following file for use by subsequent commands:
    /home/user/.terraform.d/credentials.tfrc.json

Do you want to proceed?
  Only 'yes' will be accepted to confirm.

  Enter a value: yes

Terraform must now open a web browser to the tokens page for app.terraform.io.
...
Retrieved token for user@example.com

------------------------------------------------------------------------------
Success! Terraform has obtained and saved an API token.
```

**Production usage example:** The standard onboarding step for any engineer starting to use Terraform Cloud's private module registry ([§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) or remote runs ([§85](../Part12/Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md)) — `login` replaces manually generating and pasting a token, reducing the chance of it being pasted somewhere unsafe (like committed into a repo by accident).

**Common errors:** Running `terraform login` on a headless machine (a remote server with no browser) fails to open a browser — the fix is to generate a token manually via the Terraform Cloud UI and add a `credentials` block to the CLI config file directly instead.

### 5.3 Manually Configuring a credentials Block

**Purpose:** Store a registry API token directly in CLI configuration, for headless environments or explicit control over token placement.

**Syntax (in `~/.terraformrc`):**

```hcl
credentials "app.terraform.io" {
  token = "xxxxxx.atlasv1.zzzzzzzzzzzzz"
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing the backend...
Initializing provider plugins...
- Finding latest version of my-org/internal-module in app.terraform.io...
- Installing my-org/internal-module v1.4.0...
- Installed my-org/internal-module v1.4.0
Terraform has been successfully initialized!
```

**Production usage example:** CI runners (headless by definition) that need access to a private module or provider registry set the token via a `credentials` block written from a secret at pipeline runtime — often generated dynamically rather than a static file, described further below.

**Common errors:** Hardcoding a long-lived token directly into a `.terraformrc` committed to a shared dotfiles repo (rather than a personal, gitignored file) is a real credential-leak vector — the CLI config file must never be checked into version control.

### 5.4 Using a Credentials Helper for CI

**Purpose:** Fetch registry tokens dynamically from a secrets manager or CI's native secret store, rather than writing a static token to disk.

**Syntax (in `~/.terraformrc`):**

```hcl
credentials_helper "my-helper" {
  args = []
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing the backend...
Initializing provider plugins...
# Terraform invokes `terraform-credentials-my-helper get app.terraform.io`
# behind the scenes to retrieve the token dynamically, never writing it to
# a static credentials.tfrc.json file on disk.
- Installing my-org/internal-module v1.4.0...
Terraform has been successfully initialized!
```

**Production usage example:** A CI pipeline that generates its `.terraformrc` at job start, pointing `provider_installation` at an internal mirror (see below) and wiring a `credentials_helper` executable that pulls a short-lived token from the CI platform's native secret store (e.g., a GitHub Actions OIDC-derived token) — avoiding ever writing a long-lived static credential into the runner's filesystem at all.

**Common errors:** A `credentials_helper` program that isn't on `PATH` or isn't named exactly `terraform-credentials-<name>` fails silently or with a generic "helper program not found" error — the naming convention is exact and easy to get wrong.

### 5.5 Redirecting Provider Installation to an Internal Mirror

**Purpose:** Install providers from an internal, approved network mirror instead of the public Terraform Registry — essential in air-gapped or compliance-restricted environments.

**Syntax (in `~/.terraformrc`):**

```hcl
provider_installation {
  network_mirror {
    url = "https://terraform-mirror.internal.example.com/providers/"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing provider plugins...
- Finding hashicorp/aws versions matching "~> 5.0"...
- Installing hashicorp/aws v5.42.0 from
  https://terraform-mirror.internal.example.com/providers/...
- Installed hashicorp/aws v5.42.0 (unsigned)
```

Note: providers installed from a network mirror are typically reported as `(unsigned)` unless the mirror itself re-signs and serves matching signature metadata — this is expected and not an error, but is worth understanding for supply-chain verification purposes.

**Production usage example:** A regulated enterprise's standard developer and CI setup, where all provider (and often module, [§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md)) traffic is required to flow through an internally hosted, security-scanned mirror rather than directly to `registry.terraform.io` — both a compliance control and, often, the only path that works at all inside a restrictive network perimeter.

**Common errors:** A `provider_installation` block with no matching entry for a given provider's source address and no `direct {}` fallback block causes `init` to fail outright for that provider rather than falling back to the public registry — mirror configurations should usually include an explicit `direct {}` fallback (possibly excluding specific providers) if partial fallback to the public registry is intended.

## 6. Production Usage Notes

- **`plugin_cache_dir` does not eliminate the need for `.terraform.lock.hcl`.** The cache speeds up download/install; the lock file still governs exactly which version is selected and verified — the two mechanisms solve different problems (speed vs. reproducibility) and are not substitutes for each other.
- **CI environments almost always generate the CLI config file at job runtime** (via a setup step writing `$TF_CLI_CONFIG_FILE` or `~/.terraformrc` directly), rather than committing a static file, since credentials and mirror URLs often differ per environment and must never live in source control.
- **`TF_CLI_CONFIG_FILE` overrides the default file location entirely** — useful for testing a specific CLI configuration in isolation, or for CI runners that need a non-default, job-specific config path.
- **Provider installation method precedence matters**: explicit `dev_overrides` (used for local provider development/testing) take priority over everything else, followed by matching `provider_installation` block rules, in file order.

## 7. Security Considerations

- The default `credentials.tfrc.json` written by `terraform login` stores the token **in plain text** on disk — protect the file with normal OS file permissions and prefer short-lived tokens or a credentials helper backed by a proper secrets manager for any shared or CI environment.
- **Never commit `.terraformrc` or `credentials.tfrc.json` to version control** — both can contain long-lived registry tokens; treat them with the same handling discipline as any other credential file.
- A `credentials_helper` is a genuine improvement over static tokens specifically because it can fetch short-lived, dynamically-scoped credentials (e.g., via OIDC federation in CI) rather than a long-lived static secret sitting on disk indefinitely.
- Redirecting `provider_installation` to an internal mirror is itself a security control — but only as strong as that mirror's own integrity verification; an internal mirror that doesn't validate upstream provider checksums can become a supply-chain weak point rather than a strength.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Likely Cause                                                                         | Resolution Path                                                                                        |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------ |
| `init` works locally but fails to reach a private registry in CI        | CI runner has no `credentials` block or valid token configured                       | Generate/inject `.terraformrc` (or `credentials.tfrc.json`) at CI job start with a valid, scoped token |
| Provider installs are slow, re-downloading the same provider repeatedly | No `plugin_cache_dir` configured, so every project re-downloads independently        | Set `plugin_cache_dir` in the CLI config file, pointing at a shared, writable local directory          |
| `Error: Failed to install provider` when internal network mirror is set | Mirror doesn't have that provider/version, and no `direct {}` fallback is configured | Add a `direct {}` fallback block, or verify the mirror actually proxies/mirrors the needed provider    |
| Team members get inconsistent `init` behavior on the same repository    | Differing local `.terraformrc` files (one has a mirror override, another doesn't)    | Standardize CLI configuration via onboarding scripts/dotfiles rather than leaving it fully ad hoc      |
| `terraform login` fails or hangs on a headless server                   | No browser available to complete the interactive OAuth-style flow                    | Generate a token manually via the registry's UI and add a `credentials` block directly instead         |

## 9. Best Practices

- Set `plugin_cache_dir` on every developer machine and CI runner image as a default performance optimization — it has no downside for typical workflows.
- Generate CI's CLI configuration dynamically at job start from secrets, never commit a static `.terraformrc` with embedded tokens to any repository, including private ones.
- Prefer a `credentials_helper` backed by short-lived, dynamically-issued tokens over static long-lived tokens wherever the registry and CI platform support it.
- Standardize `provider_installation` mirror configuration via team onboarding tooling (a setup script, not tribal knowledge) so all engineers and CI runners resolve providers identically.

## 10. Common Anti-Patterns / Mistakes

- **Committing `.terraformrc` or `credentials.tfrc.json` to a repository** (even a private one) — an easy, common credential leak.
- **Assuming CLI configuration is per-project** and being confused when a setting from a completely unrelated repository's setup affects the current project — it's machine/user-scoped, always.
- **Manually copy-pasting long-lived tokens into `.terraformrc`** instead of using `terraform login` or a credentials helper, increasing the chance of accidental exposure and making rotation harder.
- **Configuring a network mirror with no fallback and no verification that it actually mirrors every needed provider**, causing confusing `init` failures that look like registry outages but are actually mirror gaps.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `.terraformrc` and a project's `.tf` files?"_
**Model answer:** `.tf` files declare a specific project's desired infrastructure and requirements (providers needed, backend, resources) and are checked into version control as part of that project. `.terraformrc` (or `terraform.rc` on Windows) is a personal, machine-wide file controlling how the Terraform CLI itself behaves on that machine — provider installation sources, local caching, registry authentication — and is never checked into any repository.
_What the interviewer is probing for:_ Basic awareness that CLI-level configuration exists separately from project configuration and isn't shared via Git.

**🎯 Intermediate:** _"What does `plugin_cache_dir` do, and why does a team with many separate Terraform repositories benefit from setting it?"_
**Model answer:** By default, each project's `.terraform/providers/` directory holds its own independent copy of every provider it uses — if ten repositories all use `hashicorp/aws`, that provider gets downloaded and stored ten separate times. `plugin_cache_dir` configures a single shared local directory that `init` checks first and populates once; subsequent `init` runs across any project needing the same provider version reuse the cached copy instead of re-downloading it, significantly speeding up `init` across a machine or CI image with many repositories.
_What the interviewer is probing for:_ Practical understanding of a genuinely useful, easy-to-overlook performance setting.

**🎯 Senior:** _"Your organization requires all Terraform provider installations to go through an internal, security-scanned mirror rather than the public registry. How would you implement and enforce this consistently across both developer laptops and CI?"_
**Model answer:** Configure a `provider_installation` block with a `network_mirror` pointing at the internal mirror in the CLI configuration file — on developer machines, distribute this via a standardized onboarding script or dotfiles repository rather than leaving each engineer to configure it manually (which reliably drifts); in CI, generate the same CLI configuration at job start from a pipeline template shared across all repositories, likely via `TF_CLI_CONFIG_FILE` pointing at a file written by an early pipeline step. Enforcement beyond "set it and hope" typically means also restricting outbound network access from CI runners (and ideally developer machines, via network policy) so that the public registry isn't reachable at all — making the mirror not just the default path but the only path, which is a much stronger guarantee than CLI configuration alone.
_What the interviewer is probing for:_ Whether the candidate thinks about consistent enforcement across environments, not just knowing the syntax of the `provider_installation` block.

**🎯 Architect:** _"Design the credential-handling strategy for Terraform CLI configuration across a large organization's fleet of CI runners, balancing security and operability."_
**Model answer:** Avoid static, long-lived tokens embedded in any persisted `.terraformrc` file wherever possible. Prefer a `credentials_helper` executable, deployed as part of the standard CI runner image, that fetches short-lived tokens dynamically at job runtime — ideally via a federated identity mechanism (OIDC token exchange with the private registry or Terraform Cloud, mirroring how many teams already do this for cloud provider credentials, [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)) rather than a static secret pulled from a vault and written to disk. Where a helper isn't feasible, generate the CLI config file fresh at the start of every job from a pipeline-injected secret, write it to an ephemeral runner filesystem that's destroyed after the job, and never bake credentials into a reusable runner image. Rotate any necessarily-static tokens on a defined schedule, and audit registry access logs for anomalous patterns. The overarching principle: CLI configuration credentials should be short-lived, dynamically issued, and scoped as narrowly as the registry/token model allows, exactly mirroring the least-privilege posture applied to cloud provider credentials elsewhere in the pipeline.
_What the interviewer is probing for:_ Enterprise-scale credential lifecycle thinking — short-lived over static, dynamic over hardcoded, and consistency with the org's broader credential strategy rather than treating Terraform CLI config as a special, isolated case.

## 12. Common Misconceptions

1. **"`.terraformrc` configures cloud provider credentials like AWS keys."** It doesn't — cloud provider authentication ([§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md)) is handled separately, via provider configuration blocks or standard cloud SDK credential chains; `.terraformrc` is specifically about the Terraform CLI's own behavior (registries, caching, mirrors).
2. **"CLI configuration is project-specific and travels with a repository."** It's machine/user-scoped and deliberately excluded from version control — it applies uniformly to every project a given user runs on that machine.
3. **"`plugin_cache_dir` replaces the need for `.terraform.lock.hcl`."** They solve different problems — caching speeds up downloads of already-decided versions; the lock file is what decides and guarantees which versions are used in the first place.
4. **"`terraform login` is the only way to authenticate to a private registry."** It's the interactive, browser-based convenience path; manually writing a `credentials` block or using a `credentials_helper` are equally valid, and often necessary in headless/CI environments.

## 13. 🔑 Key Takeaways

- The CLI configuration file (`.terraformrc`/`terraform.rc`, or `TF_CLI_CONFIG_FILE`) is machine/user-scoped, controls CLI-wide behavior, and is never checked into version control.
- `plugin_cache_dir` is a high-value, low-effort setting that meaningfully speeds up `init` across multiple projects sharing providers.
- `credentials` blocks and `credentials_helper` govern registry authentication; prefer dynamically-issued, short-lived tokens via a helper over static long-lived tokens where possible.
- `provider_installation` with `network_mirror` redirects provider downloads to an internal source — essential for air-gapped/regulated environments, and should be standardized across both developer machines and CI, not left to individual configuration.
- This file is entirely distinct from cloud provider authentication (AWS/Azure/GCP credentials) — don't conflate the two authentication layers.

## 14. Related Concepts & What's Next

[§8](../Part2/Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md)–[§10](../Part2/Section-10-Part2-The-Terraform-Registry-and-Sourcing-Providers.md) cover the provider plugin model, version constraints, and the public Terraform Registry that CLI configuration customizes installation behavior for. [§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md) covers cloud provider authentication patterns, the separate authentication layer this section explicitly distinguishes from. [§87](../Part12/Section-87-Part12-Private-Module-Registry-and-Private-Provider-Registry.md) covers Terraform Cloud's private module and provider registries, the most common real-world reason teams configure `credentials` blocks. Next, [§30](./Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md) covers `terraform show`, `terraform output`, and machine-readable `-json` output — the commands used to extract and consume results from state and plans, often by exactly the kind of automation this section's credentials-helper patterns support.

**Next Section:** [§30](./Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md) — `Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md`
