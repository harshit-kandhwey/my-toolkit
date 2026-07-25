# Section 32 (Part 4): GKE Autopilot vs. Standard

## 32.1 Definition

**Plain language:** GKE gives you two very different levels of "how much of the machinery do I want to manage myself." **Standard** mode hands you the node pools directly — you pick machine types, size them, and pay for whatever capacity you provision, whether or not it's fully used. **Autopilot** mode takes nodes out of the picture entirely — you describe what your Pods need, Google runs and rightsizes the underlying machines for you, and you pay per Pod resource request rather than per VM.

**Precise:** **GKE Standard** is the traditional operating mode where the customer manages node pools (Compute Engine VM configuration, sizing, and — optionally — autoscaling) while Google manages only the control plane (Section 30). **GKE Autopilot** is a fully managed mode where Google also manages node provisioning, sizing, and the underlying node operating system, billing per vCPU/memory/storage **requested by Pods** rather than per underlying VM, and enforcing a hardened, opinionated cluster configuration (Section 33) by default.

## 32.2 Why It Exists / Problem It Solves

In Standard mode, someone still has to answer questions Kubernetes doesn't answer for you: how big should each node be, how many nodes per pool, when to scale the pool, how to avoid paying for idle capacity sitting between Pod resource requests and actual node capacity. Getting this right — bin-packing Pods efficiently onto right-sized nodes — is a genuine, ongoing operational skill, and getting it wrong either wastes money (over-provisioned, mostly-idle nodes) or causes scheduling failures (under-provisioned capacity).

Autopilot exists to remove that skill requirement entirely: Google observes the aggregate resource requests of scheduled Pods and provisions exactly the node capacity needed to satisfy them, continuously, without the customer ever choosing a machine type or sizing a node pool. This mirrors the same "IaaS vs. more-managed" trade-off explored for compute broadly (GCP Part 1, Section 10) — Autopilot moves GKE further toward the PaaS end of that spectrum without leaving Kubernetes' API surface.

## 32.3 Standard Mode: Node-Pool Control

In Standard mode the customer directly controls:

- **Machine type per node pool** — general-purpose (`e2`, `n2`), compute-optimized, memory-optimized, or GPU/TPU-equipped machine families, chosen per workload.
- **Node pool sizing and count** — how many nodes, how many pools, static or autoscaled via the Cluster Autoscaler (Section 34).
- **Node-level customization** — custom node taints/labels, specific node OS images, DaemonSets running on every node, privileged workloads, host networking, and other node-level Kubernetes features Autopilot restricts or disallows.
- **Billing** — standard Compute Engine billing for the VMs backing each node pool, regardless of how fully the scheduler is packing Pods onto them; idle node capacity between Pod requests and node capacity is still paid for.

This control is exactly what makes Standard the right fit whenever a workload needs something Autopilot's hardened, opinionated defaults don't permit.

## 32.4 Autopilot Mode: Pod-Level Management and Billing

In Autopilot mode:

- **No node pools to configure.** Google provisions nodes automatically, sized to fit scheduled Pods, and manages the node OS, patching, and node-level security hardening (Section 33) without customer input.
- **Billing is per Pod**, based on the vCPU, memory, and ephemeral storage each Pod **requests** (not the underlying node's total capacity), typically at a modest premium over equivalent raw Compute Engine pricing — the premium buys the elimination of bin-packing waste and node operations entirely.
- **A restricted, hardened feature set by default:** privileged containers, host networking/PID/IPC namespaces, and arbitrary DaemonSets are disallowed or tightly constrained, Shielded GKE Nodes and Workload Identity are enabled by default (Section 33), and several security best practices are enforced rather than optional.
- **Pods must specify resource requests** (or Autopilot assigns defaults) since requests directly drive both scheduling and billing — there's no "spare node capacity" to silently absorb an unset request the way there sometimes is in Standard mode.

> ⚠️ **Interview-relevant nuance:** Autopilot billing is per **Pod resource request**, not per node — this is the single most commonly tested distinction between the two modes. A Standard cluster with poor bin-packing can be far more expensive in practice than its sticker machine-type price suggests, while Autopilot's higher per-unit price already prices in that efficiency.

## 32.5 Comparison Table

| Aspect                          | GKE Standard                                                                                               | GKE Autopilot                                                                                       |
| ------------------------------- | ---------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------- |
| Node management                 | Customer manages node pools (machine types, sizing, upgrades of behavior)                                  | Fully managed by Google — no node pools to configure                                                |
| Billing unit                    | Per underlying Compute Engine VM (node), regardless of Pod packing                                         | Per Pod vCPU/memory/storage **request**                                                             |
| Bin-packing efficiency          | Customer's responsibility; idle node capacity is still paid for                                            | Handled automatically by Google; no idle-node waste passed to the customer                          |
| Privileged workloads/DaemonSets | Fully supported                                                                                            | Disallowed or tightly restricted by default                                                         |
| Security hardening defaults     | Optional — customer opts into Shielded Nodes, Workload Identity, etc.                                      | Enabled by default (Section 33)                                                                     |
| GPU/specialized hardware        | Full flexibility across machine families and GPU types                                                     | Supported, but with a narrower, GKE-curated set of configurations                                   |
| Best fit                        | Specialized workloads, fine-grained node control, cost optimization via Spot/committed-use at the VM level | Teams wanting Kubernetes without node operations; variable/bursty workloads; smaller platform teams |

## 32.6 When to Choose Each

- **Choose Standard when:** a workload needs privileged containers, custom DaemonSets, host networking, specific GPU/TPU configurations outside Autopilot's supported set, or when a platform team has the operational maturity to bin-pack efficiently and wants maximum control over cost levers (Spot node pools, committed use discounts on specific machine types).
- **Choose Autopilot when:** the priority is minimizing operational overhead, the workload's resource needs are reasonably standard (no privileged/host-level access required), traffic is bursty enough that manual node-pool sizing would either waste money or risk under-provisioning, or the team is smaller and doesn't want to own node-level security hardening and patching as an ongoing responsibility.
- Many organizations run **both**: Autopilot for the majority of stateless application workloads, and one or more Standard clusters for specialized workloads (GPU training jobs, workloads needing privileged access) that Autopilot's restrictions don't accommodate.

## 32.7 Architecture Diagram

```
STANDARD MODE                              AUTOPILOT MODE
┌─────────────────────────────┐            ┌─────────────────────────────┐
│  Customer chooses:          │            │  Customer declares:         │
│   - machine type            │            │   - Pod resource requests   │
│   - node pool size          │            │   - (that's it)             │
│   - autoscaling policy      │            │                             │
└──────────────┬──────────────┘            └──────────────┬──────────────┘
               │                                          │
               ▼                                          ▼
  ┌──────────────────────────┐            ┌───────────────────────────┐
  │  Node Pool (VMs)         │            │ Google-managed node fleet │
  │  ┌───┐┌───┐┌───┐         │            │ sized exactly to Pod      │
  │  │Pod││Pod││   │ idle    │            │ requests, no idle waste   │
  │  └───┘└───┘└───┘ capacity│            │  ┌───┐┌───┐               │
  │  billed regardless       │            │  │Pod││Pod│               │
  └──────────────────────────┘            │  └───┘└───┘               │
                                          └───────────────────────────┘
   Billing: per VM (node)                    Billing: per Pod request
```

## 32.8 Hands-On Example

**Beginner example — create an Autopilot cluster:**

```bash
gcloud container clusters create-auto my-autopilot-cluster \
  --region=us-central1
```

**Purpose:** Provisions a fully managed Autopilot cluster — no node pool flags exist to specify because there are no node pools to configure; Google handles node provisioning end to end.

**Expected output (abbreviated):**

```
Creating cluster my-autopilot-cluster in us-central1... done.
NAME                    LOCATION     MASTER_VERSION  MASTER_IP     MACHINE_TYPE  NODE_VERSION    NUM_NODES  STATUS
my-autopilot-cluster    us-central1  1.29.x-gke.x    xx.xx.xx.xx   e2-medium     1.29.x-gke.x    3          RUNNING
```

**Intermediate example — compare cluster mode of an existing cluster:**

```bash
gcloud container clusters describe my-cluster \
  --region=us-central1 \
  --format="value(autopilot.enabled)"
```

**Purpose:** Quickly confirms whether an existing cluster is running in Autopilot mode (`True`) or Standard mode (empty/`None`), useful when auditing an unfamiliar project's clusters.

**Expected output:**

```
True
```

## 32.9 Production & Enterprise Usage

- Enterprises commonly default new, general-purpose application clusters to **Autopilot** specifically to remove node-level security hardening and capacity-planning from the platform team's ongoing workload, reserving Standard clusters for a deliberately scoped set of specialized workloads.
- Cost governance teams appreciate Autopilot's per-Pod billing model because it removes an entire class of waste (idle, over-provisioned nodes) that otherwise requires active FinOps monitoring to catch in Standard clusters.
- Migrating an existing Standard workload to Autopilot requires auditing for disallowed node-level features (privileged containers, specific DaemonSets, host networking) before migration — this audit is a standard early step in any Standard-to-Autopilot migration plan.

## 32.10 Common Misconceptions

- **Misconception:** "Autopilot is only for small or non-production workloads." Autopilot is fully supported for production, including at large scale — Google explicitly recommends it as the default mode for most new clusters, not merely a training-wheels option.
- **Misconception:** "Autopilot is always cheaper than Standard." Autopilot's per-unit pricing carries a premium over raw Compute Engine pricing; it's cheaper in practice mainly when it eliminates meaningful bin-packing waste a Standard cluster would otherwise incur. A Standard cluster with excellent bin-packing and Spot/committed-use discounts can beat Autopilot on raw cost for some workloads.

## 32.11 Interview Questions

**🎯 Beginner:** _What is the fundamental billing difference between GKE Standard and GKE Autopilot?_
**Model answer:** Standard bills for the underlying Compute Engine VMs in each node pool, regardless of how efficiently Pods are packed onto them, so idle node capacity is still paid for. Autopilot bills per Pod based on the vCPU, memory, and storage each Pod actually requests, with Google handling node provisioning and packing behind the scenes, so there's no idle-node cost passed to the customer.

**🎯 Intermediate:** _A team wants to run a DaemonSet that needs privileged, host-network access on every node for a custom security agent. Which GKE mode should they use, and why?_
**Model answer:** Standard mode. Autopilot disallows or tightly restricts privileged containers and host networking by default as part of its hardened, opinionated security posture (Section 33), so a workload with a genuine, unavoidable need for privileged host-level access can't run as-is on Autopilot. Standard gives full node-level control needed for this use case; the team should still evaluate whether the agent's requirement can be met with a more restricted permission set that would work under Autopilot before committing to Standard purely for this reason.

**🎯 Senior/Architect:** _An enterprise platform team is deciding whether to standardize all application clusters on Autopilot or keep Standard as the default. Walk through the trade-offs you'd present._
**Model answer:** I'd frame it as an operational-burden-versus-control trade-off rather than a strict cost comparison. Autopilot removes node-pool sizing, bin-packing optimization, node OS patching, and a swath of security hardening decisions from the platform team's ongoing responsibilities, at a per-unit pricing premium that's often offset by eliminating idle-node waste — this is usually the better default for the majority of stateless application workloads, especially where the platform team is smaller or wants to shift focus toward higher-value work. I'd keep Standard available for a deliberately scoped subset of specialized workloads: GPU/TPU training jobs needing configurations outside Autopilot's curated set, any workload with a genuine privileged/host-level access requirement, and cases where a mature FinOps practice can extract real savings from Spot node pools and committed-use discounts at the VM level that would beat Autopilot's per-Pod pricing. I'd avoid a blanket "always Autopilot" or "always Standard" policy — the right default is Autopilot, with Standard as a documented, justified exception path rather than the norm.

## 32.12 Key Takeaways

- 🔑 Standard bills per node (VM) regardless of Pod packing efficiency; Autopilot bills per Pod resource request, eliminating idle-node cost at a per-unit pricing premium.
- 🔑 Autopilot removes node-pool configuration entirely — no machine type, sizing, or node-level autoscaling decisions for the customer to make.
- 🔑 Autopilot enforces a hardened, opinionated default configuration (Shielded Nodes, Workload Identity, restricted privileged/host-level access) that Standard leaves fully optional.
- 🔑 Choose Standard specifically when a workload needs privileged/host-level access, custom DaemonSets, or fine-grained cost control outside Autopilot's supported set — otherwise Autopilot is the recommended default for new clusters.

## 32.13 Related Concepts

GKE architecture and node pools (Section 30), GKE networking and storage (Section 31), GKE security and Workload Identity (Section 33), Cluster Autoscaler and node auto-provisioning (Section 34), and the compute service decision matrix (GCP Part 1, Section 10) all inform the mode choice covered here.
