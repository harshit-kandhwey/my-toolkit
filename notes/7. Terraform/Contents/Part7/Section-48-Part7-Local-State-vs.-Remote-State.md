# Section 48 (Part 7): Local State vs. Remote State

## 1. Definition

**Plain language:** By default, Terraform writes state to a file sitting right next to your configuration on whatever machine ran `apply`. That works fine alone, but breaks down the moment a second person or a CI pipeline also needs to run Terraform against the same infrastructure — they'd each have their own, quickly diverging copy. Remote state moves that file to a shared location everyone and everything reads from and writes to.

**Precise definition:** **Local state** is Terraform's default backend (`local`), which stores `terraform.tfstate` as a plain file on the filesystem where the CLI runs, with no built-in mechanism for shared access, locking across machines, or encryption beyond whatever the local filesystem provides. **Remote state** is state stored via a configured `backend` block ([§49](./Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)) — object storage (S3, Azure Storage, GCS) or a service (Terraform Cloud/Enterprise) — that centralizes the state file, typically adds locking ([§50](./Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)), and in most implementations adds encryption at rest and access control independent of any single machine. The choice of backend is declared in a `terraform { backend "..." { ... } }` block and is resolved during `terraform init` ([§24](../Part4/Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md)).

> 💡 **Tip:** "Remote state" doesn't automatically mean "safe state." An S3 bucket configured as a remote backend with public read access and no encryption is arguably worse than a local file on a single trusted laptop — remote state gets you collaboration and (with the right backend) locking, but security and durability are still things you have to configure correctly, not properties you get for free just by moving off `local`.

## 2. Why This Matters

- **Collaboration correctness.** With local state, two engineers running `apply` from their own machines have no way to know about each other's changes — the second `apply` either silently overwrites the first's state or, worse, both succeed against real infrastructure but leave one engineer's local state permanently stale.
- **Locking requires a shared backend.** State locking ([§50](./Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) — preventing two concurrent `apply` runs from corrupting state — is fundamentally a property of the backend, not of Terraform itself; the `local` backend offers only filesystem-level advisory locking, which does nothing across machines.
- **CI/CD requires remote state by construction.** A pipeline that spins up a fresh runner for every job has no persistent local filesystem to keep state on between runs — remote state is not optional for any automated Terraform pipeline, it's a hard requirement.
- **Durability and recovery.** Most remote backends offer or integrate with versioning/backup (S3 bucket versioning, Terraform Cloud's state history) that a local file, especially one correctly `.gitignore`'d and therefore unversioned, does not have by default.
- **Blast radius of loss.** Losing a laptop with the only copy of local state is a full incident ([§46](./Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)); a remote backend with versioning turns the same class of accident into "restore the previous version."

## 3. Prerequisites and Dependencies

Builds on the case for why state must exist at all ([§46](./Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md)) and the specific risks of state loss and secret exposure ([§46](./Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md), [§47](./Section-47-Part7-The-State-File-Format-terraform-tfstate-Deep-Dive.md)). [§49](./Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md) picks up immediately where this section ends, detailing the actual remote backend implementations only referenced generically here. [§50](./Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md) covers locking mechanics in depth.

## 4. Architecture / Conceptual Diagram

```text
   LOCAL STATE                              REMOTE STATE

   Engineer A's laptop                      Shared Backend (S3 / Azure Storage /
   ┌───────────────────┐                      GCS / Terraform Cloud)
   │ terraform.tfstate │                      ┌──────────────────────────┐
   │  serial: 5        │                      │  terraform.tfstate       │
   └───────────────────┘                      │  serial: 9 (latest)      │
            ▲                                 │  + versioning/backups    │
            │ apply                           │  + encryption at rest    │
                                              │  + optional locking      │
   Engineer B's laptop                        └──────────────────────────┘
   ┌────────────────────┐                                  ▲       ▲
   │ terraform.tfstate  │                                  │       │
   │  serial: 5 (STALE!)│                             pull/push  pull/push
   └────────────────────┘                                  │       │
            ▲                                   Engineer A ┘       └ CI/CD pipeline
            │ apply — conflicts silently         (no local copy persists between
              with A's changes, no lock            runs — always reads/writes
              prevents this                        the shared backend)

   Neither engineer's local copy knows        Every consumer reads/writes ONE
   about the other's changes — no             authoritative copy; locking (§50)
   shared source of truth, no locking.        serializes concurrent writes.
```

- With `local`, "state" and "the copy of state on this specific machine" are the same thing — there is exactly one, and it lives wherever the CLI happens to run.
- With a remote backend, the CLI never treats its working-directory copy as authoritative; `plan`/`apply` transparently pull the latest remote state first and push the updated state back after — `terraform state pull`/`push` ([§51](./Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) expose this mechanism directly when needed manually.
- Locking (top box on the right) is what turns "many people reading and writing one shared file" into something safe — without it, remote storage alone still allows two concurrent writers to corrupt or silently overwrite each other's changes, just with a shared file instead of separate ones.

## 5. Hands-On

### 5.1 Local State: Default Behavior

**Purpose:** Confirm the default backend and see where local state actually lives.

**Syntax:**

```hcl
# no backend block at all = local backend
resource "aws_instance" "web" {
  ami           = "ami-0abcdef1234567890"
  instance_type = "t3.micro"
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing the backend...
Terraform has been successfully initialized!

$ terraform apply
...
Apply complete! Resources: 1 added, 0 changed, 0 destroyed.

$ ls -la
-rw-r--r--  1 user  staff  2481 terraform.tfstate
-rw-r--r--  1 user  staff  2481 terraform.tfstate.backup
```

**Production usage example:** Local state is appropriate only for solo, throwaway experimentation (a personal sandbox account, a one-off proof of concept) — the moment more than one person or one automated system needs to run Terraform against the same infrastructure, local state becomes a liability, not a convenience.

**Common errors:** Committing `terraform.tfstate` to git "so the team can share it" is a common but incorrect fix — it leaks secrets into permanent git history ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) and still provides no locking, so concurrent applies still corrupt each other; the correct fix is a real remote backend ([§49](./Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md)), not version control.

### 5.2 Migrating to a Remote Backend

**Purpose:** Show the minimal change required to move an existing local-state project to remote state.

**Syntax:**

```hcl
terraform {
  backend "s3" {
    bucket         = "my-org-terraform-state"
    key            = "prod/network/terraform.tfstate"
    region         = "us-east-1"
    dynamodb_table = "terraform-locks"
    encrypt        = true
  }
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing the backend...
Terraform detected that the backend type changed from "local" to "s3".

Do you want to copy existing state to the new backend?
  Enter "yes" to copy and "no" to start with an empty state.

  Enter a value: yes

Successfully configured the backend "s3"! Terraform will automatically
use this backend unless the backend configuration changes.
```

**Production usage example:** This is the standard onboarding step for any project moving from an individual's local experimentation into a team-owned, CI/CD-managed workflow — it's typically one of the very first changes made once a proof of concept graduates to something real. [§53](./Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md) covers this migration path (and reversing it) in full depth.

**Common errors:** Answering "no" to "copy existing state" when you meant to preserve existing infrastructure's tracked state results in an empty remote state — the next `plan` will propose recreating everything that local state previously tracked, even though nothing about the real infrastructure changed.

## 6. Production Usage Notes

- **There is no scenario in a real production or shared-team context where local state is the right long-term choice.** Even single-engineer production projects benefit from remote state's durability and encryption-at-rest guarantees that most local filesystems don't provide by default.
- **The backend choice is per-configuration, declared in code, and resolved at `init` time.** Changing it requires re-running `init` and confirming a state copy/migration ([§53](./Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md)) — it is not something that silently changes at `apply` time.
- **Backend configuration itself often can't contain interpolated values.** Most backend blocks require literal values (or `-backend-config` flags/files passed to `init`) rather than referencing variables, because the backend must be resolved before the rest of configuration is even parsed — a common early surprise for teams trying to template bucket names per environment.

## 7. Security Considerations

- **Local state inherits whatever protection the local filesystem has — often none.** No encryption at rest, no access logging, and full exposure if the machine is lost, stolen, or compromised; remote backends can (if configured) provide encryption at rest and access auditing that local state simply cannot.
- **Remote state centralizes risk as much as it centralizes convenience.** A misconfigured public S3 bucket used as a backend is a worse outcome than any individual's local file, since it exposes the same secrets ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) to anyone on the internet rather than anyone with access to one laptop — bucket policies, encryption, and access controls ([§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)) are not optional extras.
- **`.gitignore` is necessary but not sufficient.** Even correctly excluding `terraform.tfstate*` from version control only prevents one leak vector (git history); it does nothing about backend access control, which must be configured explicitly regardless of local or remote.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                         | Likely Cause                                                                        | Resolution Path                                                                                                                                                                                      |
| ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Two engineers' applies overwrite each other's changes                           | Project is still using local state; no shared source of truth or locking            | Migrate to a remote backend with locking ([§49](./Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md), [§50](./Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) |
| CI pipeline's `plan` always proposes creating everything from scratch           | Pipeline runner has no persistent state; project is on local state                  | Configure a remote backend so the pipeline reads/writes shared state instead of a per-run empty local file                                                                                           |
| `terraform init` prompts "copy existing state to the new backend?" unexpectedly | Migrating backend types/locations without realizing state must be explicitly copied | Answer "yes" if existing infrastructure should remain tracked; verify with `plan` afterward that no changes are proposed                                                                             |
| Backend block errors with "variables not allowed"                               | Attempting to use a variable/interpolation directly inside the `backend` block      | Use `-backend-config` flags or files passed to `terraform init` instead ([§53](./Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md))                                                   |

## 9. Best Practices

- Default every team or production project to a remote backend from the start — treat local state as acceptable only for genuinely disposable, single-person experimentation.
- Pair every remote backend with locking ([§50](./Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)); remote storage alone (without locking) still permits concurrent-write corruption.
- Enable versioning/backups on whatever storage backs your remote state, so state loss becomes "restore a previous version" rather than an `import`-based rebuild ([§46](./Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md), [§52](./Section-52-Part7-terraform-import-Bringing-Existing-Resources-Under-Management.md)).

## 10. Common Anti-Patterns / Mistakes

- **"Sharing" local state by committing it to git.** This solves neither the locking problem nor the secrets-exposure problem, and actively makes the secrets problem worse by making it permanent in git history.
- **Treating "remote" as synonymous with "secure."** A remote backend with no encryption, no access controls, and no locking configured is still a serious liability — remote state must be deliberately hardened ([§49](./Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md), [§50](./Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md), [§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)), not assumed safe by default.
- **Mixing local and remote state for the same infrastructure across team members.** If even one engineer runs Terraform locally against infrastructure everyone else manages remotely, that engineer's runs are invisible to the shared state and vice versa — this is a subtler, harder-to-detect version of the same-state-two-copies problem.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between local and remote Terraform state?"_
**Model answer:** Local state is the default — Terraform writes `terraform.tfstate` as a plain file on whatever machine ran the command, with no shared access or locking. Remote state stores that same file in a shared location (like an S3 bucket or Terraform Cloud) that every team member and every CI/CD run reads from and writes to, typically with added locking, encryption, and versioning.
_What the interviewer is probing for:_ Basic recognition that this is fundamentally a collaboration and durability distinction, not a performance one.

**🎯 Intermediate:** _"Why is local state specifically incompatible with CI/CD pipelines, beyond just being inconvenient?"_
**Model answer:** CI/CD runners are typically ephemeral — a fresh, disposable environment is provisioned for each job and destroyed afterward. If state were local to that runner, it would exist only for the duration of one job and then be lost entirely on the next run, meaning every pipeline execution would start from an empty state and try to recreate all previously-managed infrastructure. Remote state is required not as a best practice but as a structural necessity — there has to be a persistent location outside any individual runner for state to survive between pipeline executions.
_What the interviewer is probing for:_ Understanding that this isn't a stylistic preference — it's a hard technical requirement once execution environments are ephemeral.

**🎯 Senior:** _"Your team has always used local state and just committed `terraform.tfstate` to a shared git repo so 'everyone has a copy.' What's actually wrong with this, precisely?"_
**Model answer:** Several distinct problems, not one: first, secrets — state routinely contains plaintext sensitive values ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)), and committing it means those secrets are now permanently in git history even if later removed from the current commit. Second, no locking — git provides no mechanism to prevent two engineers from running `apply` concurrently against stale local copies; both writes can succeed against real infrastructure while only one gets committed, leaving the other's changes invisible to the recorded state. Third, merge conflicts — state is JSON with a `serial` counter that must be monotonically consistent; a git merge of two diverging `terraform.tfstate` files is not a valid operation and will produce a corrupted or semantically nonsensical file even if git resolves it as text without conflict markers. The fix is a real remote backend with locking, not a different way of sharing files.
_What the interviewer is probing for:_ Whether the candidate can enumerate the distinct failure modes (secrets, locking, merge semantics) rather than giving a vague "it's bad practice" answer.

**🎯 Architect:** _"You're designing the Terraform backend strategy for an organization moving from ad hoc local-state usage across dozens of teams to a standardized remote setup. What decisions do you need to make, and what are the trade-offs?"_
**Model answer:** Key decisions: (1) backend technology — cloud-native object storage with a locking mechanism (S3+DynamoDB, azurerm with native blob lease, GCS with native locking) versus Terraform Cloud/Enterprise, trading operational ownership (you manage the bucket, IAM, and locking table yourself) against a managed platform (which adds cost and vendor dependency but centralizes RBAC, run history, and policy-as-code, Part 12) — this decision often follows from whether the org already has TFC/TFE elsewhere. (2) State topology — one shared bucket per environment/account with per-project keys, versus fully isolated backends per team, trading blast radius (a compromised or misconfigured shared bucket affects everyone) against operational overhead (managing dozens of separate backends, each needing its own locking table/mechanism and access policy). (3) Access control model — who can read versus write which state paths, since read access alone exposes secrets ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) even without write access; this typically needs per-path IAM policies, not a single shared credential for the whole bucket. (4) Migration sequencing — moving dozens of teams off local state without downtime means writing a repeatable `init -migrate-state` runbook ([§53](./Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md)) each team executes themselves, plus enforced tooling (a pre-commit or CI check that fails if a `backend "local"` config, or none at all, is detected) to prevent regression once migrated.
_What the interviewer is probing for:_ Organizational-scale thinking — not just "use S3," but the access-control, blast-radius, and migration-sequencing decisions that come with rolling this out across many teams at once.

## 12. Common Misconceptions

1. **"Remote state is mainly about not losing the file."** Durability is one benefit, but the primary reasons are collaboration (one shared source of truth) and locking (preventing concurrent-write corruption) — a durable-but-unshared file still breaks teams.
2. **"Committing state to git is a valid form of 'remote' state."** It provides no locking and permanently leaks any secrets in state into git history — it solves neither of remote state's core problems.
3. **"Any remote backend is automatically encrypted and access-controlled."** These are configuration choices (bucket encryption settings, IAM policies) that must be deliberately set — a remote backend is not inherently more secure than local state unless configured to be.
4. **"Switching backends is just editing the `backend` block."** Editing the block changes only where Terraform looks going forward; migrating actual state content requires `terraform init` to detect the change and explicitly copy/migrate state ([§53](./Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md)), which is a distinct step.

## 13. 🔑 Key Takeaways

- Local state (the `local` backend) has no built-in cross-machine sharing or locking; it's suitable only for solo, disposable use.
- Remote state centralizes state in shared storage or a service, and is a structural requirement — not just a best practice — for any team or CI/CD-driven workflow.
- Remote is not synonymous with secure; encryption at rest, access control, and locking are configuration choices that must be made deliberately regardless of backend type.
- Committing `terraform.tfstate` to git is not a substitute for a real remote backend — it leaks secrets permanently and provides no locking.
- Migrating between backends is an explicit `init`-driven state copy/migration step ([§53](./Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md)), not just a config file edit.

## 14. Related Concepts & What's Next

[§49](./Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md) details the actual remote backend implementations (S3, azurerm, gcs, Terraform Cloud) only referenced generically here. [§50](./Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md) covers the locking mechanisms each backend type provides. [§53](./Section-53-Part7-State-Migration-and-Backend-Reconfiguration.md) covers the full migration procedure for moving between backends, including local-to-remote and backend-to-backend.

**Next Section:** [§49](./Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md) — `Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md`
