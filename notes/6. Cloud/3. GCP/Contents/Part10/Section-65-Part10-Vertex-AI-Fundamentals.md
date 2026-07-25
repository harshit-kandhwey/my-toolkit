# Section 65 (Part 10): ML on GCP Fundamentals & Vertex AI

## 65.1 Definition

**Plain language:** Vertex AI is Google Cloud's single, unified platform for building, training, and deploying machine learning models — from simple no-code AutoML models to fully custom deep learning training jobs to generative AI applications built on Gemini. It's the one place you go on GCP to do machine learning, rather than piecing together a dozen separate, loosely connected services.

**Precise:** Vertex AI is a fully managed machine learning platform that consolidates data preparation, feature management, model training (AutoML and custom), model hosting/serving, MLOps tooling (pipelines, monitoring, experiment tracking), and generative AI capabilities (Model Garden, Gemini API, Vertex AI Studio) under one API surface, one SDK (`google-cloud-aiplatform`), one console experience, and one consistent IAM/networking model.

## 65.2 Why It Exists / Problem It Solves

Google's early ML tooling on GCP grew organically and, as a result, fragmented: **AI Platform** (formerly Cloud ML Engine) handled custom training and prediction; **AutoML Tables**, **AutoML Vision**, **AutoML Natural Language**, and **AutoML Video** were separate no-code products each with their own console pages, APIs, and quota systems; feature engineering and experiment tracking had no first-party home at all. Section 1.4 mentioned this consolidation briefly — by the early 2020s Google had accumulated enough separate ML products that data scientists had to learn multiple inconsistent APIs, manage separate IAM permissions per product, and manually stitch together pipelines that moved data and models between them.

Vertex AI (launched 2021) exists to solve this fragmentation directly:

- **One API and SDK** instead of a dozen separate ones, so code written for AutoML tabular models and code written for custom PyTorch training jobs share the same client library patterns.
- **One place for the full lifecycle** — data, training, tuning, deployment, monitoring, and generative AI — so a model doesn't have to "leave" the platform between steps.
- **Consistent governance** — one IAM permission model, one VPC Service Controls perimeter (Section 41), one Model Registry — instead of securing each fragmented product separately.

## 65.3 Core Concepts

### 65.3.1 Vertex AI Workbench (Managed Notebooks)

**Vertex AI Workbench** provides managed Jupyter notebook instances pre-configured with ML frameworks (TensorFlow, PyTorch, scikit-learn), direct integration with BigQuery and Cloud Storage for data access, and integrated Git support. Two flavors exist:

- **Instance-based Workbench**: a single-user managed VM running JupyterLab, similar in spirit to a persistent development notebook you fully control (choose machine type, GPUs, idle-shutdown schedules).
- **Vertex AI Workbench (managed, serverless-leaning)**: a more automated, managed notebook runtime with less infrastructure management, oriented toward teams that don't want to administer the underlying VM at all.

Workbench is the starting point for exploratory data analysis and prototyping before graduating to a formal Training Job (Section 66).

### 65.3.2 Vertex AI Datasets

A **Vertex AI Dataset** is a managed resource that wraps a training dataset (tabular, image, text, video, or time-series) with metadata — labels, annotations, and a defined schema — so the same dataset resource can be reused consistently across AutoML training, custom training, and data labeling workflows. Datasets can ingest data directly from BigQuery tables or Cloud Storage buckets (CSV, JSONL, image/video files), letting Vertex AI's own data-lineage tooling track exactly which underlying data a given trained model came from.

### 65.3.3 Vertex AI Feature Store

**Feature Store** is a centralized repository for storing, sharing, and serving ML **features** (the individual input variables a model consumes, e.g., "customer_lifetime_value" or "days_since_last_purchase"). It solves two distinct problems:

1. **Training/serving skew**: without a Feature Store, teams often compute features slightly differently for offline training versus online (real-time) prediction, causing subtle model-quality bugs. Feature Store provides one definition of a feature, served consistently to both training jobs (batch reads) and online prediction endpoints (low-latency point reads).
2. **Feature reuse across teams**: a "customer risk score" feature engineered by one team can be published to Feature Store and reused by other teams' models without re-implementing the same transformation logic.

Feature Store organizes data into **Featurestores → EntityTypes → Features** (e.g., Featurestore "retail" → EntityType "customer" → Features "lifetime_value", "churn_risk").

### 65.3.4 Model Registry (Preview)

The **Vertex AI Model Registry** is the central catalog of all trained models — AutoML and custom — with version history, deployment status, and evaluation metrics attached. It's covered in depth alongside training and deployment in Section 66, but is introduced here as the piece that ties Datasets, Feature Store, and training jobs together into one lifecycle: data goes in, a model comes out and is registered, and the registered model is what gets deployed.

## 65.4 Comparison: Vertex AI vs. AWS SageMaker vs. Azure Machine Learning

| Dimension                 | Vertex AI (GCP)                                         | SageMaker (AWS)                                     | Azure Machine Learning                                              |
| ------------------------- | ------------------------------------------------------- | --------------------------------------------------- | ------------------------------------------------------------------- |
| Unified platform history  | Consolidated in 2021 from AI Platform + AutoML products | Purpose-built as a single platform from 2017 launch | Evolved from Azure ML Studio (classic) into a unified SDK/workspace |
| Managed notebooks         | Vertex AI Workbench                                     | SageMaker Studio / Notebook Instances               | Azure ML compute instances + notebooks                              |
| No-code/low-code training | AutoML (tabular/vision/text/video)                      | SageMaker Canvas / Autopilot                        | Azure ML Automated ML (AutoML)                                      |
| Feature store             | Vertex AI Feature Store                                 | SageMaker Feature Store                             | Azure ML managed feature store (newer)                              |
| Foundation model catalog  | Model Garden (Gemini + open models)                     | Bedrock model catalog + JumpStart                   | Azure AI Foundry model catalog                                      |
| Pipelines                 | Vertex AI Pipelines (Kubeflow-based)                    | SageMaker Pipelines                                 | Azure ML Pipelines                                                  |
| Underlying orchestration  | Kubeflow Pipelines / TFX                                | Step Functions-like DAG (native)                    | Azure ML native DAG                                                 |
| Native hardware advantage | Custom TPUs alongside GPUs                              | Custom Trainium/Inferentia chips alongside GPUs     | Primarily GPU-based (Azure OpenAI backed by Microsoft/OpenAI infra) |

> 💡 **Tip:** All three major clouds converged on the same shape by the early 2020s — one platform, one SDK, a no-code AutoML layer, a feature store, a pipeline orchestrator, and a foundation-model catalog. If you know one deeply, mapping to the others is mostly a vocabulary exercise, not a conceptual one.

## 65.5 Architecture Diagram

```
                        ┌───────────────────────────────────────────┐
                        │              VERTEX AI PLATFORM           │
                        └───────────────────────────────────────────┘
                                          │
        ┌──────────────────┬──────────────┼─────────────────┬──────────────────┐
        ▼                  ▼              ▼                 ▼                  ▼
 ┌─────────────┐   ┌───────────────┐    ┌──────────┐   ┌─────────────┐  ┌───────────────────┐
 │  Workbench  │   │   Datasets    │    │ Feature  │   │  Training   │  │  Model Garden /   │
 │ (notebooks) │──►│ (BQ / GCS     │──► │  Store   │──►│ (AutoML or  │─►│  Gemini / Vertex  │
 │             │   │  ingested)    │    │(serving) │   │  Custom)    │  │  AI Studio        │
 └─────────────┘   └───────────────┘    └──────────┘   └──────┬──────┘  └───────────────────┘
                                                              │
                                                              ▼
                                                   ┌────────────────┐
                                                   │ Model Registry │
                                                   └───────┬────────┘
                                                           │
                                                  ┌────────┴─────────┐
                                                  ▼                  ▼
                                          ┌───────────────┐   ┌────────────────┐
                                          │Online Endpoint│   │Batch Prediction│
                                          └───────────────┘   └────────────────┘
```

## 65.6 Hands-On Example: Creating a Vertex AI Dataset and Workbench Instance

**Beginner example — create a managed notebook (Workbench instance):**

```bash
gcloud workbench instances create my-ml-notebook \
  --project=my-gcp-project \
  --location=us-central1-a \
  --machine-type=n1-standard-4 \
  --vm-image-project=cloud-notebooks-managed \
  --vm-image-family=workbench-instances
```

**Purpose:** Provisions a managed JupyterLab environment for exploratory analysis and prototyping, pre-authenticated against the project's GCP credentials.

**Expected output:**

```
Waiting for operation [projects/my-gcp-project/locations/us-central1-a/operations/...] to complete...done.
Created instance [my-ml-notebook].
```

**Intermediate example — create a tabular Dataset from BigQuery using the Python SDK:**

```python
from google.cloud import aiplatform

aiplatform.init(project="my-gcp-project", location="us-central1")

dataset = aiplatform.TabularDataset.create(
    display_name="customer-churn-dataset",
    bq_source="bq://my-gcp-project.retail.customer_churn_features",
)

print(dataset.resource_name)
```

**Purpose:** Registers a BigQuery table as a managed Vertex AI Dataset, tracking lineage for any model subsequently trained against it.

**Expected output:**

```
projects/123456789012/locations/us-central1/datasets/1234567890123456789
```

## 65.7 Production & Enterprise Usage

- Enterprises with an existing BigQuery-centric data warehouse (Section 44) typically feed Vertex AI Datasets and Feature Store directly from curated BigQuery tables, treating ML as one more downstream consumer of the same governed data pipeline — the same pattern used for Looker dashboards (Section 48).
- Feature Store is adopted specifically once an organization has more than one team building models against overlapping customer/product data, to avoid each team recomputing the same features with subtly different logic.
- Workbench instances are commonly configured with idle-shutdown schedules and are provisioned inside a Shared VPC (Section 62) so notebook environments inherit the same network security posture as the rest of the enterprise landing zone.

## 65.8 Common Misconceptions

- **Misconception:** "Vertex AI is just AutoML." AutoML (Section 67) is one training approach; Vertex AI also fully supports custom training containers, pipelines, and generative AI — AutoML is the no-code entry point, not the whole platform.
- **Misconception:** "Feature Store is only useful for real-time serving." Feature Store also provides significant value purely for offline training consistency and feature reuse across teams, even for models that only ever run batch prediction.
- **Misconception:** "Vertex AI replaced BigQuery ML." BigQuery ML (training simple models directly via SQL inside BigQuery, Section 44) and Vertex AI are complementary — BigQuery ML is best for teams wanting SQL-native, in-warehouse model training on structured data, while Vertex AI is the platform for the full custom/deep-learning/generative-AI lifecycle. Many organizations use both together.

## 65.9 Interview Questions

**🎯 Beginner:** _What problem did Vertex AI solve when Google launched it in 2021?_
**Model answer:** Before Vertex AI, GCP's ML tooling was fragmented across separate products — AI Platform for custom training, and separate AutoML products for tabular, vision, text, and video — each with its own API, console page, and IAM permissions. Vertex AI unified all of this under one API, one SDK, and one console, so data scientists learn one consistent platform rather than stitching together several inconsistent ones, while also adding shared capabilities like Feature Store and Model Registry that none of the fragmented products had.

**🎯 Intermediate:** _What specific problem does Vertex AI Feature Store solve that a team without it commonly runs into?_
**Model answer:** Training/serving skew — where the code computing a feature for offline model training differs subtly from the code computing that same feature for real-time online prediction, causing the deployed model to behave differently than it did during evaluation. Feature Store provides one canonical definition of each feature, served consistently to both batch training reads and low-latency online prediction reads, eliminating that class of bug. It also lets multiple teams reuse the same engineered features instead of each team re-implementing similar transformation logic independently.

**🎯 Senior/Architect:** _An enterprise has five data science teams, each independently building models against overlapping customer and transaction data in BigQuery, and is seeing inconsistent model behavior in production that traces back to feature computation differences between teams. How would you redesign their ML platform usage?_
**Model answer:** I'd introduce a centralized Vertex AI Feature Store as the single source of truth for shared features (customer lifetime value, transaction velocity, churn risk signals), populated by a governed pipeline reading from the same curated BigQuery tables (Section 44/49) rather than each team writing its own feature-computation SQL. Each team's training jobs and online prediction endpoints would then read features from Feature Store rather than recomputing them, eliminating the training/serving-skew and cross-team-inconsistency issues. I'd pair this with a shared Vertex AI Dataset convention (so lineage is tracked consistently) and a shared Model Registry so all five teams' models are cataloged and governed centrally, with IAM (Section 35) scoping who can publish versus consume features and models. This turns five siloed, inconsistent ML practices into one governed, reusable platform without removing any team's autonomy over their own model architecture choices.

## 65.10 Key Takeaways

- 🔑 Vertex AI unifies what used to be fragmented GCP ML products (AI Platform, separate AutoML products) under one API, SDK, console, and governance model.
- 🔑 Vertex AI Workbench provides managed notebook environments; Datasets wrap training data with lineage tracking from BigQuery or Cloud Storage.
- 🔑 Feature Store solves training/serving skew and enables feature reuse across teams by providing one canonical, consistently-served feature definition.
- 🔑 Vertex AI, SageMaker, and Azure ML converged on the same overall shape — unified platform, AutoML layer, feature store, pipelines, foundation-model catalog — differing mainly in underlying orchestration and custom hardware.

## 65.11 Related Concepts

BigQuery (Section 44) as a common upstream data source, IAM (Section 35) for governing platform access, VPC Service Controls (Section 41) for perimeter security around Vertex AI resources (detailed in Section 70), and Vertex AI Deep Dive — Training, Pipelines & Endpoints (Section 66), which builds directly on the Datasets and Feature Store concepts introduced here.
