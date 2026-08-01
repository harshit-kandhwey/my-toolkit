# Section 93 (Part 12): Grafana Dashboards for Kubernetes

## 1. Definition

**Plain language:** Prometheus (§92) collects and stores metrics as time-series numbers, but a raw PromQL query result is just a table of numbers — useless for spotting a trend, a spike, or a slow degradation at a glance. Grafana is the visualization layer that turns those numbers into dashboards: graphs, gauges, and heatmaps a human can actually look at during an incident and immediately understand.

**Precise definition:** **Grafana** is an open-source observability platform that queries one or more data sources — most commonly, in a Kubernetes context, a **Prometheus** server (§92) — and renders the results as configurable **dashboards** composed of **panels** (graph, gauge, table, heatmap, and stat panel types). Dashboards are defined as **JSON models**, which makes them version-controllable, importable/exportable, and provisionable as code rather than built by hand in a UI every time. Grafana runs in-cluster as a Deployment (typically installed via the `kube-prometheus-stack` Helm chart alongside Prometheus and Alertmanager), reads its dashboard definitions from **ConfigMaps** (§41) or a **Sidecar** container that watches for labeled ConfigMaps, and queries Prometheus using **PromQL** expressions embedded in each panel's configuration.

## 2. Why This Matters

- **Grafana is the visualization half of the observability pair whose collection half was built in §92** — Prometheus without Grafana is functional but operationally unusable at a glance; Grafana without Prometheus (or another data source) has nothing to render, so the two are almost always deployed and reasoned about together.
- **Dashboards-as-code (JSON model provisioning) is what makes Grafana a genuine platform capability rather than a one-off convenience** — a dashboard built by clicking in the UI and never exported is lost the moment the Grafana Pod is rescheduled onto a fresh PersistentVolume without that state, which is precisely why production Grafana deployments provision dashboards via ConfigMap rather than relying on UI-created state.
- **This section is the direct visualization layer for the centralized logging (§94) and distributed tracing (§95) sections that follow** — Grafana itself increasingly renders logs (via Loki) and traces (via Tempo/Jaeger data sources) alongside metrics, making it the common visualization surface across all three observability signal types this Part covers.

🔑 **Key Takeaway:** Grafana queries Prometheus (and other data sources) and renders the results as JSON-defined, version-controllable dashboards — the human-facing visualization layer that makes the metrics §92 collects and stores actually usable during day-to-day operations and live incidents.

## 3. Prerequisites and Dependencies

Builds directly on §92 (Prometheus on Kubernetes — ServiceMonitors, node-exporter, kube-state-metrics), which supplies the metrics Grafana queries, and on §41 (ConfigMaps, Part 6), the mechanism used to provision dashboard JSON declaratively. Sets up §94 (Centralized Logging), where Grafana reappears as a query surface for Loki logs alongside the metrics dashboards this section covers.

## 4. Architecture Diagram

```text
┌──────────────────────────────────────────────────────────────────────────┐
│                         Kubernetes Cluster                               │
│                                                                          │
│  ┌──────────────────┐    scrapes     ┌───────────────────────────┐       │
│  │ node-exporter,   │◄───────────────│      Prometheus           │       │
│  │ kube-state-      │                │  (Deployment/StatefulSet) │       │
│  │ metrics, kubelet │                │  - stores time series     │       │
│  │ (§92)            │                │  - evaluates PromQL       │       │
│  └──────────────────┘                │                           │       │
│                                      └──────────────┬────────────┘       │
│                                                     │ PromQL queries     │
│                                                     ▼                    │
│                                       ┌────────────────────────────┐     │
│                                       │       Grafana              │     │
│                                       │     (Deployment)           │     │
│                                       │ - Data Source: Prometheus  │     │
│                                       │ - Dashboards (JSON models) │     │
│                                       │ - Panels: graph/gauge/table│     │
│                                       └───────────────┬────────────┘     │
│                                                       │ provisioned from │
│                        ┌──────────────────────────────┴─────────────┐    │
│                        │ ConfigMap: grafana-dashboard-cluster-health│    │
│                        │ label: grafana_dashboard=1                 │    │
│                        │ data: dashboard.json                       │    │
│                        └────────────────────────────────────────────┘    │
│                                                                          │
│                        Engineer's browser ◄── Ingress/port-forward       │
└──────────────────────────────────────────────────────────────────────────┘
```

- **Grafana never scrapes anything itself** — it is purely a query-and-render layer sitting on top of Prometheus (or another data source), which is why Grafana being down never affects metric collection, only visualization.
- **Dashboard ConfigMaps labeled `grafana_dashboard=1` are auto-discovered by a sidecar container** running alongside the Grafana Pod (the `grafana-sc-dashboard` sidecar shipped by the `kube-prometheus-stack` chart) — new dashboards appear without restarting Grafana itself.
- **The Data Source configuration (pointing Grafana at the Prometheus Service DNS name) is itself provisionable as a ConfigMap**, meaning a fresh Grafana Pod on a fresh PersistentVolume can reconstruct its entire configuration — data sources and dashboards — purely from cluster state.

## 5. Hands-On: Deploying and Provisioning Grafana

### 5.1 Installing Grafana via the kube-prometheus-stack Helm Chart

**Purpose:** Stand up Prometheus, Alertmanager, and Grafana together as the standard, widely-adopted observability bundle, rather than installing each component individually.

**Syntax:**

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm install kube-prom-stack prometheus-community/kube-prometheus-stack -n monitoring --create-namespace
```

```yaml
# values.yaml excerpt — Grafana-specific overrides
grafana:
  adminPassword: "" # set via a pre-created Secret in production, never inline
  persistence:
    enabled: true
    size: 5Gi
  sidecar:
    dashboards:
      enabled: true
      label: grafana_dashboard
```

**Example usage and expected output:**

```bash
$ kubectl get pods -n monitoring | grep grafana
kube-prom-stack-grafana-6d8f9c9c8f-x2j7k   3/3     Running   0    2m
# 3 containers: grafana, grafana-sc-dashboard (sidecar), grafana-sc-datasources (sidecar)

$ kubectl port-forward -n monitoring svc/kube-prom-stack-grafana 3000:80
Forwarding from 127.0.0.1:3000 -> 3000
```

**Production usage example:** The `kube-prometheus-stack` chart ships a curated set of default dashboards (cluster overview, node exporter, kube-state-metrics) out of the box, which is why most teams start from this chart rather than installing Grafana standalone — the default dashboards alone already cover the majority of day-one operational visibility needs.

**Common errors:** Leaving `adminPassword` unset or defaulted, which the chart otherwise auto-generates and stores in a Secret — teams sometimes lose track of this generated password and end up unable to log in; retrieve it with `kubectl get secret kube-prom-stack-grafana -o jsonpath='{.data.admin-password}' | base64 -d` rather than resetting the whole release.

### 5.2 Provisioning a Dashboard as Code via ConfigMap

**Purpose:** Add a custom dashboard declaratively, so it survives Pod rescheduling and is reviewable in the same Git repository as the rest of cluster configuration.

**Syntax:**

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboard-pod-health
  namespace: monitoring
  labels:
    grafana_dashboard: "1"
data:
  pod-health.json: |
    {
      "title": "Pod Health Overview",
      "panels": [
        {
          "type": "graph",
          "title": "Pods Not Ready",
          "targets": [
            { "expr": "kube_pod_status_ready{condition=\"false\"}" }
          ]
        },
        {
          "type": "stat",
          "title": "CrashLoopBackOff Count",
          "targets": [
            { "expr": "kube_pod_container_status_waiting_reason{reason=\"CrashLoopBackOff\"}" }
          ]
        }
      ]
    }
```

**Example usage and expected output:**

```bash
$ kubectl apply -f pod-health-dashboard-cm.yaml
configmap/grafana-dashboard-pod-health created

$ kubectl logs -n monitoring deploy/kube-prom-stack-grafana -c grafana-sc-dashboard --tail=5
2026-07-31T10:15:03Z INFO  Adding dashboard: pod-health.json
# sidecar picked up the new ConfigMap without a Grafana restart
```

**Production usage example:** Storing this ConfigMap manifest in the same GitOps repository (§88) that manages the rest of cluster configuration means a dashboard change goes through the identical pull-request review process as any other infrastructure change — the dashboard's PromQL expressions are reviewable diffs, not opaque UI clicks nobody can audit after the fact.

**Common errors:** Forgetting the `grafana_dashboard: "1"` label (or whatever label the sidecar was configured to watch, via `sidecar.dashboards.label`) — the ConfigMap applies cleanly with no error, but the dashboard silently never appears in Grafana, since the sidecar only watches labeled ConfigMaps.

### 5.3 Building a PromQL-Driven Panel for Resource Saturation

**Purpose:** Demonstrate a panel expression that directly reuses PromQL patterns from §92's metrics pipeline to visualize a common capacity-planning signal.

**Syntax:**

```text
Panel query (PromQL):
sum(rate(container_cpu_usage_seconds_total{namespace="production"}[5m])) by (pod)
/
sum(kube_pod_container_resource_limits{resource="cpu", namespace="production"}) by (pod)
```

**Example usage and expected output:**

```text
Panel renders as a graph, one line per Pod, showing:
  api-7d9f8-x2k1     0.42   (42% of its CPU limit)
  worker-5c7b6-m9p2  0.91   (91% of its CPU limit — approaching throttling)
```

**Production usage example:** A saturation panel like this, set with a threshold-colored gauge (green below 70%, yellow 70-90%, red above 90%), lets an on-call engineer spot a Pod approaching CPU throttling at a glance during a triage session — visually, this is a direct upgrade over running the equivalent `kubectl top pod` command repeatedly and comparing numbers by eye.

**Common errors:** Building a saturation ratio panel using `resource_requests` instead of `resource_limits` in the denominator — requests represent scheduling guarantees, not the throttling ceiling, so a panel built against requests can show a Pod as "over 100%" in perfectly normal, non-throttled operation (bursting above its request but still under its limit).

## 6. Production Usage Notes

- **Grafana's own state (dashboards not provisioned as ConfigMaps, user accounts, alert rules created via the UI) lives on a PersistentVolume** — losing that volume without prior provisioning-as-code means losing anything created outside of the ConfigMap/sidecar mechanism, which is the strongest practical argument for provisioning everything meaningful as code from day one.
- **Grafana can alert directly (Grafana-managed alert rules) as an alternative to Alertmanager-based alerting** — teams increasingly consolidate on one or the other rather than running both, since maintaining alert rules in two disconnected systems is a common source of duplicate or conflicting pages.
- **Folder-based organization (Grafana folders, distinct from Kubernetes namespaces) is the standard way to scope dashboard visibility and edit permissions per team** in a shared, multi-tenant Grafana instance serving many application teams from a single platform deployment.

## 7. Security Considerations

- **Grafana's own RBAC (Viewer/Editor/Admin roles, folder permissions) is entirely separate from Kubernetes RBAC (§74–§75)** — a user with cluster-admin Kubernetes access has no implicit Grafana permissions at all, and vice versa; these two authorization systems must be configured and audited independently.
- **The default admin credentials generated by the Helm chart must be rotated or sourced from a proper secrets-management pipeline** (external Secrets Operator, Vault) rather than left as the chart-generated default, especially if the Grafana Ingress is internet-facing.
- **Dashboards can leak sensitive operational detail (internal hostnames, capacity numbers, business metrics) if exposed without authentication** — a Grafana instance reachable without login, even "just for viewing," is a real information-disclosure risk in a production environment.

## 8. Common Troubleshooting Scenarios

| Symptom                                                 | Cause                                                                             | Fix                                                                                                               |
| ------------------------------------------------------- | --------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| Dashboard ConfigMap applied but panel never appears     | Missing or wrong `grafana_dashboard` label the sidecar is configured to watch     | Confirm the label matches `sidecar.dashboards.label` in the Helm values; re-check spelling                        |
| Panel shows "No data"                                   | PromQL expression references a metric name that doesn't exist or wrong label      | Run the same expression directly in Prometheus's own UI/`/graph` endpoint to isolate the query from the rendering |
| Grafana login lost after Pod rescheduled                | No PersistentVolume attached, or dashboards/users existed only in ephemeral state | Attach persistent storage; migrate to ConfigMap-based dashboard provisioning                                      |
| Saturation panel shows values consistently over 100%    | Panel divides by `resource_requests` instead of `resource_limits`                 | Correct the PromQL denominator to use `kube_pod_container_resource_limits`                                        |
| Two teams see conflicting dashboards with the same name | Dashboard folders/permissions not scoped per team in a shared instance            | Use Grafana folder-level permissions to isolate visibility, or separate Grafana instances per major tenant        |

## 9. Best Practices

- Provision every dashboard meant to survive a restart as a ConfigMap in Git, never rely on UI-created, unexported dashboards for anything operationally important.
- Build saturation and utilization panels against `resource_limits`, not `resource_requests`, to correctly reflect the actual throttling/OOM ceiling.
- Rotate the Grafana admin credential out of the Helm-chart default and integrate it with the organization's real secrets pipeline before exposing Grafana beyond a local port-forward.

## 10. Common Anti-Patterns / Mistakes

- **Building dashboards exclusively through the UI with no export/ConfigMap backup**, losing them the moment the Grafana Pod moves to a fresh volume.
- **Confusing Grafana's own Viewer/Editor/Admin RBAC with Kubernetes RBAC**, assuming cluster-admin access implies Grafana admin access or vice versa.
- **Leaving a Grafana instance reachable without authentication "just for convenience,"** exposing internal operational detail to anyone who can reach the Ingress.

## 11. Interview Questions

**🎯 Beginner:** _"What is the relationship between Prometheus and Grafana?"_
**Model answer:** Prometheus is the data source — it scrapes and stores time-series metrics and can evaluate PromQL queries against them. Grafana is a separate visualization layer that queries Prometheus (or other data sources) and renders the results as dashboards with graph, gauge, and table panels. Grafana never collects metrics itself; it's purely a query-and-render tool sitting on top of a data source like Prometheus.
_What the interviewer is probing for:_ Clear separation between the collection layer (§92) and the visualization layer (this section), rather than conflating the two tools.

**🎯 Intermediate:** _"How would you ensure a custom Grafana dashboard survives a Pod restart or rescheduling?"_
**Model answer:** I'd never rely on a dashboard built purely through the Grafana UI, since that state lives on the Grafana Pod's PersistentVolume and is lost if that volume isn't preserved or if the dashboard was never exported. Instead, I'd export the dashboard's JSON model and provision it as a ConfigMap labeled with whatever key the deployment's dashboard sidecar is configured to watch (commonly `grafana_dashboard: "1"`) — the sidecar auto-discovers and loads it without a Grafana restart, and because it's a ConfigMap in Git, it survives any Pod lifecycle event and is reviewable like any other infrastructure change.
_What the interviewer is probing for:_ Practical knowledge of dashboards-as-code provisioning, not just that Grafana "has dashboards."

**🎯 Senior:** _"A dashboard panel shows a Pod's CPU usage consistently over 100% of its 'allocation.' What's the likely bug, and why does it matter?"_
**Model answer:** This is almost always a panel built dividing CPU usage by `kube_pod_container_resource_requests` instead of `kube_pod_container_resource_limits`. Requests represent a scheduling guarantee, not a hard ceiling — a Pod can legitimately burst well above its request (assuming spare node capacity) without being throttled at all, so a request-based denominator will show apparently-alarming numbers during entirely normal operation. The fix is to point the panel at the limits metric instead, since limits are the actual value the CFS bandwidth controller enforces and beyond which throttling (or an OOM kill, for memory) occurs. This matters because a mis-built panel like this trains on-call engineers to either ignore a real signal (alert fatigue from constant false "over-100%" panels) or chase a saturation problem that isn't actually happening.
_What the interviewer is probing for:_ Understanding the semantic difference between requests and limits (§46, Part 6) as it concretely manifests in dashboard correctness, not just abstract recall of the definitions.

**🎯 Architect:** _"Design the Grafana strategy for a platform supporting 40 application teams, each wanting their own dashboards, with a shared underlying Prometheus."_
**Model answer:** I'd run a single, centrally-managed Grafana instance backed by the shared Prometheus (or Thanos/Cortex if scale demands global query federation across multiple Prometheus instances) rather than 40 individual Grafana deployments, since a shared instance amortizes operational overhead and lets platform-wide dashboards (cluster health, node saturation) live alongside team-specific ones in one place. I'd use Grafana folders with per-team edit permissions (mapped from the organization's SSO groups via Grafana's OAuth/LDAP integration) so each team can build and own dashboards scoped to their own namespace's metrics without needing platform-team involvement for every change, while restricting who can edit shared, platform-owned dashboards. Every dashboard meant to be durable would be provisioned as a ConfigMap in that team's own GitOps repository rather than created ad hoc in the UI, keeping dashboard changes in the same review pipeline as the rest of their infrastructure. I'd also set up dashboard JSON linting in CI (checking for the requests-vs-limits mistake above, for instance) before it merges, and establish a small set of platform-blessed dashboard templates (a Pod-health template, a Service-latency template) that teams can fork rather than building every panel from scratch, keeping visual and semantic consistency across 40 otherwise-independent teams' dashboards.
_What the interviewer is probing for:_ Ability to design Grafana as a genuinely multi-tenant platform capability — permissions, provisioning pipeline, and template consistency — rather than assuming a single-team deployment model scales unchanged to 40 teams.

## 12. Common Misconceptions

1. **"Grafana stores metrics."** It does not — Grafana is purely a query-and-visualization layer; the actual time-series data lives in Prometheus (or whichever data source is configured).
2. **"A dashboard built in the Grafana UI is automatically safe from data loss."** Unless it's exported and provisioned as a ConfigMap (or otherwise version-controlled), UI-created dashboards live only on the Grafana Pod's PersistentVolume and can be lost.
3. **"Kubernetes RBAC governs who can edit Grafana dashboards."** Grafana has its own independent RBAC (Viewer/Editor/Admin, folder permissions) entirely separate from Kubernetes' RBAC system.
4. **"CPU usage over 100% of a Pod's allocation always signals a real capacity problem."** It depends entirely on whether the denominator is requests (a soft guarantee, bursting above which is normal) or limits (the actual enforced ceiling) — the two produce very different, easily-confused signals.

## 13. 🔑 Key Takeaways

- Grafana is the visualization layer over Prometheus (§92) — it queries and renders, but never collects or stores metrics itself.
- Dashboards should be provisioned as ConfigMaps (dashboards-as-code) rather than built solely in the UI, so they survive Pod rescheduling and are reviewable in Git.
- Grafana's own RBAC is entirely separate from Kubernetes RBAC and must be configured and audited independently.
- Saturation/utilization panels must be built against `resource_limits`, not `resource_requests`, to avoid misleading "over 100%" readings during normal bursting.
- A shared, centrally-managed Grafana instance with folder-based per-team permissions scales better across many teams than one Grafana deployment per team.

## 14. Related Concepts & What's Next

This section built directly on §92's Prometheus metrics pipeline, turning the raw time-series data collected there into human-usable dashboards, and used §41's ConfigMap mechanism as the dashboards-as-code provisioning path. §94, next, extends the observability story from metrics to logs — covering Fluentd/Fluent Bit, Loki, and the EFK stack as the centralized logging equivalent of what Prometheus and Grafana provide for metrics, and Grafana itself reappears there as a query surface for Loki-backed log data.

**Next Section:** §94 — `Section-94-Part12-Centralized-Logging-Patterns-Fluentd-FluentBit-Loki-EFK.md`
