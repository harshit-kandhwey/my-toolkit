# Section 36 (Part 5): Service Accounts

## 36.1 Definition

**Plain language:** A service account is a special kind of identity for machines, not people. When a VM, a container, or a script needs to call a GCP API — read a bucket, write to a database — it authenticates as a service account rather than as a human user, since there's no human sitting at a keyboard to type a password.

**Precise:** A **service account** is a non-human IAM principal (Section 35) belonging to a project, identified by an email-like address (`name@project-id.iam.gserviceaccount.com`), which workloads use to authenticate to GCP APIs. Like any principal, IAM roles can be bound to a service account, and — distinctively — a service account can itself be granted roles that let other principals **use** or **impersonate** it, and can be **attached** to compute resources so that code running on them automatically authenticates as it.

## 36.2 Why It Exists

Applications and automated processes need to call GCP APIs, but granting them a human's credentials would be both insecure (a shared password/credential with no individual accountability) and operationally fragile (tied to a person who might leave the company). Service accounts exist to give workloads their own first-class, independently-managed identity with its own IAM bindings, its own credential lifecycle, and its own audit trail — decoupling application access from any specific human's account.

## 36.3 Core Concepts

### 36.3.1 Types of Service Accounts

| Type                               | Description                                                                                                                                                                                                                                                         |
| ---------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **User-managed service account**   | Explicitly created by a user within a project for a specific application/workload. The standard choice for application identities.                                                                                                                                  |
| **Default service account**        | Automatically created by certain services (e.g., Compute Engine, App Engine) when first used, historically over-privileged (Compute Engine default SA traditionally received `Editor`) — a well-known security anti-pattern that modern deployments actively avoid. |
| **Google-managed service account** | Created and managed by Google itself to allow a Google service to act on your behalf (e.g., the GKE service agent). Not user-manageable.                                                                                                                            |

### 36.3.2 Authentication: Keys vs. Short-Lived Credentials

A service account can authenticate in two fundamentally different ways:

- **Service account keys** — a downloadable JSON (or P12) file containing a long-lived private key. Whoever holds the file can authenticate as that service account indefinitely (until the key is revoked). Keys are a significant, well-documented security liability: they can be leaked in source control, logs, or laptops, they don't expire by default, and a leaked key grants full access with no built-in time bound.
- **Short-lived credentials (recommended)** — obtained dynamically without ever creating a downloadable key:
  - **Attached identity:** Compute Engine, GKE, Cloud Run, and Cloud Functions can automatically supply short-lived tokens to code running on them via the metadata server, with no key file ever created (see 36.3.3).
  - **Workload Identity Federation:** external workloads (on-prem, AWS, Azure, CI/CD systems) exchange their own identity token for a short-lived GCP credential without any GCP service account key at all.
  - **Impersonation:** a human or another service account with the right permission can request a short-lived token _as_ a target service account, without ever holding its key (see 36.3.4).

> ⚠️ **Interview-relevant nuance:** Google's own security guidance is to avoid creating service account keys entirely wherever possible — nearly every legitimate use case (compute workloads, CI/CD, cross-service calls) has a short-lived-credential alternative. Org Policy constraints (Section 37) can enforce this by disabling key creation outright.

### 36.3.3 Attaching Service Accounts to Compute Resources

- **Compute Engine:** a VM instance has exactly one attached service account plus a set of OAuth **scopes** limiting which API surfaces the metadata-server-issued token can be used for; IAM roles bound to the service account provide the actual authorization, with scopes as an additional (mostly legacy) restriction layer.
- **GKE (Workload Identity):** rather than attaching one node-level service account to every Pod on a node (over-broad and hard to audit per-workload), **Workload Identity** (covered in depth in Section 33) lets individual Kubernetes Service Accounts impersonate specific GCP service accounts, so each workload gets its own least-privilege GCP identity without any key ever existing on the node. This is the modern replacement for the older, deprecated "metadata concealment" approach to node-level SA isolation.
- **Cloud Run / Cloud Functions:** each revision/function specifies a runtime service account directly; short-lived credentials are issued automatically to the running instance with no additional configuration.

### 36.3.4 Impersonation

**Service account impersonation** lets a principal (a human or another service account) temporarily act as a service account without holding its key, provided they hold the `roles/iam.serviceAccountTokenCreator` role on that service account. This is the recommended pattern for local development, CI/CD pipelines, and any human debugging that needs to test "as the application" — the impersonating identity's own access is audited via Cloud Audit Logs (Section 40) alongside the impersonation event itself, preserving accountability that a shared key would destroy.

```bash
gcloud auth print-access-token --impersonate-service-account=app-sa@my-project.iam.gserviceaccount.com
```

## 36.4 Architecture Diagram

```
        HUMAN / CI PIPELINE                    GKE POD                     COMPUTE ENGINE VM
              │                                    │                              │
     roles/iam.serviceAccountTokenCreator   Kubernetes SA bound via       Attached service account
     granted on target SA                   Workload Identity to a        (metadata server issues
              │                             specific GCP SA               short-lived tokens)
              ▼                                    │                              │
     ┌───────────────────┐                         ▼                              ▼
     │ Short-lived token │◄──────────────  ┌───────────────────────────────────────┐
     │ "as" app-sa@...   │                 │        SERVICE ACCOUNT: app-sa@...    │
     └───────────────────┘                 │  IAM roles bound directly to this SA  │
                                           │  (e.g., roles/storage.objectViewer)   │
                                           └───────────────────────────────────────┘
                                                              │
                                                              ▼
                                                   GCP API calls authorized
                                                   as app-sa@..., NOT as any
                                                   human identity
```

## 36.5 Comparison with AWS and Azure

| Concept                       | GCP                                          | AWS                                                     | Azure                                                                     |
| ----------------------------- | -------------------------------------------- | ------------------------------------------------------- | ------------------------------------------------------------------------- |
| Workload identity primitive   | Service account                              | IAM Role (assumed via STS)                              | Managed Identity                                                          |
| Long-lived credential risk    | Service account key (JSON/P12) — discouraged | Long-lived access key pair on an IAM user — discouraged | Client secret / certificate on a Service Principal — discouraged          |
| Attaching identity to compute | Attached SA + metadata server                | Instance Profile → Role                                 | System-assigned / User-assigned Managed Identity                          |
| Kubernetes-native binding     | Workload Identity (Section 33)               | IAM Roles for Service Accounts (IRSA)                   | Azure AD Workload Identity for AKS                                        |
| Temporary "act as" mechanism  | Impersonation (`serviceAccountTokenCreator`) | `sts:AssumeRole`                                        | Managed Identity token acquisition (no true cross-identity impersonation) |
| External workload federation  | Workload Identity Federation                 | IAM Roles Anywhere / OIDC federation                    | Workload Identity Federation for Azure AD                                 |

## 36.6 Hands-On Example: Creating and Attaching a Service Account

**Purpose:** Create a dedicated, least-privilege service account for an application and attach it to a new VM — the standard alternative to relying on the over-privileged default Compute Engine service account.

```bash
gcloud iam service-accounts create app-sa \
  --display-name="Application Service Account"

gcloud projects add-iam-policy-binding my-project-id \
  --member="serviceAccount:app-sa@my-project-id.iam.gserviceaccount.com" \
  --role="roles/storage.objectViewer"

gcloud compute instances create app-vm \
  --service-account=app-sa@my-project-id.iam.gserviceaccount.com \
  --scopes=cloud-platform \
  --zone=us-central1-a
```

**Expected output (abbreviated):**

```
Created service account [app-sa].
Updated IAM policy for project [my-project-id].
NAME    ZONE           MACHINE_TYPE   STATUS
app-vm  us-central1-a  e2-medium      RUNNING
```

> 💡 **Tip:** `--scopes=cloud-platform` combined with IAM roles bound to the service account is the modern recommended pattern — it delegates all fine-grained authorization to IAM roles rather than juggling narrow, service-specific OAuth scopes, which is the older and less flexible model.

## 36.7 Production & Enterprise Usage

- **One service account per application/workload, never shared broadly.** Enterprises provision a dedicated service account per microservice or job, scoped to exactly the roles that workload needs, rather than reusing a single "project-wide" service account across many unrelated workloads.
- **Key creation disabled by Organization Policy.** Mature organizations enforce `constraints/iam.disableServiceAccountKeyCreation` (Section 37) org-wide, forcing every team onto attached identities, Workload Identity, or impersonation instead of downloadable keys.
- **Automated key rotation/monitoring where keys are unavoidable.** For the rare legitimate case requiring a key (e.g., an external SaaS integration with no federation support), enterprises enforce short key lifetimes, automated rotation, and continuous monitoring for key usage anomalies via Security Command Center (Section 39).

## 36.8 Common Misconceptions

- **Misconception:** "A service account key is required to run code on GCP." The overwhelming majority of workloads (anything on Compute Engine, GKE, Cloud Run, Cloud Functions) never need a key at all — attached identity and Workload Identity issue credentials automatically.
- **Misconception:** "Impersonation is less secure than using a key directly." Impersonation is generally more secure: tokens are short-lived, no long-lived secret exists to leak, and every impersonation event is individually attributable and logged, unlike a shared key which grants indefinite, less-attributable access to whoever holds it.
- **Misconception:** "The default Compute Engine service account is fine to use for production workloads." The default service account has historically been granted the broad `Editor` role on the project by default in many configurations, violating least privilege; production workloads should always use a dedicated, narrowly-scoped user-managed service account.

## 36.9 Interview Questions

**🎯 Beginner:** _What is a GCP service account, and how is it different from a regular user account?_
**Model answer:** A service account is a non-human IAM identity used by applications, VMs, and automated processes to authenticate to GCP APIs, whereas a regular Google Account represents an individual human. Both can be granted IAM roles, but service accounts are the recommended identity for any workload, since using a human's credentials for an application would be both insecure and operationally fragile.

**🎯 Intermediate:** _Why is Workload Identity preferred over attaching a single service account to every node in a GKE cluster?_
**Model answer:** A single node-level service account is shared by every Pod scheduled on that node, meaning any workload on the node effectively has that service account's full permissions — a violation of least privilege and a poor audit trail, since it's unclear which Pod actually used which permission. Workload Identity lets each Kubernetes Service Account impersonate a distinct GCP service account scoped to exactly that workload's needs, with no service account key ever stored on the node, giving both least privilege and precise per-workload auditability.

**🎯 Senior/Architect:** _Your organization has dozens of service account keys scattered across CI/CD systems and third-party integrations, several of which are years old. How would you remediate this and prevent recurrence?_
**Model answer:** First I'd inventory every existing key using `gcloud iam service-accounts keys list` across all projects (or Cloud Asset Inventory for org-wide visibility) and cross-reference against Security Command Center findings for unused or old keys. For CI/CD systems, I'd migrate to Workload Identity Federation so pipelines exchange their own OIDC tokens for short-lived GCP credentials, eliminating the key entirely. For internal workloads on Compute Engine/GKE/Cloud Run, I'd migrate to attached identity or Workload Identity respectively. For genuinely external third-party integrations with no federation support, I'd rotate to fresh, narrowly-scoped keys with the shortest practical lifetime and monitoring alerts on their usage. Finally, to prevent recurrence, I'd enforce the `iam.disableServiceAccountKeyCreation` Organization Policy constraint org-wide (Section 37), with a documented, audited exception process for the rare legitimate case, so new keys can't silently reappear.

## 🔑 Key Takeaways

- 🔑 Service accounts are non-human IAM identities for workloads; like any principal they can hold IAM role bindings and be the target of other principals' access.
- 🔑 Short-lived credentials (attached identity, Workload Identity, impersonation, Workload Identity Federation) are strongly preferred over downloadable service account keys, which are long-lived and a major, well-documented leak risk.
- 🔑 Workload Identity (Section 33) is the GKE-native mechanism binding individual Kubernetes Service Accounts to specific GCP service accounts, replacing shared node-level identities.
- 🔑 Impersonation lets a principal act as a service account temporarily and auditably without ever holding its key, and is the recommended pattern for human/CI access needs.
- 🔑 GCP service accounts map conceptually to AWS IAM Roles and Azure Managed Identities, though GCP's key-based long-lived credential option (and its associated risk) has no precise Azure equivalent, since Managed Identities never expose a downloadable secret at all.

## Related Concepts

IAM fundamentals (Section 35), GKE Security & Workload Identity (Section 33), Organization Policies (Section 37), Secret Manager & Cloud KMS (Section 38), and Cloud Audit Logs (Section 40) all build directly on the service account model introduced here.
