# Section 15 — Azure Container Instances (ACI)

## 1. Definition

**Plain language:** Azure Container Instances lets you run a single container (or a small group of containers) directly on Azure, with a single command, without needing a VM to host it or a full Kubernetes cluster to orchestrate it — the fastest, simplest way to just "run this container image right now."

**Precise definition:** Azure Container Instances (ACI) is a Containers-as-a-Service (CaaS, introduced conceptually in Section 2.7) offering that provisions and runs container groups on-demand, billed per-second based on allocated vCPU and memory, without requiring the customer to provision, patch, or manage any underlying VM or orchestrator.

## 2. Why It Exists / Problem It Solves

Running a container traditionally required either a VM with a container runtime installed and manually managed (reintroducing all the IaaS operational overhead containers are meant to help avoid), or a full orchestrator like Kubernetes (AKS, Part 7) — powerful, but genuinely excessive complexity and operational overhead for a workload that's simply "run this one container, briefly, on demand" (a CI/CD build step, a short-lived batch job, a quick isolated task). ACI exists to fill this gap: the fastest possible path from "I have a container image" to "it's running," with per-second billing suited to genuinely short-lived or bursty workloads, and none of the cluster-management overhead that even a managed Kubernetes offering still carries.

## 3. Core Concepts

### 3.1 Container Groups

**Definition:** ACI's fundamental deployment unit is a **Container Group** — one or more containers that are scheduled together onto the same underlying host, sharing a lifecycle, local network namespace (allowing containers within the group to communicate via `localhost`), and optionally, storage volumes. This is conceptually similar to a Kubernetes Pod (a concept revisited directly in Section 36), though ACI's container groups are a simpler, standalone construct without the broader orchestration machinery Kubernetes provides.

**When multi-container groups are used:** A common pattern is a primary application container paired with a "sidecar" container providing a supporting function — such as a logging agent, a monitoring agent, or a network proxy — that needs to run alongside the main container and share its local network and lifecycle.

### 3.2 Resource Allocation and Billing

Each container (or container group) specifies its required vCPU and memory allocation explicitly, and ACI bills per-second based on that allocated resource consumption for the actual duration the container runs — there's no underlying VM to separately provision, size, or pay for independently of the container's actual resource request and runtime.

💡 **Tip:** This per-second, resource-request-based billing model is what makes ACI genuinely cost-effective specifically for short-lived, bursty workloads — a container that runs for 30 seconds is billed for roughly 30 seconds of its requested resources, not for an underlying VM that had to be provisioned and left running.

### 3.3 Restart Policies

ACI supports configurable restart policies determining what happens when a container's process exits:

- **Always** — the container is always restarted after exiting, suited to long-running services expected to run continuously.
- **Never** — the container is never restarted after exiting, suited to genuinely one-shot tasks (like a batch job) that should simply complete and stop.
- **OnFailure** — the container is restarted only if it exits with a non-zero (failure) exit code, suited to batch/job-style workloads that should retry on failure but not restart after a clean, successful exit.

### 3.4 Networking

ACI containers can be deployed with a public IP address (directly internet-reachable) or, for private/internal scenarios, deployed into a specific subnet of a Virtual Network (Section 21), allowing them to communicate with other private resources (like a database) without public exposure — this VNet deployment option is what allows ACI to participate in the broader private networking architectures covered in Part 5, rather than being limited to purely public-facing use cases.

## 4. Architecture Diagram

```
ACI Container Group "cig-batch-job"
 ├── Container: "processor"   (vCPU: 1, Memory: 1.5 GB)
 │      — the main workload container
 └── Container: "log-shipper" (vCPU: 0.25, Memory: 0.5 GB)
        — sidecar, shares localhost network with "processor"

Restart Policy: OnFailure
Networking: deployed into subnet "snet-batch" within VNet "vnet-prod"
             (no public IP — reaches internal resources only)

Billing: per-second, based on (1 + 0.25) vCPU and (1.5 + 0.5) GB
          for the actual duration the group runs
```

## 5. Configuration & Hands-On Example

**Running a single container with ACI:**

```bash
az container create \
  --resource-group rg-myapp-prod \
  --name aci-image-resize-job \
  --image myregistry.azurecr.io/image-resizer:latest \
  --cpu 1 --memory 1.5 \
  --restart-policy OnFailure \
  --registry-login-server myregistry.azurecr.io \
  --registry-username <acr-username> \
  --registry-password <acr-password>
```

- **Purpose:** Runs a single container from a private Azure Container Registry (Section 35) image, allocating 1 vCPU and 1.5 GB memory, restarting only on failure — appropriate for a one-shot batch-style job.
- **Important arguments explained individually:**
  - `--cpu` / `--memory` — explicit resource allocation; ACI bills based on these requested values, so right-sizing this allocation (similar to VM right-sizing, Section 11.4) directly affects cost.
  - `--restart-policy` — set to `OnFailure`, meaning a clean successful exit leaves the container stopped (appropriate for a batch job that shouldn't loop indefinitely), but a failure triggers an automatic retry.
  - `--registry-login-server` / `--registry-username` / `--registry-password` — credentials for pulling from a private registry; in production, Managed Identity-based registry authentication (rather than passing a username/password directly) is the more secure pattern, avoiding stored registry credentials entirely.
- **Common error:** `ImagePullFailure` if registry credentials are incorrect or the image tag doesn't exist — verify the image reference and registry authentication before troubleshooting further.

**Checking container logs (useful for debugging a completed or failed run):**

```bash
az container logs --resource-group rg-myapp-prod --name aci-image-resize-job
```

- **Purpose:** Retrieves stdout/stderr output from the container, essential for diagnosing why a one-shot job failed or behaved unexpectedly, especially since the container may no longer be running by the time you investigate.

## 6. Production & Enterprise Usage

Enterprises use ACI primarily for genuinely short-lived, on-demand workloads: CI/CD pipeline build/test steps that need an isolated, ephemeral container environment (Azure DevOps and GitHub Actions can both provision ACI-based ephemeral agents), scheduled or event-triggered batch jobs (often invoked from an Azure Function or Logic App, Part 8), and burst-capacity scenarios where a small amount of additional container-based compute is needed briefly without provisioning dedicated always-on infrastructure. ACI is generally **not** used as the primary hosting platform for a full production application requiring sophisticated orchestration (rolling updates, service discovery, auto-healing across many replicas, complex networking policies) — that's the domain of AKS (Part 7); ACI's role in most enterprise architectures is specifically for simple, standalone, or short-lived container execution rather than a full application platform.

## 7. Security Considerations

- Container images pulled from public registries should be vetted for known vulnerabilities before use; Microsoft Defender for Cloud (Part 11) can scan container images for known vulnerabilities as part of a broader security posture.
- Managed Identity-based authentication to Azure Container Registry (rather than embedded registry username/password credentials) is the recommended pattern to avoid stored registry credentials.
- For containers handling sensitive data or requiring network isolation, VNet deployment (Section 15.3.4) rather than a public IP is the appropriate choice, keeping the container reachable only from within the private network.

## 8. Performance Considerations

ACI container group startup time (the delay between issuing a create command and the container actually running) is generally fast relative to provisioning a full VM, but is not instantaneous — for workloads requiring the absolute fastest possible cold-start (sub-second), even ACI's startup latency may be a consideration, in which case an always-running compute option (App Service, a persistent AKS deployment) might be more appropriate than repeatedly creating fresh ACI instances per invocation.

## 9. Monitoring

Basic container metrics (CPU, memory usage) and logs are available through the Portal and CLI (`az container logs`, shown above) directly; for more sophisticated, longer-term log aggregation and alerting across many ACI instances, integration with Azure Monitor / Log Analytics (Part 10) is the standard approach, particularly important given that ACI instances are often short-lived and their direct logs may not be conveniently accessible after the instance is deleted unless shipped elsewhere.

## 10. Troubleshooting

| Symptom                                                                             | Likely Cause                                                                                    | Fix                                                                                                                                        |
| ----------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| `ImagePullFailure` at container creation                                            | Incorrect registry credentials, wrong image name/tag, or registry network access issue          | Verify registry authentication and exact image reference; check registry network accessibility if using a private VNet-restricted registry |
| Container exits immediately after starting                                          | Application error inside the container, or incorrect container entrypoint/command configuration | Check `az container logs` for the container's actual stdout/stderr output to diagnose the application-level failure                        |
| Container group deployed into a VNet subnet can't reach expected internal resources | Subnet delegation not configured correctly, or NSG rules (Part 5) blocking required traffic     | Verify the subnet is properly delegated for ACI use and that NSG rules permit the required traffic paths                                   |

## 11. Interview Questions — Section 15

### 🎯 Beginner

**Q: When would you choose Azure Container Instances over Azure Kubernetes Service for running a container?**

_Model answer:_ ACI is appropriate for simple, often short-lived or on-demand container workloads — a CI/CD build step, a one-off batch job, a quick isolated task — where the operational overhead of provisioning and managing a full Kubernetes cluster would be unnecessary and excessive. AKS is appropriate when you need genuine orchestration capabilities across many containers and replicas: rolling updates, auto-healing, service discovery, complex networking and scaling policies, and coordination of many interdependent services — capabilities ACI simply doesn't provide, since it's designed for running individual container groups, not orchestrating a full application platform.

_What the interviewer is probing:_ whether the candidate understands that "run a container" doesn't automatically mean "need Kubernetes" — recognizing when the simpler tool is the right tool is itself a signal of good engineering judgment.

### 🎯 Intermediate

**Q: How does ACI's billing model make it particularly cost-effective for certain workload types, and where does that advantage break down?**

_Model answer:_ ACI bills per-second based on the actual vCPU/memory the container consumes for the actual duration it runs, with no underlying VM to separately provision or pay for — for a workload that runs briefly and infrequently (a batch job that runs for two minutes once an hour, for example), this is far more cost-effective than maintaining an always-on VM or App Service Plan sized to handle that same brief burst of work. The advantage breaks down for workloads that need to run continuously or very frequently — at high enough sustained utilization, the per-second ACI rate can exceed the cost of an equivalently-sized always-on VM or App Service Plan, at which point a persistent compute option becomes more cost-effective than repeatedly paying ACI's on-demand rate.

_What the interviewer is probing:_ whether the candidate can reason quantitatively about when a serverless/on-demand billing model is actually advantageous versus when it isn't, rather than assuming any "serverless"-adjacent option is unconditionally cheaper.

## 12. Common Misconceptions

- **"ACI is just a smaller version of AKS."** Not quite accurate — ACI doesn't provide orchestration capabilities (auto-healing, rolling updates across replicas, service discovery) at all; it's a simpler, fundamentally different tool for running individual container groups directly, not a scaled-down orchestrator.
- **"Container groups in ACI work exactly like Kubernetes Pods with full feature parity."** They're conceptually similar (co-scheduled containers sharing network/lifecycle) but ACI container groups lack the broader Kubernetes ecosystem features (health probes with automatic remediation across a replica set, Services, Deployments, and so on) covered in Part 7 — the similarity is conceptual, not a feature-for-feature match.

## 13. Key Takeaways

- 🔑 ACI is Azure's CaaS offering for running individual containers or small container groups directly, without a VM or orchestrator, billed per-second based on allocated resources.
- 🔑 Container Groups allow multiple co-located containers (e.g., a main container plus a logging/monitoring sidecar) to share network and lifecycle, conceptually similar to (but simpler than) a Kubernetes Pod.
- 🔑 Restart policies (Always/Never/OnFailure) should be chosen based on whether the workload is a continuous service or a one-shot/batch-style task.
- 🔑 ACI is best suited to short-lived, on-demand, or bursty container workloads (CI/CD steps, batch jobs); sustained, complex, multi-service application hosting belongs on AKS instead.

## 14. Related Concepts / Part 3 Wrap-Up

This completes **Part 3 — Core Compute**, covering the full spectrum of Azure compute options from full IaaS control (VMs, Section 11; VM Scale Sets, Section 12) through PaaS (App Service, Section 13) to serverless/FaaS (Functions, Section 14) and CaaS (ACI, this section) — directly building out the service-model spectrum first introduced conceptually in Section 2. **Part 4 — Storage** begins next with Section 16, covering Azure Storage Account fundamentals, the foundational data-persistence layer that virtually every compute option covered in this Part depends on in some form (VM disks, Function app storage requirements, container image registries, and application data all ultimately rely on Azure Storage primitives).
