# Section 29 (Part 4): Artifact Registry / Container Registry

## 1. Definition

**Plain language:** Artifact Registry is GCP's storage location for the packages your build and deploy pipelines need — container images, but also language packages like npm, Maven, and Python packages, and OS packages. Think of it as a private, access-controlled warehouse that sits between "I built something" and "something is running it," whether that "something" is a GKE cluster, Cloud Run service, or a developer's laptop pulling a dependency.

**Precise:** Artifact Registry is GCP's fully managed, IAM-integrated package and container image repository service, supporting multiple repository **formats** (Docker, npm, Maven, Python, Go modules, Apt, Yum, and generic artifacts) and multiple repository **modes** (standard, remote pass-through caches, and virtual aggregating repositories), with per-repository regional or multi-regional storage location, and integrated vulnerability scanning for container images.

## 2. Why It Exists / Problem It Solves

Before Artifact Registry, GCP offered **Container Registry (GCR)**, a simpler service scoped only to Docker container images, backed directly by Cloud Storage buckets (`gcr.io`). GCR worked but had real limitations as organizations matured:

- It supported **only** the Docker image format — teams also needed separate solutions for npm, Maven, Python, or OS packages, forcing them to run third-party artifact managers alongside GCR.
- Its per-project, bucket-backed model made fine-grained IAM control and regional placement more awkward than a purpose-built repository service.
- It lacked some of the reliability and vulnerability-scanning integration depth that a dedicated artifact management product could offer.

Artifact Registry exists to be the single, unified successor: one service, one IAM model, one product surface, covering every artifact type a modern CI/CD pipeline produces or consumes — not just container images.

> ⚠️ **Migration note:** Google announced Container Registry's deprecation, with existing `gcr.io` traffic transparently redirected to Artifact Registry repositories and GCR itself scheduled for shutdown. New projects should use Artifact Registry directly rather than GCR; existing GCR users should plan an explicit migration rather than relying indefinitely on the redirect. Always verify the current shutdown timeline against Google's official deprecation announcements, since exact dates are the kind of detail that changes and goes stale in written notes.

## 3. Repository Formats

Artifact Registry organizes storage into **repositories**, each created with a single declared format:

| Format            | Typical Use Case                                                              |
| ----------------- | ----------------------------------------------------------------------------- |
| **Docker**        | Container images for GKE, Cloud Run, Compute Engine, Cloud Build.             |
| **npm**           | Node.js/JavaScript package dependencies, including private internal packages. |
| **Maven**         | Java/JVM build artifacts (JARs, POMs).                                        |
| **Python (PyPI)** | Python packages (`pip install` against a private index).                      |
| **Go modules**    | Private Go module proxying/hosting.                                           |
| **Apt / Yum**     | OS-level `.deb`/`.rpm` package hosting for custom Linux package distribution. |
| **Generic**       | Arbitrary files/binaries that don't fit a language-specific format.           |

Each repository holds only one format — you don't mix npm packages and Docker images in the same repository, though a single project can hold many repositories of different formats side by side.

## 4. Repository Modes

- **Standard repository:** you push and pull your own artifacts directly; the default mode most teams use for their own build outputs.
- **Remote repository:** acts as a pass-through cache in front of an upstream public repository (e.g., Docker Hub, npmjs.org, PyPI, Maven Central). Requests for a package are fetched from upstream on first request and cached, reducing repeated external dependency on public registries (which have rate limits) and improving pull latency/reliability.
- **Virtual repository:** presents a single unified endpoint that routes requests across multiple underlying repositories (e.g., some standard, some remote), so consumers can use one repository URL without needing to know which backing repository actually holds a given artifact.

## 5. Regional vs. Multi-Regional Repositories

Every Artifact Registry repository has a declared **location**, following the same regional/multi-regional model introduced in Section 2:

- **Regional repository** (e.g., `us-central1`): artifacts are stored in a single region. Lower latency for pulls from workloads in or near that region, and keeps data within a specific geography for residency requirements.
- **Multi-regional repository** (e.g., `us`, `europe`, `asia`): artifacts are replicated across multiple regions within the broader geography, improving availability and giving lower average latency for consumers spread across that geography, at the cost of higher storage cost and write latency.

> 💡 **Tip:** For GKE workloads, colocating the Artifact Registry repository's region with the cluster's region (or using the matching multi-region) meaningfully reduces image pull latency during node scale-up and deployments — a frequently overlooked cost/latency lever in production.

## 6. Vulnerability Scanning

Artifact Registry integrates with **Container Scanning** (part of the broader Artifact Analysis capability), which automatically scans newly pushed container images against known vulnerability databases (CVEs) and continuously re-scans stored images as new vulnerabilities are discovered, without requiring a fresh push to trigger a re-scan. Scan results are queryable via the console, `gcloud`, or API, and can be gated in CI/CD pipelines (e.g., blocking a deploy if critical/high vulnerabilities are found) or fed directly into **Binary Authorization** (Section 43) as an attestation input before a workload is permitted to deploy to GKE.

## 7. Comparison: Artifact Registry vs. AWS ECR vs. Azure Container Registry

| Capability                          | GCP Artifact Registry                              | AWS ECR                                                                                           | Azure Container Registry (ACR)                                             |
| ----------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| Formats supported                   | Docker, npm, Maven, Python, Go, Apt, Yum, generic  | Container images only (ECR); other formats need separate AWS services (CodeArtifact for packages) | Docker/OCI images, Helm charts; other package formats limited              |
| Vulnerability scanning              | Native, continuous re-scanning (Artifact Analysis) | Native (Amazon Inspector integration)                                                             | Native (Microsoft Defender for Cloud integration)                          |
| Regional model                      | Explicit regional or multi-regional repos          | Regional per-repository (replication configurable separately)                                     | Regional, with geo-replication as a Premium-tier feature                   |
| Upstream pass-through caching       | Yes (remote repositories)                          | Yes (pull-through cache)                                                                          | Yes (via ACR's cache rules, Premium tier)                                  |
| Unified multi-format single product | Yes — one product, many formats                    | No — ECR (images) and CodeArtifact (packages) are separate services                               | Partially — ACR is images/Helm-focused; other formats need Azure Artifacts |

## 8. Hands-On Example: Creating a Repository and Pushing an Image

**Beginner example — create a Docker-format repository:**

```bash
gcloud artifacts repositories create my-app-repo \
  --repository-format=docker \
  --location=us-central1 \
  --description="Container images for my-app"
```

**Purpose:** Provisions a new regional Docker repository named `my-app-repo` in `us-central1`, ready to receive pushed images.

**Expected output:**

```
Create request issued for: [my-app-repo]
Waiting for operation to complete...done.
Created repository [my-app-repo].
```

**Intermediate example — authenticate Docker and push an image:**

```bash
gcloud auth configure-docker us-central1-docker.pkg.dev
docker tag my-app:latest us-central1-docker.pkg.dev/PROJECT_ID/my-app-repo/my-app:1.0.0
docker push us-central1-docker.pkg.dev/PROJECT_ID/my-app-repo/my-app:1.0.0
```

**Purpose:** Configures Docker's credential helper to authenticate against Artifact Registry, then tags a locally built image with the full Artifact Registry path (`<location>-docker.pkg.dev/<project>/<repository>/<image>:<tag>`) and pushes it.

**Expected output (abbreviated):**

```
1.0.0: digest: sha256:abcdef... size: 1234
```

**Check vulnerability scan results:**

```bash
gcloud artifacts docker images list us-central1-docker.pkg.dev/PROJECT_ID/my-app-repo \
  --include-tags
```

**Purpose:** Lists pushed images with their tags and digests, a starting point before querying detailed vulnerability findings via `gcloud artifacts docker images describe --show-package-vulnerability`.

## 9. Production & Enterprise Usage

- Enterprises typically create **one Artifact Registry repository per environment tier or team**, not one giant shared repository, so IAM permissions can be scoped tightly (e.g., only the CI service account for team A can push to team A's repository).
- **Remote repositories** are standard practice for any organization pulling public base images (e.g., `node:20`, `python:3.12`) at scale, both to avoid public registry rate limits and to create a controlled, auditable single point through which all external dependencies flow.
- CI/CD pipelines commonly gate promotion between environments on vulnerability scan results — e.g., an image cannot be promoted from a staging repository to a production repository if it has unresolved critical CVEs, often enforced together with Binary Authorization (Section 43).

## 10. Common Misconceptions

- **Misconception:** "Artifact Registry is just Container Registry with a new name." Artifact Registry is a genuinely broader product — multi-format (not Docker-only), with a different underlying storage/IAM model and additional modes (remote, virtual) that GCR never had.
- **Misconception:** "A multi-regional repository is always the better/safer choice." Multi-regional repositories cost more and have higher write latency; for a single-region GKE cluster or Cloud Run service, a regional repository colocated with the workload is usually the better choice on both cost and latency grounds.

## 11. Interview Questions

**🎯 Beginner:** _What is Artifact Registry and how does it differ from the older Container Registry?_
**Model answer:** Artifact Registry is GCP's managed repository service for container images and other build artifacts (npm, Maven, Python, and more), replacing the older, Docker-image-only Container Registry (GCR). Artifact Registry supports multiple package formats in one product, offers explicit regional/multi-regional placement, remote pass-through caching, and virtual repositories, none of which GCR offered natively.

**🎯 Intermediate:** _What is the difference between a remote repository and a standard repository in Artifact Registry, and why would you use a remote repository?_
**Model answer:** A standard repository stores artifacts you push yourself. A remote repository is a pass-through cache configured in front of an upstream registry like Docker Hub or PyPI — the first request for a given package/image fetches and caches it from upstream, and subsequent requests are served from the cache. Organizations use remote repositories to avoid repeatedly hitting public registry rate limits, improve pull latency and reliability for CI/CD, and create a single controlled path through which external dependencies enter the organization.

**🎯 Senior/Architect:** _Design an Artifact Registry strategy for an enterprise with 20 development teams, strict production change control, and a requirement that no image with unresolved critical vulnerabilities reaches production._
**Model answer:** I'd create per-team (or per-domain) standard Docker repositories for build outputs, scoped with IAM so each team's CI service account can only push to its own repository, plus a small number of shared remote repositories (Docker Hub, base OS images) so external dependencies flow through one controlled, cached path rather than each team pulling directly from the public internet. I'd separate repositories by environment tier (e.g., a `staging` repository and a `production` repository per team, or a promotion pipeline that copies a specific validated digest from staging to production rather than re-pulling by mutable tag). Every push triggers Artifact Analysis vulnerability scanning; the CI/CD pipeline gates promotion to the production repository on scan results, and I'd pair this with Binary Authorization (Section 43) attestations so GKE itself refuses to deploy any image lacking a valid "passed vulnerability scan" attestation, giving a policy-enforced backstop rather than relying solely on pipeline discipline.

## 12. Key Takeaways

- 🔑 Artifact Registry is the multi-format successor to the Docker-only Container Registry, unifying container images, npm, Maven, Python, Go, and OS packages under one product and IAM model.
- 🔑 Repositories are regional or multi-regional; colocating repository location with consuming workloads reduces pull latency and cost.
- 🔑 Remote repositories cache upstream public registries; virtual repositories aggregate multiple underlying repositories behind one endpoint.
- 🔑 Native, continuously updated vulnerability scanning integrates with Binary Authorization (Section 43) to enforce policy at deploy time, not just report findings after the fact.

## 13. Related Concepts

Container fundamentals and image basics (Section 28), GKE architecture that pulls images from Artifact Registry (Section 30), Binary Authorization for policy-gated deploys (Section 43), and Cloud Build/CI-CD pipelines that push to Artifact Registry (Section 50) all build directly on the concepts introduced here.
