# Section 34 — Azure Container Registry (ACR)

**Part 7: Containers & Orchestration | Section 34 of 70**
**Prerequisites:** Section 33 (Docker on Azure Fundamentals — images, tags, digests, registries), Section 9 (Managed Identities & Service Principals), Section 8 (RBAC)
**Leads into:** Section 35–37 (Azure Kubernetes Service, which pulls images from ACR)

---

## 34.1 Introduction and Scope

Section 33 established that every Azure container-hosting option needs to pull an image from _somewhere_, and that Docker Hub is generally unsuitable as the source of truth for proprietary enterprise images. This section covers **Azure Container Registry (ACR)** — Azure's private, managed OCI-compliant registry — in full depth: architecture, authentication models, replication, build automation (ACR Tasks), security, and production operational patterns.

🔑 **Key Takeaway:** ACR is the trust boundary and single source of truth for container images in an Azure enterprise architecture. Nearly every downstream container service (AKS, ACI, App Service, Container Apps, Functions) is configured to pull only from ACR, making its access control and integrity guarantees a foundational security control for the entire container platform.

---

## 34.2 What Is Azure Container Registry

### 34.2.1 Definition

**Plain language:** ACR is a private Docker Hub that lives inside your Azure subscription — a place to store, version, and distribute the container images your Azure services run, with Azure's identity and networking controls built in.

**Precise definition:** Azure Container Registry is a managed, private registry service based on the open-source Docker Registry 2.0 (and OCI Distribution Specification) implementation, providing storage and distribution of container images and other OCI artifacts (Helm charts, OPA policies, and other supply-chain artifacts), integrated with Microsoft Entra ID for authentication and Azure RBAC for authorization.

### 34.2.2 Why It Exists / The Problem It Solves

- **Trust and control:** public registries place the availability, integrity, and access control of production images outside the organization's direct control. An outage or a compromised public repository directly threatens production deployments.
- **Network locality and performance:** pulling images from a registry inside the same Azure region (or replicated to multiple regions) is dramatically faster and more reliable than pulling from a public internet endpoint, especially at the scale of hundreds of AKS nodes pulling simultaneously during a scale-out event.
- **Identity-integrated access control:** ACR integrates directly with Microsoft Entra ID and Managed Identities, so image push/pull permissions can be granted and revoked using the same RBAC model as the rest of the Azure estate (Section 8), instead of separately managed registry credentials.
- **Private networking:** ACR supports Private Link, allowing image pulls to occur entirely within a private VNet without traversing the public internet — a hard requirement in many regulated enterprise network architectures (Section 23 concepts apply directly).

### 34.2.3 Terminology

| Term                             | Definition                                                                                                                                                                                              |
| -------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Registry**                     | The top-level ACR resource (e.g., `myregistry.azurecr.io`), an Azure resource with its own resource group, SKU, and access policies.                                                                    |
| **Repository**                   | A named collection of related image versions within a registry (e.g., `myregistry.azurecr.io/webapp`).                                                                                                  |
| **Artifact**                     | Any OCI-compliant object stored in ACR — not limited to container images; includes Helm charts, OCI-formatted policy bundles, and other supply-chain artifacts.                                         |
| **SKU (Basic/Standard/Premium)** | ACR's pricing/feature tier, determining storage included, throughput limits, and available features (geo-replication, Private Link, content trust require Premium).                                     |
| **Geo-replication**              | A Premium-tier feature that maintains synchronized copies of a registry's content across multiple Azure regions under a single registry name/login server.                                              |
| **ACR Tasks**                    | A suite of ACR features that build, test, and patch container images directly in Azure, triggered by source code commits, base image updates, or a schedule — without requiring a separate build agent. |
| **ACR Connected Registry**       | A feature enabling a local, on-premises or edge registry that synchronizes with a cloud ACR instance, for disconnected or intermittently connected environments.                                        |
| **Content trust**                | A Premium-tier feature (based on Docker Content Trust/Notary) enabling cryptographic signing of pushed images and rejection of unsigned images on pull, for supply-chain integrity assurance.           |
| **Login server**                 | The fully qualified DNS name of a registry, always in the form `<registry-name>.azurecr.io`, used as the registry host portion of an image reference.                                                   |
| **Webhook**                      | A registry-level event notification mechanism (e.g., on image push) that can trigger external automation such as a deployment pipeline.                                                                 |

---

## 34.3 Architecture and How ACR Fits the Ecosystem

### 34.3.1 Position in the Azure Container Ecosystem

```
Developer / CI Pipeline
        │  docker build / az acr build
        ▼
┌─────────────────────────┐
│  Azure Container Registry │  ← private, Entra ID-integrated, RBAC-controlled
│  (myregistry.azurecr.io)  │
└──────────┬────────────────┘
            │ docker pull / containerd pull (via Managed Identity or AcrPull role)
            ▼
┌─────────────┬─────────────┬─────────────────┬───────────────┐
│     AKS      │     ACI      │  App Service    │ Container Apps │
│  node pools  │ (Sec. 15)    │  (Sec. 13)      │                 │
│ (Sec. 35–37) │              │                 │                 │
└─────────────┴─────────────┴─────────────────┴───────────────┘
```

- ACR itself is built on the same OCI Distribution Specification implemented by Docker Hub and other registries; from a pure protocol perspective, `docker push`/`docker pull` behave identically against ACR as against any other OCI-compliant registry — the differentiation is entirely in the surrounding Azure integration (identity, networking, automation), not the wire protocol.
- Internally, Azure operates ACR as a multi-tenant, highly available service; the customer-visible unit is the **registry resource** (an ARM resource, Section 4), which has its own resource ID, location, SKU, and access policies, independent of any single underlying storage node.

### 34.3.2 SKU Comparison

| Feature                          | Basic                 | Standard                      | Premium                                                                |
| -------------------------------- | --------------------- | ----------------------------- | ---------------------------------------------------------------------- |
| Included storage                 | 10 GiB                | 100 GiB                       | 500 GiB                                                                |
| Throughput                       | Lower                 | Medium                        | Highest                                                                |
| Geo-replication                  | ✗                     | ✗                             | ✓                                                                      |
| Private Link / Private Endpoints | ✗                     | ✗                             | ✓                                                                      |
| Content trust (image signing)    | ✗                     | ✗                             | ✓                                                                      |
| Availability zone support        | ✗                     | ✗                             | ✓                                                                      |
| ACR Tasks                        | ✓ (all tiers)         | ✓                             | ✓                                                                      |
| Typical fit                      | Dev/test, small teams | Mid-size production workloads | Enterprise production, multi-region, regulated networking requirements |

⚠️ **Warning:** Exact storage/throughput numbers and feature availability should be verified against current Microsoft documentation at time of use, as SKU limits and included quotas are subject to change by Microsoft.

🎯 **Interview Tip:** A common architecture question is "when would you need Premium?" The strong answer ties the choice to a _specific requirement_ — multi-region AKS clusters needing geo-replicated low-latency pulls, a network policy mandating Private Link for all PaaS dependencies, or a compliance requirement for image signing — rather than defaulting to "Premium is just better."

---

## 34.4 Authentication and Authorization

### 34.4.1 Why This Is the Most Interview-Relevant Part of ACR

Because ACR sits on the critical path of every deployment, how identities authenticate to it is a frequent architecture and security discussion point, and a common source of production incidents when done incorrectly (e.g., embedded long-lived credentials, expired service principal secrets breaking deployments).

### 34.4.2 Authentication Methods (Ranked by Enterprise Preference)

1. **Microsoft Entra ID identity with RBAC role assignment (preferred, especially via Managed Identity):**
   - A **Managed Identity** (Section 9) — system-assigned to an AKS cluster, an App Service, or a VM, for example — is granted the `AcrPull` (or `AcrPush`, `AcrDelete`) role directly on the registry resource via Azure RBAC (Section 8).
   - No credentials are ever created, stored, or rotated by a human; Azure handles token issuance and rotation transparently.
   - This is the recommended pattern for AKS specifically: `az aks create --attach-acr <registry>` (or the equivalent Bicep/Terraform configuration) wires up the AKS cluster's kubelet identity with `AcrPull` on the target registry automatically.
2. **Service Principal with RBAC role assignment:**
   - Used where a Managed Identity is not available (e.g., a CI/CD system running outside Azure, such as a self-hosted GitHub Actions runner without workload identity federation configured).
   - Requires managing a client secret or certificate, which introduces rotation and storage responsibilities — Azure Key Vault (Section 53) is the standard place to store such secrets, never plaintext pipeline variables.
   - Where the CI/CD platform supports it (e.g., GitHub Actions OIDC federation, Azure DevOps workload identity federation), **federated credentials** avoid storing any secret at all, combining the security benefits of Managed Identity with support for external CI/CD platforms — this is increasingly the preferred pattern over classic Service Principal secrets.
3. **`az acr login` (Azure CLI-based, developer/interactive use):**
   - Runs `az acr login --name <registry>`, which uses the currently logged-in Azure CLI identity (a human's Entra ID account) to obtain a short-lived Docker credential, avoiding a separate `docker login` credential entirely.
   - Appropriate for interactive developer workflows; not appropriate for unattended automation.
4. **Admin user (discouraged for production):**
   - Each ACR registry has an optional built-in "admin" account with a static username/password, disabled by default.
   - ⚠️ **Warning:** the admin account is a single shared credential with full push/pull/delete access and no per-identity audit trail; Microsoft's own guidance, and consistent enterprise practice, is to leave it disabled and use Entra ID-based authentication instead. It exists mainly for quick testing/demo scenarios, not production use.

### 34.4.3 RBAC Roles for ACR (Applying Section 8 Concepts)

| Role                                     | Grants                                                                                                                                             |
| ---------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------- |
| `AcrPull`                                | Pull (read) images and metadata only.                                                                                                              |
| `AcrPush`                                | Pull and push images (includes pull).                                                                                                              |
| `AcrDelete`                              | Delete images/tags/manifests.                                                                                                                      |
| `AcrImageSigner`                         | Sign images (used with content trust, Premium).                                                                                                    |
| `Contributor` (on the registry resource) | Full management of the registry resource itself (settings, replication, SKU) — broader than image-level operations and should be scoped carefully. |

💡 **Tip:** Following least-privilege (a recurring theme from Section 8), CI build agents should typically receive only `AcrPush`, and production compute (AKS kubelet identity, App Service's Managed Identity) should receive only `AcrPull` — neither needs registry management permissions, and neither push identity needs delete rights unless a specific cleanup automation role requires it.

### 34.4.4 Commands — Authentication (Command Documentation Template)

#### `az acr login`

- **Purpose:** authenticates the local Docker client against an ACR registry using the current Azure CLI session's identity.
- **Syntax:** `az acr login --name <registry-name>`
- **Practical example:**
  ```bash
  az acr login --name myregistry
  docker push myregistry.azurecr.io/webapp:1.0
  ```
  Expected output: `Login Succeeded`.
- **Common errors:** `unauthorized: authentication required` if the signed-in identity lacks `AcrPush`/`AcrPull` role assignment on the registry; `az login` not yet run (no active Azure CLI session).
- **Security impact:** issues a short-lived token rather than a long-lived credential, reducing exposure if a developer's environment is compromised.

#### `az acr credential show` (admin account, discouraged for production)

- **Purpose:** retrieves the static admin username/password for a registry, if the admin account is enabled.
- **Syntax:** `az acr credential show --name <registry-name>`
- **Security impact:** exposes a long-lived, non-identity-scoped credential; discouraged outside temporary testing, as covered in 34.4.2.

---

## 34.5 Repositories, Tags, and Image Lifecycle in ACR

### 34.5.1 Repository and Tag Structure

Image references in ACR follow the same structure introduced in Section 33.5.4: `<registry-login-server>/<repository>:<tag>`. ACR supports **nested repository namespaces** using `/` as a path-like separator purely for organizational convention (e.g., `myregistry.azurecr.io/team-a/webapp:1.0`), which is not a true filesystem hierarchy but a naming convention that ACR's tooling and RBAC scoping (via repository-scoped tokens, 34.5.4) can key off.

### 34.5.2 Commands — Repository/Image Management

#### `az acr repository list`

- **Purpose:** lists all repositories in a registry.
- **Syntax:** `az acr repository list --name <registry-name> [--output table]`

#### `az acr repository show-tags`

- **Purpose:** lists all tags within a specific repository.
- **Syntax:** `az acr repository show-tags --name <registry-name> --repository <repo> [--orderby time_desc]`
- **Production usage:** commonly scripted as part of a cleanup/retention automation to identify old tags eligible for deletion.

#### `az acr repository delete`

- **Purpose:** deletes a repository or a specific tag/manifest.
- **Syntax:** `az acr repository delete --name <registry-name> --image <repo>:<tag>`
- **Common mistake:** deleting a tag does not necessarily delete the underlying manifest/layers if other tags still reference the same digest (content-addressed storage, Section 33.5.3) — genuine storage reclamation requires deleting the manifest itself, and untagged/orphaned manifests are the actual target of most cleanup automation (34.5.3).

### 34.5.3 Retention and Cleanup Policies

- **Untagged manifest retention policy (Premium tier):** ACR can be configured to automatically purge untagged manifests after a configurable number of days, addressing the storage growth problem caused by repeated pushes to a mutable tag such as `latest` or a CI-generated tag that gets overwritten, leaving the old digest's layers orphaned but still stored.
- **`az acr run` with the built-in `acr-purge` command:** a scriptable, scheduled way (often run via an ACR Task on a cron trigger) to delete tags/manifests matching an age or count-based filter, giving fine-grained control beyond the simple untagged-manifest policy.
- 💡 **Tip:** production registries should have an explicit retention policy from day one; unmanaged registries accumulate storage cost and clutter linearly with every CI build, which becomes a nontrivial operational cost at high build frequency.

### 34.5.4 Repository-Scoped Tokens (Fine-Grained Access)

Beyond registry-wide RBAC roles (34.4.3), ACR supports **tokens** scoped to specific repositories (or repository name patterns) with specific actions (`content/read`, `content/write`, `content/delete`), created against a **scope map**. This enables, for example, granting a specific external partner or a specific team pull-only access to just their own repository namespace, without granting any visibility into the rest of the registry — a capability that plain Azure RBAC role assignment (registry-wide) cannot express on its own.

---

## 34.6 ACR Tasks (Cloud-Native Image Building)

### 34.6.1 Definition

**ACR Tasks** is a suite of features that build and manage container images directly within Azure, triggered by source code changes, base image updates, or a schedule, without requiring a separately managed build agent (VM or CI runner) to execute `docker build`.

### 34.6.2 Why It Exists

- Running `docker build` requires a Docker daemon somewhere; ACR Tasks provides that build environment as a managed Azure service, eliminating the operational burden of maintaining build agents solely for image builds.
- **Base image update triggers** solve a problem plain CI pipelines typically cannot: rebuilding and redeploying an application image automatically when its **base image** receives a security patch upstream, even though the application's own source code has not changed — closing a common security gap where patched base images exist but dependent application images silently remain on the old, vulnerable base until the next unrelated code change triggers a rebuild.

### 34.6.3 Commands — ACR Tasks

#### `az acr build` (Quick Task — one-off build)

- **Purpose:** performs a single build-and-push in Azure without needing a local Docker daemon at all; useful for CI agents that lack Docker-in-Docker capability, or simply to offload build compute from the CI runner to Azure.
- **Syntax:** `az acr build --registry <registry-name> --image <repo>:<tag> .`
- **Practical example:**
  ```bash
  az acr build --registry myregistry --image webapp:1.0 .
  ```
  This uploads the local build context to ACR, builds the image using ACR's managed build compute, and pushes the result — all without a local `docker build`/`docker push`.
- **Production usage:** commonly used in CI/CD pipelines (Azure DevOps, GitHub Actions) specifically to avoid needing privileged Docker-in-Docker build agents, which carry their own security and operational overhead.

#### `az acr task create` (persistent, trigger-based Task)

- **Purpose:** defines a persistent task that automatically rebuilds an image when specified trigger conditions occur (source repository commit, base image update, schedule).
- **Syntax (source-trigger example):**
  ```bash
  az acr task create --registry myregistry --name build-webapp \
    --image webapp:{{.Run.ID}} \
    --context https://github.com/org/webapp.git \
    --file Dockerfile \
    --git-access-token <token>
  ```
- **Key concept — base image update trigger:** ACR Tasks can track the base images referenced in a Dockerfile's `FROM` instructions and automatically trigger a rebuild when Microsoft (or another tracked publisher) updates that base image with a security patch, without any change to the application's own source repository.
- **Common errors:** authentication failures against the source Git repository (expired token/credential); Dockerfile path mismatches relative to the specified build context.
- **Production/enterprise usage:** enterprises with strict patch-SLA requirements (e.g., "critical CVEs patched within 48 hours") rely on base-image-triggered ACR Tasks as an automated control satisfying that SLA without manual tracking of every downstream image.

### 34.6.4 Multi-Step Tasks

ACR Tasks also supports **multi-step task YAML** definitions describing a sequence of build, push, and test steps (e.g., build the image, run a container from it to execute integration tests, then push only if tests pass) — extending beyond a single `docker build` command into a lightweight CI pipeline running natively within ACR's managed compute.

---

## 34.7 Geo-Replication

### 34.7.1 Definition

**Geo-replication** (Premium SKU) allows a single ACR registry resource to maintain synchronized copies of its content across multiple Azure regions, all reachable through the same login server name, with Azure automatically routing each pull request to the nearest replica.

### 34.7.2 Why It Exists and Production Relevance

- **Latency and reliability:** an AKS cluster in East US pulling from a registry only located in West Europe incurs unnecessary latency and depends on cross-region network reliability for every image pull, including during node scale-out events where many nodes pull simultaneously.
- **Single registry name, no client-side complexity:** applications and orchestrators reference the same `myregistry.azurecr.io` regardless of which replica actually serves the request — geo-replication is transparent to the pulling client; Azure's networking layer handles routing to the nearest healthy replica.
- **Regional resilience:** if one replica's region experiences an outage, pulls can continue being served from other replicas (subject to Azure's specific failover behavior at the time, which should be verified against current documentation for exact guarantees).

### 34.7.3 Architecture Diagram

```
                    myregistry.azurecr.io (single logical registry)
                              │
        ┌─────────────────────┼─────────────────────┐
        ▼                     ▼                     ▼
  Replica: East US      Replica: West Europe    Replica: Southeast Asia
        │                     │                     │
        ▼                     ▼                     ▼
   AKS cluster           AKS cluster            AKS cluster
   (East US)             (West Europe)          (Southeast Asia)
   pulls from            pulls from             pulls from
   nearest replica        nearest replica         nearest replica
```

🔑 **Key Takeaway:** Geo-replication is an architectural decision driven by _where compute consuming the registry actually runs_, not simply "more regions is better" — a single-region deployment gains little from enabling it, while a genuinely multi-region AKS/App Service footprint benefits directly in both latency and resilience.

---

## 34.8 Private Networking (Private Link / Private Endpoints)

### 34.8.1 Definition

ACR Premium supports **Private Endpoints** (applying VNet/Private Link concepts from Section 23), allowing the registry's data-plane traffic (push/pull) to occur entirely over a private IP address within a customer VNet, with no traversal of the public internet.

### 34.8.2 Why It Matters

- Many enterprise network security policies mandate that no PaaS dependency be reachable over the public internet, even with authentication controls in place — Private Link satisfies this by giving the registry a private IP inside the organization's own VNet address space.
- Combined with **disabling public network access** on the registry entirely (a registry-level setting), this ensures the only network path to the registry is through the approved private connection.
- ⚠️ **Warning:** disabling public access without first correctly provisioning DNS resolution for the private endpoint (via Azure Private DNS zones, Section 27 concepts) will break all image pulls, including from AKS nodes, App Service, and any CI agents not connected to the private network — this is a common misconfiguration during initial rollout and should be validated in a non-production registry or with a careful maintenance window first.

---

## 34.9 Security Considerations

### 34.9.1 Vulnerability Scanning

- ACR integrates with **Microsoft Defender for Cloud** (Section 52) to automatically scan pushed images for known vulnerabilities (CVEs), surfacing findings in the Defender for Cloud dashboard and, depending on configuration, blocking deployment of images with critical findings via admission control policies at the AKS layer (Section 36/54).
- 💡 **Tip:** scanning should be treated as a required CI/CD gate for production image promotion, not merely a dashboard to review after the fact.

### 34.9.2 Content Trust (Image Signing)

- Premium-tier **content trust** allows publishers to cryptographically sign images on push, and configures the registry to reject pulls of unsigned images for repositories with trust enabled — mitigating the risk of a compromised push credential or a supply-chain injection introducing an unauthorized image under a trusted repository name.
- This is a defense-in-depth control layered on top of RBAC (34.4.3): RBAC controls _who_ can push, while content trust provides cryptographic proof of _what_ was actually published by an authorized signer, protecting against scenarios where a push credential itself is compromised.

### 34.9.3 Network and Access Hardening Checklist

- Disable the registry admin account (34.4.2) in all non-trivial environments.
- Use Managed Identities with least-privilege roles (`AcrPull` for consumers, `AcrPush` for CI) rather than shared credentials.
- Enable Private Link and disable public network access where network policy requires it (34.8).
- Enable Microsoft Defender for Cloud's container image scanning.
- Enable retention/cleanup policies to reduce the accumulated attack surface of stale, unpatched historical images (34.5.3).
- Consider content trust for registries holding production-critical images (34.9.2).

### 34.9.4 Interview Questions — ACR Security

**Intermediate:** "How does an AKS cluster typically authenticate to pull images from ACR, and why is this preferred over storing credentials in a Kubernetes Secret?"
_Model answer:_ The recommended pattern attaches the AKS cluster's kubelet Managed Identity directly to the ACR registry with the `AcrPull` role (via `az aks create --attach-acr` or equivalent IaC configuration). This avoids ever creating, storing, or rotating a long-lived credential — Entra ID issues short-lived tokens transparently. Storing a static registry credential in a Kubernetes Secret (an older, now-discouraged pattern using `imagePullSecrets`) introduces a long-lived credential that must be manually rotated and is a persistent secret at rest in the cluster, increasing the blast radius if the cluster's secret store is compromised.
_What the interviewer is probing:_ awareness of the current recommended identity-based pattern versus legacy credential-based patterns, and the security reasoning behind the preference.

**Architect:** "A compliance requirement mandates that container images cannot be pulled over the public internet under any circumstances. Walk through what you would configure."
_Model answer:_ Upgrade the registry to Premium SKU (required for Private Link). Create a Private Endpoint for the registry inside the target VNet, ensure Azure Private DNS zone integration correctly resolves the registry's login server to the private endpoint's IP for every network that needs to resolve it (including any peered VNets, Section 23), then disable public network access on the registry itself. Validate every consumer (AKS node pools, CI build agents, any App Service using VNet integration) has network line-of-sight to the private endpoint before disabling public access, since doing so prematurely will break all pulls. This should be tested in a non-production registry or during a controlled maintenance window given the blast radius of getting DNS resolution wrong.
_What the interviewer is probing:_ whether the candidate understands the full dependency chain (SKU → Private Endpoint → DNS → public access toggle) and the operational sequencing risk, not just that "Private Link exists."

---

## 34.10 Production and Enterprise Usage Patterns

- **One registry per environment tier vs. one shared registry with promotion:** two common enterprise patterns exist — (a) separate registries per environment (dev/test/prod) with images rebuilt or explicitly copied between them, or (b) a single registry with images built once and _promoted_ between environments purely via tag/labeling changes (no rebuild), aligning with the "build once, deploy many" principle from Section 33.12. Pattern (b) is generally the stronger practice where feasible, since it guarantees the exact same tested artifact reaches production; pattern (a) is sometimes chosen for stricter environment network isolation requirements. This is a trade-off decision, not a universal rule, and should be stated as such when discussed.
- **`az acr import`:** copies an image from one registry (including a public registry like Docker Hub or another ACR instance) directly into a target ACR registry, server-side, without needing to pull and push through a local Docker daemon — commonly used to mirror approved public base images into a controlled private registry (34.9) or to promote an image between separate per-environment registries under pattern (a) above.
- **Tag immutability:** ACR supports marking specific repositories or tags as immutable, preventing overwrite after push — directly supporting the "digest pinning" and release-integrity guidance from Section 33.5.6.
- **Cost management:** registry storage cost scales with retained images/layers; combined with SKU throughput/storage tiering (34.3.2), enterprises should size the SKU to genuine multi-region/Private Link/content-trust requirements rather than defaulting to Premium without a driving requirement, per Section 60's cost-optimization principles (to be covered in full in Part 12).

---

## 34.11 Monitoring and Troubleshooting

### 34.11.1 Monitoring

- ACR integrates with **Azure Monitor** (Section 47) for metrics such as storage usage, pull/push counts, and successful/failed authentication events, and with **Log Analytics** (Section 48) for diagnostic logs of registry operations (useful for auditing who pulled/pushed which image and when).
- 💡 **Tip:** enabling diagnostic settings on the registry to forward logs to Log Analytics is a common compliance requirement for auditability of image provenance and access.

### 34.11.2 Troubleshooting Reference

| Symptom                                                      | Likely Cause                                                                                                            | Diagnostic Step                                                                                                                                                                              |
| ------------------------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `unauthorized: authentication required` on pull from AKS     | Kubelet Managed Identity not granted `AcrPull` on the target registry                                                   | Verify with `az aks check-acr`, or confirm the role assignment via `az role assignment list --scope <registry-resource-id>`                                                                  |
| `docker push` denied                                         | Pushing identity lacks `AcrPush`                                                                                        | Confirm RBAC role assignment; confirm `az acr login` was run with the correct identity                                                                                                       |
| Pulls succeed from one region but fail/are slow from another | Geo-replication not enabled, or the expected replica region is missing                                                  | Check `az acr replication list --registry <name>`; add a replica in the underserved region if justified by actual consumer location                                                          |
| Pulls fail entirely after enabling Private Link              | Public network access disabled before DNS resolution to the private endpoint was correctly configured for all consumers | Verify Private DNS zone linkage (Section 27) for every VNet that needs to resolve the registry; temporarily re-enable public access to unblock while fixing DNS if this occurs in production |
| Registry storage growing unexpectedly                        | No retention/cleanup policy; repeated pushes to mutable tags leaving orphaned untagged manifests                        | Review `az acr repository show-tags`, apply a retention policy or `acr-purge` task (34.5.3)                                                                                                  |
| ACR Task build fails to authenticate to source repository    | Expired/incorrect Git access token                                                                                      | Rotate and update the token referenced by `az acr task create`/`update`                                                                                                                      |

---

## 34.12 Best Practices Checklist

- [ ] Registry admin account disabled.
- [ ] Managed Identity + least-privilege RBAC (`AcrPull`/`AcrPush`) used for all automated consumers and CI agents.
- [ ] Retention/cleanup policy configured to control storage growth from untagged manifests.
- [ ] Premium SKU with Private Link enabled where network policy requires no public exposure.
- [ ] Microsoft Defender for Cloud image scanning enabled and treated as a deployment gate.
- [ ] Base-image-update-triggered ACR Tasks configured for images with a patch-SLA requirement.
- [ ] Diagnostic logging forwarded to Log Analytics for audit purposes.
- [ ] Production deployments reference images by digest (Section 33.5.6), reinforced by tag immutability where the release process supports it.

---

## 34.13 Common Misconceptions

- "ACR is just Docker Hub hosted by Microsoft." _Correction:_ ACR implements the same open Distribution Specification, but its differentiated value is entirely in Azure-native integration — Entra ID/Managed Identity authentication, Azure RBAC, geo-replication tied to Azure regions, Private Link into customer VNets, and ACR Tasks' cloud-native build automation — none of which are properties of the underlying registry protocol itself.
- "Enabling geo-replication automatically makes pulls faster everywhere." _Correction:_ it only helps for consumers actually located near an added replica region; it provides no benefit for a single-region deployment and adds cost without justification in that case.

---

## 34.14 Interview Questions (Consolidated)

**Beginner:** "What is Azure Container Registry, and how does an image reference to it differ from a Docker Hub image reference?"
_Model answer:_ ACR is Azure's private, managed container registry. An image reference to ACR includes the registry's login server as the host portion, e.g., `myregistry.azurecr.io/webapp:1.0`, versus an implicit Docker Hub reference like `nginx:1.27`, which has no explicit registry host because Docker Hub is the default when none is specified.

**Senior:** "Explain the trade-off between per-environment registries and a single registry with promotion by tag."
_Model answer:_ covered in 34.10 — summarize as: promotion-by-tag/digest within one registry guarantees the exact tested artifact reaches production (aligned with "build once, deploy many," Section 33.12) but requires that registry to be reachable, with appropriate access controls, from every environment's compute; per-environment registries provide stronger network/administrative isolation between environments at the cost of either rebuilding per environment (reintroducing reproducibility risk) or explicit server-side copying via `az acr import`.

**FAANG-style / Scenario:** "Your organization's security team reports that a critical CVE was published for a widely used base image three days ago, and asks you to demonstrate that all production images built on that base have been patched. What ACR capability directly supports both detecting this gap and preventing its recurrence?"
_Model answer:_ Microsoft Defender for Cloud's image scanning integration (34.9.1) can identify which currently-stored images are affected by the CVE, providing the detection/audit answer for "have we been patched." For _preventing recurrence_, a base-image-update-triggered ACR Task (34.6.3) configured on the affected Dockerfiles would have automatically rebuilt and republished the dependent application images as soon as the patched base image was published upstream, without waiting for an unrelated application code change — directly closing this class of gap going forward, and this is the concrete change to recommend to the security team as a systemic fix rather than a one-time remediation.
_What the interviewer is probing:_ connecting a specific ACR capability to a real operational/security requirement, and distinguishing a one-time fix from a systemic process improvement — a hallmark of senior/architect-level reasoning.

---

## 34.15 Key Takeaways Summary

🔑 ACR implements the standard OCI Distribution Specification — the differentiation is entirely in Azure-native identity, networking, replication, and build-automation integration.

🔑 Managed Identity + RBAC (`AcrPull`/`AcrPush`) is the strongly preferred authentication pattern over the static admin account or manually managed Service Principal secrets.

🔑 ACR Tasks' base-image-update trigger closes a security gap that plain CI pipelines typically cannot: keeping dependent application images patched even without application code changes.

🔑 Geo-replication and Private Link are both driven by genuine consumer location/network-policy requirements, not defaults to enable universally — this trade-off framing is important in architecture and interview contexts alike.

🔑 Retention policy and tag immutability directly reinforce the digest-pinning and "build once, deploy many" principles established in Section 33.

---

## 34.16 Related Concepts and What Comes Next

- **Section 33 (prerequisite, completed):** image/layer/tag fundamentals this section builds on directly.
- **Sections 35–37 — Azure Kubernetes Service:** the primary large-scale consumer of ACR in most enterprise architectures; AKS-ACR integration (`--attach-acr`, kubelet Managed Identity) is introduced conceptually here and covered operationally in Section 35's architecture material.
- **Section 9 — Managed Identities & Service Principals (prerequisite, completed):** the identity mechanism underlying 34.4's authentication guidance.
- **Section 52 — Microsoft Defender for Cloud:** full depth on the vulnerability scanning integration introduced in 34.9.1.
- **Section 53 — Key Vault:** where Service Principal secrets or Git access tokens referenced in 34.4.2/34.6.3 should be stored when a Managed Identity/federated credential is not available.

---

_End of Section 34. Next: Section 35 — Azure Kubernetes Service (AKS) — Architecture._
