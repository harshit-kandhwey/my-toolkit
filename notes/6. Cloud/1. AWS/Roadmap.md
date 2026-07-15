# 🗺️ Master Roadmap

| Part    | Title                                                 | What it covers                                                                                                                               |
| ------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Part 1  | AWS Foundations & Global Infrastructure (current)     | What AWS is, cloud models, Regions/AZs/edge, shared responsibility, accounts, access methods, pricing & billing                              |
| Part 2  | Identity, Security & Governance                       | IAM, Identity Center, Organizations, SCPs, KMS, Secrets Manager, GuardDuty, Security Hub, WAF, Shield                                        |
| Part 3  | Compute                                               | EC2, AMIs, instance families, purchasing models, Auto Scaling, ELB, Lambda, ECS, EKS, Fargate, Beanstalk, Batch, Lightsail                   |
| Part 4  | Networking & Content Delivery                         | VPC internals, subnets, route tables, IGW/NAT, SG/NACL, Route 53, CloudFront, API Gateway, Direct Connect, VPN, Transit Gateway, PrivateLink |
| Part 5  | Storage                                               | S3, EBS, EFS, FSx, Storage Gateway, lifecycle, backup                                                                                        |
| Part 6  | Databases                                             | RDS, Aurora, DynamoDB, ElastiCache, Redshift, DocumentDB, Neptune, migration                                                                 |
| Part 7  | Application Integration & Streaming                   | SQS, SNS, EventBridge, Step Functions, Kinesis, MSK                                                                                          |
| Part 8  | Observability & Management                            | CloudWatch, CloudTrail, Config, Systems Manager, Trusted Advisor, Health                                                                     |
| Part 9  | DevOps, CI/CD & IaC on AWS                            | CodePipeline/Build/Deploy, CloudFormation, CDK, SAM                                                                                          |
| Part 10 | Well-Architected, Cost, Migration & Interview Mastery | WAF pillars, DR strategies, migration (6 Rs), FinOps, capstone interview prep                                                                |

## 🧭 Part 1 — Detailed Section Roadmap

- **[Section 1: What is AWS & Cloud Computing Fundamentals](./Section/Section-01-What-is-AWS-and-Cloud-Computing-Fundamentals.md)**
  - On-demand delivery of IT resources over the internet with pay-as-you-go pricing; why cloud exists (CapEx vs OpEx); the six advantages of cloud computing (trade CapEx for OpEx, economies of scale, elasticity, speed, focus on product, global reach)

- **[Section 2: AWS Global Infrastructure](./Section/Section-02-AWS-Global-Infrastructure.md)**
  - Hierarchy of Regions (geographic areas), Availability Zones (isolated data-center clusters), edge locations, Local Zones, Wavelength Zones, Outposts; latency optimization, availability, fault isolation, data residency

- **[Section 3: The Shared Responsibility Model](./Section/Section-03-Shared-Responsibility-Model.md)**
  - AWS security *of* the cloud (hardware, hypervisor, data centers, managed services); customer security *in* the cloud (data, IAM, guest OS, apps, encryption); responsibility line shifts by service type (IaaS, managed, abstracted/serverless)

- **[Section 4: AWS Accounts, Root User & Identity Basics](./Section/Section-04-AWS-Accounts-Root-User-Identity-Basics.md)**
  - AWS accounts as containers, billing boundaries, and security isolation; root user (unrestricted, non-policy-limitable, dangerous — reserved for root-only actions); IAM identities for everyday access; Free Tier structure; account creation and multi-account strategy

- **[Section 5: Ways to Interact with AWS](./Section/Section-05-Ways-to-Interact-with-AWS.md)**
  - AWS Management Console (visual, one-off exploration, incident response); AWS CLI (repeatable scripts, automation, CI/CD); SDKs (programmatic access in any language); CloudShell (zero-install terminal); underlying API (one API for all interfaces); Infrastructure as Code overview

- **[Section 6: AWS Pricing & Cost Fundamentals](./Section/Section-06-AWS-Pricing-and-Cost-Fundamentals.md)**
  - Pricing models (on-demand, reserved instances, spot instances, savings plans); Free Tier structure (always-free, 12-month-free, trial); Budgets, Cost Explorer, Cost Allocation Tags; billing periods and consolidated billing via Organizations

- **[Section 7: AWS Support Plans & Service Category Map](./Section/Section-07-AWS-Support-Plans-and-Service-Category-Map.md)**
  - AWS Support tiers (Basic, Developer, Business, Enterprise); support case routing, response times, best practices; AWS service categories; console navigation and service discovery

- **[Section 8: Part 1 Wrap-Up + Foundations Interview Drill](./Section/Section-08-Part-1-Wrap-Up-and-Foundations-Interview-Drill.md)**
  - Key takeaways, common misconceptions, glossary; interview prep questions and model answers; readiness checkpoint before Part 2
