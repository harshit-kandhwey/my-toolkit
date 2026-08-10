# Section 107 (Part 15): Terraform vs. Pulumi vs. CDK vs. CloudFormation/Bicep — Detailed Comparison

## 1. Definition

**Plain language:** There are several mature tools for provisioning cloud infrastructure declaratively, and they differ on real, meaningful axes — what language you write in, which clouds they support, whether they invented their own execution engine or generate output for someone else's, and how state is tracked. Picking one over another has lasting consequences for a team, so it's worth understanding what each one actually is rather than treating them as interchangeable.

**Precise definition:** **Terraform** is a multi-cloud, declarative IaC tool using its own configuration language (HCL, [§15](../Part3/Section-15-Part3-HCL-Fundamentals-Blocks-Arguments-Identifiers.md)) and its own execution engine, provider plugin model ([§8](../Part2/Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md)), and self-managed state file ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)). **Pulumi** is a multi-cloud IaC tool that lets engineers write infrastructure definitions in general-purpose programming languages (TypeScript, Python, Go, C#, Java) that Pulumi's engine evaluates and reconciles against its own state, conceptually similar to Terraform's model but with a real programming language instead of HCL as the authoring surface. **AWS CDK** (Cloud Development Kit) is an AWS-specific framework where infrastructure is written in a general-purpose language and then **synthesized** into a CloudFormation template, which AWS CloudFormation then executes — CDK itself has no independent execution engine or state; CloudFormation does the provisioning and state tracking. **CloudFormation** is AWS's native, JSON/YAML-based, declarative IaC service, deeply integrated with AWS APIs, with AWS itself managing execution and state (no local state file to manage). **Bicep** is Microsoft's domain-specific language that transpiles to Azure Resource Manager (ARM) JSON templates, serving the same "native, single-cloud, declarative" role for Azure that CloudFormation serves for AWS.

> 💡 **Tip:** The single most load-bearing distinction across these five tools is **where the execution engine and state live**. Terraform and Pulumi each own their full engine and state end-to-end, multi-cloud. CDK owns neither — it's a code-generation layer on top of CloudFormation, which owns both, AWS-only. CloudFormation and Bicep are native cloud-provider services with no separate state file to manage or lose. Once that axis is clear, most of the rest of the comparison (language, portability, learning curve) follows from it.

## 2. Why This Matters

- **Language choice affects team fit.** A team of application engineers already fluent in TypeScript or Python may be more productive and make fewer errors in Pulumi or CDK than learning HCL from scratch; a platform team that wants infrastructure config kept deliberately simple and non-Turing-complete may prefer HCL's constraints as a feature, not a limitation.
- **Multi-cloud vs. single-cloud is often the deciding factor, not language preference.** An organization committed to AWS-only, deeply integrated with AWS-specific services (Step Functions, native L2/L3 CDK constructs), gains real productivity from CDK or CloudFormation's tight coupling; an organization spanning AWS, Azure, and GCP needs Terraform or Pulumi's provider-agnostic model or ends up maintaining parallel toolchains.
- **State management model changes operational risk profile.** Terraform and Pulumi's self-managed state introduces a class of operational risk (state corruption, drift, locking, [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)–[§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md)) that CloudFormation and Bicep's provider-managed execution avoids entirely — but at the cost of losing multi-cloud portability.
- **Ecosystem maturity and provider coverage differ substantially.** Terraform's provider ecosystem (thousands of providers across the Registry, [§10](../Part2/Section-10-Part2-The-Terraform-Registry-and-Sourcing-Providers.md)) is broader than any competitor's for third-party (non-cloud) systems — Datadog, GitHub, Kubernetes, PagerDuty — which matters heavily for organizations managing more than just cloud resources.
- **Cost and lock-in considerations differ.** Terraform Cloud/Enterprise ([§84](../Part12/Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md)–[§91](../Part12/Section-91-Part12-Teams-RBAC-and-SSO-in-Terraform-Cloud-Enterprise.md)) and Pulumi Cloud both have paid tiers for team features, while CloudFormation and Bicep are free (bundled into the cloud provider) but tie you to that provider's roadmap and pace of resource-type support.

## 3. Prerequisites and Dependencies

This section assumes the reader already understands Terraform's own architecture in depth ([§4](../Part1/Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md), [§8](../Part2/Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md), [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)) — the comparison is only meaningful once Terraform's actual model (not a caricature of it) is well understood. [§2](../Part1/Section-02-Part1-History-Terraform-Origins-IaC-Tooling-Landscape.md) briefly introduced these tools historically; this section gives the detailed, technical comparison. No new Terraform mechanics are introduced here.

## 4. Architecture / Conceptual Diagram

```text
              AUTHORING LANGUAGE          EXECUTION ENGINE / STATE OWNER        CLOUD SCOPE

Terraform     HCL (declarative DSL)  ───► Terraform core engine, own state ───► Multi-cloud
                                          file (local or remote backend, §49)   (AWS/Azure/GCP/
                                                                                 3rd-party APIs)

Pulumi        TypeScript/Python/Go/  ───► Pulumi engine, own state         ───► Multi-cloud
              C#/Java (general-           (Pulumi Cloud or self-managed
              purpose, imperative              backend)
              code, declarative
              resource model)

AWS CDK       TypeScript/Python/Go/  ───► "cdk synth" generates a          ───► AWS only
              Java/C# (general             CloudFormation template ───►         (cdktf variant
              purpose)                     CloudFormation engine executes       targets Terraform
                                            it, AWS manages state                instead — see note)

CloudFormation JSON/YAML             ───► AWS-managed engine and state    ───► AWS only
                                          (no local state file at all)

Bicep         Bicep DSL (transpiles) ───► ARM engine and state,           ───► Azure only
                                          AWS/Azure-managed
                                          (no local state file at all)

Common thread: all five are DECLARATIVE at the resource-definition level.
CDK/Pulumi differ from Terraform/CloudFormation/Bicep in that authoring
happens in a general-purpose, imperative-capable LANGUAGE — but the
resources produced are still a declarative graph handed to an engine,
not a sequence of imperative API calls.
```

- Note on `cdktf` (CDK for Terraform): HashiCorp and AWS collaborated on a variant of CDK's programming model that synthesizes to Terraform's JSON configuration format instead of CloudFormation, executed by Terraform's own engine — this narrows the "CDK is AWS-only" statement specifically for `cdktf`, which is multi-cloud because it targets Terraform underneath, but mainstream "AWS CDK" (`aws-cdk-lib`) synthesizes to CloudFormation and is AWS-only.
- The diagram's key structural fact: Terraform and Pulumi are peers (each owns engine + state, each is multi-cloud); CDK is not a peer to CloudFormation, it's a layer on top of it; Bicep is not a peer to Terraform, it's a layer on top of ARM, exactly mirroring CDK's relationship to CloudFormation.

## 5. Hands-On

### 5.1 The Same VPC in Terraform (HCL) vs. Pulumi (TypeScript)

**Purpose:** Show the practical authoring difference between a declarative DSL and a general-purpose language expressing the same declarative intent.

**Syntax:**

```hcl
# Terraform (HCL)
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
  tags = {
    Name = "app-vpc"
  }
}
```

```typescript
// Pulumi (TypeScript)
import * as aws from "@pulumi/aws";

const main = new aws.ec2.Vpc("main", {
  cidrBlock: "10.0.0.0/16",
  tags: { Name: "app-vpc" },
});
```

**Example usage and expected output:**

```bash
$ terraform apply
Plan: 1 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

$ pulumi up
Previewing update...
     Type                 Name    Plan
 +   pulumi:pulumi:Stack  demo    create
 +   └─ aws:ec2:Vpc       main    create
Resources: 2 to create
Do you want to perform this update? yes
Update succeeded in 8s.
```

**Production usage example:** Both patterns are equally valid for a straightforward resource — the practical difference shows up once conditional logic, loops, or reuse across many near-identical resources are needed: Terraform expresses that via `for_each`/`count` and `for` expressions ([§21](../Part3/Section-21-Part3-for-Expressions-and-Splat-Expressions.md), [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)) within HCL's constraints, while Pulumi expresses it with the host language's native loops, functions, and classes, which can be more expressive but also allows accidental non-declarative complexity (hidden side effects, external I/O during synthesis) that HCL structurally prevents.

**Common errors:** Engineers new to Pulumi sometimes write code with real side effects (network calls, file I/O) directly in the "infrastructure definition" code path expecting it to run once per `pulumi up` like a script — but Pulumi's engine may evaluate that code multiple times during preview and update, so non-idempotent side effects in program code cause inconsistent or duplicated behavior in a way HCL's non-Turing-complete design makes structurally impossible.

### 5.2 The Same S3 Bucket in AWS CDK vs. Raw CloudFormation

**Purpose:** Make the CDK-synthesizes-to-CloudFormation relationship concrete rather than abstract.

**Syntax:**

```typescript
// AWS CDK (TypeScript)
import * as s3 from "aws-cdk-lib/aws-s3";

new s3.Bucket(this, "AppBucket", {
  versioned: true,
  encryption: s3.BucketEncryption.S3_MANAGED,
});
```

```yaml
# Equivalent raw CloudFormation (what `cdk synth` produces)
Resources:
  AppBucket:
    Type: AWS::S3::Bucket
    Properties:
      VersioningConfiguration:
        Status: Enabled
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
```

**Example usage and expected output:**

```bash
$ cdk synth > template.yaml    # CDK generates CloudFormation — no infra touched yet
$ cdk deploy                   # hands the synthesized template to CloudFormation, which executes it
AppBucket: creating CloudFormation changeset...
 ✅  AppStack

$ aws cloudformation describe-stacks --stack-name AppStack
{"Stacks": [{"StackStatus": "CREATE_COMPLETE", ...}]}
```

**Production usage example:** Teams already standardized on CloudFormation for governance (Service Control Policies restricting deploys to CloudFormation-managed changesets, StackSets for multi-account rollout) get CDK's higher-level, reusable "construct" abstractions (an S3 bucket with sane encryption/versioning defaults in three lines) while still producing an artifact (the synthesized template) that fits their existing CloudFormation-based governance and audit tooling unchanged.

**Common errors:** Assuming `cdk deploy` is idempotent and safe the same way `terraform apply` is — it is, but through a different mechanism: CDK computes no diff itself; CloudFormation computes a changeset from the synthesized template against its own tracked stack state, so a `cdk deploy` failure mid-rollout leaves the stack in a CloudFormation-managed rollback state (`UPDATE_ROLLBACK_COMPLETE`) that has to be resolved through CloudFormation's own semantics, not Terraform-equivalent state surgery.

## 6. Production Usage Notes

- **Terraform's advantage is provider breadth and multi-cloud maturity.** For organizations managing infrastructure across more than one cloud, or provisioning non-cloud SaaS resources (Datadog dashboards, GitHub repo settings, PagerDuty escalation policies) alongside cloud infrastructure in the same workflow, Terraform's Registry ecosystem ([§10](../Part2/Section-10-Part2-The-Terraform-Registry-and-Sourcing-Providers.md)) is the deepest of any tool compared here.
- **Pulumi's advantage is expressive power for genuinely complex, programmatic infrastructure logic.** Generating hundreds of near-identical resources with real conditional branching, calling out to existing internal libraries, or unit-testing infrastructure code with the same test frameworks used for application code are all more natural in Pulumi than in HCL — at the cost of losing HCL's guardrail that configuration can't have arbitrary side effects.
- **CDK's advantage is AWS-native ergonomics and CloudFormation governance compatibility.** Organizations already invested in CloudFormation-based guardrails (StackSets, drift detection, Service Catalog) get CDK's better authoring ergonomics without abandoning that investment — but remain AWS-only unless adopting `cdktf` specifically.
- **CloudFormation and Bicep's advantage is zero state-management burden.** Because AWS/Azure own execution and state, there's no state file to lock, corrupt, or migrate ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)–[§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) have no equivalent problem class in CloudFormation/Bicep) — a genuine operational simplification, traded against complete lock-in to that one cloud's release cadence for new resource-type support.
- **Time-to-support-new-resource-types differs.** Terraform provider updates (community or HashiCorp-maintained) and CDK/CloudFormation resource support both lag actual cloud API releases somewhat; Bicep and CloudFormation being first-party sometimes get day-one support for new Azure/AWS features that third-party Terraform providers pick up weeks or months later — this gap has narrowed significantly as cloud vendors have invested more in their official Terraform providers.

## 7. Security Considerations

- Terraform and Pulumi's self-managed state means state-file security (encryption at rest, access controls, [§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)) is entirely the operating team's responsibility; CloudFormation and Bicep shift that responsibility to the cloud provider's own IAM model, which reduces one class of operational risk but also reduces visibility and control over exactly how that state is protected.
- Pulumi and CDK, by using general-purpose languages, inherit that language's supply-chain risk surface (npm/PyPI dependency vulnerabilities in the infrastructure-authoring toolchain itself) in a way HCL and raw CloudFormation/Bicep, with no package ecosystem of their own to speak of, do not.
- Policy-as-code enforcement differs by tool: Terraform has Sentinel/OPA ([§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md), [§101](../Part14/Section-101-Part14-Policy-Testing-with-Sentinel-OPA-in-CI.md)), CloudFormation has Guard and Service Control Policies, Pulumi has CrossGuard, and Bicep integrates with Azure Policy — teams evaluating tools for a security-heavy environment should treat "which policy engine integrates with our existing compliance tooling" as a first-class comparison criterion, not an afterthought.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                       | Likely Cause                                                                                                    | Resolution Path                                                                                                                 |
| --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| `cdk deploy` fails partway and the stack is stuck in `UPDATE_ROLLBACK_FAILED`                 | A resource couldn't roll back cleanly; this is a CloudFormation-level stack state, not a CDK bug                | Resolve via CloudFormation console/CLI (continue-update-rollback or manual resource cleanup), then redeploy                     |
| Pulumi program produces different resources on repeated `pulumi preview` runs                 | Non-idempotent side effects (network calls, randomness) embedded directly in program code                       | Move non-deterministic logic out of the resource-declaration code path; use Pulumi's `Config`/data sources for external values  |
| Team picked CDK expecting multi-cloud support and hit an Azure requirement                    | Mainstream AWS CDK (`aws-cdk-lib`) is AWS-only; only `cdktf` targets multiple clouds                            | Evaluate `cdktf` (CDK program synthesizing to Terraform) or migrate the Azure-bound portion to Terraform/Bicep                  |
| Bicep template deploy is rejected for a feature Terraform's azurerm provider already supports | ARM/Bicep resource-type support and Terraform provider support move on different, sometimes divergent schedules | Check the specific ARM API version required; fall back to Terraform's provider or an ARM template `AzAPI` resource escape hatch |

## 9. Best Practices

- Choose based on real organizational constraints — cloud scope (single vs. multi), team language fluency, and existing governance investment — not tool popularity or personal preference; each of these five tools is a legitimate, production-proven choice within its actual scope.
- If multi-cloud or heavy non-cloud (SaaS/API) provider coverage is a requirement, default to Terraform or Pulumi; CDK, CloudFormation, and Bicep are the wrong category of tool no matter how good their AWS/Azure ergonomics are.
- If the organization is deeply AWS-native and already governs infrastructure through CloudFormation-based controls, evaluate CDK before introducing Terraform purely for HCL's declarative purity — the governance-compatibility win is often larger than the authoring-language preference.
- Don't let "our engineers already know TypeScript/Python" be the sole deciding factor — Pulumi's and CDK's use of a general-purpose language is a genuine expressive-power tradeoff (more power, fewer structural guardrails against non-declarative side effects), not merely a syntax preference.

## 10. Common Anti-Patterns / Mistakes

- **Treating this as a "which one is objectively best" question.** Every one of these tools is the right choice in the scope it was designed for; the comparison that matters is fit to an organization's actual cloud footprint and governance model, not a universal ranking.
- **Choosing CDK for a multi-cloud requirement without knowing about the CloudFormation dependency.** A team that adopts mainstream AWS CDK expecting eventual Azure/GCP support without knowing `cdktf` exists as a distinct product will hit a hard wall.
- **Writing genuinely imperative, side-effecting code inside Pulumi or CDK program code** and being surprised when re-runs behave unpredictably — the resource model underneath is still declarative and expects program code to be a pure function from inputs to a resource graph.
- **Assuming CloudFormation/Bicep's lack of a state file means "no operational risk."** It removes state-file-specific risk (corruption, locking) but stack-level failure modes (stuck rollbacks, drift between console changes and the stack's tracked resources) are a structurally similar class of problem under a different name.

## 11. Interview Questions

**🎯 Beginner:** _"What is the fundamental difference between Terraform and AWS CDK?"_
**Model answer:** Terraform is a standalone, multi-cloud IaC tool with its own configuration language (HCL) and its own execution engine and state, supporting AWS, Azure, GCP, and hundreds of other providers. AWS CDK is a framework for writing infrastructure in a general-purpose language (TypeScript, Python, etc.) that gets "synthesized" into a CloudFormation template, which AWS CloudFormation then actually executes — CDK itself has no independent engine or state, and mainstream CDK only targets AWS.
_What the interviewer is probing for:_ Whether the candidate understands CDK's actual relationship to CloudFormation rather than treating it as a Terraform-equivalent peer.

**🎯 Intermediate:** _"When would you recommend Pulumi over Terraform for a new project?"_
**Model answer:** Pulumi makes sense when the team wants to author infrastructure in a general-purpose language they're already fluent in and needs real programmatic capability — complex conditional logic, reuse of existing internal code libraries, or unit testing infrastructure definitions with standard language test frameworks — beyond what HCL's expression language comfortably supports. It's a weaker choice when the team specifically wants HCL's constraint that configuration can't have arbitrary side effects, since Pulumi's general-purpose language allows (and can accidentally introduce) non-idempotent behavior directly in the resource-declaration code path.
_What the interviewer is probing for:_ A balanced, criteria-driven recommendation rather than a language-preference opinion stated as fact.

**🎯 Senior:** _"A team argues CloudFormation is 'strictly safer' than Terraform because there's no state file to corrupt. Evaluate that claim."_
**Model answer:** It's directionally true but overstated. CloudFormation removes one specific risk class — state file corruption, drift between a stale local state file and reality, locking conflicts — because AWS manages execution state itself. But CloudFormation stacks have their own structurally similar failure modes: stuck rollback states (`UPDATE_ROLLBACK_FAILED`), drift between console-made changes and the stack's tracked resources, and changeset execution failures that require the same kind of careful operational handling Terraform state issues do. The risk isn't eliminated, it's moved into AWS's managed system and given different tooling and different failure semantics. The genuinely true part of the claim is narrower: a team never has to worry about losing or corrupting a state file in transit, or misconfiguring a remote backend's locking mechanism, because that responsibility doesn't exist for them at all.
_What the interviewer is probing for:_ Whether the candidate can evaluate a plausible-sounding claim critically rather than accepting or rejecting it wholesale.

**🎯 Architect:** _"You're advising a company running workloads across AWS and Azure, currently using a mix of hand-written CloudFormation and ARM templates maintained by two separate teams with no shared tooling. Propose a consolidation strategy and defend the tool choice."_
**Model answer:** Recommend consolidating onto Terraform (or Pulumi, if the teams have strong language-fluency preferences that make general-purpose-language authoring meaningfully more productive for them) specifically because the core problem is fragmentation across two single-cloud-native tools with no shared workflow, module system, or policy engine — Terraform's multi-cloud provider model directly solves that by letting both teams work in one language, one state model, one CI/CD pattern ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)), and one policy-as-code system (Sentinel/OPA, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) regardless of which cloud a given root module targets. The migration itself should not attempt a big-bang rewrite: use `terraform import` ([§52](../Part7/Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md)) incrementally per resource group/stack, starting with lower-risk environments, running the legacy CloudFormation/ARM stacks and the new Terraform state in parallel with drift checks until each imported stack is verified stable, then decommission the legacy templates stack by stack. The tradeoff being accepted is taking on Terraform's self-managed state operational burden ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)–[§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md)) in exchange for eliminating the larger, ongoing cost of two disconnected, single-cloud toolchains with no shared governance.
_What the interviewer is probing for:_ Ability to make and defend a consolidation decision under real organizational constraints, including a credible migration path — not just naming the "better" tool.

## 12. Common Misconceptions

1. **"CDK is just AWS's version of Terraform."** CDK has no independent execution engine or state — it generates CloudFormation templates that CloudFormation executes; it's structurally closer to "Bicep for AWS" than to Terraform.
2. **"Pulumi isn't really declarative because you write real code."** The authoring language is imperative-capable, but the resource model Pulumi's engine reconciles against state is still a declarative graph of desired resources, computed the same way Terraform's is — the difference is the authoring surface, not the underlying reconciliation model.
3. **"CloudFormation and Bicep have no state, so there's nothing to manage."** They have no separate file a team manages, but the cloud provider still tracks stack/deployment state internally, with its own set of failure modes (stuck rollbacks, drift) that require operational understanding just like Terraform state does.
4. **"Multi-cloud always means Terraform or Pulumi; native tools are only for single-cloud shops."** True in the common case, but `cdktf` specifically extends CDK's authoring model to target Terraform's multi-cloud engine — the "CDK is AWS-only" statement applies to mainstream `aws-cdk-lib`, not to every tool with "CDK" in the name.

## 13. 🔑 Key Takeaways

- The decisive axis across these five tools is where the execution engine and state live: Terraform and Pulumi own both and are multi-cloud; CDK and Bicep generate templates for CloudFormation/ARM to execute; CloudFormation and ARM own execution and state natively, AWS/Azure-only.
- Terraform's core differentiators are HCL's non-Turing-complete declarative constraint and the breadth of its multi-cloud and non-cloud provider ecosystem.
- Pulumi trades HCL's guardrails for general-purpose-language expressive power, at the cost of allowing accidental non-idempotent side effects in program code.
- CDK is not a Terraform peer — it's an authoring layer over CloudFormation, AWS-only unless using the distinct `cdktf` product.
- CloudFormation and Bicep eliminate self-managed state-file risk entirely but introduce structurally similar stack-level failure modes, and lock the organization to a single cloud provider's tooling and release cadence.

## 14. Related Concepts & What's Next

[§2](../Part1/Section-02-Part1-History-Terraform-Origins-IaC-Tooling-Landscape.md) covered the historical origins of these tools briefly; this section gave the detailed technical comparison. [§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md) turns to anti-patterns that occur specifically within Terraform once a team has committed to it. [§110](./Section-110-Part15-Versioning-Strategy-Terraform-Core-Providers-and-Modules.md) covers versioning strategy relevant to whichever tool is chosen. [§111](./Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md) addresses a different but related boundary question — not "which provisioning tool" but "provisioning vs. configuration vs. orchestration" across Terraform, Ansible, and Kubernetes.

**Next Section:** [§108](./Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md) — `Section-108-Part15-Common-Anti-Patterns-Giant-State-Hardcoded-Values-Provider-Sprawl.md`
