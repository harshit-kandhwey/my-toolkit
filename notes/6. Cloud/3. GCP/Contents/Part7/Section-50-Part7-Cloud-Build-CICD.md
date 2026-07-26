# Section 50 (Part 7): Cloud Build & CI/CD on GCP

## 1. Definition

**Plain language:** Cloud Build is Google's managed continuous integration/continuous delivery (CI/CD) service — it watches for a trigger (a code push, a pull request, or a manual command), then runs a sequence of containerized steps (compile, test, build an image, push it, deploy it) on infrastructure Google provisions and tears down for you.

**Precise:** Cloud Build is a serverless CI/CD execution engine that runs builds as an ordered sequence of OCI/Docker container steps defined in a `cloudbuild.yaml` (or `cloudbuild.json`) configuration file, triggered by source repository events (Cloud Source Repositories, GitHub, GitLab, Bitbucket), a Pub/Sub message, a webhook, or manual invocation, executing each step in an ephemeral worker VM (or, for network-isolated needs, a **private pool**) and billing per build-minute.

## 2. Why It Exists / Problem It Solves

Before managed CI/CD, teams either ran their own Jenkins fleet (patching, scaling, and securing the CI servers themselves) or paid for a third-party SaaS CI product that lived outside their cloud's IAM and networking boundary. Cloud Build exists to solve three problems specific to teams already standardized on GCP:

- **No CI infrastructure to manage.** Build workers are provisioned on demand and destroyed after the build; there is no idle Jenkins controller/agent fleet to patch or pay for around the clock.
- **Native IAM integration.** Build steps run as a **service account** with normal GCP IAM permissions, so pushing an image to Artifact Registry or deploying to Cloud Run/GKE requires only an IAM role grant, not a separately managed credential/secret injected into a third-party CI tool.
- **Everything is a container.** Every build step is just "run this container image with these args," which means the build environment is exactly reproducible and extending it (adding a linter, a security scanner, a custom deploy step) is as simple as pointing to another image — no plugin ecosystem to manage.

## 3. Core Concepts

### 3.1 Triggers

A **trigger** is the event binding that starts a build automatically. GCP supports three trigger models:

- **Source push trigger:** Fires on a push to a branch or a tag matching a regex pattern (e.g., `^main$` or `^v.*`), pointed at a connected repository (Cloud Source Repositories, GitHub, GitLab, or Bitbucket via the Cloud Build GitHub/GitLab App integration).
- **Pull request trigger:** Fires when a pull/merge request is opened or updated against a target branch, typically used to run tests and a preview build without deploying, gating the PR's mergeability on build success (via a required status check).
- **Manual trigger:** Invoked on demand via `gcloud builds submit` (ad hoc, no stored trigger needed) or by manually running a stored trigger from the console/CLI — used for one-off builds, release promotions, or triggers intentionally excluded from automatic firing (e.g., a production-deploy trigger requiring a human to click "Run").

Triggers can also fire from **Pub/Sub messages** or generic **webhooks**, enabling builds to be kicked off by non-Git events (e.g., a scheduled Cloud Scheduler job publishing to Pub/Sub, or an upstream pipeline signaling completion).

### 3.2 `cloudbuild.yaml` and Build Steps

The `cloudbuild.yaml` file defines the build as an ordered list of **steps**, each running a container image:

```yaml
steps:
  - name: "gcr.io/cloud-builders/go"
    args: ["test", "./..."]
  - name: "gcr.io/cloud-builders/docker"
    args:
      [
        "build",
        "-t",
        "us-central1-docker.pkg.dev/$PROJECT_ID/my-repo/app:$SHORT_SHA",
        ".",
      ]
  - name: "gcr.io/cloud-builders/docker"
    args:
      ["push", "us-central1-docker.pkg.dev/$PROJECT_ID/my-repo/app:$SHORT_SHA"]
  - name: "gcr.io/google.com/cloudsdktool/cloud-sdk"
    entrypoint: gcloud
    args:
      [
        "run",
        "deploy",
        "my-service",
        "--image=us-central1-docker.pkg.dev/$PROJECT_ID/my-repo/app:$SHORT_SHA",
        "--region=us-central1",
      ]
images:
  - "us-central1-docker.pkg.dev/$PROJECT_ID/my-repo/app:$SHORT_SHA"
options:
  logging: CLOUD_LOGGING_ONLY
```

- **Substitutions** (`$PROJECT_ID`, `$SHORT_SHA`, `$BRANCH_NAME`, and user-defined `_MY_VAR`) inject build-time context without hardcoding values.
- Steps run **sequentially by default**, sharing a `/workspace` volume so files produced by one step (e.g., compiled binaries) are visible to the next; a step can declare `waitFor` to run in parallel with (or independently of) other steps.
- The top-level `images` field tells Cloud Build which built images to push to a registry automatically at the end of a successful build, and `artifacts` similarly for non-image build outputs (binaries, tarballs) pushed to Cloud Storage.

### 3.3 Private Pools

By default, Cloud Build runs steps on Google-managed worker VMs with **no direct network path** into your VPC. A **private pool** is a dedicated, VPC-peered pool of Cloud Build workers that lets builds reach private resources — an internal artifact mirror, an on-prem system over Interconnect/VPN, a private GKE cluster's control plane — that a default public worker cannot reach, and also allows custom machine types (more CPU/memory than the default worker) for compute-heavy builds.

### 3.4 Build Service Account and Permissions

Every build runs as a **service account** — either the legacy default Cloud Build service account or, preferably, a **user-specified service account** with narrowly scoped IAM roles (e.g., `roles/artifactregistry.writer`, `roles/run.developer` for the specific steps that build needs) rather than the broad default. This is the mechanism that lets a build push an image or deploy a service without any separately managed API key or credential file.

## 4. Architecture Diagram

```
   Git push / PR / manual / Pub/Sub message
                │
                ▼
        ┌───────────────┐
        │ Cloud Build   │   reads cloudbuild.yaml from the
        │ Trigger       │   triggering commit/ref
        └───────┬───────┘
                ▼
        ┌─────────────────────────────────────────┐
        │  Build Execution (ephemeral worker)     │
        │  ┌────────┐ ┌────────┐ ┌────────┐       │
        │  │Step 1  │►│Step 2  │►│Step 3  │  ...  │
        │  │(test)  │ │(build) │ │(push)  │       │
        │  └────────┘ └────────┘ └────────┘       │
        │  runs as: build service account (IAM)   │
        │  shared /workspace volume across steps  │
        └───────────────────┬─────────────────────┘
                            ▼
         ┌───────────────────────────────────────────┐
         │ Artifact Registry (image) / GCS (artifact)│
         └───────────────────┬───────────────────────┘
                             ▼
              Cloud Deploy / gcloud run deploy / kubectl apply
              (Section 51 covers managed promotion pipelines)

   Private Pool variant: worker VM is VPC-peered, reachable from/to
   your VPC (internal artifact mirrors, on-prem via Interconnect/VPN).
```

## 5. Comparison vs. AWS CodeBuild and Azure Pipelines

| Concept                       | GCP Cloud Build                              | AWS CodeBuild                                                       | Azure Pipelines                                                                       |
| ----------------------------- | -------------------------------------------- | ------------------------------------------------------------------- | ------------------------------------------------------------------------------------- |
| Build definition              | `cloudbuild.yaml` (steps = containers)       | `buildspec.yml` (phases = shell commands in a chosen runtime image) | `azure-pipelines.yml` (stages/jobs/steps, YAML or classic UI)                         |
| Execution model               | Every step is an arbitrary container image   | Single build environment image running shell commands per phase     | Jobs run on a chosen agent (Microsoft-hosted or self-hosted), steps run tasks/scripts |
| Network-isolated builds       | Private pools (VPC-peered)                   | VPC-connected builds (CodeBuild in a VPC)                           | Self-hosted agents inside your network                                                |
| Native pipeline orchestration | Paired with Cloud Deploy for CD (Section 51) | Paired with CodePipeline for multi-stage orchestration              | Built-in multi-stage pipelines (build + release in one YAML)                          |
| Identity for deploy steps     | Build service account (IAM role bindings)    | CodeBuild service role (IAM policy)                                 | Service connections (scoped credentials per target)                                   |
| Pricing model                 | Per build-minute, by machine type            | Per build-minute, by compute type                                   | Free tier of parallel jobs, then per-parallel-job/minute                              |

## 6. Hands-On Examples

**Submit an ad hoc build (Beginner):**

```bash
gcloud builds submit --tag us-central1-docker.pkg.dev/my-project/my-repo/app:v1 .
```

**Purpose:** Builds a container image from the current directory using Cloud Build's default single-step Docker build shortcut and pushes it to Artifact Registry, without needing a `cloudbuild.yaml` for this simple case.
**Expected output (abbreviated):**

```
Creating temporary archive of 42 file(s) totalling 1.2 MiB...
Logs are available at [https://console.cloud.google.com/cloud-build/builds/...]
...
DONE
```

**Create a source-push trigger (Intermediate):**

```bash
gcloud builds triggers create github \
  --repo-name=my-app --repo-owner=my-org \
  --branch-pattern="^main$" \
  --build-config=cloudbuild.yaml
```

**Purpose:** Registers a trigger that runs `cloudbuild.yaml` automatically on every push to `main`.

**List recent build history (Beginner):**

```bash
gcloud builds list --limit=5
```

**Expected output:**

```
ID        CREATE_TIME          DURATION  SOURCE      IMAGES  STATUS
a1b2c3d4  2026-07-20T10:15:00  1M32S     main branch ...     SUCCESS
```

**Run a build in a private pool (Intermediate):**

```bash
gcloud builds submit --config=cloudbuild.yaml --worker-pool=projects/my-project/locations/us-central1/workerPools/my-private-pool .
```

**Purpose:** Forces the build to run on a VPC-peered private pool worker instead of the default public worker, so a step can reach an internal-only artifact mirror.

## 7. Production & Enterprise Usage

- **Least-privilege build service accounts:** Enterprises create a distinct service account per trigger (or per pipeline stage) with only the IAM roles that specific build needs, rather than granting the default Cloud Build service account project-wide `Editor`.
- **Build provenance and supply-chain security:** Cloud Build integrates with **SLSA build provenance** attestations and Binary Authorization (Section 43), letting a GKE/Cloud Run deploy step _require_ that an image was produced by a trusted, provenance-attested Cloud Build pipeline before it is allowed to run.
- **Private pools for regulated environments:** Organizations with data-residency or network-isolation requirements route all builds through private pools so build traffic never traverses Google's public worker fleet and can reach on-prem systems via existing Interconnect/VPN.
- **Approval gating on production triggers:** Production-deploy triggers are frequently left as **manual-only** (or wired through Cloud Deploy's approval gates, Section 51) rather than auto-firing on merge, keeping a human decision point before customer-facing environments change.

## 8. Common Misconceptions

- **Misconception:** "Cloud Build is only for building container images." In reality, Cloud Build steps can run any containerized command — compiling non-container binaries, running test suites, generating documentation, executing Terraform, or deploying — the "image" framing is just the most common use case, not the only one.
- **Misconception:** "A pull request trigger automatically blocks a bad merge." Cloud Build only _runs_ the build and reports a status check; the branch protection rule that actually blocks merging on a failed check must be configured separately in the source repository (e.g., GitHub branch protection), not in Cloud Build itself.

## 9. Interview Questions

**🎯 Beginner:** _What is the difference between a source push trigger and a manual trigger in Cloud Build?_
**Model answer:** A source push trigger fires automatically whenever a commit matching a configured branch or tag pattern is pushed to a connected repository, requiring no human action. A manual trigger is stored the same way but only runs when explicitly invoked — via the console, `gcloud builds triggers run`, or `gcloud builds submit` for an ad hoc build — commonly used for production deployments where a human decision point is wanted before the pipeline runs.

**🎯 Intermediate:** _Why would a build need a private pool instead of the default worker pool?_
**Model answer:** The default Cloud Build worker pool runs on Google-managed infrastructure with no direct network path into a customer's VPC, so it cannot reach private resources like an internal package mirror, a private GKE control plane, or an on-prem system reachable only via Interconnect/VPN. A private pool is VPC-peered into the customer's network, giving build steps a route to those private resources, and additionally allows custom machine types for builds needing more CPU/memory than the default worker provides.

**🎯 Senior/Architect:** _Design a Cloud Build pipeline for a regulated fintech application that must prove every deployed image was built from reviewed, tested source and never tampered with before reaching production._
**Model answer:** I would connect the repository with pull-request triggers running lint/test steps as a required status check, so no code merges to `main` without passing review and automated tests. On merge to `main`, a source-push trigger builds the image inside a private pool (isolating build traffic from the public internet and enabling network egress controls), runs a container vulnerability scan step, and pushes the image to Artifact Registry with SLSA build provenance attached, generated automatically by Cloud Build. I would configure Binary Authorization (Section 43) on the target GKE/Cloud Run environment to require that provenance attestation before any image is allowed to run, so an image built outside this exact pipeline — even if manually pushed to the same registry — is rejected at deploy time. Production promotion itself would go through Cloud Deploy (Section 51) with a mandatory manual approval gate, so build automation handles everything up to "ready to release," but a human explicitly approves the production rollout, keeping the build service account's permissions narrowly scoped to build-and-push only, never to production deploy.

## 10. Key Takeaways

- 🔑 Cloud Build runs builds as an ordered sequence of container-image steps defined in `cloudbuild.yaml`, triggered by source pushes, pull requests, Pub/Sub messages, or manual invocation.
- 🔑 Build steps run as an IAM service account, so pushing to Artifact Registry or deploying to Cloud Run/GKE requires only a role grant — not a separately managed credential.
- 🔑 Private pools are VPC-peered worker pools needed to reach private/internal resources or to use custom machine types; the default worker pool has no path into your VPC.
- 🔑 Cloud Build pairs with Cloud Deploy (Section 51) for managed, gated continuous delivery, and with Binary Authorization (Section 43) for supply-chain provenance enforcement.

## 11. Related Concepts

Cloud Deploy for managed continuous delivery (Section 51), Terraform on GCP for pipeline-defined infrastructure (Section 52), Artifact Registry as the image destination (Section 29), Binary Authorization for provenance enforcement (Section 43), and the GCP vs. AWS vs. Azure comparison (Section 82) all connect directly to the CI/CD model introduced here.
