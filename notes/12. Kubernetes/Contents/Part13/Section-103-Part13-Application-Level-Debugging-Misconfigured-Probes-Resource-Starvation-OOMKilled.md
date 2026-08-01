# Section 103 (Part 13): Application-Level Debugging (Misconfigured Probes, Resource Starvation, OOMKilled)

## 1. Definition

**Plain language:** A Pod can be perfectly scheduled, its networking correctly wired (§101), and its storage correctly mounted (§102), and still be broken — because the application inside the container is misbehaving, or because the container was never given enough CPU or memory to do its job in the first place. This section is about diagnosing failures that live entirely inside the container boundary: a probe configured against the wrong endpoint or the wrong port, a container repeatedly killed for exceeding its memory limit, and a Pod that's technically "running" but is so starved of CPU that it can't do useful work.

**Precise definition:** **Application-level debugging** is the practice of diagnosing failures whose root cause lives inside the container's own runtime behavior rather than in cluster infrastructure — specifically, **misconfigured liveness/readiness/startup probes** (§89) that kill or de-register a healthy container, or fail to catch a genuinely unhealthy one; **OOMKilled** terminations, where the kernel's cgroup memory controller kills a container's process for exceeding its memory limit, reported by Kubernetes with exit code `137` and reason `OOMKilled`; and **CPU starvation**, where a container's CPU limit (or contention with other Pods on an oversubscribed node) throttles it so severely that requests time out or queue up despite the container never crashing. Unlike §101 and §102, which trace failures outward into the network or storage subsystem, this section traces failures inward — into `kubectl describe`, container exit codes, and resource usage metrics.

## 2. Why This Matters

- **A misconfigured probe can turn a perfectly healthy application into a permanently failing one** — a `livenessProbe` pointed at the wrong port, path, or one that checks a downstream dependency (§89) produces symptoms (`CrashLoopBackOff`, a Pod cycling between `Running` and restart) that look exactly like an application bug, sending an engineer down the wrong investigation path entirely.
- **`OOMKilled` is a distinct, specific failure mode with its own exit code and forensic trail** — it is not a generic crash, and confusing it with an application-level exception or a liveness probe failure means reaching for the wrong fix (adjusting probe timing, or debugging application logic) when the actual fix is raising the memory limit, fixing a memory leak, or right-sizing the request/limit (§46).
- **CPU starvation is the hardest of the three to notice, because the container never crashes or restarts** — a Pod stuck at `100%` of a low CPU limit simply serves every request slowly, and without checking `kubectl top pod` or CPU throttling metrics, this can be misdiagnosed as an application performance bug rather than a resource-configuration issue.

🔑 **Key Takeaway:** These three failure modes — misconfigured probes, `OOMKilled` terminations, and CPU throttling — share the property that the Pod and its containers can appear syntactically correct while the actual problem is runtime behavior or resource sizing, which is why exit codes, restart counts, and resource usage metrics (not just object YAML) are the primary evidence here.

## 3. Prerequisites and Dependencies

Back-references §89 (Liveness/Readiness/Startup Probes, Part 12) for probe mechanics and failure semantics, and §46 (Resource Requests and Limits, Part 6) for how requests/limits and QoS classes govern OOM and CPU-throttling behavior. Builds on §100 (Part 13's structured troubleshooting methodology) and follows §102 (storage troubleshooting scenarios) as Part 13 moves from infrastructure-layer troubleshooting into application-level debugging. Forwards into §104 (cluster-level resource exhaustion and eviction).

## 4. Architecture Diagram

```text
   Three application-level failure modes and their evidence trail

   1) Misconfigured probe
   ┌───────────────────────────────────────────────────────────────┐
   │  livenessProbe → httpGet /health on port 9090                 │
   │  App actually listens on port 8080, and only serves /healthz  │
   │                          │                                    │
   │                          ▼                                    │
   │  kubelet: probe fails every period → container killed         │
   │  kubectl get pod → CrashLoopBackOff (app was never unhealthy) │
   └───────────────────────────────────────────────────────────────┘

   2) OOMKilled
   ┌───────────────────────────────────────────────────────────────┐
   │  Container memory usage climbs → hits spec.limits.memory      │
   │                          │                                    │
   │                          ▼                                    │
   │  Linux cgroup OOM killer sends SIGKILL to the process         │
   │                          │                                    │
   │                          ▼                                    │
   │  kubectl get pod → State: Terminated, Reason: OOMKilled       │
   │                    ExitCode: 137                              │
   └───────────────────────────────────────────────────────────────┘

   3) CPU starvation (no crash at all)
   ┌───────────────────────────────────────────────────────────────┐
   │  Container CPU limit: 100m, actual demand: 400m under load    │
   │                          │                                    │
   │                          ▼                                    │
   │  CFS quota throttles the process every scheduling period      │
   │  Pod stays Running, RESTARTS: 0 — but requests queue/time out │
   └───────────────────────────────────────────────────────────────┘
```

- Scenario 1's key signal is that `kubectl describe pod` shows the probe's configured target (port, path) diverging from what the application actually exposes — the fix is in the probe spec, not the application.
- Scenario 2's key signal is the specific pairing of exit code `137` and `Reason: OOMKilled` in `kubectl describe pod`'s `Last State` block — this pairing is unambiguous and never means anything other than a memory-limit kill.
- Scenario 3's key signal is the _absence_ of any crash or restart combined with degraded latency — `kubectl top pod` and CPU throttling metrics, not `kubectl describe`, are the tools that surface this one.

## 5. Hands-On

### 5.1 Diagnosing a Misconfigured Probe Causing False-Positive Restarts

**Purpose:** Distinguish a genuinely unhealthy application from one being killed by a probe pointed at the wrong target.

**Syntax:**

```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl logs <pod-name> -n <namespace> --previous
```

**Example usage:**

```bash
$ kubectl get pod payments-api-6c9f8d-x2k9p
NAME                        READY   STATUS             RESTARTS   AGE
payments-api-6c9f8d-x2k9p   0/1     CrashLoopBackOff   6          8m

$ kubectl describe pod payments-api-6c9f8d-x2k9p | grep -A6 "Liveness\|Last State"
    Liveness:  http-get http://:9090/health delay=10s timeout=1s period=10s #success=1 #failure=3
Last State:    Terminated
  Reason:      Error
  Message:     Killed by liveness probe

$ kubectl logs payments-api-6c9f8d-x2k9p --previous | tail -5
2026-07-31T10:02:14Z INFO  server listening on :8080
2026-07-31T10:02:14Z INFO  serving health checks at /healthz
```

**Production usage example:** The application logs show it started successfully, listening on port `8080` and serving `/healthz` — but the `livenessProbe` is configured against port `9090` and path `/health`, both wrong; the application was never unhealthy, it was killed repeatedly by a probe that could never have succeeded, and the fix is correcting the probe spec, not touching the application at all.

**Common errors:** Assuming `CrashLoopBackOff` always means an application bug and going straight to application logs without first checking `kubectl describe pod`'s `Liveness:` line against what the application logs actually say it's listening on — the mismatch is visible in seconds once both are compared side by side.

### 5.2 Confirming and Resolving an OOMKilled Container

**Purpose:** Identify an `OOMKilled` termination definitively (versus another crash type) and choose between raising the limit and fixing an actual memory leak.

**Syntax:**

```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl top pod <pod-name> -n <namespace> --containers
```

**Example usage:**

```bash
$ kubectl describe pod report-worker-7d8f9-p2m1x | grep -A8 "Last State"
Last State:     Terminated
  Reason:       OOMKilled
  Exit Code:    137
  Started:      Fri, 31 Jul 2026 09:40:02 +0000
  Finished:     Fri, 31 Jul 2026 09:58:47 +0000

$ kubectl get pod report-worker-7d8f9-p2m1x -o jsonpath='{.spec.containers[0].resources}'
{"limits":{"memory":"256Mi"},"requests":{"memory":"128Mi"}}

$ kubectl top pod report-worker-7d8f9-p2m1x --containers
POD                          NAME      CPU(cores)   MEMORY(bytes)
report-worker-7d8f9-p2m1x    worker    45m          251Mi
```

**Production usage example:** The container ran for roughly 18 minutes before being killed, and `kubectl top pod` on a freshly restarted replica shows memory climbing steadily toward the `256Mi` limit rather than starting high and staying flat — that growth pattern is the signature of an actual memory leak in the application, not simply an under-provisioned limit, so the durable fix is profiling the application's memory usage rather than just raising `limits.memory` (which would only delay the same kill).

**Common errors:** Reflexively doubling `limits.memory` every time an `OOMKilled` occurs without checking whether memory usage is climbing over time (a leak) versus consistently near the limit under normal load (genuine under-provisioning) — the two require entirely different fixes, and treating a leak as a sizing problem just delays the next incident.

### 5.3 Identifying CPU Starvation Without Any Crash

**Purpose:** Recognize degraded performance caused by CPU throttling when the Pod shows zero restarts and reports `Running` the entire time.

**Syntax:**

```bash
kubectl top pod <pod-name> -n <namespace>
kubectl exec <pod-name> -- cat /sys/fs/cgroup/cpu.stat
```

**Example usage:**

```bash
$ kubectl top pod checkout-api-9f7c2-k8m4n
NAME                        CPU(cores)   MEMORY(bytes)
checkout-api-9f7c2-k8m4n    100m         180Mi

$ kubectl get pod checkout-api-9f7c2-k8m4n -o jsonpath='{.spec.containers[0].resources.limits.cpu}'
100m

$ kubectl exec checkout-api-9f7c2-k8m4n -- cat /sys/fs/cgroup/cpu.stat | grep throttled
nr_throttled 4821
throttled_usec 38452019
```

**Production usage example:** `kubectl top pod` shows the container pegged at exactly its `100m` CPU limit, and the container's own `cpu.stat` shows tens of thousands of throttled periods — the Pod has zero restarts and reports `Running` throughout, but every request is competing for a CPU allowance far below what the application actually needs under real load; the fix is raising `resources.limits.cpu` (and likely `requests.cpu`, §46) to match observed demand, not debugging the application code for a "performance regression" that doesn't exist.

**Common errors:** Treating a Pod's `Running` status and zero restart count as proof that resource limits aren't the problem — CPU starvation produces no restart at all, unlike `OOMKilled`, which is exactly why `kubectl top pod` and cgroup throttling stats must be checked explicitly rather than inferred from Pod status.

## 6. Production Usage Notes

- **`kubectl describe pod`'s `Last State` block is the single most reliable source of truth for distinguishing these failure modes** — `Reason: OOMKilled` with `Exit Code: 137` is unambiguous, and should always be checked before assuming a `CrashLoopBackOff` is a probe or application-code issue.
- **Memory usage trend, not a single snapshot, is what separates a leak from under-provisioning** — capturing `kubectl top pod` at multiple points across a container's lifetime (or graphing it via the metrics pipeline, §92, Part 12) is far more diagnostic than one-off checks.
- **CPU throttling is invisible to `kubectl get pod` and `kubectl describe pod` alike** — it only surfaces through `kubectl top pod`, cgroup `cpu.stat`, or a metrics dashboard, making it the easiest of the three failure modes to overlook during a fast triage pass.

## 7. Security Considerations

- Application logs pulled during probe misdiagnosis (`kubectl logs --previous`) can contain sensitive request payloads or credentials if the application logs verbosely — treat log access with the same care given to any other production data source.
- `kubectl exec` into a container to inspect `/sys/fs/cgroup` (Scenario 3) requires `exec` RBAC permission on Pods, which is effectively equivalent to shell access inside the container — this should be scoped as tightly as any other production `exec` permission (§75, Part 10).
- An overly permissive `livenessProbe` fix (removing the probe entirely to "make CrashLoopBackOff stop") trades a false-positive restart problem for the much worse risk of a genuinely hung container never being detected or restarted at all — the correct fix is always to correct the probe target, never to remove it.

## 8. Common Troubleshooting Scenarios

| Symptom                                                            | Cause                                                                        | Fix                                                                                          |
| ------------------------------------------------------------------ | ---------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------- |
| `CrashLoopBackOff` but application logs show a clean startup       | `livenessProbe`/`readinessProbe` pointed at the wrong port or path           | Correct the probe's `port`/`path` to match what the application actually exposes             |
| `Last State: Terminated`, `Reason: OOMKilled`, `Exit Code: 137`    | Container memory usage exceeded `resources.limits.memory`                    | Determine leak vs. under-provisioning via memory trend, then fix the leak or raise the limit |
| Pod `Running`, zero restarts, but consistently slow responses      | CPU throttling — `resources.limits.cpu` too low for real demand              | Raise `requests`/`limits.cpu` (§46) to match observed usage from `kubectl top pod`           |
| Liveness probe passes intermittently, restarts happen sporadically | Probe `timeoutSeconds` too aggressive for an endpoint with variable latency  | Increase `timeoutSeconds` and/or `failureThreshold` to tolerate real-world latency variance  |
| Readiness never turns healthy, Pod never receives traffic          | `readinessProbe` checks a dependency (DB, cache) that itself isn't ready yet | Confirm dependency health first; don't restart the Pod, since readiness failures never do so |

## 9. Best Practices

- Always cross-check a probe's configured `port`/`path` against what the application logs report it's actually listening on before assuming a `CrashLoopBackOff` is an application bug.
- Treat `OOMKilled` as a two-branch diagnosis every time — check the memory usage trend to determine whether the fix is raising the limit or fixing a leak, rather than defaulting to one or the other.
- Include `kubectl top pod` and CPU throttling metrics in every application-level triage, even when the Pod shows zero restarts, since CPU starvation produces no crash signal at all.

## 10. Common Anti-Patterns / Mistakes

- **Assuming `CrashLoopBackOff` always means an application bug** without first comparing the probe's configured target against what the application logs show it's actually serving.
- **Doubling `resources.limits.memory` reflexively after every `OOMKilled`** without checking whether usage is climbing over time (a leak) versus flat near the limit (genuine under-provisioning).
- **Ruling out resource constraints because a Pod shows zero restarts** — CPU starvation degrades performance without ever crashing or restarting the container, so restart count alone is not sufficient evidence.

## 11. Interview Questions

**🎯 Beginner:** _"A Pod is stuck in `CrashLoopBackOff`, but its application logs show it started up cleanly with no errors. What would you check next?"_
**Model answer:** I'd run `kubectl describe pod` and look at the `Liveness:` probe configuration and the `Last State` block — if the reason shows something like "Killed by liveness probe," the application itself likely isn't the problem at all. I'd then compare the probe's configured port and path against what the application logs say it's actually listening on and serving; a mismatch there means the probe is killing a healthy container, and the fix is correcting the probe spec, not debugging application code that was never broken.
_What the interviewer is probing for:_ Knowing to check probe configuration against actual application behavior before assuming a crash loop is an application-level bug.

**🎯 Intermediate:** _"How do you tell whether an `OOMKilled` container needs a higher memory limit or has an actual memory leak?"_
**Model answer:** A single snapshot of memory usage isn't enough — I'd look at the memory usage trend across the container's lifetime, either via `kubectl top pod` sampled repeatedly or through the metrics pipeline's historical graphs. If memory climbs steadily over time until it hits the limit, that's the signature of a leak, and raising the limit only delays the identical kill later — the actual fix is profiling and fixing the application. If memory instead reaches a stable plateau near the limit fairly quickly and stays there under normal load, that's genuine under-provisioning, and raising `resources.limits.memory` (with a validated new baseline) is the correct fix.
_What the interviewer is probing for:_ The ability to distinguish two OOMKilled causes that look identical from the exit code alone but require entirely different remediation.

**🎯 Senior:** _"A team reports their API has become slow under load, but `kubectl get pods` shows healthy Pods with zero restarts. Walk through your diagnostic approach."_
**Model answer:** Since there's no crash or restart signal, I wouldn't expect `kubectl describe pod` to show anything meaningful — this points toward CPU throttling rather than a crash-producing failure. I'd run `kubectl top pod` to check current CPU usage against the configured `resources.limits.cpu`, and if usage is pegged at the limit, I'd confirm with the container's own `cpu.stat` (`nr_throttled`, `throttled_usec`) to quantify how much time is actually being spent throttled. If that's confirmed, the fix is raising the CPU request and limit to match real demand under load — this is exactly the failure mode that restart-count-based monitoring alone will never catch, which is why CPU usage and throttling metrics need to be part of the standard triage checklist, not an afterthought reached for only when everything else comes up clean.
_What the interviewer is probing for:_ Recognizing that some resource-starvation failures produce no crash signal at all, and knowing the specific tools (`kubectl top`, `cpu.stat`) needed to surface them.

**🎯 Architect:** _"How would you design alerting so that misconfigured probes, OOMKilled terminations, and CPU throttling are caught before they become user-facing incidents, rather than diagnosed reactively after the fact?"_
**Model answer:** I'd build three distinct alert signals rather than one generic "Pod unhealthy" alert, since these three failure modes have different leading indicators. For probes, I'd alert on elevated restart counts correlated with `Reason: Liveness probe failed` specifically (distinguishable from other restart reasons via the Kubernetes events stream, §96, Part 12), which catches a bad probe rollout quickly after deploy rather than after it's paged someone. For OOMKilled, I'd feed container memory usage over time into the same metrics pipeline (§92, Part 12) and alert on a sustained upward trend approaching the limit — a leading indicator well before the actual kill — rather than only alerting on the `OOMKilled` event itself, which is already the outage. For CPU throttling, I'd alert directly on the `container_cpu_cfs_throttled_periods_total` metric exposed by cAdvisor/kube-state-metrics crossing a meaningful threshold, since restart-count-based monitoring structurally cannot catch this failure mode at all. I'd also fold all three into the same Grafana dashboard (§93, Part 12) so an on-call engineer sees resource-pressure trends alongside probe and restart data in one place, rather than needing to know to check three separate tools during an active incident.
_What the interviewer is probing for:_ Designing proactive, leading-indicator alerting tailored to each failure mode's actual telemetry, rather than one generic health check that can't distinguish between them.

## 12. Common Misconceptions

1. **"`CrashLoopBackOff` always means the application itself is broken."** It frequently means a probe is misconfigured against the wrong port or path, killing a perfectly healthy container.
2. **"Any `OOMKilled` event means the memory limit is simply too low."** It can also mean a genuine memory leak, which raising the limit only delays rather than fixes — the usage trend over time is what distinguishes the two.
3. **"If a Pod shows zero restarts, resource limits aren't the problem."** CPU starvation degrades performance without ever crashing or restarting a container, and only surfaces through `kubectl top pod` or cgroup throttling metrics.
4. **"Removing a flaky liveness probe is an acceptable quick fix."** It trades a false-positive restart problem for the much larger risk of never detecting a genuinely hung container — the correct fix is always to correct the probe's target, not remove it.

## 13. 🔑 Key Takeaways

- A `CrashLoopBackOff` with clean application logs is a strong signal to check the probe's configured port/path against what the application actually exposes, before assuming an application bug.
- `OOMKilled` (exit code `137`) is unambiguous in `kubectl describe pod`'s `Last State` block, but resolving it correctly requires checking the memory usage trend to distinguish a leak from genuine under-provisioning.
- CPU starvation produces no crash or restart at all — `kubectl top pod` and cgroup `cpu.stat` throttling data are required to surface it, since Pod status alone will look entirely healthy.
- Never remove a probe to "fix" restart churn — correct its target instead, since removing it trades a visible false-positive for an invisible, much riskier failure to detect real hangs.
- Application-level debugging depends on exit codes, restart reasons, and resource usage metrics as primary evidence, distinct from the object-state-first approach used for networking (§101) and storage (§102).

## 14. Related Concepts & What's Next

This section builds on §89's probe mechanics and §46's resource requests/limits, applying both to real diagnostic scenarios, and follows §102's storage troubleshooting scenarios as Part 13 moves from infrastructure-layer troubleshooting into application-level debugging. §104, next, zooms out from a single Pod's resource behavior to cluster-wide resource exhaustion and node-level eviction, where the same underlying pressures (memory, CPU) play out across an entire node rather than one container.

**Next Section:** §104 — `Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md`
