# Section 70 (Part 10): AI/ML Security & Responsible AI

## 1. Definition

**Plain language:** Machine learning systems introduce security and ethical risks that traditional application security doesn't fully cover — training data can leak sensitive information, a model's predictions can be systematically unfair to certain groups, and "how did the model decide that" is often a much harder question to answer than "what did this line of code do." This section covers how to secure who can touch Vertex AI resources, keep sensitive data contained, understand why a model made a given prediction, and align ML systems with Google's published Responsible AI principles.

**Precise:** AI/ML security and governance on GCP combines standard **IAM** (Section 35) scoped to Vertex AI resources, **VPC Service Controls** (Section 41) perimeters wrapping Vertex AI to prevent data exfiltration, **data governance** controls over training data provenance and access, **Vertex AI Explainable AI** for feature-attribution-based model interpretability, and adherence to **Google's Responsible AI principles**, which guide fairness, safety, and accountability requirements for AI systems built on the platform.

## 2. Why It Exists / Problem It Solves

- **ML resources carry unusually broad blast radius if compromised.** A compromised service account with access to a Feature Store or training dataset can exfiltrate sensitive customer data at scale in a single operation — the same care given to database and storage access must extend to ML data and model resources.
- **Training data can leak through the model itself, not just through direct data access.** Models can memorize and, under certain conditions, reveal fragments of their training data through their outputs — data governance for ML must consider this risk, not just who has read access to the raw dataset.
- **"The model said so" is not an acceptable answer in regulated decisions.** Credit approval, hiring, insurance pricing, and similar high-stakes decisions increasingly face legal and regulatory requirements to explain why a model produced a given output — explainability tooling exists to answer that question with actual evidence, not post-hoc guesswork.
- **Unmanaged AI systems can cause real harm at scale.** A model that is systematically less accurate for one demographic group, or that generates unsafe content, can cause harm far faster and at far greater scale than a single human decision-maker acting badly — responsible AI principles and processes exist to catch this before deployment, not after.

## 3. Core Concepts

### 3.1 IAM for Vertex AI Resources

Vertex AI resources (Datasets, Models, Endpoints, Pipelines, Feature Store) are governed by the same IAM model (Section 35) as the rest of GCP, with Vertex AI-specific predefined roles such as:

| Role                      | Typical Grant                               | Scope                                                            |
| ------------------------- | ------------------------------------------- | ---------------------------------------------------------------- |
| `roles/aiplatform.user`   | Data scientists building/training models    | Full read/write on most Vertex AI resources                      |
| `roles/aiplatform.viewer` | Stakeholders reviewing model performance    | Read-only access to models, endpoints, metrics                   |
| `roles/aiplatform.admin`  | Platform team                               | Full control including IAM policy changes on Vertex AI resources |
| Custom roles              | Narrowly scoped production service accounts | e.g., predict-only permission on a single endpoint, nothing else |

Following least privilege (Section 35), production serving service accounts should hold only the narrow permission needed to call an endpoint's prediction API — never broad `aiplatform.user`/`admin` roles, which would allow modifying or deleting production models and pipelines from a context that only needs to serve predictions.

### 3.2 VPC Service Controls Perimeter Around Vertex AI

As introduced in Section 41, **VPC Service Controls (VPC-SC)** creates a service perimeter that blocks data exfiltration even by a principal with valid IAM permissions, by restricting API-level data movement across the perimeter boundary. Applied to Vertex AI specifically:

- A VPC-SC perimeter wrapping Vertex AI, BigQuery, and Cloud Storage together ensures training data, Feature Store contents, and model artifacts cannot be copied out to a project or service outside the perimeter — even by someone with legitimate `aiplatform.user` access — unless an explicit perimeter bridge or access level is configured.
- This directly mitigates the scenario where a compromised or malicious insider credential has valid IAM permissions but should still be prevented from exfiltrating an entire training dataset to a personal GCP project outside the organization's security boundary.
- Generative AI grounding data (Vertex AI Search indexes, Section 68) and Model Garden endpoint traffic should sit inside the same perimeter as other sensitive Vertex AI resources, since grounding retrieval often surfaces the same sensitive enterprise data the perimeter is meant to protect.

### 3.3 Data Governance for Training Data

Beyond access control, ML-specific data governance covers:

- **Provenance tracking**: knowing exactly which dataset version, with what consent/licensing basis, trained a given deployed model — Vertex AI ML Metadata (Section 66) provides the technical lineage; governance policy defines what's acceptable to train on in the first place.
- **PII handling in training data**: sensitive fields should be de-identified (e.g., via Cloud DLP tokenization/redaction) before being used for training where the model does not genuinely need the raw sensitive value to perform its task.
- **Data retention and deletion**: the ability to remove a specific individual's data from training pipelines and, where required, understand what a deployed model may have already learned from it — a nontrivial requirement when legal frameworks require honoring data deletion requests.

### 3.4 Vertex AI Explainable AI

**Vertex AI Explainable AI** provides **feature attribution** — a quantified breakdown of how much each input feature contributed to a specific prediction. For a rejected loan application, for example, Explainable AI can show that "debt-to-income ratio" contributed most heavily to the negative prediction, followed by "credit history length" — turning "the model said no" into a specific, auditable, feature-level explanation. It supports both:

- **Tabular models**: attribution across structured input features.
- **Image models**: attribution as a visual overlay ("saliency map") highlighting which pixels most influenced the prediction.

Explainable AI integrates directly with Online Endpoints (Section 66), so an explanation can be requested alongside — or instead of — a plain prediction, without a separate model or pipeline.

### 3.5 Google's Responsible AI Principles

Google publishes a set of **AI Principles** that guide the design and deployment of AI systems, broadly covering: being socially beneficial, avoiding creating or reinforcing unfair bias, being built and tested for safety, being accountable to people, incorporating privacy design principles, upholding high standards of scientific excellence, and being made available only for uses consistent with these principles. On GCP, this translates operationally into practices such as bias/fairness evaluation of model predictions across subgroups before deployment, human-review checkpoints for high-stakes automated decisions, and content-safety filtering configured on generative AI outputs (Section 68) to reduce harmful or inappropriate content.

## 4. Comparison: GCP AI/ML Security & Governance vs. AWS vs. Azure

| Capability                         | GCP                                                           | AWS                                   | Azure                                                |
| ---------------------------------- | ------------------------------------------------------------- | ------------------------------------- | ---------------------------------------------------- |
| IAM scoped to ML resources         | Vertex AI predefined/custom roles                             | SageMaker IAM policies/roles          | Azure ML RBAC roles                                  |
| Data exfiltration perimeter        | VPC Service Controls around Vertex AI                         | VPC endpoints + SCPs around SageMaker | Azure ML managed VNet / private endpoints            |
| Model explainability               | Vertex AI Explainable AI (feature attribution, saliency maps) | SageMaker Clarify                     | Azure ML Responsible AI dashboard (interpretability) |
| Bias/fairness evaluation           | Explainable AI + manual fairness evaluation practices         | SageMaker Clarify bias metrics        | Azure ML Responsible AI dashboard (fairness)         |
| Published responsible AI framework | Google AI Principles                                          | AWS Responsible AI guidelines         | Microsoft Responsible AI Standard                    |
| Content safety filtering (gen AI)  | Vertex AI safety filters/settings                             | Bedrock Guardrails                    | Azure AI Content Safety                              |

> ⚠️ **Interview-relevant nuance:** All three major clouds now ship a first-party explainability/fairness tool (Explainable AI, SageMaker Clarify, Azure ML Responsible AI dashboard) directly integrated with their ML platform, reflecting that model interpretability has moved from a research nicety to a standard production/compliance requirement — this convergence itself is a useful interview talking point when asked to compare platforms.

## 5. Architecture Diagram: Secured, Explainable Vertex AI Deployment

```
      Organization VPC Service Controls Perimeter (Section 41)
 ┌───────────────────────────────────────────────────────────────────┐
 │                                                                   │
 │   ┌─────────────┐    ┌───────────────┐    ┌───────────────────┐   │
 │   │Cloud Storage│    │  BigQuery     │    │ Vertex AI Datasets│   │
 │   │(raw data)   │    │ (curated data)│    │ / Feature Store   │   │
 │   └──────┬──────┘    └───────┬───────┘    └────────┬──────────┘   │
 │          └───────────────────┼─────────────────────┘              │
 │                              ▼                                    │
 │                    ┌──────────────────────┐                       │
 │                    │  Training Job/       │  ── narrowly-scoped   │
 │                    │Pipeline (Section 66) │     IAM service acct  │
 │                    └─────────┬────────────┘                       │
 │                              ▼                                    │
 │                    ┌───────────────────┐                          │
 │                    │  Model Registry   │                          │
 │                    └─────────┬─────────┘                          │
 │                              ▼                                    │
 │                    ┌───────────────────┐      Explainable AI      │
 │                    │  Online Endpoint  │◄──── attached for        │
 │                    │ (predict-only SA) │      feature attribution │
 │                    └───────────────────┘                          │
 │                                                                   │
 │   No path out of the perimeter without an explicit access level/  │
 │   perimeter bridge — even with valid IAM permissions.             │
 └───────────────────────────────────────────────────────────────────┘
```

## 6. Hands-On Example

**Beginner example — grant a narrowly scoped, predict-only custom role instead of broad access:**

```bash
gcloud iam roles create predictOnlyRole \
  --project=my-gcp-project \
  --title="Vertex AI Predict Only" \
  --permissions=aiplatform.endpoints.predict

gcloud projects add-iam-policy-binding my-gcp-project \
  --member=serviceAccount:churn-serving-sa@my-gcp-project.iam.gserviceaccount.com \
  --role=projects/my-gcp-project/roles/predictOnlyRole
```

**Purpose:** Grants a production serving service account only the ability to call `predict` on endpoints, without the broader `aiplatform.user` permissions that would allow modifying models or pipelines.

**Expected output:**

```
Created role [predictOnlyRole].
Updated IAM policy for project [my-gcp-project].
bindings:
- members: [serviceAccount:churn-serving-sa@my-gcp-project.iam.gserviceaccount.com]
  role: projects/my-gcp-project/roles/predictOnlyRole
```

**Intermediate example — add Vertex AI to a VPC Service Controls perimeter:**

```bash
gcloud access-context-manager perimeters update secure_ml_perimeter \
  --add-restricted-services=aiplatform.googleapis.com \
  --policy=123456789
```

**Purpose:** Extends an existing VPC-SC perimeter (already wrapping BigQuery/Cloud Storage) to also cover Vertex AI, so training data and model artifacts cannot be exfiltrated to a service or project outside the perimeter.

**Expected output:**

```
Updated perimeter [secure_ml_perimeter].
restrictedServices:
- bigquery.googleapis.com
- storage.googleapis.com
- aiplatform.googleapis.com
```

**Requesting a feature-attribution explanation alongside a prediction:**

```python
from google.cloud import aiplatform

endpoint = aiplatform.Endpoint("projects/123456789012/locations/us-central1/endpoints/5566778899")
response = endpoint.explain(instances=[{"tenure_months": 3, "monthly_charges": 89.50, "contract_type": "month-to-month"}])
for explanation in response.explanations:
    print(explanation.attributions)
```

**Purpose:** Returns not just a prediction but a per-feature attribution score, showing which inputs drove this specific prediction — e.g., that `contract_type` contributed most to a high churn-risk score.

**Expected output:**

```
[{feature: "contract_type", attribution: 0.41},
 {feature: "tenure_months", attribution: 0.33},
 {feature: "monthly_charges", attribution: 0.19}]
```

## 7. Production & Enterprise Usage

- Enterprises apply the same least-privilege discipline to Vertex AI as to any other sensitive resource: data scientists get `aiplatform.user` in development projects; production serving identities get narrow, custom, predict-only roles; and no human identity retains standing broad access to production ML resources.
- **VPC Service Controls around Vertex AI** is a near-default requirement in regulated industries (finance, healthcare) precisely because training data for models in these industries is often the most sensitive data the organization holds.
- **Explainable AI** output is retained alongside prediction logs for regulated decision types (credit, insurance, hiring-adjacent use cases), so that if a decision is challenged, the organization can produce the specific feature attribution that drove it rather than reconstructing an explanation after the fact.
- Enterprises formalize **bias/fairness evaluation** as a required pre-deployment gate for models influencing consequential decisions about people — evaluating prediction accuracy and error rates across relevant subgroups before a model is approved for production, not as an afterthought.
- Generative AI deployments (Section 68) apply content-safety filtering and human-review escalation paths for flagged outputs as a standard production control, aligned with Responsible AI principles around safety and accountability.

## 8. Common Misconceptions

- **Misconception:** "VPC Service Controls and IAM do the same job, so you only need one." IAM controls _who_ can call an API; VPC-SC controls whether data can _move across a perimeter boundary_ regardless of valid IAM permissions. A principal can have perfectly correct IAM permissions and still be blocked from exfiltrating data by VPC-SC — they solve different problems and are meant to be layered together, not chosen between.
- **Misconception:** "Explainable AI tells you whether a model is correct." Explainable AI shows which features most influenced a given prediction — it explains the model's own reasoning, not whether that reasoning reflects ground truth or the real world. A model can be confidently wrong and still produce a coherent-looking feature attribution for its wrong answer.
- **Misconception:** "Responsible AI is a compliance checkbox handled once before launch." Fairness and safety characteristics can shift as a model retrains on new data or as real-world usage patterns change, so responsible AI evaluation needs to be an ongoing practice tied into MLOps monitoring (Section 69), not a one-time pre-launch review.

## 9. Interview Questions

**🎯 Beginner:** _Why would you grant a production serving service account a narrow custom IAM role instead of `roles/aiplatform.user`?_
**Model answer:** `roles/aiplatform.user` grants broad read/write access across most Vertex AI resources — enough to modify models, delete pipelines, or change endpoint configuration. A production serving identity only needs to call the prediction API on one specific endpoint; granting it broad `aiplatform.user` access violates least privilege and means a compromised serving credential could be used to tamper with production models or pipelines, not just make predictions. A narrow custom role limited to `aiplatform.endpoints.predict` on the specific endpoint keeps the blast radius of a compromised credential to "can request predictions," nothing more.

**🎯 Intermediate:** _How does VPC Service Controls protect Vertex AI resources in a way that IAM alone doesn't?_
**Model answer:** IAM determines whether a specific identity is authorized to call a given API action, but it doesn't restrict where the data resulting from that authorized call can go. VPC Service Controls adds a perimeter around a set of services (e.g., Vertex AI, BigQuery, Cloud Storage) so that even a principal with entirely valid IAM permissions cannot move data — like copying a Feature Store's contents or a Model Registry artifact — to a project or service outside the perimeter, unless an explicit bridge or access level permits it. This specifically defends against a compromised or malicious insider credential that has legitimate permissions but should still be prevented from exfiltrating sensitive training data or models wholesale.

**🎯 Senior/Architect:** _A healthcare company is deploying a Vertex AI model that predicts patient readmission risk, feeding into clinical staffing decisions. Design the security and responsible AI controls you'd put around this system before it goes to production._
**Model answer:** I'd start with data governance: training data would be de-identified via Cloud DLP wherever the model doesn't genuinely require raw PII, with clear provenance tracking through ML Metadata (Section 66) so I can show exactly which patient-data version, with what consent basis, trained the deployed model. I'd wrap the full pipeline — Cloud Storage/BigQuery source data, Vertex AI Datasets and Feature Store, the training pipeline, and the deployed endpoint — inside a single VPC Service Controls perimeter (Section 41), since this is about as sensitive as training data gets, and I want data exfiltration blocked even against a compromised credential with otherwise-valid IAM access. IAM itself would be scoped narrowly: data scientists get `aiplatform.user` only in a development project working with de-identified data, and the production serving identity gets a custom predict-only role on the single deployed endpoint. Before launch, I'd run a formal bias/fairness evaluation comparing the model's accuracy and error rates across relevant patient subgroups, since a readmission-risk model that's systematically less accurate for one demographic could directly bias clinical staffing decisions against that group — this evaluation would be a hard pre-deployment gate, not a formality. I'd enable Vertex AI Explainable AI on the endpoint so every prediction used in a staffing decision comes with a feature attribution record, retained alongside prediction logs, so if a clinical decision is later reviewed or challenged, there's a specific, auditable explanation of what drove the model's output rather than an unexplainable "the model said so." Finally, I'd tie fairness and drift monitoring into the ongoing MLOps loop (Section 69) rather than treating the pre-launch fairness evaluation as a one-time event, since the patient population and clinical patterns this model sees will shift over time.

## 10. Key Takeaways

- 🔑 IAM and VPC Service Controls solve different problems and must be layered together: IAM governs who can call an API; VPC-SC governs whether data can move across a perimeter boundary even for authorized callers.
- 🔑 Production serving identities should hold narrow, predict-only custom roles — never broad `aiplatform.user`/`admin` — following least privilege.
- 🔑 Vertex AI Explainable AI provides feature-attribution and saliency-map explanations, but explains the model's own reasoning, not whether that reasoning is objectively correct.
- 🔑 Training data governance for ML must consider both direct data access and the risk that a model can memorize and leak training data through its outputs.
- 🔑 Responsible AI (fairness, safety, accountability) is an ongoing practice tied to MLOps monitoring, not a one-time pre-launch compliance checkbox.

## 11. Related Concepts

IAM Fundamentals (Section 35) and Organization Policies (Section 37) for the underlying access-control model, VPC Service Controls (Section 41) for the data-exfiltration perimeter applied here to Vertex AI, Vertex AI Deep Dive Training/Pipelines/Endpoints (Section 66) for the resources being secured, MLOps on GCP (Section 69) for tying fairness/drift monitoring into an ongoing operational loop, and Compliance & Governance (Section 40) for the broader regulatory context these controls support.
