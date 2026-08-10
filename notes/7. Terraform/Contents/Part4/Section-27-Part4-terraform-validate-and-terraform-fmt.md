# Section 27 (Part 4): terraform validate and terraform fmt

## 1. Definition

**Plain language:** `terraform validate` checks whether your configuration is internally correct — valid HCL syntax, correct argument names, correctly-typed references — without needing any credentials or talking to any real infrastructure. `terraform fmt` rewrites your `.tf` files into Terraform's canonical formatting style (consistent indentation, alignment, spacing) so every file in a codebase looks the same regardless of who wrote it.

**Precise definition:** `terraform validate` performs **static, local, offline correctness checking** of a configuration: it verifies HCL syntax is well-formed, that all required arguments are present, that argument and attribute types match what the provider schema expects (using cached provider schema from `.terraform/` — meaning it does require a prior `init`), and that internal references (variables, resources, modules) resolve to something declared. It does **not** check whether the configuration will actually succeed against a real provider API, and it does not require provider credentials. `terraform fmt` is a **deterministic source-code formatter**: it rewrites `.tf` and `.tfvars` files in place to match HashiCorp's canonical style — it never changes behavior, only whitespace, indentation, and alignment.

> 💡 **Tip:** `validate` and `fmt` are the two cheapest, fastest checks in the entire Terraform workflow — both run in well under a second on typical configurations and require no network access (`fmt`) or only local provider schema (`validate`). There is no excuse for skipping either before every commit; both belong in pre-commit hooks ([§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)), not just CI.

## 2. Why This Matters

- **`validate` catches an entire class of errors before they ever reach `plan`**, which itself requires provider credentials and network access — failing fast on a typo saves real time and avoids partially-authenticated, confusing failure states.
- **`fmt` eliminates an entire category of pointless code-review discussion** ("please fix the indentation here") by making formatting a machine decision, not a human one — every serious Terraform codebase enforces it.
- **`fmt -check` (rather than `fmt` itself) is what CI actually runs** — the distinction between "format my files" and "verify my files are already formatted, fail if not" is a common point of confusion for people new to CI integration.
- **Neither command touches state or real infrastructure**, making them safe to run constantly, in any environment, by anyone, with zero risk — an important property when onboarding new team members or contributors who don't yet have cloud credentials.
- **`validate` is explicitly listed as a testing strategy in its own right** ([§99](../Part14/Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md)) — for many simple configurations, `validate` plus a policy-as-code check is a meaningful first tier of an IaC test pyramid ([§105](../Part14/Section-105-Part14-Automated-Testing-Pyramids-for-IaC.md)) before anything resource-specific.

## 3. Prerequisites and Dependencies

`terraform validate` requires a successfully initialized working directory ([§24](./Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md)) since it consults cached provider schemas; `terraform fmt` has no such requirement and works on any `.tf` file, initialized or not. Basic HCL syntax ([§15](../Part3/Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md)) and file structure conventions ([§16](../Part3/Section-16-Part3-Terraform-File-Structure-and-Conventions.md)) are useful context for understanding what `fmt` normalizes. [§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md) (pre-commit hooks and tflint) and [§99](../Part14/Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md) (plan-based testing strategies) build directly on both commands as the foundation of a testing/linting pipeline.

## 4. Architecture / Conceptual Diagram

```text
                    Local, Offline Checks (no credentials, no network)
       ┌────────────────────────────────────────────────────────────┐
       │                                                            │
       ▼                                                            ▼
terraform fmt                                          terraform validate
(style / whitespace)                                (syntax + internal correctness)
       │                                                            │
       ▼                                                            ▼
- Consistent indentation                             - HCL parses correctly
- Aligned `=` signs                                   - Required arguments present
- Canonical block spacing                             - Argument types match schema
- No behavior change, ever                            - References resolve
       │                                                    (variables, resources,
       ▼                                                     modules, locals)
  Rewritten .tf files                                        │
  (or, with -check, a                                        ▼
   pass/fail exit code only)                        Pass/fail + specific error
                                                       locations (file:line)
       │                                                            │
       └───────────────────┬────────────────────────────────────────┘
                            ▼
              Safe, cheap gate BEFORE `terraform plan`
              (which requires credentials + network + state)
```

- **`fmt` never changes semantics** — a formatted and unformatted version of the same file produce identical plans; only `fmt`'s cosmetic output differs.
- **`validate` does not catch provider-side errors** — e.g., an invalid AMI ID that's syntactically a valid string will pass `validate` but fail at `plan` or `apply` time when the provider actually checks it against real infrastructure.

## 5. Hands-On

### 5.1 terraform validate — Basic Check

**Purpose:** Confirm a configuration is syntactically correct and internally consistent before attempting a plan.

**Syntax:**

```bash
terraform validate [options]
```

**Example usage and expected output (success):**

```bash
$ terraform validate
Success! The configuration is valid.
```

**Example usage and expected output (failure):**

```bash
$ terraform validate

Error: Unsupported argument

  on main.tf line 14, in resource "aws_instance" "web":
  14:   instance_typeee = "t3.micro"

An argument named "instance_typeee" is not expected here.

Error: Reference to undeclared resource

  on outputs.tf line 3, in output "web_ip":
   3:   value = aws_instance.wb.public_ip

A managed resource "aws_instance" "wb" has not been declared in the root
module.
```

**Production usage example:** The first step of nearly every CI pipeline's Terraform stage ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)), run immediately after `terraform init -backend=false` (skipping backend setup since no state access is needed for a pure syntax check) — cheap, fast, and catches typos before any expensive plan against real infrastructure is attempted.

**Common errors:**

```text
Error: Could not load plugin

Plugin reinitialization required. Please run "terraform init".
```

`validate` needs cached provider schema from `.terraform/` to check argument types against — running it in a directory that hasn't been `init`-ed (or was `init`-ed with `-backend=false` but never got providers installed) fails immediately with this message.

### 5.2 terraform validate -json

**Purpose:** Produce machine-readable validation results for CI tooling or editor integrations to parse programmatically.

**Syntax:**

```bash
terraform validate -json
```

**Example usage and expected output:**

```bash
$ terraform validate -json
{
  "format_version": "1.0",
  "valid": false,
  "error_count": 1,
  "warning_count": 0,
  "diagnostics": [
    {
      "severity": "error",
      "summary": "Unsupported argument",
      "detail": "An argument named \"instance_typeee\" is not expected here.",
      "range": {
        "filename": "main.tf",
        "start": { "line": 14, "column": 3 },
        "end": { "line": 14, "column": 18 }
      }
    }
  ]
}
```

**Production usage example:** CI systems that annotate pull requests with inline error comments at the exact file/line parse this JSON structure directly rather than scraping human-readable text output — the same machine-readable pattern covered fully for `plan`/`show` in [§30](./Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md).

**Common errors:** Piping `-json` output through a tool expecting a single top-level array rather than an object will fail — the top-level structure is always an object with a `diagnostics` array field, not a bare array.

### 5.3 terraform fmt — Rewrite in Place

**Purpose:** Normalize formatting across all `.tf` files in the current directory (and recursively, with `-recursive`).

**Syntax:**

```bash
terraform fmt [options] [DIR]
```

**Example usage and expected output:**

```bash
$ terraform fmt -recursive
main.tf
modules/vpc/variables.tf
modules/vpc/outputs.tf
```

Terraform prints the relative path of every file it actually modified; files already correctly formatted are silently skipped and not listed.

**Production usage example:** Wired into a pre-commit hook ([§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)) or editor "format on save" integration so formatting is corrected automatically and continuously, rather than accumulating as a batch of unrelated whitespace changes discovered later in review.

**Common errors:** Running `fmt` on a directory containing generated or vendored `.tf` files (e.g., from a code generator) that intentionally use non-standard formatting for a reason can unexpectedly rewrite them — scope `fmt` invocations (or use `.terraformignore`-style directory targeting) deliberately in codebases with generated Terraform code.

### 5.4 terraform fmt -check — CI-Friendly Verification

**Purpose:** Verify files are already correctly formatted without modifying anything, returning a non-zero exit code if not — the form CI pipelines actually use.

**Syntax:**

```bash
terraform fmt -check -recursive -diff
```

**Example usage and expected output (unformatted files found):**

```bash
$ terraform fmt -check -recursive -diff
main.tf
--- old/main.tf
+++ new/main.tf
@@ -10,7 +10,7 @@
 resource "aws_instance" "web" {
-  ami           = "ami-0c55b159cbfafe1f0"
-  instance_type    = "t3.micro"
+  ami           = "ami-0c55b159cbfafe1f0"
+  instance_type = "t3.micro"
 }

$ echo $?
3
```

`fmt -check` exits `0` if everything is already formatted, and a non-zero code (files listed, nothing modified) if anything needs reformatting — exactly the semantics a CI gate needs.

**Production usage example:** A dedicated "lint" job in CI that runs `terraform fmt -check -recursive` and fails the pipeline (without silently auto-fixing) if any file is unformatted — forcing the formatting fix to happen locally and be committed, keeping CI purely a verification gate rather than a code-modifying step.

**Common errors:** Confusing `fmt` (which modifies files) with `fmt -check` (which only reports) and accidentally having CI silently rewrite and even auto-commit formatting changes — CI should almost always use `-check` and fail the build, leaving the actual fix to a local `terraform fmt` run by a human.

## 6. Production Usage Notes

- **Run `validate` after `init` but before `plan`** in any pipeline — it's a strictly cheaper filter that should reject obviously broken configurations before the more expensive, credentialed `plan` step runs at all.
- **`fmt` has zero risk of changing behavior** — it is always safe to run and commit, unlike almost every other Terraform command; there's no reason to be cautious about it the way you'd be about `apply` or `destroy`.
- **`validate` is configuration-only** — it cannot catch issues that only manifest with specific variable values (e.g., a `validation` block failing for a particular input, [§44](../Part6/Section-44-Part6-Variable-Validation-Rules-and-Custom-Error-Messages.md)) unless those values are supplied; it validates structure and type-correctness, not business logic.
- **Neither command is a substitute for `plan`.** A configuration can pass both and still fail at `plan` or `apply` time due to real provider-side constraints (invalid resource identifiers, quota limits, permission errors) that only surface once Terraform actually talks to the provider.

## 7. Security Considerations

- Both commands are safe to run with zero credentials and no network access to the target infrastructure, making them ideal early gates in a pipeline before any privileged credentials are even loaded into the job's environment — a meaningful blast-radius reduction for the earliest pipeline stages.
- `validate` does require provider schema, which does come from a local `.terraform/` cache populated by `init` — that `init` step itself may need registry access (public or private, [§29](./Section-29-Part4-CLI-Configuration-terraformrc-Config-Blocks-Credentials-Helpers.md)) but not infrastructure credentials, an important distinction when scoping CI job permissions.
- `fmt` operates purely on local files and has no security surface of its own beyond normal file-write permissions.

## 8. Common Troubleshooting Scenarios

| Symptom                                                 | Likely Cause                                                                      | Resolution Path                                                                                                                                                                                                                                                                              |
| ------------------------------------------------------- | --------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `terraform validate` fails with "Could not load plugin" | Working directory hasn't been `init`-ed, or `.terraform/` cache is stale          | Run `terraform init` (or `init -backend=false` if only validating, no state access needed)                                                                                                                                                                                                   |
| `validate` passes locally but `plan` fails in CI        | `validate` doesn't check provider-side constraints (quotas, invalid IDs, auth)    | Expected — `validate` is a syntax/structure gate, not a full correctness guarantee; investigate `plan`'s specific error                                                                                                                                                                      |
| `fmt -check` fails in CI but files look fine locally    | Different Terraform CLI versions format slightly differently between local and CI | Pin the Terraform CLI version consistently everywhere ([§5](../Part1/Section-05-Part1-Installation-and-Setup-tfenv-package-managers-version-pinning.md), [§110](../Part15/Section-110-Part15-Versioning-Strategy-Terraform-Core-Providers-and-Modules.md)) so formatting rules match exactly |
| `fmt` rewrites a generated/vendored file unexpectedly   | `fmt -recursive` scanned a directory not meant to be hand-edited or reformatted   | Scope `fmt` invocations to specific directories, or exclude generated paths from the recursive scan                                                                                                                                                                                          |
| `validate` reports a reference error that seems wrong   | A module's variable/output isn't actually being passed the way you assume         | Trace the exact module boundary ([§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md)); `validate` errors always include an exact file:line locator                                                                                                                                 |

## 9. Best Practices

- Run `terraform fmt` (not `-check`) locally, and commit the result, before ever pushing — let CI's `fmt -check` be a safety net, not the primary formatting mechanism.
- Wire `validate` and `fmt -check` into pre-commit hooks ([§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md)) so violations are caught before they even reach a PR, not just in CI minutes later.
- Pin the exact Terraform CLI version across local dev and CI ([§110](../Part15/Section-110-Part15-Versioning-Strategy-Terraform-Core-Providers-and-Modules.md)) — formatting output can differ subtly between versions, causing confusing `fmt -check` CI failures that don't reproduce locally.
- Treat a passing `validate` as a necessary, not sufficient, condition — it never replaces reviewing an actual `plan`.

## 10. Common Anti-Patterns / Mistakes

- **Skipping `validate` locally and relying on CI to catch syntax errors** — wastes a full CI cycle on errors that take under a second to catch locally.
- **Running `fmt` (not `-check`) inside CI and having it auto-commit changes back to the branch** — turns CI into a code-modifying step, which is confusing, can trigger infinite pipeline loops, and hides formatting drift from the author.
- **Treating a passing `validate` as proof the configuration will apply cleanly** — it only proves structural/type correctness, not that the real infrastructure operation will succeed.
- **Not pinning CLI versions and being surprised when `fmt -check` disagrees between a developer's machine and CI.**

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `terraform validate` and `terraform plan`?"_
**Model answer:** `validate` checks that the configuration is syntactically correct and internally consistent (right argument names, right types, references that resolve) without touching real infrastructure or needing credentials. `plan` goes further — it needs provider credentials, talks to real infrastructure to refresh state, and computes an actual diff of what would change. A configuration can pass `validate` and still fail at `plan` if, say, a resource references infrastructure that doesn't actually exist.
_What the interviewer is probing for:_ Understanding the layered nature of Terraform's checks, from cheap/local to expensive/live.

**🎯 Intermediate:** _"Why does CI typically use `terraform fmt -check` instead of `terraform fmt`?"_
**Model answer:** `terraform fmt` rewrites files in place; running that directly in CI would mean the pipeline silently modifies source files, which either gets discarded (useless — the developer's actual commit remains unformatted) or gets auto-committed back (confusing, can trigger pipeline loops, and hides the fact that formatting was ever wrong). `fmt -check` instead only reports whether files are already correctly formatted and returns a non-zero exit code if not, making it a pure verification gate — the actual fix happens locally via a normal `terraform fmt` run and gets committed by the author like any other change.
_What the interviewer is probing for:_ Practical CI/CD hygiene — separating verification from mutation in automated pipelines.

**🎯 Senior:** _"A configuration passes `terraform validate` with zero errors, but `terraform plan` fails with a provider API error about an invalid AMI ID. Is this a bug in `validate`? Explain what each command is actually responsible for checking."_
**Model answer:** Not a bug — it's `validate` working exactly as designed. `validate` performs static checks against the provider's _schema_ (argument names, expected types, structural correctness) using cached schema metadata from `init`; it has no way to know whether a given string value (an AMI ID) actually corresponds to a real, existing resource in the target account/region, because that requires a live API call. `plan` performs that live check as part of its refresh and diff computation, which is why AMI-validity, quota, and authorization errors only ever surface there, not at `validate` time. The two commands intentionally check different things at different costs — cheap structural correctness locally, expensive semantic/live correctness against the real provider.
_What the interviewer is probing for:_ Precise understanding of what each command's checking boundary actually is, rather than treating them as interchangeable "does it work" gates.

**🎯 Architect:** _"You're setting up the first few stages of a Terraform CI pipeline for a large, multi-team monorepo. How would you sequence `fmt`, `validate`, and `plan`, and why does the order matter at scale?"_
**Model answer:** Sequence by cost and blast radius, cheapest and safest first: (1) `fmt -check -recursive` — purely local, no credentials, near-instant, catches the most common and least interesting class of PR feedback; (2) `terraform init -backend=false` plus `terraform validate` (or full `init` if backend access is cheap and available) — still no infrastructure credentials required, catches structural errors across potentially hundreds of modules in a monorepo before anything expensive runs; (3) only then, `terraform plan` with real (ideally read-only or narrowly scoped) credentials against the specific changed modules/environments, using something like a changed-files detection step to avoid planning every module in the monorepo on every PR. This ordering matters at scale specifically because a monorepo CI run touching many modules is expensive in both time and API rate-limit consumption — failing fast on cheap checks before ever acquiring credentials or hitting a provider API dramatically reduces wasted CI minutes and avoids unnecessary load on shared, rate-limited provider APIs across many concurrent PR pipelines.
_What the interviewer is probing for:_ Pipeline design sense — sequencing checks by cost/risk, and awareness of monorepo-scale operational concerns (rate limits, wasted compute) rather than just naming the three commands.

## 12. Common Misconceptions

1. **"`terraform validate` guarantees `plan` and `apply` will succeed."** It only guarantees structural/type correctness against provider schema — it cannot catch live provider-side errors like invalid IDs, quota limits, or authorization failures.
2. **"`terraform fmt` can change what infrastructure gets created."** It only ever changes whitespace/formatting — it is behavior-preserving by design and definition; if a `fmt` diff ever appeared to change a plan's outcome, that would be a Terraform bug, not expected behavior.
3. **"`fmt` and `fmt -check` do the same thing."** `fmt` rewrites files; `fmt -check` only reports pass/fail without modifying anything — using the wrong one in CI causes real workflow problems.
4. **"`validate` doesn't need `init` first."** It does — it needs cached provider schema to check argument types and names against, which only exists after a successful `init`.

## 13. 🔑 Key Takeaways

- `terraform validate` is a cheap, offline, credential-free structural correctness check; it complements but never replaces `plan`.
- `terraform fmt` is a purely cosmetic, behavior-preserving formatter; `fmt -check` is the non-mutating form CI should use.
- Both belong as early, fast gates before any credentialed, expensive `plan`/`apply` step — fail fast on the cheapest checks first.
- `validate` requires a prior `init` (for provider schema); `fmt` has no such requirement.
- Pin CLI versions across environments to avoid `fmt -check` disagreements between local dev and CI caused by formatting-rule differences across Terraform versions.

## 14. Related Concepts & What's Next

[§15](../Part3/Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md)–[§16](../Part3/Section-16-Part3-Terraform-File-Structure-and-Conventions.md) cover the HCL syntax and file conventions that `fmt` normalizes. [§99](../Part14/Section-99-Part14-terraform-validate-and-Plan-Based-Testing-Strategies.md) expands `validate` into a full plan-based testing strategy. [§104](../Part14/Section-104-Part14-Pre-Commit-Hooks-and-Linting-tflint.md) covers pre-commit hooks and `tflint`, the natural next layer of static checking beyond `fmt`/`validate`. [§30](./Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md) covers `-json` output more broadly across `show`, `plan`, and `output`, building on the `-json` pattern introduced here for `validate`. Next, [§28](./Section-28-Part4-terraform-console-and-terraform-graph.md) covers `terraform console` and `terraform graph` — two more local, diagnostic-only commands that round out the CLI's inspection toolkit.

**Next Section:** [§28](./Section-28-Part4-terraform-console-and-terraform-graph.md) — `Section-28-Part4-terraform-console-and-terraform-graph.md`
