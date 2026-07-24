# Section 34 — Docker on Azure Fundamentals

**Part 7: Containers & Orchestration | Section 34 of 70**
**Prerequisites:** Section 1 (What is Azure), Section 11 (Azure Virtual Machines), Section 13 (Azure App Service), Section 15 (Azure Container Instances)
**Leads into:** Section 35 (Azure Container Registry), Section 36–38 (Azure Kubernetes Service)

---

## 34.1 Introduction and Scope

This section builds the container fundamentals required before working with Azure's container services: Azure Container Registry (ACR), Azure Container Instances (ACI, already covered operationally in Section 15 but revisited here from the image/runtime perspective), Azure App Service for Containers, and Azure Kubernetes Service (AKS). Every Azure container service ultimately runs OCI-compliant container images produced by, or compatible with, Docker tooling. Without a solid grounding in what a container actually is and how Docker builds, stores, and runs one, the Azure-specific services in the rest of Part 7 and Part 8 cannot be understood at more than a surface level.

🔑 **Key Takeaway:** Docker is not an Azure product. It is the de facto standard tooling and image format (via the Open Container Initiative, OCI) that nearly every Azure container service consumes. Learning Docker here is a prerequisite investment, not a detour.

---

## 34.2 What Is Docker and What Problem It Solves

### 34.2.1 Definition

**Plain language:** Docker is a platform that packages an application together with everything it needs to run — code, runtime, system libraries, configuration — into a single unit called a **container image**, and then runs that image as an isolated, lightweight process called a **container**.

**Precise definition:** Docker is a set of platform-as-a-service tools that uses OS-level virtualization to deliver software in packages called containers. Containers are isolated from one another and from the host operating system, but share the host machine's kernel, which makes them far lighter weight than traditional virtual machines.

### 34.2.2 The Problem It Solves

Before containers became mainstream (roughly 2013 onward with Docker's public release), software teams faced a recurring and expensive problem commonly summarized as **"it works on my machine."**

- An application would be developed and tested on a developer's laptop with a specific OS version, library versions, and environment variables.
- That same application, deployed to a test server or production server, would behave differently or fail outright because the target environment had different library versions, missing dependencies, different OS patch levels, or conflicting versions of shared libraries required by other applications on the same host.
- Virtual machines solved *isolation* (each VM has its own full OS, so dependency conflicts between applications were eliminated) but at a heavy cost: each VM requires its own OS kernel, its own memory footprint for that OS, minutes to boot, and significant disk space (often gigabytes) — even before the application itself is installed.

Docker's core insight was that most of the isolation benefit of a VM can be achieved without a second kernel, by using features already built into the Linux kernel (namespaces and control groups, covered in 34.3) to isolate processes from one another while all of them share the *same* running kernel. This gives:

- **Consistency:** the same image runs identically on a developer laptop, a CI pipeline, a test environment, and Azure production infrastructure, because the image contains the full application dependency stack, not just the application code.
- **Density:** because containers do not each need a full OS, far more containers than VMs can run on the same physical or virtual hardware, and they start in milliseconds to a few seconds rather than minutes.
- **Portability:** an image built once can run on any host with a compatible container runtime — a developer's Windows or Mac laptop (via Docker Desktop's Linux VM), an on-premises Linux server, or any Azure container service.

### 34.2.3 What Existed Before Docker

- **Bare-metal or VM deployment with manual configuration:** operations teams manually installed and configured every dependency on every server, often using long-lived runbooks that drifted from reality over time ("configuration drift").
- **Configuration management tools (Puppet, Chef, early Ansible):** these automated the *installation* of dependencies onto long-lived servers, but did not solve isolation between applications on the same host, and the resulting server state was still a moving target that had to be reasoned about.
- **chroot and early Linux containers (LXC):** Docker did not invent OS-level virtualization. `chroot` (1979) provided filesystem isolation. LXC (2008) combined Linux namespaces and cgroups into a usable container toolset. Docker's contribution (2013) was not the underlying kernel technology but a dramatically simpler developer experience: a single `Dockerfile` format to build images, a single-command workflow to run them, and — critically — a public registry (Docker Hub) to share them, which drove mass adoption.

### 34.2.4 History and Evolution (Condensed — Focus on Azure Relevance)

- **2013:** Docker, Inc. (originally dotCloud) releases Docker as open source, popularizing containers for application delivery.
- **2015:** The **Open Container Initiative (OCI)** is founded by Docker and other industry players under the Linux Foundation, to standardize the container image format and runtime specification so that no single vendor controls the ecosystem. This matters directly for Azure: AKS, ACI, and ACR all operate on OCI-compliant images and runtimes, not on a Docker-specific format.
- **2017:** Docker donates its container runtime component (`containerd`) to the Cloud Native Computing Foundation (CNCF). `containerd` becomes the runtime used underneath Kubernetes (and therefore AKS) rather than the full Docker Engine.
- **2020–2022:** Kubernetes deprecates and removes direct "dockershim" support, moving to the Container Runtime Interface (CRI) and runtimes such as `containerd` directly. **This is why modern AKS node pools run `containerd` as the container runtime, not "Docker" in the historical sense** — a detail covered in depth in Section 36.
- **Present day:** "Docker" commonly refers to the Docker CLI/Engine used for local development and image building, while production container platforms (including AKS) typically run OCI images via `containerd` and `runc` directly, without the full Docker Engine installed on the node.

⚠️ **Warning:** A common point of confusion, including in interviews, is believing that Kubernetes (and therefore AKS) "runs Docker." As of the versions in common use today, AKS nodes run `containerd` as the CRI-compliant runtime. Docker Engine is typically only used on developer workstations and CI build agents to *build* the image; the image itself, once built, is a standard OCI artifact that any compliant runtime — including `containerd` — can run without Docker being present at runtime.

### 34.2.5 Terminology (Every Term Defined)

| Term | Definition |
|---|---|
| **Container** | A running instance of an image: an isolated process (or group of processes) with its own filesystem, network interfaces, and process namespace, sharing the host kernel. |
| **Image** | A read-only, layered template used to create containers. Contains application code, runtime, libraries, and metadata (entrypoint, exposed ports, environment defaults). |
| **Dockerfile** | A text file containing instructions that Docker reads to build an image, layer by layer. |
| **Layer** | An immutable, content-addressed filesystem diff produced by one Dockerfile instruction (mainly `RUN`, `COPY`, `ADD`). Images are stacks of layers. |
| **Registry** | A storage and distribution service for images (e.g., Docker Hub, Azure Container Registry). Organized into repositories and tags. |
| **Repository** | A named collection of related image versions in a registry (e.g., `myapp`), distinguished by tags (e.g., `myapp:1.0`, `myapp:latest`). |
| **Tag** | A human-readable label pointing to a specific image digest within a repository (e.g., `1.0`, `latest`, `sha256:...`). |
| **Docker Engine** | The client-server application that builds and runs containers, composed of the Docker daemon (`dockerd`), a REST API, and the `docker` CLI. |
| **`containerd`** | A CNCF container runtime that manages the container lifecycle (image transfer, storage, execution, supervision) on a host; used by Docker Engine internally and directly by Kubernetes/AKS. |
| **`runc`** | A low-level, OCI-compliant CLI tool that actually creates and runs containers using kernel primitives (namespaces, cgroups); invoked by `containerd`. |
| **OCI (Open Container Initiative)** | The Linux Foundation project defining open standards for container **images** (OCI Image Spec) and **runtimes** (OCI Runtime Spec), ensuring portability across tools and vendors. |
| **Namespace (kernel feature)** | A Linux kernel feature that isolates a specific type of system resource (process IDs, network interfaces, mount points, etc.) so that a container sees only its own isolated view. Not to be confused with a Kubernetes namespace. |
| **cgroups (control groups)** | A Linux kernel feature that limits and accounts for resource usage (CPU, memory, I/O) of a process group, preventing one container from starving others on the same host. |
| **Base image** | The starting image referenced in a Dockerfile's `FROM` instruction (e.g., `ubuntu:22.04`, `mcr.microsoft.com/dotnet/aspnet:8.0`). |
| **Multi-stage build** | A Dockerfile pattern using multiple `FROM` instructions to separate build-time dependencies from the final runtime image, reducing final image size (covered fully as its own roadmap section later in Part 7's Azure-specific build patterns and referenced again in Section 35). |
| **Volume** | Docker-managed persistent storage that exists outside a container's writable layer, surviving container removal. |
| **Bind mount** | A host filesystem path mapped directly into a container, used mainly in local development. |
| **Orchestrator** | A system (e.g., Kubernetes/AKS) that manages the lifecycle of many containers across many hosts: scheduling, scaling, self-healing, networking, and service discovery. |

### 34.2.6 Modern Use Cases and Industry Adoption

- **Microservices delivery:** each service is packaged as its own image with its own dependency stack, deployed and scaled independently.
- **CI/CD build artifacts:** container images have become the standard unit of deployment artifact in modern pipelines — a build produces an image, and that same image (never rebuilt) is promoted from dev through staging to production, guaranteeing what was tested is what ships.
- **Polyglot environments:** teams running services in different languages (Node.js, .NET, Python, Java) on the same cluster without dependency conflicts, since each container has its own isolated dependency stack.
- **Azure-specific consumption points:** Azure App Service (custom containers), Azure Container Instances (serverless single containers or container groups), Azure Kubernetes Service (full orchestration), Azure Container Apps, and Azure Functions (custom container support) all accept the same OCI image format described in this section.

### 34.2.7 Prerequisites for This Section

- Comfort with Linux command-line basics (helpful but not mandatory; Windows containers exist but this section, like most enterprise Azure container workloads, focuses primarily on Linux containers, which represent the overwhelming majority of Azure container workloads).
- A conceptual understanding of what a virtual machine is (Section 11) to contrast against containers in 34.3.
- No prior container experience is assumed beyond that.

---

## 34.3 Containers vs. Virtual Machines

### 34.3.1 Definition

A **virtual machine** virtualizes hardware: a hypervisor (Section 11 covered Azure's use of Hyper-V-based virtualization) presents virtual hardware to a full guest operating system, which boots its own kernel independently of the host.

A **container** virtualizes the operating system: all containers on a host share that host's single kernel, and are isolated from one another using kernel namespaces and cgroups rather than a hypervisor.

### 34.3.2 Comparison Table

| Aspect | Virtual Machine | Container |
|---|---|---|
| Isolation boundary | Hardware-level (hypervisor) | OS-level (kernel namespaces/cgroups) |
| Kernel | Each VM has its own kernel | All containers share the host kernel |
| Startup time | Minutes (full OS boot) | Milliseconds to a few seconds |
| Typical image/disk size | Gigabytes (full OS + app) | Megabytes to low hundreds of MB (app + minimal dependencies) |
| Density per host | Lower (tens per host typical) | Higher (hundreds possible per host) |
| OS diversity on one host | Any guest OS the hypervisor supports | Must be compatible with host kernel type (Linux containers need a Linux kernel; Windows containers need a compatible Windows kernel) |
| Security isolation strength | Strong (separate kernel = smaller shared attack surface) | Weaker by default (shared kernel = a kernel-level vulnerability can affect all containers); mitigated with hardening (34.9) |
| Primary Azure examples | Azure VMs, VM Scale Sets | ACI, AKS nodes' workloads, App Service containers |

💡 **Tip:** In production Azure architectures, these are not competing choices — they are layered. AKS nodes, for example, **are themselves Azure VMs** (Section 11 concepts apply directly), and each node then runs many containers on top of that VM's single Linux kernel. Understanding both layers is essential for capacity planning and troubleshooting in Sections 36–38.

### 34.3.3 Why This Matters for Interviews

🎯 **Interview Tip:** A very common question is "why not just use VMs for everything?" The strong answer is not "containers are strictly better" — it is a trade-off explanation: containers offer density, speed, and consistency at the cost of a weaker isolation boundary (shared kernel) and OS-family constraints (a Linux container cannot run on a Windows-only kernel without a compatibility layer). Interviewers are probing whether the candidate understands *why* the trade-off exists at the kernel level, not just that containers are "faster."

---

## 34.4 Docker Architecture

### 34.4.1 Definition

Docker's architecture is a **client-server model** composed of four cooperating layers: the Docker CLI (client), the Docker daemon (`dockerd`), the container runtime (`containerd`), and the low-level runtime (`runc`), with images and containers as the artifacts they operate on.

### 34.4.2 Components and Interactions

```
┌───────────────────────────────────────────────────────────────┐
│                         Docker Client                          │
│              (docker CLI, Docker Desktop, SDKs)                │
└───────────────────────────┬─────────────────────────────────────┘
                              │ REST API over Unix socket / TCP
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                     Docker Daemon (dockerd)                     │
│  - Receives API requests (build, run, pull, push, etc.)         │
│  - Manages images, networks, volumes                            │
│  - Delegates container lifecycle to containerd                  │
└───────────────────────────┬─────────────────────────────────────┘
                              │ gRPC
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                          containerd                             │
│  - Image pull/push, storage/snapshot management                │
│  - Container lifecycle supervision                              │
│  - Invokes runc per container                                   │
└───────────────────────────┬─────────────────────────────────────┘
                              │ OCI Runtime Spec
                              ▼
┌───────────────────────────────────────────────────────────────┐
│                             runc                                │
│  - Creates namespaces (pid, net, mnt, uts, ipc, user)            │
│  - Applies cgroup resource limits                                │
│  - Executes the container's process(es) directly on the kernel   │
└───────────────────────────────────────────────────────────────┘
```

- **Docker Client:** the `docker` command-line tool (or any tool speaking the Docker Engine API, including Docker Desktop's UI). It sends commands such as `docker build`, `docker run`, and `docker pull` to the daemon and never touches containers directly itself.
- **Docker Daemon (`dockerd`):** a long-running background service that listens for API requests, manages higher-level objects (images, networks, volumes, build cache), and delegates the actual container execution to `containerd`.
- **`containerd`:** a CNCF-graduated project responsible for the full container lifecycle on a host — pulling and unpacking images, managing storage snapshots, and starting/stopping/monitoring containers by invoking `runc`. This is the same component Kubernetes/AKS uses directly, bypassing `dockerd` entirely in production clusters.
- **`runc`:** the component that actually talks to the Linux kernel. It reads an OCI runtime bundle (a filesystem plus a `config.json` describing namespaces, cgroups, capabilities, and mounts) and creates the container process.

### 34.4.3 Lifecycle / Workflow

1. Developer runs `docker build` → Docker Client sends the Dockerfile and build context to `dockerd`.
2. `dockerd` builds the image layer by layer (34.6) and stores it locally, using `containerd`'s snapshotter for layer storage.
3. Developer runs `docker run myimage` → `dockerd` asks `containerd` to create a container from the image.
4. `containerd` unpacks the image's layers into a writable container filesystem and invokes `runc` with an OCI runtime bundle.
5. `runc` creates the kernel namespaces and cgroup, then executes the image's defined entrypoint process inside that isolated environment, and exits — `containerd` keeps supervising the running process afterward (this "runc exits after creating the container" detail is why `containerd`, not `runc`, is the long-lived supervisor).
6. Container runs until it exits, is stopped, or is removed; its writable layer is discarded on removal unless a volume was used (34.10).

### 34.4.4 Under-the-Hood Kernel Mechanisms

- **Namespaces** provide the *isolated view*: a `pid` namespace makes a container see only its own processes (starting from PID 1 inside the container); a `net` namespace gives it its own network stack (interfaces, routing table, ports); `mnt` isolates the filesystem mount points; `uts` isolates hostname; `ipc` isolates inter-process communication primitives; `user` (optional, security-relevant, see 34.9) isolates user/group ID mappings.
- **cgroups** provide the *resource limits*: CPU shares/quotas, memory limits (with OOM-kill behavior when exceeded), block I/O throttling, and process count limits, all enforced by the kernel per container.
- **Union/layered filesystem (commonly OverlayFS on Linux):** combines the image's read-only layers with a thin writable layer added at container start, so multiple containers can share the same underlying image layers on disk without duplication, while each container's writes are isolated to its own layer.

### 34.4.5 Interview Questions — Docker Architecture

**Beginner:** "What are the main components of Docker's architecture?"
*Model answer:* The Docker CLI sends commands to the Docker daemon over a REST API. The daemon manages images, networks, and volumes, and delegates actual container execution to containerd, which in turn uses runc to create the isolated process using Linux namespaces and cgroups.
*What the interviewer is probing:* whether the candidate has only used `docker run` as a black box or actually understands the layered architecture.

**Senior:** "Why does Kubernetes not require Docker to be installed on a node?"
*Model answer:* Kubernetes only requires a CRI (Container Runtime Interface)-compliant runtime, such as containerd or CRI-O. Docker Engine's `dockerd` was historically used via a compatibility shim called dockershim, which Kubernetes removed. Since containerd already sits underneath Docker Engine and directly implements the CRI, modern Kubernetes distributions including AKS talk to containerd directly, with no need for the full Docker Engine or its daemon on the node.
*What the interviewer is probing:* current, accurate knowledge of the container ecosystem rather than outdated "Kubernetes runs Docker" assumptions — a frequent gap even among experienced candidates.

**Architect:** "A security team asks why a compromised container could potentially affect other containers on the same AKS node. Explain the underlying risk in architectural terms."
*Model answer:* All containers on a node share one kernel. Namespaces and cgroups provide strong logical isolation but are not as strong a security boundary as a hypervisor's hardware-level isolation between VMs, because a kernel vulnerability or misconfiguration (e.g., an overly permissive `securityContext`, a container running as root without dropped capabilities, or a container escape exploit) can potentially allow a process to affect the shared kernel and thus other containers. This is why node-level hardening, non-root containers, read-only root filesystems, dropped Linux capabilities, and considering gVisor/Kata Containers or dedicated node pools for untrusted workloads are relevant mitigations (expanded further in Section 37's AKS security coverage).
*What the interviewer is probing:* whether the candidate can reason about the security implications of the shared-kernel model at a systems level, not just recite that "containers are isolated."

### 34.4.6 Key Takeaways

🔑 Docker Engine is a client-server system; `containerd` and `runc` do the real work of running containers, and both are used directly by Kubernetes/AKS without `dockerd` in the loop in production.

---

## 34.5 Container Images

### 34.5.1 Definition

An **image** is an immutable, read-only template composed of stacked filesystem layers plus metadata (default command, exposed ports, environment variables, working directory), from which one or more containers can be instantiated.

### 34.5.2 Why It Exists

Without a standard packaging format, "portable, reproducible deployment artifact" would be an ad hoc convention per team. The image format (standardized by the OCI Image Specification) guarantees that any compliant tool — `docker build`, `az acr build`, GitHub Actions, or a Kubernetes node's `containerd` — can produce or consume the exact same artifact, byte for byte, identified by a content-addressable digest (a SHA-256 hash of the image manifest).

### 34.5.3 Internal Working: Layers

Every image is a stack of **layers**, each one an immutable filesystem diff:

```
Layer 4 (top, read-only): COPY . /app          — application code
Layer 3 (read-only):      RUN pip install ...  — dependencies
Layer 2 (read-only):      RUN apt-get update && apt-get install ...
Layer 1 (base, read-only): FROM python:3.12-slim
```

- Each instruction in a Dockerfile that modifies the filesystem (`RUN`, `COPY`, `ADD`) produces exactly one new layer.
- Layers are **content-addressed**: identical layer content, even across unrelated images, is stored once and referenced by multiple images, saving disk space and transfer bandwidth on push/pull.
- Layers are cached during builds: if a layer's inputs have not changed, Docker reuses the cached layer instead of rebuilding it, which is the basis of build-cache optimization (34.6.5).
- When a container starts, an additional thin **writable layer** is added on top using a union filesystem (commonly OverlayFS on Linux hosts); all runtime writes go there, and the underlying image layers remain untouched and shareable across containers.

### 34.5.4 Image Naming and Tags

An image reference has the form:

```
[registry-host[:port]/]repository[:tag]
```

Examples:
- `nginx:1.27` — official image, implicit Docker Hub registry, repository `nginx`, tag `1.27`.
- `myregistry.azurecr.io/webapp:2026.07.24` — an Azure Container Registry (`myregistry.azurecr.io`, covered fully in Section 35), repository `webapp`, tag matching a date-based release convention.
- `myregistry.azurecr.io/webapp@sha256:3fbb...` — pinning to an exact immutable digest rather than a mutable tag, the strongly recommended approach for production deployments (34.5.6).

⚠️ **Warning:** Tags are mutable pointers, not immutable identifiers. `latest` in particular is a convention, not a guarantee — nothing prevents someone from pushing a completely different image under the tag `latest` or even `1.27`. Only the **digest** (`sha256:...`) is truly immutable.

### 34.5.5 Commands — Image Management (Using the Command Documentation Template)

#### `docker pull`
- **Purpose:** downloads an image (or a specific tag/digest of it) from a registry to the local image cache, without running it.
- **Syntax:** `docker pull [OPTIONS] NAME[:TAG|@DIGEST]`
- **Key options:**
  - `--platform <os/arch>` — pulls a specific platform variant from a multi-platform image (e.g., `linux/amd64` vs `linux/arm64`), important when building on Apple Silicon laptops for deployment to `linux/amd64` Azure infrastructure.
  - `-a, --all-tags` — pulls all tags in a repository (rarely used in automation; increases bandwidth and storage cost).
- **Practical example:**
  ```bash
  docker pull mcr.microsoft.com/dotnet/aspnet:8.0
  ```
  Expected output includes per-layer download progress lines ending in `Status: Downloaded newer image for mcr.microsoft.com/dotnet/aspnet:8.0`.
- **Production usage:** CI/CD agents pull a pinned base image digest at build time to guarantee reproducible builds rather than trusting a mutable tag.
- **Common errors:** `unauthorized: authentication required` (missing registry login — see `docker login` and Section 35's ACR authentication coverage); `manifest unknown` (tag or platform variant does not exist in the registry).
- **Security impact:** pulling from unverified public registries risks supply-chain compromise (typosquatted image names, compromised maintainer accounts). Enterprise practice is to pull only from an approved private registry such as ACR, optionally with content trust/image signing (touched on in 34.9, expanded in Section 35).
- **Performance impact:** layer caching means repeated pulls of the same base image across many builds/hosts only transfer new layers, not the whole image.

#### `docker build`
- **Purpose:** builds a new image from a Dockerfile and a build context (the set of files sent to the daemon for use in `COPY`/`ADD` instructions).
- **Syntax:** `docker build [OPTIONS] PATH | URL | -`
- **Key options:**
  - `-t, --tag NAME:TAG` — assigns one or more tags to the resulting image; can be repeated to apply multiple tags in one build.
  - `-f, --file PATH` — specifies a Dockerfile path other than `PATH/Dockerfile`, useful when maintaining multiple Dockerfiles (e.g., `Dockerfile.dev`, `Dockerfile.prod`) in one repository.
  - `--build-arg KEY=VALUE` — passes a build-time variable into the Dockerfile's `ARG` instructions; not available at container runtime (use `ENV` or Azure Key Vault-sourced configuration for that, covered later in Part 11).
  - `--no-cache` — forces a full rebuild ignoring the layer cache, used to pick up upstream security patches baked into a base image even when the Dockerfile text itself has not changed.
  - `--platform` — targets a specific architecture for the build output.
- **Practical example:**
  ```bash
  docker build -t myregistry.azurecr.io/webapp:1.0 -f Dockerfile .
  ```
  Expected output shows each instruction executing as `Step N/M`, ending with `Successfully tagged myregistry.azurecr.io/webapp:1.0`.
- **Production/enterprise usage:** in CI pipelines, the tag is almost never a static string; it typically embeds the Git commit SHA or a semantic version plus build number, enabling exact traceability from a running container back to the source commit that produced it — an operational requirement in regulated enterprises.
- **Common errors:** `COPY failed: file not found` (build context does not include the referenced file — often because it is excluded by `.dockerignore` or because the Dockerfile references a path outside the build context, which Docker disallows for security reasons); `no space left on device` (accumulated dangling images/layers filling host disk — see `docker system prune` under troubleshooting, 34.13).
- **Security impact:** the build context is sent in full to the daemon; without a `.dockerignore` file, secrets such as `.env` files or private keys sitting in the project directory can be inadvertently baked into an image layer and become extractable by anyone who later pulls that image — a very common real-world incident.
- **Performance impact:** instruction ordering directly affects cache efficiency (34.6.5); poor ordering causes unnecessary full rebuilds and slow CI pipelines.

#### `docker push`
- **Purpose:** uploads a locally built image to a registry, making it available to other hosts (Azure services included).
- **Syntax:** `docker push NAME[:TAG]`
- **Practical example:**
  ```bash
  docker push myregistry.azurecr.io/webapp:1.0
  ```
- **Production usage:** typically the final step of a CI pipeline stage, immediately followed by a deployment step that instructs the target Azure service (AKS, App Service, ACI, Container Apps) to pull the new tag or digest.
- **Common errors:** `denied: requested access to the resource is denied` — insufficient RBAC/registry permissions; in Azure this maps directly to the AcrPush role covered in Section 35.
- **Security impact:** push access should be restricted to CI identities (ideally via a Managed Identity or Service Principal, Section 9) rather than shared human credentials.

#### `docker images` / `docker image ls`
- **Purpose:** lists locally cached images with repository, tag, image ID, creation date, and size.
- **Syntax:** `docker images [OPTIONS] [REPOSITORY[:TAG]]`
- **Practical example:** `docker images` → tabular output of all local images.
- **Troubleshooting tip:** use this to identify unexpectedly large images (a sign of a missing multi-stage build or an unnecessarily large base image) or stale/dangling images (`<none>` tag) consuming disk space.

#### `docker rmi`
- **Purpose:** removes a local image.
- **Syntax:** `docker rmi [OPTIONS] IMAGE [IMAGE...]`
- **Key option:** `-f, --force` — removes an image even if containers reference it (dangerous; can orphan running containers' layer references in edge cases).
- **Common error:** `image is being used by stopped container` — remove or prune dependent containers first.

### 34.5.6 Production and Enterprise Usage

- **Digest pinning:** production deployment manifests (Kubernetes YAML, ARM/Bicep templates) should reference images by immutable digest (`@sha256:...`) rather than a mutable tag, guaranteeing that a rollback or redeploy always retrieves byte-identical content — this is a widely accepted best practice, not merely an opinion.
- **Image provenance and signing:** enterprises increasingly require cryptographic signing of images (e.g., via Notary/Cosign integrated with ACR) so that deployment targets can verify an image was built by an authorized pipeline and has not been tampered with in transit or at rest.
- **Immutable tags in ACR:** Azure Container Registry supports marking specific tags as immutable, preventing accidental or malicious overwrite of a released version — a governance control referenced again in Section 35.

### 34.5.7 Security Considerations

- Always use minimal base images (`-slim`, `-alpine`, or distroless variants) to shrink the attack surface — fewer installed packages means fewer potential CVEs.
- Regularly rebuild images even without application code changes, to pick up base-image security patches (`--no-cache` builds on a schedule, or automated dependency/base-image update tooling).
- Scan images for known vulnerabilities before deployment (Microsoft Defender for Cloud's container image scanning, covered in Section 55, integrates directly with ACR for this purpose).

### 34.5.8 Performance Considerations

- Smaller images pull faster, which directly reduces cold-start time for ACI, Azure Container Apps' scale-from-zero, and AKS pod scheduling during node scale-out events.
- Layer ordering that maximizes cache hits (34.6.5) reduces CI build time, which is an operational cost as much as a technical one at enterprise CI scale.

### 34.5.9 Common Misconceptions

- "An image is a running thing." *Correction:* an image is a static, read-only template; a **container** is the running instance.
- "`latest` means the newest/best version." *Correction:* `latest` is just a tag name with no special meaning enforced by Docker itself; it is a human convention that is frequently the *default* tag applied when none is specified, which is precisely why relying on it in production is discouraged.

### 34.5.10 Interview Questions — Images

**Beginner:** "What is the difference between an image and a container?"
*Model answer:* An image is an immutable, read-only template — layers of filesystem content plus metadata. A container is a running (or stopped) instance created from an image, with its own writable layer added on top. One image can be used to start many independent containers.

**Intermediate:** "Why is pinning images by digest instead of tag considered a best practice in production?"
*Model answer:* Tags are mutable pointers that can be reassigned to different image content at any time, either intentionally (a new release reusing `latest`) or accidentally. A digest is a cryptographic hash of the image manifest and is immutable by construction — the same digest always resolves to exactly the same bytes. Pinning by digest guarantees reproducible deployments and reliable rollbacks, which tags alone cannot guarantee.

**FAANG-style / Scenario:** "Your team's CI pipeline builds and pushes an image tagged `myapp:v2.3` to ACR. Two weeks later, a production incident occurs, and you need to redeploy exactly what was running last Tuesday. How do you guarantee you get the exact same image, and what would you change about the deployment pipeline going forward to make this reliable by default?"
*Model answer:* If the deployment only ever referenced the mutable tag `myapp:v2.3`, and that tag was later overwritten by a subsequent build reusing the same version string, there is no guarantee the current `v2.3` tag still points at what ran last Tuesday. The reliable fix going forward is for the deployment pipeline to record and deploy by the immutable digest returned at push time (captured as a pipeline artifact/output), and, where the registry supports it, to mark released tags immutable (ACR's tag immutability feature, Section 35) to prevent overwrite in the first place. For the immediate incident, if the exact digest from that Tuesday build was not recorded anywhere (build logs, deployment history, GitOps commit), it may be unrecoverable — which is itself the lesson to escalate: deployment records must capture digests, not just tags.
*What the interviewer is probing:* real production incident-response thinking, not just textbook recall — recognizing that the fix is both immediate (find the record) and systemic (change the pipeline).

---

## 34.6 The Dockerfile

### 34.6.1 Definition

A **Dockerfile** is a plain-text, declarative script of instructions that `docker build` executes in order to produce an image, one layer per filesystem-modifying instruction.

### 34.6.2 Core Instructions (Command Documentation Template Applied)

#### `FROM`
- **Purpose:** sets the base image the new image builds on top of; must be the first instruction (aside from optional `ARG` before it for parameterizing the base image itself).
- **Syntax:** `FROM <image>[:<tag>|@<digest>] [AS <stage-name>]`
- **Example:** `FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime`
- **Production usage:** enterprises frequently mandate approved internal base images (mirrored into ACR from Microsoft's MCR or vetted vendors) rather than pulling directly from arbitrary public registries, for supply-chain control (expanded in Section 35 and Section 58).
- **Common mistake:** using an unpinned `latest` base tag, causing unreproducible builds where the same Dockerfile produces different results on different days as the upstream `latest` moves.

#### `RUN`
- **Purpose:** executes a command during the build, producing a new layer from its filesystem changes (e.g., installing packages).
- **Syntax:** `RUN <command>` (shell form) or `RUN ["executable", "param1", "param2"]` (exec form)
- **Example:** `RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*`
- **Non-obvious detail:** chaining commands with `&&` in a single `RUN` (rather than separate `RUN` lines) keeps them in one layer, and cleaning up package manager caches (`rm -rf /var/lib/apt/lists/*`) in that *same* `RUN` instruction is essential — if the cleanup were a separate `RUN`, the earlier layer would still contain the cache data, since layers are additive diffs and an earlier layer's content cannot be removed by a later layer's deletion, only hidden from the final merged view while still occupying storage.
- **Security impact:** avoid `RUN curl ... | bash` patterns that execute unverified remote scripts during the build without integrity checking.

#### `COPY` vs `ADD`
- **Purpose:** copies files from the build context (or, for `ADD` only, a remote URL or local tar archive) into the image filesystem.
- **Syntax:** `COPY [--chown=user:group] <src>... <dest>` / `ADD [--chown=user:group] <src>... <dest>`
- **Guidance (widely accepted best practice, not merely opinion):** prefer `COPY` for local files; reserve `ADD` only for its two unique capabilities (auto-extracting local tar archives, or fetching a remote URL), because `ADD`'s implicit behaviors (especially remote fetch, and auto-extraction of archives) are less predictable and have been a source of real-world build surprises and security concerns (fetching from a URL without integrity verification).
- **Example:** `COPY --chown=appuser:appgroup ./bin/app /app/app`

#### `WORKDIR`
- **Purpose:** sets the working directory for all subsequent instructions in the Dockerfile and the default directory when the container starts.
- **Syntax:** `WORKDIR /path`
- **Best practice:** always use `WORKDIR` instead of `RUN cd ...`, since `cd` in a `RUN` instruction only affects that single instruction's subshell, not subsequent instructions.

#### `ENV`
- **Purpose:** sets an environment variable available both during subsequent build steps and at container runtime (unlike `ARG`, which is build-time only).
- **Syntax:** `ENV KEY=value`
- **Security note:** never place secrets (connection strings, API keys) in `ENV` instructions — they become permanently visible in `docker history` and the image manifest. Use Azure Key Vault references, Kubernetes Secrets, or App Service application settings injected at runtime instead (expanded in Section 56).

#### `EXPOSE`
- **Purpose:** documents which network port(s) the container listens on; purely informational metadata — it does **not** actually publish the port. Port publishing happens at `docker run -p` or in the target Azure service's networking configuration.
- **Syntax:** `EXPOSE <port>[/protocol]`
- **Common misconception:** believing `EXPOSE` opens the port to the network. It does not; it is documentation consumed by tooling (and a default hint for `docker run -P`).

#### `USER`
- **Purpose:** sets the user (and optionally group) that subsequent instructions and the final container process run as, instead of the default `root`.
- **Syntax:** `USER <user>[:<group>]`
- **Security impact:** critical hardening control — running as root inside a container means a container-escape vulnerability grants root on the host's kernel context; running as a non-root user significantly narrows that blast radius (expanded in 34.9 and Section 55).

#### `ENTRYPOINT` and `CMD`
- **Purpose:** define the default process the container runs when started. `ENTRYPOINT` sets the fixed, non-overridable (without `--entrypoint`) executable; `CMD` supplies default arguments to it, or the full command if no `ENTRYPOINT` is set — and `CMD`'s value is overridden by any command-line arguments passed to `docker run`.
- **Syntax:** exec form strongly preferred over shell form: `ENTRYPOINT ["executable", "arg1"]` / `CMD ["arg1", "arg2"]`
- **Non-obvious detail:** exec form runs the process as PID 1 directly, correctly receiving signals like `SIGTERM` for graceful shutdown; shell form (`CMD command arg1`) runs the command via `/bin/sh -c`, meaning the actual process is a child of the shell, and signals sent to PID 1 (the shell) are not automatically forwarded to the child — a frequent, subtle cause of containers that ignore graceful shutdown signals and get hard-killed after a timeout in Kubernetes/AKS.

#### `HEALTHCHECK`
- **Purpose:** defines a command Docker runs periodically to determine whether the container is healthy, surfaced in `docker ps` status and usable by orchestrators.
- **Syntax:** `HEALTHCHECK [--interval=30s --timeout=3s --retries=3] CMD <command>`
- **Production note:** in AKS, Kubernetes has its own liveness/readiness probe mechanism (Section 37) which is generally preferred over the Dockerfile `HEALTHCHECK` for orchestrated workloads, but `HEALTHCHECK` remains valuable for standalone Docker usage (e.g., ACI, App Service containers) where no external orchestrator is present.

### 34.6.3 Complete Hands-On Example

```dockerfile
# Stage 1: build
FROM mcr.microsoft.com/dotnet/sdk:8.0 AS build
WORKDIR /src
COPY *.csproj .
RUN dotnet restore
COPY . .
RUN dotnet publish -c Release -o /app/publish

# Stage 2: runtime
FROM mcr.microsoft.com/dotnet/aspnet:8.0 AS runtime
WORKDIR /app
RUN adduser --disabled-password --gecos "" appuser
COPY --from=build --chown=appuser:appuser /app/publish .
USER appuser
EXPOSE 8080
ENTRYPOINT ["dotnet", "MyApp.dll"]
```

Line-by-line, non-obvious points explained:
- Two `FROM` instructions define a **multi-stage build**: the SDK image (large, contains compilers and build tools) is used only to produce compiled output, and the final runtime image starts fresh from a much smaller ASP.NET runtime-only base, discarding the SDK entirely from the final artifact.
- `COPY *.csproj .` followed by `RUN dotnet restore` **before** copying the rest of the source (`COPY . .`) is a deliberate cache-optimization ordering (34.6.5): dependency restoration only re-runs when the project file changes, not on every source code edit.
- `COPY --from=build` pulls specific output from the named earlier stage rather than the local build context.
- A non-root `appuser` is created and switched to via `USER`, following the security guidance in 34.6.2 and 34.9.

### 34.6.4 `.dockerignore`

- **Purpose:** excludes files/directories from the build context sent to the daemon, analogous to `.gitignore`.
- **Why it matters:** prevents secrets, local environment files, `.git` history, `node_modules`, or build artifacts from being unnecessarily transferred to the daemon or accidentally copied into the image via broad `COPY . .` instructions.
- **Example:**
  ```
  .git
  .env
  node_modules
  **/*.log
  bin/
  obj/
  ```

### 34.6.5 Layer Caching and Build Optimization

- Docker evaluates each Dockerfile instruction's cache validity based on the instruction text and (for `COPY`/`ADD`) the content hash of the referenced files. If nothing has changed for an instruction *and every instruction before it in the file*, the cached layer is reused and the instruction is skipped entirely.
- Because cache validity is order-dependent from the top down, the **best practice is to order instructions from least-frequently-changing to most-frequently-changing**: base image and system dependency installation first, dependency manifests and restore/install commands next, and application source code copy last — exactly the pattern shown in 34.6.3.
- ⚠️ **Warning:** a single `COPY . .` early in the Dockerfile, followed by dependency installation, defeats caching entirely — any source code change (even a comment edit) invalidates the cache for every subsequent instruction, including the expensive dependency install step, causing unnecessarily slow CI builds at scale.

### 34.6.6 Best Practices

- Use specific, pinned base image tags or digests, never bare `latest`.
- Minimize the number of layers where reasonable by chaining related `RUN` commands, while keeping the Dockerfile readable — this is a trade-off, not an absolute rule; excessive chaining that harms cache granularity is itself an anti-pattern.
- Use multi-stage builds to keep runtime images minimal.
- Run as a non-root user.
- Use exec-form `ENTRYPOINT`/`CMD` for correct signal handling.
- Keep `.dockerignore` current.

### 34.6.7 Anti-Patterns and Common Mistakes

- Installing unnecessary packages ("just in case") that bloat the image and expand the vulnerability surface.
- Storing secrets in `ENV`, `ARG`, or baked-in config files.
- Using `ADD` for simple local file copies where `COPY` is clearer and more predictable.
- Ignoring `.dockerignore`, leading to bloated build contexts and accidental secret inclusion.
- Running the main application process as root without justification.

### 34.6.8 Interview Questions — Dockerfile

**Beginner:** "What is the difference between `CMD` and `ENTRYPOINT`?"
*Model answer:* `ENTRYPOINT` defines the fixed command the container always runs; `CMD` supplies default arguments to it (or is the whole command if no `ENTRYPOINT` exists), and `CMD`'s value can be overridden by arguments passed to `docker run`, while `ENTRYPOINT` requires the explicit `--entrypoint` flag to override.

**Senior:** "Explain why exec-form `CMD`/`ENTRYPOINT` is preferred over shell form in production."
*Model answer:* Exec form (`["executable", "arg"]`) runs the process directly as PID 1, so signals like SIGTERM sent by the container runtime during a graceful shutdown or by Kubernetes during a pod termination reach the application directly and immediately. Shell form (`command arg`) wraps the process in `/bin/sh -c`, making the shell PID 1 and the actual application a child process; the shell does not always forward signals to its child by default, which can cause the application to ignore shutdown signals, forcing the runtime to wait out the full termination grace period and then SIGKILL — this shows up in production as slow, ungraceful pod terminations during deployments or scale-down events.
*What the interviewer is probing:* depth beyond syntax — understanding of process signal propagation and its operational consequences, which is a frequent real-world debugging scenario.

### 34.6.9 Key Takeaways

🔑 A Dockerfile is not just a build recipe — instruction choice and ordering directly affect image size, build speed (via cache), security posture, and runtime shutdown behavior.

---

## 34.7 Containers: Running, Managing, and Inspecting

### 34.7.1 Definition

A running (or stopped, but not yet removed) instance of an image, with its own writable layer, its own isolated namespaces, and its own cgroup resource accounting.

### 34.7.2 Commands — Container Lifecycle

#### `docker run`
- **Purpose:** creates and starts a new container from an image in one step.
- **Syntax:** `docker run [OPTIONS] IMAGE [COMMAND] [ARG...]`
- **Key options:**
  - `-d, --detach` — runs the container in the background, returning the container ID immediately, essential for long-running services rather than blocking the terminal.
  - `-p, --publish HOST:CONTAINER` — maps a host port to a container port (e.g., `-p 8080:80`), the mechanism by which an externally reachable service is exposed from an otherwise network-isolated container.
  - `-e, --env KEY=VALUE` — sets an environment variable at runtime, overriding any Dockerfile `ENV` default; the standard way to inject configuration without rebuilding the image, and the mechanism Azure services use under the hood to pass App Settings into App Service/ACI containers.
  - `-v, --volume` — mounts a named volume or bind mount (34.10).
  - `--name` — assigns a human-readable name instead of a random generated one.
  - `--rm` — automatically removes the container's writable layer when it exits, useful for short-lived, throwaway containers (e.g., CI test runs) to avoid accumulating stopped-container clutter.
  - `--restart` — sets a restart policy (`no`, `on-failure[:max-retries]`, `always`, `unless-stopped`); relevant primarily to standalone Docker hosts (e.g., an Azure VM running Docker directly), since orchestrated platforms like AKS handle restart policy through their own scheduler instead.
- **Practical example:**
  ```bash
  docker run -d --name webapp -p 8080:8080 -e ASPNETCORE_ENVIRONMENT=Production myregistry.azurecr.io/webapp:1.0
  ```
- **Common errors:** `port is already allocated` (host port conflict); `Error response from daemon: pull access denied` (not authenticated to the registry — see Section 35's ACR authentication).
- **Exit codes:** the container's own process exit code is surfaced via `docker inspect` / `docker wait`; exit code `0` indicates a clean exit, non-zero indicates the application process itself failed, and `137` specifically indicates the process was killed by SIGKILL (commonly from an out-of-memory cgroup kill or `docker stop` timeout expiry).

#### `docker ps`
- **Purpose:** lists running containers (add `-a` for all containers including stopped ones).
- **Syntax:** `docker ps [OPTIONS]`
- **Troubleshooting tip:** `docker ps -a` immediately after an unexpected exit shows the exit code in the `STATUS` column, the first diagnostic step for "my container keeps stopping."

#### `docker logs`
- **Purpose:** retrieves the stdout/stderr output stream captured from a container's main process.
- **Syntax:** `docker logs [OPTIONS] CONTAINER`
- **Key options:** `-f, --follow` (stream continuously, like `tail -f`); `--since`, `--until` (time-bounded log retrieval); `--tail N` (last N lines).
- **Production usage:** in Azure, this local logging model is superseded by centralized logging once containers run on ACI, App Service, or AKS — Azure Monitor / Log Analytics (Section 50–51) aggregates the same stdout/stderr stream across all instances, which is why applications should always log to stdout/stderr rather than writing to local files inside the container.

#### `docker exec`
- **Purpose:** runs an additional command inside an already-running container, most commonly for interactive debugging.
- **Syntax:** `docker exec [OPTIONS] CONTAINER COMMAND`
- **Practical example:** `docker exec -it webapp /bin/sh` opens an interactive shell inside the running container.
- **Security note:** `docker exec` access is equivalent to significant control over that container's process namespace; in production Azure environments this maps to `kubectl exec` RBAC restrictions covered in Section 37.

#### `docker stop` / `docker kill`
- **Purpose:** `docker stop` sends SIGTERM, waits a grace period (default 10 seconds), then sends SIGKILL if the process has not exited; `docker kill` sends SIGKILL (or a specified signal) immediately.
- **Syntax:** `docker stop [-t SECONDS] CONTAINER` / `docker kill [-s SIGNAL] CONTAINER`
- **Relevance:** the grace period behavior directly parallels Kubernetes' pod `terminationGracePeriodSeconds` (Section 37) — understanding this at the Docker level transfers directly.

#### `docker rm`
- **Purpose:** removes a stopped container and its writable layer.
- **Syntax:** `docker rm [-f] CONTAINER`

#### `docker inspect`
- **Purpose:** returns detailed JSON metadata about a container or image (network settings, mounts, environment, resource limits, health status).
- **Syntax:** `docker inspect [OPTIONS] NAME|ID`
- **Troubleshooting tip:** `docker inspect --format '{{.State.ExitCode}}' <container>` extracts a single field programmatically, useful in scripted diagnostics.

### 34.7.3 Resource Limits at Runtime

- `--memory` and `--memory-swap` set a hard memory ceiling enforced by the cgroup; exceeding it triggers the kernel's OOM killer against that container's process specifically, not the host.
- `--cpus` sets a fractional CPU limit (e.g., `--cpus=0.5` allows up to half a CPU core's worth of time).
- These map directly to Kubernetes pod resource `limits`/`requests` (Section 37) and to ACI's per-container-group CPU/memory allocation (Section 15) — the underlying cgroup mechanism is identical across all of these Azure services.

### 34.7.4 Troubleshooting Common Container Issues

| Symptom | Likely Cause | Diagnostic Step |
|---|---|---|
| Container exits immediately after `docker run` | Main process completes and exits (containers stop when PID 1 exits); often a misconfigured `CMD`/`ENTRYPOINT`, or the app crashing on startup | `docker logs <container>` to see the crash output; `docker ps -a` to see exit code |
| Container exits with code 137 | OOM-killed by cgroup memory limit, or killed by `docker stop` timing out and escalating to SIGKILL | `docker inspect` for `OOMKilled: true`; review `--memory` limit vs actual usage |
| "Cannot connect" to a published port | Port not actually published (`-p` missing or wrong mapping), application listening on `127.0.0.1` inside the container instead of `0.0.0.0` (binding only to loopback makes it unreachable even with correct port publishing) | `docker port <container>`; verify the app's bind address in its own configuration |
| Image builds successfully but runtime fails with "file not found" for an executable | Multi-stage build copied from the wrong stage, or a runtime dependency present in the build stage was never installed in the final runtime stage | Compare `COPY --from=` stage references; verify runtime-stage base image includes required shared libraries |
| Very slow builds in CI despite a small Dockerfile | Poor layer-cache ordering (34.6.5), or CI runner not persisting Docker's build cache between runs | Reorder instructions; configure CI to reuse a build cache (e.g., BuildKit cache export, or ACR Tasks' cache-from behavior, Section 35) |

### 34.7.5 Key Takeaways

🔑 A container's lifecycle is tied directly to its main process (PID 1): when that process exits, the container stops, regardless of any other background activity. This single fact explains a large share of "why did my container stop" troubleshooting scenarios.

---

## 34.8 Docker Compose (Local Multi-Container Development)

### 34.8.1 Definition

**Docker Compose** is a tool for defining and running multi-container applications using a single declarative YAML file (`compose.yaml`, historically `docker-compose.yml`), primarily used for local development and testing environments that mirror a production topology of multiple cooperating services.

### 34.8.2 Why It Exists

Modern applications rarely consist of a single container — a typical local development setup might need an API service, a database, and a cache running together with correct networking between them. Running and wiring these together manually via repeated `docker run` commands is tedious and error-prone; Compose expresses the whole topology declaratively and brings it up or down with a single command.

### 34.8.3 Example

```yaml
services:
  webapp:
    build: .
    ports:
      - "8080:8080"
    environment:
      - ConnectionStrings__Db=Server=db;Database=app;User=sa;Password=${DB_PASSWORD}
    depends_on:
      - db
  db:
    image: mcr.microsoft.com/mssql/server:2022-latest
    environment:
      - ACCEPT_EULA=Y
      - MSSQL_SA_PASSWORD=${DB_PASSWORD}
    volumes:
      - db-data:/var/opt/mssql

volumes:
  db-data:
```

- Compose automatically creates a private network so services can reach each other by service name (`db` resolves to the database container's address from within `webapp` — a simple built-in DNS-like mechanism).
- `depends_on` controls **startup order** only; it does not wait for the dependency to be actually ready (e.g., the database accepting connections) — a frequent source of local "connection refused on first run" issues, addressed by combining `depends_on` with the `condition: service_healthy` form tied to a `HEALTHCHECK`, or with in-app retry logic.

### 34.8.4 Relationship to Azure

⚠️ **Warning:** Docker Compose is a local/dev-oriented tool. It is **not** how Azure runs multi-container production workloads at scale — that role belongs to Azure Kubernetes Service (Sections 36–38) or Azure Container Apps, both of which have their own (more capable) mechanisms for service discovery, scaling, and networking. However, Azure Container Instances does support deploying a **container group** defined via a YAML file with a structure conceptually similar to Compose (multiple containers sharing a network namespace), and some Azure Container Apps tooling accepts Compose files as a translation input for simple cases — but production Kubernetes manifests are not a Compose file and require the distinct concepts taught in Section 37.

### 34.8.5 Key Takeaways

🔑 Compose is a local development convenience for orchestrating a handful of related containers; it is a stepping stone toward understanding Kubernetes concepts (services, dependencies, environment injection), not a production Azure deployment mechanism.

---

## 34.9 Container Security Fundamentals

(Deep, Azure-service-specific container security — including Microsoft Defender for Cloud's container scanning, AKS pod security admission, and network policies — is covered fully in Sections 37 and 52–56. This subsection establishes the Docker-level fundamentals those later sections build on.)

- **Run as non-root:** as established in 34.6.2, a container running as root that suffers a container-escape vulnerability grants the attacker root in the shared-kernel context; always set `USER` in the Dockerfile, or the equivalent orchestrator-level security context.
- **Minimize base image surface:** fewer installed packages means fewer CVEs to track and patch; `-slim`, `-alpine`, or distroless base images are widely recommended for production.
- **Drop unnecessary Linux capabilities:** by default, Docker grants containers a reduced-but-still-broad set of Linux capabilities; production hardening typically drops all capabilities and adds back only the specific ones required (`--cap-drop=ALL --cap-add=NET_BIND_SERVICE`, for example).
- **Read-only root filesystem where possible:** `--read-only` prevents runtime writes to the container's filesystem outside explicitly mounted writable volumes, limiting the damage an attacker who gains code execution can do (e.g., cannot drop a persistent backdoor binary into the image layer).
- **Scan images before deployment:** vulnerability scanning (integrated with ACR and Microsoft Defender for Cloud, Section 55) should be a required CI/CD gate, not an optional afterthought.
- **Avoid privileged mode:** `--privileged` disables almost all container isolation and should essentially never be used for application workloads; legitimate uses are rare and specialized (e.g., certain low-level infrastructure tooling).
- **Registry trust:** pull only from registries under organizational control or explicitly vetted (ACR with content trust, or verified publishers on Microsoft Container Registry/MCR), never arbitrary public registries for production workloads.

🎯 **Interview Tip:** A strong senior/architect-level answer on container security always connects the *mechanism* (shared kernel, namespaces, cgroups, Linux capabilities) to the *mitigation* (non-root user, capability dropping, read-only filesystem, image scanning) rather than listing hardening steps as an unconnected checklist.

---

## 34.10 Persistent Data: Volumes and Bind Mounts

### 34.10.1 Definition

By default, all data written inside a container's writable layer is lost when the container is removed. **Volumes** and **bind mounts** are Docker's two mechanisms for persisting data beyond a container's lifecycle.

### 34.10.2 Volumes vs. Bind Mounts

| Aspect | Named Volume | Bind Mount |
|---|---|---|
| Managed by | Docker (`docker volume create`) | The host filesystem directly (path exists independent of Docker) |
| Typical use | Production-style persistent data (databases, uploaded files) | Local development (mounting live source code into a container for hot-reload) |
| Portability | Portable across hosts with the same Docker setup; abstracted from host filesystem specifics | Tied to a specific host path; not portable |
| Azure relevance | Conceptually parallels Kubernetes PersistentVolumes backed by Azure Disks/Files (Section 37) | Rarely used directly in Azure production; primarily a local-development pattern |

### 34.10.3 Example

```bash
docker volume create app-data
docker run -d -v app-data:/var/lib/app/data myregistry.azurecr.io/webapp:1.0
```

### 34.10.4 Relevance to Azure

This section intentionally stays at Docker-level fundamentals. When containers move to AKS, "volumes" become **PersistentVolumes** and **PersistentVolumeClaims**, typically backed by Azure Disks (single-node read-write) or Azure Files (multi-node read-write-many) — both already covered in depth in Sections 18–19, and revisited from the Kubernetes storage-class perspective in Section 37.

---

## 34.11 Running Docker Workloads on Azure: Service Landscape Overview

This subsection is an orientation map for the rest of Part 7 and Part 8 — a comparison of *where* a container image can actually run in Azure, without going deep into any single service (each has its own dedicated section).

### 34.11.1 Comparison of Azure Container Hosting Options

| Azure Service | Model | Orchestration | Typical Fit | Roadmap Section |
|---|---|---|---|---|
| **Azure VM with Docker installed** | You manage the VM, the Docker Engine, and everything above it | None (manual, or self-managed via Compose/scripts) | Legacy lift-and-shift, full control scenarios, or learning/dev sandboxes | Section 11 (VM fundamentals) + this section |
| **Azure Container Instances (ACI)** | Serverless single container or a small container group; no VM management | None (Azure schedules on hidden infrastructure) | Simple, short-lived, or bursty single/few-container workloads; CI/CD job runners; batch tasks | Section 15 |
| **Azure App Service (custom container / Web App for Containers)** | PaaS web app backed by a container image instead of the built-in language runtime | Platform-managed scaling of a single app | Web applications and APIs wanting PaaS convenience (deployment slots, custom domains, easy scaling) with the packaging flexibility of a container | Section 13 |
| **Azure Container Apps** | Managed serverless container platform built on Kubernetes/KEDA/Dapr under the hood, without exposing Kubernetes directly | Platform-managed (built on Kubernetes primitives internally, abstracted away) | Microservices needing scale-to-zero, event-driven scaling, and simpler operations than raw AKS | Not yet in roadmap as its own section — introduced in Section 40/40 context; candidate for a future roadmap addition if requested |
| **Azure Kubernetes Service (AKS)** | Full managed Kubernetes control plane; you manage node pools and workload manifests | Full Kubernetes orchestration (scheduling, self-healing, service discovery, rolling updates) | Complex microservice architectures needing fine-grained control, multi-team platforms, workloads requiring specific Kubernetes ecosystem tooling | Sections 36–38 |
| **Azure Functions (custom container)** | Serverless function execution using a container image instead of the built-in deployment package | Platform-managed | Event-driven functions that need custom runtime/dependencies beyond what built-in Functions stacks support | Section 14 covers Functions generally; custom-container specifics are part of Section 40's deeper dive |

💡 **Tip:** A recurring interview and architecture-decision pattern is choosing between these options along two axes: **how much orchestration control is needed** (none → full Kubernetes) and **how much operational overhead the team is willing to own** (fully managed PaaS/serverless → full self-managed Kubernetes node pools). ACI and Container Apps sit at the low-overhead end; AKS sits at the high-control, high-capability, higher-overhead end; App Service containers and VM-hosted Docker sit in between along different dimensions.

### 34.11.2 Docker on an Azure VM (Hands-On Orientation)

Since Docker itself does not require any Azure-specific installation steps beyond standard Linux package installation, running Docker on an Azure VM uses the exact same Docker Engine install and CLI workflow as any Linux server, layered on top of the VM concepts from Section 11:

```bash
# On an Azure Linux VM (Ubuntu example)
sudo apt-get update
sudo apt-get install -y ca-certificates curl
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo $VERSION_CODENAME) stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin
```

⚠️ **Warning:** Verify current package names, repository URLs, and installation steps against Docker's official documentation at the time of use — installation instructions for Linux packages evolve, and this text should be treated as illustrative of the general pattern (add Docker's official APT repository and install the `docker-ce` package family) rather than copied verbatim into a production runbook without verification.

**Production/enterprise relevance:** self-managing Docker directly on an Azure VM is now relatively uncommon for new production workloads compared to the managed container services above, because it pushes the entire operational burden (OS patching, Docker Engine updates, security hardening, orchestration/restart logic, scaling) onto the team — but it remains relevant for specific scenarios: existing legacy pipelines not yet migrated, highly customized host-level requirements, or cost-sensitive single-VM workloads where PaaS/orchestration overhead is unjustified.

### 34.11.3 Where the Image Lives: The Registry Question

Every one of the Azure services above needs to *pull* the image from somewhere. Options include:
- **Docker Hub** (public or private repositories) — acceptable for public open-source base images, generally discouraged as the source of truth for proprietary production images due to rate limiting, availability dependency on a third party outside Azure's network boundary, and weaker integration with Azure RBAC/Managed Identity.
- **Azure Container Registry (ACR)** — the enterprise-standard choice for Azure workloads: private by default, integrates with Microsoft Entra ID/Managed Identities for pull authentication (no embedded credentials), supports geo-replication, vulnerability scanning integration, and native build capabilities (ACR Tasks). Covered in full depth in **Section 35**, which is the direct next section in this roadmap.

---

## 34.12 Enterprise and Production Considerations (Docker-Level, Pre-Orchestration)

- **Immutable infrastructure principle:** in a mature container-based Azure architecture, running containers are never modified in place (no `docker exec`-ing a fix into a production container); instead, a new image is built, tested, pushed, and a new container/pod replaces the old one. This is a widely accepted best practice supporting reproducibility and auditability, distinct from older "patch the running server" operational habits.
- **Twelve-Factor-aligned configuration:** configuration (connection strings, feature flags, environment-specific settings) should be injected via environment variables or mounted secrets at runtime, never baked into the image — this is what makes the *same* image promotable unmodified from a test environment to production.
- **Build once, deploy many:** the image built and tested in CI is the exact same image (by digest) promoted through each environment, never rebuilt per environment — rebuilding per environment reintroduces the "it works in the environment it was built for" risk that containers exist to eliminate.
- **Observability from day one:** applications should log to stdout/stderr (34.7.2) and expose health endpoints so that whichever Azure hosting option is chosen (34.11.1) can integrate with Azure Monitor and platform-level health probing without custom instrumentation per environment.

---

## 34.13 Troubleshooting Reference (Consolidated)

| Problem | First Diagnostic Command | Typical Root Cause |
|---|---|---|
| Build fails at a `COPY` step | Review build context and `.dockerignore` | File path wrong, or excluded by `.dockerignore` |
| Image is much larger than expected | `docker history <image>` (shows per-layer size) | Missing multi-stage build; build tools left in final image; unnecessary package installs not cleaned in the same `RUN` |
| Container starts then exits instantly | `docker logs <container>`, `docker ps -a` for exit code | Main process crashes on startup, or `CMD`/`ENTRYPOINT` misconfigured to run a command that completes immediately |
| Cannot reach the app on the published port | `docker port <container>`; check app bind address | Missing `-p`; app bound to `127.0.0.1` instead of `0.0.0.0` inside the container |
| Host disk filling up over time | `docker system df` | Accumulated dangling images, stopped containers, unused volumes/build cache never pruned (`docker system prune`, used carefully and never blindly in production without understanding what it removes) |
| Build is slow despite a small Dockerfile | Review instruction order against 34.6.5 | Poor cache-friendly ordering; CI not persisting build cache between runs |

---

## 34.14 Best Practices Checklist

- [ ] Base images pinned to a specific tag or digest, never bare `latest`.
- [ ] Multi-stage builds used to exclude build-time-only tooling from the final image.
- [ ] `.dockerignore` present and current.
- [ ] Non-root `USER` set.
- [ ] Exec-form `ENTRYPOINT`/`CMD` used for correct signal handling.
- [ ] No secrets in `ENV`, `ARG`, or copied config files.
- [ ] Application logs to stdout/stderr, not local files.
- [ ] Images scanned for vulnerabilities before deployment.
- [ ] Production deployments reference images by digest, not mutable tag.
- [ ] Images pulled from a controlled private registry (ACR), not arbitrary public sources.

---

## 34.15 Related Concepts and What Comes Next

- **Section 35 — Azure Container Registry:** the private, Azure-integrated registry that stores and distributes the images built using everything taught in this section, including authentication via Managed Identities (Section 9), geo-replication, ACR Tasks (cloud-side image builds), and vulnerability scanning integration.
- **Sections 36–38 — Azure Kubernetes Service:** the orchestration layer that consumes these OCI images at scale, introducing pods, deployments, services, ingress, autoscaling, and cluster-level security — everything in 34.4 (architecture), 34.9 (security), and 34.10 (storage) directly underpins those sections' Kubernetes-specific equivalents.
- **Section 15 — Azure Container Instances (revisit):** now that image/container fundamentals are established, Section 15's ACI coverage can be fully understood as "the simplest possible way to run the containers built in this section, without any orchestrator."
- **Section 13 — Azure App Service (revisit):** custom container deployment to App Service is a direct application of everything in 34.5–34.7.

---

## 34.16 Key Takeaways Summary

🔑 Docker packages an application and its full dependency stack into a portable, immutable image built from cached, stacked layers.

🔑 Docker Engine's architecture (`dockerd` → `containerd` → `runc`) matters because Kubernetes/AKS talks directly to `containerd`, not to `dockerd` — a fact with direct interview and architectural relevance.

🔑 Containers achieve isolation via kernel namespaces and cgroups, not a hypervisor — weaker isolation than a VM, mitigated through explicit hardening (non-root, capability dropping, image scanning, minimal base images).

🔑 Dockerfile instruction choice and ordering affect image size, build speed, security posture, and even runtime shutdown correctness (signal handling via exec-form `ENTRYPOINT`).

🔑 Every Azure container-hosting option (VM+Docker, ACI, App Service containers, Container Apps, AKS, custom-container Functions) consumes the same OCI image artifact — the choice between them is about orchestration control versus operational overhead, not about image compatibility.

🔑 Azure Container Registry (Section 35, next) is the enterprise-standard image storage and distribution point tying this section's fundamentals into the rest of Azure's container ecosystem.

---

*End of Section 34. Next: Section 35 — Azure Container Registry (ACR).*
