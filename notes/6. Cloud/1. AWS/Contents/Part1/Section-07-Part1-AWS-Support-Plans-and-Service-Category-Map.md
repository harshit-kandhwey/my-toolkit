# Part 1 · Section 7 — AWS Support Plans & Service Category Map

> AWS Zero-to-Enterprise Knowledge Base · Part 1: Foundations & Global Infrastructure

---

## 1. Definition

**Plain-language:** AWS Support Plans are subscription tiers for different levels of help — from self-service docs up to a dedicated team responding in minutes with proactive reviews. The Service Category Map is how AWS's 200+ services are grouped into logical families.

**Precise:** **AWS Support** is a separate, optional, per-account/Organization subscription — distinct from resource costs (Section 6) — determining access to technical assistance, response-time guarantees, and proactive guidance tooling. **Service categories** are AWS's top-level taxonomy (visible in the Console services menu) organizing every service by primary function.

---

## 2. Why Support Plans Exist

- Consumption-based infrastructure means _you_ operate the system — AWS doesn't auto-detect your app breaking; docs alone aren't enough for production-critical issues.
- Tiered support lets customers choose their own risk/cost trade-off — a hobby project and a bank's trading platform have very different needs.
- Paid tiers largely scale with **monthly AWS spend** (percentage-based fee), tracking support cost to operational scale and stakes.

---

## 3. The AWS Support Plans

| Plan                   | Cost                      | Who it's for                                  | Key characteristics                                                                                             |
| ---------------------- | ------------------------- | --------------------------------------------- | --------------------------------------------------------------------------------------------------------------- |
| **Basic**              | Free, included always     | Everyone by default                           | Docs, whitepapers, re:Post, limited Trusted Advisor checks; no technical support cases beyond account/billing   |
| **Developer**          | Low flat monthly fee      | Individual devs, early experimentation        | Business-hours **email-only** support; general architectural guidance; response in many hours                   |
| **Business**           | % of usage (with minimum) | Production workloads, most companies          | **24/7 phone/chat/email**; faster response (<1hr for urgent); full Trusted Advisor; Support API access          |
| **Enterprise On-Ramp** | % of usage (higher min)   | Mid-sized orgs growing into mission-critical  | Everything in Business + TAM-adjacent guidance, faster urgent-tier response, some proactive guidance            |
| **Enterprise**         | % of usage (highest min)  | Large enterprises, mission-critical workloads | Everything above + dedicated **TAM**, fastest (minutes) response, proactive reviews, concierge support/training |

> ⚠️ Exact SLAs/percentages/minimums change — verify on AWS's official Support comparison page; treat relative ordering/qualitative traits as durable.

---

## 4. Technical Account Manager (TAM)

- Named, ongoing AWS contact (Enterprise tier; lighter form at Enterprise On-Ramp) who understands _your_ environment over time.
- Does: proactive architecture guidance, operational reviews, major-event planning (launches), incident escalation point.
- Frequently referenced in enterprise architecture/incident-response discussions.

---

## 5. Support Case Severity Levels

- **General guidance / Low** — non-urgent questions.
- **System impaired** — feature/resource not working as expected, system otherwise functioning.
- **Production system impaired** — production workload significantly degraded.
- **Production system down** — production completely unavailable.
- **Business-critical system down** — most severe; typically Business tier and above; mission-critical issue with significant business impact.

> 🎯 Response SLA depends on **both plan tier and honestly-assigned severity** — a Business customer's "business-critical down" case gets materially faster response than the same customer's "general guidance" case.

---

## 6. AWS Trusted Advisor

- Automated tool inspecting your account against best practices across **five categories**: Cost Optimization, Performance, Security, Fault Tolerance, Service Limits.
- **Availability by plan:** Basic/Developer → limited core checks (mainly security, e.g., open SGs, root MFA). Business/Enterprise On-Ramp/Enterprise → full checks across all five categories.
- Shows support tier isn't just faster reactive help — it's more proactive tooling to prevent breakage.

---

## 7. AWS re:Post

- Community-driven Q&A platform (successor to AWS Forums); AWS employees, designated experts, and customers answer questions publicly.
- Available to **every account regardless of plan**, including Basic.
- A sensible first stop before escalating to a paid support case.

---

## 8. Choosing a Support Plan — Decision Framework

1. **Is this production-critical?** If yes, at minimum Developer; Business for true production.
2. **How fast/what channel do you need?** Email-only/business-hours (Developer) vs 24/7 phone/chat (Business+).
3. **How large/complex is your footprint?** Small app → Business often enough; large multi-account estate → TAM value (Enterprise/On-Ramp).
4. **Budget relative to monthly spend?** Paid tiers scale as a predictable percentage.

---

## 9. AWS Service Category Map

| Category                        | Covers                                 | Example services                                                                                    | Course Part            |
| ------------------------------- | -------------------------------------- | --------------------------------------------------------------------------------------------------- | ---------------------- |
| Compute                         | Running code/servers/containers        | EC2, Lambda, ECS, EKS, Fargate, Beanstalk, Batch, Lightsail                                         | Part 3                 |
| Storage                         | Files, objects, blocks                 | S3, EBS, EFS, FSx, Storage Gateway                                                                  | Part 5                 |
| Database                        | Managed data stores                    | RDS, Aurora, DynamoDB, ElastiCache, Redshift, DocumentDB, Neptune                                   | Part 6                 |
| Networking & Content Delivery   | Connectivity, content distribution     | VPC, Route 53, CloudFront, API Gateway, Direct Connect, Transit Gateway                             | Part 4                 |
| Security, Identity & Compliance | Access control, protection, governance | IAM, IAM Identity Center, KMS, Secrets Manager, GuardDuty, Security Hub, WAF, Shield, Organizations | Part 2                 |
| Management & Governance         | Operating/monitoring the platform      | CloudWatch, CloudTrail, Config, Systems Manager, Trusted Advisor, Health Dashboard                  | Part 8                 |
| Developer Tools                 | Building, testing, deploying           | CodePipeline, CodeBuild, CodeDeploy                                                                 | Part 9                 |
| Application Integration         | Connecting distributed components      | SQS, SNS, EventBridge, Step Functions                                                               | Part 7                 |
| Analytics & Streaming           | Processing/analyzing data at scale     | Kinesis, MSK, Redshift                                                                              | Part 7                 |
| Machine Learning                | AI/ML                                  | SageMaker + purpose-built AI services                                                               | Part 10 (related tech) |
| Migration & Transfer            | Moving data/workloads into AWS         | DMS, Application Migration Service, Snow family                                                     | Part 10                |

> 🔑 This table is this course's syllabus. When meeting an unfamiliar service: "which category does it belong to, and what's it probably for?" gives a strong starting guess.

---

## 10. Production & Enterprise Usage

- **Support tier is a leadership risk decision**, standardized org-wide via Organizations, not chosen ad hoc per team.
- **TAMs as architectural resource** — looped into migrations, Region expansions, launches for proactive review.
- **Severity discipline** trained into incident-response runbooks (Part 8) — misjudging severity wastes urgent capacity or delays appropriate help.
- **Category map as internal training structure** — mirrors Console, docs, and certification organization.

---

## 11. Common Misconceptions

- "Technical skill means I don't need paid support." → Doesn't grant faster response times or resource-limit increases.
- "Trusted Advisor is the same for everyone." → False — checks gated by support tier.
- "re:Post is only for beginners." → False — includes AWS-designated experts, useful at any level.
- "Mark everything critical for faster response." → Severity should reflect honest impact; gaming it undermines support-team and internal credibility.

---

## 12. Interview Questions (with model answers)

**🟢 What are the Support plan tiers, in order?** Basic (free, docs/forums, no support cases) → Developer (low-cost, business-hours email) → Business (24/7 phone/chat/email, full Trusted Advisor) → Enterprise On-Ramp → Enterprise (dedicated TAM, fastest response).

**🟡 Severity vs plan tier — how do they interact?** Plan tier sets the _ceiling_ of accessible service (e.g., only Business+ can file "business-critical down"). Severity is the case-specific honest impact assessment. Actual SLA = function of both: plan sets the ceiling, severity sets the commitment within it.

**🟡 Why upgrade Developer → Business?** Once real users depend on the system, business-hours-only support is a real risk (e.g., 2am weekend outage gets no faster response). Business adds 24/7 phone/chat, faster production-down response, and full 5-category Trusted Advisor for proactive prevention, not just reactive help.

**🔴 Business vs Enterprise for a 200-person org?** Look at scale/criticality, not headcount. Large complex multi-account estate with revenue-critical minute-matters workloads → Enterprise's TAM and fastest response usually worth it (proactive prevention). Simpler/less minute-critical estate → Enterprise On-Ramp is often the better middle ground. Factor in existing internal SRE/ops maturity, which reduces marginal AWS-side response value.

**🔴 How does the service category map influence a design review?** Use category as a fast heuristic before deep-diving docs: Application Integration → expect decoupling/messaging problem, compare against SQS/SNS/EventBridge already in use; Analytics & Streaming → expect volume/real-time data processing, compare against Kinesis/MSK. Category tells you the _class_ of problem, quickly filtering whether a new service/category is even needed.

---

## 🔑 Key Takeaways

1. Support plans are separate from resource costs — Basic → Developer → Business → Enterprise On-Ramp → Enterprise, increasing response speed, channel, and proactive tooling.
2. Response-time commitments depend on both plan tier and honestly-assigned severity — two independent, interacting dimensions.
3. Trusted Advisor's check coverage is gated by support plan — full 5-category coverage needs Business+.
4. AWS re:Post is free and plan-independent — a sensible first stop before escalating.
5. The service category map is this course's syllabus — every service maps to a category, every category to a later Part; recognizing category is a genuinely useful design-review move.

## 🌐 Related Concepts (forward links)

- Trusted Advisor operational depth, AWS Health Dashboard → Part 8
- Incident response / severity-driven runbooks → Part 8
- Every category in the map → its corresponding Part (3–10)
