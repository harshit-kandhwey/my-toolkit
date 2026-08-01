# Section 28 (Part 4): Deployments: Rolling Updates, Rollbacks, and Revision History

## 1. Definition

**Plain language:** Applications don't just need to be kept running — they need to be updated, over and over, without downtime, and with a safe way back if the update turns out to be broken. A Deployment is the object that manages exactly that: it's the thing you actually write and edit as an operator, and it's responsible for turning a change in your manifest into a safe, gradual transition in the running cluster.

**Precise definition:** A **Deployment** is a controller that manages the rollout of Pods via one or more **ReplicaSets** (§27). When a Deployment's Pod template (`spec.template`) changes — a new image tag, an updated environment variable, a new resource limit — the Deployment creates a **new ReplicaSet** representing that revision, and orchestrates a transition of replica counts from the old ReplicaSet to the new one according to its configured **strategy** (§29). Kubernetes retains a bounded history of prior ReplicaSets (governed by `spec.revisionHistoryLimit`), which is what makes `kubectl rollout undo` an near-instant operation — rolling back means shifting replicas back to an already-existing, already-scheduled prior ReplicaSet rather than recreating anything from scratch.

## 2. Why This Matters

- **Deployments are what makes zero-downtime updates possible without external tooling.** Editing a bare ReplicaSet's Pod template does nothing to existing Pods (§27) — only a Deployment actually knows how to gradually transition from an old Pod template to a new one while keeping the service available throughout.
- **Revision history turns "the last deploy broke something" into a one-command fix.** `kubectl rollout undo` works because the previous ReplicaSet, complete with its exact Pod template, is still sitting there (scaled to zero) rather than deleted — a direct, practical consequence of the ReplicaSet ownership model from §27.
- **`kubectl rollout status` gives you a deterministic signal for CI/CD gating.** Because rollout progress is a first-class, queryable Deployment status field, pipelines can block on `kubectl rollout status deployment/x` and reliably know whether a deploy actually succeeded before proceeding, rather than guessing from logs.

🔑 **Key Takeaway:** A Deployment is the production-standard way to run and update stateless workloads in Kubernetes — it manages ReplicaSets (§27) on your behalf, executes an update strategy (§29) to transition between them safely, and retains revision history so that rolling back a bad release is a fast, built-in operation rather than an emergency re-deploy.

## 3. Prerequisites and Dependencies

Builds directly on §27 (ReplicaSets — the object every Deployment creates and manages) and assumes the declarative model from §4 (desired state, `kubectl apply`) as the mechanism by which Deployment changes are actually submitted.

## 4. Architecture Diagram

```text
  kubectl apply -f deployment.yaml  (image: app:v2)
              │
              ▼
  ┌─────────────────────────────────────────────────────────┐
  │                  Deployment "app"                       │
  │   spec.template changed → new revision triggered        │
  └───────────────────────┬─────────────────────────────────┘
                          │ creates
                          ▼
        ┌──────────────────────────────┐
        │  ReplicaSet "app-b7f9c" (v2) │  ◄─ new, scaling UP
        └──────────────────────────────┘
                          │
        ┌──────────────────────────────┐
        │  ReplicaSet "app-5d2a1" (v1) │  ◄─ old, scaling DOWN
        └──────────────────────────────┘
                          │
                strategy governs the pace
                of this transition (§29)
                          │
                          ▼
              steady state: v2 RS at full replicas,
              v1 RS retained at 0 replicas
              (kept for kubectl rollout undo)
```

- **Only one ReplicaSet is ever "active" (nonzero replicas) at steady state** — the transition diagram above shows the brief overlap during an in-progress rollout, not a permanent state.
- **`spec.revisionHistoryLimit` bounds how many old, zero-replica ReplicaSets are retained** (default 10) — beyond that limit, the oldest are garbage-collected, which directly caps how far back `kubectl rollout undo --to-revision=N` can reach.
- **The Deployment's own `status` fields** (`replicas`, `updatedReplicas`, `availableReplicas`, `unavailableReplicas`) are what `kubectl rollout status` polls to determine whether a rollout has actually completed successfully.

## 5. Hands-On: Deployment Lifecycle Commands

### 5.1 Creating a Deployment and Triggering an Update

**Purpose:** Show the full authoring and update cycle for the object that manages nearly all stateless workloads in production.

```yaml
# app-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
spec:
  replicas: 4
  revisionHistoryLimit: 5
  selector:
    matchLabels:
      app: app
  template:
    metadata:
      labels:
        app: app
    spec:
      containers:
        - name: app
          image: myregistry/app:v1
          ports:
            - containerPort: 8080
```

```bash
$ kubectl apply -f app-deployment.yaml
deployment.apps/app created

$ kubectl set image deployment/app app=myregistry/app:v2 --record
deployment.apps/app image updated

$ kubectl rollout status deployment/app
Waiting for deployment "app" rollout to finish: 2 out of 4 new replicas have been updated...
Waiting for deployment "app" rollout to finish: 3 out of 4 new replicas have been updated...
deployment "app" successfully rolled out
```

**Production usage example:** `kubectl set image` is a common quick imperative path for a single-field image bump, but the production-standard path is editing `spec.template.spec.containers[].image` in the version-controlled manifest and applying it via CI (§4) — `kubectl set image` is genuinely useful for fast manual hotfixes and exam scenarios.

**Common errors:** `--record` is deprecated as of newer `kubectl` versions and produces a warning; `kubectl rollout history` still functions using the `CHANGE-CAUSE` annotation only if it was set, so many teams now set `kubectl.kubernetes.io/change-cause` manually via an annotation in the manifest instead.

### 5.2 Inspecting Revision History and Rolling Back

**Purpose:** Recover from a bad rollout using the retained ReplicaSet history from §27.

```bash
$ kubectl rollout history deployment/app
deployment.apps/app
REVISION  CHANGE-CAUSE
1         <none>
2         kubectl set image deployment/app app=myregistry/app:v2

$ kubectl rollout history deployment/app --revision=2
deployment.apps/app with revision #2
Pod Template:
  Labels:  app=app
  Containers:
   app:
    Image:  myregistry/app:v2
    Port:   8080/TCP

$ kubectl rollout undo deployment/app
deployment.apps/app rolled back

$ kubectl rollout undo deployment/app --to-revision=1
deployment.apps/app rolled back
```

**Production usage example:** When a canary or early rollout metrics dashboard shows an elevated error rate right after a deploy, `kubectl rollout undo` is the fastest safe response — it shifts traffic back to the prior, already-known-good ReplicaSet in seconds, buying time to investigate the new image without extending the incident.

**Common errors:** `kubectl rollout undo --to-revision=N` fails if revision `N` has already been garbage-collected past `spec.revisionHistoryLimit` — a real reason to keep that limit generous enough for the team's actual mean-time-to-detect on bad releases.

### 5.3 Pausing, Resuming, and Scaling During a Rollout

**Purpose:** Control an in-progress rollout directly — useful for canary-style manual verification before letting a rollout fully complete.

```bash
$ kubectl rollout pause deployment/app
deployment.apps/app paused

# make further template edits; they won't roll out yet
$ kubectl set resources deployment/app -c app --limits=cpu=500m,memory=256Mi

$ kubectl rollout resume deployment/app
deployment.apps/app resumed

$ kubectl scale deployment/app --replicas=6
deployment.apps/app scaled
```

**Production usage example:** Pausing a rollout after only a fraction of Pods have updated (combined with manual monitoring, or scripted checks against error-rate dashboards) is a manual approximation of canary deployment (§29) achievable with nothing beyond built-in `kubectl` commands, though dedicated tooling (Argo Rollouts, Flagger — §88, Part 11) automates this far more robustly.

## 6. Production Usage Notes

- **`maxUnavailable` and `maxSurge` under `spec.strategy.rollingUpdate` directly control rollout pace and risk** — a lower `maxUnavailable` favors availability during the rollout at the cost of slower progression; a higher `maxSurge` speeds up the rollout at the cost of a brief spike in total resource consumption (full mechanics in §29).
- **Readiness probes (§92, Part 12) are what actually gate rollout progress.** The Deployment controller only considers a new Pod "available" — and therefore proceeds to the next batch — once that Pod's readiness probe passes; a missing or overly lenient readiness probe can let a broken rollout appear to succeed.
- **`kubectl.kubernetes.io/change-cause` as a manifest annotation is the durable way to record why a revision happened**, since it survives independent of whichever `kubectl` flags were used at deploy time and shows up cleanly in `kubectl rollout history`.

## 7. Security Considerations

- Rollback via `kubectl rollout undo` reintroduces the exact prior Pod template — including any prior image tag — so if a rollback target's image has since been found to contain a vulnerability, `undo` alone is not a safe fix; a forward roll to a patched image is required instead.
- Because a Deployment's rollout history retains prior Pod templates (including any environment variables or non-Secret configuration baked into them), reviewing `kubectl rollout history --revision=N` output can inadvertently surface old configuration values — a reason to keep genuinely sensitive values in Secrets (§42, Part 6) rather than plain environment values in the template.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Likely Cause                                                                                      | Resolution Path                                                                         |
| ----------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| `kubectl rollout status` hangs, never reports success                   | New Pods are failing their readiness probe, so the Deployment never considers them available      | `kubectl describe pod` on a new-revision Pod; check probe config and application health |
| `kubectl rollout undo` fails with an error about the target revision    | The requested revision has already been garbage-collected past `revisionHistoryLimit`             | Only revisions still retained can be targeted; consider raising the limit going forward |
| A rollout appears stuck with old and new Pods both present indefinitely | `maxUnavailable`/`maxSurge` combined with failing readiness probes on new Pods stalls progression | Fix the underlying new-Pod health issue; the strategy itself is working as designed     |

## 9. Best Practices

- Always set a meaningful `kubectl.kubernetes.io/change-cause` annotation (or equivalent CI-injected metadata) on every Deployment revision, so `kubectl rollout history` remains a useful audit trail rather than a list of unlabeled revisions.
- Gate CI/CD pipelines on `kubectl rollout status deployment/<name> --timeout=<duration>`, treating a timeout as a failed deploy that should trigger automatic rollback rather than leaving the rollout in an ambiguous half-updated state.
- Set `revisionHistoryLimit` deliberately based on how far back the team realistically needs rollback capability, rather than leaving the default unexamined.

## 10. Common Anti-Patterns / Mistakes

- **Treating `kubectl rollout undo` as a substitute for actually fixing the underlying bug** — rollback buys time; it doesn't resolve whatever caused the bad release, which still needs a proper forward fix.
- **Deploying without readiness probes configured**, which removes the Deployment controller's actual signal for rollout health and lets a broken rollout appear to "succeed" by replica count alone.
- **Relying on `kubectl set image` as the primary production deploy mechanism** rather than version-controlled manifests applied through CI — imperative image bumps leave no reviewable diff and are easy to lose track of.

## 11. Interview Questions

**🎯 Beginner:** _"What happens when you change the image in a Deployment's manifest and re-apply it?"_
**Model answer:** The Deployment detects that its Pod template changed, creates a new ReplicaSet reflecting the new image, and gradually shifts replicas from the old ReplicaSet to the new one according to its configured strategy — by default, RollingUpdate — until the new ReplicaSet holds all the replicas and the old one is scaled to zero (but retained for potential rollback).
_What the interviewer is probing for:_ Basic understanding of what triggers a rollout and the ReplicaSet-swap mechanism underneath it.

**🎯 Intermediate:** _"How does `kubectl rollout undo` actually work under the hood — what makes it fast?"_
**Model answer:** Kubernetes retains old ReplicaSets (up to `spec.revisionHistoryLimit`) scaled down to zero replicas rather than deleting them after a rollout completes. `kubectl rollout undo` doesn't recreate anything from scratch — it simply reverses the replica-count shift, scaling the previous revision's already-existing ReplicaSet back up and the current one down, which is why it completes about as fast as a forward rollout would, not instantly but with no need to rebuild or reschedule from zero.
_What the interviewer is probing for:_ Understanding that rollback reuses existing ReplicaSet objects rather than being a special, separate mechanism.

**🎯 Senior:** _"A rollout to a new image version appears to hang — `kubectl rollout status` never reports success. How do you diagnose and resolve it?"_
**Model answer:** First I'd check `kubectl get pods` for the Deployment's label selector to see whether new-revision Pods exist and what state they're in, then `kubectl describe pod` on one of them to check its readiness probe status specifically — a hanging rollout status almost always means new Pods aren't passing readiness, so the Deployment controller never considers them available and won't progress further per its `maxUnavailable`/`maxSurge` settings. Depending on findings, the fix is either correcting an application bug the new image introduced, fixing a misconfigured probe, or — if it's clearly a bad release — running `kubectl rollout undo` immediately to restore service while the root cause is investigated separately, rather than leaving production in a half-migrated state.
_What the interviewer is probing for:_ A structured diagnostic sequence connecting rollout mechanics to readiness probes, plus the judgment to decide between "keep debugging" and "roll back now."

**🎯 Architect:** _"How would you design a deployment pipeline's rollout-safety gates using nothing but native Deployment features (no external progressive-delivery tooling)?"_
**Model answer:** I'd have CI apply the manifest, then immediately run `kubectl rollout status deployment/<name> --timeout=<N>` as a blocking pipeline step — a nonzero exit (timeout or explicit failure) triggers an automatic `kubectl rollout undo` rather than leaving the deploy in an ambiguous state, and I'd back this with meaningful readiness probes (§92, Part 12) as the actual health signal the rollout depends on. I'd tune `maxUnavailable`/`maxSurge` per service based on its actual availability requirements and cost tolerance for surge capacity, and set `revisionHistoryLimit` generously enough to cover realistic mean-time-to-detect windows for the team. I'd be explicit with stakeholders, though, that this native approach gives coarse, replica-percentage-based rollout control — no traffic-percentage-based canary analysis or automated metric-driven promotion — and that genuinely progressive delivery (§29) requires layering Argo Rollouts or Flagger (§88, Part 11) on top of this same Deployment/ReplicaSet foundation.
_What the interviewer is probing for:_ Whether the candidate can build real safety into a pipeline using only built-in primitives, while correctly identifying the ceiling of what native Deployments alone can provide.

## 12. Common Misconceptions

1. **"A Deployment update immediately replaces all Pods at once."** By default it uses the RollingUpdate strategy (§29), replacing Pods incrementally according to `maxUnavailable`/`maxSurge`, not all at once.
2. **"`kubectl rollout undo` recreates the previous version from the manifest history in Git."** It has no awareness of Git at all — it operates purely on the retained ReplicaSet objects still present in the cluster; if that ReplicaSet has been garbage-collected, undo to that revision is no longer possible regardless of what Git holds.
3. **"Rollout status success means the new version is actually healthy in a business-logic sense."** It only means the configured number of new Pods passed their readiness probes — a probe that only checks "process is listening" won't catch a functional regression a broader observability stack (Part 12) would.
4. **"Scaling a Deployment and updating its image are the same kind of operation."** Scaling changes replica count without creating a new revision; only a Pod template change (image, env, resources, etc.) triggers a new ReplicaSet and rollout.

## 13. 🔑 Key Takeaways

- Deployments manage rollout of Pod template changes by creating a new ReplicaSet per revision and shifting replicas between old and new according to a strategy (§29).
- Revision history (retained, zero-replica ReplicaSets) is what makes `kubectl rollout undo` fast and reliable — rollback reuses existing objects rather than recreating anything.
- `kubectl rollout status`, `history`, `undo`, `pause`, and `resume` are the core operational toolkit for managing rollouts day to day.
- Readiness probes are the actual mechanism gating rollout progress — a rollout can only be as reliable as the health signal it depends on.
- `revisionHistoryLimit` bounds how far back rollback can reach; set it deliberately rather than leaving the default unexamined.

## 14. Related Concepts & What's Next

§27 established the ReplicaSet mechanics this section built directly on top of. §29 covers exactly how the transition between old and new ReplicaSets is paced and shaped — the built-in `RollingUpdate`/`Recreate` strategies, and how Blue/Green and Canary patterns extend beyond what a bare Deployment can do natively.

**Next Section:** §29 — `Section-29-Part4-Deployment-Strategies-RollingUpdate-Recreate-BlueGreen-Canary.md`
