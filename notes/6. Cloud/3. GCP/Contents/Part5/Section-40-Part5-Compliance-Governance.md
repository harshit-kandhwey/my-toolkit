# Section 40 (Part 5): Compliance & Governance

## 40.1 Definition

**Plain language:** Regulated organizations don't just need their cloud environment to be secure — they need to be able to _prove_ it's secure, in the specific way an auditor, regulator, or contract requires, and they often need to prevent even Google's own support staff from seeing certain data. This section covers the tools GCP provides for exactly that: enforcing compliance boundaries, controlling and observing Google's own access, and keeping an immutable record of what happened.

**Precise:** GCP's compliance and governance tooling spans **Assured Workloads** (policy-enforced compliance regimes for regulated workloads), third-party **compliance certifications** GCP itself holds, **Access Transparency** and **Access Approval** (visibility into and control over Google personnel access to customer data), and **Cloud Audit Logs** (an immutable record of administrative actions, data access, and system events across an organization).

## 40.2 Why It Exists

Compliance requirements come from two different directions that are easy to conflate. First, _your organization's_ controls need to be provably compliant with a framework (HIPAA, FedRAMP, PCI-DSS, ITAR) — this requires both configuring your resources correctly and having auditable evidence that they stay that way. Second, in a shared-responsibility public cloud model, _Google's own operational access_ to the infrastructure underlying your workloads is itself part of the compliance surface — an auditor for a government or defense workload may require proof that no Google engineer without appropriate clearance ever touched the underlying hardware, or a visibility log of every time any Google support engineer did access anything related to your resources. GCP's compliance tooling exists to make both of these provable rather than merely asserted.

## 40.3 Assured Workloads

**Assured Workloads** is a control plane that lets an organization designate a folder as subject to a specific compliance regime (e.g., FedRAMP Moderate/High, IL4/IL5 for US Department of Defense, CJIS, HIPAA, or EU data boundary requirements), and then automatically enforces the technical controls that regime requires — such as restricting resource creation to specific compliant regions, restricting support access to personnel with appropriate citizenship/clearance, enforcing CMEK (Section 38) on supported services, and blocking creation of services not yet certified for that regime.

> 💡 **Tip:** Assured Workloads is best understood as "compliance-as-a-guardrail," conceptually similar to a highly specialized, pre-packaged Organization Policy (Section 37) bundle — instead of an org handcrafting dozens of individual constraints to approximate a framework's requirements, Assured Workloads applies Google's own maintained mapping of "what technical controls this specific regime requires" directly to a folder.

## 40.4 Compliance Certifications Overview

GCP maintains certifications and attestations across a broad set of frameworks, independently audited by third parties. Understanding the _category_ of each matters more than memorizing the full list:

| Category                     | Examples                                                                    | What it demonstrates                                                                                                            |
| ---------------------------- | --------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| General security/operational | ISO 27001, SOC 1/2/3                                                        | Independently audited security, availability, and confidentiality controls over Google's infrastructure and processes.          |
| Payment industry             | PCI DSS                                                                     | Controls suitable for environments processing cardholder data.                                                                  |
| Healthcare                   | HIPAA (via signed Business Associate Agreement, not a certification per se) | GCP services covered under a BAA can be used to process Protected Health Information (PHI) under a shared-responsibility model. |
| Government (US)              | FedRAMP Moderate/High, DoD IL2–IL5                                          | Suitability for US federal government and defense workloads at specified sensitivity levels.                                    |
| Regional/sector-specific     | ENS High (Spain), C5 (Germany), IRAP (Australia)                            | Suitability against a specific country or sector's regulatory framework.                                                        |

> ⚠️ **Interview-relevant nuance:** A certification held by _Google's infrastructure_ does not automatically make _your workload_ compliant — you must still configure and operate your portion of the shared-responsibility model correctly (encryption, access control, logging, data residency) to inherit the benefit of the underlying certification. Auditors evaluate your configuration against the framework; Google's certification is necessary but not sufficient evidence on its own.

## 40.5 Access Transparency and Access Approval

These two features are frequently confused but serve distinct purposes:

- **Access Transparency** provides **near-real-time logs** whenever Google personnel access your content in the course of providing support or resolving an issue — recording who accessed what, why (linked to a support case or other justification), and when. This is passive visibility: you see it happened, after (or as) it happens.
- **Access Approval** goes further: it requires **explicit customer approval** _before_ Google personnel can access your content for a specific reason, giving the customer a real-time veto rather than only visibility. This is the stronger control, typically required by the most sensitive regulated workloads (e.g., certain government contracts).

```
                     Google Support Engineer needs to access
                     customer resource to resolve a support case
                                    │
                                    ▼
                    ┌───────────────────────────────┐
                    │   ACCESS APPROVAL ENABLED?    │
                    └───────────────┬───────────────┘
                         NO         │         YES
                    ┌───────────────┴────────────────┐
                    ▼                                ▼
        Access proceeds,                    Customer notified, must
        logged via                          explicitly APPROVE before
        Access Transparency                  access is granted
        (visibility only,                    (Access Approval —
         after the fact)                      real veto power, before
                                               the fact)
```

## 40.6 Cloud Audit Logs

Cloud Audit Logs record activity across an organization in four distinct log streams, each with different retention and cost characteristics:

### 40.6.1 The Four Log Types

| Log type           | Records                                                                                                                                            | Retention                         | Enabled by default?                                                                                                                |
| ------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| **Admin Activity** | Actions that modify resource configuration or metadata (creating a VM, changing an IAM policy, deleting a bucket).                                 | 400 days                          | Yes, always on, cannot be disabled                                                                                                 |
| **Data Access**    | Reads/writes of user-provided data itself (reading a BigQuery row, accessing a secret's value).                                                    | 30 days by default (configurable) | No for most services (except BigQuery Data Access, which is default-on); must be explicitly enabled per-service due to volume/cost |
| **System Event**   | Google Cloud system actions that modify resource configuration, not initiated by a user (e.g., live migration of a VM by Google's infrastructure). | 400 days                          | Yes, always on, cannot be disabled                                                                                                 |
| **Policy Denied**  | Requests denied due to a security policy violation (e.g., an Org Policy constraint or VPC Service Controls perimeter blocking an action).          | 400 days                          | Yes, on by default for supported services                                                                                          |

> ⚠️ **Interview-relevant nuance:** Data Access logs are the ones most often _missing_ when an incident investigation needs them, precisely because they're not universally on by default — the volume/cost trade-off means many organizations only discover they never enabled Data Access logging for a critical service after they need it during an investigation. Enabling Data Access logs proactively for sensitive data stores is a standard hardening recommendation, not an afterthought.

### 40.6.2 Where Logs Live and How They're Used

All four log types flow into **Cloud Logging**, from which they can be routed via log sinks to BigQuery (for SQL-based investigation), Cloud Storage (for long-term archival beyond the default retention), or Pub/Sub (for real-time processing, e.g., feeding a SIEM). Audit logs are themselves protected resources — access to _read_ audit logs is a distinct, separately grantable IAM permission from access to the resources the logs describe, so that even a resource owner doesn't automatically get to erase or hide their own audit trail.

## 40.7 Comparison with AWS and Azure

| Concept                                      | GCP                 | AWS                                                                                 | Azure                                                        |
| -------------------------------------------- | ------------------- | ----------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Compliance-regime-enforced workload boundary | Assured Workloads   | AWS GovCloud / Nitro-based compliance controls                                      | Azure Government / Azure confidential compliance offerings   |
| Provider-personnel-access visibility         | Access Transparency | CloudTrail does not natively expose AWS-staff access; largely covered contractually | Customer Lockbox (approval-based, closer to Access Approval) |
| Provider-personnel-access approval           | Access Approval     | No direct native equivalent                                                         | Customer Lockbox                                             |
| Admin/config change audit log                | Admin Activity logs | CloudTrail (management events)                                                      | Azure Activity Log                                           |
| Data plane access audit log                  | Data Access logs    | CloudTrail (data events, opt-in per resource)                                       | Diagnostic settings / resource-level logs (opt-in)           |
| Policy-violation denial log                  | Policy Denied logs  | CloudTrail + Config/SCP denial context                                              | Azure Policy compliance/deny logs                            |

## 40.8 Hands-On Example: Enabling Data Access Logs and Querying Audit Logs

**Purpose:** Enable Data Access audit logging for a service via an IAM policy audit config, then query recent Admin Activity logs for a project.

```bash
gcloud projects get-iam-policy my-project --format=json > policy.json
```

Add an `auditConfigs` block to `policy.json` (edited manually, then applied):

```json
{
  "auditConfigs": [
    {
      "service": "storage.googleapis.com",
      "auditLogConfigs": [
        { "logType": "DATA_READ" },
        { "logType": "DATA_WRITE" }
      ]
    }
  ]
}
```

```bash
gcloud projects set-iam-policy my-project policy.json

gcloud logging read \
  "logName=\"projects/my-project/logs/cloudaudit.googleapis.com%2Factivity\"" \
  --limit=5 --format="table(timestamp,protoPayload.methodName,protoPayload.authenticationInfo.principalEmail)"
```

**Expected output (abbreviated):**

```
Updated IAM policy for project [my-project].

TIMESTAMP                      METHOD_NAME                             PRINCIPAL_EMAIL
2026-07-24T10:15:22Z            google.iam.admin.v1.SetIamPolicy         alice@example.com
2026-07-24T09:58:03Z            v1.compute.instances.insert              deploy-sa@my-project.iam.gserviceaccount.com
```

## 40.9 Production & Enterprise Usage

- **Compliance boundary as a folder, not a project-by-project checklist.** Enterprises with regulated workloads place them under an Assured Workloads folder from day one, so every new project created underneath automatically inherits the required controls, rather than relying on every team remembering to configure each new project correctly.
- **Sink all four audit log types to a security-owned project.** Rather than trusting log retention/access controls in each workload project, mature organizations route audit logs via aggregated sinks to a centralized, security-team-owned project (with stricter IAM and longer retention via Cloud Storage/BigQuery), so a compromised workload project can't be used to tamper with its own audit trail.
- **Access Approval for the highest-sensitivity tenants only.** Because Access Approval can introduce support latency (Google support must wait for explicit approval before proceeding), it's typically scoped to the specific folders/projects holding the most sensitive data, rather than the entire organization, balancing compliance requirements against operational support speed elsewhere.

## 40.10 Common Misconceptions

- **Misconception:** "If Google is FedRAMP/HIPAA certified, my workload is automatically compliant." Google's certifications cover the underlying infrastructure and processes; your workload's compliance also depends on how you configure and operate it — encryption, access control, logging, data residency — under the shared-responsibility model.
- **Misconception:** "Access Transparency and Access Approval are the same feature at different tiers." They're functionally different: Transparency is passive after-the-fact visibility; Approval is an active, real-time veto required before access proceeds.
- **Misconception:** "All audit logs are on by default and retained forever." Only Admin Activity, System Event, and (for supported services) Policy Denied logs are on by default; most Data Access logs must be explicitly enabled, and default retention (30 days for Data Access) is shorter than for the always-on log types (400 days).

## 40.11 Interview Questions

**🎯 Beginner:** _What are the four types of Cloud Audit Logs, and which are enabled by default?_
**Model answer:** Admin Activity (configuration/resource changes), Data Access (reads/writes of actual data), System Event (Google-system-initiated changes), and Policy Denied (requests blocked by a security policy). Admin Activity, System Event, and Policy Denied are enabled by default and cannot be disabled (for Admin Activity/System Event) or are on by default for supported services (Policy Denied); most Data Access logs must be explicitly enabled per service due to their higher volume and cost.

**🎯 Intermediate:** _What's the difference between Access Transparency and Access Approval?_
**Model answer:** Access Transparency provides near-real-time logs showing when Google personnel accessed your content and why, but access still proceeds — it's visibility after (or as) the fact. Access Approval requires the customer to explicitly approve Google personnel access before it's granted, giving a real veto rather than only visibility, and is the stronger of the two controls typically required for the most sensitive regulated workloads.

**🎯 Senior/Architect:** _A defense contractor needs to run a DoD IL5 workload on GCP with full audit trail and explicit control over any Google support access. Design the governance approach._
**Model answer:** I'd create a dedicated folder designated as an Assured Workloads workload at the IL5 compliance regime, which automatically enforces the region restrictions, personnel-clearance restrictions, and CMEK requirements that regime mandates, rather than hand-building equivalent Org Policy constraints. I'd enable Access Approval on that folder so any Google support access requires explicit customer sign-off before proceeding, paired with Access Transparency logs as the durable record of every such access. For audit logging, I'd explicitly enable Data Access logs on every service touching sensitive data (not relying on defaults), and configure aggregated log sinks routing all four log types — Admin Activity, Data Access, System Event, Policy Denied — to a separate, security-team-owned project with restricted IAM and extended retention via Cloud Storage, so the workload's own compromise can't be used to tamper with its audit trail. I'd layer VPC Service Controls (Section 41) around the perimeter to prevent data exfiltration even by a compromised identity with valid IAM permissions, and CMEK (Section 38) with HSM-backed keys for encryption-at-rest control. Finally, I'd treat Security Command Center (Section 39) Premium findings and Policy Denied logs as continuous compliance-drift signals, since a compliance boundary approved at launch can silently erode as the workload evolves without ongoing monitoring.

## 🔑 Key Takeaways

- 🔑 Assured Workloads applies a pre-built bundle of technical controls matching a specific compliance regime to a folder, enforcing region, personnel, and encryption restrictions automatically.
- 🔑 Google's own certifications (ISO 27001, FedRAMP, HIPAA BAA, etc.) cover the infrastructure layer — your workload's compliance still depends on your own configuration under the shared-responsibility model.
- 🔑 Access Transparency is passive after-the-fact visibility into Google personnel access; Access Approval is an active, real-time veto required before that access proceeds — the latter is the stronger control.
- 🔑 Cloud Audit Logs has four types — Admin Activity and System Event are always on; Data Access is often not enabled by default and is the log most commonly missing during an incident investigation; Policy Denied records security-policy-blocked requests.
- 🔑 GCP's Access Approval maps most closely to Azure's Customer Lockbox; AWS has no precise native equivalent for pre-access customer veto over provider staff.

## Related Concepts

Organization Policies (Section 37), Secret Manager & Cloud KMS (Section 38), Security Command Center (Section 39), VPC Service Controls (Section 41), and Binary Authorization & Confidential Computing (Section 43) all build on or feed into the compliance and audit concepts introduced here.
