# 🗺️ AWS Zero-to-Enterprise Knowledge Base — Master Index

A comprehensive, 98-section learning resource organized into 10 parts covering AWS from foundations to enterprise architecture. Navigate by part, read sections sequentially or jump to topics of interest.

---

## Quick Navigation

| Part                             | Topic                                           | Sections |
| -------------------------------- | ----------------------------------------------- | -------- |
| **[Part 1](./Contents/Part1)**   | AWS Foundations & Global Infrastructure         | 1–8      |
| **[Part 2](./Contents/Part2)**   | Identity, Security & Governance                 | 9–18     |
| **[Part 3](./Contents/Part3)**   | Compute                                         | 19–28    |
| **[Part 4](./Contents/Part4)**   | Networking & Content Delivery                   | 29–38    |
| **[Part 5](./Contents/Part5)**   | Storage                                         | 39–48    |
| **[Part 6](./Contents/Part6)**   | Databases                                       | 49–58    |
| **[Part 7](./Contents/Part7)**   | Application Integration & Streaming             | 59–68    |
| **[Part 8](./Contents/Part8)**   | Observability, Monitoring & Management          | 69–78    |
| **[Part 9](./Contents/Part9)**   | Developer Tools, CI/CD & Infrastructure as Code | 79–88    |
| **[Part 10](./Contents/Part10)** | Final Interview Prep & Roadmap Synthesis        | 89–98    |

---

## Folder Structure

```
AWS/
├── README.md (quick-start guide)
├── INDEX.md (this file — comprehensive navigation & section index)
│
└── Contents/ (modular organization by part)
    ├── Part1/ (8 sections: AWS Foundations)
    ├── Part2/ (10 sections: Identity & Security)
    ├── Part3/ (10 sections: Compute)
    ├── Part4/ (10 sections: Networking)
    ├── Part5/ (10 sections: Storage)
    ├── Part6/ (10 sections: Databases)
    ├── Part7/ (10 sections: Application Integration)
    ├── Part8/ (10 sections: Observability)
    ├── Part9/ (10 sections: CI/CD & IaC)
    └── Part10/ (10 sections: Interview Prep & Synthesis)
```

---

## How to Use

### Starting Out

1. **New to AWS?** Start with **[Part 1: Foundations](./Contents/Part1/)** to understand what AWS is and core concepts.
2. Each part folder contains 8-10 self-contained sections covering that part's topics.
3. Each section is a deep-dive with definitions, examples, best practices, and interview questions.

### Progressive Learning

- Read parts in order (1→2→3→...→10) for a complete AWS knowledge progression.
- Within each part, sections build on one another—read them sequentially.
- Skip parts you already know well, but note cross-references to other parts.
- Use interview questions at the end of each part to self-assess understanding.

### For Interview Prep

- **Part 10** is dedicated to final interview preparation and system design walkthroughs.
- Each part ends with an **Interview Drill** section containing common questions and model answers.
- Use **Part 10 §10: Full Roadmap Synthesis** to review high-level patterns across all parts.

### Reference Lookup

- Use the **Quick Navigation** table above to jump to a specific part folder.
- Browse `Contents/PartN/` to see all sections for that part.
- Refer to detailed section tables in each part summary for direct file references.

---

## Part Summaries

### ✅ Part 1 — AWS Foundations & Global Infrastructure (8/8)

What AWS is, cloud models, Regions/AZs/edge locations, the Shared Responsibility Model, AWS accounts, access methods (Console/CLI/SDK), pricing fundamentals, and support plans.

| §   | Section                                      | File                                                             |
| --- | -------------------------------------------- | ---------------------------------------------------------------- |
| 1   | What is AWS & Cloud Computing Fundamentals   | Section-01-Part1-What-is-AWS-and-Cloud-Computing-Fundamentals.md |
| 2   | AWS Global Infrastructure                    | Section-02-Part1-AWS-Global-Infrastructure.md                    |
| 3   | The Shared Responsibility Model              | Section-03-Part1-Shared-Responsibility-Model.md                  |
| 4   | AWS Accounts, Root User & Identity Basics    | Section-04-Part1-AWS-Accounts-Root-User-Identity-Basics.md       |
| 5   | Ways to Interact with AWS                    | Section-05-Part1-Ways-to-Interact-with-AWS.md                    |
| 6   | AWS Pricing & Cost Fundamentals              | Section-06-Part1-AWS-Pricing-and-Cost-Fundamentals.md            |
| 7   | AWS Support Plans & Service Category Map     | Section-07-Part1-AWS-Support-Plans-and-Service-Category-Map.md   |
| 8   | Part 1 Wrap-Up + Foundations Interview Drill | Section-08-Part1-Wrap-Up-and-Foundations-Interview-Drill.md      |

### ✅ Part 2 — Identity, Security & Governance (10/10)

IAM core (users, groups, roles, policies), IAM policy evaluation and types, temporary credentials via STS, IAM Identity Center for federated access, AWS Organizations and SCPs, KMS encryption, secrets management, threat detection (GuardDuty, Security Hub, Config, Inspector), and edge security (WAF, Shield).

| §   | Section                                                                    | File                                                       |
| --- | -------------------------------------------------------------------------- | ---------------------------------------------------------- |
| 1   | IAM Core Concepts — Users, Groups, Roles, Policies                         | Section-09-Part2-IAM-Core-Concepts.md                      |
| 2   | IAM Policy Deep Dive — Structure, Evaluation Logic, Policy Types           | Section-10-Part2-IAM-Policy-Evaluation-Logic.md            |
| 3   | IAM Roles, Trust Policies & Temporary Credentials (STS)                    | Section-11-Part2-IAM-Roles-Trust-Policies-STS.md           |
| 4   | IAM Identity Center (SSO) & Federation                                     | Section-12-Part2-IAM-Identity-Center-SSO-Federation.md     |
| 5   | AWS Organizations & Service Control Policies (SCPs)                        | Section-13-Part2-AWS-Organizations-and-SCPs.md             |
| 6   | Data Protection — KMS & Encryption                                         | Section-14-Part2-KMS-and-Encryption.md                     |
| 7   | Secrets Management — Secrets Manager & Parameter Store                     | Section-15-Part2-Secrets-Manager-and-Parameter-Store.md    |
| 8   | Threat Detection & Compliance — GuardDuty, Security Hub, Config, Inspector | Section-16-Part2-GuardDuty-SecurityHub-Config-Inspector.md |
| 9   | Network & Edge Security — WAF, Shield, Network Firewall                    | Section-17-Part2-WAF-Shield-Network-Firewall.md            |
| 10  | Part 2 Wrap-Up + Security & Governance Interview Drill                     | Section-18-Part2-WrapUp-and-Interview-Drill.md             |

### ✅ Part 3 — Compute (10/10)

EC2 fundamentals and lifecycle, AMIs and instance types, EC2 purchasing options (on-demand, reserved, spot, savings plans), EC2 storage/networking/security integration, Auto Scaling Groups, Elastic Load Balancing, AWS Lambda and serverless, containers (ECS/EKS/Fargate), Elastic Beanstalk, Batch, and Lightsail.

| §   | Section                                        | File                                                  |
| --- | ---------------------------------------------- | ----------------------------------------------------- |
| 1   | EC2 Fundamentals & Architecture                | Section-19-Part3-EC2-Fundamentals-Architecture.md     |
| 2   | AMIs, Instance Types & Instance Lifecycle      | Section-20-Part3-AMIs-Instance-Types-Lifecycle.md     |
| 3   | EC2 Purchasing Options                         | Section-21-Part3-EC2-Purchasing-Options.md            |
| 4   | EC2 Storage, Networking & Security Integration | Section-22-Part3-EC2-Storage-Networking-Security.md   |
| 5   | Auto Scaling Groups                            | Section-23-Part3-Auto-Scaling-Groups.md               |
| 6   | Elastic Load Balancing                         | Section-24-Part3-Elastic-Load-Balancing.md            |
| 7   | AWS Lambda & Serverless Compute                | Section-25-Part3-AWS-Lambda-Serverless-Compute.md     |
| 8   | Containers — ECS, EKS & Fargate                | Section-26-Part3-Containers-ECS-EKS-Fargate.md        |
| 9   | Elastic Beanstalk, Batch & Lightsail           | Section-27-Part3-Elastic-Beanstalk-Batch-Lightsail.md |
| 10  | Part 3 Wrap-Up + Compute Interview Drill       | Section-28-Part3-WrapUp-and-Interview-Drill.md        |

### ✅ Part 4 — Networking & Content Delivery (10/10)

VPC fundamentals and CIDR blocks, subnets and route tables, internet connectivity (IGW/NAT), security groups vs NACLs, VPC peering and Transit Gateway, PrivateLink, hybrid connectivity (VPN and Direct Connect), Route 53 DNS, CloudFront CDN, ACM and API Gateway, VPC endpoints and troubleshooting.

| §   | Section                                                 | File                                                      |
| --- | ------------------------------------------------------- | --------------------------------------------------------- |
| 1   | VPC Fundamentals & Architecture                         | Section-29-Part4-VPC-Fundamentals-Architecture.md         |
| 2   | Subnets, Route Tables & Internet Connectivity (IGW/NAT) | Section-30-Part4-Subnets-RouteTables-IGW-NAT.md           |
| 3   | Security Groups vs NACLs — Full Depth                   | Section-31-Part4-SecurityGroups-vs-NACLs.md               |
| 4   | VPC Peering, Transit Gateway & PrivateLink              | Section-32-Part4-Peering-TransitGateway-PrivateLink.md    |
| 5   | Hybrid Connectivity — VPN & Direct Connect              | Section-33-Part4-VPN-DirectConnect.md                     |
| 6   | Amazon Route 53 — DNS                                   | Section-34-Part4-Route53-DNS.md                           |
| 7   | Amazon CloudFront — CDN                                 | Section-35-Part4-CloudFront-CDN.md                        |
| 8   | AWS Certificate Manager & API Gateway                   | Section-36-Part4-ACM-APIGateway.md                        |
| 9   | VPC Endpoints, Flow Logs & Network Troubleshooting      | Section-37-Part4-VPCEndpoints-FlowLogs-Troubleshooting.md |
| 10  | Part 4 Wrap-Up + Networking Interview Drill             | Section-38-Part4-WrapUp-and-Interview-Drill.md            |

### ✅ Part 5 — Storage (10/10)

S3 fundamentals (buckets, objects, keys), S3 storage classes and lifecycle, S3 security/encryption/access control, S3 advanced features (versioning, replication, performance), EBS volumes and snapshots, EFS, FSx family, Storage Gateway for hybrid storage, and backup/disaster recovery strategies.

| §   | Section                                            | File                                                               |
| --- | -------------------------------------------------- | ------------------------------------------------------------------ |
| 1   | Amazon S3 Fundamentals                             | Section-39-Part5-S3-Fundamentals.md                                |
| 2   | S3 Storage Classes & Lifecycle Management          | Section-40-Part5-S3-Storage-Classes-Lifecycle.md                   |
| 3   | S3 Security, Encryption & Access Control           | Section-41-Part5-S3-Security-Encryption-AccessControl.md           |
| 4   | S3 Advanced — Versioning, Replication, Performance | Section-42-Part5-S3-Advanced-Versioning-Replication-Performance.md |
| 5   | EBS Full Depth                                     | Section-43-Part5-EBS-Full-Depth.md                                 |
| 6   | EFS — Elastic File System                          | Section-44-Part5-EFS-Elastic-File-System.md                        |
| 7   | FSx Family                                         | Section-45-Part5-FSx-Family.md                                     |
| 8   | Storage Gateway & Hybrid                           | Section-46-Part5-Storage-Gateway-Hybrid.md                         |
| 9   | Backup Strategies & DR Patterns                    | Section-47-Part5-Backup-Strategies-DR-Patterns.md                  |
| 10  | Part 5 Wrap-Up & Storage Interview Drill           | Section-48-Part5-WrapUp-and-Interview-Drill.md                     |

### ✅ Part 6 — Databases (10/10)

RDS fundamentals, RDS high availability and read replicas, Aurora deep-dive, DynamoDB fundamentals and advanced features, ElastiCache (Redis/Memcached), Redshift for data warehousing, DocumentDB and Neptune, DMS, and choosing the right database for your workload.

| §   | Section                                    | File                                                   |
| --- | ------------------------------------------ | ------------------------------------------------------ |
| 1   | RDS Fundamentals                           | Section-49-Part6-RDS-Fundamentals.md                   |
| 2   | RDS HA, Read Replicas & Backup             | Section-50-Part6-RDS-HA-ReadReplicas-Backup.md         |
| 3   | Aurora Deep Dive                           | Section-51-Part6-Aurora-Deep-Dive.md                   |
| 4   | DynamoDB Fundamentals & Data Modeling      | Section-52-Part6-DynamoDB-Fundamentals-DataModeling.md |
| 5   | DynamoDB Advanced                          | Section-53-Part6-DynamoDB-Advanced.md                  |
| 6   | ElastiCache (Redis/Memcached)              | Section-54-Part6-ElastiCache-Redis-Memcached.md        |
| 7   | Redshift Data Warehousing                  | Section-55-Part6-Redshift-Data-Warehousing.md          |
| 8   | DocumentDB & Neptune                       | Section-56-Part6-DocumentDB-Neptune.md                 |
| 9   | DMS & Choosing the Right Database          | Section-57-Part6-DMS-Choosing-Right-Database.md        |
| 10  | Part 6 Wrap-Up & Databases Interview Drill | Section-58-Part6-WrapUp-and-Interview-Drill.md         |

### 🟡 Part 7 — Application Integration & Streaming (10/10)

SQS fundamentals and advanced (DLQs, FIFO, visibility timeout), SNS pub/sub messaging, EventBridge for event-driven architecture, Step Functions for orchestration, Kinesis Data Streams and Firehose, Amazon MSK (Kafka), choosing integration patterns, and integration interview drill.

| §   | Section                                        | File                                                        |
| --- | ---------------------------------------------- | ----------------------------------------------------------- |
| 1   | Amazon SQS Fundamentals                        | Section-59-Part7-SQS-Fundamentals.md                        |
| 2   | SQS Advanced — DLQs, FIFO, Visibility Timeout  | Section-60-Part7-SQS-Advanced-DLQ-FIFO-VisibilityTimeout.md |
| 3   | Amazon SNS — Pub/Sub Messaging                 | Section-61-Part7-SNS-PubSub-Messaging.md                    |
| 4   | Amazon EventBridge — Event-Driven Architecture | Section-62-Part7-EventBridge-Event-Driven-Architecture.md   |
| 5   | AWS Step Functions — Orchestration             | Section-63-Part7-StepFunctions-Orchestration.md             |
| 6   | Amazon Kinesis Data Streams                    | Section-64-Part7-Kinesis-Data-Streams.md                    |
| 7   | Kinesis Data Firehose & Data Analytics         | Section-65-Part7-Kinesis-Data-Firehose.md                   |
| 8   | Amazon MSK (Managed Streaming for Kafka)       | Section-66-Part7-Amazon-MSK.md                              |
| 9   | Choosing the Right Integration Pattern         | Section-67-Part7-Choosing-Integration-Pattern.md            |
| 10  | Part 7 Wrap-Up + Integration Interview Drill   | Section-68-Part7-WrapUp-Interview-Drill.md                  |

### 🟡 Part 8 — Observability, Monitoring & Management (10/10)

CloudWatch fundamentals, metrics, logs, and dashboards; CloudWatch alarms; AWS X-Ray for distributed tracing; CloudTrail for audit logging; AWS Config for compliance; Systems Manager; Trusted Advisor and AWS Health Dashboard; observability architecture patterns.

| §   | Section                                                   | File                                                     |
| --- | --------------------------------------------------------- | -------------------------------------------------------- |
| 1   | CloudWatch Fundamentals                                   | Section-69-Part8-CloudWatch-Fundamentals.md              |
| 2   | CloudWatch Logs — Collection, Insights, Log-Based Metrics | Section-70-Part8-CloudWatch-Logs.md                      |
| 3   | CloudWatch Alarms & Dashboards                            | Section-71-Part8-CloudWatch-Alarms-Dashboards.md         |
| 4   | AWS X-Ray — Distributed Tracing                           | Section-72-Part8-XRay-Distributed-Tracing.md             |
| 5   | AWS CloudTrail — Audit & Governance Logging               | Section-73-Part8-CloudTrail-Audit-Governance.md          |
| 6   | AWS Config — Resource Compliance & Configuration History  | Section-74-Part8-AWS-Config.md                           |
| 7   | AWS Systems Manager                                       | Section-75-Part8-Systems-Manager.md                      |
| 8   | Trusted Advisor & AWS Health Dashboard                    | Section-76-Part8-TrustedAdvisor-HealthDashboard.md       |
| 9   | Observability Architecture — Putting It All Together      | Section-77-Part8-Observability-Architecture-Together.md  |
| 10  | Part 8 Wrap-Up + Observability Interview Drill            | Section-78-Part8-WrapUp-Observability-Interview-Drill.md |

### 🟡 Part 9 — Developer Tools, CI/CD & Infrastructure as Code (10/10)

IaC fundamentals and CloudFormation basics, CloudFormation advanced (intrinsic functions, nested stacks, StackSets, drift detection), AWS CDK, Terraform on AWS, CodePipeline and CodeBuild, CodeDeploy, deployment strategies (blue/green, canary, rolling), CI/CD for infrastructure, and choosing the right IaC tool.

| §   | Section                                                                        | File                                                       |
| --- | ------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| 1   | IaC Fundamentals & CloudFormation Basics                                       | Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md |
| 2   | CloudFormation Advanced — Intrinsic Functions, Nested Stacks, StackSets, Drift | Section-80-Part9-CloudFormation-Advanced.md                |
| 3   | AWS CDK — Infrastructure as Real Code                                          | Section-81-Part9-AWS-CDK.md                                |
| 4   | Terraform on AWS — State, Providers, HashiCorp Ecosystem                       | Section-82-Part9-Terraform-on-AWS.md                       |
| 5   | AWS CodePipeline & CodeBuild                                                   | Section-83-Part9-CodePipeline-CodeBuild.md                 |
| 6   | AWS CodeDeploy                                                                 | Section-84-Part9-CodeDeploy.md                             |
| 7   | Deployment Strategies — Blue/Green, Canary, Rolling                            | Section-85-Part9-Deployment-Strategies.md                  |
| 8   | CI/CD for Infrastructure — Pipelines, GitOps, Safe Deployment Patterns         | Section-86-Part9-CICD-Infrastructure-GitOps.md             |
| 9   | Choosing the Right IaC Tool                                                    | Section-87-Part9-Choosing-IaC-Tool.md                      |
| 10  | Part 9 Wrap-Up + IaC Interview Drill                                           | Section-88-Part9-WrapUp-IaC-Interview-Drill.md             |

### 🟡 Part 10 — Final Interview Preparation & Roadmap Synthesis (10/10)

AWS Well-Architected Framework and its six pillars, cost optimization and FinOps, FinOps and disaster recovery capstones, migration strategies (the 7 Rs), Amazon Cognito for application identity, graph databases and ML tie-ins, end-to-end system design walkthroughs, final interview preparation drills, and full roadmap synthesis for continued learning.

| §   | Section                                                                   | File                                             |
| --- | ------------------------------------------------------------------------- | ------------------------------------------------ |
| 1   | AWS Well-Architected Framework — The Six Pillars                          | Section-89-Part10-WellArchitected-Framework.md   |
| 2   | Cost Optimization on AWS — FinOps Fundamentals                            | Section-90-Part10-Cost-Optimization-FinOps.md    |
| 3   | FinOps Capstone — Organization-Wide Cost Governance                       | Section-91-Part10-FinOps-Capstone.md             |
| 4   | Disaster Recovery Strategy — Capstone                                     | Section-92-Part10-DR-Strategy-Capstone.md        |
| 5   | Migration Strategies — The 7 Rs                                           | Section-93-Part10-Migration-Strategies.md        |
| 6   | Amazon Cognito — Identity for Applications                                | Section-94-Part10-Amazon-Cognito.md              |
| 7   | Neptune & Graph ML Tie-In                                                 | Section-95-Part10-Neptune-GraphML.md             |
| 8   | AWS System Design — End-to-End Architecture Walkthroughs                  | Section-96-Part10-System-Design-Walkthroughs.md  |
| 9   | Final Interview Preparation — Behavioral, System Design, Rapid-Fire Drill | Section-97-Part10-Final-Interview-Preparation.md |
| 10  | Full Roadmap Synthesis & Continued Learning Path                          | Section-98-Part10-Full-Roadmap-Synthesis.md      |

---

## Organization & Structure Notes

- **98 sections total**, organized into 10 parts with 8-10 sections each
- **Section numbering:** Continuous across all parts (1–98), not reset per part
  - Part 1: Sections 1–8
  - Part 2: Sections 9–18
  - Part 3: Sections 19–28
  - ... and so on
- **Each part is self-contained** but includes cross-references to related sections in other parts
- **All 98 sections are organized in `Contents/PartN/` folders** for modular, scalable structure
- **Single navigation source:** This INDEX.md is the master reference for all parts and sections

---

## Progress Summary

- ✅ **Parts 1–6:** Complete (48 sections)
- 🟡 **Parts 7–10:** Complete (50 sections)
- **Total:** 98 / 98 sections ✅

**Key note:** Parts 7–10 include newly-added sections (Systems Manager, Trusted Advisor, AWS Health, CodePipeline/CodeBuild/CodeDeploy, Deployment Strategies, DR & FinOps Capstones, Cognito, Neptune Graph ML) to align with modern AWS practices.

---

## Getting Started

1. **Pick a part** from the Quick Navigation table above (or scroll to part summaries).
2. **Open that part's folder** (e.g., `Contents/Part1/`) to browse all sections for that part.
3. **Read sections in order** within each part for cumulative understanding.
4. **Complete interview drills** at the end of each part (usually the final section).
5. **Cross-reference:** Follow section links for related topics across parts.
6. **For detailed lookup:** Refer to the tables under each part summary to find specific topics and filenames.

---

_Last updated: July 23, 2026_
