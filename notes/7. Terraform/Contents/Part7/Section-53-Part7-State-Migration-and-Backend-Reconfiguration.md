# Section 53 (Part 7): State Migration and Backend Reconfiguration

## 1. Definition

**Plain language:** Sometimes the place state lives needs to change — moving from local to remote, from one S3 bucket to another, from S3 to Terraform Cloud, or splitting one big state file into several smaller ones. Terraform has a specific, guided procedure for this so the move happens safely, without losing track of what's already deployed.

**Precise definition:** **State migration** is the process of moving an existing state file's content from one backend configuration to another — including local-to-remote, remote-to-remote (different backend type or same type with different parameters), and single-state-to-multiple-state splits — while preserving the recorded mapping to real infrastructure. Terraform's primary supported entry point is editing the `backend` block and re-running `terraform init`, which detects the backend configuration change and interactively (or, with `-migrate-state`/`-reconfigure` flags for scripted use, non-interactively) offers to copy existing state into the new location. Splitting one state into several typically combines this with `terraform state mv` ([§51](./Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)) targeting a distinct destination state file for the resources being separated out.

> 💡 **Tip:** `terraform init` distinguishes between two very different situations that look similar: `-migrate-state` copies existing state content into the new backend (the normal case when you actually want to preserve what's tracked), while `-reconfigure` changes the backend pointer without copying anything, starting the new backend empty (correct only when you deliberately want a fresh start, not when preserving existing tracked infrastructure). Picking the wrong one is one of the most consequential mistakes possible in this workflow — always confirm which behavior you actually want before running either flag non-interactively.

## 2. Why This Matters

- **Migration is the practical mechanism behind everything [§48](./Section-48-Part7-Local-State-vs.-Remote-State.md) and [§49](./Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md) argued for.** Moving from local to remote state, or from a self-managed backend to Terraform Cloud, isn't just a config edit — it requires this specific, careful procedure to actually happen safely.
- **Getting migration wrong risks the exact state-loss scenario [§46](./Section-46-Part7-What-Terraform-State-Is-and-Why-It-Exists.md) treats as a serious incident.** A migration that starts the new backend empty when the intent was to preserve existing tracking effectively reproduces "lost state" even though nothing was technically deleted.
- **State splitting (breaking one large state file into several) is a common maturity step** as a project grows, directly addressing the giant-state-file anti-pattern (referenced in Part 15) — and it depends on the migration mechanics covered here combined with `state mv` ([§51](./Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md)).
- **Migrations often happen exactly when an organization is also changing cloud providers, restructuring teams, or adopting Terraform Cloud** — situations where getting this specific step wrong has outsized consequences because it's often irreversible in practice (the old backend's copy may be decommissioned shortly after).
- **CI/CD pipelines need to handle backend changes deliberately**, since `-migrate-state`/`-reconfigure` behave very differently when run non-interactively in an automated context than when a human is present to answer prompts.

## 3. Prerequisites and Dependencies

Builds directly on [§48](./Section-48-Part7-Local-State-vs.-Remote-State.md) and [§49](./Section-49-Part7-Remote-Backends-Overview-S3-Azure-Storage-GCS-TFC.md) (why and where state might move) and [§51](./Section-51-Part7-State-Commands-list-show-mv-rm-pull-push.md) (`state mv`, `pull`, `push`, the lower-level primitives migration builds on for splits). Assumes `terraform init`'s general role from [§24](../Part4/Section-24-Part4-terraform-init-Backend-Init-Provider-Install-Module-Install.md).

## 4. Architecture / Conceptual Diagram

```text
              MIGRATION PATH DECISION TREE

  Backend block in .tf changed
            │
            ▼
    terraform init
            │
            ▼
  Terraform detects backend       ┌─────────────────────────────┐
  configuration has changed       │  Do you want to migrate     │
            │                     │  existing state to the new  │
            ▼                     │  backend?                   │
  ┌───────────────────┐           │    yes → COPY state content │
  │  Answer / flag:   │──────────►│    no  → start EMPTY        │
  │                   │           └─────────────────────────────┘
  └───────────────────┘

  -migrate-state  ──► Copies existing state content into new backend.
                       Use when: preserving tracking of existing
                       infrastructure (the common case).

  -reconfigure    ──► Points at new backend WITHOUT copying content.
                       Use when: deliberately starting fresh (new
                       project, or intentionally abandoning old
                       tracking — rare, high-risk if done by mistake).

              STATE SPLITTING (one state → two states)

  Original state (single backend/key)
  ┌───────────────────────────────────────┐
  │ aws_vpc.main   aws_subnet.public      │
  │ aws_instance.web   aws_rds_instance.db│
  └───────────────────────────────────────┘
                    │
     terraform state mv -state-out=<new_state_file_or_target>
                    │
                    ▼
  Networking state              Database state
  ┌─────────────────────┐       ┌─────────────────────┐
  │ aws_vpc.main        │       │ aws_rds_instance.db │
  │ aws_subnet.public   │       │                     │
  └─────────────────────┘       └─────────────────────┘

  Cross-references between the split states (e.g., db needs the
  subnet ID) must be re-wired as data sources / remote state reads
  (Part 8, Part 10) — `state mv` moves the state entry, not the
  config-level dependency.
```

- The decision tree's branch point — "copy or start empty" — is the single highest-stakes moment in any migration; every other step is comparatively low-risk because it's either read-only inspection or additive.
- State splitting is really two operations combined: the state-level move (`state mv`) shown here, plus a configuration-level rewire of any cross-references between the split pieces, which the diagram deliberately calls out because it's easy to overlook.

## 5. Hands-On

### 5.1 Migrating Local State to a Remote Backend

**Purpose:** Show the standard, most common migration: local to S3.

**Syntax:**

```hcl
terraform {
  backend "s3" {
    bucket = "my-org-terraform-state"
    key    = "prod/network/terraform.tfstate"
    region = "us-east-1"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform init
Initializing the backend...
Terraform detected that the backend type changed from "local" to "s3".

Do you want to copy existing state to the new backend?
  Pre-existing state was found while migrating the previous "local" backend to the
  newly configured "s3" backend. No existing state was found in the newly
  configured "s3" backend. Do you want to copy this state to the new "s3"
  backend? Enter "yes" to copy and "no" to start with an empty state.

  Enter a value: yes

Successfully configured the backend "s3"!
```

**Production usage example:** This is the exact sequence used when a project graduates from an individual's local experimentation into shared, remote-backed team ownership ([§48](./Section-48-Part7-Local-State-vs.-Remote-State.md)) — it is typically a one-time step performed early in a project's life.

**Common errors:** Answering "no" here when existing infrastructure is genuinely tracked in the local state discards that tracking — the new remote backend starts empty, and the next `plan` proposes recreating everything the local state previously knew about.

### 5.2 Non-Interactive Migration in CI/CD

**Purpose:** Perform the same migration in an automated pipeline context, where no human is present to answer the interactive prompt.

**Syntax:**

```bash
terraform init -migrate-state -input=false
```

**Example usage and expected output:**

```bash
$ terraform init -migrate-state -input=false
Initializing the backend...
Terraform detected that the backend type changed from "s3" to "s3".

Successfully configured the backend "s3"!
```

**Production usage example:** Pipelines that manage backend configuration changes as code (e.g., moving from one state bucket to a newly standardized one during an org-wide restructure) must use `-migrate-state -input=false` explicitly rather than relying on the interactive prompt, which would hang indefinitely in a non-interactive CI context without it.

**Common errors:** Using `-reconfigure` instead of `-migrate-state` in a pipeline intended to preserve tracking silently starts the new backend empty with no interactive confirmation step to catch the mistake — because CI runs unattended, this error can go unnoticed until the next `plan` proposes recreating the entire environment.

## 6. Production Usage Notes

- **Always back up the source state before any migration**, via `terraform state pull > backup.tfstate` or the backend's own versioning/snapshot mechanism, regardless of how routine the migration seems — this is the recovery path if anything goes wrong.
- **Verify with `terraform plan` immediately after any migration.** A clean "no changes" result confirms the new backend's state genuinely matches what was there before; any unexpected diff should be investigated before any further `apply`.
- **State splits should be planned around clear logical/ownership boundaries** (networking versus application, per-environment) established from the workspace/directory strategy in Part 10, not performed ad hoc as a reactive fix once a state file has already become unmanageably large.

## 7. Security Considerations

- **A migration is a window where two copies of state (with all its potential secrets, [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) exist simultaneously** — the old backend's copy and the new one — until the old one is deliberately cleaned up; both copies need to be protected and eventually the old one properly decommissioned, not left as an orphaned, forgotten, still-accessible secret store.
- **Backend migrations often change the credential/access model** (e.g., moving from a personal AWS credential used for local state to a shared CI role for remote state) — this is a natural moment to also review and tighten who can read/write state going forward ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md), [§98](../Part13/Section-98-Part13-Secure-Backend-Configuration-Encryption-Access-Controls.md)), not just to move the bytes.
- **Non-interactive migration flags used in pipelines should themselves be protected by the same review gates as any other infrastructure change** — a backend reconfiguration is a high-impact operation and shouldn't bypass whatever approval process governs other state-affecting changes.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                              | Likely Cause                                                                                                                                                               | Resolution Path                                                                                                                                                           |
| ------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Post-migration `plan` proposes recreating everything                                 | `-reconfigure` (or "no" to the copy prompt) was used when preserving state was intended                                                                                    | Restore from a pre-migration backup (`state pull` output, or old backend's version history) and redo the migration correctly with `-migrate-state`/"yes"                  |
| `init` hangs indefinitely in a CI pipeline during a backend change                   | Backend configuration changed but the interactive prompt has no human to answer it, and neither `-migrate-state`/`-reconfigure` nor `-input=false` was set                 | Explicitly pass `-migrate-state -input=false` (or `-reconfigure` if genuinely intended) in the pipeline                                                                   |
| After splitting state, `plan` fails on a cross-reference between the split resources | A resource in one split state still references an attribute of a resource that moved to the other, via a direct in-config reference no longer valid across separate states | Rewire the cross-reference as a data source or remote state read (Part 8, Part 10) instead of a direct resource reference                                                 |
| Lineage mismatch error during migration                                              | Attempting to migrate into a backend location that already holds an unrelated, different state history                                                                     | Confirm the destination is genuinely empty or intentionally being overwritten before proceeding; do not force past a lineage mismatch without understanding why it exists |

## 9. Best Practices

- Always back up state (`state pull`, or rely on backend versioning) before initiating any migration, regardless of how low-risk it seems.
- Understand the precise difference between `-migrate-state` and `-reconfigure` and confirm which one matches intent before running either, especially in scripted/non-interactive contexts.
- Run `terraform plan` immediately after any migration and treat anything other than "no changes" as a signal to stop and investigate before proceeding further.

## 10. Common Anti-Patterns / Mistakes

- **Running backend migrations without a backup "because it's just a config change."** Migration touches the entire state file at once; treating it as low-risk because the trigger was "just" a config edit ignores the actual blast radius of getting it wrong.
- **Using `-reconfigure` reflexively to make an interactive prompt go away in scripts**, without checking whether `-migrate-state` was actually the intended behavior — this is the single most common way teams accidentally end up with an empty new-backend state and duplicate infrastructure on the next apply.
- **Splitting state without rewiring cross-references first**, leaving `plan` broken across both halves until someone works out, under time pressure, which references need to become data sources or remote state lookups instead.

## 11. Interview Questions

**🎯 Beginner:** _"What command do you run to migrate Terraform state to a new backend, and what triggers it?"_
**Model answer:** You edit the `backend` block in configuration to point at the new backend, then run `terraform init`. Terraform detects that the backend configuration has changed from what state currently reflects and prompts (interactively, or via the `-migrate-state`/`-reconfigure` flags in a scripted context) whether to copy the existing state content into the new backend location.
_What the interviewer is probing for:_ Basic familiarity with the trigger (backend block change + re-init) rather than assuming a separate dedicated "migrate" command exists.

**🎯 Intermediate:** _"What's the difference between `terraform init -migrate-state` and `terraform init -reconfigure`, and why does the distinction matter?"_
**Model answer:** `-migrate-state` copies the existing state's content into the newly configured backend, preserving the tracked mapping to real infrastructure — this is what you want any time the goal is "same infrastructure, different place state lives." `-reconfigure` instead just points Terraform at the new backend location without copying anything, so the new backend starts with empty state — appropriate only when you deliberately want a fresh start, not when existing infrastructure needs to remain tracked. The distinction matters because picking `-reconfigure` by mistake when you actually needed `-migrate-state` silently discards the mapping to everything currently deployed, and the next `plan` will propose recreating it all — a serious, avoidable incident if the flags are confused, especially in a non-interactive pipeline where no prompt catches the mistake.
_What the interviewer is probing for:_ Precise knowledge of these two flags' different behavior, since confusing them is one of the most consequential real-world Terraform mistakes.

**🎯 Senior:** _"Your team wants to split one large state file — currently containing networking, a database, and an application layer — into three separate state files with independent ownership. Walk through the actual steps, including the parts people commonly forget."_
**Model answer:** First, back up the existing combined state entirely (`state pull` to a file, or confirm backend version history covers this point) before touching anything. Second, decide the target structure — three separate backend locations (buckets/keys or workspaces), each with its own configuration directory. Third, for each resource being moved, use `terraform state mv` with a target state output pointing at the new backend/location to relocate its state entry — done resource by resource or via address patterns, with zero API calls against real infrastructure. What people commonly forget: any resource in one new state that references an attribute of a resource now living in a different state (the application layer referencing the database's endpoint, or the database referencing the networking layer's subnet ID) breaks, because a direct Terraform resource reference only works within a single state/configuration — those references need to become either data source lookups (querying the real resource by tag/name at plan time) or remote state reads (`terraform_remote_state`, explicitly reading the other project's state outputs, Part 8/Part 10) as part of the same change, not as an afterthought once `plan` starts failing. Finally, run `plan` against all three new configurations and confirm each shows no unexpected changes before considering the split complete, and only then decommission the original combined state/backend location.
_What the interviewer is probing for:_ Whether the candidate knows state splitting is a config-level rewire as much as a state-level move, and specifically anticipates the cross-reference problem rather than treating it as a pure `state mv` exercise.

**🎯 Architect:** _"An organization is consolidating from six separately-managed AWS backend buckets (one per acquired subsidiary, inconsistent naming and locking setups) into one standardized backend structure across the whole company. Design the migration approach and the risks you'd flag to leadership before starting."_
**Model answer:** Approach: treat this as a per-subsidiary sequenced rollout, not a single big-bang cutover — each subsidiary's projects get migrated independently using `terraform init -migrate-state` against the new standardized backend/key convention, verified with `plan` showing no changes before that subsidiary's old bucket is decommissioned, so a problem discovered in subsidiary two doesn't block or endanger subsidiaries three through six which haven't started yet. Before migrating each subsidiary, first standardize and verify their locking configuration in the new shared structure ([§50](./Section-50-Part7-State-Locking-Mechanisms-DynamoDB-Blob-Lease.md)) — since the described inconsistency likely means some of the six had incomplete or missing locking, and folding them into a shared bucket without confirming locking first risks a concurrent-write incident during the very projects most likely to still have active local/manual workflows around them. Sequencing should prioritize by risk tolerance: pick a low-stakes subsidiary or non-production environment first to validate the runbook itself before touching anything production-critical. Risks to flag to leadership: this is calendar-time-intensive per subsidiary given the mandatory backup-verify-decommission cycle for each, and rushing it to hit an arbitrary consolidation deadline is exactly how the `-migrate-state` versus `-reconfigure` mistake (silently discarding tracked infrastructure) happens at scale; access-control review needs to happen for each subsidiary as part of the move, not be assumed to carry over automatically, since a consolidated bucket structure changes who can technically read/write which subsidiary's state and that needs explicit IAM/RBAC decisions, not inherited defaults; and until a subsidiary's old bucket is actually decommissioned post-verification, it remains a live, potentially-forgotten copy of sensitive state that needs to stay in the security review scope, not be treated as already handled the moment the new bucket looks correct.
_What the interviewer is probing for:_ Organizational-scale migration thinking — sequenced rollout over big-bang, locking/access-control review as part of (not separate from) the migration, and honest calendar-time and rushed-deadline risk framing rather than presenting this as a mechanically simple bulk operation.

## 12. Common Misconceptions

1. **"Editing the `backend` block automatically moves the state."** It only changes where Terraform will look going forward; the actual content move requires `terraform init` to detect the change and explicitly copy it (`-migrate-state` or an interactive "yes").
2. **"`-reconfigure` and `-migrate-state` do roughly the same thing."** They're opposites in effect — one copies existing state content, the other starts the new backend empty — and confusing them is a common, serious mistake.
3. **"State splitting is just running `state mv` a few times."** It also requires rewiring any cross-references between the split pieces into data sources or remote state reads, which is easy to overlook until `plan` starts failing.
4. **"Once migration completes, the old backend's copy can be safely ignored."** It should be deliberately decommissioned, not merely ignored — an orphaned old copy remains a live, potentially-forgotten exposure of whatever secrets that state held.

## 13. 🔑 Key Takeaways

- State migration is triggered by changing the `backend` block and re-running `terraform init`, which detects the change and offers to copy existing state (`-migrate-state`) or start fresh (`-reconfigure`) — these two behaviors are opposites and must not be confused.
- Always back up state before migrating and verify with a clean `terraform plan` immediately after — anything other than "no changes" warrants investigation before proceeding.
- Splitting one state file into several combines `terraform state mv` for the state-side move with a configuration-side rewire of any cross-references into data sources or remote state reads.
- Non-interactive/CI migrations must explicitly pass the correct flag (`-migrate-state` or `-reconfigure`) plus `-input=false`, since no human is present to catch a wrong choice via the interactive prompt.
- Old backend locations should be deliberately decommissioned after a verified migration, not left as an orphaned, still-sensitive copy of state.

## 14. Related Concepts & What's Next

[§54](./Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) covers the last major piece of state management in this Part: what happens when real infrastructure changes outside Terraform after state was already established, whether via migration, import, or normal `apply`.

**Next Section:** [§54](./Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md) — `Section-54-Part7-Handling-State-Drift-and-terraform-refresh.md`
