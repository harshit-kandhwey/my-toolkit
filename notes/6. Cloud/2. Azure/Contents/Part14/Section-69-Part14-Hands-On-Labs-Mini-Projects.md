# Section 69 — Hands-On Labs & Mini-Projects

**Part 14: Interview Preparation & Wrap-Up | Section 69 of 70**
**Prerequisites:** All prior sections (this section provides practical exercises applying that material)
**Leads into:** Section 70 (Key Takeaways Checklist & Recommended Next Topics)

---

## 69.1 Introduction and Purpose

This section provides progressive, hands-on labs and mini-projects — from beginner-level single-service exercises through production-style, multi-service capstone projects — giving structured practice actually building the services and patterns covered throughout this roadmap, rather than only reading and reasoning about them. Each lab specifies its objective, the specific roadmap sections it exercises, a step-by-step structure, and a "verify your understanding" checkpoint connecting back to the relevant section's material.

🔑 **Key Takeaway:** reading this roadmap's 66 technical sections builds conceptual understanding; actually executing these labs builds the hands-on fluency (exact CLI syntax, real error messages, genuine troubleshooting experience) that conceptual understanding alone cannot provide — and that genuine interview and on-the-job competence both require. Treat this section as mandatory, not optional, practice.

---

## 69.2 Beginner Labs (Single-Service Fundamentals)

### 69.2.1 Lab 1: Deploy and Access a Storage Account

- **Objective:** create a Storage Account, create a Blob container, upload/download a file via both the Portal and Azure CLI, and configure a lifecycle management policy.
- **Sections exercised:** 16, 17.
- **Steps:** (1) Create a resource group and Storage Account via `az storage account create`. (2) Create a Blob container. (3) Upload a file via `az storage blob upload` and verify download. (4) Configure a lifecycle management rule moving blobs older than 30 days to Cool tier. (5) Attempt to access the blob anonymously and confirm it fails (verifying `allowBlobPublicAccess` defaults correctly, Section 43.3.4's exact property).
- **Verify your understanding:** can you explain, without looking it up, the difference between Hot/Cool/Archive tiers and why lifecycle management exists (Section 17)?

### 69.2.2 Lab 2: Build and Push a Docker Image to ACR

- **Objective:** write a multi-stage Dockerfile, build it, push to ACR, and pull it back down.
- **Sections exercised:** 33, 34.
- **Steps:** (1) Write a simple application (any language) with a multi-stage Dockerfile following Section 33.6.3's pattern. (2) Create an ACR instance. (3) Authenticate via `az acr login`. (4) Build and push using `az acr build` (Section 34.6.3). (5) Inspect the pushed image's layers via `docker history` (Section 33.5.5). (6) Verify the image tag vs. digest distinction by pulling via digest specifically.
- **Verify your understanding:** can you explain why the multi-stage build's final image is smaller than the build stage, referencing specific instructions in your own Dockerfile?

### 69.2.3 Lab 3: Deploy an AKS Cluster and a Simple Application

- **Objective:** create an AKS cluster, deploy a Deployment and Service, and observe self-healing.
- **Sections exercised:** 35, 36.
- **Steps:** (1) Create an AKS cluster with `--attach-acr` pointing to Lab 2's registry. (2) Write a Deployment manifest referencing your Lab 2 image, with 3 replicas. (3) Apply it and expose it via a `LoadBalancer`-type Service. (4) Manually delete one pod via `kubectl delete pod` and observe it being automatically recreated (Section 35.6.2). (5) Scale the Deployment and observe the change.
- **Verify your understanding:** can you explain, in your own words, what happened at each layer (ReplicaSet, scheduler, kubelet) when you deleted the pod?

---

## 69.3 Intermediate Labs (Multi-Service Integration)

### 69.3.1 Lab 4: Serverless API with Key Vault-Sourced Secrets

- **Objective:** build an HTTP-triggered Azure Function that retrieves a secret from Key Vault via Managed Identity, with no credential stored anywhere in code or configuration.
- **Sections exercised:** 9, 38, 53.
- **Steps:** (1) Create a Function App with a system-assigned Managed Identity enabled. (2) Create a Key Vault, store a test secret. (3) Grant the Function App's Managed Identity the `Key Vault Secrets User` role (Section 53.4.3) — not broader. (4) Configure a Key Vault reference (Section 53.8.2) in the Function App's application settings. (5) Write the HTTP-triggered function to read and return (for testing only — never do this with a real secret) the configured setting value, confirming it resolves correctly.
- **Verify your understanding:** can you explain why this pattern avoids ever storing a plaintext credential, tracing the authentication flow from Function App to Key Vault?

### 69.3.2 Lab 5: CI/CD Pipeline with Environment Promotion

- **Objective:** build a pipeline that builds one container image, and deploys the same image, unmodified, through dev and (simulated) production stages with an approval gate.
- **Sections exercised:** 42, 46.
- **Steps:** (1) Create a GitHub repository (or Azure Repos) with your Lab 2 application's Dockerfile. (2) Write a multi-stage pipeline (Azure Pipelines or GitHub Actions, Section 42.4.3/46.5.3) that builds and pushes to ACR tagged with the commit SHA. (3) Add a deploy-to-dev stage deploying to a "dev" AKS namespace automatically. (4) Add a deploy-to-production stage targeting a "production" namespace, gated behind an environment approval (Section 42.4.4). (5) Verify the exact same image digest is used in both stages (Section 46.2.1).
- **Verify your understanding:** can you point to the specific pipeline configuration that guarantees "build once, promote unchanged" rather than rebuilding per environment?

### 69.3.3 Lab 6: Infrastructure as Code — Deploy a Complete Environment via Bicep

- **Objective:** author a Bicep template (using modules) that deploys a VNet, a Storage Account with diagnostic settings, and a Key Vault with purge protection — then preview and apply it.
- **Sections exercised:** 43, 44, 47.
- **Steps:** (1) Author a `networking.bicep` module (VNet + subnet). (2) Author a `main.bicep` referencing that module, plus a Storage Account resource with `allowBlobPublicAccess: false` and a diagnostic setting sending logs to a Log Analytics workspace (Section 47.4.3's exact pattern). (3) Add a Key Vault resource with `enablePurgeProtection: true` (Section 53.6.2). (4) Run `az deployment group what-if` (Section 43.7) and review the proposed changes before applying. (5) Apply the deployment, then run `what-if` again against the now-deployed state and confirm it reports no changes (idempotency, Section 43.2.2).
- **Verify your understanding:** can you explain what `what-if` would have shown if you'd accidentally used Complete deployment mode against a resource group containing an unrelated pre-existing resource?

---

## 69.4 Advanced Labs (Production-Style Patterns)

### 69.4.1 Lab 7: KQL Investigation Exercise

- **Objective:** given a Log Analytics workspace with Application Insights data (from Lab 4/5's deployed application, instrumented per Section 49.3), write KQL queries answering specific investigative questions.
- **Sections exercised:** 48, 49.
- **Steps:** write and validate KQL queries for: (1) request count per hour over the last 24 hours, using `bin()` (Section 48.4.1). (2) The top 5 slowest requests by duration. (3) A `join` correlating failed requests with their corresponding exception telemetry via `OperationId` (Section 48.4.2/49.4.2). (4) A query using `has` instead of `contains` for a text-matching condition, and explain the performance difference (Section 48.4.5).
- **Verify your understanding:** can you explain why your time filter should be the first pipeline stage in each query, in terms of actual query performance, not just convention?

### 69.4.2 Lab 8: Autoscaling and Load Testing

- **Objective:** configure HPA and Cluster Autoscaler on your Lab 3 AKS deployment, generate load, and observe scaling behavior including the HPA/Cluster-Autoscaler latency gap.
- **Sections exercised:** 36.4, 59.
- **Steps:** (1) Configure an HPA targeting 70% CPU utilization with min 2/max 10 replicas (Section 36.4.2), ensuring your Deployment has CPU `requests` set (a prerequisite, per Section 36.4.2's specific warning). (2) Enable Cluster Autoscaler on the node pool with defined min/max bounds. (3) Generate sustained load against the application (any simple load-generation tool) sufficient to trigger both HPA and, if node capacity is exhausted, Cluster Autoscaler. (4) Observe and time the delay between HPA deciding to add replicas and those replicas actually becoming `Running` versus remaining `Pending` — directly reproducing Section 59.6/36.4.1's two-layer latency gap firsthand.
- **Verify your understanding:** can you explain, from your own observed timestamps, why the HPA-decision timestamp and the pod-actually-running timestamp differ, and what specifically happened in between?

### 69.4.3 Lab 9: Implement a Complete DR Test

- **Objective:** using Lab 6's Bicep-deployed environment as a starting point, design and execute a simulated DR failover exercise.
- **Sections exercised:** 57, 58, 61.
- **Steps:** (1) Extend your Bicep templates to deploy the same environment structure in a second Azure region (directly reusing the modules from Lab 6, parameterized per Section 43.3.2/57.7.1's differentiated-per-workload approach). (2) Configure geo-replication for any data component in use. (3) Document a Recovery Plan-style runbook (even if not using actual ASR, structure the steps per Section 58.2.4's group/order/scripted-step pattern) for bringing the secondary region's environment online. (4) Actually execute a simulated failover following your runbook, timing the process against a self-defined RTO target. (5) Document any gaps discovered (directly modeling Section 57.7.2/58.5.3's "untested DR reveals gaps" principle) and revise the runbook.
- **Verify your understanding:** what gaps did your test actually reveal that your original design didn't anticipate? (If none were found, revisit whether the test was rigorous enough — a "perfect first test" is a common sign of an insufficiently realistic exercise.)

---

## 69.5 Capstone Project: End-to-End Production-Style Application

### 69.5.1 Objective

Synthesize the majority of this roadmap's Parts 7–12 material into one complete, deployed, production-style project — deliberately modeled on Section 66.2's Case Study 1 (E-Commerce Platform Migration and Modernization), scaled down to an individually-achievable scope.

### 69.5.2 Capstone Requirements Checklist

- [ ] A containerized application (Section 33) deployed to AKS (Sections 35–37), with images stored in ACR (Section 34).
- [ ] Infrastructure provisioned entirely via Bicep or Terraform (Sections 43–45), version-controlled.
- [ ] A CI/CD pipeline (Section 42 or 46) implementing environment promotion (dev → production) with an approval gate.
- [ ] Secrets sourced from Key Vault via Managed Identity/Workload Identity (Sections 9, 36.5.4, 53) — zero plaintext credentials anywhere.
- [ ] Application Insights instrumentation (Section 49) with at least one custom event tracked.
- [ ] At least one alert rule (Section 50) configured with an action group.
- [ ] Azure Policy (Section 54) enforcing at least one baseline configuration requirement (e.g., required tags, Section 61.3.4).
- [ ] Network security (Section 56) — NSGs at minimum, WAF if a public-facing component exists.
- [ ] HPA and Cluster Autoscaler configured (Section 36.4), tested per Lab 8's approach.
- [ ] Cost review — right-sizing check and a documented note on which pricing model (Section 60) would be appropriate at production scale.

### 69.5.3 Self-Assessment Rubric

| Criterion | Self-Check Question |
|---|---|
| Security | Can you demonstrate zero plaintext secrets exist anywhere in your codebase/configuration? |
| Resilience | If you deleted a random pod right now, would the application remain available? |
| Governance | If a new resource violated your Azure Policy baseline, would it actually be blocked, or only logged? |
| Cost-awareness | Can you state, with a specific number, what this environment costs per month, and identify the single largest cost driver? |
| Observability | Could you answer "why did this specific request fail" using only your KQL/Application Insights setup, without guessing? |

---

## 69.6 Key Takeaways Summary

🔑 Hands-on execution surfaces the specific, concrete details (exact CLI syntax, real error messages, genuine timing/latency observations) that reading alone cannot provide — Lab 8's HPA/Cluster-Autoscaler latency observation specifically cannot be genuinely internalized without actually watching it happen.

🔑 Each lab's "Verify your understanding" checkpoint is intentionally designed to require explaining *why*, not just confirming *that* something worked — matching this roadmap's repeated emphasis (Section 11's depth-bar test) on senior-level, not merely surface-level, comprehension.

🔑 The capstone project's self-assessment rubric mirrors the exact kind of scrutiny a genuine production readiness review or a rigorous interview would apply — completing it honestly is more valuable than completing it quickly.

---

## 69.7 Related Concepts and What Comes Next

- **All of Parts 7–12 (prerequisite, completed):** every lab in this section directly exercises specific sections' material as named explicitly per lab.
- **Section 66 (prerequisite, completed):** the case-study format this section's capstone project directly scales down from.
- **Section 70 — Key Takeaways Checklist & Recommended Next Topics (final section):** the roadmap's concluding wrap-up, consolidating this entire knowledge base.

---

*End of Section 69. Next: Section 70 — Key Takeaways Checklist & Recommended Next Topics (Final Section).*
