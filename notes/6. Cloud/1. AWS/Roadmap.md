# 🗺️ Master Roadmap

| Part    | Title                                                 | What it covers                                                                                                                               |
| ------- | ----------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------- |
| Part 1  | AWS Foundations & Global Infrastructure               | What AWS is, cloud models, Regions/AZs/edge, shared responsibility, accounts, access methods, pricing & billing                              |
| Part 2  | Identity, Security & Governance                       | IAM, Identity Center, Organizations, SCPs, KMS, Secrets Manager, GuardDuty, Security Hub, WAF, Shield                                        |
| Part 3  | Compute                                               | EC2, AMIs, instance families, purchasing models, Auto Scaling, ELB, Lambda, ECS, EKS, Fargate, Beanstalk, Batch, Lightsail                   |
| Part 4  | Networking & Content Delivery                         | VPC internals, subnets, route tables, IGW/NAT, SG/NACL, Route 53, CloudFront, API Gateway, Direct Connect, VPN, Transit Gateway, PrivateLink |
| Part 5  | Storage                                               | S3, EBS, EFS, FSx, Storage Gateway, lifecycle, backup                                                                                        |
| Part 6  | Databases                                             | RDS, Aurora, DynamoDB, ElastiCache, Redshift, DocumentDB, Neptune, migration                                                                 |
| Part 7  | Application Integration & Streaming                   | SQS, SNS, EventBridge, Step Functions, Kinesis, MSK                                                                                          |
| Part 8  | Observability & Management                            | CloudWatch, CloudTrail, Config, Systems Manager, Trusted Advisor, Health                                                                     |
| Part 9  | DevOps, CI/CD & IaC on AWS                            | CodePipeline/Build/Deploy, CloudFormation, CDK, SAM                                                                                          |
| Part 10 | Well-Architected, Cost, Migration & Interview Mastery | WAF pillars, DR strategies, migration (6 Rs), FinOps, capstone interview prep                                                                |

## 🧭 Part 1 — AWS Foundations & Global Infrastructure

- **[Section 1: What is AWS & Cloud Computing Fundamentals](./Section/Section-01-Part1-What-is-AWS-and-Cloud-Computing-Fundamentals.md)**
  - On-demand delivery of IT resources over the internet with pay-as-you-go pricing; why cloud exists (CapEx vs OpEx); the six advantages of cloud computing (trade CapEx for OpEx, economies of scale, elasticity, speed, focus on product, global reach)

- **[Section 2: AWS Global Infrastructure](./Section/Section-02-Part1-AWS-Global-Infrastructure.md)**
  - Hierarchy of Regions (geographic areas), Availability Zones (isolated data-center clusters), edge locations, Local Zones, Wavelength Zones, Outposts; latency optimization, availability, fault isolation, data residency

- **[Section 3: The Shared Responsibility Model](./Section/Section-03-Part1-Shared-Responsibility-Model.md)**
  - AWS security _of_ the cloud (hardware, hypervisor, data centers, managed services); customer security _in_ the cloud (data, IAM, guest OS, apps, encryption); responsibility line shifts by service type (IaaS, managed, abstracted/serverless)

- **[Section 4: AWS Accounts, Root User & Identity Basics](./Section/Section-04-Part1-AWS-Accounts-Root-User-Identity-Basics.md)**
  - AWS accounts as containers, billing boundaries, and security isolation; root user (unrestricted, non-policy-limitable, dangerous — reserved for root-only actions); IAM identities for everyday access; Free Tier structure; account creation and multi-account strategy

- **[Section 5: Ways to Interact with AWS](./Section/Section-05-Part1-Ways-to-Interact-with-AWS.md)**
  - AWS Management Console (visual, one-off exploration, incident response); AWS CLI (repeatable scripts, automation, CI/CD); SDKs (programmatic access in any language); CloudShell (zero-install terminal); underlying API (one API for all interfaces); Infrastructure as Code overview

- **[Section 6: AWS Pricing & Cost Fundamentals](./Section/Section-06-Part1-AWS-Pricing-and-Cost-Fundamentals.md)**
  - Pricing models (on-demand, reserved instances, spot instances, savings plans); Free Tier structure (always-free, 12-month-free, trial); Budgets, Cost Explorer, Cost Allocation Tags; billing periods and consolidated billing via Organizations

- **[Section 7: AWS Support Plans & Service Category Map](./Section/Section-07-Part1-AWS-Support-Plans-and-Service-Category-Map.md)**
  - AWS Support tiers (Basic, Developer, Business, Enterprise); support case routing, response times, best practices; AWS service categories; console navigation and service discovery

- **[Section 8: Part 1 Wrap-Up + Foundations Interview Drill](./Section/Section-08-Part1-Wrap-Up-and-Foundations-Interview-Drill.md)**
  - Key takeaways, common misconceptions, glossary; interview prep questions and model answers; readiness checkpoint before Part 2

## 🧭 Part 2 — Identity, Security & Governance

- **[Section 9: IAM Core Concepts — Users, Groups, Roles, Policies](./Section/Section-09-Part2-IAM-Core-Concepts.md)**
  - IAM users (long-lived identities), groups (collections for bulk permissions), roles (temporary identities for humans and services), policies (permission documents), least-privilege principle, MFA

- **[Section 10: IAM Policy Deep Dive — Structure, Evaluation Logic, Policy Types](./Section/Section-10-Part2-IAM-Policy-Evaluation-Logic.md)**
  - JSON policy structure (Effect, Action, Resource, Condition), policy evaluation logic and order, policy types (identity-based, resource-based, session), explicit deny, wildcards and constraints

- **[Section 11: IAM Roles, Trust Policies & Temporary Credentials (STS)](./Section/Section-11-Part2-IAM-Roles-Trust-Policies-STS.md)**
  - AssumeRole mechanism, trust policies, role assumption for humans (federation) and services (service principals), temporary credentials (access key, secret key, session token), credential expiration, STS API actions (`AssumeRole`, `AssumeRoleWithSAML`, `AssumeRoleWithWebIdentity`)

- **[Section 12: IAM Identity Center (SSO) & Federation](./Section/Section-12-Part2-IAM-Identity-Center-SSO-Federation.md)**
  - IAM Identity Center (successor to AWS SSO), centralized human workforce identity management, identity sources (built-in, Managed AD, external IdP), Permission Sets, SAML 2.0 federation with Okta/Azure AD, cross-account access, attribute-based access control (ABAC)

- **[Section 13: AWS Organizations & Service Control Policies (SCPs)](./Section/Section-13-Part2-AWS-Organizations-and-SCPs.md)**
  - AWS Organizations structure (management account, member accounts, OUs), consolidated billing, hierarchical grouping, Service Control Policies (SCPs) as guardrails, account vending, control tower overview, permission ceiling policies

- **[Section 14: Data Protection — KMS & Encryption](./Section/Section-14-Part2-KMS-and-Encryption.md)**
  - KMS (Key Management Service) for managed encryption key management, encryption at rest and in transit, symmetric and asymmetric encryption, envelope encryption (data key + master key), key rotation, FIPS 140-2 HSM backing, compliance (HIPAA, PCI DSS)

- **[Section 15: Secrets Management — Secrets Manager & Parameter Store](./Section/Section-15-Part2-Secrets-Manager-and-Parameter-Store.md)**
  - Secrets Manager for credential rotation and lifecycle management, Parameter Store for configuration and secrets storage, encrypted storage via KMS, IAM access control, automatic rotation with Lambda, database integrations, versioning and staging

- **[Section 16: Threat Detection & Compliance — GuardDuty, Security Hub, Config, Inspector](./Section/Section-16-Part2-GuardDuty-SecurityHub-Config-Inspector.md)**
  - GuardDuty (threat intelligence and anomaly detection from CloudTrail/VPC Flow Logs/DNS), Security Hub (findings aggregation and centralized view), AWS Config (resource compliance and drift detection), Inspector (vulnerability and compliance scanning)

- **[Section 17: Network & Edge Security — WAF, Shield, Network Firewall](./Section/Section-17-Part2-WAF-Shield-Network-Firewall.md)**
  - AWS WAF (Web Application Firewall for HTTP/HTTPS content filtering at layer 7), AWS Shield (DDoS protection), Network Firewall (network-layer protection), protection at CloudFront/ALB/API Gateway, Web ACLs and rule-based blocking, attack mitigation patterns

- **[Section 18: Part 2 Wrap-Up + Security & Governance Interview Drill](./Section/Section-18-Part2-WrapUp-and-Interview-Drill.md)**
  - Key takeaways and consolidated knowledge map, common misconceptions, glossary of terms, interview prep questions and model answers, readiness checkpoint before Part 3 (Compute)
