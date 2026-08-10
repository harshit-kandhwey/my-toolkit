# Section 81 (Part 11): Kubernetes Provisioning via Terraform (EKS/AKS/GKE)

## 1. Definition

**Plain language:** Provisioning a managed Kubernetes cluster with Terraform means declaring the cluster control plane and its worker node groups as resources, the same way you'd declare a VM — except the cluster itself is a higher-level construct that internally depends on the networking ([§79](./Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md)) and IAM ([§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md)) resources already covered in this Part.

**Precise definition:** Each provider exposes a managed Kubernetes offering as a small number of top-level Terraform resources: AWS's `aws_eks_cluster` (control plane) plus `aws_eks_node_group` (managed worker nodes); Azure's `azurerm_kubernetes_cluster`, which — unlike the other two — bundles control plane and a default node pool into a single resource, with `azurerm_kubernetes_cluster_node_pool` for additional pools; and GCP's `google_container_cluster` plus `google_container_node_pool` for additional pools beyond the (deprecated-by-convention) default pool. All three require a pre-existing IAM/RBAC identity for the control plane to operate with (an EKS cluster IAM role, an AKS managed identity, a GKE service account) and a pre-existing network (VPC/VNet + subnets) for the cluster to attach to — Terraform provisioning a Kubernetes cluster is therefore always a composite operation drawing on the networking and IAM foundations from [§79](./Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md) and [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md), not a standalone resource in isolation.

> 💡 **Tip:** Terraform provisions the Kubernetes _infrastructure_ (control plane, node pools, networking, IAM) — it does not, by itself, deploy anything _inside_ the cluster (Deployments, Services, Helm releases). That's a separate concern typically handled by the `kubernetes`/`helm` Terraform providers or, more commonly in practice, a GitOps tool. Conflating "provisioning the cluster" with "deploying workloads to the cluster" is one of the most common scoping mistakes in Kubernetes-on-Terraform designs — [§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md) covers this division of labor in depth.

## 2. Why This Matters

- **Managed Kubernetes is one of the most common "day two" targets after a team's initial VPC/compute provisioning matures**, making this a natural composite exercise applying nearly everything covered so far in Part 11.
- **The three providers' cluster resource shapes differ meaningfully** — Azure's single-resource bundling of control plane and default node pool is structurally different from AWS's and GCP's separate cluster/node-group resources, and this trips up engineers translating a module between clouds.
- **Cluster provisioning is a frequent source of long `apply` times and partial-failure states** (a cluster resource can take 10-20+ minutes to become ready) that engineers need to plan CI/CD pipeline timeouts and retry behavior around.

## 3. Prerequisites and Dependencies

Requires the VPC/subnet provisioning from [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md), [§76](./Section-76-Part11-Azure-Provider-azurerm-Deep-Dive-Resource-Groups-VNets-VMs.md), [§77](./Section-77-Part11-GCP-Provider-google-Deep-Dive-Projects-VPCs-Compute.md), and the peering/security-group patterns from [§79](./Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md) for the network the cluster attaches to; requires the IAM role/RBAC/service-account patterns from [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md) for the control plane and node identities. This section does not cover deploying workloads inside the cluster once created — see [§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md) for the division of labor between Terraform and Kubernetes-native tooling.

## 4. Architecture / Conceptual Diagram

```text
   AWS EKS                                  AZURE AKS
   ───────                                  ─────────
   aws_iam_role.eks_cluster                 azurerm_kubernetes_cluster.this
   (trust: eks.amazonaws.com)               (bundles control plane +
        │                                    default_node_pool in ONE
   aws_eks_cluster.this                      resource; identity block
   (vpc_config: subnet_ids)                  for control plane auth)
        │                                          │
   aws_iam_role.node_group                  azurerm_kubernetes_cluster_
   (trust: ec2.amazonaws.com)               node_pool.additional
        │                                    (extra pools beyond default)
   aws_eks_node_group.default
   (subnet_ids, scaling_config)

   GCP GKE
   ───────
   google_container_cluster.this
   (network, subnetwork; remove_default_
    node_pool = true is standard practice)
        │
   google_service_account.gke_nodes
        │
   google_container_node_pool.primary
   (node_config.service_account = above)

   Common shape across all three:
   Network (§79) ──► Cluster control plane ──► Node pool(s)
                              │
                     IAM/RBAC identity (§80)
                     for both control plane and nodes
```

## 5. Hands-On

### 5.1 AWS EKS: Cluster and Node Group

**Purpose:** Provision an EKS control plane and a managed node group, showing AWS's separated cluster/node-group resources and their distinct IAM roles.

**Syntax:**

```hcl
resource "aws_iam_role" "eks_cluster" {
  name = "eks-cluster-role"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{ Action = "sts:AssumeRole", Effect = "Allow", Principal = { Service = "eks.amazonaws.com" } }]
  })
}

resource "aws_iam_role_policy_attachment" "eks_cluster_policy" {
  role       = aws_iam_role.eks_cluster.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEKSClusterPolicy"
}

resource "aws_eks_cluster" "this" {
  name     = "app-cluster"
  role_arn = aws_iam_role.eks_cluster.arn

  vpc_config {
    subnet_ids = [aws_subnet.private_a.id, aws_subnet.private_b.id]
  }

  depends_on = [aws_iam_role_policy_attachment.eks_cluster_policy]
}

resource "aws_eks_node_group" "default" {
  cluster_name    = aws_eks_cluster.this.name
  node_group_name = "default"
  node_role_arn   = aws_iam_role.eks_node.arn
  subnet_ids      = [aws_subnet.private_a.id, aws_subnet.private_b.id]

  scaling_config {
    desired_size = 2
    max_size     = 4
    min_size     = 1
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # aws_iam_role.eks_cluster will be created
  # aws_eks_cluster.this will be created
  # aws_eks_node_group.default will be created

Plan: 3 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 3 added, 0 changed, 0 destroyed.
# (aws_eks_cluster.this typically takes 10-15 minutes to reach ACTIVE)
```

**Production usage example:** The `depends_on` on the cluster resource explicitly sequences the IAM policy attachment before cluster creation — EKS validates the role's policies at creation time, and without this explicit dependency (the implicit reference alone via `role_arn` doesn't guarantee the _attachment_ has completed), the cluster creation call can fail intermittently.

**Common errors:** Placing node groups in public subnets, or omitting subnet tags EKS expects (`kubernetes.io/cluster/<cluster-name> = shared`) on subnets shared with other AWS load-balancer integrations, are common early misconfigurations that surface later as Kubernetes-level Service/Ingress failures rather than Terraform-level errors.

### 5.2 Azure AKS: Bundled Cluster and Node Pool

**Purpose:** Show Azure's distinctive single-resource bundling of control plane and default node pool.

**Syntax:**

```hcl
resource "azurerm_kubernetes_cluster" "this" {
  name                = "app-aks"
  location            = azurerm_resource_group.main.location
  resource_group_name = azurerm_resource_group.main.name
  dns_prefix          = "app-aks"

  default_node_pool {
    name       = "default"
    node_count = 2
    vm_size    = "Standard_D2_v2"
    vnet_subnet_id = azurerm_subnet.aks.id
  }

  identity {
    type = "SystemAssigned"
  }
}

resource "azurerm_kubernetes_cluster_node_pool" "spot" {
  name                  = "spot"
  kubernetes_cluster_id = azurerm_kubernetes_cluster.this.id
  vm_size               = "Standard_D2_v2"
  node_count            = 1
  priority              = "Spot"
  eviction_policy       = "Delete"
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # azurerm_kubernetes_cluster.this will be created
  # azurerm_kubernetes_cluster_node_pool.spot will be created

Plan: 2 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 2 added, 0 changed, 0 destroyed.
```

**Production usage example:** The single `azurerm_kubernetes_cluster` resource bundling the control plane and `default_node_pool` is convenient for a minimal cluster but constrains what can change on the default pool without forcing cluster-level replacement in some cases — production AKS modules typically treat the default pool as system-workload-only (`only_critical_addons_enabled = true`) and put all real application workloads on additional `azurerm_kubernetes_cluster_node_pool` resources like the spot pool above, which can be resized/replaced independently.

**Common errors:** Certain `default_node_pool` argument changes (like `vnet_subnet_id`) force full cluster replacement since the default pool is embedded in the cluster resource itself — a mistake that would be a simple node-group-level change in AWS/GCP becomes a full cluster recreate in AKS if not anticipated.

### 5.3 GCP GKE: Cluster with Default Pool Removed

**Purpose:** Show GCP's `remove_default_node_pool` convention — provisioning the control plane without its automatically created default pool, then adding an explicitly managed pool.

**Syntax:**

```hcl
resource "google_container_cluster" "this" {
  name     = "app-gke"
  location = "us-central1"
  network  = google_compute_network.vpc.id
  subnetwork = google_compute_subnetwork.us_central.id

  remove_default_node_pool = true
  initial_node_count       = 1
}

resource "google_service_account" "gke_nodes" {
  account_id = "gke-node-sa"
}

resource "google_container_node_pool" "primary" {
  name       = "primary-pool"
  cluster    = google_container_cluster.this.name
  location   = google_container_cluster.this.location
  node_count = 2

  node_config {
    machine_type    = "e2-medium"
    service_account = google_service_account.gke_nodes.email
    oauth_scopes    = ["https://www.googleapis.com/auth/cloud-platform"]
  }
}
```

**Example usage and expected output:**

```bash
$ terraform apply
  # google_container_cluster.this will be created
  # google_service_account.gke_nodes will be created
  # google_container_node_pool.primary will be created

Plan: 3 to add, 0 to change, 0 to destroy.
Apply complete! Resources: 3 added, 0 changed, 0 destroyed.
```

**Production usage example:** `remove_default_node_pool = true` combined with `initial_node_count = 1` (required by the API even though the pool is immediately removed) is the standard, widely documented pattern — it avoids being stuck with an unmanaged, un-tunable default pool whose machine type and scaling can't be controlled the way an explicit `google_container_node_pool` resource can.

**Common errors:** Omitting `remove_default_node_pool` (leaving the provider default of `false`) creates a default pool that then coexists with any explicitly declared pools, doubling node count and cost unexpectedly compared to what the configuration visually seems to describe.

## 6. Production Usage Notes

- Cluster `apply` times of 10-20+ minutes are normal on all three providers — CI/CD pipeline timeouts and `terraform apply` invocations in automation must account for this, and a `plan` that looks trivial (one cluster resource) can still be the longest-running step in a pipeline.
- All three providers support cluster upgrade via changing a `kubernetes_version`-equivalent argument in place, but in-place version upgrades still carry real workload-disruption risk during node pool rotation — this is a Kubernetes operational concern layered on top of the Terraform provisioning concern.
- Node pool sizing/scaling is frequently better managed by the Kubernetes-native autoscaler (Cluster Autoscaler, or each provider's managed autoscaling feature) than by repeatedly changing Terraform's `desired_size`/`node_count` — treating Terraform as the sole source of truth for node count fights with autoscaling in practice; most production setups let Terraform set min/max bounds and let the cluster-native autoscaler operate within them.

## 7. Security Considerations

- Cluster control-plane API endpoints should be private (or IP-allowlisted) by default in production — `endpoint_public_access` (EKS), API server access restriction settings (AKS), and `private_cluster_config` (GKE) all exist specifically to avoid exposing the Kubernetes API to the public internet.
- Node identities (the EKS node IAM role, the AKS node pool's identity, the GKE node service account) should follow the same least-privilege discipline from [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md) — a common mistake is granting the node identity broad cluster-admin-equivalent cloud IAM permissions "to avoid debugging access issues," which defeats the purpose of workload identity scoping.
- Workload Identity (GKE's and EKS's terms for binding Kubernetes service accounts to cloud IAM identities, IRSA on AWS specifically) should be used for in-cluster workloads needing cloud API access, rather than granting broad permissions to the node's own identity that every pod on that node would then inherit.

## 8. Common Troubleshooting Scenarios

| Symptom                                                               | Likely Cause                                                                  | Resolution Path                                                                         |
| --------------------------------------------------------------------- | ----------------------------------------------------------------------------- | --------------------------------------------------------------------------------------- |
| EKS cluster creation fails intermittently referencing IAM permissions | Cluster creation raced ahead of the IAM policy attachment completing          | Add explicit `depends_on` from the cluster resource to the policy attachment resource   |
| AKS node pool change forces full cluster recreation                   | Changed argument lives on the embedded `default_node_pool` block              | Move application workloads to separate `azurerm_kubernetes_cluster_node_pool` resources |
| GKE cluster has double the expected node count                        | `remove_default_node_pool` left at default `false` alongside explicit pools   | Set `remove_default_node_pool = true` and manage all pools explicitly                   |
| `apply` appears to hang for 15+ minutes on a cluster resource         | Normal — managed Kubernetes control planes take significant time to provision | No action needed; ensure CI/CD timeouts account for this baseline duration              |

## 9. Best Practices

- Treat the default node pool (AKS) or default pool (GKE, unless removed) as reserved for system workloads only; put application workloads on explicitly managed, independently scalable pools.
- Let the Kubernetes-native autoscaler manage live node count within Terraform-declared min/max bounds rather than fighting it with repeated Terraform-driven scaling changes.
- Restrict control-plane API access to private networks or allowlisted IP ranges by default across all three providers.

## 10. Common Anti-Patterns / Mistakes

- **Using Terraform to also manage in-cluster Kubernetes objects (Deployments, Services) via the `kubernetes`/`helm` providers in the same state as the cluster infrastructure.** This tightly couples infrastructure and application deployment lifecycles and is generally discouraged in favor of a clean split — Terraform provisions the cluster, a separate GitOps/CD tool deploys workloads ([§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md)).
- **Granting node identities broad cloud IAM permissions** instead of using Workload Identity/IRSA to scope permissions to individual workloads, meaning every pod on a node inherits the node's full permission set.
- **Assuming AKS's node pool model works like EKS/GKE's**, and being surprised when a "simple" default-pool argument change forces a full cluster replacement due to AKS's bundled resource structure.

## 11. Interview Questions

**🎯 Beginner:** _"What does Terraform provision when you create an EKS, AKS, or GKE cluster, and what does it NOT provision?"_
**Model answer:** Terraform provisions the cluster infrastructure — the control plane and node pools/groups, plus the networking and IAM resources they depend on. It does not, by itself, deploy anything running inside the cluster — Deployments, Services, Ingresses, or Helm releases are a separate concern, typically handled by `kubectl`, Helm, or a GitOps tool, not by the same Terraform apply that created the cluster.
_What the interviewer is probing for:_ Correct scoping of what "provisioning a Kubernetes cluster" actually means in Terraform terms, avoiding the common conflation with workload deployment.

**🎯 Intermediate:** _"How does Azure AKS's Terraform resource structure differ from AWS EKS's or GCP GKE's, and what practical consequence does that have?"_
**Model answer:** AKS bundles the control plane and a default node pool into a single `azurerm_kubernetes_cluster` resource, with the `default_node_pool` block embedded inside it. EKS and GKE both separate the cluster (`aws_eks_cluster`/`google_container_cluster`) from its node group/pool (`aws_eks_node_group`/`google_container_node_pool`) as independent resources. The practical consequence is that certain changes to AKS's embedded default pool can force replacement of the entire cluster resource, where an equivalent node-group-level change in EKS or GKE only affects that node group — production AKS modules typically avoid running application workloads on the default pool for exactly this reason.
_What the interviewer is probing for:_ Concrete awareness of a real structural difference with a real operational consequence, not just "they're all a bit different."

**🎯 Senior:** _"A team's GKE cluster ended up with twice the expected number of nodes and double the compute cost after what looked like a routine `apply`. What likely happened, and how do you prevent recurrence?"_
**Model answer:** Almost certainly `remove_default_node_pool` was left at its default `false` while the configuration also declared an explicit `google_container_node_pool` — GKE creates the automatic default pool (sized by `initial_node_count`) _in addition to_ any explicitly declared pools, since nothing in the configuration told it to remove the default. The fix is setting `remove_default_node_pool = true` on the cluster resource so only explicitly declared pools exist. To prevent recurrence structurally, this should be enforced via a linting rule (tflint custom rule or a policy-as-code check, [§86](../Part12/Section-86-Part12-Sentinel-and-OPA-Policy-as-Code.md)/[§96](../Part13/Section-96-Part13-Static-Analysis-and-Security-Scanning-tfsec-Checkov-Terrascan.md)) flagging any `google_container_cluster` resource missing `remove_default_node_pool = true`, since this is a well-known, easily automatable check rather than something to rely on code review catching manually every time.
_What the interviewer is probing for:_ Specific, first-hand-sounding knowledge of this well-documented GKE gotcha, plus a systemic (linting/policy) rather than purely manual prevention approach.

**🎯 Architect:** _"You're deciding whether cluster autoscaling should be driven by Terraform (changing `desired_size`/`node_count` on a schedule or via CI) or by each provider's native cluster autoscaler. Make the case for your recommendation."_
**Model answer:** Terraform-driven scaling and a live cluster autoscaler fundamentally conflict if both try to own the same value: the autoscaler adjusts node count continuously based on real-time pod scheduling pressure, while Terraform's state only reflects node count as of the last `apply` — the next `apply` after the autoscaler has changed things will show a spurious diff trying to revert node count back to whatever Terraform last declared, fighting the autoscaler's decisions. The correct division of labor is for Terraform to own the _bounds_ (min/max size on the node group/pool) and static configuration (machine type, network attachment, labels/taints), while the provider-native autoscaler owns the live count within those bounds — this is directly analogous to the general principle from [§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md) (Terraform for infrastructure shape, a runtime-aware system for runtime-responsive behavior). The one exception worth calling out is genuinely static or rarely-changing capacity needs (a small, fixed-size batch-processing node pool with no autoscaling requirement at all), where Terraform-managed fixed `node_count` with no autoscaler involved is simpler and appropriate — the recommendation isn't "always use the autoscaler," it's "don't let both systems try to own live scaling of the same pool simultaneously."
_What the interviewer is probing for:_ Understanding of the ownership-conflict failure mode between declarative infrastructure state and a live, continuously reconciling system, and the ability to draw a clean division of responsibility rather than defaulting dogmatically to one tool.

## 12. Common Misconceptions

1. **"Terraform provisioning a Kubernetes cluster also deploys the applications that will run on it."** It provisions the cluster infrastructure only; workload deployment is a separate concern, typically handled outside the same Terraform state ([§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md)).
2. **"All three providers structure cluster and node pool resources the same way."** AKS bundles control plane and default node pool into one resource; EKS and GKE keep them separate.
3. **"Terraform should continuously manage live node count for autoscaling."** This conflicts with each provider's native cluster autoscaler; Terraform should own min/max bounds and static config, not live count, when an autoscaler is in use.
4. **"GKE's default node pool is harmless to leave in place alongside explicit pools."** It silently doubles node count and cost unless explicitly removed via `remove_default_node_pool = true`.

## 13. 🔑 Key Takeaways

- Managed Kubernetes provisioning is a composite operation drawing directly on the networking ([§79](./Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md)) and IAM ([§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md)) patterns already established in this Part — it is not a standalone resource type.
- AKS uniquely bundles control plane and default node pool into one resource; EKS and GKE keep cluster and node group/pool as separate, independently manageable resources.
- `remove_default_node_pool = true` is the standard, necessary GKE convention to avoid unintentionally running two node pools.
- Cluster provisioning takes materially longer than most other resources (10-20+ minutes) and pipelines must account for this.
- Terraform should own static configuration and scaling bounds; live autoscaling within those bounds is better left to each provider's native cluster autoscaler to avoid ownership conflicts.

## 14. Related Concepts & What's Next

[§79](./Section-79-Part11-Networking-as-Code-Peering-Subnets-Security-Groups.md) and [§80](./Section-80-Part11-IAM-as-Code-Across-Providers.md) supplied the networking and IAM foundations this composite section built directly on top of. [§111](../Part15/Section-111-Part15-Terraform-Ansible-Kubernetes-Division-of-Labor.md) covers the Terraform/Kubernetes/Ansible division of labor referenced throughout this section's production notes and architect answer in full depth. [§82](./Section-82-Part11-Multi-Region-and-Multi-Account-Subscription-Project-Patterns.md) now moves from a single cluster/region view to designing across multiple regions and multiple accounts/subscriptions/projects — the natural next scaling dimension after a single working environment like the one built across [§75](./Section-75-Part11-AWS-Provider-Deep-Dive-VPC-EC2-S3-IAM.md)-[§81](./Section-81-Part11-Kubernetes-Provisioning-via-Terraform-EKS-AKS-GKE.md).

**Next Section:** [§82](./Section-82-Part11-Multi-Region-and-Multi-Account-Subscription-Project-Patterns.md) — `Section-82-Part11-Multi-Region-and-Multi-Account-Subscription-Project-Patterns.md`
