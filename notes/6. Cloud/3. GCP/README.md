# GCP Zero-to-Enterprise Knowledge Base

A comprehensive, 85-section learning resource covering Google Cloud Platform from cloud fundamentals to enterprise-scale architecture, AI/ML, data engineering, security operations, and resilience testing.

## Quick Start

**👉 [Open the Master Index](./INDEX.md)** ← Complete navigation for all 13 parts and 85 sections.

## Structure at a Glance

```
📚 13 Parts | 85 Sections

Core Learning (Parts 1–8):   58 sections
Advanced Topics (Parts 9–13): 27 sections
```

| Part                             | Title                                               | Sections |
| -------------------------------- | --------------------------------------------------- | -------- |
| **[Part 1](./Contents/Part1)**   | Foundations & Core Compute                          | 1–10     |
| **[Part 2](./Contents/Part2)**   | Storage & Databases                                 | 11–18    |
| **[Part 3](./Contents/Part3)**   | Networking                                          | 19–27    |
| **[Part 4](./Contents/Part4)**   | Kubernetes & Containers                             | 28–34    |
| **[Part 5](./Contents/Part5)**   | IAM & Security                                      | 35–43    |
| **[Part 6](./Contents/Part6)**   | Data & Analytics                                    | 44–49    |
| **[Part 7](./Contents/Part7)**   | DevOps, IaC & Observability                         | 50–55    |
| **[Part 8](./Contents/Part8)**   | Enterprise Architecture, Cost & DR                  | 56–58    |
| **[Part 9](./Contents/Part9)**   | Enterprise Landing Zones & Multi-Project Operations | 59–64    |
| **[Part 10](./Contents/Part10)** | AI/ML & Generative AI on GCP                        | 65–71    |
| **[Part 11](./Contents/Part11)** | Security Operations & Incident Response             | 72–77    |
| **[Part 12](./Contents/Part12)** | Resilience Testing & Continuous DR Validation       | 78–81    |
| **[Part 13](./Contents/Part13)** | Interview Prep & Roadmap Synthesis                  | 82–85    |

## How to Use This Resource

### 1. **Learn Sequentially** (Recommended for beginners)

- Start with **[Part 1: Foundations & Core Compute](./Contents/Part1)** to establish GCP fundamentals
- Progress through Parts 2–8 for core GCP services and enterprise patterns
- Continue with Parts 9–13 for advanced topics and specializations
- Each part builds on previous knowledge

### 2. **Jump to Topics** (For experienced users)

- Use the **[Master Index](./INDEX.md)** to find sections by topic
- Browse part folders directly (e.g., `Contents/Part10/` for AI/ML topics)
- Each section is self-contained with cross-references

### 3. **Certification Prep** (PCA / ACE focus)

- See the domain mapping below to identify which Parts matter most for your target exam
- Cloud Digital Leader candidates need only Part 1 plus a light pass of Parts 5 and 8
- Associate Cloud Engineer (ACE) candidates should focus on Parts 1–5 (hands-on provisioning, networking, and IAM)
- Professional Cloud Architect (PCA) candidates need the full domain table below, including the enterprise/advanced Parts 8–13
- Professional Cloud Security Engineer candidates should focus on Part 5 (IAM & Security) and Part 11 (Security Operations)

### 4. **Interview Prep** (Final stage)

- Study **Part 13 — Interview Prep & Roadmap Synthesis** for a consolidated question bank, system design prompts, and capstone labs
- Most Parts from 1–12 close with their own dedicated interview drill section
- Reference Part 13's GCP vs. AWS vs. Azure comparison for architecture-level discussions

### 5. **Specialization Paths**

- **Data & Analytics:** Parts 2 (Storage & Databases), 6 (Data & Analytics)
- **AI/ML:** Parts 5 (IAM & Security), 7 (DevOps & IaC), 10 (AI/ML & GenAI)
- **Security & Compliance:** Parts 5 (IAM & Security), 9 (Landing Zones), 11 (Security Operations)
- **Enterprise Architecture:** Parts 3 (Networking), 8 (Enterprise Architecture, Cost & DR), 9 (Landing Zones), 12–13 (Resilience & Synthesis)

## Folder Layout

```
GCP/
├── README.md (this file — quick orientation)
├── INDEX.md (comprehensive navigation & section index for all 13 parts)
└── Contents/ (organized by part)
    ├── Part1/  (10 sections)
    ├── Part2/  (8 sections)
    ├── ...
    ├── Part11/ (6 sections)
    ├── Part12/ (4 sections)
    └── Part13/ (4 sections)
```

## Key Features

✅ **85 Complete Sections** — All parts finished, no gaps
✅ **Modular Organization** — Sections grouped by topic in `Contents/PartN/` folders
✅ **Cross-Referenced** — Sections link to related topics across parts
✅ **Interview-Focused** — Interview drills, system design, and best practices throughout
✅ **Certification-Aware** — Content maps directly onto Professional Cloud Architect exam domains, with Cloud Digital Leader/ACE/Security Engineer paths noted
✅ **Gap Coverage** — Enterprise Landing Zones, AI/ML & Generative AI, Security Operations, and Resilience Testing added as dedicated Parts (9–12) to reach parity with the AWS and Azure knowledge bases, plus Cloud Batch, Network Intelligence Center/Traffic Director, Cloud Identity/BeyondCorp, Binary Authorization/Confidential Computing, Cloud Composer, Dataplex, Looker, Cloud Deploy, and Eventarc/Workflows inserted in-place to close smaller gaps
✅ **Production-Ready** — From hands-on labs to enterprise-scale patterns
✅ **Accurate to GCP's Actual Tooling** — Explicitly notes where GCP's approach differs from AWS/Azure (e.g., no first-party chaos-engineering product; landing zones are Terraform/blueprint-driven rather than a single wizard product)

## What's Inside Each Part

- **Detailed section breakdowns** covering core concepts, architecture patterns, and best practices
- **Real-world examples** and design considerations
- **Interview drill questions** with model answers at the end of most parts
- **Cross-references** to related sections in other parts
- **Practical patterns** for hands-on application and system design

## Organization & Structure Notes

- **85 sections total**, organized into 13 parts with 3–10 sections each
- **Section numbering:** Continuous across all parts (1–85), not reset per part
  - Part 1: Sections 1–10
  - Part 2: Sections 11–18
  - Part 3: Sections 19–27
  - ... and so on through Part 13: Sections 82–85
- **Each part is self-contained** but includes cross-references to related sections in other parts
- **All 85 sections are organized in `Contents/PartN/` folders** for modular, scalable structure
- **Single navigation source:** INDEX.md is the master reference for all parts and sections

## Certification Domain Mapping (Professional Cloud Architect)

This KB was not written against a single pinned exam-blueprint revision, so treat the mapping below as orientation rather than a guaranteed percentage breakdown — always cross-check current weights against Google Cloud's published exam guide before scheduling.

| PCA Domain (representative)                               | Weight | Covered By                                                                                               |
| --------------------------------------------------------- | ------ | -------------------------------------------------------------------------------------------------------- |
| Designing and planning a cloud solution architecture      | ~24%   | Part 1 (Foundations & Core Compute), Part 8 (Enterprise Architecture, Cost & DR), Part 9 (Landing Zones) |
| Managing and provisioning a solution infrastructure       | ~15%   | Part 1, Part 4 (Kubernetes & Containers), Part 7 (DevOps, IaC & Observability)                           |
| Designing for security and compliance                     | ~18%   | Part 5 (IAM & Security), Part 11 (Security Operations & Incident Response)                               |
| Analyzing and optimizing technical and business processes | ~18%   | Part 6 (Data & Analytics), Part 10 (AI/ML & GenAI)                                                       |
| Managing implementation                                   | ~11%   | Part 7 (DevOps, IaC & Observability)                                                                     |
| Ensuring solution and operations reliability              | ~14%   | Part 8 (Enterprise Architecture, Cost & DR), Part 12 (Resilience Testing)                                |

Associate Cloud Engineer (ACE) candidates should treat Parts 1–5 as their core syllabus — the exam is hands-on provisioning rather than architecture-design, so it overlaps this table's "Managing and provisioning" and "Security" rows most heavily.

## Getting Started Now

1. **Read [INDEX.md](./INDEX.md)** for a complete overview and detailed section index
2. **Pick Part 1** if you're new to GCP, or jump to any part using the navigation table above
3. **Open `Contents/PartN/`** to see all sections for that part
4. **Read sections in order** within each part for cumulative understanding
5. **Complete interview drills** to self-assess understanding
6. **Use cross-references** to explore related topics across parts

## Additional Professional-Level Certifications

GCP's certification catalog has no separate "Specialty" tier (unlike AWS) — Professional is its only advanced generalist/vertical tier, so Professional Cloud Architect above and the certs below are the ceiling of what this KB maps to.

| Professional Certification             | Covered By                                                                                          | Coverage                                                                                                               |
| -------------------------------------- | --------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------- |
| Professional Cloud Security Engineer   | Part 5 (IAM & Security), Part 11 (Security Operations & Incident Response)                          | Strong — dedicated Parts                                                                                               |
| Professional Cloud DevOps Engineer     | Part 7 (DevOps, IaC & Observability); pair with `12. Kubernetes` for SRE-style workload reliability | Partial — needs `9. CI-CD`/`10. Prometheus`/`11. Grafana` (roadmap-only) for full coverage, see `Certification-Map.md` |
| Professional Data Engineer             | Part 6 (Data & Analytics)                                                                           | Partial — covers GCP data services, not deep pipeline/ML-modeling theory                                               |
| Professional Machine Learning Engineer | Part 10 (AI/ML & Generative AI on GCP)                                                              | Partial — covers GCP ML services, not ML theory/modeling depth                                                         |

**Total Content:** 85 sections | Continuously updated
**Last Updated:** August 3, 2026
