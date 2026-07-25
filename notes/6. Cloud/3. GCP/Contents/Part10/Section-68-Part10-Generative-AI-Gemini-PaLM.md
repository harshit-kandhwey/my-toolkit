# Section 68 (Part 10): Generative AI on GCP — Gemini, PaLM API & Vertex AI Studio

## 68.1 Definition

**Plain language:** Beyond training your own models, GCP lets you build applications directly on top of Google's own large language models — asking them questions, having them use your company's private documents to answer accurately, and letting them call your own APIs and databases as tools. This section covers how developers actually build generative AI features on GCP, rather than how models get trained.

**Precise:** **Gemini** is Google's multimodal large language model family (text, image, audio, video, code), accessible via the Vertex AI Gemini API. **Vertex AI Studio** is the console-based environment for prompt design, testing, and tuning against Gemini and other Model Garden (Section 67) models. **Grounding** connects model responses to Google Search or an organization's own enterprise data to reduce hallucination and cite sources, commonly implemented via **Vertex AI Search** for retrieval-augmented generation (RAG). **Function calling** lets a Gemini model invoke external tools/APIs as part of generating a response.

> 💡 **Note on PaLM:** PaLM 2 and the original PaLM API were Google's prior-generation large language model family and API, since superseded by Gemini as Google's flagship model line; PaLM API endpoints are in the process of being deprecated in favor of the Gemini API. This section is written against Gemini as the current, recommended model family, with PaLM referenced only where relevant for historical/migration context.

## 68.2 Why It Exists / Problem It Solves

- **Raw LLM output is not enough for enterprise use.** A model that only knows what it was trained on will hallucinate or give outdated answers about a specific company's products, policies, or internal data — grounding solves this by connecting the model to authoritative, current sources at answer time.
- **Prompt engineering benefits from a dedicated design environment.** Iterating on prompts by editing code and redeploying is slow; Vertex AI Studio provides an interactive playground to test prompt variations, compare model versions, and save prompts as reusable templates before they're wired into an application.
- **LLMs alone can't take action.** A model can describe what should happen ("check this customer's order status") but cannot itself query a database or call an API — function calling bridges this gap, letting the model decide when to invoke a defined tool and use its result in the response.
- **Building RAG from scratch is a significant undertaking.** Naively, retrieval-augmented generation requires a vector database, an embedding pipeline, chunking logic, and a retrieval-ranking layer — Vertex AI Search packages this as a managed capability so teams don't build and operate it themselves.

## 68.3 Core Concepts

### 68.3.1 Gemini Model Family

Gemini models are **multimodal** — a single model can accept and reason over combinations of text, images, audio, video, and code in one prompt, rather than requiring separate specialized models per modality. Gemini is offered in multiple size/capability tiers (e.g., a smaller, faster, cheaper tier optimized for high-volume/low-latency use cases, and a larger tier optimized for the most complex reasoning tasks), letting teams pick the right cost/latency/capability trade-off per use case rather than always paying for the largest model.

### 68.3.2 Vertex AI Studio

**Vertex AI Studio** is the console UI for:

- **Prompt design and testing** — iterating on prompt text, system instructions, and generation parameters (temperature, top-p, max output tokens) against live model responses.
- **Multimodal prompting** — attaching images, audio, or video directly in the testing interface.
- **Model comparison** — running the same prompt against multiple Gemini versions or Model Garden models side by side.
- **Saving and exporting** — a finalized prompt can be saved as a reusable template or exported as ready-to-run code (Python, `curl`, Node.js) to paste directly into an application.

### 68.3.3 Grounding

**Grounding** anchors model output to a verifiable source of truth rather than relying solely on the model's training data, addressing hallucination. Two primary grounding sources on Vertex AI:

- **Grounding with Google Search**: the model can incorporate current, public web information into its response (useful for questions about recent events or fast-changing public facts), with source citations returned alongside the answer.
- **Grounding with enterprise data**: the model retrieves relevant snippets from an organization's own private data (documents, websites, structured data) before answering, most commonly implemented through **Vertex AI Search** (below).

### 68.3.4 RAG with Vertex AI Search

**Vertex AI Search** is a managed search engine (built on the same technology underlying Google Search) that can be pointed at an organization's own data sources (Cloud Storage documents, BigQuery tables, website content) to power **retrieval-augmented generation (RAG)**:

1. Documents are ingested and automatically chunked, embedded, and indexed by Vertex AI Search.
2. At query time, a user's question retrieves the most relevant chunks from the indexed corpus.
3. Those chunks are inserted into the Gemini prompt as context, and the model generates an answer grounded in that retrieved content, with citations back to the source documents.

This pattern avoids the need to fine-tune a model on private data just to answer questions about it, and it keeps answers current as underlying documents change (since retrieval happens at query time, not training time).

### 68.3.5 Function Calling / Tool Use

**Function calling** lets a Gemini model be given a set of defined function signatures (name, description, parameters) as part of a request. Rather than the model executing anything itself, it returns a structured indication of which function to call and with what arguments; the calling application then executes the actual function (e.g., a database query, an internal API call) and returns the result to the model, which incorporates it into a final natural-language response. This is the mechanism behind agentic applications — a chatbot that can actually check an order status or book a meeting, not just describe how one might do so.

## 68.4 Comparison: Vertex AI Generative AI vs. AWS Bedrock vs. Azure OpenAI/AI Foundry

| Capability                      | GCP                          | AWS                                     | Azure                                 |
| ------------------------------- | ---------------------------- | --------------------------------------- | ------------------------------------- |
| Flagship first-party model      | Gemini                       | Amazon Nova / Titan                     | GPT (via OpenAI partnership)          |
| Prompt design environment       | Vertex AI Studio             | Bedrock Prompt Management / Playgrounds | Azure AI Foundry Playground           |
| Grounding with web search       | Grounding with Google Search | N/A (no native equivalent)              | Bing Search grounding                 |
| Enterprise RAG service          | Vertex AI Search             | Bedrock Knowledge Bases                 | Azure AI Search (as grounding source) |
| Function calling / tool use     | Gemini function calling      | Bedrock tool use / Agents for Bedrock   | Azure OpenAI function calling         |
| Multi-model catalog access      | Model Garden (Section 67)    | Bedrock model catalog                   | Azure AI Foundry model catalog        |
| Multimodal input (single model) | Native (Gemini)              | Varies by model                         | Varies by model (GPT-4o and later)    |

> ⚠️ **Interview-relevant nuance:** GCP's "Grounding with Google Search" is a genuine differentiator with no direct equivalent on AWS or Azure — it leverages Google's own search index directly, whereas AWS and Azure grounding patterns rely on either your own indexed data (Knowledge Bases / Azure AI Search) or a third-party search integration (Bing on Azure). This is a frequently asked "what's unique about Vertex AI" interview point.

## 68.5 Architecture Diagram: RAG Request Flow with Vertex AI Search

```
   User Question
        │
        ▼
 ┌─────────────────────┐      ┌────────────────────────┐
 │  Application        │─────►│  Vertex AI Search      │
 │  (calls Gemini API) │      │ (retrieves relevant    │
 └──────────┬──────────┘      │ chunks from indexed    │
            │                 │ enterprise documents)  │
            │                 └───────────┬────────────┘
            │                             │ relevant chunks
            │◄────────────────────────────┘
            ▼
 ┌───────────────────────────────────┐
 │  Gemini API call:                 │
 │  prompt = user question           │
 │           + retrieved chunks      │
 │           + (optional) tool defs  │
 └───────────────┬───────────────────┘
                 │
       ┌─────────┴──────────┐
       ▼                    ▼
 Direct answer          Function call requested
 (grounded, with        (app executes the function,
  citations)              returns result to model)
                                   │
                                   ▼
                          Final grounded answer
```

## 68.6 Hands-On Example

**Beginner example — call the Gemini API for a simple text generation:**

```python
import vertexai
from vertexai.generative_models import GenerativeModel

vertexai.init(project="my-gcp-project", location="us-central1")
model = GenerativeModel("gemini-2.0-flash")
response = model.generate_content("Summarize the key benefits of managed Kubernetes in two sentences.")
print(response.text)
```

**Purpose:** Sends a single prompt to Gemini and prints the generated text response.

**Expected output:**

```
Managed Kubernetes offloads control-plane operations like upgrades, patching,
and high availability to the cloud provider, letting teams focus on workloads
instead of cluster administration. It also typically integrates natively with
the provider's IAM, networking, and logging services, reducing setup overhead.
```

**Intermediate example — grounded RAG query against Vertex AI Search:**

```python
from vertexai.generative_models import GenerativeModel, Tool, grounding

model = GenerativeModel("gemini-2.0-flash")
tool = Tool.from_retrieval(
    grounding.Retrieval(
        grounding.VertexAISearch(datastore="projects/my-gcp-project/locations/global/dataStores/support-docs")
    )
)
response = model.generate_content(
    "What is our refund policy for enterprise customers?",
    tools=[tool],
)
print(response.text)
print(response.candidates[0].grounding_metadata)
```

**Purpose:** Answers a question grounded in the company's own indexed support documentation rather than the model's general training data, returning citation metadata alongside the answer.

**Expected output:**

```
Enterprise customers are eligible for a full refund within 30 days of purchase,
per the Enterprise Support Agreement (Section 4.2)...
grounding_metadata: { citations: [{ source: "support-docs/enterprise-agreement.pdf", ... }] }
```

**Function calling example — defining a tool the model can invoke:**

```bash
gcloud ai models predict gemini-2.0-flash \
  --region=us-central1 \
  --json-request=function_call_request.json
```

**Purpose:** Sends a request that includes a function declaration (e.g., `get_order_status(order_id)`), allowing Gemini to return a structured function-call intent instead of free text when the user's question requires live data.

**Expected output:**

```
{
  "functionCall": {
    "name": "get_order_status",
    "args": { "order_id": "ORD-48213" }
  }
}
```

## 68.7 Production & Enterprise Usage

- Enterprises use **Vertex AI Studio** during development for rapid prompt iteration, then export the finalized prompt into application code — Studio is a design tool, not typically the production runtime itself.
- **Grounding with enterprise data (Vertex AI Search)** is the standard production pattern for internal knowledge assistants, customer support chatbots, and document Q&A systems, since it avoids fine-tuning cost, keeps answers current as source documents change, and provides citations for auditability.
- **Function calling** underpins production agentic systems — e.g., a support chatbot that checks real order status via an internal API rather than only describing how a customer could check it themselves.
- Model tier selection (smaller/faster vs. larger/more capable Gemini variants) is treated as a per-feature cost/latency decision — high-volume, simple classification-style prompts route to a smaller tier, while complex multi-step reasoning tasks route to a larger tier, often within the same application.
- Generative AI endpoints sit behind the same IAM and VPC Service Controls perimeter (Section 41) as other Vertex AI resources, so enterprise data used for grounding never leaves the organization's security boundary.

## 68.8 Common Misconceptions

- **Misconception:** "Grounding eliminates hallucination completely." Grounding substantially reduces hallucination by anchoring answers to retrieved or searched content, but it does not guarantee zero incorrect output — the model can still misinterpret or partially misuse retrieved context. Citations returned alongside grounded answers exist precisely so a human or downstream system can verify the source.
- **Misconception:** "Function calling means the model executes code." The model only returns a structured request indicating which function to call and with what arguments — the calling application is responsible for actually executing that function and returning the result; the model itself never runs code or touches external systems directly.
- **Misconception:** "You should always use the largest, most capable Gemini model for best results." Larger models cost more and respond more slowly; many production use cases (simple classification, short-form extraction) perform just as well on a smaller, faster, cheaper tier, and using the largest model everywhere is a common and avoidable cost inefficiency.

## 68.9 Interview Questions

**🎯 Beginner:** _What is the difference between grounding with Google Search and grounding with enterprise data (Vertex AI Search)?_
**Model answer:** Grounding with Google Search connects the model's response to current, public web information, useful for questions about recent events or general public facts, with citations to public web sources. Grounding with enterprise data connects the response to an organization's own private, indexed documents via Vertex AI Search, useful for answering questions about company-specific information like internal policies or product documentation — something the public web and the model's training data would never contain. Both reduce hallucination by anchoring the response to a verifiable source and returning citations, but the source of truth is fundamentally different.

**🎯 Intermediate:** _Walk through what happens end to end when a user asks a grounded RAG question backed by Vertex AI Search._
**Model answer:** The application sends the user's question along with a reference to the configured Vertex AI Search data store as part of the Gemini API call. Vertex AI Search retrieves the most relevant chunks from its pre-indexed corpus of the organization's documents (which were chunked, embedded, and indexed ahead of time). Those retrieved chunks are inserted into the prompt as additional context alongside the original question. Gemini then generates a response using both its general language understanding and the retrieved context, and the API response includes grounding metadata — citations back to the specific source documents/chunks used — so the answer can be traced back to its source and verified.

**🎯 Senior/Architect:** _Design a customer-support chatbot for an enterprise SaaS company that must answer questions from the company's help documentation, check a live order/subscription status from an internal API, and never expose data outside the company's security boundary._
**Model answer:** I'd build this around three integrated pieces. First, for documentation Q&A, I'd index the company's help documentation into Vertex AI Search and use grounding with enterprise data so answers are anchored to current docs with citations rather than relying on the model's general training data, which would go stale as documentation changes. Second, for live subscription/order status, I'd define a function-calling tool (e.g., `get_subscription_status(customer_id)`) that the model can invoke when a user's question requires live data; my application backend executes the actual API call against the internal subscription system and returns the result to the model to incorporate into its response — the model itself never touches the internal API directly. Third, for the security boundary, I'd place both the Vertex AI Search data store and the Gemini API calls inside the organization's VPC Service Controls perimeter (Section 41), so enterprise documentation and any subscription data passed through the model never traverses outside the approved network boundary, and I'd scope IAM permissions narrowly so the chatbot's service account can only call the specific internal API and data store it needs, following least privilege (Section 35). I'd prototype the whole prompt/grounding/tool-definition combination in Vertex AI Studio before wiring it into the production application, and route to a smaller Gemini tier for straightforward FAQ-style questions while reserving a larger tier for multi-step troubleshooting conversations, to balance cost against response quality.

## 68.10 Key Takeaways

- 🔑 Gemini is Google's current multimodal flagship model family, offered in multiple size/capability tiers for different cost/latency/capability trade-offs; PaLM is the prior generation being superseded by Gemini.
- 🔑 Vertex AI Studio is the prompt design and testing environment, not typically the production runtime — finalized prompts are exported into application code.
- 🔑 Grounding (with Google Search or enterprise data via Vertex AI Search) anchors responses to verifiable sources and returns citations, substantially reducing but not eliminating hallucination.
- 🔑 Function calling lets Gemini request that an external tool/API be invoked, but the calling application — never the model itself — actually executes the function.
- 🔑 Grounding with Google Search is a distinctive GCP capability with no direct AWS/Azure equivalent, a common interview differentiator.

## 68.11 Related Concepts

Vertex AI Fundamentals (Section 65) and Model Garden (Section 67) for the underlying model catalog Gemini is part of, VPC Service Controls (Section 41) for securing grounding data and generative AI endpoints, MLOps on GCP (Section 69) for monitoring generative AI applications in production, and AI/ML Security & Responsible AI (Section 70) for governance considerations specific to generative AI outputs.
