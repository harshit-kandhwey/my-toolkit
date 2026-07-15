# Part 1 · Section 3 — The Shared Responsibility Model

> AWS Zero-to-Enterprise Knowledge Base · Part 1: Foundations & Global Infrastructure

---

## 1. Definition

**Plain-language:** Security in the cloud is a partnership. AWS secures the underlying infrastructure; you secure everything you put on top. Both must do their part.

**Precise:** AWS's framework dividing security/compliance obligations:

> **AWS = security *OF* the cloud** (hardware, data centers, host OS/hypervisor, global network).
> **Customer = security *IN* the cloud** (data, IAM/access, guest OS, app code, network/firewall config).

> 💡 **Mental model — apartment building:** AWS = landlord (structure, foundation, main-entrance locks, electrical). You = tenant (who gets a key to your unit, whether you lock your door, what's inside). Break-in through your unlocked door = your fault; foundation collapse = landlord's.

---

## 2. Why It Exists

- On-prem: one org owned the whole stack — responsibility unambiguous.
- Cloud: stack is split; without a clear boundary, both sides may assume the other handles a control → gap.
- The model assigns every layer to a responsible party. AWS secures infrastructure at massive scale; customers keep control (and accountability) of data and access.
- Most publicized "AWS breaches" are customer-side misconfigurations, not AWS being hacked.

> 🔑 Not AWS offloading work — a precise contract. AWS can only secure what it controls; you must secure what you control (AWS can't see your data or set your access policies).

---

## 3. Model Visualized

```
┌──────────────────────────────────────────────┐
│ CUSTOMER — security *IN* the cloud            │
│  • Customer data                              │
│  • Platform, apps, IAM                        │
│  • OS, network & firewall config              │
│  • Client-side & server-side encryption       │
│  • Network traffic protection (in transit)    │
├──────────────────────────────────────────────┤
│ AWS — security *OF* the cloud                 │
│  • Software: compute, storage, DB, networking │
│  • Hardware / Global Infra: Regions, AZs, Edge│
│  • Host OS & virtualization (hypervisor)      │
│  • Physical security of data centers          │
└──────────────────────────────────────────────┘
```
The dividing line **moves by service type** (see §6).

---

## 4. AWS's Responsibilities ("of the cloud")

1. **Physical security** of data centers.
2. **Hardware & global infrastructure** (servers, storage, network gear, Regions/AZs/edge, fiber backbone).
3. **Host OS & virtualization (hypervisor)** — patched/hardened by AWS; you never touch it.
4. **Managed-service software** — for abstracted services (S3, DynamoDB, Lambda), AWS also secures/patches the service software, guest OS, and runtime.

> 💡 Proven via audits/certs (SOC 1/2/3, ISO 27001, PCI DSS, HIPAA, FedRAMP). Download evidence via **AWS Artifact**. You inherit compliance for AWS-controlled layers only.

---

## 5. Customer's Responsibilities ("in the cloud")

1. **Customer data** — always yours, every service, no exceptions.
2. **IAM** — users/roles, least-privilege policies, MFA, credential rotation (Part 2).
3. **OS, network & firewall config** — for EC2-type services: patch guest OS, configure security groups/NACLs.
4. **Application security** — code, dependencies, secrets, auth logic.
5. **Encryption** — client-side and configuring server-side (AWS provides tools; you enable them).
6. **Network traffic protection** — TLS/HTTPS in transit.

> ⚠️ Non-negotiable: **data** and **access controls** are always yours in every service model.

---

## 6. How the Line Shifts by Service Type

### 6.1 IaaS — EC2, EBS, VPC
- Most customer responsibility: guest OS + patching, installed software, app, IAM, security groups, network config, data.
- AWS: hypervisor and below.
- *AWS patches the hypervisor; YOU patch the guest OS.*

### 6.2 Managed — RDS, EMR, ECS-on-EC2
- AWS also manages OS + platform/engine (incl. OS patching).
- Customer: data, IAM, firewall (security groups), some network/engine settings.

### 6.3 Abstracted / serverless — S3, DynamoDB, Lambda, SQS
- AWS manages the whole platform (OS, runtime, scaling, patching).
- Customer: data, IAM/resource policies, client-side encryption, enabling server-side encryption/access controls.
- "Leaky S3 bucket" = 100% customer misconfiguration.

**Responsibility line by service type:**

| Layer | IaaS (EC2) | Managed (RDS) | Abstracted (S3/Lambda) |
|-------|:---------:|:-------------:|:----------------------:|
| Customer data | Customer | Customer | Customer |
| IAM / policies | Customer | Customer | Customer |
| App code | Customer | N/A | Customer (Lambda) |
| Guest OS + patching | Customer | AWS | AWS |
| Platform / engine | Customer | AWS | AWS |
| Firewall / SGs | Customer | Customer | via IAM/policy |
| Encryption enablement | Customer | Customer | Customer |
| Hypervisor | AWS | AWS | AWS |
| Hardware / physical / net infra | AWS | AWS | AWS |

> 🎯 "Who patches the OS?" → *It depends on the service.* EC2 = customer; RDS/Lambda = AWS.

---

## 7. Shared Controls (both parties)

- **Patch management** — AWS: infra/managed layers; customer: guest OS + apps.
- **Configuration management** — AWS: its devices; customer: own OS/DB/apps.
- **Awareness & training** — AWS trains its staff; customer trains its own.

> 💡 Shared ≠ someone else's problem — each party owns its slice of the same category.

---

## 8. Production & Enterprise Usage

- **Compliance inheritance:** rely on AWS certs (AWS Artifact) for infra layers; layer own controls on top.
- **Guardrails at scale:** AWS Config rules (flag public buckets), SCPs (forbid disabling encryption), GuardDuty (threat detection) — automate the customer side.
- **Well-Architected Security pillar** (Part 10) = structured guide to the customer half.

---

## 9. Security Failures Mapped to the Model

| Incident | Responsible | Why |
|----------|-------------|-----|
| Public S3 bucket leak | Customer | Bucket policy/access is customer-side |
| Over-permissive IAM abused | Customer | IAM design is customer-side |
| Unpatched EC2 guest OS | Customer | Guest OS patching is customer-side (IaaS) |
| Leaked access keys on GitHub | Customer | Credential hygiene is customer-side |
| Hypervisor vulnerability | AWS | Virtualization is AWS-side |
| Physical intrusion | AWS | Physical security is AWS-side |
| RDS managed-OS unpatched | AWS | AWS patches managed OS |

> ⚠️ Most headline "cloud breaches" are in the customer column.

---

## 10. Best Practices & Anti-Patterns

**Best practices:** know which layers you own per service; automate enforcement (Config/SCPs/GuardDuty); encrypt at rest & in transit + manage keys (KMS); least privilege + MFA; use AWS Artifact for compliance evidence.

**Anti-patterns:** "AWS handles security so we're covered"; assuming managed = zero responsibility; leaving default-open configs; trusting memory over guardrails at scale.

---

## 11. Common Misconceptions

- "AWS is responsible for all security in the cloud." → False (of vs in).
- "Serverless/managed = security fully handled." → False (data + IAM always yours).
- "Public S3 breach = AWS hacked." → False (customer misconfig).
- "AWS certifications = my app is compliant." → False (only AWS-controlled layers inherited).

---

## 12. Interview Questions (with model answers)

**🟢 What is the Shared Responsibility Model?** Divides duties: AWS = security *of* the cloud (physical, hardware, network, virtualization); customer = security *in* the cloud (data, IAM, guest OS/firewall for EC2, app, encryption). Both must act.

**🟡 Who patches the OS?** Depends on service. IaaS (EC2): customer patches guest OS, AWS the hypervisor. Managed/abstracted (RDS, Lambda, S3): AWS patches OS/runtime. Line shifts toward AWS as service becomes more managed.

**🟡 Public S3 leak — AWS's fault?** No. Bucket access/policy/encryption are customer-side. Infra worked; customer left it open. Fix: Block Public Access, least-privilege policy, Config rules.

**🔴 Operationalize the customer side across hundreds of accounts?** Guardrails, not diligence: SCPs (block disabling encryption/non-approved Regions), Config rules (detect/auto-remediate public buckets/open SGs), GuardDuty (threats), Security Hub (aggregate), IAM Access Analyzer (over-broad access), Well-Architected Security pillar. Convert each responsibility into an automated, auditable control.

**🔴 Compliance inheritance and limits?** Inherit AWS certs (SOC/ISO/PCI via Artifact) for infra layers; must implement/evidence own controls for data, IAM, OS/app config, encryption. "AWS is PCI compliant" ≠ "my app is PCI compliant."

---

## 🔑 Key Takeaways

1. AWS secures the cloud (infrastructure); customer secures what's in it (data, access, config).
2. Line shifts by service type — IaaS puts most on you (incl. guest-OS patching); abstracted puts least, but data + IAM always yours.
3. Data and access controls are your responsibility in every service, no exceptions.
4. Most real breaches are customer-side misconfigurations, not AWS infra failures.
5. Operationalize your half with guardrails (SCPs, Config, GuardDuty); inherit AWS compliance via Artifact for AWS-controlled layers only.

## 🌐 Related Concepts (forward links)

- IAM, KMS, SCPs, GuardDuty, Security Hub → Part 2
- Security groups & NACLs → Part 4
- Well-Architected Security pillar → Part 10
