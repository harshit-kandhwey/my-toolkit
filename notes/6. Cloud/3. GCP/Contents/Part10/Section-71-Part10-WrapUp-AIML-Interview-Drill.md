# Section 71 (Part 10): Part 10 Wrap-Up — AI/ML Synthesis & Interview Drill

## 71.1 Purpose of This Section

Part 10 covered GCP's AI/ML platform across six sections: Vertex AI foundations and data management (Section 65), custom training/pipelines/serving (Section 66), no-code AutoML and the Model Garden foundation-model catalog (Section 67), generative AI with Gemini and Vertex AI Studio (Section 68), MLOps for keeping deployed models healthy (Section 69), and AI/ML security and Responsible AI (Section 70). This closing section consolidates that material into one reference architecture, drills it with tiered interview questions spanning all six sections, and transitions into Part 11's Security Operations & Incident Response coverage.

## 71.2 Part 10 Recap — What Was Covered

| §   | Section                                               | Core Idea                                                                                                                                                                                                                        |
| --- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 65  | Vertex AI Fundamentals                                | Vertex AI unifies previously fragmented ML tooling (AI Platform, separate AutoML products) into one API/SDK/console/IAM model, spanning Workbench notebooks, Datasets, and Feature Store.                                        |
| 66  | Vertex AI Deep Dive — Training, Pipelines & Endpoints | Custom Training Jobs and Hyperparameter Tuning produce models; Vertex AI Pipelines (Kubeflow-based) orchestrates and reproduces the full workflow; Model Registry versions models; Online/Batch Endpoints serve predictions.     |
| 67  | AutoML & Model Garden                                 | AutoML trains a custom model from your own data with no code; Model Garden is a multi-vendor catalog (Gemini, partners, open models) for consuming already-trained foundation models instead.                                    |
| 68  | Generative AI — Gemini, Vertex AI Studio              | Gemini is Google's multimodal flagship model; Vertex AI Studio is the prompt design environment; grounding (Google Search or Vertex AI Search/RAG) and function calling connect models to real data and real actions.            |
| 69  | MLOps on GCP                                          | Model Monitoring detects skew/drift on deployed endpoints; Vertex AI Experiments tracks training runs reproducibly; CI/CD applies software-delivery discipline to pipeline definitions, closing the monitor-alert-retrain loop.  |
| 70  | AI/ML Security & Responsible AI                       | IAM least-privilege and VPC Service Controls (Section 41) secure Vertex AI resources and data; Explainable AI provides feature-attribution transparency; Responsible AI principles guide fairness/safety as an ongoing practice. |

## 71.3 The Unifying Architecture: End-to-End Governed ML Lifecycle

```
                         VPC Service Controls Perimeter (Section 41, Section 70.3.2)
 ┌──────────────────────────────────────────────────────────────────────────────────────────┐
 │                                                                                          │
 │  ┌──────────────────┐      ┌──────────────────┐     ┌─────────────────────────────────┐  │
 │  │ Vertex AI        │      │ Vertex AI        │     │  Two training paths:            │  │
 │  │ Workbench        │─────►│ Datasets/Feature │────►│  AutoML (Sec 67, no code)       │  │
 │  │(Sec 65, explore) │      │ Store (Sec 65)   │     │  Custom Training Job            │  │
 │  └──────────────────┘      └──────────────────┘     │(Sec 66, + Hyperparameter Tuning)│  │
 │                                                     └───────────────┬─────────────────┘  │
 │                                                                     ▼                    │
 │                                            ┌───────────────────────────────┐             │
 │                                            │Vertex AI Pipeline (Sec 66)    │             │
 │                                            │CI/CD-deployed (Sec 69),       │             │
 │                                            │tracked in Experiments (Sec 69)│             │
 │                                            └───────────────┬───────────────┘             │
 │                                                            ▼                             │
 │                                            ┌───────────────────────────────┐             │
 │                                            │  Model Registry (Sec 66)      │◄───or import│
 │                                            └───────────────┬───────────────┘ Model Garden│
 │                                                            │             model (Sec 67)  │
 │                              ┌─────────────────────────────┴─────────────┐               │
 │                              ▼                                           ▼               │
 │                    ┌──────────────────────┐                    ┌───────────────────────┐ │
 │                    │ Online/Batch         │                    │  Gemini + Vertex AI   │ │
 │                    │Endpoint (Sec 66),    │                    │  Studio + Grounding   │ │
 │                    │predict-only IAM      │                    │(Sec 68, generative AI)| │
 │                    │(Sec 70), Explainable │                    └───────────────────────┘ │
 │                    │AI attached (Sec 70)  │                                              │
 │                    └───────────┬──────────┘                                              │
 │                                ▼                                                         │
 │                    ┌──────────────────┐                                                  │
 │                    │ Model Monitoring │── drift/skew alert ──►Eventarc──►retrain trigger │
 │                    │ (Sec 69)         │  (loops back to the Pipeline step above)         │
 │                    └──────────────────┘                                                  │
 │                                                                                          │
 └──────────────────────────────────────────────────────────────────────────────────────────┘
```

> 🔑 **The single repeated principle across Part 10:** every path through Vertex AI — whether a model arrives via AutoML, custom training, or Model Garden, and whether it's consumed as a classic prediction endpoint or a generative AI call — converges on the same shared infrastructure: one Model Registry, one Endpoint/serving layer, one Monitoring and Experiments backbone, and one IAM/VPC-SC security perimeter. Vertex AI's core value proposition, established in Section 65 as solving GCP's historical ML tooling fragmentation, is proven out by every subsequent section in this Part: the _how you got a model_ varies, but the _how it's registered, served, monitored, and secured_ does not.

## 71.4 Cross-Section Decision Framework

| Question                                                                                           | Answer                                                                                                           |
| -------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| Standard classification/regression problem, no ML engineers on the team?                           | AutoML (Section 67) against a labeled Vertex AI Dataset — no training code required                              |
| Need a novel architecture or highly specialized modeling approach?                                 | Custom Training Job (Section 66), with Hyperparameter Tuning to search the parameter space systematically        |
| Need a chatbot or generative text/image feature, no training data of your own to train from?       | Model Garden (Section 67) + Gemini API, prototyped in Vertex AI Studio (Section 68)                              |
| Generative AI answers must reflect current company-specific documents, not just general knowledge? | Grounding with enterprise data via Vertex AI Search / RAG (Section 68.3.4), not fine-tuning                      |
| Need the model to trigger a real action (check an order, book something)?                          | Function calling / tool use (Section 68.3.5) — the app executes the function, the model only requests it         |
| Need to know if a deployed model is quietly getting worse?                                         | Vertex AI Model Monitoring for skew/drift (Section 69), alerting via Eventarc into an automated retrain pipeline |
| Need to justify why a specific model configuration was chosen?                                     | Vertex AI Experiments (Section 69) plus ML Metadata lineage (Section 66)                                         |
| A regulator asks why a specific prediction/decision was made?                                      | Vertex AI Explainable AI feature attribution (Section 70.3.4), retained alongside prediction logs                |
| Need to stop training data or model artifacts leaving the org even with valid IAM access?          | VPC Service Controls perimeter around Vertex AI, BigQuery, and Cloud Storage together (Section 70.3.2)           |
| Production identity only needs to call an endpoint's prediction API?                               | Narrow custom predict-only IAM role, never `roles/aiplatform.user`/`admin` (Section 70.3.1)                      |

## 71.5 Common Mistakes Spanning This Part

- Defaulting to custom training for well-understood problem types where AutoML would produce a comparable model faster and with less engineering overhead (Section 67).
- Treating Vertex AI Studio as a production runtime rather than a prompt design environment whose finalized prompts get exported into application code (Section 68.7).
- Assuming grounding eliminates hallucination entirely rather than substantially reducing it while still requiring citation review for high-stakes answers (Section 68.8).
- Believing the model itself executes function calls, rather than understanding the calling application executes the function and returns the result to the model (Section 68.8).
- Confusing training-serving skew (vs. training data) with prediction drift (vs. earlier live traffic) — they point to different root causes and different fixes (Section 69.8).
- Granting broad `aiplatform.user`/`admin` IAM roles to production serving identities that only need to call an endpoint's prediction API (Section 70.3.1).
- Relying on IAM alone to prevent data exfiltration, without a VPC Service Controls perimeter, which blocks unauthorized data movement even for principals with valid IAM permissions (Section 70.8).
- Treating a pre-launch fairness/bias evaluation as a one-time compliance checkbox rather than an ongoing practice tied into MLOps drift monitoring (Section 70.8).

## 71.6 Part 10 Interview Drill

### 🎯 Beginner Tier

**Q1:** What problem did Vertex AI solve that existed on GCP before it launched?
**A:** Before Vertex AI, GCP's ML tooling was fragmented — AI Platform handled custom training, while AutoML Tables/Vision/Natural Language/Video were separate products with their own consoles, APIs, and IAM/quota systems. Vertex AI (launched 2021) consolidated all of this under one API, one SDK (`google-cloud-aiplatform`), one console, and one consistent IAM/networking model (Section 65).

**Q2:** What's the difference between an Online Endpoint and Batch Prediction?
**A:** An Online Endpoint keeps compute persistently deployed and autoscaled to serve low-latency, on-demand individual requests (e.g., a live fraud-risk check). Batch Prediction provisions transient compute for a large-volume, non-latency-sensitive job (e.g., scoring an entire customer table nightly) and tears the compute down afterward, so cost is tied to job duration rather than continuous uptime (Section 66).

**Q3:** What is the difference between AutoML and Model Garden?
**A:** AutoML trains a new model from your own labeled dataset with no training code. Model Garden is a catalog of already-trained models (Gemini, partner models, open models) you deploy or call directly — there's no training step involved, since you're consuming an existing model rather than creating a new one (Section 67).

### 🎯 Intermediate Tier

**Q4:** How does grounding with Vertex AI Search actually work, end to end?
**A:** Documents from an organization's own data sources are ingested, chunked, embedded, and indexed by Vertex AI Search ahead of time. At query time, a user's question retrieves the most relevant chunks from that index; those chunks are inserted into the Gemini prompt as context alongside the question; Gemini generates a response grounded in the retrieved content, and the API response includes citation metadata tracing the answer back to specific source documents (Section 68.3.4).

**Q5:** Why does Vertex AI Pipelines' use of Kubeflow Pipelines matter compared to SageMaker Pipelines or Azure ML Pipelines?
**A:** Kubeflow Pipelines is open-source, so a pipeline definition written against the KFP SDK is portable to any KFP-compatible runner, not locked to Vertex AI specifically — unlike SageMaker's and Azure ML's proprietary, cloud-native pipeline DAG systems. This is frequently cited as reducing platform lock-in risk, though the underlying execution environment (Vertex AI managed compute) is still GCP-specific (Section 66.4).

**Q6:** How do Model Monitoring and Vertex AI Experiments serve different purposes in the ML lifecycle?
**A:** Model Monitoring watches a deployed endpoint's _live_ prediction traffic for statistical skew (vs. training data) or drift (vs. earlier live traffic), catching post-deployment degradation. Vertex AI Experiments tracks _training-time_ runs — parameters, metrics, artifacts — for comparison and reproducibility before deployment. One protects a model already in production; the other makes the process of arriving at that model reproducible and auditable (Section 69).

### 🎯 Senior/Architect Tier

**Q7:** Design a production system where a generative AI customer-support chatbot must answer from company documentation, check live order status, never leak documentation content outside the org, and automatically alert the team if answer quality degrades over time. Walk through how Sections 65–70 combine.
**A:** Documentation lives as a Vertex AI Search index (Section 68.3.4) used for grounding, sitting inside the same VPC Service Controls perimeter (Section 70.3.2) as the rest of the org's sensitive Vertex AI resources, so indexed documentation content cannot be exfiltrated outside the perimeter even by a principal with valid IAM access. The chatbot calls Gemini (Section 68) with grounding enabled for documentation questions and a function-calling tool definition (Section 68.3.5) for live order-status lookups — the application, not the model, executes the actual order-status API call and returns the result for the model to incorporate. IAM for the chatbot's service account is scoped narrowly to only the grounding data store and the specific internal API it needs (Section 70.3.1), never broad `aiplatform.user` access. For quality degradation, I don't have ground-truth labels for generative answers the way I would for a classification model, so I'd monitor proxy signals — response length/latency anomalies, escalation-to-human rate, thumbs-down feedback rate — as a custom monitoring signal feeding the same Eventarc-triggered alerting pattern Model Monitoring uses for classic models (Section 69), routing sustained quality drops to the team for prompt/grounding-source review, since generative AI quality degradation is more often a documentation-staleness or prompt problem than a model-drift problem in the classic sense.

**Q8:** Six months after launching a Vertex AI-based credit risk model, an audit finds: the model was trained via a manual notebook run with no pipeline or experiment tracking, the serving service account has `roles/aiplatform.admin`, and no monitoring or explainability is configured on the production endpoint. What does this pattern indicate, and how do you remediate it, in order of priority?
**A:** This is a system that reached production without any of Part 10's MLOps or governance layers ever being applied — it was trained and deployed as if it were a one-off notebook experiment rather than a production financial-decision system. I'd prioritize by risk: first, the `aiplatform.admin` serving service account is the most acute security exposure — a compromised serving credential could currently modify or delete production models and pipelines, not just request predictions — so I'd immediately replace it with a narrow, predict-only custom role (Section 70.3.1). Second, since this is a credit decision with real regulatory exposure, I'd enable Vertex AI Explainable AI on the endpoint immediately (Section 70.3.4) so every subsequent prediction has a retained feature-attribution record, even before anything else is fixed, closing the audit gap for new decisions going forward. Third, I'd stand up Model Monitoring on the endpoint (Section 69.3.1) to start catching skew/drift now, rather than waiting for the full pipeline rebuild. Finally, and in parallel, I'd rebuild the training process itself as a proper CI/CD-deployed Vertex AI Pipeline (Section 66, Section 69.3.3) with every run logged to Experiments and ML Metadata, so future retraining has the reproducibility and lineage the original manual notebook run never had, and going forward, no new model can be promoted to production without passing through this pipeline and its evaluation gate. This sequencing fixes the most exploitable/least-defensible gap first (broad IAM) while getting explainability and monitoring live quickly, then addresses the deeper structural gap (no pipeline, no lineage) as the sustained fix.

## 71.7 Key Takeaways — Part 10 Overall

- 🔑 Vertex AI unifies GCP's ML platform under one API/SDK/IAM model, and every model — however it's produced (AutoML, custom training, or Model Garden) — converges on the same Model Registry, Endpoint, Monitoring, and security infrastructure (Sections 65–67).
- 🔑 Generative AI on Vertex AI (Gemini, Vertex AI Studio, grounding, function calling) is built on the same underlying platform as classic ML, with grounding via Vertex AI Search as GCP's answer to enterprise RAG (Section 68).
- 🔑 MLOps closes the loop after deployment: Model Monitoring catches skew/drift, Experiments makes training reproducible and comparable, and CI/CD applies the same delivery discipline to pipelines that DevOps applies to application code (Section 69).
- 🔑 AI/ML security layers IAM least-privilege with VPC Service Controls (data cannot move across the perimeter even with valid IAM access), and Responsible AI — fairness, safety, explainability — is an ongoing operational practice, not a one-time launch gate (Section 70).
- 🔑 Across the entire Part, the recurring theme is convergence: different paths to a model, one shared, governed serving and monitoring backbone underneath all of them.

## 71.8 Transition to Part 11

Part 10 covered how GCP builds, deploys, and governs machine learning and generative AI systems. Part 11 shifts from building AI/ML systems to defending the organization running them — **Security Operations & Incident Response**, starting with **Section 72: Chronicle SIEM Fundamentals**, GCP's cloud-native security information and event management platform. This connects directly back to material already introduced: the dedicated security project pattern from Section 61 that feeds Chronicle, Security Command Center from Section 39 whose findings flow into Chronicle detections, and the AI/ML resources secured in Section 70 that Chronicle-fed detection and response coverage will extend to at the organization-wide security-operations level.

## 71.9 Related Concepts

Vertex AI Fundamentals (Section 65), Vertex AI Deep Dive (Section 66), AutoML & Model Garden (Section 67), Generative AI on GCP (Section 68), MLOps on GCP (Section 69), and AI/ML Security & Responsible AI (Section 70) — the full set this section synthesizes — along with VPC Service Controls (Section 41), Security Command Center (Section 39), the dedicated security project pattern (Section 61), and Chronicle SIEM Fundamentals (Section 72, next) which Part 11 begins with.
