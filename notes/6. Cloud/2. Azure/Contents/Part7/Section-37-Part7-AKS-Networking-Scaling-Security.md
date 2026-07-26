# Section 37 — AKS Networking, Scaling, and Security

**Part 7: Containers & Orchestration | Section 37 of 70**
**Prerequisites:** Section 36 (AKS Architecture), Section 21–24 (VNet, NSGs, Load Balancer/Application Gateway), Section 8 (RBAC), Section 34.9 (Container Security Fundamentals)
**Leads into:** Section 38 (AKS Production Operations)

---

## 1. Introduction and Scope

Section 36 established AKS's control plane/node architecture and core objects (pods, Deployments, Services). This section covers three deep, interconnected operational domains: **networking** (how pods get IP addresses and how traffic reaches them from outside the cluster), **scaling** (how the cluster and its workloads grow and shrink automatically), and **security** (Kubernetes RBAC, pod-level hardening, and network isolation within the cluster). All three build directly on Azure networking (Part 5) and identity (Part 2) concepts already covered.

---

## 2. AKS Networking Models

### 2.1 Definition

An AKS **network plugin** determines how pod IP addressing and routing work inside the cluster and how that addressing relates to the underlying Azure Virtual Network (Section 21). AKS supports several models; the two most significant to understand deeply are **kubenet** and **Azure CNI** (Container Networking Interface), plus the newer **Azure CNI Overlay** and **Azure CNI powered by Cilium** variants.

### 2.2 Why Multiple Models Exist — The Problem Being Solved

Kubernetes itself only specifies that every pod must get its own IP address and that pods must be able to reach each other by that IP without NAT — it does not mandate _how_ that addressing is implemented. Different implementations make different trade-offs between **VNet IP address consumption**, **networking performance**, and **feature richness** (such as direct Network Policy and Private Link integration). AKS exposes this choice because no single trade-off point is correct for every cluster size and network architecture.

### 2.3 kubenet (Basic Networking)

- **How it works:** nodes get an actual IP address from the Azure VNet subnet (Section 21), but **pods** get IP addresses from a separate, logically distinct address space that exists only inside each node, not allocated from the VNet subnet itself. Traffic from a pod to a destination outside its node is routed via User Defined Routes (Section 22's route table concepts) that AKS manages automatically, translating between the pod's node-local address and the node's actual VNet IP.
- **Advantage:** conserves VNet IP address space significantly, since only nodes (not every pod) consume an address from the subnet — historically important in VNets with limited available address space.
- **Limitations:** lower performance due to the additional routing/NAT hop; does not support several advanced features including Azure Network Policies and Windows node pools; Microsoft's guidance (verify current status, as this has evolved) has moved toward deprecating kubenet in favor of Azure CNI Overlay for new clusters, since Overlay achieves kubenet's core IP-conservation benefit without its limitations.

### 2.4 Azure CNI (Traditional / "Flat" Model)

- **How it works:** every pod receives an actual, routable IP address directly from the Azure VNet subnet, exactly as if it were its own small VM. Pods are therefore fully addressable from anywhere else in the VNet (and peered VNets, Section 23) without any NAT translation.
- **Advantage:** best networking performance (no extra NAT hop), full compatibility with all AKS networking features (Network Policies, Windows node pools, Virtual Nodes), and pods are directly visible/reachable at the VNet level, simplifying integration with other VNet-resident resources (e.g., a VM directly calling a pod's IP, or Azure Firewall/NSG rules operating on real pod IPs).
- **Limitation — the core trade-off:** IP address consumption is substantial. Every node must be provisioned with enough subnet address space reserved for its _maximum possible_ pod count (a configurable `--max-pods` setting, defaulting to 30 for Azure CNI historically — verify current default against documentation), meaning the subnet must be sized generously up front; running out of subnet address space is a common real-world planning failure with traditional Azure CNI, since it cannot be resolved without re-architecting the subnet, unlike a simple in-place scaling knob.
- ⚠️ **Warning:** IP exhaustion in a traditional Azure CNI subnet is one of the most consequential AKS planning mistakes because subnet resizing after the fact is disruptive; capacity planning (max node count × max pods per node, plus headroom for upgrades which temporarily run extra nodes, Section 38) must happen at initial VNet/subnet design time (Section 21), not discovered reactively.

### 2.5 Azure CNI Overlay (Modern, Recommended Default for New Clusters)

- **How it works:** combines Azure CNI's routing efficiency and feature compatibility with kubenet's IP-conservation benefit: nodes get real VNet IPs, but pods get IP addresses from a separate, private CIDR range that exists only within the Kubernetes overlay network — not consumed from the VNet subnet at all — while still supporting Network Policies and other advanced features that traditional kubenet could not.
- **Why this is now generally the recommended default:** it resolves the IP-exhaustion planning burden of traditional Azure CNI (37.2.4) without kubenet's feature limitations (37.2.3), making capacity planning materially simpler for most new clusters.
- ⚠️ **Warning:** as with all specific product/feature-default claims, verify the current Microsoft-recommended default and exact feature-parity details against up-to-date official documentation, since AKS networking capabilities and recommendations continue to evolve.

### 2.6 Comparison Table

| Aspect                               | kubenet                                   | Azure CNI (traditional)                                               | Azure CNI Overlay                                                       |
| ------------------------------------ | ----------------------------------------- | --------------------------------------------------------------------- | ----------------------------------------------------------------------- |
| Pod IP source                        | Node-local, NAT'd                         | Real VNet subnet address                                              | Private overlay CIDR (not VNet subnet)                                  |
| VNet IP consumption                  | Low (nodes only)                          | High (every pod)                                                      | Low (nodes only)                                                        |
| Performance                          | Lower (extra NAT hop)                     | Highest                                                               | High                                                                    |
| Network Policy support               | No                                        | Yes                                                                   | Yes                                                                     |
| Windows node pool support            | No                                        | Yes                                                                   | Yes                                                                     |
| Direct VNet-level pod addressability | No                                        | Yes                                                                   | No (pods reachable via cluster networking, not directly as a VNet peer) |
| Typical fit                          | Legacy/small clusters, largely superseded | Workloads specifically requiring direct VNet-level pod addressability | Most new clusters — best balance of IP efficiency and feature support   |

🎯 **Interview Tip:** the strongest answer to "which networking model would you choose?" is not a single memorized default, but an explanation of the underlying trade-off (IP consumption vs. direct VNet addressability/performance) and which specific requirement of the workload drives the choice — e.g., "if another VNet-resident system needs to reach individual pods directly by IP without going through a Service, traditional Azure CNI's flat addressability is required; otherwise Overlay's IP efficiency is usually preferable for a new cluster."

---

## 3. Ingress: Routing External HTTP(S) Traffic

### 3.1 Definition

An **Ingress** is a Kubernetes API object that describes rules for routing external HTTP/HTTPS traffic to internal Services based on hostname and URL path, requiring an **Ingress Controller** (a running component that actually implements the routing, since Ingress is only a specification, not a functioning proxy by itself) to have any effect.

### 3.2 Why It Exists Beyond a Plain `LoadBalancer` Service

A `LoadBalancer`-type Service (Section 36.5.4) provisions one Azure Load Balancer per Service, operating at the network/transport layer (L4) — it has no awareness of HTTP hostnames or URL paths, and provisioning a separate public IP and Load Balancer per application is both costly and operationally unwieldy at scale. Ingress solves this by allowing a **single** entry point (one Load Balancer or Application Gateway, one public IP) to route to _many_ backend Services based on Layer 7 (HTTP) rules — directly parallel to the Load Balancer vs. Application Gateway distinction already covered in Section 24, now applied inside the cluster.

### 3.3 Ingress Controller Options on AKS

| Option                                                              | Description                                                                                                                                                                                                                           |
| ------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Application Gateway Ingress Controller (AGIC)**                   | Uses an actual Azure Application Gateway (Section 24) as the Ingress implementation, giving native integration with Application Gateway's Web Application Firewall (WAF) capability (Section 59) and Azure-native management.         |
| **NGINX Ingress Controller (open-source, self-managed in-cluster)** | Runs as pods inside the cluster; widely used across the broader Kubernetes ecosystem (not Azure-specific), offering flexibility and portability at the cost of the customer managing the controller's own lifecycle/scaling/upgrades. |
| **Other CNCF-ecosystem controllers (e.g., Traefik, HAProxy-based)** | Exist and are usable on AKS like any standard Kubernetes cluster, since Ingress is a portable Kubernetes API concept, not an AKS-specific one.                                                                                        |

💡 **Tip:** the choice mirrors the Section 24 Load Balancer vs. Application Gateway trade-off one layer up: AGIC provides tighter Azure-native integration (especially WAF) at the cost of being Azure-specific, while NGINX/other open-source controllers provide portability across any Kubernetes environment (useful for organizations pursuing multi-cloud or hybrid consistency) at the cost of self-managing the controller.

### 3.4 Example Ingress Manifest

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: webapp-ingress
  annotations:
    kubernetes.io/ingress.class: azure/application-gateway
spec:
  rules:
    - host: app.example.com
      http:
        paths:
          - path: /api
            pathType: Prefix
            backend:
              service:
                name: api-service
                port:
                  number: 80
          - path: /
            pathType: Prefix
            backend:
              service:
                name: frontend-service
                port:
                  number: 80
```

- A single hostname (`app.example.com`) routes different URL paths to entirely different backend Services — the core L7 routing capability that a plain L4 `LoadBalancer` Service cannot express.

---

## 4. Scaling: Horizontal Pod Autoscaler and Cluster Autoscaler

### 4.1 The Two Independent Scaling Layers

AKS scaling operates at two genuinely independent layers that are frequently confused in interviews and in real troubleshooting:

1. **Pod-level scaling (Horizontal Pod Autoscaler, HPA):** changes the _number of pod replicas_ for a Deployment, within the currently available node capacity.
2. **Node-level scaling (Cluster Autoscaler):** changes the _number of nodes_ in a node pool, in response to pods that cannot be scheduled due to insufficient cluster-wide resource capacity.

🔑 **Key Takeaway:** these two layers must work together to actually scale a workload beyond current node capacity — HPA alone cannot create nodes, and Cluster Autoscaler alone does not decide how many pod replicas an application needs. A common real-world failure mode is HPA correctly deciding to add replicas, but those new pods remaining stuck in `Pending` (Section 36.9) because Cluster Autoscaler has not yet (or cannot) add capacity — understanding this two-layer relationship is essential for diagnosing scaling issues correctly.

### 4.2 Horizontal Pod Autoscaler (HPA)

- **Definition:** a Kubernetes controller that automatically adjusts the number of pod replicas in a Deployment (or ReplicaSet/StatefulSet) based on observed metrics, most commonly CPU or memory utilization relative to the pods' declared resource `requests` (Section 34.7.3/35.6.1), or custom/external metrics (e.g., queue depth from Azure Service Bus, request rate from a metrics adapter).
- **How it works:** the HPA controller periodically compares the current average metric value across all pods in the target Deployment against a configured target value, and computes a new desired replica count proportionally, then updates the Deployment's replica count — which in turn drives the standard ReplicaSet/scheduler mechanics from Section 36.
- **Example manifest:**
  ```yaml
  apiVersion: autoscaling/v2
  kind: HorizontalPodAutoscaler
  metadata:
    name: webapp-hpa
  spec:
    scaleTargetRef:
      apiVersion: apps/v1
      kind: Deployment
      name: webapp
    minReplicas: 3
    maxReplicas: 20
    metrics:
      - type: Resource
        resource:
          name: cpu
          target:
            type: Utilization
            averageUtilization: 70
  ```
- **Common mistake:** setting an HPA target without having set resource `requests` on the pod's containers — CPU/memory utilization percentage is calculated relative to the declared `requests` value, so an HPA on CPU utilization with no CPU `request` set has no meaningful baseline to scale against and behaves unpredictably or not at all.

### 4.3 Cluster Autoscaler

- **Definition:** a component that automatically adjusts the number of **nodes** in a node pool, adding nodes when pods cannot be scheduled due to insufficient resources (respecting the node pool's configured minimum/maximum node count), and removing underutilized nodes (after safely draining and rescheduling their pods elsewhere) when capacity is no longer needed.
- **Why it exists:** without it, node count is a static, manually managed number, forcing a choice between over-provisioning (paying for unused capacity most of the time) and under-provisioning (workloads unable to scale during demand spikes, remaining `Pending` indefinitely).
- **Configuration:** enabled per node pool with `--enable-cluster-autoscaler --min-count <n> --max-count <n>`; multiple node pools can each have independent autoscaler bounds, supporting patterns such as a baseline always-on system node pool alongside a scale-to-near-zero user node pool for bursty workloads.
- ⚠️ **Warning:** Cluster Autoscaler node removal respects **Pod Disruption Budgets** (37.4.4) and will not remove a node if doing so would violate one — a frequent source of confusion when an expected scale-down does not happen, and worth checking early in that troubleshooting scenario.

### 4.4 Pod Disruption Budgets (PDB)

- **Definition:** a policy specifying the minimum number (or percentage) of pods in a Deployment that must remain available during _voluntary_ disruptions — node drains for scaling, upgrades (Section 38), or maintenance — as distinct from _involuntary_ disruptions (a node crashing unexpectedly), which a PDB cannot prevent.
- **Why it exists:** without a PDB, a node drain during a scale-down or upgrade operation could evict every replica of a Deployment simultaneously if they happen to be co-located, causing a brief but real outage even though the application is nominally "highly available" with multiple replicas.
- **Example:**
  ```yaml
  apiVersion: policy/v1
  kind: PodDisruptionBudget
  metadata:
    name: webapp-pdb
  spec:
    minAvailable: 2
    selector:
      matchLabels:
        app: webapp
  ```

### 4.5 Node Autoprovisioning / Virtual Nodes (Brief Orientation)

- **Virtual Nodes (ACI integration):** AKS supports scheduling certain pods onto Azure Container Instances (Section 15) via the Virtual Kubelet pattern, providing near-instantaneous "burst" capacity without waiting for an actual VM node to provision — useful for handling short, unpredictable spikes beyond what Cluster Autoscaler's VM-provisioning latency can respond to quickly enough.
- ⚠️ **Warning:** availability, exact feature name, and current support status for Virtual Nodes should be verified against current Microsoft documentation, as this capability's status has evolved over AKS's product history.

---

## 5. Kubernetes RBAC (Distinct from Azure RBAC)

### 5.1 Definition and Why Two RBAC Systems Exist

⚠️ **Warning:** AKS involves **two separate, layered RBAC systems** that are a very common source of confusion:

1. **Azure RBAC (Section 8):** controls access to the **AKS resource itself** at the Azure control-plane level — who can create/delete/modify the AKS cluster resource, scale node pools via the Azure API, retrieve cluster credentials, and so on.
2. **Kubernetes RBAC:** controls access to **objects inside the cluster** via the Kubernetes API — who can create pods, read secrets, modify deployments in a specific namespace, and so on. This is enforced entirely by `kube-apiserver` (Section 36.3.2) and is conceptually and mechanically distinct from Azure RBAC.

🔑 **Key Takeaway:** an identity can have full Azure `Contributor` rights on the AKS resource (able to delete the entire cluster) while having zero Kubernetes RBAC permissions inside it (unable to list a single pod), and vice versa — the two systems must both be understood and configured; assuming one implies anything about the other is a common and consequential misconception.

### 5.2 Azure RBAC Integration for Kubernetes Authorization (Optional Unification)

AKS supports an integration mode ("Azure RBAC for Kubernetes Authorization") where Kubernetes-level permissions can be granted _through_ Azure RBAC role assignments (using AKS-specific built-in roles such as `Azure Kubernetes Service RBAC Reader`/`Writer`/`Admin`) instead of maintaining a fully separate Kubernetes RBAC configuration — reducing (but per 37.5.1's warning, not eliminating the conceptual distinction of) the two-system complexity for organizations that prefer centralizing all access control in Azure RBAC/Entra ID.

### 5.3 Kubernetes RBAC Objects

| Object               | Scope            | Purpose                                                                                                                                                                                                                                   |
| -------------------- | ---------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Role`               | Namespace-scoped | Defines a set of permissions (verbs like `get`, `list`, `create`, `delete` on resource types like `pods`, `secrets`) within one namespace.                                                                                                |
| `ClusterRole`        | Cluster-wide     | Same as `Role` but applies cluster-wide, or is referenced by a namespace-scoped binding to grant a reusable permission set.                                                                                                               |
| `RoleBinding`        | Namespace-scoped | Grants a `Role` (or `ClusterRole`) to a specific user, group, or service account within one namespace.                                                                                                                                    |
| `ClusterRoleBinding` | Cluster-wide     | Grants a `ClusterRole` cluster-wide.                                                                                                                                                                                                      |
| `ServiceAccount`     | Namespace-scoped | An identity for processes running _inside_ the cluster (e.g., a pod needing to call the Kubernetes API itself) — distinct from a human user identity, and distinct from an Azure Managed Identity, though the two can be linked (37.5.4). |

### 5.4 Workload Identity (Linking Kubernetes ServiceAccounts to Azure Managed Identities)

- **Definition:** **Azure AD Workload Identity** (the modern, federation-based successor to the older "AAD Pod Identity" project) allows a pod, via its Kubernetes `ServiceAccount`, to obtain Entra ID tokens for calling Azure services (e.g., pulling secrets from Key Vault, Section 56) without any credential stored in the cluster — extending the Managed Identity pattern established in Section 9 and applied to registry authentication in Section 35.4.2, now applied to _any_ Azure service a pod needs to call, not just ACR.
- **Why it matters:** before this pattern existed, applications running in AKS needing to call other Azure services typically had to store a Service Principal credential as a Kubernetes Secret — a long-lived credential at rest inside the cluster, and exactly the anti-pattern flagged in Section 35.9.4's interview answer about registry authentication, now generalized to all Azure service access from within pods.

---

## 6. Pod-Level Security Hardening

### 6.1 Extending Section 34.9's Docker Security Fundamentals to Kubernetes

Section 34.9 established Docker-level container hardening principles (non-root, capability dropping, read-only filesystem, minimal base images). Kubernetes exposes these same underlying mechanisms through the pod specification's **`securityContext`** field, plus additional cluster-level admission controls that did not exist at the plain Docker level.

### 6.2 Pod/Container `securityContext`

```yaml
apiVersion: v1
kind: Pod
metadata:
  name: webapp
spec:
  securityContext:
    runAsNonRoot: true
    runAsUser: 1000
    fsGroup: 2000
  containers:
    - name: webapp
      image: myregistry.azurecr.io/webapp:1.0
      securityContext:
        allowPrivilegeEscalation: false
        readOnlyRootFilesystem: true
        capabilities:
          drop: ["ALL"]
```

- `runAsNonRoot: true` — instructs Kubernetes to refuse to start the container if its image would run as root, directly enforcing the Section 34.6.2/33.9 non-root guidance as a cluster-enforced policy rather than a Dockerfile-only convention that could be silently bypassed by a mismatched image.
- `readOnlyRootFilesystem: true` — the Kubernetes-level equivalent of Docker's `--read-only` (Section 34.9), preventing runtime writes to the container's filesystem outside explicitly mounted writable volumes.
- `capabilities.drop: ["ALL"]` — the Kubernetes-level equivalent of `--cap-drop=ALL` (Section 34.9), with specific capabilities added back only where genuinely required.
- `allowPrivilegeEscalation: false` — prevents a process from gaining more privileges than its parent process (e.g., via setuid binaries), closing a specific privilege-escalation path.

### 6.3 Pod Security Admission (Cluster-Level Enforcement)

- **Definition:** a built-in Kubernetes admission control mechanism that enforces one of three predefined security profiles (`Privileged`, `Baseline`, `Restricted`) at the namespace level, rejecting any pod that violates the assigned profile's constraints — moving hardening from "best practice a developer might forget" to "cluster-enforced policy a developer cannot bypass."
- **Why it matters architecturally:** without namespace-level enforcement, individual teams' adherence to the `securityContext` guidance in 37.6.2 depends entirely on developer discipline; Pod Security Admission provides a platform-team-controlled guardrail, directly parallel in philosophy to Azure Policy (Section 57) enforcing guardrails at the Azure resource level.

### 6.4 Network Policies

- **Definition:** a Kubernetes API object that restricts which pods can communicate with which other pods (and external endpoints), functioning as the intra-cluster equivalent of an NSG (Section 22) — but operating at the pod/label level rather than the subnet/VM level.
- **Why it exists:** by default, Kubernetes networking is fully open — any pod can reach any other pod across the entire cluster and every namespace, regardless of application boundaries; in a shared multi-team cluster (Section 36.8's shared-cluster trade-off), this default is frequently unacceptable from a security/compliance standpoint, and Network Policies provide the mechanism to restrict it.
- **Requires a compatible network plugin:** as noted in 37.2.3–37.2.5, kubenet does not support Network Policies; Azure CNI (traditional or Overlay) does, typically via either **Azure Network Policy Manager** (Azure's own implementation) or **Calico** (a widely used open-source implementation also usable on AKS), or the newer **Azure CNI powered by Cilium** dataplane, which implements Network Policy via eBPF for improved performance and additional capability.
- **Example — default-deny plus explicit allow:**
  ```yaml
  apiVersion: networking.k8s.io/v1
  kind: NetworkPolicy
  metadata:
    name: default-deny
    namespace: team-a
  spec:
    podSelector: {}
    policyTypes: ["Ingress"]
  ---
  apiVersion: networking.k8s.io/v1
  kind: NetworkPolicy
  metadata:
    name: allow-frontend-to-api
    namespace: team-a
  spec:
    podSelector:
      matchLabels:
        app: api
    policyTypes: ["Ingress"]
    ingress:
      - from:
          - podSelector:
              matchLabels:
                app: frontend
  ```
  The first policy denies all inbound traffic to every pod in `team-a` by default (an empty `podSelector` matches all pods, and no allowed `ingress` rule is specified); the second explicitly permits inbound traffic to pods labeled `app: api` only from pods labeled `app: frontend` — the standard "default-deny, then explicit allow" pattern that is widely recommended best practice for production multi-tenant clusters, directly paralleling NSG default-deny design guidance from Section 22.

### 6.5 Secrets Management

- Kubernetes `Secret` objects store sensitive data (base64-encoded, **not encrypted by default at the API object level** unless encryption at rest is separately configured — a frequently misunderstood point: base64 is an encoding, not encryption, and provides no confidentiality on its own) for consumption by pods as environment variables or mounted files.
- **Production guidance:** rather than storing sensitive values directly as Kubernetes Secrets, production architectures increasingly use the **Azure Key Vault Provider for Secrets Store CSI Driver**, which mounts secrets directly from Azure Key Vault (Section 56) into pods at runtime (often in combination with Workload Identity, 37.5.4, for the pod's authentication to Key Vault itself), avoiding persistent storage of the actual secret value inside the cluster's `etcd` at all.

---

## 7. Troubleshooting Reference (Networking, Scaling, Security)

| Symptom                                                                | Likely Cause                                                                                                                                            | Diagnostic Step                                                                                                                            |
| ---------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------ |
| New pods stuck `Pending` despite HPA scaling up                        | Cluster Autoscaler has not yet added nodes, or has hit its configured `--max-count`, or a PDB is blocking node drain needed to make room                | `kubectl describe pod` Events; `kubectl get nodes`; review Cluster Autoscaler logs and node pool min/max settings                          |
| Pods cannot reach each other across namespaces                         | A default-deny Network Policy is in effect without a corresponding allow rule for the required traffic                                                  | Review `kubectl get networkpolicy -A` and the specific pod labels/selectors involved                                                       |
| Ingress returns 502/504                                                | Backend Service has no ready pods (readiness probe failing, Section 36.6.3), or Ingress Controller misconfiguration                                     | `kubectl get endpoints <service>`; check backend pod readiness status                                                                      |
| `kubectl` commands return `Forbidden` for a specific user              | Missing Kubernetes RBAC `Role`/`RoleBinding` for that identity in the target namespace — remember this is separate from Azure RBAC (37.5.1)             | `kubectl auth can-i <verb> <resource> --as=<user>`; review `RoleBinding`/`ClusterRoleBinding` objects                                      |
| Subnet running out of available IPs in a traditional Azure CNI cluster | Node count × max-pods-per-node approaching or exceeding subnet capacity, often worsened by extra nodes temporarily added during an upgrade (Section 38) | Review subnet address space utilization; consider migrating new node pools to Azure CNI Overlay, or expanding the subnet if still possible |

---

## 8. Best Practices Checklist

- [ ] Networking model chosen deliberately based on IP-conservation vs. direct-VNet-addressability requirements, not by default.
- [ ] Subnet sized with headroom for node count × max pods per node, plus upgrade-surge capacity, if using traditional Azure CNI.
- [ ] Ingress used instead of one `LoadBalancer` Service per application, where multiple HTTP(S) applications are exposed.
- [ ] Resource `requests` set on every container before relying on HPA CPU/memory-based scaling.
- [ ] Cluster Autoscaler enabled with appropriate min/max bounds per node pool.
- [ ] Pod Disruption Budgets defined for every production Deployment with more than one replica.
- [ ] Kubernetes RBAC (and/or the Azure RBAC-for-Kubernetes integration) configured with least privilege, understood as distinct from Azure RBAC on the AKS resource itself.
- [ ] Pod `securityContext` hardening (non-root, dropped capabilities, read-only filesystem) applied, ideally enforced via Pod Security Admission at the namespace level rather than left to developer discipline alone.
- [ ] Default-deny Network Policies applied in shared/multi-tenant clusters, with explicit allow rules for required traffic.
- [ ] Sensitive values sourced from Azure Key Vault via the Secrets Store CSI Driver rather than stored directly as Kubernetes Secrets, where feasible.

---

## 9. Common Misconceptions

- "Azure RBAC controls what I can do inside the cluster." _Correction:_ Azure RBAC controls access to the AKS resource at the Azure control-plane level; Kubernetes RBAC (or the optional Azure RBAC-for-Kubernetes integration) controls access to objects inside the cluster — two distinct systems (37.5.1).
- "Kubernetes Secrets are encrypted and safe to store sensitive data in directly." _Correction:_ Secret values are base64-encoded by default, not encrypted, unless encryption at rest is separately configured; production guidance favors sourcing secrets from Key Vault at runtime instead (37.6.5).
- "HPA alone can scale a workload beyond current cluster capacity." _Correction:_ HPA only changes pod replica count within available node resources; Cluster Autoscaler must add nodes for genuinely new capacity, and the two must be understood together (37.4.1).

---

## 10. Interview Questions (Consolidated)

**Beginner:** "What is the difference between kubenet and Azure CNI?"
_Model answer:_ covered in 37.2.3–37.2.4 — summarize as: kubenet gives pods node-local, NAT'd addresses conserving VNet IP space but with lower performance and feature limitations; Azure CNI gives every pod a real, routable VNet IP for full addressability and performance at the cost of significant IP address consumption; Azure CNI Overlay (37.2.5) combines the IP efficiency of kubenet with the feature support of Azure CNI and is generally the recommended starting point for new clusters, subject to verifying current guidance.

**Intermediate:** "A team's HPA is configured correctly and shows it wants to scale to 15 replicas, but only 8 are running and the rest are Pending. What would you check?"
_Model answer:_ this is the two-layer scaling relationship from 37.4.1 — HPA has correctly decided pod count, but something is preventing the scheduler from placing the remaining pods. Check Cluster Autoscaler status and its configured `--max-count` (it may have hit its ceiling), check for a Pod Disruption Budget blocking a node drain that Cluster Autoscaler needs to perform for a scale-up-and-rebalance operation, and check `kubectl describe pod` on a Pending pod for the scheduler's specific reported reason (insufficient CPU/memory, an unsatisfiable node affinity/taint rule, or a subnet IP exhaustion issue if using traditional Azure CNI, 37.2.4).
_What the interviewer is probing:_ whether the candidate understands the HPA/Cluster Autoscaler relationship as two cooperating but independent systems, and can name concrete, checkable diagnostic steps rather than a vague "check the logs."

**Senior:** "Explain the difference between Kubernetes RBAC and Azure RBAC in the context of AKS, and describe a scenario where confusing the two would cause a real security gap."
_Model answer:_ Azure RBAC governs the AKS resource itself (who can delete the cluster, retrieve credentials, modify node pools via the Azure control plane); Kubernetes RBAC governs objects inside the cluster (who can read a Secret, create a pod, in a given namespace) and is enforced by `kube-apiserver`, entirely independent of Azure RBAC. A concrete security gap: an organization might carefully restrict Azure RBAC on the AKS resource to a small platform team, and reasonably conclude "access is locked down" — while every developer with `kubectl` credentials (obtained once, perhaps during initial onboarding) retains broad, never-reviewed Kubernetes RBAC permissions inside the cluster, including read access to Secrets across namespaces, because nobody separately audited the Kubernetes-level `RoleBinding`/`ClusterRoleBinding` objects. The fix is treating both systems as requiring independent, deliberate least-privilege configuration and periodic review, not assuming Azure-level restriction implies in-cluster restriction.
_What the interviewer is probing:_ depth of understanding that these are genuinely separate systems with separate audit obligations, illustrated with a realistic, specific failure scenario rather than an abstract statement of the distinction.

**Architect / Scenario:** "Design the networking and security posture for an AKS cluster that will host workloads for multiple internal teams with different compliance requirements, some needing network isolation from each other."
_Model answer:_ start with Azure CNI Overlay (37.2.5) for IP efficiency and full feature support, assuming no specific requirement forces traditional Azure CNI's direct VNet addressability. Use one Kubernetes namespace per team as the baseline organizational and RBAC-scoping boundary (35.5.5), backed by Kubernetes RBAC `Role`/`RoleBinding` per namespace granting only that team access to their own namespace's objects (37.5.3), and, if centralizing on Azure identity is preferred, the Azure RBAC-for-Kubernetes integration (37.5.2) instead of separately maintained Kubernetes RBAC. Apply default-deny Network Policies (37.6.4) per namespace with explicit allow rules only for legitimate cross-team traffic, achieving the requested inter-team isolation at the pod-networking level. Enforce Pod Security Admission (37.6.3) at the `Restricted` or `Baseline` profile per namespace depending on each team's actual workload needs, backed by individual pod `securityContext` hardening (37.6.2) as the underlying mechanism. Source secrets via the Key Vault CSI driver with Workload Identity (37.5.4/37.6.5) rather than native Kubernetes Secrets, particularly for teams with stricter compliance requirements. Explicitly flag that namespace-based isolation, even with Network Policies and RBAC, is _logical_ isolation (35.11) — if a specific team's compliance requirement mandates hard tenant isolation (e.g., regulatory data residency/segregation rules that a shared control plane and shared underlying nodes cannot satisfy), that requirement should be surfaced back to the organization as a potential driver for a separate dedicated cluster instead, per the trade-off discussed in Section 36.8, rather than assuming namespace-level controls are always sufficient.
_What the interviewer is probing:_ the ability to synthesize networking, RBAC, and pod security controls into a coherent multi-tenant design, while correctly recognizing the limits of logical (namespace-level) isolation and knowing when to escalate to an architectural-level trade-off (separate clusters) instead of over-relying on in-cluster controls alone.

---

## 11. Key Takeaways Summary

🔑 AKS networking model choice (kubenet, Azure CNI, Azure CNI Overlay) is a genuine trade-off between VNet IP consumption and direct pod addressability/performance/feature support — not a one-size-fits-all default.

🔑 HPA (pod-level) and Cluster Autoscaler (node-level) are two independent, cooperating scaling systems; diagnosing "why didn't scaling work" requires checking both layers.

🔑 Azure RBAC (on the AKS resource) and Kubernetes RBAC (inside the cluster) are entirely separate systems that must each be configured and audited independently — this is one of the most consequential and frequently misunderstood aspects of AKS security.

🔑 Pod-level `securityContext` hardening extends Section 34.9's Docker fundamentals into Kubernetes, and Pod Security Admission moves that hardening from developer-discretionary practice to cluster-enforced policy.

🔑 Network Policies are the intra-cluster equivalent of NSGs, require a compatible network plugin, and should follow a default-deny-then-explicit-allow pattern in shared/multi-tenant clusters — but remain logical isolation, not a substitute for separate clusters where hard tenant isolation is a genuine compliance requirement.

---

## 12. Related Concepts and What Comes Next

- **Section 38 — AKS Production Operations:** cluster/node upgrades (including how node pool surge capacity interacts with the IP-planning concerns raised in 37.2.4), node image management, backup/DR for stateful workloads, and day-2 operational runbooks — the natural continuation of this section's scaling and security foundation into ongoing operational practice.
- **Section 21–24 (prerequisite, completed):** VNet, NSG, Load Balancer, and Application Gateway concepts this section's networking and Ingress material builds on directly.
- **Section 8–9 (prerequisite, completed):** Azure RBAC and Managed Identity concepts underlying 37.5's dual-RBAC and Workload Identity material.
- **Section 56 — Key Vault (upcoming, Part 11):** full depth on the Secrets Store CSI Driver integration introduced in 37.6.5.
- **Section 57 — Azure Policy (upcoming, Part 11):** the Azure-resource-level guardrail mechanism directly parallel in philosophy to Pod Security Admission (37.6.3).

---

_End of Section 37. Next: Section 38 — AKS Production Operations._
