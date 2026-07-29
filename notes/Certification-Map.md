# Certification Map — Which Folder Combinations Cover Which Exam

This file tracks, for each major industry certification, which folder(s) in this
repo cover it and whether that folder's content actually exists yet. It is a
planning/reference index, not a knowledge-base topic itself.

**Status legend**

- ✅ **Ready** — folder is fully authored and sufficient for this exam
- 🟡 **YTS** ("Yet To be Started") — folder exists but is empty, or (for Kubernetes)
  contains only a roadmap with no sections authored yet
- ⚠️ **Partial** — combination includes at least one 🟡 YTS folder, so the
  certification is only partially coverable right now

---

## 1. AWS Certifications

| Certification                                       | Folder(s) Needed                                        | Status                        |
| ----------------------------------------------------- | ---------------------------------------------------------- | ------------------------------- |
| AWS Certified Cloud Practitioner (CLF-C02)             | `6. Cloud/1. AWS`                                           | ✅ Ready                        |
| AWS Certified Solutions Architect – Associate (SAA-C03)| `6. Cloud/1. AWS`                                           | ✅ Ready                        |
| AWS Certified SysOps Administrator – Associate         | `6. Cloud/1. AWS` + `2. Linux`                              | ✅ Ready                        |
| AWS Certified Solutions Architect – Professional       | `6. Cloud/1. AWS`                                           | ✅ Ready                        |
| AWS Certified Security – Specialty                     | `6. Cloud/1. AWS`                                           | ✅ Ready                        |
| AWS Certified DevOps Engineer – Professional           | `6. Cloud/1. AWS` + `9. CI-CD` 🟡 + `7. Terraform` 🟡        | ⚠️ Partial (cloud half ready)   |

## 2. Microsoft Azure Certifications

| Certification                                  | Folder(s) Needed                                        | Status                        |
| ------------------------------------------------ | ---------------------------------------------------------- | ------------------------------- |
| AZ-900: Azure Fundamentals                       | `6. Cloud/2. Azure`                                         | ✅ Ready                        |
| SC-900: Security, Compliance, Identity Fundamentals | `6. Cloud/2. Azure`                                       | ✅ Ready                        |
| AZ-104: Azure Administrator Associate            | `6. Cloud/2. Azure`                                         | ✅ Ready                        |
| AZ-305: Azure Solutions Architect Expert         | `6. Cloud/2. Azure`                                         | ✅ Ready                        |
| AZ-500: Azure Security Engineer Associate        | `6. Cloud/2. Azure`                                         | ✅ Ready                        |
| AZ-400: Azure DevOps Engineer Expert             | `6. Cloud/2. Azure` + `9. CI-CD` 🟡 + `7. Terraform` 🟡 + `1. GIT` | ⚠️ Partial (cloud + Git ready)  |

## 3. Google Cloud Certifications

| Certification                                | Folder(s) Needed                                                                 | Status                        |
| ----------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------- |
| Cloud Digital Leader                           | `6. Cloud/3. GCP`                                                                    | ✅ Ready                        |
| Associate Cloud Engineer (ACE)                 | `6. Cloud/3. GCP` + `2. Linux`                                                       | ✅ Ready                        |
| Professional Cloud Architect (PCA)             | `6. Cloud/3. GCP`                                                                    | ✅ Ready                        |
| Professional Cloud Security Engineer           | `6. Cloud/3. GCP`                                                                    | ✅ Ready                        |
| Professional Cloud DevOps Engineer             | `6. Cloud/3. GCP` + `12. Kubernetes` 🟡 + `9. CI-CD` 🟡 + `10. Prometheus` 🟡 + `11. Grafana` 🟡 | ⚠️ Partial (cloud half ready)   |

## 4. Kubernetes / CNCF Certifications

| Certification                                         | Folder(s) Needed                          | Status                                   |
| -------------------------------------------------------- | -------------------------------------------- | ------------------------------------------- |
| CKA — Certified Kubernetes Administrator                 | `12. Kubernetes` 🟡 + `2. Linux`             | ⚠️ Partial (roadmap only, Linux ready)     |
| CKAD — Certified Kubernetes Application Developer        | `12. Kubernetes` 🟡                          | 🟡 YTS                                      |
| CKS — Certified Kubernetes Security Specialist            | `12. Kubernetes` 🟡 + `2. Linux`             | ⚠️ Partial (roadmap only, Linux ready)     |
| KCNA — Kubernetes and Cloud Native Associate              | `12. Kubernetes` 🟡 + `4. Docker` 🟡          | 🟡 YTS                                      |

## 5. Vendor-Neutral / Tool-Specific Certifications

| Certification                                              | Folder(s) Needed              | Status   |
| -------------------------------------------------------------- | -------------------------------- | ---------- |
| HashiCorp Certified: Terraform Associate                        | `7. Terraform`                    | 🟡 YTS   |
| Docker Certified Associate (DCA)                                 | `4. Docker`                       | 🟡 YTS   |
| Red Hat Certified Specialist in Ansible Automation                | `8. Ansible` + `2. Linux`          | ⚠️ Partial (Linux ready) |
| CNCF Prometheus Certified Associate (PCA)                         | `10. Prometheus`                  | 🟡 YTS   |
| GitHub Foundations / GitHub Actions certification                 | `1. GIT` + `9. CI-CD` 🟡           | ⚠️ Partial (Git ready)   |

## 6. Networking Certifications

| Certification                | Folder(s) Needed  | Status |
| ------------------------------- | -------------------- | -------- |
| CompTIA Network+                | `3. Networking`       | 🟡 YTS |
| Cisco CCNA                      | `3. Networking`       | 🟡 YTS |

## 7. Language / Scripting Certifications

| Certification                             | Folder(s) Needed | Status |
| --------------------------------------------- | ------------------- | -------- |
| Python Institute PCEP / PCAP                    | `5. Python`          | 🟡 YTS |

---

## 8. Folder Status Summary

| Folder                | Content Status                     |
| ------------------------ | ------------------------------------- |
| `1. GIT`                  | ✅ Ready (40 sections)                 |
| `2. Linux`                | ✅ Ready (125 sections, 17 parts)      |
| `3. Networking`           | 🟡 YTS — empty                         |
| `4. Docker`               | 🟡 YTS — empty                         |
| `5. Python`               | 🟡 YTS — empty                         |
| `6. Cloud/1. AWS`         | ✅ Ready (131 sections, 15 parts)      |
| `6. Cloud/2. Azure`       | ✅ Ready (100 sections, 18 parts)      |
| `6. Cloud/3. GCP`         | ✅ Ready (85 sections, 13 parts)       |
| `7. Terraform`            | 🟡 YTS — empty                         |
| `8. Ansible`              | 🟡 YTS — empty                         |
| `9. CI-CD`                | 🟡 YTS — empty                         |
| `10. Prometheus`          | 🟡 YTS — empty                         |
| `11. Grafana`             | 🟡 YTS — empty                         |
| `12. Kubernetes`          | 🟡 YTS — roadmap only (0 of 141 sections authored) |

**Bottom line:** every certification whose folder combination touches only `1. GIT`, `2. Linux`, or `6. Cloud/*` is fully coverable today. Every certification that needs `12. Kubernetes`, `7. Terraform`, `8. Ansible`, `9. CI-CD`, `10. Prometheus`, `11. Grafana`, `3. Networking`, `4. Docker`, or `5. Python` is currently ⚠️ Partial or 🟡 YTS until that folder is authored.

This file should be updated whenever a folder moves from 🟡 YTS to ✅ Ready.
