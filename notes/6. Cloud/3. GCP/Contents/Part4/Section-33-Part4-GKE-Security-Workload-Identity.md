# Section 33 (Part 4): GKE Security & Workload Identity

## 1. Definition

**Plain language:** Letting a Pod call other Google Cloud services (like reading from a Cloud Storage bucket) safely means giving it credentials — but handing every Pod on a node the same broad node-level credentials is like giving every tenant in an apartment building the landlord's master key. GKE's security model exists to give each workload exactly the identity and permissions it needs, nothing more, and to harden the nodes and cluster underneath it.

**Precise:** **Workload Identity** is GKE's mechanism for binding a Kubernetes **ServiceAccount (KSA)** to a GCP **IAM service account (GSA)**, letting Pods authenticate to Google Cloud APIs with fine-grained, workload-scoped IAM permissions instead of relying on node-level credentials. It works alongside **Shielded GKE Nodes** (boot integrity verification for the underlying VMs), **private clusters** (removing public IP exposure from nodes and, optionally, the control plane), and **Binary Authorization** (deploy-time image provenance enforcement, detailed in Section 43) as the core pillars of GKE's default security posture.

## 2. Why It Exists / Problem It Solves

Before Workload Identity, the standard way for a Pod to call a GCP API was to rely on the **node's** service account and its attached credentials, available to every Pod scheduled on that node via the Compute Engine metadata server. This has two serious problems: every Pod on a node effectively shares the same GCP permissions (violating least privilege), and any Pod capable of reaching the node's metadata server endpoint could potentially exfiltrate those node-level credentials and impersonate the node's identity — a well-known Kubernetes attack pattern across every cloud provider, not just GKE.

Workload Identity solves both problems by giving each Kubernetes ServiceAccount its own, distinct binding to a GCP service account, scoped with only the IAM permissions that specific workload needs, and by removing direct Pod access to the node's own credentials from the metadata server. Shielded Nodes and private clusters solve adjacent but different problems: verifying a node hasn't been tampered with at boot, and reducing the network attack surface nodes and the control plane expose to the public internet, respectively.

## 3. Workload Identity: How the Binding Works

Workload Identity connects three identities:

1. **Kubernetes ServiceAccount (KSA)** — a namespaced Kubernetes-native identity a Pod's spec references via `serviceAccountName`.
2. **GCP IAM Service Account (GSA)** — a GCP-native identity with IAM role bindings granting specific permissions (e.g., `roles/storage.objectViewer` on one bucket).
3. **The Workload Identity binding itself** — an IAM policy binding (`roles/iam.workloadIdentityUser`) on the GSA, granting a specific KSA (identified by `PROJECT_ID.svc.id.goog[NAMESPACE/KSA_NAME]`) permission to impersonate it, plus an annotation on the KSA pointing at the GSA.

Once bound, any Pod using that KSA automatically receives short-lived, automatically rotated credentials for the associated GSA when it calls Google Cloud client libraries or the metadata server — no static key files, no manually mounted service account JSON keys, and no node-level credential sharing.

> ⚠️ **Interview-relevant nuance:** Workload Identity replaces the older, now-discouraged pattern of mounting a downloaded GSA JSON key file as a Kubernetes Secret. That pattern creates a long-lived, exportable static credential sitting in `etcd` and potentially in container images or logs — exactly the kind of durable secret sprawl Workload Identity is designed to eliminate, since its credentials are short-lived and never touch disk as a static key.

## 4. Shielded GKE Nodes

**Shielded GKE Nodes** apply Compute Engine's Shielded VM protections to GKE nodes:

- **Secure Boot** — verifies the node's boot loader and kernel are signed and untampered before allowing boot, blocking boot-level rootkits.
- **vTPM (virtual Trusted Platform Module)** — measures the boot process and can attest to it, providing integrity monitoring.
- **Integrity monitoring** — compares a node's boot measurements against a known-good baseline and can alert on unexpected changes.

Shielded GKE Nodes are enabled by default for new clusters and mandatory (non-optional) in Autopilot mode (Section 32) as part of its hardened default posture; Standard-mode clusters should explicitly verify this setting rather than assume it, particularly for older clusters created before it became a default.

## 5. Private Clusters

A **private cluster** removes public IP addresses from nodes, the control plane, or both:

| Configuration                             | Node IPs                        | Control Plane Access                                                                                                              |
| ----------------------------------------- | ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| **Public cluster** (default historically) | Public or private, configurable | Public endpoint reachable from the internet (optionally restricted by authorized networks)                                        |
| **Private cluster, public endpoint**      | No public IPs — private only    | Public endpoint reachable from the internet, ideally restricted to specific CIDR ranges via **control plane authorized networks** |
| **Private cluster, private endpoint**     | No public IPs — private only    | No public endpoint at all — `kubectl` access requires being on the VPC (directly, via VPN/Interconnect, or a bastion)             |

Removing public IPs from nodes means Pods and nodes are reachable only via the internal VPC network (with a Cloud NAT gateway, Section 21, providing outbound internet access where needed), substantially shrinking the network attack surface compared to nodes with individually routable public IPs.

## 6. Binary Authorization (Forward Reference)

**Binary Authorization** is a deploy-time control that only allows container images meeting defined trust policies — such as being signed by a specific, trusted build pipeline — to actually be deployed to a GKE cluster, blocking anything else at admission time regardless of who tries to deploy it or how. It's the enforcement layer that ensures the image-provenance guarantees an organization's CI/CD pipeline establishes (Section 29's Artifact Registry image scanning, combined with signing) are actually honored at runtime, not just recommended. Binary Authorization is covered in full, alongside Confidential Computing, in **Section 43** (Part 5: IAM & Security) — it's introduced here because it's commonly deployed as one more layer of a GKE cluster's security posture alongside Workload Identity, Shielded Nodes, and private clusters.

## 7. Architecture Diagram

```
                     ┌────────────────────────────────────────────┐
                     │        GCP IAM                             │
                     │  GSA: storage-reader@project.iam...        │
                     │  roles/storage.objectViewer (one bucket)   │
                     │  roles/iam.workloadIdentityUser bound to ► │
                     └───────────────────┬────────────────────────┘
                                         │ Workload Identity binding
                                         ▼
        PRIVATE GKE CLUSTER (no public node IPs, Shielded Nodes on)
   ┌─────────────────────────────────────────────────────────────────┐
   │  Namespace: app                                                 │
   │  KSA: reader-ksa  ── annotated with GSA above                   │
   │        ▲                                                        │
   │        │ serviceAccountName: reader-ksa                         │
   │  ┌─────────────┐                                                │
   │  │  Pod        │── calls GCS API using short-lived GSA creds    │
   │  │             |  no node-level creds visible;                  │
   │  └─────────────┘       metadata server access scoped)           │
   │                                                                 │
   │ Node: Secure Boot verified, vTPM-measured, integrity-monitored  │
   └─────────────────────────────────────────────────────────────────┘
                     Binary Authorization gate (Section 43)
              blocks any Pod image not matching trust policy
                        before it ever reaches this cluster
```

## 8. Hands-On Example: Enabling and Binding Workload Identity

**Beginner example — enable Workload Identity on a cluster:**

```bash
gcloud container clusters update my-cluster \
  --region=us-central1 \
  --workload-pool=my-project.svc.id.goog
```

**Purpose:** Enables the Workload Identity pool for the cluster, a prerequisite for any KSA-to-GSA binding; new clusters (and all Autopilot clusters) have this enabled by default.

**Expected output (abbreviated):**

```
Updating my-cluster...done.
NAME         WORKLOAD_IDENTITY_CONFIG
my-cluster   {"workloadPool": "my-project.svc.id.goog"}
```

**Intermediate example — bind a KSA to a GSA:**

```bash
gcloud iam service-accounts add-iam-policy-binding \
  storage-reader@my-project.iam.gserviceaccount.com \
  --role=roles/iam.workloadIdentityUser \
  --member="serviceAccount:my-project.svc.id.goog[app/reader-ksa]"

kubectl annotate serviceaccount reader-ksa \
  --namespace=app \
  iam.gke.io/gcp-service-account=storage-reader@my-project.iam.gserviceaccount.com
```

**Purpose:** The first command grants the specific KSA `reader-ksa` in namespace `app` permission to impersonate the `storage-reader` GSA; the second annotates the KSA so GKE knows which GSA it maps to. Together, any Pod using `reader-ksa` now authenticates as `storage-reader@my-project.iam.gserviceaccount.com` automatically.

**Expected output:**

```
Updated IAM policy for serviceAccount [storage-reader@my-project.iam.gserviceaccount.com].
serviceaccount/reader-ksa annotated
```

## 9. Production & Enterprise Usage

- Enterprises treat Workload Identity as **mandatory, not optional** — static GSA key files mounted as Kubernetes Secrets are a common finding in security audits and Security Command Center (Section 39) scans, and organizations typically have a policy explicitly prohibiting them in favor of Workload Identity.
- **Private clusters with authorized networks** (or fully private endpoints, accessed via a bastion or VPN) are the default for production clusters handling sensitive data, with public-endpoint clusters reserved for narrow, justified cases.
- Binary Authorization (Section 43) is commonly paired with Workload Identity and private clusters as a three-layer defense: only trusted images deploy, deployed Pods authenticate with minimal scoped permissions, and the cluster's network surface is minimized — each layer independently reduces risk if another fails.

## 10. Common Misconceptions

- **Misconception:** "Workload Identity is just a convenience feature to avoid managing key files." While it does remove key-file management, its primary security value is eliminating node-level credential sharing across Pods and the long-lived, exportable nature of static keys — it's a least-privilege and blast-radius control, not merely a convenience.
- **Misconception:** "A private cluster with no public node IPs doesn't need Workload Identity, since nodes aren't internet-reachable anyway." Private clusters and Workload Identity solve different problems — private clusters reduce network exposure, Workload Identity enforces least-privilege identity for workloads calling GCP APIs. A private cluster's Pods can still over-share node-level credentials with each other absent Workload Identity; the two controls are complementary, not substitutes.

## 11. Interview Questions

**🎯 Beginner:** _What problem does Workload Identity solve that existed before it?_
**Model answer:** Before Workload Identity, Pods calling Google Cloud APIs typically relied on the node's own service account credentials via the metadata server, meaning every Pod on a node shared the same broad permissions and any Pod that could reach the metadata server could potentially access node-level credentials. Workload Identity binds each Kubernetes ServiceAccount to its own scoped GCP service account, giving each workload exactly the permissions it needs and issuing short-lived credentials instead of relying on shared node-level or static key-file credentials.

**🎯 Intermediate:** _Why is mounting a downloaded GCP service account JSON key as a Kubernetes Secret considered a security anti-pattern compared to Workload Identity?_
**Model answer:** A downloaded JSON key is a long-lived, static, exportable credential — it doesn't expire on its own, it can be copied out of the cluster (accidentally logged, committed to source control, or exfiltrated from `etcd`), and rotating it requires manual key-management discipline. Workload Identity issues short-lived, automatically rotated credentials tied to the Pod's identity at request time, never persisting a static key to disk or `etcd`, which removes an entire class of credential-sprawl risk that static keys inherently carry.

**🎯 Senior/Architect:** _Design the security posture for a GKE cluster handling regulated customer data — cover network exposure, workload identity, node integrity, and deployment controls._
**Model answer:** I'd start with a **private cluster** with a private (non-public) control plane endpoint accessed only via a bastion host or VPN/Interconnect from the corporate network, and no public node IPs, using Cloud NAT for any legitimate outbound internet access — this minimizes network attack surface immediately. Every workload would use **Workload Identity**, with GSAs scoped per-application to the specific IAM roles that application needs on the specific resources it touches — no broad project-level roles, and an explicit policy prohibiting static GSA key files as Kubernetes Secrets, enforced via Org Policy (Section 37) and periodic Security Command Center scans (Section 39). I'd require **Shielded GKE Nodes** (default in current GKE, but I'd verify explicitly given regulated-data stakes) for boot integrity assurance. Finally, I'd layer in **Binary Authorization** (Section 43) requiring images to be signed by our CI/CD pipeline's attestor before deployment is even permitted, closing the loop so a compromised or unauthorized image can't reach the cluster regardless of who attempts to deploy it — combined, these four controls address network exposure, identity/least-privilege, node integrity, and supply-chain trust as genuinely independent, complementary layers.

## 12. Key Takeaways

- 🔑 Workload Identity binds a Kubernetes ServiceAccount to a scoped GCP IAM service account, replacing shared node-level credentials with short-lived, per-workload credentials — treat static GSA key files in Secrets as a finding to remediate, not an acceptable alternative.
- 🔑 Shielded GKE Nodes verify node boot integrity (Secure Boot, vTPM, integrity monitoring) and are on by default for new clusters, mandatory under Autopilot.
- 🔑 Private clusters remove public IPs from nodes and, optionally, the control plane endpoint, shrinking network attack surface independently of identity controls.
- 🔑 Binary Authorization (fully covered in Section 43) enforces deploy-time image provenance and is commonly layered alongside Workload Identity, Shielded Nodes, and private clusters as complementary — not overlapping — defenses.

## 13. Related Concepts

GKE architecture (Section 30), GKE networking and storage — including Cloud NAT for private cluster egress (Section 31), Autopilot's default-hardened posture (Section 32), Artifact Registry image scanning (Section 29), IAM fundamentals and service accounts (Part 5, Sections 35–36), Org Policy (Section 37), and Binary Authorization & Confidential Computing (Section 43) all extend the security model introduced here.
