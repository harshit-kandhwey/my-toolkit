# Section 80 (Part 11): IAM as Code Across Providers

## 1. Definition

**Plain language:** IAM as code means defining who (or what) can do what, to which resources, entirely in Terraform — roles, permissions, and the trust relationships that bind them to users, services, or workloads — instead of clicking through an identity console. All three major providers implement access control differently enough that "IAM" means a genuinely different resource model on each.

**Precise definition:** **IAM as code** provisions identity and access-control primitives declaratively. AWS models this as **roles** (`aws_iam_role`) with a **trust policy** (who/what can assume the role) plus **permission policies** (`aws_iam_policy`) attached via `aws_iam_role_policy_attachment`. Azure models it as **Role-Based Access Control (RBAC)** — `azurerm_role_assignment` binds a built-in or custom `azurerm_role_definition` to a principal (user, group, service principal, or managed identity) at a specific scope (subscription, resource group, or individual resource). GCP models it as **IAM policy bindings** — `google_project_iam_member`/`google_project_iam_binding` (or the resource-scoped equivalents) attach a **role** (predefined or custom) to a **member** (a user, group, or service account) at a given scope in GCP's resource hierarchy (organization → folder → project → resource). All three share the same underlying shape — principal, role/permissions, scope — but the resource names, binding mechanics, and default postures differ substantially.

> 💡 **Tip:** The three providers' "role" terminology means different things structurally. An AWS IAM role is itself an _identity_ that can be assumed (it has a trust policy and can act as a principal). An Azure role definition is _just a set of permissions_ with no identity of its own — it's bound to a separate principal via a role assignment. A GCP IAM role is likewise just a permission set bound to a member via a binding. Calling all three "roles" in conversation without this distinction is a common source of miscommunication on multi-cloud teams.

## 2. Why This Matters

- **IAM misconfiguration is consistently among the top causes of real cloud security incidents** across all three providers — over-permissioned roles, wildcard resource scopes, and forgotten stale bindings are recurring, high-impact findings in security audits.
- **The structural differences between the three models are not cosmetic** — an engineer who assumes Azure RBAC works like AWS IAM roles (i.e., that a "role" is itself assumable) will misdesign the Azure side of a multi-cloud IAM strategy.
- **Least-privilege execution roles for Terraform itself** (the identity that runs `apply`) is a security topic that recurs across this entire roadmap ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) covers it in depth) — this section is the provisioning-mechanics foundation that discussion depends on.

## 3. Prerequisites and Dependencies

Builds on the IAM/role provisioning already introduced in [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md) (§5.4's `aws_iam_role`/`aws_iam_policy` chain) and the service-account pattern from [§77](./Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md) (§5.3). Assumes familiarity with `jsonencode()` for policy documents ([§19](../Part3/Section-19-Part3-String-Interpolation-and-Templating-heredoc-templatefile.md)/[§20](../Part3/Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md)) and basic resource addressing ([§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md)).

## 4. Architecture / Conceptual Diagram

```text
   AWS                        AZURE                       GCP
   ───                        ─────                       ───
   aws_iam_role                azurerm_role_assignment      google_project_iam_member
   (an ASSUMABLE identity      (binds a role definition      (binds a role to a
    with a trust policy)        to a principal at a scope)     member at a scope)
        │                            │                              │
   assume_role_policy          role_definition_name         role = "roles/storage
   (who/what can assume         OR role_definition_id         .objectViewer"
    this role — e.g.            (built-in or custom)
    ec2.amazonaws.com)                │                              │
        │                       principal_id                  member = "serviceAccount:
   aws_iam_policy               (the actual identity           sa@project.iam..."
   (the permission set,          being granted access)
    attached SEPARATELY)              │                              │
        │                       scope                         project / resource
   aws_iam_role_policy_         (subscription/RG/resource)     (GCP resource hierarchy)
   attachment
   (role ⟷ policy link)

   Key structural difference: AWS's role IS the identity.
   Azure's and GCP's "role" is just a permission set — the
   identity is a separate principal/member bound to it.
```

## 5. Hands-On

### 5.1 AWS: Role, Policy, and Attachment

**Purpose:** Reiterate the role/policy/attachment chain from [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md) in an IAM-specific context, emphasizing that the role itself is the assumable identity.

**Syntax:**

```hcl
resource "aws_iam_role" "ci_deploy" {
  name = "ci-deploy-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action    = "sts:AssumeRoleWithWebIdentity"
      Effect    = "Allow"
      Principal = { Federated = "arn:aws:iam::123456789012:oidc-provider/token.actions.githubusercontent.com" }
      Condition = {
        StringEquals = { "token.actions.githubusercontent.com:sub" = "repo:my-org/my-repo:ref:refs/heads/main" }
      }
    }]
  })
}

resource "aws_iam_policy" "deploy_permissions" {
  name   = "deploy-permissions"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["ec2:DescribeInstances", "s3:PutObject"]
      Resource = "*"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "attach" {
  role       = aws_iam_role.ci_deploy.name
  policy_arn = aws_iam_policy.deploy_permissions.arn
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # aws_iam_role.ci_deploy will be created
  # aws_iam_policy.deploy_permissions will be created
  # aws_iam_role_policy_attachment.attach will be created

Plan: 3 to add, 0 to change, 0 to destroy.
```

**Production usage example:** The OIDC-federated trust policy shown (`AssumeRoleWithWebIdentity` scoped to a specific GitHub repo/branch) is the modern standard for CI/CD authentication, replacing long-lived static AWS access keys stored as CI secrets — this pattern is the AWS-specific instance of the least-privilege execution role topic covered generally in [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md).

**Common errors:** A `Resource = "*"` permission (shown above only for brevity) is a common but avoidable over-permissioning mistake — production policies should scope `Resource` to specific ARNs wherever the API supports it.

### 5.2 Azure: Role Assignment to a Managed Identity

**Purpose:** Show Azure's separated role-definition/role-assignment/principal model, using a system-assigned managed identity as the principal.

**Syntax:**

```hcl
resource "azurerm_linux_virtual_machine" "app" {
  # ... other arguments ...
  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_role_assignment" "storage_reader" {
  scope                = azurerm_storage_account.data.id
  role_definition_name = "Storage Blob Data Reader"
  principal_id         = azurerm_linux_virtual_machine.app.identity[0].principal_id
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # azurerm_linux_virtual_machine.app will be created
  # azurerm_role_assignment.storage_reader will be created

Plan: 2 to add, 0 to change, 0 to destroy.
```

**Production usage example:** System-assigned managed identities (rather than a Service Principal with a stored client secret) are the standard production pattern for granting a VM access to other Azure resources — the identity's lifecycle is tied to the VM itself, and there's no secret to rotate or leak.

**Common errors:** Referencing `azurerm_linux_virtual_machine.app.identity[0].principal_id` before the VM resource has actually finished creating (e.g., in a module applied in the same run without Terraform's implicit dependency being inferable) can produce a `null`/empty principal ID error — the identity block's `principal_id` attribute is only populated after the resource is created, so this reference must be a genuine implicit dependency, not a hardcoded guess.

### 5.3 GCP: IAM Policy Binding to a Service Account

**Purpose:** Show GCP's member/role/scope binding model, contrasting `google_project_iam_member` (additive) against `google_project_iam_binding` (authoritative).

**Syntax:**

```hcl
resource "google_service_account" "app_sa" {
  account_id = "app-workload-sa"
}

# Additive: adds this member to the role without touching other members
resource "google_project_iam_member" "storage_viewer" {
  project = "my-app-prod-123"
  role    = "roles/storage.objectViewer"
  member  = "serviceAccount:${google_service_account.app_sa.email}"
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # google_service_account.app_sa will be created
  # google_project_iam_member.storage_viewer will be created

Plan: 2 to add, 0 to change, 0 to destroy.
```

**Production usage example:** `google_project_iam_member` (additive, one resource per member/role pair) is strongly preferred over `google_project_iam_binding` (authoritative, replaces the _entire_ member list for that role) in any module shared across teams — `_binding` will silently remove other teams' bindings to the same role on `apply` if they weren't included in that specific resource's member list, a well-documented and frequently cited GCP Terraform hazard.

**Common errors:** Using `google_project_iam_binding` in a module applied by multiple independent pipelines is the single most cited GCP IAM Terraform mistake — each pipeline's `apply` overwrites the full member list for that role with only what it declares, silently revoking access other teams believed was permanent.

## 6. Production Usage Notes

- Across all three providers, prefer **narrowly scoped, additive** grants over broad or list-replacing ones: specific `Resource` ARNs over `*` in AWS, resource-scoped `azurerm_role_assignment` over subscription-wide scope in Azure, and `google_project_iam_member` over `google_project_iam_binding` in GCP.
- Custom roles/policies (an `aws_iam_policy` with a hand-written statement, an `azurerm_role_definition`, a `google_project_iam_custom_role`) are preferred over broad built-in roles (AWS managed policies like `PowerUserAccess`, Azure's `Contributor`, GCP's `roles/editor`) for any workload identity, reserving broad roles for genuine human administrators.
- Modern CI/CD authentication on all three providers has converged on federated/OIDC-based short-lived credentials rather than static keys/secrets — AWS OIDC (5.1), Azure Workload Identity Federation, and GCP Workload Identity Federation are the respective mechanisms.

## 7. Security Considerations

- The `google_project_iam_binding` hazard in 5.3's common-errors note is a genuine, recurring production incident pattern — it deserves explicit mention in any team's Terraform style guide, not just awareness.
- Trust policies (AWS) and federated identity conditions should be scoped as narrowly as the underlying platform allows — e.g., AWS's OIDC trust condition scoped to a specific repo _and_ branch (5.1), not just the GitHub organization, limits which CI runs can assume the role.
- IAM bindings, roles, and policies should be reviewed with the same rigor as network security groups in `terraform plan` output — an overlooked wildcard permission is at least as consequential as an overlooked open port.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                     | Likely Cause                                                                                               | Resolution Path                                                                                            |
| --------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| GCP: another team's access to a role disappeared after an unrelated `apply` | `google_project_iam_binding` used instead of `google_project_iam_member`, overwriting the full member list | Switch to `google_project_iam_member` for additive, per-identity grants                                    |
| Azure: `principal_id` reference is empty/null during `apply`                | Referencing a managed identity's `principal_id` before the resource is fully created                       | Ensure the reference is a genuine implicit dependency, not applied out of order via `-target`              |
| AWS: `AccessDenied` despite a policy that looks correct                     | Trust policy condition too narrow (wrong branch/repo), or policy not yet propagated                        | Verify the trust policy's `Condition` block matches the actual caller exactly; allow for propagation delay |
| Newly created workload identity can't access anything yet                   | Role/policy attachment hasn't propagated (all three providers have some eventual consistency here)         | Add a brief retry/backoff in the dependent workload rather than assuming instant availability              |

## 9. Best Practices

- Default to additive, narrowly-scoped IAM resources everywhere: specific ARNs/scopes, custom least-privilege roles, and — specifically on GCP — `_member` resources rather than `_binding`.
- Use federated/OIDC-based short-lived credentials for CI/CD authentication on all three providers instead of long-lived static keys or secrets.
- Document the structural difference between the three providers' "role" concepts explicitly in onboarding material for any team working across more than one cloud, since the terminology overlap is a recurring source of confusion.

## 10. Common Anti-Patterns / Mistakes

- **Using `google_project_iam_binding` in any module that might be applied by more than one team/pipeline.** This is the single most consequential GCP-specific IAM mistake in this section and bears repeating as its own anti-pattern entry.
- **Attaching broad managed/built-in roles to workload identities "to unblock development," then never narrowing them.** This is how `AdministratorAccess`-on-a-service-account situations accumulate in every real organization's audit findings.
- **Treating Azure's role definition as if it were an assumable identity**, e.g., trying to reference a `azurerm_role_definition` where a principal ID is expected — the role definition is just the permission set, not something that itself has an identity.

## 11. Interview Questions

**🎯 Beginner:** _"In AWS IAM, is a 'role' the same kind of thing as a 'role' in Azure RBAC?"_
**Model answer:** No. An AWS IAM role is itself an assumable identity — it has a trust policy determining who/what can assume it, and permissions are attached to it. An Azure role (role definition) is just a set of permissions with no identity of its own; it must be bound via a separate role assignment to an actual principal (user, group, service principal, or managed identity) to grant anyone access.
_What the interviewer is probing for:_ Whether the candidate understands this is a structural difference, not just different terminology for the same concept.

**🎯 Intermediate:** _"Why is `google_project_iam_binding` considered risky to use in a shared Terraform module, and what should be used instead?"_
**Model answer:** `google_project_iam_binding` is authoritative for a given role — applying it sets the _complete_ member list for that role, replacing whatever was there before, including bindings created by other Terraform configurations or manually. If multiple teams' pipelines each apply a `_binding` resource for the same role, whichever applies last silently overwrites the others' access. `google_project_iam_member` is additive instead — it manages exactly one member/role pair without touching any other member's binding to that same role, which is safe for shared or multi-team use.
_What the interviewer is probing for:_ Concrete, first-hand-sounding knowledge of this specific, well-documented GCP hazard rather than vague "be careful with permissions" generalities.

**🎯 Senior:** _"Design an IAM strategy for a CI/CD pipeline that needs to deploy to AWS, Azure, and GCP from the same GitHub Actions workflow, without storing any long-lived cloud credentials as GitHub secrets."_
**Model answer:** Use each provider's OIDC/workload-identity-federation mechanism, all trusting GitHub Actions' own OIDC token issuer as the external identity provider — configure an AWS IAM role with a trust policy conditioned on the GitHub OIDC token's `sub` claim (scoped to the specific repo and branch/environment), an Azure Federated Identity Credential trusting the same token bound to a specific App Registration/Managed Identity, and a GCP Workload Identity Pool/Provider trusting the same token bound to a service account via `google_service_account_iam_member` granting `roles/iam.workloadIdentityUser`. Each cloud's pipeline step then exchanges the GitHub-issued OIDC token for short-lived, provider-specific credentials at runtime — no static keys or secrets exist anywhere in the pipeline configuration, and each trust relationship is independently scoped and revocable without needing to rotate any stored secret in GitHub.
_What the interviewer is probing for:_ Whether the candidate can design a coherent, credential-free, multi-cloud CI/CD authentication strategy using each provider's actual federation mechanism, not just "use IAM roles" vaguely.

**🎯 Architect:** _"Your organization's Terraform IAM configurations across AWS, Azure, and GCP have accumulated hundreds of individually reasonable-looking grants over several years, and a recent audit can't determine which are still needed. How do you fix this structurally, not just by removing unused ones once?"_
**Model answer:** The one-time cleanup addresses the symptom, not the cause — the real problem is that grants were added individually over time with no mechanism forcing periodic justification or automatic expiry. The structural fix has three parts: first, adopt policy-as-code (Sentinel/OPA, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) that rejects new broad or wildcard-scoped IAM resources at PR time, so the accumulation rate of new over-broad grants drops going forward. Second, tag every IAM grant (AWS policy, Azure role assignment, GCP binding) with an owning team and a business justification via a required module variable, so future audits can attribute and question each grant without archaeology. Third, where the provider supports it, prefer time-bound or condition-scoped access (AWS's `Condition` blocks with date/session constraints, Azure PIM for just-in-time elevation) over standing grants for anything beyond baseline workload identity needs, and schedule recurring automated access reviews (a CI job diffing current bindings against a last-reviewed baseline) rather than relying on a periodic manual audit that clearly already isn't happening reliably enough to have caught this.
_What the interviewer is probing for:_ Whether the candidate proposes a self-sustaining process (policy gates, mandatory metadata, scheduled review automation) rather than a one-time manual remediation that will simply recur in a few more years.

## 12. Common Misconceptions

1. **"An Azure role or a GCP role is an identity, like an AWS IAM role."** Only AWS's role is itself an assumable identity; Azure's and GCP's "roles" are permission sets bound to a separate principal/member.
2. **"`google_project_iam_binding` and `google_project_iam_member` are interchangeable, just different syntax."** They have fundamentally different semantics — authoritative (replaces the full member list) versus additive (manages one member/role pair) — and using the wrong one in a shared context causes real access-loss incidents.
3. **"IAM changes take effect immediately everywhere."** All three providers have some degree of eventual consistency for IAM propagation; a freshly granted identity may briefly fail to use its new permissions.
4. **"Static access keys are simpler and therefore fine for CI/CD."** Federated/OIDC-based short-lived credentials are now the standard precisely because static keys are a standing secret-leak liability with no expiry, and all three major providers have mature, well-documented federation mechanisms making the "simpler" argument obsolete.

## 13. 🔑 Key Takeaways

- AWS IAM roles are themselves assumable identities; Azure and GCP "roles" are permission sets bound to a separate principal via a role assignment or binding — a structural, not just terminological, difference.
- `google_project_iam_binding` is authoritative and overwrites the full member list for a role; `google_project_iam_member` is additive and safe for shared, multi-team modules.
- Federated/OIDC-based short-lived credentials (AWS OIDC, Azure Workload Identity Federation, GCP Workload Identity Federation) are the modern standard for CI/CD authentication across all three providers, replacing static keys/secrets.
- Least privilege applies identically in spirit across all three providers even though the mechanics differ: narrow `Resource` ARNs, resource-scoped role assignments, and per-member IAM bindings.
- IAM propagation is eventually consistent on all three providers; freshly granted access may not be immediately usable.

## 14. Related Concepts & What's Next

[§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md)'s §5.4 and [§77](./Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md)'s §5.3 supplied the AWS and GCP identity provisioning patterns this section formalized as IAM-as-code specifically; [§76](./Section-76-Part11-Azure-Provider-azurerm-Deep-Dive-Resource-Groups-VNets-VMs.md)'s §5.2/§5.3 (not covered in depth there) is completed here with the Azure RBAC model. [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) covers least-privilege Terraform execution roles specifically — the identity running `apply` itself, applying everything from this section to Terraform's own operational security. [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) (Sentinel/OPA) is the policy-enforcement mechanism referenced in the architect answer above. [§81](./Section-81-Part11-Kubernetes-Provisioning-via-Terraform-EKS-AKS-GKE.md) now turns to a composite case that draws on both networking ([§79](./Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md)) and IAM (this section): provisioning managed Kubernetes clusters via Terraform.

**Next Section:** [§81](./Section-81-Part11-Kubernetes-Provisioning-via-Terraform-EKS-AKS-GKE.md) — `Section-81-Part11-Kubernetes-Provisioning-via-Terraform-EKS-AKS-GKE.md`
