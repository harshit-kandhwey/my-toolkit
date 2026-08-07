# Section 82 (Part 13): GCP vs. AWS vs. Azure — Comprehensive Comparison

## 1. Definition

**Plain language:** Every major cloud provider solves the same underlying problems — compute, storage, networking, identity, data, AI, and operations — but names its services differently and makes different architectural choices. Interviewers and real multi-cloud/migration work both routinely require translating fluently between GCP, AWS, and Azure. This section is a single reference table doing exactly that translation for every service covered across this entire 85-section knowledge base.

**Precise:** This section maps each GCP service introduced in Parts 1–12 to its closest functional equivalent(s) in AWS and Azure, organized by category, followed by an honest assessment of where GCP genuinely differentiates itself and where it genuinely lags the other two providers.

## 2. Why This Comparison Matters

- **Interviews:** senior cloud/DevOps interviews frequently ask "what's the GCP equivalent of X" or "how would this AWS-native design change if built on GCP" — fluent translation signals genuine platform-agnostic architectural understanding rather than single-vendor memorization.
- **Multi-cloud and migration work:** organizations migrating between providers, or running deliberately multi-cloud, need this mapping as day-one working knowledge, not something looked up mid-project.
- **Vendor evaluation:** choosing a provider for a new workload requires knowing not just "GCP has a BigQuery equivalent" but the real functional and operational differences underneath the marketing names.

> ⚠️ **Accuracy note:** Feature parity between providers shifts constantly — a service listed as "no direct equivalent" today may exist next quarter, and vice versa. Treat this table as a snapshot of the well-established, stable mappings rather than a permanently fixed reference; verify against current documentation before relying on any specific parity claim in a real design decision.

## 3. Compute

| GCP Service (Section)        | AWS Equivalent                                  | Azure Equivalent                                  |
| ---------------------------- | ----------------------------------------------- | ------------------------------------------------- |
| Compute Engine (5)           | EC2                                             | Virtual Machines                                  |
| App Engine (6)               | Elastic Beanstalk                               | App Service                                       |
| Cloud Run (7)                | App Runner / Fargate (ECS)                      | Container Apps / Azure App Service (containers)   |
| Cloud Functions (8)          | Lambda                                          | Azure Functions                                   |
| Cloud Batch (9)              | AWS Batch                                       | Azure Batch                                       |
| Compute Decision Matrix (10) | (no single AWS equivalent — decision framework) | (no single Azure equivalent — decision framework) |

## 4. Storage and Databases

| GCP Service (Section)            | AWS Equivalent                                                                         | Azure Equivalent                                           |
| -------------------------------- | -------------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| Cloud Storage (11)               | S3                                                                                     | Blob Storage                                               |
| Persistent Disk / Filestore (12) | EBS / EFS                                                                              | Managed Disks / Azure Files                                |
| Cloud SQL (13)                   | RDS                                                                                    | Azure SQL Database / Azure Database for MySQL-PostgreSQL   |
| Cloud Spanner (14)               | Aurora (partial — no true global-distributed-with-external-consistency AWS equivalent) | Azure Cosmos DB (multi-model, closest global-scale analog) |
| Firestore / Datastore (15)       | DynamoDB                                                                               | Azure Cosmos DB (Core/SQL API)                             |
| Bigtable (16)                    | DynamoDB / Amazon Keyspaces (Cassandra-compatible)                                     | Azure Cosmos DB (Table API / Cassandra API)                |
| Memorystore (17)                 | ElastiCache                                                                            | Azure Cache for Redis                                      |
| Storage/DB Decision Matrix (18)  | (decision framework)                                                                   | (decision framework)                                       |

> 💡 **Tip:** Cloud Spanner is the one row on this table with the weakest true equivalent — it is Google's genuinely distinctive offering (globally distributed, strongly consistent, horizontally scalable relational SQL with TrueTime-based external consistency), and neither AWS nor Azure has shipped a fully equivalent product as of this writing; this is a legitimate, frequently-cited GCP differentiator, covered in depth in [Section 14](../Part2/Section-14-Part2-Cloud-Spanner.md).

## 5. Networking

| GCP Service (Section)                               | AWS Equivalent                                                     | Azure Equivalent                                                                     |
| --------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------------------------------ |
| VPC Fundamentals (19)                               | VPC                                                                | Virtual Network (VNet)                                                               |
| Subnets/IP/Routes (20)                              | Subnets/Route Tables                                               | Subnets/Route Tables (UDRs)                                                          |
| Firewall Rules (21)                                 | Security Groups + NACLs                                            | Network Security Groups (NSGs)                                                       |
| Cloud Load Balancing (22)                           | ELB (ALB/NLB/GLB)                                                  | Azure Load Balancer / Application Gateway / Front Door                               |
| Cloud DNS (23)                                      | Route 53                                                           | Azure DNS                                                                            |
| Cloud NAT / Interconnect / VPN (24)                 | NAT Gateway / Direct Connect / Site-to-Site VPN                    | Azure NAT Gateway / ExpressRoute / VPN Gateway                                       |
| Shared VPC / Peering / PSC (25)                     | VPC Peering / PrivateLink                                          | VNet Peering / Azure Private Link                                                    |
| Hybrid & Multi-Cloud Networking (26)                | Transit Gateway / Direct Connect Gateway                           | Virtual WAN                                                                          |
| Network Intelligence Center & Traffic Director (27) | VPC Reachability Analyzer / CloudWatch Network Insights / App Mesh | Network Watcher / (no direct Traffic Director service-mesh-control-plane equivalent) |

> ⚠️ **Interview-relevant nuance:** GCP's VPC is a **global** resource with **regional** subnets ([Section 19](../Part3/Section-19-Part3-VPC-Fundamentals.md)–[Section 20](../Part3/Section-20-Part3-Subnets-IP-Addressing-and-Routes.md)); both AWS's VPC and Azure's VNet are inherently **regional** resources with zonal/regional subnets. This is the single most frequently probed cross-provider networking distinction in interviews.

## 6. Containers and Kubernetes

| GCP Service (Section)                 | AWS Equivalent                                          | Azure Equivalent                    |
| ------------------------------------- | ------------------------------------------------------- | ----------------------------------- |
| Container Fundamentals (28)           | (Docker/OCI — provider-agnostic)                        | (Docker/OCI — provider-agnostic)    |
| Artifact Registry (29)                | Elastic Container Registry (ECR)                        | Azure Container Registry (ACR)      |
| GKE Architecture (30)                 | EKS                                                     | AKS                                 |
| GKE Networking & Storage (31)         | EKS VPC-CNI / EBS CSI                                   | AKS CNI / Azure Disk CSI            |
| GKE Autopilot vs Standard (32)        | EKS with Fargate profiles (partial analog to Autopilot) | AKS Automatic                       |
| GKE Security & Workload Identity (33) | EKS IRSA (IAM Roles for Service Accounts)               | AKS Workload Identity               |
| GKE Operations (34)                   | EKS managed node groups / Karpenter                     | AKS node pools / cluster autoscaler |

> 🔑 **Note:** GKE is widely regarded as the most mature of the three managed Kubernetes offerings, a direct reflection of Google's Borg heritage ([Section 1](../Part1/Section-01-Part1-What-is-GCP-History-Evolution.md)) — this is one of GCP's clearest genuine differentiators, not just marketing.

## 7. Identity, Governance, and Security

| GCP Service (Section)                              | AWS Equivalent                                                                      | Azure Equivalent                                                 |
| -------------------------------------------------- | ----------------------------------------------------------------------------------- | ---------------------------------------------------------------- |
| IAM Fundamentals (35)                              | IAM                                                                                 | Azure RBAC                                                       |
| Service Accounts (36)                              | IAM Roles / Instance Profiles                                                       | Managed Identities                                               |
| Org Policies (37)                                  | Service Control Policies (SCPs)                                                     | Azure Policy                                                     |
| Secret Manager & KMS (38)                          | Secrets Manager / KMS                                                               | Key Vault                                                        |
| Security Command Center (39)                       | Security Hub + GuardDuty + Inspector                                                | Microsoft Defender for Cloud                                     |
| Compliance & Governance (40)                       | AWS Artifact / Config                                                               | Compliance Manager / Azure Policy                                |
| VPC Service Controls (41)                          | (no direct equivalent — closest is VPC endpoint policies + Nitro Enclaves combined) | Service Endpoints / Private Link with NSG restrictions (partial) |
| Cloud Identity & BeyondCorp (42)                   | IAM Identity Center + Verified Access                                               | Microsoft Entra ID + Entra Private Access                        |
| Binary Authorization & Confidential Computing (43) | ECR image scanning + signing / AWS Nitro Enclaves                                   | Azure confidential computing (confidential VMs)                  |

> ⚠️ **Gap worth naming honestly:** VPC Service Controls ([Section 41](../Part5/Section-41-Part5-VPC-Service-Controls.md)) — a perimeter-based data-exfiltration control around managed services — has no clean one-to-one AWS or Azure equivalent; this is a genuine GCP differentiator in the security direction, not a gap, and is worth highlighting distinctly from the gaps noted in [Section 82](./Section-82-Part13-GCP-vs-AWS-vs-Azure-Comparison.md).10.

## 8. Data, Analytics, and AI/ML

| GCP Service (Section)                    | AWS Equivalent                                   | Azure Equivalent                                              |
| ---------------------------------------- | ------------------------------------------------ | ------------------------------------------------------------- |
| BigQuery (44)                            | Redshift / Athena                                | Azure Synapse Analytics                                       |
| Dataflow / Dataproc / Pub/Sub (45)       | Kinesis Data Streams/Firehose / EMR / SNS+SQS    | Azure Stream Analytics / HDInsight / Event Hubs + Service Bus |
| Cloud Composer (46)                      | Amazon MWAA (Managed Airflow)                    | Azure Data Factory                                            |
| Dataplex (47)                            | AWS Lake Formation                               | Microsoft Purview                                             |
| Looker & Looker Studio (48)              | QuickSight                                       | Power BI                                                      |
| Data Pipeline Architecture Patterns (49) | (patterns — provider-agnostic)                   | (patterns — provider-agnostic)                                |
| Vertex AI (65–67)                        | SageMaker                                        | Azure Machine Learning                                        |
| Generative AI: Gemini/PaLM (68)          | Bedrock                                          | Azure OpenAI Service                                          |
| MLOps on GCP (69)                        | SageMaker Pipelines/Model Registry               | Azure ML Pipelines/Model Registry                             |
| AI/ML Security & Responsible AI (70)     | SageMaker security features + Bedrock Guardrails | Azure AI Content Safety / Responsible AI dashboard            |

## 9. DevOps, Observability, and Security Operations

| GCP Service (Section)                        | AWS Equivalent                                                    | Azure Equivalent                             |
| -------------------------------------------- | ----------------------------------------------------------------- | -------------------------------------------- |
| Cloud Build & CI/CD (50)                     | CodeBuild / CodePipeline                                          | Azure Pipelines                              |
| Cloud Deploy (51)                            | CodeDeploy                                                        | Azure DevOps Release / Deployment Center     |
| Terraform on GCP (52)                        | Terraform (provider-agnostic, same tool)                          | Terraform (provider-agnostic, same tool)     |
| Eventarc & Workflows (53)                    | EventBridge / Step Functions                                      | Event Grid / Logic Apps                      |
| Cloud Monitoring/Logging/Trace/Profiler (54) | CloudWatch / X-Ray                                                | Azure Monitor / Application Insights         |
| Incident Response & SRE (55)                 | (practice — provider-agnostic)                                    | (practice — provider-agnostic)               |
| Chronicle SIEM (72–73)                       | Security Lake + partner SIEM (no native equivalent-scale product) | Microsoft Sentinel                           |
| Cloud Armor & Edge Security (74)             | AWS WAF + Shield                                                  | Azure Front Door WAF + Azure DDoS Protection |
| Automated Incident Response (75)             | Security Hub automated response / EventBridge-driven remediation  | Sentinel automation (Logic Apps playbooks)   |
| SOC Patterns (76)                            | Security Hub + Detective                                          | Sentinel + Defender for Cloud                |

## 10. GCP's Genuine Differentiators

- **BigQuery's serverless analytics model:** no cluster to provision or manage at all — query pricing is purely on bytes scanned or flat-rate slots, a genuinely distinct operational model versus Redshift's or Synapse's provisioned-cluster foundations ([Section 44](../Part6/Section-44-Part6-BigQuery-Deep-Dive.md)).
- **Global VPC model:** GCP's VPC-as-a-global-resource design ([Section 19](../Part3/Section-19-Part3-VPC-Fundamentals.md)–[Section 20](../Part3/Section-20-Part3-Subnets-IP-Addressing-and-Routes.md)) is architecturally distinct from both AWS's and Azure's regional-VPC models, simplifying multi-region network design in ways the other two providers require Transit Gateway/Virtual WAN overlays to approximate.
- **Kubernetes/GKE heritage:** GKE's direct lineage from Google's internal Borg system ([Section 1](../Part1/Section-01-Part1-What-is-GCP-History-Evolution.md)) gives it a maturity and operational polish — Autopilot's fully-managed node layer, first-class Workload Identity — that both EKS and AKS have converged toward but arrived at later.
- **TPUs (Tensor Processing Units):** custom AI/ML accelerator silicon unique to GCP ([Section 65](../Part10/Section-65-Part10-Vertex-AI-Fundamentals.md)–[Section 66](../Part10/Section-66-Part10-Vertex-AI-Deep-Dive-Training-Pipelines-Endpoints.md)), offering a genuinely different price/performance profile for large-scale training workloads than GPU-only offerings from AWS and Azure.

## 11. GCP's Genuine Gaps

- **Smaller marketplace and region footprint:** GCP has fewer regions and a smaller third-party marketplace ecosystem than AWS, meaning some workloads with strict low-latency-to-every-market requirements or deep marketplace-integration needs are easier to satisfy on AWS today.
- **No native chaos-engineering product:** as covered in Sections 78–79, GCP has no first-party equivalent to AWS Fault Injection Simulator or Azure Chaos Studio — chaos engineering on GCP requires open-source tooling (Chaos Mesh, Gremlin) rather than a fully-managed native service.
- **Smaller enterprise landing-zone tooling ecosystem:** as covered in [Section 59](../Part9/Section-59-Part9-Landing-Zone-Architecture-Blueprints.md), GCP has no single managed product equivalent to AWS Control Tower or Azure Landing Zone accelerators — the Enterprise Foundations Blueprint is a Terraform reference architecture you deploy and own yourself, not a console-driven managed service, meaning more up-front assembly work for enterprise governance.

## 12. Interview Questions

**🎯 Beginner:** _What is the AWS equivalent of Cloud Run, and how are they similar?_
**Model answer:** AWS App Runner is the closest direct equivalent — both are fully managed serverless platforms for running containerized applications without managing the underlying infrastructure, scaling automatically (including to zero) based on incoming traffic. AWS Fargate (via ECS) is a broader analog for "serverless containers" generally, though it requires more orchestration setup than Cloud Run's single-command deploy model.

**🎯 Intermediate:** _Why is Cloud Spanner difficult to map cleanly to an AWS or Azure equivalent?_
**Model answer:** Spanner combines properties that no single AWS or Azure product offers together: horizontal scalability across regions, strong (external) consistency guarantees backed by Google's TrueTime API, and a familiar relational SQL interface. Aurora offers relational SQL with strong regional consistency but not Spanner's global external-consistency guarantees at scale; Cosmos DB offers global distribution but with a different consistency-model menu and a non-relational-first API surface. This gap is a genuine architectural differentiator, not just a naming difference.

**🎯 Senior/Architect:** _A team is deciding between GCP and AWS for a new global, latency-sensitive multi-region application. What's the most architecturally significant infrastructure difference they should factor into that decision?_
**Model answer:** GCP's global VPC model ([Section 19](../Part3/Section-19-Part3-VPC-Fundamentals.md)) versus AWS's regional VPC model is the most architecturally significant difference for this use case — on GCP, a single VPC spans every region with regional subnets, meaning cross-region private connectivity requires no VPC peering or Transit Gateway at all; on AWS, achieving equivalent cross-region private connectivity requires explicitly provisioning Transit Gateway or peering between regional VPCs. This doesn't make one provider strictly better, but it meaningfully changes the network architecture's complexity and operational surface for a genuinely global, multi-region design, and should be weighed alongside region count, service availability per region, and team familiarity rather than decided on service-name parity alone.

## 13. Key Takeaways

- 🔑 Nearly every GCP service covered in this knowledge base has a direct or close AWS and Azure equivalent — fluent translation across all three is a genuinely valuable, frequently-tested interview and real-world skill.
- 🔑 GCP's global VPC model, BigQuery's serverless analytics, GKE's Borg heritage, and TPUs are its clearest genuine differentiators, not marketing claims.
- 🔑 GCP's gaps are real and specific — smaller region/marketplace footprint, no native chaos-engineering product, and a less turnkey landing-zone tooling ecosystem than AWS Control Tower or Azure Landing Zones.
- 🔑 Feature parity across providers shifts constantly; treat any specific parity claim as a snapshot to be re-verified before it drives a real architectural decision.

## 14. Related Concepts

This comparison table draws on every prior Part of this knowledge base; it feeds directly into the consolidated interview preparation in [Section 83](./Section-83-Part13-Interview-Preparation-Consolidated.md) and the capstone labs in [Section 84](./Section-84-Part13-Hands-On-Labs-Capstone-Projects.md), both of which assume fluency with these cross-provider mappings.
