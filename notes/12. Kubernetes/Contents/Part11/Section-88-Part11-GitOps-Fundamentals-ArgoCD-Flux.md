# Section 88 (Part 11): GitOps Fundamentals: ArgoCD and Flux

## 1. Definition

**Plain language:** Every tool covered so far in this Part answers "how do I package and template my manifests" (Helm, §82–§83), "how do I customize them per environment" (Kustomize, §84), or "how do I automate deep operational logic" (Operators, §86–§87) — but none of them answer a more basic operational question: what actually applies these manifests to the cluster, when, and from where? GitOps answers that question by making a Git repository the single, version-controlled source of truth, and putting a controller — not a human running `kubectl apply` — in charge of continuously reconciling the live cluster to match it.

**Precise definition:** **GitOps** is an operational model in which a Git repository holds the declarative, desired-state definition of a system (Kubernetes manifests, Helm charts, Kustomize overlays), and a dedicated **GitOps controller** running inside (or alongside) the cluster continuously reconciles live cluster state to match that repository — applying the exact watch/compare/act loop from §13, with "desired state" sourced from Git commits instead of purely from objects already in etcd. **ArgoCD** and **Flux** are the two dominant, CNCF-graduated GitOps controllers implementing this model: both watch one or more Git repositories, detect drift between the repository's declared state and the live cluster, and either automatically reconcile that drift (auto-sync) or surface it for manual approval, depending on configuration.

## 2. Why This Matters

- **GitOps is the delivery-model synthesis of everything else in Part 11** — Helm charts and Kustomize overlays (§82–§85) define _what_ good desired state looks like; Operators and custom controllers (§86–§87) define _how_ deep, stateful reconciliation works; GitOps ties both together by defining _where_ desired state authoritatively lives (Git) and _what_ continuously enforces it (ArgoCD/Flux, themselves controllers built the same way as §87 describes).
- **It replaces "someone ran `kubectl apply` from their laptop" with an auditable, reviewable, revertible process** — every cluster change traces to a Git commit, which means code review, a full history, and a one-command rollback (`git revert`) apply to infrastructure changes the same way they've always applied to application code, closing a governance gap that ad hoc `kubectl` access leaves wide open.
- **Continuous reconciliation (not just one-time deployment) means configuration drift gets corrected automatically**, not just detected after the fact — an emergency manual `kubectl edit` made directly against a live cluster during an incident gets flagged and reverted by the GitOps controller's next sync, which is exactly the same self-correcting property §13's reconciliation loop provides for built-in resources, just applied at the whole-cluster-configuration level.

🔑 **Key Takeaway:** GitOps makes a Git repository the authoritative source of desired cluster state, and puts a dedicated controller (ArgoCD or Flux) in charge of continuously reconciling the live cluster to match it — the same watch/compare/act pattern from §13, applied cluster-wide, turning every infrastructure change into an auditable, reviewable, revertible Git commit instead of an untracked imperative command.

## 3. Prerequisites and Dependencies

Synthesizes §82–§83 (Helm Fundamentals and chart authoring), §84 (Kustomize), and §85 (Helm vs. Kustomize decision framework) as the packaging formats GitOps controllers most commonly reconcile, and §86–§87 (Operators and Custom Controllers, this Part), since ArgoCD and Flux are themselves `controller-runtime`-style controllers reconciling against Git rather than purely in-cluster state. Back-references §13 (Controller Manager, Part 2) as the generic pattern this entire delivery model extends.

## 4. Architecture Diagram

```text
┌───────────────────────────────────────────────────────────────────────┐
│  GIT REPOSITORY (source of truth)                                     │
│  manifests/ , helm-charts/ , kustomize-overlays/                      │
│  └── every change arrives via a reviewed pull request + merge         │
└──────────────────────────────┬────────────────────────────────────────┘
                               │  poll / webhook-triggered pull
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  GITOPS CONTROLLER (ArgoCD Application-controller / Flux source-    │
│  controller + kustomize-controller)                                 │
│                                                                     │
│    loop:                                                            │
│      1. fetch latest committed state from Git                       │
│      2. render it (helm template / kustomize build, if applicable)  │
│      3. compare rendered manifests against LIVE cluster state       │
│      4. if drift exists:                                            │
│           - auto-sync ON  → apply changes automatically             │
│           - auto-sync OFF → surface as "OutOfSync", await approval  │
└──────────────────────────────┬──────────────────────────────────────┘
                               ▼
┌─────────────────────────────────────────────────────────────────────┐
│  LIVE CLUSTER                                                       │
│  - a manual kubectl edit made here is DRIFT — the next reconcile    │
│    pass detects and (if auto-sync is on) reverts it back to Git's   │
│    declared state                                                   │
└─────────────────────────────────────────────────────────────────────┘
```

- **The controller pulls from Git — the cluster is never granted push/write access to the repository, and CI/CD pipelines never push directly to the cluster.** This "pull, not push" direction is GitOps's defining architectural property: it means cluster credentials never need to leave the cluster and be handed to an external CI system, meaningfully shrinking the credential-exposure surface compared to a traditional push-based pipeline.
- **Both ArgoCD and Flux render Helm charts and Kustomize overlays as part of their reconcile step** — GitOps controllers don't replace §82–§84's packaging tools, they consume their output as the "desired state" input to the same watch/compare/act loop.

## 5. Hands-On

### 5.1 Installing ArgoCD and Defining an Application

**Purpose:** Show ArgoCD's core `Application` custom resource — itself a CRD, exactly as covered in §86 — declaring what Git source maps to what cluster destination.

**Syntax:**

```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
argocd app sync my-app
```

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: my-app
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/example/gitops-configs.git
    targetRevision: main
    path: apps/my-app/overlays/production
  destination:
    server: https://kubernetes.default.svc
    namespace: production
  syncPolicy:
    automated:
      prune: true
      selfHeal: true
```

**Production usage example:** `syncPolicy.automated.selfHeal: true` is what turns ArgoCD from a one-time deployer into a genuine continuous reconciler — without it, ArgoCD detects drift and shows `OutOfSync` but waits for a manual sync; with it, drift (including a manual emergency `kubectl edit`) is corrected automatically on the next reconcile pass, the exact self-healing property described in §2.

**Common errors:** Setting `prune: true` without fully understanding its scope — `prune` deletes any live cluster object that's no longer present in the Git-declared state, which is correct and intended behavior for GitOps but has caused real incidents when a manifest was accidentally removed from a Git repository and ArgoCD faithfully (and correctly, per its contract) deleted the corresponding live resource.

### 5.2 Installing Flux and Defining a GitRepository + Kustomization

**Purpose:** Show Flux's equivalent two-part model — a `GitRepository` source object and a `Kustomization` object that applies it — reflecting Flux's more modular, multi-controller architecture (source-controller, kustomize-controller, helm-controller as separate components).

**Syntax:**

```bash
flux bootstrap github --owner=example --repository=gitops-configs --branch=main --path=clusters/production
```

```yaml
apiVersion: source.toolkit.fluxcd.io/v1
kind: GitRepository
metadata:
  name: gitops-configs
  namespace: flux-system
spec:
  interval: 1m
  url: https://github.com/example/gitops-configs.git
  ref:
    branch: main
---
apiVersion: kustomize.toolkit.fluxcd.io/v1
kind: Kustomization
metadata:
  name: my-app
  namespace: flux-system
spec:
  interval: 5m
  sourceRef:
    kind: GitRepository
    name: gitops-configs
  path: "./apps/my-app/overlays/production"
  prune: true
```

**Production usage example:** Flux's split between `GitRepository` (the source) and `Kustomization` (what to apply from it, and where) reflects its deliberately modular architecture — multiple `Kustomization` objects can reference the same `GitRepository` source to deploy different paths to different namespaces or clusters, without redundantly re-fetching the same repository multiple times.

**Common errors:** Setting `interval` far too low (e.g., `10s`) on a `GitRepository` polling a busy repository — this creates unnecessary load on the Git provider and offers little practical benefit over a webhook-triggered reconcile, which both ArgoCD and Flux support as the preferred, near-instant alternative to short polling intervals.

### 5.3 Structuring a GitOps Repository for Multiple Environments

**Purpose:** Show the common repository layout pattern combining Kustomize overlays (§84) with GitOps, so both tools in this synthesis section are visibly working together.

**Syntax:**

```text
gitops-configs/
├── apps/
│   └── my-app/
│       ├── base/
│       │   ├── deployment.yaml
│       │   ├── service.yaml
│       │   └── kustomization.yaml
│       └── overlays/
│           ├── staging/
│           │   └── kustomization.yaml   # patches: 2 replicas
│           └── production/
│               └── kustomization.yaml   # patches: 5 replicas, prod resource limits
└── clusters/
    ├── staging/    # Flux Kustomization / ArgoCD Application pointing at overlays/staging
    └── production/ # Flux Kustomization / ArgoCD Application pointing at overlays/production
```

**Production usage example:** This base/overlay-per-environment structure, combined with one GitOps `Application`/`Kustomization` object per environment pointing at its respective overlay path, is the standard pattern that lets a single Git repository safely drive multiple clusters or namespaces with environment-specific differences, while keeping the actual application definition (the `base/`) written exactly once.

**Common errors:** Duplicating entire manifests per environment instead of using Kustomize overlays (§84) against a shared base — this defeats much of GitOps's value, since a fix or update then has to be manually copied across every environment's duplicated files rather than applied once in the shared base and inherited everywhere.

## 6. Production Usage Notes

- **Both ArgoCD and Flux support a "progressive delivery" extension via Argo Rollouts or Flagger**, layering canary/blue-green deployment strategies on top of the base GitOps reconciliation model — worth knowing exists, though it's beyond this section's fundamentals scope.
- **ArgoCD ships with a first-class web UI showing sync status, diffs, and application health visually**, which is a meaningful adoption factor for teams wanting visibility without needing to `kubectl describe` custom resources directly; Flux is comparatively more CLI/GitOps-tool-native, often paired with a separate UI (like Weave GitOps or a Grafana dashboard) if visual status is wanted.
- **Multi-cluster/multi-tenant GitOps at scale typically uses a "hub and spoke" or "app of apps" pattern** — a root `Application`/`Kustomization` object that itself manages a set of other `Application`/`Kustomization` objects, letting a single Git commit to the root repository fan out changes across many clusters or namespaces consistently.

## 7. Security Considerations

- **GitOps's "pull, not push" model is itself a meaningful security improvement over traditional CI/CD push pipelines** — cluster credentials live only inside the cluster (used by ArgoCD/Flux to reconcile), and never need to be distributed to an external CI system, shrinking a real and historically-exploited credential-exposure surface.
- **The GitOps controller's own ServiceAccount typically needs broad permissions to apply arbitrary manifests across the namespaces/clusters it's responsible for** — exactly the same high-value-target consideration as an Operator's ServiceAccount (§86), warranting equivalent RBAC scrutiny, and in multi-tenant setups, careful scoping via ArgoCD Projects or Flux's namespace-scoped Kustomizations so one team's GitOps controller instance can't reconcile another team's namespace.
- **Because a Git repository is now the mechanism that drives real cluster changes, write access to that repository is effectively write access to the cluster** — branch protection, mandatory PR review, and commit signing on the GitOps repository are load-bearing security controls, not just code-hygiene niceties, and should be governed with the same rigor as direct cluster RBAC.

## 8. Common Troubleshooting Scenarios

| Symptom                                                               | Cause                                                                                         | Fix                                                                                                      |
| --------------------------------------------------------------------- | --------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------- |
| Application shows `OutOfSync` and doesn't self-correct                | `syncPolicy.automated` (ArgoCD) or auto-apply isn't enabled — manual sync is required         | Trigger a manual sync, or enable `automated.selfHeal`/equivalent if continuous auto-reconcile is desired |
| A resource was unexpectedly deleted from the live cluster             | It was removed from the Git-declared manifests and `prune: true` correctly deleted it live    | Verify this was an intentional Git change; if not, revert the Git commit that removed it                 |
| A manual `kubectl edit` made during an incident keeps reverting       | GitOps controller's self-heal/auto-sync correctly detected and corrected the drift            | Expected behavior — commit the actual fix to Git instead of editing the live cluster directly            |
| Reconciliation reflects an old commit despite a new one being pushed  | Long polling `interval`, or a webhook trigger from Git to the controller isn't configured     | Reduce polling interval within reason, or configure a Git webhook for near-instant reconcile triggering  |
| Multiple teams' Applications/Kustomizations interfere with each other | Insufficient RBAC scoping — one GitOps controller instance/Application has cluster-wide reach | Scope via ArgoCD Projects or Flux namespace-scoped Kustomizations to each team's actual responsibility   |

## 9. Best Practices

- Enable automated self-healing (ArgoCD's `selfHeal`, Flux's continuous reconcile) in production so drift is corrected automatically rather than merely detected and left pending.
- Enforce branch protection, mandatory PR review, and ideally commit signing on any GitOps repository — write access to it is effectively write access to the cluster.
- Structure repositories with Kustomize base/overlay layering (§84) per environment rather than duplicating manifests, so GitOps's "fix once, apply everywhere" value is actually realized.
- Configure Git webhooks rather than relying solely on polling intervals, for near-instant reconciliation after a merge.
- Scope GitOps controller RBAC (ArgoCD Projects, Flux namespace-scoped Kustomizations) tightly in multi-tenant environments, mirroring the least-privilege principle already applied to Operators (§86).

## 10. Common Anti-Patterns / Mistakes

- **Making emergency changes directly against the live cluster during an incident and forgetting to commit the equivalent fix to Git** — a self-healing GitOps controller will silently revert the manual fix on its next reconcile pass, potentially re-introducing the very incident being fixed.
- **Enabling `prune: true` without understanding its full deletion scope**, then being surprised when an accidental manifest removal in Git results in a real, correctly-executed deletion of a live production resource.
- **Duplicating manifests across environment directories instead of using Kustomize overlays against a shared base**, undermining GitOps's core "single source of truth, fix once" value proposition.
- **Granting a GitOps controller cluster-admin-equivalent, unscoped RBAC "to keep things simple,"** rather than scoping it to each team's or environment's actual responsibility via Projects/namespace-scoped Kustomizations.

## 11. Interview Questions

**🎯 Beginner:** _"What is GitOps, in plain terms, and what's the difference between it and just running `kubectl apply` from a CI pipeline?"_
**Model answer:** GitOps means a Git repository is the single, authoritative source of desired cluster state, and a dedicated controller running inside or alongside the cluster continuously watches that repository and reconciles live cluster state to match it — the same watch/compare/act pattern as any Kubernetes controller, just pointed at Git. The key difference from a CI pipeline running `kubectl apply` is direction: GitOps pulls from Git into the cluster via a controller with credentials that never leave the cluster, while a traditional CI pipeline pushes into the cluster using credentials handed to an external system. GitOps also means changes are continuously reconciled, not just applied once — drift gets detected and (if configured) automatically corrected, not just deployed and forgotten.
_What the interviewer is probing for:_ Clear grasp of Git-as-source-of-truth plus continuous reconciliation, and the pull-vs-push architectural distinction from traditional CI/CD.

**🎯 Intermediate:** _"An engineer made an emergency `kubectl edit` directly on a production Deployment during an incident, and it got reverted a few minutes later. What happened, and what should they have done instead?"_
**Model answer:** The cluster is running a GitOps controller (ArgoCD or Flux) with self-healing/auto-sync enabled, which detected the manual edit as drift from the Git repository's declared state and correctly reverted it on its next reconcile pass — this is the self-healing behavior working exactly as designed, not a bug. What the engineer should have done is commit the actual fix to the GitOps repository (even under incident pressure, ideally via a fast-tracked but still reviewed PR) so the fix becomes the new declared desired state, rather than a manual change that's invisible to and actively fought by the reconciliation loop. Some teams configure a documented emergency procedure — temporarily pausing auto-sync for a specific Application/Kustomization — for genuine incident response, but the fix still needs to land in Git before auto-sync resumes.
_What the interviewer is probing for:_ Recognizing self-healing as intended behavior rather than a malfunction, and understanding that Git remains the durable fix location even under incident time pressure.

**🎯 Senior:** _"How does GitOps's pull-based model change the security posture of a deployment pipeline compared to a traditional push-based CI/CD pipeline, and what new risks does it introduce instead?"_
**Model answer:** Pull-based GitOps removes the need to distribute cluster credentials to an external CI system, which closes off a historically significant attack surface — compromised CI credentials in a push-based pipeline are a direct path to cluster compromise, and GitOps eliminates that specific vector since the reconciling controller's credentials never leave the cluster. However, it doesn't eliminate risk, it relocates it: write access to the GitOps repository is now functionally equivalent to write access to the cluster, so the repository's own access controls (branch protection, mandatory PR review, ideally commit signing) become just as security-critical as RBAC on the cluster itself, and a compromised contributor account or a missing branch-protection rule is the new equivalent risk. Additionally, the GitOps controller's own ServiceAccount typically holds broad apply permissions across whatever it's responsible for, making the controller itself — much like an Operator (§86) — a high-value target deserving the same RBAC scrutiny and SecurityContext hardening as any other cluster-wide privileged workload.
_What the interviewer is probing for:_ Nuanced understanding that GitOps shifts, rather than eliminates, the credential/access attack surface — from CI-held cluster credentials to Git-repository write access and the GitOps controller's own privileges.

**🎯 Architect:** _"Design a GitOps strategy for an organization running 20+ Kubernetes clusters across multiple teams and environments, using the tools covered across this Part (Helm, Kustomize, Operators, custom controllers, GitOps)."_
**Model answer:** I'd structure repositories around a base/overlay Kustomize pattern (§84) per application, with Helm (§82–§83) used specifically for third-party software with genuinely complex templating needs (databases, ingress controllers, Operators themselves), keeping hand-authored application manifests in plain Kustomize bases to avoid unnecessary templating complexity per §85's decision framework. For the GitOps layer itself, I'd adopt an "app of apps" / hub-and-spoke pattern — a root Application or Kustomization per cluster that itself manages a set of per-team, per-namespace child Applications/Kustomizations, so a single commit to a shared root repository can consistently fan out platform-level changes (a new required Operator, an updated cluster-wide policy) across all 20+ clusters, while each team's own repository or repository path governs their own application-level changes independently. I'd scope every child Application/Kustomization's RBAC tightly to its owning team's namespace(s) via ArgoCD Projects or Flux's namespace-scoped Kustomizations, mirroring the least-privilege principle already established for Operators (§86) and custom controllers (§87) — no team's GitOps scope should extend beyond their own responsibility. I'd enforce branch protection and mandatory review on every GitOps repository given that repository write access is now equivalent to cluster write access, and I'd configure Git webhooks (not bare polling) for near-instant reconciliation. Finally, since Operators and custom controllers (§86–§87) are themselves part of the desired state this GitOps layer manages, I'd make sure their CRDs and controller Deployments are reconciled through the exact same GitOps pipeline as application workloads — not installed or upgraded out-of-band — so the entire platform, from CRDs through applications, has one consistent, auditable, Git-driven change history end to end.
_What the interviewer is probing for:_ Ability to synthesize the whole Part's toolset (Helm, Kustomize, Operators, custom controllers, GitOps) into one coherent, scalable, secure multi-team/multi-cluster delivery architecture, with explicit attention to RBAC scoping and consistent change governance across every layer, including the platform components themselves.

## 12. Common Misconceptions

1. **"GitOps is just running deployment scripts triggered by a Git commit."** It's specifically a continuous reconciliation model — a controller keeps comparing live state to Git's declared state indefinitely, not a one-time deploy-on-commit trigger.
2. **"A GitOps controller pushes changes into the cluster from an external CI system."** It's the opposite direction — the controller runs inside/alongside the cluster and pulls from Git, meaning cluster credentials never need to be handed to an external system.
3. **"An unexpected resource deletion after a GitOps sync must be a bug."** With `prune`/auto-apply enabled, it's the controller correctly enforcing that Git is the source of truth — if a manifest was removed from Git, the corresponding live resource being deleted is expected, correct behavior.
4. **"GitOps and Helm/Kustomize are competing approaches — you pick one or the other."** GitOps controllers consume Helm charts and Kustomize overlays as their rendered desired-state input; they're complementary layers, not alternatives.

## 13. 🔑 Key Takeaways

- GitOps makes a Git repository the authoritative source of desired cluster state, and a controller (ArgoCD or Flux) continuously reconciles live state to match it — §13's watch/compare/act pattern applied at the whole-cluster-configuration level.
- The pull-based model (controller pulls from Git; cluster credentials never leave the cluster) is a meaningful security improvement over traditional push-based CI/CD, though it relocates risk onto Git repository access controls.
- Both ArgoCD and Flux render Helm charts and Kustomize overlays as part of reconciliation — GitOps is a delivery-model layer on top of §82–§84's packaging tools, not a replacement for them.
- Self-healing/auto-sync means manual, unrecorded cluster changes get automatically reverted — the fix belongs in Git, not in a live `kubectl edit`, even under incident pressure.
- Operators and custom controllers (§86–§87) should themselves be managed through the same GitOps pipeline as application workloads, for one consistent, auditable change history across the whole platform.

## 14. Related Concepts & What's Next

This section closes out Part 11 by synthesizing Helm (§82–§83) and Kustomize (§84) as the packaging formats GitOps controllers reconcile, and Operators/custom controllers (§86–§87) as both examples of the same underlying controller pattern and, in mature setups, workloads themselves managed through this same GitOps pipeline. Part 11 as a whole has moved from templating and packaging individual applications through to a complete, auditable, self-healing delivery model for an entire cluster's configuration. Part 12 shifts focus to observability — starting with the health-check mechanisms (liveness, readiness, and startup probes) that any workload deployed through this GitOps pipeline relies on to report its own status back to Kubernetes.

**Next Section:** §89 — `Section-89-Part12-Liveness-Readiness-Startup-Probes.md`
