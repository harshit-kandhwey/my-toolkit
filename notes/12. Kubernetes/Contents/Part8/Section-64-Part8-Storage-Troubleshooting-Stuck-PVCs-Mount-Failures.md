# Section 64 (Part 8): Storage Troubleshooting (Stuck PVCs, Mount Failures, Node Affinity Conflicts)

## 1. Definition

**Plain language:** "The Pod is stuck `Pending`" or "the Pod won't mount its volume" are two of the most common storage support tickets in Kubernetes, and — much like network connectivity failures — the root cause can sit at any one of several layers (the PVC itself, the StorageClass/provisioner, the CSI driver, node affinity, or the underlying disk), so an ordered, mechanical diagnostic flow turns a confusing multi-layer problem into a fast process of elimination.

**Precise definition:** This section defines a **structured, ordered diagnostic workflow** for Kubernetes storage failures, synthesizing every storage layer covered in this Part (Volumes at [§57](./Section-57-Part8-Volumes-emptyDir-hostPath-Ephemeral-Storage.md), PersistentVolumes/PVCs at [§58](./Section-58-Part8-PersistentVolumes-PersistentVolumeClaims.md), StorageClasses and dynamic provisioning at [§59](./Section-59-Part8-StorageClasses-Dynamic-Provisioning.md), CSI architecture at [§60](./Section-60-Part8-CSI-Container-Storage-Interface-Architecture.md), Access Modes and Reclaim Policies at [§61](./Section-61-Part8-Access-Modes-RWO-ROX-RWX-Reclaim-Policies.md), StatefulSet storage patterns at [§62](./Section-62-Part8-StatefulSet-Storage-Patterns-volumeClaimTemplates.md), and Volume Snapshots/Cloning at [§63](./Section-63-Part8-Volume-Snapshots-Cloning.md)) into a single practical checklist — moving from the cheapest, most likely checks (PVC/PV binding status, StorageClass existence) toward progressively deeper diagnostics (CSI driver Pod logs, node-level mount inspection, scheduler/affinity conflicts) only as needed.

## 2. Why This Matters

- **Most storage tickets are resolved by reading `kubectl describe pvc` and `kubectl describe pod` events, without ever touching a node or a CSI driver log.** A PVC stuck `Pending` almost always has a specific, human-readable Event explaining exactly why (no matching StorageClass, no available PV, provisioning error) — reaching for node-level debugging before reading these events wastes significant time.
- **An ordered checklist prevents debugging the wrong layer first**, particularly around a very common and easy-to-misdiagnose failure: a Pod stuck `Pending` because its volume was provisioned in the wrong availability zone relative to where the scheduler wants to place it — this looks like a scheduling problem but is actually a storage/topology problem, and vice versa.
- **This toolkit is the direct storage-specific instance of the general troubleshooting methodology built in Part 13** — [§97](../Part13/Section-97-Part13-Structured-Troubleshooting-Methodology-Kubernetes.md)'s structured methodology and [§102](../Part13/Section-102-Part13-Storage-Troubleshooting-Scenarios-PVC-Pending-Mount-Errors.md)'s storage-specific troubleshooting scenarios generalize the exact ordered-elimination approach this section applies specifically to PVC binding, mounting, and node affinity failures.

🔑 **Key Takeaway:** Effective storage troubleshooting in Kubernetes is an ordered elimination process — check PVC/PV binding state and Events before StorageClass/provisioner health, check provisioning before node-level mount and affinity issues, and reach for CSI driver logs and node inspection only after every cheaper, object-level check has been exhausted, since most real-world storage failures surface a clear cause directly in `kubectl describe` output.

## 3. Prerequisites and Dependencies

Synthesizes [§57](./Section-57-Part8-Volumes-emptyDir-hostPath-Ephemeral-Storage.md)–[§63](./Section-63-Part8-Volume-Snapshots-Cloning.md) in full (Volumes, PersistentVolumes/PVCs, StorageClasses, CSI, Access Modes/Reclaim Policies, StatefulSet storage patterns, Volume Snapshots) and sets up [§102](../Part13/Section-102-Part13-Storage-Troubleshooting-Scenarios-PVC-Pending-Mount-Errors.md) (Part 13's storage-specific troubleshooting scenarios) and the scheduling internals covered starting in [§65](../Part9/Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md).

## 4. Architecture Diagram: the Diagnostic Order

```text
   "Pod stuck Pending / volume won't mount" — ordered diagnostic flow

   Step 1: PVC/PV binding state (cheapest, check first)
   ┌───────────────────────────────────────────────────────────┐
   │ kubectl get pvc -n <ns>            → Bound? Pending?      │
   │ kubectl describe pvc <name>        → read Events directly │
   └───────────────────────────┬───────────────────────────────┘
                                 │ (PVC Pending, no clear PV bound)
                                 ▼
   Step 2: StorageClass and provisioner sanity (§59)
   ┌───────────────────────────────────────────────────────────┐
   │ kubectl get storageclass                                  │
   │ kubectl get pods -n kube-system | grep <provisioner>      │
   │  → StorageClass exists? provisioner Pods Running?         │
   └───────────────────────────┬───────────────────────────────┘
                                 │ (StorageClass fine; still Pending)
                                 ▼
   Step 3: CSI controller-side provisioning errors (§60)
   ┌───────────────────────────────────────────────────────────┐
   │ kubectl logs -n kube-system <csi-controller-pod> \        │
   │   -c csi-provisioner                                      │
   │  → quota exceeded? IAM/cloud API error? zone mismatch?    │
   └───────────────────────────┬───────────────────────────────┘
                                 │ (PVC now Bound, but Pod still stuck)
                                 ▼
   Step 4: Scheduling / node affinity conflict (§59 WaitForFirstConsumer)
   ┌───────────────────────────────────────────────────────────┐
   │ kubectl describe pod <pod>  → FailedScheduling?           │
   │  → PV's node affinity (zone) vs. Pod's actual placement   │
   │    constraints (taints, node selectors, other zones)      │
   └───────────────────────────┬───────────────────────────────┘
                                 │ (scheduled fine; mount itself fails)
                                 ▼
   Step 5: Node-level mount failure (CSI node plugin, §60)
   ┌───────────────────────────────────────────────────────────┐
   │ kubectl describe pod <pod>  → FailedMount / FailedAttach  │
   │ kubectl logs -n kube-system <csi-node-plugin-pod>         │
   │ node-level: journalctl -u kubelet, mount/lsblk on the node│
   └───────────────────────────────────────────────────────────┘
```

- **Each step is deliberately cheaper and faster than the one below it** — PVC/PV object status and Events take seconds to check and rule out the two most statistically common causes (missing StorageClass, exhausted quota) before any log-diving or node access is needed.
- **Step 4 (node affinity conflict) is the single most commonly misdiagnosed failure in this entire flow** — a Pod stuck `Pending` after its PVC is already `Bound` looks like a generic scheduling problem, but is very often actually a storage-topology problem: the PV was provisioned in a zone the Pod cannot be scheduled into.
- **Node-level log and mount inspection (Step 5) is reserved for the bottom of the flow deliberately** — it requires node access and answers "why did the attach/mount itself fail," which is the right question only once binding and scheduling have been ruled out.

## 5. Hands-On

### 5.1 Diagnosing a Stuck PVC

**Purpose:** Rule out the most common and cheapest-to-fix causes of a PVC that never leaves `Pending` — a missing/misspelled StorageClass, or a provisioner that isn't running.

**Syntax:**

```bash
kubectl get pvc -n <namespace>
kubectl describe pvc <pvc-name> -n <namespace>
kubectl get storageclass
```

**Example usage:**

```bash
$ kubectl get pvc -n default
NAME          STATUS    VOLUME   CAPACITY   ACCESS MODES   STORAGECLASS   AGE
app-data-pvc  Pending                                        fast-ssd       4m

$ kubectl describe pvc app-data-pvc -n default | tail -5
Events:
  Type     Reason              Age                From                         Message
  ----     ------              ----               ----                         -------
  Warning  ProvisioningFailed  30s (x8 over 4m)   ebs.csi.aws.com_ebs-csi-controller  storageclass.storage.k8s.io "fast-ssd" not found
```

**Production usage example:** A `ProvisioningFailed` Event referencing a StorageClass name that "not found" is one of the single most common root causes of a stuck PVC in practice — almost always a typo in the manifest's `storageClassName`, or a StorageClass that exists in one cluster/environment but was never created in another (a frequent gap in multi-environment Kustomize/Helm overlays, [§47](../Part6/Section-47-Part6-Multi-Environment-Configuration-Patterns.md)), and it's fixable in seconds once the exact Event message is read.

**Common errors:** Assuming a `Pending` PVC always means the cluster is out of capacity — the far more common cause is a simple naming mismatch or missing StorageClass, and the `describe` output's Events section states the exact cause directly rather than requiring guesswork.

### 5.2 Diagnosing Node Affinity Conflicts

**Purpose:** Recognize the specific pattern where a PVC is `Bound` but its Pod is stuck `Pending`, because the provisioned volume's zone doesn't match where the Pod can actually be scheduled.

**Syntax:**

```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl get pv <pv-name> -o jsonpath='{.spec.nodeAffinity}'
kubectl get nodes --show-labels | grep topology.kubernetes.io/zone
```

**Example usage:**

```bash
$ kubectl describe pod db-0 -n default | grep -A3 Events
Events:
  Warning  FailedScheduling  2m (x5 over 10m)  default-scheduler
    0/6 nodes are available: 4 node(s) had volume node affinity conflict,
    2 node(s) didn't match Pod's node affinity/selector.

$ kubectl get pv pvc-a1b2 -o jsonpath='{.spec.nodeAffinity.required.nodeSelectorTerms[0].matchExpressions[0]}'
{"key":"topology.kubernetes.io/zone","operator":"In","values":["us-east-1a"]}
```

**Production usage example:** With `volumeBindingMode: WaitForFirstConsumer` ([§59](./Section-59-Part8-StorageClasses-Dynamic-Provisioning.md)) not set (i.e., using the older `Immediate` binding mode), a StorageClass can provision a volume in whatever zone the provisioner happens to choose _before_ the scheduler has decided where the Pod will run — if that zone doesn't overlap with the zones the Pod's other constraints (node selectors, taints, topology spread from [§72](../Part9/Section-72-Part9-Topology-Spread-Constraints.md)) permit, the Pod becomes permanently unschedulable until the PVC is deleted and recreated correctly.

**Common errors:** Troubleshooting this purely as a scheduling problem (checking taints, resource requests, node selectors) without noticing "volume node affinity conflict" specifically in the `FailedScheduling` message — that exact phrase is the signal this is a storage/topology issue, not a general scheduling capacity issue.

### 5.3 Diagnosing Mount and Attach Failures

**Purpose:** Once binding and scheduling are confirmed healthy, determine why the volume is failing to actually attach or mount to the node hosting the Pod.

**Syntax:**

```bash
kubectl describe pod <pod-name> -n <namespace>
kubectl logs -n kube-system <csi-node-plugin-pod> -c <driver-container>
kubectl get volumeattachment
```

**Example usage:**

```bash
$ kubectl describe pod app-0 -n default | grep -A3 Events
Events:
  Warning  FailedMount  90s (x3 over 5m)  kubelet
    MountVolume.MountDevice failed for volume "pvc-e5f6" :
    rpc error: code = Internal desc = could not format "/dev/xvdba" ... device or resource busy

$ kubectl get volumeattachment
NAME                                                                   ATTACHER          PV          NODE       ATTACHED
csi-7a1b2c3d4e5f6789...                                                ebs.csi.aws.com   pvc-e5f6    ip-10-0-1-23   true
```

**Production usage example:** A `device or resource busy` mount error commonly indicates the same underlying disk is still attached (or in the process of detaching) from a previous node — often seen right after a node failure or forced Pod eviction, where the CSI driver hasn't yet completed detaching the volume from the old node before the new node tries to attach it; checking `VolumeAttachment` objects shows exactly which node currently holds the attachment.

**Common errors:** Immediately deleting and recreating the Pod when a `FailedMount` occurs, without checking whether a stale `VolumeAttachment` to a now-dead node is the actual blocker — recreating the Pod doesn't help if the old attachment is never cleaned up, and can require manually deleting the stale `VolumeAttachment` object (with care) to unblock it.

## 6. Production Usage Notes

- **`volumeBindingMode: WaitForFirstConsumer` ([§59](./Section-59-Part8-StorageClasses-Dynamic-Provisioning.md)) prevents the majority of node-affinity conflicts by design** — it defers volume provisioning/binding until a Pod requesting it is actually being scheduled, letting the scheduler's placement decision and the volume's zone stay in sync; StorageClasses still using the older `Immediate` mode are a common source of the exact conflict pattern in 5.2.
- **CSI controller and node plugin Pods (`kube-system`, typically named `<driver>-controller` and `<driver>-node`) are themselves regular Kubernetes Pods and can fail like any other** — a CrashLoopBackOff'd CSI driver Pod silently breaks provisioning and mounting cluster-wide, and its own health should be an early check when _many_ PVCs across the cluster are stuck simultaneously, not just one.
- **`VolumeAttachment` objects are cluster-scoped and not namespaced** — they're easy to overlook in a namespace-scoped troubleshooting habit, but they're often the single fastest way to see exactly which node currently holds a stale or conflicting attachment.

## 7. Security Considerations

- Diagnosing CSI driver failures often requires reading controller/node plugin logs and, in some cases, node-level access (`journalctl`, direct filesystem inspection) — this should be gated the same way as any other privileged node-level operation ([§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)), consistent with the raw packet-capture access discipline described in [§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md).
- Manually deleting a stuck `VolumeAttachment` object to unblock a mount is a genuinely risky, low-level operation if done against a volume that's actually still in active use elsewhere — it should be treated as a deliberate, reviewed action, not a routine troubleshooting reflex.
- Reviewing PVC/PV Events as part of this workflow can surface StorageClass or provisioner misconfigurations (e.g., unintentionally permissive cloud IAM roles granted to a CSI driver) that are worth feeding back into a security review, similar to how NetworkPolicy gaps are often caught incidentally during network troubleshooting ([§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md)).

## 8. Common Troubleshooting Scenarios

| Symptom                                                               | Cause                                                                                 | Fix                                                                                                                                                                               |
| --------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| PVC stuck `Pending` with `ProvisioningFailed: storageclass not found` | Typo in `storageClassName`, or StorageClass never created in this environment         | Correct the name, or create the missing StorageClass; verify multi-environment overlays include it ([§47](../Part6/Section-47-Part6-Multi-Environment-Configuration-Patterns.md)) |
| PVC `Bound`, Pod stuck `Pending` with "volume node affinity conflict" | Volume provisioned in a zone incompatible with the Pod's other scheduling constraints | Delete and recreate the PVC under a StorageClass with `volumeBindingMode: WaitForFirstConsumer`                                                                                   |
| Pod `FailedMount` with "device or resource busy"                      | Stale `VolumeAttachment` to a previous (possibly dead) node not yet cleaned up        | Check `kubectl get volumeattachment`; manually clean up the stale attachment only after confirming it's safe                                                                      |
| PVC stuck `Pending`, StorageClass and provisioner both look healthy   | Cloud-provider quota exhausted (e.g., max EBS volumes per account/region)             | Check CSI controller logs for the specific cloud API error; request a quota increase or free up unused volumes                                                                    |
| Many PVCs across the cluster stuck simultaneously                     | CSI controller or node plugin Pods themselves unhealthy (CrashLoopBackOff, etc.)      | Check CSI driver Pod health in `kube-system` first, before investigating individual PVCs                                                                                          |

## 9. Best Practices

- Always work the checklist in order — PVC/PV binding status and Events, then StorageClass/provisioner health, then CSI controller logs, then scheduling/affinity, then node-level mount inspection — rather than jumping straight to node access or CSI logs for every issue.
- Default new StorageClasses to `volumeBindingMode: WaitForFirstConsumer` unless there's a specific reason not to, since it eliminates an entire, commonly-misdiagnosed category of node-affinity failures at the source.
- Treat "volume node affinity conflict" in a `FailedScheduling` message as an immediate, specific signal to check the PV's zone against the Pod's actual scheduling constraints, rather than re-investigating generic scheduling causes.

## 10. Common Anti-Patterns / Mistakes

- **Treating a stuck PVC as a capacity problem by default**, when the far more common causes are a StorageClass naming typo or a missing StorageClass in the current environment, both visible directly in `kubectl describe pvc` Events.
- **Diagnosing a "volume node affinity conflict" Pod as a generic scheduling issue** (checking taints, resources, node selectors) without recognizing the specific phrase that points directly at a storage-topology mismatch.
- **Deleting and recreating a Pod stuck on `FailedMount` without checking for a stale `VolumeAttachment`** first, which doesn't address the actual blocker and just repeats the same failure.

## 11. Interview Questions

**🎯 Beginner:** _"A PVC has been stuck in `Pending` for several minutes. What's the first thing you'd check?"_
**Model answer:** I'd run `kubectl describe pvc <name>` and read the Events section directly — Kubernetes almost always states the exact reason a PVC can't bind or provision, most commonly a missing or misspelled StorageClass, or a provisioning error from the CSI driver. This takes seconds and rules out the most statistically common causes before considering anything about cluster capacity or node-level issues.
_What the interviewer is probing for:_ Instinct to read Events directly rather than guessing or jumping to deeper investigation.

**🎯 Intermediate:** _"A PVC shows `Bound`, but the Pod using it is stuck `Pending` with a `FailedScheduling` event mentioning 'volume node affinity conflict.' What does this mean, and how do you fix it?"_
**Model answer:** This means the PersistentVolume that was provisioned for the PVC has a node affinity restricting it to specific zones or nodes (set at provisioning time, based on where the underlying disk actually lives), and none of the nodes the Pod could otherwise be scheduled onto satisfy that constraint. This typically happens when a StorageClass uses `volumeBindingMode: Immediate`, letting the volume get provisioned in an arbitrary zone before the scheduler has decided where the Pod goes, rather than `WaitForFirstConsumer`, which defers provisioning until a scheduling decision is already being made. The fix is usually to delete the PVC (and the now-orphaned PV, if reclaim policy left it behind) and recreate it under a StorageClass using `WaitForFirstConsumer`, so the volume gets provisioned in a zone that actually matches where the Pod will run.
_What the interviewer is probing for:_ Understanding that this is a storage-topology problem masquerading as a scheduling problem, and knowing the specific StorageClass setting that prevents it going forward.

**🎯 Senior:** _"You've confirmed the PVC is `Bound`, the Pod is scheduled onto a node, but it's stuck with a `FailedMount` error. Walk me through your next steps."_
**Model answer:** I'd start by reading the exact `FailedMount`/`FailedAttach` message from `kubectl describe pod`, since the specific error text usually narrows things significantly — a "device or resource busy" message points at a stale attachment (I'd check `kubectl get volumeattachment` to see if the volume is still marked attached to a different, possibly now-dead node), while a filesystem-format error might point at actual disk corruption or an incompatible filesystem type. I'd then check the CSI node plugin Pod's logs on that specific node, since the node plugin is what actually executes the mount operation and its logs typically surface the underlying cloud-provider or kernel-level error. If a stale `VolumeAttachment` is the cause, I'd confirm the volume genuinely isn't in use elsewhere before manually deleting that attachment object to unblock the new mount — this is a deliberate, somewhat risky operation, so I wouldn't do it reflexively without that confirmation.
_What the interviewer is probing for:_ Methodical progression from Pod-level events to node-plugin logs to cluster-scoped `VolumeAttachment` state, plus appropriate caution around a genuinely risky manual remediation step.

**🎯 Architect:** _"How would you reduce the frequency of storage-related incidents across a platform supporting many application teams, rather than just getting better at diagnosing them after the fact?"_
**Model answer:** I'd focus on eliminating entire categories of failure at the platform level rather than relying on faster diagnosis. Defaulting every StorageClass to `volumeBindingMode: WaitForFirstConsumer` removes the node-affinity-conflict category almost entirely. I'd build automated monitoring on CSI controller/node plugin Pod health specifically, since their failure silently breaks provisioning and mounting cluster-wide and is easy to miss until many unrelated-looking tickets show up. I'd also add a pre-deployment validation step (in CI, using a tool like `kubeconform` or a custom admission policy) that catches `storageClassName` typos or references to StorageClasses that don't exist in the target environment — a surprisingly large fraction of "stuck PVC" tickets in practice. Finally, I'd formalize this section's ordered diagnostic flow as a documented runbook, paired with pre-approved node-access procedures for the rare cases that do require CSI driver log inspection or manual `VolumeAttachment` cleanup, so on-call engineers aren't improvising both the diagnosis order and the access process during an actual incident.
_What the interviewer is probing for:_ Platform-level thinking that prevents failure categories via defaults and CI validation, not just individual diagnostic skill, plus recognizing CSI driver health monitoring as a leverage point.

## 12. Common Misconceptions

1. **"A stuck PVC always means the cluster is out of storage capacity."** The most common causes are configuration issues — a missing/misspelled StorageClass or a provisioning error visible directly in Events — not actual capacity exhaustion.
2. **"'Volume node affinity conflict' is a generic scheduling problem."** It's a specific, storage-topology-driven signal that the provisioned volume's zone doesn't match where the Pod can be scheduled — a different root cause and fix from taint/toleration or resource-based scheduling failures.
3. **"Recreating the Pod fixes any mount failure."** A stale `VolumeAttachment` pointing at a dead or wrong node will cause the identical failure to recur until the attachment itself is addressed, regardless of how many times the Pod is recreated.
4. **"CSI driver health is a per-PVC concern."** A single unhealthy CSI controller or node plugin Pod can silently break provisioning or mounting cluster-wide — it's worth checking early, especially when multiple, seemingly unrelated PVCs fail at once.

## 13. 🔑 Key Takeaways

- Work Kubernetes storage troubleshooting as an ordered elimination flow — PVC/PV binding state and Events, then StorageClass/provisioner health, then CSI controller logs, then scheduling/node-affinity, then node-level mount inspection.
- "Volume node affinity conflict" is a distinct, specific failure signature pointing at a zone mismatch between a provisioned volume and the Pod's scheduling constraints — largely preventable by defaulting StorageClasses to `volumeBindingMode: WaitForFirstConsumer`.
- `VolumeAttachment` objects are cluster-scoped and are often the fastest way to spot a stale attachment causing a `FailedMount`/"device or resource busy" error.
- CSI controller and node plugin Pod health is itself worth checking early when multiple, unrelated-looking PVCs fail simultaneously.
- Reducing storage incidents at the platform level (safe StorageClass defaults, CI manifest validation, CSI driver health monitoring) is more effective long-term than only getting faster at diagnosing them individually.

## 14. Related Concepts & What's Next

This section synthesizes the entire Storage Part — [§57](./Section-57-Part8-Volumes-emptyDir-hostPath-Ephemeral-Storage.md) (Volumes), [§58](./Section-58-Part8-PersistentVolumes-PersistentVolumeClaims.md) (PersistentVolumes/PVCs), [§59](./Section-59-Part8-StorageClasses-Dynamic-Provisioning.md) (StorageClasses and Dynamic Provisioning), [§60](./Section-60-Part8-CSI-Container-Storage-Interface-Architecture.md) (CSI Architecture), [§61](./Section-61-Part8-Access-Modes-RWO-ROX-RWX-Reclaim-Policies.md) (Access Modes and Reclaim Policies), [§62](./Section-62-Part8-StatefulSet-Storage-Patterns-volumeClaimTemplates.md) (StatefulSet Storage Patterns), and [§63](./Section-63-Part8-Volume-Snapshots-Cloning.md) (Volume Snapshots and Cloning) — into one ordered diagnostic workflow. [§102](../Part13/Section-102-Part13-Storage-Troubleshooting-Scenarios-PVC-Pending-Mount-Errors.md) returns to storage troubleshooting specifically with additional scenario depth beyond what this Part's capstone covers, following the same pattern as [§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md)'s networking capstone feeding into [§101](../Part13/Section-101-Part13-Networking-Troubleshooting-Scenarios-Unreachable-Services-DNS-Failures.md). This is the final section of Part 8 — Part 9 begins immediately with Scheduling, starting from the scheduler's filtering and scoring internals.

**Next Section:** [§65](../Part9/Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md) — `Section-65-Part9-Scheduler-Deep-Dive-Filtering-Scoring-Phases.md`
