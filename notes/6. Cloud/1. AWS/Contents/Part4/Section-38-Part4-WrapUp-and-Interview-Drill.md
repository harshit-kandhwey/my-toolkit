# Part 4 - Section 10 - Part 4 Wrap-Up + Networking Interview Drill

AWS Zero-to-Enterprise Knowledge Base - Part 4: Networking & Content Delivery (Final Section)

---

## 1. Part 4 Consolidated Knowledge Map

Networking & Content Delivery (Part 4) breaks down into:

- S1 VPC Fundamentals: Region-scoped, CIDR sizing
- S2 Subnets/Routing/IGW/NAT: Public = IGW route, private = NAT
- S3 Security Groups vs NACLs: Stateful/allow-only vs stateless/allow+deny
- S4 Peering/Transit Gateway/PrivateLink: Non-transitive mesh vs hub; narrow PrivateLink vs full connectivity
- S5 VPN & Direct Connect: Encrypted-over-internet vs dedicated-private-link
- S6 Route 53: DNS plus 7 routing policies
- S7 CloudFront: CDN, edge caching, OAC, WAF placement
- S8 ACM & API Gateway: TLS certs, managed API front door
- S9 VPC Endpoints, Flow Logs & Troubleshooting: Closes the NAT-cost loop, gives empirical tools

Throughline: S1-2 build the network container and internet connectivity. S3 adds firewall layers governing what's allowed through. S4-5 extend connectivity beyond a single VPC - to other VPCs and on-premises. S6-8 add naming, content-delivery, and API layers making the network useful to end users. S9 closes the loop with cost optimization (Endpoints) and empirical troubleshooting tools for everything built in S1-8.

---

## 2. Consolidated Key-Takeaways Checklist

- Explain a VPC's Region scope, CIDR sizing trade-offs, and why the Default VPC is inappropriate for production.
- State precisely what makes a subnet "public" (route table, not a label) and the three conditions for internet reachability.
- Explain why one NAT Gateway per AZ is standard, and the NAT Gateway cost model.
- State the Security Group vs NACL comparison from memory - stateful/allow-only/instance-level vs stateless/allow+deny/subnet-level - and the inbound/outbound asymmetry.
- Explain why VPC Peering doesn't scale (non-transitive, quadratic mesh) and how Transit Gateway solves it.
- Explain PrivateLink's narrower "service, not network" model and when it's the right choice over Peering/Transit Gateway.
- Compare VPN and Direct Connect on setup time, path, encryption, and cost - and explain the VPN-as-failover pattern.
- Name all seven Route 53 routing policies and map each to the requirement it solves.
- Explain Origin Access Control's necessity for CloudFront + S3, and the cache-key/hit-ratio relationship.
- Explain ACM's DNS-vs-email validation trade-off and the CloudFront us-east-1 requirement.
- Distinguish HTTP API from REST API and know which REST-only features (usage plans, API keys, request validation, private APIs) drive that choice.
- Explain Gateway Endpoint vs Interface Endpoint (service scope, mechanism, cost) and what VPC Flow Logs actually capture.
- Walk the full six-layer network troubleshooting checklist from memory.

---

## 3. Progressive Hands-On Labs - Part 4

### Lab 1 (Beginner) - Build a Custom VPC by Hand

1. Create a custom VPC (e.g., 10.0.0.0/16) - no Default VPC.
2. Create one public subnet and one private subnet in a single AZ.
3. Create/attach an Internet Gateway; create a custom route table for the public subnet routing 0.0.0.0/0 to the IGW; associate it.
4. Launch an EC2 instance in the public subnet with a public IP; confirm reachability, then confirm removing the IGW route breaks it - direct proof of the three-condition checklist.

### Lab 2 (Beginner) - Add a Private Subnet and NAT Gateway

1. Launch an EC2 instance in the private subnet (no public IP).
2. Create a NAT Gateway in the public subnet; update the private subnet's route table to send 0.0.0.0/0 to the NAT Gateway.
3. From the private instance (via Session Manager, no bastion needed), confirm outbound internet access works and no inbound connection is possible.

### Lab 3 (Intermediate) - Security Groups vs NACLs, Empirically

1. Add a security group rule on the private instance allowing inbound from the public subnet's CIDR only.
2. Add a custom NACL to the private subnet with an explicit Deny for a specific port, positioned before a broader Allow - confirm the port is blocked despite the security group allowing it.
3. Enable VPC Flow Logs; generate blocked traffic and find the REJECT entry - connecting Section 3's theory to Section 9's empirical confirmation.

### Lab 4 (Intermediate) - Gateway Endpoint Cost Optimization

1. From the private instance, run an S3 CLI command and confirm it works via the NAT Gateway.
2. Add a Gateway Endpoint for S3; update the private subnet's route table.
3. Re-run the S3 command and confirm (via Flow Logs or route inspection) traffic no longer transits the NAT Gateway - a direct, free cost-optimization proof.

### Lab 5 (Capstone) - Full-Stack Networking Decision Document

1. Sketch a three-tier architecture (public ALB, private app tier, private database tier) across two AZs, labeling every Part 4 component: subnets, route tables, IGW, NAT Gateways (one per AZ), chained security groups, a NACL backstop on the database subnet, Route 53 records, CloudFront + ACM if internet-facing.
2. Write a one-paragraph justification for each connectivity choice (VPN vs Direct Connect if hybrid is needed; Gateway vs Interface Endpoints for AWS service access).

---

## 4. Cross-Section Interview Drill

**Trace a request from a browser to a private RDS database behind an ALB and a Lambda function, naming every Part 4 component.**
DNS resolution via Route 53, possibly with a routing policy directing to the nearest/healthiest Region. Request may hit CloudFront first (caching/WAF), then an ALB in a public subnet (reachable because its route table has an IGW route). The ALB's security group allows the inbound request, forwards to Lambda or a private-subnet instance whose security group only allows traffic from the ALB's security group. If reaching RDS, routed via the VPC's local route to the database's private subnet, protected by its own tightly-scoped security group and potentially a NACL backstop denying anything not from the app tier directly.

**Why would a request to the same S3 bucket sometimes go through a NAT Gateway and sometimes not?**
Depends on whether a Gateway Endpoint for S3 is configured in the relevant subnet's route table. Without one, S3 traffic routes through NAT like any internet-bound traffic. With one, the route table sends S3 traffic directly to the endpoint, bypassing NAT entirely, for free.

**A CloudFront distribution in front of an ALB throws a certificate error - what to check?**
First, whether the ACM certificate was requested in us-east-1 specifically - required regardless of where the ALB lives, and the most common cause of this symptom. If correct, check whether DNS validation actually completed (CNAME propagated) - a pending-validation certificate isn't usable. Separately verify the ALB has its own correctly-configured certificate in its own Region if TLS is also terminated there - two independent certificates for two independent layers.

**Design the complete Part 4 stack for a global SaaS product: multi-Region latency, hard EU data-residency requirement, hybrid connectivity to a customer's on-prem system via a private API, full observability.**
Each Region gets its own VPC with public subnets (ALB, NAT Gateway per AZ) and private subnets (app, database tiers), connected via chained security groups and a NACL backstop on the database tier. Route 53 uses geolocation routing as the outer layer to hard-route EU traffic only to the EU Region (data residency as a rule), latency-based routing among non-EU Regions for performance, failover routing layered under both for resilience with health checks. CloudFront in front globally for caching/WAF with its ACM cert in us-east-1; each Region's API Gateway custom domain has its own regionally-appropriate cert. For the customer's on-prem connectivity: a private REST API via VPC Endpoint combined with Direct Connect (VPN failover) if high-volume/latency-sensitive, or Site-to-Site VPN alone if lower-volume - avoiding unnecessary public internet exposure. Observability: VPC Flow Logs across every Region's VPCs feeding a centralized logging account; Gateway Endpoints enabled everywhere applicable for S3/DynamoDB cost efficiency.

---

## 5. Related Technologies (forward links, consolidated)

- S3, EBS, EFS as VPC Endpoint / NAT Gateway destinations -> Part 5
- RDS/Aurora as the private-subnet database tier -> Part 6
- SQS/SNS/EventBridge as further service-integration targets for API Gateway -> Part 7
- CloudWatch, CloudTrail, Systems Manager Session Manager, centralized Flow Logs analysis -> Part 8
- Infrastructure as Code for VPC/subnet/route-table provisioning -> Part 9
- Well-Architected Reliability pillar, multi-Region DR patterns -> Part 10

---

## 6. Recommended Certification Alignment

- AWS Certified Advanced Networking - Specialty is almost entirely a formalized test of this Part's content, at greater depth.
- AWS Certified Solutions Architect - Associate/Professional both weight VPC design, routing, and connectivity heavily - this Part is foundational to both.

---

## Part 4 - Final Consolidated Key Takeaways

1. A VPC is a Region-scoped container; subnets are its AZ-scoped, route-table-defined public/private building blocks - public/private is a routing fact, never a label.
2. Security Groups (stateful, allow-only, instance-level) and NACLs (stateless, allow+deny, subnet-level) are complementary, not redundant - the inbound/outbound asymmetry between them is the single most tested interaction in this Part.
3. VPC-to-VPC and VPC-to-on-premises connectivity is a genuine architectural decision tree - Peering for a few stable VPCs, Transit Gateway for many/growing/segmented ones, PrivateLink for service-only access, VPN for fast/encrypted/variable, Direct Connect for dedicated/consistent/unencrypted-by-default.
4. DNS (Route 53), content delivery (CloudFront), and API management (API Gateway/ACM) are the layers that make network connectivity actually useful to end users - each with its own genuinely differentiated capability set.
5. VPC Endpoints and Flow Logs close the loop - Endpoints for cost/security optimization of AWS-service traffic, Flow Logs for the empirical, layer-by-layer troubleshooting discipline this Part depends on.

---

## Part 4 Complete

All 10 sections of Networking & Content Delivery are done. Next: Part 5 - Storage (S3, EBS, EFS, FSx, Storage Gateway, lifecycle management, backup).
