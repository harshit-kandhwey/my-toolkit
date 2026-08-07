# Section 110 (Part 14): Cluster Backup Strategies (Velero)

## 1. Definition

**Plain language:** [§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md) covered backing up etcd — the cluster's control-plane brain. But etcd only holds the _desired state_ of your cluster (specs, metadata, RBAC); it holds nothing about the actual bytes sitting inside your PersistentVolumes. A restored etcd snapshot brings back a Deployment object claiming a PVC — it does not bring back the database files that PVC's volume contained. **Velero** is the tool that closes that gap: it backs up both Kubernetes API object state and the underlying persistent volume data together, as one coordinated, application-consistent backup.

**Precise definition:** **Velero** is an open-source backup and disaster-recovery tool for Kubernetes clusters that runs as an in-cluster server (a Deployment plus a CLI client) and performs two coordinated operations per backup: (1) it queries the Kubernetes API server and serializes the specs of selected resources (by namespace, label selector, or resource type) into compressed JSON, uploading them to an object-storage backend (S3, GCS, Azure Blob, or any S3-compatible store, via a `BackupStorageLocation`); and (2) it triggers a **VolumeSnapshotter** plugin (CSI-based `VolumeSnapshot` or a provider-native snapshot API) to snapshot each PersistentVolume referenced by those resources, recorded via a `VolumeSnapshotLocation`. Restores reverse the process — Velero recreates the Kubernetes objects from the stored JSON and provisions new PVs from the snapshots, restoring both state and data together. Velero also supports **Backup Hooks** (pre/post exec commands inside a Pod, e.g. to flush a database before snapshotting its volume) and **Schedules** (cron-based recurring backups).

## 2. Why This Matters

- **etcd backup ([§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)) alone cannot recover a stateful application** — a restored Deployment for a PostgreSQL StatefulSet is a useless empty shell without the actual database files, and Velero is the standard tool that backs up both the object graph and the volume data as one atomic operation.
- **Velero backups are namespace- and label-selector-scoped**, making it the practical tool for both full-disaster-recovery scenarios and much narrower, everyday tasks — migrating one namespace between clusters, or restoring a single accidentally-deleted application without touching the rest of the cluster.
- **Velero's schedule and retention model turns disaster recovery from a manual, easily-forgotten task into an automated, continuously-verified capability** — a nightly cron-scheduled backup with a defined TTL is meaningfully more reliable than "someone remembers to run a backup before a risky change."

🔑 **Key Takeaway:** Velero backs up Kubernetes object state and PersistentVolume data together as one coordinated operation — the missing half of what an etcd snapshot ([§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)) alone provides — making it the standard tool for both full-cluster disaster recovery and narrower namespace-level migration/restore tasks.

## 3. Prerequisites and Dependencies

Builds directly on [§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md) (etcd Backup and Restore Procedures) — Velero is explicitly the broader-scope complement to an etcd snapshot, covering PV data that etcd never holds — and assumes familiarity with PersistentVolumes/PVCs ([§58](../Part8/Section-58-Part8-PersistentVolumes-PersistentVolumeClaims.md)) and CSI drivers. Forward-references [§111](./Section-111-Part14-Version-Skew-Policy-Deprecation-Handling.md) (Version Skew Policy and Deprecation Handling), since restoring a Velero backup across a cluster upgrade raises exactly the API-version compatibility questions [§111](./Section-111-Part14-Version-Skew-Policy-Deprecation-Handling.md) addresses.

## 4. Architecture Diagram

```text
┌────────────────────────────────────────────────────────────────────┐
│                         Velero Backup Flow                         │
│                                                                    │
│  velero backup create <name> --include-namespaces=production       │
│                        │                                           │
│                        ▼                                           │
│  ┌─────────────────────────────────────┐                           │
│  │  Velero Server (in-cluster Deploy)  │                           │
│  │  1. Query API server for matching   │                           │
│  │     resources (Deployments, Svcs,   │                           │
│  │     PVCs, ConfigMaps, Secrets...)   │                           │
│  │  2. Run pre-backup hooks (exec into │                           │
│  │     Pods: e.g. `pg_dump`, flush)    │                           │
│  │  3. Trigger VolumeSnapshotter for   │                           │
│  │     each referenced PV              │                           │
│  └─────────────┬───────────────┬───────┘                           │
│                │               │                                   │
│                ▼               ▼                                   │
│  ┌──────────────────────┐  ┌─────────────────────────┐             │
│  │ Object Storage       │  │ Volume Snapshots        │             │
│  │ (S3/GCS/Azure Blob)  │  │ (CSI VolumeSnapshot or  │             │
│  │ BackupStorageLocation│  │ cloud-native, e.g. EBS) │             │
│  │ - resource JSON      │  │ VolumeSnapshotLocation  │             │
│  │ - backup metadata    │  │                         │             │
│  └──────────────────────┘  └─────────────────────────┘             │
│                                                                    │
│                        Restore reverses both paths:                │
│           Object JSON ──► kubectl-apply-equivalent recreate        │
│           Volume Snapshot ──► new PV provisioned from snapshot     │
│                        (bound to the recreated PVC)                │
└────────────────────────────────────────────────────────────────────┘
```

- **Velero coordinates two independent storage systems** (object storage for API state, snapshot storage for volume data) into what appears to the operator as a single `velero backup create` / `velero restore create` operation.
- **Backup hooks run before the volume snapshot is taken**, which is what makes the resulting snapshot application-consistent rather than a crash-consistent snapshot of a database mid-write.
- **The `BackupStorageLocation` and `VolumeSnapshotLocation` are separate, independently-configurable resources** — a cluster can, for instance, store resource JSON in S3 while using a CSI snapshot class native to its cloud provider for volumes.

## 5. Hands-On

### 5.1 Installing Velero and Creating a First Backup

**Purpose:** Get Velero running in-cluster with an object-storage backend and take a namespace-scoped backup.

**Syntax:**

```bash
velero install \
  --provider aws \
  --plugins velero/velero-plugin-for-aws:v1.9.0 \
  --bucket my-velero-backups \
  --backup-location-config region=us-east-1 \
  --snapshot-location-config region=us-east-1 \
  --secret-file ./credentials-velero

velero backup create <backup-name> \
  --include-namespaces=<namespace> \
  --ttl=720h0m0s
```

**Example usage and expected output:**

```bash
$ velero backup create prod-backup-20260731 --include-namespaces=production --ttl=720h0m0s
Backup request "prod-backup-20260731" submitted successfully.
Run `velero backup describe prod-backup-20260731` or `velero backup logs prod-backup-20260731` for more details.

$ velero backup describe prod-backup-20260731
Name:         prod-backup-20260731
Phase:        Completed
Namespaces:
  Included:  production
Total items to be backed up:  47
Items backed up:              47
```

**Production usage example:** A `production` namespace backup taken right before a risky Helm upgrade ([§82](../Part11/Section-82-Part11-Helm-Fundamentals-Charts-Releases-Repositories.md)-adjacent territory) gives an immediate, namespace-scoped rollback path — `velero restore create --from-backup prod-backup-20260731` — that's far faster than reconstructing the namespace from GitOps manifests plus a separate PV data recovery process.

**Common errors:** Running `velero backup create` without first confirming `velero backup-location get` shows the `BackupStorageLocation` as `Available` — a misconfigured bucket or expired cloud credentials causes the backup to silently fail at the storage-upload step, and this is only visible via `velero backup logs`, not `describe`'s summary phase.

### 5.2 Scheduled Backups and Backup Hooks for Application Consistency

**Purpose:** Automate recurring backups and ensure a stateful application (e.g. a database) is quiesced before its volume is snapshotted.

**Syntax:**

```yaml
apiVersion: velero.io/v1
kind: Schedule
metadata:
  name: nightly-production-backup
  namespace: velero
spec:
  schedule: "0 2 * * *" # cron: 02:00 daily
  template:
    includedNamespaces:
      - production
    ttl: 336h0m0s # 14 days
```

```bash
# Pre/post hooks via Pod annotations, applied at backup time
kubectl annotate pod db-primary-0 -n production \
  pre.hook.backup.velero.io/command='["/bin/bash", "-c", "pg_dump -U postgres mydb > /backup/dump.sql"]' \
  pre.hook.backup.velero.io/timeout=3m
```

**Example usage and expected output:**

```bash
$ velero schedule create nightly-production-backup --schedule="0 2 * * *" --include-namespaces=production --ttl=336h0m0s
Schedule "nightly-production-backup" created successfully.

$ velero schedule get
NAME                        STATUS    CREATED                         SCHEDULE      BACKUP TTL   LAST BACKUP
nightly-production-backup   Enabled   2026-07-31 02:00:00 +0000 UTC   0 2 * * *     336h0m0s     6h ago
```

**Production usage example:** A `pre.hook.backup.velero.io` annotation running `pg_dump` before the PV snapshot ensures the database is in a known-consistent state at snapshot time — restoring from a crash-consistent snapshot of a live database mid-transaction is a materially riskier recovery path than restoring from one taken immediately after a clean dump.

**Common errors:** Relying on a Schedule's default retention (`ttl`) without confirming the `BackupStorageLocation`'s actual bucket lifecycle policy matches it — if the bucket independently expires objects sooner than the Velero TTL, `velero restore create` against an "available" backup listed by `velero backup get` fails because the underlying object storage data is already gone.

### 5.3 Restoring to a Different Cluster (Migration/DR Scenario)

**Purpose:** Demonstrate the disaster-recovery/migration use case — restoring a namespace's full state onto a brand-new cluster.

**Syntax:**

```bash
# On the target cluster, install Velero pointed at the SAME BackupStorageLocation
velero install --provider aws --bucket my-velero-backups --backup-location-config region=us-east-1 ...

velero restore create --from-backup <backup-name> \
  --namespace-mappings production:production-restored
```

**Example usage and expected output:**

```bash
$ velero restore create restore-20260731 --from-backup prod-backup-20260731
Restore request "restore-20260731" submitted successfully.

$ velero restore describe restore-20260731
Name:         restore-20260731
Phase:        Completed
Total items to be restored:  47
Items restored:              47
```

**Production usage example:** This exact flow is a real disaster-recovery test: stand up a fresh cluster, point a new Velero install at the existing S3 bucket, and restore — validating that the organization's actual recovery time objective (RTO) is achievable, not merely assumed, which is precisely the kind of exercise [§112](./Section-112-Part14-Disaster-Recovery-Planning-Kubernetes-Clusters.md)'s disaster recovery planning formalizes as a required, recurring practice.

**Common errors:** Restoring onto a cluster running a materially different Kubernetes minor version than the source without checking API deprecations first — a backup containing a now-removed API version (e.g. an old `Ingress` under `extensions/v1beta1`) fails to restore with an API-not-found error; this is exactly the version-skew and deprecation concern [§111](./Section-111-Part14-Version-Skew-Policy-Deprecation-Handling.md) covers next.

## 6. Production Usage Notes

- **Velero backups should be tested via periodic actual restores, not merely scheduled and assumed to work** — a backup that has never been restored is an unverified assumption, and the only way to know an RTO/RPO target is achievable is to actually exercise the restore path on a non-production cluster.
- **CSI-based volume snapshots (via `VolumeSnapshotLocation` with a CSI plugin) are the modern, portable approach**, replacing older provider-native snapshot APIs; confirm the cluster's CSI driver supports `VolumeSnapshot`/`VolumeSnapshotClass` objects before relying on Velero's CSI integration.
- **Backup retention (`--ttl`) and the underlying object-storage bucket's own lifecycle policy must be kept in sync** — a mismatch in either direction either loses backups Velero still believes exist, or retains stale backups Velero has already forgotten about, needlessly inflating storage cost.

## 7. Security Considerations

- **The credentials Velero uses to reach object storage (the `--secret-file` at install time) are as sensitive as full cluster read access** — a full backup contains every Secret in the backed-up namespaces in plaintext-decoded form (unless encryption-at-rest is separately configured on the bucket), so bucket access control deserves the same rigor as RBAC on the Secrets objects themselves.
- **Backup hooks execute arbitrary commands inside application Pods with that Pod's own privileges** — a `pre.hook.backup.velero.io/command` annotation is effectively a remote-exec vector; restrict who can annotate Pods in sensitive namespaces via RBAC on `pods/annotate` or a validating admission policy.
- **Cross-cluster restores, shown above, move Secrets and ConfigMaps between clusters verbatim** — confirm the target cluster's trust boundary and network policies are appropriate for the workload before restoring, since a restore is functionally a bulk clone of sensitive configuration into a new environment.

## 8. Common Troubleshooting Scenarios

| Symptom                                                             | Cause                                                                                           | Fix                                                                                                                                                                       |
| ------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `velero backup describe` shows `Phase: PartiallyFailed`             | Some resources or volume snapshots failed (e.g. a PVC with no matching snapshot class)          | Check `velero backup logs <name>` for the specific resource/volume error and address it directly                                                                          |
| Restore fails with API-not-found for a resource type                | Backup was taken on an older cluster with an API version now removed on the target              | Check API deprecation timeline ([§111](./Section-111-Part14-Version-Skew-Policy-Deprecation-Handling.md)) before restoring across minor versions; migrate manifests first |
| Backup silently never uploads, storage location shows `Unavailable` | Expired/incorrect cloud credentials in the Velero secret, or bucket access misconfigured        | Rotate/correct the credentials secret and re-run `velero backup-location get` to confirm `Available`                                                                      |
| Restored Pod stuck Pending, PVC never binds                         | Volume snapshot restore didn't complete, or storage class on target cluster differs from source | Confirm `VolumeSnapshotLocation` matches target cluster's storage backend; check `StorageClass` compatibility                                                             |
| Scheduled backups stop appearing after a while                      | Retention TTL and bucket lifecycle policy conflict, or Velero server Pod itself crash-looping   | Check `kubectl get pods -n velero` for server health first, then reconcile TTL vs. bucket lifecycle                                                                       |

## 9. Best Practices

- Treat Velero as the complement to etcd backup ([§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)), not a replacement — back up etcd for control-plane state and Velero for the combined object-graph-plus-volume-data picture, and document which recovery scenario each one addresses.
- Actually exercise restores on a non-production cluster on a regular cadence — an untested backup is an unverified assumption about recovery capability, not a real safety net.
- Use pre/post backup hooks for any stateful application where crash-consistent (rather than application-consistent) snapshots are unacceptable, such as relational databases mid-transaction.
- Keep backup retention (`--ttl`) and object-storage bucket lifecycle policies explicitly synchronized, reviewed together whenever either is changed.

## 10. Common Anti-Patterns / Mistakes

- **Assuming an etcd snapshot ([§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)) alone constitutes a full cluster backup**, missing that it contains no PersistentVolume data whatsoever — a real production incident then discovers stateful workloads are unrecoverable exactly when it matters most.
- **Scheduling backups and never testing a restore**, leaving an organization's actual RTO/RPO an assumption rather than a demonstrated, measured capability.
- **Granting broad object-storage credentials to Velero without treating the resulting bucket as a Secrets-equivalent asset**, overlooking that a full-namespace backup contains every Secret in that namespace.

## 11. Interview Questions

**🎯 Beginner:** _"What does Velero back up that an etcd snapshot doesn't?"_
**Model answer:** An etcd snapshot captures the Kubernetes API object state — specs, metadata, RBAC bindings — but etcd never stores the actual data sitting inside PersistentVolumes; it only stores the PVC objects that reference them. Velero backs up both halves together: it serializes the selected API objects to object storage (like S3) and simultaneously triggers a volume snapshot of every PersistentVolume those objects reference. Restoring from an etcd snapshot alone would recreate a Deployment and its PVC, but the PV would either be empty or fail to bind — Velero is what makes a stateful application's actual data recoverable, not just its Kubernetes-level definition.
_What the interviewer is probing for:_ Clear understanding that etcd and Velero cover genuinely different, complementary scopes rather than being interchangeable backup tools.

**🎯 Intermediate:** _"How would you back up a production namespace running a PostgreSQL StatefulSet, and why would a plain volume snapshot alone be risky?"_
**Model answer:** I'd use Velero with a pre-backup hook annotation on the PostgreSQL Pod that runs `pg_dump` (or a similar consistent-checkpoint command) before Velero triggers the volume snapshot. Without that hook, Velero would snapshot the PV whenever the schedule fires, potentially catching the database mid-write — a crash-consistent snapshot, meaning it looks like the database was hard-powered-off at that instant. PostgreSQL's write-ahead log usually makes that recoverable, but it's a materially riskier restore than one taken immediately after a clean logical dump. The pre-hook ensures the data is quiesced to a known-good state before the snapshot happens, so the restore path is a known-consistent recovery rather than relying on crash-recovery logic working correctly.
_What the interviewer is probing for:_ Practical awareness of application-consistent versus crash-consistent snapshots, and hands-on familiarity with Velero's hook mechanism, not just the backup command syntax.

**🎯 Senior:** _"Design a Velero backup strategy for a multi-namespace, multi-team cluster, balancing storage cost, RTO, and blast-radius isolation."_
**Model answer:** I'd avoid one cluster-wide backup as the only strategy, since restoring a single giant backup to recover one team's accidentally-deleted namespace is both slow and unnecessarily broad in blast radius. Instead, I'd run namespace- or label-selector-scoped Schedules per team or per criticality tier — a tight, frequent schedule (e.g. every 4 hours, 7-day TTL) for stateful, high-change namespaces, and a lighter nightly schedule for mostly-static namespaces — each with its own `BackupStorageLocation` prefix so teams can restore independently without touching each other's data. I'd size retention against actual RPO requirements per tier rather than one blanket TTL, and I'd separately track object-storage cost against that retention, since indefinite retention of frequent snapshots compounds quickly. Backup hooks would be mandatory for any StatefulSet running a database, and I'd validate restore procedures quarterly on an isolated test cluster per critical namespace, treating an unverified restore path as equivalent to having no backup at all.
_What the interviewer is probing for:_ Ability to design tiered, scoped backup strategy rather than a single uniform policy, balancing cost, RTO/RPO, and blast-radius isolation across a real multi-tenant environment.

**🎯 Architect:** _"How does Velero fit into an organization-wide disaster recovery plan spanning multiple clusters and regions?"_
**Model answer:** Velero is one layer of a larger DR strategy that must also address control-plane recovery (etcd, [§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)), infrastructure provisioning (how a replacement cluster gets stood up at all — Terraform/kubeadm automation), and application-level recovery ordering (which namespaces restore first, and in what dependency order). I'd configure Velero's `BackupStorageLocation` to point at a bucket replicated across regions independently of the source cluster's region, so a full regional outage doesn't take the backups down with the cluster they protect. I'd maintain the restore procedure as a tested, documented runbook — not tribal knowledge — including exact namespace-mapping flags for standing up a restored environment under a different cluster name or region, and exact ordering for namespaces with cross-namespace dependencies (e.g. a shared ingress-controller namespace restored before application namespaces that depend on it). Critically, I'd treat the whole pipeline as something to validate on a real schedule via game-day exercises: actually destroying a test cluster and timing the full recovery against the organization's stated RTO, feeding any gap discovered back into either the backup frequency, the automation tooling, or the runbook itself. This full picture — etcd for control-plane, Velero for object-plus-volume state, tested automation for infrastructure, and a rehearsed runbook tying it together — is exactly what [§112](./Section-112-Part14-Disaster-Recovery-Planning-Kubernetes-Clusters.md)'s disaster recovery planning formalizes.
_What the interviewer is probing for:_ Systems-level thinking about DR as a multi-layered, rehearsed capability rather than a single tool or backup job, and awareness that Velero is necessary but not sufficient on its own.

## 12. Common Misconceptions

1. **"Velero and etcd backup are redundant with each other."** They cover different scopes — etcd holds API object state, Velero backs up both API object state and PersistentVolume data together — and neither substitutes fully for the other in a real recovery scenario.
2. **"A volume snapshot is always application-consistent by default."** Without a pre-backup hook to quiesce the application first, a snapshot is only crash-consistent, which is a materially riskier restore starting point for databases and other stateful workloads.
3. **"Scheduling backups is sufficient disaster-recovery preparation."** A backup that has never been restored is an unverified assumption; only an actual, periodically-tested restore confirms the recovery path genuinely works within the required time window.
4. **"Velero's object storage credentials are a minor operational detail."** A full backup contains every Secret in the backed-up namespaces, making those storage credentials effectively equivalent in sensitivity to cluster-wide Secret read access.

## 13. 🔑 Key Takeaways

- Velero backs up Kubernetes API object state and PersistentVolume data together as one coordinated operation — the missing half of what an etcd snapshot ([§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)) alone provides.
- Pre/post backup hooks make volume snapshots application-consistent rather than merely crash-consistent, which matters materially for stateful workloads like databases.
- Scheduled backups (`Schedule` objects) automate recurring backups with retention (`ttl`), but retention must stay synchronized with the underlying object-storage bucket's own lifecycle policy.
- Cross-cluster restores are a real migration and disaster-recovery mechanism, but restoring across a Kubernetes version boundary can hit removed API versions — a direct link to [§111](./Section-111-Part14-Version-Skew-Policy-Deprecation-Handling.md)'s version-skew and deprecation concerns.
- An untested restore path is an unverified assumption about recovery capability; only periodic, actual restore exercises confirm a real RTO/RPO is achievable.

## 14. Related Concepts & What's Next

This section extended [§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)'s etcd backup coverage into the full-cluster picture, adding PersistentVolume data backup via Velero's coordinated object-storage-plus-volume-snapshot model, backup hooks for application consistency, and scheduled/cross-cluster restore workflows. The next section addresses a concern that surfaces directly from the cross-cluster restore scenario above — restoring (or upgrading) across Kubernetes versions requires understanding exactly which API versions and skew combinations are supported, which is the subject of [§111](./Section-111-Part14-Version-Skew-Policy-Deprecation-Handling.md).

**Next Section:** [§111](./Section-111-Part14-Version-Skew-Policy-Deprecation-Handling.md) — `Section-111-Part14-Version-Skew-Policy-Deprecation-Handling.md`
