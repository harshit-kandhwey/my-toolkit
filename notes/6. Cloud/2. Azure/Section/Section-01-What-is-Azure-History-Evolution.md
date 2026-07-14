# Section 1 — What is Azure, History & Evolution

## 1.1 Definition

**Plain language:** Microsoft Azure is a public cloud platform — a collection of remote data centers, owned and operated by Microsoft, that you can rent computing resources (servers, storage, databases, networking, and hundreds of higher-level services) from over the internet, paying only for what you use, instead of buying and running your own physical hardware.

**Precise definition:** Azure is Microsoft's public cloud computing platform providing Infrastructure-as-a-Service (IaaS), Platform-as-a-Service (PaaS), and Software-as-a-Service (SaaS) offerings, delivered from a globally distributed network of Microsoft-managed data centers, accessible via REST APIs, SDKs, CLI, PowerShell, and a web portal, and consumed on a pay-as-you-go or reserved-capacity commercial model.

## 1.2 Why It Exists / The Problem It Solves

Before cloud computing became mainstream (roughly pre-2010), organizations that wanted to run software had to:

- **Buy physical servers** — a large upfront capital expenditure (CapEx), with multi-week or multi-month procurement lead times.
- **Provision for peak capacity** — you had to buy enough hardware to handle your *busiest* expected day (e.g., Black Friday for retail), which meant most of that hardware sat idle the rest of the year.
- **Operate physical data centers** — power, cooling, physical security, rack space, networking hardware, and the staff to maintain all of it, none of which is differentiated value for the business.
- **Manage hardware failure and refresh cycles** — disks fail, servers age out, and someone has to plan and execute replacement, all while systems stay online.
- **Scale slowly** — adding capacity meant ordering, receiving, racking, and configuring new physical machines, a process that could take weeks.

Azure (and public cloud generally) solves this by converting **CapEx into OpEx** (you rent instead of buy), by letting you **provision resources in minutes instead of weeks**, by letting you **scale up or down on demand** to match actual load, and by letting Microsoft absorb the burden of physical data-center operations, hardware failure, and global infrastructure build-out.

> 💡 **Tip:** In interviews, when asked "why cloud over on-prem," always structure your answer around these four pillars: cost model (CapEx→OpEx), speed of provisioning, elasticity/scalability, and reduced operational burden — this is what interviewers are listening for.

## 1.3 What Existed Before It

- **On-premises data centers**: Organizations owned and ran their own physical servers in their own buildings or leased data-center space (colocation).
- **Managed hosting / dedicated servers**: Companies like Rackspace rented out physical or virtual servers, but with limited self-service automation and slow provisioning compared to modern cloud.
- **Early virtualization** (VMware ESX/ESXi, Xen, Hyper-V, from the early-to-mid 2000s): Allowed multiple virtual machines to run on one physical server, improving hardware utilization, but these virtual machines were still typically deployed and managed on infrastructure the organization itself owned or leased — this was the direct technical precursor to cloud IaaS.
- **AWS (launched 2006)**: The first major hyperscale public cloud, proving the commercial and technical viability of on-demand, API-driven infrastructure. Azure entered the market afterward, learning from and competing directly with AWS's model.

## 1.4 History & Evolution of Azure

- **2008 — Announced as "Project Red Dog"** at Microsoft's Professional Developers Conference, an internal codename reflecting its early experimental status.
- **February 2010 — General availability as "Windows Azure."** The original product was heavily PaaS-focused: developers deployed application code and Azure handled the underlying VM and OS management, a more restrictive but higher-abstraction model than raw IaaS.
- **2012 — IaaS capabilities added**, including Azure Virtual Machines and Virtual Networks, allowing customers to run arbitrary VMs (Windows or Linux) with full OS-level control, directly matching AWS EC2's model and broadening Azure's addressable market beyond pure PaaS developers.
- **2014 — Renamed "Microsoft Azure"** from "Windows Azure," a deliberate signal that the platform was no longer Windows-only — Linux workloads, open-source tooling, and non-Microsoft technologies became first-class citizens on the platform.
- **2014 onward — Rapid service expansion**: Azure SQL Database, Azure Storage maturation, Azure Active Directory (identity), and a steadily growing catalog of managed services.
- **2015 — Azure Resource Manager (ARM)** became the standard deployment and management model, replacing the older "Azure Service Management" (ASM/"classic") model. ARM introduced resource groups, declarative templates, and unified role-based access control — this is covered in depth in Section 4.
- **2018–2020 — Kubernetes & cloud-native investment**: Azure Kubernetes Service (AKS) reached general availability (2018), and Azure invested heavily in containers, DevOps tooling (Azure DevOps, formerly Visual Studio Team Services), and hybrid cloud (Azure Arc, announced 2019).
- **2023 — Microsoft Entra**: Azure Active Directory was rebranded as part of the broader "Microsoft Entra" identity product family, reflecting an expanded identity and access portfolio beyond just directory services.
  > ⚠️ **Verify against current docs** — Microsoft continues to evolve Entra branding and sub-product names; treat any specific Entra sub-product names in later sections as subject to change and confirm current naming before using in production documentation.
- **Present day**: Azure is one of the top three global hyperscale cloud providers (alongside AWS and Google Cloud Platform), offering several hundred distinct services spanning compute, storage, networking, data, AI/ML, IoT, and enterprise/government-specific clouds (e.g., Azure Government).

## 1.5 Terminology Introduced in This Section

| Term | Definition |
|---|---|
| **Public cloud** | Computing resources (servers, storage, networking, etc.) owned and operated by a third-party provider (Microsoft, in Azure's case) and made available to multiple customers over the internet, as opposed to a private cloud built for a single organization's exclusive use. |
| **IaaS (Infrastructure-as-a-Service)** | A cloud service model where the provider supplies raw computing infrastructure (VMs, storage, networks), and the customer manages the operating system, runtime, and application layers. |
| **PaaS (Platform-as-a-Service)** | A cloud service model where the provider manages the underlying infrastructure *and* the operating system/runtime, and the customer only manages application code and configuration. |
| **SaaS (Software-as-a-Service)** | A cloud service model where the provider manages the entire application stack, and the customer simply uses the finished software (e.g., Microsoft 365). |
| **CapEx (Capital Expenditure)** | Upfront spending on physical assets (like servers) that are owned and depreciated over time. |
| **OpEx (Operational Expenditure)** | Ongoing, recurring spending for services consumed (like a cloud subscription bill), rather than owned assets. |
| **Hyperscale cloud provider** | A cloud provider operating at massive global scale across many regions and data centers, typically referring to AWS, Azure, and GCP. |
| **ARM (Azure Resource Manager)** | Azure's deployment and management layer that processes requests to create, update, and delete resources; covered fully in Section 4. |

## 1.6 Modern Use Cases

- **Web application hosting** — from simple static sites to complex multi-tier enterprise applications, using services like App Service, AKS, or VMs.
- **Data platforms and analytics** — using Azure SQL Database, Cosmos DB, Azure Synapse Analytics, and Azure Data Factory to store, process, and analyze data at scale.
- **AI/ML workloads** — using Azure Machine Learning and Azure OpenAI Service for training and serving models.
- **Enterprise hybrid cloud** — organizations that cannot fully move to the cloud (due to regulatory, latency, or legacy-system constraints) use Azure Arc and Azure Stack to extend Azure management to on-premises and edge infrastructure.
- **Disaster recovery and backup** — using Azure Site Recovery and Azure Backup as a cost-effective DR target, avoiding the need for a second physical data center.
- **DevOps and CI/CD pipelines** — using Azure DevOps or GitHub Actions integrated with Azure to automate build, test, and deployment workflows.

## 1.7 Industry Adoption

Azure is widely adopted particularly among **enterprises already invested in the Microsoft ecosystem** — organizations using Windows Server, Active Directory, SQL Server, and Microsoft 365 often find Azure a natural extension due to licensing benefits (like Azure Hybrid Benefit, covered in Part 12) and identity integration (Entra ID). It has strong adoption in **regulated industries** (finance, healthcare, government) partly due to Azure Government and extensive compliance certifications, and is commonly used alongside AWS or GCP in **multi-cloud enterprise strategies**.

## 1.8 Prerequisites for This Topic

- Basic networking concepts (IP addressing, DNS, TCP/UDP, HTTP/HTTPS) — briefly reintroduced in Part 5 where relevant.
- Basic Linux/Windows OS familiarity — needed for VM and container sections; not re-taught in depth here.
- Basic understanding of virtualization (VMs, hypervisors) — a hypervisor allows one physical machine to run multiple isolated virtual machines, each with its own OS — this concept underlies all of Azure's compute IaaS offerings.
- Familiarity with command-line usage — helpful for CLI sections in Section 5.

## 1.9 Interview Questions — Section 1

### 🎯 Junior level
**Q: What is Azure?**

*Model answer:* Azure is Microsoft's public cloud platform that provides on-demand computing resources — like virtual machines, storage, databases, and networking — over the internet on a pay-as-you-go basis, eliminating the need to buy and maintain physical hardware.

*What the interviewer is probing:* whether the candidate understands the basic value proposition of cloud computing, not just that "Azure is Microsoft's cloud."

### 🎯 Intermediate level
**Q: What's the difference between IaaS, PaaS, and SaaS, and where does Azure fit?**

*Model answer:* IaaS gives you raw infrastructure (e.g., Azure VMs) where you manage the OS and everything above it; PaaS (e.g., Azure App Service) manages the OS and runtime for you so you only deploy code; SaaS (e.g., Microsoft 365) is a fully finished application you just use. Azure offers all three models simultaneously, and most real architectures mix them — for example, an app might run on App Service (PaaS) while connecting to a VM-hosted legacy database (IaaS).

*What the interviewer is probing:* whether the candidate can map abstract service models to concrete, correctly-categorized Azure services, and whether they understand that real architectures are hybrid across models.

### 🎯 Senior/Architect level
**Q: Why might an enterprise choose Azure over AWS or a private data center, and what are the trade-offs?**

*Model answer:* Key drivers include existing Microsoft licensing investment (Azure Hybrid Benefit can significantly reduce Windows Server/SQL Server licensing costs on Azure VMs), deep Active Directory/Entra ID integration for hybrid identity, strong compliance certifications for regulated industries, and Azure Government for public-sector workloads. Trade-offs include potential vendor lock-in, service-parity gaps versus AWS in certain niche services, and the operational cost of retraining teams already expert in another platform. A private data center trades elasticity and OpEx-based cost for full physical control, which some regulated or latency-sensitive workloads still require.

*What the interviewer is probing:* whether the candidate can reason about business and technical trade-offs holistically, not just recite feature lists — this is where junior candidates fail and senior candidates differentiate themselves.

## 1.10 Common Misconceptions

- **"Azure only runs Windows."** False since 2014's rebrand — Azure fully supports Linux VMs, containers, and open-source workloads as first-class citizens, and in fact a majority of Azure VM workloads industry-wide run Linux.
- **"Cloud is always cheaper than on-premises."** Not universally true — cloud shifts cost structure (CapEx→OpEx) and adds elasticity, but poorly managed cloud spend (unused resources, wrong VM sizing) can exceed equivalent on-prem costs; this is why cost management (Part 12) is a distinct discipline.

## 1.11 Key Takeaways

- 🔑 Azure is Microsoft's public cloud platform, launched in 2010, originally PaaS-only and now spanning IaaS, PaaS, and SaaS across several hundred services.
- 🔑 The core value proposition is converting CapEx to OpEx, enabling fast provisioning, elastic scaling, and offloading physical infrastructure management to Microsoft.
- 🔑 Azure Resource Manager (ARM), introduced in 2015, is the modern deployment/management backbone for virtually everything else covered in this roadmap — every later section assumes ARM as the underlying model.
- 🔑 Azure's identity system was rebranded from Azure Active Directory to Microsoft Entra ID in 2023 — expect to see both names in the wild, especially in older documentation and existing enterprise environments.

## 1.12 Related Concepts (Next Up)

Section 2 will build directly on this foundation by formalizing the **cloud service models (IaaS/PaaS/SaaS)** and **deployment models (public/private/hybrid/multi-cloud)** introduced briefly here, followed by Section 3 covering Azure's **physical global infrastructure** (Regions, Availability Zones) that everything in later Parts is physically deployed onto.
