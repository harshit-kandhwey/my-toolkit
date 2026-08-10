# Section 6 (Part 1): Prerequisites Recap (Cloud Fundamentals, CLI Basics)

## 1. Definition

**Plain language:** Before diving into Terraform's language and workflow in Part 2 onward, it's worth explicitly naming the baseline knowledge this roadmap assumes — cloud computing concepts (accounts, regions, IAM, networking basics) and command-line comfort — so gaps can be filled from this repo's existing knowledge bases before they cause confusion later.

**Precise definition:** This section is a **consolidated prerequisite checkpoint**, not new Terraform material. It enumerates the specific cloud-fundamentals and CLI-fundamentals concepts that later sections assume without re-explaining, maps each to where it's covered in depth elsewhere in this repo, and gives a short self-check so a reader can identify gaps before proceeding. Terraform itself is provider-agnostic ([§2](./Section-02-Part1-History-Terraform-Origins-IaC-Tooling-Landscape.md), [§4](./Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md)), but nearly every hands-on example from Part 2 onward uses a real cloud provider (primarily AWS, with Azure/GCP examples in Part 11) to stay concrete — so provider-specific concepts like regions, IAM, and resource identifiers are assumed baseline knowledge from this point forward.

> 💡 **Tip:** If any item in the checklist below feels unfamiliar, the right move is to spend 20–30 minutes in the referenced knowledge base now — Terraform's own concepts (state, providers, the graph) are hard enough to learn without simultaneously learning what a VPC or an IAM role is for the first time via a Terraform error message.

## 2. Why This Matters

- **Terraform errors are frequently cloud-API errors surfaced through Terraform's output**, not Terraform-specific problems — recognizing "this is an IAM permissions error" vs. "this is a Terraform state error" requires baseline cloud literacy.
- **The CLI workflow (Part 4) assumes comfort with shells, environment variables, and exit codes** — concepts this section names explicitly so Part 4 can move quickly without re-teaching them.
- **Skipping this checkpoint is a common cause of frustration in Part 2–5**, where examples assume the reader already knows what a region, an availability zone, or an IAM role is, rather than explaining cloud concepts inline.
- **This repo already has full, dedicated coverage of these prerequisites** — re-deriving them inside the Terraform roadmap would duplicate content and dilute focus; this section exists to point, not re-teach.

## 3. Prerequisites and Dependencies

This section is itself the prerequisite checkpoint for [§8](../Part2/Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md) onward (all of Part 2 through Part 17) — it depends only on [§1](./Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md)–[§5](./Section-05-Part1-Installation-and-Setup-tfenv-package-managers-version-pinning.md) of this Part. It references the Cloud knowledge base at `../../../6. Cloud/00-Roadmap`, the Linux knowledge base at `../../../2. Linux/00-Roadmap` for shell/CLI fundamentals, and the Git knowledge base at `../../../1. GIT/00-Roadmap` for version control basics assumed from Part 12 (Terraform Cloud VCS-driven workflows) and Part 14 (CI/CD) onward.

## 4. Architecture / Conceptual Diagram

```text
                    Prerequisite Knowledge Feeding This Roadmap

  ┌──────────────────────────┐
  │   Cloud Fundamentals     │──► Needed for: Part 2 (provider auth),
  │  (accounts, regions,     │    Part 5 (resources/data sources),
  │   IAM, networking)       │    Part 11 (multi-cloud patterns),
  │  See: ../../../6. Cloud  │    Part 13 (secrets/IAM)
  └──────────────────────────┘
  ┌──────────────────────────┐
  │   CLI / Shell Basics     │──► Needed for: Part 4 (CLI workflow),
  │  (shells, env vars,      │    Part 9 (provisioners/SSH),
  │   exit codes, piping)    │    Part 14 (CI/CD pipelines)
  │  See: ../../../2. Linux  │
  └──────────────────────────┘
  ┌──────────────────────────┐
  │   Git / Version Control  │──► Needed for: Part 12 (VCS-driven
  │  (commits, branches, PRs)│    Terraform Cloud workflows),
  │  See: ../../../1. GIT    │    Part 14 (GitOps for Terraform)
  └──────────────────────────┘
                    │
                    ▼
        Terraform Roadmap Parts 2–17
        (this repo, Contents/Part2 onward)
```

- This roadmap does not re-teach any of the three prerequisite pillars above — it assumes them and links out where a gap needs filling, consistent with this repo's overall structure of independent-but-cross-referenced knowledge bases.

## 5. Hands-On

### 5.1 Self-Check: Cloud Fundamentals Readiness

**Purpose:** Verify baseline cloud literacy before proceeding, using AWS as the concrete example (since it's the primary provider used in this roadmap's examples).

**Syntax:**

```bash
aws sts get-caller-identity
aws ec2 describe-regions --query "Regions[].RegionName" --output table
```

**Example usage and expected output:**

```bash
$ aws sts get-caller-identity
{
    "UserId": "AIDAEXAMPLE123456",
    "Account": "123456789012",
    "Arn": "arn:aws:iam::123456789012:user/jsmith"
}

$ aws ec2 describe-regions --query "Regions[].RegionName" --output table
---------------------
|  DescribeRegions  |
+-------------------+
|  us-east-1         |
|  us-west-2         |
|  eu-west-1         |
+-------------------+
```

**Production usage example:** This is the same identity/region check an operator runs before any Terraform `init`/`apply` against a new AWS account — if this command doesn't work, no Terraform AWS example in this roadmap will work either, since Terraform's AWS provider authenticates using the same underlying credential chain as the AWS CLI ([§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md)).

**Common errors:** `Unable to locate credentials` here means AWS CLI/SDK credential configuration (not yet Terraform-specific) needs setting up first — see the Cloud knowledge base's IAM/credentials sections before attempting any Terraform provider authentication examples.

### 5.2 Self-Check: CLI/Shell Readiness

**Purpose:** Verify the baseline shell comfort (environment variables, exit codes, command chaining) assumed throughout the CLI-heavy Part 4 and Part 9 material.

**Syntax:**

```bash
export TF_LOG=DEBUG
terraform plan; echo "exit code: $?"
```

**Example usage and expected output:**

```bash
$ export TF_VAR_region="us-east-1"
$ echo $TF_VAR_region
us-east-1

$ terraform plan; echo "exit code: $?"
No changes. Your infrastructure matches the configuration.
exit code: 0
```

**Production usage example:** Reading and setting environment variables (like `TF_VAR_*` for variable input, [§40](../Part6/Section-40-Part6-Variable-Precedence-and-Assignment-Methods.md), or `TF_LOG` for debug output) and checking a command's exit code (`0` = success, non-zero = failure, used by CI/CD to decide whether a pipeline stage passed) are baseline skills this roadmap assumes from Part 4 onward without re-explaining.

**Common errors:** Not understanding that `terraform plan` returns a **non-zero exit code when changes are detected** in certain flag combinations (e.g., `terraform plan -detailed-exitcode` returns `2` for changes, `0` for none, `1` for error) trips up CI/CD pipelines that naively treat any non-zero exit as failure — covered fully in [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md).

## 6. Production Usage Notes

- **This roadmap's hands-on examples default to AWS** for concreteness (matching the AWS knowledge base already in this repo at `../../../6. Cloud`), with dedicated Azure and GCP deep-dives in Part 11 — readers whose primary cloud is Azure or GCP can still follow Parts 1–10 (provider-agnostic core concepts) directly, substituting provider-specific details mentally, before Part 11's dedicated coverage.
- **CLI comfort compounds in value as the roadmap progresses** — Part 4's CLI workflow, Part 9's SSH-based provisioners, and Part 14's CI/CD integration all assume the reader can comfortably read and write shell commands without each one being explained from first principles.
- **Certification exam relevance**: the Terraform Associate exam explicitly does not test AWS/Azure/GCP-specific knowledge directly, but nearly every scenario question is grounded in a cloud context — cloud fundamentals remain practically necessary even though they're not the exam's direct subject.

## 7. Security Considerations

- Cloud credentials used for local Terraform experimentation (following this roadmap's examples) should still follow least-privilege principles from the start — using a personal AWS root account or an over-privileged IAM user "just for learning" builds bad habits that carry into production usage; [§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md) covers least-privilege execution roles for Terraform specifically, but the habit should start here.
- Never commit cloud credentials (access keys, service principal secrets) to version control while working through this roadmap's examples — this applies even to throwaway learning repositories, since accidental public pushes of real credentials are a common, costly mistake.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                            | Likely Cause                                                            | Resolution Path                                                                                                                                                                                               |
| ---------------------------------------------------------------------------------- | ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Terraform AWS examples fail with credential errors immediately                     | AWS CLI/SDK credentials never configured, unrelated to Terraform itself | Run `aws sts get-caller-identity` to isolate whether the problem is credentials (fix via Cloud KB) or Terraform-specific ([§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md)) |
| Reader is lost on shell syntax used in CLI examples (`$?`, env var export, piping) | Gap in baseline shell/CLI fundamentals                                  | Review Linux knowledge base shell fundamentals sections before continuing past Part 4                                                                                                                         |
| Reader unfamiliar with regions/availability zones referenced in examples           | Gap in baseline cloud fundamentals                                      | Review Cloud knowledge base's core concepts sections (`../../../6. Cloud`) before Part 2 onward                                                                                                               |

## 9. Best Practices

- Treat this section as a genuine checkpoint, not boilerplate — a reader who can't confidently explain what an IAM role or an availability zone is will struggle far more with [§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md) (provider authentication) or [§75](../Part11/Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md) (AWS provider deep dive) than the extra 30 minutes reviewing prerequisites now would cost.
- Set up a real (but low-cost or free-tier) cloud account and CLI access before Part 2, rather than reading Terraform examples passively — this roadmap is designed for hands-on execution, and the hands-on sections throughout assume a working, authenticated CLI.
- Bookmark the Cloud, Linux, and Git knowledge bases referenced here — later Parts (11, 12, 14) will reference them again for progressively more advanced prerequisite concepts (multi-account patterns, VCS-driven workflows, CI/CD).

## 10. Common Anti-Patterns / Mistakes

- **Skipping prerequisite gaps and pushing through Terraform-specific sections anyway**, then misattributing cloud-API confusion (an IAM permissions error, a region mismatch) to Terraform being confusing, when the actual gap is cloud fundamentals.
- **Using an over-privileged personal cloud account "just for learning"** and carrying that habit into how production Terraform execution roles get scoped later.
- **Assuming CLI/shell fluency isn't necessary "because Terraform has its own commands."** Terraform's CLI workflow is still invoked from, and interacts with, a shell — environment variables, exit codes, and piping remain directly relevant ([§29](../Part4/Section-29-Part4-CLI-Configuration-terraformrc-Config-Blocks-Credentials-Helpers.md), [§31](../Part4/Section-31-Part4-Common-CLI-Flags-Automation-Friendly-Patterns.md), [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)).

## 11. Interview Questions

**🎯 Beginner:** _"What cloud and CLI knowledge should someone have before learning Terraform?"_
**Model answer:** Basic cloud fundamentals — what a cloud account, region, and IAM role/permission are — since most real Terraform configuration provisions cloud resources and assumes that vocabulary. And basic command-line comfort — running commands, reading exit codes, setting environment variables — since Terraform is a CLI tool invoked from a shell and its automation-friendly patterns (CI/CD, scripting) depend on shell fluency.
_What the interviewer is probing for:_ Whether the candidate recognizes Terraform's dependence on surrounding infrastructure knowledge, not treating it as a standalone skill.

**🎯 Intermediate:** _"Why does this roadmap explicitly call out cloud fundamentals as a prerequisite rather than teaching AWS/Azure/GCP concepts inline as they come up?"_
**Model answer:** Because Terraform's core value is being provider-agnostic ([§1](./Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md), [§4](./Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md)) — the language, state model, and CLI workflow are the same regardless of which cloud is being provisioned. Teaching AWS-specific concepts (VPCs, IAM policies, regions) inline throughout the Terraform material would conflate two genuinely separate skill sets and duplicate content this repo already covers in depth in its dedicated Cloud knowledge base. Separating them keeps the Terraform roadmap focused on what's actually Terraform-specific, while still pointing to where cloud fundamentals live for anyone with a gap.
_What the interviewer is probing for:_ Understanding of why provider-agnostic tooling still has provider-specific prerequisites, and appreciation for modular documentation/learning structure.

**🎯 Senior:** _"A junior engineer keeps hitting confusing errors in early Terraform examples and assumes Terraform itself is broken or badly designed. How would you diagnose whether the actual gap is Terraform or something else?"_
**Model answer:** I'd look at the error's origin first: does it come from Terraform Core itself (HCL syntax errors, graph/dependency errors, state errors) or is it a cloud API error being passed through Terraform's output (an `AccessDenied`, an invalid region, a resource limit)? The vast majority of "Terraform is confusing" complaints from engineers new to cloud work are actually cloud-API errors surfacing through Terraform's error reporting — an IAM permissions problem, for instance, looks identical whether triggered by the AWS CLI directly or by Terraform's AWS provider, because it's the same underlying AWS API call failing the same way. I'd have them run the equivalent raw AWS CLI command (e.g., `aws sts get-caller-identity`, or directly attempt the API call Terraform is trying to make) to isolate whether the problem exists independent of Terraform — if it does, it's a cloud fundamentals or credentials gap, not a Terraform problem, and coaching should focus there rather than deeper into Terraform-specific debugging.
_What the interviewer is probing for:_ Practical debugging judgment and the ability to correctly attribute a symptom to the right layer — directly exercising the same "which layer is responsible" reasoning introduced architecturally in [§4](./Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md).

**🎯 Architect:** _"You're onboarding a team of application developers with strong coding skills but limited cloud/infrastructure background onto a Terraform-based platform. How would you sequence their ramp-up, given what you know about Terraform's prerequisites?"_
**Model answer:** I would not start with Terraform syntax. I'd sequence it: first, enough cloud fundamentals to be dangerous — accounts, regions, the specific handful of resource types (VPC, subnet, compute instance, IAM role) their actual workloads will touch, likely via a scoped subset of this repo's Cloud knowledge base rather than its full breadth. Second, CLI/shell fluency if it's genuinely missing, since every subsequent Terraform exercise assumes it. Only then would I introduce Terraform itself, starting from declarative concepts ([§1](./Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md)) and architecture ([§4](./Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md)) before syntax (Part 3), so they understand _why_ Terraform behaves the way it does before memorizing HCL mechanics. I'd deliberately have them work against a real, low-stakes sandbox account from day one rather than only reading — cloud and Terraform concepts both compound much faster with hands-on practice than passive reading, and errors encountered hands-on are exactly what builds the "which layer is this error coming from" diagnostic instinct that separates a comfortable Terraform user from one who's memorized syntax without understanding it.
_What the interviewer is probing for:_ Ability to design a coherent onboarding sequence that respects the real prerequisite dependencies (cloud → CLI → Terraform) rather than jumping straight to the tool everyone wants to learn, and valuing hands-on practice over passive reading.

## 12. Common Misconceptions

1. **"Terraform teaches you cloud concepts as you go."** It assumes them — Terraform's documentation and error messages assume familiarity with the underlying cloud provider's concepts and terminology, not the other way around.
2. **"CLI fluency is optional since Terraform Cloud/Enterprise has a UI."** Even UI-driven workflows ([§84](../Part12/Section-84-Part12-Terraform-Cloud-Overview-Organizations-Workspaces-and-Runs.md) onward) are built on top of the same CLI-workflow concepts (plan, apply, state) — understanding the CLI first makes the UI's behavior legible rather than mysterious.
3. **"This roadmap will teach AWS/Azure/GCP in depth."** It uses them for concrete, worked examples (primarily AWS, with dedicated Azure/GCP coverage in Part 11) but assumes baseline cloud fundamentals are already covered elsewhere in this repo, not taught fresh here.
4. **"Skipping the prerequisite self-check costs nothing if you're a fast learner."** Cloud and Terraform confusion compound — misattributing a cloud-API error to "Terraform being weird" wastes far more time than the prerequisite check would have.

## 13. 🔑 Key Takeaways

- This section is a checkpoint, not new material: it names the cloud-fundamentals and CLI-fundamentals prerequisites assumed from [§8](../Part2/Section-08-Part2-The-Terraform-Core-Provider-Plugin-Model-RPC-Provider-SDK.md) onward and points to this repo's dedicated Cloud, Linux, and Git knowledge bases for any gaps.
- Terraform's provider-agnostic design ([§1](./Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md), [§4](./Section-04-Part1-Terraform-Architecture-Overview-Core-Providers-State-Plugins.md)) means cloud-specific knowledge is a genuine prerequisite, not something this roadmap re-teaches inline.
- Many apparent "Terraform is confusing" moments are actually cloud-API errors or CLI/shell gaps surfacing through Terraform's output — correctly attributing the layer responsible is a real diagnostic skill worth building early.
- Git/version-control basics become relevant specifically from Part 12 (VCS-driven Terraform Cloud workflows) and Part 14 (CI/CD, GitOps) onward.
- Setting up a real, low-privilege cloud account and working through examples hands-on is strongly preferred over passive reading for retention throughout this roadmap.

## 14. Related Concepts & What's Next

[§1](./Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md)–[§5](./Section-05-Part1-Installation-and-Setup-tfenv-package-managers-version-pinning.md) established Terraform's conceptual and architectural foundation; this section closes the loop on prerequisites before syntax and workflow begin in earnest. [§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md) returns to provider authentication patterns specifically, building directly on the cloud-credentials self-check performed here. [§75](../Part11/Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md)–[§77](../Part11/Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md) return to AWS/Azure/GCP-specific provisioning in full depth once the provider-agnostic core (Parts 2–10) is complete. [§7](./Section-07-Part1-Terraform-Associate-Certification-Landscape-and-How-This-Roadmap-Maps-to-It.md) (next, closing this Part) maps this entire roadmap explicitly against the HashiCorp Certified: Terraform Associate exam curriculum.

**Next Section:** [§7](./Section-07-Part1-Terraform-Associate-Certification-Landscape-and-How-This-Roadmap-Maps-to-It.md) — `Section-07-Part1-Terraform-Associate-Certification-Landscape-and-How-This-Roadmap-Maps-to-It.md`
