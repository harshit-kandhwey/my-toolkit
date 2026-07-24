# Section 92 — Microsoft Sentinel: SIEM/SOAR Fundamentals

**Part 17: Security Operations & Incident Response | Section 92 of 100**
**Prerequisites:** Section 50 (Azure Monitor Fundamentals), Section 51 (Log Analytics & KQL — the workspace and query language Sentinel is built directly on top of), Section 55 (Defender for Cloud — CSPM/CWPP, whose alerts are one of many Sentinel data sources), Section 91 (Microsoft Purview)
**Leads into:** Section 93 (Sentinel Deep Dive — analytics rules, hunting, SOAR playbooks), Section 94 (Automated Incident Response)

---

## 92.1 Definition

**Plain language:** every service covered so far generates its own security-relevant signal in its own silo — Defender for Cloud raises alerts about Azure resource threats (Section 55.7), Azure Monitor collects platform logs and metrics (Section 50), Entra ID logs sign-in activity (Part 2). A real security operations team needs all of that signal, plus signal from firewalls, on-premises Active Directory, other clouds, and third-party security tools, correlated together in one place, with the ability to both search across all of it and automatically respond when something suspicious is found. That's what Microsoft Sentinel is — Azure's cloud-native platform for collecting, correlating, investigating, and automatically responding to security signal from anywhere, not just Azure.

**Precise definition:** Microsoft Sentinel is a cloud-native Security Information and Event Management (SIEM) and Security Orchestration, Automation and Response (SOAR) solution, built on top of a Log Analytics workspace (Section 51), that ingests security-relevant log and event data from Azure-native sources, other clouds, on-premises infrastructure, and third-party security products via **data connectors**, correlates that data using **analytics rules** to surface security **incidents**, supports interactive **threat hunting** and **entity behavior analytics**, and automates response through **automation rules** and Logic Apps-based **playbooks** (Section 42).

## 92.2 Why It Exists / Problem It Solves

Defender for Cloud (Section 55) is explicitly scoped to Azure (and Arc-connected, Section 68, resources) — it assesses posture and detects threats for the specific resource types it has Defender plans for. That's exactly the right scope for what it does, but it leaves a real gap: enterprises virtually never run security operations against Azure alone. They have on-premises Active Directory domain controllers, firewalls and network appliances producing Syslog/CEF data, other cloud providers (AWS, GCP) with their own security signal, SaaS applications like Microsoft 365, and existing third-party security tools already in place — and a genuine security incident often only becomes visible when signal from *several* of these sources is correlated together (an anomalous sign-in from Entra ID, followed by an unusual data-transfer pattern from a firewall log, followed by a Defender for Cloud alert on a specific VM, are each individually low-signal but together indicate a real, in-progress attack).

Sentinel exists specifically to be this correlation and response layer across an entire heterogeneous security estate, not just Azure resources. It's built directly on Log Analytics (Section 51) rather than a separate, purpose-built data store — meaning every KQL skill and every Log Analytics workspace design consideration (Section 50.8's cost/access trade-offs) already covered in Part 10 applies directly and immediately to working with Sentinel; Sentinel is best understood not as a wholly separate product with its own data plane, but as a security-specific application layer (detection rules, incidents, playbooks, hunting) running on top of the exact same workspace and query engine already established.

---

## 92.3 SIEM and SOAR, Precisely Defined

### 92.3.1 SIEM (Security Information and Event Management)

**Definition:** a SIEM centralizes log/event collection from many disparate sources into one searchable data store, and applies correlation rules against that combined data to detect patterns indicating a security incident that wouldn't be visible from any single source in isolation.

### 92.3.2 SOAR (Security Orchestration, Automation and Response)

**Definition:** SOAR capability takes detected incidents and automates the response workflow — enrichment (gathering additional context automatically, e.g., looking up an IP address's threat-intelligence reputation), containment (e.g., disabling a compromised user account or isolating a VM), and notification (paging an analyst, opening a ticket) — reducing the manual, repetitive work a human analyst would otherwise have to perform for every incident.

🔑 **Key Takeaway:** Sentinel is genuinely both, in one product — many legacy on-premises SIEM deployments required bolting on a separate SOAR tool; Sentinel's automation rules and Logic Apps-based playbooks (Section 93-94) are native, first-class capability within the same product, not a bolted-on integration.

---

## 92.4 Sentinel's Relationship to the Log Analytics Workspace (Section 51)

### 92.4.1 Sentinel Is "Enabled Onto" a Workspace, Not a Separate Data Store

Enabling Sentinel is, mechanically, associating the Sentinel solution with an **existing (or newly created) Log Analytics workspace** — Sentinel does not maintain its own independent log storage; every table Sentinel writes to or reads from (via data connectors) is a genuine Log Analytics table, queryable with the exact same KQL syntax and `SigninLogs`/`SecurityEvent`/custom-table conventions already covered in Section 51.

### 92.4.2 Why This Matters Architecturally

Because Sentinel's data plane *is* Log Analytics, every workspace-design consideration from Section 50.8 (single vs. multiple workspaces, cross-workspace query cost/latency, RBAC granularity at the workspace level) applies directly and without modification to a Sentinel deployment — a "how should we design our Sentinel workspace strategy" question is, at its core, exactly the same "how should we design our Log Analytics workspace strategy" question from Part 10, now applied specifically to security data with the additional considerations of cross-tenant/cross-subscription centralization covered in Section 95.

### 92.4.3 Table Plans and Ingestion Cost

Log Analytics tables can be configured with different **table plans** — commonly a distinction between an **Analytics** tier (full analytics-rule and KQL query capability, at standard ingestion cost) and lower-cost, more restricted tiers intended for high-volume, lower-priority log data that's retained for compliance/occasional search but doesn't need full real-time analytics-rule evaluation. ⚠️ Exact table-plan names, their specific capabilities, and pricing structure change over time — verify current table-plan options against documentation before designing an ingestion strategy for a high-volume data source (e.g., verbose firewall Syslog data), since ingestion volume is Sentinel's single largest recurring cost driver.

---

## 92.5 Data Connectors

### 92.5.1 Definition

**Definition:** a data connector is a pre-built (or, for less common sources, custom) integration that ingests log/event data from a specific source into the Sentinel-enabled Log Analytics workspace, populating one or more tables in a known schema that Sentinel's analytics rules and hunting queries can then query.

### 92.5.2 Common Connector Categories

| Connector Category | Example Sources | Notes |
| --- | --- | --- |
| Azure-native | Microsoft Entra ID sign-in/audit logs, Defender for Cloud alerts (Section 55.7), Azure Activity Log | Typically the lowest-friction connectors to enable, since the data already exists within Azure |
| Microsoft 365 | Exchange Online, SharePoint, Teams activity | Extends coverage to SaaS productivity-suite signal, not just infrastructure |
| Multi-cloud | AWS CloudTrail, GCP audit logs | Extends Sentinel's SIEM scope beyond Azure, directly addressing the multi-cloud gap this section opened with |
| On-premises/network | Syslog/CEF (via the Azure Monitor Agent, Section 50.5), Windows Security Events from on-premises servers | Requires an agent deployed on-premises or Arc-connected (Section 68) machines forwarding logs into the workspace |
| Third-party security | A wide and evolving catalog of firewall, EDR, and identity-provider connectors, distributed via the **Content Hub** | Content Hub packages connectors together with related analytics rules, workbooks, and playbooks as a cohesive "solution" for a given product/domain |

⚠️ The specific set of available data connectors and the exact ingestion agent/method each requires (some use the Azure Monitor Agent, some use direct API polling, some require an on-premises collector) evolves continuously — verify current connector availability and configuration requirements against documentation for any specific source before committing to an ingestion architecture.

### 92.5.3 Content Hub Solutions

**Definition:** a bundled package of related data connectors, analytics rule templates, hunting queries, workbooks, and playbooks for a specific product or security domain (e.g., a solution bundling everything needed to onboard and analyze a specific firewall vendor's logs) — reducing the setup effort of wiring together each of these pieces individually for a common integration scenario.

---

## 92.6 Sentinel vs. Defender for Cloud — Precise Comparison

| Aspect | Defender for Cloud (Section 55) | Microsoft Sentinel |
| --- | --- | --- |
| Scope | Azure-native (and Arc-connected) resources specifically | Anything with a data connector — Azure, other clouds, on-premises, third-party, SaaS |
| Core function | CSPM (posture) + CWPP (resource-type-specific threat detection) | SIEM (cross-source correlation) + SOAR (automated response) |
| Detection style | Built-in, resource-type-specific detections requiring no rule authoring | Author-defined and Microsoft-template analytics rules (Section 93), giving far more customization but requiring more deliberate rule design |
| Underlying data store | Its own internal alerting pipeline, optionally exported to Log Analytics (Section 55.8.2) | *Is* a Log Analytics workspace (Section 92.4) |
| Relationship | A data source feeding **into** Sentinel via a dedicated data connector | The correlation and response layer that Defender for Cloud alerts are one (important) input to, alongside every other connected source |

🎯 **Interview Tip:** the single most common point of confusion here is treating Defender for Cloud and Sentinel as redundant or competing — they are not; Defender for Cloud alerts are a **data connector into Sentinel**, one of potentially dozens of sources Sentinel correlates together. A mature answer explicitly states that Defender for Cloud is the specialized Azure-resource-threat-detection engine, and Sentinel is the broader correlation-and-response layer sitting above it and every other security signal source in the estate — "why would we need both" is answered by "because Sentinel's value is precisely in correlating Defender for Cloud's Azure-specific signal against everything else, which Defender for Cloud alone cannot see."

---

## 92.7 Architecture Diagram

```
 Entra ID          Defender for       AWS CloudTrail /      On-Prem Syslog/CEF
 Sign-in/Audit     Cloud Alerts       GCP Audit Logs        (via Azure Monitor
 Logs              (Section 55)                              Agent, Section 50.5)
     │                   │                    │                     │
     └───────────────────┴─────────┬──────────┴─────────────────────┘
                                    │  Data Connectors (92.5)
                                    ▼
                 ┌──────────────────────────────────────┐
                 │   Log Analytics Workspace (Section 51) │
                 │   + Microsoft Sentinel enabled          │
                 └───────────────┬──────────────────────┘
                                 │
              ┌──────────────────┼──────────────────┐
              ▼                  ▼                  ▼
      Analytics Rules      Hunting Queries /     Automation Rules
      (Section 93)         Workbooks / UEBA      + Logic Apps Playbooks
              │             (Section 93)          (Section 94, on Section 42)
              ▼
          Incidents
     (correlated, prioritized,
      assigned to SOC analysts — Section 95)
```

## 92.8 Configuration & Hands-On Example

**Enabling Microsoft Sentinel onto an existing Log Analytics workspace (via Azure CLI):**

```bash
az monitor log-analytics workspace create \
  --resource-group rg-security \
  --workspace-name law-sentinel-prod \
  --location eastus \
  --sku PerGB2018

az sentinel onboarding-state create \
  --resource-group rg-security \
  --workspace-name law-sentinel-prod \
  --name default
```

- **Purpose:** provisions a Log Analytics workspace (identical to the workspace creation pattern from Section 51) and then onboards Microsoft Sentinel onto it, enabling the Sentinel-specific solution (analytics rules, incidents, hunting, playbooks) against that workspace's data.
- **Important arguments explained individually:**
  - `--sku PerGB2018` — the workspace's pricing tier for Log Analytics ingestion; Sentinel-specific commitment-tier pricing (discounted per-GB rates at higher committed daily ingestion volumes) is layered on top of the base workspace pricing model and should be evaluated once actual ingestion volume from connected data sources is better understood, directly analogous to right-sizing any other consumption-based Azure service (Section 65's cost-optimization material) after observing real usage rather than guessing up front.
  - `--name default` — the onboarding-state resource name; Sentinel onboarding is a singleton operation per workspace, so this is conventionally left as `default`.
- **Common error:** attempting to onboard Sentinel onto a workspace already in use for high-volume, non-security operational logging (e.g., the same workspace collecting verbose Application Insights telemetry from Section 52) without first evaluating cost/access implications — mixing operational and security log data in a single workspace can complicate RBAC (security analysts typically shouldn't need broad access to unrelated application telemetry, and vice versa) and can substantially and unexpectedly inflate the workspace's effective Sentinel ingestion cost, since some Sentinel pricing models bill based on the workspace's total ingestion, not merely security-specific tables. A dedicated, security-purposed workspace is the more common and recommended pattern for anything beyond a small trial deployment.

**A basic KQL query against a Sentinel-connected data source (Entra ID sign-in logs), the same query style from Section 51 now applied to security investigation:**

```kql
SigninLogs
| where TimeGenerated > ago(24h)
| where ResultType != "0"
| summarize FailedAttempts = count() by UserPrincipalName, IPAddress
| where FailedAttempts > 10
| order by FailedAttempts desc
```

- **Purpose:** surfaces accounts with more than ten failed sign-in attempts from a single IP address in the last 24 hours — a simple, illustrative brute-force-pattern hunting query, directly reusing the KQL syntax and aggregation operators (`summarize`, `where`) already covered in Section 51.6.
- **Common error:** forgetting that `ResultType != "0"` specifically filters to failed sign-ins (a `ResultType` of `"0"` indicates success) — omitting or inverting this filter silently changes the query's meaning from "find likely brute-force attempts" to "find successful high-frequency logins," a materially different (and far less useful) security question, and a genuinely easy mistake to make when quickly adapting an example query without reading its filter logic carefully.

---

## 92.9 Production & Enterprise Usage

Enterprises typically run a small number of purpose-dedicated Sentinel workspaces (often exactly one centralized workspace per tenant, or occasionally one per major regulatory/data-residency boundary) rather than a Sentinel workspace per subscription or team — the whole value proposition of a SIEM is cross-source correlation, which is undermined if security signal is fragmented across many small, isolated workspaces that can't be queried together. This centralization pattern, and its cross-subscription/cross-tenant implementation, is covered in depth in Section 95's SOC-patterns treatment, directly building on Section 67's multi-subscription/multi-tenant architecture material.

## 92.10 Security Considerations

- The Sentinel workspace itself is a high-value target — it contains a correlated view of an organization's entire security posture and incident history; RBAC scoping (Section 8) of who can read, query, or administer the workspace should be treated with the same rigor as any other highly sensitive data store, not as an operational afterthought.
- Data connector credentials/service principals (particularly for third-party and multi-cloud connectors) require careful least-privilege scoping — a connector only needs read access to the source logs it's ingesting, not broader administrative access to the connected system.

## 92.11 Performance Considerations

Ingestion volume is the dominant cost and performance lever in a Sentinel deployment — high-verbosity sources (raw firewall Syslog/CEF data in particular) can produce enormous daily ingestion volumes if connected without deliberate filtering; many organizations apply source-side filtering (only forwarding genuinely security-relevant log categories) or route very high-volume, lower-priority data to a lower-cost table plan (Section 92.4.3) rather than the full Analytics tier, balancing comprehensive coverage against ingestion cost, directly analogous to Section 50.8's diagnostic-settings cost/coverage trade-off now applied specifically to Sentinel connector design.

## 92.12 Monitoring

Sentinel provides its own workbooks (dashboard-style visualizations, built on the same underlying visualization capability as Azure Monitor workbooks, Section 50) tracking ingestion volume by connector/table, analytics rule health, and incident volume/status trends — essential for a SOC lead to notice, for example, a data connector silently failing (leading to a dangerous, invisible coverage gap) before that gap results in a missed detection.

## 92.13 Troubleshooting

| Symptom | Likely Cause | Fix |
| --- | --- | --- |
| A connected data source's logs aren't appearing in Sentinel queries | Data connector misconfigured, or the underlying agent (e.g., Azure Monitor Agent for Syslog sources) not correctly installed/forwarding | Verify connector status in the Sentinel Data Connectors page; verify agent health on the source system |
| Sentinel ingestion cost far exceeds initial estimate | A high-verbosity source (e.g., raw firewall Syslog) connected without source-side filtering, or connected to the full Analytics table tier rather than a lower-cost tier | Review per-table ingestion volume; apply source-side filtering or move low-priority high-volume tables to an appropriate lower-cost table plan (Section 92.4.3) |
| KQL query against a Sentinel-connected table times out or returns incomplete results | Query spans an excessively long time range against a very high-volume table without appropriate filtering early in the query | Apply `TimeGenerated` and other filters as early as possible in the query pipeline, consistent with Section 51's KQL performance guidance |
| Two teams' workspace RBAC assignments conflict, with the security team unable to see application telemetry needed for an investigation | Security and application telemetry mixed in a single, non-security-purposed workspace, or RBAC scoped too narrowly | Evaluate whether a dedicated Sentinel workspace (92.9) with appropriate cross-workspace query access is a better long-term design than shared use of one workspace |

## 92.14 Interview Questions — Section 92

### 🎯 Intermediate

**Q: Why is Microsoft Sentinel described as being "built on" Log Analytics rather than as an entirely separate product, and why does that matter architecturally?**

_Model answer:_ Sentinel doesn't maintain its own independent log storage — it's enabled onto an existing (or newly created) Log Analytics workspace (Section 51), and every table it reads from or writes to is a genuine Log Analytics table queryable with standard KQL. This matters architecturally because every workspace design consideration already established in Part 10 — single vs. multiple workspaces, RBAC granularity, cross-workspace query cost — applies directly to Sentinel without modification; designing a Sentinel deployment is, at its foundation, a Log Analytics workspace design exercise, with SIEM/SOAR-specific capability (analytics rules, incidents, playbooks) layered on top.

_What the interviewer is probing:_ whether the candidate understands Sentinel's actual technical foundation rather than treating it as an opaque, self-contained black-box product — a distinction that directly affects real deployment decisions like cost estimation and RBAC design.

### 🎯 Senior/Architect

**Q: Your organization already has Defender for Cloud enabled across all Azure subscriptions and feels well-protected. Leadership asks why you'd recommend also deploying Microsoft Sentinel — isn't that redundant?**

_Model answer:_ Defender for Cloud and Sentinel operate at different layers and aren't redundant: Defender for Cloud's CSPM/CWPP capability (Section 55) is specifically scoped to Azure-native (and Arc-connected) resources, providing excellent posture assessment and resource-type-specific threat detection within that scope — but a real attack rarely announces itself through a single Azure resource's alert in isolation; it typically leaves a trail across multiple systems (an anomalous Entra ID sign-in, followed by unusual on-premises firewall traffic, followed by a Defender for Cloud alert on a specific VM). Sentinel's value is precisely in correlating that Defender for Cloud alert against every other connected signal source — on-premises infrastructure, other clouds, third-party tools, Microsoft 365 activity — that Defender for Cloud has no visibility into at all. In this design, Defender for Cloud alerts become one of Sentinel's data connectors (Section 92.5.2), not a redundant, competing product; the recommendation is not "replace Defender for Cloud with Sentinel" but "feed Defender for Cloud's excellent Azure-specific detection into Sentinel's broader cross-source correlation and automated response layer," giving the organization both depth (within Azure) and breadth (across the entire estate) rather than having to choose one.

_What the interviewer is probing:_ the ability to clearly articulate the complementary (not competing) relationship between these two services with specific architectural reasoning, rather than a vague "more security tools are always better" answer.

## 92.15 Common Misconceptions

- **"Sentinel and Defender for Cloud are two competing SIEM/security products — you'd only use one."** False — Defender for Cloud is an Azure-scoped CSPM/CWPP platform whose alerts flow into Sentinel as one of many data connectors; they're complementary layers, not competitors.
- **"Sentinel has its own dedicated log storage separate from Log Analytics."** False — Sentinel is enabled onto a Log Analytics workspace and uses that workspace as its actual data store; there is no separate Sentinel-native database.
- **"Enabling more data connectors is always strictly better, with no downside."** False — every connected source adds ingestion volume and cost, and very high-verbosity sources can dominate a workspace's ingestion bill if connected without deliberate filtering; connector breadth is a genuine cost/coverage trade-off, not a free win.

## 92.16 Key Takeaways

- 🔑 Microsoft Sentinel is a cloud-native SIEM (cross-source log correlation) and SOAR (automated response) platform, built directly on top of a Log Analytics workspace (Section 51) — not a separate data store or product.
- 🔑 Data connectors bring in signal from Azure-native sources, Defender for Cloud (Section 55, as one connector among many), other clouds, on-premises infrastructure, and third-party tools — Sentinel's core value is correlating across all of these, something no single-source tool like Defender for Cloud can do alone.
- 🔑 Because Sentinel's data plane is Log Analytics, every KQL skill and workspace-design consideration from Part 10 (Sections 50-51) transfers directly to Sentinel work.
- 🔑 Ingestion volume, not license cost, is typically the dominant cost driver in a Sentinel deployment, making source-side filtering and appropriate table-plan selection genuine architectural decisions, not afterthoughts.
- 🔑 Sentinel workspace strategy should default toward centralization (one workspace per tenant or major regulatory boundary) rather than fragmentation, since cross-source correlation is undermined by splitting security signal across many isolated workspaces.

## 92.17 Related Concepts (Next Up)

Section 93 goes deep on what actually happens once data lands in a Sentinel-enabled workspace: **analytics rules** (scheduled, near-real-time, and Fusion correlation rules) that turn raw connected log data into prioritized security incidents, **threat hunting** and **entity behavior analytics** for proactive investigation beyond automated rules, and the **SOAR playbooks**, built on Logic Apps (Section 42), that begin the automated-response story completed in Section 94.
