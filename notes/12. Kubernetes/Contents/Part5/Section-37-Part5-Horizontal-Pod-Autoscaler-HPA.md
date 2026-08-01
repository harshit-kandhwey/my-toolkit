# Section 37 (Part 5): Horizontal Pod Autoscaler (HPA)

## 1. Definition

**Plain language:** A Deployment (§28) declares a fixed replica count, but real traffic doesn't hold still — it spikes at lunch, drops overnight, and surges during a marketing push. Manually editing `replicas` to chase that curve doesn't scale as an operating model. The Horizontal Pod Autoscaler automates exactly that edit: it watches a metric, compares it against a target, and adjusts the replica count of a Deployment, ReplicaSet (§27), or StatefulSet (§33) up or down on a recurring schedule, with no human in the loop.

**Precise definition:** The **HorizontalPodAutoscaler (HPA)** is a Kubernetes API object and accompanying controller (running inside kube-controller-manager) that periodically queries a **metrics source** for a target workload's current metric value, computes a **desired replica count** using the formula `desiredReplicas = ceil(currentReplicas × (currentMetricValue / desiredMetricValue))`, and — subject to configured min/max bounds and stabilization windows — patches the target's `spec.replicas` field to match. HPA reads metrics through the **metrics.k8s.io** (resource metrics: CPU/memory, served by metrics-server), **custom.metrics.k8s.io** (per-Pod or per-object custom metrics, e.g., queue depth), and **external.metrics.k8s.io** (metrics from outside the cluster, e.g., a cloud provider queue length) APIs — HPA itself contains no metric-collection logic; without a working metrics pipeline (§89, Part 12) registered against one of these APIs, HPA has nothing to act on and cannot function.

## 2. Why This Matters

- **HPA is the mechanism that makes "elastic" mean something concrete in Kubernetes.** Without it, the replica counts set in §27/§28 are static declarations that a human must revise by hand every time load shifts — HPA turns replica count itself into a second, continuously reconciled desired state, layered on top of the Deployment's own reconciliation loop.
- **It has a hard, easy-to-forget dependency on the metrics pipeline covered in §89 (Part 12).** An HPA object with no metrics-server (or custom/external metrics adapter) installed and healthy will sit reporting `<unknown>` for its current metric indefinitely — a very common "HPA doesn't do anything" support case that is actually a missing-prerequisite case, not an HPA bug.
- **HPA only ever changes replica count — it never changes what a single Pod is allowed to consume.** That's a distinct axis of scaling (§38, Vertical Pod Autoscaler) that a lot of engineers conflate with HPA until the distinction is made explicit.

🔑 **Key Takeaway:** HPA is a periodic reconciliation loop that adjusts replica count based on live metrics fetched from the metrics.k8s.io/custom.metrics.k8s.io/external.metrics.k8s.io APIs — it has zero built-in metric collection of its own, so a functioning metrics pipeline (§89) is a strict prerequisite, not an optional add-on.

## 3. Prerequisites and Dependencies

Builds directly on §27 (ReplicaSets, the object whose `replicas` field HPA ultimately patches) and §28 (Deployments, the most common HPA scale target); depends on the metrics pipeline detailed in §89 (Part 12) to have any data to act on.

## 4. Architecture Diagram

```text
                    ┌───────────────────────────────────────────┐
                    │      HorizontalPodAutoscaler object       │
                    │  scaleTargetRef: Deployment/app           │
                    │  minReplicas: 3   maxReplicas: 20         │
                    │  metrics: [ cpu utilization target 60% ]  │
                    └───────────────────┬───────────────────────┘
                                        │ every sync period (default 15s)
                                        ▼
                    ┌────────────────────────────────────────────────┐
                    │   HPA controller (kube-controller-manager)     │
                    │   1. Query current metric value                │
                    │   2. desiredReplicas = ceil(cur × (val/target))│
                    │   3. Clamp to [minReplicas, maxReplicas]       │
                    │   4. Apply stabilization window / scaling      │
                    │      policies (rate limits on change)          │
                    └───────────────────┬────────────────────────────┘
                                        │ patches spec.replicas
                                        ▼
                    ┌──────────────────────────────────────────────┐
                    │         Deployment "app" (§28)               │
                    │  spec.replicas: 3 → 7 (controller-managed)   │
                    └───────────────────┬──────────────────────────┘
                                        │
                                        ▼
                    ┌──────────────────────────────────────────────┐
                    │         ReplicaSet (§27) creates/deletes     │
                    │         Pods to match new replica count      │
                    └──────────────────────────────────────────────┘

Metric sources the HPA controller reads from (never collects itself):

  metrics.k8s.io           ◄── metrics-server (CPU/memory, §89)
  custom.metrics.k8s.io    ◄── Prometheus Adapter or similar (per-Pod custom metrics)
  external.metrics.k8s.io  ◄── cloud provider adapter (e.g., SQS queue depth)
```

- **The HPA controller never talks to Pods or nodes directly** — it reads aggregated metric values through the Kubernetes API server's metrics aggregation layer, then writes its scaling decision back through the same API server as a patch to the target workload's `spec.replicas`.
- **Scaling is asymmetric by design** — Kubernetes applies more conservative defaults to scale-down than scale-up (a default stabilization window of 300 seconds on scale-down vs. 0 on scale-up) specifically to avoid flapping replica counts on noisy metrics.

## 5. Hands-On: Configuring and Observing HPA

### 5.1 Creating a CPU-Based HPA (autoscaling/v2)

**Purpose:** Scale a Deployment between 3 and 20 replicas, targeting 60% average CPU utilization across Pods.

**Syntax:** `kubectl autoscale deployment <name> --min=<n> --max=<n> --cpu-percent=<pct>` or a full manifest for multi-metric control.

```yaml
# app-hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: app-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: app
  minReplicas: 3
  maxReplicas: 20
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 60
  behavior:
    scaleDown:
      stabilizationWindowSeconds: 300
    scaleUp:
      stabilizationWindowSeconds: 0
      policies:
        - type: Pods
          value: 4
          periodSeconds: 60
```

```bash
$ kubectl apply -f app-hpa.yaml
horizontalpodautoscaler.autoscaling/app-hpa created

$ kubectl get hpa app-hpa
NAME      REFERENCE          TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
app-hpa   Deployment/app     45%/60%   3         20        4          2m
```

**Production usage example:** The `behavior` block's asymmetric policy — instant scale-up in bursts of up to 4 Pods per minute, but a 5-minute stabilization window before scaling down — is standard for latency-sensitive services, absorbing traffic spikes quickly while avoiding premature scale-down during brief metric dips.

**Common errors:** Requesting `resource: cpu` on containers with no `resources.requests.cpu` set (§6, Part 6, once written) results in a `TARGETS` column showing `<unknown>/60%` — utilization targets are computed as a percentage of the request, so an unset request makes the percentage undefined, not zero.

### 5.2 Diagnosing an HPA Stuck at `<unknown>`

**Purpose:** Distinguish "metrics pipeline missing" from "HPA misconfigured" — the single most common HPA support case.

```bash
$ kubectl get hpa app-hpa
NAME      REFERENCE        TARGETS         MINPODS   MAXPODS   REPLICAS   AGE
app-hpa   Deployment/app   <unknown>/60%   3         20        3          5m

$ kubectl describe hpa app-hpa | grep -A3 Conditions
Conditions:
  Type           Status  Reason               Message
  ----           ------  ------               -------
  AbleToScale    True    ReadyForNewScale      recommended size matches current size
  ScalingActive  False   FailedGetResourceMetric  the HPA was unable to compute the replica count: unable to get metrics for resource cpu: unable to fetch metrics from resource metrics API

$ kubectl get apiservices | grep metrics
v1beta1.metrics.k8s.io                False (MissingEndpoints)
```

**Production usage example:** `MissingEndpoints` on the `metrics.k8s.io` APIService almost always means metrics-server isn't installed or its Pod is unhealthy — the fix is installing or repairing metrics-server (§89), not touching the HPA object at all.

**Common errors:** Assuming a `<unknown>` target means the HPA YAML itself is wrong; in the overwhelming majority of cases the HPA spec is fine and the metrics pipeline is the actual gap.

### 5.3 Scaling on a Custom Metric (Queue Depth)

**Purpose:** Show HPA driving scale from an application-level signal rather than CPU/memory, common for queue-worker workloads.

```yaml
# worker-hpa.yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: worker-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: queue-worker
  minReplicas: 1
  maxReplicas: 50
  metrics:
    - type: External
      external:
        metric:
          name: sqs_queue_messages_visible
          selector:
            matchLabels:
              queue: orders
        target:
          type: AverageValue
          averageValue: "30"
```

**Production usage example:** With `averageValue: "30"`, a queue holding 300 visible messages drives the HPA toward 10 replicas (300 / 30) — a natural fit for worker pools where CPU utilization is a poor proxy for actual backlog pressure, requiring an external metrics adapter registered against `external.metrics.k8s.io` for the specific queue system in use.

## 6. Production Usage Notes

- **`autoscaling/v2` (formerly `v2beta2`) is the API version to use for anything beyond a single CPU metric** — `autoscaling/v1` only supports CPU utilization and lacks the `behavior` block entirely; most production HPAs should be authored directly as `v2` manifests rather than generated via `kubectl autoscale`, which only produces a `v1`-style single-metric object.
- **HPA and a CI/CD pipeline that also sets `replicas` in its manifests will fight each other** — once an HPA is targeting a Deployment, any subsequent `kubectl apply` that includes an explicit `replicas` value will be immediately overridden on the next HPA sync; GitOps pipelines (§88, Part 11) commonly omit `replicas` entirely from Deployment manifests once HPA owns that field.
- **Multiple metrics in one HPA use a "highest wins" resolution** — when several metrics are specified, the HPA controller computes a desired replica count per metric and scales to the largest resulting number, so a workload can be simultaneously protected against CPU pressure and queue backlog without either metric being silently ignored.

## 7. Security Considerations

- The HPA controller runs with the permissions of kube-controller-manager and only needs read access to metrics APIs and patch access to the scale subresource of workloads — a custom or external metrics adapter, by contrast, often needs broader read access to an external system (a message queue, a cloud monitoring API) and that credential's blast radius should be scoped tightly.
- Unbounded `maxReplicas` combined with an attacker-influenceable metric (e.g., a custom metric derived from unauthenticated request volume) is a real resource-exhaustion and cost-amplification vector — always set a `maxReplicas` ceiling that reflects genuine capacity and budget limits, not an arbitrarily large number "just in case."

## 8. Common Troubleshooting Scenarios

| Symptom                                             | Likely Cause                                                           | Resolution Path                                                                   |
| --------------------------------------------------- | ---------------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| `TARGETS` column shows `<unknown>/60%`              | metrics-server (or custom/external adapter) not installed or unhealthy | Check `kubectl get apiservices`; repair or install the metrics pipeline (§89)     |
| Replica count oscillates rapidly up and down        | No or too-short stabilization window on scale-down                     | Set `behavior.scaleDown.stabilizationWindowSeconds` to a larger value (e.g., 300) |
| HPA computes a target but replicas never change     | `minReplicas`/`maxReplicas` bounds already satisfied at current level  | Confirm the computed desired count against the configured min/max clamp           |
| CI/CD keeps resetting replicas, undoing HPA scaling | Deployment manifest still hardcodes `spec.replicas`                    | Remove `replicas` from the manifest once an HPA owns that field                   |

## 9. Best Practices

- Author HPAs as `autoscaling/v2` manifests directly rather than relying on `kubectl autoscale`'s CPU-only, `behavior`-less output for anything production-grade.
- Set resource requests (§6, Part 6, once written) on every container targeted by a CPU/memory-based HPA — utilization targets are meaningless without a request to compute the percentage against.
- Tune `behavior` stabilization windows deliberately per workload risk profile rather than accepting defaults blindly — bursty, latency-sensitive services usually want fast scale-up and conservative scale-down.

## 10. Common Anti-Patterns / Mistakes

- **Deploying an HPA without first confirming the metrics pipeline (§89) is healthy**, then treating the resulting `<unknown>` target as an HPA bug rather than a missing prerequisite.
- **Leaving `spec.replicas` hardcoded in a Deployment manifest that's also targeted by an HPA**, causing every subsequent `kubectl apply`/GitOps sync to fight the autoscaler's decision.
- **Setting `maxReplicas` far above genuine capacity or budget limits** "just in case," turning a metric spike or misconfigured custom metric into an unbounded cost-amplification incident.

## 11. Interview Questions

**🎯 Beginner:** _"What does a Horizontal Pod Autoscaler actually do, and what does it never do?"_
**Model answer:** It watches a configured metric (CPU utilization, a custom metric, or an external metric) for a target workload and adjusts that workload's replica count up or down to keep the metric near a desired target, within a configured min/max bound. It never changes the CPU/memory resource requests or limits of individual Pods — that's a separate concern (Vertical Pod Autoscaler, §38) — and it never provisions nodes itself either.
_What the interviewer is probing for:_ Clear boundary between HPA's actual scope (replica count only) and adjacent autoscaling concepts.

**🎯 Intermediate:** _"An HPA has been applied but its TARGETS column has shown `<unknown>/60%` for ten minutes. Walk through your diagnosis."_
**Model answer:** First I'd run `kubectl describe hpa` and look at the `Conditions` section, specifically `ScalingActive` and its `Reason` — a `FailedGetResourceMetric` reason points straight at the metrics pipeline rather than the HPA spec. Then I'd check `kubectl get apiservices` for `v1beta1.metrics.k8s.io` (or the relevant custom/external metrics APIService) and look for `MissingEndpoints` or similar, which usually means metrics-server (or the custom/external adapter) isn't installed, is unhealthy, or isn't reachable from the API server's aggregation layer. Only after confirming the metrics pipeline is genuinely healthy would I revisit the HPA manifest itself for a misconfigured metric name or selector.
_What the interviewer is probing for:_ Correct triage order — metrics pipeline health before HPA spec — since this is the overwhelmingly common root cause.

**🎯 Senior:** _"A team wants an HPA to scale a Deployment based on queue depth from an external message broker rather than CPU. What has to exist for that to work, and what are the risks?"_
**Model answer:** They need an external metrics adapter registered against the `external.metrics.k8s.io` API that can query the specific broker (e.g., an SQS or RabbitMQ adapter) and expose the queue depth as a metric the HPA controller can read — HPA itself has no native understanding of any specific broker. The HPA spec then uses a `type: External` metric with an `averageValue` target, and desired replicas are computed from queue depth divided by that target. The main risks are: the adapter credential needs read access to the broker and its own failure mode needs to be understood (does a broken adapter freeze scaling at the last known value, or does it report `<unknown>` and potentially trigger conservative fallback behavior?); and an unbounded `maxReplicas` against a metric an attacker or a runaway upstream producer can inflate is a genuine cost and capacity risk, so the ceiling needs to reflect real downstream capacity (e.g., database connection limits), not just "however many workers can theoretically run."
_What the interviewer is probing for:_ Understanding that custom/external metrics require real infrastructure beyond the HPA object, plus awareness of the operational failure modes and cost risks that come with metric-driven scaling on non-resource signals.

**🎯 Architect:** _"How would you design HPA policy across a platform serving many teams with heterogeneous workloads — some bursty and latency-sensitive, some batch and cost-sensitive — while avoiding both under-provisioning incidents and runaway cost?"_
**Model answer:** I'd avoid a single platform-wide HPA template and instead define a small number of named autoscaling profiles teams opt into, each encoding a deliberate `behavior` policy: a "bursty/latency-sensitive" profile with fast scale-up (short or zero stabilization, larger per-period Pod increments) and conservative scale-down (a multi-minute stabilization window) for user-facing services, and a "batch/cost-sensitive" profile with slower scale-up and fast scale-down for internal or asynchronous workloads where cost matters more than instant responsiveness. Every profile would enforce a mandatory, workload-appropriate `maxReplicas` ceiling tied to a capacity or budget review, never left as an arbitrary large default, and every metric-driven HPA (custom or external) would require its metrics pipeline's health to be part of that workload's own alerting, since a silently degraded metrics adapter freezing an HPA's replica count is functionally an outage in slow motion. Finally, I'd treat "does this Deployment still hardcode `replicas` in its GitOps manifest" as a standard platform lint check, since that's the single most common way HPA gets silently defeated by CI/CD in a large multi-team environment.
_What the interviewer is probing for:_ Ability to turn HPA mechanics into a governed, multi-tenant platform policy rather than a one-off per-service configuration, with explicit attention to cost governance and failure-mode observability.

## 12. Common Misconceptions

1. **"HPA scales nodes as well as Pods."** It only ever changes a workload's replica count; provisioning or removing nodes is Cluster Autoscaler's job (§38), an entirely separate component that HPA has no direct relationship with.
2. **"HPA collects its own metrics."** It contains no metric-collection logic at all — it is purely a consumer of the metrics.k8s.io/custom.metrics.k8s.io/external.metrics.k8s.io APIs, which must be populated by metrics-server or a custom/external adapter (§89).
3. **"A CPU utilization target of 60% means 60% of a full CPU core."** It means 60% of the Pod's configured CPU **request**, not an absolute core count — an unset request makes the percentage undefined rather than zero.
4. **"HPA and manually running `kubectl scale` are equally valid ways to set replica count on an HPA-managed Deployment."** Once an HPA targets a workload, any manual or CI/CD-driven `replicas` change is transient — the HPA controller's next sync will override it back to its own computed value.

## 13. 🔑 Key Takeaways

- HPA adjusts replica count only, computed from `ceil(currentReplicas × (currentMetricValue / desiredMetricValue))`, clamped to configured min/max bounds.
- It depends entirely on the metrics.k8s.io/custom.metrics.k8s.io/external.metrics.k8s.io APIs being populated by a healthy metrics pipeline (§89) — HPA has no built-in metric collection.
- `autoscaling/v2` supports multiple simultaneous metrics (highest-wins resolution) and a `behavior` block for asymmetric scale-up/scale-down policy tuning.
- A Deployment manifest that still hardcodes `replicas` will fight an HPA targeting it on every subsequent apply — remove that field once HPA owns it.
- HPA is one of three distinct autoscaling axes alongside Vertical Pod Autoscaler (resource requests per Pod) and Cluster Autoscaler (node count) — §38 draws that full three-way distinction.

## 14. Related Concepts & What's Next

§27 and §28 established the ReplicaSet/Deployment mechanics that HPA's replica-count patches ultimately act on. §89 (Part 12) covers the metrics pipeline — metrics-server and the custom/external metrics adapter ecosystem — that HPA has a hard, non-optional dependency on. §38 (next) introduces Vertical Pod Autoscaler and Cluster Autoscaler, the two other autoscaling axes that are frequently confused with HPA despite operating on entirely different dimensions (per-Pod resource sizing and node count, respectively, rather than replica count).

**Next Section:** §38 — `Section-38-Part5-Vertical-Pod-Autoscaler-Cluster-Autoscaler.md`
