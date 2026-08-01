# Section 74 (Part 10): Authorization Modes: RBAC, ABAC, Node, Webhook

## 1. Definition

**Plain language:** Once the API server knows _who_ is making a request (§73), it needs a separate mechanism to decide _what that identity is allowed to do_. Authorization is that decision layer — and unlike authentication, where a cluster typically settles on one or two mechanisms, a Kubernetes cluster can have several authorization modes active simultaneously, each getting a chance to approve a request before it's denied.

**Precise definition:** **Authorization** is the stage of the API server request lifecycle, immediately following authentication, that determines whether an already-identified user, group, or ServiceAccount may perform a specific **verb** (get, list, create, update, delete, watch, patch) against a specific **resource** (pods, secrets, deployments) in a specific **namespace** (or cluster-wide). Kubernetes supports four **authorization modes**, configured via the API server's `--authorization-mode` flag as an ordered, comma-separated list: **RBAC** (Role-Based Access Control — declarative, API-object-based, the de facto default in every modern cluster), **ABAC** (Attribute-Based Access Control — static policy files evaluated against request attributes, largely legacy), **Node** (a specialized authorizer granting kubelets access scoped only to resources related to their own node), and **Webhook** (delegating the authorization decision to an external HTTP service). When multiple modes are configured, the API server evaluates them in order and grants access on the **first explicit allow**; if every configured mode either denies or has no opinion, the request is rejected with `403 Forbidden`.

## 2. Why This Matters

- **RBAC is, in practice, the only authorization mode virtually every modern production cluster relies on for user- and workload-facing permissions**, and both CKA and CKS treat RBAC configuration as core, hands-on exam material — but understanding it in the context of the other three modes clarifies exactly what problem RBAC solves and why the alternatives largely fell out of favor.
- **The Node authorizer is what makes kubelet-to-API-server communication safe by default**, restricting each kubelet to only the Pods, Secrets, ConfigMaps, and other objects related to workloads scheduled on its own node — without it, a compromised kubelet could read every Secret in the cluster, not just those relevant to its own node.
- **Understanding the "first explicit allow wins" evaluation order is essential for correctly reasoning about multi-mode clusters**, especially in organizations still running a legacy Webhook or ABAC authorizer alongside RBAC during a migration — a request that RBAC would deny can still succeed if an earlier-evaluated mode explicitly allows it.

🔑 **Key Takeaway:** Kubernetes authorization decides what an already-authenticated identity can do, evaluated across one or more configured modes (RBAC, ABAC, Node, Webhook) in order with first-explicit-allow winning; RBAC is the modern default and the near-universal choice for both human and workload permissions in production clusters.

## 3. Prerequisites and Dependencies

Builds directly on §73 (Authentication — the username/group identity that authorization decisions are made against). Assumes familiarity with the Pod spec anatomy (§24) and basic namespace concepts. Forward-references §75 for the full mechanics of RBAC's own API objects.

## 4. Architecture: The Authorization Decision Chain

```text
┌──────────────────────────────────────────────────────────────────┐
│  Authenticated request: user "jane", groups ["engineering"]      │
│  wants to: GET pods in namespace "production"                    │
└──────────────────────────────┬───────────────────────────────────┘
                               │
                               ▼
        ┌──────────────────────────────────────────────────────────┐
        │  --authorization-mode=Node,RBAC   (order matters!)       │
        │                                                          │
        │  1. Node authorizer                                      │
        │     - Applies only to kubelet identities                 │
        │     - "jane" is not a kubelet → NO OPINION, pass through │
        │                                                          │
        │  2. RBAC authorizer                                      │
        │     - Checks all RoleBindings/ClusterRoleBindings        │
        │       for "jane" or group "engineering"                  │
        │     - Finds a RoleBinding granting "get pods" in         │
        │       "production" → EXPLICIT ALLOW                      │
        └──────────────────────────┬───────────────────────────────┘
                                   │ first explicit allow found
                                   ▼
                          Request proceeds to
                          Admission Controllers (§77)

  If NO configured mode explicitly allows the request:
                          403 Forbidden
```

- **A mode with "no opinion" is not the same as a denial** — the Node authorizer, for example, simply abstains on any request from a non-kubelet identity, passing evaluation to the next configured mode rather than blocking it.
- **Order in `--authorization-mode` is significant only in the sense that evaluation proceeds left to right until an explicit allow is found** — there is no equivalent of RBAC's explicit-deny concept across modes; authorization overall is purely additive (allow-only), never subtractive.
- **RBAC itself has no explicit "deny" rule type** — a Role or ClusterRole can only grant permissions, never revoke them, which is why RBAC policy design is fundamentally an allow-list exercise (full mechanics in §75).

## 5. Hands-On: Configuring and Observing Authorization Modes

### 5.1 Inspecting and Setting the Authorization Mode

**Purpose:** Show where `--authorization-mode` is configured and how to confirm which modes are active on a running cluster.

**Syntax:**

```bash
# On a kubeadm-managed control plane node
cat /etc/kubernetes/manifests/kube-apiserver.yaml | grep authorization-mode
```

```yaml
# Excerpt of the kube-apiserver static Pod manifest
spec:
  containers:
    - command:
        - kube-apiserver
        - --authorization-mode=Node,RBAC
        - --authorization-webhook-config-file=/etc/kubernetes/webhook-config.yaml # only if Webhook is used
```

**Example usage and expected output:**

```bash
$ kubectl auth can-i get pods --as=jane -n production
yes

$ kubectl auth can-i delete deployments --as=jane -n production
no
```

**Production usage example:** `kubectl auth can-i --as=<user> --as-group=<group>` is the standard, fast diagnostic for checking effective permissions without needing to actually attempt the action or trace through every RoleBinding manually — it's one of the most frequently used commands during both RBAC design and CKA/CKAD exam troubleshooting scenarios.

**Common errors:** Editing the static Pod manifest's `--authorization-mode` flag directly on a running control plane node without understanding that the kubelet will restart the API server container automatically on file change — this is expected `kubeadm` behavior, but doing it without warning teammates during a live cluster can look like an unplanned outage.

### 5.2 The Node Authorizer in Action

**Purpose:** Demonstrate the specific, narrow scope the Node authorizer grants to kubelet identities, distinct from any RBAC grant.

**Syntax:**

```bash
# A kubelet's identity is a special "system:node:<nodename>" user,
# in the "system:nodes" group, authenticated via its own client certificate
$ kubectl get csr | grep node
csr-abc123   ...   system:node:worker-3   Approved,Issued
```

**Example usage and expected output:**

```bash
$ kubectl auth can-i get secrets --as=system:node:worker-3 -n production
no  # Node authorizer restricts a kubelet to Secrets referenced by Pods scheduled on ITS node only

$ kubectl auth can-i get pods --as=system:node:worker-3 --namespace=production
yes  # only for Pods actually scheduled to worker-3
```

**Production usage example:** This narrow scoping is precisely why a compromised kubelet on one worker node cannot be used to exfiltrate every Secret in the cluster — it can only read the Secrets that Pods scheduled on that specific node actually reference, dramatically limiting the blast radius of a single-node compromise.

**Common errors:** Assuming a kubelet has broad read access to cluster state the way a cluster-admin ServiceAccount would — the Node authorizer is deliberately restrictive, and workloads that genuinely need broader API access (a monitoring DaemonSet reading Pod metadata cluster-wide, for instance) must be granted that access through RBAC bound to their own ServiceAccount, not by relying on kubelet identity.

### 5.3 Webhook Authorization for External Policy Decisions

**Purpose:** Show the shape of Webhook authorization, used when an organization needs authorization decisions made by an external policy engine rather than native RBAC alone.

**Syntax:**

```yaml
# webhook-config.yaml — kubeconfig-style file pointing at the external authorizer
apiVersion: v1
kind: Config
clusters:
  - name: external-authz
    cluster:
      server: https://policy-engine.example.com/authorize
      certificate-authority: /etc/kubernetes/pki/webhook-ca.crt
contexts:
  - context: { cluster: external-authz, user: api-server }
    name: webhook
current-context: webhook
```

**Example usage and expected output:**

```bash
# The API server POSTs a SubjectAccessReview object to the webhook endpoint
$ curl -s -X POST https://policy-engine.example.com/authorize -d '{
  "apiVersion": "authorization.k8s.io/v1",
  "kind": "SubjectAccessReview",
  "spec": {"user": "jane", "resourceAttributes": {"verb": "delete", "resource": "deployments"}}
}'
# Response includes {"status": {"allowed": false, "reason": "outside change window"}}
```

**Production usage example:** Webhook authorization is typically layered _alongside_ RBAC (not instead of it) to enforce organization-specific policy that doesn't map cleanly onto RBAC's static role model — for example, denying `delete` operations outside an approved change window, a decision that depends on time-of-day context RBAC has no native way to express.

**Common errors:** Treating Webhook authorization as a replacement for RBAC rather than a complement — most production uses layer it for a narrow set of extra, dynamic policy checks on top of an RBAC baseline that still handles the bulk of everyday permission decisions.

## 6. Production Usage Notes

- **ABAC is effectively legacy** in modern Kubernetes — it requires a static JSON policy file on every control plane node with no dynamic update mechanism (a full API server restart is needed to pick up changes), which RBAC's live, API-object-based model made largely obsolete; new clusters essentially never enable it.
- **The recommended, near-universal `--authorization-mode` setting for a self-managed cluster is `Node,RBAC`** — this combination handles both kubelet-scoped access and all human/workload permissions without needing ABAC or Webhook at all, unless a genuine need for external dynamic policy exists.
- **Managed Kubernetes offerings (EKS, AKS, GKE) each pre-configure authorization modes as part of the managed control plane** and typically don't expose the raw `--authorization-mode` flag for direct editing — RBAC configuration (§75) remains the primary lever available to cluster operators on these platforms.

## 7. Security Considerations

- **Because authorization across modes is purely additive (first explicit allow wins, with no cross-mode deny), adding a permissive mode like ABAC or a loosely configured Webhook authorizer alongside RBAC can inadvertently widen access** beyond what the RBAC policy alone would allow — every additional authorization mode is itself an expansion of the attack surface for privilege escalation, not merely an alternative path.
- **The Node authorizer's scoping to "resources related to the requesting node" is a meaningful, security-relevant boundary** — verifying it's actually enabled (`Node` present in `--authorization-mode`) is a standard CKS-level cluster hardening check, since its absence would let any kubelet with a valid certificate query cluster-wide resources via RBAC roles bound too broadly to `system:nodes`.
- **A Webhook authorizer that fails open (treats a timeout or error from the external service as an allow) is a serious misconfiguration** — the webhook's failure policy should always default to deny, since an unreachable policy engine should never silently grant unrestricted access.

## 8. Common Troubleshooting Scenarios

| Symptom                                                                            | Likely Cause                                                                                               | Resolution Path                                                                                                                    |
| ---------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| A request is unexpectedly allowed despite no matching RBAC binding                 | Another authorization mode (Webhook or legacy ABAC) is explicitly allowing it before RBAC is reached       | Review `--authorization-mode` order and each mode's policy independently, not just RBAC                                            |
| Every request from a kubelet fails against resources it should legitimately access | Node authorizer misconfigured, or kubelet's client certificate isn't in the `system:nodes` group correctly | Verify the kubelet's certificate CN/group via `kubectl get csr` and confirm `Node` is in `--authorization-mode`                    |
| `kubectl auth can-i` reports `yes` but the actual `kubectl` command still fails    | A subsequent admission controller (§77) is rejecting the request after authorization succeeded             | Distinguish authorization success from admission rejection; check `kubectl describe` events for the actual admission denial reason |
| Webhook authorizer causes cluster-wide request timeouts                            | External policy engine is slow, unreachable, or the failure policy isn't configured correctly              | Check webhook endpoint health and latency; ensure a sane timeout and explicit fail-closed behavior is configured                   |

## 9. Best Practices

- Standardize on `Node,RBAC` for self-managed clusters unless a specific, well-understood need for Webhook authorization exists; avoid re-introducing ABAC in any modern cluster.
- Treat every additional authorization mode as an expansion of attack surface requiring its own review, not a purely additive convenience.
- Use `kubectl auth can-i --as` liberally during RBAC design and troubleshooting to verify effective permissions quickly, rather than manually tracing bindings.

## 10. Common Anti-Patterns / Mistakes

- **Assuming RBAC is the only authorization mode active on a cluster** without checking `--authorization-mode`, leading to confusing situations where access doesn't match what the RBAC policy alone would suggest.
- **Configuring a Webhook authorizer with a fail-open policy**, silently granting broad access whenever the external policy engine is slow or unreachable.
- **Conflating an authorization `403 Forbidden` with an admission controller rejection** — both can produce similarly worded API errors, but they occur at different stages and require different remediation.

## 11. Interview Questions

**🎯 Beginner:** _"What's the difference between authentication and authorization in Kubernetes?"_
**Model answer:** Authentication (§73) establishes who is making a request — resolving it to a username and group set through a mechanism like an X.509 certificate or OIDC token. Authorization is the separate, subsequent stage that decides what that already-identified caller is allowed to do — which verbs against which resources, in which namespaces. A request can pass authentication cleanly (the caller's identity is confirmed) and still be denied at authorization if no policy grants that identity the requested action, producing a `403 Forbidden` rather than a `401 Unauthorized`.
_What the interviewer is probing for:_ Clean separation of the two stages and the distinct HTTP status codes each produces.

**🎯 Intermediate:** _"If a cluster is configured with `--authorization-mode=Node,RBAC,Webhook`, and a request would be denied by RBAC but explicitly allowed by the Webhook authorizer, what happens?"_
**Model answer:** The request is allowed. Kubernetes evaluates configured authorization modes in the order listed and grants access on the first explicit allow found from any mode — there's no concept of one mode's denial overriding another mode's later explicit allow, and there's no aggregation or voting across modes. In this case, Node would abstain (not a kubelet identity), RBAC would deny (no matching binding), but Webhook, evaluated last, explicitly allows it, so the overall result is an allowed request. This is exactly why understanding all active authorization modes — not just RBAC — matters when troubleshooting unexpected access.
_What the interviewer is probing for:_ Precise understanding of the multi-mode evaluation order and that it's additive/first-allow-wins, not consensus-based.

**🎯 Senior:** _"Why is the Node authorizer specifically important for cluster security, and what would happen without it?"_
**Model answer:** The Node authorizer restricts each kubelet's API access to only the resources genuinely related to Pods scheduled on its own node — its own Node object, the Pods bound to it, and the Secrets/ConfigMaps those specific Pods reference. Without it, a kubelet's identity would need to rely purely on RBAC bindings, and because every kubelet in a cluster typically shares a similar certificate structure (`system:node:<name>` in the `system:nodes` group), a single overly broad RBAC ClusterRoleBinding to that group would grant every kubelet identical, often excessive access — meaning a single compromised node's kubelet certificate could be used to read every Secret in the cluster, not just the ones relevant to workloads actually running there. The Node authorizer closes this gap by enforcing node-scoped relevance as a first-class authorization rule, independent of whatever RBAC bindings exist.
_What the interviewer is probing for:_ Concrete understanding of why the Node authorizer exists as a distinct mechanism rather than being fully subsumed by RBAC, and its role in limiting blast radius.

**🎯 Architect:** _"You're asked to add dynamic, time-of-day and change-window-aware policy on top of an existing RBAC-based cluster. How would you design this, and what are the risks?"_
**Model answer:** RBAC has no native concept of time-based or contextual conditions — it's a static allow-list keyed on user/group, verb, and resource, with no way to express "allow this only during business hours" or "deny destructive operations outside an approved change window." I'd add a Webhook authorizer, configured after RBAC in the `--authorization-mode` list, that calls out to a purpose-built policy engine (OPA/Gatekeeper acting in an authorization-webhook capacity, or a custom service) evaluating a `SubjectAccessReview` against the extra contextual rules. Critically, I'd design the webhook to only ever add _additional_ restriction on top of what RBAC allows, never grant access RBAC itself wouldn't — meaning the webhook's own policy logic should default to abstain-or-deny rather than explicit-allow, keeping RBAC as the authoritative base grant and the webhook purely as an extra restriction layer applied through careful ordering and fail-closed configuration. I'd also insist on a strict timeout and a fail-closed policy for the webhook call itself, since a fail-open webhook authorizer under network partition would silently bypass the very restriction it exists to enforce, and I'd monitor webhook latency closely since it sits directly in the request path for every authorization decision reaching it.
_What the interviewer is probing for:_ Ability to extend Kubernetes' native authorization model safely for a genuine gap (contextual/dynamic policy) without introducing a privilege-escalation or fail-open risk in the process.

## 12. Common Misconceptions

1. **"RBAC is the only authorization mechanism in Kubernetes."** It's the default and near-universal choice, but ABAC, Node, and Webhook are all distinct, independently configurable authorization modes that can run alongside it.
2. **"Multiple authorization modes work like a voting system, requiring majority approval."** Evaluation is sequential, and the very first explicit allow from any configured mode grants the request — there's no aggregation across modes.
3. **"A `403 Forbidden` and admission controller rejection are the same kind of failure."** They occur at genuinely different stages of the request lifecycle (authorization versus admission, §77) and require different diagnostic approaches.
4. **"The Node authorizer is redundant with RBAC."** It enforces node-scoped relevance as a distinct rule that RBAC's group/user model cannot express on its own, meaningfully limiting the blast radius of a single compromised kubelet.

## 13. 🔑 Key Takeaways

- Authorization is a separate stage from authentication, deciding what an already-identified caller can do, evaluated across one or more configured modes.
- Kubernetes supports RBAC, ABAC (legacy), Node, and Webhook authorization modes, evaluated in the order configured in `--authorization-mode`, with the first explicit allow from any mode granting the request.
- The Node authorizer scopes kubelet access to only the resources relevant to its own node, meaningfully limiting the blast radius of a single compromised node beyond what RBAC alone would enforce.
- ABAC is effectively legacy; `Node,RBAC` is the standard modern baseline, with Webhook added only for genuine dynamic/contextual policy needs.
- Additional authorization modes expand attack surface, not just capability — a fail-open Webhook authorizer or an overly permissive ABAC policy file can silently widen access beyond what RBAC alone would allow.

## 14. Related Concepts & What's Next

This section builds directly on §73's authentication chain, which establishes the identity that every authorization decision is made against. With the four authorization modes now understood at a conceptual level, §75 goes deep on the mode virtually every production cluster actually relies on day to day: RBAC's own API objects — Roles, ClusterRoles, RoleBindings, and ClusterRoleBindings — and exactly how their scoping and aggregation rules work in practice.

**Next Section:** §75 — `Section-75-Part10-RBAC-Deep-Dive-Roles-ClusterRoles-RoleBindings.md`
