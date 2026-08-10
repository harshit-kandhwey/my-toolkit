# Section 33 (Part 5): Data Sources: Reading External and Existing Infrastructure

## 1. Definition

**Plain language:** A data source lets Terraform look something up without creating, changing, or deleting it — the AMI ID for the latest Amazon Linux image, the ID of a VPC that another team's Terraform project already created, the current AWS account ID you're authenticated as. It's Terraform's "read" operation, as opposed to the "create/update/delete" a resource block performs.

**Precise definition:** A **data source** is declared with `data "<PROVIDER_TYPE>" "<LOCAL_NAME>" { ... }` and represents a read-only query against a provider's API, evaluated during `terraform plan` (specifically during the refresh phase, [§12](../Part2/Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md)) rather than owning any lifecycle. Unlike a resource, Terraform never creates, updates, or destroys the object a data source reads — it has zero ownership of that object's lifecycle, and running `terraform destroy` never deletes what a data source points at. Data source results become **computed values**, referenceable elsewhere in configuration as `data.<TYPE>.<NAME>.<attribute>`, and are re-evaluated on every plan unless the queried arguments are unchanged and the provider deems a re-read unnecessary.

> 💡 **Tip:** The single distinction that matters most: a `resource` block answers "what should exist, and Terraform is responsible for making it so"; a `data` block answers "what already exists, and Terraform just wants to know about it." Confusing the two — for instance, expecting `terraform destroy` to clean up something referenced only via a `data` block — is one of the most common early misunderstandings.

## 2. Why This Matters

- **Data sources are how Terraform integrates with infrastructure it doesn't own** — a shared VPC managed by a networking team's separate Terraform state, an AMI published by a cloud provider or a separate image-baking pipeline (Packer), a DNS zone that predates this project.
- **They avoid hardcoding values that change over time or by region**, such as always resolving "the latest Amazon Linux 2023 AMI" dynamically instead of pinning a specific AMI ID that eventually goes stale or is deprecated.
- **They enable safe cross-stack references without merging state files** — one team's Terraform project can read outputs from another's infrastructure (via `terraform_remote_state` as a data source, or provider-native data sources) without both teams needing to share a single state file or root module.
- **Getting data-source vs. resource wrong has real safety implications**: assuming a data source "creates" something it doesn't leads to a plan/apply that silently does nothing, while assuming a resource is merely a "lookup" (and therefore safe to `destroy`) can delete real, possibly shared, infrastructure.
- **Data sources still participate in the dependency graph** ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)), so understanding how they're ordered relative to resources — and their limitation of not being able to depend on a resource that doesn't exist yet, in most cases — matters for correct configuration.

## 3. Prerequisites and Dependencies

This section builds directly on [§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md)'s resource-addressing model — data source addresses use the parallel `data.<TYPE>.<NAME>` grammar. [§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md) (resource graph) and [§12](../Part2/Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md) (execution model: refresh/plan/apply) are prerequisite for understanding _when_ data sources are evaluated relative to resources. [§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md) (provider configuration) applies identically to data sources, since a data source is served by the same provider plugin as its sibling resources.

## 4. Architecture / Conceptual Diagram

```text
        RESOURCE                              DATA SOURCE
   ┌───────────────────────┐           ┌────────────────────────────┐
   │ resource "aws_vpc"    │           │ data "aws_vpc" "existing"  │
   │        "main" {       │           │ {                          │
   │   cidr_block = "..."  │           │   filter {                 │
   │ }                     │           │     name   = "tag:Name"    │
   │                       │           │     values = ["prod-vpc"]  │
   │ Terraform OWNS this   │           │   }                        │
   │ object's lifecycle:   │           │ }                          │
   │  create / update /    │           │                            │
   │  destroy              │           │ Terraform only READS this  │
   │                       │           │ object. No create/update/  │
   │ terraform destroy     │           │ destroy. terraform destroy │
   │  → deletes the VPC    │           │  → never touches it.       │
   └───────────────────────┘           └────────────────────────────┘

   PLAN/REFRESH TIMELINE

   terraform plan
        │
        ▼
   ┌────────────────────────────────────────────────────────────┐
   │ Refresh phase: data sources without dependencies on        │
   │ not-yet-created resources are READ NOW, values become      │
   │ known immediately.                                         │
   │                                                            │
   │ Data sources that reference a resource's computed          │
   │ attribute (e.g. an ID known only after apply) are          │
   │ deferred — their read happens during apply, after that     │
   │ resource is created, shown in plan as                      │
   │ "(known after apply)".                                     │
   └────────────────────────────────────────────────────────────┘
```

- Most data sources with fully static arguments (filters, names, tags) resolve **immediately at plan time** — their values appear concretely in `plan` output, not as `(known after apply)`.
- A data source that depends on a resource not yet created (via an attribute reference) cannot be resolved until that resource exists — Terraform defers the read to `apply` time, and the plan shows it as unknown until then.
- Data sources have no state "ownership" entry the way resources do for destroy purposes, but their last-read result **is** cached in the state file so that `plan` output and dependent resources have a value to compare against between runs.

## 5. Hands-On

### 5.1 A Basic Lookup Data Source

**Purpose:** Resolve the latest matching AMI ID dynamically instead of hardcoding one.

**Syntax:**

```hcl
data "<TYPE>" "<LOCAL_NAME>" {
  <filter/query arguments>
}
```

**Example usage and expected output:**

```hcl
data "aws_ami" "amazon_linux" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-x86_64"]
  }
}

resource "aws_instance" "web" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t3.micro"
}
```

```bash
$ terraform plan
data.aws_ami.amazon_linux: Reading...
data.aws_ami.amazon_linux: Read complete after 1s [id=ami-0abcdef1234567890]

  # aws_instance.web will be created
  + resource "aws_instance" "web" {
      + ami           = "ami-0abcdef1234567890"
      + instance_type = "t3.micro"
    }

Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** This is the standard pattern for base images across most cloud providers — teams almost never hardcode AMI/image IDs directly, since they're region-specific and are periodically deprecated; a data source keeps the reference current without a manual update every time the provider publishes a new image.

**Common errors:** `Error: no matching AMI found` means the filter criteria (owner, name pattern) matched zero images in the current region — a very common mistake is copying an `aws_ami` data block from documentation without adjusting the region or filter pattern for the actual account/region being used.

### 5.2 Referencing Existing, Externally-Managed Infrastructure

**Purpose:** Integrate with a VPC created and managed by a separate Terraform project (or manually), without taking ownership of it.

**Syntax:**

```hcl
data "aws_vpc" "existing" {
  filter {
    name   = "tag:Name"
    values = ["prod-vpc"]
  }
}
```

**Example usage and expected output:**

```hcl
data "aws_vpc" "existing" {
  filter {
    name   = "tag:Name"
    values = ["prod-vpc"]
  }
}

resource "aws_subnet" "app" {
  vpc_id     = data.aws_vpc.existing.id
  cidr_block = "10.0.5.0/24"
}
```

```bash
$ terraform plan
data.aws_vpc.existing: Reading...
data.aws_vpc.existing: Read complete after 1s [id=vpc-0a1b2c3d4e5f6g7h8]

  # aws_subnet.app will be created
  + resource "aws_subnet" "app" {
      + vpc_id     = "vpc-0a1b2c3d4e5f6g7h8"
      + cidr_block = "10.0.5.0/24"
    }

Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** This is the standard shape of a "spoke" Terraform project (an application team's subnet/instance provisioning) referencing a "hub" project's shared networking (a platform team's VPC) without both teams sharing state — a common organizational pattern at companies with a dedicated networking/platform team ([§78](../Part11/Section-78-Part11-Cross-Provider-Patterns-Shared-Modules-Across-Clouds.md), [§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md)).

**Common errors:** `Error: multiple VPCs matched; use additional constraints to reduce matches to a single VPC` occurs when filter criteria aren't specific enough and more than one object matches — data sources that expect a single result fail loudly rather than silently picking one, which is a deliberate safety behavior.

### 5.3 Data Sources That Depend on Resources (Deferred Read)

**Purpose:** Show what happens when a data source's arguments depend on a resource created in the same plan/apply — a case where the read cannot happen immediately.

**Syntax:**

```hcl
data "<TYPE>" "<NAME>" {
  <arg> = <resource>.<name>.<attribute>
}
```

**Example usage and expected output:**

```hcl
resource "aws_instance" "web" {
  ami           = data.aws_ami.amazon_linux.id
  instance_type = "t3.micro"
}

data "aws_ebs_volumes" "web_volumes" {
  filter {
    name   = "attachment.instance-id"
    values = [aws_instance.web.id]   # depends on a resource not yet created
  }
}
```

```bash
$ terraform plan
  # aws_instance.web will be created
  + resource "aws_instance" "web" { ... }

  # data.aws_ebs_volumes.web_volumes will be read during apply
  # (config refers to values not yet known)
 <= data "aws_ebs_volumes" "web_volumes" {
      + ids = (known after apply)
    }

Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** This pattern shows up whenever a data source needs to inspect the result of infrastructure being created in the same apply — for instance, querying attached volumes on an instance that's also being provisioned — and it's a signal that the data source cannot be used to gate anything at plan time; its value is genuinely unknown until apply runs.

**Common errors:** Trying to use such a deferred data source's result inside a `count`/`for_each` expression ([§34](./Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md)) on another resource produces `Error: Invalid count argument` — count/for_each arguments must be known at plan time, and a data source deferred to apply time cannot satisfy that requirement.

### 5.4 The `terraform_remote_state` Data Source for Cross-Stack References

**Purpose:** Read outputs from a different Terraform state file entirely — the canonical way to consume another project's outputs without shared state.

**Syntax:**

```hcl
data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket = "..."
    key    = "..."
    region = "..."
  }
}
```

**Example usage and expected output:**

```hcl
data "terraform_remote_state" "network" {
  backend = "s3"
  config = {
    bucket = "org-tfstate"
    key    = "network/terraform.tfstate"
    region = "us-east-1"
  }
}

resource "aws_instance" "web" {
  subnet_id = data.terraform_remote_state.network.outputs.public_subnet_id
}
```

```bash
$ terraform plan
data.terraform_remote_state.network: Reading...
data.terraform_remote_state.network: Read complete after 1s

  # aws_instance.web will be created
  + resource "aws_instance" "web" {
      + subnet_id = "subnet-0a1b2c3d"
    }

Plan: 1 to add, 0 to change, 0 to destroy.
```

**Production usage example:** This is a common (if increasingly discouraged in favor of dedicated outputs APIs or Terraform Cloud run triggers, [§88](../Part12/Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md)) pattern for stitching together independently-managed layers of infrastructure — networking, platform, and application teams each keep their own state ([§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md)) while still consuming each other's published outputs ([§42](../Part6/Section-42-Part6-Output-Values-Declaration-Dependencies-and-Consumption.md)).

**Common errors:** `Error: state snapshot was created by Terraform vX.Y, which is newer than current vA.B` occurs when the remote state was last written by a newer Terraform version than the one reading it — remote state consumers must stay on a compatible or newer CLI version than any producer they read from.

## 6. Production Usage Notes

- **Data sources are re-evaluated on every `plan`/`apply` by default**, meaning a data source pointed at mutable external infrastructure (a VPC's tags, an AMI matching a wildcard pattern) can silently change what it resolves to between runs even if your own configuration didn't change — this is a common source of "why did my plan show a change when I didn't touch anything" confusion.
- **Data sources cannot be targeted with `-target` for destruction** ([§37](./Section-37-Part5-Resource-Targeting-and-Partial-Applies.md)) — since they own nothing, `-target` against a data source address only affects whether Terraform reads it during that specific plan, not any real-world deletion.
- **Prefer data sources over hardcoded values for anything that legitimately changes over time or by environment/region** (AMIs, account IDs via `aws_caller_identity`, availability zones via `aws_availability_zones`) — but avoid overusing them for values that are actually static and better expressed as variables or locals ([§43](../Part6/Section-43-Part6-Local-Values-Use-Cases-and-Best-Practices.md)), since every data source read is a live API call adding to plan/apply latency.

## 7. Security Considerations

- A data source can expose sensitive information it reads (a KMS key's policy, a secret stored as a tag) into the state file exactly like a resource would — the read-only nature of a data source does not exempt its results from the general state-secrets risk ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)).
- Because data sources execute a live read on every plan, an overly broad IAM policy that only grants Terraform's execution role read access still allows that role to enumerate significant infrastructure detail — even "read-only" Terraform execution roles need scoping ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)), not just resource-modifying permissions.
- Referencing a data source pointed at infrastructure outside your control (a shared VPC, a third-party AMI) means your plan's correctness now depends on that external object's stability — a security-relevant tag or filter change made by another team can silently redirect your infrastructure (e.g., a different, unexpected AMI matching a loose filter pattern) without any change to your own configuration.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                  | Likely Cause                                                                                              | Resolution Path                                                                                                                                                                                      |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `terraform destroy` doesn't remove something you expected it to          | The object was only ever referenced via a `data` block, not a `resource` block — Terraform never owned it | Confirm intent; if it should be managed, convert to (or `import`, [§52](../Part7/Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md), into) a proper `resource` block |
| Plan shows an unrelated change every run even though config is unchanged | A data source's filter matches mutable external infrastructure whose state changed between runs           | Tighten the filter to something more stable, or accept that the data source is intentionally dynamic                                                                                                 |
| `Error: multiple ... matched; use additional constraints`                | Filter/query criteria too broad, matching more than one real object                                       | Add more specific filter criteria (exact tags, IDs) so exactly one object matches                                                                                                                    |
| Data source value shown as `(known after apply)` unexpectedly            | The data source's arguments reference a resource's attribute not yet created in this same apply           | Expected behavior for that dependency shape (§5.3) — restructure only if the value is genuinely needed at plan time                                                                                  |

## 9. Best Practices

- Use data sources to reference infrastructure your Terraform project does not and should not own — never use a `data` block as a workaround to "peek at" a resource that logically belongs in this same project's `resource` blocks.
- Prefer narrow, specific filters (exact tag values, exact names) over broad wildcard filters, to avoid `multiple matched` errors and to keep the resolved object stable and predictable across environments.
- Cache expensive or slow-changing data source lookups into a `local` value ([§43](../Part6/Section-43-Part6-Local-Values-Use-Cases-and-Best-Practices.md)) if referenced many times in a large configuration, to keep the intent clear even though Terraform already deduplicates the actual API call per unique data source instance.
- Document (via a comment or clearly descriptive local name) which team or system owns the infrastructure a cross-project data source points at — this saves significant confusion during incident response when a "why does this exist" question comes up.

## 10. Common Anti-Patterns / Mistakes

- **Using a data source to work around not having proper access/outputs from another team's project**, e.g., filtering by tag guesswork instead of requesting a proper output or shared module — this is fragile and breaks silently the moment tagging conventions drift.
- **Assuming a data source result is immutable for the life of the project.** Data sources re-read on every plan; treating their output as a fixed constant (embedding it deep in logic that assumes it never changes) leads to surprising behavior when the underlying infrastructure legitimately changes.
- **Declaring a resource where a data source was intended (or vice versa)**, most commonly copy-pasting a `resource "aws_vpc"` block intended to reference an existing VPC — this actually attempts to create a second, duplicate VPC instead of reading the existing one.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between a `resource` block and a `data` block in Terraform?"_
**Model answer:** A `resource` block tells Terraform to create, manage, and potentially destroy a piece of infrastructure — Terraform owns that object's full lifecycle. A `data` block only reads information about something that already exists (created by this project, another project, or manually) — Terraform never creates, modifies, or deletes the object a data source points at; it's purely a read operation whose result can be referenced elsewhere in configuration.
_What the interviewer is probing for:_ The most fundamental distinction in Terraform's object model — miscategorizing this leads to real mistakes like expecting `destroy` to clean up something referenced only via a data source.

**🎯 Intermediate:** _"When is a data source's value resolved — always at plan time, or can it be deferred?"_
**Model answer:** It depends on whether the data source's arguments depend on values that are already known. If all its arguments are static or already-known values, Terraform reads it during the refresh/plan phase and the resolved value appears concretely in plan output. But if a data source's arguments reference an attribute of a resource that hasn't been created yet in this same run (something shown as "known after apply"), Terraform can't read the data source until that resource actually exists, so the read is deferred to apply time — the plan shows the data source's result as unknown until then.
_What the interviewer is probing for:_ Understanding that data sources aren't magically always-resolved-at-plan-time — their evaluation timing depends on their dependency graph position, which affects what else can safely depend on them (e.g., `count`/`for_each` arguments require plan-time-known values).

**🎯 Senior:** _"A teammate is using a data source with a loose wildcard filter to find 'the latest' AMI, and complains that `terraform plan` occasionally shows an unexpected instance replacement with no config changes on their end. What's happening, and how would you fix it?"_
**Model answer:** Data sources re-evaluate on every plan by default. If the AMI data source's filter matches "any AMI starting with a given name pattern, most recent," then whenever the cloud provider (or an internal image pipeline) publishes a new matching AMI, the data source resolves to a different ID on the next plan — even though the Terraform configuration itself hasn't changed. If that AMI ID feeds into an `aws_instance` resource's `ami` argument, Terraform sees a legitimate attribute change and plans to replace the instance. The fix depends on intent: if automatic adoption of new AMIs is desired, this is arguably correct behavior and should be paired with `create_before_destroy` ([§36](./Section-36-Part5-The-lifecycle-Block-create_before_destroy-prevent_destroy-ignore_changes.md)) for safe rollout; if it's not desired, pin to a specific AMI ID (perhaps sourced from a variable updated deliberately) instead of a "most recent" data source lookup, or gate AMI updates through an explicit, reviewed process rather than an always-floating filter.
_What the interviewer is probing for:_ Real production debugging instinct — connecting "data sources re-read every run" to a concrete, observed symptom, and offering a deliberate trade-off rather than a blanket rule.

**🎯 Architect:** _"You're designing the boundary between a platform team's networking Terraform project and application teams' Terraform projects. Should application teams reference the network via data sources, or should there be a different mechanism? What are the trade-offs?"_
**Model answer:** There are three realistic options: (1) data sources with tag/name filters against the raw cloud API, (2) `terraform_remote_state` reading the network project's actual outputs, or (3) a purpose-built lookup mechanism (e.g., AWS SSM Parameter Store or a dedicated "shared values" service) that both projects write to and read from independently of Terraform state internals. Filter-based data sources are the most fragile — they depend on tagging discipline staying consistent forever and expose implementation details (VPC structure) that the network team may want to change without breaking consumers. `terraform_remote_state` is more precise (reads actual declared outputs) but tightly couples consumers to the network project's state backend location and Terraform version, and grants read access to the network team's _entire_ state file, not just the outputs meant to be shared — a real security and blast-radius concern ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)). A dedicated parameter-store-style indirection layer decouples the two projects most cleanly: the network team publishes only the specific values meant to be consumed, versioned independently of state file structure, and application teams' data sources don't need any awareness of the network project's Terraform internals at all. For most organizations past a small scale, the third option is worth the additional operational surface area specifically because it minimizes both coupling and the security exposure of full remote-state read access.
_What the interviewer is probing for:_ Systems-design thinking about organizational boundaries and blast radius, not just knowledge of the `terraform_remote_state` data source's existence.

## 12. Common Misconceptions

1. **"`terraform destroy` will clean up anything referenced by my configuration, including data sources."** False — data sources own nothing; `destroy` only affects resources this state file manages.
2. **"A data source's result is fixed once resolved, like a constant."** False — it re-reads (and can change) on every `plan`/`apply` unless the underlying infrastructure and filter criteria are both stable.
3. **"Data sources are only for looking up cloud-provider-published things like AMIs."** They're equally used for cross-project integration (`terraform_remote_state`), account/identity introspection (`aws_caller_identity`), and reading manually-created infrastructure.
4. **"A data source always resolves immediately at plan time."** Not if its arguments depend on a resource's attribute that isn't known until apply — in that case its read is deferred (§5.3).

## 13. 🔑 Key Takeaways

- `data "<TYPE>" "<NAME>" { ... }` performs a read-only lookup; Terraform never owns the lifecycle of what it reads, and `terraform destroy` never deletes it.
- Data sources re-evaluate on every plan/apply by default, meaning their resolved values can legitimately change between runs even with no configuration edits — this is a frequent source of "unexpected change" confusion if the underlying filter is too broad.
- A data source's read timing depends on its dependency graph position: static-argument data sources resolve at plan time; data sources depending on not-yet-created resource attributes are deferred to apply time.
- `terraform_remote_state` and provider-native filtered data sources are the two common mechanisms for cross-project/cross-team infrastructure integration, each with different coupling and security trade-offs.
- Confusing a resource for a data source (or vice versa) is a real, common configuration mistake with meaningfully different consequences — one creates/owns, the other only reads.

## 14. Related Concepts & What's Next

[§32](./Section-32-Part5-Resource-Blocks-Anatomy-and-Resource-Addressing.md) established the resource addressing model this section's `data.<TYPE>.<NAME>` grammar parallels. [§34](./Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) covers `count`/`for_each`, which apply to data sources exactly as they do to resources for producing multiple lookups. [§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)–[§12](../Part2/Section-12-Part2-Terraform-s-Execution-Model-Refresh-Plan-Apply-Internals.md) cover the dependency graph and refresh/plan/apply execution model that determines data source read timing in depth. [§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md) (local vs. remote state) and [§88](../Part12/Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md) (Terraform Cloud run triggers) offer alternative cross-project integration patterns beyond `terraform_remote_state`.

**Next Section:** [§34](./Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md) — `Section-34-Part5-Resource-Meta-Arguments-count-vs.-for_each.md`
