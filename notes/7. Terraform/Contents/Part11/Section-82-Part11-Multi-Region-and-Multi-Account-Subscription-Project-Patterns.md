# Section 82 (Part 11): Multi-Region and Multi-Account/Subscription/Project Patterns

## 1. Definition

**Plain language:** As infrastructure grows, teams typically need to run the same workload in multiple regions (for latency or disaster recovery) and to separate environments or teams into different AWS accounts, Azure subscriptions, or GCP projects (for security and billing isolation). Terraform supports both, but the mechanics — provider aliases for multi-region, and separate provider configurations plus cross-boundary IAM trust for multi-account — are distinct patterns that are often conflated.

**Precise definition:** **Multi-region provisioning** in Terraform uses **provider aliases** ([§13](../Part2/Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md)) — multiple `provider` blocks for the same provider type, each configured for a different region, referenced explicitly via the `provider = aws.us_west_2` argument on individual resources or passed into modules via the `providers` map. **Multi-account/subscription/project provisioning** goes a step further: it requires not just a different regional endpoint but genuinely different credentials and trust boundaries — an AWS provider alias assuming a role in a different account via `assume_role`, an Azure provider alias authenticating against a different subscription ID, or a GCP provider alias scoped to a different project ID. The two patterns compose: a real multi-region, multi-account architecture uses provider aliases along both dimensions simultaneously, and the account/subscription/project boundary is also the natural boundary for separate Terraform state files ([§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md)/[§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)), since blast radius containment is usually the whole point of the separation.

> 💡 **Tip:** A provider alias changes _where_ Terraform's API calls land (which region, which account) — it does not, by itself, change _what permissions_ those calls run with unless the alias's own credentials/`assume_role` configuration grants different permissions. Multi-region within one account typically reuses the same underlying credentials across aliases; multi-account virtually always requires each alias to assume a distinct role or use distinct credentials, because that's the actual security boundary being enforced.

## 2. Why This Matters

- **Multi-region is the more common of the two requirements** — even single-account organizations often need a second region for disaster recovery or global latency, making provider aliases a mechanic nearly every intermediate-or-above Terraform practitioner needs.
- **Multi-account/subscription/project separation is the dominant real-world pattern for security boundary enforcement** at scale — "one big account with tags" does not provide the same blast-radius containment as genuinely separate accounts/subscriptions/projects, and this shows up constantly in both interviews and real platform-team design work.
- **Getting the state-boundary decision wrong compounds** — a single sprawling state file spanning multiple accounts/regions becomes a bottleneck ([§109](../Part15/Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) and a security liability (a leaked state file exposes every account's resource details, not just one).

## 3. Prerequisites and Dependencies

Requires provider configuration and aliasing from [§13](../Part2/Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md) as direct mechanical prerequisites, remote backends from [§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md) for the state-per-boundary discussion, and IAM-as-code from [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md) for the cross-account/subscription/project trust relationships this section's patterns depend on.

## 4. Architecture / Conceptual Diagram

```text
   MULTI-REGION (single AWS account)
   ──────────────────────────────────
   provider "aws" {                    provider "aws" {
     alias  = "us_east_1"                alias  = "us_west_2"
     region = "us-east-1"                region = "us-west-2"
   }                                    }
          │                                    │
   module "app_east" {                  module "app_west" {
     source    = "./modules/app"          source    = "./modules/app"
     providers = { aws = aws.us_east_1 }  providers = { aws = aws.us_west_2 }
   }                                    }
          (same credentials, different region endpoint)

   MULTI-ACCOUNT (AWS example — cross-account assume_role)
   ────────────────────────────────────────────────────────
   provider "aws" {                    provider "aws" {
     alias = "prod"                      alias = "staging"
     assume_role {                       assume_role {
       role_arn = "arn:aws:iam::         role_arn = "arn:aws:iam::
       999900001111:role/terraform"      888800002222:role/terraform"
     }                                    }
   }                                    }
          │                                    │
   Separate STATE FILE per account ──────────────────►
   (blast radius containment IS the point of the split)

   Composed: multi-region × multi-account = a grid of
   provider aliases, one per (account, region) pair, each
   backed by its own assume_role trust and typically its
   own state file or workspace.
```

## 5. Hands-On

### 5.1 Multi-Region via Provider Aliases (AWS)

**Purpose:** Deploy the same module into two regions within one account using provider aliases.

**Syntax:**

```hcl
provider "aws" {
  alias  = "us_east_1"
  region = "us-east-1"
}

provider "aws" {
  alias  = "us_west_2"
  region = "us-west-2"
}

module "app_east" {
  source    = "./modules/app"
  providers = { aws = aws.us_east_1 }
}

module "app_west" {
  source    = "./modules/app"
  providers = { aws = aws.us_west_2 }
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # module.app_east.aws_instance.this will be created (us-east-1)
  # module.app_west.aws_instance.this will be created (us-west-2)

Plan: 2 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 2 added, 0 changed, 0 destroyed.
```

**Production usage example:** The `providers = { aws = aws.us_east_1 }` map argument on a module call is the required mechanism for passing a specific aliased provider into a child module — a module cannot select which alias to use internally; the caller decides.

**Common errors:** A child module that itself declares a hardcoded `provider "aws" { region = "..." }` block internally (rather than accepting a provider passed from the caller) cannot be reused across regions this way — this is a common module-design mistake that only surfaces once a second region is actually needed.

### 5.2 Multi-Account via `assume_role` (AWS)

**Purpose:** Provision into a different AWS account than the one the base credentials belong to, using cross-account role assumption.

**Syntax:**

```hcl
provider "aws" {
  alias  = "prod"
  region = "us-east-1"

  assume_role {
    role_arn     = "arn:aws:iam::999900001111:role/terraform-execution"
    session_name = "terraform-prod-apply"
  }
}

resource "aws_s3_bucket" "prod_artifacts" {
  provider = aws.prod
  bucket   = "prod-artifacts-999900001111"
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # aws_s3_bucket.prod_artifacts will be created

Plan: 1 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.
```

**Production usage example:** The base credentials Terraform runs with (often a CI/CD OIDC-federated identity, [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md)) typically belong to a central "management" or "tooling" account with narrow permissions of their own, whose _only_ real permission is `sts:AssumeRole` into the target account's `terraform-execution` role — this indirection means a compromised base credential alone cannot act in the target account without the target account's own trust policy also permitting it.

**Common errors:** Forgetting that the target account's `terraform-execution` role's trust policy must explicitly list the calling account/role as a trusted principal is a frequent first-setup failure — `assume_role` fails with `AccessDenied` not because the base credentials are wrong, but because the _target_ side of the trust relationship was never configured.

### 5.3 Multi-Subscription (Azure) and Multi-Project (GCP)

**Purpose:** Show the equivalent aliasing pattern for Azure subscriptions and GCP projects.

**Syntax:**

```hcl
provider "azurerm" {
  alias           = "prod"
  subscription_id = "11111111-2222-3333-4444-555555555555"
  features {}
}

resource "azurerm_resource_group" "prod" {
  provider = azurerm.prod
  name     = "prod-rg"
  location = "eastus"
}

provider "google" {
  alias   = "prod"
  project = "my-app-prod-123"
  region  = "us-central1"
}

resource "google_compute_network" "prod_vpc" {
  provider = google.prod
  name     = "prod-vpc"
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # azurerm_resource_group.prod will be created (subscription 111...555)
  # google_compute_network.prod_vpc will be created (project my-app-prod-123)

Plan: 2 to add, 0 to change, 0 to destroy.
```

**Production usage example:** Unlike AWS's `assume_role` indirection, Azure and GCP provider aliases most commonly authenticate to the target subscription/project more directly (a Service Principal scoped to that subscription, a GCP service account with permissions in that project) — the underlying identity federation model still applies ([§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md)) but the alias configuration itself is typically just a different `subscription_id`/`project` value rather than an explicit role-assumption hop.

**Common errors:** Using the same Service Principal/service account across every subscription/project alias "for simplicity" undermines the isolation the separate subscriptions/projects were meant to provide in the first place — each boundary should generally have its own scoped identity with permissions only in that boundary.

## 6. Production Usage Notes

- Real organizations almost always pair account/subscription/project separation with **separate state files** ([§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md)/[§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)) per boundary — a shared state file spanning prod and staging accounts defeats much of the isolation purpose, since anyone with access to that one state file (or the pipeline that manages it) can see and potentially affect both.
- CI/CD pipelines applying across multiple accounts/subscriptions/projects typically run as a matrix (one pipeline job per boundary, each with its own scoped credentials) rather than a single `apply` fanning out internally via aliases — this keeps blast radius contained even at the pipeline level, not just the Terraform-configuration level.
- Landing zone patterns (AWS Control Tower/Organizations, Azure Landing Zones, GCP Folders/Organization) exist specifically to standardize how new accounts/subscriptions/projects are bootstrapped with baseline IAM, networking, and logging — Terraform modules provisioning _new_ accounts/subscriptions/projects (as opposed to resources within an existing one) are a distinct, more advanced pattern than anything covered in this section.

## 7. Security Considerations

- Cross-account/subscription/project trust relationships (the `assume_role` target's trust policy, the Service Principal's subscription-scoped role assignment, the service account's project-scoped IAM binding) are exactly the kind of narrowly-scoped grant discussed in [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md) — a trust policy that's too broad (trusting an entire account rather than a specific role) undermines the isolation.
- State files containing resources from a sensitive account/subscription/project must be protected at least as strictly as that boundary's own access controls — a state file is effectively a detailed inventory of everything in that boundary, and leaking it leaks that inventory regardless of how well the boundary itself is locked down.
- Provider alias credentials (assume-role ARNs, subscription IDs, project IDs) are themselves sensitive-adjacent configuration — hardcoding a production account ID directly in a shared, widely-readable module is a minor information-disclosure risk worth avoiding via variables where the organization treats account topology as sensitive.

## 8. Common Troubleshooting Scenarios

| Symptom                                                            | Likely Cause                                                                        | Resolution Path                                                                                      |
| ------------------------------------------------------------------ | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| `AccessDenied` on `assume_role` despite correct base credentials   | Target account's role trust policy doesn't list the calling principal               | Update the target role's trust policy to explicitly trust the calling account/role                   |
| A module fails when reused in a second region                      | Module hardcodes its own `provider` block instead of accepting a passed-in provider | Remove the internal provider block; require callers to pass `providers = { aws = aws.alias }`        |
| Resources appear in the wrong account/subscription/project         | Missing or incorrect `provider = <alias>` argument on a resource/module call        | Explicitly set the `provider` argument on every resource/module that must target a non-default alias |
| One team's `apply` can see/affect another team's account resources | Shared state file spans multiple accounts/subscriptions/projects                    | Split into per-boundary state files/backends, each with its own access-scoped credentials            |

## 9. Best Practices

- Pair every account/subscription/project boundary with its own state file and its own scoped pipeline credentials — don't rely on Terraform-level aliasing alone to contain blast radius.
- Design child modules to accept providers from the caller (via the `providers` map) rather than hardcoding provider configuration internally, so the same module is reusable across regions and accounts/subscriptions/projects.
- Scope cross-boundary trust (assume-role trust policies, Service Principal role assignments, service account IAM bindings) as narrowly as the specific automation identity that needs to cross the boundary — never trust an entire account/subscription broadly for convenience.

## 10. Common Anti-Patterns / Mistakes

- **Using one shared state file across multiple accounts/subscriptions/projects** "to keep things simple," which defeats the isolation purpose those boundaries exist to provide.
- **Hardcoding provider configuration inside a child module**, making it impossible to reuse that module across regions or accounts without duplicating it.
- **Reusing the same cross-boundary identity/credentials across every account/subscription/project** instead of scoping a distinct identity per boundary, which turns a compromise of that one identity into an all-boundaries compromise.

## 11. Interview Questions

**🎯 Beginner:** _"What Terraform mechanism lets you provision resources into two different AWS regions from the same configuration?"_
**Model answer:** Provider aliases — declaring multiple `provider "aws" {}` blocks, each with a different `region` and a distinct `alias`, and then referencing the desired alias explicitly on individual resources (`provider = aws.us_west_2`) or passing it into a module via the `providers` map.
_What the interviewer is probing for:_ Basic mechanical familiarity with provider aliasing as the tool for this specific requirement.

**🎯 Intermediate:** _"What's the key difference between using a provider alias for multi-region versus multi-account provisioning in AWS?"_
**Model answer:** Multi-region aliasing typically reuses the same underlying credentials across aliases — only the `region` argument differs, since the account and its permissions are the same. Multi-account aliasing requires each alias to actually change _which account_ the calls run against, which in AWS is done via an `assume_role` block pointing at a role in the target account — this requires that target account's role to have a trust policy explicitly permitting the caller, an additional configuration step multi-region aliasing doesn't need.
_What the interviewer is probing for:_ Understanding that multi-account isn't just "another alias" — it requires an actual cross-account trust relationship to be configured on both sides.

**🎯 Senior:** _"A team wants to reuse the same VPC/compute module across dev, staging, and prod AWS accounts. How do you structure the provider and state boundaries?"_
**Model answer:** The module itself should accept a provider from its caller rather than hardcoding one, so the same module code works regardless of which account it's applied into. Each environment (dev/staging/prod) gets its own root module invocation with its own provider alias configured via `assume_role` into that environment's account, and — critically — its own separate state file/backend, not a shared one, so a mistake or compromise in one environment's pipeline can't read or affect another's state. The root modules can still share the same child module source (from a private registry or a versioned Git ref, [§58](../Part8/Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)/[§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) to avoid duplicating the actual resource logic — what's duplicated is only the thin root-module wiring (which account, which state backend), not the module implementation itself.
_What the interviewer is probing for:_ Whether the candidate separates "module reuse" (good, shared code) from "state/execution boundary reuse" (bad, defeats isolation) — a common point of confusion.

**🎯 Architect:** _"Design the account/region topology and Terraform state strategy for a company expanding from a single AWS account/single region into a genuinely global, multi-team, compliance-sensitive footprint."_
**Model answer:** Adopt an account-per-environment-per-team (or at minimum account-per-environment) structure under an AWS Organization, provisioned itself via Terraform against a small, tightly controlled management account — this is the landing-zone pattern. Within each account, apply multi-region provider aliasing for any workload with a genuine latency or disaster-recovery requirement, keeping single-region as the default for workloads without that requirement to avoid unnecessary operational complexity. State boundaries should mirror the account boundaries one-to-one at minimum — one state file (or a small number, further split by logical layer like networking vs. compute vs. data per [§106](../Part15/Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md)) per account — never spanning accounts, so a compromised or misconfigured pipeline for one team/environment cannot read or affect another's resources even indirectly through shared state. Cross-account access (a shared logging account receiving centralized logs, a shared networking account other accounts peer into) should use narrowly-scoped `assume_role` trust relationships provisioned explicitly, not broad account-level trust. This whole topology should itself be provisioned by Terraform, ideally in a bootstrap layer applied by a small, highly restricted pipeline distinct from the pipelines that manage individual team/environment accounts, so the tooling that creates isolation boundaries isn't itself running with the same broad access the boundaries are meant to constrain.
_What the interviewer is probing for:_ Whether the candidate can design a coherent, compliance-aware topology at organizational scale — landing zones, state-boundary-per-account discipline, narrowly scoped cross-account trust, and a clear separation between the bootstrap tooling and the tenant pipelines it creates — rather than just describing provider aliasing mechanics in isolation.

## 12. Common Misconceptions

1. **"A provider alias alone changes what permissions API calls run with."** It changes where calls target (region/account/subscription/project); permissions come from whatever credentials or `assume_role` configuration back that specific alias.
2. **"Multi-region and multi-account are the same kind of problem, just at different scope."** Multi-region typically reuses one identity across regions; multi-account requires an actual cross-boundary trust relationship configured on both sides.
3. **"A shared module needs a separate copy per account/environment to be reusable."** The module code can be shared and versioned identically across accounts; what should differ per account is only the root-module wiring (provider, backend), not the module implementation.
4. **"One Terraform state file can safely span multiple accounts if access to it is controlled."** Even with access control, a shared state file undermines blast-radius containment — anyone/anything with legitimate access to manage one account's resources in that state can see and potentially affect the others too.

## 13. 🔑 Key Takeaways

- Provider aliases ([§13](../Part2/Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md)) are the mechanical tool for both multi-region and multi-account provisioning, but multi-account additionally requires a real cross-boundary trust relationship (AWS `assume_role`, Azure subscription-scoped Service Principal, GCP project-scoped service account).
- Modules should accept providers from their caller rather than hardcoding provider configuration, to remain reusable across regions and accounts.
- Account/subscription/project boundaries should be matched one-to-one with separate state files and separately scoped pipeline credentials — shared state undermines the isolation those boundaries exist to provide.
- Cross-boundary trust should be scoped as narrowly as the actual automation identity needing to cross, never broadly at the account/subscription level.
- Landing-zone patterns (Control Tower, Azure Landing Zones, GCP Folders) exist for provisioning new accounts/subscriptions/projects themselves — a distinct, more advanced layer than provisioning resources within an existing one.

## 14. Related Concepts & What's Next

[§13](../Part2/Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md) supplied the provider-aliasing mechanics this section applied to two concrete real-world scenarios; [§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md)/[§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md) (state boundaries and remote backends) and [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md) (IAM as code) are the direct dependencies for the state-per-account and cross-account-trust discussions here. [§106](../Part15/Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md) (project structure at scale) revisits the state-splitting question raised in the architect answer in a broader, non-multi-cloud-specific context. [§83](./Section-83-Part11-Cost-Awareness-in-Multi-Cloud-Terraform-Design.md) closes out Part 11 by shifting from provisioning correctness to cost — the last lens this Part applies to everything built across [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md)-[§82](./Section-82-Part11-Multi-Region-and-Multi-Account-Subscription-Project-Patterns.md).

**Next Section:** [§83](./Section-83-Part11-Cost-Awareness-in-Multi-Cloud-Terraform-Design.md) — `Section-83-Part11-Cost-Awareness-in-Multi-Cloud-Terraform-Design.md`
