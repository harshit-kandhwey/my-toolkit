# Section 91 — Microsoft Purview

**Part 17: Security Operations & Incident Response | [Section 91](./Section-91-Part17-Microsoft-Purview.md) of 100 (First Section of Part 17)**
**Prerequisites:** [Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md) (Defender for Cloud — CSPM/CWPP posture and workload protection, the infrastructure-config-centric counterpart to Purview's data-centric governance), [Section 56](../Part11/Section-56-Part11-Key-Vault.md) (Key Vault), [Section 58](../Part11/Section-58-Part11-Compliance-Encryption.md) (Compliance & Encryption), Sections 16-20 (Storage Account/Blob/Disks/Files/Redundancy — Part 4), Sections 29-33 (Databases — Part 6), [Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md) (Multi-Subscription/Multi-Tenant Architecture)
**Leads into:** [Section 92](./Section-92-Part17-Microsoft-Sentinel-SIEM-Fundamentals.md) (Microsoft Sentinel SIEM Fundamentals) and the rest of Part 17 — Security Operations & Incident Response

---

## 1. Definition

**Plain language:** Microsoft Purview answers a question none of the preceding security tooling in this roadmap actually answers: not "is this resource configured securely" (Defender for Cloud, [Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md)) and not "who can access this secret" (Key Vault, [Section 56](../Part11/Section-56-Part11-Key-Vault.md)) — but "where, across every storage account, database, and file share we own, does sensitive data (customer PII, payment card numbers, health records, credentials) actually live, and is it labeled, tracked, and protected in a way that matches its sensitivity?" Purview scans your data estate, finds and classifies sensitive information wherever it sits, and builds a searchable map and catalog of what data exists, where, and who owns it.

**Precise definition:** Microsoft Purview is a unified data governance, data security, and risk-management platform providing automated data discovery ("data map"), sensitive-data classification and labeling, a searchable business data catalog, and estate-wide compliance/risk insights across Azure-native data services, on-premises data sources (via a self-hosted integration runtime), other clouds (AWS S3, and others), and Microsoft 365 content — unifying what were historically separate "Azure Purview" (data governance/catalog) and "Microsoft 365 compliance" (information protection/DLP) product lines under one governance plane.

⚠️ Microsoft has substantially rebranded and re-scoped this product family more than once — "Azure Purview" became simply "Microsoft Purview," absorbing Microsoft 365 sensitivity labels, Data Loss Prevention (DLP), Insider Risk Management, and eDiscovery under the same umbrella brand. Verify current product boundaries and the exact feature set included in a given Purview SKU/plan against official documentation before scoping a rollout — the line between "Purview data governance" and "Microsoft 365 compliance center" capability has moved repeatedly.

## 2. Why It Exists / Problem It Solves

Every prior security section in this roadmap protects infrastructure or secrets, not data itself. Defender for Cloud ([Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md)) tells you whether a storage account's network rules or a SQL server's TLS configuration is compliant with best practice — but it has no opinion on what's actually inside the blobs or database rows behind that configuration. Key Vault ([Section 56](../Part11/Section-56-Part11-Key-Vault.md)) protects keys, secrets, and certificates — not the sensitive business data an application processes using those secrets. Compliance & Encryption ([Section 58](../Part11/Section-58-Part11-Compliance-Encryption.md)) confirms data is encrypted at rest and in transit — but encryption tells you nothing about _what_ is encrypted, whether it's classified correctly, or whether a well-meaning analyst just copied a table full of customer national-ID numbers into a new, unmonitored storage account nobody on the security team knows exists.

As an organization's data estate grows across the storage services from Part 4 (Blob, Files, Disks), the databases from Part 6 (SQL Database, Cosmos DB, PostgreSQL/MySQL), and increasingly the analytics estate from Part 15 (data lakes, Synapse, and similar), "where is our sensitive data" stops being a question any single team can answer from memory. Purview exists specifically to close this gap: continuous, automated discovery and classification of sensitive data across an entire, sprawling, frequently-changing data estate, producing both a governance answer (a catalog analysts and data stewards can search) and a security answer (what's actually sensitive, and is it protected and labeled appropriately) that feeds directly into the incident-response and SOC material the rest of Part 17 builds on top of.

---

## 3. Core Purview Capabilities

### 3.1 Data Map

**Definition:** the Data Map is Purview's foundational metadata repository — a graph of every scanned data source, the assets within it (databases, tables, columns, files, containers), their schema, lineage (where data flows from and to), and classification results, kept continuously up to date via scheduled scans.

**How it works conceptually:** a Purview account is registered against data sources (a storage account, a SQL server, an on-premises file share reached via a self-hosted integration runtime) and a scan is configured and scheduled against each; each scan run crawls the source, extracts schema/metadata, applies classification rules, and updates the Data Map with the results — the Data Map is therefore a continuously refreshed inventory, not a one-time snapshot.

### 3.2 Data Catalog (Unified Catalog)

**Definition:** the human-facing, searchable layer built on top of the Data Map — allowing data stewards and analysts to search for data assets by name, classification, business glossary term, or owner, browse lineage, and see who is accountable for a given dataset.

- **Business glossary:** a controlled vocabulary of business terms (e.g., "Customer Lifetime Value," "PCI Cardholder Data") that can be linked to specific technical assets in the Data Map, bridging the gap between business-analyst language and the underlying technical schema — directly analogous in spirit to tagging conventions ([Section 65](../Part12/Section-65-Part12-Capacity-Planning-Tagging-Strategy.md).3) but for data meaning rather than cost allocation.
- **Ownership/stewardship:** assets can be assigned a data owner and data steward, establishing organizational accountability for a given dataset's quality, classification accuracy, and access governance — critical for the incident-response workflows later in this Part, where knowing _who owns this data_ is often the first question during a suspected data-exposure incident.

### 3.3 Automated Data Classification

**Definition:** Purview scans apply both Microsoft-provided **system classifiers** (pre-built pattern-matching and machine-learning-based detectors for common sensitive-data types — credit card numbers, national ID/SSN-equivalent numbers, common health-record identifiers) and organization-defined **custom classifiers** (regex patterns or exact-data-match rules tailored to an organization's own sensitive-data formats, e.g., an internal customer ID format) to discovered data, tagging matching assets/columns with the relevant classification.

⚠️ The specific catalog of built-in system classifiers, their exact detection patterns, and confidence-scoring behavior are updated by Microsoft over time — verify current classifier coverage against documentation for any compliance-critical classification requirement rather than assuming a specific sensitive-data type is automatically covered.

### 3.4 Sensitivity Labels

**Definition:** a sensitivity label (e.g., "Confidential," "Highly Confidential — PII") is a persistent classification marking that can be applied to a data asset (or, in the Microsoft 365 information-protection context, to a document/email) either automatically (based on classification results, 91.3.3) or manually by a data owner — the label itself can drive downstream protection behavior (encryption, access restriction, DLP policy enforcement) in supporting services.

**Why it matters for this Part:** a sensitivity label discovered and applied by Purview is exactly the kind of signal a mature SOC ([Section 95](./Section-95-Part17-SOC-Patterns-on-Azure.md)) wants correlated with a Sentinel security incident ([Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md)) — "an anomalous large download occurred against a dataset labeled Highly Confidential" is a materially higher-priority incident than the same anomalous download against unclassified data, and this correlation is only possible because Purview did the classification work upstream.

### 3.5 Data Estate Insights

**Definition:** dashboard-level, aggregated reporting across the entire scanned estate — total assets discovered, classification coverage, scan health, and sensitive-data distribution by source type or business unit — providing the same kind of estate-wide, at-a-glance visibility for data governance that Secure Score ([Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md).3) provides for security posture, letting a CISO or data-governance lead track improving (or degrading) coverage over time rather than only seeing per-asset detail.

---

## 4. Integration With the Data Estate Covered Elsewhere in This Roadmap

### 4.1 Storage Accounts (Part 4)

Purview scans register directly against Blob containers and Azure Data Lake Storage Gen2 hierarchical-namespace accounts ([Section 17](../Part4/Section-17-Part4-Blob-Storage-Deep-Dive.md)), classifying files by content (structured formats like CSV/Parquet get column-level classification; unstructured documents get document-level classification) — directly extending the storage lifecycle and access-tier guidance from [Section 17](../Part4/Section-17-Part4-Blob-Storage-Deep-Dive.md) with a governance layer answering "what's actually in here" rather than only "how is it tiered and replicated" ([Section 20](../Part4/Section-20-Part4-Data-Redundancy-and-Replication.md)).

### 4.2 Databases (Part 6)

Azure SQL Database/Managed Instance ([Section 29](../Part6/Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md)) and other relational sources expose column-level schema to Purview scans, enabling column-level sensitivity classification (e.g., flagging a `national_id` column specifically, not just the table as a whole) — this is a materially finer-grained governance signal than table-level or database-level classification alone, and connects directly to [Section 29](../Part6/Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md)'s own built-in SQL Data Discovery & Classification feature, which Purview can consume and centralize alongside every other scanned source rather than leaving SQL-specific classification siloed in each individual database.

### 4.3 Multi-Cloud and On-Premises Sources

Purview scans extend beyond Azure-native sources to AWS S3 buckets and on-premises SQL Server/file shares (the latter reached via a **self-hosted integration runtime** — a lightweight agent installed within the on-premises network, directly analogous in purpose to Azure Arc's [Section 68](../Part13/Section-68-Part13-Hybrid-Multi-Cloud-Azure-Arc.md) role of extending Azure management to non-Azure resources, though a functionally distinct mechanism specific to Purview scanning) — giving a single governance plane visibility across a genuinely hybrid, multi-cloud data estate rather than requiring separate governance tooling per environment.

---

## 5. Purview vs. Defender for Cloud — Comparison

| Aspect           | Microsoft Defender for Cloud ([Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md)) | Microsoft Purview                                                                                          |
| ---------------- | -------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| Core question    | "Is this resource configured securely, and is it under active attack?"                                   | "Where does sensitive data actually live, and is it classified and governed appropriately?"                |
| Unit of analysis | Resource configuration and runtime behavior                                                              | Data content and schema, at the column/file/document level                                                 |
| Output           | Recommendations, Secure Score, security alerts                                                           | Data Map, catalog entries, classification/sensitivity labels, estate-wide governance insights              |
| Primary consumer | Security/cloud engineering teams                                                                         | Data governance teams, data stewards, privacy/compliance teams, and — via label correlation — SOC analysts |
| Relationship     | Protects the "container" (the storage account, the VM, the database engine)                              | Inventories and classifies the "contents" (the actual sensitive data inside that container)                |

🎯 **Interview Tip:** a precise answer distinguishing these two services should avoid the common trap of treating them as competing or redundant — they operate at entirely different layers and are complementary, not overlapping: Defender for Cloud would flag a storage account with public blob access enabled as a misconfiguration regardless of what's inside it; Purview would separately tell you that the same storage account happens to contain a column matching a credit-card-number pattern — the combination (a _misconfigured_ container that also happens to hold _sensitive_ data) is the genuinely high-priority finding neither tool alone fully captures, and mature security programs correlate both signals rather than treating either as sufficient on its own.

---

## 6. Architecture Diagram

```
                    Microsoft Purview Account
                    ┌─────────────────────────────┐
                    │  Data Map  (metadata graph)   │
                    │  Data Catalog (search/glossary)│
                    │  Classification/Labeling Engine │
                    └───────────┬─────────────────┘
                                │  scheduled scans
        ┌───────────────────────┼───────────────────────┐
        │                       │                       │
 Azure Storage            Azure SQL DB /            On-Premises /
 (Blob, ADLS Gen2)         Cosmos DB / Synapse       Multi-Cloud
 Section 17, 20            Section 29-33             (via Self-Hosted
                                                       Integration Runtime,
                                                       or AWS S3 connector)

Classification results / sensitivity labels flow onward to:
  → Section 92-95 (Sentinel): sensitive-label context enriches security incidents
  → Section 58: compliance dashboard evidence for regulated data handling
  → Section 56 (Key Vault): confirms genuinely sensitive data has appropriate
    encryption-key/secret-management backing it, closing the loop from
    "we found it" to "it's properly protected"
```

## 7. Configuration & Hands-On Example

**Registering a storage account as a Purview data source and triggering a scan (via Azure CLI, using the `purview` extension):**

```bash
az extension add --name purview

az purview account create \
  --resource-group rg-governance \
  --account-name purview-corp-prod \
  --location eastus \
  --managed-resource-group-name rg-purview-managed

az purview account show \
  --resource-group rg-governance \
  --account-name purview-corp-prod \
  --query "endpoints"
```

- **Purpose:** provisions a Purview account (which internally creates a managed Event Hubs namespace and Storage account for scan-result ingestion) and retrieves its Data Map/Catalog API endpoints, the prerequisite step before registering any data source for scanning.
- **Important arguments explained individually:**
  - `--managed-resource-group-name` — Purview provisions supporting infrastructure (an internally-managed storage account and Event Hubs namespace used for scan ingestion) into a dedicated, Azure-managed resource group, conceptually similar to AKS's node-resource-group pattern ([Section 36](../Part7/Section-36-Part7-AKS-Architecture.md)) — this argument names that managed group explicitly rather than accepting an auto-generated name, useful for governance clarity in environments with strict resource-group naming conventions.
  - `account-name` — must be globally unique, since it forms part of the account's regional API endpoint hostname.
- **Common error:** attempting to register data-source scans immediately after account creation before the managed resource group and underlying ingestion infrastructure has finished provisioning — Purview account creation is not instantaneous; scan registration calls made too early fail with a resource-not-ready error and simply need a short retry delay.

**Registering an Azure Data Lake Storage Gen2 source and creating a scan (conceptual, via the Purview Studio-backed Scan API — illustrative REST payload shape):**

```json
{
  "kind": "AzureDataLakeStorageGen2Credential",
  "properties": {
    "endpoint": "https://stcorpprod.dfs.core.windows.net/",
    "collection": { "referenceName": "finance-data-collection" },
    "scanRulesetName": "AzureDataLakeStorageGen2",
    "scanRulesetType": "System"
  }
}
```

- **Purpose:** registers an ADLS Gen2 account ([Section 17](../Part4/Section-17-Part4-Blob-Storage-Deep-Dive.md)) into a specific Purview **collection** (a logical grouping used for access control and organization within the catalog — directly analogous in purpose to a resource group's organizational role, but scoped to catalog assets rather than deployable resources) and applies the built-in system scan ruleset (the default set of classifiers, 91.3.3) to it.
- **Important arguments explained individually:**
  - `collection` — collections form their own hierarchy within Purview and support delegated RBAC (a specific team can be granted access to manage scans/view catalog entries only within their own collection), directly mirroring the management-group/subscription scoping principle from [Section 4](../Part1/Section-04-Part1-Azure-Resource-Manager.md), now applied to data-catalog organization rather than deployable-resource organization.
  - `scanRulesetName` — can reference the built-in system ruleset (all Microsoft classifiers) or a custom ruleset scoped to only the organization's own custom classifiers, trading broader coverage against faster/cheaper scans depending on actual classification needs.
- **Common error:** scanning a data source using credentials/managed identity lacking sufficient read permission on the target — the scan fails partially or entirely, and the resulting Data Map entry silently under-represents the source's actual sensitive-data content, producing a false sense of governance coverage; always verify scan completion status and asset counts against expected estate size rather than assuming a "succeeded" scan status alone guarantees complete coverage.

---

## 8. Production & Enterprise Usage

Enterprises with a large, distributed data estate — replicated exactly the pattern already established for Defender for Cloud in [Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md).8.1 — enforce Purview scanning coverage via **Azure Policy** ([Section 57](../Part11/Section-57-Part11-Azure-Policy-Blueprints.md)) at management-group scope, ensuring newly provisioned storage accounts and databases are automatically registered for scanning rather than depending on each application team remembering to onboard their own data source manually. A single, centrally-owned Purview account is typically used across an entire tenant (registering data sources across many subscriptions into collections scoped per business unit or environment), directly mirroring the centralized-vs-team-owned Log Analytics workspace pattern from [Section 50](../Part10/Section-50-Part10-Azure-Monitor-Fundamentals.md).8, now applied to data governance rather than operational telemetry.

## 9. Security Considerations

- The managed identity or service principal Purview uses to scan a data source needs read access to that source's actual content (not merely metadata) to perform classification — this makes the Purview scanning identity itself a genuinely sensitive credential requiring careful RBAC scoping ([Section 8](../Part2/Section-08-Part2-Role-Based-Access-Control.md)) and monitoring, since a compromised scanning identity would have broad read access across the entire registered data estate.
- Classification results and the catalog itself contain a summary of _where sensitive data lives_ — this metadata is itself sensitive (a map of an organization's most valuable data is a high-value target for an attacker), and access to the Purview catalog/Data Map should be scoped via collection-level RBAC rather than granted broadly.

## 10. Performance Considerations

Full scans of very large data estates (petabyte-scale Data Lake accounts, large database estates) can take significant time and consume scanning-infrastructure throughput; incremental scans (scanning only new/changed data since the last successful scan) are the recommended default for recurring scan schedules, reserving full re-scans for less frequent, deliberate estate-wide reclassification passes (e.g., after a significant classifier ruleset update) — ⚠️ verify current incremental-scan support and behavior per source type against documentation, as coverage varies by connector.

## 11. Monitoring

Purview scan run history, success/failure status, and asset-count trends are visible within Purview Studio and exportable to a Log Analytics workspace ([Section 51](../Part10/Section-51-Part10-Log-Analytics-KQL.md)) for KQL-based trend analysis and alerting — directly reusing the same diagnostic-export pattern established in [Section 50](../Part10/Section-50-Part10-Azure-Monitor-Fundamentals.md).4.2, now applied to data-governance-specific telemetry (e.g., alerting when a scheduled scan fails repeatedly, which would otherwise silently degrade classification coverage without anyone noticing).

## 12. Troubleshooting

| Symptom                                                                                | Likely Cause                                                                                                        | Fix                                                                                                                                                                                                    |
| -------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Newly provisioned storage account shows no classification results weeks after creation | No scan registered against the new source; auto-registration policy not enforced or not covering that resource type | Verify Azure Policy-driven auto-registration ([Section 57](../Part11/Section-57-Part11-Azure-Policy-Blueprints.md)) actually covers the resource type/scope; manually register and scan in the interim |
| Scan completes successfully but a known-sensitive column isn't flagged                 | The relevant system classifier doesn't cover that specific data format, or a custom classifier is needed            | Review classifier coverage against the actual data format; author a custom classifier (regex or exact-data-match) for organization-specific sensitive-data patterns                                    |
| Scan fails with an authorization error                                                 | Purview's scanning identity lacks sufficient read permission on the target data source                              | Verify and grant the required RBAC role/access on the source specifically for the Purview managed identity or service principal used for that scan                                                     |
| Catalog search returns stale results for a recently modified dataset                   | Scan schedule hasn't run since the change, or incremental scan missed the change                                    | Verify scan schedule/frequency; trigger a manual scan run to confirm current state                                                                                                                     |

## 13. Interview Questions — [Section 91](./Section-91-Part17-Microsoft-Purview.md)

### 🎯 Intermediate

**Q: What specific gap does Microsoft Purview close that Defender for Cloud ([Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md)) does not address?**

_Model answer:_ Defender for Cloud assesses whether resources are configured securely and detects active threats against them (CSPM/CWPP) — but it has no visibility into what data actually lives inside those resources. Purview closes that gap by scanning data sources (storage accounts, databases, on-premises/multi-cloud sources) to discover, classify, and catalog the actual sensitive data content — answering "where is our sensitive data and is it labeled/governed appropriately," a question orthogonal to and complementary with Defender for Cloud's configuration-and-threat focus.

_What the interviewer is probing:_ whether the candidate understands these are complementary tools operating at different layers (infrastructure/config vs. data content) rather than competing or redundant products — a common point of confusion given both fall under the broad "Azure security" umbrella.

### 🎯 Senior/Architect

**Q: A regulator asks your organization to demonstrate, within 48 hours, every location where customer national-ID numbers are stored across your Azure estate, spanning 40 subscriptions ([Section 67](../Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md)'s scenario). How would you have prepared for this in advance, and how would you respond?**

_Model answer:_ Preparation would center on Purview being deployed proactively, not reactively — a centrally-owned Purview account with scan coverage enforced via Azure Policy ([Section 57](../Part11/Section-57-Part11-Azure-Policy-Blueprints.md)) at management-group scope across all 40 subscriptions, ensuring every storage account and database is auto-registered for scanning as it's created, with a custom classifier specifically authored to match the organization's national-ID number format (since a generic system classifier may not exactly match a jurisdiction-specific ID format). With that groundwork in place, responding to the regulator's request becomes a Data Catalog search filtered by that classification/sensitivity label across all collections, rather than a frantic, manual, subscription-by-subscription audit — the search returns every classified asset location, its owning team (via the catalog's ownership/stewardship metadata, [Section 91](./Section-91-Part17-Microsoft-Purview.md).3.2), and can be cross-referenced against Defender for Cloud's Secure Score ([Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md)) for those specific resources to additionally confirm they're appropriately configured, not merely inventoried. Without this proactive Purview deployment, the honest answer to a 48-hour regulatory request across 40 subscriptions would likely be "we cannot reliably produce this," which is itself the strongest argument for treating estate-wide data classification as a standing governance capability rather than a one-time audit exercise.

_What the interviewer is probing:_ recognition that Purview's real value is in continuous, proactive coverage rather than point-in-time discovery, and the ability to connect classification results back to ownership metadata and Defender for Cloud posture as a combined governance-plus-security answer, not two disconnected tools.

## 14. Common Misconceptions

- **"Purview is just a rebrand of Azure Data Catalog / a simple metadata browser."** False — while it does include a searchable catalog, its core value in a security context is automated, continuous, estate-wide sensitive-data classification and the resulting governance/risk signal, not merely a passive metadata browsing tool.
- **"Enabling Purview automatically encrypts or restricts access to discovered sensitive data."** False — Purview discovers, classifies, and labels; it does not itself enforce access restrictions or apply encryption. Acting on a classification result (restricting access, applying DLP, verifying Key Vault-backed encryption, [Section 56](../Part11/Section-56-Part11-Key-Vault.md)) is a separate step that must be deliberately connected to Purview's findings.
- **"Column-level classification in Azure SQL and Purview's classification are two unrelated things."** False — Purview centralizes and can consume SQL Data Discovery & Classification results ([Section 29](../Part6/Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md)) alongside every other scanned source, rather than requiring classification to be managed separately per database engine.

## 15. Key Takeaways

- 🔑 Purview answers "where does sensitive data live and is it classified/governed appropriately" — a data-content question entirely distinct from and complementary to Defender for Cloud's ([Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md)) infrastructure-configuration and threat-detection focus.
- 🔑 The Data Map (metadata inventory), Data Catalog (searchable, business-glossary-linked layer), and classification/sensitivity labeling engine are Purview's three foundational capabilities, working together across Azure-native, on-premises, and multi-cloud sources.
- 🔑 Column-level and file-level classification connects directly to the storage (Part 4) and database (Part 6) services covered earlier in this roadmap, adding a governance layer on top of infrastructure that was previously only assessed for configuration and redundancy.
- 🔑 Sensitivity labels and classification results are the upstream signal that later Part 17 sections (Sentinel, [Section 92](./Section-92-Part17-Microsoft-Sentinel-SIEM-Fundamentals.md)-[Section 93](./Section-93-Part17-Sentinel-Deep-Dive.md)) correlate with security incidents — a data-exposure incident against classified-sensitive data is a materially higher priority than the same incident against unclassified data.
- 🔑 Enterprise-scale Purview adoption requires the same management-group-scoped, policy-enforced auto-registration pattern already established for Defender for Cloud ([Section 55](../Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md).8.1) — proactive, continuous coverage, not a one-time audit.

## 16. Related Concepts (Next Up)

[Section 92](./Section-92-Part17-Microsoft-Sentinel-SIEM-Fundamentals.md) begins the SIEM/SOAR half of Part 17 with **Microsoft Sentinel Fundamentals** — the cloud-native SIEM built directly on top of the Log Analytics workspace ([Section 51](../Part10/Section-51-Part10-Log-Analytics-KQL.md)) that will consume security signal from across the estate, including, where wired up, Purview's classification and sensitivity-label context established in this section, to enrich and prioritize the security incidents Sections 93-95 cover in depth.
