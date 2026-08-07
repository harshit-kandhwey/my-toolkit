# Section 111 (Part 14): Version Skew Policy and Deprecation Handling

## 1. Definition

**Plain language:** A Kubernetes cluster is never one single version running everywhere at once, even in a healthy steady state — the API server, controller-manager, scheduler, kubelet on each node, and `kubectl` itself can each legitimately sit on slightly different versions during a rolling upgrade, or even permanently by design (older nodes, newer control plane). Kubernetes defines exact rules for how far apart these components are allowed to drift — the **version skew policy** — and separately defines a formal, predictable process for retiring old API versions over time — **deprecation handling**. Getting either wrong is one of the most common causes of a broken upgrade or a suddenly-failing manifest.

**Precise definition:** Kubernetes' **version skew policy** specifies the maximum supported version difference between cluster components during and after an upgrade: `kube-apiserver` instances in a highly-available control plane may differ by at most one minor version from each other; `kube-controller-manager`, `kube-scheduler`, and `cloud-controller-manager` may be up to one minor version _older_ than `kube-apiserver`; `kubelet` may be up to **three** minor versions older than `kube-apiserver` (as of current upstream policy); and `kubectl` is supported within one minor version _either direction_ of `kube-apiserver`. **API deprecation policy** governs how long a given API version remains available after being marked deprecated: a **GA (`v1`) API version**, once deprecated, must remain supported for no less than **12 months or 3 releases** (whichever is longer) before removal; **beta API versions** get no less than **9 months or 3 releases**; **alpha API versions** carry no deprecation guarantee and may be removed in any release. The **API deprecation guide** and each release's changelog enumerate exactly which API versions are scheduled for removal in that release.

## 2. Why This Matters

- **Ignoring version skew during a multi-node upgrade is a common cause of an upgrade going sideways mid-flight** — an out-of-policy kubelet-to-apiserver gap can cause node registration failures or feature mismatches that only surface once several nodes have already been upgraded, well past the point of an easy rollback.
- **API deprecation is not a hypothetical concern — it directly breaks real manifests on a predictable schedule**, and the single most common real-world trigger is a Velero restore ([§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md)) or a stale Helm chart referencing a since-removed `apiVersion`, failing with an API-not-found error precisely when a team is depending on that manifest working, such as during a disaster-recovery restore.
- **The version skew policy exists specifically to make rolling, zero-downtime upgrades possible** — without a defined, bounded skew window, a control-plane-first upgrade order ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) would require every component to update in perfect lockstep, which is operationally infeasible at any real cluster scale.

🔑 **Key Takeaway:** Version skew policy defines the maximum safe version gap between `kube-apiserver`, control-plane components, `kubelet`, and `kubectl` during an upgrade, while API deprecation policy guarantees a minimum notice period (12 months/3 releases for GA, 9 months/3 releases for beta) before a given API version is removed — both are the concrete mechanical rules that make Kubernetes' rolling-upgrade model ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) and long-term manifest stability possible at all.

## 3. Prerequisites and Dependencies

Directly extends [§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md) (Cluster Upgrades with kubeadm) — the ordering rules in that section exist precisely because of the version skew policy formalized here — and [§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md) (Velero), since cross-cluster or cross-version restores are the most common place deprecated-API failures actually surface in practice. Assumes familiarity with kubeadm upgrade mechanics and the general concept of API groups/versions (Part 2). Forward-references [§112](./Section-112-Part14-Disaster-Recovery-Planning-Kubernetes-Clusters.md), the Part 14 capstone, which synthesizes this section's deprecation-awareness discipline into full disaster recovery planning.

## 4. Architecture Diagram

```text
┌───────────────────────────────────────────────────────────────────────────┐
│                     Version Skew Policy (example: apiserver = v1.31)      │
│                                                                           │
│   kube-apiserver (HA, multiple instances)                                 │
│   v1.31 ◄──── max 1 minor version skew ────► v1.30   (both valid together)│
│                                                                           │
│   kube-controller-manager / kube-scheduler / cloud-controller-manager     │
│   Must be ≤ apiserver version, at most 1 minor OLDER:  v1.30 or v1.31 OK  │
│                                                                           │
│   kubelet (per node)                                                      │
│   Must be ≤ apiserver version, at most 3 minors OLDER: v1.28–v1.31 OK     │
│   ──────────────────────────────────────────────────────────────────►     │
│   (nodes can lag much further behind than control-plane components)       │
│                                                                           │
│   kubectl (client)                                                        │
│   Within 1 minor version EITHER direction: v1.30, v1.31, or v1.32 OK      │
│                                                                           │
│   Correct upgrade order (per §106): apiserver first → controller-manager/ │
│   scheduler → kubelet last — this order is *why* skew policy permits      │
│   controller-manager/scheduler/kubelet to lag, not lead, the apiserver    │
└───────────────────────────────────────────────────────────────────────────┘

┌───────────────────────────────────────────────────────────────────────────┐
│                       API Deprecation Timeline (example)                  │
│                                                                           │
│  v1.20: policy/v1beta1 PodSecurityPolicy marked deprecated                │
│           │                                                               │
│           │  ≥ 9 months / 3 releases (beta minimum notice)                │
│           ▼                                                               │
│  v1.25: policy/v1beta1 PodSecurityPolicy REMOVED — manifests using it     │
│           now fail with an API-not-found error, no fallback               │
└───────────────────────────────────────────────────────────────────────────┘
```

- **The skew policy is intentionally asymmetric** — kubelet is allowed to lag far more (3 minors) than control-plane components (1 minor), reflecting the operational reality that upgrading hundreds of nodes takes much longer than upgrading a handful of control-plane instances.
- **The correct upgrade order from [§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md) (apiserver → controller-manager/scheduler → kubelet) is a direct consequence of this policy** — components are permitted to be older than the apiserver, never newer, so upgrading anything ahead of the apiserver risks going out of policy immediately.
- **Deprecation removal happens on a fixed, published schedule** — there is no grace period beyond what the deprecation guide states; a manifest still referencing a removed API version simply fails outright the moment the target cluster reaches that release.

## 5. Hands-On

### 5.1 Checking Component Versions Against Skew Policy Before an Upgrade

**Purpose:** Verify every cluster component's current version and confirm the planned target version stays within policy before starting an upgrade.

**Syntax:**

```bash
kubectl version --short
kubectl get nodes -o custom-columns='NAME:.metadata.name,KUBELET:.status.nodeInfo.kubeletVersion'
kubeadm upgrade plan
```

**Example usage and expected output:**

```bash
$ kubectl get nodes -o custom-columns='NAME:.metadata.name,KUBELET:.status.nodeInfo.kubeletVersion'
NAME      KUBELET
node-1    v1.29.4
node-2    v1.29.4
node-3    v1.28.9

$ kubeadm upgrade plan
[upgrade/versions] Cluster version: v1.29.4
[upgrade/versions] kubeadm version: v1.31.0
Upgrade to the latest version in the v1.31 series:
COMPONENT                 CURRENT   TARGET
kube-apiserver             v1.29.4   v1.31.0
kube-controller-manager    v1.29.4   v1.31.0
kube-scheduler              v1.29.4   v1.31.0
```

**Production usage example:** Confirming `node-3` sits at v1.28.9 (one minor behind the others) before starting the control-plane upgrade to v1.31 catches, ahead of time, that node-3 would land 3 minors behind the new apiserver — right at the edge of the supported kubelet skew — informing a decision to upgrade node-3's kubelet sooner rather than letting it linger at the policy boundary.

**Common errors:** Attempting to jump the apiserver more than one minor version in a single `kubeadm upgrade apply` step — kubeadm enforces upgrading one minor version at a time, and skipping this (e.g. v1.28 directly to v1.31) is explicitly unsupported and will be rejected or produce undefined behavior.

### 5.2 Identifying and Migrating Deprecated API Versions Before They're Removed

**Purpose:** Proactively find manifests using an API version scheduled for removal, before an upgrade breaks them outright.

**Syntax:**

```bash
kubectl api-resources -o wide | grep -i deprecated
kubectl deprecations 2>/dev/null # via krew plugin, if installed
kubectl get --raw /metrics | grep apiserver_requested_deprecated_apis
```

**Example usage and expected output:**

```bash
$ kubectl get --raw /metrics | grep apiserver_requested_deprecated_apis
apiserver_requested_deprecated_apis{group="policy",removed_release="1.25",resource="podsecuritypolicies",version="v1beta1"} 1

$ grep -rl "apiVersion: policy/v1beta1" ./manifests/
./manifests/legacy-psp.yaml
```

**Production usage example:** Running the `apiserver_requested_deprecated_apis` metric query against a production cluster's `/metrics` endpoint a full release cycle before a planned upgrade surfaces exactly which manifests will break, giving the team time to migrate `policy/v1beta1` PodSecurityPolicy references to their replacement (Pod Security Admission, Part 10) well ahead of the removal release rather than discovering it during the upgrade window.

**Common errors:** Only checking for deprecated APIs immediately before an upgrade rather than continuously — the metric above is available on every running cluster at every version, and checking it only at upgrade time misses months of advance warning the deprecation policy was specifically designed to provide.

### 5.3 Handling a Restore or Chart That References a Removed API Version

**Purpose:** Recover when a Velero restore ([§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md)) or Helm chart fails because it references an API version no longer served by the target cluster.

**Syntax:**

```bash
kubectl convert -f old-manifest.yaml --output-version apps/v1
```

**Example usage and expected output:**

```bash
$ velero restore describe restore-20260731
Phase: PartiallyFailed
Errors:
  Velero:
  - error restoring extensions/v1beta1, Kind=Ingress "web": the server could not find the requested resource

$ kubectl convert -f web-ingress.yaml --output-version networking.k8s.io/v1 > web-ingress-v1.yaml
```

**Production usage example:** A Velero restore ([§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md)) taken from a cluster several versions older fails partway through with exactly this kind of API-not-found error on an `Ingress` resource — the fix is not to abandon the restore, but to extract the failed resource's manifest, run it through `kubectl convert` (or manually rewrite it) to the currently-served API version, and re-apply it directly, completing the recovery the automated restore path alone couldn't finish.

**Common errors:** Assuming a `PartiallyFailed` Velero restore means the whole recovery failed and starting over from scratch — in practice it usually means everything except the specific deprecated-API resources restored successfully, and the fix is a targeted manifest conversion for just those remaining items, not a full restart.

## 6. Production Usage Notes

- **Every cluster upgrade plan should include an explicit deprecated-API audit step** using the `apiserver_requested_deprecated_apis` metric (or the equivalent `kubectl-deprecations` krew plugin) before touching any component version, not as an afterthought once the upgrade has already started.
- **Skew policy compliance should be checked per-node, not just at the fleet-average level** — a single straggler node running a kubelet version far behind the rest of the fleet is easy to miss in an aggregate view but will be the one that goes out of policy first.
- **The official Kubernetes deprecation guide (published per release) is the authoritative source for exactly which API versions are being removed in an upcoming release** — relying on tribal knowledge or an outdated blog post instead of the actual release's deprecation guide is a common source of surprise breakage.

## 7. Security Considerations

- **Deprecated and removed security-relevant APIs (like `policy/v1beta1` PodSecurityPolicy) leave a security control gap if their replacement isn't adopted before removal** — a cluster that never migrated from PodSecurityPolicy to Pod Security Admission before the v1.25 removal silently lost that entire enforcement layer, not just an API convenience.
- **A stale `kubectl` client far outside the supported skew window may lack support for current authentication or admission-control features**, creating an operational gap where an operator's tooling silently fails to exercise controls the cluster otherwise enforces.
- **Rushing a version-skew-violating emergency upgrade under incident pressure risks skipping the deprecated-API audit step entirely**, potentially reintroducing exactly the security-control gaps the previous point describes at the worst possible time.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                                                         | Cause                                                                                           | Fix                                                                                                                                                                         |
| ------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `kubeadm upgrade apply` rejects the target version                                                                              | Attempting to skip more than one minor version in a single upgrade step                         | Upgrade one minor version at a time, per [§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)'s ordering, until reaching the target |
| Node fails to rejoin cluster after kubelet upgrade lag                                                                          | kubelet drifted more than 3 minor versions behind `kube-apiserver`, exceeding supported skew    | Upgrade the lagging node's kubelet to bring it back within the 3-minor-version window                                                                                       |
| Manifest apply fails with API-not-found after a cluster upgrade                                                                 | Manifest references an `apiVersion` removed in the new release                                  | Run `kubectl convert` or manually update the manifest to the currently-served API version before reapplying                                                                 |
| Velero restore ([§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md)) shows `PartiallyFailed` on specific resources | Backup was taken on an older cluster referencing an API version now removed on the target       | Extract and convert just the failed resources' manifests to the current API version, then reapply directly                                                                  |
| Security control silently absent after an upgrade                                                                               | A deprecated security-relevant API (e.g. PodSecurityPolicy) was removed without migrating first | Audit deprecated-API usage, as shown above, well before any upgrade and migrate to the replacement control ahead of time                                                    |

## 9. Best Practices

- Run the deprecated-API audit (`apiserver_requested_deprecated_apis` metric or equivalent) as a standing, recurring check — not a one-time pre-upgrade task — so deprecation warnings surface with months of lead time, as the policy intends.
- Always upgrade one minor version at a time per [§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)'s ordering, verifying skew compliance at each step rather than attempting to jump directly to a distant target version.
- Treat `kubectl convert` (or manual manifest migration) as a normal part of the upgrade and restore toolkit, not an emergency improvisation, since deprecated-API failures during restores ([§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md)) are a routine, expected occurrence rather than an edge case.
- Read the actual per-release deprecation guide before every upgrade, rather than relying on memory of past removals or general policy numbers alone.

## 10. Common Anti-Patterns / Mistakes

- **Treating version skew policy numbers as flexible guidelines rather than hard support boundaries** — operating outside the documented skew window is explicitly unsupported and can produce undefined behavior, not merely a theoretical risk.
- **Auditing for deprecated APIs only immediately before an upgrade**, forfeiting the months of advance notice the deprecation policy is specifically designed to provide.
- **Assuming a partially-failed Velero restore ([§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md)) means starting recovery over from scratch**, rather than recognizing it as a scoped, fixable gap usually limited to resources referencing removed API versions.

## 11. Interview Questions

**🎯 Beginner:** _"What is Kubernetes' version skew policy, in general terms?"_
**Model answer:** It's the set of rules defining how far apart in version different cluster components are allowed to be, both during and after an upgrade. In general, control-plane components like the controller-manager and scheduler can be up to one minor version older than the API server, kubelet on nodes can lag up to three minor versions behind, and `kubectl` clients are supported within one minor version in either direction of the API server. The policy exists so a rolling upgrade — control plane first, then nodes — is actually operationally feasible, since requiring every component to update in perfect lockstep would make upgrading a large cluster impractical.
_What the interviewer is probing for:_ Basic familiarity with the actual skew numbers and why the policy exists, not just that "components can differ somewhat."

**🎯 Intermediate:** _"You're about to restore a Velero backup taken six months ago onto a cluster that's since been upgraded twice. What do you check first, and why?"_
**Model answer:** Before restoring, I'd check whether any resources in that backup use an API version that's been deprecated and removed in the intervening upgrades — a six-month-old backup, spanning two upgrade cycles, is a realistic candidate for containing something like an old `Ingress` under `extensions/v1beta1` that no longer exists on the target cluster. I'd look at the backup's resource manifests directly, or just attempt the restore and watch for `PartiallyFailed` status with API-not-found errors in `velero restore describe`. If I find affected resources, I'd extract just those manifests, run them through `kubectl convert` to the currently-served API version, and reapply them directly rather than assuming the whole restore has failed.
_What the interviewer is probing for:_ Practical connection between version skew/deprecation concepts and a real Velero ([§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md)) restore scenario, and knowing that a partial restore failure is scoped and fixable rather than catastrophic.

**🎯 Senior:** _"How would you build a process to prevent deprecated-API breakage from ever surprising your team during an upgrade?"_
**Model answer:** I'd make deprecated-API auditing a continuous, automated check rather than a manual pre-upgrade step — scraping the `apiserver_requested_deprecated_apis` metric on a schedule (or running the `kubectl-deprecations` krew plugin in CI against the manifest repository) and alerting whenever a resource in active use references an API version with a published removal release within, say, the next two minor versions. I'd also fold this into the change-management process for any Helm chart or manifest update, so new deprecated-API usage doesn't get introduced between audits. Combined with reading the actual per-release deprecation guide before planning any upgrade — rather than relying on memory of prior removals — this turns deprecation handling from a reactive "the upgrade just broke something" scramble into a proactive, months-ahead-of-time migration task, which is exactly the lead time the deprecation policy (12 months/3 releases for GA, 9 months/3 for beta) is designed to provide.
_What the interviewer is probing for:_ Ability to design a systematic, automated early-warning process rather than relying on manual vigilance or tribal knowledge at upgrade time.

**🎯 Architect:** _"How do version skew policy and API deprecation handling fit into an organization's broader disaster recovery and upgrade strategy?"_
**Model answer:** Both are foundational constraints that every other piece of the upgrade and DR strategy has to respect. For upgrades, I'd bake skew-policy compliance checks directly into the automated upgrade pipeline ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) — refusing to proceed to the next component if the resulting version gap would exceed policy — rather than trusting an operator to remember the numbers under time pressure. For disaster recovery specifically, I'd recognize that a Velero backup ([§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md)) is effectively a time capsule of API versions as they existed when it was taken, so any DR runbook needs an explicit step validating that a restore's manifests are compatible with the target cluster's currently-served APIs, converting anything that isn't, before declaring a restore complete. I'd also maintain a standing, automated deprecated-API audit across all production manifests and Helm charts, feeding results into the upgrade planning cycle months ahead of any actual maintenance window, so upgrade risk is discovered and mitigated on the team's own schedule rather than the cluster's. This discipline — skew-aware upgrade automation plus deprecation-aware backup/restore validation — is a load-bearing piece of what makes the full disaster recovery plan in [§112](./Section-112-Part14-Disaster-Recovery-Planning-Kubernetes-Clusters.md) actually executable under real time pressure, rather than theoretically sound but practically fragile.
_What the interviewer is probing for:_ Systems-level integration of version skew and deprecation awareness into upgrade automation and DR tooling, not just isolated knowledge of the policy numbers.

## 12. Common Misconceptions

1. **"Version skew is only a concern for very large clusters."** Even a small cluster can go out of policy if a single node's kubelet lags too far behind after a control-plane upgrade — cluster size affects how _likely_ drift is, not whether the policy applies.
2. **"Deprecated APIs are removed without warning."** Kubernetes' deprecation policy guarantees a minimum notice period (12 months/3 releases for GA, 9 months/3 releases for beta) before removal, published in advance via the per-release deprecation guide — surprise only happens when that guide isn't consulted.
3. **"A `PartiallyFailed` Velero restore ([§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md)) means the recovery failed."** It usually means specific resources referencing removed API versions failed to restore while everything else succeeded — a scoped, fixable gap, not a total failure.
4. **"kubectl, kubelet, and control-plane components all need to be on the exact same version."** The skew policy explicitly permits differing amounts of version lag for each component type, by design, to make rolling upgrades operationally feasible.

## 13. 🔑 Key Takeaways

- Version skew policy bounds how far `kube-apiserver`, control-plane components, `kubelet`, and `kubectl` may legitimately differ in version, asymmetrically (kubelet permitted much more lag than control-plane components).
- API deprecation policy guarantees a minimum notice period before removal — 12 months/3 releases for GA APIs, 9 months/3 releases for beta — published per release in the official deprecation guide.
- Deprecated-API auditing should be continuous, using metrics like `apiserver_requested_deprecated_apis`, not a one-time check immediately before an upgrade.
- A Velero restore ([§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md)) failing on a removed API version is a scoped, fixable problem — extract and convert the affected manifests, then reapply — not a reason to restart the whole recovery.
- Skew and deprecation discipline are load-bearing prerequisites for both routine cluster upgrades ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) and for disaster recovery actually working under real time pressure.

## 14. Related Concepts & What's Next

This section formalized the mechanical rules — version skew limits and API deprecation timelines — that make the rolling upgrade process ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) and cross-version Velero restores ([§110](./Section-110-Part14-Cluster-Backup-Strategies-Velero.md)) actually safe and predictable, rather than left to operator memory or assumption. The next and final section of Part 14 synthesizes everything from [§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md) through this section — upgrades, etcd backup, node maintenance, certificate rotation, Velero, and version skew/deprecation handling — into a complete disaster recovery planning framework.

**Next Section:** [§112](./Section-112-Part14-Disaster-Recovery-Planning-Kubernetes-Clusters.md) — `Section-112-Part14-Disaster-Recovery-Planning-Kubernetes-Clusters.md`
