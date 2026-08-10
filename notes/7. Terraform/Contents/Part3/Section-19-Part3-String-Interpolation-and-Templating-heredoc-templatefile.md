# Section 19 (Part 3): String Interpolation and Templating (heredoc, templatefile)

## 1. Definition

**Plain language:** String interpolation is how you embed a computed value inside a string — instead of writing `"Server: " + var.name` like some languages, HCL lets you write `"Server: ${var.name}"` directly inside the string. Templating extends this to whole files: `templatefile()` reads an external file (a shell script, a config template, cloud-init user data) and substitutes variables into it, so you don't have to build large multi-line strings by hand inside a `.tf` file.

**Precise definition:** HCL supports **string interpolation syntax**, `${expression}`, embedded inside any string literal, which is evaluated and substituted at plan/apply time. HCL also defines **template directives** — `%{ if condition }...%{ endif }` and `%{ for item in collection }...%{ endfor }` — for conditional and iterative logic _inside_ a string template, distinct from the `for` expression covered in [§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md). For multi-line strings, HCL provides **heredoc syntax** (`<<EOT ... EOT`, and its indentation-aware variant `<<-EOT ... EOT`). The built-in `templatefile(path, vars)` function reads an entire external file as a template, evaluates any interpolation/directives inside it against the supplied `vars` map, and returns the rendered result as a string — the standard mechanism for generating cloud-init scripts, config files, and other templated text from Terraform.

> 💡 **Tip:** `${...}` substitutes a single expression's value into a string. `%{ if }`/`%{ for }` directives are template-only control flow that exist _nowhere else_ in HCL — they only work inside string templates (heredocs, `templatefile()`), not as general-purpose language constructs.

## 2. Why This Matters

- Nearly every non-trivial Terraform module needs to generate some piece of external configuration text — cloud-init user data, Nginx configs, Kubernetes manifests, IAM policy JSON — and `templatefile()` combined with heredoc syntax is the standard, idiomatic way to do it without string-concatenation gymnastics.
- Interpolation syntax is used _everywhere_ in real HCL — resource names, tags, computed identifiers — so fluency with `${}` and when it's actually required (vs. when it's a redundant no-op) is a daily-use skill.
- Template directives (`%{ if }`, `%{ for }`) let a single external template file adapt to different inputs without duplicating near-identical template files per environment — understanding them prevents unnecessary template sprawl.
- Getting heredoc indentation wrong (`<<EOT` vs. `<<-EOT`) is a common, hard-to-spot source of malformed generated files (leading whitespace breaking YAML, shell scripts, etc.) that only surfaces once the generated content is actually consumed downstream.

## 3. Prerequisites and Dependencies

Builds on [§17](./Section-17-Part3-Data-Types-Primitives-Collections-list-map-set-Structural-object-tuple.md) (types — templates always produce a `string`) and [§18](./Section-18-Part3-Expressions-Arithmetic-Comparison-and-Conditional-Ternary-Expressions.md) (expressions — `${}` embeds any valid expression, including ternaries and function calls). Directly feeds into [§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md) (built-in string functions like `format()`, `join()`, `replace()` are frequently combined with templating) and [§64](../Part9/Section-64-Part9-local-exec-and-remote-exec-Provisioners.md) (`local-exec`/`remote-exec` provisioners commonly use `templatefile()`-generated scripts).

## 4. Architecture / Conceptual Diagram

```hcl
# ── Simple interpolation ─────────────────────────────────────
locals {
  greeting = "Hello, ${var.name}!"              # ${} substitutes var.name's value
  full_id  = "${var.project}-${var.environment}" # multiple interpolations in one string
}

# ── Heredoc (multi-line string) ───────────────────────────────
locals {
  raw_script = <<EOT
    #!/bin/bash
    echo "this preserves leading whitespace exactly as written"
  EOT

  clean_script = <<-EOT
    #!/bin/bash
    echo "the '-' strips the common leading indentation"
  EOT
}

# ── templatefile(): render an external file as a template ─────
resource "aws_instance" "web" {
  # ...
  user_data = templatefile("${path.module}/templates/init.sh.tpl", {
    hostname    = "web-01"
    environment = var.environment
    packages    = ["nginx", "curl", "git"]
  })
}
```

```text
# templates/init.sh.tpl — a template file, using ${} and %{} directives
#!/bin/bash
hostnamectl set-hostname ${hostname}

%{ if environment == "production" }
echo "production hardening applied"
%{ endif }

%{ for pkg in packages }
apt-get install -y ${pkg}
%{ endfor }
```

## 5. Hands-On

### 5.1 Basic Interpolation

**Purpose:** Embed a computed value directly inside a string literal.

**Syntax:**

```hcl
"literal text ${expression} more literal text"
```

**Example usage and expected output:**

```bash
$ terraform console
> "Hello, ${"World"}"
"Hello, World"
> "${var.environment}-${var.project}-db"
"production-payments-db"
```

**Production usage example:** Resource naming almost universally uses interpolation to build unique, descriptive names from variables and locals — e.g., `"${var.project}-${var.environment}-${var.component}"` produces consistent, greppable resource names across an entire organization's Terraform estate.

**Common errors:** Redundant interpolation of an already-string expression (`"${var.name}"` instead of just `var.name` when the whole argument is a single reference) is not an error — `terraform fmt`/linters flag it as an unnecessary-interpolation style issue, since `var.name` alone already evaluates to the string.

### 5.2 Heredoc Syntax

**Purpose:** Write multi-line string literals cleanly without escaping every newline.

**Syntax:**

```hcl
<<EOT
...content, indentation preserved literally...
EOT

<<-EOT
    ...content, common leading whitespace stripped...
    EOT
```

**Example usage and expected output:**

```hcl
locals {
  policy_doc = <<-EOT
    {
      "Version": "2012-10-17",
      "Statement": [{
        "Effect": "Allow",
        "Action": "s3:GetObject",
        "Resource": "arn:aws:s3:::${var.bucket_name}/*"
      }]
    }
  EOT
}
```

```bash
$ terraform console
> local.policy_doc
<<EOT
{
  "Version": "2012-10-17",
  ...
}

EOT
```

**Production usage example:** Inline IAM policy JSON, shell scripts, and short config snippets embedded directly in a resource argument (rather than pulled from an external file via `templatefile()`) commonly use `<<-EOT` heredocs specifically for the indentation-stripping behavior, so the HCL source can stay properly indented without corrupting the generated content with leading whitespace.

**Common errors:** Using `<<EOT` (no `-`) with indented HCL source embeds that literal leading whitespace into the output string — this is a very common cause of malformed generated YAML or JSON, since leading whitespace is often semantically meaningful in those formats; switching to `<<-EOT` is the fix in virtually every such case.

### 5.3 `templatefile()` and Template Directives

**Purpose:** Render an external file as a template with variable substitution and conditional/loop directives, keeping large generated content out of `.tf` files entirely.

**Syntax:**

```hcl
templatefile(path, vars_map)
```

**Example usage and expected output:**

```hcl
# templates/user_data.sh.tpl
#!/bin/bash
set -e
echo "Provisioning ${hostname} in ${environment}"

%{ if environment == "production" }
echo "enabling enhanced monitoring"
%{ endif }

%{ for pkg in packages ~}
apt-get install -y ${pkg}
%{ endfor ~}
```

```hcl
# main.tf
resource "aws_instance" "web" {
  ami           = "ami-0c55b159cbfafe1f0"
  instance_type = "t3.micro"
  user_data = templatefile("${path.module}/templates/user_data.sh.tpl", {
    hostname    = "web-01"
    environment = "production"
    packages    = ["nginx", "curl"]
  })
}
```

```bash
$ terraform console
> templatefile("${path.module}/templates/user_data.sh.tpl", { hostname = "web-01", environment = "production", packages = ["nginx", "curl"] })
"#!/bin/bash\nset -e\necho \"Provisioning web-01 in production\"\n\necho \"enabling enhanced monitoring\"\n\napt-get install -y nginx\napt-get install -y curl\n"
```

**Production usage example:** `templatefile()` is the standard way to generate EC2 `user_data` / cloud-init scripts, Kubernetes ConfigMap content, and application config files from Terraform — keeping the templated content in its own `.tpl` file (often with proper shell/YAML syntax highlighting in an editor) instead of an unwieldy multi-hundred-line heredoc embedded in a resource argument.

**Common errors:** `templatefile()` requires **every** variable referenced inside the template to be present in the `vars_map` argument — an undefined reference inside the template produces `Error: Invalid function call — vars map does not contain key "x"` at plan time, a common mistake when a template is edited without updating the calling `templatefile()` invocation.

## 6. Production Usage Notes

- The `~` modifier on template directives (`%{ for pkg in packages ~}`) strips the newline/whitespace immediately adjacent to the directive, which is essential for producing clean output from loop directives that would otherwise leave stray blank lines in generated files.
- `templatefile()` paths are almost always built with `path.module` ([§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md)/[§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md) context) rather than a hardcoded relative path, so the module works correctly regardless of the caller's working directory or how deeply the module is nested.
- Large generated files (multi-KB cloud-init scripts, full application configs) belong in external `.tpl` files consumed via `templatefile()`, not inline heredocs — this keeps `.tf` files reviewable and lets the template itself get proper syntax highlighting and linting in an editor.

## 7. Security Considerations

- Interpolating a `sensitive`-marked variable ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) into a template does **not** automatically propagate the sensitivity marking to the rendered output in all Terraform versions/contexts — treat any template output that embeds a secret as sensitive explicitly, and be aware it may be written to `user_data` in plaintext, visible via the cloud provider's instance metadata API to anyone with access to the instance.
- Templated shell scripts that embed variable values directly (`echo ${var.user_input}`) can be vulnerable to shell-injection-style issues if the embedded value isn't controlled/validated — treat any externally-influenced value flowing into a rendered shell script template with the same care as any other injection surface.

## 8. Common Troubleshooting Scenarios

| Symptom                                                       | Likely Cause                                                                    | Resolution Path                                                                           |
| ------------------------------------------------------------- | ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- |
| Generated file has unexpected leading whitespace/broken YAML  | Used `<<EOT` instead of `<<-EOT`, so source indentation was preserved literally | Switch to `<<-EOT`/`<<-EOF` to strip common leading indentation                           |
| `Error: vars map does not contain key "x"`                    | Template references a variable not passed in `templatefile()`'s vars map        | Add the missing key to the vars map, or remove the unused reference from the template     |
| Rendered template has stray blank lines from `%{ for }` loops | Missing `~` whitespace-trim modifiers on directive tags                         | Add `~` to the directive tags (`%{ for x in y ~}` / `%{ endfor ~}`)                       |
| Interpolated sensitive value appears in plan output or logs   | Sensitivity wasn't propagated through the template rendering                    | Mark the output/resource attribute `sensitive = true` explicitly; audit logs for exposure |

## 9. Best Practices

- Use `<<-EOT`/`<<-EOF` (indentation-stripping heredoc) as the default, not `<<EOT`, unless literal indentation preservation is genuinely required.
- Move any template content beyond a few lines into a dedicated `.tpl` file consumed via `templatefile()`, rather than growing a heredoc inline in a resource block.
- Use the `~` whitespace-trim modifier on `%{ if }`/`%{ for }` directive tags to avoid stray blank lines in generated output.
- Avoid redundant interpolation (`"${var.x}"` when `var.x` alone suffices) — `terraform fmt` and most linters flag this, and it adds visual noise without changing behavior.

## 10. Common Anti-Patterns / Mistakes

- **Building large generated files as string concatenation** (`"${a}${b}${c}..."`) instead of using `templatefile()` with a proper template file — harder to read, harder to review, and loses any editor syntax highlighting for the target file format.
- **Mixing `${}` interpolation syntax with `%{}` directive syntax incorrectly** (e.g., using `${if ...}` instead of `%{ if ... }`) — a common early mistake since both use similar `{}` delimiter styles but serve entirely different purposes.
- **Forgetting `~` whitespace trimming**, producing generated files littered with blank lines that then need post-processing or cause issues in whitespace-sensitive formats like YAML.
- **Interpolating sensitive values into unencrypted `user_data`** without considering that cloud instance metadata is often readable by anything running on that instance — a real, recurring security oversight.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `${}` and `%{}` in an HCL template?"_
**Model answer:** `${expression}` substitutes the evaluated value of an expression directly into a string. `%{ directive }` is template-only control flow — `%{ if condition }...%{ endif }` for conditionals and `%{ for x in list }...%{ endfor }` for loops — that only exists inside string templates, not as general HCL syntax elsewhere.
_What the interviewer is probing for:_ Whether the candidate can distinguish value-substitution syntax from template-control-flow syntax, since they look superficially similar but do fundamentally different things.

**🎯 Intermediate:** _"When would you use `templatefile()` instead of a heredoc string directly in a resource block?"_
**Model answer:** Once the templated content grows beyond a handful of lines, or needs proper syntax highlighting/linting as its native format (shell, YAML, JSON), moving it into an external file consumed via `templatefile()` keeps the `.tf` file itself clean and makes the template file reviewable and editable with appropriate tooling. It also allows the same template to potentially be reused or tested independently of the Terraform configuration that renders it.
_What the interviewer is probing for:_ Practical judgment about when inline heredocs are fine (short, simple) versus when external templates are the better engineering choice (long, complex, needs its own tooling).

**🎯 Senior:** _"A generated `user_data` script from `templatefile()` is failing on the instance with a syntax error, but the template file looks correct in the editor. What's your debugging approach?"_
**Model answer:** First render the template independently via `terraform console` (calling `templatefile()` directly with representative variable values) to see the actual generated output as a raw string, since editor preview and actual rendered output can differ — particularly around heredoc indentation stripping and `%{ for }`/`%{ if }` whitespace trimming with `~`. A frequent root cause is stray blank lines or leading whitespace from missing `~` trim modifiers, which look harmless in an editor but can break shell script syntax (e.g., an accidental blank line inside a multi-line command) or YAML indentation. Comparing the `terraform console` output byte-for-byte against what a correctly-formed script should look like usually isolates the issue quickly.
_What the interviewer is probing for:_ A concrete, tool-based debugging methodology (use `terraform console` to inspect actual rendered output) rather than guessing from the template source alone.

**🎯 Architect:** _"Your organization has dozens of modules each with their own near-duplicate cloud-init templates. How would you architect this to reduce duplication while keeping per-module flexibility?"_
**Model answer:** Extract a shared, parameterized base template (using `%{ if }`/`%{ for }` directives to handle the variation between modules — optional package lists, optional hardening blocks, per-environment conditional sections) into a common module or shared file included via a relative path or a small internal "cloud-init" module that every consuming module calls with its own `vars` map. The key design decision is drawing the line between what varies as _data_ (passed through the `vars` map — package lists, hostnames, environment flags) versus what varies as _template structure_ (requiring `%{ if }` branches within the shared template) — pushing too much structural variation into directives makes the shared template itself hard to read, at which point it's often better to accept two or three purpose-specific templates rather than one template trying to serve every case via directives.
_What the interviewer is probing for:_ Architectural judgment about the trade-off between DRY template reuse and template readability/maintainability — recognizing that over-parameterizing a template with directives has its own real cost.

## 12. Common Misconceptions

1. **"`${}` and `%{}` are interchangeable template syntax."** They're not — `${}` substitutes a value; `%{}` is control-flow directive syntax, valid only inside templates.
2. **"Heredocs always preserve exact formatting."** Only `<<EOT` (no dash) does; `<<-EOT` strips common leading indentation, which is the far more commonly desired behavior in practice.
3. **"`templatefile()` variables can reference anything in scope automatically."** They can't — every variable used inside the template must be explicitly passed in the `vars_map` argument; there's no automatic scope inheritance from the calling module.
4. **"Sensitive values stay marked sensitive automatically through template rendering."** Propagation isn't guaranteed in every context — explicitly mark downstream outputs/attributes `sensitive = true` if a template embeds secret material.

## 13. 🔑 Key Takeaways

- `${expression}` performs value interpolation inside any string; `%{ if }`/`%{ for }` are template-only directives for conditional and iterative logic inside a template, not general HCL constructs.
- `<<-EOT` (indentation-stripping heredoc) should be the default over `<<EOT` for any indented multi-line string.
- `templatefile(path, vars)` is the standard, idiomatic way to render external files (cloud-init scripts, configs) with variable substitution, and requires every referenced variable to be present in the `vars` map.
- The `~` whitespace-trim modifier on directive tags prevents stray blank lines in rendered output — a frequent source of malformed generated files without it.
- Treat any templated output embedding a secret as sensitive explicitly; propagation through templating is not automatically guaranteed.

## 14. Related Concepts & What's Next

[§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md) covers the built-in string functions (`format()`, `join()`, `replace()`, `trimspace()`) frequently used alongside templating. [§21](./Section-21-Part3-for-Expressions-and-Splat-Expressions.md) covers `for` expressions — the general-purpose collection-transformation construct, distinct from but conceptually related to the `%{ for }` template directive covered here. [§64](../Part9/Section-64-Part9-local-exec-and-remote-exec-Provisioners.md) (`local-exec`/`remote-exec` provisioners) and Part 11's cloud-provider sections make heavy practical use of `templatefile()`-generated scripts and configs. [§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md) covers sensitivity propagation in full depth, directly relevant to the security note above.

**Next Section:** [§20](./Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md) — `Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md`
