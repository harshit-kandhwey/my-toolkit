# Section 35 — Azure Kubernetes Service (AKS) — Architecture

**Part 7: Containers & Orchestration | Section 35 of 70**
**Prerequisites:** Section 33 (Docker Fundamentals), Section 34 (Azure Container Registry), Section 11 (Azure Virtual Machines), Section 21–22 (VNet, Subnets, NSGs)
**Leads into:** Section 36 (AKS Networking, Scaling, Security), Section 37 (AKS Production Operations)

---

## 35.1 Introduction and Scope

This section covers the architecture of Azure Kubernetes Service: what Kubernetes is and the problem it solves, the control plane vs. node architecture, how AKS specifically manages the control plane as a service, core Kubernetes objects (pods, deployments, services), and the scheduling and self-healing model. Section 36 builds on this foundation for networking, scaling, and security; Section 37 covers day-2 production operations (upgrades, node pool management, cluster maintenance).

🔑 **Key Takeaway:** AKS is not a different product from open-source Kubernetes — it is upstream, conformant Kubernetes with Azure managing the control plane and integrating Azure-native services (networking, identity, storage, monitoring) as pluggable components. Everything learned about standard Kubernetes concepts transfers directly; the "Azure" part of AKS is primarily about _what manages the control plane_ and _which Azure services plug into_ standard Kubernetes extension points.

---

## 35.2 What Is Kubernetes and What Problem It Solves

### 35.2.1 Definition

**Plain language:** Kubernetes is a system that runs many containers across many machines, automatically deciding where each container runs, restarting it if it fails, scaling it up or down, and routing network traffic to it — so operators declare the _desired state_ of an application and Kubernetes continuously works to make reality match it.

**Precise definition:** Kubernetes (often abbreviated "K8s") is an open-source container orchestration platform, originally developed by Google and now governed by the Cloud Native Computing Foundation (CNCF), that automates the deployment, scaling, networking, and lifecycle management of containerized applications across a cluster of machines.

### 35.2.2 The Problem It Solves

Section 33 established that Docker Compose is a local-development convenience, not a production orchestration mechanism, because production requirements Compose does not address include:

- **Multi-host scheduling:** deciding _which_ of potentially hundreds of machines should run a given container, accounting for available CPU/memory, existing load, and placement constraints — Docker alone has no concept of a "cluster" of hosts to schedule across.
- **Self-healing:** if a container crashes, or the host it runs on fails entirely, something must detect this and reschedule the workload elsewhere automatically, without human intervention paging someone at 3 AM for a routine restart.
- **Declarative desired state:** rather than issuing imperative commands ("start this container," "stop that one"), operators declare "I want 5 replicas of this application running, each with these resource limits," and the system continuously reconciles actual state toward that desired state — including automatically correcting drift (a crashed replica is automatically replaced to restore the declared count of 5).
- **Service discovery and load balancing at scale:** with potentially many replicas of many services across many hosts, and replicas being created/destroyed dynamically by scaling and self-healing, static IP-based configuration (as used in simple Compose networking, Section 33.8.3) does not scale; Kubernetes provides a stable virtual IP/DNS name per service that transparently load-balances across whichever pod replicas currently exist.
- **Rolling updates and rollback:** deploying a new version without downtime, replacing old replicas with new ones gradually while monitoring health, and automatically or manually rolling back if the new version is unhealthy.

### 35.2.3 What Existed Before Kubernetes (Brief)

- **Docker Swarm:** Docker's own native orchestrator, simpler to operate than Kubernetes but with a much smaller ecosystem and fewer advanced scheduling/extension capabilities; still exists but has a small fraction of Kubernetes' industry adoption today.
- **Apache Mesos / Marathon:** an earlier general-purpose cluster resource manager (not container-specific), influential in early cluster-scheduling thinking but has been largely superseded by Kubernetes in the container orchestration space.
- **Google's internal systems (Borg, Omega):** Kubernetes' design is explicitly derived from over a decade of Google's internal experience running containerized workloads at massive scale via these predecessor internal systems, published and open-sourced starting in 2014.

### 35.2.4 Why AKS Specifically (Rather Than Self-Managed Kubernetes on Azure VMs)

- **Control plane management:** Kubernetes' control plane (35.3) is complex, stateful (etcd), and requires careful operational discipline (upgrades, backup, high availability) to run reliably; AKS manages this entirely, removing that operational burden from the customer.
- **Azure-native integration out of the box:** identity (Microsoft Entra ID / Managed Identities), networking (Azure CNI, Load Balancer, Application Gateway Ingress), storage (Azure Disks/Files as PersistentVolumes), and monitoring (Azure Monitor/Container Insights) are all pre-integrated, rather than requiring manual configuration of each Kubernetes extension point.
- **No control-plane cost (at time of writing, for most tiers):** the AKS control plane itself is offered without direct charge on the free tier (customers pay only for the node VMs and other consumed Azure resources); a paid tier (the Standard/Uptime SLA-backed tier) exists for workloads requiring a financially backed SLA on control plane availability. ⚠️ **Warning:** exact pricing tiers, names, and SLA terms should be verified against current Microsoft documentation, as these details are subject to change.

---

## 35.3 Kubernetes Architecture: Control Plane and Nodes

### 35.3.1 Definition

A Kubernetes cluster consists of two categories of machines: the **control plane** (the "brain" — makes scheduling and cluster-state decisions) and **worker nodes** (the machines that actually run application containers, called pods).

### 35.3.2 Control Plane Components

```
┌─────────────────────────────────────────────────────────────┐
│                        CONTROL PLANE                          │
│                  (fully managed by Azure in AKS)               │
│                                                                 │
│  ┌───────────────┐   ┌──────────────┐   ┌───────────────────┐ │
│  │  kube-apiserver │◄──│  etcd         │   │ kube-scheduler     │ │
│  │  (REST API,      │  │  (cluster      │   │ (decides which     │ │
│  │  front door for   │  │  state store,  │   │ node a new pod     │ │
│  │  all requests)    │  │  key-value)   │   │ should run on)      │ │
│  └───────┬───────┘   └──────────────┘   └───────────────────┘ │
│           │                                                      │
│  ┌───────▼───────────────┐                                    │
│  │ kube-controller-manager │  (runs reconciliation control       │
│  │                          │   loops: ReplicaSet, Node,          │
│  │                          │   Deployment controllers, etc.)     │
│  └──────────────────────────┘                                    │
└─────────────────────────────────────────────────────────────┘
                              │ API calls
                              ▼
┌─────────────────────────────────────────────────────────────┐
│                          WORKER NODES                          │
│                (Azure VMs / VM Scale Set instances)             │
│                                                                 │
│   Node 1                    Node 2                    Node N   │
│  ┌─────────────┐          ┌─────────────┐          ┌────────┐ │
│  │  kubelet      │          │  kubelet      │          │ ...    │ │
│  │  kube-proxy   │          │  kube-proxy   │          │        │ │
│  │  containerd    │          │  containerd    │          │        │ │
│  │  [pod] [pod]  │          │  [pod] [pod]  │          │        │ │
│  └─────────────┘          └─────────────┘          └────────┘ │
└─────────────────────────────────────────────────────────────┘
```

- **`kube-apiserver`:** the single entry point for all cluster interactions — `kubectl` commands, internal component communication, and any automation all go through the API server's REST API. It validates and persists requests and is the only component that talks directly to `etcd`.
- **`etcd`:** a distributed, consistent key-value store holding the entire cluster's state — every object definition (deployments, services, secrets, config, current pod placements) lives here. Losing `etcd` data without a backup means losing the cluster's entire declared state.
- **`kube-scheduler`:** watches for newly created pods that have no node assignment yet, and assigns each to a suitable node based on resource requirements (33.7.3's cgroup-backed requests/limits), constraints (affinity/anti-affinity, taints/tolerations, covered in Section 36), and current node load.
- **`kube-controller-manager`:** runs numerous **control loops**, each responsible for one type of reconciliation — for example, the ReplicaSet controller continuously ensures the actual number of running pod replicas matches the declared desired count, and the Node controller tracks node health and evicts pods from nodes that have gone unresponsive.

### 35.3.3 AKS-Specific: Who Manages What

🔑 **Key Takeaway — the single most important architectural fact about AKS:** in AKS, **Azure fully manages and hosts the control plane** (`kube-apiserver`, `etcd`, `kube-scheduler`, `kube-controller-manager`) on Azure-managed infrastructure, invisible to and inaccessible by the customer directly — there is no VM, no resource group entry, no billed compute the customer sees for these components (aside from the tier-based charge on the paid Uptime SLA tier, per 35.2.4). The customer only sees, manages, and pays for the **node pool VMs**, which are standard Azure VMs / VM Scale Set instances (Section 11–12 concepts apply directly) that the customer _can_ see in their resource group, size, and scale.

This division matters concretely:

- Customers **cannot** SSH into or directly modify the control plane; all interaction happens exclusively through the standard Kubernetes API (`kubectl`, ARM/Azure CLI wrappers around it, or direct API calls).
- Azure handles control-plane version upgrades, patching, and high availability of `etcd` and the API server; the customer is responsible for **node pool** OS patching cadence and Kubernetes version upgrades on the node side (though AKS provides managed upgrade automation for this too, covered in Section 37).
- Control plane high availability (multiple `etcd`/API server replicas across availability zones) is handled transparently by Azure on qualifying tiers/regions, without the customer needing to design or provision it — a stark contrast to self-managed Kubernetes, where achieving a highly available control plane is a substantial, error-prone undertaking.

### 35.3.4 Node Components

- **`kubelet`:** the primary "node agent" — communicates with the control plane's API server, receives pod specifications assigned to its node, and ensures the containers described in those specifications are actually running (via the node's container runtime) and healthy.
- **`kube-proxy`:** implements the networking rules that make Kubernetes Services (35.5.4) work — maintaining network rules (historically iptables-based, increasingly IPVS or eBPF-based in modern configurations) on each node so that traffic to a Service's virtual IP is correctly routed to one of the backing pods, wherever they are running in the cluster.
- **Container runtime (`containerd`):** as established in Section 33.4, AKS nodes run `containerd` directly as the CRI-compliant runtime — there is no `dockerd` on modern AKS nodes; `kubelet` talks to `containerd` via the Container Runtime Interface (CRI) to actually create and manage containers, ultimately via `runc` exactly as described in Section 33.4.2.

### 35.3.5 AKS Nodes Are Azure VMs (Direct Application of Section 11)

Every AKS worker node is, underneath, a standard Azure VM belonging to a **VM Scale Set** (Section 12 concepts apply directly — AKS node pools are implemented using VM Scale Sets for the standard "Virtual Machine Scale Sets" node pool type). This means:

- VM sizing choices (Section 11.3 — series, vCPU/memory ratios) apply directly to choosing a node pool's VM size, with the additional consideration that some resources on each node are reserved for the OS and Kubernetes system components (`kubelet`, `kube-proxy`, `containerd`) and are not available to application pods — a detail with direct capacity-planning consequences covered further in Section 36.
- Availability Zone placement (Section 3's AZ concepts) applies to spreading node pool instances across zones for resilience against a single-zone failure, configured at node pool creation.
- Azure VM-level concepts — managed disks for the node OS disk (Section 18), NSGs at the subnet level (Section 22) — all apply to the infrastructure underneath a node pool, layered beneath the Kubernetes-level networking and security concepts covered in Section 36.

---

## 35.4 Pods: The Fundamental Kubernetes Unit

### 35.4.1 Definition

**Plain language:** a pod is the smallest deployable unit in Kubernetes — usually a single container, but capable of holding a small group of tightly coupled containers that must run together on the same node and share networking and storage.

**Precise definition:** a Pod is a Kubernetes API object representing one or more containers that are guaranteed to be co-located on the same node, share a single network namespace (and therefore a single IP address and port space) and, optionally, shared storage volumes.

### 35.4.2 Why the Pod Abstraction Exists (Rather Than Scheduling Containers Directly)

- Some application patterns genuinely require multiple tightly coupled processes sharing network/storage — e.g., a "sidecar" container handling log shipping or a service mesh proxy alongside a primary application container. The pod abstraction gives Kubernetes a natural unit for "these containers must always be scheduled and scaled together."
- Every container in a pod shares the pod's single IP address; containers within a pod communicate with each other via `localhost`, exactly as if they were separate processes on the same physical/virtual machine — this directly parallels the Docker Compose networking model from Section 33.8.3, but formalized as a first-class scheduling unit rather than a development-convenience construct.

### 35.4.3 Pod Lifecycle

```
Pending → Running → Succeeded / Failed
                │
                └─→ (if container crashes) → restarted per restartPolicy, pod stays Running
                                              (unless CrashLoopBackOff threshold behavior applies)
```

- **Pending:** the pod has been accepted by the API server but is not yet fully scheduled/running (waiting for a node assignment, or waiting for its container images to be pulled — directly connecting to Section 33/34's image-pull mechanics).
- **Running:** the pod has been bound to a node and at least one container is running.
- **Succeeded/Failed:** terminal states, typically relevant to batch-style workloads (Jobs) rather than long-running services.
- ⚠️ **Warning:** a pod that repeatedly crashes shortly after starting enters a `CrashLoopBackOff` status, where Kubernetes progressively increases the delay between restart attempts — this is one of the most common production troubleshooting scenarios and is covered in depth in Section 37's operational troubleshooting material.

### 35.4.4 Pods Are Usually Not Created Directly

🎯 **Interview Tip:** a frequent junior-level mistake is describing application deployment purely in terms of "creating pods." In practice, pods are almost never created directly in production; they are created indirectly by higher-level controllers — most commonly a **Deployment** (35.5) — specifically because a directly created pod has no self-healing behavior: if it crashes and its node fails, nothing recreates it. Understanding this distinction, and correctly explaining _why_ Deployments exist rather than just naming them, is a strong signal of genuine understanding versus memorized terminology.

---

## 35.5 Core Workload and Networking Objects

### 35.5.1 ReplicaSet

- **Definition:** a controller object that ensures a specified number of identical pod replicas are running at all times, continuously reconciling actual replica count toward the declared desired count (35.3.2's controller-manager reconciliation loop, applied concretely).
- **Why it exists and the problem it solves:** without it, a crashed pod (or a node failure taking a pod down with it) would simply reduce running capacity permanently until a human intervened; the ReplicaSet controller detects the discrepancy between desired and actual replica count and creates a replacement pod automatically, typically within seconds.
- 💡 **Tip:** ReplicaSets are rarely created directly either — they are typically managed automatically by a Deployment (35.5.2), which adds rolling-update capability on top.

### 35.5.2 Deployment

- **Definition:** a higher-level controller that manages ReplicaSets on behalf of the user, providing declarative updates to pods, including rolling updates and rollback.
- **Why it exists:** a bare ReplicaSet has no built-in concept of _changing_ the pod template (e.g., deploying a new image version) without manual, error-prone ReplicaSet replacement; Deployment adds a managed update strategy on top.
- **Lifecycle / workflow:** when a Deployment's pod template is updated (e.g., a new image tag/digest), the Deployment controller creates a _new_ ReplicaSet with the updated template and gradually scales it up while scaling the _old_ ReplicaSet down, according to the configured update strategy (most commonly `RollingUpdate`, with configurable `maxSurge`/`maxUnavailable` controlling how aggressively old pods are replaced), providing a zero-downtime deployment for a correctly configured, horizontally scaled application.
- **Rollback:** because the Deployment retains a revision history of prior ReplicaSets (by default, a limited number of recent revisions), rolling back to a previous version is a first-class, fast operation (`kubectl rollout undo`), rather than requiring a fresh build/redeploy — directly reinforcing the "build once, deploy many, and be able to instantly revert" principle from Section 33.12.

### 35.5.3 Command — `kubectl` Fundamentals (Applied to Deployments)

#### `kubectl apply`

- **Purpose:** declaratively creates or updates Kubernetes objects from a YAML/JSON manifest, reconciling the cluster's actual state toward what the manifest describes; the standard way to manage Kubernetes objects in production (as opposed to imperative `kubectl create`/`kubectl run` commands, generally reserved for quick ad hoc testing).
- **Syntax:** `kubectl apply -f <file-or-directory>`
- **Practical example:**
  ```bash
  kubectl apply -f deployment.yaml
  ```
  Expected output: `deployment.apps/webapp created` (or `configured` on a subsequent apply against an existing object).
- **Production usage:** in mature GitOps-style pipelines, `kubectl apply` (or an equivalent tool like Flux/Argo CD, not yet covered in this roadmap) is driven automatically from a Git repository representing the cluster's desired state as the single source of truth, rather than run manually by engineers.
- **Common errors:** `error validating data` (malformed YAML or a field not recognized by the target API version); `forbidden` (insufficient RBAC permission for the authenticated identity, connecting directly to Section 36's Kubernetes RBAC coverage).

#### `kubectl get` / `kubectl describe`

- **Purpose:** `get` lists objects (concise, table-style); `describe` shows detailed information about a single object including recent events, essential for troubleshooting.
- **Syntax:** `kubectl get pods [-n <namespace>]` / `kubectl describe pod <pod-name>`
- **Troubleshooting tip:** `kubectl describe pod` surfaces the **Events** section, which frequently contains the exact reason a pod is not starting (image pull failure connecting back to Section 34's authentication concepts, insufficient node resources, failed health checks) — this should typically be the first diagnostic command run against any pod that is not behaving as expected.

#### `kubectl logs`

- **Purpose:** retrieves the stdout/stderr stream from a specific container in a pod — directly analogous to `docker logs` (Section 33.7.2), since a pod's containers are, under the hood, still standard OCI containers running via `containerd`.
- **Syntax:** `kubectl logs <pod-name> [-c <container-name>] [-f]`

#### `kubectl rollout`

- **Purpose:** manages and inspects Deployment rollout history and status.
- **Syntax:** `kubectl rollout status deployment/<name>` / `kubectl rollout undo deployment/<name> [--to-revision=N]`
- **Production usage:** `kubectl rollout undo` is the fast, first-response tool for a bad deployment causing production issues, restoring the previous known-good ReplicaSet within seconds — a critical incident-response capability covered further in Section 37.

### 35.5.4 Service: Stable Networking for Ephemeral Pods

- **Definition:** a Service is a Kubernetes API object that provides a stable virtual IP address and DNS name for a logical set of pods (selected by a label selector), automatically load-balancing traffic across whichever pods currently match that selector, regardless of how often those pods are individually created or destroyed.
- **Why it exists — the problem it solves:** pods are inherently ephemeral; a Deployment's rolling update replaces pods (and therefore their individual IP addresses) constantly. Without a stable abstraction in front of them, every client would need to track a constantly changing set of pod IPs directly, which is entirely impractical at scale. A Service solves this exactly the way a Load Balancer solves the equivalent problem for VMs (Section 24's concepts apply directly, one layer down inside the cluster).
- **Service types (introduced here, expanded fully in Section 36):**
  - `ClusterIP` (default): an internal-only virtual IP, reachable only from within the cluster — used for internal service-to-service communication.
  - `NodePort`: exposes the service on a static port on every node's IP, a lower-level mechanism rarely used directly in production Azure architectures in favor of...
  - `LoadBalancer`: provisions an external Azure Load Balancer (Section 24) automatically, giving the service a public (or internal, with annotation) IP address reachable from outside the cluster — the most common way to expose a service directly in AKS, and the clearest example of AKS's Azure-native integration: creating a Kubernetes Service of type `LoadBalancer` triggers Azure to provision an actual Azure Load Balancer resource behind the scenes.
- 🔑 **Key Takeaway:** the relationship between a Kubernetes Service and Azure's own Load Balancer/networking resources is a direct, concrete example of "Azure-native integration" — Kubernetes' own abstraction (Service) triggers the creation of a real Azure resource (Load Balancer) automatically, without the user manually provisioning it through the Azure Portal or CLI as would be required for a VM-based workload (Section 24).

### 35.5.5 Namespaces (Kubernetes Namespaces — Distinct from Linux Kernel Namespaces)

⚠️ **Warning:** do not confuse this concept with the Linux **kernel** namespaces from Section 33.4.4 (pid, net, mnt, etc.) — they share a name but are entirely unrelated concepts at different layers.

- **Definition:** a Kubernetes namespace is a logical partition within a single cluster, used to divide cluster resources between multiple teams, environments, or applications, providing a scope for object names (two objects can share a name if they are in different namespaces) and a scope for RBAC policy application (Section 36).
- **Why it exists:** a single AKS cluster is frequently shared across multiple teams or applications for cost and operational efficiency; namespaces provide a lightweight isolation boundary (logical, not a hard security boundary equivalent to separate clusters) for organizing and securing that shared cluster.
- **Common default namespaces:** `default` (used when no namespace is specified — a common source of confusion when objects seem to "disappear" because they were actually created in `default` rather than an intended namespace), `kube-system` (control-plane-adjacent and Azure-managed system components running on the node side, such as `kube-proxy` and certain AKS add-ons), `kube-public`.

---

## 35.6 Scheduling and Self-Healing in Depth

### 35.6.1 How Scheduling Decisions Are Made

The `kube-scheduler` (35.3.2) evaluates each unscheduled pod against every candidate node using a two-phase process:

1. **Filtering:** eliminates nodes that cannot satisfy the pod's requirements — insufficient available CPU/memory relative to the pod's declared resource `requests` (Section 33.7.3's cgroup concept, now expressed as a Kubernetes API field), node taints the pod does not tolerate, node selector/affinity rules that exclude the node, and so on.
2. **Scoring:** ranks the remaining candidate nodes by a set of scoring functions (e.g., preferring nodes with more available resources, spreading pods of the same Deployment across nodes/zones for resilience) and selects the highest-scoring node.

### 35.6.2 Self-Healing Mechanisms

| Failure Scenario                           | Kubernetes Response                                                                                                                                                                                                     |
| ------------------------------------------ | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A container inside a pod crashes           | `kubelet` on that node restarts the container in place, according to the pod's `restartPolicy` (commonly `Always` for long-running services).                                                                           |
| A pod fails health checks (liveness probe) | `kubelet` restarts the container, following the same in-place restart mechanism.                                                                                                                                        |
| An entire node becomes unresponsive        | The Node controller (part of `kube-controller-manager`) marks the node as unhealthy after a timeout; pods on that node are eventually evicted and rescheduled onto healthy nodes by their owning ReplicaSet/Deployment. |
| A pod is manually or accidentally deleted  | If owned by a ReplicaSet/Deployment, a replacement pod is created immediately to restore the desired replica count; a standalone pod (35.4.4) is not replaced.                                                          |

### 35.6.3 Health Probes (Liveness, Readiness, Startup)

- **Liveness probe:** periodically checks whether a container is still functioning correctly; a failing liveness probe causes `kubelet` to restart the container — this is the Kubernetes-native mechanism that supersedes the Dockerfile-level `HEALTHCHECK` instruction (Section 33.6.2) for orchestrated workloads, as noted in Section 33.
- **Readiness probe:** determines whether a container is ready to receive traffic; a pod failing its readiness probe is removed from a Service's load-balancing pool (35.5.4) without being restarted — critical during startup (an application still initializing should not receive traffic yet) and during transient issues (a temporarily overloaded pod can be pulled from rotation without a disruptive restart).
- **Startup probe:** allows extra time for slow-starting applications before liveness/readiness probing begins, preventing a legitimately slow-starting application from being killed by an impatient liveness probe before it has finished initializing.
- ⚠️ **Warning:** a very common production misconfiguration is setting an aggressive liveness probe on a slow-starting application without a startup probe, causing Kubernetes to repeatedly kill and restart the container before it ever finishes starting — manifesting as a persistent `CrashLoopBackOff` that is actually a probe misconfiguration, not an application bug. This is a frequent real-world troubleshooting scenario expanded further in Section 37.

---

## 35.7 AKS Cluster Creation — Hands-On Orientation

### 35.7.1 Command — `az aks create`

- **Purpose:** provisions a new AKS cluster, including its managed control plane and an initial node pool.
- **Syntax (representative, non-exhaustive):**
  ```bash
  az aks create \
    --resource-group myResourceGroup \
    --name myAKSCluster \
    --node-count 3 \
    --node-vm-size Standard_D4s_v5 \
    --attach-acr myregistry \
    --enable-managed-identity \
    --generate-ssh-keys
  ```
- **Key arguments explained individually:**
  - `--node-count` — the initial number of nodes in the default (system) node pool; production clusters typically add additional user node pools afterward (Section 36/37) rather than running all workloads on the system pool alone.
  - `--node-vm-size` — the Azure VM size (Section 11.3 concepts) for nodes in this pool; sizing should account for the per-node resource reservation for system components mentioned in 35.3.5.
  - `--attach-acr` — wires up the cluster's kubelet Managed Identity with the `AcrPull` role on the named registry, directly applying Section 34.4.2's recommended authentication pattern at cluster creation time.
  - `--enable-managed-identity` — uses a Managed Identity (Section 9) for the cluster's own control-plane-to-Azure-resource interactions (e.g., managing the Load Balancer, managed disks) instead of the older, now-discouraged Service Principal-based cluster identity model.
- **Common errors:** insufficient regional VM quota for the requested size/count (Section 11 quota concepts apply); RBAC permission errors if the deploying identity lacks `Contributor`-equivalent rights on the target resource group.
- **Production/enterprise usage:** in practice, production clusters are essentially never created via a single ad hoc CLI command; they are defined via Infrastructure as Code (Bicep or Terraform, Sections 44–45) as part of a repeatable, version-controlled provisioning pipeline, with the CLI command shown here serving as the conceptual equivalent for learning purposes.

### 35.7.2 The Resulting Resource Footprint

⚠️ **Warning:** AKS creates **two** resource groups: the one the user specifies (containing the AKS resource itself, a management-plane object) and an automatically generated, Azure-managed **node resource group** (by default named `MC_<resource-group>_<cluster-name>_<region>`) containing the actual node VMs, VM Scale Set, managed disks, Load Balancer, and other infrastructure resources the cluster depends on. Manually modifying or deleting resources inside the managed node resource group outside of Kubernetes-native or `az aks`-driven operations is strongly discouraged and can break the cluster in ways that are difficult to diagnose, since the managed node resource group's contents are expected to be fully owned and reconciled by the AKS control plane, not manually administered like an ordinary resource group.

---

## 35.8 Production and Enterprise Usage Considerations (Architecture-Level)

- **Multiple node pools:** production clusters typically separate the **system node pool** (running only Azure/Kubernetes system components, tainted to prevent application pods from being scheduled there) from one or more **user node pools** (running actual application workloads, potentially with different VM sizes/specializations, such as a GPU-enabled pool for ML workloads) — a pattern expanded fully in Section 36.
- **Multi-cluster vs. single large cluster:** enterprises face a genuine architectural trade-off between fewer, larger shared clusters (simpler to operate, better bin-packing efficiency, but a larger blast radius for cluster-wide issues and weaker isolation between tenants) versus many smaller, team- or environment-dedicated clusters (stronger isolation, smaller blast radius, but higher operational overhead multiplied by cluster count). This is a genuine trade-off without a universally correct answer, and should be presented as such — the right choice depends on organizational structure, isolation/compliance requirements, and platform team capacity.
- **Region and availability zone strategy:** control plane availability across zones is handled by Azure on qualifying configurations (35.3.3); node pool zone spreading is a customer configuration choice made at node pool creation, directly reusing Section 3's Availability Zone concepts.

---

## 35.9 Troubleshooting Reference (Architecture-Level Issues)

| Symptom                                                    | Likely Cause                                                                                                                                                                                                 | Diagnostic Step                                                                                                        |
| ---------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------------------------------------------------------------------------------- |
| Pod stuck in `Pending`                                     | Insufficient schedulable resources cluster-wide, or an unsatisfiable scheduling constraint (taint/toleration, affinity rule)                                                                                 | `kubectl describe pod` → check the Events section for a scheduler-reported reason                                      |
| Pod stuck in `ImagePullBackOff`                            | Registry authentication failure (Section 34.4), incorrect image reference, or network path to the registry blocked (e.g., Private Link misconfiguration, Section 34.8)                                       | `kubectl describe pod` Events; verify `az aks check-acr`, verify the image reference and tag/digest exist in ACR       |
| Pod in `CrashLoopBackOff`                                  | Application crashing on startup, or a misconfigured liveness probe killing it before it finishes starting (35.6.3)                                                                                           | `kubectl logs <pod> --previous` (logs from the prior, crashed instance); review probe configuration and startup timing |
| Cannot reach the application via its Service's external IP | `LoadBalancer` provisioning delay, NSG blocking traffic at the underlying Azure Load Balancer/subnet level (Section 22 concepts), or a readiness probe failing so no pods are in the Service's endpoint pool | `kubectl get svc`, `kubectl get endpoints`, verify readiness probe status via `kubectl describe pod`                   |
| Node shows `NotReady`                                      | Node-level resource exhaustion, `kubelet` failure, or an underlying Azure VM/VMSS instance issue                                                                                                             | `kubectl describe node`; check Azure VMSS instance health for the underlying node pool                                 |

---

## 35.10 Best Practices Checklist

- [ ] Applications deployed via Deployments (or other appropriate controllers), never bare pods, for self-healing.
- [ ] Resource `requests`/`limits` set on every container, informing scheduling and preventing noisy-neighbor resource contention.
- [ ] Liveness, readiness, and (for slow-starting applications) startup probes correctly configured and tuned to actual application startup behavior.
- [ ] System and user workloads separated into distinct node pools.
- [ ] Cluster provisioned via Infrastructure as Code, not ad hoc CLI commands, for production environments.
- [ ] Managed identity (not legacy Service Principal) used for the cluster's own Azure resource interactions, with `--attach-acr` (or equivalent) for registry access.
- [ ] Node resource group treated as Azure-managed and not manually modified outside Kubernetes-native or `az aks` operations.

---

## 35.11 Common Misconceptions

- "AKS clusters run Docker." _Correction:_ as established in Section 33.2.4 and reaffirmed in 35.3.4, AKS nodes run `containerd` directly via the CRI; there is no `dockerd` on the node.
- "The AKS control plane is a VM I can see and manage in my resource group." _Correction:_ the control plane is fully Azure-managed and invisible to the customer; only node pool VMs (in the separate, Azure-managed node resource group, 35.7.2) are customer-visible infrastructure.
- "A Kubernetes namespace provides strong security isolation equivalent to a separate cluster." _Correction:_ a namespace is a logical partition and RBAC/policy scope, not a hard multi-tenancy security boundary; workloads with strict isolation requirements may need separate clusters or additional controls (network policies, Section 36) rather than relying on namespace separation alone.

---

## 35.12 Interview Questions (Consolidated)

**Beginner:** "What is the difference between a Pod, a ReplicaSet, and a Deployment?"
_Model answer:_ a Pod is the smallest deployable unit — one or more co-located containers. A ReplicaSet ensures a specified number of identical pod replicas are running, replacing any that fail. A Deployment manages ReplicaSets on top of that, adding declarative rolling updates and rollback — in practice, applications are almost always deployed via Deployments, which create and manage ReplicaSets automatically, which in turn create and manage the actual pods.

**Intermediate:** "Explain what happens, step by step, when you update the image tag in a Deployment's pod template and apply the change."
_Model answer:_ the Deployment controller detects the pod template change and creates a new ReplicaSet reflecting the new template, while the old ReplicaSet remains. Following the configured `RollingUpdate` strategy (governed by `maxSurge`/`maxUnavailable`), the controller gradually scales the new ReplicaSet up and the old one down, with the scheduler placing new pods (which must first have their images pulled, per Section 34) on available nodes and readiness probes gating when new pods start receiving traffic through the Service. The old ReplicaSet is retained (scaled to zero) as part of the revision history, enabling fast rollback via `kubectl rollout undo` if needed.

**Senior:** "A team asks whether their AKS control plane is highly available across zones. How do you answer, and what is and isn't within their control?"
_Model answer:_ control plane HA (multiple `etcd`/API server replicas, spread across availability zones on qualifying regions/tiers) is managed entirely by Azure and is not something the customer configures or is responsible for directly — it is a property of the AKS service tier and region selected. What _is_ within the customer's control is node pool-level zone spreading (configured at node pool creation, applying Section 3's AZ concepts) and application-level resilience (adequate replica count spread across those zones via pod anti-affinity, covered in Section 36) — control plane HA and workload HA are separate concerns with separate ownership, and a thorough answer should distinguish them explicitly rather than conflating "is my cluster HA" into one undifferentiated question.
_What the interviewer is probing:_ whether the candidate correctly separates Azure-managed responsibility from customer responsibility — a recurring theme across every Azure managed service, and a frequent source of confused or overconfident answers from less experienced candidates.

**Architect / Scenario:** "Your organization is deciding between one large shared AKS cluster for all teams versus a cluster per team. What factors would you weigh, and what would you actually recommend needing more information about?"
_Model answer:_ factors include: blast radius (a cluster-wide issue such as a bad admission-controller policy or control-plane version bug affects every team on a shared cluster, versus being contained to one team on a per-team model); isolation and compliance requirements (regulated workloads may require hard isolation beyond what namespaces provide, 35.11); operational overhead (each additional cluster multiplies patching, upgrade, and monitoring effort, expanded in Section 37); cost efficiency (a shared cluster generally achieves better bin-packing/utilization than many small, individually right-sized clusters); and organizational maturity (a strong platform team with mature namespace-level RBAC, network policy, and resource quota practices can safely operate a larger shared cluster than a less mature organization). Rather than asserting a universal recommendation, the strongest answer states this is a genuine trade-off and identifies the specific missing information needed to decide for this organization — team count and growth trajectory, actual isolation/compliance requirements, and current platform team capacity — before committing to either model.
_What the interviewer is probing:_ whether the candidate can reason about a genuinely open architectural trade-off with no single correct answer, rather than reciting a memorized "best practice," and whether they know what additional information would actually change the recommendation.

---

## 35.13 Key Takeaways Summary

🔑 AKS is standard, upstream-conformant Kubernetes with Azure fully managing the control plane (`kube-apiserver`, `etcd`, scheduler, controller-manager) — the customer sees and manages only node pool VMs, in a separate Azure-managed node resource group.

🔑 Pods are the smallest deployable unit but are almost never created directly in production; Deployments (managing ReplicaSets) provide the self-healing and rolling-update capability that makes production use practical.

🔑 A Kubernetes Service provides a stable virtual IP/DNS abstraction over ephemeral pods, and a `LoadBalancer`-type Service directly triggers Azure to provision a real Azure Load Balancer resource — a concrete example of AKS's Azure-native integration model.

🔑 Liveness, readiness, and startup probes are the Kubernetes-native mechanism superseding Dockerfile `HEALTHCHECK` for orchestrated workloads, and their misconfiguration is one of the most common real-world sources of `CrashLoopBackOff` incidents.

🔑 AKS nodes run `containerd` directly, not Docker Engine — a direct continuation of the fact established in Section 33.2.4.

---

## 35.14 Related Concepts and What Comes Next

- **Section 36 — AKS Networking, Scaling, and Security:** builds directly on this section's Service/node/scheduling foundation to cover Azure CNI vs. kubenet networking models, Ingress, Horizontal Pod Autoscaler and Cluster Autoscaler, Kubernetes RBAC, Network Policies, and pod security hardening (extending Section 33.9's Docker-level security fundamentals to the orchestrated context).
- **Section 37 — AKS Production Operations:** cluster and node image upgrades, node pool management, backup/DR considerations for stateful workloads, and operational runbooks.
- **Section 34 (prerequisite, completed):** the ACR authentication model this section's `--attach-acr` and image-pull troubleshooting content builds on directly.
- **Section 11–12 (prerequisite, completed):** Azure VM and VM Scale Set concepts underlying node pool architecture (35.3.5, 35.7).

---

_End of Section 35. Next: Section 36 — AKS Networking, Scaling, and Security._
