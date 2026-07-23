# Part 3 · Section 9 — Elastic Beanstalk, Batch & Lightsail

> AWS Zero-to-Enterprise Knowledge Base · Part 3: Compute

---

## 1. Definition

**Plain-language:** Elastic Beanstalk takes your application code and automatically deploys it onto EC2, load balancers, and Auto Scaling behind the scenes. AWS Batch runs large numbers of computational jobs efficiently without you building a job queue system yourself. Lightsail is AWS's simplified, all-in-one, predictable-pricing offering for simple websites/applications.

**Precise:** **Elastic Beanstalk** is a PaaS orchestration layer automatically provisioning/managing underlying **EC2, ELB, and Auto Scaling**. **AWS Batch** is a managed batch computing service provisioning/scaling compute (EC2 or Fargate) for **queued, job-based workloads**. **Lightsail** is a simplified VPS offering bundling compute/storage/networking into flat-rate pricing.

---

## 2. AWS Elastic Beanstalk — PaaS Orchestration

### 2.1 Why It Exists

- The concrete AWS PaaS offering (Part 1 §5) for traditional applications — upload code, Beanstalk auto-provisions/wires an EC2 ASG behind an ELB with sensible defaults.
- Value proposition: everything Beanstalk provisions could be built manually — its value is doing that wiring automatically/consistently, letting developers focus on code, not infrastructure assembly.

### 2.2 Not a New Compute Type

- **Critical understanding:** Beanstalk is an orchestration/automation layer provisioning the exact same EC2/ASG/ELB from Sections 1, 5, 6. Everything from those sections applies underneath.
- You retain access to underlying resources — manual modification outside Beanstalk's mechanism risks configuration drift, now specifically in tension with Beanstalk's own management.

### 2.3 Environments and Deployment

- A Beanstalk **application** has multiple **environments** (production, staging) — mirrors Part 1 §7's environment separation, automated at deployment level.
- **Deployment policies** (all-at-once, rolling, rolling with batch, immutable, blue/green) — different risk/downtime/cost trade-offs, previewing Part 9's deployment strategies in packaged form.

### 2.4 When to Use Beanstalk vs Manual vs Containers

- **Beanstalk:** fast, opinionated EC2-based deployment without manually wiring Sections 1/5/6.
- **Manual EC2/ASG/ELB:** precise, non-standard infrastructure control Beanstalk's opinionated model doesn't expose.
- **ECS/EKS:** genuinely containerized architectures — more purpose-built than Beanstalk's container support.

---

## 3. AWS Batch — Managed Batch Computing

### 3.1 Why It Exists

- Batch processing (simulations, financial modeling, transcoding) is a genuinely different workload shape — needs to run to completion, without interactive/always-available nature.
- Before Batch: building your own job queue, scheduler, dynamic compute-provisioning logic — a non-trivial distributed systems problem organizations solved poorly, repeatedly.

### 3.2 Core Concepts

- **Job** — a unit of work: a containerized app with resource requirements and optional job dependencies.
- **Job Definition** — a template (analogous to a Task Definition, Section 8 §4.2).
- **Job Queue** — where jobs wait, with configurable priority.
- **Compute Environment** — actual compute Batch provisions: EC2 (incl. Spot — batch is a canonical Spot use case, Section 3 §5.3) or Fargate.

### 3.3 What Batch Automates

- **Dynamic compute provisioning tied to queue depth** — scales up when jobs queue, down (to zero) when empty — extends ASG concepts but driven by queue depth, not a CloudWatch metric.
- **Job scheduling/dependency management** — the logic you'd otherwise build yourself.

### 3.4 Batch vs Building on ECS/EKS Directly

- You could build this on ECS/EKS + SQS + custom scaling logic — Batch exists specifically to save you from building that scheduling/queue-management layer.

---

## 4. Amazon Lightsail — Simplified Compute

### 4.1 Why It Exists

- For simple use cases, AWS's full flexibility (instance types, VPC, security groups) is disproportionate complexity.
- Competes directly with simpler VPS providers while staying in the AWS ecosystem — a genuinely different target audience worth recognizing precisely.

### 4.2 What It Bundles

- **Compute + storage + networking, one flat-rate package** — deliberate contrast to EC2's unbundled, consumption-based pricing (Part 1 §6).
- **Simplified networking** — abstracts VPC/subnet/security-group config behind a simpler firewall interface.
- Also offers managed databases, container services, simple load balancers — a parallel simplified mini-ecosystem.

### 4.3 Relationship to Broader AWS

- Can connect to the broader ecosystem (S3, VPC peering) — not fully isolated, but the default experience is deliberately self-contained.
- **Upgrade path:** start on Lightsail for simplicity, migrate to full EC2/VPC as needs grow — Lightsail supports exporting resources for exactly this.

---

## 5. Comparing All Three

| Service           | Problem solved                                                      | Built on                                       |
| ----------------- | ------------------------------------------------------------------- | ---------------------------------------------- |
| Elastic Beanstalk | Automating EC2+ASG+ELB wiring for a deployed app (PaaS convenience) | EC2, Auto Scaling, ELB (Sections 1, 5, 6)      |
| AWS Batch         | Automating job queueing, scheduling, dynamic compute provisioning   | EC2 (incl. Spot) or Fargate (Sections 3, 6, 8) |
| Amazon Lightsail  | Simplifying the entire experience, predictable flat pricing         | EC2 and related services, abstracted           |

> Key idea: none of these are a fundamentally new compute type — all are automation/abstraction layers on top of Sections 1-8's primitives. This is why this section comes after those sections.

---

## 6. Production & Enterprise Usage

- **Elastic Beanstalk** genuinely used in production for rapid deployment of traditional web apps without a dedicated platform team building custom CI/CD-to-EC2 pipelines.
- **AWS Batch is the standard AWS-native choice** for genomics research, financial risk modeling, media transcoding — frequently cited for Spot-integration cost savings on fault-tolerant restartable jobs.
- **Lightsail common for:** agencies/freelancers, small businesses, learning environments, proof-of-concept projects — a legitimate, sizable customer segment.

---

## 7. Security Considerations

- Beanstalk-managed resources need the same security discipline as manual EC2/ASG/ELB — defaults are reasonable starting points, not automatic security.
- Batch job containers carry Section 8's same container security considerations — image scanning, least-privilege job-level roles, secure secrets handling.
- Lightsail's simplified firewall is still a real security boundary — ease of interface doesn't reduce the importance of correct port/source scoping.

---

## 8. Troubleshooting

| Symptom                                                     | Cause                                                           | Fix                                                                               |
| ----------------------------------------------------------- | --------------------------------------------------------------- | --------------------------------------------------------------------------------- |
| Manual change to Beanstalk-managed instance disappears      | Beanstalk's config management overwrote it on next deployment   | Make changes via Beanstalk's config mechanism (.ebextensions, environment config) |
| Batch jobs stay queued longer than expected                 | Compute environment limit reached, or Spot capacity unavailable | Review scaling limits; consider mixed Spot/On-Demand or raise limits              |
| Lightsail instance can't reach a resource in a separate VPC | Lightsail's simplified network isn't auto-peered                | Set up explicit VPC peering                                                       |

---

## 9. Best Practices & Anti-Patterns

**Best practices:** use Beanstalk's configuration mechanism for customization, not manual console changes; use Batch with Spot compute environments for fault-tolerant restartable workloads; choose Lightsail deliberately for genuinely simple use cases with a clear upgrade-path understanding.

**Anti-patterns:** manually modifying Beanstalk-managed infrastructure outside its config system; building custom job-queue logic on raw ECS/EKS when Batch already solves it; forcing a genuinely complex app onto Lightsail well past its fit.

---

## 10. Common Misconceptions

- "Elastic Beanstalk is a separate compute service from EC2." → False — an orchestration layer over standard EC2/ASG/ELB.
- "AWS Batch is just ECS with a different name." → False — purpose-built for job-queue/scheduling automation you'd otherwise build yourself.
- "Lightsail is a toy product." → False — legitimate, widely-used, with a real supported migration path to full AWS.
- "Beanstalk automation means security is automatic too." → False — same responsibilities apply as any EC2/ASG/ELB deployment.

---

## 11. Interview Questions (with model answers)

**Beginner — Is Elastic Beanstalk a different compute type from EC2?** No — an orchestration/automation layer provisioning standard EC2, an ASG, and an ELB based on deployed code. Everything about EC2 types/scaling/load balancing still applies underneath; Beanstalk just automates the wiring.

**Beginner — What problem does AWS Batch solve that EC2/ECS alone doesn't?** You could build it yourself with EC2/ECS + SQS + custom scaling logic — Batch automates job queueing, scheduling, and dynamic compute provisioning tied to queue depth specifically, so you don't build/maintain that scheduling layer. Purpose-built for the batch-job pattern.

**Intermediate — A manual security group change on a Beanstalk-provisioned instance disappeared after deployment — why, and correct approach?** Beanstalk reconciles infrastructure back to its own configuration on deployment/update, overwriting untracked manual changes. Should have used Beanstalk's own configuration mechanism (.ebextensions, environment config) so the change is part of the desired state and survives future deployments.

**Senior — Design a cost-effective architecture for a fault-tolerant genomics pipeline with thousands of varying-resource jobs, no strict deadline?** Canonical AWS Batch use case: Job Definitions per job type's resource needs, submitted to Job Queues with priority as needed, Compute Environment using EC2 Spot (fault-tolerant, no deadline = ideal Spot profile), Batch auto-retries interrupted jobs. Scale to zero when queue empties for no idle cost. Include accelerated computing family instance types for GPU-needing jobs. Batch's scheduling automation + Spot's discount together is what makes this pattern cost-effective vs custom scheduling or steady On-Demand.

**Architect — A Lightsail website has grown into a multi-tier app needing a database, background jobs, and granular network control — migration approach?** Exactly the scenario Lightsail's upgrade path exists for — don't force more complexity into it. Migrate to full EC2 within a properly designed VPC for real network control. Move database to RDS. Background jobs: SQS+Lambda for lightweight event-driven, or ECS/Batch for substantial/batch-oriented work. Use Lightsail's export capability to bring existing data into the new architecture. Treat as a genuine planned migration, not a quick patch.

---

## Key Takeaways

1. None of these three services are new compute primitives — all are automation/abstraction layers on top of EC2, Auto Scaling, ELB, and containers from Sections 1-8.
2. Elastic Beanstalk automates PaaS-style deployment — provisions/wires EC2+ASG+ELB, same underlying resources and security responsibilities as building manually.
3. AWS Batch automates job queueing, scheduling, and compute provisioning for batch workloads — a canonical, high-value pairing with Spot Instances.
4. Lightsail trades full flexibility for predictable, bundled, flat-rate simplicity — legitimate for simple use cases, with a real migration path to full EC2/VPC.
5. Choosing among these is a genuine architectural decision based on workload shape and team needs — not a maturity hierarchy where more manual or more managed is inherently better.

## Related Concepts (forward links)

- Part 3 Wrap-Up and comprehensive Compute interview drill → Part 3, Section 10 (final section)
- Deployment strategies (rolling, blue/green, canary) in full depth → Part 9
- VPC/subnet design underlying Beanstalk and Lightsail networking → Part 4
- SQS as a building block for custom job-queue patterns outside Batch's scope → Part 7
