# 00 — Roadmap: Prometheus (Complete Topic Roadmap)

## 0. Assumption Line

Prometheus is treated in its most common **DevOps / Cloud / SRE / Observability Engineering** interpretation: Prometheus as a production metrics-collection, storage, querying, and alerting system built on the pull model — covering architecture and the TSDB, PromQL from first principles through advanced query patterns, the exporter and client-library ecosystem, service discovery, Alertmanager and alerting design, recording rules and performance tuning, federation and long-term storage (remote-write, Thanos/Cortex/Mimir at a conceptual level), Grafana integration, Kubernetes-native deployment via the Prometheus Operator, and production operation at scale. This roadmap runs **99 sections across 14 parts** — deliberately smaller than broader platform tracks in this repo (Linux's 125, Ansible's 119) because Prometheus is a focused, single-purpose tool rather than a sprawling platform, and this roadmap does not pad section count to match unrelated topics.

This repo already has a 141-section Kubernetes knowledge base at `notes/12. Kubernetes/`, including a Part 12 "Observability" section that covers the Metrics Server pipeline and a survey-level introduction to running Prometheus and Grafana on Kubernetes plus centralized logging. This roadmap does **not** re-teach that material. It assumes the reader has seen that survey (or will read it as a companion) and instead goes deep on Prometheus itself: PromQL mastery, the exporter ecosystem, Alertmanager internals, and production-grade scaling patterns — with Kubernetes-native Prometheus (Operator, ServiceMonitor, kube-prometheus-stack) treated as its own dedicated Part rather than duplicated survey content.

Because Prometheus spans query language, storage internals, alerting design, and Kubernetes-native operation, this project is split into **named Parts**, generated sequentially. Do not ask which part to start with — Part 1 begins immediately after this roadmap.

---

## 1. Complete Numbered Roadmap

### Part 1 — Foundations and the Pull-Based Monitoring Model

1.1 What Prometheus Is; Monitoring vs. Observability vs. Alerting
1.2 History: Google Borgmon → Prometheus → CNCF Graduation
1.3 The Pull Model vs. the Push Model — Architecture Philosophy and Tradeoffs
1.4 Prometheus vs. Nagios/Zabbix/Datadog/InfluxDB — Positioning
1.5 Core Concepts Overview: Metrics, Labels, Time Series, and Samples
1.6 The Prometheus Ecosystem Map (Server, Exporters, Alertmanager, Client Libraries, Pushgateway)
1.7 Prerequisites Recap and How This Roadmap Relates to the Kubernetes Observability Survey

### Part 2 — Architecture and the TSDB

2.1 Prometheus Server Architecture: Retrieval, Storage, HTTP API, Rule Engine
2.2 The Data Model: Metric Names, Label Sets, Samples, and Time Series Identity
2.3 Metric Types: Counter, Gauge, Histogram, and Summary
2.4 The TSDB Storage Engine: Blocks, Chunks, and the Write-Ahead Log (WAL)
2.5 Compaction, Retention, and On-Disk Layout
2.6 Memory Usage and Cardinality Fundamentals
2.7 The HTTP API Surface (`/query`, `/query_range`, `/series`, `/labels`)
2.8 Staleness Handling and Out-of-Order Sample Behavior

### Part 3 — Installation and Configuration

3.1 Installation Methods: Binary, Docker, and OS Package Managers
3.2 `prometheus.yml` Structure and Configuration Reload
3.3 Global Configuration: `scrape_interval`, `evaluation_interval`, `external_labels`
3.4 `scrape_configs` Deep Dive: `job_name`, `static_configs`, `metrics_path`
3.5 Relabeling Fundamentals: `relabel_configs` vs. `metric_relabel_configs`
3.6 TLS and Authentication for Scrape Targets (Basic Auth, Bearer Tokens, mTLS)
3.7 Command-Line Flags and Runtime Reloadability

### Part 4 — PromQL Fundamentals

4.1 PromQL Data Types: Instant Vector, Range Vector, Scalar, and String
4.2 Selecting Time Series: Label Matchers (`=`, `!=`, `=~`, `!~`)
4.3 Range Vector Selectors and the `[duration]` Syntax
4.4 The `offset` and `@` Modifiers
4.5 Basic Aggregation Operators: `sum`, `avg`, `min`, `max`, `count`
4.6 Aggregation `by`/`without` Clauses and Grouping Semantics
4.7 Binary Operators: Arithmetic, Comparison, and Logical/Set Operators

### Part 5 — PromQL Advanced Queries and Functions

5.1 `rate()`, `irate()`, and `increase()` — Counter Math Explained Correctly
5.2 Vector Matching: One-to-One, Many-to-One, and `group_left`/`group_right`
5.3 Histogram Functions: `histogram_quantile()` and Bucket Math
5.4 Subqueries and Nested Range Queries
5.5 Time and Date Functions
5.6 Prediction and Trend Functions: `predict_linear`, `deriv`, `delta`
5.7 Common Query Patterns: Error Rates, Saturation, and Apdex/SLO Queries
5.8 PromQL Anti-Patterns and Query-Performance Pitfalls

### Part 6 — Exporters and Instrumentation (Client Libraries)

6.1 Exporter Architecture: What an Exporter Actually Is
6.2 Node Exporter Deep Dive (Host-Level Metrics)
6.3 Widely-Used Exporters Survey (Blackbox, cAdvisor, MySQL/Postgres, Redis, JMX)
6.4 Writing a Custom Exporter
6.5 Client Libraries: Instrumenting Application Code (Go, Python, Java Conceptually)
6.6 The Four Metric Types in Practice: Choosing the Right One
6.7 The Pushgateway: When and How to Use It (and When Not To)
6.8 Naming Conventions and Metric/Label Design Best Practices

### Part 7 — Service Discovery

7.1 Static vs. Dynamic Service Discovery — Why SD Matters at Scale
7.2 File-Based Service Discovery
7.3 Kubernetes Service Discovery (`kubernetes_sd_configs`) Deep Dive
7.4 Cloud-Provider Service Discovery (EC2, Azure, GCE, Consul)
7.5 Relabeling for Service Discovery: Filtering and Enriching Targets
7.6 Target Health, Scrape Status, and `up` Metric Patterns

### Part 8 — Alertmanager and Alerting Design

8.1 Alerting Architecture: Rule Evaluation → Alertmanager → Notification
8.2 Alerting Rules Syntax: `alert`, `expr`, `for`, `labels`, `annotations`
8.3 Alertmanager Configuration: Routes, Receivers, and Matchers
8.4 Grouping, Inhibition, and Silencing
8.5 Notification Integrations (Slack, PagerDuty, Email, Webhook, OpsGenie)
8.6 High-Availability Alertmanager Clustering (Gossip Protocol)
8.7 Alert Design Principles: Symptom-Based vs. Cause-Based Alerting
8.8 SLO-Based Alerting and Multi-Window, Multi-Burn-Rate Alerts
8.9 Alert Fatigue, Runbooks, and On-Call Practices

### Part 9 — Recording Rules and Performance

9.1 Recording Rules: Syntax and Use Cases
9.2 Rule Groups and Evaluation Order
9.3 Precomputing Expensive Queries for Dashboards and Alerts
9.4 Cardinality Management and Metric Relabeling to Drop High-Cardinality Labels
9.5 Query Performance Tuning and the Query Log
9.6 Capacity Planning: Sizing Prometheus for Scale (Samples/sec, Memory)

### Part 10 — Federation and Long-Term Storage

10.1 Federation: Hierarchical and Cross-Service Federation Patterns
10.2 Remote Write and Remote Read Protocols
10.3 Long-Term Storage Concepts: Why Local TSDB Isn't Enough
10.4 Thanos Architecture Overview (Sidecar, Store Gateway, Compactor, Querier)
10.5 Cortex and Mimir Architecture Overview (Horizontally Scalable Prometheus)
10.6 Choosing a Scaling Strategy: Federation vs. Remote-Write vs. Thanos/Mimir/Cortex
10.7 Multi-Cluster and Multi-Region Monitoring Topologies

### Part 11 — Grafana Integration and Dashboarding

11.1 Prometheus as a Grafana Data Source: Configuration and Query Editor
11.2 Dashboard Design Principles for Prometheus Metrics (Brief — Grafana Has Its Own Knowledge Base)
11.3 Variables and Templating in Grafana Dashboards Backed by Prometheus
11.4 Alerting in Grafana vs. Alertmanager — Where Each Fits
11.5 Community Dashboards and the Monitoring-Mixins Pattern

### Part 12 — Kubernetes-Native Prometheus (Operator, ServiceMonitor, kube-prometheus-stack)

12.1 Recap: What the Kubernetes Observability Survey Already Covers vs. This Part's Depth
12.2 The Prometheus Operator: CRD Overview (`Prometheus`, `Alertmanager`, `ThanosRuler`)
12.3 `ServiceMonitor` and `PodMonitor` Resources
12.4 `PrometheusRule` CRD for Alerts and Recording Rules as Code
12.5 kube-prometheus-stack: What It Bundles and How to Deploy It
12.6 Scraping Kubernetes Components: kubelet, cAdvisor, kube-state-metrics, API Server
12.7 RBAC, Namespacing, and Multi-Tenant Prometheus Operator Patterns

### Part 13 — Production Operations and Scaling

13.1 High-Availability Prometheus: Redundant Pairs and Their Tradeoffs
13.2 Backup and Disaster Recovery for TSDB Data
13.3 Monitoring Prometheus Itself (Meta-Monitoring)
13.4 Security Hardening: TLS, Authentication, and Network Exposure
13.5 Upgrades and Version Migration Strategy
13.6 Troubleshooting: Common Failure Modes and Debugging Techniques
13.7 Incident Case Studies and Runbooks

### Part 14 — Mastery, Best Practices, and Wrap-Up

14.1 Best Practices Checklist: Naming, Labels, Cardinality, Alerting
14.2 Common Anti-Patterns and Misconceptions
14.3 Prometheus in the Broader Observability Landscape (Metrics vs. Logs vs. Traces, OpenTelemetry)
14.4 Interview Question Bank (Beginner to Architect)
14.5 Scenario-Based Design Questions ("Design a Monitoring Stack for X")
14.6 Progressive Hands-On Labs
14.7 Consolidated Key Takeaways and Recommended Next Topics

---

## 2. Prerequisites

| Prerequisite                                                                                     | Needed For    | Introduced                                                       |
| ------------------------------------------------------------------------------------------------ | ------------- | ---------------------------------------------------------------- |
| Linux fundamentals (processes, filesystem, networking)                                           | Throughout    | Assumed baseline (see [[../2. Linux/00-Roadmap]])                |
| Basic Kubernetes awareness (Pods, Services, Deployments)                                         | Part 7, 12    | Assumed baseline (see [[../12. Kubernetes/00-Roadmap]])          |
| Kubernetes Observability survey (Metrics Server, Prometheus/Grafana on K8s, centralized logging) | Part 12       | Covered at survey depth in Kubernetes Part 12; not repeated here |
| Basic HTTP and YAML literacy                                                                     | Part 3 onward | Assumed baseline                                                 |

No external topic must be studied before starting; every Prometheus-specific concept is built in place, though Linux fundamentals and basic Kubernetes familiarity are assumed baseline knowledge, and the Kubernetes-native Part (12) assumes the reader has seen this repo's Kubernetes Observability survey rather than re-deriving it.

---

## 3. Learning Phases

| Phase                                  | Parts Covered | Goal                                                               |
| -------------------------------------- | ------------- | ------------------------------------------------------------------ |
| Phase 1 — Foundations                  | Part 1, 2     | Understand the pull model and the TSDB architecture                |
| Phase 2 — Setup and Query Language     | Part 3, 4     | Install/configure Prometheus and write basic PromQL                |
| Phase 3 — Query Mastery                | Part 5        | Advanced PromQL: rate math, vector matching, histograms, SLOs      |
| Phase 4 — Data Collection              | Part 6, 7     | Exporters, instrumentation, and service discovery                  |
| Phase 5 — Alerting                     | Part 8        | Alertmanager configuration and alert design                        |
| Phase 6 — Efficiency and Scale         | Part 9, 10    | Recording rules, performance tuning, federation, long-term storage |
| Phase 7 — Visualization and Kubernetes | Part 11, 12   | Grafana integration and Kubernetes-native Prometheus deployment    |
| Phase 8 — Production Operations        | Part 13       | HA, backup/DR, security, troubleshooting                           |
| Phase 9 — Mastery and Wrap-Up          | Part 14       | Best practices, interview prep, labs, next steps                   |

---

## 4. Section-to-File Mapping

Each roadmap subsection (e.g., `1.1`, `8.5`) is authored as its own file, following the `Contents/PartN/Section-NN-PartN-Slug.md` convention shared with this repo's other knowledge bases (Linux, AWS, Azure, GCP, Kubernetes, Ansible, GIT). Section numbers (`§`) are continuous across the entire 14-part roadmap (1–99), not reset per part.

| Part                                                                     | Roadmap Range | Continuous § Range | Folder             |
| ------------------------------------------------------------------------ | ------------- | ------------------ | ------------------ |
| Part 1 — Foundations and the Pull-Based Monitoring Model                 | 1.1–1.7       | §1–§7              | `Contents/Part1/`  |
| Part 2 — Architecture and the TSDB                                       | 2.1–2.8       | §8–§15             | `Contents/Part2/`  |
| Part 3 — Installation and Configuration                                  | 3.1–3.7       | §16–§22            | `Contents/Part3/`  |
| Part 4 — PromQL Fundamentals                                             | 4.1–4.7       | §23–§29            | `Contents/Part4/`  |
| Part 5 — PromQL Advanced Queries and Functions                           | 5.1–5.8       | §30–§37            | `Contents/Part5/`  |
| Part 6 — Exporters and Instrumentation (Client Libraries)                | 6.1–6.8       | §38–§45            | `Contents/Part6/`  |
| Part 7 — Service Discovery                                               | 7.1–7.6       | §46–§51            | `Contents/Part7/`  |
| Part 8 — Alertmanager and Alerting Design                                | 8.1–8.9       | §52–§60            | `Contents/Part8/`  |
| Part 9 — Recording Rules and Performance                                 | 9.1–9.6       | §61–§66            | `Contents/Part9/`  |
| Part 10 — Federation and Long-Term Storage                               | 10.1–10.7     | §67–§73            | `Contents/Part10/` |
| Part 11 — Grafana Integration and Dashboarding                           | 11.1–11.5     | §74–§78            | `Contents/Part11/` |
| Part 12 — Kubernetes-Native Prometheus (Operator, ServiceMonitor, Stack) | 12.1–12.7     | §79–§85            | `Contents/Part12/` |
| Part 13 — Production Operations and Scaling                              | 13.1–13.7     | §86–§92            | `Contents/Part13/` |
| Part 14 — Mastery, Best Practices, and Wrap-Up                           | 14.1–14.7     | §93–§99            | `Contents/Part14/` |

**Total: 99 sections across 14 parts.**

---

## 5. Cross-Topic Dependency Graph

```text
Foundations and the Pull-Based Monitoring Model (P1)
        │
        ▼
Architecture and the TSDB (P2) ──────────────► Data model, metric types, storage engine
        │
        ▼
Installation and Configuration (P3)
        │
        ▼
PromQL Fundamentals (P4) ──► Selectors, aggregation, binary operators
        │
        ▼
PromQL Advanced Queries and Functions (P5) ──► rate math, vector matching, histograms, SLO queries
        │
        ├──► Exporters and Instrumentation (P6)
        │
        ▼
Service Discovery (P7) ──► Kubernetes SD, cloud SD, relabeling
        │
        ▼
Alertmanager and Alerting Design (P8)
        │
        ▼
Recording Rules and Performance (P9)
        │
        ▼
Federation and Long-Term Storage (P10) ──► Remote-write, Thanos, Cortex/Mimir
        │
        ├──► Grafana Integration and Dashboarding (P11)
        │
        ▼
Kubernetes-Native Prometheus (P12) ──► Operator, ServiceMonitor, kube-prometheus-stack
        │
        ▼
Production Operations and Scaling (P13) ──► HA, backup/DR, security, troubleshooting
        │
        ▼
Mastery, Best Practices, and Wrap-Up (P14) ──► Recommended next topics: Grafana, general observability/SRE practices
```

**Recommended technologies to learn alongside or after Prometheus:** Grafana (this repo's next planned topic — dashboarding and visualization atop Prometheus and other data sources), general observability and SRE practices (SLOs, error budgets, incident response), OpenTelemetry (traces and logs alongside Prometheus metrics), and this repo's existing Kubernetes KB (see [[../12. Kubernetes/00-Roadmap]]) for the platform Prometheus most commonly runs on in production.

---

## 6. Roadmap Expansion Backlog

_(Empty at project start. Populated when the user requests additions, gap coverage, or new parts.)_

| Item | Requested Reason / Gap | Placement | Status | Target Filename |
| ---- | ---------------------- | --------- | ------ | --------------- |
| —    | —                      | —         | —      | —               |

---

## 7. Current Roadmap State

| #   | Part                                                                     | Section   | Status         |
| --- | ------------------------------------------------------------------------ | --------- | -------------- |
| 01  | Part 1 — Foundations and the Pull-Based Monitoring Model                 | 1.1–1.7   | ⬜ Not Started |
| 02  | Part 2 — Architecture and the TSDB                                       | 2.1–2.8   | ⬜ Not Started |
| 03  | Part 3 — Installation and Configuration                                  | 3.1–3.7   | ⬜ Not Started |
| 04  | Part 4 — PromQL Fundamentals                                             | 4.1–4.7   | ⬜ Not Started |
| 05  | Part 5 — PromQL Advanced Queries and Functions                           | 5.1–5.8   | ⬜ Not Started |
| 06  | Part 6 — Exporters and Instrumentation (Client Libraries)                | 6.1–6.8   | ⬜ Not Started |
| 07  | Part 7 — Service Discovery                                               | 7.1–7.6   | ⬜ Not Started |
| 08  | Part 8 — Alertmanager and Alerting Design                                | 8.1–8.9   | ⬜ Not Started |
| 09  | Part 9 — Recording Rules and Performance                                 | 9.1–9.6   | ⬜ Not Started |
| 10  | Part 10 — Federation and Long-Term Storage                               | 10.1–10.7 | ⬜ Not Started |
| 11  | Part 11 — Grafana Integration and Dashboarding                           | 11.1–11.5 | ⬜ Not Started |
| 12  | Part 12 — Kubernetes-Native Prometheus (Operator, ServiceMonitor, Stack) | 12.1–12.7 | ⬜ Not Started |
| 13  | Part 13 — Production Operations and Scaling                              | 13.1–13.7 | ⬜ Not Started |
| 14  | Part 14 — Mastery, Best Practices, and Wrap-Up                           | 14.1–14.7 | ⬜ Not Started |

**Next Section:** Part 1 — Foundations and the Pull-Based Monitoring Model (§1–§7)
