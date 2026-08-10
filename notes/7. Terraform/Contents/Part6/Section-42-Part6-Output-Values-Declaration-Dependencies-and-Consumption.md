# Section 42 (Part 6): Output Values: Declaration, Dependencies, and Consumption

## 1. Definition

**Plain language:** Output values are how a Terraform configuration reports information back out — a resource's generated ID, an assigned IP address, a computed URL. They're the return values of a Terraform run: things nobody typed in as input, but that only exist after `apply` actually creates the infrastructure and Terraform learns what the provider assigned.

**Precise definition:** An **output value** is declared with an `output` block containing a label (the output's name) and a `value` argument (an expression, typically referencing a resource attribute, data source attribute, or local value). Outputs are computed and displayed after `terraform apply` completes, are queryable individually via `terraform output <name>`, are the mechanism by which a **child module** exposes values to its **calling (parent) module** ([§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md)), and are the mechanism by which a **remote state data source** (`terraform_remote_state`) exposes values from one Terraform configuration to a completely separate one. Because an output's value typically depends on a resource attribute that's only known after that resource is created or updated, Terraform automatically computes output dependencies from the expression itself — there is no need to declare `depends_on` on an output in the ordinary case.

> 💡 **Tip:** An output is not "a variable for the outside world" in the sense of being settable — it's read-only and computed. You never assign an output a value externally the way you assign an input variable; its value is entirely determined by the expression in its `value` argument, evaluated against the current state after apply.

## 2. Why This Matters

- **Passing data between modules.** A VPC module's `vpc_id` and `subnet_ids` outputs are exactly how a compute module that's called afterward learns which network resources to launch instances into — outputs are the mechanism modules use to compose ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md), [§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md)).
- **Surfacing operationally useful information.** A load balancer's DNS name, a database's connection endpoint, an S3 bucket's ARN — these are frequently things a human or another system needs immediately after `apply`, and outputs are the standard way Terraform reports them without requiring a separate query to the cloud provider's console or API.
- **Cross-configuration data sharing via remote state.** Two independently-applied Terraform configurations (say, a networking team's VPC config and an application team's compute config) can share data through `terraform_remote_state` reading the networking config's outputs — a foundational pattern for organizing infrastructure across team boundaries.
- **CI/CD pipeline integration.** `terraform output -json` ([§30](../Part4/Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md)) is a common way for a pipeline to extract a value (an ECR repository URL, a deployed function ARN) and feed it into a subsequent pipeline step, such as a container build-and-push job.
- **Documentation of a module's "API surface."** A well-designed module's outputs, alongside its variables, form its complete public interface — reading `outputs.tf` tells a caller exactly what they get back without needing to read the module's internal resource blocks.

## 3. Prerequisites and Dependencies

This section assumes familiarity with resource blocks and resource attribute references ([§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md)), the resource graph and how Terraform derives dependency order from references ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)), and the standard file layout convention where outputs live in `outputs.tf` ([§16](../Part3/Section-16-Part3-Terraform-File-Structure-and-Conventions.md)). [§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md) already covered `sensitive` outputs specifically; this section covers the general case. [§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md) (Module Inputs and Outputs) revisits outputs specifically in the module-boundary context only briefly introduced here.

## 4. Architecture / Conceptual Diagram

```text
   DEPENDENCY-DRIVEN OUTPUT COMPUTATION

   resource "aws_instance" "app" {
     ami           = "ami-0abcdef1234567890"
     instance_type = "t3.micro"
   }
          │
          │ aws_instance.app.public_ip only exists AFTER apply —
          │ the provider assigns it, Terraform doesn't know it in advance
          ▼
   output "app_public_ip" {
     value = aws_instance.app.public_ip
   }
          │
          │ Terraform automatically infers: this output depends on
          │ aws_instance.app — no depends_on needed, derived from
          │ the reference itself (same mechanism as §11's graph)
          ▼
   $ terraform apply
   ...
   Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

   Outputs:

   app_public_ip = "54.210.12.98"
          │
          ▼
   CONSUMPTION PATHS:
   ├─ terraform output app_public_ip           (CLI, human/script use)
   ├─ terraform output -json                   (machine-readable, §30)
   ├─ module "app" { } → module.app.app_public_ip   (parent module reference, §57)
   └─ terraform_remote_state data source            (separate configuration, §48)
```

- An output's dependency on the resources/data it references is computed automatically from the expression graph — identical in principle to how resource-to-resource dependencies are inferred ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)), just applied to the output block instead.
- During `terraform plan` (before any resource is actually created), an output whose value depends on an attribute only known after creation shows as `(known after apply)` rather than a real value — the plan can't predict what the provider will assign.

## 5. Hands-On

### 5.1 Declaring a Basic Output

**Purpose:** Show the minimal `output` block syntax and its post-apply display.

**Syntax:**

```hcl
resource "aws_instance" "app" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"
}

output "app_public_ip" {
  description = "Public IP address of the app instance"
  value       = aws_instance.app.public_ip
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # aws_instance.app will be created
      + public_ip = (known after apply)

Plan: 1 to add, 0 to change, 0 to destroy.

Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

Outputs:

app_public_ip = "54.210.12.98"
```

**Production usage example:** Nearly every root module in production ends with an `outputs.tf` file surfacing the small set of values (endpoints, IDs, ARNs) that either a human operator or a downstream pipeline step actually needs after the run completes.

**Common errors:** Referencing an attribute that doesn't exist on the resource type (a typo like `aws_instance.app.public_addr`) fails `terraform validate`/`plan` with `This object does not have an attribute named "public_addr"` — a straightforward catch, but worth knowing the error looks like an attribute-name problem, not a dependency problem.

### 5.2 Outputs with `depends_on` for Non-Attribute Dependencies

**Purpose:** Show the rare case where an output needs an explicit `depends_on` because its value expression doesn't naturally reference the thing it should wait on.

**Syntax:**

```hcl
resource "aws_s3_bucket_policy" "app" {
  bucket = aws_s3_bucket.app.id
  policy = data.aws_iam_policy_document.app.json
}

output "bucket_ready" {
  description = "Signals the bucket and its policy are both fully applied"
  value       = aws_s3_bucket.app.id
  depends_on  = [aws_s3_bucket_policy.app]
}
```

**Example usage and expected output:**

```bash
$ terraform apply
# Terraform waits for aws_s3_bucket_policy.app to apply successfully
# before considering output "bucket_ready" resolved, even though the
# output's value expression only references aws_s3_bucket.app directly.

Outputs:

bucket_ready = "app-bucket-a1b2c3"
```

**Production usage example:** A module deliberately exposing an output as a "ready" signal for a resource whose meaningful completion isn't captured by any single attribute reference — used sparingly, since explicit `depends_on` on outputs is the exception, not the norm.

**Common errors:** Overusing `depends_on` on outputs to "be safe" when the natural attribute reference already creates the correct dependency is unnecessary and adds a maintenance burden — Terraform's automatic dependency inference from references ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) is sufficient in the overwhelming majority of cases.

### 5.3 Consuming Outputs: `terraform output` and Module References

**Purpose:** Show querying outputs after the fact and consuming a child module's outputs from a parent module.

**Syntax:**

```bash
terraform output app_public_ip
terraform output -json
```

```hcl
module "network" {
  source = "./modules/network"
}

resource "aws_instance" "app" {
  subnet_id = module.network.subnet_id
}
```

**Example usage and expected output:**

```bash
$ terraform output app_public_ip
"54.210.12.98"

$ terraform output -json
{
  "app_public_ip": {
    "sensitive": false,
    "type": "string",
    "value": "54.210.12.98"
  }
}

$ terraform apply
# module.network's "subnet_id" output resolves and feeds directly
# into aws_instance.app.subnet_id, establishing an implicit
# dependency on the entire network module's apply completing first.
```

**Production usage example:** A deployment script queries `terraform output -json` after `apply` to extract a newly created load balancer's DNS name and register it with an external DNS provider or update a status page — a very common CI/CD glue pattern ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)).

**Common errors:** Referencing `module.network.subnet_id` when the network module never declared a `subnet_id` output produces `Unsupported attribute` — a reminder that a module's outputs are its actual public interface; nothing inside the module is visible to a caller unless explicitly exposed as an output.

## 6. Production Usage Notes

- **Outputs are the only sanctioned way data crosses a module boundary outward** — a parent module cannot reach into a child module's internal resources directly; if a value isn't exposed as an output, it's simply invisible to the caller, which is a deliberate encapsulation boundary, not an oversight.
- **`terraform output -json` is the standard machine-readable consumption path** for CI/CD pipelines and external tooling — human-readable `terraform output` (no flags) is for interactive use, and its formatting is not a stable contract to script against.
- **Large numbers of outputs on a root module are often a sign the module's boundary is drawn wrong** — needing to expose dozens of low-level values usually means downstream consumers should instead be reading `terraform_remote_state` selectively, or the module decomposition itself should be reconsidered.

## 7. Security Considerations

- Non-sensitive outputs are printed in full after every `apply` and are visible in CI logs by default — anything even mildly sensitive should be evaluated for `sensitive = true` ([§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) before it's ever declared as a plain output.
- `terraform_remote_state` data sources ([§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md)) that read another configuration's outputs give the reading configuration visibility into every non-sensitive output of the source configuration — over-broad remote state access is a common way sensitive-adjacent data (like an internal hostname or account ID that shouldn't be widely known) ends up more exposed than intended.
- Outputs referencing resource attributes that are themselves sensitive at the provider level (e.g., certain IAM or secret-adjacent attributes some providers mark sensitive automatically) inherit that sensitivity and must be marked accordingly or Terraform will refuse to plan ([§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)).

## 8. Common Troubleshooting Scenarios

| Symptom                                                               | Likely Cause                                                                                           | Resolution Path                                                                                       |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------- |
| Output shows `(known after apply)` even after a completed `apply`     | Looking at `plan` output, not `apply` output — `plan` cannot know provider-assigned values in advance  | Re-run `terraform apply` (or check `terraform output` afterward) rather than reading the plan preview |
| `Error: Unsupported attribute` when referencing `module.x.some_value` | The child module never declared `some_value` as an output — module internals aren't visible by default | Add the missing `output` block inside the child module, or correct the referenced output name         |
| `terraform output` prints nothing at all                              | No `output` blocks are declared anywhere in the root module, or the state has no applied resources yet | Add output declarations and re-apply, or verify `terraform apply` has actually run successfully       |

## 9. Best Practices

- Give every output a `description` — like variables, outputs form a public interface, and an undocumented output forces every future consumer to read the module's internals to understand what it represents.
- Keep a root module's output surface deliberately small and focused on what's actually consumed downstream — resist exposing "everything just in case."
- Prefer letting Terraform infer output dependencies from the value expression itself; reserve explicit `depends_on` on outputs for the narrow case where the expression genuinely doesn't capture the needed dependency (5.2).

## 10. Common Anti-Patterns / Mistakes

- **Exposing every resource attribute as an output "for completeness."** This bloats the module's interface, makes it harder to evolve (removing any output is a breaking change to callers, [§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)), and obscures which outputs actually matter to consumers.
- **Forgetting to mark a genuinely sensitive output as `sensitive`.** Covered in depth in [§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md), but worth repeating here: an output is exactly as exposed as a plain variable if this step is skipped.
- **Using `terraform_remote_state` to reach deep into another team's configuration for values that were never meant to be a stable interface.** Because remote state exposes every non-sensitive output of the source configuration, this pattern tends to create tight, brittle coupling between configurations that should be more independently evolvable.

## 11. Interview Questions

**🎯 Beginner:** _"What is a Terraform output value, and when does it get its value?"_
**Model answer:** An output value is a named piece of information a Terraform configuration reports after running — typically a resource attribute like an IP address or ID that only exists once the resource is actually created. It's declared with an `output` block and a `value` expression, and it's computed and displayed after `terraform apply` completes; during `plan`, if the value depends on something not yet created, it shows as `(known after apply)` instead of a real value.
_What the interviewer is probing for:_ Basic grasp that outputs are read-only, computed, and timing-dependent on apply — not something assigned externally like an input variable.

**🎯 Intermediate:** _"How does a parent module access a value from a child module, and what happens if that value was never exposed?"_
**Model answer:** The parent module references `module.<name>.<output_name>`, where `<output_name>` must correspond to an `output` block declared inside the child module. If the child module never declared that output, the reference fails with an `Unsupported attribute` error — a child module's internal resources are not visible to its caller by default; only explicitly declared outputs cross the module boundary. This means a module's output set functions as its public interface, symmetric to its input variables.
_What the interviewer is probing for:_ Understanding of module encapsulation and that outputs are the deliberate, sole mechanism for exposing data outward — not an implementation detail.

**🎯 Senior:** _"When would you need an explicit `depends_on` on an output block, given that Terraform infers most dependencies automatically?"_
**Model answer:** Terraform automatically infers an output's dependencies from whatever resources or data sources its `value` expression references — in the overwhelming majority of cases, this is sufficient and explicit `depends_on` is unnecessary. It becomes necessary when the output needs to wait on a resource that isn't actually referenced by the value expression itself — for example, an output meant to signal "this bucket and its policy are both fully applied" where the value only references the bucket's ID but the intent is to also wait on a separate `aws_s3_bucket_policy` resource. Without the explicit `depends_on`, Terraform would have no way to know the output should wait for that unrelated resource, since dependency inference is purely reference-based.
_What the interviewer is probing for:_ Whether the candidate understands dependency inference is reference-based, not intent-based, and can identify the specific edge case where that matters.

**🎯 Architect:** _"You're reviewing a root module with 40 output declarations, most of which just pass through raw resource attributes. What concerns does this raise, and how would you restructure it?"_
**Model answer:** A large, unfocused output surface usually indicates the module's boundary is drawn at the wrong granularity — either the module is trying to be a single monolithic unit that should be decomposed into smaller, purpose-specific modules ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md), [§62](../Part8/Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md)) each with a tighter output contract, or downstream consumers are reaching for raw attributes that should instead be composed into a smaller number of higher-level, more meaningful outputs (a single `database_connection_info` object output rather than five separate host/port/username/etc. outputs). The operational risk of a sprawling output surface is that every output is effectively part of a versioned contract with every consumer (directly, or via `terraform_remote_state`), so removing or renaming any of the 40 is a breaking change somewhere — the larger the surface, the more brittle the module becomes to evolve. I'd audit actual consumption (grep for `module.<name>.<output>` references across the org, and remote-state consumers) to find which outputs are genuinely used, consolidate related raw attributes into structured object outputs where sensible, and remove or deprecate the rest with a clear versioning plan ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)).
_What the interviewer is probing for:_ Systems-level thinking about outputs as a versioned interface with real coupling costs, and a concrete methodology for cleaning up interface sprawl rather than a vague "reduce outputs" answer.

## 12. Common Misconceptions

1. **"Outputs are like variables, just for returning values instead of receiving them."** True at a high level, but the mechanics differ meaningfully: outputs are always computed from an expression (never assigned externally), always depend on the current state of resources they reference, and can be `(known after apply)` during planning in a way inputs never are.
2. **"An output is visible everywhere the moment it's declared."** It's only visible where explicitly consumed — a parent module accessing `module.x.output_name`, a `terraform_remote_state` data source reading it, or `terraform output` at the CLI — declaring it doesn't broadcast it anywhere by itself.
3. **"`terraform plan` shows the real output value before I apply."** For any output depending on a not-yet-created or changing resource attribute, plan can only show `(known after apply)` — the real value literally doesn't exist yet.
4. **"Removing an unused-looking output is always safe."** If any other configuration consumes it via `terraform_remote_state`, removing it is a breaking change invisible from within the source configuration itself — this is a real coordination risk in multi-team setups.

## 13. 🔑 Key Takeaways

- Output values are read-only, computed values declared via `output` blocks; they're the mechanism for exposing information out of a module or configuration, never assigned externally like input variables.
- Terraform automatically derives an output's dependencies from its `value` expression, mirroring the resource graph's dependency inference ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)); explicit `depends_on` on an output is the exception, needed only when the intended dependency isn't captured by the expression itself.
- Outputs are the sole mechanism data crosses a module boundary outward — a parent module can only see a child module's explicitly declared outputs, never its internal resources directly.
- `terraform output -json` is the stable, machine-readable consumption path for CI/CD and external tooling; plain `terraform output` is for interactive/human use.
- A module's output set is effectively a versioned public interface — removing or renaming outputs is a breaking change for any consumer, including ones via `terraform_remote_state` that aren't visible from within the source configuration.

## 14. Related Concepts & What's Next

[§41](./Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md) already covered the `sensitive` variant of outputs in detail; this section is the general case. [§43](./Section-43-Part6-Local-Values-Use-Cases-and-Best-Practices.md) covers local values, which are frequently used to compute intermediate expressions before they're exposed as an output. [§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md) covers `terraform_remote_state`, the cross-configuration consumption path for outputs only briefly mentioned here. [§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md) revisits outputs specifically in the module-authoring context, including conventions for structuring a module's complete input/output interface.

**Next Section:** [§43](./Section-43-Part6-Local-Values-Use-Cases-and-Best-Practices.md) — `Section-43-Part6-Local-Values-Use-Cases-and-Best-Practices.md`
