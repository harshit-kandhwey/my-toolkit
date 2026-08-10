# Section 111 (Part 15): Terraform + Ansible + Kubernetes: Division of Labor in a Full Stack

## 1. Definition

**Plain language:** A real production stack rarely uses just one tool. Terraform, Ansible, and Kubernetes each do a genuinely different job, and understanding exactly where one tool's responsibility ends and the next begins — rather than reaching for whichever tool is most familiar — is what separates a coherent full-stack design from an accumulation of overlapping, redundant automation.

**Precise definition:** **Terraform** operates at the **infrastructure provisioning layer**: it is declarative and state-driven, understands a dependency graph of cloud/infrastructure resources ([§11](../Part2/Section-11-Part2-The-Resource-Graph-Dependency-Resolution-and-DAG-Construction.md)), and creates, modifies, or destroys the compute, network, storage, and IAM primitives that everything else runs on top of. **Ansible** operates at the **configuration management layer**: it is procedural (tasks execute in the order written, per play) and agentless (it connects over SSH/WinRM to targets and runs modules remotely, with no persistent daemon required on managed nodes), and it configures the software state of already-provisioned machines — installing packages, templating config files, managing services, applying OS-level hardening — in an ordered, multi-step way that suits imperative, sequential logic well. **Kubernetes** operates at the **application workload orchestration layer**: it is declarative, like Terraform, but reconciles continuously against a live cluster (not on-demand at `plan`/`apply` time), and its job is running, scaling, healing, and networking containerized application workloads once compute already exists — it does not provision the underlying VMs or networks itself. The three layers stack: Terraform provisions the substrate (including, often, the Kubernetes cluster itself via [§81](../Part11/Section-81-Part11-Kubernetes-Provisioning-via-Terraform-EKS-AKS-GKE.md)), Ansible (optionally) configures machines that aren't purely container hosts, and Kubernetes orchestrates what runs on top.

> 💡 **Tip:** The cleanest single test for "which tool owns this" is: does the thing being managed have a _lifecycle independent of the underlying compute_ (an application that gets deployed, scaled, and rolled back many times without the VM/node ever changing) or is it _part of provisioning or preparing that compute in the first place_ (the VM existing at all, or the OS packages it needs before anything can run on it)? The former is Kubernetes' (or, for non-containerized workloads, sometimes still Ansible's) job. The latter is Terraform's, with Ansible sometimes bridging the gap between "VM exists" and "container runtime/cluster agent is ready."

## 2. Why This Matters

- **Using the wrong tool for a layer creates real, ongoing pain**, not just stylistic untidiness — provisioning infrastructure imperatively via Ansible playbooks loses Terraform's dependency-graph safety and idempotent diffing; managing rapidly-changing application deployments via Terraform's Kubernetes provider loses Kubernetes' continuous reconciliation and rolling-update machinery.
- **The boundaries genuinely blur in specific, well-known places**, and knowing exactly where — rather than pretending the division is perfectly clean — is what separates an accurate mental model from a caricature.
- **Full-stack interview and architecture-design questions routinely probe this boundary directly**, because it's one of the most common real design decisions a platform or DevOps engineer makes, and a vague or hand-wavy answer signals shallow hands-on experience with more than one of these tools.
- **Handoff points between tools are where automation pipelines most often break** — Terraform provisioning a VM, then failing to hand off cleanly to Ansible for configuration, or a Kubernetes cluster provisioned by Terraform having its node pools drift out of sync with what Terraform thinks exists — understanding the boundary is what lets these handoffs be designed deliberately instead of discovered as bugs.
- **Team ownership and tooling investment decisions depend on this.** An organization decides which team owns which layer, which CI pipelines exist for which tool, and which skills to hire for, largely based on a clear model of what each tool is actually responsible for.

## 3. Prerequisites and Dependencies

This section assumes the Terraform-side material from across this roadmap, especially provisioner alternatives ([§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md), which specifically discusses handoff to configuration management and `cloud-init`/`user_data`), Kubernetes provisioning via Terraform ([§81](../Part11/Section-81-Part11-Kubernetes-Provisioning-via-Terraform-EKS-AKS-GKE.md)), and the earlier provisioning-vs.-configuration-management distinction ([§3](../Part1/Section-03-Part1-Terraform-vs-Configuration-Management-Ansible-Puppet-Chef.md), which drew this same line at the very start of the roadmap in less depth). For Ansible specifics beyond what's summarized here, see the Ansible knowledge base roadmap; for Kubernetes specifics, see the Kubernetes knowledge base at `../../../12. Kubernetes/`. Neither is duplicated here — this section focuses specifically on the boundary and handoff, not on teaching either tool.

## 4. Architecture / Conceptual Diagram

```text
FULL-STACK DIVISION OF LABOR

┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 3: APPLICATION WORKLOAD ORCHESTRATION — Kubernetes           │
│  Declarative, CONTINUOUSLY reconciling against live cluster state   │
│  Deployments, Services, Ingress, HPA, rolling updates, self-healing │
│  Lifecycle: independent of underlying nodes — pods reschedule,      │
│  scale, and roll out without touching the VMs beneath them          │
└─────────────────────────────────────────────────────────────────────┘
                                  ▲
                    runs on top of a cluster that exists
                                  │
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 2: CONFIGURATION MANAGEMENT — Ansible (where still needed)   │
│  Procedural, agentless (SSH), ORDERED multi-step OS-level tasks     │
│  Installing container runtime/kubelet, OS hardening, non-container  │
│  workloads (legacy VMs, bastion hosts, DB servers not in K8s)       │
│  Lifecycle: runs against already-provisioned machines, prepares     │
│  or maintains their software state                                  │
└─────────────────────────────────────────────────────────────────────┘
                                  ▲
                    configures machines that exist
                                  │
┌─────────────────────────────────────────────────────────────────────┐
│  LAYER 1: INFRASTRUCTURE PROVISIONING — Terraform                   │
│  Declarative, state-driven, ON-DEMAND reconciliation (plan/apply)   │
│  VPCs, subnets, VMs/node pools, IAM, the EKS/AKS/GKE cluster        │
│  itself (§81), load balancers, DNS                                  │
│  Lifecycle: the substrate everything else runs on                   │
└─────────────────────────────────────────────────────────────────────┘

WHERE THE LINES BLUR:

  Terraform's `kubernetes` / `helm` providers CAN create K8s resources
  (Deployments, Helm releases) directly from HCL — technically possible,
  usually the WRONG tool for ongoing application deployment: Terraform
  state now has to track fast-changing application resources it wasn't
  designed for, losing Kubernetes' native rollout/rollback machinery.
  Common, defensible exception: using Terraform for a cluster's own
  foundational, slow-changing add-ons (ingress controller, CNI plugin)
  installed once alongside cluster creation — not for the applications
  that team ships weekly.

  cloud-init / user_data (set BY Terraform, executed by the cloud AT
  boot) is a lightweight alternative to Ansible for simple, one-shot
  bootstrap tasks — installing a kubelet and joining a cluster, for
  instance — without a full configuration-management tool at all.
```

## 5. Hands-On

### 5.1 Terraform Provisioning, Then Handing Off to Ansible

**Purpose:** Show a clean, deliberate handoff from Terraform-provisioned infrastructure to Ansible-driven configuration, using a dynamic inventory rather than a provisioner ([§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) covers why provisioners are the wrong mechanism for this).

**Syntax:**

```hcl
resource "aws_instance" "app" {
  count         = 3
  ami           = var.ami_id
  instance_type = "t3.medium"
  tags = {
    Name = "app-${count.index}"
    Role = "app-server"
  }
}

output "app_server_ips" {
  value = aws_instance.app[*].public_ip
}
```

```bash
# Ansible consumes Terraform's output via a dynamic inventory plugin
# (aws_ec2 inventory plugin filtering on the "Role: app-server" tag)
# rather than Terraform shelling out to ansible-playbook via local-exec
ansible-playbook -i inventory.aws_ec2.yml site.yml
```

**Example usage and expected output:**

```bash
$ terraform apply
Apply complete! Resources: 3 added, 0 changed, 0 destroyed.

Outputs:
app_server_ips = [
  "54.212.10.1",
  "54.212.10.2",
  "54.212.10.3",
]

$ ansible-playbook -i inventory.aws_ec2.yml site.yml
PLAY [app_server] *****************************************
TASK [Gathering Facts] ************************************
ok: [54.212.10.1]
ok: [54.212.10.2]
ok: [54.212.10.3]
TASK [Install and configure nginx] **************************
changed: [54.212.10.1]
changed: [54.212.10.2]
changed: [54.212.10.3]
PLAY RECAP ***************************************************
54.212.10.1 : ok=4 changed=1 unreachable=0 failed=0
```

**Production usage example:** CI/CD pipelines typically run these as two explicit, separately-owned stages — a `terraform apply` stage followed by an `ansible-playbook` stage that queries the cloud provider directly for currently-running, appropriately-tagged instances (a dynamic inventory) rather than depending on Terraform to have called Ansible itself — keeping each tool's failure modes and retries independent and each tool doing only the job it's actually good at.

**Common errors:** Using a `local-exec` provisioner inside the `aws_instance` resource to shell out directly to `ansible-playbook` ([§64](../Part9/Section-64-Part9-local-exec-and-remote-exec-Provisioners.md)) reintroduces the imperative, non-idempotent behavior [§1](../Part1/Section-01-Part1-What-Infrastructure-as-Code-Is-Declarative-vs-Imperative.md) and [§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md) both warn against — a failed or partial Ansible run inside a provisioner leaves Terraform's own state ambiguous about whether the resource succeeded, and re-running `apply` doesn't naturally re-run just the configuration step the way re-running `ansible-playbook` independently does.

### 5.2 Terraform Provisioning a Kubernetes Cluster, Then Handing Off to Kubernetes-Native Tooling

**Purpose:** Show the correct layering — Terraform creates the cluster ([§81](../Part11/Section-81-Part11-Kubernetes-Provisioning-via-Terraform-EKS-AKS-GKE.md)), a Kubernetes-native tool deploys applications onto it, not Terraform's `kubernetes` provider for ongoing app deployment.

**Syntax:**

```hcl
module "eks" {
  source  = "terraform-aws-modules/eks/aws"
  version = "~> 20.0"

  cluster_name    = "prod-cluster"
  cluster_version = "1.29"
  # node groups, networking, IAM, etc.
}

output "cluster_endpoint" {
  value = module.eks.cluster_endpoint
}
```

```bash
# Kubernetes-native tooling takes over from here — NOT more Terraform
aws eks update-kubeconfig --name prod-cluster
kubectl apply -f k8s-manifests/
# or: helm upgrade --install app ./charts/app
```

**Example usage and expected output:**

```bash
$ terraform apply
module.eks.aws_eks_cluster.this: Creation complete after 11m32s
Apply complete! Resources: 47 added, 0 changed, 0 destroyed.

$ aws eks update-kubeconfig --name prod-cluster
Updated context arn:aws:eks:us-east-1:...:cluster/prod-cluster in ~/.kube/config

$ kubectl apply -f k8s-manifests/
deployment.apps/app created
service/app created

$ kubectl rollout status deployment/app
deployment "app" successfully rolled out
```

**Production usage example:** The cluster infrastructure (node pools, networking, IAM roles for service accounts) stays in Terraform's slow-changing, plan-reviewed workflow ([§81](../Part11/Section-81-Part11-Kubernetes-Provisioning-via-Terraform-EKS-AKS-GKE.md)), while application deployments go through a CI/CD pipeline that runs `kubectl`/`helm`/a GitOps controller (Argo CD, Flux) against the cluster — the application deployment cadence (potentially many times a day) is completely decoupled from the infrastructure change cadence (weekly or less), which is exactly the separation this layering is meant to produce.

**Common errors:** Managing a `kubernetes_deployment` resource directly in Terraform for an application that gets redeployed frequently — every application release then requires a full `terraform plan`/`apply` cycle, loses Kubernetes' native rolling-update and automatic rollback behavior, and puts fast-changing application state inside a state file designed and optimized for much slower-changing infrastructure.

## 6. Production Usage Notes

- **Ansible's role is shrinking, not disappearing, in container-centric stacks.** In an organization running everything in Kubernetes, Ansible's remaining job is often narrow: bootstrapping the OS/kubelet/container runtime on cluster nodes before they join the cluster (sometimes now replaced entirely by cloud-init/`user_data` or immutable, pre-baked AMIs), plus anything genuinely outside Kubernetes — bastion hosts, standalone database VMs, legacy non-containerized services.
- **Immutable infrastructure patterns push work from Ansible toward Terraform+image-baking.** Instead of Ansible configuring a long-lived VM's software state repeatedly over its lifetime, many organizations bake a fully-configured machine image once (via Packer, often itself invoking Ansible or shell provisioners at build time) and have Terraform simply provision new instances from that pre-baked image — shifting Ansible's role from "configure this specific running server" to "define what goes into the image template."
- **The Terraform Kubernetes/Helm providers have a legitimate, narrow use case**: provisioning a cluster's foundational, slow-changing add-ons (an ingress controller, a CNI plugin, cluster-autoscaler) at the same time as the cluster itself, so a single `apply` produces a fully-functional cluster ready for application teams — this is different from using the same providers for the applications teams deploy weekly, which is where the boundary genuinely should hold.
- **GitOps controllers (Argo CD, Flux) sit conceptually where "Kubernetes-native CI/CD" belongs**, continuously reconciling manifests from Git against the live cluster — this is the natural evolution of the "Kubernetes owns the application layer" boundary, extending Kubernetes' own continuous-reconciliation model to the deployment pipeline itself, rather than either Terraform or ad hoc `kubectl apply` scripting owning it.

## 7. Security Considerations

- Terraform's execution role ([§95](../Part13/Section-95-Part13-Least-Privilege-IAM-for-Terraform-Execution-Roles.md)) provisioning cluster infrastructure typically needs broad cloud-account permissions (create VPCs, IAM roles, EKS clusters); Kubernetes-native deployment tooling should use narrower, cluster-scoped RBAC permissions rather than reusing the same broad cloud credentials — conflating the two means a compromised deployment pipeline has far more blast radius than it needs.
- Ansible's SSH-based, agentless model means managed-node access hinges entirely on SSH key/credential hygiene — rotating and scoping those credentials (often via a bastion host or Vault-issued short-lived SSH certificates, tying back to [§93](../Part13/Section-93-Part13-Integrating-HashiCorp-Vault-with-Terraform.md)) matters as much as any Terraform- or Kubernetes-specific credential concern.
- Secrets that need to reach a running container (a database password an application needs at runtime) generally should NOT flow through Terraform state ([§92](../Part13/Section-92-Part13-Secrets-in-State-Risks-and-Mitigations.md)) or a baked machine image at all — Kubernetes Secrets (ideally backed by an external secrets operator pulling from a cloud-native secrets manager, [§94](../Part13/Section-94-Part13-Cloud-Native-Secrets-Managers-AWS-Azure-GCP.md)) or Ansible Vault for non-containerized targets are the appropriate mechanism for the layer that actually needs the secret at runtime, not the provisioning layer.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                                              | Likely Cause                                                                                          | Resolution Path                                                                                                                                         |
| ---------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------- |
| A newly-provisioned VM isn't ready when Ansible tries to connect                                     | Terraform's `apply` completed but the instance's SSH daemon/cloud-init hasn't finished booting yet    | Add a readiness wait/health check between pipeline stages rather than a fixed sleep; avoid a `local-exec` provisioner masking the real dependency       |
| Application deployments via `kubernetes_deployment` in Terraform are slow and risky                  | Using Terraform for a fast-changing application layer that belongs to Kubernetes-native tooling       | Migrate application deployment to `kubectl`/Helm/a GitOps controller; keep Terraform scoped to cluster infrastructure and slow-changing add-ons         |
| Ansible playbook fails against nodes that Terraform's state considers healthy                        | Drift between Terraform's provisioning-time view and the node's actual current software state         | Re-run Ansible independently (it's idempotent per-task); investigate whether immutable image baking would reduce this class of drift                    |
| A Kubernetes cluster node pool provisioned by Terraform doesn't match what Kubernetes itself reports | Terraform state and the cluster autoscaler both trying to control node pool size, fighting each other | Let Kubernetes' autoscaler own dynamic scaling; have Terraform manage only the node pool's static configuration/min-max bounds, not live instance count |

## 9. Best Practices

- Match each concern to the layer it structurally belongs to: infrastructure existing at all → Terraform; ordered OS-level setup on machines that aren't purely container hosts → Ansible; running, scaling, and healing containerized applications → Kubernetes.
- Use explicit, independently-owned handoffs between tools (separate CI/CD pipeline stages, dynamic inventories, cluster kubeconfig retrieval) rather than one tool shelling out to invoke another via a provisioner.
- Reserve Terraform's Kubernetes/Helm providers for a cluster's own foundational, slow-changing add-ons installed alongside cluster creation — not for the application workloads teams deploy on their own, faster cadence.
- Consider shrinking Ansible's footprint over time toward image-baking (Packer) and cloud-init for simple bootstrap tasks as a stack becomes more container-centric, without assuming Ansible disappears entirely — non-containerized systems still need it.

## 10. Common Anti-Patterns / Mistakes

- **Managing fast-changing application deployments through Terraform's Kubernetes/Helm providers** — this is the most common and most damaging boundary violation named explicitly in this section's brief, forcing application-release cadence into infrastructure's slower, plan-reviewed workflow and losing Kubernetes' native rollout/rollback machinery.
- **Using `local-exec`/`remote-exec` provisioners to invoke Ansible from inside Terraform**, reintroducing imperative, non-idempotent behavior into an otherwise declarative provisioning step ([§63](../Part9/Section-63-Part9-Provisioners-Overview-and-Why-HashiCorp-Discourages-Them.md), [§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md)) and creating ambiguous state on partial failure.
- **Treating Ansible as the tool for ongoing container orchestration** — deploying and managing containers via Ansible playbooks instead of Kubernetes forfeits scheduling, self-healing, service discovery, and rolling updates that Kubernetes provides natively and Ansible has no equivalent for.
- **Letting Terraform and a Kubernetes cluster autoscaler both try to own live node count**, producing a persistent, confusing fight between the two systems' respective views of the "correct" state.
- **Assuming the division of labor is a strict, unbending law rather than a design heuristic** — the legitimate exceptions (Terraform managing foundational cluster add-ons, cloud-init as a lightweight Ansible substitute for simple bootstrap) are real and defensible when applied narrowly; the anti-pattern is applying them broadly, to the fast-changing application layer, not using them at all.

## 11. Interview Questions

**🎯 Beginner:** _"In one sentence each, what does Terraform do, what does Ansible do, and what does Kubernetes do?"_
**Model answer:** Terraform provisions infrastructure — the VMs, networks, and cloud resources that everything else runs on. Ansible configures software on machines that already exist, running ordered, agentless setup tasks over SSH. Kubernetes orchestrates containerized applications once compute exists, continuously scheduling, scaling, and healing workloads on top of whatever nodes it has.
_What the interviewer is probing for:_ Whether the candidate has a basic, accurate sense of the three layers rather than treating the tools as interchangeable.

**🎯 Intermediate:** _"Why is Terraform generally considered the wrong tool for deploying application updates to a running Kubernetes cluster, even though its Kubernetes provider technically supports it?"_
**Model answer:** Terraform's `kubernetes_deployment` resource can technically create and update Kubernetes objects, but doing so for frequently-changing applications forces every deployment through a full `plan`/`apply` cycle, puts fast-changing application state inside a state file designed for much slower-changing infrastructure, and forfeits Kubernetes' own native rolling-update, health-check-driven rollback, and continuous reconciliation behavior — Kubernetes is specifically built to manage that lifecycle itself, on-cluster, without needing an external plan/apply step for every change. It's technically possible, but it's using an infrastructure-layer tool for an application-layer job it isn't optimized for.
_What the interviewer is probing for:_ Understanding of the specific mechanical reasons (state file mismatch, lost native rollout features) rather than a vague "it's just not what Terraform is for."

**🎯 Senior:** _"You're bootstrapping new Kubernetes worker nodes. Would you use Ansible, cloud-init/user_data, or a pre-baked image, and how do you decide?"_
**Model answer:** It depends on how much bootstrap logic is needed and how often the base configuration changes. cloud-init/`user_data` (set by Terraform, executed once at boot) is the right choice for simple, one-shot tasks — installing a kubelet and joining a cluster with a handful of commands — without needing a full configuration-management tool. Ansible is a better fit when bootstrap logic is genuinely complex, ordered, and needs conditional branching or idempotent re-application after boot (not just at first boot). A pre-baked image (via Packer, often invoking Ansible or shell provisioners at build time) is the right choice when node bootstrap time matters at scale — baking the kubelet, container runtime, and monitoring agents into the AMI itself means new nodes join the cluster in seconds instead of minutes of runtime configuration, at the cost of needing a rebuild-and-redeploy cycle whenever the baseline configuration changes. In practice, mature Kubernetes platforms tend to converge on the pre-baked-image approach for worker nodes specifically because of that startup-time and consistency benefit, with cloud-init reserved for genuinely small, node-specific runtime parameters.
_What the interviewer is probing for:_ Awareness of the real tradeoffs between the three options and the specific reason (boot-time performance, consistency) mature platforms often prefer pre-baked images for this particular use case.

**🎯 Architect:** _"Design the tool boundaries for a stack that includes: a Kubernetes cluster for containerized microservices, a small fleet of standalone VMs running a legacy monolith that isn't being containerized soon, and shared networking/IAM. Where does each tool's responsibility start and stop?"_
**Model answer:** Terraform owns the entire infrastructure substrate uniformly regardless of what runs on it: the shared VPC/networking, IAM roles and policies, the EKS/AKS/GKE cluster and its node pools ([§81](../Part11/Section-81-Part11-Kubernetes-Provisioning-via-Terraform-EKS-AKS-GKE.md)), and the standalone VM instances for the legacy monolith — all provisioned and change-managed through one consistent, plan-reviewed workflow, ideally with state split ([§109](./Section-109-Part15-Performance-at-Scale-Parallelism-State-Splitting-Large-Graphs.md)) along the cluster/legacy-VM/shared-networking boundary so a change to one doesn't blast-radius into the others. For the legacy monolith's VMs specifically, Ansible owns ongoing configuration management — OS packages, application config templating, service management — since it isn't containerized and won't get Kubernetes' orchestration benefits; this is exactly the kind of ordered, multi-step OS-level task Ansible suits well, and there's no argument for forcing it into Kubernetes prematurely just for tooling uniformity. For the Kubernetes cluster, application teams own their own deployment cadence entirely through Kubernetes-native tooling — Helm charts or manifests deployed via a GitOps controller — with Terraform's involvement limited to the cluster's own foundational add-ons (ingress controller, CNI, cluster-autoscaler configuration) set up once alongside cluster creation, not touched again for ordinary application releases. The explicit design principle communicated to both teams: Terraform's boundary is "does this resource's lifecycle track infrastructure change cadence or application change cadence" — anything on the application cadence, containerized or not, does not belong in Terraform's ongoing management regardless of which specific tool (Kubernetes-native tooling for the microservices, Ansible for the monolith) ends up owning it instead.
_What the interviewer is probing for:_ Ability to design a coherent, justified boundary across a genuinely mixed (containerized plus legacy) real-world stack, not just recite the clean three-layer model for a purely containerized case.

## 12. Common Misconceptions

1. **"Terraform, Ansible, and Kubernetes are competing tools and you pick one."** They solve different problems at different layers and are commonly used together in the same stack; the question is division of labor, not which one "wins."
2. **"Kubernetes replaces the need for Terraform once you're containerized."** Kubernetes orchestrates workloads on top of compute that already exists — something still has to provision the cluster, its nodes, and the surrounding cloud networking/IAM, which is Terraform's job ([§81](../Part11/Section-81-Part11-Kubernetes-Provisioning-via-Terraform-EKS-AKS-GKE.md)), not Kubernetes'.
3. **"Ansible is obsolete now that Kubernetes and immutable infrastructure exist."** Its role has narrowed in container-heavy stacks but remains genuinely necessary for non-containerized systems, cluster node bootstrap in some architectures, and any ordered, multi-step OS-level task that doesn't fit a container's lifecycle model.
4. **"Because Terraform's Kubernetes provider can create Deployments, it's a reasonable default for application deployment."** Technically capable is not the same as well-suited — it's a defensible narrow exception for a cluster's own foundational add-ons, and the wrong default for the application workloads teams ship on their own cadence.

## 13. 🔑 Key Takeaways

- Terraform provisions infrastructure (declarative, state-driven, on-demand reconciliation), Ansible configures software on already-provisioned machines (procedural, agentless, ordered), and Kubernetes orchestrates containerized workloads on top of existing compute (declarative, continuously reconciling).
- The cleanest boundary test is whether something's lifecycle tracks infrastructure change cadence or application change cadence — the latter belongs to Kubernetes-native tooling (or Ansible, for non-containerized systems), not Terraform.
- Terraform's Kubernetes/Helm providers have a narrow, legitimate use for foundational, slow-changing cluster add-ons — using them for ongoing application deployment is the most common and damaging boundary violation.
- Handoffs between tools should be explicit and independently owned (separate pipeline stages, dynamic inventories) rather than one tool shelling out to invoke another via a provisioner.
- Ansible's footprint shrinks but doesn't disappear as stacks become more container-centric — non-containerized systems and cluster-node bootstrap still commonly need it, sometimes alongside or displaced by image-baking and cloud-init.

## 14. Related Concepts & What's Next

[§3](../Part1/Section-03-Part1-Terraform-vs-Configuration-Management-Ansible-Puppet-Chef.md) introduced the provisioning-vs.-configuration-management distinction this section returns to with full production depth. [§68](../Part9/Section-68-Part9-Alternatives-to-Provisioners-cloud-init-user_data-Ansible.md) covers provisioner alternatives, including the cloud-init/Ansible handoff mechanics referenced here. [§81](../Part11/Section-81-Part11-Kubernetes-Provisioning-via-Terraform-EKS-AKS-GKE.md) covers Terraform's Kubernetes cluster provisioning specifically. This section closes Part 15's synthesis of best practices, comparisons, and anti-patterns; Part 16 turns to certification and interview preparation, starting with how the Terraform Associate exam's domains map against everything covered across Parts 1–15.

**Next Section:** [§112](../Part16/Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md) — `Section-112-Part16-Terraform-Associate-Exam-Domain-Breakdown-Time-Management.md`
