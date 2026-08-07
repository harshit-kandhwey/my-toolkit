# Section 62 (Part 8): StatefulSet Storage Patterns (volumeClaimTemplates)

## 1. Definition

**Plain language:** A Deployment's Pods are interchangeable and can share a volume or go without persistent storage entirely, but a database replica needs its _own_ disk that follows it specifically across restarts and reschedules — `volumeClaimTemplates` is the mechanism that gives every StatefulSet replica exactly that: a dedicated, stable PersistentVolumeClaim tied to its identity, not just to the Pod.

**Precise definition:** `volumeClaimTemplates` is a StatefulSet spec field that defines one or more PVC templates the StatefulSet controller uses to automatically create a distinct, ordinally-named PersistentVolumeClaim (`<template-name>-<statefulset-name>-<ordinal>`) for each replica, at creation time, which is then re-attached to that same replica's Pod on every restart or reschedule — combining the stable network identity StatefulSets already provide ([§33](../Part5/Section-33-Part5-Statefulsets-Stable-Network-Identity-Ordered-Deployment.md)) with equally stable, per-replica storage identity.

## 2. Why This Matters

- **This is the mechanism that makes running stateful workloads like databases, message queues, and distributed caches viable on Kubernetes at all** — without it, every Pod restart of a stateful application would either lose its data (ephemeral storage) or fight over a single shared volume (a manually-managed shared PVC), neither of which matches how these systems are actually designed to run.
- **Per-replica PVCs are not automatically deleted with the StatefulSet by default** — understanding this data-retention behavior (and its interaction with the reclaim policy from [§61](./Section-61-Part8-Access-Modes-RWO-ROX-RWX-Reclaim-Policies.md)) is essential to avoid two opposite mistakes: assuming storage disappears with the StatefulSet (leading to orphaned, cost-incurring volumes) or assuming it's always retained safely (when reclaim policy is `Delete`, it is not).
- **The ordinal naming and per-replica binding directly determines what happens during scale-down and scale-up** — a replica that's scaled down and later scaled back up reattaches to _its own_ previous PVC (same ordinal), preserving its data, which is a load-bearing assumption for any distributed stateful system relying on identity-to-data continuity (e.g., a Cassandra or etcd-like quorum member rejoining with its prior state).

🔑 **Key Takeaway:** `volumeClaimTemplates` binds storage identity to Pod ordinal identity, not to the Pod object itself — every `pod-N` in a StatefulSet always gets `pvc-template-pod-N`, across restarts, rescheduling, and scale-down/scale-up cycles, and understanding this exact binding (plus that it survives StatefulSet deletion by default) is what separates safe stateful operations from accidental data loss or orphaned storage.

## 3. Prerequisites and Dependencies

Builds on [§33](../Part5/Section-33-Part5-Statefulsets-Stable-Network-Identity-Ordered-Deployment.md) (StatefulSets: stable network identity and ordered deployment, Part 5), [§58](./Section-58-Part8-PersistentVolumes-PersistentVolumeClaims.md) (PersistentVolumeClaims), [§59](./Section-59-Part8-StorageClasses-Dynamic-Provisioning.md) (StorageClasses and Dynamic Provisioning), and [§61](./Section-61-Part8-Access-Modes-RWO-ROX-RWX-Reclaim-Policies.md) (Access Modes and Reclaim Policies) — a solid grasp of `ReadWriteOnce` semantics from [§61](./Section-61-Part8-Access-Modes-RWO-ROX-RWX-Reclaim-Policies.md) is required, since almost every `volumeClaimTemplates` use case relies on each replica having its own exclusive, non-shared volume.

## 4. Architecture Diagram

```text
   StatefulSet "cassandra" with volumeClaimTemplates: [name: data]

   ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
   │ cassandra-0 │     │ cassandra-1 │     │ cassandra-2 │
   │ (Pod)       │     │ (Pod)       │     │ (Pod)       │
   └──────┬──────┘     └──────┬──────┘     └──────┬──────┘
          │ mounts            │ mounts            │ mounts
          ▼                   ▼                   ▼
   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
   │data-cassandra│     │data-cassandra│     │data-cassandra│
   │     -0       │     │     -1       │     │     -2       │
   │  (PVC)       │     │  (PVC)       │     │  (PVC)       │
   └──────┬───────┘     └──────┬───────┘     └──────┬───────┘
          ▼                    ▼                    ▼
   ┌──────────────┐     ┌──────────────┐     ┌──────────────┐
   │   PV / Disk  │     │   PV / Disk  │     │   PV / Disk  │
   └──────────────┘     └──────────────┘     └──────────────┘

   Scale-down (replicas: 3 → 2):
     cassandra-2 Pod terminated  →  data-cassandra-2 PVC/PV PERSISTS (not deleted)

   Scale-up again (replicas: 2 → 3):
     cassandra-2 Pod recreated  →  reattaches to the SAME data-cassandra-2 PVC
                                    (prior data still there)

   StatefulSet deleted entirely:
     All Pods removed  →  all PVCs (data-cassandra-0/1/2) STILL PERSIST by default
                           (must be deleted manually, or via
                            persistentVolumeClaimRetentionPolicy, see below)
```

- **Each replica's PVC is created once, on that ordinal's first creation, and is never recreated as long as the ordinal persists** — this is what gives `cassandra-1`, specifically, a durable identity-to-data relationship across its entire lifecycle.
- **Scale-down does not delete PVCs by default** — this is a deliberate safety choice (accidental scale-down shouldn't equal data loss), but it means storage costs silently accumulate unless explicitly managed.
- **`persistentVolumeClaimRetentionPolicy` (stable since Kubernetes 1.27) is the field that lets you opt into automatic PVC deletion** on scale-down and/or StatefulSet deletion, rather than relying on manual cleanup.

## 5. Hands-On

### 5.1 Defining volumeClaimTemplates in a StatefulSet

**Purpose:** Give each replica of a stateful workload its own dedicated, dynamically provisioned volume tied to its ordinal identity.

**Syntax:**

```yaml
volumeClaimTemplates:
  - metadata:
      name: <template-name>
    spec:
      accessModes: ["ReadWriteOnce"]
      storageClassName: <storage-class>
      resources:
        requests:
          storage: <size>
```

**Example usage:**

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cassandra
spec:
  serviceName: cassandra-headless
  replicas: 3
  selector:
    matchLabels: { app: cassandra }
  template:
    metadata:
      labels: { app: cassandra }
    spec:
      containers:
        - name: cassandra
          image: cassandra:4.1
          volumeMounts:
            - name: data
              mountPath: /var/lib/cassandra
  volumeClaimTemplates:
    - metadata:
        name: data
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: gp3-retain
        resources:
          requests:
            storage: 100Gi
```

```bash
$ kubectl get pvc -l app=cassandra
NAME              STATUS   VOLUME    CAPACITY   ACCESS MODES   AGE
data-cassandra-0  Bound    pvc-a1b   100Gi      RWO            5m
data-cassandra-1  Bound    pvc-c3d   100Gi      RWO            5m
data-cassandra-2  Bound    pvc-e5f   100Gi      RWO            5m
```

**Production usage example:** A 3-node Cassandra StatefulSet pairs `gp3-retain` (a `Retain`-policy StorageClass, [§61](./Section-61-Part8-Access-Modes-RWO-ROX-RWX-Reclaim-Policies.md)) with `volumeClaimTemplates` specifically so that a rolling restart, a node drain ([§107](../Part14/Section-107-Part14-etcd-Backup-Restore-Procedures.md)), or even a full StatefulSet redeployment never risks losing a replica's SSTables — each `cassandra-N` Pod always reattaches to `data-cassandra-N`, preserving quorum state exactly as the application expects.

**Common errors:** Using a `ReadWriteMany` access mode in the template under the mistaken belief that it will let replicas share data — `volumeClaimTemplates` is designed around each replica getting its _own independent_ volume; sharing state between replicas via a common RWX volume defeats the purpose and is rarely what a stateful application's own replication protocol expects.

### 5.2 Scale-Down, Scale-Up, and PVC Retention Behavior

**Purpose:** Understand — and control — exactly what happens to per-replica storage across scaling events and StatefulSet deletion, since the default (retain everything, forever) is not always the desired behavior.

**Syntax:**

```yaml
spec:
  persistentVolumeClaimRetentionPolicy:
    whenDeleted: Retain | Delete
    whenScaled: Retain | Delete
```

**Example usage:**

```bash
$ kubectl scale statefulset cassandra --replicas=2
statefulset.apps/cassandra scaled

$ kubectl get pvc -l app=cassandra
NAME              STATUS   VOLUME    CAPACITY   AGE
data-cassandra-0  Bound    pvc-a1b   100Gi      10m
data-cassandra-1  Bound    pvc-c3d   100Gi      10m
data-cassandra-2  Bound    pvc-e5f   100Gi      10m   # still present after scale-down
```

```yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: cassandra
spec:
  persistentVolumeClaimRetentionPolicy:
    whenDeleted: Retain
    whenScaled: Delete
  # ...rest of spec
```

**Production usage example:** For a workload where scale-down genuinely means "this replica is gone for good" (a stateless-cache-like StatefulSet used only for stable naming), setting `whenScaled: Delete` avoids the operational burden of manually tracking and cleaning up orphaned PVCs after every scale-down, while still keeping `whenDeleted: Retain` so an accidental `kubectl delete statefulset` doesn't cascade into destroying all replicas' data at once.

**Common errors:** Assuming `persistentVolumeClaimRetentionPolicy` is available and defaulted the same way across all cluster versions — it graduated to stable in Kubernetes 1.27, and clusters running older versions have no such field, meaning all PVCs are unconditionally retained on both scale-down and StatefulSet deletion with no built-in opt-out.

## 6. Production Usage Notes

- **The default retention behavior (retain on both scale-down and deletion) is a safety-first default that predates `persistentVolumeClaimRetentionPolicy`** — many production clusters still rely on manual PVC cleanup scripts or GitOps-driven pruning rather than the newer field, and teams should check their cluster's Kubernetes version before assuming the field is available.
- **`volumeClaimTemplates` combined with a headless Service (`clusterIP: None`, referenced via `serviceName`) is what gives each replica both stable network identity and stable storage identity together** — the two mechanisms are usually discussed separately but are almost always deployed as a pair for real stateful workloads.
- **Changing a `volumeClaimTemplates` spec (e.g., resizing storage) after the StatefulSet already has replicas does not retroactively resize existing PVCs** — existing per-replica PVCs must be resized individually (if the StorageClass supports `allowVolumeExpansion`) or replaced, since the template only governs _new_ replica creation.

## 7. Security Considerations

- Per-replica PVCs created via `volumeClaimTemplates` inherit whatever encryption-at-rest and access controls the underlying StorageClass and CSI driver provide — verify the StorageClass used for sensitive stateful workloads (databases holding customer data) has encryption enabled by default, since it is not automatically implied by using a StatefulSet.
- Orphaned PVCs left behind after scale-down or StatefulSet deletion are a data-retention and compliance risk in regulated environments — a retained volume containing customer data that's forgotten about is effectively an unmanaged, unaudited copy of that data.
- RBAC controlling who can `kubectl scale` or delete a StatefulSet should be considered alongside PVC retention policy — a `whenScaled: Delete` policy means a scale-down action (which may have lower approval friction than an explicit `kubectl delete pvc`) can now destroy data, changing the effective blast radius of that RBAC permission.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                       | Cause                                                                                                     | Fix                                                                                                                                                                  |
| --------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Replaced/recreated replica Pod comes up with unexpected old data                              | This is expected behavior — the new Pod reattached to the same ordinal's PVC                              | Confirm this is actually the intended behavior; if a clean volume was expected, the PVC must be deleted manually first                                               |
| Scaling back up after scale-down doesn't restore prior replica data                           | `persistentVolumeClaimRetentionPolicy.whenScaled` was set to `Delete`                                     | Set `whenScaled: Retain` if scale-down/up cycles are expected to preserve data                                                                                       |
| PVCs pile up long after a StatefulSet was deleted                                             | Default retention behavior (or `whenDeleted: Retain`) left PVCs behind                                    | Explicitly `kubectl delete pvc -l <label>` after intentional StatefulSet teardown, or set `whenDeleted: Delete`                                                      |
| Resizing `volumeClaimTemplates.spec.resources.requests.storage` had no effect on running Pods | Template changes only apply to newly created ordinals, not existing PVCs                                  | Manually edit/resize each existing PVC (requires `allowVolumeExpansion: true` on the StorageClass, [§59](./Section-59-Part8-StorageClasses-Dynamic-Provisioning.md)) |
| New replica (higher ordinal) stuck `Pending` when others are healthy                          | StorageClass exhausted capacity/quota, or `volumeBindingMode: WaitForFirstConsumer` blocked on scheduling | Check StorageClass/provisioner capacity and quota; confirm the new Pod can actually be scheduled first                                                               |

## 9. Best Practices

- Pair `volumeClaimTemplates` with a `Retain`-policy StorageClass ([§61](./Section-61-Part8-Access-Modes-RWO-ROX-RWX-Reclaim-Policies.md)) for any stateful workload where per-replica data matters, since the default StorageClass `Delete` policy combined with StatefulSet PVC retention behavior creates confusing, inconsistent expectations about what actually survives.
- Explicitly set `persistentVolumeClaimRetentionPolicy` (on Kubernetes 1.27+) rather than relying on implicit default behavior, so the intended scale-down and deletion semantics are visible directly in the manifest.
- Build a periodic audit or cleanup process for orphaned per-replica PVCs left behind by StatefulSet deletions, especially in clusters still on the older default-retain-everything behavior.

## 10. Common Anti-Patterns / Mistakes

- **Using a single shared PVC across a StatefulSet's replicas instead of `volumeClaimTemplates`**, reintroducing the exact `ReadWriteOnce` attachment conflicts ([§61](./Section-61-Part8-Access-Modes-RWO-ROX-RWX-Reclaim-Policies.md)) that per-replica storage was designed to avoid.
- **Deleting and recreating a StatefulSet as a way to "reset" a stateful workload**, not realizing the old PVCs are retained by default and will silently reattach the previous data to the new StatefulSet's replicas.
- **Resizing a `volumeClaimTemplates` entry and assuming existing replicas picked up the change**, when in fact only newly created ordinals use the updated template.

## 11. Interview Questions

**🎯 Beginner:** _"What does `volumeClaimTemplates` do in a StatefulSet, and how is it different from a normal Pod volume?"_
**Model answer:** `volumeClaimTemplates` tells the StatefulSet controller to automatically create a separate PersistentVolumeClaim for each replica, named after that replica's stable ordinal (like `data-cassandra-0`), rather than every Pod sharing one volume or having no persistent storage at all. Unlike a plain Pod-level volume reference, this claim is tied to the replica's identity — it gets created once for that ordinal and is reattached to whatever Pod currently holds that ordinal across restarts, rather than being tied to a specific Pod object's lifecycle.
_What the interviewer is probing for:_ Basic grasp that the binding is to ordinal identity, not to a specific Pod instance.

**🎯 Intermediate:** _"If you scale a StatefulSet down from 5 replicas to 3, and then back up to 5, what storage does the new `pod-3` and `pod-4` get?"_
**Model answer:** By default, scaling down does not delete the PVCs for the removed ordinals — `data-statefulset-3` and `data-statefulset-4` remain bound, just unused while their Pods don't exist. Scaling back up to 5 recreates `pod-3` and `pod-4`, and the StatefulSet controller reattaches each to its existing, matching-ordinal PVC rather than provisioning new ones — so both replicas come back with whatever data was on those volumes before the scale-down, not empty disks. This behavior can be changed on Kubernetes 1.27+ using `persistentVolumeClaimRetentionPolicy.whenScaled: Delete` if that retention isn't desired.
_What the interviewer is probing for:_ Correct understanding of default retention on scale-down/up, and awareness of the newer opt-out mechanism.

**🎯 Senior:** _"You need to permanently increase the storage size for every replica of a running StatefulSet. Walk me through how you'd do it."_
**Model answer:** Editing `volumeClaimTemplates.spec.resources.requests.storage` on the StatefulSet only affects PVCs created for _new_ ordinals going forward — it does not retroactively resize any already-bound PVC. To resize existing replicas, I'd first confirm the StorageClass has `allowVolumeExpansion: true` ([§59](./Section-59-Part8-StorageClasses-Dynamic-Provisioning.md)), then edit each existing PVC's `spec.resources.requests.storage` directly (this is one of the few fields PVCs allow mutating post-creation), and depending on the CSI driver and filesystem, either the expansion completes online or requires a Pod restart to pick up the filesystem resize (`FileSystemResizePending` condition clearing after the kubelet completes the resize on next mount). I'd do this replica-by-replica for a StatefulSet, verifying each one completes before moving to the next, given these are usually ordered, quorum-sensitive workloads where taking multiple replicas down for resize simultaneously risks availability.
_What the interviewer is probing for:_ Real operational knowledge that template edits are not retroactive, and the actual per-PVC resize workflow including StorageClass prerequisites.

**🎯 Architect:** _"Design the storage strategy for a self-managed distributed database (e.g., Cassandra or a similar quorum-based system) running as a StatefulSet across three availability zones, considering durability, cost, and operational recovery."_
**Model answer:** I'd use `volumeClaimTemplates` with a `Retain`-policy, zone-aware StorageClass (using `volumeBindingMode: WaitForFirstConsumer` so the PVC binds to a zone matching wherever the scheduler actually places the Pod, avoiding cross-zone attach failures), giving each replica its own durable, per-ordinal disk. I'd pin `persistentVolumeClaimRetentionPolicy` explicitly — likely `whenScaled: Retain` (since removing a quorum member shouldn't silently discard its state before the operator confirms it's safe to do so) and `whenDeleted: Retain` (protecting against accidental full-StatefulSet deletion). For durability beyond the retained disks themselves, I'd layer Volume Snapshots ([§63](./Section-63-Part8-Volume-Snapshots-Cloning.md)) on a schedule as point-in-time recovery points independent of the live PVCs, since `Retain` alone protects against Kubernetes-object deletion but not against corruption or logical errors replicated across all replicas. Operationally, I'd document and rehearse the manual PVC re-bind procedure (clearing `claimRef`, [§61](./Section-61-Part8-Access-Modes-RWO-ROX-RWX-Reclaim-Policies.md)) as part of disaster-recovery runbooks (Part 14), so recovering a specific replica's data from a retained-but-orphaned PV isn't something the team is improvising for the first time during an actual incident.
_What the interviewer is probing for:_ Ability to combine zone-awareness, retention policy, snapshot-based recovery, and operational readiness into one coherent storage design for a genuinely stateful distributed system.

## 12. Common Misconceptions

1. **"volumeClaimTemplates creates one shared PVC for the whole StatefulSet."** It creates one distinct PVC _per replica ordinal_ — the entire point is per-replica isolation, not sharing.
2. **"Deleting a StatefulSet deletes its data."** By default, per-replica PVCs are retained after StatefulSet deletion; only `persistentVolumeClaimRetentionPolicy.whenDeleted: Delete` (1.27+) changes this.
3. **"Editing volumeClaimTemplates resizes existing replicas' storage."** It only affects PVCs created for new ordinals going forward; existing PVCs must be resized individually.
4. **"Scaling a StatefulSet back up after scaling down gives replicas fresh, empty volumes."** By default they reattach to their previous ordinal's retained PVC, data intact, unless `whenScaled: Delete` is explicitly set.

## 13. 🔑 Key Takeaways

- `volumeClaimTemplates` creates one PVC per replica ordinal, bound to that ordinal's identity across restarts and rescheduling, not to a specific Pod object.
- Default retention behavior keeps PVCs alive through both scale-down/up cycles and StatefulSet deletion — a deliberate safety default that can surprise teams expecting a "clean slate" on redeploy.
- `persistentVolumeClaimRetentionPolicy` (stable in 1.27+) is the explicit, in-manifest way to opt into automatic PVC deletion on scale-down and/or StatefulSet deletion.
- Template edits (including storage size) only apply to newly created ordinals — existing replicas' PVCs must be resized individually via direct PVC edits.
- Pairing `volumeClaimTemplates` with a `Retain`-policy StorageClass ([§61](./Section-61-Part8-Access-Modes-RWO-ROX-RWX-Reclaim-Policies.md)) and a headless Service gives stateful workloads both durable per-replica storage and stable network identity together.

## 14. Related Concepts & What's Next

This section connects [§33](../Part5/Section-33-Part5-Statefulsets-Stable-Network-Identity-Ordered-Deployment.md)'s StatefulSet fundamentals (Part 5) with the storage-specific mechanics of PersistentVolumeClaims ([§58](./Section-58-Part8-PersistentVolumes-PersistentVolumeClaims.md)) and Access Modes/Reclaim Policies ([§61](./Section-61-Part8-Access-Modes-RWO-ROX-RWX-Reclaim-Policies.md)), showing how they combine to give stateful workloads durable, identity-bound storage. [§63](./Section-63-Part8-Volume-Snapshots-Cloning.md) builds on this same PVC foundation to cover Volume Snapshots and Cloning — a complementary, point-in-time data-protection layer that sits on top of, rather than replaces, the retention strategy discussed here.

**Next Section:** [§63](./Section-63-Part8-Volume-Snapshots-Cloning.md) — `Section-63-Part8-Volume-Snapshots-Cloning.md`
