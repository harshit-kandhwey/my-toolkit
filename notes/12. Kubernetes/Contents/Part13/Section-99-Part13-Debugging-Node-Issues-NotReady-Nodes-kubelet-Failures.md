# Section 99 (Part 13): Debugging Node Issues: NotReady Nodes, kubelet Failures

## 1. Definition

**Plain language:** When a Pod is stuck `Pending` or gets repeatedly evicted on the same node, the actual problem is frequently not the Pod at all — it's the Node itself. `kubectl get nodes` reporting a Node as `NotReady` is the Node-level equivalent of the Pod failure states from [§98](./Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md), and applying [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s methodology one layer up the stack means learning to read Node conditions and kubelet health signals with the same precision.

**Precise definition:** A Node's `STATUS` column reflects its **`NodeStatus.conditions`** array, most importantly the **`Ready`** condition, which the kubelet itself reports to the API server via a periodic heartbeat (`node-status-update-frequency`, default 10s). `NotReady` means the API server has not received a healthy heartbeat within the configured grace period (`node-monitor-grace-period`, default 40s in the controller manager) — the Node's kubelet has either stopped running, is unable to reach the API server, or is reporting an unhealthy condition (`MemoryPressure`, `DiskPressure`, `PIDPressure`, or `NetworkUnavailable` set to `True`). This is distinct from a Pod-level failure precisely because a `NotReady` Node affects **every** Pod scheduled to it simultaneously — the node-lifecycle controller applies `NoSchedule`/`NoExecute` taints and, after a further grace period, begins evicting all Pods from the Node, which is exactly the mechanism that can make a single struggling Node look like a wave of unrelated Pod failures across several workloads.

## 2. Why This Matters

- **A single `NotReady` Node can masquerade as several unrelated Pod-level incidents** — if three Deployments each have one Pod stuck `Pending` or `Terminating` at the same moment, checking `kubectl get nodes` first, before diving into three separate Pod investigations, is almost always the faster path per [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s ISOLATE step.
- **The kubelet is the single most important process on every worker node** — it's a systemd-managed unit outside the Kubernetes API entirely, so `kubectl` commands alone cannot always diagnose a kubelet crash; you have to escalate to node-level access (`journalctl`, SSH) when the API server itself has no fresher information to offer.
- **`NotReady` triggers automatic Pod eviction after a delay, not immediately** — understanding the default `pod-eviction-timeout` behavior (and the `NoExecute` taint tolerations that delay it) is directly tested on the CKA exam and is essential for predicting when workloads on a struggling node will actually be rescheduled elsewhere.

🔑 **Key Takeaway:** A `NotReady` Node is a heartbeat failure reported by the kubelet, and diagnosing it requires two distinct toolsets — `kubectl describe node` for what the API server already knows from the last heartbeat, and `journalctl -u kubelet` / `crictl` directly on the node when the API server's information has gone stale because the kubelet itself has stopped reporting.

## 3. Prerequisites and Dependencies

Applies [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s structured troubleshooting methodology one layer up from [§98](./Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md)'s Pod-level failure states, to the Node. Back-references [§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md) (Node Components, Part 2 — kubelet, kube-proxy, container runtime architecture) for the underlying process model being diagnosed here. Forwards into [§100](./Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md), which applies the same methodology one further layer up, to control plane component failures.

## 4. Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────┐
│              Node Health Reporting and Where It Breaks              │
│                                                                     │
│   kubelet (on Node)                                                 │
│      │  every 10s: reports NodeStatus (Ready/Memory/Disk/PID)       │
│      ▼                                                              │
│   API Server  ◄── heartbeat received, Node marked Ready             │
│      │                                                              │
│      │  no heartbeat for > node-monitor-grace-period (40s default)  │
│      ▼                                                              │
│   node-lifecycle-controller marks Node NotReady                     │
│      │                                                              │
│      ├──► applies node.kubernetes.io/unreachable:NoSchedule taint   │
│      │                                                              │
│      └──► after pod-eviction-timeout (default 5m): NoExecute taint, │
│           Pods without matching tolerations are evicted             │
│                                                                     │
│   ── where the break actually happened (three distinct causes) ──   │
│                                                                     │
│   ┌────────────┐   ┌─────────────────┐   ┌───────────────────────┐  │
│   │ kubelet    │   │ kubelet running │   │ kubelet healthy,      │  │
│   │ process    │   │ but can't reach │   │ but MemoryPressure/   │  │
│   │ crashed/   │   │ API server      │   │ DiskPressure/         │  │
│   │ stopped    │   │ (network/cert)  │   │ PIDPressure = True    │  │
│   └────────────┘   └─────────────────┘   └───────────────────────┘  │
│         │                     │                        │            │
│         ▼                     ▼                        ▼            │
│   journalctl -u kubelet   check node network,    kubectl describe   │
│   shows process exit       kubelet client cert    node → Conditions │
└─────────────────────────────────────────────────────────────────────┘
```

- **The API server only knows what the last heartbeat told it** — once a kubelet stops reporting entirely, `kubectl describe node` freezes on stale, increasingly outdated information, and node-level access becomes necessary rather than optional.
- **Taints, not immediate deletion, are the mechanism** — a `NotReady` Node's Pods aren't torn down the instant the condition flips; the `NoSchedule` taint applies first, and `NoExecute` eviction follows only after `pod-eviction-timeout` elapses, giving a genuinely transient blip time to self-resolve without workload disruption.
- **Three structurally different causes produce the identical `NotReady` symptom** — a crashed kubelet process, a healthy kubelet unable to reach the API server, and a healthy, connected kubelet reporting genuine resource pressure all show up the same way in `kubectl get nodes`, and only node-level inspection distinguishes them.

## 5. Hands-On

### 5.1 Reading Node Conditions from the API Server's Perspective

**Purpose:** Start with what the API server already knows, per [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s cheapest-signal-first ordering, before escalating to node-level access.

**Syntax:**

```bash
kubectl get nodes
kubectl describe node <node> | grep -A15 Conditions
kubectl get node <node> -o jsonpath='{.status.conditions}'
```

**Example usage:**

```bash
$ kubectl get nodes
NAME     STATUS     ROLES    AGE   VERSION
node-1   Ready      <none>   40d   v1.29.4
node-2   NotReady   <none>   40d   v1.29.4

$ kubectl describe node node-2 | grep -A15 Conditions
Conditions:
  Type                 Status  LastHeartbeatTime                 Reason
  ----                 ------  -----------------                 ------
  MemoryPressure       False   Thu, 31 Jul 2026 09:14:02 +0000    KubeletHasSufficientMemory
  DiskPressure         False   Thu, 31 Jul 2026 09:14:02 +0000    KubeletHasNoDiskPressure
  PIDPressure          False   Thu, 31 Jul 2026 09:14:02 +0000    KubeletHasSufficientPID
  Ready                Unknown Thu, 31 Jul 2026 09:02:41 +0000    NodeStatusUnknown
```

**Production usage example:** `LastHeartbeatTime` on `Ready` is over ten minutes stale here while the other three conditions show a heartbeat that's also stale but at the same timestamp — this pattern (all conditions frozen at the same last-seen time, `Reason: NodeStatusUnknown`) specifically means the kubelet stopped reporting entirely, not that a real resource-pressure condition flipped; that distinction sends the next step toward node-level access (SSH, `journalctl`) rather than resource investigation.

**Common errors:** Treating `Ready: Unknown` the same as `Ready: False` — `Unknown` means the controller has no recent data at all (kubelet silent), while `False` means the kubelet is actively reporting itself unhealthy; the two point at different root causes and different fixes.

### 5.2 Diagnosing a Crashed or Unreachable kubelet

**Purpose:** Escalate to the node itself once the API server's information is confirmed stale, checking the kubelet process and its connectivity directly.

**Syntax:**

```bash
ssh <node>
systemctl status kubelet
journalctl -u kubelet -n 100 --no-pager
journalctl -u kubelet -f
```

**Example usage:**

```bash
node-2$ systemctl status kubelet
● kubelet.service - kubelet: The Kubernetes Node Agent
   Active: failed (Result: exit-code) since Thu 2026-07-31 09:02:38 UTC; 12min ago

node-2$ journalctl -u kubelet -n 20 --no-pager
Jul 31 09:02:38 node-2 kubelet[2145]: F0731 09:02:38.112233 2145 server.go:203] failed to run Kubelet: unable to load client CA file /var/lib/kubelet/pki/ca.crt: open /var/lib/kubelet/pki/ca.crt: no such file or directory
Jul 31 09:02:38 node-2 systemd[1]: kubelet.service: Main process exited, code=exited, status=1/FAILURE
```

**Production usage example:** The exact log line points at a missing client CA file, not a generic crash — this is a materially different fix (restoring or re-provisioning the kubelet's PKI material, often after a botched certificate rotation, [§109](../Part14/Section-109-Part14-Certificate-Rotation-Renewal.md)) than the more common "kubelet can't reach the API server" case, which instead shows repeated `Failed to connect to API server` or `x509: certificate has expired` messages in the same log stream.

**Common errors:** Restarting the kubelet service blindly (`systemctl restart kubelet`) without first reading the exit reason in the journal — a missing CA file or expired certificate will simply cause the same immediate failure on restart, wasting a cycle that reading the log first would have avoided.

### 5.3 Diagnosing Resource Pressure Conditions (MemoryPressure, DiskPressure, PIDPressure)

**Purpose:** Distinguish a genuinely connected, healthy kubelet reporting real node resource exhaustion from the silent-kubelet case in 5.2, since the fix path is entirely different.

**Syntax:**

```bash
kubectl describe node <node> | grep -A15 Conditions
df -h
free -h
crictl ps -a
crictl stats
```

**Example usage:**

```bash
$ kubectl describe node node-2 | grep -A5 Conditions
Conditions:
  Type            Status  Reason
  ----            ------  ------
  DiskPressure    True    KubeletHasDiskPressure
  Ready           False   KubeletNotReady

node-2$ df -h /var/lib/kubelet
Filesystem      Size  Used Avail Use% Mounted on
/dev/sda1        50G   48G  1.2G  97% /var/lib/kubelet

node-2$ crictl images | wc -l
214
```

**Production usage example:** A `DiskPressure: True` condition combined with `df -h` confirming the kubelet's filesystem is 97% full points directly at accumulated unused container images and dead container filesystems, not application misbehavior — the immediate fix is `crictl rmi --prune` (or letting the kubelet's own image garbage collection catch up) and the longer-term fix is provisioning more disk or lowering the kubelet's `imageGCHighThresholdPercent`.

**Common errors:** Investigating individual Pod specs for a `DiskPressure`-evicted workload as if it were an application bug, when the condition is Node-wide by definition — every Pod on that Node is equally at risk regardless of which one got evicted first.

## 6. Production Usage Notes

- **`kubectl get nodes -o wide` combined with `kubectl top nodes`** (requires metrics-server, [§92](../Part12/Section-92-Part12-Prometheus-Kubernetes-ServiceMonitors-Node-Exporter-kube-state-metrics.md)) gives a fast cluster-wide view of which Nodes are trending toward pressure before they actually flip `NotReady`, turning this into a proactive check rather than a reactive one.
- **A Node flapping between `Ready` and `NotReady` repeatedly** (rather than staying down) is a distinct pattern worth its own investigation — often a marginal network link, an overloaded kubelet missing its heartbeat deadline under load, or a systemd unit set to auto-restart after each crash — and is a materially different problem from a Node that goes down once and stays down.
- **`crictl` and `ctr` are the direct container-runtime-level tools** available once you're on the node itself, and are essential when `kubectl describe pod` output is itself unavailable because the kubelet that would normally report it is the very thing that's down.

## 7. Security Considerations

- **SSH access to worker nodes should be tightly restricted and audited separately from Kubernetes RBAC** — node-level debugging bypasses the API server's authorization layer entirely, so who can reach `journalctl -u kubelet` on a production node is a distinct access-control surface from who can run `kubectl` commands.
- **A missing or expired kubelet client certificate, as seen in 5.2, is itself a security-relevant failure mode** — certificate expiry silently taking nodes offline is exactly the kind of incident that certificate-rotation monitoring ([§109](../Part14/Section-109-Part14-Certificate-Rotation-Renewal.md)) is meant to prevent proactively.
- **`crictl` and direct container runtime access on a node can expose the contents of any Pod's containers**, regardless of the RBAC restrictions that would normally apply via the API server — node-level access is effectively cluster-admin-equivalent for anything scheduled to that node, and should be provisioned accordingly.

## 8. Common Troubleshooting Scenarios

| Symptom                                                         | Cause                                                                      | Fix                                                                                                                                  |
| --------------------------------------------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| `Ready: Unknown`, all conditions frozen at the same stale time  | kubelet process stopped reporting entirely (crashed, network partition)    | SSH to the node; check `systemctl status kubelet` and `journalctl -u kubelet` for the exact exit reason                              |
| `Ready: False`, `Reason: KubeletNotReady`, `DiskPressure: True` | Node's filesystem (often container image/log storage) is nearly full       | Prune unused images (`crictl rmi --prune`), clear logs, or provision more disk                                                       |
| kubelet log shows `x509: certificate has expired`               | kubelet's client certificate for API server auth has expired               | Rotate the kubelet's client certificate ([§109](../Part14/Section-109-Part14-Certificate-Rotation-Renewal.md), Certificate Rotation) |
| kubelet log shows repeated `Failed to connect to API server`    | Network path between node and control plane is broken, or a wrong endpoint | Check node network connectivity, DNS resolution of the API server endpoint, and firewall rules                                       |
| Node flaps between `Ready` and `NotReady` repeatedly            | Marginal network link or kubelet missing heartbeat deadline under CPU load | Investigate node resource saturation and network stability, not a one-time root cause                                                |

## 9. Best Practices

- Check `kubectl get nodes` first whenever multiple, seemingly unrelated Pods across different workloads show failures at the same time — a single struggling Node is a common shared root cause.
- Distinguish `Ready: Unknown` (kubelet silent, escalate to node access) from `Ready: False` (kubelet reporting itself unhealthy, check the specific condition) before choosing a diagnostic path.
- Read the exact `journalctl -u kubelet` exit reason before restarting the service — a certificate or configuration problem will simply recur immediately on restart if not fixed first.

## 10. Common Anti-Patterns / Mistakes

- **Diagnosing individual Pod failures across several Deployments independently**, missing that they all share a single Node that has gone `NotReady`.
- **Restarting the kubelet service reflexively** without reading its crash/exit log first, wasting a cycle when the same misconfiguration (missing cert, bad config) causes it to fail again immediately.
- **Treating `DiskPressure`/`MemoryPressure` as an application-level bug on whichever Pod happened to be evicted first**, rather than recognizing it as a Node-wide condition affecting every Pod scheduled there.

## 11. Interview Questions

**🎯 Beginner:** _"What does it mean when `kubectl get nodes` shows a Node as `NotReady`?"_
**Model answer:** It means the API server hasn't received a healthy heartbeat from that Node's kubelet within the configured grace period, which defaults to 40 seconds. The kubelet is supposed to report its status — including the `Ready` condition and resource-pressure conditions like `MemoryPressure` and `DiskPressure` — roughly every 10 seconds, and when that heartbeat stops arriving or reports an unhealthy condition, the node-lifecycle controller marks the Node `NotReady`. This matters because it can affect every Pod scheduled to that Node at once, not just one workload, so it's often the actual root cause behind what look like several unrelated Pod problems happening at the same time.
_What the interviewer is probing for:_ Basic understanding of the kubelet heartbeat mechanism and that `NotReady` is Node-wide, not Pod-specific.

**🎯 Intermediate:** _"A Node shows `Ready: Unknown` rather than `Ready: False`. Does that distinction matter?"_
**Model answer:** Yes, and it changes where I'd look next. `Ready: False` means the kubelet is still actively reporting to the API server, but it's telling the API server itself that something is wrong — for example, a genuine `DiskPressure` or `MemoryPressure` condition — so I'd investigate that specific condition on the node using tools like `df -h` or `crictl stats`. `Ready: Unknown` means the opposite: the API server has stopped receiving any heartbeat at all from that kubelet, so it has no current information to offer, and continuing to interrogate `kubectl describe node` further is pointless past a certain point — the next step has to be direct node access, checking whether the kubelet process is even still running via `systemctl status kubelet`, and if it is, checking network connectivity between the node and the control plane.
_What the interviewer is probing for:_ Precise understanding that `Unknown` versus `False` reflects a fundamentally different diagnostic situation — data absence versus a reported unhealthy state — and knowing to escalate to node-level tooling appropriately.

**🎯 Senior:** _"Walk through diagnosing a Node whose kubelet log shows repeated `x509: certificate has expired` errors."_
**Model answer:** This tells me the kubelet's client certificate, used to authenticate to the API server, has expired, which means the kubelet can no longer establish a TLS connection to report its status at all — that's why the Node shows `NotReady` (often with `Ready: Unknown` since heartbeats have stopped entirely). The fix is rotating that certificate, which in a `kubeadm`-managed cluster is typically handled via `kubeadm certs renew` or, in a properly configured cluster, should have been happening automatically via kubelet's certificate rotation feature before ever reaching expiry. Restarting the kubelet service alone won't help — it will simply fail to authenticate again immediately with the same expired certificate. Beyond fixing this one node, I'd treat an expired certificate reaching production as a monitoring gap: certificate expiry should be tracked and alerted on well before the actual expiration date, since discovering it via a `NotReady` Node in production means the monitoring that should have caught this proactively didn't exist or wasn't checked.
_What the interviewer is probing for:_ Recognizing that a TLS/auth-layer failure has a completely different fix path from a resource-pressure or process-crash failure, and connecting the incident back to a proactive monitoring gap rather than treating it as a one-off fix.

**🎯 Architect:** _"How would you design monitoring and automated remediation so `NotReady` Nodes are caught and, where possible, self-heal before paging anyone?"_
**Model answer:** I'd build detection on the same conditions this section relies on manually. Using kube-state-metrics ([§92](../Part12/Section-92-Part12-Prometheus-Kubernetes-ServiceMonitors-Node-Exporter-kube-state-metrics.md)) feeding Prometheus, I'd alert on `kube_node_status_condition` for `Ready` transitioning to `False` or `Unknown`, with a short delay window to avoid paging on a single missed heartbeat that self-resolves, and separately alert on `DiskPressure`/`MemoryPressure` conditions trending toward `True` well before they actually flip, using node-exporter metrics for disk and memory headroom as a leading indicator rather than waiting for the kubelet's own condition to fire. For certificate expiry specifically, I'd monitor certificate expiration dates directly (many teams export this as its own Prometheus metric) and alert weeks in advance, since that failure mode is entirely preventable and should never reach a production `NotReady` incident. Where remediation can be safely automated, I'd consider node auto-replacement in cloud-managed node groups — if a Node fails health checks past a threshold, the underlying infrastructure (not Kubernetes itself) terminates and replaces the instance, which handles the common case of a bad instance or disk far more reliably than manual SSH-based recovery. Finally, I'd feed genuinely novel node-failure root causes back into the team's runbook ([§105](./Section-105-Part13-Incident-Case-Studies-Runbooks.md)), keeping the manual `journalctl`/`crictl` diagnostic path from this section as the escalation tier for whatever automated detection and remediation doesn't already cover.
_What the interviewer is probing for:_ Ability to convert manual node-level diagnostic knowledge into proactive, layered monitoring plus automated remediation where safe, while still valuing the manual escalation path for genuinely novel failures.

## 12. Common Misconceptions

1. **"A `NotReady` Node means the physical machine is down."** It only means the kubelet stopped reporting a healthy heartbeat — the underlying machine, and even the kubelet process, may still be running; the cause could be a certificate, network, or resource-pressure issue entirely separate from hardware failure.
2. **"`Ready: Unknown` and `Ready: False` mean the same thing."** `Unknown` means the API server has no recent data because the kubelet has stopped reporting; `False` means the kubelet is actively reporting itself unhealthy — they point at different root causes.
3. **"Restarting the kubelet always fixes a `NotReady` Node."** If the underlying cause is a missing certificate, expired credentials, or a persistent configuration error, the kubelet will simply fail again immediately on restart until the actual root cause is addressed.
4. **"Pods on a `NotReady` Node are deleted immediately."** The node-lifecycle controller applies a `NoSchedule` taint first, and only evicts Pods (`NoExecute`) after `pod-eviction-timeout` elapses, giving transient issues time to self-resolve.

## 13. 🔑 Key Takeaways

- `NotReady` is a Node-wide heartbeat failure reported by the kubelet, and can be the shared root cause behind several seemingly unrelated Pod-level incidents at once.
- `Ready: Unknown` (kubelet silent, escalate to node access) and `Ready: False` (kubelet reporting a specific unhealthy condition) require different diagnostic paths — distinguish them before choosing a next step.
- `journalctl -u kubelet` and `systemctl status kubelet` are essential once the API server's information about a Node is confirmed stale, and reading the exact exit reason before restarting avoids wasted cycles.
- `MemoryPressure`/`DiskPressure`/`PIDPressure` conditions are genuine node-level resource exhaustion, distinct from a silent or crashed kubelet, and require capacity or garbage-collection fixes rather than certificate or network fixes.
- Taints (`NoSchedule` then `NoExecute` after a delay), not immediate deletion, govern how and when Pods actually leave a `NotReady` Node.

## 14. Related Concepts & What's Next

This section moved [§97](./Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s structured troubleshooting methodology one layer up from [§98](./Section-98-Part13-Pod-Failure-States-CrashLoopBackOff-ImagePullBackOff-Pending-Evicted.md)'s Pod-level failure states to the Node, drawing on the kubelet/kube-proxy/container-runtime architecture from [§9](../Part2/Section-09-Part2-Node-Components-Kubelet-Kube-Proxy-Container-Runtime.md) to explain exactly how and why a Node reports `NotReady`, and how to escalate from API-server-visible signals to direct node-level tooling. [§100](./Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md) moves one layer further up the stack, applying the same methodology to control plane component failures — API server, etcd, and scheduler outages — which is the layer above individual Nodes entirely.

**Next Section:** [§100](./Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md) — `Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md`
