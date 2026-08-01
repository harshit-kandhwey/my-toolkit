# Section 32 (Part 4): YAML Manifest Authoring and the kubectl apply Workflow

## 1. Definition

**Plain language:** Every concept covered so far in Part 4 — Pods, multi-container patterns, init containers, ReplicaSets, Deployments, deployment strategies, labels/selectors, and `kubectl`'s generator commands — exists to produce one artifact: a YAML manifest that gets applied to a cluster and kept in sync over time. This section is where those pieces come together into the actual, repeatable, real-world workflow a platform engineer follows to write, validate, and ship a manifest.

**Precise definition:** **YAML manifest authoring** is the practice of writing a Kubernetes object's desired state as structured YAML, typically starting from a `kubectl create --dry-run=client -o yaml` skeleton (§31) and hand-extending it with fields generators don't populate (resource limits, probes, volumes, security context). The **`kubectl apply` workflow** is the resulting operational loop: author or edit the manifest, validate it (`kubectl apply --dry-run=server`, §31), preview the exact change (`kubectl diff`, §31), commit it to version control, and apply it — with Kubernetes' **three-way merge** (comparing the last-applied-configuration annotation, the submitted manifest, and live cluster state) computing precisely which fields to change, add, or remove.

## 2. Why This Matters

- **This is the synthesis point of everything in Part 4.** A production manifest is a Pod spec (§24) wrapped in a Deployment (§27, §28) using a chosen strategy (§29), carrying label metadata (§30) a selector depends on, most efficiently drafted via a generator (§31) — this section is where an engineer must hold all of it in mind simultaneously to write one coherent file.
- **`kubectl apply`'s three-way merge is what makes collaborative, partial edits safe.** Unlike `kubectl replace` (which wholesale overwrites an object with exactly what's submitted, silently dropping any field a controller or another team added out-of-band), `apply` merges intelligently — this distinction is a frequent source of production incidents when misunderstood.
- **This entire workflow is exactly what GitOps automates.** §88 (Part 11) covers ArgoCD and Flux, which are, at their core, controllers that continuously run this same author-diff-apply loop against a Git repository automatically — understanding the manual workflow here is a direct prerequisite for understanding what GitOps is actually removing from the human loop.

🔑 **Key Takeaway:** Writing and shipping a Kubernetes manifest in production is a five-step loop — author (often generator-assisted), validate, diff, commit, apply — and `kubectl apply`'s three-way merge (not a blind overwrite) is what makes that loop safe to repeat indefinitely, which is precisely the property GitOps tooling later automates end-to-end.

## 3. Prerequisites and Dependencies

Synthesizes §24 (Pod spec anatomy) through §31 (kubectl generators, dry-run, diff) — this section assumes familiarity with every object type and command pattern introduced earlier in Part 4.

## 4. Architecture Diagram

```text
  1. AUTHOR                2. VALIDATE              3. DIFF                 4. COMMIT              5. APPLY
  ──────────                ───────────              ───────                ─────────               ───────
  kubectl create             kubectl apply            kubectl diff            git add/commit/         kubectl apply -f
  --dry-run=client            -f file.yaml              -f file.yaml           push (PR review)         file.yaml
  -o yaml > file.yaml         --dry-run=server
       │                          │                       │                       │                       │
       ▼                          ▼                       ▼                       ▼                       ▼
  Hand-edit: resources,      Confirms admission        Shows exact field-      Reviewed change,       API server computes
  probes, volumes,           chain (§77) and           level delta vs live      audit trail (§4)        3-way merge:
  securityContext (§43)      quotas would allow it     cluster state                                    last-applied-config
                                                                                                          ⊕ submitted manifest
                                                                                                          ⊕ live state
                                                                                                          = final object

  ┌─────────────────────────────── kubectl apply's three-way merge ──────────────────────────────────┐
  │  last-applied-configuration   submitted manifest        live cluster state    →   result         │
  │  (annotation, prior apply)     (this apply)                                                      │
  │  replicas: 3                  replicas: 5                replicas: 3 (HPA-scaled to 7!)  →  5    │
  │  A field removed from the submitted manifest but present in last-applied → REMOVED from live     │
  │  A field changed out-of-band by another controller (not in last-applied) → LEFT ALONE            │
  └──────────────────────────────────────────────────────────────────────────────────────────────────┘
```

- **`kubectl replace -f`, by contrast, has no three-way merge at all** — it's a full overwrite of the live object with exactly the submitted file's contents, which silently discards anything the API server or another controller (e.g., an HPA adjusting `replicas`) added since the last apply.
- **The `last-applied-configuration` annotation is how `apply` "remembers" what it applied last time**, distinguishing "a field was deliberately removed from the manifest" (should be deleted live) from "a field was never part of what apply manages" (should be left alone, e.g., a mutating webhook's injected sidecar).

## 5. Hands-On: The Full Author-to-Apply Workflow

### 5.1 Authoring a Complete Production-Ready Manifest

**Purpose:** Show a realistic manifest that goes beyond generator output — the actual hand-editing step every real deployment requires.

**Syntax:** Start from a generator (§31), then extend by hand.

```yaml
# payments-deployment.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: payments
  labels:
    app.kubernetes.io/name: payments
    app.kubernetes.io/version: "2.3.0"
    env: prod
spec:
  replicas: 3
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxSurge: 1
      maxUnavailable: 0
  selector:
    matchLabels:
      app.kubernetes.io/name: payments
  template:
    metadata:
      labels:
        app.kubernetes.io/name: payments
        app.kubernetes.io/version: "2.3.0"
    spec:
      containers:
        - name: payments
          image: payments:2.3.0
          ports:
            - containerPort: 8080
          resources:
            requests: { cpu: "250m", memory: "256Mi" }
            limits: { cpu: "500m", memory: "512Mi" }
          readinessProbe:
            httpGet: { path: /healthz, port: 8080 }
            initialDelaySeconds: 5
          securityContext:
            runAsNonRoot: true
            allowPrivilegeEscalation: false
```

**Production usage example:** The generator (§31) produces only the skeleton — `metadata`, `spec.selector`, `spec.template.spec.containers[].image`. Every field beyond that (resource requests/limits, probes, rolling-update tuning, securityContext) is domain knowledge from earlier sections (§25 probes concept, §29 strategies, §43 SecurityContext) hand-added by whoever owns the workload — this is the actual authoring work, not a mechanical step.

### 5.2 Validate, Diff, Commit, Apply — The Full Loop

**Purpose:** Run the complete safety sequence before anything reaches the live cluster.

```bash
# 1. Validate against the full admission chain without persisting
$ kubectl apply -f payments-deployment.yaml --dry-run=server
deployment.apps/payments configured (server dry run)

# 2. Preview the exact change
$ kubectl diff -f payments-deployment.yaml
diff -u -N /tmp/LIVE-.../apps.v1.Deployment.default.payments /tmp/MERGED-.../apps.v1.Deployment.default.payments
--- /tmp/LIVE-.../apps.v1.Deployment.default.payments
+++ /tmp/MERGED-.../apps.v1.Deployment.default.payments
@@ -20,7 +20,7 @@
       containers:
         - name: payments
-          image: payments:2.2.0
+          image: payments:2.3.0

# 3. Commit (in a real workflow, this happens BEFORE step 5 via a PR)
$ git add payments-deployment.yaml
$ git commit -m "Bump payments to 2.3.0"

# 4. Apply
$ kubectl apply -f payments-deployment.yaml
deployment.apps/payments configured
```

**Production usage example:** In a mature setup, steps 1–2 run automatically as CI checks on every pull request touching `payments-deployment.yaml`, with the `kubectl diff` output posted as a PR comment for human review — step 4 (`apply`) is often not run by a human at all, but by a GitOps controller (§88) reacting to the merge.

**Common errors:** Running `kubectl apply` on a manifest that was never previously applied via `apply` (e.g., an object originally created with `kubectl create`) can produce a `metadata.annotations: kubectl.kubernetes.io/last-applied-configuration must have configuration annotation` warning on first use — harmless, but confirms the object wasn't apply-managed until now.

### 5.3 `apply` vs `replace` — Seeing the Three-Way Merge Consequence Directly

**Purpose:** Demonstrate concretely why `replace` is dangerous when another actor (e.g., an HPA) has modified the live object out-of-band.

```bash
# An HPA has scaled payments to 7 replicas based on load; the manifest still says 3
$ kubectl get deployment payments -o jsonpath='{.spec.replicas}'
7

$ kubectl apply -f payments-deployment.yaml     # manifest says replicas: 3
deployment.apps/payments configured
$ kubectl get deployment payments -o jsonpath='{.spec.replicas}'
3   # apply's merge respects the explicit field in the submitted manifest

$ kubectl replace -f payments-deployment.yaml   # for contrast — also forces to 3,
                                                  # but would ALSO have wholesale
                                                  # discarded any other out-of-band
                                                  # field the manifest doesn't mention
```

**Production usage example:** This exact scenario — a manifest's static `replicas` fighting an HPA's dynamic scaling — is why teams either omit `replicas` from Deployments managed by an HPA entirely (letting the HPA own that field exclusively) or use `kubectl apply --server-side` with field-ownership tracking (Server-Side Apply) to formally divide ownership of specific fields between the manifest and the controller.

## 6. Production Usage Notes

- **The order matters: validate and diff _before_ committing to version control is backwards in a healthy pipeline** — the real order is author → commit to a branch → PR-triggered CI runs `--dry-run=server` and `diff` as required checks → merge → apply (often automatic via GitOps, §88). Running validation only after merging removes the chance to catch problems before they're the team's committed source of truth.
- **Server-Side Apply (`kubectl apply --server-side`)** is a newer alternative to classic client-side apply that moves the three-way merge computation to the API server itself and tracks field ownership explicitly per-manager, resolving the exact HPA-vs-manifest `replicas` conflict shown above (see Hands-On section 5.3) more robustly than classic apply's annotation-based merge.
- **A manifest with fields you didn't set intentionally left blank (defaults)** still gets recorded in `last-applied-configuration`, meaning a later removal of that field from the manifest is correctly detected as "should be deleted" — this is why deliberately blank/default fields should still be reviewed with the same care as explicit ones.

## 7. Security Considerations

- SecurityContext fields (`runAsNonRoot`, `allowPrivilegeEscalation: false`) belong in the manifest at authoring time, not bolted on later — retrofitting security hardening onto hundreds of already-running manifests is a real, expensive migration (§43, §113 Part 15).
- The commit-then-apply workflow's audit trail (§4) is itself a security control — it's how an incident responder answers "who changed this and when" after the fact, something a bare `kubectl apply` run outside of any pipeline doesn't provide on its own.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                  | Likely Cause                                                                                                                | Resolution Path                                                                                                                       |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| A field removed from the manifest doesn't disappear from the live object | The object was never `apply`-managed (no `last-applied-configuration` annotation) or was last touched with `replace`/`edit` | Confirm via `kubectl get -o yaml` whether the annotation exists; if missing, the first `apply` establishes the baseline going forward |
| `kubectl apply` keeps reverting an HPA's scaled replica count            | The manifest's static `replicas` field fights the HPA's dynamic scaling on every apply                                      | Omit `replicas` from the Deployment manifest when an HPA manages it, or adopt Server-Side Apply field ownership (§65, Part 9)         |
| CI's `kubectl diff` step shows an unexpected, unreviewed field change    | Someone used `kubectl edit` or a manual imperative command against the cluster out-of-band (§4)                             | Reconcile the live drift back into the tracked manifest before merging the new change                                                 |

## 9. Best Practices

- Always author manifests starting from a `--dry-run=client -o yaml` generator skeleton (§31), then hand-extend with resource limits, probes, and securityContext rather than writing boilerplate from scratch.
- Run `--dry-run=server` and `kubectl diff` as required CI checks on every pull request touching a manifest, before merge — not as an optional manual step run only sometimes.
- Omit fields from a manifest that another controller (HPA, VPA) is meant to own exclusively, or adopt Server-Side Apply, to avoid a static manifest value fighting a dynamic one on every apply.

## 10. Common Anti-Patterns / Mistakes

- **Using `kubectl replace` interchangeably with `kubectl apply`**, unaware that `replace` performs a full overwrite with no three-way merge, silently discarding any out-of-band field another actor set.
- **Skipping `kubectl diff` in CI because "the change is small and obviously fine"** — the entire value of the check is catching the _unexpected_ small change, which by definition doesn't look obviously fine to the author beforehand.
- **Leaving a Deployment's `replicas` field under manifest control while an HPA also manages it**, causing every `apply` to silently undo the HPA's most recent scaling decision.

## 11. Interview Questions

**🎯 Beginner:** _"Walk me through the basic steps of writing and shipping a Kubernetes manifest."_
**Model answer:** Start by generating a skeleton with `kubectl create <object> --dry-run=client -o yaml`, then hand-edit it to add fields the generator doesn't populate — resource requests/limits, probes, security context. Validate it with `kubectl apply --dry-run=server` to catch admission or quota issues without persisting anything, preview the exact change with `kubectl diff`, commit the file to version control, and finally run `kubectl apply -f` to ship it.
_What the interviewer is probing for:_ Whether the candidate knows the actual sequence, not just that "you write YAML and apply it."

**🎯 Intermediate:** _"What's the practical difference between `kubectl apply` and `kubectl replace`, and why does it matter?"_
**Model answer:** `kubectl apply` performs a three-way merge between the last-applied-configuration annotation, the submitted manifest, and live cluster state — it only changes fields that actually differ and, critically, leaves alone any field the manifest doesn't mention that wasn't previously apply-managed. `kubectl replace` performs a full overwrite with exactly the submitted file's contents, with no merge logic at all — any field set out-of-band by another controller (an HPA's replica count, a mutating webhook's injected values) gets silently discarded. This matters because in a real cluster, multiple actors modify objects concurrently, and only `apply`'s merge behavior is safe under that condition.
_What the interviewer is probing for:_ Concrete understanding of the merge mechanics, not just "apply is declarative, replace is imperative."

**🎯 Senior:** _"A Deployment managed by an HPA keeps getting scaled back down every time your CI pipeline runs `kubectl apply`. Diagnose and fix this."_
**Model answer:** The manifest almost certainly still specifies a static `spec.replicas` value, and the HPA is scaling that same field dynamically based on load — every `apply` re-asserts the manifest's static value, undoing whatever the HPA had set, and then the HPA re-scales it back up on its next reconciliation pass, producing a visible flap. The fix is to remove `replicas` from the manifest entirely once an HPA is managing it, letting the HPA own that field exclusively going forward — `apply`'s merge logic will then leave the live replica count alone since the manifest no longer expresses an opinion on it. For a more robust long-term fix across many such shared fields, I'd migrate to Server-Side Apply, which tracks field ownership explicitly per manager rather than relying on the classic annotation-based merge.
_What the interviewer is probing for:_ Ability to trace an operational symptom back to the underlying merge mechanics and propose the correct structural fix, not just a workaround.

**🎯 Architect:** _"You're designing the manifest-authoring and deployment workflow for a platform serving 50+ teams. What does the end-to-end pipeline look like, and what failure modes are you designing against?"_
**Model answer:** The pipeline is: teams author manifests (generator-assisted per §31) in team-owned repos, submit via pull request, CI runs `kubectl apply --dry-run=server` and `kubectl diff` as required checks with the diff posted to the PR for human review, and on merge a GitOps controller (§88) — not a human running `kubectl apply` directly — reconciles the change into the cluster, giving every change a Git commit as its audit trail (§4). I'm designing against several failure modes: teams bypassing the pipeline with direct `kubectl apply`/`edit` access, which I'd close by removing standing write RBAC (§74) to production namespaces entirely, routing all writes through the GitOps controller's own credentials; static manifest fields fighting dynamic controllers (HPA/VPA replica counts), which I'd resolve by mandating Server-Side Apply field ownership or explicit field omission conventions; and `kubectl replace` usage creeping in and silently discarding out-of-band state, which I'd catch via a linter (kube-linter, §116) flagging `replace` in any script or runbook. The core design principle is that the manual workflow described in this section should be something teams rarely run by hand in production at all — it should be what CI and the GitOps controller execute on their behalf, with humans reviewing diffs rather than typing apply commands.
_What the interviewer is probing for:_ Whether the candidate can scale a manual, single-engineer workflow into an enforced, multi-team platform pipeline, correctly anticipating the concurrency and access-control failure modes that only appear at scale.

## 12. Common Misconceptions

1. **"`kubectl apply` and `kubectl replace` produce the same result if the manifest is correct."** They differ specifically when live state has been changed out-of-band since the last apply — `replace` discards that out-of-band state, `apply`'s merge does not.
2. **"Generators produce a deployment-ready manifest."** They produce a minimal skeleton; production fields (resources, probes, securityContext) are near-universally added by hand afterward.
3. **"`kubectl diff` in CI is optional polish."** It's the one concrete pre-merge opportunity to catch an unintended change before it's live — skipping it removes the actual safety value of the whole pipeline.
4. **"A Deployment's `replicas` field should always be explicitly set."** Not when an HPA manages that Deployment — leaving it out (or using Server-Side Apply field ownership) is what prevents the manifest and the autoscaler from fighting each other.

## 13. 🔑 Key Takeaways

- The production manifest workflow is a five-step loop: author (generator-assisted, §31), validate (`--dry-run=server`), diff (`kubectl diff`), commit, apply — synthesizing every object type covered across §24–§30.
- `kubectl apply`'s three-way merge (last-applied-configuration ⊕ submitted manifest ⊕ live state) is what makes repeated, collaborative edits safe; `kubectl replace` has no such protection.
- Static manifest fields (like `replicas`) can conflict with dynamic controllers (HPA); the fix is field omission or Server-Side Apply field-ownership tracking, not fighting it with repeated applies.
- CI-enforced `--dry-run=server` and `kubectl diff` checks turn this manual workflow into a genuine safety gate, rather than a best-effort human habit.
- This entire manual loop is precisely what GitOps controllers (§88) automate end-to-end — understanding it by hand is the direct prerequisite for understanding what GitOps removes from human hands.

## 14. Related Concepts & What's Next

This section is the capstone of Part 4, synthesizing the Pod spec (§24), controller objects (§27, §28), deployment strategies (§29), labels/selectors (§30), and kubectl generator/diff tooling (§31) into the complete real-world authoring-and-shipping workflow. §88 (Part 11) covers GitOps tooling (ArgoCD, Flux) that automates this exact loop against a Git repository without a human running `kubectl apply` directly. Part 5 begins immediately with StatefulSets, extending the Deployment model covered here to workloads needing stable network identity and per-replica storage.

**Next Section:** §33 (Part 5) — `Section-33-Part5-Statefulsets-Stable-Network-Identity-Ordered-Deployment.md`
