# Section 108 (Part 14): Node Maintenance: cordon, drain, uncordon

## 1. Definition

**Plain language:** A node sometimes needs to be taken out of service temporarily — a kernel patch, a hardware replacement, an OS upgrade — without the workloads it's running simply vanishing or getting killed abruptly. Kubernetes gives operators a clean, three-step way to do this: stop new work from landing there, safely relocate the work already there, do the maintenance, then let the node back into rotation.

**Precise definition:** **`kubectl cordon <node>`** marks a node `Unschedulable`, preventing the scheduler from placing any new Pods on it while leaving existing Pods running untouched. **`kubectl drain <node>`** evicts (or deletes) all Pods from a node in a controlled way — respecting PodDisruptionBudgets (PDBs), honoring each Pod's `terminationGracePeriodSeconds`, and by default refusing to proceed if the node hosts Pods managed by a DaemonSet or unmanaged/standalone Pods, unless `--ignore-daemonsets` and `--force` are explicitly passed — and implicitly cordons the node first if it isn't already. **`kubectl uncordon <node>`** reverses cordon, marking the node `Schedulable` again so the scheduler resumes considering it for new Pods; it does **not** move any workloads back automatically, since drained Pods are rescheduled elsewhere by their controllers and won't return to the original node without a fresh scheduling decision.

## 2. Why This Matters

- **Cordon/drain/uncordon is the mechanical basis for every planned node-level maintenance operation** — kernel patching, node pool upgrades, hardware replacement, and even the node-by-node kubelet upgrade step in [§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md) all rely on this exact sequence to avoid disrupting running workloads.
- **`drain` is deliberately safety-conscious, not merely a bulk-delete** — it respects PodDisruptionBudgets so it won't evict a Pod if doing so would violate an application's declared minimum availability, which is the difference between a controlled maintenance window and an accidental outage.
- **This is a core CKA administration skill tested directly** — "safely drain this node, perform an action, then return it to the cluster" is a standard exam scenario precisely because it combines several real operational concerns (PDBs, DaemonSets, grace periods) into one command sequence.

🔑 **Key Takeaway:** `cordon` stops new scheduling, `drain` safely evicts existing Pods (respecting PodDisruptionBudgets and requiring explicit flags to override DaemonsSet/standalone-Pod protections), and `uncordon` makes the node schedulable again without automatically moving workloads back — together they form the standard, safe procedure for any planned node maintenance.

## 3. Prerequisites and Dependencies

Builds on [§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md) (etcd Backup and Restore Procedures) as the next operational lifecycle skill in Part 14's maintenance sequence, and assumes familiarity with the scheduler's basic Pod-placement role (Part 2) and PodDisruptionBudgets (Part 9, workload availability). Forward-references [§109](./Section-109-Part14-Certificate-Rotation-Renewal.md) (Certificate Rotation and Renewal), since certificate rotation on a control-plane node is itself an operation frequently performed during a cordoned/drained maintenance window.

## 4. Architecture Diagram

```text
   NODE MAINTENANCE LIFECYCLE
   ═══════════════════════════════════════════════════════

   STEP 1: cordon
   ─────────────────────────────────────────────────────────
     kubectl cordon node-3
       -> node-3 marked "Unschedulable" (SchedulingDisabled)
       -> scheduler will NOT place new Pods here
       -> Pods already running on node-3 are UNAFFECTED

   STEP 2: drain
   ─────────────────────────────────────────────────────────
     kubectl drain node-3 --ignore-daemonsets --delete-emptydir-data
       -> implicitly cordons (already done above)
       -> for each Pod on node-3:
            - DaemonSet-managed Pod?  -> skipped (stays, unless --ignore-daemonsets)
            - covered by a PDB?       -> evict() call checks PDB budget
                 - would violate min-available -> eviction BLOCKED, retried
                 - within budget           -> Pod evicted, controller
                                              reschedules it on ANOTHER node
       -> node-3 ends with (almost) no workload Pods left

   STEP 3: perform maintenance
   ─────────────────────────────────────────────────────────
     (patch kernel, replace hardware, upgrade kubelet, rotate certs...)

   STEP 4: uncordon
   ─────────────────────────────────────────────────────────
     kubectl uncordon node-3
       -> node-3 marked "Schedulable" again
       -> scheduler MAY place new Pods here going forward
       -> Pods evicted in Step 2 do NOT move back automatically
```

- **Draining never touches DaemonSet Pods by default** — DaemonSet Pods are excluded from normal eviction because they're tied to the node itself (e.g., a log-shipper or CNI agent), and `--ignore-daemonsets` tells `drain` to proceed despite their presence rather than actually removing them.
- **PodDisruptionBudgets are the safety mechanism that can legitimately block or slow a drain** — this is by design, not a bug to work around with `--force`.

## 5. Hands-On

### 5.1 Cordoning a Node

**Purpose:** Stop the scheduler from placing any new Pods on a node, without disturbing what's already running there — the first, non-disruptive step before any maintenance.

**Syntax:** `kubectl cordon <node-name>`

```bash
$ kubectl cordon node-3
node/node-3 cordoned

$ kubectl get nodes
NAME       STATUS                     ROLES    AGE   VERSION
node-1     Ready                      <none>   90d   v1.31.0
node-2     Ready                      <none>   90d   v1.31.0
node-3     Ready,SchedulingDisabled   <none>   90d   v1.31.0
```

**Production usage example:** Cordoning a node an hour before its scheduled maintenance window (without draining yet) lets the scheduler naturally stop routing new traffic-sensitive workloads there while existing Pods keep serving traffic normally, giving a clean, low-risk buffer before the actual eviction step.

**Common errors:** Assuming `cordon` alone is sufficient before rebooting a node — cordon only stops _new_ scheduling; every Pod already running on the node will still be forcibly killed by a reboot unless it was also drained first.

### 5.2 Draining a Node

**Purpose:** Safely evict all evictable Pods from a node ahead of a disruptive maintenance action, respecting PodDisruptionBudgets and grace periods.

**Syntax:** `kubectl drain <node-name> --ignore-daemonsets [--delete-emptydir-data] [--force] [--grace-period=<seconds>]`

```bash
$ kubectl drain node-3 --ignore-daemonsets --delete-emptydir-data
node/node-3 cordoned
evicting pod production/web-7f8b9c-x2k9m
evicting pod production/cache-5d7f6b-p8q1r
evicting pod kube-system/kube-proxy-abc12  # DaemonSet, skipped due to --ignore-daemonsets
error when evicting pods/"web-7f8b9c-x2k9m" -n "production" (will retry after 5s): Cannot evict pod as it would violate the pod's disruption budget.
evicting pod production/web-7f8b9c-x2k9m
pod/cache-5d7f6b-p8q1r evicted
pod/web-7f8b9c-x2k9m evicted
node/node-3 drained
```

**Production usage example:** A `Deployment` with 3 replicas and a `minAvailable: 2` PodDisruptionBudget will cause `drain` to retry evicting its Pods one at a time until the controller has rescheduled a replacement elsewhere and the budget allows the next eviction — this is exactly the mechanism that turns a naive "kill everything on this node" into a controlled rolling relocation that never drops below the declared minimum availability.

**Common errors:** Running `drain` without `--ignore-daemonsets` on a node running standard DaemonSets (like `kube-proxy` or a CNI agent) causes the command to abort immediately with an error listing the DaemonSet-managed Pods — this is intentional friction, not a bug, since DaemonSet Pods aren't meant to be relocated at all.

### 5.3 Uncordoning a Node After Maintenance

**Purpose:** Return a node to the scheduling pool once maintenance is complete.

**Syntax:** `kubectl uncordon <node-name>`

```bash
$ kubectl uncordon node-3
node/node-3 uncordoned

$ kubectl get nodes
NAME       STATUS   ROLES    AGE   VERSION
node-1     Ready    <none>   90d   v1.31.0
node-2     Ready    <none>   90d   v1.31.0
node-3     Ready    <none>   90d   v1.31.0
```

**Production usage example:** After uncordoning node-3, workloads that were evicted during the drain do not automatically migrate back — they continue running wherever the scheduler placed them during the drain. node-3 simply becomes eligible for future scheduling decisions, gradually receiving new Pods over time as normal scheduling and any subsequent rollouts occur.

**Common errors:** Expecting `uncordon` to rebalance the cluster back to its pre-drain Pod distribution — it does not trigger any rescheduling at all; if even distribution matters, a separate rebalancing action (e.g., a rollout restart of affected Deployments, or a descheduler) is required.

## 6. Production Usage Notes

- **Always cordon before draining as a distinct, deliberate first step in high-stakes environments**, even though `drain` cordons implicitly — an explicit cordon gives a visible window to confirm traffic has shifted away before the more disruptive eviction step begins.
- **Set an explicit `--timeout` on `drain` in automation** so a stuck eviction (e.g., a Pod that a misconfigured PDB will never allow to be evicted) fails loudly rather than hanging a maintenance pipeline indefinitely.
- **`--delete-emptydir-data` is required whenever a node hosts Pods using `emptyDir` volumes** — without it, `drain` refuses to evict those Pods, since their `emptyDir` contents would otherwise be silently lost with no warning built into a bare eviction.

## 7. Security Considerations

- **Draining a node is a privileged, disruptive operation** — `kubectl drain`/`cordon`/`uncordon` should be gated by RBAC restricting `nodes/*` and `pods/eviction` verbs to a narrow operator or automation role, not broadly granted, since it can be used to forcibly relocate or disrupt arbitrary workloads across the cluster.
- **`--force` bypasses the standalone-Pod protection that normally blocks `drain`** — forcing eviction of unmanaged Pods (Pods with no owning controller) permanently deletes them with no controller to recreate them, so `--force` usage should be logged and reviewed, not routine.
- **A malicious or compromised actor with drain permissions can degrade availability cluster-wide** by repeatedly cordoning/draining nodes even without directly touching workload manifests — this makes node-level RBAC just as security-relevant as workload-level RBAC.

## 8. Common Troubleshooting Scenarios

| Symptom                                                     | Cause                                                                                | Fix                                                                                                     |
| ----------------------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| `drain` aborts immediately, listing DaemonSet Pods          | DaemonSet-managed Pods present and `--ignore-daemonsets` not passed                  | Re-run with `--ignore-daemonsets` (they remain running; this only allows drain to proceed)              |
| `drain` hangs, repeatedly retrying an eviction              | A PodDisruptionBudget's `minAvailable` can never be satisfied given current replicas | Investigate the PDB and Deployment replica count; temporarily scale up or adjust the PDB if appropriate |
| `drain` refuses to evict a Pod with an `emptyDir` volume    | `--delete-emptydir-data` flag not supplied                                           | Re-run with `--delete-emptydir-data`, understanding that volume's data will be lost                     |
| Node stays `SchedulingDisabled` after maintenance completes | `uncordon` was never run, or ran against the wrong node name                         | Run `kubectl uncordon <node>` and confirm with `kubectl get nodes`                                      |
| Workload distribution stays uneven after uncordoning        | `uncordon` does not reschedule already-evicted Pods back automatically               | Trigger a rollout restart or use a descheduler if rebalancing across nodes is required                  |

## 9. Best Practices

- Always cordon explicitly before draining in production, even though `drain` does it implicitly, to create a visible confirmation point before disruption begins.
- Set PodDisruptionBudgets on every availability-sensitive workload _before_ relying on `drain` for maintenance, so eviction safety is guaranteed by policy rather than by luck of timing.
- Use `--ignore-daemonsets` and `--delete-emptydir-data` deliberately and knowingly, not as reflexive flags copy-pasted without understanding their consequences.
- Automate node maintenance (cordon → drain → maintenance → uncordon) as a single scripted or pipeline-driven sequence with an explicit `--timeout`, rather than a manual, ad hoc process prone to a forgotten uncordon step.

## 10. Common Anti-Patterns / Mistakes

- **Rebooting or replacing a node after only cordoning it, without draining first**, causing every Pod still running there to be forcibly killed rather than gracefully relocated.
- **Reflexively adding `--force` to make a stuck drain "just work"**, permanently destroying unmanaged standalone Pods without recognizing that's what the flag actually does.
- **Forgetting to uncordon a node after maintenance**, silently shrinking the cluster's effective scheduling capacity until someone notices the node never returned to the pool.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `kubectl cordon` and `kubectl drain`?"_
**Model answer:** `cordon` only prevents _new_ Pods from being scheduled onto a node — anything already running there keeps running untouched. `drain` goes further: it evicts the Pods that are already on the node, moving them elsewhere (via their owning controllers), and it also cordons the node as part of doing so. Cordon is the "stop sending new work here" step; drain is the "also move the existing work away" step, typically used right before a disruptive maintenance action like a reboot.
_What the interviewer is probing for:_ Clear distinction between the two commands' actual scope, not treating them as synonyms.

**🎯 Intermediate:** _"You run `kubectl drain node-3` and it hangs, repeatedly trying to evict the same Pod. What's likely happening and how do you fix it?"_
**Model answer:** The most likely cause is a PodDisruptionBudget on that Pod's controller that can never be satisfied given the current replica count — for example, a Deployment with `minAvailable: 3` but only 3 replicas total, meaning evicting even one Pod would violate the budget, so the eviction API call keeps getting rejected and `drain` keeps retrying. I'd check `kubectl get pdb -n <namespace>` and compare `minAvailable`/`maxUnavailable` against the actual replica count, then either temporarily scale up the Deployment so there's room for the PDB to tolerate one eviction, or adjust the PDB if it's genuinely misconfigured — I would not reach for `--force`, since that would bypass the safety mechanism rather than fix the underlying constraint.
_What the interviewer is probing for:_ Understanding that a stuck drain is usually a PDB constraint working as intended, not a bug, and that the fix addresses the constraint rather than forcing past it.

**🎯 Senior:** _"Design the exact procedure your team would follow to patch the kernel on every node in a 50-node production cluster, one at a time, with zero workload downtime."_
**Model answer:** I'd process nodes one at a time, never in parallel, to keep the blast radius of any single node's maintenance minimal. For each node: cordon it first as an explicit, logged step; wait briefly to confirm no new traffic-sensitive Pods land there; then drain with `--ignore-daemonsets --delete-emptydir-data --timeout=300s`, letting PodDisruptionBudgets naturally throttle eviction pace so availability-sensitive workloads never dip below their declared minimums. Once drained, apply the kernel patch and reboot, then wait for the node to report `Ready` again before `uncordon`ing it and moving to the next node. I'd have PodDisruptionBudgets already in place on every availability-sensitive Deployment/StatefulSet as a hard prerequisite — not something assumed to exist — and I'd script the whole per-node sequence so a forgotten `uncordon` or a skipped drain step isn't possible. I'd also monitor cluster-wide capacity headroom throughout, since draining even one node in a tightly-packed cluster can trigger scheduling pressure or Pending Pods elsewhere if there isn't enough spare capacity.
_What the interviewer is probing for:_ Ability to design a safe, repeatable, one-node-at-a-time maintenance procedure that accounts for PDBs, capacity headroom, and automation discipline, not just knowing the three commands in isolation.

**🎯 Architect:** _"How does node-level maintenance tooling like cordon/drain fit into a broader cluster lifecycle and disaster-recovery strategy?"_
**Model answer:** Cordon/drain/uncordon is the mechanical primitive underneath several higher-level lifecycle operations: it's how [§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)'s node-by-node kubelet upgrade avoids disruption, it's frequently how certificate rotation ([§109](./Section-109-Part14-Certificate-Rotation-Renewal.md)) is performed on control-plane nodes without an abrupt outage, and it's the same pattern used for routine infrastructure churn like autoscaler-driven node replacement or spot-instance reclamation. At an architectural level, I'd treat "safe node removal" as a platform capability, not a manual runbook step — building automation that always cordons, verifies PDB-respecting drain completion, performs the maintenance action, confirms node health, and uncordons, with alerting if any step stalls or a node is left cordoned longer than expected. This same automation is directly reusable as part of disaster recovery exercises — simulating node loss and confirming workloads reschedule cleanly within the required RTO is a very close cousin of a routine planned drain, and testing it regularly under both "planned maintenance" and "unplanned node failure" framings is exactly the kind of rehearsal [§112](./Section-112-Part14-Disaster-Recovery-Planning-Kubernetes-Clusters.md)'s disaster recovery planning formalizes.
_What the interviewer is probing for:_ Recognition that cordon/drain is a foundational primitive reused across upgrades, certificate rotation, and disaster recovery, and that it belongs in platform automation rather than manual operator discipline alone.

## 12. Common Misconceptions

1. **"Cordoning a node stops its existing Pods from running."** Cordon only affects future scheduling decisions — Pods already running on the node are completely unaffected until an explicit drain or some other disruption happens.
2. **"Draining a node deletes DaemonSet Pods."** DaemonSet-managed Pods are specifically excluded from eviction; `--ignore-daemonsets` merely lets `drain` proceed past their presence, it does not remove them.
3. **"Uncordoning a node moves previously evicted workloads back to it."** Uncordon only makes the node eligible for future scheduling; nothing automatically returns — workloads stay wherever they were rescheduled during the drain.
4. **"`--force` is a normal, safe way to speed up a slow drain."** `--force` specifically bypasses the protection for standalone (unmanaged) Pods, permanently deleting them with no controller to recreate them — it is not a generic "try harder" flag.

## 13. 🔑 Key Takeaways

- `cordon` blocks new scheduling only; `drain` additionally evicts existing Pods, respecting PodDisruptionBudgets and requiring explicit flags (`--ignore-daemonsets`, `--delete-emptydir-data`) to handle DaemonSets and ephemeral volume data.
- `uncordon` makes a node schedulable again but never automatically rebalances workloads back onto it.
- A stuck drain retrying the same eviction almost always means a PodDisruptionBudget constraint is being correctly enforced, not a bug to force past.
- The full cordon → drain → maintain → uncordon sequence is the standard, safe basis for kernel patching, hardware replacement, node-by-node upgrades ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)), and certificate rotation ([§109](./Section-109-Part14-Certificate-Rotation-Renewal.md)) alike.
- `--force` and skipped `uncordon` steps are the most common ways this otherwise-safe procedure causes real damage — permanently lost standalone Pods, or silently shrunk cluster capacity.

## 14. Related Concepts & What's Next

[§107](./Section-107-Part14-etcd-Backup-Restore-Procedures.md) covered etcd backup/restore as the previous operational lifecycle skill in Part 14's maintenance sequence; this section covered the safe node-level maintenance procedure — cordon, drain, uncordon — that underlies node-by-node upgrades ([§106](./Section-106-Part14-Cluster-Upgrades-kubeadm-Control-Plane-Node-Upgrade-Ordering.md)) and is frequently the operational context certificate rotation happens inside. [§109](./Section-109-Part14-Certificate-Rotation-Renewal.md) (next) covers certificate rotation and renewal — the PKI maintenance task that keeps a cluster's internal trust relationships valid over time, often performed during exactly this kind of cordoned/drained maintenance window.

**Next Section:** [§109](./Section-109-Part14-Certificate-Rotation-Renewal.md) — `Section-109-Part14-Certificate-Rotation-Renewal.md`
