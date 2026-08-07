# Section 102 (Part 13): Storage Troubleshooting Scenarios (PVC Pending, Mount Errors)

## 1. Definition

**Plain language:** [§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md)'s toolkit gave you the ordered checklist for a stuck PVC or failed mount. This section goes one level deeper into specific, named failure scenarios — a StorageClass whose provisioner itself is failing (not just missing), a PV whose node affinity conflicts with where a Pod actually needs to run, and a CSI driver Pod crashing in a way that silently breaks storage for every workload on a node, not just one.

**Precise definition:** This section catalogs **specific storage failure scenarios** that extend beyond [§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md)'s general diagnostic flow — dynamic-provisioning failures where the StorageClass and provisioner both exist but the provisioning call itself errors out (quota, IAM, or backend API failures), volume node-affinity conflicts examined in more topological depth than [§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md)'s introduction, and CSI driver crash scenarios where the node or controller plugin itself is unhealthy, producing symptoms that look like dozens of unrelated PVC problems at once. Each scenario follows the same object-state-first, node-access-last discipline established in [§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md) and [§100](./Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md).

## 2. Why This Matters

- **A StorageClass and its provisioner both existing and looking healthy doesn't guarantee provisioning succeeds** — cloud-side quota exhaustion, expired or under-scoped IAM credentials, and backend API throttling all produce a `Pending` PVC even when every Kubernetes-side object looks correct, and the real cause only surfaces in the CSI controller's own logs.
- **Node affinity conflicts are easy to half-diagnose** — recognizing "volume node affinity conflict" in a `FailedScheduling` event ([§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md)) is only the first half; understanding _why_ the volume landed in the wrong zone or node in the first place (immediate binding, a node pool that changed after provisioning, manual PV creation with a wrong label) determines whether the real fix is a StorageClass change, a node pool fix, or neither.
- **A single unhealthy CSI driver Pod can present as many unrelated-looking tickets simultaneously** — "PVC A is stuck," "PVC B won't mount," "PVC C's Pod is CrashLooping on a mount timeout" can all trace back to one crashing CSI node plugin on one node, and treating them as three separate investigations wastes significant time.

🔑 **Key Takeaway:** These scenarios share a common trap — the Kubernetes-side objects (StorageClass, PVC, PV) can all look entirely correct while the actual failure lives one layer down, in the CSI driver's own logs, the cloud provider's API responses, or the driver Pod's own health — so escalating to that layer promptly, once object-level checks are exhausted, is what separates a fast resolution from a long one.

## 3. Prerequisites and Dependencies

Builds directly on [§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md) (storage troubleshooting toolkit) and [§100](./Section-100-Part13-Debugging-Control-Plane-Failures-API-Server-etcd-Scheduler-Down.md) (Part 13's structured troubleshooting methodology), and assumes familiarity with [§59](../Part8/Section-59-Part8-StorageClasses-Dynamic-Provisioning.md) (StorageClasses/dynamic provisioning) and [§60](../Part8/Section-60-Part8-CSI-Container-Storage-Interface-Architecture.md) (CSI architecture). Back-references [§101](./Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md) (networking troubleshooting scenarios) as the prior section in Part 13's scenario sequence, and forwards into [§103](./Section-103-Part13-Application-Level-Debugging-Misconfigured-Probes-Resource-Starvation-OOMKilled.md) (application-level debugging).

## 4. Architecture Diagram

```text
   Three storage scenarios and where they actually break

   Scenario A: Provisioner exists, but the call itself fails
   ┌───────────────────────────────────────────────────────────────┐
   │ StorageClass: fast-ssd  →  provisioner: ebs.csi.aws.com       │
   │  Pods:  ebs-csi-controller-xxxx     Running                   │
   │                                          │                    │
   │                                          ▼                    │
   │           csi-provisioner container logs:                     │
   │           "VolumeLimitExceeded: max volumes per instance"     │
   │           → PVC stays Pending despite everything looking fine │
   └───────────────────────────────────────────────────────────────┘

   Scenario B: Node affinity conflict, deeper topology view
   ┌───────────────────────────────────────────────────────────────┐
   │  StorageClass: Immediate binding                              │
   │  Provisioner picks zone us-east-1a  (no Pod scheduled yet)    │
   │                                          │                    │
   │  Meanwhile: node pool "us-east-1a" scaled to zero             │
   │  or Pod has nodeSelector restricting it to us-east-1b         │
   │                                          ▼                    │
   │  PV permanently bound to a zone with zero eligible nodes      │
   └───────────────────────────────────────────────────────────────┘

   Scenario C: CSI driver Pod itself unhealthy
   ┌───────────────────────────────────────────────────────────────┐
   │  node-3:  csi-node-plugin  CrashLoopBackOff                   │
   │                                          │                    │
   │        ┌─────────────┬─────────────┬─────┴────────┐           │
   │        ▼             ▼             ▼                          │
   │PVC-A Pending  PVC-B Failed Mount  PVC-C mount timeout         │
   │   (all Pods scheduled onto node-3, all fail for one reason)   │
   └───────────────────────────────────────────────────────────────┘
```

- Scenario A's key signal is that every Kubernetes-native object check passes — the failure only appears in the CSI controller container's own logs, one layer below what [§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md)'s Step 2 checks.
- Scenario B extends [§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md)'s introduction of "volume node affinity conflict" by tracing the failure back to _why_ the mismatch occurred — usually `Immediate` binding combined with a node pool topology that shifted after the volume was already provisioned.
- Scenario C's key signal is the pattern across tickets, not any single ticket — multiple, differently-worded storage failures all tracing to Pods scheduled on the same node is the tell that the CSI node plugin itself, not any individual PVC, is the root cause.

## 5. Hands-On

### 5.1 Provisioner Healthy, But Provisioning Calls Fail (Quota/IAM)

**Purpose:** Diagnose a `Pending` PVC where the StorageClass exists and the CSI controller Pod is Running, so [§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md)'s Step 2 passes cleanly, but the actual provisioning API call is failing.

**Syntax:**

```bash
kubectl describe pvc <pvc-name> -n <namespace>
kubectl logs -n kube-system <csi-controller-pod> -c csi-provisioner --tail=50
```

**Example usage:**

```bash
$ kubectl get storageclass fast-ssd
NAME       PROVISIONER       RECLAIMPOLICY   VOLUMEBINDINGMODE
fast-ssd   ebs.csi.aws.com   Delete          WaitForFirstConsumer

$ kubectl get pods -n kube-system -l app=ebs-csi-controller
NAME                                  READY   STATUS    RESTARTS
ebs-csi-controller-7d9f8b6c4d-abc12   6/6     Running   0

$ kubectl logs -n kube-system ebs-csi-controller-7d9f8b6c4d-abc12 -c csi-provisioner --tail=20
E0731 provisioner.go:284 error creating volume: rpc error: code = ResourceExhausted
  desc = VolumeLimitExceeded: instance has reached maximum EBS volume attachment limit
```

**Production usage example:** Both the StorageClass and the CSI controller Pod pass every object-level check — this is exactly the class of failure where escalating directly to the `csi-provisioner` sidecar container's logs (not the main driver container) is necessary, since the actual `ResourceExhausted`/`VolumeLimitExceeded` error only appears there, and no amount of re-checking the StorageClass or PVC YAML would reveal it.

**Common errors:** Checking only the main CSI driver container's logs and missing the `csi-provisioner` (or `csi-attacher`, `csi-resizer`) sidecar containers, which run in the same Pod but log the actual provisioning/attach errors separately — always check every container in a multi-container CSI controller Pod, not just the first one listed.

### 5.2 Node Affinity Conflict Traced to Its Root Cause

**Purpose:** Go beyond recognizing "volume node affinity conflict" ([§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md)) to determine _why_ the volume ended up in a zone with no eligible nodes, and apply the correct fix at the right layer.

**Syntax:**

```bash
kubectl get storageclass <name> -o jsonpath='{.volumeBindingMode}'
kubectl get pv <pv-name> -o jsonpath='{.spec.nodeAffinity}'
kubectl get nodes -L topology.kubernetes.io/zone
```

**Example usage:**

```bash
$ kubectl get storageclass fast-ssd -o jsonpath='{.volumeBindingMode}'
Immediate

$ kubectl get pv pvc-9f8e7d -o jsonpath='{.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0].values}'
["us-east-1a"]

$ kubectl get nodes -L topology.kubernetes.io/zone
NAME      STATUS   ZONE
node-1    Ready    us-east-1b
node-2    Ready    us-east-1b
# no nodes remain in us-east-1a — that node pool was scaled to zero last week
```

**Production usage example:** The real root cause here isn't just "wrong zone" in the abstract — it's that the StorageClass still used `Immediate` binding, so the volume was provisioned into `us-east-1a` before any Pod was being scheduled, and a subsequent, unrelated node-pool scale-down of `us-east-1a` (done for cost reasons, with no awareness it would strand existing volumes) left the PV permanently unusable; the durable fix is switching the StorageClass to `WaitForFirstConsumer` going forward, not just deleting and recreating this one PVC.

**Common errors:** Fixing only the immediate symptom (delete/recreate the one stuck PVC) without changing the StorageClass's `volumeBindingMode`, guaranteeing the identical conflict recurs the next time a node pool's zone footprint changes.

### 5.3 CSI Driver Pod Crash Presenting as Multiple Unrelated Tickets

**Purpose:** Recognize the pattern where several differently-worded storage failures across different PVCs and Pods all trace back to a single unhealthy CSI driver Pod on one node.

**Syntax:**

```bash
kubectl get pods -A -o wide | grep csi
kubectl get pods -A --field-selector=status.phase!=Running | grep -i csi
kubectl describe pod <csi-node-plugin-pod> -n kube-system
```

**Example usage:**

```bash
$ kubectl get pods -n kube-system -l app=ebs-csi-node -o wide
NAME                    READY   STATUS             RESTARTS   NODE
ebs-csi-node-2f8k1      3/3     Running            0          node-1
ebs-csi-node-9j3m7      3/3     Running            0          node-2
ebs-csi-node-x7q2p      2/3     CrashLoopBackOff    14         node-3

$ kubectl describe pod ebs-csi-node-x7q2p -n kube-system | tail -8
Warning  BackOff  90s (x30 over 20m)  kubelet
  Back-off restarting failed container node-driver-registrar in pod ebs-csi-node-x7q2p
```

**Production usage example:** Three separate tickets — a `Pending` PVC, a `FailedMount` Pod, and a Pod stuck in mount-timeout retries — all had their Pods scheduled onto `node-3`, and investigating them individually would have meant three separate deep-dives; checking CSI node plugin Pod health across the cluster up front (`kubectl get pods -n kube-system -l app=ebs-csi-node`) immediately shows `node-3`'s plugin CrashLooping and explains all three at once.

**Common errors:** Investigating each affected Pod/PVC as an independent incident without first checking whether they share a node — when multiple, differently-symptomed storage tickets arrive close together, checking CSI driver Pod health across all nodes should happen before individual root-cause analysis on each one.

## 6. Production Usage Notes

- **Cloud-provider volume quotas (max volumes per account, max attachments per instance type) are a real, finite ceiling** that scales with cluster growth — monitoring quota headroom proactively (rather than discovering it via a stuck PVC) avoids Scenario A recurring as clusters grow.
- **`Immediate` binding mode StorageClasses should be treated as deliberate exceptions requiring justification**, not a lingering default — most workloads have no reason to need it, and its absence is what prevents Scenario B from recurring after any node pool topology change.
- **CSI driver Pods should be included in the same node-health monitoring and alerting as kubelet itself** — since a crashing CSI node plugin degrades storage functionality for every Pod scheduled onto that node, comparably to a `NotReady` node, even though the node itself may otherwise report healthy.

## 7. Security Considerations

- CSI controller logs (Scenario A) can reveal cloud-account-level details (account IDs, IAM role ARNs, quota limits) — treat `kube-system` log access with the same care as any other control-plane-adjacent log source ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)).
- Overly broad IAM permissions granted to a CSI driver to "make provisioning errors go away" is a common but risky over-correction — a `ResourceExhausted` or permission-denied error should be diagnosed and right-sized, not resolved by granting the driver's service account broader cloud permissions than it needs.
- CSI driver Pods typically run with elevated node-level privileges (to perform mount operations) — restricting who can modify their DaemonSet manifests or exec into them is as important as restricting raw node access itself ([§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md), [§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md)).

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Cause                                                                                    | Fix                                                                                                            |
| ----------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- |
| PVC `Pending`; StorageClass and CSI controller Pod both healthy         | Cloud-provider quota exhausted or IAM permission denied on the actual provisioning call  | Check `csi-provisioner`/`csi-attacher` sidecar container logs specifically, not just the main driver container |
| PV bound to a zone with zero eligible nodes                             | `Immediate` binding mode combined with a node pool's zone footprint changing afterward   | Switch StorageClass to `WaitForFirstConsumer`; recreate the stranded PVC                                       |
| Multiple, differently-symptomed storage tickets arriving close together | CSI node plugin Pod CrashLoopBackOff on the node hosting all the affected Pods           | Check CSI node plugin Pod health across the cluster before investigating each ticket individually              |
| Provisioning succeeds, but attach/mount is intermittently slow or fails | Cloud API throttling on the CSI controller's attach calls under high provisioning volume | Check controller logs for rate-limit errors; consider provisioning request pacing or a quota increase          |
| CSI driver Pod itself is CrashLoopBackOff                               | Misconfigured driver DaemonSet, incompatible driver version after a cluster upgrade      | Check driver Pod logs and version compatibility with the current Kubernetes version before other diagnosis     |

## 9. Best Practices

- Always check every sidecar container's logs inside a multi-container CSI controller Pod (`csi-provisioner`, `csi-attacher`, `csi-resizer`), not just the main driver container, since each handles a distinct part of the volume lifecycle and logs independently.
- Treat a node-affinity conflict's _root cause_ — not just its symptom — as the thing to fix; changing `volumeBindingMode` to `WaitForFirstConsumer` prevents recurrence in a way that recreating one PVC does not.
- When multiple storage-related tickets arrive close together, check CSI driver Pod health across the cluster before starting individual root-cause analysis on each affected PVC or Pod.

## 10. Common Anti-Patterns / Mistakes

- **Checking only the main CSI driver container's logs and missing the sidecar containers** (`csi-provisioner`, `csi-attacher`) that actually surface provisioning and attach errors.
- **Fixing a node-affinity conflict by recreating the stuck PVC alone**, without addressing the `Immediate` binding mode that will cause the identical conflict to recur.
- **Investigating multiple simultaneous storage tickets as independent incidents** without first checking whether the affected Pods share a node and a single crashing CSI driver Pod.

## 11. Interview Questions

**🎯 Beginner:** _"A PVC stays `Pending` even though the StorageClass exists and the CSI controller Pod shows `Running`. What would you check next?"_
**Model answer:** I'd look at the logs of the individual containers _inside_ the CSI controller Pod, specifically the `csi-provisioner` sidecar, rather than assuming the controller Pod's overall `Running` status means provisioning itself is succeeding. CSI controller Pods commonly run several sidecar containers handling different parts of the volume lifecycle, and a cloud-side error — quota exhaustion, a permission problem — surfaces in that specific sidecar's logs even though the Pod as a whole reports healthy.
_What the interviewer is probing for:_ Knowing that CSI controller Pods are multi-container and that overall Pod health doesn't guarantee every sidecar's underlying operation is succeeding.

**🎯 Intermediate:** _"You fix a 'volume node affinity conflict' by deleting and recreating the affected PVC, and it works. Is the issue actually resolved?"_
**Model answer:** Not durably. Recreating the PVC only fixes that one instance — if the StorageClass is still using `Immediate` binding mode, the exact same conflict can recur the next time the provisioner happens to pick a zone that doesn't match where Pods can actually be scheduled, especially after any node pool topology change. The actual fix is switching the StorageClass to `WaitForFirstConsumer`, which defers volume provisioning until a scheduling decision is already in progress, keeping the volume's zone and the Pod's placement in sync by construction going forward.
_What the interviewer is probing for:_ Distinguishing a symptom-level fix from a root-cause fix, and knowing the specific StorageClass setting that prevents recurrence.

**🎯 Senior:** _"Three tickets come in around the same time: a Pending PVC, a Pod stuck on FailedMount, and a Pod repeatedly timing out during mount. How do you approach investigating all three?"_
**Model answer:** Before diving into each ticket individually, I'd check whether the affected Pods share a node, and specifically check the health of the CSI node plugin Pod on that node — `kubectl get pods -n kube-system -l app=<csi-node-label> -o wide` sorted by node. A single crashing or degraded CSI node plugin can produce exactly this kind of varied symptom set across otherwise-unrelated PVCs and Pods, because every mount/attach operation for Pods on that node routes through the same driver Pod. If that's confirmed, fixing the one CSI node plugin Pod resolves all three tickets at once, versus three independent, much slower investigations that would each eventually arrive at the same underlying cause.
_What the interviewer is probing for:_ Pattern recognition across seemingly unrelated tickets, and knowing to check shared infrastructure (a single node's CSI plugin) before investigating each symptom independently.

**🎯 Architect:** _"How would you build safeguards so cloud-provider volume quota exhaustion doesn't surface first as a production incident?"_
**Model answer:** I'd treat cloud-provider storage quotas the same way I'd treat any other finite capacity resource — with proactive monitoring and alerting on headroom, not just reactive diagnosis when a PVC gets stuck. Concretely, that means exporting quota utilization metrics (via the cloud provider's own APIs or a periodic check) into the same monitoring stack as cluster resource metrics ([§92](../Part12/Section-92-Part12-Prometheus-Kubernetes-ServiceMonitors-Node-Exporter-kube-state-metrics.md)), with an alert threshold well before the hard limit, giving the platform team time to request an increase or clean up unused volumes before it becomes user-facing. I'd also build a lightweight automated check for orphaned volumes (PVs with `Reclaim: Retain` left behind by deleted PVCs) since these silently consume quota without any workload actively using them, and are a common, avoidable contributor to hitting the ceiling sooner than expected. Finally, I'd fold the CSI controller sidecar logs into the same centralized logging pipeline ([§94](../Part12/Section-94-Part12-Centralized-Logging-Patterns-Fluentd-FluentBit-Loki-EFK.md)) used for everything else, so `ResourceExhausted`-class errors are visible in dashboards rather than requiring someone to manually `kubectl logs` into a specific controller Pod during an active incident.
_What the interviewer is probing for:_ Proactive capacity monitoring and centralized observability applied specifically to storage quota, rather than relying purely on reactive per-incident diagnosis.

## 12. Common Misconceptions

1. **"If the CSI controller Pod is `Running`, provisioning is working."** The Pod's overall status doesn't reflect whether individual sidecar containers (`csi-provisioner`, `csi-attacher`) are successfully completing their specific operations — check their logs directly.
2. **"Recreating a PVC stuck on a node affinity conflict fully resolves the issue."** It resolves that one instance; without changing `volumeBindingMode` to `WaitForFirstConsumer`, the same conflict can recur after any future node pool topology change.
3. **"Unrelated-looking storage tickets require separate investigations."** Multiple, differently-symptomed failures across Pods sharing a node frequently trace back to one unhealthy CSI node plugin Pod on that node.
4. **"Storage quota exhaustion is rare enough not to monitor proactively."** It scales predictably with cluster and volume growth and is a common, avoidable cause of stuck PVCs if not tracked ahead of time.

## 13. 🔑 Key Takeaways

- A healthy-looking StorageClass and CSI controller Pod don't guarantee provisioning succeeds — check individual sidecar container logs (`csi-provisioner`, `csi-attacher`) for the actual cloud-side error.
- Fix node-affinity conflicts at the root (`volumeBindingMode: WaitForFirstConsumer`), not just by recreating the affected PVC, to prevent recurrence.
- Multiple, differently-worded storage tickets arriving together are frequently one CSI node plugin Pod crash on a shared node — check driver health across the cluster before investigating tickets individually.
- Cloud-provider storage quotas are a finite, predictable resource worth monitoring proactively rather than discovering via a stuck PVC.
- CSI driver Pod health deserves the same monitoring rigor as kubelet health, since its failure degrades storage for every Pod on that node.

## 14. Related Concepts & What's Next

This section extends [§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md)'s storage troubleshooting toolkit with deeper scenario coverage, building on [§59](../Part8/Section-59-Part8-StorageClasses-Dynamic-Provisioning.md) (StorageClasses/dynamic provisioning) and [§60](../Part8/Section-60-Part8-CSI-Container-Storage-Interface-Architecture.md) (CSI architecture), and follows [§101](./Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md)'s networking scenario deep dive as the second entry in Part 13's scenario sequence. [§103](./Section-103-Part13-Application-Level-Debugging-Misconfigured-Probes-Resource-Starvation-OOMKilled.md) moves from infrastructure-layer troubleshooting (networking, storage) into application-level debugging next.

**Next Section:** [§103](./Section-103-Part13-Application-Level-Debugging-Misconfigured-Probes-Resource-Starvation-OOMKilled.md) — `Section-103-Part13-Application-Level-Debugging-Misconfigured-Probes-Resource-Starvation-OOMKilled.md`
