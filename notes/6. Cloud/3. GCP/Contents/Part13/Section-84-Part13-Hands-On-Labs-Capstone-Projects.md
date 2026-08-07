# Section 84 (Part 13): Hands-On Labs & Capstone Projects

## 1. Definition

**Plain language:** Reading about a service and actually deploying it are different skills — real operational intuition (what a misconfigured IAM binding actually looks like when it breaks, how long a GKE upgrade actually takes, what a Dataflow job's autoscaling actually does under load) only comes from building something real and watching it behave. This section is five progressively harder hands-on projects that exercise the services covered across this entire knowledge base, from a first deployable application through a secured, monitored generative AI platform.

**Precise:** Five capstone labs of increasing scope and difficulty, each specifying its objective, the GCP services and knowledge-base sections it exercises, and an explicit "done when" checklist to make completion unambiguous rather than open-ended.

> 💡 **Tip:** Build these on a dedicated, low-spend GCP project (or the free-tier/trial credits), and set a billing budget alert ([Section 57](../Part8/Section-57-Part8-Cost-Optimization-FinOps.md)) before starting Lab 1 — several of these labs provision billable resources (Cloud SQL instances, GKE clusters, Dataflow jobs) that should be torn down promptly after each lab is verified complete.

## 2. Why This Progression

Each lab is deliberately scoped to exercise a different Part's core services while reusing what the previous lab already proved: Lab 1 is a single deployable application; Lab 2 shifts to data movement and analytics; Lab 3 shifts to container platform security; Lab 4 zooms out to the organizational/governance layer that should have existed _before_ Labs 1–3 in a real enterprise; and Lab 5 folds AI/ML on top of all of it, deployed inside the governed foundation Lab 4 built. Working them in order mirrors the dependency order a real platform team would actually encounter, rather than treating each service as an isolated demo.

> ⚠️ **Sequencing note:** Lab 4 conceptually belongs "before" Labs 1–3 in a real organization (workloads should land inside a governed landing zone from day one), but is sequenced fourth here deliberately — building the individual application, data, and platform patterns first makes the _purpose_ of the landing zone's guardrails concrete rather than abstract when you reach it.

**Prerequisites by lab:** Labs 1–3 need only a single GCP project with billing enabled and Owner/Editor on that project. Lab 4 needs Organization Admin (or a folder delegated with equivalent permissions) since it provisions folders and org policies, which do not exist below the organization node. Lab 5 needs everything Lab 4 needs, plus Vertex AI API access enabled, which is not on by default in a fresh project.

## 3. Lab 1 — Three-Tier Web Application

**Scope:** Deploy a standard three-tier web application: a stateless application layer on Cloud Run, a managed relational database on Cloud SQL, and a Cloud Load Balancing front end distributing traffic to the application layer over HTTPS.

**Estimated effort:** A weekend for a first attempt; a few hours once the pattern is familiar.

**Services / sections exercised:** Cloud Run ([Section 7](../Part1/Section-07-Part1-Cloud-Run.md)), Cloud SQL ([Section 13](../Part2/Section-13-Part2-Cloud-SQL.md)), Cloud Load Balancing ([Section 22](../Part3/Section-22-Part3-Cloud-Load-Balancing.md)), VPC fundamentals and firewall rules for restricting direct database access (Sections 19, 21), Secret Manager for database credentials ([Section 38](../Part5/Section-38-Part5-Secret-Manager-Cloud-KMS.md)), and basic IAM service-account scoping for the Cloud Run service identity (Sections 35–36).

**Done when:**

- [ ] The application is reachable only through the load balancer's HTTPS endpoint (a managed SSL certificate, not a self-signed one).
- [ ] Cloud Run connects to Cloud SQL via a private connection (Cloud SQL Auth Proxy or private IP), not a publicly exposed database IP.
- [ ] Database credentials are read from Secret Manager at runtime, never hardcoded or stored in a container image or environment file.
- [ ] The Cloud Run service account has only the specific IAM roles it needs (Cloud SQL Client, Secret Manager Secret Accessor) — not `Editor` or `Owner`.
- [ ] Load is verified by generating traffic and confirming autoscaling in Cloud Run's revision metrics.

**Stretch goal:** Add a Cloud CDN layer in front of the load balancer for static assets, and measure the cache-hit ratio improvement.

## 4. Lab 2 — Streaming Data Pipeline

**Scope:** Build an end-to-end streaming data pipeline: simulated events published to Pub/Sub, transformed and enriched by a Dataflow streaming job, landed in BigQuery, and visualized in a live Looker Studio dashboard.

**Estimated effort:** A long weekend — Dataflow job authoring and debugging windowed transforms is typically the slowest part.

**Services / sections exercised:** Pub/Sub ([Section 45](../Part6/Section-45-Part6-Dataflow-Dataproc-PubSub.md)), Dataflow ([Section 45](../Part6/Section-45-Part6-Dataflow-Dataproc-PubSub.md)), BigQuery ([Section 44](../Part6/Section-44-Part6-BigQuery-Deep-Dive.md)), Looker Studio ([Section 48](../Part6/Section-48-Part6-Looker-Looker-Studio.md)), and Dataplex tagging/cataloging of the resulting BigQuery dataset for governance ([Section 47](../Part6/Section-47-Part6-Dataplex-Data-Governance-Catalog.md)).

**Done when:**

- [ ] A publisher script or Cloud Scheduler-triggered job produces a continuous stream of realistic sample events to a Pub/Sub topic.
- [ ] A Dataflow streaming job (Beam pipeline, template or custom) consumes the subscription, performs at least one meaningful transformation (windowing, aggregation, or enrichment join), and writes to a partitioned BigQuery table.
- [ ] The BigQuery table is registered and tagged in Dataplex with at least a basic data-quality or classification tag.
- [ ] A Looker Studio dashboard queries the BigQuery table directly and reflects new data within the pipeline's expected end-to-end latency.
- [ ] The pipeline survives a deliberate burst of 10x normal event volume without data loss (verify via Pub/Sub subscription backlog metrics returning to zero).

**Stretch goal:** Add a Cloud Composer DAG ([Section 46](../Part6/Section-46-Part6-Cloud-Composer-Workflow-Orchestration.md)) that orchestrates a daily batch reconciliation job against the same BigQuery table, demonstrating batch and streaming coexisting over one dataset.

## 5. Lab 3 — Secured GKE Cluster

**Scope:** Stand up a production-patterned GKE cluster with Workload Identity for pod-to-GCP-API authentication, Binary Authorization enforcing that only signed, approved images can run, and Cloud Armor protecting the cluster's ingress from common web attacks.

**Estimated effort:** A full week for a first attempt — Binary Authorization attestation setup and Cloud Armor policy tuning both have real learning curves.

**Services / sections exercised:** GKE architecture ([Section 30](../Part4/Section-30-Part4-GKE-Architecture-Deep-Dive.md)), GKE networking ([Section 31](../Part4/Section-31-Part4-GKE-Networking-and-Storage.md)), Workload Identity ([Section 33](../Part4/Section-33-Part4-GKE-Security-Workload-Identity.md)), Binary Authorization ([Section 43](../Part5/Section-43-Part5-Binary-Authorization-Confidential-Computing.md)), Cloud Armor ([Section 74](../Part11/Section-74-Part11-Cloud-Armor-Edge-Security.md)), and Artifact Registry as the image source for the signing/attestation flow ([Section 29](../Part4/Section-29-Part4-Artifact-Registry-Container-Registry.md)).

**Done when:**

- [ ] The cluster runs with Workload Identity enabled, and at least one workload accesses a GCP API (e.g., reading a Secret Manager secret) using a federated Kubernetes service account — no downloaded service-account key files anywhere in the cluster.
- [ ] Binary Authorization is configured with a policy requiring at least one attestor; an attempt to deploy an unsigned/unattested image is demonstrably blocked.
- [ ] Container images are built and stored in Artifact Registry, with the attestation created as part of (or immediately after) the build.
- [ ] An Ingress or Gateway fronting the cluster has a Cloud Armor security policy attached, with at least one WAF rule verified by triggering it deliberately (e.g., a request matching an OWASP rule) and confirming it's blocked.
- [ ] Network policy or namespace segmentation restricts which workloads can reach which others (verify with a deliberate cross-namespace connection attempt that fails as expected).

**Stretch goal:** Add a GKE node auto-upgrade and surge-upgrade configuration ([Section 34](../Part4/Section-34-Part4-GKE-Operations-Scaling-Upgrades.md)), then trigger a manual upgrade and confirm zero dropped requests against a continuously polled health-check endpoint during the rollout.

## 6. Lab 4 — Enterprise Landing Zone

**Scope:** Build an enterprise landing zone in Terraform following the folder/policy/networking/logging patterns from Sections 59–63: a folder hierarchy with environment separation, an org-policy baseline, centralized logging and security projects, a Shared VPC, and an automated project-vending mechanism.

**Estimated effort:** One to two weeks — this lab is intentionally the most organizationally complex, since it models governance work rather than a single deployable workload.

**Services / sections exercised:** Landing Zone Architecture Blueprints ([Section 59](../Part9/Section-59-Part9-Landing-Zone-Architecture-Blueprints.md)), Organization Policy Hierarchy ([Section 60](../Part9/Section-60-Part9-Organization-Policy-Hierarchy-Deep-Dive.md)), Centralized Logging & Security Projects ([Section 61](../Part9/Section-61-Part9-Centralized-Logging-Security-Projects.md)), Shared VPC at Scale ([Section 62](../Part9/Section-62-Part9-Shared-VPC-at-Scale.md)), Folder/Project Vending Automation ([Section 63](../Part9/Section-63-Part9-Folder-Project-Vending-Automation.md)), and Terraform on GCP as the implementation tool ([Section 52](../Part7/Section-52-Part7-Terraform-on-GCP-Deployment-Manager.md)).

**Done when:**

- [ ] A folder hierarchy exists (e.g., `prod`/`nonprod`/`sandbox`) with at least three org policy constraints enforced at the appropriate folder level and verified to inherit correctly to a test project beneath it.
- [ ] A centralized logging project aggregates audit and platform logs from at least two workload projects via log sinks.
- [ ] A Shared VPC host project is configured with at least one service project attached, demonstrating centralized network administration.
- [ ] A Terraform module (or equivalent script-driven process) can provision a new, policy-compliant project from a single input (team name/environment) without manual console steps — this is the project-vending automation.
- [ ] The entire landing zone is defined as Terraform code in version control, with a documented `plan`/`apply` workflow — no resource in the landing zone was created by hand through the console.

**Stretch goal:** Retrofit Labs 1–3's resources so they're provisioned inside a project vended by this landing zone rather than a standalone project, and confirm the org policies from [Section 60](../Part9/Section-60-Part9-Organization-Policy-Hierarchy-Deep-Dive.md) now apply to them automatically.

## 7. Lab 5 — Capstone: Secured Generative AI Platform

**Scope:** The most demanding lab, combining nearly everything prior: a retrieval-augmented generation (RAG) application using Vertex AI and Vertex AI Search, served through Cloud Run, deployed _inside_ the Lab 4 landing zone, with monitoring and a documented disaster-recovery plan.

**Estimated effort:** Two or more weeks, and only realistic once Labs 1–4 are complete — this is the capstone, not a starting point.

**Services / sections exercised:** Vertex AI fundamentals and generative AI (Sections 65, 68), Vertex AI Search for grounding ([Section 67](../Part10/Section-67-Part10-AutoML-Model-Garden.md)), Cloud Run for the application layer ([Section 7](../Part1/Section-07-Part1-Cloud-Run.md)), the Lab 4 landing zone as the deployment target (Sections 59–63), Cloud Monitoring and Logging for observability ([Section 54](../Part7/Section-54-Part7-Cloud-Monitoring-Logging-Trace-Profiler.md)), VPC Service Controls scoping the AI project's data boundary ([Section 41](../Part5/Section-41-Part5-VPC-Service-Controls.md)), MLOps practices for any custom model component ([Section 69](../Part10/Section-69-Part10-MLOps-on-GCP.md)), responsible-AI review ([Section 70](../Part10/Section-70-Part10-AIML-Security-Responsible-AI.md)), and a disaster-recovery plan following [Section 58](../Part8/Section-58-Part8-Disaster-Recovery-Multi-Region-Architecture.md)'s RTO/RPO framework.

**Done when:**

- [ ] A document corpus is indexed in Vertex AI Search, and a Cloud Run application retrieves relevant grounding context from it before calling a generative model, demonstrably reducing hallucinated answers versus an ungrounded baseline (show at least one before/after example).
- [ ] The application is deployed inside a project provisioned through the Lab 4 landing zone's vending mechanism, inheriting its org-policy baseline and Shared VPC networking — not a standalone unmanaged project.
- [ ] A VPC Service Controls perimeter scopes the AI project, and an attempted data-exfiltration path (e.g., copying data to an external, non-perimeter project) is demonstrably blocked.
- [ ] Cloud Monitoring dashboards track request latency, error rate, and token/cost usage; at least one alert (e.g., latency SLO breach) is configured and verified by triggering it.
- [ ] A documented responsible-AI review checklist (safety filtering, evaluation for hallucination rate, escalation path for flagged outputs) is completed before the "launch."
- [ ] A written DR plan states the platform's RTO/RPO targets and the specific mechanism that meets them (e.g., multi-region Vertex AI Search index replication, Cloud Run's inherently multi-zonal nature) — and at least one element of the plan is actually tested, not just documented.

**Stretch goal:** Run a [Section 79](../Part12/Section-79-Part12-Chaos-Engineering-Tooling.md)-style chaos experiment against the Lab 5 platform (e.g., simulate the primary region becoming unavailable) and measure the actual failover time against the documented RTO target.

## 8. Common Pitfalls Across These Labs

- ⚠️ **Skipping the "done when" verification steps.** It's tempting to declare a lab complete once a resource exists and looks correct in the console — but a Binary Authorization policy that was never actually tested against an unsigned image, or a VPC Service Controls perimeter never actually probed with a real exfiltration attempt, may silently be misconfigured and permissive. Every checklist item above is written to require triggering the control, not just configuring it.
- ⚠️ **Building each lab in total isolation.** Labs 1–3 are written so they can technically be built standalone, but the real value of Labs 4 and 5 comes from retrofitting earlier labs' resources into the landing zone rather than building the capstone from a blank slate — this is what makes the progression feel like one platform instead of five disconnected demos.
- ⚠️ **Leaving billable resources running.** GKE clusters, Cloud SQL instances, and long-running Dataflow jobs accrue cost continuously; the [Section 84](./Section-84-Part13-Hands-On-Labs-Capstone-Projects.md).1 tip about a billing budget alert exists specifically because these are the resources most likely to be forgotten after a lab is verified complete.
- ⚠️ **Treating IAM scoping as an afterthought.** Every lab's checklist includes a least-privilege IAM verification step deliberately — it's easy to grant `Editor` to unblock a lab quickly and never revisit it, which defeats the point of practicing production-realistic patterns.

## 9. Key Takeaways

- 🔑 Each lab is deliberately cumulative — Lab 5 assumes Lab 4's landing zone exists, and reuses Lab 1–3's compute/data patterns inside it, mirroring how real platforms actually get built.
- 🔑 "Done when" checklists are written to require _verification_, not just configuration — a control that hasn't been deliberately triggered and observed to work (a blocked exfiltration attempt, a fired alert, a rejected unsigned image) isn't actually proven yet.
- 🔑 Every lab maps back to specific sections in Parts 1–12 and [Section 83](./Section-83-Part13-Interview-Preparation-Consolidated.md)'s question bank — building these labs is the single most effective way to convert that question bank's answers from memorized to genuinely understood.
- 🔑 Tear down billable resources (GKE clusters, Cloud SQL instances, Dataflow jobs) promptly after verifying each lab's checklist — these labs are learning exercises, not workloads meant to run indefinitely.

## 10. Related Concepts

These labs are the applied counterpart to [Section 83](./Section-83-Part13-Interview-Preparation-Consolidated.md)'s interview question bank and draw on Sections 7, 13, 14, 22, 29–34, 38, 41, 43–52, 54, 57–74 collectively; [Section 85](./Section-85-Part13-Key-Takeaways-Next-Learning-Path.md) closes the knowledge base by mapping which of these labs matter most for which specific career path and certification goal.
