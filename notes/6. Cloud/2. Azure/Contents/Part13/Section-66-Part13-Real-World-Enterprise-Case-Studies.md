# Section 66 — Real-World Enterprise Case Studies

**Part 13: Enterprise Architecture & Comparisons | Section 66 of 70 (Final Section of Part 13)**
**Prerequisites:** All prior sections of Part 13 (62–65); broad familiarity with Parts 7–12
**Leads into:** Part 14 — Interview Preparation & Wrap-Up (Section 67, Consolidated Interview Question Bank)

---

## 66.1 Introduction and Scope

This final section of Part 13 synthesizes this entire roadmap's material into three complete, illustrative case studies — composite, representative enterprise scenarios (not real, named companies, consistent with this roadmap's anti-hallucination principles, Section 15, which prohibit inventing unverifiable specific facts) that walk through end-to-end architectural reasoning spanning every Part of this roadmap. Each case study explicitly traces which prior sections' material informs each design decision, demonstrating the kind of cumulative, cross-referencing architectural thinking this roadmap has modeled throughout its architect-level interview answers.

🔑 **Key Takeaway:** real enterprise architecture decisions are never single-topic exercises — every case study in this section deliberately spans compute, networking, data, security, DevOps, observability, and cost considerations simultaneously, because that is how genuine architectural work actually happens. This section's purpose is demonstrating that synthesis explicitly, one final time, before Part 14's interview-preparation material.

---

## 66.2 Case Study 1: E-Commerce Platform Migration and Modernization

### 66.2.1 Scenario

A mid-sized retail company runs its e-commerce platform on aging on-premises infrastructure (a monolithic .NET application on Windows Server VMs, a single SQL Server database, no automated deployment pipeline) and needs to migrate to Azure while modernizing toward a more resilient, scalable architecture, driven by recent revenue growth straining the existing infrastructure and a board-level mandate to reduce infrastructure operational risk within 12 months.

### 66.2.2 Phase 1: CAF Strategy and Plan (Section 62.2.2)

- **Strategy:** the business motivation is explicitly named (revenue growth straining infrastructure, board-mandated risk reduction) — directly following Section 62.2.2's Strategy methodology's emphasis on articulating concrete business motivations before any technical work begins.
- **Plan:** a digital estate assessment inventories the existing on-premises environment — informed by deploying **Azure Arc** (Section 64.3) to the existing on-premises servers early in the process specifically to gain Azure-tooling-based visibility into actual resource utilization and dependencies (Section 64.7.2's direct application), informing migration sequencing and sizing decisions with real data rather than guesswork.

### 66.2.3 Phase 2: Landing Zone Foundation (Section 62)

- Before any workload migration, establish a **Landing Zone** (Section 62.3) using the Azure Landing Zones reference implementation (Section 62.5.1) — Platform subscriptions for Connectivity (hub VNet, Azure Firewall, Section 56.2.4) and Management (centralized Log Analytics, Section 47–48), and an initial Application Landing Zone subscription structure separating Production from Staging/Development (Section 63.3.3's environment-isolation reasoning).
- Baseline governance (required tags per Section 61.3.3, Defender for Cloud auto-provisioning per Section 52.8.1, Azure Policy baseline per Section 54) assigned at the Landing Zones management group scope from day one, ensuring every subsequently-created subscription/resource inherits consistent governance automatically.

### 66.2.4 Phase 3: Compute and Application Modernization

- The monolithic .NET application is containerized (Section 33's Docker fundamentals — Dockerfile authored following Section 33.6's multi-stage build and security guidance), with images pushed to **ACR** (Section 34), authenticated via Managed Identity (Section 34.4.2).
- Given the "reduce operational risk" mandate and the application's genuine need for horizontal scalability under growth, deploy to **AKS** (Sections 35–37) rather than lift-and-shift to VMs — chosen specifically because the growth-driven scalability requirement and multi-tier application architecture (web, API, background job processing) benefit from Kubernetes' orchestration capability (Section 35.2.2's stated problem-solving rationale) more than a simpler PaaS option would provide, accepting AKS's higher operational complexity (Section 33.11.1's comparison table) as a justified trade-off given the stated growth trajectory.
- The AKS cluster is configured with **Azure CNI Overlay** networking (Section 36.2.5, the generally-recommended default), **Cluster Autoscaler and HPA** (Section 36.4) tuned per Section 59's autoscaling framework — combining schedule-based scaling for predictable daily traffic patterns with metric-based scaling for genuine demand variability (Section 59.3's combined-trigger guidance).

### 66.2.5 Phase 4: Data Migration and Modernization

- The single SQL Server database migrates to **Azure SQL Database** (Section 28) using the **Azure Database Migration Service** (Section 32), with data validation and a defined cutover plan (Section 32.14) minimizing production risk during the transition.
- Given the board-mandated risk-reduction goal, configure **zone-redundant** SQL Database deployment (Section 57.4.3's "prefer zones when available" default) and **geo-replication/failover groups** (Section 28.15) to a paired region, directly satisfying the stated infrastructure-risk-reduction mandate with a concrete, specific mechanism.

### 66.2.6 Phase 5: CI/CD and Observability

- A CI/CD pipeline (Azure DevOps Pipelines, Section 42, or GitHub Actions, Section 46.5, chosen based on where source code already resides per Section 46.6.1's guidance) builds, tests, and deploys the containerized application to AKS following the **environment-promotion pattern** (Section 46.2) — one artifact built, promoted unchanged through dev/staging/production — using a **canary deployment strategy** (Section 46.3.4) for production given the platform's genuine revenue-criticality, directly reusing this roadmap's own recurring checkout-service example pattern (Sections 46, 57, 58, 59) now applied concretely to this case study's actual scenario.
- **Application Insights** (Section 49) is instrumented across the application, with alert rules (Section 50) monitoring version-specific error rates gating the canary promotion decision (directly resolving Section 50's own senior-level interview scenario, now applied here).

### 66.2.7 Phase 6: DR and Ongoing Operations

- **Azure Site Recovery** is evaluated for any remaining VM-based components, while the AKS-hosted application's DR strategy follows Section 37.5.3/58.2.5's guidance — GitOps-based cluster reconstruction (Section 46.4) in a secondary region, combined with the SQL Database failover group already established in Phase 4.
- RTO/RPO targets (Section 57.2.3) are explicitly defined through business-stakeholder conversation (not set unilaterally by engineering), directly informed by the board's stated risk-reduction mandate translating into concrete, numeric resilience targets.
- Ongoing cost optimization (Section 60) applies right-sizing review and **Reserved Instances/Savings Plans** for the now-predictable steady-state AKS node pool capacity, while a **Spot node pool** (Section 60.2.5/37.4.3) handles the platform's batch/background-job processing tier specifically, given its genuine interruption tolerance.

---

## 66.3 Case Study 2: Financial Services Firm — Multi-Region, Compliance-Heavy Platform

### 66.3.1 Scenario

A financial services firm building a new customer-facing trading platform must satisfy strict regulatory requirements (data residency within a specific country, customer-controlled encryption key revocation capability, demonstrable audit trails), needs near-zero RTO/RPO given the direct financial impact of any downtime, and must integrate with existing on-premises mainframe systems that cannot be migrated in the foreseeable future.

### 66.3.2 Compliance and Data Residency Foundation

- Directly applying **Section 55.7.1**: all data-storing resources are deployed exclusively within an Azure region located in the required country, enforced via **Azure Policy** location-restriction assignments (Section 54) at management-group scope, preventing any team from accidentally deploying non-compliant regional resources.
- **Customer-managed keys** (Section 55.5.2–55.5.3) are adopted specifically because of the stated revocation-capability requirement — stored in a dedicated **Key Vault** (Section 53) with **purge protection enabled** (Section 53.6.2, essential given this vault protects genuinely critical financial data) and tightly scoped RBAC (Section 53.4.3) restricting revocation-capable identities.
- The **Regulatory Compliance Dashboard** (Section 55.4) tracks the firm's posture against the specific applicable financial-services regulatory standard, with the explicit understanding (Section 55.4.2's warning) that this technical-configuration compliance signal complements, but doesn't replace, the firm's own independent audit process covering non-technical requirements.

### 66.3.3 Near-Zero RTO/RPO Architecture

- Given the stated near-zero RTO/RPO requirement (directly connecting to Section 57.6.1's DR pattern spectrum), the platform adopts an **active-active architecture** — the highest-cost, highest-complexity point on that spectrum, explicitly justified here (per Section 57.7.1's differentiated-investment guidance) by the direct, severe financial impact of downtime for a trading platform specifically, in contrast to Case Study 1's less extreme canary/warm-standby approach for a different risk profile.
- **Azure Front Door** (Section 25) provides global traffic distribution across the active-active regions, with the application architecture itself designed for the data-consistency challenges active-active inherently introduces (Section 37.5.3's explicit warning about this being a genuine, non-trivial application-design consideration, not merely an infrastructure configuration).
- **Cosmos DB** (Section 29) with multi-region write capability is selected for state requiring this active-active consistency model, given its native multi-region architecture, over SQL Database's more traditional primary-replica geo-replication model (Section 28.15) — a deliberate data-service choice driven directly by the active-active requirement.

### 66.3.4 Hybrid Integration with On-Premises Mainframe Systems

- Given the stated on-premises mainframe integration requirement that cannot be migrated, **ExpressRoute** (Section 26) provides private, high-bandwidth, low-latency connectivity between the Azure environment and the on-premises datacenter — chosen over a VPN Gateway specifically given the financial platform's latency/reliability sensitivity for the mainframe integration path.
- **Azure Arc** (Section 64) is evaluated for the on-premises servers hosting mainframe-adjacent integration services (not the mainframe itself, which falls outside Arc's server/Kubernetes-focused scope, per Section 64.6.2's explicit scope-limitation warning), bringing those specific integration servers under unified Azure governance/monitoring where Arc's actual scope genuinely applies.

### 66.3.5 Security and Network Architecture

- The full **defense-in-depth** network security stack (Section 56.5.1) is applied given the platform's high-value target profile: DDoS Network Protection tier (Section 56.4.2, clearly justified for a financial trading platform), WAF at both Front Door and Application Gateway layers (Section 56.3.2), and Azure Firewall with FQDN-based egress restriction (Section 56.2.3) for the AKS-hosted trading-logic components.
- **Defender for Cloud** (Section 52) with the relevant Defender plans enabled across every resource type in use, given the platform's security-critical profile fully justifying comprehensive CWPP coverage (Section 52.4.4's risk-based enablement guidance, here resolving clearly toward "enable broadly" given the stated risk profile).

---

## 66.4 Case Study 3: Healthcare SaaS Provider — Multi-Tenant Application on Shared Infrastructure

### 66.4.1 Scenario

A healthcare technology SaaS provider serves many independent hospital-system customers from a shared Azure platform, requiring strict per-customer data isolation (regulatory requirement, not merely a preference), a cost-efficient shared-infrastructure model (given competitive SaaS pricing pressure), and rapid onboarding of new customers without proportionally scaling operational overhead.

### 66.4.2 Application-Level vs. Infrastructure-Level Multi-Tenancy (Direct Application of Section 63.5.1's Distinction)

- This scenario is explicitly the "SaaS provider's own application-level multi-tenancy" case named in **Section 63.5.1** as distinct from Azure/Entra-ID tenancy itself — the provider operates within its **own single Entra ID tenant** (Section 63.2.2's guidance against unnecessary multi-tenant Azure architecture), building its customer-facing multi-tenancy as an application-level concern layered on top of shared Azure infrastructure, not by giving each hospital-system customer their own Azure/Entra ID tenant.

### 66.4.3 Data Isolation Strategy

- Given the stated strict regulatory data-isolation requirement, the platform adopts a **per-customer AKS namespace** isolation model (Section 35.5.5) as the baseline, layered with **Kubernetes Network Policies** (Section 36.6.4) enforcing default-deny, explicit-allow traffic isolation between customer namespaces — directly applying Section 36.6.4's exact default-deny pattern to satisfy the regulatory isolation requirement within the shared cluster.
- For data storage specifically, given the regulatory strength of the isolation requirement, the platform uses **per-customer Cosmos DB containers or databases** (Section 29) rather than a shared, row-level-isolated schema — a deliberate, more conservative isolation choice justified by the regulatory (not merely competitive) nature of the requirement, directly connecting to Section 35.11's explicit warning that namespace-level isolation is *logical*, not hard, isolation — for a genuine regulatory requirement of this strength, the platform architects toward stronger, more explicit isolation boundaries than namespace-level controls alone would provide, exactly as Section 35.11 and Section 36.10's architect-level scenario both anticipated as the appropriate escalation path when logical isolation isn't sufficient.
- **Customer-managed keys per customer** (Section 55.5.2) are evaluated specifically for hospital-system customers with their own additional key-revocation compliance requirements, layered on top of the baseline namespace/database isolation.

### 66.4.4 Cost-Efficient Shared Infrastructure

- Despite the strong isolation requirements, the underlying **AKS cluster infrastructure itself is shared** across all customers (a single cluster with per-customer namespace isolation, rather than a dedicated cluster per customer) — directly balancing the isolation requirement (satisfied at the namespace/network-policy/data layer, 66.4.3) against the cost-efficiency requirement (satisfied by shared node pool infrastructure, avoiding the operational and cost overhead of Section 35.8's "many small clusters" extreme) — a deliberate middle-ground resolution of the exact trade-off Section 35.8 named explicitly as a genuine, no-universal-answer architectural decision.
- **Cluster Autoscaler and HPA** (Section 36.4) scale the shared infrastructure elastically as the customer base grows, with **Reserved Instances** (Section 60.2.2) covering the predictable baseline node capacity and **Savings Plans** (Section 60.2.3) or pay-as-you-go covering the more variable growth-driven scale-out, directly applying Section 60.2.4's decision framework to this specific, growing-but-partially-predictable capacity profile.

### 66.4.5 Rapid Customer Onboarding Automation

- New customer onboarding (namespace creation, network policy application, Cosmos DB container provisioning, tag assignment per Section 61.3.3) is fully automated via **Infrastructure as Code** (Bicep or Terraform, Sections 44–45) triggered through a **CI/CD pipeline** (Section 42/46), directly satisfying the "rapid onboarding without proportional operational overhead" requirement — treating customer onboarding itself as a governed, repeatable deployment process rather than manual per-customer configuration, directly extending Section 63.7.1's subscription-vending automation principle to customer-tenant onboarding specifically within this shared-infrastructure model.

---

## 66.5 Cross-Case-Study Synthesis

### 66.5.1 The Common Thread

🔑 **Key Takeaway:** despite covering three genuinely different industries, scales, and requirement profiles, all three case studies draw on the **same underlying architectural toolkit** covered throughout this roadmap — Landing Zones for governance foundation, the HA/DR pattern spectrum matched to actual business-criticality, differentiated pricing-model selection matched to usage predictability, defense-in-depth security layering, and IaC/CI-CD-driven automation for consistency and speed. The specific choices differ (canary vs. active-active deployment strategy; namespace-level vs. per-database isolation; AKS vs. simpler PaaS) precisely because each scenario's actual requirements differ — but the underlying decision-making *framework* applied to reach those choices is identical across all three, and across this entire roadmap.

### 66.5.2 Why This Matters for Interview and Real-World Practice

🎯 **Interview Tip:** the strongest system-design interview answers (Section 68, upcoming) demonstrate exactly this pattern — not reciting a memorized "correct" architecture, but applying a consistent decision framework (business requirement → specific Azure service/pattern selection → explicit trade-off justification) to whatever specific scenario is presented, exactly as this section's three case studies have modeled explicitly across three different domains.

---

## 66.6 Key Takeaways Summary

🔑 Every real enterprise architecture decision spans multiple roadmap Parts simultaneously (compute, data, networking, security, DevOps, observability, cost) — no genuine architectural exercise is a single-topic decision.

🔑 The Landing Zone foundation (Section 62) is the appropriate starting point for any genuine enterprise Azure adoption, established before workload-specific decisions, exactly as Case Study 1 modeled explicitly.

🔑 HA/DR investment level, isolation strategy strength, and pricing-model selection should each be explicitly matched to the specific scenario's actual business-criticality and regulatory requirements — the same underlying decision framework, applied to genuinely different conclusions across the three case studies given their different actual requirements.

🔑 SaaS multi-tenancy (Case Study 3) is an application-level architectural concern distinct from Azure/Entra ID tenancy itself (Section 63.5.1's explicit distinction), satisfied via namespace/network-policy/data-layer isolation on shared infrastructure, not via separate Azure tenants per customer.

🔑 This section's three case studies collectively demonstrate that this roadmap's recurring architectural principles (centrally-owned-vs-team-owned organization, preview-before-enforce governance rollout, defense-in-depth layering, business-driven RTO/RPO/cost-ceiling decisions) are genuinely transferable across industries and scales, not isolated to any single scenario type.

---

## 66.7 Part 13 Complete: Consolidated Dependency Recap

```
Section 62 (Landing Zones & CAF) — the governance/organizational foundation
        ▼
Section 63 (Multi-Subscription/Multi-Tenant Architecture) — scaling that foundation across subscriptions
        ▼
Section 64 (Hybrid & Multi-Cloud, Azure Arc) — extending governance beyond pure Azure
        ▼
Section 65 (Azure vs. AWS vs. GCP) — provider-selection context
        ▼
Section 66 (Real-World Enterprise Case Studies)  ← this section
   synthesizing the entire roadmap into complete, illustrative end-to-end scenarios
```

Part 13 is now complete, providing the enterprise-architecture synthesis layer connecting every technical Part of this roadmap (1–12) into coherent, real-world-applicable architectural practice.

---

## 66.8 Related Concepts and What Comes Next

- **All of Parts 1–13 (prerequisite, completed):** this section synthesizes the entire roadmap's material into concrete scenarios.
- **Section 67 — Consolidated Interview Question Bank (Part 14, next):** begins the roadmap's final Part, organizing interview preparation material across every topic covered, building directly on the case-study-driven reasoning patterns modeled in this section.
- **Section 68 — System Design Questions (Azure-Based) (upcoming, Part 14):** directly extends this section's case-study format into a dedicated, practice-oriented system-design interview preparation section.
- **Section 69 — Hands-On Labs & Mini-Projects (upcoming, Part 14):** provides practical exercises directly modeled on this section's case-study scenarios.

---

*End of Section 66. End of Part 13 — Enterprise Architecture & Comparisons. Next: Section 67 — Consolidated Interview Question Bank (Part 14 — Interview Preparation & Wrap-Up).*
