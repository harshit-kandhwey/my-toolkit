# Section 4 (Part 1): The Declarative Model: Desired State vs. Imperative Commands

## 1. Definition

**Plain language:** There are two ways to tell a computer what to do: give it a list of steps to follow ("do this, then this, then this"), or tell it what the end result should look like and let it figure out the steps itself. Kubernetes is built almost entirely around the second approach.

**Precise definition:** In the **imperative model**, an operator issues specific commands that directly cause a specific action (e.g., "create this Pod now"). In the **declarative model**, an operator submits a specification of the desired end state (e.g., "3 replicas of this Pod should exist"), and the system's controllers continuously reconcile actual state toward that declaration — reapplying it, correcting drift, and recovering from failures without further instruction. Kubernetes supports imperative commands for convenience and debugging, but its entire controller architecture (§1) is built to serve the declarative model, and production workflows are expected to use it almost exclusively.

## 2. Why the Distinction Matters

- **Declarative state is self-healing; imperative actions are not.** If an imperative `kubectl run` creates a Pod and that Pod later crashes, nothing recreates it — the imperative command already "happened" and is over. A declarative Deployment, by contrast, has a controller continuously ensuring the declared replica count exists, so a crash triggers automatic recreation.
- **Declarative state is git-diffable and auditable.** A YAML manifest committed to version control gives a clear historical record of intended state over time; a sequence of imperative commands run against a cluster leaves no equivalent trail unless separately logged.
- **GitOps (§88, Part 11) is only possible because Kubernetes' API is declarative and idempotent.** Applying the same manifest repeatedly produces no unintended side effects — a property imperative command sequences don't generally have (running "create X" twice usually errors or duplicates X).

🔑 **Key Takeaway:** Imperative commands are useful for quick exploration, debugging, and generating starter YAML — but declarative manifests, applied via `kubectl apply`, are the production standard because they're what makes self-healing, auditability, and GitOps possible at all.

## 3. Prerequisites and Dependencies

Builds on §1 (reconciliation model) and §3 (control plane makes these decisions). No new external prerequisites.

## 4. The Three Management Approaches Compared

```text
1. Imperative commands       kubectl run nginx --image=nginx
   (least recommended for    kubectl expose pod nginx --port=80
   production)                → Direct, one-time actions. No record of "why."

2. Imperative object          kubectl create -f pod.yaml
   configuration               kubectl replace -f pod.yaml
   (rarely used)               → YAML file exists, but each command maps to
                                  one specific verb; editing requires knowing
                                  exactly what changed.

3. Declarative object         kubectl apply -f pod.yaml
   configuration               → Submit desired state; Kubernetes computes
   (production standard)         the diff and reconciles automatically.
                                  Safe to re-run identically (idempotent).
```

- **Imperative commands** — Fast for learning and one-off debugging (e.g., `kubectl run`, `kubectl expose`, `kubectl scale`). Not recommended for anything meant to persist or be reproducible.
- **Imperative object configuration** — `kubectl create`/`kubectl replace` against a YAML file. Rarely used in practice; it captures state in a file but still requires the operator to track which specific command to issue for each change.
- **Declarative object configuration** — `kubectl apply -f`, the dominant production pattern. The operator declares desired end state; Kubernetes computes and applies whatever diff is needed, and the same command can be re-run safely at any time.

## 5. Hands-On: Comparing the Three Approaches Directly

### 5.1 Imperative: Creating and Modifying a Deployment by Command

**Purpose:** Illustrate how imperative commands work and where they fall short.

```bash
$ kubectl create deployment web --image=nginx:1.25
deployment.apps/web created

$ kubectl scale deployment web --replicas=3
deployment.apps/web scaled
```

**Common errors:** Running `kubectl create deployment web --image=nginx:1.25` a second time fails with `AlreadyExists` — imperative `create` is not idempotent, unlike `apply`.

### 5.2 Declarative: The Same Result via a Manifest

**Purpose:** Show the equivalent, production-standard declarative approach.

```yaml
# web-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
        - name: web
          image: nginx:1.25
```

```bash
$ kubectl apply -f web-deployment.yaml
deployment.apps/web created

$ kubectl apply -f web-deployment.yaml    # running it again is safe
deployment.apps/web unchanged
```

**Production usage example:** Because re-running `kubectl apply -f web-deployment.yaml` is safe and produces no error or duplication, this exact command is what CI/CD pipelines and GitOps controllers (§88, Part 11) run on every deploy, and it's also what an operator re-runs by hand during an incident to "re-assert" desired state without needing to know exactly what drifted.

### 5.3 `kubectl diff` — Preview Before Applying

**Purpose:** Show what a declarative `apply` would change before actually changing it.

```bash
$ kubectl diff -f web-deployment.yaml
```

**Production usage example:** Run routinely in CI pipelines before `apply`, as a safety check to catch unexpected drift or an unintended manifest change before it's live.

## 6. Production Usage Notes: Where the Line Actually Gets Drawn in Practice

- **Debugging and exploration:** imperative commands (`kubectl run`, `kubectl exec`, `kubectl scale` for a quick manual test) remain genuinely useful and are not an anti-pattern when used for temporary, throwaway investigation.
- **Anything meant to persist:** declarative manifests, committed to version control, applied via `kubectl apply` (or a GitOps controller applying them automatically) — this is the production expectation across essentially every serious Kubernetes operation covered in the remainder of this roadmap.
- **`kubectl edit` is a middle-ground trap.** It lets an operator imperatively edit live cluster state directly — convenient in an emergency, but it creates drift between the cluster's actual state and whatever is checked into version control, which GitOps and later `apply` runs will silently overwrite unless the edit is also captured back into the manifest.

## 7. Security Considerations

- Declarative manifests stored in version control create an audit trail of _intended_ state changes, which is valuable for compliance and incident forensics — imperative command histories are typically only as good as separate shell/audit logging.
- `kubectl edit`-style live imperative changes bypass any review process (pull requests, CI checks) that a GitOps-based declarative workflow would otherwise enforce — a real security/change-management gap worth closing deliberately (§88, Part 11).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                         | Likely Cause                                                                                                                  | Resolution Path                                                                    |
| ------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------- |
| A GitOps controller keeps "reverting" a manual production fix                   | Someone used `kubectl edit` or an imperative command directly against the cluster, creating drift from the Git-declared state | Make the fix in the Git-tracked manifest instead, then let the controller apply it |
| `kubectl apply` reports no changes but the operator expected an update          | The manifest change wasn't actually saved, or was applied to the wrong context/namespace                                      | Re-verify the file content and `kubectl config current-context` before re-applying |
| `kubectl create` fails with `AlreadyExists` on a supposedly idempotent redeploy | Imperative `create` was used instead of declarative `apply`                                                                   | Switch the redeploy process to `kubectl apply -f`                                  |

## 9. Best Practices

- Default to `kubectl apply -f` with version-controlled YAML for anything intended to persist beyond a debugging session.
- Reserve imperative commands for quick, throwaway exploration and for generating starter YAML (many imperative commands support `--dry-run=client -o yaml` specifically for this purpose).
- Treat any live `kubectl edit` in production as a signal that the corresponding manifest in version control needs an immediate matching update, to avoid silent drift.

## 10. Common Anti-Patterns / Mistakes

- **Managing production workloads primarily through imperative commands**, losing the self-healing, auditability, and idempotency benefits the declarative model provides.
- **Using `kubectl edit` as a routine change-management tool** rather than an emergency-only escape hatch, silently diverging cluster state from version-controlled manifests.
- **Mixing imperative `create`/`replace` and declarative `apply` inconsistently across a team**, which produces confusing, hard-to-reproduce cluster state history.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `kubectl create` and `kubectl apply`?"_
**Model answer:** `kubectl create` is imperative — it creates a resource once and fails with an error if run again against the same resource. `kubectl apply` is declarative — it submits a desired-state manifest, and Kubernetes computes whatever diff is needed; running it again with the same file is safe and simply reports no change.
_What the interviewer is probing for:_ Basic command-level awareness of imperative vs. declarative behavior.

**🎯 Intermediate:** _"Why is the declarative model considered the production standard in Kubernetes rather than imperative commands?"_
**Model answer:** Declarative manifests are idempotent (safe to reapply), version-controllable, and are what enables self-healing — a controller can continuously reconcile toward a declared state, recovering automatically from crashes or drift, whereas an imperative command is a one-time action with no ongoing enforcement. This is also the foundation GitOps tooling depends on, since it needs to be able to reapply the same manifests repeatedly and safely.
_What the interviewer is probing for:_ Understanding of _why_ declarative wins in production, not just which commands are declarative.

**🎯 Senior:** _"A production incident is resolved with a quick `kubectl edit` directly against a live Deployment. What risk does this introduce, and how would you close it?"_
**Model answer:** The live edit creates drift between the cluster's actual state and whatever is declared in version control. If a GitOps controller or the next CI-driven `kubectl apply` runs, it will silently overwrite the manual fix with the old, stale manifest, potentially reintroducing the original incident. I'd immediately backport the same fix into the tracked manifest and merge it, treating the live edit as a temporary bridge, not the actual resolution — and I'd flag it in the incident retro as a reminder that any hotfix bypassing the declarative source of truth needs an immediate follow-up commit.
_What the interviewer is probing for:_ Awareness that live imperative fixes are incomplete without closing the loop back to the declarative source of truth.

**🎯 Architect:** _"You're designing change-management policy for a platform team's Kubernetes clusters. How does the declarative model shape what you'd allow, restrict, or automate?"_
**Model answer:** I'd make declarative, version-controlled manifests the only sanctioned path for anything persistent, enforced by routing all changes through a GitOps controller (§88) rather than direct `kubectl apply`/`edit` access to production, which also gives me a natural place to insert review (pull requests), policy checks (admission control, §77, Part 10), and `kubectl diff`-style previews before anything lands. I'd still leave direct, imperative `kubectl` access available for genuine incident response, but paired with a hard requirement that any live change gets backported into the tracked manifest within a defined window, and I'd monitor for drift between live cluster state and the Git-declared state as an ongoing signal that this policy is being followed. The core architectural bet is that the declarative model's idempotency and auditability are worth the discipline required to keep imperative "escape hatches" genuinely rare.
_What the interviewer is probing for:_ Whether the candidate can turn the declarative/imperative distinction into an actual organizational policy with guardrails, not just a technical preference.

## 12. Common Misconceptions

1. **"Imperative commands are always wrong to use."** They're genuinely useful for quick debugging and generating starter YAML (`--dry-run=client -o yaml`) — the concern is using them as the primary mechanism for persistent production state.
2. **"`kubectl create -f file.yaml` and `kubectl apply -f file.yaml` are interchangeable."** `create` is a one-time imperative action against a file's contents and fails on a second run; `apply` is declarative and idempotent.
3. **"A live `kubectl edit` fix is the same as fixing the problem."** It fixes the _cluster_, temporarily — the declarative source of truth (version control) still needs the same fix, or a later `apply` will revert it.

## 13. 🔑 Key Takeaways

- Kubernetes supports imperative commands, imperative object configuration, and declarative object configuration — but declarative (`kubectl apply -f` against version-controlled YAML) is the production standard.
- Declarative state is idempotent and self-healing because controllers continuously reconcile toward it; imperative commands are one-time actions with no ongoing enforcement.
- GitOps is only possible because of Kubernetes' declarative, idempotent API design.
- Live imperative edits (`kubectl edit`) against production are a useful emergency tool but create drift that must be closed by updating the tracked manifest.
- Reserve imperative commands for debugging and exploration; treat declarative manifests as the actual source of truth for anything meant to persist.

## 14. Related Concepts & What's Next

§1 introduced the reconciliation loop this section's declarative model depends on. §32 (Part 4) revisits imperative vs. declarative specifically in the context of `kubectl` command patterns and generators. §88 (Part 11) covers GitOps tooling (ArgoCD, Flux) that automates the declarative-apply workflow described here at scale. §77 (Part 10) covers admission control, one of the guardrails a declarative change-management pipeline can enforce.

**Next Section:** §5 — `Section-05-Part1-Kubernetes-Distributions-Managed-Offerings.md`
