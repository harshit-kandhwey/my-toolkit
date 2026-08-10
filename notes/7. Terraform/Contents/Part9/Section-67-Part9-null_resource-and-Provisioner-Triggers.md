# Section 67 (Part 9): null_resource and Provisioner Triggers

## 1. Definition

**Plain language:** `null_resource` (and its newer replacement, `terraform_data`) is a resource that does nothing on its own — it doesn't create a server, a database, or anything real. Its entire purpose is to be a place to attach a provisioner that isn't naturally tied to any specific infrastructure resource, and to control, via a `triggers` map, exactly when Terraform should re-run that provisioner.

**Precise definition:** **`null_resource`** is a resource type provided by the `hashicorp/null` provider that has no real-world side effects of its own — creating, updating, or destroying it makes no external API calls — and exists purely as an attachment point for provisioners ([§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md)) and a `triggers` argument. **`triggers`** is a map of arbitrary key-value pairs; Terraform stores this map in state at creation, and on every subsequent `plan`, compares the _current_ computed value of that map against what's stored — if any value differs, the `null_resource` is destroyed and recreated (forcing its creation-time provisioner to re-run), even though the resource itself represents nothing real. **`terraform_data`** is the newer, built-in-provider equivalent (no separate provider install required) introduced to serve the same role, with an `input`/`output` pair in addition to `triggers_replace`, and is the form HashiCorp now recommends over `null_resource` for new configuration.

> 💡 **Tip:** The core insight is that provisioners never re-run just because you re-`apply` with no changes — they run once, at a lifecycle event. `triggers` is the mechanism that manufactures a lifecycle event (a forced destroy-and-recreate of the null resource) on demand, whenever some value you care about changes. Without `triggers`, a `null_resource`'s provisioner would only ever run once, on the very first `apply` that creates it, identical to a provisioner on any other resource type.

## 2. Why This Matters

- [§38](../Part5/Section-38-Part5-Local-Only-Resources-null_resource-terraform_data-random-time.md) already introduced `null_resource`/`terraform_data` as a category of "local-only" resource; this section is the direct, practical follow-up specifically for the pattern of pairing one with a provisioner and `triggers` — arguably the single most common reason either resource type appears in real configuration at all.
- This is the standard pattern for running a provisioner that logically belongs to a _group_ of resources rather than any one of them — for example, re-running a database migration script whenever any file in a `migrations/` directory changes, which isn't naturally the responsibility of any single `aws_db_instance` or `aws_instance`.
- Getting `triggers` wrong (too broad, too narrow, or referencing a value that changes on every apply for unrelated reasons) is a common source of either "why does this provisioner never re-run when it should" or "why does this provisioner re-run on every single apply" bug reports.

## 3. Prerequisites and Dependencies

This section assumes the provisioner mechanics of [§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md), the failure/tainting behavior of [§66](./Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md) (since triggering a `null_resource` recreation follows the identical destroy-and-recreate mechanics as a tainted resource), and the introduction to `null_resource`/`terraform_data` as resource types in [§38](../Part5/Section-38-Part5-Local-Only-Resources-null_resource-terraform_data-random-time.md). Familiarity with the `filesha1`/`filemd5`/`sha256` family of functions ([§20](../Part3/Section-20-Part3-Built-In-Functions-Numeric-String-Collection-Type-Conversion.md)) is useful, since they're the most common way to compute a `triggers` value from file contents.

## 4. Architecture / Conceptual Diagram

```text
   resource "null_resource" "migrate" {
     triggers = {
       migrations_hash = sha1(join("", [for f in fileset(".", "migrations/*.sql") : filesha1(f)]))
     }

     provisioner "local-exec" {
       command = "psql -f run_migrations.sh"
     }
   }

   ─────────────────────────────────────────────────────────────

   terraform plan / apply
        │
        ▼
   Compute current triggers map value
        │
        ▼
   Compare to triggers value stored in state
        │
   ┌────┴──────┐
   │           │
  SAME        DIFFERENT
   │           │
   ▼           ▼
 No change  null_resource.migrate is
 planned    destroyed + recreated
 for this      │
 resource      ▼
            creation-time provisioner
            (local-exec) RUNS AGAIN
```

- The `triggers` map is opaque to Terraform — it doesn't interpret what the values _mean_, it only compares them byte-for-byte between state and the current computed value. Any change to any key's value is sufficient to force recreation.
- This is the same "destroy and recreate" mechanism a tainted resource goes through ([§66](./Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md)) — a changed `triggers` map is just a second way a resource ends up on that same path, this time intentionally rather than as a failure response.

## 5. Hands-On

### 5.1 null_resource with a Trigger Tied to File Content

**Purpose:** Re-run a provisioner only when the content of specific files actually changes — the canonical `triggers` use case.

**Syntax:**

```hcl
resource "null_resource" "run_migrations" {
  triggers = {
    migrations_hash = sha1(join("", [for f in fileset("${path.module}/migrations", "*.sql") : filesha1(f)]))
  }

  provisioner "local-exec" {
    command = "./scripts/run-migrations.sh"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
null_resource.run_migrations: Creating...
null_resource.run_migrations: Provisioning with 'local-exec'...
null_resource.run_migrations (local-exec): Executing: ["/bin/sh" "-c" "./scripts/run-migrations.sh"]
null_resource.run_migrations: Creation complete after 2s [id=8f3b1e2a]

$ terraform apply -auto-approve       # no migration files changed
null_resource.run_migrations: Refreshing state... [id=8f3b1e2a]

No changes. Your infrastructure matches the configuration.

# ... a migration file is edited ...

$ terraform apply -auto-approve
null_resource.run_migrations: Destroying... [id=8f3b1e2a]
null_resource.run_migrations: Destruction complete after 0s
null_resource.run_migrations: Creating...
null_resource.run_migrations (local-exec): Executing: ["/bin/sh" "-c" "./scripts/run-migrations.sh"]
null_resource.run_migrations: Creation complete after 2s [id=a1c9d4e7]
```

**Production usage example:** This exact pattern is the standard way to trigger a one-off script (a database migration, a cache-warming call, a static-asset upload) whenever relevant source files change, without tying that action to any specific infrastructure resource's own lifecycle.

**Common errors:** Using `timestamp()` as a trigger value (`triggers = { t = timestamp() }`) forces recreation on _every single apply_, since `timestamp()` evaluates fresh each run — this is a frequent, easy-to-make mistake for anyone wanting "run once per apply."

### 5.2 terraform_data as the Modern Equivalent

**Purpose:** Show the newer, provider-free replacement recommended for new configuration.

**Syntax:**

```hcl
resource "terraform_data" "run_migrations" {
  triggers_replace = [
    sha1(join("", [for f in fileset("${path.module}/migrations", "*.sql") : filesha1(f)]))
  ]

  provisioner "local-exec" {
    command = "./scripts/run-migrations.sh"
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply -auto-approve
terraform_data.run_migrations: Creating...
terraform_data.run_migrations: Provisioning with 'local-exec'...
terraform_data.run_migrations (local-exec): Executing: ["/bin/sh" "-c" "./scripts/run-migrations.sh"]
terraform_data.run_migrations: Creation complete after 2s [id=8f3b1e2a-...]
```

**Production usage example:** `terraform_data` is preferred in new configuration specifically because it ships as part of Terraform core (no separate `hashicorp/null` provider to declare and install via [§9](../Part2/Section-09-Part2-Provider-Configuration-and-Version-Constraints.md)'s version-constraint mechanics), simplifying dependency management for a purely internal helper resource.

**Common errors:** `terraform_data` uses `triggers_replace` (a list or map, forcing full replacement on change) rather than `null_resource`'s `triggers` — the two are not drop-in syntax replacements for each other despite serving the same role.

## 6. Production Usage Notes

- `triggers` values should be as narrowly scoped as possible to what actually needs the provisioner to re-run — a trigger computed from an entire directory's contents when only one subset of files matters causes unnecessary re-runs (and, for `local-exec` scripts with real side effects, unnecessary repeated side effects).
- Because a `null_resource`/`terraform_data` recreation follows the exact same destroy-then-create sequence as any tainted resource, a _destroy-time_ provisioner attached to the same resource also fires on that recreation — useful for pairing "tear down the old thing" logic with "set up the new thing" logic across a single trigger change.
- `depends_on` is commonly needed on a `null_resource` whose provisioner depends on other resources being fully created first, since a resource with no real attributes referencing another resource creates no implicit dependency edge in the graph ([§35](../Part5/Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md)) the way a normal attribute reference would.

## 7. Security Considerations

- A `null_resource`'s `local-exec` provisioner runs with the same OS-level permissions as the Terraform process itself — the security considerations from [§63](./Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md) and [§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md) (command injection via interpolated values, credentials appearing in logs) apply identically here, and are easy to overlook because `null_resource` "feels" less consequential than a real cloud resource.
- Because `triggers` values are stored in Terraform state, any sensitive value used as a trigger (a secret hash, for instance) is persisted in state just like any other resource attribute — the same state-security concerns from [§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md) apply.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Likely Cause                                                                                                                 | Resolution Path                                                                                                                                                                            |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Provisioner re-runs on every single `apply`, even with no relevant changes | A `triggers` value derived from something that changes every run (`timestamp()`, an unstable ordering in a `for` expression) | Replace with a stable, content-derived value (a hash of specific file contents, an explicit version string)                                                                                |
| Provisioner never re-runs despite an expected change                       | `triggers` map doesn't actually reference the value that changed, or references a value that Terraform considers unchanged   | Verify the trigger expression's actual computed value differs before and after the change (`terraform console`, [§28](../Part4/Section-28-Part4-terraform-console-and-terraform-graph.md)) |
| `null_resource` provisioner runs before a dependent resource is ready      | No dependency edge exists between the `null_resource` and the resource it logically depends on                               | Add explicit `depends_on` ([§35](../Part5/Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md)) since attribute-less resources create no implicit graph edge        |
| Migrating from `null_resource` to `terraform_data` breaks the config       | `triggers` (map) and `triggers_replace` (list/map with different semantics) are not directly interchangeable syntax          | Rewrite the trigger expression to `terraform_data`'s argument shape rather than a mechanical find-replace                                                                                  |

## 9. Best Practices

- Prefer `terraform_data` over `null_resource` for new configuration, per current HashiCorp guidance, to avoid an extra provider dependency for a purely internal helper resource.
- Derive `triggers` from content hashes of the specific files/values that actually matter, not broad proxies (a whole directory's mtime, a random ID) that either over- or under-trigger.
- Add a comment next to any `triggers`-driven `null_resource`/`terraform_data` explaining _why_ the provisioner needs to be re-run on that specific condition — this pattern is inherently less self-documenting than a normal resource attribute change.

## 10. Common Anti-Patterns / Mistakes

- **Using `null_resource` as a general-purpose script runner for logic that has nothing to do with infrastructure state** — effectively turning Terraform into a cron-like task runner, which is a symptom of reaching for the tool at hand rather than a purpose-built job scheduler or CI step.
- **Trigger values that are too broad**, causing expensive or disruptive provisioner re-runs far more often than actually needed (e.g., hashing an entire large directory when only one file's content is relevant).
- **Forgetting `depends_on`** on a `null_resource` whose provisioner implicitly assumes another resource already exists and is ready, since the lack of attribute references means Terraform has no way to infer that ordering automatically.

## 11. Interview Questions

**🎯 Beginner:** _"What does `null_resource` actually do?"_
**Model answer:** Nothing on its own — it has no real-world side effects. Its only purpose is to serve as a place to attach a provisioner and a `triggers` map, so a script can be run on demand without being tied to a specific real infrastructure resource.
_What the interviewer is probing for:_ Correct understanding that it's a deliberately inert resource, not a misunderstanding that it somehow represents "nothing" in a confusing or broken way.

**🎯 Intermediate:** _"How does `triggers` control when a `null_resource`'s provisioner re-runs?"_
**Model answer:** Terraform stores the `triggers` map's computed values in state at creation. On every subsequent plan, it recomputes the current value of that map and compares it to what's stored — if any value differs, the `null_resource` is destroyed and recreated, which causes its creation-time provisioner to run again. If nothing in the map changes, the resource (and its provisioner) is left alone.
_What the interviewer is probing for:_ Mechanistic understanding — the resource is destroyed and recreated, not "the provisioner runs again in place."

**🎯 Senior:** _"A `null_resource` provisioner meant to run a database migration runs on every single `apply`, even when no migration files changed. What's the likely cause and fix?"_
**Model answer:** Most likely the `triggers` expression includes something that changes on every evaluation regardless of actual migration content — `timestamp()` is the classic culprit, but an unstable ordering from a `for` expression over a `fileset()` result (if file enumeration order isn't guaranteed stable) can produce the same symptom. The fix is to derive the trigger from a stable, content-based value — hashing each migration file's content with `filesha1()` and combining them deterministically (sorted, joined) — so the trigger value is identical between runs unless the actual file content changed.
_What the interviewer is probing for:_ Debugging skill connecting a vague symptom to the specific mechanism (unstable trigger expression) causing it.

**🎯 Architect:** _"A team is using dozens of `null_resource` blocks with `local-exec` provisioners to orchestrate what is essentially a deployment pipeline inside Terraform — build steps, migration steps, cache invalidation, notification steps, all chained via triggers and `depends_on`. How do you evaluate this design?"_
**Model answer:** This is a sign Terraform is being used as a general-purpose task orchestrator, which it isn't designed for — it has no retry semantics, no partial-failure recovery beyond taint-and-recreate, no parallelism control beyond the resource graph's default concurrency, and debugging a chain of `null_resource` dependencies is materially harder than reading a dedicated CI/CD pipeline definition ([§102](../Part14/Section-102-Part14-CI-CD-Pipeline-Integration-GitHub-Actions-GitLab-Jenkins.md)) or Ansible playbook, both of which are purpose-built for ordered, multi-step orchestration with proper logging and failure handling. I'd recommend separating concerns: Terraform provisions infrastructure; a dedicated pipeline (GitHub Actions/GitLab CI stage, or an Ansible run, [§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md)) handles the build/migrate/invalidate/notify sequence as its own well-supported workflow, invoked _after_ `terraform apply` completes rather than embedded inside it via chained `null_resource` provisioners.
_What the interviewer is probing for:_ Recognition that this pattern, while technically achievable, is architecturally the wrong tool for the job, and the ability to propose the correct division of responsibility.

## 12. Common Misconceptions

1. **"`null_resource` provisions something, just something minimal."** It provisions nothing at all — no API calls happen for the resource itself; it exists purely in Terraform state as an attachment point.
2. **"Changing `triggers` re-runs the provisioner in place."** It doesn't run "in place" — the entire `null_resource`/`terraform_data` is destroyed and recreated, which happens to have the side effect of re-running its creation-time provisioner.
3. **"`null_resource` and `terraform_data` are interchangeable via find-and-replace."** They aren't — `triggers` (map) and `triggers_replace` (list/map with different comparison semantics) require rewriting the trigger expression, not just renaming the resource type.
4. **"A `null_resource` automatically depends on other resources its provisioner script references by name."** Terraform's dependency graph is built from _HCL attribute references_, not from what a shell script happens to touch — referencing another resource's ID inside a `local-exec` command string doesn't create a graph dependency unless that reference appears as an actual Terraform expression (or `depends_on` is set explicitly).

## 13. 🔑 Key Takeaways

- `null_resource` (and its recommended successor `terraform_data`) has no real-world side effects — it exists solely as an attachment point for provisioners and a `triggers`/`triggers_replace` mechanism.
- `triggers` stores a map's values in state at creation; any difference between the stored and currently computed values forces the resource to be destroyed and recreated, re-running its creation-time provisioner.
- A stable, content-derived trigger value (file content hashes) is essential — unstable values like `timestamp()` cause the provisioner to re-run on every single apply.
- `terraform_data` is the current recommended form for new configuration, avoiding a separate provider dependency for a purely internal helper resource.
- Dependency ordering for a `null_resource`'s provisioner often needs an explicit `depends_on`, since the resource typically has no attribute references that would create an implicit graph edge.

## 14. Related Concepts & What's Next

[§38](../Part5/Section-38-Part5-Local-Only-Resources-null_resource-terraform_data-random-time.md) introduced `null_resource`/`terraform_data` as a category of local-only resource; this section completed the picture with the trigger-driven provisioner pattern that's their most common real use. [§64](./Section-64-Part9-local-exec-and-remote-exec-Provisioners.md) and [§66](./Section-66-Part9-Provisioner-Failure-Behavior-on_failure.md) cover the provisioner mechanics and failure/tainting behavior this section's recreation cycle relies on. [§35](../Part5/Section-35-Part5-Resource-Dependencies-Implicit-vs.-Explicit-depends_on.md) covers the explicit `depends_on` mechanism referenced above. [§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) closes Part 9 by examining whether a `null_resource`-driven script is even the right tool compared to boot-time provisioning or a dedicated pipeline stage.

**Next Section:** [§68](./Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) — `Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md`
