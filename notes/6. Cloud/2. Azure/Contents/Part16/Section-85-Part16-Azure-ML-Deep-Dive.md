# Section 85 — Azure ML Deep Dive

## 85.1 Definition

**Plain language:** Section 84 introduced the AML workspace, its compute, and its data references — the containers everything sits inside. This section covers what actually happens inside those containers: submitting a piece of training code as a tracked job, automatically searching for the best hyperparameters, chaining multiple steps into a repeatable pipeline, keeping a versioned catalog of trained models, and finally exposing a trained model as something an application can call.

**Precise definition:** This section covers the **Azure ML training and inference lifecycle in depth** — **Jobs** (the unit of tracked, executed work, encompassing training runs and experiments), **Sweep Jobs** (automated hyperparameter tuning), **AML Pipelines** (multi-step, reusable, chained workflows), the **Model Registry** (a versioned catalog of trained models within the workspace), and **inference endpoints** — both **Managed Online Endpoints** (real-time, low-latency serving) and **Batch Endpoints** (asynchronous, large-volume scoring).

## 85.2 Why It Exists / Problem It Solves

Section 84 established the workspace, compute, and data-referencing model, but a workspace with compute attached and data registered doesn't yet produce a usable model — someone still has to run training code, systematically search for good hyperparameters instead of guessing, keep track of what was tried and what won, and eventually expose the winning model as something other systems can call. Each of these has a naive, unmanaged version teams commonly reach for first — a data scientist manually re-running a script with slightly different arguments, saving models with ad-hoc filenames like `model_v2_final_ACTUAL.pkl`, and eventually copy-pasting model-loading code into a Flask app running on a VM someone remembers to keep patched. Azure ML's Jobs, Sweep Jobs, Pipelines, Model Registry, and managed endpoints exist specifically to replace that ad-hoc pattern with tracked, reproducible, and operable equivalents — the same motivation that led Part 9 to replace manually-run deployment scripts with tracked CI/CD pipelines.

## 85.3 Training Jobs and Experiments

### 85.3.1 Jobs

**Definition:** A **Job** in Azure ML is a single tracked execution of code (a training script, most commonly) against a specified compute target, environment (a container image or Conda specification defining the Python/library versions used), and set of input data assets — every job execution is automatically logged with its code, environment, inputs, outputs, metrics, and logs, making it individually reproducible and comparable against other runs.

**How it works conceptually:** submitting a job doesn't run code on the machine that submitted it — it packages the specified script, environment definition, and input references, sends that package to the target Compute Cluster (Section 84.4.2), and the cluster executes it, streaming logs and metrics back to the workspace in real time, similar in spirit to how a CI/CD pipeline (Part 9) packages and dispatches a build to a remote agent rather than running it on the developer's own machine.

### 85.3.2 Experiments

**Definition:** An **Experiment** is a logical grouping of related Jobs — typically all the runs associated with training a particular model, letting a data scientist compare metrics (accuracy, loss, F1 score, whatever was logged) across many runs side by side in the AML Studio UI, rather than manually keeping a spreadsheet of results.

## 85.4 Hyperparameter Tuning — Sweep Jobs

### 85.4.1 What a Sweep Job Does

**Definition:** A **Sweep Job** automates hyperparameter search by running the same training script many times with systematically varied hyperparameter values (learning rate, batch size, regularization strength, and so on), using a specified sampling strategy, and tracking each run as part of the same experiment so the best-performing combination can be identified automatically rather than manually.

### 85.4.2 Sampling Strategies

- **Grid sampling** — exhaustively tries every combination of specified hyperparameter values; thorough but expensive as the number of hyperparameters and values grows.
- **Random sampling** — randomly samples combinations from specified distributions/ranges; often nearly as effective as grid sampling at a fraction of the compute cost.
- **Bayesian sampling** — uses the results of previous runs to intelligently choose the next combination to try, typically converging on good hyperparameters faster than either grid or random sampling for a comparable run budget.

### 85.4.3 Early Termination Policies

To avoid wasting compute on runs that are clearly underperforming partway through training, Sweep Jobs support **early termination policies** (such as Bandit or Median Stopping policies) that monitor a run's intermediate metrics and cancel it early if it's substantially behind other runs at the same point in training — meaningfully reducing the total compute cost of a large hyperparameter search.

⚠️ Specific sampling algorithm names, their exact configuration parameters, and early termination policy options are an area where the SDK v1-to-v2 transition changed syntax; verify current sweep job configuration syntax against official documentation before writing production sweep job definitions.

## 85.5 AML Pipelines

**Definition:** An **AML Pipeline** is a defined, reusable sequence of discrete steps (data preparation, training, evaluation, registration, for example) chained together into a single executable workflow, where each step can run on its own appropriately-sized compute target and outputs from one step feed as inputs into the next.

**How it works conceptually:** this is directly analogous to a Data Factory pipeline (Section 77) or a CI/CD pipeline (Part 9) applied specifically to the ML lifecycle — instead of a data scientist manually running a data-prep script, then manually running a training script, then manually running an evaluation script, a single AML Pipeline definition captures all three steps and their dependencies, making the entire process one reproducible, schedulable, and shareable artifact rather than a sequence of manual actions someone has to remember to perform in the right order.

🎯 **Interview Tip:** A frequently tested nuance: AML Pipelines are step-caching-aware — if a pipeline step's inputs, code, and environment haven't changed since a previous run, AML can skip re-executing that step and reuse its cached output, meaningfully speeding up iterative pipeline development where only the final training step is actually being changed between runs.

## 85.6 Model Registry

**Definition:** The **Model Registry** is a versioned catalog of trained models within the workspace — registering a model captures a specific trained artifact (the model file itself) along with metadata (which job produced it, what metrics it achieved, what environment it needs to run) as an immutable, versioned entry, so a specific model version can always be traced back to the exact job, code, and data that produced it.

**Why this matters:** without a registry, "which model is currently deployed to production" and "can we roll back to the previous version if the new one underperforms" become manual, error-prone questions — the registry gives both an authoritative answer, since a deployment always references a specific registered model version rather than an arbitrary file path. This versioning and rollback capability is expanded on operationally in Section 86 (MLOps).

## 85.7 Inference Endpoints

### 85.7.1 Managed Online Endpoints

**Definition:** A **Managed Online Endpoint** is a fully managed, real-time HTTP(S) inference endpoint — Azure ML provisions and operates the underlying compute (VM instances behind the scenes), handles load balancing, and exposes a stable REST endpoint that applications call synchronously, expecting a low-latency response per request.

**How it works conceptually:** a Managed Online Endpoint supports multiple **deployments** underneath a single stable endpoint URL, each deployment representing a specific registered model version running on its own compute allocation — traffic can be split across deployments by percentage, enabling controlled rollout patterns.

### 85.7.2 Blue-Green Deployments and Traffic Splitting

A common pattern deploys a new model version as a second deployment behind the same endpoint, initially receiving 0% (or a small percentage) of live traffic, then gradually increasing that percentage as confidence in the new version grows, with the ability to shift traffic back to the prior (blue) deployment immediately if problems emerge — the same blue-green/canary deployment philosophy used for general application deployments (Part 9), applied specifically to model deployments.

### 85.7.3 Batch Endpoints

**Definition:** A **Batch Endpoint** is designed for asynchronous, large-volume scoring — rather than a synchronous request/response for individual predictions, a batch endpoint accepts a large dataset (referencing a datastore location) and processes it as a job across a compute cluster, writing scored results back out, appropriate for workloads like scoring an entire customer database overnight rather than serving individual real-time requests.

## 85.8 Managed Online Endpoints vs. Batch Endpoints — Comparison

| Aspect              | Managed Online Endpoint                                                     | Batch Endpoint                                                                  |
| ------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------- |
| Invocation          | Synchronous HTTP request/response                                           | Asynchronous job over a dataset                                                 |
| Latency expectation | Low (real-time, typically milliseconds)                                     | High-throughput over minutes/hours, not latency-sensitive                       |
| Compute             | Always-provisioned (or autoscaled) instances behind the endpoint            | Compute Cluster (Section 84.4.2), scales for the duration of the batch job only |
| Typical use case    | Live application feature (fraud scoring on a transaction, chatbot response) | Nightly/periodic scoring of large datasets (scoring an entire customer table)   |
| Cost model          | Pay for provisioned instances continuously (or per autoscale policy)        | Pay only for compute consumed during the batch job's execution                  |

## 85.9 Architecture Diagram

```
Model Registry (versioned models, each traceable to a Job)
        │
        ├──► Managed Online Endpoint "ep-fraud-scoring"
        │       ├── Deployment "blue"  (90% traffic) — model v3
        │       └── Deployment "green" (10% traffic) — model v4 (canary)
        │
        └──► Batch Endpoint "ep-nightly-scoring"
                └── Batch Job ──► Compute Cluster (scales up for job, then to zero)
                        │
                        ▼
                Scored output written to Datastore

Training side:
Data Asset ──► Job (training script + environment + compute) ──► Experiment (tracked runs)
                     │
                     ▼
              Sweep Job (hyperparameter search across many Jobs)
                     │
                     ▼
              Best Job's model ──► registered to Model Registry
```

## 85.10 Configuration & Hands-On Example

**Submitting a training job and deploying a registered model to a Managed Online Endpoint (Azure CLI v2, YAML job/endpoint definitions):**

```bash
# Submit a training job
az ml job create --file train-job.yml --resource-group rg-ml-prod --workspace-name mlw-project

# Register the resulting model (after inspecting job output)
az ml model create --name fraud-model --version 1 \
  --path azureml://jobs/<job-name>/outputs/model \
  --resource-group rg-ml-prod --workspace-name mlw-project

# Create the endpoint and a deployment behind it
az ml online-endpoint create --name ep-fraud-scoring \
  --resource-group rg-ml-prod --workspace-name mlw-project

az ml online-deployment create --name blue \
  --endpoint ep-fraud-scoring \
  --model fraud-model:1 \
  --instance-type Standard_DS3_v2 \
  --instance-count 2 \
  --traffic-percentage 100 \
  --resource-group rg-ml-prod --workspace-name mlw-project
```

- **Purpose:** Walks through the full path from a training job to a live, traffic-serving endpoint — training, registration, endpoint creation, and deployment — mirroring the lifecycle diagram in Section 85.9.
- **Important arguments explained individually:**
  - `--path azureml://jobs/<job-name>/outputs/model` — registers the model artifact directly from a completed job's output folder, preserving the traceability link back to the exact job that produced it (Section 85.6).
  - `--instance-count 2` — provisions two instances behind this specific deployment for both throughput and availability; a single instance would be a single point of failure for this deployment.
  - `--traffic-percentage 100` — routes all endpoint traffic to this deployment; a canary rollout (Section 85.7.2) would instead create a second deployment with a smaller percentage and gradually shift traffic.
- **Common error:** Attempting to deploy a model without first registering it (referencing a raw job output path directly in the deployment instead of a registered model) works in ad-hoc testing but breaks the versioning and rollback story described in Section 85.6 — production deployments should always reference an explicitly registered, versioned model.

## 85.11 Production & Enterprise Usage

Production AML usage typically wraps individual training jobs into an AML Pipeline (Section 85.5) triggered by CI/CD (Azure DevOps or GitHub Actions, expanded on operationally in Section 86) rather than manually submitted by a data scientist, with the pipeline's final steps handling model evaluation against a holdout set and conditional registration (only registering — and potentially auto-deploying — a new model version if it beats the currently deployed version on key metrics). Managed Online Endpoints in production are typically configured with autoscaling and multiple instances for availability, deployed behind a blue-green traffic split during rollout of any new model version, with automated rollback (shifting traffic back to the prior deployment) if monitored error rates or latency degrade after a rollout — the operational specifics of this monitoring and rollback are covered in Section 86.

## 85.12 Security Considerations

- Managed Online Endpoints support **Managed Identity** (Section 9) for the deployment's own runtime identity, letting the deployed model's scoring code access other Azure resources (a feature store, an external API) without embedded credentials, and support **key-based or Microsoft Entra ID token-based authentication** for callers of the endpoint itself — production endpoints should prefer Entra ID token auth over long-lived static keys where feasible.
- Endpoints can be configured with private networking (no public IP, accessed only via a private endpoint within a VNet), preventing the inference API from being reachable over the public internet — important for endpoints scoring sensitive data (e.g., a fraud-scoring endpoint processing real transaction data).
- Batch Endpoints reading from and writing to datastores should use identity-based datastore access (Section 84.3.2) rather than embedded storage keys, keeping the same least-privilege posture established for training data access.

## 85.13 Performance Considerations

Managed Online Endpoint latency is driven by instance SKU, instance count, and autoscaling responsiveness — an under-provisioned deployment with too few instances queues requests under load, increasing tail latency; autoscaling rules should be tuned against realistic load patterns rather than left at defaults for latency-sensitive production endpoints. Batch Endpoint throughput scales with the underlying Compute Cluster's `max-instances` and the degree of parallelism configured for the batch job — a batch job processing a very large dataset with an insufficiently sized cluster simply takes proportionally longer, which matters if the batch job has a completion-time SLA (e.g., "nightly scoring must finish before business hours").

## 85.14 Monitoring

Managed Online Endpoints emit request count, latency, and error rate metrics to Azure Monitor and Application Insights (Part 10) by default via the workspace's associated Application Insights instance (Section 84.3.1), enabling standard alerting (Section 53) on elevated error rates or latency degradation following a new deployment's traffic ramp-up. Batch Endpoint jobs surface status and per-record scoring results/errors through the AML Studio job UI and can similarly be monitored via Azure Monitor for job failures or unusually long completion times.

## 85.15 Troubleshooting

| Symptom                                                  | Likely Cause                                                                                                                                             | Fix                                                                                                                                      |
| -------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Sweep job runs many trials but never seems to improve    | Poorly chosen hyperparameter search space/distributions, or too few trials for the chosen sampling strategy                                              | Review the search space definition; consider Bayesian sampling (Section 85.4.2) for more efficient convergence with a limited run budget |
| Managed Online Endpoint deployment fails to come healthy | Scoring script error, missing dependency in the deployment's environment definition, or insufficient instance resources for the model's memory footprint | Review deployment logs; verify the environment definition includes all required dependencies and the instance type has sufficient memory |
| Batch endpoint job takes far longer than expected        | Compute Cluster `max-instances` too low for the dataset size, or insufficient parallelism configured on the batch job                                    | Increase cluster `max-instances` and/or the batch job's configured mini-batch size and parallelism                                       |

## 85.16 Interview Questions — Section 85

### 🎯 Intermediate

**Q: When would you choose a Batch Endpoint over a Managed Online Endpoint, and why does the compute cost model differ between them?**

_Model answer:_ A Batch Endpoint fits scenarios that don't need a real-time response — scoring an entire dataset periodically (e.g., nightly customer churn scoring) rather than serving individual live requests. A Managed Online Endpoint fits scenarios needing low-latency, synchronous responses to individual requests, like a fraud-scoring check during a live transaction. The cost model differs because a Managed Online Endpoint keeps instances continuously provisioned (or autoscaled within a live range) to be ready for requests at any moment, while a Batch Endpoint's underlying Compute Cluster only scales up for the duration of the batch job and scales back to zero afterward, so cost is incurred only while actual batch scoring work is happening.

_What the interviewer is probing:_ whether the candidate can map a workload's actual latency and volume requirements to the correct endpoint type, rather than defaulting to real-time endpoints for everything regardless of fit — a common source of unnecessary cost in real deployments.

### 🎯 Senior/Architect

**Q: You need to roll out a new fraud-detection model version to production with minimal risk. Describe the deployment strategy using Azure ML's endpoint and deployment model, and how you'd decide whether to complete or roll back the rollout.**

_Model answer:_ I'd register the new model version in the Model Registry (Section 85.6), preserving traceability to the exact job, code, and data that produced it, then create a second deployment (green) behind the existing Managed Online Endpoint alongside the currently-serving deployment (blue), initially routing a small percentage of live traffic — say 5-10% — to green while blue continues serving the majority. I'd monitor the green deployment's error rate, latency, and (crucially, for a fraud model) business metrics like false-positive/false-negative rates via Application Insights and any custom logging, comparing against blue's baseline over a defined observation window. If green's metrics hold up or improve, I'd incrementally increase its traffic percentage toward 100%, eventually decommissioning the blue deployment; if green shows elevated errors, latency regressions, or worse fraud-detection accuracy, I'd immediately shift traffic back to 100% blue, since the deployment infrastructure supports this rollback as a traffic-percentage change rather than requiring a redeploy. Throughout, since this is a fraud model handling sensitive transaction data, I'd also ensure the endpoint uses private networking and Entra ID-based authentication rather than static keys, and that the model's Responsible AI evaluation (Section 86, Section 89) was completed before green ever received live traffic, not just after the fact.

_What the interviewer is probing:_ whether the candidate can design a genuinely low-risk rollout using the specific mechanics AML provides (multi-deployment endpoints, traffic splitting, rollback-by-traffic-shift) rather than a vague "we'll do canary deployment," and whether they connect the technical rollout to the specific business risk (fraud model correctness) and security/governance considerations rather than treating it as a generic deployment.

## 85.17 Common Misconceptions

- **"A Sweep Job trains one model with automatically-chosen best settings."** False — a Sweep Job runs many separate training jobs across a range of hyperparameter combinations, and it's the candidate's/pipeline's responsibility to select and register the best-performing resulting job's model.
- **"Batch Endpoints and Managed Online Endpoints are just two configuration options for the same underlying endpoint type."** False — they are distinct resource types with different invocation models (synchronous request/response vs. asynchronous job-over-dataset) and different underlying compute and cost models.
- **"Once a model is registered, deploying a new version means editing the existing deployment in place."** False — the standard, low-risk pattern creates a new deployment behind the same endpoint and shifts traffic gradually, rather than overwriting an already-serving deployment.

## 85.18 Key Takeaways

- 🔑 Jobs are the tracked unit of execution in Azure ML, capturing code, environment, data, and metrics for reproducibility; Experiments group related Jobs for comparison.
- 🔑 Sweep Jobs automate hyperparameter search using grid, random, or Bayesian sampling, with early termination policies to avoid wasting compute on clearly underperforming trials.
- 🔑 AML Pipelines chain multiple steps into a single reusable, cacheable workflow, mirroring the Data Factory/CI-CD pipeline pattern applied to the ML lifecycle specifically.
- 🔑 The Model Registry provides versioned, traceable model artifacts, which Managed Online Endpoints reference via multiple traffic-split deployments to enable safe, gradual, reversible rollouts.
- 🔑 Managed Online Endpoints suit low-latency, synchronous, real-time inference; Batch Endpoints suit high-volume, asynchronous scoring jobs, with correspondingly different compute and cost models.

## 85.19 Related Concepts (Next Up)

Section 86 turns from the mechanics of training and deploying an individual model to the operational discipline of running ML in production continuously — MLOps on Azure: monitoring deployed models for data and concept drift, wiring CI/CD (Azure DevOps or GitHub Actions, cross-referencing Part 9) around the AML Pipelines introduced here, the Responsible AI dashboard, and the model versioning/rollback mechanics touched on above, formalized into a repeatable operational process.
