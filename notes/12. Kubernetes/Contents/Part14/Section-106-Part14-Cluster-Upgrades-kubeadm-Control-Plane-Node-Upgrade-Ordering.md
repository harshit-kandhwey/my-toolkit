# Section 106 (Part 14): Cluster Upgrades with kubeadm (Control Plane and Node Upgrade Ordering)

## 1. Definition

**Plain language:** A Kubernetes cluster doesn't get upgraded all at once with a single switch flip. It gets upgraded one node at a time, in a specific order, using the same tool that built it in the first place — kubeadm re-runs a controlled version of its own bootstrap logic to move each node forward one minor version, while the rest of the cluster keeps serving traffic.

**Precise definition:** **`kubeadm upgrade`** is the subcommand family that moves an existing kubeadm-managed cluster from one Kubernetes minor or patch version to the next, following a strict ordering: the **first control-plane node** is upgraded via `kubeadm upgrade plan` (dry-run/preview) then `kubeadm upgrade apply` (executes), **additional control-plane nodes** follow with `kubeadm upgrade node`, and **worker nodes** are upgraded last, each preceded by a `cordon`/`drain` ([§108](./Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md)) to evacuate workloads safely. The `kubeadm`, `kubelet`, and `kubectl` binaries on each node are upgraded separately via the OS package manager, since `kubeadm upgrade` only orchestrates the cluster-side static Pod manifests and configuration — it does not replace its own binary.

## 2. Why This Matters

- **Kubernetes only supports upgrading one minor version at a time** (e.g., 1.29 → 1.30, never 1.29 → 1.31 directly) — skipping this rule is the single most common cause of failed or unsupported upgrade attempts, and getting the ordering right is a core CKA "Cluster Architecture, Installation & Configuration" exam skill.
- **Upgrade ordering exists to protect etcd and API availability throughout the process** — the first control-plane node's `kubeadm upgrade apply` is the only step that touches cluster-wide configuration (like the CoreDNS and kube-proxy versions); every other node's upgrade is comparatively mechanical once that first step succeeds.
- **This entire process directly reuses the bootstrap mental model from [§16](../Part3/Section-16-Part3-Kubeadm-Cluster-Bootstrapping-Step-By-Step.md)** — `kubeadm upgrade` regenerates static Pod manifests and certificates using the same machinery `kubeadm init` used originally, just pointed at a newer version instead of a first-time install.

🔑 **Key Takeaway:** Upgrade one minor version at a time, always upgrade the first control-plane node's `kubeadm` binary and run `kubeadm upgrade apply` before touching any other node, then work through remaining control-plane nodes with `kubeadm upgrade node`, and finish with worker nodes — draining each node before its `kubelet` is touched.

## 3. Prerequisites and Dependencies

Builds directly on [§16](../Part3/Section-16-Part3-Kubeadm-Cluster-Bootstrapping-Step-By-Step.md) (kubeadm bootstrapping — the same manifest-rendering and PKI machinery this section reuses) and [§15](../Part2/Section-15-Part2-High-Availability-Control-Plane-Architectures.md) (Part 2, HA control-plane topology — multi-control-plane ordering only matters when that topology is in play). [§108](./Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md) (node maintenance: cordon/drain/uncordon, next) covers the workload-evacuation step this section assumes before touching any node's kubelet. [§109](./Section-109-Part14-Certificate-Rotation-Renewal.md) covers certificate renewal, which `kubeadm upgrade` also triggers as a side effect.

## 4. Architecture Diagram

```text
   UPGRADE ORDER (one minor version at a time, e.g. v1.29.x -> v1.30.x)
   ══════════════════════════════════════════════════════════════════

   STEP 0: Plan
   ─────────────────────────────────────────────────────────
   On the FIRST control-plane node:
     apt-get update && apt-get install -y kubeadm=1.30.x-*
     kubeadm upgrade plan          <- dry-run, shows what will change

   STEP 1: First control-plane node (the only "apply" step)
   ─────────────────────────────────────────────────────────
     cordon + drain this node (§108)
     kubeadm upgrade apply v1.30.x
       - upgrades static Pod manifests (apiserver, scheduler,
         controller-manager, etcd if stacked)
       - renews near-expiry certificates (§109)
       - upgrades CoreDNS and kube-proxy config cluster-wide
     apt-get install -y kubelet=1.30.x-* kubectl=1.30.x-*
     systemctl daemon-reload && systemctl restart kubelet
     uncordon this node

   STEP 2: Every ADDITIONAL control-plane node (HA topology only)
   ─────────────────────────────────────────────────────────
     cordon + drain this node
     kubeadm upgrade node          <- NOT "apply" - just this node
     apt-get install -y kubelet=1.30.x-* kubectl=1.30.x-*
     systemctl daemon-reload && systemctl restart kubelet
     uncordon this node
     (repeat for each remaining control-plane node)

   STEP 3: Every WORKER node (one at a time, last)
   ─────────────────────────────────────────────────────────
     cordon + drain this node
     apt-get install -y kubeadm=1.30.x-*
     kubeadm upgrade node
     apt-get install -y kubelet=1.30.x-*
     systemctl daemon-reload && systemctl restart kubelet
     uncordon this node
     (repeat for each remaining worker node)

   RESULT: Cluster now fully at v1.30.x, upgraded with zero
           full-cluster downtime (individual node evacuation only)
```

- **`kubeadm upgrade apply` is run exactly once, on exactly one node** — every other control-plane node uses `kubeadm upgrade node`, which applies the already-decided cluster-wide configuration locally without re-deciding it.
- **Worker nodes never run `kubeadm upgrade apply`** — they only need `kubeadm upgrade node` (to update local kubelet configuration) since they hold no control-plane components.

## 5. Hands-On

### 5.1 Upgrading the First Control-Plane Node

**Purpose:** Move the cluster's control-plane configuration and the first node's binaries to the new version, establishing the version the rest of the cluster will follow.

**Syntax:** `kubeadm upgrade plan` then `kubeadm upgrade apply <version>`

```bash
# Check what versions are available and what will change
$ kubeadm upgrade plan
[upgrade/versions] Cluster version: v1.29.4
[upgrade/versions] kubeadm version: v1.30.2
Upgrade to the latest version:
COMPONENT                 CURRENT   TARGET
kube-apiserver             v1.29.4   v1.30.2
kube-controller-manager    v1.29.4   v1.30.2
kube-scheduler             v1.29.4   v1.30.2
kube-proxy                 v1.29.4   v1.30.2
CoreDNS                    v1.11.1   v1.11.3
etcd                       3.5.10    3.5.12

# Drain, then apply the upgrade
$ kubectl drain cp-node-1 --ignore-daemonsets
$ sudo kubeadm upgrade apply v1.30.2
[upgrade/successful] SUCCESS! Your cluster was upgraded to "v1.30.2"

# Upgrade the kubelet/kubectl binaries on THIS node, then restart
$ sudo apt-get install -y kubelet=1.30.2-* kubectl=1.30.2-*
$ sudo systemctl daemon-reload && sudo systemctl restart kubelet
$ kubectl uncordon cp-node-1
```

**Production usage example:** `kubeadm upgrade plan` never modifies anything — it's the mandatory pre-flight review step used to confirm the exact target version and check for any component-specific caveats printed in its output (deprecated API removals, etc.) before committing to `apply`, which is why skipping straight to `apply` without reviewing `plan`'s output first is discouraged even when the upgrade path seems obvious.

**Common errors:** Attempting to jump more than one minor version (e.g., 1.28 → 1.30 directly) fails during `kubeadm upgrade plan` with a version-skew error — Kubernetes' supported upgrade path is strictly one minor version at a time, requiring 1.28 → 1.29 → 1.30 as two separate upgrade cycles.

### 5.2 Upgrading Additional Control-Plane Nodes and Worker Nodes

**Purpose:** Propagate the already-decided cluster configuration to every remaining node without re-deciding it.

**Syntax:** `kubeadm upgrade node` (no version argument — it reads the already-upgraded cluster's target)

```bash
# On a SECOND control-plane node (HA topology)
$ kubectl drain cp-node-2 --ignore-daemonsets
$ sudo kubeadm upgrade node
[upgrade] Upgrading your Static Pod-hosted control plane instance
$ sudo apt-get install -y kubelet=1.30.2-* kubectl=1.30.2-*
$ sudo systemctl daemon-reload && sudo systemctl restart kubelet
$ kubectl uncordon cp-node-2

# On EACH worker node, one at a time
$ kubectl drain worker-1 --ignore-daemonsets --delete-emptydir-data
$ sudo apt-get install -y kubeadm=1.30.2-*
$ sudo kubeadm upgrade node
$ sudo apt-get install -y kubelet=1.30.2-*
$ sudo systemctl daemon-reload && sudo systemctl restart kubelet
$ kubectl uncordon worker-1
```

**Production usage example:** Upgrading worker nodes one at a time, fully draining and uncordoning each before starting the next, is what allows an entire cluster upgrade to proceed with zero scheduling downtime — the tradeoff is total upgrade wall-clock time, which scales linearly with node count, making this the correct place to reach for automation (Ansible playbooks, or rolling node-pool replacement on managed platforms) rather than manual per-node execution at scale.

**Common errors:** Forgetting to upgrade the `kubeadm` binary itself on a worker node before running `kubeadm upgrade node` causes the command to silently run the old logic — `kubeadm upgrade node` on a worker still needs `kubeadm` upgraded first via the package manager, since `kubeadm upgrade apply`/`node` never upgrades its own binary.

## 6. Production Usage Notes

- **Version skew policy allows the `kube-apiserver` to be up to two minor versions ahead of the `kubelet` and `kube-proxy` on any given node during the rolling upgrade window** — this is precisely why control-plane-first, worker-last ordering is safe: intermediate mixed-version states are explicitly supported, not merely tolerated.
- **`kubeadm upgrade apply` also handles certificate renewal as a side effect** if certificates are within 180 days of expiry, folding routine cert renewal ([§109](./Section-109-Part14-Certificate-Rotation-Renewal.md)) into the normal upgrade cadence rather than requiring a wholly separate maintenance window.
- **Always back up etcd ([§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)) immediately before starting a control-plane upgrade** — an upgrade is the single highest-risk moment for the control plane, and having a fresh, verified snapshot taken minutes before is the standard safety net if `kubeadm upgrade apply` fails midway.

## 7. Security Considerations

- **The upgraded `kubeadm`, `kubelet`, and `kubectl` binaries should come from the same trusted package repository used at initial bootstrap** — pinning to a specific, verified version (rather than "latest") avoids accidentally installing an untested or malicious package during a routine maintenance action.
- **`kubeadm upgrade apply`'s automatic certificate renewal is a security-positive side effect**, but operators relying on it as their sole cert-renewal mechanism should still track certificate expiry independently ([§109](./Section-109-Part14-Certificate-Rotation-Renewal.md)) — an upgrade schedule and a certificate's 1-year default validity window don't always align.
- **RBAC permissions used to run `kubeadm upgrade` and drain nodes are highly privileged** (effectively cluster-admin-equivalent) — the same credential-hygiene practices from [§18](../Part3/Section-18-Part3-Certificates-PKI-Kubeadm-Certificate-Management.md) apply to whoever or whatever automation executes cluster upgrades.

## 8. Common Troubleshooting Scenarios

| Symptom                                                   | Cause                                                              | Fix                                                                                                                                                                             |
| --------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kubeadm upgrade plan` errors with a version-skew message | Attempting to skip more than one minor version in a single upgrade | Upgrade one minor version at a time (e.g., 1.28 → 1.29, then 1.29 → 1.30 as separate cycles)                                                                                    |
| `kubeadm upgrade node` on a worker appears to do nothing  | `kubeadm` binary itself wasn't upgraded on that node first         | `apt-get install kubeadm=<target>-*` before running `kubeadm upgrade node`                                                                                                      |
| Pods get abruptly terminated during a node's upgrade      | Node's kubelet restarted without a prior `kubectl drain`           | Always cordon and drain ([§108](./Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md)) before touching kubelet on any node, upgrade or otherwise                      |
| `kubeadm upgrade apply` hangs waiting for control plane   | Static Pod manifest change failed to produce a healthy component   | Check kubelet logs and static Pod status (`crictl ps`) on that node; restore from etcd backup ([§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)) if unrecoverable |

## 9. Best Practices

- Always run `kubeadm upgrade plan` and read its full output before running `apply` — it surfaces deprecated API removals and component-specific caveats specific to that exact version jump.
- Take a fresh, verified etcd snapshot ([§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)) immediately before starting any control-plane upgrade, treating the upgrade window as the highest-risk moment for needing it.
- Upgrade and drain nodes one at a time, always in the order first-control-plane, remaining-control-plane, workers-last, never in parallel across control-plane nodes.

## 10. Common Anti-Patterns / Mistakes

- **Skipping more than one Kubernetes minor version in a single upgrade attempt**, which is unsupported and will surface confusing failures partway through rather than a clean upfront rejection in some cases.
- **Running `kubeadm upgrade apply` on more than one control-plane node**, when only the first node should ever use `apply` — every other control-plane node uses `kubeadm upgrade node`.
- **Upgrading kubelet without draining the node first**, causing running Pods to be abruptly disrupted instead of gracefully evacuated.

## 11. Interview Questions

**🎯 Beginner:** _"What is the difference between `kubeadm upgrade apply` and `kubeadm upgrade node`?"_
**Model answer:** `kubeadm upgrade apply <version>` is run exactly once, on the very first control-plane node — it's the command that actually decides and applies the new cluster-wide configuration (control-plane component versions, CoreDNS, kube-proxy). `kubeadm upgrade node` is run on every other node afterward — additional control-plane nodes and all worker nodes — to bring that specific node in line with the configuration `apply` already established, without re-deciding anything cluster-wide.
_What the interviewer is probing for:_ Correctly distinguishing the one-time cluster-deciding step from the repeated per-node propagation step.

**🎯 Intermediate:** _"Why must Kubernetes clusters be upgraded one minor version at a time instead of jumping straight to the latest release?"_
**Model answer:** Kubernetes' version skew policy only guarantees compatibility across a one-minor-version gap between the api-server and other components (kubelet, kube-proxy, kubectl); jumping two or more minor versions at once risks hitting removed or changed APIs, incompatible component protocols, or upgrade logic that was never tested for that large a gap. kubeadm itself enforces this by refusing (or warning heavily against) multi-version jumps during `kubeadm upgrade plan`, so the supported path for a large version gap is a sequence of single-minor-version upgrade cycles, each fully completed before starting the next.
_What the interviewer is probing for:_ Awareness that this is a hard compatibility constraint, not just a conservative recommendation.

**🎯 Senior:** _"You're upgrading a 3-control-plane-node, 10-worker-node cluster. Walk through your exact ordering and what could go wrong at each stage."_
**Model answer:** I'd start by backing up etcd ([§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)) and reviewing `kubeadm upgrade plan`'s output on the first control-plane node. I'd drain that node, run `kubeadm upgrade apply <version>` — this is the highest-risk step since it changes static Pod manifests and potentially renews certificates cluster-wide; if the api-server manifest is malformed, the entire control plane can become unreachable, which is exactly why the etcd backup exists as a rollback path. Once that node's kubelet/kubectl are upgraded and it's uncordoned, I'd move to the remaining two control-plane nodes one at a time with `kubeadm upgrade node`, draining and uncordoning each — a risk here is running these in parallel, which could momentarily drop etcd quorum ([§10](../Part2/Section-10-Part2-etcd-Deep-Dive-Data-Model-Raft-Consensus.md)) if more than one control-plane node's etcd member is down simultaneously, so I'd strictly serialize them. Finally, I'd work through the 10 worker nodes one at a time, draining, upgrading, and uncordoning each — the main risk here is workload disruption if PodDisruptionBudgets aren't respected during drain, or if the cluster lacks enough spare capacity to reschedule evicted Pods elsewhere during each node's evacuation window.
_What the interviewer is probing for:_ A concrete, ordered execution plan that explicitly reasons about etcd quorum risk during multi-control-plane upgrades and workload-disruption risk during worker upgrades, not just a recitation of the command sequence.

**🎯 Architect:** _"How would you design an automated upgrade pipeline for a fleet of kubeadm clusters that minimizes both risk and total upgrade time?"_
**Model answer:** I'd encode the strict ordering (first control-plane apply, remaining control-plane nodes serially, then workers) as an idempotent pipeline stage rather than a set of manual runbook steps, with an automated etcd snapshot ([§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)) taken and verified immediately before the pipeline touches the first control-plane node, and an automated abort-and-alert path if `kubeadm upgrade apply` doesn't report success within a bounded timeout. For worker nodes, I'd parallelize the drain/upgrade/uncordon cycle across a bounded subset of nodes at a time (e.g., one availability zone's worth) rather than either strictly one-at-a-time or all-at-once, balancing total upgrade wall-clock time against blast radius if a bad node image or kubelet config affects an entire batch. I'd also gate the pipeline on PodDisruptionBudget compatibility checks beforehand, since automated drains that violate PDBs will stall indefinitely rather than fail loudly, and I'd version-pin the exact kubeadm/kubelet/kubectl package versions in the pipeline definition itself so the same upgrade is fully reproducible across every cluster in the fleet rather than depending on "latest available" at run time.
_What the interviewer is probing for:_ Ability to translate a manual, sequential runbook into a safe, partially-parallelized, fully automated pipeline while explicitly reasoning about blast radius and etcd/quorum risk at scale.

## 12. Common Misconceptions

1. **"`kubeadm upgrade` also upgrades the `kubeadm` binary itself."** It does not — the `kubeadm`, `kubelet`, and `kubectl` binaries are always upgraded separately via the OS package manager, before or after running the relevant `kubeadm upgrade` subcommand.
2. **"Any control-plane node can run `kubeadm upgrade apply`."** Only the first one should — every other control-plane node uses `kubeadm upgrade node` to propagate the already-decided configuration, never `apply` again.
3. **"Kubernetes upgrades require full cluster downtime."** They don't — the entire point of the ordered, node-by-node drain/upgrade/uncordon cycle is to avoid full-cluster downtime, accepting only per-node evacuation windows instead.
4. **"You can skip straight from an old version to the newest release to save time."** Kubernetes' version skew policy only supports one-minor-version jumps per upgrade cycle; multi-version jumps are unsupported and require sequential single-version upgrade cycles instead.

## 13. 🔑 Key Takeaways

- Upgrade exactly one Kubernetes minor version at a time, in strict order: first control-plane node (`kubeadm upgrade apply`), remaining control-plane nodes (`kubeadm upgrade node`), then worker nodes last.
- `kubeadm upgrade apply` is run exactly once per upgrade cycle; every other node uses `kubeadm upgrade node`.
- Always drain a node before touching its kubelet, and uncordon it only after the upgrade completes successfully.
- Take a fresh, verified etcd snapshot ([§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md)) immediately before starting any control-plane upgrade — it's the rollback path if `apply` fails.
- `kubeadm upgrade apply` also renews near-expiry certificates as a side effect, but that shouldn't be relied on as the sole certificate-renewal mechanism.

## 14. Related Concepts & What's Next

[§16](../Part3/Section-16-Part3-Kubeadm-Cluster-Bootstrapping-Step-By-Step.md) covered the original kubeadm bootstrap sequence this section's upgrade machinery directly reuses. [§15](../Part2/Section-15-Part2-High-Availability-Control-Plane-Architectures.md) (Part 2) covers the HA control-plane topologies that determine how many "additional control-plane node" steps a given cluster's upgrade requires. [§108](./Section-108-Part14-Node-Maintenance-cordon-drain-uncordon.md) (next) covers the cordon/drain/uncordon workflow this section assumes before touching any node's kubelet. [§109](./Section-109-Part14-Certificate-Rotation-Renewal.md) covers the certificate rotation that `kubeadm upgrade apply` triggers as a side effect. [§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md) covers the etcd backup procedure that should always precede a control-plane upgrade.

**Next Section:** [§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md) — `Section-107-Part14-etcd-Backup-Restore-Procedures.md`
