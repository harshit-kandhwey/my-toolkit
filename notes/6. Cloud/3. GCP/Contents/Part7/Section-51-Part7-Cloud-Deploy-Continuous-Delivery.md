# Section 51 (Part 7): Cloud Deploy — Continuous Delivery

## 1. Definition

**Plain language:** Cloud Deploy is Google's managed service for taking an already-built application artifact (a container image) and _rolling it out_ through a defined sequence of environments — say, dev, then staging, then production — automatically or with human approval gates in between, and giving you a one-click way to roll back if something breaks.

**Precise:** Cloud Deploy is a managed continuous delivery service that executes **delivery pipelines** — declaratively defined sequences of **targets** (deployable environments backed by GKE clusters or Cloud Run services) — creating a **release** from a built artifact, automatically **promoting** it target-by-target according to configured approval and strategy rules, and retaining rollout history to support one-command **rollbacks**.

## 2. Why It Exists / Problem It Solves

Cloud Build (Section 50) can absolutely run a `gcloud run deploy` or `kubectl apply` as its final step, but that approach has real gaps once an application needs to move through multiple environments with governance:

- **No first-class notion of promotion.** A raw Cloud Build pipeline treats "deploy to staging" and "deploy to production" as two independent builds; there's no built-in concept of "the exact same artifact that passed staging is what goes to production," which is precisely the guarantee most release processes need.
- **No native approval gating on promotion.** Requiring a human to approve a production rollout means custom logic (manual trigger, external ticketing integration) rather than a first-class pipeline feature.
- **No built-in rollout history/rollback.** Reverting to a previous known-good version means re-running an old build or manually reapplying an old manifest, rather than clicking "rollback" against a tracked deployment history.

Cloud Deploy exists to formalize "move this specific artifact through these environments, in this order, with these gates and this rollout strategy" as a managed, auditable resource, separate from the build/test process that produces the artifact in the first place.

## 3. Core Concepts

### 3.1 Delivery Pipelines and Targets

A **delivery pipeline** is a declarative resource (`clouddeploy.yaml`) defining an ordered sequence of **targets** (also called **stages**) — each a deployable destination such as a specific GKE cluster/namespace or a specific Cloud Run service/region:

```yaml
apiVersion: deploy.cloud.google.com/v1
kind: DeliveryPipeline
metadata:
  name: my-app-pipeline
serialPipeline:
  stages:
    - targetId: dev
    - targetId: staging
      profiles: [staging]
    - targetId: prod
      profiles: [prod]
      strategy:
        standard:
          verify: true
```

Each `targetId` references a separately defined `Target` resource specifying the actual GKE cluster or Cloud Run service/region, and optionally a `requireApproval: true` flag gating promotion into that target.

### 3.2 Releases and Rollouts

A **release** is a snapshot of a specific application version (rendered Kubernetes manifests or a Cloud Run service definition, referencing a specific built image) submitted into the pipeline. Cloud Deploy creates a **rollout** for the first target automatically; a rollout is the actual act of deploying that release's artifact into one specific target. Promotion to the next target creates a new rollout of the _same release_ (not a new build), which is the mechanism guaranteeing that what reaches production is byte-for-byte identical to what passed staging.

### 3.3 Promotion Sequences

**Promotion** is advancing a release from one target to the next in the pipeline's defined order. Promotion can be:

- **Automatic:** The next target's rollout is created immediately once the current target's rollout succeeds (and, if configured, its verification passes).
- **Manual:** An operator explicitly runs `gcloud deploy releases promote` to advance the release to the next target — the common choice once a pipeline reaches a pre-production or production target.

### 3.4 Approvals

A target configured with `requireApproval: true` pauses the rollout in a **pending approval** state before it deploys, requiring an authorized approver (a specific IAM role, `roles/clouddeploy.approver`) to explicitly approve or reject via console, `gcloud deploy releases approve`, or API before the rollout proceeds. This is Cloud Deploy's first-class mechanism for a human gate before production changes, rather than a bolted-on manual trigger.

### 3.5 Deployment/Rollout Strategies

- **Standard:** Deploy the full release directly to the target (optionally followed by a **verify** step, an arbitrary container job checking the deployment is healthy before marking the rollout successful).
- **Canary:** Route a small percentage of traffic to the new version first (e.g., 25%, then 50%, then 100%), pausing between phases — supported for both GKE (via traffic-split routing) and Cloud Run (via revision traffic percentages) — reducing blast radius if the new version has a defect.

### 3.6 Rollbacks

Because Cloud Deploy retains a full history of rollouts per target, reverting is a single command (`gcloud deploy targets rollback`) that redeploys the last known-good release to a target — no rebuild, no reapplying manifests by hand, and no ambiguity about exactly what "known-good" refers to, since it points at a specific tracked release.

## 4. Architecture Diagram

```
            Cloud Build (Section 50) produces image + rendered manifest
                                    │
                                    ▼
                          gcloud deploy releases create
                                    │
                                    ▼
        ┌────────────────────────────────────────────────────────────┐
        │                      Delivery Pipeline                     │
        │                                                            │
        │  ┌────────┐   auto   ┌─────────┐  manual   ┌────────┐      |
        │  │  dev   │ ───────► │ staging │ ───────►  │  prod  │      |
        │  │(GKE ns)│  promote │(GKE ns) │  promote  │(Cloud  │      |
        │  │        │          │         │ +approval │  Run)  │      |
        │  └────────┘          └─────────┘  gate     └────────┘      |
        │      rollout             rollout           requireApproval |
        │     (same release across every target — never rebuilt)     │
        └────────────────────────────────────────────────────────────┘
                        │
                        ▼
           Rollout history retained per target
           ► gcloud deploy targets rollback (one command,
             redeploys last known-good release)
```

## 5. Comparison vs. AWS CodeDeploy and Azure DevOps Release Pipelines / Deployment Slots

| Concept                      | GCP Cloud Deploy                                                 | AWS CodeDeploy                                                     | Azure DevOps Release Pipelines / Slots                        |
| ---------------------------- | ---------------------------------------------------------------- | ------------------------------------------------------------------ | ------------------------------------------------------------- |
| Core unit promoted           | Release (same artifact promoted target-to-target)                | Deployment (per-application-revision, per-environment)             | Release (build artifact promoted through stages)              |
| Multi-environment sequencing | Native `DeliveryPipeline` with ordered targets                   | Composed via CodePipeline stages calling CodeDeploy per stage      | Native multi-stage release pipeline                           |
| Approval gates               | `requireApproval` on a target, IAM-gated approver role           | Manual approval action in CodePipeline                             | Pre-deployment approvals per stage                            |
| Canary/traffic-shifting      | Built-in canary strategy for GKE and Cloud Run                   | Deployment configs (linear/canary) for EC2/ECS/Lambda              | Deployment slots (App Service) or ring-based rollout patterns |
| Rollback mechanism           | `gcloud deploy targets rollback` against tracked rollout history | Automatic rollback on CloudWatch alarm trigger, or manual redeploy | Redeploy previous release from history                        |
| Deploy targets               | GKE, Cloud Run                                                   | EC2, ECS, Lambda, on-prem                                          | App Service, VMs, Kubernetes (via extensions)                 |

## 6. Hands-On Examples

**Create a delivery pipeline and targets (Beginner):**

```bash
gcloud deploy apply --file=clouddeploy.yaml --region=us-central1
```

**Purpose:** Registers the `DeliveryPipeline` and its `Target` resources (dev, staging, prod) defined in the YAML file.

**Create a release (Intermediate):**

```bash
gcloud deploy releases create release-001 \
  --delivery-pipeline=my-app-pipeline \
  --region=us-central1 \
  --images=my-app=us-central1-docker.pkg.dev/my-project/my-repo/app:v1
```

**Purpose:** Submits a new release, automatically creating and deploying the first rollout to the `dev` target.
**Expected output (abbreviated):**

```
Created Cloud Deploy release release-001.
Rollout release-001-to-dev-0001 created and deploying.
```

**Promote to the next target (Intermediate):**

```bash
gcloud deploy releases promote --release=release-001 --delivery-pipeline=my-app-pipeline --region=us-central1
```

**Approve a pending production rollout (Intermediate):**

```bash
gcloud deploy rollouts approve rollout-id --release=release-001 --delivery-pipeline=my-app-pipeline --target-id=prod --region=us-central1
```

**Roll back a target to its last known-good release (Intermediate-Advanced):**

```bash
gcloud deploy targets rollback prod --delivery-pipeline=my-app-pipeline --region=us-central1
```

**Expected output:** Confirms the target's most recent successful rollout is redeployed, without requiring a new release to be built.

## 7. Production & Enterprise Usage

- **Production gated, lower environments automatic:** Common enterprise pattern is auto-promotion dev→staging on every successful build, with `requireApproval: true` only on the production target, keeping velocity high in lower environments while preserving a human checkpoint before customer impact.
- **Canary for high-traffic services:** Customer-facing services with strict SLOs deploy via canary strategy (e.g., 10% → 50% → 100%) with automated verify steps checking error rates between phases, and configured to automatically halt promotion if the verify step fails.
- **Audit trail for compliance:** Every release, rollout, approval, and rollback is a tracked, queryable Cloud Deploy resource with an associated identity (via Cloud Audit Logs), giving regulated organizations a built-in "who approved what, when" record without custom tooling.
- **Multi-pipeline fan-out for microservices:** Organizations running many independently deployable services typically define one delivery pipeline per service (rather than one giant shared pipeline), so one service's rollback or stuck approval never blocks another's release.

## 8. Common Misconceptions

- **Misconception:** "Promoting a release rebuilds or re-images the application for the next environment." Promotion deploys the _exact same_ artifact/image that was validated in the prior target — that immutability guarantee is the entire point of Cloud Deploy; if you need a different image per environment, you're building separate releases, not promoting one.
- **Misconception:** "Rollback means redeploying an old Git commit." Rollback redeploys the last known-good tracked _rollout_ for that target, which Cloud Deploy already has recorded — no rebuild, no re-checkout, and no dependency on the build system being available at rollback time.

## 9. Interview Questions

**🎯 Beginner:** _What is the difference between a release and a rollout in Cloud Deploy?_
**Model answer:** A release is a snapshot of a specific application version submitted into a delivery pipeline, referencing a specific built artifact. A rollout is the act of deploying that release into one specific target — so a single release can have multiple rollouts over time (one per target as it's promoted through dev, staging, and production), while always referring back to the same underlying artifact.

**🎯 Intermediate:** _Why does Cloud Deploy guarantee the same artifact reaches every environment, and why does that matter?_
**Model answer:** Cloud Deploy's promotion operation deploys the same release object into the next target rather than creating a new build, so the exact container image (and rendered manifest) validated in staging is what reaches production, byte-for-byte. This matters because a huge class of production incidents historically came from "works in staging, breaks in prod" caused by a rebuild picking up a different dependency version, a different base image tag, or an unnoticed source change between the staging build and the production build — Cloud Deploy's model structurally eliminates that risk by never rebuilding between environments.

**🎯 Senior/Architect:** _Design a Cloud Deploy strategy for a customer-facing Cloud Run service with a strict 99.95% availability SLO, where a bad deploy must be caught and reverted with minimal customer impact._
**Model answer:** I would configure a delivery pipeline with dev (auto-promote), staging (auto-promote after an automated integration-test verify step), and prod using a canary strategy — say 10% traffic for an initial soak period, then 50%, then 100% — with a `requireApproval` gate before the canary begins, so a human explicitly authorizes each production release window even though the canary phases themselves progress automatically. I'd attach a verify step at each canary phase that queries Cloud Monitoring (Section 54) for error-rate and latency SLO burn over the soak window, configured to automatically halt promotion (rather than proceeding to the next traffic percentage) if the verify step detects an SLO violation, minimizing the blast radius to the initial 10% of traffic. If a bad rollout does reach a later phase or full traffic before detection, I'd rely on `gcloud deploy targets rollback` against the tracked rollout history to redeploy the last known-good release within seconds, rather than re-running the build pipeline, since the whole point of separating Cloud Build from Cloud Deploy is that rollback should never depend on the build system being available or fast under incident pressure.

## 10. Key Takeaways

- 🔑 Cloud Deploy formalizes multi-environment promotion as a first-class resource — a `DeliveryPipeline` of ordered `Target`s — separate from the build process that produces the artifact.
- 🔑 Promotion always deploys the same release/artifact to the next target, never a rebuild, guaranteeing what passed staging is exactly what reaches production.
- 🔑 `requireApproval` on a target is the native human-gate mechanism; canary strategies reduce blast radius for high-traffic production targets.
- 🔑 Rollback redeploys a tracked known-good rollout in one command, with no dependency on the build system being available at rollback time.

## 11. Related Concepts

Cloud Build as the upstream artifact producer (Section 50), GKE and Cloud Run as deploy targets (Sections 30 and 7), Cloud Monitoring for verify-step health signals (Section 54), Binary Authorization for provenance-gated deploys (Section 43), and the GCP vs. AWS vs. Azure comparison (Section 82) all connect directly to the continuous delivery model introduced here.
