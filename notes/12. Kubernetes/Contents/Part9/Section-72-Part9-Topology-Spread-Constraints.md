# Section 72 (Part 9): Topology Spread Constraints

## 1. Definition

**Plain language:** Even after the scheduler decides which nodes have room for your Pods, you often care about _which_ of those candidate nodes gets picked — specifically, you don't want every replica of your Deployment to accidentally land in the same availability zone, or on the same rack, where a single failure could take out your entire application at once. Topology spread constraints let you tell the scheduler exactly how evenly to distribute Pods across whatever failure domains you define.

**Precise definition:** A **topology spread constraint**, set via `spec.topologySpreadConstraints` on a Pod template, instructs the scheduler to distribute Pods matching a given label selector evenly across groups of nodes sharing the same value for a specified **topology key** (a node label such as `topology.kubernetes.io/zone`, `kubernetes.io/hostname`, or any custom label). Each constraint defines a `maxSkew` (the maximum allowed difference in matching-Pod count between the most- and least-populated topology domain), a `topologyKey`, a `whenUnsatisfiable` policy (`DoNotSchedule` to hard-fail placement, or `ScheduleAnyway` to prefer but not require even spread), and a `labelSelector` identifying which Pods count toward the skew calculation. This mechanism operates in the scheduler's filtering (for `DoNotSchedule`) and scoring (for `ScheduleAnyway`) phases, layering on top of — not replacing — the resource-based filtering from §70.

## 2. Why This Matters

- **Topology spread is the modern, more precise successor to Pod anti-affinity for even distribution.** Pod anti-affinity can express "don't co-locate," but topology spread constraints express a quantifiable, tunable evenness guarantee (`maxSkew`) across arbitrary topology domains — zone, region, rack, or any custom label — which is what most real high-availability requirements actually need.
- **A Deployment with correct replica counts can still have terrible fault tolerance without this.** Three replicas that all land in the same availability zone (because nothing constrained them otherwise) provide zero protection against a zone outage, despite looking healthy and "highly available" by replica count alone.
- **`whenUnsatisfiable` is the operational safety valve that determines whether spread is a hard requirement or a soft preference.** `DoNotSchedule` can leave Pods Pending if perfect spread isn't achievable (e.g., during a zone outage), while `ScheduleAnyway` degrades gracefully — choosing correctly between them is a real production trade-off, not a stylistic detail.

🔑 **Key Takeaway:** Topology spread constraints give the scheduler a quantifiable evenness target (`maxSkew`) across any topology domain you define, closing the gap between "enough replicas exist" and "those replicas are actually fault-tolerant against real infrastructure failure domains."

## 3. Prerequisites and Dependencies

Builds on §71 (Priority Classes and Preemption) as the final placement-control mechanism in Part 9's scheduling tour, and assumes familiarity with node labels and the general filtering/scoring pipeline vocabulary established across Part 9, alongside Deployment/ReplicaSet concepts from Part 4.

## 4. Architecture Diagram

```text
              Deployment: 6 replicas, label app=web
              topologySpreadConstraints:
                - maxSkew: 1
                  topologyKey: topology.kubernetes.io/zone
                  whenUnsatisfiable: DoNotSchedule
                  labelSelector: { matchLabels: { app: web } }
                                │
                                ▼
        ┌───────────────────────────────────────────────────┐
        │              Cluster nodes grouped by zone        │
        │                                                   │
        │   zone-a          zone-b          zone-c          │
        │  ┌───────┐       ┌───────┐       ┌───────┐        │
        │  │ node1 │       │ node3 │       │ node5 │        │
        │  │ node2 │       │ node4 │       │ node6 │        │
        │  └───────┘       └───────┘       └───────┘        │
        └───────────────────────────────────────────────────┘
                                │
                                ▼
        Scheduler places Pods so |max_zone_count - min_zone_count| ≤ 1:
              zone-a: 2 Pods    zone-b: 2 Pods    zone-c: 2 Pods
              (skew = 0, well within maxSkew: 1 — balanced deployment)

        If zone-c had no available nodes (outage):
          DoNotSchedule → remaining Pods stay Pending rather than
                           violate maxSkew by overloading zone-a/b
          ScheduleAnyway → remaining Pods schedule into zone-a/b
                           anyway, accepting a temporary imbalance
```

## 5. Hands-On

### 5.1 Spreading Pods Evenly Across Availability Zones

**Purpose:** Guarantee that replicas of a Deployment are distributed across zones with a bounded imbalance, protecting against a single zone outage taking down the whole application.

**Syntax:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: web
spec:
  replicas: 6
  selector:
    matchLabels:
      app: web
  template:
    metadata:
      labels:
        app: web
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: web
      containers:
        - name: web
          image: myregistry/web:2.3.0
```

**Example usage and expected output:**

```bash
$ kubectl get pods -l app=web -o custom-columns=NAME:.metadata.name,NODE:.spec.nodeName
NAME              NODE
web-6f9d8-2kx9p   node1
web-6f9d8-8f2mq   node3
web-6f9d8-9x7lp   node5
web-6f9d8-b2n4t   node2
web-6f9d8-c8v3r   node4
web-6f9d8-d1w9k   node6

$ kubectl get nodes -L topology.kubernetes.io/zone
NAME    STATUS   ZONE
node1   Ready    zone-a
node2   Ready    zone-a
node3   Ready    zone-b
node4   Ready    zone-b
node5   Ready    zone-c
node6   Ready    zone-c
```

**Production usage example:** A checkout service running behind a regional load balancer sets `maxSkew: 1` with `topologyKey: topology.kubernetes.io/zone` across its Deployment, ensuring a single-zone outage removes at most a proportional fraction of capacity rather than a disproportionate chunk that could have accumulated if replicas had drifted unevenly over successive rolling updates.

**Common errors:** Forgetting that `topology.kubernetes.io/zone` must actually be populated as a node label by the cloud provider's cloud-controller-manager (or manually on bare-metal clusters) — on clusters where this label is missing or inconsistent, the constraint silently has no meaningful effect because every node appears to belong to the same (empty) topology domain.

### 5.2 Combining Node and Zone Spread with Multiple Constraints

**Purpose:** Layer two topology spread constraints simultaneously — spreading across zones for regional fault tolerance and across individual nodes for protection against single-node failure within a zone.

**Syntax:**

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: api
spec:
  replicas: 9
  selector:
    matchLabels:
      app: api
  template:
    metadata:
      labels:
        app: api
    spec:
      topologySpreadConstraints:
        - maxSkew: 1
          topologyKey: topology.kubernetes.io/zone
          whenUnsatisfiable: DoNotSchedule
          labelSelector:
            matchLabels:
              app: api
        - maxSkew: 1
          topologyKey: kubernetes.io/hostname
          whenUnsatisfiable: ScheduleAnyway
          labelSelector:
            matchLabels:
              app: api
      containers:
        - name: api
          image: myregistry/api:5.0.1
```

**Example usage and expected output:**

```bash
$ kubectl describe deployment api | grep -A10 "Topology Spread"
Topology Spread Constraints:  topology.kubernetes.io/zone:DoNotSchedule when max skew 1
                               kubernetes.io/hostname:ScheduleAnyway when max skew 1

$ kubectl get pods -l app=api -o wide
# Output shows 9 Pods spread evenly across 3 zones (3 each),
# and within each zone spread across distinct hostnames where
# node capacity allows, best-effort where it doesn't
```

**Production usage example:** A platform team standardizes this two-constraint pattern (`DoNotSchedule` on zone, `ScheduleAnyway` on hostname) across all Tier-1 services — zone spread is treated as a hard regional-availability requirement worth leaving Pods Pending over, while node-level spread is a nice-to-have that shouldn't block scheduling if a particular zone has fewer nodes available than replicas.

**Common errors:** Setting both constraints to `DoNotSchedule` in a cluster with an uneven number of nodes per zone can leave Pods permanently Pending, because satisfying strict per-zone _and_ strict per-node evenness simultaneously may be mathematically impossible given the actual node topology — mixing `DoNotSchedule` and `ScheduleAnyway` across constraints is often the more resilient real-world configuration.

## 6. Production Usage Notes

- Since Kubernetes 1.24, `topologySpreadConstraints` supports a cluster-wide default via `defaultConstraints` in the scheduler's `PodTopologySpread` plugin configuration, letting platform teams apply a baseline zone-spread policy to every Pod without requiring each application team to author it manually.
- `matchLabelKeys` (a newer field, generally available from Kubernetes 1.27+) lets spread calculations automatically account for Pod template hash labels during a rolling update, preventing old and new ReplicaSet revisions from being incorrectly counted together (or apart) during the transition — worth adopting to avoid brief spread miscalculations mid-rollout.
- Topology spread constraints and Pod anti-affinity can be combined, but doing so is rarely necessary — most "spread evenly" requirements are better expressed purely with topology spread's quantifiable `maxSkew`, reserving anti-affinity for genuinely binary co-location rules ("never on the same node as X").

## 7. Security Considerations

- Topology spread constraints have no confidentiality implications directly, but in multi-tenant clusters, a poorly-scoped `labelSelector` could inadvertently count another tenant's Pods toward your own spread calculation if label namespacing isn't enforced, producing confusing and potentially exploitable placement behavior.
- Relying solely on topology spread for availability without also considering node-level isolation (e.g., dedicated node pools per tenant) doesn't provide a security boundary — it's a fault-tolerance mechanism, not a workload isolation mechanism, and shouldn't be conflated with the two.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                  | Likely Cause                                                                                                                | Resolution Path                                                                                                    |
| ------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| Pods stuck `Pending` with "didn't match pod topology spread constraints" | `whenUnsatisfiable: DoNotSchedule` combined with insufficient nodes in some topology domain                                 | Check node distribution per topology key; relax to `ScheduleAnyway` or add capacity to the underrepresented domain |
| Spread constraint appears to have no effect at all                       | Topology key label (e.g., `topology.kubernetes.io/zone`) missing or inconsistent across nodes                               | `kubectl get nodes -L <topologyKey>`; ensure the label is actually populated cluster-wide                          |
| Pods unevenly distributed despite a configured constraint                | `labelSelector` doesn't match the Pods it's meant to count, or multiple unrelated Deployments share a label unintentionally | Verify `labelSelector` precisely targets only the intended Pod set                                                 |
| Rolling update briefly produces skewed distribution                      | Old and new ReplicaSet revisions counted inconsistently during transition                                                   | Adopt `matchLabelKeys` (1.27+) to correctly account for pod-template-hash during rollouts                          |

## 9. Best Practices

- Set `maxSkew: 1` with `topologyKey: topology.kubernetes.io/zone` as a baseline on every multi-replica production Deployment — it's inexpensive to configure and directly protects against a very real, common failure mode.
- Prefer `ScheduleAnyway` for constraints where degraded evenness is acceptable during a partial outage, reserving `DoNotSchedule` only for requirements where imbalance itself is unacceptable even temporarily.
- Adopt `matchLabelKeys` on rollout-sensitive workloads to prevent spread miscalculation during Deployment revisions, especially on clusters running frequent rolling updates.

## 10. Common Anti-Patterns / Mistakes

- **Trusting replica count alone as a proxy for fault tolerance**, without any topology spread constraint ensuring those replicas are actually distributed across independent failure domains.
- **Setting every constraint to `DoNotSchedule`** without modeling whether the cluster's actual node topology can mathematically satisfy all constraints simultaneously, risking permanently Pending Pods.
- **Configuring a topology key that isn't actually populated as a node label**, silently producing a no-op constraint that gives a false sense of protection.

## 11. Interview Questions

**🎯 Beginner:** _"What does `maxSkew` control in a topology spread constraint?"_
**Model answer:** `maxSkew` sets the maximum allowed difference in the count of matching Pods between the most-populated and least-populated topology domain (like an availability zone). A `maxSkew` of 1 means no domain can have more than one extra matching Pod compared to the domain with the fewest.
_What the interviewer is probing for:_ Whether the candidate understands `maxSkew` as a quantifiable balance metric rather than a vague "spread things out" setting.

**🎯 Intermediate:** _"What's the practical difference between `DoNotSchedule` and `ScheduleAnyway`, and when would you choose each?"_
**Model answer:** `DoNotSchedule` makes the constraint a hard filtering requirement — if placing a Pod would violate `maxSkew`, it stays Pending rather than scheduling unevenly. `ScheduleAnyway` treats it as a scoring preference — the scheduler favors nodes that improve balance but will still place the Pod somewhere even if perfect spread isn't achievable. I'd choose `DoNotSchedule` for hard regional-availability requirements where imbalance itself is unacceptable, and `ScheduleAnyway` where I'd rather degrade gracefully (accept temporary imbalance) than have Pods stuck Pending during a partial outage.
_What the interviewer is probing for:_ Understanding the filtering-vs-scoring distinction as it applies specifically to this mechanism, and the operational trade-off between strictness and availability.

**🎯 Senior:** _"During a partial zone outage, several Pods governed by a `DoNotSchedule` zone-spread constraint are stuck Pending even though other zones have plenty of capacity. Walk through the diagnosis and fix."_
**Model answer:** This is expected behavior, not a bug — with `DoNotSchedule`, the scheduler refuses to place additional Pods into the healthy zones if doing so would push `maxSkew` beyond its configured limit relative to the now-unreachable zone, since it can't tell whether the missing zone's nodes are temporarily degraded or permanently gone. I'd confirm via `kubectl describe pod` that the FailedScheduling event cites the topology spread constraint specifically, then make a deliberate operational call: either temporarily patch the Deployment to relax that constraint to `ScheduleAnyway` (accepting the imbalance during the outage) or wait it out if the zone is expected to recover shortly and the remaining capacity in healthy zones is sufficient in the meantime. Long-term, I'd reconsider whether `DoNotSchedule` is really the right choice for this workload given how often zone-level disruptions occur in practice, versus using `ScheduleAnyway` so this exact scenario self-heals without manual intervention next time.
_What the interviewer is probing for:_ Whether the candidate can correctly diagnose expected-but-inconvenient scheduler behavior under partial failure, and reason about the operational trade-off rather than treating the Pending state as unconditionally wrong.

**🎯 Architect:** _"Design the topology spread strategy for a Tier-1 multi-region service running across three cloud availability zones, balancing strict availability guarantees against the reality of partial outages."_
**Model answer:** I'd apply a two-layer constraint set on the Deployment: a zone-level constraint with `maxSkew: 1` and `whenUnsatisfiable: ScheduleAnyway` — treating zone balance as strongly preferred but not something I'd let block scheduling entirely during a genuine zone-level incident — paired with a node-level constraint (`kubernetes.io/hostname`) also on `ScheduleAnyway` to avoid over-concentrating replicas onto a single node within a zone. I'd deliberately choose `ScheduleAnyway` over `DoNotSchedule` at the zone level specifically because a Tier-1 service's worst outcome is being unable to schedule replacement capacity during exactly the kind of event (a zone degradation) that spread constraints exist to protect against — a hard `DoNotSchedule` constraint can perversely make the service less available during the very scenario it's meant to guard against. I'd combine this with a cluster-wide default topology spread policy (via scheduler `defaultConstraints`) as a baseline safety net for every other Tier-2/3 workload that hasn't explicitly configured its own constraints, and adopt `matchLabelKeys` everywhere to keep rolling updates from producing false skew readings. The overarching principle: use spread constraints to bias toward balance under normal conditions, but never let the balance requirement itself become a single point of failure during the abnormal conditions it exists to mitigate.
_What the interviewer is probing for:_ Sophisticated understanding that strict spread enforcement can be self-defeating during real outages, and the ability to design a layered, workload-tier-aware strategy rather than a single blanket policy.

## 12. Common Misconceptions

1. **"Topology spread constraints and Pod anti-affinity solve the same problem interchangeably."** Anti-affinity expresses binary co-location rules; topology spread expresses a quantifiable evenness target (`maxSkew`) across a topology domain — related but distinct tools, with topology spread usually the better fit for "distribute evenly" requirements.
2. **"More replicas automatically means better fault tolerance."** Without a topology spread constraint (or equivalent), replicas can cluster entirely within a single failure domain regardless of count.
3. **"`DoNotSchedule` is always the safer, stricter choice."** During a partial outage, a strict `DoNotSchedule` zone constraint can leave a Tier-1 service unable to schedule replacement capacity at all — sometimes `ScheduleAnyway` is the more resilient real-world choice.
4. **"A topology spread constraint works regardless of whether the topology key is populated on nodes."** If the specified label isn't actually set consistently across nodes, the constraint silently becomes a no-op rather than producing an error.

## 13. 🔑 Key Takeaways

- Topology spread constraints distribute Pods evenly across any topology domain (zone, node, custom label) using a quantifiable `maxSkew`, layered on top of resource-based filtering (§70).
- `DoNotSchedule` enforces spread as a hard filtering requirement (Pods may stay Pending); `ScheduleAnyway` treats it as a scoring preference that degrades gracefully.
- Replica count alone says nothing about fault tolerance — topology spread constraints are what actually guarantee distribution across independent failure domains.
- The topology key must be a genuinely populated node label for the constraint to have any real effect; missing labels silently produce a no-op.
- For Tier-1 services, `ScheduleAnyway` at the zone level is often more resilient than `DoNotSchedule`, since strict enforcement can block scheduling exactly during the outage scenario it's meant to protect against.

## 14. Related Concepts & What's Next

This section closes Part 9's scheduling tour, building on §71's priority/preemption mechanics and §70's resource-based filtering to complete the full picture of how the scheduler decides not just _whether_ a Pod can be placed, but _where_ among its viable candidates it ends up. Part 10 shifts from placement to security and access control, beginning with how Kubernetes authenticates the users, ServiceAccounts, and certificates that create and manage every object discussed so far.

**Next Section:** §73 — `Section-73-Part10-Authentication-Users-ServiceAccounts-X509-OIDC.md`
