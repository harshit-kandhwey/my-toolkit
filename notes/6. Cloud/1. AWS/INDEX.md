# AWS Zero-to-Enterprise Knowledge Base — Index

A comprehensive, 131-section learning resource organized into 15 parts covering AWS from foundations to enterprise architecture. Navigate by part, read sections sequentially, or jump to topics of interest.

---

## Quick Navigation

| Part                             | Topic                                               | Sections |
| -------------------------------- | --------------------------------------------------- | -------- |
| **[Part 1](./Contents/Part1)**   | AWS Foundations & Global Infrastructure             | 1–8      |
| **[Part 2](./Contents/Part2)**   | Identity, Security & Governance                     | 9–18     |
| **[Part 3](./Contents/Part3)**   | Compute                                             | 19–28    |
| **[Part 4](./Contents/Part4)**   | Networking & Content Delivery                       | 29–38    |
| **[Part 5](./Contents/Part5)**   | Storage                                             | 39–48    |
| **[Part 6](./Contents/Part6)**   | Databases                                           | 49–58    |
| **[Part 7](./Contents/Part7)**   | Application Integration & Streaming                 | 59–68    |
| **[Part 8](./Contents/Part8)**   | Observability, Monitoring & Management              | 69–78    |
| **[Part 9](./Contents/Part9)**   | Developer Tools, CI/CD & Infrastructure as Code     | 79–88    |
| **[Part 10](./Contents/Part10)** | Final Interview Prep & Roadmap Synthesis            | 89–98    |
| **[Part 11](./Contents/Part11)** | Data Engineering & Analytics on AWS                 | 99–107   |
| **[Part 12](./Contents/Part12)** | AI/ML & Generative AI on AWS                        | 108–114  |
| **[Part 13](./Contents/Part13)** | Enterprise Landing Zones & Multi-Account Operations | 115–120  |
| **[Part 14](./Contents/Part14)** | Security Operations & Incident Response             | 121–126  |
| **[Part 15](./Contents/Part15)** | Resilience Testing & Continuous DR Validation       | 127–131  |

---

## Folder Structure

```
AWS/
├── README.md (quick-start guide)
├── INDEX.md (this file — comprehensive navigation & section index)
│
└── Contents/ (modular organization by part)
    ├── Part1/  (8 sections: AWS Foundations)
    ├── Part2/  (10 sections: Identity & Security)
    ├── Part3/  (10 sections: Compute)
    ├── Part4/  (10 sections: Networking)
    ├── Part5/  (10 sections: Storage)
    ├── Part6/  (10 sections: Databases)
    ├── Part7/  (10 sections: Application Integration)
    ├── Part8/  (10 sections: Observability)
    ├── Part9/  (10 sections: CI/CD & IaC)
    ├── Part10/ (10 sections: Interview Prep & Synthesis)
    ├── Part11/ (9 sections: Data Engineering & Analytics)
    ├── Part12/ (7 sections: AI/ML & Generative AI)
    ├── Part13/ (6 sections: Landing Zones & Multi-Account)
    ├── Part14/ (6 sections: Security Operations)
    └── Part15/ (5 sections: Resilience Testing)
```

---

## Part Summaries

### Part 1 — AWS Foundations & Global Infrastructure

What AWS is, cloud models, Regions/AZs/edge locations, the Shared Responsibility Model, AWS accounts, access methods (Console/CLI/SDK), pricing fundamentals, and support plans.

| §   | Section                                      | File                                                                                                                                               |
| --- | -------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | What is AWS & Cloud Computing Fundamentals   | [Section-01-Part1-What-is-AWS-and-Cloud-Computing-Fundamentals](./Contents/Part1/Section-01-Part1-What-is-AWS-and-Cloud-Computing-Fundamentals.md) |
| 2   | AWS Global Infrastructure                    | [Section-02-Part1-AWS-Global-Infrastructure](./Contents/Part1/Section-02-Part1-AWS-Global-Infrastructure.md)                                       |
| 3   | The Shared Responsibility Model              | [Section-03-Part1-Shared-Responsibility-Model](./Contents/Part1/Section-03-Part1-Shared-Responsibility-Model.md)                                   |
| 4   | AWS Accounts, Root User & Identity Basics    | [Section-04-Part1-AWS-Accounts-Root-User-Identity-Basics](./Contents/Part1/Section-04-Part1-AWS-Accounts-Root-User-Identity-Basics.md)             |
| 5   | Ways to Interact with AWS                    | [Section-05-Part1-Ways-to-Interact-with-AWS](./Contents/Part1/Section-05-Part1-Ways-to-Interact-with-AWS.md)                                       |
| 6   | AWS Pricing & Cost Fundamentals              | [Section-06-Part1-AWS-Pricing-and-Cost-Fundamentals](./Contents/Part1/Section-06-Part1-AWS-Pricing-and-Cost-Fundamentals.md)                       |
| 7   | AWS Support Plans & Service Category Map     | [Section-07-Part1-AWS-Support-Plans-and-Service-Category-Map](./Contents/Part1/Section-07-Part1-AWS-Support-Plans-and-Service-Category-Map.md)     |
| 8   | Part 1 Wrap-Up + Foundations Interview Drill | [Section-08-Part1-Wrap-Up-and-Foundations-Interview-Drill](./Contents/Part1/Section-08-Part1-Wrap-Up-and-Foundations-Interview-Drill.md)           |

### Part 2 — Identity, Security & Governance

IAM core (users, groups, roles, policies), IAM policy evaluation and types, temporary credentials via STS, IAM Identity Center for federated access, AWS Organizations and SCPs, KMS encryption, secrets management, threat detection (GuardDuty, Security Hub, Config, Inspector), and edge security (WAF, Shield).

| §   | Section                                                                    | File                                                                                                                                   |
| --- | -------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | IAM Core Concepts — Users, Groups, Roles, Policies                         | [Section-09-Part2-IAM-Core-Concepts](./Contents/Part2/Section-09-Part2-IAM-Core-Concepts.md)                                           |
| 2   | IAM Policy Deep Dive — Structure, Evaluation Logic, Policy Types           | [Section-10-Part2-IAM-Policy-Evaluation-Logic](./Contents/Part2/Section-10-Part2-IAM-Policy-Evaluation-Logic.md)                       |
| 3   | IAM Roles, Trust Policies & Temporary Credentials (STS)                    | [Section-11-Part2-IAM-Roles-Trust-Policies-STS](./Contents/Part2/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md)                     |
| 4   | IAM Identity Center (SSO) & Federation                                     | [Section-12-Part2-IAM-Identity-Center-SSO-Federation](./Contents/Part2/Section-12-Part2-IAM-Identity-Center-SSO-Federation.md)         |
| 5   | AWS Organizations & Service Control Policies (SCPs)                        | [Section-13-Part2-AWS-Organizations-and-SCPs](./Contents/Part2/Section-13-Part2-AWS-Organizations-and-SCPs.md)                         |
| 6   | Data Protection — KMS & Encryption                                         | [Section-14-Part2-KMS-and-Encryption](./Contents/Part2/Section-14-Part2-KMS-and-Encryption.md)                                         |
| 7   | Secrets Management — Secrets Manager & Parameter Store                     | [Section-15-Part2-Secrets-Manager-and-Parameter-Store](./Contents/Part2/Section-15-Part2-Secrets-Manager-and-Parameter-Store.md)       |
| 8   | Threat Detection & Compliance — GuardDuty, Security Hub, Config, Inspector | [Section-16-Part2-GuardDuty-SecurityHub-Config-Inspector](./Contents/Part2/Section-16-Part2-GuardDuty-SecurityHub-Config-Inspector.md) |
| 9   | Network & Edge Security — WAF, Shield, Network Firewall                    | [Section-17-Part2-WAF-Shield-Network-Firewall](./Contents/Part2/Section-17-Part2-WAF-Shield-Network-Firewall.md)                       |
| 10  | Part 2 Wrap-Up + Security & Governance Interview Drill                     | [Section-18-Part2-WrapUp-and-Interview-Drill](./Contents/Part2/Section-18-Part2-WrapUp-and-Interview-Drill.md)                         |

### Part 3 — Compute

EC2 fundamentals and lifecycle, AMIs and instance types, EC2 purchasing options (on-demand, reserved, spot, savings plans), EC2 storage/networking/security integration, Auto Scaling Groups, Elastic Load Balancing, AWS Lambda and serverless, containers (ECS/EKS/Fargate), Elastic Beanstalk, Batch, and Lightsail.

| §   | Section                                        | File                                                                                                                         |
| --- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------- |
| 1   | EC2 Fundamentals & Architecture                | [Section-19-Part3-EC2-Fundamentals-Architecture](./Contents/Part3/Section-19-Part3-EC2-Fundamentals-Architecture.md)         |
| 2   | AMIs, Instance Types & Instance Lifecycle      | [Section-20-Part3-AMIs-Instance-Types-Lifecycle](./Contents/Part3/Section-20-Part3-AMIs-Instance-Types-Lifecycle.md)         |
| 3   | EC2 Purchasing Options                         | [Section-21-Part3-EC2-Purchasing-Options](./Contents/Part3/Section-21-Part3-EC2-Purchasing-Options.md)                       |
| 4   | EC2 Storage, Networking & Security Integration | [Section-22-Part3-EC2-Storage-Networking-Security](./Contents/Part3/Section-22-Part3-EC2-Storage-Networking-Security.md)     |
| 5   | Auto Scaling Groups                            | [Section-23-Part3-Auto-Scaling-Groups](./Contents/Part3/Section-23-Part3-Auto-Scaling-Groups.md)                             |
| 6   | Elastic Load Balancing                         | [Section-24-Part3-Elastic-Load-Balancing](./Contents/Part3/Section-24-Part3-Elastic-Load-Balancing.md)                       |
| 7   | AWS Lambda & Serverless Compute                | [Section-25-Part3-AWS-Lambda-Serverless-Compute](./Contents/Part3/Section-25-Part3-AWS-Lambda-Serverless-Compute.md)         |
| 8   | Containers — ECS, EKS & Fargate                | [Section-26-Part3-Containers-ECS-EKS-Fargate](./Contents/Part3/Section-26-Part3-Containers-ECS-EKS-Fargate.md)               |
| 9   | Elastic Beanstalk, Batch & Lightsail           | [Section-27-Part3-Elastic-Beanstalk-Batch-Lightsail](./Contents/Part3/Section-27-Part3-Elastic-Beanstalk-Batch-Lightsail.md) |
| 10  | Part 3 Wrap-Up + Compute Interview Drill       | [Section-28-Part3-WrapUp-and-Interview-Drill](./Contents/Part3/Section-28-Part3-WrapUp-and-Interview-Drill.md)               |

### Part 4 — Networking & Content Delivery

VPC fundamentals and CIDR blocks, subnets and route tables, internet connectivity (IGW/NAT), security groups vs NACLs, VPC peering and Transit Gateway, PrivateLink, hybrid connectivity (VPN and Direct Connect), Route 53 DNS, CloudFront CDN, ACM and API Gateway, VPC endpoints and troubleshooting.

| §   | Section                                                 | File                                                                                                                                 |
| --- | ------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | VPC Fundamentals & Architecture                         | [Section-29-Part4-VPC-Fundamentals-Architecture](./Contents/Part4/Section-29-Part4-VPC-Fundamentals-Architecture.md)                 |
| 2   | Subnets, Route Tables & Internet Connectivity (IGW/NAT) | [Section-30-Part4-Subnets-RouteTables-IGW-NAT](./Contents/Part4/Section-30-Part4-Subnets-RouteTables-IGW-NAT.md)                     |
| 3   | Security Groups vs NACLs — Full Depth                   | [Section-31-Part4-SecurityGroups-vs-NACLs](./Contents/Part4/Section-31-Part4-SecurityGroups-vs-NACLs.md)                             |
| 4   | VPC Peering, Transit Gateway & PrivateLink              | [Section-32-Part4-Peering-TransitGateway-PrivateLink](./Contents/Part4/Section-32-Part4-Peering-TransitGateway-PrivateLink.md)       |
| 5   | Hybrid Connectivity — VPN & Direct Connect              | [Section-33-Part4-VPN-DirectConnect](./Contents/Part4/Section-33-Part4-VPN-DirectConnect.md)                                         |
| 6   | Amazon Route 53 — DNS                                   | [Section-34-Part4-Route53-DNS](./Contents/Part4/Section-34-Part4-Route53-DNS.md)                                                     |
| 7   | Amazon CloudFront — CDN                                 | [Section-35-Part4-CloudFront-CDN](./Contents/Part4/Section-35-Part4-CloudFront-CDN.md)                                               |
| 8   | AWS Certificate Manager & API Gateway                   | [Section-36-Part4-ACM-APIGateway](./Contents/Part4/Section-36-Part4-ACM-APIGateway.md)                                               |
| 9   | VPC Endpoints, Flow Logs & Network Troubleshooting      | [Section-37-Part4-VPCEndpoints-FlowLogs-Troubleshooting](./Contents/Part4/Section-37-Part4-VPCEndpoints-FlowLogs-Troubleshooting.md) |
| 10  | Part 4 Wrap-Up + Networking Interview Drill             | [Section-38-Part4-WrapUp-and-Interview-Drill](./Contents/Part4/Section-38-Part4-WrapUp-and-Interview-Drill.md)                       |

### Part 5 — Storage

S3 fundamentals (buckets, objects, keys), S3 storage classes and lifecycle, S3 security/encryption/access control, S3 advanced features (versioning, replication, performance), EBS volumes and snapshots, EFS, FSx family, Storage Gateway for hybrid storage, and backup/disaster recovery strategies.

| §   | Section                                            | File                                                                                                                                                   |
| --- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1   | Amazon S3 Fundamentals                             | [Section-39-Part5-S3-Fundamentals](./Contents/Part5/Section-39-Part5-S3-Fundamentals.md)                                                               |
| 2   | S3 Storage Classes & Lifecycle Management          | [Section-40-Part5-S3-Storage-Classes-Lifecycle](./Contents/Part5/Section-40-Part5-S3-Storage-Classes-Lifecycle.md)                                     |
| 3   | S3 Security, Encryption & Access Control           | [Section-41-Part5-S3-Security-Encryption-AccessControl](./Contents/Part5/Section-41-Part5-S3-Security-Encryption-AccessControl.md)                     |
| 4   | S3 Advanced — Versioning, Replication, Performance | [Section-42-Part5-S3-Advanced-Versioning-Replication-Performance](./Contents/Part5/Section-42-Part5-S3-Advanced-Versioning-Replication-Performance.md) |
| 5   | EBS Full Depth                                     | [Section-43-Part5-EBS-Full-Depth](./Contents/Part5/Section-43-Part5-EBS-Full-Depth.md)                                                                 |
| 6   | EFS — Elastic File System                          | [Section-44-Part5-EFS-Elastic-File-System](./Contents/Part5/Section-44-Part5-EFS-Elastic-File-System.md)                                               |
| 7   | FSx Family                                         | [Section-45-Part5-FSx-Family](./Contents/Part5/Section-45-Part5-FSx-Family.md)                                                                         |
| 8   | Storage Gateway & Hybrid                           | [Section-46-Part5-Storage-Gateway-Hybrid](./Contents/Part5/Section-46-Part5-Storage-Gateway-Hybrid.md)                                                 |
| 9   | Backup Strategies & DR Patterns                    | [Section-47-Part5-Backup-Strategies-DR-Patterns](./Contents/Part5/Section-47-Part5-Backup-Strategies-DR-Patterns.md)                                   |
| 10  | Part 5 Wrap-Up & Storage Interview Drill           | [Section-48-Part5-WrapUp-and-Interview-Drill](./Contents/Part5/Section-48-Part5-WrapUp-and-Interview-Drill.md)                                         |

### Part 6 — Databases

RDS fundamentals, RDS high availability and read replicas, Aurora deep-dive, DynamoDB fundamentals and advanced features, ElastiCache (Redis/Memcached), Redshift for data warehousing, DocumentDB and Neptune, DMS, and choosing the right database for your workload.

| §   | Section                                    | File                                                                                                                           |
| --- | ------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------ |
| 1   | RDS Fundamentals                           | [Section-49-Part6-RDS-Fundamentals](./Contents/Part6/Section-49-Part6-RDS-Fundamentals.md)                                     |
| 2   | RDS HA, Read Replicas & Backup             | [Section-50-Part6-RDS-HA-ReadReplicas-Backup](./Contents/Part6/Section-50-Part6-RDS-HA-ReadReplicas-Backup.md)                 |
| 3   | Aurora Deep Dive                           | [Section-51-Part6-Aurora-Deep-Dive](./Contents/Part6/Section-51-Part6-Aurora-Deep-Dive.md)                                     |
| 4   | DynamoDB Fundamentals & Data Modeling      | [Section-52-Part6-DynamoDB-Fundamentals-DataModeling](./Contents/Part6/Section-52-Part6-DynamoDB-Fundamentals-DataModeling.md) |
| 5   | DynamoDB Advanced                          | [Section-53-Part6-DynamoDB-Advanced](./Contents/Part6/Section-53-Part6-DynamoDB-Advanced.md)                                   |
| 6   | ElastiCache (Redis/Memcached)              | [Section-54-Part6-ElastiCache-Redis-Memcached](./Contents/Part6/Section-54-Part6-ElastiCache-Redis-Memcached.md)               |
| 7   | Redshift Data Warehousing                  | [Section-55-Part6-Redshift-Data-Warehousing](./Contents/Part6/Section-55-Part6-Redshift-Data-Warehousing.md)                   |
| 8   | DocumentDB & Neptune                       | [Section-56-Part6-DocumentDB-Neptune](./Contents/Part6/Section-56-Part6-DocumentDB-Neptune.md)                                 |
| 9   | DMS & Choosing the Right Database          | [Section-57-Part6-DMS-Choosing-Right-Database](./Contents/Part6/Section-57-Part6-DMS-Choosing-Right-Database.md)               |
| 10  | Part 6 Wrap-Up & Databases Interview Drill | [Section-58-Part6-WrapUp-and-Interview-Drill](./Contents/Part6/Section-58-Part6-WrapUp-and-Interview-Drill.md)                 |

### Part 7 — Application Integration & Streaming

SQS fundamentals and advanced (DLQs, FIFO, visibility timeout), SNS pub/sub messaging, EventBridge for event-driven architecture, Step Functions for orchestration, Kinesis Data Streams and Firehose, Amazon MSK (Kafka), choosing integration patterns, and integration interview drill.

| §   | Section                                        | File                                                                                                                                     |
| --- | ---------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Amazon SQS Fundamentals                        | [Section-59-Part7-SQS-Fundamentals](./Contents/Part7/Section-59-Part7-SQS-Fundamentals.md)                                               |
| 2   | SQS Advanced — DLQs, FIFO, Visibility Timeout  | [Section-60-Part7-SQS-Advanced-DLQ-FIFO-VisibilityTimeout](./Contents/Part7/Section-60-Part7-SQS-Advanced-DLQ-FIFO-VisibilityTimeout.md) |
| 3   | Amazon SNS — Pub/Sub Messaging                 | [Section-61-Part7-SNS-PubSub-Messaging](./Contents/Part7/Section-61-Part7-SNS-PubSub-Messaging.md)                                       |
| 4   | Amazon EventBridge — Event-Driven Architecture | [Section-62-Part7-EventBridge-Event-Driven-Architecture](./Contents/Part7/Section-62-Part7-EventBridge-Event-Driven-Architecture.md)     |
| 5   | AWS Step Functions — Orchestration             | [Section-63-Part7-StepFunctions-Orchestration](./Contents/Part7/Section-63-Part7-StepFunctions-Orchestration.md)                         |
| 6   | Amazon Kinesis Data Streams                    | [Section-64-Part7-Kinesis-Data-Streams](./Contents/Part7/Section-64-Part7-Kinesis-Data-Streams.md)                                       |
| 7   | Kinesis Data Firehose & Data Analytics         | [Section-65-Part7-Kinesis-Data-Firehose](./Contents/Part7/Section-65-Part7-Kinesis-Data-Firehose.md)                                     |
| 8   | Amazon MSK (Managed Streaming for Kafka)       | [Section-66-Part7-Amazon-MSK](./Contents/Part7/Section-66-Part7-Amazon-MSK.md)                                                           |
| 9   | Choosing the Right Integration Pattern         | [Section-67-Part7-Choosing-Integration-Pattern](./Contents/Part7/Section-67-Part7-Choosing-Integration-Pattern.md)                       |
| 10  | Part 7 Wrap-Up + Integration Interview Drill   | [Section-68-Part7-WrapUp-Interview-Drill](./Contents/Part7/Section-68-Part7-WrapUp-Interview-Drill.md)                                   |

### Part 8 — Observability, Monitoring & Management

CloudWatch fundamentals, metrics, logs, and dashboards; CloudWatch alarms; AWS X-Ray for distributed tracing; CloudTrail for audit logging; AWS Config for compliance; Systems Manager; Trusted Advisor and AWS Health Dashboard; observability architecture patterns.

| §   | Section                                                   | File                                                                                                                               |
| --- | --------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| 1   | CloudWatch Fundamentals                                   | [Section-69-Part8-CloudWatch-Fundamentals](./Contents/Part8/Section-69-Part8-CloudWatch-Fundamentals.md)                           |
| 2   | CloudWatch Logs — Collection, Insights, Log-Based Metrics | [Section-70-Part8-CloudWatch-Logs](./Contents/Part8/Section-70-Part8-CloudWatch-Logs.md)                                           |
| 3   | CloudWatch Alarms & Dashboards                            | [Section-71-Part8-CloudWatch-Alarms-Dashboards](./Contents/Part8/Section-71-Part8-CloudWatch-Alarms-Dashboards.md)                 |
| 4   | AWS X-Ray — Distributed Tracing                           | [Section-72-Part8-XRay-Distributed-Tracing](./Contents/Part8/Section-72-Part8-XRay-Distributed-Tracing.md)                         |
| 5   | AWS CloudTrail — Audit & Governance Logging               | [Section-73-Part8-CloudTrail-Audit-Governance](./Contents/Part8/Section-73-Part8-CloudTrail-Audit-Governance.md)                   |
| 6   | AWS Config — Resource Compliance & Configuration History  | [Section-74-Part8-AWS-Config](./Contents/Part8/Section-74-Part8-AWS-Config.md)                                                     |
| 7   | AWS Systems Manager                                       | [Section-75-Part8-Systems-Manager](./Contents/Part8/Section-75-Part8-Systems-Manager.md)                                           |
| 8   | Trusted Advisor & AWS Health Dashboard                    | [Section-76-Part8-TrustedAdvisor-HealthDashboard](./Contents/Part8/Section-76-Part8-TrustedAdvisor-HealthDashboard.md)             |
| 9   | Observability Architecture — Putting It All Together      | [Section-77-Part8-Observability-Architecture-Together](./Contents/Part8/Section-77-Part8-Observability-Architecture-Together.md)   |
| 10  | Part 8 Wrap-Up + Observability Interview Drill            | [Section-78-Part8-WrapUp-Observability-Interview-Drill](./Contents/Part8/Section-78-Part8-WrapUp-Observability-Interview-Drill.md) |

### Part 9 — Developer Tools, CI/CD & Infrastructure as Code

IaC fundamentals and CloudFormation basics, CloudFormation advanced (intrinsic functions, nested stacks, StackSets, drift detection), AWS CDK, Terraform on AWS, CodePipeline and CodeBuild, CodeDeploy, deployment strategies (blue/green, canary, rolling), CI/CD for infrastructure, and choosing the right IaC tool.

| §   | Section                                                                        | File                                                                                                                                   |
| --- | ------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | IaC Fundamentals & CloudFormation Basics                                       | [Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics](./Contents/Part9/Section-79-Part9-IaC-Fundamentals-CloudFormation-Basics.md) |
| 2   | CloudFormation Advanced — Intrinsic Functions, Nested Stacks, StackSets, Drift | [Section-80-Part9-CloudFormation-Advanced](./Contents/Part9/Section-80-Part9-CloudFormation-Advanced.md)                               |
| 3   | AWS CDK — Infrastructure as Real Code                                          | [Section-81-Part9-AWS-CDK](./Contents/Part9/Section-81-Part9-AWS-CDK.md)                                                               |
| 4   | Terraform on AWS — State, Providers, HashiCorp Ecosystem                       | [Section-82-Part9-Terraform-on-AWS](./Contents/Part9/Section-82-Part9-Terraform-on-AWS.md)                                             |
| 5   | AWS CodePipeline & CodeBuild                                                   | [Section-83-Part9-CodePipeline-CodeBuild](./Contents/Part9/Section-83-Part9-CodePipeline-CodeBuild.md)                                 |
| 6   | AWS CodeDeploy                                                                 | [Section-84-Part9-CodeDeploy](./Contents/Part9/Section-84-Part9-CodeDeploy.md)                                                         |
| 7   | Deployment Strategies — Blue/Green, Canary, Rolling                            | [Section-85-Part9-Deployment-Strategies](./Contents/Part9/Section-85-Part9-Deployment-Strategies.md)                                   |
| 8   | CI/CD for Infrastructure — Pipelines, GitOps, Safe Deployment Patterns         | [Section-86-Part9-CICD-Infrastructure-GitOps](./Contents/Part9/Section-86-Part9-CICD-Infrastructure-GitOps.md)                         |
| 9   | Choosing the Right IaC Tool                                                    | [Section-87-Part9-Choosing-IaC-Tool](./Contents/Part9/Section-87-Part9-Choosing-IaC-Tool.md)                                           |
| 10  | Part 9 Wrap-Up + IaC Interview Drill                                           | [Section-88-Part9-WrapUp-IaC-Interview-Drill](./Contents/Part9/Section-88-Part9-WrapUp-IaC-Interview-Drill.md)                         |

### Part 10 — Final Interview Preparation & Roadmap Synthesis

AWS Well-Architected Framework and its six pillars, cost optimization and FinOps, FinOps and disaster recovery capstones, migration strategies (the 7 Rs), Amazon Cognito for application identity, graph databases and ML tie-ins, end-to-end system design walkthroughs, final interview preparation drills, and full roadmap synthesis for continued learning.

| §   | Section                                                                   | File                                                                                                                |
| --- | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| 1   | AWS Well-Architected Framework — The Six Pillars                          | [Section-89-Part10-WellArchitected-Framework](./Contents/Part10/Section-89-Part10-WellArchitected-Framework.md)     |
| 2   | Cost Optimization on AWS — FinOps Fundamentals                            | [Section-90-Part10-Cost-Optimization-FinOps](./Contents/Part10/Section-90-Part10-Cost-Optimization-FinOps.md)       |
| 3   | FinOps Capstone — Organization-Wide Cost Governance                       | [Section-91-Part10-FinOps-Capstone](./Contents/Part10/Section-91-Part10-FinOps-Capstone.md)                         |
| 4   | Disaster Recovery Strategy — Capstone                                     | [Section-92-Part10-DR-Strategy-Capstone](./Contents/Part10/Section-92-Part10-DR-Strategy-Capstone.md)               |
| 5   | Migration Strategies — The 7 Rs                                           | [Section-93-Part10-Migration-Strategies](./Contents/Part10/Section-93-Part10-Migration-Strategies.md)               |
| 6   | Amazon Cognito — Identity for Applications                                | [Section-94-Part10-Amazon-Cognito](./Contents/Part10/Section-94-Part10-Amazon-Cognito.md)                           |
| 7   | Neptune & Graph ML Tie-In                                                 | [Section-95-Part10-Neptune-GraphML](./Contents/Part10/Section-95-Part10-Neptune-GraphML.md)                         |
| 8   | AWS System Design — End-to-End Architecture Walkthroughs                  | [Section-96-Part10-System-Design-Walkthroughs](./Contents/Part10/Section-96-Part10-System-Design-Walkthroughs.md)   |
| 9   | Final Interview Preparation — Behavioral, System Design, Rapid-Fire Drill | [Section-97-Part10-Final-Interview-Preparation](./Contents/Part10/Section-97-Part10-Final-Interview-Preparation.md) |
| 10  | Full Roadmap Synthesis & Continued Learning Path                          | [Section-98-Part10-Full-Roadmap-Synthesis](./Contents/Part10/Section-98-Part10-Full-Roadmap-Synthesis.md)           |

### Part 11 — Data Engineering & Analytics on AWS

Data lakes and AWS Glue/Data Catalog, Lake Formation governance, Athena, EMR, Redshift Spectrum, QuickSight, OpenSearch Service, lakehouse/ETL-ELT architecture patterns, and a data & analytics interview drill.

| §   | Section                                                     | File                                                                                                                                        |
| --- | ----------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------- |
| 1   | Data Lake Fundamentals & AWS Glue / Data Catalog            | [Section-99-Part11-Data-Lake-Fundamentals-Glue-DataCatalog](./Contents/Part11/Section-99-Part11-Data-Lake-Fundamentals-Glue-DataCatalog.md) |
| 2   | AWS Lake Formation — Governance & Fine-Grained Access       | [Section-100-Part11-Lake-Formation](./Contents/Part11/Section-100-Part11-Lake-Formation.md)                                                 |
| 3   | Amazon Athena — Serverless SQL Query                        | [Section-101-Part11-Athena](./Contents/Part11/Section-101-Part11-Athena.md)                                                                 |
| 4   | Amazon EMR — Big Data Processing                            | [Section-102-Part11-EMR](./Contents/Part11/Section-102-Part11-EMR.md)                                                                       |
| 5   | Redshift Spectrum — Bridging Warehouse & Lake               | [Section-103-Part11-Redshift-Spectrum](./Contents/Part11/Section-103-Part11-Redshift-Spectrum.md)                                           |
| 6   | Amazon QuickSight — BI & Visualization                      | [Section-104-Part11-QuickSight](./Contents/Part11/Section-104-Part11-QuickSight.md)                                                         |
| 7   | Amazon OpenSearch Service — Search & Log Analytics          | [Section-105-Part11-OpenSearch](./Contents/Part11/Section-105-Part11-OpenSearch.md)                                                         |
| 8   | Data Engineering Architecture Patterns — Lakehouse, ETL/ELT | [Section-106-Part11-Data-Architecture-Patterns](./Contents/Part11/Section-106-Part11-Data-Architecture-Patterns.md)                         |
| 9   | Part 11 Wrap-Up + Data & Analytics Interview Drill          | [Section-107-Part11-WrapUp-Interview-Drill](./Contents/Part11/Section-107-Part11-WrapUp-Interview-Drill.md)                                 |

### Part 12 — AI/ML & Generative AI on AWS

SageMaker fundamentals and deep dive, MLOps and model monitoring, Bedrock fundamentals and deep dive (agents, knowledge bases, guardrails), AI/ML security and governance, and an AI/ML interview drill.

| §   | Section                                                       | File                                                                                                            |
| --- | ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| 1   | ML on AWS Fundamentals & Amazon SageMaker                     | [Section-108-Part12-SageMaker-Fundamentals](./Contents/Part12/Section-108-Part12-SageMaker-Fundamentals.md)     |
| 2   | SageMaker Deep Dive — Training, Tuning, Deployment, Pipelines | [Section-109-Part12-SageMaker-DeepDive](./Contents/Part12/Section-109-Part12-SageMaker-DeepDive.md)             |
| 3   | Model Monitoring & MLOps on AWS                               | [Section-110-Part12-MLOps-Model-Monitoring](./Contents/Part12/Section-110-Part12-MLOps-Model-Monitoring.md)     |
| 4   | Amazon Bedrock — Generative AI Fundamentals                   | [Section-111-Part12-Bedrock-Fundamentals](./Contents/Part12/Section-111-Part12-Bedrock-Fundamentals.md)         |
| 5   | Bedrock Deep Dive — Agents, Knowledge Bases, Guardrails       | [Section-112-Part12-Bedrock-DeepDive](./Contents/Part12/Section-112-Part12-Bedrock-DeepDive.md)                 |
| 6   | AI/ML Security & Governance                                   | [Section-113-Part12-AIML-Security-Governance](./Contents/Part12/Section-113-Part12-AIML-Security-Governance.md) |
| 7   | Part 12 Wrap-Up + AI/ML Interview Drill                       | [Section-114-Part12-WrapUp-Interview-Drill](./Contents/Part12/Section-114-Part12-WrapUp-Interview-Drill.md)     |

### Part 13 — Enterprise Landing Zones & Multi-Account Operations

Multi-account strategy and Control Tower, Account Factory, centralized logging/audit accounts, delegated administration, guardrail operations, and a landing-zone interview drill.

| §   | Section                                                | File                                                                                                              |
| --- | ------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------- |
| 1   | Multi-Account Strategy & AWS Control Tower             | [Section-115-Part13-ControlTower](./Contents/Part13/Section-115-Part13-ControlTower.md)                           |
| 2   | Account Factory & Automated Account Vending            | [Section-116-Part13-Account-Factory](./Contents/Part13/Section-116-Part13-Account-Factory.md)                     |
| 3   | Centralized Logging & Audit Account Architecture       | [Section-117-Part13-Centralized-Logging-Audit](./Contents/Part13/Section-117-Part13-Centralized-Logging-Audit.md) |
| 4   | Delegated Administration Across AWS Services           | [Section-118-Part13-Delegated-Administration](./Contents/Part13/Section-118-Part13-Delegated-Administration.md)   |
| 5   | Guardrails — Preventive & Detective Control Operations | [Section-119-Part13-Guardrails-Operations](./Contents/Part13/Section-119-Part13-Guardrails-Operations.md)         |
| 6   | Part 13 Wrap-Up + Landing Zone Interview Drill         | [Section-120-Part13-WrapUp-Interview-Drill](./Contents/Part13/Section-120-Part13-WrapUp-Interview-Drill.md)       |

### Part 14 — Security Operations & Incident Response

Amazon Macie, Amazon Detective, AWS Security Lake, automated incident response (EventBridge/Lambda/SSM runbooks), SOC patterns on AWS, and a security-operations interview drill. Also expands on the threat-detection topics introduced in Part 2 §8.

| §   | Section                                                         | File                                                                                                                  |
| --- | --------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| 1   | Amazon Macie — Sensitive Data Discovery                         | [Section-121-Part14-Macie](./Contents/Part14/Section-121-Part14-Macie.md)                                             |
| 2   | Amazon Detective — Security Investigation                       | [Section-122-Part14-Detective](./Contents/Part14/Section-122-Part14-Detective.md)                                     |
| 3   | AWS Security Lake — Centralized Security Data                   | [Section-123-Part14-Security-Lake](./Contents/Part14/Section-123-Part14-Security-Lake.md)                             |
| 4   | Automated Incident Response — EventBridge, Lambda, SSM Runbooks | [Section-124-Part14-Automated-Incident-Response](./Contents/Part14/Section-124-Part14-Automated-Incident-Response.md) |
| 5   | Security Operations Center (SOC) Patterns on AWS                | [Section-125-Part14-SOC-Patterns](./Contents/Part14/Section-125-Part14-SOC-Patterns.md)                               |
| 6   | Part 14 Wrap-Up + Security Operations Interview Drill           | [Section-126-Part14-WrapUp-Interview-Drill](./Contents/Part14/Section-126-Part14-WrapUp-Interview-Drill.md)           |

### Part 15 — Resilience Testing & Continuous DR Validation

AWS Elastic Disaster Recovery (DRS), Resilience Hub, Fault Injection Service (chaos engineering), continuous DR validation and game days, and a resilience interview drill.

| §   | Section                                               | File                                                                                                                              |
| --- | ----------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| 1   | AWS Elastic Disaster Recovery (DRS)                   | [Section-127-Part15-Elastic-Disaster-Recovery](./Contents/Part15/Section-127-Part15-Elastic-Disaster-Recovery.md)                 |
| 2   | AWS Resilience Hub                                    | [Section-128-Part15-Resilience-Hub](./Contents/Part15/Section-128-Part15-Resilience-Hub.md)                                       |
| 3   | AWS Fault Injection Service (FIS) — Chaos Engineering | [Section-129-Part15-FIS-Chaos-Engineering](./Contents/Part15/Section-129-Part15-FIS-Chaos-Engineering.md)                         |
| 4   | Continuous DR Validation & Game Days                  | [Section-130-Part15-Continuous-DR-Validation-GameDays](./Contents/Part15/Section-130-Part15-Continuous-DR-Validation-GameDays.md) |
| 5   | Part 15 Wrap-Up + Resilience Interview Drill          | [Section-131-Part15-WrapUp-Interview-Drill](./Contents/Part15/Section-131-Part15-WrapUp-Interview-Drill.md)                       |

---

_Last updated: July 23, 2026_
