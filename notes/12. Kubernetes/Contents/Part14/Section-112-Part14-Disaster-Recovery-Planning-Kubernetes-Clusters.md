# Section 112 (Part 14): Disaster Recovery Planning for Kubernetes Clusters

## 1. Definition

**Plain language:** Everything Part 14 has covered so far — upgrading safely, backing up etcd, draining nodes, rotating certificates, backing up workloads and volumes, and respecting version skew — are individually necessary skills, but none of them by itself is a disaster recovery plan. A real DR plan is what ties all of them together into a rehearsed, documented, timed procedure that answers a much harder question than any single tool does: when something actually goes catastrophically wrong, exactly what do we do, in what order, and how do we know it will actually work within the time we have?

**Precise definition:** **Disaster recovery (DR) planning** for a Kubernetes cluster is the practice of defining, documenting, and periodically rehearsing a complete recovery procedure that restores cluster and workload functionality after a catastrophic event — total etcd loss, control-plane node destruction, an entire region outage, or accidental mass deletion — bounded by two explicit targets: **Recovery Point Objective (RPO)**, the maximum acceptable amount of data loss measured in time (how old can the most recent usable backup be), and **Recovery Time Objective (RTO)**, the maximum acceptable time to restore full service. A complete plan specifies exactly which backup source restores which layer of the system (etcd snapshots for cluster/API state, per §107; Velero for workload objects and PersistentVolume data, per §110), the precise ordering of recovery steps (infrastructure provisioning, control-plane re-establishment, certificate/PKI trust re-establishment per §109, then workload restore), the version-compatibility checks required before any restore is trusted (§111), and a recurring **game-day exercise** cadence that actually performs the recovery against a disposable environment to measure whether the stated RTO/RPO is real or merely assumed.

## 2. Why This Matters

- **A disaster recovery plan that has never been rehearsed is not a plan — it's an unverified assumption**, and every section from §107 through §111 independently makes this exact point about its own backup mechanism; the capstone insight is that the assumption compounds when several unverified layers are stacked together and expected to work in combination during an actual incident.
- **RTO and RPO are business decisions, not purely technical ones** — the technical building blocks (§107's etcd snapshots, §110's Velero backups) can support almost any RPO/RTO target given enough investment, but a DR plan that never explicitly states and tests these numbers leaves an organization with no way to know whether its actual recovery capability matches what stakeholders assume it is.
- **This is where CKA/CKS exam knowledge becomes real operational judgment** — the exam tests etcd restore, drain, and certificate renewal as isolated skills, but a real incident requires knowing the correct _order_ to apply them and the _dependencies_ between them, which only a synthesized, rehearsed plan makes reliable under pressure.

🔑 **Key Takeaway:** A Kubernetes disaster recovery plan is the ordered, rehearsed synthesis of etcd backup/restore (§107), node maintenance discipline (§108), certificate/PKI re-establishment (§109), workload-and-volume backup via Velero (§110), and version-skew-aware restore validation (§111) — bounded by explicit RTO/RPO targets and proven, not merely assumed, via recurring game-day exercises.

## 3. Prerequisites and Dependencies

This capstone section directly synthesizes every prior section of Part 14: §106 (Cluster Upgrades), §107 (etcd Backup and Restore), §108 (Node Maintenance), §109 (Certificate Rotation and Renewal), §110 (Cluster Backup Strategies, Velero), and §111 (Version Skew Policy and Deprecation Handling). It assumes working familiarity with all of them individually — this section's job is ordering and integrating them, not reintroducing their mechanics. Forward-references §113 (Part 15's CKS curriculum overview), since a mature DR plan's security posture (encrypted backups, restricted restore credentials, hardened rebuild images) connects directly into the CKS security-hardening material that follows.

## 4. Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│              KUBERNETES DISASTER RECOVERY: LAYERED RECOVERY MODEL           │
│                                                                             │
│  LAYER 1: INFRASTRUCTURE                                                    │
│  ─────────────────────────────────────────────────────────────────────      │
│  Provision replacement nodes/VMs (Terraform, cloud automation)              │
│  -> nothing above this layer is possible without compute existing first     │
│                          │                                                  │
│                          ▼                                                  │
│  LAYER 2: CONTROL PLANE + ETCD                                              │
│  ─────────────────────────────────────────────────────────────────────      │
│  kubeadm init / re-join control-plane nodes                                 │
│  etcdctl snapshot restore  (§107)  -> reconstructs cluster API state        │
│  Re-establish PKI/CA + certificates (§109) so components trust each other   │
│                          │                                                  │
│                          ▼                                                  │
│  LAYER 3: VERSION COMPATIBILITY CHECK                                       │
│  ─────────────────────────────────────────────────────────────────────      │
│  Confirm rebuilt cluster's version vs. backup's original version (§111)     │
│  -> identify any deprecated/removed API versions BEFORE restoring workloads │
│                          │                                                  │
│                          ▼                                                  │
│  LAYER 4: WORKLOAD + DATA RESTORE                                           │
│  ─────────────────────────────────────────────────────────────────────      │
│  velero restore create --from-backup <name>  (§110)                         │
│  -> recreates Deployments/Services/ConfigMaps/Secrets                       │
│  -> provisions new PVs from volume snapshots                                │
│  kubectl convert for any resources hitting removed API versions (§111)      │
│                          │                                                  │
│                          ▼                                                  │
│  LAYER 5: VALIDATION                                                        │
│  ─────────────────────────────────────────────────────────────────────      │
│  etcdctl endpoint health / kubectl get nodes,pods --all-namespaces          │
│  Application-level health checks, traffic cutover                           │
│  -> declare RTO achieved (or not) against the clock started at failure      │
│                                                                             │
│  THROUGHOUT: node maintenance discipline (§108, cordon/drain/uncordon)      │
│  governs how partial-failure scenarios (single node lost, not full cluster) │
│  are handled without invoking the full layered rebuild above                │
└─────────────────────────────────────────────────────────────────────────────┘
```

- **The layers are strictly ordered and dependency-bound** — attempting Layer 4 (workload restore) before Layer 2 (control plane + etcd) is even up is not just inefficient, it's impossible, since Velero itself needs a functioning API server to talk to.
- **Layer 3's version check is the layer most often skipped under incident pressure**, and it's precisely what §111 formalized — skipping it doesn't prevent the problem, it just moves the API-not-found failure later, into the middle of Layer 4 instead of before it.
- **Not every incident requires all five layers** — a single node failure is handled entirely by §108's cordon/drain/replace discipline; the full layered rebuild is reserved for control-plane-level or full-cluster-level disasters.

## 5. Hands-On

### 5.1 Writing a Tiered DR Runbook with Explicit RTO/RPO Targets

**Purpose:** Convert the layered model above into a concrete, documented runbook with measurable targets, rather than leaving recovery to in-the-moment improvisation.

**Syntax (runbook structure, not a command):**

```yaml
# dr-runbook.yaml (illustrative structure - not a live Kubernetes manifest)
scenario: "Full control-plane loss, single-region cluster"
rpo_target: "15 minutes" # matches etcd snapshot cadence
rto_target: "45 minutes" # end-to-end, failure-to-validated-recovery
steps:
  - layer: infrastructure
    action: "Provision 3 replacement control-plane nodes via Terraform"
    owner: "platform-oncall"
    est_time: "10m"
  - layer: control-plane-etcd
    action: "kubeadm init on node-1; etcdctl snapshot restore from latest snapshot (§107)"
    owner: "platform-oncall"
    est_time: "10m"
  - layer: version-check
    action: "kubeadm certs check-expiration; confirm target kubeadm version matches snapshot's origin cluster within skew policy (§111)"
    owner: "platform-oncall"
    est_time: "5m"
  - layer: workload-restore
    action: "velero restore create --from-backup latest-nightly (§110); kubectl convert any failed resources"
    owner: "app-oncall"
    est_time: "15m"
  - layer: validation
    action: "etcdctl endpoint health; smoke-test critical Services; declare RTO met/missed"
    owner: "platform-oncall + app-oncall"
    est_time: "5m"
```

**Production usage example:** Assigning an explicit owner and estimated time to each layer, as shown above, turns a vague "we have backups" claim into a runbook that can actually be timed during a game-day exercise — if Layer 2 alone consistently takes 25 minutes instead of the estimated 10, that's a concrete signal the 45-minute RTO target needs either faster tooling (pre-provisioned standby infrastructure) or a renegotiated target with stakeholders, discovered safely in a drill rather than during a real incident.

**Common errors:** Writing an RTO/RPO target without ever validating it against an actual timed exercise — a runbook with numbers nobody has confirmed achievable is functionally indistinguishable from having no numbers at all, just with more false confidence attached.

### 5.2 Running a Game-Day Disaster Recovery Exercise

**Purpose:** Actually prove the runbook works, end-to-end, on a disposable environment — the single most important DR practice, since every prior section (§107, §110) independently emphasized that an untested backup is an unverified assumption.

**Syntax:**

```bash
# 1. Stand up a disposable cluster mirroring production's version and topology
kubeadm init --kubernetes-version=v1.31.0 ...

# 2. Deliberately destroy it (simulating the disaster)
sudo systemctl stop kubelet
sudo mv /var/lib/etcd /var/lib/etcd-destroyed-for-drill

# 3. Execute the runbook exactly as written, starting a timer at step 1
etcdctl snapshot restore /backup/latest-snapshot.db --data-dir=/var/lib/etcd-restored ...
velero restore create --from-backup latest-nightly

# 4. Validate and record actual elapsed time against the RTO target
kubectl get nodes
kubectl get pods --all-namespaces
echo "Drill completed in: $(( $(date +%s) - $START_TIME )) seconds"
```

**Production usage example:** A quarterly game day that deliberately destroys a staging cluster's etcd and control plane, then executes the DR runbook against a stopwatch, is what actually confirms a 45-minute RTO target is real — organizations that skip this step routinely discover during a genuine incident that a step assumed to take 5 minutes (e.g., locating the correct, current snapshot file) actually takes 30, because nobody had exercised the retrieval path before.

**Common errors:** Running the drill against an environment that doesn't match production's Kubernetes version or topology — a game day performed on a single-node kind cluster does not surface the multi-member etcd coordination complexity (§107) or version-skew issues (§111) that a real production-scale restore will actually encounter.

### 5.3 Post-Incident Review and Runbook Refinement

**Purpose:** Close the loop after either a real incident or a game-day drill, feeding discovered gaps back into the runbook rather than treating the exercise as a one-time checkbox.

```bash
# Example: a real gap found during a drill - snapshot retrieval script assumed
# a specific S3 bucket path structure that changed after a storage migration
$ aws s3 ls s3://cluster-backups/etcd/ --recursive | tail -5
# (discovers the retrieval script's hardcoded prefix is stale)
```

**Production usage example:** After a drill reveals the snapshot-retrieval step took 20 minutes instead of an assumed 2 (due to a stale hardcoded S3 prefix in the retrieval script, as above), the runbook is updated, the script is fixed, and the next drill is scheduled to confirm the fix actually closed the gap — this iterative loop, not the original runbook draft, is what makes a DR plan trustworthy over time as infrastructure and tooling around it inevitably changes.

**Common errors:** Treating a single successful game day as permanent proof the plan works — infrastructure, backup tooling, and cluster versions all drift over time (§111), so a DR plan validated once and never re-tested degrades back into an unverified assumption within a surprisingly short window.

## 6. Production Usage Notes

- **RTO/RPO targets should be set per-workload-tier, not as one blanket number for the whole cluster** — a payments-critical namespace might justify a 15-minute RPO via frequent Velero schedules (§110) plus rapid etcd snapshotting (§107), while a low-criticality internal tool can tolerate a much longer window at lower operational cost.
- **Pre-provisioned standby infrastructure (warm or hot standby control-plane capacity) meaningfully shrinks Layer 1's time cost** at the expense of ongoing infrastructure spend — this tradeoff should be an explicit, stakeholder-visible decision, not an unstated assumption baked into an RTO number.
- **The runbook itself should live as version-controlled documentation, reviewed on the same cadence as the game-day exercises**, so it evolves alongside the actual cluster topology, backup tooling, and Kubernetes version rather than silently going stale.

## 7. Security Considerations

- **A DR plan that restores from backups without validating their integrity or provenance re-introduces every security risk those backups carry** — etcd snapshots and Velero backups both contain plaintext Secrets absent encryption at rest (§107, §110), so restore automation credentials deserve exactly the same access rigor as production Secret access.
- **Disaster recovery drills and real incidents are both high-privilege operations** — provisioning infrastructure, restoring etcd, and running `velero restore create` all require broad permissions, so access to trigger DR procedures should be tightly scoped via RBAC and audited, not available to the entire on-call rotation by default.
- **A rebuilt cluster's PKI trust (§109) must be re-established deliberately, not assumed to carry over** — restoring workload state onto a control plane with a different or improperly initialized CA can create subtle trust mismatches that don't fail loudly, unlike a version-skew API error; validating certificate and CA state is as much a part of DR validation as checking `kubectl get pods`.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                  | Cause                                                                                         | Fix                                                                                                                                 |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| Recovery takes far longer than the documented RTO during a real incident | Runbook was never timed via a game-day exercise, so estimates were guesses, not measurements  | Run (and repeat) game-day drills against production-representative environments to get real, trusted time estimates                 |
| Workload restore (Layer 4) fails with API-not-found errors               | Version compatibility check (Layer 3 / §111) was skipped under incident pressure              | Always perform the version-skew/deprecation check before restoring workloads, even during a real, time-pressured incident           |
| Restored cluster's components fail to trust each other after rebuild     | PKI/CA (§109) wasn't re-established correctly, or an old CA was reused inconsistently         | Explicitly validate certificate/CA state as part of Layer 2, not just etcd health                                                   |
| Game-day drill "succeeds" but real incident still goes badly             | Drill environment didn't match production's scale, version, or topology                       | Rebuild the drill to mirror production as closely as feasible — same Kubernetes version, similar etcd topology, similar data volume |
| Runbook steps reference tools/paths that no longer exist                 | Runbook wasn't kept in sync with infrastructure and tooling drift since it was last exercised | Review and re-validate the runbook on the same recurring cadence as the game-day exercises themselves                               |

## 9. Best Practices

- Define explicit, per-workload-tier RTO and RPO targets, and treat them as unproven until confirmed by an actual timed game-day exercise, not as soon as they're written down.
- Maintain the DR runbook as version-controlled documentation covering every layer — infrastructure, control-plane/etcd (§107), PKI (§109), version compatibility (§111), and workload/volume restore (§110) — in explicit dependency order.
- Run game-day exercises on a recurring schedule against production-representative environments, and feed every discovered gap back into both the runbook and the underlying tooling.
- Scope and audit DR-triggering permissions tightly via RBAC, since both real incidents and drills involve broad, high-privilege operations across infrastructure, etcd, and workload state.

## 10. Common Anti-Patterns / Mistakes

- **Treating individual backup mechanisms (etcd snapshots, Velero) as a complete DR plan on their own**, missing that a real recovery requires correctly ordering and integrating several layers, not just possessing the raw backup files.
- **Setting RTO/RPO numbers that have never been validated by an actual timed exercise**, leaving stakeholders with false confidence in a recovery capability that may not exist in practice.
- **Running a single game-day exercise once and considering the plan permanently proven**, ignoring that infrastructure, tooling, and cluster versions (§111) all drift, silently invalidating an unrefreshed runbook over time.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between having an etcd backup and having a disaster recovery plan?"_
**Model answer:** An etcd backup is one specific piece of technical capability — a point-in-time snapshot of cluster API state (§107). A disaster recovery plan is the full, ordered procedure that uses that backup (and others, like Velero for workload and volume data, §110) alongside infrastructure provisioning, PKI re-establishment (§109), and version compatibility checks (§111) to actually bring a cluster back to working order within a defined time target. Having the backup file is necessary but not sufficient — without a documented, rehearsed procedure for using it correctly and in the right order, the backup alone doesn't guarantee a successful recovery.
_What the interviewer is probing for:_ Understanding that DR is a synthesized process, not a single artifact or tool.

**🎯 Intermediate:** _"Your team has etcd snapshots and Velero backups, both taken nightly, but has never tested a full recovery. What's your first recommendation and why?"_
**Model answer:** Run an actual game-day exercise — stand up a disposable cluster matching production's version and topology, deliberately simulate the disaster (destroy etcd, stop the control plane), and execute the full recovery procedure against a timer using the real backup files. Both §107 and §110 make the same point independently: an untested backup is an unverified assumption, not a proven recovery path. Without having actually exercised the restore, the team has no real evidence their RPO or RTO expectations are achievable — they might discover, for instance, that the etcd restore works fine but the Velero restore hits removed API versions (§111) because the backup is from an older cluster version, a gap that only surfaces by actually trying the full sequence end-to-end.
_What the interviewer is probing for:_ Prioritizing verification over simply having more backups, and recognizing that integration between backup mechanisms is where untested gaps usually hide.

**🎯 Senior:** _"Design a disaster recovery plan for a production Kubernetes cluster running several tiers of workloads with different criticality levels."_
**Model answer:** I'd start by defining separate RTO/RPO targets per workload tier rather than one cluster-wide number — a payments-critical namespace might need a 15-minute RPO backed by frequent Velero schedules and closely-spaced etcd snapshots, while a lower-criticality internal tool can tolerate hours. I'd document the full layered recovery procedure explicitly: infrastructure provisioning, etcd restore (§107) and PKI re-establishment (§109) to rebuild the control plane, a mandatory version-skew/deprecation check (§111) before touching workload state, then Velero-driven workload and volume restore (§110), followed by explicit validation steps before declaring the incident resolved. Each layer would have an owner and a time estimate, refined by actual measurement rather than guesswork. Critically, I'd schedule recurring game-day exercises — at minimum quarterly — against an environment mirroring production's version and scale, treating any gap discovered (stale scripts, wrong assumptions about backup location, unexpectedly long steps) as required runbook and tooling fixes, not just findings to note and forget. I'd also make sure DR-triggering access is scoped and audited via RBAC, since the procedure itself involves broad, high-privilege actions across infrastructure and cluster state.
_What the interviewer is probing for:_ Ability to design a tiered, ordered, measured DR strategy that integrates every underlying mechanism rather than treating backup tools as independently sufficient.

**🎯 Architect:** _"How would you evolve a single-cluster disaster recovery plan into an organization-wide DR capability spanning many clusters, regions, and teams?"_
**Model answer:** I'd standardize the layered recovery model — infrastructure, control-plane/etcd, PKI, version-compatibility validation, workload/volume restore, validation — as a reusable template rather than letting each team or cluster invent its own ad hoc procedure, since the mechanics (§107 through §111) are the same regardless of which specific cluster is being recovered. I'd centralize backup storage across regions independently of any single cluster's own region, so a full regional outage doesn't take out the backups meant to protect against exactly that scenario. I'd build a fleet-wide dashboard tracking each cluster's last-validated RTO/RPO (from its most recent game-day result), not just its most recent backup timestamp, since a stale, unvalidated drill result is functionally the same risk as a stale backup. I'd mandate a recurring game-day cadence enforced organizationally, not left to individual team discipline, with post-incident (and post-drill) reviews feeding a shared runbook template that improves for every cluster at once rather than each team rediscovering the same gaps independently. Finally, I'd treat this whole DR capability as itself needing security hardening — restricted, audited access to backup stores and restore automation, and encrypted backups by default — which is exactly the bridge into the CKS-focused hardening material that follows in §113 and the rest of Part 15.
_What the interviewer is probing for:_ Systems-level thinking about DR as an organizational capability with shared tooling and measured, tracked reliability — not a per-cluster manual exercise — plus recognition of where DR planning connects to broader security posture.

## 12. Common Misconceptions

1. **"Having recent backups is the same as having a disaster recovery plan."** Backups are one necessary input; a real plan requires the ordered, integrated, rehearsed procedure that turns those backups into an actual restored, functioning cluster within a defined time window.
2. **"RTO and RPO are purely technical metrics set by the platform team."** They're business decisions about acceptable data loss and downtime that should be made with stakeholder input, then validated technically — not numbers invented unilaterally and never confirmed achievable.
3. **"A disaster recovery plan, once validated, stays valid indefinitely."** Infrastructure, tooling, and Kubernetes versions all drift over time (§111); a runbook validated once and never re-tested degrades back into an unverified assumption.
4. **"Skipping the version-compatibility check during a real incident is acceptable because time is critical."** Skipping it doesn't save time — it just relocates the failure from a quick upfront check (§111) into the middle of a workload restore already under way, costing more time overall to diagnose and fix.

## 13. 🔑 Key Takeaways

- A disaster recovery plan is the ordered, rehearsed synthesis of etcd backup/restore (§107), node maintenance (§108), certificate/PKI re-establishment (§109), Velero-based workload and volume backup (§110), and version-skew-aware restore validation (§111) — not any single backup mechanism alone.
- RTO and RPO are explicit, stakeholder-relevant targets that must be confirmed by actual timed game-day exercises, not assumed correct because a runbook exists on paper.
- Recovery layers are strictly ordered and dependency-bound: infrastructure, then control-plane/etcd, then version compatibility checks, then workload/volume restore, then validation — skipping or reordering steps (especially the version check) causes failures later rather than preventing them.
- Game-day exercises must be recurring, not one-time, and must run against production-representative environments to surface real gaps rather than false confidence.
- DR-triggering access deserves the same RBAC rigor and audit trail as any other high-privilege cluster operation, since both real incidents and drills involve broad infrastructure, etcd, and workload-level actions.

## 14. Related Concepts & What's Next

This capstone section synthesized every prior section of Part 14 — §106's upgrade procedures, §107's etcd backup/restore, §108's node maintenance discipline, §109's certificate rotation, §110's Velero-based workload and volume backup, and §111's version-skew and deprecation handling — into one ordered, rehearsed disaster recovery framework bounded by explicit RTO/RPO targets and proven only through recurring game-day exercises. With Part 14's operational lifecycle and disaster recovery foundation complete, Part 15 shifts focus to the CKS security curriculum, beginning with cluster setup hardening, CIS Benchmarks, and `kube-bench` — since a mature DR capability's own security posture (encrypted backups, restricted restore credentials, hardened rebuild automation) is itself a direct application of the hardening discipline that follows.

**Next Section:** §113 — `Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md`
