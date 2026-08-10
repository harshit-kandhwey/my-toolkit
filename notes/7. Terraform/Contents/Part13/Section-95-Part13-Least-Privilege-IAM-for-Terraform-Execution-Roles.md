# Section 95 (Part 13): Least-Privilege IAM for Terraform Execution Roles

## 1. Definition

**Plain language:** The credentials Terraform itself runs as — the "execution role" — are a completely different thing from the permissions the resources Terraform creates end up having. An execution role that's over-permissioned "to avoid permission errors" is one of the highest-leverage security mistakes in a Terraform setup: it means a single compromised CI pipeline, leaked credential, or malicious pull request can do anything in your cloud account, not just what that specific configuration is supposed to manage.

**Precise definition:** The **Terraform execution role** (or execution identity/credential) is the set of cloud IAM permissions under which the `terraform plan`/`apply`/`destroy` process itself authenticates and acts — distinct from the permissions granted _to resources Terraform creates_ (an EC2 instance's instance profile, a Lambda's execution role, an application's service account). **Least-privilege IAM for execution roles** is the practice of scoping the execution role's permissions to exactly the actions and resource scopes a given configuration needs to plan and apply successfully — no more — recognizing that this credential is both the most powerful (broad create/modify/destroy authority) and most exposed (used by automation, often CI/CD, often less carefully guarded than an individual's console session) credential in the entire IaC pipeline.

> 💡 **Tip:** A useful test for whether an execution role is over-scoped: could this role, as currently defined, do meaningful damage to infrastructure that this specific Terraform configuration doesn't manage? If yes — if the role could delete a database in another team's account, or modify IAM policies unrelated to this stack — the role is broader than the configuration needs, regardless of whether any current `apply` actually exercises that excess permission.

## 2. Why This Matters

- **The execution role is the single highest-value target for an attacker aiming at infrastructure**, because compromising it (via a leaked CI secret, a malicious PR that gets auto-applied, a compromised dependency in the pipeline) grants exactly the create/modify/destroy power that role has — a broad role means broad blast radius from any one of those compromise paths.
- **CI/CD pipelines are frequently the weakest link**, not because the platforms are inherently insecure, but because pipeline configuration (secrets storage, third-party actions/plugins, PR-triggered runs) has a larger attack surface than a single engineer's carefully guarded console session — [§1](../Part1/Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md) already flags this: "the blast radius of a compromised CI/CD pipeline running Terraform is typically far larger than a compromised individual's console session."
- **"Just grant admin to unblock the pipeline" is an extremely common shortcut** under deadline pressure, and it tends to become permanent because nobody revisits it once the immediate blocker is resolved — least-privilege IAM design has to be a deliberate practice, not a default outcome.
- **A destroy-capable, broadly-scoped execution role turns a configuration mistake into a production incident** — the difference between "a bad `apply` deletes the resources this stack manages" and "a bad `apply` deletes anything in the account" is entirely a function of how the execution role was scoped.
- **Auditors and compliance frameworks specifically assess this** — "what can your CI/CD pipeline's credentials do, and is it scoped to only what it needs" is a standard question in security reviews of any IaC-driven organization.

## 3. Prerequisites and Dependencies

This section assumes familiarity with provider authentication mechanics from [§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md) (how Terraform authenticates to AWS/Azure/GCP at all) — this section is about _scoping_ that authentication's permissions correctly, not establishing it in the first place. [§80](../Part11/Section-80-Part11-IAM-as-Code-Across-Providers.md) (IAM as code across providers) covers writing IAM resources generally; this section is specifically about the IAM identity Terraform itself runs as, a narrower and higher-stakes topic. The distinction drawn in this section — execution-role permissions vs. resource permissions — is easiest to grasp with basic IAM policy familiarity (roles, policies, resource ARNs/scopes) from whichever cloud is in use.

## 4. Architecture / Conceptual Diagram

```text
   TWO DIFFERENT PERMISSION SURFACES — DO NOT CONFUSE THEM

   ┌────────────────────────────────────────────────────────────────┐
   │  1. EXECUTION ROLE (what Terraform itself runs as)             │
   │     - Used by: CI/CD pipeline, or an engineer's local          │
   │       credentials, when running plan/apply/destroy             │
   │     - Needs: permission to create/read/update/delete the       │
   │       SPECIFIC resource types this configuration manages,      │
   │       scoped to the SPECIFIC resource ARNs/paths/projects it   │
   │       is responsible for                                       │
   │     - Risk if over-scoped: a compromised pipeline/credential   │
   │       can affect infrastructure FAR beyond this configuration  │
   └────────────────────────────────────────────────────────────────┘
                          │  creates/manages
                          ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  2. RESOURCE PERMISSIONS (what the created infra can do)        │
   │     - e.g. an EC2 instance profile, a Lambda execution role,    │
   │       a GCP service account attached to a Cloud Run service     │
   │     - Needs: permission for the RUNNING APPLICATION's own       │
   │       runtime needs (read from S3, write to a queue, etc.)      │
   │     - Entirely separate concern from what Terraform itself      │
   │       needed to CREATE that resource                            │
   └─────────────────────────────────────────────────────────────────┘

   COMMON MISTAKE: conflating these two. "The Lambda needs S3 access,
   so let's give the Terraform execution role S3 access too" —
   already true if Terraform is creating the S3 bucket/policy, but
   the SCOPE and PURPOSE of that grant are different: Terraform needs
   permission to create/modify the bucket and its policy; the Lambda
   needs permission to read/write objects in it at runtime. Granting
   the execution role broad S3 data-plane access it never actually
   uses (GetObject/PutObject) "just in case" is unnecessary excess.
```

- The execution role's scope should map to **what this specific configuration manages**: if a stack only creates VPCs, subnets, and security groups, its execution role needs `ec2:*Vpc*`, `ec2:*Subnet*`, `ec2:*SecurityGroup*`-class actions — not `s3:*`, `iam:*`, or unrelated service access.
- Splitting infrastructure into multiple Terraform configurations/state files (per team, per environment, per service) naturally enables narrower per-stack execution roles — a monolithic single state file managing everything tends to justify (and then require) an overly broad single execution role.
- CI/CD platforms increasingly support **OIDC federation** (GitHub Actions, GitLab CI issuing short-lived cloud credentials via OIDC trust) as a modern alternative to long-lived static access keys stored as CI secrets — removing a standing credential entirely is a stronger control than merely scoping one down.

## 5. Hands-On

### 5.1 An Over-Scoped Execution Role (Anti-Pattern, Shown for Contrast)

**Purpose:** Illustrate the common "just unblock the pipeline" shortcut and why it's dangerous.

**Syntax:**

```hcl
# AWS IAM policy attached to the CI pipeline's execution role — DO NOT DO THIS
data "aws_iam_policy_document" "ci_execution_overbroad" {
  statement {
    effect    = "Allow"
    actions   = ["*"]
    resources = ["*"]
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply   # works, because the role can do literally anything
Apply complete! Resources: 12 added, 0 changed, 0 destroyed.

# ...but a leaked CI secret using this role can now also:
$ aws iam create-user --user-name backdoor    # unrelated to this config
$ aws rds delete-db-instance --db-instance-identifier prod-db  # unrelated to this config
```

**Production usage example:** This pattern is disturbingly common in early-stage or deadline-pressured teams — a permission error blocks a deploy, someone attaches `AdministratorAccess` "temporarily" to unblock it, and the temporary grant is never revisited.

**Common errors:** None at apply time — that's precisely the danger; an over-scoped role produces no errors, which means there's no natural signal prompting anyone to fix it later.

### 5.2 A Scoped Execution Role (Correct Pattern)

**Purpose:** Show a policy scoped to exactly the resource types and ARN patterns a specific networking-focused stack needs.

**Syntax:**

```hcl
data "aws_iam_policy_document" "ci_execution_scoped" {
  statement {
    sid    = "VPCManagement"
    effect = "Allow"
    actions = [
      "ec2:CreateVpc", "ec2:DeleteVpc", "ec2:DescribeVpcs",
      "ec2:CreateSubnet", "ec2:DeleteSubnet", "ec2:DescribeSubnets",
      "ec2:CreateSecurityGroup", "ec2:DeleteSecurityGroup",
      "ec2:AuthorizeSecurityGroupIngress", "ec2:RevokeSecurityGroupIngress",
      "ec2:DescribeSecurityGroups", "ec2:CreateTags",
    ]
    resources = ["*"]  # EC2 network actions largely don't support resource-level ARN scoping
    condition {
      test     = "StringEquals"
      variable = "aws:RequestedRegion"
      values   = ["us-east-1"]
    }
  }
  statement {
    sid       = "StateBackendAccess"
    effect    = "Allow"
    actions   = ["s3:GetObject", "s3:PutObject", "dynamodb:GetItem", "dynamodb:PutItem", "dynamodb:DeleteItem"]
    resources = ["arn:aws:s3:::app-terraform-state/networking/*", "arn:aws:dynamodb:*:*:table/terraform-locks"]
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # aws_vpc.main will be created
  # aws_subnet.public will be created
Apply complete! Resources: 2 added, 0 changed, 0 destroyed.

$ terraform apply -target=aws_iam_user.unrelated   # not even in this config
Error: aws_iam_user.unrelated does not exist in the configuration
# even if it did, the role lacks iam:CreateUser — attempted action would fail with AccessDenied
```

**Production usage example:** Splitting execution roles per stack (networking, compute, data) with region and resource-type conditions like this is standard practice in mature organizations, often generated and reviewed as its own piece of Terraform-managed IAM ([§80](../Part11/Section-80-Part11-IAM-as-Code-Across-Providers.md)), with a deliberately separate, more tightly controlled pipeline for changes to the execution roles themselves.

**Common errors:** `AccessDenied` on a legitimate new resource type added to the configuration — expected friction of least privilege; the fix is to deliberately extend the policy for the new action, not to broaden scope preemptively for hypothetical future needs.

## 6. Production Usage Notes

- **Prefer short-lived, federated credentials (OIDC) over long-lived static access keys stored as CI secrets** wherever the CI platform and cloud both support it — this removes an entire class of "leaked static credential" risk rather than just scoping its permissions.
- **Splitting state/configuration per logical boundary (team, environment, service) is what makes narrow execution roles practical** — a single execution role for a single giant state file managing the entire account will always trend toward broad permissions because it genuinely needs to touch everything in that state.
- **The pipeline or process that modifies the execution role's own IAM policy should itself require a higher bar of review** than ordinary infrastructure changes — an attacker (or a mistake) that can broaden its own execution role has effectively defeated the whole control.
- **`terraform plan` (read-only) and `terraform apply` (mutating) can reasonably run under different-scoped credentials** — a common pattern grants broader read/describe permissions for `plan` (useful for full drift visibility) while gating destructive `apply` actions behind a separate, more tightly scoped or human-approved step.

## 7. Security Considerations

- **Distinguish execution-role permissions from resource permissions explicitly in every design review** — the conflation described in the architecture diagram above is the most common reasoning error that leads to over-scoping; "the resource needs X" does not mean "Terraform needs X to create the resource," and vice versa.
- **Destructive actions (`Delete*`, `Terminate*`, `Destroy*`) deserve extra scrutiny in execution-role policies** — a role that can create resources but has intentionally narrower destroy permissions (or requires a separate approval gate for `terraform destroy` specifically) limits the damage of both compromise and operator error.
- **Wildcard resource scoping (`resources = ["*"]`) is sometimes technically unavoidable** (many EC2 network actions don't support resource-level ARN restriction) — where unavoidable, compensate with action-level narrowing (only the specific actions needed) and conditions (region, tag-based conditions) rather than treating the wildcard as an excuse to also broaden the action list.
- **Cross-account/cross-subscription/cross-project execution roles** (a central CI/CD pipeline applying Terraform into many downstream accounts via assumed roles) multiply the blast radius of a single compromised pipeline identity across every account it can assume into — apply the same least-privilege discipline per target account's assumed role, and avoid one identity trusted broadly across all of them.
- **Audit logging of the execution role's actual API activity (CloudTrail, Azure Activity Log, Cloud Audit Logs) should be reviewed periodically against the granted policy** — permissions granted "just in case" that are never actually exercised in practice are prime candidates for removal, and this comparison is the practical way to find them.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                      | Likely Cause                                                                                        | Resolution Path                                                                                                                                                                |
| ---------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| `AccessDenied`/`Forbidden` on a specific action during `apply`               | Execution role correctly scoped but missing the newly-needed action for a new resource type         | Extend the policy with the specific missing action, scoped to the relevant resource ARN — do not broaden generally                                                             |
| Team defaults to attaching a fully-permissive managed policy "to unblock CI" | Time pressure and unclear ownership of the execution role's policy design                           | Establish execution-role policy changes as their own reviewed artifact; treat broad grants as an incident to remediate, not a fix                                              |
| A single leaked CI secret is discovered to have account-wide impact          | Execution role was scoped far broader than the configuration it runs actually needs                 | Immediately rotate/revoke the credential; redesign the role scoped to actual need; consider OIDC federation to remove standing credentials entirely                            |
| Execution role works for `apply` but plan-only automated drift checks fail   | Read/describe permissions were bundled only into the apply-time role, not a separate plan-only role | Provision a distinct, appropriately-scoped read-only role for automated `plan`/drift-detection runs ([§97](./Section-97-Part13-Drift-Detection-and-Compliance-Enforcement.md)) |

## 9. Best Practices

- Scope execution-role IAM policies to the exact resource types and, where the cloud API supports it, the exact resource ARNs/paths/projects a given configuration manages.
- Split Terraform state/configuration along boundaries (team, environment, service) that make narrow, purpose-specific execution roles practical rather than forcing one broad role to cover everything.
- Prefer OIDC/workload-identity federation for CI/CD execution credentials over long-lived static access keys wherever supported.
- Treat changes to the execution role's own policy as higher-risk changes requiring more scrutiny than ordinary resource changes.
- Periodically audit actual API usage against granted permissions and remove unused grants.

## 10. Common Anti-Patterns / Mistakes

- **Attaching a broad managed policy (`AdministratorAccess`, `Contributor`, `Owner`) to "unblock" a pipeline and never revisiting it.**
- **Conflating what a created resource needs at runtime with what Terraform needs to create it**, leading to execution roles that accumulate permissions belonging to the workloads they provision, not to provisioning itself.
- **One execution role shared across every team's and every environment's Terraform runs** — production and a developer's sandbox environment sharing an identically-broad execution role means a mistake or compromise in the low-stakes environment has production-level blast radius.
- **Storing long-lived static cloud access keys as CI secrets when the CI platform supports OIDC federation** — a needless standing credential when a short-lived, federated alternative is available.

## 11. Interview Questions

**🎯 Beginner:** _"What is a Terraform 'execution role'?"_
**Model answer:** It's the cloud IAM identity/credential under which Terraform itself runs `plan`/`apply`/`destroy` — for example, the AWS IAM role a CI/CD pipeline assumes to run Terraform. It's distinct from the permissions of the resources Terraform creates (like an EC2 instance's own instance profile); the execution role is about what Terraform itself is allowed to do to your cloud account.
_What the interviewer is probing for:_ Whether the candidate understands this as a distinct concept from general IAM, not just "some credentials."

**🎯 Intermediate:** _"Why is it dangerous to grant a CI/CD pipeline's Terraform execution role broad administrative permissions, even if the pipeline currently only manages a small set of resources?"_
**Model answer:** Because the execution role's granted permissions, not its current usage pattern, define the blast radius of any compromise — a leaked CI secret, a malicious dependency in the pipeline, or a maliciously crafted PR that gets auto-applied can exploit whatever the role is _capable_ of doing, regardless of what the configuration currently does. A broadly-permissioned role turns what should be a contained incident (damage limited to the resources this stack manages) into an account-wide one.
_What the interviewer is probing for:_ Understanding that IAM scope, not observed behavior, is the actual security boundary — a common gap where engineers reason "it's fine, we don't actually use those permissions."

**🎯 Senior:** _"A team's Terraform CI pipeline uses a long-lived AWS access key stored as a GitHub Actions secret, scoped reasonably narrowly via IAM policy. What's the remaining risk, and how would you address it?"_
**Model answer:** Even with narrow IAM scoping, a long-lived static access key is itself a standing credential that can be leaked (accidentally logged, exfiltrated via a compromised dependency in the Actions workflow, exposed via a misconfigured secret) and remains valid until manually rotated or revoked — narrow scoping limits the damage of a leak but doesn't prevent the leak or shorten its window of usefulness. The stronger fix is to eliminate the standing credential entirely via OIDC federation: configure AWS IAM's OIDC identity provider to trust GitHub Actions' token issuer for that specific repository/workflow, and have the pipeline assume a role using a short-lived token minted per-run — there's no persistent secret to leak in the first place, and a leaked run token expires almost immediately.
_What the interviewer is probing for:_ Awareness that scoping and credential lifetime are separate risk dimensions, and familiarity with OIDC federation as the modern best-practice mitigation for the latter.

**🎯 Architect:** _"Design the execution-role strategy for an organization with 40 product teams, each owning their own Terraform-managed infrastructure, with a central platform team responsible for shared networking and IAM baseline resources."_
**Model answer:** Give each product team its own execution role, scoped to the specific AWS account(s)/subscription(s)/project(s) and resource-type set that team's stacks manage, provisioned via OIDC federation from their own CI pipelines so there's no shared standing credential across teams — a compromise in one team's pipeline can't reach another's. The platform team's execution role for shared networking/IAM baseline resources is necessarily broader in scope (it touches cross-cutting infrastructure) but should still be scoped to that specific domain, not full account administrative access, and should run through a more tightly controlled pipeline (fewer contributors, mandatory review, possibly a separate approval gate for destructive actions) given its higher blast radius if compromised. Critically, no team's execution role — including the platform team's — should have standing permission to modify IAM policies for OTHER teams' execution roles; that self-broadening path is the actual privilege-escalation risk to design against explicitly, not just an oversight to hope doesn't happen. Periodic automated review comparing each role's granted permissions against actual CloudTrail usage closes the loop on permissions that accumulate but go unused.
_What the interviewer is probing for:_ Organizational-scale thinking about isolation between teams' blast radii, recognition of the platform team's execution role as a distinct higher-risk case, and explicit attention to the privilege-escalation path of roles that can modify other roles.

## 12. Common Misconceptions

1. **"If the pipeline doesn't currently use a broad permission, granting it is harmless."** The permission itself, not current usage, defines what a compromised credential running under that role can do — unused-but-granted permissions are exactly as exploitable as used ones.
2. **"The execution role and the created resource's own permissions are the same concern."** They're separate: what Terraform needs to create/modify/delete a resource is different from what that resource needs at runtime to do its job — conflating them is the most common cause of over-scoped execution roles.
3. **"Least privilege for Terraform is only about the resources it manages, not the credential type itself."** Credential lifetime and delivery mechanism (long-lived static key vs. short-lived OIDC-federated token) is an independent risk dimension from scope — a narrowly-scoped but long-lived static key is still a standing liability.
4. **"`AdministratorAccess` is fine for CI as long as only trusted engineers can trigger the pipeline."** This ignores supply-chain risk (compromised CI dependencies/actions/plugins) and the possibility of a malicious or mistaken PR being auto-applied — "trusted engineers trigger it" doesn't bound what a compromised pipeline component can do once triggered.

## 13. 🔑 Key Takeaways

- The Terraform execution role — the identity Terraform itself runs as — is a distinct concept from the permissions granted to the resources Terraform creates; conflating the two is the most common cause of over-scoped roles.
- Execution-role permission grants, not observed pipeline behavior, define the actual blast radius of a compromised credential — unused excess permission is still exploitable.
- Splitting Terraform state/configuration along team, environment, or service boundaries is what makes genuinely narrow, purpose-specific execution roles practical.
- Credential lifetime matters independently of scope — prefer short-lived, OIDC-federated credentials over long-lived static access keys for CI/CD execution roles wherever supported.
- Changes to the execution role's own IAM policy deserve a higher review bar than ordinary infrastructure changes, since a role that can broaden itself has defeated the control entirely.

## 14. Related Concepts & What's Next

[§96](./Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md), next, covers static analysis tooling (tfsec, Checkov, Terrascan) that can catch overly permissive IAM policies — including execution-role definitions themselves, if they're written in Terraform — before they're ever applied. [§80](../Part11/Section-80-Part11-IAM-as-Code-Across-Providers.md) covers writing IAM resources generally as code, a broader topic than the execution-role-specific scoping covered here. [§98](./Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md) closes this Part with backend access controls, which is the analogous least-privilege question applied to who can read the state backend rather than who can run `apply`.

**Next Section:** [§96](./Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md) — `Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md`
