# Section 34 (Part 4): GKE Operations, Scaling & Upgrades — Part 4 Wrap-Up

## 1. Definition

**Plain language:** Building a GKE cluster is the easy part; keeping it running well over months and years — patched, right-sized as load changes, and neither over- nor under-provisioned — is the ongoing operational work this section covers.

**Precise:** GKE operations spans three related but distinct concerns: **upgrades** (keeping the control plane and node OS/`kubelet` version current, via release channels and maintenance windows, Section 30), **workload-level scaling** (the **Horizontal Pod Autoscaler (HPA)** and **Vertical Pod Autoscaler (VPA)**, which resize the number or size of Pods based on observed demand), and **infrastructure-level scaling** (the **Cluster Autoscaler** and **node auto-provisioning (NAP)**, which resize and reshape the node fleet underneath those Pods to match).

## 2. Why It Exists / Problem It Solves

A cluster sized correctly on day one is wrong within weeks — traffic grows, shrinks, and shifts shape, and Kubernetes minor versions ship roughly every few months upstream with their own security patches that can't be deferred indefinitely. Manually re-sizing Deployments and node pools, and manually scheduling upgrade windows, doesn't scale past a handful of clusters — it's exactly the kind of continuous, reactive toil that made self-managed Kubernetes control planes painful before GKE (Section 30). Automated scaling and automated upgrades exist to make "matching capacity to demand" and "staying patched" continuous background properties of a cluster rather than a recurring manual task for a platform team.

## 3. Auto-Upgrades and Maintenance Windows

GKE clusters on a **release channel** (Section 30) receive **automatic upgrades** for both the control plane and node pools, gated to versions Google has already validated for that channel. Two customer-facing controls shape when upgrades actually happen:

- **Maintenance windows** — a recurring time range (e.g., Saturdays 02:00–06:00 UTC) during which GKE is permitted to perform disruptive maintenance, including node upgrades; outside this window, GKE defers eligible maintenance.
- **Maintenance exclusions** — a defined date range during which GKE will _not_ perform certain categories of disruptive maintenance at all, used to protect known business-critical periods (e.g., a retail freeze around a major sales event) from an upgrade landing mid-event.

Node upgrades within a pool proceed via a **surge upgrade** strategy by default — GKE creates new nodes on the target version, drains and cordons old nodes gradually, and removes them once workloads have rescheduled onto the new nodes, controlled by `max-surge` and `max-unavailable` settings that trade upgrade speed against how much temporary extra node capacity is provisioned during the rollout.

> ⚠️ **Interview-relevant nuance:** Maintenance windows control _when_ GKE is allowed to act; they don't prevent upgrades from happening at all. A cluster on a release channel will still eventually be upgraded to keep pace with that channel's supported versions — maintenance exclusions, not windows, are the tool for genuinely blocking upgrades during a specific critical period, and even those are time-bounded, not permanent opt-outs.

## 4. Workload-Level Scaling: HPA and VPA

| Autoscaler                          | Scales                                             | Trigger                                                                                     | Typical Fit                                                                                          |
| ----------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------- |
| **Horizontal Pod Autoscaler (HPA)** | Number of Pod replicas in a Deployment/StatefulSet | CPU/memory utilization, or custom/external metrics (e.g., queue depth via Cloud Monitoring) | Stateless workloads that scale well by adding more replicas                                          |
| **Vertical Pod Autoscaler (VPA)**   | CPU/memory **requests** of individual Pods         | Historical and current usage observed for that workload                                     | Workloads that scale better by resizing than replicating, or to right-size initial resource requests |

HPA and VPA are not interchangeable and, in their default configuration, **should not target the same resource metric on the same workload simultaneously** — HPA reacting to CPU by adding replicas while VPA simultaneously resizes CPU requests on those replicas can fight each other, producing thrashing rather than stable scaling. VPA is commonly run in **recommendation-only mode** even alongside HPA, purely to inform what resource requests a workload's manifest should declare, without VPA actively resizing running Pods.

## 5. Infrastructure-Level Scaling: Cluster Autoscaler and Node Auto-Provisioning

- **Cluster Autoscaler** watches for Pods that can't be scheduled due to insufficient node capacity and adds nodes to an existing node pool to fit them; it also removes nodes that have been underutilized for a sustained period and whose Pods can be safely rescheduled elsewhere, within the min/max bounds configured per node pool.
- **Node auto-provisioning (NAP)** goes a step further than the Cluster Autoscaler: rather than only scaling existing node pools, NAP can create **entirely new node pools** automatically — with an appropriate machine type — when scheduled Pods need a shape of resources (e.g., a specific GPU type, or a much larger memory ratio) no existing pool provides, within limits the operator defines.
- In **Autopilot** (Section 32), this entire layer is invisible to the customer — Google performs the equivalent of Cluster Autoscaler and NAP behind the scenes automatically, which is precisely the operational burden Autopilot removes.

## 6. GKE Managed Istio (Brief Mention)

GKE offers a managed **Istio-based service mesh add-on** (historically branded Anthos Service Mesh / Cloud Service Mesh) that layers mutual TLS between Pods, fine-grained traffic management (canary splitting, retries, circuit breaking), and mesh-wide observability on top of the networking primitives covered in Section 31, without requiring the customer to operate Istio's control plane themselves. It's typically adopted once an organization's number of interdependent microservices grows large enough that Gateway API-level routing (Section 31) alone no longer gives enough east-west traffic control and observability — a deeper architectural topic outside this Part's scope, noted here as the natural next step past what Sections 28–34 cover.

## 7. Hands-On Example

**Beginner example — apply an HPA to a Deployment:**

```bash
kubectl autoscale deployment my-app --cpu-percent=60 --min=2 --max=10
kubectl get hpa my-app
```

**Purpose:** Creates an HPA targeting the `my-app` Deployment, scaling replicas between 2 and 10 to keep average CPU utilization near 60%.

**Expected output:**

```
NAME     REFERENCE           TARGETS   MINPODS   MAXPODS   REPLICAS   AGE
my-app   Deployment/my-app   45%/60%   2         10        3          40s
```

**Intermediate example — enable Cluster Autoscaler with bounds on a node pool:**

```bash
gcloud container clusters update my-cluster \
  --region=us-central1 \
  --enable-autoscaling \
  --node-pool=default-pool \
  --min-nodes=1 \
  --max-nodes=8
```

**Purpose:** Turns on the Cluster Autoscaler for `default-pool`, letting GKE add nodes (up to 8) when Pods can't be scheduled and remove nodes (down to 1) when sustained utilization is low.

**Expected output (abbreviated):**

```
Updating my-cluster...done.
NAME         NODE_POOL     AUTOSCALING   MIN_NODES  MAX_NODES
my-cluster   default-pool  enabled       1          8
```

## 8. Production & Enterprise Usage

- Production clusters set **maintenance windows** deliberately (typically low-traffic hours) and use **maintenance exclusions** proactively around known critical business periods, rather than discovering an in-progress node upgrade during a peak event.
- Combining **HPA on custom/external metrics** (e.g., a queue-depth metric from Cloud Monitoring rather than raw CPU) is standard for workloads whose real bottleneck isn't CPU-bound, since CPU-only HPA can badly under- or over-scale a queue-processing workload.
- **Node auto-provisioning** is common in shared, multi-tenant enterprise clusters running heterogeneous workloads (some needing GPUs, some memory-optimized), so new node shapes appear automatically as new workload types are onboarded, rather than requiring a platform-team ticket to pre-create every needed node pool.

## 9. Common Misconceptions

- **Misconception:** "A maintenance window prevents upgrades from ever happening outside it." A maintenance window only controls _when_ GKE is permitted to perform maintenance — a release-channel cluster will still be upgraded eventually to remain within its channel's supported version range; only maintenance exclusions can genuinely block maintenance for a bounded period.
- **Misconception:** "HPA and VPA can safely both actively manage the same resource metric on the same workload." Running HPA and VPA both actively targeting CPU on the same workload can cause the two autoscalers to work against each other; the common safe pattern is HPA for replica count plus VPA in recommendation-only mode, or scoping VPA to a different resource dimension than HPA's trigger metric.

## 10. Interview Questions

**🎯 Beginner:** _What's the difference between the Horizontal Pod Autoscaler and the Cluster Autoscaler?_
**Model answer:** HPA operates at the workload level — it changes the number of Pod replicas for a Deployment based on observed metrics like CPU. The Cluster Autoscaler operates at the infrastructure level — it changes the number of _nodes_ in a node pool, adding nodes when Pods can't be scheduled due to insufficient capacity and removing underutilized nodes. They work together: HPA creating more Pods can trigger the Cluster Autoscaler to add nodes to fit them.

**🎯 Intermediate:** _Why might an organization proactively define a maintenance exclusion rather than relying solely on their regular maintenance window?_
**Model answer:** A maintenance window only limits maintenance to a recurring low-traffic time slot; it doesn't stop a release-channel cluster's normal upgrade cadence from eventually landing an upgrade, including around a known critical business period if that period happens to fall inside or near the window's schedule. A maintenance exclusion explicitly blocks disruptive maintenance for a defined date range regardless of the regular window, which is the correct tool for protecting a specific known event (a major sale, a product launch) from any upgrade-related disruption.

**🎯 Senior/Architect:** _Design the autoscaling and upgrade strategy for a multi-tenant GKE cluster running a mix of steady web services and bursty batch/GPU workloads._
**Model answer:** I'd separate the workloads into distinct node pools by shape — a general-purpose pool for steady web services and a GPU pool for batch workloads — with **node auto-provisioning** enabled so new node shapes for future workload types can appear automatically without a manual node-pool-creation step each time. Web services get **HPA** on request-latency or custom queue-depth metrics rather than raw CPU where that's the truer bottleneck, backed by the **Cluster Autoscaler** on their pool; the GPU batch pool relies more heavily on the Cluster Autoscaler scaling to zero between batch runs, since GPU capacity is expensive to hold idle. For upgrades, I'd put this cluster on the **Regular** release channel with a maintenance window during the batch workload's known-quiet hours, plus maintenance exclusions around any known business-critical processing windows, and would size `max-surge`/`max-unavailable` conservatively for the GPU pool specifically, since GPU node replacement during an upgrade is more disruptive to reschedule than general-purpose capacity.

## 11. Part 4 Consolidated Knowledge Map

Kubernetes on GCP (Part 4) breaks down into:

- S28 Container Fundamentals: images, registries, the Borg/Kubernetes lineage
- S29 Artifact Registry: storing and scanning container images before they ever reach a cluster
- S30 GKE Architecture: managed control plane vs. customer-managed node pools, zonal vs. regional, release channels
- S31 GKE Networking & Storage: VPC-native Pod/Service IPs, Ingress/Gateway API, CSI-backed Persistent Disks and Filestore
- S32 Autopilot vs. Standard: Pod-based vs. node-based management and billing
- S33 GKE Security & Workload Identity: least-privilege Pod identity, Shielded Nodes, private clusters, Binary Authorization forward-ref
- S34 Operations, Scaling & Upgrades: maintenance windows, HPA/VPA, Cluster Autoscaler, NAP, managed Istio mention

**Throughline:** S28–29 establish what actually runs in a cluster before a cluster exists. S30–31 build the cluster itself — the managed control plane, node pools, and the networking/storage fabric Pods run on. S32 is the fundamental mode decision (who manages the nodes) that reshapes everything downstream of it. S33 layers identity and network hardening on top of whichever mode was chosen. S34 closes the loop with what keeps a chosen architecture healthy indefinitely — scaling to match demand and staying current without manual toil.

## 12. Part 4 Key-Takeaways Checklist

- Explain the GKE control plane vs. node pool split, and why regional (not just multi-zonal) clusters protect against a control-plane zone outage.
- State the difference between VPC-native alias IP Pod networking and an overlay network, and why it matters for firewall/Flow Log visibility.
- Choose correctly between Ingress and the Gateway API, and between a Persistent Disk and Filestore, for a given workload's needs.
- Explain Autopilot's per-Pod billing model versus Standard's per-node billing, and identify when a workload's requirements force a Standard choice.
- Explain what Workload Identity replaces and why static GSA key files are an anti-pattern.
- Distinguish HPA from VPA from the Cluster Autoscaler from node auto-provisioning — what each one actually resizes.
- Explain the difference between a maintenance window and a maintenance exclusion.

## 13. Part 4 Interview Drill

**How do the GKE control plane and a node pool divide responsibility, and how does that change under Autopilot?**
In Standard mode, Google fully manages the control plane (API server, `etcd`, scheduler, controller manager) while the customer manages node pools — Compute Engine VMs they size and scale. Under Autopilot, Google additionally manages node provisioning and sizing itself, billing per Pod resource request instead of per VM, so the customer's remaining responsibility shrinks to declaring what their Pods need.

**Why does VPC-native networking matter more on GKE than "just use whatever the default is"?**
VPC-native clusters assign Pods real, routable VPC IPs from alias IP ranges rather than an overlay network, which means VPC firewall rules, Flow Logs, and Shared VPC configurations can see and act on Pod traffic directly. Choosing routes-based (legacy) networking loses that integration, which is why VPC-native is the default and near-universal recommendation.

**A workload needs shared read-write file access across 20 replicas — what storage choice, and why not the alternative?**
Filestore, because it's natively `ReadWriteMany` managed NFS. A Persistent Disk is fundamentally single-writer (`ReadWriteOnce` in the default case), so it cannot satisfy genuinely simultaneous multi-Pod write access regardless of how it's configured.

**When would Standard mode be required over Autopilot despite Autopilot being the recommended default?**
When a workload needs privileged containers, host networking/PID/IPC namespaces, custom DaemonSets, or GPU/TPU configurations outside Autopilot's curated support set — Autopilot's hardened, opinionated defaults disallow or restrict these by design, so a genuine unavoidable requirement for them forces Standard.

**Why is a downloaded GSA JSON key considered worse than Workload Identity, beyond just being inconvenient?**
It's a long-lived, static, exportable credential that can be copied out of the cluster, logged accidentally, or committed to source control, with no automatic expiry or rotation. Workload Identity issues short-lived, automatically rotated credentials scoped to a specific KSA-to-GSA binding, eliminating that durable-secret exposure entirely.

**What's the risk of running HPA and VPA both actively targeting CPU on the same Deployment?**
The two autoscalers can work against each other — HPA adding replicas in response to CPU pressure while VPA simultaneously resizes each Pod's CPU request — producing scaling thrashing rather than stable behavior. The safe pattern is HPA for replica count with VPA in recommendation-only mode, or scoping each to a different metric.

**Design a resilient, cost-aware GKE setup for a workload with unpredictable traffic spikes.**
Regional cluster (control-plane resilience) on the Regular release channel with a sensible maintenance window; either Autopilot (if no node-level restrictions apply, for automatic capacity matching with no idle-node cost) or Standard with Cluster Autoscaler and HPA tuned to a leading-indicator metric (queue depth, request latency) rather than lagging CPU alone, so scale-out begins before user-facing latency degrades; Workload Identity and a private cluster regardless of mode chosen, since neither depends on the scaling-mode decision.

## 14. Related Concepts

Container fundamentals (Section 28), Artifact Registry (Section 29), GKE architecture and release channels (Section 30), GKE networking and storage (Section 31), Autopilot vs. Standard (Section 32), Workload Identity and cluster security (Section 33), and — looking ahead — IAM fundamentals and service accounts opening Part 5 (Section 35) all connect directly to the operational practices covered here.

## Part 4 Complete

All seven sections of Kubernetes on GCP (Sections 28–34) are done — from container fundamentals and image registries, through cluster architecture, networking, storage, the Autopilot/Standard mode decision, security and Workload Identity, to ongoing operations and scaling. GKE's security model in Section 33 deliberately left Binary Authorization as a forward reference, because deploy-time image trust enforcement belongs alongside the rest of GCP's identity and security stack.

**Next: Part 5 — IAM & Security**, starting at **Section 35 (IAM Fundamentals)**, followed by Service Accounts (36), Org Policies (37), Secret Manager & KMS (38), Security Command Center (39), Compliance & Governance (40), VPC Service Controls (41), Cloud Identity & BeyondCorp (42), and closing with Binary Authorization & Confidential Computing (43) — picking up exactly where Section 33's forward reference left off.
