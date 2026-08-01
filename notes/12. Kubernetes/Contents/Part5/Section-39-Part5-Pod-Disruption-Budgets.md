# Section 39 (Part 5): Pod Disruption Budgets

## 1. Definition

**Plain language:** A node needs draining for a kernel upgrade, or the Cluster Autoscaler (§38) wants to remove an underutilized node, or an operator runs `kubectl delete node`. Each of these is a deliberate, plannable action — nobody's forcing it to happen this exact second. A Pod Disruption Budget lets a workload tell the cluster "these deliberate actions are fine, but not all at once — never take down more than this many of my replicas simultaneously," turning what would otherwise be an uncoordinated stampede of evictions into a constraint the cluster respects.

**Precise definition:** A **PodDisruptionBudget (PDB)** is a namespaced API object that limits the number of Pods matching a label selector that can be **voluntarily disrupted** at the same time, expressed as either `minAvailable` (a floor on how many matching Pods must remain available) or `maxUnavailable` (a ceiling on how many matching Pods may be unavailable at once) — never both on the same PDB. It is enforced through the **Eviction API** (used by `kubectl drain`, Cluster Autoscaler's scale-down, and any other component performing a voluntary eviction rather than a direct Pod delete): an eviction request that would push the count of unavailable matching Pods past the PDB's bound is rejected with a `429 Too Many Requests`, forcing the caller to retry later or address the constraint. PDBs apply exclusively to **voluntary disruptions** initiated through the Eviction API — they provide **zero protection** against **involuntary disruptions** (a node crashing, a kernel panic, a container OOMKilling, a hardware failure), which bypass the Eviction API entirely and simply happen.

## 2. Why This Matters

- **PDBs are the mechanism that makes voluntary cluster operations safe for stateful, quorum-sensitive, or minimally-replicated workloads.** Without one, a node drain (§109, Part 14) during maintenance could evict every replica of a 3-node etcd-backed application simultaneously if they happen to co-locate, breaking quorum — a PDB with `minAvailable: 2` makes that scenario a rejected eviction instead of an outage.
- **The voluntary-vs-involuntary distinction is the single most tested and most misunderstood PDB concept.** A PDB provides real protection during a `kubectl drain` (§109) or Cluster-Autoscaler-driven scale-down (§38) — both go through the Eviction API — but offers absolutely no protection when a node simply dies or a container crashes; conflating "I have a PDB" with "my workload is protected against any disruption" is a dangerous, false sense of security.
- **PDBs interact directly with the HA design decisions from Part 2.** §15's high-availability control-plane discussion and the general principle of spreading replicas across failure domains only pay off operationally if voluntary maintenance actions are also constrained to respect that spread — a PDB is the enforcement mechanism that turns "we designed for HA" into "maintenance operations can't accidentally violate our HA design."

🔑 **Key Takeaway:** A PodDisruptionBudget bounds how many Pods can be voluntarily evicted at once via the Eviction API (drains, Cluster Autoscaler scale-down) — it enforces nothing against involuntary disruptions like crashes or hardware failure, and confusing the two is the most common and most consequential PDB misunderstanding.

## 3. Prerequisites and Dependencies

Builds directly on §14 (scheduler internals, since PDB-aware eviction interacts with how replicas ended up distributed across nodes) and §15 (high-availability control-plane architecture, the broader HA context PDBs help protect); interacts closely with §109 (Part 14, node drain mechanics) and §38 (Cluster Autoscaler's scale-down path).

## 4. Architecture Diagram

```text
                     Voluntary disruption request arrives via Eviction API
                     (kubectl drain, Cluster Autoscaler scale-down, etc.)
                                        │
                                        ▼
                     ┌───────────────────────────────────────────┐
                     │   Does a PDB match this Pod's labels?     │
                     └───────────────┬───────────────────┬───────┘
                                     │ no                │ yes
                                     ▼                    ▼
                     No constraint applied     ┌───────────────────────────┐
                     (eviction proceeds)       │ Would evicting this Pod   │
                                               │ violate minAvailable /    │
                                               │ maxUnavailable?           │
                                               └──────────┬────────────────┘
                                                          │
                                        ┌─────────────────┴──────────────────┐
                                        │ yes                                │ no
                                        ▼                                    ▼
                             Eviction REJECTED                    Eviction ALLOWED
                             (429 Too Many Requests)               Pod terminates,
                             caller retries later                  replacement scheduled

──────────────────────────────────────────────────────────────────────────────
VOLUNTARY (Eviction API — PDB applies)     INVOLUNTARY (no Eviction API — PDB is IRRELEVANT)
  kubectl drain                              Node hardware failure / kernel panic
  Cluster Autoscaler scale-down (§38)        kubelet crash / container OOMKilled
  Manual kubectl evict / API eviction call   Network partition isolating a node
```

- **The rejection is a signal to the caller to back off and retry, not a permanent block** — `kubectl drain` in particular is designed to retry-and-wait against a `429`, meaning a PDB typically slows a drain down (waiting for a replacement Pod to become Ready elsewhere before continuing) rather than failing it outright.
- **A PDB with `minAvailable` equal to or greater than the workload's total replica count effectively blocks all voluntary eviction of that workload** — a real, sometimes deliberately-used, sometimes accidental configuration worth recognizing on sight.

## 5. Hands-On: Configuring and Testing Pod Disruption Budgets

### 5.1 A `minAvailable` PDB Protecting Quorum

**Purpose:** Guarantee at least 2 of 3 replicas of a quorum-sensitive workload stay available during any voluntary disruption.

**Syntax:** `spec.minAvailable: <int|percentage>` with a `spec.selector` matching the target Pods.

```yaml
# quorum-app-pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: quorum-app-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: quorum-app
```

```bash
$ kubectl apply -f quorum-app-pdb.yaml
poddisruptionbudget.policy/quorum-app-pdb created

$ kubectl get pdb quorum-app-pdb
NAME              MIN AVAILABLE   MAX UNAVAILABLE   ALLOWED DISRUPTIONS   AGE
quorum-app-pdb    2               N/A               1                     5s
```

**Production usage example:** `ALLOWED DISRUPTIONS: 1` is the PDB controller's live computed value — with 3 healthy replicas and `minAvailable: 2`, exactly one can be voluntarily evicted at a time; this number recalculates continuously as replicas become Ready or Unready, and is the first thing to check when a drain appears "stuck."

**Common errors:** Setting `minAvailable` equal to the total replica count (e.g., `minAvailable: 3` on a 3-replica Deployment) makes `ALLOWED DISRUPTIONS` permanently `0`, silently blocking every future voluntary eviction, including legitimate node drains — a frequent, hard-to-diagnose cause of a drain that never completes.

### 5.2 A `maxUnavailable` PDB for a Larger, Loosely-Coupled Fleet

**Purpose:** Allow a bounded percentage of a large stateless fleet to be evicted at once, expressed proportionally rather than as an absolute count.

```yaml
# web-fleet-pdb.yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: web-fleet-pdb
spec:
  maxUnavailable: 20%
  selector:
    matchLabels:
      app: web-fleet
```

```bash
$ kubectl get pdb web-fleet-pdb
NAME             MIN AVAILABLE   MAX UNAVAILABLE   ALLOWED DISRUPTIONS   AGE
web-fleet-pdb    N/A             20%               6                     2m
# 30 replicas total → 20% = 6 may be unavailable simultaneously
```

**Production usage example:** Percentage-based `maxUnavailable` scales automatically as a Deployment's replica count changes (e.g., via HPA, §37) without requiring the PDB itself to be edited — a common pairing for large, horizontally-scaled stateless fleets where an absolute `minAvailable` count would need constant manual adjustment.

**Common errors:** Applying a percentage-based PDB to a very small replica count (e.g., `maxUnavailable: 20%` on 2 replicas) rounds down to `0` allowed disruptions in some Kubernetes versions' rounding behavior — always verify `ALLOWED DISRUPTIONS` directly on small fleets rather than assuming the percentage behaves as expected.

### 5.3 Observing a Drain Respect (and Get Blocked By) a PDB

**Purpose:** Show the practical interaction between `kubectl drain` and a restrictive PDB.

```bash
$ kubectl drain node-3 --ignore-daemonsets
node/node-3 cordoned
evicting pod default/quorum-app-2
error when evicting pods/"quorum-app-2" -n "default" (will retry after 5s): Cannot evict pod as it would violate the pod's disruption budget.

$ kubectl get pdb quorum-app-pdb
NAME              MIN AVAILABLE   MAX UNAVAILABLE   ALLOWED DISRUPTIONS   AGE
quorum-app-pdb    2               N/A               0                     20m
# ALLOWED DISRUPTIONS is 0 — another replica is already down elsewhere
```

**Production usage example:** `kubectl drain`'s automatic retry-with-backoff against a `429` is why a drain can appear to "hang" — it isn't stuck, it's correctly waiting for `ALLOWED DISRUPTIONS` to rise above 0 again (e.g., once a previously-evicted replica becomes Ready on another node), which is the expected, safe behavior rather than a failure.

**Common errors:** Force-deleting the blocked Pod directly (`kubectl delete pod --force --grace-period=0`) to "unstick" a drain bypasses the Eviction API entirely, defeating the PDB's protection and potentially breaking quorum exactly as it was designed to prevent — this should only ever be a deliberate, understood exception, never a routine workaround.

## 6. Production Usage Notes

- **A PDB with zero currently-Ready Pods matching its selector allows any number of evictions** — the disruption budget only meaningfully constrains once at least one Pod is healthy; a fully-down workload has nothing left for a PDB to protect against further disruption.
- **`kubectl drain --disable-eviction`** exists specifically to bypass PDBs entirely by deleting Pods directly instead of evicting them — a genuinely dangerous flag reserved for emergency scenarios (e.g., a node that must be forcibly removed regardless of workload impact), never routine operations.
- **Cluster Autoscaler's scale-down path (§38) checks PDBs before removing a node** exactly the same way `kubectl drain` does — a node hosting Pods that a PDB would block from eviction is simply skipped for scale-down, meaning an overly restrictive PDB can quietly prevent legitimate cost-saving scale-down as a side effect.

## 7. Security Considerations

- A maliciously or mistakenly configured `minAvailable` equal to total replica count can be used (deliberately or accidentally) to block all legitimate node maintenance indefinitely, effectively a denial-of-service against cluster operations teams trying to patch or decommission nodes — PDB configurations warrant the same review scrutiny as RBAC bindings in shared multi-tenant clusters.
- PDBs do not protect against involuntary disruption, meaning any security incident response plan that assumes "the PDB will keep enough replicas up" during, say, a compromised-node isolation event is relying on a guarantee the PDB does not actually provide — isolating a compromised node is an involuntary-disruption-adjacent action outside Eviction API semantics.

## 8. Common Troubleshooting Scenarios

| Symptom                                                      | Likely Cause                                                                     | Resolution Path                                                                                    |
| ------------------------------------------------------------ | -------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------- |
| `kubectl drain` hangs indefinitely on one node               | A PDB's `ALLOWED DISRUPTIONS` is `0` and staying there                           | Check `kubectl get pdb`; investigate why replicas aren't recovering elsewhere (capacity, affinity) |
| Node crashed and workload availability dropped despite a PDB | The disruption was involuntary (crash), which PDBs do not protect against at all | Address via replica count/spread/affinity design, not PDB — PDBs are irrelevant here               |
| PDB shows `minAvailable` met but eviction still rejected     | A second PDB with an overlapping selector also applies and is more restrictive   | Enumerate all PDBs matching the Pod's labels; the most restrictive applicable one governs          |
| Cluster Autoscaler never scales down a specific node         | Pods on that node are protected by a PDB currently at `0` allowed disruptions    | Review whether the PDB is more restrictive than intended; adjust or accept the constraint          |

## 9. Best Practices

- Set `minAvailable`/`maxUnavailable` based on the workload's actual fault-tolerance requirement (e.g., quorum size for a stateful cluster), never as an arbitrary default copied from an unrelated service.
- Verify `ALLOWED DISRUPTIONS` directly with `kubectl get pdb` before and during planned maintenance windows, rather than assuming a configured value behaves as expected — especially on small replica counts with percentage-based bounds.
- Pair every PDB-protected workload with genuine replica spread across nodes/zones (§72, Part 9, topology spread) — a PDB alone doesn't create resilience, it only constrains how aggressively existing resilience can be drawn down at once.

## 10. Common Anti-Patterns / Mistakes

- **Believing a PDB protects against node crashes, kubelet failures, or any other involuntary disruption** — it only ever governs voluntary, Eviction-API-mediated actions.
- **Setting `minAvailable` equal to total replica count**, silently and permanently blocking all future voluntary eviction, including necessary node drains — a frequent root cause of a drain that never completes.
- **Force-deleting Pods to work around a PDB rejection as a routine practice** rather than a deliberate, rare exception, defeating the exact protection the PDB was configured to provide.

## 11. Interview Questions

**🎯 Beginner:** _"What does a PodDisruptionBudget actually protect against?"_
**Model answer:** It protects against voluntary disruptions — actions initiated through the Kubernetes Eviction API, like `kubectl drain` or a cluster autoscaler removing a node — by limiting how many matching Pods can be evicted at the same time, expressed as either a `minAvailable` floor or a `maxUnavailable` ceiling. It does not protect against involuntary disruptions such as a node crashing or a container being OOMKilled, since those never go through the Eviction API at all.
_What the interviewer is probing for:_ Correct grasp of the voluntary/involuntary boundary, the most commonly tested PDB concept.

**🎯 Intermediate:** _"A `kubectl drain` on a node appears to hang indefinitely. How do you diagnose whether a PDB is the cause?"_
**Model answer:** I'd run `kubectl get pdb` across the relevant namespace and check the `ALLOWED DISRUPTIONS` column for any PDB matching the labels of Pods still on that node — a value of `0` strongly suggests the drain is correctly blocked and retrying rather than actually stuck. From there I'd investigate why the budget isn't recovering: are replacement replicas failing to become Ready elsewhere (capacity or affinity issues), or is `minAvailable` set at or above total replica count, which would make `0` a permanent state rather than a temporary one. I'd avoid reaching for `--disable-eviction` or a force-delete unless I've confirmed the constraint is genuinely stuck and understood the consequence of bypassing it.
_What the interviewer is probing for:_ A methodical diagnosis path that respects the PDB's purpose rather than jumping straight to bypassing it.

**🎯 Senior:** _"Why doesn't a PodDisruptionBudget protect a workload during a node hardware failure, and what should be used instead to address that risk?"_
**Model answer:** A PDB only ever intercepts requests made through the Eviction API — that's a deliberate, negotiated request path where the API server can say "not yet." A node hardware failure or kernel panic doesn't go through any API at all; the Pods on that node simply become unreachable, and the node's Pod objects eventually get marked accordingly by the node lifecycle controller (relevant to §13's controller/watch pattern), with no eviction request for a PDB to reject in the first place. Protecting against that class of failure is a resilience/replication design problem, not a disruption-budgeting one: sufficient replica count, spread across failure domains via topology spread constraints or anti-affinity (§72, Part 9), and — for stateful workloads — appropriate storage replication (§57+, Part 8) or application-level quorum tolerance. A PDB is a valuable complement to that design (protecting the resilience you've built from being drawn down too aggressively during planned maintenance) but is not itself a substitute for the underlying replication and spread.
_What the interviewer is probing for:_ Clear architectural separation between availability-by-design (replication, spread) and disruption-budgeting (PDBs), and the ability to explain precisely why the Eviction API boundary matters.

**🎯 Architect:** _"You're setting platform-wide PDB policy for hundreds of tenant workloads with varying replica counts and criticality. What guardrails would you put in place?"_
**Model answer:** I'd start by making a PDB mandatory (via admission policy or CI validation) for any workload above a criticality threshold, specifically to prevent a well-intentioned node drain or Cluster-Autoscaler scale-down from silently taking down more of a service than intended. I'd forbid, via the same validation layer, any `minAvailable` configuration that mathematically equals or exceeds a workload's declared replica count, since that's almost always an accident that permanently blocks voluntary eviction rather than a deliberate choice — and I'd flag it during CI rather than discovering it during an urgent node drain. For high-replica, horizontally-scaled fleets I'd default to percentage-based `maxUnavailable` so the constraint scales automatically with HPA-driven (§37) replica changes without manual PDB edits, while for small, quorum-sensitive stateful workloads I'd require an explicit, reviewed `minAvailable` tied to the actual quorum math (e.g., `minAvailable: 2` for a 3-node quorum system, never left at a copy-pasted default). Finally, I'd make sure platform runbooks are explicit that PDBs provide zero protection against involuntary disruption, so incident response plans don't lean on a guarantee PDBs were never designed to provide.
_What the interviewer is probing for:_ Ability to translate PDB mechanics into governed, validated platform policy that prevents the most common accidental misconfigurations (over-restrictive `minAvailable`) while correctly scoping what PDBs can and cannot be relied upon for.

## 12. Common Misconceptions

1. **"A PDB protects a workload against any kind of disruption."** It only governs voluntary disruptions made through the Eviction API — it provides zero protection against node crashes, kubelet failures, or other involuntary events.
2. **"`minAvailable` and `maxUnavailable` can both be set on the same PDB for tighter control."** A PDB uses exactly one of the two; they express the same constraint from opposite directions and are mutually exclusive on a single object.
3. **"A drain that pauses on a PDB rejection has failed."** `kubectl drain` treats a `429` from the Eviction API as a retry signal, not a failure — it waits and retries, which is the expected, safe behavior, not a stuck or broken state (unless the budget never recovers).
4. **"Setting `minAvailable` as high as possible is always the safest choice."** Setting it equal to or above total replica count blocks all voluntary eviction permanently, which can prevent legitimate, necessary node maintenance rather than making the workload safer.

## 13. 🔑 Key Takeaways

- PDBs bound voluntary disruption only — actions routed through the Eviction API (`kubectl drain`, §109; Cluster Autoscaler scale-down, §38) — and provide no protection against involuntary disruptions like crashes or hardware failure.
- A PDB is configured with exactly one of `minAvailable` or `maxUnavailable`, and its live-computed `ALLOWED DISRUPTIONS` value (visible via `kubectl get pdb`) is the fastest diagnostic signal for a stalled drain.
- `minAvailable` set at or above total replica count silently and permanently blocks all voluntary eviction — a common, hard-to-diagnose misconfiguration.
- Percentage-based `maxUnavailable` scales automatically with HPA-driven (§37) replica count changes, avoiding the need to hand-edit a PDB as fleet size changes.
- PDBs complement, but do not replace, genuine resilience design (replica spread, topology constraints, storage replication) — they constrain how fast existing resilience can be drawn down, not create resilience by themselves.

## 14. Related Concepts & What's Next

§14 and §15 established the scheduling and HA foundations that make replica placement and control-plane resilience meaningful; this section supplied the mechanism that keeps voluntary cluster operations from undermining that resilience. §38's Cluster Autoscaler scale-down path and §109 (Part 14)'s node drain mechanics both consult PDBs identically via the Eviction API. §40 (next, closing Part 5) synthesizes everything from §27 through §39 — Deployments, StatefulSets, DaemonSets, Jobs, CronJobs, HPA, VPA, Cluster Autoscaler, and PDBs — into a single decision framework for choosing the right workload type and the right set of autoscaling/disruption controls to pair with it.

**Next Section:** §40 — `Section-40-Part5-Workload-Choice-Decision-Framework.md`
