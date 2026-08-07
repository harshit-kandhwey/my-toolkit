# Part 12, Section 5: Bedrock Deep Dive — Agents, Knowledge Bases, Guardrails

## 1. Definition

**Plain language:** [§111](./Section-111-Part12-Bedrock-Fundamentals.md) covered basic Bedrock usage — send a prompt, get a response. Real generative AI applications usually need more: grounding responses in an organization's own documents (not just the model's general training knowledge), letting the model take multi-step actions rather than just generate text, and enforcing safety/content boundaries so the application behaves appropriately in production. This section covers the three Bedrock capabilities that turn basic prompting into a genuine production application: Knowledge Bases (for RAG), Agents (for multi-step, tool-using behavior), and Guardrails (for safety).

**Precise definition:** This section covers three Bedrock production capabilities: **Knowledge Bases**, a managed Retrieval-Augmented Generation (RAG) implementation that indexes an organization's documents for retrieval and automatically incorporates relevant retrieved content into prompts; **Agents**, which orchestrate multi-step reasoning and can invoke external tools/APIs (including AWS services) to accomplish a task beyond single-turn text generation; and **Guardrails**, configurable policies enforcing content-safety, topic restriction, and sensitive-information filtering on both prompts and model responses.

## 2. Why It Exists / Problem It Solves

- [§111](./Section-111-Part12-Bedrock-Fundamentals.md) §4.3 established that a foundation model's knowledge is bounded by its training data — Knowledge Bases exist specifically to solve the "ground responses in our own, current, private information" problem without retraining the model itself, which [§111](./Section-111-Part12-Bedrock-Fundamentals.md)'s fundamentals section named but didn't yet cover the mechanics of.
- Basic prompting produces one text response per request — but many real tasks need more: looking up current information, calling an internal API to check an order status, performing a calculation, or chaining several such steps together to accomplish a genuinely multi-step task ("check this customer's order status, and if it's delayed, draft an apology email referencing the specific delay reason"). Agents exist to orchestrate exactly this kind of multi-step, tool-using behavior, which a single prompt/response call cannot accomplish on its own.
- Generative models can, without safeguards, produce content that's off-topic, unsafe, or reveals sensitive information inadvertently included in a prompt or retrieved context — a genuinely different risk category than traditional ML's accuracy-focused monitoring ([§110](./Section-110-Part12-MLOps-Model-Monitoring.md)). Guardrails exist to enforce explicit content-safety and topic boundaries as a configurable policy layer, rather than relying solely on the underlying model's own built-in safety training.

## 3. Prerequisites and Dependencies

- **Amazon Bedrock fundamentals** ([§111](./Section-111-Part12-Bedrock-Fundamentals.md)): this section builds directly on the basic prompting/inference model established there.
- **Amazon OpenSearch Service** ([§105](../Part11/Section-105-Part11-OpenSearch.md)): commonly the underlying vector-search technology behind a Knowledge Base's retrieval mechanism (§4.1).
- **AWS Lambda** ([§25](../Part3/Section-25-Part3-AWS-Lambda-Serverless-Compute.md)): commonly the mechanism through which an Agent invokes custom tools/actions (§4.2).

## 4. Internal Working / Architecture & Components

### 4.1 Knowledge Bases — Managed RAG

- A **Knowledge Base** ingests a specified set of documents (from S3, following this course's established data lake patterns from [§99](../Part11/Section-99-Part11-Data-Lake-Fundamentals-Glue-DataCatalog.md)), automatically chunks them into smaller passages, generates **embeddings** (numerical vector representations capturing semantic meaning) for each chunk using an embedding model, and stores those embeddings in a **vector store** — commonly Amazon OpenSearch Service ([§105](../Part11/Section-105-Part11-OpenSearch.md)), configured specifically for vector similarity search, though other vector store options exist and evolve; verify current documentation for supported vector store backends.
- At query time, the user's question is itself converted to an embedding, and the vector store is searched for the most semantically similar document chunks (**semantic search** — finding content with similar _meaning_, not just matching keywords, a meaningfully different retrieval mechanism than a traditional keyword-based OpenSearch full-text query, [§105](../Part11/Section-105-Part11-OpenSearch.md) §4.1) — the retrieved, relevant chunks are then automatically incorporated into the prompt sent to the foundation model, grounding its response in that actual retrieved content.
- 🔑 **Key takeaway:** this is exactly the RAG mechanism [§111](./Section-111-Part12-Bedrock-Fundamentals.md) §4.3 introduced conceptually, now with the specific mechanics: chunking, embedding, vector similarity search, and prompt augmentation, all managed by Bedrock rather than an organization building this retrieval pipeline from scratch.

### 4.2 Agents — Multi-Step, Tool-Using Orchestration

- A **Bedrock Agent** extends basic prompting with the ability to break a complex user request into a sequence of steps, and, at each step, decide whether to generate a direct text response or invoke an external **action** — a defined integration point, commonly implemented as a Lambda function ([§25](../Part3/Section-25-Part3-AWS-Lambda-Serverless-Compute.md)), that can call an internal API, query a database, or perform some other concrete operation, with the action's result fed back into the Agent's ongoing reasoning process.
- This orchestration pattern — an LLM deciding, step by step, whether to respond directly or invoke a tool, incorporating each tool's result before deciding the next step — is commonly called the **ReAct** (Reason + Act) pattern in the broader generative AI field, though Bedrock Agents manage this orchestration logic on the developer's behalf rather than requiring it to be hand-built.
- An Agent can also be connected to a Knowledge Base (§4.1), combining retrieval-grounded knowledge with tool-using action capability in a single orchestrated flow — for example, an Agent that retrieves relevant policy documentation via a Knowledge Base _and_ calls an internal order-status API via an action, within one multi-step interaction handling a single user request.
- ⚠️ **Warning:** giving an Agent the ability to invoke real actions (especially any action with a side effect — sending an email, modifying a record, initiating a refund) is a genuinely different risk profile than a purely text-generating chatbot; the same explicit-permission and confirmation principles this course applies to any side-effectful automated action (echoing the action-category distinctions in this course's own operating principles) apply directly to Agent action design — an Agent's action permissions should be scoped deliberately, and side-effectful actions should generally require an explicit confirmation step rather than executing unilaterally.

### 4.3 Guardrails — Content Safety and Governance

- **Guardrails** are configurable policies applied to both the input (user prompt) and output (model response) of a Bedrock interaction, independent of which underlying foundation model is being used — supporting content filters (blocking harmful content categories), denied topics (blocking specific subject matter the application shouldn't engage with), sensitive information filters (detecting and redacting or blocking PII), and word/phrase filters (blocking specific terms).
- Guardrails are evaluated as a distinct policy layer _around_ the model interaction — meaning the same Guardrail policy can be applied consistently across different underlying foundation models an application might use, rather than depending entirely on each individual model's own built-in safety behavior, which can vary across models and providers.
- 🔑 **Key takeaway:** Guardrails address a risk category with no direct analog in [§108](./Section-108-Part12-SageMaker-Fundamentals.md)-[§110](./Section-110-Part12-MLOps-Model-Monitoring.md)'s traditional ML monitoring — traditional ML monitoring ([§110](./Section-110-Part12-MLOps-Model-Monitoring.md)) is about detecting _drift_ in an already-narrow, well-defined prediction task; Guardrails are about actively constraining the _open-ended, unpredictable output space_ a generative model can otherwise produce, a fundamentally different governance problem.

## 5. Lifecycle / Workflow

1. An organization's relevant documents (support docs, policy documents, product catalogs) are ingested into a Knowledge Base (§4.1), chunked and embedded into a vector store.
2. A Guardrail policy (§4.3) is defined, specifying content filters, denied topics, and sensitive-information handling appropriate to the application.
3. A user submits a request; if using an Agent (§4.2), the Agent reasons about the request, potentially querying the Knowledge Base for relevant grounding content and/or invoking one or more actions (Lambda-backed tool calls) to gather information or perform operations.
4. Guardrails evaluate both the user's input and the model's generated output at each relevant step, blocking or redacting content that violates the configured policy before it reaches the model (for input) or the end user (for output).
5. The final response — grounded in retrieved knowledge, potentially incorporating action results, and filtered through Guardrails — is returned to the user.

## 6. Configuration

| Setting                                                                          | Purpose                                                                                                         |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| Knowledge Base data source (S3 location) and sync schedule                       | What documents are ingested and how frequently the Knowledge Base re-syncs to reflect updated source documents. |
| Chunking strategy                                                                | How documents are divided into retrievable passages — affects retrieval granularity/relevance.                  |
| Agent action group definitions                                                   | Which external actions (Lambda functions/APIs) an Agent can invoke, and their input/output schemas.             |
| Guardrail policy (content filters, denied topics, sensitive-information filters) | The specific safety/governance boundaries enforced on prompts and responses.                                    |

## 7. Commands / API (Full Documentation)

### 7.1 Querying a Knowledge Base (RAG)

- **Purpose:** Retrieve relevant grounding content and generate a response incorporating it, in one call.
- **Syntax:**

```bash
aws bedrock-agent-runtime retrieve-and-generate \
  --input '{"text": "What is our refund policy for damaged items?"}' \
  --retrieve-and-generate-configuration '{"type":"KNOWLEDGE_BASE","knowledgeBaseConfiguration":{"knowledgeBaseId":"KB123456","modelArn":"<foundation-model-arn>"}}'
```

- **Important arguments:** `knowledgeBaseId` identifies the specific Knowledge Base (and therefore document set) to retrieve from. `modelArn` specifies which foundation model generates the final response using the retrieved content.
- **Practical example / expected output:** the response includes both the generated answer (grounded in retrieved policy documentation, not the model's general training knowledge) and citations identifying which specific source document chunks were used — a genuinely important production feature for auditability and user trust, letting an application show "here's the actual policy text this answer is based on."
- **Common errors:** querying a Knowledge Base whose data source hasn't finished syncing after a document update, returning stale results; a chunking strategy poorly suited to the document type (e.g., overly large chunks diluting retrieval relevance for very specific questions).

### 7.2 Invoking an Agent

```bash
aws bedrock-agent-runtime invoke-agent \
  --agent-id AGENT123 \
  --agent-alias-id ALIAS456 \
  --session-id customer-session-789 \
  --input-text "What's the status of order #48213, and if it's delayed, draft an apology email"
```

- **Production usage:** this single request could trigger a multi-step Agent flow: invoking an "order lookup" action (a Lambda function querying an internal order database), reasoning about whether the returned status indicates a delay, and — if so — generating a drafted apology email as the response, potentially also querying a Knowledge Base for the company's approved communication tone/template guidelines. `session-id` maintains conversational context across multiple turns of an ongoing interaction.

## 8. Hands-On Example — Full Production Pattern

```text
Customer support application (extending §111's basic example):

1. Guardrail defined: blocks discussion of competitor products, filters
   any credit card numbers appearing in either user input or model
   output, blocks generation of medical/legal advice

2. Knowledge Base ingests: product documentation, support FAQ,
   refund/return policy documents from S3

3. Agent configured with:
   - Knowledge Base connection (for policy/documentation questions)
   - Action: "check_order_status" (Lambda calling internal order API)
   - Action: "initiate_refund" (Lambda calling internal refund API --
     configured to require an explicit confirmation step given its
     side-effectful, financial nature, per §4.2's warning)

4. Customer asks: "My order #48213 arrived damaged, can I get a refund?"

5. Agent flow:
   a. Retrieves refund policy from Knowledge Base (grounds eligibility
      criteria in actual policy, not the model's general assumptions)
   b. Invokes check_order_status action to verify order details
   c. Determines the order qualifies per retrieved policy
   d. Responds confirming eligibility and next steps, WITHOUT
      unilaterally invoking initiate_refund -- instead prompting the
      customer to confirm before the action proceeds

6. Guardrails evaluate the final response before it reaches the customer,
   confirming no policy-violating content is present
```

This demonstrates all three capabilities working together: Knowledge Bases grounding the response in actual policy, Agents orchestrating a multi-step flow involving both retrieval and a real backend action, and Guardrails providing a consistent safety layer around the entire interaction — directly extending [§111](./Section-111-Part12-Bedrock-Fundamentals.md)'s basic single-call example into a genuine production pattern.

## 9. Production and Enterprise Usage

- Knowledge Bases are the standard Bedrock pattern for any application needing to answer questions grounded in an organization's own, potentially frequently-changing documentation — support chatbots, internal knowledge assistants, and document Q&A tools overwhelmingly use this pattern rather than fine-tuning a model on document content directly, given RAG's lower cost and easier update cycle (re-sync a Knowledge Base versus retrain a model) established in [§111](./Section-111-Part12-Bedrock-Fundamentals.md) §4.3.
- Agents are increasingly used for genuinely multi-step, tool-using enterprise workflows — customer service automation, internal operations assistants — where a single text response isn't sufficient and real backend integration is needed, though the side-effectful-action confirmation discipline from §4.2's warning is a standard, expected production safeguard, not an optional nicety.
- Guardrails are commonly treated as a required, non-negotiable component of any customer-facing or otherwise production generative AI application, given both reputational risk (an application generating inappropriate content) and, in regulated industries, genuine compliance requirements around what an AI system may or may not discuss or reveal.

## 10. Security Considerations

- Agent actions with side effects require the same explicit-confirmation and least-privilege scoping discipline this course applies throughout to any automated, side-effectful action — an Agent's underlying Lambda action functions should be scoped to exactly the operations genuinely needed, following IAM least-privilege ([§9](../Part2/Section-09-Part2-IAM-Core-Concepts.md)-[§10](../Part2/Section-10-Part2-IAM-Policy-Evaluation-Logic.md)).
- Sensitive-information filters within Guardrails (§4.3) are a meaningful defense-in-depth layer against a prompt or retrieved document inadvertently surfacing PII in a generated response, though the underlying data governance (ensuring sensitive data isn't unnecessarily present in Knowledge Base source documents in the first place, following Lake Formation's column-level restriction principles, [§100](../Part11/Section-100-Part11-Lake-Formation.md)) remains the more foundational control.
- Knowledge Base data sources should be governed with the same access-control rigor as any other data source in this course — if a Knowledge Base indexes documents a given user population shouldn't have full access to, that access boundary needs to be enforced independently of the Knowledge Base/RAG mechanism itself, since RAG retrieval doesn't automatically respect fine-grained, per-user document permissions unless explicitly designed to.

## 11. Performance Considerations

- Knowledge Base retrieval adds a genuine latency step (embedding the query, vector search, then model generation) compared to a basic single-call prompt — an architectural trade-off accepted specifically for the grounding accuracy benefit.
- Chunking strategy ([§6](../Part1/Section-06-Part1-AWS-Pricing-and-Cost-Fundamentals.md)) directly affects retrieval relevance and, indirectly, response quality — a poorly-tuned chunking strategy can retrieve less relevant content, degrading response accuracy even though the underlying documents contain the correct information.
- Multi-step Agent flows (invoking a Knowledge Base retrieval, then one or more actions, then generating a final response) accumulate latency across each step — appropriate for genuinely multi-step tasks, but an unnecessarily complex Agent flow for a task that a simple single-call prompt could have handled adds latency without corresponding benefit.

## 12. Monitoring

- CloudWatch Metrics ([§69](../Part8/Section-69-Part8-CloudWatch-Fundamentals.md)) track Knowledge Base retrieval and Agent invocation latency/volume, alongside the basic Bedrock invocation metrics covered in [§111](./Section-111-Part12-Bedrock-Fundamentals.md) [§12](../Part2/Section-12-Part2-IAM-Identity-Center-SSO-Federation.md).
- Retrieved-chunk citations (§7.1) provide a genuinely useful debugging/quality signal — reviewing which source content a response was actually grounded in helps diagnose whether a poor response stems from a retrieval problem (wrong/irrelevant chunks retrieved) versus a generation problem (right content retrieved, but poorly used by the model).
- Guardrail intervention events (when a filter blocks or redacts content) should be logged and periodically reviewed — both to tune the Guardrail policy's sensitivity (avoiding excessive false positives blocking legitimate content) and to catch genuine attempted misuse patterns.

## 13. Troubleshooting

| Symptom                                                                | Cause                                                                                                | Fix                                                                                                                                |
| ---------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| Knowledge Base responses don't reflect a recently updated document     | Data source hasn't been re-synced since the document changed                                         | Trigger or verify the Knowledge Base sync schedule/process                                                                         |
| RAG responses are inaccurate despite correct source documents existing | Chunking strategy or retrieval relevance issue — wrong/irrelevant chunks retrieved                   | Review chunking configuration; inspect retrieved-chunk citations to diagnose whether retrieval or generation is the actual problem |
| Agent fails to complete a multi-step task                              | Action definition/schema mismatch, or the Agent's action-invocation IAM permissions are insufficient | Review the action's input/output schema definition and the underlying Lambda's IAM permissions                                     |
| Guardrail blocks legitimate, appropriate content                       | Guardrail policy configured too strictly/broadly for the application's actual legitimate use cases   | Review and recalibrate the Guardrail policy's specific filters/topics, balancing safety against false-positive blocking            |

## 14. Best Practices

- Use Knowledge Bases (RAG) as the default approach for grounding responses in organization-specific or frequently-changing information, reserving fine-tuning ([§111](./Section-111-Part12-Bedrock-Fundamentals.md) §4.3) for needs RAG genuinely doesn't address.
- Require explicit confirmation for any Agent action with a real side effect (financial transactions, sending communications, modifying records), never allowing an Agent to execute such actions unilaterally.
- Apply Guardrails consistently across every production generative AI application as a baseline safety control, tuned to the specific application's legitimate use case rather than left at an overly generic default.
- Review retrieved-chunk citations when diagnosing response quality issues, distinguishing retrieval problems from generation problems before attempting a fix.

## 15. Anti-Patterns and Common Mistakes

- ❌ Allowing an Agent to invoke side-effectful actions (refunds, emails, record changes) without any confirmation step, risking an unintended or erroneous action executing automatically based on the model's own reasoning.
- ❌ Assuming RAG automatically respects per-user document access permissions without explicitly designing for it — a Knowledge Base indexing documents a given user shouldn't fully see needs that access boundary enforced separately, not assumed.
- ❌ Deploying a customer-facing generative AI application with no Guardrails configured, relying entirely on the underlying foundation model's own built-in safety behavior.
- ❌ Building an unnecessarily complex multi-step Agent flow for a task a single, simpler RAG-grounded prompt could have handled, adding latency and operational complexity without corresponding benefit.

## 16. Interview Questions with Model Answers

**🎯 Junior:** _"What does a Bedrock Knowledge Base actually do?"_
**Model answer:** It implements Retrieval-Augmented Generation in a managed way — you point it at your documents in S3, and it automatically chunks them, converts the chunks into vector embeddings, and stores them in a vector search index. When a user asks a question, the Knowledge Base finds the most semantically relevant chunks from your documents and includes them in the prompt sent to the foundation model, so the model's response is grounded in your actual content rather than only its general training knowledge.

**🎯 Intermediate:** _"Why does giving a Bedrock Agent the ability to invoke real actions introduce a different risk than a basic chatbot, and how would you mitigate it?"_
**Model answer:** A basic chatbot only generates text — the worst outcome is a bad or inaccurate response, which is contained to the conversation itself. An Agent with action capability can actually do things — call an internal API, and if that action has a real side effect like processing a refund or sending an email, the model's own reasoning is now what decides whether that real-world action happens. If the model reasons incorrectly, that's no longer just a bad text response, it's an unintended real action. The mitigation is treating any side-effectful action the same way this course treats any other automated side-effectful action generally — requiring an explicit confirmation step before it executes, rather than letting the Agent invoke it unilaterally, and scoping the underlying action's permissions as tightly as possible so even a confirmed action can't exceed its intended, narrow scope.

**🎯 Senior:** _"A company's RAG-based support chatbot is giving confidently wrong answers about their return policy, even though the correct policy document is in their Knowledge Base. How would you diagnose this?"_
**Model answer:** I'd start by checking the retrieved-chunk citations for a few example failing queries, which directly shows whether the Knowledge Base is even retrieving the correct policy document chunks in the first place — if it's retrieving irrelevant or wrong chunks, this is a retrieval problem, likely caused by a chunking strategy poorly suited to the document (for example, splitting the policy document in a way that separates a condition from its exception onto different chunks, so neither chunk alone contains the full accurate rule) or the document's sync being stale relative to a recent policy update. If the citations show the correct chunks _are_ being retrieved, but the response still gets the answer wrong, that's a generation problem instead — the model is being given the right information but not using it correctly, which might call for prompt engineering adjustments (being more explicit that the response must be strictly grounded in the provided context) or, if this persists, considering Guardrails' ability to help constrain the model to only make claims supported by retrieved content. Distinguishing these two failure modes via the citations is the necessary first diagnostic step before attempting any fix, since the fix for a retrieval problem (chunking/sync) is completely different from the fix for a generation problem (prompting/guardrails).

**🎯 Architect:** _"Design a generative AI-powered internal operations assistant for a logistics company, letting employees ask natural-language questions about shipment status, company policy, and initiate common operational actions like flagging a shipment for review — while ensuring the system can't take unauthorized actions and maintains an audit trail."_
**Model answer:** Build this as a Bedrock Agent (§4.2) connected to a Knowledge Base (§4.1) indexing company policy and operational documentation, with defined actions for read-only operations (checking shipment status via a Lambda calling the internal shipment-tracking API) invoked freely by the Agent as part of normal conversational flow, since read-only actions carry minimal risk. For the "flag a shipment for review" action specifically — a genuine, if modest, side-effectful action — configure it to require explicit user confirmation before executing, per §4.2's established pattern, rather than the Agent executing it unilaterally based on inferring the user's intent from a single message. Scope every action's underlying Lambda function and IAM permissions tightly to exactly its specific operation (the shipment-flagging action's role should be able to flag shipments and nothing broader), directly addressing the "can't take unauthorized actions" requirement structurally rather than relying on the Agent's own reasoning as the only safeguard. For the audit trail requirement, log every Agent interaction — including which Knowledge Base chunks were retrieved, which actions were invoked (and by which employee, via session/identity tracking), and the final response — to CloudWatch Logs or a dedicated audit store, mirroring the CloudTrail-style auditability principle established throughout this course ([§73](../Part8/Section-73-Part8-CloudTrail-Audit-Governance.md)) but applied to generative AI interactions specifically, since demonstrating exactly what the system did and why is just as important for an internal operations tool with real action capability as it is for infrastructure changes. Apply Guardrails (§4.3) scoped to the operational domain — blocking off-topic discussion and filtering any sensitive shipment/customer data that shouldn't appear in a response beyond what the requesting employee is authorized to see, acknowledging per [§10](../Part2/Section-10-Part2-IAM-Policy-Evaluation-Logic.md)'s point that this authorization boundary needs to be explicitly designed into the Knowledge Base/action access pattern, not assumed to be automatic.

## 17. Common Misconceptions

- "RAG and fine-tuning accomplish the same thing." False — RAG grounds responses in retrieved, current external content without changing the model itself, while fine-tuning actually adjusts the model's own parameters for more consistent task/style behavior; they solve different problems and are often complementary rather than substitutes.
- "An Agent's actions are inherently safe because the model 'understands' the request." False — an Agent's action-invocation decision is still a model-generated inference, which can be wrong; side-effectful actions need explicit confirmation and tight permission scoping regardless of how capable the underlying model appears.
- "Guardrails make a generative AI application completely safe." Overstated — Guardrails are a genuine, valuable policy layer, but they're one control among several (data governance, action permission scoping, human confirmation for side effects) rather than a single, complete solution to generative AI safety on their own.

## 18. Key Takeaways

🔑 Knowledge Bases implement managed RAG — chunking, embedding, vector search, and prompt augmentation — grounding responses in an organization's own documents without retraining the underlying model.
🔑 Agents orchestrate multi-step, tool-using behavior (the ReAct pattern), invoking real actions via Lambda-backed integrations — side-effectful actions specifically require explicit confirmation and tight permission scoping, not unilateral execution.
🔑 Guardrails provide a configurable, model-independent content-safety policy layer applied to both prompts and responses — addressing an open-ended output-space risk category with no direct analog in traditional ML monitoring ([§110](./Section-110-Part12-MLOps-Model-Monitoring.md)).
🔑 Retrieved-chunk citations are a genuinely important diagnostic tool for distinguishing RAG retrieval problems from model generation problems when troubleshooting response quality.
🔑 RAG doesn't automatically enforce per-user document access permissions — that access boundary must be explicitly designed into the Knowledge Base and application architecture, not assumed.

## 19. Related Concepts

- **Amazon Bedrock Fundamentals** ([§111](./Section-111-Part12-Bedrock-Fundamentals.md)) — the basic prompting/inference model this section's three capabilities extend.
- **Amazon OpenSearch Service** ([§105](../Part11/Section-105-Part11-OpenSearch.md)) — the common underlying vector-search technology behind Knowledge Bases.
- **AWS Lambda** ([§25](../Part3/Section-25-Part3-AWS-Lambda-Serverless-Compute.md)) — the common mechanism for implementing Agent actions.
- **AI/ML Security & Governance** ([§113](./Section-113-Part12-AIML-Security-Governance.md), next section) — broader governance considerations spanning both traditional ML and this section's generative AI capabilities.
- **AWS Lake Formation** ([§100](../Part11/Section-100-Part11-Lake-Formation.md)) — the fine-grained access-control pattern relevant to properly scoping Knowledge Base document access per [§10](../Part2/Section-10-Part2-IAM-Policy-Evaluation-Logic.md)'s discussion.
