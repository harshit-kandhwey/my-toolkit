# Part 3 - Section 10 - Part 3 Wrap-Up + Compute Interview Drill

AWS Zero-to-Enterprise Knowledge Base - Part 3: Compute (Final Section)

---

## 1. Part 3 Consolidated Knowledge Map

Compute (Part 3) breaks down into:

- S1 EC2 Fundamentals: Instances, Nitro, stop/terminate
- S2 AMIs/Instance Types: Golden images, families
- S3 Purchasing Options: On-Demand, RI, Savings Plans, Spot
- S4 Storage/Networking/Security: EBS, ENIs, SGs, instance profiles
- S5 Auto Scaling Groups: Self-healing, elasticity via Launch Templates
- S6 ELB: ALB/NLB/GWLB, health checks, the ASG-ELB handoff
- S7 Lambda: FaaS, cold starts, concurrency
- S8 Containers: ECS/EKS/Fargate, orchestration
- S9 Beanstalk/Batch/Lightsail: Abstraction layers over S1-8

**Throughline:** S1-4 build the raw EC2 primitive fully. S5-6 make it elastic and reachable (ASG's reconciliation loop + ELB's detection/routing, working together). S7-8 offer progressively more abstracted alternatives (FaaS, then container orchestration) for workloads not needing EC2's full control. S9 shows even AWS's "higher-level" compute products are built from S1-8's primitives, not new foundations.

---

## 2. Consolidated Key-Takeaways Checklist

- Explain EC2 as IaaS, the Nitro System's role, and stop vs terminate (including why instance store can't be stopped).
- Decode an instance type name and map it to the correct family for a given bottleneck.
- Explain the burstable T-family credit system and when it's the wrong choice.
- Walk through the purchasing-options decision tree (On-Demand -> Spot -> Savings Plans -> Zonal RI/ODCR) and the commitment/discount trade-off.
- Explain why Compute Savings Plans and EC2 Instance Savings Plans differ, and why AWS generally favors Savings Plans over RIs.
- Distinguish EBS from instance store, and explain ENIs as the detachable unit of network identity.
- State the exact relationship between min/max/desired capacity in an ASG, and that policies adjust desired capacity rather than launching instances directly.
- Explain the ELB-ASG health-check handoff (ELB detects, ASG acts) precisely.
- Distinguish ALB/NLB/GWLB by layer and use case.
- Explain Lambda's cold start/warm start, the memory-scales-CPU relationship, and reserved vs Provisioned Concurrency.
- Distinguish ECS from EKS, and explain what Fargate actually removes from that equation.
- Recognize Beanstalk, Batch, and Lightsail as abstraction layers over S1-8's primitives, not new compute types.

---

## 3. Progressive Hands-On Labs - Part 3

### Lab 1 (Beginner) - Launch and Inspect an Instance

1. Launch a small EC2 instance from an AWS-provided Amazon Linux AMI, in a VPC with a public subnet.
2. Connect via Session Manager or SSH; query IMDS to see instance metadata firsthand (with IMDSv2 in mind, Part 2 Section 3.8).
3. Stop the instance, note its public IP, restart it, confirm the public IP changed (Section 1 Section 7); release any Elastic IP for cost hygiene.

### Lab 2 (Beginner) - Build a Golden Image

1. On the Lab 1 instance, install a simple web server and a basic health-check page.
2. Create a custom AMI from this configured instance (Section 2 Section 4).
3. Launch a second instance from the new AMI and confirm it boots already configured.

### Lab 3 (Intermediate) - Launch Template + Auto Scaling Group + ALB

1. Create a Launch Template referencing your golden AMI, with a scoped security group and least-privilege instance profile.
2. Create an ALB with a target group using ELB health checks against your web server's health page.
3. Create an ASG using the Launch Template, spanning at least two AZs, attached to the target group, target-tracking on average CPU.
4. Terminate one instance manually and observe the ASG replace it and the ALB route around it appropriately.

Success: the exact self-healing, load-balanced architecture Sections 1-6 described conceptually, built end to end.

### Lab 4 (Intermediate) - A Minimal Lambda Function

1. Write a Lambda function reading an S3 object and writing a summary to DynamoDB (or logging to CloudWatch).
2. Scope its execution role tightly to just that bucket/table.
3. Trigger via S3 event notification; check CloudWatch Logs for cold-start vs warm-start timing on a second invocation.

### Lab 5 (Capstone) - Compute Decision Document

1. For three hypothetical workloads (spiky public API, nightly batch job, small internal admin tool), write a one-paragraph justification for which compute option and purchasing option you'd choose, referencing this Part's decision criteria.
2. Extend the account-health document with a "compute posture" section: what's running, its purchasing model, whether Savings Plans/Spot are used appropriately.

---

## 4. Cross-Section Interview Drill

**How do a Launch Template, an ASG, and an ALB work together?**
The Launch Template defines exactly what to launch (AMI, instance type, security groups, instance profile). The ASG uses it to maintain a desired instance count across AZs, replacing failures and scaling by policy. The ALB distributes traffic only to instances passing its application-level health checks - it's specifically the ALB's health check result, not just EC2's own status check, that the ASG relies on to know when to replace an instance.

**Why would a workload fit Fargate better than Lambda, or vice versa?**
A workload exceeding 15 minutes, needing significant persistent in-memory state, or holding long-lived connections is a poor Lambda fit but works fine on Fargate (no execution-time ceiling, containers can hold state for their lifetime). A highly spiky, infrequent, short-duration workload often fits Lambda better, since Fargate bills for provisioned task time even during intermittent traffic while Lambda charges nothing with no invocation.

**An ASG keeps launching instances that immediately fail health checks and get replaced in a loop - diagnostic process?**
Check whether it's an ELB health check or just default EC2 status check - if ELB, confirm the target group's health check path and that the app actually responds correctly once booted. Check the health check grace period - if bootstrap genuinely takes longer, the ASG marks it unhealthy prematurely. Verify the Launch Template's instance profile grants whatever permissions the bootstrap needs (e.g., pulling from Secrets Manager/S3). Check CloudWatch Logs for the actual error rather than guessing - grace period, health check config, IAM permissions, or a genuine app bug could all produce this symptom.

**Design compute architecture for a SaaS product: public web API (unpredictable traffic), internal admin dashboard (employees only), nightly data-aggregation job - justify every choice.**
Public API: Lambda behind API Gateway if requests are short/stateless (zero-idle-cost handles spikes); if more substantial/needs persistent connections, ECS on Fargate behind an ALB, mixing Fargate Spot for cost-sensitive portions with standard Fargate for a guaranteed baseline. Admin dashboard: low, predictable, business-hours traffic - Elastic Beanstalk for fast deployment on a small On-Demand/Savings-Plan-covered EC2 footprint, since Lambda's per-request model or Fargate's premium isn't justified for low-volume internal use. Nightly aggregation: canonical AWS Batch use case - Spot-based compute environment (fault-tolerant, time-flexible), scaling to zero between runs. Across all three: same IAM least-privilege, security-group scoping, encryption discipline from Part 2; revisit purchasing choices in 3-6 months using real Cost Explorer data.

---

## 5. Related Technologies (forward links, consolidated)

- VPC, subnets, security groups, NACLs, Route 53, ACM, public/private architecture -> Part 4
- EBS volume types, snapshots, S3, EFS -> Part 5
- RDS/Aurora/DynamoDB as Lambda/container backends -> Part 6
- SQS, Step Functions, EventBridge for event-driven and batch patterns -> Part 7
- CloudWatch metrics/alarms/logs underlying all scaling and health checks -> Part 8
- CI/CD pipelines building/deploying to EC2, Lambda, and containers; deployment strategies -> Part 9
- Well-Architected Performance Efficiency and Cost Optimization pillars -> Part 10

---

## 6. Recommended Certification Alignment

- AWS Certified SysOps Administrator - Associate and AWS Certified Solutions Architect - Associate both draw heavily on this Part - EC2, Auto Scaling, ELB, and Lambda are consistently heavily-weighted.
- AWS Certified Developer - Associate emphasizes Lambda, containers, and deployment patterns from Sections 7-9.

---

## Part 3 - Final Consolidated Key Takeaways

1. EC2 is the IaaS foundation everything else in this Part either builds on or abstracts away - instances, AMIs, purchasing options are the primitives; storage/networking/security is how an instance connects to everything else.
2. Auto Scaling and Elastic Load Balancing work as a coordinated pair, not independently - ASG's reconciliation loop and ELB's application-aware health checks together deliver genuine self-healing, elastic, highly-available compute.
3. Lambda and containers represent progressively more abstraction along the IaaS-to-FaaS spectrum - Lambda removes server management entirely for event-driven bounded-duration code; ECS/EKS (optionally on Fargate) orchestrate containers for workloads needing more control, state, or duration.
4. Purchasing decisions apply across the entire spectrum, not just EC2 - Savings Plans cover Fargate and Lambda too; the commitment/discount/interruptibility trade-off is a lens applicable to nearly every compute decision in this Part.
5. Elastic Beanstalk, Batch, and Lightsail are automation layers, not new foundations - recognizing what's actually running underneath any AWS compute product is the difference between surface familiarity and real architectural understanding.

---

## Part 3 Complete

All 10 sections of Compute are done. Next: Part 4 - Networking & Content Delivery (VPC internals, subnets, route tables, IGW/NAT, security groups vs NACLs, Route 53, CloudFront, API Gateway, Direct Connect, VPN, Transit Gateway, PrivateLink).
