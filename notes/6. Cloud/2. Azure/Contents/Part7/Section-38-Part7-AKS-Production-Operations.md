# Section 38 — AKS Production Operations

**Part 7: Containers & Orchestration | Section 38 of 70 (Final Section of Part 7)**
**Prerequisites:** Section 36 (AKS Architecture), Section 37 (AKS Networking, Scaling, Security), Section 18–19 (Managed Disks, Azure Files), Section 62 (Azure Site Recovery & Backup — referenced conceptually here, taught fully in Part 12)
**Leads into:** Part 8 — Serverless & Integration (Section 40, Azure Functions deep dive)

---

## 38.1 Introduction and Scope

This final section of Part 7 covers the day-2 operational concerns of running AKS in production: cluster and node upgrades, node image management, node pool lifecycle operations, backup and disaster recovery considerations for stateful workloads, cost and capacity operations, and a consolidated operational runbook and troubleshooting reference. Where Sections 36–37 established what AKS _is_ and how it is _architected_, this section addresses how it is _operated_ over time.

🔑 **Key Takeaway:** the majority of real-world AKS incidents are operational in nature — an upgrade gone wrong, a misconfigured PDB blocking a necessary drain, an exhausted subnet during a scale event — rather than architectural design flaws. Mastery of this section's material is disproportionately valuable for production-troubleshooting and incident-response interview questions.

---

## 38.2 Kubernetes Version Upgrades

### 38.2.1 Why Upgrades Are a First-Class Operational Concern

Kubernetes follows a regular upstream release cadence, and AKS supports only a rolling window of recent minor versions (Microsoft deprecates support for older versions on an ongoing schedule — verify the exact current support window against official documentation, as it is subject to change). Falling behind the supported version window forces an eventual, potentially disruptive multi-version jump upgrade rather than a series of smaller, safer incremental ones — making proactive upgrade cadence a genuine operational discipline, not a one-time setup task.

### 38.2.2 The Two Upgrade Surfaces

As established in Section 36.3.3, AKS separates control plane and node responsibilities — and upgrades follow the same split:

1. **Control plane upgrade:** Azure upgrades the managed `kube-apiserver`/`etcd`/scheduler/controller-manager to a target Kubernetes minor/patch version. This is initiated by the customer (`az aks upgrade` or the control-plane-only upgrade option) but _performed_ by Azure on its managed infrastructure.
2. **Node pool upgrade:** each node pool's nodes must also be upgraded to a compatible Kubernetes version (node `kubelet` version cannot be newer than the control plane, and Kubernetes supports only a limited version skew between them — verify the exact supported skew against current documentation). This is a customer-configured operation, though AKS automates the mechanics.

⚠️ **Warning:** upgrading only the control plane without also upgrading node pools is a valid intermediate state supported by AKS (within the version skew policy) but is not a stopping point — node pools should be upgraded to match reasonably promptly, since running an old node `kubelet` version against a newer control plane for an extended period is not the intended long-term operating state and increases the risk of subtle incompatibilities.

### 38.2.3 Node Pool Upgrade Mechanics: Surge and Drain

- AKS performs a node pool upgrade by **provisioning new nodes** on the target Kubernetes version, **cordoning and draining** pods off old nodes onto the new ones (respecting Pod Disruption Budgets, Section 37.4.4), and then **removing the old nodes** — never upgrading a node's Kubernetes version in place.
- **Max surge:** a configurable setting (`--max-surge`) controlling how many _extra_ nodes are provisioned during the upgrade beyond the node pool's normal count, trading off upgrade speed (higher surge = more parallel node replacement = faster upgrade) against temporary additional cost and, critically, additional temporary IP address consumption in a traditional Azure CNI subnet (directly connecting back to Section 37.2.4's IP-exhaustion warning — upgrade surge capacity must be included in subnet capacity planning, not just steady-state node/pod count).
- **Drain and PDB interaction:** if a PDB (Section 37.4.4) would be violated by draining a given node's pods, the drain operation for that node pauses until the PDB constraint can be satisfied (e.g., other replicas becoming healthy on already-upgraded nodes) — meaning an overly strict or misconfigured PDB (e.g., `minAvailable` equal to total replica count) can stall an upgrade indefinitely, a real-world operational trap.

### 38.2.4 Upgrade Strategy Options

| Approach                        | Description                                                                                                                              | Trade-off                                                                                                                                                                                                                                                                            |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Manual upgrade**              | Operator explicitly runs `az aks upgrade` when ready                                                                                     | Full control over timing, but requires active operational discipline to avoid falling behind the supported version window (38.2.1)                                                                                                                                                   |
| **Auto-upgrade channels**       | AKS automatically upgrades the cluster on a configured cadence/channel (e.g., "patch," "stable," "node-image")                           | Reduces operational burden and version-drift risk, at the cost of less precise control over exact upgrade timing — a trade-off between operational safety-net and control, generally favoring auto-upgrade for most production clusters given the real-world risk of upgrade neglect |
| **Planned maintenance windows** | Combined with auto-upgrade channels, restricts _when_ automatic upgrade operations are permitted to occur (e.g., outside business hours) | Reduces the risk of an automated upgrade colliding with peak traffic or a change freeze, while still capturing auto-upgrade's operational safety benefit                                                                                                                             |

💡 **Tip:** a mature production posture typically combines an auto-upgrade channel with a defined maintenance window, rather than choosing purely manual or purely unconstrained automatic upgrades — this reflects a widely accepted best practice balancing operational safety against control, though the exact channel/cadence choice should be stated as a judgment call tied to the organization's own change-management maturity and risk tolerance, not asserted as a universal rule.

### 38.2.5 Command — `az aks upgrade`

- **Purpose:** upgrades the AKS control plane and/or specified node pool(s) to a target Kubernetes version.
- **Syntax:** `az aks upgrade --resource-group <rg> --name <cluster> --kubernetes-version <version>`
- **Key options:**
  - `--control-plane-only` — upgrades only the control plane, leaving node pools at their current version (subject to the version skew policy, 38.2.2).
  - `--node-image-only` — upgrades only the underlying node VM image (OS-level patches, Section 38.3) without changing the Kubernetes version itself — a distinct, more frequent operation from a full Kubernetes version upgrade.
- **Common errors:** attempting to upgrade node pools to a version outside the supported skew relative to the control plane; a PDB stalling the drain step indefinitely (38.2.3), surfaced as an upgrade operation that appears "stuck."
- **Production usage:** in mature environments, this operation (or its Infrastructure-as-Code equivalent, Bicep/Terraform, Sections 47–48) is typically wrapped in a change-managed pipeline with pre-upgrade validation (checking PDB configuration, confirming sufficient subnet IP headroom for the surge, reviewing release notes for the target version's deprecations) rather than run as an unplanned ad hoc command against a production cluster.

---

## 38.3 Node Image Upgrades (Distinct from Kubernetes Version Upgrades)

### 38.3.1 Definition and Why This Is a Separate Concern

The underlying VM image each node boots from (containing the OS, `containerd`, `kubelet` binaries, and other node-level software, Section 36.3.4–36.3.5) is patched and updated by Microsoft on its own release cadence, independent of Kubernetes minor version releases — a node image update might ship an OS security patch or a `containerd` version bump without any change to the cluster's Kubernetes version at all.

### 38.3.2 Why This Matters Operationally

⚠️ **Warning:** an organization that only tracks Kubernetes version upgrades (38.2) while neglecting node image upgrades can accumulate significant OS-level security exposure over time even while nominally staying "on a supported Kubernetes version" — the two upgrade tracks must both be actively managed, and node image upgrades typically need to happen considerably more frequently than Kubernetes minor version upgrades, given the different release cadences of OS security patches versus Kubernetes releases.

- Node image upgrades use the same surge/cordon/drain mechanics described in 38.2.3, since replacing a node's image also requires replacing the node itself (never patched in place, consistent with the immutable-infrastructure principle from Section 34.12).
- The `node-image` auto-upgrade channel (38.2.4) specifically targets this concern, decoupled from the Kubernetes-version auto-upgrade channel, allowing an organization to, for example, aggressively auto-apply node image (OS patch) upgrades while being more conservative and manual about full Kubernetes version upgrades.

---

## 38.4 Node Pool Lifecycle Management

### 38.4.1 Adding and Removing Node Pools

- Production clusters typically run multiple node pools (introduced in Section 36.8): a **system node pool** (tainted to exclude application workloads, running only Azure/Kubernetes system components) and one or more **user node pools** for actual application workloads, potentially differentiated by VM size, specialization (e.g., GPU-enabled), or team/environment ownership.
- **Command — `az aks nodepool add`:**
  ```bash
  az aks nodepool add \
    --resource-group myResourceGroup \
    --cluster-name myAKSCluster \
    --name userpool2 \
    --node-count 3 \
    --node-vm-size Standard_D8s_v5 \
    --enable-cluster-autoscaler --min-count 2 --max-count 10
  ```
  This adds an independently sized and independently autoscaled node pool alongside the existing system pool, applying the per-node-pool Cluster Autoscaler bounds described in Section 37.4.3.
- **Node pool removal:** requires all workloads scheduled on that pool to be safely drained/rescheduled elsewhere first (or accepted as disrupted, for a planned decommission) — the same drain mechanics from 38.2.3 apply.

### 38.4.2 Taints, Tolerations, and Node Selectors (Applying Section 36.6.1)

- **Taints** are applied to nodes to _repel_ pods that do not explicitly tolerate them (e.g., the system node pool is tainted `CriticalAddonsOnly=true:NoSchedule` by default in many AKS configurations, preventing application pods from being scheduled there and preserving system component capacity — verify exact default taint behavior against current documentation).
- **Tolerations** are applied to pods to allow (but not force) scheduling onto tainted nodes.
- **Node selectors / node affinity** direct specific pods toward specific node pools (e.g., a GPU-requiring workload's pods should be scheduled only on a GPU-enabled node pool), typically combined with a corresponding taint on the specialized pool to prevent _other_ workloads from consuming its (potentially expensive) capacity accidentally.
- 🎯 **Interview Tip:** a precise answer distinguishes taints (node-side repulsion) from affinity (pod-side attraction preference) — a very common point of imprecise terminology even among experienced engineers, worth stating explicitly and correctly in an interview answer.

### 38.4.3 Spot Node Pools (Cost Optimization Pattern)

- AKS supports provisioning a node pool using Azure Spot VMs (deeply discounted, reclaimable compute capacity — full Spot VM economics and eviction behavior covered in Section 11's VM pricing material and revisited in Section 64's cost-optimization content), appropriate for fault-tolerant, interruption-tolerant workloads (batch processing, CI build agents, certain stateless/highly-replicated services) where an unexpected node eviction is an acceptable, recoverable event given Kubernetes' self-healing rescheduling (Section 36.6.2).
- ⚠️ **Warning:** Spot node pools should never host workloads without adequate replica count and tolerance for sudden, simultaneous multi-node eviction (Azure Spot capacity can be reclaimed with limited notice) — this is an explicit trade-off decision (cost savings vs. availability risk) appropriate only for genuinely interruption-tolerant workloads, not a default choice for production-critical services.

---

## 38.5 Backup and Disaster Recovery for AKS Workloads

### 38.5.1 What AKS Does and Does Not Provide Natively

🔑 **Key Takeaway:** AKS itself provides no built-in application-data backup mechanism — Kubernetes' declarative object definitions (Deployments, Services, etc.) can be reconstructed from source-controlled manifests (a strong argument for GitOps-style, source-controlled cluster configuration, Section 36.5.3), but **stateful data** (databases, persistent volumes) requires an explicit, separately designed backup strategy, exactly as it would for any other Azure compute.

### 38.5.2 Persistent Volume Backup

- Persistent storage backing Kubernetes `PersistentVolume`s in AKS is most commonly Azure Disks (single-node read-write, Section 18) or Azure Files (multi-node read-write-many, Section 19) — meaning the backup mechanisms already covered in depth in those sections (Azure Disk snapshots/incremental snapshots, Section 18.14; Azure Files soft delete and share snapshots, Section 19.14) apply directly to AKS-attached storage, with the additional Kubernetes-level consideration of ensuring application-consistent snapshots (e.g., quiescing a database's writes briefly, or using a Kubernetes-aware backup tool that coordinates with the application) rather than simply snapshotting the raw disk at an arbitrary point.
- **Velero** (a widely used open-source Kubernetes backup tool, not an Azure-specific product but commonly deployed on AKS) can back up both Kubernetes object definitions and, via a plugin architecture, coordinate Azure Disk/Blob-based snapshots of persistent volume data, providing a more Kubernetes-native backup workflow than orchestrating Section 18/19's storage-layer tools independently.

### 38.5.3 Multi-Region DR Patterns for AKS

- **Active-passive:** a secondary AKS cluster in a paired or otherwise chosen secondary region (Section 3's region pair concepts) remains scaled down or idle, activated during a regional failover; requires a strategy for replicating both cluster configuration (via GitOps/IaC, straightforward to replicate) and application data (via the underlying database/storage service's own cross-region replication — e.g., Section 29's SQL geo-replication/failover groups, or Section 20's storage redundancy options — since AKS itself has no native cross-region data replication mechanism).
- **Active-active:** both regions run live traffic simultaneously, typically fronted by Azure Front Door or Traffic Manager (Section 25) for global load balancing/failover, requiring the application architecture itself to support active-active data consistency (a significant application-design consideration well beyond AKS configuration alone, and one that should be flagged as a genuine architectural decision rather than an AKS setting).
- ⚠️ **Warning:** AKS cluster-level DR planning is frequently under-scoped in practice to just "the cluster comes back up in another region," while the harder and more consequential half of DR — actual data replication and recovery point/time objectives (RPO/RTO) for stateful dependencies — is a separate design exercise layered on top of, not solved by, AKS or Kubernetes itself. This distinction is covered in full generality in Section 61–62 (Part 12).

---

## 38.6 Cost and Capacity Operations

### 38.6.1 Right-Sizing Node Pools

- Node pool VM size and count should be driven by actual observed workload resource `requests`/`limits` (Section 37.4.2) and the per-node system reservation (Section 36.3.5), reviewed periodically rather than set once at initial provisioning and left unexamined — a form of the general Azure capacity-planning discipline covered fully in Section 65.
- 💡 **Tip:** the **Vertical Pod Autoscaler** (a Kubernetes-ecosystem component, not always enabled by default in AKS — verify current availability/configuration against documentation) can provide data-driven `requests`/`limits` recommendations based on observed actual usage, informing both HPA effectiveness (Section 37.4.2's dependency on accurate `requests`) and node pool sizing decisions.

### 38.6.2 Reserved Instances and Azure Hybrid Benefit for Node Pools

- Since AKS node pools are ordinary Azure VMs/VM Scale Sets underneath (Section 36.3.5), the same cost-optimization mechanisms covered generally in Section 64 (Reserved Instances, Azure Hybrid Benefit) apply directly to steady-state, predictable node pool capacity — while Spot node pools (38.4.3) address the opposite end of the cost/availability trade-off for interruption-tolerant capacity.

---

## 38.7 Consolidated Operational Runbook: Common Production Incidents

| Incident                                                                      | First Response                                                                                                                      | Root-Cause Investigation                                                                                                                                               |
| ----------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Widespread `Pending` pods after a traffic spike                               | Check Cluster Autoscaler status and `--max-count`; check subnet IP headroom if traditional Azure CNI (Section 37.2.4)               | Was max-count set too conservatively; is subnet capacity the actual ceiling; review HPA-driven replica request against realistic capacity assumptions                  |
| Application errors immediately following a deployment                         | `kubectl rollout undo` (Section 36.5.3) as immediate mitigation                                                                     | Review the new image/config for the actual defect; review whether readiness probes should have caught the issue before traffic was routed to new pods (Section 36.6.3) |
| Upgrade operation appears stuck                                               | Check for a PDB blocking drain (38.2.3); check for insufficient subnet IP for surge nodes (36.2.4/38.2.3)                           | Was the PDB's `minAvailable` set too strictly relative to actual replica count; was surge capacity accounted for in subnet sizing                                      |
| Unexpected multi-node loss                                                    | Check whether affected nodes were in a Spot node pool (38.4.3) subject to eviction                                                  | Confirm workload placement policy correctly excluded non-interruption-tolerant workloads from Spot capacity                                                            |
| Gradual accumulation of unpatched CVEs despite "supported" Kubernetes version | Check node image upgrade cadence separately from Kubernetes version upgrade cadence (38.3.2)                                        | Confirm the `node-image` auto-upgrade channel or an equivalent manual cadence is actually in place, not just the Kubernetes-version channel                            |
| Data loss following a cluster-level incident                                  | Confirm whether a PV backup strategy (Velero or storage-layer snapshots, 38.5.2) was actually in place and tested, not just assumed | Treat as a process gap requiring a defined, tested backup/restore runbook, not solely a technical fix                                                                  |

---

## 38.8 Best Practices Checklist (Part 7 Wrap-Up)

- [ ] Kubernetes version upgrade cadence actively managed (manual with discipline, or an auto-upgrade channel with a maintenance window) — never allowed to drift out of the supported version window.
- [ ] Node image upgrades tracked and cadenced separately from Kubernetes version upgrades.
- [ ] PDBs reviewed for realistic `minAvailable` values that will not indefinitely stall legitimate drains/upgrades.
- [ ] Subnet IP capacity planning (traditional Azure CNI) explicitly includes upgrade surge headroom, not just steady-state node/pod count.
- [ ] System and user node pools separated via taints/tolerations; specialized pools (GPU, Spot) further isolated via node selectors/affinity plus matching taints.
- [ ] Spot node pools used only for genuinely interruption-tolerant workloads with adequate replica count and self-healing tolerance.
- [ ] Persistent volume backup strategy explicitly defined and periodically tested (Velero and/or Section 18/19's storage-layer snapshot mechanisms), not assumed.
- [ ] Multi-region DR strategy, if required, explicitly addresses data replication for stateful dependencies — not just cluster/control-plane re-creation.
- [ ] Node pool sizing reviewed periodically against actual observed resource usage, not left static from initial provisioning.

---

## 38.9 Common Misconceptions

- "Upgrading the Kubernetes version patches my nodes' OS." _Correction:_ these are two independent upgrade tracks (38.2 vs. 38.3) with different release cadences; both must be actively managed.
- "A PDB guarantees my application stays available during any disruption." _Correction:_ a PDB only constrains _voluntary_ disruptions (drains, upgrades); it cannot prevent or mitigate an _involuntary_ disruption such as an unexpected node crash or a genuinely simultaneous Spot eviction across a pool (38.5.1-adjacent distinction, first introduced in 36.4.4).
- "AKS backs up my application's data automatically." _Correction:_ AKS provides no native application-data backup; this is an explicit, separate design responsibility layered on top of the underlying storage service's own backup mechanisms (38.5.1–38.5.2).

---

## 38.10 Interview Questions (Consolidated)

**Beginner:** "What is the difference between a Kubernetes version upgrade and a node image upgrade on AKS?"
_Model answer:_ a Kubernetes version upgrade changes the version of Kubernetes components (control plane and/or `kubelet`) running in the cluster; a node image upgrade updates the underlying VM image nodes boot from (OS patches, `containerd` version, etc.) without necessarily changing the Kubernetes version at all. They follow independent release cadences and both need active operational management.

**Intermediate:** "Walk through what happens, mechanically, when you run `az aks upgrade` on a node pool."
_Model answer:_ AKS provisions new nodes on the target version (the number of extra nodes controlled by the `--max-surge` setting), then cordons and drains pods off the old nodes onto the new ones — respecting any Pod Disruption Budgets, which can pause the drain if violated — and finally removes the old nodes once their pods have been successfully rescheduled. Nodes are never upgraded in place; this is a replace-not-patch operation consistent with Kubernetes' general immutable-infrastructure approach to nodes.

**Senior:** "A scheduled AKS Kubernetes version upgrade has been running for over an hour and appears stuck at 60% node replacement, with no error reported. What would you check, in order?"
_Model answer:_ first, check whether a Pod Disruption Budget on a workload still running on an un-upgraded node has a `minAvailable` (or `maxUnavailable`) setting that cannot currently be satisfied — for example, `minAvailable` equal to total replica count, which makes any drain of a node hosting one of those replicas impossible until another replica becomes available elsewhere, which itself may be blocked by the same constraint in a poorly configured single-replica-per-node scenario. Second, if using traditional Azure CNI (not Overlay), check whether the subnet has run out of available IP addresses to accommodate the surge nodes the upgrade is trying to provision — new surge nodes (and their pods, under Azure CNI) require IP allocation, and an exhausted subnet would silently stall new node provisioning. Third, check for a node-level issue specific to one of the new nodes (failed to join the cluster, `kubelet` failing to start) via `kubectl get nodes` and, if accessible, node-level diagnostics. The PDB and subnet-exhaustion causes are the two most common real-world root causes for this specific "stuck at partial completion, no clear error" symptom pattern.
_What the interviewer is probing:_ practical, ordered incident-response reasoning grounded in the specific mechanics covered in 38.2.3 and 36.2.4, rather than a generic "check the logs" answer — this question specifically rewards having internalized the surge/drain/PDB/subnet-capacity interaction as a connected system.

**Architect / Scenario:** "Design an upgrade and patching operational strategy for a production AKS cluster running customer-facing workloads with a strict no-downtime requirement, balancing security patch currency against change-management risk."
_Model answer:_ separate the two upgrade tracks explicitly (38.3.2): enable the `node-image` auto-upgrade channel with a defined maintenance window for aggressive, low-risk OS/security patch currency, since node image upgrades are frequent, generally low-risk, and important for security posture; adopt a more measured approach for full Kubernetes version upgrades — for example, a "stable" or "patch" auto-upgrade channel (rather than fully manual, given the real-world risk of version drift falling out of the supported window, 38.2.1) combined with a maintenance window outside peak traffic, and pre-upgrade validation gates (confirming PDB configuration will not stall the upgrade, confirming subnet IP headroom for the configured surge, reviewing the target version's release notes for breaking changes) built into the change-management pipeline rather than assumed. For the no-downtime requirement specifically: ensure every production Deployment has an appropriately (not overly strictly) configured PDB and sufficient replica count spread across nodes/zones so that the surge-drain upgrade mechanic (38.2.3) can proceed without violating availability — this is where Section 36/36's replica-count and anti-affinity guidance directly enables Section 38's safe-upgrade requirement, illustrating how the topics build on each other. State explicitly that "no downtime" during upgrades is achieved through the combination of correct PDB configuration, adequate replica count, and sufficient surge/subnet capacity — not through any single AKS setting alone.
_What the interviewer is probing:_ the ability to design a coherent, layered operational strategy connecting concepts across the whole of Part 7 (networking capacity, scaling/PDB configuration, and this section's upgrade mechanics) toward a specific business requirement, rather than treating each topic as an isolated fact.

---

## 38.11 Key Takeaways Summary

🔑 Kubernetes version upgrades and node image upgrades are two independent operational tracks with different cadences, and both must be actively managed to avoid either falling out of the supported version window or accumulating unpatched OS-level exposure.

🔑 Node (and control plane) upgrades follow a surge-provision, cordon-and-drain, remove-old-node mechanic — nodes are replaced, never patched in place — and this mechanic directly depends on correctly configured Pod Disruption Budgets and, for traditional Azure CNI clusters, adequate subnet IP headroom for surge capacity.

🔑 AKS provides no native application-data backup; persistent volume backup (via Velero and/or the underlying Azure Disk/Files snapshot mechanisms from Sections 18–19) is an explicit, separate design responsibility, as is multi-region data replication for any genuine DR strategy.

🔑 Spot node pools are a deliberate cost/availability trade-off appropriate only for genuinely interruption-tolerant workloads, never a default choice for production-critical services.

🔑 The most consequential real-world AKS production incidents typically arise from the _interaction_ between scaling, PDB configuration, and upgrade/surge mechanics — understanding these as one connected operational system, rather than isolated topics, is what distinguishes strong senior/architect-level troubleshooting and design reasoning.

---

## 38.12 Part 7 Wrap-Up: Consolidated Dependency Recap

```
Section 34 (Docker Fundamentals)
        │  images, layers, Dockerfile, security, containerd/runc
        ▼
Section 35 (Azure Container Registry)
        │  where images live; Managed Identity-based pull auth
        ▼
Section 36 (AKS Architecture)
        │  control plane vs. nodes; pods, Deployments, Services
        ▼
Section 37 (AKS Networking, Scaling, Security)
        │  CNI models, Ingress, HPA/Cluster Autoscaler, dual RBAC, pod hardening, Network Policies
        ▼
Section 38 (AKS Production Operations)  ← this section
   upgrades, node pool lifecycle, backup/DR, cost operations, runbooks
```

Part 7 is now complete. Every downstream Azure container-related topic — Azure Container Apps context in Part 8, CI/CD deployment pipelines targeting AKS/ACR in Part 9, Azure Monitor Container Insights in Part 10, and container-specific security/governance controls in Part 11 — builds directly on the foundation established across these five sections.

---

## 38.13 Related Concepts and What Comes Next

- **Section 40 — Azure Functions Deep Dive (Part 8, next):** shifts from container orchestration to serverless/event-driven compute; where relevant, custom-container Azure Functions (briefly noted in Section 34.11.1) will reference this Part's image/registry foundations directly.
- **Section 61–62 (Part 12):** general HA/DR patterns and Azure Site Recovery/Backup, providing the fuller treatment of the multi-region DR concepts introduced narrowly for AKS in 38.5.3.
- **Section 64–65 (Part 12):** full cost-optimization and capacity-planning treatment, of which 38.6's node-pool-specific guidance is a preview.
- **Section 50–52 (Part 10):** Azure Monitor, Log Analytics/KQL, and Application Insights — the observability layer that operational runbooks like 38.7 depend on in practice for actually detecting and diagnosing the incidents listed there.

---

_End of Section 38. Section 39 closes out Part 7 next with **Service Mesh on AKS**, covering Istio/Linkerd-based traffic management as the fine-grained, mesh-native alternative to the Ingress/AGIC patterns covered in this Part. End of Part 7 — Containers & Orchestration after that. Next Part: Section 40 — Azure Functions Deep Dive (Part 8 — Serverless & Integration)._
