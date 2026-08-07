# Section 89 (Part 12): Liveness, Readiness, and Startup Probes

## 1. Definition

**Plain language:** Kubernetes considers a container "up" the instant its process starts and keeps running — but a running process is not the same thing as a healthy, request-serving application. A Java application might start its process in 200ms and then spend 45 seconds loading a cache before it can actually answer a request; a database connection pool might silently die at 3 AM while the main process keeps running untouched. Probes are how Kubernetes closes that gap between "the process exists" and "the process is actually working."

**Precise definition:** A **probe** is a diagnostic check the kubelet ([§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md)) performs periodically against a container, using one of three mechanisms — an **HTTP GET** request (success = 2xx/3xx status code), a **TCP socket** connection attempt (success = connection established), or an **exec** command run inside the container (success = exit code 0). Kubernetes defines three distinct probe types, each answering a different question and each driving different controller behavior: a **livenessProbe** answers "is this container still functioning, or has it deadlocked/hung?" — failure triggers a container restart per `restartPolicy`; a **readinessProbe** answers "is this container ready to receive traffic right now?" — failure removes the Pod's IP from the Endpoints/EndpointSlice object backing any Service ([§50](../Part7/Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md)) targeting it, without restarting anything; and a **startupProbe** answers "has this container finished its (potentially slow) initialization yet?" — while it hasn't succeeded, liveness and readiness probes are suppressed entirely, protecting slow-starting applications from being killed before they ever get a fair chance to start.

## 2. Why This Matters

- **Readiness and liveness solve fundamentally different problems, and conflating them is the single most common probe misconfiguration in production.** A readiness failure should mean "stop sending traffic here temporarily" (e.g., a downstream dependency is briefly unavailable); a liveness failure should mean "this process is unrecoverable without a restart" (e.g., a genuine deadlock). Using one probe definition for both, or using a liveness probe to check downstream dependencies, causes exactly the kind of restart storms this section exists to prevent.
- **A startup probe is the correct fix for an entire historical class of bugs** — before `startupProbe` existed (pre-1.16), engineers were forced to set an unrealistically long `initialDelaySeconds` on the liveness probe itself to accommodate slow-starting applications, which meant a genuinely hung container after startup wouldn't be caught for that entire delay window either.
- **Every Service's routing decision ([§50](../Part7/Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md)) and every rolling update's progress gate ([§28](../Part4/Section-28-Part4-Deployments-Rolling-Updates-Rollbacks-Revision-History.md)) depend directly on readiness probe results** — a Pod without a passing readiness check is never added to a Service's Endpoints, and a Deployment rollout will not proceed past a batch of Pods that never become ready, making probes a load-bearing dependency for two entirely separate subsystems most engineers think of as unrelated to health checking.

🔑 **Key Takeaway:** Liveness probes answer "should this container restart?", readiness probes answer "should this Pod receive traffic right now?", and startup probes answer "has this slow-starting container finished initializing?" — startup probes suppress the other two until they pass, and confusing liveness with readiness (or vice versa) is the most common real-world probe misconfiguration.

## 3. Prerequisites and Dependencies

Builds directly on [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) (Pod Spec Anatomy, Part 4, which introduced `livenessProbe`/`readinessProbe` structurally as fields on a container spec) and [§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md) (kubelet, the component that actually executes every probe check on the node). Back-references [§28](../Part4/Section-28-Part4-Deployments-Rolling-Updates-Rollbacks-Revision-History.md) (Deployments, Part 4, whose rolling update progress gates on readiness) and [§50](../Part7/Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md) (Services, Part 7, whose Endpoints membership gates on readiness). Assumes familiarity with [§88](../Part11/Section-88-Part11-GitOps-Fundamentals-ArgoCD-Flux.md)'s GitOps deployment workflow as the mechanism through which probe configuration typically reaches a cluster.

## 4. Architecture Diagram

```text
┌───────────────────────────────────────────────────────────────────────┐
│                         Container Lifecycle                           │
│                                                                       │
│   Container starts                                                    │
│        │                                                              │
│        ▼                                                              │
│   ┌───────────────────────────────────────────────────┐               │
│   │  startupProbe running (if defined)                │               │
│   │  - liveness/readiness probes SUPPRESSED here      │               │
│   │  - retries up to failureThreshold × periodSeconds │               |
│   └────────────────────┬──────────────────────────────┘               │
│                        │ succeeds                                     │
│                        ▼                                              │
│   ┌─────────────────────────────┐   ┌─────────────────────────────┐   │
│   │   livenessProbe (ongoing)   │   │   readinessProbe (ongoing)  │   │
│   │   "is it still alive?"      │   │   "is it ready for traffic?"│   │
│   │                             │   │                             │   │
│   │   FAIL → kubelet kills      │   │   FAIL → Pod IP removed     │   │
│   │   container → restartPolicy │   │   from Service Endpoints    │   │
│   │   (§24) governs restart     │   │   (§50) — NO restart        │   │
│   └─────────────────────────────┘   └─────────────────────────────┘   │
└───────────────────────────────────────────────────────────────────────┘

Probe mechanisms (any probe type can use any of these):
  httpGet   → 2xx/3xx response code = success
  tcpSocket → connection established = success
  exec      → command exit code 0   = success
```

- **The kubelet, not the API server or a controller, is what actually executes every probe** — probe results are a purely node-local decision reported up through Pod status, which is why a probe misconfiguration only ever affects the specific node running that Pod, never the cluster's control plane.
- **`startupProbe` gating both liveness and readiness is the mechanism's whole point** — without it, a slow-starting container either needs an inflated `initialDelaySeconds` on liveness (delaying real hang detection) or gets killed mid-initialization by an impatient liveness probe.
- **Readiness failures never restart anything** — the container keeps running exactly as it was; only its Pod's membership in Service Endpoints changes, which is precisely why readiness is the safe probe to use for "temporarily can't serve traffic" conditions like a dependency outage.

## 5. Hands-On: Configuring the Three Probe Types

### 5.1 Liveness and Readiness Probes on an HTTP Application

**Purpose:** Define distinct liveness and readiness checks against the same application, reflecting their genuinely different failure semantics.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: web-app
spec:
  containers:
    - name: app
      image: myregistry.example.com/web-app:2.1.0
      ports:
        - containerPort: 8080
      livenessProbe:
        httpGet:
          path: /healthz # cheap, dependency-free check
          port: 8080
        initialDelaySeconds: 10
        periodSeconds: 15
        failureThreshold: 3
        timeoutSeconds: 2
      readinessProbe:
        httpGet:
          path: /ready # may check DB/cache connectivity
          port: 8080
        initialDelaySeconds: 5
        periodSeconds: 10
        failureThreshold: 2
```

**Example usage and expected output:**

```bash
$ kubectl apply -f web-app-pod.yaml
pod/web-app created

$ kubectl get pod web-app
NAME      READY   STATUS    RESTARTS   AGE
web-app   1/1     Running   0          45s

$ kubectl describe pod web-app | grep -A2 "Liveness\|Readiness"
    Liveness:   http-get http://:8080/healthz delay=10s timeout=2s period=15s #success=1 #failure=3
    Readiness:  http-get http://:8080/ready delay=5s timeout=2s period=10s #success=1 #failure=2
```

**Production usage example:** `/healthz` should be a cheap endpoint that only confirms the process's own event loop is responsive — no downstream calls — because a liveness probe checking a downstream dependency causes the container to be killed and restarted for a failure a restart can never fix; `/ready`, by contrast, is exactly the right place to check database or cache connectivity, since a readiness failure only pulls the Pod out of traffic rotation until the dependency recovers.

**Common errors:** Pointing `livenessProbe` at an endpoint that checks database connectivity — a transient database blip then triggers container restarts across the entire Deployment simultaneously, which does nothing to fix the database and instead adds restart churn and cold-start latency on top of an already-degraded dependency.

### 5.2 A startupProbe for a Slow-Initializing Application

**Purpose:** Protect an application with a genuinely slow (but bounded) startup — e.g., a JVM app warming a cache — from being killed by an impatient liveness probe before it finishes initializing.

**Syntax:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: cache-warmer-app
spec:
  replicas: 3
  selector:
    matchLabels:
      app: cache-warmer-app
  template:
    metadata:
      labels:
        app: cache-warmer-app
    spec:
      containers:
        - name: app
          image: myregistry.example.com/cache-warmer-app:1.0.0
          ports:
            - containerPort: 8080
          startupProbe:
            httpGet:
              path: /healthz
              port: 8080
            periodSeconds: 5
            failureThreshold: 30 # 5s × 30 = 150s max startup window
          livenessProbe:
            httpGet:
              path: /healthz
              port: 8080
            periodSeconds: 10
            failureThreshold: 3
          readinessProbe:
            httpGet:
              path: /ready
              port: 8080
            periodSeconds: 10
```

**Example usage and expected output:**

```bash
$ kubectl get pod -l app=cache-warmer-app -w
NAME                                READY   STATUS    RESTARTS   AGE
cache-warmer-app-7d4f9c-x8k2p       0/1     Running   0          20s
cache-warmer-app-7d4f9c-x8k2p       1/1     Running   0          95s
# liveness/readiness only begin evaluating once the startupProbe succeeds
```

**Production usage example:** Setting `failureThreshold: 30` with `periodSeconds: 5` gives the container a 150-second window to pass its startup check before the kubelet gives up and restarts it — a far cleaner expression of intent than the pre-`startupProbe` workaround of setting `livenessProbe.initialDelaySeconds: 150`, which would also blind the liveness probe to a genuine hang for that entire window even on a fast, healthy startup.

**Common errors:** Setting `failureThreshold` too low on a startup probe for an application whose startup time varies under load (e.g., slower during a cold cache after a full cluster restart) — the container gets killed and restarted in a loop precisely when the cluster is already under the most stress, compounding the original problem.

### 5.3 An exec-Based Liveness Probe

**Purpose:** Show the `exec` probe mechanism for containers with no HTTP endpoint at all (e.g., a worker process or a database).

**Syntax:**

```yaml
livenessProbe:
  exec:
    command:
      - sh
      - -c
      - "pg_isready -U postgres"
  initialDelaySeconds: 15
  periodSeconds: 20
  timeoutSeconds: 5
```

**Example usage and expected output:**

```bash
$ kubectl exec postgres-0 -- sh -c "pg_isready -U postgres"
/var/run/postgresql:5432 - accepting connections
```

**Production usage example:** `exec` probes are the standard pattern for databases and message brokers packaged with their own CLI health-check tooling (`pg_isready`, `redis-cli ping`, `mysqladmin ping`) — no application code change is required, since the check runs the same binary already shipped in the container image.

**Common errors:** Using an `exec` probe command that itself has a meaningful startup or connection cost (e.g., spinning up a full client library per invocation) — under load, the probe's own resource consumption can measurably compete with the application it's meant to be checking, especially at a short `periodSeconds`.

## 6. Production Usage Notes

- **`timeoutSeconds` defaults to 1 second, which is frequently too aggressive for anything beyond the cheapest in-memory health check** — a probe endpoint that occasionally takes 1.2 seconds under load will register as failing intermittently for reasons entirely unrelated to actual health, so tuning `timeoutSeconds` deliberately per endpoint's real latency profile matters.
- **`failureThreshold` and `periodSeconds` together define the real detection latency for any probe** — a liveness probe with `periodSeconds: 30` and `failureThreshold: 3` won't trigger a restart until roughly 90 seconds after a genuine hang begins, a tradeoff between fast detection and tolerance for transient blips that should be a deliberate choice, not a default left unexamined.
- **Probes run independently per container in a multi-container Pod ([§25](../Part4/Section-25-Part4-Multi-Container-Pods-Sidecar-Ambassador-Adapter-Patterns.md))** — a sidecar's own liveness probe failing restarts only that sidecar container, not the whole Pod, though a Pod's overall `Ready` condition still requires every container's readiness probe (if defined) to pass.

## 7. Security Considerations

- **Probe endpoints are frequently exposed without authentication**, since the kubelet itself has no mechanism to attach credentials to a probe request — an `httpGet` liveness/readiness path should never double as, or accidentally expose, anything beyond the minimum health signal, since it is effectively an unauthenticated endpoint reachable from the Pod's own network namespace.
- **`exec` probes run inside the container's own security context**, meaning an exec probe command that requires elevated privileges to run correctly can force a container's `securityContext` ([§45](../Part6/Section-45-Part6-SecurityContext-Pod-Container-Level.md)) to be more permissive than the application itself actually needs — prefer HTTP or TCP probes over exec wherever the application exposes an equivalent endpoint.
- **A liveness probe that depends on an external, network-reachable resource is itself a availability risk an attacker (or an unrelated outage) can exploit** — an attacker capable of disrupting that dependency (e.g., flooding a shared database) can indirectly trigger mass container restarts across every Pod whose liveness probe depends on it, which is a strong argument for keeping liveness checks strictly local to the process.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                                                                            | Likely Cause                                                                     | Resolution Path                                                                                         |
| -------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Pod restarts repeatedly right after passing readiness once                                                                                         | Liveness probe checks a downstream dependency that's flaky                       | Move the dependency check to `readinessProbe`; keep `livenessProbe` limited to the process's own health |
| Pod killed during a slow (but legitimate) startup                                                                                                  | No `startupProbe` defined, and `livenessProbe.initialDelaySeconds` set too short | Add a `startupProbe` with a `failureThreshold`/`periodSeconds` window matching real startup time        |
| Pod `Running` but never receives Service traffic                                                                                                   | `readinessProbe` failing, or missing entirely with the app not actually ready    | `kubectl describe pod`, check `Readiness` probe output and Endpoints (`kubectl get endpoints <svc>`)    |
| Rolling update stuck, new Pods never replace old ones ([§28](../Part4/Section-28-Part4-Deployments-Rolling-Updates-Rollbacks-Revision-History.md)) | New Pods never pass their `readinessProbe`                                       | Check readiness probe target and application logs; rollout waits on readiness by design                 |

## 9. Best Practices

- Define separate `livenessProbe` and `readinessProbe` endpoints in the application itself — never reuse one endpoint for both, since their failure semantics (restart vs. remove-from-traffic) are fundamentally different.
- Add a `startupProbe` for any container whose realistic startup time exceeds a few seconds, sized generously enough to tolerate worst-case cold-start conditions, not just the common-case fast path.
- Keep `livenessProbe` logic strictly local (process/event-loop health only) — never let it depend on a downstream service, database, or network call that a restart cannot actually fix.

## 10. Common Anti-Patterns / Mistakes

- **Using the same endpoint for both `livenessProbe` and `readinessProbe`**, collapsing two distinct failure semantics into one and turning transient dependency issues into unnecessary container restarts.
- **Checking downstream dependencies (database, cache, upstream API) inside a liveness probe**, causing restart storms across an entire Deployment when the dependency — not the application — is actually unhealthy.
- **Omitting a `startupProbe` on a slow-starting application and instead inflating `livenessProbe.initialDelaySeconds`** to compensate, which blinds liveness detection to genuine hangs for that entire inflated window even after a fast, healthy startup.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a liveness probe and a readiness probe?"_
**Model answer:** A liveness probe asks "is this container still functioning, or has it hung/deadlocked?" — a failure causes the kubelet to kill and restart the container according to its `restartPolicy`. A readiness probe asks "is this Pod ready to receive traffic right now?" — a failure removes the Pod's IP from the Service's Endpoints so no traffic is routed to it, but the container itself keeps running untouched and no restart happens. They answer different questions and drive completely different remediation actions.
_What the interviewer is probing for:_ Clean separation of the two probes' purposes and, critically, that only liveness failures cause restarts.

**🎯 Intermediate:** _"A team's Deployment restarts every Pod almost simultaneously whenever their database has a brief connectivity blip. What's the likely misconfiguration?"_
**Model answer:** Their `livenessProbe` is almost certainly checking database connectivity directly — when the database blips, every Pod's liveness probe fails around the same time, and the kubelet on each node independently kills and restarts its container, turning one transient database issue into a fleet-wide restart storm that does nothing to fix the actual problem and adds cold-start latency on top of it. The fix is moving the database check to the `readinessProbe` instead — a failure there simply pulls Pods out of traffic rotation until the database recovers, with no restart involved, which is the correct response to a dependency issue the process itself didn't cause and a restart can't fix.
_What the interviewer is probing for:_ Practical diagnosis connecting a specific symptom (simultaneous restarts) to the specific misconfiguration (dependency check in liveness) and the correct fix.

**🎯 Senior:** _"How would you size `startupProbe` parameters for an application whose startup time varies meaningfully between a warm and a cold cache?"_
**Model answer:** I'd size `failureThreshold × periodSeconds` to comfortably exceed the worst realistic cold-start time, not the typical warm-start time — under-provisioning this window means the exact scenario most likely to need it (a cold, stressed cluster after a broad restart event) is also the scenario where the startup probe kills containers mid-initialization, compounding the original stress. I'd also keep `periodSeconds` reasonably granular (not overly long) so that fast, healthy startups still transition to liveness/readiness evaluation promptly rather than waiting out most of the window unnecessarily even when everything's fine. If startup time genuinely varies by an order of magnitude between conditions, that's also a signal worth surfacing to the application team — a very high worst-case-to-typical-case startup ratio is often itself a symptom worth investigating rather than something to only compensate for at the probe layer.
_What the interviewer is probing for:_ Understanding that startup probe sizing must account for worst-case, not typical-case, conditions, plus the judgment to flag an underlying variance problem rather than only tuning around it.

**🎯 Architect:** _"Design a probe strategy standard for a platform team to apply across hundreds of heterogeneous services, some HTTP, some gRPC, some queue workers with no network endpoint at all."_
**Model answer:** I'd mandate that every service define at minimum a liveness and a readiness check, with liveness strictly limited to local process/event-loop health (no downstream calls) and readiness allowed to check genuine dependency health, enforced as a policy via a validating admission webhook or policy engine ([§77](../Part10/Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md)) that rejects any Pod spec missing both probes rather than relying on each team remembering. For HTTP/gRPC services, I'd standardize on a shared health-check library exposing consistent `/healthz` and `/ready` conventions (gRPC services using the standard gRPC health-checking protocol rather than a bespoke endpoint) so the platform's tooling and dashboards can assume a uniform contract. For queue workers with no network endpoint, I'd require an `exec` probe against a lightweight CLI check or a small embedded HTTP server exposing just a health endpoint, rather than allowing "no probes at all" as a silent default — a Pod with no readiness probe is treated as ready the instant its container starts, which is a real production risk for any worker whose actual readiness lags container start. I'd size every `startupProbe` against measured worst-case startup telemetry rather than guessed values, and require teams to justify any liveness probe with a `periodSeconds`/`failureThreshold` combination implying more than roughly a minute of detection latency, since silent, slow detection is functionally similar to no liveness probe at all for anything genuinely latency-sensitive.
_What the interviewer is probing for:_ Ability to turn probe best practices into an enforceable, uniform platform standard across heterogeneous workload types, including the non-obvious case of workloads with no natural network endpoint.

## 12. Common Misconceptions

1. **"A failing readiness probe restarts the container, just like liveness."** It never does — readiness only affects Service Endpoints membership; the container keeps running exactly as it was.
2. **"`initialDelaySeconds` on a liveness probe is a reasonable substitute for a `startupProbe`."** It technically can delay the first check, but it also blinds liveness detection to a genuine hang for that entire delay window on every subsequent restart too, not just the first startup — a `startupProbe` avoids that tradeoff entirely.
3. **"A Pod with no readiness probe defined is treated as not-ready until manually checked."** The opposite is true — with no readiness probe, a Pod is considered ready the instant its container starts, which can route traffic to an application that hasn't finished its own internal initialization.
4. **"Liveness and readiness probes should always point at the same endpoint to keep things simple."** Doing so collapses two distinct failure semantics into one, and is a leading cause of restart storms triggered by transient dependency issues that a restart cannot fix.

## 13. 🔑 Key Takeaways

- Liveness probes drive container restarts; readiness probes drive Service Endpoints membership; startup probes suppress both until a slow-starting container finishes initializing.
- Liveness checks should be strictly local to the process — never dependent on a downstream service a restart cannot fix.
- `startupProbe` is the correct modern fix for slow-starting applications, replacing the older, worse workaround of inflating `livenessProbe.initialDelaySeconds`.
- `timeoutSeconds`, `periodSeconds`, and `failureThreshold` together define real-world detection latency and false-positive tolerance, and deserve deliberate tuning per endpoint rather than defaults.
- Both Service traffic routing ([§50](../Part7/Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md)) and Deployment rollout progress ([§28](../Part4/Section-28-Part4-Deployments-Rolling-Updates-Rollbacks-Revision-History.md)) depend directly on readiness probe results, making probes load-bearing well beyond simple health checking.

## 14. Related Concepts & What's Next

This section built on [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md)'s Pod spec anatomy (which introduced probe fields structurally) and [§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md)'s kubelet (the component executing every probe check), and back-referenced [§28](../Part4/Section-28-Part4-Deployments-Rolling-Updates-Rollbacks-Revision-History.md) and [§50](../Part7/Section-50-Part7-Services-ClusterIP-NodePort-LoadBalancer-ExternalName.md) as the two subsystems whose behavior directly depends on readiness probe results. [§90](./Section-90-Part12-kubectl-logs-exec-debug-Ephemeral-Containers.md), next, moves from automated health signals to the manual, human-driven diagnostic tools — `kubectl logs`, `kubectl exec`, `kubectl debug`, and ephemeral containers — that an engineer reaches for once a probe (or an alert) has already flagged that something is wrong.

**Next Section:** [§90](./Section-90-Part12-kubectl-logs-exec-debug-Ephemeral-Containers.md) — `Section-90-Part12-kubectl-logs-exec-debug-Ephemeral-Containers.md`
