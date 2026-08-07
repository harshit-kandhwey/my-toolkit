# Section 98 (Part 13): Pod Failure States: CrashLoopBackOff, ImagePullBackOff, Pending, Evicted

## 1. Definition

**Plain language:** `kubectl get pods` reports a small, fixed vocabulary of failure states — `CrashLoopBackOff`, `ImagePullBackOff`, `Pending`, `Evicted`, and a handful of others — and each one narrows down the possible causes dramatically before any deeper investigation is needed. Knowing precisely what each state means, and what it rules out, is the fastest possible first step of the isolation phase described in [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md).

**Precise definition:** A Pod's reported `STATUS` column reflects its **`PodStatus.phase`** combined with per-container **`waiting`/`terminated` reason** fields, and each commonly seen failure state corresponds to a specific, narrow mechanism: **`CrashLoopBackOff`** means a container started, exited (successfully or not), and the kubelet is applying an exponential back-off before the next restart attempt (`restartPolicy: Always`, the default) — the container **did** start at least once. **`ImagePullBackOff`**/**`ErrImagePull`** means the kubelet could not pull the specified image at all — the container **never** started, distinguishing it fundamentally from `CrashLoopBackOff`. **`Pending`** means the Pod object exists in the API server but has not yet been bound to a node, or has been bound but its containers have not yet started — the cause lives with the scheduler or node-level admission, not the container runtime. **`Evicted`** is a **terminal state**, not a restart-eligible one — the kubelet forcibly terminated the Pod under node-level resource pressure (memory, disk) per its eviction manager, and the Pod will not restart on that node; a new Pod (via the owning controller) must be scheduled elsewhere. Applying [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s methodology, each of these four states is itself the output of the ISOLATE step — reading the state correctly already tells you which layer (image registry, scheduler, container runtime, or node resource pressure) to investigate next.

## 2. Why This Matters

- **These four states account for the overwhelming majority of real Pod-failure tickets**, and each one, correctly read, eliminates entire categories of possible cause before a single additional command is run — misreading `ImagePullBackOff` as `CrashLoopBackOff` (or vice versa) sends the whole investigation to the wrong layer from the start.
- **`Evicted` is fundamentally different from the other three in one critical way** — it is not a state the Pod will recover from by itself, no matter how long you wait or how many times you check; recognizing this immediately redirects effort toward the controller replacing the Pod and the node-level pressure that caused it, rather than waiting on a Pod that will never restart.
- **Correctly distinguishing these states is directly assessed on both the CKA (Troubleshooting, 30%) and CKAD (Application Deployment, 20%) exams** — scenario questions frequently present a `kubectl get pods` output and expect the exact next diagnostic command, not a general description of "something's wrong."

🔑 **Key Takeaway:** Each Pod failure state is itself a fast, free isolation signal — `CrashLoopBackOff` means the container started and exited, `ImagePullBackOff` means it never started at all, `Pending` means it never even got assigned to a node, and `Evicted` means it was forcibly terminated by node pressure and will not restart — and reading the state correctly, per [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s ISOLATE step, should always precede reaching for logs or `describe`.

## 3. Prerequisites and Dependencies

Applies [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s structured troubleshooting methodology to the Pod-failure-state category specifically. Back-references [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) (Pod Spec Anatomy, Part 4 — `restartPolicy`, container spec fields) and [§89](../Part12/Section-89-Part12-Liveness-Readiness-Startup-Probes.md) (Probes, Part 12 — liveness probe failures as a common `CrashLoopBackOff` trigger). Sets up [§99](./Section-99-Part13-Debugging-Node-Issues-NotReady-Nodes-kubelet-Failures.md), which applies the same methodology one layer up, at the Node.

## 4. Architecture Diagram

```text
┌──────────────────────────────────────────────────────────────────────────────┐
│         Pod Lifecycle and Where Each Failure State Enters                    │
│                                                                              │
│  Pod created (API server) ──► Scheduled to a node ──► kubelet starts         │
│         │                            │                    containers         │
│         │                            │                        │              │
│         ▼                            ▼                        ▼              │
│    ┌──────────┐               ┌──────────────┐          ┌─────────────┐      │
│    │ PENDING v│               │  PENDING     │          │ Image pull  │      │
│    │ (unsched-│  ◄── stuck    │ (scheduled,  │          │ attempt     │      │
│    │ ulable)  │      here     │  not started)│          └─┬─────────┬─┘      │
│    └──────────┘               └──────────────┘            │         │        |
│                                                     fails │ succeeds│        |
│                                                           ▼         ▼        │
│                                                 ┌────────────┐  ┌─────────┐  │
│                                                 │ImagePull-  │  │Container│  │
│                                                 │BackOff /   │  │ starts  │  │
│                                                 │ErrImagePull│  └───┬─────┘  │
│                                                 └────────────┘      │        │
│                                                            exits ◄──┘        │
│                                                                │             │
│                                                                ▼             │
│                                                        ┌────────────────┐    │
│                                                        │CrashLoopBack-  │    │
│                                                        │Off (restart    │    │
│                                                        │ Policy: Always)│    │
│                                                        └────────────────┘    │
│                                                                              │
│  ── separately, at ANY point, node-level pressure can intervene: ──          │
│                                                                              │
│   Node under memory/disk pressure ──► kubelet eviction manager ──► EVICTED   │
│   (terminal — Pod does not restart; owning controller schedules a new one)   │
└──────────────────────────────────────────────────────────────────────────────┘
```

- **`Pending` and `ImagePullBackOff` both occur before a container ever runs**, but at different points — `Pending` is pre-scheduling or pre-start, `ImagePullBackOff` is a specific post-scheduling failure to fetch the image.
- **`CrashLoopBackOff` is the only one of the four where the container definitively ran** — this single fact should redirect the very next command toward `kubectl logs --previous` rather than image-pull or scheduling checks.
- **`Evicted` sits outside the normal restart cycle entirely** — it's a node-pressure-driven termination, not a step in the Pending → Pull → Start → Crash sequence, and no amount of waiting resolves it on that same Pod.

## 5. Hands-On

### 5.1 Diagnosing CrashLoopBackOff

**Purpose:** Confirm the container did start, then find out why it exited, using `--previous` logs first per [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s cheapest-signal-first ordering.

**Syntax:**

```bash
kubectl get pod <pod> -n <namespace>
kubectl logs <pod> -n <namespace> --previous
kubectl describe pod <pod> -n <namespace> | grep -A5 "Last State"
```

**Example usage and expected output:**

```bash
$ kubectl get pod web-7d9f8-x2k1 -n production
NAME              READY   STATUS             RESTARTS   AGE
web-7d9f8-x2k1    0/1     CrashLoopBackOff   9          14m

$ kubectl describe pod web-7d9f8-x2k1 -n production | grep -A5 "Last State"
Last State:    Terminated
  Reason:      Error
  Exit Code:   1
  Started:     Tue, 31 Jul 2026 08:55:02 +0000
  Finished:    Tue, 31 Jul 2026 08:55:04 +0000

$ kubectl logs web-7d9f8-x2k1 -n production --previous
FATAL: config file /etc/app/config.yaml not found
```

**Production usage example:** The exit code (1, generic application error, not 137 which would indicate an OOM kill) plus the two-second lifetime and the `--previous` log line together point precisely at a missing mounted ConfigMap ([§41](../Part6/Section-41-Part6-ConfigMaps-Creation-Consumption.md)) rather than a resource or probe issue — the fix is correcting the volume mount, not adjusting resource limits or restart policy.

**Common errors:** Concluding "the app is crashing" without checking the `Exit Code` — code `137` specifically indicates a SIGKILL, almost always an OOM kill (worth checking `kubectl describe pod` for `OOMKilled` in the reason field), which points at resource limits rather than application logic, a materially different fix path.

### 5.2 Diagnosing ImagePullBackOff / ErrImagePull

**Purpose:** Confirm the container never started, then find the specific pull failure reason from the Event stream.

**Syntax:**

```bash
kubectl describe pod <pod> -n <namespace> | grep -A10 Events
```

**Example usage and expected output:**

```bash
$ kubectl describe pod web-7d9f8-x2k1 -n production | grep -A6 Events
Events:
  Type     Reason     Age                From     Message
  ----     ------     ----               ----     -------
  Normal   Scheduled  5m                 default-scheduler  Successfully assigned production/web-7d9f8-x2k1 to node-3
  Normal   Pulling    5m                 kubelet   Pulling image "registry.internal/web:v2.4.1"
  Warning  Failed     5m (x4 over 5m)    kubelet   Failed to pull image "registry.internal/web:v2.4.1": rpc error: code = Unknown desc = failed to authorize: 401 Unauthorized
  Warning  BackOff    3m (x10 over 5m)   kubelet   Back-off pulling image "registry.internal/web:v2.4.1"
```

**Production usage example:** The exact Event message (`401 Unauthorized`) narrows this immediately to an `imagePullSecrets` or private-registry authentication problem, not a networking, DNS, or typo issue — the fix is verifying the Pod's (or its ServiceAccount's) `imagePullSecrets` reference a valid, current registry credential, distinct entirely from the `CrashLoopBackOff` fix path in 5.1.

**Common errors:** Assuming `ImagePullBackOff` always means a typo in the image tag — the Event message distinguishes an actual "not found" (typo/missing tag) from an authentication failure (`401`/`403`, missing or expired pull secret) from a registry unreachable/timeout (network or DNS issue) — reading the exact message text is required, not just the state name.

### 5.3 Diagnosing Pending and Evicted Pods

**Purpose:** Show how to distinguish an unschedulable Pod from a node-pressure eviction, and why `Evicted` requires a fundamentally different response than the other three states.

**Syntax:**

```bash
kubectl describe pod <pod> -n <namespace> | grep -A5 Events
kubectl get pod <pod> -n <namespace> -o jsonpath='{.status.reason}'
kubectl describe node <node> | grep -A5 Conditions
```

**Example usage and expected output:**

```bash
# Pending example
$ kubectl describe pod worker-9f2a1 -n batch | grep -A3 Events
Events:
  Warning  FailedScheduling  2m (x5 over 6m)  default-scheduler
  0/4 nodes are available: 4 Insufficient memory.

# Evicted example
$ kubectl get pod cache-5c8b2 -n production
NAME           READY   STATUS    RESTARTS   AGE
cache-5c8b2    0/1     Evicted   0           -

$ kubectl get pod cache-5c8b2 -n production -o jsonpath='{.status.reason}{"\n"}{.status.message}'
Evicted
The node was low on resource: memory. Container cache was using 980Mi, which exceeds its request of 512Mi.
```

**Production usage example:** `FailedScheduling` with `Insufficient memory` isolates the Pending case to a scheduling-layer capacity problem — either the cluster needs more capacity or this workload's requests need adjusting — while the `Evicted` example's status message confirms the container exceeded its memory _request_ under real node memory pressure, meaning the fix targets that container's resource requests/limits ([§46](../Part6/Section-46-Part6-Resource-Requests-Limits-QoS-Classes.md)) or overall node capacity planning, not the Pod itself, which will never restart in this state.

**Common errors:** Repeatedly running `kubectl get pod` on an `Evicted` Pod expecting it to recover, or trying to `kubectl delete` and manually recreate it, instead of checking whether its owning controller (Deployment, StatefulSet) already scheduled a fresh replacement Pod elsewhere — for bare Pods with no controller, eviction is genuinely final and requires manual recreation.

## 6. Production Usage Notes

- **`kubectl get pods -o wide` combined with `--sort-by=.status.startTime`** is a fast way to spot a cluster-wide pattern (many Pods `Evicted` around the same timestamp on the same node) versus an isolated single-Pod issue, materially changing whether the investigation targets one workload or one node's capacity.
- **Old `Evicted` Pod objects accumulate and are worth periodic cleanup** (`kubectl get pods --field-selector=status.phase=Failed -A` followed by a scoped delete) since they remain visible in `kubectl get pods` output indefinitely unless garbage-collected, cluttering routine status checks.
- **`ImagePullBackOff` triggered by expired registry credentials is a recurring operational pattern** worth automating a check for — many teams alert specifically on this Event reason/message pattern rather than waiting for a user-facing outage to surface it.

## 7. Security Considerations

- **`ErrImagePull`/`401`/`403` messages can reveal registry topology or credential existence to anyone with read access to Events in that namespace** — a minor but real information-disclosure consideration when scoping RBAC read access.
- **`imagePullSecrets` misconfiguration is a common, low-severity but real availability risk** — an expired credential silently blocking every new Pod rollout from a private registry is worth monitoring proactively rather than discovering during an incident.
- **Investigating `Evicted` Pods sometimes surfaces a workload with no resource `limits` set at all (BestEffort QoS, [§46](../Part6/Section-46-Part6-Resource-Requests-Limits-QoS-Classes.md))** — a security- and stability-relevant gap worth flagging, since such Pods are always the first evicted under any node pressure, by design.

## 8. Common Troubleshooting Scenarios

| Symptom                                                   | Cause                                                                                                                                                                     | Fix                                                                                                                                                                                                                     |
| --------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CrashLoopBackOff`, exit code 1, short container lifetime | Application-level startup error (missing config, bad env var)                                                                                                             | Check `kubectl logs --previous` for the exact application error and fix the underlying config                                                                                                                           |
| `CrashLoopBackOff`, exit code 137                         | Container OOM-killed by the kernel                                                                                                                                        | Increase memory limit or fix an application memory leak; check `Reason: OOMKilled` in `describe`                                                                                                                        |
| `ImagePullBackOff`, Event shows `401`/`403`               | Missing, expired, or misconfigured `imagePullSecrets`                                                                                                                     | Recreate/refresh the registry credential Secret and confirm it's referenced correctly                                                                                                                                   |
| `ImagePullBackOff`, Event shows `manifest unknown`        | Wrong image name or tag                                                                                                                                                   | Correct the image reference in the Pod/Deployment spec                                                                                                                                                                  |
| `Pending`, Event shows `Insufficient cpu`/`memory`        | No node in the cluster has enough allocatable capacity for the requests                                                                                                   | Reduce requests, add node capacity, or review scheduling constraints ([§65](../Part9/Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md)–[§72](../Part9/Section-72-Part9-Topology-Spread-Constraints.md)) |
| `Pending`, no `FailedScheduling` Event at all             | Scheduler itself may be down — check control plane ([§100](./Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md)) before workload spec | Verify `kube-scheduler` Pod/process health before assuming the Pod spec is at fault                                                                                                                                     |
| `Evicted`, node under memory pressure                     | Container exceeded its memory request while node had insufficient headroom                                                                                                | Adjust resource requests/limits ([§46](../Part6/Section-46-Part6-Resource-Requests-Limits-QoS-Classes.md)) or increase node capacity; confirm controller rescheduled a replacement                                      |

## 9. Best Practices

- Read the exact `STATUS` value and the exact Event `Message` text before forming any hypothesis — `CrashLoopBackOff` and `ImagePullBackOff` point at entirely different layers and require different next commands.
- Always check `Exit Code` and `Reason` (`Error` vs `OOMKilled`) for a crashing container before assuming an application bug — the exit code alone often distinguishes application-level failure from resource-limit failure.
- Treat `Evicted` as terminal immediately — verify the owning controller has scheduled a replacement rather than waiting on or manually retrying the evicted Pod object itself.

## 10. Common Anti-Patterns / Mistakes

- **Treating `CrashLoopBackOff` and `ImagePullBackOff` as interchangeable "the Pod is broken" states**, missing that only the former means the container actually started at all.
- **Reading current-instance logs instead of `--previous` for a crashing container**, missing the actual exit reason recorded by the container instance that failed.
- **Waiting on or repeatedly recreating an `Evicted` Pod**, rather than addressing the node-level resource pressure that caused it and confirming the owning controller already handled replacement.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `CrashLoopBackOff` and `ImagePullBackOff`?"_
**Model answer:** `ImagePullBackOff` means the kubelet was never able to successfully pull the container image at all — the container never started, so the problem is with the image reference, registry access, or pull credentials. `CrashLoopBackOff` means the opposite in one key respect — the container did successfully start at least once, but then exited, and the kubelet is now applying exponential back-off before trying to restart it again under the default restart policy. The practical difference matters because it points to a completely different next step: `ImagePullBackOff` sends you to check the image name and `imagePullSecrets`, while `CrashLoopBackOff` sends you to `kubectl logs --previous` to see why the running container exited.
_What the interviewer is probing for:_ Precise understanding that these states mark fundamentally different points in the Pod lifecycle, not just "two different error messages."

**🎯 Intermediate:** _"A Pod shows `Evicted`. Walk me through your investigation and what you'd actually do about it."_
**Model answer:** First, I recognize `Evicted` as a terminal state — the kubelet's eviction manager forcibly terminated this Pod, almost always due to node-level memory or disk pressure, and this specific Pod object will not restart. I'd check its status message (`kubectl get pod -o jsonpath` on `.status.message`) to confirm the exact resource under pressure and how far the container exceeded its request. Then I'd check whether the owning controller — a Deployment or StatefulSet — already scheduled a replacement Pod elsewhere in the cluster, which is usually the case and means the immediate availability concern is already handled. The real fix, though, targets the root cause: either that workload's resource requests were set too low relative to its actual usage, or the node genuinely lacks capacity and needs either more headroom or better bin-packing across the cluster — I wouldn't consider the incident closed just because a replacement Pod is running if the underlying resource-pressure condition is still there waiting to evict the next Pod.
_What the interviewer is probing for:_ Recognition that `Evicted` is terminal and node-level in origin, not a Pod-level bug to retry, and that the real fix addresses resource planning, not the individual Pod.

**🎯 Senior:** _"You see `CrashLoopBackOff` with exit code 137. What does that tell you, and how does it change your investigation compared to exit code 1?"_
**Model answer:** Exit code 137 is 128 plus signal 9 (SIGKILL), which in a Kubernetes context is almost always the kernel's OOM killer terminating the container because it exceeded its memory limit — I'd confirm this specifically by checking `kubectl describe pod` for `Reason: OOMKilled` in the `Last State` section, rather than assuming from the exit code alone. This changes the investigation materially from exit code 1, which is a generic application-level error requiring me to read the application's own log output via `--previous` to find the specific cause. With 137/OOMKilled, the logs are often unhelpful (the container is killed abruptly, sometimes mid-write, with no graceful shutdown message), so the actual fix path is about resource sizing — either the memory limit is genuinely too low for the workload's real footprint, or there's an actual memory leak in the application that needs profiling separately, and I'd check historical memory usage via metrics ([§91](../Part12/Section-91-Part12-Metrics-Server-Kubernetes-Metrics-Pipeline.md)–[§92](../Part12/Section-92-Part12-Prometheus-Kubernetes-ServiceMonitors-Node-Exporter-kube-state-metrics.md)) to distinguish "always been tight, just under-provisioned" from "usage is climbing over time, a leak," since those two root causes call for different long-term fixes.
_What the interviewer is probing for:_ Ability to extract a specific, actionable signal from an exit code rather than treating "CrashLoopBackOff" as a single undifferentiated failure mode, and to reason about distinguishing under-provisioning from a genuine memory leak.

**🎯 Architect:** _"Design a proactive detection strategy so your team catches these four Pod failure states before they become user-facing incidents, across a large multi-team cluster."_
**Model answer:** I'd build alerting directly on the signals this section relies on manually, rather than waiting for someone to run `kubectl get pods` and notice a problem. Using kube-state-metrics ([§92](../Part12/Section-92-Part12-Prometheus-Kubernetes-ServiceMonitors-Node-Exporter-kube-state-metrics.md)) feeding Prometheus, I'd alert on `kube_pod_container_status_waiting_reason` for `CrashLoopBackOff` and `ImagePullBackOff` specifically, and on `kube_pod_status_reason` for `Evicted`, each with a reasonable time-window threshold to avoid paging on a single transient restart. For `Pending`, I'd alert on Pods remaining unscheduled past a threshold duration correlated with `FailedScheduling` Events, since a brief Pending state during normal rollout churn is expected and shouldn't page anyone. I'd also build a lightweight dashboard summarizing eviction frequency by node, since a node evicting Pods repeatedly is a capacity-planning signal worth catching before it becomes a recurring incident, and I'd track `ImagePullBackOff` incidents specifically tied to credential expiry as their own alert category, since that failure mode is entirely predictable and preventable with credential-rotation automation rather than reactive firefighting. Finally, I'd feed real incidents from all four categories back into team-level runbooks (per [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s Architect answer), so recurring root causes for a specific team's workloads (chronically under-provisioned memory requests, say) get addressed structurally rather than being rediscovered fresh every time.
_What the interviewer is probing for:_ Ability to convert reactive, manual diagnostic knowledge into proactive, automated detection at scale, tied to the correct underlying metrics and Event data rather than generic dashboarding.

## 12. Common Misconceptions

1. **"CrashLoopBackOff means the image or config is fundamentally broken and won't run."** It specifically means the container did start and then exited — the cause could be anything from a transient dependency timeout to a genuine bug, but the container running at all is itself informative and rules out image-pull or scheduling problems entirely.
2. **"ImagePullBackOff is always a typo in the image name."** The exact Event message differentiates a genuine not-found/typo from an authentication failure (expired or missing pull secret) from a registry connectivity issue — each requiring a different fix.
3. **"A Pending Pod will eventually schedule itself if you just wait."** Some Pending causes (transient scheduler backlog) do resolve with time, but persistent `FailedScheduling` due to insufficient cluster capacity or unsatisfiable constraints (taints, affinity) will not resolve without an actual change to either the workload's requirements or the cluster's capacity.
4. **"An Evicted Pod can be restarted like any other failed Pod."** Eviction is terminal for that specific Pod object; recovery relies on the owning controller scheduling an entirely new Pod, and for bare, controller-less Pods, manual recreation is required.

## 13. 🔑 Key Takeaways

- `CrashLoopBackOff` means the container started and exited — investigate via `kubectl logs --previous` and the exit code/reason, not image or scheduling checks.
- `ImagePullBackOff`/`ErrImagePull` means the container never started at all — the exact Event message text distinguishes a naming typo, an auth failure, and a registry connectivity issue, each with a different fix.
- `Pending` means the Pod hasn't been scheduled (or started post-scheduling) yet — `FailedScheduling` Events point at capacity or constraint mismatches, and total silence on Events may point instead at scheduler health itself ([§100](./Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md)).
- `Evicted` is a terminal, node-pressure-driven state — it will not restart on its own, and the real fix targets resource sizing or node capacity, verifying the owning controller has already rescheduled a replacement.
- Reading the exact Pod state and Event message correctly is itself the isolation step from [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s methodology — it should always precede reaching for logs or deeper tools, not follow it.

## 14. Related Concepts & What's Next

This section applied [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s structured troubleshooting methodology to the most common Pod-level failure states, drawing on Pod spec fundamentals ([§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md)) and probe behavior ([§89](../Part12/Section-89-Part12-Liveness-Readiness-Startup-Probes.md)) to explain why each state occurs and what it isolates. [§99](./Section-99-Part13-Debugging-Node-Issues-NotReady-Nodes-kubelet-Failures.md) moves one layer up the stack, applying the same methodology to Node-level failures — `NotReady` Nodes and kubelet failures — which is frequently the actual root cause behind a Pod stuck `Pending` or repeatedly evicted on a single struggling node.

**Next Section:** [§99](./Section-99-Part13-Debugging-Node-Issues-NotReady-Nodes-kubelet-Failures.md) — `Section-99-Part13-Debugging-Node-Issues-NotReady-Nodes-kubelet-Failures.md`
