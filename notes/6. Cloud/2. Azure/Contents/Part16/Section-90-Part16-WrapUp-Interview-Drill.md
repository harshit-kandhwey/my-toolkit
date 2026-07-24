# Section 90 — Part 16 Wrap-Up + AI/ML Interview Drill

## 90.1 Definition

**Plain language:** This section closes out Part 16 by tying the six preceding sections together into one coherent story — from training a classical model in Azure ML through to governing a generative AI application responsibly — and then drills the whole Part rapid-fire, the way an interviewer might jump between topics in a single conversation rather than staying neatly within one section.

**Precise definition:** This is the **synthesis and interview-drill section** for Part 16 — AI/ML & Generative AI on Azure, consolidating Sections 84-89 into a single end-to-end narrative and providing a rapid-fire question set spanning classical ML (Azure ML), MLOps, Azure OpenAI, Azure AI Foundry, and Responsible AI governance.

## 90.2 Why It Exists / Problem It Solves

Every Part in this KB that spans multiple sections ends with exactly this kind of synthesis, because real interviews and real architectural conversations rarely stay confined to one section's boundaries — an interviewer discussing a RAG application (Section 88) will naturally ask about the security implications (Section 89), and a question about MLOps (Section 86) may pivot into asking how it differs from CI/CD for a generative AI application (Sections 87-88). This section exists to rehearse exactly that kind of cross-cutting recall, and to make explicit the throughline connecting Part 16 back to the rest of the KB — Part 15's data engineering stack, Part 11's security patterns, Part 9's DevOps discipline, and Part 2's identity model — rather than leaving Part 16 as a set of six isolated topics.

## 90.3 The Part 16 Narrative, End to End

Azure's AI/ML story on Azure begins where Part 15 ends: clean, governed data sitting in ADLS Gen2, Synapse, or Databricks. **Section 84** introduced Azure Machine Learning's organizing model — the workspace as the central resource wiring together compute (Compute Instances for interactive work, Compute Clusters for auto-scaling job execution), datastores/data assets referencing that Part 15 data, and the Managed Identity-based access pattern threading through everything. **Section 85** went deeper into the actual training-and-serving lifecycle — Jobs and Experiments for tracked training runs, Sweep Jobs for automated hyperparameter search, AML Pipelines for chaining steps, the Model Registry for versioned, traceable models, and the choice between Managed Online Endpoints (real-time) and Batch Endpoints (asynchronous, high-volume) for serving. **Section 86** brought operational discipline to that lifecycle — data and concept drift monitoring catching silent model degradation, CI/CD via Azure DevOps or GitHub Actions (Part 9) automating retraining and deployment, the Responsible AI dashboard gating deployments on fairness alongside accuracy, and disciplined model versioning making rollback a traffic-routing decision rather than a retraining exercise.

The Part then pivoted from classical, predictive ML to generative AI. **Section 87** introduced Azure OpenAI Service as the same OpenAI models wrapped in Azure's identity, networking, and compliance envelope — model deployments with their own TPM quota, chat completions, and embeddings as the foundational APIs. **Section 88** built Azure AI Foundry's orchestration layer on top of that raw model access — a broader model catalog, RAG grounding responses in Part 15 data via Azure AI Search, agents reasoning about which tools to invoke, and Prompt Flow versioning multi-step LLM workflows the same way AML Pipelines version training workflows. **Section 89** closed the loop on security and governance — content filtering as an independent safety net, layered prompt injection defenses (spotlighting, tool scoping, retrieval-time authorization filtering), RAG-specific data residency obligations, and Microsoft's Responsible AI principles as the organizing framework tying every technical control back to a named, accountable governance process.

The throughline across all six sections is the same identity-first, defense-in-depth philosophy applied throughout this entire KB: Managed Identity by default (Section 9), Key Vault only where identity-based access genuinely can't reach (Section 56), Private Link for network isolation (Section 23.5), least-privilege RBAC (Section 8), and — specific to this Part — the recognition that a language model's own judgment is never a reliable security or authorization boundary on its own.

## 90.4 Architecture Diagram — Part 16 Synthesis

```
Part 15 Data Engineering (ADLS Gen2, Synapse, Data Factory, Databricks)
                    │
        ┌───────────┴───────────┐
        ▼                       ▼
  Classical ML Path        Generative AI Path
  (Sections 84-86)          (Sections 87-89)
        │                       │
  AML Workspace            Azure OpenAI Service
  Compute/Datastores       (model deployments, TPM quota)
        │                       │
  Jobs/Sweep/Pipelines     Azure AI Foundry
        │                  (model catalog, RAG, agents,
  Model Registry            Prompt Flow)
        │                       │
  MLOps: drift monitor,    Content filtering,
  CI/CD (Part 9),          prompt injection defenses,
  RAI dashboard gate       retrieval-time authZ
        │                       │
        └───────────┬───────────┘
                     ▼
     Identity-first security substrate (shared):
     Managed Identity (Section 9) · Key Vault (Section 56)
     Private Link (Section 23.5) · RBAC (Section 8)
     Microsoft Responsible AI principles (Section 89.6)
                     │
                     ▼
        Part 17 — Security Operations &
        Incident Response (Section 91+)
```

## 90.5 Part 16 Interview Drill

### 🎯 Drill 1 (Section 84 — AML Fundamentals)

**Q: Why can't training code just reference a storage account path directly instead of going through an AML datastore?**

_Model answer:_ It can, technically, but doing so embeds connection details directly into training code and forfeits the abstraction datastores provide — a stable, access-controlled, identity-authenticated reference that doesn't need to change if the underlying storage account or authentication approach changes, mirroring the same rationale for Data Factory Linked Services (Section 77).

### 🎯 Drill 2 (Section 85 — Training/Serving)

**Q: Why does a Sweep Job typically use Bayesian sampling over grid sampling for an expensive-to-train model?**

_Model answer:_ Bayesian sampling uses the results of prior runs to intelligently choose the next hyperparameter combination to try, generally converging on strong hyperparameters in fewer total runs than grid sampling's exhaustive combination search — valuable specifically when each individual training run is expensive, since the run budget itself becomes the limiting resource.

### 🎯 Drill 3 (Section 86 — MLOps)

**Q: A model's accuracy on live data has degraded, but no code has changed and no new data has been detected as drifting from the training baseline. What's the likely explanation?**

_Model answer:_ This points toward concept drift rather than data drift — the relationship between input features and the correct outcome has shifted even though the input feature distribution itself looks statistically similar to the training baseline; since concept drift requires ground-truth labels to detect and those often lag, this kind of degradation can be discovered well after it began.

### 🎯 Drill 4 (Section 87 — Azure OpenAI)

**Q: A developer ports code from the public OpenAI API to Azure OpenAI and gets a "deployment not found" error despite the model existing. Why?**

_Model answer:_ The `model` parameter in an Azure OpenAI API call must reference the **deployment name** configured within the Azure OpenAI resource, not the underlying base model name — a very common mistake when adapting code originally written against the public API, which takes the model name directly.

### 🎯 Drill 5 (Section 88 — Azure AI Foundry / RAG)

**Q: A RAG chatbot answers fluently but its answers sometimes blend accurate retrieved facts with plausible-sounding but incorrect pretrained knowledge. What's missing?**

_Model answer:_ Most likely the system prompt doesn't sufficiently constrain the model to answer only from the retrieved context — without an explicit instruction to that effect, the model can blend genuinely retrieved, grounded content with unrelated pretrained knowledge in a way that's difficult for a user to distinguish, undermining the whole point of grounding via RAG.

### 🎯 Drill 6 (Section 89 — Security/Governance)

**Q: What's the difference between direct and indirect prompt injection, and which is the bigger concern for a RAG application specifically?**

_Model answer:_ Direct prompt injection comes from the end user's own input attempting to override instructions; indirect prompt injection arrives via retrieved content (a poisoned document in the data source a RAG pipeline indexes) that the model can't reliably distinguish from trusted instructions. Indirect injection is the bigger, more distinctive concern for RAG applications specifically, since it doesn't require the attacker to interact with the application at all — only to get malicious content into whatever data source is being retrieved from.

### 🎯 Drill 7 (Cross-cutting — MLOps meets Responsible AI)

**Q: Why should a model promotion pipeline gate on both an accuracy threshold and a Responsible AI fairness check, rather than accuracy alone?**

_Model answer:_ A model can have strong aggregate accuracy while performing meaningfully worse for specific subgroups within that aggregate — an accuracy-only gate would pass such a model straight into production, so the Responsible AI dashboard's fairness/disparity analysis needs to be a distinct, additional gate rather than assumed to be captured implicitly by an overall accuracy number.

### 🎯 Drill 8 (Cross-cutting — Identity across the Part)

**Q: What's the one identity pattern that appears consistently across AML workspaces, Managed Online Endpoints, and Azure OpenAI/AI Search integrations?**

_Model answer:_ Managed Identity (Section 9) as the default authentication mechanism, with RBAC-scoped least-privilege roles granted to that identity on the specific resources it needs to access, and Key Vault reserved only for secrets that genuinely can't be replaced by identity-based access — the same identity-first philosophy applied consistently across every AI/ML component in this Part, not a special AI-specific access model.

## 90.6 Part 16 Common Misconceptions (Consolidated)

- **"AI/ML on Azure is just calling an API — there's no real architecture to it."** False — as this Part demonstrated across six sections, there's a full lifecycle (data, compute, training, tuning, versioning, deployment, monitoring) for classical ML, and a distinct but equally substantial orchestration/security stack (RAG, agents, content filtering, injection defenses) for generative AI.
- **"Azure OpenAI and Azure AI Foundry are interchangeable names for the same thing."** False — Azure OpenAI Service provides raw model deployment access (Section 87); Azure AI Foundry is the broader platform built on top, providing orchestration, a wider model catalog, RAG tooling, and agents (Section 88).
- **"Securing a generative AI application is fundamentally different from securing everything else in this KB."** False in the way it's usually meant — the specific risks (prompt injection, RAG data exfiltration) are new, but the underlying access-control substrate (Managed Identity, Key Vault, Private Link, RBAC) is the exact same identity-first model used everywhere else in this KB; what's genuinely new is layered on top, not built from scratch.

## 90.7 Part 16 Key Takeaways (Consolidated)

- 🔑 Azure ML (Sections 84-85) provides the full classical ML lifecycle — workspace, compute, data, training/tuning, registry, and both real-time and batch inference — on top of the data already staged by Part 15's engineering pipeline.
- 🔑 MLOps (Section 86) applies Part 9's CI/CD discipline plus ML-specific drift monitoring and Responsible AI fairness gating, making model promotion and rollback a disciplined, versioned process rather than an ad-hoc one.
- 🔑 Azure OpenAI Service (Section 87) is the same OpenAI models wrapped in Azure's enterprise identity, networking, and compliance envelope — accessed via named model deployments with their own TPM quota, not the base model name directly.
- 🔑 Azure AI Foundry (Section 88) is the orchestration and grounding layer above raw model access — RAG for grounding in enterprise data, agents for multi-step tool-driven reasoning, and Prompt Flow for versioned, testable workflow definitions.
- 🔑 AI/ML security (Section 89) layers content filtering, prompt injection defenses, and retrieval-time authorization on top of the same identity-first substrate (Managed Identity, Key Vault, Private Link, RBAC) used throughout this entire KB — an LLM's own judgment is never a reliable security boundary on its own.
- 🔑 Microsoft's Responsible AI principles (fairness, reliability and safety, privacy and security, inclusiveness, transparency, accountability) are the organizing framework tying every technical control in this Part back to named organizational accountability.

## 90.8 Related Concepts (Next Up — Part 17)

Part 16 closes the AI/ML and generative AI gap this KB previously had none of. The roadmap now moves to **Part 17 — Security Operations & Incident Response**, beginning at **Section 91** with **Microsoft Purview** (data governance and classification at enterprise scale — directly relevant to the RAG data-governance obligations just covered in Section 89.5), followed by **Section 92** (Microsoft Sentinel SIEM Fundamentals), **Section 93** (Sentinel Deep Dive), **Section 94** (Automated Incident Response), **Section 95** (SOC Patterns), and **Section 96** (Part 17 Wrap-Up) — shifting focus from building and governing AI systems to detecting, investigating, and responding to security incidents across the entire Azure estate this KB has covered, including the AI/ML workloads introduced in this Part.
