# Section 47 (Part 6): Multi-Environment Configuration Patterns (Namespaces, Preview of Kustomize Overlays)

## 1. Definition

**Plain language:** Almost no application runs identically in dev, staging, and production — replica counts, resource sizing, ConfigMap values, and even which features are enabled all differ — and Kubernetes needs a repeatable, non-error-prone way to express "same application, different environment" rather than maintaining entirely separate, hand-edited YAML per environment.

**Precise definition:** A **Namespace** is a Kubernetes API-level partition that scopes names, RBAC, ResourceQuotas, and NetworkPolicies to a logical grouping — commonly one per environment (`dev`, `staging`, `prod`) or one per team/tenant. **Multi-environment configuration** is the broader discipline of managing the _differences_ between environments (image tags, replica counts, resource requests, ConfigMap/Secret values) without duplicating entire manifest sets, most commonly today via **Kustomize's base-and-overlay model** — a base set of manifests plus per-environment patches that are composed at apply time, covered here at a conceptual/preview level with full authoring depth in §84.

## 2. Why This Matters

- **Namespaces are a soft multi-tenancy boundary, not a hard security one on their own.** Two workloads in different Namespaces still share the same underlying nodes and kernel unless further isolated by NetworkPolicy (§55) and RBAC (Part 10) — a common misunderstanding this section corrects before it causes an incident.
- **Hand-copying manifests per environment is the single most common source of prod-only configuration drift.** A ConfigMap value or resource limit (§46) tuned in staging but forgotten in prod's separately maintained YAML is a recurring, avoidable outage cause — which is precisely the problem the base-and-overlay pattern previewed here, and covered fully in §84-85, exists to solve.
- **This section is deliberately a preview, not the full picture.** Full Kustomize authoring (bases, overlays, patches, `kustomization.yaml` mechanics) and the Helm vs. Kustomize decision framework live in §84-86 — treat this section as "why the problem exists and what the shape of the solution looks like," not the complete toolset.

🔑 **Key Takeaway:** Namespaces give you a logical per-environment boundary for naming, quotas, and access control, but they don't by themselves solve the harder problem of managing _configuration differences_ across environments — that's what overlay-based tooling is for, and this section only establishes the mental model before Part 11 builds it in full.

## 3. Prerequisites and Dependencies

Builds on §26 (ConfigMaps) and §46 (resource requests/limits, one of the most common values that legitimately differs per environment); assumes familiarity with basic YAML manifest authoring from §31.

## 4. Architecture Diagram

```text
                    Namespace boundary (per environment)
   ┌───────────────┐   ┌───────────────┐   ┌───────────────┐
   │  dev          │   │  staging      │   │  prod         │
   │  ──────────── │   │  ──────────── │   │  ──────────── │
   │  Deployments  │   │  Deployments  │   │  Deployments  │
   │  ConfigMaps   │   │  ConfigMaps   │   │  ConfigMaps   │
   │  Secrets      │   │  Secrets      │   │  Secrets      │
   │  ResourceQuota│   │  ResourceQuota│   │  ResourceQuota│
   └───────────────┘   └───────────────┘   └───────────────┘
          ▲                    ▲                    ▲
          │  environment-specific values applied at deploy time
          │                    │                    │
   ┌──────┴────────────────────┴────────────────────┴─────────┐
   │              Kustomize overlay model (preview)           │
   │                                                          │
   │   base/                overlays/dev/    overlays/prod/   │
   │   ├── deployment.yaml  ├── kustomization.yaml            │
   │   ├── service.yaml     │   (patches replicas, image tag, │
   │   └── kustomization.yaml   resource limits, ConfigMap    │
   │                             values for THIS environment) │
   └──────────────────────────────────────────────────────────┘
```

- **The base directory holds the environment-agnostic manifest set** — the Deployment, Service, and ConfigMap shape that's common to every environment.
- **Each overlay directory patches only what actually differs** for that environment (replica count, image tag, a specific env var) — full mechanics of `kustomization.yaml`, `patchesStrategicMerge`, and `configMapGenerator` are covered in §84.
- **Namespaces are typically the deploy-time target**, not the mechanism that generates the environment-specific YAML — the overlay produces the manifests; the Namespace is where they land.

## 5. Hands-On: Establishing Environment Boundaries

### 5.1 Creating Per-Environment Namespaces

**Purpose:** Establish the logical isolation boundary that scopes names, quotas, and access per environment.

**Syntax:**

```bash
kubectl create namespace dev
kubectl create namespace staging
kubectl create namespace prod
```

**Example usage and expected output:**

```bash
$ kubectl create namespace prod
namespace/prod created

$ kubectl get namespaces
NAME              STATUS   AGE
default           Active   120d
dev               Active   2m
staging           Active   2m
prod              Active   1s
kube-system       Active   120d
```

**Production usage example:** A platform team provisions `dev`, `staging`, and `prod` Namespaces per application team, each with its own `ResourceQuota` and `RoleBinding` set (Part 10), so a Deployment named `web-app` can exist identically-named in all three without collision — `kubectl apply -f deployment.yaml -n staging` and `-n prod` target entirely separate objects.

**Common errors:** Forgetting `-n <namespace>` (or a `namespace:` field / active context default) silently applies to whatever namespace is currently the kubectl context default — frequently `default` — which has caused real incidents where a manifest intended for `staging` was accidentally applied cluster-wide to `default`.

### 5.2 Setting the Default Namespace Per Context

**Purpose:** Reduce the risk of the mistake above by binding a kubeconfig context to a specific namespace, so commands default there without requiring `-n` every time.

**Syntax:**

```bash
kubectl config set-context --current --namespace=staging
```

**Example usage and expected output:**

```bash
$ kubectl config set-context --current --namespace=staging
Context "my-cluster" modified.

$ kubectl config view --minify | grep namespace
    namespace: staging
```

**Production usage example:** Teams commonly maintain separate kubeconfig contexts per cluster/environment combination (`dev-context`, `prod-context`), each pre-bound to its Namespace, and require an explicit `kubectl config use-context prod-context` switch before any prod-targeting command — a deliberate friction point that reduces accidental cross-environment application, tying back to §19's kubeconfig/context coverage.

### 5.3 Previewing the Overlay Pattern Conceptually

**Purpose:** See the shape of a base-plus-overlay layout before the full Kustomize mechanics arrive in §84 — this is intentionally a preview, not a working syntax reference.

**Syntax (conceptual, not exhaustive):**

```yaml
# base/kustomization.yaml
resources:
  - deployment.yaml
  - service.yaml

---
# overlays/prod/kustomization.yaml
resources:
  - ../../base
patches:
  - target:
      kind: Deployment
      name: web-app
    patch: |-
      - op: replace
        path: /spec/replicas
        value: 5
      - op: replace
        path: /spec/template/spec/containers/0/resources/limits/memory
        value: 1Gi
```

**Production usage example:** A base Deployment defines `replicas: 1` and modest resource limits suitable for a laptop-scale dev cluster; the `overlays/prod` directory patches only `replicas` (to 5) and the memory limit (to 1Gi) — one base, small per-environment diffs, instead of three fully duplicated 80-line Deployment manifests that inevitably drift apart over time. Full patch syntax (`patchesStrategicMerge`, JSON 6902 patches, `configMapGenerator`, `images` transformers) is covered in §84.

## 6. Production Usage Notes

- **Namespace-per-environment is the most common pattern for smaller organizations**, while larger organizations frequently use **Namespace-per-team** combined with **separate clusters per environment** (dev cluster, staging cluster, prod cluster) for stronger blast-radius isolation than Namespaces alone provide — the right choice depends on organizational scale and risk tolerance, not a universal rule.
- **ConfigMap and Secret values that differ per environment (§26-27) are exactly the kind of difference overlays are designed to isolate** — database connection strings, feature flags, and log levels are classic candidates for overlay-level patches rather than being baked into the base.
- **Resource requests/limits (§46) very commonly differ between dev and prod overlays** — a dev overlay might set minimal requests to fit more services on a small cluster, while the prod overlay sets requests reflecting real observed production load.

## 7. Security Considerations

- **Namespaces alone do not prevent network traffic between workloads in different Namespaces** — without NetworkPolicy (§55), a Pod in `dev` can reach a Service in `prod` by DNS name (§52) exactly as if they were co-located, so Namespace boundaries must be paired with NetworkPolicy for genuine network isolation.
- **RBAC RoleBindings scoped per Namespace (Part 10) are what actually prevents a developer with `dev` access from modifying `prod` resources** — the Namespace boundary only becomes an access-control boundary once RBAC is deliberately configured to respect it; an unscoped ClusterRoleBinding defeats this entirely.

## 8. Common Troubleshooting Scenarios

| Symptom                                                             | Likely Cause                                                                                             | Resolution Path                                                                                                     |
| ------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------- |
| Manifest applied to the wrong environment                           | Active kubectl context defaulted to an unintended Namespace/cluster                                      | Verify with `kubectl config current-context` and `--namespace` before every apply                                   |
| Prod behaves differently from staging despite "identical" YAML      | Manually maintained per-environment YAML has silently drifted apart                                      | Migrate to base-plus-overlay (§84) so differences are explicit and diffable                                         |
| A dev-namespace Pod can unexpectedly reach a prod Service           | No NetworkPolicy enforcing Namespace isolation                                                           | Apply default-deny NetworkPolicy per Namespace (§55) and allow only intended traffic                                |
| Developer can modify prod resources despite only needing dev access | RBAC RoleBinding scope too broad, or a ClusterRoleBinding used instead of a Namespace-scoped RoleBinding | Audit RBAC bindings per Namespace (Part 10); replace ClusterRoleBindings with scoped RoleBindings where appropriate |

## 9. Best Practices

- Treat Namespaces as the deploy-time target for environment separation, but rely on an overlay tool (Kustomize, or Helm values files) as the actual mechanism for managing what differs between environments — don't hand-maintain parallel YAML trees.
- Pair every environment Namespace with both a `ResourceQuota` and NetworkPolicy from day one, rather than adding isolation retroactively after an incident exposes its absence.
- Bind kubeconfig contexts to specific Namespaces/clusters and require explicit context switches before prod-targeting commands, reducing the "wrong environment" class of human error.

## 10. Common Anti-Patterns / Mistakes

- **Maintaining fully separate, hand-copied manifest sets per environment** instead of a base-plus-overlay structure, guaranteeing eventual silent drift between environments.
- **Assuming Namespace separation implies network or RBAC isolation by default** — neither is true without explicitly configuring NetworkPolicy and scoped RBAC bindings.
- **Relying on kubectl context defaults without regularly verifying the active context/namespace**, a small habit gap responsible for a disproportionate number of "applied to the wrong environment" incidents.

## 11. Interview Questions

**🎯 Beginner:** _"What is a Kubernetes Namespace, and what does it isolate by default?"_
**Model answer:** A Namespace is a logical partition within a cluster that scopes object names, so you can have a Deployment called `web-app` in both `dev` and `prod` without collision. By default it doesn't provide network isolation or resource isolation — those require explicitly configuring NetworkPolicy and ResourceQuota respectively; a bare Namespace mainly separates naming and provides a scope for RBAC bindings.
_What the interviewer is probing for:_ Whether the candidate understands Namespaces are a naming/organizational boundary first, not an automatic security or resource boundary.

**🎯 Intermediate:** _"Why is hand-maintaining separate YAML files per environment considered an anti-pattern, and what's the alternative?"_
**Model answer:** Hand-copied manifests inevitably drift — a fix or tuning change made in one environment's file is easy to forget in the others, and there's no structural way to see what's actually different between environments versus accidentally different. The alternative is a base-plus-overlay approach (Kustomize) or a templated values approach (Helm), where a single base definition captures what's common, and small, explicit, diffable patches capture only genuine per-environment differences — making drift visible in a diff rather than silent.
_What the interviewer is probing for:_ Understanding of configuration drift as a real operational risk and familiarity with the tooling patterns that mitigate it, not just tool names.

**🎯 Senior:** _"A developer with only 'dev' Namespace access was able to delete a Deployment in 'prod.' How do you investigate and prevent recurrence?"_
**Model answer:** I'd start by checking the actual RBAC bindings granted to that developer's identity — most likely a ClusterRoleBinding (cluster-wide) was used where a Namespace-scoped RoleBinding should have been, or a RoleBinding in `prod` was created and never cleaned up. I'd audit all bindings for that user/group across every Namespace, remove any inappropriately broad grants, and going forward enforce that prod-Namespace RBAC changes go through a distinct, more tightly reviewed process than dev-Namespace RBAC changes, since this incident shows the "Namespace as isolation boundary" assumption was never actually backed by matching RBAC scope.
_What the interviewer is probing for:_ Recognition that Namespace isolation is only as strong as the RBAC configuration actually layered on top of it, plus a concrete remediation and audit process rather than just "restrict permissions."

**🎯 Architect:** _"You're designing the environment topology for a platform serving 40 application teams across dev/staging/prod. What's your Namespace/cluster strategy, and what trade-offs are you weighing?"_
**Model answer:** I'd weigh Namespace-per-team-per-environment within shared clusters (cheaper, faster to provision, but weaker blast-radius isolation, requiring disciplined NetworkPolicy/RBAC/ResourceQuota to be safe) against fully separate clusters per environment or even per major tenant (stronger isolation and blast-radius containment, but materially higher operational and cost overhead — more control planes to upgrade, secure, and monitor). For 40 teams, I'd likely land on separate clusters per environment (dev/staging/prod each its own cluster) with Namespace-per-team within each, since environment-level isolation (a broken dev experiment should never be able to touch prod, even accidentally) is worth the operational cost, while team-level isolation within an environment can be handled adequately by Namespace-scoped RBAC/quota/NetworkPolicy given the lower stakes of intra-environment cross-team interference. I'd pair this with base-plus-overlay Kustomize structures (§84) or Helm per team so the 40 teams aren't each hand-maintaining parallel manifest trees.
_What the interviewer is probing for:_ Ability to reason about the real trade-off between isolation strength and operational overhead at organizational scale, and to combine Namespace, cluster topology, and configuration-management tooling into one coherent strategy rather than treating them as unrelated decisions.

## 12. Common Misconceptions

1. **"Namespaces provide network isolation between environments by default."** They don't — Pods in different Namespaces can reach each other's Services by DNS name unless NetworkPolicy explicitly restricts it.
2. **"More Namespaces automatically means better security."** Namespace boundaries only become meaningful access-control boundaries once RBAC, NetworkPolicy, and ResourceQuota are deliberately scoped to respect them.
3. **"Kustomize overlays require rewriting the base manifest per environment."** The base stays environment-agnostic; overlays contain only the specific, minimal patches for each environment — full mechanics in §84.
4. **"Namespace-per-environment and cluster-per-environment are the same level of isolation."** Namespace separation shares the same underlying control plane and nodes across environments; separate clusters provide materially stronger blast-radius isolation at higher operational cost.

## 13. 🔑 Key Takeaways

- A Namespace scopes object names, RBAC bindings, ResourceQuotas, and NetworkPolicy targets — it is an organizational boundary, not an automatic security or resource-isolation boundary.
- Hand-maintaining separate manifest sets per environment is a leading cause of prod configuration drift; base-plus-overlay tooling exists specifically to make environment differences explicit and diffable.
- ConfigMap/Secret values and resource requests/limits (§46) are the most common configuration values that legitimately need to differ per environment.
- Genuine environment isolation requires pairing Namespaces with NetworkPolicy (§55) and scoped RBAC (Part 10) — none of the three alone is sufficient.
- This section is a conceptual preview only; full Kustomize authoring mechanics and the Helm vs. Kustomize decision framework are covered in §84-86.

## 14. Related Concepts & What's Next

This section closes Part 6 by connecting §26's ConfigMaps and §46's resource requests/limits to the broader problem of managing them consistently across environments, previewing the base-and-overlay model that §84-88 (Part 11) build out completely, including full Kustomize patch syntax, Helm chart authoring, and the decision framework for choosing between them. Part 7 now begins with the networking model these environment-scoped Services and Pods actually communicate over.

**Next Section:** §48 — `Section-48-Part7-Kubernetes-Networking-Model-Flat-Network.md`
