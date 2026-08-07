# Section 86 (Part 11): Operators and the Operator Pattern; Custom Resource Definitions (CRDs)

## 1. Definition

**Plain language:** Kubernetes natively knows how to run stateless things well — a Deployment scaling Pods is easy because "more replicas" is a shallow, mechanical operation. But running a PostgreSQL cluster, a Kafka broker set, or a certificate authority involves deep operational knowledge — how to fail over a primary, how to rebalance partitions, how to rotate a CA safely — that no generic Kubernetes object understands. An Operator is how that specialized human operational knowledge gets encoded as software and run inside the cluster itself, watching and acting the same way a built-in controller does.

**Precise definition:** A **Custom Resource Definition (CRD)** extends the Kubernetes API with a new resource type — a new schema the api-server will validate, store in etcd, and serve through the same REST/watch machinery as any built-in object like a Pod or Deployment. An **Operator** pairs a CRD with a **custom controller** that watches instances of that custom resource (a "Custom Resource," or CR) and reconciles real-world state to match — the exact watch/compare/act loop covered for built-in controllers in [§13](../Part2/Section-13-Part2-Controller-Manager-Controller-Pattern-Reconciliation-Loops.md), just applied to a resource type nobody but this Operator's author defined. Where a plain CRD without a controller is just inert structured storage, an Operator is what makes that storage _operational_: encoding domain-specific knowledge (how to fail over a database primary, how to safely resize a running cluster) as reconciliation logic.

## 2. Why This Matters

- **CRDs are the extension mechanism that makes Kubernetes a platform, not just a container scheduler.** Nearly every significant piece of cluster infrastructure beyond raw workloads — cert-manager's `Certificate` objects, Prometheus's `ServiceMonitor`, Istio's `VirtualService`, database operators' `PostgreSQLCluster` — is a CRD, and the vast majority of production clusters run several dozen of them without operators ever noticing they're not "built-in."
- **The Operator pattern is what makes stateful workloads genuinely automatable in Kubernetes**, closing the gap between "Kubernetes runs stateless apps well out of the box" and the reality that most real systems have state — a well-written database Operator can perform a leader failover in seconds, correctly, every time, encoding a runbook a human on-call engineer would otherwise execute manually and inconsistently under pressure.
- **Understanding CRDs and Operators is the direct prerequisite for [§87](./Section-87-Part11-Custom-Controllers-Conceptual-Overview-controller-runtime.md)'s custom controllers** — a CRD alone does nothing; it needs a controller loop to become an Operator, and that reconciliation logic is exactly what [§87](./Section-87-Part11-Custom-Controllers-Conceptual-Overview-controller-runtime.md) covers in depth.

🔑 **Key Takeaway:** A CRD extends the Kubernetes API with a new resource type; an Operator pairs that CRD with a custom controller that reconciles real-world state using the same watch/compare/act loop as any built-in controller — turning encoded operational expertise (failover, scaling, backup) into automated, in-cluster software.

## 3. Prerequisites and Dependencies

Builds directly on [§13](../Part2/Section-13-Part2-Controller-Manager-Controller-Pattern-Reconciliation-Loops.md) (Controller Manager, the Controller Pattern, and reconciliation loops, Part 2) — the CRD/Operator mechanism is a direct generalization of that pattern to user-defined resource types — and on [§85](./Section-85-Part11-Helm-vs-Kustomize-vs-Raw-Manifests-Decision-Framework.md) (Helm vs. Kustomize vs. Raw Manifests decision framework), since Operators are very commonly themselves distributed and installed as Helm charts. Forward-references [§87](./Section-87-Part11-Custom-Controllers-Conceptual-Overview-controller-runtime.md) (Custom Controllers, conceptual overview) for the mechanics of how an Operator's reconciliation loop is actually implemented.

## 4. Architecture Diagram

```text
┌───────────────────────────────────────────────────────────────────────┐
│  1. CRD registers a NEW API type with the api-server                  │
│     apiVersion: apiextensions.k8s.io/v1, kind: CustomResourceDef.     │
│     e.g. group: databases.example.com, kind: PostgresCluster          │
└──────────────────────────────┬────────────────────────────────────────┘
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│  2. Users create CUSTOM RESOURCE instances of that new type           │
│     kind: PostgresCluster                                             │
│     spec: {replicas: 3, version: "15", storageSize: "100Gi"}          │
│     (stored in etcd, served via the api-server, exactly like a Pod)   │
└──────────────────────────────┬────────────────────────────────────────┘
                               ▼
┌───────────────────────────────────────────────────────────────────────┐
│  3. The OPERATOR (a custom controller, usually itself a Pod) watches  │
│     PostgresCluster objects via the api-server                        │
│                                                                       │
│     loop forever:                                                     │
│       a. observe: what PostgresCluster CRs exist, and their spec      │
│       b. observe: real-world state (actual Pods, PVCs, replica roles) │
│       c. compare: does actual state match desired spec?               │
│       d. act: create/scale StatefulSet, promote a replica, take backup│
└──────────────────────────────┬────────────────────────────────────────┘
                               ▼
              Underlying Kubernetes objects (StatefulSets, Services,
              PVCs, Secrets) created/managed on the user's behalf —
              the CR is the single source of truth; these are derived.
```

- **The CRD only defines the shape of the data — it has zero behavior on its own.** A cluster can have a CRD registered with no controller watching it at all; CRs would simply sit inert in etcd, validated and stored but never acted upon. The Operator's controller is what supplies the behavior.
- **The Operator's own controller Pod(s) typically run inside the cluster they manage**, watching and reconciling their target CRs the same way kube-controller-manager's built-in controllers watch built-in types — architecturally, an Operator is not a special Kubernetes concept, just an ordinary workload with elevated RBAC permissions over its target CRD.

## 5. Hands-On

### 5.1 Defining and Registering a CRD

**Purpose:** Show the minimal shape of a CRD that registers a new API type, including OpenAPI schema validation.

**Syntax:**

```bash
kubectl apply -f postgrescluster-crd.yaml
kubectl get crd postgresclusters.databases.example.com
```

```yaml
apiVersion: apiextensions.k8s.io/v1
kind: CustomResourceDefinition
metadata:
  name: postgresclusters.databases.example.com
spec:
  group: databases.example.com
  names:
    kind: PostgresCluster
    plural: postgresclusters
    singular: postgrescluster
    shortNames: ["pgc"]
  scope: Namespaced
  versions:
    - name: v1
      served: true
      storage: true
      schema:
        openAPIV3Schema:
          type: object
          properties:
            spec:
              type: object
              required: ["replicas", "version"]
              properties:
                replicas:
                  type: integer
                  minimum: 1
                version:
                  type: string
                storageSize:
                  type: string
```

**Production usage example:** The `schema` block's validation is enforced by the api-server itself at admission time ([§77](../Part10/Section-77-Part10-Admission-Controllers-Validating-Mutating-Webhooks.md)) before the CR is ever persisted — a `PostgresCluster` with `replicas: 0` is rejected outright with a clear schema error, the same category of safety net `ResourceQuota` and built-in object schemas already provide for Pods and Deployments.

**Common errors:** Forgetting `storage: true` on exactly one served version when a CRD defines multiple API versions — the api-server requires exactly one version marked as the storage version, and omitting it (or marking more than one) causes the CRD to fail registration outright.

### 5.2 Creating and Inspecting a Custom Resource

**Purpose:** Show a user-facing CR instance and how `kubectl` treats it identically to a built-in object once the CRD is registered.

**Syntax:**

```bash
kubectl apply -f my-postgres-cluster.yaml
kubectl get postgresclusters
kubectl describe pgc my-cluster
```

```yaml
apiVersion: databases.example.com/v1
kind: PostgresCluster
metadata:
  name: my-cluster
  namespace: production
spec:
  replicas: 3
  version: "15"
  storageSize: "100Gi"
```

**Production usage example:** Once an Operator's controller is running, `kubectl apply -f my-postgres-cluster.yaml` is the _entire_ user-facing interface for provisioning a production Postgres cluster — the Operator handles creating the underlying StatefulSet, Services, Secrets, and PVCs, and reconciling any drift, so application teams never touch those lower-level objects directly.

**Common errors:** Manually editing the Operator-managed derived objects (e.g., directly patching the StatefulSet an Operator created) instead of the CR's spec — the Operator's next reconciliation pass will typically detect and revert the manual change, since its desired state comes from the CR, not from the derived object.

### 5.3 Installing a Real-World Operator via OLM/Helm

**Purpose:** Show how Operators are typically distributed and installed in practice, rather than hand-built from scratch.

**Syntax:**

```bash
helm repo add postgres-operator https://opensource.zalando.com/postgres-operator/charts/postgres-operator
helm install postgres-operator postgres-operator/postgres-operator --namespace operators --create-namespace
kubectl get pods -n operators
```

**Production usage example:** Nearly all mature, widely-used Operators (Prometheus Operator, cert-manager, the Zalando/CrunchyData Postgres Operators, Strimzi for Kafka) ship as Helm charts ([§82](./Section-82-Part11-Helm-Fundamentals-Charts-Releases-Repositories.md)–[§83](./Section-83-Part11-Writing-Helm-Charts-Templates-Values-Helpers.md)) that install both the CRDs and the controller Deployment together — this is the practical convergence point between Part 11's earlier package-management material and this section's Operator content.

**Common errors:** Uninstalling an Operator's Helm release without first considering what happens to CRs it was managing — depending on the Operator, deleting the controller can leave existing CRs (and their underlying StatefulSets/PVCs) orphaned but still present, or in some configurations, CRD deletion cascades to delete every CR instance and its underlying storage, a data-loss risk worth verifying before any uninstall.

## 6. Production Usage Notes

- **CRD schema versioning follows the same conventions as core Kubernetes API groups** (`v1alpha1` → `v1beta1` → `v1`), and CRDs support **conversion webhooks** to translate between versions when a CRD evolves — directly analogous to the API versioning concepts covered for built-in groups in Part 2.
- **The Operator ecosystem has a maturity model (commonly described by the Operator Capability Levels: Basic Install, Seamless Upgrades, Full Lifecycle, Deep Insights, Auto Pilot)** — a "Basic Install" Operator only automates initial provisioning, while an "Auto Pilot" Operator can handle autonomous scaling, failure recovery, and tuning; evaluating where a candidate Operator sits on this spectrum is a meaningful part of due diligence before adopting one for a stateful production workload.
- **Not every CRD needs an Operator** — some CRDs (like Gateway API's `HTTPRoute`) exist purely as declarative configuration consumed by an existing controller (an ingress controller, in that example) rather than pairing with a dedicated custom controller of their own; recognizing this distinction avoids assuming every CRD implies a full Operator is running behind it.

## 7. Security Considerations

- **An Operator's ServiceAccount typically needs broad RBAC permissions across the resources it manages** (its own CRD, plus StatefulSets, Services, Secrets, PVCs it creates on users' behalf) — this makes the Operator's own Pod a high-value target, deserving the same SecurityContext hardening ([§45](../Part6/Section-45-Part6-SecurityContext-Pod-Container-Level.md)) and RBAC least-privilege scrutiny ([§75](../Part10/Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md)) as any other cluster-wide privileged component.
- **CRDs themselves are cluster-scoped objects**, meaning any user with permission to create/modify CRDs can introduce new API surface cluster-wide — RBAC control over the `customresourcedefinitions` resource itself (not just CR instances) is an easily overlooked but significant privilege boundary.
- **Malicious or buggy CR specs can drive an Operator into dangerous actions** if the Operator's reconciliation logic doesn't validate CR input defensively — a CRD's OpenAPI schema validation (see the hands-on CRD example above) is a necessary but not sufficient safeguard; the controller's own logic must also treat CR fields as untrusted input, not blindly trusted configuration.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                 | Cause                                                                                     | Fix                                                                                                          |
| ----------------------------------------------------------------------- | ----------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------ |
| `kubectl apply` on a CR fails with a schema validation error            | The CR's fields don't match the CRD's OpenAPI schema (wrong type, missing required field) | Compare the CR against `kubectl get crd <name> -o yaml` schema; fix the CR's fields                          |
| A CR is created but nothing happens — no derived objects appear         | No Operator/controller is actually running to watch that CRD, or it crashed               | Check for the Operator's Deployment/Pod; inspect its logs directly like any other controller                 |
| Manual edits to an Operator-managed StatefulSet keep reverting          | The Operator's reconciliation loop detects the drift from the CR's spec and corrects it   | Edit the CR's spec instead of the derived object directly — the CR is the actual source of truth             |
| Deleting a CRD unexpectedly deletes all its CR instances and their data | CRD deletion cascades to delete all CR instances (standard Kubernetes garbage collection) | Back up CR specs and underlying data before any CRD deletion; verify the Operator's finalizer behavior first |
| Operator upgrade breaks existing CRs                                    | New CRD version's schema is incompatible with CR instances created under the old version  | Use a conversion webhook, or migrate CR instances to the new schema version before upgrading the Operator    |

## 9. Best Practices

- Prefer well-established, actively maintained Operators (Prometheus Operator, cert-manager, Strimzi) distributed via Helm over hand-rolling a custom Operator, unless the operational domain genuinely has no mature existing option.
- Treat the CR's spec as the single source of truth for any Operator-managed resource — never manually edit the derived objects an Operator created, since reconciliation will typically revert unauthorized drift anyway.
- Scope an Operator's RBAC permissions as tightly as the resources it actually manages, and audit its ServiceAccount's bindings the same way any other cluster-wide privileged workload would be audited.
- Understand and test a CRD's deletion/cascade behavior in a non-production cluster before relying on it in production, given the real data-loss risk on CRD or CR deletion.

## 10. Common Anti-Patterns / Mistakes

- **Manually patching Operator-managed derived objects** (a StatefulSet, a Secret) instead of the CR's spec, fighting the reconciliation loop instead of working with it.
- **Adopting an immature, "Basic Install"-only Operator for a workload that actually needs deep lifecycle automation** (automated failover, backup/restore), then discovering the gap only during a real incident.
- **Granting an Operator's ServiceAccount cluster-admin-equivalent permissions "to be safe"** rather than scoping RBAC to the specific resources the Operator's documented responsibilities actually require.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a CRD and an Operator?"_
**Model answer:** A CRD is purely a schema registration — it tells the api-server about a new resource type, so instances of it (Custom Resources) can be validated, stored, and served through the normal Kubernetes API, but a CRD by itself has no behavior. An Operator is a CRD paired with a custom controller that actually watches CR instances and reconciles real-world state to match their spec. A CRD without a controller is just inert structured storage; the Operator is what makes it operational.
_What the interviewer is probing for:_ Clear separation between the API-extension mechanism (CRD) and the behavior-providing mechanism (the controller) that together constitute an Operator.

**🎯 Intermediate:** _"A user reports that a Custom Resource they created isn't doing anything — no underlying Pods or Services appeared. How would you debug this?"_
**Model answer:** First I'd confirm the CRD itself is correctly registered and the CR was actually accepted (`kubectl get <cr-type>`, checking for schema validation errors on creation). Then I'd check whether an Operator is actually running and watching that CRD at all — `kubectl get pods` for the Operator's namespace, since a CR sitting inert with no controller watching it is functionally indistinguishable from a broken Operator until you check. If the Operator Pod exists, I'd check its logs directly, the same as debugging any other controller ([§13](../Part2/Section-13-Part2-Controller-Manager-Controller-Pattern-Reconciliation-Loops.md)) — reconciliation errors, RBAC permission denials preventing it from creating derived objects, or a stalled watch connection are the most common root causes.
_What the interviewer is probing for:_ Applying the "CR is inert without a controller" mental model to a concrete debugging workflow, and treating an Operator's own logs as the primary diagnostic source, same as any other controller.

**🎯 Senior:** _"Why is CRD deletion behavior a genuine production risk, and how would you guard against it?"_
**Model answer:** Deleting a CRD triggers Kubernetes' standard garbage collection to delete every existing instance of that Custom Resource, and depending on the Operator's finalizer logic, that in turn can cascade to delete the underlying StatefulSets, PVCs, and real data those CRs were managing — a single `kubectl delete crd` on a database Operator's CRD could delete every managed database cluster's storage cluster-wide, which is a far larger blast radius than deleting a single object typically implies. I'd guard against this with RBAC restricting who can delete CRDs at all (a cluster-scoped, high-privilege action that shouldn't be broadly granted), documented and tested backup/restore procedures independent of the CR's continued existence, and where the Operator supports it, verifying its finalizer behavior in a non-production cluster so the actual cascade behavior is known and not assumed.
_What the interviewer is probing for:_ Recognizing that CRD deletion has a genuinely different, much larger blast radius than deleting an individual object, and translating that into concrete operational safeguards (RBAC scoping, backup independence, tested cascade behavior).

**🎯 Architect:** _"Your organization is evaluating whether to adopt a third-party Operator for managing a stateful system versus building one in-house. What framework would you use to decide?"_
**Model answer:** I'd start with the Operator Capability Level model — Basic Install through Auto Pilot — and map the candidate third-party Operator's actual, documented capabilities against what our operational needs genuinely require; a mismatch here (adopting a Basic-Install-only Operator for a system that needs automated failover) is a common and costly discovery made too late, during an incident rather than during evaluation. I'd weigh maintenance burden and community health (release cadence, issue responsiveness, CVE history) against the in-house-build alternative, since a hand-rolled Operator inherits the full ongoing burden of correctly implementing idempotent, interruption-tolerant reconciliation ([§13](../Part2/Section-13-Part2-Controller-Manager-Controller-Pattern-Reconciliation-Loops.md)) for a domain as complex as a stateful system — a nontrivial, easy-to-underestimate engineering investment. I'd also scope the Operator's RBAC footprint explicitly as part of the evaluation, verify its CRD deletion/cascade behavior in a sandboxed cluster before any production adoption, and confirm it's distributed via a maintained Helm chart ([§82](./Section-82-Part11-Helm-Fundamentals-Charts-Releases-Repositories.md)–[§83](./Section-83-Part11-Writing-Helm-Charts-Templates-Values-Helpers.md)) so upgrades follow our existing package-management workflow rather than a bespoke installation process. Ultimately, I'd default to a mature, widely-adopted third-party Operator unless our system's operational requirements are genuinely unique enough that no existing option's capability level and RBAC/security posture meet our bar.
_What the interviewer is probing for:_ A structured evaluation framework (capability maturity, maintenance burden, security posture, packaging/upgrade path) rather than an ad hoc build-vs-buy gut call, and awareness of the concrete risks (RBAC scope, cascade deletion) an architect must verify before committing.

## 12. Common Misconceptions

1. **"A CRD alone gives Kubernetes new behavior."** A CRD only registers a new schema/resource type — it has zero behavior on its own; an Operator's controller is what supplies reconciliation logic.
2. **"Every CRD implies a dedicated Operator is running behind it."** Some CRDs (like Gateway API's `HTTPRoute`) are purely declarative configuration consumed by an existing, separately-running controller, not paired with their own dedicated Operator.
3. **"Operators are a fundamentally different mechanism from built-in Kubernetes controllers."** They use the identical watch/compare/act reconciliation pattern covered in [§13](../Part2/Section-13-Part2-Controller-Manager-Controller-Pattern-Reconciliation-Loops.md), just applied to a user-defined resource type instead of a built-in one.
4. **"Editing an Operator's derived objects (StatefulSets, Secrets) directly is a safe shortcut."** The Operator's own reconciliation loop typically detects and reverts such drift, since the CR's spec — not the derived object — is its actual source of truth.

## 13. 🔑 Key Takeaways

- A CRD extends the Kubernetes API with a new resource type, validated and stored via the same api-server machinery as built-in objects — but has no behavior on its own.
- An Operator pairs a CRD with a custom controller that reconciles real-world state to match CR specs, using the exact watch/compare/act loop covered for built-in controllers in [§13](../Part2/Section-13-Part2-Controller-Manager-Controller-Pattern-Reconciliation-Loops.md).
- CRD/CR deletion has an outsized blast radius (cascading deletion of derived objects and real data), making RBAC control over CRD deletion and tested backup independence essential production safeguards.
- The Operator Capability Level model (Basic Install through Auto Pilot) is a useful framework for evaluating whether a candidate Operator's actual automation depth matches operational needs.
- Prefer mature, actively maintained Operators distributed via Helm over hand-rolled custom controllers unless the operational domain has no viable existing option.

## 14. Related Concepts & What's Next

This section generalized [§13](../Part2/Section-13-Part2-Controller-Manager-Controller-Pattern-Reconciliation-Loops.md)'s controller pattern to user-defined resource types via CRDs, and connected back to [§85](./Section-85-Part11-Helm-vs-Kustomize-vs-Raw-Manifests-Decision-Framework.md)'s Helm/Kustomize decision framework, since Operators are typically distributed as Helm charts. [§87](./Section-87-Part11-Custom-Controllers-Conceptual-Overview-controller-runtime.md), next, goes deeper into how a custom controller's reconciliation logic is actually implemented in practice — the `controller-runtime` library, informers, work queues, and reconcile functions that power the Operator pattern introduced here.

**Next Section:** [§87](./Section-87-Part11-Custom-Controllers-Conceptual-Overview-controller-runtime.md) — `Section-87-Part11-Custom-Controllers-Conceptual-Overview-controller-runtime.md`
