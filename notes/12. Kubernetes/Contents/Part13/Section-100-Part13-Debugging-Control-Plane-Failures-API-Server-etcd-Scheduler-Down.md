# Section 100 (Part 13): Debugging Control Plane Failures (API Server, etcd, Scheduler Down)

## 1. Definition

**Plain language:** §99 covered a struggling Node — one machine among potentially hundreds. This section moves up one more layer, to the small handful of components that, if broken, can affect the entire cluster at once: the API server, etcd, and the scheduler. A `NotReady` Node degrades some workloads; a down control plane component can silently degrade the whole cluster's ability to change state at all, even while every existing Pod keeps running unaffected.

**Precise definition:** The control plane (§8) consists of the **kube-apiserver** (the sole entry point for all reads and writes to cluster state), **etcd** (the backing key-value store holding all cluster state), and **kube-scheduler** (assigns unscheduled Pods to Nodes) alongside kube-controller-manager and cloud-controller-manager. Because these components sit above the per-Node kubelet layer, their failure modes are distinctive: an API server outage manifests as `kubectl` commands failing outright (connection refused, timeouts) while already-running Pods on healthy Nodes continue serving traffic unaffected, since kubelets and kube-proxy operate independently once configured. An etcd failure manifests as the API server itself staying up but every read or write operation failing or hanging, since the API server has no state store to read from or write to. A scheduler failure manifests narrowly — existing Pods are entirely unaffected, but any _new_ unscheduled Pod stays `Pending` indefinitely with no `FailedScheduling` Event at all, because no scheduler process is running to even attempt the assignment. Distinguishing which of these three specific components has failed, using the correct isolation signal for each, is the core skill this section builds on top of §97's general methodology.

## 2. Why This Matters

- **Control plane failures are the rare case where "kubectl isn't working" doesn't mean "nothing is working"** — in a self-managed cluster with a single API server instance down, application traffic to already-running Pods is frequently completely unaffected, and panicking about a full outage when only cluster _management_ is impaired wastes critical incident-response time.
- **An etcd failure is the single highest-severity control plane failure possible**, since it holds all cluster state — a corrupted or unavailable etcd cluster can mean total, unrecoverable loss of the ability to manage the cluster at all, which is precisely why etcd backup and restore procedures (§14, Part 14) exist as a dedicated topic.
- **A silently dead scheduler is one of the most deceptive control plane failures**, because it produces no error at all — no `FailedScheduling` Event, no crash visible from `kubectl`, just Pods that stay `Pending` forever — and recognizing "total silence" itself as a diagnostic signal, distinct from the `FailedScheduling` Events covered in §98, is directly assessed on the CKA exam.

🔑 **Key Takeaway:** The three core control plane components fail in three structurally distinct, non-overlapping ways — API server down means `kubectl` itself fails while running Pods keep serving; etcd down means the API server responds but every state read/write fails; scheduler down means everything looks calm except new Pods silently never leave `Pending` — and correctly attributing a symptom to the right one of these three is the entire isolation step at this layer.

## 3. Prerequisites and Dependencies

Applies §97's structured troubleshooting methodology at the control plane layer, following §99's Node-level application of the same approach. Back-references §8 (Control Plane Components, Part 2), §10 (etcd Deep Dive, Part 2 — data model and Raft consensus, essential for understanding etcd failure modes), and §14 (Scheduler Internals Preview, Part 2 — filtering and scoring phases). Forwards into §101, which continues Part 13's scenario-driven approach into networking-specific troubleshooting.

## 4. Architecture Diagram

```text
┌──────────────────────────────────────────────────────────────────────────┐
│           Three Control Plane Components, Three Failure Modes            │
│                                                                          │
│   kubectl ──► kube-apiserver ──► etcd ──► kube-scheduler ──► kubelet     │
│                    │                │             │             │        │
│                    ▼                ▼             ▼             ▼        │
│       ┌────────────────┐  ┌──────────────┐ ┌──────────────┐ ┌─────────┐  │
│       │ API server     │  │ etcd fails   │ │ Scheduler    │ │ (§99,   │  │
│       │ down:          │  │ (or          │ │ down:        │ │ Node    │  │
│       │                │  │  unreachable)│ │              │ │ layer,  │  │
│       │ kubectl        │  │              │ │ new Pods     │ │ already │  │
│       │ "connection    │  │ API server   │ │ stay Pending │ │ covered)│  │
│       │  refused"      │  │ up, but      │ │ FOREVER,     │ │         │  │
│       │                │  │ every read/  │ │ zero Events  │ │         │  │
│       │ Running Pods   │  │ write hangs  │ │ at all       │ │         │  │
│       │ UNAFFECTED     │  │ or times out │ │              │ │         │  │
│       │ (kubelet works │  │              │ │ Existing     │ │         │  │
│       │  independently)│  │              │ │ Pods         │ │         │  │
│       │                │  │              │ │ UNAFFECTED   │ │         │  │
│       └────────────────┘  └──────────────┘ └──────────────┘ └─────────┘  │
│                                                                          │
│   Check order per §97: kubectl reachable? → etcd health? → scheduler     │
│   process/logs? — each answer eliminates one component definitively      │
└──────────────────────────────────────────────────────────────────────────┘
```

- **The failure surface shrinks as you move right along the chain** — an API server failure is the most visible (nothing works via `kubectl`) but least disruptive to already-running workloads; a scheduler failure is the least visible but only affects Pods that haven't been placed yet.
- **etcd sits "behind" the API server in this diagram deliberately** — you cannot query etcd's health through normal `kubectl` commands if the API server itself is down, which is why etcd diagnosis sometimes requires direct `etcdctl` access on a control plane node, bypassing `kubectl` entirely.
- **Kubelets and kube-proxy are explicitly Node-local and don't depend on a live control plane connection to keep already-configured Pods running** — this is precisely why "the whole cluster is down" is so often the wrong read on what's actually a control-plane-only outage.

## 5. Hands-On

### 5.1 Diagnosing an Unreachable API Server

**Purpose:** Confirm whether the API server itself is the failure point before assuming anything about etcd or the scheduler.

**Syntax:**

```bash
kubectl cluster-info
kubectl get --raw='/healthz'
curl -k https://<control-plane-ip>:6443/healthz
crictl ps | grep kube-apiserver
journalctl -u kubelet -n 50 | grep apiserver
```

**Example usage:**

```bash
$ kubectl cluster-info
Kubernetes control plane is running at https://10.0.1.10:6443
Unable to connect to the server: dial tcp 10.0.1.10:6443: connect: connection refused

$ ssh control-plane-1
control-plane-1$ crictl ps -a | grep kube-apiserver
a3f9e1c22b1d   kube-apiserver:v1.29.4   Exited (1) 2 minutes ago

control-plane-1$ crictl logs a3f9e1c22b1d --tail 20
E0731 09:20:11.442211 1 run.go:74] "command failed" err="context deadline exceeded" while dialing etcd
```

**Production usage example:** `connection refused` on port 6443 confirms the API server process itself isn't listening at all — combined with `crictl` showing the static Pod exited and its log showing a `context deadline exceeded` dialing etcd, the actual root cause here is upstream of the API server: etcd is unreachable, and the API server is crash-looping (as a static Pod, kubelet keeps restarting it) because it cannot start without a working connection to its data store.

**Common errors:** Assuming "kubectl can't connect" always means the API server binary itself crashed — the more common real-world cause, as shown, is the API server failing its own startup dependency check against etcd, which requires checking etcd next rather than restarting the API server repeatedly.

### 5.2 Diagnosing an etcd Failure

**Purpose:** Confirm etcd's health directly, bypassing `kubectl` where the API server can't be reached, since etcd is the actual data store behind every cluster read and write.

**Syntax:**

```bash
sudo ETCDCTL_API=3 etcdctl --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  endpoint health
crictl ps -a | grep etcd
journalctl -u kubelet | grep etcd
```

**Example usage:**

```bash
control-plane-1$ sudo ETCDCTL_API=3 etcdctl --endpoints=https://127.0.0.1:2379 \
  --cacert=/etc/kubernetes/pki/etcd/ca.crt \
  --cert=/etc/kubernetes/pki/etcd/server.crt \
  --key=/etc/kubernetes/pki/etcd/server.key \
  endpoint health
{"level":"warn","msg":"health check failed","endpoint":"https://127.0.0.1:2379","error":"context deadline exceeded"}
https://127.0.0.1:2379 is unhealthy: failed to commit proposal: context deadline exceeded

control-plane-1$ df -h /var/lib/etcd
Filesystem  Size  Used Avail Use% Mounted on
/dev/sdb1    20G   20G     0 100% /var/lib/etcd
```

**Production usage example:** `failed to commit proposal: context deadline exceeded` combined with `/var/lib/etcd` at 100% disk usage points precisely at etcd being unable to persist Raft log entries because its dedicated volume is full — a genuinely common self-inflicted control plane outage, and the fix (freeing disk, then addressing etcd's `--auto-compaction` and defragmentation settings, per §10) is entirely different from a network partition between etcd members in a multi-node etcd cluster, which would instead show `etcdserver: request timed out` with leader-election-related log lines.

**Common errors:** Restarting the etcd static Pod repeatedly without checking disk space or the Raft cluster's member health (`etcdctl member list`) first — if the underlying volume is full, a restart alone doesn't free space and etcd fails identically on the next attempt.

### 5.3 Diagnosing a Down or Unresponsive Scheduler

**Purpose:** Recognize the distinctive "total silence" signature of a dead scheduler — no Events at all, not even a `FailedScheduling` message — and confirm it directly against the scheduler's own process health.

**Syntax:**

```bash
kubectl get pods -A --field-selector=status.phase=Pending
kubectl describe pod <pending-pod> | grep -A5 Events
crictl ps -a | grep kube-scheduler
kubectl get pods -n kube-system -l component=kube-scheduler
```

**Example usage:**

```bash
$ kubectl describe pod new-worker-8f2c1 -n batch | grep -A3 Events
Events:          <none>

$ crictl ps -a | grep kube-scheduler
b7e2a91d3c4f   kube-scheduler:v1.29.4   Exited (1) 8 minutes ago

$ crictl logs b7e2a91d3c4f --tail 15
E0731 09:25:44.881122 1 leaderelection.go:332] error retrieving resource lock kube-system/kube-scheduler: etcdserver: request timed out
```

**Production usage example:** `Events: <none>` on a Pending Pod — genuinely zero Events, not a `FailedScheduling` warning as covered in §98 — is itself the signature of "no scheduler process attempted to handle this Pod at all," which is a categorically different situation from `FailedScheduling` (scheduler running, actively rejecting placement); confirming the scheduler's static Pod has actually exited, and that its own crash log traces back to the same etcd unavailability diagnosed above, ties this specific symptom back to the same upstream root cause rather than treating it as an independent scheduler bug.

**Common errors:** Investigating the Pending Pod's own spec (affinity rules, taints, resource requests) when the actual signal — zero Events whatsoever — already rules out the scheduler having evaluated the Pod at all; that symptom should immediately redirect to checking the scheduler process itself, not the Pod spec.

## 6. Production Usage Notes

- **In production, control plane components almost always run as multi-replica, highly-available deployments** (stacked or external etcd across 3+ nodes, multiple API server instances behind a load balancer, per §15's HA architectures) — a single component instance failing in a properly built HA cluster should be a non-event handled by failover, not an outage, and treating any single-instance failure as a full incident is worth calibrating against the actual cluster topology in use.
- **Static Pod manifests for the API server, scheduler, and controller-manager live in `/etc/kubernetes/manifests/` on control plane nodes** in a `kubeadm`-based cluster — the kubelet watches this directory directly and restarts these components automatically on crash, which is why they show up via `crictl`/`journalctl` rather than `kubectl get pods` when they're crash-looping badly enough to never register with the API server.
- **etcd's disk performance (specifically write latency) is a first-class production concern**, not just capacity — etcd is highly sensitive to disk fsync latency, and a healthy-looking etcd process on a slow disk can produce exactly the same "leader election" instability symptoms as a genuine network partition.

## 7. Security Considerations

- **`etcdctl` access requires the etcd server's own client certificates**, which are among the most sensitive credentials in the entire cluster — anyone with access to `/etc/kubernetes/pki/etcd/` effectively has unrestricted read/write access to all cluster state, bypassing every RBAC rule enforced at the API server layer entirely.
- **A compromised or overly-permissive static Pod manifest directory (`/etc/kubernetes/manifests/`) on any control plane node is a full cluster-compromise vector** — anyone who can write there can get the kubelet to run an arbitrary container with control-plane-level access, making filesystem permissions on that directory as critical as any RBAC policy.
- **etcd should never be exposed on a network-reachable interface without mutual TLS**, since it has no independent authorization model beyond client certificate validation — this is a foundational, non-negotiable hardening requirement distinct from anything configured at the Kubernetes API layer.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Cause                                                                      | Fix                                                                                                             |
| -------------------------------------------------------------------------- | -------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| `kubectl` returns `connection refused`, running Pods still serving traffic | API server process down or unreachable, kubelets operate independently     | Check API server static Pod/process via `crictl`/`journalctl` on the control plane node                         |
| API server reachable, but every `kubectl` command hangs or times out       | etcd unavailable — API server has no data store to read from/write to      | Check etcd health directly with `etcdctl endpoint health`; check disk space and Raft member status (§10)        |
| New Pods stay `Pending` forever with zero Events at all                    | kube-scheduler process is down and never evaluated the Pod                 | Check scheduler static Pod/process health via `crictl`; restart or fix its root cause (often etcd connectivity) |
| etcd logs show `mvcc: database space exceeded`                             | etcd's data store hit its storage quota without compaction/defragmentation | Run `etcdctl compact`/`defrag`, and check `--quota-backend-bytes` and auto-compaction settings (§10)            |
| API server static Pod crash-looping, log shows etcd dial errors            | Root cause is upstream — etcd, not the API server itself                   | Fix etcd first; the API server should recover automatically once etcd is healthy again                          |

## 9. Best Practices

- Check `kubectl cluster-info`/API server reachability first, then etcd health, then scheduler process health, in that order — each successive component depends on the one before it, so isolating from the front of the chain avoids chasing downstream symptoms of an upstream cause.
- Treat "zero Events at all" on a Pending Pod as a distinct, more severe signal than a `FailedScheduling` Event — the former points at the scheduler process itself being down, not a placement constraint issue.
- Never restart a control plane static Pod repeatedly without first reading its crash log — API server and scheduler failures very commonly trace back to an upstream etcd problem that a restart alone won't fix.

## 10. Common Anti-Patterns / Mistakes

- **Declaring a full cluster outage the moment `kubectl` stops responding**, without checking whether already-running Pods on healthy Nodes are actually still serving traffic unaffected.
- **Restarting the API server or scheduler static Pod repeatedly** without checking etcd's health first, when an upstream etcd failure is a very common actual root cause of both.
- **Investigating a Pending Pod's spec for constraint issues** when the Events list is completely empty, missing that "zero Events" itself signals the scheduler never evaluated the Pod at all.

## 11. Interview Questions

**🎯 Beginner:** _"If `kubectl get pods` stops working entirely, does that mean your application is down?"_
**Model answer:** Not necessarily, and that's actually one of the more important things to understand about Kubernetes architecture. `kubectl` talks to the API server, and if the API server is down or unreachable, cluster _management_ — creating, updating, or querying resources — stops working. But Pods that are already scheduled and running keep running independently, because the kubelet on each Node and kube-proxy don't need a live connection to the control plane to keep executing what they were already told to do. So application traffic to existing Pods is frequently completely unaffected even during a control plane outage — the actual impact is that you temporarily can't deploy changes, scale anything, or observe cluster state through the normal API, not that running workloads stop serving requests.
_What the interviewer is probing for:_ Understanding that the control plane and data plane are architecturally decoupled, and that a management-plane outage is not automatically an application outage.

**🎯 Intermediate:** _"The API server is reachable, but every `kubectl` command just hangs or times out. What's your first hypothesis, and how do you confirm it?"_
**Model answer:** My first hypothesis would be etcd — the API server itself might be up and accepting connections, but if it can't read from or write to its backing data store, every operation that needs to touch cluster state will hang or eventually time out, while the API server process itself stays alive. I'd confirm this by going directly to a control plane node and running `etcdctl endpoint health` against the local etcd instance with the appropriate client certificates, rather than continuing to poke at `kubectl`, since `kubectl` timing out doesn't tell me anything more specific than "something downstream of the API server is broken." I'd also check etcd's own logs and disk usage on its dedicated volume, since a full disk or hitting etcd's storage quota is a very common real-world cause of exactly this symptom.
_What the interviewer is probing for:_ Correctly attributing "API server up, but operations hang" to etcd specifically rather than the API server itself, and knowing the direct `etcdctl` diagnostic path that bypasses `kubectl` entirely.

**🎯 Senior:** _"A newly created Pod stays `Pending` indefinitely, and `kubectl describe pod` shows zero Events — not even a `FailedScheduling` warning. Walk through your reasoning."_
**Model answer:** Zero Events at all is a fundamentally different signal from a `FailedScheduling` Event, and I'd treat it as such immediately rather than investigating the Pod's own spec for constraint problems. A `FailedScheduling` Event means the scheduler is running and actively evaluated the Pod, just couldn't find a suitable Node — that's a capacity or constraint problem, covered under §98's Pending scenarios. Genuinely zero Events means no scheduler ever picked the Pod up to evaluate it in the first place, which points at the scheduler process itself being down or non-functional. I'd go check the scheduler's static Pod or process directly via `crictl ps -a` and its logs, and I'd specifically look for whether its crash traces back to something upstream — in my experience, scheduler failures very often aren't a bug in the scheduler itself but a failure to maintain its leader-election lease against etcd, which ties back to the same etcd health check I'd already be running for any other control plane symptom. I wouldn't consider this fixed until I've confirmed the scheduler process is not just running again, but that new test Pods are actually receiving `Scheduled` Events.
_What the interviewer is probing for:_ Distinguishing "scheduler ran but rejected" from "scheduler never ran" as fundamentally different diagnostic branches, and connecting scheduler health back to its etcd-backed leader election dependency rather than treating it in isolation.

**🎯 Architect:** _"Design the monitoring and architecture choices that minimize the blast radius of control plane component failures in a production cluster."_
**Model answer:** The most important structural decision is running a genuinely highly-available control plane (§15) — at least three etcd members across separate failure domains using Raft's quorum-based consensus, multiple API server instances behind a load balancer with health checks, and leader-elected scheduler and controller-manager instances so a single instance crash triggers failover rather than an outage. On top of that architecture, I'd monitor each component's specific failure signature separately rather than a single generic "control plane down" alert: API server availability and latency via synthetic `kubectl`-equivalent health checks against the load balancer endpoint, etcd's own `/health` endpoint plus Raft leader-election metrics and disk fsync latency (etcd is exceptionally sensitive to slow disks), and scheduler health via its leader-election lease staying current, alongside a direct check that test Pods continue receiving `Scheduled` Events over time as an end-to-end confirmation the scheduler is genuinely functional, not just that its process is technically running. I'd also make sure etcd backups (§14, Part 14) run on a tested, automated schedule with periodic restore drills, since etcd is the one component where "highly available" doesn't fully substitute for "recoverable" if a bad write or corruption propagates across the whole quorum. Finally, I'd document the exact chain-of-dependency reasoning from this section — API server depends on etcd, scheduler depends on etcd via leader election — directly in the incident runbook (§105), so an on-call engineer investigates in dependency order rather than symptom order during a real 3 a.m. page.
_What the interviewer is probing for:_ Combining architectural HA design (quorum, load-balanced API servers, leader election) with component-specific monitoring that reflects each component's actual failure mode, plus recognizing that etcd backup/restore is a distinct concern from etcd availability.

## 12. Common Misconceptions

1. **"If `kubectl` isn't working, the whole cluster and every application is down."** The control plane and data plane are decoupled — already-running Pods on healthy Nodes typically keep serving traffic unaffected by a control-plane-only outage.
2. **"An API server crash-loop is always a bug in the API server itself."** A very common real cause is the API server failing its own startup dependency on etcd — fixing etcd resolves the API server automatically in that case, without touching the API server directly at all.
3. **"`FailedScheduling` and zero Events both just mean 'the Pod isn't scheduled yet.'"** They're diagnostically opposite signals — `FailedScheduling` means the scheduler evaluated and rejected placement (a constraint/capacity issue), while zero Events means the scheduler never evaluated the Pod at all (a scheduler-health issue).
4. **"Restarting a crash-looping control plane component will eventually fix it."** If the root cause is upstream (etcd unavailable, a full disk, an expired certificate), the component fails identically on every restart until that upstream cause is actually addressed.

## 13. 🔑 Key Takeaways

- API server, etcd, and scheduler failures each produce a structurally distinct symptom — `kubectl` unreachable, `kubectl` reachable but hanging, and Pods silently stuck `Pending` with zero Events, respectively — and correctly attributing the symptom to the right component is the isolation step at this layer.
- Already-running Pods on healthy Nodes typically continue serving traffic during a control-plane-only outage, since kubelets and kube-proxy operate independently of a live control plane connection.
- etcd sits upstream of both the API server and the scheduler — many API server crash-loops and scheduler failures trace back to etcd unavailability rather than a bug in the component itself, so check etcd health before assuming otherwise.
- "Zero Events at all" on a Pending Pod is a distinct, more severe signal than `FailedScheduling`, pointing at the scheduler process itself being down rather than a placement constraint.
- A properly built HA control plane (§15) turns single-instance component failures into non-events via quorum and load-balanced failover, but etcd backup and restore (§14, Part 14) remains a separate, necessary safeguard beyond availability alone.

## 14. Related Concepts & What's Next

This section moved §97's structured troubleshooting methodology one further layer up from §99's Node-level diagnosis to the control plane itself, drawing on the component architecture from §8, etcd's data model and consensus mechanics from §10, and the scheduler's filtering/scoring internals from §14 to explain exactly how and why each control plane component's failure produces its own distinctive symptom. §101 shifts from vertical layers (Pod, Node, control plane) to a horizontal, scenario-driven approach, applying this same methodology to specific networking failures — unreachable Services and DNS resolution failures.

**Next Section:** §101 — `Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md`
