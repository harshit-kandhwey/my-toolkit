# Section 33 (Part 5): StatefulSets: Stable Network Identity, Ordered Deployment, Per-Replica Storage

## 1. Definition

**Plain language:** A Deployment's Pods are interchangeable cattle — any replica can be killed and replaced by an identical one with a new random name and a fresh, empty disk, and nothing breaks. Some workloads can't tolerate that: a database node needs to keep the same identity and the same data across restarts, and cluster members often need to come up in a specific order so they can find and join each other. A StatefulSet is the controller built specifically for that class of workload.

**Precise definition:** A **StatefulSet** is a workload controller that manages Pods with three guarantees a ReplicaSet/Deployment ([§27](../Part4/Section-27-Part4-ReplicaSets-Purpose-Relationship-To-Deployments.md), [§28](../Part4/Section-28-Part4-Deployments-Rolling-Updates-Rollbacks-Revision-History.md)) does not provide: **stable, predictable network identity** (each Pod gets a fixed ordinal name like `web-0`, `web-1`, `web-2` that persists across rescheduling, paired with a stable DNS entry via a **headless Service**), **ordered, graceful deployment and scaling** (Pods are created, updated, and terminated one at a time, in strict ordinal sequence, each waiting for the previous one to become Ready), and **stable, per-replica persistent storage** (each Pod ordinal gets its own PersistentVolumeClaim, created from a `volumeClaimTemplate`, that follows that specific ordinal across rescheduling rather than being shared or randomly reassigned). Together these guarantees make StatefulSets the correct primitive for distributed, stateful systems — databases, message queues, and consensus-based clusters — where "which specific instance this is" and "which specific disk it owns" both matter.

## 2. Why This Matters

- **Deployments actively work against clustered stateful software.** A Deployment's Pods have random names, no ordering guarantee, and (without a StatefulSet) no reliable way to give each replica its own persistent disk — exactly the three properties a system like a Postgres replica set, Kafka, or Elasticsearch depends on to know its own identity and rejoin the cluster correctly after a restart. [§27](../Part4/Section-27-Part4-ReplicaSets-Purpose-Relationship-To-Deployments.md) and [§28](../Part4/Section-28-Part4-Deployments-Rolling-Updates-Rollbacks-Revision-History.md) covered why Deployments are correct for stateless workloads; this section exists because that same design is actively wrong for state.
- **Stable network identity is what makes peer discovery possible without external coordination.** Because each Pod's DNS name (`web-0.web.default.svc.cluster.local`) is fixed for the lifetime of that ordinal, cluster members can reference each other by a name that survives Pod rescheduling — the headless Service and DNS mechanics behind this are covered fully in Part 7's Service and DNS sections.
- **Per-replica storage via `volumeClaimTemplates` is what prevents a rescheduled Pod from silently coming up empty.** When `web-1` is rescheduled to a different node, it reattaches to the exact same PersistentVolumeClaim it had before — this depends directly on the PVC mechanics covered in Part 8, and is the single biggest reason StatefulSets exist as a distinct object rather than being an option flag on Deployment.

🔑 **Key Takeaway:** Use a StatefulSet whenever a workload's individual replicas are not interchangeable — when identity, join order, or per-instance disk ownership matters — and use a Deployment for everything else; reaching for a StatefulSet by default for a stateless app only adds unnecessary ordering constraints and operational friction.

## 3. Prerequisites and Dependencies

Builds on [§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) (full Pod spec anatomy) and directly contrasts with [§27](../Part4/Section-27-Part4-ReplicaSets-Purpose-Relationship-To-Deployments.md)/[§28](../Part4/Section-28-Part4-Deployments-Rolling-Updates-Rollbacks-Revision-History.md) (ReplicaSet and Deployment mechanics) to explain why a separate controller exists; forward dependencies are Part 7 ([§48](../Part7/Section-48-Part7-Kubernetes-Networking-Model-Flat-Network.md)-[§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md), especially headless Service and CoreDNS mechanics that back stable network identity) and Part 8 ([§57](../Part8/Section-57-Part8-Volumes-emptyDir-hostPath-Ephemeral-Storage.md)-[§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md), especially `volumeClaimTemplates` and PVC lifecycle, covered in full depth there).

## 4. Architecture Diagram

```text
                     StatefulSet "web" (replicas: 3)
                                │
              ┌─────────────────┼─────────────────┐
              ▼                 ▼                 ▼
          web-0             web-1             web-2
      (created 1st)     (created 2nd,     (created 3rd,
                         waits for web-0    waits for web-1
                         Ready first)       Ready first)
           │                  │                   │
  ┌────────┴────────┐ ┌───────┴─────────┐ ┌───────┴─────────┐
  │ PVC: www-web-0  │ │ PVC: www-web-1  │ │ PVC: www-web-2  │
  │ (bound forever  │ │ (bound forever  │ │ (bound forever  │
  │ to this ordinal)│ |(to this ordinal)│ |(to this ordinal)│
  └─────────────────┘ └─────────────────┘ └─────────────────┘

  Stable DNS (via headless Service "web", ClusterIP: None):

      web-0.web.default.svc.cluster.local  → always resolves to web-0's Pod IP
      web-1.web.default.svc.cluster.local  → always resolves to web-1's Pod IP
      web-2.web.default.svc.cluster.local  → always resolves to web-2's Pod IP

  Scale-down order: reverse ordinal (web-2 terminated first, then web-1, then web-0)
  Scale-up / rollout order: ascending ordinal (web-0 first, then web-1, then web-2)
```

- **The headless Service (`clusterIP: None`) is mandatory, not optional** — it's what CoreDNS uses to publish one DNS record per Pod ordinal rather than a single load-balanced VIP; without it, StatefulSet Pods have no stable per-instance DNS name at all.
- **Ordinal index is baked into the Pod name itself** (`<statefulset-name>-<ordinal>`), starting at 0, and is what both the PVC naming (`<volumeClaimTemplate-name>-<statefulset-name>-<ordinal>`) and the ordered rollout/scaling logic key off of.
- **Termination and creation both respect ordinal order strictly by default** (`podManagementPolicy: OrderedReady`), which is exactly right for systems requiring sequential join (e.g., a database primary must exist before replicas start) but can be relaxed with `podManagementPolicy: Parallel` for workloads that don't need it.

## 5. Hands-On: Deploying and Operating a StatefulSet

### 5.1 Defining a StatefulSet with a Headless Service and Volume Claim Template

**Purpose:** Stand up a minimal three-replica stateful workload with per-replica storage and stable DNS.

```yaml
# web-headless-svc.yaml
apiVersion: v1
kind: Service
metadata:
  name: web
spec:
  clusterIP: None
  selector:
    app: web
  ports:
    - port: 80
      name: http
---
# web-statefulset.yaml
apiVersion: apps/v1
kind: StatefulSet
metadata:
  name: web
spec:
  serviceName: web
  replicas: 3
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      containers:
        - name: web
          image: nginx:1.25
          ports:
            - containerPort: 80
              name: http
          volumeMounts:
            - name: www
              mountPath: /usr/share/nginx/html
  volumeClaimTemplates:
    - metadata:
        name: www
      spec:
        accessModes: ["ReadWriteOnce"]
        storageClassName: standard
        resources:
          requests:
            storage: 5Gi
```

```bash
$ kubectl apply -f web-headless-svc.yaml -f web-statefulset.yaml
service/web created
statefulset.apps/web created

$ kubectl get pods -l app=web -w
NAME    READY   STATUS    RESTARTS   AGE
web-0   1/1     Running   0          8s
web-1   0/1     ContainerCreating   0   2s   # only starts after web-0 is Ready
web-1   1/1     Running   0          6s
web-2   1/1     Running   0          5s

$ kubectl get pvc
NAME        STATUS   VOLUME       CAPACITY   ACCESS MODES   STORAGECLASS
www-web-0   Bound    pvc-8a1f...  5Gi        RWO            standard
www-web-1   Bound    pvc-9c2e...  5Gi        RWO            standard
www-web-2   Bound    pvc-3d7b...  5Gi        RWO            standard
```

**Common errors:** Omitting `spec.serviceName`, or pointing it at a Service that isn't headless (`clusterIP: None`), causes the StatefulSet to be created but with no working per-Pod DNS resolution — a frequent source of "peers can't find each other" bugs that don't show up as an obvious error at apply time.

### 5.2 Verifying Stable Network Identity Across a Restart

**Purpose:** Demonstrate that ordinal identity, DNS name, and attached storage all survive a Pod being deleted and recreated — the core guarantee a Deployment cannot offer.

```bash
$ kubectl exec web-0 -- hostname
web-0

$ kubectl run -it --rm dns-test --image=busybox:1.36 --restart=Never -- \
    nslookup web-1.web.default.svc.cluster.local
Server:    10.96.0.10
Address:   10.96.0.10:53
Name:      web-1.web.default.svc.cluster.local
Address:   10.244.1.7

$ kubectl delete pod web-1
pod "web-1" deleted

$ kubectl get pods -l app=web
NAME    READY   STATUS    RESTARTS   AGE
web-0   1/1     Running   0          4m
web-1   1/1     Running   0          9s     # same name, same ordinal, reattached to www-web-1
web-2   1/1     Running   0          3m50s
```

**Production usage example:** This is exactly the mechanism a replicated database relies on — a rescheduled replica comes back as the same named member with the same disk still attached, so it can rejoin the cluster and resume replication rather than being treated as a brand-new, empty node.

### 5.3 Scaling and Ordered Rolling Updates

**Purpose:** Show that scale-up, scale-down, and rollout all respect ordinal order — critical for clustered systems with join/leave sequencing requirements.

```bash
$ kubectl scale statefulset web --replicas=5
statefulset.apps/web scaled
# web-3 created only after web-2 is confirmed Ready; then web-4

$ kubectl scale statefulset web --replicas=3
statefulset.apps/web scaled
# web-4 terminated first, then web-3 — reverse ordinal order

$ kubectl set image statefulset/web web=nginx:1.27
statefulset.apps/web image updated
$ kubectl rollout status statefulset/web
Waiting for partitioned roll out to finish: 1 out of 3 new pods have been updated...
statefulset rolling update complete 3 pods at revision web-7d4f9c...
```

**Common errors:** Scaling down does **not** delete the associated PVCs by default — `www-web-4` remains Bound after `web-4` is removed, which is deliberate (avoiding accidental data loss) but surprises teams expecting Kubernetes to reclaim storage automatically; PVCs must be deleted explicitly if the data is genuinely no longer needed.

## 6. Production Usage Notes

- **`podManagementPolicy: Parallel` is worth setting for workloads that don't require strict join ordering** (e.g., some Elasticsearch topologies), since the default `OrderedReady` policy can make scale-up of a large StatefulSet noticeably slow — each Pod waits for the previous one's readiness probe before starting.
- **Most production stateful workloads are run via a purpose-built Helm chart or Operator** ([§85](../Part11/Section-85-Part11-Helm-vs-Kustomize-vs-Raw-Manifests-Decision-Framework.md)) rather than a hand-authored StatefulSet manifest, because real systems like Postgres or Kafka need additional automation around initialization, leader election, and backup that a bare StatefulSet doesn't provide on its own — but the Operator itself is almost always managing a StatefulSet underneath.
- **`updateStrategy.rollingUpdate.partition`** lets you update only Pods with an ordinal greater than or equal to the partition value, a manual canary mechanism specific to StatefulSets — useful for validating a new image against a single high-ordinal replica before rolling it out cluster-wide.

## 7. Security Considerations

- Per-replica PersistentVolumeClaims often hold sensitive data at rest (database files, message logs) — StorageClass-level encryption and access controls (Part 8, Part 15) matter more here than for typical stateless Deployment storage, since the data genuinely persists across the Pod's lifecycle rather than being ephemeral.
- Headless Services expose per-Pod DNS names that make individual replicas directly addressable — a NetworkPolicy ([§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)) should still constrain which Pods may actually connect to each StatefulSet member, since stable naming does not imply any access control on its own.

## 8. Common Troubleshooting Scenarios

| Symptom                                                    | Likely Cause                                                                                      | Resolution Path                                                                                                      |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------- |
| `web-1` stuck `Pending`, `web-2`/`web-3` never created     | `OrderedReady` policy blocking on a Pod that never becomes Ready (failing probe, PVC not binding) | `kubectl describe pod web-1`; fix the underlying readiness or storage-binding issue before later ordinals will start |
| PVC still `Bound` and consuming storage after scaling down | StatefulSets never auto-delete PVCs on scale-down by design                                       | Manually delete the orphaned PVC once the data is confirmed no longer needed                                         |
| Pod can't resolve a peer's stable DNS name                 | Headless Service missing or `clusterIP` not set to `None`                                         | Verify the Service manifest and confirm `serviceName` on the StatefulSet matches it                                  |
| Rolling update seems to skip most replicas                 | `updateStrategy.rollingUpdate.partition` left set from a prior canary test                        | Reset `partition` to `0` to allow the update to proceed for all ordinals                                             |

## 9. Best Practices

- Always pair a StatefulSet with a dedicated headless Service using the same selector, and set `serviceName` explicitly rather than relying on any implicit default.
- Use `volumeClaimTemplates` rather than a shared, pre-created PVC referenced by all replicas — sharing one PVC across ordinals breaks the per-instance storage guarantee entirely for most access modes.
- Prefer an Operator ([§85](../Part11/Section-85-Part11-Helm-vs-Kustomize-vs-Raw-Manifests-Decision-Framework.md)) over a hand-rolled StatefulSet for any genuinely complex stateful system (databases, coordination services), reserving raw StatefulSet manifests for simpler or custom cases.

## 10. Common Anti-Patterns / Mistakes

- **Using a StatefulSet for a stateless workload "just in case,"** which adds unnecessary ordered-rollout latency and operational complexity with no corresponding benefit.
- **Forgetting the headless Service**, leaving Pods with stable names but no working stable DNS — the network-identity guarantee silently doesn't function.
- **Assuming scaling down deletes the corresponding PVCs**, leading to orphaned storage costs accumulating unnoticed across repeated scale up/down cycles.

## 11. Interview Questions

**🎯 Beginner:** _"What three things does a StatefulSet provide that a Deployment doesn't?"_
**Model answer:** Stable, predictable Pod names and network identity that persist across rescheduling; ordered, sequential Pod creation and termination instead of all-at-once; and stable per-replica persistent storage via `volumeClaimTemplates`, where each ordinal keeps its own PVC across restarts rather than getting a fresh, empty volume.
_What the interviewer is probing for:_ Clean recall of the three defining guarantees, not just "it's for databases."

**🎯 Intermediate:** _"Why does a StatefulSet require a headless Service, and what actually breaks if you forget it?"_
**Model answer:** The headless Service (`clusterIP: None`) is what tells CoreDNS to publish one DNS `A`/`AAAA` record per Pod ordinal instead of a single load-balanced ClusterIP. Without it, the StatefulSet's Pods still get stable ordinal names and stable storage, but there's no way for one replica to address another by a fixed, resolvable name — peer discovery for clustered systems like a database replica set breaks silently, since nothing about pod creation itself fails; it's only DNS resolution between members that doesn't work.
_What the interviewer is probing for:_ Understanding that the three StatefulSet guarantees are somewhat independent, and that DNS identity specifically depends on an easily-missed companion object.

**🎯 Senior:** _"A StatefulSet scale-up from 3 to 5 replicas seems to be stuck after creating the 4th Pod. How do you diagnose it?"_
**Model answer:** By default, `podManagementPolicy: OrderedReady` means ordinal 4 must pass its readiness probe before ordinal 5 is even created — so I'd start with `kubectl describe pod web-3` (0-indexed, so the 4th Pod) to check probe status, then check whether its PVC bound successfully (`kubectl get pvc`), since a StorageClass provisioning failure or an access-mode conflict would also block readiness. If the workload genuinely doesn't require strict join ordering, I'd also consider whether `podManagementPolicy: Parallel` was a better fit from the start to avoid this kind of serialized bottleneck during scale operations.
_What the interviewer is probing for:_ Practical, ordered diagnostic instinct connecting the ordering guarantee to concrete failure points (probes, storage), not just "check the logs."

**🎯 Architect:** _"When would you choose to run a stateful database directly as a hand-authored StatefulSet versus adopting a database Operator, and what are you trading off?"_
**Model answer:** A hand-authored StatefulSet gives full, transparent control over every field, which is fine for simpler systems or where the team wants no dependency on third-party CRDs and controllers — but it leaves you to manually build initialization ordering, leader election, backup/restore, failover automation, and version-upgrade orchestration, all of which a mature Operator ([§85](../Part11/Section-85-Part11-Helm-vs-Kustomize-vs-Raw-Manifests-Decision-Framework.md)) already encodes as controller logic reacting to a purpose-built CRD. The trade-off is operational maturity and reduced manual toil against an added dependency (the Operator itself, its update cadence, and its own potential bugs) and less granular control over exactly what happens under the hood. For anything beyond a simple, low-stakes stateful service, I'd default to a well-maintained Operator and reserve raw StatefulSets for cases where no adequate Operator exists or where full manual control is a deliberate requirement.
_What the interviewer is probing for:_ Architectural judgment about when abstraction (Operators) earns its complexity versus when direct control is the better call.

## 12. Common Misconceptions

1. **"A StatefulSet automatically replicates or shards data across its Pods."** It provides identity, ordering, and storage stability only — actual data replication logic is the application's (or Operator's) responsibility, not something Kubernetes does natively.
2. **"Deleting a StatefulSet also deletes its PersistentVolumeClaims."** PVCs created via `volumeClaimTemplates` are deliberately retained after the StatefulSet (or individual Pods) are deleted, to prevent accidental data loss.
3. **"Scaling a StatefulSet works exactly like scaling a Deployment."** Scale-up and scale-down happen strictly in ordinal order under the default policy, unlike a Deployment's unordered Pod creation/deletion.
4. **"Any workload with a database in it needs a StatefulSet."** A single-instance database with no clustering requirement, or one using external managed storage without per-replica identity needs, can often run perfectly well as a Deployment with one replica.

## 13. 🔑 Key Takeaways

- StatefulSets exist to give ordinal Pod identity, ordered lifecycle operations, and stable per-replica storage — three guarantees a Deployment/ReplicaSet pair does not provide.
- A headless Service (`clusterIP: None`) is mandatory for the stable DNS identity guarantee to actually function.
- `volumeClaimTemplates` bind each ordinal to its own PersistentVolumeClaim, which survives Pod rescheduling and is not deleted automatically on scale-down.
- Default `OrderedReady` Pod management processes replicas strictly in ordinal sequence; `Parallel` is available when strict ordering isn't required.
- Most production stateful systems are better served by a database Operator built on top of a StatefulSet than by a hand-authored StatefulSet manifest alone.

## 14. Related Concepts & What's Next

[§24](../Part4/Section-24-Part4-Pod-Smallest-Deployable-Unit-Full-Pod-Spec-Anatomy.md) supplied the Pod spec fundamentals this section extends with ordinal identity and per-replica storage, while [§27](../Part4/Section-27-Part4-ReplicaSets-Purpose-Relationship-To-Deployments.md) and [§28](../Part4/Section-28-Part4-Deployments-Rolling-Updates-Rollbacks-Revision-History.md) provided the contrast against ReplicaSets and Deployments that explains why StatefulSets exist as a separate controller. The headless Service and DNS mechanics referenced throughout are covered in full in Part 7 ([§48](../Part7/Section-48-Part7-Kubernetes-Networking-Model-Flat-Network.md)-[§56](../Part7/Section-56-Part7-In-Cluster-Network-Troubleshooting-Toolkit.md)), and `volumeClaimTemplates`/PVC lifecycle in full depth in Part 8 ([§57](../Part8/Section-57-Part8-Volumes-emptyDir-hostPath-Ephemeral-Storage.md)-[§64](../Part8/Section-64-Part8-Storage-Troubleshooting-Stuck-PVCs-Mount-Failures.md)). [§34](./Section-34-Part5-DaemonSets-Node-Level-Agent-Workloads.md) shifts from per-replica identity to a different advanced workload shape entirely: running exactly one Pod per (or per matching subset of) cluster node.

**Next Section:** [§34](./Section-34-Part5-DaemonSets-Node-Level-Agent-Workloads.md) — `Section-34-Part5-DaemonSets-Node-Level-Agent-Workloads.md`
