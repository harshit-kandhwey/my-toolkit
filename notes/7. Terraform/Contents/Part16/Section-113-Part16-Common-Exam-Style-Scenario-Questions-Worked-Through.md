# Section 113 (Part 16): Common Exam-Style Scenario Questions (Worked Through Step by Step)

## 1. Definition

**Plain language:** This section is a worked problem set — a series of Terraform Associate-style scenario questions, each solved step by step the way you'd actually reason through it under exam conditions, not just answered with a letter.

**Precise definition:** An **exam-style scenario question** presents a small, self-contained Terraform configuration or CLI transcript and asks the candidate to predict behavior (what will `plan` output show, what state will result, what error will occur) rather than recall a fact in isolation. This format mirrors the real HashiCorp Terraform Associate exam's question style, which is dominated by short code/output excerpts with multiple-choice or multiple-select answers. This section works through a representative set spanning the highest-weighted objective areas from [§112](./Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md) (CLI workflow, state, resources/variables, modules).

> 💡 **Tip:** The single most useful exam skill this section trains is reading a `plan` diff symbol-by-symbol. `+` means create, `-` means destroy, `~` (or `-/+`) means update in place, and `-/+` with a different resource address entirely means destroy-then-recreate. Misreading `-/+` as "update" instead of "replace" is the single most common source of wrong answers on state/lifecycle questions.

## 2. Why This Matters

- Scenario questions are how the real exam tests understanding, not fact recall — practicing the reasoning process (not just memorizing this section's answers) is what transfers to novel questions on the actual exam.
- Reading `plan` output correctly is a skill independent of any single question — it recurs across state, lifecycle, and resource-meta-argument questions alike, so investing in it once pays off across many question types.
- These worked scenarios double as a compressed review of Part 4 through Part 8's highest-yield content, useful even outside exam prep as a self-check on production Terraform fluency.

## 3. Prerequisites and Dependencies

Builds directly on [§112](./Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md)'s domain map and time-management strategy. Assumes working familiarity with the CLI workflow ([§24](../Part4/Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md)-[§31](../Part4/Section-31-Part4-Common-CLI-Flags-Automation-Friendly-Patterns.md)), resource meta-arguments ([§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md), [§35](../Part5/Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md), [§36](../Part5/Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)), and state fundamentals ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)-[§52](../Part7/Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md)) — each worked scenario below references the specific section covering the underlying mechanic if a refresher is needed.

## 4. Architecture / Conceptual Diagram

```text
   SCENARIO-QUESTION SOLVING FLOW

   Read the code/output excerpt
            │
            ▼
   Identify the objective area          ┌──────────────────────────┐
   (state? CLI workflow? resource       │ Does the question hinge  │
   meta-arg? module composition?)  ───► │ on PLAN OUTPUT SYMBOLS?  │
            │                           └────────────┬─────────┬───┘
            │                                    yes │         |no
            │                                        ▼         ▼
            │                          Parse +/-/~/-\/+   Trace resource
            │                          precisely first     addressing /
            │                                              dependency order
            ▼                                        │         │
   Eliminate answers that                            └────┬────┘
   contradict a fact you're                               ▼
   certain of (e.g. "count            Differentiate remaining plausible
   produces a list, not a map")  ───► answers using the SPECIFIC mechanic
            │                        tested (not general Terraform vibes)
            ▼
   Select answer; move on if
   time-boxed, flag if still unsure
```

## 5. Hands-On — Worked Scenario Questions

### 5.1 State and Resource Addressing

**Purpose:** Test whether a candidate can reason about what happens to state when a resource is renamed in configuration.

**Syntax (scenario):**

```hcl
# BEFORE
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"
}

# AFTER — resource block renamed, arguments unchanged
resource "aws_instance" "web_server" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"
}
```

**Example usage and expected output:**

```text
Q: After this rename, what does `terraform plan` show, assuming no
   other changes are made?

A) No changes — Terraform matches resources by their arguments, not their address
B) 1 to add, 1 to destroy — Terraform sees this as two unrelated resources
C) 1 to add, 0 to destroy — Terraform infers the rename automatically
D) An error — resource renames are not supported without `moved` blocks

ANSWER: B

Reasoning: Terraform's state maps configuration to real infrastructure
by RESOURCE ADDRESS (`aws_instance.web` vs. `aws_instance.web_server`),
not by argument content. Since the address changed and state still
has an entry for the OLD address, `plan` sees "aws_instance.web_server
doesn't exist in state → create" and "aws_instance.web is in state but
no longer in config → destroy." This produces `1 to add, 1 to destroy`
even though the underlying infrastructure described is identical.

$ terraform plan
  # aws_instance.web will be destroyed
  # aws_instance.web_server will be created
  Plan: 1 to add, 1 to destroy.
```

**Production usage example:** This is exactly the failure mode a `moved` block (or, historically, `terraform state mv`, [§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) exists to prevent — refactoring resource names or moving them between modules without a `moved` block causes real, disruptive destroy-and-recreate cycles in production even when the underlying resource is functionally unchanged.

**Common errors:** Assuming Terraform is "smart enough" to detect a rename by comparing argument values — it deliberately is not, since two genuinely different resources could coincidentally share identical arguments (e.g., two identical `t3.micro` instances).

### 5.2 count vs. for_each Index Stability

**Purpose:** Test understanding of why `for_each` is generally preferred over `count` for resource collections that can shrink from the middle.

**Syntax (scenario):**

```hcl
variable "subnet_names" {
  default = ["a", "b", "c"]
}

resource "aws_subnet" "this" {
  count      = length(var.subnet_names)
  cidr_block = "10.0.${count.index}.0/24"
  tags       = { Name = var.subnet_names[count.index] }
}
```

**Example usage and expected output:**

```text
Q: If "b" is removed from var.subnet_names (leaving ["a", "c"]), what
   does `terraform plan` show?

A) 1 to destroy (the subnet that was "b")
B) 1 to destroy, 1 to change — subnet[1] ("b") is destroyed, and
   subnet[2] no longer exists so nothing about "c" changes
C) 1 to destroy, 1 to change — aws_subnet.this[1] changes from "b" to
   "c" in place, and aws_subnet.this[2] is destroyed
D) No changes — Terraform tracks subnets by name, not index

ANSWER: C

Reasoning: `count` indexes resources positionally (aws_subnet.this[0],
[1], [2]). Removing the middle element shifts every subsequent
element's index down by one. Terraform sees aws_subnet.this[1]
still exists in state AND in the new plan, but its arguments changed
(cidr_block and tags now reflect "c" instead of "b") — so it's an
in-place UPDATE, not a clean destroy of "b". Meanwhile
aws_subnet.this[2] no longer has a corresponding config entry, so
it's destroyed. Net effect: the actual subnet tagged "b" is not
cleanly destroyed — it's repurposed in place as "c", which is rarely
the intended behavior and is the core argument for using `for_each`
(keyed by the stable string itself, §34) instead of `count` whenever
list order/membership can change.
```

**Production usage example:** This exact behavior has caused real production incidents — removing a security group from the middle of a `count`-based list caused Terraform to modify an unrelated, still-attached security group in place instead of cleanly destroying the removed one, briefly changing live firewall rules on a resource nobody intended to touch.

**Common errors:** Assuming `count` and `for_each` are interchangeable stylistic choices — they have materially different state-addressing behavior that matters specifically when the underlying collection can change membership, not just size.

### 5.3 Variable Precedence

**Purpose:** Test knowledge of the exact precedence order Terraform uses to resolve a variable's final value when it's set in multiple places at once.

**Syntax (scenario):**

```bash
# variables.tf
variable "instance_type" {
  default = "t3.micro"
}

# terraform.tfvars
instance_type = "t3.small"

# shell
export TF_VAR_instance_type="t3.medium"
```

```bash
$ terraform apply -var="instance_type=t3.large"
```

**Example usage and expected output:**

```text
Q: What value does `instance_type` resolve to?

A) t3.micro (the declared default)
B) t3.small (terraform.tfvars)
C) t3.medium (the environment variable)
D) t3.large (the -var flag)

ANSWER: D

Reasoning: Terraform's variable precedence, highest to lowest:
  1. -var / -var-file flags on the command line (highest)
  2. *.auto.tfvars / *.auto.tfvars.json (alphabetical)
  3. terraform.tfvars.json
  4. terraform.tfvars
  5. TF_VAR_ environment variables
  6. Declared `default` in the variable block (lowest)
Command-line -var flags always win because they're the most specific,
most recently-stated override at apply time. (§40 covers this table
in full, including .auto.tfvars ordering.)
```

**Production usage example:** CI/CD pipelines rely on this precedence deliberately — a pipeline typically sets baseline values via `.tfvars` checked into the repo, then overrides environment-specific values (like an image tag) via `-var` at the point of `apply`, trusting the flag to win over anything checked in.

**Common errors:** Assuming environment variables (`TF_VAR_*`) are the highest-precedence source because they "feel" more dynamic — they are actually one of the lowest-precedence sources, beaten by every `.tfvars` file and CLI flag.

### 5.4 Data Source vs. Resource Read Timing

**Purpose:** Test understanding of when a `data` source is actually read, relative to `plan` and `apply`.

**Syntax (scenario):**

```hcl
data "aws_ami" "latest" {
  most_recent = true
  owners      = ["099720109477"]
  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd/ubuntu-jammy-*"]
  }
}

resource "aws_instance" "app" {
  ami           = data.aws_ami.latest.id
  instance_type = "t3.micro"
}
```

**Example usage and expected output:**

```text
Q: A new matching AMI is published between `terraform plan -out=tfplan`
   and `terraform apply tfplan`. What does `apply` do?

A) Uses the AMI ID resolved at plan time, ignoring the new AMI
B) Re-queries the data source at apply time and uses the new AMI
C) Fails with an error requiring a fresh plan
D) Prompts interactively to choose which AMI to use

ANSWER: A

Reasoning: A saved plan file (§25) is a frozen, literal record of the
exact actions Terraform will take, INCLUDING already-resolved data
source values. Applying a saved plan file never re-evaluates data
sources or re-computes the diff — that's precisely the point of
saving a plan: what you reviewed is exactly what gets applied, with
no possibility of the world shifting underneath you between plan and
apply. (Running a fresh, un-saved `terraform apply` without a saved
plan file, by contrast, WOULD re-read the data source live at that
moment, since it computes plan and apply in one step.)
```

**Production usage example:** This is precisely why CI/CD pipelines that separate a "plan" job (reviewed by a human or gate) from an "apply" job (executed later) always pass the saved `-out` plan file through to `apply`, rather than re-running `plan` implicitly inside `apply` — it guarantees what was reviewed is exactly what gets executed, per [§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)'s GitOps pattern.

**Common errors:** Assuming `data` sources are "live" at every stage of the workflow — they're only re-read when Terraform actually recomputes a plan, not when applying a plan that was already computed and saved.

### 5.5 Module Output Consumption

**Purpose:** Test understanding of how a root module accesses a value produced deep inside a child module.

**Syntax (scenario):**

```hcl
# modules/network/outputs.tf
output "vpc_id" {
  value = aws_vpc.this.id
}

# root main.tf
module "network" {
  source = "./modules/network"
}

resource "aws_subnet" "public" {
  vpc_id = module.network.vpc_id   # (A)
}
```

**Example usage and expected output:**

```text
Q: Which statement about reference (A) is correct?

A) It's invalid — child module internals are always private to the root
B) It's valid because the child module explicitly declared an output
   named vpc_id; without that output block, the reference would fail
C) It's valid regardless of whether the child module declares an
   output, since Terraform can introspect any resource inside a module
D) It's valid only if the child module is sourced from the public
   Terraform Registry, not a local path

ANSWER: B

Reasoning: A module's internal resources are NOT implicitly exposed
to callers — only values explicitly declared via `output` blocks
inside the child module are accessible from the root as
`module.<name>.<output_name>` (§57). This is a deliberate encapsulation
boundary: a module author can freely refactor internal resource names
without breaking callers, as long as the output contract stays stable.
```

**Production usage example:** This is the entire basis for module versioning discipline ([§60](../Part8/Section-60-Part8-Module-Versioning-and-Version-Constraints.md)) — as long as a module's documented outputs (its public contract) stay stable across a version bump, callers don't need to inspect or care about internal resource renames.

**Common errors:** Trying to reference a child module's resource directly (`module.network.aws_vpc.this.id`) instead of through a declared output — Terraform does not permit reaching into a module's internals from outside it.

## 6. Production Usage Notes

- All five worked scenarios above reflect behaviors that also show up as real production surprises, not just exam trivia — the `count` reindexing issue (§5.2) and the saved-plan-freezes-data-sources behavior (§5.4) in particular are common sources of real incidents, which is exactly why the exam tests them.
- Practicing scenario questions by writing out the full reasoning chain (as done here), not just picking the answer, is what builds the transferable pattern-recognition the exam actually rewards — memorizing these five answers without the reasoning generalizes poorly to differently-worded questions on the same concepts.

## 7. Security Considerations

- §5.3's variable precedence matters for security specifically because a `-var` flag passed on a shared CI runner's command line can be visible in process listings or CI logs — sensitive values should flow through `-var-file` pointed at a securely-generated file or a secrets-manager integration ([§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md), [§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)), never as a literal `-var="db_password=..."` on the command line.
- §5.1 and §5.2's state-mutation behaviors are a reminder that `plan` review before `apply` in a shared environment isn't optional ceremony — a resource silently being destroyed-and-recreated due to a rename, or repurposed in place due to `count` reindexing, is exactly the kind of change that's easy to miss without reading the diff symbols carefully.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                             | Likely Cause                                                                                                                    | Resolution Path                                                                                                                                                                           |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Renaming a resource in config causes an unexpected destroy-and-recreate             | No `moved` block or `terraform state mv` performed alongside the rename                                                         | Add a `moved` block (or run `terraform state mv`) before applying a resource rename ([§51](../Part7/Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md))                        |
| Removing an item from the middle of a `count`-based list changes the wrong resource | `count` addresses resources by positional index, which shifts on removal                                                        | Migrate the collection to `for_each` keyed by a stable identifier ([§34](../Part5/Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md))                                        |
| Applying a saved plan produces different results than expected from `plan` output   | The saved plan is stale — real infrastructure changed after it was generated, and Terraform will reject or warn on the mismatch | Regenerate the plan close to apply time; treat a long gap between plan and apply as a smell ([§25](../Part4/Section-25-Part4-terraform-plan-Reading-Plan-Output-and-Saved-Plan-Files.md)) |
| A resource output from a module can't be referenced in the root module              | The child module never declared an `output` block for that value                                                                | Add the missing `output` block inside the child module ([§57](../Part8/Section-57-Part8-Module-Inputs-and-Outputs.md))                                                                    |

## 9. Best Practices

- Work through scenario questions by writing the full reasoning chain, not just selecting an answer — this is what builds transferable pattern recognition rather than rote memorization of this specific question set.
- When a scenario question involves a `plan` diff, read every symbol (`+`, `-`, `~`, `-/+`) deliberately before touching the answer choices — most wrong answers stem from misreading the diff, not from not knowing the underlying concept.
- Treat every "surprising" scenario answer (like §5.2's `count` reindexing) as a production lesson first and an exam fact second — the ones that feel counterintuitive are exactly the ones worth remembering because they're also the ones most likely to bite in real usage.

## 10. Common Anti-Patterns / Mistakes

- **Answering from vibes instead of tracing the actual mechanic.** A wrong answer to §5.4 ("data sources re-read at apply") stems from a general sense that "Terraform is always up to date," rather than tracing what a saved plan file actually freezes.
- **Assuming `count` and `for_each` are purely stylistic.** They have materially different state-addressing semantics that change what happens to real infrastructure on a collection-membership change, as shown in §5.2.
- **Skipping the reasoning and jumping straight to the answer letter when self-testing.** This produces false confidence — recognizing an answer you've seen before is not the same skill as deriving it from first principles on a novel, differently-worded question.

## 11. Interview Questions

**🎯 Beginner:** _"If you rename a resource block in Terraform configuration without doing anything else, what happens on the next apply?"_
**Model answer:** Terraform destroys the resource under the old address and creates a new one under the new address, even if every argument is identical — because Terraform matches state to configuration by resource address, not by comparing argument values. To rename safely without a destroy/recreate cycle, you use a `moved` block or `terraform state mv` to tell Terraform explicitly that the old and new addresses refer to the same real resource.
_What the interviewer is probing for:_ Whether the candidate understands resource addressing as the actual mechanism behind state matching, not just "Terraform tracks stuff somehow."

**🎯 Intermediate:** _"Why is `for_each` generally recommended over `count` for a list of resources that might shrink or reorder?"_
**Model answer:** `count` addresses resources purely by positional index (`resource[0]`, `resource[1]`, ...). If an item is removed from the middle of the underlying list, every subsequent index shifts down by one, and Terraform sees this as in-place changes to the shifted resources rather than a clean destroy of the removed one — this can silently mutate a resource that was never intended to change. `for_each`, by contrast, keys each resource instance by a stable string (`resource["a"]`, `resource["b"]`), so removing "b" from the underlying map or set cleanly destroys exactly the resource keyed "b" and leaves every other instance completely untouched.
_What the interviewer is probing for:_ Real production awareness of a subtle but consequential state-addressing difference, not just "for_each is the newer/better one."

**🎯 Senior:** _"Walk me through what happens, step by step, if a CI pipeline runs `terraform plan -out=tfplan`, waits two hours for manual approval, then runs `terraform apply tfplan` — and in that two-hour window, someone else applies an unrelated change to the same state."_
**Model answer:** The saved plan file is a frozen snapshot of the diff and the state serial/lineage it was computed against. When `apply tfplan` runs, Terraform checks whether the current remote state still matches what the plan was computed against; if the state has moved on (a new serial from someone else's apply), Terraform refuses to apply the stale plan and returns an error rather than silently applying a plan computed against out-of-date state. This is a deliberate safety mechanism — applying a stale plan against a shifted baseline could produce results the plan review never actually saw. The practical fix is to keep the window between plan and apply short, or accept that a stale-plan rejection means regenerating a fresh plan.
_What the interviewer is probing for:_ Deep, accurate understanding of the plan-apply contract and state consistency guarantees, not just workflow mechanics at a surface level.

**🎯 Architect:** _"A team has a recurring incident pattern: someone renames or restructures resources during a refactor, and it silently causes production destroy-and-recreate cycles that weren't caught in review. How would you change their process, not just their knowledge, to prevent this?"_
**Model answer:** Knowledge alone (teaching `moved` blocks) helps but doesn't scale as a sole fix, since it depends on every engineer remembering to apply it every time. I'd add process guardrails: first, a required `plan` output review step in CI that specifically flags any `-/+` (replace) or `- then +` (destroy+create under different address) action on resources tagged as stateful/production-critical, surfaced prominently rather than buried in a long diff. Second, a pre-merge lint or policy check (via Sentinel/OPA, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md), or a custom CI script) that fails a PR containing a resource address removal paired with a same-PR resource address addition of a similar type, prompting the author to confirm whether a `moved` block was intended. Third, culturally, treat any `plan` showing unexpected replace actions as a hard stop requiring explicit sign-off, never an auto-approved change — this shifts the safety net from individual memory to a structural check everyone's changes pass through.
_What the interviewer is probing for:_ Systems thinking about incident prevention — recognizing that a recurring pattern calls for process/tooling changes, not just better individual training.

## 12. Common Misconceptions

1. **"Terraform detects resource renames automatically by comparing configuration content."** It does not — it matches purely by resource address; content-identical resources under different addresses are treated as entirely unrelated.
2. **"`count` and `for_each` behave identically for list-like resource collections."** They differ specifically in how they respond to membership changes in the middle of a collection, which materially affects which real resources get touched.
3. **"A saved plan file always reflects the absolute latest state of the world at apply time."** It reflects the state of the world at the moment `plan` was run; applying a saved plan against subsequently-changed state is rejected, not silently reconciled.
4. **"Any resource inside a module can be referenced from the root, since Terraform can see the whole configuration."** Only values explicitly exposed via the child module's `output` blocks are accessible from outside it — module internals are otherwise encapsulated.

## 13. 🔑 Key Takeaways

- Terraform matches state to configuration by resource address, not argument content — renames without `moved` blocks or `state mv` cause destroy-and-recreate.
- `count`'s positional indexing can silently mutate the wrong resource when a middle list item is removed; `for_each`'s key-based addressing avoids this.
- Variable precedence, highest to lowest: CLI `-var`/`-var-file`, `.auto.tfvars`, `terraform.tfvars.json`, `terraform.tfvars`, `TF_VAR_*` environment variables, declared defaults.
- A saved plan file freezes data source resolution and the full diff at plan time; applying it never re-reads data sources, and Terraform rejects applying a stale plan against changed state.
- Module outputs are the only way a root module can read a value from inside a child module — internal resources are not implicitly exposed.

## 14. Related Concepts & What's Next

[§114](./Section-114-Part16-CLI-Speed-Techniques-and-Common-Gotchas-for-Exam-Conditions.md) shifts from conceptual scenario-solving to raw CLI speed and gotcha-avoidance under exam time pressure. [§115](./Section-115-Part16-General-Terraform-Interview-Question-Bank.md) broadens into a general interview question bank beyond exam-specific framing. [§116](./Section-116-Part16-Scenario-Based-Infrastructure-Design-Questions.md) applies the same worked-scenario approach to larger, open-ended infrastructure design questions rather than single-mechanic exam questions.

**Next Section:** [§114](./Section-114-Part16-CLI-Speed-Techniques-and-Common-Gotchas-for-Exam-Conditions.md) — `Section-114-Part16-CLI-Speed-Techniques-and-Common-Gotchas-for-Exam-Conditions.md`
