# Section 105 (Part 13): Incident Case Studies and Runbooks

## 1. Definition

**Plain language:** Every section in Part 13 so far has isolated one layer of failure at a time — the methodology ([§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)), Pod failure states ([§98](./Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md)), node issues ([§99](./Section-99-Part13-Debugging-Node-Issues-NotReady-Nodes-kubelet-Failures.md)), control plane failures ([§100](./Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md)), networking ([§101](./Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md)), storage ([§102](./Section-102-Part13-Storage-Troubleshooting-Scenarios-PVC-Pending-Mount-Errors.md)), application-level bugs ([§103](./Section-103-Part13-Application-Level-Debugging-Misconfigured-Probes-Resource-Starvation-OOMKilled.md)), and cluster-wide resource exhaustion ([§104](./Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md)). Real incidents rarely respect those boundaries; a single production outage often touches two or three of these layers in sequence, and the skill that actually matters on-call is following the evidence from one layer into the next without losing the thread. This section stitches the whole toolkit together into complete, realistic incident narratives.

**Precise definition:** An **incident case study** is an end-to-end narrative of a production Kubernetes failure — from the first user-facing or alerting signal, through the diagnostic path an on-call engineer actually walks, to root cause and resolution — deliberately constructed to require moving between the failure categories covered across [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)-[§104](./Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md). A **runbook** is the structured, repeatable sequence of commands and decision points extracted from that narrative, written so that a future on-call engineer facing the same symptom pattern can execute the same diagnostic path directly rather than rediscovering it under pressure. This section presents three such case studies, each ending in a condensed runbook.

## 2. Why This Matters

- **Real incidents don't announce which layer they belong to** — a user-facing "checkout is down" report gives no indication up front whether the cause is networking, storage, an application bug, or node-level resource exhaustion, and the entire discipline built across [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)-[§104](./Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md) exists to let an engineer narrow that down systematically rather than guessing.
- **The transition points between layers are where time gets lost in real incidents** — recognizing when a networking investigation ([§101](./Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md)) has actually reached its natural end and the evidence now points toward an application-level cause ([§103](./Section-103-Part13-Application-Level-Debugging-Misconfigured-Probes-Resource-Starvation-OOMKilled.md)) is a distinct skill from being competent at either layer in isolation.
- **A well-written runbook converts a one-time investigation into a repeatable, much faster response** — the value of documenting an incident's resolution path isn't historical record-keeping, it's directly shortening the time-to-resolution the next time a structurally similar symptom appears, potentially for an entirely different on-call engineer.

🔑 **Key Takeaway:** Production incidents move across the layers covered in [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)-[§104](./Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md) rather than staying contained in one, and the practical payoff of studying complete incident narratives — and converting them into runbooks — is training the judgment to recognize when to stop digging in one layer and follow the evidence into the next.

## 3. Prerequisites and Dependencies

This section synthesizes every prior section in Part 13: [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md) (structured troubleshooting methodology), [§98](./Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md) (Pod failure states), [§99](./Section-99-Part13-Debugging-Node-Issues-NotReady-Nodes-kubelet-Failures.md) (node issues), [§100](./Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md) (control plane failures), [§101](./Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md) (networking scenarios), [§102](./Section-102-Part13-Storage-Troubleshooting-Scenarios-PVC-Pending-Mount-Errors.md) (storage scenarios), [§103](./Section-103-Part13-Application-Level-Debugging-Misconfigured-Probes-Resource-Starvation-OOMKilled.md) (application-level debugging), and [§104](./Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md) (cluster-level resource exhaustion and eviction). No new mechanism is introduced here — this is deliberately a synthesis and capstone section, assuming full familiarity with all eight preceding sections. Forwards into Part 14 (Cluster Maintenance and Lifecycle), where the operational discipline shifts from reactive troubleshooting to proactive maintenance.

## 4. Architecture Diagram

```text
   How a single incident can traverse every layer covered in Part 13

   User-facing symptom: "checkout requests are failing intensively"
                    │
                    ▼
   §97 methodology: start at Pod/Service state, work outward
                    │
        ┌───────────┼────────────────┬─────────────────┐
        ▼                            ▼                 ▼
   §98 Pod failure state       §101 Networking     §104 Node-level
   (CrashLoopBackOff?              (Service/DNS         resource pressure
    Pending? Evicted?)              unreachable?)       (Evicted Pods?)
        │                            │                 │
        ▼                            ▼                 ▼
   §103 Application-level      §102 Storage          §99 Node
   (OOMKilled? bad probe?)     (PVC Pending?          (NotReady? kubelet
                                mount error?)           degraded?)
        │                            │                 │
        └────────────┬───────────────┴─────────────────┘
                     ▼
              Root cause identified — often one layer feeding
              symptoms into the next (e.g., node pressure §104
              → evicted Pods → readiness gaps → §101-looking
              Service unavailability)
```

- The diagram's point is topological, not sequential — a real incident doesn't necessarily start at the top and move down in order; the methodology ([§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)) is what tells you which branch to follow first based on the actual evidence in front of you.
- The three case studies below each walk one distinct path through this diagram, chosen because they represent the most common real-world traversal patterns: resource pressure cascading into evictions, a probe misconfiguration masquerading as a networking issue, and a storage failure masking as an application bug.

## 5. Hands-On: Three Incident Case Studies

### 5.1 Case Study — Cascading Node Pressure Masquerading as a Networking Outage

**Scenario:** A checkout service reports intermittent `503`s from its Ingress. The on-call engineer's first instinct, following [§101](./Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md)'s networking playbook, is to check Service Endpoints and DNS.

**Investigation walkthrough:**

```bash
$ kubectl get endpoints checkout-svc -n prod
NAME           ENDPOINTS                     AGE
checkout-svc   10.244.2.14:8080              4h
# Expected 6 endpoints (6 replicas) — only 1 present

$ kubectl get pods -n prod -l app=checkout -o wide
NAME                        READY   STATUS    RESTARTS   AGE   NODE
checkout-7d9f-a1b2c         1/1     Running   0          4h    node-2
checkout-7d9f-d3e4f         0/1     Evicted   0          8m    node-7
checkout-7d9f-g5h6i         0/1     Evicted   0          8m    node-7
checkout-7d9f-j7k8l         0/1     Evicted   0          6m    node-7
checkout-7d9f-m9n0o         0/1     Pending   0          6m    <none>
checkout-7d9f-p1q2r         0/1     Pending   0          6m    <none>

$ kubectl describe node node-7 | grep -A3 Conditions
Conditions:
  Type             Status  Reason
  MemoryPressure   True    KubeletHasInsufficientMemory
```

**Root cause:** Five of six `checkout-svc` replicas were scheduled onto `node-7`, which — per [§104](./Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md) — hit `MemoryPressure` because a separate, unrelated `BestEffort` batch job (no `resources.requests` set) had scaled up sharply and was co-located on the same node. The kubelet evicted the `checkout` Pods (which were `Burstable`, less protected than the batch job would have been if it were `Guaranteed`, but more numerous and thus mathematically more likely to be selected) while remaining Pods were left `Pending` because no other node had capacity. The Service's Endpoints list shrank to one healthy Pod, which is what actually produced the `503`s the ticket originally described as a networking issue.

**Runbook:**

1. Check `kubectl get endpoints <svc>` first — an Endpoints list shorter than expected redirects the investigation from "is networking broken" to "why are backing Pods missing," per [§101](./Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md)'s own guidance.
2. Check the status of every Pod behind the Service (`kubectl get pods -l <selector> -o wide`) — `Evicted` or `Pending` statuses point away from networking and toward [§104](./Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md) (resource exhaustion) or [§98](./Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md) (scheduling failures).
3. If Pods show `Evicted`, immediately check `kubectl describe node <node>` for pressure conditions, and identify every Pod that was co-located on that node, not just the ones in the original ticket.
4. Fix the actual cause (missing `resources.requests` on the offending batch job) rather than only restarting the evicted `checkout` Pods, which would recur identically on the next batch job scale-up.
5. Consider a `PodDisruptionBudget` and pod anti-affinity ([§33](../Part5/Section-33-Part5-Statefulsets-Stable-Network-Identity-Ordered-Deployment.md), [§68](../Part9/Section-68-Part9-Taints-Tolerations.md)) for `checkout-svc` so future node pressure events can't evict a majority of its replicas simultaneously.

### 5.2 Case Study — A Probe Misconfiguration After a Routine Deploy, Mistaken for a Storage Issue

**Scenario:** Immediately after a routine deploy, a reporting service's Pods cycle through restarts, and its logs show intermittent errors referencing a mounted config file — leading the on-call engineer, per [§102](./Section-102-Part13-Storage-Troubleshooting-Scenarios-PVC-Pending-Mount-Errors.md)'s storage playbook, to first suspect a mount problem.

**Investigation walkthrough:**

```bash
$ kubectl describe pod report-svc-8f2a-x9y8z -n prod | grep -A6 "Last State\|Liveness"
    Liveness:  http-get http://:8080/ready delay=5s timeout=1s period=10s #success=1 #failure=2
Last State:    Terminated
  Reason:      Error
  Message:     Killed by liveness probe

$ kubectl logs report-svc-8f2a-x9y8z --previous -n prod | tail -6
2026-07-31T14:02:03Z INFO  config loaded from /etc/report/config.yaml
2026-07-31T14:02:03Z INFO  connecting to cache backend, this may take up to 20s
2026-07-31T14:02:04Z INFO  server listening on :8080

$ kubectl get deployment report-svc -n prod -o jsonpath='{.spec.template.spec.containers[0].livenessProbe}'
{"httpGet":{"path":"/ready","port":8080},"initialDelaySeconds":5,"periodSeconds":10,"failureThreshold":2}
```

**Root cause:** The config mount and the volume behind it (both checked early and cleared using [§102](./Section-102-Part13-Storage-Troubleshooting-Scenarios-PVC-Pending-Mount-Errors.md)'s toolkit) were never the problem — the log line referencing the config file was simply the last line printed before the container was killed, which misled the initial triage. The actual cause, per [§103](./Section-103-Part13-Application-Level-Debugging-Misconfigured-Probes-Resource-Starvation-OOMKilled.md), was the new deploy's `livenessProbe` pointed at `/ready` (an endpoint that itself waits up to 20 seconds for a downstream cache connection to establish) with only a 5-second `initialDelaySeconds` and a `failureThreshold` of 2 — the container was being killed by its own liveness probe before it ever finished a legitimately slow, but bounded, startup sequence. This is precisely the class of problem a `startupProbe` ([§89](../Part12/Section-89-Part12-Liveness-Readiness-Startup-Probes.md)) exists to prevent, and the deploy had none.

**Runbook:**

1. Don't anchor on the last log line before a crash as the cause — check `kubectl describe pod`'s `Last State`/`Message` field first; `"Killed by liveness probe"` overrides any other hypothesis immediately.
2. Compare the probe's `initialDelaySeconds`/`periodSeconds`/`failureThreshold` window against the application's actual, logged startup time — if the startup sequence description (cache connection, warm-up) exceeds the probe's tolerance window, that mismatch is the root cause.
3. Check whether this regressed with the most recent deploy (`kubectl rollout history`) — a probe misconfiguration introduced by a routine deploy is far more likely than a sudden, unrelated storage regression on infrastructure that was previously stable.
4. Fix by adding a `startupProbe` sized to the worst-case startup time ([§89](../Part12/Section-89-Part12-Liveness-Readiness-Startup-Probes.md)), rather than only loosening the `livenessProbe`'s own thresholds, which would blind ongoing hang detection during steady-state running.
5. Add a deploy-time check (e.g., a post-deploy smoke test or staged rollout) that would have caught Pods cycling through restarts before the full rollout completed.

### 5.3 Case Study — A Silent CSI Driver Failure Presenting as Multiple Unrelated Application Tickets

**Scenario:** Three tickets arrive within ten minutes: an ingestion Pod stuck `Pending`, a different Pod reporting application-level write errors to its data directory, and a third Pod that appears healthy but is failing its readiness probe. Each is initially assigned to a different on-call rotation (scheduling, application, probes) because they look unrelated.

**Investigation walkthrough:**

```bash
$ kubectl get pods -A -o wide | grep -E "ingest|writer|reader"
prod   ingest-worker-4f-a1     0/1   Pending             0    9m    <none>
prod   writer-svc-9c-b2        1/1   Running             0    2h    node-5
prod   reader-svc-2d-c3        0/1   Running             0    2h    node-5

$ kubectl get pods -n kube-system -l app=ebs-csi-node -o wide
NAME                    READY   STATUS             RESTARTS   NODE
ebs-csi-node-h7j2k      2/3     CrashLoopBackOff   11         node-5

$ kubectl logs writer-svc-9c-b2 -n prod --tail=5
2026-07-31T15:10:02Z ERROR write to /data/output.log failed: input/output error
```

**Root cause:** All three Pods trace back to `node-5`'s CSI node plugin, which was `CrashLoopBackOff` — a scenario directly covered in [§102](./Section-102-Part13-Storage-Troubleshooting-Scenarios-PVC-Pending-Mount-Errors.md)'s storage catalog. `ingest-worker` couldn't be scheduled because its PVC's volume required attachment via the broken plugin (surfacing as `Pending`, initially misfiled as a scheduling issue per [§98](./Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md)); `writer-svc` was already running with a volume mounted before the plugin crashed, and began throwing I/O errors as the underlying mount degraded (misfiled as an application bug); `reader-svc`'s readiness probe checked filesystem access to the same degrading mount and began failing (misfiled as a probe issue per [§103](./Section-103-Part13-Application-Level-Debugging-Misconfigured-Probes-Resource-Starvation-OOMKilled.md), superficially similar to the case study above but with a genuinely different root cause). Only checking CSI driver Pod health across the node — the specific move [§102](./Section-102-Part13-Storage-Troubleshooting-Scenarios-PVC-Pending-Mount-Errors.md) calls out — connected all three.

**Runbook:**

1. When multiple, differently-symptomed tickets involving Pods or PVCs arrive close together, check first whether the affected Pods share a node, before assigning each ticket to a different specialist rotation.
2. Check CSI driver Pod health on that shared node (`kubectl get pods -n kube-system -l app=<csi-node-label> -o wide`) as a single, fast, cluster-wide check that can immediately explain an otherwise-scattered set of symptoms.
3. Resist the urge to fix each symptom independently (restart `writer-svc`, tweak `reader-svc`'s readiness probe, force-schedule `ingest-worker` elsewhere) before confirming whether they share a root cause — those actions would have masked, not fixed, the underlying CSI plugin crash.
4. Fix the CSI node plugin itself (restart, or roll back a recent DaemonSet version bump if that's the trigger); the three application-facing tickets should self-resolve without any Pod-specific intervention.
5. Add CSI driver Pod health to the same node-health dashboard used for kubelet/node conditions ([§92](../Part12/Section-92-Part12-Prometheus-Kubernetes-ServiceMonitors-Node-Exporter-kube-state-metrics.md)), so a future occurrence surfaces as one infrastructure alert rather than three separate, misleading application tickets.

## 6. Production Usage Notes

- **The `kubectl describe pod`'s `Last State`/`Message` field and node condition checks are consistently the fastest way to redirect a misdirected initial hypothesis** across all three case studies above — making them a standing first move regardless of how a ticket was originally worded or routed.
- **Ticket triage that assigns each symptom to a different specialist rotation before checking for a shared node or shared underlying component** is a recurring, avoidable source of slow incident resolution, visible directly in Case Study 3.
- **Every runbook above ends with a preventive step**, not just a resolution step — a mature incident response practice treats the "how do we stop this recurring" question as part of the incident, not a follow-up ticket that may or may not get done later.

## 7. Security Considerations

- Incident runbooks and postmortems frequently reference internal architecture details, node names, and capacity figures — store and share them with the same access controls applied to other internal operational documentation, not in an unrestricted public wiki.
- During a live incident, the pressure to resolve quickly increases the temptation to grant broad, temporary RBAC permissions ("just give me cluster-admin for now") — this should be resisted in favor of pre-approved, scoped break-glass roles ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)) established before an incident, not improvised during one.
- Postmortems that name individuals rather than systems or process gaps create an incentive to hide information during future incidents — the case studies above intentionally frame root causes as system/process gaps (missing `resources.requests`, missing `startupProbe`, ticket-routing habits), which is the standard blameless-postmortem convention worth carrying into any real incident review.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                       | Cause                                                                                           | Fix                                                                                                                                                                        |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Service returns intermittent errors, Endpoints list shorter than expected     | Backing Pods evicted due to node-pressure eviction from an unrelated co-located workload        | Trace Endpoints shrinkage to Pod status, then to node conditions ([§104](./Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md)), not just Service/DNS config |
| Pods restart right after a routine deploy, logs show unrelated-looking errors | New deploy introduced a probe misconfiguration; last log line before the kill is coincidental   | Check `Last State`/`Message` for "Killed by liveness probe" before trusting the last application log line                                                                  |
| Multiple, differently-symptomed tickets across Pods sharing a node            | A single degrading node-level component (CSI driver, kubelet) affecting every Pod on that node  | Check shared-node infrastructure health before routing each symptom to a different specialist                                                                              |
| Incident resolved by restarting/patching individual Pods, recurs days later   | Root cause (missing requests, missing startupProbe, missing anti-affinity) never actually fixed | Always include a durable preventive fix, not just a symptom-level resolution, before closing an incident                                                                   |

## 9. Best Practices

- Treat the first ticket's initial framing (which team, which layer) as a hypothesis to test, not a fact — following [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s methodology of starting from object state and following evidence outward is what corrects a misrouted initial assumption quickly.
- Convert every non-trivial incident into a short, reusable runbook immediately after resolution, while the diagnostic path is still fresh, rather than relying on memory or an unstructured postmortem document read once and never referenced again.
- Always pair a symptom-level fix (restart a Pod, patch a probe) with a preventive, durable fix (`resources.requests`, a `startupProbe`, an anti-affinity rule, a monitoring gap closed) before considering an incident fully resolved.

## 10. Common Anti-Patterns / Mistakes

- **Anchoring on the ticket's original framing or the last log line before a crash**, rather than following the evidence at each layer (Pod state, node conditions, probe configuration, storage health) independently of how the incident was initially described.
- **Investigating multiple simultaneous, differently-symptomed tickets in isolation** without first checking whether the affected Pods share a node or a common underlying component.
- **Closing an incident after only a symptom-level fix** (a restart, a manual patch) without addressing the actual root cause, guaranteeing a structurally identical recurrence later.

## 11. Interview Questions

**🎯 Beginner:** _"A ticket says 'the checkout service is down,' but when you check, only one out of six Pods behind the Service is listed as an endpoint. What's your very next step?"_
**Model answer:** Rather than assuming a networking problem just because the initial report framed it as one, I'd check the status of every Pod backed by that Service selector, not just the Endpoints count — `kubectl get pods -l <selector> -o wide` would show me whether the missing Pods are `Evicted`, `Pending`, `CrashLoopBackOff`, or something else entirely, which tells me which of Part 13's playbooks (scheduling, resource exhaustion, application-level) actually applies here, rather than continuing to dig into Service/DNS configuration that may be completely healthy.
_What the interviewer is probing for:_ Not getting anchored on the initial ticket framing, and knowing that a shrunk Endpoints list is a symptom that redirects the investigation toward Pod status first.

**🎯 Intermediate:** _"You're investigating a Pod restart loop that started right after a deploy, and the last log line before each crash references a config file mount. Would you start by investigating storage?"_
**Model answer:** Not before checking `kubectl describe pod`'s `Last State` and `Message` field first — if it says something like "Killed by liveness probe," the storage-adjacent log line was simply the last thing printed before an unrelated kill, not evidence of a mount problem. Since the restart loop started right after a deploy, I'd specifically compare the deploy's probe configuration (timing, target endpoint) against the application's actual startup behavior before spending time re-verifying storage that was very likely already working correctly.
_What the interviewer is probing for:_ Not treating a coincidental log line as causal evidence, and correlating a regression's timing with the most likely recent change (the deploy) before investigating unrelated subsystems.

**🎯 Senior:** _"Three tickets — a Pending Pod, a Pod throwing write errors, and a Pod failing readiness — arrive within minutes of each other, and get assigned to three different specialists. What would you flag about this triage approach, and how would you have handled it instead?"_
**Model answer:** I'd flag that assigning each ticket to a different specialist before checking whether the affected Pods share infrastructure risks three parallel, slower investigations that may all eventually converge on the same root cause anyway — wasted effort at best, and conflicting or masking fixes at worst if each specialist patches their own symptom independently. I'd have instead checked first whether the three Pods share a node, and if so, checked the health of node-level shared components (CSI driver Pods, kubelet) before routing anything further — a single crashing CSI node plugin, for instance, can produce exactly this varied symptom set across otherwise-unrelated Pods, and fixing it resolves all three tickets simultaneously without touching any of the affected Pods directly.
_What the interviewer is probing for:_ Recognizing when ticket-routing conventions actively slow down an investigation, and defaulting to a shared-infrastructure check before parallel, siloed root-causing.

**🎯 Architect:** _"How would you build an incident response practice, cluster-wide, that turns every non-trivial Part-13-style incident into compounding operational leverage rather than a one-off firefight?"_
**Model answer:** I'd require every incident above a defined severity threshold to produce two artifacts before being marked resolved: a blameless postmortem identifying the actual root cause at the system/process level (never at the individual level), and a short, versioned runbook capturing the specific diagnostic path that led there — stored in a searchable, centrally indexed location so the next on-call engineer facing a similar symptom pattern finds it before re-deriving it from scratch. I'd build alerting that reflects the lessons from these incidents directly — node condition monitoring ([§104](./Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md)), CSI driver health folded into node-health dashboards ([§102](./Section-102-Part13-Storage-Troubleshooting-Scenarios-PVC-Pending-Mount-Errors.md)), and probe/restart-reason correlation ([§103](./Section-103-Part13-Application-Level-Debugging-Misconfigured-Probes-Resource-Starvation-OOMKilled.md)) — so future occurrences of the same underlying pattern surface as a single, clear infrastructure alert rather than as multiple misleadingly-worded application tickets. I'd also periodically review the runbook library itself for staleness and for repeated root causes across supposedly unrelated incidents, since a root cause reappearing across multiple case studies (e.g., missing `resources.requests` showing up in both a resource-exhaustion incident and a QoS-related eviction incident) is itself a signal that a cluster-wide policy fix (a mandatory `LimitRange`, an admission policy) would eliminate an entire category of future incidents rather than requiring another one-off runbook.
_What the interviewer is probing for:_ Institutionalizing incident learning as a compounding system — postmortems, runbooks, and alerting improvements feeding back into prevention — rather than treating each incident as an isolated, forgotten event.

## 12. Common Misconceptions

1. **"The way a ticket is initially worded tells you which team or playbook should handle it."** Initial framing is frequently wrong — a "networking" symptom can trace to node-pressure eviction, and a "storage" symptom can trace to a probe misconfiguration; the actual evidence, not the ticket's wording, should drive the investigation.
2. **"The last log line before a crash is usually the cause of the crash."** It's frequently just the last thing printed before an unrelated kill (a liveness probe failure, an eviction) — `kubectl describe pod`'s `Last State`/`Message` field is more reliable evidence of cause than application log proximity to the crash.
3. **"Unrelated-looking simultaneous tickets require separate investigations by separate specialists."** They frequently share a root cause traceable through shared infrastructure (a node, a CSI driver Pod, a control-plane component), and checking for that shared infrastructure first is usually faster than three parallel investigations.
4. **"An incident is resolved once the immediate symptom stops."** Without a durable preventive fix (proper requests, a startupProbe, anti-affinity, a monitoring gap closed), the identical incident recurs under the same triggering conditions later.

## 13. 🔑 Key Takeaways

- Real incidents traverse the layers covered across [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)-[§104](./Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md) rather than staying contained in one, and following the evidence — not the ticket's initial framing — is what correctly identifies which layer actually matters.
- `kubectl describe pod`'s `Last State`/`Message` field and node condition checks are consistently the fastest way to redirect a misdirected initial investigation, across networking, storage, application, and resource-exhaustion incidents alike.
- Multiple, differently-symptomed tickets arriving close together are worth checking for a shared node or shared infrastructure component before assigning each to a separate specialist investigation.
- Every incident resolution should pair a symptom-level fix with a durable, preventive fix — otherwise the same incident recurs under the same conditions.
- Converting resolved incidents into short, reusable, blameless runbooks is what compounds troubleshooting effort into lasting organizational leverage, rather than each incident being re-derived from scratch.

## 14. Related Concepts & What's Next

This capstone section synthesizes the full troubleshooting toolkit built across Part 13 — [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s methodology, [§98](./Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md)'s Pod failure states, [§99](./Section-99-Part13-Debugging-Node-Issues-NotReady-Nodes-kubelet-Failures.md)'s node debugging, [§100](./Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md)'s control plane failures, [§101](./Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md)'s networking scenarios, [§102](./Section-102-Part13-Storage-Troubleshooting-Scenarios-PVC-Pending-Mount-Errors.md)'s storage scenarios, [§103](./Section-103-Part13-Application-Level-Debugging-Misconfigured-Probes-Resource-Starvation-OOMKilled.md)'s application-level debugging, and [§104](./Section-104-Part13-Cluster-Level-Resource-Exhaustion-Eviction.md)'s cluster-level resource exhaustion — into complete, realistic incident narratives and their extracted runbooks. With Part 13's troubleshooting toolkit now complete, Part 14 shifts from reactive incident response to proactive cluster maintenance and lifecycle management, beginning with the structured process of upgrading a cluster's control plane and nodes without incurring the very kinds of outages this Part has spent nine sections learning to diagnose.

**Next Section:** [§106](../Part14/Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md) — `Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md`
