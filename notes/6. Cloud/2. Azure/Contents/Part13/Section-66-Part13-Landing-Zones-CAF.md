# Section 66 — Landing Zones & Cloud Adoption Framework (CAF)

**Part 13: Enterprise Architecture & Comparisons | Section 66 of 70 (First Section of Part 13)**
**Prerequisites:** Section 46.6 (Deployment scopes), Section 57 (Azure Policy), Section 65 (Capacity Planning & Tagging)
**Leads into:** Section 67 (Multi-Subscription/Multi-Tenant Enterprise Architecture), Section 68 (Hybrid & Multi-Cloud/Azure Arc)

---

## 66.1 Introduction and Scope

This section formalizes the **Cloud Adoption Framework (CAF)** — Microsoft's structured methodology for planning and executing cloud adoption — and **Landing Zones**, the concrete architectural pattern CAF prescribes for a governed, scalable multi-subscription Azure environment. This section directly consolidates and formalizes the management-group hierarchy, baseline-policy, and hub-and-spoke patterns already referenced repeatedly throughout Parts 9–12 (Section 46.12's architect scenario, Section 55.8.1's auto-provisioning enforcement, Section 59.2.4's hub-and-spoke networking, Section 65.5.2's tagging-at-scale forward reference) into their proper, complete architectural context.

🔑 **Key Takeaway:** everything this roadmap has built toward across Parts 9–12 — management-group-scoped Policy enforcement, hub-and-spoke networking, centrally-owned-vs-team-owned resource organization, consistent tagging — is not a collection of separate best practices. It is, collectively, **what a Landing Zone actually is**. This section names and formalizes the pattern that dozens of prior architect-level scenario answers throughout this roadmap have already been implicitly constructing, piece by piece.

---

## 66.2 The Cloud Adoption Framework (CAF)

### 66.2.1 Definition

**Plain language:** the Cloud Adoption Framework is Microsoft's comprehensive, structured guidance for every phase of an organization's cloud journey — from initial strategy and business justification, through planning, technical readiness, adoption (migration and new development), governance, and ongoing management — providing a consistent methodology and vocabulary rather than a single technical product.

**Precise definition:** CAF is a lifecycle framework organized into distinct methodologies (Strategy, Plan, Ready, Adopt — itself split into Migrate and Innovate — Govern, Manage, Secure) providing prescriptive guidance, tools, and templates for each phase of cloud adoption, with Landing Zones (66.3) as its concrete technical/architectural output for the "Ready" phase specifically.

### 66.2.2 The CAF Methodologies (Brief Survey)

| Methodology                    | Focus                                                                                                                                                                                                                 |
| ------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Strategy**                   | Business justification, defining motivations (cost reduction, agility, migration off aging infrastructure) and expected business outcomes for cloud adoption — the organizational "why" preceding any technical work. |
| **Plan**                       | Translating strategy into an actionable adoption plan — digital estate assessment (inventorying current on-premises/existing infrastructure), organizational alignment, and a prioritized adoption roadmap.           |
| **Ready**                      | Preparing the actual Azure environment for adoption — this is where **Landing Zones** (66.3) are designed and provisioned, the primary technical output of this methodology phase.                                    |
| **Adopt (Migrate / Innovate)** | Executing the actual migration of existing workloads and/or new cloud-native development — directly connecting to this roadmap's Part 9 (CI/CD, IaC) as the technical execution mechanism for this phase.             |
| **Govern**                     | Ongoing governance — directly the domain of Section 57 (Azure Policy), Section 65.3 (tagging), and this section's Landing Zone baseline policy material.                                                              |
| **Manage**                     | Ongoing operations — directly the domain of Part 10 (Monitoring & Observability) and Part 12 (HA/DR/Scaling/Cost).                                                                                                    |
| **Secure**                     | Ongoing security posture — directly the domain of Part 11 (Security & Governance).                                                                                                                                    |

🔑 **Key Takeaway, connecting CAF to this entire roadmap's structure:** CAF's Govern, Manage, and Secure methodologies are not new topics this section introduces — they are the **organizing framework retroactively contextualizing** everything covered in Parts 10–12 of this roadmap. Recognizing this explicitly is valuable: a candidate who can say "our governance approach follows CAF's Govern methodology, implemented via Azure Policy and management-group-scoped enforcement" demonstrates structured, framework-aware thinking beyond just knowing the individual Azure services.

---

## 66.3 Landing Zones

### 66.3.1 Definition

**Plain language:** a Landing Zone is the pre-provisioned, governed multi-subscription Azure environment — the management group hierarchy, baseline policies, networking topology, identity configuration, and monitoring foundation — that new workloads land into, providing consistent guardrails, security, and connectivity from day one, rather than each new workload/team building its own governance and networking foundation from scratch.

**Precise definition:** a Landing Zone is a logical construct representing the standardized subscription-level environment provisioned according to CAF's Ready methodology, comprising a management group hierarchy, baseline Azure Policy assignments, hub-and-spoke (or Virtual WAN-based) network topology, centralized identity/RBAC foundation, and platform-level monitoring/logging — into which application workloads are subsequently deployed.

### 66.3.2 Why the "Landing Zone" Concept Exists — What Problem It Solves

- **Without a Landing Zone, every team reinvents governance independently:** without a standardized, pre-provisioned foundation, each new application team creating a new subscription would need to independently figure out (and likely inconsistently implement) networking connectivity, security baseline configuration, monitoring setup, and RBAC — repeating work that should be done once, centrally, and consistently. This is the direct, formal generalization of every "centrally-owned-vs-team-owned" pattern this roadmap has established piecemeal across Log Analytics (Section 50.8), Terraform state (Section 48.8), Defender for Cloud (Section 55), Key Vault (Section 56), and tagging (Section 65) — a Landing Zone is the single, comprehensive architectural pattern unifying all of those individually-covered instances into one coherent whole.
- **Consistency at scale:** a well-designed Landing Zone ensures that whether an organization has 5 subscriptions or 500, every new subscription automatically inherits the same baseline governance, security, and connectivity — directly enabling the management-group-scoped Policy enforcement pattern (Section 57.5.1) to actually deliver on its "current and future subscriptions" promise at genuine scale.

### 66.3.3 Landing Zone Types (Platform vs. Application Landing Zones)

| Type                                         | Purpose                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| -------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Platform Landing Zones**                   | Centrally-managed, shared foundational subscriptions — typically including a **Connectivity** subscription (hosting the hub VNet, Azure Firewall, ExpressRoute/VPN Gateway, Section 26/56.2.4), an **Identity** subscription (for organizations extending on-premises AD via domain controllers in Azure — connecting to Section 6's Entra ID/hybrid-identity concepts), and a **Management** subscription (hosting centralized Log Analytics workspaces, Section 50–51; centralized Azure Automation; centralized security tooling). |
| **Application (Landing Zone) Subscriptions** | The subscriptions where actual application workloads are deployed by individual teams — spoke VNets connecting to the platform's hub (Section 59.2.4), inheriting the platform-level baseline policies (Section 57.5.1) automatically via management-group-scoped assignment, but with the application team retaining day-to-day ownership and deployment autonomy within those inherited guardrails.                                                                                                                                 |

### 66.3.4 Reference Management Group Hierarchy

```
Tenant Root Group
  └── Intermediate Root Management Group (e.g., "Contoso")
        ├── Platform
        │     ├── Connectivity  (hub VNet, Firewall, ExpressRoute/VPN)
        │     ├── Identity       (domain controllers, if hybrid identity)
        │     └── Management     (centralized Log Analytics, Automation)
        ├── Landing Zones
        │     ├── Corp           (internal-facing application subscriptions)
        │     └── Online         (internet-facing application subscriptions)
        ├── Sandbox               (experimentation, isolated from production connectivity)
        └── Decommissioned        (subscriptions pending removal)
```

- This hierarchy structure directly applies Section 46.6.1's deployment-scope material and Section 57.5's assignment-inheritance model concretely: baseline policies (network restrictions, required tags per Section 65.3.4, security defaults per Section 55.8.1) are assigned at the **Landing Zones** management group (or even higher, at the intermediate root, for genuinely universal requirements), automatically inheriting down to every current and future subscription placed under it — while the **Platform** management group's own, distinct set of policies apply specifically to the shared infrastructure subscriptions.
- ⚠️ **Warning:** this exact hierarchy structure and naming is Microsoft's commonly-published reference/example, not a rigid mandate — organizations adapt it to their own specific structure and naming conventions; verify current specific Microsoft reference architecture details against official CAF documentation, as this guidance continues to evolve.

### 66.3.5 Sandbox Subscriptions

- **Definition:** deliberately isolated subscriptions (typically disconnected from the platform's hub-and-spoke production connectivity, 56.2.4) for genuine experimentation/proof-of-concept work, where teams need freedom to try things without the full production governance/networking constraints, while remaining logically separate from anything that could affect production connectivity or security posture — a deliberate, explicit "safe space" carved out of the overall governance model, rather than either forcing every experiment through full production guardrails or allowing ungoverned experimentation to risk production systems.

---

## 66.4 Design Areas (CAF's Structured Landing Zone Design Checklist)

### 66.4.1 The Eight Design Areas

CAF's Ready methodology structures Landing Zone design decisions across eight areas, each directly mapping to material already covered in depth throughout this roadmap:

| Design Area                           | Direct Roadmap Connection                                                           |
| ------------------------------------- | ----------------------------------------------------------------------------------- |
| **Azure billing and Entra ID tenant** | Section 4 (subscriptions), Section 6 (Entra ID)                                     |
| **Identity and access management**    | Part 2 (Sections 6–10)                                                              |
| **Resource organization**             | Section 4 (management groups/subscriptions/resource groups), Section 65.3 (tagging) |
| **Network topology and connectivity** | Section 21–28 (Part 5), Section 59.2.4 (hub-and-spoke)                              |
| **Security**                          | Part 11 (Sections 55–59)                                                            |
| **Management**                        | Part 10 (Sections 50–54)                                                            |
| **Governance**                        | Section 57 (Azure Policy)                                                           |
| **Platform automation and DevOps**    | Part 9 (Sections 45–49)                                                             |

🔑 **Key Takeaway:** this table is the clearest possible illustration of this section's core framing — CAF's eight Landing Zone design areas are not new technical content; they are a **structured checklist organizing everything this entire roadmap has already taught**, into the specific decision points an organization must address when actually building a governed, production-ready Azure environment. Part 13 exists precisely to provide this organizing, synthesizing structure over Parts 1–12's technical depth.

---

## 66.5 Production and Enterprise Usage

### 66.5.1 Enterprise-Scale Landing Zone (Azure Landing Zones / ALZ)

- Microsoft publishes reference implementations — commonly referred to as **Azure Landing Zones (ALZ)** — providing pre-built Bicep/Terraform modules (directly reusing Section 47/45's IaC skills) implementing the management group hierarchy, baseline policies, and hub-and-spoke networking pattern described in this section, as an accelerator rather than requiring every organization to design and build this foundational architecture entirely from scratch — directly paralleling the "start from Azure Verified Modules rather than hand-authoring from scratch" principle already established in Section 47.4.4, now applied at the whole-Landing-Zone scale.

### 66.5.2 Landing Zone as a Living, Evolving Foundation

💡 **Tip:** directly extending this roadmap's recurring "governance/posture requires ongoing attention" theme (Sections 54.5.1, 55.3.3, 57.8.1, 64.6.1): a Landing Zone is not a one-time build-and-forget foundation — baseline policies evolve as security/compliance requirements change (Section 58), network topology may need to expand (additional regions, additional connectivity requirements), and the management group structure itself may need to adapt as organizational structure changes — treating the Landing Zone as a continuously-maintained platform, with its own IaC-managed (Section 46–48), version-controlled, CI/CD-deployed (Section 45/46) configuration, exactly like any other production system covered throughout this roadmap.

---

## 66.6 Troubleshooting Reference

| Symptom                                                                                                             | Likely Cause                                                                                                                                                                   | Diagnostic Step                                                                                                                                                                                                                                |
| ------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A new application team's subscription doesn't automatically receive expected baseline policies/network connectivity | Subscription placed under the wrong management group in the hierarchy (e.g., left under a default/ungoverned group rather than moved into the Landing Zones hierarchy, 66.3.4) | Verify the subscription's actual management group placement; move it under the correct Landing Zone management group                                                                                                                           |
| Teams report the Landing Zone's baseline policies are too restrictive for a legitimate, specific use case           | No exemption process established (directly reusing Section 57.2.3's exemption mechanism)                                                                                       | Establish a documented exemption request/review process, rather than either universally loosening the baseline or leaving legitimate use cases permanently blocked                                                                             |
| Landing Zone's hub-and-spoke connectivity doesn't scale to a new region the organization is expanding into          | Original network topology design didn't account for multi-region growth                                                                                                        | Review and extend the hub-and-spoke topology (potentially introducing an additional regional hub, or migrating to Azure Virtual WAN for larger-scale, multi-region connectivity needs — a topic outside this roadmap's current explicit scope) |

---

## 66.7 Best Practices Checklist

- [ ] Landing Zone architecture explicitly separates Platform (shared, centrally-owned) subscriptions from Application Landing Zone (team-owned) subscriptions.
- [ ] Baseline policies assigned at the appropriate management-group scope to automatically cover current and future subscriptions.
- [ ] Sandbox subscriptions provided as an explicit, isolated space for experimentation, distinct from production connectivity/governance.
- [ ] Azure Landing Zones (ALZ) reference implementation/accelerator evaluated before designing a Landing Zone entirely from scratch.
- [ ] Landing Zone treated as a living, IaC-managed, continuously-evolving platform, not a one-time initial build.
- [ ] Exemption process established for legitimate exceptions to baseline policy, avoiding both universal loosening and permanently blocking valid use cases.

---

## 66.8 Common Misconceptions

- "A Landing Zone is a single Azure resource or a specific product you deploy." _Correction:_ it's an architectural pattern/logical construct — a management group hierarchy plus baseline policies plus networking plus identity foundation — not a single deployable resource, though Microsoft's ALZ reference implementation (66.5.1) provides accelerator tooling to build one.
- "CAF is purely a technical framework." _Correction:_ CAF spans the full adoption lifecycle including business strategy and organizational planning (Strategy, Plan methodologies), not only the technical Ready/Govern/Manage/Secure methodologies — a common oversimplification.
- "Once a Landing Zone is built, the foundational work is complete." _Correction:_ a Landing Zone requires ongoing maintenance and evolution as requirements, scale, and organizational structure change (66.5.2) — not a one-time deliverable.

---

## 66.9 Interview Questions (Consolidated)

**Beginner:** "What is a Landing Zone, and why does an organization need one rather than letting each team set up their own subscription independently?"
_Model answer:_ a Landing Zone is the pre-provisioned, governed multi-subscription environment — management group hierarchy, baseline policies, networking, identity foundation — that new workloads land into. Without it, each team creating a subscription independently would need to reinvent governance, security baseline, and network connectivity from scratch, almost certainly inconsistently — a Landing Zone ensures every subscription automatically inherits the same baseline guardrails and connectivity, providing consistency at scale rather than requiring per-team reinvention.

**Intermediate:** "Explain the difference between a Platform Landing Zone subscription and an Application Landing Zone subscription."
_Model answer:_ Platform Landing Zone subscriptions are centrally-managed, shared foundational subscriptions — typically Connectivity (hosting the hub VNet, firewall, gateways), Identity (for hybrid-identity scenarios), and Management (centralized logging/automation) — owned and operated by a central platform team. Application Landing Zone subscriptions are where individual application teams actually deploy their workloads, connecting as spokes to the platform's hub and automatically inheriting the platform's baseline policies via management-group-scoped assignment, while the application team retains day-to-day deployment autonomy within those inherited guardrails.

**Senior:** "Your organization built its Landing Zone two years ago, and a recent audit found that several newer subscriptions are missing baseline security policies that older subscriptions have. What's the likely cause, and how should this be prevented going forward?"
_Model answer:_ the most likely cause is that the newer subscriptions were placed under the wrong management group in the hierarchy — perhaps left under a default group, or a newly-created business unit's subscriptions weren't correctly onboarded into the existing Landing Zones management group structure — meaning they never inherited the baseline policy assignments that automatically apply to subscriptions correctly placed under the Landing Zones hierarchy (66.3.4/66.6's specific, named failure mode). This should be prevented going forward by treating subscription creation/onboarding as a governed, checklist-driven process ensuring every new subscription is explicitly placed under the correct management group as part of its creation — ideally automated via the same IaC/CI-CD tooling (Sections 45–49) used for the rest of the Landing Zone's own configuration, rather than a manual step that can be forgotten, and periodically audited via Resource Graph queries (Section 65.4.1) checking for subscriptions outside the expected management group structure.
_What the interviewer is probing:_ the ability to connect a realistic governance-gap finding to the specific, named mechanism (management group placement determining policy inheritance) rather than a vague "policies weren't applied," and to propose a concrete, automatable prevention mechanism.

**Architect / Scenario:** "Design a Landing Zone strategy for an organization currently operating with a single, ungoverned Azure subscription containing a mix of production and experimental workloads, planning to scale to dozens of subscriptions across multiple business units over the next two years."
_Model answer:_ first, establish the target management group hierarchy (66.3.4) — Platform (Connectivity, Identity if applicable, Management subscriptions), Landing Zones (further subdivided by business unit or Corp/Online classification as appropriate to the organization's actual structure), and Sandbox — using Microsoft's Azure Landing Zones reference implementation (66.5.1) as the accelerator rather than building this from scratch, directly applying Section 47.4.4's "start from a curated starting point" principle at this larger architectural scale. Migrate the existing single subscription's production workloads into an appropriately-placed Application Landing Zone subscription (or split across multiple, if the current mixed workload set genuinely warrants separation), and explicitly carve out the experimental workloads into a dedicated Sandbox subscription (66.3.5), isolated from production connectivity — directly addressing the "mix of production and experimental" concern named in the prompt. Assign baseline policies (network restrictions, required tags per Section 65.3.4, security defaults per Section 55.8.1) at the Landing Zones management group scope, ensuring the next two years' worth of new business-unit subscriptions automatically inherit them without requiring per-subscription manual configuration — directly satisfying the stated "scale to dozens of subscriptions" growth trajectory. Establish subscription onboarding as a governed, IaC-driven process (directly connecting to the prior senior-level answer's prevention mechanism) ensuring every new business unit's subscriptions are correctly placed in the hierarchy from the start, with periodic Resource Graph audits (Section 65.4.1) catching any drift. Treat the entire Landing Zone configuration itself as version-controlled, IaC-managed infrastructure (Sections 46–49), deployed and evolved via the same CI/CD discipline as any other production system, consistent with 66.5.2's "living platform" framing.
_What the interviewer is probing:_ the ability to design a complete, realistic Landing Zone migration/build strategy addressing a genuine starting-state problem (ungoverned single subscription) and a genuine growth trajectory (dozens of subscriptions, multiple business units), synthesizing this section's Landing Zone/CAF material with prior sections' IaC, tagging, and governance-enforcement material into one coherent, phased plan.

---

## 66.10 Key Takeaways Summary

🔑 CAF is a full-lifecycle methodology (Strategy, Plan, Ready, Adopt, Govern, Manage, Secure) — Landing Zones are its concrete technical/architectural output specifically for the Ready phase, and CAF's Govern/Manage/Secure methodologies retroactively organize everything covered in this roadmap's Parts 10–12.

🔑 A Landing Zone formally names and unifies the management-group-scoped policy enforcement, hub-and-spoke networking, and centrally-owned-vs-team-owned organizational patterns this roadmap has established piecemeal across many prior sections — Part 13 exists to provide this synthesizing structure.

🔑 Platform Landing Zone subscriptions (Connectivity, Identity, Management) are centrally-owned shared infrastructure; Application Landing Zone subscriptions are where teams deploy workloads while inheriting the platform's baseline guardrails automatically via management-group scope.

🔑 Azure Landing Zones (ALZ) provides a reference IaC implementation accelerator, directly applying the "start from a curated starting point rather than building from scratch" principle already established for Bicep modules (Section 47.4.4) at the full-Landing-Zone architectural scale.

🔑 A Landing Zone requires ongoing maintenance as a living platform — not a one-time build — with subscription onboarding treated as a governed, automatable process to prevent the specific, realistic "newer subscriptions missing baseline governance" failure mode this section names explicitly.

---

## 66.11 Related Concepts and What Comes Next

- **Section 46.6/54.5 (prerequisite, completed):** the deployment-scope and policy-inheritance mechanics this section's management group hierarchy directly applies.
- **Section 59.2.4 (prerequisite, completed):** the hub-and-spoke networking pattern this section's Connectivity subscription directly implements.
- **Section 65 (prerequisite, completed):** the tagging and capacity-planning material this section's Landing Zone design areas directly incorporate.
- **Section 67 — Multi-Subscription/Multi-Tenant Enterprise Architecture (next):** directly extends this section's Landing Zone foundation into the fuller multi-subscription/multi-tenant architectural treatment, including the 40-subscription scenario referenced repeatedly throughout Parts 10–12.
- **Section 68 — Hybrid & Multi-Cloud (Azure Arc) (upcoming):** extends the Landing Zone concept to hybrid/on-premises and multi-cloud resource management.

---

_End of Section 66. Next: Section 67 — Multi-Subscription/Multi-Tenant Enterprise Architecture._
