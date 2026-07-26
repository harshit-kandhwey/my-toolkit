# Section 84 — ML on Azure Fundamentals & Azure Machine Learning

## 1. Definition

**Plain language:** Azure Machine Learning (Azure ML, often abbreviated AML) is Microsoft's managed platform for building, training, and deploying machine learning models. Instead of standing up your own servers, wrangling Python environments, and manually tracking which dataset produced which model, Azure ML gives you a workspace that centralizes the compute, the data, the experiment history, and the resulting models in one place, with the plumbing needed to move a model from a notebook to a production endpoint.

**Precise definition:** **Azure Machine Learning** is a managed cloud service (`Microsoft.MachineLearningServices/workspaces` as an ARM resource, Section 4) providing an end-to-end platform for the ML lifecycle — data preparation, experimentation, training (at scale, on managed or attached compute), model registration/versioning, and deployment to real-time or batch inference endpoints — built around a central **workspace** resource that acts as the organizing container for every other AML asset (compute, data, experiments, models, endpoints).

## 2. Why It Exists / Problem It Solves

Every earlier Part in this roadmap has covered infrastructure that generic applications need: compute (Part 3), storage (Part 4), networking (Part 5), databases (Part 6), and — most recently — the data engineering stack in Part 15 (Data Lake in Section 75, Synapse in Section 76, Data Factory in Section 77, Databricks in Section 78) that gets raw data cleaned, transformed, and staged somewhere queryable. Azure ML picks up exactly where Part 15 leaves off: once data is clean and accessible in ADLS Gen2 (Section 75) or a Synapse/Databricks table, the next problem is training a model on it, and that problem has its own distinct pain points that plain VMs (Section 11) don't solve out of the box — reproducibility (which code, data, and library versions produced this specific model?), scale-out training across GPU clusters that spin up only when needed, experiment comparison across dozens of hyperparameter runs, and a controlled path from "a data scientist's notebook" to "an API a production application calls." Azure ML exists to solve these ML-specific lifecycle problems the same way AKS (Section 34) solves container orchestration problems that plain VMs don't address — it's a purpose-built layer on top of general compute and storage, not a replacement for either.

## 3. The Azure ML Workspace

### 3.1 Workspace as the Central Resource

**Definition:** The **workspace** is the top-level Azure ML resource that every other AML asset — compute targets, datastores, experiments/jobs, environments, models, and endpoints — is scoped underneath. Creating a workspace provisions (or attaches) a set of dependent Azure resources it relies on: a Storage Account (Section 16, for artifacts, logs, and default datastore), a Key Vault (Section 56, for storing secrets/credentials used by the workspace), Application Insights (Section 52, for endpoint monitoring), and optionally a Container Registry (for storing built training/inference images).

**Why this matters architecturally:** because the workspace automatically wires itself to Key Vault and Application Insights, security and monitoring aren't afterthoughts bolted onto AML — secrets used by training jobs or deployed endpoints (connection strings, API keys for external services) are meant to be stored in the associated Key Vault and referenced rather than hardcoded, and endpoint telemetry flows into Application Insights by default, consistent with the observability patterns established in Part 10.

### 3.2 Workspace Identity and Access

Azure ML workspaces support **Managed Identities** (Section 9) as their authentication mechanism to other Azure resources — a workspace's system-assigned or user-assigned managed identity can be granted RBAC roles (Section 8) on a storage account, Key Vault, or container registry, letting training jobs and endpoints access those resources without embedding credentials in code or configuration. This is the same identity pattern used throughout the KB (an AKS pod's identity in Section 34, a Function's identity in Section 40) applied specifically to ML workloads — a training job that reads from ADLS Gen2 authenticates via the workspace's managed identity and an RBAC role grant on the storage account, not a connection string in a notebook cell.

⚠️ Azure ML's specific default authentication modes for datastores (identity-based vs. credential-based access) and workspace networking options change fairly often as the product matures — verify current defaults and recommended patterns against official documentation before designing a new workspace's access model.

## 4. Compute in Azure ML

### 4.1 Compute Instances

**Definition:** A **Compute Instance** is a fully managed, single-node development VM intended for interactive work — a data scientist's personal notebook environment, pre-configured with common ML frameworks and SDKs, that they can start, use for exploratory analysis, and stop when not in use.

**How it works conceptually:** it functions like a hosted, pre-provisioned Jupyter/VS Code environment tied to the workspace, with direct access to the workspace's datastores and compute clusters — it is not itself meant for large-scale training, only for the interactive authoring of the code that submits training jobs to run elsewhere.

### 4.2 Compute Clusters

**Definition:** A **Compute Cluster** is a managed, multi-node, auto-scaling cluster of VMs used to actually execute training jobs — it scales from zero nodes (when idle, incurring no compute cost) up to a configured maximum node count as jobs are submitted, then scales back down automatically.

**Why this distinction matters:** Compute Instances are for a human iterating in a notebook; Compute Clusters are for the platform executing a queued, potentially long-running or parallelized training job — conflating the two (e.g., trying to run a multi-hour distributed training job directly on a Compute Instance) defeats the auto-scaling cost benefit and the ability to run many training jobs concurrently on independently-scaling cluster nodes.

### 4.3 Attached Compute — AKS and Other Targets

Azure ML can also attach existing compute resources it doesn't fully manage itself — most notably an existing AKS cluster (Section 34) for high-throughput inference, or (less commonly today) attached VMs or HDInsight clusters. This lets an organization that already operates AKS for other workloads reuse that same operational investment for ML inference rather than standing up a wholly separate inference platform.

## 5. Datastores and Datasets

### 5.1 Datastores

**Definition:** A **Datastore** is a registered reference within the workspace pointing to an underlying data source — most commonly an Azure Blob container or ADLS Gen2 filesystem (Section 16, Section 75), but also Azure SQL Database (Section 29) or other sources — storing the connection information (and, depending on configuration, authentication approach) so that training code references the datastore by name rather than embedding storage account keys or connection strings directly in scripts.

**How it works conceptually:** this is directly analogous to a Synapse or Data Factory Linked Service (Section 77) — an abstraction layer decoupling "where is my data" and "how do I authenticate to it" from the code that actually consumes the data, so the same training script works unchanged whether pointed at a dev storage account or a production ADLS Gen2 filesystem.

### 5.2 Data Assets (formerly Datasets)

**Definition:** A **Data Asset** is a versioned, registered reference to a specific set of data within a datastore (a specific file, folder, or table, at a specific version) — giving training jobs a reproducible, named handle on "exactly this data" rather than a mutable path that might contain different files by the time a job actually runs.

⚠️ Azure ML has renamed and restructured its data-referencing concepts more than once (Datasets → Data Assets, with both v1 and v2 SDK/CLI concepts having existed side by side for a period) — verify current terminology and the v2 CLI/SDK data asset syntax against official documentation, since older tutorials and blog posts may reference deprecated v1 concepts.

## 6. The General ML Lifecycle Shape on Azure

At a high level, a typical Azure ML lifecycle runs: (1) data lands in ADLS Gen2 or a Synapse/Databricks table via the Part 15 data engineering pipeline; (2) a Datastore and Data Asset register a reference to that data within the AML workspace; (3) a data scientist explores the data interactively on a Compute Instance; (4) a training job is submitted to a Compute Cluster, tracked as an experiment run; (5) the resulting model is registered in the AML Model Registry; (6) the registered model is deployed to a real-time or batch inference endpoint. Section 85 picks up this lifecycle in depth starting from step 4 — training jobs, hyperparameter tuning, pipelines, the model registry, and both endpoint types.

## 7. Architecture Diagram

```
Part 15 Data Engineering Layer
  ADLS Gen2 (Section 75) / Synapse (76) / Databricks (78)
        │
        ▼
Azure ML Workspace ("mlw-project")
  ├── Datastore ──► Data Asset (versioned reference to training data)
  ├── Key Vault (Section 56) ──► secrets for training jobs/endpoints
  ├── Application Insights (Section 52) ──► endpoint telemetry
  ├── Storage Account ──► artifacts, run logs, default datastore
  │
  ├── Compute Instance ──► interactive notebook (data scientist)
  │
  └── Compute Cluster (auto-scale 0→N nodes)
         │
         ▼
   Training Job (Section 85) ──► Model Registry ──► Inference Endpoint
```

## 8. Configuration & Hands-On Example

**Creating an Azure ML workspace and a compute cluster via Azure CLI (`az ml` extension, v2):**

```bash
az extension add -n ml

az ml workspace create \
  --resource-group rg-ml-prod \
  --name mlw-project \
  --location eastus

az ml compute create \
  --resource-group rg-ml-prod \
  --workspace-name mlw-project \
  --name cpu-cluster \
  --type AmlCompute \
  --min-instances 0 \
  --max-instances 4 \
  --size Standard_DS3_v2
```

- **Purpose:** Provisions the central AML workspace (which in turn provisions its dependent Storage Account, Key Vault, and Application Insights resources if not supplied explicitly) and a managed, auto-scaling compute cluster ready to accept training jobs.
- **Important arguments explained individually:**
  - `--type AmlCompute` — specifies a managed Azure ML compute cluster, as opposed to attaching an existing AKS cluster or other compute target (Section 84.4.3).
  - `--min-instances 0` — allows the cluster to scale to zero nodes when idle, meaning no compute cost is incurred between training runs; this is the key cost-efficiency lever of Compute Clusters versus an always-on VM.
  - `--size Standard_DS3_v2` — the VM SKU used for each cluster node; GPU-backed SKUs (e.g., the `Standard_NC` family) would be selected instead for deep learning workloads needing GPU acceleration.
- **Common error:** Submitting a training job that references a Compute Instance name instead of a Compute Cluster name fails, or runs but blocks other interactive work, because Compute Instances are single-node and intended for interactive use, not queued job execution (Section 84.4.1 vs 84.4.2) — this distinction is a frequent source of confusion for teams new to AML.

## 9. Production & Enterprise Usage

Enterprises typically provision separate AML workspaces per environment (dev/test/prod) or per business unit, following the same environment-segregation logic used for other Azure resources throughout this KB, with production workspaces configured with private networking (no public endpoint, accessed via Private Link, echoing the pattern established for Key Vault in Section 56.7 and PaaS services generally in Section 23.5) and datastore access governed by managed identity RBAC grants rather than storage account keys. Compute clusters are frequently configured with a modest `min-instances` (sometimes non-zero for latency-sensitive shared team clusters) and a `max-instances` ceiling tied to a cost budget, with Azure Policy (Section 57) sometimes used to restrict which VM SKUs (and, notably, which GPU SKUs, given their cost) are permitted within a given subscription or resource group.

## 10. Security Considerations

- Workspace-associated Key Vault (Section 56) should hold all secrets training jobs or endpoints need (external API keys, database credentials) — never hardcoded in notebooks or training scripts, which are frequently checked into source control.
- Datastore access should prefer identity-based authentication via the workspace's Managed Identity (Section 9) with RBAC-scoped permissions, rather than storing storage account keys or SAS tokens directly in the datastore registration, minimizing the blast radius of a leaked credential.
- Private networking (private endpoints for the workspace, storage account, and Key Vault) is the recommended posture for production workspaces handling sensitive training data, preventing data exfiltration paths over the public internet — this becomes especially important once Part 16 reaches generative AI and RAG patterns (Section 88), where training/grounding data may include sensitive enterprise content.

## 11. Performance Considerations

Compute Cluster node count and VM SKU (CPU vs. GPU, and GPU generation/family) are the primary levers for training throughput — under-provisioned clusters queue jobs or throttle distributed training, while over-provisioned `max-instances` ceilings risk runaway cost if a misconfigured job spins up far more nodes than a workload actually needs. Data locality also matters: training jobs reading from a datastore in a different region than the compute cluster incur cross-region data transfer latency and cost, so co-locating the AML workspace, its compute, and its primary datastores in the same region is the default best practice.

## 12. Monitoring

Azure ML integrates with Azure Monitor and Application Insights (Part 10) for compute utilization, job status, and (once a model is deployed, Section 85) endpoint request/latency/error telemetry — the AML Studio UI additionally surfaces job-level metrics and logs directly, useful during active experimentation before a workload matures to the point of needing full Azure Monitor dashboards and alerts (Section 53).

## 13. Troubleshooting

| Symptom                                                                       | Likely Cause                                                                                                                                                                                             | Fix                                                                                                                 |
| ----------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Training job stuck in "queued" state indefinitely                             | Compute Cluster `max-instances` already at capacity, or cluster scale-up delay                                                                                                                           | Check cluster node status/utilization; increase `max-instances` if consistently at capacity                         |
| Job fails with an authentication/access-denied error reading from a datastore | Workspace Managed Identity lacks the required RBAC role on the underlying storage account                                                                                                                | Grant the workspace's managed identity the appropriate role (e.g., Storage Blob Data Reader) on the storage account |
| Compute Instance costs higher than expected                                   | Compute Instance left running rather than stopped after interactive use (Compute Instances, unlike Compute Clusters, don't auto-scale to zero on their own without an idle-shutdown schedule configured) | Configure an auto-shutdown/idle-shutdown schedule on the Compute Instance, or stop it manually after use            |

## 14. Interview Questions — Section 84

### 🎯 Intermediate

**Q: What's the difference between a Compute Instance and a Compute Cluster in Azure ML, and why does the distinction matter?**

_Model answer:_ A Compute Instance is a single-node, always-addressable development VM meant for interactive work — a data scientist's personal notebook environment. A Compute Cluster is a multi-node, auto-scaling (including scale-to-zero) cluster meant for executing submitted training jobs, not for interactive use. The distinction matters for both cost and correctness: running a long, resource-intensive training job directly on a Compute Instance defeats the auto-scaling cost benefit of a cluster and ties up a single node that should instead be available for interactive exploration, while submitting interactive, iterative notebook work as cluster jobs adds unnecessary job-queueing overhead for something that should be immediate and interactive.

_What the interviewer is probing:_ whether the candidate understands AML's compute model well enough to architect cost-efficient, correctly-separated interactive-vs-batch workflows, rather than treating all AML compute as interchangeable.

### 🎯 Senior/Architect

**Q: A data science team wants to onboard onto Azure ML, training models on sensitive customer data currently sitting in ADLS Gen2. Walk through how you'd architect the workspace to be secure and production-ready from day one.**

_Model answer:_ I'd provision a dedicated Azure ML workspace per environment (dev/test/prod), each with its dependent Storage Account, Key Vault, and Application Insights, configured with private endpoints rather than public network access, consistent with the Private Link pattern used elsewhere for PaaS resources (Section 23.5, Section 56.7). Rather than storing storage account keys on the datastore pointing at the ADLS Gen2 filesystem, I'd grant the workspace's system-assigned Managed Identity (Section 9) an appropriate RBAC role (e.g., Storage Blob Data Reader, scoped as narrowly as possible) directly on the storage account, so datastore access is identity-based rather than credential-based. Any additional secrets training jobs need (external API keys, service credentials) would go into the workspace's associated Key Vault, referenced by the training code rather than hardcoded. For compute, I'd use auto-scaling Compute Clusters with a `min-instances` of zero to control idle cost, and use Azure Policy (Section 57) to restrict which VM SKUs — particularly GPU SKUs — are permitted in the resource group, to keep both cost and the compliance posture predictable. Given the sensitivity of customer data, I'd also loop in whatever Responsible AI and data governance requirements apply (expanded on in Section 89) before any model trained on this data moves toward deployment.

_What the interviewer is probing:_ whether the candidate designs for security (private networking, identity-based access, least-privilege RBAC) and cost control from the outset rather than bolting these on after an initial "get it working" pass — and whether they connect this specific scenario to the KB's broader security patterns (Managed Identity, Key Vault, Private Link, Policy) rather than treating AML as an isolated silo.

## 15. Common Misconceptions

- **"Azure ML compute clusters run 24/7 like a VM."** False — Compute Clusters are designed to auto-scale to zero nodes when idle, incurring no compute cost between training runs; only Compute Instances need to be explicitly stopped to avoid ongoing charges.
- **"Any data source can be referenced directly in training code without a datastore."** False — while technically possible for quick experiments, the intended pattern registers a Datastore (and versioned Data Asset) so training code references data by a stable, access-controlled name rather than embedding raw connection details.
- **"The AML workspace is just a UI wrapper — the real work happens entirely outside it."** False — the workspace is the actual scoping and access-control boundary for compute, data, experiments, and models; its associated Key Vault, Storage Account, and Application Insights resources are functionally load-bearing, not cosmetic.

## 16. Key Takeaways

- 🔑 The Azure ML workspace is the central resource every other AML asset is scoped under, and it provisions dependent Storage Account, Key Vault, and Application Insights resources that are functionally integral, not optional add-ons.
- 🔑 Compute Instances are for interactive, single-node development work; Compute Clusters are for auto-scaling, queued training job execution — conflating the two undermines both cost efficiency and workflow correctness.
- 🔑 Datastores and Data Assets decouple training code from raw connection strings and mutable data paths, mirroring the Linked Service abstraction pattern from Data Factory (Section 77).
- 🔑 Identity-based datastore access via the workspace's Managed Identity and scoped RBAC is the recommended pattern over storage account keys, consistent with the identity-first approach used throughout this KB.
- 🔑 Azure ML sits on top of, not instead of, the Part 15 data engineering stack — training data typically originates in ADLS Gen2, Synapse, or Databricks before ever reaching an AML datastore.

## 17. Related Concepts (Next Up)

Section 85 continues directly into the substance of actually using Azure ML for training and inference: submitting training jobs and tracking them as experiments, running hyperparameter tuning via sweep jobs, chaining steps together with AML Pipelines, registering trained models in the Model Registry, and deploying those models to real-time managed online endpoints or batch inference endpoints.
