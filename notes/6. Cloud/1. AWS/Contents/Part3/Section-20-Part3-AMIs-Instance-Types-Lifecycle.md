# Part 3 · Section 2 — AMIs, Instance Types & Instance Lifecycle

> AWS Zero-to-Enterprise Knowledge Base · Part 3: Compute

---

## 1. Definition

**Plain-language:** An AMI is a snapshot-like template containing an OS and everything installed on top, ready to launch as one or more identical servers. Instance types are the "sizes and shapes" of virtual server AWS offers.

**Precise:** An **AMI** is a Region-specific, versioned template containing a root volume snapshot (OS + software + config) plus launch permissions and block device mapping, used to launch EC2 instances. An **instance type** defines the virtual hardware spec — vCPU, memory, network performance, and (for some types) local storage.

---

## 2. Why AMIs Exist

- Without templating, every new instance starts from a bare OS install — slow, error-prone, inconsistent.
- AMIs let you capture a known-good state once, launch identical instances repeatedly — enabling horizontal scaling (Auto Scaling, [§5](../Part1/Section-05-Part1-Ways-to-Interact-with-AWS.md)) and IaC consistency.
- **Region-specific, deliberately:** an AMI is tied to its creation Region — you cannot launch from it in another Region without explicitly copying it first.

---

## 3. AMI Sources

| Source                     | Description                                                                               |
| -------------------------- | ----------------------------------------------------------------------------------------- |
| AWS-provided (Quick Start) | Maintained by AWS for common OSes, free, patched regularly                                |
| AWS Marketplace            | Third-party vendor images, often licensed software, usage/subscription pricing            |
| Community AMIs             | Shared publicly, **not vetted by AWS** — same caution as any unverified external software |
| Custom AMIs                | Created by you from a configured instance — the standard production pattern               |

> ⚠️ Launching from an unverified Community AMI is a supply-chain risk — trusting unseen software/configuration.

---

## 4. Creating a Custom AMI — Golden Image Pattern

### 4.1 The Process

1. Configure an instance exactly as desired — install software, patch, harden, strip temporary/sensitive data (SSH host keys, shell history, temp credentials).
2. Create an AMI (`create-image`) — AWS creates EBS snapshots of attached volumes and registers the AMI.
3. Launch any number of identical instances from the resulting AMI.

### 4.2 Golden Image — Production Pattern

- A pre-hardened, pre-configured baseline AMI, baked once, reused everywhere.
- **Why not pure user data:** baked config means faster launch (nothing to install at boot) and more consistency (every instance starts identical) vs a lengthy boot-time setup script.
- **Trade-off:** needs a maintenance pipeline — rebuild the golden image (often via EC2 Image Builder or Packer) when patches/updates are needed, rather than patching running instances by hand.

### 4.3 AMI Lifecycle Management

- AMIs accumulate cost via their underlying EBS snapshots — deregistering unused AMIs and deleting snapshots is genuine cost hygiene.
- **Deregistering an AMI** blocks _new_ launches but does **not** affect already-running instances.

---

## 5. AMI Sharing, Permissions, and Copying

### 5.1 AMI Permissions

- **Private (default)** — only your account.
- **Shared with specific accounts** — explicit account ID grants, a simpler mechanism than a full IAM resource policy but the same cross-account spirit as [§1](../Part1/Section-01-Part1-What-is-AWS-and-Cloud-Computing-Fundamentals.md)3.2.
- **Public** — anyone (how Marketplace/Community AMIs distribute).

### 5.2 Encrypted AMI Sharing

- If the underlying snapshot is KMS-encrypted with a CMK, cross-account sharing **also requires** sharing key-usage permission via the KMS key policy — direct application of "key policy is the primary gate" ([§14](../Part2/Section-14-Part2-KMS-and-Encryption.md)) — a common real-world gotcha.

### 5.3 Copying AMIs Across Regions

- AMIs are Region-specific — multi-Region golden image deployment requires an explicit `copy-image` action per target Region.

---

## 6. Instance Type Naming Convention

```
m6i.2xlarge
│ │  │
│ │  └─ Size (nano→micro→small→medium→large→xlarge→2xlarge...)
│ └──── Generation (6th gen of "i" variant)
└────── Family (M = general purpose)
```

- **Family letter(s)** — workload category ([§7](../Part1/Section-07-Part1-AWS-Support-Plans-and-Service-Category-Map.md)).
- **Feature variant letters:** `i` = Intel, `a` = AMD, `g` = Graviton (ARM), `n` = enhanced networking, `d` = local instance store (NVMe SSD).
- **Generation number** — later = better price-performance generally.
- **Size** — scales vCPU/memory/network roughly proportionally within a family.

> 🎯 Decoding an instance type name (e.g., `c6g.xlarge` = compute-optimized, 6th gen, Graviton, extra-large) tests real fluency.

---

## 7. Instance Families

| Family                                 | Optimized for                   | Use cases                                                           |
| -------------------------------------- | ------------------------------- | ------------------------------------------------------------------- |
| General Purpose (M, T, A1)             | Balanced compute/memory/network | Web servers, small-medium DBs, dev/test                             |
| Compute Optimized (C)                  | High vCPU-to-memory             | Batch processing, transcoding, HPC web servers, scientific modeling |
| Memory Optimized (R, X, z1d)           | Large memory relative to vCPU   | In-memory DBs/caches (Redis), large analytics, SAP HANA-style       |
| Storage Optimized (I, D, H)            | High/fast local disk I/O        | NoSQL DBs, data warehousing, distributed file systems               |
| Accelerated Computing (P, G, Inf, Trn) | GPUs/ML accelerator chips       | ML training/inference, graphics rendering, HPC                      |

### 7.1 Burstable "T" Family

- **CPU credit system:** accrues credits during low utilization, spends during bursts, rather than guaranteeing sustained full CPU.
- **Best for:** mostly-idle-with-occasional-spikes workloads (low-traffic web server, dev/test) — cost-effective.
- **Failure mode:** exhausting credits under sustained load → throttling (Standard mode) or extra charges (Unlimited mode).
- **Common mistake:** sustained-high-CPU workload on T-family, surprised by throttling/charges — fix: choose M/C family for sustained load.

---

## 8. Graviton — AWS's Custom ARM Processor

- **Graviton** = AWS's own custom ARM-architecture chips (not licensed Intel/AMD x86). `g` in the instance type name (`m7g`, `c7g`, `r7g`).
- **Benefit:** meaningfully better price-performance for many workloads vs comparable x86 ([§6](../Part1/Section-06-Part1-AWS-Pricing-and-Cost-Fundamentals.md) cost optimization).
- **Trade-off:** software must be compiled for ARM (or be architecture-agnostic) — may require rebuilding container images/verifying dependency compatibility.

---

## 9. Choosing an Instance Type — Decision Framework

1. Identify the workload's bottleneck (CPU/memory/storage-I/O/network) → points to a family.
2. Determine sustained vs bursty load → M/C/R for sustained, T-family for bursty/idle.
3. Check architecture compatibility → Graviton (ARM) eligible or x86-required?
4. Right-size within the chosen family using actual CloudWatch utilization, revisited continuously.

---

## 10. Production & Enterprise Usage

- **EC2 Image Builder** — automates the golden-image pipeline (build, test, distribute updated AMIs on schedule/trigger).
- **Standardized golden images across an Organization** — centrally-approved hardened images shared via AMI-sharing across accounts (mapped to [§13](../Part2/Section-13-Part2-AWS-Organizations-and-SCPs.md)'s OU structure), enforcing a consistent baseline.
- **Graviton migration** as an active cost-optimization initiative — a common real-world project.

---

## 11. Security Considerations

- **Strip secrets/credentials before AMI creation** — a baked-in credential exists in every future instance launched from it, a much larger blast radius than a single leak ([§15](../Part2/Section-15-Part2-Secrets-Manager-and-Parameter-Store.md) principle, applied to image-baking).
- **Vet Community/Marketplace AMIs** with the same scrutiny as any external dependency; prefer AWS-provided or custom AMIs for security-sensitive workloads.
- **Encrypted cross-account AMI sharing requires KMS key policy alignment** (§5.2) — a common practical gotcha.

---

## 12. Performance Considerations

- Instance family selection is the single largest performance lever — more impactful than fine-tuning within the wrong family.
- T-family credit exhaustion is a genuine, observable performance cliff — monitor `CPUCreditBalance` under sustained load.

---

## 13. Troubleshooting

| Symptom                                                   | Cause                                                                | Fix                                                                          |
| --------------------------------------------------------- | -------------------------------------------------------------------- | ---------------------------------------------------------------------------- |
| Can't launch from an AMI in a different Region            | AMIs are Region-specific                                             | Copy the AMI to the target Region first                                      |
| Cross-account AMI launch fails despite sharing permission | Snapshot is KMS-encrypted, target account lacks key-usage permission | Update the KMS key policy                                                    |
| T-family instance slows under sustained load              | CPU credit balance exhausted                                         | Monitor CPUCreditBalance; switch to Unlimited mode or a non-burstable family |
| Deregistered AMI, running instances unaffected            | Expected — deregistering only blocks new launches                    | No action needed                                                             |

---

## 14. Best Practices & Anti-Patterns

**Best practices:** build/maintain golden images via automated pipeline (Image Builder); strip all secrets before AMI creation; choose family by actual bottleneck; evaluate Graviton for eligible workloads; monitor T-family CPU credit balance.

**Anti-patterns:** ad hoc manual AMI recreation without a pipeline; production launches from unverified Community AMIs; sustained-high-CPU workloads on T-family; forgetting AMI Region-specificity in multi-Region planning.

---

## 15. Common Misconceptions

- "An AMI is the same as a running instance, just paused." → False — template vs running resource; many instances from one AMI.
- "AMIs are automatically available in every Region." → False — must be explicitly copied.
- "Deregistering an AMI terminates instances launched from it." → False — only blocks future launches.
- "T-family instances always underperform." → False — excellent under their intended bursty/idle pattern; mismatch only under sustained load.

---

## 16. Interview Questions (with model answers)

**🟢 What is an AMI and how does it relate to an instance?** A template (OS + software + config) used to launch instances. The instance is the running server created from it — many identical instances can launch from one AMI, enabling repeatable deployment and horizontal scaling.

**🟢 Compute-optimized vs memory-optimized family?** Compute-optimized (C): high vCPU-to-memory, for CPU-bound workloads (batch, transcoding). Memory-optimized (R): large memory relative to vCPU, for memory-bound workloads (in-memory DBs/caches). Choice = matching the actual bottleneck.

**🟡 How do T-family burstable instances work, and when are they wrong?** CPU credit system — accrue credits when idle, spend during bursts, no guaranteed sustained full CPU. Cost-effective for mostly-idle-with-spikes workloads. Wrong for sustained high-CPU workloads — credit exhaustion causes throttling (Standard) or extra charges (Unlimited); use M/C family instead.

**🟡 Deploy the same golden image to three Regions — what's needed?** AMIs are Region-specific — explicitly copy the AMI into each target Region (`copy-image`). If snapshot is KMS-encrypted, ensure an appropriately configured key (and its policy) exists in each target Region too, since KMS keys are also Region-specific.

**🔴 Golden image strategy for 20 accounts under one Organization, including patching?** Centralize creation in a dedicated (Shared Services/Security-adjacent) account using EC2 Image Builder to automate build/test/version rather than manual creation. Bake in security hardening, strip credentials before each build. Share AMIs to other accounts via AMI sharing (+ KMS key policy grants if encrypted). Patch via recurring Image Builder runs producing new AMI versions; update Auto Scaling launch templates to reference the new version so new instances pick it up, cycling out old instances over time rather than patching in place.

**🔴 Evaluate before recommending a Graviton migration?** Architecture compatibility — verify app/container base images/dependencies support ARM natively or are architecture-agnostic; x86-only compiled dependencies need rebuilding. Benchmark actual price-performance for this specific workload rather than assuming general published figures apply. Check third-party licensed software for architecture-specific licensing/ARM availability. Pilot on non-production first, validating correctness and real improvement before broad rollout — a genuine migration project with verification, not a trivial swap.

---

## 🔑 Key Takeaways

1. An AMI is a Region-specific template; an instance is the running thing launched from it — must be explicitly copied to use in another Region.
2. Custom "golden images" are the production pattern — pre-baked, hardened baselines via an automated pipeline, trading maintenance overhead for faster/more consistent launches.
3. Instance type names are decodable (family + generation + processor/feature variant + size) — recognizing the pattern and core family taxonomy is practical, testable knowledge.
4. T-family burstable instances trade sustained performance for cost efficiency via a CPU credit system — great for bursty/idle, wrong for sustained load.
5. Graviton (ARM) offers meaningfully better price-performance but requires verifying architecture compatibility — not a universal drop-in replacement.

## 🌐 Related Concepts (forward links)

- EC2 purchasing options (On-Demand, Reserved, Spot, Savings Plans) → [§21](./Section-21-Part3-EC2-Purchasing-Options.md)
- EBS volumes underlying AMI snapshots, in full depth → Part 5
- Auto Scaling launch templates referencing AMIs → [§23](./Section-23-Part3-Auto-Scaling-Groups.md)
