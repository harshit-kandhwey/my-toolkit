# Part 1 · Section 1 — What is AWS & Cloud Computing Fundamentals

> AWS Zero-to-Enterprise Knowledge Base · Part 1: Foundations & Global Infrastructure

---

## 1. Definition

**Plain-language:** Amazon Web Services (AWS) is a subsidiary of Amazon that rents out computing resources — servers, storage, databases, networking, and hundreds of higher-level services — over the internet, on demand, charging only for what you use. Instead of buying physical machines, you request them via a web console or an API, use them for minutes or years, and release them.

**Precise:** AWS is a **public cloud provider** offering **on-demand delivery of IT resources and services over the internet with pay-as-you-go pricing**. *On-demand* = provisioned programmatically in seconds without procurement. *Pay-as-you-go* = billing metered by actual consumption (compute-seconds, GB-months, requests).

> 💡 **Mental model — utility computing:** AWS is like electricity from a utility. You don't build a power plant to run a lamp; you plug in, draw the wattage you need, and pay per kWh. AWS applies this utility model to computing.

---

## 2. Why It Exists / The Problem It Solves

### 2.1 What existed before: on-premises ("on-prem")

To run an application before cloud, a company had to:
1. Forecast demand months ahead.
2. Buy physical servers for the **peak** forecast (large capital purchase).
3. Wait weeks/months for procurement, shipping, installation.
4. House them (power, cooling, fire suppression, physical security).
5. Staff a team to rack, cable, patch, secure, replace hardware.
6. Over-provision deliberately, since running out meant outages and adding capacity took months.

### 2.2 Problems → cloud solutions

| On-prem problem | Why it hurt | How cloud solves it |
|-----------------|-------------|--------------------|
| Huge upfront capital (CapEx) | Paid for peak before earning revenue | Convert to OpEx — pay monthly for usage |
| Capacity guessing | Too high = waste; too low = outages | Elasticity — auto scale to real demand |
| Slow procurement | Weeks–months killed agility | Provision in seconds via API |
| Undifferentiated heavy lifting | Time on racking/cooling, not product | AWS operates physical layer |
| Hard to go global | Needed a data center per continent | Deploy to Regions worldwide in minutes |
| Idle DR capacity | Standby site fully paid but unused | Pay for standby only when spun up |

> 🔑 **CapEx vs OpEx:** CapEx = one-time purchase of an owned asset (buy 100 servers). OpEx = ongoing metered cost for a consumed service (rent server-time by the second). AWS's core pitch: **"trade capital expense for variable expense."**

### 2.3 The Six Advantages of Cloud Computing (memorize verbatim)

1. **Trade capital expense for variable expense** — pay only when you consume.
2. **Benefit from massive economies of scale** — aggregated demand → lower per-unit cost.
3. **Stop guessing capacity** — scale to actual demand instead of forecasting.
4. **Increase speed and agility** — new resources in minutes, not weeks; cheap experimentation.
5. **Stop spending money running/maintaining data centers** — focus on customers, not heavy lifting.
6. **Go global in minutes** — deploy across Regions worldwide for low latency at minimal cost.

---

## 3. History & Evolution

- **Early 2000s:** Amazon.com scaling led to an internal mandate (~2002) that all teams expose functionality via **well-documented, network-accessible APIs**, decoupling teams. This "everything is a service" discipline is AWS's cultural DNA.
- **Insight:** Amazon was very good at running reliable, scalable infrastructure and realized other companies would pay for that capability.
- **2004:** Amazon SQS (Simple Queue Service) — an early public building block.
- **2006 (public platform launch):**
  - **Amazon S3** (object storage) — March 2006.
  - **Amazon EC2** (rentable virtual servers) — August 2006 (beta).
  - Storage + compute on demand = the primal atoms of the cloud industry.
- **First Region:** US East (N. Virginia), `us-east-1` — oldest, largest, default; new services usually launch here first.
- **Expansion:** from a handful of services to **200+** across compute, storage, DB, analytics, ML, IoT, with continuous Region growth.
- **Leadership & significance:** led for years by Andy Jassy (later Amazon CEO); AWS became the cloud-infrastructure market leader and a major Amazon profit engine — a strategic core business, not a side project.

> ⚠️ **Accuracy flag:** S3 (Mar 2006) and EC2 (Aug 2006) are well-established; finer-grained early-history dates are often misquoted — verify against AWS's official history if a precise date matters.

---

## 4. Core Terminology

- **Cloud computing** — on-demand delivery of IT resources over the internet, pay-as-you-go. Pillars: *on-demand*, *internet*, *metered*.
- **Provisioning** — creating/allocating a resource; programmatic and near-instant in cloud.
- **Elasticity** — automatic, **bidirectional** capacity adjustment to match demand in near-real-time (scales *down* too).
- **Scalability** — handling more load by adding resources. **Vertical** = bigger machine; **Horizontal** = more machines. Cloud favors horizontal.
- **Agility** — speed to build, change, experiment.
- **High Availability (HA)** — keep running despite failures (e.g., 99.99% uptime) via redundancy across failure domains.
- **Fault tolerance** — continue operating *correctly* even when a component fails, often invisibly.
- **Latency** — travel-time delay for data; reduced by placing resources near users.
- **Resiliency / Durability** — resiliency = recover from failure; durability = safety of stored data from loss (e.g., S3 "eleven nines").
- **Multi-tenancy** — multiple isolated customers share physical hardware; enables economies of scale.
- **Region / AZ / Edge Location** — physical building blocks (full detail in Section 2).

---

## 5. Cloud Service Models — IaaS / PaaS / FaaS / SaaS

Full stack (bottom → top): data-center facility → networking → storage → servers → virtualization → OS → middleware → runtime → data → application.

| Model | Provider manages | You manage | AWS example | Analogy |
|-------|-----------------|------------|-------------|---------|
| On-prem | Nothing | Everything | Own data center | Own the whole house |
| **IaaS** | HW, virtualization, networking, facility | OS, runtime, app, data | **EC2** | Empty apartment; bring furniture |
| **PaaS** | Up to runtime/OS | App + data | **Elastic Beanstalk, RDS** | Furnished apartment |
| **FaaS** (serverless) | All but your function | Function code | **Lambda** | Hotel room by the hour |
| **SaaS** | Entire stack incl. app | Usage/config only | **WorkMail, Chime** | Stay at a hotel |

> 🎯 **Interview tip:** Name the responsibility boundary: "With EC2 (IaaS) I patch the guest OS; with Lambda (FaaS) AWS patches the runtime and I only own my function code." Moving up the stack = less burden, less control.

---

## 6. Cloud Deployment Models

- **Public cloud** — provider-owned, shared across many customers over the internet (AWS). Max agility/scale; own no hardware.
- **Private cloud** — cloud-style infra dedicated to one organization; for strict compliance/residency/legacy; less elasticity.
- **Hybrid cloud** — deliberate public + private/on-prem combination, connected (AWS Outposts, Direct Connect, Storage Gateway).
- **Multi-cloud** — two or more *public* providers (AWS + Azure) to avoid lock-in / meet regulation / best-of-breed; adds complexity.

> 💡 Hybrid = public + private/on-prem. Multi-cloud = 2+ public clouds. Don't confuse them.

---

## 7. Shape of the Platform — Service Categories

- **Compute** — EC2, Lambda, ECS/EKS (Part 3)
- **Storage** — S3, EBS, EFS (Part 5)
- **Databases** — RDS, DynamoDB, Redshift (Part 6)
- **Networking & Content Delivery** — VPC, Route 53, CloudFront (Part 4)
- **Security, Identity & Compliance** — IAM, KMS, GuardDuty (Part 2)
- **Management & Observability** — CloudWatch, CloudTrail, Systems Manager (Part 8)
- **Developer Tools / IaC** — CodePipeline, CloudFormation, CDK (Part 9)
- **App Integration / Analytics / ML** — SQS, Kinesis, SageMaker (Part 7+)

> 🔑 Every AWS service is a managed abstraction over the same primitives — compute, storage, networking in Regions and AZs. Master the primitives and higher-level services become "the same ideas with more convenience."

---

## 8. Production & Enterprise Context

- **Startups:** cloud-native from day one; six advantages map to survival (low capital, scale on success, cheap experimentation).
- **Enterprises:** arrive via migration; often hybrid for years; focus on governance, multi-team cost control, compliance (finance/healthcare/government), and DR.
- **Adoption:** e-commerce/streaming (elastic demand), finance (security/compliance), healthcare (durability/compliance), gaming (global low latency), public sector (sovereign Regions).

---

## 9. Common Misconceptions

- **"Cloud is just someone else's computer."** Base is true but misses the value: managed services, elasticity, automation, global reach.
- **"Cloud is always cheaper."** False blanket claim — cheaper for variable/spiky workloads; steady fully-utilized loads can be cheaper on-prem.
- **"Serverless means no servers."** False — servers exist; you just don't provision/manage them or pay for idle.
- **"AWS handles all my security."** False — security is **shared** (see Section 3).

---

## 10. Interview Questions (with model answers)

**🟢 What is cloud computing?**
On-demand delivery of IT resources over the internet with pay-as-you-go pricing; provision programmatically in seconds, pay for consumption. *Probes:* on-demand + internet + metered.

**🟢 Difference between IaaS, PaaS, SaaS?**
Differ by how much of the stack the provider manages: IaaS (EC2) = infra, you manage OS+; PaaS (Beanstalk) = platform, you bring code+data; SaaS = finished app, you manage usage/config. Up the stack trades control for reduced burden. *Probes:* responsibility boundary + examples.

**🟡 Why move from on-prem to AWS? Trade-offs?**
Pull: CapEx→OpEx, elasticity, faster provisioning, offload heavy lifting, go global. Trade-offs: possibly costlier for steady loads, learning curve, less low-level control, need to re-architect for resilience. Workload-dependent. *Probes:* balanced judgment.

**🟡 Elasticity vs scalability?**
Scalability = handle more load by adding resources (vertical/horizontal). Elasticity = automatic, bidirectional real-time adjustment incl. scaling down for cost. All elastic systems scale; not all scalable systems are elastic. *Probes:* the "scales down too" nuance.

**🔴 Client says cloud is less secure than their data center — respond.**
Reframe via Shared Responsibility Model: AWS secures underlying infra to standards few can match; customer secures what they put in the cloud (IAM, encryption, network, data). Most breaches = customer misconfiguration. Real question: "are we configuring our side correctly?" — AWS provides IAM/KMS/GuardDuty/Config to do so. *Probes:* shared security + stakeholder handling.

---

## 🔑 Key Takeaways

1. AWS = on-demand IT over the internet, pay-as-you-go (utility computing).
2. Solves on-prem pains: upfront capital, capacity guessing, slow procurement, heavy lifting, hard globalization — memorize the six advantages.
3. Service models = how much provider manages; deployment models = where it lives / who uses it.
4. History (API discipline → S3 & EC2 in 2006 → 200+ services) explains "everything is a service" and AWS as Amazon's strategic core.
5. Cloud is not automatically cheaper or more secure — both are architecture/config dependent.

## 🌐 Related Concepts (forward links)

- Regions & AZs → Section 2
- Shared Responsibility Model → Section 3
- Well-Architected Framework → Part 10
