# Section 31 (Part 4): kubectl Fundamentals: Imperative Commands, Generators, --dry-run, kubectl diff

## 1. Definition

**Plain language:** `kubectl` is the primary command-line tool you use to talk to a Kubernetes cluster, and while §4 established that declarative YAML is the production standard, `kubectl` itself has an entire imperative command surface that — used correctly — becomes one of the fastest ways to _produce_ that YAML in the first place, rather than a competing way to manage production state.
"Correctly", specifically, means using imperative commands as **generators**: producing a starter manifest via `--dry-run=client -o yaml` and then treating that output as the thing you actually commit and apply, not treating the imperative command itself as the deployment mechanism.

**Precise definition:** **Imperative commands** (`kubectl run`, `kubectl create`, `kubectl expose`, `kubectl scale`) issue a direct, one-time action against the API server. **Generators** are the object-construction logic behind commands like `kubectl create deployment`/`kubectl create service` that can, given `--dry-run=client -o yaml`, print the equivalent YAML manifest **without sending it to the API server at all** — client-side only. `kubectl diff` compares a local manifest against live cluster state and prints exactly what a subsequent `kubectl apply` would change, without applying anything, functioning as a pre-flight preview.

## 2. Why This Matters

- **This is the standard technique for exam-speed manifest authoring.** §130–§137 (Part 17) cover CKA/CKAD/CKS exam strategy in depth, and `kubectl create deployment web --image=nginx --dry-run=client -o yaml > web.yaml` is the single highest-leverage command pattern for producing correct, boilerplate-free YAML in seconds under time pressure, rather than hand-typing a Deployment spec from memory.
- **`--dry-run=client` vs `--dry-run=server` catch fundamentally different classes of error.** Client-side dry-run only validates the request shape locally; server-side dry-run (`--dry-run=server`) sends the request through the full API server validation and admission chain (§77, Part 10) without persisting it — meaning it can catch admission-webhook or quota rejections client-side dry-run cannot.
- **`kubectl diff` closes the gap §4 left open** — it's the concrete tool that lets an operator or CI pipeline preview a declarative change before committing to it, directly extending the imperative-vs-declarative distinction established in §4 into an actual pre-apply safety practice.

🔑 **Key Takeaway:** `kubectl`'s imperative commands are at their most valuable not as a production deployment mechanism, but as a **YAML generator** — `--dry-run=client -o yaml` produces a correct manifest instantly, which you then treat as the declarative source of truth, previewing any subsequent change with `kubectl diff` before it ever touches the cluster.

## 3. Prerequisites and Dependencies

Builds directly on §4 (Part 1's declarative-vs-imperative model, which this section operationalizes into concrete command patterns) and §24–§29 (Pod/Deployment/ReplicaSet objects this section's commands generate).

## 4. Architecture Diagram

```text
   kubectl create deployment web --image=nginx:1.25 --dry-run=client -o yaml
                       │
                       │  (client-side only — nothing sent to API server)
                       ▼
             ┌─────────────────────┐
             │  Generated YAML     │───► redirect to file: > web-deployment.yaml
             │  (Deployment object)│───► edit further (add resources, probes...)
             └─────────────────────┘
                       │
                       ▼
             kubectl diff -f web-deployment.yaml     ← preview: what WOULD change
                       │
                       ▼
             kubectl apply -f web-deployment.yaml    ← actually applied (§4, §32)


   --dry-run=client                    --dry-run=server
   ─────────────────                   ─────────────────
   Local validation only.              Full request sent through API server's
   No API server round-trip.           validation + admission chain (§77),
   Fastest; misses server-side         then discarded without persisting.
   validation/admission issues.        Catches quota/webhook rejections
                                        client-side dry-run cannot.
```

- **The generator-then-edit-then-apply pipeline is the actual production workflow**, not just an exam trick: generate the skeleton fast, hand-edit the parts `kubectl create` can't express (resource limits, probes, volumes), then apply declaratively.
- **`kubectl diff` requires the `KUBECTL_EXTERNAL_DIFF` environment variable or defaults to a standard `diff`-style tool** under the hood, and needs the same RBAC read permissions as `kubectl get` on the relevant resource to compare against live state.

## 5. Hands-On: Generators, Dry-Run, and Diff in Practice

### 5.1 Generating a Deployment Manifest with `--dry-run=client -o yaml`

**Purpose:** Produce a correct starter manifest in seconds instead of hand-writing boilerplate.

**Syntax:**

```bash
kubectl create deployment <name> --image=<image> --replicas=<n> --dry-run=client -o yaml
```

```bash
$ kubectl create deployment web --image=nginx:1.25 --replicas=3 --dry-run=client -o yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  creationTimestamp: null
  labels:
    app: web
  name: web
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web
  strategy: {}
  template:
    metadata:
      creationTimestamp: null
      labels:
        app: web
    spec:
      containers:
        - image: nginx:1.25
          name: nginx
          resources: {}
status: {}
```

**Production usage example:** `kubectl create deployment web --image=nginx:1.25 --dry-run=client -o yaml > web-deployment.yaml` is a routine first step even for experienced platform engineers — it's faster and less error-prone than hand-typing `apiVersion`/`kind`/`selector` boilerplate from memory, with the generated YAML then hand-edited to add resource requests/limits, probes, and other fields the generator doesn't populate.

**Common errors:** Forgetting to strip the empty `status: {}` and `creationTimestamp: null` fields before committing the file to version control is harmless (the API server ignores/overwrites them on apply) but considered untidy; many teams pipe the output through `yq`/manual cleanup before committing.

### 5.2 `--dry-run=server` for Full Validation Without Persisting

**Purpose:** Catch admission-controller and quota rejections before genuinely committing to a change.

```bash
$ kubectl apply -f web-deployment.yaml --dry-run=server
deployment.apps/web created (server dry run)

$ kubectl apply -f web-deployment.yaml --dry-run=server
Error from server: error when creating "web-deployment.yaml":
admission webhook "policy.example.com" denied the request:
containers must set resource limits
```

**Production usage example:** CI pipelines commonly run `kubectl apply --dry-run=server` as a pre-merge validation gate, catching a Pod Security Admission (§78, Part 10) or OPA/Gatekeeper policy violation before the change is even merged, which `--dry-run=client` — being purely local — cannot detect at all.

### 5.3 `kubectl diff` — Previewing Exactly What Would Change

**Purpose:** See the concrete field-level diff `kubectl apply` would produce, before applying it.

**Syntax:**

```bash
kubectl diff -f <file>.yaml
```

```bash
$ kubectl diff -f web-deployment.yaml
diff -u -N /tmp/LIVE-123/apps.v1.Deployment.default.web /tmp/MERGED-456/apps.v1.Deployment.default.web
--- /tmp/LIVE-123/apps.v1.Deployment.default.web
+++ /tmp/MERGED-456/apps.v1.Deployment.default.web
@@ -13,7 +13,7 @@
   spec:
-    replicas: 3
+    replicas: 5
     selector:
       matchLabels:
         app: web
```

**Production usage example:** Run as a mandatory step immediately before `kubectl apply` in CI/CD pipelines and by operators during incident response — it's the concrete tool that turns "I think this manifest change is safe" into a verified, line-level confirmation before anything touches the live cluster, directly extending the caution §4 recommends around declarative changes.

**Common errors:** `kubectl diff` returns a non-zero exit code whenever a diff exists (even an intentional one) — pipelines that treat any non-zero exit as failure need to explicitly branch on this rather than aborting the deploy on an expected, reviewed change.

## 6. Production Usage Notes

- **The generator pattern extends beyond Deployments** — `kubectl create service clusterip`, `kubectl create configmap --from-literal`, `kubectl create secret generic --from-file`, and `kubectl expose` all support `--dry-run=client -o yaml`, making this a general-purpose fast-authoring technique across almost every core object type, not just workloads.
- **`--dry-run=server` costs a real round-trip to the API server** and, depending on admission webhook complexity, is measurably slower than `--dry-run=client` — teams use client-side dry-run for rapid local iteration and reserve server-side dry-run for a final pre-merge CI gate.
- **`kubectl diff` is only as good as the RBAC permissions of whoever runs it** — a service account with restricted read access on a namespace will get incomplete or denied diffs, a common false negative in locked-down CI runners that needs an explicitly scoped ClusterRole (§74, Part 10).

## 7. Security Considerations

- Encouraging `--dry-run=client -o yaml` as the default generation technique reduces the temptation to run bare imperative commands directly against production, which — per §4 — bypasses any review or admission gate a declarative, Git-reviewed pipeline would otherwise enforce.
- `kubectl diff`'s reliance on local read access means it can only be trusted as a safety gate if the identity running it has sufficiently broad (but still least-privilege) read permissions on the target namespace — an overly restricted CI identity produces a false sense of safety by silently truncating the diff.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Likely Cause                                                                                                                 | Resolution Path                                                                                                                           |
| -------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Generated YAML from `--dry-run=client` is missing fields a team expects    | Client-side generators only populate a minimal object skeleton                                                               | Hand-edit the generated YAML to add resource limits, probes, volumes — the generator is a starting point, not a finished manifest         |
| `kubectl apply --dry-run=server` succeeds locally but the real apply fails | An admission webhook behaves differently under `--dry-run=server` vs a real request (rare, webhook-implementation dependent) | Verify the webhook explicitly honors the `dryRun` field in `AdmissionReview`; some poorly written webhooks skip dry-run handling entirely |
| `kubectl diff` exits non-zero in CI and fails the pipeline unexpectedly    | Pipeline treats any non-zero exit as failure, but a non-zero exit from `diff` just means "a diff exists"                     | Explicitly branch pipeline logic on `kubectl diff`'s exit code semantics rather than treating it as a generic failure                     |

## 9. Best Practices

- Default to `kubectl create <object> --dry-run=client -o yaml > file.yaml` as the starting point for any new manifest, rather than hand-typing boilerplate from scratch.
- Add `kubectl apply -f <file> --dry-run=server` as a CI gate ahead of merge, catching admission/quota rejections earlier than a real deploy attempt would.
- Run `kubectl diff -f <file>` immediately before every `kubectl apply` in both CI pipelines and manual incident-response changes, treating an unexpected diff as a stop-and-investigate signal.

## 10. Common Anti-Patterns / Mistakes

- **Treating `kubectl run`/`kubectl create` as an acceptable production deployment mechanism** rather than purely a generator or debugging tool, reintroducing exactly the risks §4 describes (no self-healing enforcement, no audit trail).
- **Skipping `kubectl diff` before `apply` in CI pipelines**, losing the one concrete opportunity to catch an unintended change before it's live.
- **Assuming `--dry-run=client` validates everything** — it cannot catch admission webhook or ResourceQuota rejections, which only `--dry-run=server` or a real apply will surface.

## 11. Interview Questions

**🎯 Beginner:** _"What does `kubectl create deployment web --image=nginx --dry-run=client -o yaml` actually do?"_
**Model answer:** It builds the Deployment object client-side, using the same generator logic `kubectl create deployment` would normally use to send a create request, but because of `--dry-run=client` it never contacts the API server — instead of creating anything, it prints the resulting YAML to stdout, which can be redirected into a file and used as a starter manifest.
_What the interviewer is probing for:_ Whether the candidate understands this is purely a local, client-side operation with zero cluster side effects.

**🎯 Intermediate:** _"What's the difference between `--dry-run=client` and `--dry-run=server`, and when would you use each?"_
**Model answer:** `--dry-run=client` builds and validates the request entirely locally without any API server round-trip — fast, but it can't catch anything the server itself would enforce, like admission webhook policies or ResourceQuota limits. `--dry-run=server` sends the full request through the API server's validation and admission chain and reports what would happen, but doesn't persist it — slower, since it's a real round trip, but it catches server-side-only rejections. I'd use client-side dry-run for rapid local iteration while drafting a manifest, and server-side dry-run as a final CI gate before merge, to catch policy violations early without actually deploying.
_What the interviewer is probing for:_ Concrete understanding of what each dry-run mode actually validates, not just that both "don't really create anything."

**🎯 Senior:** _"Your team wants to add a safety gate to the deploy pipeline that prevents unreviewed changes from silently modifying more than expected. How do you use `kubectl diff` to build this?"_
**Model answer:** I'd add `kubectl diff -f <manifests>/ ` as a required CI step immediately before the `kubectl apply` step, piping its output into the pipeline's build log and, ideally, into the pull request as a visible comment so reviewers see the exact field-level change before approving. Since `kubectl diff` exits non-zero whenever any diff exists, I'd explicitly branch on that (rather than treating any non-zero exit as failure) — the real gate is a human or policy check confirming the shown diff matches intent, not the exit code itself. I'd also make sure the CI identity running `kubectl diff` has sufficiently broad read RBAC on the target namespace (§74, Part 10), since an under-scoped service account produces an incomplete diff that undermines the entire safety gate without any obvious error.
_What the interviewer is probing for:_ Ability to turn a simple CLI feature into an actual pipeline safety control, including the RBAC and exit-code subtleties that make or break it in practice.

**🎯 Architect:** _"You're designing kubectl usage policy for a large platform team under exam-speed and production-safety pressure simultaneously. How do you reconcile 'use imperative commands for speed' with 'declarative manifests are the production standard'?"_
**Model answer:** These aren't actually in tension once framed correctly: imperative commands are sanctioned specifically as a **generation** step — `--dry-run=client -o yaml` — never as a live-apply mechanism against anything persistent. I'd codify this as policy: any imperative command that would mutate cluster state directly (`kubectl run` without `--dry-run`, `kubectl scale`, `kubectl edit`) is restricted to non-production namespaces or genuine incident-response escape hatches, while `--dry-run=client`/`server` and `kubectl diff` are actively encouraged everywhere, including in CI, as the fast-and-safe path to producing and validating declarative manifests. This lets engineers get the speed benefit of imperative tooling (crucial under CKA/CKAD exam time pressure, §130–137) while keeping the actual source of truth and deployment mechanism entirely declarative and Git-reviewed (§32, §88). I'd enforce the production-namespace restriction via RBAC (§74) rather than relying on convention alone, since policy that depends purely on developer discipline eventually gets violated under pressure.
_What the interviewer is probing for:_ Whether the candidate can architect a coherent policy that captures imperative tooling's real value (fast generation) without compromising the declarative production model, backed by an actual enforcement mechanism rather than a guideline.

## 12. Common Misconceptions

1. **"`--dry-run=client` fully validates a manifest."** It only validates locally-checkable structure; it cannot catch admission webhook or quota rejections, which require `--dry-run=server` or a real request.
2. **"Imperative commands and declarative manifests are competing approaches you pick one of."** In practice they compose: imperative commands generate the manifest, which is then managed declaratively — they're sequential steps in one workflow, not alternatives.
3. **"`kubectl diff` applies the change if it looks fine."** It never mutates anything — it only computes and displays what a subsequent `apply` would do; `apply` must still be run separately.
4. **"A non-zero exit from `kubectl diff` means something is broken."** It simply means a diff exists between local and live state — for a genuinely intended change, that's expected and not a failure signal.

## 13. 🔑 Key Takeaways

- `--dry-run=client -o yaml` turns any `kubectl create`/`kubectl expose` command into a fast, correct YAML generator with zero cluster side effects — the standard technique for both exam speed and real manifest authoring.
- `--dry-run=server` validates against the full API server admission chain without persisting, catching classes of error client-side dry-run structurally cannot.
- `kubectl diff` previews exactly what an `apply` would change, and belongs as a mandatory step immediately before any `apply` in both CI and manual operations.
- Imperative commands and declarative manifests aren't competitors — the production workflow chains them: generate imperatively, edit and commit declaratively, preview with `diff`, then `apply`.
- `kubectl diff`'s usefulness depends entirely on the RBAC read scope of whoever runs it — an under-scoped identity silently produces an incomplete, falsely reassuring diff.

## 14. Related Concepts & What's Next

§4 (Part 1) introduced the declarative-vs-imperative distinction this section operationalizes into concrete generator and preview commands. §24–§29 cover the Pod, Deployment, and ReplicaSet objects these commands generate. §77 (Part 10) covers the admission chain that `--dry-run=server` exercises without persisting. §130–§137 (Part 17) build directly on this section's generator patterns as core CKA/CKAD exam-speed technique. §32 closes out Part 4 by synthesizing generator output, hand-authored YAML, and the full `apply` workflow into one coherent production process.

**Next Section:** §32 — `Section-32-Part4-YAML-Manifest-Authoring-Kubectl-Apply-Workflow.md`
