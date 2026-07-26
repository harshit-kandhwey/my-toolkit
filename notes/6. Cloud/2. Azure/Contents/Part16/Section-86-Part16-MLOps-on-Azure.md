# Section 86 — MLOps on Azure

## 1. Definition

**Plain language:** Getting a model trained and deployed once (Sections 84-85) is only the beginning. Real-world data shifts over time, models quietly get worse without anyone noticing unless someone's watching for it, and every new model version needs to go through the same rigor as any other production software change — reviewed, tested, and deployable without a human manually running commands from their laptop. MLOps is the set of practices and Azure tooling that keeps a model healthy and its deployment process disciplined for as long as it stays in production.

**Precise definition:** **MLOps** (Machine Learning Operations) is the application of DevOps discipline (Part 9) — automated CI/CD, monitoring, versioning, rollback — to the ML lifecycle specifically, addressing ML-specific operational concerns like **data drift** and **concept drift** monitoring, automated model retraining/redeployment pipelines, and responsible-AI evaluation gates that don't have a direct equivalent in general application DevOps.

## 2. Why It Exists / Problem It Solves

Section 85 covered how to submit a training job and deploy a model to an endpoint — but doing that manually, once, is exactly the anti-pattern Part 9 addressed for general application deployments: a manually-run process is unrepeatable, undocumented, and dependent on a specific person remembering the right sequence of commands. MLOps exists because ML deployments have this same problem plus additional ML-specific ones that general CI/CD doesn't address on its own: a model's accuracy can silently degrade over time as the real-world data it scores diverges from its training data (drift), without any code change ever occurring — something a traditional application deployment pipeline, built to catch code regressions, isn't designed to detect. MLOps combines the CI/CD discipline from Part 9 with ML-specific monitoring (drift detection) and governance (Responsible AI evaluation) to keep models both operationally reliable and behaviorally trustworthy for as long as they remain deployed.

## 3. Model Monitoring — Data Drift and Concept Drift

### 3.1 Data Drift

**Definition:** **Data drift** occurs when the statistical distribution of the input data a deployed model receives in production diverges meaningfully from the distribution of the data it was trained on — for example, a fraud-detection model trained on pre-pandemic transaction patterns encountering a materially different distribution of transaction types and volumes afterward.

**How it works conceptually:** Azure ML's model monitoring capability compares a rolling window of production inference input data against a baseline (typically the training dataset), computing statistical distance metrics for each feature, and flags features whose distribution has drifted beyond a configured threshold — giving an early warning that the model's assumptions about its input data may no longer hold, even before accuracy visibly degrades.

### 3.2 Concept Drift

**Definition:** **Concept drift** occurs when the actual relationship between input features and the target outcome changes over time, even if the input feature distribution itself stays stable — for example, customer behaviors that used to reliably predict churn no longer being predictive after a change in the market or product.

**Why the distinction matters:** data drift is detectable purely by observing input data statistics, without needing ground-truth labels; concept drift generally requires comparing model predictions against actual outcomes (labels), which often only become available after some delay (e.g., knowing whether a customer actually churned takes weeks or months to confirm) — this means concept drift monitoring is inherently laggier and depends on a pipeline to eventually collect ground truth, whereas data drift can be monitored in near real time purely from incoming request data.

⚠️ Azure ML's model monitoring feature set (metrics available, configuration surface, integration with the Studio UI) has evolved and been renamed across product iterations — verify current model monitoring capabilities and setup steps against official documentation.

## 4. CI/CD for ML — Azure DevOps and GitHub Actions

### 4.1 Why ML Needs Its Own CI/CD Shape

General application CI/CD (Part 9) builds and tests code, then deploys an artifact. ML CI/CD needs the same discipline applied to a pipeline that also involves data and a trained model as first-class artifacts — a typical ML CI/CD pipeline triggers on a code change (a new training script, feature engineering change, or a scheduled retraining cadence), executes the AML Pipeline (Section 85.5) to retrain, evaluates the new model against held-out data and Responsible AI checks (Section 86.5), and only proceeds to register and deploy the new model if it passes both accuracy and fairness/safety gates — a build that "compiles" (a model that trains successfully) is not the same bar as a build that's fit to deploy.

### 4.2 Azure DevOps Pipelines for ML

Azure DevOps Pipelines (Part 9) can orchestrate the ML CI/CD flow using the `azureml` extension or direct `az ml` CLI calls within pipeline YAML — a typical pipeline stage submits an AML training/pipeline job, waits for completion, evaluates the resulting metrics against a threshold gate, and conditionally proceeds to a deployment stage that creates a new Managed Online Endpoint deployment with an initial low traffic percentage, following the canary pattern from Section 85.7.2.

### 4.3 GitHub Actions for ML

The equivalent pattern is available via GitHub Actions using the `azure/ml-actions` or general Azure CLI-based steps — functionally interchangeable with the Azure DevOps approach for teams whose broader repository and CI/CD investment already lives in GitHub rather than Azure DevOps, consistent with the general Azure DevOps vs. GitHub Actions decision already covered in Part 9.

## 5. Responsible AI Dashboard

**Definition:** The **Responsible AI dashboard** is an integrated set of tools within Azure ML for evaluating a trained model's fairness, explainability, error distribution, and causal behavior before it's deployed — surfacing whether a model's errors or predictions are disproportionately distributed across sensitive subgroups (e.g., a loan-approval model performing meaningfully worse for one demographic group than another), which features most influence individual predictions, and counterfactual "what would need to change for this prediction to flip" analysis.

**Why this matters operationally:** a model can have excellent aggregate accuracy while still being unacceptably unfair to a subgroup within the aggregate — a metric-only CI/CD gate (Section 86.4.1) checking overall accuracy alone would pass such a model, so the Responsible AI dashboard's fairness assessment is meant to be a distinct, additional gate in the deployment pipeline, not a replacement for accuracy evaluation. This ties directly into the broader Responsible AI governance framework covered in Section 89.

## 6. Model Versioning and Rollback

Section 85.6 introduced the Model Registry's versioning; the MLOps discipline formalizes how that versioning is actually used operationally: every model promoted through the CI/CD pipeline gets a new registry version (never overwriting a prior version in place), every production deployment references a specific version explicitly, and rollback is executed by redeploying (or shifting endpoint traffic back to) a deployment referencing the prior known-good version — the same "never mutate a released artifact, roll forward or back by referencing a different immutable version" discipline used for container image tags (Part 7) and IaC state (Part 9), applied to models specifically.

## 7. Architecture Diagram

```
Code/config change (training script, retrain schedule trigger)
        │
        ▼
Azure DevOps Pipeline / GitHub Actions (Part 9)
        │
        ├──► Trigger AML Pipeline (Section 85.5): retrain job
        │
        ├──► Evaluate: accuracy/metrics gate
        │           │
        │           ▼ (pass)
        ├──► Evaluate: Responsible AI dashboard gate (fairness, error analysis)
        │           │
        │           ▼ (pass)
        ├──► Register new Model version in Model Registry
        │
        └──► Deploy: new canary deployment behind Managed Online Endpoint
                     │
                     ▼
              Model Monitoring (data drift / concept drift)
                     │
                     ▼ (drift detected beyond threshold)
              Alert ──► triggers retraining pipeline again
```

## 8. Configuration & Hands-On Example

**A simplified Azure DevOps pipeline YAML stage gating ML deployment on both accuracy and a monitoring check:**

```yaml
stages:
  - stage: TrainAndEvaluate
    jobs:
      - job: RunTrainingPipeline
        steps:
          - script: |
              az ml job create --file train-pipeline.yml \
                --resource-group rg-ml-prod --workspace-name mlw-project \
                --stream
          - script: |
              python evaluate_metrics.py --threshold-accuracy 0.85
            displayName: "Gate on accuracy threshold"

  - stage: DeployCanary
    dependsOn: TrainAndEvaluate
    condition: succeeded()
    jobs:
      - job: DeployNewVersion
        steps:
          - script: |
              az ml online-deployment create --name green \
                --endpoint ep-fraud-scoring \
                --model fraud-model:$(Build.BuildId) \
                --instance-type Standard_DS3_v2 --instance-count 2 \
                --traffic-percentage 10 \
                --resource-group rg-ml-prod --workspace-name mlw-project
```

- **Purpose:** Demonstrates the CI/CD shape described in Section 86.4.1 — a training stage that gates on an accuracy threshold before a deployment stage proceeds, deploying the new model as a low-traffic canary rather than immediately replacing all live traffic.
- **Important arguments explained individually:**
  - `--stream` on the job create call — streams job logs directly into the pipeline's console output, letting the CI/CD run fail fast and visibly if the training job itself errors, rather than silently succeeding at the "job submitted" step while training actually fails downstream.
  - `condition: succeeded()` on the deploy stage — ensures deployment only proceeds if the prior stage (including the accuracy gate script) exited successfully, implementing the "accuracy bar before deployment" gate described in Section 86.4.1.
  - `--traffic-percentage 10` — deploys the new model version as a canary receiving a minority of live traffic, consistent with the gradual rollout pattern from Section 85.7.2, rather than an all-or-nothing cutover.
- **Common error:** Omitting an explicit Responsible AI fairness gate and relying solely on an aggregate accuracy threshold can let a model pass CI/CD despite significant fairness disparities across subgroups (Section 86.5) — production ML CI/CD pipelines for anything customer-impacting should include an explicit fairness/Responsible AI evaluation step, not just an accuracy check.

## 9. Production & Enterprise Usage

Mature enterprise MLOps setups run scheduled or drift-triggered retraining (a monitoring alert from Section 86.3 automatically kicking off the CI/CD pipeline from Section 86.4, rather than requiring a human to notice degraded metrics and manually retrain), with every promoted model required to pass both an accuracy gate and a Responsible AI fairness gate before deployment, and canary rollouts with automated rollback if post-deployment monitoring shows regressions. Governance often layers on top of this technical pipeline: a model registry entry might require a human sign-off (an approval gate in Azure DevOps/GitHub Actions, Part 9) before promotion to production for higher-stakes models (credit decisions, medical predictions), even if all automated gates pass, reflecting that some decisions warrant human review regardless of how well the automated evaluation performed.

## 10. Security Considerations

- CI/CD pipelines that submit training jobs and deploy models need their own scoped identity (a service principal or, preferably, a Managed Identity, Section 9) with least-privilege RBAC on the AML workspace — broad, standing credentials embedded in pipeline configuration recreate the exact credential-sprawl risk Part 9's CI/CD security guidance already warns against for general application deployments.
- Model monitoring pipelines that compare production inference data against training data baselines are themselves handling potentially sensitive data (the actual inputs being scored) — access to monitoring dashboards and underlying logged data should be governed with the same RBAC discipline as the training data itself.
- Responsible AI dashboard outputs (fairness/error analysis reports) can reveal sensitive patterns about how a model treats different subgroups — these reports should be access-controlled and handled with appropriate confidentiality, not casually shared outside the team accountable for the model's governance.

## 11. Performance Considerations

Retraining cadence is a trade-off: retraining on every detected drift signal keeps a model maximally current but consumes proportionally more compute and CI/CD pipeline runs, while retraining only on a fixed schedule (weekly, monthly) is cheaper but risks running a materially drifted model in production for longer between retraining cycles — most mature setups use drift monitoring to trigger an alert that a human or an automated policy then decides whether to act on immediately or defer to the next scheduled retraining window, balancing responsiveness against cost.

## 12. Monitoring

Azure ML model monitoring (Section 86.3) surfaces data/concept drift metrics through the AML Studio UI and can be wired to Azure Monitor alerts (Section 53) so a drift threshold breach automatically notifies the responsible team or triggers a retraining pipeline run — combined with the standard endpoint-level monitoring (request volume, latency, error rate) from Section 85.14, this gives both an operational health view (is the endpoint serving correctly) and a model-quality view (is the model's behavior still trustworthy) side by side.

## 13. Troubleshooting

| Symptom                                                                                                    | Likely Cause                                                                                                                                                               | Fix                                                                                                                                                                |
| ---------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Model monitoring reports data drift, but the model's actual accuracy on recent labeled data hasn't changed | Drifted features may not be the ones the model heavily relies on for its predictions                                                                                       | Cross-reference drifted features against feature importance from the Responsible AI dashboard (Section 86.5) before triggering an unnecessary retrain              |
| CI/CD pipeline deploys a new model version that performs worse than the prior version in production        | Accuracy gate evaluated against a stale or unrepresentative holdout dataset that doesn't reflect current production data distribution                                      | Refresh the evaluation/holdout dataset regularly; consider gating on a canary's live production metrics, not just offline evaluation, before ramping traffic       |
| Responsible AI dashboard generation step fails or times out in the CI/CD pipeline                          | Dashboard computation (especially fairness/causal analysis) is resource-intensive and may need a larger compute allocation or reduced sample size for CI/CD-time execution | Run the full Responsible AI dashboard analysis on a scheduled/manual basis with adequate compute, and a lighter-weight subset of checks as an automated CI/CD gate |

## 14. Interview Questions — Section 86

### 🎯 Intermediate

**Q: What's the difference between data drift and concept drift, and why does concept drift detection typically lag behind data drift detection?**

_Model answer:_ Data drift is a change in the statistical distribution of the input data a model receives, detectable purely from the input data itself without needing to know the correct outcome. Concept drift is a change in the actual relationship between inputs and the correct outcome — the model's learned patterns no longer hold even if input distributions look the same. Concept drift detection lags because confirming it requires comparing predictions against actual ground-truth outcomes, and those outcomes (e.g., whether a customer actually churned, whether a transaction was actually fraudulent) often aren't known until well after the prediction was made, whereas data drift can be assessed immediately from incoming request data alone.

_What the interviewer is probing:_ whether the candidate understands these as genuinely distinct phenomena requiring different monitoring approaches, rather than treating "model degradation" as a single undifferentiated concept.

### 🎯 Senior/Architect

**Q: Design an MLOps pipeline for a customer churn prediction model that retrains periodically and must pass both accuracy and fairness checks before any new version reaches production traffic.**

_Model answer:_ I'd set up an Azure DevOps (or GitHub Actions) pipeline triggered both on a fixed schedule (say, monthly) and on a data drift alert from Azure ML's model monitoring (Section 86.3), so retraining happens proactively even between scheduled runs if the input data has drifted meaningfully. The pipeline would first run the AML training Pipeline (Section 85.5) against the current data, then gate on an accuracy/AUC threshold evaluated against a held-out, periodically-refreshed test set — failing the pipeline outright if the new model underperforms the currently-deployed version. Only after passing that gate would the pipeline generate a Responsible AI dashboard (Section 86.5) for the candidate model, checking for disparate error rates across customer segments (e.g., by region or demographic where legally and ethically appropriate to assess), with a required review step before promotion for this customer-facing, decision-influencing model — potentially a manual approval gate in the pipeline given churn predictions likely feed into retention offers that carry real business and customer-fairness implications. If both gates pass, the pipeline would register the new model version and deploy it as a low-traffic canary behind the existing Managed Online Endpoint, ramping traffic gradually while monitoring live error rates and business metrics, with an explicit rollback path (shifting traffic back to the prior version) if anything regresses post-deployment. I'd also make sure the Managed Identity used by this pipeline has least-privilege RBAC scoped to only what it needs on the AML workspace, consistent with the credential-hygiene practices established in Part 9.

_What the interviewer is probing:_ whether the candidate can design a complete, realistic MLOps pipeline that treats fairness/Responsible AI evaluation as a first-class deployment gate alongside accuracy — not an afterthought — while also applying sound general CI/CD and security practices (canary rollout, least-privilege pipeline identity) rather than treating ML deployment as fundamentally different from disciplined software deployment generally.

## 15. Common Misconceptions

- **"If a model's code hasn't changed, its production behavior won't change either."** False — data drift and concept drift can silently degrade a deployed model's real-world accuracy with zero code changes, which is precisely why dedicated model monitoring, not just code-change-triggered CI, is necessary.
- **"Passing an aggregate accuracy threshold is sufficient evidence a model is safe to deploy."** False — a model can have strong aggregate accuracy while performing meaningfully worse for specific subgroups; the Responsible AI dashboard's fairness analysis is meant to be a distinct, additional deployment gate.
- **"Rolling back a bad model deployment requires retraining a new, corrected model."** False — rollback in a properly versioned MLOps setup means redirecting traffic back to the prior, already-registered model version, which requires no retraining at all.

## 16. Key Takeaways

- 🔑 MLOps applies Part 9's DevOps discipline to the ML lifecycle, plus ML-specific concerns — data/concept drift monitoring and Responsible AI evaluation gates — that general application CI/CD doesn't natively address.
- 🔑 Data drift is detectable from input data alone in near real time; concept drift requires ground-truth labels and is inherently laggier to detect.
- 🔑 CI/CD for ML (via Azure DevOps or GitHub Actions) should gate model promotion on both an accuracy/metrics threshold and a Responsible AI fairness assessment, not accuracy alone.
- 🔑 The Responsible AI dashboard evaluates fairness, explainability, and error distribution across subgroups — a distinct concern from aggregate model accuracy.
- 🔑 Disciplined model versioning in the Model Registry, paired with canary deployments (Section 85.7.2), makes rollback a traffic-routing decision rather than a retraining exercise.

## 17. Related Concepts (Next Up)

Sections 84-86 have covered the full "classical" ML lifecycle on Azure — workspaces, training, deployment, and operations. Section 87 pivots the Part toward generative AI, starting with **Azure OpenAI Service**: how it differs from calling the public OpenAI API directly, its model deployment and quota model, and the core chat completions and embeddings APIs that underpin the generative AI patterns covered for the rest of this Part.
