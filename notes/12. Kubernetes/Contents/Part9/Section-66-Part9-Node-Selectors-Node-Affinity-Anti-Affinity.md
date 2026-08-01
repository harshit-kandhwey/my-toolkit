# Section 66 (Part 9): Node Selectors and Node Affinity/Anti-Affinity

## 1. Definition

**Plain language:** `nodeSelector` is the blunt instrument for saying "only run this Pod on a node with this exact label." Node affinity is the same idea with sharper tools: it can express "must" (hard) or "would prefer" (soft) constraints, match on multiple values and operators, and even weight several preferences against each other.

**Precise definition:** `nodeSelector` is a simple `spec.nodeSelector` map of key-value pairs, evaluated in the scheduler's `Filter` phase (§65) as an implicit AND of exact-match label requirements — a node missing any key or having a mismatched value is eliminated outright. **Node affinity** (`spec.affinity.nodeAffinity`) generalizes this via the `NodeAffinity` plugin, offering `requiredDuringSchedulingIgnoredDuringExecution` (a hard filtering constraint supporting `In`, `NotIn`, `Exists`, `DoesNotExist`, `Gt`, `Lt` operators across multiple `matchExpressions`) and `preferredDuringSchedulingIgnoredDuringExecution` (a soft, weighted scoring-phase preference with a `weight` from 1–100 per term). **Node anti-affinity** is not a separate field — it is node affinity expressed with `NotIn`/`DoesNotExist` operators to exclude rather than include matching nodes. The `IgnoredDuringExecution` suffix on both forms means Kubernetes never re-evaluates or evicts a running Pod if the node's labels change after scheduling — affinity is a placement-time decision only.

## 2. Why This Matters

- **`nodeSelector` and node affinity solve the same problem at two different precision levels**, and choosing the wrong one is a recurring exam and production mistake — §65 already flagged that required affinity is a `Filter`-phase mechanism and preferred affinity is a `Score`-phase mechanism; this section operationalizes that distinction with real syntax.
- **Multi-value and operator-based matching (`In`, `NotIn`, `Exists`) is impossible with `nodeSelector` alone** — any requirement like "run on a node in zone `us-east-1a` OR `us-east-1b`" requires node affinity's `matchExpressions`, a common trigger for migrating an existing `nodeSelector`-based manifest.
- **`IgnoredDuringExecution` is a frequent source of production surprise** — teams often assume a node's changing labels will trigger a live Pod to be rescheduled or evicted, when in fact affinity is checked only once, at scheduling time; understanding this prevents false expectations about self-healing label-driven placement.

🔑 **Key Takeaway:** `nodeSelector` is a legacy-simple hard match; node affinity replaces it with a strictly more expressive syntax offering both hard (`required...`) and soft (`preferred...`) forms — and neither form re-evaluates once a Pod is already running.

## 3. Prerequisites and Dependencies

Builds directly on §65, which established that `Filter` plugins hard-eliminate nodes while `Score` plugins produce weighted rankings — node affinity is the concrete mechanism exercising both extension points via a single field. Also assumes familiarity with Pod spec structure from §24 and label/selector mechanics from §31.

## 4. Architecture Diagram: nodeSelector vs. Node Affinity Evaluation Paths

```text
                     spec.nodeSelector: { disktype: ssd }
                                    │
                                    ▼
                     ┌─────────────────────────────────┐
                     │   Filter phase only             │
                     │   Exact-match AND of all keys   │
                     │   Any mismatch → node eliminated│
                     └─────────────────────────────────┘


          spec.affinity.nodeAffinity
                    │
       ┌────────────┴─────────────────────────────┐
       ▼                                          ▼
requiredDuringScheduling               preferredDuringScheduling
IgnoredDuringExecution                 IgnoredDuringExecution
       │                                            │
       ▼                                            ▼
┌─────────────────────────┐          ┌─────────────────────────────────┐
│  FILTER phase           │          │  SCORE phase                    │
│  matchExpressions must  │          │  Each term has a weight (1-100) │
│  ALL be satisfied for a │          │  Nodes satisfying higher-weight │
│  node to survive        │          │  terms score higher; nodes      │
│  (any one false → node  │          │  satisfying none still survive  │
│  eliminated entirely)   │          │  filtering — this is a          │
│                         │          │  preference, never a veto       │
└─────────────────────────┘          └─────────────────────────────────┘

  Both forms: "IgnoredDuringExecution" = checked ONCE at scheduling
  time only. If node labels change after the Pod is Running, the
  Pod is NOT re-evaluated, rescheduled, or evicted as a result.
```

- **Required and preferred terms can coexist** in the same `nodeAffinity` block — a Pod can have a hard zone requirement and a soft preference for a specific instance type within that zone simultaneously.
- **Multiple `matchExpressions` within one `nodeSelectorTerms` entry are ANDed; multiple `nodeSelectorTerms` entries are ORed** — this OR-of-ANDs structure is what enables "zone A OR zone B" logic impossible with plain `nodeSelector`.

## 5. Hands-On: From nodeSelector to Full Node Affinity

### 5.1 Basic nodeSelector (the Simple Case)

**Purpose:** Pin a Pod to nodes carrying an exact label, using the simplest possible mechanism.

**Syntax:** `spec.nodeSelector: { <key>: <value> }`

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: ssd-cache
spec:
  nodeSelector:
    disktype: ssd
  containers:
    - name: cache
      image: redis:7.2
```

**Production usage example:** A team with exactly two node label conventions (`disktype=ssd` vs. `disktype=hdd`) uses plain `nodeSelector` for a latency-sensitive cache workload — the requirement is genuinely a single exact match, so reaching for the more verbose node affinity syntax would add no value.

**Common errors:** Typo-ing the label key or value silently produces a permanently `Pending` Pod with no hint beyond the generic `FailedScheduling` Event — always cross-check `kubectl get nodes --show-labels` against the exact string used in `nodeSelector` before assuming a deeper scheduling bug.

### 5.2 Required Node Affinity with Multiple Operators

**Purpose:** Express a hard constraint that plain `nodeSelector` cannot: multiple acceptable values, or existence checks rather than exact value matches.

**Syntax:** `spec.affinity.nodeAffinity.requiredDuringSchedulingIgnoredDuringExecution.nodeSelectorTerms[].matchExpressions[]`

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: multi-zone-app
spec:
  affinity:
    nodeAffinity:
      requiredDuringSchedulingIgnoredDuringExecution:
        nodeSelectorTerms:
          - matchExpressions:
              - key: topology.kubernetes.io/zone
                operator: In
                values:
                  - us-east-1a
                  - us-east-1b
              - key: node-role.kubernetes.io/control-plane
                operator: DoesNotExist
  containers:
    - name: app
      image: myregistry/app:2.1.0
```

**Production usage example:** A stateless web tier explicitly excludes control-plane nodes (`DoesNotExist` on the control-plane role label) while accepting either of two approved availability zones — expressing both constraints in a single required block that plain `nodeSelector` has no syntax for at all.

**Common errors:** Nesting a second `matchExpressions` entry inside the same `nodeSelectorTerms` list item when an OR relationship (not AND) was intended — remember that expressions inside one `nodeSelectorTerms` entry are ANDed together, while separate entries in the `nodeSelectorTerms` list are ORed; the fix above intentionally uses AND semantics for a genuinely required combination.

### 5.3 Preferred Node Affinity with Weighted Terms

**Purpose:** Express a soft preference that influences scoring without ever blocking placement outright.

**Syntax:** `spec.affinity.nodeAffinity.preferredDuringSchedulingIgnoredDuringExecution[].weight` and `.preference`

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: cost-aware-app
spec:
  affinity:
    nodeAffinity:
      preferredDuringSchedulingIgnoredDuringExecution:
        - weight: 80
          preference:
            matchExpressions:
              - key: node-lifecycle
                operator: In
                values:
                  - spot
        - weight: 20
          preference:
            matchExpressions:
              - key: instance-type
                operator: In
                values:
                  - m5.large
  containers:
    - name: app
      image: myregistry/app:2.1.0
```

**Production usage example:** A cost-optimization initiative weights a preference for spot-lifecycle nodes heavily (80) over a specific instance type (20), so the scheduler favors cheaper capacity when available but still schedules successfully on on-demand nodes during a spot capacity shortage rather than leaving the Pod `Pending`.

**Common errors:** Assuming a `preferredDuringSchedulingIgnoredDuringExecution` term with a high weight functions as a near-requirement — under sufficient scheduling pressure a Pod can and will land on a node satisfying none of its preferred terms, since preferences only ever influence relative ranking among already-feasible nodes and can never eliminate a node from consideration.

## 6. Production Usage Notes

- **Prefer required affinity only for genuine hard constraints** (compliance zone boundaries, architecture-specific nodes for `arm64` vs. `amd64` workloads) — overusing required affinity for what are really soft preferences risks Pods going permanently `Pending` when the "ideal" node type is temporarily unavailable.
- **`nodeSelector` remains fully supported and is not deprecated** — for genuinely simple single-label matches it is more readable than the equivalent node affinity block, and there is no operational reason to migrate a working `nodeSelector` Pod spec purely for its own sake.
- **`Exists`/`DoesNotExist` operators are commonly used for taint-adjacent exclusions** (e.g., excluding nodes carrying a `dedicated=gpu` label from general-purpose workloads) even when no corresponding taint exists — affinity and taints/tolerations (§68) are complementary, not redundant, mechanisms.

## 7. Security Considerations

- Node affinity governs placement only, not runtime permissions — a Pod correctly steered onto a compliant node via required affinity still needs SecurityContext hardening (§45) and Pod Security Admission (Part 10) to actually behave safely once running there.
- Labels used in affinity rules are mutable by anyone with node-update RBAC permission — a compromised or over-privileged actor able to relabel nodes could subvert intended placement boundaries; restricting `nodes` update/patch RBAC verbs is a relevant hardening step (Part 10) when affinity is load-bearing for compliance.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                  | Cause                                                                                                          | Fix                                                                                                                                          |
| ---------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Pod `Pending`, Event references node affinity/selector                                   | Required affinity or `nodeSelector` matched zero nodes                                                         | Run `kubectl get nodes --show-labels` and diff against the exact keys/values/operators used                                                  |
| Pod ignores an apparent preference and lands elsewhere                                   | Preferred affinity is a soft signal, not a guarantee; another scoring plugin or higher-weighted term dominated | Confirm this is expected behavior; raise the term's weight only if the preference is genuinely more important than competing scoring factors |
| Node relabeled but running Pods didn't move                                              | `IgnoredDuringExecution` means affinity is checked once at scheduling time only                                | This is expected; deliberately delete/recreate the Pod if re-evaluation against new labels is actually desired                               |
| Required affinity with multiple `matchExpressions` behaves like AND when OR was intended | Expressions placed inside one `nodeSelectorTerms` entry instead of separate entries                            | Split into multiple `nodeSelectorTerms` list items for OR semantics                                                                          |

## 9. Best Practices

- Reserve `requiredDuringSchedulingIgnoredDuringExecution` for constraints that are truly non-negotiable, and express everything else as `preferredDuringSchedulingIgnoredDuringExecution` so the cluster degrades gracefully under pressure instead of leaving Pods unschedulable.
- Keep `nodeSelector` for simple single-key matches and reach for node affinity only when multi-value or operator-based logic is genuinely needed — don't migrate working simple cases purely for syntax uniformity.
- Document why each required affinity term exists (compliance, architecture, hardware) so future maintainers don't loosen a hard constraint that was actually load-bearing.

## 10. Common Anti-Patterns / Mistakes

- **Using required affinity for what is really a soft cost or performance preference**, causing Pods to go permanently `Pending` during a capacity shortage that a soft preference would have gracefully absorbed.
- **Expecting `IgnoredDuringExecution` semantics to re-evaluate placement live** when a node's labels change, then being surprised that a running Pod stays put.
- **Writing multiple `matchExpressions` inside a single `nodeSelectorTerms` entry expecting OR logic**, when the actual semantics are AND-within-entry, OR-across-entries.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between `nodeSelector` and node affinity?"_
**Model answer:** `nodeSelector` is a simple exact-match label filter with implicit AND across keys, with no soft/hard distinction — a mismatch always eliminates the node. Node affinity generalizes this: `requiredDuringSchedulingIgnoredDuringExecution` is the hard-match equivalent with richer operators (`In`, `NotIn`, `Exists`, `Gt`, `Lt`), while `preferredDuringSchedulingIgnoredDuringExecution` adds a soft, weighted preference that influences the scoring phase without ever blocking placement.
_What the interviewer is probing for:_ Clear grasp that node affinity is a strict superset of `nodeSelector`'s capability, not an unrelated mechanism.

**🎯 Intermediate:** _"A Pod has a required node affinity term for `zone in [us-east-1a, us-east-1b]`. Explain exactly what happens if a third zone, us-east-1c, also has capacity."_
**Model answer:** The Pod will never schedule to `us-east-1c` regardless of that zone's available capacity — required affinity is evaluated in the Filter phase, and any node in a zone not listed in the `values` array is eliminated outright before scoring ever runs. This holds even under resource pressure in the two permitted zones; the Pod would rather stay `Pending` than schedule to a technically-capable but non-matching zone, which is exactly why required constraints should be reserved for genuine hard requirements.
_What the interviewer is probing for:_ Understanding that required affinity is absolute and unaffected by resource pressure elsewhere — a common point of confusion with newer engineers who expect some fallback behavior.

**🎯 Senior:** _"You have a workload that should strongly prefer GPU-labeled nodes but must still schedule (in degraded form) if none are available. How do you express this, and why not use required affinity?"_
**Model answer:** I'd use `preferredDuringSchedulingIgnoredDuringExecution` with a high weight (e.g., 90-100) matching the GPU node label, not required affinity. Required affinity would leave the Pod permanently `Pending` the moment GPU nodes are fully occupied or temporarily unavailable, which contradicts the stated requirement that the workload must still schedule in a degraded form. A high-weight preferred term achieves the desired bias — the scheduler will strongly favor GPU nodes when available — while still allowing scheduling onto non-GPU nodes as a fallback, trading ideal placement for guaranteed availability exactly as the requirement specifies.
_What the interviewer is probing for:_ Correctly mapping a "strong preference, not absolute requirement" business need onto the soft-affinity mechanism rather than defaulting to required affinity out of habit.

**🎯 Architect:** _"Design a node affinity strategy for a platform running both regulated (must stay in a specific compliance zone) and general-purpose workloads on the same cluster, while also optimizing general-purpose placement for cost."_
**Model answer:** For regulated workloads I'd use `requiredDuringSchedulingIgnoredDuringExecution` matching a compliance-zone label as a genuine hard boundary, likely combined with taints/tolerations (§68) on the compliance-zone nodes themselves so non-regulated workloads can't accidentally land there either — affinity alone only controls what regulated Pods can select, not what other Pods are excluded from selecting, so a taint provides the complementary exclusion. For general-purpose workloads, I'd avoid any required affinity tied to cost and instead use weighted preferred affinity favoring spot/cheaper node pools, ensuring cost optimization degrades gracefully to on-demand capacity rather than blocking scheduling during a spot shortage. I'd periodically audit that the compliance required-affinity terms and their corresponding taints stay in sync, since a drift between the two (a labeled-but-untainted compliance node, for instance) would silently reopen the isolation boundary the regulated workloads depend on.
_What the interviewer is probing for:_ Recognition that affinity alone is a one-directional selection mechanism and that genuine isolation between workload classes typically needs the complementary taint/toleration mechanism (§68), plus sound judgment on where hard vs. soft constraints belong.

## 12. Common Misconceptions

1. **"Node affinity replaces `nodeSelector` entirely and `nodeSelector` is deprecated."** `nodeSelector` remains fully supported for simple exact-match cases; node affinity is additive expressiveness, not a replacement mandate.
2. **"A high-weight preferred term functions like a soft requirement that's almost always honored."** It only ever influences relative scoring among already-feasible nodes; under sufficient pressure, a Pod can and will land on a node satisfying no preferred terms at all.
3. **"IgnoredDuringExecution means the affinity rule is ignored."** It means the rule is ignored for re-evaluation purposes after scheduling — the rule is fully enforced once, at scheduling time; it simply isn't re-checked against a running Pod.
4. **"Multiple `matchExpressions` are always ORed together."** They are ANDed within a single `nodeSelectorTerms` entry; only separate `nodeSelectorTerms` list entries are ORed.

## 13. 🔑 Key Takeaways

- `nodeSelector` is a simple, fully-supported exact-match filter; node affinity is a strict superset offering richer operators plus a hard/soft distinction.
- Required affinity operates in the Filter phase (hard elimination); preferred affinity operates in the Score phase (soft, weighted ranking) — never confuse the two's failure modes.
- `IgnoredDuringExecution` means affinity is checked once at scheduling time only, never re-evaluated against a running Pod even if node labels later change.
- Expressions within one `nodeSelectorTerms` entry are ANDed; separate `nodeSelectorTerms` entries are ORed — this OR-of-ANDs structure is what makes multi-zone-style constraints possible.
- Node affinity governs Pod-to-node placement only and is not a runtime security boundary; genuine isolation typically needs taints/tolerations (§68) as a complementary mechanism.

## 14. Related Concepts & What's Next

§65 established the Filter/Score framework that required and preferred node affinity each exercise. §24 and §31 cover Pod spec structure and label/selector mechanics this section assumes. §68 covers taints/tolerations, the complementary node-side exclusion mechanism referenced in the architect-level scenario above. §67 next extends this same required/preferred, hard/soft model from node-level matching to Pod-to-Pod relationships.

**Next Section:** §67 — `Section-67-Part9-Pod-Affinity-Anti-Affinity.md`
