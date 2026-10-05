# Docker Zero-to-Production Knowledge Base — Index

A comprehensive, 109-section learning resource organized into 15 parts covering Docker from foundations to production operations. Navigate by part, read sections sequentially, or jump to topics of interest.

---

## Quick Navigation

| Part                             | Topic                                                   | Sections |
| -------------------------------- | ------------------------------------------------------- | -------- |
| **[Part 1](./Contents/Part1)**   | Foundations and History                                 | 1–7      |
| **[Part 2](./Contents/Part2)**   | Architecture and the Container Runtime                  | 8–15     |
| **[Part 3](./Contents/Part3)**   | Images and Dockerfile Authoring                         | 16–25    |
| **[Part 4](./Contents/Part4)**   | Container Lifecycle and CLI                             | 26–33    |
| **[Part 5](./Contents/Part5)**   | Docker Compose and Multi-Container Apps                 | 34–41    |
| **[Part 6](./Contents/Part6)**   | Networking                                              | 42–49    |
| **[Part 7](./Contents/Part7)**   | Storage and Volumes                                     | 50–56    |
| **[Part 8](./Contents/Part8)**   | Security and Hardening                                  | 57–65    |
| **[Part 9](./Contents/Part9)**   | Registries and Image Distribution                       | 66–72    |
| **[Part 10](./Contents/Part10)** | Build Optimization and Multi-Stage Builds               | 73–79    |
| **[Part 11](./Contents/Part11)** | CI/CD Integration                                       | 80–85    |
| **[Part 12](./Contents/Part12)** | Production Operations and Monitoring                    | 86–93    |
| **[Part 13](./Contents/Part13)** | Mastery: Best Practices, Anti-Patterns, and Comparisons | 94–99    |
| **[Part 14](./Contents/Part14)** | Interview Preparation                                   | 100–105  |
| **[Part 15](./Contents/Part15)** | Wrap-Up                                                 | 106–109  |

---

## Folder Structure

```
Docker/
├── README.md (quick-start guide)
├── INDEX.md (this file — comprehensive navigation & section index)
├── 00-Roadmap.md (planning roadmap)
│
└── Contents/ (modular organization by part)
    ├── Part1/(7 sections: Foundations and History)
    ├── Part2/(8 sections: Architecture and the Container Runtime)
    ├── Part3/(10 sections: Images and Dockerfile Authoring)
    ├── Part4/(8 sections: Container Lifecycle and CLI)
    ├── Part5/(8 sections: Docker Compose and Multi-Container Apps)
    ├── Part6/(8 sections: Networking)
    ├── Part7/(7 sections: Storage and Volumes)
    ├── Part8/(9 sections: Security and Hardening)
    ├── Part9/(7 sections: Registries and Image Distribution)
    ├── Part10/(7 sections: Build Optimization and Multi-Stage Builds)
    ├── Part11/(6 sections: CI/CD Integration)
    ├── Part12/(8 sections: Production Operations and Monitoring)
    ├── Part13/(6 sections: Mastery: Best Practices, Anti-Patterns, and Comparisons)
    ├── Part14/(6 sections: Interview Preparation)
    └── Part15/(4 sections: Wrap-Up)
```

---

## Part Summaries

### Part 1 — Foundations and History

What Docker is and how containers differ from VMs, the history from dotCloud to OCI, Docker versus Podman/LXC/containerd, installation (Desktop, Engine, rootless), a Linux namespaces/cgroups recap, editions and licensing, and the DCA landscape.

| § | Section                                                              | File                                                                                                                                                                                         |
| - | -------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | What Docker Is and the Container Model vs. Virtual Machines          | [Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines](./Contents/Part1/Section-01-Part1-What-Docker-Is-and-the-Container-Model-vs-Virtual-Machines.md)               |
| 2 | History: dotCloud to Docker Inc. to OCI Standardization              | [Section-02-Part1-History-dotCloud-to-Docker-Inc-to-OCI-Standardization](./Contents/Part1/Section-02-Part1-History-dotCloud-to-Docker-Inc-to-OCI-Standardization.md)                         |
| 3 | Docker vs. Podman, LXC, rkt, and containerd Standalone               | [Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone](./Contents/Part1/Section-03-Part1-Docker-vs-Podman-LXC-rkt-and-containerd-Standalone.md)                               |
| 4 | Installation and Setup: Docker Desktop, Engine, and Rootless Mode    | [Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode](./Contents/Part1/Section-04-Part1-Installation-and-Setup-Docker-Desktop-Engine-and-Rootless-Mode.md)       |
| 5 | Prerequisites Recap: Linux Namespaces, cgroups, and Basic Networking | [Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking](./Contents/Part1/Section-05-Part1-Prerequisites-Recap-Linux-Namespaces-cgroups-and-Basic-Networking.md) |
| 6 | Docker Editions and Licensing Changes                                | [Section-06-Part1-Docker-Editions-and-Licensing-Changes](./Contents/Part1/Section-06-Part1-Docker-Editions-and-Licensing-Changes.md)                                                         |
| 7 | Docker Certified Associate (DCA) Landscape Overview                  | [Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview](./Contents/Part1/Section-07-Part1-Docker-Certified-Associate-DCA-Landscape-Overview.md)                                 |

### Part 2 — Architecture and the Container Runtime

The dockerd/containerd/runc stack, the client-server model and REST API, OCI image and runtime specs, namespaces and cgroups (v1 vs v2) in depth, overlay2 layered storage, containerd and the CRI, and daemon.json and socket permissions.

| § | Section                                                       | File                                                                                                                                                                                   |
| - | ------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Docker Engine Architecture: dockerd, containerd, and runc     | [Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc](./Contents/Part2/Section-08-Part2-Docker-Engine-Architecture-dockerd-containerd-and-runc.md)                 |
| 2 | Client-Server Model: Docker CLI and the REST API              | [Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API](./Contents/Part2/Section-09-Part2-Client-Server-Model-Docker-CLI-and-the-REST-API.md)                               |
| 3 | OCI Specifications: Image Spec and Runtime Spec               | [Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec](./Contents/Part2/Section-10-Part2-OCI-Specifications-Image-Spec-and-Runtime-Spec.md)                                 |
| 4 | Linux Namespaces Deep Dive                                    | [Section-11-Part2-Linux-Namespaces-Deep-Dive](./Contents/Part2/Section-11-Part2-Linux-Namespaces-Deep-Dive.md)                                                                         |
| 5 | Control Groups (cgroups) Deep Dive: v1 vs v2                  | [Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2](./Contents/Part2/Section-12-Part2-Control-Groups-cgroups-Deep-Dive-v1-vs-v2.md)                                           |
| 6 | Union Filesystems and Layered Storage (overlay2 Internals)    | [Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals](./Contents/Part2/Section-13-Part2-Union-Filesystems-and-Layered-Storage-overlay2-Internals.md)             |
| 7 | containerd and the CRI's Relationship to Kubernetes           | [Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes](./Contents/Part2/Section-14-Part2-containerd-and-the-CRIs-Relationship-to-Kubernetes.md)                         |
| 8 | Docker Daemon Configuration (daemon.json, Socket Permissions) | [Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions](./Contents/Part2/Section-15-Part2-Docker-Daemon-Configuration-daemon-json-and-Socket-Permissions.md) |

### Part 3 — Images and Dockerfile Authoring

Image anatomy (layers, manifest, config), Dockerfile instructions (FROM/RUN/COPY/ADD, CMD vs ENTRYPOINT, WORKDIR/ENV/ARG/LABEL, EXPOSE/VOLUME/USER), .dockerignore and build context, base image selection, tagging, BuildKit basics, and image inspection.

| §  | Section                                                  | File                                                                                                                                                                     |
| -- | -------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1  | Image Anatomy: Layers, Manifest, and Config              | [Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config](./Contents/Part3/Section-16-Part3-Image-Anatomy-Layers-Manifest-and-Config.md)                               |
| 2  | Dockerfile Fundamentals: FROM, RUN, COPY, ADD            | [Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD](./Contents/Part3/Section-17-Part3-Dockerfile-Fundamentals-FROM-RUN-COPY-ADD.md)                             |
| 3  | CMD vs ENTRYPOINT: Semantics and Interactions            | [Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions](./Contents/Part3/Section-18-Part3-CMD-vs-ENTRYPOINT-Semantics-and-Interactions.md)                       |
| 4  | WORKDIR, ENV, ARG, and LABEL                             | [Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL](./Contents/Part3/Section-19-Part3-WORKDIR-ENV-ARG-and-LABEL.md)                                                             |
| 5  | EXPOSE, VOLUME, and USER Instructions                    | [Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions](./Contents/Part3/Section-20-Part3-EXPOSE-VOLUME-and-USER-Instructions.md)                                         |
| 6  | .dockerignore and Build Context Mechanics                | [Section-21-Part3-dockerignore-and-Build-Context-Mechanics](./Contents/Part3/Section-21-Part3-dockerignore-and-Build-Context-Mechanics.md)                               |
| 7  | Base Image Selection (distroless, alpine, slim, scratch) | [Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch](./Contents/Part3/Section-22-Part3-Base-Image-Selection-distroless-alpine-slim-and-scratch.md) |
| 8  | Image Tagging Conventions and Semantic Versioning        | [Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning](./Contents/Part3/Section-23-Part3-Image-Tagging-Conventions-and-Semantic-Versioning.md)             |
| 9  | Building Images: docker build and BuildKit Basics        | [Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics](./Contents/Part3/Section-24-Part3-Building-Images-docker-build-and-BuildKit-Basics.md)               |
| 10 | Inspecting Images: docker inspect, history, and dive     | [Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive](./Contents/Part3/Section-25-Part3-Inspecting-Images-docker-inspect-history-and-dive.md)             |

### Part 4 — Container Lifecycle and CLI

docker run flags and patterns, the container lifecycle, exec and attach, logs and log drivers, docker cp, resource constraints, restart policies and HEALTHCHECK, and prune and disk-usage management.

| § | Section                                                        | File                                                                                                                                                                           |
| - | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1 | docker run Deep Dive: Flags and Common Patterns                | [Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns](./Contents/Part4/Section-26-Part4-docker-run-Deep-Dive-Flags-and-Common-Patterns.md)                         |
| 2 | Container Lifecycle: create, start, stop, restart, pause, kill | [Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill](./Contents/Part4/Section-27-Part4-Container-Lifecycle-create-start-stop-restart-pause-kill.md)     |
| 3 | Executing Commands in Running Containers: exec and attach      | [Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach](./Contents/Part4/Section-28-Part4-Executing-Commands-in-Running-Containers-exec-and-attach.md)     |
| 4 | Container Logs and Log Drivers                                 | [Section-29-Part4-Container-Logs-and-Log-Drivers](./Contents/Part4/Section-29-Part4-Container-Logs-and-Log-Drivers.md)                                                         |
| 5 | Copying Files: docker cp and Data Exchange Patterns            | [Section-30-Part4-Copying-Files-docker-cp-and-Data-Exchange-Patterns](./Contents/Part4/Section-30-Part4-Copying-Files-docker-cp-and-Data-Exchange-Patterns.md)                 |
| 6 | Resource Constraints: --memory, --cpus, --pids-limit           | [Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit](./Contents/Part4/Section-31-Part4-Resource-Constraints-memory-cpus-pids-limit.md)                               |
| 7 | Restart Policies and Health Checks (HEALTHCHECK Instruction)   | [Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction](./Contents/Part4/Section-32-Part4-Restart-Policies-and-Health-Checks-HEALTHCHECK-Instruction.md) |
| 8 | Cleaning Up: prune Commands and Disk Usage Management          | [Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management](./Contents/Part4/Section-33-Part4-Cleaning-Up-prune-Commands-and-Disk-Usage-Management.md)             |

### Part 5 — Docker Compose and Multi-Container Apps

The Compose Specification, services/networks/volumes, environment variables and .env files, dependency ordering and health checks, profiles and overrides, scaling, the Compose CLI, and local development workflows with hot reload.

| § | Section                                                         | File                                                                                                                                                                                 |
| - | --------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1 | Compose File Format: Compose v2 and the Compose Specification   | [Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification](./Contents/Part5/Section-34-Part5-Compose-File-Format-Compose-v2-and-the-Compose-Specification.md)   |
| 2 | Services, Networks, and Volumes in docker-compose.yml           | [Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml](./Contents/Part5/Section-35-Part5-Services-Networks-and-Volumes-in-docker-composeyml.md)                       |
| 3 | Environment Variables and .env Files                            | [Section-36-Part5-Environment-Variables-and-env-Files](./Contents/Part5/Section-36-Part5-Environment-Variables-and-env-Files.md)                                                     |
| 4 | Dependency Ordering: depends_on, Health Checks, Wait Strategies | [Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies](./Contents/Part5/Section-37-Part5-Dependency-Ordering-dependson-Health-Checks-Wait-Strategies.md)     |
| 5 | Compose Profiles and Multi-Environment Overrides                | [Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides](./Contents/Part5/Section-38-Part5-Compose-Profiles-and-Multi-Environment-Overrides.md)                           |
| 6 | Scaling Services with Compose                                   | [Section-39-Part5-Scaling-Services-with-Compose](./Contents/Part5/Section-39-Part5-Scaling-Services-with-Compose.md)                                                                 |
| 7 | Compose CLI Deep Dive: up, down, logs, exec                     | [Section-40-Part5-Compose-CLI-Deep-Dive-up-down-logs-exec](./Contents/Part5/Section-40-Part5-Compose-CLI-Deep-Dive-up-down-logs-exec.md)                                             |
| 8 | Compose in Local Development Workflows: Hot Reload, Bind Mounts | [Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts](./Contents/Part5/Section-41-Part5-Compose-in-Local-Development-Workflows-Hot-Reload-Bind-Mounts.md) |

### Part 6 — Networking

Network drivers, default and custom bridge networks, container DNS and service discovery, port publishing and iptables/nftables, overlay networks, troubleshooting tools, communication patterns, and network isolation and segmentation.

| § | Section                                                               | File                                                                                                                                                                                             |
| - | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| 1 | Docker Network Drivers Overview: bridge, host, none, overlay, macvlan | [Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan](./Contents/Part6/Section-42-Part6-Docker-Network-Drivers-Overview-bridge-host-none-overlay-macvlan.md)       |
| 2 | The Default Bridge Network and Custom Bridge Networks                 | [Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks](./Contents/Part6/Section-43-Part6-The-Default-Bridge-Network-and-Custom-Bridge-Networks.md)                             |
| 3 | Container DNS and Service Discovery                                   | [Section-44-Part6-Container-DNS-and-Service-Discovery](./Contents/Part6/Section-44-Part6-Container-DNS-and-Service-Discovery.md)                                                                 |
| 4 | Port Publishing and iptables/nftables Under the Hood                  | [Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood](./Contents/Part6/Section-45-Part6-Port-Publishing-and-iptables-nftables-Under-the-Hood.md)                               |
| 5 | Overlay Networks and Multi-Host Networking Concepts                   | [Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts](./Contents/Part6/Section-46-Part6-Overlay-Networks-and-Multi-Host-Networking-Concepts.md)                                 |
| 6 | Network Troubleshooting Tools and Techniques                          | [Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques](./Contents/Part6/Section-47-Part6-Network-Troubleshooting-Tools-and-Techniques.md)                                               |
| 7 | Container-to-Host and Container-to-Container Communication Patterns   | [Section-48-Part6-Container-to-Host-and-Container-to-Container-Communication-Patterns](./Contents/Part6/Section-48-Part6-Container-to-Host-and-Container-to-Container-Communication-Patterns.md) |
| 8 | Network Security: Isolation and Segmentation Patterns                 | [Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns](./Contents/Part6/Section-49-Part6-Network-Security-Isolation-and-Segmentation-Patterns.md)                               |

### Part 7 — Storage and Volumes

overlay2 internals revisited, volumes vs bind mounts vs tmpfs, named volume lifecycle, volume drivers and plugins, persistence patterns for stateful containers, backup and restore, and storage performance.

| § | Section                                                  | File                                                                                                                                                             |
| - | -------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Storage Drivers: overlay2 Internals Revisited            | [Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited](./Contents/Part7/Section-50-Part7-Storage-Drivers-overlay2-Internals-Revisited.md)               |
| 2 | Volumes vs. Bind Mounts vs. tmpfs: When Each Applies     | [Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies](./Contents/Part7/Section-51-Part7-Volumes-vs-Bind-Mounts-vs-tmpfs-When-Each-Applies.md)     |
| 3 | Named Volumes: Lifecycle and Management                  | [Section-52-Part7-Named-Volumes-Lifecycle-and-Management](./Contents/Part7/Section-52-Part7-Named-Volumes-Lifecycle-and-Management.md)                           |
| 4 | Volume Drivers and Plugins: NFS and Cloud-Backed Storage | [Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage](./Contents/Part7/Section-53-Part7-Volume-Drivers-and-Plugins-NFS-Cloud-Backed-Storage.md) |
| 5 | Data Persistence Patterns for Stateful Containers        | [Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers](./Contents/Part7/Section-54-Part7-Data-Persistence-Patterns-for-Stateful-Containers.md)     |
| 6 | Backup and Restore Strategies for Volumes                | [Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes](./Contents/Part7/Section-55-Part7-Backup-and-Restore-Strategies-for-Volumes.md)                     |
| 7 | Storage Performance Considerations                       | [Section-56-Part7-Storage-Performance-Considerations](./Contents/Part7/Section-56-Part7-Storage-Performance-Considerations.md)                                   |

### Part 8 — Security and Hardening

The container security model, running as non-root and user namespaces, capabilities, seccomp, AppArmor and SELinux, read-only filesystems, vulnerability scanning (Trivy, Docker Scout, Snyk), secrets management, and supply chain security (signing, SBOM, Content Trust).

| § | Section                                                           | File                                                                                                                                                                                     |
| - | ----------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Container Security Model: What Isolation Does and Doesn't Provide | [Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide](./Contents/Part8/Section-57-Part8-Container-Security-Model-What-Isolation-Does-and-Doesnt-Provide.md) |
| 2 | Running as Non-Root: USER Instruction and User Namespaces         | [Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces](./Contents/Part8/Section-58-Part8-Running-as-Non-Root-USER-Instruction-and-User-Namespaces.md)               |
| 3 | Capabilities: --cap-add/--cap-drop and Least Privilege            | [Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege](./Contents/Part8/Section-59-Part8-Capabilities-cap-add-cap-drop-and-Least-Privilege.md)                             |
| 4 | Seccomp Profiles                                                  | [Section-60-Part8-Seccomp-Profiles](./Contents/Part8/Section-60-Part8-Seccomp-Profiles.md)                                                                                               |
| 5 | AppArmor and SELinux with Docker                                  | [Section-61-Part8-AppArmor-and-SELinux-with-Docker](./Contents/Part8/Section-61-Part8-AppArmor-and-SELinux-with-Docker.md)                                                               |
| 6 | Read-Only Filesystems and Immutable Containers                    | [Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers](./Contents/Part8/Section-62-Part8-Read-Only-Filesystems-and-Immutable-Containers.md)                                   |
| 7 | Image Vulnerability Scanning (Trivy, Docker Scout, Snyk)          | [Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk](./Contents/Part8/Section-63-Part8-Image-Vulnerability-Scanning-Trivy-Docker-Scout-Snyk.md)                       |
| 8 | Secrets Management: Docker Secrets and Avoiding ENV-Based Secrets | [Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets](./Contents/Part8/Section-64-Part8-Secrets-Management-Docker-Secrets-Avoiding-ENV-Based-Secrets.md)       |
| 9 | Supply Chain Security: Image Signing, SBOM, Content Trust         | [Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust](./Contents/Part8/Section-65-Part8-Supply-Chain-Security-Image-Signing-SBOM-Content-Trust.md)                   |

### Part 9 — Registries and Image Distribution

Docker Hub, private registries and Harbor, cloud registries (ECR, ACR, Artifact Registry), authentication and credential helpers, push/pull workflows and tagging strategy, retention and garbage collection, and multi-architecture images.

| § | Section                                                    | File                                                                                                                                                                       |
| - | ---------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Docker Hub Fundamentals: Public/Private Repos, Rate Limits | [Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits](./Contents/Part9/Section-66-Part9-Docker-Hub-Fundamentals-Public-Private-Repos-Rate-Limits.md) |
| 2 | Private Registries: Self-Hosted Registry and Harbor        | [Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor](./Contents/Part9/Section-67-Part9-Private-Registries-Self-Hosted-Registry-and-Harbor.md)             |
| 3 | Cloud Registries: ECR, ACR, GCR/Artifact Registry          | [Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry](./Contents/Part9/Section-68-Part9-Cloud-Registries-ECR-ACR-GCR-Artifact-Registry.md)                     |
| 4 | Authentication: docker login and Credential Helpers        | [Section-69-Part9-Authentication-docker-login-and-Credential-Helpers](./Contents/Part9/Section-69-Part9-Authentication-docker-login-and-Credential-Helpers.md)             |
| 5 | Image Push/Pull Workflows and Tagging Strategies           | [Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies](./Contents/Part9/Section-70-Part9-Image-Push-Pull-Workflows-and-Tagging-Strategies.md)                 |
| 6 | Image Retention Policies and Garbage Collection            | [Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection](./Contents/Part9/Section-71-Part9-Image-Retention-Policies-and-Garbage-Collection.md)                   |
| 7 | Multi-Architecture Images: buildx, Manifest Lists          | [Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists](./Contents/Part9/Section-72-Part9-Multi-Architecture-Images-buildx-Manifest-Lists.md)                   |

### Part 10 — Build Optimization and Multi-Stage Builds

Multi-stage builds, layer caching and invalidation, BuildKit features, build secrets and SSH forwarding, minimizing image size, reproducible builds and build args, and docker buildx multi-platform pipelines.

| § | Section                                               | File                                                                                                                                                                    |
| - | ----------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Multi-Stage Builds: Pattern and Motivation            | [Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation](./Contents/Part10/Section-73-Part10-Multi-Stage-Builds-Pattern-and-Motivation.md)                         |
| 2 | Layer Caching Strategies and Build Cache Invalidation | [Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation](./Contents/Part10/Section-74-Part10-Layer-Caching-Strategies-and-Build-Cache-Invalidation.md) |
| 3 | BuildKit Deep Dive: Features and Syntax               | [Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax](./Contents/Part10/Section-75-Part10-BuildKit-Deep-Dive-Features-and-Syntax.md)                               |
| 4 | Build Secrets and SSH Forwarding During Build         | [Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build](./Contents/Part10/Section-76-Part10-Build-Secrets-and-SSH-Forwarding-During-Build.md)                 |
| 5 | Minimizing Image Size: Techniques and Trade-offs      | [Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs](./Contents/Part10/Section-77-Part10-Minimizing-Image-Size-Techniques-and-Trade-offs.md)             |
| 6 | Reproducible Builds and Build Args Best Practices     | [Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices](./Contents/Part10/Section-78-Part10-Reproducible-Builds-and-Build-Args-Best-Practices.md)         |
| 7 | docker buildx: Multi-Platform Build Pipelines         | [Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines](./Contents/Part10/Section-79-Part10-docker-buildx-Multi-Platform-Build-Pipelines.md)                   |

### Part 11 — CI/CD Integration

Docker in GitHub Actions, GitLab CI and Jenkins, Docker-in-Docker vs socket mounting, automated build-and-push pipelines, integration testing with ephemeral containers, GitOps image promotion, and CI build caching.

| § | Section                                                       | File                                                                                                                                                                              |
| - | ------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Docker in CI/CD Pipelines: GitHub Actions, GitLab CI, Jenkins | [Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins](./Contents/Part11/Section-80-Part11-Docker-in-CI-CD-Pipelines-GitHub-Actions-GitLab-CI-Jenkins.md) |
| 2 | Docker-in-Docker vs. Docker Socket Mounting: Trade-offs       | [Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs](./Contents/Part11/Section-81-Part11-Docker-in-Docker-vs-Docker-Socket-Mounting-Trade-offs.md)           |
| 3 | Automated Image Build-and-Push Pipelines                      | [Section-82-Part11-Automated-Image-Build-and-Push-Pipelines](./Contents/Part11/Section-82-Part11-Automated-Image-Build-and-Push-Pipelines.md)                                     |
| 4 | Integration Testing with Ephemeral Containers                 | [Section-83-Part11-Integration-Testing-with-Ephemeral-Containers](./Contents/Part11/Section-83-Part11-Integration-Testing-with-Ephemeral-Containers.md)                           |
| 5 | GitOps Patterns for Container Image Promotion                 | [Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion](./Contents/Part11/Section-84-Part11-GitOps-Patterns-for-Container-Image-Promotion.md)                           |
| 6 | Build Caching Strategies in CI for Faster Pipelines           | [Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines](./Contents/Part11/Section-85-Part11-Build-Caching-Strategies-in-CI-for-Faster-Pipelines.md)               |

### Part 12 — Production Operations and Monitoring

Logging architectures, monitoring with cAdvisor and Prometheus, health checks and self-healing, resource management at scale, Docker Swarm in pre-Kubernetes context, zero-downtime deployments, disaster recovery and rollback, and production troubleshooting.

| § | Section                                                               | File                                                                                                                                                                                              |
| - | --------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Logging Architectures for Containerized Applications                  | [Section-86-Part12-Logging-Architectures-for-Containerized-Applications](./Contents/Part12/Section-86-Part12-Logging-Architectures-for-Containerized-Applications.md)                             |
| 2 | Monitoring: cAdvisor, Prometheus, and Container Metrics               | [Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics](./Contents/Part12/Section-87-Part12-Monitoring-cAdvisor-Prometheus-and-Container-Metrics.md)                             |
| 3 | Health Checks and Self-Healing Patterns                               | [Section-88-Part12-Health-Checks-and-Self-Healing-Patterns](./Contents/Part12/Section-88-Part12-Health-Checks-and-Self-Healing-Patterns.md)                                                       |
| 4 | Resource Management at Scale                                          | [Section-89-Part12-Resource-Management-at-Scale](./Contents/Part12/Section-89-Part12-Resource-Management-at-Scale.md)                                                                             |
| 5 | Docker Swarm as a Native Orchestrator (Brief, Pre-Kubernetes Context) | [Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context](./Contents/Part12/Section-90-Part12-Docker-Swarm-as-a-Native-Orchestrator-Brief-Pre-Kubernetes-Context.md) |
| 6 | Zero-Downtime Deployment Patterns with Docker                         | [Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker](./Contents/Part12/Section-91-Part12-Zero-Downtime-Deployment-Patterns-with-Docker.md)                                           |
| 7 | Disaster Recovery and Rollback Strategies                             | [Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies](./Contents/Part12/Section-92-Part12-Disaster-Recovery-and-Rollback-Strategies.md)                                                   |
| 8 | Troubleshooting Production Container Issues                           | [Section-93-Part12-Troubleshooting-Production-Container-Issues](./Contents/Part12/Section-93-Part12-Troubleshooting-Production-Container-Issues.md)                                               |

### Part 13 — Mastery: Best Practices, Anti-Patterns, and Comparisons

A Dockerfile best-practices checklist, common anti-patterns, Docker vs Podman vs standalone containerd, when Docker is the wrong tool, a performance tuning recap, and the path from Docker to orchestration.

| § | Section                                                          | File                                                                                                                                                                                    |
| - | ---------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Dockerfile Best Practices Checklist                              | [Section-94-Part13-Dockerfile-Best-Practices-Checklist](./Contents/Part13/Section-94-Part13-Dockerfile-Best-Practices-Checklist.md)                                                     |
| 2 | Common Anti-Patterns and Why They Hurt                           | [Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt](./Contents/Part13/Section-95-Part13-Common-Anti-Patterns-and-Why-They-Hurt.md)                                               |
| 3 | Docker vs. Podman vs. Standalone containerd: Detailed Comparison | [Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison](./Contents/Part13/Section-96-Part13-Docker-vs-Podman-vs-Standalone-containerd-Detailed-Comparison.md) |
| 4 | When Docker Is the Wrong Tool                                    | [Section-97-Part13-When-Docker-Is-the-Wrong-Tool](./Contents/Part13/Section-97-Part13-When-Docker-Is-the-Wrong-Tool.md)                                                                 |
| 5 | Performance Tuning Recap                                         | [Section-98-Part13-Performance-Tuning-Recap](./Contents/Part13/Section-98-Part13-Performance-Tuning-Recap.md)                                                                           |
| 6 | The Path from Docker to Orchestration (Swarm vs. Kubernetes)     | [Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes](./Contents/Part13/Section-99-Part13-The-Path-from-Docker-to-Orchestration-Swarm-vs-Kubernetes.md)         |

### Part 14 — Interview Preparation

The DCA domain breakdown, a beginner-to-advanced interview question bank, scenario-based troubleshooting, Dockerfile code-review questions, container system design questions, and a hands-on exercise bank.

| § | Section                                                  | File                                                                                                                                                                        |
| - | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Docker Certified Associate (DCA) Domain Breakdown        | [Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown](./Contents/Part14/Section-100-Part14-Docker-Certified-Associate-DCA-Domain-Breakdown.md)               |
| 2 | Common Docker Interview Questions (Beginner to Advanced) | [Section-101-Part14-Common-Docker-Interview-Questions-Beginner-to-Advanced](./Contents/Part14/Section-101-Part14-Common-Docker-Interview-Questions-Beginner-to-Advanced.md) |
| 3 | Scenario-Based Troubleshooting Questions                 | [Section-102-Part14-Scenario-Based-Troubleshooting-Questions](./Contents/Part14/Section-102-Part14-Scenario-Based-Troubleshooting-Questions.md)                             |
| 4 | Dockerfile Code-Review Style Questions                   | [Section-103-Part14-Dockerfile-Code-Review-Style-Questions](./Contents/Part14/Section-103-Part14-Dockerfile-Code-Review-Style-Questions.md)                                 |
| 5 | System Design Questions Involving Containers             | [Section-104-Part14-System-Design-Questions-Involving-Containers](./Contents/Part14/Section-104-Part14-System-Design-Questions-Involving-Containers.md)                     |
| 6 | Hands-On Whiteboard / Live-Coding Exercise Bank          | [Section-105-Part14-Hands-On-Whiteboard-Live-Coding-Exercise-Bank](./Contents/Part14/Section-105-Part14-Hands-On-Whiteboard-Live-Coding-Exercise-Bank.md)                   |

### Part 15 — Wrap-Up

Progressive hands-on labs, a consolidated key-takeaways checklist, a misconceptions and anti-patterns recap, and related technologies and next topics.

| § | Section                                                  | File                                                                                                                                                                  |
| - | -------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| 1 | Progressive Hands-On Labs (Beginner to Production-Style) | [Section-106-Part15-Progressive-Hands-On-Labs-Beginner-Production-Style](./Contents/Part15/Section-106-Part15-Progressive-Hands-On-Labs-Beginner-Production-Style.md) |
| 2 | Consolidated Key-Takeaways Checklist                     | [Section-107-Part15-Consolidated-Key-Takeaways-Checklist](./Contents/Part15/Section-107-Part15-Consolidated-Key-Takeaways-Checklist.md)                               |
| 3 | Common Misconceptions and Anti-Patterns Recap            | [Section-108-Part15-Common-Misconceptions-and-Anti-Patterns-Recap](./Contents/Part15/Section-108-Part15-Common-Misconceptions-and-Anti-Patterns-Recap.md)             |
| 4 | Related Technologies and Recommended Next Topics         | [Section-109-Part15-Related-Technologies-and-Recommended-Next-Topics](./Contents/Part15/Section-109-Part15-Related-Technologies-and-Recommended-Next-Topics.md)       |

---

_Last updated: October 6, 2026_
