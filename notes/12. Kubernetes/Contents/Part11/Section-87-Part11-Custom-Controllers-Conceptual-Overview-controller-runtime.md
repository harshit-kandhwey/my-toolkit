# Section 87 (Part 11): Custom Controllers (Conceptual Overview, controller-runtime)

## 1. Definition

**Plain language:** §86 established that an Operator is a CRD plus a controller that reconciles it — but "just write a controller" glosses over a surprising amount of genuinely hard, easy-to-get-wrong machinery: efficiently watching for changes across a whole cluster without hammering the api-server, handling the same event multiple times safely, and recovering cleanly from a crash mid-reconciliation. This section opens that box conceptually, focusing on the shared library — `controller-runtime` — that almost every real-world custom controller is built on, so that mechanism stops being a mystery.

**Precise definition:** A **custom controller** is user-written code implementing the watch/compare/act reconciliation loop (§13) against one or more resource types, typically a CRD (§86). **`controller-runtime`** is the shared Go library (maintained by the Kubernetes SIG API Machinery community, and the foundation of both Kubebuilder and the Operator SDK) that supplies the reusable infrastructure every custom controller needs: **informers** (efficient, cached, event-driven watches against the api-server), a **work queue** (deduplicating and rate-limiting reconcile requests so bursts of events collapse into a manageable number of actual reconcile calls), and a **Reconciler** interface — the single function (`Reconcile(ctx, request) (Result, error)`) where a controller author's own domain-specific logic lives. Because `controller-runtime` handles the generic, hard-to-get-right plumbing, a controller author's actual job reduces to writing one function: given a resource's name, compute and enforce the difference between desired and actual state.

## 2. Why This Matters

- **`controller-runtime` is the near-universal foundation beneath the Operator ecosystem** — Kubebuilder, Operator SDK, and the vast majority of production Operators (Prometheus Operator, cert-manager, most database Operators) are built on it, meaning understanding its core abstractions (informers, work queues, Reconcilers) transfers directly to reading or contributing to almost any real-world Operator's source code.
- **The informer/work-queue pattern is precisely what makes controllers scale to cluster-wide event volume without either missing events or overwhelming the api-server** — a naive "watch and immediately react to every single event" implementation would both duplicate work needlessly and risk falling behind under load; `controller-runtime`'s deduplicating queue is the specific mechanism that makes reconciliation robust in practice, not just in theory.
- **The `Reconcile` function's contract — it must be idempotent and safe to call repeatedly for the same object, including after a crash mid-execution — is the single most important design property from §13 made concrete**, and it's exactly the property a hastily-built custom controller most commonly gets wrong.

🔑 **Key Takeaway:** `controller-runtime` supplies the reusable plumbing (informers for efficient watches, a deduplicating work queue, a Reconciler interface) that every custom controller needs, reducing a controller author's actual job to writing one idempotent `Reconcile` function that computes and closes the gap between desired and actual state for a single object at a time.

## 3. Prerequisites and Dependencies

Builds directly on §86 (Operators and CRDs, this Part), which established _what_ a custom controller reconciles, and back-references §13 (Controller Manager, the Controller Pattern, and reconciliation loops, Part 2), whose generic watch/compare/act loop this section makes concrete at the implementation level. Forward-references §88 (GitOps Fundamentals), whose ArgoCD and Flux controllers are themselves built using this exact pattern, reconciling against Git rather than purely in-cluster desired state.

## 4. Architecture Diagram

```text
┌───────────────────────────────────────────────────────────────────────┐
│                            api-server                                 │
└──────────────────────────────┬────────────────────────────────────────┘
                               │  watch events (Add/Update/Delete)
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│  INFORMER (per watched resource type)                                 │
│  - maintains a local, in-memory CACHE of that resource's objects      │
│  - all reads by the controller hit this cache, NOT the api-server     │
│    directly — this is what keeps controllers from hammering it        │
└──────────────────────────────┬────────────────────────────────────────┘
                               │  on any relevant event, enqueue a
                               │  reconcile REQUEST (just a name/namespace,
                               │  never the object's full content)
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│  WORK QUEUE                                                           │
│  - DEDUPLICATES: 5 rapid updates to the same object collapse into ONE │
│    pending reconcile request, not five                                │
│  - RATE-LIMITS retries on error (exponential backoff)                 │
└──────────────────────────────┬────────────────────────────────────────┘
                               │  worker goroutine pulls next request
                               ▼
┌──────────────────────────────────────────────────────────────────────────┐
│  Reconcile(ctx, request) (Result, error)   <-- USER-WRITTEN CODE         │
│                                                                          │
│    1. Fetch current object from the informer's cache using request's name│
│    2. Fetch/derive real-world observed state                             │
│    3. Compare desired (spec) vs. observed state                          │
│    4. Act: create/update/delete derived objects via api-server client    │
│    5. Return Result{Requeue: bool, RequeueAfter: duration} or an error   │
└──────────────────────────────────────────────────────────────────────────┘
```

- **The informer's cache is what makes controllers scalable** — without it, every controller reconciling would issue a fresh API read against the live api-server, and with dozens of controllers running simultaneously (built-in and custom), that would overwhelm it; the cache is kept current via the same watch stream that triggers reconciliation in the first place.
- **A reconcile request carries only a name and namespace, never the object's content** — this is deliberate: by the time a worker actually processes the request, the object may have changed again, so `Reconcile` always re-fetches current state fresh from the cache rather than acting on a possibly-stale snapshot passed at enqueue time.

## 5. Hands-On

### 5.1 The Reconciler Interface in Practice

**Purpose:** Show the actual shape of the one function a controller author implements, using Go (the language `controller-runtime` and virtually all real-world Operators are written in).

**Syntax:**

```bash
kubebuilder init --domain example.com --repo github.com/example/postgres-operator
kubebuilder create api --group databases --version v1 --kind PostgresCluster
```

```go
func (r *PostgresClusterReconciler) Reconcile(ctx context.Context, req ctrl.Request) (ctrl.Result, error) {
    var cluster databasesv1.PostgresCluster
    if err := r.Get(ctx, req.NamespacedName, &cluster); err != nil {
        // Object was deleted; nothing further to reconcile.
        return ctrl.Result{}, client.IgnoreNotFound(err)
    }

    desiredReplicas := cluster.Spec.Replicas
    var sts appsv1.StatefulSet
    if err := r.Get(ctx, req.NamespacedName, &sts); err != nil {
        // StatefulSet doesn't exist yet — create it.
        return ctrl.Result{}, r.Create(ctx, buildStatefulSet(&cluster))
    }

    if *sts.Spec.Replicas != desiredReplicas {
        sts.Spec.Replicas = &desiredReplicas
        return ctrl.Result{}, r.Update(ctx, &sts)
    }

    return ctrl.Result{}, nil // actual matches desired; nothing to do
}
```

**Production usage example:** This exact scaffold — generated by Kubebuilder, then filled in with domain logic — is how essentially every modern Operator is built; the boilerplate (registering the Reconciler with the manager, wiring up watches on both the CRD and its derived StatefulSet) is generated once, leaving the author to focus purely on the domain-specific comparison and action logic inside `Reconcile`.

**Common errors:** Writing `Reconcile` logic that assumes it will only ever be called once per meaningful change — `controller-runtime` guarantees `Reconcile` _will_ be called multiple times for the same object (retries on error, periodic resyncs, unrelated watch triggers), so any logic with a side effect that isn't safe to repeat (e.g., "send exactly one email notification" without deduplication) will misbehave under this contract.

### 5.2 Watching Multiple Resource Types (Owned Resources)

**Purpose:** Show how a controller reconciling a CRD also needs to watch the derived objects it creates, so it notices if they drift.

**Syntax:**

```go
func (r *PostgresClusterReconciler) SetupWithManager(mgr ctrl.Manager) error {
    return ctrl.NewControllerManagedBy(mgr).
        For(&databasesv1.PostgresCluster{}).
        Owns(&appsv1.StatefulSet{}).
        Owns(&corev1.Service{}).
        Complete(r)
}
```

**Production usage example:** The `Owns()` calls are what let a PostgresCluster Operator notice — and correct — someone manually deleting or patching the StatefulSet it created (§86's "manual edits keep reverting" behavior), since an event on an owned StatefulSet re-triggers reconciliation of its owning PostgresCluster, not just events on the CRD itself.

**Common errors:** Forgetting to set an owner reference on a derived object when creating it — without it, `Owns()` watches won't correlate the derived object's events back to the correct parent CR, and orphaned derived objects also won't be automatically garbage-collected when their intended parent CR is deleted.

### 5.3 Local Development and Testing with envtest

**Purpose:** Show how custom controllers are typically tested without needing a full real cluster.

**Syntax:**

```bash
make test  # runs controller-gen-scaffolded tests against envtest's local api-server + etcd binaries
```

```yaml
# Excerpt: envtest spins up a real (but minimal, local) api-server + etcd
# so Reconcile logic can be tested against genuine API behavior, not mocks
```

**Production usage example:** `envtest` (part of the `controller-runtime` toolchain) runs a real, minimal api-server and etcd locally, letting CI test actual `Reconcile` behavior — creating CRs, asserting the correct derived objects appear — without needing a full Kubernetes cluster, which is both faster and closer to real behavior than mocking the Kubernetes client entirely.

**Common errors:** Testing `Reconcile` only with mocked Kubernetes clients rather than `envtest`'s real (if minimal) api-server — mocks can silently diverge from actual api-server behavior (admission defaults, validation errors, garbage collection timing), giving false test confidence that doesn't hold up against a real cluster.

## 6. Production Usage Notes

- **`controller-runtime`'s work queue applies exponential backoff to repeatedly failing reconciles automatically** — a `Reconcile` call returning a non-nil error gets requeued with increasing delay, which is why a struggling controller often shows a _slowing_ retry pattern in its logs rather than a tight failure loop, a useful diagnostic signal on its own.
- **Periodic resyncs (a full re-reconcile of every watched object on a fixed interval, independent of any actual change) are a deliberate `controller-runtime` feature**, guarding against silently missed events (a rare but real possibility with any watch-based system) by guaranteeing every object gets re-evaluated at least occasionally regardless.
- **Leader election is built into `controller-runtime`'s manager** for controllers run with multiple replicas for high availability — only the elected leader actively reconciles at any moment, avoiding the same object being reconciled concurrently by multiple replicas, while the standby replicas are ready to take over immediately if the leader's Pod fails.

## 7. Security Considerations

- **A custom controller's RBAC permissions (via its ServiceAccount) should be scoped to exactly the resource types its `Reconcile` logic touches** — `controller-runtime`-based projects typically generate RBAC manifests directly from `+kubebuilder:rbac` code annotations, which keeps the granted permissions honest and traceable to the actual code that uses them, rather than hand-maintained and prone to drifting into over-permissiveness.
- **`Reconcile` logic that constructs Kubernetes object specs from CR fields must treat those fields as untrusted input**, the same principle as §86's CR-input-validation point — a CR field used unsanitized inside a container command or image reference is a real injection vector if any less-trusted identity can create CRs of that type.
- **Owner references used for garbage collection are also a security-relevant mechanism** — a controller that fails to set them correctly can leave derived Secrets or ConfigMaps orphaned after their owning CR is deleted, silently persisting credentials or configuration beyond their intended lifecycle.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                 | Cause                                                                                           | Fix                                                                                                        |
| --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Reconciliation is stuck retrying with increasing delay between attempts                 | `Reconcile` is returning a non-nil error repeatedly; work queue's exponential backoff is active | Check the controller's logs for the actual returned error; fix the underlying condition causing it         |
| Manual edits to a derived object (StatefulSet) revert almost immediately                | An `Owns()` watch correctly re-triggered reconciliation, which corrected the drift              | Expected behavior — edit the owning CR's spec instead of the derived object directly                       |
| A derived object isn't garbage-collected after its owning CR is deleted                 | The controller failed to set an owner reference when creating the derived object                | Fix the controller code to set `controllerutil.SetControllerReference` on every derived object it creates  |
| Controller with multiple replicas seems to reconcile the same object twice concurrently | Leader election isn't configured or is misconfigured, allowing multiple active reconcilers      | Verify `LeaderElection: true` is set on the manager, and check the leader election Lease object's holder   |
| Test suite passes against mocks but the real Operator misbehaves in-cluster             | Tests used a mocked client instead of `envtest`'s real api-server, masking actual API behavior  | Migrate tests to `envtest` so they exercise genuine admission, validation, and garbage-collection behavior |

## 9. Best Practices

- Scaffold new custom controllers with Kubebuilder or Operator SDK rather than hand-assembling `controller-runtime` primitives from scratch, to inherit correct, tested boilerplate for manager setup, RBAC generation, and webhook wiring.
- Write `Reconcile` functions that are strictly idempotent — safe to call repeatedly, including immediately after a crash mid-execution — treating this property as a non-negotiable design constraint, not an implementation detail to revisit later.
- Always set owner references on derived objects created by a controller, both for correct `Owns()`-watch correlation and for automatic garbage collection.
- Test against `envtest`'s real (if minimal) api-server rather than mocked clients, to catch divergences from actual cluster behavior before production.

## 10. Common Anti-Patterns / Mistakes

- **Writing `Reconcile` logic with non-idempotent side effects** (e.g., unconditionally incrementing an external counter, sending a notification without deduplication) that breaks under `controller-runtime`'s guaranteed multiple-invocation contract.
- **Forgetting owner references on derived objects**, breaking both drift-correction watches and garbage collection when the owning CR is later deleted.
- **Testing exclusively against mocked Kubernetes clients**, gaining false confidence that doesn't transfer to real cluster behavior around admission, validation, and garbage collection timing.

## 11. Interview Questions

**🎯 Beginner:** _"What problem does `controller-runtime` solve, and what's the one thing a controller author actually has to write?"_
**Model answer:** `controller-runtime` supplies all the generic, hard-to-get-right plumbing every controller needs — efficient cached watches (informers), a deduplicating and rate-limited work queue, and the wiring to register a controller with the cluster. What's left for the controller author to write is a single function, `Reconcile`, that's handed just a resource's name and namespace, fetches its current state, compares it against desired state, and takes corrective action. Everything else — how and when that function gets called — is handled by the library.
_What the interviewer is probing for:_ Clear grasp that `controller-runtime` is reusable infrastructure, and the actual authored logic is narrowly scoped to one reconcile function.

**🎯 Intermediate:** _"Why does `controller-runtime` deduplicate reconcile requests in a work queue instead of processing every single watch event individually?"_
**Model answer:** Because a single object can generate many rapid, closely-spaced update events (multiple field changes, status updates, unrelated churn), processing every event individually would mean redundant reconcile calls doing essentially the same work repeatedly — wasteful, and in high-churn clusters, potentially overwhelming. By collapsing the queue to at most one pending reconcile request per object (identified just by name/namespace, not event content), multiple rapid changes to the same object naturally coalesce into a single reconcile pass that reads the object's latest state fresh — which is also why `Reconcile` always re-fetches current state rather than acting on data passed at enqueue time.
_What the interviewer is probing for:_ Understanding both the efficiency rationale for deduplication and its direct consequence — that `Reconcile` must always read fresh state rather than trust any data captured earlier.

**🎯 Senior:** _"A custom controller behaves correctly in `envtest` but misbehaves when run with multiple replicas in production, occasionally double-processing the same object. What's the likely cause and fix?"_
**Model answer:** This is the classic signature of missing or misconfigured leader election — `controller-runtime`'s manager supports leader election specifically so that only one replica actively reconciles at a time even when multiple replicas are running for availability, with standbys ready to take over on leader failure via a Lease object. If leader election isn't enabled (or is enabled but each replica is somehow acquiring its own separate lease due to misconfiguration), multiple replicas can end up actively reconciling the same objects concurrently, which is exactly the double-processing symptom described. `envtest` typically runs a single controller instance in tests, so this class of bug specifically wouldn't surface there — it only appears once multiple replicas are actually running together, which is worth calling out as a real gap between test and production topology.
_What the interviewer is probing for:_ Recognizing leader election as the specific mechanism preventing concurrent multi-replica reconciliation, and awareness that single-instance test environments like `envtest` can't surface this entire class of bug.

**🎯 Architect:** _"You're designing the reconciliation strategy for a controller managing external, non-Kubernetes infrastructure (e.g., a controller that provisions cloud database instances via a cloud provider's API). What controller-runtime design considerations become more critical than for a purely in-cluster controller?"_
**Model answer:** The core idempotency requirement from §13 becomes considerably harder to satisfy, because "observed state" now means calling out to an external API with its own latency, rate limits, and eventual-consistency behavior, rather than reading a locally cached, immediately consistent Kubernetes object — I'd design `Reconcile` to always treat the external system as the actual source of observed truth, re-querying it fresh (or from a short-lived cache with an explicit TTL, not the informer's indefinite cache) rather than assuming its own prior write immediately reflects there. I'd lean heavily on `controller-runtime`'s `Result{RequeueAfter: duration}` return value to poll the external system's actual provisioning status on a controlled interval rather than assuming synchronous completion, since most cloud provisioning APIs are asynchronous. I'd also build explicit handling for partial failure — a reconcile that successfully calls the cloud API to start provisioning but crashes before recording that fact must, on its next invocation, detect the in-flight external resource rather than blindly re-issuing a duplicate provisioning call — which typically means storing a tracking identifier (the cloud resource's ID) in the CR's `status` subresource as early as possible in the reconcile sequence, specifically so a crash-and-retry can recognize prior progress. Finally, I'd scope the controller's cloud IAM credentials as tightly as its CRD's actual scope of responsibility, mirroring the in-cluster RBAC least-privilege principle but extended to the external system's own permission model.
_What the interviewer is probing for:_ Ability to extend the idempotent-reconciliation design discipline to a domain with genuine external-system asynchrony and partial-failure risk, specifically identifying status-subresource tracking as the mechanism that makes crash recovery safe against duplicate external side effects.

## 12. Common Misconceptions

1. **"A controller author has to implement the watch and event-handling machinery themselves."** `controller-runtime` supplies informers, the work queue, and manager wiring; the author writes only the `Reconcile` function's domain logic.
2. **"`Reconcile` is only called once per meaningful change to an object."** It's guaranteed to be called multiple times for the same object (error retries, periodic resyncs, unrelated triggers) — reconcile logic must be idempotent and safe under repeated invocation.
3. **"Testing against a mocked Kubernetes client is equivalent to testing against a real cluster."** Mocks can silently diverge from actual api-server behavior (admission, validation, garbage collection); `envtest`'s real (if minimal) api-server is the more reliable test target.
4. **"Running multiple controller replicas automatically provides safe, non-duplicated reconciliation."** It requires leader election to be correctly configured — without it, multiple replicas can reconcile the same object concurrently.

## 13. 🔑 Key Takeaways

- `controller-runtime` supplies the reusable plumbing (informers, a deduplicating/rate-limited work queue, manager/leader-election wiring) so a controller author's actual job is writing one idempotent `Reconcile` function.
- Reconcile requests carry only a name/namespace, never object content, because `Reconcile` must always re-fetch current state fresh — a direct consequence of the work queue's deduplication design.
- `Owns()` watches on derived objects, paired with correctly-set owner references, are what enable both drift correction and automatic garbage collection.
- Leader election is required for safe multi-replica controller deployments; without it, concurrent reconciliation of the same object is possible.
- Test custom controllers against `envtest`'s real (if minimal) api-server rather than mocked clients, to avoid false confidence that doesn't hold up in production.

## 14. Related Concepts & What's Next

This section made §86's abstract Operator pattern concrete at the implementation level, and reinforced §13's idempotent-reconciliation design principle as `controller-runtime`'s core `Reconcile` contract. §88, next, closes out Part 11 by covering GitOps fundamentals with ArgoCD and Flux — both of which are themselves `controller-runtime`-style controllers, reconciling live cluster state against a Git repository's declared desired state, tying together Helm (§82–§83), Kustomize (§84), Operators (§86), and custom controllers (this section) into a single coherent delivery model.

**Next Section:** §88 — `Section-88-Part11-GitOps-Fundamentals-ArgoCD-Flux.md`
