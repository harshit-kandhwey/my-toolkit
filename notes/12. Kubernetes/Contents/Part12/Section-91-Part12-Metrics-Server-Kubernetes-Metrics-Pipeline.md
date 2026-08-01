# Section 91 (Part 12): Metrics Server and the Kubernetes Metrics Pipeline

## 1. Definition

**Plain language:** `kubectl top pod` and the Horizontal Pod Autoscaler (§37, Part 5) both need to answer the same basic question — "how much CPU and memory is this Pod actually using right now?" — but the API server itself has no built-in mechanism to answer it. Something has to actually go collect that data from every node and make it queryable through the standard Kubernetes API. That something is Metrics Server.

**Precise definition:** **Metrics Server** is a cluster add-on that periodically scrapes CPU and memory usage from every node's kubelet (specifically the kubelet's `/stats/summary` endpoint, which in turn sources data from cAdvisor, the container-runtime-embedded resource monitor), aggregates it in-memory, and exposes it through the Kubernetes API server via the **`metrics.k8s.io`** APIService — a distinct, registered extension API, not part of the core API groups. This is the **resource metrics API**, and it is deliberately narrow in scope: current CPU and memory only, no historical data, no custom application metrics. Kubernetes' broader **metrics pipeline** extends beyond this single narrow API into two additional, separately-implemented APIs: **`custom.metrics.k8s.io`**, populated by an adapter (commonly the Prometheus Adapter) translating metrics already stored in a full time-series system like Prometheus (§92) into per-Pod/per-object values Kubernetes objects can reference, and **`external.metrics.k8s.io`**, populated by a cloud-provider- or system-specific adapter exposing metrics that originate entirely outside the cluster (an SQS queue depth, a cloud load balancer's request count). Metrics Server implements only the first of these three; HPA (§37) and `kubectl top` are the two primary consumers.

## 2. Why This Matters

- **Metrics Server is a strict, non-optional prerequisite for HPA's CPU/memory-based scaling (§37) and for `kubectl top` to return anything at all** — an HPA reporting `<unknown>` targets and a `kubectl top pod` returning "Metrics API not available" are, in the overwhelming majority of real incidents, the exact same root cause: Metrics Server missing, unhealthy, or unreachable, not a bug in the consuming tool.
- **Metrics Server is deliberately not a monitoring system** — it holds no history, has no alerting, and discards data almost immediately after serving it; conflating "I have Metrics Server installed" with "I have observability" is a common and consequential misunderstanding that leaves teams with functioning autoscaling but zero ability to investigate what happened five minutes ago.
- **The three metrics APIs (`metrics.k8s.io`, `custom.metrics.k8s.io`, `external.metrics.k8s.io`) are registered, queryable Kubernetes APIs in their own right**, discoverable and inspectable the same way any other API resource is — understanding this as "just another APIService" rather than a mysterious black box demystifies a large fraction of HPA and `kubectl top` troubleshooting.

🔑 **Key Takeaway:** Metrics Server scrapes CPU/memory from every kubelet and exposes it through the narrow, ephemeral `metrics.k8s.io` API that `kubectl top` and CPU/memory-based HPA (§37) both depend on directly — it holds no history and is not a monitoring solution, which is exactly the gap Prometheus (§92) and the `custom.metrics.k8s.io`/`external.metrics.k8s.io` APIs exist to fill.

## 3. Prerequisites and Dependencies

Builds directly on §90 (the manual diagnostic tools this section's automated pipeline complements rather than replaces) and §9 (kubelet, the actual per-node source of the resource usage data Metrics Server scrapes). Back-references §37 (Horizontal Pod Autoscaler, Part 5, the primary consumer of this exact pipeline, already covered in depth) and forward-references §92 (Prometheus, which fills the historical-data and custom-metrics gap this section identifies).

## 4. Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────┐
│                              Node                                   │
│   cAdvisor (embedded in the container runtime / kubelet)            │
│        │  collects live CPU/memory usage per container              │
│        ▼                                                            │
│   kubelet's /stats/summary endpoint                                 │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ scraped every ~15s (default)
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Metrics Server Pod                           │
│   - aggregates in-memory, per-node and per-Pod                      │
│   - NO persistence, NO history — last scrape only                   │
│   - registers itself as the metrics.k8s.io APIService               │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ served through the API server's
                               │ aggregation layer
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│              metrics.k8s.io API  (Resource Metrics API)             │
│                                                                     │
│   consumed by:                                                      │
│     kubectl top node / kubectl top pod                              │
│     HorizontalPodAutoscaler (type: Resource, cpu/memory) — §37      │
└─────────────────────────────────────────────────────────────────────┘

The BROADER metrics pipeline (Metrics Server covers only the top box):

  metrics.k8s.io           ◄── Metrics Server (THIS section)
  custom.metrics.k8s.io    ◄── Prometheus Adapter, reading from Prometheus (§92)
  external.metrics.k8s.io  ◄── cloud-provider / external-system adapter
```

- **cAdvisor, not Metrics Server, is the actual source of raw usage data** — Metrics Server is a scraper and aggregator sitting one layer above cAdvisor/kubelet, which is why a cAdvisor or kubelet-level failure on a specific node shows up as that node's Pods missing from `kubectl top`, even with Metrics Server itself perfectly healthy.
- **The aggregation layer is what makes `metrics.k8s.io` feel like "just another kubectl/API resource"** — the same API server extension mechanism (an APIService object) that backs custom resources and admission webhooks (§77, Part 10) is what registers Metrics Server's data as a first-class, queryable API.
- **Nothing here is persisted** — a `kubectl top pod` query five minutes after a spike shows only the current, not the historical, usage; anything requiring "what did CPU usage look like at 3 AM" requires the entirely separate Prometheus-based pipeline (§92).

## 5. Hands-On: Installing, Querying, and Diagnosing Metrics Server

### 5.1 Installing Metrics Server and Confirming Registration

**Purpose:** Deploy Metrics Server and verify it has correctly registered the `metrics.k8s.io` APIService.

**Syntax:**

```bash
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

```yaml
# Common self-managed cluster addition to the Deployment's container args
# (kubeadm clusters often need this for kubelet TLS not signed by a public CA)
spec:
  containers:
    - name: metrics-server
      args:
        - --kubelet-insecure-tls # ONLY for clusters with self-signed kubelet certs
        - --kubelet-preferred-address-types=InternalIP
```

**Example usage and expected output:**

```bash
$ kubectl get apiservices | grep metrics
v1beta1.metrics.k8s.io   kube-system/metrics-server   True   45s

$ kubectl get deployment metrics-server -n kube-system
NAME             READY   UP-TO-DATE   AVAILABLE   AGE
metrics-server   1/1     1            1           50s
```

**Production usage example:** `--kubelet-insecure-tls` is a frequent necessity on kubeadm-provisioned or on-prem clusters where kubelet serving certificates aren't signed by a CA Metrics Server trusts by default — it's a real security tradeoff (Metrics Server no longer verifies kubelet identity via TLS), and managed cloud offerings (EKS, GKE, AKS) generally avoid needing it because their kubelet certificates chain to a trusted CA already.

**Common errors:** Installing Metrics Server on a cluster with self-signed kubelet certificates and omitting `--kubelet-insecure-tls`, resulting in the Metrics Server Pod running but its APIService showing `False (FailedDiscoveryCheck)` — a `kubectl describe apiservice v1beta1.metrics.k8s.io` reveals the underlying TLS handshake failure, not an application-level bug.

### 5.2 Querying Resource Metrics Directly and via kubectl top

**Purpose:** Show both the human-facing `kubectl top` interface and the raw API it's built on.

**Syntax:** `kubectl top node|pod [-n <namespace>] [--containers]`

```bash
kubectl top nodes
kubectl top pods -n production --containers
kubectl get --raw "/apis/metrics.k8s.io/v1beta1/namespaces/production/pods" | jq .
```

**Example usage and expected output:**

```bash
$ kubectl top nodes
NAME       CPU(cores)   CPU%   MEMORY(bytes)   MEMORY%
worker-1   340m         17%    2100Mi          54%
worker-2   890m         44%    3400Mi          87%

$ kubectl top pods -n production
NAME                       CPU(cores)   MEMORY(bytes)
web-app-7d4f9c-x8k2p       12m          145Mi
web-app-7d4f9c-9k3lm       15m          151Mi
```

**Production usage example:** `kubectl top node` is frequently the fastest first check when investigating a `NotReady` node or unexplained Pod eviction (§67, Part 9, and §98, Part 13) — high memory percentage on a specific node is often the direct precursor to kubelet-triggered eviction, visible here well before an alert fires from a slower, separately-scraped monitoring pipeline.

**Common errors:** Running `kubectl top pod` immediately (within seconds) after Metrics Server first becomes healthy and seeing `<unknown>` or missing values — the first scrape cycle needs to complete (default ~15-60 seconds depending on version) before any data is available; this is expected startup latency, not a fault.

### 5.3 Diagnosing "Metrics API Not Available"

**Purpose:** Walk the actual failure chain when `kubectl top` returns an error, mirroring the same triage HPA troubleshooting (§37) already relies on.

```bash
$ kubectl top pods
error: Metrics API not available

$ kubectl get apiservices v1beta1.metrics.k8s.io -o yaml | grep -A5 status
status:
  conditions:
    - type: Available
      status: "False"
      reason: FailedDiscoveryCheck
      message: 'failing or missing response from https://10.0.4.12:443/apis/metrics.k8s.io/v1beta1: Get "https://10.0.4.12:443/apis/metrics.k8s.io/v1beta1": dial tcp 10.0.4.12:443: connect: connection refused'

$ kubectl get pods -n kube-system -l k8s-app=metrics-server
NAME                              READY   STATUS             RESTARTS
metrics-server-6d47f9-p8x2k       0/1     CrashLoopBackOff   6
```

**Production usage example:** This exact chain — API not available → APIService condition → Metrics Server Pod status — is the standard triage path for any Metrics Server outage, and is the same underlying root cause an HPA showing `<unknown>` targets (§37) would trace back to; a team maintaining both should treat a Metrics Server health check as a shared, foundational dependency worth its own dedicated alert.

**Common errors:** Assuming a `kubectl top` failure means the cluster itself is unhealthy — in the overwhelming majority of cases it means specifically Metrics Server (a single, optional add-on Deployment) is down, entirely independent of workload or node health otherwise.

## 6. Production Usage Notes

- **Metrics Server's default scrape interval (15s) and short data retention window mean brief, sub-15-second spikes can be entirely invisible to it** — for anything requiring sub-minute-resolution investigation or true historical trending, Prometheus (§92) with its own, independently-configured scrape interval is the correct tool, not Metrics Server.
- **A single Metrics Server replica is a common single point of failure for both `kubectl top` and every CPU/memory-based HPA in the cluster simultaneously** — production clusters commonly run it with `--replicas=2` behind a PodDisruptionBudget (§39, Part 5) precisely because so much depends on its continuous availability.
- **Metrics Server's resource requests are often under-provisioned on large clusters** — its memory usage scales with the number of Pods/nodes being aggregated, and an under-resourced Metrics Server on a several-thousand-Pod cluster can itself become OOMKilled, silently degrading every dependent HPA at once.

## 7. Security Considerations

- **`--kubelet-insecure-tls` disables TLS verification of the kubelet's serving certificate**, meaning Metrics Server can no longer cryptographically confirm it's actually talking to the real kubelet rather than a man-in-the-middle on the node network — acceptable as a pragmatic tradeoff on many self-managed clusters, but a real weakening of the trust chain that should be tracked, not treated as a permanent, unexamined default.
- **The `metrics.k8s.io` API itself exposes resource usage data across the entire cluster to anyone with read access to it**, which is generally low-sensitivity but can still reveal workload scaling patterns or capacity information — RBAC scoping (§74, Part 10) for `pods.metrics.k8s.io`/`nodes.metrics.k8s.io` read access should follow the same least-privilege principle as any other cluster-wide read API.
- **Metrics Server itself needs read access to every node's kubelet API**, making its own ServiceAccount and RBAC bindings a meaningful part of the cluster's trust surface — the same category of scrutiny given to any other cluster-wide, node-reaching component (§76, Part 10).

## 8. Common Troubleshooting Scenarios

| Symptom                                                     | Likely Cause                                                                 | Resolution Path                                                                                             |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------- |
| `kubectl top` returns "Metrics API not available"           | Metrics Server not installed, or its Pod/APIService unhealthy                | `kubectl get apiservices \| grep metrics`, then `kubectl get pods -n kube-system -l k8s-app=metrics-server` |
| `metrics.k8s.io` APIService shows `FailedDiscoveryCheck`    | TLS handshake failure between Metrics Server and kubelet (self-signed certs) | Add `--kubelet-insecure-tls` (accepting the tradeoff) or provision proper kubelet serving certs             |
| HPA shows `<unknown>` for CPU/memory targets (§37)          | Same Metrics Server issue as above, surfaced through a different consumer    | Fix Metrics Server health; HPA will resolve automatically on the next sync once metrics are available       |
| `kubectl top` values look correct but always slightly stale | Expected — Metrics Server serves its last scrape, not real-time data         | Not a fault; reduce `--metric-resolution` if lower staleness is genuinely required, within realistic bounds |

## 9. Best Practices

- Run Metrics Server with at least 2 replicas and a PodDisruptionBudget (§39, Part 5) on any cluster where HPA is in production use — its availability is a shared dependency for every CPU/memory-based HPA at once.
- Treat `--kubelet-insecure-tls` as a tracked, deliberate tradeoff rather than a permanent unexamined default — pursue proper kubelet serving certificates where the cluster's provisioning tooling makes that practical.
- Pair Metrics Server with Prometheus (§92) from the start rather than treating Metrics Server as sufficient observability — they solve genuinely different problems (live scaling signal vs. historical, queryable time-series data).

## 10. Common Anti-Patterns / Mistakes

- **Treating Metrics Server as a monitoring or alerting solution**, then discovering during an incident retrospective that no historical data exists for what happened even five minutes earlier.
- **Running a single, under-resourced Metrics Server replica on a large cluster**, creating a silent single point of failure for both `kubectl top` and every CPU/memory-based HPA simultaneously.
- **Debugging an HPA `<unknown>` target by repeatedly re-editing the HPA object** rather than checking Metrics Server's own health first, when the root cause is almost always the latter.

## 11. Interview Questions

**🎯 Beginner:** _"What does Metrics Server actually do, and what does it explicitly not do?"_
**Model answer:** It periodically scrapes current CPU and memory usage from every node's kubelet (sourced from cAdvisor) and exposes that data through the `metrics.k8s.io` API, which `kubectl top` and CPU/memory-based HPA (§37) both consume directly. It explicitly does not store any history — it holds only the most recent scrape in memory — and it has no alerting, dashboards, or custom metrics support of any kind; it is a narrow, purpose-built data source for exactly those two consumers, not a monitoring system.
_What the interviewer is probing for:_ Clear understanding of Metrics Server's narrow scope, especially the "no history" fact that trips up teams expecting it to double as observability.

**🎯 Intermediate:** _"`kubectl top pod` and an HPA both show missing/`<unknown>` data at the same time. What's the most likely single root cause, and how do you confirm it?"_
**Model answer:** Both symptoms almost always trace back to the same underlying cause — Metrics Server itself is down, unhealthy, or its `metrics.k8s.io` APIService can't reach it — since both `kubectl top` and CPU/memory-based HPA metrics are served through that exact same API. I'd confirm by checking `kubectl get apiservices | grep metrics` for the APIService's `Available` condition, then `kubectl get pods -n kube-system -l k8s-app=metrics-server` for the Pod's actual health, rather than investigating the HPA object or the workload's own resource usage first — the shared dependency is the more likely and more efficient place to look given both symptoms appearing together.
_What the interviewer is probing for:_ Recognizing the shared dependency between two seemingly unrelated symptoms and following the correct diagnostic order (shared infrastructure before individual consumer configuration).

**🎯 Senior:** _"Why might a large cluster's Metrics Server itself become a reliability risk, and how would you mitigate it?"_
**Model answer:** Metrics Server's own memory usage scales with the number of nodes and Pods it's aggregating data for, and a single, under-resourced replica on a several-thousand-Pod cluster can be OOMKilled or simply fall behind on scrape latency — since both `kubectl top` and every CPU/memory-based HPA in the cluster depend on it simultaneously, its failure has an unusually broad blast radius for what looks like "just an add-on." I'd mitigate this with multiple replicas behind a PodDisruptionBudget for availability during node drains or upgrades, explicit and generous resource requests/limits sized against the cluster's actual node/Pod count rather than left at chart defaults, and monitoring Metrics Server's own health (via Prometheus, §92) as a first-class cluster dependency with its own alert, rather than only discovering its degradation indirectly through HPA or `kubectl top` symptoms.
_What the interviewer is probing for:_ Understanding that a small, easily-overlooked add-on can have an outsized blast radius due to how many other subsystems silently depend on it, and concrete operational mitigations beyond "just restart it."

**🎯 Architect:** _"Design the full metrics pipeline strategy for a platform supporting both standard CPU/memory-based autoscaling and custom, application-level autoscaling metrics across many teams."_
**Model answer:** I'd run Metrics Server as a highly-available, dedicated platform component (multiple replicas, PodDisruptionBudget, resource requests sized against real cluster scale) purely for the narrow `metrics.k8s.io` resource-metrics use case — `kubectl top` and CPU/memory HPA — treating it as foundational, always-on cluster infrastructure rather than an optional add-on. For custom, application-level metrics (queue depth, request latency, business-level signals), I'd stand up Prometheus (§92) as the actual time-series store, with the Prometheus Adapter registered against `custom.metrics.k8s.io` as the bridge letting HPA objects reference those metrics using the same API shape as resource metrics. I'd keep the two pipelines architecturally distinct rather than trying to force custom metrics through Metrics Server itself (which fundamentally doesn't support them), and I'd monitor both Metrics Server and the Prometheus Adapter's own health as first-class platform SLOs, since a silent failure in either degrades autoscaling for every team relying on it, often without an obvious, immediate symptom pointing back to the actual root cause.
_What the interviewer is probing for:_ Ability to architect a two-tier metrics strategy — narrow, high-availability resource metrics via Metrics Server, and full-featured custom metrics via Prometheus/Prometheus Adapter — rather than trying to stretch Metrics Server beyond its deliberately narrow design.

## 12. Common Misconceptions

1. **"Metrics Server is a full monitoring solution."** It holds no history and has no alerting or dashboards — it is a narrow, ephemeral data source for `kubectl top` and CPU/memory-based HPA only.
2. **"Installing Metrics Server gives HPA access to custom application metrics."** It only ever exposes CPU and memory via `metrics.k8s.io`; custom metrics require an entirely separate pipeline (Prometheus Adapter and `custom.metrics.k8s.io`, §92).
3. **"An HPA showing `<unknown>` targets means the HPA object is misconfigured."** In the large majority of real cases, it means Metrics Server (or the relevant custom/external adapter) is unhealthy or unreachable, not that the HPA's own spec is wrong.
4. **"`kubectl top` failing indicates a broader cluster health problem."** It specifically indicates Metrics Server (a single, separately-managed add-on) is unavailable — workloads and nodes can be perfectly healthy while `kubectl top` fails entirely.

## 13. 🔑 Key Takeaways

- Metrics Server scrapes CPU/memory from every kubelet (sourced from cAdvisor) and serves it through the `metrics.k8s.io` APIService, consumed directly by `kubectl top` and CPU/memory-based HPA (§37).
- It holds no history and provides no alerting — it is deliberately narrow, and Prometheus (§92) is the correct tool for anything requiring historical or custom application metrics.
- `custom.metrics.k8s.io` and `external.metrics.k8s.io` are separate APIs populated by separate adapters (commonly the Prometheus Adapter), not by Metrics Server itself.
- Metrics Server availability is a shared dependency for both `kubectl top` and every CPU/memory-based HPA simultaneously, making its own reliability (replicas, PodDisruptionBudget, resource sizing) a meaningful production concern.
- `kubectl top` failures and HPA `<unknown>` targets very often share the exact same root cause — Metrics Server health — and should be triaged in that order.

## 14. Related Concepts & What's Next

This section built on §90's manual diagnostic tools and §9's kubelet as the actual data source Metrics Server scrapes, and back-referenced §37 (HPA, Part 5), whose CPU/memory-based scaling depends directly on this exact pipeline. §92, next, covers Prometheus on Kubernetes — ServiceMonitors, Node Exporter, and kube-state-metrics — the full-featured, historical monitoring layer that fills the gap this section identified: everything Metrics Server deliberately does not do.

**Next Section:** §92 — `Section-92-Part12-Prometheus-Kubernetes-ServiceMonitors-Node-Exporter-kube-state-metrics.md`
