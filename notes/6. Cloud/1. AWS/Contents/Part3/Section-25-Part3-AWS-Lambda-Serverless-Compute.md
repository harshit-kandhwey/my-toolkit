# Part 3 · Section 7 — AWS Lambda & Serverless Compute

> AWS Zero-to-Enterprise Knowledge Base · Part 3: Compute

---

## 1. Definition

**Plain-language:** AWS Lambda lets you upload just your code — a function — and AWS runs it whenever triggered, automatically providing exactly the compute needed, then tearing it down. You pay only for the milliseconds your code actually runs.

**Precise:** **AWS Lambda** is AWS's serverless, event-driven compute service — you supply a function (code + handler), Lambda automatically provisions, scales, and tears down the execution environment in response to triggering events, billed by invocation count and execution duration × allocated memory, with no idle-time charge.

---

## 2. Why It Exists

- The concrete realization of FaaS (§5) — AWS manages everything except your function's code, the logical endpoint of the "less operational burden" trend from EC2 through ASG automation.
- Even a perfectly-tuned ASG still means thinking about instance types, AMIs, patching, capacity — pure waste for event-driven/intermittent/unpredictable workloads. Lambda removes it entirely.
- Extends §6's consumption-based pricing to its logical extreme — paying for actual execution time at sub-second granularity, not provisioned (even elastic) capacity.

---

## 3. The Execution Model

### 3.1 Function, Handler, Runtime

- A function = handler (entry-point method) + runtime (Node.js, Python, Java, Go, .NET, Ruby, or custom via Runtime API).
- **Container image support** — functions can package as container images (up to 10 GB) for large dependencies/system libraries, still executing in Lambda's serverless model.

### 3.2 Invocation Types

- **Synchronous** — caller waits for a response (API Gateway, ALB direct invocation).
- **Asynchronous** — caller hands off and moves on; Lambda queues internally with automatic retries (~2 more), optional DLQ or on-failure destination for exhausted retries (S3 events, SNS).
- **Event source mapping (poll-based)** — for streams/queues (SQS, Kinesis, DynamoDB Streams), Lambda itself polls and invokes with batches — a distinct third pattern.

### 3.3 Cold Starts vs Warm Starts

- **Cold start** — brand-new execution environment: download code, start runtime, run init code outside the handler — adds latency.
- **Warm start** — reuses an already-initialized environment, skipping init overhead.
- Matters most for latency-sensitive, synchronous, user-facing invocations; less relevant for async/batch workloads.
- **Mitigation — Provisioned Concurrency:** pay to keep N environments pre-initialized/warm at all times, eliminating cold starts for that capacity — a direct trade-off against Lambda's "pay only for execution" premise.

---

## 4. Concurrency Model

- **Concurrency** = simultaneous in-flight executions; Lambda auto-scales up to account/function limits.
- **Account concurrency limit** — regional ceiling across all functions, raisable via service-limit increase.
- **Reserved concurrency** — sets aside a guaranteed portion for one function — both a floor (guaranteed capacity) and a ceiling (caps consumption, protecting other functions).
- **Reserved vs Provisioned Concurrency — frequently confused:** reserved = free scaling/isolation control (capacity set-aside/cap). Provisioned = paid cold-start mitigation (pre-warmed environments). Different problems, usable together or independently.

---

## 5. Triggers

| Trigger category   | Examples                                                | Invocation type                    |
| ------------------ | ------------------------------------------------------- | ---------------------------------- |
| HTTP/API           | API Gateway, ALB                                        | Synchronous                        |
| Storage events     | S3 object created/deleted                               | Asynchronous                       |
| Streams/queues     | SQS, Kinesis, DynamoDB Streams                          | Event source mapping (poll-based)  |
| Messaging          | SNS                                                     | Asynchronous                       |
| Scheduled          | EventBridge Scheduler/rules                             | Asynchronous                       |
| Orchestration      | Step Functions                                          | Synchronous (within state machine) |
| Other AWS services | CloudFormation custom resources, Cognito triggers, etc. | Varies                             |

> 🔑 Lambda is fundamentally reactive — doesn't "do" anything until triggered, a natural fit for event-driven architectures (Part 7).

---

## 6. Configuration — Memory, Timeout, Memory/CPU Relationship

- **Memory** — configurable in fine-grained MB increments; **CPU scales proportionally with memory** — no independent CPU dial (frequently tested, non-obvious).
- **Timeout** — max 15 minutes per invocation — precisely why Lambda isn't suited for long-running processes (contrast with §8's ECS/EKS, no such ceiling).
- **Right-sizing memory is a performance AND cost lever** — a CPU-bound function may run faster (and cost less overall, since billing = duration × memory) at higher memory despite the higher per-ms rate. "Lower memory = lower cost" is often wrong.

---

## 7. Environment and State

- **Ephemeral by design** — no guaranteed persistent state between invocations (a warm environment _may_ retain `/tmp`/globals, but never reliably).
- **`/tmp` storage** — ephemeral local disk for one invocation (or opportunistically across warm ones), never a persistence substitute.
- **Statelessness implication:** persistent/shared data must live externally (S3, DynamoDB, ElastiCache) — extends Section 6 §9's "externalize state" principle to serverless.
- **Environment variables** for non-secret config; **secrets pulled from Secrets Manager/Parameter Store at runtime** (§15), never hardcoded.

---

## 8. IAM Integration — Execution Role

- Every function has an **execution role** (IAM role, §9/§11) with `lambda.amazonaws.com` as trusted principal.
- Least privilege applies fully — scoped per function, arguably more important here given how many small single-purpose functions a serverless architecture accumulates, each a distinct blast-radius boundary.

---

## 9. Lambda Layers

- A **Layer** = reusable package of code/dependencies attachable to multiple functions, separate from each function's own deployment package.
- Maintains shared logic (logging, tracing, utilities) once instead of duplicating across every function — parallel to golden-image reuse (Section 2 §4.2), applied to function code.

---

## 10. Production & Enterprise Usage

- **Lambda behind API Gateway/ALB** — standard serverless REST/HTTP API pattern, no server layer to manage.
- **Event-driven data pipelines** — S3 upload → Lambda → DynamoDB, or SQS → batch Lambda — common production pattern (full depth Part 7).
- **Lambda as operational glue** — many automated-remediation patterns (§16 GuardDuty/Config remediation, §14 KMS rotation) are themselves Lambda functions.
- **Compute Savings Plans apply to Lambda** — relevant cost lever for high-volume steady-state usage.

---

## 11. Security Considerations

- **Execution role least privilege** — the primary Lambda-specific control, higher-stakes given function count.
- **VPC vs non-VPC Lambda** — VPC access for private resources (RDS) vs default internet/AWS-service access outside a VPC — a real architectural decision (full detail Part 4).
- **Supply-chain risk applies** — vulnerable dependencies in deployment packages/container images; Amazon Inspector (§16) scans Lambda functions.

---

## 12. Performance Considerations

- Cold starts (§3.3) are the primary concern — mitigated by Provisioned Concurrency, lighter init code, or lighter runtime.
- Memory/CPU right-sizing (§6) — profile actual execution time, don't assume lower memory = lower cost.
- 15-minute timeout is a hard boundary — exceeding workloads need Step Functions orchestration or a different compute type (§8).

---

## 13. Troubleshooting

| Symptom                                    | Cause                                                                    | Fix                                                                                        |
| ------------------------------------------ | ------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------ |
| Occasional higher latency on some requests | Cold start on a new environment                                          | Provisioned Concurrency for latency-sensitive functions; accept for async workloads        |
| Works individually, fails under real load  | Concurrency limit reached, throttling                                    | Review/raise limits; use reserved concurrency for critical functions                       |
| Times out on larger inputs                 | Exceeds configured/max (15 min) timeout                                  | Increase up to ceiling; else break into Step Functions steps or move to non-Lambda compute |
| AccessDenied calling another service       | Execution role lacks the permission                                      | Update execution role's permissions policy                                                 |
| `/tmp` data missing on next invocation     | Different/cold environment; persistence is opportunistic, not guaranteed | Never rely on `/tmp` for persistence — use S3/DynamoDB                                     |

---

## 14. Best Practices & Anti-Patterns

**Best practices:** scope execution roles tightly per function; externalize all state; pull secrets from Secrets Manager/Parameter Store at runtime; use Provisioned Concurrency deliberately where cold starts genuinely matter; profile memory against actual execution time; use Layers for shared code.

**Anti-patterns:** running long monolithic processes on Lambda; relying on `/tmp`/in-memory state persisting across invocations; broad service-level execution role permissions "for convenience"; ignoring cold starts for latency-sensitive synchronous functions; hardcoding secrets as plain environment variables.

---

## 15. Common Misconceptions

- "Serverless means nothing to think about operationally." → False — execution role scope, memory/timeout tuning, cold starts, concurrency limits all still matter.
- "Memory and CPU are independently configurable." → False — CPU scales automatically with memory.
- "Lower memory always means lower cost." → False — CPU-bound functions can cost less overall at higher memory due to reduced duration.
- "Reserved concurrency and Provisioned Concurrency are the same." → False — free scaling/isolation control vs paid cold-start mitigation, different mechanisms.

---

## 16. Interview Questions (with model answers)

**🟢 What is Lambda, and how does its billing differ from EC2?** Serverless, event-driven compute — provide code, Lambda auto-provisions/tears down execution environments per trigger. Billed by invocation count and duration × memory, zero idle cost — genuinely different from EC2's pay-for-provisioned-capacity model even with Auto Scaling.

**🟢 What's a cold start and when does it matter most?** New execution environment initialization (code download, runtime start, init code) adds latency before the first invocation. Matters most for latency-sensitive synchronous user-facing calls; much less for async/batch workloads.

**🟡 Reserved concurrency vs Provisioned Concurrency?** Reserved: guaranteed portion of account concurrency for one function — floor (guaranteed capacity) and ceiling (caps consumption, protects other functions); free. Provisioned: paid feature keeping N environments pre-warmed, eliminating cold starts. Different problems; can combine.

**🟡 Why might increasing memory decrease total cost?** CPU scales proportionally with memory (no independent CPU config). More memory → more CPU → for CPU-bound work, potentially much shorter duration. Since cost = duration × memory, if duration shrinks enough, total cost drops despite the higher per-ms rate — profiling often reveals a sweet spot faster and cheaper than the naive minimum.

**🔴 Design a serverless pipeline: S3 upload → validate/transform → DynamoDB, with graceful failure handling?** S3 event notification asynchronously triggers Lambda, execution role scoped to just that bucket prefix + target table. Configure a DLQ/on-failure destination (SQS) to capture events exhausting automatic retries, so failures aren't silently lost. Single-step transform stays in one function; genuinely multi-step logic with different retry semantics per step uses Step Functions instead of one large function handling every failure mode. Right-size memory via profiling; shared validation logic in a Lambda Layer.

**🔴 Lambda vs ECS/EKS for a new internal microservice — what factors drive the decision?** Execution duration/pattern first — genuinely event-driven work within the 15-min ceiling favors Lambda's zero-idle-cost billing, especially for spiky/unpredictable traffic. Long-running/persistent-connection/significant-in-memory-state/potentially->15-min work favors ECS/EKS, since Lambda's statelessness and timeout become real constraints. Weigh cold-start sensitivity — a latency-critical synchronous API might need Provisioned Concurrency, narrowing the cost advantage vs a small always-on container. Team familiarity/existing tooling matters — sunk container/Kubernetes operational maturity may favor platform consistency over introducing a second compute paradigm.

---

## 🔑 Key Takeaways

1. Lambda is the FaaS endpoint of the IaaS→SaaS spectrum — AWS manages everything but function code, billed purely by invocation count and duration × memory, zero idle cost.
2. Cold starts vs warm starts is the central performance concept — mitigated (at cost) by Provisioned Concurrency, mattering far more for synchronous/latency-sensitive workloads.
3. Reserved concurrency (free, floor/ceiling) and Provisioned Concurrency (paid, cold-start mitigation) are genuinely different, frequently confused mechanisms.
4. Memory and CPU aren't independently configurable — CPU scales with memory, making memory right-sizing a real performance and cost lever.
5. Lambda is fundamentally stateless and event-triggered — persistence must be externalized, execution roles need per-function least privilege, and the 15-minute timeout is a hard boundary separating Lambda-appropriate workloads from ECS/EKS territory.

## 🌐 Related Concepts (forward links)

- Containers — ECS, EKS, Fargate for workloads exceeding Lambda's constraints → §26 (next)
- Step Functions and event-driven architecture patterns → Part 7
- VPC-Lambda networking integration → Part 4
- DynamoDB, S3, and other Lambda-adjacent data stores → Parts 5-6
