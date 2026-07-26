# Section 1 (Part 1): What is GCP, History & Evolution, Problem It Solves

## 1. Definition

**Plain language:** Google Cloud Platform (GCP) is a collection of computing, storage, networking, database, and management services that Google rents out over the internet. Instead of buying physical servers and running them in your own data center, you "rent" virtual servers, storage, and higher-level managed services from Google, paying only for what you use.

**Precise:** GCP is a public cloud platform providing Infrastructure-as-a-Service (IaaS), Platform-as-a-Service (PaaS), and Software-as-a-Service (SaaS) offerings, built on top of Google's global physical infrastructure (data centers, fiber-optic network backbone, and custom hardware). It exposes these capabilities via web console, REST APIs, command-line tools (`gcloud`, `gsutil`, `bq`), and client SDKs in multiple languages.

## 2. Why It Exists / Problem It Solves

Before public cloud platforms existed, every organization that needed compute capacity had to:

- **Buy physical hardware** (servers, storage arrays, network switches) months in advance based on guessed future demand — this is called **capital expenditure (CapEx)**.
- **Provision a physical data center** or rent rack space (colocation), requiring power, cooling, physical security, and staff to maintain it.
- **Over-provision for peak load.** If a retail site expects a 10x traffic spike on a sale day, it had to own enough hardware for that spike year-round, even though 90% of the year that hardware sits idle.
- **Wait weeks or months** for new hardware to be ordered, delivered, racked, and configured before a project could even start.
- **Manage hardware failures themselves** — disks fail, power supplies fail, and someone has to physically walk into the data center to replace parts.

GCP (and public cloud generally) solves this by converting infrastructure from a CapEx model to an **operational expenditure (OpEx)** model: you rent exactly the compute/storage/network capacity you need, when you need it, and release it when you don't. Google owns and maintains the physical hardware; you consume it as a service over the internet, provisioned in minutes instead of months.

## 3. What Existed Before It

- **On-premises data centers:** Organizations owned and operated their own hardware. Full control, but slow to scale, high CapEx, and required deep operational expertise (power, cooling, physical security, hardware replacement).
- **Colocation ("colo"):** Organizations owned the hardware but rented physical space, power, and cooling from a third-party facility. Reduced facility burden but hardware ownership and provisioning delays remained.
- **Managed hosting:** A provider owned and racked the hardware and rented dedicated or virtual servers, but with limited self-service automation and typically manual provisioning via support tickets.
- **Early public cloud (AWS launched 2006):** Amazon Web Services pioneered the modern self-service, API-driven, pay-as-you-go public cloud model years before Google or Microsoft entered the market.

## 4. History & Evolution of GCP

| Year      | Milestone                                                                                                                                                                                                                                                           |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 2008      | Google App Engine launched (Google's first public cloud product) — a PaaS for running Python/Java web apps without managing servers.                                                                                                                                |
| 2010      | Google Cloud Storage launched, providing object storage.                                                                                                                                                                                                            |
| 2012      | Google Compute Engine launched in limited preview — Google's IaaS virtual machine offering.                                                                                                                                                                         |
| 2013      | Compute Engine reaches General Availability. BigQuery (originally an internal tool, "Dremel") opened to the public.                                                                                                                                                 |
| 2015      | Google Cloud Platform is formally branded and unified as a suite ("GCP"), consolidating previously separate products under one console and billing system.                                                                                                          |
| 2016      | Google Kubernetes Engine (GKE) launched — a managed service for Kubernetes, the container-orchestration system Google open-sourced in 2014 based on its internal "Borg" system.                                                                                     |
| 2017–2018 | Rapid expansion of managed services: Cloud Functions (serverless), Cloud Spanner GA, Cloud IoT, expansion of AI/ML services (Vertex AI's predecessors).                                                                                                             |
| 2019      | Cloud Run launched — serverless containers, combining the simplicity of Cloud Functions with the flexibility of running any containerized workload.                                                                                                                 |
| 2020s     | Continued expansion: Anthos (hybrid/multi-cloud Kubernetes), BigQuery ML, expanded AI/ML platform (Vertex AI, consolidating prior ML tools), stronger enterprise security tooling (VPC Service Controls, Security Command Center), and continuous region expansion. |

> 💡 **Tip:** GCP's compute and container strategy is deeply informed by Google's own internal infrastructure history. Google ran containerized workloads internally at massive scale for over a decade (via a system called **Borg**) before Kubernetes — the open-source descendant of Borg's ideas — became an industry standard. This lineage is why GKE is widely regarded as one of the most mature managed Kubernetes offerings among cloud providers; it is not a bolt-on service, it reflects over a decade of Google's own operational experience running containers at scale.

## 5. Terminology (defined at first use)

- **Cloud computing:** The on-demand delivery of computing resources (servers, storage, databases, networking, software) over the internet, with pay-as-you-go pricing.
- **IaaS (Infrastructure as a Service):** The cloud provider gives you raw building blocks — virtual machines, storage, networks — and you are responsible for the operating system, runtime, and application. Example on GCP: Compute Engine.
- **PaaS (Platform as a Service):** The cloud provider manages the underlying infrastructure and operating system; you deploy just your application code. Example on GCP: App Engine.
- **SaaS (Software as a Service):** A complete, ready-to-use application delivered over the internet, with no infrastructure management by the consumer at all. Example: Google Workspace (Gmail, Docs) — not usually classified as "GCP" proper, but built on the same underlying infrastructure.
- **Serverless:** A deployment model where the cloud provider automatically manages server provisioning and scaling, including scaling down to zero when there's no traffic, so you are billed only for actual execution rather than for idle reserved capacity. Example on GCP: Cloud Functions, Cloud Run.
- **Region:** A specific geographic location (e.g., `us-central1` in Iowa, USA) where GCP resources are hosted, made up of multiple isolated zones (covered fully in Section 2).
- **Zone:** An isolated location within a region, roughly analogous to a single data center or cluster of data centers, used for placing resources to protect against localized failures (covered fully in Section 2).
- **Managed service:** A service where Google handles operational responsibilities like patching, backups, and high availability, in contrast to unmanaged services where you handle these yourself.
- **Console:** The GCP web-based graphical user interface (console.cloud.google.com) for managing resources.
- **`gcloud`:** The primary command-line interface (CLI) tool for interacting with most GCP services.
- **SLA (Service Level Agreement):** A contractual commitment from Google about a service's guaranteed uptime/availability, with financial credits owed if the commitment is missed.

## 6. Modern Use Cases

- **Web and mobile application hosting** — from simple websites (App Engine, Cloud Run) to complex multi-service backends (GKE).
- **Data warehousing and analytics** — organizations use BigQuery to run SQL analytics over petabytes of data without managing any database servers.
- **Machine learning and AI workloads** — GCP is a major provider of GPU/TPU compute for training and serving ML models, leveraging Google's own hardware (Tensor Processing Units).
- **Disaster recovery and backup** — using GCP as a secondary site or backup target for on-premises systems.
- **Hybrid and multi-cloud workloads** — via Anthos, organizations run consistent Kubernetes-based workloads across on-prem, GCP, AWS, and Azure.
- **Startups building cloud-native from day one** — avoiding any hardware ownership entirely, scaling serverless services with demand.
- **Enterprises migrating legacy data centers** — "lift and shift" of VMs into Compute Engine, followed by gradual modernization into managed services.

## 7. Industry Adoption

GCP is one of the three dominant global public cloud providers, alongside AWS (market leader) and Microsoft Azure (second place), commonly referred to as the "big three." GCP is generally regarded as the third-largest by market share, though it has particular strength and reputation advantages in **data analytics (BigQuery)**, **Kubernetes/containers (GKE)**, and **AI/ML workloads**, reflecting Google's own internal expertise in these areas.

> ⚠️ **Accuracy note:** Precise market share percentages change quarter to quarter and vary by which analyst firm publishes them — verify against current industry reports (e.g., Synergy Research Group, Gartner) rather than relying on any fixed number here, since this is exactly the kind of fast-changing metric that goes stale.

## 8. Prerequisites

- No prior cloud experience is required to start GCP.
- Basic familiarity with the command line (any OS) will help once we reach `gcloud` usage in Section 5 and onward.
- Basic understanding of client-server architecture (a "server" responds to requests from a "client") is helpful for later networking and compute sections.

## 9. Key Takeaways

- 🔑 GCP converts infrastructure from a CapEx (buy hardware upfront) model to an OpEx (pay for usage) model.
- 🔑 GCP evolved from Google's internal infrastructure experience — most notably, Kubernetes/GKE traces directly back to Google's internal Borg system.
- 🔑 GCP offers IaaS (Compute Engine), PaaS (App Engine), and serverless (Cloud Run, Cloud Functions) compute models, each trading off control for convenience differently — this trade-off is explored in depth in Section 10.
- 🔑 GCP's key differentiators in the market are BigQuery (analytics), GKE (Kubernetes), and AI/ML (Vertex AI, TPUs).

## 10. Related Concepts

Region/zone infrastructure (Section 2), resource hierarchy (Section 3), the compute service decision matrix (Section 10), and the GCP vs. AWS vs. Azure comparison (Section 82) all build directly on the concepts introduced here.
