# Azure Zero-to-Enterprise Knowledge Base — Index

A comprehensive, 100-section learning resource organized into 18 parts covering Azure from foundations to enterprise architecture, data engineering, AI/ML, security operations, and resilience testing. Navigate by part, read sections sequentially, or jump to topics of interest.

---

## Quick Navigation

| Part                             | Topic                                   | Sections |
| -------------------------------- | --------------------------------------- | -------- |
| **[Part 1](./Contents/Part1)**   | Foundations & Cloud Computing Model     | 1–5      |
| **[Part 2](./Contents/Part2)**   | Identity & Access Management            | 6–10     |
| **[Part 3](./Contents/Part3)**   | Core Compute                            | 11–15    |
| **[Part 4](./Contents/Part4)**   | Storage                                 | 16–20    |
| **[Part 5](./Contents/Part5)**   | Networking                              | 21–28    |
| **[Part 6](./Contents/Part6)**   | Databases & Data Services               | 29–33    |
| **[Part 7](./Contents/Part7)**   | Containers & Orchestration              | 34–39    |
| **[Part 8](./Contents/Part8)**   | Serverless & Integration                | 40–44    |
| **[Part 9](./Contents/Part9)**   | DevOps & Infrastructure as Code         | 45–49    |
| **[Part 10](./Contents/Part10)** | Monitoring & Observability              | 50–54    |
| **[Part 11](./Contents/Part11)** | Security & Governance                   | 55–60    |
| **[Part 12](./Contents/Part12)** | High Availability, DR, Scaling & Cost   | 61–65    |
| **[Part 13](./Contents/Part13)** | Enterprise Architecture & Comparisons   | 66–70    |
| **[Part 14](./Contents/Part14)** | Interview Preparation & Wrap-Up         | 71–74    |
| **[Part 15](./Contents/Part15)** | Data Engineering & Analytics on Azure   | 75–83    |
| **[Part 16](./Contents/Part16)** | AI/ML & Generative AI on Azure          | 84–90    |
| **[Part 17](./Contents/Part17)** | Security Operations & Incident Response | 91–96    |
| **[Part 18](./Contents/Part18)** | Resilience Testing & Chaos Engineering  | 97–100   |

---

## Folder Structure

```
Azure/
├── README.md (quick-start guide)
├── INDEX.md (this file — comprehensive navigation & section index)
│
└── Contents/ (modular organization by part)
    ├── Part1/  (5 sections: Foundations)
    ├── Part2/  (5 sections: Identity & Access Management)
    ├── Part3/  (5 sections: Core Compute)
    ├── Part4/  (5 sections: Storage)
    ├── Part5/  (8 sections: Networking)
    ├── Part6/  (5 sections: Databases & Data Services)
    ├── Part7/  (6 sections: Containers & Orchestration)
    ├── Part8/  (5 sections: Serverless & Integration)
    ├── Part9/  (5 sections: DevOps & IaC)
    ├── Part10/ (5 sections: Monitoring & Observability)
    ├── Part11/ (6 sections: Security & Governance)
    ├── Part12/ (5 sections: HA, DR, Scaling & Cost)
    ├── Part13/ (5 sections: Enterprise Architecture & Comparisons)
    ├── Part14/ (4 sections: Interview Preparation & Wrap-Up)
    ├── Part15/ (9 sections: Data Engineering & Analytics)
    ├── Part16/ (7 sections: AI/ML & Generative AI)
    ├── Part17/ (6 sections: Security Operations & Incident Response)
    └── Part18/ (4 sections: Resilience Testing & Chaos Engineering)
```

---

## Part Summaries

### Part 1 — Foundations & Cloud Computing Model

What Azure is and its history/evolution, cloud service and deployment models (IaaS/PaaS/SaaS, public/private/hybrid), Azure's global infrastructure (Regions, Availability Zones, Region Pairs, Edge), Azure Resource Manager (resources, resource groups, subscriptions, management groups), and Azure tooling (Portal, CLI, PowerShell, SDKs).

| §   | Section                                                | File                                                                                                                             |
| --- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------- |
| 1   | What is Azure, History & Evolution                     | [Section-01-Part1-What-is-Azure-History-Evolution](./Contents/Part1/Section-01-Part1-What-is-Azure-History-Evolution.md)         |
| 2   | Cloud Service & Deployment Models                      | [Section-02-Part1-Cloud-Service-and-Deployment-Models](./Contents/Part1/Section-02-Part1-Cloud-Service-and-Deployment-Models.md) |
| 3   | Azure Global Infrastructure                            | [Section-03-Part1-Azure-Global-Infrastructure](./Contents/Part1/Section-03-Part1-Azure-Global-Infrastructure.md)                 |
| 4   | Azure Resource Manager (ARM)                           | [Section-04-Part1-Azure-Resource-Manager](./Contents/Part1/Section-04-Part1-Azure-Resource-Manager.md)                           |
| 5   | Azure Tooling Overview — Portal, CLI, PowerShell, SDKs | [Section-05-Part1-Azure-Tooling-Overview](./Contents/Part1/Section-05-Part1-Azure-Tooling-Overview.md)                           |

### Part 2 — Identity & Access Management

Microsoft Entra ID (Azure AD) fundamentals, authentication vs. authorization with OAuth2/OIDC/SAML in Azure context, Role-Based Access Control (RBAC), Managed Identities & Service Principals, and Conditional Access/MFA/Privileged Identity Management (PIM).

| §   | Section                                 | File                                                                                                                                         |
| --- | --------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Microsoft Entra ID Fundamentals         | [Section-06-Part2-Microsoft-Entra-ID-Fundamentals](./Contents/Part2/Section-06-Part2-Microsoft-Entra-ID-Fundamentals.md)                     |
| 2   | AuthN vs. AuthZ — OAuth2/OIDC/SAML      | [Section-07-Part2-AuthN-vs-AuthZ-OAuth2-OIDC-SAML](./Contents/Part2/Section-07-Part2-AuthN-vs-AuthZ-OAuth2-OIDC-SAML.md)                     |
| 3   | Role-Based Access Control (RBAC)        | [Section-08-Part2-Role-Based-Access-Control](./Contents/Part2/Section-08-Part2-Role-Based-Access-Control.md)                                 |
| 4   | Managed Identities & Service Principals | [Section-09-Part2-Managed-Identities-and-Service-Principals](./Contents/Part2/Section-09-Part2-Managed-Identities-and-Service-Principals.md) |
| 5   | Conditional Access, MFA & PIM           | [Section-10-Part2-Conditional-Access-MFA-PIM](./Contents/Part2/Section-10-Part2-Conditional-Access-MFA-PIM.md)                               |

### Part 3 — Core Compute

Azure Virtual Machines (architecture, sizing, images), VM Scale Sets, Azure App Service (PaaS compute), Azure Functions (serverless compute), and Azure Container Instances (ACI).

| §   | Section                         | File                                                                                                         |
| --- | ------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| 1   | Azure Virtual Machines          | [Section-11-Part3-Azure-Virtual-Machines](./Contents/Part3/Section-11-Part3-Azure-Virtual-Machines.md)       |
| 2   | VM Scale Sets                   | [Section-12-Part3-VM-Scale-Sets](./Contents/Part3/Section-12-Part3-VM-Scale-Sets.md)                         |
| 3   | Azure App Service               | [Section-13-Part3-Azure-App-Service](./Contents/Part3/Section-13-Part3-Azure-App-Service.md)                 |
| 4   | Azure Functions                 | [Section-14-Part3-Azure-Functions](./Contents/Part3/Section-14-Part3-Azure-Functions.md)                     |
| 5   | Azure Container Instances (ACI) | [Section-15-Part3-Azure-Container-Instances](./Contents/Part3/Section-15-Part3-Azure-Container-Instances.md) |

### Part 4 — Storage

Azure Storage Account fundamentals (Blob, Queue, Table, File), Blob Storage deep dive (tiers, redundancy, lifecycle), Azure Managed Disks, Azure Files & File Sync, and data redundancy/replication (LRS/ZRS/GRS/RA-GRS).

| §   | Section                                            | File                                                                                                                           |
| --- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Azure Storage Account Fundamentals                 | [Section-16-Part4-Azure-Storage-Account-Fundamentals](./Contents/Part4/Section-16-Part4-Azure-Storage-Account-Fundamentals.md) |
| 2   | Blob Storage Deep Dive                             | [Section-17-Part4-Blob-Storage-Deep-Dive](./Contents/Part4/Section-17-Part4-Blob-Storage-Deep-Dive.md)                         |
| 3   | Azure Managed Disks                                | [Section-18-Part4-Azure-Managed-Disks](./Contents/Part4/Section-18-Part4-Azure-Managed-Disks.md)                               |
| 4   | Azure Files & File Sync                            | [Section-19-Part4-Azure-Files-and-File-Sync](./Contents/Part4/Section-19-Part4-Azure-Files-and-File-Sync.md)                   |
| 5   | Data Redundancy & Replication (LRS/ZRS/GRS/RA-GRS) | [Section-20-Part4-Data-Redundancy-and-Replication](./Contents/Part4/Section-20-Part4-Data-Redundancy-and-Replication.md)       |

### Part 5 — Networking

Virtual Network (VNet) fundamentals, NSGs & Route Tables, VNet Peering/Service Endpoints/Private Link, Load Balancer (L4) vs. Application Gateway (L7), Azure Front Door & CDN, VPN Gateway & ExpressRoute, Azure Virtual WAN, and Azure DNS.

| §   | Section                                         | File                                                                                                                                             |
| --- | ----------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Virtual Network (VNet) Fundamentals             | [Section-21-Part5-Virtual-Network-Fundamentals](./Contents/Part5/Section-21-Part5-Virtual-Network-Fundamentals.md)                               |
| 2   | NSGs & Route Tables                             | [Section-22-Part5-NSGs-and-Route-Tables](./Contents/Part5/Section-22-Part5-NSGs-and-Route-Tables.md)                                             |
| 3   | VNet Peering, Service Endpoints & Private Link  | [Section-23-Part5-VNet-Peering-Service-Endpoints-Private-Link](./Contents/Part5/Section-23-Part5-VNet-Peering-Service-Endpoints-Private-Link.md) |
| 4   | Load Balancer (L4) vs. Application Gateway (L7) | [Section-24-Part5-Load-Balancer-vs-Application-Gateway](./Contents/Part5/Section-24-Part5-Load-Balancer-vs-Application-Gateway.md)               |
| 5   | Azure Front Door & CDN                          | [Section-25-Part5-Azure-Front-Door-and-CDN](./Contents/Part5/Section-25-Part5-Azure-Front-Door-and-CDN.md)                                       |
| 6   | VPN Gateway & ExpressRoute                      | [Section-26-Part5-VPN-Gateway-and-ExpressRoute](./Contents/Part5/Section-26-Part5-VPN-Gateway-and-ExpressRoute.md)                               |
| 7   | Azure Virtual WAN                               | [Section-27-Part5-Azure-Virtual-WAN](./Contents/Part5/Section-27-Part5-Azure-Virtual-WAN.md)                                                     |
| 8   | Azure DNS (Public Zones & Private DNS Zones)    | [Section-28-Part5-Azure-DNS](./Contents/Part5/Section-28-Part5-Azure-DNS.md)                                                                     |

### Part 6 — Databases & Data Services

Azure SQL Database & Managed Instance, Cosmos DB, Azure Database for PostgreSQL/MySQL, Azure Cache for Redis, and data migration via the Azure Database Migration Service (DMS).

| §   | Section                                                 | File                                                                                                                                     |
| --- | ------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Azure SQL Database & Managed Instance                   | [Section-29-Part6-Azure-SQL-Database-and-Managed-Instance](./Contents/Part6/Section-29-Part6-Azure-SQL-Database-and-Managed-Instance.md) |
| 2   | Cosmos DB                                               | [Section-30-Part6-Cosmos-DB](./Contents/Part6/Section-30-Part6-Cosmos-DB.md)                                                             |
| 3   | Azure Database for PostgreSQL/MySQL                     | [Section-31-Part6-Azure-Database-PostgreSQL-MySQL](./Contents/Part6/Section-31-Part6-Azure-Database-PostgreSQL-MySQL.md)                 |
| 4   | Azure Cache for Redis                                   | [Section-32-Part6-Azure-Cache-for-Redis](./Contents/Part6/Section-32-Part6-Azure-Cache-for-Redis.md)                                     |
| 5   | Data Migration & Azure Database Migration Service (DMS) | [Section-33-Part6-Data-Migration-and-DMS](./Contents/Part6/Section-33-Part6-Data-Migration-and-DMS.md)                                   |

### Part 7 — Containers & Orchestration

Docker on Azure fundamentals, Azure Container Registry (ACR), Azure Kubernetes Service (AKS) architecture, AKS networking/scaling/security, AKS production operations, and Service Mesh on AKS (Istio/Linkerd).

| §   | Section                                    | File                                                                                                                     |
| --- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------ |
| 1   | Docker on Azure Fundamentals               | [Section-34-Part7-Docker-on-Azure-Fundamentals](./Contents/Part7/Section-34-Part7-Docker-on-Azure-Fundamentals.md)       |
| 2   | Azure Container Registry (ACR)             | [Section-35-Part7-Azure-Container-Registry](./Contents/Part7/Section-35-Part7-Azure-Container-Registry.md)               |
| 3   | AKS — Architecture                         | [Section-36-Part7-AKS-Architecture](./Contents/Part7/Section-36-Part7-AKS-Architecture.md)                               |
| 4   | AKS — Networking, Scaling & Security       | [Section-37-Part7-AKS-Networking-Scaling-Security](./Contents/Part7/Section-37-Part7-AKS-Networking-Scaling-Security.md) |
| 5   | AKS — Production Operations                | [Section-38-Part7-AKS-Production-Operations](./Contents/Part7/Section-38-Part7-AKS-Production-Operations.md)             |
| 6   | Service Mesh on AKS (Istio, Linkerd & OSM) | [Section-39-Part7-Service-Mesh-on-AKS](./Contents/Part7/Section-39-Part7-Service-Mesh-on-AKS.md)                         |

### Part 8 — Serverless & Integration

Azure Functions deep dive (triggers, bindings, hosting plans), Azure Container Apps, Logic Apps, Event Grid/Event Hubs/Service Bus, and API Management.

| §   | Section                              | File                                                                                                                         |
| --- | ------------------------------------ | ---------------------------------------------------------------------------------------------------------------------------- |
| 1   | Azure Functions Deep Dive            | [Section-40-Part8-Azure-Functions-Deep-Dive](./Contents/Part8/Section-40-Part8-Azure-Functions-Deep-Dive.md)                 |
| 2   | Azure Container Apps                 | [Section-41-Part8-Azure-Container-Apps](./Contents/Part8/Section-41-Part8-Azure-Container-Apps.md)                           |
| 3   | Logic Apps                           | [Section-42-Part8-Logic-Apps](./Contents/Part8/Section-42-Part8-Logic-Apps.md)                                               |
| 4   | Event Grid, Event Hubs & Service Bus | [Section-43-Part8-Event-Grid-Event-Hubs-Service-Bus](./Contents/Part8/Section-43-Part8-Event-Grid-Event-Hubs-Service-Bus.md) |
| 5   | API Management                       | [Section-44-Part8-API-Management](./Contents/Part8/Section-44-Part8-API-Management.md)                                       |

### Part 9 — DevOps & Infrastructure as Code

Azure DevOps (Boards, Repos, Pipelines, Artifacts), ARM Templates, Bicep, Terraform on Azure, and CI/CD pipeline patterns with GitHub Actions.

| §   | Section                                            | File                                                                                                                                 |
| --- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Azure DevOps (Boards, Repos, Pipelines, Artifacts) | [Section-45-Part9-Azure-DevOps](./Contents/Part9/Section-45-Part9-Azure-DevOps.md)                                                   |
| 2   | ARM Templates                                      | [Section-46-Part9-ARM-Templates](./Contents/Part9/Section-46-Part9-ARM-Templates.md)                                                 |
| 3   | Bicep                                              | [Section-47-Part9-Bicep](./Contents/Part9/Section-47-Part9-Bicep.md)                                                                 |
| 4   | Terraform on Azure                                 | [Section-48-Part9-Terraform-on-Azure](./Contents/Part9/Section-48-Part9-Terraform-on-Azure.md)                                       |
| 5   | CI/CD Pipeline Patterns & GitHub Actions           | [Section-49-Part9-CICD-Pipeline-Patterns-GitHub-Actions](./Contents/Part9/Section-49-Part9-CICD-Pipeline-Patterns-GitHub-Actions.md) |

### Part 10 — Monitoring & Observability

Azure Monitor fundamentals, Log Analytics & KQL, Application Insights, Alerts/Action Groups/Dashboards, and Azure Advisor.

| §   | Section                            | File                                                                                                                        |
| --- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------- |
| 1   | Azure Monitor Fundamentals         | [Section-50-Part10-Azure-Monitor-Fundamentals](./Contents/Part10/Section-50-Part10-Azure-Monitor-Fundamentals.md)           |
| 2   | Log Analytics & KQL                | [Section-51-Part10-Log-Analytics-KQL](./Contents/Part10/Section-51-Part10-Log-Analytics-KQL.md)                             |
| 3   | Application Insights               | [Section-52-Part10-Application-Insights](./Contents/Part10/Section-52-Part10-Application-Insights.md)                       |
| 4   | Alerts, Action Groups & Dashboards | [Section-53-Part10-Alerts-Action-Groups-Dashboards](./Contents/Part10/Section-53-Part10-Alerts-Action-Groups-Dashboards.md) |
| 5   | Azure Advisor                      | [Section-54-Part10-Azure-Advisor](./Contents/Part10/Section-54-Part10-Azure-Advisor.md)                                     |

### Part 11 — Security & Governance

Microsoft Defender for Cloud, Key Vault, Azure Policy & Blueprints, Compliance & Encryption (at rest/in transit), Network Security deep dive (firewalls, WAF, DDoS Protection), and Azure Bastion.

| §   | Section                                           | File                                                                                                                  |
| --- | ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| 1   | Microsoft Defender for Cloud                      | [Section-55-Part11-Microsoft-Defender-for-Cloud](./Contents/Part11/Section-55-Part11-Microsoft-Defender-for-Cloud.md) |
| 2   | Key Vault                                         | [Section-56-Part11-Key-Vault](./Contents/Part11/Section-56-Part11-Key-Vault.md)                                       |
| 3   | Azure Policy & Blueprints                         | [Section-57-Part11-Azure-Policy-Blueprints](./Contents/Part11/Section-57-Part11-Azure-Policy-Blueprints.md)           |
| 4   | Compliance & Encryption (At Rest/In Transit)      | [Section-58-Part11-Compliance-Encryption](./Contents/Part11/Section-58-Part11-Compliance-Encryption.md)               |
| 5   | Network Security Deep Dive (Firewalls, WAF, DDoS) | [Section-59-Part11-Network-Security-Deep-Dive](./Contents/Part11/Section-59-Part11-Network-Security-Deep-Dive.md)     |
| 6   | Azure Bastion                                     | [Section-60-Part11-Azure-Bastion](./Contents/Part11/Section-60-Part11-Azure-Bastion.md)                               |

### Part 12 — High Availability, DR, Scaling & Cost

HA/DR patterns (Availability Sets vs. Zones), Azure Site Recovery & Backup, autoscaling strategies, Cost Management/Reservations/Azure Hybrid Benefit, and capacity planning/tagging strategy.

| §   | Section                                              | File                                                                                                                                                |
| --- | ---------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | HA/DR Patterns — Availability Sets vs. Zones         | [Section-61-Part12-HA-DR-Patterns-Availability-Sets-Zones](./Contents/Part12/Section-61-Part12-HA-DR-Patterns-Availability-Sets-Zones.md)           |
| 2   | Azure Site Recovery & Backup                         | [Section-62-Part12-Azure-Site-Recovery-Backup](./Contents/Part12/Section-62-Part12-Azure-Site-Recovery-Backup.md)                                   |
| 3   | Autoscaling Strategies                               | [Section-63-Part12-Autoscaling-Strategies](./Contents/Part12/Section-63-Part12-Autoscaling-Strategies.md)                                           |
| 4   | Cost Management, Reservations & Azure Hybrid Benefit | [Section-64-Part12-Cost-Management-Reservations-Hybrid-Benefit](./Contents/Part12/Section-64-Part12-Cost-Management-Reservations-Hybrid-Benefit.md) |
| 5   | Capacity Planning & Tagging Strategy                 | [Section-65-Part12-Capacity-Planning-Tagging-Strategy](./Contents/Part12/Section-65-Part12-Capacity-Planning-Tagging-Strategy.md)                   |

### Part 13 — Enterprise Architecture & Comparisons

Landing zones & the Cloud Adoption Framework (CAF), multi-subscription/multi-tenant enterprise architecture, hybrid & multi-cloud with Azure Arc, Azure vs. AWS vs. GCP comparison, and real-world enterprise case studies.

| §   | Section                                                 | File                                                                                                                                                  |
| --- | ------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Landing Zones & Cloud Adoption Framework (CAF)          | [Section-66-Part13-Landing-Zones-CAF](./Contents/Part13/Section-66-Part13-Landing-Zones-CAF.md)                                                       |
| 2   | Multi-Subscription/Multi-Tenant Enterprise Architecture | [Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture](./Contents/Part13/Section-67-Part13-Multi-Subscription-Multi-Tenant-Architecture.md) |
| 3   | Hybrid & Multi-Cloud — Azure Arc                        | [Section-68-Part13-Hybrid-Multi-Cloud-Azure-Arc](./Contents/Part13/Section-68-Part13-Hybrid-Multi-Cloud-Azure-Arc.md)                                 |
| 4   | Azure vs. AWS vs. GCP Comparison                        | [Section-69-Part13-Azure-vs-AWS-vs-GCP](./Contents/Part13/Section-69-Part13-Azure-vs-AWS-vs-GCP.md)                                                   |
| 5   | Real-World Enterprise Case Studies                      | [Section-70-Part13-Real-World-Enterprise-Case-Studies](./Contents/Part13/Section-70-Part13-Real-World-Enterprise-Case-Studies.md)                     |

### Part 14 — Interview Preparation & Wrap-Up

Consolidated interview question bank (Beginner → Architect), Azure-based system design questions, hands-on labs & mini-projects, and a key-takeaways checklist with recommended next topics.

| §   | Section                                                     | File                                                                                                                                  |
| --- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Consolidated Interview Question Bank (Beginner → Architect) | [Section-71-Part14-Consolidated-Interview-Question-Bank](./Contents/Part14/Section-71-Part14-Consolidated-Interview-Question-Bank.md) |
| 2   | System Design Questions (Azure-Based)                       | [Section-72-Part14-System-Design-Questions](./Contents/Part14/Section-72-Part14-System-Design-Questions.md)                           |
| 3   | Hands-On Labs & Mini-Projects                               | [Section-73-Part14-Hands-On-Labs-Mini-Projects](./Contents/Part14/Section-73-Part14-Hands-On-Labs-Mini-Projects.md)                   |
| 4   | Key Takeaways Checklist & Recommended Next Topics           | [Section-74-Part14-Key-Takeaways-Checklist-Next-Topics](./Contents/Part14/Section-74-Part14-Key-Takeaways-Checklist-Next-Topics.md)   |

### Part 15 — Data Engineering & Analytics on Azure

Data Lake fundamentals & Azure Data Lake Storage Gen2, Azure Synapse Analytics, Azure Data Factory, Azure Databricks, Power BI, Azure Cognitive Search, Microsoft Fabric, data architecture patterns (lakehouse/medallion), and a data & analytics interview drill.

| §   | Section                                                         | File                                                                                                                          |
| --- | --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------- |
| 1   | Data Lake Fundamentals & Azure Data Lake Storage Gen2           | [Section-75-Part15-Data-Lake-Fundamentals-ADLS-Gen2](./Contents/Part15/Section-75-Part15-Data-Lake-Fundamentals-ADLS-Gen2.md) |
| 2   | Azure Synapse Analytics                                         | [Section-76-Part15-Azure-Synapse-Analytics](./Contents/Part15/Section-76-Part15-Azure-Synapse-Analytics.md)                   |
| 3   | Azure Data Factory                                              | [Section-77-Part15-Azure-Data-Factory](./Contents/Part15/Section-77-Part15-Azure-Data-Factory.md)                             |
| 4   | Azure Databricks                                                | [Section-78-Part15-Azure-Databricks](./Contents/Part15/Section-78-Part15-Azure-Databricks.md)                                 |
| 5   | Power BI                                                        | [Section-79-Part15-Power-BI](./Contents/Part15/Section-79-Part15-Power-BI.md)                                                 |
| 6   | Azure Cognitive Search (Azure AI Search)                        | [Section-80-Part15-Azure-Cognitive-Search](./Contents/Part15/Section-80-Part15-Azure-Cognitive-Search.md)                     |
| 7   | Microsoft Fabric                                                | [Section-81-Part15-Microsoft-Fabric](./Contents/Part15/Section-81-Part15-Microsoft-Fabric.md)                                 |
| 8   | Data Architecture Patterns — Lakehouse & Medallion Architecture | [Section-82-Part15-Data-Architecture-Patterns](./Contents/Part15/Section-82-Part15-Data-Architecture-Patterns.md)             |
| 9   | Part 15 Wrap-Up + Data & Analytics Interview Drill              | [Section-83-Part15-WrapUp-Interview-Drill](./Contents/Part15/Section-83-Part15-WrapUp-Interview-Drill.md)                     |

### Part 16 — AI/ML & Generative AI on Azure

ML on Azure fundamentals with Azure Machine Learning, Azure ML deep dive (training/pipelines/deployment/endpoints), MLOps on Azure, Azure OpenAI Service, Azure AI Foundry (agents/prompt flow/RAG), AI/ML security & Responsible AI governance, and an AI/ML interview drill.

| §   | Section                                                         | File                                                                                                                                                        |
| --- | --------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | ML on Azure Fundamentals & Azure Machine Learning               | [Section-84-Part16-ML-on-Azure-Fundamentals-Azure-Machine-Learning](./Contents/Part16/Section-84-Part16-ML-on-Azure-Fundamentals-Azure-Machine-Learning.md) |
| 2   | Azure ML Deep Dive — Training, Pipelines, Deployment, Endpoints | [Section-85-Part16-Azure-ML-Deep-Dive](./Contents/Part16/Section-85-Part16-Azure-ML-Deep-Dive.md)                                                           |
| 3   | MLOps on Azure                                                  | [Section-86-Part16-MLOps-on-Azure](./Contents/Part16/Section-86-Part16-MLOps-on-Azure.md)                                                                   |
| 4   | Azure OpenAI Service                                            | [Section-87-Part16-Azure-OpenAI-Service](./Contents/Part16/Section-87-Part16-Azure-OpenAI-Service.md)                                                       |
| 5   | Azure AI Foundry — Agents, Prompt Flow & RAG Patterns           | [Section-88-Part16-Azure-AI-Foundry](./Contents/Part16/Section-88-Part16-Azure-AI-Foundry.md)                                                               |
| 6   | AI/ML Security & Responsible AI Governance                      | [Section-89-Part16-AIML-Security-Responsible-AI-Governance](./Contents/Part16/Section-89-Part16-AIML-Security-Responsible-AI-Governance.md)                 |
| 7   | Part 16 Wrap-Up + AI/ML Interview Drill                         | [Section-90-Part16-WrapUp-Interview-Drill](./Contents/Part16/Section-90-Part16-WrapUp-Interview-Drill.md)                                                   |

### Part 17 — Security Operations & Incident Response

Microsoft Purview (sensitive data discovery & governance), Microsoft Sentinel SIEM fundamentals, Sentinel deep dive (analytics rules, hunting, SOAR playbooks), automated incident response via Logic Apps, SOC patterns on Azure, and a security operations interview drill.

| §   | Section                                                               | File                                                                                                                                  |
| --- | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Microsoft Purview — Sensitive Data Discovery & Governance             | [Section-91-Part17-Microsoft-Purview](./Contents/Part17/Section-91-Part17-Microsoft-Purview.md)                                       |
| 2   | Microsoft Sentinel — SIEM Fundamentals                                | [Section-92-Part17-Microsoft-Sentinel-SIEM-Fundamentals](./Contents/Part17/Section-92-Part17-Microsoft-Sentinel-SIEM-Fundamentals.md) |
| 3   | Sentinel Deep Dive — Analytics Rules, Hunting & SOAR Playbooks        | [Section-93-Part17-Sentinel-Deep-Dive](./Contents/Part17/Section-93-Part17-Sentinel-Deep-Dive.md)                                     |
| 4   | Automated Incident Response — Logic Apps Playbooks & Automation Rules | [Section-94-Part17-Automated-Incident-Response](./Contents/Part17/Section-94-Part17-Automated-Incident-Response.md)                   |
| 5   | Security Operations Center (SOC) Patterns on Azure                    | [Section-95-Part17-SOC-Patterns-on-Azure](./Contents/Part17/Section-95-Part17-SOC-Patterns-on-Azure.md)                               |
| 6   | Part 17 Wrap-Up + Security Operations Interview Drill                 | [Section-96-Part17-WrapUp-Interview-Drill](./Contents/Part17/Section-96-Part17-WrapUp-Interview-Drill.md)                             |

### Part 18 — Resilience Testing & Chaos Engineering

Azure Chaos Studio fault injection fundamentals, designing chaos experiments & steady-state hypotheses, continuous DR validation & game days on Azure, and a final resilience interview drill (with a full-roadmap closing synthesis).

| §   | Section                                               | File                                                                                                                              |
| --- | ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Azure Chaos Studio — Fault Injection Fundamentals     | [Section-97-Part18-Azure-Chaos-Studio-Fundamentals](./Contents/Part18/Section-97-Part18-Azure-Chaos-Studio-Fundamentals.md)       |
| 2   | Designing Chaos Experiments & Steady-State Hypotheses | [Section-98-Part18-Designing-Chaos-Experiments](./Contents/Part18/Section-98-Part18-Designing-Chaos-Experiments.md)               |
| 3   | Continuous DR Validation & Game Days on Azure         | [Section-99-Part18-Continuous-DR-Validation-Game-Days](./Contents/Part18/Section-99-Part18-Continuous-DR-Validation-Game-Days.md) |
| 4   | Part 18 Wrap-Up + Resilience Interview Drill          | [Section-100-Part18-WrapUp-Resilience-Interview-Drill](./Contents/Part18/Section-100-Part18-WrapUp-Resilience-Interview-Drill.md) |

---

_Last updated: July 25, 2026_
