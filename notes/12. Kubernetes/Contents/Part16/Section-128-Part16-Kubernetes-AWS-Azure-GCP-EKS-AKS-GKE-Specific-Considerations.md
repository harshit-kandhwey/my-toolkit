# Section 128 (Part 16): Kubernetes on AWS/Azure/GCP: EKS/AKS/GKE-Specific Considerations

## 1. Definition

**Plain language:** Running Kubernetes on a managed provider doesn't erase the differences between clouds — it relocates them from "how do I bootstrap this cluster" (already covered in §21) into "how does this cluster actually behave in production": how it autoscales, how it bills, what its native cost and networking tooling looks like, and which cloud-specific failure modes an operator needs to know about that would never show up on a self-managed kubeadm cluster.

**Precise definition:** This section covers the **operational, cost, and architectural nuances** that distinguish EKS, AKS, and GKE once a cluster is already running, extending §21's (Part 3) bootstrap-time comparison into steady-state operation: node autoscaling mechanics (Cluster Autoscaler vs. Karpenter on EKS, the cluster autoscaler add-on on AKS, native node auto-provisioning on GKE), each provider's approach to spot/preemptible capacity, load-balancer and ingress integration patterns specific to each cloud's networking stack, storage-class defaults tied to each cloud's block storage product, and each provider's native cost-visibility tooling. It assumes the resource-governance layer from §127 (ResourceQuota/LimitRange) is already in place and asks the next question: **given that layer, what does each cloud provider additionally do (or fail to do) to help or hinder cost and operational efficiency at the infrastructure layer beneath it.**

## 2. Why This Matters

- **Autoscaling behavior is the single biggest cost lever beneath ResourceQuota/LimitRange (§127)**, and it is genuinely different across providers — Karpenter's just-in-time, bin-packing node provisioning on EKS behaves fundamentally differently from AKS's cluster-autoscaler-plus-node-pool model or GKE Autopilot's fully-abstracted per-Pod billing, and choosing the wrong mental model for a given provider leads directly to over-provisioned (wasted spend) or under-provisioned (throttled/evicted workloads) clusters.
- **Cloud-specific storage and networking defaults quietly shape reliability and cost** — the default StorageClass, its reclaim policy, and its underlying block-storage product's availability-zone behavior differ meaningfully between EBS-backed EKS, Azure Disk-backed AKS, and Persistent Disk-backed GKE, and assuming one provider's defaults transfer to another is a common migration mistake.
- **§21 (Part 3) established that "managed" doesn't mean "identical"; this section is the enterprise-scale continuation of that claim** — it's the operational depth a platform team actually needs once past initial bootstrap, and it feeds directly into §129's landing-zone synthesis.

🔑 **Key Takeaway:** EKS gives the most granular control (and the most manual assembly) via tools like Karpenter and Cluster Autoscaler; AKS gives the tightest turnkey integration for organizations already standardized on Azure (AD, Azure Monitor, Azure Policy); GKE offers the most opinionated, fully-managed extremes at either end (Standard's node-pool control vs. Autopilot's per-Pod abstraction) — and none of these differences are cosmetic once ResourceQuota/LimitRange (§127) governance is layered on top and real cloud spend is on the line.

## 3. Prerequisites and Dependencies

Builds directly on §21 (Managed Kubernetes Bootstrap Differences: EKS, AKS, GKE, Part 3) for the identity and bootstrap-time comparison this section extends into steady-state operation, and on §127 (Part 16) for the ResourceQuota/LimitRange governance layer this section's cloud-specific autoscaling and cost tooling interacts with. Assumes familiarity with each cloud's basic compute and storage primitives (EC2/EBS, Azure VMs/Disk, GCE/Persistent Disk).

## 4. Architecture Diagram

```text
                    CLOUD-SPECIFIC OPERATIONAL LAYER (beneath ResourceQuota/LimitRange, §127)

   ┌─────────────────────────────┐  ┌───────────────────────────────┐  ┌─────────────────────────────────┐
   │          EKS                │  │          AKS                  │  │          GKE                    │
   │                             │  │                               │  │                                 │
   │ Autoscaling:                │  │ Autoscaling:                  │  │ Autoscaling:                    │
   │  - Cluster Autoscaler       │  │  - Cluster Autoscaler         │  │  - Cluster Autoscaler           │
   │    (per-ASG node group)     │  │    (per-node-pool)            │  │    (per-node-pool, Standard)    │
   │  - Karpenter (newer,        │  │  - Node auto-provision        │  │  - Node Auto-Provisioning       │
   │    just-in-time, bin-pack,  │  │    (preview/GA varies)        │  │    (Standard, similar to        │
   │    provider-agnostic        │  │                               │  │    Karpenter's goal)            │
   │    node shapes)             │  │                               │  │  - Autopilot: no node           │
   │                             │  │                               │  │    autoscaling exposed at       │
   │                             │  │                               │  │    all — per-Pod billing        │
   │                             │  │                               │  │    replaces the concept         │
   │                             │  │                               │  │                                 │
   │ Spot capacity:              │  │ Spot capacity:                │  │ Spot capacity:                  │
   │  EC2 Spot node groups,      │  │  Spot VMs node pools,         │  │  Spot VMs node pools,           │
   │  Karpenter spot-aware       │  │  eviction via Azure signal    │  │  30s preemption notice,         │
   │  provisioning               │  │                               │  │  Autopilot Spot Pods exist too  │
   │                             │  │                               │  │                                 │
   │ Storage default:            │  │ Storage default:              │  │ Storage default:                │
   │  gp2/gp3 EBS StorageClass   │  │  managed-csi (Azure Disk)     │  │  pd-balanced/pd-ssd             │
   │  single-AZ PVs by default   │  │  single-zone by default       │  │  regional PD option for multi-AZ│
   │                             │  │                               │  │                                 │
   │ Load balancing:             │  │ Load balancing:               │  │ Load balancing:                 │
   │  AWS Load Balancer          │  │  Azure LB / Application       │  │  GCE ingress / Cloud Load       │
   │  Controller (ALB/NLB)       │  │  Gateway Ingress Controller   │  │  Balancing native integration   │
   │                             │  │                               │  │                                 │
   │ Cost tooling:               │  │ Cost tooling:                 │  │ Cost tooling:                   │
   │  Cost Explorer + Kubecost/  │  │  Azure Cost Management +      │  │  GKE cost allocation (native,   │
   │  OpenCost (not native to    │  │  native AKS cost views        │  │  per-namespace/label built in)  │
   │  Kubernetes objects)        │  │  (namespace-level, GA)        │  │                                 │
   └─────────────────────────────┘  └───────────────────────────────┘  └─────────────────────────────────┘
                │                                   │                              │
                └───────────────────────────────────┴──────────────────────────────┘
                                                    ▼
                              Same ResourceQuota / LimitRange governance (§127)
                              sits above all three, but produces different actual
                              cost/reliability outcomes depending on the provider's
                              autoscaling, storage, and networking behavior beneath it.
```

## 5. Hands-On

### 5.1 EKS: Karpenter for Just-in-Time, Bin-Packing Node Provisioning

**Purpose:** Show how Karpenter's provisioning model differs from the older, ASG-based Cluster Autoscaler by directly launching right-sized EC2 instances per pending Pod rather than scaling a pre-defined node group.

**Syntax:**

```yaml
apiVersion: karpenter.sh/v1
kind: NodePool
metadata:
  name: default
spec:
  template:
    spec:
      requirements:
        - key: karpenter.sh/capacity-type
          operator: In
          values: ["spot", "on-demand"]
        - key: kubernetes.io/arch
          operator: In
          values: ["amd64"]
      nodeClassRef:
        name: default
  limits:
    cpu: "1000"
  disruption:
    consolidationPolicy: WhenUnderutilized
```

```bash
kubectl get nodepool
kubectl get nodeclaims
```

**Production usage example:** A platform team running highly variable batch and CI workloads on EKS replaces a fixed set of Cluster Autoscaler-managed node groups with a Karpenter NodePool that can launch any instance shape from a defined family, letting Karpenter bin-pack Pods onto the smallest set of right-sized instances rather than scaling whole, pre-sized node groups — typically producing meaningfully better bin-packing efficiency and lower idle-capacity cost than ASG-based autoscaling.

**Common errors:** Setting `consolidationPolicy: WhenUnderutilized` without understanding that Karpenter will actively terminate and reschedule Pods off underutilized nodes to consolidate capacity — teams running Pods that assume long node lifetimes (without PodDisruptionBudgets, §39 Part 5) can see unexpectedly frequent, disruptive node churn.

### 5.2 AKS: Native Azure Cost Management Integration and Node Pool Sizing

**Purpose:** Show AKS's built-in, namespace/label-level cost allocation view, which requires no third-party tool (unlike EKS's reliance on Kubecost/OpenCost) for basic chargeback visibility.

**Syntax:**

```bash
az aks update --resource-group my-rg --name my-cluster --enable-cost-analysis
```

```bash
az aks nodepool add \
  --resource-group my-rg --cluster-name my-cluster \
  --name spotpool --priority Spot \
  --eviction-policy Delete --spot-max-price -1 \
  --enable-cluster-autoscaler --min-count 0 --max-count 10
```

**Production usage example:** A finance team asks for per-team Kubernetes cost breakdown without deploying additional tooling; the platform team enables AKS's native cost analysis add-on (GA, built on OpenCost under the hood but surfaced natively in the Azure portal) and gets namespace-level cost views directly correlated with Azure billing, without standing up a separate Kubecost deployment as would typically be required on EKS.

**Common errors:** Setting `--spot-max-price -1` (pay up to standard on-demand price to avoid eviction on price) without also configuring pod-level tolerance for the `Spot` node taint and an eviction-handling strategy — Spot node pools still receive eviction notices regardless of price cap, and workloads without graceful-eviction handling can experience abrupt termination.

### 5.3 GKE: Autopilot's Per-Pod Cost Model vs. Standard's Node Auto-Provisioning

**Purpose:** Contrast Autopilot's abstraction of node cost entirely away from the operator against Standard mode's Node Auto-Provisioning, GKE's own answer to Karpenter-style just-in-time node shape selection.

**Syntax:**

```bash
# Standard mode: enable Node Auto-Provisioning
gcloud container clusters update my-cluster \
  --enable-autoprovisioning \
  --min-cpu 4 --min-memory 16 \
  --max-cpu 100 --max-memory 400

# View per-Pod cost breakdown on Autopilot (native, no add-on needed)
gcloud container clusters describe my-cluster --region us-central1 \
  --format="value(autopilot.enabled)"
```

**Production usage example:** A team on GKE Autopilot reviews their GCP bill directly against Pod resource requests, since Autopilot bills per-Pod resource reservation rather than per-node — making the ResourceQuota/LimitRange (§127) rightsizing discipline from the previous section directly and immediately visible in the cloud bill, with none of the node-utilization-efficiency question that Standard mode or EKS/AKS node-pool billing introduces.

**Common errors:** Assuming Node Auto-Provisioning on GKE Standard behaves identically to Karpenter on EKS — both select node shapes just-in-time, but NAP operates within GKE's own node-pool abstraction and constraints (min/max CPU and memory bounds set cluster-wide), while Karpenter's NodePool/NodeClass model exposes more granular per-workload provisioning constraints; treating the two as drop-in equivalents during a migration misses real configuration differences.

## 6. Production Usage Notes

- **EKS's cost/autoscaling tooling is the most "assemble it yourself" of the three** — Karpenter, Cluster Autoscaler, and Kubecost/OpenCost are all separately installed and configured components, giving maximum flexibility at the cost of more operational assembly and ongoing maintenance burden than AKS's or GKE's more integrated native equivalents.
- **AKS's native cost analysis add-on and GKE's built-in cost allocation both remove the "stand up Kubecost" step** that EKS typically still requires for namespace/label-level cost visibility — a real operational cost difference between providers that is easy to overlook when comparing raw compute pricing alone.
- **Spot/preemptible capacity handling differs subtly across providers**: AWS Spot interruption gives a 2-minute warning via an instance metadata endpoint, Azure Spot VMs give a 30-second eviction notice, and GCP Spot VMs give a 30-second preemption notice — workloads designed for graceful shutdown on one cloud's notice window need verification, not assumption, when moved to another.
- **Regional/zonal storage defaults affect real availability**: EKS's default StorageClass (`gp2`/`gp3`, EBS-backed) is single-AZ by default, as is AKS's `managed-csi`, while GKE additionally offers regional Persistent Disks as an explicit, opt-in multi-zone option — a StatefulSet's actual resilience to an availability-zone failure depends on this choice, not just on the StatefulSet spec itself.

## 7. Security Considerations

- **Karpenter's node-provisioning IAM role (on EKS) is a high-value target** — since Karpenter directly launches EC2 instances and can attach IAM instance profiles, the IAM role Karpenter itself assumes must be scoped tightly (least-privilege for `ec2:RunInstances`, `iam:PassRole` limited to the specific node instance profiles), since an overly broad Karpenter controller role effectively grants broad EC2 provisioning capability to anything that can create a NodePool object.
- **Azure Spot VM eviction and AWS/GCP Spot preemption both interact with Pod Security and workload assumptions** — a workload relying on Spot capacity without properly configured PodDisruptionBudgets (§39, Part 5) and graceful shutdown handling can experience data-integrity issues on abrupt termination, which is a reliability and correctness concern with security-adjacent implications for stateful workloads specifically.
- **Native cost-visibility tooling (AKS cost analysis, GKE cost allocation) typically requires broader read access to billing and resource-usage data** than most application teams need by default — scoping who can view cross-namespace cost breakdowns is itself a minor but real access-governance decision, particularly in a shared cluster where cost data can reveal one tenant's usage patterns to another if not properly scoped.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                          | Likely Cause                                                                                                    | Fix                                                                                                                                       |
| -------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------- |
| Nodes on EKS churn frequently, disrupting long-running workloads                 | Karpenter's `consolidationPolicy: WhenUnderutilized` actively terminates underutilized nodes for bin-packing    | Add PodDisruptionBudgets (§39) to protect critical workloads, or adjust the NodePool's disruption/consolidation settings                  |
| Spot-based Pod terminated with no graceful shutdown observed                     | Application doesn't handle the cloud's Spot/preemption notice window (varies: AWS ~2 min, Azure/GCP ~30 sec)    | Implement a `preStop` hook or signal handler matched to the actual notice window for that specific cloud                                  |
| StatefulSet's PV unavailable after an availability-zone outage                   | Default StorageClass is single-zone (EBS gp2/gp3, AKS managed-csi default); no cross-zone redundancy configured | Use GKE regional Persistent Disks, or design application-level replication instead of relying on storage-layer zone redundancy on EKS/AKS |
| Per-team cost breakdown unavailable on EKS without extra tooling                 | EKS has no native namespace-level cost allocation feature comparable to AKS/GKE's built-in options              | Deploy Kubecost or OpenCost explicitly on EKS; budget for this as a required, separate operational component                              |
| DaemonSet or privileged workload fails to schedule after moving to GKE Autopilot | Autopilot restricts node-level access by design (also covered at bootstrap-time in §21)                         | Migrate the workload to GKE Standard, or redesign the workload to avoid node-level/privileged requirements                                |

## 9. Best Practices

- Choose an autoscaling model deliberately per provider rather than assuming feature parity: Karpenter on EKS for granular, provider-flexible bin-packing; native Cluster Autoscaler/Node Auto-Provisioning on AKS/GKE Standard where turnkey integration outweighs Karpenter's extra configurability; Autopilot on GKE when the goal is removing node-management entirely.
- Budget explicitly for Kubecost/OpenCost as a required operational component on EKS specifically, since — unlike AKS and GKE — EKS has no comparably mature native namespace-level cost allocation feature.
- Verify each cloud's actual Spot/preemptible notice window and design graceful-shutdown handling against that cloud's real window, rather than assuming a handler tuned for one provider transfers unchanged to another.
- Treat storage zone-redundancy as an explicit per-provider decision (regional PD on GKE vs. application-level replication on EKS/AKS), not an assumption inherited from a StatefulSet spec that "worked" on a different cloud.

## 10. Common Anti-Patterns / Mistakes

- **Assuming Karpenter, GKE Node Auto-Provisioning, and AKS's cluster autoscaler are functionally interchangeable** during a multi-cloud platform design, when their configuration models, granularity, and defaults meaningfully differ.
- **Deploying Spot/preemptible capacity without verifying the specific cloud's eviction notice window**, leading to abrupt, ungraceful workload termination that a correctly-tuned handler would have avoided.
- **Relying on third-party cost tooling assumptions built for one provider when moving to another** — e.g., assuming Kubecost must be separately deployed on AKS or GKE the way it typically is on EKS, missing that native alternatives already exist there.
- **Ignoring storage zone-redundancy defaults during a cross-cloud migration**, discovering only after an availability-zone incident that the new provider's default StorageClass behaves differently than the one being migrated from.

## 11. Interview Questions

**🎯 Beginner:** _"Name one operational difference between EKS, AKS, and GKE that goes beyond how you initially set up the cluster."_
**Model answer:** Native cost-visibility tooling is a clear one — AKS and GKE both offer built-in, namespace/label-level cost allocation views out of the box, while EKS typically requires deploying a separate tool like Kubecost or OpenCost to get comparable per-team cost breakdowns. Another is node autoscaling: EKS commonly uses Karpenter for just-in-time node provisioning, while AKS and GKE Standard rely more on their own native cluster-autoscaler or node-auto-provisioning features, and GKE Autopilot removes node-level autoscaling from the picture entirely by billing per-Pod instead.
_What the interviewer is probing for:_ Awareness that "managed Kubernetes" differences extend well past bootstrap-time (§21) into ongoing operational and cost behavior.

**🎯 Intermediate:** _"How does Karpenter's node-provisioning model differ from a traditional Cluster Autoscaler scaling a fixed set of node groups?"_
**Model answer:** A traditional Cluster Autoscaler scales pre-defined node groups (Auto Scaling Groups on AWS, or equivalent) up and down within their existing instance-type configuration — it decides _how many_ nodes of an already-chosen shape to run. Karpenter instead directly provisions right-sized nodes per pending Pod's actual requirements, choosing from a broader set of possible instance shapes defined in a NodePool/NodeClass, and it can also actively consolidate underutilized nodes to improve bin-packing. The practical difference is that Karpenter tends to produce tighter bin-packing and less idle capacity, but its disruption/consolidation behavior needs to be paired with PodDisruptionBudgets for workloads that shouldn't be frequently rescheduled.
_What the interviewer is probing for:_ Genuine understanding of the provisioning model difference, not just "Karpenter is EKS's autoscaler."

**🎯 Senior:** _"A team migrating a StatefulSet from AKS to GKE reports it's now resilient to an availability-zone failure in a way it wasn't before, without any application-level change. What likely explains this?"_
**Model answer:** The most likely explanation is a StorageClass difference, not an application change. AKS's default `managed-csi` StorageClass provisions single-zone Azure Disks by default, so a PV backing that StatefulSet's storage was tied to one zone and would become unavailable if that zone failed. GKE offers regional Persistent Disks as an explicit option, which synchronously replicate data across two zones within a region — if the migrated cluster's StorageClass was set (deliberately or by a differing default) to use a regional PD, the StatefulSet would gain zone-failure resilience purely from the storage layer, with no application-level replication logic involved. I'd confirm this is deliberate and not accidental, since regional PDs carry a meaningful cost and write-latency premium over zonal PDs that should be a conscious trade-off, not a side effect of an unexamined default.
_What the interviewer is probing for:_ Ability to trace a cross-cloud behavioral difference to a specific infrastructure-layer cause (storage zone redundancy) rather than assuming it's inherently "just how GKE is better," and awareness of the cost trade-off that comes with that resilience.

**🎯 Architect:** _"Your organization runs workloads on all three major clouds and wants a single cost-governance and autoscaling strategy that doesn't require three completely separate playbooks per cloud. What would you propose, and what can't realistically be unified?"_
**Model answer:** I'd unify at the layer that's already cloud-agnostic — ResourceQuota and LimitRange (§127) applied identically across all three, since Kubernetes-native resource governance doesn't care which cloud it's running on, and standardized tenant tiers built on those objects give one consistent story regardless of underlying provider. For cost visibility, I'd standardize on OpenCost (or a paid Kubecost tier) deployed uniformly across all three, even though AKS and GKE both offer native alternatives, specifically because a single tool producing comparable cost data across all three clouds is more valuable for cross-cloud comparison than each cloud's best-in-class native tool viewed in isolation. What I would _not_ try to unify is the autoscaling and node-provisioning layer itself — Karpenter, AKS's autoscaler/NAP, and GKE Standard/Autopilot have genuinely different provisioning models, disruption behaviors, and Spot/preemptible notice windows, and forcing artificial uniformity there (e.g., mandating identical consolidation policies across all three) would fight each provider's actual underlying infrastructure rather than working with it. My explicit recommendation would be: unify the governance and cost-visibility layers because they're Kubernetes-native and genuinely portable; accept and document per-cloud differences at the autoscaling/provisioning layer because that's where each cloud's infrastructure primitives are fundamentally distinct, and pretending otherwise creates fragile, leaky abstractions rather than real consistency.
_What the interviewer is probing for:_ Ability to distinguish what's genuinely portable across clouds (Kubernetes-native governance) from what fundamentally isn't (cloud-specific infrastructure provisioning), rather than either over-unifying into a brittle abstraction or giving up on any cross-cloud consistency at all.

## 12. Common Misconceptions

1. **"Once bootstrapped, EKS, AKS, and GKE clusters behave essentially the same."** Autoscaling models, storage defaults, Spot/preemptible notice windows, and native cost tooling all differ meaningfully in steady-state operation, well beyond the bootstrap-time differences covered in §21.
2. **"Karpenter is just EKS's version of Cluster Autoscaler."** It's a genuinely different provisioning model (just-in-time, bin-packing, broader instance-shape selection with active consolidation) rather than a rebrand of the same node-group-scaling approach.
3. **"Spot/preemptible eviction notice windows are the same across clouds."** AWS gives roughly 2 minutes, while Azure and GCP give roughly 30 seconds — a graceful-shutdown handler tuned for one cloud may not have enough time to complete on another.
4. **"GKE Autopilot and Standard just differ in price."** Autopilot removes node-level autoscaling and access concepts entirely in favor of per-Pod billing, a genuinely different operational and cost model, not a pricing toggle on an otherwise identical cluster (also emphasized at bootstrap-time in §21).

## 13. 🔑 Key Takeaways

- EKS's autoscaling and cost tooling (Karpenter, Kubecost/OpenCost) is the most assemble-it-yourself of the three, offering the most flexibility at the cost of more operational setup than AKS's or GKE's more integrated native equivalents.
- AKS and GKE both provide native, namespace-level cost allocation without additional tooling, a genuine operational advantage over EKS's typical reliance on separately-deployed Kubecost/OpenCost.
- Spot/preemptible notice windows differ meaningfully across clouds (AWS ~2 min, Azure/GCP ~30 sec) and must be verified per-provider rather than assumed to transfer.
- Default storage zone-redundancy differs across providers (GKE's regional Persistent Disk option vs. EKS/AKS's single-zone defaults), directly affecting a StatefulSet's real resilience to an availability-zone failure independent of its own spec.
- ResourceQuota/LimitRange (§127) governance is genuinely cloud-agnostic and worth unifying across a multi-cloud fleet; autoscaling/provisioning behavior beneath it is genuinely cloud-specific and should be documented and accepted as different, not forced into artificial uniformity.

## 14. Related Concepts & What's Next

This section extended §21's (Part 3) bootstrap-time EKS/AKS/GKE comparison into steady-state operational nuance — autoscaling models, storage/networking defaults, and native cost tooling — and showed how §127's ResourceQuota/LimitRange governance layer produces different real-world cost and reliability outcomes depending on the cloud-specific infrastructure beneath it. §129, the Part 16 capstone, synthesizes this section together with service mesh (§122–124), multi-cluster architectures (§125), multi-tenancy (§126), and resource governance (§127) into a single enterprise landing-zone reference architecture.

**Next Section:** §129 — `Section-129-Part16-Enterprise-Landing-Zone-Patterns-Kubernetes-Platforms.md`
