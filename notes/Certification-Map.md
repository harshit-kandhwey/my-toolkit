# Certification Map — Which Folder Combinations Cover Which Exam

This file tracks, for each major industry certification, which folder(s) in this
repo cover it and whether that folder's content actually exists yet. It is a
planning/reference index, not a knowledge-base topic itself.

**Status legend**

- ✅ **Ready** — folder is fully authored, with an explicit certification domain
  mapping in its README where a relevant industry cert exists
- 🟡 **Roadmap Only** — folder has a scaffolded `00-Roadmap.md` but no sections
  authored yet
- ⚠️ **Partial** — combination includes at least one 🟡 Roadmap Only folder, so
  the certification is only partially coverable right now

---

## 1. AWS Certifications

| Certification                                           | Folder(s) Needed                                   | Status                                            |
| ------------------------------------------------------- | -------------------------------------------------- | ------------------------------------------------- |
| AWS Certified Cloud Practitioner (CLF-C02)              | `6. Cloud/1. AWS`                                  | ✅ Ready                                          |
| AWS Certified Solutions Architect – Associate (SAA-C03) | `6. Cloud/1. AWS`                                  | ✅ Ready (explicit domain map)                    |
| AWS Certified SysOps Administrator – Associate          | `6. Cloud/1. AWS` + `2. Linux`                     | ✅ Ready                                          |
| AWS Certified Solutions Architect – Professional        | `6. Cloud/1. AWS`                                  | ✅ Ready (explicit domain map)                    |
| AWS Certified Security – Specialty                      | `6. Cloud/1. AWS`                                  | ✅ Ready (explicit domain map)                    |
| AWS Certified Advanced Networking – Specialty           | `6. Cloud/1. AWS`                                  | ⚠️ Partial (single-Part coverage)                 |
| AWS Certified DevOps Engineer – Professional            | `6. Cloud/1. AWS` + `9. CI-CD` 🟡 + `7. Terraform` | ⚠️ Partial (cloud + Terraform ready, needs CI-CD) |

## 2. Microsoft Azure Certifications

| Certification                                                          | Folder(s) Needed                                                | Status                                                               |
| ---------------------------------------------------------------------- | --------------------------------------------------------------- | -------------------------------------------------------------------- |
| AZ-900: Azure Fundamentals                                             | `6. Cloud/2. Azure`                                             | ✅ Ready                                                             |
| SC-900: Security, Compliance, Identity Fundamentals                    | `6. Cloud/2. Azure`                                             | ✅ Ready                                                             |
| AZ-104: Azure Administrator Associate                                  | `6. Cloud/2. Azure`                                             | ✅ Ready (explicit domain map)                                       |
| AZ-305: Azure Solutions Architect Expert                               | `6. Cloud/2. Azure`                                             | ✅ Ready (explicit domain map)                                       |
| AZ-500: Azure Security Engineer Associate                              | `6. Cloud/2. Azure`                                             | ✅ Ready                                                             |
| AZ-400: Azure DevOps Engineer Expert                                   | `6. Cloud/2. Azure` + `9. CI-CD` 🟡 + `7. Terraform` + `1. GIT` | ⚠️ Partial (cloud + Terraform + Git ready, needs CI-CD)              |
| Azure Specialty certs (SAP Workloads, Virtual Desktop, IoT Operations) | N/A                                                             | ⚠️ Not covered — narrow verticals outside this KB's generalist scope |

## 3. Google Cloud Certifications

| Certification                          | Folder(s) Needed                                                                              | Status                                                |
| -------------------------------------- | --------------------------------------------------------------------------------------------- | ----------------------------------------------------- |
| Cloud Digital Leader                   | `6. Cloud/3. GCP`                                                                             | ✅ Ready                                              |
| Associate Cloud Engineer (ACE)         | `6. Cloud/3. GCP` + `2. Linux`                                                                | ✅ Ready                                              |
| Professional Cloud Architect (PCA)     | `6. Cloud/3. GCP`                                                                             | ✅ Ready (explicit domain map)                        |
| Professional Cloud Security Engineer   | `6. Cloud/3. GCP`                                                                             | ✅ Ready (explicit domain map)                        |
| Professional Data Engineer             | `6. Cloud/3. GCP`                                                                             | ⚠️ Partial (services covered, not pipeline/ML theory) |
| Professional Machine Learning Engineer | `6. Cloud/3. GCP`                                                                             | ⚠️ Partial (services covered, not ML theory)          |
| Professional Cloud DevOps Engineer     | `6. Cloud/3. GCP` + `12. Kubernetes` + `9. CI-CD` 🟡 + `10. Prometheus` 🟡 + `11. Grafana` 🟡 | ⚠️ Partial (cloud + Kubernetes ready)                 |

## 4. Kubernetes / CNCF Certifications

| Certification                                     | Folder(s) Needed                  | Status                         |
| ------------------------------------------------- | --------------------------------- | ------------------------------ |
| CKA — Certified Kubernetes Administrator          | `12. Kubernetes` + `2. Linux`     | ✅ Ready (explicit domain map) |
| CKAD — Certified Kubernetes Application Developer | `12. Kubernetes`                  | ✅ Ready (explicit domain map) |
| CKS — Certified Kubernetes Security Specialist    | `12. Kubernetes` + `2. Linux`     | ✅ Ready (explicit domain map) |
| KCNA — Kubernetes and Cloud Native Associate      | `12. Kubernetes` + `4. Docker` 🟡 | ⚠️ Partial (Kubernetes ready)  |

CNCF has no separate "Professional" or "Specialty" tier above CKA/CKAD/CKS — those three ARE the ceiling for Kubernetes-specific credentials.

## 5. Vendor-Neutral / Tool-Specific Certifications

| Certification                                      | Folder(s) Needed             | Status                         |
| -------------------------------------------------- | ---------------------------- | ------------------------------ |
| HashiCorp Certified: Terraform Associate           | `7. Terraform`               | ✅ Ready (explicit domain map) |
| Docker Certified Associate (DCA)                   | `4. Docker` 🟡               | 🟡 Roadmap Only                |
| Red Hat Certified Specialist in Ansible Automation | `8. Ansible` 🟡 + `2. Linux` | ⚠️ Partial (Linux ready)       |
| CNCF Prometheus Certified Associate (PCA)          | `10. Prometheus` 🟡          | 🟡 Roadmap Only                |
| GitHub Foundations / GitHub Actions certification  | `1. GIT` + `9. CI-CD` 🟡     | ⚠️ Partial (Git ready)         |

HashiCorp has no separate "Professional" or "Specialty" tier above Terraform Associate — it is the ceiling for Terraform-specific credentials (HashiCorp's Vault/Consul Associate certs are separate products, not higher tiers of the same cert).

## 6. Networking Certifications

| Certification    | Folder(s) Needed   | Status          |
| ---------------- | ------------------ | --------------- |
| CompTIA Network+ | `3. Networking`    | ✅ Ready (explicit domain map) |
| Cisco CCNA       | `3. Networking`    | ⚠️ Partial (conceptual switching/routing depth, not full hardware-configuration depth) |

## 7. Language / Scripting Certifications

| Certification                | Folder(s) Needed | Status          |
| ---------------------------- | ---------------- | --------------- |
| Python Institute PCEP / PCAP | `5. Python` 🟡   | 🟡 Roadmap Only |

## 8. Linux Certifications

| Certification                                          | Folder(s) Needed                                         | Status                                                                     |
| ------------------------------------------------------ | -------------------------------------------------------- | -------------------------------------------------------------------------- |
| Linux Foundation Certified System Administrator (LFCS) | `2. Linux`                                               | ✅ Ready (explicit domain map)                                             |
| Red Hat Certified System Administrator (RHCSA)         | `2. Linux`                                               | ✅ Ready (adjacent, not exam-blueprint-pinned)                             |
| Red Hat Certified Engineer (RHCE)                      | `2. Linux` + `8. Ansible` 🟡                             | ⚠️ Partial (Linux ready, needs Ansible for exam-specific depth)            |
| Red Hat Certified Architect (RHCA)                     | `2. Linux` + `8. Ansible` 🟡 + `12. Kubernetes` + others | ⚠️ Partial — multi-exam credential spanning several KBs, no single mapping |

## 9. Git

No single industry-standard Git certification exists analogous to the AWS/Azure/GCP/Kubernetes/Linux exams above, so `1. GIT` is not mapped to a certification domain table — its README notes this explicitly.

---

## 10. Folder Status Summary

| Folder              | Content Status                                                      |
| ------------------- | ------------------------------------------------------------------- |
| `1. GIT`            | ✅ Ready (36 sections, 8 parts) — no cert applicable                |
| `2. Linux`          | ✅ Ready (125 sections, 17 parts) — LFCS domain map, RHCSA-adjacent |
| `3. Networking`     | ✅ Ready (145 sections, 17 parts) — CompTIA Network+ domain map      |
| `4. Docker`         | 🟡 Roadmap Only — 109 sections planned, 15 parts                    |
| `5. Python`         | 🟡 Roadmap Only — 130 sections planned, 16 parts                    |
| `6. Cloud/1. AWS`   | ✅ Ready (131 sections, 15 parts) — SAA-C03 domain map              |
| `6. Cloud/2. Azure` | ✅ Ready (100 sections, 18 parts) — AZ-104 & AZ-305 domain maps     |
| `6. Cloud/3. GCP`   | ✅ Ready (85 sections, 13 parts) — PCA domain map                   |
| `7. Terraform`      | ✅ Ready (120 sections, 17 parts) — Terraform Associate domain map  |
| `8. Ansible`        | 🟡 Roadmap Only — 119 sections planned                              |
| `9. CI-CD`          | 🟡 Roadmap Only — 130 sections planned, 16 parts                    |
| `10. Prometheus`    | 🟡 Roadmap Only — 99 sections planned, 14 parts                     |
| `11. Grafana`       | 🟡 Roadmap Only — 95 sections planned, 13 parts                     |
| `12. Kubernetes`    | ✅ Ready (141 sections, 18 parts) — CKA/CKAD/CKS domain maps        |

**Bottom line:** every certification whose folder combination touches only `1. GIT`, `2. Linux`, `3. Networking`, `6. Cloud/*`, `7. Terraform`, or `12. Kubernetes` is fully coverable today, with an explicit domain-weight mapping in the relevant README wherever a real exam blueprint exists. Every certification that also needs `8. Ansible`, `9. CI-CD`, `10. Prometheus`, `11. Grafana`, `4. Docker`, or `5. Python` is currently ⚠️ Partial until that folder's roadmap is authored into sections.

This file should be updated whenever a folder moves from 🟡 Roadmap Only to ✅ Ready, or whenever a README's certification mapping changes.
