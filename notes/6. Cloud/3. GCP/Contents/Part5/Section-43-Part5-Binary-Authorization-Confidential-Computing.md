# Section 43 (Part 5): Binary Authorization & Confidential Computing — Part 5 Wrap-Up

## 1. Definition

**Plain language:** Two remaining gaps close out Part 5's security coverage. First: how do you make sure only container images that have actually passed your security scanning and CI pipeline are ever allowed to run in production — not just images you _intended_ to deploy, but a technical guarantee that unsigned or unapproved images are rejected? Second: everything covered so far protects data at rest (Section 38's KMS/CMEK) and in transit (TLS), but what protects data _while it's actively being processed in memory_ — from, say, a compromised hypervisor or a malicious cloud operator? Binary Authorization answers the first; Confidential Computing answers the second.

**Precise:** **Binary Authorization** is a deploy-time security control for GKE and Cloud Run that enforces a policy requiring container images to carry specific cryptographic **attestations** — signed statements that a defined process (e.g., a vulnerability scan, a QA sign-off) was completed — before the platform will allow the image to run, verified against configured **attestors**. **Confidential Computing** extends encryption to data **in use** (in memory, during processing) via **Confidential VMs** and **Confidential GKE Nodes**, using hardware-based memory encryption (AMD SEV) so that even privileged access to the underlying host cannot read a workload's in-memory data.

## 2. Why It Exists

Even with a secure CI/CD pipeline, hardened images, and correct IAM, nothing technically stops someone (a compromised credential, a rushed manual deploy, a misconfigured pipeline stage) from deploying an image that skipped vulnerability scanning, was never signed off by QA, or was pulled from an untrusted registry — the pipeline's security controls are only as strong as their _enforcement_, and enforcement that lives entirely in process/culture rather than the platform itself can always be bypassed under pressure. Binary Authorization exists to make policy compliance a hard technical gate at deploy time, not a convention — the platform itself refuses to run an image that lacks the required signed attestations, regardless of who's trying to deploy it or how.

Confidential Computing exists because "encrypted at rest, encrypted in transit" leaves one gap: the moment data is decrypted for processing, it exists in plaintext in the VM's memory, and traditional virtualization means the hypervisor (and, by extension, anyone with sufficiently privileged access to the physical host) can theoretically inspect that memory. For workloads with the highest sensitivity requirements — regulated data, multi-party computation where even the infrastructure provider shouldn't see the data, highly regulated industries — this is an unacceptable residual risk. Confidential Computing closes it by encrypting memory itself at the hardware level, so plaintext data never exists outside the CPU's protected boundary, even to the host system.

## 3. Binary Authorization

### 3.1 Attestors and Attestations

An **attestor** represents a specific verification step (e.g., "passed vulnerability scanning," "approved by QA") and holds the public key(s) used to verify signatures on **attestations** — a signed statement, tied to a specific container image digest, confirming that step was completed for that exact image. A Binary Authorization **policy** then specifies which attestors' signatures are _required_ before an image may be deployed — commonly, a policy might require both a "build provenance" attestation (came from the trusted CI pipeline) and a "vulnerability scan passed" attestation before allowing deployment to a production cluster.

### 3.2 Enforcement Modes

- **Dry-run mode** — like VPC Service Controls (Section 41), Binary Authorization supports a mode that logs what _would_ be blocked without actually blocking it, letting a team validate a new policy against real deployment traffic before enforcing.
- **Enforced mode** — deployments lacking the required attestations are rejected by GKE/Cloud Run at deploy time, with the rejection itself recorded in Cloud Audit Logs.

### 3.3 Relationship to the CI/CD Pipeline

Binary Authorization doesn't perform the scanning or QA sign-off itself — it verifies that _attestations produced elsewhere_ (a vulnerability scanner integrated into the CI pipeline, an automated or manual QA gate) are present and validly signed. This means the actual security work (running the scan, doing the review) still happens in the pipeline; Binary Authorization is the enforcement backstop ensuring that work can't be silently skipped for a given deployment.

## 4. Confidential Computing

### 4.1 Confidential VMs

A **Confidential VM** is a Compute Engine VM type where memory is encrypted in hardware using **AMD Secure Encrypted Virtualization (SEV)**, with a unique per-VM encryption key generated and managed entirely within the AMD Secure Processor — not accessible to the hypervisor, Google's own infrastructure, or any other tenant. This provides **encryption in use**, closing the gap left by at-rest and in-transit encryption, with only a modest performance overhead compared to a standard VM and no application code changes required.

### 4.2 Confidential GKE Nodes

**Confidential GKE Nodes** apply the same memory-encryption guarantee to the underlying nodes of a GKE cluster, so workloads running in pods on those nodes get in-use memory protection without any change to the containerized application itself — the encryption operates below the container/Kubernetes layer entirely.

> ⚠️ **Interview-relevant nuance:** Confidential Computing protects against a different threat model than CMEK/Secret Manager — CMEK and Secret Manager protect data at rest against unauthorized _access_ (via IAM, key control); Confidential Computing protects data _in use_ against a privileged infrastructure-level observer (a compromised hypervisor, a malicious insider with host access) who would otherwise be able to read plaintext memory even without any IAM or key-level access at all. These are complementary, not overlapping, controls.

## 5. Comparison with AWS and Azure

| Concept                                      | GCP                       | AWS                                                                        | Azure                                                        |
| -------------------------------------------- | ------------------------- | -------------------------------------------------------------------------- | ------------------------------------------------------------ |
| Deploy-time image attestation enforcement    | Binary Authorization      | ECR image scanning + Signer (weaker native enforcement gate)               | Azure Policy for AKS + Notary/Ratify-based admission control |
| Confidential VM (hardware memory encryption) | Confidential VM (AMD SEV) | Nitro Enclaves (isolated compute, different model) / AMD SEV-SNP instances | Azure Confidential Computing VMs (AMD SEV-SNP / Intel TDX)   |
| Confidential Kubernetes nodes                | Confidential GKE Nodes    | Nitro Enclaves used alongside EKS (not a direct node-level equivalent)     | Azure Confidential Computing on AKS                          |

## 6. Hands-On Example: Requiring an Attestation for GKE Deployment

**Purpose:** Create an attestor, sign an image, and enable a Binary Authorization policy requiring that attestation before deployment.

```bash
gcloud container binauthz attestors create vuln-scan-attestor \
  --attestation-authority-note=projects/my-project/notes/vuln-scan-note \
  --attestation-authority-note-project=my-project

gcloud beta container binauthz attestations sign-and-create \
  --artifact-url="gcr.io/my-project/my-app@sha256:abcd1234..." \
  --attestor=vuln-scan-attestor \
  --keyversion=projects/my-project/locations/global/keyRings/binauthz/cryptoKeys/sign-key/cryptoKeyVersions/1

gcloud container binauthz policy import policy.yaml
```

**Expected output (abbreviated):**

```
Created attestor [vuln-scan-attestor].
Created attestation for artifact [gcr.io/my-project/my-app@sha256:abcd1234...].
Updated policy.
```

**Attempting to deploy an unsigned image (blocked in enforced mode):**

```
ERROR: admission webhook denied the request: Image
gcr.io/my-project/my-app@sha256:eeee5678... denied by
attestor projects/my-project/attestors/vuln-scan-attestor:
no valid attestations found
```

## 7. Production & Enterprise Usage

- **Binary Authorization as the non-bypassable pipeline gate.** Enterprises with strict change-management or regulatory requirements (e.g., SOX-relevant deployments, healthcare workloads) use Binary Authorization to ensure that even a well-meaning engineer with valid GKE deploy permissions physically cannot push an image that skipped required scanning or approval — turning a policy into an enforced technical control rather than a trust-based process.
- **Confidential Computing for the most sensitive processing workloads.** Rather than applying Confidential VMs universally (unnecessary overhead for most workloads), organizations reserve it for specific workloads with the highest in-use data sensitivity — multi-party analytics, regulated healthcare/financial processing, or contractual requirements that even the cloud provider's infrastructure staff be unable to access plaintext data.
- **Combining both as the capstone of a defense-in-depth deployment pipeline.** A mature enterprise pattern: CMEK-encrypted data at rest (Section 38), VPC-SC perimeter around data services (Section 41), IAP/Context-Aware Access at the front door (Section 42), Binary Authorization gating what can even run, and Confidential Computing for the highest-sensitivity workloads' runtime — each control independently addressing a distinct point in the system, none substituting for another.

## 8. Common Misconceptions

- **Misconception:** "Binary Authorization scans images for vulnerabilities." It doesn't scan anything itself — it verifies that attestations (produced by a separate scanning/QA process) are present and validly signed before allowing deployment; the actual scanning is a different tool (e.g., Artifact Registry vulnerability scanning) feeding into it.
- **Misconception:** "Confidential Computing is just stronger disk encryption." It specifically protects data _in use_ (in memory during processing) via hardware-level memory encryption — a fundamentally different protection than at-rest disk encryption (CMEK) or in-transit TLS, addressing a threat model (privileged host-level access to live memory) neither of those covers.
- **Misconception:** "Enabling Confidential VM requires rewriting my application." It does not — the memory encryption operates transparently below the OS/application layer; existing workloads generally run unmodified on Confidential VMs, with only a modest performance overhead.

## 9. Part 5 Consolidated Knowledge Map

```
                         IAM & SECURITY (Part 5)
                                    │
   ┌────────────┬─────────────┬─────┴─────┬─────────────┬─────────────┐
   │            │             │           │             │             │
§35 IAM       §36 Service  §37 Org      §38 Secret    §39 Security  §40 Compliance
Fundamentals  Accounts     Policies     Manager &     Command       & Governance
Members/      Non-human    Preventive   Cloud KMS     Center        Assured Wkld,
Roles/        identities,  guardrails,  Secrets +     Findings      Access Trans/
Policies      keys, WI     constraints  encryption    aggregator    Approval, logs
                                    │
                    ┌───────────────┼───────────────┐
                 §41 VPC          §42 Cloud       §43 Binary Auth &
                 Service          Identity &      Confidential Computing
                 Controls         BeyondCorp      Deploy-time gating +
                 Exfiltration     Zero-trust      in-use encryption
                 perimeter        access model    (this section)
```

**Throughline:** §35–37 establish who/what can act and what guardrails constrain them. §38 protects secrets and data at rest. §39–40 detect problems and prove compliance. §41–42 control data movement and access at the perimeter and application layer. §43 closes the loop — gating what's allowed to run at all, and protecting the most sensitive workloads' data even while actively in use. Every section adds an independent, non-substitutable layer.

## 10. Part 5 Interview Drill

**🟢 A service account key was leaked publicly on GitHub. Which Part 5 controls does this incident touch, and in what order would you respond?**
Immediately disable/delete the compromised key (Section 36) and audit what IAM roles it held (Section 35). Check Cloud Audit Logs — specifically Data Access logs (Section 40) — for any usage of that key since exposure, to determine actual blast radius. If the key had access to sensitive data stores protected by a VPC Service Controls perimeter (Section 41), confirm whether any exfiltration attempt was blocked or succeeded. Review Security Command Center (Section 39) for any related findings or Event Threat Detection alerts. Long-term: this is exactly the scenario Section 36 argues against long-lived keys for — migrate the workload to Workload Identity Federation or attached service account identity instead of a downloadable key entirely.

**🟢 How do Org Policies (Section 37) and Binary Authorization (Section 43) both act as deploy-time guardrails, and how do they differ?**
Both are preventive, technical (not process-based) controls enforced automatically rather than relying on review discipline. Org Policy constraints restrict _what configurations_ are allowed at the resource level (e.g., disallowing public IPs, restricting which regions resources can be created in) — broad, resource-shape governance. Binary Authorization restricts _what container images_ are allowed to run, based on cryptographic proof of a required process having been completed — narrow, deployment-artifact-specific governance. Neither substitutes for the other; a fully locked-down region policy says nothing about whether a deployed image passed a vulnerability scan.

**🟡 Design the minimum set of Part 5 controls for a startup's first production GCP environment with a small team and limited security headcount.**
Start with the foundational, low-effort-high-value layer: correctly scoped IAM roles using predefined roles over primitive ones (Section 35), Workload Identity Federation instead of downloadable service account keys wherever possible (Section 36), and a small set of high-value Org Policy constraints (disable service account key creation, restrict public IP creation) (Section 37). Enable Secret Manager for all credentials from day one rather than environment variables (Section 38) — cheap and prevents a common early mistake. Enable Security Command Center Standard (free) for baseline visibility (Section 39), and ensure Admin Activity/System Event audit logs are being retained appropriately, adding Data Access logs on the most sensitive data store even at this stage (Section 40). VPC Service Controls, Binary Authorization, and Confidential Computing (Sections 41, 43) are reasonable to defer until the team has more data sensitivity, compliance requirements, or headcount to operate them well — they add real operational overhead that isn't justified for every early-stage environment.

**🟡 A compromised employee laptop is used to attempt access to an internal GCP-hosted admin tool. Walk through how Section 42's controls would (or wouldn't) stop this.**
If the tool is behind Identity-Aware Proxy with a Context-Aware Access level requiring a managed, compliant device, the compromise itself matters: if the laptop is still reporting as "managed and compliant" (encryption on, screen lock on, not yet flagged), the attacker inherits the legitimate context signals and IAP would not block on device posture alone — identity/credential-level protections (MFA, session risk signals from the federated IdP) become the operative defense at that point. If the compromise has caused the device to fall out of compliance (e.g., disk encryption disabled, unusual location breaking an IP-range condition), Context-Aware Access would deny access even with valid credentials. This illustrates that Context-Aware Access is a meaningful additional signal, not a silver bullet — it's one layer among several (strong auth, IAM scoping, monitoring) rather than a complete answer on its own.

**🔴 Design the full Part 5 security posture for a healthcare startup processing PHI on GCP, from IAM through runtime protection.**
Identity: Cloud Identity federated with the company's IdP, group-based IAM role assignment following least privilege, no primitive roles (Section 35). Workloads use attached service account identity or Workload Identity Federation exclusively — no long-lived keys (Section 36). Org Policy constraints enforce baseline hygiene org-wide: no public IPs, no service account key creation, restricted resource locations for data residency (Section 37). All PHI encrypted at rest with CMEK, HSM-backed given the regulatory sensitivity, per-environment key rings with admin/user role separation (Section 38). Security Command Center Premium enabled at the org level for full detection coverage and compliance reporting mapped to HIPAA-relevant controls (Section 39). A signed BAA with Google, Data Access audit logs explicitly enabled on every PHI-touching service, aggregated log sinks to a security-owned project, Access Approval enabled given the sensitivity (Section 40). A VPC Service Controls perimeter around every project touching PHI, in dry-run first, then enforced, to prevent exfiltration even from a compromised but validly-permissioned credential (Section 41). Internal admin tools behind IAP with Context-Aware Access requiring managed/compliant devices; IAP TCP forwarding replacing any VPN/bastion access entirely (Section 42). Binary Authorization enforced on the GKE clusters processing PHI, requiring vulnerability-scan and QA attestations before any deploy; Confidential GKE Nodes for the specific workloads processing raw PHI in memory, given the regulatory and contractual sensitivity of even infrastructure-level access to that data (Section 43). Every layer is independently necessary — none substitutes for another, and the design assumes any single layer can eventually fail or be bypassed, which is precisely why there are this many of them.

## 11. 🔑 Part 5 — Final Consolidated Key Takeaways

- 🔑 IAM (Section 35) and service accounts (Section 36) establish who/what can act; Org Policies (Section 37) constrain what configurations are even possible, regardless of IAM — prevention operating at two different layers.
- 🔑 Secret Manager and Cloud KMS (Section 38) protect secrets and data at rest, with CMEK enabling customer-controlled, revocable encryption independent of IAM changes.
- 🔑 Security Command Center (Section 39) aggregates detection across the organization; Compliance & Governance tooling (Section 40) proves controls are working and governs Google's own access to customer data.
- 🔑 VPC Service Controls (Section 41) and Cloud Identity/BeyondCorp (Section 42) control data movement and application access respectively, both operating on a zero-trust, context-aware basis rather than trusting network location or IAM alone.
- 🔑 Binary Authorization and Confidential Computing (Section 43) close Part 5 by gating what's allowed to run at all, and protecting the most sensitive workloads' data even while actively in use — no single Part 5 control is a substitute for any other; the whole Part is one continuous, layered defense-in-depth argument.

## ✅ Part 5 Complete

All nine sections of **IAM & Security** are done — from foundational identity (Section 35) through runtime protection of the most sensitive workloads (Section 43). Next: **Part 6 — Data & Analytics** (Section 44 onward), covering BigQuery's architecture and query engine, Dataflow and stream/batch processing, Pub/Sub messaging, Dataproc for Spark/Hadoop workloads, and the broader data platform GCP is best known for — building on the secure, governed foundation this Part established, since every data pipeline and warehouse covered next inherits the IAM, encryption, and access-control patterns introduced here.

## Related Concepts

IAM Fundamentals (Section 35), Service Accounts (Section 36), Secret Manager & Cloud KMS (Section 38), Security Command Center (Section 39), VPC Service Controls (Section 41), GKE Security & Workload Identity (Section 33), and BigQuery/data platform security (Part 6) all connect directly to the deploy-time and runtime protection concepts introduced here.
