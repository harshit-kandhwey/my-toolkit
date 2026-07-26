# Section 69 (Part 10): MLOps on GCP

## 1. Definition

**Plain language:** Getting a model deployed (Section 66) is not the end of the story — the real world keeps changing after deployment, and a model trained on last year's data can quietly get worse without anyone noticing until it's already hurt the business. MLOps is the discipline (and the Vertex AI tooling) for watching deployed models over time, tracking what was tried during experimentation, and automating the retrain-and-redeploy cycle so it doesn't rely on someone remembering to do it manually.

**Precise:** MLOps on Vertex AI combines **Model Monitoring** (automated detection of training-serving skew and prediction drift on deployed endpoints), **Vertex AI Experiments** (structured tracking and comparison of training runs, parameters, and metrics), and **CI/CD for ML pipelines** (automated build/test/deploy of Vertex AI Pipelines, Section 66, triggered by code or data changes) to operate machine learning systems with the same reliability discipline applied to traditional software via DevOps (Section 50).

## 2. Why It Exists / Problem It Solves

- **Models degrade silently.** Unlike a crashing application, a model that has become less accurate typically doesn't throw an error — it just quietly makes worse predictions, which can go undetected for weeks without active monitoring.
- **The real world drifts from training data.** Customer behavior, market conditions, and upstream data pipelines all change after a model is trained; a model's assumptions about the world become stale even if nothing about the model itself changed.
- **Experimentation without tracking is unreproducible.** A data scientist trying 20 combinations of features and hyperparameters, without a system recording what was tried and what the results were, cannot reliably reproduce their best result or explain to a reviewer why a particular configuration was chosen.
- **Manual retraining doesn't scale.** Re-running a full training pipeline by hand every time monitoring detects an issue, or on a fixed schedule, doesn't scale past a handful of models — CI/CD automation is required once an organization operates more than a few production ML systems.

## 3. Core Concepts

### 3.1 Vertex AI Model Monitoring

**Model Monitoring** continuously compares the statistical distribution of live prediction request data (and, where ground truth is available, prediction accuracy) against a baseline, and alerts when it detects meaningful divergence. Two primary types of divergence it detects:

- **Training-serving skew**: the distribution of features in live prediction requests differs meaningfully from the distribution of features in the original training data. This can indicate a bug in the serving-time feature pipeline (a feature is being computed differently at serving time than it was at training time) or a genuine shift in the population being served.
- **Prediction drift**: the distribution of live prediction requests changes over time relative to an earlier window of live traffic (rather than compared to the original training data) — indicating the real-world input population itself is evolving, independent of any training-serving mismatch.

Model Monitoring is configured with a **monitoring job** on a deployed endpoint, specifying which features to watch, an alerting threshold, and a notification channel; when skew/drift exceeds the threshold, an alert triggers — commonly wired to kick off a retraining pipeline automatically.

### 3.2 Vertex AI Experiments

**Vertex AI Experiments** tracks and organizes training runs so they can be compared systematically:

- Each **run** records the parameters used (learning rate, feature set, algorithm choice), the resulting metrics (accuracy, loss, AUC), and artifacts produced (the trained model, plots).
- Runs are grouped into an **experiment**, letting a team view all attempted configurations for a given modeling problem side by side in a comparison table or chart.
- Experiments integrate with **Vertex AI ML Metadata** (introduced in Section 66) so a run's full lineage — which data, code version, and parameters produced which model and metrics — is automatically captured rather than manually logged.

This turns "I think the third model I trained last week was the best one, but I'm not sure exactly what I changed" into a queryable, comparable record.

### 3.3 CI/CD for ML Pipelines

Applying CI/CD (Section 50) discipline to ML means the **Vertex AI Pipeline definition itself** (Section 66) — not just the application code around it — goes through source control, automated testing, and automated deployment:

- **Continuous Integration**: a change to pipeline code (e.g., a new preprocessing step, an updated training script) triggers automated tests — unit tests on preprocessing logic, a small-scale pipeline dry run — before the change is merged.
- **Continuous Delivery/Deployment**: a merged pipeline definition is automatically compiled and either deployed to a pipeline template registry ready for triggered runs, or directly scheduled/triggered depending on the organization's release process.
- **Triggering**: production pipeline runs are commonly triggered by Cloud Build (Section 50) on a code merge, Cloud Scheduler on a fixed cadence (e.g., weekly retrain), or Eventarc (Section 53) in response to an event such as a Model Monitoring drift alert or new data landing in BigQuery/Cloud Storage.

## 4. Comparison: MLOps on Vertex AI vs. AWS SageMaker vs. Azure ML

| Capability                          | Vertex AI                                      | SageMaker                                            | Azure ML                                                    |
| ----------------------------------- | ---------------------------------------------- | ---------------------------------------------------- | ----------------------------------------------------------- |
| Drift/skew monitoring               | Vertex AI Model Monitoring                     | SageMaker Model Monitor                              | Azure ML Data Drift / Model Monitoring                      |
| Experiment tracking                 | Vertex AI Experiments                          | SageMaker Experiments                                | Azure ML Jobs/Experiments tracking                          |
| Pipeline CI/CD trigger tooling      | Cloud Build + Eventarc + Cloud Scheduler       | CodePipeline / SageMaker Pipelines triggers          | Azure DevOps / GitHub Actions + Azure ML Pipelines triggers |
| Automatic lineage tracking          | Vertex AI ML Metadata (built-in)               | SageMaker Lineage Tracking                           | Azure ML asset lineage (built-in)                           |
| Underlying pipeline orchestration   | Kubeflow Pipelines (open source)               | SageMaker Pipelines (proprietary)                    | Azure ML Pipelines (proprietary)                            |
| Retrain-on-drift automation pattern | Monitoring alert → Eventarc → Pipeline trigger | Model Monitor alert → EventBridge → Pipeline trigger | Data drift alert → Azure Monitor → Pipeline trigger         |

> ⚠️ **Interview-relevant nuance:** All three clouds converge on the same conceptual retrain-on-drift loop (monitor → alert → event → automated pipeline trigger), but the specific glue services differ — GCP wires this through Eventarc, AWS through EventBridge, Azure through Azure Monitor action groups. Understanding the pattern matters more than memorizing exact service names, but naming the correct glue service for the cloud in question is a common interview check.

## 5. Architecture Diagram: Monitor-Alert-Retrain Loop

```
 ┌────────────────────┐
 │  Deployed Endpoint │──── live prediction traffic
 │  (Section 66)      │
 └──────────┬─────────┘
            │ sampled requests/responses
            ▼
 ┌────────────────────┐
 │  Model Monitoring  │──── compares live distribution vs.
 │  Job               │     training baseline / prior window
 └──────────┬─────────┘
            │ threshold exceeded (skew or drift detected)
            ▼
 ┌────────────────────┐
 │  Alert (Cloud      │
 │ Monitoring / email/│
 │ Pub/Sub)           │
 └──────────┬─────────┘
            │ Eventarc trigger
            ▼
 ┌────────────────────┐
 │  Vertex AI Pipeline│──── retrains, evaluates against
 │  (CI/CD-deployed,  │     current deployed model
 │   Section 66)      │
 └──────────┬─────────┘
            │ only if new model beats current
            ▼
 ┌────────────────────┐
 │  Model Registry ►  │
 │redeploy to Endpoint│
 └────────────────────┘
       Every run recorded in Vertex AI Experiments + ML Metadata for audit/comparison.
```

## 6. Hands-On Example

**Beginner example — enable Model Monitoring on a deployed endpoint:**

```bash
gcloud ai model-monitoring-jobs create \
  --region=us-central1 \
  --display-name=churn-endpoint-monitoring \
  --endpoint=ENDPOINT_ID \
  --feature-thresholds=tenure_months=0.3,monthly_charges=0.3 \
  --emails=ml-team@example.com
```

**Purpose:** Configures ongoing skew/drift monitoring on two key features of a deployed churn-prediction endpoint, alerting the ML team by email if divergence exceeds the configured threshold.

**Expected output:**

```
Using endpoint [https://us-central1-aiplatform.googleapis.com/]
ModelDeploymentMonitoringJob created: projects/123456789012/locations/us-central1/modelDeploymentMonitoringJobs/445566
```

**Intermediate example — log a training run to Vertex AI Experiments:**

```python
from google.cloud import aiplatform

aiplatform.init(project="my-gcp-project", location="us-central1", experiment="churn-model-experiments")

with aiplatform.start_run("run-lr-001") as run:
    run.log_params({"learning_rate": 0.01, "max_depth": 6})
    # ... training happens here ...
    run.log_metrics({"accuracy": 0.912, "auc": 0.947})
```

**Purpose:** Records the hyperparameters and resulting metrics of one training run under a named experiment, so it can be compared against other runs later.

**Expected output:**

```
Associating projects/123456789012/locations/us-central1/metadataStores/default/contexts/churn-model-experiments-run-lr-001
Run run-lr-001 logged successfully.
```

**CI trigger example — Cloud Build step that runs a pipeline dry-run test on merge:**

```yaml
steps:
  - name: "python:3.11"
    entrypoint: bash
    args:
      - "-c"
      - |
        pip install kfp google-cloud-aiplatform
        python compile_pipeline.py
        python -m pytest tests/test_preprocessing.py
```

**Purpose:** Runs preprocessing unit tests and confirms the pipeline still compiles cleanly before allowing a merged pipeline-code change to be deployed.

**Expected output:**

```
Step #0: ============ test session starts ============
Step #0: tests/test_preprocessing.py::test_feature_scaling PASSED
Step #0: Pipeline compiled successfully: churn_pipeline.json
```

## 7. Production & Enterprise Usage

- Production endpoints for business-critical models (fraud detection, credit risk, churn) run **Model Monitoring continuously**, with alerts wired via Eventarc directly into an automated retraining pipeline rather than relying on a human to notice a dashboard.
- **Vertex AI Experiments** is used as the system of record for model governance — when a regulator or internal audit asks "why was this specific model version deployed," the experiment log provides the parameters, data version, and comparative metrics that justified the choice.
- Enterprises apply the same code-review, testing, and approval gates to **pipeline definition changes** as they do to application code changes, since a bug in a preprocessing step can silently corrupt every subsequent model trained by that pipeline.
- The "only deploy if the new model beats the current one" conditional pattern (introduced in Section 66) is standard practice specifically to prevent a retraining pipeline — triggered automatically off a drift alert — from replacing a good model with a worse one.

## 8. Common Misconceptions

- **Misconception:** "Model Monitoring guarantees you'll be alerted before a model causes business harm." Monitoring detects statistical skew/drift in feature distributions or prediction patterns, which correlates with degraded model quality but isn't a direct measurement of business impact — a model can still degrade in ways monitoring thresholds don't catch, or catch too late relative to real-world consequences. Monitoring reduces risk; it does not eliminate it.
- **Misconception:** "Training-serving skew and prediction drift are the same thing." Skew compares live traffic against the original training data distribution (often indicating a serving-time bug); drift compares live traffic against an earlier window of live traffic (indicating the real world is genuinely changing). They point to different root causes and different fixes.
- **Misconception:** "MLOps CI/CD is just regular software CI/CD applied to ML code." Regular CI/CD tests and deploys code; ML CI/CD must additionally account for data versioning, model evaluation gates (don't deploy a worse model), and experiment lineage tracking — dimensions that don't exist in typical application CI/CD pipelines.

## 9. Interview Questions

**🎯 Beginner:** _What is the difference between training-serving skew and prediction drift in Vertex AI Model Monitoring?_
**Model answer:** Training-serving skew compares the distribution of features in live prediction requests against the distribution in the original training data — a large difference often indicates a bug, such as a feature being computed differently at serving time than it was during training. Prediction drift compares live prediction requests against an earlier window of live traffic, independent of the training data — a large difference here indicates the real-world population being served is genuinely changing over time, rather than pointing to a pipeline bug.

**🎯 Intermediate:** _Why is Vertex AI Experiments important even for a small team with only one or two models in production?_
**Model answer:** Even with few production models, teams typically try many configurations during development — different feature sets, hyperparameters, algorithms — before settling on what gets deployed. Without systematic tracking, it's easy to lose track of exactly which configuration produced the best result, making it hard to reproduce, hard to justify the choice during review, and hard to know what's already been tried when picking up the work later. Vertex AI Experiments records parameters, metrics, and artifacts for every run automatically, and ties back to full data/code lineage via ML Metadata, turning ad hoc trial-and-error into a reproducible, comparable record — valuable regardless of how many models are ultimately deployed.

**🎯 Senior/Architect:** _Design an MLOps setup for a credit-risk scoring model where regulators require a full audit trail of every deployed model version, and a compliance requirement mandates the model never auto-deploys without a human review step, even if it passes automated evaluation._
**Model answer:** I'd build the pipeline as a CI/CD-deployed Vertex AI Pipeline (Section 66) that trains and evaluates the model automatically, logging every run — parameters, data snapshot reference, evaluation metrics — to Vertex AI Experiments, which together with ML Metadata gives the automatic, queryable audit trail regulators require, tying each candidate model back to the exact data and code that produced it. I'd enable Model Monitoring on the production endpoint for both training-serving skew and prediction drift, since a credit-risk model quietly degrading as economic conditions shift is exactly the kind of silent failure regulators care about, with alerts routed to the ML team via Eventarc. For the human-review requirement, I would deliberately break the fully automated "auto-deploy if it beats the current model" pattern from Section 66 at the final step: the pipeline would run through training and evaluation automatically, register the candidate model with its comparison metrics against the current production model in Model Registry, and then stop — requiring an explicit manual approval action (e.g., a designated reviewer promoting the model via Model Registry's deployment controls) before the new version is deployed to the production endpoint. This keeps every step traceable through Experiments and ML Metadata for the audit requirement while ensuring no model reaches production credit decisions without a human explicitly signing off, satisfying both the audit and human-oversight requirements without weakening the automated evaluation gate itself.

## 10. Key Takeaways

- 🔑 Model Monitoring detects training-serving skew (vs. training data) and prediction drift (vs. earlier live traffic) separately — they indicate different root causes.
- 🔑 Vertex AI Experiments turns ad hoc trial-and-error into a reproducible, comparable record of parameters/metrics/artifacts, integrated with automatic ML Metadata lineage tracking.
- 🔑 CI/CD for ML pipelines applies the same testing/review discipline to pipeline definitions as to application code, plus ML-specific gates like "don't deploy a worse model."
- 🔑 The standard production pattern wires Model Monitoring alerts through Eventarc directly into an automated retraining pipeline, closing the monitor-alert-retrain loop.
- 🔑 Monitoring reduces but does not eliminate the risk of undetected model degradation — it is a risk-reduction tool, not a guarantee.

## 11. Related Concepts

Vertex AI Deep Dive Training/Pipelines/Endpoints (Section 66) for the pipeline and endpoint infrastructure being monitored, AutoML & Model Garden (Section 67) since AutoML/Model Garden-sourced models flow through the same monitoring and experiment tracking, DevOps/Cloud Build/CI-CD (Section 50) and Eventarc (Section 53) for the automation glue, and AI/ML Security & Responsible AI (Section 70) for governance considerations layered on top of monitoring.
