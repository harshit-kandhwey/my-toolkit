# Section 75 (Part 10): RBAC Deep Dive: Roles, ClusterRoles, RoleBindings, ClusterRoleBindings

## 1. Definition

**Plain language:** RBAC is where Kubernetes permissions actually get written down as concrete, reviewable, version-controllable YAML — instead of a vague notion of "jane can deploy things," RBAC forces every permission into an explicit statement: this exact set of verbs, against this exact set of resources, in this exact scope, granted to this exact identity. It's the single most hands-on, most exam-relevant mechanism in Kubernetes' entire security model.

**Precise definition:** **RBAC (Role-Based Access Control)** is implemented through four API objects working in two paired sets. A **Role** defines a set of permission **rules** (`apiGroups`, `resources`, `verbs`, optionally `resourceNames`) scoped to a single **namespace**; a **ClusterRole** defines the same kind of rules but scoped **cluster-wide**, and can also grant access to cluster-scoped resources (Nodes, PersistentVolumes, Namespaces themselves) that a namespaced Role cannot reference at all. A **RoleBinding** grants the permissions of a Role (or, notably, a ClusterRole) to one or more **subjects** (Users, Groups, or ServiceAccounts) — but critically, a RoleBinding's grant is always scoped to the RoleBinding's own namespace, even when it references a ClusterRole. A **ClusterRoleBinding** grants a ClusterRole's permissions cluster-wide, across every namespace, with no namespace scoping at all. This four-object model — two permission-definition objects (Role/ClusterRole) crossed with two grant-scope objects (RoleBinding/ClusterRoleBinding) — is the entire vocabulary of native Kubernetes authorization policy.

## 2. Why This Matters

- **RBAC is the primary, hands-on mechanism both CKA and CKAD test directly and repeatedly** — creating Roles, RoleBindings, and diagnosing why a ServiceAccount lacks an expected permission are some of the single most common exam task types across both certifications.
- **The distinction between a RoleBinding referencing a ClusterRole (namespace-scoped grant) versus a ClusterRoleBinding (cluster-wide grant) of that exact same ClusterRole is one of the most consequential, most frequently misunderstood details in all of Kubernetes RBAC** — the same ClusterRole object can be reused either way, and confusing the two is a common source of both broken workloads and accidental over-permissioning.
- **RBAC is purely additive with no explicit deny rule**, which means the entire practice of designing safe RBAC policy is fundamentally about careful, minimal granting — least privilege isn't a nice-to-have here, it's the only lever available at all.

🔑 **Key Takeaway:** RBAC's four objects pair permission definitions (Role/ClusterRole) with grant scopes (RoleBinding/ClusterRoleBinding); a RoleBinding can reference a ClusterRole to grant its permissions within just one namespace, while a ClusterRoleBinding grants that same ClusterRole cluster-wide — and because RBAC has no deny rule, least-privilege design is the only real safeguard against over-permissioning.

## 3. Prerequisites and Dependencies

Builds directly on §74 (Authorization Modes, where RBAC was introduced as the default/near-universal authorization mode) and §73 (Authentication, providing the Users/Groups/ServiceAccounts that RBAC subjects reference). Assumes familiarity with namespace concepts from earlier Parts.

## 4. Architecture: The Four-Object RBAC Model

```text
┌────────────────────────────────┐          ┌─────────────────────────────────┐
│         Role                   │          │        ClusterRole              │
│  (namespace-scoped rules)      │          │  (cluster-scoped rules;         │
│  apiGroups, resources, verbs   │          │   can target cluster-scoped     │
│  e.g. "pods", "get/list/watch" │          │   resources like Nodes, PVs)    │
└──────────────┬─────────────────┘          └────┬──────────────────────┬─────┘
               │                                 │                      |
     bound by  │                        bound by │                      |bound by
               ▼                                 ▼                      ▼
     ┌───────────────────────┐         ┌──────────────────────┐  ┌──────────────────────┐
     │   RoleBinding         │         │   RoleBinding        │  │  ClusterRoleBinding  |
     │  (grants Role within  │         │  (grants CLUSTERROLE │  │  (grants ClusterRole │
     │   its OWN namespace)  │         │   but scoped to ONE  │  │   CLUSTER-WIDE, every│
     │                       │         │   namespace only!)   │  │   namespace)         │
     └──────────┬────────────┘         └────────┬─────────────┘  └────────────┬─────────┘
                │                               │                             │
                ▼                               ▼                             ▼
     Subject can act on Role's     Subject can act on ClusterRole's     Subject can act on ClusterRole's
     rules, ONLY in the            rules, ONLY in the RoleBinding's     rules, in EVERY namespace
     RoleBinding's namespace       OWN namespace (not cluster-wide!)    AND on cluster-scoped resources
```

- **A RoleBinding referencing a ClusterRole is a deliberately common, useful pattern** — it lets platform teams define a single reusable ClusterRole (e.g., a standard "view" or "edit" permission set) once, then grant it narrowly, namespace by namespace, via separate RoleBindings, avoiding rule duplication while still keeping each grant properly scoped.
- **Only a ClusterRole (never a plain Role) can grant access to cluster-scoped resources** — Nodes, PersistentVolumes, Namespaces, StorageClasses — because a Role's rules are inherently namespace-bound and these resources simply don't belong to any namespace.
- **RBAC evaluation is purely additive across every binding that applies to a subject** — if a user has three different RoleBindings each granting different permissions, the user's effective permission is the union of all three; there is no mechanism to have one binding subtract or restrict what another grants.

## 5. Hands-On: Defining and Binding RBAC Policy

### 5.1 A Namespaced Role and RoleBinding

**Purpose:** Grant a specific, minimal set of permissions scoped to exactly one namespace — the most common RBAC pattern for application teams.

**Syntax:**

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
  namespace: production
rules:
  - apiGroups: [""] # core API group
    resources: ["pods", "pods/log"]
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: jane-pod-reader
  namespace: production
subjects:
  - kind: User
    name: jane
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
```

**Example usage and expected output:**

```bash
$ kubectl apply -f pod-reader-role.yaml
role.rbac.authorization.k8s.io/pod-reader created
rolebinding.rbac.authorization.k8s.io/jane-pod-reader created

$ kubectl auth can-i get pods --as=jane -n production
yes
$ kubectl auth can-i get pods --as=jane -n staging
no   # Role and RoleBinding are both scoped to "production" only
```

**Production usage example:** This exact pattern — read-only access to Pods and their logs, scoped to a single namespace — is the standard baseline grant for an on-call engineer or a support team member who needs to observe application behavior without being able to modify or delete anything.

**Common errors:** Forgetting `apiGroup: rbac.authorization.k8s.io` in the `roleRef` or `subjects` block — a common copy-paste mistake that produces a binding the API server rejects or silently fails to apply correctly.

### 5.2 A ClusterRole Bound Narrowly via a Namespaced RoleBinding

**Purpose:** Demonstrate the reusable-ClusterRole-bound-namespace-by-namespace pattern directly, and contrast it explicitly against a ClusterRoleBinding.

**Syntax:**

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: deployment-editor
rules:
  - apiGroups: ["apps"]
    resources: ["deployments"]
    verbs: ["get", "list", "watch", "update", "patch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding # NOTE: RoleBinding, not ClusterRoleBinding
metadata:
  name: team-a-deployment-editor
  namespace: team-a
subjects:
  - kind: Group
    name: team-a-engineers
    apiGroup: rbac.authorization.k8s.io
roleRef:
  kind: ClusterRole # references a CLUSTER-SCOPED role definition
  name: deployment-editor
  apiGroup: rbac.authorization.k8s.io
```

**Example usage and expected output:**

```bash
$ kubectl auth can-i update deployments --as-group=team-a-engineers -n team-a
yes
$ kubectl auth can-i update deployments --as-group=team-a-engineers -n team-b
no   # same ClusterRole, but this RoleBinding only grants it within "team-a"
```

**Production usage example:** A platform team typically defines one `deployment-editor` ClusterRole exactly once, then creates a lightweight RoleBinding per team's namespace referencing that same ClusterRole — this avoids duplicating the same rule set repeatedly across dozens of namespaces while still keeping each team's grant properly isolated to their own namespace.

**Common errors:** Accidentally creating a **ClusterRoleBinding** instead of a **RoleBinding** when the intent was namespace-scoped access — this single object-type mistake silently grants the permission cluster-wide across every namespace, a serious, easy-to-miss over-permissioning bug since both objects reference the ClusterRole identically.

### 5.3 A ClusterRoleBinding for Genuinely Cluster-Wide Access

**Purpose:** Show the correct, deliberate use of a ClusterRoleBinding, reserved for identities that legitimately need cluster-wide scope.

**Syntax:**

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: node-viewer
rules:
  - apiGroups: [""]
    resources: ["nodes"] # cluster-scoped resource — only valid via ClusterRole
    verbs: ["get", "list", "watch"]
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: monitoring-node-viewer
subjects:
  - kind: ServiceAccount
    name: monitoring-agent
    namespace: monitoring
roleRef:
  kind: ClusterRole
  name: node-viewer
  apiGroup: rbac.authorization.k8s.io
```

**Example usage and expected output:**

```bash
$ kubectl auth can-i get nodes \
    --as=system:serviceaccount:monitoring:monitoring-agent
yes   # ClusterRoleBinding — genuinely cluster-wide, no namespace boundary applies
```

**Production usage example:** A cluster-wide monitoring agent (Prometheus's node-exporter DaemonSet controller, for instance) that needs to read Node metadata across the entire cluster is exactly the legitimate case for a ClusterRoleBinding — Nodes are cluster-scoped resources, so no namespaced RoleBinding could grant this access even if one were attempted.

**Common errors:** Granting a ClusterRoleBinding "just to be safe" or "to avoid future permission issues" for a workload that only actually needs namespace-scoped access — this is the single most common RBAC over-permissioning pattern and directly violates least privilege.

## 6. Production Usage Notes

- **`kubectl create role` and `kubectl create rolebinding` (and their `clusterrole`/`clusterrolebinding` equivalents) support fast imperative creation** for exam conditions and quick iteration, but production RBAC policy should be version-controlled YAML, reviewed like any other infrastructure change, given how directly it controls blast radius.
- **Kubernetes ships several built-in ClusterRoles** (`view`, `edit`, `admin`, `cluster-admin`) providing sensible, pre-defined permission tiers — `cluster-admin` in particular grants unrestricted access to everything and should be bound extremely sparingly, typically only to genuine cluster operators, never to application workloads.
- **`kubectl describe rolebinding` and `kubectl describe clusterrolebinding` show the resolved subjects and roleRef directly**, making them the fastest way to audit exactly who holds a given grant without manually cross-referencing YAML files.

## 7. Security Considerations

- **RBAC has no explicit deny rule — every grant is additive, and the effective permission for any identity is the union of every applicable Role/ClusterRole granted through every RoleBinding/ClusterRoleBinding that targets it**, which means auditing "what can this identity actually do" requires checking _all_ bindings that reference it, not just the one you remember creating.
- **`resourceNames` can scope a Role's grant to specific named objects** (e.g., `get` access to only one specific Secret by name) rather than every object of that resource type — a valuable but underused fine-graining tool for genuinely sensitive individual resources.
- **Wildcard verbs or resources (`verbs: ["*"]`, `resources: ["*"]`) in a Role or ClusterRole should be treated as a serious red flag during any security review** — they're occasionally necessary for a small number of genuinely broad administrative roles, but are far too often used as a lazy shortcut that silently grants much more than intended.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                           | Likely Cause                                                                                                    | Resolution Path                                                                                         |
| --------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------- |
| A RoleBinding referencing a ClusterRole doesn't grant access in another namespace | Expected behavior — a RoleBinding always scopes the grant to its own namespace regardless of what it references | Use a ClusterRoleBinding instead if cluster-wide (or create a separate RoleBinding per namespace)       |
| A ServiceAccount has unexpectedly broad, cluster-wide access                      | A ClusterRoleBinding was created where a namespaced RoleBinding was intended                                    | Audit `kubectl get clusterrolebindings -o yaml`, replace with a properly scoped RoleBinding             |
| `kubectl auth can-i` reports `no` despite an apparently matching Role             | RoleBinding references the wrong Role/ClusterRole name, or `apiGroup` typo in `roleRef`/`subjects`              | `kubectl describe rolebinding <name>`, confirm exact `roleRef` name and subject identity strings match  |
| A Role's rule for a cluster-scoped resource (e.g., `nodes`) has no effect         | Roles cannot grant access to cluster-scoped resources at all — only ClusterRoles can                            | Convert the rule to a ClusterRole, bound via RoleBinding (namespace-scoped grant) or ClusterRoleBinding |

## 9. Best Practices

- Default to the narrowest object (Role + RoleBinding) unless cluster-wide scope or a cluster-scoped resource genuinely requires a ClusterRole/ClusterRoleBinding.
- Reuse a small set of well-designed ClusterRoles across many namespaces via per-namespace RoleBindings, rather than duplicating near-identical Role definitions repeatedly.
- Audit `resources: ["*"]` or `verbs: ["*"]` wherever they appear in any Role or ClusterRole as a mandatory security review checkpoint, not a routine convenience.

## 10. Common Anti-Patterns / Mistakes

- **Creating a ClusterRoleBinding when a namespaced RoleBinding was intended**, silently granting cluster-wide access due to the two objects' near-identical naming and structure.
- **Binding `cluster-admin` to a workload's ServiceAccount** "temporarily" to unblock a permission issue, without ever narrowing it back down afterward.
- **Relying entirely on the built-in `edit`/`admin` ClusterRoles for every team** without evaluating whether their broad, generic permission sets actually match that team's genuine, narrower needs.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between a Role and a ClusterRole?"_
**Model answer:** A Role's rules are scoped to a single namespace — it can only grant permissions on namespaced resources within that one namespace. A ClusterRole's rules are cluster-scoped and can additionally grant access to genuinely cluster-scoped resources like Nodes or PersistentVolumes that don't belong to any namespace. Importantly, a ClusterRole can still be bound narrowly to just one namespace via a RoleBinding — the object itself being "cluster-scoped" refers to where its rules can apply, not automatically to how broadly it gets granted.
_What the interviewer is probing for:_ Basic grasp of the namespace-scoped versus cluster-scoped rule distinction.

**🎯 Intermediate:** _"If I bind a ClusterRole using a RoleBinding instead of a ClusterRoleBinding, what's the actual effect?"_
**Model answer:** The ClusterRole's permission rules still apply, but the grant itself is scoped to only the namespace the RoleBinding lives in — the subject gets those permissions in that one namespace, not cluster-wide. This is a genuinely useful, common pattern for reusing one centrally-defined ClusterRole across many teams' namespaces without duplicating rule definitions, but it's frequently confused with a ClusterRoleBinding, which would grant that same ClusterRole's permissions across every namespace in the cluster — a much broader, often unintended, over-permissioning outcome if the two are mixed up.
_What the interviewer is probing for:_ The single most commonly tested, commonly misunderstood RBAC detail — that grant scope comes from the binding object type, not the role object type.

**🎯 Senior:** _"You inherit a cluster where several ServiceAccounts are bound to `cluster-admin`. How do you safely narrow their permissions without breaking production workloads?"_
**Model answer:** I would never simply revoke `cluster-admin` bindings outright without first understanding actual usage, since that risks an immediate outage. I'd start by auditing the Kubernetes audit log (§89, Part 12) for each affected ServiceAccount over a representative time window to see exactly which verbs and resources it actually exercises in practice, rather than guessing from the workload's code. From that observed usage, I'd construct a minimal, purpose-specific Role or ClusterRole covering only those actual operations, bind it via the narrowest appropriate object (RoleBinding if the usage is namespace-confined, ClusterRoleBinding only if genuinely cluster-wide access is exercised), and roll it out in a non-production environment first with continued audit-log monitoring to catch any missed permission before promoting the change to production. Only once the narrowed role has run cleanly for a representative period would I remove the original `cluster-admin` binding.
_What the interviewer is probing for:_ A safe, evidence-based methodology for de-risking an over-permissioned production system, not just "delete the binding and see what breaks."

**🎯 Architect:** _"Design an RBAC strategy for a multi-tenant platform where dozens of teams each own one or more namespaces, and a smaller platform team needs cross-cutting operational access."_
**Model answer:** I'd define a small library of reusable ClusterRoles representing common permission tiers — a `namespace-viewer`, `namespace-developer` (deploy/scale/rollback within a namespace, no Secret access), and `namespace-admin` (adds Secret and RBAC-object management within that namespace) — each carefully scoped to only namespaced resources so they can never be accidentally over-granted via a ClusterRoleBinding by mistake. Each tenant team gets RoleBindings (never ClusterRoleBindings) in their own namespace(s) referencing these shared ClusterRoles, mapped to their OIDC group (§73) rather than individual usernames, so team membership changes propagate automatically. For the platform team's genuine cross-cutting needs — Node visibility, cluster-wide monitoring read access — I'd define separate, narrowly-scoped ClusterRoles bound via ClusterRoleBindings only for the specific resources that are genuinely cluster-scoped or genuinely need cross-namespace visibility, resisting the temptation to just grant `cluster-admin` for convenience. I'd enforce this entire structure through a GitOps-managed RBAC repository (tying into §88's GitOps material) with mandatory review on any new ClusterRoleBinding or `cluster-admin` reference, since those are exactly the objects most likely to introduce unintended blast radius at platform scale.
_What the interviewer is probing for:_ Ability to design a scalable, tenant-isolated RBAC architecture that balances reusability against the risk of accidental over-permissioning, and to translate policy into an enforced, auditable process rather than tribal knowledge.

## 12. Common Misconceptions

1. **"A RoleBinding referencing a ClusterRole grants that ClusterRole's permissions cluster-wide."** It does not — the grant is always scoped to the RoleBinding's own namespace; only a ClusterRoleBinding grants cluster-wide scope.
2. **"RBAC supports explicit deny rules to restrict specific permissions."** It does not — RBAC is purely additive; the only way to "remove" a permission is to not grant it (or remove the binding/rule that grants it) in the first place.
3. **"A Role can grant access to cluster-scoped resources like Nodes if I just add them to its `resources` list."** A plain Role's rules simply have no effect on cluster-scoped resources regardless of what's listed — only a ClusterRole can grant access to them.
4. **"Built-in ClusterRoles like `edit` are always the right choice for a team's default permission set."** They're convenient generic defaults but often grant more (or less precisely scoped) access than a given team's actual, narrower needs — purpose-built Roles/ClusterRoles are frequently the more defensible choice.

## 13. 🔑 Key Takeaways

- RBAC's four objects pair permission definitions (Role: namespace-scoped, ClusterRole: cluster-scoped) with grant-scope objects (RoleBinding: scoped to its own namespace even for a ClusterRole, ClusterRoleBinding: genuinely cluster-wide).
- A RoleBinding referencing a ClusterRole is a deliberate, common reuse pattern — it does not grant cluster-wide access, only namespace-scoped access within the RoleBinding's own namespace.
- Only ClusterRoles can grant access to cluster-scoped resources (Nodes, PersistentVolumes, Namespaces) — a plain Role's rules on such resources have no effect.
- RBAC has no explicit deny; effective permission for any identity is the union of every applicable binding, making least-privilege design the only real safeguard.
- `cluster-admin` and wildcard verbs/resources should be treated as serious red flags in any security review, reserved for genuinely justified, narrowly-held cases.

## 14. Related Concepts & What's Next

This section builds directly on §74's introduction of RBAC as an authorization mode, going fully hands-on with its four core objects. §76 continues the identity thread specifically for workloads, covering ServiceAccount tokens, auto-mounting behavior, and the modern Bound Service Account Token mechanism that these RoleBindings and ClusterRoleBindings ultimately grant permissions to.

**Next Section:** §76 — `Section-76-Part10-ServiceAccounts-Tokens-Auto-Mounting-Bound-Tokens.md`
