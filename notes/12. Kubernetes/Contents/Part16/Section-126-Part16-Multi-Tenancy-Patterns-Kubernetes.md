# Section 126 (Part 16): Multi-Tenancy Patterns in Kubernetes

## 1. Definition

**Plain language:** Multi-tenancy means letting multiple teams, business units, or even external customers share a single Kubernetes cluster while keeping their workloads, data, and blast radius separate from each other — like an apartment building where everyone shares the foundation and utilities but has their own locked unit.

**Precise definition:** Kubernetes multi-tenancy is the practice of isolating **tenants** (a team, application, business unit, or customer) sharing common cluster infrastructure along four independent axes: **API-level isolation** (RBAC, [§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md), controlling who can read/write which objects), **network isolation** (NetworkPolicies, [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md), controlling which Pods can talk to which), **resource isolation** (ResourceQuotas and LimitRanges constraining how much CPU/memory/object-count a tenant can consume, covered in depth in [§127](./Section-127-Part16-Cost-Optimization-Resource-Governance-ResourceQuotas-LimitRanges.md)), and **workload/node isolation** (whether tenants share the same underlying nodes at all, via taints/tolerations or dedicated node pools, versus true physical or control-plane separation). Kubernetes ships no single "multi-tenancy" object — it's a **composition pattern** built from primitives that already exist, and the fundamental architectural decision is which isolation model to adopt: **soft multi-tenancy** (namespace-based, trusted tenants, shared control plane), **hard multi-tenancy** (untrusted tenants, requiring stronger primitives like separate clusters, virtual clusters, or sandboxed runtimes), or **hierarchical namespaces** for structured delegation within one trust domain.

## 2. Why This Matters

- **Namespace boundaries are not security boundaries by default** — a namespace alone provides only a naming/object-organization scope; without RBAC and NetworkPolicies actively layered on top, any Pod in any namespace can, by default, reach any other Pod in the cluster and any identity with broad enough permissions can read across namespaces, making "soft" multi-tenancy a deliberate composition, not a default.
- **The soft-vs-hard tenancy decision is the single most consequential architectural call a platform team makes**, because retrofitting hard isolation (separate clusters, virtual control planes) onto a cluster architected for soft multi-tenancy is a significant re-platforming effort, not a configuration change.
- **This is where [§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md) (RBAC) and [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) (NetworkPolicies) stop being independent concepts and become one composed system** — real multi-tenancy is the demonstration that Kubernetes' security model is additive across multiple primitives, none of which is sufficient alone.

🔑 **Key Takeaway:** Kubernetes has no built-in "tenant" object — multi-tenancy is always a composed pattern layering RBAC ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)), NetworkPolicies ([§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)), ResourceQuotas/LimitRanges ([§127](./Section-127-Part16-Cost-Optimization-Resource-Governance-ResourceQuotas-LimitRanges.md)), and optionally node-level or cluster-level separation on top of namespaces, and the soft-versus-hard trust boundary decision made early drives which of those layers are mandatory versus optional.

## 3. Prerequisites and Dependencies

Builds directly on [§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md) (RBAC Deep Dive, Part 10) for the identity-and-authorization layer of tenant isolation, and [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md) (NetworkPolicies, Part 7) for the network-traffic isolation layer — both are treated here as already-understood primitives being composed into a larger tenancy architecture. Also assumes familiarity with [§125](./Section-125-Part16-Multi-Cluster-Architectures-Federation-Cluster-API.md) (Multi-Cluster Architectures), since "how many clusters" is itself one axis of the tenancy decision.

## 4. Architecture Diagram

```text
                        MULTI-TENANCY ISOLATION AXES
   ┌──────────────────────────────────────────────────────────────────────┐
   │  SOFT MULTI-TENANCY (trusted tenants, shared control plane)          │
   │                                                                      │
   │   Namespace: team-a          Namespace: team-b                       │
   │   ┌────────────────────┐        ┌────────────────────┐               │
   │   │ RoleBinding →      │        │ RoleBinding →      │               │
   │   │  team-a-devs       │        │  team-b-devs       │               │
   │   │ ResourceQuota      │        │ ResourceQuota      │               │
   │   │ NetworkPolicy:     │        │ NetworkPolicy:     │               │
   │   │  deny cross-ns     │        │  deny cross-ns     │               │
   │   │  ingress by default│        │  ingress by default│               │
   │   │ Pods ──┐           │        │ Pods ──┐           │               │
   │   └────────┼───────────┘        └────────┼───────────┘               │
   │            │  BLOCKED by NetworkPolicy   │                           │
   │            └─────────────X───────────────┘                           │
   │                                                                      │
   │   Shared: control plane, kubelet, CNI, node pool (optionally tainted │
   │   per-tenant), cluster-wide CRDs, admission webhooks                 │
   └──────────────────────────────────────────────────────────────────────┘

   ┌───────────────────────────────────────────────────────────────────────┐
   │  HARD MULTI-TENANCY (untrusted tenants)                               │
   │                                                                       │
   │   Option A: Cluster-per-tenant       Option B: Virtual control        │
   │   ┌───────────┐ ┌───────────┐         plane (e.g., vcluster)          │
   │   │ Cluster A │ │ Cluster B │         ┌──────────────────────────┐    │
   │   │ (team-a)  │ │ (team-b)  │         │ Host cluster             │    │
   │   └───────────┘ └───────────┘         │  ┌────────┐ ┌────────┐   │    │
   │   Full isolation, highest cost,       │  │vcluster│ │vcluster│   │    │
   │   highest ops overhead                │  │ team-a │ │ team-b │   │    │
   │                                       │  │(own API│ │(own API│   │    │
   │                                       │  │ server)│ │ server)│   │    │
   │                                       │  └────────┘ └────────┘   │    │
   │                                       │  Pods still land on the  │    │
   │                                       │  shared host cluster's   │    │
   │                                       │  nodes underneath        │    │
   │                                       └──────────────────────────┘    │
   └───────────────────────────────────────────────────────────────────────┘
```

## 5. Hands-On

### 5.1 Soft Multi-Tenancy: Composing RBAC, Quotas, and NetworkPolicy per Namespace

**Purpose:** Build a standard "tenant namespace" bundle that a platform team stamps out for every onboarded team.

**Syntax:**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: team-a
  labels:
    tenant: team-a
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: team-a-full-access
  namespace: team-a
subjects:
  - kind: Group
    name: team-a-developers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole
  name: edit
  apiGroup: rbac.authorization.k8s.io
---
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-cross-namespace
  namespace: team-a
spec:
  podSelector: {}
  policyTypes: [Ingress]
  ingress:
    - from:
        - podSelector: {}
```

**Production usage example:** Platform teams codify this bundle (Namespace + RoleBinding + default-deny NetworkPolicy + ResourceQuota, [§127](./Section-127-Part16-Cost-Optimization-Resource-Governance-ResourceQuotas-LimitRanges.md)) as a single Helm chart or Kustomize base, applied via GitOps whenever a new team is onboarded — turning "create a tenant" into a pull request rather than a manual multi-step runbook, which is both faster and auditable.

**Common errors:** Creating the namespace and RBAC binding but forgetting the default-deny NetworkPolicy, leaving every Pod in the cluster able to reach every other Pod across namespace boundaries regardless of RBAC — RBAC governs the Kubernetes API, not Pod-to-Pod network traffic, and the two must both be applied for namespace isolation to mean anything at the network layer.

### 5.2 Hierarchical Namespaces for Delegated Sub-Tenancy

**Purpose:** Let a platform team delegate namespace-creation authority to a team lead without granting cluster-wide namespace-creation RBAC, using the Hierarchical Namespace Controller (HNC) pattern.

**Syntax:**

```yaml
apiVersion: hnc.x-k8s.io/v1alpha2
kind: SubnamespaceAnchor
metadata:
  name: team-a-staging
  namespace: team-a
```

```bash
kubectl hns tree team-a
kubectl hns set team-a --allowCascadingDeletion
```

**Production usage example:** A platform team grants a business-unit lead admin rights over their top-level namespace (`team-a`) and lets that lead create child namespaces (`team-a-staging`, `team-a-dev`) that automatically inherit RBAC RoleBindings and NetworkPolicies from the parent, without the lead ever needing cluster-admin-level namespace-creation permission.

**Common errors:** Assuming child namespaces created via HNC automatically inherit ResourceQuota limits proportionally — quota inheritance must be explicitly configured (HNC supports quota propagation, but it is not automatic parity with the parent's quota) and is a frequent source of "why did my sub-team consume the entire parent quota" incidents.

### 5.3 Hard Tenancy via Virtual Clusters (vcluster Pattern)

**Purpose:** Give an untrusted or highly-isolated tenant what looks like its own full Kubernetes API server and control plane, while still scheduling its Pods onto a shared underlying host cluster's nodes.

**Syntax:**

```bash
vcluster create team-c-vcluster --namespace host-team-c
vcluster connect team-c-vcluster --namespace host-team-c
kubectl get namespaces   # now shows only team-c-vcluster's own view
```

**Production usage example:** A platform-as-a-service offering selling "your own Kubernetes cluster" to external customers uses vcluster to give each customer an isolated API server, their own CRDs, and their own RBAC root, without provisioning a genuinely separate physical cluster (and its control-plane cost) per customer — while still centrally managing the shared underlying node pool's capacity, patching, and CNI.

**Common errors:** Treating a virtual cluster as equivalent to full hard isolation at the workload-execution level — Pods from different vclusters can still land on the same underlying node and share the same kernel unless the host cluster additionally enforces node-level or sandboxed-runtime isolation (gVisor/Kata, [§115](../Part15/Section-115-Part15-Minimizing-Microservice-Vulnerabilities-SecurityContext-Hardening-gVisor-Kata.md)); vcluster isolates the **control plane and API surface**, not automatically the **container runtime boundary**.

## 6. Production Usage Notes

- The soft-vs-hard decision should be driven by **trust level**, not convenience: internal teams within the same organization who already trust each other's intentions (even if their code quality varies) are typically fine with soft, namespace-based tenancy; external customers, regulatory-isolation requirements, or genuinely adversarial workloads (e.g., running untrusted third-party code) push toward hard tenancy.
- Admission control (OPA Gatekeeper or Kyverno policies) is frequently the missing fourth pillar alongside RBAC/NetworkPolicy/ResourceQuota — without policy enforcement, a tenant with `edit` RBAC can still create Pods that mount host paths, run privileged, or bypass the intended isolation model entirely.
- Cluster-scoped resources (CRDs, StorageClasses, ClusterRoles, admission webhook configurations) sit outside any namespace boundary by definition — a genuinely thorough multi-tenancy review must inventory which cluster-scoped objects a tenant can create or modify, since namespace-scoped RBAC alone says nothing about these.

## 7. Security Considerations

- Shared kernel risk: even with strict RBAC, NetworkPolicy, and quotas, all soft-tenancy Pods on a shared node share the same Linux kernel — a container-escape vulnerability in one tenant's workload is a potential path to every other tenant's workload on that node, which is the fundamental risk hard tenancy (separate clusters, sandboxed runtimes, dedicated node pools) exists to close.
- Default-allow networking is the most common multi-tenancy security gap in the wild: without an explicit default-deny NetworkPolicy per tenant namespace, Kubernetes' default behavior is full any-to-any Pod connectivity, meaning "namespace isolation" without NetworkPolicy is isolation in name only.
- Secrets and ConfigMaps are namespace-scoped by default, but any identity with cluster-wide `get secrets` RBAC (common in poorly-scoped operators or monitoring agents) can read across every tenant's secrets — auditing which ClusterRoles grant cross-namespace secret access is a standard tenancy security review step.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                    | Likely Cause                                                                          | Fix                                                                                                     |
| -------------------------------------------------------------------------- | ------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| Tenant A's Pods can reach Tenant B's Pods despite separate namespaces      | No default-deny NetworkPolicy applied; Kubernetes' default is any-to-any connectivity | Apply a default-deny ingress (and typically egress) NetworkPolicy per tenant namespace                  |
| Team lead can't create a namespace they should be delegated authority over | HNC subnamespace anchor missing, or lead only has RBAC scoped to existing namespaces  | Grant namespace-creation via HNC SubnamespaceAnchor rather than cluster-wide namespace RBAC             |
| Sub-team's workloads consumed the entire parent team's resource budget     | Quota not propagated/configured on the child namespace under hierarchical namespaces  | Explicitly configure HNC quota propagation or apply a distinct ResourceQuota per child namespace        |
| Tenant Pod created with `hostPath` mount despite "edit" RBAC only          | No admission policy (Gatekeeper/Kyverno) restricting Pod spec fields beyond RBAC      | Deploy admission policies constraining privileged fields; RBAC alone does not restrict Pod spec content |
| Virtual cluster tenant's workload affected a co-located tenant's Pod       | vcluster isolates API surface only; shared node/kernel runtime boundary not addressed | Add node-level isolation (dedicated node pools, taints, or sandboxed runtime) alongside vcluster        |

## 9. Best Practices

- Standardize a "tenant onboarding bundle" (namespace, RBAC, default-deny NetworkPolicy, ResourceQuota, LimitRange) as a single GitOps-managed template rather than manually assembling primitives per team.
- Make the soft-vs-hard tenancy decision explicitly and document the trust boundary it assumes, rather than defaulting into namespace-only isolation without evaluating whether the tenant population is genuinely trusted.
- Layer admission control (OPA Gatekeeper/Kyverno) as a mandatory fourth pillar alongside RBAC, NetworkPolicy, and ResourceQuota — RBAC restricts _who_ can act, admission policy restricts _what_ they can create, and neither substitutes for the other.
- Audit cluster-scoped resources and cross-namespace RBAC grants (`get secrets` cluster-wide, broad `ClusterRoleBinding`s) specifically for tenancy-breaking exceptions on a recurring basis.

## 10. Common Anti-Patterns / Mistakes

- **Treating namespaces alone as a security boundary**, when a namespace without RBAC, NetworkPolicy, and quota layered on top provides only naming/organizational separation, not isolation.
- **Retrofitting hard tenancy onto a cluster architected for soft tenancy** after a trust-boundary requirement changes (e.g., onboarding an external customer), rather than deciding the tenancy model upfront.
- **Assuming vcluster or similar virtual-control-plane tools provide full workload isolation**, when they isolate the API/control-plane surface but still share the underlying node's kernel unless paired with node-level isolation.

## 11. Interview Questions

**🎯 Beginner:** _"Does putting two teams' workloads in separate Kubernetes namespaces mean they're isolated from each other?"_
**Model answer:** Not by itself. A namespace is primarily a naming and object-organization scope. Without RBAC restricting cross-namespace API access and a NetworkPolicy restricting cross-namespace Pod traffic, any Pod can reach any other Pod cluster-wide by default, and any sufficiently-privileged identity can read or modify objects across namespaces. Real isolation requires composing RBAC, NetworkPolicy, and typically ResourceQuota on top of the namespace boundary.
_What the interviewer is probing for:_ The foundational misconception that namespaces alone are a security boundary — a frequent gap in candidates who've only used namespaces for organizational tidiness.

**🎯 Intermediate:** _"What's the difference between soft and hard multi-tenancy, and how would you decide which one a given cluster needs?"_
**Model answer:** Soft multi-tenancy assumes tenants are mutually trusted — they share a control plane, and isolation is achieved entirely through namespace-scoped RBAC, NetworkPolicy, and ResourceQuota. Hard multi-tenancy assumes tenants may be adversarial or must meet strict regulatory/blast-radius isolation requirements, requiring stronger primitives: separate clusters per tenant, virtual clusters with isolated control planes, or sandboxed container runtimes. The deciding factor is trust level, not convenience — internal teams within one organization are usually fine with soft tenancy; external customers or genuinely untrusted workloads need hard tenancy, because a shared-kernel container escape in soft tenancy can cross every tenant's boundary at once.
_What the interviewer is probing for:_ Whether the candidate frames the decision around trust and risk rather than defaulting to "namespaces are enough" or over-engineering everything into separate clusters regardless of actual need.

**🎯 Senior:** _"A platform team's soft multi-tenant cluster has RBAC and ResourceQuota in place, but a security review still flags it as high-risk. What's most likely missing, and how would you close the gap?"_
**Model answer:** The most common gap is NetworkPolicy — RBAC governs the Kubernetes API and ResourceQuota governs resource consumption, but neither restricts Pod-to-Pod network traffic, so without an explicit default-deny NetworkPolicy per tenant namespace, every tenant's Pods can reach every other tenant's Pods by default. I'd also check for admission control: RBAC's `edit` role permits creating Pods, but without an OPA Gatekeeper or Kyverno policy, that same RBAC grant permits privileged containers, hostPath mounts, or hostNetwork usage that bypass the intended isolation entirely. Finally, I'd audit cluster-scoped resources and any ClusterRoleBindings granting cross-namespace secret or object access, since those bypass namespace-scoped isolation regardless of how well the per-namespace RBAC and quota are configured.
_What the interviewer is probing for:_ Systematic gap analysis across the four isolation axes rather than treating "RBAC plus quota" as a complete multi-tenancy solution.

**🎯 Architect:** _"Design the multi-tenancy architecture for a platform hosting workloads for external, mutually-distrustful customers on shared infrastructure, where cost efficiency (avoiding one cluster per customer) is also a hard requirement."_
**Model answer:** I'd reject pure soft tenancy immediately given "mutually distrustful" — namespace-scoped isolation alone leaves a shared-kernel escape path between customers, which is unacceptable for adversarial trust levels. I'd also reject full cluster-per-customer given the stated cost constraint, since that reintroduces per-tenant control-plane and node-pool overhead at scale. My design centers on virtual clusters (vcluster or a similar control-plane-per-tenant pattern) on a shared host cluster, giving each customer their own API server, RBAC root, and CRD namespace, while pairing that with node-level isolation — either dedicated node pools per customer tier (with taints/tolerations preventing cross-tenant scheduling) or a sandboxed runtime (gVisor/Kata, [§113](../Part15/Section-113-Part15-CKS-Curriculum-Overview-Cluster-Setup-Hardening-CIS-Benchmarks-kube-bench.md)) on shared nodes for lower-tier customers where dedicated nodes aren't cost-justified. I'd layer ResourceQuota and LimitRange ([§127](./Section-127-Part16-Cost-Optimization-Resource-Governance-ResourceQuotas-LimitRanges.md)) per virtual cluster to prevent one customer's burst from starving others, default-deny NetworkPolicy at both the host-cluster and virtual-cluster layers, and admission policy on the host cluster that customers cannot override regardless of their virtual cluster's own RBAC, since the host cluster's admission chain is the actual last line of defense against a compromised virtual cluster attempting to affect co-tenants. The core trade-off I'm making explicit to the business is a tiered isolation model: highest-value or highest-risk customers get dedicated node pools, while cost-sensitive tenants accept sandboxed-runtime-level isolation on shared nodes — not one uniform isolation guarantee for everyone at the same cost.
_What the interviewer is probing for:_ Ability to reconcile competing constraints (adversarial trust + cost efficiency) into a tiered, defensible architecture rather than picking one extreme (all separate clusters, or namespaces-only) and ignoring the stated trade-off.

## 12. Common Misconceptions

1. **"Namespaces provide security isolation by default."** They provide only naming/object scope; RBAC, NetworkPolicy, and quota must be actively composed on top for any real isolation.
2. **"Soft multi-tenancy is inherently less secure and should be avoided."** It's entirely appropriate for genuinely trusted internal teams — the risk it carries (shared kernel, shared control plane) is proportional to trust level, not a universal flaw.
3. **"Virtual clusters (vcluster) provide the same isolation as separate physical clusters."** They isolate the control-plane/API surface, not the underlying node/kernel execution boundary, unless explicitly paired with node-level isolation.
4. **"RBAC restricting `create pods` to `edit` role is sufficient tenant control."** RBAC governs API actions, not Pod spec content — without admission policy, an `edit`-scoped identity can still request privileged, hostPath, or hostNetwork-enabled Pods.

## 13. 🔑 Key Takeaways

- Kubernetes has no native "tenant" primitive — multi-tenancy is always a composed pattern layering RBAC ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)), NetworkPolicy ([§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)), ResourceQuota/LimitRange ([§127](./Section-127-Part16-Cost-Optimization-Resource-Governance-ResourceQuotas-LimitRanges.md)), and optionally node- or cluster-level separation atop namespaces.
- The soft-versus-hard tenancy decision is driven by trust level and must be made deliberately and early, since retrofitting hard isolation later is a significant re-platforming effort.
- Admission control (Gatekeeper/Kyverno) is a frequently-missing fourth pillar alongside RBAC, NetworkPolicy, and quota — without it, RBAC-granted identities can still create Pods that bypass the intended isolation model.
- Virtual-cluster patterns (vcluster) isolate the control-plane/API surface but do not automatically isolate the shared node/kernel execution boundary underneath.
- Cluster-scoped resources and cross-namespace RBAC grants must be specifically audited, since namespace-scoped isolation says nothing about them.

## 14. Related Concepts & What's Next

This section composed [§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)'s RBAC model and [§55](../Part7/Section-55-Part7-NetworkPolicies-Default-Deny-Ingress-Egress-Rules.md)'s NetworkPolicy model into a full multi-tenancy architecture, building on [§125](./Section-125-Part16-Multi-Cluster-Architectures-Federation-Cluster-API.md)'s multi-cluster patterns as the "how many clusters" axis of the same decision. [§127](./Section-127-Part16-Cost-Optimization-Resource-Governance-ResourceQuotas-LimitRanges.md) continues directly from here into the resource-governance axis of tenancy — ResourceQuotas and LimitRanges as the mechanism preventing one tenant from starving another's compute budget, which this section referenced repeatedly as the fourth isolation pillar without detailing its mechanics.

**Next Section:** [§127](./Section-127-Part16-Cost-Optimization-Resource-Governance-ResourceQuotas-LimitRanges.md) — `Section-127-Part16-Cost-Optimization-Resource-Governance-ResourceQuotas-LimitRanges.md`
