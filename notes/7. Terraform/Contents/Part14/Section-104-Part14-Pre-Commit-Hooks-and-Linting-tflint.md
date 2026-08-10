# Section 104 (Part 14): Pre-Commit Hooks and Linting (tflint)

## 1. Definition

**Plain language:** Every check discussed so far in this Part — validate, plan, tests, policy — runs in CI, meaning an engineer only finds out about a formatting mistake or a linting violation after pushing and waiting for a pipeline. Pre-commit hooks and linting move a subset of those cheap, fast checks to the moment _before_ a commit is even created locally, so the feedback loop shrinks from minutes (CI) to seconds (a git hook on the developer's own machine).

**Precise definition:** A **pre-commit hook** is a script that Git runs automatically immediately before a commit is finalized, capable of blocking the commit if the script exits non-zero; the **pre-commit framework** (the `pre-commit` Python tool, distinct from but often conflated with "a pre-commit hook" generically) manages a declarative `.pre-commit-config.yaml` file listing which checks to run, installing and versioning each check's tooling automatically per-repository. **tflint** is a Terraform-specific linter — distinct from `terraform validate` ([§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md), which only checks internal HCL/schema consistency) — that checks for provider-specific best-practice violations, deprecated syntax, unused declarations, and, via plugins, cloud-provider-specific correctness issues (e.g., an invalid AWS instance type string that would only otherwise be caught at `plan` or `apply` time against a real API).

> 💡 **Tip:** `terraform validate` and `tflint` are frequently confused as redundant, but they check different things. `validate` confirms the configuration is internally consistent — correct HCL, correct argument types, resolvable references — using only the provider schema Terraform already has locally. `tflint` goes further: it flags things that are _valid_ Terraform but still wrong or risky — an unused variable declaration, a deprecated argument that still technically works, or (via the AWS/Azure/GCP plugins) a string that isn't a real instance type in that specific provider's catalog, something `validate` structurally cannot know because it doesn't maintain a live catalog of valid values.

## 2. Why This Matters

- **Shifts feedback left from minutes to seconds.** A formatting or linting violation caught in a pre-commit hook costs the developer a few seconds locally; the same violation caught only in CI costs a push, a wait, a failed pipeline, a fix, and a re-push — a meaningfully worse feedback loop repeated across every contributor on every PR.
- **Keeps CI focused on checks that genuinely require CI-scale resources.** Formatting, linting, and basic validation don't need real cloud credentials or a shared remote backend — running them locally first means CI's more expensive stages (plan, integration tests) aren't wasted on PRs that fail on a trivial `fmt` violation.
- **tflint catches a class of bugs `validate` and `plan` both miss until much later.** An unused variable or a deprecated-but-still-valid argument doesn't break `validate` or even `plan` — it's a maintainability and correctness signal that only a dedicated linter surfaces, often well before it becomes a real production issue.
- **Consistent formatting removes an entire category of PR review noise.** `terraform fmt` and its pre-commit enforcement eliminate "please reformat this" review comments entirely, letting reviewers focus on substance (the plan diff, the actual logic) instead of whitespace.
- **A shared `.pre-commit-config.yaml` makes the standard reproducible and enforceable across a whole team**, rather than depending on each individual remembering to run `terraform fmt` and `tflint` manually before every commit.

## 3. Prerequisites and Dependencies

This section builds on [§27](../Part4/Section-27-Part4-terraform-validate-and-terraform-fmt.md)'s introduction of `terraform fmt` and `terraform validate` as CLI commands, and on [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)'s deeper treatment of `validate` — this section adds the pre-commit automation layer and the complementary `tflint` tool on top of both. It connects forward to [§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)'s CI pipelines: pre-commit hooks are a local, opt-in-by-default-but-bypassable first line of defense, while the same `fmt -check`/`validate`/`tflint` checks re-run in CI as the actual enforced gate, since a local hook can always be skipped with `git commit --no-verify`.

## 4. Architecture / Conceptual Diagram

```text
   LOCAL (pre-commit hook)                    CI (§102, cannot be bypassed)

   git commit                                 git push → PR opened
        │                                            │
        ▼                                            ▼
   .pre-commit-config.yaml hooks run:         Same checks re-run as a
   1. terraform_fmt   (auto-fixes)            required status check:
   2. terraform_validate                      - terraform fmt -check
   3. terraform_tflint                        - terraform validate
   4. terraform_docs (optional, regenerates   - tflint
      README tables from variables/outputs)        │
        │                                          ▼
        ▼                                     PLUS everything only CI can
   Any hook failure blocks the commit         run: plan, tests (§100),
   from being created at all — fix and        policy checks (§101)
   re-attempt                                        │
        │                                            ▼
        ▼                                     Required status checks must
   `git commit --no-verify` bypasses          pass before merge — this is
   ALL local hooks (escape hatch, not          the actual enforcement point,
   a substitute for CI enforcement)            since local hooks are
                                                skippable by design
```

- Local hooks exist purely for fast feedback — they are never the actual security/quality boundary, because any developer can bypass them with `--no-verify` or simply not install them.
- CI re-running the identical checks (`fmt -check`, `validate`, `tflint`) is what makes the standard actually enforced — the pre-commit layer is a convenience that reduces how often CI catches these specific, cheap violations, not a replacement for CI catching them.
- tflint sits at the local layer because it's fast and requires no cloud credentials (aside from provider plugins optionally fetching a cached ruleset), making it cheap enough to run on every single commit without noticeable friction.

## 5. Hands-On

### 5.1 A `.pre-commit-config.yaml` for Terraform

**Purpose:** Declare the standard set of fast, local checks every contributor's commits run through automatically, using the widely-adopted `antonbabenko/pre-commit-terraform` hook collection.

**Syntax:**

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/antonbabenko/pre-commit-terraform
    rev: v1.92.0
    hooks:
      - id: terraform_fmt
      - id: terraform_validate
      - id: terraform_tflint
        args:
          - --args=--config=.tflint.hcl
      - id: terraform_docs
        args:
          - --hook-config=--path-to-file=README.md
          - --hook-config=--add-to-existing-file=true
```

**Example usage and expected output:**

```bash
$ pre-commit install         # one-time setup per clone, wires the git hook
pre-commit installed at .git/hooks/pre-commit

$ git commit -m "Add subnet resource"
terraform_fmt............................................................Passed
terraform_validate.......................................................Passed
terraform_tflint..........................................................Failed
- hook id: terraform_tflint
- exit code: 3

main.tf
  1:1  warning  variable "region" is declared but not used (terraform_unused_declarations)
```

**Production usage example:** This exact config, checked into the repository root, is the standard onboarding step for new contributors to any Terraform monorepo — `pre-commit install` is typically documented as the very first command in the repo's contribution guide, right after cloning.

**Common errors:** Forgetting to run `pre-commit install` after cloning means the hooks are declared in the repo but never actually wired into the local `.git/hooks/` directory — the config file existing is not sufficient; each contributor's clone needs the one-time `install` step.

### 5.2 tflint: Catching a Provider-Specific Mistake `validate` Cannot

**Purpose:** Demonstrate a class of error tflint's AWS plugin catches that `terraform validate` structurally cannot, because it requires a live catalog of valid values rather than just schema shape.

**Syntax:**

```hcl
# .tflint.hcl
plugin "aws" {
  enabled = true
  version = "0.31.0"
  source  = "github.com/terraform-linters/tflint-ruleset-aws"
}

rule "terraform_unused_declarations" {
  enabled = true
}

rule "terraform_deprecated_interpolation" {
  enabled = true
}
```

```hcl
# main.tf — a typo'd, non-existent instance type
resource "aws_instance" "app" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micrio"   # typo: not a real AWS instance type
}
```

**Example usage and expected output:**

```bash
$ tflint --init      # downloads the AWS ruleset plugin
$ tflint

2 issue(s) found:

Error: "t3.micrio" is an invalid value as instance_type (aws_instance_invalid_type)

  on main.tf line 3:
   3:   instance_type = "t3.micrio"

Reference: https://github.com/terraform-linters/tflint-ruleset-aws
```

**Production usage example:** Catching this locally, in seconds, before a commit is even created, avoids what would otherwise be a `plan`-time or `apply`-time failure discovered only after a full CI round-trip — for a large team, this class of catch across hundreds of commits per week represents real, cumulative time saved.

**Common errors:** Running `tflint` without first running `tflint --init` fails to load any provider-specific plugin rules (the AWS/Azure/GCP rulesets are downloaded separately from tflint core) — the base `tflint` binary alone only runs Terraform-language-level rules, not provider-catalog checks.

### 5.3 Enforcing Both Locally and in CI (Redundant by Design)

**Purpose:** Show the intentional duplication between the local pre-commit hook and the CI job, since local hooks alone are not an enforceable gate.

**Syntax:**

```yaml
# excerpt from .github/workflows/terraform-plan.yml — same checks, CI-enforced
- name: Terraform fmt (CI-enforced, cannot be bypassed)
  run: terraform fmt -check -recursive

- name: tflint (CI-enforced)
  run: |
    curl -s https://raw.githubusercontent.com/terraform-linters/tflint/master/install_linux.sh | bash
    tflint --init
    tflint --minimum-failure-severity=warning
```

**Example usage and expected output:**

```text
$ gh pr checks 55
Terraform Plan / fmt-and-lint   fail   12s

tflint reported 1 issue at warning severity or above; failing per
--minimum-failure-severity=warning
```

**Production usage example:** A contributor who commits with `--no-verify` (skipping their local hooks, deliberately or accidentally) is still caught here — the PR simply cannot merge until the same checks pass in CI, which is the actual, unbypassable enforcement point.

**Common errors:** Relying solely on pre-commit hooks and never re-running the same checks in CI is the single most common mistake here — since `--no-verify` and "forgot to run `pre-commit install`" are both trivially possible, a team that treats local hooks as sufficient enforcement will eventually merge a PR that violates the standard.

## 6. Production Usage Notes

- **Pin hook and plugin versions explicitly** (`rev: v1.92.0`, `version = "0.31.0"` above) — unpinned "latest" hook versions can introduce new rules or behavior changes that suddenly start failing commits that passed yesterday, with no corresponding code change to explain it.
- **`terraform_docs` as a pre-commit hook keeps module README tables (input/output documentation) synchronized automatically** with the actual `variables.tf`/`outputs.tf` — a common, high-value addition for module repositories ([§56](../Part8/Section-56-Part8-Module-Structure-and-Conventions.md)) specifically, since stale module documentation is a frequent source of downstream consumer confusion.
- **CI should run the identical tool versions as the pre-commit config**, ideally by referencing the same pinned versions in both places (or generating one from the other), to avoid a "passes locally, fails in CI" or vice versa discrepancy caused purely by version drift between the two layers.

## 7. Security Considerations

- Pre-commit hooks execute arbitrary code on a developer's local machine sourced from a third-party repository (`antonbabenko/pre-commit-terraform` and tflint's plugin ecosystem) — pinning to a specific reviewed revision/version, rather than a floating branch reference, avoids supply-chain risk from a compromised upstream hook repository silently changing behavior.
- tflint's provider-specific plugins are downloaded and executed locally; sourcing them only from the official `terraform-linters` GitHub organization (as shown) rather than an unverified fork avoids introducing an unreviewed binary into every contributor's local environment.
- Because pre-commit hooks are bypassable, they must never be the sole enforcement mechanism for a security-relevant check (e.g., a secrets-scanning hook) — security-critical checks belong in CI (or better, as a required status check per [§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)), with the local hook treated purely as an early, optional convenience.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                | Likely Cause                                                                                                                                          | Resolution Path                                                                                          |
| ---------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Pre-commit hooks never run, despite `.pre-commit-config.yaml` existing | `pre-commit install` was never run in this local clone                                                                                                | Run `pre-commit install` once per clone to wire the git hook                                             |
| tflint reports zero issues even for an obviously invalid instance type | `tflint --init` was never run, so the AWS/Azure/GCP plugin ruleset isn't loaded — only core language rules are active                                 | Run `tflint --init` before `tflint`, and confirm the plugin block in `.tflint.hcl`                       |
| A commit that failed pre-commit locally still shows up in a merged PR  | Contributor bypassed hooks with `git commit --no-verify`, and CI either wasn't configured to re-run the same checks or wasn't a required status check | Add the identical checks as a required CI status check; local hooks alone are not sufficient enforcement |
| Pre-commit hook passes locally but the same check fails in CI          | Hook/tool version drift between the locally cached pre-commit environment and CI's installed version                                                  | Pin identical versions in both `.pre-commit-config.yaml` and the CI job definition                       |

## 9. Best Practices

- Document `pre-commit install` as a mandatory first step in the repository's contribution guide, and consider a CI check that fails if evidence suggests hooks weren't run (e.g., unformatted code reaching a PR).
- Pin all hook and linter plugin versions explicitly, and keep local and CI tool versions in sync deliberately rather than letting them drift independently.
- Re-run every pre-commit check as an unbypassable CI status check — treat local hooks as a convenience layer, never the actual enforcement boundary.

## 10. Common Anti-Patterns / Mistakes

- **Treating pre-commit hooks as sufficient enforcement on their own**, with no equivalent CI check — `--no-verify` and unset-up local environments both defeat this silently.
- **Running `tflint` without provider plugins initialized**, giving a false sense of coverage — core tflint alone catches Terraform-language issues (unused declarations, deprecated syntax) but not provider-catalog correctness issues like invalid instance types.
- **Letting `.pre-commit-config.yaml` hook versions float unpinned**, causing unrelated commits to suddenly start failing (or silently stop catching issues) when an upstream hook or ruleset changes behavior with no corresponding local code change.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `terraform validate` and `tflint`?"_
**Model answer:** `terraform validate` checks that a configuration is internally consistent — correct HCL syntax, correct argument names/types against the provider schema, resolvable references — using only what Terraform already has locally. `tflint` is a separate, dedicated linter that goes further: it flags things that are technically valid Terraform but still risky or wrong, like unused variable declarations, deprecated syntax that still works, or, via provider-specific plugins, values like an instance type string that isn't real in that cloud provider's actual catalog — something `validate` has no way to check since it doesn't maintain a live list of valid values.
_What the interviewer is probing for:_ Whether the candidate understands these as complementary, not redundant, tools.

**🎯 Intermediate:** _"Why aren't pre-commit hooks sufficient on their own as a quality gate for a team's Terraform repository?"_
**Model answer:** Pre-commit hooks only run if a contributor has installed them locally (`pre-commit install`) and doesn't bypass them with `git commit --no-verify` — both are entirely under the individual contributor's control, making hooks a convenience for fast local feedback, not an enforceable gate. The actual enforcement has to happen somewhere a contributor can't opt out of, which is why the same checks (fmt, validate, tflint) should also run as a required CI status check that blocks merging regardless of what happened locally.
_What the interviewer is probing for:_ Recognition that local automation and enforced automation are different things, and that "we have pre-commit hooks" alone doesn't answer "how do you guarantee code quality standards are met."

**🎯 Senior:** _"A team notices that some PRs pass their local pre-commit hooks but fail the equivalent tflint check in CI. What's the likely cause, and how do you prevent it going forward?"_
**Model answer:** This is almost always a version-drift problem — the locally cached pre-commit environment (managed by the `pre-commit` tool's own virtualenv/cache) is running a different tflint version or plugin ruleset version than what CI installs fresh on each run. The fix is to pin exact versions in both places and keep them in sync deliberately — ideally by having the CI job read the same pinned version string from `.pre-commit-config.yaml` (or a shared version file) rather than maintaining two independently-updated version pins that inevitably diverge over time.
_What the interviewer is probing for:_ Practical diagnosis of a common real-world CI/local parity issue, and a concrete prevention strategy (single source of truth for versions), not just "update the versions."

**🎯 Architect:** _"You're introducing pre-commit hooks and tflint across 60 existing Terraform repositories with years of accumulated technical debt — many will fail dozens of lint violations on day one if the checks are made hard-blocking immediately. How do you roll this out without stalling every team's ongoing work?"_
**Model answer:** I'd separate "introducing the tooling" from "making it a hard gate," similar to the advisory-first policy rollout pattern from [§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md). First, I'd land `.pre-commit-config.yaml` and the equivalent CI job in every repository but configure tflint (and any other newly-introduced check) to report violations without failing the build initially — either via a lenient `--minimum-failure-severity` threshold or by running the check as non-required/informational in CI. I'd then generate a baseline report per repository of existing violations, and either bulk-fix the cheap, mechanical ones immediately (a scripted `terraform fmt -recursive` pass across all 60 repos is usually safe to land in one PR per repo with minimal review needed) or file tracked remediation issues for anything requiring judgment. Once a repository's existing violations are at or near zero, I'd flip that specific repository's CI job to hard-blocking as a required status check — repo by repo, not organization-wide in one cutover — so teams aren't suddenly blocked mid-sprint by a standard introduced after their code was already written. Throughout, I'd keep the local pre-commit hooks non-blocking-by-default too (matching whatever the CI gate currently enforces) so the two layers stay consistent rather than the local hook being stricter than what's actually enforced.
_What the interviewer is probing for:_ Whether the candidate can design a low-friction, incremental rollout for a retroactive quality standard across many existing repositories — a realistic large-scale platform-engineering problem, mirroring the policy-rollout thinking from [§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md) but applied to linting specifically.

## 12. Common Misconceptions

1. **"tflint is redundant with `terraform validate` since both check the configuration."** They check fundamentally different things — schema/reference consistency (`validate`) versus best-practice and provider-catalog correctness (`tflint`) — and finding one clean doesn't imply the other is.
2. **"Installing `.pre-commit-config.yaml` in the repo is enough — contributors will pick it up automatically."** Each clone requires an explicit one-time `pre-commit install` to actually wire the git hook; the config file alone does nothing until that step runs.
3. **"Pre-commit hooks are a security control."** They're trivially bypassable (`--no-verify`, or simply not installing them) and should never be relied on as the enforcement point for anything security-relevant — that belongs in CI.
4. **"tflint catches everything `plan`/`apply` would eventually catch, just earlier."** tflint's provider plugins check against a maintained catalog of known-valid values and patterns, but they can lag behind a provider's actual current API — a genuinely new, valid value not yet in the plugin's ruleset can still pass tflint and only be validated at real `plan`/`apply` time.

## 13. 🔑 Key Takeaways

- Pre-commit hooks move fast, cheap checks (fmt, validate, tflint) to the moment before a local commit, shrinking feedback loops from CI-round-trip minutes to local seconds.
- tflint is complementary to, not redundant with, `terraform validate` — it catches best-practice and provider-catalog issues validate structurally cannot see.
- tflint requires `tflint --init` to load provider-specific plugin rulesets; core tflint alone only checks Terraform-language-level issues.
- Local pre-commit hooks are always bypassable and must be mirrored by identical, unbypassable checks in CI to serve as real enforcement.
- Version pinning across both the local pre-commit config and CI job definitions prevents "passes locally, fails in CI" drift.

## 14. Related Concepts & What's Next

[§27](../Part4/Section-27-Part4-terraform-validate-and-terraform-fmt.md) and [§99](./Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md) cover `terraform validate` and `fmt` as the CLI-level checks this section automates and complements with tflint. [§102](./Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md) covers the CI pipelines where the same checks must be re-enforced, since pre-commit hooks alone are bypassable. [§101](./Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)'s advisory-first policy rollout pattern is directly analogous to the incremental linting rollout discussed in this section's architect-level interview answer. [§105](./Section-105-Part14-Automated-Testing-Pyramids-for-IaC.md) places pre-commit/linting formally at the base of the complete IaC testing pyramid.

**Next Section:** [§105](./Section-105-Part14-Automated-Testing-Pyramids-for-IaC.md) — `Section-105-Part14-Automated-Testing-Pyramids-for-IaC.md`
