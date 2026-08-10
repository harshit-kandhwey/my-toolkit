# Section 1 (Part 1): What Infrastructure as Code Is; Declarative vs. Imperative Provisioning

## 1. Definition

**Plain language:** Infrastructure as Code (IaC) means describing the servers, networks, databases, and other infrastructure you need in text files — instead of clicking through a cloud console or running one-off commands — and letting a tool read those files and make the real infrastructure match them. The files become the source of truth; the infrastructure is just a reflection of what's written down.

**Precise definition:** **Infrastructure as Code** is the practice of managing and provisioning computing infrastructure through machine-readable definition files, rather than manual, interactive configuration. IaC tools fall into two provisioning philosophies: **imperative** (the file specifies an ordered sequence of steps that produce the desired result — "create a VPC, then create a subnet inside it, then launch an instance in that subnet") and **declarative** (the file specifies only the desired end state — "this VPC, this subnet, this instance should exist" — and the tool computes the steps needed to reach that state from whatever the current state is). Terraform is a **declarative, state-driven** IaC tool: you write HCL (HashiCorp Configuration Language) describing desired infrastructure, and Terraform's engine diffs that description against a recorded **state** file to compute a minimal set of API calls to reconcile reality with intent.

> 💡 **Tip:** The question that separates declarative from imperative isn't "does the tool use a config file?" — plenty of imperative tools do. It's "if I run this twice, does the second run know what the first run already did, or does it try to redo everything?" Declarative tools answer "I know what's already there and only change what's different." Imperative tools, unless carefully written to be idempotent, just re-execute the same steps.

## 2. Why This Matters

- **Reproducibility.** The same `.tf` files produce the same infrastructure whether applied by one engineer today or a different engineer in six months — eliminating "it worked when I clicked it in the console" drift.
- **Auditability and review.** Infrastructure changes go through the same pull-request review process as application code, instead of living only in a change log nobody reads or an admin's memory of what they clicked.
- **Disaster recovery.** If an environment is destroyed, IaC lets you rebuild it from the same declarative files rather than reverse-engineering what existed from screenshots or tribal knowledge.
- **Drift detection.** Declarative tools like Terraform can compare declared state against real infrastructure and surface exactly what has silently changed outside the pipeline (someone manually resized a database, for instance).
- **Scale.** Provisioning 200 near-identical resources (subnets across regions, IAM roles per team) by hand doesn't scale; looping over a declarative resource block with `count` or `for_each` does.
- **Version control as infrastructure history.** `git log` on infrastructure files gives you exactly who changed what, when, and why (via commit messages) — something console-driven changes never provide natively.

## 3. Prerequisites and Dependencies

This section is the entry point of the entire 120-section Terraform roadmap and assumes only general familiarity with cloud computing concepts (accounts, regions, virtual machines) — see the Cloud knowledge base at `../../../6. Cloud` if any of that is unfamiliar. No Terraform-specific knowledge is assumed. [§2](./Section-02-Part1-History-Terraform-Origins-IaC-Tooling-Landscape.md) covers Terraform's specific history and where it sits among other IaC tools; [§3](./Section-03-Part1-Terraform-vs-Configuration-Management-Ansible-Puppet-Chef.md) contrasts provisioning tools like Terraform against configuration-management tools like Ansible.

## 4. Architecture / Conceptual Diagram

```text
   IMPERATIVE APPROACH                    DECLARATIVE APPROACH
   ("how" — ordered steps)                ("what" — desired end state)

   Script:                                Configuration:
   1. az group create ...                 resource "azurerm_resource_group" "rg" {
   2. az network vnet create ...            name = "app-rg"
   3. az vm create ...                    }
                                           resource "azurerm_virtual_network" "vnet" {
   Run again? Re-executes every step —      name = "app-vnet"
   step 1 may now fail ("already          }
   exists") unless the script author      resource "azurerm_linux_virtual_machine" "vm" {
   hand-writes existence checks for         name = "app-vm"
   every single step.                     }
                                                    │
                                                    ▼
                                           ┌────────────────────┐
                                           │  Terraform Engine  │
                                           │  diff: desired vs. │
                                           │  recorded state    │
                                           └────────────────────┘
                                                    │
                                           Run again with no changes?
                                           Diff is empty → no API calls
                                           made. Idempotent by design.
```

- **Imperative tools** (raw shell scripts, most SDK automation, early Chef "recipes") describe a procedure. Idempotency — the property that running the same operation twice produces the same result as running it once — has to be manually engineered into every step.
- **Declarative tools** (Terraform, Kubernetes manifests, CloudFormation) describe an outcome. Idempotency is a structural property of the engine, not something the author has to hand-code: the diff between "what's declared" and "what's recorded/observed" is naturally empty on a second run if nothing changed.
- Terraform's specific twist on "declarative" is that it is **state-driven**: unlike Kubernetes (which continuously reconciles against the live cluster), Terraform computes its diff against a **state file** it maintains itself ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)), then reconciles that against real infrastructure only when you explicitly run `plan`/`apply` — reconciliation is on-demand, not a continuously running control loop.

## 5. Hands-On

### 5.1 Imperative Provisioning with a Shell Script

**Purpose:** Illustrate what imperative, non-idempotent provisioning looks like in practice, as a contrast baseline.

**Syntax:**

```bash
#!/usr/bin/env bash
aws ec2 create-vpc --cidr-block 10.0.0.0/16
aws ec2 create-subnet --vpc-id "$VPC_ID" --cidr-block 10.0.1.0/24
aws ec2 run-instances --image-id ami-0abcdef1234567890 --instance-type t3.micro
```

**Example usage and expected output:**

```bash
$ ./provision.sh
{
    "Vpc": { "VpcId": "vpc-0a1b2c3d4e5f6g7h8", ... }
}
{
    "Subnet": { "SubnetId": "subnet-0a1b2c3d", ... }
}
{
    "Instances": [ { "InstanceId": "i-0a1b2c3d4e5f6g7h8", ... } ]
}

$ ./provision.sh          # run again — NOT idempotent
An error occurred (VpcLimitExceeded) or a second, duplicate VPC is created
```

**Production usage example:** Teams sometimes still use scripts like this for genuinely one-shot, throwaway environments (a scratch sandbox torn down within the hour) where the cost of writing declarative configuration outweighs the benefit — but this pattern does not scale to anything meant to persist or be repeatable.

**Common errors:** Running the script twice either fails outright (resource already exists, where the API rejects a duplicate name) or silently duplicates resources (where the API happily creates a second VPC) — the script itself has no memory of what it already did.

### 5.2 Declarative Provisioning with Terraform

**Purpose:** Show the same intent — a VPC, a subnet, an instance — expressed declaratively, and demonstrate idempotent re-application.

**Syntax:**

```hcl
resource "aws_vpc" "main" {
  cidr_block = "10.0.0.0/16"
}

resource "aws_subnet" "public" {
  vpc_id     = aws_vpc.main.id
  cidr_block = "10.0.1.0/24"
}

resource "aws_instance" "app" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"
  subnet_id     = aws_subnet.public.id
}
```

**Example usage and expected output:**

```bash
$ terraform apply
Terraform will perform the following actions:
  # aws_vpc.main will be created
  # aws_subnet.public will be created
  # aws_instance.app will be created

Plan: 3 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 3 added, 0 changed, 0 destroyed.

$ terraform apply          # run again — idempotent
No changes. Your infrastructure matches the configuration.
```

**Production usage example:** This is the default pattern for essentially all production infrastructure in a Terraform-managed organization — the same configuration files are applied repeatedly (often via CI/CD, [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) with the engine itself guaranteeing that a no-op run makes no API calls.

**Common errors:** A common beginner mistake is expecting `terraform apply` on unchanged configuration to still "do something" — seeing `No changes` is the correct, desired outcome, not a sign that nothing worked.

## 6. Production Usage Notes

- **Declarative does not mean "no ordering."** Terraform still computes an execution order internally — it builds a dependency graph ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) from resource references (like `aws_subnet.public` referencing `aws_vpc.main.id` above) and creates/destroys resources in the correct order automatically. The author never writes that order explicitly, which is precisely the point.
- **State is what makes declarative reconciliation possible at all.** Without a record of what Terraform previously created, the engine would have no way to distinguish "this resource in my config doesn't exist yet, create it" from "this resource in my config exists and is unchanged, leave it alone." [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md) covers why this file exists and what breaks without it.
- **Plan before apply is the practical safety net of the declarative model.** Because Terraform computes the full diff before touching anything, `terraform plan` ([§25](../Part4/Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md)) lets an operator review exactly what will change — add, change, or destroy — before any API call is made, something imperative scripts generally cannot offer without significant extra engineering.

## 7. Security Considerations

- Configuration files (`.tf`) frequently reference credentials, secrets, or sensitive values (database passwords, API keys) either directly or via variables — treating `.tf`/`.tfvars` files as sensitive-adjacent artifacts from day one avoids later remediation; [§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md) covers marking variables `sensitive` and [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) covers the deeper risk of secrets ending up in state.
- Because declarative IaC is usually run by an automated pipeline with broad cloud credentials (to create/modify/destroy infrastructure), the blast radius of a compromised CI/CD pipeline running Terraform is typically far larger than a compromised individual's console session — least-privilege execution roles ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)) matter more, not less, once provisioning is automated.
- Storing IaC in version control is a security win (auditability) but also a risk if secrets are checked in alongside configuration — `.gitignore` for `*.tfvars` containing secrets and use of dedicated secrets managers ([§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md), [§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)) are standard mitigations.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                | Likely Cause                                                                                  | Resolution Path                                                                                                                                                                              |
| ---------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Re-running an imperative script fails with "resource already exists"   | The script has no state/memory of prior runs; it's not idempotent by construction             | Rewrite provisioning declaratively (Terraform) or add manual existence checks to every step                                                                                                  |
| `terraform apply` proposes to recreate a resource that already exists  | Terraform's state file doesn't know about a resource that was created outside Terraform       | `terraform import` ([§52](../Part7/Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md)) to bring the existing resource under management instead of recreating |
| Team member says "the console shows something different from the code" | Someone made a manual change in the console (drift) that was never reflected in configuration | Run `terraform plan` to detect drift; reconcile via `terraform refresh` workflow ([§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md))                            |

## 9. Best Practices

- Default to declarative tooling (Terraform, or equivalent) for anything meant to persist beyond a short-lived experiment — reserve imperative scripts for genuinely disposable, one-shot use cases.
- Treat the `.tf` configuration as the single source of truth; discourage (and where possible, block via IAM permissions) manual console changes to Terraform-managed resources, since they create drift the declarative model can't see until the next plan.
- Always review `terraform plan` output before `apply` in any shared or production environment — the declarative model's main safety advantage is a pre-change diff, and skipping that review discards it.

## 10. Common Anti-Patterns / Mistakes

- **Writing "declarative-looking" configuration that's secretly imperative.** For example, using `local-exec` provisioners ([§64](../Part9/Section-64-Part9-local-exec-and-remote-exec-Provisioners.md)) to shell out to imperative scripts from within a Terraform resource — this reintroduces non-idempotent behavior inside an otherwise declarative tool and is one reason HashiCorp actively discourages provisioners ([§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md)).
- **Assuming declarative means "safe by default."** A declarative tool will just as happily plan to destroy a production database as create one if the configuration says so — declarative removes _ordering_ mistakes, not _intent_ mistakes; `prevent_destroy` ([§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) exists precisely to guard against this.
- **Mixing manual console changes with Terraform-managed resources.** Even a single manual edit to a Terraform-managed resource creates drift that surfaces confusingly on the next `plan`, often mid-incident when it's least convenient to debug.

## 11. Interview Questions

**🎯 Beginner:** _"What is Infrastructure as Code, in one sentence?"_
**Model answer:** Infrastructure as Code is managing servers, networks, and other infrastructure by writing and version-controlling text files that describe them, and using a tool to create or update the real infrastructure to match those files, instead of manually configuring it through a console or one-off commands.
_What the interviewer is probing for:_ Whether the candidate understands IaC as a practice (files as source of truth) rather than just naming tools.

**🎯 Intermediate:** _"Explain the difference between declarative and imperative infrastructure provisioning, with an example of each."_
**Model answer:** Imperative provisioning specifies an ordered sequence of steps to reach a result — e.g., a shell script that runs `create-vpc`, then `create-subnet`, then `run-instances` in order. Declarative provisioning specifies only the desired end state — e.g., a Terraform configuration stating a VPC, subnet, and instance should exist — and the tool itself computes what steps are needed, in what order, by comparing the declared state to what's currently recorded. The key practical difference is idempotency: re-running declarative configuration with no changes does nothing, while re-running an imperative script naively re-executes every step.
_What the interviewer is probing for:_ Conceptual clarity, and specifically whether the candidate connects the distinction to idempotency rather than just reciting definitions.

**🎯 Senior:** _"A teammate says Terraform is 'declarative, so it always knows the true state of infrastructure.' Is that accurate?"_
**Model answer:** Not fully — Terraform is state-driven, not continuously reconciling. It computes its diff against a state file it maintains itself, which is only as accurate as the last `refresh` (implicit in `plan`/`apply`, [§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md)). If infrastructure changes outside Terraform between runs (manual console edit, another pipeline), the state file is stale until the next plan/apply cycle detects the drift. This is different from, say, Kubernetes, which runs a continuous control loop reconciling against live cluster state. Terraform's declarative reconciliation is on-demand, not continuous.
_What the interviewer is probing for:_ Whether the candidate has an accurate mental model of Terraform's specific reconciliation mechanism, not just IaC buzzwords — this distinction matters for reasoning about drift.

**🎯 Architect:** _"You're advising a team currently managing infrastructure with a large collection of imperative Bash/Python provisioning scripts wrapped in Makefiles. What's the actual case for migrating to declarative IaC, and what should they NOT expect it to fix automatically?"_
**Model answer:** The case is primarily about reducing the engineering cost of correctness at scale: idempotency, dependency ordering, and drift detection become structural properties of the tool instead of hand-maintained logic scattered across scripts, which reduces both bugs and onboarding cost as the script collection grows. It also meaningfully improves reviewability — declarative diffs (`plan` output) are far easier to review in a PR than reading imperative script logic to infer its effect. What it does NOT automatically fix: it doesn't remove the need for good module boundaries and naming conventions (a badly organized Terraform codebase is just as unmaintainable as badly organized scripts, [§106](../Part15/Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md)); it doesn't eliminate operational risk from destructive changes (a bad `apply` can still be catastrophic, arguably faster than a bad script since one command touches everything); and it introduces new failure modes the team must learn — state file corruption, locking conflicts ([§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)), and provider version drift ([§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)) — that a script-based approach never had to think about.
_What the interviewer is probing for:_ A balanced, non-dogmatic assessment of the migration's real trade-offs, not "Terraform is strictly better."

## 12. Common Misconceptions

1. **"Declarative means the tool doesn't need to think about ordering."** It absolutely does — Terraform just derives ordering automatically from resource references ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)) instead of the author specifying it manually.
2. **"IaC and Terraform are the same thing."** Terraform is one implementation of the IaC pattern; CloudFormation, ARM/Bicep, Pulumi, and CDK ([§2](./Section-02-Part1-History-Terraform-Origins-IaC-Tooling-Landscape.md)) are others, with different design trade-offs.
3. **"Declarative tools are always safer than imperative scripts."** They eliminate a specific class of bugs (ordering, non-idempotency) but a mistaken declarative intent (e.g., accidentally declaring a production resource should not exist) is just as destructive, often more so because it executes uniformly.
4. **"If `terraform apply` shows no changes, the infrastructure is definitely correct."** It means the infrastructure matches Terraform's _recorded state_ — if state itself is stale or was never refreshed, "no changes" can mask real drift until the next accurate refresh.

## 13. 🔑 Key Takeaways

- Infrastructure as Code means infrastructure is defined in version-controlled files that are the source of truth, not manual console actions.
- The declarative vs. imperative distinction hinges on idempotency: declarative tools describe desired end state and compute the diff themselves; imperative tools describe steps that must be manually engineered to be safe to re-run.
- Terraform is declarative and state-driven: it reconciles configuration against a state file on-demand (at `plan`/`apply` time), not continuously.
- The dependency graph and correct ordering are derived automatically from resource references — the author never writes execution order by hand.
- Declarative does not mean inherently safe; it removes ordering/idempotency bugs, not the risk of a mistaken but internally consistent declared intent.

## 14. Related Concepts & What's Next

[§2](./Section-02-Part1-History-Terraform-Origins-IaC-Tooling-Landscape.md) traces Terraform's specific origins and situates it against other IaC tools (CloudFormation, ARM/Bicep, Pulumi, CDK) that also implement the declarative model differently. [§3](./Section-03-Part1-Terraform-vs-Configuration-Management-Ansible-Puppet-Chef.md) draws the boundary between provisioning tools like Terraform and configuration-management tools like Ansible/Puppet/Chef. [§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md) opens up the dependency graph only gestured at here. [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md) covers the state file that makes Terraform's declarative reconciliation possible at all.

**Next Section:** [§2](./Section-02-Part1-History-Terraform-Origins-IaC-Tooling-Landscape.md) — `Section-02-Part1-History-Terraform-Origins-IaC-Tooling-Landscape.md`
