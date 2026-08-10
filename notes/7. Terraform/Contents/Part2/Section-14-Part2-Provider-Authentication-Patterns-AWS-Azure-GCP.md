# Section 14 (Part 2): Provider Authentication Patterns (AWS/Azure/GCP)

## 1. Definition

**Plain language:** A `provider "aws" {}` block being present in your configuration doesn't mean Terraform automatically knows how to authenticate to your AWS account. Every provider needs credentials from somewhere — and each major cloud has its own set of conventions, environment variables, and identity mechanisms for supplying them, ranging from "paste an access key" (never recommended) to "assume a role with no long-lived credentials at all" (the production standard).

**Precise definition:** Provider authentication is the process by which a provider plugin instance ([§8](./Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md), [§9](./Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)) obtains the credentials it needs to sign and authorize API calls against its target platform. Each major cloud provider's Terraform provider implements a **credential resolution chain** — an ordered list of places it checks for credentials, stopping at the first one that succeeds — modeled closely on that cloud's own SDK conventions: the **AWS provider** follows the AWS SDK's standard chain (explicit provider arguments → environment variables → shared credentials file → **IAM role** via EC2 instance metadata, ECS task role, or IRSA on EKS); the **Azure provider (`azurerm`)** supports Azure CLI authentication, environment-variable-based Service Principal auth (client ID/secret or client certificate), OpenID Connect (OIDC) federation for CI/CD, and **Managed Identity** for Azure-hosted execution; the **GCP provider (`google`)** supports Application Default Credentials (ADC) via `gcloud` CLI login, a downloaded Service Account key file, environment-based Workload Identity Federation, and **attached Service Account** credentials when running on GCP compute. Across all three, the universally preferred production pattern is the same: **short-lived, automatically-rotated credentials obtained via an identity mechanism tied to the execution environment** (IAM role, Managed Identity, attached Service Account, or OIDC federation) rather than long-lived static keys stored anywhere.

> 💡 **Tip:** The single authentication mistake that causes the most real-world security incidents across all three clouds is the same one, just with different names: **long-lived static credentials (AWS access keys, Azure Service Principal client secrets, GCP Service Account JSON key files) checked into version control, hardcoded in a `provider {}` block, or left in a `.tfvars` file that gets committed.** Every cloud's credential chain supports a zero-static-secret path (IAM role / Managed Identity / Workload Identity Federation) specifically to eliminate this risk — reaching for that path first, and treating static keys as a last resort for genuinely credential-less environments (some local dev scenarios), is the correct default posture, not an advanced optimization.

## 2. Why This Matters

- **Credential leakage via hardcoded provider auth or committed `.tfvars` files is one of the most common real-world cloud security incidents involving Terraform**, and it is entirely preventable by following each cloud's recommended identity-based authentication pattern instead of static keys.
- **The credential resolution chain's ordering determines which credentials actually get used when multiple sources are present simultaneously — a frequent source of "why is it using the wrong account" confusion**, especially on developer machines with multiple AWS profiles or Azure CLI sessions active.
- **CI/CD pipelines increasingly use OIDC federation instead of stored long-lived secrets**, letting GitHub Actions, GitLab CI, or other CI systems assume a cloud role/identity directly via a signed token exchange with zero static credentials stored in the CI system at all — this is now the recommended default for new pipelines across AWS, Azure, and GCP.
- **Each cloud's terminology and mechanism differs enough that assuming "it works like AWS" when configuring Azure or GCP auth is a real, common mistake** — Azure's Service Principal model, GCP's Service Account model, and AWS's IAM role model are conceptually similar but not identical in their configuration surface.

## 3. Prerequisites and Dependencies

Builds directly on [§9](./Section-09-Part2-Provider-Configuration-and-Version-Constraints.md) (Provider Configuration and Version Constraints), which introduced the `provider {}` block this section fills in with authentication specifics, and [§13](./Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md) (Multiple Provider Instances and Provider Aliases), since multi-account authentication (via `assume_role`/impersonation) is a common aliasing use case. [§8](./Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md)'s RPC model explains why the provider process — not Terraform Core — is what actually holds and uses these credentials. [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) (Least-Privilege IAM for Terraform Execution Roles) and [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) (Secrets in State) return to the security dimension of this topic in full depth; this section focuses on the mechanics of _how_ each provider authenticates, not the broader IAM design principles.

## 4. Architecture / Conceptual Diagram

```text
AWS Provider Credential Chain (checked in order, first match wins):
  1. Explicit provider block arguments (access_key/secret_key) -- AVOID in production
  2. Environment variables: AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY / AWS_SESSION_TOKEN
  3. Shared credentials file: ~/.aws/credentials (profile-based)
  4. assume_role block (STS AssumeRole -- cross-account access)
  5. EC2 instance metadata / ECS task role / EKS IRSA (IAM role, PREFERRED for
     workloads actually running on AWS)

Azure Provider (azurerm) Credential Chain:
  1. Explicit provider block arguments -- AVOID in production
  2. Environment variables: ARM_CLIENT_ID / ARM_CLIENT_SECRET / ARM_TENANT_ID / ARM_SUBSCRIPTION_ID
  3. OIDC token federation (ARM_USE_OIDC=true, for CI/CD)
  4. Azure CLI session (`az login`) -- common for local dev
  5. Managed Identity (PREFERRED for workloads running on Azure compute)

GCP Provider (google) Credential Chain:
  1. Explicit provider block arguments (credentials = file(...)) -- AVOID in production
  2. GOOGLE_APPLICATION_CREDENTIALS env var (path to a Service Account key file)
  3. gcloud CLI Application Default Credentials (`gcloud auth application-default login`)
  4. Workload Identity Federation (for CI/CD, no stored keys)
  5. Attached Service Account (PREFERRED for workloads running on GCP compute)

           ┌────────────────────────────────────────────────┐
           │        Common shape across all three:          │
           │                                                │
           │  Static, long-lived secrets  ──►  AVOID        │
           │         (bottom of preference)                 │
           │                                                │
           │  Identity-based, short-lived,  ──►  PREFERRED  │
           │  auto-rotated credentials tied                 │
           │  to the execution environment                  │
           │  (IAM role / Managed Identity /                │
           │   attached Service Account / OIDC)             │
           └────────────────────────────────────────────────┘
```

## 5. Hands-On

### 5.1 AWS: IAM Role Assumption via `assume_role`

**Purpose:** Provision into a target AWS account using a role assumed from a base identity, without ever handling that target account's long-lived credentials — the standard multi-account pattern.

**Syntax:**

```hcl
provider "aws" {
  region = "us-east-1"
  assume_role {
    role_arn     = "<target_account_role_arn>"
    session_name = "<session_identifier>"
  }
}
```

**Example usage and expected output:**

```hcl
provider "aws" {
  region = "us-east-1"
  assume_role {
    role_arn     = "arn:aws:iam::123456789012:role/terraform-execution"
    session_name = "terraform-ci"
  }
}
```

```bash
$ terraform plan
data.aws_caller_identity.current: Reading...
data.aws_caller_identity.current: Read complete after 1s [id=123456789012]
# subsequent provider calls now execute as the assumed role
```

**Production usage example:** A central CI pipeline holds a single base IAM identity (itself often an OIDC-federated role, 5.3) that has permission to `sts:AssumeRole` into per-environment execution roles (`terraform-execution` in dev, staging, prod accounts) — the pipeline never holds standing credentials for any target account directly, only the ability to assume into scoped roles per run.

**Common errors:** `Error: error configuring Terraform AWS Provider: ... AccessDenied ... is not authorized to perform: sts:AssumeRole` — the base identity lacks a trust relationship permitting it to assume the target role; the fix is on the target role's trust policy, not the Terraform configuration.

### 5.2 Azure: Service Principal via Environment Variables

**Purpose:** Authenticate the `azurerm` provider without hardcoding credentials in configuration, using the standard environment-variable convention CI systems commonly inject as secrets.

**Syntax:**

```hcl
provider "azurerm" {
  features {}
  # no explicit credential arguments -- resolved from ARM_* environment variables
}
```

**Example usage and expected output:**

```bash
export ARM_CLIENT_ID="00000000-0000-0000-0000-000000000000"
export ARM_CLIENT_SECRET="<secret>"
export ARM_TENANT_ID="11111111-1111-1111-1111-111111111111"
export ARM_SUBSCRIPTION_ID="22222222-2222-2222-2222-222222222222"

$ terraform plan
# azurerm provider picks up ARM_* env vars automatically, no provider block config needed
```

**Production usage example:** CI/CD systems inject `ARM_CLIENT_ID`/`ARM_CLIENT_SECRET`/`ARM_TENANT_ID`/`ARM_SUBSCRIPTION_ID` as masked pipeline secrets rather than storing them in any file the pipeline checks out from source control, keeping the `provider "azurerm" {}` block itself entirely free of credential material.

**Common errors:** The mandatory empty `features {}` block being omitted — `azurerm` requires this block to exist (even empty) as of provider 2.x+, and omitting it produces `Error: "features": required field is not set` regardless of whether authentication itself is correctly configured — a frequent first-time `azurerm` stumbling block unrelated to credentials at all.

### 5.3 GCP and AWS: OIDC Federation from CI/CD (No Stored Secrets)

**Purpose:** Let a CI/CD system (e.g., GitHub Actions) authenticate directly to a cloud provider via a signed OIDC token exchange, with zero long-lived credentials stored in the CI system.

**Syntax:**

```yaml
# GitHub Actions workflow snippet (AWS example)
permissions:
  id-token: write
  contents: read
steps:
  - uses: aws-actions/configure-aws-credentials@v4
    with:
      role-to-assume: arn:aws:iam::123456789012:role/github-actions-terraform
      aws-region: us-east-1
  - run: terraform plan
```

**Example usage and expected output:**

```text
Configuring credentials for Amazon Web Services
Assuming role with OIDC
Authenticated as arn:aws:sts::123456789012:assumed-role/github-actions-terraform/GitHubActions
```

**Production usage example:** This is now the recommended default for any new CI/CD pipeline across AWS, Azure, and GCP — the CI system's own signed identity token is exchanged directly for short-lived cloud credentials scoped to a specific pre-configured trust relationship (the AWS IAM role's trust policy, Azure's federated credential, or GCP's Workload Identity Pool provider), with nothing stored as a static CI secret at all, eliminating an entire class of "leaked CI secret" incidents.

**Common errors:** `Not authorized to perform sts:AssumeRoleWithWebIdentity` (AWS) or equivalent — almost always a misconfigured trust policy/federated credential that doesn't correctly match the CI system's token issuer, audience, and subject claims (e.g., restricting to a specific repository and branch) rather than a Terraform-side misconfiguration.

## 6. Production Usage Notes

- **Local developer authentication and CI authentication should generally use different mechanisms deliberately.** Developers commonly use `aws sso login` / `az login` / `gcloud auth application-default login` interactively for local `plan`/`apply`, while CI uses OIDC federation or an assumed role with no interactive component — conflating the two (e.g., trying to use a developer's personal SSO session inside CI) doesn't scale and isn't automatable.
- **`TF_VAR_*` environment variables are for Terraform input variables, not provider credentials** — a common early confusion; provider credentials use each cloud's own environment variable convention (`AWS_*`, `ARM_*`, `GOOGLE_*`), which the provider reads directly, entirely separate from Terraform's own variable system ([§40](../Part6/Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md) covers `TF_VAR_*` in full).
- **Provider authentication failures surface at `plan` time (during the first RPC call requiring credentials), not at `init` time.** `terraform init` only needs to download the provider binary, not authenticate — a team can have a perfectly successful `init` and still hit a credential error on the very first `plan`, which is the correct and expected boundary given [§8](./Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md)'s separation of provider installation from provider configuration.

## 7. Security Considerations

- Never commit static credentials (AWS access keys, Azure Service Principal secrets, GCP Service Account key files) to version control, even in `.tfvars` files intended to be gitignored — a single missed `.gitignore` entry turns a config mistake into a credential leak; use CI secret stores or, preferably, OIDC federation to avoid storing them anywhere at all.
- Prefer the identity-based, zero-static-secret path on every cloud whenever the execution environment supports it: IAM roles (AWS), Managed Identity (Azure), and attached Service Accounts (GCP) for workloads actually running on that cloud's compute; OIDC federation for CI/CD systems running elsewhere.
- Scope every Terraform execution identity — whether an assumed role, a Service Principal, or a Service Account — to the minimum permissions the specific configuration actually needs ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)), and separate plan-time (read-only) from apply-time (write) credentials wherever the pipeline structure allows ([§12](./Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md)'s execution-model discussion covers why this split is mechanically possible).
- Rotate any long-lived credentials that do remain in use (some legacy or constrained environments genuinely can't yet use identity federation) on a defined schedule, and treat provider authentication errors from expired/rotated credentials as an expected, planned event with a documented runbook — not a surprise incident.

## 8. Common Troubleshooting Scenarios

| Symptom                                                              | Likely Cause                                                                                                                                                            | Resolution Path                                                                                                                                            |
| -------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `No valid credential sources found` (AWS) or equivalent on Azure/GCP | No credential source in the resolution chain resolved successfully                                                                                                      | Verify environment variables, CLI login session, or attached identity are actually present in the execution environment                                    |
| Terraform authenticates as the wrong account/subscription/project    | Multiple credential sources present simultaneously; an unintended one wins per the resolution chain's precedence order                                                  | Explicitly set the intended profile/subscription/project via environment variables or provider arguments rather than relying on ambient default resolution |
| `Error: "features": required field is not set` (azurerm)             | Mandatory empty `features {}` block omitted from the `provider "azurerm"` block                                                                                         | Add `features {}` — unrelated to actual credential configuration                                                                                           |
| OIDC-based CI authentication fails with an authorization/trust error | CI system's token issuer, audience, or subject claim doesn't match the cloud-side trust configuration (role trust policy, federated credential, Workload Identity Pool) | Verify the exact claim matching rules on the cloud side against the CI system's actual token contents                                                      |

## 9. Best Practices

- Default to identity-based authentication (IAM role, Managed Identity, attached Service Account, or OIDC federation) on every cloud; treat static long-lived credentials as a last resort, not a starting point.
- Keep local developer authentication (interactive CLI login) and CI/CD authentication (OIDC federation or assumed roles) as deliberately separate mechanisms rather than trying to unify them.
- Never store cloud credentials in `.tf`, `.tfvars`, or any file committed to version control, regardless of `.gitignore` intentions.
- Separate plan-time (read-only) and apply-time (write) execution identities in CI/CD pipelines wherever the pipeline architecture supports it.

## 10. Common Anti-Patterns / Mistakes

- **Hardcoding `access_key`/`secret_key` (or their Azure/GCP equivalents) directly as literal values in a `provider {}` block.** The single most damaging and most avoidable Terraform authentication mistake; every cloud's provider supports credential resolution without literal in-file values.
- **Storing a long-lived Service Account JSON key file or Service Principal secret as a CI pipeline secret when OIDC federation is available and supported.** Adds an unnecessary standing credential that must be rotated and can be leaked, when a zero-static-secret alternative exists.
- **Assuming Azure or GCP authentication "works the same as AWS" without checking that provider's specific conventions.** Each provider's environment variable names, required blocks (like `azurerm`'s `features {}`), and credential chain ordering differ in real, non-obvious ways.
- **Debugging authentication failures by guessing and re-running `apply` repeatedly rather than checking which credential source is actually being resolved.** Each provider offers explicit ways to introspect this (e.g., `aws sts get-caller-identity`, `az account show`, `gcloud auth list`) that should be checked directly before assuming Terraform itself is misbehaving.

## 11. Interview Questions

**🎯 Beginner:** _"What's the recommended way to supply AWS credentials to the Terraform AWS provider — hardcoding them in the `provider` block, or something else?"_
**Model answer:** Something else — hardcoding `access_key`/`secret_key` literal values in the `provider "aws" {}` block is explicitly discouraged because it puts long-lived credentials in version control. The recommended approaches are environment variables for local/CI use, or — best of all for workloads actually running on AWS — an attached IAM role (EC2 instance profile, ECS task role, or EKS IRSA) requiring no stored credentials at all, since the AWS SDK's credential chain resolves these automatically.
_What the interviewer is probing for:_ Basic security awareness about credential handling, a fundamental expectation for anyone using Terraform against real cloud accounts.

**🎯 Intermediate:** _"Explain what `assume_role` does in an AWS provider block, and why it's commonly used even when the base identity already has AWS credentials."_
**Model answer:** `assume_role` has the provider call AWS STS's `AssumeRole` API using the base identity's credentials to obtain temporary, short-lived credentials scoped to a different IAM role — often in a different AWS account entirely. It's commonly used even when the base identity already has credentials because it enables cross-account provisioning without ever holding standing credentials for the target account directly: a central CI identity can assume into per-environment (dev/staging/prod) execution roles, each scoped with only the permissions that environment's Terraform run actually needs, keeping account boundaries and permission scoping clean.
_What the interviewer is probing for:_ Understanding of role assumption as an access-scoping mechanism, not just an authentication technicality.

**🎯 Senior:** _"A CI pipeline currently stores an AWS access key and secret as a GitHub Actions secret to run Terraform. What's the security concern, and how would you migrate it to OIDC federation?"_
**Model answer:** The concern is that a static access key/secret is a long-lived credential stored in the CI system — if that secret leaks (misconfigured logging, a compromised dependency in the pipeline, an over-permissioned collaborator with secret access), it grants standing access until manually rotated or revoked, with no automatic expiration. Migrating to OIDC federation involves: creating an IAM OIDC identity provider trusting GitHub Actions' token issuer (`token.actions.githubusercontent.com`); creating an IAM role with a trust policy restricting `sts:AssumeRoleWithWebIdentity` to specific claims (repository, branch, or environment, via the `sub` claim); granting the workflow `permissions: id-token: write`; and replacing the stored access key/secret with the `aws-actions/configure-aws-credentials` action's `role-to-assume` input, pointing at that new role. The end state has zero long-lived AWS credentials stored in GitHub at all — the workflow authenticates via a per-run, short-lived token exchange instead.
_What the interviewer is probing for:_ Practical, specific knowledge of a real, common migration every team maturing their CI/CD security posture goes through — not just an abstract endorsement of "OIDC is better."

**🎯 Architect:** _"Design the credential architecture for a multi-cloud Terraform setup (AWS, Azure, GCP) provisioned from a single central CI/CD platform, covering both least privilege and operational maintainability."_
**Model answer:** Each cloud gets its own zero-stored-secret trust relationship configured to accept the CI platform's OIDC tokens directly: an AWS IAM OIDC provider + role, an Azure federated credential on an App Registration, and a GCP Workload Identity Pool + provider — each scoped via claim matching (repository, branch/environment, or a custom claim) to only the specific pipelines that legitimately need that cloud's access. Within each cloud, further scope by environment: separate execution roles/Service Principals/Service Accounts per environment (dev/staging/prod), each holding only the permissions that environment's Terraform configurations require ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)), reachable via a further `assume_role`/impersonation hop from a narrower base identity rather than one broad per-cloud identity covering every environment. Plan-time and apply-time credentials are split per environment where the pipeline architecture allows, granting read-only access for PR-triggered plans and write access only for the apply stage post-approval. Operationally, this whole configuration (the OIDC trust relationships, roles, and their permission policies) is itself managed as Terraform code — in a bootstrap/foundational configuration deliberately separate from the workloads it grants access to — so the credential architecture is versioned, reviewed, and auditable the same way application infrastructure is.
_What the interviewer is probing for:_ Whether the candidate can design a coherent, least-privilege, zero-static-secret credential architecture spanning multiple clouds and environments — connecting authentication mechanics to a genuinely production-grade security design, not just listing each cloud's auth method in isolation.

## 12. Common Misconceptions

1. **"`TF_VAR_` environment variables are how you pass cloud credentials to a provider."** `TF_VAR_*` populates Terraform input variables ([§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)–[§40](../Part6/Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md)); cloud credentials use each provider's own environment variable convention (`AWS_*`, `ARM_*`, `GOOGLE_*`), read directly by the provider, entirely separate from Terraform's variable system.
2. **"Authentication failures mean `terraform init` failed."** `init` only downloads and installs the provider binary; authentication is only attempted on the first RPC call requiring credentials, which happens during `plan`, not `init`.
3. **"Azure and GCP authenticate the same way as AWS, just with different environment variable names."** The underlying identity models differ meaningfully — Azure's Service Principal/Managed Identity model and GCP's Service Account/Workload Identity model each have distinct configuration surfaces and required blocks (like `azurerm`'s mandatory `features {}`) beyond just naming differences.
4. **"Static access keys are simpler and therefore an acceptable trade-off for production use."** They're simpler to set up initially but carry meaningfully higher standing risk than identity-based or federated authentication, which modern tooling (OIDC actions, cloud CLI integrations) has made no harder to configure in practice.

## 13. 🔑 Key Takeaways

- Each major cloud's Terraform provider implements its own ordered credential resolution chain, checking multiple sources and stopping at the first successful one.
- The universally preferred production pattern across AWS, Azure, and GCP is identity-based, short-lived, automatically-rotated credentials (IAM role, Managed Identity, attached Service Account, or OIDC federation) — not static long-lived keys.
- Provider authentication is attempted at `plan` time (the first RPC call needing credentials), not at `init` time, which only installs the provider binary.
- OIDC federation is now the recommended default for CI/CD pipelines across all three major clouds, eliminating stored static secrets entirely.
- Cloud credentials and Terraform's own `TF_VAR_*` input variable mechanism are entirely separate systems that should not be conflated.

## 14. Related Concepts & What's Next

[§9](./Section-09-Part2-Provider-Configuration-and-Version-Constraints.md) introduced the `provider {}` block this section fills in with concrete authentication mechanics. [§13](./Section-13-Part2-Multiple-Provider-Instances-and-Provider-Aliases.md)'s provider aliasing is frequently combined with `assume_role`/impersonation for multi-account patterns, as shown in 5.1. [§8](./Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md)'s RPC model explains why credentials are held and used by the provider process itself, not Terraform Core. [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) and [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) return to least-privilege IAM design and state-related secrets risk in full depth later in the roadmap. This closes out Part 2's core architecture coverage — Part 3 shifts into HCL language mechanics itself, beginning with [§15](../Part3/Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md)'s treatment of blocks, arguments, and identifiers, the actual syntax every construct discussed in Part 2 (`provider {}`, `required_providers {}`, `resource {}`) is built from.

**Next Section:** [§15](../Part3/Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md) — `Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md`
