# Section 29 (Part 4): Deployment Strategies: RollingUpdate vs. Recreate; Blue/Green and Canary Patterns

## 1. Definition

**Plain language:** Once you accept that updates need to happen safely (§28), the next question is exactly _how_ old and new versions coexist during that transition — do you take everything down and bring the new version up cold, trickle new Pods in gradually, or run both versions fully side-by-side and switch traffic all at once? Different answers suit different risk tolerances, and Kubernetes only natively builds in two of the possible answers.

**Precise definition:** Kubernetes' Deployment object supports exactly two **native, built-in strategies** via `spec.strategy.type`: **`RollingUpdate`** (the default — incrementally replaces old Pods with new ones, controlled by `maxUnavailable`/`maxSurge`) and **`Recreate`** (terminates all old Pods before creating any new ones, guaranteeing no version overlap at the cost of downtime). **Blue/Green** and **Canary** are **not** built-in Deployment strategy values — they are architectural _patterns_ achieved by running two separate Deployments (or Deployment + traffic-splitting mechanism) and controlling traffic distribution between them externally, typically via Service selector swaps, Ingress/Gateway traffic weighting, or dedicated progressive-delivery controllers like Argo Rollouts or Flagger (§88, Part 11).

## 2. Why This Matters

- **`RollingUpdate` vs. `Recreate` is a Kubernetes-native, zero-extra-tooling choice** — every cluster supports both out of the box, making the distinction between "brief overlap of two versions" (RollingUpdate) and "guaranteed no overlap, but downtime" (Recreate) a decision every Deployment author actually has to make, even if only by accepting the default.
- **Blue/Green and Canary require additional infrastructure that a bare Deployment alone cannot provide.** This is one of the single most common points of confusion in Kubernetes interviews and real design discussions — conflating "I can achieve a canary-like effect by manually pausing a rollout" (§28) with "Kubernetes has a native Canary strategy" leads to under-engineered, manually-babysat "canary" deployments in production.
- **The choice directly trades off risk, cost, and complexity.** `Recreate` is simplest but incurs downtime; `RollingUpdate` avoids downtime but requires the application to tolerate two versions running simultaneously (a real constraint, e.g., during schema-incompatible database migrations); Blue/Green and Canary buy much finer-grained safety and instant rollback at the cost of running duplicate infrastructure and/or adopting new tooling.

🔑 **Key Takeaway:** `RollingUpdate` and `Recreate` are the only two strategies Kubernetes Deployments natively understand; Blue/Green and Canary are patterns built _on top of_ Kubernetes primitives (extra Deployments, Service selector changes, Ingress weighting, or dedicated controllers), not settings in `spec.strategy.type` — conflating the two is a common and consequential misunderstanding.

## 3. Prerequisites and Dependencies

Builds directly on §28 (Deployment rollout mechanics and revision history) and §27 (ReplicaSets as the objects a Deployment shifts replicas between during any of these strategies).

## 4. Architecture Diagram

```text
NATIVE (built into the Deployment object):

  RollingUpdate (default)              Recreate
  ────────────────────────             ────────────────────────
  t0: [v1][v1][v1][v1]                 t0: [v1][v1][v1][v1]
  t1: [v1][v1][v1][v2]  ← surge/       t1: [ ][ ][ ][ ]        ← ALL v1
                          unavailable       (brief full outage)
  t2: [v1][v1][v2][v2]     bounded
  t3: [v2][v2][v2][v2]  ← complete     t2: [v2][v2][v2][v2]  ← ALL v2 up
                                            (after t1 fully drains)

  Both versions briefly coexist.       Never overlap; downtime window
  No downtime, if replicas > 1.        between old-gone and new-ready.

──────────────────────────────────────────────────────────────────────

NOT NATIVE (require extra tooling/objects on top of Deployments):

  Blue/Green                            Canary
  ────────────────────────              ────────────────────────
  Deployment "app-blue"  (v1, live)      Deployment "app" (v1, 95% traffic)
  Deployment "app-green" (v2, staged)    Deployment "app-canary" (v2, 5%)
        │                                      │
  Service selector flips                 Ingress/Gateway/service-mesh
  blue → green, all at once              traffic-splits by weight,
  (instant cutover, instant                gradually shifted upward
   rollback by flipping back)             (gradual exposure, fast pull-back)
```

- **RollingUpdate's `maxUnavailable`/`maxSurge` directly control the shape of the middle diagram** — `maxUnavailable: 0` with a positive `maxSurge` guarantees full capacity throughout at the cost of temporarily exceeding the declared replica count; `maxSurge: 0` with a positive `maxUnavailable` guarantees never exceeding the replica count at the cost of temporarily reduced capacity.
- **Recreate is the right (and often only sane) choice when two versions genuinely cannot coexist** — e.g., an application making a breaking, non-backward-compatible schema change against a shared database, where even a brief window of old and new Pods running simultaneously would corrupt data.
- **Blue/Green and Canary both depend on something outside the Deployment object making the traffic-routing decision** — a Service's `spec.selector`, an Ingress's traffic-splitting annotations, a Gateway API `HTTPRoute` weight, or a dedicated controller's custom resource.

## 5. Hands-On: Configuring and Approximating Each Strategy

### 5.1 Native `RollingUpdate` with Explicit Pacing

**Purpose:** Tune exactly how conservative or aggressive a rolling update is.

```yaml
# app-deployment-rolling.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app
spec:
  replicas: 6
  strategy:
    type: RollingUpdate
    rollingUpdate:
      maxUnavailable: 1 # at most 1 fewer than desired at any point
      maxSurge: 2 # at most 2 more than desired at any point
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
          image: myregistry/app:v2
```

```bash
$ kubectl apply -f app-deployment-rolling.yaml
deployment.apps/app configured

$ kubectl get rs -l app=app -w
NAME             DESIRED   CURRENT   READY   AGE
app-5d2a1 (v1)   4         4         4       10m
app-b7f9c (v2)   2         2         1       5s
```

**Production usage example:** Setting `maxUnavailable: 0` is standard for user-facing services where capacity must never dip below the declared replica count during a deploy, accepting the small transient cost of `maxSurge` extra Pods (and their resource consumption) instead.

### 5.2 Native `Recreate` for Version-Incompatible Workloads

**Purpose:** Guarantee zero overlap between old and new Pod versions.

```yaml
# app-deployment-recreate.yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: app-migrator
spec:
  replicas: 3
  strategy:
    type: Recreate
  selector:
    matchLabels:
      app: app-migrator
  template:
    metadata:
      labels:
        app: app-migrator
    spec:
      containers:
        - name: app
          image: myregistry/app:v2-breaking-schema-change
```

```bash
$ kubectl apply -f app-deployment-recreate.yaml
deployment.apps/app-migrator configured

$ kubectl get pods -l app=app-migrator -w
NAME                   READY   STATUS        AGE
app-migrator-5d2a1-x   1/1     Terminating   12m
app-migrator-5d2a1-y   1/1     Terminating   12m
app-migrator-5d2a1-z   1/1     Terminating   12m
# brief gap — zero Pods matching selector
app-migrator-b7f9c-a   1/1     Running       3s
app-migrator-b7f9c-b   1/1     Running       3s
app-migrator-b7f9c-c   1/1     Running       2s
```

**Common errors:** Using `Recreate` for a normal stateless service that didn't actually need it introduces avoidable downtime — confirm the incompatibility is real (e.g., verify the schema migration truly cannot support both versions reading/writing concurrently) before reaching for `Recreate` over the default `RollingUpdate`.

### 5.3 Approximating Blue/Green with Two Deployments and a Service Selector Swap

**Purpose:** Demonstrate the pattern concretely, since it is not a `spec.strategy.type` value.

```yaml
# service.yaml — the cutover point
apiVersion: v1
kind: Service
metadata:
  name: app
spec:
  selector:
    app: app
    version: blue # ← changing this value IS the cutover
  ports:
    - port: 80
      targetPort: 8080
```

```bash
# app-blue (v1) and app-green (v2) both already running as separate Deployments
$ kubectl get deployments -l app=app
NAME        READY   UP-TO-DATE   AVAILABLE   AGE
app-blue    4/4     4            4           2d
app-green   4/4     4            4           5m

# cutover: flip the Service selector to green
$ kubectl patch service app -p '{"spec":{"selector":{"version":"green"}}}'
service/app patched

# instant rollback if green is bad: flip back
$ kubectl patch service app -p '{"spec":{"selector":{"version":"blue"}}}'
service/app patched
```

**Production usage example:** Blue/Green is favored when instant, guaranteed rollback matters more than infrastructure efficiency — the old version stays fully warm and ready the entire time, so rollback is a Service-selector change, not a re-deploy, at the cost of running the full duplicate replica count of both versions simultaneously.

**Common errors:** Forgetting to also scale down (or delete) the old-color Deployment after a successful cutover leaves duplicate infrastructure running indefinitely, silently doubling compute cost for no ongoing benefit.

## 6. Production Usage Notes

- **A hand-rolled Canary using `kubectl rollout pause` (§28) only controls replica-count-based exposure**, not actual traffic-percentage weighting — two Pods out of ten Deployment replicas doesn't guarantee 20% of _traffic_, since Service load-balancing (§53, Part 7) typically distributes evenly per-Pod, not per-version-aware; true traffic-weighted canaries need Ingress/Gateway/service-mesh-level traffic splitting.
- **Real production Canary and Blue/Green pipelines generally use dedicated tooling** — Argo Rollouts or Flagger (§88, Part 11) — specifically because they automate metric-driven promotion/rollback decisions, traffic-weight shifting, and integrate with the same Deployment/ReplicaSet primitives underneath rather than replacing them.
- **`Recreate` is genuinely still the right choice in specific, real scenarios** — not just a legacy option — anywhere two application versions cannot safely coexist against shared state, which is more common with monolithic or tightly-coupled database schemas than with well-designed microservices.

## 7. Security Considerations

- Blue/Green's duplicate-Deployment pattern means both versions' images, Secrets, and RBAC bindings are live simultaneously until cutover and cleanup — a security review of "what's currently running" needs to account for both colors during the transition window, not just the one currently receiving traffic.
- Canary deployments intentionally expose a new, less-vetted version to a slice of real production traffic — any security regression in the canary image is a real, live exposure to real users, not a staging-only risk, reinforcing the value of automated rollback triggers tied to error-rate/security-signal metrics rather than purely manual observation.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                | Likely Cause                                                                                     | Resolution Path                                                                                         |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| "Canary" Pods are receiving far more or less traffic than expected     | Traffic is being distributed per-Pod by a standard Service, not by a genuine weighted split      | Use an Ingress/Gateway API/service-mesh traffic-splitting mechanism instead of relying on replica ratio |
| Brief outage occurred during a deploy that should've had none          | `strategy.type: Recreate` was used (or defaulted incorrectly) for a workload that didn't need it | Switch to `RollingUpdate` with an appropriate `maxUnavailable`/`maxSurge`                               |
| Blue/Green cutover done, but old environment still consuming resources | Old-color Deployment was never scaled down/deleted after cutover                                 | Scale down or delete the retired-color Deployment once the new color is confirmed stable                |

## 9. Best Practices

- Default to `RollingUpdate` with `maxUnavailable: 0` for user-facing services; reserve `Recreate` explicitly for workloads with a genuine version-incompatibility constraint, and document why when it's used.
- Treat "Blue/Green" and "Canary" as architecture decisions requiring explicit extra infrastructure (duplicate Deployments, traffic-splitting Ingress/Gateway/mesh, or a progressive-delivery controller) — never describe a paused `RollingUpdate` as a true canary in design docs or postmortems.
- For genuine progressive delivery at scale, adopt a dedicated controller (Argo Rollouts, Flagger — §88, Part 11) rather than hand-rolling traffic-splitting logic, since automated metric-based promotion/rollback is much harder to get right manually than it first appears.

## 10. Common Anti-Patterns / Mistakes

- **Calling a manually-paused `RollingUpdate` a "canary deployment"** in documentation or postmortems, when it provides no actual traffic-percentage control — a real source of miscommunication during incident response.
- **Using `Recreate` by habit or misunderstanding rather than a genuine version-incompatibility requirement**, introducing avoidable downtime on workloads that would have deployed safely with `RollingUpdate`.
- **Leaving retired Blue/Green environments running indefinitely** after a successful cutover, quietly doubling infrastructure cost with no corresponding benefit.

## 11. Interview Questions

**🎯 Beginner:** _"What are the two native Deployment strategy types in Kubernetes, and how do they differ?"_
**Model answer:** `RollingUpdate` (the default) incrementally replaces old Pods with new ones, allowing a controlled, temporary overlap of both versions with no downtime for workloads that can run more than one replica. `Recreate` terminates all old Pods first and only then creates new ones, guaranteeing the two versions never run simultaneously, at the cost of a downtime window between the two.
_What the interviewer is probing for:_ Basic, correct recall of the only two values Kubernetes actually supports natively.

**🎯 Intermediate:** _"Are Blue/Green and Canary built-in Kubernetes Deployment strategies? If not, how are they actually implemented?"_
**Model answer:** No — `spec.strategy.type` only accepts `RollingUpdate` or `Recreate`. Blue/Green and Canary are architectural patterns built on top of those primitives: Blue/Green typically runs two full, separate Deployments (old and new versions both fully live) and cuts traffic over instantly by changing a Service's label selector or an Ingress/Gateway rule, giving instant rollback by flipping it back. Canary similarly runs a small second Deployment alongside the main one, with traffic split between them by percentage using an Ingress, Gateway API, or service mesh — or more robustly, using a dedicated controller like Argo Rollouts or Flagger that automates the traffic-shifting and promotion/rollback decisions based on live metrics.
_What the interviewer is probing for:_ Precise understanding that these patterns require additional infrastructure Kubernetes doesn't provide out of the box — a very commonly confused point.

**🎯 Senior:** _"A team says they're running canary deployments using `kubectl rollout pause` after 10% of replicas have updated. What's actually happening, and what's the gap versus a 'real' canary?"_
**Model answer:** What's actually happening is that roughly 10% of the Deployment's Pods are running the new version while the rollout is paused mid-way — but a standard Service load-balances across all Pods matching its selector without regard to version, so this does not guarantee 10% of _traffic_ goes to the new version; it only guarantees 10% of _replicas_ exist. Under uneven request patterns, keep-alive connection reuse, or session affinity, actual traffic split can differ significantly from the replica ratio. A "real" canary needs a traffic-aware routing layer — Ingress/Gateway API weighted routing or a service mesh — to control the actual percentage of requests, plus ideally automated metric-driven promotion/rollback rather than a human manually deciding when to resume or abort based on limited signal.
_What the interviewer is probing for:_ Ability to identify the specific technical gap between a manual approximation and genuine traffic-weighted canary delivery — a sign of hands-on production experience, not just terminology.

**🎯 Architect:** _"You're designing progressive-delivery strategy for a platform serving many teams with varying risk tolerance. How do you decide when RollingUpdate alone is sufficient versus when to invest in Blue/Green or Canary tooling?"_
**Model answer:** I'd start from RollingUpdate as the default for the majority of stateless services with reasonable readiness probes and a tolerant blast radius — it's zero-extra-infrastructure and handles the common case well. I'd reserve Blue/Green for services where instant, guaranteed rollback matters more than infrastructure cost — often externally-facing, high-visibility services, or ones fronting breaking data-layer changes where even RollingUpdate's brief overlap is unacceptable, accepting the cost of running duplicate full-scale environments during transitions. I'd invest in genuine Canary tooling (Argo Rollouts or Flagger, §88) specifically for services with rich enough telemetry (error rates, latency percentiles) to drive automated promotion/rollback decisions, since a canary without solid metrics to gate on is really just a slower, riskier RollingUpdate with extra steps. The overall framework is matching the sophistication of the deployment pattern to both the blast radius of a bad release and the team's actual observability maturity — over-investing in Canary tooling for a low-risk internal service is wasted complexity, just as under-investing for a high-risk, high-traffic service is a real production risk.
_What the interviewer is probing for:_ Whether the candidate can build a decision framework balancing risk, cost, and organizational tooling maturity, rather than defaulting to "always use the most sophisticated pattern available."

## 12. Common Misconceptions

1. **"Blue/Green and Canary are values you can set in `spec.strategy.type`."** Only `RollingUpdate` and `Recreate` are valid native values; Blue/Green and Canary are patterns implemented with additional Deployments and traffic-control mechanisms.
2. **"Pausing a RollingUpdate partway through is the same as a canary deployment."** It controls replica count exposure, not traffic percentage — a standard Service doesn't weight traffic by version, so actual request distribution can differ meaningfully from the replica ratio.
3. **"`Recreate` is just an inferior, legacy option that should never be used."** It's the correct choice specifically when two application versions genuinely cannot coexist safely against shared state (e.g., certain breaking schema migrations).
4. **"Blue/Green is strictly better than RollingUpdate since rollback is instant."** It comes at the real cost of running full duplicate infrastructure for both versions during the transition — a legitimate tradeoff, not a strictly dominant choice.

## 13. 🔑 Key Takeaways

- Kubernetes Deployments natively support exactly two strategies: `RollingUpdate` (default, incremental, no-downtime-capable) and `Recreate` (full teardown before rebuild, guarantees no version overlap, incurs downtime).
- `maxUnavailable` and `maxSurge` under `RollingUpdate` let operators tune the exact tradeoff between capacity dips and resource surge during a rollout.
- Blue/Green and Canary are patterns, not built-in strategy values — they require extra Deployments and a traffic-control mechanism (Service selector swap, Ingress/Gateway weighting, or service mesh) external to the Deployment object itself.
- A manually-paused RollingUpdate approximates canary-style partial exposure by replica count only, not genuine traffic-percentage control — a frequently confused distinction.
- Production-grade progressive delivery (automated, metric-driven Canary/Blue-Green) is typically implemented with dedicated tooling like Argo Rollouts or Flagger (§88, Part 11), built on top of the same Deployment/ReplicaSet foundation covered in §27–§28.

## 14. Related Concepts & What's Next

§27 and §28 established the ReplicaSet-swap mechanics that every strategy in this section ultimately relies on. §88 (Part 11) covers the GitOps and progressive-delivery tooling (ArgoCD, Flux, and by extension controllers like Argo Rollouts and Flagger) that automates genuine Canary and Blue/Green patterns at scale, well beyond what a bare Deployment or manual `kubectl rollout pause` can achieve. §30 shifts focus to the labeling and selection mechanisms — labels, selectors, and annotations — that every strategy in this section depends on for correctly routing traffic between Pod versions.

**Next Section:** §30 — `Section-30-Part4-Labels-Selectors-Annotations.md`
