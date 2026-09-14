# Section 75 (Part 9): Health Checks and Failover Behavior

## 1. Definition

**Plain language:** A health check is the load balancer repeatedly asking each backend, on its own schedule, "are you still working?" — and only sending real traffic to the backends that answer correctly. When a backend stops answering correctly, the load balancer stops sending it traffic without anyone having to intervene manually, and starts sending traffic to it again once it recovers.

**Precise definition:** A **health check** is a periodic probe a load balancer issues against each backend independently of real client traffic, used to determine whether that backend should remain **in rotation** (eligible to receive traffic) or be marked **unhealthy** and removed from rotation. Health checks are commonly implemented at multiple levels of depth: a **TCP health check** (can a connection even be established on the target port), an **HTTP health check** (does a GET request to a specific path return an expected status code, optionally with expected body content), or a custom **application-level health check** (does the application report that its own dependencies — database, cache, downstream services — are also healthy). The load balancer's **failover behavior** is governed by configurable thresholds: how many consecutive failed checks mark a backend unhealthy (the **unhealthy threshold**), how many consecutive successful checks are required to mark it healthy again (the **healthy threshold**), and how frequently checks run (the **interval**) — together, these determine how quickly a real failure is detected and how quickly a recovered backend rejoins rotation.

> 💡 **Tip:** A health check endpoint answering "yes" should mean "I can actually serve real traffic right now," not just "my process is running." A process that's up but whose database connection pool is exhausted should fail its health check — otherwise the load balancer keeps sending it traffic it cannot actually serve, which is strictly worse than routing around it entirely.

## 2. Why This Matters

- **Health checks are the mechanism that makes "removing a failed backend from rotation" ([§72](Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md)) actually happen automatically.** Without them, a load balancer has no way to know a backend has failed and will keep sending it a share of traffic indefinitely.
- **Threshold tuning is a direct trade-off between failure-detection speed and false-positive risk.** Aggressive thresholds (fail after 1 missed check) detect real failures fast but also flap backends out of rotation on transient blips (a single slow garbage-collection pause); conservative thresholds are more stable but slower to react to genuine outages.
- **The depth of the health check determines what kind of failure it can actually catch.** A TCP-only check confirms the process is listening on a port but says nothing about whether the application can actually serve a request correctly — an application that's accepting connections but returning 500 errors on every request will pass a TCP check while failing every real request.
- **Health checks directly affect deployment safety.** Rolling deployments depend on the load balancer correctly detecting when a newly deployed instance is ready to receive traffic (and pulling the old instance out) — a misconfigured health check can cause a deployment to send live traffic to an instance that isn't actually ready yet.
- **They are one of the most commonly misconfigured pieces of production infrastructure**, precisely because the default settings often don't match a specific application's actual startup time, dependency behavior, or failure modes.

## 3. Prerequisites and Dependencies

This section builds directly on the backend pool and rotation concepts introduced in [§72](Section-72-Part9-Load-Balancing-Fundamentals-Why-and-Where-in-the-Stack.md), and assumes the algorithm behavior described in [§74](Section-74-Part9-Load-Balancing-Algorithms-Round-Robin-Least-Connections-Weighted-Hashing.md) — an algorithm can only select among backends that health checks have already determined are eligible. Basic HTTP status code familiarity (Part 8, [§63](../Part8/Section-63-Part8-HTTP-1-1-Fundamentals-Requests-Responses-Methods-Status-Codes.md)) is assumed for the HTTP health check examples below, and TCP connection establishment (Part 7, [§54](../Part7/Section-54-Part7-Transport-Layer-Purpose-Connection-Oriented-vs-Connectionless.md)-[§55](../Part7/Section-55-Part7-TCP-Three-Way-Handshake-and-Connection-Teardown-FIN-RST.md)) is assumed for the TCP-level check examples.

## 4. Architecture / Conceptual Diagram

```text
                          Load Balancer's independent
                          health-check loop (separate
                          from real client traffic)

    every N seconds  ──►  GET /healthz  ──►  Backend A  ──► 200 OK   ✓ healthy
    (interval)             GET /healthz  ──►  Backend B  ──► 200 OK   ✓ healthy
                           GET /healthz  ──►  Backend C  ──► timeout  ✗ fail #1

    ... N seconds later, next check cycle ...

                           GET /healthz  ──►  Backend C  ──► timeout  ✗ fail #2
                                              (unhealthy_threshold = 2 reached)
                                                     │
                                                     ▼
                                    Backend C marked UNHEALTHY,
                                    removed from rotation. Algorithm (§74)
                                    now only considers A and B.

    ... Backend C recovers ...

                           GET /healthz  ──►  Backend C  ──► 200 OK   ✓ success #1
    ... N seconds later ...
                           GET /healthz  ──►  Backend C  ──► 200 OK   ✓ success #2
                                              (healthy_threshold = 2 reached)
                                                     │
                                                     ▼
                                    Backend C marked HEALTHY again,
                                    rejoins rotation, starts receiving
                                    real client traffic.
```

- The health-check loop runs **continuously and independently** of real client traffic — a backend can be marked unhealthy even during a period with zero real client requests, purely from the health-check probes themselves.
- The **worst-case detection time** for a real failure is roughly `interval × unhealthy_threshold` — tuning these two numbers is the direct lever for how fast a load balancer reacts to a genuine outage.
- Most implementations distinguish **connection-draining/deregistration delay** (letting in-flight requests on a backend being removed finish gracefully, rather than dropping them mid-request) from the health check itself — this is a related but separate configuration, covered further in Production Usage Notes below.

## 5. Hands-On

### 5.1 Configuring an HTTP Health Check in NGINX Plus-Style / Open-Source Passive Checks

**Purpose:** Show a basic active health check configuration and observe a backend being marked down and later recovering.

**Syntax:**

```nginx
upstream backend_pool {
    server 10.0.1.10:8080 max_fails=2 fail_timeout=10s;
    server 10.0.1.11:8080 max_fails=2 fail_timeout=10s;
}
```

**Example usage and expected output:**

```bash
$ curl -s http://lb.internal/health
{"served_by": "10.0.1.10"}

# 10.0.1.10 crashes ...

$ curl -s http://lb.internal/health   # first request after crash may still hit it
curl: (52) Empty reply from server

$ curl -s http://lb.internal/health   # second failure trips max_fails=2
{"served_by": "10.0.1.11"}

$ curl -s http://lb.internal/health   # subsequent requests avoid 10.0.1.10 for fail_timeout=10s
{"served_by": "10.0.1.11"}
```

- Open-source NGINX's `max_fails`/`fail_timeout` implements **passive** health checking — it marks a backend down based on real request failures rather than a dedicated synthetic probe, and retries it again after `fail_timeout` elapses.
- This differs meaningfully from **active** health checking (a dedicated probe hitting a health endpoint on a fixed interval regardless of real traffic), which is available in NGINX Plus and in most cloud load balancers and HAProxy — active checks detect failure even with zero real traffic, which passive checks structurally cannot.

**Production usage example:** Passive checks are a reasonable low-configuration default for internal, low-traffic services; public-facing production services almost universally use active health checks so that a failure is detected even during a lull in real traffic, rather than waiting for the next real request to fail first.

**Common errors:** Relying solely on passive checks for a low-traffic service means a completely dead backend can sit in rotation, silently failing every request it happens to receive, for an unbounded amount of time if requests are infrequent enough that `max_fails` is never actually reached within a reasonable window.

### 5.2 Active HTTP Health Check in HAProxy With Explicit Thresholds

**Purpose:** Demonstrate a fully configured active health check with explicit interval, healthy/unhealthy thresholds — the pattern closest to what cloud load balancers implement natively.

**Syntax:**

```
backend app_pool
    option httpchk GET /healthz
    http-check expect status 200
    default-server inter 5s fall 3 rise 2
    server app1 10.0.1.10:8080 check
    server app2 10.0.1.11:8080 check
```

**Example usage and expected output:**

```bash
$ echo "show stat" | socat stdio /var/run/haproxy.sock | cut -d, -f1,2,18
app_pool,app1,UP
app_pool,app2,DOWN
```

- `inter 5s` sets the check interval to every 5 seconds; `fall 3` means 3 consecutive failures mark the server DOWN; `rise 2` means 2 consecutive successes mark it back UP — worst-case detection time here is roughly 15 seconds (`5s × 3`).
- `option httpchk GET /healthz` with `http-check expect status 200` means HAProxy is actively probing a dedicated health endpoint on its own schedule, independent of real client traffic — this is an active check, unlike the passive example in §5.1.

**Production usage example:** This exact pattern — a dedicated `/healthz` (or `/health`, `/ready`) endpoint checked on a short interval with a small fall/rise threshold — is close to universal across production HTTP services, and the same conceptual configuration (interval, healthy threshold, unhealthy threshold, timeout) appears under different names in every major cloud load balancer product ([§80](Section-80-Part9-Cloud-Load-Balancer-Types-ALB-NLB-Azure-LB-App-Gateway-GCP-LB-Conceptual.md)).

**Common errors:** Pointing the health check at the same path as the actual application's primary endpoint (rather than a dedicated lightweight `/healthz`) means the health check itself consumes real capacity and can be affected by the same slowness or dependency issues it's supposed to be detecting cleanly — a dedicated, minimal-dependency health endpoint is the standard mitigation.

### 5.3 Testing a Health Check Endpoint Directly

**Purpose:** Verify what the load balancer's health check actually sees, independent of the load balancer itself — a critical debugging step when backends are unexpectedly marked unhealthy.

**Syntax:**

```bash
curl -sv http://<backend-ip>:<port>/healthz
```

**Example usage and expected output:**

```bash
$ curl -sv http://10.0.1.10:8080/healthz
> GET /healthz HTTP/1.1
> Host: 10.0.1.10:8080
>
< HTTP/1.1 503 Service Unavailable
< Content-Type: application/json
{"status": "unhealthy", "reason": "database connection pool exhausted"}
```

- Hitting the health endpoint directly, bypassing the load balancer entirely, isolates whether the failure is in the backend's actual health logic (as shown here — a legitimate application-reported failure) versus a load-balancer-side configuration problem (wrong path, wrong port, wrong expected status code).

**Production usage example:** This is the standard first diagnostic step whenever a load balancer reports a backend as unhealthy unexpectedly — confirming what the backend's health endpoint genuinely returns, directly and without the load balancer as an intermediary, immediately narrows the investigation to either the application's own health logic or the load balancer's check configuration.

**Common errors:** Testing the health endpoint from a workstation outside the backend's network (through a different path than the load balancer uses) can produce a misleadingly different result if there's a firewall rule, security group, or network path that treats the load balancer's source differently than an ad hoc test client's source.

## 6. Production Usage Notes

- **Deregistration delay (connection draining) is a separate but related setting from the health check itself** — when a backend is marked unhealthy or intentionally removed (during a deployment), a well-configured load balancer allows in-flight requests already sent to that backend to finish before fully removing it, rather than abruptly dropping active connections.
- **Health check endpoints should avoid deep, expensive dependency checks on every single probe** — a health check that queries a downstream database on every 5-second interval, from every load balancer node, can itself become a meaningful load source; shallow "am I running and can I serve" checks with a separate, less frequent deep dependency check are a common compromise.
- **Startup/warm-up behavior matters as much as failure detection.** A newly launched backend often needs a grace period (or a distinct "initial delay" setting before the first health check even runs) to finish warming caches, establishing connection pools, or JIT-compiling before it's actually ready to serve production-level load, even if it would technically pass a basic health check immediately.

## 7. Security Considerations

- Health check endpoints, if publicly reachable, can leak internal state (database connectivity, downstream service names, internal error details) to anyone who can reach them — health endpoints should generally be reachable only from the load balancer's network path, not from the public internet directly.
- An attacker able to reach and manipulate a health check endpoint directly (in a misconfigured network where it's exposed) could potentially force a backend to report unhealthy repeatedly, creating an easy, low-effort denial-of-service vector against the service's own capacity.
- Health checks that require authentication add complexity but prevent a completely unauthenticated endpoint from existing on every backend — where feasible, restricting health check reachability to the load balancer's specific source IP/subnet (via security group or firewall rule, [§84](../Part10/Section-84-Part10-Security-Groups-vs-Network-ACLs-Cloud-Agnostic-Concepts.md)) is a low-cost mitigation.

## 8. Common Troubleshooting Scenarios

| Symptom                                                            | Likely Cause                                                                                     | Resolution Path                                                                                                    |
| ------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Backend flaps in and out of rotation repeatedly                     | Health check thresholds too aggressive (low fall count) for normal transient latency variance        | Increase unhealthy threshold and/or interval to tolerate brief blips without full removal from rotation             |
| Newly deployed backend never receives traffic despite appearing to run | Health check runs before the application has finished warming up/establishing dependencies           | Add a startup grace period or initial delay before health checks begin; verify actual readiness at expected startup time |
| A backend serving errors is still receiving traffic                 | Health check is too shallow (TCP-only, or an HTTP check that doesn't verify true readiness)           | Deepen the health check to a meaningful HTTP endpoint that reflects real serviceability, not just process liveness   |
| Removing a backend during deployment causes dropped in-flight requests | No connection draining/deregistration delay configured before the backend is fully removed          | Configure a deregistration delay/connection draining window sufficient for typical in-flight request duration       |

## 9. Best Practices

- Implement a dedicated, lightweight health check endpoint (`/healthz` or equivalent) distinct from real application endpoints, and have it reflect genuine serviceability — not just process liveness — without incurring expensive per-check cost.
- Tune interval and threshold values to the specific application's actual failure and recovery characteristics, rather than accepting defaults uncritically; document the intended worst-case detection time (`interval × unhealthy_threshold`) as an explicit, known trade-off.
- Always configure connection draining/deregistration delay alongside health checks so that removing a backend (for failure or planned deployment) doesn't abruptly terminate in-flight requests.

## 10. Common Anti-Patterns / Mistakes

- **Using the application's primary business endpoint as the health check target.** This makes the health check subject to the same load, dependency slowness, or partial-degradation conditions it's meant to detect cleanly, and can itself add meaningful load to the very endpoint under stress.
- **Setting unhealthy thresholds so aggressive that transient latency blips repeatedly remove healthy backends from rotation.** This reduces effective capacity and can create a self-reinforcing cascade where remaining backends absorb more load, become slower, and get removed themselves.
- **Deploying new backend versions without a startup grace period, then blaming the load balancer for routing traffic to instances that "aren't ready."** The load balancer only knows what the health check tells it — if the check runs before the application signals true readiness, this is a configuration gap, not a load balancer defect.

## 11. Interview Questions

**🎯 Beginner:** _"What is a health check, in the context of a load balancer?"_
**Model answer:** A health check is a periodic probe the load balancer sends to each backend server, independent of real client traffic, to determine whether that backend is currently able to serve requests. If a backend fails enough consecutive checks, the load balancer stops sending it real traffic until it starts passing checks again.
_What the interviewer is probing for:_ Basic understanding that health checks are separate from real traffic and drive the in/out-of-rotation decision.

**🎯 Intermediate:** _"What's the difference between a TCP health check and an HTTP health check, and when would you use each?"_
**Model answer:** A TCP health check just confirms a connection can be established on the target port — it verifies the process is listening but says nothing about whether the application can actually process a request correctly. An HTTP health check sends an actual HTTP request to a specific path and checks the response status code (and optionally body content), which verifies real application-level readiness, not just that a socket is open. I'd use TCP checks for non-HTTP protocols or extremely simple services where port-listening genuinely correlates with readiness, and HTTP checks for anything where the application could be technically running but functionally broken — for example, up and listening but unable to reach its database.
_What the interviewer is probing for:_ Understanding that check depth determines what kind of failure it can actually catch, not just familiarity with the two check types by name.

**🎯 Senior:** _"Your team set health check thresholds to fail after a single missed check, to detect outages as fast as possible. What's the risk, and how would you rebalance this?"_
**Model answer:** A single-failure threshold reacts extremely fast to genuine outages, but it also has essentially zero tolerance for transient blips — a single slow garbage collection pause, a brief network hiccup, or momentary CPU contention on an otherwise healthy backend can trip it and pull a perfectly good backend out of rotation. That reduces effective capacity unnecessarily and, in the worst case, can create a flapping cycle where a backend is repeatedly removed and re-added, each transition adding its own overhead. I'd rebalance by requiring a small number of consecutive failures (commonly two or three) before marking a backend unhealthy, while keeping the check interval itself reasonably short — this preserves fast detection of genuinely persistent failures while tolerating single transient blips. The right numbers depend on the application's real latency variance, which I'd derive from actual observed metrics rather than guessing.
_What the interviewer is probing for:_ Whether the candidate understands the detection-speed-versus-false-positive trade-off concretely, rather than reflexively treating "faster failure detection" as an unambiguous good.

**🎯 Architect:** _"You're designing health checks for a service with a genuinely slow startup process (a large in-memory cache that takes 90 seconds to warm on boot). How do you prevent the load balancer from sending traffic to instances before they're truly ready, without slowing down failure detection for already-running instances?"_
**Model answer:** I'd separate the concerns explicitly: a startup grace period (sometimes called an initial delay or warm-up period) that prevents the health check from even running, or from being able to mark the instance healthy, until the known minimum startup time has elapsed — this directly addresses the slow-startup case without touching steady-state failure-detection speed at all. Once past that grace period, the instance is subject to the normal interval/threshold configuration tuned for fast detection of a genuine post-startup failure. I'd also make the health check itself readiness-aware rather than just liveness-aware — the application should track its own internal "cache warmed and ready" state and have the health endpoint reflect that directly, rather than the load balancer inferring readiness purely from elapsed time, since elapsed time is a proxy that can be wrong if warm-up is occasionally slower than the configured grace period. This separates "is the process minimally alive" (liveness) from "is the process actually ready to serve real traffic" (readiness) as genuinely distinct signals, a distinction that maps directly onto the same liveness/readiness split used in Kubernetes probes ([§111](../Part13/Section-111-Part13-The-Kubernetes-Networking-Model-Pod-to-Pod-Service-and-Ingress-Concepts.md)).
_What the interviewer is probing for:_ The ability to design around a genuine constraint (slow startup) without sacrificing steady-state responsiveness, and awareness of the liveness/readiness conceptual split as a general pattern beyond one specific tool.

## 12. Common Misconceptions

1. **"A health check passing means the application is fully healthy."** It only confirms whatever the specific check actually verifies — a shallow TCP or minimal HTTP check can pass while the application is functionally degraded in ways the check never examines.
2. **"Health checks and connection draining are the same setting."** They're related but distinct: health checks determine when a backend is marked unhealthy; connection draining determines how gracefully an already-marked-for-removal backend finishes its in-flight work before being fully removed.
3. **"Faster failure detection (lower thresholds) is always strictly better."** Aggressive thresholds increase false-positive risk and can cause flapping, reducing effective capacity and stability for backends that are actually fine.
4. **"Health check endpoints don't need to be secured since they just return a status."** They can leak internal architecture details in their response body and, if directly reachable and manipulable, can become a denial-of-service vector against the service's own capacity.

## 13. 🔑 Key Takeaways

- Health checks are periodic, independent probes that determine whether a backend stays in or out of rotation, distinct from real client traffic.
- Check depth (TCP vs. HTTP vs. application-level) determines what kind of failure the check can actually detect — shallow checks can pass while the application is functionally broken.
- Interval and threshold tuning is a direct trade-off between fast failure detection and tolerance for transient blips; worst-case detection time is roughly `interval × unhealthy_threshold`.
- Connection draining/deregistration delay is a separate, complementary setting that prevents abruptly dropping in-flight requests when a backend is removed.
- Startup grace periods and readiness-aware health checks prevent traffic from reaching instances that are technically running but not yet actually ready to serve.

## 14. Related Concepts & What's Next

[§74](Section-74-Part9-Load-Balancing-Algorithms-Round-Robin-Least-Connections-Weighted-Hashing.md) covers the algorithms that operate over the pool of backends this section's health checks maintain as eligible. [§111](../Part13/Section-111-Part13-The-Kubernetes-Networking-Model-Pod-to-Pod-Service-and-Ingress-Concepts.md) extends the liveness/readiness distinction touched on in the Architect interview question into the Kubernetes-specific probe model. [§80](Section-80-Part9-Cloud-Load-Balancer-Types-ALB-NLB-Azure-LB-App-Gateway-GCP-LB-Conceptual.md) shows how these same health check concepts (interval, threshold, path) are configured concretely across AWS, Azure, and GCP's managed load balancer products.

**Next Section:** [§76](Section-76-Part9-SSL-TLS-Termination-and-Passthrough-Patterns.md) — `Section-76-Part9-SSL-TLS-Termination-and-Passthrough-Patterns.md`
