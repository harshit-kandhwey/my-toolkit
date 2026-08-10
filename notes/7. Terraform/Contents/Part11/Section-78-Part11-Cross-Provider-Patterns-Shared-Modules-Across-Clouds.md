# Section 78 (Part 11): Cross-Provider Patterns: Shared Modules Across Clouds

## 1. Definition

**Plain language:** A cross-provider (or "provider-agnostic") pattern is a way of writing Terraform so that the same module interface — the same input variables, the same output shape — can provision equivalent infrastructure on AWS, Azure, or GCP, with the provider-specific resource blocks hidden behind that common interface. The caller says "give me a VM with this size and this network" without needing to know or care whether that becomes an `aws_instance`, an `azurerm_linux_virtual_machine`, or a `google_compute_instance` underneath.

**Precise definition:** **Cross-provider patterns** in Terraform address the reality that HCL has no native abstraction for "a compute instance" independent of a specific provider's resource schema — each provider defines its own resource types with incompatible argument names and semantics. Because Terraform resource blocks cannot be conditionally typed at runtime (you cannot write a single `resource` block that becomes `aws_instance` or `azurerm_linux_virtual_machine` depending on a variable), provider-agnostic modules are built through **composition and selection**, not runtime polymorphism: either (a) a wrapper module that internally declares all provider-specific resources behind `count`/`for_each` conditionals gated on which provider is active, exposing one normalized output interface, or (b) a root-level pattern that selects which of several single-provider child modules to call based on a variable, with all child modules sharing an identical input/output variable contract.

> 💡 **Tip:** "Provider-agnostic" in Terraform never means "one resource block that works on any cloud" — that construct doesn't exist. It means "one _module interface_ that works on any cloud, with provider-specific resource blocks hidden inside." If you find yourself trying to make a single `resource` block conditionally become a different resource type, that's the signal you need a module boundary instead.

## 2. Why This Matters

- **Genuine multi-cloud requirements are less common than believed, but the module-interface discipline pays off even single-cloud** — a well-designed common interface makes swapping AWS for Azure in a future acquisition, disaster-recovery region, or cost-driven migration a matter of changing a variable, not rewriting configuration.
- **It clarifies what actually varies vs. what's incidental.** Building a shared interface forces an explicit decision about which arguments are truly universal (a VM needs a size, a network, a name) versus provider-specific escape hatches (AWS's `iam_instance_profile` vs. GCP's `service_account` block have no common shape).
- **It's a frequently tested architect-level interview topic** precisely because it exposes whether a candidate understands Terraform's actual capabilities (module composition) versus imagined ones (runtime resource-type polymorphism, which HCL does not support).

## 3. Prerequisites and Dependencies

Requires the AWS, Azure, and GCP provider deep dives from [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md), [§76](./Section-76-Part11-Azure-Provider-azurerm-Deep-Dive-Resource-Groups-VNets-VMs.md), and [§77](./Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md) as the concrete resource vocabulary this section abstracts over, plus module composition patterns from [§61](../Part8/Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md) and the `for_each` meta-argument from [§23](../Part3/Section-23-Part3-Meta-Arguments-Overview-count-for_each-depends_on-lifecycle.md)/[§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md), which is the mechanical tool used to conditionally instantiate provider-specific resources.

## 4. Architecture / Conceptual Diagram

```text
                     Caller (root module)
                              │
                     var.cloud_provider = "aws" | "azure" | "gcp"
                              │
                              ▼
              ┌─────────────────────────────────┐
              │   module "compute_instance"     │  ← common interface:
              │                                 │    var.name, var.size,
              │   Internally:                   │    var.network_id
              │   for_each = var.cloud_provider │
              │   == "aws"   ? {aws = {}} : {}  │
              │   == "azure" ? {azure = {}} : {}│
              │   == "gcp"   ? {gcp = {}} : {}  │
              └────────────────┬────────────────┘
                               │
              ┌────────────────┼─────────────────┐
              ▼                ▼                 ▼
      aws_instance     azurerm_linux_     google_compute_
      (for_each=1      virtual_machine    instance
       item if aws)    (for_each=1        (for_each=1
                        item if azure)     item if gcp)
              │                │                 │
              └────────────────┼─────────────────┘
                               ▼
                    output "instance_id" {
                      value = coalesce(
                        try(aws_instance.this["aws"].id, null),
                        try(azurerm_linux_virtual_machine.this["azure"].id, null),
                        try(google_compute_instance.this["gcp"].id, null)
                      )
                    }
```

- Exactly one of the three `for_each` maps ever has an element in it — the other two are always empty — so only one real resource is ever created per `apply`, but all three resource blocks exist in the module's configuration at all times.
- The output normalizes three different attribute names (`id` happens to match here, but `size`/`instance_type`/`machine_type` do not) into one consistent interface the caller depends on.

## 5. Hands-On

### 5.1 A Provider-Agnostic Compute Module via `for_each` Selection

**Purpose:** Demonstrate the core pattern — one module interface, three mutually exclusive provider-specific resource blocks selected by a variable.

**Syntax:**

```hcl
# modules/compute_instance/variables.tf
variable "cloud_provider" {
  type    = string
  validation {
    condition     = contains(["aws", "azure", "gcp"], var.cloud_provider)
    error_message = "cloud_provider must be one of: aws, azure, gcp."
  }
}

variable "name" { type = string }
variable "size" { type = string }        # normalized size label, mapped per-provider
variable "network_id" { type = string }  # subnet ID / subnetwork self_link

# modules/compute_instance/main.tf
locals {
  size_map = {
    aws   = { small = "t3.micro",     medium = "t3.small" }
    azure = { small = "Standard_B1s", medium = "Standard_B2s" }
    gcp   = { small = "e2-small",     medium = "e2-medium" }
  }
}

resource "aws_instance" "this" {
  for_each      = var.cloud_provider == "aws" ? { "aws" = true } : {}
  ami           = "ami-0abcdef1234567890"
  instance_type = local.size_map.aws[var.size]
  subnet_id     = var.network_id
  tags          = { Name = var.name }
}

resource "azurerm_linux_virtual_machine" "this" {
  for_each               = var.cloud_provider == "azure" ? { "azure" = true } : {}
  name                    = var.name
  size                    = local.size_map.azure[var.size]
  network_interface_ids   = [var.network_id]
  # ... admin_username, admin_ssh_key, os_disk, source_image_reference omitted for brevity
}

resource "google_compute_instance" "this" {
  for_each     = var.cloud_provider == "gcp" ? { "gcp" = true } : {}
  name         = var.name
  machine_type = local.size_map.gcp[var.size]
  zone         = "us-central1-a"
  boot_disk {
    initialize_params { image = "debian-cloud/debian-12" }
  }
  network_interface {
    subnetwork = var.network_id
  }
}

# modules/compute_instance/outputs.tf
output "instance_id" {
  value = coalesce(
    try(aws_instance.this["aws"].id, null),
    try(azurerm_linux_virtual_machine.this["azure"].id, null),
    try(google_compute_instance.this["gcp"].id, null),
  )
}
```

**Example usage and expected output:**

```hcl
module "web" {
  source         = "./modules/compute_instance"
  cloud_provider = "azure"
  name           = "web-vm"
  size           = "small"
  network_id     = azurerm_network_interface.web_nic.id
}
```

```bash
$ terraform apply
  # module.web.azurerm_linux_virtual_machine.this["azure"] will be created
  # (aws_instance.this and google_compute_instance.this both resolve to
  #  empty for_each maps and produce no resources)

Plan: 1 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

$ terraform output instance_id
"/subscriptions/.../virtualMachines/web-vm"
```

**Production usage example:** This pattern is genuinely used in organizations with a real multi-cloud mandate (regulated industries often required to maintain provisioning capability on a second cloud for resilience, or companies mid-acquisition merging two cloud estates) — but it requires all three providers to be configured in the same Terraform run ([§13](../Part2/Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md), provider aliases), which is itself a real operational cost most single-cloud teams should not take on speculatively.

**Common errors:** Forgetting the `validation` block on `cloud_provider` means a typo (`"awz"`) silently produces zero resources across all three `for_each` maps with no error — `apply` reports "0 to add" with no explanation, which is far more confusing than a clear validation failure at plan time.

### 5.2 Root-Level Module Selection Pattern

**Purpose:** Show the alternative to 5.1 — instead of one module hiding three resource types internally, three separate single-provider child modules share an identical variable contract, and the root module picks which to call.

**Syntax:**

```hcl
# each of these modules independently exposes:
#   var.name, var.size, var.network_id  →  output.instance_id
module "aws_compute" {
  source = "./modules/aws-compute"
  count  = var.cloud_provider == "aws" ? 1 : 0
  name   = var.name
  size   = var.size
}

module "azure_compute" {
  source = "./modules/azure-compute"
  count  = var.cloud_provider == "azure" ? 1 : 0
  name   = var.name
  size   = var.size
}

module "gcp_compute" {
  source = "./modules/gcp-compute"
  count  = var.cloud_provider == "gcp" ? 1 : 0
  name   = var.name
  size   = var.size
}
```

**Example usage and expected output:**

```bash
$ terraform apply -var cloud_provider=gcp
  # module.gcp_compute[0].google_compute_instance.this will be created
Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** This pattern is preferred over 5.1 when the provider-specific modules are large or maintained by different sub-teams (a platform team's AWS module, a separate Azure specialist's module) — it avoids one mega-module owning all three providers' full resource surface, at the cost of the caller managing three `count`-gated module blocks instead of one.

**Common errors:** Because `count` here is `0` or `1` per module block, referencing `module.aws_compute.instance_id` directly (without an index) fails with "this object does not have an attribute" when count is `0` — callers must use `module.aws_compute[0].instance_id` guarded by the same conditional, or better, wrap the whole thing in a `coalesce()`/`try()` output pattern identical to 5.1's.

## 6. Production Usage Notes

- The `for_each`-selection style (5.1) centralizes provider-specific logic in one module, which is easier to keep interface-consistent but grows large and mixes unrelated provider concerns in one file as more resource types are added.
- The root-level selection style (5.2) scales better organizationally (separate ownership per provider module) but pushes the coalesce/try normalization burden up to every caller unless a thin wrapper module re-centralizes it.
- Both styles require every provider actually in play to be configured (`provider "aws" {}`, `provider "azurerm" {}`, `provider "google" {}`) in the same Terraform configuration even when only one is active for a given `apply` — Terraform validates provider configuration blocks regardless of whether their resources end up with zero instances.

## 7. Security Considerations

- A provider-agnostic module that silently produces zero resources on a variable typo (as in 5.1's common-errors note) is a security-relevant failure mode, not just an inconvenience — a `plan` showing "0 to add" for what was expected to be a production security control (e.g., a firewall/NSG module) can be mistaken for "nothing changed" when it actually means "nothing was created at all."
- Provider credentials for all three clouds must be available to whatever CI/CD identity runs `apply` against a genuinely multi-cloud module, which multiplies the blast radius of a compromised pipeline threefold compared to a single-cloud configuration — least-privilege scoping ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)) matters proportionally more here.

## 8. Common Troubleshooting Scenarios

| Symptom                                                               | Likely Cause                                                                                    | Resolution Path                                                                                                    |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| `apply` reports "0 to add" with no created resources                  | Typo or unhandled value in the provider-selector variable, `for_each`/`count` all resolve empty | Add a `validation` block restricting the variable to the exact supported set                                       |
| `Error: Invalid index` referencing a `count`-gated module's output    | Referencing `module.x.output` without `[0]` when `count` may be `0`                             | Index the module block explicitly, or centralize normalization behind a `coalesce()`/`try()` output                |
| Configuration fails to validate even though only one provider is used | All three provider blocks are still required in configuration regardless of which is "active"   | Configure all providers in play, or split into fully separate root modules per provider if only one is ever needed |
| Output value is `null` unexpectedly                                   | None of the `try()` calls in a `coalesce()` chain matched an existing resource                  | Verify the selector variable's value actually matches one of the `for_each` conditions                             |

## 9. Best Practices

- Always add a `validation` block constraining a provider-selector variable to the exact supported set — silent zero-resource applies are a worse failure mode than a clear validation error.
- Normalize outputs (IDs, IPs, sizes) behind a single `coalesce()`/`try()` pattern so callers never need to know which provider's resource actually produced the value.
- Reserve genuine cross-provider modules for cases with a real multi-cloud requirement — building this abstraction speculatively for a single-cloud team adds real maintenance cost (three resource schemas to track, three sets of provider version constraints) for no realized benefit.

## 10. Common Anti-Patterns / Mistakes

- **Trying to make one `resource` block conditionally become different resource types.** This isn't supported by HCL at all — the resource type in a `resource "TYPE" "NAME"` block is a static identifier, not a runtime-evaluated expression; module-boundary selection (5.1/5.2) is the only mechanism available.
- **Building a "just in case" multi-cloud abstraction for a team that only ever deploys to one cloud.** This is one of the most cited real-world Terraform anti-patterns — the abstraction cost (three resource schemas, three provider version constraints, three sets of credentials in CI) is paid continuously while the benefit (easy migration) may never be realized.
- **Assuming a normalized "size" label maps cleanly across providers.** `t3.small`, `Standard_B2s`, and `e2-medium` are not equivalent in vCPU/RAM even when a module's `size_map` pairs them as "the small tier" — treating them as interchangeable without documenting the actual specs misleads capacity planning.

## 11. Interview Questions

**🎯 Beginner:** _"Can a single Terraform `resource` block become either an `aws_instance` or an `azurerm_linux_virtual_machine` depending on a variable?"_
**Model answer:** No — the resource type in `resource "TYPE" "NAME"` is a fixed identifier, not something that can be computed at runtime. To support multiple providers behind one interface, you declare both resource blocks (typically gated with `for_each` or `count` so only one ever actually creates anything) inside a module, and expose one normalized output.
_What the interviewer is probing for:_ Whether the candidate understands this as a real language limitation rather than assuming Terraform has some form of dynamic resource typing.

**🎯 Intermediate:** _"Describe two different ways to structure a Terraform module so it can provision equivalent infrastructure on AWS or Azure based on a variable."_
**Model answer:** One: a single module internally declares both provider-specific resource types, each gated by `for_each` so exactly one is ever non-empty, and exposes one normalized output via `coalesce()`/`try()` across both possible resources. Two: two separate single-provider child modules share an identical variable contract, and the root module conditionally calls one or the other via `count`, indexing the resulting module output. The first centralizes complexity in one module; the second distributes ownership across provider-specific modules but pushes output normalization up to the caller.
_What the interviewer is probing for:_ Concrete familiarity with both real patterns, not just the concept in the abstract.

**🎯 Senior:** _"A cross-cloud compute module silently produced zero resources during a production `apply` because of a typo in the provider-selector variable, and nobody noticed until the environment was found to be missing a VM days later. How do you prevent this class of failure?"_
**Model answer:** The root cause is that `for_each`/`count` conditionals fail silently — an unmatched value just produces empty maps/zero counts rather than an error, and "0 to add" in a large `apply` with many other resources is easy to miss in review. The fix is a `validation` block on the selector variable restricting it to the exact supported literal set (`contains(["aws","azure","gcp"], var.cloud_provider)`), which converts the typo into an immediate `terraform plan`-time error instead of a silent no-op. As a second layer, CI pipelines applying such modules should assert expected resource counts in the plan JSON output ([§30](../Part4/Section-30-Part4-terraform-show-output-and-Machine-Readable-JSON-Output.md)) for critical modules, catching unexpected zero-resource plans even when the variable itself is technically valid but wrong for the intended target.
_What the interviewer is probing for:_ Recognition that Terraform's conditional-resource mechanisms fail silently by default, and a concrete, layered mitigation (validation block plus CI-level plan assertions), not just "add a validation block" in isolation.

**🎯 Architect:** _"A platform team wants to build a general-purpose 'compute' module abstracting AWS, Azure, and GCP for every application team in the company, arguing it future-proofs against a cloud migration. What's your architectural pushback, if any?"_
**Model answer:** The pushback isn't that the pattern is wrong — it's real and works, as shown in 5.1/5.2 — it's that the cost is paid by every team continuously (learning a bespoke abstraction on top of three providers' native documentation, debugging normalized outputs that hide real per-provider differences, maintaining three provider version constraints) while the benefit (an actual cloud migration) is speculative and, if it ever happens, is a large enough project that a purpose-built migration effort at that time would likely produce a better abstraction than one guessed years in advance anyway. The better default is single-provider modules per team, with the cross-provider abstraction reserved for the specific subset of infrastructure with a genuine, current multi-cloud requirement (e.g., a DR posture mandated by compliance, or an actual in-flight multi-cloud workload) — introduced narrowly there, not company-wide speculatively. If the team insists on the general abstraction, the real ask should be: which teams have a concrete multi-cloud requirement today, and can the module scope start there and expand only as more teams demonstrate the same real need.
_What the interviewer is probing for:_ Willingness to push back on speculative abstraction with a cost/benefit argument, and understanding that "future-proofing" is not free — this mirrors the general YAGNI critique applied specifically to infrastructure module design.

## 12. Common Misconceptions

1. **"Provider-agnostic Terraform means writing one resource block that works on any cloud."** No such construct exists; the pattern is module-boundary composition with multiple provider-specific resource blocks, not runtime polymorphism.
2. **"A cross-provider module removes the need to understand each provider's actual resource schema."** It only hides that complexity from the _caller_ — someone still has to write and maintain each provider-specific resource block correctly inside the module.
3. **"Normalized size tiers (`small`/`medium`) mean equivalent compute specs across providers."** They're an approximate mapping the module author chose; actual vCPU/RAM/pricing differ per provider and should be documented, not assumed equivalent.
4. **"Building a multi-cloud abstraction is always good engineering discipline."** For teams with no real multi-cloud requirement, it's frequently a net-negative — real ongoing maintenance cost for a speculative, possibly-never-realized benefit.

## 13. 🔑 Key Takeaways

- Terraform has no runtime resource-type polymorphism; cross-provider patterns work by hiding multiple provider-specific resource blocks behind a shared module interface, selected via `for_each`/`count`, never by one block dynamically becoming another type.
- Two structurally different approaches exist: one large module internally selecting among provider-specific resources, or several single-provider modules selected at the root — the tradeoff is centralized complexity versus distributed ownership.
- Conditional resource selection fails silently on invalid input; a `validation` block on the selector variable is the standard, necessary safeguard.
- All configured providers must be valid even when only one is "active" for a given `apply`, since Terraform validates provider blocks regardless of resulting instance counts.
- Building this abstraction should be driven by a genuine, current multi-cloud requirement, not spec­ulative future-proofing — the ongoing cost is real and continuous even when the benefit never materializes.

## 14. Related Concepts & What's Next

[§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md), [§76](./Section-76-Part11-Azure-Provider-azurerm-Deep-Dive-Resource-Groups-VNets-VMs.md), and [§77](./Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md) supplied the concrete AWS, Azure, and GCP resource vocabulary this section built the abstraction over. [§61](../Part8/Section-61-Part8-Module-Composition-Patterns-and-Nested-Modules.md) (module composition patterns) and [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) (`count` vs. `for_each`) are the mechanical foundations this section assumed. [§79](./Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md) now applies these same cross-provider considerations specifically to networking constructs — peering, subnets, and security groups/NSGs — as a more concrete, narrower case than the general pattern covered here.

**Next Section:** [§79](./Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md) — `Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md`
