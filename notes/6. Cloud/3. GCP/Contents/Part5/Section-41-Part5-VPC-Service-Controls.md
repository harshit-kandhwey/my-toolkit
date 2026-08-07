# Section 41 (Part 5): VPC Service Controls

## 1. Definition

**Plain language:** IAM ([Section 35](./Section-35-Part5-IAM-Fundamentals-Members-Roles-Policies.md)) controls _who_ can call an API and _what_ they're allowed to do. But even with perfectly correct IAM, a legitimate, correctly-scoped credential that gets stolen (a leaked service account key, a compromised laptop with valid `gcloud` credentials) can still be used to copy data out of a Cloud Storage bucket or BigQuery dataset to somewhere outside your control — because IAM alone doesn't know or care _where_ the request is coming from or _where the data is going_. VPC Service Controls closes that specific gap.

**Precise:** **VPC Service Controls (VPC-SC)** creates a **service perimeter** around a set of GCP resources (projects) and supported APIs (Cloud Storage, BigQuery, and dozens of others), restricting data movement across that perimeter's boundary regardless of IAM permissions — even a principal with valid IAM Allow permissions cannot move data out of the perimeter to an unauthorized destination, mitigating **data exfiltration** as a distinct threat model from unauthorized access.

## 2. Why It Exists

Consider a compromised service account key with legitimate `roles/storage.objectViewer` on a sensitive bucket. Under IAM alone, that stolen credential can be used from _anywhere_ — an attacker's laptop, a VM in an unrelated project, a different organization entirely — to read and exfiltrate that data, because IAM evaluates "is this principal allowed to do this action," not "is this request originating from, and directed to, somewhere it should be." This is precisely the exfiltration path VPC Service Controls exists to block: it adds a network/context-aware boundary _on top of_ IAM, so that even a valid, correctly-permissioned credential is denied if the request crosses outside an approved perimeter — a second, independent layer that has to also be satisfied, not an alternative to correct IAM.

## 3. Core Concepts

### 3.1 Service Perimeter

A **service perimeter** groups one or more GCP projects and a defined set of supported services (e.g., `storage.googleapis.com`, `bigquery.googleapis.com`) into a boundary. Requests to those services _from inside_ the perimeter to resources _inside_ the perimeter proceed normally (subject to IAM as usual); requests attempting to reach _across_ the boundary — either data leaving to an external destination, or an external identity/network reaching in — are blocked by VPC-SC regardless of IAM, unless an explicit exception is configured.

### 3.2 Perimeter Bridges

Two separate perimeters (e.g., belonging to different departments, each with their own project set) normally cannot exchange data at all. A **perimeter bridge** creates a controlled, bidirectional connection between two specific perimeters, allowing defined communication between them without merging them into one perimeter or fully opening either boundary — useful when two otherwise-isolated teams have one legitimate integration point (e.g., a shared pipeline reading from one team's BigQuery dataset into another's).

### 3.3 Ingress and Egress Rules

Rather than the coarser bridge mechanism, **ingress/egress rules** allow fine-grained exceptions on a single perimeter — e.g., "allow requests from this specific external service account, restricted to this specific project and this specific API method, to read from inside the perimeter." This is the mechanism used for controlled access from outside sources (an on-premises system, a partner's GCP project) without opening the perimeter broadly.

### 3.4 Dry-Run Mode

Because a service perimeter can break legitimate existing traffic if misconfigured (a real risk given how many services and access patterns a production environment has), VPC-SC supports **dry-run mode**: the perimeter's rules are evaluated and violations are logged (to Cloud Audit Logs' Policy Denied logs, [Section 40](./Section-40-Part5-Compliance-Governance.md)) exactly as they would be enforced, but nothing is actually blocked. This lets a team observe what _would_ break before committing to enforcement, iterating on the perimeter's rules until dry-run shows no unexpected violations, then switching to enforced mode.

> ⚠️ **Interview-relevant nuance:** Skipping dry-run mode and enabling a new perimeter directly in enforced mode is one of the most common causes of a self-inflicted production outage in GCP security hardening projects — a perimeter that looks correct on paper frequently misses a legitimate access pattern (a cross-project data pipeline, a CI/CD system reading from BigQuery) that only surfaces once real traffic hits it. Dry-run mode exists specifically to catch this before it becomes an incident.

## 4. Architecture Diagram

```
                          ORGANIZATION
   ┌──────────────────────────────────────────────────────────────────┐
   │                SERVICE PERIMETER: "finance-data"                 │
   │   ┌─────────────────┐        ┌─────────────────┐                 │
   │   │  Project: fin-  │        │  Project: fin-  │                 │
   │   │  warehouse      │        │  reporting      │                 │
   │   │  (BigQuery)     │        │  (Cloud Storage)│                 │
   │   └───────┬─────────┘        └────────┬────────┘                 │
   │           │   requests among perimeter members: OK (IAM applies) │
   │           └──────────────────┬─────────────────┘                 │
   └──────────────────────────────┼───────────────────────────────────┘
                                  │
                     ✕  BLOCKED — even with valid IAM Allow  ✕
                                  │
                     ┌────────────▼────────────────┐
                     │  Stolen service account key │
                     │  used from an external VM / │
                     │  unrelated project          │
                     └─────────────────────────────┘

           Perimeter Bridge (explicit, bidirectional)
   ┌────────────────────────┐        ┌───────────────────────┐
   │ Perimeter: "finance"   │◄──────►│ Perimeter: "analytics"│
   └────────────────────────┘ bridge └───────────────────────┘
```

## 5. Comparison with AWS and Azure

| Concept                                                     | GCP                                               | AWS                                                                                                                         | Azure                                                                                       |
| ----------------------------------------------------------- | ------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| Data-exfiltration-focused perimeter around managed services | VPC Service Controls                              | VPC Endpoints (Gateway/Interface) + endpoint policies                                                                       | Private Link / Service Endpoints + network/firewall rules                                   |
| Blocks exfiltration even with valid IAM credentials         | Yes — VPC-SC is explicitly designed for this      | Partially — endpoint policies restrict which resources are reachable via the endpoint, combined with SCPs (condition-based) | Partially — combined with Azure Policy and firewall/NSG rules                               |
| Cross-boundary controlled connection                        | Perimeter bridge                                  | VPC peering / Transit Gateway + endpoint policy scoping                                                                     | VNet peering + Private Link scoping                                                         |
| Safe-rollout testing mode                                   | Dry-run mode                                      | No direct native equivalent (typically tested via IAM policy simulation)                                                    | No direct native equivalent (Azure Policy has "Audit" effect, conceptually similar)         |
| Primary threat model addressed                              | Data exfiltration via otherwise-valid credentials | Primarily network reachability; exfiltration mitigation requires combining several controls                                 | Primarily network reachability; exfiltration mitigation requires combining several controls |

> 💡 **Tip:** This is a genuine differentiator worth knowing cold for interviews — VPC-SC is purpose-built around the exfiltration threat model as its primary design goal, whereas AWS and Azure's nearest equivalents (VPC Endpoints + SCPs, Private Link + Policy) achieve a similar outcome only when several separate features are deliberately combined together.

## 6. Hands-On Example: Creating a Service Perimeter in Dry-Run Mode

**Purpose:** Create an access policy and a service perimeter around a project's Cloud Storage and BigQuery usage, starting in dry-run mode to observe impact before enforcing.

```bash
gcloud access-context-manager policies create \
  --organization=123456789012 --title="org-access-policy"

gcloud access-context-manager perimeters dry-run create finance-data \
  --title="Finance Data Perimeter" \
  --resources=projects/111111111 \
  --restricted-services=storage.googleapis.com,bigquery.googleapis.com \
  --policy=THE_POLICY_ID
```

**Expected output (abbreviated):**

```
Created access policy [THE_POLICY_ID].
Created dry-run perimeter [finance-data].
```

**Checking for violations before enforcing:**

```bash
gcloud logging read \
  "protoPayload.metadata.@type=\"type.googleapis.com/google.cloud.audit.VpcServiceControlAuditMetadata\""  \
  --limit=10
```

Once dry-run shows no unexpected denials over a representative period, the perimeter is promoted from dry-run to enforced:

```bash
gcloud access-context-manager perimeters dry-run enforce finance-data \
  --policy=THE_POLICY_ID
```

## 7. Production & Enterprise Usage

- **Perimeter around the org's most sensitive data services, not everything.** Because VPC-SC adds real friction to legitimate cross-service and cross-project access patterns, enterprises typically scope perimeters tightly around genuinely sensitive data stores (financial data, PII/PHI, source code in a private Artifact Registry) rather than wrapping the entire organization, where the operational overhead would outweigh the benefit for lower-sensitivity workloads.
- **Perimeters as a required control for regulated workloads.** VPC-SC is commonly a mandatory component of Assured Workloads ([Section 40](./Section-40-Part5-Compliance-Governance.md)) configurations, since exfiltration resistance is exactly the property many compliance regimes require beyond simple access control.
- **Always dry-run, always review Policy Denied logs before enforcing.** Mature platform teams treat skipping the dry-run phase as a hard process violation — every new perimeter or perimeter change runs in dry-run first, with a deliberate review of Policy Denied logs ([Section 40](./Section-40-Part5-Compliance-Governance.md)) against known legitimate traffic patterns before flipping to enforced.

## 8. Common Misconceptions

- **Misconception:** "VPC Service Controls is a firewall — it's about network traffic." It operates at the API/service level, not the network packet level — it governs which API calls involving supported services (like Cloud Storage or BigQuery) are allowed to cross a perimeter boundary, independent of the underlying network path, which is a different concern from VPC firewall rules or Cloud Firewall.
- **Misconception:** "If my IAM policy is correct, I don't need VPC-SC." IAM and VPC-SC solve different threats — IAM governs authorized actions for a given identity; VPC-SC governs data movement across a boundary regardless of whether the identity performing it is authorized. A stolen but validly-permissioned credential is exactly the scenario IAM alone cannot stop and VPC-SC is designed to.
- **Misconception:** "A perimeter with no exceptions configured means nothing gets through, full stop." Legitimate cross-perimeter access is still possible via perimeter bridges or explicit ingress/egress rules — VPC-SC isn't an all-or-nothing lockdown, it's a default-deny boundary with deliberate, auditable exception mechanisms.

## 9. Interview Questions

**🎯 Beginner:** _What problem does VPC Service Controls solve that IAM alone does not?_
**Model answer:** IAM determines whether a given identity is allowed to perform a given action, but doesn't know or restrict where the request originates from or where resulting data goes. A stolen but validly-permissioned credential can still exfiltrate data from anywhere under IAM alone. VPC Service Controls adds a perimeter boundary around supported services and projects that blocks data movement across that boundary regardless of IAM permissions, directly mitigating data exfiltration as a distinct threat.

**🎯 Intermediate:** _What is dry-run mode, and why is it recommended before enforcing a new service perimeter?_
**Model answer:** Dry-run mode evaluates a perimeter's rules and logs what would be blocked, without actually blocking anything. It's recommended because service perimeters are easy to under-scope in ways that only surface under real traffic — a legitimate cross-project pipeline or CI/CD access pattern that wasn't accounted for when designing the perimeter. Running in dry-run first and reviewing the resulting Policy Denied-equivalent violation logs lets a team fix the perimeter's rules before enforcement, avoiding a self-inflicted outage from blocking legitimate traffic.

**🎯 Senior/Architect:** _Design VPC Service Controls for an organization with a finance team and an analytics team, where analytics needs read access to a subset of finance's BigQuery data, and the whole environment must resist exfiltration even from a compromised service account._
**Model answer:** I'd create two separate service perimeters — one around the finance team's projects (BigQuery, Cloud Storage) and one around analytics' projects — rather than one shared perimeter, so each team's blast radius stays contained and a compromise in one doesn't automatically expose the other's full resource set. For the legitimate cross-team need, I'd configure a perimeter bridge (or, if the access pattern is narrower, an explicit ingress rule) permitting only the specific analytics service account to read the specific finance BigQuery dataset needed, rather than opening broader connectivity between the perimeters. Every perimeter change — initial creation and any later rule modification — goes through dry-run mode first, with a review of violation logs against known legitimate traffic before promoting to enforced, since a perimeter this consequential is exactly where an under-scoped rule causes real production breakage. I'd combine this with correctly-scoped IAM (VPC-SC is a second independent layer, not a replacement), CMEK on the underlying data ([Section 38](./Section-38-Part5-Secret-Manager-Cloud-KMS.md)), and continuous monitoring via Security Command Center ([Section 39](./Section-39-Part5-Security-Command-Center.md)) and Policy Denied audit logs ([Section 40](./Section-40-Part5-Compliance-Governance.md)) to detect both attempted exfiltration and perimeter misconfiguration drift over time.

## 🔑 Key Takeaways

- 🔑 VPC Service Controls creates a service perimeter around projects and supported APIs, blocking data movement across the boundary even for a principal with otherwise-valid IAM permissions — it specifically targets data exfiltration, a threat IAM alone cannot address.
- 🔑 Perimeter bridges and ingress/egress rules provide controlled, auditable exceptions for legitimate cross-perimeter or external access, so a perimeter is a default-deny boundary, not an absolute lockdown.
- 🔑 Dry-run mode logs what would be blocked without enforcing it — always use it before enforcing a new or changed perimeter, since under-scoped perimeters routinely miss real legitimate traffic patterns until they hit production.
- 🔑 VPC-SC operates at the API/service level, distinct from network-layer firewall rules, and is a second independent layer on top of (not a replacement for) correct IAM.
- 🔑 GCP's exfiltration-first design is a genuine differentiator versus AWS's VPC Endpoints + SCPs and Azure's Private Link + policy, which achieve comparable protection only by deliberately combining several separate features.

## Related Concepts

IAM Fundamentals ([Section 35](./Section-35-Part5-IAM-Fundamentals-Members-Roles-Policies.md)), Organization Policies ([Section 37](./Section-37-Part5-Organization-Policies.md)), Compliance & Governance and Cloud Audit Logs ([Section 40](./Section-40-Part5-Compliance-Governance.md)), Security Command Center ([Section 39](./Section-39-Part5-Security-Command-Center.md)), Cloud Identity & BeyondCorp ([Section 42](./Section-42-Part5-Cloud-Identity-BeyondCorp.md)), and networking fundamentals (Part 3) all connect to the perimeter concepts introduced here.
