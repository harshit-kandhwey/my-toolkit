# Section 107 (Part 14): etcd Backup and Restore Procedures

## 1. Definition

**Plain language:** Every Deployment, Secret, ConfigMap, and Namespace a cluster has ever been told to run lives inside etcd (§10). If etcd is lost with no backup, that knowledge is gone — even if every node and container is still physically running, the cluster no longer remembers what it's supposed to look like. Backing up etcd, and knowing exactly how to restore it, is the real disaster-recovery plan for an entire Kubernetes cluster.

**Precise definition:** An **etcd backup** is a point-in-time **snapshot** of etcd's entire data store, taken with `etcdctl snapshot save` against a live etcd member, producing a single portable `.db` file that captures every key-value pair etcd holds at that moment. **Restore** is the reverse operation, `etcdctl snapshot restore`, which reconstructs a fresh etcd data directory from that snapshot file — a destructive, offline operation that requires stopping the existing etcd static Pod, replacing its data directory, and restarting it, since restore always creates a **new** etcd cluster from the snapshot rather than rejoining an existing one.

## 2. Why This Matters

- **etcd backup is the highest-priority operational responsibility for any self-managed cluster** — this is the section §10 explicitly promised: understanding etcd's data model there is the prerequisite for understanding exactly what a snapshot captures and why restoring it correctly reconstructs cluster state.
- **Restore is fundamentally different from a normal etcd restart** — it doesn't rejoin the existing Raft cluster; it creates a new one from the snapshot's contents, which has direct consequences for cluster membership, node IPs, and multi-member etcd topologies that must be handled deliberately, not assumed away.
- **This is one of the single most heavily tested CKA scenarios** — "back up etcd, then restore it" appears in the exam's Cluster Architecture, Installation & Configuration domain precisely because it's both operationally critical and easy to get subtly wrong under time pressure.

🔑 **Key Takeaway:** `etcdctl snapshot save` captures a portable point-in-time copy of all cluster state; `etcdctl snapshot restore` rebuilds a fresh etcd data directory from that file (never rejoining the old cluster) — the kubelet must then be pointed at that new data directory via the static Pod manifest, and the entire control plane briefly restarts as a consequence.

## 3. Prerequisites and Dependencies

Builds directly on §10 (etcd Deep Dive — the data model, Raft consensus, and quorum mechanics that this section's backup/restore procedures operate on) and §17 (Part 3, static Pods — etcd itself runs as a static Pod in a stacked topology, which is why restore requires manipulating its manifest and data directory directly rather than using `kubectl`). §106 covers cluster upgrades, which should always be preceded by a fresh snapshot using the procedure here.

## 4. Architecture Diagram

```text
   ETCD BACKUP (routine, non-disruptive, run on a schedule)
   ═══════════════════════════════════════════════════════
                                                    ┌────────────┐
   etcdctl snapshot save ──────► reads live etcd ──►│ backup.db  │──► copied off-node
                                  (no downtime)     └────────────┘    (S3, NFS, etc.)


   ETCD RESTORE (disruptive, deliberate DR action)
   ═══════════════════════════════════════════════════════

   STEP 1: Stop the control plane's view of etcd
   ─────────────────────────────────────────────────────────
     mv /etc/kubernetes/manifests/etcd.yaml /tmp/
       -> kubelet notices the static Pod manifest is gone,
          stops the etcd container
     (api-server also fails/stalls - it depends on etcd)

   STEP 2: Restore the snapshot into a NEW data directory
   ─────────────────────────────────────────────────────────
     etcdctl snapshot restore backup.db \
       --data-dir=/var/lib/etcd-restored \
       --name=<member-name> \
       --initial-cluster=<name>=https://<ip>:2380 \
       --initial-advertise-peer-urls=https://<ip>:2380
       -> creates a BRAND NEW etcd cluster's data directory,
          seeded with the snapshot's key-value contents

   STEP 3: Point etcd's static Pod manifest at the new directory
   ─────────────────────────────────────────────────────────
     edit etcd.yaml: hostPath -> /var/lib/etcd-restored
     mv etcd.yaml back into /etc/kubernetes/manifests/
       -> kubelet starts etcd again, now serving restored data

   STEP 4: Verify
   ─────────────────────────────────────────────────────────
     etcdctl endpoint health
     kubectl get nodes / kubectl get pods --all-namespaces
       -> control plane recovers, reflecting the snapshot's
          point-in-time state (anything written after the
          snapshot was taken is GONE)
```

- **Restore always produces a new cluster identity** — this is why `--initial-cluster`, `--name`, and `--initial-advertise-peer-urls` must be specified explicitly at restore time, mirroring the original cluster's topology rather than being inferred automatically.
- **Anything written to etcd after the snapshot was taken is permanently lost on restore** — restore is a point-in-time rollback, not a continuous replication mechanism.

## 5. Hands-On

### 5.1 Taking a Snapshot (`etcdctl snapshot save`)

**Purpose:** Capture the entire current state of the cluster into a single portable file, on a recurring schedule.

**Syntax:** `ETCDCTL_API=3 etcdctl snapshot save <path> --endpoints=<url> --cacert=<ca> --cert=<cert> --key=<key>`

```bash
$ ETCDCTL_API=3 etcdctl snapshot save /backup/etcd-snapshot-$(date +%Y%m%d-%H%M).db \
    --endpoints=https://127.0.0.1:2379 \
    --cacert=/etc/kubernetes/pki/etcd/ca.crt \
    --cert=/etc/kubernetes/pki/etcd/server.crt \
    --key=/etc/kubernetes/pki/etcd/server.key

{"level":"info","msg":"created temporary db file","path":"/backup/etcd-snapshot-20260731-0200.db.part"}
{"level":"info","msg":"fetched snapshot","took":"128ms"}
{"level":"info","msg":"saved","path":"/backup/etcd-snapshot-20260731-0200.db"}
Snapshot saved at /backup/etcd-snapshot-20260731-0200.db

# Always verify the snapshot immediately
$ ETCDCTL_API=3 etcdctl snapshot status /backup/etcd-snapshot-20260731-0200.db --write-out=table
+----------+----------+------------+------------+
|   HASH   | REVISION | TOTAL KEYS | TOTAL SIZE |
+----------+----------+------------+------------+
| a1b2c3d4 |    48213 |       1847 |     6.2 MB |
+----------+----------+------------+------------+
```

**Production usage example:** Snapshots taken with `snapshot save` are non-disruptive — they don't require stopping etcd or the control plane — which is why they're safely automatable via a cron job or CronJob-driven sidecar, copying the resulting `.db` file off-node (S3, NFS, another region entirely) immediately after each save, since a snapshot sitting on the same disk as the live etcd data provides no protection against a node or disk failure.

**Common errors:** Running `etcdctl snapshot save` without the correct `--cacert`/`--cert`/`--key` flags fails with a TLS handshake error — etcd's client endpoint requires mutual TLS by default in a kubeadm cluster (§8), and the correct certificate paths are always under `/etc/kubernetes/pki/etcd/`.

### 5.2 Restoring from a Snapshot (`etcdctl snapshot restore`)

**Purpose:** Reconstruct etcd's data from a previously taken snapshot — the actual disaster-recovery action, used when etcd data is lost or corrupted.

**Syntax:** `ETCDCTL_API=3 etcdctl snapshot restore <path> --data-dir=<new-dir> --name=<member> --initial-cluster=<...> --initial-advertise-peer-urls=<...>`

```bash
# STEP 1: Move the etcd static Pod manifest out so kubelet stops it
$ sudo mv /etc/kubernetes/manifests/etcd.yaml /tmp/etcd-backup-manifest.yaml

# STEP 2: Restore the snapshot into a fresh data directory
$ ETCDCTL_API=3 etcdctl snapshot restore /backup/etcd-snapshot-20260731-0200.db \
    --data-dir=/var/lib/etcd-restored \
    --name=etcd-1 \
    --initial-cluster=etcd-1=https://10.0.1.10:2380 \
    --initial-advertise-peer-urls=https://10.0.1.10:2380

2026-07-31 02:15:00 info snapshot restored from /backup/etcd-snapshot-20260731-0200.db

# STEP 3: Edit the manifest's hostPath to point at the restored directory,
# then move it back so kubelet restarts etcd
$ sudo sed -i 's|/var/lib/etcd|/var/lib/etcd-restored|' /tmp/etcd-backup-manifest.yaml
$ sudo mv /tmp/etcd-backup-manifest.yaml /etc/kubernetes/manifests/etcd.yaml

# STEP 4: Verify
$ ETCDCTL_API=3 etcdctl endpoint health --endpoints=https://127.0.0.1:2379 ...
https://127.0.0.1:2379 is healthy: successfully committed proposal: took = 15ms

$ kubectl get pods --all-namespaces
# Reflects state exactly as of the snapshot's timestamp
```

**Production usage example:** Restoring to a fresh `--data-dir` rather than overwriting the original in place is deliberate — it leaves the original (possibly corrupted) data directory intact for forensic inspection if the restore doesn't behave as expected, and makes rollback to "still broken but unmodified" trivial by simply pointing the manifest back at the original path.

**Common errors:** Forgetting to update `hostPath` in the etcd static Pod manifest after restoring to a new `--data-dir` causes kubelet to restart etcd against the old (still-broken) directory — the manifest edit in Step 3 is not optional, and is the step most commonly missed under exam time pressure.

### 5.3 Restoring in a Multi-Member (HA) etcd Topology

**Purpose:** Apply the same restore procedure correctly when etcd has 3 or 5 members instead of 1, since the `--initial-cluster` value must list every member for the new cluster to form correctly.

```bash
# Restore must be run identically on EVERY control-plane node,
# each with its own --name and matching --initial-cluster listing ALL members
$ ETCDCTL_API=3 etcdctl snapshot restore /backup/etcd-snapshot-20260731-0200.db \
    --data-dir=/var/lib/etcd-restored \
    --name=etcd-2 \
    --initial-cluster=etcd-1=https://10.0.1.10:2380,etcd-2=https://10.0.1.11:2380,etcd-3=https://10.0.1.12:2380 \
    --initial-advertise-peer-urls=https://10.0.1.11:2380
```

**Production usage example:** All members must be restored from the exact same snapshot file and brought up together — restoring only a subset of members from a snapshot while others still run old data produces a split, inconsistent cluster, which is why a full etcd HA restore is always coordinated as a single maintenance action across every control-plane node simultaneously, never rolled out node-by-node the way an upgrade is.

**Common errors:** Restoring only one member of a 3-member cluster and leaving the others running their pre-restore data results in a cluster that never re-establishes quorum correctly — every member must be restored from the same snapshot in the same coordinated operation.

## 6. Production Usage Notes

- **Automate `snapshot save` on a schedule (e.g., hourly or every few hours) via a cron job or CronJob-driven sidecar**, and always copy the resulting file off the control-plane node immediately — a snapshot that never leaves the node it was taken on provides zero protection against that node's own disk or hardware failure.
- **Test the restore procedure on a non-production cluster or in a lab periodically** — a backup that has never been restored is an unverified assumption, not a working disaster-recovery plan; §107's most common real-world failure mode is discovering restore doesn't work as expected during an actual outage.
- **Snapshot size and `snapshot status`'s reported key count are a useful early signal of etcd bloat** — a rapidly growing key count over time (often from excessive Event objects or unbounded custom resources) is worth investigating independently of backup hygiene.

## 7. Security Considerations

- **Snapshot files contain the entire cluster's data, including all Secrets** — if encryption at rest (§113, Part 15) isn't enabled, this means every Secret in plaintext; snapshot files must be encrypted at rest wherever they're stored and access-restricted exactly as strictly as the etcd data directory itself.
- **The TLS certificates used to authenticate `etcdctl` against etcd are themselves sensitive** (§18) — reusing the control plane's own `/etc/kubernetes/pki/etcd/` certificates for backup automation means that automation's credentials are as sensitive as direct etcd access.
- **Off-node backup storage (S3, NFS, etc.) needs its own access controls** — a snapshot file leaked from backup storage is equivalent to a full cluster data breach, not a lesser incident just because it didn't come from the live cluster.

## 8. Common Troubleshooting Scenarios

| Symptom                                                      | Cause                                                                                                               | Fix                                                                                                                      |
| ------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------ |
| `etcdctl snapshot save` fails with a TLS/cert error          | Missing or incorrect `--cacert`/`--cert`/`--key` flags                                                              | Use the correct paths under `/etc/kubernetes/pki/etcd/` (ca.crt, server.crt, server.key)                                 |
| After restore, `kubectl` commands still fail                 | etcd static Pod manifest still points at the old `hostPath`, or wasn't moved back into `/etc/kubernetes/manifests/` | Verify manifest's `hostPath` matches the new `--data-dir` and the file is back in the manifests directory                |
| Multi-member restore leaves etcd cluster unhealthy/no quorum | Not all members were restored from the same snapshot in the same coordinated action                                 | Restore every member simultaneously from the identical snapshot file, each with correct `--name`/`--initial-cluster`     |
| Restore "succeeds" but cluster state looks stale             | Snapshot was older than expected — restore is a point-in-time rollback, not incremental                             | Confirm snapshot timestamp/recency with `snapshot status` before restoring; anything written after snapshot time is lost |

## 9. Best Practices

- Automate `etcdctl snapshot save` on a recurring schedule and copy every snapshot off-node immediately, treating on-node-only backups as equivalent to no backup.
- Verify every snapshot with `etcdctl snapshot status` right after taking it, and periodically perform a full test restore in a non-production environment.
- Encrypt snapshot files at rest and restrict access to them as strictly as the etcd data directory itself, since they contain the same plaintext Secrets.

## 10. Common Anti-Patterns / Mistakes

- **Taking snapshots but never testing restore**, discovering procedural gaps only during an actual disaster when there's no time to fix them calmly.
- **Storing snapshots only on the same node (or disk) as the live etcd data**, which provides no protection against the exact failure — node or disk loss — a backup is meant to guard against.
- **Restoring only a subset of members in a multi-member etcd cluster**, leaving the cluster in an inconsistent, quorum-broken state instead of coordinating a full simultaneous restore.

## 11. Interview Questions

**🎯 Beginner:** _"What does `etcdctl snapshot save` actually capture, and why does it matter for a Kubernetes cluster?"_
**Model answer:** It captures a complete, point-in-time copy of everything stored in etcd — every Pod, Deployment, Secret, ConfigMap, and Namespace definition the cluster currently has, as a single portable file. It matters because etcd is the only place this state persists (§10); if etcd is lost with no snapshot, the cluster loses all memory of what it's supposed to be running, even if every node and container is still physically fine.
_What the interviewer is probing for:_ Understanding that this is a full cluster-state backup, not a minor operational detail.

**🎯 Intermediate:** _"After restoring an etcd snapshot, why do you have to edit the static Pod manifest's `hostPath` instead of just restarting etcd?"_
**Model answer:** `etcdctl snapshot restore` writes the reconstructed data into a brand new directory specified by `--data-dir` — it never touches or overwrites the original data directory in place. The etcd static Pod's manifest still points at the original `hostPath`, so if you just restart etcd without changing that, it comes back up reading the old (still broken or missing) data, not the restored snapshot. The manifest has to be edited to point at the new `--data-dir` before etcd is restarted, which is exactly why the etcd Pod manifest is temporarily moved out of `/etc/kubernetes/manifests/` during the process — to control precisely when and with what configuration it restarts.
_What the interviewer is probing for:_ Concrete understanding of the restore mechanics, not just memorized command syntax.

**🎯 Senior:** _"Your production cluster uses a 3-member stacked etcd topology. Walk through exactly how you'd restore from a snapshot after a catastrophic data corruption event, and what could go wrong."_
**Model answer:** I'd first confirm the snapshot's recency and integrity with `etcdctl snapshot status`, then coordinate restoring all three members simultaneously — moving each node's etcd static Pod manifest out of `/etc/kubernetes/manifests/`, running `etcdctl snapshot restore` on each with the identical snapshot file but each member's own `--name` and an `--initial-cluster` value listing all three members' correct peer URLs, then moving each manifest back in with `hostPath` updated to the new data directory. The main risk is restoring only some members while leaving others on old data, which produces a cluster that can't form quorum correctly — restore has to be treated as one atomic, coordinated action across all three nodes, not a rolling one-node-at-a-time process the way an upgrade would be. I'd also expect a brief control-plane outage window during this — api-server depends on etcd, so `kubectl` commands will fail until all three members are back and healthy — and I'd verify with `etcdctl endpoint health --cluster` before considering the restore complete.
_What the interviewer is probing for:_ Understanding that multi-member restore must be simultaneous and fully coordinated, unlike node-by-node procedures like upgrades, plus awareness of the control-plane outage window this implies.

**🎯 Architect:** _"How would you design an etcd backup strategy for a fleet of production kubeadm clusters, balancing recovery point objective (RPO), storage cost, and operational complexity?"_
**Model answer:** I'd automate `etcdctl snapshot save` on a schedule tuned to the acceptable RPO for each cluster's workload criticality — e.g., every 15-30 minutes for a high-change-rate production cluster, hourly for lower-churn clusters — rather than a single fixed cadence across the whole fleet. Every snapshot would be copied off-node immediately to durable, geographically separate storage (cross-region object storage), encrypted at rest, with lifecycle policies retaining a tiered set (recent snapshots at high frequency, older ones thinned out) to control storage cost without losing meaningful recovery points. I'd build automated snapshot verification (`snapshot status` plus a periodic actual test-restore into an isolated scratch environment) into the pipeline itself, since an unverified snapshot is functionally not a backup. Operationally, I'd document and rehearse the exact multi-member restore sequence as a runbook exercised on a real schedule (e.g., quarterly game days), because the complexity of coordinating a simultaneous multi-node restore under real incident pressure is exactly the kind of procedure that fails when it's only ever been read, not practiced. Finally, I'd pair this with the broader cluster backup strategy (§110, Velero) for workload-level and PV-level recovery, since an etcd snapshot alone doesn't capture persistent volume data.
_What the interviewer is probing for:_ Ability to reason about RPO/cost/complexity tradeoffs holistically, and recognition that etcd backup is necessary but not sufficient for full cluster disaster recovery.

## 12. Common Misconceptions

1. **"etcd backups are optional if the cluster's nodes and workloads are healthy."** etcd is the sole source of persisted cluster state (§10) — its loss is catastrophic regardless of current node/workload health, making backups mandatory, not optional insurance.
2. **"Restoring a snapshot just restarts etcd with the old data intact."** Restore builds a brand-new data directory and, functionally, a new cluster identity from the snapshot's contents — it does not rejoin or resume the previous Raft cluster.
3. **"You can restore just one member of a multi-member etcd cluster and the rest will catch up."** All members must be restored from the identical snapshot in one coordinated action; partial restores leave the cluster in a broken, quorum-inconsistent state.
4. **"A snapshot taken but never test-restored is a working backup."** An unverified snapshot is an assumption, not a proven recovery path — the only way to know restore actually works is to have exercised it.

## 13. 🔑 Key Takeaways

- `etcdctl snapshot save` takes a non-disruptive, point-in-time snapshot of all cluster state; `etcdctl snapshot restore` rebuilds a fresh data directory from it — always as a new cluster identity, never a rejoin.
- Restoring requires moving the etcd static Pod manifest out, restoring into a new `--data-dir`, updating the manifest's `hostPath` to match, then moving it back so kubelet restarts etcd against the restored data.
- Multi-member etcd restores must be coordinated simultaneously across every member from the identical snapshot — never rolled out one node at a time.
- Snapshot files contain the entire cluster's data including plaintext Secrets (absent encryption at rest) and must be protected and access-restricted accordingly.
- An untested backup is an unverified assumption — periodic real test-restores are what make a backup strategy actually trustworthy.

## 14. Related Concepts & What's Next

§10 covered etcd's data model and Raft quorum mechanics that this section's backup/restore procedures directly operate on. §17 (Part 3) covers the static Pod mechanism this section manipulates directly during restore. §106 covers cluster upgrades, which should always be preceded by a fresh, verified etcd snapshot using this section's procedure. §108 (next) covers node maintenance (cordon/drain/uncordon) — the next operational lifecycle skill after backup/restore.

**Next Section:** §108 — `Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md`
