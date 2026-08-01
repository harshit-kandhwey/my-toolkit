# Section 61 (Part 8): Access Modes (RWO/ROX/RWX) and Reclaim Policies

## 1. Definition

**Plain language:** Once a PersistentVolume exists and can be dynamically provisioned through a CSI driver (§60), two more questions decide whether it actually behaves the way an application needs it to: how many nodes are allowed to mount it at once, and what happens to the underlying storage after the claim that used it is deleted.

**Precise definition:** **Access Modes** (`ReadWriteOnce`, `ReadOnlyMany`, `ReadWriteMany`, and the newer `ReadWriteOncePod`) declare the mount concurrency a PersistentVolume supports, and are enforced by the kubelet and the CSI driver at mount time, not by the API server at admission time. **Reclaim Policy** (`Delete` or `Retain`, with `Recycle` deprecated) declares what happens to the underlying storage asset once its bound PersistentVolumeClaim is deleted — whether the backing volume (and its data) is destroyed along with the Kubernetes object, or preserved for manual recovery or re-binding.

## 2. Why This Matters

- **Picking the wrong access mode is a common cause of Pods stuck in `Pending` or `ContainerCreating`** — a Deployment with multiple replicas requesting a `ReadWriteOnce` volume will schedule its first Pod fine and then fail to attach the same volume to a second Pod on a different node, because most block-storage-backed `ReadWriteOnce` volumes can only be attached to one node at a time.
- **The reclaim policy is the single setting standing between an accidental `kubectl delete pvc` and permanent data loss** — a `Delete` reclaim policy (the default for most dynamically provisioned StorageClasses, §59) destroys the underlying disk the moment the claim is deleted, while `Retain` leaves the disk and its data intact, requiring deliberate action to actually remove it.
- **These two settings interact directly with the workload patterns covered next** — StatefulSet storage (§62) and Volume Snapshots (§63) both assume a correct understanding of access mode concurrency and reclaim behavior as their foundation.

🔑 **Key Takeaway:** Access Modes govern _how many Pods, on how many nodes, can mount a volume concurrently_, while Reclaim Policy governs _what happens to the data after the claim is gone_ — conflating the two, or assuming defaults are always safe, is the root cause of both scheduling failures and unrecoverable data loss in production.

## 3. Prerequisites and Dependencies

Builds directly on §57 (Volumes), §58 (PersistentVolumes and PersistentVolumeClaims), §59 (StorageClasses and Dynamic Provisioning), and §60 (CSI Architecture) — access modes are advertised by the CSI driver and enforced at mount time, and reclaim policy is set either on the StorageClass (for dynamically provisioned volumes) or directly on a statically provisioned PersistentVolume.

## 4. Architecture Diagram

```text
   Access Modes: concurrency the underlying storage actually supports
   ┌────────────────────────────────────────────────────────────────────┐
   │ RWO  ReadWriteOnce      1 node,  read-write   (most block disks)   │
   │ ROX  ReadOnlyMany       many nodes, read-only (rare; e.g. AMI-like)│
   │ RWX  ReadWriteMany      many nodes, read-write (NFS, EFS, CephFS)  │
   │ RWOP ReadWriteOncePod   1 POD (not just 1 node), read-write        │
   └────────────────────────────────────────────────────────────────────┘

   Reclaim Policy: what happens when the PVC is deleted
   ┌────────────────────────────────────────────────────────────────────┐
   │  PVC deleted                                                       │
   │       │                                                            │
   │       ▼                                                            │
   │  reclaimPolicy: Delete   → PV deleted → underlying disk destroyed  │
   │  reclaimPolicy: Retain   → PV kept, phase → "Released"             │
   │                             (not reusable until manually cleaned   │
   │                              and re-created/re-bound)              │
   └────────────────────────────────────────────────────────────────────┘

   RWO conflict — the common Pending failure:
   Node A: Pod-1 ── mounts PVC (RWO) ──► Volume (attached to Node A)
   Node B: Pod-2 ── tries to mount same PVC ──► FailedAttachVolume
                     (blocked: volume already attached elsewhere)
```

- **Access mode is a _ceiling_ set by the storage backend, not a request Kubernetes can override** — requesting `ReadWriteMany` on a StorageClass backed by EBS/Azure Disk/GCE PD will simply fail to provision, since those backends are physically block devices that cannot be attached read-write to multiple nodes.
- **`ReadWriteOncePod` (stable since Kubernetes 1.29) is stricter than `ReadWriteOnce`** — it limits the volume to a single _Pod_ cluster-wide, closing a real gap where `RWO` alone still permitted two Pods on the _same_ node to both mount the volume simultaneously, which is unsafe for many single-writer applications.
- **`Retain` does not mean "still usable"** — a Released PV cannot be bound to a new PVC until an operator manually removes the `claimRef` (or deletes and recreates the PV) after confirming the data is either safe to reuse or has been extracted.

## 5. Hands-On

### 5.1 Choosing and Verifying an Access Mode

**Purpose:** Confirm what access modes a StorageClass's backing CSI driver actually supports before designing a workload around a shared-writer assumption.

**Syntax:**

```bash
kubectl get storageclass <name> -o yaml
kubectl describe pvc <pvc-name>
```

**Example usage:**

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: shared-media-pvc
spec:
  accessModes:
    - ReadWriteMany
  storageClassName: efs-sc
  resources:
    requests:
      storage: 50Gi
```

```bash
$ kubectl get pvc shared-media-pvc
NAME               STATUS   VOLUME    CAPACITY   ACCESS MODES   STORAGECLASS   AGE
shared-media-pvc   Bound    pvc-9f2   50Gi       RWX            efs-sc         12s
```

**Production usage example:** A media-processing pipeline running multiple worker replicas that all need to read and write to the same scratch directory requires a genuinely `ReadWriteMany`-capable backend such as AWS EFS, Azure Files, or CephFS — attempting the same pattern against an EBS-backed StorageClass will provision successfully (the PVC binds) but every Pod after the first will fail to schedule with `FailedAttachVolume` once a second node tries to attach it.

**Common errors:** Requesting `ReadWriteMany` in the PVC spec against a StorageClass whose provisioner is fundamentally block-storage (EBS, Azure Disk, GCE PD, most local-path provisioners) — the claim itself may bind, but any attempt to actually mount it from a second node fails at the CSI `NodeStageVolume`/attach step, not at admission.

### 5.2 Setting and Testing Reclaim Policy

**Purpose:** Guarantee that deleting a PVC does not silently destroy data for volumes holding anything valuable, by explicitly setting `Retain` where recovery matters.

**Syntax:**

```bash
kubectl patch pv <pv-name> -p '{"spec":{"persistentVolumeReclaimPolicy":"Retain"}}'
kubectl get pv <pv-name> -o jsonpath='{.spec.persistentVolumeReclaimPolicy}'
```

**Example usage:**

```yaml
apiVersion: storage.k8s.io/v1
kind: StorageClass
metadata:
  name: db-storage-retain
provisioner: ebs.csi.aws.com
reclaimPolicy: Retain
volumeBindingMode: WaitForFirstConsumer
parameters:
  type: gp3
```

```bash
$ kubectl delete pvc db-data-pvc
persistentvolumeclaim "db-data-pvc" deleted

$ kubectl get pv
NAME       CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS     CLAIM
pvc-7a1c   100Gi      RWO            Retain           Released   default/db-data-pvc
```

**Production usage example:** For a StatefulSet-backed database (§62), setting `reclaimPolicy: Retain` on the StorageClass means an accidental `kubectl delete pvc` or a mistaken StatefulSet scale-down doesn't destroy the underlying disk — the PV moves to `Released`, and an operator can manually re-bind it to a newly created PVC (by clearing `claimRef` and matching `volumeName`) to recover the data, rather than restoring from a backup.

**Common errors:** Assuming the default `Delete` reclaim policy used by most cloud-provider StorageClasses is a safe default for stateful workloads — it is optimized for ephemeral/scratch use cases, and using it unmodified for a production database StorageClass turns any accidental claim deletion into permanent, unrecoverable data loss.

## 6. Production Usage Notes

- **Most dynamically provisioned StorageClasses default `reclaimPolicy` to `Delete`** — this must be explicitly overridden to `Retain` for any StorageClass backing genuinely important data, since the field is set once on the StorageClass (or PV) and is not something a PVC author controls per-claim.
- **`ReadWriteMany` backends (EFS, Azure Files, CephFS, NFS) generally have different performance characteristics (higher latency, weaker consistency guarantees) than block storage** — teams sometimes over-index on the convenience of shared mounts without accounting for the throughput and latency trade-off versus per-Pod `ReadWriteOnce` volumes.
- **`Recycle` is deprecated and should not be used in new StorageClasses** — it performed a basic `rm -rf` of the volume's contents rather than deleting the underlying disk, a much weaker and less auditable guarantee than either `Delete` or `Retain`.

## 7. Security Considerations

- A `Retain`-ed, Released PV still contains the previous claim's data in full — leaving it unbound and unmanaged is itself a data-exposure risk if a future, unrelated PVC in the same namespace could bind to it before it's properly wiped or destroyed.
- `ReadWriteMany` volumes shared across multiple Pods (and potentially multiple tenants/namespaces if RBAC and StorageClass access aren't scoped carefully) widen the blast radius of a single compromised Pod, since it can read or write to data other workloads also depend on.
- Static provisioning workflows that manually recreate a PV from a `Retain`-ed disk should re-verify the disk's origin and integrity before re-binding it to a new workload — reattaching an unvetted volume is a supply-chain-adjacent risk in regulated environments.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                             | Cause                                                                                 | Fix                                                                                                   |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- |
| Second Pod replica stuck in `Pending`/`ContainerCreating` with `FailedAttachVolume` | Volume is `ReadWriteOnce`, already attached to a different node                       | Use a `ReadWriteMany`-capable StorageClass, or redesign the workload to use per-replica volumes (§62) |
| PVC deletion destroyed data unexpectedly                                            | StorageClass/PV `reclaimPolicy` was `Delete`, not `Retain`                            | Set `reclaimPolicy: Retain` on the StorageClass before provisioning anything holding real data        |
| PV stuck in `Released`, new PVC won't bind to it                                    | `Retain`-ed PV still has a stale `claimRef` pointing at the deleted PVC               | Manually clear `spec.claimRef` on the PV (or delete and recreate it referencing the same volume ID)   |
| PVC requesting `ReadWriteMany` never leaves `Pending`                               | Underlying StorageClass provisioner physically doesn't support RWX (e.g., EBS/GCE PD) | Switch to an RWX-capable provisioner (EFS/Azure Files/CephFS/NFS) or redesign for per-Pod volumes     |
| Two Pods on the _same_ node both mounted an "RWO" volume unexpectedly               | `ReadWriteOnce` only limits attachment to one _node_, not one Pod                     | Use `ReadWriteOncePod` (Kubernetes 1.29+) if true single-Pod exclusivity is required                  |

## 9. Best Practices

- Set `reclaimPolicy: Retain` explicitly on any StorageClass backing stateful, business-critical data, and treat the `Delete` default as appropriate only for genuinely disposable/scratch storage.
- Match the access mode to the actual concurrency the workload needs — default to `ReadWriteOnce` (or `ReadWriteOncePod` where single-Pod exclusivity matters) unless the application genuinely requires concurrent multi-node writers.
- Document and periodically audit `Released` PVs in `Retain`-policy StorageClasses — they represent both a cost (unused disks still billed) and a data-governance liability if left unmanaged indefinitely.

## 10. Common Anti-Patterns / Mistakes

- **Requesting `ReadWriteMany` reflexively "to be safe" for a workload that only ever needs one writer**, taking on the operational complexity and performance trade-offs of a shared filesystem backend for no real benefit.
- **Leaving the default `Delete` reclaim policy on StorageClasses backing production databases or other stateful workloads**, turning a routine or accidental PVC deletion into irreversible data loss.
- **Forgetting that `Retain`-ed volumes require manual intervention to be reused**, leading to teams believing data was "backed up" simply because the PV wasn't deleted, without an actual runbook for recovery.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `ReadWriteOnce` and `ReadWriteMany`?"_
**Model answer:** `ReadWriteOnce` means the volume can be mounted read-write by Pods on only a single node at a time — the common case for block storage like EBS or Azure Disk. `ReadWriteMany` means the volume can be mounted read-write by Pods across many nodes simultaneously, which requires a shared-filesystem backend like NFS, EFS, or CephFS rather than a plain block device, since a physical disk can't be attached to multiple machines at once.
_What the interviewer is probing for:_ Basic understanding that access modes reflect real physical storage constraints, not an arbitrary Kubernetes setting.

**🎯 Intermediate:** _"A Deployment with 3 replicas using a `ReadWriteOnce` PVC only ever has one Pod running successfully, with the others stuck in `Pending`. Why, and how would you fix it?"_
**Model answer:** A `ReadWriteOnce` volume can only be attached to one node at a time (in older behavior, potentially multiple Pods on that _same_ node, but not across nodes), so once the first Pod schedules and attaches the volume, any replica scheduled to a different node fails to attach it and stays `Pending` with a `FailedAttachVolume` event. The fix depends on the actual requirement: if the workload genuinely needs a shared volume across replicas, switch to a `ReadWriteMany`-capable StorageClass (EFS/Azure Files/CephFS); if each replica should have its own independent storage instead, the workload should likely be a StatefulSet with `volumeClaimTemplates` rather than a Deployment sharing one PVC.
_What the interviewer is probing for:_ Ability to diagnose a real scheduling failure back to its storage root cause, and to choose the correct fix (RWX vs. redesign) rather than a blanket "switch to RWX" answer.

**🎯 Senior:** _"Walk me through what happens, step by step, when a PVC bound to a `Retain`-policy PV is deleted, and how you'd safely reuse that data."_
**Model answer:** Deleting the PVC does not delete the PV or its underlying storage asset — the PV transitions to the `Released` phase, but it retains a `claimRef` pointing at the now-deleted PVC, which prevents it from being automatically bound to a new claim even if capacity and access modes match. To reuse it, I'd first verify the data is what I expect (mount it read-only from a debug Pod if needed), then either edit the PV to clear `spec.claimRef` so it becomes `Available` again, or delete and recreate the PV object referencing the same underlying volume ID/handle, and finally create a new PVC that explicitly requests that specific PV (via `volumeName` in the PVC spec, or matching storageClassName/capacity/accessModes for the scheduler to bind it). I'd treat this as a deliberate, documented recovery procedure rather than routine operation, since it bypasses the normal dynamic-provisioning lifecycle.
_What the interviewer is probing for:_ Real hands-on familiarity with the Released-PV recovery workflow, not just knowing that "Retain keeps the data."

**🎯 Architect:** _"How would you design StorageClass and reclaim-policy governance across a platform serving dozens of teams with mixed stateful and stateless workloads?"_
**Model answer:** I'd offer at least two tiers of StorageClass by default — a `Delete`-policy tier for ephemeral/scratch/dev workloads, and a `Retain`-policy tier (possibly gp3/premium-tier disks) explicitly labeled and documented for production stateful workloads — and use admission policy (an OPA/Kyverno policy or a custom admission webhook, §77) to block PVCs referencing production namespaces from using a `Delete`-policy StorageClass. I'd pair this with a scheduled audit job that reports on `Released` PVs older than a threshold, since they represent both unnecessary cloud spend and stale data sitting outside the managed lifecycle. For access modes, I'd steer teams by default toward `ReadWriteOnce`/`ReadWriteOncePod` and require an explicit justification (reviewed in PR) for `ReadWriteMany` requests, given the added operational cost and different consistency model of shared-filesystem backends. Finally, I'd bake reclaim-policy and access-mode choices into the platform's Helm chart/Kustomize base defaults (§82–§86) so individual application teams inherit safe defaults rather than needing to get this right from scratch every time.
_What the interviewer is probing for:_ Platform-level thinking — tiered StorageClasses, policy enforcement, cost/data-governance auditing, and building safe defaults into shared tooling rather than relying on every team getting it right independently.

## 12. Common Misconceptions

1. **"Access mode is something Kubernetes enforces independently of the storage backend."** It reflects what the underlying storage technology physically supports; Kubernetes surfaces it, but a CSI driver backed by block storage cannot be made to support `ReadWriteMany` by requesting it in a PVC.
2. **"`ReadWriteOnce` means only one Pod can mount the volume."** It restricts attachment to one _node_; historically, multiple Pods on that same node could still mount it — `ReadWriteOncePod` was introduced specifically to close this gap.
3. **"`Retain` is equivalent to a backup."** A Released PV still depends on the same underlying disk existing and being intact; it protects against accidental _Kubernetes-object_ deletion, not against the disk itself being lost, corrupted, or deleted at the cloud-provider level.
4. **"Reclaim policy is a per-PVC setting."** It's set on the StorageClass (inherited by dynamically provisioned PVs) or directly on a statically provisioned PV — an individual PVC author cannot override it per-claim.

## 13. 🔑 Key Takeaways

- Access modes (RWO/ROX/RWX/RWOP) describe mount concurrency the storage backend physically supports, and are enforced at mount/attach time, not by API-server admission.
- `ReadWriteOncePod` closes a real gap left by `ReadWriteOnce`, restricting a volume to a single Pod cluster-wide rather than just a single node.
- Reclaim policy (`Delete` vs. `Retain`) determines whether deleting a PVC destroys the underlying storage — `Delete` is the common StorageClass default and is unsafe for production stateful data without explicit override.
- A `Retain`-ed PV moves to `Released`, not `Available`, and requires manual `claimRef` cleanup or PV recreation before it can be bound to a new claim.
- Governance (tiered StorageClasses, admission policy, periodic Released-PV audits) is how platform teams keep these settings safe by default rather than relying on every application team getting them right.

## 14. Related Concepts & What's Next

This section builds directly on CSI architecture (§60) and feeds into the next two sections: StatefulSet storage patterns (§62) depend on correctly understanding per-replica `ReadWriteOnce` semantics via `volumeClaimTemplates`, and Volume Snapshots (§63) offer an alternative, more granular data-protection mechanism that complements (rather than replaces) reclaim-policy planning.

**Next Section:** §62 — `Section-62-Part8-StatefulSet-Storage-Patterns-volumeClaimTemplates.md`
