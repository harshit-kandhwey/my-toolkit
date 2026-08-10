# Section 117 (Part 17): Progressive Hands-On Labs (Beginner to Production-Style, Exam-Simulation Labs)

## 1. Definition

**Plain language:** This section is a set of labs, not a new concept — a ladder of hands-on exercises that starts with "provision one instance" and ends with a single scenario combining a broken configuration, a resource that needs importing, and a state migration, done under a clock. Unlike Kubernetes' hands-on certification exams, the Terraform Associate exam itself is multiple-choice/multiple-select ([§112](../Part16/Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md)) — but the exam's scenario questions test exactly the behavioral reasoning ("what does this plan do," "what happens to state here") these labs build through actually doing the work, not just reading about it.

**Precise definition:** This is the **capstone lab sequence** for the entire 120-section roadmap: four progressively harder, self-contained labs that require applying concepts from many earlier Parts simultaneously rather than in isolation, culminating in an exam-simulation scenario that exercises the same underlying task categories the exam's scenario-based questions probe — writing resources, fixing broken configuration, importing existing infrastructure, and migrating state — even though the real exam asks about these as multiple-choice reasoning questions rather than live tasks. Each lab states an objective, a step-by-step task list with real HCL, and an explicit note tying it back to the specific earlier sections it exercises — the goal is integration and retrieval practice, not first exposure to new material.

## 2. Why This Matters

- **Reading 116 sections of explanation does not, by itself, build exam or production readiness.** The Terraform Associate exam rewards being able to correctly predict _behavior_ from a given configuration ([§112](../Part16/Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md)) — what a `plan` will show, what `count` vs. `for_each` produces, what happens to state after a given command — and that predictive skill is best built by actually running the commands and watching the real output, not by re-reading definitions.
- **Real production changes rarely respect Part boundaries.** A single onboarding task might require writing a new resource, importing one a teammate created manually last quarter, and fixing a broken `for_each` expression, all in one sitting — these labs are deliberately built to force that same cross-cutting practice.
- **This is the last rehearsal before the real thing** — whether "the real thing" is a certification attempt, a first production `apply`, or an on-call incident that touches Terraform-managed infrastructure.

## 3. Prerequisites and Dependencies

This section assumes completion of Parts 1–16 — specifically [§1](../Part1/Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md) (declarative provisioning), [§24](../Part4/Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md)–[§26](../Part4/Section-26-Part4-terraform-apply-and-terraform-destroy.md) (the init/plan/apply/destroy CLI workflow), [§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md)–[§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) (resource blocks and `count`/`for_each`), [§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)–[§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md) (variables and outputs), [§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)–[§54](../Part7/Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) (state, remote backends, and `import`), [§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)–[§62](../Part8/Section-62-Part8-Module-Design-Best-Practices-and-Anti-Patterns.md) (modules), and [§106](../Part15/Section-106-Part15-Project-Structure-Best-Practices-Monorepo-vs-Polyrepo.md)–[§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md)'s best-practices and anti-patterns synthesis. A local Terraform installation ([§5](../Part1/Section-05-Part1-Installation-and-Setup-tfenv-package-managers-version-pinning.md)) and either a real or mocked cloud provider (the labs below use AWS syntax but translate directly to Azure/GCP equivalents from Part 11) are required to actually perform these labs; they are not theoretical.

## 4. Architecture / Conceptual Diagram

```text
                    PROGRESSIVE LAB DIFFICULTY CURVE (§117)

  Lab 1                Lab 2                  Lab 3                   Lab 4
  Beginner             Intermediate           Production-Style        Exam Simulation
  ─────────            ─────────────          ────────────────        ────────────────
  One instance         + variables            Multi-module,           Write + import +
  + variables          + outputs              remote state,           fix broken config
  + outputs            + count/for_each       multi-environment,      + migrate state
  (§32, §39, §42)       (§34, §43)             + CI pipeline           under time limit
                                                (§46-§49, §55-§58,      (§32, §52, §53, §34)
                                                §69-§71, §102)

  single resource   →   parameterized,     →  team-scale,          →  multi-domain,
  correctness            reusable config       collaborative config     timed, integrated

  ───────────────────────────────────────────────────────────────────────────────────►
                          increasing scope, increasing realism, decreasing time budget
```

- Each lab is a strict superset of the skills exercised by the one before it — Lab 4 does not introduce new HCL syntax, it recombines everything from Labs 1–3 under exam-like time pressure and with deliberately broken starting material.
- The curve mirrors this roadmap's own Part ordering: Lab 1 draws almost entirely from Parts 3–6, Lab 2 adds Part 5's meta-arguments, Lab 3 pulls in Parts 7, 8, 10, and 14, and Lab 4 is a synthesis exercise identical in spirit to the exam-domain breakdown in [§112](../Part16/Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md).

## 5. Hands-On

### Lab 1 — Beginner: Provision a Single Instance with Variables and Outputs

**Objective:** Get one compute instance running with its size and name parameterized by input variables, and its resulting ID surfaced as an output — the smallest complete unit of "a real Terraform project," not just a bare resource block.

**Tasks:**

1. Create a new directory `lab1/` with `main.tf`, `variables.tf`, and `outputs.tf` ([§16](../Part3/Section-16-Part3-Terraform-File-Structure-and-Conventions.md)'s file structure convention).
2. In `variables.tf`, declare:

```hcl
variable "instance_name" {
  type        = string
  description = "Name tag for the lab instance"
  default     = "lab1-instance"
}

variable "instance_type" {
  type        = string
  description = "EC2 instance type"
  default     = "t3.micro"
}
```

3. In `main.tf`, declare the provider and a single `aws_instance` resource whose `tags.Name` and `instance_type` reference the two variables above:

```hcl
provider "aws" {
  region = "us-east-1"
}

resource "aws_instance" "lab" {
  ami           = "ami-0abcdef1234567890"
  instance_type = var.instance_type

  tags = {
    Name = var.instance_name
  }
}
```

4. In `outputs.tf`, output the instance's `id` and `public_ip`:

```hcl
output "instance_id" {
  value = aws_instance.lab.id
}

output "instance_public_ip" {
  value = aws_instance.lab.public_ip
}
```

5. Run `terraform init`, `terraform plan`, and `terraform apply`, confirming the plan shows `1 to add` and the apply produces both outputs.
6. Re-run `terraform apply` with `-var="instance_type=t3.small"` and confirm the plan shows an in-place update (not a replace) for `instance_type`.

**What this exercises:** Resource block anatomy ([§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md)), input variable declaration and defaults ([§39](../Part6/Section-39-Part6-Input-Variables-Declaration-Types-and-Defaults.md)), output value declaration ([§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md)), and the core init/plan/apply loop ([§24](../Part4/Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md)–[§26](../Part4/Section-26-Part4-terraform-apply-and-terraform-destroy.md)).

**Common errors:** Forgetting that `outputs.tf` values are only populated after a successful `apply` — running `terraform output` before the first `apply` completes returns nothing, which is expected, not a bug.

### Lab 2 — Intermediate: Parameterize with `for_each` and Sensitive Variables

**Objective:** Extend Lab 1 into a small, reusable pattern that provisions a named set of instances from a map, with one sensitive input handled correctly.

**Tasks:**

1. Replace the single `aws_instance` block with a `for_each`-based block driven by a map variable:

```hcl
variable "instances" {
  type = map(object({
    instance_type = string
  }))
  default = {
    web = { instance_type = "t3.micro" }
    api = { instance_type = "t3.small" }
  }
}

resource "aws_instance" "lab" {
  for_each      = var.instances
  ami           = "ami-0abcdef1234567890"
  instance_type = each.value.instance_type

  tags = {
    Name = each.key
  }
}
```

2. Add a `sensitive` variable representing a fake database password, and pass it into a `random_password`-backed `aws_db_instance` stand-in (or a `null_resource` with a `triggers` map if no RDS budget is available) to observe redacted plan output:

```hcl
variable "db_password" {
  type      = string
  sensitive = true
}
```

3. Update `outputs.tf` to output the map of instance IDs: `output "instance_ids" { value = { for k, v in aws_instance.lab : k => v.id } }`.
4. Run `terraform plan` and confirm each instance is addressed as `aws_instance.lab["web"]` and `aws_instance.lab["api"]`, not by numeric index.
5. Remove the `web` entry from the `instances` map and re-plan — confirm only `aws_instance.lab["web"]` is destroyed and `aws_instance.lab["api"]` shows no change at all.

**What this exercises:** `for_each` over a map and stable key-based addressing ([§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)), sensitive variables and what they do and do not protect ([§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)), and output values built from `for` expressions ([§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md), [§21](../Part3/Section-21-Part3-for-Expressions-and-Splat-Expressions.md)).

**Common errors:** Passing a `list` directly to `for_each` instead of a `map` or `set` — this produces `Error: Invalid for_each argument`; convert with `toset()` or restructure into a map, as covered in [§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md).

### Lab 3 — Production-Style: Multi-Module, Remote State, Multi-Environment, CI Pipeline

**Objective:** Restructure Labs 1–2 into a production-shaped project: a reusable child module, remote state with locking, directory-based environment separation, and a CI pipeline that runs `plan` on pull requests and `apply` on merge.

**Tasks:**

1. Create a `modules/compute/` directory containing a self-contained child module (its own `main.tf`, `variables.tf`, `outputs.tf`) that accepts `instance_name` and `instance_type` and exposes `instance_id` as an output ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)–[§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md)).
2. Create `environments/dev/` and `environments/prod/` directories, each calling the module with environment-specific values and each with its **own** `backend.tf`:

```hcl
# environments/dev/backend.tf
terraform {
  backend "s3" {
    bucket = "acme-tfstate-dev"
    key    = "lab3/terraform.tfstate"
    region = "us-east-1"
  }
}

# environments/dev/main.tf
module "compute" {
  source        = "../../modules/compute"
  instance_name = "dev-web"
  instance_type = "t3.micro"
}
```

3. Duplicate the pattern for `environments/prod/`, pointing at a **separate** state bucket (`acme-tfstate-prod`) — this is directory-based, not workspace-based, environment separation, deliberately, per the guidance in [§73](../Part10/Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md).
4. Run `terraform init` and `terraform apply` independently in each environment directory and confirm each has its own, independent state file with no shared backend.
5. Write a minimal CI pipeline definition (GitHub Actions syntax, per [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) that runs `terraform fmt -check`, `terraform validate`, and `terraform plan` on every pull request touching `environments/**`, and gates `terraform apply` behind a manual approval on merge to `main`.
6. Intentionally introduce a naming collision (reuse the same S3 key across both environments' backends) and observe how state locking ([§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) or an entirely wrong resource set being planned reveals the mistake — then fix it.

**What this exercises:** Module structure and composition ([§55](../Part8/Section-55-Part8-What-Modules-Are-Root-Module-vs.-Child-Modules.md)–[§58](../Part8/Section-58-Part8-Calling-Modules-Local-Registry-Git-Sources.md)), remote backends and state locking ([§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md)–[§50](../Part7/Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)), directory-based (not CLI-workspace-based) environment separation ([§70](../Part10/Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md), [§73](../Part10/Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md)), and CI/CD pipeline integration ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md), [§103](../Part14/Section-103-Part14-GitOps-for-Terraform-PR-Based-Plan-Apply-Workflows.md)).

**Common errors:** Using CLI workspaces (`terraform workspace new prod`) instead of separate directories for this lab's dev/prod split — this is the exact anti-pattern [§73](../Part10/Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) warns against, since a shared backend block means both "environments" would share credentials and a single backend regardless of workspace name.

### Lab 4 — Exam Simulation: Write, Import, Fix, and Migrate

**Objective:** A single, time-boxed (45-minute) scenario combining writing a new resource, importing a pre-existing one, fixing a deliberately broken configuration, and migrating state — practicing hands-on the same four task categories that the real (multiple-choice) exam's scenario questions ask you to reason about abstractly.

**Tasks:**

1. **Write:** Given a requirement ("add an S3 bucket named `acme-lab4-artifacts` with versioning enabled"), write the resource block from scratch, including the separate `aws_s3_bucket_versioning` resource required by the modern AWS provider's split-resource model, and apply it.
2. **Import:** You are told a security group named `lab4-sg` already exists in the account, created manually outside Terraform. Write the matching `resource "aws_security_group" "lab4" { ... }` block, then bring it under management with `terraform import aws_security_group.lab4 sg-0123456789abcdef0` ([§52](../Part7/Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md)), and run `terraform plan` until it shows zero diff — adjusting your written configuration to match the real resource's actual arguments, not the other way around.
3. **Fix:** You are handed a pre-broken `main.tf` with two seeded defects: a `for_each` block being passed a `list` instead of a `set`/`map` (`Error: Invalid for_each argument`), and a `count`-based resource where a middle list element was removed, causing an unwanted destroy/recreate plan ([§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)) — diagnose both from `terraform plan` output alone and fix them without being told which lines are wrong in advance.
4. **Migrate:** Given a working local-backend configuration, reconfigure it to use a remote S3 backend and run `terraform init -migrate-state` ([§53](../Part7/Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md)), confirming afterward that `terraform state list` shows the same resources as before the migration and that `terraform plan` reports zero changes.
5. Time yourself; stop at 45 minutes regardless of completion and review what remained undone as a gap-analysis input for further Part 16 review ([§112](../Part16/Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md)–[§116](../Part16/Section-116-Part16-Scenario-Based-Infrastructure-Design-Questions.md)).

**What this exercises:** Resource authoring from a requirement ([§32](../Part5/Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md)), `terraform import` and matching configuration to real-world state ([§52](../Part7/Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md)), diagnosing `count`/`for_each` addressing errors from plan output alone ([§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)), and state migration via backend reconfiguration ([§53](../Part7/Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md)) — the same four task categories the real exam's hands-on portion draws from.

**Common errors:** Attempting to fix the `import` task by editing the security group in the cloud console to match a guessed configuration, rather than writing configuration that matches the _actual_ imported resource — `import` only creates the state-to-real-world mapping; it never generates matching HCL for you (in Terraform versions without the newer `-generate-config-out` flag), so the configuration must be written to match what was actually imported.

### Stretch Goal: Lab 5 — Multi-Environment Incident Under Simulated On-Call Conditions

For teams wanting a fifth, harder rung: combine Labs 1–4 into one longer-running project with dev/staging/prod directories, inject two simultaneous unrelated faults (a state lock left stale by a crashed CI run in one environment, and a provider version constraint drifted out of range in another), and hand the scenario to someone who did not set it up. This mirrors an actual on-call page far more closely than any single-fault lab can, and is the natural bridge from "lab exercise" to real incident response.

## 6. Production Usage Notes

- These labs are deliberately ordered so each one's "what could go wrong" step is the actual learning objective, not an afterthought — Lab 2's `for_each` removal and Lab 3's backend-key collision are the most instructive moments in each lab, not edge cases to skip.
- Re-running Lab 4 multiple times with different seeded defects (a broken `depends_on` instead of a broken `for_each`, a different resource type to import) is more valuable than running it once and moving on — the exam and production changes both present novel combinations of the same small set of root causes.
- Treat the 45-minute cap in Lab 4 as non-negotiable practice discipline: the Terraform Associate exam is strictly time-boxed, and the instinct to "just take a few more minutes" is exactly the habit this lab exists to correct before it costs real exam time.
- Consider pairing these labs with a partner for Lab 4 specifically — one person seeds the defects without telling the other, which more accurately simulates "nobody warned you what broke" than self-injected faults ever can.

## 7. Security Considerations

- Lab 3's remote backend and Lab 4's state migration should never be practiced against a shared or production account — use a disposable sandbox account or a local mock provider; the deliberately broken states and destructive state-migration steps are exactly the kind of action that must stay confined to disposable environments.
- Never commit the `.tfstate` files these labs generate to version control, even in a throwaway lab repository — treat every lab's state file with the same discipline [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) describes for production state, since lab resources can still contain realistic-looking sensitive values.
- Tear down every lab's resources (`terraform destroy`) when finished, and confirm the destroy actually completed — leftover lab infrastructure billed to a real account is one of the most common, avoidable costs of hands-on practice.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                               | Likely Cause                                                                                                                                         | Resolution Path                                                                                          |
| ------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Lab 1 `terraform apply` fails with a credentials error before any resource is touched | Provider authentication ([§14](../Part2/Section-14-Part2-Provider-Authentication-Patterns-AWS-Azure-GCP.md)) not configured in the shell environment | Verify credentials with the provider's own CLI (`aws sts get-caller-identity`) before re-running `apply` |
| Lab 2 `for_each` map produces unexpected extra/missing instances on re-plan           | Map keys changed unintentionally (e.g. a typo) between runs, not a real membership change                                                            | Diff the map variable's current vs. intended value directly before trusting the plan output              |
| Lab 3 both environments show the same state list despite separate backends            | Backend `key` value accidentally reused across environments' `backend.tf` files                                                                      | Give each environment a distinct backend bucket and/or key; re-run `init -reconfigure` per environment   |
| Lab 4 import step leaves `terraform plan` showing non-zero changes                    | Written configuration doesn't fully match the imported resource's actual arguments                                                                   | Adjust configuration attribute-by-attribute against `terraform state show` output until plan is empty    |
| Lab 4 state migration leaves resources missing from `terraform state list`            | Migration was run against the wrong backend config, or interrupted mid-migration                                                                     | Restore from the pre-migration local `terraform.tfstate` backup Terraform creates automatically, retry   |

## 9. Best Practices

- Run every lab against a disposable sandbox account or a local mock, rather than a shared environment, so destructive steps (Lab 4's migration, Lab 3's backend reconfiguration) carry no real risk.
- Do each lab cold first, without referring back to its source sections, then use a failed or incomplete attempt as the trigger to re-read the specific §N sections it exercises — this mirrors real retrieval practice rather than copy-along tutorial-following.
- Time-box Lab 4 strictly and log how far you got, then repeat it a week later with different seeded defects to check whether the diagnostic instinct — not just the specific fix — has actually stuck.
- Always run `terraform destroy` and verify a clean `terraform state list` (empty) at the end of each lab session, matching the discipline expected of any real Terraform project.

## 10. Common Anti-Patterns / Mistakes

- **Treating these labs as read-through exercises rather than actually typing every command and every line of HCL** — the value is in the muscle memory of reading real `plan` output and diagnosing it, which reading alone does not build.
- **Skipping the "break it, then fix it" steps** (Lab 2's `for_each` removal, Lab 4's seeded defects) because they feel like extra work — these are the single most exam-relevant and production-relevant moments in the whole lab sequence.
- **Running Lab 4 once, succeeding, and considering exam readiness "done"** — a single successful pass proves the concept was understood once, not that it will be applied correctly under a novel combination of defects next time.
- **Practicing Lab 3's backend reconfiguration or Lab 4's state migration against a shared or production-adjacent account** to save the setup time of a disposable one — the setup time is trivial compared to the cost of an actual incident.

## 11. Interview Questions

**🎯 Beginner:** _"Walk me through how you'd verify that a Terraform-provisioned instance and its outputs are actually correct after `apply`."_
**Model answer:** First `terraform show` or `terraform state show <resource>` to confirm the resource's recorded attributes match what was intended, then `terraform output` to confirm the declared outputs resolved to real, non-null values, and finally a direct check against the provider's own console or CLI (e.g., `aws ec2 describe-instances`) to confirm the real-world object matches what state believes exists — trusting `Apply complete!` alone isn't the same as confirming the actual infrastructure is correct.
_What the interviewer is probing for:_ A methodical, layered verification habit rather than assuming a successful apply means the infrastructure is definitely correct.

**🎯 Intermediate:** _"In Lab 4's import step, you imported a security group but `terraform plan` still shows changes. What does that mean, and how do you fix it?"_
**Model answer:** It means the HCL I wrote doesn't fully match the real resource's actual current arguments — `terraform import` only creates the state-to-real-world ID mapping; it doesn't generate or validate matching configuration for you (absent the newer `-generate-config-out` flag). I'd run `terraform state show` on the imported resource to see its actual recorded attribute values, then adjust my configuration attribute-by-attribute until `terraform plan` reports zero changes, confirming configuration and real-world state are now in agreement.
_What the interviewer is probing for:_ Accurate understanding of what `import` does and doesn't do — a very common practical gotcha and a frequently tested exam scenario.

**🎯 Senior:** _"Lab 3 has you separate dev and prod by directory rather than by CLI workspace. Justify that design choice to a teammate who thinks workspaces would be simpler."_
**Model answer:** CLI workspaces share one backend block and one set of provider credentials across every workspace on a given configuration — switching workspaces changes only which state file is active, nothing about the backend or the credentials used to reach it. For dev and prod specifically, that means a compromised or misdirected credential in one environment has identical reach into the other, which is precisely the risk HashiCorp's own guidance warns against ([§73](../Part10/Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md)). Directory-based separation, by contrast, lets each environment have its own backend bucket, its own execution role, and independently pinned provider versions — a mistake or compromise in dev structurally cannot reach prod. It's more files, but the extra structure buys a real security boundary that workspace-name conventions alone cannot provide.
_What the interviewer is probing for:_ Whether the candidate can articulate the structural (not stylistic) reason workspaces are discouraged for environment isolation, not just recite "workspaces are for state, not environments."

**🎯 Architect:** _"How would you extend these four labs into an onboarding program for new hires joining a platform team that manages Terraform at scale?"_
**Model answer:** I'd keep the four-tier difficulty curve but extend each lab with a "why did we design it this way" retrospective discussion after completion, tying each lab's failure mode back to a real incident or design decision from the platform's own history — Lab 3's backend-key collision mapped to an actual past state-corruption incident, for instance, makes the lesson concrete rather than abstract. I'd add a fifth, org-specific lab exercising whatever the platform team's actual module registry, CI pipeline, and policy-as-code gates ([§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)) look like, since these four labs are deliberately generic and exam-aligned rather than tied to any one organization's tooling. Finally, I'd track completion and time-to-fix metrics across new hires over successive cohorts, since a lab sequence that never gets measured for effectiveness tends to calcify into ritual rather than staying a genuine skill-building tool.
_What the interviewer is probing for:_ Ability to extend a generic exercise into an organizationally useful, measurable onboarding tool rather than treating it as a fixed artifact.

## 12. Common Misconceptions

1. **"Completing these labs once means the material is mastered."** Retrieval practice research is consistent on this: spaced repetition with varied seeded defects builds durable skill far better than a single successful pass.
2. **"These labs are only useful for exam preparation."** The same skills — writing a resource from a requirement, importing an unmanaged resource, diagnosing a broken plan, migrating state safely — are exactly what a first production onboarding task or incident response actually demands; the exam-simulation framing is a forcing function for realism, not the sole purpose.
3. **"`terraform import` writes the matching configuration for you."** As Lab 4 demonstrates directly, `import` only establishes the state-to-real-world mapping; the engineer must still write (or, with newer tooling, review and correct generated) configuration matching the resource's actual arguments.
4. **"CLI workspaces would have been simpler for Lab 3's environment split."** As the Lab 3 walkthrough and its senior interview answer make explicit, that simplicity comes at the cost of shared backend and credentials across environments — exactly the isolation gap [§73](../Part10/Section-73-Part10-When-Workspaces-Are-the-Wrong-Tool.md) addresses.

## 13. 🔑 Key Takeaways

- These four labs deliberately increase in both technical scope and time pressure, moving from single-resource correctness (Lab 1) to a full exam-style, multi-domain, timed scenario (Lab 4).
- Each lab's deliberately broken or destructive step (a `for_each` list error, a stale backend key, a seeded plan defect) is the most instructive part of the lab, not an optional extra.
- Verification must happen against real command output (`plan`, `state show`, `state list`) rather than by reading configuration alone, since configuration describes intent, not necessarily the resulting real-world or recorded state.
- Repetition with varied seeded defects, not a single successful pass, is what builds the diagnostic instinct both the certification exam and real production work actually demand.
- Always run these labs against a disposable sandbox, given the genuinely destructive steps built into Labs 3 and 4 by design.

## 14. Related Concepts & What's Next

These labs are the practical, hands-on complement to Part 16's exam-domain breakdowns and scenario question banks ([§112](../Part16/Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md)–[§116](../Part16/Section-116-Part16-Scenario-Based-Infrastructure-Design-Questions.md)) — where Part 16 built exam-day strategy and question familiarity, this section builds the muscle memory of actually executing under the same conditions. Having now practiced the roadmap's concepts end-to-end rather than section-by-section, the next section consolidates every Part's single most important takeaway into one structured checklist, serving as a final compressed review artifact for exam day or a pre-deployment production review.

**Next Section:** [§118](./Section-118-Part17-Consolidated-Key-Takeaways-Checklist.md) — `Section-118-Part17-Consolidated-Key-Takeaways-Checklist.md`
