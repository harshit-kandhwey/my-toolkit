# Section 2 — Cloud Computing Models (IaaS/PaaS/SaaS) and Deployment Models

## 2.1 Definition

**Plain language:** A "cloud service model" describes how much of the technology stack Microsoft manages for you versus how much you manage yourself. A "deployment model" describes _where_ that infrastructure physically lives and who else shares it.

**Precise definition:** Cloud service models (IaaS, PaaS, SaaS, and the less common FaaS/CaaS) form a spectrum defined by the division of management responsibility between provider and customer across the technology stack (physical hardware → virtualization → OS → runtime → application → data). Deployment models (public, private, hybrid, multi-cloud) describe the ownership, location, and tenancy boundary of the infrastructure itself.

## 2.2 Why It Exists / Problem It Solves

Different workloads have different needs. A legacy application that requires full OS-level control (custom kernel modules, specific patch levels) needs IaaS. A team that just wants to deploy code without thinking about servers at all wants PaaS or serverless. A company that cannot legally store data outside its own physical premises needs a private or hybrid deployment. This spectrum of models exists so that **you only manage what you actually need to manage** — every layer you don't have to manage is a layer you don't have to secure, patch, monitor, or scale yourself.

## 2.3 The Responsibility Spectrum

The clearest way to understand IaaS vs PaaS vs SaaS is the "who manages what" table. Read it as: everything **below** the line "You manage" is handled by Microsoft; everything **above** it is your responsibility.

| Layer                 | On-Premises | IaaS (e.g., Azure VMs) | PaaS (e.g., App Service) | SaaS (e.g., Microsoft 365) |
| --------------------- | ----------- | ---------------------- | ------------------------ | -------------------------- |
| Data                  | You         | You                    | You                      | You                        |
| Applications          | You         | You                    | You                      | Microsoft                  |
| Runtime               | You         | You                    | Microsoft                | Microsoft                  |
| Middleware            | You         | You                    | Microsoft                | Microsoft                  |
| Operating System      | You         | You                    | Microsoft                | Microsoft                  |
| Virtualization        | You         | Microsoft              | Microsoft                | Microsoft                  |
| Servers (physical)    | You         | Microsoft              | Microsoft                | Microsoft                  |
| Storage (physical)    | You         | Microsoft              | Microsoft                | Microsoft                  |
| Networking (physical) | You         | Microsoft              | Microsoft                | Microsoft                  |

> 🎯 **Interview tip:** This exact table (sometimes called the "shared responsibility model" for service tiers, distinct from the security-specific shared responsibility model covered in Part 11) is one of the most commonly drawn diagrams in cloud interviews. Being able to reproduce it from memory, and explain _why_ each row sits where it does, signals genuine understanding rather than memorization.

## 2.4 IaaS (Infrastructure-as-a-Service) — Deep Dive

**Definition:** IaaS provides the fundamental building blocks — virtual machines, virtual networks, and storage — with Microsoft managing only the physical hardware and the hypervisor layer. You are responsible for the guest operating system, all patching above it, and everything you install and run.

**Azure examples:** Azure Virtual Machines (Section 11), Virtual Network (Section 21), Managed Disks (Section 18).

**When to use it:**

- You need a specific OS version, kernel configuration, or third-party software with strict OS-level dependencies.
- You are lifting-and-shifting an existing on-premises application with minimal re-architecture (a "lift and shift" migration).
- You need full control over networking, security agents, or compliance tooling that must run at the OS level.

**Trade-off:** Maximum control, but maximum operational burden — you own OS patching, security hardening, scaling configuration, and availability configuration.

## 2.5 PaaS (Platform-as-a-Service) — Deep Dive

**Definition:** PaaS provides a managed runtime environment — Microsoft manages the OS, patching, and underlying scaling infrastructure, and you deploy only your application code and configuration.

**Azure examples:** Azure App Service (Section 13), Azure SQL Database (Section 28, as opposed to SQL Server on a VM which would be IaaS), Azure Kubernetes Service in its managed-control-plane sense (Section 35 — note AKS is a hybrid case, explained below).

**When to use it:**

- You are building new applications and don't need OS-level customization.
- You want to minimize operational overhead — no OS patch management, no manual scaling configuration.
- Your team wants to move faster by focusing purely on application code.

**Trade-off:** Less control — you generally cannot install arbitrary OS-level software, and you are constrained to the runtime versions and configurations the platform supports.

> ⚠️ **A common point of confusion:** AKS (Azure Kubernetes Service) is often mis-categorized. Microsoft manages the Kubernetes _control plane_ (the API server, etcd, scheduler — PaaS-like), but you still manage the _worker nodes_ as VMs, including their OS patching in many configurations (IaaS-like), and you fully manage what runs inside your containers. This makes AKS a hybrid model — expect this nuance to come up in senior interviews. AKS is covered fully in Part 7.

## 2.6 SaaS (Software-as-a-Service) — Deep Dive

**Definition:** SaaS delivers a complete, ready-to-use application. Microsoft manages everything from physical hardware up through the application itself; you only manage your data and user-level configuration.

**Azure/Microsoft examples:** Microsoft 365, Dynamics 365. Azure itself is not typically described as offering "core" SaaS products in the way IaaS/PaaS are core to it, but many services built _on_ Azure by Microsoft or third parties are delivered as SaaS.

**When to use it:** When the business need is a finished capability (email, CRM, office productivity) rather than a platform to build on.

## 2.7 Serverless / FaaS and Containers-as-a-Service — Where They Fit

Two additional models are commonly discussed alongside the classic three:

- **FaaS (Function-as-a-Service)** — an even more abstracted form of PaaS where you deploy individual functions (small units of code) rather than a whole application, and the platform handles all infrastructure including scaling to zero when idle. Azure Functions (Section 14, Section 38) is Azure's FaaS offering.
- **CaaS (Containers-as-a-Service)** — a model where the unit of deployment is a container image rather than either a VM or raw code. Azure Container Instances (Section 15) is a pure CaaS offering; AKS sits between CaaS and full IaaS/PaaS hybrid as discussed above.

These aren't separate rows on the responsibility table so much as they are refinements within the IaaS→PaaS spectrum, trading further customer responsibility for further convenience.

## 2.8 Deployment Models

Separately from _how much_ Microsoft manages, you must decide _where_ infrastructure lives and who shares it:

- **Public cloud** — infrastructure is owned by Microsoft and shared (multi-tenant) across many customers, with strong isolation between tenants enforced in software. This is the default and most common Azure deployment model, and the one this entire roadmap primarily addresses.
- **Private cloud** — infrastructure dedicated to a single organization, either on-premises or in a dedicated hosted environment. Azure Stack (Azure Stack Hub, Azure Stack HCI) allows organizations to run Azure-consistent infrastructure and services inside their own data center, useful for regulatory or latency requirements that prohibit public cloud.
- **Hybrid cloud** — a combination of on-premises/private infrastructure and public cloud, connected and often managed together. Azure Arc (Part 13) extends Azure's management plane (including Azure Policy, RBAC, and monitoring) to resources running outside Azure entirely, including on-premises servers, other clouds, and edge devices.
- **Multi-cloud** — using more than one public cloud provider (e.g., Azure plus AWS) simultaneously, either for redundancy, to avoid vendor lock-in, or because different providers excel at different services. This introduces significant complexity in identity, networking, and tooling standardization, discussed further in Part 13.

## 2.9 Production & Enterprise Usage

In practice, large enterprises rarely commit to a single service model. A typical enterprise Azure estate mixes: legacy applications on IaaS VMs (because rewriting them for PaaS isn't cost-justified), new applications built on PaaS/serverless (App Service, Functions) to minimize operational overhead, and SaaS for productivity tooling (Microsoft 365). Deployment-model-wise, regulated enterprises frequently run **hybrid**, keeping sensitive data on-premises or in a private cloud while bursting compute or running less-sensitive workloads in the Azure public cloud — this pattern is formalized later in the Cloud Adoption Framework and landing zone architecture (Part 13).

## 2.10 Interview Questions — Section 2

### 🎯 Beginner

**Q: Give a real-world analogy for IaaS, PaaS, and SaaS.**

_Model answer:_ A common analogy is pizza-making. IaaS is like renting a fully-equipped kitchen — you bring your own ingredients and do all the cooking yourself. PaaS is like ordering a pizza from a shop that bakes it for you — you just choose toppings (your application logic), and they handle the oven (runtime, OS). SaaS is like dining at a restaurant — you just eat the finished meal (use the finished application), managing none of the preparation.

_What the interviewer is probing:_ whether the candidate can communicate technical distinctions in plain language, a skill valued for cross-team collaboration.

### 🎯 Senior/Architect

**Q: A regulated financial services client needs to modernize a legacy application but cannot move certain data outside their own data center due to compliance requirements. How would you approach the service and deployment model decision?**

_Model answer:_ I'd start by classifying the application's components by data sensitivity and coupling. Compliance-bound data stores might stay on-premises or move to Azure Stack HCI/Hub for Azure-consistent management without leaving the premises. Less sensitive, stateless application tiers could move to Azure PaaS (App Service or AKS) for operational efficiency, connected back to on-premises data via a hybrid networking pattern (ExpressRoute, covered in Part 5) with Azure Arc providing unified governance and monitoring across both environments. This hybrid deployment model balances compliance constraints against modernization benefits, rather than forcing an all-or-nothing migration.

_What the interviewer is probing:_ whether the candidate can navigate real-world constraints (compliance, legacy systems) rather than defaulting to a purely theoretical "always use the most modern service" answer — this is a strong differentiator at the architect level.

## 2.11 Common Misconceptions

- **"PaaS is always better than IaaS."** Not true — PaaS trades control for convenience, and workloads requiring OS-level customization, specific compliance agents, or unsupported legacy dependencies genuinely need IaaS.
- **"Serverless means there are no servers."** False — servers still exist; "serverless" means _you_ don't provision or manage them directly, and billing is typically based on execution rather than reserved capacity.

## 2.12 Key Takeaways

- 🔑 The service model spectrum (IaaS→PaaS→SaaS) is about _who manages which layer of the stack_ — more managed by Microsoft means less operational burden but less customization control.
- 🔑 AKS is a hybrid model: managed control plane (PaaS-like) but customer-managed worker nodes (IaaS-like) — a frequent interview nuance.
- 🔑 Deployment models (public/private/hybrid/multi-cloud) are an orthogonal decision from service models — about _where_ infrastructure lives and who it's shared with, not how much of the stack is managed.
- 🔑 Real enterprise architectures mix all of these models simultaneously rather than standardizing on just one.

## 2.13 Related Concepts (Next Up)

Section 3 will cover Azure's **physical global infrastructure** — Regions, Availability Zones, Region Pairs — which is the literal physical substrate that every IaaS, PaaS, and SaaS resource discussed in this section is ultimately deployed onto.
