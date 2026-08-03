# 00 — Roadmap: Grafana (Complete Topic Roadmap)

## 0. Assumption Line

Grafana is treated in its most common **DevOps / Cloud / SRE / Observability** interpretation: Grafana as the visualization and dashboarding layer of a production observability stack — architecture and installation, data source integration (Prometheus, Loki, SQL databases, and other cloud-native data sources), dashboard and panel design, variables and templating, Grafana-native unified alerting, provisioning-as-code (YAML provisioning and the Terraform provider), plugins, users/teams/permissions/organizations, and production/enterprise operation (Grafana Cloud vs. self-hosted, high availability). Grafana is **not** a metrics store or query engine in its own right — it renders and alerts on data owned by other systems — so this roadmap treats Prometheus as one of several data sources rather than the only backend, and defers deep PromQL coverage to the dedicated [[../10. Prometheus/00-Roadmap]] knowledge base. This roadmap runs **95 sections across 13 parts**, deliberately smaller than broad platform tracks like Linux (125) or Ansible (119), since Grafana is a focused, specialized tool rather than an entire operating system or automation platform.

Because Grafana spans multiple concerns — architecture, query-language-agnostic data source integration, visualization design, alerting, and GitOps-style dashboard management — this project is split into **named Parts**, generated sequentially. Do not ask which part to start with — Part 1 begins immediately after this roadmap.

---

## 1. Complete Numbered Roadmap

### Part 1 — Foundations and the Role of Dashboards in Observability

1.1 What Grafana Is; Visualization Layer vs. Metrics Store vs. Log Store
1.2 The Observability Stack: Metrics, Logs, Traces — Where Grafana Fits (LGTM Stack Overview)
1.3 Grafana vs. Kibana vs. Datadog vs. Cloud-Native Dashboards — Positioning
1.4 History and Editions: OSS Grafana, Grafana Enterprise, Grafana Cloud
1.5 Prerequisites Recap (Basic Monitoring Concepts, Prometheus Fundamentals)
1.6 The Query → Panel → Dashboard → Alert Mental Model
1.7 How This Roadmap Maps to Production Dashboarding Work

### Part 2 — Architecture and Installation

2.1 Grafana Server Architecture: Frontend, Backend, Database, Plugin Runtime
2.2 The Grafana Database: SQLite vs. MySQL vs. PostgreSQL for Grafana's Own State
2.3 Installation Methods: Package Managers, Docker, Helm Chart on Kubernetes
2.4 grafana.ini Configuration Deep Dive and Environment Variable Overrides
2.5 Authentication Backends Overview (Basic Auth, OAuth2/OIDC, SAML, LDAP)
2.6 Networking, Reverse Proxies, and TLS Termination in Front of Grafana
2.7 Upgrades, Backups, and the Grafana Database Migration Process
2.8 Health Checks, Logging, and Internal Metrics (Grafana Monitoring Itself)

### Part 3 — Data Sources: Prometheus, Loki, SQL, and Cloud-Native Backends

3.1 The Data Source Abstraction: Query Editors, Field Mapping, Time-Series vs. Table vs. Log Frames
3.2 Configuring the Prometheus Data Source (Recap — Deep PromQL Lives in [[../10. Prometheus/00-Roadmap]])
3.3 Configuring the Loki Data Source for Log Exploration
3.4 SQL Data Sources: MySQL, PostgreSQL, MSSQL Query Editors and Macros
3.5 Cloud-Native Data Sources: CloudWatch, Azure Monitor, Google Cloud Monitoring, Elasticsearch/OpenSearch
3.6 Mixed Data Source Queries and Cross-Source Panels
3.7 Data Source Provisioning, Health Checks, and Access Modes (Server vs. Browser)
3.8 Query Caching and Performance Considerations Per Data Source

### Part 4 — Dashboard Fundamentals and Panel Types

4.1 Dashboard Anatomy: Rows, Panels, Time Range, Refresh Interval
4.2 Creating and Organizing Dashboards; Folders and Dashboard Search
4.3 Core Panel Types: Time Series, Stat, Gauge, Bar Gauge, Table
4.4 Panel Editor Deep Dive: Queries, Transformations, Field Overrides
4.5 Legends, Tooltips, Axes, and Thresholds Configuration
4.6 Dashboard JSON Model: Structure and Direct Editing
4.7 Sharing, Exporting, Snapshots, and Public Dashboards
4.8 Dashboard Versioning and the Built-In Change History

### Part 5 — Transformations and Advanced Visualizations

5.1 Transformations Deep Dive: Merge, Join, Reduce, Organize Fields
5.2 Field Overrides and Value Mappings for Custom Display Logic
5.3 Advanced Panel Types: Heatmap, Histogram, Candlestick, State Timeline
5.4 Geomap and Node Graph Panels for Spatial and Topology Data
5.5 Logs Panel and Log Context in Dashboards
5.6 Text, News, and Annotation-List Panels for Runbooks and Context
5.7 Panel Repeats and Dynamic Panel Generation
5.8 Custom Panel Plugins Overview (Preview of Part 10)

### Part 6 — Variables and Templating

6.1 Dashboard Variables: Query, Custom, Constant, Interval, Datasource Types
6.2 Variable Syntax and Multi-Value / Include-All Options
6.3 Chained Variables and Dependent Variable Queries
6.4 Ad-Hoc Filters and Global Variables ($__interval, $__range, $timeFilter)
6.5 Repeating Rows and Panels Driven by Variables
6.6 Templating Best Practices for Reusable, Multi-Tenant Dashboards

### Part 7 — Alerting (Grafana Unified Alerting)

7.1 Unified Alerting Architecture: Alert Rules, Contact Points, Notification Policies
7.2 Creating Alert Rules from Panel Queries and Multi-Dimensional Data
7.3 Evaluation Groups, Intervals, and the Pending/Firing/Resolved State Machine
7.4 Contact Points: Email, Slack, PagerDuty, Webhook, OpsGenie Integration
7.5 Notification Policies, Routing Trees, and Label Matching
7.6 Silences, Mute Timings, and Alert Grouping
7.7 Alerting on Prometheus vs. Loki vs. SQL Data Sources
7.8 Grafana Alerting vs. Prometheus Alertmanager — When to Use Which
7.9 Alert State History, Annotations, and Troubleshooting Noisy Alerts

### Part 8 — Provisioning-as-Code and GitOps for Dashboards

8.1 YAML Provisioning: Data Sources, Dashboards, Notifiers, Alert Rules as Code
8.2 Dashboard-as-Code with JSON/Jsonnet and the Grafonnet Library
8.3 The Grafana Terraform Provider: Managing Dashboards, Folders, Data Sources
8.4 GitOps Workflows: Version-Controlled Dashboards and CI/CD Promotion (dev → staging → prod)
8.5 The Grafana HTTP API for Programmatic Dashboard and Alert Management
8.6 Dashboard Linting, Drift Detection, and Preventing Manual Edits From Diverging
8.7 Reusable Dashboard Libraries and Panel/Row Templates Across Teams

### Part 9 — Users, Teams, Permissions, and Organizations

9.1 Organizations: Multi-Tenancy Within a Single Grafana Instance
9.2 Users, Teams, and Role-Based Access Control (RBAC) Fundamentals
9.3 Folder and Dashboard Permissions: Viewer, Editor, Admin Granularity
9.4 Data Source Permissions and Query Restriction by Team
9.5 SSO Integration: OAuth2/OIDC and SAML Configuration Walkthrough
9.6 Service Accounts and API Keys for Automation
9.7 Auditing: Access Logs and Change Tracking

### Part 10 — Plugins and Extending Grafana

10.1 Plugin Types: Panel, Data Source, and App Plugins
10.2 Installing and Managing Plugins (grafana-cli, Provisioning, Grafana Cloud Catalog)
10.3 Popular Community Data Source Plugins (Beyond the Built-In Set)
10.4 Building a Minimal Custom Panel Plugin (Conceptual Walkthrough)
10.5 Plugin Signing, Security Review, and Allow-Listing in Enterprise Environments
10.6 App Plugins and Grafana as an Extensible Application Shell

### Part 11 — Loki and Log Exploration

11.1 Loki Architecture Primer: Labels, Streams, and Index-Free Log Storage
11.2 LogQL Fundamentals for Dashboard and Explore Use (Query Basics, Not a Loki Deep Dive)
11.3 The Explore View: Ad-Hoc Log and Metric Investigation
11.4 Correlating Logs and Metrics: Split View, Trace-to-Logs, Derived Fields
11.5 Log-Based Alerting Patterns
11.6 Building Log-Centric Dashboards (Error Rates, Log Volume, Pattern Panels)

### Part 12 — Production Operations, Scaling, and Grafana Cloud

12.1 Self-Hosted High Availability: Multiple Grafana Instances Behind a Load Balancer
12.2 Session Storage, Database Scaling, and Shared Alerting State in HA
12.3 Grafana Cloud Overview: Managed Grafana, Managed Prometheus/Mimir, Managed Loki
12.4 Grafana Enterprise Features: Reporting, White-Labeling, Advanced Auth, Usage Insights
12.5 Performance Tuning: Query Timeouts, Dashboard Load Optimization, Caching
12.6 Monitoring Grafana Itself: Golden Signals for the Dashboarding Layer
12.7 Disaster Recovery: Backing Up Dashboards, Data Sources, and Alert Rules
12.8 Cost and Capacity Planning for Self-Hosted vs. Grafana Cloud

### Part 13 — Mastery, Best Practices, and Wrap-Up

13.1 Dashboard Design Best Practices (Signal-to-Noise, RED/USE Methods, Layout Conventions)
13.2 Common Anti-Patterns: Alert Fatigue, Dashboard Sprawl, Unowned Panels
13.3 Interview Question Bank (Beginner to Architect)
13.4 Scenario-Based Troubleshooting Questions (Broken Panels, Missing Data, Alert Storms)
13.5 Progressive Hands-On Labs (Single Dashboard → Provisioned Multi-Team GitOps Setup)
13.6 Consolidated Key-Takeaways Checklist
13.7 Related Technologies and Recommended Next Topics

---

## 2. Prerequisites

| Prerequisite                                                    | Needed For    | Introduced                                                          |
| --------------------------------------------------------------- | ------------- | ------------------------------------------------------------------- |
| Basic monitoring/observability concepts (metrics, logs, alerts) | Throughout    | Assumed baseline                                                    |
| Prometheus fundamentals (metrics model, PromQL basics)          | Part 3, 7, 11 | Assumed baseline — see [[../10. Prometheus/00-Roadmap]]             |
| Basic YAML syntax                                               | Part 2, 8     | Assumed baseline                                                    |
| Basic SQL literacy (reading, not writing)                       | Part 3        | Briefly recapped in 3.4                                             |
| Basic Linux/container operations (for installation)             | Part 2        | Assumed baseline — see [[../2. Linux/00-Roadmap]], [[../4. Docker]] |

No external topic must be studied before starting; this roadmap builds every Grafana-specific concept in place, though basic observability vocabulary and Prometheus fundamentals are assumed baseline knowledge.

---

## 3. Learning Phases

| Phase                               | Parts Covered | Goal                                                           |
| ----------------------------------- | ------------- | -------------------------------------------------------------- |
| Phase 1 — Foundations               | Part 1, 2     | Understand Grafana's role and stand up an instance             |
| Phase 2 — Data Integration          | Part 3        | Connect Prometheus, Loki, SQL, and cloud-native data sources   |
| Phase 3 — Visualization             | Part 4, 5, 6  | Build dashboards, panels, transformations, and variables       |
| Phase 4 — Alerting                  | Part 7        | Design unified alert rules, routing, and notification policies |
| Phase 5 — Automation and Governance | Part 8, 9     | Provisioning-as-code, GitOps, RBAC, and multi-team access      |
| Phase 6 — Extensibility             | Part 10       | Plugins and extending Grafana beyond built-ins                 |
| Phase 7 — Logs                      | Part 11       | Loki-driven log exploration and correlation with metrics       |
| Phase 8 — Production Operations     | Part 12       | HA, Grafana Cloud, Enterprise features, DR                     |
| Phase 9 — Mastery and Wrap-Up       | Part 13       | Best practices, interview prep, labs, next steps               |

---

## 4. Section-to-File Mapping

Each roadmap subsection (e.g., `1.1`, `7.5`) is authored as its own file, following the `Contents/PartN/Section-NN-PartN-Slug.md` convention shared with this repo's other knowledge bases (Linux, AWS, Azure, GCP, Kubernetes, Ansible, Prometheus). Section numbers (`§`) are continuous across the entire 13-part roadmap (1–95), not reset per part.

| Part                                                                    | Roadmap Range | Continuous § Range | Folder             |
| ----------------------------------------------------------------------- | ------------- | ------------------ | ------------------ |
| Part 1 — Foundations and the Role of Dashboards in Observability        | 1.1–1.7       | §1–§7              | `Contents/Part1/`  |
| Part 2 — Architecture and Installation                                  | 2.1–2.8       | §8–§15             | `Contents/Part2/`  |
| Part 3 — Data Sources: Prometheus, Loki, SQL, and Cloud-Native Backends | 3.1–3.8       | §16–§23            | `Contents/Part3/`  |
| Part 4 — Dashboard Fundamentals and Panel Types                         | 4.1–4.8       | §24–§31            | `Contents/Part4/`  |
| Part 5 — Transformations and Advanced Visualizations                    | 5.1–5.8       | §32–§39            | `Contents/Part5/`  |
| Part 6 — Variables and Templating                                       | 6.1–6.6       | §40–§45            | `Contents/Part6/`  |
| Part 7 — Alerting (Grafana Unified Alerting)                            | 7.1–7.9       | §46–§54            | `Contents/Part7/`  |
| Part 8 — Provisioning-as-Code and GitOps for Dashboards                 | 8.1–8.7       | §55–§61            | `Contents/Part8/`  |
| Part 9 — Users, Teams, Permissions, and Organizations                   | 9.1–9.7       | §62–§68            | `Contents/Part9/`  |
| Part 10 — Plugins and Extending Grafana                                 | 10.1–10.6     | §69–§74            | `Contents/Part10/` |
| Part 11 — Loki and Log Exploration                                      | 11.1–11.6     | §75–§80            | `Contents/Part11/` |
| Part 12 — Production Operations, Scaling, and Grafana Cloud             | 12.1–12.8     | §81–§88            | `Contents/Part12/` |
| Part 13 — Mastery, Best Practices, and Wrap-Up                          | 13.1–13.7     | §89–§95            | `Contents/Part13/` |

**Total: 95 sections across 13 parts.**

---

## 5. Cross-Topic Dependency Graph

```text
Foundations and the Role of Dashboards in Observability (P1)
        │
        ▼
Architecture and Installation (P2) ──────────────► Server setup, database, auth backends
        │
        ▼
Data Sources: Prometheus, Loki, SQL, Cloud-Native (P3) ──► Relies on Prometheus KB for PromQL depth
        │
        ▼
Dashboard Fundamentals and Panel Types (P4)
        │
        ▼
Transformations and Advanced Visualizations (P5)
        │
        ▼
Variables and Templating (P6)
        │
        ▼
Alerting: Unified Alerting (P7) ──► Contact points, routing, alert state
        │
        ├──► Provisioning-as-Code and GitOps (P8)
        ├──► Users, Teams, Permissions, Organizations (P9)
        │
        ▼
Plugins and Extending Grafana (P10)
        │
        ▼
Loki and Log Exploration (P11) ──► Correlates back to P3 data sources and P7 alerting
        │
        ▼
Production Operations, Scaling, and Grafana Cloud (P12)
        │
        ▼
Mastery, Best Practices, and Wrap-Up (P13) ──► Recommended next topics: SRE/incident-response practices, distributed tracing
```

**Recommended technologies to learn alongside or after Grafana:** Prometheus (metrics data source and alerting foundation — see [[../10. Prometheus/00-Roadmap]]), Kubernetes (common deployment target and a rich source of dashboards/metrics — see [[../12. Kubernetes/00-Roadmap]]), Docker (local Grafana/Prometheus/Loki stacks — see [[../4. Docker]]), CI/CD (dashboard-as-code promotion pipelines — see [[../9. CI-CD]]), Terraform (the Grafana provider used in Part 8 — see [[../7. Terraform]]), and general SRE/incident-response practices (on-call, postmortems, error budgets) as the natural next extension once metrics, logs, and alerts are all wired together.

---

## 6. Roadmap Expansion Backlog

_(Empty at project start. Populated when the user requests additions, gap coverage, or new parts.)_

| Item | Requested Reason / Gap | Placement | Status | Target Filename |
| ---- | ---------------------- | --------- | ------ | --------------- |
| —    | —                      | —         | —      | —               |

---

## 7. Current Roadmap State

| #   | Part                                                                    | Section   | Status         |
| --- | ----------------------------------------------------------------------- | --------- | -------------- |
| 01  | Part 1 — Foundations and the Role of Dashboards in Observability        | 1.1–1.7   | ⬜ Not Started |
| 02  | Part 2 — Architecture and Installation                                  | 2.1–2.8   | ⬜ Not Started |
| 03  | Part 3 — Data Sources: Prometheus, Loki, SQL, and Cloud-Native Backends | 3.1–3.9   | ⬜ Not Started |
| 04  | Part 4 — Dashboard Fundamentals and Panel Types                         | 4.1–4.8   | ⬜ Not Started |
| 05  | Part 5 — Transformations and Advanced Visualizations                    | 5.1–5.8   | ⬜ Not Started |
| 06  | Part 6 — Variables and Templating                                       | 6.1–6.6   | ⬜ Not Started |
| 07  | Part 7 — Alerting (Grafana Unified Alerting)                            | 7.1–7.9   | ⬜ Not Started |
| 08  | Part 8 — Provisioning-as-Code and GitOps for Dashboards                 | 8.1–8.7   | ⬜ Not Started |
| 09  | Part 9 — Users, Teams, Permissions, and Organizations                   | 9.1–9.7   | ⬜ Not Started |
| 10  | Part 10 — Plugins and Extending Grafana                                 | 10.1–10.6 | ⬜ Not Started |
| 11  | Part 11 — Loki and Log Exploration                                      | 11.1–11.6 | ⬜ Not Started |
| 12  | Part 12 — Production Operations, Scaling, and Grafana Cloud             | 12.1–12.8 | ⬜ Not Started |
| 13  | Part 13 — Mastery, Best Practices, and Wrap-Up                          | 13.1–13.7 | ⬜ Not Started |

**Next Section:** Part 1 — Foundations and the Role of Dashboards in Observability (§1–§7)
