# Section 67 (Part 9): Pod Affinity and Anti-Affinity

## 1. Definition

**Plain language:** Node affinity (§66) answers "which nodes qualify?" based on node labels. Pod affinity and anti-affinity answer a different question entirely: "which nodes qualify, based on what other Pods are already running there?" Affinity pulls a Pod toward nodes running certain other Pods; anti-affinity pushes it away from them.

**Precise definition:** Pod affinity (`spec.affinity.podAffinity`) and Pod anti-affinity (`spec.affinity.podAntiAffinity`) let a Pod's placement depend on the labels of **other Pods** already scheduled within a given **topology domain**, defined by `topologyKey` (a node label such as `topology.kubernetes.io/zone` or `kubernetes.io/hostname`). Each rule specifies a `labelSelector` matching target Pods, a `topologyKey` defining what "co-located" means, and optionally a `namespaces`/`namespaceSelector` scope. Like node affinity, both come in `requiredDuringSchedulingIgnoredDuringExecution` (hard, Filter-phase) and `preferredDuringSchedulingIgnoredDuringExecution` (soft, Score-phase, weighted) forms, implemented by the `InterPodAffinity` plugin (§65). Affinity says "schedule me where matching Pods already are"; anti-affinity says "schedule me away from where matching Pods already are" — the same mechanism, inverted intent.

## 2. Why This Matters

- **Pod anti-affinity is the primary mechanism for spreading replicas across failure domains** — a Deployment's three replicas landing on the same node defeats the purpose of running three replicas at all; required anti-affinity keyed on `kubernetes.io/hostname` (or `topology.kubernetes.io/zone` for zone-level resilience) is the standard fix, directly relevant to CKA's high-availability workload design expectations.
- **Pod affinity co-locates genuinely interdependent workloads** — a cache-heavy application and its local cache sidecar-adjacent Pod, or a latency-sensitive pair, benefit from being scheduled in the same zone or even the same node, which affinity expresses declaratively instead of relying on luck.
- **`topologyKey` is the single most consequential and most-forgotten field** — omitting or mis-choosing it silently changes the entire meaning of a rule (node-level vs. zone-level vs. region-level co-location/anti-co-location), and is a frequent source of "why didn't this spread my Pods the way I expected" incidents.

🔑 **Key Takeaway:** Pod affinity/anti-affinity extend the same required/preferred hard/soft model from §66 to inter-Pod relationships, with `topologyKey` defining the granularity of "together" — get `topologyKey` wrong and the rule silently means something other than intended.

## 3. Prerequisites and Dependencies

Builds directly on §66 (node affinity's required/preferred, hard/soft model, which Pod affinity mirrors exactly) and §65 (the `InterPodAffinity` plugin operating within the same Filter/Score framework). Also assumes label/selector fundamentals from §31 and topology label conventions (`topology.kubernetes.io/zone`, `kubernetes.io/hostname`) introduced across Part 2/Part 7.

## 4. Architecture Diagram: Pod Affinity/Anti-Affinity Evaluation

```text
   New Pod with spec.affinity.podAntiAffinity:
     requiredDuringSchedulingIgnoredDuringExecution:
       - labelSelector: { matchLabels: { app: web } }
         topologyKey: kubernetes.io/hostname

                              │
                              ▼
        For each candidate node, find its topology value
        for the given topologyKey (here: the node's own
        hostname — i.e., topology domain = single node)
                              │
                              ▼
        Does ANY existing Pod matching the labelSelector
        already sit in that SAME topology domain?
                              │
                 ┌────────────┴─────────────┐
                 ▼                          ▼
               YES                            NO
        (anti-affinity violated)      (anti-affinity satisfied)
        node ELIMINATED               node remains feasible
        (required = Filter phase)

   ── Changing topologyKey changes what "same domain" means ──

   topologyKey: kubernetes.io/hostname        → per-node granularity
   topologyKey: topology.kubernetes.io/zone   → per-zone granularity
   topologyKey: topology.kubernetes.io/region → per-region granularity

   Same labelSelector + different topologyKey = different outcome:
   hostname-scoped anti-affinity only prevents co-location on the
   SAME node; zone-scoped anti-affinity prevents co-location
   anywhere in the SAME zone, which is a much stronger spread.
```

- **`preferredDuringSchedulingIgnoredDuringExecution` follows the identical weighted-scoring model as node affinity** — a soft anti-affinity preference nudges the scheduler toward spreading Pods but never blocks placement if spreading isn't achievable.
- **Pod affinity/anti-affinity rules are evaluated against Pods that already exist at scheduling time** — they are not a live, continuously-enforced invariant; a Pod satisfying anti-affinity at scheduling time is never rechecked as other Pods are later added (`IgnoredDuringExecution` applies here exactly as it does for node affinity).

## 5. Hands-On: Co-locating and Spreading Workloads

### 5.1 Required Pod Anti-Affinity: Spreading Replicas Across Nodes

**Purpose:** Guarantee that no two replicas of a Deployment ever land on the same node, using a hard constraint.

**Syntax:** `spec.affinity.podAntiAffinity.requiredDuringSchedulingIgnoredDuringExecution[].{labelSelector, topologyKey}`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 3
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      affinity:
        podAntiAffinity:
          requiredDuringSchedulingIgnoredDuringExecution:
            - labelSelector:
                matchExpressions:
                  - key: app
                    operator: In
                    values:
                      - web
              topologyKey: kubernetes.io/hostname
      containers:
        - name: web
          image: myregistry/web:3.2.0
```

**Production usage example:** A customer-facing web tier uses this exact pattern so a single node failure can never take down more than one replica — a hard guarantee that required anti-affinity provides, at the explicit cost that the Deployment cannot scale beyond the number of distinct nodes available.

**Common errors:** Setting `replicas` higher than the number of nodes in the cluster while using required (not preferred) hostname-scoped anti-affinity — the excess replicas will sit permanently `Pending` since no node can satisfy the constraint, a frequent surprise during cluster scale-down or in small clusters.

### 5.2 Preferred Pod Anti-Affinity: Best-Effort Zone Spread

**Purpose:** Encourage spreading across zones for resilience without risking unschedulable Pods if the ideal spread isn't achievable.

**Syntax:** `spec.affinity.podAntiAffinity.preferredDuringSchedulingIgnoredDuringExecution[].{weight, podAffinityTerm}`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 5
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      affinity:
        podAntiAffinity:
          preferredDuringSchedulingIgnoredDuringExecution:
            - weight: 100
              podAffinityTerm:
                labelSelector:
                  matchExpressions:
                    - key: app
                      operator: In
                      values:
                        - api
                topologyKey: topology.kubernetes.io/zone
      containers:
        - name: api
          image: myregistry/api:1.9.0
```

**Production usage example:** With 5 replicas across 3 zones, preferred zone-scoped anti-affinity produces the best achievable spread (roughly 2-2-1) rather than leaving 2 replicas permanently `Pending` the way a required constraint would once each zone already holds at least one replica — this is the standard pattern once replica count exceeds the number of topology domains.

**Common errors:** Choosing `topologyKey: topology.kubernetes.io/zone` when hostname-level spread was actually intended (or vice versa) — always state the failure domain being protected against explicitly (a single node dying vs. a whole zone going dark) before picking `topologyKey`, since the two produce very different placement outcomes from identical `labelSelector` values.

### 5.3 Pod Affinity: Co-locating Interdependent Workloads

**Purpose:** Pull a Pod toward nodes already running a related workload, for latency or data-locality reasons.

**Syntax:** `spec.affinity.podAffinity.requiredDuringSchedulingIgnoredDuringExecution[].{labelSelector, topologyKey}`

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: report-generator
  labels:
    app: report-generator
spec:
  affinity:
    podAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        - labelSelector:
            matchExpressions:
              - key: app
                operator: In
                values:
                  - data-cache
          topologyKey: topology.kubernetes.io/zone
  containers:
    - name: report-generator
      image: myregistry/report-generator:1.0.0
```

**Production usage example:** A batch reporting job that reads heavily from an in-cluster data cache uses zone-scoped required affinity to guarantee it never runs in a zone lacking a cache instance, avoiding cross-zone network latency and egress cost on every read.

**Common errors:** Using required Pod affinity referencing a workload that might not exist yet in any zone (e.g., during initial cluster bring-up before the cache Deployment has scheduled) — the dependent Pod will sit `Pending` indefinitely until at least one matching Pod exists somewhere satisfying the topology constraint; sequencing deployment order matters when required Pod affinity is involved.

## 6. Production Usage Notes

- **Pod anti-affinity has a real, documented performance cost at scale** — the `InterPodAffinity` plugin's evaluation grows more expensive as cluster size and Pod count grow, since it must inspect other Pods' labels across the relevant topology domain for every scheduling attempt; extremely large clusters sometimes need `preferred` over `required` partly for this reason, not resilience alone.
- **Pairing `topologySpreadConstraints` (§72) with Pod anti-affinity is common but can be redundant or conflicting** — most modern spread requirements are better served by dedicated topology spread constraints, which offer more precise `maxSkew` control; reserve Pod anti-affinity for cases genuinely about "away from this specific other workload" rather than general even-spreading.
- **Required Pod affinity introduces a scheduling-order dependency** between workloads that didn't otherwise need one — deploying the "target" workload (the one being affinitized toward) before the dependent workload avoids unnecessary `Pending` states during bring-up.

## 7. Security Considerations

- Pod affinity/anti-affinity rules can reference Pods across namespaces via `namespaces` or `namespaceSelector` — an overly broad `namespaceSelector` in a multi-tenant cluster could leak information about what workloads exist in other tenants' namespaces (their labels are visible to the scheduling decision even if the Pods themselves aren't), a subtle multi-tenancy consideration when designing shared-cluster affinity policy.
- Anti-affinity is not a security isolation mechanism by itself — it changes placement preference, not runtime access; regulated workloads requiring genuine isolation still need taints/tolerations (§68) or dedicated node pools, not anti-affinity alone.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                        | Cause                                                                                                   | Fix                                                                                                                |
| ------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Deployment replicas stuck `Pending` once replica count exceeds node/zone count | Required anti-affinity with a `topologyKey` too coarse for the available topology domains               | Switch to preferred anti-affinity, or add more nodes/zones matching the topology granularity                       |
| Pods spread across zones but not evenly                                        | Preferred anti-affinity only nudges scoring; other scoring plugins or existing imbalance dominate       | Consider `topologySpreadConstraints` (§72) for precise `maxSkew` control instead of relying on anti-affinity alone |
| New Pod with required Pod affinity stuck `Pending` on a fresh cluster          | No Pod matching the referenced `labelSelector` exists yet in any qualifying topology domain             | Deploy the target workload first, or relax to preferred affinity if strict ordering isn't acceptable               |
| Anti-affinity rule has no visible effect                                       | Wrong `topologyKey` for the intended failure domain (e.g., zone-scoped when hostname-scoped was needed) | Explicitly restate the failure domain being protected against and match `topologyKey` to it                        |

## 9. Best Practices

- Default to required, hostname-scoped anti-affinity for replica spreading on any workload where a single node failure taking out multiple replicas would be unacceptable, and switch to preferred only once replica count is known to exceed available nodes.
- Always state the intended failure domain in plain language before writing `topologyKey`, since it is the field most likely to silently produce the wrong outcome.
- Prefer `topologySpreadConstraints` (§72) over Pod anti-affinity when the goal is general even-spreading rather than avoiding a specific other workload — they're purpose-built for that case with tighter skew control.

## 10. Common Anti-Patterns / Mistakes

- **Using required Pod anti-affinity with `replicas` set higher than the cluster's node count**, guaranteeing a subset of replicas will be permanently unschedulable.
- **Choosing `topologyKey` casually without stating the actual failure domain being protected against**, producing spread behavior that doesn't match the resilience goal.
- **Layering Pod anti-affinity and topology spread constraints redundantly for the same general-spreading goal** instead of picking the tool purpose-built for it (`topologySpreadConstraints`, §72).

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between node affinity and Pod affinity?"_
**Model answer:** Node affinity matches a Pod against node labels directly — "run me on a node with this label." Pod affinity/anti-affinity instead matches against the labels of other Pods already running within a defined topology domain — "run me near (or away from) nodes that already have Pods matching this selector." Both support the same required/preferred hard/soft distinction, but the thing being matched against is fundamentally different: node characteristics versus other workloads' placement.
_What the interviewer is probing for:_ Clear separation of "matching nodes" from "matching based on co-located Pods," since the two are often conflated by name alone.

**🎯 Intermediate:** _"You set required Pod anti-affinity with `topologyKey: kubernetes.io/hostname` for a Deployment with 5 replicas on a 3-node cluster. What happens?"_
**Model answer:** The first 3 replicas schedule successfully, one per node, since each node satisfies the constraint (no other matching Pod on that same node yet). The remaining 2 replicas will stay permanently `Pending` — every node in the cluster already has a matching Pod, so the required, hostname-scoped constraint eliminates all 3 nodes for each additional replica, and there's no fourth node available to absorb them. This is expected, correct behavior for a hard constraint, not a bug — the fix is either more nodes, fewer replicas, or switching that specific rule to preferred.
_What the interviewer is probing for:_ Ability to reason precisely about required constraints under resource/topology exhaustion rather than assuming the scheduler will "figure something out."

**🎯 Senior:** _"Why can Pod anti-affinity become a scheduler performance concern at scale, and how would you mitigate it?"_
**Model answer:** The `InterPodAffinity` plugin has to inspect the labels of other Pods within the relevant topology domain for every scheduling attempt involving an affinity/anti-affinity rule, which scales with cluster size and Pod density rather than being a constant-time check like a node label match. On very large clusters with many Pods carrying affinity rules, this can measurably slow scheduling throughput. Mitigations include preferring `preferred` over `required` where resilience requirements allow it (since preferred terms can be evaluated more cheaply and don't require exhaustive elimination), narrowing `labelSelector` scope as tightly as possible, and considering whether `topologySpreadConstraints` (§72) — which are designed with this cost in mind — can replace a general-spreading anti-affinity rule entirely.
_What the interviewer is probing for:_ Awareness that affinity mechanisms have a real computational cost profile, not just a functional one, and practical familiarity with the alternatives available to control it.

**🎯 Architect:** _"Design the affinity strategy for a multi-tier application: a stateless API tier, a stateful cache tier, and a batch analytics tier that reads from the cache. Resilience and data-locality both matter."_
**Model answer:** The API tier gets required, hostname-scoped Pod anti-affinity against itself, guaranteeing no single node failure removes more than one replica — a standard resilience pattern with no data-locality concern to trade off. The cache tier, being stateful (likely a StatefulSet, §33), also gets required anti-affinity against itself for the same reason, plus possibly zone-scoped anti-affinity if the cluster spans zones and inter-zone cache-instance loss should be tolerated independently. The batch analytics tier gets required Pod affinity toward the cache tier's label, scoped at the zone level (not hostname — co-locating on the exact same node isn't necessary for the latency win and would over-constrain scheduling), so batch jobs always read from an in-zone cache instance rather than paying cross-zone latency and egress cost; I'd deploy the cache tier before enabling this required affinity on the batch tier to avoid a bring-up ordering deadlock, or use preferred affinity if analytics jobs can tolerate degraded performance during initial rollout. I'd deliberately avoid combining all of this with additional general-spreading anti-affinity rules where topology spread constraints (§72) would express the same intent with clearer skew semantics.
_What the interviewer is probing for:_ Ability to apply distinct affinity strategies per tier based on that tier's actual resilience and locality requirements, rather than one blanket policy, plus awareness of bring-up ordering and tool overlap concerns.

## 12. Common Misconceptions

1. **"Pod anti-affinity guarantees even distribution across all nodes."** Required anti-affinity only guarantees no two matching Pods share the same topology domain — it says nothing about even load distribution otherwise; `topologySpreadConstraints` (§72) is the purpose-built tool for genuine even spreading.
2. **"topologyKey is a minor cosmetic detail."** It defines the entire granularity of what "together" or "apart" means — the same `labelSelector` with a different `topologyKey` produces a materially different scheduling outcome.
3. **"Pod affinity/anti-affinity continuously enforces its rule as the cluster changes."** Like node affinity, it's `IgnoredDuringExecution` — evaluated once at scheduling time; Pods already running are never rechecked or moved as other Pods come and go.
4. **"Required Pod affinity toward a workload that doesn't exist yet will just wait patiently and succeed once it appears."** It leaves the dependent Pod `Pending` until a qualifying Pod exists in a matching topology domain — deployment ordering matters, and there's no automatic retry-and-succeed guarantee beyond the scheduler's normal watch-driven re-evaluation.

## 13. 🔑 Key Takeaways

- Pod affinity/anti-affinity extend node affinity's required/preferred, hard/soft model to matching against other Pods' labels within a `topologyKey`-defined domain, rather than matching node labels directly.
- `topologyKey` determines the granularity of "together" (node, zone, region) and is the field most likely to silently produce unexpected results if chosen without first stating the intended failure domain in plain language.
- Required anti-affinity is a hard guarantee that can leave excess replicas `Pending` once matching Pods already occupy every qualifying topology domain; preferred anti-affinity degrades gracefully instead.
- Pod affinity/anti-affinity carry a real scheduler performance cost at scale via the `InterPodAffinity` plugin, distinct from their functional behavior.
- `topologySpreadConstraints` (§72) is often the better-suited tool for general even-spreading goals, leaving Pod anti-affinity for cases specifically about avoiding co-location with a particular other workload.

## 14. Related Concepts & What's Next

§66 established the required/preferred, hard/soft model and `topologyKey`-adjacent topology label conventions this section builds directly on. §65's `InterPodAffinity` plugin is the mechanism underlying everything here. §31 covers the label/selector fundamentals assumed throughout. §72 (topology spread constraints) is the more precise alternative referenced repeatedly above for general-spreading goals. §68 next covers taints and tolerations — a node-side exclusion mechanism that, unlike affinity, can actively repel Pods regardless of what they request, and is frequently combined with affinity for genuine workload isolation.

**Next Section:** §68 — `Section-68-Part9-Taints-Tolerations.md`
