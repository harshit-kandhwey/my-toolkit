# Section 92 (Part 12): Prometheus on Kubernetes: ServiceMonitors, Node Exporter, kube-state-metrics

## 1. Definition

**Plain language:** Metrics Server (§91) answers "how much CPU is this Pod using right now" and then immediately forgets the answer. Real operational work — capacity planning, incident postmortems, alerting on a slow memory leak over six hours, dashboards showing a week-over-week traffic trend — needs that data remembered, queryable, and combinable across time and across many different sources. Prometheus is the tool the Kubernetes ecosystem converged on to do exactly that.

**Precise definition:** **Prometheus** is a time-series monitoring system that works by **pulling** (scraping) metrics from HTTP endpoints on a configured interval and storing them in its own on-disk time-series database, queryable via **PromQL**. On Kubernetes, the **Prometheus Operator** manages Prometheus deployments declaratively through Custom Resource Definitions (§85, Part 11), the most important being the **ServiceMonitor** — a CRD that declares "scrape any Pod behind this Service, on this port, at this path, every N seconds" — letting Prometheus's actual scrape target list be derived automatically from Kubernetes Service/Pod labels rather than hand-maintained as a static config file. Three components together give Prometheus visibility into the whole cluster: the metrics endpoints applications expose directly (custom application metrics via a Prometheus client library), **Node Exporter**, a DaemonSet (§34, Part 5) running one Pod per node that exposes host-level metrics (CPU, memory, disk, network at the OS level) Kubernetes itself doesn't expose, and **kube-state-metrics**, a Deployment that watches the Kubernetes API server itself and exposes cluster **object state** as metrics (deployment replica counts, Pod phase, PVC status) — not resource usage, but the state of Kubernetes objects themselves.

## 2. Why This Matters

- **Prometheus is the historical-data and custom-metrics layer that Metrics Server (§91) explicitly does not provide** — the two aren't competitors; a production cluster typically runs both, with Metrics Server serving the narrow live-scaling use case and Prometheus serving everything requiring history, alerting, dashboards, or custom application-level signals.
- **ServiceMonitors turn scrape configuration from a static, hand-maintained file into a declarative, per-application Kubernetes object** — a team can add monitoring to a new Service by applying a ServiceMonitor alongside their Deployment, with zero changes to Prometheus's own configuration or a central platform team's involvement, which is the single biggest reason the Prometheus Operator model displaced hand-rolled Prometheus configs in Kubernetes environments.
- **kube-state-metrics and Node Exporter answer two categorically different questions that are easy to conflate** — "is my Deployment's desired replica count actually matched by ready replicas" (kube-state-metrics, object state) versus "is this node's disk about to fill up" (Node Exporter, host-level resource usage) — and dashboards or alerts built assuming the wrong source produce confusing gaps.

🔑 **Key Takeaway:** Prometheus pulls and stores time-series metrics via scraping, with the Prometheus Operator's ServiceMonitor CRD making scrape target discovery declarative and Kubernetes-native; Node Exporter supplies host-level OS metrics per node and kube-state-metrics supplies Kubernetes object-state metrics, together filling the historical, custom-metrics, and object-state gaps that Metrics Server (§91) deliberately leaves open.

## 3. Prerequisites and Dependencies

Builds directly on §91 (Metrics Server, whose narrow scope and lack of history motivate this section's full monitoring stack) and §34 (DaemonSets, Part 5, the workload type Node Exporter is deployed as, one Pod per node). Assumes familiarity with §85 (Custom Resource Definitions, Part 11, since ServiceMonitor is itself a CRD introduced by the Prometheus Operator) and §50 (Services, Part 7, whose label selectors ServiceMonitors reuse to discover scrape targets).

## 4. Architecture Diagram

```text
┌─────────────────────────────────────────────────────────────────────┐
│                          Prometheus Operator                        │
│         watches ServiceMonitor / PodMonitor CRDs (§85)              │
│         and reconciles Prometheus's actual scrape config            │
└──────────────────────────────┬──────────────────────────────────────┘
                               │ generates scrape config
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        Prometheus Server (StatefulSet, §33)         │
│   - scrapes (PULLS) targets on a configured interval                │
│   - stores time series in its own on-disk TSDB                      │
│   - queryable via PromQL                                            │
└──────────────┬─────────────────────┬─────────────────────┬──────────┘
               │ scrapes             │ scrapes             │ scrapes
               ▼                     ▼                     ▼
   ┌────────────────────┐ ┌──────────────────┐ ┌─────────────────────┐
   │ Application Pods   │ │ Node Exporter    │ │ kube-state-metrics  │
   │ (custom /metrics   │ │ (DaemonSet, §34, │ │ (Deployment,        │
   │  endpoint via a    │ │  1 per node)     │ │  watches API server)│
   │  Prometheus client │ │  → CPU/mem/disk/ │ │  → object STATE:    │
   │  library)          │ │    network at the│ │    replica counts,  │
   │                    │ │    HOST/OS level │ │    Pod phase, PVC   │
   │                    │ │                  │ │    status, etc.     │
   └────────────────────┘ └──────────────────┘ └─────────────────────┘

   ServiceMonitor CRD example (declares WHAT to scrape, derived from labels):
   ┌───────────────────────────────────────────────────┐
   │ selector: matchLabels: { app: web-app }           │
   │ endpoints: [ { port: metrics, interval: 30s } ]   │
   └───────────────────────────────────────────────────┘
   → Prometheus Operator finds every Service matching  app: web-app
     and auto-generates scrape targets from its Endpoints, no manual
     Prometheus config edit required.
```

- **Prometheus's pull model is the opposite of a push-based system** — targets expose a `/metrics` HTTP endpoint and wait; Prometheus initiates every scrape, which is precisely why a target must be network-reachable from Prometheus's own Pod, not the other way around.
- **ServiceMonitors don't scrape anything themselves** — they are pure configuration objects the Prometheus Operator reads and translates into Prometheus's actual scrape config; the real scraping is still done by the Prometheus server Pod itself.
- **Node Exporter and kube-state-metrics are scraped exactly like any application's custom `/metrics` endpoint** — from Prometheus's perspective there's no special-casing; they're just two more scrape targets, discovered via their own ServiceMonitors like anything else.

## 5. Hands-On: Deploying and Wiring the Monitoring Stack

### 5.1 A ServiceMonitor for an Application's Custom Metrics

**Purpose:** Let Prometheus automatically discover and scrape a new application's `/metrics` endpoint with zero manual Prometheus configuration.

**Syntax:**

```yaml
# The application's own Service (must expose the metrics port)
apiVersion: v1
kind: Service
metadata:
  name: web-app
  labels:
    app: web-app
spec:
  selector:
    app: web-app
  ports:
    - name: metrics
      port: 9090
      targetPort: 9090
---
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: web-app-monitor
  labels:
    release: prometheus # must match the Prometheus CR's serviceMonitorSelector
spec:
  selector:
    matchLabels:
      app: web-app
  endpoints:
    - port: metrics # matches the Service's named port above
      path: /metrics
      interval: 30s
```

**Example usage and expected output:**

```bash
$ kubectl apply -f web-app-servicemonitor.yaml
servicemonitor.monitoring.coreos.com/web-app-monitor created

$ kubectl port-forward svc/prometheus-operated 9090:9090 -n monitoring &
$ curl -s localhost:9090/api/v1/targets | jq '.data.activeTargets[] | select(.labels.job=="web-app")'
{
  "labels": { "job": "web-app", "instance": "10.244.1.7:9090" },
  "health": "up"
}
```

**Production usage example:** This ServiceMonitor-per-application pattern is what lets application teams own their own monitoring configuration alongside their Deployment manifest in the same GitOps repository (§88, Part 11) — no ticket to a platform team, no central Prometheus config file edit, and the new scrape target simply appears the next time the Prometheus Operator reconciles.

**Common errors:** Forgetting the `release: prometheus` (or equivalent) label that must match the Prometheus custom resource's own `serviceMonitorSelector` — a syntactically valid ServiceMonitor with the wrong (or missing) selector label is silently ignored by the Prometheus Operator, producing no error but also no scraping, a very common "why isn't my metric showing up" support case.

### 5.2 Node Exporter as a DaemonSet

**Purpose:** Expose host-level OS metrics (disk, network, CPU, memory at the kernel level) that neither the application nor Kubernetes itself expose.

**Syntax:**

```yaml
apiVersion: apps/v1
kind: DaemonSet
metadata:
  name: node-exporter
  namespace: monitoring
spec:
  selector:
    matchLabels:
      app: node-exporter
  template:
    metadata:
      labels:
        app: node-exporter
    spec:
      hostNetwork: true # binds directly to the node's network namespace
      hostPID: true
      containers:
        - name: node-exporter
          image: prom/node-exporter:v1.7.0
          args:
            - --path.rootfs=/host
          volumeMounts:
            - name: rootfs
              mountPath: /host
              readOnly: true
      volumes:
        - name: rootfs
          hostPath:
            path: /
```

**Example usage and expected output:**

```bash
$ kubectl get daemonset node-exporter -n monitoring
NAME            DESIRED   CURRENT   READY   NODE SELECTOR   AGE
node-exporter   4         4         4       <none>          2m

$ curl -s http://worker-1:9100/metrics | grep node_filesystem_avail_bytes | head -2
node_filesystem_avail_bytes{device="/dev/sda1",mountpoint="/"} 4.2109440e+10
```

**Production usage example:** `node_filesystem_avail_bytes` and `node_memory_MemAvailable_bytes` are the standard signals behind disk-pressure and memory-pressure alerting — the same underlying conditions that eventually trigger kubelet-level node eviction (§67, Part 9) are visible here, from Node Exporter, well before Kubernetes' own eviction mechanism engages, giving operators lead time to react.

**Common errors:** Deploying Node Exporter without `hostNetwork: true` and `hostPID: true` — without direct access to the host's network and process namespaces, Node Exporter reports the container's own isolated view rather than genuine host-level metrics, silently producing meaningless or misleading data rather than an obvious error.

### 5.3 kube-state-metrics for Object State

**Purpose:** Expose Kubernetes object state (not resource usage) as Prometheus metrics — replica counts, Pod phase, PVC binding status.

**Syntax:**

```bash
kubectl apply -f https://github.com/kubernetes/kube-state-metrics/releases/latest/download/standard-manifests.yaml
```

```promql
# Deployments where desired replicas don't match available replicas — a classic alerting rule
kube_deployment_spec_replicas != kube_deployment_status_replicas_available
```

**Example usage and expected output:**

```bash
$ curl -s http://kube-state-metrics.monitoring:8080/metrics | grep kube_deployment_status_replicas_available | head -1
kube_deployment_status_replicas_available{deployment="web-app",namespace="production"} 2

$ curl -s http://kube-state-metrics.monitoring:8080/metrics | grep kube_pod_status_phase | grep Pending
kube_pod_status_phase{namespace="production",pod="worker-9k2p",phase="Pending"} 1
```

**Production usage example:** `kube_deployment_spec_replicas != kube_deployment_status_replicas_available` sustained for more than a few minutes is a standard, high-signal Prometheus alerting rule — it catches a Deployment that's stuck under-provisioned (a failed rollout, an unschedulable Pod) purely from object state, with no dependency on the application's own metrics being instrumented at all.

**Common errors:** Confusing kube-state-metrics' `kube_pod_status_phase` (an object-state field Kubernetes itself reports) with actual resource consumption — a Pod can be `Running` per kube-state-metrics while still using excessive CPU per Metrics Server (§91) or Node Exporter; these are answering entirely different questions and neither substitutes for the other.

## 6. Production Usage Notes

- **Prometheus's on-disk TSDB has a default local retention window (commonly 15 days) and is not itself horizontally scalable or highly available out of the box** — long-term retention and multi-cluster aggregation typically require a remote-write target (Thanos, Cortex, Mimir, or a managed equivalent), which is a common, deliberate next step once a single Prometheus instance's local storage becomes the binding constraint.
- **`kube-state-metrics` and `Node Exporter` are near-universal cluster additions, typically bundled by the `kube-prometheus-stack` Helm chart alongside the Prometheus Operator itself** — most production clusters install all of these together rather than piecing together the operator, exporters, and CRDs independently.
- **A ServiceMonitor's `interval` should be set deliberately, not left uniformly aggressive across every target** — scraping a low-cardinality, cheap-to-produce metrics endpoint every 15 seconds is harmless, but doing the same against an expensive-to-compute custom metrics endpoint across hundreds of Pod replicas is a real, avoidable load source on both the target application and Prometheus's own ingestion pipeline.

## 7. Security Considerations

- **Node Exporter's `hostNetwork: true` and `hostPID: true` are genuinely privileged settings**, granting visibility into the host's full process list and network namespace — the same category of scrutiny given to any other host-level-access component (§45, Part 6) should apply, and Node Exporter's own container should still run with the least additional privilege beyond what those two settings require (no root filesystem write access, no additional capabilities).
- **Prometheus itself, by scraping essentially every workload in the cluster, accumulates a broad view of application-level metrics that can inadvertently include sensitive labels or values** if application teams aren't careful about what they expose on their `/metrics` endpoint — treat `/metrics` endpoints as semi-public within the cluster's network boundary and avoid embedding secrets or PII in metric labels.
- **The Prometheus UI and API, if exposed beyond the cluster's internal network without authentication**, expose the entirety of scraped metrics (including kube-state-metrics' full object inventory) to anyone reaching that endpoint — Prometheus should sit behind the same NetworkPolicy (§55, Part 7) and ingress authentication controls as any other internal, cluster-wide-visibility service.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                          | Likely Cause                                                                               | Resolution Path                                                                                               |
| -------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------- |
| A new ServiceMonitor is applied but the target never appears in Prometheus       | Label mismatch between the ServiceMonitor and the Prometheus CR's `serviceMonitorSelector` | Confirm the ServiceMonitor's own labels match exactly what the Prometheus CR selects for                      |
| Node Exporter metrics look identical to the container's own view, not the host's | Missing `hostNetwork: true` / `hostPID: true` on the DaemonSet                             | Add both fields; Node Exporter requires direct host namespace access to report genuine OS-level metrics       |
| `kube_deployment_status_replicas_available` stuck below desired                  | Underlying Deployment rollout issue (unschedulable Pods, failing readiness, §89)           | Investigate the Deployment/Pods directly (§28, §89); kube-state-metrics is correctly reporting a real problem |
| Prometheus scrape target shows `health: down`                                    | Target's `/metrics` endpoint unreachable, wrong port, or NetworkPolicy blocking            | `kubectl exec` (§90) into Prometheus's Pod or a debug Pod to test reachability directly to the target's port  |

## 9. Best Practices

- Adopt the `kube-prometheus-stack` Helm chart (or equivalent) to install the Prometheus Operator, Node Exporter, kube-state-metrics, and default dashboards/alerts together, rather than assembling each piece independently from scratch.
- Let application teams own and version their own ServiceMonitor objects alongside their Deployment manifests in the same GitOps repository (§88), rather than centralizing scrape configuration ownership with a platform team.
- Set ServiceMonitor `interval` deliberately per target's actual cost and required freshness, and plan for long-term retention (Thanos/Cortex/Mimir or a managed equivalent) before local Prometheus storage becomes a binding constraint, not after.

## 10. Common Anti-Patterns / Mistakes

- **Treating Metrics Server and Prometheus as redundant and running only one** — they serve genuinely different purposes (live scaling signal vs. historical, alertable, custom-metric-capable monitoring), and a production cluster typically needs both.
- **Deploying Node Exporter without `hostNetwork`/`hostPID`**, silently collecting meaningless containerized metrics instead of genuine host-level data, often undetected until a host-level incident reveals the gap.
- **Exposing the Prometheus UI/API without authentication or network restriction**, leaking a broad, cluster-wide metrics inventory (including kube-state-metrics' full object state) to anyone who can reach the endpoint.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between Node Exporter and kube-state-metrics?"_
**Model answer:** Node Exporter runs as a DaemonSet, one Pod per node, and exposes host-level operating system metrics — CPU, memory, disk, and network usage at the kernel level, things Kubernetes itself has no direct visibility into. kube-state-metrics runs as a single Deployment and instead watches the Kubernetes API server, exposing the **state** of Kubernetes objects themselves as metrics — a Deployment's desired versus available replica count, a Pod's current phase, a PVC's binding status — not resource usage at all. They answer entirely different categories of question and are both typically scraped by the same Prometheus instance.
_What the interviewer is probing for:_ Clear understanding that these two components serve different metric categories (host resource usage vs. Kubernetes object state) rather than being interchangeable or redundant.

**🎯 Intermediate:** _"A team applies a syntactically correct ServiceMonitor but their application's metrics never appear in Prometheus. What's the most common cause, and how do you check it?"_
**Model answer:** The most common cause is a label selector mismatch — the ServiceMonitor's own metadata labels must match the Prometheus custom resource's `serviceMonitorSelector` (commonly something like `release: prometheus`), or the Prometheus Operator will simply never pick up that ServiceMonitor at all, with no error surfaced anywhere. I'd check the Prometheus CR's `spec.serviceMonitorSelector` directly and compare it against the ServiceMonitor's own labels, then separately confirm the ServiceMonitor's own `selector.matchLabels` correctly targets the application's Service. Only after confirming both label-matching layers would I look at network reachability or the application's `/metrics` endpoint itself.
_What the interviewer is probing for:_ Awareness of the two distinct label-matching layers involved (Prometheus-to-ServiceMonitor, and ServiceMonitor-to-Service) and the correct order to check them in, since this is the single most common real-world ServiceMonitor support case.

**🎯 Senior:** _"Why does Prometheus's default architecture become a scaling problem for a large, long-lived cluster, and what's the standard remediation?"_
**Model answer:** A single Prometheus instance stores its time series on local disk with a default, relatively short retention window, and it isn't horizontally scalable on its own — as cluster size and metric cardinality grow (more Pods, more custom metrics, more labels), both ingestion load and local storage requirements grow with it, and a single instance eventually becomes a capacity and reliability bottleneck, with no built-in high availability beyond running a second, independently-scraping replica. The standard remediation is layering a long-term storage and federation system on top — Thanos, Cortex, or Mimir (or a managed equivalent) — which lets multiple Prometheus instances remote-write into shared, horizontally-scalable long-term storage, decoupling retention and query scale from any single Prometheus Pod's local disk, while still letting each Prometheus instance do the actual near-real-time scraping it's designed for.
_What the interviewer is probing for:_ Understanding Prometheus's genuine architectural limitations at scale (single-node storage, limited built-in HA) and the standard ecosystem answer (Thanos/Cortex/Mimir) rather than assuming Prometheus alone scales indefinitely.

**🎯 Architect:** _"Design the observability metrics strategy for a platform running many teams' applications across several clusters, balancing team autonomy with platform-wide consistency."_
**Model answer:** I'd deploy the Prometheus Operator via `kube-prometheus-stack` in every cluster as standard platform infrastructure, bundling Node Exporter and kube-state-metrics by default so every cluster has consistent host-level and object-state visibility with zero per-team setup. I'd let application teams own their own ServiceMonitor objects, versioned in the same GitOps repository (§88) as their Deployment manifests, giving them full autonomy to instrument and expose whatever custom metrics matter to their service without needing platform-team involvement for each new scrape target — while enforcing, via a policy engine (§77, Part 10), that every ServiceMonitor carries the platform's required `release` selector label so nothing silently fails to register. For cross-cluster, long-term visibility, I'd remote-write every cluster's Prometheus into a shared Thanos or Mimir deployment, giving a single, federated query surface for cross-cluster dashboards and long-term capacity trending without requiring any single Prometheus instance to retain more data locally than its own cluster's near-term operational needs require. Finally, I'd pair this with Metrics Server (§91) in every cluster specifically for the narrow live-scaling use case HPA (§37) needs, keeping that dependency deliberately decoupled from the broader, richer Prometheus stack so a Prometheus outage never affects autoscaling responsiveness.
_What the interviewer is probing for:_ Ability to design a multi-cluster, multi-team observability architecture balancing team-level autonomy (ServiceMonitor ownership) with platform-wide consistency (bundled exporters, enforced labels, federated long-term storage), plus recognition that Metrics Server and Prometheus should remain deliberately decoupled.

## 12. Common Misconceptions

1. **"Prometheus and Metrics Server are redundant, so a cluster only needs one."** They solve different problems — Metrics Server is a narrow, ephemeral source for live CPU/memory scaling decisions; Prometheus is a full historical, alertable, custom-metric-capable monitoring system — and production clusters typically run both.
2. **"kube-state-metrics reports resource usage, like CPU or memory."** It reports Kubernetes **object state** only — replica counts, Pod phase, PVC status — with zero awareness of actual resource consumption; that's Node Exporter's and Metrics Server's domain instead.
3. **"A ServiceMonitor scrapes metrics itself."** It is a pure configuration object the Prometheus Operator translates into Prometheus's own scrape config — the actual scraping is still performed by the Prometheus server Pod.
4. **"Node Exporter works correctly as a regular, non-privileged Pod."** Without `hostNetwork: true` and `hostPID: true`, it reports only its own container's isolated view rather than genuine host-level OS metrics, silently producing misleading data rather than an obvious failure.

## 13. 🔑 Key Takeaways

- Prometheus pulls (scrapes) metrics on an interval and stores them in a queryable time-series database, filling the historical-data and custom-metrics gap Metrics Server (§91) deliberately leaves open.
- The Prometheus Operator's ServiceMonitor CRD makes scrape target discovery declarative and Kubernetes-native, letting application teams own their own monitoring configuration without central Prometheus config edits.
- Node Exporter (a DaemonSet requiring `hostNetwork`/`hostPID`) supplies host-level OS metrics per node; kube-state-metrics (a Deployment watching the API server) supplies Kubernetes object-state metrics — the two answer categorically different questions.
- A single Prometheus instance's local storage and lack of built-in horizontal scalability become a real constraint at cluster scale, typically remediated with Thanos, Cortex, or Mimir for long-term, federated storage.
- Metrics Server and Prometheus should remain deliberately decoupled — a Prometheus outage should never affect HPA's autoscaling responsiveness, and vice versa.

## 14. Related Concepts & What's Next

This section built on §91's Metrics Server (the narrow pipeline this section's full monitoring stack complements) and §34's DaemonSet mechanics (the workload type backing Node Exporter), and assumed familiarity with §85's CRD concepts (since ServiceMonitor is itself a CRD) and §50's Service label selectors (which ServiceMonitors reuse for target discovery). §93, next, moves from raw metrics collection to visualization — Grafana dashboards built directly on top of the Prometheus data this section established as the cluster's queryable time-series source of truth.

**Next Section:** §93 — `Section-93-Part12-Grafana-Dashboards-Kubernetes.md`
