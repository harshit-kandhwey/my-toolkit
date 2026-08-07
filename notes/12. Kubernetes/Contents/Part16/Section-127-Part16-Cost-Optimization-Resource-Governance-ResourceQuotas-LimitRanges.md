# Section 127 (Part 16): Cost Optimization and Resource Governance (ResourceQuotas, LimitRanges)

## 1. Definition

**Plain language:** ResourceQuotas and LimitRanges are the mechanism that turns "please don't use more than your fair share of the cluster" from a polite request into an enforced rule — a ResourceQuota caps how much a whole namespace can consume in total, and a LimitRange fills in sensible defaults and per-container guardrails so a single misconfigured Pod can't quietly blow through that cap on its own.

**Precise definition:** A **ResourceQuota** is a namespace-scoped object that limits the aggregate consumption of compute resources (CPU, memory, ephemeral storage) and object counts (Pods, Services, PersistentVolumeClaims, ConfigMaps) within that namespace, enforced by an admission-time check that rejects any object creation which would push total consumption over the declared limit. A **LimitRange** is a namespace-scoped object that sets default requests/limits for containers that don't specify their own, and enforces minimum/maximum bounds and a max limit-to-request ratio per container or Pod — without a LimitRange, a Pod with no resource requests set consumes zero from a ResourceQuota's compute totals (since quota tracks requests, not actual usage) while still competing for real node capacity, an inconsistency that is one of the most common gaps in resource governance. Together, these two objects are the concrete implementation of the "resource isolation" pillar that [§126](./Section-126-Part16-Multi-Tenancy-Patterns-Kubernetes.md) (multi-tenancy) referenced repeatedly without detailing its mechanics — this section is that mechanics, and it directly builds on [§46](../Part6/Section-46-Part6-Resource-Requests-Limits-QoS-Classes.md)'s per-container requests/limits/QoS model (Part 6) by applying the same concepts at namespace scope, and on [§70](../Part9/Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)'s resource-based scheduling (Part 9) by explaining why a Pod that satisfies both can still be rejected at admission if it exceeds the namespace's aggregate budget.

## 2. Why This Matters

- **Resource requests are the currency of both scheduling and cost allocation** — the scheduler places Pods based on requests ([§70](../Part9/Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)), and cloud cost (node-hours, autoscaler-driven node counts) is ultimately driven by aggregate requested capacity, so a namespace's ResourceQuota is simultaneously a governance control and a direct lever on cloud spend.
- **Without a LimitRange, a ResourceQuota has an exploitable blind spot**: Pods with no resource requests specified don't count against a quota's CPU/memory totals at all (quota accounting is entirely requests-based), letting an unbounded number of "free" (quota-wise) Pods land on real nodes and consume genuine capacity while appearing to cost nothing against the namespace's declared budget.
- **This is the mechanism a platform team actually enforces during tenant onboarding** — [§126](./Section-126-Part16-Multi-Tenancy-Patterns-Kubernetes.md) described the "tenant onboarding bundle" pattern (Namespace + RBAC + NetworkPolicy + ResourceQuota/LimitRange); this section is where that bundle's compute-governance component is built and reasoned about in full.

🔑 **Key Takeaway:** ResourceQuota caps aggregate namespace-level consumption and object counts; LimitRange fills the gap ResourceQuota alone leaves open by forcing every container to carry a request/limit (defaulted if unset) and by bounding the limit-to-request ratio — deploy them together, because a ResourceQuota without a LimitRange can be silently bypassed by requestless Pods, and cost governance built on requests without both objects in place is not actually enforced.

## 3. Prerequisites and Dependencies

Builds directly on [§46](../Part6/Section-46-Part6-Resource-Requests-Limits-QoS-Classes.md) (Resource Requests and Limits; Quality-of-Service Classes, Part 6) for the per-container mechanics these namespace-scoped objects aggregate and default, and on [§70](../Part9/Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md) (Resource-Based Scheduling, Part 9) for how the scheduler consumes the requests that ResourceQuota/LimitRange govern. Also assumes [§126](./Section-126-Part16-Multi-Tenancy-Patterns-Kubernetes.md)'s (Part 16) multi-tenancy framing, since ResourceQuota/LimitRange are presented here as the concrete implementation of that section's fourth isolation axis.

## 4. Architecture Diagram

```text
                     RESOURCEQUOTA + LIMITRANGE ENFORCEMENT FLOW

   kubectl apply -f pod.yaml (no resources specified)
                │
                ▼
   ┌─────────────────────────────────────────────────────────────────┐
   │  ADMISSION CHAIN (namespace: team-a)                            │
   │                                                                 │
   │   Step 1: LimitRange admission plugin                           |
   │     - No requests/limits set on container?                      │
   │       → inject namespace's LimitRange defaults                  │
   │     - Requests/limits set but outside min/max/ratio bounds?     │
   │       → REJECT ("minimum cpu usage per Container is 100m")      │
   │                                                                 │
   │   Step 2: ResourceQuota admission plugin                        │
   │     - Sum(existing Pod requests in namespace) + this Pod's      │
   │       (now-defaulted) requests > quota.spec.hard?               │
   │       → REJECT ("exceeded quota: compute-quota")                │
   │     - Object count (pods, services, pvcs) + 1 > quota count cap?│
   │       → REJECT                                                  │
   └─────────────────────────────────────────────────────────────────┘
                │  both pass
                ▼
   ┌─────────────────────────────────────────────────────────────┐
   │  Pod persisted to etcd → scheduler places it using the same │
   │  (now-defaulted) requests for filtering/scoring (§70)       │
   └─────────────────────────────────────────────────────────────┘

   NAMESPACE: team-a
   ┌──────────────────────────────────────────────────────────────┐
   │ ResourceQuota "compute-quota"                                │
   │   requests.cpu: 10, requests.memory: 20Gi                    │
   │   limits.cpu: 20,   limits.memory: 40Gi                      │
   │   pods: 50, persistentvolumeclaims: 10                       │
   │                                                              │
   │ LimitRange "default-limits"                                  │
   │   default request/limit per container                        │
   │   min/max per container                                      │
   │   maxLimitRequestRatio                                       │
   │                                                              │
   │  Pod A (explicit)   Pod B (defaulted)   Pod C (rejected)     │
   │  req: 500m/1Gi       req: 250m/512Mi     req: 2/8Gi          │
   │  ✓ within quota      ✓ within quota      ✗ exceeds remaining│
   └──────────────────────────────────────────────────────────────┘
```

## 5. Hands-On

### 5.1 Defining and Applying a ResourceQuota

**Purpose:** Cap total compute and object-count consumption for a tenant namespace.

**Syntax:**

```yaml
apiVersion: v1
kind: ResourceQuota
metadata:
  name: compute-quota
  namespace: team-a
spec:
  hard:
    requests.cpu: "10"
    requests.memory: 20Gi
    limits.cpu: "20"
    limits.memory: 40Gi
    pods: "50"
    services: "10"
    persistentvolumeclaims: "10"
    requests.storage: 100Gi
```

```bash
kubectl apply -f compute-quota.yaml
kubectl describe resourcequota compute-quota -n team-a
```

**Production usage example:** A platform team sets `requests.cpu`/`requests.memory` on every tenant namespace's ResourceQuota to match that tenant's purchased or allocated capacity tier, so the ResourceQuota becomes the enforcement point for a cost-allocation agreement made outside Kubernetes entirely — exceeding quota produces an immediate, actionable admission error rather than a surprise bill discovered a month later.

**Common errors:** Setting only `limits.cpu`/`limits.memory` and omitting `requests.cpu`/`requests.memory` — since the scheduler and node capacity accounting both operate on requests, a quota that only bounds limits leaves the actual capacity-planning number (aggregate requests) completely unconstrained.

### 5.2 Defining a LimitRange to Default and Bound Container Resources

**Purpose:** Guarantee every container in a namespace has a request/limit (even if the author forgot to set one) and prevent absurd limit-to-request ratios.

**Syntax:**

```yaml
apiVersion: v1
kind: LimitRange
metadata:
  name: default-limits
  namespace: team-a
spec:
  limits:
    - type: Container
      default:
        cpu: 500m
        memory: 512Mi
      defaultRequest:
        cpu: 250m
        memory: 256Mi
      min:
        cpu: 100m
        memory: 128Mi
      max:
        cpu: 2
        memory: 4Gi
      maxLimitRequestRatio:
        cpu: "4"
        memory: "4"
```

```bash
kubectl apply -f default-limits.yaml
kubectl run test-pod --image=nginx -n team-a --dry-run=client -o yaml | kubectl apply -f -
kubectl get pod test-pod -n team-a -o jsonpath='{.spec.containers[0].resources}'
```

**Production usage example:** A platform team enforces `maxLimitRequestRatio: "4"` specifically to prevent a container from requesting 100m CPU but setting a limit of 8 CPUs — a pattern that looks fine at admission but produces severe, unpredictable burst behavior and node-level noisy-neighbor effects once several such Pods land on the same node and simultaneously burst.

**Common errors:** Assuming a LimitRange applies retroactively to already-running Pods — LimitRange defaults and bounds are enforced only at admission time for new object creation; existing Pods are unaffected until they are recreated (e.g., via a Deployment rollout).

### 5.3 Diagnosing Quota Exhaustion and Verifying Actual Consumption

**Purpose:** Distinguish "quota looks full" from "quota is actually full," and identify which objects are consuming the budget.

**Syntax:**

```bash
kubectl describe resourcequota compute-quota -n team-a
```

```text
Name:            compute-quota
Namespace:       team-a
Resource         Used   Hard
--------         ----   ----
limits.cpu       14     20
limits.memory    28Gi   40Gi
pods             47     50
requests.cpu     9500m  10
requests.memory  19Gi   20Gi
```

**Production usage example:** A CI pipeline deploying a new environment fails with `exceeded quota: compute-quota, requested: requests.cpu=1, used: requests.cpu=9500m, limited: requests.cpu=10` — the platform team uses `kubectl describe resourcequota` in the failing namespace as the first triage step before assuming the cluster itself is out of capacity, since the two are frequently confused.

**Common errors:** Confusing a ResourceQuota rejection (a namespace-scoped admission-time budget check, fixable by raising quota or freeing capacity within the namespace) with genuine cluster-wide node capacity exhaustion (a scheduling-time `Pending`/`Insufficient cpu` condition) — the two produce different error messages and require entirely different remediation.

## 6. Production Usage Notes

- ResourceQuota accounting is based on **requests**, not actual runtime usage — a namespace can be "at quota" per its declared requests while its Pods are using a fraction of that in practice, and conversely a namespace under-provisioned on requests can have Pods that are actually starved at runtime; quota governs allocation, not utilization, and cost/capacity dashboards should track both separately.
- LimitRange's `default`/`defaultRequest` values are injected **only if a container specifies no resources at all** for that field — a container specifying `requests.cpu` but omitting `limits.cpu` gets only the missing field defaulted, not the whole resources block replaced.
- Object-count quotas (`pods`, `services`, `persistentvolumeclaims`, `secrets`, `configmaps`) are a frequently under-used but important governance lever independent of compute — a tenant that can create unlimited Services or PVCs can still exhaust cluster-wide resources (LoadBalancer quota with the cloud provider, storage backend capacity) even with tight compute quotas in place.

## 7. Security Considerations

- A missing LimitRange is a resource-exhaustion attack surface, not just a cost-governance gap: a tenant with `create pod` RBAC but no LimitRange can create Pods with no requests set (invisible to ResourceQuota's compute accounting) and no limits set (able to consume unbounded node memory/CPU until OOMKilled or throttled by the kernel), directly enabling a noisy-neighbor or denial-of-service condition against co-located tenants.
- ResourceQuota and LimitRange are not exempt for cluster-admin-created objects by default configuration, but exemption is possible via a validating admission policy scoped to specific identities — any such exemption should be treated as a deliberate, audited exception, since a routinely-exempted "break glass" identity defeats the quota model for anyone who inherits or compromises that identity.
- Quota exhaustion itself can be an availability risk if not monitored: a tenant unknowingly at quota during an incident (e.g., needing to scale up quickly to absorb load) will have new Pods rejected at admission with no automatic escalation path, so quota-exhaustion alerting is a genuine production-readiness requirement, not an optional nicety.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                 | Likely Cause                                                                                                                        | Fix                                                                                                                                                                                  |
| --------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Pod creation fails with `exceeded quota: compute-quota`                                 | Namespace's aggregate requested CPU/memory or object count is at or above the ResourceQuota's hard cap                              | Raise the quota (with governance sign-off), free capacity by removing/rightsizing existing Pods, or split the tenant across more namespaces                                          |
| Pod exists with no resources set despite a ResourceQuota being in place                 | No LimitRange present in the namespace to inject defaults; ResourceQuota alone does not default anything                            | Deploy a LimitRange with `default`/`defaultRequest` alongside the ResourceQuota                                                                                                      |
| Pod rejected at creation with a min/max resources error                                 | Container's explicit requests/limits fall outside the namespace LimitRange's `min`/`max` bounds                                     | Adjust the Pod spec's resources to fall within the LimitRange bounds, or revisit whether the bounds are still appropriate                                                            |
| Namespace "at quota" per `kubectl describe resourcequota` but nodes show spare capacity | Quota tracks requests, not actual usage/utilization — the namespace's declared requests are high even if actual consumption is low  | Rightsize requests to reflect real usage (via VPA recommendations, [§38](../Part5/Section-38-Part5-Vertical-Pod-Autoscaler-Cluster-Autoscaler.md)) rather than raising quota blindly |
| New Deployment rollout suddenly hits a LimitRange rejection that didn't exist before    | LimitRange was added/tightened after existing Pods were created; the new ReplicaSet's Pods are the first to be evaluated against it | Adjust the new Pod template's resources to comply, or adjust the LimitRange bounds if they were set too aggressively                                                                 |

## 9. Best Practices

- Deploy ResourceQuota and LimitRange together as a pair for every tenant namespace, never one without the other — a ResourceQuota without a LimitRange leaves a requestless-Pod blind spot; a LimitRange without a ResourceQuota bounds individual containers but places no aggregate ceiling on the namespace.
- Set `requests.cpu`/`requests.memory` quotas to reflect actual capacity allocation agreements (the number that matters for scheduling and cost), and treat `limits.cpu`/`limits.memory` quotas as a secondary, generally looser ceiling that permits legitimate bursting without permitting unbounded bursting.
- Monitor quota utilization (`used` vs. `hard` from `kubectl describe resourcequota`, or the equivalent Prometheus metrics from kube-state-metrics) proactively with alerting well before 100%, not reactively after the first admission rejection during an incident.
- Periodically reconcile ResourceQuota's declared `requests.cpu`/`memory` against actual utilization data (metrics-server, VPA recommendations) to right-size quotas over time rather than treating the initial onboarding number as permanent.

## 10. Common Anti-Patterns / Mistakes

- **Deploying a ResourceQuota without a LimitRange**, leaving requestless Pods able to consume real node capacity while counting as zero against the namespace's compute quota.
- **Setting quota limits high "to avoid tickets" rather than to reflect actual capacity allocation**, which defeats the purpose of quota as a cost-governance and fair-sharing mechanism and just delays the eventual capacity conversation.
- **Treating a ResourceQuota rejection and a scheduler `Pending`/`Insufficient cpu` condition as the same problem**, when the former is a namespace-scoped admission-time budget check and the latter is genuine cluster-wide node capacity exhaustion, requiring different fixes.
- **Never revisiting quota values after initial tenant onboarding**, even as the tenant's actual workload footprint grows or shrinks substantially, leaving quota disconnected from real usage over time.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a ResourceQuota and a LimitRange?"_
**Model answer:** A ResourceQuota sets an aggregate ceiling for an entire namespace — total CPU/memory requests and limits across all Pods, plus object counts like Pods, Services, and PVCs. A LimitRange operates per-container within a namespace — it provides default requests/limits for containers that don't specify their own, and enforces minimum, maximum, and limit-to-request ratio bounds on individual containers. ResourceQuota answers "how much can this namespace consume in total"; LimitRange answers "what must every individual container's resource spec look like."
_What the interviewer is probing for:_ Basic clarity on scope (aggregate vs. per-container) — a common early confusion is treating the two as interchangeable or redundant.

**🎯 Intermediate:** _"Why would a Pod with no resource requests set not show up as consuming anything against a namespace's ResourceQuota?"_
**Model answer:** ResourceQuota's compute accounting (`requests.cpu`, `requests.memory`) is based entirely on the requests declared on Pods, not their actual runtime usage. A Pod with no `resources.requests` set contributes zero to that accounting even though it still gets scheduled onto a real node and can consume genuine CPU/memory there, up to whatever the kernel and cgroup limits allow (potentially unbounded without a limit set). This is exactly the gap a LimitRange closes, by injecting a `defaultRequest` (and `default` limit) onto any container that doesn't specify its own, so every Pod that lands in the namespace is forced to have a request that quota can actually track.
_What the interviewer is probing for:_ Understanding that ResourceQuota and LimitRange are complementary, not redundant, and specifically why deploying one without the other leaves an exploitable gap.

**🎯 Senior:** _"A namespace's ResourceQuota shows near-100% utilization on `requests.cpu`, but node-level metrics show the cluster has plenty of spare CPU capacity. Is there a problem, and if so what would you do?"_
**Model answer:** This isn't necessarily a capacity problem — it's evidence that the namespace's Pods have requests set higher than their actual usage, which is a rightsizing problem, not a "the cluster is full" problem. I'd pull actual utilization data (metrics-server, or ideally historical data via a VPA in recommendation mode) for the Pods in that namespace and compare declared requests against real consumption. If there's a substantial gap, the fix is to rightsize the Pods' requests downward (freeing quota headroom without raising the quota ceiling itself) rather than reflexively increasing the ResourceQuota, since raising quota without addressing over-provisioned requests just delays the same problem at a higher ceiling and continues to reserve cluster capacity the tenant isn't actually using — capacity other tenants may need.
_What the interviewer is probing for:_ The distinction between requests-based quota accounting and actual utilization, and a bias toward rightsizing over blindly raising limits.

**🎯 Architect:** _"Design a resource-governance model for a platform with 40 tenant namespaces of varying size, where you need both fair capacity allocation and a defensible chargeback/cost-allocation story to each business unit."_
**Model answer:** I'd tier tenants (e.g., small/medium/large) with standardized ResourceQuota + LimitRange bundles per tier rather than hand-tuning 40 bespoke configurations, since a small number of standardized tiers is auditable and comparable across business units in a way that 40 unique quota values are not. Each tier's `requests.cpu`/`requests.memory` quota becomes the basis of chargeback — since requests are what actually drives node-hours and thus cloud cost, quota utilization data (not raw usage metrics, which fluctuate) gives a stable, contractual number each business unit can be billed against. I'd pair every namespace's ResourceQuota with a LimitRange enforcing sane per-container defaults and a bounded limit-to-request ratio, specifically to prevent any tenant's containers from either silently evading quota accounting (requestless Pods) or requesting minimally while bursting massively (an extreme limit-to-request ratio) in a way that undermines the fairness the quota tiers are meant to guarantee. I'd build a recurring rightsizing review (quarterly, using VPA recommendation-mode data) into the process, since a chargeback model anchored to declared requests only stays fair and defensible if those requests are periodically reconciled against actual usage rather than left to drift — otherwise tenants either over-request (paying for and reserving capacity they don't use, at other tenants' expense in a shared-capacity cluster) or under-request (extracting more value than they're charged for). Finally, I'd add quota-utilization alerting well ahead of 100% for every tenant, since an unmonitored quota exhaustion during a legitimate scale-up event is an availability incident dressed up as a governance success.
_What the interviewer is probing for:_ Ability to connect a purely technical mechanism (ResourceQuota/LimitRange) to a genuine business requirement (fair, defensible chargeback across business units) and to reason about the ongoing operational discipline (rightsizing reviews) required to keep that connection honest over time, not just the initial configuration.

## 12. Common Misconceptions

1. **"ResourceQuota tracks actual resource usage."** It tracks declared requests (and limits for the `limits.*` fields), not real-time consumption — a namespace can be at quota while genuinely idle, or under quota while its Pods are memory-starved.
2. **"A LimitRange applies retroactively to already-running Pods."** It only affects admission of new objects; existing Pods are unaffected until recreated.
3. **"Setting a ResourceQuota is sufficient without a LimitRange."** Requestless Pods bypass compute quota accounting entirely while still consuming real node capacity — the two objects close different halves of the same gap.
4. **"Object-count quotas (pods, services, PVCs) are a minor detail compared to compute quotas."** Unbounded Service or PVC creation can exhaust cloud-provider LoadBalancer quotas or storage backend capacity independent of how tightly compute is governed.

## 13. 🔑 Key Takeaways

- ResourceQuota caps aggregate namespace-level compute and object-count consumption; LimitRange defaults and bounds per-container resources — deploy both together, since either alone leaves a governance gap the other closes.
- ResourceQuota accounting is requests-based, not usage-based — a namespace can be "at quota" while genuinely underutilized, making periodic rightsizing (via VPA recommendation data) essential to keeping quota meaningful over time.
- A LimitRange's `defaultRequest`/`default` values only apply to containers with no resources field set at all, and only to the specific missing field, not the entire resources block.
- Object-count quotas (Services, PVCs, Secrets) are an independent governance axis from compute quotas and can be the actual constraint even when compute quota looks healthy.
- ResourceQuota admission rejections and scheduler-level `Pending`/`Insufficient cpu` conditions look superficially similar but require entirely different remediation paths.

## 14. Related Concepts & What's Next

This section made concrete the resource-governance pillar of multi-tenancy that [§126](./Section-126-Part16-Multi-Tenancy-Patterns-Kubernetes.md) referenced without detailing, extending [§46](../Part6/Section-46-Part6-Resource-Requests-Limits-QoS-Classes.md)'s per-container requests/limits/QoS model (Part 6) to namespace scope and explaining its interaction with [§70](../Part9/Section-70-Part9-Resource-Based-Scheduling-Requests-Limits-Placement.md)'s resource-based scheduling (Part 9). [§128](./Section-128-Part16-Kubernetes-AWS-Azure-GCP-EKS-AKS-GKE-Specific-Considerations.md) shifts from this governance mechanism to the cloud-provider layer it ultimately operates within — the EKS/AKS/GKE-specific considerations (node autoscaling behavior, cloud-native cost tooling, provider-specific quota interactions) that shape how ResourceQuota and LimitRange decisions play out once a cluster is actually running on a specific managed provider.

**Next Section:** [§128](./Section-128-Part16-Kubernetes-AWS-Azure-GCP-EKS-AKS-GKE-Specific-Considerations.md) — `Section-128-Part16-Kubernetes-AWS-Azure-GCP-EKS-AKS-GKE-Specific-Considerations.md`
