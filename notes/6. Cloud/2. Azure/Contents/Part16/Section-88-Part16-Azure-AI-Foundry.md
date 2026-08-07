# Section 88 — Azure AI Foundry

## 1. Definition

**Plain language:** Azure OpenAI Service ([Section 87](./Section-87-Part16-Azure-OpenAI-Service.md)) gives you raw access to a model deployment — you send a prompt, you get a completion. But real generative AI applications are rarely a single prompt-response call: they need to pull in relevant enterprise data before asking the model a question, chain several model calls and tool invocations together, choose between many possible underlying models (not just OpenAI's), and manage all of this as a coherent, versioned application rather than a pile of ad-hoc API calls. Azure AI Foundry is Microsoft's platform for building exactly that — a layer above raw model access that provides orchestration, grounding, and a broader model catalog.

**Precise definition:** **Azure AI Foundry** (the current name for what was previously branded **Azure AI Studio**) is Microsoft's unified platform for developing generative AI applications — providing a **model catalog** (OpenAI models alongside open-source and third-party models from providers like Meta, Mistral, and others), **prompt flow** for visually/programmatically orchestrating multi-step LLM workflows, first-class support for building **agents** (LLM-driven systems that can invoke tools and take multi-step actions), and integrated patterns for **Retrieval-Augmented Generation (RAG)** grounding model responses in an organization's own data sources.

⚠️ Azure AI Foundry is one of the fastest-moving product areas in this entire KB — it was rebranded from Azure AI Studio, and its constituent features (agent service specifics, prompt flow's exact tooling, model catalog breadth) have changed substantially across recent product iterations. Treat every specific feature name, UI description, and capability claim in this section as directionally correct but subject to verification against current official Microsoft documentation before being used to make a real architectural decision or represented in an interview as current fact.

## 2. Why It Exists / Problem It Solves

[Section 87](./Section-87-Part16-Azure-OpenAI-Service.md) established that Azure OpenAI gives raw, direct access to individual model deployments — sufficient for a simple single-call application, but insufficient the moment an application needs to: choose from a broader range of models than just OpenAI's (perhaps a smaller, cheaper open-source model is sufficient for a simpler sub-task, reserving a larger model for genuinely complex reasoning), ground responses in proprietary enterprise data the model was never trained on (an internal knowledge base, a product catalog, historical support tickets), or chain multiple steps together (retrieve context, then reason over it, then optionally call an external tool, then format a final response) rather than a single prompt-response round trip. Azure AI Foundry exists to provide this missing orchestration and grounding layer, the same way Data Factory ([Section 77](../Part15/Section-77-Part15-Azure-Data-Factory.md)) provides an orchestration layer above raw data-movement primitives, or the same way AML Pipelines ([Section 85](./Section-85-Part16-Azure-ML-Deep-Dive.md).5) provide an orchestration layer above individual training jobs — a purpose-built layer for chaining and governing multi-step AI workflows rather than every team hand-rolling their own orchestration code around raw API calls.

## 3. Model Catalog

**Definition:** The **model catalog** within Azure AI Foundry is a curated collection of models available for deployment — spanning Azure OpenAI's own models, open-source models (from providers like Meta's Llama family, Mistral, and others), and other specialized models (for vision, speech, or domain-specific tasks) — letting an application choose the model best suited to a specific task's cost, latency, and capability requirements rather than defaulting to the largest, most expensive model for every task regardless of fit.

**Why this matters architecturally:** not every step in an AI application needs a frontier-class, expensive model — a classification or extraction sub-task within a larger workflow might be handled adequately (and far more cheaply and quickly) by a smaller open-source model from the catalog, reserving an expensive, high-capability model call for the specific step in the workflow that genuinely requires deep reasoning. This mirrors the broader engineering principle (seen elsewhere in this KB, like choosing appropriately-sized VM SKUs in Part 3) of matching resource cost to actual task requirements rather than over-provisioning uniformly.

## 4. Retrieval-Augmented Generation (RAG)

### 4.1 The Core Pattern

**Definition:** **Retrieval-Augmented Generation** is a pattern where, instead of relying solely on a language model's training-time knowledge, an application first **retrieves** relevant content from an external data source at request time (based on the user's query), then **augments** the prompt sent to the model with that retrieved content as additional context, so the model's response is **grounded** in specific, current, organization-owned information rather than only its general pretrained knowledge.

**How it works conceptually:** a user's query is converted into an embedding vector ([Section 87](./Section-87-Part16-Azure-OpenAI-Service.md).5.2), that vector is used to search a vector-indexed corpus of enterprise documents for the most semantically similar content, the top-matching document excerpts are inserted into the prompt alongside the user's original question, and the model is instructed (via the system message) to answer based primarily on the provided context — reducing hallucination risk and enabling the model to answer questions about proprietary data it was never trained on, without needing to fine-tune the model itself.

### 4.2 Grounding with Azure Cognitive Search

RAG's retrieval step is most commonly implemented using **Azure AI Search** (Cognitive Search, [Section 80](../Part15/Section-80-Part15-Azure-Cognitive-Search.md)) as the vector/hybrid search index — documents are chunked, embedded (via the Azure OpenAI embeddings API, [Section 87](./Section-87-Part16-Azure-OpenAI-Service.md).5.2), and indexed into a Cognitive Search index supporting vector similarity search (and, in hybrid configurations, combining vector similarity with traditional keyword/BM25 search for more robust retrieval than either approach alone). Azure AI Foundry provides built-in tooling ("Add your data" / grounding data connections in the Foundry portal, and corresponding SDK support) to wire an Azure OpenAI chat model directly to a Cognitive Search index for this pattern without hand-building the entire retrieval pipeline from scratch.

### 4.3 Sourcing Data for RAG — ADLS Gen2 and the Part 15 Pipeline

The documents that get chunked, embedded, and indexed for RAG typically originate from the same data engineering stack covered in Part 15 — raw documents landing in ADLS Gen2 ([Section 75](../Part15/Section-75-Part15-Data-Lake-Fundamentals-ADLS-Gen2.md)), potentially processed or extracted via Data Factory ([Section 77](../Part15/Section-77-Part15-Azure-Data-Factory.md)) or Databricks ([Section 78](../Part15/Section-78-Part15-Azure-Databricks.md)) pipelines before being chunked and embedded, then indexed into Cognitive Search. This means a production RAG pipeline is genuinely an extension of the data engineering architecture from Part 15, not an isolated AI-only concern — data freshness, quality, and governance considerations that applied to that pipeline ([Section 82](../Part15/Section-82-Part15-Data-Architecture-Patterns.md)) apply equally to whatever ends up grounding a generative AI application's responses, since a RAG system is only as trustworthy as the data it retrieves from.

## 5. Agents

**Definition:** An **agent**, in the Azure AI Foundry sense, is an LLM-driven system capable of reasoning about a task, deciding which of a set of available **tools** (function calls, API invocations, code execution, retrieval against a knowledge source) to invoke, executing those tool calls, observing the results, and iterating — potentially across multiple steps — toward completing a task, rather than producing a single one-shot response to a single prompt.

**How it works conceptually:** rather than a developer hand-coding every branch of "if the user asks X, call this API; if they ask Y, call that other API," an agent is given a description of available tools (their names, purposes, and expected inputs/outputs) and lets the underlying model itself decide, at each step, whether to respond directly or invoke a tool — the model effectively plans its own execution path within the bounds of the tools it's been given, which is powerful but also introduces its own security considerations ([Section 89](./Section-89-Part16-AIML-Security-Responsible-AI-Governance.md)) since the model's own judgment, not fully deterministic code, is deciding what actions to take.

🎯 **Interview Tip:** A frequently tested nuance: agents are not magic — they're built on the same chat completions mechanism from [Section 87](./Section-87-Part16-Azure-OpenAI-Service.md).5.1, using a specific capability (function/tool calling) where the model returns a structured request to invoke a named tool rather than a plain text response, and the calling application is responsible for actually executing that tool call and feeding the result back to the model in a subsequent turn. The orchestration loop (call model → check for tool call → execute tool → feed result back → repeat) is application-level logic that Azure AI Foundry's agent service manages on your behalf, not an inherent capability of the underlying model in isolation.

## 6. Prompt Flow

**Definition:** **Prompt Flow** is Azure AI Foundry's tool for designing, testing, and iterating on multi-step LLM workflows — visually or via code, representing a flow as a directed graph of nodes (prompt templates, Python code steps, retrieval steps, conditional branches) with defined inputs and outputs, letting a team version, test against a set of evaluation examples, and deploy the entire flow as a callable endpoint, rather than the orchestration logic living as scattered, untracked application code.

**Why this matters operationally:** this mirrors the AML Pipeline concept from [Section 85](./Section-85-Part16-Azure-ML-Deep-Dive.md).5 (and, further back, Data Factory pipelines from [Section 77](../Part15/Section-77-Part15-Azure-Data-Factory.md)) applied specifically to LLM workflows — a Prompt Flow definition is a reusable, testable, versioned artifact rather than an ad-hoc script, and Azure AI Foundry provides built-in evaluation tooling to systematically test a flow's outputs against a labeled evaluation set (for groundedness, relevance, and other LLM-specific quality metrics) before deploying a change to production.

## 7. Orchestration — Putting It Together

A realistic Azure AI Foundry application composes the pieces above: an agent ([Section 88](./Section-88-Part16-Azure-AI-Foundry.md).5) reasons about a user's request, decides to invoke a retrieval tool grounded in a Cognitive Search index ([Section 88](./Section-88-Part16-Azure-AI-Foundry.md).4.2) built from Part 15's data pipeline, feeds the retrieved context plus the user's question into a chat completion ([Section 87](./Section-87-Part16-Azure-OpenAI-Service.md).5.1) against a model chosen from the catalog ([Section 88](./Section-88-Part16-Azure-AI-Foundry.md).3) appropriate for the task's complexity, and the whole multi-step flow is defined, versioned, and evaluated as a Prompt Flow ([Section 88](./Section-88-Part16-Azure-AI-Foundry.md).6) rather than scattered imperative code.

## 8. Architecture Diagram

```
User Query
    │
    ▼
Azure AI Foundry Project
    │
    ├── Agent (reasons, decides which tool to invoke)
    │       │
    │       ├──► Tool: Retrieval against Azure AI Search index (Section 80)
    │       │            │
    │       │            ▼
    │       │     Vector index built from:
    │       │     ADLS Gen2 (Section 75) ──► chunked/embedded documents
    │       │            (via Part 15 pipeline: Data Factory/Databricks)
    │       │
    │       └──► Tool: external API / function call
    │
    ├── Retrieved context + user query ──► Chat Completion
    │                                          │
    │                                          ▼
    │                                Model Catalog selection
    │                                (Azure OpenAI GPT-class, or
    │                                 open-source model, per task fit)
    │
    └── Entire flow defined/versioned as Prompt Flow, evaluated
        against test set before deployment
                    │
                    ▼
              Response to User
```

## 9. Configuration & Hands-On Example

**Conceptual Python SDK pattern for a RAG call grounding an Azure OpenAI chat completion in an Azure AI Search index (via the Foundry-supported "on your data" extension):**

```python
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from openai import AzureOpenAI

token_provider = get_bearer_token_provider(
    DefaultAzureCredential(), "https://cognitiveservices.azure.com/.default"
)
client = AzureOpenAI(
    azure_endpoint="https://aoai-project.openai.azure.com/",
    azure_ad_token_provider=token_provider,
    api_version="2024-06-01",
)

response = client.chat.completions.create(
    model="gpt-chat-prod",
    messages=[
        {"role": "system", "content": "Answer only using the retrieved context. If the context doesn't contain the answer, say so."},
        {"role": "user", "content": "What is our current parental leave policy?"},
    ],
    extra_body={
        "data_sources": [{
            "type": "azure_search",
            "parameters": {
                "endpoint": "https://search-project.search.windows.net",
                "index_name": "hr-policies-index",
                "authentication": {"type": "system_assigned_managed_identity"},
            },
        }]
    },
)
print(response.choices[0].message.content)
```

- **Purpose:** Demonstrates the RAG grounding pattern from [Section 88](./Section-88-Part16-Azure-AI-Foundry.md).4 using Azure OpenAI's built-in "on your data" integration with Azure AI Search, rather than manually implementing the retrieve-then-augment steps in application code.
- **Important arguments explained individually:**
  - `extra_body.data_sources` — instructs the service to first query the specified Azure AI Search index for content relevant to the user's message, then automatically inject the retrieved excerpts into the model's context before generating a response — this is the managed version of the manual "embed query, search index, inject context" pipeline described conceptually in [Section 88](./Section-88-Part16-Azure-AI-Foundry.md).4.1.
  - `authentication.type: system_assigned_managed_identity` — the Azure OpenAI resource authenticates to the Azure AI Search resource using its own Managed Identity ([Section 9](../Part2/Section-09-Part2-Managed-Identities-and-Service-Principals.md)) rather than an API key, consistent with the identity-first access pattern established throughout this KB.
  - The system message explicitly instructing the model to only answer from retrieved context — a critical prompt-design practice reducing (though not eliminating) hallucination risk, since without this instruction the model may blend retrieved facts with unrelated pretrained knowledge in ways that are hard to distinguish.
- **Common error:** Failing to explicitly instruct the model (via the system message) to constrain its answer to the retrieved context often results in responses that mix accurate retrieved facts with plausible-sounding but ungrounded pretrained knowledge — a subtle failure mode that's easy to miss during casual testing but significant in a compliance-sensitive application like HR policy Q&A.

## 10. Production & Enterprise Usage

Enterprises building production generative AI applications typically stand up dedicated Azure AI Foundry projects per application (or business domain), with RAG grounding data sourced from governed, access-controlled indexes built from the same data engineering pipeline (Part 15) already trusted for other analytics, rather than a separately-maintained, ungoverned document store built solely for the AI application. Prompt Flow definitions are version-controlled (often in the same repositories managed via Part 9's CI/CD practices) and evaluated against a maintained test set before any change is promoted to production, catching regressions in groundedness or relevance the same way a code change is caught by automated tests. Agents deployed for internal or customer-facing use are typically scoped to a tightly-defined, reviewed set of tools rather than broad, unconstrained tool access, given the security considerations expanded on next in [Section 89](./Section-89-Part16-AIML-Security-Responsible-AI-Governance.md).

## 11. Security Considerations

- **RAG-specific data exfiltration risk** — if the retrieval layer (the Cognitive Search index) isn't filtered by the querying user's own authorization (e.g., document-level security trimming), a RAG application risks surfacing content the requesting user shouldn't have access to, purely because it was semantically relevant to their query — retrieval-time authorization filtering (matching the underlying data source's own access controls) is essential, not optional, and cannot be safely deferred to "the model will use good judgment."
- **Agent tool-scope risk** — because an agent's model decides which tools to invoke based on its own reasoning, granting it access to broad, high-impact tools (e.g., a tool that can delete records or send emails) without strict guardrails risks the model invoking that tool in an unintended or manipulated way (following a prompt injection, [Section 87](./Section-87-Part16-Azure-OpenAI-Service.md).10) — production agent deployments should scope available tools as narrowly as the task genuinely requires, and consider requiring human confirmation for high-impact tool invocations.
- **Data residency for grounding data** — RAG pipelines that embed and index enterprise data should respect the same data residency and access-control requirements that applied to that data in its original source (ADLS Gen2, Part 15), since embedding and indexing effectively creates a second copy of that data's information content in the search index, subject to the same governance obligations as the original.
- Managed Identity-based authentication between Azure AI Foundry, Azure OpenAI, and Azure AI Search components (as shown in [Section 88](./Section-88-Part16-Azure-AI-Foundry.md).9) avoids proliferating static API keys across an increasingly multi-component AI application stack.

## 12. Performance Considerations

RAG pipeline latency is additive — retrieval (the Cognitive Search query) happens before the model call, so end-to-end response latency is retrieval latency plus generation latency, not just generation latency alone; poorly-tuned search indexes or excessively large retrieved-context windows both directly increase user-perceived response time. Agent-based workflows involving multiple sequential tool calls compound this further, since each tool invocation and subsequent model reasoning step adds latency serially — production agent design should balance genuinely useful multi-step reasoning against runaway latency from an agent taking an excessive number of steps to complete a simple task, sometimes bounded by an explicit maximum-steps limit.

## 13. Monitoring

Azure AI Foundry integrates with Application Insights ([Section 52](../Part10/Section-52-Part10-Application-Insights.md)) for tracing individual requests through a Prompt Flow or agent's multi-step execution, letting teams inspect exactly which retrieval results, tool calls, and intermediate model outputs led to a given final response — essential for debugging both incorrect answers and unexpected agent behavior, since a black-box "the model said X" observation alone is rarely enough to diagnose why. Built-in evaluation metrics (groundedness, relevance, coherence) can be tracked over time as a quality signal analogous to accuracy drift monitoring in classical ML ([Section 86](./Section-86-Part16-MLOps-on-Azure.md).3), flagging if a RAG application's answer quality degrades as underlying grounding data or model versions change.

## 14. Troubleshooting

| Symptom                                                                                | Likely Cause                                                                                                                                                            | Fix                                                                                                                                                   |
| -------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| RAG responses occasionally include information the user shouldn't have access to       | Retrieval index lacks document-level authorization filtering matching the underlying data source's access controls                                                      | Implement security trimming on the search index so retrieval itself is scoped to what the requesting user is authorized to see                        |
| RAG responses are fluent but factually wrong or inconsistent with the source documents | Retrieved context isn't sufficiently relevant (poor chunking/embedding strategy), or the system prompt doesn't constrain the model to answer only from provided context | Review document chunking strategy and retrieval relevance; strengthen system prompt instructions to answer only from retrieved context                |
| Agent takes an excessive number of steps or loops without completing the task          | No maximum-step bound configured, or the agent's available tool set is ambiguous/overlapping, causing indecisive tool selection                                         | Configure an explicit maximum-steps limit; clarify and narrow the tool set's descriptions to reduce ambiguity in the model's tool-selection reasoning |

## 15. Interview Questions — [Section 88](./Section-88-Part16-Azure-AI-Foundry.md)

### 🎯 Intermediate

**Q: Explain the RAG (Retrieval-Augmented Generation) pattern and why grounding matters for enterprise generative AI applications.**

_Model answer:_ RAG retrieves relevant content from an external data source at request time — typically via a vector similarity search over embedded documents indexed in Azure AI Search — and injects that retrieved content into the prompt sent to the language model, so the model's response is grounded in specific, current, organization-owned data rather than relying solely on whatever general knowledge it acquired during training. This matters for enterprise applications because it lets the model answer questions about proprietary, frequently-changing, or otherwise non-public information (internal policies, product catalogs, support history) without needing to fine-tune the model itself, and it materially reduces hallucination risk by anchoring responses in retrieved, verifiable source content rather than the model's unconstrained pretrained knowledge.

_What the interviewer is probing:_ whether the candidate understands RAG as a genuine architectural pattern (retrieval plus augmentation, with a specific mechanism — embeddings and vector search) rather than a vague buzzword, and whether they connect it correctly to reducing hallucination and enabling proprietary-data grounding.

### 🎯 Senior/Architect

**Q: Design a RAG-based internal HR chatbot on Azure AI Foundry that must never reveal HR policy details a specific employee isn't entitled to see (e.g., executive-only compensation policies), and explain how you'd prevent that from happening.**

_Model answer:_ The critical design decision is that authorization must be enforced at the retrieval layer, not left to the language model's judgment. I'd implement document-level security trimming on the Azure AI Search index backing this chatbot, so that when an employee's query triggers a retrieval, the search itself is scoped (via the employee's Entra ID group memberships or role claims) to only the subset of indexed HR documents that employee is actually authorized to see — meaning an executive-only compensation document would never even be returned as a retrieval candidate for a non-executive employee's query, regardless of how the model might otherwise handle it. I would not rely on instructing the model, via the system prompt, to withhold information it technically has access to in its context window, since prompt-based restrictions can potentially be circumvented via prompt injection and shouldn't be treated as a genuine authorization boundary. I'd source the underlying HR policy documents from a governed ADLS Gen2 location ([Section 75](../Part15/Section-75-Part15-Data-Lake-Fundamentals-ADLS-Gen2.md)) with the same access control tagging used for the source documents, propagated through the Part 15 ingestion pipeline into the search index's document-level permissions metadata. I'd also enable Azure OpenAI's built-in content filtering and add application-level logging (via Application Insights) of retrieved documents per query, so any suspected authorization leak could be audited after the fact by reviewing exactly what was retrieved and surfaced for a given user's session.

_What the interviewer is probing:_ whether the candidate recognizes that an LLM cannot be treated as a reliable authorization boundary and correctly places access control at the retrieval/data layer instead — a genuinely important and frequently-missed architectural distinction in real RAG deployments, versus a superficial "the AI will know not to share that" answer.

## 16. Common Misconceptions

- **"RAG means fine-tuning the model on your company's documents."** False — RAG retrieves and injects relevant content into the prompt at request time; it doesn't alter the model's underlying weights at all, and is a fundamentally different (and typically far cheaper and faster to update) approach than fine-tuning.
- **"An agent can be trusted to withhold information a user isn't authorized to see, as long as it's instructed to."** False — authorization must be enforced at the retrieval/data layer; instructing a model not to reveal certain information is not a reliable security boundary against a determined or accidental prompt injection.
- **"Azure AI Foundry and Azure OpenAI Service are the same thing."** False — Azure OpenAI Service provides raw model deployment access ([Section 87](./Section-87-Part16-Azure-OpenAI-Service.md)); Azure AI Foundry is the broader orchestration, agent, model-catalog, and RAG-tooling platform built on top of (and alongside) Azure OpenAI and other model providers.

## 17. Key Takeaways

- 🔑 Azure AI Foundry (formerly Azure AI Studio) is the orchestration and grounding layer above raw model access — providing a model catalog beyond just OpenAI models, RAG tooling, agents, and Prompt Flow.
- 🔑 RAG grounds model responses in retrieved, organization-owned content via embeddings and vector search (commonly against an Azure AI Search index), reducing hallucination without requiring model fine-tuning.
- 🔑 RAG grounding data typically originates from the Part 15 data engineering pipeline (ADLS Gen2, Data Factory, Databricks) — a production RAG system is an extension of that data architecture, not an isolated AI concern.
- 🔑 Agents use the model's own reasoning (via tool/function calling) to decide which available tools to invoke across multiple steps — powerful, but requiring careful tool-scoping and guardrails given the model's judgment, not fully deterministic code, drives the decision.
- 🔑 Authorization for RAG-retrieved content must be enforced at the retrieval/data layer via security trimming, never left to the model's own judgment about what it should or shouldn't reveal.
- 🔑 This entire product area evolves rapidly — verify specific Azure AI Foundry feature names and capabilities against current documentation before relying on them in a real design or interview answer.

## 18. Related Concepts (Next Up)

[Section 89](./Section-89-Part16-AIML-Security-Responsible-AI-Governance.md) turns from building generative AI applications to governing them responsibly at scale — AI/ML Security & Responsible AI Governance: content filtering in depth, prompt injection and jailbreak defenses, data residency and privacy considerations for RAG pipelines specifically, Microsoft's Responsible AI principles, and the access-control mechanisms (Managed Identity, Key Vault, Private Link) that tie every service covered across this Part into a single coherent security posture.
