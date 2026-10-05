# Docker Zero-to-Production Knowledge Base

A comprehensive, 109-section learning resource covering Docker from the container model and Engine internals to image authoring, Compose, networking, storage, security hardening, registries, build optimization, CI/CD integration, and production operations.

## Quick Start

**👉 [Open the Master Index](./INDEX.md)** ← Complete navigation for all 15 parts and 109 sections.

## Structure at a Glance

```
📚 15 Parts | 109 Sections

Core Learning (Parts 1–10):  79 sections
Delivery, Operations & Mastery (Parts 11–15): 30 sections
```

| Part                             | Title                                                   | Sections |
| -------------------------------- | ------------------------------------------------------- | -------- |
| **[Part 1](./Contents/Part1)**   | Foundations and History                                 | 1–7      |
| **[Part 2](./Contents/Part2)**   | Architecture and the Container Runtime                  | 8–15     |
| **[Part 3](./Contents/Part3)**   | Images and Dockerfile Authoring                         | 16–25    |
| **[Part 4](./Contents/Part4)**   | Container Lifecycle and CLI                             | 26–33    |
| **[Part 5](./Contents/Part5)**   | Docker Compose and Multi-Container Apps                 | 34–41    |
| **[Part 6](./Contents/Part6)**   | Networking                                              | 42–49    |
| **[Part 7](./Contents/Part7)**   | Storage and Volumes                                     | 50–56    |
| **[Part 8](./Contents/Part8)**   | Security and Hardening                                  | 57–65    |
| **[Part 9](./Contents/Part9)**   | Registries and Image Distribution                       | 66–72    |
| **[Part 10](./Contents/Part10)** | Build Optimization and Multi-Stage Builds               | 73–79    |
| **[Part 11](./Contents/Part11)** | CI/CD Integration                                       | 80–85    |
| **[Part 12](./Contents/Part12)** | Production Operations and Monitoring                    | 86–93    |
| **[Part 13](./Contents/Part13)** | Mastery: Best Practices, Anti-Patterns, and Comparisons | 94–99    |
| **[Part 14](./Contents/Part14)** | Interview Preparation                                   | 100–105  |
| **[Part 15](./Contents/Part15)** | Wrap-Up                                                 | 106–109  |

## How to Use This Resource

### 1. **Learn Sequentially** (Recommended for beginners)

- Start with **[Part 1: Foundations and History](./Contents/Part1)** to establish the container model
- Progress through Parts 2–10 for the Engine, images, Compose, networking, storage, security, registries and builds
- Continue with Parts 11–15 for CI/CD, production operations, mastery and interview preparation
- Each part builds on previous knowledge

### 2. **Jump to Topics** (For experienced users)

- Use the **[Master Index](./INDEX.md)** to find sections by topic
- Browse part folders directly (e.g., `Contents/Part8/` for security topics)
- Each section is self-contained with cross-references

### 3. **Certification Prep** (DCA-style domains)

- See the domain mapping below to identify which Parts matter most for Docker Certified Associate-style competence
- The DCA exam itself has been retired by Docker/Mirantis, so treat the mapping as a competence framework rather than a live exam blueprint
- Pair with the `12. Kubernetes` KB for orchestration and KCNA-style cloud-native coverage

### 4. **Interview Prep** (Final stage)

- Study each section's **Interview Questions** (four per section: Beginner, Intermediate, Senior, Architect)
- Work through the dedicated question banks and scenarios in Part 14
- Finish with the labs and checklist in Part 15

### 5. **Specialization Paths**

- **Platform / SRE:** Parts 2 (Architecture), 6 (Networking), 7 (Storage), 12 (Production Operations)
- **Security:** Parts 2, 8 (Security and Hardening), 9 (Registries), 10 (Build secrets)
- **CI/CD and Release Engineering:** Parts 3, 9, 10, 11
- **Application Developers:** Parts 3, 4, 5 (Compose), 10

## Folder Layout

```
Docker/
├── README.md (this file — quick orientation)
├── INDEX.md (comprehensive navigation & section index for all 15 parts)
├── 00-Roadmap.md (planning roadmap and section-to-file mapping)
└── Contents/ (organized by part)
    ├── Part1/ (7 sections)
    ├── Part2/ (8 sections)
    ├── Part3/ (10 sections)
    ├── Part4/ (8 sections)
    ├── Part5/ (8 sections)
    ├── Part6/ (8 sections)
    ├── Part7/ (7 sections)
    ├── Part8/ (9 sections)
    ├── Part9/ (7 sections)
    ├── Part10/ (7 sections)
    ├── Part11/ (6 sections)
    ├── Part12/ (8 sections)
    ├── Part13/ (6 sections)
    ├── Part14/ (6 sections)
    └── Part15/ (4 sections)
```

## Key Features

✅ **109 Complete Sections** — All parts finished, no gaps
✅ **Modular Organization** — Sections grouped by topic in `Contents/PartN/` folders
✅ **Cross-Referenced** — Sections link to related topics across parts
✅ **Interview-Focused** — Four-level interview questions in every section, plus dedicated banks in Part 14
✅ **Certification-Aware** — Content maps onto DCA-style domains, with the retired status noted
✅ **Hands-On** — Every section has a Hands-On part, and Part 15 adds progressive labs
✅ **Production-Ready** — From local Compose workflows to CI/CD, monitoring and rollback

## What's Inside Each Part

- **Fourteen-part section template:** Definition, Why This Matters, Prerequisites, Architecture Diagram, Hands-On, Production Usage, Security, Troubleshooting, Best Practices, Anti-Patterns, Interview Questions, Misconceptions, Key Takeaways, Related Concepts
- **Real-world examples** and design considerations
- **Interview questions** with model answers in every section
- **Cross-references** to related sections in other parts
- **Practical patterns** for hands-on application and system design

## Organization & Structure Notes

- **109 sections total**, organized into 15 parts with 4–10 sections each
- **Section numbering:** Continuous across all parts (1–109), not reset per part
  - Part 1: Sections 1–7
  - Part 2: Sections 8–15
  - Part 3: Sections 16–25
  - ... and so on through Part 15: Sections 106–109
- **Each part is self-contained** but includes cross-references to related sections in other parts
- **All 109 sections are organized in `Contents/PartN/` folders** for modular, scalable structure
- **Single navigation source:** INDEX.md is the master reference for all parts and sections

## Certification Domain Mapping (Docker Certified Associate — DCA, Historical Reference)

The Docker Certified Associate (DCA) exam has since been retired by Docker/Mirantis, but its domain breakdown remains a useful, widely-referenced framework for structuring practical Docker competence. This KB was not written against a pinned exam blueprint, so treat the mapping below as orientation rather than a guaranteed breakdown. Section 100 covers the domain breakdown in detail; confirm any exam weights against current sources before relying on them.

| Representative DCA Domain            | Covered By                                                                         |
| ------------------------------------ | ---------------------------------------------------------------------------------- |
| Orchestration (Swarm-era)            | Part 12 (Swarm, briefly, pre-Kubernetes), Part 13 (path to Kubernetes)             |
| Image Creation, Management, Registry | Part 3 (Images and Dockerfiles), Part 9 (Registries), Part 10 (Build Optimization) |
| Installation and Configuration       | Part 1 (Foundations), Part 2 (Architecture and daemon configuration)               |
| Networking                           | Part 6 (Networking)                                                                |
| Security                             | Part 8 (Security and Hardening)                                                    |
| Storage and Volumes                  | Part 7 (Storage and Volumes)                                                       |

Part 14 additionally provides a dedicated interview-question bank and hands-on scenario exercises modeled on how Docker competence is assessed in modern SRE/DevOps interview loops. For orchestration beyond Swarm, continue with the [Kubernetes knowledge base](../12.%20Kubernetes/README.md), which maps to CKA, CKAD, CKS and KCNA.

## Getting Started Now

1. **Read [INDEX.md](./INDEX.md)** for a complete overview and detailed section index
2. **Pick Part 1** if you're new to containers, or jump to any part using the navigation table above
3. **Open `Contents/PartN/`** to see all sections for that part
4. **Read sections in order** within each part for cumulative understanding
5. **Work through the interview questions** to self-assess understanding
6. **Use cross-references** to explore related topics across parts

**Total Content:** 109 sections | Continuously updated
**Last Updated:** October 6, 2026
