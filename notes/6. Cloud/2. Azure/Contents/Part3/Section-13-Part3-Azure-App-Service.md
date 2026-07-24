# Section 13 — Azure App Service (PaaS Compute)

## 13.1 Definition

**Plain language:** Azure App Service lets you deploy a web application, API, or mobile backend by just handing Azure your code (or container), without ever creating, patching, or managing a VM yourself — Azure runs it on infrastructure it fully manages.

**Precise definition:** Azure App Service is a fully managed Platform-as-a-Service (PaaS) offering for hosting web applications, REST APIs, and mobile backends, supporting multiple languages and frameworks natively or via custom containers, with built-in support for autoscaling, deployment slots, custom domains/TLS, and integration with CI/CD pipelines — Microsoft manages the underlying OS, runtime patching, and infrastructure entirely, per the PaaS responsibility model introduced in Section 2.5.

## 13.2 Why It Exists / Problem It Solves

Running a web application on IaaS VMs (Section 11) or a VM Scale Set (Section 12) requires the customer to manage OS patching, runtime installation and updates, web server configuration, scaling logic, and load balancing — substantial operational overhead for a very common use case (hosting a web app or API) that, in the majority of cases, doesn't actually require OS-level customization. App Service exists to eliminate that overhead entirely for this common case: the customer supplies application code or a container image, and Azure handles everything below the application layer, letting development teams deploy and iterate faster without needing dedicated infrastructure operations expertise for every project.

## 13.3 Core Concepts

### 13.3.1 App Service Plan

**Definition:** An **App Service Plan** defines the underlying compute resources (VM size, region, OS) that one or more App Service apps run on, and determines available features (custom domains, scaling limits, deployment slots) based on its **pricing tier**.

**Pricing tier categories (conceptual, verify current exact tier names/limits):**
- **Free/Shared tiers** — for development/testing only, with significant limitations (no custom domain TLS, limited compute, shared infrastructure with other customers' apps at the compute level) — not appropriate for production.
- **Basic tier** — dedicated compute, suitable for low-traffic production or dev/test workloads needing dedicated resources, but with limited scaling and no deployment slots.
- **Standard/Premium tiers** — dedicated compute with full autoscaling, deployment slots, and higher performance limits, the standard choice for production workloads.
- **Isolated tier** — runs within a dedicated Azure App Service Environment for maximum network isolation, typically used for high-compliance or high-security requirements needing full network isolation from other customers' App Service infrastructure.

⚠️ Exact tier names, feature availability per tier, and pricing change over time — verify current tier structure against official documentation before making a tier selection for a real deployment.

**Multiple apps per plan:** Multiple App Service apps can share a single App Service Plan (and therefore its underlying compute), which is cost-efficient for several low-traffic applications, but means they also share that compute capacity — a "noisy neighbor" app consuming heavy resources can affect others on the same plan, an important capacity-planning consideration for enterprise multi-app deployments.

### 13.3.2 Supported Runtimes and Deployment Methods

App Service natively supports common language runtimes (as of general Azure practice: .NET, Java, Node.js, Python, PHP, Ruby — verify current supported runtime versions against documentation, since supported version lists are updated as language versions reach end-of-life) without requiring a container, as well as **custom containers** (Docker images) for workloads needing a runtime or dependency configuration outside the natively supported options.

**Common deployment methods:**
- **Continuous deployment from source control** — App Service can be configured to automatically deploy on every push to a connected GitHub/Azure DevOps repository branch, the standard modern pattern integrated with CI/CD (Part 9).
- **ZIP deploy** — pushing a pre-built application package directly, common in CI/CD pipeline steps.
- **Container deploy** — pointing App Service at a container image in Azure Container Registry (Section 34) or another registry.

### 13.3.3 Deployment Slots

**Definition:** A **Deployment Slot** is a separate, live instance of the app (with its own hostname) running under the same App Service Plan, most commonly used for staging a new version before it goes live in production.

**Why they matter:** The standard pattern is to deploy a new application version to a non-production slot (e.g., "staging"), validate it there against production-identical infrastructure, and then perform a **slot swap** — an operation that exchanges the staging and production slots' routing (and, depending on configuration, warms up the new version before the swap completes) with effectively zero downtime, and critically, allows near-instant rollback by swapping back if a problem is discovered post-swap.

💡 **Tip:** Deployment slots are only available at Standard tier and above (verify current tier requirement against documentation) — this is a common reason a team upgrades from Basic tier once they need safer deployment practices.

### 13.3.4 Scaling

App Service supports two scaling dimensions:
- **Scale up** (vertical) — moving to a higher App Service Plan tier/size for more CPU/memory per instance.
- **Scale out** (horizontal) — increasing the number of running instances behind the built-in load balancing, either manually or via autoscale rules (conceptually identical to the VM Scale Set autoscaling covered in Section 12.3.2, but managed entirely by the App Service platform rather than requiring the customer to configure a separate scale set and load balancer).

### 13.3.5 Networking Integration

By default, an App Service app is reachable over the public internet at a Microsoft-provided subdomain (`<app-name>.azurewebsites.net`), with support for custom domains and managed TLS certificates. For network isolation, App Service supports **VNet Integration** (allowing the app to reach resources inside a private Virtual Network, Section 21) and **Private Endpoints** (allowing inbound traffic to the app to be restricted to private network paths rather than the public internet) — these networking concepts are covered in depth in Part 5, and are commonly required in enterprise architectures where the app must reach a database or backend service that isn't publicly exposed.

## 13.4 Architecture Diagram

```
App Service Plan "asp-webapp-prod" (Standard S1 tier, 2 instances)
 │
 ├── App Service "app-webapp-prod"  (production slot)
 │      URL: app-webapp-prod.azurewebsites.net
 │
 └── Deployment Slot "staging"
        URL: app-webapp-prod-staging.azurewebsites.net
        (new version validated here before slot swap → production)

Autoscale: 2–6 instances based on CPU/memory metrics
VNet Integration: outbound calls reach private backend DB inside a VNet
```

## 13.5 Configuration & Hands-On Example

**Creating an App Service Plan and Web App:**
```bash
az appservice plan create \
  --resource-group rg-myapp-prod \
  --name asp-webapp-prod \
  --sku S1 \
  --is-linux

az webapp create \
  --resource-group rg-myapp-prod \
  --plan asp-webapp-prod \
  --name app-webapp-prod \
  --runtime "NODE:20-lts"
```
- **Purpose:** Creates a Standard-tier (`S1`) Linux-based App Service Plan, then a Web App running on Node.js within it.
- **Important arguments explained individually:**
  - `--sku` — the pricing tier/size; `S1` is a Standard-tier size supporting autoscaling and deployment slots, chosen deliberately over a Free/Basic tier for production readiness.
  - `--is-linux` — specifies the Linux-based App Service flavor rather than Windows; the choice affects available runtime stack options and is generally not changeable after plan creation without recreating it.
  - `--runtime` — specifies the language/version stack; exact accepted runtime strings should be verified against `az webapp list-runtimes` since supported versions are updated over time.
- **Common error:** Attempting to change `--is-linux` on an existing plan, or deploying a runtime unsupported on the chosen OS flavor, both require recreating the plan/app rather than an in-place change.

**Creating a deployment slot and performing a slot swap:**
```bash
az webapp deployment slot create \
  --resource-group rg-myapp-prod \
  --name app-webapp-prod \
  --slot staging

# ... deploy new version to the staging slot, validate it ...

az webapp deployment slot swap \
  --resource-group rg-myapp-prod \
  --name app-webapp-prod \
  --slot staging \
  --target-slot production
```
- **Purpose:** Demonstrates the full safe-deployment pattern: create a staging slot, deploy and validate the new version there, then swap it into production with near-zero downtime.
- **Production impact:** If an issue is discovered shortly after the swap, running the same swap command again (staging ↔ production) effectively rolls back to the previous version, since the previous production content is now sitting in the staging slot.

## 13.6 Production & Enterprise Usage

Enterprises use App Service extensively for internal and customer-facing web applications and APIs where full OS-level control isn't required, favoring it over VM-based hosting specifically to reduce operational burden and to standardize deployment patterns (deployment slots plus CI/CD) across many application teams without each team needing deep infrastructure expertise. Multi-region App Service deployments, combined with Azure Front Door or Traffic Manager (Part 5) for global routing and failover, are a common enterprise high-availability pattern, alongside VNet Integration to reach private backend databases without exposing them publicly — this pattern connects directly to the networking concepts covered in Part 5 and the HA/DR patterns formalized in Part 12.

## 13.7 Security Considerations

- Because App Service is internet-reachable by default via its `.azurewebsites.net` domain, restricting or disabling public access (via access restrictions, Private Endpoints, or requiring traffic to flow only through a fronting service like Front Door/Application Gateway) is an important consideration for apps that shouldn't be directly internet-accessible.
- Managed Identities (Section 9) are the recommended way for an App Service app to authenticate to other Azure resources (like Key Vault or a Storage Account), avoiding stored connection-string secrets in application configuration wherever possible.
- TLS should always be enforced (HTTPS-only setting), and Azure-managed certificates can handle custom domain TLS without the customer needing to manually procure or rotate certificates.

## 13.8 Performance Considerations

Cold start latency (the delay before an app instance is ready to serve its first request after being newly started, whether due to scale-out or a deployment) can matter for latency-sensitive applications — mitigated via "Always On" settings (keeping at least one instance warm continuously rather than scaling to zero) and by warming up new instances during slot swaps before they receive live production traffic.

## 13.9 Monitoring

App Service integrates natively with Application Insights (Section 49, covered fully in Part 10) for request tracing, dependency tracking, and performance monitoring, in addition to standard Azure Monitor platform metrics (CPU, memory, response time, HTTP error rates) available by default.

## 13.10 Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| Deployment succeeds but app shows a generic error page | Application startup failure, often a missing dependency or misconfigured runtime version | Check App Service log stream / Application Insights for the actual startup exception |
| App works fine at low traffic but degrades under load | Under-provisioned tier/instance count, or autoscale rules too conservative | Review scale-out rules and consider a higher tier or more aggressive scale-out thresholds |
| Slot swap causes a brief spike in errors immediately after swapping | New version wasn't properly warmed up before the swap completed | Configure swap with warm-up (application initialization) enabled before the swap fully redirects traffic |

## 13.11 Interview Questions — Section 13

### 🎯 Beginner
**Q: What's the main advantage of App Service over hosting a web application on a VM?**

*Model answer:* App Service is PaaS — Microsoft manages the OS, runtime patching, and underlying infrastructure entirely, so the team only manages application code and configuration. This removes the operational burden of OS patching, manual scaling configuration, and infrastructure management that a VM-hosted application would require, at the cost of less low-level control, which is usually an acceptable trade-off for standard web applications and APIs.

*What the interviewer is probing:* whether the candidate can connect App Service concretely back to the general PaaS-vs-IaaS trade-off established in Section 2.

### 🎯 Senior
**Q: How would you design a zero-downtime deployment process for a business-critical App Service application?**

*Model answer:* I'd use a Standard-or-above tier to enable deployment slots, deploying every new release first to a staging slot rather than directly to production, running automated smoke tests and/or manual validation against the staging slot (which runs on production-identical infrastructure), then performing a slot swap with warm-up enabled so the new version is fully initialized before it starts receiving live traffic — minimizing both downtime and cold-start-related errors during the transition. I'd keep the previous version readily available in the (now-staging) slot immediately after swap specifically so a fast rollback is just another swap away if a problem surfaces post-deployment, rather than requiring a fresh redeploy of the old version under pressure. For the broadest resilience, I'd also consider a multi-region App Service deployment with Front Door for global routing and automatic regional failover, layering that regional-level resilience on top of the slot-based deployment safety within each region.

*What the interviewer is probing:* whether the candidate has genuine familiarity with the deployment-slot pattern as a practical, specific mechanism, not just an awareness that "zero downtime deployment" is a good goal in the abstract.

## 13.12 Common Misconceptions

- **"App Service can't run containers, only specific language runtimes."** False — App Service supports custom container deployment for workloads needing dependencies or configurations outside the natively supported runtime stacks.
- **"Multiple apps on one App Service Plan are fully isolated from each other."** False — apps sharing a plan share its underlying compute capacity; heavy resource usage by one app can affect others on the same plan, a real capacity-planning consideration.

## 13.13 Key Takeaways

- 🔑 App Service is Azure's core PaaS web/API hosting offering — Microsoft manages OS and runtime; the customer manages only application code and configuration.
- 🔑 An App Service Plan defines the underlying compute and available features (based on pricing tier); multiple apps can share one plan, with shared-capacity trade-offs.
- 🔑 Deployment Slots enable safe, near-zero-downtime releases via deploy-to-staging-then-swap, with fast rollback by swapping again.
- 🔑 VNet Integration and Private Endpoints extend App Service into private networking scenarios, connecting it to the broader networking concepts covered in Part 5.

## 13.14 Related Concepts (Next Up)

Section 14 covers **Azure Functions** — Azure's serverless/FaaS compute offering (introduced conceptually in Section 2.7), representing a further step along the PaaS-to-serverless abstraction spectrum from App Service, where even the concept of a continuously-running app instance is abstracted away in favor of individually-triggered, independently-scaled function executions.
