# Section 66 (Part 10): Vertex AI Deep Dive — Training, Pipelines & Endpoints

## 1. Definition

**Plain language:** Once you have data in a Vertex AI Dataset or Feature Store ([Section 65](./Section-65-Part10-Vertex-AI-Fundamentals.md)), you need to actually train a model, tune it to perform well, package it in a way other systems can call, and keep repeating that process reliably as data changes. This section covers the mechanics of doing that: how training jobs run, how hyperparameter tuning searches for the best model configuration, how Pipelines automate the whole sequence, and how trained models get served for predictions.

**Precise:** Vertex AI Training provides managed custom training jobs (prebuilt or custom containers) and hyperparameter tuning; Vertex AI Pipelines is a managed, serverless orchestrator for multi-step ML workflows built on the open-source Kubeflow Pipelines SDK; the Model Registry catalogs trained model versions; and Vertex AI Endpoints provide both real-time (online) and batch prediction serving for registered models.

## 2. Why It Exists / Problem It Solves

Training a model well, in production, at scale requires solving several distinct problems that a single `model.fit()` call in a notebook does not address:

- **Provisioning the right compute** (potentially GPUs/TPUs, potentially distributed across multiple machines) for training runs that can take hours, without leaving expensive hardware idle before or after the job.
- **Systematically searching hyperparameters** (learning rate, tree depth, batch size, etc.) rather than manually guessing, since the difference between a mediocre and a strong model is often hyperparameter tuning.
- **Repeating an entire training workflow reliably** as new data arrives — a pipeline that was run once manually is not the same as a pipeline that reruns automatically and reproducibly on a schedule or trigger.
- **Serving a trained model** to actual applications, which is a fundamentally different workload from training (training is throughput-oriented and batch; serving is latency-sensitive and often bursty).

## 3. Core Concepts

### 3.1 Custom Training Jobs

A **Custom Training Job** runs your own training code against Vertex AI-managed compute. Two container approaches exist:

- **Prebuilt containers**: Google-maintained Docker images with a specific ML framework and version already installed (TensorFlow, PyTorch, scikit-learn, XGBoost) — you supply only your training script, and Vertex AI supplies the environment. This is the lowest-friction path for standard frameworks.
- **Custom containers**: you build and push your own Docker image (to Artifact Registry, [Section 29](../Part4/Section-29-Part4-Artifact-Registry-Container-Registry.md)) with any dependencies, framework versions, or non-Python tooling your training code requires. This trades a small amount of extra setup for complete environment control — necessary when a team needs a specific library version or a non-standard training stack.

Training jobs specify a **worker pool spec** — machine type, accelerator type/count (GPU or TPU), and replica count — and can run as a single machine or as **distributed training** across multiple worker replicas for large models or datasets.

### 3.2 Hyperparameter Tuning

**Vertex AI Hyperparameter Tuning** runs many training trials in parallel or sequence, each with a different combination of hyperparameter values, and uses a search algorithm (Google's own Bayesian optimization by default) to converge on the combination that best optimizes a target metric (e.g., validation accuracy or minimized loss) — far more efficient than manual grid search or pure random search for expensive-to-train models. You define a **search space** (e.g., learning rate between 0.0001 and 0.1, log-scaled) and a **metric to optimize**, and Vertex AI manages launching, monitoring, and terminating underperforming trials early.

### 3.3 Vertex AI Pipelines

**Vertex AI Pipelines** orchestrates a multi-step ML workflow — e.g., "read data → validate schema → engineer features → train → evaluate → conditionally register the model if it beats the previous version" — as a directed acyclic graph (DAG) of containerized steps. It is built on the open-source **Kubeflow Pipelines (KFP)** SDK, meaning pipelines are defined as Python code using the KFP SDK (or Google's `google-cloud-pipeline-components` library, which provides pre-built steps for common Vertex AI operations), compiled to a portable pipeline definition, and executed serverlessly — you don't manage the underlying Kubernetes cluster running the steps.

Pipelines provide:

- **Reproducibility** — the same pipeline definition run against new data produces a comparable, versioned artifact trail.
- **Caching** — steps whose inputs haven't changed since a prior run can be skipped, speeding up iteration.
- **Lineage tracking** — Vertex AI ML Metadata automatically records which data, code, and parameters produced which model, tying back to the Dataset lineage introduced in [Section 65](./Section-65-Part10-Vertex-AI-Fundamentals.md).

### 3.4 Model Registry

The **Vertex AI Model Registry** is the central catalog for trained models. Every model — whether produced by AutoML ([Section 67](./Section-67-Part10-AutoML-Model-Garden.md)), a custom Training Job, or imported from elsewhere — gets registered with a **version**, associated evaluation metrics, and a deployment history. This allows teams to compare model versions side by side, roll back to a previous version if a new one underperforms, and control exactly which registered version is currently deployed to which endpoint.

### 3.5 Prediction: Online vs. Batch Endpoints

| Aspect         | Online (Real-Time) Endpoint                                           | Batch Prediction                                                               |
| -------------- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| Use case       | Low-latency, on-demand predictions (e.g., a live recommendation call) | Large-volume, offline scoring (e.g., scoring an entire customer table nightly) |
| Latency        | Milliseconds to low seconds per request                               | Not latency-sensitive; a whole job may run minutes to hours                    |
| Infrastructure | Persistently deployed compute (nodes stay up, can autoscale)          | Transient compute, provisioned for the job and torn down after                 |
| Input          | Individual requests (HTTP/gRPC)                                       | A file or BigQuery table of many rows at once                                  |
| Cost model     | Pay for deployed node uptime                                          | Pay only for the duration of the batch job                                     |
| Example        | A checkout page's fraud-risk score call                               | Monthly churn-risk scoring of the full customer base                           |

## 4. Comparison: Vertex AI Training/Pipelines/Endpoints vs. AWS SageMaker vs. Azure ML

| Capability               | Vertex AI                                                      | SageMaker                                                           | Azure ML                                    |
| ------------------------ | -------------------------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------- |
| Custom training          | Custom Training Jobs (prebuilt/custom containers)              | Training Jobs (built-in algos, framework containers, BYO container) | Azure ML Jobs (curated/custom environments) |
| Hyperparameter tuning    | Vertex AI Hyperparameter Tuning (Bayesian optimization)        | Automatic Model Tuning                                              | HyperDrive                                  |
| Pipeline orchestration   | Vertex AI Pipelines (Kubeflow Pipelines-based)                 | SageMaker Pipelines (native DAG)                                    | Azure ML Pipelines (native DAG)             |
| Model catalog/registry   | Vertex AI Model Registry                                       | SageMaker Model Registry                                            | Azure ML Model Registry                     |
| Real-time serving        | Vertex AI Online Endpoints                                     | SageMaker Real-Time Endpoints                                       | Azure ML Online Endpoints                   |
| Batch serving            | Vertex AI Batch Prediction                                     | SageMaker Batch Transform                                           | Azure ML Batch Endpoints                    |
| Underlying pipeline tech | Open-source Kubeflow Pipelines (portable, can run outside GCP) | Proprietary, AWS-native DAG                                         | Proprietary, Azure-native DAG               |

> ⚠️ **Interview-relevant nuance:** Vertex AI Pipelines' use of the open-source Kubeflow Pipelines SDK (versus SageMaker/Azure ML's proprietary pipeline DAGs) is a frequently cited differentiator — a pipeline definition written against the KFP SDK is portable to any KFP-compatible runner, not locked to Vertex AI specifically, which some organizations value for reducing platform lock-in risk.

## 5. Architecture Diagram: End-to-End Pipeline to Serving

```
 ┌────────────┐    ┌──────────────┐   ┌───────────────┐    ┌────────────┐   ┌─────────────────┐
 │ Dataset    │───►│  Preprocess  │──►│Custom Training│───►│  Evaluate  │──►│ Register Model  │
 │(Section 65)│    │  (KFP step)  │   │ Job (+ HP     │    │ (KFP step) │   │(if beats prior) │
 └────────────┘    └──────────────┘   │ Tuning)       │    └────────────┘   └────────┬────────┘
                                      └───────────────┘                              │
                                                                                     ▼
                                                                              ┌───────────────────┐
                                                                              │  Model Registry   │
                                                                              └─────────┬─────────┘
                                                                    ┌───────────────────┴──────────────────┐
                                                                    ▼                                      ▼
                                                          ┌───────────────────┐                  ┌────────────────────┐
                                                          │ Online Endpoint   │                  │Batch Prediction Job│
                                                          │(autoscaled nodes) │                  │(transient compute) │
                                                          └───────────────────┘                  └────────────────────┘
       Whole flow above = one Vertex AI Pipeline (KFP DAG), rerunnable on schedule or trigger,
       with caching skipping unchanged steps and ML Metadata recording full lineage.
```

## 6. Hands-On Example

**Beginner example — submit a custom training job with a prebuilt container:**

```bash
gcloud ai custom-jobs create \
  --region=us-central1 \
  --display-name=churn-model-training \
  --worker-pool-spec=machine-type=n1-standard-8,replica-count=1,\
container-image-uri=us-docker.pkg.dev/vertex-ai/training/tf-cpu.2-13:latest,\
local-package-path=./trainer,script=train.py
```

**Purpose:** Runs a custom TensorFlow training script on a single managed VM using a Google-maintained prebuilt container.

**Expected output:**

```
Using endpoint [https://us-central1-aiplatform.googleapis.com/]
CustomJob created. Resource name: projects/123456789012/locations/us-central1/customJobs/1234567890123456789
```

**Intermediate example — define and run a Vertex AI Pipeline with KFP:**

```python
from kfp import dsl
from google.cloud import aiplatform

@dsl.pipeline(name="churn-training-pipeline")
def pipeline(project: str, location: str):
    from google_cloud_pipeline_components.v1.custom_job import CustomTrainingJobOp
    train_task = CustomTrainingJobOp(
        project=project, location=location,
        display_name="churn-training-step",
        worker_pool_specs=[{
            "machine_spec": {"machine_type": "n1-standard-8"},
            "replica_count": 1,
            "container_spec": {"image_uri": "us-docker.pkg.dev/vertex-ai/training/tf-cpu.2-13:latest"},
        }],
    )

aiplatform.init(project="my-gcp-project", location="us-central1")
job = aiplatform.PipelineJob(
    display_name="churn-pipeline-run",
    template_path="churn_pipeline.json",
    parameter_values={"project": "my-gcp-project", "location": "us-central1"},
)
job.submit()
```

**Purpose:** Compiles and submits a reusable, versioned training pipeline rather than a one-off manual job.

**Expected output:**

```
PipelineJob created. Resource name: projects/123456789012/locations/us-central1/pipelineJobs/churn-pipeline-run-20260725...
View in the Cloud Console: https://console.cloud.google.com/vertex-ai/pipelines/runs/...
```

**Deploying a registered model to an online endpoint:**

```bash
gcloud ai endpoints deploy-model ENDPOINT_ID \
  --region=us-central1 \
  --model=MODEL_ID \
  --display-name=churn-model-v3-deployment \
  --machine-type=n1-standard-4 \
  --min-replica-count=2 \
  --max-replica-count=10
```

**Purpose:** Deploys a registered model version behind an autoscaling real-time endpoint (2–10 nodes).

**Expected output:**

```
Waiting for operation [...] to complete...done.
Deployed a model to the endpoint. To use this endpoint, run:
gcloud ai endpoints predict ENDPOINT_ID --region=us-central1 --json-request=INPUT.json
```

## 7. Production & Enterprise Usage

- Enterprises standardize training on **Vertex AI Pipelines** rather than ad hoc manual training-job submissions, so every production model has a reproducible, versioned, auditable path from data to deployed endpoint — essential for regulated industries needing to explain exactly how a deployed model was produced.
- **Online Endpoints** are configured with `min-replica-count` set above zero for latency-sensitive production traffic (avoiding cold-start delay), while `max-replica-count` bounds cost during traffic spikes — the same autoscaling trade-off pattern used for GKE ([Section 34](../Part4/Section-34-Part4-GKE-Operations-Scaling-Upgrades.md)) and Cloud Run ([Section 7](../Part1/Section-07-Part1-Cloud-Run.md)).
- **Batch Prediction** is the default choice for large periodic scoring workloads (e.g., nightly churn scoring of the full customer base) since it avoids paying for continuously deployed serving capacity that sits idle between batch runs.
- Model Registry version history is used as the rollback mechanism: if a newly deployed model version regresses on a key business metric, traffic is routed back to the prior registered version rather than requiring emergency retraining.

## 8. Common Misconceptions

- **Misconception:** "Hyperparameter tuning always improves a model." Tuning can only optimize within the chosen search space and algorithm/architecture — if the underlying model architecture or feature set is fundamentally weak, tuning will not compensate for that; it should be applied after core modeling choices are reasonably sound.
- **Misconception:** "Batch Prediction is just a slower Online Endpoint." They're architecturally distinct: Batch Prediction provisions transient compute for one large job and tears it down, while an Online Endpoint keeps compute persistently deployed and autoscaled for on-demand, low-latency traffic. Choosing incorrectly (e.g., using an always-on Online Endpoint for a monthly batch job) leads to substantial unnecessary cost.
- **Misconception:** "Vertex AI Pipelines locks you into GCP." Because pipelines are defined using the open-source KFP SDK, the pipeline definition itself is portable to other KFP-compatible runners; only the underlying execution environment (Vertex AI managed compute) is GCP-specific.

## 9. Interview Questions

**🎯 Beginner:** _What's the difference between a prebuilt and a custom training container in Vertex AI?_
**Model answer:** A prebuilt container is a Google-maintained Docker image with a standard ML framework (TensorFlow, PyTorch, scikit-learn, XGBoost) and its dependencies already installed — you only supply your training script. A custom container is one you build and push yourself, giving complete control over the environment, dependencies, and framework versions, at the cost of some extra setup. Prebuilt containers are the default choice for standard frameworks; custom containers are used when a team needs specific library versions or a non-standard training stack.

**🎯 Intermediate:** _When would you choose Batch Prediction over an Online Endpoint, and why?_
**Model answer:** Batch Prediction is the right choice when you need to score a large volume of data that isn't latency-sensitive — for example, scoring an entire customer table nightly for churn risk. It provisions transient compute for the duration of the job and tears it down afterward, so you only pay for the actual scoring time. An Online Endpoint, by contrast, keeps compute persistently deployed (and autoscaled) so it can respond to individual, low-latency requests on demand — the right choice for something like a live fraud-risk check during checkout. Using an Online Endpoint for a large periodic batch job would mean paying for continuously deployed capacity that's mostly idle between runs.

**🎯 Senior/Architect:** _Design a production ML retraining workflow for a fraud-detection model that must retrain weekly on fresh transaction data, must not deploy a new model version if it underperforms the currently deployed version on key metrics, and must maintain a full audit trail of what data/code produced each deployed version._
**Model answer:** I'd build this as a single Vertex AI Pipeline (KFP-based) triggered weekly via Cloud Scheduler and Eventarc ([Section 53](../Part7/Section-53-Part7-Eventarc-Workflows.md)): the pipeline reads the latest curated transaction data (from BigQuery, [Section 44](../Part6/Section-44-Part6-BigQuery-Deep-Dive.md)), runs a preprocessing/feature-engineering step, launches a Custom Training Job (optionally with Hyperparameter Tuning for periodic re-optimization), then an evaluation step that compares the new model's key metrics (precision/recall on a held-out fraud-labeled test set) against the metrics of the currently deployed model version pulled from Model Registry. I'd add a conditional pipeline step (KFP supports conditional DAG branches) that only registers and deploys the new model if it beats the deployed version by a defined margin — otherwise the pipeline exits without touching production, and the current version keeps serving. Every run is automatically tracked in Vertex AI ML Metadata, giving a full audit trail linking each deployed model version back to the exact data snapshot, code version, and hyperparameters that produced it — satisfying the audit requirement without any extra custom tooling on top of what Pipelines and Model Registry already provide.

## 10. Key Takeaways

- 🔑 Custom Training Jobs support prebuilt (Google-maintained) or custom containers, with distributed training available for large models/datasets.
- 🔑 Hyperparameter Tuning uses Bayesian optimization by default to efficiently search a defined parameter space rather than manual guessing.
- 🔑 Vertex AI Pipelines orchestrates multi-step ML workflows as a Kubeflow Pipelines DAG — reproducible, cacheable, and with automatic lineage tracking via ML Metadata.
- 🔑 Online Endpoints serve low-latency, on-demand predictions with persistently deployed, autoscaled compute; Batch Prediction serves large offline scoring jobs with transient, job-oriented compute — choosing the wrong one is a common and costly mistake.
- 🔑 Model Registry versions every trained model and is the mechanism for rollback if a newly deployed version underperforms.

## 11. Related Concepts

Vertex AI Fundamentals and Feature Store ([Section 65](./Section-65-Part10-Vertex-AI-Fundamentals.md)) as the upstream data foundation, AutoML & Model Garden ([Section 67](./Section-67-Part10-AutoML-Model-Garden.md)) as an alternative no-code/foundation-model training path, MLOps on GCP ([Section 69](./Section-69-Part10-MLOps-on-GCP.md)) for ongoing monitoring of deployed endpoints, Cloud Build/CI-CD ([Section 50](../Part7/Section-50-Part7-Cloud-Build-CICD.md)) and Eventarc ([Section 53](../Part7/Section-53-Part7-Eventarc-Workflows.md)) for triggering pipeline runs, and Artifact Registry ([Section 29](../Part4/Section-29-Part4-Artifact-Registry-Container-Registry.md)) for storing custom training containers.
