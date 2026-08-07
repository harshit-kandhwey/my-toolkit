# Section 67 (Part 10): AutoML & Model Garden

## 1. Definition

**Plain language:** Not every team has (or needs) a data scientist writing custom training code. AutoML lets someone with a labeled dataset and no ML expertise get a production-quality model by clicking through a UI or making a few API calls. Model Garden is the opposite end of the spectrum for teams that don't want to train a model from scratch at all — it's a browsable catalog of ready-to-use foundation models (Google's own Gemini family plus third-party and open models) that can be deployed or called directly.

**Precise:** **Vertex AI AutoML** automates feature engineering, model architecture search, and hyperparameter tuning to produce a trained model from a labeled Vertex AI Dataset ([Section 65](./Section-65-Part10-Vertex-AI-Fundamentals.md)) across tabular, image, text, and video modalities, without the user writing training code. **Vertex AI Model Garden** is a curated catalog of first-party (Gemini), Google-partner, and open-source (e.g., Llama, Gemma, Mistral) foundation and task-specific models that can be deployed to an endpoint, fine-tuned, or called via API directly from the catalog page.

## 2. Why It Exists / Problem It Solves

- **Not every organization has ML engineers on staff.** A marketing team that wants to classify support tickets by sentiment shouldn't need to hire a data scientist to write a training script — AutoML makes model training accessible to analysts and developers who understand the business problem but not deep learning architecture.
- **Custom training is often unnecessary overhead.** For many well-understood problem types (tabular classification, image classification, entity extraction), AutoML's automated architecture search frequently matches or beats a hand-tuned custom model, at a fraction of the engineering time.
- **Building a foundation model from scratch is infeasible for almost everyone.** Training a large language model requires enormous compute, data, and expertise that only a handful of organizations possess. Model Garden lets any team start from an already-trained, state-of-the-art foundation model instead.
- **Teams need to compare models before committing.** Model Garden centralizes discovery — benchmarks, licensing terms, and deployment options — so teams aren't hunting across scattered open-source repositories to figure out which model fits their latency, cost, and accuracy requirements.

## 3. Core Concepts

### 3.1 AutoML by Modality

| Modality | AutoML Product | Typical Use Case                                                                  |
| -------- | -------------- | --------------------------------------------------------------------------------- |
| Tabular  | AutoML Tables  | Churn prediction, fraud scoring, demand forecasting from structured/BigQuery data |
| Image    | AutoML Image   | Product defect detection, medical image classification, object detection          |
| Text     | AutoML Text    | Support-ticket classification, sentiment analysis, entity extraction              |
| Video    | AutoML Video   | Video content classification, object tracking/action recognition                  |

All AutoML modalities share the same workflow: import a labeled Vertex AI Dataset ([Section 65](./Section-65-Part10-Vertex-AI-Fundamentals.md)) → AutoML runs automated architecture search and hyperparameter tuning internally (you never see or edit the underlying model code) → the result is a registered model in Model Registry ([Section 66](./Section-66-Part10-Vertex-AI-Deep-Dive-Training-Pipelines-Endpoints.md)), deployable to an Online or Batch endpoint exactly like a custom-trained model.

### 3.2 AutoML Trade-offs vs. Custom Training

| Aspect               | AutoML                                           | Custom Training ([Section 66](./Section-66-Part10-Vertex-AI-Deep-Dive-Training-Pipelines-Endpoints.md)) |
| -------------------- | ------------------------------------------------ | ------------------------------------------------------------------------------------------------------- |
| Code required        | None (dataset + config only)                     | Training script (Python/framework of choice)                                                            |
| Architecture control | None — Google selects and tunes the architecture | Full control over model architecture                                                                    |
| Time to first model  | Fast (minutes to a few hours)                    | Slower (write, debug, and iterate on training code)                                                     |
| Best for             | Standard, well-understood problem types          | Novel architectures, research, highly specialized domains                                               |
| Cost model           | Pay for AutoML training compute (node-hours)     | Pay for custom training compute (node-hours)                                                            |

### 3.3 Model Garden

**Model Garden** organizes available models into three broad categories:

- **Google first-party models**: the Gemini family ([Section 68](./Section-68-Part10-Generative-AI-Gemini-PaLM.md)) and task-specific Google models (e.g., embedding models, specialized vision models).
- **Partner models**: models from Google's model partners (e.g., Anthropic's Claude, available via Vertex AI Model Garden as a fully managed API), offered with the same billing/IAM integration as first-party models.
- **Open models**: openly licensed models (e.g., Llama, Gemma, Mistral) that can be deployed to a self-managed Vertex AI Endpoint, giving control over weights and hosting while still using Vertex AI's managed infrastructure.

For each model, Model Garden shows benchmark data, a "deploy" or "fine-tune" action, licensing/usage terms, and (for API-based models) a direct playground to test prompts before writing code.

### 3.4 Deploying from Model Garden

A model selected in Model Garden is deployed one of two ways:

1. **Managed API call** (for Gemini and most partner models) — no infrastructure to manage; you call the model's API endpoint directly and pay per token/request.
2. **Self-managed endpoint deployment** (typical for open models) — the model weights are deployed onto Vertex AI-managed compute (with GPU/TPU as needed) as a dedicated Online Endpoint ([Section 66](./Section-66-Part10-Vertex-AI-Deep-Dive-Training-Pipelines-Endpoints.md)) that you configure, scale, and pay for by node-uptime, similar to deploying a custom-trained model.

## 4. Architecture Diagram: Two Paths to a Deployed Model

```
                          ┌─────────────────────┐
                          │Vertex AI Dataset    │
                          │(labeled, Section 65)│
                          └─────────┬───────────┘
                                    │
                       ┌────────────┴─────────────┐
                       ▼                          ▼
              ┌────────────────┐           ┌──────────────────────┐
              │AutoML Training │           │ Custom Training Job  │
              │ (no code, auto │           │(Section 66, your own │
              │  architecture) │           │ training script)     │
              └────────┬───────┘           └─────────┬────────────┘
                       │                             │
                       └───────────────┬─────────────┘
                                       ▼
                                ┌─────────────────┐
                                │  Model Registry │
                                └────────┬────────┘
                                         ▼
                                ┌─────────────────┐
                                │ Online/Batch    │
                                │ Endpoint        │
                                └─────────────────┘

                     Separate path — no dataset/training needed:

                     ┌────────────────────┐        ┌───────────────────┐
                     │  Model Garden      │───────►│ Managed API call  │
                     │  (Gemini, partner, │        │  OR self-managed  │
                     │   open models)     │        │  endpoint deploy  │
                     └────────────────────┘        └───────────────────┘
```

## 5. Comparison: AutoML/Model Garden vs. AWS vs. Azure

| Capability                               | GCP                                                    | AWS                                                     | Azure                                                   |
| ---------------------------------------- | ------------------------------------------------------ | ------------------------------------------------------- | ------------------------------------------------------- |
| No-code tabular/vision AutoML            | Vertex AI AutoML (Tables, Image, Text, Video)          | SageMaker Canvas / SageMaker Autopilot                  | Azure ML Automated ML                                   |
| Foundation model catalog                 | Vertex AI Model Garden (Gemini, partners, open models) | Amazon Bedrock model catalog                            | Azure AI Foundry model catalog                          |
| First-party flagship model               | Gemini                                                 | Amazon Titan / Nova                                     | GPT (via OpenAI partnership)                            |
| Third-party model access in same catalog | Yes (e.g., Claude available in Model Garden)           | Yes (Anthropic, Meta, Cohere, Mistral, etc. in Bedrock) | Yes (OpenAI, Meta, Mistral, Cohere, etc. in AI Foundry) |
| Open-model self-hosting                  | Deploy to Vertex AI Endpoint                           | Deploy via SageMaker JumpStart                          | Deploy via Azure ML / AI Foundry managed compute        |
| Underlying AutoML mechanism              | Automated architecture search + hyperparameter tuning  | Automated algorithm selection + tuning                  | Automated algorithm selection + tuning                  |

> ⚠️ **Interview-relevant nuance:** All three major clouds converged on the same two-tier pattern — a no-code AutoML product for classic ML problem types, and a separate foundation-model catalog for generative AI — because the underlying problems (classic supervised learning vs. large pretrained model consumption) require fundamentally different tooling. Naming them correctly per cloud (SageMaker Canvas/Autopilot vs. Bedrock; Vertex AI AutoML vs. Model Garden; Azure Automated ML vs. AI Foundry model catalog) is a common interview stumble point.

## 6. Hands-On Example

**Beginner example — train an AutoML tabular classification model:**

```bash
gcloud ai auto-ml train tabular \
  --region=us-central1 \
  --display-name=churn-automl-model \
  --dataset=projects/my-gcp-project/locations/us-central1/datasets/DATASET_ID \
  --target-column=churned \
  --budget-milli-node-hours=1000 \
  --prediction-type=classification
```

**Purpose:** Kicks off a fully automated tabular classification training run (1 node-hour budget) with no training code required.

**Expected output:**

```
Using endpoint [https://us-central1-aiplatform.googleapis.com/]
Training pipeline created: projects/123456789012/locations/us-central1/trainingPipelines/9876543210
```

**Intermediate example — deploy a Model Garden open model to a self-managed endpoint (Python SDK):**

```python
from google.cloud import aiplatform

aiplatform.init(project="my-gcp-project", location="us-central1")

model = aiplatform.Model(model_name="publishers/meta/models/llama3-8b-instruct")
endpoint = model.deploy(
    machine_type="g2-standard-24",
    accelerator_type="NVIDIA_L4",
    accelerator_count=2,
    min_replica_count=1,
    max_replica_count=3,
)
print(endpoint.resource_name)
```

**Purpose:** Deploys an open Model Garden model (Llama 3 8B) to a dedicated GPU-backed endpoint you control, rather than calling a Google-managed API.

**Expected output:**

```
Creating Endpoint
Endpoint created. Resource name: projects/123456789012/locations/us-central1/endpoints/5566778899
Deploying model to Endpoint...done.
projects/123456789012/locations/us-central1/endpoints/5566778899
```

**Calling a managed Model Garden model directly (no deployment step):**

```bash
gcloud ai models list --region=us-central1 --filter="displayName:gemini*"
```

**Purpose:** Confirms available managed Gemini model variants without any deployment step, since managed API models require no endpoint provisioning.

**Expected output:**

```
MODEL_ID              DISPLAY_NAME
publishers/google/... gemini-2.0-flash
publishers/google/... gemini-2.0-pro
```

## 7. Production & Enterprise Usage

- Enterprises default to **AutoML** for standard, well-understood problem types (churn, fraud scoring, defect detection) to reduce time-to-first-model and free ML engineers to focus on higher-value custom work rather than reinventing well-solved problem types.
- **Model Garden's managed API models** (Gemini, partner models like Claude) are the default choice for generative AI features where teams want zero infrastructure management and per-token billing; **self-managed open-model endpoints** are chosen when data residency, model customization, or predictable fixed-cost hosting requirements rule out a managed API.
- Enterprises use Model Garden's centralized catalog (with benchmarks and licensing terms visible in one place) as part of formal model-selection governance — comparing cost, latency, and accuracy trade-offs across models before committing a production workload to one.
- AutoML models still flow through the same **Model Registry** and **Online/Batch Endpoints** ([Section 66](./Section-66-Part10-Vertex-AI-Deep-Dive-Training-Pipelines-Endpoints.md)) as custom-trained models, so production MLOps tooling (monitoring, rollback) is identical regardless of how the model was trained.

## 8. Common Misconceptions

- **Misconception:** "AutoML is only for beginners and always produces a worse model than custom training." For standard, well-understood problem types, AutoML's automated architecture search frequently matches or exceeds hand-tuned custom models — many production systems at large enterprises run on AutoML-trained models with no shame or performance penalty involved.
- **Misconception:** "Model Garden only has Google's own models." Model Garden includes partner models (e.g., Anthropic's Claude) and open-source models (Llama, Gemma, Mistral) alongside Gemini — it is a multi-vendor catalog, not a Gemini-only showcase.
- **Misconception:** "Every model in Model Garden works the same way." Managed API models (most first-party/partner models) require no deployment step and bill per-request/token; open models typically require an explicit endpoint deployment step and bill by node-uptime — conflating the two leads to incorrect cost and latency assumptions.

## 9. Interview Questions

**🎯 Beginner:** _What is the difference between Vertex AI AutoML and Vertex AI Model Garden?_
**Model answer:** AutoML trains a new model from your own labeled dataset without you writing training code — you provide data, AutoML handles architecture search and tuning, and you get a custom-trained model for your specific problem. Model Garden is a catalog of already-trained foundation and task-specific models (Gemini, partner models like Claude, and open models like Llama) that you deploy or call directly — there's no training step, you're consuming an existing model rather than creating a new one.

**🎯 Intermediate:** _When would you choose a self-managed Model Garden endpoint deployment over a managed API call?_
**Model answer:** A managed API call (e.g., calling Gemini directly) requires no infrastructure management and bills per-request/token, which is simplest when it meets your requirements. You'd choose a self-managed endpoint deployment instead when you need an open model not offered as a managed API, when you need to fine-tune and host a customized version of a model, when data residency or network isolation requirements mean the model must run inside your own VPC Service Controls perimeter, or when your traffic volume is high and predictable enough that fixed node-hour billing is cheaper than per-token billing.

**🎯 Senior/Architect:** _A retail company wants to add a product-defect image classifier and a customer-support chatbot. How would you decide which parts of this use AutoML, Model Garden, or custom training, and how do the pieces fit into the same production MLOps pipeline?_
**Model answer:** For the defect classifier, I'd start with AutoML Image against a labeled Vertex AI Dataset of product images — image defect detection is a well-understood classification problem where AutoML's automated architecture search typically performs competitively, and it gets a production model far faster than custom training. I'd only move to custom training ([Section 66](./Section-66-Part10-Vertex-AI-Deep-Dive-Training-Pipelines-Endpoints.md)) if AutoML's accuracy ceiling proves insufficient for a highly specialized defect type, which would justify the added engineering cost. For the chatbot, there's no reason to train a language model from scratch — I'd start in Model Garden with a managed Gemini API call, using Vertex AI Studio ([Section 68](./Section-68-Part10-Generative-AI-Gemini-PaLM.md)) for prompt design and grounding against the company's product/support documentation via Vertex AI Search for RAG ([Section 68](./Section-68-Part10-Generative-AI-Gemini-PaLM.md)), avoiding hallucinated answers about specific products. Both pieces converge on the same production pipeline regardless of origin: the AutoML-trained defect model registers into Model Registry and deploys to an Online Endpoint exactly like a custom model would, and both the defect endpoint and the chatbot's Gemini calls sit behind the same IAM and VPC Service Controls perimeter ([Section 41](../Part5/Section-41-Part5-VPC-Service-Controls.md)) and are monitored through the same MLOps tooling ([Section 69](./Section-69-Part10-MLOps-on-GCP.md)) — the choice of AutoML vs. Model Garden vs. custom training only affects how a model is produced, not how it's governed or operated afterward.

## 10. Key Takeaways

- 🔑 AutoML trains a custom model from your own labeled dataset with no training code, across tabular, image, text, and video modalities.
- 🔑 AutoML often matches or beats hand-tuned custom models for well-understood problem types, making "AutoML is only for beginners" a myth.
- 🔑 Model Garden is a multi-vendor catalog (Google first-party, partner, and open models) — not a Gemini-only showcase — for consuming already-trained foundation models rather than training new ones.
- 🔑 Managed API models require no deployment and bill per-token/request; open models typically require explicit endpoint deployment and bill by node-uptime — choosing correctly matters for both cost and latency.
- 🔑 AutoML-trained and custom-trained models converge on the same Model Registry and Endpoint infrastructure ([Section 66](./Section-66-Part10-Vertex-AI-Deep-Dive-Training-Pipelines-Endpoints.md)), so production MLOps tooling doesn't care how a model was produced.

## 11. Related Concepts

Vertex AI Fundamentals and Datasets ([Section 65](./Section-65-Part10-Vertex-AI-Fundamentals.md)) as the data source AutoML consumes, Vertex AI Deep Dive Training/Pipelines/Endpoints ([Section 66](./Section-66-Part10-Vertex-AI-Deep-Dive-Training-Pipelines-Endpoints.md)) for the shared Model Registry and serving infrastructure, Generative AI on GCP ([Section 68](./Section-68-Part10-Generative-AI-Gemini-PaLM.md)) for deeper coverage of Gemini/Vertex AI Studio consumption patterns, MLOps on GCP ([Section 69](./Section-69-Part10-MLOps-on-GCP.md)) for monitoring models regardless of training origin, and VPC Service Controls ([Section 41](../Part5/Section-41-Part5-VPC-Service-Controls.md)) for securing Model Garden endpoint access.
