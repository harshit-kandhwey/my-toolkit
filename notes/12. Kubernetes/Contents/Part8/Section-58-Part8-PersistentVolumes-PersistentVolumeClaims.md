# Section 58 (Part 8): PersistentVolumes and PersistentVolumeClaims

## 1. Definition

**Plain language:** A database Pod that gets rescheduled to a different node shouldn't lose its data, and an application developer shouldn't need to know or care which physical disk, cloud volume, or NFS export their storage actually lives on. Kubernetes solves both problems with a two-object split: cluster operators (or a provisioner) manage real storage as PersistentVolumes, and application developers simply request storage generically through PersistentVolumeClaims.

**Precise definition:** A **PersistentVolume (PV)** is a cluster-scoped API object representing a piece of real, provisioned storage — a cloud disk, an NFS share, an iSCSI target, or similar — with a defined capacity, access mode, and reclaim policy, existing independently of any Pod's lifecycle. A **PersistentVolumeClaim (PVC)** is a namespaced object through which a user requests storage by size and access mode, without needing to know the underlying storage implementation; the control plane's PV controller **binds** a suitable PV to a matching PVC in a one-to-one relationship. This PV/PVC split is Kubernetes' storage equivalent of the Service abstraction covered in §50 — just as a Service decouples a Pod's network identity from the actual backing Pods, a PVC decouples an application's storage request from the actual backing volume implementation.

## 2. Why This Matters

- **The PV/PVC split is what makes storage genuinely portable across environments.** A Deployment manifest referencing a PVC by name works identically whether that PVC is ultimately backed by an AWS EBS volume, an Azure Disk, an NFS server, or a local disk — the application manifest never needs to change, mirroring how §50's Service abstraction decouples workloads from the specific Pods backing them.
- **Binding, reclaim policy, and lifecycle are the three concepts every CKA candidate is tested on directly**, since storage-related exam tasks routinely involve creating a PV and PVC pair, diagnosing why a PVC is stuck `Pending`, or explaining what happens to data after a PVC is deleted — each governed by a distinct, precisely-defined mechanism this section covers explicitly.
- **Every StatefulSet workload (§33, Part 5) with per-replica storage, and every dynamic provisioning workflow (§59), builds directly on the binding mechanics defined here** — understanding manual static provisioning first makes the automation in §59 make sense rather than feel like unexplained magic.

🔑 **Key Takeaway:** PersistentVolumes represent real, provisioned storage independent of any Pod; PersistentVolumeClaims are namespaced requests for storage by size and access mode; and the PV controller binds the two together one-to-one — a decoupling that lets application manifests stay identical regardless of what actually backs the storage underneath.

## 3. Prerequisites and Dependencies

Builds directly on §57 (emptyDir/hostPath and their lack of persistence, the exact gap this section closes), and on the Service abstraction pattern from §50 as a conceptual parallel. Assumes familiarity with basic `kubectl apply` workflows and namespaces (Part 4). Sets up §59 (StorageClasses and Dynamic Provisioning), which automates the PV creation step covered manually here.

## 4. Architecture Diagram: PV/PVC Binding Lifecycle

```text
   Cluster-scoped                          Namespaced
   ┌────────────────────────────┐             ┌──────────────────────────┐
   │   PersistentVolume (PV)    │             │  PersistentVolumeClaim   │
   │   capacity: 10Gi           │◄────bind────┤  (PVC)                   │
   │   accessModes: [RWO]       │             │  requests: 5Gi           │
   │   reclaimPolicy: Retain    │             │  accessModes: [RWO]      │
   │   storageClassName: manual │             │  storageClassName: manual│
   └──────────────┬─────────────┘             └──────────────┬───────────┘
                  │                                          │
                  │ mounted via PVC reference                │
                  ▼                                          ▼
              ┌────────────────────────────────────────────────┐
              │                       Pod                      │
              │   volumes:                                     │
              │     - name: data                               │
              │       persistentVolumeClaim:                   │
              │         claimName: my-pvc                      │
              └────────────────────────────────────────────────┘

   PVC lifecycle states:      Pending ──► Bound ──► (Pod deleted) ──► Bound (PVC persists)
   PV reclaim on PVC delete:  Retain  → PV kept, marked Released, needs manual intervention
                              Delete  → underlying storage deleted automatically
                              Recycle → deprecated, do not use

   Binding rule: PV controller matches PVC to the SMALLEST PV that satisfies
   capacity, accessModes, and storageClassName — never partially, always 1:1
```

- **A PVC's `Pending` state almost always means no PV currently satisfies its request** — capacity too small, wrong access mode, or a `storageClassName` mismatch are the three most common reasons, in roughly that order of frequency.
- **The Pod layer never talks to the PV directly** — it references the PVC by name, and the PVC's binding to a specific PV is entirely transparent to the Pod spec, which is the whole point of the abstraction.
- **Reclaim policy determines what happens to data after the PVC is deleted**, not after the Pod is deleted — deleting a Pod that uses a PVC has no effect on the PV at all; the PVC (and its binding) persists independently.

## 5. Hands-On: Static Provisioning and Binding

### 5.1 Creating a PersistentVolume (Static Provisioning)

**Purpose:** Manually define a piece of storage as a PV, the foundational step before any PVC can bind to it — this is "static provisioning," as opposed to the on-demand automation covered in §59.

**Syntax:**

```yaml
apiVersion: v1
kind: PersistentVolume
metadata:
  name: pv-nfs-data
spec:
  capacity:
    storage: 10Gi
  accessModes:
    - ReadWriteOnce
  persistentVolumeReclaimPolicy: Retain
  storageClassName: manual
  nfs:
    server: nfs-server.example.internal
    path: "/exports/data"
```

**Example usage and expected output:**

```bash
$ kubectl apply -f pv-nfs-data.yaml
persistentvolume/pv-nfs-data created

$ kubectl get pv
NAME           CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS      STORAGECLASS   AGE
pv-nfs-data    10Gi       RWO            Retain           Available   manual         5s
```

**Production usage example:** Static PVs are still commonly used for pre-existing storage that must be onboarded into Kubernetes as-is — an NFS export a storage team already manages, or a cloud disk with existing data that must not go through a fresh dynamic-provisioning workflow.

**Common errors:** Setting `storageClassName` on the PV but forgetting to set the matching name on the PVC (or vice versa) — the PV controller treats an empty `storageClassName` as its own distinct class, so a PVC with no `storageClassName` will never bind to a PV that explicitly declares one, and this exact mismatch is one of the most common causes of a PVC stuck `Pending`.

### 5.2 Creating a PersistentVolumeClaim and Verifying the Bind

**Purpose:** Request storage generically from the application side, and confirm the PV controller successfully bound it to the PV created above.

**Syntax:**

```yaml
apiVersion: v1
kind: PersistentVolumeClaim
metadata:
  name: data-claim
  namespace: production
spec:
  accessModes:
    - ReadWriteOnce
  resources:
    requests:
      storage: 5Gi
  storageClassName: manual
```

**Example usage and expected output:**

```bash
$ kubectl apply -f data-claim.yaml
persistentvolumeclaim/data-claim created

$ kubectl get pvc -n production
NAME          STATUS   VOLUME         CAPACITY   ACCESS MODES   STORAGECLASS   AGE
data-claim    Bound    pv-nfs-data    10Gi       RWO            manual         3s

$ kubectl get pv
NAME           CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS   CLAIM                    STORAGECLASS   AGE
pv-nfs-data    10Gi       RWO            Retain           Bound    production/data-claim    manual         2m
```

**Production usage example:** Note the PVC requested only 5Gi but bound to a 10Gi PV — Kubernetes binds by "smallest PV that satisfies the request," not an exact match, and the Pod using this PVC gets the PV's full 10Gi capacity, not the 5Gi it asked for; this asymmetry surprises many teams the first time they inspect actual usable capacity.

**Common errors:** Deleting a PVC that's actively mounted by a running Pod — the PVC enters a `Terminating` state and hangs until the Pod using it is deleted first, since Kubernetes protects in-use storage from being torn out from under a running workload (via the `kubernetes.io/pvc-protection` finalizer).

### 5.3 Mounting the PVC in a Pod and Observing Reclaim Behavior

**Purpose:** Attach the bound PVC to an actual workload, then demonstrate what happens to the underlying PV when the PVC is eventually deleted, under each reclaim policy.

**Syntax:**

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: db-pod
  namespace: production
spec:
  containers:
    - name: db
      image: myregistry.example.com/postgres:15
      volumeMounts:
        - name: data
          mountPath: /var/lib/postgresql/data
  volumes:
    - name: data
      persistentVolumeClaim:
        claimName: data-claim
```

**Example usage and expected output:**

```bash
$ kubectl apply -f db-pod.yaml
pod/db-pod created

$ kubectl delete pvc data-claim -n production
persistentvolumeclaim "data-claim" deleted

$ kubectl get pv
NAME           CAPACITY   ACCESS MODES   RECLAIM POLICY   STATUS      CLAIM   STORAGECLASS   AGE
pv-nfs-data    10Gi       RWO            Retain           Released    <none>  manual         10m
```

**Production usage example:** With `Retain` (as configured here), the PV moves to `Released` rather than being deleted or reused automatically — a cluster operator must manually inspect, wipe, and either delete the PV or reset its `claimRef` before it can be bound again, a deliberate manual safety gate for data that might still be needed.

**Common errors:** Assuming a `Released` PV is immediately reusable by a new PVC — it is not; a `Released` PV retains its old `claimRef` internally and won't automatically rebind until an operator explicitly clears that reference or deletes and recreates the PV object.

## 6. Production Usage Notes

- **Access modes (`ReadWriteOnce`, `ReadOnlyMany`, `ReadWriteMany`) are enforced at the PV/PVC level but their actual support depends entirely on the underlying storage backend** — most cloud block storage (EBS, Azure Disk, PD) only supports `ReadWriteOnce`, while `ReadWriteMany` typically requires a networked filesystem like NFS, EFS, or a CSI driver built specifically for it (full depth in §61).
- **`ReadWriteOnce` since Kubernetes 1.22+ is enforceable at the node level rather than the Pod level** (`ReadWriteOncePod`, a distinct, stricter access mode added later) — worth distinguishing during upgrades, since older assumptions about "one node" vs. "one Pod" exclusivity can silently change behavior.
- **Reclaim policy defaults differ by provisioning path** — statically created PVs default to `Retain` unless set otherwise, while dynamically provisioned PVs (§59) inherit the reclaim policy of their StorageClass, which commonly defaults to `Delete` — a distinction that has caused real data-loss incidents when teams assumed `Retain` was universal.

## 7. Security Considerations

- **PV specs frequently embed storage backend credentials or connection details** (NFS server addresses, cloud volume IDs tied to specific accounts) — these are cluster-scoped objects, so RBAC controlling who can create or view PVs matters as much as PVC-level RBAC.
- **A `Retain`ed PV containing sensitive data is not automatically wiped** — an operator reusing that storage for a different, unrelated PVC without manually scrubbing it first risks exposing the previous tenant's data to a new workload, a genuine multi-tenancy concern.
- **PVC-to-Pod binding has no inherent authorization check beyond RBAC and namespace boundaries** — any Pod in the same namespace that references a PVC by name can mount it, so tenant isolation depends on namespace-level RBAC (§75, Part 10) being correctly enforced, not on anything storage-specific.

## 8. Common Troubleshooting Scenarios

| Symptom                                           | Cause                                                                                          | Fix                                                                                                                            |
| ------------------------------------------------- | ---------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| PVC stuck in `Pending`                            | No PV satisfies requested capacity, access mode, or matching `storageClassName`                | `kubectl describe pvc` for the exact reason; create/adjust a matching PV, or check StorageClass (§59) for dynamic provisioning |
| PVC stuck `Terminating`                           | PVC still referenced by a running Pod (protected by the pvc-protection finalizer)              | Delete the Pod using the PVC first, then the PVC deletion completes                                                            |
| PV shows `Released` and won't rebind to a new PVC | Reclaim policy is `Retain`; the released PV still carries a stale `claimRef`                   | Manually clear `spec.claimRef` on the PV (or delete/recreate it) before it can bind again                                      |
| Data unexpectedly gone after deleting a PVC       | Reclaim policy was `Delete`, not `Retain`, so the underlying storage was removed automatically | Confirm reclaim policy before deleting PVCs holding important data; set `Retain` explicitly where data must survive            |
| Pod stuck `Pending` referencing a bound PVC       | PV's underlying storage is zone/node-restricted and no eligible node exists for scheduling     | Check the PV's node affinity rules and cross-reference against actual node topology/zone placement                             |

## 9. Best Practices

- Explicitly set `persistentVolumeReclaimPolicy: Retain` for any PV holding data that must survive accidental PVC deletion, and treat `Delete` as an opt-in for genuinely disposable storage only.
- Always check `kubectl describe pvc` (not just `kubectl get pvc`) when a claim is stuck `Pending` — the Events section usually states the exact binding failure reason directly.
- Match `storageClassName` deliberately between PV and PVC (including explicitly setting it to `""` on both if intentionally opting out of any class) rather than leaving it unset and hoping the default behavior matches expectations.

## 10. Common Anti-Patterns / Mistakes

- **Deleting a PVC without first checking its reclaim policy**, discovering only afterward that `Delete` had already destroyed the underlying storage irrecoverably.
- **Assuming a Pod deletion affects the PV or PVC in any way** — Pods are fully decoupled from PV/PVC lifecycle; only explicit PVC deletion (and then reclaim policy) determines the storage's fate.
- **Leaving `storageClassName` unset on one side of a PV/PVC pair while explicitly setting it on the other**, causing binding to silently fail since an unset class is treated as its own distinct (empty) class, not a wildcard.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a PersistentVolume and a PersistentVolumeClaim?"_
**Model answer:** A PersistentVolume represents actual, provisioned storage — a real disk, NFS share, or similar — and is a cluster-scoped object typically managed by a cluster operator or a provisioner. A PersistentVolumeClaim is a namespaced request from an application for storage of a given size and access mode, without needing to know or specify what's actually backing it. The PV controller binds a suitable PV to a PVC automatically, and Pods reference storage only through the PVC, never the PV directly — this is what lets the same Pod manifest work regardless of what kind of storage is actually behind the scenes.
_What the interviewer is probing for:_ Clear grasp of the abstraction split and which object a Pod actually references.

**🎯 Intermediate:** _"A PVC has been stuck in `Pending` status for several minutes. Walk me through how you'd diagnose it."_
**Model answer:** I'd start with `kubectl describe pvc <name>`, since the Events section almost always states the exact reason the PV controller couldn't bind it — most commonly no PV exists with sufficient capacity, a matching access mode, or the same `storageClassName`. I'd then check `kubectl get pv` to see what's actually `Available` versus already `Bound` elsewhere, and compare capacity and access modes side by side against the PVC's request. If the cluster relies on dynamic provisioning (§59) rather than pre-created PVs, I'd instead check whether the referenced StorageClass exists and whether its provisioner is healthy, since in that case there's no static PV to inspect at all — the failure would be at the provisioner level instead.
_What the interviewer is probing for:_ A concrete, ordered diagnostic process rather than vague troubleshooting, and awareness that static and dynamic provisioning fail differently.

**🎯 Senior:** _"Your team accidentally deleted a PVC that was backing a production database, and now the data appears to be gone. What would you check, and how would you prevent this going forward?"_
**Model answer:** First I'd check the PV's reclaim policy at the time of deletion — if it was `Delete`, the underlying storage was very likely destroyed automatically the moment the PVC was removed, and recovery depends entirely on whatever backup exists outside Kubernetes (a volume snapshot, §63, or an external database backup), not on anything Kubernetes itself retains. If the policy was `Retain`, there's a real chance the PV still exists in a `Released` state with the data intact, just disconnected from any PVC, in which case I'd locate that PV, verify the data, and manually rebind it (clearing `claimRef`) to a new PVC rather than assuming it's lost. Going forward, I'd enforce `Retain` as the default reclaim policy for any StorageClass backing stateful production workloads, add a `kubectl` admission policy or manual approval gate on PVC deletions in production namespaces, and pair that with regular volume snapshots (§63) so a reclaim-policy mistake alone can never be the single point of failure for critical data.
_What the interviewer is probing for:_ Ability to reason through an active incident calmly, and translate the specific failure into concrete, durable prevention rather than a one-off fix.

**🎯 Architect:** _"How would you design storage governance across a multi-team cluster so that reclaim-policy and access-mode mistakes like accidental data loss become structurally unlikely, not just a documented warning?"_
**Model answer:** I'd centralize StorageClass definitions (§59) under platform-team ownership, each with an explicit, deliberately chosen reclaim policy baked in — `Retain` as the default for anything tagged stateful/production, with `Delete` reserved for classes explicitly named and documented as ephemeral/dev-tier — so individual application teams never make that choice ad hoc per PV. I'd back this with an OPA Gatekeeper or Kyverno policy that blocks PVC deletion in production namespaces without an explicit annotation or a separate approval step, and pair every stateful workload's StorageClass with a mandatory VolumeSnapshotClass (§63) so a reclaim-policy failure is never the last line of defense. I'd also require access mode and capacity requests to be validated against actual backend capability at admission time (many teams misrequest `ReadWriteMany` against a backend that silently only supports `ReadWriteOnce`), catching a class of failure that otherwise only surfaces at Pod scheduling time, often during an incident rather than during review.
_What the interviewer is probing for:_ Systems-level thinking about turning individual best practices into structural, enforced platform guarantees across many teams.

## 12. Common Misconceptions

1. **"Deleting a Pod deletes its PVC and PV too."** Pods are fully decoupled from PV/PVC lifecycle — deleting a Pod has zero effect on the PVC or PV it referenced; only explicit PVC deletion (and then reclaim policy) affects the underlying storage.
2. **"A PVC always gets exactly the capacity it requested."** The PV controller binds the smallest PV that satisfies the request, which is very often larger than requested — the Pod gets the PV's actual capacity, not the PVC's requested minimum.
3. **"Retain and Delete reclaim policies behave the same, just with different names."** `Retain` requires manual operator intervention before the PV can be reused and never touches the underlying data; `Delete` automatically destroys the underlying storage the moment the PVC is removed — the practical difference is the entire boundary between recoverable and unrecoverable data loss.

## 13. 🔑 Key Takeaways

- A PersistentVolume represents real, provisioned storage (cluster-scoped); a PersistentVolumeClaim is a namespaced request for storage that the PV controller binds one-to-one to a satisfying PV.
- Pods reference storage only through the PVC name, never the PV directly, which is what makes application manifests portable across different underlying storage implementations.
- Reclaim policy (`Retain` vs. `Delete`) determines what happens to the underlying storage after PVC deletion, and defaults differ between statically created PVs and dynamically provisioned ones (§59).
- A stuck `Pending` PVC almost always traces to a capacity, access-mode, or `storageClassName` mismatch, diagnosable directly via `kubectl describe pvc`.
- `Released` PVs under a `Retain` policy require manual operator action (clearing `claimRef`) before they can be bound to a new PVC — they don't rebind automatically.

## 14. Related Concepts & What's Next

This section closes the gap left by §57's ephemeral `emptyDir`/`hostPath` volumes, giving storage an independent lifecycle from any single Pod or node through the PV/PVC binding model — conceptually parallel to how §50's Service abstraction decouples network identity from specific backing Pods. Everything demonstrated here was **static** provisioning, requiring a cluster operator to manually create each PV ahead of time; §59, immediately next, covers **StorageClasses and Dynamic Provisioning**, which automates PV creation on-demand as PVCs are created, the model almost universally used in real production clusters today.

**Next Section:** §59 — `Section-59-Part8-StorageClasses-Dynamic-Provisioning.md`
