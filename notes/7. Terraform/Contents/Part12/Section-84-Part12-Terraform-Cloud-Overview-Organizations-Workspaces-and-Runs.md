# Section 84 (Part 12): Terraform Cloud Overview: Organizations, Workspaces, and Runs

## 1. Definition

**Plain language:** Terraform Cloud (TFC) is HashiCorp's hosted service that runs the same `plan`/`apply` workflow you already know from the CLI, but does it on shared infrastructure, with a web UI, team permissions, remote state storage, and a history of every run — instead of each engineer running Terraform from their own laptop against a state file in S3.

**Precise definition:** **Terraform Cloud** is a SaaS product (with a self-hosted equivalent, **Terraform Enterprise**, [§89](./Section-89-Part12-Terraform-Enterprise-On-Prem-Self-Hosted-Considerations.md)) that provides remote execution and remote state management for Terraform configurations, organized into a three-level hierarchy: an **organization** (a billing and access-control boundary containing multiple teams and workspaces), a **workspace** (a persistent, named unit that pairs one Terraform configuration with one state file, one set of variables, and one execution context — roughly the hosted equivalent of running `terraform apply` from one directory against one backend), and a **run** (a single execution of the plan/apply cycle inside a workspace, triggered by a VCS push, a CLI-driven remote operation, or the UI/API). Every workspace has its own state, its own variable set, and its own run history; runs execute in ephemeral, isolated containers on HashiCorp-managed (or customer-managed, for Enterprise) infrastructure rather than on a developer's machine.

> 💡 **Tip:** A TFC workspace is **not** the same concept as a CLI workspace ([§69](../Part10/Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md)), despite the shared name and HashiCorp's own reuse of the word. A CLI workspace is a named state-file suffix inside one backend configuration in one directory. A TFC workspace is a fully separate top-level object with its own state, variables, run history, permissions, and VCS binding — closer in shape to "one root module directory with a `backend` block pointed at TFC" than to a `terraform workspace new` alias. Conflating the two is one of the most common sources of confusion when teams migrate from CLI-only to TFC.

## 2. Why This Matters

- **Shared remote execution removes "works on my machine."** Every plan and apply runs in the same clean, versioned execution environment (a fixed Terraform version, a fixed set of environment variables) rather than whatever a given engineer happens to have installed locally.
- **State becomes centrally managed by default.** Every TFC workspace has remote state built in — there's no separate S3 bucket, DynamoDB table, or Azure Storage container to provision and lock down ([§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)); TFC itself is the backend, with locking handled automatically.
- **Team workflows need an audit trail.** A run history per workspace — who triggered which plan, what changed, who approved the apply — is something ad hoc CLI usage against a shared backend cannot give you without extra tooling.
- **Governance hooks attach at the workspace/run level.** Policy checks ([§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)), cost estimates ([§90](./Section-90-Part12-Cost-Estimation-Features.md)), and approval gates all plug into the run pipeline that TFC provides — none of this exists in the bare CLI workflow.
- **Organizations scale team boundaries cleanly.** Multiple teams, each with their own workspaces and permissions ([§91](./Section-91-Part12-Teams-RBAC-and-SSO-in-Terraform-Cloud-Enterprise.md)), can share one organization without stepping on each other's state or credentials.

## 3. Prerequisites and Dependencies

This section assumes the full CLI workflow ([§24](../Part4/Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md)–[§31](../Part4/Section-31-Part4-Common-CLI-Flags-Automation-Friendly-Patterns.md)), remote backends ([§49](../Part7/Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)), and state fundamentals ([§46](../Part7/Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)–[§48](../Part7/Section-48-Part7-Local-State-vs.-Remote-State.md)) are already understood — TFC is best framed as "the CLI workflow, hosted and shared," not a separate tool. [§85](./Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md) builds directly on this section by covering how workspaces bind to a VCS repository and auto-trigger runs. [§91](./Section-91-Part12-Teams-RBAC-and-SSO-in-Terraform-Cloud-Enterprise.md) covers the team/permission model only introduced here at a high level.

## 4. Architecture / Conceptual Diagram

```text
                         ORGANIZATION ("acme-corp")
                         billing + org-level settings
                                    │
        ┌───────────────────────────┼───────────────────────────┐
        ▼                           ▼                           ▼
   Team: "platform"           Team: "app-devs"            Team: "owners"
   (admin on infra-*)         (write on app-*)            (admin on all)
        │                           │
        ▼                           ▼
┌────────────────────┐      ┌────────────────────┐
│ Workspace:         │      │ Workspace:         │
│ "infra-network"    │      │ "app-api-prod"     │
│  - own state       │      │  - own state       │
│  - own variables   │      │  - own variables   │
│  - VCS: infra repo │      │  - VCS: api repo   │
│  - run history     │      │  - run history     │
└─────────┬──────────┘      └──────────┬─────────┘
          │                            │
          ▼                            ▼
   RUN (triggered by VCS push, UI, or API)
   ┌─────────────────────────────────────────┐
   │ queued → plan → (policy check) →        │
   │ cost estimate → apply (auto or manual) →│
   │ applied / errored / discarded           │
   └─────────────────────────────────────────┘
```

- One organization can contain many workspaces, each tied to a different repository, directory, or environment.
- A run always belongs to exactly one workspace and progresses through a fixed pipeline of states; [§85](./Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md) covers the VCS trigger step and [§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) covers the policy-check step in this pipeline in detail.
- Team permissions ([§91](./Section-91-Part12-Teams-RBAC-and-SSO-in-Terraform-Cloud-Enterprise.md)) are granted per-workspace, not globally — a team can have admin on one workspace and no access at all to another in the same organization.

## 5. Hands-On

### 5.1 Creating an Organization and a Workspace (UI/API Concepts, CLI-Driven Setup)

**Purpose:** Show how a workspace is declared and connected to remote execution from the CLI side, using the `cloud` block that replaces a traditional `backend` block.

**Syntax:**

```hcl
terraform {
  cloud {
    organization = "acme-corp"

    workspaces {
      name = "infra-network"
    }
  }
}
```

**Example usage and expected output:**

```bash
$ terraform login
# Opens a browser to generate an API token, stored in the CLI config (§29)

$ terraform init
Initializing Terraform Cloud...

Initializing provider plugins...
- Reusing previous version of hashicorp/aws from the dependency lock file

Terraform Cloud has been successfully initialized!
```

**Production usage example:** A platform team migrating from an S3 backend to TFC replaces the `backend "s3" { ... }` block with a `cloud` block pointing at an existing or new workspace, runs `terraform init` (which offers to migrate existing state into TFC automatically), and from then on `terraform plan`/`apply` execute remotely by default rather than locally.

**Common errors:** Running `terraform apply` locally against a `cloud`-configured workspace still queues a **remote** run by default (output streams back to the local terminal) — engineers new to TFC are sometimes surprised the plan isn't actually computed on their machine, which matters if a local-only data source or credential is required.

### 5.2 Inspecting Run State via the API

**Purpose:** Show how run status can be queried programmatically, which is the mechanism CI pipelines and run triggers ([§88](./Section-88-Part12-Terraform-Cloud-Run-Triggers-and-Workspace-Dependencies.md)) build on.

**Syntax:**

```bash
curl \
  --header "Authorization: Bearer $TFC_TOKEN" \
  --header "Content-Type: application/vnd.api+json" \
  https://app.terraform.io/api/v2/runs/run-XXXXXXXXXXXX
```

**Example usage and expected output:**

```bash
$ curl -s --header "Authorization: Bearer $TFC_TOKEN" \
    https://app.terraform.io/api/v2/runs/run-CZcmD7eagjhyX0vN | jq '.data.attributes.status'
"planned_and_finished"
```

**Production usage example:** A deployment dashboard polls this endpoint (or subscribes to notification configurations) to reflect whether the latest run in a production workspace applied cleanly, without engineers needing to open the TFC UI.

**Common errors:** Using a **user** API token where a **team** or **organization** token is more appropriate scopes runs to a specific person's identity and permissions, which breaks automation when that person leaves or their token expires — production automation should use team/organization-scoped tokens ([§91](./Section-91-Part12-Teams-RBAC-and-SSO-in-Terraform-Cloud-Enterprise.md)).

## 6. Production Usage Notes

- **Execution mode matters per workspace.** A workspace can be set to **Remote** (TFC/TFE executes plan/apply — the default and most common), **Local** (TFC only stores state and orchestrates variables, but plan/apply run on the engineer's or CI's own machine), or **Agent** (execution happens on a self-hosted agent inside a private network TFC cannot otherwise reach) — this choice affects where credentials must live.
- **Workspaces are the natural unit for state isolation, mirroring directory-based separation ([§70](../Part10/Section-70-Part10-Workspace-Based-vs.-Directory-Based-Environment-Separation.md)).** Most organizations map one workspace per environment per component (`network-prod`, `network-staging`, `app-api-prod`) rather than one giant workspace for an entire account.
- **Concurrency is per-workspace, not per-organization.** Only one run executes at a time within a given workspace (subsequent runs queue), but different workspaces run fully in parallel — a wide, well-decomposed workspace layout gets more real concurrency than one monolithic workspace.

## 7. Security Considerations

- Provider credentials configured as workspace variables (especially marked **sensitive**, mirroring [§41](../Part6/Section-41-Part6-Sensitive-Variables-and-Sensitive-Output-Values.md)) never appear in plan output or the API response body once set — but any team with write access to a workspace can still trigger runs that use those credentials, so workspace-level permissions ([§91](./Section-91-Part12-Teams-RBAC-and-SSO-in-Terraform-Cloud-Enterprise.md)) are the real credential boundary, not the variable's sensitivity flag alone.
- Remote execution means TFC's own infrastructure (or the customer's, for Enterprise, [§89](./Section-89-Part12-Terraform-Enterprise-On-Prem-Self-Hosted-Considerations.md)) holds live cloud credentials during every run — trusting TFC with production credentials is a real trust boundary decision, distinct from trusting a CI runner you control.
- API tokens (user, team, or organization-scoped) are bearer credentials with no additional MFA check per request — token scope and rotation policy matter as much as the underlying cloud credentials the workspace uses.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                | Likely Cause                                                                                                                   | Resolution Path                                                                                                                                                       |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `terraform init` fails with "Error: Invalid or missing organization"                   | The `cloud` block's `organization` doesn't match an org the authenticated token can access, or `terraform login` was never run | Verify org name spelling; re-run `terraform login` and confirm token scope                                                                                            |
| A local `terraform apply` unexpectedly streams a remote run instead of running locally | The workspace's execution mode is "Remote" (the default)                                                                       | Expected behavior for remote-execution workspaces; switch to "Local" execution mode only if local-machine access (e.g., a VPN-only data source) is genuinely required |
| Two engineers' runs on the same workspace conflict or one waits indefinitely           | Only one run executes at a time per workspace; the second is correctly queued behind the first                                 | Check the workspace's run queue in the UI; cancel or wait rather than assuming a hang                                                                                 |
| State appears "missing" after migrating from S3 to TFC                                 | `terraform init` was run without confirming the state-migration prompt, or migrated into the wrong workspace name              | Re-run `terraform init -migrate-state` deliberately, verifying the target workspace name first                                                                        |

## 9. Best Practices

- Map workspaces to the same environment/component boundaries you'd otherwise express with directories ([§71](../Part10/Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md)) — one workspace per deployable unit per environment, not one workspace per organization.
- Name workspaces with a consistent, greppable convention (`<component>-<environment>`) so the organization's workspace list stays navigable as it grows past a handful of entries.
- Use organization-level and team-level API tokens for automation, never a personal user token, so credential lifecycle isn't tied to an individual's employment.

## 10. Common Anti-Patterns / Mistakes

- **Treating a TFC workspace as interchangeable with a CLI workspace.** They solve different problems (hosted execution/state/permissions vs. a state-file suffix) and mentally merging them leads to confused migration decisions.
- **One giant workspace for an entire environment.** Just as with monolithic state files ([§47](../Part7/Section-47-Part7-The-State-File-Format-terraform-tfstate-Deep-Dive.md)), a single workspace covering dozens of unrelated resources means any change queues behind unrelated runs and a bad apply has an outsized blast radius.
- **Leaving all workspaces on default "Remote" execution without considering Agent mode for private-network resources.** Attempting to reach a private, VPN-only API endpoint from TFC's public execution environment fails in ways that are confusing until the execution-mode distinction is understood.

## 11. Interview Questions

**🎯 Beginner:** _"What is a Terraform Cloud workspace, in one sentence?"_
**Model answer:** A Terraform Cloud workspace is a persistent, named object in an organization that pairs one Terraform configuration with its own state file, variable set, and run history, and is the unit against which plan/apply runs execute remotely.
_What the interviewer is probing for:_ Basic grasp of TFC's core object model before diving into workflow details.

**🎯 Intermediate:** _"How is a Terraform Cloud workspace different from a CLI (`terraform workspace`) workspace?"_
**Model answer:** A CLI workspace is a lightweight, named suffix on a single state file within one backend configuration in one directory — switching workspaces with `terraform workspace select` just changes which state file slice is active, and all workspaces share the same variables and configuration. A TFC workspace is a fully separate top-level object: its own state, its own variable set, its own permissions, its own VCS binding, and its own run history, managed independently in the organization hierarchy. They share a name by coincidence of HashiCorp's terminology, not by underlying mechanism.
_What the interviewer is probing for:_ Whether the candidate has actually used both and can articulate the structural difference, not just repeat that "they're different."

**🎯 Senior:** _"A team wants one Terraform Cloud organization with workspaces for both a shared network layer and per-team application layers. How would you structure workspace boundaries and permissions?"_
**Model answer:** Separate the shared network/foundational layer (VPCs, subnets, shared IAM) into its own workspace(s) owned and write-accessed only by a platform team, exposing needed values (VPC ID, subnet IDs) via remote state data sources or explicit outputs consumed by downstream workspaces. Application teams get their own workspaces, scoped to their own component and environment, with write access limited to their own team and read-only or no access to the network workspace's state. This mirrors directory-based separation ([§71](../Part10/Section-71-Part10-File-Layout-Patterns-for-Multi-Environment-Projects.md)) but at the TFC object level, and keeps blast radius and permission boundaries aligned with actual ownership.
_What the interviewer is probing for:_ Ability to design a real multi-team workspace topology, not just describe the object model in isolation.

**🎯 Architect:** _"Your organization currently runs Terraform entirely from CI with an S3 backend and is considering a full migration to Terraform Cloud. What's the actual case for migrating, and what should leadership NOT expect it to solve on its own?"_
**Model answer:** The case: centralized run history and audit trail, built-in state management without separately provisioning and locking down S3/DynamoDB, native policy-as-code and cost-estimation hooks in the run pipeline ([§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md), [§90](./Section-90-Part12-Cost-Estimation-Features.md)), and a permission model ([§91](./Section-91-Part12-Teams-RBAC-and-SSO-in-Terraform-Cloud-Enterprise.md)) that doesn't require building custom IAM/CI logic to gate who can apply what. What it does not solve automatically: it doesn't fix a poorly decomposed workspace/state topology inherited from the S3 setup — a monolithic state file becomes a monolithic TFC workspace with the same blast-radius problem; it doesn't eliminate the need for least-privilege credential design ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)), since TFC still needs real cloud credentials per workspace; and it introduces a new operational dependency (TFC's own availability and API) that a self-hosted CI+S3 setup didn't have, which for regulated or air-gapped environments may instead point toward Terraform Enterprise ([§89](./Section-89-Part12-Terraform-Enterprise-On-Prem-Self-Hosted-Considerations.md)) rather than the SaaS product.
_What the interviewer is probing for:_ Balanced trade-off reasoning about a real platform migration decision, not vendor enthusiasm.

## 12. Common Misconceptions

1. **"A TFC workspace and a CLI workspace are the same feature."** They are unrelated objects that happen to share a name; conflating them causes real confusion when migrating ([§69](../Part10/Section-69-Part10-Terraform-CLI-Workspaces-Concepts-and-Commands.md)).
2. **"TFC always runs plan/apply remotely."** Only true for workspaces set to Remote execution mode; Local mode uses TFC purely for state and variable storage while execution happens elsewhere.
3. **"An organization is just a folder for workspaces."** It's also the billing boundary and the top level of the team/permission hierarchy ([§91](./Section-91-Part12-Teams-RBAC-and-SSO-in-Terraform-Cloud-Enterprise.md)) — not merely an organizational label.
4. **"Every workspace needs its own separate cloud credentials manually re-entered."** Variable sets can be shared across multiple workspaces in an organization, avoiding redundant credential configuration per workspace.

## 13. 🔑 Key Takeaways

- Terraform Cloud organizes work into organization → workspace → run, with each workspace owning its own state, variables, and run history.
- A TFC workspace is architecturally distinct from a CLI workspace despite the shared name — don't conflate state-file suffixing with a full hosted execution/state/permissions object.
- Runs progress through a fixed pipeline (queued → plan → policy check → cost estimate → apply) that later sections build governance features onto.
- Execution mode (Remote, Local, Agent) determines where credentials and network access actually need to exist.
- Workspace boundaries should mirror the environment/component boundaries you'd otherwise express with directories, not collapse into one giant workspace per organization.

## 14. Related Concepts & What's Next

[§85](./Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md) covers how workspaces bind to a VCS repository so runs trigger automatically on push/PR/merge rather than manually. [§86](./Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md) covers the policy-check stage of the run pipeline shown above. [§90](./Section-90-Part12-Cost-Estimation-Features.md) covers the cost-estimate stage. [§91](./Section-91-Part12-Teams-RBAC-and-SSO-in-Terraform-Cloud-Enterprise.md) expands the team/permission model only sketched here.

**Next Section:** [§85](./Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md) — `Section-85-Part12-VCS-Driven-Workflows-and-Remote-Runs.md`
