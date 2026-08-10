# Section 40 (Part 6): Variable Precedence and Assignment Methods (CLI Flags, .tfvars, Environment Variables)

## 1. Definition

**Plain language:** A single declared variable can potentially receive a value from several different places at once — a command-line flag, one or more `.tfvars` files, an environment variable, or its own default. When more than one of these supplies a value for the same variable, Terraform needs a deterministic rule for which one wins, so the same configuration doesn't behave unpredictably depending on which files happen to be lying around.

**Precise definition:** Terraform resolves each input variable's final value using a fixed **precedence order**, from highest to lowest priority: (1) `-var` and `-var-file` command-line flags, evaluated **in the order given on the command line**, later flags overriding earlier ones; (2) `*.auto.tfvars`/`*.auto.tfvars.json` files in the working directory, loaded automatically in **alphabetical order by filename**; (3) `terraform.tfvars`/`terraform.tfvars.json`, if present, loaded automatically; (4) `TF_VAR_<name>` environment variables; (5) the variable's own `default` argument, if declared. Any source higher in this list overrides a value from a source lower in the list for the same variable name; sources that don't mention a given variable simply don't participate for that variable.

> 💡 **Tip:** `-var-file` and `-var` on the command line are the only sources whose relative order you control explicitly (left to right, later wins) — every other automatic source (`*.auto.tfvars`, `terraform.tfvars`, environment variables) has a fixed position in the hierarchy regardless of file timestamps or the order variables happen to be declared in `variables.tf`.

## 2. Why This Matters

- **Predictable environment overrides.** CI/CD pipelines ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) rely on being able to pass `-var-file=prod.tfvars` and have it reliably override whatever is sitting in `terraform.tfvars` locally — without a fixed precedence order, this pattern wouldn't be trustworthy.
- **Local developer overrides without touching shared files.** A developer can drop a personal `override.auto.tfvars` (gitignored) to tweak a value locally without editing the checked-in `terraform.tfvars` that the rest of the team relies on.
- **Debugging "why did it use that value" incidents.** When a plan uses an unexpected value for a variable, understanding precedence is the only way to systematically trace which of potentially five candidate sources actually won, rather than guessing.
- **Secrets injection via environment variables.** `TF_VAR_*` is the standard mechanism CI/CD systems use to inject secrets from a secrets manager into a Terraform run without writing them to any file on disk — understanding where it sits in precedence (below `.tfvars` files, above defaults) is essential to using it correctly.
- **Safe defaults that are still overridable everywhere else.** A variable's `default` sitting at the bottom of precedence means every other assignment method can reliably override it — module authors depend on this to ship usable defaults that any caller can still customize.

## 3. Prerequisites and Dependencies

This section directly extends [§39](./Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md) (variable declaration) — it assumes a `variable` block already exists and focuses purely on how its runtime value is resolved. It also assumes familiarity with common CLI flags from [§31](../Part4/Section-31-Part4-Common-CLI-Flags-Automation-Friendly-Patterns.md) (`-var`, `-var-file`, and other automation-friendly flags). [§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md) builds on precedence to discuss what happens when a `sensitive`-marked variable is assigned via each of these methods.

## 4. Architecture / Conceptual Diagram

```text
   HIGHEST PRECEDENCE (wins ties)
   ┌─────────────────────────────────────────────────────────────┐
   │ 1. -var="key=value"  and  -var-file=path.tfvars             │
   │    (CLI flags, left-to-right order on the command line —    │
   │     later flag overrides earlier flag for the same key)     │
   ├─────────────────────────────────────────────────────────────┤
   │ 2. *.auto.tfvars / *.auto.tfvars.json                       │
   │    (auto-loaded, alphabetical filename order:               │
   │     01-base.auto.tfvars loads before 02-region.auto.tfvars) │
   ├─────────────────────────────────────────────────────────────┤
   │ 3. terraform.tfvars / terraform.tfvars.json                 │
   │    (auto-loaded if present)                                 │
   ├─────────────────────────────────────────────────────────────┤
   │ 4. TF_VAR_<name> environment variables                      │
   ├─────────────────────────────────────────────────────────────┤
   │ 5. default argument in the variable block (§39)             │
   └─────────────────────────────────────────────────────────────┘
   LOWEST PRECEDENCE (loses to everything above)

   Resolution is PER VARIABLE, not per file: variable "region" could
   resolve from terraform.tfvars while variable "instance_type"
   resolves from a -var flag in the very same run.
```

- Precedence resolves independently for each variable name — there's no "whichever file is used wins for everything"; a single `terraform apply` invocation can pull different variables from different tiers simultaneously.
- Within tier 2 (`*.auto.tfvars`), files load in alphabetical order and later files override earlier ones for any variable they both set — a common convention is numeric prefixes (`00-defaults.auto.tfvars`, `10-region.auto.tfvars`) purely to control this ordering predictably.

## 5. Hands-On

### 5.1 CLI Flags: `-var` and `-var-file`

**Purpose:** Show explicit, run-time variable assignment via the command line, the highest-precedence source.

**Syntax:**

```bash
terraform apply -var="instance_type=t3.large" -var-file="prod.tfvars"
```

**Example usage and expected output:**

```bash
$ cat prod.tfvars
instance_type = "t3.medium"
environment   = "prod"

$ terraform apply -var="instance_type=t3.large" -var-file="prod.tfvars"
# instance_type resolves to "t3.large" — the -var flag came after
# -var-file on the command line for a value that ALSO appears in
# prod.tfvars, and -var/-var-file both outrank all other sources;
# ordering between multiple CLI flags follows command-line order.
# environment resolves to "prod" from prod.tfvars (no -var override given)

Plan: ...
```

**Production usage example:** A CI/CD pipeline ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) uses `-var-file` to select an entire environment's variable set (`prod.tfvars`, `staging.tfvars`) while reserving individual `-var` flags for values only known at pipeline runtime, such as a build-specific artifact version or a commit SHA tag.

**Common errors:** Passing `-var="count=3"` for a variable that doesn't exist in `variables.tf` produces a warning (not always a hard error, depending on Terraform version) about an undeclared variable — a frequent sign of a typo in the flag or a stale flag left over after a variable was renamed.

### 5.2 `.tfvars` Files: Explicit and Auto-Loaded

**Purpose:** Show the difference between a `.tfvars` file that must be explicitly passed and ones Terraform loads automatically.

**Syntax:**

```hcl
# terraform.tfvars — loaded automatically, no flag needed
region       = "us-east-1"
instance_type = "t3.micro"

# region.auto.tfvars — also loaded automatically (matches *.auto.tfvars)
availability_zones = ["us-east-1a", "us-east-1b"]
```

**Example usage and expected output:**

```bash
$ ls
main.tf  variables.tf  terraform.tfvars  region.auto.tfvars

$ terraform plan
# Both terraform.tfvars and region.auto.tfvars are loaded automatically —
# no -var-file flag needed for either.
```

**Production usage example:** `terraform.tfvars` commonly holds the values for whichever environment a given directory or workspace represents (in a directory-per-environment layout, [§71](../Part10/Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md)); `*.auto.tfvars` is often used for values that should always load regardless of which explicit `-var-file` a pipeline passes, such as organization-wide tags.

**Common errors:** Two files both auto-loading and both setting the same variable (e.g., `terraform.tfvars` and `a.auto.tfvars`) produces a silent override — the alphabetically later `.auto.tfvars` file, or the fixed-position `terraform.tfvars` per the tier ordering — with no warning, which is a common source of "why is this using the wrong value" confusion during review.

### 5.3 Environment Variables: `TF_VAR_*`

**Purpose:** Show injecting a variable value without any file at all — the standard pattern for CI-supplied secrets.

**Syntax:**

```bash
export TF_VAR_db_password="s3cr3t-from-secrets-manager"
```

**Example usage and expected output:**

```bash
$ export TF_VAR_db_password="s3cr3t-value"
$ terraform apply
# var.db_password resolves to "s3cr3t-value" — UNLESS a .tfvars file
# or -var flag also sets db_password, in which case those win instead,
# since TF_VAR_* sits below every .tfvars tier in precedence.

Plan: ...
```

**Production usage example:** A GitHub Actions workflow ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) pulls a database password from a secrets store and exports it as `TF_VAR_db_password` immediately before invoking `terraform apply`, so the secret never touches disk as a `.tfvars` file and never appears in shell history as a literal `-var` argument.

**Common errors:** Setting `TF_VAR_dbpassword` (missing underscore, or mismatched casing against the declared variable name `db_password`) silently does nothing — Terraform requires an exact name match after the `TF_VAR_` prefix, and there's no error for a `TF_VAR_*` variable that doesn't correspond to any declared variable, since environment variables not matching a declaration are simply ignored.

## 6. Production Usage Notes

- **`-var-file` order on the command line is significant and often overlooked.** `terraform apply -var-file=base.tfvars -var-file=prod.tfvars` lets `prod.tfvars` override anything `base.tfvars` also sets — a common layered-configuration pattern (shared base values plus environment-specific overrides) that depends entirely on getting the flag order right.
- **`*.auto.tfvars` files are easy to forget are being loaded at all**, since nothing on the command line references them — code reviewers unfamiliar with a repository's file layout can be surprised that a plan's values don't trace back to any flag or explicit file reference.
- **Environment-variable-sourced secrets don't appear in `.tfvars` diffs**, which is exactly the point for CI/CD secret injection, but it also means `TF_VAR_*` usage should be documented somewhere discoverable (a README, a pipeline definition) since it's otherwise invisible from the Terraform configuration alone.

## 7. Security Considerations

- `TF_VAR_*` environment variables are the standard low-exposure channel for secrets into a Terraform run — they avoid writing the secret to disk as a `.tfvars` file that could be accidentally committed, and avoid it appearing as a literal `-var` argument that would be visible in shell history or process listings (`ps aux`) on multi-tenant CI runners.
- `-var="password=..."` on the command line is the least secure assignment method for anything sensitive — the value is visible in shell history, in process listings while the command runs, and often in CI job logs that echo the invoked command — avoid it for secrets even though it works functionally.
- `.tfvars` files containing real secrets must never be committed; `.gitignore` entries for `*.tfvars` (or a narrower pattern like `secrets.tfvars`) are a baseline hygiene practice, with `.tfvars.example` files (containing placeholder values only) checked in instead to document the expected shape.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                       | Likely Cause                                                                                                      | Resolution Path                                                                                                       |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| A variable uses an unexpected value with no obvious source in the plan output | A `*.auto.tfvars` file or `TF_VAR_*` environment variable is silently supplying it and being overlooked           | Run `terraform plan` after listing all `*.tfvars` files and `env \| grep TF_VAR_` to enumerate every candidate source |
| `-var-file` value doesn't take effect even though it's clearly passed         | A later `-var` or `-var-file` flag on the same command line overrides it (flag order matters)                     | Reorder flags so the intended override comes last, or remove the conflicting flag                                     |
| `TF_VAR_` export has no effect on the plan                                    | Variable name mismatch after the prefix (case sensitivity, missing underscore) against the declared variable name | Verify the exact declared variable name in `variables.tf` and match `TF_VAR_<exact_name>` precisely                   |

## 9. Best Practices

- Keep secrets out of `.tfvars` files entirely where possible; prefer `TF_VAR_*` injected at pipeline runtime from a secrets manager ([§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md)/[§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)), or a dedicated secrets-management integration over any file-based assignment method.
- Use numeric or semantic filename prefixes for multiple `*.auto.tfvars` files (`00-common.auto.tfvars`, `10-region.auto.tfvars`) so their alphabetical load order is intentional and reviewable, not accidental.
- Document, in the module or root configuration's README, which variables are expected to arrive via `TF_VAR_*` — this precedence tier is otherwise invisible from the `.tf`/`.tfvars` files alone and easy for a new team member to miss.

## 10. Common Anti-Patterns / Mistakes

- **Relying on flag order in a long, hand-typed `-var-file` chain without documenting why the order matters.** A future edit that reorders flags "for readability" can silently flip which environment's values win.
- **Committing a `.tfvars` file with real secrets because "it's easier than setting up environment variables."** This is one of the most common sources of leaked credentials in infrastructure repositories — [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) covers the state-file side of secrets exposure, but committed `.tfvars` is an even more direct leak vector.
- **Assuming `terraform.tfvars` is the only place values come from**, then being confused when a `*.auto.tfvars` file (higher precedence) or a `TF_VAR_*` export overrides it during troubleshooting — precedence has five tiers, not one.

## 11. Interview Questions

**🎯 Beginner:** _"Name two ways to assign a value to a Terraform input variable, other than its default."_
**Model answer:** A command-line `-var="name=value"` flag, and a `.tfvars` file (either explicitly passed with `-var-file` or auto-loaded if named `terraform.tfvars` or `*.auto.tfvars`). A third method is setting an environment variable named `TF_VAR_<name>`.
_What the interviewer is probing for:_ Basic familiarity with the range of assignment mechanisms beyond just editing a default.

**🎯 Intermediate:** _"If a variable is set in both `terraform.tfvars` and via a `TF_VAR_`environment variable, which one wins, and why does that ordering make sense?"_
**Model answer:**`terraform.tfvars`wins —`.tfvars`files sit above environment variables in Terraform's fixed precedence order. This makes sense operationally because`.tfvars`files represent an explicit, reviewed configuration choice checked into (or deliberately supplied alongside) the codebase, while environment variables are often ambient — inherited from a shell session, a CI runner's default environment, or a previous command — and giving them lower priority means an accidental leftover`TF*VAR*\*` export can't silently override an intentional, version-controlled value.
_What the interviewer is probing for:_ Whether the candidate has memorized the actual order (not guessed it) and can reason about why it's designed that way, not just recite it.

**🎯 Senior:** _"A teammate passes `-var-file=base.tfvars -var-file=prod.tfvars` and is confused that a value from `base.tfvars` unexpectedly won. What's the likely cause, and how do you verify it?"_
**Model answer:** The likely cause is that `prod.tfvars` simply doesn't set that particular variable at all, so there's nothing to override it with — precedence between two `-var-file` flags only applies to variables both files actually set; for any variable only `base.tfvars` sets, `base.tfvars`'s value is correct and expected, not a bug. To verify, check whether the variable name appears in `prod.tfvars` at all (`grep` for the key) rather than assuming file order alone determines every variable's outcome — resolution is per-variable, not "whichever file loads last wins for everything."
_What the interviewer is probing for:_ Precision about the fact that precedence is evaluated independently per variable name, a subtlety that trips up engineers who think of `-var-file` order as a blanket override.

**🎯 Architect:** _"Design a variable-assignment strategy for an organization running the same Terraform root module across 40 accounts in dev/staging/prod, where some values are org-wide constants, some are per-environment-tier, and a small number are genuine per-run secrets."_
**Model answer:** Org-wide constants (common tags, a company-wide naming prefix) belong in an `*.auto.tfvars` file checked into every consuming repo or generated from a shared template, so they load automatically without every pipeline needing to reference them explicitly. Per-environment-tier values (instance sizing, replica counts) belong in explicit, named `.tfvars` files per tier (`dev.tfvars`, `staging.tfvars`, `prod.tfvars`) passed via `-var-file` in the pipeline step that selects the target environment — explicit is safer than automatic here because selecting the wrong tier should be a visible, deliberate flag choice, not something that happens by file-naming accident. Genuine secrets (API keys, database passwords) should bypass `.tfvars` entirely and flow in as `TF_VAR_*` environment variables populated at pipeline runtime from a secrets manager ([§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md)/[§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)), scoped narrowly to the job's lifetime and never written to disk or logged. Defaults in `variable` blocks should exist only for genuinely safe, non-environment-sensitive fallbacks — anything account-critical (like account ID) should have no default at all, forcing every invocation to supply it explicitly and fail loudly if it's missing.
_What the interviewer is probing for:_ Whether the candidate can map the five-tier precedence model onto a real organizational structure with mixed sensitivity and scope requirements, rather than using one assignment method for everything.

## 12. Common Misconceptions

1. **"`.tfvars` files always need `-var-file` to be used."** Only true for files that aren't named `terraform.tfvars` or matching `*.auto.tfvars` — those two patterns load automatically with no flag at all.
2. **"Whichever `.tfvars` file was edited most recently wins."** File modification time is irrelevant; precedence is governed strictly by tier (CLI flag > `*.auto.tfvars` alphabetical > `terraform.tfvars` > env var > default) and, within the `*.auto.tfvars` tier, filename alphabetical order — never timestamps.
3. **"`-var` on the command line is a safe way to pass a one-off secret for testing."** It's actually one of the least safe methods — visible in shell history and process listings — `TF_VAR_*` set in the current shell session (and unset immediately after) is a materially safer alternative for anything sensitive.
4. **"If a variable isn't in `terraform.tfvars`, it must be using its default."** It could just as easily be coming from a `*.auto.tfvars` file, a `-var` flag, or a `TF_VAR_*` environment variable — absence from one particular source proves nothing about the others.

## 13. 🔑 Key Takeaways

- The full precedence order, highest to lowest, is: `-var`/`-var-file` (command-line order) > `*.auto.tfvars` (alphabetical filename order) > `terraform.tfvars` > `TF_VAR_<name>` environment variables > the variable's own `default`.
- Precedence resolves independently per variable name — a single run can pull different variables from different tiers simultaneously.
- `TF_VAR_*` is the standard, disk-free channel for injecting secrets into CI/CD Terraform runs; `-var` on the command line is the least safe method for anything sensitive.
- `*.auto.tfvars` files load automatically with no flag reference, which makes them easy to overlook when debugging an unexpected value.
- Secrets belong in environment variables or a secrets manager integration, never in a committed `.tfvars` file.

## 14. Related Concepts & What's Next

[§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md) builds directly on this precedence model to cover what happens specifically to `sensitive`-marked variables as they flow through each of these assignment methods, and what protection `sensitive` does and doesn't provide. [§31](../Part4/Section-31-Part4-Common-CLI-Flags-Automation-Friendly-Patterns.md) revisits `-var-file` and related flags in the broader context of automation-friendly CLI usage. [§71](../Part10/Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md) covers file-layout patterns for multi-environment projects, where `.tfvars` file organization is a central design decision.

**Next Section:** [§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md) — `Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md`
